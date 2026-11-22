# Fork/Join: Chiến lược chia nhỏ và ngưỡng threshold trong Java

## 1. Bài toán và mục tiêu

Khi tính tổng một mảng lớn, biến đổi ảnh, xử lý một cây hoặc tìm kiếm qua nhiều nhánh, ta có thể phân chia bài toán thành các phần độc lập rồi gộp kết quả. Mô hình **Fork/Join** giúp thực hiện kiểu divide-and-conquer này bằng các worker trong `ForkJoinPool`. Nhưng tạo ra nhiều task không tự động nhanh hơn: mỗi lần chia đều phải trả chi phí tạo object, scheduling, work stealing, fork/join và gộp kết quả.

Bài tập trung vào hai quyết định thiết kế:

- **Chiến lược chia nhỏ:** chia đôi theo chỉ số, theo trọng số công việc, theo nhánh cây, theo chi phí ước tính, hay điều chỉnh động?
- **Ngưỡng `threshold`:** khi nào một task nên **ngừng chia** và xử lý tuần tự ngay trên worker hiện tại?

Sau bài bạn có thể:
1. Phân biệt `ForkJoinPool`, `ForkJoinTask`, `RecursiveTask<V>` và `RecursiveAction`; hiểu work stealing giúp cân bằng tải ra sao.
2. Cài đặt split an toàn trên khoảng **nửa mở `[from,to)`**, không bỏ sót/trùng phần tử và không đệ quy vô hạn.
3. Dùng mẫu **fork một nhánh, compute một nhánh, join**.
4. Ước lượng số leaf, số node, độ sâu và overhead khi thay threshold.
5. Biết khi nào dùng threshold theo **số phần tử**, theo **cost**, theo **độ sâu** hoặc kết hợp nhiều tiêu chí.
6. Tuning threshold dựa trên workload/benchmark thay vì một hằng số áp dụng cho mọi bài toán.
7. Đọc và chạy **bốn chương trình Java 17+ độc lập**: tổng mảng, đếm hình dạng cây, biến đổi mảng và phân hoạch theo trọng số.
8. Nhận biết các lỗi về shared state, float reduction, blocking, cancellation và chi phí tạo task.

**Phạm vi:** Java SE concurrency nói chung, theo Special Note của module. Các API hay cơ chế riêng của Spring không thuộc bài này vì đã có chương Spring riêng.

## 2. Fork/Join vận hành như thế nào?

Một `ForkJoinTask` đại diện cho công việc có thể fork và join. Các lớp quen thuộc:

| Thành phần | Mục đích | Ứng dụng |
| --- | --- | --- |
| `ForkJoinPool` | Điều phối worker, hàng đợi task và work stealing | Chạy task gốc qua `invoke/execute/submit` |
| `RecursiveTask<V>` | Hàm `compute()` trả kết quả `V` | Tính tổng, tìm max, chia rồi reduce |
| `RecursiveAction` | `compute()` không trả kết quả | Biến đổi từng đoạn array độc lập |
| `ForkJoinTask<V>` | Hỗ trợ `fork()`, `join()`, `invoke()` và trạng thái hoàn tất | Nền tảng của task trong pool |

Ví dụ một mảng 16 phần tử, leaf tối đa 4 phần tử:

~~~text
                  [0,16)
               /          \
           [0,8)          [8,16)
          /     \         /      \
       [0,4)  [4,8)   [8,12)  [12,16)
        leaf    leaf     leaf     leaf

  Các leaf xử lý tuần tự; node nội bộ kết hợp kết quả.
~~~

Work stealing nghĩa là một worker hết việc có thể lấy những task đang chờ của worker khác. Cơ chế này hữu ích khi các nhánh không hoàn thành cùng lúc. Tuy nhiên:
- Nếu chỉ có một leaf cực lớn, những worker rảnh không tự chia được phép tính.
- Nếu hàng triệu leaf chỉ làm một phép cộng, overhead có thể lớn hơn thời gian tính hữu ích.
- Nếu leaf bị chặn lâu vì mạng, database hay synchronized lock, work stealing không biến blocking I/O thành tác vụ CPU hiệu quả.

Fork/Join **phù hợp nhất khi công việc có thể phân rã, độc lập tương đối, đủ nặng và có phần kết hợp hợp lệ**.

## 3. Threshold: ngưỡng chuyển từ chia song song sang tính tuần tự

Quy tắc cổ điển:

~~~java
if (to - from <= threshold) {
    return computeSequentially(from, to);
}
~~~

Đây là snippet trong subclass của `RecursiveTask`, với các field/method cần được khai báo. Nếu đoạn còn lớn, chia thành hai phần:

~~~java
int length = to - from;
int mid = from + length / 2;
~~~

Công thức midpoint này an toàn hơn `(from+to)/2` về nguy cơ overflow của phép cộng index, trong phạm vi các chỉ số mảng không âm hợp lệ. Với khoảng `[from,to)`, hai child là:

~~~text
parent: [from, to)
left:   [from, mid)
right:  [mid, to)

left + right bao phủ parent đúng một lần.
~~~

