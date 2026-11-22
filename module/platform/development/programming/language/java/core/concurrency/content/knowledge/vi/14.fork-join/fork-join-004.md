# `compute()`, `fork()` và `join()` trong Java Fork/Join

Khi một bài toán có thể chia thành các phần độc lập, Java cung cấp **Fork/Join Framework** để tách công việc lớn thành các **subtask** nhỏ, cho nhiều worker xử lý, rồi kết hợp kết quả. Ba lời gọi thường thấy nhất là `compute()`, `fork()` và `join()`. Chúng **không có cùng nghĩa**:

- **`compute()`:** phương thức do lập trình viên viết để mô tả cách giải một task; thường kiểm tra ngưỡng, chia dữ liệu, gọi task con và gộp kết quả. Việc gọi trực tiếp `compute()` là **một lời gọi phương thức thông thường**, chạy trên thread hiện tại.
- **`fork()`:** đưa một `ForkJoinTask` vào cơ chế thực thi bất đồng bộ của Fork/Join để có thể được worker khác xử lý. Nó **không bảo đảm task được chạy trên một thread khác**, cũng không đợi task hoàn tất.
- **`join()`:** đợi một `ForkJoinTask` hoàn tất và lấy kết quả (hoặc truyền tiếp lỗi theo hợp đồng). `join()` không giống `Thread.join()`; khi gọi trong Fork/Join worker, runtime có thể hỗ trợ tiến độ bằng cách thực hiện công việc liên quan thay vì chỉ chờ thụ động.

Ba thao tác phối hợp tạo thành mô hình **divide → fork/compute → join → combine**. Chọn ngưỡng chia, số subtask và thứ tự chờ rất quan trọng: tạo quá nhiều task nhỏ gây overhead, còn chờ sai cách có thể làm mất parallelism hoặc tạo vòng phụ thuộc khó tiến triển.

Bài thuộc phần **Fork/Join** của **Java concurrency nói chung** và dùng Java SE 17+. Không sử dụng annotation, executor hoặc cơ chế chạy tác vụ riêng của Spring Framework.

## 1. Fork/Join giải quyết loại bài toán nào?

Fork/Join phát huy lợi ích khi công việc lớn có thể được chia thành các nhánh **tương đối độc lập**, chẳng hạn:

- Tính tổng, min/max hoặc thống kê trên một mảng rất lớn.
- Biến đổi dữ liệu trên các vùng chỉ số không chồng lấn.
- Xử lý cấu trúc cây với các nhánh có thể tính độc lập.
- Thuật toán chia để trị: merge sort, tìm kiếm song song có kiểm soát.
- Tính toán CPU-bound cần tận dụng nhiều lõi xử lý.

Ví dụ tính tổng mảng:

```text
                  sum[0..16)
                   /       \
            sum[0..8)     sum[8..16)
             /    \         /     \
          [0..4) [4..8) [8..12) [12..16)
             \      \       \       /
                các kết quả con
                       |
                  cộng kết quả
```

Các khoảng ở đây dùng quy ước **`[start, end)`**, tức đầu gồm, cuối không gồm; cách này tránh trùng phần tử giữa hai nhánh.

Nếu dữ liệu chỉ có 10 phần tử, việc tạo nhiều task có thể còn **chậm hơn vòng `for`**. Fork/Join không phải lời hứa cứ chia nhỏ là nhanh: nó có chi phí quản lý task, scheduling, cache và contention.

## 2. Các lớp và interface liên quan

| API | Vai trò chính |
| --- | --- |
| `ForkJoinPool` | Executor chuyên xử lý `ForkJoinTask`, thường dùng **work-stealing** |
| `ForkJoinTask<V>` | Lớp trừu tượng cho tác vụ có thể fork/join, cung cấp `fork`, `join`, `invoke` và trạng thái hoàn tất |
| `RecursiveTask<V>` | Task chia để trị **trả kết quả kiểu `V`** |
| `RecursiveAction` | Task chia để trị **không trả kết quả** |
| `CountedCompleter<T>` | Mô hình hoàn tất dựa trên đếm phụ thuộc, hữu ích cho một số thuật toán phức tạp |
| `ForkJoinPool.commonPool()` | Pool dùng chung ở cấp JVM theo hợp đồng Java; cần cân nhắc tranh chấp tài nguyên |

Hai kiểu thường gặp nhất khi học là `RecursiveTask<T>` và `RecursiveAction`.

```java
import java.util.concurrent.RecursiveTask;

final class SumTask extends RecursiveTask<Long> {
    @Override
    protected Long compute() {
        // Tính trực tiếp hoặc chia task.
        return 0L;
    }
}
```

Đây là **class minh họa**, chưa có `main` hay thuật toán chia thật. Method `compute()` được **override** từ `RecursiveTask`; nó không phải API của `Thread`.

Khi không cần kết quả:

```java
import java.util.concurrent.RecursiveAction;

final class PrintAction extends RecursiveAction {
    @Override
    protected void compute() {
        // Thực hiện tác vụ không trả giá trị.
    }
}
```

Task dạng action vẫn có thể được theo dõi bằng `ForkJoinTask<?>`; chỉ là `compute()` không trả kết quả nghiệp vụ.

## 3. `compute()` là logic thực thi, không phải lệnh tạo thread

Với `RecursiveTask<V>`:

```java
@Override
protected V compute() {
    if (smallEnough()) {
        return solveSequentially();
    }

    RecursiveTask<V> left = createLeft();
    RecursiveTask<V> right = createRight();
    // Chạy/gộp task con theo giao thức Fork/Join.
}
```

Đây là **pseudocode Java minh họa**: các method được nhắc đến chưa định nghĩa.

Khi task được `ForkJoinPool` chạy, runtime gọi logic `compute()` thông qua cơ chế task. Còn nếu lập trình viên trực tiếp gọi `someTask.compute()` từ một nơi có quyền truy cập, đó là **lời gọi đồng bộ trên thread hiện tại**. Bản thân tên `compute` không kích hoạt parallelism.

Một cấu trúc `compute()` tốt thường có:

1. **Base case:** khi đoạn dữ liệu đã đủ nhỏ, tính tuần tự và trả kết quả.
2. **Split:** chọn điểm giữa, tạo task con với các đoạn độc lập.
3. **Dispatch:** `fork` một hoặc nhiều task con, đồng thời xử lý nhánh còn lại.
4. **Join:** đợi/đọc kết quả các task đã fork.
5. **Combine:** gộp kết quả đúng với phép toán của bài toán gốc.

