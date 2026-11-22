# Chọn ngưỡng phân chia Fork/Join theo chi phí thực tế

> **Mục tiêu bài học:** Chọn và kiểm chứng ngưỡng `threshold` (hay *cutoff/grain size*) để biết khi nào `RecursiveTask.compute()` nên **ngừng chia** và thực hiện công việc tuần tự. Ngưỡng tốt không phải một con số Java quy định sẵn: nó phụ thuộc vào chi phí thực tế của từng đơn vị dữ liệu, overhead tạo và điều phối task, khả năng chạy song song, độ lệch tải, locality bộ nhớ và môi trường chạy. Bài thuộc **Fork/Join** trong Java 7; các API `ForkJoinPool`, `ForkJoinTask`, `RecursiveTask` và `RecursiveAction` vẫn còn áp dụng trong Java 17+. Mã minh họa dùng JDK 17 và có lệnh biên dịch/chạy, kết quả cố định khi phù hợp; mọi số đo thời gian chỉ là quan sát trên một môi trường, không phải ngưỡng tối ưu toàn cục.

## 1. Threshold kiểm soát điều gì?

Fork/Join thực hiện một công việc lớn bằng cách **chia thành công việc con**, cho phép các worker xử lý song song rồi **kết hợp kết quả**. Một cấu trúc quen thuộc:

```text
Công việc [lo, hi)
       |
       | kích thước > threshold?
       |        \
       |         yes -> chia [lo,mid) + [mid,hi)
       |                    /              \
       |               task trái         task phải
       |                    \              /
       |                     kết hợp kết quả
       |
       no
       |
       v
  xử lý tuần tự trong một leaf task
```

Một `threshold` nhỏ tạo **nhiều leaf tasks** và **nhiều split/fork/join**. Một `threshold` lớn tạo **ít tasks hơn**, nhưng có thể không đủ công việc song song để bận các worker.

Ví dụ với mảng 16.384 phần tử và chia giữa đều đặn:

| Threshold theo số phần tử | Số leaf tasks | Số lần phân nhánh | Độ sâu chia tối đa |
| ---: | ---: | ---: | ---: |
| 1 | 16.384 | 16.383 | 14 |
| 64 | 256 | 255 | 8 |
| 1.024 | 16 | 15 | 4 |
| 16.384 | 1 | 0 | 0 |

Các con số này chính xác cho **thuật toán chia đôi và dữ liệu đó**, không phải đặc tính chung của mọi ForkJoinTask. Một bài toán chia không cân hoặc điều kiện dừng khác sẽ có số tasks khác.

### 1.1. Leaf work và task overhead

Gọi:

- `N`: tổng số đơn vị dữ liệu hoặc đơn vị việc (work units).
- `T`: threshold, số đơn vị công việc tối đa một leaf xử lý tuần tự.
- `L`: số leaf tasks (xấp xỉ `N/T` nếu work phân bố đều).
- `P`: số workers đủ điều kiện làm CPU work (không nhất thiết bằng toàn bộ số lõi vật lý).
- `c`: chi phí xử lý một đơn vị công việc ở leaf (đơn vị thời gian, có thể phụ thuộc dữ liệu).
- `h`: overhead trung bình cho split, task allocation, queue, fork, steal, join và scheduling.
- `m`: chi phí bộ nhớ/cache/GC/merge, có thể thay đổi theo workload và độ song song.

Một mô hình **trực giác**, không phải định luật chính xác:

\[
\text{time} \approx \frac{\text{useful work}}{\text{effective parallelism}}+
   \text{task overhead}+\text{memory/merge costs}+\text{load imbalance}.
\]

Giảm `T` có thể tăng parallelism nhưng cũng tăng số tasks và overhead. Tăng `T` có thể tiết kiệm overhead nhưng làm workers chờ leaf lớn. Hiệu năng tốt là **điểm cân bằng**, thường thay đổi theo input size và đặc điểm dữ liệu.

### 1.2. Chọn threshold theo **chi phí** thay vì chỉ chiều dài

Hai khoảng dữ liệu đều dài 1.000 phần tử có thể rất khác:
- Một khoảng chỉ cộng 1.000 số nguyên.
- Khoảng khác chạy thuật toán giải mã, parse JSON hoặc kiểm tra trạng thái nhiều lần trên mỗi phần tử.
- Một nhánh chạm cache CPU; nhánh khác truy cập RAM không liên tục.
- Một nhánh chứa các phần tử “khó” phải thực hiện nhiều vòng tính toán.

Với workload đồng nhất, `hi-lo` là proxy hữu ích. Với workload lệch, nên ước lượng **work units** bằng trọng số/cost estimator hoặc thiết kế chia theo chi phí thay vì số phần tử. `Threshold=4096` không tự nói gì về số microseconds nếu mỗi phần tử không có cost tương đương.

## 2. Vì sao quá nhiều tasks làm chậm?

ForkJoinPool dùng worker threads và work-stealing queues để phân phối các `ForkJoinTask`. Việc tạo, xếp hàng và hoàn tất mỗi task không miễn phí:

1. Cấp phát object task và lưu các tham số `lo`/`hi`.
2. Đưa một task vào queue bằng `fork()`.
3. Worker khác có thể tìm và “steal” task; có chi phí phối hợp.
4. Sau khi xử lý, caller hoặc worker phải `join()` và kết hợp kết quả.
5. Task objects phát sinh áp lực lên allocator và Garbage Collector.
6. Các leaf quá nhỏ có thể mất lợi thế locality, hoặc phải tranh cache lines.
7. Instrumentation/Atomic counters nếu đặt vào từng leaf có thể làm tăng contention và đổi kết quả benchmark.

Giả sử một leaf cộng 4 phần tử trong vài nanoseconds nhưng mất thêm overhead điều phối task đáng kể; tạo hàng chục nghìn tasks như vậy thường không có ích. Ngược lại, nếu một leaf xử lý hàng nghìn operations CPU phức tạp, overhead fork/join có thể chiếm tỷ lệ nhỏ hơn.

Không có giá trị overhead `h` cố định: nó thay đổi theo JDK/JIT, CPU, queue contention, thread load, memory topology, GC và độ dài của computation. **Đo trên workload thực**, không lấy một “giá task” từ bài viết rồi coi đúng cho mọi máy.

### 2.1. Quy tắc định tính

- **Leaf quá nhỏ** → tổng overhead/GC/stealing cao, nhiều tasks, thời gian có thể tệ hơn tuần tự.
- **Leaf vừa phải** → đủ công việc bên trong mỗi task để bù overhead, vẫn có nhiều leaf giúp work stealing.
- **Leaf quá lớn** → ít tasks hơn workers, một số workers nhàn rỗi, load imbalance cao.
- **N quá nhỏ** → thường không nên fork song song, dù `P` lớn.
- **N rất lớn nhưng bị giới hạn memory bandwidth** → thêm tasks/threads chưa chắc nhanh hơn.
- **Work thực tế có chi phí không đồng đều** → threshold theo số phần tử đơn thuần dễ tạo “straggler” kéo dài tail latency.

## 3. Mẫu `RecursiveTask` hiện hành và thứ tự fork/compute/join

Một pattern được dùng rộng rãi:

```java
@Override
protected Long compute() {
    int length = hi - lo;
    if (length <= threshold) {
        return computeSequentially(lo, hi);
    }
    int mid = lo + length / 2;
    Task left = new Task(lo, mid, threshold);
    Task right = new Task(mid, hi, threshold);
    left.fork();
    long rightResult = right.compute();
    return rightResult + left.join();
}
```

Đây là **snippet minh họa**, với `Task`, `lo`, `hi`, `threshold` và `computeSequentially` do bài toán cụ thể định nghĩa; không phải file Java đầy đủ. Thứ tự này:
- `fork` **một** nửa để worker khác có cơ hội lấy việc.
- Xử lý nửa còn lại trực tiếp bằng `compute()` trên worker hiện tại.
- `join` nửa đã fork khi cần kết quả.

Thường tốt hơn việc fork **cả hai** nửa rồi join cả hai vì có thể giảm overhead tạo queue và tránh worker hiện tại đứng chờ trong khi có công việc sẵn để làm.

### 3.1. Luôn bảo đảm thuật toán tiến tới leaf

- `threshold` phải dương, hoặc điều kiện dừng phải bảo đảm `hi-lo<=1`.
- Với range rỗng `[lo,lo)`, trả kết quả rỗng và **không tiếp tục chia**.
- Dùng `int mid = lo + (hi-lo)/2` để tránh overflow của `(lo+hi)/2`.
- Hai child ranges nên là `[lo,mid)` và `[mid,hi)`: không trùng, không bỏ sót.
- Không recursion vô hạn khi một child có kích thước 0 còn nhánh cha không giảm.
- Không chia cho mục đích “thêm song song” khi thuật toán con không độc lập hoặc có shared mutable state nguy hiểm.

