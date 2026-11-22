# Fork/Join ứng dụng: tổng hợp mảng, cây và tính toán đệ quy trong Java

## 1. Mục tiêu và bối cảnh

Nhiều bài toán tính toán có cấu trúc “**chia nhỏ một bài toán lớn thành các phần độc lập, xử lý từng phần, rồi kết hợp kết quả**”. Ví dụ:

- Tính tổng, min/max hoặc thống kê trên một mảng lớn.
- Tính tổng trọng số, đếm node hoặc tổng hợp thuộc tính của cây.
- Sắp xếp mảng bằng merge sort, xử lý dữ liệu theo từng vùng.
- Thực thi một thuật toán đệ quy mà các nhánh có thể tính độc lập.

Trong Java, **Fork/Join Framework** cung cấp `ForkJoinPool` và các `ForkJoinTask` để tổ chức kiểu **divide and conquer** này. Nó đặc biệt thích hợp với công việc **CPU-bound**, các nhánh độc lập, có thể chia đủ lớn để bù lại chi phí tạo/lập lịch task.

**Ý tưởng cốt lõi:**

```text
                  Bài toán ban đầu
                        |
                      chia
                  /           \
             bài toán A     bài toán B
                |               |
          xử lý hoặc chia    xử lý hoặc chia
                \               /
                 kết hợp kết quả
                        |
                      kết quả
```

Một task Fork/Join điển hình có **ngưỡng dừng chia (threshold)**. Nếu phần việc nhỏ hơn ngưỡng, task tính **tuần tự**; nếu lớn, task tách nhánh. Không có threshold hợp lý, chia từng phần tử hoặc từng node thành task riêng có thể tốn nhiều thời gian hơn tính tuần tự.

Bài học nằm trong module **Java Advance - concurrency → Fork/Join**, chỉ dùng **Java concurrency nói chung**, không phụ thuộc Spring hay framework nào.

## 2. Các thành phần API cần biết

| Thành phần | Vai trò |
| --- | --- |
| `ForkJoinPool` | Pool worker tối ưu để thực thi các task dạng Fork/Join, có hỗ trợ work stealing |
| `ForkJoinTask<V>` | Lớp nền tảng biểu diễn công việc có kết quả kiểu `V` |
| `RecursiveTask<V>` | Task đệ quy có **giá trị trả về**; triển khai `compute()` |
| `RecursiveAction` | Task đệ quy **không trả giá trị**; triển khai `compute()` |
| `fork()` | Lên lịch một task để có thể chạy bất đồng bộ |
| `join()` | Lấy kết quả task, đợi khi chưa xong |
| `compute()` | Thực thi phần việc của task ngay trong thread gọi `compute()` |
| `invoke()`, `ForkJoinPool.invoke(task)` | Thực thi và đợi kết quả của task |
| `invokeAll(...)` | Thực thi nhóm task Fork/Join và chờ các task đó hoàn tất theo contract |

**Phân biệt quan trọng:** `fork()` thường **không trả kết quả tính toán của task**; nó trả về chính task để có thể `join()` về sau. Một lời gọi `compute()` bình thường thực hiện task ngay, không có nghĩa tự tạo thêm thread.

### Mẫu RecursiveTask

```java
class Task extends RecursiveTask<Long> {
    @Override
    protected Long compute() {
        if (isSmallEnough()) {
            return computeSequentially();
        }

        Task left = splitLeft();
        Task right = splitRight();

        left.fork();
        Long rightValue = right.compute();
        Long leftValue = left.join();

        return combine(leftValue, rightValue);
    }
}
```

Đây là **mã khung minh họa**, các helper do ứng dụng định nghĩa. Ý nghĩa của thứ tự:

1. `left.fork()`: đưa nhánh trái vào cơ chế lên lịch Fork/Join, có thể được worker khác lấy.
2. `right.compute()`: worker hiện tại tự xử lý nhánh phải, tránh chỉ tạo task rồi chờ.
3. `left.join()`: lấy kết quả nhánh trái khi cần.
4. `combine`: kết hợp hai kết quả đã hoàn thành.

**Không nên viết** `left.fork(); left.join(); right.compute();` khi muốn cả hai nhánh có cơ hội chạy song song: gọi `join()` ngay sau `fork()` có thể khiến thread hiện tại đợi nhánh trái trước khi làm nhánh phải, làm mất một phần cơ hội song song.

## 3. Cơ chế work stealing, không phải “một thread mỗi task”

`ForkJoinPool` quản lý một nhóm worker. Worker tạo ra nhiều task nhỏ, và trong những tình huống phù hợp, worker nhàn rỗi có thể **lấy việc từ hàng đợi của worker khác**. Đây là **work stealing**.

```text
Worker 1                         Worker 2
--------                         --------
task gốc
  fork(task A)  ----> hàng đợi     có thể steal task A
  compute(B)                      compute(A)
  join(A)     <---- kết quả       hoàn thành A
  combine(A, B)
```

Sơ đồ chỉ minh họa một cách xen kẽ có thể xảy ra; **không cam kết** task A chắc chắn do worker 2 chạy. Trong hệ thống thực, worker 1 cũng có thể tự hoàn thành A, hoặc một worker khác lấy task.

**Vì sao phù hợp với bài toán đệ quy bất quy tắc?** Các nhánh có thể lớn/nhỏ khác nhau. Work stealing giúp phân phối phần việc còn lại thay vì gán cứng “worker số 1 làm nửa trái, worker số 2 làm nửa phải”.

Tuy nhiên:

- Work stealing không làm một thuật toán sai trở nên đúng.
- Công việc quá nhỏ khiến overhead chia task/lập lịch/đồng bộ chiếm ưu thế.
- Một nhánh tuần tự rất dài có thể là **critical path** khiến nhiều core phải chờ.
- Chặn worker bằng I/O lâu hoặc `Thread.sleep()` không phải workload lý tưởng.
- Không có bảo đảm thứ tự thực thi các nhánh; kết quả phải được thiết kế độc lập với thứ tự đó.

## 4. Ứng dụng 1: tính tổng mảng bằng RecursiveTask<Long>

Bài toán: với một mảng `long[]` có nhiều phần tử, tính tổng. Phép cộng là một phép **reduction** có phần tử đơn vị `0`, nên có thể tính tổng từng đoạn không giao nhau rồi cộng lại:

\[
\operatorname{sum}(a[l:r]) =
\operatorname{sum}(a[l:m]) +
\operatorname{sum}(a[m:r])
\]

Với `m = (l + r) / 2`. Dùng quy ước đoạn **nửa mở** `[from, to)` để tránh trùng phần tử tại mốc chia.

### Mã chạy độc lập

