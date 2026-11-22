# Phân biệt invoke(), execute() và submit() trong Fork/Join Framework

Khi dùng `ForkJoinPool`, ba phương thức **`invoke()`**, **`execute()`** và **`submit()`** đều có thể đưa một tác vụ vào pool, nhưng **khác nhau ở việc thread gọi có chờ hay không, kiểu trả về và cách lấy kết quả/lỗi**. Nếu nhầm chúng, ứng dụng có thể chờ ngoài ý muốn, bỏ qua exception hoặc không có cơ chế xác nhận task đã hoàn tất.

Nội dung trọng tâm là API của **`java.util.concurrent.ForkJoinPool`**, với `ForkJoinTask`, `RecursiveTask` và `RecursiveAction` theo Java 17+. Đây là kiến thức Java concurrency nói chung, không phụ thuộc framework khác.

**Nhớ nhanh:**

- **`pool.invoke(task)`**: gửi task và **chờ task hoàn tất**, sau đó **trả về kết quả `V`** hoặc truyền lỗi theo quy tắc Fork/Join.
- **`pool.execute(task)`**: gửi task **không chờ**, phương thức trả về **`void`**; muốn biết đã xong thì cần giữ handle của task hoặc cơ chế hoàn thành khác.
- **`pool.submit(task)`**: gửi task **không chờ**, nhưng **trả về `ForkJoinTask<V>`**, có thể gọi `join()`, `get()`, `get(timeout)`, `isDone()` và `cancel()`.

`invoke()` ở đây là **`ForkJoinPool.invoke(ForkJoinTask)`**. Đừng nhầm với `ForkJoinTask.invoke()` hay `ExecutorService.invokeAll(Collection)`: tên gần giống nhưng cách gọi, đối tượng nhận và ý nghĩa khác nhau.

## 1. So sánh theo hợp đồng API

| Tiêu chí | `pool.invoke(task)` | `pool.execute(task)` | `pool.submit(task)` |
|---|---|---|---|
| Hành vi khi gọi | **Chờ** task hoàn tất rồi mới trả về. | Gửi để chạy; **không chờ** hoàn tất. | Gửi để chạy; **không chờ** hoàn tất. |
| Giá trị trả về | `V` của `ForkJoinTask<V>`. | `void`. | `ForkJoinTask<V>` với overload nhận `ForkJoinTask<V>`. |
| Tác vụ `RecursiveAction` | Kết quả dạng `Void` (thường `null`). | Không nhận result từ lời execute. | Có handle có thể chờ để xác nhận xong. |
| Cách lấy kết quả | Có ngay sau invoke trả về thành công. | Phải giữ chính task hoặc dùng cơ chế khác. | Gọi `join()`/`get()` trên handle khi cần. |
| Chờ có timeout | `invoke()` không có overload timeout. | `execute()` không chờ; handle có thể được đợi riêng. | `handle.get(timeout, unit)` có giới hạn đợi. |
| Lỗi tính toán | Có thể ném unchecked exception/Error theo ngữ nghĩa task. | Không tự trả lỗi task về thread gọi qua lời `execute()` bất đồng bộ. | Lỗi có thể được quan sát qua `join()` hoặc `get()`. |
| Tình huống hợp lý | Caller cần **kết quả ngay** để đi tiếp. | Fire-and-dispatch với quy tắc theo dõi hoàn tất/lỗi được thiết kế riêng. | Caller muốn tiếp tục làm việc khác rồi **đợi/kiểm tra/hủy** task. |

Với `execute()` và `submit()`, “không chờ” nghĩa là **không chờ task tính xong**; lời gọi vẫn phải thực hiện công việc tiếp nhận/lập lịch và có thể ném lỗi nộp task (ví dụ executor không chấp nhận công việc). Đừng suy rằng submit là một thao tác không tốn thời gian hoặc luôn thành công.

## 2. Tại sao ForkJoinTask được dùng thay Runnable thông thường?

`ForkJoinTask<V>` là đối tượng đại diện cho công việc Fork/Join, có cơ chế hoàn tất và lấy kết quả. Hai lớp thường dùng:

- `RecursiveTask<V>`: ghi đè `protected V compute()` để tính và trả **kết quả V**.
- `RecursiveAction`: ghi đè `protected void compute()` cho công việc **không có giá trị kết quả**.

Các task này được thiết kế cho bài toán chia để trị, trong đó một nhánh có thể `fork()` các nhánh con, tính nhánh khác rồi `join()` để gộp kết quả. `ForkJoinPool` sử dụng worker và **work-stealing** để cân bằng các nhánh; nó **không tạo một Thread mới cho mỗi task**.

Sơ đồ:

```text
                 Caller thread
                      |
             +--------+--------+
             |        |        |
           invoke   execute   submit
             |        |        |
             v        v        v
           WAIT     return   return handle
             |        |        |
             v        |        +--> handle.get()/join() nếu cần
           result    |              
                      |
                ForkJoinPool
                      |
              work-stealing workers
                      |
               RecursiveTask/Action
```

Không nên áp dụng cùng một sơ đồ “fork mỗi việc nhỏ” cho mọi bài toán. Chi phí tạo task, chia nhánh, quản lý deque và join có thể lớn hơn phép tính nếu việc quá nhỏ. Cần có **base case/threshold** khi triển khai `compute()` đệ quy.

