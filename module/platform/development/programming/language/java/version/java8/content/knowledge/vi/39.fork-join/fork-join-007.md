# Chia hạt công việc theo chi phí thực tế với Fork/Join trong Java

## 1. Mục tiêu: không chỉ chia đều số phần tử

`ForkJoinPool` và `ForkJoinTask` trong `java.util.concurrent` giúp phân rã một bài toán CPU thành các phần việc có thể xử lý song song, kết hợp kết quả và tận dụng cơ chế **work-stealing**. Khi dùng `RecursiveTask<V>` hoặc `RecursiveAction`, một quyết định quan trọng nằm trong phương thức `compute()`: **đến mức nào thì dừng chia và xử lý tuần tự?**

Quyết định này gọi là lựa chọn **độ hạt** (*task granularity* hoặc *grain size*). “Mỗi task xử lý 1.000 phần tử” chỉ hợp lý khi chi phí của từng phần tử gần giống nhau. Nếu một phần tử cần hàng triệu phép tính còn phần tử khác chỉ cần một phép cộng, chia đôi số phần tử chưa chắc chia đôi khối lượng công việc.

Bài học tập trung vào chủ đề **“Chia hạt công việc theo chi phí thực tế”**, thuộc nhóm **Fork/Join**. Kết thúc bài, bạn có thể:

1. Hiểu quan hệ giữa **chi phí hữu ích tại lá**, **overhead tạo/điều phối task**, **độ sâu cây chia**, **critical path** và số worker thực sự sẵn có.
2. Viết bài toán `RecursiveTask` có điều kiện dừng an toàn, không chia một phần tử vô hạn.
3. Dùng `fork()` cho một nhánh, tính nhánh còn lại bằng `compute()`, rồi `join()`; biết vì sao không nên fork mọi phép tính nhỏ.
4. Đo sự khác biệt giữa **256 lá nhỏ** và **4 lá lớn** mà không nhầm số lá với tốc độ.
5. Chọn ngưỡng ban đầu dựa trên kích cỡ input và target parallelism, rồi benchmark để điều chỉnh.
6. Xử lý công việc **không đều chi phí** bằng ước lượng cost, prefix sums và điểm chia cân bằng **khối lượng** thay vì chỉ cân bằng **số lượng**.
7. Giữ các vùng ghi **không chồng lấn**, giảm tranh chấp, bảo đảm reducer đúng và không trộn kết quả sai do thứ tự.
8. Phân biệt tác vụ CPU với blocking I/O; hiểu tác dụng và giới hạn của `ForkJoinPool.managedBlock`.
9. Dùng `getStealCount()`, `getQueuedTaskCount()`, JFR và JMH đúng mục đích, không biến metric ước lượng thành bảo đảm.
10. Kiểm tra các cạnh biên: input rỗng, một phần tử, ngưỡng không hợp lệ, exception, overflow và cleanup pool.

Các API `ForkJoinPool`, `RecursiveTask`, `RecursiveAction`, `fork`, `join` và `invoke` đều là API **còn hiệu lực**. Ví dụ chạy độc lập bằng Java 17+ và không dựa vào cơ chế đã legacy. Những thông tin phụ thuộc máy hoặc thời gian chạy được trình bày như **heuristic cần đo**, không phải số liệu tốc độ được khẳng định.

## 2. Fork/Join hoạt động như thế nào?

Mẫu cơ bản là **divide–conquer–combine**:

```text
                   toàn bộ đầu vào [lo, hi)
                             |
                   đủ nhỏ theo cost?
                       /           \
                    có              không
                    |                 |
              xử lý tuần tự        chia thành
               tại leaf           [lo,mid) [mid,hi)
                                      |       |
                                   fork      compute
                                      \       /
                                        join
                                         |
                                 kết hợp kết quả
```

Hai công cụ thường gặp:

- `RecursiveTask<V>`: dùng khi tác vụ **trả về một giá trị V**, chẳng hạn tổng, min/max hoặc một object kết quả.
- `RecursiveAction`: dùng khi tác vụ **không trả giá trị**, ví dụ ghi vào các dải index không chồng lấn của một mảng đích.

`ForkJoinPool` điều phối các task bằng nhiều hàng đợi và cơ chế **work-stealing**. Một worker bận có thể tạo subtask, còn worker khác có thể lấy việc chưa chạy để làm. Nhưng việc “được steal” không có nghĩa task sẽ hoàn thành đúng theo thứ tự tạo, và không có bảo đảm mỗi nhánh sẽ có một thread riêng.

Một pattern hữu ích trong `RecursiveTask`:

```java
LeftTask left = new LeftTask(...);
RightTask right = new RightTask(...);
left.fork();
Result rightResult = right.compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
```

*Đây là đoạn minh họa pattern, không phải class Java chạy độc lập.*

**Vì sao fork một nhánh, compute một nhánh?** Worker hiện tại có thể xử lý một nửa ngay thay vì đưa cả hai nửa vào hàng đợi và chờ. Nhánh được `fork` có thể được worker khác steal; nếu không có worker khác rảnh, quá trình `join` có thể hỗ trợ tiến trình hoàn thành. Mẫu này thường dễ kiểm soát overhead hơn việc fork hai task rồi chặn chờ cả hai.

## 3. “Hạt” và chi phí phải được định nghĩa ở đúng đơn vị

Một **leaf** là subtask không tiếp tục tách nhỏ và trực tiếp thực hiện vòng lặp/thuật toán tuần tự. “Grain size” có thể được biểu diễn bằng:

- **Số phần tử:** `hi - lo`. Phù hợp khi công việc/element gần đồng đều.
- **Số phép tính ước lượng:** khoảng các phép kiểm tra, số cạnh trong graph, số lần nhân ma trận hoặc số lần thử chia khi kiểm tra số nguyên tố.
- **Số byte hoặc vùng bộ nhớ:** hữu ích khi bottleneck là memory bandwidth/cache, nhưng không đồng nhất với CPU work.
- **Chi phí CPU đo được:** `ns/task` hoặc CPU cycles từ profiling; có nhiễu, không nên đo lại mỗi leaf nếu chính việc đo làm tăng overhead.
- **Độ sâu còn lại của cây:** đôi khi được dùng để tránh tạo quá nhiều task, nhưng chỉ là proxy cho khối lượng thật.
- **Một tổ hợp:** dừng khi cost ước lượng đủ nhỏ **hoặc** phạm vi chỉ còn một item không thể phân nhỏ.

Chọn đúng đơn vị là phần quan trọng nhất của bài. Ví dụ duyệt 100 số lớn để kiểm tra primality thường tốn khác hẳn 100 số nhỏ. Chia chính xác 50 số mỗi nhánh chưa chắc tạo hai nhánh chạy lâu bằng nhau.

**Nguyên tắc:** đừng lầm tưởng mỗi `RecursiveTask` mất đúng một chi phí cố định; chi phí thực bao gồm object allocation, đưa việc vào hàng đợi, điều phối, cache miss, work-stealing, `join`, callback và chính phép tính.

### 3.1. Công thức chi phí để suy nghĩ, không phải dự báo thời gian chính xác

Với tổng công việc hữu ích `W`, số worker `P`, số leaf `L` và overhead điều phối trung bình `h`:

```text
T_parallel   chịu ảnh hưởng bởi:
    W / P                      (cận dưới lý tưởng về CPU work)
    critical path              (nhánh tuần tự dài nhất)
    L * h                      (chi phí tạo/điều phối leaf/task)
    contention + cache misses  (tài nguyên chia sẻ)
    idle time                  (nhánh không đều, worker hết việc)

Không thể đơn giản khẳng định:
    T_parallel = W / P
```

Nếu chia **quá mịn**: `L` tăng mạnh, làm tăng overhead, allocation, lịch task, cache miss và contention. Nếu chia **quá thô**: số nhánh có thể ít hơn số worker, hoặc một nhánh nặng kéo dài critical path khiến worker khác nhàn rỗi.

**Mục tiêu thường là vừa đủ task để cân bằng tải nhưng mỗi task vẫn làm đủ công việc hữu ích.** Không phải “càng nhiều task càng nhanh”.

Javadoc `ForkJoinTask` có đưa ra một kinh nghiệm rất sơ bộ về lượng tính toán trong một task (cỡ hàng trăm đến hàng nghìn bước cơ bản). Đó là **ước lượng giáo dục**, không phải ngưỡng chuẩn hay số đo áp dụng trực tiếp cho mọi phép toán, CPU, JIT, cấu trúc dữ liệu hoặc workload. Cần benchmark trên môi trường đích.

