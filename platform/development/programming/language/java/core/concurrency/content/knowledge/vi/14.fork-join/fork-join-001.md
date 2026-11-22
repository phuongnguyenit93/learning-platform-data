# Fork/Join và divide-and-conquer trong Java Concurrency

Khi cần xử lý một khối dữ liệu lớn, đôi khi ta có thể **chia bài toán lớn thành các bài toán con độc lập**, cho nhiều worker xử lý đồng thời rồi **gộp kết quả**. Đây là tư duy *divide-and-conquer* (chia để trị). Java cung cấp **Fork/Join Framework** trong `java.util.concurrent` để hiện thực hóa kiểu tác vụ này, đặc biệt khi khối lượng tính toán chủ yếu sử dụng CPU.

**Fork/Join** là mô hình:
1. **Divide:** nếu bài toán đủ lớn, chia nó thành các nhánh nhỏ.
2. **Fork:** cho một hay nhiều nhánh cơ hội được thực thi bởi worker khác.
3. **Join:** chờ nhánh cần thiết hoàn tất và kết hợp kết quả.
4. **Conquer/base case:** nếu khối lượng đủ nhỏ, tính trực tiếp mà không chia nữa.

Trong JDK, ba thành phần thường gặp là `ForkJoinPool` (pool có cơ chế work-stealing), `RecursiveTask<V>` (tác vụ trả kết quả) và `RecursiveAction` (tác vụ không trả kết quả). Tất cả đều thuộc **Java concurrency nói chung**; bài không dựa trên framework bên ngoài.

## 1. Bài toán nào phù hợp divide-and-conquer?

Lấy ví dụ tính tổng mảng 8 phần tử:

```text
sum([1,2,3,4,5,6,7,8])
                |
       +--------+--------+
       |                 |
sum([1,2,3,4])     sum([5,6,7,8])
       |                 |
   +---+---+         +---+---+
   |       |         |       |
sum(1,2) sum(3,4) sum(5,6) sum(7,8)
   |       |         |       |
   3       7        11      15
   +---+---+         +---+---+
      10                26
       +--------+--------+
                36
```

Các nhánh tổng con có thể thực thi độc lập. Kết quả cuối là tổng của các kết quả con. Nếu tổng số phần tử rất lớn và mỗi nhánh có đủ công việc, một số nhánh có thể chạy song song trên nhiều lõi CPU.

Để chia để trị hiệu quả, nên có các đặc tính:

- **Phân tách được:** mỗi nhánh đọc/xử lý một vùng dữ liệu hoặc một phần bài toán riêng.
- **Ít phụ thuộc chéo:** không cần khóa một biến chung cho từng phần tử.
- **Ghép kết quả rõ ràng:** tổng, min/max, thống kê, cây kết quả hoặc dữ liệu đầu ra ở vùng tách biệt.
- **Base case hữu hạn:** phép chia cuối cùng dừng ở một ngưỡng cụ thể, không tạo tác vụ mãi mãi.
- **Công việc đủ lớn:** thời gian xử lý mỗi nhánh phải đáng kể so với chi phí tạo, lên lịch và join task.

Ví dụ điển hình: tính toán đệ quy trên mảng, xử lý cây, thuật toán phân đoạn, biến đổi từng vùng dữ liệu, một số thuật toán tìm kiếm/tổng hợp có thể tách độc lập.

Fork/Join **không mặc định phù hợp** cho mỗi request HTTP nhỏ, ghi file, gọi database hoặc một vòng xử lý vốn phụ thuộc nghiêm ngặt vào kết quả bước trước.

## 2. ForkJoinPool khác gì tạo Thread cho mỗi nhánh?

Cách ngây thơ là tạo một `new Thread(...)` tại mỗi nút đệ quy. Khi độ sâu tăng, số thread tạo ra có thể bùng nổ, tốn bộ nhớ stack, chi phí khởi động và context switch.

`ForkJoinPool` thay cách đó bằng một nhóm **worker thread tái sử dụng** và nhiều `ForkJoinTask` nhẹ hơn thread. Worker xử lý một task; task có thể fork ra những task con mà không tạo thread hệ điều hành mới cho từng nhánh.

Khái niệm **work-stealing**:

- Mỗi worker có hàng đợi tác vụ cục bộ hỗ trợ xử lý các nhánh của nó.
- Nếu một worker hết việc, nó có thể **lấy (steal)** tác vụ đang chờ ở hàng đợi của worker khác.
- Cơ chế này cố giữ các worker bận khi số nhánh không chia đều hoặc mỗi nhánh mất thời gian khác nhau.
- Thứ tự chạy và thread thực thi nhánh **không được bảo đảm cố định**; task vừa fork cũng có thể được chính worker hiện tại thực hiện sau đó.