### 3.2. `RecursiveTask` hay `RecursiveAction`?

`RecursiveTask<V>` trả một kết quả có thể join/merge (ví dụ sum). `RecursiveAction` phù hợp tác vụ không trả result (ví dụ xử lý một vùng mảng *độc lập*), nhưng tác dụng phụ vẫn phải thread-safe. Cả hai dùng nguyên tắc cutoff theo công việc thực, không phải hai thuật toán hoàn toàn khác nhau.

`ForkJoinPool.commonPool()` là pool chung có thể bị tải bởi workloads khác. Khi đo threshold, dùng **dedicated ForkJoinPool** với số workers xác định sẽ giúp bớt nhiễu. Đừng gọi `shutdown()` lên common pool như thể nó thuộc sở hữu của ứng dụng; nếu tạo custom pool thì quản lý lifecycle của pool đó.

## 4. Chương trình 1 — nhìn trực tiếp số task do threshold tạo ra

Chương trình dùng `RecursiveTask<Shape>` để đếm leaf, lần split, độ sâu và leaf lớn nhất. **Instrumentation trong kết quả** là để quan sát cấu trúc cây, **không dùng làm code benchmark thời gian**.

Lưu thành `ThresholdTreeShapeDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ThresholdTreeShapeDemo {
    record Shape(long sum, int leaves, int forks, int maxLeaf, int depth) {}

    static final class ShapeTask extends RecursiveTask<Shape> {
        final int[] values;
        final int lo, hi, threshold;
        ShapeTask(int[] values, int lo, int hi, int threshold) {
            this.values = values; this.lo = lo; this.hi = hi; this.threshold = threshold;
        }
        @Override protected Shape compute() {
            int length = hi - lo;
            if (length <= threshold) {
                long sum = 0;
                for (int i = lo; i < hi; i++) sum += values[i];
                return new Shape(sum, 1, 0, length, 0);
            }
            int mid = lo + length / 2;
            ShapeTask left = new ShapeTask(values, lo, mid, threshold);
            ShapeTask right = new ShapeTask(values, mid, hi, threshold);
            left.fork();
            Shape b = right.compute();
            Shape a = left.join();
            return new Shape(a.sum + b.sum, a.leaves + b.leaves,
                    a.forks + b.forks + 1,
                    Math.max(a.maxLeaf, b.maxLeaf),
                    1 + Math.max(a.depth, b.depth));
        }
    }
    public static void main(String[] args) {
        int[] values = new int[16_384];
        java.util.Arrays.fill(values, 1);
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            for (int threshold : new int[]{1, 64, 1024, 16384}) {
                Shape shape = pool.invoke(new ShapeTask(values, 0, values.length, threshold));
                System.out.printf("threshold=%d leaves=%d forks=%d depth=%d maxLeaf=%d sum=%d%n",
                        threshold, shape.leaves, shape.forks, shape.depth,
                        shape.maxLeaf, shape.sum);
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ThresholdTreeShapeDemo.java
java ThresholdTreeShapeDemo
```

Stdout đã kiểm chứng:

```text
threshold=1 leaves=16384 forks=16383 depth=14 maxLeaf=1 sum=16384
threshold=64 leaves=256 forks=255 depth=8 maxLeaf=64 sum=16384
threshold=1024 leaves=16 forks=15 depth=4 maxLeaf=1024 sum=16384
threshold=16384 leaves=1 forks=0 depth=0 maxLeaf=16384 sum=16384
```

**Giải thích:**
- Ngưỡng 1 buộc toàn bộ mảng tách đến từng phần tử: 16.384 leaf tasks, 16.383 internal splits, độ sâu 14.
- Ngưỡng 64 tạo 256 lá, một leaf tối đa 64 phần tử.
- Ngưỡng 1.024 tạo 16 lá, một leaf tối đa 1.024 phần tử.
- Ngưỡng bằng N không chia; task gốc trực tiếp tính tuần tự.

Bài này **không đo tốc độ** và **không nói 1.024 là tối ưu**; số leaf chỉ giúp dự đoán granularity. Do `Shape` objects được tạo/merge ở mọi leaf/internal node, chúng **làm lệch overhead thật** nếu dùng để benchmark một thuật toán chỉ cộng số.

### 4.1. Vì sao `leaves≈N/T` không phải công thức chính xác?

Chia đôi tạo các ranges có kích thước gần nhau nhưng không nhất thiết đúng bằng T. Ví dụ N không phải lũy thừa của 2; số lá là kết quả của cây phân chia, có thể hơi khác phép chia số học `ceil(N/T)`. Với mô hình chi phí trong planning, dùng `N/T` như **ước lượng**, còn production metrics nên đo theo thuật toán thực.

## 5. Chương trình 2 — bài toán sum với threshold và kiểm tra đúng

Một ví dụ gần với code thật dùng `RecursiveTask<Long>` để cộng 100.000 phần tử. Ở đây dùng `long` để tránh tràn số nguyên khi tính tổng 1..N.

Lưu thành `RangeSumForkJoinDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class RangeSumForkJoinDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final long[] data;
        final int lo, hi, threshold;
        final AtomicInteger leaves;
        SumTask(long[] data, int lo, int hi, int threshold, AtomicInteger leaves) {
            this.data = data; this.lo = lo; this.hi = hi;
            this.threshold = threshold; this.leaves = leaves;
        }
        @Override protected Long compute() {
            int length = hi - lo;
            if (length <= threshold) {
                leaves.incrementAndGet(); // Educational instrumentation, not for timing.
                long result = 0;
                for (int i = lo; i < hi; i++) result += data[i];
                return result;
            }
            int mid = lo + length / 2;
            SumTask left = new SumTask(data, lo, mid, threshold, leaves);
            SumTask right = new SumTask(data, mid, hi, threshold, leaves);
            left.fork();
            long rightResult = right.compute();
            return rightResult + left.join();
        }
    }
    public static void main(String[] args) {
        int n = 100_000;
        long[] data = new long[n];
        for (int i = 0; i < n; i++) data[i] = i + 1L;
        long expected = (long)n * (n + 1) / 2;
        AtomicInteger leaves = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long actual = pool.invoke(new SumTask(data, 0, n, 4096, leaves));
            System.out.println("sum=" + actual);
            System.out.println("sumMatches=" + (actual == expected));
            System.out.println("threshold=4096");
            System.out.println("leaves=" + leaves.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RangeSumForkJoinDemo.java
java RangeSumForkJoinDemo
```

Stdout đã kiểm thử:

```text
sum=5000050000
sumMatches=true
threshold=4096
leaves=32
```

Ngưỡng `4096` nghĩa là **mỗi leaf được phép tính tối đa 4096 phần tử**, không có nghĩa Java tạo đúng 4096 tasks. Với 100.000 phần tử chia đôi, ta nhận 32 lá, mỗi lá gần 3.125 phần tử. Tổng kết quả đúng `5.000.050.000` theo công thức cấp số cộng.

**Quan trọng khi đo:** `AtomicInteger leaves.incrementAndGet()` được đặt vào code chỉ để quan sát. Nếu dùng bản này đo throughput, atomic contention và kết cấu `Long` object có thể làm méo kết quả. Trong benchmark hiệu năng, nên **loại bỏ counters và side-effects không thuộc workload**, rồi đo cấu trúc task riêng khi cần.

## 6. Lập một mô hình chọn ngưỡng ban đầu

Chưa đo gì thì vẫn cần **một điểm khởi đầu để thử nghiệm**. Một heuristic thường dùng là tạo nhiều leaf hơn số workers một vài lần, ví dụ target `P*k` leaf tasks với k là hệ số “đủ job để steal” (2, 4, 8...). Với input đồng nhất và split cân:

\[
T_{\text{parallelism}} \approx \left\lceil \frac{N}{P\cdot k} \right\rceil.
\]

Đây là **heuristic tạo thí nghiệm**, không phải “công thức Java khuyến nghị” và không đảm bảo tốc độ. Ngưỡng vừa đủ để bù overhead có thể lớn hơn kết quả trên; việc chạy N nhỏ hoặc chi phí phần tử cực thấp có thể khiến chạy tuần tự nhanh hơn mọi cutoff Fork/Join.

### 6.1. Vì sao cần nhiều leaf hơn số workers?

Nếu P=4 mà chỉ có 2 leaf tasks, tối đa hai phần việc lớn có thể chạy cùng lúc; hai workers còn lại có thể rảnh. Nếu P=4 và có 16 leaf tasks, scheduler có dư nhiệm vụ để phân phối khi một worker xong sớm hoặc steal. Nhưng nếu tăng lên 100.000 leaf rất nhỏ, overhead vượt lợi ích.

`k` càng lớn chưa chắc tốt. Work stealing cần **đủ** granularity, không cần tạo task cho mọi phần tử.

### 6.2. Chương trình 3 — heuristic theo N và P, có kiểm tra input