Tạo tệp `ForkJoinArraySumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinArraySumDemo {
    private static final class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2;

        private final long[] values;
        private final int from;
        private final int to;

        SumTask(long[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            int length = to - from;

            if (length <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += values[i];
                }
                return sum;
            }

            int mid = from + length / 2;
            SumTask left = new SumTask(values, from, mid);
            SumTask right = new SumTask(values, mid, to);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();

            return leftResult + rightResult;
        }
    }

    private static long sequentialSum(long[] values) {
        long sum = 0;
        for (long value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        long[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            long total = pool.invoke(
                    new SumTask(values, 0, values.length));

            System.out.println("parallel sum=" + total);
            System.out.println("sequential sum="
                    + sequentialSum(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac ForkJoinArraySumDemo.java
java ForkJoinArraySumDemo
```

Output:

```text
parallel sum=36
sequential sum=36
```

### Diễn biến cụ thể của phép chia

Với mảng 8 phần tử và threshold `2`:

```text
[1,2,3,4,5,6,7,8]           tổng = 36
         /      \
[1,2,3,4]                  [5,6,7,8]
   /   \                      /   \
[1,2] [3,4]                [5,6] [7,8]
  3     7                    11    15
     10                          26
                  36
```

Những đoạn dài ≤ 2 được tính bằng một vòng `for` thông thường; các đoạn lớn hơn mới tiếp tục chia. Mỗi `SumTask` chỉ cần giữ **tham chiếu mảng và hai chỉ số**, không sao chép các nửa mảng thành `long[]` mới.

### Vì sao phép cộng không bị data race?

Các worker **chỉ đọc** mảng đầu vào. Mỗi task dùng biến `sum` **cục bộ** trong `compute()` hoặc giữ kết quả trả về `Long` riêng. Không có một biến global mutable kiểu `static long total` bị mọi worker cùng `+=`.

Việc gọi `join()` đảm bảo caller chỉ kết hợp kết quả sau khi nhánh tương ứng hoàn thành, cùng các quan hệ đồng bộ/bộ nhớ do Fork/Join API cung cấp. Nếu cần mảng được đọc nhất quán, các writer không được sửa mảng đồng thời trong lúc tính tổng mà không có giao thức đồng bộ tương ứng.

### Các trường hợp biên

- **Mảng rỗng:** `length = 0`, nhánh tuần tự trả `0`.
- **Mảng chỉ có một phần tử:** trả chính giá trị phần tử.
- **Phần chia không chồng lấn:** `[from, mid)` và `[mid, to)`, không đếm trùng/thiếu.
- **Số âm:** phép cộng vẫn hoạt động.
- **Overflow:** `long` vẫn có thể overflow nếu tổng vượt phạm vi `long`. Cần `Math.addExact` hoặc `BigInteger` nếu domain yêu cầu phát hiện/không chấp nhận wrap-around.
- **Mảng mutable:** việc tham chiếu cùng mảng là an toàn **cho đọc đồng thời**, không có nghĩa được sửa nội dung bất kỳ lúc nào.

### Chọn threshold cho mảng thực tế

`THRESHOLD=2` được chọn để sơ đồ dễ hiểu, **không phải giá trị tối ưu trong production**. Với hàng triệu phần tử, threshold quá nhỏ tạo số task rất lớn. Nên thử những kích thước chunk lớn hơn, đo bằng benchmark và xét chi phí mỗi phần tử.

Nếu mỗi phần tử chỉ được cộng một số `long`, công việc trong một chunk rất rẻ, do đó cần chunk đủ lớn mới bù overhead của Fork/Join. Nếu mỗi phần tử phải tính toán nặng, một chunk nhỏ hơn có thể hợp lý.

## 5. Công thức tổng quát: map – reduce trên mảng

Tổng mảng có thể tổng quát thành:

1. **Map:** biến đổi từng phần tử, ví dụ `x -> x * x`.
2. **Reduce:** kết hợp các kết quả, ví dụ cộng.
3. **Identity:** giá trị trung tính, ví dụ `0` cho tổng, `1` cho tích.

Một task tính tổng bình phương có thể dùng leaf:

```java
long sum = 0;
for (int i = from; i < to; i++) {
    long x = values[i];
    sum += x * x;
}
return sum;
```

Đây là **đoạn minh họa** bên trong `compute()`, với `from`, `to`, `values` do lớp task quản lý. Các nhánh vẫn cộng kết quả như ví dụ trước.

Muốn một reduction song song có kết quả đáng tin cậy cần chú ý **tính kết hợp (associativity)** của phép gộp. Với phép cộng số nguyên trong miền không tràn, nhóm hạng tử khác nhau vẫn cùng kết quả toán học. Với `double`/`float`, phép cộng dấu phẩy động **không hoàn toàn kết hợp**:

\[
(a+b)+c \ne a+(b+c)
\]

trong một số trường hợp do rounding, infinity, NaN và mất độ chính xác. Vì vậy reduction song song có thể cho kết quả khác chút so với vòng lặp tuần tự hoặc giữa những cách nhóm phần việc khác nhau.

Nếu cần kết quả tài chính chính xác, cân nhắc `BigDecimal`, integer scaled value hoặc kiểu dữ liệu/chính sách số học phù hợp. Nếu cần tính bitwise reproducible, phải thiết kế thứ tự cộng và thuật toán ổn định theo yêu cầu, không mặc định mọi parallel reduction là bitwise identical.

## 6. Ứng dụng 2: tổng hợp node trong cây

Một cây có thể chứa số lượng node lớn. Với mỗi node, nếu nhánh trái và nhánh phải **độc lập**, tổng trọng số của cây là:

\[
S(node)=value(node)+S(left)+S(right)
\]

Với cây rỗng, `S(null)=0`.

```text
          10
         /  \
        5    7
       / \    \
      2   3    4

Tổng = 10 + 5 + 7 + 2 + 3 + 4 = 31
```

Cây khác mảng ở chỗ các nhánh có thể **không cân đối**. Fork/Join có cơ hội tận dụng work stealing khi một nhánh lớn hơn nhánh khác. Tuy nhiên, fork một task cho **mọi node** thường không hiệu quả: node lá quá nhỏ, số task nhiều và cây quá sâu có thể làm stack recursion lớn.

Một kỹ thuật hữu ích là đặt **giới hạn độ sâu song song**: đến một độ sâu nào đó, những cây con còn lại được tính tuần tự. Đây là một threshold đơn giản; với cây thật, có thể dựa trên **số node ước tính**, công việc ước tính của subtree hoặc profile.

### Mã chạy độc lập