## 3. invoke(): lời gọi đồng bộ trả về kết quả

Chữ ký cốt lõi:

```java
public <T> T invoke(ForkJoinTask<T> task)
```

Đây là **chữ ký API minh họa**, không phải một method cần tự định nghĩa. Ví dụ:

```java
long total = pool.invoke(new SumTask(data, 0, data.length));
```

`pool.invoke(...)` **không trả về trước khi root task hoàn tất bình thường**, nên caller có thể dùng tổng ngay ở dòng kế tiếp. Nếu task ném unchecked exception/Error, việc chờ/gọi theo API Fork/Join có thể truyền lỗi lên caller; nó không biến lỗi thành một giá trị tổng hợp mặc định.

Đặc điểm:

1. Dễ viết khi cần kết quả trước bước tiếp theo, chẳng hạn tổng hoặc thống kê của một mảng.
2. Caller phải chấp nhận **bị chặn** đến khi task kết thúc. Nếu task không hoàn tất, lời invoke cũng không có timeout tích hợp.
3. Có thể dùng `RecursiveTask<V>` trả `V`, hoặc `RecursiveAction` với `Void`.
4. Không cần tự gọi `join()` trên **root** để lấy kết quả sau `pool.invoke(root)`: invoke đã chờ root.
5. Các nhánh bên trong root vẫn phải được phối hợp đúng: nếu kết quả phụ thuộc child, root cần `join()` hoặc `invokeAll()` cho chúng.

### Ví dụ 1: ForkJoinPool.invoke() tính tổng

Tạo file **`ForkJoinInvokeDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinInvokeDemo {
    static final class SumTask extends RecursiveTask<Integer> {
        private final int from;
        private final int to;

        SumTask(int from, int to) {
            this.from = from;
            this.to = to;
        }

        @Override
        protected Integer compute() {
            if (to - from <= 10) {
                int sum = 0;
                for (int i = from; i < to; i++) {
                    sum += i;
                }
                return sum;
            }

            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(from, mid);
            SumTask right = new SumTask(mid, to);

            left.fork();
            int rightSum = right.compute();
            int leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            SumTask root = new SumTask(1, 101);
            int result = pool.invoke(root);

            System.out.println("Sum: " + result);
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinInvokeDemo.java
java ForkJoinInvokeDemo
```

Kết quả:

```text
Sum: 5050
Root done: true
```

**Giải thích:** đoạn `[1,101)` chứa các số 1 đến 100, có tổng `100 * 101 / 2 = 5050`. Mỗi nhánh lớn hơn 10 số được chia đôi. `left.fork()` tạo cơ hội thực thi song song, worker hiện tại tính `right`, rồi `left.join()` đưa kết quả left về nút cha. `pool.invoke(root)` chỉ trở về sau khi cả cây đã gộp xong; `root.isDone()` bằng true ở thời điểm in. Thứ tự chạy hai nhánh có thể khác nhau, nhưng stdout không phụ thuộc lịch chạy.

**Tránh hiểu nhầm:** `invoke()` không có nghĩa “chỉ chạy trong thread caller”. Việc thực thi task thuộc cơ chế của ForkJoinPool, và các worker có thể giúp nhau xử lý cây tác vụ. Ngược lại, việc caller đợi đồng bộ cũng không đảm bảo pool đã dùng nhiều worker hơn một.

## 4. execute(): gửi tác vụ không chờ và không trả handle

Dạng overload cho ForkJoinTask:

```java
public void execute(ForkJoinTask<?> task)
```

Đây là chữ ký minh họa. Lời gọi:

```java
pool.execute(task);
```

**trả về `void`**, vì vậy không có `Future` mới được trả từ lời gọi này. Tuy nhiên, nếu **caller đã giữ reference tới `task`** và đó là một `ForkJoinTask`, chính task đã có API `join()`, `get()`, `isDone()`, `cancel()`. “Execute không trả handle” **không có nghĩa** bạn không thể theo dõi task nếu đã giữ object task trước khi execute.

Pool còn có overload `execute(Runnable)` do interface Executor. Với một lambda `Runnable`, caller không nhận `Future` từ `execute()`; nếu cần nhận handle từ một `Runnable` bình thường, `submit()` thường phù hợp hơn.

### Ví dụ 2: execute() không chờ, task.join() mới xác nhận hoàn tất

Dùng hai latch để tạo một tác vụ chắc chắn **đang chạy nhưng chưa thể kết thúc** tại lúc main quan sát. Vì vậy ví dụ không dựa vào `Thread.sleep()` hay may mắn của scheduler.