## 4. Ví dụ nền: tính tổng dải với điều kiện dừng bằng số phần tử

Đây là bài toán có **chi phí/element đồng đều**: một phép cộng `long` mỗi phần tử, nên dùng ngưỡng `hi-lo` có ý nghĩa.

Lưu `ForkJoinRangeSumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinRangeSumDemo {
    static class SumTask extends RecursiveTask<Long> {
        final int[] values;
        final int lo, hi, grain;
        final AtomicInteger leafCount;

        SumTask(int[] values, int lo, int hi, int grain,
                AtomicInteger leafCount) {
            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
            this.leafCount = leafCount;
        }

        @Override
        protected Long compute() {
            int len = hi - lo;
            if (len <= grain) {
                leafCount.incrementAndGet();
                long sum = 0L;
                for (int i = lo; i < hi; i++) {
                    sum += values[i];
                }
                return sum;
            }

            int mid = lo + len / 2;
            SumTask left = new SumTask(
                    values, lo, mid, grain, leafCount);
            SumTask right = new SumTask(
                    values, mid, hi, grain, leafCount);

            left.fork();
            long rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger leaves = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            long result = pool.invoke(new SumTask(
                    numbers, 0, numbers.length, 2, leaves));

            System.out.println("sum = " + result);
            System.out.println("leaves = " + leaves.get());
            System.out.println("correct = " + (result == 36L));
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac ForkJoinRangeSumDemo.java
java ForkJoinRangeSumDemo
```

Stdout:

```text
sum = 36
leaves = 4
correct = true
```

Giải thích:

- Input có 8 phần tử, `grain=2` nên chia dải 8 → 4+4 → 2+2+2+2.
- Có 4 leaf, mỗi leaf tính tổng tuần tự trên 2 phần tử.
- `left.fork()` đưa nhánh trái vào cơ chế scheduling; worker hiện tại tính nhánh phải.
- `left.join()` lấy kết quả từ task trái; phép cộng kết hợp hai nửa. Tổng bằng 36 bất kể thứ tự thực thi.

Đây **không phải** bằng chứng mức grain 2 nhanh hơn grain 4 hoặc 8. Với chỉ 8 phần tử, cả bài có thể chạy tuần tự nhanh hơn nhiều. Ví dụ chủ yếu minh họa **ranh giới tách** và đảm bảo kết quả đúng.

## 5. Quá mịn và quá thô: đếm số task thay vì đo tốc độ giả

Khi chia đôi dải 256 phần tử tới từng item, sẽ có:

- 256 leaf.
- 255 internal node chia đôi.
- 511 task node tổng cộng.

Nếu grain là 64 và chia đôi đều thì chỉ có:

- 4 leaf.
- 3 internal node.
- 7 task node tổng cộng.

Số task khác nhau rất lớn, nhưng **tổng phép cộng hữu ích vẫn như nhau**. Đây là chi phí tổ chức task cần đưa vào cân nhắc.

Lưu `ForkJoinGrainCountDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinGrainCountDemo {
    static class CountedSum extends RecursiveTask<Long> {
        final int lo, hi, grain;
        final AtomicInteger leaves, nodes;

        CountedSum(int lo, int hi, int grain,
                   AtomicInteger leaves, AtomicInteger nodes) {
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
            this.leaves = leaves;
            this.nodes = nodes;
        }

        @Override
        protected Long compute() {
            nodes.incrementAndGet();
            if (hi - lo <= grain) {
                leaves.incrementAndGet();
                long result = 0L;
                for (int x = lo; x < hi; x++) {
                    result += x;
                }
                return result;
            }
            int mid = lo + (hi - lo) / 2;
            CountedSum left = new CountedSum(
                    lo, mid, grain, leaves, nodes);
            CountedSum right = new CountedSum(
                    mid, hi, grain, leaves, nodes);
            left.fork();
            long rightValue = right.compute();
            return left.join() + rightValue;
        }
    }

    private static void run(String name, int grain,
                            ForkJoinPool pool) {
        AtomicInteger leaves = new AtomicInteger();
        AtomicInteger nodes = new AtomicInteger();
        long sum = pool.invoke(new CountedSum(
                1, 257, grain, leaves, nodes));
        System.out.println(name + " sum=" + sum +
                " leaves=" + leaves.get() +
                " nodes=" + nodes.get());
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            run("fine", 1, pool);
            run("coarse", 64, pool);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinGrainCountDemo.java
java ForkJoinGrainCountDemo
```

```text
fine sum=32896 leaves=256 nodes=511
coarse sum=32896 leaves=4 nodes=7
```

**Diễn giải đúng:** ví dụ chứng minh overhead tiềm năng từ **số task**, không đo trực tiếp độ trễ. Trong một phép cộng rẻ như thế này, chia quá nhỏ thường không đáng, nhưng muốn kết luận phải đo trên bộ dữ liệu, môi trường và cách sử dụng pool thực tế.

### 5.1. Bảng so sánh cơ chế

| Lựa chọn | Ưu điểm | Nguy cơ |
| --- | --- | --- |
| Một leaf cho toàn bộ input | Không fork, ít overhead | Không tận dụng nhiều worker |
| Rất ít leaf lớn | Ít task, cache locality tốt hơn trong nhiều bài | Load imbalance, worker thiếu việc |
| Một số leaf nhiều hơn số worker | Có cơ hội work-stealing cân bằng tải | Vẫn tốn scheduling; cần đo |
| Một leaf cho mỗi item | Chia rất mịn | Task allocation/scheduling có thể lấn át công việc |
| Leaf theo **chi phí ước lượng** | Cân bằng được item không đồng đều | Tốn công ước lượng, có sai số và cần fallback |

Trong thực tế, không dùng một bảng cố định “P=8 thì luôn tạo 32 task” như luật cứng. Đó chỉ có thể là **điểm thử ban đầu**.

## 6. Chọn ngưỡng sơ bộ theo số worker và cỡ input

Với input khá đồng đều, có thể thử số leaf mục tiêu **gấp vài lần target parallelism** để cho phép work-stealing xử lý bất cân bằng nhỏ. Ví dụ:

```text
n = 100 items
targetParallelism = 2
targetLeaves = 2 * 4 = 8
initialGrain = ceil(100 / 8) = 13
```

Hệ số **4** chỉ là **một heuristic thử nghiệm**, không phải thông số JDK bắt buộc. Chi phí leaf, loại dữ liệu, số core, memory bandwidth và CPU quota có thể khiến hệ số tốt nhất khác hẳn.

Lưu `ForkJoinAdaptiveGrainDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinAdaptiveGrainDemo {
    static class Sum extends RecursiveTask<Long> {
        final int lo, hi, grain;
        final AtomicInteger leaves;

        Sum(int lo, int hi, int grain, AtomicInteger leaves) {
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
            this.leaves = leaves;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= grain) {
                leaves.incrementAndGet();
                long result = 0L;
                for (int x = lo + 1; x <= hi; x++) {
                    result += x;
                }
                return result;
            }
            int mid = lo + (hi - lo) / 2;
            Sum left = new Sum(lo, mid, grain, leaves);
            Sum right = new Sum(mid, hi, grain, leaves);
            left.fork();
            long rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    public static void main(String[] args) {
        int n = 100;
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            int parallelism = pool.getParallelism();
            int targetLeaves = parallelism * 4;
            int grain = Math.max(
                    1, (n + targetLeaves - 1) / targetLeaves);

            AtomicInteger leaves = new AtomicInteger();
            long sum = pool.invoke(
                    new Sum(0, n, grain, leaves));

            System.out.println("targetParallelism = " +
                    parallelism);
            System.out.println("initialGrain = " + grain);
            System.out.println("leaves = " + leaves.get());
            System.out.println("sum = " + sum);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinAdaptiveGrainDemo.java
java ForkJoinAdaptiveGrainDemo
```

```text
targetParallelism = 2
initialGrain = 13
leaves = 8
sum = 5050
```

**Điều cần lưu ý:** `ForkJoinPool.getParallelism()` là **target parallelism**, không bảo đảm hai CPU thực sự chạy đồng thời trong máy/container. Công thức từ `n` và `P` chỉ là ngưỡng khởi đầu. Nếu mỗi element tốn 1 µs hay 1 ms, cùng số lượng element lại có hai lựa chọn grain rất khác nhau.

