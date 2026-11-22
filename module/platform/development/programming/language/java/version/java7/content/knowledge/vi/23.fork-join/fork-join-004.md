# Thiết kế compute với điều kiện dừng rõ ràng — Fork/Join trong Java

## 1. Vì sao điều kiện dừng là phần quan trọng nhất của Fork/Join?

Fork/Join là mô hình chia một bài toán lớn thành các bài toán con độc lập, xử lý chúng trên `ForkJoinPool` và ghép kết quả. Khác với vòng `for` tuần tự, một lời gọi `compute()` có thể tạo ra thêm nhiều tác vụ con. Vì vậy, nếu thiếu điều kiện dừng hoặc phân chia không làm bài toán nhỏ đi, hệ thống có thể:

- Đệ quy mãi và phát sinh `StackOverflowError`.
- Tạo quá nhiều `ForkJoinTask` làm tăng chi phí lập lịch, cấp phát bộ nhớ và GC.
- Xử lý trùng hoặc bỏ sót phần tử do chia khoảng sai.
- Chờ một tác vụ phụ thuộc vòng tròn, không bao giờ hoàn thành.
- Trả kết quả sai vì base case không xét mảng rỗng/âm.
- Chậm hơn chạy tuần tự nếu mỗi phần việc quá nhỏ.

**Thiết kế `compute()` tốt phải chứng minh được ba điều:** (1) Khi nào **dừng chia**? (2) Nếu chưa dừng, mỗi bước có thực sự **tiến gần đến điểm dừng** không? (3) Các kết quả ở phần lá và bước ghép có **giữ nguyên ý nghĩa bài toán** không?

~~~text
compute([lo, hi))
      |
      v
n = hi - lo
      |
      +-- n <= threshold --> base case --> tính trực tiếp --> return
      |
      +-- n > threshold --> mid = lo + n / 2
                               |
                      +--------+--------+
                      |                 |
                [lo, mid)           [mid, hi)
                      |                 |
                   compute            compute
                      |                 |
                      +--------+--------+
                               |
                        kết hợp kết quả
                               |
                             return
~~~

**Ngữ cảnh phiên bản:** `ForkJoinPool`, `RecursiveTask<V>` và `RecursiveAction` có từ Java 7 và vẫn được hỗ trợ. Bài ưu tiên ví dụ **Java 17+** có thể biên dịch bằng `javac --release 17`, đối chiếu hợp đồng hiện hành tại **Oracle Java SE 26**. Không xây nội dung dựa vào API lỗi thời/legacy.

**Kiểm chứng:** 13 chương trình độc lập ở dưới đã biên dịch với `javac -encoding UTF-8 --release 17` và chạy trên JDK 17. Kết quả stdout trình bày theo các giá trị đã kiểm chứng; không dùng thứ tự thread/tên worker để làm output cố định.

### Học xong bài này, bạn cần đạt được

1. Phân biệt `RecursiveTask<V>` (có kết quả) và `RecursiveAction` (không trả kết quả).
2. Viết đúng `protected V compute()` hoặc `protected void compute()`.
3. Tạo base case cho kích thước `0`, `1` và `n <= threshold`.
4. Dùng khoảng nửa mở `[lo, hi)` để tránh trùng/mất phần tử.
5. Giữ bất biến tiến triển: **mỗi bài toán con nhỏ hơn bài toán cha** khi chia.
6. Validate `threshold > 0` và ranh giới trước khi submit.
7. Sử dụng `fork` một nhánh, `compute` nhánh còn lại, rồi `join`.
8. Sử dụng `invokeAll` cho `RecursiveAction` khi phù hợp.
9. Chọn kết quả base case và phép ghép đúng với tổng, đếm, cực đại, tích.
10. Xử lý empty input mà không tự lấy `0` làm max của dãy âm.
11. Hiểu cách threshold thay đổi số leaf tasks và overhead.
12. Quản lý `ForkJoinPool`, ngoại lệ, blocking, shared state và shutdown.

## 2. Những thành phần chính của Fork/Join

| Thành phần | Vai trò |
| --- | --- |
| `ForkJoinPool` | Executor dùng chiến lược **work-stealing** để xử lý nhiều ForkJoinTasks |
| `ForkJoinTask<V>` | Lớp cơ sở cho tác vụ có thể fork, join, invoke |
| `RecursiveTask<V>` | Viết `compute()` trả kết quả kiểu `V` |
| `RecursiveAction` | Viết `compute()` không trả kết quả, dùng cho thao tác có side effect được kiểm soát |
| `fork()` | Sắp lịch cho một subtask thực hiện bất đồng bộ trong pool đang chạy |
| `join()` | Chờ subtask hoàn thành và lấy kết quả, hoặc truyền lỗi unchecked |
| `compute()` | Phương thức **do bạn tự định nghĩa** với base case, split và combine |
| `ForkJoinPool.invoke(task)` | Submit task gốc và chờ kết quả |
| `ForkJoinPool.submit(task)` | Submit task gốc, nhận đối tượng Future/task để chờ sau |
| `invokeAll(left,right)` | Sắp lịch và chờ nhiều subtasks, tiện cho `RecursiveAction` |

Ví dụ cấu trúc:

~~~java
static final class MyTask extends RecursiveTask<Long> {
    @Override
    protected Long compute() {
        // 1. Đo kích thước phần việc.
        // 2. Base case: tính trực tiếp và return.
        // 3. Nếu chưa dừng: chia thành 2 phần nhỏ hơn.
        // 4. Fork một nhánh, tính nhánh còn lại, join.
        // 5. Ghép kết quả và return.
        throw new UnsupportedOperationException(
                "Đây chỉ là skeleton minh họa");
    }
}
~~~

Đây là **skeleton minh họa**, không phải chương trình được khuyên chạy; ví dụ đầy đủ với code thật nằm ở các mục tiếp theo.

### 2.1. Work-stealing giải quyết điều gì?

Các worker trong `ForkJoinPool` có thể lấy việc từ queue của worker khác khi rảnh, giúp cân bằng các subtasks đã fork. Nhưng pool **không tự biết** chia mảng ở index nào, chọn threshold bao nhiêu hoặc điều kiện dừng của nghiệp vụ là gì. Tất cả là trách nhiệm của `compute()`.

Fork/Join phù hợp nhất khi tác vụ có thể chia thành những phần tính toán tương đối độc lập. Nó **không** là lựa chọn mặc định tốt cho tác vụ blocking I/O, đợi database hoặc mạng kéo dài.

Nguồn: [ForkJoinPool Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html), [ForkJoinTask Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html).

## 3. Hợp đồng của một compute có thể dừng

Hãy mô tả một tác vụ xử lý đoạn mảng bằng:

~~~text
Task(array, lo, hi, threshold)

Bất biến:
    0 <= lo <= hi <= array.length
    threshold >= 1

Đại lượng đo tiến triển:
    n = hi - lo

Base case:
    n <= threshold
    -> xử lý tuần tự đoạn [lo, hi)
    -> không tạo thêm subtask

Recursive case:
    n > threshold
    mid = lo + n / 2
    tạo [lo, mid) và [mid, hi)

Hậu điều kiện:
    tổng hợp kết quả hai phần bằng kết quả toàn đoạn
~~~

### 3.1. Vì sao nên dùng khoảng nửa mở?

Đoạn `[lo, hi)` bao gồm các index `lo, lo+1, …, hi-1`, **không bao gồm hi**. Ưu điểm:

- Số phần tử là `hi - lo`.
- Mảng rỗng biểu diễn bằng `lo == hi`.
- Toàn bộ mảng là `[0, array.length)`.
- Tách tại `mid` thành `[lo, mid)` và `[mid, hi)`.
- Hai đoạn không chồng lấn và không bỏ sót một phần tử nào.
- Vòng lá viết đơn giản `for (int i = lo; i < hi; i++)`.

Ví dụ mảng 7 phần tử:

~~~text
Index:        0  1  2  3  4  5  6
Values:       A  B  C  D  E  F  G

Root: [0,7)         n=7
    mid = 0 + 7/2 = 3
    left  [0,3)     A B C
    right [3,7)     D E F G

Nếu threshold=3:
    [0,3) là lá (3 phần tử)
    [3,7) còn 4 phần tử -> tiếp tục chia
        [3,5) D E
        [5,7) F G
~~~

Không dùng `[lo, mid]` kết hợp với `[mid, hi]` nếu cả hai đều đóng; index mid sẽ bị xử lý **hai lần**. Không gọi đệ quy lại với `[lo, hi)` nguyên vẹn, vì không giảm kích thước.

### 3.2. Chứng minh tiến triển

Giả sử `threshold >= 1` và đang ở recursive case:

- `n = hi - lo > threshold >= 1` nên `n >= 2`.
- `mid = lo + n / 2` với phép chia số nguyên.
- Vì `1 <= n/2 < n`, suy ra `lo < mid < hi`.
- `leftLength = mid - lo` và `rightLength = hi - mid` **đều lớn hơn 0 và nhỏ hơn n**.
- Vì kích thước là số nguyên không âm và giảm nghiêm ngặt, sau số hữu hạn lần chia sẽ đến `n <= threshold`.

