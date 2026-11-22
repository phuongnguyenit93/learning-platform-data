# RecursiveTask<V> so với RecursiveAction trong Java Fork/Join

## 1. Tổng quan: cùng Fork/Join, khác hợp đồng kết quả

**Fork/Join Framework** trong `java.util.concurrent` là mô hình thực hiện tác vụ chia để trị: chia bài toán thành những phần đủ độc lập, phân phối công việc lên các worker, rồi chờ và tổng hợp khi cần. **ForkJoinPool** dùng **work stealing** để các worker đang nhàn rỗi có thể lấy việc từ những worker khác, qua đó cân bằng tải của tác vụ có thể chia nhỏ.

Hai lớp cần phân biệt:

- **`RecursiveTask<V>`**: định nghĩa `protected V compute()`. Task tính toán và **trả về một kết quả** kiểu `V`. Lựa chọn tự nhiên cho bài toán tổng, trung bình, tìm max, đếm, tìm kiếm hoặc thu thập thống kê.
- **`RecursiveAction`**: định nghĩa `protected void compute()`. Task thực hiện công việc **không trả giá trị từ `compute()`**. Thường dùng để cập nhật từng phân vùng độc lập của mảng, biến đổi dữ liệu tại chỗ hoặc áp dụng hiệu ứng lên những vùng được phân chia rõ.

Cả hai đều kế thừa **ForkJoinTask**, có thể được gửi đến **ForkJoinPool**, gọi `fork()`, `join()`, `invoke()`, chịu cùng nguyên lý xếp lịch và cùng những yêu cầu an toàn dữ liệu. Khác biệt quan trọng nhất là **có cần trả về/gộp kết quả của các nhánh hay không**, chứ không phải kiểu nào “chạy nhanh hơn” mặc định.

**Chọn nhanh:** cần `return` giá trị từ mỗi nhánh để combine → **RecursiveTask<V>**; cần xử lý nhiều vùng dữ liệu mà không cần nhánh trả giá trị → **RecursiveAction**, với điều kiện quản lý side effect an toàn.

## 2. Bảng so sánh trực diện

| Nội dung | `RecursiveTask<V>` | `RecursiveAction` |
|---|---|---|
| Kế thừa | `ForkJoinTask<V>` | `ForkJoinTask<Void>` |
| Phương thức override | `protected V compute()` | `protected void compute()` |
| Base case | Tính trực tiếp rồi **return V** | Thực hiện trực tiếp rồi **return;** hoặc kết thúc thân hàm |
| Sau khi chia nhánh | Lấy kết quả nhánh con và **combine** | **join** để chờ các nhánh hoàn tất |
| Giá trị của `join()` khi thành công | Giá trị `V` | `null` (kiểu `Void`) |
| Giá trị của `pool.invoke(...)` khi thành công | Giá trị `V` | `null` (kiểu `Void`) |
| Ví dụ điển hình | Sum, count, max, tree reduction | Cập nhật vùng ảnh, biến đổi vùng mảng |
| Lỗi thiết kế dễ gặp | Không gộp đủ nhánh, chia quá nhỏ | Data race do nhiều nhánh ghi cùng vùng |

**Lưu ý về `Void`:** `compute()` của RecursiveAction có kiểu `void`. Tuy nhiên `RecursiveAction` kế thừa `ForkJoinTask<Void>`, nên `join()` và `pool.invoke(action)` có kiểu trả về `Void`; chúng trả `null` nếu hoàn thành bình thường. Phân biệt **kiểu trả về của `compute`** với kiểu trả về của các API kế thừa.

Một `RecursiveTask<V>` vẫn có thể gây side effect, và một `RecursiveAction` vẫn có thể tạo dữ liệu đầu ra bằng cách cập nhật đối tượng chia sẻ. API không cưỡng chế tính thuần khiết; người lập trình phải thiết kế vùng đọc/ghi an toàn.