Nếu thiếu base case hoặc không thu nhỏ kích thước ở mỗi lần đệ quy, chương trình có thể tạo task vô hạn, tràn stack hoặc cạn bộ nhớ.

## 4. `fork()` làm gì?

Method:

```java
ForkJoinTask<V> fork()
```

`fork()` **sắp lịch** task cho thực thi bất đồng bộ, thông thường trong pool nơi current worker đang chạy. Task có thể được chính worker đó thực thi sau, hoặc bị worker khác **steal** theo cơ chế work-stealing.

Ví dụ:

```java
left.fork(); // Lên lịch cho nhánh trái; không đợi kết quả.
int rightResult = right.compute(); // Tính ngay trên current thread.
int leftResult = left.join();      // Lấy kết quả nhánh trái.
return leftResult + rightResult;
```

Đây là snippet minh họa trong `compute()`, giả định `left` và `right` là các `RecursiveTask<Integer>` hợp lệ.

**Điểm dễ nhầm:**

- `fork` **không giống `new Thread(task).start()`**. Nó hoạt động trên `ForkJoinTask` trong pool và không lập một Java thread mới cho mỗi subtask.
- `fork` **không bảo đảm chạy song song**. Nếu pool có một worker hoặc dữ liệu nhỏ, kết quả vẫn đúng nhưng hầu như không có parallelism.
- `fork` **không trả kết quả đã tính**. Nó trả handle task, thường chính task để hỗ trợ cách viết chaining.
- Task đã được fork cần được quản lý completion, thường bằng `join`, `invokeAll` hoặc giao thức khác; đừng fork rồi bỏ quên những task ảnh hưởng kết quả.

Tạo 1 triệu task từ 1 triệu phần tử là một ví dụ dễ gây overhead. Cần ngưỡng dừng để mỗi leaf xử lý một đoạn đủ lớn.

## 5. `join()` đợi gì, trả gì và báo lỗi thế nào?

Với một `RecursiveTask<Long>`:

```java
long value = subtask.join();
```

`join` chờ **subtask cụ thể** hoàn tất và trả giá trị của nó nếu thành công.

Nếu task thất bại với unchecked exception, `join` có thể truyền tiếp exception tương ứng tới caller; không nên giả định một kết quả mặc định như `0`. Nếu task bị cancel, `join` có thể ném `CancellationException`.

**Quan trọng:** `ForkJoinTask.join()` không khai báo `InterruptedException` và việc chờ của `join` là **không interruptible theo cách `Future.get()` thường là**. Nếu cần chờ có thể bị ngắt và có timeout, API của `ForkJoinTask` có `get()` / `get(timeout, unit)` theo hợp đồng của `Future`; nhưng cách dùng đó trong worker cần cân nhắc khả năng tiến độ và dependency. Không đổi một thuật toán thành blocking get tùy tiện rồi giả định work-stealing giải quyết mọi vòng chờ.

So sánh:

| Lời gọi | Mục đích |
| --- | --- |
| `subtask.compute()` | Tính ngay phần việc của subtask trên thread hiện tại |
| `subtask.fork()` | Đưa task vào Fork/Join để có thể chạy bất đồng bộ |
| `subtask.join()` | Chờ và lấy kết quả/công bố lỗi của task đã chạy |
| `subtask.invoke()` | Bắt đầu thực thi task và chờ hoàn tất ở ranh giới lời gọi |
| `pool.invoke(task)` | Đưa task gốc vào pool và đợi kết quả |
| `ForkJoinTask.invokeAll(a, b)` | Hỗ trợ thực thi/chờ một nhóm ForkJoinTask |

`join` của Fork/Join **khác** `Thread.join()`: `Thread.join` chờ một thread kết thúc và không trả kết quả tính toán của `RecursiveTask`.

## 6. Mẫu chuẩn: fork một nhánh, compute nhánh còn lại

Một mẫu được khuyên dùng trong nhiều thuật toán chia đôi:

```java
if (length <= threshold) {
    return computeSequentially();
}

var left = new SumTask(data, start, mid, threshold);
var right = new SumTask(data, mid, end, threshold);

left.fork();              // Cho phép một worker khác lấy nhánh trái.
long rightSum = right.compute(); // Current thread không đứng chờ nhàn rỗi.
long leftSum = left.join();      // Đồng bộ kết quả nhánh trái.
return leftSum + rightSum;
```

Đây là snippet minh họa, các biến và class được định nghĩa đầy đủ ở ví dụ tiếp theo.

**Vì sao không nhất thiết fork cả hai?**

- Fork hai nhánh sẽ tạo nhiều scheduling work hơn nếu một nhánh cũng có thể được xử lý ngay.
- Current worker vẫn có thể làm việc hữu ích trên một nhánh trong lúc nhánh kia có thể được steal.
- Chỉ cần chờ kết quả của nhánh đã fork sau khi tính xong nhánh hiện tại.

Đây không phải định lý "fork một nhánh luôn nhanh nhất". Hiệu năng phụ thuộc kích thước input, cách phân hoạch, locality, pool parallelism và workload. Tuy vậy, mẫu **one fork + one direct compute + one join** dễ hiểu và hạn chế tạo task không cần thiết.

## 7. Ví dụ Java 17+: tính tổng mảng bằng `RecursiveTask<Long>`

Lưu thành `ForkJoinSumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int[] data;
        private final int start;
        private final int end;
        private final int threshold;

        SumTask(int[] data, int start, int end, int threshold) {
            this.data = data;
            this.start = start;
            this.end = end;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            if (end - start <= threshold) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += data[i];
                }
                return sum;
            }

            int mid = start + (end - start) / 2;

            SumTask left = new SumTask(
                    data, start, mid, threshold);
            SumTask right = new SumTask(
                    data, mid, end, threshold);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();

            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        int[] numbers = new int[16];
        for (int i = 0; i < numbers.length; i++) {
            numbers[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(
                    new SumTask(numbers, 0, numbers.length, 4));

            System.out.println("Sum: " + result);
            System.out.println("Expected: " + (16L * 17 / 2));
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
```

Stdout **chính xác**, không phụ thuộc lịch chạy:

```text
Sum: 136
Expected: 136
```

Giải thích:

1. Mảng chứa các số 1 đến 16, nên tổng toán học là 136.
2. Task gốc giải `[0,16)`, chia thành hai đoạn không chồng lấn `[0,8)` và `[8,16)`.
3. Khi đoạn còn ≤4 phần tử, leaf task cộng tuần tự; không tạo task con nữa.
4. Mỗi parent fork một nhánh, trực tiếp compute nhánh khác, rồi join kết quả fork.
5. Các phép cộng `long` bảo đảm không overflow với dữ liệu nhỏ này; dùng `long` cũng phù hợp hơn `int` cho tổng lớn.
6. Không có hai task ghi vào mảng; chúng chỉ đọc mảng đã tạo trước `pool.invoke`. Vì vậy không phát sinh data race trên mảng.
7. `pool.invoke` đợi kết quả task gốc; main không in cho đến khi toàn bộ cây tính tổng cần thiết đã kết thúc.
8. `pool.shutdown` biểu thị không nhận thêm task mới; ví dụ không để pool tự tạo tồn tại mãi mà không quản lý vòng đời.

**Đừng suy ra có bốn worker thì bốn task luôn chạy đồng thời.** Hợp đồng đảm bảo kết quả, không đảm bảo mỗi leaf được thực thi bởi một thread khác nhau.

## 8. Vẽ cây task của ví dụ tính tổng

Với `threshold=4`:

```text
SumTask[0,16)  (parent)
├── SumTask[0,8)
│   ├── SumTask[0,4)   => 1+2+3+4       = 10
│   └── SumTask[4,8)   => 5+6+7+8       = 26
│   -> 10+26 = 36
└── SumTask[8,16)
    ├── SumTask[8,12)  => 9+10+11+12    = 42
    └── SumTask[12,16) => 13+14+15+16  = 58
    -> 42+58 = 100

Root: 36 + 100 = 136
```

Tổng số object `SumTask` được tạo trong lần chạy này là **7**: root 1, hai task mức giữa và bốn leaf. Đây là một cây cân đối cố định, nên con số 7 có thể xác định độc lập với việc các task chạy trên worker nào.

**Task object khác thread.** Bảy object task **không** có nghĩa bảy Java threads được tạo. Một số lượng nhỏ worker có thể xử lý hàng ngàn task ngắn bằng cơ chế queue/work-stealing.

## 9. Khi nào dùng `RecursiveAction` thay vì `RecursiveTask`?

Nếu task chỉ **biến đổi dữ liệu** mà không cần trả result tổng hợp, `RecursiveAction` có `compute()` trả `void`.

Ví dụ:

- Tính bình phương và ghi vào các đoạn khác nhau của cùng một array.
- Áp dụng transform cho từng phần tử thuộc vùng chỉ số không chồng lấn.
- Duyệt cây và thực hiện thao tác cục bộ đã được bảo vệ phù hợp.

Điều kiện để an toàn: các task con cần có **ownership vùng dữ liệu rõ ràng**. Nếu hai task cùng ghi một phần tử hoặc cùng sửa `ArrayList` thông thường, việc dùng Fork/Join không tự làm chúng thread-safe.

Nếu task thật sự cần kết quả để combine, `RecursiveTask<V>` thường tự nhiên hơn. Không cần tạo side effect chỉ để truyền kết quả khi kiểu trả về đã hỗ trợ việc đó.

## 10. Ví dụ Java 17+: ghi vào các phân đoạn không chồng lấn

Lưu thành `ForkJoinActionDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinActionDemo {
    static final class SquareAction extends RecursiveAction {
        private final int[] values;
        private final int start;
        private final int end;

        SquareAction(int[] values, int start, int end) {
            this.values = values;
            this.start = start;
            this.end = end;
        }

        @Override
        protected void compute() {
            if (end - start <= 4) {
                for (int i = start; i < end; i++) {
                    values[i] = i * i;
                }
                return;
            }

            int mid = start + (end - start) / 2;
            SquareAction left = new SquareAction(
                    values, start, mid);
            SquareAction right = new SquareAction(
                    values, mid, end);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) {
        int[] values = new int[16];
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new SquareAction(
                    values, 0, values.length));
            System.out.println(Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinActionDemo.java
java ForkJoinActionDemo
```

Stdout chính xác:

```text
[0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100, 121, 144, 169, 196, 225]
```

Vì sao an toàn?

- Mỗi leaf chỉ ghi vào **một khoảng index riêng** của mảng, không có hai writer tới cùng ô.
- Mỗi parent đợi `join()` nhánh đã fork, nên task gốc chỉ hoàn tất sau khi mọi nhánh đã cập nhật xong.
- Main đọc mảng **sau `pool.invoke(...)`** trả về; quan hệ đồng bộ khi chờ completion bảo đảm nhìn thấy những cập nhật đã hoàn thành.
- Nếu thay assignment bằng `values[i]++` trên những đoạn **chồng lấn**, sẽ cần thiết kế khác; không được kỳ vọng Fork/Join tự bảo vệ data race.

## 11. `fork()` rồi `join()` ngay có tạo parallelism hữu ích không?

Một anti-pattern hiệu năng:

```java
left.fork();
long leftValue = left.join(); // Chờ ngay lập tức.
long rightValue = right.compute();
return leftValue + rightValue;
```

Đây là đoạn minh họa trong `compute()`. Current worker không chủ động làm nhánh phải trước khi chờ nhánh trái. Fork/Join runtime có thể hỗ trợ tiến độ khi join, nhưng cách viết này thường **bỏ lỡ một cơ hội rõ ràng** cho current worker tính nhánh còn lại.

Thường tốt hơn:

```java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
```

Các snippet giả định `left/right` và kết quả kiểu `long` đã khai báo.

Không phải mọi `join` sớm đều là deadlock. Đây chủ yếu là lỗi tổ chức công việc và hiệu năng. **Deadlock thực** có thể xảy ra nếu task chờ một dependency vòng, giữ khóa không được nhả hoặc block trên resource chỉ chính task bị chờ mới có thể cung cấp.

Quy tắc thực tế: **đừng chờ một subtask trong khi current thread còn nhánh độc lập có thể tính ngay**.

## 12. `fork()` khác `invoke()` và `pool.invoke()`

Ba phương thức dễ nhầm:

```java
left.fork();         // Schedule; chưa đợi.
Long a = left.join(); // Đợi task đã fork, lấy kết quả.

Long b = right.invoke(); // Thực thi + đợi task ngay.

Long c = pool.invoke(root); // Submit task gốc vào pool + đợi.
```

Đây là snippet minh họa, các biến chưa khai báo trong một class hoàn chỉnh.

**Điểm phân biệt:**

- `ForkJoinTask.invoke()` bắt đầu thực thi và chờ task này hoàn tất theo cách Fork/Join.
- `ForkJoinPool.invoke(task)` là điểm nhập thuận tiện từ thread bên ngoài vào pool: pool xử lý task gốc và caller đợi kết quả.
- `ForkJoinPool.execute(task)` cho phép submit task mà **không đợi** completion tại dòng gọi; hãy lưu handle nếu cần join/get sau.
- `ForkJoinPool.submit(task)` trả task/future handle, cho phép caller quản lý completion theo API.
- `fork()` thuận tiện **bên trong công việc Fork/Join** để tạo các subtask có thể được worker khác lấy.

Khi code ứng dụng khởi tạo pool riêng, gọi `pool.invoke(root)` thường rõ ràng nhất cho một computation đồng bộ cần result. Không nhất thiết phải tự gọi `root.fork()` trên main thread rồi `root.join()`; việc chọn pool chạy task có thể trở nên khó suy luận nếu trộn pool khác nhau.

## 13. `invokeAll` có lợi gì?

`ForkJoinTask.invokeAll(left, right)` là một tiện ích fork/join cho **nhóm task**. Nó sắp xếp thực thi và đợi nhóm hoàn tất theo giao thức Fork/Join, rồi caller có thể lấy kết quả từ những task đó.

```java
ForkJoinTask.invokeAll(left, right);
return left.join() + right.join();
```

Đây là snippet minh họa trong một `RecursiveTask<Integer>`, với `left/right` là task con kiểu số nguyên.

Ưu điểm: dễ đọc khi có nhiều subtask tương đương, và không phải tự viết mọi lời gọi fork/join. Nhưng với thuật toán có thể xử lý một nhánh inline, mẫu one-fork-one-compute đôi khi giảm overhead hơn. **Benchmark với workload thực tế** để chọn.

Khi có lỗi từ task con, phải hiểu chính sách exceptional completion của nhóm; đừng giả định các task đã có side effect tự được rollback khi một task khác throw.

## 14. Ví dụ Java 17+: dùng `ForkJoinTask.invokeAll`

Lưu thành `ForkJoinInvokeAllDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveTask;

public class ForkJoinInvokeAllDemo {
    static final class CountEvenTask extends RecursiveTask<Integer> {
        private final int start;
        private final int end;

        CountEvenTask(int start, int end) {
            this.start = start;
            this.end = end;
        }

        @Override
        protected Integer compute() {
            if (end - start <= 4) {
                int count = 0;
                for (int i = start; i < end; i++) {
                    if ((i & 1) == 0) {
                        count++;
                    }
                }
                return count;
            }

            int mid = start + (end - start) / 2;
            CountEvenTask left = new CountEvenTask(start, mid);
            CountEvenTask right = new CountEvenTask(mid, end);

            ForkJoinTask.invokeAll(left, right);
            return left.join() + right.join();
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(3);
        try {
            int count = pool.invoke(new CountEvenTask(0, 20));
            System.out.println("Even numbers in [0,20): " + count);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinInvokeAllDemo.java
java ForkJoinInvokeAllDemo
```

Stdout chính xác:

```text
Even numbers in [0,20): 10
```

Các số chẵn trong khoảng từ 0 đến 19 là `0,2,4,...,18`: tổng cộng 10. Task gốc và task con chỉ xử lý các khoảng nguyên không chồng lấn. `invokeAll` là **helper quản lý subtask**, không làm phép cộng thay cho code của chúng ta.

Trong một số thuật toán, `invokeAll` có overhead khác với tự fork một nhánh và compute nhánh còn lại; thay đổi cách scheduling không làm thay đổi kết quả toán học nếu mỗi task được viết đúng và không có shared side effect sai.

## 15. Work-stealing: tại sao Fork/Join không tạo một thread cho mỗi subtask?

`ForkJoinPool` có tập worker tương đối giới hạn. Trong quá trình chia để trị, worker thường quản lý queue/deque của các task sinh ra. Worker rảnh có thể **steal** những task chưa xử lý từ worker khác.

Hình dung:

```text
Worker A                         Worker B
--------                         --------
đang compute(root)               rảnh
fork(left)
compute(right)                   steal(left)
  |                                |
  |                                compute(left)
  |                                |
right result                     left result
  |                                |
join(left) <-----------------------+
combine
```

Đây là sơ đồ **cơ chế có thể xảy ra**, không phải lời hứa task trái luôn chạy trên worker B.

Những điểm đúng cần nhớ:

- Work-stealing giúp cân bằng tải khi nhánh có độ dài tính toán khác nhau.
- Trong implementation phổ biến, các local tasks và stolen tasks có chính sách lấy khác nhau để cải thiện locality và giảm cạnh tranh, nhưng **không nên viết logic phụ thuộc vào thứ tự xử lý FIFO/LIFO cụ thể**.
- Một pool với `parallelism = 4` không có nghĩa một task được chia thành đúng bốn nhánh.
- Task có thể chạy trên cùng worker đã fork; không cần tồn tại worker rảnh khác.
- Work-stealing không giải quyết data race, block I/O dài hoặc vòng phụ thuộc logic.

## 16. Ngưỡng dừng (threshold) quyết định độ mịn của task

Trong ví dụ mảng, điều kiện:

```java
if (end - start <= threshold) {
    return computeSequentially();
}
```

tạo giới hạn kích thước leaf. Đây là snippet minh họa.

**Threshold quá nhỏ:**

- Nhiều task object.
- Nhiều phép fork/join và quản lý queue.
- Overhead có thể lớn hơn thời gian tính toán.
- Hạn chế lợi ích cache/locality và tăng áp lực GC.

**Threshold quá lớn:**

- Ít nhánh được xử lý song song.
- Một worker có thể giữ đoạn dữ liệu rất lớn trong khi worker khác rảnh.
- Bỏ lỡ cơ hội cân bằng tải.