Lưu thành `ThresholdSizingHeuristicDemo.java`:

```java
public class ThresholdSizingHeuristicDemo {
    static int thresholdFor(int n, int workers, int tasksPerWorker) {
        if (n <= 0 || workers <= 0 || tasksPerWorker <= 0)
            throw new IllegalArgumentException("positive inputs required");
        long desiredLeaves = (long) workers * tasksPerWorker;
        long ceil = ((long) n + desiredLeaves - 1) / desiredLeaves;
        return (int) Math.max(1, Math.min((long) n, ceil));
    }
    static int countLeaves(int n, int threshold) {
        if (n <= threshold) return 1;
        int left = n / 2;
        return countLeaves(left, threshold) + countLeaves(n - left, threshold);
    }
    public static void main(String[] args) {
        int t = thresholdFor(100_000, 4, 4);
        System.out.println("heuristicThreshold=" + t);
        System.out.println("modelLeaves=" + countLeaves(100_000, t));
        System.out.println("smallThreshold=" + thresholdFor(10, 4, 4));
        System.out.println("smallLeaves=" + countLeaves(10, thresholdFor(10, 4, 4)));
        try {
            thresholdFor(100, 0, 4);
        } catch (IllegalArgumentException expected) {
            System.out.println("zeroWorkers=REJECTED");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ThresholdSizingHeuristicDemo.java
java ThresholdSizingHeuristicDemo
```

Stdout đã chạy:

```text
heuristicThreshold=6250
modelLeaves=16
smallThreshold=1
smallLeaves=10
zeroWorkers=REJECTED
```

Với N=100.000, P=4, k=4: 100.000/(4×4)=6.250 phần tử/leaf, tạo 16 lá với split đều. Trường hợp N=10 thì threshold clamp về 1; code mô hình vẫn có 10 leaf, không cố “phát minh” thêm phần tử để đủ 16 tasks. Input invalid P=0 bị từ chối thay vì chia cho 0.

**Đừng copy mặc định P=4/k=4 vào production như chân lý.** P phải phản ánh workers thực sự dành cho workload, k phải thử nghiệm. Ngay cả khi `Runtime.getRuntime().availableProcessors()` báo nhiều CPUs, container quotas, CPU contention, cgroup limits và những ứng dụng khác dùng `commonPool` có thể khiến khả năng song song hữu dụng thấp hơn.

## 7. “Chi phí thực tế” không tỷ lệ đơn giản với số phần tử

Trong sum long[] đơn giản, 100 phần tử gần như đồng nhất về công việc. Nhưng một bộ xử lý tài liệu có thể gặp:
- 100 bản ghi ngắn chỉ kiểm tra một flag;
- 100 bản ghi dài parse hàng nghìn ký tự;
- các phần tử lệch theo cấu trúc cây và độ sâu recursion;
- một nhóm dữ liệu đã ở cache và nhóm khác gây cache misses;
- computation có sớm thoát (early return), nên cùng số phần tử nhưng work khác.

Nếu chỉ tách mảng ở midpoint `(lo+hi)/2`, hai nửa có số phần tử bằng nhau nhưng **tổng cost rất lệch**. Work stealing chỉ giúp khi có đủ task còn chia được; một leaf “quá nặng” còn lại có thể giữ toàn bộ request dù nhiều workers rảnh.

### 7.1. Đơn vị công việc và prefix cost

Nếu ước lượng chi phí mỗi phần tử `w[i]` là số nguyên dương, có thể tính prefix sums:

\[
C(0)=0,\qquad C(i+1)=C(i)+w[i].
\]

Tổng work ước lượng trong `[lo,hi)` là `C(hi)-C(lo)`. Một cách chia cân là chọn mid sao cho `C(mid)-C(lo)` gần một nửa tổng work. Khi đó **threshold tính theo work units**, không chỉ chiều dài phần tử.

Lưu ý cost estimator cũng có overhead. Nếu muốn tính chính xác `w[i]` phải parse/đọc hết input trước thì khả năng lời lỗ của bước tiền xử lý cần được đo. Với data nhỏ hoặc cost đồng đều, việc đo prefix/weighted split có thể tốn hơn lợi ích.

### 7.2. Ví dụ tải lệch

Xét trọng số:

```text
index :   0  1  2  3 | 4   5   6   7
weight:   1  1  1  1 | 32  32  32  32
```

Chia theo số phần tử tại index 4 tạo work 4 và 128; một bên quá nhẹ, bên kia quá nặng. Chọn split gần một nửa **tổng 132 work units** tại index 6 tạo 68 và 64 — cân hơn nhiều.

### 7.3. Chương trình 4 — chia theo prefix work cost

Lưu thành `WeightedWorkThresholdDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class WeightedWorkThresholdDemo {
    static int[] prefix(int[] weight) {
        int[] p = new int[weight.length + 1];
        for (int i = 0; i < weight.length; i++) p[i + 1] = p[i] + weight[i];
        return p;
    }
    static int bestSplit(int[] prefix, int lo, int hi) {
        int desired = prefix[lo] + (prefix[hi] - prefix[lo]) / 2;
        int at = Arrays.binarySearch(prefix, lo + 1, hi, desired);
        if (at < 0) at = -at - 1;
        at = Math.max(lo + 1, Math.min(hi - 1, at));
        int before = at - 1;
        if (before <= lo) return at;
        int a = Math.abs((prefix[at] - prefix[lo]) * 2 - (prefix[hi] - prefix[lo]));
        int b = Math.abs((prefix[before] - prefix[lo]) * 2 - (prefix[hi] - prefix[lo]));
        return b < a ? before : at;
    }
    static long work(int index, int units) {
        long x = index * 0x9E3779B97F4A7C15L + 13L;
        for (int k = 0; k < units * 20; k++) {
            x ^= x << 13;
            x ^= x >>> 7;
            x ^= x << 17;
        }
        return x;
    }
    static final class CostTask extends RecursiveTask<Long> {
        final int[] weight, prefix;
        final int lo, hi, budget;
        CostTask(int[] weight, int[] prefix, int lo, int hi, int budget) {
            this.weight = weight; this.prefix = prefix;
            this.lo = lo; this.hi = hi; this.budget = budget;
        }
        @Override protected Long compute() {
            if (hi - lo <= 1 || prefix[hi] - prefix[lo] <= budget) {
                long result = 0;
                for (int i = lo; i < hi; i++) result += work(i, weight[i]);
                return result;
            }
            int mid = bestSplit(prefix, lo, hi);
            CostTask a = new CostTask(weight, prefix, lo, mid, budget);
            CostTask b = new CostTask(weight, prefix, mid, hi, budget);
            a.fork();
            long right = b.compute();
            return a.join() + right;
        }
    }
    public static void main(String[] args) {
        int[] weight = {1, 1, 1, 1, 32, 32, 32, 32};
        int[] p = prefix(weight);
        int countMid = weight.length / 2;
        int costMid = bestSplit(p, 0, weight.length);
        System.out.println("countSplitWork=" + p[countMid] + "/" + (p[8] - p[countMid]));
        System.out.println("costSplitWork=" + p[costMid] + "/" + (p[8] - p[costMid]));
        long sequential = 0;
        for (int i = 0; i < weight.length; i++) sequential += work(i, weight[i]);
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long parallel = pool.invoke(new CostTask(weight, p, 0, weight.length, 32));
            System.out.println("sumMatches=" + (parallel == sequential));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 WeightedWorkThresholdDemo.java
java WeightedWorkThresholdDemo
```

Stdout đã kiểm chứng:

```text
countSplitWork=4/128
costSplitWork=68/64
sumMatches=true
```

Ở đây mỗi phần tử thực hiện số vòng `work(...)` tỷ lệ với trọng số; dùng cùng công thức trong đường tuần tự và Fork/Join. Kết quả sum khớp. Chênh lệch 4/128 và 68/64 là **ước lượng work**, không phải đo thời gian thực của hai nhánh. Do loop ngắn và CPU/JIT, runtime thực không nhất thiết tỷ lệ chính xác 4:128.

### 7.4. Giới hạn của bestSplit trong ví dụ

- Trọng số ở ví dụ **dương**, prefix tăng đơn điệu nên `Arrays.binarySearch` có thể chọn split theo cost.
- Code dùng `int` vì fixture rất nhỏ; ở dữ liệu lớn, prefix có thể tràn int, nên dùng `long[]` và kiểm tra overflow.
- Một phần tử đơn lẻ có work cost rất lớn không thể chia nhỏ hơn index; cần thuật toán tách phần tử hoặc chấp nhận straggler.
- Ước lượng cost có thể sai: input phân bố thay đổi hoặc JIT/cache khác; đo lại trên data đại diện.
- Việc xây prefix và binary search có overhead, chỉ nên làm nếu skew đủ lớn để bù lại.

## 8. Từ overhead và chi phí đơn vị tới một “cửa sổ ngưỡng”