Tạo tệp `ForkJoinTreeSumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinTreeSumDemo {
    record Node(long value, Node left, Node right) {}

    static long sequential(Node node) {
        if (node == null) {
            return 0;
        }
        return node.value()
                + sequential(node.left())
                + sequential(node.right());
    }

    static final class TreeSumTask extends RecursiveTask<Long> {
        private final Node node;
        private final int parallelDepth;

        TreeSumTask(Node node, int parallelDepth) {
            this.node = node;
            this.parallelDepth = parallelDepth;
        }

        @Override
        protected Long compute() {
            if (node == null) {
                return 0L;
            }

            if (parallelDepth <= 0
                    || (node.left() == null && node.right() == null)) {
                return sequential(node);
            }

            if (node.left() == null) {
                return node.value() + new TreeSumTask(
                        node.right(), parallelDepth - 1).compute();
            }

            if (node.right() == null) {
                return node.value() + new TreeSumTask(
                        node.left(), parallelDepth - 1).compute();
            }

            TreeSumTask left = new TreeSumTask(
                    node.left(), parallelDepth - 1);
            TreeSumTask right = new TreeSumTask(
                    node.right(), parallelDepth - 1);

            left.fork();
            long rightValue = right.compute();
            long leftValue = left.join();

            return node.value() + leftValue + rightValue;
        }
    }

    public static void main(String[] args) {
        Node tree = new Node(
                10,
                new Node(5,
                        new Node(2, null, null),
                        new Node(3, null, null)),
                new Node(7,
                        null,
                        new Node(4, null, null)));

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(new TreeSumTask(tree, 2));
            System.out.println("parallel tree sum=" + result);
            System.out.println("sequential tree sum="
                    + sequential(tree));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinTreeSumDemo.java
java ForkJoinTreeSumDemo
```

Output:

```text
parallel tree sum=31
sequential tree sum=31
```

### Tại sao tree task đúng?

- `Node` là một Java `record` chứa `value`, `left` và `right`. **Trong ví dụ** các node được tạo xong trước khi nộp task và không bị sửa trong quá trình tính; record không tự bảo đảm bất biến sâu cho mọi kiểu dữ liệu.
- Mỗi task chỉ **đọc** một cây con, nên không có nhiều writer tranh chấp trường `value`.
- Chỉ khi **cả hai nhánh có dữ liệu** và `parallelDepth > 0`, code mới fork một nhánh và compute nhánh kia.
- Nếu chỉ có một con, code tính tiếp trên thread hiện tại, không cần tạo thêm một task được fork để rồi đợi.
- Khi depth đã hết, `sequential(node)` xử lý phần còn lại tuần tự, giới hạn độ nở của cây task.
- Sau `left.join()`, kết quả nhánh trái đã sẵn sàng để cộng với nhánh phải.

### Cây không phải lúc nào cũng là tree thuần

Nhiều mô hình thực tế là **đồ thị (graph)** hoặc **DAG** có node chia sẻ:

```text
   Root
   /  \
  A    B
   \  /
    C    (C được tham chiếu từ cả A và B)
```

Nếu đếm node bằng hàm trên, node C có thể bị tính **hai lần**, vì code đệ quy theo **đường đi**, không khử trùng node. Nếu graph có chu trình, recursion còn có thể chạy vô hạn hoặc gây `StackOverflowError`.

Để xử lý graph cần định nghĩa rõ nghĩa nghiệp vụ:

- **Tổng theo path:** node xuất hiện trên hai đường đi được tính hai lần có thể đúng.
- **Tổng theo node duy nhất:** cần một cơ chế visited/deduplication an toàn khi chạy song song.
- **Graph có cycle:** cần cơ chế phát hiện vòng và quy tắc dừng.
- **DAG:** có thể dùng memoization của các subproblem bất biến, nhưng phải quản lý cạnh tranh cùng tính một node.
- Nếu tổng hợp phụ thuộc **thứ tự duyệt**, cần hợp đồng ordering cụ thể thay vì giả định work stealing giữ thứ tự.

Đừng đưa `HashSet<Node> visited` dùng chung cho mọi worker rồi sửa đồng thời không đồng bộ. Điều đó gây data race và sai kết quả; chọn cấu trúc concurrent và giao thức atomic thích hợp hoặc giải quyết dedup ở một pha riêng.

## 7. Bài toán bất quy tắc: cây lệch và phân chia không cân

Với mảng, mỗi lần chia đôi theo chỉ số thường cho hai phần có kích thước gần bằng nhau. Với cây, một subtree có thể chứa hàng triệu node, subtree kia chỉ có một lá.

```text
                   Root
                 /      \
       cây con lớn      node lá
        /      \
      ...      ...
```

Work stealing có thể giúp các worker lấy những task còn sẵn có ở nhánh lớn. Nhưng nếu thuật toán chỉ fork hai nhánh **ngay tại gốc**, sau đó tính tất cả node nhánh lớn tuần tự, các worker khác vẫn có thể nhàn rỗi. Threshold và chiến lược chia phải tạo ra **đủ task độc lập**.

Một độ sâu fork cố định, chẳng hạn `parallelDepth=2`, tạo tối đa một số lượng task có giới hạn nhưng có thể không phân bố đều trên cây lệch. Các hướng cải tiến:

- Lưu sẵn kích thước subtree (`size`) nếu cây immutable và việc xây dựng dữ liệu cho phép.
- Chỉ fork khi kích thước ước tính vượt threshold.
- Tách một nhánh lớn thành các frontier/subtree độc lập rồi giao vào pool.
- Dùng cấu trúc duyệt lặp với explicit stack nếu cây có thể rất sâu; đệ quy Java thông thường có thể gặp `StackOverflowError`.
- Tránh fork một task cho một leaf rất rẻ.
- Đo throughput và độ cân bằng workload thay vì dựa vào số core danh nghĩa.

**Đừng mặc định Fork/Join tự chia nhỏ một công việc tuần tự khó chia.** Pool chỉ lập lịch những task mà thuật toán thực sự tạo ra.

## 8. Ứng dụng 3: parallel merge sort bằng RecursiveAction

`RecursiveTask<T>` thích hợp khi task trả về một giá trị. Nhưng với thuật toán sắp xếp **sửa mảng đầu vào tại chỗ**, ta có thể dùng `RecursiveAction` (không có giá trị trả về) vì tác động của task là làm một đoạn mảng được sắp xếp.

**Merge sort**:

1. Nếu đoạn nhỏ, dùng `Arrays.sort` tuần tự.
2. Nếu lớn, chia đoạn thành trái/phải.
3. Sắp xếp hai đoạn không giao nhau bằng các subtask.
4. Đợi hai nhánh hoàn tất.
5. Trộn hai đoạn đã sắp xếp vào vùng của mảng phụ.
6. Copy vùng đã trộn về mảng gốc.

**Điểm dễ sai:** Nếu parent bắt đầu merge trước khi hai subtask sắp xếp xong, kết quả sai. `invokeAll`/`join` là ranh giới đồng bộ cần thiết.

### Mã chạy độc lập

Tạo tệp `ForkJoinMergeSortDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinMergeSortDemo {
    private static final class SortTask extends RecursiveAction {
        private static final int THRESHOLD = 3;

        private final int[] values;
        private final int[] temp;
        private final int from;
        private final int to;

        SortTask(int[] values, int[] temp, int from, int to) {
            this.values = values;
            this.temp = temp;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            int length = to - from;

            if (length <= THRESHOLD) {
                Arrays.sort(values, from, to);
                return;
            }

            int mid = from + length / 2;
            SortTask left = new SortTask(values, temp, from, mid);
            SortTask right = new SortTask(values, temp, mid, to);

            invokeAll(left, right);

            int i = from;
            int j = mid;
            int k = from;

            while (i < mid && j < to) {
                if (values[i] <= values[j]) {
                    temp[k++] = values[i++];
                } else {
                    temp[k++] = values[j++];
                }
            }
            while (i < mid) {
                temp[k++] = values[i++];
            }
            while (j < to) {
                temp[k++] = values[j++];
            }

            System.arraycopy(temp, from, values, from, length);
        }
    }

    public static void main(String[] args) {
        int[] values = {9, 4, 7, 2, 8, 1, 3, 6, 5};
        int[] temp = new int[values.length];

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new SortTask(
                    values, temp, 0, values.length));

            System.out.println("sorted="
                    + Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinMergeSortDemo.java
java ForkJoinMergeSortDemo
```