**Chọn thế nào?** Đo workload thực tế và chi phí xử lý mỗi phần tử. Một mảng vài chục phần tử không cần parallelism; một mảng hàng chục triệu phần tử với operation CPU đáng kể có thể đáng chia. Threshold 4 trong demo chỉ để **nhìn rõ cây chia**, không phải cấu hình được khuyên cho production.

Một kinh nghiệm là chọn đủ nhiều leaf để cân bằng worker nhưng mỗi leaf phải làm **đủ công việc hữu ích** nhằm bù overhead. Không có con số threshold chung cho mọi CPU/thuật toán.

## 17. Ví dụ Java 17+: đếm số lần `compute()` để nhìn chi phí chia

Lưu thành `ForkJoinTaskCountDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinTaskCountDemo {
    static final class CountingSum extends RecursiveTask<Long> {
        private final int start, end, threshold;
        private final AtomicInteger tasksSeen;

        CountingSum(int start, int end, int threshold,
                    AtomicInteger tasksSeen) {
            this.start = start;
            this.end = end;
            this.threshold = threshold;
            this.tasksSeen = tasksSeen;
        }

        @Override
        protected Long compute() {
            tasksSeen.incrementAndGet();

            if (end - start <= threshold) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += i + 1L;
                }
                return sum;
            }

            int mid = start + (end - start) / 2;
            CountingSum left = new CountingSum(
                    start, mid, threshold, tasksSeen);
            CountingSum right = new CountingSum(
                    mid, end, threshold, tasksSeen);

            left.fork();
            long r = right.compute();
            return left.join() + r;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(4);
        AtomicInteger seen = new AtomicInteger();

        try {
            long sum = pool.invoke(
                    new CountingSum(0, 16, 4, seen));
            System.out.println("Sum: " + sum);
            System.out.println("Compute invocations: " + seen.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinTaskCountDemo.java
java ForkJoinTaskCountDemo
```

Stdout chính xác:

```text
Sum: 136
Compute invocations: 7
```

Vì mảng logic có 16 phần tử và threshold 4, cây chia cố định gồm 1 root, 2 internal tasks, 4 leaf tasks. Mỗi object thực hiện `compute()` đúng một lần, nên bộ đếm atomic đạt 7, **không phụ thuộc task nào chạy trước**.

Đếm số task không phải benchmark throughput. Nếu đổi threshold thành 1, cây task sẽ lớn hơn; nhưng kết quả toán học vẫn bằng 136 khi thuật toán chính xác. Để tối ưu thật, cần đo elapsed time trên input đủ lớn sau warm-up hợp lý và kiểm soát CPU/load.

## 18. Chi phí dữ liệu và tính đúng của phép gộp

Để chia và combine an toàn, thường cần phép gộp có tính chất phù hợp:

- Tổng: `left + right`, chú ý overflow.
- Min/max: `Math.min(left, right)` hoặc `Math.max(...)`.
- Đếm: cộng số đếm.
- Ghép danh sách: cần quan tâm **thứ tự** và ownership.
- Các phép toán số thực: thay đổi thứ tự cộng có thể thay đổi rounding.

Ví dụ với `double`, phép cộng floating-point **không kết hợp chính xác** do sai số làm tròn:

```text
(a + b) + c  không nhất thiết ==  a + (b + c)
```

Vì vậy thuật toán Fork/Join tổng hợp số thực có thể cho kết quả bit khác vòng lặp tuần tự vì thứ tự combine khác. Nếu yêu cầu reproducibility chính xác, phải định nghĩa cây combine ổn định, kiểu số và chính sách sai số.

Với kết quả mutable (như `ArrayList`), mỗi leaf nên tạo **result riêng**, rồi parent gộp sau khi join. Tránh để nhiều task cùng `add` vào một `ArrayList` dùng chung mà không đồng bộ; có thể gây race và hỏng cấu trúc.

## 19. Dữ liệu input có cần immutable không?

Không bắt buộc mọi input phải immutable, nhưng cần có **quy tắc sở hữu rõ ràng**.

An toàn thường gặp:

1. Tạo xong một `int[]` trước khi submit root task.
2. Các subtask chỉ **đọc** mảng đó.
3. Không có thread khác sửa mảng khi computation diễn ra.
4. Chỉ đọc result sau khi root task hoàn tất.

Với `RecursiveAction` ghi vào array, task con phải sở hữu **những vùng index không chồng lấn**. Một thread ngoài cây task sửa cùng index trong lúc task chạy sẽ làm mất giả định.

`ForkJoinTask.join()`/completion và submission cung cấp các bảo đảm memory consistency cần thiết để công bố dữ liệu theo giao thức. Nhưng chúng **không** làm cho các collection thường `ArrayList`, `HashMap` hay object mutable dùng chung tự thread-safe nếu nhiều writer cạnh tranh.

Nếu thuật toán cần shared accumulator, thường tốt hơn để **mỗi task trả kết quả riêng rồi gộp** thay vì dùng một shared counter có contention cao.

## 20. `join()` không giải quyết vòng phụ thuộc

Một lỗi logic nghiêm trọng là tạo task phụ thuộc nhau theo chu trình:

```text
Task A cần join(Task B)
Task B cần join(Task A)
```

Không task nào có thể hoàn tất trước task còn lại. Dù pool có work-stealing, **thuật toán vẫn sai**.

Ví dụ anti-pattern ở mức logic:

```java
// Minh họa ý tưởng sai, không phải chương trình runnable.
ForkJoinTask<?> a = ...;
ForkJoinTask<?> b = ...;

// a đợi b, b lại đợi a -> vòng dependency.
```

Ở đoạn trên dấu `...` là ký pháp minh họa không hợp lệ nếu biên dịch; **không chạy**.

Một biến thể nguy hiểm là **giữ monitor khi join**:

```java
synchronized (lock) {
    child.fork();
    child.join(); // Nếu child cần lock, có thể deadlock.
}
```

Đây là snippet minh họa với `child` và `lock` đã định nghĩa ở nơi khác. Nếu child cần sở hữu `lock` để hoàn tất, parent đang giữ lock và chờ child: vòng đợi có thể không tự thoát.

**Nguyên tắc:** không chờ subtask có khả năng cần một tài nguyên/monitor mà parent đang giữ, và không tạo dependency cycle giữa các subtask.

## 21. Blocking I/O và `ForkJoinPool`

Fork/Join tối ưu chủ yếu cho nhiều task tính toán có thể chia nhỏ. Nếu mỗi task gọi socket read, JDBC, `Thread.sleep` dài hoặc `Future.get()` chờ công việc ở pool khác, worker có thể bị block, giảm số worker còn hoạt động.