Giả sử ước lượng overhead bình quân để tách/điều phối một leaf-equivalent là `h` nanoseconds, còn xử lý một phần tử là `c` nanoseconds. Nếu muốn một leaf có công việc ít nhất gấp `q` lần overhead:

\[
T_{\text{overhead}} \gtrsim \frac{q\cdot h}{c}.
\]

Đây chỉ là cách suy nghĩ về **minimum useful work**, không phải công thức được JDK bảo đảm. Đồng thời để có khoảng `P*k` leaf jobs cho work cân:

\[
T_{\text{parallelism}} \lesssim \frac{N}{P\cdot k}.
\]

Đôi khi hai mong muốn mâu thuẫn: leaf đủ lớn để bù overhead thì số leaf lại quá ít. Khi đó **không có cutoff thần kỳ** làm song song có lợi cho input nhỏ — chạy tuần tự có thể là lựa chọn tốt nhất.

### 8.1. Cách dùng thực tế

1. Đo một leaf chạy tuần tự với dữ liệu đại diện để ước lượng “công việc hữu ích”.
2. Đo hiệu ứng tăng task count, allocation, GC và stealing trên cùng môi trường.
3. Chọn vài ngưỡng làm thí nghiệm sao cho số leaf và cost mỗi leaf đều hợp lý.
4. Test nhiều input sizes và số workers, không chỉ một N duy nhất.
5. Khi có nhiều workloads, cân nhắc **chọn ngưỡng theo nhóm dữ liệu** hoặc estimated cost.
6. Luôn có fallback serial với input quá nhỏ và kiểm tra đúng kết quả.

### 8.2. Đừng lấy một nanosecond “h” duy nhất rồi áp mọi nơi

Chi phí queue/steal của một task có thể khác khi pool rảnh, khi tất cả workers bận, khi có nhiều requests đồng thời hoặc khi GC/CPU throttling xảy ra. Mô hình `h/c` hữu ích để định hướng, nhưng con số phải kiểm chứng bằng benchmark và profiling đại diện.

## 9. Chương trình 5 — heuristic kết hợp đủ việc song song và cost mỗi leaf

Một chính sách ban đầu có thể chọn threshold lớn hơn hai ràng buộc:
- Có đủ leaf để khoảng `P*k` công việc có thể phân tán.
- Mỗi leaf mang ít nhất một lượng **estimated useful work** cho phép bù overhead.

Ví dụ `minUsefulWork=10_000` chỉ là **tham số đầu vào để minh họa mô hình**, không phải một số cố định Java khuyến nghị. Khi một phần tử có cost 1 unit, cần khoảng 10.000 phần tử mới đạt 10.000 units; nếu cost 100 units, cần khoảng 100 phần tử, nên cutoff có thể nhỏ hơn.

Lưu thành `AdaptiveThresholdPolicyDemo.java`:

```java
public class AdaptiveThresholdPolicyDemo {
    record Inputs(int n, int workers, int targetTasksPerWorker,
                  int estimatedCostPerItem, int minimumUsefulWork) {}
    static int choose(Inputs in) {
        if (in.n() <= 0 || in.workers() <= 0 || in.targetTasksPerWorker() <= 0
                || in.estimatedCostPerItem() <= 0 || in.minimumUsefulWork() <= 0)
            throw new IllegalArgumentException("positive inputs");
        long desiredTasks = (long) in.workers() * in.targetTasksPerWorker();
        long byParallelism = ((long) in.n() + desiredTasks - 1) / desiredTasks;
        long byWork = ((long) in.minimumUsefulWork() + in.estimatedCostPerItem() - 1)
                / in.estimatedCostPerItem();
        long wanted = Math.max(byParallelism, byWork);
        return (int) Math.min((long) in.n(), Math.max(1L, wanted));
    }
    public static void main(String[] args) {
        Inputs cheap = new Inputs(100_000, 4, 4, 1, 10_000);
        Inputs costly = new Inputs(100_000, 4, 4, 100, 10_000);
        System.out.println("cheapThreshold=" + choose(cheap));
        System.out.println("costlyThreshold=" + choose(costly));
        System.out.println("costlierNeedsNoLargerThreshold=" +
                (choose(costly) <= choose(cheap)));
        System.out.println("guardOne=" +
                choose(new Inputs(1, 4, 4, 1, 10_000)));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 AdaptiveThresholdPolicyDemo.java
java AdaptiveThresholdPolicyDemo
```

Stdout đã kiểm chứng:

```text
cheapThreshold=10000
costlyThreshold=6250
costlierNeedsNoLargerThreshold=true
guardOne=1
```

Ở input N=100.000, P=4, target 4 leaf/worker, `byParallelism=6.250`. Công việc rẻ 1 unit/item đặt `byWork=10.000` nên chọn 10.000. Công việc đắt 100 units/item đặt `byWork=100` nên chọn 6.250. Thông điệp là **một threshold tính theo số phần tử có thể đổi khi cost mỗi phần tử đổi**, không phải công thức này đã tìm được ngưỡng nhanh nhất.

### 9.1. Những lưu ý khi đưa heuristic lên production

- `estimatedCostPerItem` phải được đo/hiệu chỉnh từ telemetry hoặc profile, không đoán “100” vì nhìn code có 100 dòng.
- `minimumUsefulWork` cần được gắn với overhead thực tế (và môi trường CPU), không cố định ở mọi node.
- Nếu hai điều kiện khó cùng thỏa, chạy tuần tự.
- Nếu data skew, estimate cost theo range/record, không giả định mỗi item cùng cost.
- Dùng kiểu số rộng cho phép nhân `N`, `P`, `k` và tổng work; tránh overflow.
- Ước lượng có thể giảm chất lượng khi task chứa locks, I/O hoặc external calls; Fork/Join không tự chữa được blocking workloads.
- Reconfiguration threshold khi requests đang chạy phải tránh trạng thái chia không nhất quán. Thông thường lấy “snapshot” threshold lúc khởi tạo root task và truyền xuống mọi children.

## 10. Đo hiệu năng đúng: warmup, input đại diện, nhiều lượt

Chọn threshold bằng cảm giác hoặc từ một lần `System.nanoTime()` thường dễ sai do:
- JVM JIT compilation và warmup;
- CPU frequency scaling, nhiệt độ, power modes;
- GC và áp lực heap;
- CPU load bởi tiến trình khác, container quotas;
- fork/join threads mới khởi tạo khi lần chạy đầu;
- khả năng cache và data locality thay đổi giữa các lượt;
- OS scheduler và work stealing không quyết định tuyệt đối;
- data distributions khác nhau, đôi khi input ngắn **không đáng fork**.

### 10.1. Quy trình tối thiểu có trách nhiệm

1. Tạo input **bất biến, đại diện** và chuẩn bị ngoài vùng đo.
2. Tính **baseline tuần tự** và kiểm tra checksum/result của mọi threshold.
3. Dùng cùng pool size, số workers và hardware cho các cấu hình.
4. **Warm up** JIT/classes/task path trước khi lấy số liệu.
5. Đo nhiều lần sau warmup; dùng median và xem độ phân tán, không chỉ min.
6. Ngăn JIT bỏ công việc bằng cách sử dụng kết quả (blackhole/volatile) và tránh constant folding không đúng.
7. Không cấp phát/khởi tạo input trong timing nếu muốn đo chỉ compute.
8. Tránh log/Atomic counters/metrics ở từng leaf trong benchmark chính.
9. Kiểm tra GC, allocation rate, CPU saturation và run-to-run variance.
10. Lặp trên nhiều N, nhiều cost/element, dữ liệu skewed và nhiều giá trị P.
11. Chạy nhiều JVM forks/iterations; nếu kết luận cho production, nên dùng một harness chuyên dụng như **JMH**.
12. Kiểm chứng trên môi trường triển khai thật (CPU limits, NUMA/cache, JDK version), không coi máy developer là chuẩn.

### 10.2. Tại sao cần so với tuần tự?

Một ngưỡng `T>=N` thực hiện **một** leaf trong ForkJoinPool; nó vẫn phải submit/invoke root task, nên khác một vòng for trực tiếp ngoài pool. Nếu workload quá nhỏ, mọi threshold Fork/Join có thể chậm hơn vòng for thuần. Quyết định thiết kế đôi khi là “**không chia, không vào pool**” thay vì “tìm một T cực lớn”.

### 10.3. Ngưỡng đo nên theo cấp số nhân trước

Đừng thử lần lượt threshold 1024, 1025, 1026 khi chưa biết khu vực tốt. Bắt đầu các mốc phân biệt như 256, 2048, 16384, 131072; sau khi thấy một vùng tiềm năng, thử dày hơn và nhiều JVM forks. Mục tiêu là tìm **vùng hiệu năng ổn định** chứ không tối ưu noise ở một điểm ngẫu nhiên.

## 11. Chương trình 6 — benchmark đơn giản, minh bạch giới hạn