## 3. Cơ chế fork, compute, join và work stealing

Đệ quy chia để trị theo trình tự:

1. Xác định **base case**, ví dụ đoạn mảng dài tối đa `THRESHOLD`. Khi đạt ngưỡng, tính tuần tự, không tạo thêm task.
2. Nếu chưa đạt ngưỡng, chia khoảng `[from, to)` thành `[from, middle)` và `[middle, to)`.
3. **fork một nhánh** để worker khác có thể lấy xử lý.
4. **compute nhánh còn lại ngay trên worker hiện tại**.
5. **join** nhánh đã fork để chờ hoàn tất, lấy kết quả hoặc bảo đảm side effect đã thực hiện.
6. Với RecursiveTask, **combine và return**; với RecursiveAction, kết thúc sau khi đã join các nhánh cần đợi.

~~~text
               Task [0, 16)
                    |
               vượt threshold?
                /        \
               có       không
               |           |
          chia hai phần   xử lý tuần tự
           /        \
      fork trái    compute phải
           \        /
             join trái
                 |
          RecursiveTask: combine + return V
          RecursiveAction: hoàn tất (void)
~~~

**`fork()` không tạo thread hệ điều hành mới cho mỗi nhánh.** Nó đưa một ForkJoinTask vào cơ chế thực thi của pool; worker thực sự chạy có thể là worker hiện tại hoặc worker khác. Work stealing không bảo đảm thứ tự hoàn thành giữa các task, nên ví dụ xác minh phải dựa trên **kết quả**, không dựa trên thứ tự dòng log.

Mẫu phổ biến:

~~~java
// MÃ MINH HỌA: các kiểu và phương thức phụ thuộc bài toán cụ thể.
LeftTask left = new LeftTask(...);
left.fork();
Result rightResult = new RightTask(...).compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
~~~

Đây là **đoạn ý tưởng**, không phải class độc lập. Không fork cả hai nhánh rồi ngay lập tức chờ cả hai một cách máy móc: việc tính một nhánh trực tiếp thường giảm số thao tác lập lịch. Nhiều `ForkJoinTask` nhỏ không đồng nghĩa nhiều CPU hơn.

## 4. RecursiveTask<V>: ví dụ tính tổng mảng

Công thức đệ quy cho tổng là:

`sum(range) = sum(leftRange) + sum(rightRange)`.

Khi `range` đủ nhỏ, chạy vòng lặp tuần tự. Với các nhánh lớn, trả tổng cục bộ để cha gộp lại. Không cần biến tổng chung hoặc lock, vì kết quả được chuyển qua `join()`.

### Mã Java 17 đầy đủ