Work-stealing không bảo đảm tạo thêm đủ worker để bù mọi blocking call. Một số tình huống có thể dùng `ForkJoinPool.ManagedBlocker` thông qua `ForkJoinPool.managedBlock(...)`, cho pool có cơ hội quản lý blocking phù hợp hơn, nhưng cần thiết kế một blocker đúng contract và **không áp dụng mù quáng**.

Khi workload chủ yếu là blocking I/O và không mang cấu trúc divide-and-conquer, thường hợp lý hơn nếu dùng `ExecutorService` hoặc một mô hình concurrency phù hợp thay vì ép mọi việc thành `RecursiveTask`.

**Không đánh đồng `join` chờ subtask trong Fork/Join với một external network wait.** Runtime hiểu cấu trúc task của chính pool tốt hơn so với một blocking operation tùy ý mà task thực hiện.

## 22. Lỗi trong `compute()` truyền thế nào?

Nếu task con ném unchecked exception hoặc `Error`, task có thể hoàn tất **bất thường**. Parent thực hiện `join()` hoặc root gọi `pool.invoke(...)` sẽ quan sát lỗi theo hợp đồng Fork/Join; không có kết quả số hợp lệ cho nhánh lỗi đó.

Ví dụ một task cố ý từ chối input âm.

Lưu thành `ForkJoinExceptionDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinExceptionDemo {
    static final class ValidateTask extends RecursiveTask<Integer> {
        private final int input;

        ValidateTask(int input) {
            this.input = input;
        }

        @Override
        protected Integer compute() {
            if (input < 0) {
                throw new IllegalArgumentException("negative input");
            }
            return input * 2;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            try {
                pool.invoke(new ValidateTask(-3));
            } catch (IllegalArgumentException e) {
                System.out.println("Rejected: " + e.getMessage());
            }
            System.out.println("Good result: "
                    + pool.invoke(new ValidateTask(5)));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinExceptionDemo.java
java ForkJoinExceptionDemo
```

Stdout chính xác:

```text
Rejected: negative input
Good result: 10
```

Task lỗi **không mặc nhiên làm toàn bộ pool shutdown**; sau đó pool vẫn có thể chạy task hợp lệ nếu còn ở trạng thái hoạt động. Nhưng nếu parent đã fork nhiều task rồi một task ném lỗi, các nhánh còn lại có thể đã tạo side effect. Không coi exception là rollback transaction đa task.

Nếu cần gộp lỗi của nhiều task, hãy định nghĩa policy xử lý exception và cancellation rõ; đừng chỉ catch rồi trả `0` và làm sai kết quả nghiệp vụ.

## 23. `join()` và `get()`: interruption, timeout, exception

`ForkJoinTask` implement `Future<V>`, vì thế có thể dùng những thao tác quen thuộc:

| Method | Hành vi khái quát |
| --- | --- |
| `join()` | Chờ task xong theo cơ chế Fork/Join, trả kết quả hoặc phát exception unchecked/cancellation |
| `get()` | Chờ completion theo contract `Future`, có `InterruptedException` và `ExecutionException` khi thích hợp |
| `get(timeout, unit)` | Chờ có thời hạn, có thể ném `TimeoutException` |
| `cancel(...)` | Thử cancel task; không đồng nghĩa worker đã ngừng ngay |
| `isDone()` | Task đã ở trạng thái hoàn tất, bao gồm bình thường/lỗi/hủy |
| `isCompletedNormally()` | Task hoàn tất bình thường |
| `isCompletedAbnormally()` | Task hoàn tất lỗi hoặc hủy, theo contract ForkJoinTask |

Nếu dùng timed get, **timeout chỉ giới hạn lần chờ của caller**, không tự hủy task đang chạy. Task có thể hoàn thành muộn và trả kết quả ở lần `get` khác. Nếu cần yêu cầu dừng, phải có cancellation policy riêng.

Một nuance quan trọng: `ForkJoinTask.cancel(boolean)` theo contract không sử dụng tham số `mayInterruptIfRunning` để điều khiển việc ngắt thực thi như một số future loại khác. Không suy từ `cancel(true)` rằng ForkJoinTask sẽ được interrupt trực tiếp.

Trong ứng dụng thật, tránh dùng `join()` để đợi I/O bên ngoài; nó dành cho **dependency giữa ForkJoinTasks** theo cây tính toán.

## 24. Quản lý cancellation trong một cây task

Một task gốc bị cancel không tự chứng minh rằng mọi subtask đã được tạo đều ngừng side effect hoặc cleanup. Hủy song song phức tạp hơn một cờ, vì nhiều nhánh có thể đã bắt đầu.

Muốn thiết kế cây tác vụ hủy hợp tác, cần:

- Một **cancellation token** (chẳng hạn `AtomicBoolean`) dùng chung cho các nhánh nếu phù hợp.
- Các **checkpoints** kiểm tra token trước khi chia thêm hoặc làm công việc tốn kém.
- Giới hạn số lượng task phát sinh sau khi đã yêu cầu hủy.
- Quy tắc xử lý các subtask đã fork nhưng chưa join (join/cancel/cleanup theo contract).
- Quản lý resource ownership để không bỏ sót file/connection/lock.
- Kết quả cuối phân biệt normal completion, partial work, failure và cancellation.

Ví dụ snippet:

```java
if (cancelled.get()) {
    return 0L; // Chỉ hợp lệ nếu contract coi partial result là được phép.
}
```

Đây là snippet minh họa; `cancelled` thuộc ứng dụng. **Không tự động trả 0 khi hủy nếu bên gọi có thể hiểu nó là tổng hợp lệ.** Trong nhiều API, nên báo trạng thái hủy hoặc exception để không tạo dữ liệu sai trông như thành công.

Và `Thread.interrupt()` không cưỡng ép mọi CPU-bound subtask dừng; code cần hợp tác kiểm tra signal.

## 25. `ForkJoinPool.commonPool()` và pool tự tạo

`ForkJoinPool.commonPool()` là pool chia sẻ được nhiều API/lớp code sử dụng. Các thao tác `ForkJoinTask.fork()` ở một số ngữ cảnh ngoài worker có thể liên quan tới common pool theo contract của ForkJoinTask.

