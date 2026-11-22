# ExecutorCompletionService nhận kết quả theo thứ tự hoàn tất trong Java

Khi gửi nhiều tác vụ độc lập vào một `ExecutorService`, chúng có thể bắt đầu, kết thúc, thất bại hoặc bị hủy ở những thời điểm khác nhau. Nếu chương trình nhận các `Future` rồi lần lượt gọi `get()` theo **thứ tự submit**, nó có thể bị kẹt ở tác vụ đầu tiên còn chậm, dù những tác vụ submit sau đã hoàn thành. `ExecutorCompletionService<V>` giải quyết chính bài toán **thu thập kết quả theo thứ tự các tác vụ hoàn tất và được đưa vào completion queue**, thay vì thứ tự gửi.

Ví dụ: ba truy vấn A, B, C được gửi theo thứ tự A→B→C, nhưng B xong trước, C xong thứ hai và A xong sau cùng. Với `ExecutorCompletionService`, một consumer có thể lấy kết quả B, C, A và xử lý ngay khi từng kết quả sẵn sàng. Không cần chờ A trước khi xem kết quả B.

Bài Knowledge này thuộc phần **Future & Scheduling trong Java Concurrency nói chung**. Nội dung đi từ mô hình API, so sánh cách dùng Future, ví dụ Java 17+ có stdout xác định, xử lý lỗi/hủy/timeout, đến lựa chọn cấu hình executor và lưu ý vận hành. Những API tích hợp riêng của Spring nằm ngoài phạm vi.

## 1. Bài toán head-of-line blocking khi duyệt Future theo thứ tự submit

Một cách làm thông dụng là submit nhiều tác vụ và lưu các Future trong list:

~~~java
List<Future<String>> futures = new ArrayList<>();
futures.add(executor.submit(taskA));
futures.add(executor.submit(taskB));
futures.add(executor.submit(taskC));

for (Future<String> future : futures) {
    System.out.println(future.get());
}
~~~

Đây là **mảnh minh họa**, giả định `executor` và ba `Callable<String>` đã tồn tại; method chứa nó phải xử lý `InterruptedException`, `ExecutionException`.

Vòng lặp đọc Future theo thứ tự list. Khi `taskA` chậm:

~~~text
Submit:         A --------> B --------> C
Hoàn tất thật:  B --------> C --------> A
get(list):      chờ A................................
                [in A] [in B] [in C]
~~~

Tác vụ B, C có thể đã làm xong nhưng kết quả chưa được tiêu thụ. Đây là **head-of-line blocking ở tầng xử lý kết quả**: caller tự áp đặt thứ tự tiêu thụ không cần thiết. Không phải executor bắt buộc chạy task theo thứ tự đó.

Nếu bài toán cần xử lý kết quả ngay khi từng tác vụ hoàn thành (fan-out/fan-in độc lập), completion service là công cụ thích hợp. Nếu cần kết quả được xuất **đúng vị trí ban đầu** theo request, thứ tự submit có thể lại là yêu cầu hợp lệ và cần sắp xếp ở tầng presentation.

## 2. ExecutorCompletionService là gì?

`java.util.concurrent.ExecutorCompletionService<V>` triển khai interface `CompletionService<V>`. Nó kết hợp:

1. **Một Executor đã có sẵn:** chịu trách nhiệm thực thi các task, định nghĩa số worker, queue, chính sách từ chối, vòng đời và tài nguyên.
2. **Một completion queue:** chứa các `Future<V>` của task đã được xử lý xong theo giao thức completion service.
3. **API submit và nhận kết quả:** `submit(...)` gửi work; `take()` hoặc `poll()` lấy completed Future ra khỏi queue.

Tạo đối tượng:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(3);
CompletionService<String> completion =
        new ExecutorCompletionService<>(executor);
~~~

Đây là mảnh mã minh họa, cần import `ExecutorService`, `Executors`, `CompletionService`, `ExecutorCompletionService`. `ExecutorCompletionService` không tạo thêm pool worker bí mật. Nó sử dụng executor được truyền vào.

### 2.1 Sơ đồ luồng dữ liệu

~~~text
Producer / submitter
       |
       | submit(callable A)
       | submit(callable B)
       | submit(callable C)
       v
+----------------------------+
| Executor / worker threads  |
|    A: chậm                 |
|    B: nhanh                |
|    C: trung bình           |
+----------------------------+
       |
       | mỗi task hoàn tất -> completed Future
       v
+----------------------------+
| Completion queue           |
|  [Future(B)] [Future(C)]   |
|                   ... [A]  |
+----------------------------+
       |
       | take()/poll()
       v
Consumer -> Future.get() -> value hoặc exception
~~~

**Đừng nhầm:** completion queue chứa **Future đã hoàn tất**, không nhất thiết chứa thành công value. Task ném exception vẫn tạo completed Future để consumer lấy; lỗi nghiệp vụ được phát hiện khi gọi `get()`.

Cũng đừng nhầm completion queue với **work queue của ThreadPoolExecutor**. Work queue chứa tác vụ chưa được worker lấy chạy; completion queue chứa các Future đã xong, chờ consumer nhận. Hai queue có vai trò và giới hạn tài nguyên khác nhau.

## 3. API cốt lõi và hợp đồng blocking