### Threshold nhỏ và lớn có tác dụng trái chiều

**T quá nhỏ**:
- Có nhiều leaf và node nội bộ.
- Tăng allocation, fork/join, bookkeeping và áp lực GC.
- Leaf có thể xử lý quá ít việc để bù chi phí tạo task.
- Cây đệ quy sâu hơn; mỗi nhánh cần nhiều bước combine hơn.

**T quá lớn**:
- Ít leaf, khó dùng đủ các worker.
- Một leaf chậm có thể khiến các worker khác đợi.
- Công việc bất cân đối càng rõ nếu phân phối chi phí không đều.
- Có thể gần như xử lý tuần tự dù đang dùng ForkJoinPool.

**Tối ưu là điểm cân bằng** giữa độ song song và overhead. Threshold không phải số thread, không phải độ song song `P` và không phải số task phải chạy đồng thời.

### Điều kiện dừng cũng là vấn đề đúng đắn

Nếu `threshold=0` và một đoạn có đúng một phần tử, midpoint bằng đầu đoạn; một child có thể không nhỏ đi, gây đệ quy vô tận. Luôn validate `threshold >= 1` với chiến lược theo số phần tử. Với chiến lược theo work/cost, cần thêm điều kiện `length <= 1` để một phần tử cực nặng không bị chia mãi.

Nếu input rỗng và threshold dương, xử lý leaf rỗng theo quy tắc tuần tự của thuật toán (tổng bằng 0, max cần identity phù hợp, v.v.). Không chỉ kiểm thử các input có kích thước là lũy thừa hai.

## 4. Mẫu cơ sở: fork một nhánh, tự compute nhánh kia

Mẫu điều phối chuẩn bên trong `RecursiveTask`:

~~~java
@Override
protected Long compute() {
    int length = to - from;
    if (length <= threshold) {
        return sequentialSum(from, to);
    }

    int mid = from + length / 2;
    SumTask left = new SumTask(from, mid);
    SumTask right = new SumTask(mid, to);

    left.fork();                      // Tạo cơ hội cho worker khác.
    long rightValue = right.compute(); // Worker hiện tại làm việc.
    long leftValue = left.join();      // Đợi nhánh trái.
    return leftValue + rightValue;
}
~~~

Đây là snippet, không phải file chạy độc lập; `SumTask`, fields và method tuần tự cần khai báo.

Vì sao nó thường là baseline tốt?
1. Một nhánh được đưa vào hàng đợi fork/join để worker khác có thể thực hiện.
2. Nhánh còn lại được xử lý **trực tiếp** trên worker hiện tại, tránh phải tạo thêm một task chờ nhận CPU.
3. `join()` lấy kết quả nhánh fork; kết hợp chỉ sau khi có cả hai kết quả.
4. Mỗi task chịu trách nhiệm đúng khoảng `[from,to)` của nó.

Một mẫu khác là:

~~~java
left.fork();
right.fork();
return left.join() + right.join();
~~~

Mẫu này không nhất thiết sai, nhưng có thể thêm chi phí điều phối vì cả hai nhánh đều fork rồi caller đợi. Mẫu **fork một, compute một, join** thường ít overhead hơn cho divide-and-conquer cân bằng. Không phải quy tắc tối ưu tuyệt đối với mọi custom scheduler; cuối cùng vẫn phải đo.

### Không giữ lock không cần thiết khi join

Nếu parent giữ một lock mà child cũng cần, rồi parent `join()` trong lúc vẫn giữ lock, hai bên có thể chờ nhau mãi. Leaf nên làm công việc CPU độc lập, tránh chờ các tài nguyên đang được parent sở hữu. Mẫu reduction trả kết quả cục bộ giúp tránh shared lock.

## 5. Ví dụ độc lập 1: tính tổng với threshold=4

Tạo file **`ForkJoinSumDemo.java`**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int[] values;
        private final int from, to, threshold;
        private final AtomicInteger leafCount;

        SumTask(int[] values, int from, int to,
                int threshold, AtomicInteger leafCount) {
            if (threshold <= 0) {
                throw new IllegalArgumentException("threshold <= 0");
            }
            this.values = values;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
            this.leafCount = leafCount;
        }

        @Override
        protected Long compute() {
            int length = to - from;
            if (length <= threshold) {
                leafCount.incrementAndGet();
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += values[i];
                }
                return sum;
            }

            int mid = from + length / 2;
            SumTask left = new SumTask(
                    values, from, mid, threshold, leafCount);
            SumTask right = new SumTask(
                    values, mid, to, threshold, leafCount);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        int[] values = new int[32];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }

        AtomicInteger leaves = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long total = pool.invoke(
                    new SumTask(values, 0, values.length, 4, leaves));

            System.out.println("sum=" + total);
            System.out.println("leaves=" + leaves.get());
            System.out.println("threshold=4");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
~~~

Stdout khi thực thi thành công:

~~~text
sum=528
leaves=8
threshold=4
~~~