Đây là một harness chỉ dùng JDK, để bạn chạy ngay và quan sát cutoff tác động ra sao với công việc **rẻ (0 rounds)** và **đắt hơn (24 rounds)**. Nó:
- tạo `int[]` ngoài thời gian đo;
- dùng một `ForkJoinPool(4)`;
- warmup hai lần/cấu hình;
- đo năm lần bằng `System.nanoTime()`, báo median ms;
- so với checksum tuần tự;
- lưu kết quả vào `volatile blackhole`;
- không dùng Atomic counters ở mỗi leaf;
- báo ngưỡng nhanh nhất **trong lần đo này**.

**Giới hạn:** đây là một demo đo nhanh cho bài học, chưa phải benchmark nghiêm ngặt. Thời gian rất ngắn (cỡ dưới 1 ms) đặc biệt nhiễu; thứ tự các thresholds cố định, chỉ một JVM process, không kiểm soát GC/scheduler. **Không dùng nó thay cho JMH khi quyết định production threshold**.

Lưu thành `ThresholdMeasurementDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ThresholdMeasurementDemo {
    static volatile long blackhole;
    static final int[] THRESHOLDS = {256, 2048, 16384, 131072};
    static final int N = 120_000;

    static long element(int value, int rounds) {
        long x = value * 0x9E3779B97F4A7C15L + 17;
        for (int j = 0; j < rounds; j++) {
            x = Long.rotateLeft(x ^ (x >>> 19), 13) * 0xBF58476D1CE4E5B9L + j;
        }
        return x;
    }

    static long sequential(int[] data, int rounds) {
        long total = 0;
        for (int value : data) total += element(value, rounds);
        return total;
    }

    static final class Worker extends RecursiveTask<Long> {
        final int[] data;
        final int lo, hi, threshold, rounds;
        Worker(int[] data, int lo, int hi, int threshold, int rounds) {
            this.data = data; this.lo = lo; this.hi = hi;
            this.threshold = threshold; this.rounds = rounds;
        }
        @Override protected Long compute() {
            int length = hi - lo;
            if (length <= threshold) {
                long total = 0;
                for (int i = lo; i < hi; i++) total += element(data[i], rounds);
                return total;
            }
            int mid = lo + length / 2;
            Worker left = new Worker(data, lo, mid, threshold, rounds);
            Worker right = new Worker(data, mid, hi, threshold, rounds);
            left.fork();
            long a = right.compute();
            return a + left.join();
        }
    }

    static double medianMillis(ForkJoinPool pool, int[] data,
            int threshold, int rounds, long expected) {
        for (int i = 0; i < 2; i++) {
            long observed = pool.invoke(new Worker(data, 0, data.length, threshold, rounds));
            if (observed != expected) throw new AssertionError("warmup mismatch");
            blackhole = observed;
        }
        long[] samples = new long[5];
        for (int i = 0; i < samples.length; i++) {
            long start = System.nanoTime();
            long observed = pool.invoke(new Worker(data, 0, data.length, threshold, rounds));
            samples[i] = System.nanoTime() - start;
            if (observed != expected) throw new AssertionError("mismatch");
            blackhole = observed; // Make result observable.
        }
        Arrays.sort(samples);
        return samples[samples.length / 2] / 1_000_000.0;
    }

    public static void main(String[] args) {
        int[] data = new int[N];
        for (int i = 0; i < data.length; i++) data[i] = i + 1;
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            for (int rounds : new int[]{0, 24}) {
                long expected = sequential(data, rounds);
                double fastest = Double.POSITIVE_INFINITY;
                int fastestThreshold = -1;
                System.out.println("rounds=" + rounds);
                for (int threshold : THRESHOLDS) {
                    double med = medianMillis(pool, data, threshold, rounds, expected);
                    System.out.printf(java.util.Locale.ROOT,
                            "threshold=%d medianMs=%.3f correct=true%n", threshold, med);
                    if (med < fastest) {
                        fastest = med;
                        fastestThreshold = threshold;
                    }
                }
                System.out.println("fastestObservedThreshold=" + fastestThreshold);
            }
            System.out.println("allChecksPassed=true");
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ThresholdMeasurementDemo.java
java ThresholdMeasurementDemo
```

**Ví dụ stdout được ghi lại từ một lần chạy trên JDK 17** (đây là số đo **biến thiên giữa các lần chạy**, không phải expected output cố định):

```text
rounds=0
threshold=256 medianMs=0.211 correct=true
threshold=2048 medianMs=0.032 correct=true
threshold=16384 medianMs=0.025 correct=true
threshold=131072 medianMs=0.030 correct=true
fastestObservedThreshold=16384
rounds=24
threshold=256 medianMs=0.594 correct=true
threshold=2048 medianMs=0.560 correct=true
threshold=16384 medianMs=0.580 correct=true
threshold=131072 medianMs=1.996 correct=true
fastestObservedThreshold=2048
allChecksPassed=true
```

**Chỉ những điều sau có ý nghĩa ổn định trong chương trình:**
- `correct=true` cho mọi threshold nếu implementation đúng.
- `allChecksPassed=true` khi không có lỗi.
- Có hai nhóm rounds và bốn thresholds, nhưng **các số median và fastestObservedThreshold có thể thay đổi**.
- Ở rounds=0, task creation rất nhỏ có thể là overhead lớn tương đối.
- Ở rounds=24, việc tính toán nhiều hơn thường có thêm cơ hội song song.
- Threshold >=N tạo một leaf tính trên worker, **không hoàn toàn bằng** vòng for sequential trên caller.

### 11.1. Cách diễn giải số liệu đúng

Trong ví dụ này, threshold=16.384 nhanh nhất **cho rounds=0**, còn threshold=2.048 nhanh nhất **cho rounds=24**. Điều này minh họa rằng **cost/element thay đổi thì cutoff tốt có thể thay đổi**. Nhưng chênh lệch 0.025 vs 0.030 ms nhỏ và nhiễu; một lần chạy không đủ làm căn cứ production. Đừng tuyên bố 16.384 hay 2.048 là “tối ưu Java 17”.

### 11.2. Vì sao dùng `volatile blackhole`?

Nếu benchmark tính kết quả nhưng không bao giờ sử dụng, JIT có thể tối ưu bỏ hoặc đơn giản hóa computation. Việc so sánh với expected và gán vào `volatile` làm kết quả quan sát được, giảm rủi ro dead-code elimination trong demo. Nó **không** biến harness này thành một benchmark nghiêm ngặt bằng JMH; compiler vẫn có nhiều tối ưu hợp lệ khác.

### 11.3. Tại sao chọn median?

Median của năm lượt giảm ảnh hưởng của một lần pause/outlier so với mean đơn lẻ, nhưng không loại hết JIT, CPU frequency, GC, drift hay bias do thứ tự test. JMH với forks/warmup/measurement riêng, kết quả phân phối và độ lệch sẽ đáng tin hơn.

### 11.4. Nếu “ngưỡng nhanh nhất” đảo vị trí ở lần chạy kế

Đó là chuyện có thể xảy ra, nhất là khi chênh lệch nhỏ. Kết luận cần dựa trên **vùng ổn định** qua nhiều iterations, nhiều input kích thước và JVM forks. Nếu hai threshold tương đương về hiệu năng trong sai số, ưu tiên phương án đơn giản, dễ đọc, ít allocation hơn và phù hợp p95/p99 latency.

## 12. Benchmark production với JMH: điều nên biết

**JMH (Java Microbenchmark Harness)** là dự án OpenJDK dùng để xây benchmark JVM, cho phép cấu hình warmup, measurement, forks, threads, benchmark modes và state. Nó thường được dùng để so sánh các cutoff trên JVM; muốn chạy cần thêm JMH dependencies/build plugin từ dự án riêng.

Một benchmark dự định triển khai nên:
- Dùng `@State(Scope.Benchmark)` để chuẩn bị input bên ngoài hot loop.
- Test `@Param` cho các threshold candidate, n, work cost, data distribution.
- Dùng `@Benchmark` cho đường compute; tách baseline serial.
- Có `@Warmup`, `@Measurement`, `@Fork`, chế độ `AverageTime` hoặc `Throughput` phù hợp.
- Dùng `Blackhole.consume(result)`, không in log trong body benchmark.
- Ghi lại JDK version/flags, CPU model, pool size, RAM/GC, OS và CPU quotas.
- Lặp lại với input skewed và input lớn hơn cache, không chỉ một array ở L1/L2.
- Đo allocation, GC, CPU utilization, steal counts nếu có, tránh instrumentation làm lệch hot path.
- Với throughput server, đo **end-to-end p95/p99 latency dưới concurrent load**, không chỉ microbenchmark latency một task.

**Không kèm code JMH giả chạy với javac thuần**: các annotation/classes JMH không thuộc `java.base`; cần dependency được khai báo trong dự án. Những sáu chương trình JDK-only trong bài đã được kiểm thử độc lập; phần này là hướng dẫn xây benchmark nâng cao, không giả định máy đọc đã cài JMH.