Output:

```text
sorted=[1, 2, 3, 4, 5, 6, 7, 8, 9]
```

### Tại sao nhiều task cùng dùng hai mảng vẫn an toàn?

Mọi task đều giữ tham chiếu tới cùng `values` và `temp`, nhưng có **ownership theo đoạn chỉ số**:

- Subtask trái chỉ được sửa `[from, mid)`.
- Subtask phải chỉ được sửa `[mid, to)`.
- Hai vùng **không giao nhau**, nên hai subtask không ghi cùng ô mảng.
- Parent chỉ merge sau khi `invokeAll(left, right)` hoàn thành; lúc đó hai đoạn đã sorted.
- Parent chỉ ghi `temp[from:to)` và copy lại `values[from:to)` sau khi con hoàn tất. Những task thuộc subtree khác làm trên đoạn không giao nhau.

Đó là một ví dụ **shared array nhưng có phân chia quyền ghi rõ ràng**: không nhất thiết phải đưa từng phần tử vào `AtomicIntegerArray` hoặc dùng `synchronized` cho mọi phép gán. Điều kiện đúng là các task phải **không có vùng ghi chồng lấn** cho tới khi parent join.

### Tính chất và chi phí

Merge sort có tổng công việc xấp xỉ `O(n log n)`. Với implementation này, mỗi parent merge đoạn của mình **tuần tự** sau khi các con sort xong, nên không phải mọi giai đoạn đều song song hoàn toàn. Một mảng phụ cỡ `O(n)` được dùng để merge; các task còn có overhead bổ sung.

**`THRESHOLD=3` chỉ để minh họa.** Với mảng thực tế, hãy benchmark threshold lớn hơn. `Arrays.parallelSort` có sẵn trong Java là lựa chọn nên xem xét trước khi tự triển khai parallel merge sort để sản xuất; nó được thiết kế/test cho trường hợp sort mảng, còn code tự viết đòi hỏi chứng minh correctness, ổn định, memory usage và hiệu năng.

## 9. Ứng dụng 4: tính toán đệ quy với Fibonacci và điều cần tránh

Fibonacci thường được dùng để minh họa hai nhánh đệ quy:

\[
F(n)=F(n-1)+F(n-2), \quad F(0)=0,\ F(1)=1.
\]

Nhìn qua, các nhánh có thể fork độc lập. Tuy nhiên, **Fibonacci đệ quy ngây thơ là ví dụ xấu về hiệu năng** vì cùng một giá trị `F(k)` được tính đi tính lại rất nhiều lần:

```text
                F(5)
              /      \
           F(4)      F(3)
           /  \      /  \
        F(3) F(2)  F(2) F(1)
        ...
```

`F(3)`, `F(2)` và những subproblem khác lặp lại. Fork/Join không tự thực hiện memoization và không làm thuật toán từ thời gian mũ thành tuyến tính.

Ta vẫn có thể viết **ví dụ hybrid có threshold** để thấy cơ chế, nhưng phải nói rõ: **đây là bài dạy về recursive task, không phải cách tối ưu để tính Fibonacci**.

### Mã chạy độc lập

Tạo tệp `ForkJoinFibonacciDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinFibonacciDemo {
    private static long sequentialFib(int n) {
        long a = 0;
        long b = 1;

        for (int i = 0; i < n; i++) {
            long next = a + b;
            a = b;
            b = next;
        }
        return a;
    }

    private static final class FibTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 16;
        private final int n;

        FibTask(int n) {
            this.n = n;
        }

        @Override
        protected Long compute() {
            if (n <= THRESHOLD) {
                return sequentialFib(n);
            }

            FibTask left = new FibTask(n - 1);
            FibTask right = new FibTask(n - 2);

            left.fork();
            long rightValue = right.compute();
            long leftValue = left.join();

            return leftValue + rightValue;
        }
    }

    public static void main(String[] args) {
        int n = 20;
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(new FibTask(n));
            System.out.println("fork/join F(20)=" + result);
            System.out.println("sequential F(20)="
                    + sequentialFib(n));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinFibonacciDemo.java
java ForkJoinFibonacciDemo
```

Output:

```text
fork/join F(20)=6765
sequential F(20)=6765
```

### Vì sao đây không phải thuật toán tối ưu?

`FibTask` chia thành `F(n-1)` và `F(n-2)` đến khi `n <= THRESHOLD`. Trong các phần chia trên ngưỡng, nhiều subproblem bị lặp. Cách tính tuần tự với hai biến ở `sequentialFib` chạy trong `O(n)` thời gian và `O(1)` bộ nhớ; với bài toán cần `F(n)` đơn thuần, cách này thường dễ hiểu, ít overhead và hiệu quả hơn.

Một số phương pháp tối ưu khác:

- **Dynamic programming/memoization:** mỗi `F(k)` chỉ tính một lần.
- **Fast doubling:** tính Fibonacci bằng công thức chia đôi chỉ số, có độ phức tạp xấp xỉ `O(log n)` phép bước số học (chưa tính chi phí số lớn).
- **BigInteger:** tránh overflow của `long` khi `n` lớn; `F(93)` đã vượt giá trị dương tối đa của `long`.

Nếu một bài toán đệ quy thực tế có **các nhánh độc lập và không trùng subproblem** hoặc chi phí mỗi nhánh rất lớn, Fork/Join mới có nhiều cơ hội mang lại lợi ích hơn Fibonacci ngây thơ.

## 10. Chọn giữa RecursiveTask và RecursiveAction

**Chọn `RecursiveTask<V>` khi mỗi phần trả một giá trị cần reduce:**

- Tổng mảng, đếm node, min/max cây.
- Tính hash hay một báo cáo con.
- Tính số đường đi trong một cây với luật gộp đã rõ.
- Một giá trị bất biến được kết hợp sau `join()`.

**Chọn `RecursiveAction` khi mỗi phần thực hiện side effect trên vùng dữ liệu có ownership độc lập:**

- Sort một đoạn mảng không giao nhau.
- Biến đổi nhiều vùng độc lập của buffer.
- Cập nhật từng tile của một ma trận khi các tile không chồng lấn.
- Duyệt và xuất kết quả vào vùng output đã phân hoạch.

**Cảnh báo:** `RecursiveAction` không có return value **không đồng nghĩa side effect tự thread-safe**. Nếu các task cùng ghi một `ArrayList` hoặc một biến `long total` không đồng bộ, đó vẫn là data race. Với `RecursiveTask`, việc trả kết quả từ task thường giúp hạn chế nhu cầu shared mutable state.