Mọi công thức dạng `(n + targetLeaves - 1) / targetLeaves` cũng cần cẩn thận overflow với n rất lớn; trong code production, có thể dùng long hoặc phép chia và remainder để tính ceiling an toàn. Ví dụ trên có n=100 nên không có nguy cơ.

## 7. Vì sao chia đôi theo index có thể tạo hai nhánh lệch nặng?

Xem 8 công việc có **chi phí ước lượng**:

```text
index:      0   1  2  3  4  5  6  7
cost:      10   1  1  1  1  1  1  1
total cost = 17
```

Nếu chia theo **số item** ở `mid=4`:

```text
left  indices [0,4): cost 10+1+1+1 = 13
right indices [4,8): cost 1+1+1+1  = 4
```

Nếu chia theo **tổng cost**, điểm chia `cut=1` cho:

```text
left  [0,1): cost 10
right [1,8): cost 7
```

Sự chênh 10/7 ít hơn 13/4. Chia số item bằng nhau không tương đương chia công việc bằng nhau. Tuy nhiên, **item tại index 0 vẫn có cost 10**, vượt ngưỡng leaf nếu ngưỡng dưới 10. Vì item không thể chia nhỏ hơn nếu thuật toán chỉ xử lý whole items, critical path còn phụ thuộc item này. Một cost estimator tốt không làm một task nguyên tử nặng **tự trở nên song song**.

### 7.1. Chứng minh dữ liệu đầu vào trước khi viết scheduler

Lưu `ForkJoinUnevenBalanceDemo.java`:

```java
public class ForkJoinUnevenBalanceDemo {
    private static long sum(long[] costs, int lo, int hi) {
        long result = 0L;
        for (int i = lo; i < hi; i++) {
            result += costs[i];
        }
        return result;
    }

    public static void main(String[] args) {
        long[] costs = {10, 1, 1, 1, 1, 1, 1, 1};
        int indexMid = costs.length / 2;
        int weightedCut = 1;

        System.out.println("total = " +
                sum(costs, 0, costs.length));
        System.out.println("byIndex = " +
                sum(costs, 0, indexMid) + "," +
                sum(costs, indexMid, costs.length));
        System.out.println("byCost = " +
                sum(costs, 0, weightedCut) + "," +
                sum(costs, weightedCut, costs.length));
    }
}
```

```bash
javac ForkJoinUnevenBalanceDemo.java
java ForkJoinUnevenBalanceDemo
```

```text
total = 17
byIndex = 13,4
byCost = 10,7
```

**Lưu ý:** cost là **mô hình**, không phải thời gian CPU thật được đo trong ví dụ. Khi áp dụng thực tế, cost có thể là số phép kiểm tra ước lượng, độ phức tạp input, số cạnh graph hoặc thông tin từ các lần xử lý trước. Cần kiểm tra rằng cost ước lượng thực sự tương quan với CPU work; nếu không, “cân bằng theo cost” có thể làm tình hình tệ hơn.

## 8. Chia theo tổng cost bằng prefix sums

Nếu thứ tự item phải được giữ trong các range liên tiếp, có thể tạo mảng prefix sum:

```text
costs:  [10, 1, 1, 1, 1, 1, 1, 1]
prefix: [0,10,11,12,13,14,15,16,17]

estimatedWork(lo,hi) = prefix[hi] - prefix[lo]
```

Với một range `[lo,hi)`, tìm cut nằm giữa `lo+1` và `hi-1` sao cho **chi phí ước lượng của hai nửa gần nhau nhất**, thay vì chọn midpoint theo index. Nếu mỗi cost dương, prefix sums tăng dần, ta có thể dùng **binary search** để tìm ranh giới gần một nửa cost; nếu input có cost âm, thuật toán đó không hợp lệ. Cost âm không có nghĩa là “khối lượng CPU âm”; phải kiểm tra dữ liệu trước.

Quy tắc dừng:

```text
if range has <= 1 indivisible item:
    execute leaf
else if estimatedWork(lo,hi) <= costBudget:
    execute leaf
else:
    choose cost-balanced cut
    fork one side, compute other, join
```

Lưu `ForkJoinWeightedCostDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinWeightedCostDemo {
    static int bestCut(long[] prefix, int lo, int hi) {
        long target = prefix[lo] +
                (prefix[hi] - prefix[lo]) / 2L;

        int low = lo + 1;
        int high = hi - 1;

        while (low < high) {
            int mid = (low + high) >>> 1;
            if (prefix[mid] < target) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }

        int before = Math.max(lo + 1, low - 1);
        int after = low;

        long diffBefore = Math.abs(
                (prefix[before] - prefix[lo])
                - (prefix[hi] - prefix[before]));
        long diffAfter = Math.abs(
                (prefix[after] - prefix[lo])
                - (prefix[hi] - prefix[after]));

        return diffBefore <= diffAfter ? before : after;
    }

    static class Work extends RecursiveTask<Long> {
        final long[] costs, prefix;
        final int lo, hi;
        final long budget;

        Work(long[] costs, long[] prefix,
             int lo, int hi, long budget) {
            this.costs = costs;
            this.prefix = prefix;
            this.lo = lo;
            this.hi = hi;
            this.budget = budget;
        }

        @Override
        protected Long compute() {
            long estimated = prefix[hi] - prefix[lo];
            if (hi - lo <= 1 || estimated <= budget) {
                long operations = 0L;
                for (int i = lo; i < hi; i++) {
                    for (long j = 0; j < costs[i]; j++) {
                        operations++;
                    }
                }
                return operations;
            }

            int cut = bestCut(prefix, lo, hi);
            Work left = new Work(
                    costs, prefix, lo, cut, budget);
            Work right = new Work(
                    costs, prefix, cut, hi, budget);

            left.fork();
            long rightWork = right.compute();
            return left.join() + rightWork;
        }
    }

    public static void main(String[] args) {
        long[] costs = {10, 1, 1, 1, 1, 1, 1, 1};
        long[] prefix = new long[costs.length + 1];

        for (int i = 0; i < costs.length; i++) {
            if (costs[i] <= 0L) {
                throw new IllegalArgumentException(
                        "positive costs required");
            }
            prefix[i + 1] = Math.addExact(
                    prefix[i], costs[i]);
        }

        int rootCut = bestCut(
                prefix, 0, costs.length);

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            long done = pool.invoke(new Work(
                    costs, prefix, 0, costs.length, 4L));

            System.out.println("rootCut = " + rootCut);
            System.out.println("indexMid = " +
                    costs.length / 2);
            System.out.println("workDone = " + done);
            System.out.println("sameAsCostSum = " +
                    (done == prefix[costs.length]));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinWeightedCostDemo.java
java ForkJoinWeightedCostDemo
```

```text
rootCut = 1
indexMid = 4
workDone = 17
sameAsCostSum = true
```

**Vì sao chương trình tính bằng vòng đếm `operations++`?** Để xây dựng một workload nhỏ, xác định được kết quả mà không cần đo thời gian hay lệ thuộc tốc độ CPU. Nó chỉ chứng minh thuật toán **chia theo cost và phủ đủ phạm vi**, không chứng minh thực thi song song có lợi hơn.

Giới hạn quan trọng khi áp dụng:

- Chuẩn bị `prefix` tốn O(n) thời gian và O(n) bộ nhớ. Nếu phép xử lý thật rất rẻ, riêng chi phí này có thể không đáng.
- `bestCut` dùng binary search vì `prefix` tăng đều theo cost dương; cost bằng 0 cần xử lý cẩn thận, cost âm phải bị loại trừ.
- `Math.addExact` giúp phát hiện tràn long khi cộng cost. Ví dụ bài học có cost rất nhỏ.
- Nếu một item không thể chia có cost lớn hơn budget, điều kiện `hi-lo<=1` ngăn tách vô hạn; đó là leaf quá nặng **không thể tự cân bằng**.
- `Math.abs` trên `Long.MIN_VALUE` có góc cạnh overflow; với cost cực lớn, nên dùng phép so chênh lệch không overflow hoặc `BigInteger`/giới hạn tổng rõ ràng. Ví dụ đã kiểm tra tổng chi phí nhỏ.
- Biết được cost *ước lượng* không đồng nghĩa biết chính xác thời gian CPU; cần profiling và hiệu chỉnh mô hình.

## 9. Khi nào nên chia lại bên trong một phần tử nặng?