Tạo file **`ForkJoinExecuteDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

public class ForkJoinExecuteDemo {
    static final class WaitingAction extends RecursiveAction {
        private final CountDownLatch started;
        private final CountDownLatch release;

        WaitingAction(CountDownLatch started, CountDownLatch release) {
            this.started = started;
            this.release = release;
        }

        @Override
        protected void compute() {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted while waiting", e);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        WaitingAction task = new WaitingAction(started, release);

        try {
            pool.execute(task); // Không chờ task hoàn tất.
            started.await();

            System.out.println("Before release, done: " + task.isDone());
            release.countDown();

            task.join(); // Đây mới là bước chờ hoàn tất.
            System.out.println("After join, done: " + task.isDone());
        } finally {
            release.countDown();
            pool.shutdown();
        }

        System.out.println("Pool terminated: "
                + pool.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

```bash
javac ForkJoinExecuteDemo.java
java ForkJoinExecuteDemo
```

Kết quả trong lần chạy bình thường, không bị external interrupt:

```text
Before release, done: false
After join, done: true
Pool terminated: true
```

**Vì sao?**

1. `pool.execute(task)` nộp task rồi trả về mà không đợi nó hoàn tất.
2. `started.await()` buộc main đợi tới khi `compute()` đã bắt đầu chạy.
3. `compute()` phải chờ `release` mới có thể trở về; main chưa mở latch, nên `task.isDone()` chắc chắn là **false** trước release.
4. Main mở latch. `task.join()` chờ compute hoàn tất, sau đó `task.isDone()` là **true**.
5. `shutdown()` dừng nhận task mới; `awaitTermination()` xác nhận pool riêng đã ngừng trong thời hạn năm giây của ví dụ.

Đây là mô hình học về khác biệt **dispatch** và **completion**, không phải lời khuyên nên block worker Fork/Join bằng latch trong ứng dụng sản xuất. ForkJoinPool ưu tiên công việc tính toán; các lời chờ chặn dài có thể làm giảm số worker hữu ích.

## 5. submit(): gửi không chờ nhưng trả handle để quản lý kết quả

Với overload nhận ForkJoinTask:

```java
public <T> ForkJoinTask<T> submit(ForkJoinTask<T> task)
```

Đây là chữ ký minh họa. Ví dụ:

```java
ForkJoinTask<Integer> handle = pool.submit(rootTask);
```

Caller **không bị chặn chờ task xong tại lời submit**, và có thể làm việc khác. Khi cần kết quả, có thể gọi:

```java
Integer result = handle.join();
```

hoặc:

```java
Integer result = handle.get();
```

Hai trích đoạn cần object task/handle khai báo trước và, với `get()`, checked exceptions phù hợp.

`ForkJoinPool.submit` còn có overload cho **`Callable<T>`** và **`Runnable`**. Với `Callable<T>`, handle có kết quả kiểu `T`; với `Runnable` thuần không có result, một handle dạng `ForkJoinTask<?>` có thể trả `null` ở `get()` sau khi hoàn tất. Có overload `submit(Runnable, T result)` để gắn một kết quả định trước theo hợp đồng.

**Lưu ý overload:** Nếu truyền một object `RecursiveTask<V>`, compiler chọn overload nhận `ForkJoinTask<V>` cụ thể. Nếu truyền `Callable<V>` hoặc lambda `Runnable`, sẽ chọn overload tương ứng theo kiểu tham số. Trường hợp lambda có trả giá trị nên cần kiểu rõ (`Callable`) để tránh nhầm khi dùng nhiều overload.

### Ví dụ 3: submit() với RecursiveTask, Callable và Runnable

Tạo file **`ForkJoinSubmitDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinSubmitDemo {
    static final class NumberTask extends RecursiveTask<Integer> {
        @Override
        protected Integer compute() {
            return 6 * 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        AtomicInteger ran = new AtomicInteger();

        try {
            ForkJoinTask<Integer> a = pool.submit(new NumberTask());
            ForkJoinTask<String> b = pool.submit(
                    (Callable<String>) () -> "callable-result"
            );
            ForkJoinTask<?> c = pool.submit(
                    (Runnable) ran::incrementAndGet
            );

            System.out.println("RecursiveTask: " + a.get());
            System.out.println("Callable: " + b.get());
            System.out.println("Runnable get: " + c.get());
            System.out.println("Runnable executed: " + ran.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinSubmitDemo.java
java ForkJoinSubmitDemo
```

Kết quả:

```text
RecursiveTask: 42
Callable: callable-result
Runnable get: null
Runnable executed: 1
```

**Điểm cần hiểu:**

- `a` là `ForkJoinTask<Integer>`, `a.get()` trả 42 sau khi task hoàn tất.
- `b` minh họa overload nhận `Callable<String>` và trả kết quả dạng String.
- `c` minh họa overload nhận `Runnable`. Runnable không trả giá trị nghiệp vụ, nhưng `c.get()` chờ nó hoàn tất. Sau đó `ran.get() == 1` vì method reference chỉ chạy một lần.
- Dù ba task có thể chạy theo thứ tự bất kỳ, `get()` của từng handle bảo đảm câu lệnh in tương ứng chỉ tiếp tục khi task đã hoàn tất. Vì in nằm trong main theo thứ tự cố định, **stdout xác định**.
- Dùng `submit` không tự đồng nghĩa “tác vụ chạy trên thread khác ngay lập tức”; nó chỉ cung cấp một **handle theo dõi tác vụ** và cơ chế để pool thực hiện theo lịch.

**Về Runnable method reference:** `ran::incrementAndGet` có giá trị trả về nhưng được dùng trong ngữ cảnh `Runnable` có method `void run()`; kết quả tăng của atomic counter bị bỏ. `get()` của handle Runnable vẫn trả `null`, không phải giá trị 1.

## 6. Các phương thức chờ trên ForkJoinTask: join(), get(), invoke()

Một điểm rất hay nhầm là cùng chữ `invoke` xuất hiện ở **pool** và ở **task**.

| Cách gọi | Đối tượng nhận | Ý nghĩa |
|---|---|---|
| `pool.invoke(task)` | `ForkJoinPool` | Gửi root task vào pool và **chờ kết quả**. |
| `task.invoke()` | `ForkJoinTask` | Bắt đầu thực hiện **chính task đó** và chờ kết quả; không phải cú pháp thay thế trực tiếp cho việc gửi root vào **pool cụ thể**. |
| `task.fork()` | `ForkJoinTask` | Lập lịch task bất đồng bộ trong ngữ cảnh Fork/Join hiện hành. |
| `task.join()` | `ForkJoinTask` | Chờ **task đã được thực hiện/lập lịch** hoàn tất và trả kết quả; bản thân join không nên được coi là lời gửi root task chưa được lập lịch vào pool. |
| `task.get()` | `ForkJoinTask` / `Future` | Chờ hoàn tất và trả kết quả, nhưng có checked exception. |
| `task.get(timeout, unit)` | `ForkJoinTask` / `Future` | Chờ có giới hạn; có thể ném `TimeoutException`. |

Trong `RecursiveTask.compute()`, mẫu thông thường là:

```java
left.fork();
Result rightResult = right.compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
```

Đây là trích đoạn minh họa; `left`/`right` là task, `Result`/`combine` được giả định đã khai báo. **`fork()` và `join()` là cơ chế phối hợp nhánh con**, trong khi `pool.invoke/execute/submit` thường là lựa chọn tại ranh giới code ứng dụng nộp **root task**.

Nếu đang ở ngoài ForkJoinPool và muốn root chạy **trên một pool riêng**, hãy gọi `pool.invoke(root)` hoặc `pool.submit(root)`. Gọi `root.invoke()` trực tiếp không tương đương chọn pool riêng đó.

## 7. join() và get(): khác nhau ở exception và interrupt

`ForkJoinTask.join()` và `ForkJoinTask.get()` đều có thể chờ task hoàn tất, nhưng hướng xử lý exception khác nhau:

- **`join()`:** trả kết quả hoặc ném unchecked exception/Error (có thể được framework truyền lại từ task); **không khai báo** `InterruptedException` hay `ExecutionException`.
- **`get()`:** theo hợp đồng `Future`, có thể ném `InterruptedException` và `ExecutionException`; nếu Future đã hủy sẽ ném `CancellationException`.
- **`get(timeout, unit)`:** thêm `TimeoutException` để caller không phải chờ vô hạn trong một lần đợi.
- **`invoke()`:** dạng đồng bộ có thể truyền unchecked exception của task, không tự cung cấp tham số timeout.

Bảng:

| Kịch bản | `join()` | `get()` |
|---|---|---|
| Task thành công | Trả `V`. | Trả `V`. |
| Task ném unchecked exception | Truyền unchecked exception theo contract của ForkJoinTask. | Thường ném `ExecutionException`, lấy lỗi gốc bằng `getCause()`. |
| Task bị hủy | `CancellationException`. | `CancellationException`. |
| Thread đang chờ bị interrupt | Không khai báo/không xử lý theo kiểu `InterruptedException` của get. | `InterruptedException` trong đường đợi có hỗ trợ interrupt. |
| Caller muốn timeout | Không có overload `join(timeout)`. | `get(timeout, unit)` cho phép chờ có giới hạn. |

**Không dùng `join()` trên các task không có đường hoàn tất** rồi kỳ vọng nó tự timeout. Nếu cần ngân sách thời gian, dùng timed `get` ở vị trí thích hợp và thiết kế cancellation hợp tác.

Các API `ForkJoinTask` có những chi tiết riêng về exception, cancellation và blocking. Đừng áp dụng máy móc semantics của `Thread.join()` hay `CompletableFuture.join()` cho chúng chỉ vì cùng tên method.

## 8. Ví dụ 4: submit() + get(timeout) cho caller không chờ vô hạn

`submit()` thường hữu ích khi caller muốn nộp root task, thực hiện việc khác, rồi **chờ kết quả trong thời hạn**. Để chứng minh timeout mà không dựa vào `sleep()`, ví dụ dùng latch chặn completion cho đến khi caller chủ động mở.

Tạo file **`ForkJoinTimedGetDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ForkJoinTimedGetDemo {
    static final class DelayedTask extends RecursiveTask<Integer> {
        private final CountDownLatch started;
        private final CountDownLatch release;

        DelayedTask(CountDownLatch started, CountDownLatch release) {
            this.started = started;
            this.release = release;
        }

        @Override
        protected Integer compute() {
            started.countDown();
            try {
                release.await();
                return 99;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Task interrupted", e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ForkJoinTask<Integer> handle =
                    pool.submit(new DelayedTask(started, release));
            started.await();

            try {
                handle.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("Timed out");
            }

            System.out.println("Cancelled by timeout: "
                    + handle.isCancelled());

            release.countDown();

            System.out.println("Result after release: "
                    + handle.get(5, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            pool.shutdown();
        }

        System.out.println("Pool terminated: "
                + pool.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

```bash
javac ForkJoinTimedGetDemo.java
java ForkJoinTimedGetDemo
```

Kết quả trong lần chạy bình thường:

```text
Timed out
Cancelled by timeout: false
Result after release: 99
Pool terminated: true
```

**Giải thích:** `started.await()` xác nhận root task đã vào `compute()`, nhưng nó chưa thể hoàn thành khi `release` còn đóng. Vì vậy lần `get(20, MILLISECONDS)` đầu ném `TimeoutException`. Timeout **không tự cancel** `ForkJoinTask`; `isCancelled()` vẫn false. Sau khi release mở, task hoàn thành và `get` tiếp theo nhận 99. Cuối cùng main shutdown pool riêng và chờ termination.

Đây là ví dụ giáo dục minh họa API timeout, **không phải lời khuyên chèn blocking wait dài vào compute của Fork/Join production**. ForkJoinPool vốn thiên về các nhánh tính toán ngắn và cơ chế work-stealing. Nếu chủ yếu chờ I/O/blocking, cần đánh giá executor hoặc API khác.

## 9. Vấn đề với lỗi bất đồng bộ: execute() có thể làm caller không biết task thất bại

`execute()` trả về `void`, vì vậy code:

```java
pool.execute(new FailingTask());
System.out.println("Submitted");
```

**không chứng minh FailingTask đã hoàn tất thành công**. Đoạn này chỉ minh họa: `FailingTask` cần là một ForkJoinTask được định nghĩa. Nếu lỗi xảy ra sau lời execute, lỗi không tự trở thành exception đồng bộ ở thread caller tại dòng `execute`.

Nếu ứng dụng cần xác nhận:

- Giữ task: `ForkJoinTask<?> task = new FailingTask(); pool.execute(task); task.join();` rồi xử lý lỗi unchecked.
- Dùng `pool.submit(task)` và quan sát `handle.get()`, `get(timeout)` hoặc `join()`.
- Thiết kế kênh báo lỗi/metrics chuyên biệt khi đúng nghĩa “fire-and-forget”; không im lặng mất lỗi.

Với `submit()` của các executor, ngoại lệ có thể được giữ trong Future thay vì xuất hiện tức thời trên caller. **Đừng bỏ handle nếu nhiệm vụ bắt buộc phải thành công hoặc cần audit**. Việc executor vẫn sống hay `submit()` trả về bình thường chỉ có nghĩa yêu cầu nộp task đã được tiếp nhận, không bảo đảm kết quả nghiệp vụ.

## 10. Tương tác với RecursiveAction và kết quả Void

`RecursiveAction` là kiểu tác vụ không trả giá trị. Do đó:

```java
ForkJoinTask<Void> task = new MyRecursiveAction();
Void result = pool.invoke(task);
```

Đây là trích đoạn minh họa; `MyRecursiveAction` cần mở rộng `RecursiveAction` và định nghĩa `compute()`. `result` bình thường là `null`: điều hữu ích của invoke lúc này là **đợi action hoàn tất**, không phải nhận một object kết quả.

Có thể thay bằng:

```java
pool.execute(task);
// Làm việc khác...
task.join(); // Chờ action nếu cần xác nhận đã xong.
```

hoặc:

```java
ForkJoinTask<Void> handle = pool.submit(task);
handle.get(); // Chờ và xử lý exception theo Future.
```

Những trích đoạn đều yêu cầu task đã có và khai báo/handle checked exceptions thích hợp. Nếu mục tiêu là biến đổi mảng theo các vùng độc lập, `RecursiveAction` tiện khi dữ liệu đã được chia vùng ghi rõ và caller chỉ cần biết cây tác vụ đã kết thúc. Nếu cần tính một giá trị tổng hợp, `RecursiveTask<V>` thường thể hiện kết quả trực tiếp hơn.

Không nhầm `void` của **`pool.execute`** (lời gọi không trả handle) với **`Void`** của `RecursiveAction` (kiểu kết quả của một task, có thể lấy `null` khi completion).

## 11. Khác nhau giữa pool.invoke() và ExecutorService.invokeAll()

`ForkJoinPool` triển khai `ExecutorService`, nên còn có các API của interface này. **`invokeAll(Collection<? extends Callable<T>> tasks)`** không phải một biến thể “số nhiều” của `pool.invoke(ForkJoinTask<T>)` theo nghĩa đơn giản.

- `pool.invoke(root)`: nhận **một `ForkJoinTask<T>` root**, chờ root hoàn tất rồi trả **`T`**.
- `executor.invokeAll(callables)`: nhận **một collection các Callable**, chờ các Future đạt trạng thái hoàn tất theo hợp đồng, rồi trả **danh sách `Future<T>`** theo thứ tự collection input. Cần gọi get trên từng Future để lấy kết quả hoặc lỗi.
- `invokeAll(callables, timeout, unit)`: có một thời hạn cho nhóm theo API; có thể cancel các task chưa hoàn tất khi hết hạn theo contract.

Ví dụ chữ ký giản lược:

```java
T result = pool.invoke(rootTask);

List<Future<T>> handles = pool.invokeAll(tasks);
```

Đoạn này là trích đoạn cần các biến/generic imports phù hợp; `tasks` là collection Callable chứ không phải hai ForkJoinTask child thông thường. Trong `RecursiveTask.compute()`, còn có **`ForkJoinTask.invokeAll(left, right)`** để phối hợp **những child ForkJoinTask**. Ba API có chữ `invoke` trong tên nhưng khác đối tượng và hợp đồng.

## 12. Memory visibility: khi nào có thể dùng kết quả?

Theo các bảo đảm memory consistency của Java concurrency, các hành động trước khi submit một task cho executor có quan hệ **happens-before** với hành động trong task; các hành động thực hiện trong tính toán bất đồng bộ có quan hệ **happens-before** với hành động của thread khác sau khi nhận kết quả qua `Future.get()` tương ứng.

Các primitive hoàn thành của `ForkJoinTask` (`join()`, `invoke()`) cung cấp cơ chế phối hợp để caller hoặc parent sử dụng kết quả hoàn tất của child theo hợp đồng Fork/Join.

Từ đó:

- Sau `pool.invoke(root)` thành công, caller có thể dùng giá trị trả về của root.
- Sau `pool.submit(task)` rồi `handle.get()` thành công, caller có mốc hoàn tất và công bố kết quả theo hợp đồng Future.
- Sau `pool.execute(task)` trả về, **chưa** có mốc xác nhận task hoàn thành. Nếu cần đọc state do task cập nhật, phải chờ task `join()`/`get()` hoặc dùng một cơ chế đồng bộ khác.
- `isDone()` là phép quan sát trạng thái task, không thay thế việc xử lý kết quả, lỗi và mọi shared state không được đồng bộ đúng.

Cơ chế đồng bộ completion **không** biến mọi shared mutable object thành thread-safe. Nếu nhiều ForkJoinTask đồng thời sửa một `ArrayList`, một counter bình thường hoặc cùng index mảng, vẫn có thể có data race. Tránh chia sẻ accumulator mutable; ưu tiên kết quả cục bộ qua `RecursiveTask` hoặc phân vùng dữ liệu rõ ràng trong `RecursiveAction`.

## 13. Timeout, cancellation và hoàn tất thực tế

Không phương thức nào tự giải quyết mọi vấn đề vòng đời:

- `pool.invoke(task)` có thể chờ lâu nếu task không hoàn tất; không có tham số timeout.
- `pool.execute(task)` trả về ngay nhưng **task vẫn có thể chạy rất lâu**; không chờ không nghĩa tác vụ không cần owner.
- `pool.submit(task)` trả handle; dùng `handle.get(timeout, unit)` để caller chờ có giới hạn.
- Khi `get(timeout)` ném `TimeoutException`, **task không tự bị hủy**.
- Với `ForkJoinTask.cancel(true)`, tham số `mayInterruptIfRunning` **không có tác dụng trong implementation mặc định của ForkJoinTask**: interrupt không được dùng để điều khiển cancellation theo cách nhiều người kỳ vọng từ `FutureTask`. Một task đang chạy có thể vẫn tiếp tục thực thi.
- `isDone()` hay `isCancelled()` không tự chứng minh side effects ở hệ thống ngoài đã được rollback hoặc cleanup tài nguyên đã hoàn tất.
- Task đang thực hiện I/O chặn hoặc không kiểm tra yêu cầu hủy cần giao thức xử lý riêng, timeout ngay tại API I/O và chính sách cleanup thích hợp.

**Không nhầm `ForkJoinTask.cancel(true)` với `FutureTask.cancel(true)` dùng trong một số executor khác.** Cùng interface Future, nhưng khả năng interrupt worker cụ thể thuộc hợp đồng implementation. Nếu nhiệm vụ bắt buộc phải ngừng ở một deadline, cần thiết kế cooperative cancellation ngay trong công việc, chứ không chỉ dựa vào dấu canceled của handle.

## 14. Shutdown, common pool và quyền sở hữu

Khi tạo `new ForkJoinPool(parallelism)`, ứng dụng sở hữu pool riêng, nên quản lý vòng đời:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    // invoke / execute / submit các task...
} finally {
    pool.shutdown();
}
```

Đây là trích đoạn minh họa. `shutdown()` ngừng nhận tác vụ mới nhưng không chứng minh toàn bộ task đã hoàn tất. Nếu cần xác nhận, gọi `awaitTermination(timeout, unit)` ở vị trí phù hợp và kiểm tra boolean trả về. Với task đã được gửi nhưng chưa chờ, shutdown bình thường vẫn cho các task được chấp nhận hoàn thành theo contract; tuy nhiên caller không nên coi “đã gọi shutdown” là kết quả thành công của từng task.

`ForkJoinPool.commonPool()` là pool dùng chung trong JVM. Không tự ý shutdown nó như tài nguyên thuộc sở hữu một method: `shutdown()` trên common pool không có cùng hiệu ứng chấm dứt như pool riêng. Nếu cần isolation, parallelism và lifecycle riêng, tạo/giữ một dedicated pool theo vòng đời thành phần, **không tạo pool mới cho từng nhánh**.

Đối với code thư viện, lựa chọn pool cần nhất quán: gửi root tới pool cụ thể, các child fork theo ngữ cảnh thực thi trong pool đó. Không lẫn tùy tiện root task đã chạy với một lời submit khác; `ForkJoinTask` thông thường được thiết kế cho một lần thực thi, **không reuse một instance đã completed làm task mới** nếu không có cơ chế reset được hiểu và kiểm soát rõ.

## 15. Khi nào nên dùng phương thức nào?

| Nhu cầu của caller | Chọn | Lý do |
|---|---|---|
| Cần tổng/min/max trước bước kế tiếp, caller được phép chờ. | `pool.invoke(root)`. | Trả giá trị trực tiếp sau khi root hoàn tất. |
| Nộp công việc rồi tiếp tục xử lý khác, nhưng sau này cần kết quả. | `pool.submit(root)`. | Trả handle theo dõi, lấy kết quả khi cần. |
| Muốn chờ kết quả có deadline. | `pool.submit(root)` + `get(timeout)`. | Giới hạn lần đợi của caller. |
| Fire-and-dispatch và ứng dụng đã có kênh theo dõi hoàn tất/lỗi riêng. | `pool.execute(task)`. | Không chờ và không trả handle mới, API gọn. |
| Có sẵn `ForkJoinTask`, vẫn muốn gửi không chờ và chờ sau. | `pool.execute(task)` rồi `task.join()`. | Handle là chính task đã giữ. |
| Có nhiều Callable độc lập và cần đợi cả nhóm. | `ExecutorService.invokeAll(...)`. | Trả danh sách Future; phân biệt với root ForkJoinTask. |
| Trong `compute()`, chia hai nhánh và gộp kết quả. | `left.fork(); right.compute(); left.join();`. | Phối hợp các child task, không nộp lại root vào pool. |

Không có lựa chọn nào “luôn nhanh nhất”. Về mặt tính toán, ba lời gọi có thể dẫn tới cùng công việc được thực hiện; sự khác nhau nổi bật nằm ở **quyền điều khiển của caller và cơ chế quan sát completion**.

## 16. Lỗi thường gặp khi dùng invoke/execute/submit

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Dùng `pool.invoke(root)` trên đường xử lý không được block. | Caller chờ đến khi root xong, có thể tăng latency. | Submit và xử lý kết quả bất đồng bộ/có deadline. |
| Nghĩ `execute()` đồng nghĩa task đã xong khi lời gọi trả về. | Đọc dữ liệu đang cập nhật, kết quả chưa hoàn tất. | Chờ task `join()/get()` hoặc tín hiệu completion. |
| Dùng `submit()` rồi bỏ handle của tác vụ bắt buộc thành công. | Lỗi task có thể không được quan sát từ caller. | Giữ Future và có đường xử lý lỗi/hoàn tất. |
| Dùng `task.join()` như `Thread.join()`. | Hiểu sai đối tượng chờ và exception contract. | Phân biệt task completion với thread termination. |
| Dùng `task.invoke()` ngoài pool rồi nghĩ nó chạy trên dedicated pool. | Không chắc tác vụ vào pool mong muốn. | Gọi `pool.invoke(root)`/ `pool.submit(root)` với pool cụ thể. |
| Fork child rồi join ngay trước khi làm nhánh còn lại. | Hạn chế cơ hội song song. | Fork một nhánh, tự compute nhánh khác, rồi join. |
| Bắt `ExecutionException` quanh `join()` mà không hiểu chữ ký. | Sai handling/biên dịch hoặc bỏ sót unchecked lỗi. | `get()` có checked exception; `join()` có unchecked path. |
| Cho rằng timeout `get` tự hủy task. | Worker tiếp tục chạy sau caller timeout. | Quyết định cancel/lifecycle riêng. |
| Cho rằng `ForkJoinTask.cancel(true)` chắc chắn interrupt worker. | Worker có thể tiếp tục, làm side effect ngoài ý muốn. | Cooperative cancellation theo contract thực. |
| Dùng chung một mutable accumulator cho các RecursiveTask. | Data race và mất kết quả. | Trả kết quả cục bộ hoặc phân vùng ghi không trùng. |
| Tạo một `new ForkJoinPool()` trong mỗi compute con. | Nổ số pool/thread, chi phí cao. | Dùng cùng pool và fork child. |
| Dùng Fork/Join cho phần lớn blocking I/O. | Worker bị chặn, giảm throughput hoặc deadlock. | Cân nhắc executor cho I/O, timeout và managed blocking khi thích hợp. |
| Quên shutdown pool riêng. | Tài nguyên pool không được quản lý rõ. | Owner shutdown và chờ termination có giới hạn. |
| Coi `isDone()` là chắc chắn task thành công. | Done bao gồm failed/cancelled. | Lấy kết quả hoặc kiểm tra trạng thái lỗi/hủy. |

## 17. Vận hành: CPU-bound, blocking và work-stealing

ForkJoinPool tối ưu cho các công việc **CPU-bound phân nhánh**, đặc biệt khi một số worker có thể đánh cắp task còn chờ từ worker khác. Những bài toán tính tổng, đệ quy trên cây và chia mảng hợp lý thường phù hợp nếu leaf đủ lớn.

Lựa chọn invoke/execute/submit **không thay đổi bản chất bài toán**: nếu task quá nhỏ hoặc xử lý I/O chặn, cả ba cách nộp đều có thể cho hiệu năng kém. Các blocking call dài như socket, database hoặc `CountDownLatch.await()` trong worker làm giảm khả năng xử lý task khác. Framework cung cấp `ForkJoinPool.managedBlock(ManagedBlocker)` cho một số tình huống cần báo với pool về việc block, nhưng API này **không biến I/O thành non-blocking và không tự ngăn deadlock**.

Đối với công việc tính toán dài, có thể cân nhắc `parallelStream()` hoặc các API mức cao hơn khi thích hợp, nhưng cũng cần chú ý shared mutable state và quản lý tài nguyên. Với tác vụ cần một lịch deadline, timeout của `get` chỉ giới hạn caller; worker cũng phải có chính sách kiểm tra deadline và hủy hợp tác.

## 18. Checklist trước khi dùng trong dự án

1. **Caller được phép block?** Nếu không, đừng gọi `pool.invoke()` trên thread nhạy latency.
2. **Có cần giá trị trả về?** Nếu có và cần ngay, invoke; nếu cần sau, submit và giữ handle.
3. **Có cần quan sát lỗi/hủy?** Luôn giữ handle hoặc kênh hoàn thành phù hợp, kể cả khi dùng execute.
4. **Có deadline?** Dùng `get(timeout)` và thiết kế cả cancellation/cleanup của worker.
5. **Task có thực sự là bài toán chia để trị?** Thiết kế threshold và base case, tránh fork quá nhỏ.
6. **Các nhánh có độc lập?** Trả kết quả cục bộ, giữ dữ liệu immutable hoặc ghi các vùng riêng.
7. **Join các child đúng chỗ?** Parent phải chờ mọi child mà kết quả phụ thuộc.
8. **Lỗi task được chuyển tới đâu?** Hiểu `join()` unchecked path và `get()` checked path.
9. **Pool nào sở hữu task?** Sử dụng pool được chọn rõ ràng; không nhầm `task.invoke()` trực tiếp với `pool.invoke(task)`.
10. **Có blocking I/O?** Đánh giá lại ForkJoinPool; cân nhắc executor khác và API timeout cụ thể.
11. **Quản lý lifecycle?** Dedicated pool phải được shutdown theo ownership và chờ khi thích hợp.
12. **Kiểm thử không dựa vào sleep:** dùng latch để dựng lịch chạy, kiểm tra kết quả và completion một cách xác định.

## 19. Câu hỏi tự kiểm tra

1. **`pool.invoke(root)` có trả ngay sau khi đưa task vào queue không?** Không. Nó chờ root hoàn tất rồi trả kết quả hoặc lỗi.
2. **`pool.execute(task)` trả kiểu gì?** `void`; không tự đưa handle mới về caller.
3. **`pool.submit(task)` trả kiểu gì khi task là ForkJoinTask?** `ForkJoinTask<V>` (cũng là Future).
4. **Dùng execute mà đã có reference task thì chờ bằng cách nào?** `task.join()` hoặc `task.get()` theo hợp đồng.
5. **`submit()` có chặn đến khi task hoàn tất không?** Không; nó nộp task và trả handle.
6. **`join()` có khai báo `InterruptedException` như `get()` không?** Không; exception contract khác nhau.
7. **Vì sao `get(timeout)` không đủ để hủy tác vụ chạy quá lâu?** Timeout chỉ kết thúc lần đợi của caller.
8. **`ForkJoinTask.cancel(true)` có bảo đảm interrupt worker không?** Không; implementation mặc định không dùng interrupt để điều khiển cancellation.
9. **`pool.invoke(root)` và `root.invoke()` có luôn giống nhau không?** Không; lời gọi trên root không thể coi là chọn pool riêng.
10. **`ExecutorService.invokeAll(callables)` trả gì?** Một danh sách Future cho các Callable, không phải một kết quả V của root.
11. **Sau `pool.execute(root)` có được đọc dữ liệu root đang sửa như đã hoàn thành không?** Không; cần mốc completion/synchronization.
12. **Tại sao fork một nhánh, tự compute nhánh kia rồi join?** Tăng cơ hội làm việc hữu ích song song và giảm chờ quá sớm.
13. **Vì sao `submit` không đảm bảo task chạy trên thread riêng ngay lập tức?** Pool quyết định worker/scheduling theo trạng thái và work-stealing.
14. **Khi nào dùng RecursiveTask thay RecursiveAction?** Khi nhánh phải trả giá trị để gộp, thay vì chỉ làm side effect trên vùng tách biệt.
15. **Với pool riêng, gọi `shutdown()` là đủ để chứng minh mọi task đã hoàn tất?** Không; cần quản lý completion/awaitTermination và kiểm tra kết quả.

**Ghi nhớ:** **`invoke` = nộp và chờ kết quả; `execute` = nộp không chờ, không trả handle; `submit` = nộp không chờ nhưng trả handle.** Trong cây Fork/Join, dùng `fork()`/`join()` để phối hợp nhánh con; ở ranh giới ứng dụng, chọn cách nộp root dựa trên nhu cầu chờ, lấy kết quả, xử lý lỗi và timeout.
