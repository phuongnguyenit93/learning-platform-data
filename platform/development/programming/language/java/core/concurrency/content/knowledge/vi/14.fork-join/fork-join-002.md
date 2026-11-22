# ForkJoinPool và cơ chế work stealing trong Java

`ForkJoinPool` là một executor chuyên xử lý những bài toán có thể **chia thành các tác vụ con (fork)** rồi **kết hợp kết quả (join)**. Thay vì chỉ có một hàng đợi công việc tập trung và mỗi thread nhận một task hoàn chỉnh, các worker trong pool có thể tạo thêm tác vụ con khi đang xử lý một bài toán lớn. **Work stealing** giúp worker đã rảnh lấy một phần công việc còn chờ ở worker khác, nhờ vậy những nhánh đệ quy lớn/nhỏ không đều có cơ hội được cân bằng tải tốt hơn.

Đây không phải phép màu khiến mọi Java program chạy nhanh hơn. `ForkJoinPool` hiệu quả nhất khi công việc chia được thành nhiều đơn vị **đủ lớn để bù chi phí fork/join**, tương đối độc lập, ít blocking I/O và có đường hợp nhất kết quả rõ ràng. Nếu tác vụ chủ yếu gọi mạng, chờ khóa hoặc cần xử lý theo thứ tự chặt chẽ, cách chia task và executor khác có thể hợp lý hơn.

Bài Knowledge này thuộc **Fork/Join của Java Concurrency nói chung**. Chúng ta sẽ nắm mô hình chia–trị, cơ chế worker deque và đánh cắp việc, các API `RecursiveTask`/`RecursiveAction`, ngưỡng chia, common pool, blocking, exception, cancellation, quan sát runtime và ví dụ **Java 17+**. Các tích hợp riêng của Spring thuộc một chương khác.

## 1. Vì sao cần hiểu lịch thực thi của pool?

`ForkJoinPool` điều phối các `ForkJoinTask` trên worker và hỗ trợ work stealing để cân bằng những nhánh lớn/nhỏ không đều. Mỗi task là một đơn vị việc, không phải một thread; thuật toán vẫn phải có base case, phép chia và cách kết hợp đúng.

Với bài toán tổng mảng, có thể fork một nửa, compute nửa còn lại rồi join kết quả. Bài này đi sâu **deque riêng của worker, chính sách lấy local task và steal task**; work stealing không cam kết thứ tự thực thi hoặc tăng tốc trong mọi workload.
## 2. Kiến trúc cơ bản của ForkJoinPool

`ForkJoinPool` nằm trong `java.util.concurrent`, kế thừa `AbstractExecutorService` và triển khai `ExecutorService`. Nó có thể nhận task từ thread bên ngoài pool qua `invoke`, `execute` hoặc `submit`, đồng thời tối ưu các task tạo ra nhiều nhánh con từ những worker đang chạy.

Những thành phần chính:

| Thành phần | Chức năng |
| --- | --- |
| **ForkJoinPool** | Quản lý worker, lịch thực thi, mức parallelism mục tiêu, lifecycle và metrics. |
| **ForkJoinWorkerThread** | Worker chạy nhiều `ForkJoinTask`; có khả năng hỗ trợ xử lý task đang chờ của worker khác. |
| **Work deque / queue nội bộ** | Giữ những task có thể chạy của worker, cho phép lấy local và steal theo chính sách triển khai. |
| **ForkJoinTask<V>** | Task nhẹ cho fork/join, có API `fork()`, `join()`, `invoke()`, completion status. |
| **RecursiveTask<V>** | Base class task đệ quy có giá trị trả về từ `compute()`. |
| **RecursiveAction** | Base class task đệ quy không trả value (`compute()` trả `void`). |
| **CountedCompleter<V>** | Biến thể dùng completion count, phù hợp một số thuật toán phân rã không tổ chức dưới cây join đơn giản. |
| **Work stealing** | Worker rảnh tìm task còn chờ từ worker khác, giảm mất cân bằng giữa các nhánh. |

Một `ForkJoinPool` không phải một “thread cho mỗi task”. Nhiều task nhỏ được thực hiện trên một số worker có giới hạn parallelism mục tiêu. Task mới không nhất thiết tạo thread mới.

### 2.1 Work queue của executor thường và work deque

Trong một fixed thread pool kiểu truyền thống, mô hình trực quan thường là:

~~~text
submission queue: [task A] [task B] [task C]
                   |        |        |
                 worker 1 worker 2 worker 3
~~~

Còn với Fork/Join, trong khi worker thực hiện task A, nó có thể tạo A1, A2, A3; worker khác nếu đã rảnh có thể lấy một task từ những nhánh chưa chạy:

~~~text
Worker 1: đang xử lý A
          local deque: [A1] [A2] [A3]
                            |
Worker 2: không có task     +-- steal một task đang chờ
Worker 3: có thể xử lý nhánh riêng của mình
~~~

Đây là sơ đồ khái niệm, **không phải cam kết** các queue luôn chứa đúng thứ tự này. Cấu trúc và tối ưu thực tế của JVM có thể thay đổi theo phiên bản JDK.

## 3. Work stealing vận hành như thế nào?

Trong mô hình Fork/Join phổ biến, mỗi worker thường ưu tiên xử lý **task của chính mình**; khi không còn việc phù hợp, nó thử lấy task từ các queue khác trong pool.

Trực giác về hai đầu deque:

~~~text
                   deque của Worker A
              đầu cũ             đầu mới
             [T1] [T2] [T3] [T4]
               ^              ^
               |              |
       worker khác steal    Worker A lấy local
       từ phía đối diện     ở phía đang làm việc
~~~

Trong chế độ fork/join mặc định, **local work thường thiên về LIFO (last-in, first-out)**, còn **steal thường lấy từ phía đối diện**, gần các task cũ hơn. Ý tưởng này hỗ trợ worker vừa fork một nhánh có thể tiếp tục xử lý những công việc gần dữ liệu hiện tại, trong khi worker rảnh lấy một nhánh khác thường có phạm vi lớn để khai thác song song.

Tuy nhiên đừng xây chương trình dựa vào “task T4 chắc chắn chạy trước T1”:

- Scheduler, trạng thái worker và external submissions làm thứ tự thay đổi.
- Pool có các queue dành cho submission ngoài worker, không chỉ một deque cho mỗi worker.
- Một số đường trợ giúp khi `join()` có thể khiến worker thực hiện task mà nó đang đợi hoặc task liên quan.
- Phiên bản JDK, mức contention và tùy chọn `asyncMode` có thể thay đổi chi tiết scheduling.
- `getStealCount()` là chỉ số giám sát **ước lượng**, không phải counter đảm bảo phản ánh chính xác từng interleaving trong mọi thời điểm.

### 3.1 Vì sao steal từ đầu đối diện hữu ích?

Nếu owner vừa tạo một chuỗi các task gần nhau, nó có thể xử lý local một cách hiệu quả mà ít tranh với worker khác. Worker rảnh lấy task từ phía đối diện, thường tương ứng một nhánh được tạo sớm và có nhiều việc còn lại. Việc các worker **không cùng tranh một đầu deque** giảm chi phí phối hợp trong nhiều workload.

Đây là mục tiêu thiết kế, không phải bảo đảm tải luôn cân bằng hoàn hảo. Nếu thuật toán tạo một task rất nặng và hàng nghìn task gần như không có việc, steal vẫn không thể tự chia task nặng duy nhất thành nhiều phần nếu code `compute()` không chia tiếp.

### 3.2 Work stealing không đồng nghĩa preemption

Worker B “steal” một **task chưa được thực thi hoặc đang chờ trong cấu trúc lập lịch**, không có nghĩa nó cắt ngang instruction của task đang chạy trên Worker A để lấy nửa stack. Nếu một leaf task đang chạy CPU lâu và không fork thêm, các worker rảnh không thể chia nhỏ leaf đó một cách tự động.

Do đó thiết kế threshold và cách chia bài toán còn quan trọng hơn số thread được tạo.

## 4. RecursiveTask và RecursiveAction: chọn đúng kiểu

| Kiểu | Phương thức cài đặt | Dùng khi |
| --- | --- | --- |
| `RecursiveTask<V>` | `protected V compute()` | Cần trả kết quả từ task và kết hợp chúng, như tổng, min/max, tìm kiếm, thống kê. |
| `RecursiveAction` | `protected void compute()` | Thực hiện thao tác không trả kết quả, như biến đổi các đoạn **không chồng lấn** của mảng. |
| `CountedCompleter<V>` | `compute()` cùng protocol pending count/completion | Đồ thị completion/processing không khớp việc join từng nhánh trực tiếp; cần hiểu lifecycle phức tạp hơn. |

Tất cả là các dạng `ForkJoinTask`. Bạn có thể dùng `fork()` để schedule một task con và `join()` để lấy kết quả. Tùy bài toán, task con có thể gọi `compute()` trực tiếp trên một nhánh khác để giảm số task fork.

Mẫu phổ biến cho `RecursiveTask<Long>`:

~~~java
if (rangeSmallEnough) {
    return sequentialCompute();
}

Task left = new Task(start, mid);
Task right = new Task(mid, end);

left.fork();              // Để nhánh trái có thể chạy bất đồng bộ.
long rightResult = right.compute();  // Nhánh phải chạy trực tiếp.
long leftResult = left.join();        // Lấy nhánh trái khi cần.
return leftResult + rightResult;
~~~

Đây là **mã minh họa giả định**, cần định nghĩa `Task`, `rangeSmallEnough`, `sequentialCompute()`, kiểu dữ liệu và xử lý overflow theo bài toán. Dùng một nhánh `fork` và một nhánh `compute` thường giảm việc đưa quá nhiều task vào queue so với việc fork cả hai rồi lập tức đợi.

## 5. Ví dụ Java 17+: tính tổng với RecursiveTask

Tạo tệp `ForkJoinSumDemo.java`:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public final class ForkJoinSumDemo {
    private static final class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2_048;
        private final long[] numbers;
        private final int start;
        private final int end;

        SumTask(long[] numbers, int start, int end) {
            this.numbers = numbers;
            this.start = start;
            this.end = end;
        }

        @Override
        protected Long compute() {
            if (end - start <= THRESHOLD) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += numbers[i];
                }
                return sum;
            }

            int mid = start + (end - start) / 2;
            SumTask left = new SumTask(numbers, start, mid);
            SumTask right = new SumTask(numbers, mid, end);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        long[] data = new long[100_000];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1L;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long sum = pool.invoke(
                    new SumTask(data, 0, data.length));
            System.out.println("Sum: " + sum);
            System.out.println("Expected: 5000050000");
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
~~~

Stdout khi không có external interruption:

~~~text
Sum: 5000050000
Expected: 5000050000
~~~

### 5.1 Giải thích từng phần

- Root task quản lý khoảng `[0, 100000)` và trả về `Long`.
- Các khoảng lớn hơn `2048` phần tử tiếp tục chia tại midpoint; khoảng nhỏ được tính tuần tự trong leaf.
- `left.fork()` cho phép nhánh trái được worker hiện tại hoặc worker khác xử lý.
- `right.compute()` làm nhánh phải ngay trong thread hiện tại, không cần fork thêm một task chỉ để làm việc ấy.
- `left.join()` bảo đảm đã nhận kết quả nhánh trái trước khi cộng hai tổng. Có thể đã xong sẵn hoặc cần chờ/hỗ trợ công việc.
- Dữ liệu là mảng chỉ đọc sau khi submit; mỗi leaf đọc một khoảng riêng. Không có shared mutable accumulator cần `synchronized`.
- Tổng từ 1 đến 100000 là `100000 * 100001 / 2 = 5000050000`; dùng `long` để tránh overflow của `int`.
- Pool được tạo riêng với parallelism mục tiêu 4, rồi shutdown và chờ kết thúc trong `finally`. Chương trình không đòi chính xác 4 worker phải thực sự chạy cùng lúc.

**Chú ý:** `THRESHOLD=2048` là giá trị minh họa, **không phải công thức tối ưu** cho mọi CPU/dữ liệu. Với một mảng 100000 phần tử, vòng lặp tuần tự có thể còn nhanh hơn fork/join do chi phí overhead. Bài tập này chứng minh **đúng mô hình**, không quảng cáo tốc độ cụ thể.

### 5.2 Bảo vệ dữ liệu đầu vào

`numbers` là một reference đến mảng mutable. Việc truyền reference vào task không tự đóng băng mảng. Ví dụ chỉ an toàn vì main **không sửa data** trong lúc `pool.invoke` chạy. Nếu thread khác sửa phần tử đồng thời, kết quả có thể không đại diện một snapshot nhất quán. Có thể copy input trước khi submit hoặc dùng ownership/synchronization phù hợp.