Lưu thành **RecursiveSumDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class RecursiveSumDemo {
    private static class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 3;

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
            if (to - from <= THRESHOLD) {
                long total = 0;
                for (int i = from; i < to; i++) {
                    total += values[i];
                }
                return total;
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, middle);
            SumTask right = new SumTask(values, middle, to);

            left.fork();
            long rightTotal = right.compute();
            long leftTotal = left.join();
            return leftTotal + rightTotal;
        }
    }

    public static void main(String[] args) {
        long[] numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(
                    new SumTask(numbers, 0, numbers.length));
            System.out.println("sum=" + result);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac RecursiveSumDemo.java
java RecursiveSumDemo
~~~

Stdout chính xác:

~~~text
sum=78
~~~

**Phân tích:**

- Các khoảng `[from, to)` là **nửa mở**: bao gồm `from`, loại trừ `to`. Nhờ vậy hai khoảng con không ghi hoặc đọc trùng phần tử do lỗi biên.
- `THRESHOLD=3` phục vụ ví dụ dễ quan sát; ngoài thực tế cần benchmark để chọn ngưỡng.
- Nếu độ dài đoạn nhỏ hơn hoặc bằng 3, vòng lặp cộng trực tiếp và `return total`. Đây là base case bảo đảm đệ quy dừng.
- Nếu lớn hơn, `left.fork()` đưa nhánh trái lên lịch, nhánh phải được tính trực tiếp bằng `right.compute()`. `left.join()` nhận tổng nhánh trái.
- `return leftTotal + rightTotal` gộp hai nhánh thành kết quả cha. `pool.invoke` chạy root và đợi root hoàn tất; tổng 1 tới 12 là **78**, không phụ thuộc thứ tự scheduling.

Đặc điểm về generic: `RecursiveTask<Long>` trả về đối tượng `Long`, Java hỗ trợ unboxing sang `long`. Không thể dùng `RecursiveTask<long>` vì tham số kiểu generic phải là reference type. Với tổng lớn, lưu ý giới hạn `long` và overflow.

## 5. RecursiveAction: ví dụ biến đổi mảng tại chỗ

Bài toán: chuyển từng từ trong mảng thành chữ hoa. Ta không cần trả về mảng mới từ mỗi nhánh; mỗi nhánh được giao **một phân đoạn độc quyền** của mảng gốc và sửa đúng đoạn đó. `RecursiveAction` biểu đạt ý định này rõ ràng.

### Mã Java 17 đầy đủ

Lưu thành **RecursiveUppercaseDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class RecursiveUppercaseDemo {
    private static class UppercaseAction extends RecursiveAction {
        private static final int THRESHOLD = 2;

        private final String[] words;
        private final int from;
        private final int to;

        UppercaseAction(String[] words, int from, int to) {
            this.words = words;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= THRESHOLD) {
                for (int i = from; i < to; i++) {
                    words[i] = words[i].toUpperCase(Locale.ROOT);
                }
                return;
            }

            int middle = from + (to - from) / 2;
            UppercaseAction left =
                    new UppercaseAction(words, from, middle);
            UppercaseAction right =
                    new UppercaseAction(words, middle, to);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) {
        String[] words = {"java", "fork", "join", "tasks"};
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new UppercaseAction(words, 0, words.length));
            System.out.println(Arrays.toString(words));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac RecursiveUppercaseDemo.java
java RecursiveUppercaseDemo
~~~

Stdout:

~~~text
[JAVA, FORK, JOIN, TASKS]
~~~

**Điều khác với RecursiveTask:**

- `protected void compute()` không tạo `Long` hoặc một giá trị trả về cho cha. Trong base case chỉ xử lý vùng rồi **return;**.
- Các nhánh cùng giữ tham chiếu tới `words`, nhưng chỉ ghi vào **các khoảng không giao nhau**: một nhánh `[from, middle)`, nhánh kia `[middle, to)`.
- Nhánh phải chạy trực tiếp; `left.join()` bảo đảm nhánh trái kết thúc. Khi root `invoke()` trả về bình thường, tất cả các nhánh đã kết thúc và việc in mảng sau đó nhận kết quả.
- `Locale.ROOT` cho kết quả có thể kiểm tra độc lập với locale mặc định của máy.

**Thận trọng:** Không thể suy ra rằng `RecursiveAction` tự động an toàn. Nếu nhiều nhánh cùng gọi `sharedList.add(...)` trên `ArrayList` thường hoặc cùng cập nhật `sharedCounter++`, có thể xảy ra race. Cần chia vùng độc quyền, hoặc sử dụng cấu trúc/đồng bộ phù hợp khi phải chia sẻ.

## 6. Hai cách tiếp cận cho cùng một dạng công việc

### Tính một giá trị tổng hợp

Nếu muốn đếm số phần tử thỏa điều kiện, cách tự nhiên là mỗi `RecursiveTask<Integer>` trả số đếm của nhánh; cha cộng hai số lại. Tránh để mọi `RecursiveAction` gọi `AtomicInteger.incrementAndGet()` trên cùng một biến đếm nếu mục tiêu là mở rộng hiệu năng: tăng contention có thể làm chậm tác vụ song song.

### Biến đổi dữ liệu tại chỗ

Nếu muốn thay đổi từng pixel trong mảng ảnh, `RecursiveAction` với các phân đoạn không chồng nhau tránh phải tạo nhiều mảng kết quả và ghép lại. Nhưng nếu yêu cầu trả về một ảnh mới bất biến, có thể chọn `RecursiveTask<Result>` hoặc chuẩn bị một mảng đích riêng rồi dùng Action ghi vào những phân đoạn độc quyền; lựa chọn phụ thuộc vào **ownership và cách công bố dữ liệu**.

| Bài toán | Gợi ý | Lý do |
|---|---|---|
| Tổng, max, min, đếm | `RecursiveTask<Long>` hoặc kiểu kết quả phù hợp | Mỗi nhánh trả phần kết quả và gộp |
| Tìm một đối tượng | `RecursiveTask<Optional<T>>` hoặc dạng kết quả riêng | Cần biểu diễn kết quả thành công/không tìm thấy |
| Biến đổi vùng mảng tại chỗ | `RecursiveAction` | Có thể chia vùng ghi độc quyền |
| Xuất ra tập dữ liệu mới | Tùy thiết kế; Task trả kết quả hoặc Action ghi vùng output riêng | Cần xác định cách ghép kết quả |
| Gọi HTTP/JDBC blocking | Thường chọn executor phù hợp I/O | ForkJoin worker không phát huy khi bị chặn |
| Một thao tác nhỏ, không chia được | Thực thi tuần tự | Tránh overhead tạo task |

Không có quy tắc “RecursiveAction nhanh hơn vì không tạo kết quả”. Thực tế còn phụ thuộc phần công việc tính toán, cấu trúc dữ liệu, phân phối task và chi phí đồng bộ.

## 7. Hiểu API chính xác: compute, fork, join, invoke và invokeAll

**`compute()`** là phương thức bạn override. Gọi trực tiếp `right.compute()` là **lời gọi Java đồng bộ** trong thread hiện tại; nó không tự tạo luồng hay đưa task vào queue.

**`fork()`** đưa task vào cơ chế thực thi của Fork/Join. Worker nào chạy task và chạy lúc nào phụ thuộc lập lịch, không phải cam kết của `fork()`. Mỗi nhánh mới thường cần một instance task mới; không dùng lại một task đã hoàn tất như thể nó là một job mới độc lập.

**`join()`** đợi task hoàn tất, trả kết quả `V` (Task) hoặc `null` (Action). Worker Fork/Join có thể hỗ trợ thực thi task trong lúc chờ, khác với mô hình thụ động đơn giản. `join()` có thể ném unchecked exception nếu tác vụ thất bại hoặc bị hủy. `join()` **không khai báo checked** `InterruptedException`/`ExecutionException` như `Future.get()`; không thể coi hai phương thức này giống hệt nhau.

**`pool.invoke(root)`** gửi root task vào pool và đợi root hoàn tất. Với `RecursiveTask<Long>` nó trả `Long`; với `RecursiveAction` nó trả `Void` (`null` khi thành công). Các lệnh `pool.submit(task)` và `pool.execute(task)` cũng có thể dùng để đưa task vào pool, nhưng cách lấy Future hoặc chờ kết quả khác với `invoke` đồng bộ.

**`ForkJoinTask.invokeAll(a, b)`** cho phép thực hiện và chờ các subtask được đưa vào; với `RecursiveTask` vẫn phải lấy các giá trị để ghép khi bài toán cần. Đây là một cách viết khác, không bắt buộc cho mọi bài toán.

Với task chạy ở nền, cần xác định **ai chịu trách nhiệm join/get**. Nếu submit rồi bỏ qua kết quả và không có cơ chế báo lỗi, exception trong task có thể bị bỏ qua trong logic ứng dụng.

## 8. Chọn threshold và mức parallelism

Nếu chia một mảng triệu phần tử thành một triệu `ForkJoinTask`, chi phí cấp phát object, scheduling, đồng bộ và GC có thể lớn hơn phép tính cần làm. Nếu threshold quá lớn, số task không đủ để trải việc qua các worker.

Cách chọn thực tế:

1. Xác định **chi phí thực thi một leaf** (base case) khi chạy tuần tự.
2. Chọn ngưỡng đủ lớn để mỗi leaf có lượng công việc đáng kể; nhưng vẫn tạo đủ nhánh để giữ các worker bận, kể cả khi thời gian thực hiện các nhánh không đều.
3. Benchmark nhiều kích thước/ngưỡng trên **dữ liệu và phần cứng thực**, sau warm-up/JIT; đo wall time, CPU utilization, allocation/GC, contention và throughput.
4. Với dữ liệu có chi phí xử lý rất không đều, chỉ chia đôi số lượng phần tử chưa chắc cân bằng **khối lượng công việc**; có thể cần chiến lược chia khác.
5. Đo tốc độ tuần tự làm baseline: Fork/Join chỉ có ý nghĩa khi lợi ích parallelism lớn hơn overhead quản lý.

`ForkJoinPool(parallelism)` đặt cấu hình mức song song mục tiêu. Nó không bảo đảm luôn có đúng số thread đó chạy trong mọi thời điểm, và không tạo thêm CPU ngoài tài nguyên thực sự cấp cho JVM. Nếu ứng dụng chạy trong container, cần cân nhắc CPU quota, các pool khác và mức tải toàn hệ thống.

**Threshold=2 hoặc 3 trong ví dụ là giá trị minh họa.** Với tác vụ đơn giản như cộng số, ngưỡng tối ưu có thể lớn hơn nhiều; không đưa các ngưỡng trong ví dụ vào production mà chưa đo.

## 9. Tính đúng đắn: phân đoạn, memory visibility, và data race

Mỗi nhánh phải có ranh giới dữ liệu rõ ràng.

- **Đọc chung dữ liệu bất biến:** nhiều `RecursiveTask` đọc một mảng không bị sửa trong lúc tính toán là trường hợp thuận lợi.
- **Ghi vùng riêng:** nhiều `RecursiveAction` cập nhật các đoạn không giao nhau của cùng một mảng là mẫu hợp lý.
- **Ghi cùng dữ liệu chia sẻ:** phải dùng đồng bộ hoặc concurrent structure khi phù hợp; nếu không, có thể mất cập nhật và vi phạm Java Memory Model.
- **Gộp dữ liệu:** Task trả kết quả cục bộ qua `join()`; cha gộp kết quả sau khi nhánh con hoàn tất, giảm cạnh tranh.

Ví dụ không an toàn:

~~~java
// Chỉ là đoạn minh họa với sharedCounter là biến giả định:
sharedCounter++; // Không nguyên tử khi nhiều task cùng cập nhật.
~~~

Các hành động hoàn tất và join cung cấp cơ chế đồng bộ cần thiết để quan sát kết quả sau khi task hoàn tất; tuy nhiên chúng **không khiến việc hai nhánh đồng thời ghi trùng vị trí trở nên thread-safe**. Trong ví dụ Action, mảng chỉ được đọc để in **sau khi** root `pool.invoke()` trả về bình thường.

Với bất kỳ chia nhánh nào, kiểm tra các khoảng `[from, middle)` và `[middle, to)` đủ bao phủ mảng, không chồng lấp, và base case xử lý cả khoảng rỗng nếu thuật toán cho phép. Bỏ sót phần tử hoặc lặp phần tử có thể tạo kết quả sai dù không có data race.

## 10. Exception: task thất bại không tự trở thành null

Nếu `compute()` ném unchecked exception, task kết thúc bất thường; `join()` hoặc `invoke()` có thể truyền exception cho caller. Khi truyền qua các worker, phần triển khai có thể tái tạo/wrap ngoại lệ, nên **không dựa vào chuỗi message hay stack trace giống hệt mọi lịch thực thi**.

Ví dụ đầy đủ **RecursiveFailureDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class RecursiveFailureDemo {
    private static class FailingTask extends RecursiveTask<Integer> {
        @Override
        protected Integer compute() {
            throw new IllegalArgumentException("bad element");
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            try {
                pool.invoke(new FailingTask());
            } catch (IllegalArgumentException failure) {
                System.out.println(
                        "error=" + failure.getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac RecursiveFailureDemo.java
java RecursiveFailureDemo
~~~

Stdout:

~~~text
error=IllegalArgumentException
~~~

Ví dụ kiểm tra **loại exception**, không phụ thuộc message có thể khác khi lỗi đi qua worker. Một nhánh lỗi **không tự rollback những nhánh khác**; các nhánh còn lại có thể đã hoàn tất hoặc còn đang chạy. Nếu tác vụ có side effect, phải thiết kế xử lý lỗi, idempotency hoặc khôi phục dữ liệu ở tầng nghiệp vụ tương ứng.

Nếu `join()/invoke()` thất bại do cancellation, chúng có thể ném `CancellationException`. Khác với `Future.get()`, các phương thức `join()/invoke()` không buộc caller khai báo `ExecutionException`; đừng vì vậy bỏ qua đường đi lỗi.

## 11. Cancellation và giới hạn ngắt tác vụ

`RecursiveTask` và `RecursiveAction` kế thừa khả năng `cancel(...)` của ForkJoinTask/Future. Nhưng **không nên giả định `cancel(true)` sẽ interrupt thread đang chạy** như trong một số tác vụ dùng `FutureTask`: ForkJoinTask không dựa trên interruption để điều khiển hủy theo cách đó. Nếu bài toán cần dừng sớm, thiết kế một cờ dừng hợp tác phù hợp, kiểm tra tại những điểm an toàn, và tránh công bố kết quả trước khi các subtask cần thiết kết thúc.

Một ForkJoinTask đã chuyển trạng thái canceled không chứng minh mọi phép biến đổi dữ liệu đã được rollback hoặc worker tức thì ngừng tác động. Tình huống này đặc biệt quan trọng với `RecursiveAction` vì nó thường sửa dữ liệu tại chỗ.

Ngoài ra, nếu đã `fork()` nhánh trái rồi phần tính nhánh phải ném lỗi trước khi `join()`, nhánh trái có thể vẫn tiếp tục. Tùy yêu cầu bài toán, cần theo dõi các outstanding tasks, ngăn công bố kết quả chưa đầy đủ và xử lý cleanup phù hợp.

## 12. Không dùng Fork/Join như pool I/O blocking mặc định

Work stealing phát huy tốt khi các leaf task **chủ yếu CPU-bound** và có thể hoàn tất trong thời gian hữu hạn. Khi một worker chờ network, database, file I/O blocking hoặc khóa lâu, worker đó không xử lý các nhánh khác; throughput có thể giảm.

**ForkJoinPool.ManagedBlocker** là cơ chế nâng cao để khai báo một số thao tác blocking với ForkJoinPool nhằm cho pool cân nhắc điều chỉnh worker; nó không biến mọi tác vụ I/O thành ứng viên Fork/Join tốt. Với tác vụ I/O thường xuyên, có thể dùng ExecutorService cấu hình queue/timeout riêng hoặc virtual threads trên Java 21+, kèm giới hạn downstream.

Đừng shutdown `ForkJoinPool.commonPool()` như thể nó thuộc riêng một module. Common pool là tài nguyên JVM dùng chung, có thể được các API khác sử dụng. Với công việc cần kiểm soát parallelism, lỗi và vòng đời, tạo `ForkJoinPool` riêng như ví dụ, rồi shutdown khi không dùng nữa. **shutdown()** không tự đợi mọi task ngừng; khi cần đảm bảo kết thúc, quản lý thêm thời hạn chờ theo API và lifecycle thích hợp.

## 13. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| `RecursiveAction.compute()` cố `return sum` | Sai kiểu trả về, không biên dịch | Dùng `RecursiveTask<Long>` |
| `RecursiveTask<Long>.compute()` không trả giá trị ở một nhánh | Không biên dịch hoặc sai combine | Có base case và return ở mọi đường đi thành công |
| Action không cần `join()` vì “không có kết quả” | Cha có thể công bố khi con chưa xong | Join để bảo đảm completion |
| Fork quá nhiều task nhỏ | Scheduling/GC overhead | Threshold và tính trực tiếp một nhánh |
| Nhiều Action cùng sửa một index/một List không thread-safe | Data race, mất cập nhật | Chia vùng ghi hoặc dùng đồng bộ đúng |
| Task cộng vào biến tổng toàn cục ở mọi nhánh | Contention và nguy cơ sai | Return tổng cục bộ rồi combine |
| Gọi `compute()` và nghĩ là chạy song song | Thực tế chỉ là lời gọi đồng bộ | Dùng fork hoặc submit đúng cách |
| Tin rằng `fork()` luôn tạo thread mới | Hiểu sai scheduling | Pool quản lý worker và work stealing |
| Không kiểm soát base case | Đệ quy sâu hoặc không dừng | Bảo đảm đoạn được chia nhỏ dần |
| Lấy thứ tự log làm kết quả cố định | Scheduling không xác định thứ tự | Test kết quả sau join/invoke |
| Bỏ qua exception/cancellation | Kết quả thiếu hoặc side effect dở dang | Xử lý lỗi và trạng thái rõ ràng |
| Dùng Fork/Join cho blocking I/O mà không thiết kế | Worker bị chiếm, pool dễ nghẽn | Executor phù hợp hoặc mô hình I/O khác |

## 14. Checklist khi lựa chọn

Hãy trả lời lần lượt:

1. **Kết quả cần trả về từ nhánh là gì?** Nếu phải gộp giá trị, ưu tiên `RecursiveTask<V>`; nếu chỉ biến đổi các vùng độc lập, cân nhắc `RecursiveAction`.
2. **Base case và threshold đã được xác định?** Thuật toán chắc chắn dừng và tránh phân rã đến mức overhead vượt lợi ích?
3. **Phân chia dữ liệu có chính xác?** Mọi phần tử nằm trong đúng vùng cần xử lý, không có hai task ghi chung vùng ngoài ý muốn?
4. **Mọi nhánh bắt buộc đã được join?** Kể cả khi nhánh khác lỗi hoặc caller bị hủy, có kiểm soát outstanding task không?
5. **Có đo trước và sau song song?** Có baseline tuần tự, CPU utilization, GC và chi phí phân đoạn?
6. **Tác vụ chủ yếu CPU-bound?** Nếu blocking I/O, đã cân nhắc executor/phương pháp phù hợp hơn?
7. **Exception và side effect có chính sách rõ?** Không ngầm coi tác vụ thất bại là thành công.
8. **Ai sở hữu ForkJoinPool?** Tránh ảnh hưởng common pool và quản lý shutdown cho pool riêng.

**Ghi nhớ:** `RecursiveTask<V>` tạo ra **kết quả của từng nhánh và gộp thành kết quả cuối**; `RecursiveAction` thực hiện **công việc không có giá trị trả về từ compute()**, thường cập nhật các vùng dữ liệu độc lập. Cả hai chạy bằng cơ chế Fork/Join và work stealing của Java; sự khác biệt hiệu năng và độ tin cậy đến từ thuật toán chia việc, cách gộp kết quả, ngưỡng tách, ownership dữ liệu và việc xử lý lỗi.