```text
ForkJoinPool (parallelism ~ số worker mục tiêu)
       |
       +-- Worker 1: task A -> fork A1, A2
       |                 |
       |                 +-- xử lý A2
       |
       +-- Worker 2: hết việc -> steal A1
       |                                |
       +-- Worker 3: xử lý nhánh khác ---+
       |
       +-- Worker 4: có thể rảnh nếu ít việc
```

**Work-stealing là chiến lược phân phối công việc**, không phải cam kết mỗi nhánh có một worker riêng, mọi worker luôn bận, hay kết quả sẽ nhanh hơn chạy tuần tự. `parallelism` là mức song song mục tiêu của pool, không phải bảo đảm mọi task chạy đồng thời ở đúng số luồng đó.

## 3. Các thành phần và phương thức cơ bản

| API | Ý nghĩa | Khi dùng |
|---|---|---|
| `ForkJoinPool` | Executor chuyên dụng cho các `ForkJoinTask`; hỗ trợ work-stealing. | Chạy cây tác vụ chia để trị, quản lý parallelism/lifecycle. |
| `RecursiveTask<V>` | Lớp abstract cho task có kết quả `V`; ghi đè `compute()`. | Tính tổng, đếm, min/max, thống kê hoặc trả object kết quả. |
| `RecursiveAction` | Lớp abstract cho task không trả kết quả; `compute()` trả `void`. | Biến đổi từng vùng mảng độc lập, sắp xếp tại chỗ có phân vùng an toàn. |
| `task.fork()` | Đưa một `ForkJoinTask` vào cơ chế lập lịch để thực hiện bất đồng bộ với task hiện tại. | Khi muốn nhánh con có cơ hội chạy song song. |
| `task.join()` | Chờ task con hoàn tất và lấy kết quả; lỗi runtime có thể được truyền lại. | Gộp kết quả khi một nhánh đã được fork. |
| `task.invoke()` | Thực thi task và chờ kết quả. | Khi muốn xử lý đồng bộ một ForkJoinTask. |
| `ForkJoinTask.invokeAll(a,b)` | Thực hiện nhóm tác vụ theo cơ chế Fork/Join và đợi chúng hoàn tất. | Khi hai nhánh là các `RecursiveAction` hoặc không cần viết fork/join thủ công. |
| `pool.invoke(root)` | Đưa tác vụ gốc vào pool và chờ kết quả. | Điểm khởi động cây tác vụ ở caller. |
| `pool.execute(task)` | Gửi task để thực thi, không chờ ngay tại caller. | Khi quản lý completion ở bước khác. |

`ForkJoinTask.join()` **khác với** `Thread.join()`: nó chờ một **task** trong ForkJoin Framework, không phải đợi một đối tượng `Thread` kết thúc. `ForkJoinTask.join()` không khai báo `InterruptedException` như `Thread.join()`; việc cần giới hạn thời gian chờ và xử lý interrupt đòi hỏi thiết kế API phù hợp (ví dụ `get(timeout, unit)` của `Future`).

`RecursiveTask.compute()` là code do mình viết; **chính method này quyết định base case, cách chia và cách gộp**. Framework không tự đoán ngưỡng hay phân chia mảng giúp ứng dụng.

## 4. Mẫu fork một nhánh, compute một nhánh, join nhánh đã fork

Mẫu đơn giản cho `RecursiveTask<Result>`:

```java
@Override
protected Result compute() {
    if (smallEnough()) {
        return calculateDirectly();
    }

    Task left = new Task(leftRange);
    Task right = new Task(rightRange);

    left.fork();                    // Cho left cơ hội chạy song song.
    Result rightResult = right.compute(); // Worker hiện tại tự tính right.
    Result leftResult = left.join();       // Chờ left khi thật sự cần.

    return combine(leftResult, rightResult);
}
```

Đây là **pseudocode theo cú pháp Java**, không phải class độc lập: `Task`, `Result`, `Range`, các method minh họa chưa được định nghĩa. Chương trình hoàn chỉnh ở phần sau.

**Vì sao không `left.fork(); left.join(); right.compute();`?** Nếu join ngay sau khi fork, worker có thể phải chờ left hoàn tất trước khi bắt đầu right, làm mất một phần cơ hội chồng lấp công việc. Mẫu fork left → compute right → join left giúp thread hiện tại có công việc hữu ích trong khi left có thể được worker khác xử lý.