## 13. Chọn ngưỡng theo **thể loại bottleneck**

### 13.1. Compute-bound, cost đều

Khi mỗi phần tử thực hiện phép biến đổi CPU nặng và độc lập, có cơ hội tăng throughput khi chia đủ leaf cho các workers. Với nhiều CPU cores, cutoff nhỏ hơn một chút có thể hữu ích, **nếu** leaf vẫn lớn so với overhead. Đo speedup thực để xác định.

### 13.2. Memory bandwidth-bound

Với vòng lặp chỉ đọc/cộng `long[]`, CPU có thể bị giới hạn tốc độ đọc bộ nhớ trước khi tận dụng hết cores. Thêm workers có thể saturate bandwidth, làm tăng cache misses và memory traffic chứ không tăng throughput. Một threshold lớn hơn hoặc chạy tuần tự có thể tốt hơn.

### 13.3. Cache locality và false sharing

Hai leaf truy cập các vùng mảng không chồng lấn thường có locality tốt hơn so với nhiều threads sửa xen kẽ một vùng nhỏ. Nếu mỗi task ghi vào shared counters cạnh nhau trên cache line, false sharing/cache coherence có thể làm chậm dù không có data race. Thiết kế data ownership theo contiguous ranges, giảm shared writes và kiểm tra bằng profiler.

### 13.4. Work không cân bằng

Một vài leaf nặng có thể kéo tail completion. Giảm threshold giúp task nặng có cơ hội tiếp tục chia, nhưng tạo overhead hơn. Khi cost skew cực lớn, mô hình cost-aware split hoặc dynamic chunks hiệu quả hơn việc chỉ giảm T vô hạn.

### 13.5. Merge/combine quá đắt

Nếu mỗi internal node thực hiện merge O(length) hoặc copy mảng, tổng combine cost có thể lớn. Threshold không chỉ ảnh hưởng leaf cost mà còn **số tầng merge**, temporary allocations và cache. Đo full algorithm, không chỉ leaf function. Merge sort Fork/Join là ví dụ: threshold tốt phụ thuộc cả sorting leaf và merging.

### 13.6. Blocking I/O trong `compute()`

ForkJoinPool chủ yếu tối ưu workload chia nhỏ CPU-bound; blocking I/O hoặc chờ lock vô hạn trên worker có thể làm thiếu threads. Nếu phải block trong ForkJoin task, nghiên cứu `ForkJoinPool.managedBlock(ManagedBlocker)` khi phù hợp, hoặc tách I/O khỏi CPU pool. **Đừng “chữa” blocking bằng cách hạ threshold** rồi tạo thêm hàng nghìn blocked tasks.

### 13.7. Các requests cạnh tranh cùng pool

Một request duy nhất trong pool 4 workers khác với 100 concurrent requests cùng dùng commonPool. Nếu tất cả đều sinh rất nhiều tasks, queue contention/GC có thể tăng. Tối ưu threshold dưới **throughput và tail latency của ứng dụng thật**, không chỉ speedup microbenchmark một request.

## 14. Vì sao `Runtime.availableProcessors()` không là số worker tối ưu mặc định?

`Runtime.getRuntime().availableProcessors()` cho biết estimate số processors hiện có với JVM, nhưng:
- môi trường container có CPU quotas/limits khác nhau;
- hyperthreading không tương đương cores vật lý;
- JVM có thể nhận CPU count biến động theo cấu hình runtime;
- một phần CPU bị hệ thống và các tasks khác dùng;
- pool size và concurrent workloads quyết định số worker hữu dụng.

Do đó `P` trong heuristic nên đại diện **parallelism được cấp cho workload này**, thường là `ForkJoinPool.getParallelism()` của custom pool, chứ không đương nhiên bằng tổng CPU machine. Nếu sản phẩm vận hành với CPU throttling, phải benchmark trong đúng cgroup/container limits.

### 14.1. Common pool vs custom pool

`ForkJoinPool.commonPool()` tiện nhưng là pool chung; việc đo bằng commonPool có thể bị hoạt động ngoài bài toán làm nhiễu. Custom pool:
- phù hợp khi muốn cố định P trong benchmark;
- có thể tách resource giữa services/subsystems;
- cần lifecycle rõ: `shutdown()`/`awaitTermination` khi hoàn tất các tasks;
- không nên tạo/đóng một pool mới **cho từng leaf** hoặc mỗi phần tử.

Các chương trình trong bài tạo **một pool** cho toàn bộ demo, rồi gọi `pool.shutdown()` trong finally. Vì `pool.invoke` đã đợi tasks hoàn tất, không còn pending work khi shutdown trong các chương trình này.

## 15. Một threshold cố định có thể làm sai phép tính floating-point

Khi kết hợp kết quả, thuật toán không chỉ phải nhanh mà còn **đúng theo contract mong muốn**. Với số nguyên `long`, phép cộng có tính kết hợp theo bit-pattern modulo 2^64 của Java khi overflow; nhưng ứng dụng vẫn phải xét overflow theo yêu cầu nghiệp vụ. Với `double`, phép cộng **không kết hợp** do làm tròn. Ngưỡng thay đổi cây phân chia và thứ tự cộng nên có thể thay đổi kết quả số học.

### 15.1. Chương trình 7 — thứ tự tổng hợp làm đổi kết quả double

Lưu thành `FloatingPointOrderDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class FloatingPointOrderDemo {
    static final class Sum extends RecursiveTask<Double> {
        final double[] data;
        final int lo, hi, threshold;
        Sum(double[] data, int lo, int hi, int threshold) {
            this.data = data; this.lo = lo; this.hi = hi; this.threshold = threshold;
        }
        @Override protected Double compute() {
            if (hi - lo <= threshold) {
                double sum = 0.0;
                for (int i = lo; i < hi; i++) sum += data[i];
                return sum;
            }
            int mid = lo + (hi - lo) / 2;
            Sum left = new Sum(data, lo, mid, threshold);
            Sum right = new Sum(data, mid, hi, threshold);
            left.fork();
            double b = right.compute();
            return left.join() + b;
        }
    }

    public static void main(String[] args) {
        double[] data = {1e16, 1.0, -1e16, 1.0};
        double sequential = 0;
        for (double x : data) sequential += x;
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            double pairwise = pool.invoke(new Sum(data, 0, data.length, 2));
            double unsplit = pool.invoke(new Sum(data, 0, data.length, 4));
            System.out.println("sequential=" + sequential);
            System.out.println("threshold2=" + pairwise);
            System.out.println("threshold4=" + unsplit);
            System.out.println("sameResult=" + (sequential == pairwise));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FloatingPointOrderDemo.java
java FloatingPointOrderDemo
```

Stdout đã kiểm chứng:

```text
sequential=1.0
threshold2=0.0
threshold4=1.0
sameResult=false
```

Vì `1e16+1` làm tròn về `1e16` trong double, tổng theo hai nửa khác với tổng tuần tự theo thứ tự đầu vào. Cả hai đều là kết quả của phép cộng floating-point theo trình tự khác nhau. Nếu cần độ tái lập chính xác, cần quy định reduction order, dùng kỹ thuật compensated summation/kiểu dữ liệu phù hợp, hoặc đánh giá sai số theo tolerance nghiệp vụ; đừng dùng equality `==` như một phép kiểm tổng quát cho kết quả double song song.

### 15.2. Khi thay threshold, phải kiểm chứng gì?

- Mỗi phần tử có được xử lý đúng một lần?
- Range [lo,hi) không trùng hoặc bị bỏ sót?
- Phép merge có thực sự associative theo dữ liệu/business semantics không?
- Có side effects phụ thuộc thứ tự không?
- Có data races trên shared arrays/maps/counters?
- Có overflow khi cộng hoặc tính prefix work?
- Có cần deterministic order/reproducibility không?
- Có giữ invariant trong các trường hợp N=0, N=1, threshold=1, threshold>=N?
- Có phát hiện exception của leaf ở `join` thay vì nuốt lỗi và trả partial result?

Một threshold chỉ được gọi là “tốt” khi **tính đúng được đảm bảo**, rồi mới so sánh tốc độ.

## 16. Khi nào nên đổi thuật toán thay vì đổi threshold?

Có những tình huống hạ/tăng T không thể giải quyết:
- Vòng lặp tuần tự đã nhanh hơn vì input rất nhỏ.
- Thông lượng bị chặn bởi memory bandwidth.
- Một phần tử duy nhất chiếm gần hết work và không thể chia.
- Thuật toán con có lock làm tuần tự hóa mọi workers.
- Tất cả tasks đều block I/O hoặc chờ external resources.
- Combine/merge có độ phức tạp quá cao.
- Dữ liệu phân phối rất lệch; chia theo index không cân.
- Pool concurrency bị giới hạn bởi quota, những services khác hoặc nested parallelism.