| API | Ý nghĩa | Có chờ không? |
| --- | --- | --- |
| `submit(Callable<V>)` | Gửi một task trả value hoặc exception, nhận `Future<V>` dùng để theo dõi/hủy riêng task đó. | Submission bản thân không chờ completion; có thể bị reject bởi executor. |
| `submit(Runnable, V result)` | Gửi Runnable, dùng result định sẵn nếu Runnable hoàn thành bình thường. | Không chờ completion. |
| `take()` | Lấy và loại khỏi completion queue **một Future đã hoàn tất**. | **Chờ vô thời hạn** nếu queue chưa có phần tử, trừ khi bị interrupt. |
| `poll()` | Thử lấy ngay một completed Future. | Không chờ; trả `null` nếu queue đang trống. |
| `poll(timeout, unit)` | Đợi có giới hạn để lấy một completed Future. | Chờ tới khi có phần tử hoặc deadline; trả `null` khi hết hạn. |
| `Future.get()` | Lấy giá trị hoặc exception của Future được lấy ra. | Với completed Future từ queue, bình thường không còn phải chờ task chạy; vẫn cần xử lý lỗi/hủy/interruption. |
| `Future.cancel(true)` | Yêu cầu hủy một task qua Future đã lưu. | Không phải lệnh kill đồng bộ; kết quả/timing còn phụ thuộc task và executor. |

`take()` và timed `poll()` có thể ném `InterruptedException`. `Future.get()` có thể ném `ExecutionException` nếu callable thất bại, `CancellationException` nếu Future bị hủy; phải phân biệt với `InterruptedException` của consumer đang chờ.

### 3.1 Chỉ trả completion, không đảm bảo thứ tự submit

Nếu A xong sau B, thông thường Future của B xuất hiện trong completion queue trước A. Nhưng khi nhiều task hoàn thành gần như đồng thời, **không có hợp đồng thứ tự tổng thể theo nanosecond/dòng log** để người dùng dự đoán tie-break. Thứ tự consumer quan sát là thứ tự các Future được enqueue để lấy.

Đặc biệt, scheduler có thể thay đổi thứ tự chạy giữa các lần thực thi. Một chương trình không được assert cứng “B luôn nhanh hơn A” nếu chỉ dùng `Thread.sleep` để tạo tốc độ giả định.

### 3.2 Không tự biết khi nào toàn bộ nhóm đã xong

`CompletionService` **không có phương thức** kiểu `closeSubmissions()` hoặc `takeAll()` biết chính xác số task của một lô. Consumer phải quản lý:

- Bao nhiêu task đã **submit thành công**;
- Bao nhiêu completion đã nhận;
- Khi nào ngừng submit hoặc chuyển sang lô mới;
- Cách xử lý task bị reject, cancel, timeout hoặc producer ngừng giữa chừng.

Mẫu thông dụng là đếm `n` lần submit rồi gọi `take()` **đúng n lần**, với điều kiện tất cả task được chấp nhận và sẽ thật sự hoàn tất theo contract. Nếu một callable block mãi, `take()` có thể block mãi; cần timeout/cancellation policy.

## 4. Ví dụ Java 17+: chứng minh kết quả nhận theo thứ tự hoàn tất

Để tránh ngẫu nhiên do scheduler, ví dụ dùng `CountDownLatch` làm ba cổng. Main **submit theo A→B→C**, sau đó lần lượt mở cổng B, C, A và nhận **một completion trước khi mở cổng tiếp theo**. Nhờ vậy stdout xác định mà không cần `sleep()`.