Có thể fork cả hai nhánh rồi join, nhưng khi một worker đang chạy cây đệ quy, tự tính một nhánh thường giảm overhead lập lịch và được khuyên dùng như một mẫu hợp lý. Không phải mọi trường hợp đều phải theo đúng một thứ tự; tính đúng đắn vẫn phụ thuộc dữ liệu, không phụ thuộc thứ tự.

## 5. Ví dụ 1 — Tính tổng mảng với RecursiveTask<Long>

Ta chia `long[]` thành hai đoạn `[from, to)` cho đến khi số phần tử trong đoạn không vượt `THRESHOLD`. Các nhánh chỉ **đọc dữ liệu**, và `join()` gộp tổng con; không cần `AtomicLong` hay synchronized cho biến tổng toàn cục.

Tạo file **`ForkJoinSumDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    private static final int THRESHOLD = 256;

    static final class SumTask extends RecursiveTask<Long> {
        private final long[] data;
        private final int from;
        private final int to;

        SumTask(long[] data, int from, int to) {
            this.data = data;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += data[i];
                }
                return sum;
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(data, from, middle);
            SumTask right = new SumTask(data, middle, to);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();

            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        long[] data = new long[10_000];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1;
        }

        long sequential = 0;
        for (long value : data) {
            sequential += value;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long parallel = pool.invoke(
                    new SumTask(data, 0, data.length)
            );

            System.out.println("Sequential: " + sequential);
            System.out.println("ForkJoin: " + parallel);
            System.out.println("Equal: " + (sequential == parallel));
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
```

Đầu ra:

```text
Sequential: 50005000
ForkJoin: 50005000
Equal: true
```

**Giải thích theo từng bước:**

1. `data` chứa các số từ 1 đến 10.000; tổng toán học bằng `10000 * 10001 / 2 = 50005000`.
2. Root task phụ trách `[0,10000)`. Mỗi lần đoạn lớn hơn 256 phần tử, nó chia thành hai nửa **không trùng nhau**.
3. `left.fork()` cho left cơ hội chạy song song; worker hiện tại gọi `right.compute()` để tận dụng thời gian.
4. `left.join()` chờ left nếu nó chưa hoàn tất rồi nhận tổng. Mỗi nút trả tổng hai nhánh, nên root nhận tổng toàn bộ.
5. Không có shared accumulator bị nhiều worker sửa. Các biến `sum`, `leftSum`, `rightSum` là local của từng lời compute, giúp tránh data race.
6. Main nhận kết quả từ `pool.invoke()` sau khi task gốc đã hoàn tất, rồi in. Chương trình không in thứ tự các worker để bảo đảm stdout không phụ thuộc lập lịch.

**Lưu ý:** `ForkJoinPool(4)` chỉ giới hạn mức parallelism được yêu cầu cho pool; không chứng minh máy chạy nhanh gấp bốn lần. Với mảng chỉ 10.000 phần tử và phép cộng rất rẻ, phiên bản tuần tự có thể nhanh hơn do chi phí chia task.

## 6. Chọn threshold: điểm dừng chia bài toán

`THRESHOLD` là số phần tử tối đa được xử lý trực tiếp trong một leaf task. Đây là một **tham số hiệu năng** chứ không phải hằng số Java đưa ra cho mọi thuật toán.

- Threshold **quá nhỏ**: tạo rất nhiều task, tăng allocation, quản lý deque, steal, join và đệ quy; overhead có thể lớn hơn công việc hữu ích.
- Threshold **quá lớn**: ít nhánh, ít khả năng cân bằng tải; worker khác có thể rảnh trong khi một nhánh lớn tính toán.
- Threshold **phù hợp**: mỗi leaf đủ công việc và có đủ nhánh để phân phối nhưng không tạo hàng triệu task bé.

Ví dụ xấp xỉ: với `N = 1_000_000` phần tử và threshold 1.000, số leaf vào cỡ `N / 1000` (phụ thuộc cách chia đôi), không phải đúng một task cho mỗi phần tử. Tốc độ thực tế còn phụ thuộc chi phí tính trên mỗi phần tử, memory bandwidth, JIT warm-up và số lõi CPU.

Thực hành tuning:

1. Tạo **phiên bản tuần tự** làm baseline và đối chiếu đúng kết quả.
2. Đảm bảo phép tính đủ lớn; thử nhiều threshold (ví dụ 256, 1.024, 4.096, 16.384).
3. Benchmark với dữ liệu, máy và JVM phù hợp; chạy nhiều vòng, có warm-up và đo biến thiên.
4. Theo dõi throughput, allocations, GC, số lần steal và mức sử dụng CPU nếu có ích.
5. Không lấy kết quả thời gian của một lần `System.nanoTime()` quanh một lời tính nhỏ làm kết luận tổng quát.