Ưu điểm của common pool là không phải tạo thêm pool cho từng phép tính nhỏ. Nhược điểm:

- Các tác vụ không liên quan có thể **cạnh tranh worker và throughput**.
- Một ứng dụng có code blocking kém phù hợp có thể ảnh hưởng người dùng khác của pool.
- Vòng đời common pool **không được sở hữu bởi từng component**; không tự ý shutdown nó như pool riêng.
- Không thể dựa vào cấu hình parallelism mặc định là một số cố định trên mọi máy/JVM.
- Các chính sách bảo mật, giới hạn tài nguyên hoặc cấu hình runtime có thể thay đổi hành vi thực tế.

Nếu cần cô lập tài nguyên hoặc kiểm soát độ song song, tạo `new ForkJoinPool(parallelism)` và quản lý shutdown khi xong; nhưng một pool riêng cho **mỗi request** thường lãng phí tài nguyên.

Trong ví dụ bài này, mỗi chương trình tạo pool riêng để minh họa ownership rõ và tránh phụ thuộc contention của common pool.

## 26. Độ song song (parallelism) không đồng nghĩa số task

Ví dụ:

```java
ForkJoinPool pool = new ForkJoinPool(4);
```

Đây là snippet minh họa, không phải toàn bộ chương trình.

`4` là **mức độ song song mục tiêu**/cấu hình cho worker của pool, không phải lời hứa đúng bốn task đang chạy ở mọi thời điểm.

Một cây có 100 leaf tasks vẫn có thể được một nhóm worker nhỏ xử lý theo thời gian. Trái lại một task có thể thực thi hoàn toàn tuần tự nếu threshold quá lớn không tạo nhánh.

Các yếu tố ảnh hưởng throughput:

- Số lõi CPU thực và tải của những ứng dụng khác.
- Cost của từng leaf; task quá nhỏ gây overhead.
- Mức cân đối của cây chia.
- Số worker rảnh có thể steal việc.
- Chi phí memory bandwidth và cache misses.
- Shared locks/atomics gây contention.
- Thời gian blocking bên trong task.
- Chi phí combine kết quả và cấp phát object.

Thực hiện benchmark không chỉ với 1 input nhỏ; cần input thực tế, warm-up, nhiều lần đo, kiểm soát JVM/GC và không dùng logging trong inner loop.

## 27. Những sai lầm thường gặp

**1. "Gọi `compute()` tức là có thread mới."** Sai. `compute` là logic task; gọi trực tiếp là method call trên current thread.

**2. "`fork()` tương đương `Thread.start()`."** Sai. `fork` schedule `ForkJoinTask`, không tạo một thread mới cho mỗi subtask.

**3. "`fork()` bảo đảm chạy song song."** Sai. Pool có thể dùng cùng worker, hoặc task chưa có cơ hội được steal.

**4. "`join()` chỉ dùng để nối thread `Thread`."** Sai. `ForkJoinTask.join` đợi **task và kết quả**, khác `Thread.join` đợi một thread kết thúc.

**5. "Cứ fork cả hai nhánh rồi join ngay là tốt nhất."** Không mặc định. One-fork-one-compute có thể ít overhead và tránh chờ thừa.

**6. "Threshold càng nhỏ càng nhanh."** Sai. Nhiều subtask quá nhỏ tốn scheduling/object allocation.

**7. "Đã dùng Fork/Join là `ArrayList` chung thread-safe."** Sai. Shared mutable state cần đồng bộ/ownership riêng.

**8. "`join` sẽ cứu được mọi dependency deadlock."** Sai. Vòng phụ thuộc hoặc giữ monitor khi join có thể khiến không tiến triển.

**9. "Một task ném exception thì tất cả side effect task khác rollback."** Sai. Các subtask có thể đã ghi dữ liệu/tài nguyên bên ngoài.

**10. "`ForkJoinPool(4)` chắc chắn có bốn task đang chạy."** Sai. `parallelism` là cấu hình mức song song, không phải số task chạy thực tại từng thời điểm.

**11. "`join()` phải khai báo `throws InterruptedException`."** Sai. `join` không khai báo checked interruption; `get` của `Future` có thể làm điều đó.

**12. "`get(timeout)` timeout sẽ tự cancel task."** Sai. Đó chỉ là timeout lần chờ.

**13. "`cancel(true)` của ForkJoinTask luôn interrupt worker."** Sai. Tham số đó không có tác dụng tương đương trong contract của ForkJoinTask.

**14. "Fork/Join phù hợp nhất cho mọi blocking I/O."** Không. Nó ưu tiên tính toán chia để trị; blocking không quản lý có thể làm thiếu worker.

**15. "Task hoàn thành đúng nghĩa kết quả business luôn thành công."** Không. `isDone` có thể bao gồm exceptional completion/cancellation; phải kiểm tra trạng thái đúng.

**16. "Common pool có thể shutdown tùy ý bởi component."** Sai về ownership. Shared pool không thuộc về một task riêng.

**17. "Task có thể fork chính nó rồi join chính nó."** Sai về dependency: tạo vòng chờ trên cùng task là lỗi thiết kế.

**18. "Kết quả phép cộng `double` luôn giống thứ tự tuần tự."** Không bảo đảm do floating-point rounding khác theo cây combine.

## 28. Checklist review thuật toán Fork/Join