Với input dạng `[10,1,1,1,...]`, một phần tử nặng có thể trở thành critical path. Có ba hướng giải:

1. **Phân rã phần tử:** nếu item chứa 10.000 cạnh hoặc 10.000 pixel độc lập, tách item đó thành các unit nhỏ hơn rồi dùng Fork/Join ngay trong item.
2. **Tạo nhiều task độc lập:** với danh sách item không cần các range liên tiếp, có thể dùng lịch task theo cost (chẳng hạn task lớn được đưa vào pool đủ sớm) và tận dụng work-stealing.
3. **Không chia nữa:** nếu item là một thuật toán tuần tự hoặc tài nguyên không thể chia, chấp nhận nhánh nặng. Chia wrapper quanh nó thành hàng trăm task không thể tăng tính song song của công việc bên trong.

Phải phân biệt **“chi phí cao”** với **“có thể chia nhỏ”**. Không tự áp dụng thêm recursion cho một phép gọi vốn không có đơn vị độc lập.

Một số workload không đều theo **dữ liệu tại từng điểm**: phân tích cú pháp, giải nén, đánh giá cây biểu thức, xử lý graph, render các vùng ảnh phức tạp, tính số nguyên tố. Trong trường hợp đó, threshold dựa trên count chỉ là proxy và cần test với dữ liệu đại diện.

## 10. `RecursiveAction`: chia công việc ghi trên các dải không chồng lấn

Không phải mọi tác vụ đều trả giá trị. Nếu biến đổi mảng đầu ra, `RecursiveAction` phù hợp, miễn mỗi leaf chỉ ghi vùng thuộc quyền của nó.

Mẫu an toàn: chia mảng theo các dải `[lo,hi)` **không trùng nhau**. Không dùng một `ArrayList` hay `StringBuilder` chung để nhiều leaf gọi `add`/`append` mà không có synchronization.

Lưu `ForkJoinDisjointActionDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinDisjointActionDemo {
    static class SquareAction extends RecursiveAction {
        final int[] data;
        final int lo, hi, grain;

        SquareAction(int[] data, int lo, int hi, int grain) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
        }

        @Override
        protected void compute() {
            if (hi - lo <= grain) {
                for (int i = lo; i < hi; i++) {
                    data[i] = data[i] * data[i];
                }
                return;
            }

            int mid = lo + (hi - lo) / 2;
            SquareAction left =
                    new SquareAction(data, lo, mid, grain);
            SquareAction right =
                    new SquareAction(data, mid, hi, grain);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            pool.invoke(
                    new SquareAction(data, 0, data.length, 2));
        } finally {
            pool.shutdown();
        }

        System.out.println("squared = " +
                Arrays.toString(data));
        System.out.println("sum = " +
                Arrays.stream(data).sum());
    }
}
```

```bash
javac ForkJoinDisjointActionDemo.java
java ForkJoinDisjointActionDemo
```

```text
squared = [1, 4, 9, 16, 25, 36, 49, 64]
sum = 204
```

Ở đây các leaf không cùng ghi một index nên không có **write/write race tại phần tử mảng**. Sau khi `pool.invoke` hoàn tất bình thường, caller có thể đọc kết quả đã được publish theo cơ chế hoàn tất task. Nếu các leaf cùng sửa **một object mutable nằm trong mảng**, việc chia index không tự đảm bảo bên trong object đó thread-safe.

### 10.1. Data locality và false sharing

Một worker xử lý một dải liên tiếp thường khai thác cache locality tốt hơn việc đọc/ghi các index rải rác. Tuy nhiên, hai thread có thể ghi các field hoặc phần tử gần nhau ở **cùng cache line** dẫn đến **false sharing**: cache line di chuyển giữa core dù về logic các giá trị khác nhau.

Granularity quá nhỏ có thể tăng khả năng nhiều worker liên tục ghi các vùng sát nhau. Nhưng **không phải mọi bài toán mảng đều bị false sharing**, và không nên tự “padding mọi object” khi chưa có profiling. Các công cụ như Java Flight Recorder và profiler CPU/cache giúp xác minh bottleneck thật.

## 11. Tổng hợp kết quả: tránh shared accumulator khi có thể

Mẫu chuẩn cho tổng số:

```java
long leftResult = left.join();
long rightResult = right.compute();
return leftResult + rightResult;
```

*Đây chỉ là công thức minh họa; trong triển khai thực tế phải fork/tính/join theo thứ tự hợp lệ. Không dùng đoạn này nguyên xi như một chương trình.*

Nên để mỗi leaf tạo **local result**, rồi merge theo cây. Nếu tất cả leaf cùng cập nhật một `AtomicLong` hoặc một collection concurrent, tính đúng vẫn có thể đảm bảo, nhưng contention ở một biến dùng chung có thể làm giảm scalability.

Không phải reducer nào cũng phù hợp:

- Tổng số nguyên có kiểm soát overflow, min/max, bitwise OR/AND có thể dùng các phép kết hợp phù hợp.
- Phép trừ, nối text yêu cầu thứ tự hoặc cập nhật state ngoài có thể **không phù hợp** với cây gộp bất kỳ.
- Phép cộng floating-point không **associative chính xác** vì quy tắc làm tròn. Thay đổi thứ tự gộp có thể làm kết quả khác từng bit.

Lưu `ForkJoinFloatingOrderDemo.java`:

```java
public class ForkJoinFloatingOrderDemo {
    public static void main(String[] args) {
        double[] values = {
                10_000_000_000_000_000.0,
                1.0,
                -10_000_000_000_000_000.0,
                1.0
        };

        double sequential = 0.0;
        for (double value : values) {
            sequential += value;
        }

        double balanced =
                (values[0] + values[1])
                + (values[2] + values[3]);

        System.out.println("sequential = " + sequential);
        System.out.println("balanced = " + balanced);
        System.out.println("sameBits = " +
                (Double.doubleToLongBits(sequential) ==
                 Double.doubleToLongBits(balanced)));
    }
}
```

```bash
javac ForkJoinFloatingOrderDemo.java
java ForkJoinFloatingOrderDemo
```

```text
sequential = 1.0
balanced = 0.0
sameBits = false
```

Đây là ví dụ số thực IEEE-754, **không phải race**. Nếu nghiệp vụ yêu cầu tổng chính xác theo một thứ tự nhất định hoặc độ ổn định bit-by-bit, cần chọn phương pháp số học/reduction khác (ví dụ số nguyên đơn vị nhỏ nhất với kiểm tra overflow, thuật toán cộng giảm sai số, deterministic grouping, hoặc `BigDecimal` trong bối cảnh phù hợp).

### 11.1. Cẩn thận overflow khi trả `Integer`

Một cây tính tổng mà mỗi leaf trả `Integer` sẽ chịu quy tắc tràn int. Nếu đầu vào hoặc tổng có thể vượt dải int, dùng `RecursiveTask<Long>`/`long` và kiểm tra phạm vi.

Lưu `ForkJoinOverflowDemo.java`:

```java
import java.util.Arrays;

public class ForkJoinOverflowDemo {
    public static void main(String[] args) {
        int[] values = {
                Integer.MAX_VALUE,
                Integer.MAX_VALUE
        };

        int intSum = Arrays.stream(values).sum();
        long longSum = Arrays.stream(values)
                .mapToLong(Integer::longValue)
                .sum();

        System.out.println("intSum = " + intSum);
        System.out.println("longSum = " + longSum);
        System.out.println("correctInLong = " +
                (longSum == 4_294_967_294L));
    }
}
```

```bash
javac ForkJoinOverflowDemo.java
java ForkJoinOverflowDemo
```

```text
intSum = -2
longSum = 4294967294
correctInLong = true
```

Không sử dụng output overflow làm số liệu nghiệp vụ hợp lệ. Dù thực thi tuần tự hay song song, overflow vẫn có thể xảy ra. Việc đổi `grain` không sửa được bài toán miền giá trị.

## 12. Work-stealing giúp phân phối việc nhưng không xóa mọi bất cân bằng

`ForkJoinPool` dùng **work-stealing** để worker rảnh tìm task chưa chạy. Nó hiệu quả nhất khi:

- Có đủ subtask độc lập để worker khác lấy.
- Công việc bên trong đủ nhiều để chi phí lấy việc không lấn át.
- Chia task không tạo các dependency blocking hoặc vùng ghi tranh chấp nặng.
- Công việc thật sự có thể chạy đồng thời (không bị tuần tự hóa bởi một lock, một connection hoặc một bước merge dài).