Tỷ lệ overhead cũng thay đổi theo loại phép tính: nếu leaf làm phép toán đơn giản trong mảng, threshold có thể cần lớn; nếu mỗi phần tử đòi hỏi tính nặng, threshold nhỏ hơn có thể hữu ích.

## 7. RecursiveAction: thay đổi các vùng dữ liệu độc lập

`RecursiveAction` không trả giá trị từ `compute()`. Nó phù hợp khi các nhánh có thể **ghi vào những vùng dữ liệu tách biệt** mà không cần gộp object kết quả. Điều kiện quan trọng là mọi nhánh chỉ sửa đoạn thuộc quyền nó, tránh hai worker ghi cùng ô.

Ví dụ bình phương từng phần tử của một mảng. Chương trình cố ý dùng mảng nhỏ để stdout dễ kiểm tra; đây là ví dụ **đúng về concurrency**, không phải benchmark.

Tạo file **`ForkJoinSquareDemo.java`**:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinSquareDemo {
    static final class SquareTask extends RecursiveAction {
        private static final int THRESHOLD = 2;

        private final int[] values;
        private final int from;
        private final int to;

        SquareTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= THRESHOLD) {
                for (int i = from; i < to; i++) {
                    values[i] = values[i] * values[i];
                }
                return;
            }

            int middle = from + (to - from) / 2;
            invokeAll(
                    new SquareTask(values, from, middle),
                    new SquareTask(values, middle, to)
            );
        }
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            pool.invoke(new SquareTask(values, 0, values.length));
            System.out.println("Squares: " + Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinSquareDemo.java
java ForkJoinSquareDemo
```

Đầu ra:

```text
Squares: [1, 4, 9, 16, 25, 36, 49, 64]
```

**Vì sao không cần synchronized khi ghi mảng?** Mỗi task xử lý một khoảng half-open `[from,to)`. Hai khoảng con `[from,middle)` và `[middle,to)` không trùng index; không có hai task nào trong cây ghi cùng phần tử. `invokeAll()` chờ các nhánh hoàn tất trước khi nút cha trả về; `pool.invoke()` chờ cả cây xong trước khi main đọc toàn bộ mảng.

Không suy rộng rằng “dùng Fork/Join thì mảng mutable luôn thread-safe”. Nếu các task ghi chung một index, thay đổi `ArrayList` chung hoặc tăng một biến đếm chung không đồng bộ, vẫn có race. Tính an toàn của ví dụ dựa vào **phân chia quyền ghi không giao nhau**.

## 8. RecursiveTask trả kết quả tổng hợp phức tạp

Không phải bài chia để trị nào cũng chỉ tính một số. Ta có thể tạo một immutable result object chứa **tổng, giá trị nhỏ nhất và lớn nhất**, rồi gộp từng nhánh. Đây là mô hình map/reduce ở cấp tác vụ: mỗi leaf tạo kết quả riêng, nút cha combine mà không sửa trạng thái toàn cục.

Tạo file **`ForkJoinStatsDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinStatsDemo {
    record Stats(long sum, int min, int max) {
        static Stats combine(Stats a, Stats b) {
            return new Stats(
                    a.sum() + b.sum(),
                    Math.min(a.min(), b.min()),
                    Math.max(a.max(), b.max())
            );
        }
    }

    static final class StatsTask extends RecursiveTask<Stats> {
        private static final int THRESHOLD = 2;

        private final int[] values;
        private final int from;
        private final int to;

        StatsTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Stats compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                int min = Integer.MAX_VALUE;
                int max = Integer.MIN_VALUE;

                for (int i = from; i < to; i++) {
                    int value = values[i];
                    sum += value;
                    min = Math.min(min, value);
                    max = Math.max(max, value);
                }
                return new Stats(sum, min, max);
            }

            int middle = from + (to - from) / 2;
            StatsTask left = new StatsTask(values, from, middle);
            StatsTask right = new StatsTask(values, middle, to);

            left.fork();
            Stats rightResult = right.compute();
            Stats leftResult = left.join();
            return Stats.combine(leftResult, rightResult);
        }
    }

    public static void main(String[] args) {
        int[] values = {8, 3, 12, 4, 9, 1, 7, 6};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            Stats stats = pool.invoke(
                    new StatsTask(values, 0, values.length)
            );

            System.out.println("Sum: " + stats.sum());
            System.out.println("Min: " + stats.min());
            System.out.println("Max: " + stats.max());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinStatsDemo.java
java ForkJoinStatsDemo
```

Đầu ra:

```text
Sum: 50
Min: 1
Max: 12
```

Mỗi nhánh `StatsTask` tạo một `Stats` mới, nút cha gọi `Stats.combine` để gộp. Kết quả không phụ thuộc thứ tự chạy task. Với mảng rỗng, cách khởi tạo `min/max` trong ví dụ **không biểu diễn một giá trị thống kê hợp lệ**; code này giả định đầu vào có ít nhất một phần tử và nên từ chối mảng rỗng hoặc trả kiểu kết quả mô tả empty khi đưa vào thư viện thực tế.

Nếu phép gộp không có tính **kết hợp** (*associative*), kết quả có thể thay đổi khi thay cây phân chia. Cộng số nguyên trong ví dụ có tính kết hợp theo ngữ nghĩa toán học (và Java `long` có thể overflow với dữ liệu quá lớn); cộng `double` có sai số làm tròn nên thứ tự gộp khác nhau có thể cho kết quả số thực hơi khác. Không mặc định mọi phép reduce an toàn để phân tách/gộp.

## 9. Không chia sẻ accumulator mutable giữa các nhánh

Một mẫu thiếu an toàn:

```java
// PHẢN VÍ DỤ: sharedTotal là một biến mutable chia sẻ.
sharedTotal += values[i];
```

Nếu nhiều task cùng chạy dòng này, thao tác đọc–cộng–ghi không nguyên tử, nên có thể mất cập nhật (*lost update*). Thêm `volatile` lên sharedTotal cũng không làm `+=` nguyên tử.

Các lựa chọn tốt hơn:

- Dùng `RecursiveTask<Long>` trả tổng cục bộ rồi **join và gộp** như `ForkJoinSumDemo`.
- Giao cho các `RecursiveAction` sửa **vùng dữ liệu riêng**, rồi đọc sau khi toàn bộ cây hoàn tất.
- Nếu thật sự cần cập nhật shared state, dùng công cụ đồng bộ thích hợp, song tranh chấp trên một counter chung có thể làm Fork/Join mất lợi thế.

Khi task con giữ cùng reference đến một object mutable, việc tạo nhiều `RecursiveTask` **không tự sao chép object**. Phải chủ động bảo đảm quyền truy cập không giao nhau, immutability hoặc đồng bộ. Việc trả kết quả dạng record immutable giúp làm rõ ownership và giảm mutable shared state.

## 10. Java Memory Model: tính hiển thị sau join/invoke

Java Fork/Join có các quy tắc đồng bộ hóa bộ nhớ cho việc **gửi tác vụ và lấy kết quả**. Các hành động trước khi submit một task cho executor có quan hệ *happens-before* với hành động của task; các hành động của asynchronous computation có quan hệ *happens-before* với hành động sau khi thread khác truy xuất kết quả qua `Future.get()` tương ứng. Những primitive hoàn thành của `ForkJoinTask` như `join()` cũng cung cấp cơ chế đồng bộ hóa để kết quả nhánh đã hoàn tất được sử dụng an toàn theo contract của task.

Trong `ForkJoinSumDemo`, dữ liệu mảng được khởi tạo **trước khi gửi root task**; các task chỉ đọc nó. Trong `ForkJoinSquareDemo`, task con ghi các vùng riêng rồi cây hoàn tất trước khi main in mảng, vì `pool.invoke(root)` chỉ trở về sau khi root hoàn tất việc phối hợp các nhánh.

Điều này **không** cho phép main đọc mảng đang bị các task sửa **trước khi** đã có điểm đồng bộ hoàn tất; cũng không làm an toàn các mutation đồng thời không được bảo vệ ở nơi khác.

`join()` là mốc chờ một task, không phải một cơ chế “khóa tất cả biến”. Nếu có thread bên ngoài tiếp tục sửa dữ liệu đầu vào trong lúc Fork/Join đang chạy, vẫn cần thiết kế đồng bộ phù hợp hoặc dùng snapshot immutable.

## 11. ForkJoinPool.commonPool() và pool riêng

JDK cung cấp pool dùng chung:

```java
ForkJoinPool common = ForkJoinPool.commonPool();
```

Pool này được chia sẻ bởi các thành phần Java sử dụng common pool theo mặc định, và các hoạt động như một số `parallelStream()` hay `CompletableFuture` bất đồng bộ có thể liên quan đến nó tùy cách gọi và môi trường. Dùng common pool giúp **tái sử dụng worker** mà không tạo pool mới mỗi phép tính, nhưng cũng có rủi ro workload không liên quan cạnh tranh CPU.

So sánh:

| Cách dùng | Ưu điểm | Cân nhắc |
|---|---|---|
| `ForkJoinPool.commonPool()` | Pool chia sẻ, không cần tự quản lý worker cho mỗi phép tính. | Không điều khiển riêng mức tranh chấp giữa nhiều subsystem; không shutdown common pool như pool riêng. |
| `new ForkJoinPool(parallelism)` | Chủ động chọn mức parallelism cho nhóm công việc và quản lý lifecycle. | Tạo pool tốn tài nguyên; phải shutdown khi không còn dùng. |
| `pool.invoke(rootTask)` | Caller chờ kết quả của cây tác vụ gốc. | Caller bị block cho tới khi root xong; nếu root kẹt thì caller cũng có thể kẹt. |
| `pool.submit(task)` | Trả Future-like handle để chờ ở bước khác. | Cần quản lý completion, timeout, hủy và lỗi. |

**Đừng tạo một `new ForkJoinPool()` cho mỗi phần tử hoặc mỗi nhánh.** Thông thường chỉ cần một pool cho cả cây. Task con được fork vào cơ chế làm việc của pool, không tự quản lý một pool riêng.

`commonPool()` có lifecycle đặc biệt của pool dùng chung; lời `shutdown()` trên common pool không có hiệu ứng giống shutdown pool riêng. Đừng để một chức năng trong hệ thống tự ý shutdown tài nguyên dùng chung mà nhiều thành phần khác đang sử dụng.

## 12. CPU-bound tốt, blocking I/O cần thận trọng

Fork/Join được tối ưu cho nhiều task tính toán ngắn, tách độc lập và có khả năng work-stealing. Không nên nhét hàng nghìn lời gọi I/O chặn vào ForkJoinTask rồi mặc định sẽ mở rộng giống pool dành cho blocking requests.

Các vấn đề khi blocking:

1. Một worker bị chặn ở socket, database hay lock dài có thể không tham gia lấy công việc khác.
2. Nếu các task chờ lẫn nhau mà không dùng cơ chế phối hợp phù hợp, pool có thể không tiến triển; một số cấu trúc chờ còn gây deadlock.
3. Tăng parallelism một cách tùy tiện có thể chuyển nghẽn sang service/database ngoài, không giúp hệ thống nhanh hơn.
4. Các lời gọi I/O thường cần **timeout ngay tại API I/O** và cancellation/cleanup độc lập.

`ForkJoinPool.managedBlock(ManagedBlocker)` là cơ chế để pool được thông báo về một số tình huống block và có thể bù worker theo điều kiện cho phép. Nó **không** biến blocking I/O thành non-blocking, **không** bảo đảm không deadlock và **không** tự giải quyết backpressure/timeout.

Nếu bài toán chủ yếu là I/O, một `ThreadPoolExecutor` phù hợp, asynchronous I/O, hoặc thiết kế task khác có thể đơn giản và hiệu quả hơn. Với phép tính CPU nặng và tách độc lập, Fork/Join thường đáng thử nghiệm.

## 13. Lỗi, hủy, thời hạn và exception

`RecursiveTask.compute()` có thể ném runtime exception. Khi task được gọi qua `pool.invoke()` hoặc `join()`, lỗi có thể được truyền tới thread đang đợi theo ngữ nghĩa ForkJoinTask. Không mặc định phần còn lại của toàn bộ cây đã được cleanup chỉ vì một nhánh ném exception; task khác có thể đang chạy và cần hợp đồng quản lý dữ liệu/lỗi riêng.

`ForkJoinTask` cũng triển khai `Future`, nên có những thao tác như `get()`, `get(timeout, unit)`, `cancel()`, `isDone()`, `isCancelled()`. Nhưng:

- `join()` thông thường **không có tham số timeout** và không khai báo `InterruptedException`.
- `get(timeout)` giới hạn thời gian chờ của caller; **không tự dừng tác vụ** khi hết hạn.
- `cancel(true)` của ForkJoinTask **không nên được hiểu** là bảo đảm interrupt worker đang chạy: ForkJoinTask cancellation theo hợp đồng có giới hạn riêng; việc hủy có thể không khiến code đang thực thi dừng.
- `isDone()` chỉ cho biết task ở trạng thái completed/cancelled theo API, không chứng minh mọi side effect và external resource đã được dọn.

Một task chạy quá lâu cần có chiến lược **cooperative cancellation**, điểm kiểm tra dừng, xử lý interruption phù hợp, deadline khi cần và cleanup trong `finally`. Nếu dùng pool riêng, caller cần quản lý `shutdown()`/`awaitTermination()` có giới hạn thay vì mặc định worker luôn kết thúc.

Đừng dùng `Thread.stop()` hay cưỡng bức hủy một nhánh khi nó đang sửa shared state; nguy cơ phá invariant vẫn tồn tại.

## 14. Những sai lầm về thuật toán và hiệu năng

| Sai lầm | Vì sao gây vấn đề? | Cách cải thiện |
|---|---|---|
| Fork từng phần tử một. | Tạo quá nhiều task, overhead lớn hơn phép tính. | Dùng threshold cho base case. |
| Không có base case/điều kiện dừng. | Đệ quy vô hạn, có thể `StackOverflowError` hoặc tràn công việc. | Bảo đảm chia làm đoạn nhỏ hơn và có ngưỡng dừng. |
| `left.fork(); left.join(); right.compute();`. | Join quá sớm làm mất cơ hội chồng lấp right với left. | Fork một nhánh, tự compute nhánh kia, rồi join. |
| Fork một task rồi không join khi kết quả cần thiết. | Parent có thể trả kết quả thiếu/chưa hoàn tất. | Join các nhánh cần gộp trước khi trả parent. |
| Dùng chung một mutable accumulator. | Data race, lost update hoặc contention nặng. | Trả result cục bộ hoặc chia vùng ghi không giao nhau. |
| Coi `parallelism=8` nghĩa tám lõi luôn chạy 100%. | Workload nhỏ, imbalance hoặc blocking khiến thread rảnh. | Đo CPU/steal, cải thiện chia nhánh và threshold. |
| Đưa I/O chặn vào task mà không tính đến pool. | Worker bị giữ lại, giảm throughput/deadlock. | Dùng executor/async I/O thích hợp hoặc managedBlock khi phù hợp. |
| Giả định thứ tự chạy nhánh ổn định. | Work-stealing, scheduler và `join()` có thể tạo lịch khác. | Xác định output từ dữ liệu/gộp kết quả, không dựa lịch chạy. |
| Ghép kết quả bằng phép không associative mà cần kết quả bất biến. | Thứ tự cây gộp có thể ảnh hưởng đáp án. | Định nghĩa combine đúng toán học hoặc ghi rõ sai số/thứ tự. |
| Tạo pool mới cho mọi lời gọi đệ quy. | Tiêu tốn thread và tài nguyên. | Sử dụng một pool cho cả cây. |
| Quên shutdown pool riêng. | Tài nguyên pool có thể tồn tại lâu không cần thiết. | Đóng lifecycle tại owner và chờ khi thích hợp. |
| Đọc dữ liệu mutable trước điểm hoàn tất. | Có thể thấy dữ liệu cập nhật một phần. | Đợi invoke/join và dùng giao thức đồng bộ đúng. |

## 15. Thiết kế bài toán chia để trị có hệ thống

Trước khi chọn Fork/Join, có thể dùng checklist:

1. **Bản tuần tự có đúng chưa?** Xác định kết quả chuẩn, xử lý empty input, overflow và biên vùng dữ liệu.
2. **Chia thế nào?** Thường dùng đoạn half-open `[from,to)` để hai nhánh không trùng; `middle = from + (to-from)/2` tránh một dạng overflow khi tính midpoint.
3. **Base case là gì?** Nếu `to-from <= threshold`, tính trực tiếp để không tạo task con quá nhỏ.
4. **Hai nhánh có độc lập không?** Nếu cùng sửa object, cần kiểm soát shared state hoặc thiết kế trả kết quả riêng.
5. **Combine có đúng không?** Với tổng/min/max, combine đơn giản; với các thuật toán không associative cần xét thứ tự.
6. **Có bao nhiêu tác vụ?** Ước lượng overhead, đừng nhầm nhiều task với nhiều CPU chạy đồng thời.
7. **Chọn pool nào?** Common pool cho workload chung được chấp nhận; pool riêng nếu cần isolation và lifecycle.
8. **Có chặn không?** Nếu task phải đợi I/O hoặc đợi tài nguyên ngoài, đánh giá lại Executor Framework và managedBlock.
9. **Xử lý lỗi/hủy/timeout?** Cấu trúc cây task cần quy tắc dọn dẹp và theo dõi completion.
10. **Đo đúng hiệu năng?** Warm-up JIT, so tuần tự, thử nhiều threshold/dữ liệu, kiểm tra kết quả.
11. **Tránh bị phân tán resource:** không tạo thêm pool/thread trong `compute()` nếu không có lý do rõ.
12. **Thiết kế API bên ngoài:** chỉ công bố một phương thức compute mức cao; không bắt caller quản lý task con một cách tùy tiện.

## 16. Fork/Join, ExecutorService và parallel stream

| Nhu cầu | API thường cân nhắc | Điểm lưu ý |
|---|---|---|
| Cây tính toán phân nhánh đệ quy, gộp kết quả | `ForkJoinPool` + `RecursiveTask`. | Kiểm soát chia nhánh/threshold; phải thiết kế result và join. |
| Biến đổi vùng dữ liệu tách biệt | `RecursiveAction`. | Ghi vùng không trùng, parent đợi đủ child. |
| Danh sách tác vụ độc lập không đệ quy | `ExecutorService.invokeAll()` hoặc `submit()`. | Timeout, queueing và cancellation vẫn cần thiết. |
| Xử lý collection theo pipeline | `parallelStream()` khi tác vụ phù hợp. | Dễ dùng nhưng vẫn phải tránh shared mutable state và cần benchmark. |
| I/O chặn, API ngoài | Executor/async I/O phù hợp workload. | Không mặc định Fork/Join tối ưu cho blocking. |
| Công việc ít và phép tính rất rẻ | Vòng lặp tuần tự. | Không chịu overhead task creation/work-stealing. |

Fork/Join là một công cụ mạnh, không phải lý do để **luôn song song hóa**. Việc tính tổng một mảng nhỏ có thể chạy nhanh hơn bằng vòng `for`. Ngược lại, khi có mảng lớn, nhiều lõi và phép tính đủ nặng, mô hình chia để trị thường dễ tạo tính song song mà không phải tự điều phối hàng nghìn `Thread`.

## 17. Tự kiểm tra kiến thức

1. **Divide-and-conquer có ba bước logic nào?** Chia thành bài toán con, xử lý bài toán con/base case, rồi gộp kết quả.
2. **`RecursiveTask` khác `RecursiveAction` thế nào?** Task trả giá trị kết quả và action không trả kết quả từ compute.
3. **`ForkJoinPool` có tạo một thread hệ điều hành cho mỗi task không?** Không; nó tái sử dụng worker và lập lịch nhiều ForkJoinTask.
4. **Work-stealing dùng để làm gì?** Worker đang rảnh có thể lấy tác vụ từ queue của worker khác để cân bằng công việc.
5. **Vì sao hay dùng `left.fork(); right.compute(); left.join();`?** Cho left cơ hội chạy song song trong khi worker hiện tại vẫn tính right.
6. **Threshold quá nhỏ có hậu quả gì?** Số task/chi phí điều phối tăng quá mức.
7. **Có bắt buộc nhiều task sẽ chạy song song không?** Không; mức parallelism, dữ liệu và scheduler quyết định thực tế.
8. **Tại sao không dùng một biến tổng mutable chung?** Nhiều task có thể update cạnh tranh, mất cập nhật hoặc tăng contention.
9. **Hai task `RecursiveAction` cùng sửa mảng có an toàn không?** Chỉ khi vùng ghi không trùng hoặc có giao thức đồng bộ thích hợp.
10. **`pool.invoke(root)` khác `pool.execute(root)`?** Invoke đợi root hoàn tất/nhận kết quả; execute chỉ nộp task và không chờ ngay.
11. **`ForkJoinTask.join()` có phải `Thread.join()` không?** Không; một cái chờ task, một cái chờ thread.
12. **`ForkJoinTask.join()` có timeout không?** Không; nếu cần chờ hữu hạn, xét `get(timeout, unit)` và cancellation protocol.
13. **Fork/Join có phù hợp xử lý hàng nghìn socket blocking không?** Thường không phải lựa chọn mặc định; cân nhắc API blocking/async khác.
14. **Vì sao `Stats` immutable dễ gộp an toàn hơn shared accumulator?** Mỗi leaf trả kết quả riêng và parent combine sau join.
15. **Có thể luôn nhận lợi ích tốc độ lớn hơn chạy tuần tự không?** Không; overhead và chi phí memory/scheduling có thể lớn hơn công việc hữu ích.

**Ghi nhớ:** Fork/Join dùng **chia để trị + task nhẹ + work-stealing + join kết quả** để khai thác song song cho những bài toán có nhánh độc lập. Tính đúng đắn dựa vào base case, phân vùng không giao nhau, cách gộp và đồng bộ hoàn tất; hiệu năng dựa vào workload, threshold và cấu hình pool — không dựa vào số task được tạo.