## 11. Phân chia theo range thay vì sao chép dữ liệu

Một thiết kế tốt thường truyền **tham chiếu dữ liệu + chỉ số**:

```java
new SumTask(values, from, mid);
new SumTask(values, mid, to);
```

Đây là đoạn minh họa trong `ForkJoinArraySumDemo`.

Một lựa chọn dễ mắc lỗi hiệu năng:

```java
long[] left = Arrays.copyOfRange(values, from, mid);
long[] right = Arrays.copyOfRange(values, mid, to);
```

Nếu mỗi tầng đệ quy lại copy dữ liệu, tổng allocation, bộ nhớ tạm và chi phí copy có thể rất lớn, che hết lợi ích song song. Dùng range giúp tránh cấp phát mảng con; vẫn có overhead tạo task nhưng thấp hơn so với copy toàn bộ dữ liệu ở nhiều tầng.

**Không phải mọi copy đều sai.** Với dữ liệu đầu vào đang bị writer khác sửa, một snapshot/copy có thể cần thiết để đảm bảo consistency. Nhưng nên copy **có chủ đích ở ranh giới ownership**, thay vì copy vô tội vạ ở mỗi lần chia.

## 12. Threshold: biến số quan trọng nhất của bài toán

Một threshold tốt phải cân bằng:

- **Quá nhỏ:** nhiều task, chi phí fork/join, scheduling, object allocation và GC cao.
- **Quá lớn:** ít task, không đủ việc để chia đều số core, mất cơ hội work stealing.
- **Phù hợp:** phần leaf đủ nặng để việc chạy song song bù chi phí lập lịch; số task hữu ích đủ nhiều để phân phối.

Một cách khởi đầu thực dụng:

1. Đo phiên bản **tuần tự** đúng, giữ làm baseline.
2. Chọn kích thước đầu vào đủ lớn.
3. Thử nhiều threshold có ý nghĩa, ví dụ các chunk từ vài nghìn đến vài trăm nghìn phần tử tùy phép tính.
4. Đo throughput, latency và allocation bằng benchmark đáng tin.
5. Quan sát số core thực có, memory bandwidth, GC và độ cân đối của các nhánh.
6. Chọn threshold theo workload, **không chốt một con số dùng cho mọi thuật toán**.

Trong ví dụ tổng mảng, leaf chỉ thực hiện vài phép cộng nên threshold production cần **lớn hơn 2 rất nhiều** trên đa số workload. Trong tính toán hình ảnh/phép toán nặng trên mỗi pixel, threshold có thể khác.

### Threshold theo kích thước hay theo độ sâu?

- **Mảng:** `to - from <= THRESHOLD` là tiêu chí trực tiếp, ổn định.
- **Cây cân đối:** giới hạn parallel depth có thể giúp khống chế số lượng task.
- **Cây không cân:** depth có thể dự đoán rất kém khối lượng; ưu tiên ước lượng subtree size/work nếu có.
- **Đệ quy trùng subproblem:** threshold không sửa bản chất thuật toán lặp việc; cần thay đổi thuật toán/memoization.

## 13. Amdahl's Law và “tăng số thread” có giới hạn

Nếu một thuật toán có phần tuần tự `s` và phần song song `1-s`, tốc độ lý tưởng bị giới hạn bởi phần tuần tự. Công thức tham khảo:

\[
S(p)\le \frac{1}{s+\frac{1-s}{p}}
\]

với `p` là số worker hiệu dụng.

Giả sử khoảng `20%` công việc không thể song song, dù số worker tăng rất lớn, speedup lý tưởng cũng không thể vượt xấp xỉ `5×`, chưa tính overhead.

**Trong thực tế** chi phí fork/join, cache misses, memory bandwidth, GC và data locality còn làm speedup thấp hơn. Tăng `ForkJoinPool(64)` trên máy có ít core hoặc workload memory-bound có thể chậm hơn `ForkJoinPool(4)`.

**Đo hiệu năng:** với JVM, benchmark cần warm-up JIT, chống dead-code elimination, cùng kích thước đầu vào, đo nhiều lần và kiểm tra kết quả đúng. Công cụ chuyên dụng như JMH thường đáng tin hơn một lần `System.nanoTime()` trước/sau trong `main`. Không dùng các output ví dụ nhỏ `8` phần tử để khẳng định Fork/Join nhanh hơn tuần tự.

## 14. ForkJoinPool.commonPool() và pool riêng

Java có `ForkJoinPool.commonPool()`, một pool chung được dùng bởi nhiều API, bao gồm một số parallel stream và thao tác asynchronous theo cấu hình mặc định.

Ví dụ:

```java
long answer = ForkJoinPool.commonPool()
        .invoke(new SumTask(values, 0, values.length));
```

Đây là **đoạn minh họa** dùng `SumTask` trong ví dụ trước. Nếu dùng common pool, **không nên gọi `shutdown()` như thể ứng dụng sở hữu pool đó**. Pool được JVM/thư viện dùng chung, và việc quản lý vòng đời có contract khác với `new ForkJoinPool(...)` của ứng dụng.