Work-stealing **không thể** làm một leaf duy nhất, không thể chia được, chạy đồng thời trên nhiều core. Nó cũng không cam kết cân bằng hoàn hảo: một nhánh có cost bị ước lượng sai vẫn có thể thành critical path.

### 12.1. Khi nào nên tăng số leaf?

Cần tăng khả năng chia việc khi:

- Có ít leaf hơn worker, nhiều worker không có việc.
- Một số leaf rất nặng so với leaf khác.
- Profiling cho thấy một worker bận lâu trong khi các worker khác gần như idle và không còn task để steal.

### 12.2. Khi nào nên tăng grain (ít leaf hơn)?

Cần giảm số task nếu:

- Số lượng fork/join tăng vọt so với công việc hữu ích.
- Allocation/GC, scheduling hoặc queue contention chiếm tỷ lệ lớn.
- Thêm worker không cải thiện throughput dù CPU không thiếu.
- Leaf quá ngắn khiến data/cache locality suy giảm.

Không rút ra “nhiều steals = tốt” hoặc “ít steals = xấu” đơn giản. `getStealCount()` là một **metric ước lượng**, cần đọc cùng throughput, active worker, queue depth và critical path.

## 13. Tác vụ có chi phí không đều: ví dụ đếm số nguyên tố

Kiểm tra `n` có nguyên tố không bằng trial division tốn số phép chia phụ thuộc `n` và khi nào gặp ước số đầu tiên. Ngay cả khi hai input có cùng số chữ số, một số chẵn có thể kết thúc gần như ngay, còn số nguyên tố phải thử nhiều ước số hơn.

Vì vậy số item không phản ánh chính xác CPU work. Một cost model đơn giản có thể lấy `floor(sqrt(n))` làm **cận trên gần đúng về số vòng kiểm tra**; với số hợp số, phép thử có thể dừng sớm hơn nhiều.

Lưu `ForkJoinIrregularCpuDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.Arrays;

public class ForkJoinIrregularCpuDemo {
    static boolean isPrime(int n) {
        if (n < 2) {
            return false;
        }
        for (int divisor = 2;
             (long) divisor * divisor <= n;
             divisor++) {
            if (n % divisor == 0) {
                return false;
            }
        }
        return true;
    }

    static class PrimeCounter extends RecursiveTask<Integer> {
        final int[] values;
        final int lo, hi, grain;

        PrimeCounter(int[] values, int lo, int hi, int grain) {
            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= grain) {
                int count = 0;
                for (int i = lo; i < hi; i++) {
                    if (isPrime(values[i])) {
                        count++;
                    }
                }
                return count;
            }

            int mid = lo + (hi - lo) / 2;
            PrimeCounter left = new PrimeCounter(
                    values, lo, mid, grain);
            PrimeCounter right = new PrimeCounter(
                    values, mid, hi, grain);

            left.fork();
            int rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {2, 4, 17, 18, 19, 20, 97, 99};

        long estimatedUpperWork = Arrays.stream(numbers)
                .mapToLong(n -> (long) Math.sqrt(n))
                .sum();

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int primes = pool.invoke(new PrimeCounter(
                    numbers, 0, numbers.length, 2));

            System.out.println("items = " + numbers.length);
            System.out.println("estimatedWork = " +
                    estimatedUpperWork);
            System.out.println("primeCount = " + primes);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinIrregularCpuDemo.java
java ForkJoinIrregularCpuDemo
```

```text
items = 8
estimatedWork = 37
primeCount = 4
```

Số nguyên tố trong input là `2, 17, 19, 97`. Cost estimate 37 chỉ là một proxy tính từ sqrt của 8 giá trị; **không phải số phép chia thật** và cũng không phải thời gian CPU. Đây là lý do cần hiệu chỉnh cost model theo dữ liệu thật.

Nếu có 100.000 số lớn, bạn có thể dùng prefix sum của estimated work để chia dải theo tổng cost, tương tự `ForkJoinWeightedCostDemo`. Nhưng với chỉ 8 số như trên, chuẩn bị prefix sum và tách thêm task không có cơ sở để kỳ vọng tăng tốc.

## 14. Blocking I/O là trường hợp khác với CPU-bound Fork/Join

Một task Fork/Join lý tưởng thường có phần tính toán CPU tương đối ngắn và ít blocking không được quản lý. Nếu mỗi leaf:

- Gọi HTTP/DB đồng bộ.
- Chờ socket hoặc một lock trong thời gian dài.
- Gọi `Thread.sleep` để mô phỏng I/O.
- Chờ một future/task khác bị queue sau trong cùng một pool ít worker.

thì worker có thể bị giữ lại thay vì xử lý task hữu ích. Work-stealing không tự bù đắp mọi dạng blocking I/O.

`ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)` là **API vẫn còn hiệu lực** cho các trường hợp blocking mà pool có thể nhận biết; nó có thể cho phép pool bù trừ worker đang bị chặn. Nhưng:

- **Không** có bảo đảm chắc chắn tạo thêm worker trong mọi cấu hình.
- Cần triển khai `ManagedBlocker.isReleasable()` và `block()` đúng contract, xử lý interruption.
- Đây **không phải** giải pháp chung để biến bất kỳ tác vụ I/O dài nào thành phù hợp với Fork/Join.
- Với nhiều HTTP/DB request, thường nên dùng asynchronous client hoặc bounded executor có policy I/O, timeout và backpressure rõ ràng.

**Anti-pattern minh họa:**

```java
protected Integer compute() {
    int result = slowBlockingHttpCall();
    return result;
}
```

*Chỉ minh họa một method không độc lập; `slowBlockingHttpCall()` không được định nghĩa. Nếu gọi loại tác vụ này với số lượng rất lớn trên common pool, có thể dẫn đến chiếm worker và tải I/O không kiểm soát.*

Khi bottleneck là **network latency**, đổi grain từ 100 xuống 10 không tự tăng tốc CPU; bạn cần xử lý ở **tầng giới hạn connections, concurrency, timeout, rate limit và batching request**.

## 15. Tránh chờ chặn vô ích và dependency vòng

Mẫu đúng trong nhiều divide-and-conquer:

```java
left.fork();                 // một nhánh có thể được steal
Result rightValue = right.compute(); // tự xử lý nhánh kia
Result leftValue = left.join();       // chờ khi thực sự cần
return merge(leftValue, rightValue);
```

*Đây là pseudocode dạng Java, không phải chương trình độc lập.*

Mẫu không nên mặc định:

```java
left.fork();
right.fork();
return merge(left.join(), right.join());
```

*Minh họa phương án có thể tạo thêm scheduling overhead; không phải cú pháp sai trong mọi bối cảnh.*

Cả hai có thể cho kết quả đúng, nhưng **fork hai nhánh rồi không làm gì ngoài chờ** dễ tạo thêm overhead ở workload nhỏ. Trong nhiều thuật toán, fork một nhánh và tự compute nhánh còn lại là lựa chọn mặc định thực dụng.

**Nguy cơ deadlock lô-gic:** nếu task A chờ B mà B chờ ngược A, hoặc các task chiếm lock rồi đợi nhau, việc dùng ForkJoinPool không tự giải quyết dependency vòng. Đừng xây một cây phụ thuộc có các cạnh chờ không thể thỏa.

## 16. Quan sát pool bằng metric — không biến số đo ước lượng thành assertion

`ForkJoinPool` hiện có các API quan sát hữu ích:

- `getParallelism()`: mức parallelism mục tiêu.
- `getPoolSize()`: số worker đã được tạo (không phải lúc nào cũng đang chạy).
- `getActiveThreadCount()`: ước lượng worker đang hoạt động.
- `getRunningThreadCount()`: ước lượng worker không chặn vì join/managed synchronization.
- `getStealCount()`: ước lượng số task được thực hiện nhờ steal từ submitter khác.
- `getQueuedTaskCount()`: ước lượng task nằm trong queue của worker.
- `getQueuedSubmissionCount()`: ước lượng submission từ bên ngoài chưa chạy.

Những metric này có thể thay đổi ngay khi đọc; một lần lấy mẫu **không phải snapshot nguyên tử của toàn pool**. Không viết unit test ép `getStealCount()==4` cho một bài toán nhỏ, vì kết quả phụ thuộc scheduler và CPU.

Lưu `ForkJoinPoolMetricsDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinPoolMetricsDemo {
    static class Sum extends RecursiveTask<Integer> {
        final int lo, hi;
        Sum(int lo, int hi) {
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= 2) {
                int total = 0;
                for (int x = lo; x < hi; x++) {
                    total += x;
                }
                return total;
            }

            int mid = lo + (hi - lo) / 2;
            Sum left = new Sum(lo, mid);
            Sum right = new Sum(mid, hi);
            left.fork();
            int rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int result = pool.invoke(new Sum(1, 17));

            System.out.println("parallelism = " +
                    pool.getParallelism());
            System.out.println("sum = " + result);
            System.out.println("stealsNonNegative = " +
                    (pool.getStealCount() >= 0L));
            System.out.println("queuedNonNegative = " +
                    (pool.getQueuedTaskCount() >= 0L));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinPoolMetricsDemo.java
java ForkJoinPoolMetricsDemo
```

```text
parallelism = 2
sum = 136
stealsNonNegative = true
queuedNonNegative = true
```

Ví dụ chỉ kiểm tra kết quả tính và tính hợp lệ cơ bản của metric, không cố định số steals/queue thật. Trong production, cần ghi **chuỗi mẫu theo thời gian** và liên hệ với throughput, latency, CPU utilization, GC và workload.

### 16.1. Khi nhìn thấy high steal count thì làm gì?

Đừng kết luận ngay “cần giảm grain” hoặc “cần tăng grain”. Có thể:

- Nhiều steals vì có rất nhiều task nhỏ cần lấy.
- Nhiều steals vì load balancing đang hoạt động tốt.
- Ít steals vì một worker làm xong hầu hết task trước khi worker khác rảnh.
- Ít steals vì cây quá thô, không có việc để steal.
- Ít steals vì toàn bộ pool đang bị blocking.

Cần kết hợp metric với **thời gian lá**, **kích cỡ hàng đợi**, **CPU idle/busy** và cấu trúc cây nhiệm vụ.

## 17. Cạnh biên: dải rỗng, một phần tử, ngưỡng <= 0

Một điều kiện dừng tốt phải ngăn **recursion vô hạn** khi range chỉ còn một phần tử:

```java
if (hi - lo <= 1 || estimatedCost <= budget) {
    return computeSequentially();
}
```

*Snippet minh họa; `estimatedCost`, `budget` và hàm xử lý cần được khai báo.*

Với `budget` dự kiến dương, nên validate sớm. Khi dải rỗng, nhiều phép reduction có identity là 0, nhưng các bài toán khác có thể cần identity khác (min/max dùng empty result hoặc Optional).

Lưu `ForkJoinEdgeCasesDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinEdgeCasesDemo {
    static class Sum extends RecursiveTask<Integer> {
        final int[] values;
        final int lo, hi, grain;

        Sum(int[] values, int lo, int hi, int grain) {
            if (grain <= 0) {
                throw new IllegalArgumentException(
                        "grain must be positive");
            }
            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= grain) {
                int total = 0;
                for (int i = lo; i < hi; i++) {
                    total += values[i];
                }
                return total;
            }

            int mid = lo + (hi - lo) / 2;
            Sum left = new Sum(values, lo, mid, grain);
            Sum right = new Sum(values, mid, hi, grain);
            left.fork();
            int rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    public static void main(String[] args) {
        int[] data = {7};
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            int empty = pool.invoke(
                    new Sum(data, 0, 0, 1));
            int singleton = pool.invoke(
                    new Sum(data, 0, 1, 1));

            boolean rejected = false;
            try {
                new Sum(data, 0, 1, 0);
            } catch (IllegalArgumentException e) {
                rejected = true;
            }

            System.out.println("empty = " + empty);
            System.out.println("singleton = " + singleton);
            System.out.println("invalidGrainRejected = " +
                    rejected);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinEdgeCasesDemo.java
java ForkJoinEdgeCasesDemo
```

```text
empty = 0
singleton = 7
invalidGrainRejected = true
```

Bên cạnh ngưỡng, code production cần kiểm tra phạm vi `0 <= lo <= hi <= values.length` nếu input đến từ bên ngoài. Ví dụ tập trung vào grain nên không thêm phần validation đó vào mọi constructor.

## 18. Exceptions, cancellation và yêu cầu dừng công việc

Nếu một leaf trong cây ném `RuntimeException`, kết quả của root `invoke()` có thể hoàn tất bất thường và exception được lan truyền theo cơ chế task. Nhưng:

- Các nhánh khác có thể **đã chạy** hoặc **đang chạy** trước khi lỗi được phát hiện.
- Không có transaction rollback tự động cho side effect.
- Hủy task không đồng nghĩa mọi phép tính đang chạy chắc chắn ngừng ngay.
- Nếu phải dừng công việc lớn kịp thời, cần cơ chế cooperative cancellation/flag và kiểm tra tại các điểm hợp lý; chính sách interrupt/cancellation phụ thuộc API cụ thể.
- `ForkJoinTask.join()` trả giá trị khi hoàn tất bình thường, nhưng có thể rethrow exception khi task thất bại; không dùng `join` như một phép lấy giá trị không bao giờ lỗi.

Lưu `ForkJoinFailureDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinFailureDemo {
    static class ValidatedSum extends RecursiveTask<Integer> {
        final int[] data;
        final int lo, hi;

        ValidatedSum(int[] data, int lo, int hi) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= 1) {
                if (hi == lo) {
                    return 0;
                }
                if (data[lo] < 0) {
                    throw new IllegalArgumentException(
                            "negative item");
                }
                return data[lo];
            }

            int mid = lo + (hi - lo) / 2;
            ValidatedSum left =
                    new ValidatedSum(data, lo, mid);
            ValidatedSum right =
                    new ValidatedSum(data, mid, hi);

            left.fork();
            int rightPart = right.compute();
            return left.join() + rightPart;
        }
    }

    public static void main(String[] args) {
        int[] values = {1, 2, -3, 4};
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            boolean failed = false;
            try {
                pool.invoke(
                        new ValidatedSum(
                                values, 0, values.length));
            } catch (RuntimeException e) {
                failed = true;
            }

            System.out.println("failed = " + failed);
            System.out.println("inputStillLength = " +
                    values.length);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinFailureDemo.java
java ForkJoinFailureDemo
```

```text
failed = true
inputStillLength = 4
```

**Không suy ra rằng mọi nhánh đã hoàn tất khi nhận exception đầu tiên**, hoặc rằng toàn bộ side effect bị đảo ngược. Nếu tác vụ cần tạo file, ghi database hay gửi message, phải có chính sách commit/rollback riêng ở tầng nghiệp vụ.

## 19. Common pool hay custom pool?

`ForkJoinPool.commonPool()` là pool chia sẻ và phù hợp với nhiều ứng dụng. Khi có nhu cầu tách workload CPU hoặc kiểm soát target parallelism, có thể tạo `new ForkJoinPool(parallelism)`.

Không nhầm:

- **Parallelism**: mục tiêu số worker có thể hoạt động (không phải số task chính xác).
- **Grain**: lượng công việc một leaf xử lý trước khi trả kết quả.
- **Task count**: tổng số node/leaf được tạo theo cấu trúc cây.
- **CPU quota/availableProcessors**: tài nguyên có thể sử dụng trong container/JVM.
- **Blocking compensation**: pool có thể điều chỉnh nhân sự trong một số trường hợp, không bảo đảm loại bỏ mọi lãng phí do I/O.

Đổi pool từ `parallelism=2` sang `parallelism=8` không tự làm một cây chỉ có 2 leaf xử lý trên 8 core. Đổi grain từ 1.000 xuống 1 cũng không tự làm máy có thêm core.

Lưu `ForkJoinCustomPoolsDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinCustomPoolsDemo {
    static class Sum extends RecursiveTask<Integer> {
        final int lo, hi;

        Sum(int lo, int hi) {
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= 2) {
                int total = 0;
                for (int x = lo; x < hi; x++) {
                    total += x;
                }
                return total;
            }

            int mid = lo + (hi - lo) / 2;
            Sum left = new Sum(lo, mid);
            Sum right = new Sum(mid, hi);
            left.fork();
            int rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool one = new ForkJoinPool(1);
        ForkJoinPool two = new ForkJoinPool(2);

        try {
            int first = one.invoke(new Sum(1, 9));
            int second = two.invoke(new Sum(1, 9));

            System.out.println("poolOne = " +
                    one.getParallelism());
            System.out.println("poolTwo = " +
                    two.getParallelism());
            System.out.println("first = " + first);
            System.out.println("second = " + second);
            System.out.println("sameResult = " +
                    (first == second));
        } finally {
            one.shutdown();
            two.shutdown();
        }
    }
}
```