**Vì sao kết quả xác định?**
- Mảng có số `1..32`, nên tổng là `32*33/2=528`.
- Với threshold 4, cây chia `32 -> 16 -> 8 -> 4`, tạo **8 lá**, mỗi lá gồm 4 phần tử.
- `AtomicInteger` đếm số leaf thread-safe, không bỏ sót increment khi các worker cạnh tranh.
- `pool.invoke` chờ root task hoàn tất, bao gồm các `join` của nó, nên khi main in kết quả thì mọi leaf đã xong.

**Điểm quan trọng:** tám leaf **không đồng nghĩa tám thread**. Pool có parallelism mục tiêu bốn; có worker có thể xử lý nhiều leaf, và thứ tự thực thi không cố định.

Dùng `long` để cộng các số `int` giúp mở rộng miền giá trị, nhưng `long` vẫn có giới hạn; nếu bài toán có số rất lớn hoặc yêu cầu không overflow, cần kiểm tra miền đầu vào hoặc dùng toán học phù hợp.

## 6. Hình dạng cây là yếu tố có thể tính được

Với phép chia đôi cân bằng:
- Số leaf thường có bậc `N/T`, nhưng không luôn bằng chính xác `ceil(N/T)` vì phép chia nhị phân và điều kiện dừng.
- Độ sâu thường gần `ceil(log2(N/T))` khi `N>T` và split cân bằng.
- Nếu có `L` lá trong một cây nhị phân mà **mỗi node nội bộ có đúng hai child**, tổng node là `2L-1`.

Ví dụ `N=64`:

| Threshold | Số lá | Số node | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 1 | 64 | 127 | Nhiều task nhỏ, overhead cao cho work đơn giản |
| 4 | 16 | 31 | Nhiều cơ hội work stealing |
| 16 | 4 | 7 | Ít overhead nhưng có thể thiếu việc cho nhiều worker |
| 100 | 1 | 1 | Toàn bộ dữ liệu nằm trong một leaf |

Bảng **không đo thời gian** và không chứng minh threshold nào nhanh hơn. Trong một bài tính toán đắt tiền, nhiều lá có thể có ích; với phép cộng đơn giản, số node tăng có thể tốn hơn phần việc leaf.

### Ví dụ độc lập 2: số node thay đổi mà tổng không đổi