Đây là **lập luận dừng** đơn giản và rất hữu ích khi review code. Nếu chọn `threshold=0`, khi `n=1` mà tiếp tục chia, `mid=lo`, một nhánh vẫn dài 1; không còn bảo đảm tiến triển. Vì vậy cần **validate threshold dương**, không chỉ viết một điều kiện kiểm tra cho đẹp.

### 3.3. Vì sao tính mid theo lo + n/2?

Ưu tiên:

~~~java
int n = hi - lo;
int mid = lo + n / 2;
~~~

thay vì:

~~~java
int mid = (lo + hi) / 2;
~~~

Với chỉ số nguyên lớn, `lo + hi` có thể vượt phạm vi `int`; cách `lo + (hi-lo)/2` tránh cộng hai số lớn trực tiếp khi đầu vào thỏa điều kiện range hợp lệ.

### 3.4. Base case không chỉ là một if

Để base case đúng cần đồng thời:

1. Điều kiện bảo đảm dừng (**ví dụ `n <= threshold`**).
2. Công việc tuần tự chính xác cho đoạn đó.
3. Kết quả trung tính/biên đúng khi đoạn rỗng.
4. `return` ngay, không vô tình chạy tiếp nhánh split.
5. Không `fork` task con khi đã đủ nhỏ.
6. Không dựa vào thứ tự thread và biến mutable dùng chung trừ khi đã đồng bộ.

## 4. Ví dụ 1 — Tính tổng bằng RecursiveTask với base case rõ ràng

Một bài tính tổng phù hợp vì:

- Có thể chia mảng thành những đoạn độc lập.
- Tổng của đoạn bằng tổng hai đoạn con.
- Base case cho đoạn rỗng là `0`.
- Có thể dùng `long` để giảm nguy cơ overflow so với `int`.
- Dễ đo số **leaf tasks** và số **split tasks**.