```bash
javac ForkJoinCustomPoolsDemo.java
java ForkJoinCustomPoolsDemo
```

```text
poolOne = 1
poolTwo = 2
first = 36
second = 36
sameResult = true
```

Output chỉ nói hai pool có target parallelism khác nhau và cho **cùng đáp số**, không chứng minh pool hai nhanh hơn pool một. Với bài 8 phép cộng, thời gian chạy không đáng dùng để kết luận.

### 19.1. Cleanup

`ForkJoinPool` là một `ExecutorService`. Với custom pool có vòng đời tạm, gọi `shutdown()` trong `finally` sau khi hoàn tất tác vụ. Trong ứng dụng lâu dài, pool có thể được quản lý ở phạm vi service, tránh tạo/hủy pool cho từng request nhỏ. `shutdown()` khởi động quy trình ngừng nhận task mới; nếu yêu cầu đợi termination, thực hiện theo hợp đồng `awaitTermination` hoặc lifecycle thích hợp.

**Không shutdown common pool cho mỗi request.** `ForkJoinPool.commonPool()` là tài nguyên chia sẻ với cách quản lý đặc biệt; nên để JVM quản lý vòng đời chung.

## 20. Benchmark đúng cách: so chi phí thực, không chạy một lần rồi đoán

**JMH** là công cụ benchmark Java có thể dùng để so sánh grain/pool/workload có kiểm soát. Tài liệu của `java.time` không liên quan tới đây; tài liệu chính là `java.util.concurrent`, và JMH là một dự án công cụ benchmark Java riêng.

Các điểm chuẩn bị:

1. **Dữ liệu đại diện:** cỡ input, giá trị nặng/nhẹ, tỷ lệ skew, locality và kích cỡ object.
2. **Nhiều grain:** ví dụ tuần tự, `n` (một leaf), `n/2`, `n/8`, `n/32` và các ngưỡng cost tương ứng. Chọn các điểm để **đo**, không công bố là tối ưu.
3. **Nhiều mức P:** 1, 2, 4, ... theo tài nguyên thật; lưu ý CPU quota trong container.
4. **Warmup/JIT:** chạy đủ warmup, nhiều lần fork JVM để giảm nhiễu.
5. **Cô lập setup:** không tạo mảng input/pool trong vùng đo nếu nghiệp vụ thực tái sử dụng chúng; hoặc đo cả setup nếu setup thật sự nằm trên critical path.
6. **Đo nhiều đại lượng:** throughput, p50/p95 latency, allocation/GC, CPU utilization, worker idle, steal/queue counts và tail latency.
7. **Xác minh kết quả:** không để JIT loại bỏ toàn bộ tính toán vì kết quả không được tiêu thụ.
8. **Đo contention:** hai benchmark cùng JVM có thể cạnh tranh common pool; cần kịch bản song song thực tế và so sánh công bằng.
9. **Lặp lại:** không kết luận từ một con số `System.nanoTime` trong `main`.
10. **Tách CPU và I/O:** một case blocking I/O không đại diện cho chi phí phép tính CPU ở leaf.

**Không tạo bảng “grain=1 nhanh gấp 4 lần grain=1000” khi chưa có phép đo.** Trong các demo, hầu hết kết quả in là số học xác định; phần benchmark cần làm trên máy đích và dữ liệu thật.

### 20.1. Công thức thử nghiệm ban đầu

Với các phần tử tương tự nhau:

```text
targetLeafCount ~= parallelism * trialFactor
trialFactor in {2, 4, 8}    // ví dụ ba ứng viên để benchmark
initialLeafItems ~= ceil(N / targetLeafCount)
```

Với công việc không đều:

```text
estimatedTotalWork = sum(cost(item))
initialLeafBudget ~= ceil(estimatedTotalWork / targetLeafCount)
split by work budget, not merely item count
```

Đây là công thức **chọn các cấu hình thử**, không phải lời khuyên cố định. Nếu overhead cost estimation cao, chỉ dùng cost-aware splitting khi lợi ích lớn hơn chi phí chuẩn bị/sắp xếp.

### 20.2. Dùng JFR và profiler để tìm đúng bottleneck

Khi thử nghiệm, đừng chỉ đo tổng thời gian:

- Nếu allocation và GC tăng khi grain nhỏ, có thể task quá nhiều.
- Nếu nhiều core rảnh nhưng một worker rất bận, có thể grain quá thô hoặc input skew.
- Nếu CPU gần bão hòa và memory bandwidth là nút thắt, thêm task không giúp nhiều.
- Nếu nhiều worker chờ lock/IO, thay đổi cách đồng bộ/I/O trước khi tinh chỉnh threshold.
- Nếu một leaf rất dài, xem có thể chia chính computation bên trong hay không.

**JFR (Java Flight Recorder)** là công cụ profiling hiện hành của Java. Cũng có thể dùng JMH cho microbenchmarks. Các metric nên được phân tích trên môi trường Java và hạ tầng phù hợp, không suy đoán từ thread name.

## 21. Khi nào Fork/Join không phải cách giải phù hợp?

| Bài toán | Hướng suy nghĩ | Lý do |
| --- | --- | --- |
| Sum/map CPU-heavy trên dữ liệu độc lập lớn | Fork/Join hoặc parallel stream, benchmark | Có cơ hội chia thành leaf độc lập |
| Dữ liệu rất nhỏ, phép cộng rẻ | Vòng lặp tuần tự | Tránh scheduling overhead |
| Nhiều job HTTP/DB cần bounded concurrency | Async client / executor được cấu hình cho I/O | Fork/Join không thay thế timeout/connection pool |
| Tác vụ phải chạy theo thứ tự rõ ràng | Pipeline ordered hoặc tuần tự | Work-stealing không bảo đảm thứ tự |
| Nhiều task viết một mutable object chung | Thiết kế lại state/partition | Race và contention lấn át |
| Một item cực nặng không thể chia | Tối ưu thuật toán item; chấp nhận critical path | Chia wrapper không thêm song song thật |
| Kết quả cần bit-for-bit deterministic khi reducer không kết hợp | Sequential hoặc deterministic reduction | Thứ tự gộp ảnh hưởng đáp số |
| Cần phản hồi kết quả ngay khi job bất kỳ hoàn tất | Executor/CompletionStage theo event | Không nhất thiết phải chờ cây reduction |
| Cần transaction nhiều hệ thống | Transaction/idempotent workflow | Fork/Join chỉ là điều phối CPU |

Bài tập “đang có nhiều phần tử” không đủ để kết luận cần Fork/Join. Phải có **công việc song song thực sự**, đủ lớn, ít dependency và phương pháp kết hợp đúng.

## 22. Lỗi phổ biến khi chọn grain

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng cố định `grain=1000` cho mọi workload | Chi phí mỗi item có thể khác hàng nghìn lần | Dùng work estimate/profiling |
| Mỗi item một ForkJoinTask | Task allocation/scheduling có thể lấn át CPU work | Gom nhiều item vào leaf |
| Chỉ chia 2 task cho 32 worker | Worker thiếu việc, nhánh dài thành critical path | Có thêm leaf nếu work thật cho phép |
| Cho rằng work-stealing tự chia một leaf nặng | Nó chỉ chuyển task chưa chạy | Phân rã leaf nếu có thể |
| Lấy `Runtime.availableProcessors()` làm số thread chắc chắn chạy | Container quota và tài nguyên ảnh hưởng thực | Đo CPU thực, dùng target parallelism như cấu hình |
| Fork hai nhánh rồi chờ mà không tự tính | Có thể tạo thêm overhead | Thử fork một nhánh, compute nhánh kia |
| Chia theo số item khi cost rất skew | Hai nhánh có work chênh lớn | Prefix sums/estimated cost |
| Tính cost model phức tạp hơn chính phép tính | Tiền xử lý phá lợi ích | Dùng proxy rẻ hoặc chia count |
| Quên `hi-lo<=1` khi budget quá nhỏ | Có thể chia vô hạn/empty branches | Base case đúng |
| Dùng shared ArrayList cho mọi leaf | Không thread-safe, có race | Local result/disjoint ranges/concurrent collection |
| Mặc định output có thứ tự theo fork | Scheduler không bảo đảm | Combine theo cấu trúc, sort khi cần |
| Gộp double và đòi kết quả bit-for-bit giống tuần tự | Floating-point không associative chính xác | Cấu trúc reduction/precision policy |
| Bỏ qua overflow trong int sum | Sai kết quả dù chạy atomically | long/BigInteger theo nhu cầu |
| Blocking I/O lâu trên pool CPU | Worker chờ thay vì làm việc hữu ích | Async I/O, bounded executor hoặc managedBlock khi phù hợp |
| Đọc `getStealCount()` là số công việc chính xác | Là metric ước lượng theo lúc đo | Dùng với metrics khác |
| Đo `nanoTime` một lần rồi gọi là benchmark | JIT, GC, scheduler và dữ liệu gây nhiễu | JMH/warmup/nhiều lần |
| Bỏ qua task exception/cancellation | Có thể còn partial work/side effect | Chính sách lỗi, dừng hợp tác |
| Tạo một pool mới cho mọi request rất nhỏ | Chi phí quản lý và cô lập không cần thiết | Pool có lifecycle phù hợp |
| Nhầm grain với `parallelismThreshold` của ConcurrentHashMap | Là hai API khác nhau | Tập trung vào leaf budget trong RecursiveTask |