1. **Bài toán có chia được thành các nhánh độc lập không?** Nếu không, Fork/Join có thể làm code phức tạp hơn mà không tăng tốc.
2. **Base case đã thu nhỏ tới ngưỡng chắc chắn dừng chưa?** Nếu không, nguy cơ đệ quy vô hạn.
3. **Các khoảng `[start,end)` có phủ đủ dữ liệu và không chồng lấn không?** Kiểm tra số lẻ, mảng rỗng, size 1.
4. **Ngưỡng dừng được chọn theo chi phí xử lý hay chỉ đoán?** Tạo task quá nhỏ gây overhead.
5. **Một nhánh được fork, nhánh khác được compute tại chỗ khi phù hợp chưa?** Tránh join quá sớm.
6. **Mọi task đã fork cần thiết có được join hoặc được quản lý completion không?** Đừng để kết quả chưa xong bị bỏ qua.
7. **Phép gộp có đúng toán học không?** Kể cả overflow và tính không kết hợp của floating point.
8. **Input có immutable/safe-publication/ownership đúng không?** Chặn writer concurrent ngoài cây nếu không được đồng bộ.
9. **Có shared mutable accumulator không?** Cân nhắc local result rồi combine thay vì lock/atomic contention.
10. **Có callback hoặc I/O blocking trong `compute` không?** Nếu có, xem kiến trúc khác hoặc giao thức managed blocking đúng.
11. **Có dependency cycle hoặc chờ trong lúc giữ monitor không?** Đây là nguồn deadlock thực.
12. **Exception/cancellation có tạo partial side effect không?** Xác định cách báo failure và cleanup.
13. **Pool nào thực thi root/subtask?** Tránh pha trộn pool không rõ ownership.
14. **Có kiểm thử output độc lập lịch chạy không?** Dùng các ví dụ nhỏ với kết quả toán học biết trước.
15. **Có benchmark real workload không?** So sánh với vòng tuần tự, kiểm soát input/JIT/GC.
16. **Có đóng pool riêng sau khi dùng không?** `shutdown`/lifecycle phù hợp.
17. **Có tránh overfitting dựa vào `getStealCount` hoặc pool metric snapshot không?** Metric quan sát không phải correctness condition.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** `compute()` có tự tạo thread mới khi được gọi trực tiếp không?

**Không.** Đây là method do `RecursiveTask`/`RecursiveAction` override. Gọi trực tiếp chạy trên thread hiện tại; muốn quản lý task bằng pool, submit/invoke qua `ForkJoinPool` hoặc tổ chức fork/join đúng ngữ cảnh.

**Câu 2.** `fork()` có bảo đảm nhánh chạy ngay trên worker khác không?

**Không.** Nó lên lịch task để Fork/Join xử lý. Worker khác **có thể** steal, nhưng cùng worker cũng có thể thực thi task đó.

**Câu 3.** `join()` trả gì đối với `RecursiveTask<Long>`?

Khi task hoàn tất bình thường, nó trả kết quả `Long` của task đó. Khi task thất bại/cancel, caller phải xử lý exception tương ứng.

**Câu 4.** Vì sao thường viết `left.fork(); right.compute(); left.join();`?

Vì current worker làm việc có ích trên nhánh right trong lúc left có thể chạy bởi worker khác, thay vì join left ngay rồi để right chưa được tính.

**Câu 5.** Dữ liệu 16 phần tử chia đôi đến threshold 4 tạo bao nhiêu `SumTask` trong ví dụ cân đối?

**7**: 1 root, 2 internal, 4 leaf tasks. Số task không đồng nghĩa số thread.

**Câu 6.** `RecursiveAction` khác `RecursiveTask<V>` ở đâu?

`RecursiveAction.compute` trả `void` và phù hợp tác vụ chỉ tạo side effect được kiểm soát; `RecursiveTask<V>.compute` trả một kết quả `V` để parent gộp.

**Câu 7.** Một leaf ghi cùng index với leaf khác trong `int[]`, có an toàn chỉ vì chúng cùng ForkJoinPool không?

**Không.** Ghi vào vùng chồng lấn có thể tạo race. Cần phân hoạch ownership hoặc synchronization phù hợp.

**Câu 8.** `ForkJoinTask.join()` và `Future.get()` có cùng hợp đồng interruption không?

**Không.** `join` không khai báo `InterruptedException`; `get` có thể chờ interruptible theo contract `Future` và có phiên bản timeout.

**Câu 9.** `pool.invoke(root)` khác `root.fork()` ở điểm nào?

`pool.invoke` đưa task gốc vào **pool đã chọn** và đợi result. `fork` lên lịch task theo ngữ cảnh Fork/Join của caller và không chờ completion tại dòng gọi.

**Câu 10.** Tại sao task con ném exception không làm rollback task khác?

Vì Fork/Join là cơ chế scheduling/completion trong bộ nhớ, không phải transaction manager. Những side effect khác có thể đã xảy ra.

**Câu 11.** Task CPU-bound làm 10 phép cộng có cần chia thành 10 `RecursiveTask` không?

Thông thường không. Overhead tạo/schedule task có thể lớn hơn tính toán; chọn threshold đủ lớn hoặc làm tuần tự.

**Câu 12.** Khi nào nên tránh Fork/Join?

Khi công việc không chia độc lập được, phụ thuộc chéo nhiều, chủ yếu là blocking I/O không quản lý, hoặc cần durable/distributed execution semantics mà ForkJoinPool không cung cấp.

## 30. Tổng kết

- **`compute()`** là logic giải task; nó tự xác định base case, chia nhánh và combine.
- **`fork()`** lên lịch một subtask để có thể xử lý bất đồng bộ trong Fork/Join; không tự tạo một thread riêng cho mỗi task và không bảo đảm chạy song song.
- **`join()`** đợi task đã fork hoàn thành và lấy kết quả, với semantics exception/cancellation của `ForkJoinTask`; không phải `Thread.join()`.
- Với divide-and-conquer, mẫu **fork một nhánh → compute nhánh còn lại → join nhánh đã fork → combine** giúp worker tiếp tục làm việc hữu ích, giảm một số overhead.
- **`RecursiveTask<V>`** dùng khi cần kết quả; **`RecursiveAction`** dùng cho hành động không trả value. `invokeAll` là helper thực thi/chờ nhóm subtask.
- **Work-stealing** cân bằng các task giữa workers; số task có thể nhiều hơn số thread, và thứ tự thực thi không được dùng làm giả định correctness.
- **Threshold, ownership dữ liệu và phép combine** quyết định hiệu năng/tính đúng. Tạo task quá nhỏ, viết vào shared collection thường hoặc giữ monitor khi join đều có thể gây lỗi.
- **Exception/cancellation/timeout** có hợp đồng riêng; Fork/Join không tự rollback side effect, không phù hợp với mọi blocking I/O và không bảo đảm hard real-time.
- Tạo **pool riêng có ownership và shutdown rõ** khi cần cô lập nguồn lực; không tự shutdown shared common pool.

Trong mỗi thuật toán Fork/Join, hãy tự hỏi: **"Phần nào có thể thực thi song song một cách độc lập, phần nào tính trực tiếp, và điều kiện nào bảo đảm mọi nhánh đã xong trước khi tôi gộp kết quả?"**. Trả lời được ba câu hỏi ấy sẽ giúp dùng `compute()`, `fork()` và `join()` đúng hơn nhiều so với chỉ dựa trên tên method.