Lúc này nên cân nhắc tối ưu thuật toán, layout dữ liệu, cache, batching, tránh allocation, tách I/O, thay partition strategy hoặc chạy sequential fallback. Không cần ép Fork/Join cho mọi đoạn mã chỉ vì CPU có nhiều lõi.

## 17. Đo dữ liệu nào để ra quyết định?

Một bảng thực nghiệm nên có ít nhất:

| Nhóm thông số | Cần ghi |
| --- | --- |
| Workload | N, phân bố dữ liệu, cost/record, input cache locality |
| Threshold | T, số leaf ước lượng, số tasks thực tế nếu đo ngoài hot path |
| Pool | P, custom/common, số requests đồng thời |
| Correctness | checksum hoặc đối chiếu baseline tuần tự, error tolerance |
| Time | median/p95, throughput, số JVM forks/warmup/measurements |
| CPU | utilization, throttling, context switches |
| Memory | allocation, GC pauses, cache misses, bandwidth |
| Stealing | queue/steal metrics chỉ như **chẩn đoán**, không xem là objective độc lập |
| Môi trường | JDK, GC, heap, OS, CPU, cgroup limits, JVM flags |
| Quyết định | vùng threshold có hiệu năng ổn định, fallback serial, ngày benchmark |

### 17.1. Dùng metrics của ForkJoinPool đúng cách

`ForkJoinPool.getStealCount()` cung cấp một ước lượng tổng số tasks được steal; `getQueuedTaskCount()` là ước lượng số task đang chờ trong queues; `getActiveThreadCount()`/`getRunningThreadCount()` là các metrics trạng thái. Chúng có giá trị để **chẩn đoán** thiếu việc, tranh chấp hay imbalance, nhưng không thể trực tiếp suy “steals càng nhiều càng tốt” hoặc “steals càng ít càng tốt”. Số đo có thể thay đổi khi threads xử lý song song và thường không phải ảnh chụp nhất quán tuyệt đối.

Đừng gọi mọi method lấy metrics tại **mỗi leaf** trong timed benchmark. Hãy lấy snapshot ở mức coarse-grained hoặc dùng profiling riêng để tránh instrument overhead thay đổi threshold winner.

### 17.2. False sharing và shared counters

Nếu các tasks cùng cập nhật một `AtomicLong` cho từng phần tử, điểm nghẽn có thể chuyển từ leaf computation sang cache coherence và CAS contention. Hãy xử lý local trong mỗi leaf rồi combine kết quả; nếu cần telemetry, sampling/LongAdder có thể giảm contention nhưng vẫn có overhead. Đừng thêm counters rồi quy kết speedup giảm là do Fork/Join threshold đơn thuần.

## 18. Những lỗi tuning rất thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chọn T=1 cho mọi thuật toán | Tạo gần một task mỗi item, overhead/GC cực cao | Đo granularity, tăng cutoff |
| Chọn T=N/P và coi là tối ưu | Ít việc để steal, load imbalance | Thử k>1, đo skew |
| Hard-code “threshold=1000 luôn nhanh” | Workload/hardware thay đổi | Benchmark theo input/cost/P |
| Chia cả hai nửa bằng fork | Thêm queue work không cần thiết | Fork một nửa, compute nửa kia, join |
| Threshold=0 với recursion không guard | Chia mãi trên range 1, stack overflow | Enforce T>=1, base case |
| Chia theo index khi cost rất lệch | Stragglers | Weighted/cost-aware partitioning |
| Dùng Atomic counters trong benchmark | Contention che mất hiệu ứng thật | Tách instrumentation khỏi timed path |
| Chỉ đo lần chạy đầu | JIT/pool initialization bias | Warmup, nhiều iterations/forks |
| Chỉ đo 1 N và 1 pool size | Không tổng quát | Matrix nhiều N, P, data distributions |
| Bỏ baseline sequential | Song song có thể chậm hơn | So đo đường tuần tự trực tiếp |
| Không consume result | JIT có thể đơn giản hóa | Validate checksum, Blackhole/volatile |
| Chỉ nhìn median nhỏ hơn vài microseconds | Noise tạo winner giả | Đo phương sai/vùng ổn định |
| Mỗi request tạo pool mới | Thread/resource churn | Reuse dedicated pool |
| Dùng commonPool rồi đo dưới tải không kiểm soát | Nhiễu và contention | Isolate hoặc đo tải thật có ghi nhận |
| Chặn I/O trong leaf | Worker starvation | Tách I/O, managedBlock nếu cần |
| Không xử lý data races | Kết quả không đúng, khó debug | Immutable ranges/local accumulators |
| Coi floating-point sum associative | T khác có thể cho kết quả khác | Reduction policy/tolerance |
| Chỉ tính số phần tử | Không thấy cost variance | Cost model, profiles, weighted split |
| Không đo GC/cache | Tệ hơn dù CPU leaf nhanh | Profiling và full-workload test |
| Coi một lần đo JDK17 là kết luận cho mọi máy | Thiếu độ tin cậy | JMH và triển khai theo môi trường |

## 19. Quy trình thực hành chọn threshold cho một workload thật

### Bước 1 — định nghĩa correctness và dữ liệu

Đặt test cases N=0, 1, 100, 10.000, 1.000.000 (nếu phù hợp), dữ liệu đồng nhất và dữ liệu lệch, input có nhiều giá trị biên, phân phối hiện tại của hệ thống. Xây baseline tuần tự, thêm checksum và kiểm tra overflow/precision.

### Bước 2 — xác định đơn vị cost

Với sum một mảng, work unit là phần tử. Với parse documents, có thể là tổng bytes, số tokens, độ sâu cây hoặc các chỉ số proxy. Nếu work units không đồng đều, đo cost per partition và cân nhắc weighted split.

### Bước 3 — thiết kế pool và phân chia đúng

Chọn `RecursiveTask` hoặc `RecursiveAction`, đảm bảo base case tiến tới leaf, một child fork một child compute, return/join có cấu trúc; không dùng mutable shared state thiếu synchronization. Chọn custom pool với P có giới hạn trong test.

### Bước 4 — chọn candidate thresholds

Dùng heuristic `ceil(N/(P*k))` với k=2..8 như điểm khởi đầu, kết hợp minimum useful work. Thử dải cấp số nhân quanh vùng này, có cả `T>=N` và baseline tuần tự; không bỏ trường hợp không fork.

### Bước 5 — benchmark có kiểm soát

Warm up, đo nhiều iterations, consume result, so correctness, tránh load phụ, ghi GC/CPU/JDK/OS. Đừng chỉ nhìn một số nanoTime. Với production, dùng JMH và full application benchmark.

### Bước 6 — đọc nguyên nhân

Nếu T thấp tạo task count rất cao, allocation/GC lớn: tăng T. Nếu T cao có ít leaf hơn P, workers idle và critical path dài: giảm T hoặc chia theo cost. Nếu mọi T tương đương, ưu tiên đơn giản và ít overhead; nếu sequential thắng, không fork cho input này.

### Bước 7 — chọn chính sách thay vì hằng số mù

Chính sách có thể là:
- Với `N < smallInputCutoff`, chạy tuần tự.
- Với N lớn và cost đều, chọn threshold từ bảng đo theo N/P.
- Với cost khác biệt, dùng estimated work units hoặc weighted partitioning.
- Với resource contention/cgroup, giới hạn P và đặt trần số outstanding tasks.
- Ghi lại giả định, monitor performance drift và benchmark lại khi JVM/hardware/input đổi.

### Bước 8 — regression và deployment

Đảm bảo output vẫn đúng, memory/GC không tăng bất thường, p95/p99 của request không xấu đi và application không starvation khi nhiều workloads cùng chạy. Không chỉ triển khai vì một microbenchmark tối ưu vài phần trăm trên máy dev.

## 20. Checklist code review

1. Base case có `threshold>=1` và xử lý range 0/1 không?
2. Split có bảo đảm `lo<=mid<=hi` và hai child tiến tới nhỏ hơn?
3. Có dùng `mid = lo + (hi-lo)/2` tránh overflow?
4. Leaf work có độc lập hoặc đồng bộ hóa đúng không?
5. Có fork một child rồi compute child còn lại?
6. Có join mọi child đã fork, propagate exception đúng?
7. Có tính đúng khi N nhỏ hơn T và khi T>=N?
8. Có checksum/baseline tuần tự cho mọi candidate threshold?
9. Phép merge có associative/commutative đủ cho business semantics?
10. Floating-point precision có được kiểm soát?
11. Có tránh contention/Atomic counters trong timed hot path?
12. Có xác định cost thực tế của mỗi phần tử/leaf không?
13. Nếu cost skew, có tránh split theo count một cách ngây thơ?
14. Có tránh cost estimator đắt hơn lợi ích của weighted splitting?
15. Có xét GC/allocation từ số tasks tăng?
16. Có xét cache locality/false sharing?
17. Có phân biệt CPU-bound và memory-bandwidth-bound?
18. Có tránh blocking I/O trên worker threads?
19. Pool size P có phản ánh deployment CPU/quotas không?
20. Custom pool có được reuse và shutdown đúng ownership?
21. Có so sánh với đường chạy tuần tự trực tiếp, không chỉ một root task?
22. Benchmark có warmup, đo nhiều lượt và consume result?
23. Có ghi lại JDK/CPU/GC/heap/OS/input/P?
24. Có test nhiều N và nhiều cost/element?
25. Có đo variation, không chỉ min của một lần?
26. Có dùng JMH khi cần kết luận production?
27. Có xét throughput và p95/p99 latency dưới concurrent requests?
28. Có đo steals/queues như metrics chẩn đoán thay vì chỉ tiêu?
29. Có tránh hard-code threshold không nguồn gốc?
30. Có benchmark lại khi hardware/JVM/workload thay đổi?

