# Kiểm thử kết thúc, ngoại lệ và không bỏ sót công việc trong Fork/Join

## 1. Ba điều cần chứng minh khi kiểm thử Fork/Join

Trong Java, `ForkJoinPool` cùng `ForkJoinTask`, `RecursiveTask<V>` và `RecursiveAction` cho phép chia công việc thành nhánh nhỏ rồi phối hợp kết quả. Cách này có ích cho bài toán CPU-bound chia để trị, nhưng kết quả “task đã xong” có thể che ba loại lỗi khác nhau:

- **Hoàn tất:** Có chờ đúng root và mọi task con chưa? Một tác vụ có thể `fork()` child rồi trả về mà không `join()`.
- **Ngoại lệ:** Task hoàn thành bình thường, thất bại hay bị cancel? `isDone()` vẫn là `true` nếu task ném exception hoặc bị hủy.
- **Độ bao phủ:** Từng phần tử dự kiến có được xử lý **đúng một lần** không? Một tổng kết quả đúng chưa đủ chứng minh không thiếu/trùng.

Bài học dùng **Java 8 và những API Fork/Join vẫn được áp dụng trong Java hiện đại**, với mã ví dụ tương thích **JDK 17+**. Không dựa vào cách làm legacy. Trọng tâm là cách xây dựng các bất biến kiểm thử và một quy trình thu thập exception/coverage đủ tin cậy, không lệ thuộc lịch thực thi ngẫu nhiên của thread.

Các ví dụ được kiểm thử bằng JDK và có stdout xác định. Những ví dụ cố tình chặn task hoặc thiếu `join()` là **thử nghiệm minh họa lỗi**, không phải mẫu production.

## 2. Phân biệt trạng thái task và trạng thái pool

| API | Bảo đảm/ý nghĩa | Không được suy diễn |
| --- | --- | --- |
| `task.fork()` | Đưa task vào cơ chế Fork/Join để có thể chạy | Không bảo đảm task đã xong |
| `task.join()` | Chờ task hoàn thành, nhận kết quả hoặc lỗi | Không có timeout |
| `task.invoke()` | Thực thi/chờ task | Không chờ child bị bỏ quên trong code |
| `pool.invoke(root)` | Gửi task gốc và chờ result/exception của root | Không tự join tất cả descendant |
| `pool.execute(task)` | Gửi task vào pool | Không chờ task |
| `pool.submit(task)` | Gửi task và nhận handle/future | Caller phải chờ nếu cần result |
| `task.get()` | Chờ theo contract `Future` | Lỗi computation bọc bằng `ExecutionException` |
| `task.get(timeout,u)` | Giới hạn thời gian caller chờ | Timeout không tự dừng task |
| `task.isDone()` | Task kết thúc theo bất kỳ trạng thái | Bao gồm success/failure/cancelled |
| `task.isCompletedNormally()` | Task xong không exception/cancellation | Chỉ áp dụng task đó |
| `task.isCompletedAbnormally()` | Task lỗi hoặc bị hủy | Không xác định output đã rollback |
| `task.isCancelled()` | Task có trạng thái cancellation | Compute có thể chưa từng chạy |
| `task.getException()` | Throwable hoặc CancellationException khi có | Có thể null |
| `pool.shutdown()` | Bắt đầu orderly shutdown của pool riêng | Không tự chờ |
| `pool.awaitTermination(...)` | Chờ pool riêng kết thúc sau shutdown | Không bảo đảm đã submit đủ item |
| `pool.awaitQuiescence(...)` | Chờ/hỗ trợ tới trạng thái quiescent | Không phải proof business coverage |

**Kết luận quan trọng:** `isDone() == true` không tương đương `isCompletedNormally() == true`. Và `root.isCompletedNormally() == true` vẫn có thể xảy ra khi root **fork child mà không join**, vì trạng thái chỉ phản ánh computation của root.

Đối với exception:

- `join()` hoặc `invoke()` ném unchecked exception của task (có thể có stack trace bổ sung).
- `get()` ném `ExecutionException` bao quanh lỗi computation; đọc `getCause()`.
- Cancellation có `CancellationException` riêng.
- `getException()` có thể null nếu không có lỗi hoặc task chưa hoàn tất, nên đừng dereference vô điều kiện.

## 3. Bất biến phân hoạch dữ liệu để không bỏ sót

Một chiến lược dễ kiểm tra là dùng khoảng nửa mở `[lo,hi)`. Tại mỗi bước:

```text
Khoảng cha:   [lo,                  hi)
Khoảng trái:  [lo,         mid)
Khoảng phải:               [mid, hi)
```

Chọn `mid = lo + (hi-lo)/2` khi cần chia. Các điều kiện:

1. Hai khoảng con rời nhau.
2. Hợp của chúng đúng bằng khoảng cha.
3. Mỗi khoảng nhỏ hơn khoảng cha khi thực hiện chia.
4. Có điều kiện dừng `hi-lo <= THRESHOLD`.
5. Mỗi index `i` trong `[lo,hi)` được leaf xử lý **một lần**.

Các lỗi quen thuộc:

```text
left=[lo,mid); right=[mid+1,hi)   -> bỏ sót mid
left=[lo,mid+1); right=[mid,hi)   -> xử lý mid 2 lần
mid=lo; right=[lo,hi)             -> không giảm bài toán
```