## 23. Bài tập và lời giải

**Bài 1 — Quá mịn:** Có 256 phần tử và chỉ làm phép cộng. So sánh số leaf/internal node với `grain=1` và `grain=64`. Điều gì có thể tăng overhead? Có được kết luận luôn `grain=64` chạy nhanh hơn không?

**Bài 2 — Cost skew:** Cho `costs={10,1,1,1,1,1,1,1}`. Chia theo item midpoint rồi chia theo cost. Giải thích điểm khác và phần tử nào vẫn là critical path.

**Bài 3 — Adaptive budget:** Với `n=100`, pool target parallelism=2 và trialFactor=4, tính số leaf mục tiêu và initial grain. Vì sao chỉ là điểm benchmark đầu tiên?

**Bài 4 — Pure reduction:** Với dải `1..16`, viết RecursiveTask trả `long`. Fork một bên, compute bên kia và join; test kết quả bằng 136.

**Bài 5 — Dải rỗng:** Thử `[0,0)` và `[0,1)`. Base case nào ngăn recursion vô hạn nếu threshold bằng 0? Nên từ chối threshold<=0 hay xử lý bằng điều kiện dừng riêng?

**Bài 6 — Precision:** Dùng dãy `[1e16,1,-1e16,1]`. Giải thích vì sao tuần tự cho 1.0 và cân bằng cặp cho 0.0 dù không có race.

**Bài 7 — Blocking I/O:** Mỗi leaf gọi một HTTP request đồng bộ 2 giây. Vì sao giảm grain có thể làm common pool bị giữ worker và gây quá tải downstream? Nêu giải pháp concurrency/rate/timeout phù hợp hơn.

### 23.1. Lời giải Java cho bài 4

Lưu `ForkJoinGrainPractice.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinGrainPractice {
    static class Sum extends RecursiveTask<Long> {
        final int lo, hi, grain;
        final AtomicInteger leaves;

        Sum(int lo, int hi, int grain, AtomicInteger leaves) {
            this.lo = lo;
            this.hi = hi;
            this.grain = grain;
            this.leaves = leaves;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= grain) {
                leaves.incrementAndGet();
                long result = 0L;
                for (int x = lo; x < hi; x++) {
                    result += x;
                }
                return result;
            }

            int mid = lo + (hi - lo) / 2;
            Sum left = new Sum(lo, mid, grain, leaves);
            Sum right = new Sum(mid, hi, grain, leaves);
            left.fork();
            long rightSum = right.compute();
            return left.join() + rightSum;
        }
    }

    public static void main(String[] args) {
        AtomicInteger leafCount = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            long sum = pool.invoke(
                    new Sum(1, 17, 4, leafCount));

            System.out.println("sum = " + sum);
            System.out.println("leaves = " + leafCount.get());
            System.out.println("matches = " + (sum == 136L));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinGrainPractice.java
java ForkJoinGrainPractice
```

```text
sum = 136
leaves = 4
matches = true
```

Đáp án ngắn:

- Bài 1: 256 leaf và 255 internal node so với 4 leaf và 3 internal node; nhiều task hơn có overhead hơn, **không có kết luận tốc độ khi chưa benchmark**.
- Bài 2: theo count là 13/4, theo cost là 10/7; item cost 10 vẫn không chia thêm nếu indivisible.
- Bài 3: targetLeaves=8, grain=ceil(100/8)=13; điều chỉnh sau profiling và benchmark.
- Bài 5: xử lý len 0/1 đúng identity và từ chối threshold không hợp lệ; không để một item bị chia thành các range 0/1 vô hạn.
- Bài 6: floating-point làm tròn theo thứ tự gộp.
- Bài 7: dùng client async hoặc bounded I/O executor, deadline, connection/rate policy; `managedBlock` chỉ hỗ trợ khi có đúng blocker contract và không bảo đảm giải quyết mọi blocking.

## 24. Checklist review trước khi đưa vào production

- Tôi đã xác định **đơn vị công việc thực tế** và biến nào tương quan với thời gian CPU chưa?
- Các phần tử có chi phí gần đồng đều không? Nếu không, có cần cost-based splitter hay xử lý item nặng riêng?
- Tôi có đúng base case cho empty/singleton và threshold<=0?
- Tôi đã tránh tạo task cho từng phép tính rất nhỏ?
- Tôi đã tạo đủ leaf để worker có cơ hội steal nhưng không làm queue/task count phình quá mức?
- `fork`, `compute` và `join` có đúng thứ tự và không có dependency vòng?
- Dữ liệu input có immutable hoặc read-only trong toàn lượt xử lý? Các leaf có ghi vào dải không chồng lấn?
- Reducer có phù hợp nếu cây kết hợp khác thứ tự tuần tự? Có nguy cơ floating-point deviation hoặc overflow?
- Có shared accumulator/lock nào làm contention và phá mục tiêu song song?
- Tôi có đo trên **dữ liệu skew** và input cân bằng, thay vì chỉ test với số ngẫu nhiên đồng đều?
- Benchmark có warmup, đa lần lặp, phân biệt setup và computation thật không?
- Có đo CPU, allocation, GC, latency và tail latency thay vì chỉ một con số thời gian tổng?
- Nếu workload là blocking I/O, đã xem xét thiết kế khác thay vì giảm grain trên common pool?
- Tôi có dùng pool đúng lifecycle, cleanup custom pool mà không shutdown tài nguyên chung?
- Các metric `getStealCount/getQueuedTaskCount` có được xem là ước lượng?
- Có kiểm thử exception và cancellation không? Code có giả định mọi nhánh chắc chắn dừng ngay khi root lỗi?
- Có nêu rõ **grain heuristic không phải giá trị JDK bắt buộc**, kết quả đo phụ thuộc CPU/JDK/container/GC?
- Các ví dụ dùng API `java.util.concurrent` hiện hành, phù hợp Java 17+ và không dựa vào kiến thức lỗi thời?

## 25. Tài liệu chính thức Java còn hiệu lực

- Oracle Java SE 26 — `ForkJoinTask`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html
- Oracle Java SE 26 — `ForkJoinPool`, work-stealing, `managedBlock`, metrics và pool lifecycle: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- Oracle Java SE 26 — `RecursiveTask<V>`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveTask.html
- Oracle Java SE 26 — `RecursiveAction`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveAction.html
- Oracle Java SE 26 — `ExecutorService`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 26 — `ForkJoinPool.ManagedBlocker`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html
- OpenJDK JMH project — framework hiện hành để benchmark Java: https://github.com/openjdk/jmh
- OpenJDK JFR documentation — tooling giám sát/profiling JVM: https://openjdk.org/jeps/328

**Ghi nhớ:** chia hạt Fork/Join theo **chi phí thật của leaf**, không chỉ theo **số lượng element**. Granularity quá nhỏ tốn scheduling/allocation; quá lớn khiến ít task và critical path dài. Với cost không đều, một cost model đơn giản và điểm chia theo tổng estimated work có thể giúp cân bằng, nhưng bản thân cost model cũng tốn chi phí và không thay thế profiling. Hãy giữ `fork`/`compute`/`join` gọn, state an toàn, reduction đúng, tránh blocking I/O trên pool CPU và kiểm chứng trên workload thực trước khi gọi một threshold là “tối ưu”.