## 6. Vì sao fork một nhánh, compute nhánh kia, join nhánh đã fork?

Một cách viết lãng phí là:

~~~java
left.fork();
right.fork();
return left.join() + right.join();
~~~

Đây là mảnh code minh họa. Nó có thể đúng về mặt kết quả nếu các task độc lập, nhưng tăng số lần schedule cho cả hai nhánh rồi lập tức chờ, đôi khi gây overhead không cần thiết.

Mẫu phổ biến:

~~~java
left.fork();
long rightValue = right.compute();
return left.join() + rightValue;
~~~

Nó tận dụng thread hiện tại cho một nhánh trong khi nhánh kia có thể bị steal. Tuy nhiên đây là **heuristic**, không phải quy luật hiệu năng tuyệt đối; cấu trúc cây và dữ liệu có thể làm lựa chọn fork nhánh nào quan trọng. Với phân rã không đều, nên đưa nhánh có đủ việc vào cơ hội chạy song song và tránh tạo quá nhiều task cực nhỏ.

### 6.1 Không gọi fork rồi join tức thì nếu không có việc song song

~~~java
left.fork();
return left.join(); // Nếu không có công việc độc lập khác, có thể lãng phí.
~~~

Mảnh trên không thể hiện nhiều cơ hội song song cho thread hiện tại. Tối ưu chỉ có ý nghĩa khi trong thời gian left đang chạy, worker hiện tại có **công việc khác có thể làm** hoặc có worker khác sẵn sàng lấy task. Với cây fork/join, dùng `compute` trực tiếp cho một nhánh thường phù hợp.

### 6.2 Task tree phải kết thúc

Một lỗi phổ biến là chia không giảm kích thước:

~~~java
if (size > THRESHOLD) {
    // Sinh task mới với cùng start/end.
}
~~~

Đây là mã giả lỗi. Mỗi lần split phải giảm miền vấn đề, và có leaf/base case chắc chắn. Nếu không, có thể đệ quy vô hạn, `StackOverflowError` hoặc tạo vô số task và hết bộ nhớ.

## 7. RecursiveAction: xử lý các vùng dữ liệu độc lập

Nếu không cần trả value, `RecursiveAction` thích hợp. Ví dụ tăng mỗi phần tử của mảng đúng một lần. Các leaf chỉ thao tác trên các đoạn **không giao nhau**, nên không cần atomic increment cho từng phần tử.

Tạo `ForkJoinActionDemo.java`:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

public final class ForkJoinActionDemo {
    private static final class IncrementTask extends RecursiveAction {
        private static final int THRESHOLD = 512;
        private final int[] numbers;
        private final int start;
        private final int end;

        IncrementTask(int[] numbers, int start, int end) {
            this.numbers = numbers;
            this.start = start;
            this.end = end;
        }