Đoạn trên là ký pháp toán học, không phải Java.

**Để kiểm thử chính xác**, dùng cấu trúc theo index như `AtomicIntegerArray visits` và assert mọi `visits[i]==1`. Chỉ dùng tổng hoặc số leaf task không đủ: một phần tử bị bỏ, phần tử khác chạy hai lần vẫn có thể tạo cùng tổng đếm hoặc cùng giá trị kết quả.

## 4. Ví dụ 1 — SumCoverageDemo: tổng đúng và mỗi index đúng một lần

Tạo file **SumCoverageDemo.java**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class SumCoverageDemo {
    static class SumTask extends RecursiveTask<Long> {
        final int lo, hi;
        final AtomicIntegerArray visits;

        SumTask(int lo, int hi, AtomicIntegerArray visits) {
            this.lo = lo;
            this.hi = hi;
            this.visits = visits;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= 32) {
                long sum = 0;
                for (int i = lo; i < hi; i++) {
                    visits.incrementAndGet(i);
                    sum += i;
                }
                return sum;
            }

            int mid = lo + (hi - lo) / 2;
            SumTask left = new SumTask(lo, mid, visits);
            SumTask right = new SumTask(mid, hi, visits);

            left.fork();
            long rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    public static void main(String[] args)
            throws Exception {
        int n = 1000;
        AtomicIntegerArray visits =
            new AtomicIntegerArray(n);

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long sum = pool.invoke(
                new SumTask(0, n, visits)
            );

            int missing = 0;
            int duplicate = 0;
            for (int i = 0; i < n; i++) {
                if (visits.get(i) == 0) missing++;
                if (visits.get(i) > 1) duplicate++;
            }

            long expected = (long) n * (n - 1) / 2;
            System.out.println("sum=" + sum);
            System.out.println("expected=" + expected);
            System.out.println("missing=" + missing);
            System.out.println("duplicate=" + duplicate);
            System.out.println(
                "exactlyOnce=" +
                (missing == 0 && duplicate == 0)
            );
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "pool did not terminate"
                );
            }
        }
    }
}
```

```bash
javac SumCoverageDemo.java
java SumCoverageDemo
```

Stdout:

```text
sum=499500
expected=499500
missing=0
duplicate=0
exactlyOnce=true
```

Phép tính tổng độc lập dùng công thức `n*(n-1)/2`, ép `n` sang long trước khi nhân. Phần `AtomicIntegerArray` là instrumentation test an toàn dưới nhiều thread. `pool.invoke` chờ root, root gọi `left.join()` nên không trả về trước khi các nhánh của cấu trúc đệ quy hợp lệ hoàn tất.

Nếu quên `join()` hoặc chia sai ranh giới, ít nhất một kiểm tra **kết quả**, **missing** hoặc **duplicate** có thể thất bại. Tuy nhiên, vẫn cần test exception/cancellation vì một phép xử lý có thể bị dừng giữa chừng do lỗi.

## 5. Ví dụ 2 — RecursiveAction có side effect lên mảng kết quả

`RecursiveAction` không trả kết quả từ `compute()`. Nó có thể ghi vào những phần **không giao nhau** của một mảng, nhưng caller phải chờ đầy đủ và kiểm tra output.

Tạo file **ActionCoverageDemo.java**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class ActionCoverageDemo {
    static class Fill extends RecursiveAction {
        final int[] values;
        final AtomicIntegerArray visits;
        final int lo, hi;

        Fill(
            int[] values,
            AtomicIntegerArray visits,
            int lo,
            int hi
        ) {
            this.values = values;
            this.visits = visits;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected void compute() {
            if (hi - lo <= 16) {
                for (int i = lo; i < hi; i++) {
                    values[i] = i * i;
                    visits.incrementAndGet(i);
                }
                return;
            }

            int mid = (lo + hi) >>> 1;
            invokeAll(
                new Fill(values, visits, lo, mid),
                new Fill(values, visits, mid, hi)
            );
        }
    }

    public static void main(String[] args)
            throws Exception {
        int[] values = new int[100];
        AtomicIntegerArray visits =
            new AtomicIntegerArray(values.length);

        ForkJoinPool pool = new ForkJoinPool(3);
        try {
            Fill root = new Fill(
                values, visits, 0, values.length
            );
            pool.invoke(root);

            long sum = 0;
            int missing = 0;
            int duplicates = 0;

            for (int i = 0; i < values.length; i++) {
                sum += values[i];
                if (visits.get(i) == 0) missing++;
                if (visits.get(i) > 1) duplicates++;
            }

            System.out.println(
                "normal=" + root.isCompletedNormally()
            );
            System.out.println("squaresSum=" + sum);
            System.out.println("missing=" + missing);
            System.out.println("duplicates=" + duplicates);
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ActionCoverageDemo.java
java ActionCoverageDemo
```

Stdout:

```text
normal=true
squaresSum=328350
missing=0
duplicates=0
```

Đây là tổng bình phương từ 0 tới 99, kiểm tra đồng thời root normal và coverage. `invokeAll` tiện để fork/join các child **trong nhánh bình thường**. Tuy nhiên, nếu một child ném exception, `invokeAll` có thể ném lỗi và các child khác có thể bị cancel/chưa hoàn tất bình thường. Vì thế kết quả `invokeAll` thất bại **không phải bằng chứng mọi phần tử đã được chạy**.