Tạo file **`ThresholdShapeDemo.java`**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ThresholdShapeDemo {
    private record Stats(long sum, int leaves, int nodes) {}

    private static final class Task extends RecursiveTask<Stats> {
        private final int[] data;
        private final int from, to, threshold;

        Task(int[] data, int from, int to, int threshold) {
            this.data = data;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected Stats compute() {
            int len = to - from;
            if (len <= threshold) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += data[i];
                }
                return new Stats(sum, 1, 1);
            }

            int mid = from + len / 2;
            Task left = new Task(data, from, mid, threshold);
            Task right = new Task(data, mid, to, threshold);

            left.fork();
            Stats r = right.compute();
            Stats l = left.join();

            return new Stats(
                    l.sum() + r.sum(),
                    l.leaves() + r.leaves(),
                    1 + l.nodes() + r.nodes());
        }
    }

    public static void main(String[] args) {
        int[] input = new int[64];
        for (int i = 0; i < input.length; i++) {
            input[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            for (int threshold : new int[]{1, 4, 16, 100}) {
                Stats result = pool.invoke(
                        new Task(input, 0, input.length, threshold));

                System.out.printf(
                        "threshold=%d sum=%d leaves=%d nodes=%d%n",
                        threshold, result.sum(),
                        result.leaves(), result.nodes());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac ThresholdShapeDemo.java
java ThresholdShapeDemo
~~~

Stdout:

~~~text
threshold=1 sum=2080 leaves=64 nodes=127
threshold=4 sum=2080 leaves=16 nodes=31
threshold=16 sum=2080 leaves=4 nodes=7
threshold=100 sum=2080 leaves=1 nodes=1
~~~

Tổng `1..64=64*65/2=2080` không đổi vì mọi cách chia đều xử lý toàn bộ dữ liệu đúng một lần. Kết quả của `Stats` được tổng hợp sau `join` thay vì cập nhật một bộ đếm task thường có data race.

**Không dùng thời gian chạy vài chục phần tử của demo này để quyết định threshold thực tế.** Nó chỉ làm rõ mối liên hệ giữa ngưỡng và số node, không đo hiệu năng production.

## 7. RecursiveAction: chia và biến đổi mảng không cần kết quả trả về

`RecursiveTask<V>` dùng khi các child tạo kết quả rồi merge, còn `RecursiveAction` dùng khi không cần trả giá trị. Ví dụ: các task làm việc trên **các đoạn mảng không chồng lấn**.

Tạo file **`RecursiveActionDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class RecursiveActionDemo {
    private static final class DoubleRange extends RecursiveAction {
        private final int[] data;
        private final int from, to, threshold;

        DoubleRange(int[] data, int from, int to, int threshold) {
            if (threshold < 1) {
                throw new IllegalArgumentException("threshold < 1");
            }
            this.data = data;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected void compute() {
            int length = to - from;
            if (length <= threshold) {
                for (int i = from; i < to; i++) {
                    data[i] *= 2;
                }
                return;
            }

            int mid = from + length / 2;
            DoubleRange left = new DoubleRange(
                    data, from, mid, threshold);
            DoubleRange right = new DoubleRange(
                    data, mid, to, threshold);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) {
        int[] values = new int[12];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new DoubleRange(
                    values, 0, values.length, 3));

            System.out.println(Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RecursiveActionDemo.java
java RecursiveActionDemo
~~~

Stdout:

~~~text
[2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
~~~

Mỗi index thuộc một leaf duy nhất; các task không cùng ghi một phần tử. Sau khi `pool.invoke` trả về, main đọc mảng đã được biến đổi. Điều này **không có nghĩa** mọi shared mutable object sẽ an toàn nếu được chia theo Fork/Join: nếu hai task cùng sửa một field, hoặc nhiều field có invariant chung, vẫn cần đồng bộ/giao thức cập nhật đúng.

Chia theo dải liên tiếp có thể giúp tính locality/cache khi quét mảng. Tuy nhiên hiệu năng còn tùy các thao tác tại leaf, kích thước dữ liệu và hệ thống bộ nhớ.

## 8. Khi nào threshold theo số phần tử là sai đại diện cho công việc?

Trong ví dụ tính tổng, mỗi phần tử tốn khoảng một phép cộng; số phần tử có thể dùng làm ước lượng work. Nhưng một thuật toán tìm kiếm/giải mã/phân tích dữ liệu có thể có cost rất khác nhau giữa các phần tử:

~~~text
index:  0  1  2  3  4  5  6  7
cost:   1  1  1  9  1  1  1  1
~~~

Nếu chia đều bốn phần tử mỗi bên, work ước tính là:
- Nhánh trái: `1+1+1+9=12`.
- Nhánh phải: `1+1+1+1=4`.

Cả hai nhánh có kích thước bằng nhau nhưng worker bên trái làm nhiều việc hơn. Vì thế, nhiều task có thể **rảnh chờ một nhánh nặng**.

### Những cách chia khác

- **Theo cost ước tính:** leaf nếu `sumEstimatedCost <= costThreshold`.
- **Theo prefix cost:** chọn vị trí chia sao cho cost của hai phía gần cân bằng; dùng prefix sums để lấy cost đoạn O(1).
- **Theo nhánh cây:** tách các subtree độc lập thay vì chia array thành hai nửa tùy ý.
- **Theo độ sâu:** giới hạn depth để tránh cây task nở quá lớn; thường kết hợp với kích thước/cost.
- **Theo ngân sách task:** ngừng chia khi số task đã đủ, phải có quản lý đồng bộ nếu budget được chia sẻ.
- **Theo mức bất cân đối quan sát được:** sinh thêm task khi còn work đáng kể, nhưng tránh instrumentation tốn hơn việc thật.

Không có một splitter lý tưởng cho mọi workload. Việc **ước lượng work** và tìm weighted midpoint cũng có chi phí. Một thuật toán theo cost O(N) ở mỗi node có thể khiến overhead split tăng mạnh; với dữ liệu lớn, cân nhắc prefix sums + binary search hoặc heuristic có chi phí nhỏ hơn.

## 9. Ví dụ độc lập 4: threshold theo trọng số, có fallback khi một phần tử quá nặng

Tạo file **`WeightedSplitDemo.java`**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class WeightedSplitDemo {
    private record Result(long total, int leaves, long maxLeafCost) {}

    private static final class WorkTask extends RecursiveTask<Result> {
        private final long[] prefix;
        private final int from, to;
        private final long threshold;

        WorkTask(long[] prefix, int from, int to, long threshold) {
            this.prefix = prefix;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected Result compute() {
            long cost = prefix[to] - prefix[from];

            // Một phần tử không thể chia thêm bằng index.
            if (to - from <= 1 || cost <= threshold) {
                return new Result(cost, 1, cost);
            }

            int bestMid = from + 1;
            long bestDiff = Long.MAX_VALUE;

            for (int mid = from + 1; mid < to; mid++) {
                long leftCost = prefix[mid] - prefix[from];
                long rightCost = prefix[to] - prefix[mid];
                long diff = Math.abs(leftCost - rightCost);

                if (diff < bestDiff) {
                    bestDiff = diff;
                    bestMid = mid;
                }
            }

            WorkTask left = new WorkTask(
                    prefix, from, bestMid, threshold);
            WorkTask right = new WorkTask(
                    prefix, bestMid, to, threshold);

            left.fork();
            Result b = right.compute();
            Result a = left.join();

            return new Result(
                    a.total() + b.total(),
                    a.leaves() + b.leaves(),
                    Math.max(a.maxLeafCost(), b.maxLeafCost()));
        }
    }

    public static void main(String[] args) {
        int[] weights = {1, 1, 1, 9, 1, 1, 1, 1};
        long[] prefix = new long[weights.length + 1];

        for (int i = 0; i < weights.length; i++) {
            prefix[i + 1] = prefix[i] + weights[i];
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            Result r = pool.invoke(new WorkTask(
                    prefix, 0, weights.length, 4));

            System.out.println("totalCost=" + r.total());
            System.out.println("leafTasks=" + r.leaves());
            System.out.println("maxLeafCost=" + r.maxLeafCost());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac WeightedSplitDemo.java
java WeightedSplitDemo
~~~

Stdout:

~~~text
totalCost=16
leafTasks=3
maxLeafCost=9
~~~

**Giải thích từng split:**
1. Tổng cost là 16; đoạn gốc có 8 phần tử nên còn các midpoint hợp lệ từ 1 tới 7.
2. Chọn điểm chia tốt nhất sau phần tử ở index 3: trái `[1,1,1,9]` cost=12, phải `[1,1,1,1]` cost=4.
3. Nhánh phải cost=4 thỏa threshold và trở thành leaf.
4. Nhánh trái cost=12 chia thành `[1,1,1]` cost=3 và `[9]` cost=9.
5. Cả hai là leaf; phần tử đơn có cost=9 vượt ngưỡng nhưng **không thể chia nhỏ thêm bằng vị trí mảng**.
6. Tổng có ba leaf, tổng cost 16 và leaf cost lớn nhất 9.

**Giới hạn rất quan trọng:** chương trình này minh họa **phân hoạch chi phí ước tính**, chứ không thực hiện CPU work tỷ lệ 1:1 với các weights. Không so thời gian chạy của nó với phép chia đều để kết luận về speedup. Trong ứng dụng thật, estimated cost phải đủ tương quan với chi phí thực; nếu không, splitter theo trọng số có thể làm chương trình chậm hơn.

Để triển khai trên dữ liệu rất lớn, cần kiểm soát chi phí tính prefix, chi phí scan midpoint, overflow khi cộng cost và khả năng nhiều phần tử có estimated weight=0. Đối với dữ liệu động hoặc tìm kiếm, chi phí thực có thể chỉ được biết sau khi đi vào nhánh.

## 10. Công thức tư duy về work, span và overhead

Đặt:
- `N` = số đơn vị dữ liệu.
- `P` = mức song song thực tế có thể dùng.
- `T` = threshold.
- `W` = tổng work hữu ích nếu tính tuần tự.
- `S` = critical path/span: độ dài chuỗi công việc phụ thuộc dài nhất.
- `H` = overhead Fork/Join, allocation, scheduling, join, cache/GC.

Một trực giác lý tưởng hóa:

~~~text
Parallel runtime bị ràng buộc bởi:
  W / số worker thực sự hữu ích,
  critical path S,
  overhead H,
  và giới hạn memory/cache/contended resources.
~~~

Giảm threshold có thể tăng số leaf và làm các worker bớt nhàn rỗi, nhưng đồng thời làm `H` tăng. Tăng threshold giảm `H` nhưng có thể làm `S` của một leaf dài và thiếu parallel slack. Không có công thức closed-form nào chỉ dựa vào `N` và `P` để chọn threshold tối ưu trong mọi workload.

### Ước lượng từ số worker chỉ để bắt đầu thử nghiệm

Một cách **khởi tạo vòng tuning**, nếu cost tương đối đều:
- Chọn mục tiêu có **nhiều leaf hơn số worker** vài lần, để work stealing có lựa chọn.
- Dùng `T ≈ N/(P*k)` với một vài `k` thử nghiệm (ví dụ 4 hoặc 8) để có điểm xuất phát.
- Rồi đo các ngưỡng lớn hơn/nhỏ hơn nhiều lần theo cấp số nhân.

Đây **không** phải khuyến nghị mặc định. Khi mỗi phần tử rất rẻ, `T` có thể cần lớn hơn rất nhiều; khi mỗi đơn vị rất nặng hoặc độ lệch work cao, threshold nhỏ hơn và split theo cost có thể hữu ích.

Nếu input nhỏ, chi phí khởi tạo/điều phối Fork/Join có thể còn lớn hơn chạy sequential trực tiếp. Một ứng dụng có thể cần **ngưỡng thứ nhất quyết định có parallelize toàn bộ không**, sau đó **ngưỡng thứ hai chia leaf trong pool**.

## 11. Tuning threshold đúng phương pháp

Không nên viết một vòng lặp đo một lần `System.nanoTime()` rồi kết luận. Microbenchmark Java chịu ảnh hưởng JIT, warm-up, allocation, GC, OS scheduling và contention. **JMH** là một công cụ phù hợp hơn để đo microbenchmark có kiểm soát.

Checklist thực nghiệm:
1. Chọn cùng input, cùng thuật toán và **same correctness result** cho mọi ngưỡng.
2. Có baseline **tuần tự**, không chỉ so các cấu hình Fork/Join.
3. Thử nhiều kích thước input: nhỏ, vừa, lớn.
4. Thử các ngưỡng theo cấp số nhân, ví dụ 128, 512, 2.048, 8.192, rồi thu hẹp vùng tốt.
5. Thử các pool parallelism hợp lý với môi trường (chẳng hạn 1, 2, 4, 8 nếu máy hỗ trợ).
6. Thử workload có **chi phí đều** và **chi phí bị lệch**; một threshold tốt cho mảng số có thể tệ cho cây tìm kiếm.
7. Warm-up và chạy nhiều measurement iterations; xem phân phối, không lấy một sample “may mắn”.
8. Đảm bảo kết quả thực sự được sử dụng/kiểm tra; tránh để compiler tối ưu biến mất workload giả.
9. Không tính tạo data, in console hoặc thao tác I/O ngoài mục tiêu benchmark vào thời gian compute khi mục tiêu là so split cost.
10. Quan sát latency, throughput, GC, allocation, active worker và số leaf/task.
11. Ghi cấu hình JVM, CPU, số worker và môi trường máy: kết quả có thể không lặp lại trên một hệ thống khác.
12. Lựa chọn dựa trên cả **độ đúng** và hiệu năng; một implementation nhanh nhưng bỏ sót kết quả không có ý nghĩa.

### Không bịa stdout cho benchmark

Ví dụ snippet minh họa duration:

~~~java
long start = System.nanoTime();
long result = pool.invoke(task);
long elapsed = System.nanoTime() - start;

if (result != expected) {
    throw new AssertionError("wrong result");
}
System.out.println("elapsedNanos=" + elapsed);
~~~

Đây là snippet với `pool`, `task` và `expected` đã được định nghĩa, **không phải chương trình độc lập**. Giá trị `elapsedNanos` không có stdout cố định; phụ thuộc JVM/máy/scheduler. Nó chỉ cho thấy cách lấy duration đơn giản, **không thay JMH**.

### Những con số chẩn đoán không phải kết quả đúng đắn

`ForkJoinPool.getStealCount()`, `getQueuedTaskCount()` và số active worker có thể hỗ trợ phân tích. Chúng thay đổi trong lúc pool chạy và có thể mang tính snapshot/ước lượng; không lấy một số đo tức thời làm bằng chứng chính xác về mọi lần work stealing.

Quan trọng hơn là: tổng kết quả đúng chưa? số leaf có hợp lý? worker có bị rảnh vì một nhánh nặng không? throughput/latency tăng hay giảm khi thay threshold?

## 12. Threshold theo số phần tử, cost và depth: bảng lựa chọn

| Loại ngưỡng | Điều kiện dừng | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Count | `to-from <= T` | Dễ cài đặt, ít overhead | Không phản ánh cost lệch |
| Cost | `estimatedCost <= C` | Gần work thực hơn nếu estimate tốt | Tốn công ước lượng và split |
| Depth | `depth >= D` | Giới hạn độ sâu cây | Cùng depth có thể khác work |
| Task budget | Đạt giới hạn task được phép tạo | Hạn chế allocation | Cần phối hợp budget đúng concurrency |
| Hybrid | `length<=T || depth>=D` | Chống chia quá sâu | Có nhiều tham số phải tuning |
| Per-node heuristic | Tính độ khó/độ lệch | Hữu ích với cây tìm kiếm | Heuristic có thể sai/đắt |

### Cost-based threshold không tự bảo đảm cân bằng

Nếu dữ liệu có một phần tử cực nặng không thể tách, việc đặt threshold cost nhỏ hơn phần tử ấy không thể chia chính nó thành nhiều core. Cần đổi **đơn vị phân hoạch**: phân rã bên trong phần tử hoặc dùng thuật toán khác. Đây là giới hạn của bài toán, không phải bug của ForkJoinPool.

### Budget chung có thể tạo contention

Nếu các task cùng đọc/ghi một biến `int tasksRemaining` không đồng bộ, đó là data race. Nếu dùng một `AtomicInteger` được mọi nhánh cập nhật liên tục, ta có thể tạo một điểm contention mới. Có thể phân phối ngân sách theo cây hoặc quyết định chia dựa vào state local để tránh một global counter nóng.

## 13. Những giới hạn và lỗi thường gặp

### 13.1. Split sai khiến trùng hoặc mất dữ liệu

Đừng tùy tiện dùng hai khoảng đóng như `[from,mid]` và `[mid,to]` nếu thuật toán không loại trừ phần tử midpoint; phần tử đó bị tính hai lần. Hãy thống nhất **[from,mid)** và **[mid,to)**, rồi kiểm tra với input N lẻ và input rỗng.

### 13.2. Shared mutable counter bị race

~~~java
sharedSum += leafSum;
~~~

Đây là snippet sai nếu nhiều leaf sửa `sharedSum` cùng lúc mà không có đồng bộ. Phép đọc–cộng–ghi không atomic. Đối với reduction, nên trả local result từ `RecursiveTask` và combine **sau join**, thay vì cập nhật một biến chung.

### 13.3. Chưa join đã đọc kết quả

Một `fork()` chỉ lên lịch công việc có thể chạy song song. Đừng đọc output buffer/result từ caller trong lúc worker vẫn đang sửa; sử dụng `join()` hoặc `pool.invoke()` để đợi các task hoàn tất theo contract.

### 13.4. Dùng nhiều thread cho workload chạm trần memory bandwidth

Đọc mảng lớn với phép tính quá đơn giản có thể bị giới hạn bởi băng thông RAM. Tăng số task không tăng tốc độ truy cập bộ nhớ vô hạn. Chia thành đoạn liên tiếp để tăng locality khi phù hợp và đo trên input thực.

### 13.5. False sharing

Hai worker ghi những vị trí logic khác nhau nhưng gần nhau trong cache line có thể gây invalidation/cache traffic. Điều này có thể xảy ra dù không có data race cùng một field. Kỹ thuật local accumulation rồi combine giúp giảm việc nhiều worker ghi một vùng shared liên tục.

### 13.6. Blocking I/O trong worker

Fork/Join phù hợp với công việc chia nhỏ CPU-bound; một leaf gọi network I/O, đọc database hay chờ lock dài có thể giữ worker mà không làm tính toán hữu ích. Với blocking có kiểm soát, `ForkJoinPool.ManagedBlocker` là API nâng cao; trong nhiều ứng dụng, một executor dành cho I/O hoặc API async rõ ràng sẽ dễ quản lý hơn.

**Không** coi work stealing là giải pháp tự động cho mọi blocking operation.

### 13.7. Float/double reduction không luôn bit-for-bit giống tuần tự

Cộng `double` chịu rounding và không kết hợp chính xác theo luật số thực. Một cây reduce có thứ tự gộp khác vòng lặp tuần tự, nên có thể ra kết quả cuối khác vài bit dù không có data race. Nếu kết quả tài chính hoặc yêu cầu tái lập bit-for-bit, phải chọn representation và quy tắc reduction phù hợp.

### 13.8. Exception ở child và partial result

Nếu leaf ném exception, caller `join()/invoke()` có thể nhận completion bất thường theo hợp đồng `ForkJoinTask`. Không được tự coi kết quả từ những nhánh thành công là kết quả toàn bộ bài toán nếu invariant yêu cầu xử lý hết input. Cần propagate/handle exception đúng và cleanup tài nguyên nếu leaf đã acquire.

### 13.9. Cancellation của ForkJoinTask không giống FutureTask

Theo hợp đồng Java SE, `ForkJoinTask.cancel(true)` **không sử dụng interruption để điều khiển xử lý** theo cách nhiều người quen từ `FutureTask`; `mayInterruptIfRunning` không làm task đang chạy chắc chắn dừng. Nếu cần hủy sớm, hãy dùng cooperative cancellation, token/flag được công bố an toàn, quản lý child tasks và xử lý cleanup/side effect. Không sử dụng `Thread.stop()` để cưỡng bức dừng code.

### 13.10. Tạo pool mới cho từng node

Không tạo `new ForkJoinPool()` cho mỗi lần split hoặc mỗi leaf. Cách làm đó tăng overhead, gây oversubscription và phá mô hình một nhóm worker chia sẻ work. Thông thường dùng **một pool phù hợp** cho toàn computation, có lifecycle rõ ràng; hoặc dùng common pool nếu contract và ownership cho phép.

## 14. Checklist khi review một thuật toán Fork/Join

1. Điều kiện dừng có bảo đảm tiến triển? Threshold dương và leaf cho length 0/1?
2. Khoảng split phủ đủ `[from,to)` đúng một lần?
3. Công việc ở các child có thực sự độc lập để chạy song song?
4. Có invariant chung giữa nhiều child không? Nếu có, ai bảo vệ?
5. Leaf work đủ lớn để bù overhead task không?
6. Có đủ leaf để worker rảnh có việc lấy không?
7. Có một vài leaf quá nặng vì cost skew không?
8. Cost estimate có đáng tin và chi phí tính estimate có nhỏ hơn lợi ích không?
9. Mẫu fork/compute/join có tránh fork hai nhánh không cần thiết không?
10. Result reduction có đúng theo phép toán và quy tắc số học không?
11. Có overflow hoặc floating-point rounding làm thay đổi yêu cầu correctness không?
12. Có I/O/lock dài khiến worker bị block không?
13. Exception của leaf có được propagate và không tạo success giả không?
14. Cancellation có thực sự đến được các leaf đang chạy không?
15. Pool có được sở hữu/quản lý đúng, không shutdown pool dùng chung vì một request?
16. Đã so baseline tuần tự với nhiều N, nhiều threshold và nhiều loại input chưa?
17. Benchmark có warm-up và đủ iterations, không bị logging/GC bất thường thống trị?
18. Có quan sát leaf count, allocation, p95/p99 latency và throughput không?
19. Với dữ liệu N lẻ, N=0, N=1, một phần tử heavy, tất cả kết quả vẫn đúng chứ?
20. Đã ghi lại threshold được chọn dựa trên workload và điều kiện máy nào?

## 15. Bài tập và lời giải

### Bài 1 — Đếm node

Nếu N=32 và threshold=8, cây chia đôi cân bằng có bao nhiêu leaf?

**Đáp án:** `32 -> 16 -> 8`, có 4 leaf và `2*4-1=7` node. Số leaf không bằng số worker chắc chắn đang chạy.

### Bài 2 — Input không là lũy thừa của 2

Với khoảng `[0,10)` và threshold 3, chia đôi bằng midpoint floor. Các leaf là gì?

**Đáp án:** `[0,2)`, `[2,5)`, `[5,7)`, `[7,10)`. Tổng độ dài bằng 10, không trùng và không sót.

### Bài 3 — Threshold 0

Tại sao threshold=0 là sai khi length=1?

**Đáp án:** Nếu leaf condition là `length<=0`, đoạn length=1 vẫn bị split; một nhánh có thể tiếp tục length=1, recursion không tiến triển. Validate threshold dương hoặc thêm base case cho length<=1.

### Bài 4 — Ngưỡng và hiệu năng

Vì sao threshold=1 không nhất thiết nhanh hơn threshold=4 dù có nhiều task hơn?

**Đáp án:** Càng nhiều task càng tốn scheduling, allocation, fork/join, GC; nếu leaf work rẻ, overhead áp đảo. Cần benchmark.

### Bài 5 — Cost imbalance

Mảng cost `[1,1,1,9,1,1,1,1]` chia làm hai nửa bốn phần tử có cân bằng work không?

**Đáp án:** Không. Trái cost=12, phải cost=4. Chia theo số phần tử cân bằng nhưng theo chi phí thì lệch.

### Bài 6 — Một phần tử nặng hơn threshold

Tại sao leaf chứa duy nhất phần tử cost=9 được phép tồn tại khi threshold=4?

**Đáp án:** Không có điểm split hợp lệ theo index cho một phần tử. Nếu muốn chia tiếp, phải thay đổi đơn vị công việc.

### Bài 7 — SharedSum

Hai RecursiveTask cùng cập nhật `sharedSum += partial` có an toàn không?

**Đáp án:** Không nếu sharedSum là biến thường. Nên dùng local result và join rồi combine; hoặc có synchronization nếu thật sự cần shared state.

### Bài 8 — Khi nào dùng RecursiveAction?

**Đáp án:** Khi leaf thực hiện side effect đã được phân vùng độc lập (ví dụ sửa các đoạn mảng không chồng lấn) và parent không cần nhận một kết quả `V`. Vẫn phải đảm bảo shared state không có race.

### Bài 9 — Số core và threshold

Pool có parallelism 8, nhưng input chỉ có 8 phần tử và mỗi phần tử tốn một phép cộng. Có nên dùng threshold=1?

**Đáp án:** Không nhất thiết; việc tạo task có thể đắt hơn toàn bộ phép tính. Xử lý tuần tự có thể hợp lý hơn.

### Bài 10 — Floating-point

Vì sao parallel `double` sum đôi khi khác kết quả vòng lặp tuần tự?

**Đáp án:** Floating-point addition không associative chính xác bit-for-bit, và cây reduction thay đổi thứ tự cộng.

### Bài 11 — Blocking I/O

Đưa công việc download file vào hàng nghìn leaf của ForkJoinPool có luôn tận dụng CPU tốt không?

**Đáp án:** Không. Worker có thể bị block; cần dùng API I/O/executor phù hợp hoặc managed blocking nếu có lý do cụ thể.

### Bài 12 — Cancellation

Gọi `ForkJoinTask.cancel(true)` có bảo đảm interrupt worker để leaf thoát tức thì không?

**Đáp án:** Không. Hợp đồng của ForkJoinTask không dùng interruption để điều khiển computation. Cần thiết kế cancellation hợp tác.

## 16. Tổng kết

**Chiến lược chia nhỏ** quyết định hình dạng và mức cân bằng của cây công việc. **Threshold** quyết định khi nào dừng tạo task mới và xử lý tuần tự. Cả hai ảnh hưởng mạnh đến khả năng tận dụng work stealing và chi phí scheduling.

Với dữ liệu đồng đều, hãy bắt đầu từ **split [from,to) thành hai khoảng nửa mở**, leaf khi `length<=threshold`, dùng **fork một nhánh, compute nhánh còn lại, join**, rồi kiểm tra tính đúng đắn. Nếu cost phân bố lệch, hãy cân nhắc **cost-based partition**, độ sâu/ngân sách task hoặc thay đổi đơn vị chia. Không chọn threshold chỉ theo số lõi hay từ một ví dụ N nhỏ.

**Không có threshold tốt nhất cho mọi workload**. Ngưỡng quá nhỏ gây overhead, quá lớn thiếu parallelism. Quyết định cuối cùng cần dựa trên **correctness + baseline tuần tự + benchmark có kiểm soát**.

## Tài liệu tham khảo Java SE 17

- [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, parallelism và metrics.
- [ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, cancellation semantics.
- [RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): divide-and-conquer trả kết quả.
- [RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): chia công việc không trả kết quả.
- [ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): blocking có quản lý.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory model và happens-before.
- [JMH (OpenJDK)](https://openjdk.org/projects/code-tools/jmh/): Java Microbenchmark Harness.