Tạo file `CompletionOrderDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class CompletionOrderDemo {
    private static Callable<String> job(
            String name, CountDownLatch started, CountDownLatch gate) {
        return () -> {
            started.countDown();
            gate.await();
            return name;
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CompletionService<String> cs = new ExecutorCompletionService<>(pool);
        CountDownLatch allStarted = new CountDownLatch(3);
        CountDownLatch a = new CountDownLatch(1);
        CountDownLatch b = new CountDownLatch(1);
        CountDownLatch c = new CountDownLatch(1);

        try {
            cs.submit(job("A", allStarted, a));
            cs.submit(job("B", allStarted, b));
            cs.submit(job("C", allStarted, c));
            allStarted.await();

            b.countDown();
            System.out.println("Completed: " + cs.take().get());

            c.countDown();
            System.out.println("Completed: " + cs.take().get());

            a.countDown();
            System.out.println("Completed: " + cs.take().get());
        } finally {
            a.countDown();
            b.countDown();
            c.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac CompletionOrderDemo.java
java CompletionOrderDemo
~~~

Kết quả bình thường, không có interruption bên ngoài:

~~~text
Completed: B
Completed: C
Completed: A
~~~

### 4.1 Vì sao không thể ra thứ tự khác?

- Pool có **ba worker** nên ba task đều có thể đi tới `allStarted.countDown()` rồi chờ cổng riêng.
- `allStarted.await()` của main đợi tới khi cả ba task đã đạt mốc.
- B được phép thoát gate đầu tiên; A và C vẫn bị chặn. `cs.take()` chỉ có thể nhận completion B ở bước này.
- Chỉ **sau khi** main đã lấy B, nó mới mở gate C; A vẫn bị chặn, nên completion kế tiếp là C.
- Tương tự, gate A chỉ mở cuối cùng.
- `cs.take()` trả Future hoàn tất; `get()` trả value A/B/C. `finally` mở tất cả gate khi có lỗi ở main, rồi yêu cầu executor shutdown để tránh để worker chờ vô hạn trong ví dụ.

**`allStarted` và các gate chỉ để thử nghiệm thứ tự:** ứng dụng thực tế thường chạy các tác vụ I/O/CPU độc lập và không chủ động áp thứ tự completion. Lợi ích là consumer có thể xử lý *bất kỳ task nào hoàn tất trước*, không bị ép chờ task đầu trong list.

## 5. Đọc kết quả theo submission order so với completion order

Hai kiểu consumer khác nhau:

### 5.1 Theo submission order

~~~java
List<Future<Result>> futures = new ArrayList<>();
for (Request request : requests) {
    futures.add(executor.submit(() -> call(request)));
}

for (Future<Result> future : futures) {
    consume(future.get());
}
~~~

Đây là **mảnh code minh họa** cần class `Request`/`Result`, `call`, `consume` và import thích hợp. `get()` trên Future đầu tiên chậm sẽ làm consumer chờ, dù Future thứ hai đã hoàn tất.

### 5.2 Theo completion order

~~~java
CompletionService<Result> cs =
        new ExecutorCompletionService<>(executor);
int submitted = 0;

for (Request request : requests) {
    cs.submit(() -> call(request));
    submitted++;
}

for (int i = 0; i < submitted; i++) {
    Future<Result> completed = cs.take();
    consume(completed.get());
}
~~~

Đây cũng là mảnh minh họa. Điểm khác biệt là consumer đợi `cs.take()` lấy **bất kỳ Future đã hoàn tất**; không phụ thuộc request nào được gửi trước.

### 5.3 Khi nào vẫn phải giữ thứ tự đầu vào?

Ví dụ danh sách kết quả hiển thị đúng theo chỉ số dòng yêu cầu. Completion order vẫn có thể dùng cho **xử lý nội bộ**, nhưng phải mang theo ID/index:

~~~java
record IndexedResult(int index, String value) {}

cs.submit(() -> new IndexedResult(index, query()));
~~~

Đây là mảnh code, giả định `cs` có generic type `IndexedResult`, `index` là biến local effectively final cho từng task, `query()` tồn tại. Consumer lưu từng result vào slot tương ứng rồi mới xuất theo order. **Completion order và presentation order là hai quyết định khác nhau**.

## 6. Exception không làm mất một Future đã hoàn tất

Task có thể ném exception, nhưng việc đó không có nghĩa completion service “chỉ trả success”. `submit(Callable)` thường giữ exception trong Future; consumer lấy Future ra rồi gọi `get()` mới biết task thành công hay thất bại.

Tạo file `CompletionFailureDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CompletionFailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CompletionService<String> cs = new ExecutorCompletionService<>(pool);
        CountDownLatch allowSuccess = new CountDownLatch(1);

        try {
            cs.submit(() -> {
                throw new IllegalStateException("source unavailable");
            });
            cs.submit(() -> {
                allowSuccess.await();
                return "OK";
            });

            // Success task vẫn chờ gate: failure phải được nhận trước.
            for (int i = 0; i < 2; i++) {
                Future<String> completed = cs.take();
                try {
                    System.out.println("Success: " + completed.get());
                } catch (ExecutionException e) {
                    System.out.println("Failure: "
                            + e.getCause().getClass().getSimpleName());
                    allowSuccess.countDown();
                }
            }
        } catch (ExecutionException e) {
            throw new AssertionError(e);
        } finally {
            allowSuccess.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac CompletionFailureDemo.java
java CompletionFailureDemo
~~~

Stdout trong trường hợp bình thường:

~~~text
Failure: IllegalStateException
Success: OK
~~~

**Vì sao?** Task thành công phải đợi `allowSuccess`; task thất bại không cần gate nên Future thất bại xuất hiện trước. Consumer `take()` được Future thất bại, và `get()` ném `ExecutionException` chứa `IllegalStateException` ở `getCause()`. Sau khi bắt failure, main mở gate cho task còn lại.

Lưu ý: đây là mẫu dạy học tập trung vào exception. Trong code production nên có **nhánh xử lý lỗi theo từng task**, không dùng một catch `ExecutionException` bao trùm cả vòng lặp rồi bỏ qua các completion còn lại. Nếu một task có thể mắc kẹt vô hạn, `take()` cũng có thể chờ mãi, cần deadline/cancellation.

### 6.1 Không nhầm exception ở submit và exception ở get

- **RejectedExecutionException** có thể xảy ra ngay tại `submit()` nếu executor không chấp nhận task; khi đó không có một submission thành công tương ứng để consumer chờ.
- **ExecutionException** xảy ra ở `get()` nếu task đã chạy và ném exception.
- **CancellationException** ở `get()` khi Future ở trạng thái cancelled.
- **InterruptedException** ở consumer khi đang chờ `take()`/`get()`; đây là đường cancellation của caller, không phải lỗi của callable.

Bộ đếm số completion cần đợi chỉ nên tăng cho các submission **đã được chấp nhận**. Nếu đếm số request đầu vào nhưng có request bị reject, consumer có thể đợi một “completion chưa từng được đăng ký”.

## 7. take(), poll() và timed poll: chọn theo yêu cầu chờ

`take()` phù hợp khi biết ít nhất một task được chấp nhận và dự kiến sẽ hoàn thành trong thời gian hữu hạn. Nó **block vô hạn** nếu completion queue trống; điều đó có thể đến từ task chậm, task bị kẹt hoặc không có task nào được submit.

`poll()` dùng khi consumer phải làm việc khác ngay nếu chưa có kết quả:

~~~java
Future<String> ready = cs.poll();
if (ready != null) {
    use(ready.get());
}
~~~

Đây là mảnh minh họa, giả định `cs`/`use` có sẵn và method xử lý `InterruptedException`, `ExecutionException`.

`poll(timeout, unit)` hỗ trợ giới hạn thời gian đợi một completion:

~~~java
Future<String> ready = cs.poll(200, TimeUnit.MILLISECONDS);
if (ready == null) {
    onTimeout();
} else {
    use(ready.get());
}
~~~

Đây cũng là mảnh minh họa. Trả `null` là **chưa lấy được completion trong cửa sổ chờ**, không chứng minh mọi task đã chết hoặc executor không hoạt động. Timed poll **không tự cancel** task còn đang chạy.

### 7.1 Timeout của collector khác timeout của từng task

Một consumer có thể đợi tối đa 2 giây cho **cả lô**, trong khi mỗi task có thời gian xử lý khác nhau. Nếu gọi `poll(2, SECONDS)` **lặp lại cho từng kết quả**, tổng thời gian có thể lớn hơn 2 giây nhiều lần.

Hãy chọn một **deadline tổng** và tính thời gian còn lại ở mỗi lần poll. Không reset toàn bộ timeout ở mỗi vòng.

### 7.2 Minh họa deadline tổng

~~~java
long deadline = System.nanoTime() + timeoutNanos;

for (int received = 0; received < submitted; received++) {
    long left = deadline - System.nanoTime();
    if (left <= 0L) {
        break;
    }
    Future<Result> result = cs.poll(left, TimeUnit.NANOSECONDS);
    if (result == null) {
        break;
    }
    handle(result.get());
}
~~~

Đây là mảnh minh họa, giả định timeoutNanos có giá trị hợp lý, `submitted` là số task được chấp nhận và `cs`/`handle` có kiểu đúng. `System.nanoTime()` thích hợp để đo khoảng thời gian trôi qua, không phải timestamp wall-clock. Với deadline gần giới hạn `long`, cần thiết kế tính toán tránh overflow; ở đây chỉ minh họa cách không cấp lại full timeout mỗi lần.

Khi deadline hết, chương trình **phải có chính sách xử lý những task còn lại**: cho tiếp tục chạy và thu dọn sau, yêu cầu hủy, hoặc trả partial results. Chỉ thoát vòng poll mà không biết ai sở hữu những task còn chạy là một lỗi lifecycle.

## 8. First successful result: lấy kết quả hữu ích đầu tiên

Một tình huống thực tế: gửi cùng yêu cầu tới nhiều nguồn dữ liệu, cần **kết quả thành công đầu tiên**, không phải Future submit đầu tiên. `CompletionService` hữu ích vì có thể:

1. Submit tất cả candidate tasks.
2. Nhận completed Future sớm nhất.
3. Nếu `get()` thất bại, tiếp tục đợi một completion khác.
4. Nếu thành công, lưu kết quả rồi **yêu cầu hủy các task còn lại**.
5. Nếu mọi task thất bại, trả một failure được định nghĩa rõ.

**Không được coi “completion đầu tiên” luôn là “success đầu tiên”**. Task lỗi rất nhanh có thể đến trước mọi task thành công.

### 8.1 Java 17+: first-success pattern chạy được

Tạo file `FirstSuccessCompletionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FirstSuccessCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CompletionService<Integer> cs = new ExecutorCompletionService<>(pool);
        CountDownLatch blocker = new CountDownLatch(1);
        List<Future<Integer>> submitted = new ArrayList<>();

        try {
            submitted.add(cs.submit(() -> {
                throw new IllegalStateException("source A failed");
            }));
            submitted.add(cs.submit(() -> 42));
            submitted.add(cs.submit(() -> {
                blocker.await();
                return -1;
            }));

            Integer answer = null;
            int failures = 0;
            for (int i = 0; i < submitted.size(); i++) {
                Future<Integer> completed = cs.take();
                try {
                    answer = completed.get();
                    break;
                } catch (ExecutionException e) {
                    failures++;
                }
            }

            if (answer != null) {
                System.out.println("First success: " + answer);
            } else {
                System.out.println("All failed: " + failures);
            }
        } finally {
            for (Future<Integer> future : submitted) {
                future.cancel(true);
            }
            blocker.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FirstSuccessCompletionDemo.java
java FirstSuccessCompletionDemo
~~~

Stdout bình thường:

~~~text
First success: 42
~~~

Ở đây một task lỗi, một task trả 42 và một task bị block trên latch. Bất kể task lỗi hay task 42 hoàn thành trước, consumer tiếp tục qua error và dừng ngay khi lấy được value 42. `finally` yêu cầu hủy những task chưa xong và mở blocker để không rò thread.

**Giới hạn:** `future.cancel(true)` là yêu cầu hủy; nếu task thật bỏ qua interruption, nó có thể tiếp tục. Với hệ thống thật, cần có deadline tổng để first-success không chờ vô hạn khi không nguồn nào thành công, đồng thời xử lý `CancellationException` nếu candidate bị hủy bởi bên khác.

Nếu “kết quả đầu tiên” có ý nghĩa **first response bao gồm error**, không loop tìm success. Hợp đồng nghiệp vụ phải quyết định.

## 9. Hủy tác vụ và completion queue: những điều dễ hiểu sai

`ExecutorCompletionService.submit` trả một `Future<V>` để caller lưu và chủ động hủy. `Future.cancel(true)` có thể đánh dấu Future cancelled, và khi `get()` trên Future đó sẽ nhận `CancellationException`.

Tuy nhiên cần phân biệt:

- **Future trạng thái cancelled**;
- **callable thực sự đã thôi chạy hay chưa**;
- **Future đã được đặt vào completion queue hay chưa**.

Các trạng thái không nhất thiết diễn ra tức thì cùng thời điểm. Đặc biệt `ExecutorCompletionService` dùng wrapper để enqueue completed task khi wrapper hoàn tất; đừng giả định việc gọi `cancel()` ở một thread lập tức tạo đúng một completion ngay lập tức có sẵn qua `take()` trong mọi race/hệ executor.

Khi caller muốn chấm dứt sớm và không còn tiêu thụ mọi completion, lưu danh sách Future do mình submit để cancel/cleanup, thay vì phụ thuộc vào số phần tử của completion queue để suy ra tất cả user task đã dừng.

### 9.1 Xử lý CancellationException khi get

~~~java
try {
    Result value = completed.get();
    consume(value);
} catch (CancellationException e) {
    recordCancelled();
} catch (ExecutionException e) {
    recordFailure(e.getCause());
}
~~~

Đây là mảnh minh họa trong method đã xử lý `InterruptedException`; `Result` và các helper tự định nghĩa. `CancellationException` là unchecked, **không** bị bọc trong `ExecutionException`. Không nên dùng `catch (Exception)` chung và ghi nhãn mọi tình huống là “task failed”; việc hủy có semantics riêng.

### 9.2 Không chặn consumer bằng công việc xử lý quá lâu

`take()` trả completion theo thứ tự queue, nhưng nếu consumer xử lý mỗi kết quả rất lâu trong cùng thread, các completed Future khác sẽ tồn đọng. Completion service không tự song song hóa **consumer logic**. Nếu cần parse/aggregate nặng, xem xét pipeline khác hoặc executor riêng, nhưng phải kiểm soát backpressure và ordering.

## 10. Completion queue mặc định và rủi ro bounded queue

Constructor thường gặp:

~~~java
CompletionService<Result> cs =
        new ExecutorCompletionService<>(executor);
~~~

Dùng completion queue mặc định kiểu `LinkedBlockingQueue` không có giới hạn thực tế theo số lượng task của một lô nhỏ; cần lưu ý khi submit nhiều task nhanh mà consumer không tiêu thụ.

Có overload nhận queue do caller cung cấp:

~~~java
new ExecutorCompletionService<Result>(executor, completionQueue);
~~~

Nhưng **đừng mặc định truyền một `ArrayBlockingQueue` nhỏ** để “thêm backpressure”. Theo hợp đồng API, completion queue được xem là **unbounded** đối với nhu cầu enqueue completed Future; khi task hoàn tất, service dùng `add` chứ không chờ `put`. Nếu queue do caller cung cấp có capacity hữu hạn và đã đầy, việc thêm completed task có thể thất bại khiến completed Future **không còn lấy được qua completion service** dù task đã chạy xong. Đây là một failure mode quan trọng.

Nếu thật sự cần backpressure, hãy:

- **Giới hạn số task đang được submit/in-flight**, ví dụ dùng `Semaphore` với ownership rõ.
- Tiêu thụ kết quả đủ nhanh hoặc dùng consumer worker phù hợp.
- Cấu hình giới hạn queue đầu vào của `ThreadPoolExecutor` cùng rejection policy có chủ đích, nhưng nhớ đây là **work queue**, khác completion queue.
- Không thay queue của completion service bằng bounded queue một cách tùy tiện.

**Phân biệt hai tầng giới hạn tài nguyên:** work queue giới hạn số task đang chờ được chạy; in-flight limit giới hạn số task chưa được thu hồi completion; completion queue chứa các Future đã xong. Chỉ giới hạn work queue không bảo đảm completed results sẽ được tiêu thụ đủ nhanh.

## 11. Chọn ExecutorService và thread pool

`ExecutorCompletionService` không cung cấp scheduling policy mới. Nó dùng executor được đưa vào:

| Executor | Đặc tính | Phù hợp / hạn chế |
| --- | --- | --- |
| `newFixedThreadPool(n)` | Có tối đa n worker hoạt động; task dư được queue. | Dễ minh họa và kiểm soát concurrency nhưng work queue mặc định có thể tích tụ không giới hạn thực tế. |
| `ThreadPoolExecutor` cấu hình riêng | Có core/max size, work queue, thread factory, rejection policy. | Phù hợp khi cần giới hạn concurrency, queue và saturation policy rõ. |
| `newSingleThreadExecutor()` | Một worker thực thi task tuần tự theo queue. | Completion order thường gắn với execution order của task; không có lợi ích fan-out song song. |
| `newCachedThreadPool()` | Có thể tạo thêm worker theo nhu cầu. | Dễ tăng tài nguyên khi submit rất nhiều blocking tasks; phải giới hạn tải. |
| `newVirtualThreadPerTaskExecutor()` (Java 21+) | Một virtual thread cho mỗi task. | Có thể phù hợp tác vụ chờ I/O, nhưng phải kiểm soát số yêu cầu/tài nguyên bên ngoài; không phải API Java 17. |

Ví dụ Java 17 trong bài dùng fixed pool để tránh phụ thuộc API mới. `newVirtualThreadPerTaskExecutor()` chỉ có ở **Java 21+**; không chạy dòng đó trong ví dụ Java 17.

### 11.1 Bài toán pool starvation

Nếu các task trong cùng một pool nhỏ **chờ completion của những task khác đang nằm chờ được chạy trong chính pool**, có thể xảy ra thread-pool starvation. Ví dụ pool chỉ có một worker, task A submit B vào chính pool rồi gọi `Future.get()` đợi B, trong khi worker đang bị A chiếm. B không có worker để chạy.

`CompletionService` không chữa dependency deadlock/starvation của task. Nó chỉ thu thập completion. Thiết kế đồ thị phụ thuộc và capacity của pool vẫn là trách nhiệm người dùng.

## 12. CompletionService và ExecutorService.invokeAll()

`ExecutorService.invokeAll(collection)` hữu ích khi cần chạy một tập task và đợi **cả tập** hoàn tất hoặc hết timeout, rồi nhận các Future theo **thứ tự iterator đầu vào**. `invokeAny(collection)` hữu ích khi muốn một kết quả thành công sớm và không cần quản lý loop completion thủ công.

| Yêu cầu | API thường phù hợp |
| --- | --- |
| Thu thập kết quả **từng cái ngay khi xong** | `ExecutorCompletionService.take()/poll()` |
| Chạy một tập task rồi chờ kết quả tất cả, trả Future theo thứ tự input | `ExecutorService.invokeAll()` |
| Cần một kết quả thành công sớm | `ExecutorService.invokeAny()` hoặc CompletionService để tùy chỉnh policy |
| Một task với một Future | `ExecutorService.submit()` + `Future.get()` |
| Ghép pipeline bất đồng bộ và transformation | `CompletableFuture` combinators |
| Kết quả cần stream/event-driven nonblocking phức tạp | `CompletableFuture` hoặc framework/reactive API có hợp đồng phù hợp |

`invokeAll` không tự đưa kết quả theo thứ tự hoàn tất chỉ vì các Future có thể đã done. `CompletionService` thuận lợi khi caller cần xử lý **partial results liên tục**.

`invokeAny` có logic hủy những candidate còn lại theo hợp đồng API và trả một kết quả thành công; nếu nhu cầu chính xác như vậy, nó có thể đơn giản hơn việc viết lại toàn bộ thuật toán. CompletionService phù hợp khi cần thêm metrics, xử lý từng lỗi, fallback, partial collection hoặc custom deadline.

### 12.1 So với CompletableFuture

`CompletableFuture.anyOf(...)` hoàn tất khi **bất kỳ future** nào hoàn tất, kể cả exceptional completion; không nhất thiết là *first success*. Muốn xử lý một stream nhiều completion có state, ordering và backpressure thì cần thiết kế pipeline/callback phù hợp.

`CompletionService` cho một API **blocking pull-based**: consumer chủ động `take()`/`poll()`. `CompletableFuture` thiên về callback/composition. Chọn theo nhu cầu orchestration và cách ứng dụng xử lý thread khi chờ.

## 13. Memory consistency và thread safety

Các primitive trong `java.util.concurrent` có các **memory-consistency effects** được tài liệu mô tả. Với `ExecutorService`, những hành động của thread **trước khi submit** task happens-before các hành động trong task; những hành động của task happens-before hành động **sau khi caller nhận kết quả qua `Future.get()`** theo hợp đồng.

Điều này quan trọng khi task tính một result hoặc cập nhật trạng thái trước khi kết thúc. Tuy nhiên:

- `CompletionService.take()` lấy một completed Future; `get()` là cách rõ ràng để thu giá trị/error và nhận hợp đồng memory-consistency của Future.
- Một object mutable được đưa vào task rồi bị **caller sửa tiếp trong lúc task đang chạy** vẫn có thể race. Submit không đóng băng object.
- Một result object mutable được publish rồi bị worker/thread khác sửa không đồng bộ sau completion vẫn cần ownership/synchronization riêng.
- Completion order **không** khiến các task chia sẻ mutable state tự thread-safe.
- Nếu các task update cùng một invariant, cần `synchronized`, atomic aggregate hoặc cấu trúc concurrent theo đúng scope; completion service chỉ quản lý thu kết quả.

### 13.1 Task thuần và snapshot immutable

Một cách đơn giản để giảm race là truyền input immutable/snapshot vào mỗi callable và trả output immutable/result value, rồi aggregate kết quả trong một consumer thread. Nếu kết quả được xử lý trên nhiều consumer thread, cần bảo vệ state tổng hợp theo contract.

## 14. Thu thập nhiều loại kết quả và gắn metadata

Vì completion queue chỉ trả Future, caller có thể không biết ngay kết quả thuộc request nào nếu Callable trả mỗi một giá trị thuần. Nên **gói metadata vào result**:

~~~java
record QueryResult(String sourceId, long elapsedNanos, String value) {}

cs.submit(() -> {
    long start = System.nanoTime();
    String value = fetchFromSource();
    return new QueryResult(
            sourceId, System.nanoTime() - start, value);
});
~~~

Đây là mảnh minh họa, giả định `cs` nhận `QueryResult`, `sourceId` là effectively final, `fetchFromSource` tồn tại. Nhờ metadata, consumer có thể:

- Log nguồn nào xong trước;
- Lưu results theo ID vào map;
- Tính latency từng nguồn;
- Retry có chọn lọc;
- Tổng hợp partial success/failure.

Nếu task lỗi trước khi trả result, metadata trong result không tồn tại. Muốn gắn lỗi với request cụ thể, có thể giữ mapping `Future<?> → RequestId` ở phía submitter (cần map thread-safe nếu collector dùng thread khác), hoặc cho callable trả một `Outcome` chứa success/error thay vì ném exception. **Không biến mọi failure thành success im lặng**; contract cần phân biệt hai trạng thái.

### 14.1 Thứ tự nhận khác thứ tự hiển thị

Consumer có thể xử lý completion B trước A để cập nhật tiến độ, nhưng cuối cùng trả list kết quả theo A, B, C. Tách **order of processing** và **order of presentation** giúp tối ưu phản hồi sớm mà vẫn giữ giao diện/hợp đồng đúng.

## 15. Hạn chế outstanding tasks và thiết kế backpressure

Một hệ thống có hàng triệu request không thể luôn submit tất cả cùng lúc rồi mới bắt đầu lấy completion. Nó có thể giữ quá nhiều Future/callable, lấp đầy work queue hoặc gây áp lực bộ nhớ.

Mô hình **sliding window**:

~~~text
MAX_IN_FLIGHT = 20
submit tối đa 20 task
mỗi khi nhận một completion:
    xử lý outcome
    nếu còn input thì submit thêm 1 task
lặp đến khi:
    hết input và đã nhận hết in-flight completions
~~~

Đây là **mã giả**, không phải Java chạy độc lập. Cần quản lý chính xác biến `inFlight` và các nhánh submit failure/cancellation:

1. Tăng `inFlight` sau khi submit **thành công**.
2. Khi lấy completed Future qua `take/poll` và đã quyết định outcome, giảm `inFlight`.
3. Chỉ submit thêm khi còn input và không vượt giới hạn.
4. Khi cancellation/timeout, gửi yêu cầu hủy các task chưa hoàn tất và quản lý ownership/lifecycle.
5. Nếu producer hoặc consumer có nhiều thread, dùng synchronization để giữ đúng số in-flight.

Không nhất thiết dùng completion queue bounded để kiểm soát outstanding tasks; thường an toàn hơn để **completion queue nhận được mọi completed Future**, còn cửa sổ in-flight được giới hạn **trước khi submit**.

## 16. Interrupt, cancel và shutdown đúng cách

Một collector gọi `take()` có thể bị interrupt. Nếu method có thể khai báo `throws InterruptedException`, thường truyền lên để caller quyết định cancellation. Trong top-level worker `Runnable.run()`, có thể restore interrupted status rồi thoát:

~~~java
try {
    Future<Result> future = cs.take();
    consume(future.get());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Yêu cầu hủy outstanding tasks và thoát đúng policy.
}
~~~

Đây là mảnh code minh họa; `Result` và helpers đã được giả định. Nếu consumer ngừng sớm, những task vẫn đang chạy phải có **owner** quản lý. Không bỏ hết Future references rồi để executor chạy mãi mà không có shutdown policy.

### 16.1 Mẫu cleanup

~~~java
List<Future<Result>> futures = new ArrayList<>();
try {
    // Submit/collect theo contract của lô.
} finally {
    for (Future<Result> future : futures) {
        if (!future.isDone()) {
            future.cancel(true);
        }
    }
    executor.shutdownNow();
}
~~~

Đây là mảnh code minh họa. `shutdownNow()` là best effort và không đảm bảo mọi task ngừng ngay; nếu executor thuộc một thành phần khác, **không tự shutdown executor dùng chung**. Hãy đặt lifecycle owner rõ ràng: ai tạo pool thì thường chịu trách nhiệm đóng nó, còn thư viện nhận executor từ caller không nên lén shutdown.

Một task bỏ qua interruption hoặc kẹt trên I/O không có timeout có thể không chịu dừng. Cần timeout/resource-specific cancellation và observability phù hợp.

## 17. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Submit bằng ECS nhưng lưu Future rồi get theo list đầu vào. | Vẫn head-of-line blocking. | Dùng `take()/poll()` trên completion service để thu completion order. |
| Coi completion order luôn là đúng thứ tự theo thời gian thực. | Assertion flaky khi gần đồng thời. | Không dự đoán tie-break; dùng latch trong test cần thứ tự xác định. |
| Coi completed Future là success. | `get()` có thể ném ExecutionException/CancellationException. | Xử lý outcome của từng Future. |
| Gọi take quá số task đã submit thành công. | Có thể block mãi chờ completion không tồn tại. | Đếm accepted submissions; xử lý rejection. |
| Không có deadline khi task có thể kẹt. | Collector block vô hạn. | Timed poll/deadline/cancellation. |
| Gọi timed poll N lần với full timeout. | Deadline tổng bị kéo dài N lần. | Tính remaining time theo monotonic clock. |
| Dùng bounded completionQueue quá nhỏ. | `add` completed Future có thể fail, completion không lấy được. | Giới hạn in-flight trước submit, không chặn completion enqueue. |
| Quên shutdown executor do mình sở hữu. | Worker không-daemon có thể giữ process sống; rò tài nguyên. | Lifecycle trong finally, shutdown/awaitTermination phù hợp. |
| Shutdown executor được caller cung cấp. | Ảnh hưởng các subsystem dùng chung. | Rõ ownership; chỉ hủy task do mình sở hữu. |
| Hủy Future rồi coi worker đã chết tức thì. | Task có thể chưa hợp tác dừng. | Kiểm tra lifecycle, timeout và cleanup policy. |
| Consumer xử lý kết quả quá chậm. | Completion queue và bộ nhớ có thể tăng. | Theo dõi backlog, giới hạn in-flight hoặc tách stage xử lý. |
| Dùng pool một worker rồi task đợi task khác trong cùng pool. | Pool starvation/deadlock. | Sửa dependency graph và cấu hình executor. |
| Các task sửa cùng mutable map/list không đồng bộ. | Data race/invariant lỗi. | Immutable input/output hoặc synchronization thích hợp. |
| Chỉ muốn một kết quả thành công nhưng tự viết loop quá phức tạp. | Nhiều nhánh lỗi/hủy khó kiểm soát. | Xem xét `invokeAny()` khi contract phù hợp. |

## 18. Quy trình áp dụng vào ứng dụng thực tế

Trước khi dùng `ExecutorCompletionService`, hãy trả lời:

1. **Kết quả nào cần trước?** Có cần nhận bất kỳ completion nào ngay khi xong, hay vẫn phải xuất đúng thứ tự input?
2. **Các task có độc lập không?** Nếu task đợi nhau, completion order không giải quyết dependency.
3. **Executor do ai sở hữu?** Có được shutdown khi kết thúc workflow không?
4. **Số task giới hạn bao nhiêu?** Có nguy cơ submit quá nhiều hoặc tạo backlog?
5. **Bao nhiêu completion sẽ thu?** Bộ đếm dựa vào accepted submissions hay input dự kiến?
6. **Cách xử lý failure?** Ném exception, partial success, retry, fail-fast hay first success?
7. **Cancellation của leftover?** Có lưu Future handles để yêu cầu hủy khi timeout/đủ kết quả không?
8. **Deadline ở đâu?** Per task, toàn lô, hay cả hai? Có tính remaining time không?
9. **Dữ liệu được publish ra sao?** Callable nhận input immutable, Future.get công bố result, state tổng hợp có thread safety phù hợp?
10. **Quan sát hiệu năng gì?** Latency từng task, tỉ lệ lỗi, completion queue backlog, in-flight count, pool saturation, shutdown latency?
11. **Xử lý task bị reject?** Không chờ completion cho task chưa được chấp nhận.
12. **Không dùng completion queue làm cơ chế backpressure sai chỗ?** Giới hạn in-flight hoặc work queue đúng tầng.
13. **Có test thứ tự xác định bằng latch?** Không dùng sleep đoán thứ tự kết thúc.

Nếu các yêu cầu trên chỉ là “đợi tất cả xong rồi xử lý chung”, `invokeAll()` hoặc `CompletableFuture.allOf()` có thể gọn hơn. Nếu cần **xử lý dần theo hoàn tất**, ECS thể hiện ý định rất rõ.

## 19. Câu hỏi tự kiểm tra

**1.** Submit A, B, C; B và C xong trước A. Vì sao duyệt list Future theo submit order gây chậm?  
**Đáp:** `get()` trên A block consumer dù kết quả B/C đã hoàn tất; đây là head-of-line blocking ở tầng kết quả.

**2.** `ExecutorCompletionService.take()` trả về value hay Future?  
**Đáp:** Trả một `Future<V>` đã hoàn tất và lấy nó ra khỏi completion queue; cần `get()` để nhận value hoặc exception.

**3.** Task ném exception có được lấy qua take không?  
**Đáp:** Có, Future hoàn tất ngoại lệ vẫn được enqueue; `get()` ném `ExecutionException`.

**4.** `poll()` trả null nghĩa là tất cả task đã thất bại?  
**Đáp:** Không. Chỉ là queue chưa có completed Future tại thời điểm poll.

**5.** `poll(timeout)` hết hạn có tự cancel task còn chạy không?  
**Đáp:** Không. Cần cancellation policy riêng.

**6.** Vì sao completion order không bảo đảm tie-break khi hai task xong rất gần nhau?  
**Đáp:** Nó phản ánh thứ tự enqueue completion theo lịch chạy/runtime; không có đồng hồ tổng thể dùng để ép một thứ tự lịch sử xác định.

**7.** Một batch submit 10 task, 2 task bị reject. Collector nên đợi bao nhiêu completion?  
**Đáp:** Chỉ đợi số **accepted submissions**, không đợi hai task bị reject.

**8.** Có nên truyền `ArrayBlockingQueue(2)` làm completion queue cho 100 task không?  
**Đáp:** Không nếu không thể bảo đảm queue luôn có chỗ khi enqueue: `add` có thể fail và làm mất completed Future khỏi dịch vụ thu kết quả.

**9.** Muốn deadline tổng 5 giây, vì sao không gọi `poll(5s)` 100 lần?  
**Đáp:** Có thể chờ tổng cộng nhiều lần 5 giây; phải tính remaining time từ một deadline chung.

**10.** `Future.cancel(true)` có chắc khiến task dừng ngay không?  
**Đáp:** Không; đây là yêu cầu hủy/interruption, phụ thuộc task hợp tác và API blocking.

**11.** Khi nào `invokeAny()` có thể đơn giản hơn ECS tự viết?  
**Đáp:** Khi chỉ cần một kết quả thành công sớm và không cần custom policy/partial progress.

**12.** Nếu muốn hiển thị kết quả A, B, C theo input order nhưng vẫn xử lý nhanh ngay khi chúng xong, làm sao?  
**Đáp:** Đưa request ID/index vào result, xử lý theo completion order rồi sắp xếp/đặt vào slot theo input order.

**13.** Completion service có tự shutdown executor không?  
**Đáp:** Không. Lifecycle thuộc executor owner; phải quản lý shutdown/cleanup riêng.

**14.** ECS có làm các callable cùng sửa một list thường trở nên thread-safe không?  
**Đáp:** Không. ECS chỉ thu completion; state chia sẻ vẫn cần ownership, synchronization hoặc immutable design.

**15.** Vì sao một pool chỉ có một worker có thể deadlock khi task A đợi Future của task B vừa submit vào chính pool?  
**Đáp:** Worker bị A chiếm trong khi B chưa có worker chạy; ECS không giải quyết dependency starvation ấy.

**16.** Khi nào chọn ECS thay vì lấy Future trực tiếp?  
**Đáp:** Khi cần **thu và xử lý kết quả theo từng task hoàn tất**, không bị khóa vào thứ tự submit.

**Ghi nhớ:** `ExecutorCompletionService` tổ chức **fan-out task qua Executor** và **fan-in completed Future qua completion queue**. `take()/poll()` giúp consumer xử lý task hoàn tất trước, còn `Future.get()` cho value hoặc exception. Correctness vẫn đòi hỏi đếm accepted submissions, deadline/cancel/cleanup, thread-safety của state và giới hạn số in-flight; completion service không thay thế executor lifecycle, transaction hay backpressure policy.