## 21. Câu hỏi ôn tập kèm đáp án

**Câu 1.** Threshold trong `RecursiveTask` có nghĩa gì?  
**Đáp án:** Điều kiện dừng chia; khi work đủ nhỏ thì xử lý tuần tự trong leaf.

**Câu 2.** T nhỏ luôn nhanh hơn?  
**Đáp án:** Không, task overhead/GC/stealing có thể vượt useful work.

**Câu 3.** T lớn luôn nhanh hơn vì ít tasks?  
**Đáp án:** Không, có thể thiếu parallelism và tạo stragglers.

**Câu 4.** Vì sao không có ngưỡng “chuẩn Java 7”?  
**Đáp án:** Cost/element, pool size, data distribution, hardware và JIT khác nhau.

**Câu 5.** N=16.384, T=64 theo chia đôi tạo bao nhiêu leaf trong demo?  
**Đáp án:** 256, với thuật toán chia đều cụ thể.

**Câu 6.** P=4, k=4, N=100.000 cho heuristic T bao nhiêu?  
**Đáp án:** 6.250, chỉ là điểm thí nghiệm.

**Câu 7.** `N/T` có luôn đúng số leaf?  
**Đáp án:** Không; đây là ước lượng khi chia đều.

**Câu 8.** Vì sao fork một child và compute một child?  
**Đáp án:** Worker hiện tại vẫn làm việc thay vì queue cả hai rồi chờ; có thể giảm overhead.

**Câu 9.** Vì sao không dùng `AtomicInteger` ở mỗi leaf khi benchmark?  
**Đáp án:** Contention và allocation/instrumentation làm lệch thời gian.

**Câu 10.** Cost/element không đồng đều thì sao?  
**Đáp án:** Dùng cost-aware split/weighted work units nếu lợi ích vượt overhead của estimator.

**Câu 11.** 4 phần tử nhẹ và 4 nặng, split midpoint cân cost không?  
**Đáp án:** Không; ví dụ tạo 4/128 work units, weighted split tạo 68/64.

**Câu 12.** Vì sao benchmark phải có baseline tuần tự?  
**Đáp án:** Để phát hiện input quá nhỏ hoặc memory-bound khiến Fork/Join chậm hơn for loop.

**Câu 13.** Chạy năm lần và median có đảm bảo kết quả đáng tin production?  
**Đáp án:** Không; cần nhiều forks, warmup, môi trường/đầu vào đại diện; dùng JMH.

**Câu 14.** Thay threshold có đổi output `double` không?  
**Đáp án:** Có thể, vì phép cộng floating-point không kết hợp chính xác.

**Câu 15.** `getStealCount()` tăng có luôn là tốt?  
**Đáp án:** Không; nhiều steals có thể là dư việc hoặc overhead cao.

**Câu 16.** `Runtime.availableProcessors()` có chắc bằng số workers hữu dụng?  
**Đáp án:** Không; containers, hyperthreads và workloads khác ảnh hưởng.

**Câu 17.** Vì sao `System.nanoTime` được dùng đo?  
**Đáp án:** Đo duration giữa hai mốc, tránh trộn thời gian tường có thể thay đổi.

**Câu 18.** Blocking I/O trong leaf xử lý bằng giảm T?  
**Đáp án:** Không; cần thiết kế concurrency/I/O đúng hoặc `managedBlock` khi phù hợp.

**Câu 19.** Khi T>=N, có nghĩa benchmark đúng bằng tuần tự trực tiếp?  
**Đáp án:** Không, vẫn có chi phí pool invoke/root task.

**Câu 20.** Khi nào nên chọn serial fallback?  
**Đáp án:** Work quá nhỏ, chi phí task không bù, hoặc kết quả đo cho thấy tuần tự tốt hơn.

## 22. Bài tập thực hành

### Bài A — Kiểm chứng số tasks

Chạy `ThresholdTreeShapeDemo` với thresholds 2, 32, 512 và N=16.384. Tính trước số leaf/splits rồi đối chiếu.

### Bài B — Thử T khác với sum

Chạy `RangeSumForkJoinDemo`, thay 4096 bằng 256 và 16.384. Mỗi lần phải giữ `sumMatches=true`; đối chiếu số leaves. Không dùng AtomicInteger leaf counter để kết luận tốc độ.

### Bài C — Heuristic song song

Chạy `ThresholdSizingHeuristicDemo` với P=2,4,8, k=2,4,8. Quan sát số leaf; giải thích vì sao đây chưa phải lựa chọn tối ưu.

### Bài D — Weighted split

Chạy `WeightedWorkThresholdDemo`, đổi trọng số 32 thành 4 và 256. So sánh work chia theo count midpoint và theo prefix cost; phân tích khi nào estimator đáng tiền.

### Bài E — Chi phí rẻ vs đắt

Chạy `AdaptiveThresholdPolicyDemo`, thay estimatedCostPerItem=2,20,200. Giải thích vì sao threshold theo phần tử có thể giảm khi work mỗi item tăng.

### Bài F — Benchmark theo dữ liệu thật

Chạy `ThresholdMeasurementDemo` ba lần; ghi lại median và fastestObservedThreshold cho rounds 0 và 24. Đánh dấu các kết quả khác nhau là **noise/distribution effects**, không tự sửa thuật toán vì một lần thay winner.

### Bài G — So với baseline tuần tự

Mở rộng `ThresholdMeasurementDemo` để đo `sequential(data,rounds)` trong cùng điều kiện warmup/measurement, rồi tính speedup. Cân nhắc chi phí pool.invoke ở ngưỡng T>=N.

### Bài H — JMH

Tạo dự án benchmark riêng có JMH, `@Param` cho ngưỡng và `@Fork` nhiều JVM. So kết quả với harness đơn giản và giải thích JIT/pool/GC bias.

### Bài I — Floating-point correctness

Chạy `FloatingPointOrderDemo`. Giải thích vì sao threshold2=0.0 và threshold4=1.0; đề xuất contract kiểm tra sai số phù hợp.

### Bài J — Memory bandwidth

Thay công việc giả lập trong `ThresholdMeasurementDemo` bằng vòng chỉ đọc/cộng `long[]` rất lớn và thử nhiều P. Quan sát liệu thêm workers có bão hòa bandwidth.

### Bài K — Production scenario

Thiết kế một bộ xử lý hàng triệu records có chi phí parse lệch: đặt telemetry, cost estimation, thresholds theo nhóm input, fallback serial và p95/p99 evaluation.

### Bài L — Regression test

Viết test cho N=0,1,2,threshold=1,threshold>=N; xác minh task không recursion vô hạn, không bỏ sót, không trùng ranges, và exceptions được propagate.

## 23. Tài liệu Java chính thức và công cụ đo

- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, parallelism, pool lifecycle và diagnostic counters.
- [Java SE 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork, join, invoke, computation design.
- [Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): return result và split/merge.
- [Java SE 17 — RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): task không trả result.
- [Java SE 17 — ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): phối hợp blocking khi cần.
- [Java SE 17 — Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): processors estimate.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): thời gian monotonic để đo elapsed.
- [OpenJDK — JMH](https://openjdk.org/projects/code-tools/jmh/): framework đo microbenchmark cho JVM.

**Kết luận:** Chọn threshold Fork/Join là bài toán **định lượng giữa useful work và task overhead**, không phải chọn một số phần tử tùy ý. Trước hết bảo đảm thuật toán đúng và task tree tiến tới base case; sau đó ước lượng cost/leaf, đảm bảo đủ jobs cho P workers nhưng không quá nhiều; đo nhiều threshold, kích thước input và workloads với baseline tuần tự và warmup đầy đủ. Nếu cost lệch, cân nhắc weighted split; nếu work quá nhỏ hoặc memory-bound, đừng ngại chạy tuần tự. Chỉ công bố “ngưỡng tốt” cùng điều kiện benchmark và tái kiểm chứng khi môi trường triển khai thay đổi.