## 6. submit/execute bất đồng bộ: phải có điểm chờ đúng

Ví dụ sai khi cần output đã được hoàn thiện:

```java
// Phản ví dụ:
pool.execute(task);
publishResult(output); // Có thể chạy trước compute().
```

Dùng `pool.invoke(task)` nếu muốn gửi/chờ một lần, hoặc `pool.execute(task); task.join();` nếu đã gửi bất đồng bộ. `join` là điểm đồng bộ completion của task; nếu cần deadline của caller, sử dụng `get(timeout,unit)` và xử lý riêng trường hợp hết thời gian.

### Ví dụ 3 — SubmitJoinDemo.java

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class SubmitJoinDemo {
    static class Slow extends RecursiveTask<String> {
        final CountDownLatch entered, release;

        Slow(
            CountDownLatch entered,
            CountDownLatch release
        ) {
            this.entered = entered;
            this.release = release;
        }

        @Override
        protected String compute() {
            entered.countDown();
            try {
                if (!release.await(
                        3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "gate"
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
            return "READY";
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch entered =
            new CountDownLatch(1);
        CountDownLatch release =
            new CountDownLatch(1);
        Slow task = new Slow(entered, release);

        try {
            pool.execute(task);
            if (!entered.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not started"
                );
            }

            System.out.println(
                "beforeReleaseDone=" + task.isDone()
            );

            release.countDown();
            System.out.println("joined=" + task.join());
            System.out.println(
                "afterJoinDone=" + task.isDone()
            );
            System.out.println(
                "normal=" + task.isCompletedNormally()
            );
        } finally {
            release.countDown();
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac SubmitJoinDemo.java
java SubmitJoinDemo
```

Stdout:

```text
beforeReleaseDone=false
joined=READY
afterJoinDone=true
normal=true
```

`CountDownLatch` ở đây chỉ để **điều phối thời điểm trong test**. Đừng dùng `sleep` hoặc chờ latch dài trong Fork/Join computation production; pool tối ưu cho phép chia tính toán CPU và không cam kết bù mọi dạng blocking không được quản lý.

## 7. Ngoại lệ của task phải được quan sát

Khi một leaf ném `IllegalStateException`, task không kết thúc bình thường, nhưng `isDone()` vẫn true. Một caller chỉ kiểm tra `isDone` sẽ bỏ qua lỗi.

### Ví dụ 4 — ForkExceptionDemo.java

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class ForkExceptionDemo {
    static class Broken extends RecursiveTask<Integer> {
        @Override
        protected Integer compute() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            Broken task = new Broken();
            pool.execute(task);

            try {
                task.join();
            } catch (RuntimeException ex) {
                System.out.println(
                    "joinType=" +
                    ex.getClass().getSimpleName()
                );
            }

            System.out.println("done=" + task.isDone());
            System.out.println(
                "normal=" + task.isCompletedNormally()
            );
            System.out.println(
                "abnormal=" +
                task.isCompletedAbnormally()
            );
            System.out.println(
                "storedType=" +
                task.getException()
                    .getClass().getSimpleName()
            );

            try {
                task.get();
            } catch (ExecutionException ex) {
                System.out.println(
                    "getType=" +
                    ex.getClass().getSimpleName()
                );
                System.out.println(
                    "causeType=" +
                    ex.getCause()
                        .getClass().getSimpleName()
                );
            }
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ForkExceptionDemo.java
java ForkExceptionDemo
```

Stdout:

```text
joinType=IllegalStateException
done=true
normal=false
abnormal=true
storedType=IllegalStateException
getType=ExecutionException
causeType=IllegalStateException
```

Đây là bằng chứng rõ rằng **done không đồng nghĩa success**. Với `getException()` trong code tổng quát, cần kiểm tra `null` khi task chưa xong hoặc hoàn thành bình thường; ví dụ này biết trước task thất bại nên có thể truy cập Throwable.

## 8. Một task lỗi không nên làm bỏ qua việc kiểm tra task khác

Cách này có thể bỏ sót task nếu cần báo cáo đầy đủ:

```java
// Phản ví dụ nếu yêu cầu collect-all:
for (ForkJoinTask<?> task : tasks) {
    task.join(); // Một exception sẽ thoát vòng lặp.
}
```

Với chính sách **collect-all**, kiểm tra từng task độc lập, tiếp tục join các task còn lại, rồi tổng hợp lỗi. Với chính sách **fail-fast**, có thể hủy task khác nhưng phải ghi rõ trạng thái **PARTIAL/CANCELLED** thay vì full success.

### Ví dụ 5 — JoinEveryTaskDemo.java

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class JoinEveryTaskDemo {
    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(3);
        AtomicInteger successes =
            new AtomicInteger();

        try {
            List<RecursiveAction> tasks = Arrays.asList(
                new RecursiveAction() {
                    protected void compute() {
                        successes.incrementAndGet();
                    }
                },
                new RecursiveAction() {
                    protected void compute() {
                        throw new IllegalArgumentException(
                            "invalid"
                        );
                    }
                },
                new RecursiveAction() {
                    protected void compute() {
                        successes.incrementAndGet();
                    }
                }
            );

            for (RecursiveAction task : tasks) {
                pool.execute(task);
            }

            int failures = 0;
            int normals = 0;

            for (RecursiveAction task : tasks) {
                try {
                    task.join();
                } catch (RuntimeException ex) {
                    failures++;
                }
                if (task.isCompletedNormally()) {
                    normals++;
                }
            }

            System.out.println(
                "joinedCount=" + tasks.size()
            );
            System.out.println(
                "normalCount=" + normals
            );
            System.out.println(
                "failureCount=" + failures
            );
            System.out.println(
                "successSideEffects=" + successes.get()
            );
            System.out.println(
                "allDone=" +
                tasks.stream()
                    .allMatch(ForkJoinTask::isDone)
            );
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac JoinEveryTaskDemo.java
java JoinEveryTaskDemo
```

Stdout:

```text
joinedCount=3
normalCount=2
failureCount=1
successSideEffects=2
allDone=true
```

Cả ba task được join/quan sát nhưng có **một lỗi**. Do đó `allDone=true` và `failureCount=1` cùng đúng. Nếu output business yêu cầu cả ba task thành công thì job phải được đánh dấu **FAILED**, hoặc công bố **PARTIAL** theo hợp đồng, không tự biến partial thành success.

### 8.1. Exception xảy ra giữa fork và join

Pattern thường dùng:

```java
left.fork();
long right = rightTask.compute();
return left.join() + right;
```

Nếu `rightTask.compute()` ném exception, lệnh `left.join()` chưa được chạy. Nhánh left có thể vẫn đang chạy hoặc có lỗi không được quan sát.

Để giải quyết cần **exception-safe ownership**: ghi rõ ai chờ/cancel left khi right thất bại, có giữ primary exception và các secondary exception hay không. `try/finally` có thể hỗ trợ, nhưng `left.join()` trong finally cũng có thể ném và **che lỗi ban đầu**, nên phải xử lý và ghi `addSuppressed` nếu chính sách cần thu thập cả hai.

## 9. Parent hoàn tất nhưng child chưa: lỗi thiếu join

`pool.invoke(parent)` chỉ chờ task parent. Nếu parent fork child rồi trả về mà không join, parent có thể **normal** trong lúc child còn chưa thực thi xong.

### Ví dụ 6 — OrphanTaskDemo.java

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class OrphanTaskDemo {
    static class Child extends RecursiveAction {
        final CountDownLatch started, release;
        final AtomicInteger visited;

        Child(
            CountDownLatch started,
            CountDownLatch release,
            AtomicInteger visited
        ) {
            this.started = started;
            this.release = release;
            this.visited = visited;
        }

        @Override
        protected void compute() {
            started.countDown();
            try {
                if (!release.await(
                        4, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "timeout"
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
            visited.incrementAndGet();
        }
    }

    static class Parent extends RecursiveAction {
        final Child child;

        Parent(Child child) {
            this.child = child;
        }

        @Override
        protected void compute() {
            child.fork(); // LỖI CỐ Ý: thiếu child.join().
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        CountDownLatch started =
            new CountDownLatch(1);
        CountDownLatch release =
            new CountDownLatch(1);
        AtomicInteger visited = new AtomicInteger();

        Child child =
            new Child(started, release, visited);
        Parent parent = new Parent(child);

        try {
            pool.invoke(parent);
            if (!started.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "child not started"
                );
            }

            System.out.println(
                "parentDone=" +
                parent.isCompletedNormally()
            );
            System.out.println(
                "childDoneBeforeRelease=" +
                child.isDone()
            );
            System.out.println(
                "visitedBeforeRelease=" +
                visited.get()
            );

            release.countDown();
            child.join();

            System.out.println(
                "childNormal=" +
                child.isCompletedNormally()
            );
            System.out.println(
                "visitedAfterJoin=" +
                visited.get()
            );
        } finally {
            release.countDown();
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac OrphanTaskDemo.java
java OrphanTaskDemo
```

Stdout:

```text
parentDone=true
childDoneBeforeRelease=false
visitedBeforeRelease=0
childNormal=true
visitedAfterJoin=1
```

Bài test chứng minh parent đã báo xong **trước** child. Sau khi release và `child.join()`, công việc mới được xác nhận. Latch được dùng có chủ đích để tái hiện lỗi; đây không phải cách lập trình Fork/Join production.

## 10. Cancellation có thể đánh dấu task done mà chưa chạy compute

`ForkJoinTask.cancel(...)` cho phép đánh dấu task là cancelled. `isDone()` có thể true, `isCancelled()` true, `isCompletedAbnormally()` true, và `join()` ném `CancellationException`.

Theo contract hiện hành của `ForkJoinTask`, đối số `mayInterruptIfRunning` **không có tác dụng trong triển khai mặc định**, vì việc ngắt không là cơ chế điều khiển cancellation của lớp này. Đừng giả định `cancel(true)` làm mọi worker lập tức dừng/rollback.

### Ví dụ 7 — ForkCancellationDemo.java

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ForkCancellationDemo {
    static class Blocker extends RecursiveTask<Integer> {
        final CountDownLatch started, release;

        Blocker(
            CountDownLatch started,
            CountDownLatch release
        ) {
            this.started = started;
            this.release = release;
        }

        @Override
        protected Integer compute() {
            started.countDown();
            try {
                if (!release.await(
                        4, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "timeout"
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
            return 7;
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch started =
            new CountDownLatch(1);
        CountDownLatch release =
            new CountDownLatch(1);
        AtomicBoolean queuedRan =
            new AtomicBoolean();

        Blocker blocker =
            new Blocker(started, release);

        RecursiveTask<Integer> queued =
            new RecursiveTask<Integer>() {
                protected Integer compute() {
                    queuedRan.set(true);
                    return 9;
                }
            };

        try {
            pool.execute(blocker);
            if (!started.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not started"
                );
            }

            pool.execute(queued);
            System.out.println(
                "cancelled=" + queued.cancel(false)
            );

            try {
                queued.join();
            } catch (CancellationException ex) {
                System.out.println("joinCancelled=true");
            }

            release.countDown();
            System.out.println(
                "blocker=" + blocker.join()
            );
            System.out.println(
                "queuedRan=" + queuedRan.get()
            );
            System.out.println(
                "cancelStatus=" + queued.isCancelled()
            );
            System.out.println(
                "abnormal=" +
                queued.isCompletedAbnormally()
            );
        } finally {
            release.countDown();
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ForkCancellationDemo.java
java ForkCancellationDemo
```

Stdout:

```text
cancelled=true
joinCancelled=true
blocker=7
queuedRan=false
cancelStatus=true
abnormal=true
```

Đây là bằng chứng task có thể **done/cancelled** mà chưa làm việc. Nếu một business job có cancellation, phần chưa xử lý phải được phân loại rõ và có chính sách retry/reconcile.

## 11. get(timeout) không tự hủy task

`Future.get(timeout,unit)` giới hạn thời gian caller chờ. Sau `TimeoutException`, task **có thể tiếp tục chạy** và sau đó vẫn có kết quả.

### Ví dụ 8 — ForkTimeoutDemo.java

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ForkTimeoutDemo {
    static class Slow extends RecursiveTask<Integer> {
        final CountDownLatch started, release;

        Slow(
            CountDownLatch started,
            CountDownLatch release
        ) {
            this.started = started;
            this.release = release;
        }

        @Override
        protected Integer compute() {
            started.countDown();
            try {
                if (!release.await(
                        4, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "timeout"
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
            return 17;
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch started =
            new CountDownLatch(1);
        CountDownLatch release =
            new CountDownLatch(1);
        Slow job = new Slow(started, release);

        try {
            pool.execute(job);
            if (!started.await(
                    3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "not started"
                );
            }

            try {
                job.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println(
                    "callerTimedOut=true"
                );
            }

            System.out.println(
                "doneAfterTimeout=" + job.isDone()
            );

            release.countDown();

            System.out.println(
                "eventually=" +
                job.get(3, TimeUnit.SECONDS)
            );
        } finally {
            release.countDown();
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac ForkTimeoutDemo.java
java ForkTimeoutDemo
```

Stdout:

```text
callerTimedOut=true
doneAfterTimeout=false
eventually=17
```

Lệnh `get(100ms)` timeout nhưng task vẫn tồn tại và sau khi release có kết quả 17. Trong sản xuất, không giả định `isDone=false` luôn đúng sau mọi timeout vì task có thể kết thúc ngay thời điểm sau đó; demo dùng latch để tạo thứ tự kiểm thử rõ ràng.

Khi timeout làm caller không còn muốn nhận output, cần chính sách cancellation/deadline và kiểm tra version trước khi publish kết quả muộn.

## 12. Kết thúc pool riêng đúng cách

`shutdown()` yêu cầu pool ngừng nhận task mới và hoàn tất task đã nhận. `awaitTermination(timeout,unit)` chờ pool thật sự kết thúc; `isTerminated()` phản ánh trạng thái cuối. `awaitQuiescence` chỉ nói pool tạm không có việc đang chạy/chờ theo semantics quiescence, **không chứng minh tất cả dữ liệu dự kiến đã được submit**.

### Ví dụ 9 — PoolTerminationDemo.java

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

public class PoolTerminationDemo {
    static class Answer extends RecursiveTask<Integer> {
        protected Integer compute() {
            return 42;
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        Answer task = new Answer();

        try {
            System.out.println(
                "answer=" + pool.invoke(task)
            );
            System.out.println(
                "taskNormal=" +
                task.isCompletedNormally()
            );

            pool.shutdown();

            System.out.println(
                "shutdown=" + pool.isShutdown()
            );
            System.out.println(
                "terminated=" +
                pool.awaitTermination(
                    5, TimeUnit.SECONDS
                )
            );
            System.out.println(
                "isTerminated=" + pool.isTerminated()
            );

            try {
                pool.execute(new Answer());
            } catch (RejectedExecutionException ex) {
                System.out.println(
                    "rejectAfterShutdown=true"
                );
            }
        } finally {
            if (!pool.isShutdown()) {
                pool.shutdown();
            }
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac PoolTerminationDemo.java
java PoolTerminationDemo
```

Stdout:

```text
answer=42
taskNormal=true
shutdown=true
terminated=true
isTerminated=true
rejectAfterShutdown=true
```

**Giới hạn quan trọng:** `ForkJoinPool.commonPool()` không bị shutdown bởi `shutdown()` hay `shutdownNow()`; `awaitTermination` trên common pool không phải bằng chứng pool đã terminate. Nếu cần lifecycle kiểm soát, dùng pool riêng và chờ termination.

`shutdownNow()` cố hủy/dừng task; nó không hoàn tác dữ liệu đã ghi ra file, DB hoặc service. Với công việc business quan trọng, thiết kế trạng thái **FAILED/PARTIAL/CANCELLED**, checkpoint và recovery theo hợp đồng.

## 13. Stress test 201 kích thước để bắt lỗi biên

Test một mảng lớn chưa đủ. Cần thử `n=0`, `n=1`, `THRESHOLD-1`, `THRESHOLD`, `THRESHOLD+1`, n lẻ, n không chia hết, và các mức parallelism.

### Ví dụ 10 — StressCoverageDemo.java

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class StressCoverageDemo {
    static class Count extends RecursiveTask<Long> {
        final int lo, hi;
        final AtomicIntegerArray visits;

        Count(
            int lo,
            int hi,
            AtomicIntegerArray visits
        ) {
            this.lo = lo;
            this.hi = hi;
            this.visits = visits;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= 9) {
                long result = 0;
                for (int i = lo; i < hi; i++) {
                    visits.incrementAndGet(i);
                    result += i;
                }
                return result;
            }

            int mid = lo + (hi - lo) / 2;
            Count left =
                new Count(lo, mid, visits);

            left.fork();
            long right =
                new Count(mid, hi, visits).compute();

            return left.join() + right;
        }
    }

    public static void main(String[] args)
            throws Exception {
        ForkJoinPool pool = new ForkJoinPool(4);
        int failed = 0;

        try {
            for (int n = 0; n <= 200; n++) {
                AtomicIntegerArray visits =
                    new AtomicIntegerArray(n);

                long actual = pool.invoke(
                    new Count(0, n, visits)
                );

                long expected =
                    (long) n * (n - 1) / 2;

                if (actual != expected) {
                    failed++;
                }

                for (int i = 0; i < n; i++) {
                    if (visits.get(i) != 1) {
                        failed++;
                        break;
                    }
                }
            }

            System.out.println("cases=201");
            System.out.println(
                "failedCases=" + failed
            );
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac StressCoverageDemo.java
java StressCoverageDemo
```

Stdout:

```text
cases=201
failedCases=0
```

Đã kiểm tra 201 kích thước, không phát hiện sai kết quả hoặc index thiếu/trùng. Đây không phải chứng minh hình thức cho mọi input: nên phối hợp test nhiều ngưỡng, nhiều parallelism, error injection và kiểm tra bất biến phân hoạch.

## 14. Exception policy: fail-fast hay collect-all?

Nếu một child ném lỗi, phải xác định **chính sách của job**:

**Fail-fast:** Thoát với lỗi, có thể cancel các công việc còn lại. Không được trả SUCCESS cho output chỉ xử lý một phần. Cancellation không đảm bảo mọi task đang chạy bị ngắt hoặc side effect được rollback.

**Collect-all:** Mỗi item có kết quả `SUCCESS`/`FAILED`, các task đều được chờ/quan sát, sau đó trả thống kê lỗi và những item chưa hoàn thành. Nếu một phần dữ liệu không đủ điều kiện để công bố, không publish nó chỉ vì một số leaf thành công.

Đầu ra ví dụ ứng dụng:

```text
ItemResult:
  itemId
  status = SUCCESS | FAILED | CANCELLED
  data
  errorCode
```

Đây là schema do ứng dụng tự định nghĩa, không phải class Java dựng sẵn.

Khi một nhánh compute ném lỗi **trước khi chờ sibling** đã fork, có nguy cơ child chưa được join. Dùng thiết kế exception-safe completion ownership; nếu join trong finally thì chú ý exception từ join có thể che exception ban đầu, nên cần bảo toàn primary/secondary error theo policy.

## 15. Những cách test đồng thời nên tránh

### 15.1. Dùng Thread.sleep rồi đoán task đã xong

`Thread.sleep(100)` không phải synchronization; tốc độ CPU, GC và lịch luồng làm test flaky. Dùng `join()` hoặc `get(timeout)`, đồng thời dùng `CountDownLatch`/barrier trong test tái hiện race.

### 15.2. So thứ tự System.out.println của các leaf

Fork/Join dùng work stealing, nên thứ tự chạy không cố định. Hãy lưu output theo ID/index và kiểm tra tập kết quả; không hardcode thứ tự log làm expected.

### 15.3. Đếm số leaf nhưng không biết leaf nào

Một leaf chạy hai lần và một leaf khác không chạy có thể tạo cùng tổng số leaf callbacks. Cần instrumentation theo từng ID/item.

### 15.4. Dùng getQueuedTaskCount như business coverage

`getQueuedTaskCount`/`getStealCount` là thông tin vận hành/scheduler, không phải danh sách các item đã xử lý. Không dùng chúng để chứng minh “không bỏ sót”.

### 15.5. Dùng RecursiveAction cùng ghi ArrayList không đồng bộ

`ArrayList` không thread-safe. Nếu leaf cùng ghi một collection, phải dùng cấu trúc đồng thời hoặc cơ chế đồng bộ thích hợp; tốt hơn là mỗi leaf xử lý phần output rời nhau khi có thể.

### 15.6. ForkJoinTask lồng I/O chậm hoặc chờ khóa lâu

Fork/Join phù hợp với công việc có thể chia nhỏ và hợp nhất, không bảo đảm bù mọi blocking ngoài cơ chế. Nếu bắt buộc block, cần nghiên cứu `ForkJoinPool.ManagedBlocker` và lựa chọn executor thích hợp. Những latch trong demo chỉ là công cụ kiểm thử có timeout/finally, không là pattern production.

## 16. CountedCompleter và completion phức tạp

`CountedCompleter` hỗ trợ mô hình task có **pending completion counts**. Nếu dùng:

- Kiểm tra pending count có đúng số nhánh cần hoàn thành không.
- Đảm bảo mọi nhánh áp dụng cơ chế completion đúng.
- Truyền hoặc ghi nhận exception theo contract.
- Đừng dùng root completion thay cho coverage dữ liệu.
- Test từng task/item ID và trường hợp lỗi giữa quá trình giảm pending.

Nếu bài toán có thể mô tả bằng `RecursiveTask` và fork một nhánh, compute nhánh kia, join nhánh đã fork, mẫu đơn giản thường dễ kiểm tra hơn. Không chọn CountedCompleter chỉ để tránh viết join.

## 17. Ma trận kiểm thử tối thiểu

| Bài test | Kỳ vọng |
| --- | --- |
| Input rỗng | Không xử lý item nào, không lỗi index |
| Input một phần tử | Item duy nhất xử lý một lần |
| THRESHOLD±1 | Phân chia tiến triển đúng |
| Kích thước lẻ | Không bỏ sót/trùng midpoint |
| Parallelism 1, 2, 4 | Output và coverage nhất quán |
| RecursiveTask bình thường | `isCompletedNormally=true` và result đúng |
| RecursiveAction bình thường | Các vùng output được ghi đủ |
| execute async | Chưa chờ không được coi là finished |
| join | Chờ hoàn tất và trả đúng result |
| Task ném exception | `isDone=true`, `isCompletedAbnormally=true` |
| join/get exception | Unchecked vs ExecutionException |
| Nhiều task một lỗi | Quan sát đủ 3 task, không che lỗi |
| Parent quên join | Parent done trước child |
| Cancellation queued | Done/cancelled nhưng compute chưa chạy |
| get(timeout) | Caller timeout, task có thể vẫn chạy |
| shutdown + awaitTermination | Pool riêng đã dừng |
| Stress n=0..200 | Không có item thiếu/trùng |
| Exception giữa fork và join | Sibling được xử lý theo policy |
| Output partial | Không nhầm thành full success |

## 18. Các lỗi thường gặp

1. **Quên join child:** Parent có thể kết thúc khi child còn chạy. Sửa bằng ownership rõ cho mỗi fork.
2. **Dùng `isDone` như success:** Lỗi và cancel cũng done. Kiểm tra `isCompletedNormally`.
3. **Tin `pool.invoke(root)` luôn chờ mọi descendant:** Không nếu root viết sai và bỏ quên child.
4. **Chỉ so tổng:** Dùng per-item coverage để bắt thiếu/trùng.
5. **Sai ranh giới `mid`:** Dùng `[lo,mid)` và `[mid,hi)`, test biên.
6. **Không có base case:** Recursion không dừng hoặc chia không nhỏ hơn.
7. **Nuốt exception trong leaf:** Job có thể trả partial như success.
8. **Lỗi đầu làm dừng vòng join:** Các task khác chưa được chờ/quan sát.
9. **Coi `invokeAll` khi lỗi là hoàn tất mọi child:** API không hứa tất cả child thành công.
10. **Đồng nhất cancelled với completed work:** Task có thể bị cancel trước compute.
11. **Đồng nhất timeout với cancellation:** `get(timeout)` không tự dừng task.
12. **Gọi shutdown rồi không awaitTermination:** Pool riêng có thể còn chạy.
13. **Gọi commonPool.shutdown để đợi:** Common pool không shutdown theo cách đó.
14. **Dùng quiescence làm chứng cứ đủ input:** Không chứng minh đã submit đủ.
15. **Dùng sleep để test:** Không bảo đảm scheduling; dùng latch/join.
16. **Dựa vào thứ tự log của worker:** Work stealing không hứa thứ tự.
17. **Dùng counter leaf tổng:** Không cho biết leaf/index nào bị bỏ.
18. **Ghi mảng/collection trùng vùng giữa workers:** Có thể race và mất dữ liệu.
19. **Exception trước sibling.join:** Forked sibling có thể không được chờ.
20. **Dùng shutdownNow như rollback:** Side effects trước đó không được undo.
21. **Tái sử dụng task đã hoàn thành như task mới:** Tạo task mới cho mỗi phép xử lý.
22. **Dùng scheduler metrics thay invariant:** Đo đúng item IDs.
23. **Đặt I/O dài trong Fork/Join worker:** Có thể làm giảm hiệu năng và liveness.
24. **Chỉ kiểm tra root normal:** Vẫn phải xác minh output và coverage nghiệp vụ.

## 19. Checklist review

1. Có biết input dự kiến gồm bao nhiêu item/ID không?
2. Có đúng base case cho n=0 và n=1 không?
3. Hai khoảng con rời nhau và phủ đúng khoảng cha không?
4. Mỗi nhánh được fork có owner join hoặc completion không?
5. Exception giữa fork và join được xử lý thế nào?
6. Caller đã chờ root bằng invoke/join/get phù hợp chưa?
7. Có phân biệt done, normal, abnormal, cancelled không?
8. Có propagate/collect mọi exception cần thiết không?
9. Có phân biệt fail-fast với collect-all không?
10. Có assert per-ID visits chính xác không?
11. Có so result với nguồn tham chiếu độc lập không?
12. Có test n lẻ và threshold±1 không?
13. Có test parallelism=1 và >1 không?
14. Có tránh flaky tests bằng latch/join thay sleep không?
15. Có xử lý timeout caller mà không coi task stopped không?
16. Có quản lý pool riêng bằng shutdown/awaitTermination không?
17. Có tránh hiểu sai common pool shutdown không?
18. Có xử lý dữ liệu partial và side effect khi lỗi/hủy không?
19. Nếu dùng CountedCompleter, pending count được kiểm thử không?
20. Có tránh dùng scheduler counters để kết luận business success không?

## 20. Câu hỏi ôn tập

**1.** `root.isDone()` true có đồng nghĩa mọi child xong không?

**Đáp án:** Không, nếu root quên join task con.

**2.** `task.isDone()` true có bảo đảm thành công không?

**Đáp án:** Không; có thể lỗi hoặc cancelled.

**3.** Dùng gì để biết task kết thúc bình thường?

**Đáp án:** `isCompletedNormally()`.

**4.** `join` và `get` khác thế nào khi task ném unchecked exception?

**Đáp án:** `join` ném unchecked exception, `get` thường bọc trong `ExecutionException`.

**5.** Vì sao không chỉ so sum?

**Đáp án:** Thiếu và trùng phần tử có thể triệt tiêu ở một số bài toán.

**6.** Phân hoạch đúng `[lo,hi)` thế nào?

**Đáp án:** `[lo,mid)` và `[mid,hi)`.

**7.** Khi một nhánh tính lỗi trước khi join sibling, có nguy cơ gì?

**Đáp án:** Sibling có thể chưa được chờ và lỗi của nó bị bỏ sót.

**8.** `invokeAll` ném lỗi có đồng nghĩa mọi child đã chạy thành công không?

**Đáp án:** Không.

**9.** Task bị cancel trước khi chạy có thể isDone=true không?

**Đáp án:** Có.

**10.** `get(timeout)` có tự dừng task không?

**Đáp án:** Không.

**11.** `shutdown()` có chờ pool dừng hẳn không?

**Đáp án:** Không, dùng `awaitTermination` sau shutdown với pool riêng.

**12.** commonPool.shutdown có hiệu lực như pool riêng không?

**Đáp án:** Không.

**13.** `isQuiescent` có chứng minh đủ item đã submit không?

**Đáp án:** Không.

**14.** Vì sao CountDownLatch tốt hơn sleep cho test race?

**Đáp án:** Nó điều phối thời điểm quan sát có chủ đích.

**15.** Làm sao chứng minh từng item được xử lý đúng một lần?

**Đáp án:** Kiểm tra `visits[i]==1` cho mọi index/ID.

**16.** Vì sao log order của leaf không nên là expected output?

**Đáp án:** Work-stealing không cam kết thứ tự thực thi.

**17.** Một task normal nhưng output thiếu item có được báo SUCCESS không?

**Đáp án:** Không, phải kiểm tra invariant business.

**18.** Vì sao không dùng `getQueuedTaskCount` thay kiểm tra coverage?

**Đáp án:** Đó là metric scheduler, không phải danh sách item đã làm.

**19.** Khi một leaf lỗi, hai chính sách chính là gì?

**Đáp án:** Fail-fast hoặc collect-all với trạng thái partial/error rõ ràng.

**20.** Vì sao phải test các kích thước quanh threshold?

**Đáp án:** Để bắt lỗi chia miền, midpoint và base case.

## 21. Tài liệu Oracle chính thức, còn áp dụng

- [ForkJoinTask — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, `get`, `isDone`, `isCompletedNormally`, `isCompletedAbnormally`, `cancel`.
- [ForkJoinPool — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): `invoke`, `execute`, `submit`, `shutdown`, `awaitTermination`, `awaitQuiescence` và common pool.
- [RecursiveTask — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveTask.html): task đệ quy trả kết quả.
- [RecursiveAction — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveAction.html): task đệ quy trả void.
- [CountedCompleter — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountedCompleter.html): pending count, quy tắc completion.
- [Future — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): timeout, cancellation và lỗi.
- [AtomicIntegerArray — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html): instrumentation theo index an toàn dưới concurrency.

**Ghi nhớ:** Ba điều phải kiểm tra trong Fork/Join là **kết thúc đúng**, **ngoại lệ/hủy được quan sát**, và **không bỏ sót/trùng item**. Một root done, pool terminated hay pool quiescent không tự chứng minh ba điều ấy. Sử dụng phân hoạch rời nhau, joins có ownership, error policy minh bạch, và kiểm thử coverage theo từng item để biết kết quả thật sự hoàn chỉnh.