Tạo `SumBaseCaseDemo.java`:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class SumBaseCaseDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;
        final AtomicInteger leaves, splits;

        SumTask(
                int[] a, int lo, int hi, int threshold,
                AtomicInteger leaves, AtomicInteger splits) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
            this.leaves = leaves;
            this.splits = splits;
        }

        @Override
        protected Long compute() {
            int size = hi - lo;

            if (size <= threshold) {
                leaves.incrementAndGet();
                long sum = 0;
                for (int i = lo; i < hi; i++) {
                    sum = Math.addExact(sum, a[i]);
                }
                return sum;
            }

            splits.incrementAndGet();
            int mid = lo + size / 2;

            SumTask left = new SumTask(
                    a, lo, mid, threshold, leaves, splits);
            SumTask right = new SumTask(
                    a, mid, hi, threshold, leaves, splits);

            left.fork();
            long rightSum = right.compute();

            return Math.addExact(left.join(), rightSum);
        }
    }

    public static void main(String[] args) {
        int[] data = {4, -2, 7, 5, 1, -3, 8};
        AtomicInteger leaves = new AtomicInteger();
        AtomicInteger splits = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            long sum = pool.invoke(new SumTask(
                    data, 0, data.length, 3, leaves, splits));

            System.out.println("sum=" + sum);
            System.out.println("leaves=" + leaves.get());
            System.out.println("splits=" + splits.get());
            System.out.println("nodes=" +
                    (leaves.get() + splits.get()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SumBaseCaseDemo.java
java SumBaseCaseDemo
~~~

Stdout đã kiểm chứng:

~~~text
sum=20
leaves=3
splits=2
nodes=5
~~~

### 4.1. Giải thích cây tác vụ

Với bảy phần tử và threshold = 3:

~~~text
             [0,7)              (split #1)
             /   \
        [0,3)     [3,7)         (split #2 ở [3,7))
          |        /    \
         leaf   [3,5)  [5,7)
                   |      |
                  leaf   leaf

Tổng: 3 leaves, 2 splits, 5 task nodes.
~~~

- `if (size <= threshold)` là **base case**, không chia dưới ngưỡng.
- `mid` tách thành hai đoạn không giao nhau, bảo đảm progress.
- `left.fork()` lên lịch nhánh trái trong pool.
- `right.compute()` xử lý nhánh phải **ngay trong worker hiện tại**, không submit một Future riêng.
- `left.join()` chờ kết quả từ nhánh trái.
- `Math.addExact` thông báo `ArithmeticException` nếu tổng `long` overflow; không âm thầm trả kết quả bị tràn.
- `AtomicInteger` ở đây **chỉ để đo cây tác vụ trong demo**; production có thể bỏ counters để tránh contention.

**Không nhầm:** `compute()` được *override* để định nghĩa công việc; `right.compute()` là một lời gọi method trực tiếp, **không phải** lời gọi `fork()`. Quy tắc thường dùng là **fork một nhánh, tự compute nhánh còn lại rồi join**.

### 4.2. Vì sao không fork cả hai và join ngay?

Có thể dùng `invokeAll(left,right)` hoặc fork cả hai, nhưng nếu task cha chỉ cần tính một nhánh ở chính worker, việc `left.fork(); right.compute(); left.join()` thường tránh một phần overhead tạo thêm công việc xếp hàng. Đây là một **idiom**, không phải ràng buộc bắt buộc hay bảo đảm luôn nhanh hơn.

Javadoc lưu ý các subtask có phụ thuộc `join` nên được join theo thứ tự phù hợp, tránh các chu kỳ phụ thuộc. Không viết `left.fork(); left.join(); right.compute();` một cách máy móc rồi kỳ vọng hai nhánh chắc chắn chạy song song.

## 5. Base case cho dữ liệu rỗng, một phần tử và ranh giới threshold

Một thuật toán chỉ thử mảng kích thước lớn có thể che lỗi ở các đầu vào:

| Kích thước n | Threshold = 3 | Kỳ vọng |
| --- | --- | --- |
| 0 | n <= 3 | Không truy cập a[0], trả kết quả của tập rỗng |
| 1 | n <= 3 | Xử lý duy nhất một phần tử |
| 3 | n <= 3 | Không chia, xử lý trực tiếp |
| 4 | n > 3 | Chia thành 2 và 2 |
| 5 | n > 3 | Chia thành 2 và 3 |
| 7 | n > 3 | Chia thành 3 và 4, nhánh 4 tiếp tục |

Không phải mọi bài toán đều dùng kết quả tập rỗng là `0`. Tổng/đếm dùng `0`; tích dùng `1`; tìm maximum trên dãy rỗng nên dùng trạng thái **không có giá trị** thay vì lấy `0` vô điều kiện.

## 6. Ví dụ 2 — Kiểm thử đầy đủ các biên

Tạo `RangeEdgeCasesDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class RangeEdgeCasesDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;

        SumTask(int[] a, int lo, int hi, int threshold) {
            this.a = Objects.requireNonNull(a);
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;

            if (threshold < 1) {
                throw new IllegalArgumentException(
                        "threshold must be positive");
            }
            if (lo < 0 || lo > hi || hi > a.length) {
                throw new IndexOutOfBoundsException("invalid range");
            }
        }

        @Override
        protected Long compute() {
            int length = hi - lo;
            if (length <= threshold) {
                long result = 0;
                for (int i = lo; i < hi; i++) {
                    result += a[i];
                }
                return result;
            }

            int mid = lo + length / 2;
            SumTask left = new SumTask(a, lo, mid, threshold);
            SumTask right = new SumTask(a, mid, hi, threshold);

            left.fork();
            long rightValue = right.compute();
            return left.join() + rightValue;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println("empty=" +
                    pool.invoke(new SumTask(
                            new int[]{}, 0, 0, 3)));
            System.out.println("single=" +
                    pool.invoke(new SumTask(
                            new int[]{9}, 0, 1, 3)));
            System.out.println("equalThreshold=" +
                    pool.invoke(new SumTask(
                            new int[]{1, 2, 3}, 0, 3, 3)));
            System.out.println("aboveThreshold=" +
                    pool.invoke(new SumTask(
                            new int[]{1, 2, 3, 4}, 0, 4, 3)));
            System.out.println("oddLength=" +
                    pool.invoke(new SumTask(
                            new int[]{1, 2, 3, 4, 5}, 0, 5, 3)));
            System.out.println("negatives=" +
                    pool.invoke(new SumTask(
                            new int[]{-10, 2, -3}, 0, 3, 3)));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 RangeEdgeCasesDemo.java
java RangeEdgeCasesDemo
~~~

Stdout:

~~~text
empty=0
single=9
equalThreshold=6
aboveThreshold=10
oddLength=15
negatives=-11
~~~

Đoạn mảng rỗng `[0,0)` không chạy vòng lặp; tổng rỗng là 0. Mảng lẻ vẫn được chia đều gần nhất nhờ integer division. Điều kiện `threshold < 1` được từ chối trong constructor để không có input khiến recursive case tiến triển sai.

**Ghi chú về overflow:** Ví dụ biên dùng `long` nhưng phép cộng thường. Với yêu cầu kết quả không được overflow `long`, sử dụng `Math.addExact` như ví dụ đầu và báo lỗi khi vượt phạm vi, hoặc chọn `BigInteger` nếu miền giá trị có thể rất lớn.

## 7. Chứng minh cây đệ quy dừng bằng thống kê leaves/splits

Thêm kiểm thử invariant vào `compute()` rất hữu ích:

~~~java
if (!(lo < mid && mid < hi)) {
    throw new AssertionError("split failed to progress");
}
~~~

Đây là đoạn trong nhánh **recursive case** với `mid` đã tính và `threshold > 0`. Nếu invariant bị vi phạm, đừng tiếp tục tạo children. Khi đã chứng minh được công thức và validate input, assertion là biện pháp phòng vệ/kiểm thử, không thay việc chọn thiết kế đúng.

Đối với chia đôi nhị phân đầy đủ mà mỗi internal node có đúng hai children: nếu có `L` leaf tasks thì thường có `L - 1` internal splits và `2L - 1` total tasks. Nhưng số leaf phụ thuộc kích thước dữ liệu và threshold.

### 7.1. Ví dụ 3 — Đếm số leaf/split theo n

Tạo `TerminationCountDemo.java`:

~~~java
import java.util.concurrent.*;

public class TerminationCountDemo {
    record Stats(int leaves, int splits) {}

    static final class CountTask extends RecursiveTask<Stats> {
        final int lo, hi, threshold;

        CountTask(int lo, int hi, int threshold) {
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Stats compute() {
            int size = hi - lo;

            if (size <= threshold) {
                return new Stats(1, 0);
            }

            int mid = lo + size / 2;
            if (!(lo < mid && mid < hi)) {
                throw new AssertionError(
                        "split failed to progress");
            }

            CountTask left =
                    new CountTask(lo, mid, threshold);
            CountTask right =
                    new CountTask(mid, hi, threshold);

            left.fork();
            Stats rs = right.compute();
            Stats ls = left.join();

            return new Stats(
                    ls.leaves() + rs.leaves(),
                    ls.splits() + rs.splits() + 1);
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            for (int size : new int[]{0, 1, 2, 3, 4, 7}) {
                Stats stats = pool.invoke(
                        new CountTask(0, size, 2));
                System.out.println(
                        "n=" + size
                        + " leaves=" + stats.leaves()
                        + " splits=" + stats.splits());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TerminationCountDemo.java
java TerminationCountDemo
~~~

Stdout:

~~~text
n=0 leaves=1 splits=0
n=1 leaves=1 splits=0
n=2 leaves=1 splits=0
n=3 leaves=2 splits=1
n=4 leaves=2 splits=1
n=7 leaves=4 splits=3
~~~

**Tại sao n=0 có 1 leaf?** Ta vẫn khởi tạo **một root task** với range rỗng. Root không tạo children và tự xử lý base case, nên số *task leaf* là 1 dù không có phần tử nào. Đây là cách đếm **tasks**, không phải số phần tử dữ liệu.

Ví dụ dùng `record Stats` (có từ Java 16, được hỗ trợ trên Java 17) để ghép các số đếm mà không cần shared mutable counters. Mỗi nhánh trả một Stats, parent combine sau join. Điều này vừa minh họa hợp đồng `RecursiveTask<V>`, vừa tránh race condition trong phần kết quả.

## 8. Chọn threshold thế nào để vừa đúng vừa có hiệu năng?

**Threshold** là ngưỡng chuyển từ chia tác vụ sang xử lý tuần tự trong một leaf:

~~~java
if (hi - lo <= threshold) {
    return sequentialCalculation();
}
~~~

Khi threshold quá nhỏ:

- Nhiều tasks, nhiều objects và nhiều lượt fork/join.
- CPU có thể dành nhiều thời gian lập lịch hơn thời gian tính.
- Task queue/work-stealing overhead và GC tăng.
- Đệ quy sâu hơn và dễ tạo pressure lên memory/cache.

Khi threshold quá lớn:

- Có ít tasks để các workers lấy việc.
- Những công việc lớn không được chia đều, khó cân bằng tải.
- Một worker có thể làm quá nhiều phần trong khi các worker khác rảnh.

**Không có ngưỡng cố định luôn tốt** cho mọi CPU và mọi thuật toán. Nó phụ thuộc số phần tử, chi phí tính trên từng phần tử, cache locality, chi phí combine, số cores, parallelism, tần suất gọi và hoạt động của pool. Hãy đo trên dữ liệu thật.

Javadoc `ForkJoinTask` gợi ý rất thô rằng một task lý tưởng thường thực hiện hơn 100 nhưng dưới 10.000 phép tính cơ bản. Đây là **heuristic**, không phải quy tắc bắt buộc hay số phần tử áp dụng cho mọi thuật toán.

### 8.1. Thứ tự tối ưu hợp lý

1. Đảm bảo base case **đúng** và bảo đảm dừng.
2. Kiểm tra tuần tự làm baseline.
3. Chọn threshold ban đầu **dương** và đủ lớn để có công việc đáng kể trong leaf.
4. Đo tổng thời gian, throughput, allocation và CPU.
5. Thử các threshold khác nhau, cả dataset nhỏ lẫn lớn.
6. Không benchmark bằng cách in log trong compute; I/O sẽ làm méo kết quả.
7. Kiểm tra trên nhiều số cores và mức tải thực tế.
8. Khi dataset rất nhỏ, cân nhắc **không chạy parallel** vì overhead có thể lớn hơn lợi ích.

## 9. Ví dụ 4 — Threshold ảnh hưởng số lượng leaf tasks

Với `n=1024` và chia đôi đều, các threshold 1, 16, 128 tạo số lá rất khác nhau dù tổng không đổi.

Tạo `ThresholdTuningDemo.java`:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ThresholdTuningDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;
        final AtomicInteger leaves;

        SumTask(
                int[] a, int lo, int hi,
                int threshold, AtomicInteger leaves) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
            this.leaves = leaves;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= threshold) {
                leaves.incrementAndGet();
                long s = 0;
                for (int i = lo; i < hi; i++) {
                    s += a[i];
                }
                return s;
            }

            int mid = lo + n / 2;
            SumTask left = new SumTask(
                    a, lo, mid, threshold, leaves);
            left.fork();

            return new SumTask(
                    a, mid, hi, threshold, leaves).compute()
                    + left.join();
        }
    }

    public static void main(String[] args) {
        int[] a = new int[1024];
        for (int i = 0; i < a.length; i++) {
            a[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            for (int threshold : new int[]{1, 16, 128}) {
                AtomicInteger leaves = new AtomicInteger();
                long total = pool.invoke(new SumTask(
                        a, 0, a.length, threshold, leaves));
                System.out.println(
                        "threshold=" + threshold
                        + " leaves=" + leaves.get()
                        + " sum=" + total);
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ThresholdTuningDemo.java
java ThresholdTuningDemo
~~~

Stdout:

~~~text
threshold=1 leaves=1024 sum=524800
threshold=16 leaves=64 sum=524800
threshold=128 leaves=8 sum=524800
~~~

**Điều cần thấy:** Với input và thuật toán chia này, số leaf tasks là đặc tính của cây phân rã, không phải con số do worker scheduling quyết định. Nhưng **thời gian chạy** có thể thay đổi giữa máy và lần chạy; demo không tự gắn timing cứng vào output để tuyên bố threshold nào nhanh nhất.

`AtomicInteger` được sử dụng để đo, không phải để cộng tổng. Mỗi task trả giá trị của mình, parent ghép, tránh shared counter thành điểm nghẽn của thuật toán chính.

## 10. RecursiveTask: chọn phép ghép đúng với bài toán

Không phải bài nào cũng cộng tổng. Khi thiết kế `compute`, hãy định nghĩa rõ:

| Bài toán | Base case khi đoạn rỗng | Combine hai nhánh |
| --- | --- | --- |
| Tổng số nguyên | `0` | `left + right` |
| Đếm phần tử thỏa predicate | `0` | `leftCount + rightCount` |
| Tích | `1` | `leftProduct * rightProduct` |
| Maximum | Không có max trên tập rỗng | `max(left,right)` nếu cả hai có giá trị |
| Minimum | Không có min trên tập rỗng | `min(left,right)` nếu cả hai có giá trị |
| Merge sort | Đoạn rỗng/1 phần tử đã sắp xếp | Merge hai nửa đã sắp xếp |
| Biến đổi mảng | Không cần kết quả trả về | Mỗi nhánh ghi một vùng không giao nhau |

Một lỗi phổ biến là dùng `0` làm identity của phép **max**. Nếu mảng toàn số âm, `max(0,-3)` trả 0 dù mảng không có số 0. Cần reject empty input hoặc trả `OptionalInt.empty()` cho tập rỗng.

## 11. Ví dụ 5 — Đếm số phần tử bằng RecursiveTask<Long>

Tạo `CountMatchesDemo.java`:

~~~java
import java.util.concurrent.*;

public class CountMatchesDemo {
    static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, needle, threshold;

        Task(
                int[] a, int lo, int hi,
                int needle, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.needle = needle;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;

            if (n <= threshold) {
                long count = 0;
                for (int i = lo; i < hi; i++) {
                    if (a[i] == needle) {
                        count++;
                    }
                }
                return count;
            }

            int mid = lo + n / 2;
            Task left = new Task(
                    a, lo, mid, needle, threshold);
            left.fork();

            long right = new Task(
                    a, mid, hi, needle, threshold).compute();

            return left.join() + right;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int[] data = {0, 1, 0, 1, 2, 1, 3, 1, 4, 1};

            System.out.println("ones=" +
                    pool.invoke(new Task(
                            data, 0, data.length, 1, 3)));
            System.out.println("zeroes=" +
                    pool.invoke(new Task(
                            data, 0, data.length, 0, 3)));
            System.out.println("missing=" +
                    pool.invoke(new Task(
                            data, 0, data.length, 999, 3)));
            System.out.println("empty=" +
                    pool.invoke(new Task(
                            new int[0], 0, 0, 1, 3)));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CountMatchesDemo.java
java CountMatchesDemo
~~~

Stdout:

~~~text
ones=5
zeroes=2
missing=0
empty=0
~~~

Base case không dựa vào thread, chỉ xét đoạn `[lo,hi)`. Các phần rời nhau, nên mỗi phần tử được xét đúng một lần. Đếm số trùng khớp sử dụng `long`; nếu có dữ liệu lớn cần kiểm tra overflow. Với những predicates tốn CPU, phân việc có thể có lợi; với một phép so sánh cực rẻ, overhead fork/join dễ vượt lợi ích trên input nhỏ.

## 12. RecursiveAction: compute trả void nhưng vẫn phải có base case

`RecursiveAction` phù hợp khi một tác vụ xử lý dữ liệu **tại chỗ** và không cần trả giá trị, ví dụ:

- Biến đổi mỗi phần tử của một vùng mảng độc lập.
- Chuẩn hóa các blocks dữ liệu.
- Sắp xếp tại chỗ theo kiểu divide-and-conquer.
- Áp dụng một thao tác chỉ ảnh hưởng vùng dữ liệu thuộc quyền sở hữu của task.

Với `RecursiveAction`, chữ ký là:

~~~java
@Override
protected void compute() {
    if (enoughSmall()) {
        performSequentialWork();
        return;  // Base case void vẫn phải kết thúc.
    }
    // Chia công việc và phối hợp subtasks.
}
~~~

Đây là skeleton mô tả; các method minh họa cần được định nghĩa trong class thật. Không chia cùng một vùng dữ liệu thành nhiều tasks ghi đè nhau. Với mảng, mỗi task nên có khoảng chỉ số **không chồng lấn**.

## 13. Ví dụ 6 — RecursiveAction nhân đôi mỗi phần tử

Tạo `ActionTransformDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class ActionTransformDemo {
    static final class DoubleTask extends RecursiveAction {
        final int[] a;
        final int lo, hi, threshold;

        DoubleTask(
                int[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected void compute() {
            int n = hi - lo;

            if (n <= threshold) {
                for (int i = lo; i < hi; i++) {
                    a[i] = Math.multiplyExact(a[i], 2);
                }
                return;
            }

            int mid = lo + n / 2;
            invokeAll(
                    new DoubleTask(a, lo, mid, threshold),
                    new DoubleTask(a, mid, hi, threshold));
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3, 4, 5, 6, 7};
        int[] empty = {};

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            pool.invoke(new DoubleTask(
                    a, 0, a.length, 2));
            pool.invoke(new DoubleTask(
                    empty, 0, empty.length, 2));

            System.out.println("doubled=" +
                    Arrays.toString(a));
            System.out.println("empty=" +
                    Arrays.toString(empty));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ActionTransformDemo.java
java ActionTransformDemo
~~~

Stdout:

~~~text
doubled=[2, 4, 6, 8, 10, 12, 14]
empty=[]
~~~

**Vì sao không bị data race trong phép ghi?** Các subtasks xử lý những khoảng `[lo,mid)` và `[mid,hi)` **rời nhau**; không có hai tasks ghi cùng `a[i]`. Parent gọi `invokeAll`, đợi children hoàn tất rồi mới trả về; main chỉ in sau `pool.invoke`.

**Lưu ý:** Khi phép nhân overflow, `Math.multiplyExact` có thể ném ngoại lệ, và nếu các nhánh đã sửa một phần mảng trước lỗi, dữ liệu sẽ **không tự rollback**. Fork/Join không cung cấp transaction. Nếu cần atomic update, nên tính ra buffer riêng và chỉ publish sau khi toàn bộ thành công.

## 14. Xử lý dãy rỗng đúng với bài toán maximum

Tổng của tập rỗng thường xác định là 0. Nhưng **maximum của tập rỗng không xác định**. Lấy `0` làm sentinel sẽ gây lỗi với mảng số âm.

Cách an toàn là biểu diễn kết quả **có thể không tồn tại** bằng `OptionalInt`:

~~~text
[ ]                -> OptionalInt.empty()
[-10, -3, -25]     -> OptionalInt.of(-3)
[42]               -> OptionalInt.of(42)

Ghép:
empty + X -> X
X + empty -> X
Some(a) + Some(b) -> Some(max(a,b))
~~~

## 15. Ví dụ 7 — Maximum với OptionalInt

Tạo `ParallelMaxDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class ParallelMaxDemo {
    static final class MaxTask
            extends RecursiveTask<OptionalInt> {
        final int[] a;
        final int lo, hi, threshold;

        MaxTask(int[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected OptionalInt compute() {
            int n = hi - lo;

            if (n <= threshold) {
                if (n == 0) {
                    return OptionalInt.empty();
                }

                int max = a[lo];
                for (int i = lo + 1; i < hi; i++) {
                    max = Math.max(max, a[i]);
                }
                return OptionalInt.of(max);
            }

            int mid = lo + n / 2;
            MaxTask left =
                    new MaxTask(a, lo, mid, threshold);
            left.fork();

            OptionalInt right =
                    new MaxTask(a, mid, hi, threshold).compute();
            OptionalInt l = left.join();

            if (l.isEmpty()) {
                return right;
            }
            if (right.isEmpty()) {
                return l;
            }

            return OptionalInt.of(
                    Math.max(l.getAsInt(), right.getAsInt()));
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int[] negative = {-10, -3, -25, -4, -9};

            System.out.println("negativeMax=" +
                    pool.invoke(new MaxTask(
                            negative, 0, negative.length, 2))
                            .orElseThrow());

            System.out.println("emptyPresent=" +
                    pool.invoke(new MaxTask(
                            new int[0], 0, 0, 2))
                            .isPresent());

            System.out.println("singleton=" +
                    pool.invoke(new MaxTask(
                            new int[]{42}, 0, 1, 2))
                            .orElseThrow());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ParallelMaxDemo.java
java ParallelMaxDemo
~~~

Stdout:

~~~text
negativeMax=-3
emptyPresent=false
singleton=42
~~~

**Điểm quan trọng:** Độ lớn của bài toán chỉ quyết định **khi nào dừng**, còn **toán tử combine** quyết định tính đúng đắn. Một compute có base case dừng được nhưng combine dùng sai phần tử trung tính vẫn trả kết quả sai.

## 16. Bài toán tích: dùng BigInteger để tránh tràn số nguyên

Giai thừa `n!` là tích `1 × 2 × … × n`, với `0! = 1`. Một `int` hay `long` có thể tràn nhanh. Với `BigInteger`, ta có thể chia khoảng tích và ghép bằng `multiply`.

~~~text
factorial(10)
= product([1,11))
= product([1,6)) × product([6,11))

Base case [lo,hi) có hi-lo <= 3:
    product = BigInteger.ONE
    for i in [lo,hi): product *= i
~~~

Dừng ở threshold 3 có nghĩa xử lý trực tiếp tối đa ba số, không có vòng đệ quy vô hạn.

## 17. Ví dụ 8 — Giai thừa bằng RecursiveTask<BigInteger>

Tạo `FactorialProductDemo.java`:

~~~java
import java.math.*;
import java.util.concurrent.*;

public class FactorialProductDemo {
    static final class ProductTask
            extends RecursiveTask<BigInteger> {
        final int lo, hi, threshold;

        ProductTask(int lo, int hi, int threshold) {
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected BigInteger compute() {
            int n = hi - lo;

            if (n <= threshold) {
                BigInteger product = BigInteger.ONE;
                for (int i = lo; i < hi; i++) {
                    product = product.multiply(
                            BigInteger.valueOf(i));
                }
                return product;
            }

            int mid = lo + n / 2;
            ProductTask left =
                    new ProductTask(lo, mid, threshold);
            left.fork();

            BigInteger right =
                    new ProductTask(mid, hi, threshold).compute();

            return left.join().multiply(right);
        }
    }

    static BigInteger factorial(int n, ForkJoinPool pool) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
        return pool.invoke(new ProductTask(1, n + 1, 3));
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println("factorial0=" +
                    factorial(0, pool));
            System.out.println("factorial1=" +
                    factorial(1, pool));
            System.out.println("factorial10=" +
                    factorial(10, pool));
            System.out.println("factorial20=" +
                    factorial(20, pool));

            boolean negativeRejected = false;
            try {
                factorial(-1, pool);
            } catch (IllegalArgumentException e) {
                negativeRejected = true;
            }
            System.out.println("negativeRejected=" +
                    negativeRejected);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 FactorialProductDemo.java
java FactorialProductDemo
~~~

Stdout:

~~~text
factorial0=1
factorial1=1
factorial10=3628800
factorial20=2432902008176640000
negativeRejected=true
~~~

**Tại sao `factorial(0)` trả 1?** Khoảng `[1,1)` rỗng, leaf khởi tạo product = `BigInteger.ONE` và vòng lặp không chạy. Đây là phần tử trung tính **đúng** của phép nhân.

**Giới hạn minh họa:** `n + 1` có thể overflow nếu `n == Integer.MAX_VALUE` và factorial rất lớn sẽ sử dụng nhiều CPU/RAM. Production phải validate ngưỡng kích thước và resource budget, không cho input bất kỳ tạo computation vô hạn thời gian hoặc làm cạn bộ nhớ.

## 18. Merge sort: base case trả về bằng cách sắp xếp tuần tự

Với thuật toán merge sort:

1. Nếu đoạn đủ nhỏ, gọi `Arrays.sort(array,lo,hi)`.
2. Nếu lớn, chia đôi thành hai đoạn không chồng lấn.
3. Sắp xếp hai nửa (có thể concurrent).
4. **Chỉ sau khi cả hai đã hoàn tất**, merge hai nửa đã sorted.
5. Parent trả về khi cả đoạn `[lo,hi)` sorted.

Sơ đồ:

~~~text
[7,2,9,1,0,-2,7,5]
          |
       split
      /     \
[7,2,9,1] [0,-2,7,5]
      \     /
     join + merge
          |
[-2,0,1,2,5,7,7,9]
~~~

Đoạn rỗng và một phần tử **đã sorted**, không cần tạo subtask.

## 19. Ví dụ 9 — Merge sort bằng RecursiveAction

Tạo `MergeSortBaseCaseDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class MergeSortBaseCaseDemo {
    static final class SortTask extends RecursiveAction {
        final int[] a, work;
        final int lo, hi, threshold;

        SortTask(
                int[] a, int[] work,
                int lo, int hi, int threshold) {
            this.a = a;
            this.work = work;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected void compute() {
            int n = hi - lo;

            if (n <= threshold) {
                Arrays.sort(a, lo, hi);
                return;
            }

            int mid = lo + n / 2;

            invokeAll(
                    new SortTask(
                            a, work, lo, mid, threshold),
                    new SortTask(
                            a, work, mid, hi, threshold));

            int i = lo;
            int j = mid;
            int k = lo;

            while (i < mid && j < hi) {
                work[k++] = (a[i] <= a[j])
                        ? a[i++]
                        : a[j++];
            }

            while (i < mid) {
                work[k++] = a[i++];
            }
            while (j < hi) {
                work[k++] = a[j++];
            }

            System.arraycopy(work, lo, a, lo, n);
        }
    }

    static void sort(int[] a, ForkJoinPool pool) {
        pool.invoke(new SortTask(
                a, new int[a.length], 0, a.length, 2));
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int[] values = {7, 2, 9, 1, 0, -2, 7, 5};
            int[] empty = {};
            int[] single = {42};

            sort(values, pool);
            sort(empty, pool);
            sort(single, pool);

            System.out.println("sorted=" +
                    Arrays.toString(values));
            System.out.println("empty=" +
                    Arrays.toString(empty));
            System.out.println("singleton=" +
                    Arrays.toString(single));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MergeSortBaseCaseDemo.java
java MergeSortBaseCaseDemo
~~~

Stdout:

~~~text
sorted=[-2, 0, 1, 2, 5, 7, 7, 9]
empty=[]
singleton=[42]
~~~

### 19.1. Vì sao có thể chia sẻ work[]?

`work` là một **scratch array** dùng chung, nhưng mỗi subtask chỉ ghi vào **vùng index của chính nó** khi merge. Các child tasks cùng cấp có khoảng `[lo,mid)` và `[mid,hi)` rời nhau; sau `invokeAll`, parent mới merge toàn đoạn lớn hơn. Không có hai tasks đồng thời ghi cùng phần tử `work[k]` theo cấu trúc này.

Nếu đổi logic để hai children cùng merge/ghi vào một vùng, việc dùng mảng chung sẽ thành data race. Đây không phải phép màu thread-safe của mảng; tính an toàn đến từ **partitioning và join**.

### 19.2. Memory và hiệu năng

- Đoạn nhỏ dùng `Arrays.sort` để tránh tạo tasks khi không cần.
- Cần cấp phát scratch array có kích thước mảng; đây là chi phí bộ nhớ `O(n)`.
- Merge theo đoạn cần chờ cả hai nửa sorted; nếu merge sớm sẽ sai.
- Threshold 2 là **để minh họa** chia cây rõ ràng, không phải tối ưu production.
- Với mảng nguyên thủy lớn, so sánh với `Arrays.parallelSort` (API hiện hành) và benchmark trước khi tự duy trì merge sort phức tạp.

## 20. Validate threshold và range trước khi compute

Một số bug gây đệ quy vô hạn không nằm trong công thức sum, mà do input:

- `threshold=0` hoặc âm.
- `lo > hi` dẫn đến size âm nên base case có thể chạy như thể đoạn rỗng.
- `hi > a.length` khiến leaf truy cập vượt mảng.
- `lo < 0` hoặc tham số không cùng mảng.
- `array == null`.
- Tính `mid` sai làm một subtask giống y hệt parent.
- Cứ `fork` cả hai tasks mà không join/propagate lỗi.

Một constructor guard có thể xác minh trước khi đưa task vào pool, thay vì chờ worker thread phát hiện lỗi sâu trong cây.

## 21. Ví dụ 10 — Từ chối threshold và range sai

Tạo `ThresholdGuardDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class ThresholdGuardDemo {
    static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;

        Task(int[] a, int lo, int hi, int threshold) {
            this.a = Objects.requireNonNull(a);
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;

            if (threshold < 1) {
                throw new IllegalArgumentException(
                        "threshold must be positive");
            }
            if (lo < 0 || hi < lo || hi > a.length) {
                throw new IndexOutOfBoundsException(
                        "invalid range");
            }
        }

        @Override
        protected Long compute() {
            int n = hi - lo;

            if (n <= threshold) {
                long s = 0;
                for (int i = lo; i < hi; i++) {
                    s += a[i];
                }
                return s;
            }

            int mid = lo + n / 2;
            if (!(lo < mid && mid < hi)) {
                throw new AssertionError(
                        "nondecreasing subproblem");
            }

            Task left = new Task(a, lo, mid, threshold);
            left.fork();

            return new Task(
                    a, mid, hi, threshold).compute()
                    + left.join();
        }
    }

    public static void main(String[] args) {
        boolean thresholdRejected = false;
        boolean rangeRejected = false;

        try {
            new Task(new int[]{1, 2, 3}, 0, 3, 0);
        } catch (IllegalArgumentException e) {
            thresholdRejected = true;
        }

        try {
            new Task(new int[]{1, 2, 3}, 2, 1, 1);
        } catch (IndexOutOfBoundsException e) {
            rangeRejected = true;
        }

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println("badThresholdRejected=" +
                    thresholdRejected);
            System.out.println("badRangeRejected=" +
                    rangeRejected);
            System.out.println("emptySum=" +
                    pool.invoke(new Task(
                            new int[0], 0, 0, 1)));
            System.out.println("sum=" +
                    pool.invoke(new Task(
                            new int[]{1, 2, 3, 4, 5}, 0, 5, 1)));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ThresholdGuardDemo.java
java ThresholdGuardDemo
~~~

Stdout:

~~~text
badThresholdRejected=true
badRangeRejected=true
emptySum=0
sum=15
~~~

**Vì sao không cố chạy ví dụ đệ quy vô hạn để chứng minh lỗi?** Nó có thể làm cạn stack/heap và khiến worker/test khó khôi phục. Thay vào đó, dùng constructor để **ngăn đầu vào lỗi từ đầu**, rồi test exception và invariant.

## 22. Hai mẫu compute sai thường gặp

### 22.1. Không bảo đảm phần việc giảm

**Mã sai có chủ ý, không chạy:**

~~~java
@Override
protected Long compute() {
    int n = hi - lo;
    if (n == 0) {
        return 0L;
    }
    int mid = lo + n / 2;
    // Với n=1, mid==lo, đoạn [mid,hi) vẫn dài 1!
    BadTask left = new BadTask(lo, mid);
    BadTask right = new BadTask(mid, hi);
    left.fork();
    return right.compute() + left.join();
}
~~~

Code trên minh họa lỗi logic, không phải class độc lập. Nếu `n==1`, recursive branch vẫn chạy và right subproblem **không giảm**, có thể lặp mãi. Sửa bằng base case `n<=1` hoặc threshold dương:

~~~java
int n = hi - lo;
if (n <= threshold) {
    return sequentialSum(lo, hi);
}
int mid = lo + n / 2;
~~~

`sequentialSum` ở đoạn minh họa này phải được định nghĩa trong class thật.

### 22.2. Fork rồi không join trước combine

**Mã sai có chủ ý, không chạy:**

~~~java
left.fork();
right.fork();
return left.result + right.result; // Các field có thể chưa sẵn sàng.
~~~

Đoạn minh họa không độc lập: không được giả định việc gọi `fork()` tương đương hoàn tất. Phải `join`/`invokeAll` hoặc cơ chế completion hợp lệ trước khi đọc kết quả. Với `RecursiveTask<V>`, cách dễ hiểu hơn là combine kết quả trả về của `join()` và compute trực tiếp.

### 22.3. Không tạo vòng chờ

Nếu task A chờ B nhưng B lại chờ A, không có đường hoàn tất hợp lệ. `ForkJoinTask.join()` được thiết kế cho các dependency **không tạo chu kỳ**. Một cây divide-and-conquer tự nhiên tránh vòng lặp vì mỗi parent chỉ chờ descendants, không có child nào đợi parent.

## 23. fork, compute, join và invokeAll: sự khác nhau

| Lệnh | Điều xảy ra |
| --- | --- |
| `child.fork()` | Sắp lịch child, thường trả ngay; child có thể chạy bởi worker khác |
| `child.compute()` | Gọi code tính của child **ngay trong thread hiện tại** |
| `child.join()` | Chờ child hoàn tất rồi lấy kết quả/ngoại lệ unchecked |
| `pool.invoke(root)` | Submit root bên ngoài và chờ kết quả |
| `pool.submit(root)` | Submit root, trả `ForkJoinTask<V>`/Future để lấy kết quả sau |
| `invokeAll(a,b)` | Fork và join các subtasks theo quy ước framework |

Với tree reduce, mẫu này thường rõ ràng:

~~~java
Task left = new Task(/* left range */);
Task right = new Task(/* right range */);
left.fork();
Result rightResult = right.compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
~~~

Đây là **mã giả dạng Java**, không phải class chạy được: `Task`, `Result`, `combine` phải được định nghĩa trong ứng dụng. Ý chính là **cho một nhánh có cơ hội chạy song song trong lúc worker hiện tại làm nhánh còn lại**, rồi join trước khi combine.

### 23.1. Vì sao không gọi pool.invoke cho từng child trong compute?

Trong một `ForkJoinTask`, ta đã chạy trong một pool. Gọi `fork()` cho child và `compute()` với child khác sử dụng cơ chế lập lịch đang hoạt động. Việc liên tục tạo `new ForkJoinPool(...)` bên trong mỗi `compute` sẽ làm nổ số lượng thread/pool và khó shutdown; **không** phải cách chia subtask đúng.

### 23.2. Task object không phải một công việc có thể fork lại tùy ý

Theo Javadoc `ForkJoinTask`, fork một task **nhiều lần** là misuse nếu nó chưa hoàn tất và chưa `reinitialize`. Trong cây đệ quy thông thường, hãy tạo **task object mới cho mỗi node**, không cho nhiều parents cùng fork một instance. Việc reuse/reinitialize là API nâng cao, không cần cho design base case cơ bản.

## 24. Gọi tác vụ từ bên ngoài pool: submit và Future

Chương trình chính có thể muốn bắt đầu một phép tính rồi làm việc khác trước khi nhận kết quả. Khi đó:

- `pool.invoke(task)` thích hợp nếu muốn chờ ngay và nhận kết quả.
- `pool.submit(task)` trả ForkJoinTask đã được submit; có thể dùng `get(timeout,unit)` và xử lý exception.
- `task.join()` trả kết quả và ném lỗi unchecked trực tiếp khi task lỗi; `get()` theo semantics Future, có `InterruptedException`, `ExecutionException` và timeout.
- Lệnh submit không thay đổi nghĩa của base case hoặc quy tắc split.

## 25. Ví dụ 11 — Submit root từ thread ngoài pool

Tạo `ExternalSubmitDemo.java`:

~~~java
import java.util.concurrent.*;

public class ExternalSubmitDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final long[] a;
        final int lo, hi;

        SumTask(long[] a, int lo, int hi) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= 2) {
                long s = 0;
                for (int i = lo; i < hi; i++) {
                    s += a[i];
                }
                return s;
            }

            int mid = lo + n / 2;
            SumTask left = new SumTask(a, lo, mid);
            left.fork();

            return new SumTask(a, mid, hi).compute()
                    + left.join();
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            long[] values = {1, 2, 3, 4, 5, 6, 7, 8};

            ForkJoinTask<Long> future =
                    pool.submit(new SumTask(
                            values, 0, values.length));

            System.out.println("submitResult=" +
                    future.get(5, TimeUnit.SECONDS));
            System.out.println("doneAfterGet=" +
                    future.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ExternalSubmitDemo.java
java ExternalSubmitDemo
~~~

Stdout:

~~~text
submitResult=36
doneAfterGet=true
~~~

**Quan trọng:** `future.get(5,SECONDS)` có thể block thread gọi. Nếu timeout, operation có thể vẫn chạy; timeout **không** chứng minh đã hủy task. Phải có chính sách cancellation/shutdown nếu chương trình cần giới hạn thời gian xử lý.

## 26. Quản lý ForkJoinPool và commonPool

Có hai lựa chọn chính:

**Pool dùng chung:**

~~~java
ForkJoinPool.commonPool();
~~~

**Pool tùy biến:**

~~~java
ForkJoinPool pool = new ForkJoinPool(2);
try {
    // submit/invoke root tasks.
} finally {
    pool.shutdown();
}
~~~

Đây là đoạn minh họa. `commonPool()` là pool chia sẻ được JDK quản lý; không tự shutdown commonPool từ code nghiệp vụ. Pool riêng hữu ích khi muốn kiểm soát mức song song hoặc tách workload khỏi các thành phần khác.

`ForkJoinPool` dùng chiến lược work-stealing để workers chia sẻ công việc. Điều đó **không** bảo đảm tốc độ tăng tuyến tính theo số threads; nếu dữ liệu nhỏ, bộ nhớ bị tranh chấp, hoặc combine quá đắt, thêm threads có thể không giúp.

### 26.1. Đừng tạo pool ở mỗi lần compute

Sai:

~~~java
protected Long compute() {
    ForkJoinPool other = new ForkJoinPool(8);
    // Submit children qua pool mới mỗi node...
    return 0L;
}
~~~

Đây là đoạn **cố ý sai về kiến trúc**, không phải chương trình mẫu. Một compute có thể sinh hàng nghìn nodes; tạo một pool mỗi node làm bùng threads và tài nguyên. Chọn pool một lần ở **boundary ứng dụng**, rồi submit root; các subtasks dùng `fork` trong pool đó.

### 26.2. Common pool có thể bị chia sẻ

Các cơ chế khác như một số parallel streams hoặc tác vụ CompletableFuture không có explicit Executor có thể dùng common pool theo cấu hình. Nếu bạn submit một workload nặng lên commonPool, nó có thể cạnh tranh tài nguyên với các thành phần khác. Khi cần isolation, dùng custom pool; không tùy tiện điều chỉnh parallelism toàn JVM mà không có đo đạc.

## 27. Ví dụ 12 — Pool với parallelism 2 và shutdown

Tạo `PoolLifecycleDemo.java`:

~~~java
import java.util.concurrent.*;

public class PoolLifecycleDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi;

        SumTask(int[] a, int lo, int hi) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;

            if (n <= 3) {
                long s = 0;
                for (int i = lo; i < hi; i++) {
                    s += a[i];
                }
                return s;
            }

            int mid = lo + n / 2;
            SumTask left = new SumTask(a, lo, mid);
            left.fork();

            return new SumTask(a, mid, hi).compute()
                    + left.join();
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int[] a = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

            System.out.println("parallelism=" +
                    pool.getParallelism());
            System.out.println("result=" +
                    pool.invoke(
                            new SumTask(a, 0, a.length)));
        } finally {
            pool.shutdown();
            System.out.println("terminated=" +
                    pool.awaitTermination(
                            5, TimeUnit.SECONDS));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 PoolLifecycleDemo.java
java PoolLifecycleDemo
~~~

Stdout:

~~~text
parallelism=2
result=55
terminated=true
~~~

`getParallelism()` là **target parallelism** của pool, không phải số threads luôn chạy tích cực tại mọi thời điểm. `shutdown()` ngăn submissions mới và cho các tasks đã submit hoàn tất theo policy; `awaitTermination` chờ pool kết thúc. Trên Java 17, mẫu shutdown/await được dùng để tránh phụ thuộc những API vòng đời mới hơn mà bài không cần.

**Lưu ý:** Nếu ứng dụng dùng pool làm service dài hạn, không tạo và shutdown cho mỗi request một cách máy móc. Pool có thể được giữ và tái sử dụng theo vòng đời service. Đừng shutdown common pool.

## 28. Khi một leaf ném ngoại lệ, chuyện gì xảy ra?

Nếu `compute()` ném một `RuntimeException` hoặc `Error`:

- Task có thể hoàn tất **bất thường**.
- `join()` thường rethrow exception unchecked.
- `pool.invoke(root)` cũng truyền lỗi unchecked cho caller.
- `Future.get()` dùng semantics `ExecutionException` với nguyên nhân từ task.
- Các sibling tasks có thể còn đang chạy hoặc bị hủy tùy đường đi; đừng giả định state đã rollback.
- Nếu leaf đã sửa shared mutable state, Fork/Join không bảo đảm tính atomic của toàn bộ job.

Không nên bắt lỗi trong leaf rồi trả số `0` như thể task hoàn tất nếu lỗi thực sự khiến kết quả mất tin cậy; làm thế khiến caller không nhận ra dữ liệu bị thiếu.

## 29. Ví dụ 13 — Ngoại lệ từ leaf được truyền ra root

Tạo `ExceptionPropagationDemo.java`:

~~~java
import java.util.concurrent.*;

public class ExceptionPropagationDemo {
    static final class CheckTask extends RecursiveTask<Integer> {
        final int[] a;
        final int lo, hi;

        CheckTask(int[] a, int lo, int hi) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Integer compute() {
            int n = hi - lo;

            if (n <= 2) {
                int sum = 0;
                for (int i = lo; i < hi; i++) {
                    if (a[i] == -99) {
                        throw new IllegalArgumentException(
                                "bad value");
                    }
                    sum += a[i];
                }
                return sum;
            }

            int mid = lo + n / 2;
            CheckTask left = new CheckTask(a, lo, mid);
            left.fork();

            return new CheckTask(a, mid, hi).compute()
                    + left.join();
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            boolean detected = false;

            try {
                pool.invoke(new CheckTask(
                        new int[]{1, 2, 3, -99, 5, 6, 7},
                        0, 7));
            } catch (RuntimeException e) {
                for (Throwable p = e;
                     p != null;
                     p = p.getCause()) {
                    if (p instanceof IllegalArgumentException
                            && "bad value".equals(p.getMessage())) {
                        detected = true;
                        break;
                    }
                }
            }

            System.out.println("badLeafPropagated=" +
                    detected);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ExceptionPropagationDemo.java
java ExceptionPropagationDemo
~~~

Stdout:

~~~text
badLeafPropagated=true
~~~

**Vì sao duyệt cause chain?** Tùy task chạy ở worker nào, ngoại lệ có thể được rethrow với stack trace hoặc wrapper khác nhau. Kiểm tra đúng **nguyên nhân nghiệp vụ** thay vì so toàn bộ stack trace hoặc message ngẫu nhiên của worker. Trong code production, đừng lạm dụng bắt mọi RuntimeException rồi bỏ qua; cần log context và thông báo thất bại tới nơi submit.

## 30. Hai vấn đề an toàn hay bị bỏ sót: shared state và blocking

### 30.1. Đúng base case chưa đủ để thread-safe

Ví dụ mỗi leaf tăng một shared `int total`:

~~~java
// Mã minh họa không an toàn nếu nhiều tasks cùng cập nhật total.
total += partialSum;
~~~

Đây là **race condition** nếu total là biến mutable được nhiều workers ghi không đồng bộ. Có nhiều cách đúng hơn:

- Để mỗi `RecursiveTask<V>` trả kết quả **riêng**, parent combine qua `join` (ưu tiên).
- Dùng `AtomicLong`/LongAdder chỉ khi thật sự cần đo/tổng hợp dùng chung và hiểu contention.
- Với `RecursiveAction` biến đổi mảng, chia **các ranges không chồng lấn**.
- Tạo scratch buffer theo quy tắc vùng riêng, như merge sort.
- Không sửa input arrays ở một thread khác trong lúc Fork/Join đang tính nếu kết quả đòi snapshot ổn định.

### 30.2. Vì sao không nên chặn ForkJoin workers bằng I/O?

Javadoc `ForkJoinTask` nêu task lý tưởng nên là tính toán CPU ngắn/vừa, hạn chế `synchronized`, blocking I/O và những wait không được pool quản lý. Nếu nhiều workers cùng chờ database/file/network, work-stealing không tự tạo thêm CPU hoặc kết thúc waits; pool có thể thiếu workers để làm việc khác.

Khi thật sự buộc dùng blocking synchronization, `ForkJoinPool.ManagedBlocker`/`managedBlock` có thể hỗ trợ một số tình huống bằng cơ chế bổ sung workers, nhưng đây là API nâng cao, không thay đổi nhiệm vụ tự thiết kế base case đúng.

Với workload I/O-bound dài, cân nhắc executor hoặc mô hình đồng thời phù hợp hơn. Với Java mới, virtual threads có thể là lựa chọn; nhưng Fork/Join vẫn hữu ích cho CPU-bound divide-and-conquer.

### 30.3. Cancellation không thay điều kiện dừng

Một lời gọi `ForkJoinTask.cancel(...)` đánh dấu cố gắng hủy, nhưng không nên xem nó như cách chữa thuật toán bị đệ quy vô hạn. Tác vụ CPU đang chạy có thể cần kiểm tra trạng thái hủy một cách có chủ ý; stop/cancel không bảo đảm rollback data mutation.

Để bảo đảm dừng, phải dùng **base case + progress invariant**, còn cancellation dùng cho yêu cầu vận hành riêng.

### 30.4. Đừng giữ khóa khi join cyclic dependency

Nếu parent chờ child trong khi child cần một lock mà parent giữ, có thể gây deadlock dù cấu trúc ranges đúng. Hạn chế shared locks và blocking operations trong `compute`. Không tạo dependency graph có chu kỳ; `join` phù hợp nhất với cây/DAG không có vòng chờ.

## 31. Sai lầm thường gặp

| Sai lầm | Hậu quả | Sửa như thế nào |
| --- | --- | --- |
| `threshold=0` và chỉ dừng n=0 | Đoạn n=1 không tiến triển | Validate threshold >=1, base n<=threshold |
| Không xét mảng rỗng | Truy cập a[0] gây lỗi | Base case n=0 có kết quả phù hợp |
| Gọi lại child với cùng [lo,hi) | Đệ quy không giảm | Split với lo<mid<hi |
| Dùng khoảng đóng sai | Trùng/mất phần tử | Dùng [lo,hi) thống nhất |
| Tính mid bằng (lo+hi)/2 | Có thể overflow | Dùng lo+(hi-lo)/2 |
| Base case còn gọi fork | Tạo task thừa/lỗi dừng | Return ngay từ leaf |
| Fork quá nhiều tasks nhỏ | Overhead queue/GC lớn | Tăng threshold sau benchmark |
| Threshold quá lớn | Khó tận dụng nhiều workers | Benchmark nhiều mức |
| Quên join trước combine | Đọc kết quả chưa sẵn sàng | join/invokeAll đúng |
| Fork hai nhánh rồi join nhánh đầu ngay | Có thể giảm cơ hội song song | Fork một nhánh, compute một nhánh |
| Dùng 0 làm max của dãy âm | Sai kết quả | OptionalInt/reject empty |
| Phép sum/product tràn số | Kết quả sai | long/BigInteger/Math.addExact |
| Ghi chung một vùng mảng | Data race | Mỗi task vùng riêng |
| Dùng shared mutable counter thường | Race condition | Trả kết quả hoặc atomic |
| Tạo pool trong mỗi compute | Thread/resource explosion | Pool một lần, fork children |
| Fork cùng instance nhiều lần | Misuse ForkJoinTask | Task mới mỗi node |
| Task A join B, B join A | Deadlock | Dependency acyclic |
| Blocking network/file I/O trong leaves | Starvation/hiệu năng kém | Tách I/O hoặc ManagedBlocker |
| Dùng join/get nhưng nuốt exception | Mất lỗi, kết quả không đáng tin | Propagate và xử lý ở boundary |
| Coi cancel như chắc chắn interrupt/rollback | Dữ liệu có thể đã thay đổi | Hủy có phối hợp |
| Benchmark khi có println trong compute | Timing vô nghĩa | Đo compute thật, không log mỗi node |

## 32. Checklist review compute trước khi merge code

**Đầu vào và bất biến**

1. `array`/source có được validate non-null?
2. `0 <= lo <= hi <= size` có được đảm bảo?
3. Threshold có **dương** và được ghi rõ là số phần tử/cost hay không?
4. Tập dữ liệu rỗng đã có định nghĩa kết quả đúng?
5. Kiểu số/precision có đáp ứng domain, có nguy cơ overflow?
6. Phần việc có thước đo tiến triển như `hi-lo`?

**Base case**

7. Base case `n <= threshold` có luôn đạt tới sau hữu hạn bước?
8. Leaf có thực hiện **trọn vẹn công việc tuần tự** trên đoạn?
9. Leaf có `return`, không rơi sang nhánh tạo subtasks?
10. Với n=0,1,threshold,threshold+1,odd có test chưa?
11. Kết quả trung tính có đúng với phép toán không?
12. Có tránh blocking I/O và locks kéo dài trong leaf?

**Recursive case**

13. `mid=lo+(hi-lo)/2` có không làm mất/trùng index?
14. Khi chia, `lo<mid<hi` có luôn đúng?
15. Hai children có nhỏ hơn cha và bao phủ toàn đoạn?
16. Mỗi child có data/parameter ownership rõ?
17. Có fork một nhánh và compute nhánh còn lại (hoặc invokeAll có chủ đích)?
18. Parent có join trước khi dùng kết quả?
19. Combine có tính toán đúng không phụ thuộc thứ tự lịch worker?
20. Có tránh dependency cycles và lặp fork cùng một instance?
21. Với mutation, các vùng ghi có không chồng lấn?

**Pool, lỗi và đo đạc**

22. Root có được submit vào đúng ForkJoinPool?
23. Có tránh tạo pool bên trong compute?
24. Pool riêng có shutdown khi hết vòng đời?
25. Có xử lý exception ở root hoặc Future.get?
26. Có cân nhắc failure/cancel của sibling tasks?
27. Có giới hạn memory, số tasks và data size?
28. Có benchmark threshold thực tế thay vì copy số từ ví dụ?
29. Có baseline tuần tự để so sánh?
30. Có thử ở nhiều parallelism/core counts?
31. Có tránh in log/time nondeterministic trong stdout test?
32. Có hiểu commonPool có thể bị workload khác chia sẻ?

## 33. Câu hỏi tự kiểm tra

**1.** Điều kiện dừng của compute trong ví dụ xử lý mảng là gì?  
**Đáp án:** `hi-lo <= threshold`, với threshold dương.

**2.** Vì sao cần threshold dương?  
**Đáp án:** Để khi buộc chia thì n>=2, từ đó hai children giảm kích thước nghiêm ngặt.

**3.** Độ đo tiến triển đơn giản nhất với [lo,hi) là gì?  
**Đáp án:** `n = hi-lo`.

**4.** Với [0,7) và threshold 3, root chia thế nào?  
**Đáp án:** [0,3) và [3,7); đoạn 4 phần tử lại chia tiếp.

**5.** Vì sao dùng half-open intervals?  
**Đáp án:** Dễ tính length, biểu diễn empty và tránh overlap/gap.

**6.** Với mảng rỗng, tổng trả gì?  
**Đáp án:** 0.

**7.** Với mảng rỗng, maximum trả gì?  
**Đáp án:** Không có max; có thể dùng OptionalInt.empty.

**8.** `RecursiveTask<Long>` khác `RecursiveAction` ở đâu?  
**Đáp án:** RecursiveTask compute trả Long; RecursiveAction compute trả void.

**9.** `child.fork()` có đồng nghĩa child đã xong?  
**Đáp án:** Không, chỉ sắp lịch.

**10.** `child.compute()` có tạo một Future mới?  
**Đáp án:** Không, gọi trực tiếp method trong thread hiện tại.

**11.** `child.join()` làm gì?  
**Đáp án:** Chờ child hoàn tất, trả kết quả hoặc lỗi unchecked.

**12.** Vì sao không fork rồi dùng kết quả ngay?  
**Đáp án:** Child có thể chưa tính xong.

**13.** Threshold=1 của 1024 phần tử tạo bao nhiêu leaf trong ví dụ chia đôi?  
**Đáp án:** 1024 leaves.

**14.** Threshold=128 tạo bao nhiêu leaf với n=1024?  
**Đáp án:** 8 leaves.

**15.** Có một threshold luôn nhanh nhất không?  
**Đáp án:** Không, phụ thuộc workload/CPU/pool; phải benchmark.

**16.** `Math.addExact` giúp gì?  
**Đáp án:** Ném ArithmeticException khi phép cộng tràn kiểu.

**17.** Vì sao factorial base case tích rỗng bằng 1?  
**Đáp án:** 1 là phần tử trung tính của phép nhân, và 0!=1.

**18.** Merge sort cần chờ lúc nào?  
**Đáp án:** Chờ hai nửa sorted trước khi merge.

**19.** Có thể để children cùng sửa một index array không?  
**Đáp án:** Không nếu không có đồng bộ và quy tắc ownership rõ.

**20.** Tác vụ ném RuntimeException thì root luôn trả kết quả mặc định không?  
**Đáp án:** Không, lỗi được truyền theo join/invoke/get.

**21.** ForkJoinPool có phù hợp cho blocking file/network I/O dài không?  
**Đáp án:** Không lý tưởng, dễ làm pool thiếu workers.

**22.** Có nên tạo ForkJoinPool mới ở mỗi node compute không?  
**Đáp án:** Không; một pool quản lý nhiều subtasks.

**23.** `commonPool()` có cần shutdown thủ công không?  
**Đáp án:** Không, đó là pool dùng chung do runtime quản lý.

**24.** `Future.get(timeout)` hết hạn có tự hủy task không?  
**Đáp án:** Không.

**25.** Có nên dùng shared int counter để cộng kết quả nhiều worker không?  
**Đáp án:** Không nếu không đồng bộ; ưu tiên mỗi task trả partial result.

**26.** Điều gì quyết định số splits trên một cây phân đôi?  
**Đáp án:** Kích thước ban đầu, threshold và quy tắc chia, không phải thứ tự scheduling.

**27.** Tại sao `lo+(hi-lo)/2` tốt hơn `(lo+hi)/2`?  
**Đáp án:** Tránh nguy cơ overflow khi cộng hai indexes lớn.

**28.** Reuse một ForkJoinTask instance để fork nhiều lần an toàn không?  
**Đáp án:** Không nên; cần task mới cho node mới.

**29.** Chứng minh tiến triển thế nào?  
**Đáp án:** Khi n>threshold>=1, chia thành hai lengths dương và đều nhỏ hơn n.

**30.** Ba bước cơ bản nhất của compute?  
**Đáp án:** **Base case rõ ràng → split có tiến triển → combine đúng sau join**.

## 34. Nguồn tham khảo chính thức

- [Oracle Java SE 26 — RecursiveTask](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveTask.html): compute trả kết quả, idiom fork một nhánh/tính một nhánh/join.
- [Oracle Java SE 26 — RecursiveAction](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveAction.html): compute không trả kết quả, ví dụ divide-and-conquer trên mảng.
- [Oracle Java SE 26 — ForkJoinTask](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork/join/invokeAll, exceptions, task size heuristic, tránh blocking và dependency cycles.
- [Oracle Java SE 26 — ForkJoinPool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, invoke/submit, commonPool, parallelism và shutdown.
- [Oracle Java SE 26 — ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): hỗ trợ đặc biệt cho một số trường hợp blocking.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancel.
- [Oracle Java SE 26 — OptionalInt](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalInt.html): biểu diễn kết quả max có thể không tồn tại.
- [Oracle Java SE 26 — AtomicInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): counters an toàn cho kiểm thử thống kê.
- [Oracle Java SE 26 — Math](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): addExact/multiplyExact và kiểm tra overflow.
- [Oracle Java SE 26 — BigInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html): phép nhân với độ lớn tùy ý.
- [Oracle Java SE 26 — Arrays](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html): sort/parallelSort để cân nhắc thuật toán đã được tối ưu.
- [Oracle Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): đối chiếu Java 17 của các chương trình chạy thực.
- [Oracle Java SE 17 — RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): đối chiếu chữ ký compute và invokeAll.
- [Oracle Java SE 7 — RecursiveTask](https://docs.oracle.com/javase/7/docs/api/java/util/concurrent/RecursiveTask.html): xác nhận nguồn gốc API từ Java 7, nhưng khuyến nghị hành vi hiện hành được đối chiếu bản Java mới.

**Tóm tắt trọng tâm:** `compute()` trong Fork/Join **không nên chia việc theo cảm tính**. Hãy chọn **đại lượng tiến triển** (ví dụ `hi-lo`), xác định **base case rõ** (ví dụ `n<=threshold` với threshold dương), chia thành những phần **nhỏ hơn và không chồng lấn**, làm công việc tuần tự ở leaf, rồi **join và combine đúng**. Kiểm thử mảng rỗng, một phần tử, sát threshold, dữ liệu âm, chia lẻ, lỗi và overflow; sau đó mới đo threshold/parallelism để quyết định tối ưu hiệu năng.