        @Override
        protected void compute() {
            if (end - start <= THRESHOLD) {
                for (int i = start; i < end; i++) {
                    numbers[i]++;
                }
                return;
            }

            int mid = start + (end - start) / 2;
            IncrementTask left =
                    new IncrementTask(numbers, start, mid);
            IncrementTask right =
                    new IncrementTask(numbers, mid, end);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        int[] values = new int[10_000];
        ForkJoinPool pool = new ForkJoinPool(3);
        try {
            pool.invoke(new IncrementTask(values, 0, values.length));
            int sum = 0;
            boolean allOnes = true;
            for (int value : values) {
                sum += value;
                allOnes &= value == 1;
            }

            System.out.println("Sum: " + sum);
            System.out.println("All ones: " + allOnes);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ForkJoinActionDemo.java
java ForkJoinActionDemo
~~~

Stdout:

~~~text
Sum: 10000
All ones: true
~~~

**Phân tích:** hai subtask luôn quản lý những đoạn half-open `[start, mid)` và `[mid, end)` không trùng nhau. Mỗi phần tử chỉ có một leaf ghi, nên không có lost update do hai worker cùng sửa một index. Sau `pool.invoke`, toàn bộ root computation hoàn tất và main có thể kiểm tra mảng theo contract fork/join.

Nếu đổi bài toán sang “mọi task tăng **cùng một biến** globalCount++” thì sẽ tạo data race/lost update; phải dùng reduction, `LongAdder` theo contract metrics, hoặc primitive đồng bộ phù hợp. `ForkJoinPool` tự nó **không biến shared mutable state thành thread-safe**.

## 8. Work stealing cân bằng nhánh không đều ra sao?

Một cây công việc thực tế thường không cân đối hoàn hảo. Ví dụ:

~~~text
                        Root
                      /      \
              nhánh nhỏ      nhánh lớn
                 |            /      \
               10 ms        60 ms    70 ms
~~~

Các con số chỉ mô phỏng, không phải số đo runtime. Nếu một worker giữ cả nhánh lớn trong khi worker khác đã hoàn thành nhánh nhỏ, công suất CPU có thể bị bỏ trống. Với phân rã tiếp và work stealing, worker rảnh có thể lấy task chưa chạy từ worker bận.

Điều cần hiểu:

1. Steal xảy ra với **task có thể chuyển giao**, không “cắt đôi” một instruction đang chạy.
2. Cân bằng tốt phụ thuộc tác vụ lớn còn có thể chia nhỏ hay không.
3. Nếu task quá nhỏ, overhead fork/steal có thể lớn hơn công việc leaf.
4. Nếu task cần truy cập chung một lock, số worker tăng không mang lại throughput tỷ lệ thuận.
5. Nếu một leaf cần I/O chậm, work stealing không tự bảo đảm có worker thay thế khi blocking unmanaged.

Một việc quan trọng là **tránh kỳ vọng mọi worker luôn bận 100%**. Trong các cây có dependency, giai đoạn combine hoặc workload nhỏ có thể làm worker tạm rảnh là bình thường.

## 9. Grain size và threshold: vì sao không fork cho từng phần tử?

Có chi phí cho mỗi lần tạo/schedule/task metadata, join, phối hợp worker và cache effects. Nếu cứ chia đến mỗi phần tử:

~~~text
N phần tử -> gần 2N task tree nodes
mỗi leaf chỉ làm một phép cộng
overhead có thể lớn hơn phép toán thật
~~~

Đây là mô hình minh họa. Trong thực tế, số task phụ thuộc cấu trúc cây, cách code fork và việc thực thi nhánh trực tiếp.

Một **threshold** quyết định khi nào xử lý tuần tự. Cách chọn:

- Đủ lớn để leaf có lượng công việc hữu ích đáng kể.
- Đủ nhỏ để sinh ra nhiều leaf hơn số worker, cho phép cân bằng tải.
- Phù hợp độ khó của mỗi phần tử: tính checksum phức tạp có thể dùng chunk nhỏ hơn phép cộng integer đơn giản.
- Phù hợp layout dữ liệu/cache, độ lớn array và chi phí tạo object task.
- Dựa trên đo đạc, không “tối ưu bằng cảm giác”.

Có thể benchmark `THRESHOLD` lần lượt 256, 1024, 4096, 16384 với **cùng dữ liệu, JDK, tải**, xem median/p95, throughput và allocation. Không kết luận chỉ dựa vào một lần chạy `System.nanoTime` vì JIT warmup, GC, CPU scheduling và noise.

### 9.1 Tính toán work và span

Trong mô hình thuật toán song song:

- **Work T1**: lượng công việc nếu thực hiện tuần tự.
- **Span T∞**: độ dài đường phụ thuộc dài nhất (critical path), dù có vô hạn worker.
- Với `P` worker, thời gian thực còn phụ thuộc scheduling overhead, contention và memory bandwidth; không thể chỉ lấy `T1/P`.

Một cây chia đôi cân đối cho phép giảm span của nhiều bài toán reduction, nhưng nếu phần combine là một bước tuần tự rất nặng hoặc dữ liệu nằm trên một memory bottleneck, tăng worker cũng không tạo speedup tương ứng.

Đừng đồng nhất số core với tốc độ: mức parallelism cao hơn không loại bỏ chi phí memory bandwidth hoặc tính chất tuần tự không thể chia.

## 10. Parallelism, số worker và commonPool

### 10.1 Parallelism không phải số thread luôn thực thi

~~~java
ForkJoinPool pool = new ForkJoinPool(4);
System.out.println(pool.getParallelism()); // 4
~~~

Đây là mảnh code minh họa, nên đặt trong context quản lý `shutdown()` phù hợp. `getParallelism()` trả **target parallelism** được cấu hình, không chứng minh luôn có bốn worker đang thực hiện code. `getPoolSize()` có thể khác mức parallelism mục tiêu, chẳng hạn khi pool quản lý việc blocking.

Những số liệu như `getActiveThreadCount()`, `getRunningThreadCount()` và `getQueuedTaskCount()` là ảnh chụp/ước lượng trạng thái tại thời điểm quan sát, không dùng để assert invariant của nghiệp vụ.

### 10.2 ForkJoinPool.commonPool()

~~~java
ForkJoinPool shared = ForkJoinPool.commonPool();
~~~

`commonPool()` là pool dùng chung ở cấp JVM. Nhiều thành phần có thể sử dụng nó, trong đó có `ForkJoinTask` không được submit vào custom pool; các API như `CompletableFuture.supplyAsync` không truyền executor thường sử dụng common pool theo điều kiện của API/JDK.

Các lưu ý:

- **Không tự shutdown commonPool** khi một module kết thúc; đây là tài nguyên chia sẻ và shutdown thông thường không có tác dụng dừng common pool theo contract API.
- Một module gửi task CPU nặng hoặc blocking vào common pool có thể ảnh hưởng độ trễ module khác.
- Các cấu hình như `java.util.concurrent.ForkJoinPool.common.parallelism` có thể ảnh hưởng pool; tránh phụ thuộc giá trị ngầm định khi ứng dụng cần cô lập tài nguyên.
- Kết quả có thể khác khi chạy trên máy ít core, container giới hạn CPU hoặc JVM options khác.
- Tạo **custom pool** khi cần isolation, target parallelism rõ hoặc lifecycle riêng.

Trong JDK 17, `ForkJoinPool.commonPool()` thường phù hợp các tác vụ chia–trị CPU-bound độc lập, nhưng việc dùng chung có thể khó dự đoán khi một hệ thống lớn có nhiều thư viện cùng submit.

## 11. Ví dụ Java 17+: submit task từ thread bên ngoài pool

`ForkJoinPool` không chỉ chạy `RecursiveTask`. Nó cũng triển khai `ExecutorService` và có thể nhận `Callable` thông thường. Tạo `ForkJoinSubmitDemo.java`:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ForkJoinSubmitDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            Future<Integer> answer = pool.submit(() -> 6 * 7);
            System.out.println("Answer: " + answer.get());
            System.out.println("Target parallelism: "
                    + pool.getParallelism());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ForkJoinSubmitDemo.java
java ForkJoinSubmitDemo
~~~

Stdout:

~~~text
Answer: 42
Target parallelism: 2
~~~

**Phân tích:** main không phải một `ForkJoinWorkerThread`, nhưng vẫn submit task vào pool. `Future.get()` đợi kết quả và có checked exception theo `Future` API, khác `ForkJoinTask.join()`. Ví dụ không nhằm chứng minh work stealing đã diễn ra; một `Callable` nhỏ có thể được một worker xử lý trọn vẹn, chẳng có task nào để steal.

Khi mục tiêu đơn giản là thực thi nhiều `Runnable`/`Callable` độc lập, `ThreadPoolExecutor` hoặc `Executors.newFixedThreadPool` cũng có thể phù hợp. Work stealing có giá trị đặc biệt khi workload tạo các **nhánh fork/join động** hoặc các task nhỏ có khả năng phân phối giữa workers.

## 12. fork(), join(), invoke(), get() và invokeAll()

Những API nghe tương tự nhưng có khác biệt:

| API | Vai trò |
| --- | --- |
| `ForkJoinTask.fork()` | Schedule task để thực thi bất đồng bộ trong pool liên quan/current task hoặc common pool theo hợp đồng. Trả chính task. |
| `ForkJoinTask.join()` | Lấy kết quả khi task hoàn tất; nếu bất thường, truyền `RuntimeException`/`Error` theo cơ chế task thay vì checked `ExecutionException`. |
| `ForkJoinTask.invoke()` | Thực hiện task này và chờ kết quả; là một tiện ích cho root/subtask theo contract. |
| `ForkJoinPool.invoke(task)` | Entry point phổ biến từ main/non-worker: gửi root `ForkJoinTask` vào pool và đợi kết quả. |
| `ForkJoinTask.invokeAll(left, right)` | Fork/join một nhóm task con và bảo đảm hoàn tất hoặc báo abnormal completion theo contract. |
| `ForkJoinTask.get()` | Phù hợp `Future` API: có checked `InterruptedException`/`ExecutionException`. |
| `Thread.join()` | Chờ **lifecycle của một Java Thread**, không trả giá trị `ForkJoinTask`. |

`ForkJoinTask.join()` không giống `Thread.join()`: một bên lấy result của task, một bên chỉ đợi thread kết thúc. Đặc biệt `ForkJoinTask.join()` không ném checked `InterruptedException` theo đường chờ bình thường; do vậy nếu ứng dụng cần policy cancellation/deadline, phải chọn API và thiết kế lifecycle rõ hơn việc gọi join vô thời hạn.

`get()` không bảo đảm task đã bắt đầu nếu bạn chỉ tạo một `RecursiveTask` rồi chưa submit/fork/invoke. Tạo object task chưa phải thực thi.

### 12.1 Task không được fork nhiều lần tùy tiện

Một `ForkJoinTask` thường có lifecycle “new → scheduled/executing → completed”. Không nên submit/fork **cùng một instance còn đang chạy** nhiều lần. Nếu muốn thực hiện lại cùng logic, tạo một task instance mới với input tương ứng.

Việc reinitialize task đã completed là một khả năng cấp thấp có quy tắc riêng; đa số ứng dụng không cần và không nên dùng để “reset” ngẫu nhiên một task.

## 13. Java Memory Model và tính đúng đắn khi fork/join

`ForkJoinPool` quản lý scheduling, nhưng **không biến dữ liệu chia sẻ thành bất biến hoặc thread-safe**. Hãy phân biệt:

- **Task ownership:** mỗi task sở hữu một phạm vi input/output cụ thể.
- **Publication:** caller chuẩn bị input trước khi submit/invoke; cần tuân thủ memory-consistency effects của executor/task.
- **Completion:** caller chỉ đọc output sau khi task con hoàn tất qua `join()`, `invoke()` hoặc hợp đồng completion tương ứng.
- **Shared state:** nếu nhiều task viết cùng collection/counter mà không có phối hợp, có thể có race bất kể `fork()/join()` được gọi.

Trong `ForkJoinSumDemo`, tất cả leaf **chỉ đọc** mảng nên không tranh write; partial sum trả về như immutable `Long` được join/reduce. Trong `ForkJoinActionDemo`, leaf viết những vùng không giao nhau và main đọc sau completion. Đây là những thiết kế dễ chứng minh đúng.

### 13.1 Tránh một accumulator mutable chung

Mẫu lỗi:

~~~java
static long total;

void computeLeaf(long value) {
    total += value; // Có thể lost update khi các leaf chạy đồng thời.
}
~~~

Đây là mảnh lỗi minh họa. `total += value` là read-modify-write nhiều bước; nhiều worker có thể ghi đè cập nhật của nhau.

Các phương án đúng:

1. Mỗi `RecursiveTask<Long>` trả một partial sum, parent dùng `join()` rồi cộng.
2. Nếu thật sự là metric độc lập và chỉ cần tổng gần đúng khi đang cập nhật, chọn primitive atomic/adder phù hợp; không dùng thay cho invariant nhiều bước.
3. Nếu nhiều field liên quan transaction, dùng một giao thức synchronization/immutable aggregate có ranh giới commit chung.

**Reduction bằng kết quả trả về thường là cách tự nhiên nhất** cho Fork/Join vì tránh cache contention ở một biến toàn cục.

## 14. Blocking I/O: điểm yếu phải thiết kế riêng

Fork/Join chủ yếu tối ưu cho task tính toán ngắn có thể fork/join. Khi một worker chạy:

~~~java
String content = remoteService.fetch(); // Có thể đợi mạng rất lâu.
~~~

Đây là mảnh minh họa; API remote giả định. Nếu worker block trong I/O hoặc chờ lock/condition **không được pool quản lý**, pool có thể thiếu worker hoạt động để phục vụ các task còn lại. Javadoc Java 17 nêu rõ pool có khả năng điều chỉnh khi worker chờ join hoặc managed synchronization, nhưng **không bảo đảm bù thread khi gặp blocked I/O/unmanaged synchronization**.

### 14.1 Hướng thiết kế

- Ưu tiên dành ForkJoinPool cho **CPU-bound divide-and-conquer**; với nhiều request blocking I/O, xét executor phù hợp với số kết nối, quota và timeout.
- Không giữ monitor trong lúc block trên remote I/O hay chờ `Future.get()` không rõ deadline.
- Nếu bắt buộc block trên một primitive chưa được pool biết, `ForkJoinPool.managedBlock(ManagedBlocker)` cho phép pool **có cơ hội** bù worker để giữ parallelism; không hứa tạo thread không giới hạn.
- Chọn timeout/cancellation và resource ownership rõ ràng; `managedBlock` không tự cung cấp timeout hoặc giải quyết deadlock.
- Nếu task dùng chung pool với nhiều subsystem khác, blocking kéo dài có thể ảnh hưởng workload không liên quan.

### 14.2 ManagedBlocker minh họa

Mảnh method Java sau mô tả đợi một `CountDownLatch`:

~~~java
static void awaitManaged(CountDownLatch latch)
        throws InterruptedException {
    ForkJoinPool.managedBlock(new ForkJoinPool.ManagedBlocker() {
        @Override
        public boolean isReleasable() {
            return latch.getCount() == 0;
        }

        @Override
        public boolean block() throws InterruptedException {
            latch.await();
            return true;
        }
    });
}
~~~

Đây là **mảnh method**, cần import `java.util.concurrent.CountDownLatch` và `java.util.concurrent.ForkJoinPool`; không có `main`. `isReleasable()` cho biết có thể tiếp tục mà không block; `block()` thực hiện chờ thực sự và trả `true` khi không cần block thêm.

Nếu gọi method này từ ForkJoinWorkerThread, pool có thể quản lý/compensate tình huống blocking theo thuật toán và resource limits. Nhưng:

- Nếu latch không bao giờ countDown, task vẫn có thể chờ vô hạn.
- Nếu worker vẫn giữ một lock khác mà producer cần để countDown, có thể deadlock.
- Nếu blocking nằm trong remote call không hỗ trợ cancellation, việc bọc managedBlock không tự sửa hỏng giao thức.
- Nếu cần timeout, đưa deadline vào blocker/API đợi và xử lý kết quả đúng cách.
- Một số logic bên trong `ManagedBlocker` có thể được gọi lặp; phải giữ đúng contract `isReleasable`/`block`.

## 15. Deadlock và starvation trong cây fork/join

Một pattern lỗi là dùng chung pool nhỏ rồi **block chờ việc mà chính pool chưa đủ worker để thực hiện**. `join()` của ForkJoinTask có những cơ chế hỗ trợ work nhằm tránh trường hợp phổ biến, nhưng không bảo đảm giải quyết mọi đồ thị phụ thuộc tùy ý, nhất là chờ I/O hoặc synchronization ngoài giao thức.

Ví dụ nguy hiểm về mặt thiết kế:

~~~text
Worker A giữ monitor L
  -> đợi một signal / Future từ task B
Task B đang đợi lấy monitor L để hoàn tất
=> vòng phụ thuộc: A không nhả L, B không chạy được
~~~

Đây không phải lỗi “work stealing không hoạt động” mà là **dependency deadlock** do giữ monitor trong khi chờ task khác cần monitor.

### 15.1 Những chống mẫu thường gặp

| Chống mẫu | Vì sao rủi ro | Thay thế |
| --- | --- | --- |
| Fork một task rồi join khi vẫn giữ monitor task con cần. | Vòng chờ về lock. | Nhả lock/hoàn tất critical section trước khi join. |
| Task trong pool chờ I/O vô hạn. | Thiếu worker hoạt động; nguy cơ starvation. | Deadline, executor I/O phù hợp hoặc managedBlock đúng contract. |
| Task A chờ B, B chờ A qua join/Future. | Chu kỳ phụ thuộc không thể tiến triển. | Thiết kế DAG không vòng; review dependency graph. |
| Fork hàng triệu leaf cực nhỏ. | Overhead/queue/memory tăng mạnh. | Threshold xử lý tuần tự và giới hạn phân rã. |
| Mỗi leaf khóa một global mutex dài. | Song song bị tuần tự hóa, contention cao. | Partition state, reduce result thay vì shared accumulator. |
| Common pool bị code bên thứ ba giữ worker lâu. | Ảnh hưởng module khác. | Custom pool/lifecycle isolation, không block unmanaged. |
| ForkJoinTask được fork lại khi đang chạy. | Lifecycle task sai, hành vi không được hỗ trợ. | Tạo task mới cho mỗi computation. |

Không tự kết luận “đổi `ForkJoinPool(4)` thành 100” chữa starvation. Tăng worker có thể tăng memory, context switching và contention, trong khi deadlock vẫn tồn tại.

## 16. asyncMode, local LIFO/FIFO và tác vụ event-style

Một số constructor `ForkJoinPool` có tham số `asyncMode`. Theo tài liệu Java 17:

- Mặc định (không bật asyncMode), pool thường tối ưu local execution theo chính sách hỗ trợ **fork/join task có join**.
- Với `asyncMode=true`, pool áp dụng **local FIFO scheduling** cho các task kiểu event-style **không được join**; đây là một tùy chọn phù hợp trong một số mô hình xử lý tác vụ bất đồng bộ.
- Nó **không bảo đảm toàn cục FIFO** giữa mọi external submission, worker và steal.
- Nó không thay semantics của `join()` hay làm các task phụ thuộc trở nên độc lập.

Ví dụ constructor ở mức API:

~~~java
ForkJoinPool pool = new ForkJoinPool(
        4,
        ForkJoinPool.defaultForkJoinWorkerThreadFactory,
        null,
        true
);
~~~

Đây là mảnh code (đặt trong method/class và import `ForkJoinPool`). `true` chọn async scheduling mode cho local tasks theo contract; `null` nghĩa không dùng một `UncaughtExceptionHandler` tùy biến. Không nên chọn `asyncMode=true` chỉ vì tin “FIFO chắc chắn công bằng hơn”: đo latency/throughput thực tế và hiểu pattern task của mình.

## 17. CountedCompleter: khi join không còn là một cây đơn giản

`CountedCompleter<V>` là một `ForkJoinTask` đặc biệt giúp các tác vụ con phối hợp **completion count** thay vì parent gọi `join()` trên từng child theo một cây nhị phân cố định. Nó có ích cho một số thuật toán traversal, map/scan, propagation và event-driven completion phức tạp.

Nhưng complexity tăng:

- `setPendingCount/addToPendingCount` theo dõi số child còn cần phối hợp.
- `tryComplete()`/`propagateCompletion()` giúp chuyển completion khi không còn pending tasks.
- `onCompletion(...)` và `onExceptionalCompletion(...)` có vai trò riêng theo contract.
- Nếu pending count sai hoặc không gọi đúng completion method, root có thể không bao giờ hoàn tất.
- Cần phân biệt completion của **task chính** với hiệu ứng side effect của các child, và tránh đọc shared state trước khi mọi child cần thiết hoàn thành.

Với tổng mảng, đừng bắt đầu bằng CountedCompleter: `RecursiveTask<Long>` đơn giản và dễ audit hơn. Chỉ dùng CountedCompleter khi **thuật toán thực sự cần một hình dạng đồ thị completion khác** và team hiểu rõ protocol.

## 18. Observation: đo work stealing mà không diễn giải quá mức

`ForkJoinPool` có các API giám sát như:

| Metric / method | Ý nghĩa gần đúng | Điều không nên suy ra |
| --- | --- | --- |
| `getStealCount()` | Ước lượng số task bị worker khác lấy để thực thi. | Không phải bằng chứng mọi task đã steal đúng số lần. |
| `getQueuedTaskCount()` | Ước lượng số task còn trong worker queues. | Không bao gồm chính xác mọi task đang chạy hoặc submission chưa lấy. |
| `getQueuedSubmissionCount()` | Ước lượng số task đang chờ từ external submissions. | Không phải số lượng task còn phải hoàn tất của lô nghiệp vụ. |
| `getActiveThreadCount()` | Ước lượng worker đang active. | Không tương đương số core thực sự bận. |
| `getRunningThreadCount()` | Ước lượng worker không bị suspended bởi join/managed synchronization. | Không bảo đảm không có blocking I/O unmanaged. |
| `getPoolSize()` | Số worker đã bắt đầu nhưng chưa terminate. | Không luôn bằng `getParallelism()`. |
| `getParallelism()` | Mục tiêu parallelism được cấu hình. | Không phải số task đã chạy song song chính xác. |
| `toString()` | Snapshot tình trạng pool thuận tiện khi debug. | Không phải log lịch sử chính xác, không có transaction semantics. |

Với một ví dụ nhỏ, `getStealCount()` có thể bằng 0, 1 hoặc số khác tùy scheduling. **Không assert stdout cụ thể cho chỉ số này.** Thay vào đó:

1. Assert kết quả nghiệp vụ **đúng và xác định**.
2. Đo trên nhiều lần chạy, kích thước dữ liệu và parallelism đại diện.
3. Xem throughput, CPU utilization, p95/p99, allocation, GC và số steals khi workload đủ lớn.
4. Quan sát contention/blocked task qua thread dump, JFR và profiler.
5. Kiểm tra bottleneck có phải memory bandwidth, threshold, false sharing, lock contention hay I/O.

### 18.1 Tránh benchmark có shared bottleneck

Nếu tất cả leaf đều `System.out.println` mỗi phần tử, lock I/O của output có thể chiếm phần lớn thời gian, làm benchmark không phản ánh work stealing. Tương tự, nhiều task cộng vào cùng `AtomicLong` có thể khiến cache contention che lấp lợi ích parallel reduction.

Benchmark nên so sánh **cùng thuật toán**, input, JDK, VM options, warmup và môi trường CPU. Dùng JMH cho microbenchmark JVM nếu cần thay vì chạy một lần rồi kết luận.

## 19. Khi nào chọn ForkJoinPool thay vì executor khác?

| Bài toán | Lựa chọn thường cân nhắc | Lý do |
| --- | --- | --- |
| Divide-and-conquer CPU-bound, cây task sinh động, reduction | **ForkJoinPool + RecursiveTask** | Work stealing hỗ trợ chia tải khi task tự fork nhánh con. |
| Biến đổi mảng trên các phạm vi độc lập, không trả value | **ForkJoinPool + RecursiveAction** | Partition giúp tránh shared mutable accumulator. |
| Nhiều callable độc lập có thời lượng tương đương, không fork con | **Fixed thread pool** hoặc ForkJoinPool sau đo đạc | Work stealing không nhất thiết đem lợi thế. |
| Nhiều task blocking I/O | Executor được thiết kế cho blocking/tài nguyên cụ thể, hoặc virtual threads Java 21+ | ForkJoin worker không được bảo đảm compensate unmanaged blocking. |
| Tác vụ có deadline/cancellation phức tạp, batch results | `ExecutorService` + `Future`/`CompletionService` | Lifecycle/result semantics rõ theo yêu cầu. |
| Xử lý stream dữ liệu có parallel stages | Parallel Stream khi phù hợp, hoặc pipeline thiết kế riêng | Thường dựa vào fork/join internals nhưng cần hiểu ordering và shared pool. |
| Kết hợp nhiều async operation có dependency | `CompletableFuture` composition | Diễn đạt dependency/callback rõ hơn một cây recursive join. |

Điều quan trọng: **ForkJoinPool là chiến lược scheduling, không phải API transaction hoặc safe-publication cho mọi dữ liệu**. Lựa chọn phải bắt đầu từ invariant, khả năng chia việc, chi phí scheduling và yêu cầu hủy/shutdown, sau đó mới tối ưu throughput.

## 20. Lỗi phổ biến và cách sửa

**Lỗi 1: Fork task cho từng phần tử rồi nghĩ “càng nhiều task càng nhanh”.** Không: overhead task, scheduling và allocation có thể lấn át workload. Chọn leaf threshold và đo.

**Lỗi 2: Tạo một Task lớn chỉ có một leaf CPU-bound rồi kỳ vọng steal.** Không có task con khả dụng để steal; công việc không tự chia nhỏ.

**Lỗi 3: Dùng một global `total += value` cho mọi leaf.** Race/lost update; trả partial results và combine sau join.

**Lỗi 4: Dùng `Thread.sleep()` để đo thứ tự worker.** Scheduler không đảm bảo thứ tự. Kiểm tra final result, dùng latch cho bài test interleaving nếu cần.

**Lỗi 5: Nghĩ `getStealCount()` phải dương nếu ForkJoinPool “đúng”.** Với work nhỏ hoặc nhánh được worker gốc xử lý, 0 steal là hoàn toàn hợp lệ.

**Lỗi 6: Gọi I/O blocking rất lâu trong `compute()`.** Có thể làm cạn worker active; dùng timeout, executor khác hoặc managedBlock phù hợp.

**Lỗi 7: Tăng parallelism để chữa deadlock do giữ lock rồi join.** Deadlock dependency không biến mất chỉ bằng nhiều worker.

**Lỗi 8: Shutdown `ForkJoinPool.commonPool()` khi xong module.** Common pool dùng chung; không sở hữu nó như custom pool.

**Lỗi 9: Dùng custom pool nhưng không shutdown/await.** Có thể rò lifecycle và tài nguyên theo môi trường. Owner phải quản lý pool.

**Lỗi 10: Dùng `RecursiveAction` để mutate cùng một index ở nhiều task không synchronization.** Không có bảo đảm atomic/invariant; partition hoặc đồng bộ.

**Lỗi 11: Dùng `ForkJoinTask.join()` như `Thread.join()`.** Hai contract khác nhau, exception và result khác nhau.

**Lỗi 12: Fork lại cùng một ForkJoinTask đang chạy.** Lifecycle sai; tạo instance mới cho lần tính mới.

**Lỗi 13: Bật `asyncMode` rồi khẳng định mọi task FIFO.** Nó liên quan local FIFO cho một số asynchronous workloads, không phải thứ tự toàn cục.

**Lỗi 14: Chia phạm vi chồng lấn [start, mid] và [mid, end] cho thao tác ghi.** Chỉ số mid có thể được xử lý hai lần; dùng half-open intervals nhất quán.

**Lỗi 15: Chỉ đo tốc độ một lần không warm-up.** JIT, GC, CPU và I/O làm kết luận thiếu giá trị; đo workload đại diện, xem hiệu năng cùng correctness.

## 21. Quy trình thiết kế một thuật toán Fork/Join

1. **Xác định bài toán chia được:** các phần con có tính toán độc lập hoặc reduction có tính chất phù hợp không?
2. **Viết hàm tuần tự chuẩn:** có test đúng trước khi song song hóa.
3. **Xác định miền dữ liệu:** dùng `[start, end)` để chia không sót/chồng lấn.
4. **Chọn base case:** leaf đủ lớn để có ích, không đệ quy mãi.
5. **Thiết kế reduction:** kết hợp partial results sau join, xử lý overflow/độ chính xác phù hợp.
6. **Chọn thứ tự fork/compute/join:** tránh fork quá nhiều và join khi giữ lock.
7. **Đảm bảo task không chia sẻ mutable state bừa bãi:** copy/snapshot hoặc partition ownership.
8. **Chọn pool owner:** common pool nếu không cần cô lập, custom pool nếu cần parallelism/lifecycle riêng.
9. **Xử lý failure/cancel:** abnormal completion, interrupt/deadline và cleanup phải có policy.
10. **Đo CPU/overhead/threshold:** so với baseline tuần tự; không mặc định parallel luôn nhanh.
11. **Quan sát work stealing:** xem metrics là ước lượng, không dùng làm assertion thứ tự thực thi.
12. **Đánh giá memory bandwidth và contention:** có thể là giới hạn thực thay vì worker count.
13. **Kiểm tra regression:** kết quả phải đúng trên input rỗng, rất nhỏ, rất lớn và nhánh lệch.
14. **Xem lại khi nâng JDK/đổi hạ tầng:** scheduler và CPU quota có thể ảnh hưởng đặc điểm workload.

## 22. Câu hỏi tự kiểm tra

**1.** ForkJoinPool khác fixed thread pool ở điểm mạnh nào?  
**Đáp:** Workers có thể tạo task con và work-steal task đang chờ từ worker khác, hữu ích cho divide-and-conquer không đều.

**2.** Work stealing có lấy nửa instruction đang chạy trên worker khác không?  
**Đáp:** Không. Nó lấy **task có thể thực thi đang chờ**, không preempt một leaf đang chạy.

**3.** Vì sao một worker thường lấy local ở một đầu deque còn thief lấy đầu đối diện?  
**Đáp:** Để hỗ trợ locality và giảm tranh chấp cùng đầu queue; đây là trực giác về thuật toán, không cam kết mọi interleaving của JVM.

**4.** `RecursiveTask<V>` và `RecursiveAction` khác nhau thế nào?  
**Đáp:** RecursiveTask trả value từ compute; RecursiveAction có compute void.

**5.** Tại sao mẫu `left.fork(); right.compute(); left.join();` thường hợp lý?  
**Đáp:** Một nhánh có cơ hội chạy song song trong khi worker hiện tại làm nhánh kia, giảm scheduling overhead so với fork cả hai.

**6.** Fork mỗi phần tử trong mảng để tính tổng có chắc nhanh hơn vòng for không?  
**Đáp:** Không. Overhead fork/join có thể cao hơn phép cộng; cần leaf threshold và đo.

**7.** `getParallelism() == 4` có chứng minh bốn worker luôn chạy đồng thời không?  
**Đáp:** Không, đó là target parallelism chứ không phải ảnh chụp số worker đang làm việc.

**8.** Khi nào `getStealCount() == 0` vẫn hoàn toàn hợp lệ?  
**Đáp:** Khi workload nhỏ, task tự hoàn tất trên worker sở hữu hoặc không có cơ hội steal.

**9.** Nên dùng `ForkJoinPool.commonPool()` thế nào?  
**Đáp:** Xem như tài nguyên dùng chung; không tự shutdown nó, tránh blocking kéo dài gây ảnh hưởng subsystem khác.

**10.** `ForkJoinTask.join()` khác `Future.get()` về lỗi?  
**Đáp:** Join báo abnormal completion bằng RuntimeException/Error theo contract, còn Future.get dùng checked ExecutionException và có InterruptedException.

**11.** Vì sao đọc mảng sau `pool.invoke` an toàn trong `ForkJoinActionDemo`?  
**Đáp:** Các leaf sửa vùng không chồng lấn, root computation đã hoàn tất trước khi main kiểm tra kết quả.

**12.** Nếu mọi leaf cùng ghi global counter++ thì có race không?  
**Đáp:** Có. ForkJoinPool không tự đồng bộ shared state; dùng reduction hoặc primitive đúng yêu cầu.

**13.** Blocking I/O lâu trong compute có rủi ro gì?  
**Đáp:** Worker bị chiếm, pool không đảm bảo bù thread cho unmanaged blocking; throughput và liveness có thể giảm.

**14.** `ForkJoinPool.managedBlock` có biến mọi wait thành an toàn vô hạn không?  
**Đáp:** Không. Nó giúp pool biết cơ hội blocking để điều chỉnh, nhưng vẫn cần timeout, không có deadlock và resource limits.

**15.** Bật `asyncMode=true` có đảm bảo mọi task FIFO toàn cục không?  
**Đáp:** Không. Nó chủ yếu đổi local scheduling cho những task kiểu asynchronous không joined; không tạo global ordering.

**16.** Khi nào nên dùng CountedCompleter thay RecursiveTask?  
**Đáp:** Khi pattern completion không phù hợp cây join trực tiếp và lợi ích đáng đổi lấy protocol pending count phức tạp.

**17.** Một task fork nhánh trái rồi không bao giờ join/đợi completion nhưng main đọc kết quả nhánh trái ngay, đúng không?  
**Đáp:** Không có bảo đảm task đã xong hay visibility phù hợp; phải dùng completion/join hoặc protocol công bố kết quả đúng.

**18.** Tại sao không thể khẳng định ForkJoin luôn nhanh hơn tuần tự?  
**Đáp:** Work có thể quá nhỏ, memory-bandwidth bound, contention, blocking hoặc overhead chia task lớn hơn lợi ích song song.

**Ghi nhớ:** `ForkJoinPool` chuyên cho **cây task có khả năng fork/join và phân chia công việc**, còn work stealing giúp worker rảnh lấy các task còn chờ để cân bằng tải. **Tính đúng** đến từ chia phạm vi không chồng lấn, reduction sau join và ownership của dữ liệu; **hiệu năng** đến từ grain size, mức parallelism, ít blocking và đo đạc thực tế. Không nhầm scheduling của ForkJoinPool với transaction, fairness hay tự động thread safety của mọi shared object.

## Tham khảo chính thức

- [ForkJoinPool — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, common pool, parallelism, ManagedBlocker, monitoring.
- [ForkJoinTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork, join, invoke và lifecycle.
- [RecursiveTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): task đệ quy có value.
- [RecursiveAction — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): task không trả value.
- [CountedCompleter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): completion count cho các pattern nâng cao.