Khi tạo pool riêng:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    Result result = pool.invoke(task);
    use(result);
} finally {
    pool.shutdown();
}
```

Đây là đoạn minh họa; `Result`, `task` và `use` do ứng dụng định nghĩa. Pool riêng giúp kiểm soát mức song song và phạm vi tài nguyên; **ai tạo pool thì cần quản lý shutdown**. Nếu ứng dụng nộp nhiều task bất đồng bộ, chỉ `shutdown()` không phải bằng chứng chúng đã kết thúc; có thể cần `awaitTermination()` hoặc thu các task result trước khi trả tài nguyên.

### Parallelism không phải số thread tuyệt đối chạy mọi lúc

`ForkJoinPool(4)` thể hiện mức song song mục tiêu. Nó không bảo đảm bốn task luôn chạy đồng thời hoặc mọi đoạn `compute()` được phân đều. Số task hữu ích, các dependency từ `join()`, scheduler, CPU và khả năng chặn đều ảnh hưởng số worker hoạt động thực tế.

## 15. Fork/Join và Parallel Streams

Một số phép reduction có thể được viết ngắn với streams:

```java
long sum = LongStream.of(values).parallel().sum();
```

Đây là đoạn minh họa; cần `import java.util.stream.LongStream;` và `values` là `long[]`. Với dữ liệu đơn giản, thư viện có thể tối ưu tốt hơn một implementation tự viết.

**Không phải vì dùng `parallel()` thì lúc nào cũng nên:**

- Các phép toán quá nhỏ có thể bị overhead chi phối.
- Operation có side effect lên shared mutable state dễ race.
- Stateful operations, ordering requirements và nguồn dữ liệu có chi phí chia không đều có thể làm chậm.
- Parallel stream sử dụng cơ chế Fork/Join bên dưới trong nhiều trường hợp, có thể chia sẻ tài nguyên với tác vụ khác của ứng dụng.

Ví dụ sai về shared mutable accumulation:

```java
List<Integer> result = new ArrayList<>();
values.parallelStream().forEach(result::add); // Không thread-safe.
```

Đây là **đoạn phản ví dụ** với `values` là một stream source phù hợp. `ArrayList` không an toàn cho nhiều writer đồng thời. Ưu tiên collector thread-safe/đúng contract, reduction không side effect, hoặc dùng cấu trúc dữ liệu/concurrency protocol phù hợp.

## 16. Không dùng Fork/Join cho I/O chặn dài một cách máy móc

Fork/Join được thiết kế mạnh cho việc **CPU-bound và task có thể chia**. Worker bị chặn lâu bởi:

- Gọi mạng không có timeout.
- `Thread.sleep()` để chờ service khác.
- Đợi lock từ một hệ thống không liên quan.
- `Future.get()` của một task không thuộc cùng cấu trúc Fork/Join.
- Truy vấn database hoặc đọc file chặn lâu.

có thể làm pool có ít worker khả dụng để thực hiện các task chưa xong.

`ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)` tồn tại để thông báo một số kiểu chặn có quản lý, cho phép pool xem xét bù worker khi phù hợp. **Đây không phải phép màu biến I/O thành non-blocking**, và không thay thế timeout, cancel hay thiết kế workload đúng.

Khi workload chủ yếu là I/O, cân nhắc executor phù hợp với blocking tasks hoặc cơ chế asynchronous I/O. Với Java 21+ còn có virtual threads, nhưng chúng giải quyết một bài toán lập lịch khác; không đồng nhất chúng với Fork/Join CPU divide-and-conquer.

**Tách bạch:** một thuật toán xử lý file song song có thể dùng Fork/Join cho phần tính CPU sau khi đọc dữ liệu, nhưng không cần cho mọi thread cùng chờ I/O trên cùng pool.

## 17. Exception trong ForkJoinTask: truy nguyên lỗi

Một `RecursiveTask.compute()` có thể ném `RuntimeException` hoặc `Error` nếu gặp lỗi. Khi gọi `join()` hoặc `invoke()`, lỗi của subtask có thể được **truyền lại** theo hợp đồng `ForkJoinTask`; các loại unchecked exception thường không được bọc giống cách `Future.get()` ném `ExecutionException`.

Nếu sử dụng `ForkJoinTask.get()` (giao diện Future), có thể nhận `ExecutionException` khi task hoàn thành bất thường, cùng `InterruptedException` khi caller chờ bị ngắt. Vì vậy cần phân biệt **API chờ kết quả** đang dùng:

| API | Kết quả/lỗi |
| --- | --- |
| `task.join()` | Trả kết quả hoặc ném unchecked exception khi task thất bại |
| `pool.invoke(task)` | Trả kết quả hoặc ném unchecked exception khi task thất bại |
| `task.get()` | Contract Future, có `ExecutionException` và `InterruptedException` |
| `task.get(timeout, unit)` | Có thể thêm `TimeoutException` |

Nếu một nhánh thất bại, đừng mặc định nhánh khác được rollback hoặc tất cả task đang chạy sẽ lập tức dừng. Với `RecursiveAction` sửa nhiều đoạn, một số đoạn có thể đã được cập nhật trước khi lỗi được quan sát. Cần quyết định tính nhất quán, retry, rollback hoặc loại bỏ kết quả theo nghiệp vụ.

### Ví dụ về validation

Ở một phép reduce có giới hạn domain, hãy kiểm tra input trước khi tạo các task, hoặc làm rõ exception nào là lỗi có thể phục hồi. Ví dụ `Math.addExact` có thể ném `ArithmeticException` nếu overflow. Trong Fork/Join, exception đó có thể đi qua `join()` đến caller; không tự suy ra rằng các nhánh khác chưa thực hiện side effect nào.

## 18. Cancellation và interruption

`ForkJoinTask.cancel(boolean mayInterruptIfRunning)` có cơ chế khác với việc giả định một worker `Thread` thông thường sẽ bị interrupt đúng như `FutureTask` trong một `ThreadPoolExecutor`. Theo contract của `ForkJoinTask`, **cancel thường không dùng interrupt để điều khiển việc thực thi task**; argument `mayInterruptIfRunning` không phải cam kết worker sẽ dừng.

Do đó:

- Đừng mong `cancel(true)` chắc chắn ngắt một phép tính dài bên trong `compute()`.
- Một task CPU-bound cần hỗ trợ hủy có thể kiểm tra token/cờ `AtomicBoolean` hoặc một trạng thái hợp tác do ứng dụng quản lý.
- Kiểm tra hủy ở **điểm an toàn** và dừng trước khi tạo thêm subtask nếu cần.
- Các nhánh đã bắt đầu có thể tiếp tục; cần thiết kế chính sách dọn dẹp và kết quả khi hủy.
- Nếu task có side effect hoặc giữ tài nguyên, phải dùng `finally` đúng chỗ.

Mẫu minh họa:

```java
if (cancelled.get()) {
    return 0L;
}
```

Ở đây `cancelled` là `AtomicBoolean` do ứng dụng cung cấp. **Trả `0L` khi hủy** chỉ hợp lệ nếu contract phép reduce phân biệt được “bị hủy” và kết quả hợp lệ; thường tốt hơn là một tín hiệu hủy riêng hoặc exception được thiết kế rõ, tránh trả `0` mà caller tưởng là tổng thực.

### Không fork các task vô hạn

Một lỗi nguy hiểm là `compute()` luôn chia mà không có điều kiện base case, hoặc chia một range thành một range giống hệt nó (ví dụ tính `mid = from` rồi tiếp tục với `[from,to)` không đổi). Điều đó có thể tạo ra vô hạn task, tăng allocation và làm pool kiệt tài nguyên. **Mọi nhánh recursive phải tiến gần base case.**

## 19. Quan hệ bộ nhớ khi fork và join

Để tính đúng, chúng ta cần biết dữ liệu được **công bố** cho worker và kết quả của worker được **quan sát** đúng cách.

Khi một subtask được fork và sau đó join, hợp đồng đồng bộ của Fork/Join cung cấp cơ sở cho việc các thao tác trước khi giao task và sau khi nhận kết quả nhìn thấy các thay đổi liên quan một cách hợp lệ. Cách thực hành an toàn nhất vẫn là:

1. Khởi tạo đầy đủ các tham chiếu input trước khi nộp task.
2. Mỗi task chỉ đọc input bất biến hoặc chỉ sửa **vùng dữ liệu được phân quyền độc lập**.
3. Không đọc vùng output của subtask trước khi `join()`/`invokeAll()` hoàn thành.
4. Gộp kết quả ở thread parent sau khi đã đợi các nhánh.
5. Nếu có writer ngoài cây Fork/Join sửa dữ liệu đồng thời, xây một giao thức đồng bộ/ownership riêng.

**Không nhầm:** `join()` không giúp một code tùy tiện ghi chung `static long total` bằng phép `+=` trở thành an toàn. Nó chỉ cung cấp điểm đợi và quan hệ đồng bộ cho tác vụ, trong khi những lần cập nhật tranh chấp vẫn có thể bị lost update nếu không atomic/khóa.

## 20. Những lỗi thiết kế thường gặp

### 20.1. Fork rồi join ngay

```java
left.fork();
long a = left.join();
long b = right.compute();
```

Đây là **đoạn phản ví dụ về cơ hội song song**. Worker hiện tại có thể ngồi đợi left trước khi bắt đầu right. Mẫu thường thích hợp hơn là `left.fork(); b = right.compute(); a = left.join();`.

### 20.2. Tạo task cho từng phần tử/leaf

Nếu tính một phép cộng vài nano giây nhưng tạo hàng triệu object `RecursiveTask`, overhead có thể chiếm ưu thế. Phải có threshold.

### 20.3. Không có base case, hoặc chia không giảm kích thước

Một bài toán recursive phải tiến dần tới leaf/termination. Nếu không, có thể gây `StackOverflowError`, bùng task hoặc không bao giờ hoàn tất.

### 20.4. Ghi vào cùng biến tổng mutable

```java
static long total;
...
total += value;
```

Đây là **phản ví dụ** khi nhiều task cùng chạy. Phép cộng không atomic; cách rõ nhất là trả `Long` từ mỗi `RecursiveTask` rồi parent cộng sau `join()`.

### 20.5. Sửa đồng thời cùng phần tử mảng

Trong merge sort, hai subtask phải sở hữu những khoảng không giao nhau. Nếu cả hai cùng ghi `temp[k]` hoặc parent merge trước khi join, có data race/logic error.

### 20.6. Duyệt graph có chu trình như tree

Một phương thức `sum(node.left)+sum(node.right)` có thể đếm cùng node nhiều lần hoặc recurse vô hạn khi dữ liệu là DAG/graph. Cần định nghĩa semantics và visited protocol.

### 20.7. Cho rằng Fork/Join luôn nhanh hơn sequential

Với input nhỏ, chi phí task lớn hơn phép tính. Benchmark đúng workload và threshold; không dựa trên số worker hoặc trực giác.

### 20.8. Dùng Fibonacci ngây thơ rồi xem fork là tối ưu

Fibonacci đệ quy có subproblem lặp, vốn đã không hiệu quả. Ưu tiên memoization/DP/fast doubling theo bài toán.

### 20.9. Bỏ qua overflow/associativity

`long` có giới hạn; `double` reduction có rounding và kết quả phụ thuộc grouping. Chọn kiểu số và luật kết hợp theo yêu cầu kết quả.

### 20.10. Dùng common pool rồi shutdown như tài nguyên riêng

`ForkJoinPool.commonPool()` là tài nguyên dùng chung của runtime; không tự ý đóng nó. Với `new ForkJoinPool`, quản lý lifecycle pool bạn sở hữu.

### 20.11. Block worker ở I/O dài

Fork/Join phù hợp CPU divide-and-conquer; I/O dài làm worker thiếu khả năng xử lý task. Xem xét pool/kiểu tác vụ khác hoặc managed blocking phù hợp.

### 20.12. Tưởng Future cancel(true) luôn interrupt ForkJoinTask

Hợp đồng hủy của `ForkJoinTask` khác nhiều Future implementations. Thiết kế cooperative cancellation thay vì dựa vào cờ mayInterruptIfRunning để dừng chắc chắn.

### 20.13. Bỏ qua exception của child task

Một child ném lỗi có thể được truyền tại `join()`. Đừng nuốt exception rồi cộng một kết quả giả khiến output sai; báo lỗi/rollback theo hợp đồng nghiệp vụ.

### 20.14. Bắt đầu đọc kết quả trước khi join

Một result buffer đang được các subtask ghi chưa phải snapshot hoàn chỉnh. Phải có điểm đợi trước khi parent merge hoặc reader dùng output.

## 21. Quy trình áp dụng Fork/Join trong dự án

Trước khi viết code, trả lời:

1. **Tính độc lập:** các subproblem có thể chạy không phụ thuộc nhau không?
2. **Phép gộp:** kết quả có identity và phép combine đúng không?
3. **Cấu trúc:** mảng range, cây subtree, hay graph có node chia sẻ?
4. **Base case:** tại kích thước nào nên xử lý tuần tự?
5. **Ownership:** các task có đọc/ghi trùng mutable state không?
6. **Độ sâu:** recursion có thể gây tràn stack không?
7. **Số học:** cần long, BigInteger, BigDecimal hay Kahan/pairwise sum?
8. **Pool:** dùng common pool hay pool riêng? Ai shutdown?
9. **Liveness:** task có blocking I/O, join vòng hoặc deadlock không?
10. **Hủy và lỗi:** cancellation, exception, partial side effect xử lý thế nào?
11. **Hiệu năng:** so với tuần tự và thư viện có sẵn có lợi ích đo được không?

Nếu hai subproblem **không độc lập**, phép combine yêu cầu thứ tự đặc biệt hoặc dữ liệu có mutable graph phức tạp, chưa chắc Fork/Join là mô hình tốt. Có thể dùng thuật toán tuần tự, `ExecutorService` chuyên dụng, pipeline khác hoặc cấu trúc concurrency phù hợp hơn.

## 22. Kiểm thử correctness trước khi benchmark

Trước khi đo performance, luôn có **oracle tuần tự** để kiểm tra:

### Với sum array

- Mảng rỗng.
- Một phần tử, hai phần tử.
- Độ dài lẻ để kiểm tra `mid`.
- Giá trị âm/0.
- Dữ liệu lớn ngẫu nhiên với seed cố định.
- Biên overflow nếu nghiệp vụ cần xử lý.
- So sánh `pool.invoke(task)` với `sequentialSum`.

### Với tree sum

- `root == null` cho kết quả `0`.
- Một node.
- Cây cân đối, cây chỉ có con trái/phải.
- Cây sâu để phát hiện rủi ro stack.
- DAG/cycle nếu input không được bảo đảm là cây thuần.
- Kết quả bằng hàm duyệt tuần tự đã được xác thực.

### Với merge sort

- Mảng rỗng và một phần tử.
- Độ dài lẻ/chẵn.
- Đã sắp xếp, đảo ngược, nhiều số trùng.
- Số âm.
- So sánh với `Arrays.sort` trên một bản copy.
- Xác nhận không có task ghi ra ngoài `[from,to)`.

### Không kiểm thử bằng sleep

Đừng giả định một task sẽ hoàn tất trong `sleep(10)` chỉ vì máy chạy nhanh. `pool.invoke(...)` là điểm đợi kết quả trực tiếp. Nếu cần giới hạn thời gian test, dùng timeout của framework test hoặc một cơ chế Future có deadline rõ, không thay correctness assertion bằng ngẫu nhiên lịch chạy.

**Tính đúng không phụ thuộc số worker:** thử parallelism 1, 2, 4 hoặc nhiều mức phù hợp. Một thuật toán đúng không được tự biến kết quả thành sai khi chỉ có một worker, dù tốc độ thay đổi.

## 23. Bài tập tự thực hành

### Bài tập 1: max trong mảng

Biến `SumTask` thành `MaxTask`: leaf tìm max trong `[from,to)`, parent gộp bằng `Math.max(left,right)`. Trường hợp mảng rỗng phải **định nghĩa rõ hợp đồng** (throw `IllegalArgumentException` hoặc trả `OptionalLong`), không dùng tùy tiện `0` vì mảng có thể chứa toàn số âm.

### Bài tập 2: thống kê min/max/count

Cho mỗi task trả về một record `Stats(long min, long max, long count)`; parent kết hợp hai stats. Định nghĩa identity hoặc tách trường hợp empty để tránh sai min/max. Không dùng ba biến static mutable cập nhật đồng thời.

### Bài tập 3: đếm node của cây

Biến TreeSumTask thành NodeCountTask với `count(null) = 0`, `count(node) = 1 + count(left) + count(right)`. Thử cây cân đối và cây lệch, so với hàm tuần tự.

### Bài tập 4: tổng bình phương

Thay leaf của SumTask thành cộng `values[i]*values[i]` và kiểm tra overflow. So sánh với oracle tuần tự. Với `double`, dùng tolerance phù hợp thay vì đòi bitwise identical nếu thứ tự cộng khác nhau.

### Bài tập 5: thử threshold

Chạy trên mảng đủ lớn, thay threshold và đo bằng JMH hoặc benchmark đúng. Dùng kết quả đúng làm điều kiện bắt buộc trước khi ghi nhận latency/speedup. Thử nhiều kích cỡ input và mức parallelism, không kết luận từ một lần chạy.

### Bài tập 6: cây lệch

Tạo cây chỉ có con phải. Quan sát vì sao “fork hai nhánh” ít hữu ích; cân nhắc chuyển đổi thành danh sách/node range hoặc chia frontier nếu bài toán cho phép.

### Bài tập 7: kết quả có lỗi

Cho một leaf throw `IllegalArgumentException` khi gặp dữ liệu sai; theo dõi exception được báo tại `join()` hoặc `pool.invoke()`. Xác định policy liệu các subtask khác có side effect không và có thể retry an toàn không.

## 24. Tự kiểm tra kiến thức

**1. Vì sao `RecursiveTask<Long>` phù hợp tính tổng mảng?**

Vì mỗi subtask có thể trả một `Long` độc lập; parent kết hợp sau `join()` mà không cần các worker cùng ghi biến tổng.

**2. Điều kiện cần để chia mảng thành hai task không bị đếm thiếu/trùng?**

Dùng hai khoảng nửa mở `[from,mid)` và `[mid,to)` không chồng lấn; cả hai cùng phủ `[from,to)`.

**3. `left.fork(); left.join(); right.compute();` có vấn đề gì về hiệu năng?**

Nó có thể khiến worker đợi left trước khi xử lý right, giảm cơ hội chạy hai nhánh đồng thời. Thường fork một nhánh, compute nhánh kia, rồi join.

**4. Work stealing có đảm bảo một subtask do worker khác chạy không?**

Không. Nó cho phép worker nhàn rỗi lấy việc; runtime quyết định lịch chạy. Correctness không được phụ thuộc worker nào thực thi.

**5. Vì sao phải có threshold?**

Tránh tạo quá nhiều task nhỏ so với chi phí tính leaf, làm overhead fork/join và allocation lớn hơn lợi ích song song.

**6. Cây chỉ có một nhánh rất sâu có tự chạy nhanh nhờ Fork/Join không?**

Không. Nếu không có đủ nhánh độc lập, rất ít công việc để phân phối; recursion còn có nguy cơ tràn stack.

**7. Hai task merge sort cùng dùng chung mảng có an toàn không?**

Có nếu chúng chỉ ghi các đoạn **không giao nhau**, parent đợi con xong trước khi merge, và không có writer bên ngoài phá ownership.

**8. Vì sao không fork task riêng cho từng node lá?**

Chi phí tạo/sắp lịch task có thể lớn hơn phép tính leaf. Nên xử lý các subtree nhỏ tuần tự.

**9. Fibonacci ngây thơ được fork có tự thành thuật toán tối ưu không?**

Không. Các subproblem bị tính lặp theo cấu trúc đệ quy; DP/memoization hoặc fast doubling thường hiệu quả hơn.

**10. `ForkJoinPool.commonPool()` có nên shutdown ở cuối mỗi method không?**

Không. Đó là pool dùng chung, không phải tài nguyên riêng của method. Pool do ứng dụng tự tạo mới cần owner quản lý lifecycle.

**11. Nếu một `ForkJoinTask` bị `cancel(true)`, có đảm bảo worker đang compute bị interrupt dừng ngay không?**

Không. Hợp đồng hủy của ForkJoinTask không bảo đảm dùng interrupt để điều khiển thực thi; phải thiết kế hủy hợp tác khi cần.

**12. Vì sao kết quả song song của phép cộng `double` có thể khác vòng lặp tuần tự?**

Do thứ tự nhóm phép cộng khác và rounding; floating-point addition không kết hợp hoàn toàn.

**13. `RecursiveAction` có tự ngăn race khi nhiều task ghi chung ArrayList không?**

Không. Không có return value không có nghĩa side effect an toàn; phải phân vùng ghi hoặc đồng bộ.

**14. Một graph có node được dùng chung ở hai nhánh có thể tính sai theo thuật toán tree sum vì sao?**

Vì cùng node có thể được tính nhiều lần; khi có cycle còn có thể đệ quy vô hạn. Cần định nghĩa graph semantics và visited/dedup đúng.

## 25. Tóm tắt

**Fork/Join** là cách tổ chức các phép tính **divide-and-conquer** trên dữ liệu/nhánh độc lập. `RecursiveTask<V>` phù hợp **trả kết quả để reduction**, còn `RecursiveAction` phù hợp **tác động lên những vùng dữ liệu có quyền ghi tách biệt**. `ForkJoinPool` sử dụng cơ chế work stealing để phân phối các task có sẵn, nhưng không tự tạo song song nếu thuật toán không chia được việc.

Với **mảng**, chia bằng các range nửa mở và gộp kết quả sau `join()`. Với **cây**, chia theo subtree và chú ý cây lệch, độ sâu recursion, graph/cycle và ownership. Với **đệ quy tính toán**, kiểm tra có subproblem trùng lặp hay không trước khi fork; Fibonacci ngây thơ là bài học về giới hạn, không phải thuật toán tốt cho production. Với **merge sort**, các task được sửa các đoạn độc lập và parent chỉ merge sau khi đã đợi con.

Để code đúng và hiệu quả: **có base case + threshold**, tránh shared mutable accumulator, giới hạn độ sâu/task, quản lý pool ownership, xử lý lỗi/hủy đúng contract, và **so sánh với oracle tuần tự trước khi benchmark**. Fork/Join hữu ích nhất khi chi phí mỗi nhánh đủ lớn, dữ liệu có thể chia an toàn và overhead song song được bù bằng công việc thực.
