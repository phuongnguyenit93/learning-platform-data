# Java 7 — Fork/Join: Phối hợp fork, xử lý cục bộ và join

## 1. Vấn đề cần giải quyết

Khi một tác vụ CPU có thể chia thành những phần tương đối độc lập, Java cung cấp framework **Fork/Join** trong gói `java.util.concurrent` để khai thác nhiều lõi CPU. Thao tác cốt lõi thường có ba bước:

1. **`fork()`:** đưa một tác vụ con vào hàng đợi để pool có thể thực hiện trên worker khác.
2. **Xử lý cục bộ bằng `compute()`:** chính worker đang chạy tiếp tục thực hiện một nhánh công việc, thay vì đứng đợi ngay.
3. **`join()`:** lấy kết quả nhánh đã fork, đợi/hỗ trợ thực thi cho đến khi hoàn tất nếu cần, rồi kết hợp các kết quả.

Thứ tự **fork một nhánh → tính nhánh còn lại ngay trong worker hiện tại → join nhánh đầu** là một mẫu quan trọng. Nó tránh phí công enqueue cả hai nhánh trong khi worker hiện tại có thể xử lý trực tiếp một nhánh, và tránh chờ quá sớm trước khi có phần việc cục bộ được hoàn thành.

Bài này tập trung vào **phối hợp đúng ba bước**, không chỉ nêu cú pháp từng phương thức. Bạn sẽ học cách:

- Chia miền dữ liệu thành các phạm vi con **không chồng lấp**, dùng điều kiện dừng để làm phần nhỏ tuần tự.
- Hiểu nghĩa thực tế của `fork`, `compute`, `join`, `invoke` và `invokeAll`.
- Phân tích thứ tự thực thi: **thứ tự fork không phải thứ tự worker chạy, và join không đồng nghĩa tạo thread mới**.
- Dùng `RecursiveTask<V>` để trả kết quả, `RecursiveAction` cho việc cập nhật vùng dữ liệu không trả kết quả.
- Đặt ngưỡng kích thước task (*threshold/granularity*) để giảm overhead.
- Tránh tuần tự hóa bằng join quá sớm, fork quá nhiều, ghi chồng dữ liệu, blocking I/O trong pool và deadlock do chờ vòng.
- Kiểm thử kết quả **xác định** mà không giả định tên thread hoặc lịch chạy của work-stealing.

Những API chính có từ Java 7 và **vẫn được hỗ trợ trong Java 17+**. Ví dụ biên dịch theo `javac --release 17`; không dùng các phương pháp lỗi thời.

## 2. Fork/Join framework gồm những gì?

| Lớp/phương thức | Vai trò |
| --- | --- |
| `ForkJoinPool` | Pool có worker threads và cơ chế **work-stealing** |
| `ForkJoinTask<V>` | Lớp nền của những tác vụ nhỏ có thể fork/join |
| `RecursiveTask<V>` | Tác vụ đệ quy trả về giá trị kiểu V |
| `RecursiveAction` | Tác vụ đệ quy không trả kết quả nghiệp vụ |
| `compute()` | Phương thức tác vụ hiện tại thực hiện công việc |
| `fork()` | Lên lịch thực hiện tác vụ này một cách bất đồng bộ |
| `join()` | Lấy kết quả của tác vụ đã hoàn tất; đợi/hỗ trợ nếu chưa xong |
| `invoke()` | Bắt đầu và chờ kết quả của task này |
| `ForkJoinPool.invoke(task)` | Entry point phổ biến để gửi một root task vào pool và nhận kết quả |
| `invokeAll(taskA,taskB)` | Khởi động các task và chờ tất cả hoàn thành |
| `ForkJoinPool.commonPool()` | Pool dùng chung của JVM |
| `getSurplusQueuedTaskCount()` | Ước lượng số task trong queue của worker so với worker khác, dùng cho heuristics nâng cao |
| `ForkJoinPool.ManagedBlocker` | Giao diện giúp pool biết các trường hợp blocking đặc biệt |
| `shutdown()/awaitTermination()` | Quản lý vòng đời pool **do ứng dụng tạo riêng** |

### 2.1. Tác vụ khác worker thread

Một `ForkJoinTask` **không phải một Thread**. Pool có thể quản lý rất nhiều tác vụ con nhưng chỉ có một số lượng worker threads phù hợp. Khi `left.fork()`, chương trình **không tạo một OS thread mới cho left**; nó sắp xếp để worker hiện tại hoặc worker khác có thể thực hiện `left.compute()` vào thời điểm thích hợp.

### 2.2. Work-stealing có ý nghĩa gì?

Mỗi ForkJoinPool worker quản lý các tác vụ, có thể lấy việc trong queue của chính nó hoặc **đánh cắp công việc chưa bắt đầu của worker khác** nếu mình đang rảnh. Chẳng hạn:

```text
CPU worker W1: đang xử lý task [0, 16)
       |
       +-- fork task [0, 8) ----> queue W1
       |
       +-- compute [8,16) ngay tại W1
                              |
             worker W2 có thể steal task [0,8)
                              |
                    W2 thực hiện nhánh left
                              |
       W1 xong nhánh right ----+---- join left -> combine
```

Đây là **sơ đồ một khả năng scheduling**, không phải hứa W2 chắc chắn lấy nhánh trái. Pool có thể thực hiện forked task trên chính worker W1, worker khác, hoặc thực hiện thêm các task trong khi một join đang chờ. Đó là lý do không nên assert cứng tên/thread/thứ tự log.

## 3. Mẫu quan trọng nhất: fork một nhánh, compute nhánh kia, join

Giả sử một mảng số cần tính tổng:

- Mỗi task phụ trách miền **[from, to)**, tức từ `from` tới `to - 1`.
- Nếu phạm vi nhỏ, dùng vòng for để cộng **cục bộ**.
- Nếu phạm vi lớn, chia theo `mid = from + (to - from) / 2`.
- Nhánh trái là `[from, mid)`, nhánh phải là `[mid, to)`.

Mẫu:

```java
LeftTask left = new LeftTask(...);
RightTask right = new RightTask(...);

left.fork();                    // (1) Có thể xử lý song song.
Result rightValue = right.compute();  // (2) Worker hiện tại tự làm.
Result leftValue = left.join();        // (3) Lấy kết quả nhánh trái.
return combine(leftValue, rightValue);
```

**Đây là pseudocode Java để minh họa**, không phải ví dụ độc lập: `LeftTask`, `RightTask`, `Result`, `combine` và dấu `...` cần được thay bằng kiểu/cấu trúc cụ thể. Mã thực sự biên dịch được nằm ở phần 7 và 9.

### 3.1. Tại sao fork trước compute?

Lệnh `left.fork()` làm một nhánh có cơ hội trở thành công việc cho worker rảnh trong lúc worker hiện tại đang thực hiện `right.compute()`. Nếu worker khác lấy được, có parallelism. Nếu không, pool vẫn có thể thực hiện task đó sau. Mấu chốt là **có một khoảng thời gian hữu ích để hai nhánh tiến triển** trước khi cần kết quả của cả hai.

### 3.2. Tại sao tính cục bộ?

Gọi `right.compute()` **trực tiếp** như một lời gọi hàm Java thông thường; không phải submit thêm task tới pool. Điều này:

- Sử dụng ngay CPU của worker đang chạy.
- Tránh thêm một lần fork/queue/scheduling cho nhánh phải.
- Giảm số `ForkJoinTask` phải được đưa vào work queue.
- Cho phép task còn lại được worker khác steal nếu có worker rảnh.
- Dễ duy trì logic: có đúng một nhánh chủ động chạy cục bộ.

Không hiểu `right.compute()` là “chạy trên thread riêng”: nó chạy trên **chính thread hiện tại**, trừ khi trong quá trình xử lý các subtask của right lại được fork.

### 3.3. Tại sao join cuối?

Sau khi `right.compute()` trả kết quả, task cha vẫn cần kết quả của left. `left.join()` trả giá trị của left sau khi nó hoàn tất, hoặc chờ/hỗ trợ thực thi nếu chưa xong. Việc join ở **điểm thực sự cần kết quả** giữ cơ hội tính song song lớn hơn so với join ngay sau fork.

### 3.4. Một parent phải kết hợp hai kết quả

Nếu `combine` là phép cộng:

```java
long leftValue = left.join();
return Math.addExact(leftValue, rightValue);
```

Nó phải kết hợp **đúng một lần** mỗi miền dữ liệu và tránh đếm trùng. Nếu dùng phép toán không giao hoán như nối chuỗi, thứ tự operand có thể quan trọng: dù left hoàn thành sau right, kết quả cuối vẫn phải ghép theo **thứ tự logic mong muốn**, không phải thứ tự callback/log.

## 4. So sánh các thứ tự để thấy lỗi

### 4.1. Mẫu thường được khuyên dùng

```java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
```

Đây là snippet trong một `RecursiveTask<Long>.compute()` với `left/right` là các task con cùng kiểu. Ưu điểm: một nhánh có thể được steal, một nhánh làm ngay.

### 4.2. Mẫu dễ làm giảm mức song song: join quá sớm

```java
left.fork();
long leftValue = left.join();
long rightValue = right.compute();
return leftValue + rightValue;
```

Vẫn có thể **đúng kết quả**, nhưng luồng đang chạy yêu cầu left hoàn tất **trước khi bắt đầu tính right**. Điều này thường làm mất cơ hội để left và right cùng tiến triển trên các cores. Nó không có nghĩa pool sẽ luôn chỉ dùng một thread; nói chính xác là **không tận dụng được song song giữa hai nhánh theo cách mẫu đầu**.

### 4.3. Fork cả hai rồi join cả hai

```java
left.fork();
right.fork();
long rightValue = right.join();
long leftValue = left.join();
return leftValue + rightValue;
```

Mẫu này có thể hoạt động và được Javadoc đề cập. Tuy nhiên với bài toán đệ quy nhị phân đều đặn, nó thêm một lần fork/queue so với việc tự tính right ngay. Nếu fork cả hai, Javadoc `ForkJoinTask` khuyên **join theo thứ tự ngược**, ví dụ `a.fork(); b.fork(); b.join(); a.join();`, thường hiệu quả hơn join a trước b vì đặc tính queue/work-stealing.

**Không** kết luận “fork hai task luôn sai”. Có trường hợp task graph phức tạp, nhiều subtasks, hoặc `invokeAll` là lựa chọn phù hợp. Nhưng với bài toán chia đôi cơ bản, *fork one / compute one / join* là baseline dễ giải thích và tối ưu chi phí thường gặp.

### 4.4. Không fork và không join

```java
long leftValue = left.compute();
long rightValue = right.compute();
return leftValue + rightValue;
```

Đây là **xử lý tuần tự hai nhánh** bên trong thread hiện tại. Nó có thể hợp lý khi phạm vi nhỏ, nhưng nếu mọi cấp recursion đều làm vậy thì framework không tạo cơ hội để worker khác steal.

### 4.5. Fork không join khi kết quả cần dùng

```java
left.fork();
long rightValue = right.compute();
return rightValue; // SAI: bỏ kết quả left và có thể để task chưa hoàn tất.
```

Đây là **anti-pattern**. Với chia để trị, parent cần kết quả left trước khi combine; bỏ `join` vừa làm sai tổng vừa làm lifetime của subtasks khó kiểm soát.

## 5. Quan hệ giữa compute(), fork(), join(), invoke()

### 5.1. compute() chạy ngay trong thread gọi

`compute()` là phương thức do subclass định nghĩa. Khi trong một worker gọi `right.compute()`, right chạy **đồng bộ theo call stack hiện tại**, không tự xếp task vào queue. Nó có thể tiếp tục fork các task sâu hơn.

### 5.2. fork() lên lịch, không lấy kết quả

`fork()` trả lại **chính task**, thuận tiện cho fluent use:

```java
ForkJoinTask<Long> pending = left.fork();
```

Nó không có nghĩa `left.compute()` đã kết thúc. Một task không được `fork()` lặp lại tùy tiện trong lúc đang hoạt động: tài liệu Java cảnh báo đó là lỗi sử dụng nếu không có chu trình hoàn thành và reinitialize theo hợp đồng (việc tái sử dụng task nâng cao thường không cần cho ứng dụng thông thường).

### 5.3. join() lấy kết quả và xử lý abnormal completion

`join()` trả kết quả khi task hoàn thành. Nếu task ném unchecked exception hoặc error, `join()` truyền thông tin thất bại qua unchecked exception/error theo hợp đồng.

Khác `Future.get()`:

| Đặc điểm | `ForkJoinTask.join()` | `Future.get()` |
| --- | --- | --- |
| Trả kết quả khi task hoàn thành | Có | Có |
| Có thể chờ | Có | Có |
| Khi task ném exception | Phát ra unchecked RuntimeException/Error tương ứng | Gói nguyên nhân trong `ExecutionException` |
| Caller bị interrupt khi chờ | Không ném `InterruptedException` để thoát ngay theo overload cơ bản | `get()` có thể ném `InterruptedException` |
| Có bản có timeout | `join()` không có timeout overload | `get(timeout, unit)` có |
| Thiết kế dùng bên trong Fork/Join recursion | Rất phù hợp | Ít tự nhiên hơn |

**Không gọi `join()` là thao tác “không bao giờ chặn”.** Nó cần kết quả nên có thể đợi, nhưng trong ForkJoinPool worker, runtime có thể hỗ trợ tiến triển của work-stealing thay vì chỉ đợi thụ động theo cách tưởng tượng đơn giản.

### 5.4. invoke() phù hợp entry point hoặc tác vụ con muốn hoàn thành ngay

`ForkJoinPool.invoke(root)` gửi root task tới pool và chờ kết quả. Có thể dùng:

```java
ForkJoinPool pool = new ForkJoinPool(4);
long sum = pool.invoke(new SumTask(...));
```

Đây là snippet minh họa, `SumTask` và tham số được định nghĩa ở ví dụ hoàn chỉnh.

`ForkJoinTask.invoke()` trên một task bắt đầu nó trong thread hiện tại nếu phù hợp, chờ xong rồi trả kết quả. Trong cấu trúc chia đôi, gọi `right.compute()` trực tiếp thường rõ ràng hơn vì bạn biết đang tính cục bộ.

### 5.5. invokeAll() khi muốn API quản lý nhiều subtasks

```java
invokeAll(left, right);
long a = left.join();
long b = right.join();
return a + b;
```

Đây là snippet trong subclass `RecursiveTask<Long>`. `invokeAll` **đã chờ** các tasks xong trước khi trả về (hoặc có abnormal completion); các lệnh `join` sau đó lấy kết quả. Nó tiện cho các dạng chia nhiều nhánh, nhưng không nhất thiết ít overhead hơn mẫu fork one/compute one/join.

**Nếu muốn tập trung tối ưu chia đôi:** dùng mẫu fork left, compute right, join left. **Nếu muốn biểu đạt task graph nhiều nhánh rõ ràng:** `invokeAll` có thể phù hợp, hãy benchmark.

## 6. Điều kiện dừng: vì sao “xử lý cục bộ” có hai nghĩa?

Trong Fork/Join, **xử lý cục bộ** xuất hiện ở hai cấp:

1. **Ở nút chia nhánh:** parent worker tự gọi `right.compute()` thay vì fork right.
2. **Ở nút lá:** khi phạm vi đủ nhỏ, task thực hiện **vòng for tuần tự** và trả kết quả, không chia thêm.

Hai ý nghĩa liên quan nhưng không giống nhau.

### 6.1. Điều kiện dừng chính xác

Giả sử `THRESHOLD = 4`:

```java
if (to - from <= THRESHOLD) {
    long sum = 0;
    for (int i = from; i < to; i++) {
        sum = Math.addExact(sum, numbers[i]);
    }
    return sum;
}
```

Đây là snippet trong `RecursiveTask<Long>.compute()` với `numbers`, `from`, `to` và `THRESHOLD` đã khai báo.

- Với phạm vi có 0–4 phần tử: tính tuần tự.
- Với phạm vi trên 4 phần tử: chia đôi.
- Nếu `from == to`: tổng phạm vi rỗng bằng 0.
- Ngưỡng phải hợp lý và **dương**; ngưỡng 0 có thể gây chia không tiến triển ở phạm vi 1 phần tử nếu code không có điều kiện dừng đúng.
- Không phải mọi dữ liệu đều dùng threshold 4; đây chỉ là ngưỡng nhỏ để dễ nhìn cấu trúc demo.

### 6.2. Tại sao cần threshold?

Nếu cứ chia tới từng phần tử, số task và chi phí queue/fork/join có thể lớn hơn chi phí phép tính thực. Ngược lại, nếu threshold quá lớn, chỉ có vài task nặng và worker khác thiếu việc.

Tối ưu phụ thuộc:

- Tổng số phần tử và phân phối dữ liệu.
- Chi phí tính cho mỗi phần tử.
- Số lõi/parallelism của pool.
- Khả năng chia đều hoặc có nhánh rất lệch.
- Chi phí cấp phát task, tham chiếu dữ liệu, cache locality và memory bandwidth.
- Việc task có I/O/synchronization hoặc CPU-bound thuần.
- Khả năng work-stealing/queue contention.

Không có công thức threshold chung phù hợp mọi workload. Hãy đo nhiều mức ngưỡng bằng JMH/benchmark nghiêm túc và kiểm tra tải production.

## 7. Chương trình Java 17+ hoàn chỉnh: RecursiveTask tính tổng

Ví dụ **`ForkComputeJoinDemo.java`** giải quyết bài toán tổng mảng bằng `RecursiveTask<Long>`, dùng đúng thứ tự **fork trái → compute phải → join trái**.

Để chứng minh cấu trúc task thay vì dựa vào scheduling, demo dùng hai `LongAdder`:

- `forked` đếm số lần code gọi `left.fork()`.
- `leaves` đếm các vùng nhỏ được cộng tuần tự.

Với 16 số và `THRESHOLD = 4`, cây chia đôi có **4 lá** và **3 nút trong**, nên số fork calls bằng **3**, bất kể worker nào thực hiện từng lá.

**Tệp: `ForkComputeJoinDemo.java`**

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.LongStream;

public class ForkComputeJoinDemo {
    private static final int THRESHOLD = 4;

    private static final class SumTask extends RecursiveTask<Long> {
        private final long[] numbers;
        private final int from;
        private final int to;
        private final LongAdder forked;
        private final LongAdder leaves;

        SumTask(long[] numbers, int from, int to,
                LongAdder forked, LongAdder leaves) {
            this.numbers = numbers;
            this.from = from;
            this.to = to;
            this.forked = forked;
            this.leaves = leaves;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                leaves.increment();
                long result = 0L;
                for (int i = from; i < to; i++) {
                    result = Math.addExact(result, numbers[i]);
                }
                return result;
            }
            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(numbers, from, mid, forked, leaves);
            SumTask right = new SumTask(numbers, mid, to, forked, leaves);

            forked.increment();
            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();
            return Math.addExact(leftResult, rightResult);
        }
    }

    public static void main(String[] args) throws Exception {
        long[] data = LongStream.rangeClosed(1, 16).toArray();
        LongAdder forked = new LongAdder();
        LongAdder leaves = new LongAdder();
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(
                    new SumTask(data, 0, data.length, forked, leaves));
            long sequential = LongStream.of(data).sum();
            System.out.println("parallel sum = " + result);
            System.out.println("sequential sum = " + sequential);
            System.out.println("matching = " + (result == sequential));
            System.out.println("fork calls = " + forked.sum());
            System.out.println("leaf computations = " + leaves.sum());
            System.out.println("pool parallelism = " + pool.getParallelism());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ForkComputeJoinDemo.java
java ForkComputeJoinDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24, mã tương thích Java 17:**

```text
parallel sum = 136
sequential sum = 136
matching = true
fork calls = 3
leaf computations = 4
pool parallelism = 4
```

**Tại sao kết quả xác định?**

1. `LongStream.rangeClosed(1,16)` tạo 16 số từ 1 đến 16; tổng chính xác là 136.
2. `pool.invoke(...)` chờ root task xong, do đó khi print, mọi nhánh thuộc computation đã được join trong cây.
3. Cây chia: [0,16) thành [0,8) và [8,16), rồi thành bốn vùng dài 4 — đúng 4 leaves.
4. Mỗi nút trong gọi `left.fork()` một lần, đúng 3 calls.
5. Các `LongAdder` cho phép nhiều tasks tăng counter an toàn; chỉ đọc `sum()` **sau khi root đã hoàn tất**.
6. `pool.getParallelism()` là target parallelism đã cấu hình bằng constructor 4, **không** chứng minh có 4 threads chạy đồng thời trong mọi thời điểm.
7. `Math.addExact` làm phép cộng ném `ArithmeticException` nếu long bị overflow, tránh bỏ qua sai số do tràn trong task. Dataset này nhỏ nên không overflow.

**Không** in tên thread hoặc dựa vào steal count để xác nhận kết quả. Những thông số đó không có giá trị xác định dưới mọi scheduling.

### 7.1. Diễn giải cây chia

```text
Sum [0,16) -> 136
├── left [0,8)  -> 36     <- fork() ở root
│   ├── [0,4)  -> 10      <- fork()
│   └── [4,8)  -> 26      <- compute() cục bộ ở cấp này
└── right [8,16) -> 100   <- compute() cục bộ ở root
    ├── [8,12)  -> 42     <- fork()
    └── [12,16) -> 58     <- compute() cục bộ
```

Tổng bốn lá: 10 + 26 + 42 + 58 = **136**. Mỗi parent join đúng nhánh đã fork rồi cộng hai kết quả. Một lá có thể do bất kỳ worker phù hợp nào thực hiện; cấu trúc dữ liệu không phụ thuộc lịch thực thi.

### 7.2. Vì sao counter không đặt trong biến long thường chia sẻ?

Nếu nhiều tasks cùng ghi `long forkedCount++`, đó là **data race**, kết quả có thể mất increments. `LongAdder` cho phép tăng đếm concurrent an toàn. Nó được dùng để minh họa số nhánh, không phải thành phần cần có trong mọi thuật toán Fork/Join.

### 7.3. Vì sao chia theo [from,to)?

Khoảng **half-open** giúp tránh chồng lấp: trái [from,mid), phải [mid,to). Với `mid = from + (to-from)/2`, ta tránh cộng trực tiếp `from + to` có thể overflow với chỉ số lớn (dù ví dụ này nhỏ). Mỗi phần tử xuất hiện đúng một lần trong cây.

## 8. Giải thích lịch chạy: fork không hứa song song

Với `left.fork(); right.compute(); left.join();`, có ít nhất các diễn biến hợp lệ:

**Trường hợp A: worker khác steal thành công**

```text
W1: left.fork() ---- right.compute() -------- left.join() -> result
                          |
W2:         left.compute() -------- complete
```

Hai nhánh có thời gian chạy chồng nhau, tăng mức song song.

**Trường hợp B: không ai steal left**

```text
W1: left.fork() ---- right.compute() ---- left.join()
                                            |
                                      W1/pool xử lý left
                                            |
                                         combine
```

Không có guarantee một task fork sẽ luôn chạy trên worker khác. Đây là mô hình **cơ hội để parallel**, không phải bắt buộc song song.

**Trường hợp C: bất cân bằng khối lượng**

Nhánh right có thể ngắn hơn left rất nhiều. W1 tính right xong sớm và đến join trong khi left vẫn chạy ở W2, hoặc W1 hỗ trợ thêm work. Khi dữ liệu có nhánh rất không đều, threshold/cách chia cố định 50/50 theo chỉ số chưa chắc cân bằng **thời gian tính**; cần xem độ phức tạp thực của mỗi phần tử/nhánh.

### 8.1. In tên worker để “chứng minh” kết quả là sai mục tiêu

Ví dụ:

```java
System.out.println(Thread.currentThread().getName());
```

đây là snippet có thể chạy ở bất kỳ worker nào. Dòng log có thể xen kẽ không ổn định; in console còn làm thay đổi timing/hiệu năng. Nếu cần quan sát, dùng metrics và tracing không blocking nhiều, nhưng **assert output dựa vào dữ liệu**, không dựa vào thứ tự thread names.

## 9. Chương trình Java 17+ thứ hai: RecursiveAction xử lý miền riêng

Nếu tác vụ không cần trả một giá trị mà cần cập nhật dữ liệu **ở những miền không chồng nhau**, `RecursiveAction` có thể phù hợp. Nó trả `Void` ở cấp ForkJoinTask; `join()` ở đây chủ yếu bảo đảm **đã hoàn tất**.

Ví dụ nhân đôi từng phần tử của một `int[]`. Các task con đều dùng chung array nhưng **chỉ ghi vào đoạn index do mình sở hữu**. Parent join mọi child trước khi trả về, nên main đọc array sau `pool.invoke(...)` là an toàn về lifecycle của công việc.

**Tệp: `DisjointArrayActionDemo.java`**

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

public class DisjointArrayActionDemo {
    private static final class DoubleRange extends RecursiveAction {
        private final int[] values;
        private final int from;
        private final int to;

        DoubleRange(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= 2) {
                for (int i = from; i < to; i++) {
                    values[i] = Math.multiplyExact(values[i], 2);
                }
                return;
            }
            int mid = from + (to - from) / 2;
            DoubleRange left = new DoubleRange(values, from, mid);
            DoubleRange right = new DoubleRange(values, mid, to);
            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) throws Exception {
        int[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            pool.invoke(new DoubleRange(numbers, 0, numbers.length));
            System.out.println("doubled = " + Arrays.toString(numbers));
            System.out.println("length = " + numbers.length);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 DisjointArrayActionDemo.java
java DisjointArrayActionDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24, mã tương thích Java 17:**

```text
doubled = [2, 4, 6, 8, 10, 12, 14, 16]
length = 8
```

Ở ví dụ này, `join()` với `RecursiveAction` không dùng để nhận số hay mảng trả về, mà để đảm bảo tác vụ trái đã xong trước khi task cha kết thúc. Sau khi `pool.invoke(root)` trả về thành công, main mới in giá trị. Không có hai task nào cập nhật **cùng index** vì miền [from,mid) và [mid,to) không chồng lấp.

### 9.1. Chia mảng theo phạm vi là mẫu sở hữu dữ liệu đơn giản

Các phần tử array là shared memory, nhưng mỗi leaf chỉ thay đổi vùng do task đó sở hữu. Không cần khóa cho mỗi phép nhân nếu không có thread khác đọc/ghi cùng index trong lúc tính và tất cả tasks đã join trước khi main đọc. Nếu các nhánh chồng lấp, bạn phải sửa cách partition hoặc dùng synchronization thích hợp.

### 9.2. Tại sao không dùng RecursiveTask để trả mảng mới?

Có thể, nhưng nếu mục tiêu thay đổi trực tiếp mỗi phần tử trong array do app sở hữu, `RecursiveAction` tránh tạo một result object lớn cho mỗi nhánh. Nếu cần tính toán thuần hàm hoặc không được sửa input, nên dùng `RecursiveTask` trả kết quả/buffer mới với hợp đồng immutability rõ ràng. Lựa chọn tùy mục tiêu.

## 10. Sự khác nhau giữa RecursiveTask và RecursiveAction

| Nội dung | `RecursiveTask<V>` | `RecursiveAction` |
| --- | --- | --- |
| Phương thức cần override | `protected V compute()` | `protected void compute()` |
| Kết quả từ `join()` | Giá trị kiểu V | `null` khi hoàn thành bình thường |
| Trường hợp thường dùng | Tổng, max, thống kê, kết quả độc lập | Cập nhật những vùng riêng, biến đổi tại chỗ |
| Kết hợp kết quả | Parent cộng/gộp hai nhánh | Parent chờ children xong, hoặc quản lý kết quả khác |
| Cần giới hạn recursion | Có | Có |
| Có thể fork one, compute one, join | Có | Có |
| Có thể dùng `invokeAll` | Có | Có |

Không dùng `RecursiveAction` rồi bỏ join nếu parent cần bảo đảm các side effects con đã hoàn tất. Ngoài ra, đừng nghĩ `RecursiveTask` có sẵn “gộp hai kết quả” tự động; bạn phải viết `combine` trong `compute()`.

## 11. Khi nào nên dùng invokeAll thay cho mẫu fork/compute/join?

`invokeAll(left,right)` biểu đạt trực tiếp “hai task này phải hoàn thành”. Nó dễ đọc ở một số thuật toán như sort/transform khi cần đợi tất cả children. Ví dụ trong `RecursiveAction.compute()`:

```java
invokeAll(
        new DoubleRange(values, from, mid),
        new DoubleRange(values, mid, to));
```

Đây là snippet với lớp `DoubleRange` từ ví dụ hoàn chỉnh và các biến `values/from/mid/to` hợp lệ. Method tự fork và join theo cách của thư viện, nhưng không có quyền hứa tốc độ cao hơn mẫu tự viết trong mọi workload.

### 11.1. invokeAll với RecursiveTask cần gọi join lấy giá trị

```java
RecursiveTask<Long> left = new SumTask(...);
RecursiveTask<Long> right = new SumTask(...);
invokeAll(left, right);
long result = left.join() + right.join();
```

Đây là **pseudocode**; kiểu `SumTask` và constructor được xác định trong code khác, dấu `...` là tham số thực tế cần thay. `invokeAll` chờ cả hai, sau đó `join` lấy giá trị. Nếu một child thất bại, `invokeAll` có thể ném exception; những child còn lại có thể bị cancel, nhưng trạng thái cụ thể phải kiểm tra theo Javadoc.

### 11.2. Join ngược khi fork nhiều task

Nếu tự fork nhiều subtasks, Javadoc `ForkJoinTask` nói lệnh join thường nên **đi từ task fork sau cùng trở về task fork trước** (innermost-first hoặc reverse fork order):

```java
a.fork();
b.fork();
b.join();
a.join();
```

Nó có thể tận dụng locality/queue behavior tốt hơn so với `a.join(); b.join();`. Đừng áp quy tắc này cho logic business nếu phải xuất dữ liệu theo thứ tự khác; **thứ tự chờ** và **thứ tự kết hợp kết quả** là hai thứ có thể tách biệt.

## 12. Ngưỡng chia bài và chi phí thực tế

Một thuật toán chia đôi mảng kích thước N đến các lá có tối đa T phần tử thường có khoảng **N/T** leaf tasks (bỏ qua việc làm tròn), và số nội nodes xấp xỉ leaves - 1 cho cây nhị phân đầy đủ. Nhưng **mức tăng tốc không tương đương số leaves**:

- Task creation, queue operations, scheduling và steal có chi phí.
- ForkJoin worker count hữu hạn.
- Bộ nhớ/CPU cache và false sharing có thể ảnh hưởng throughput.
- Các nhánh có thể phân bố workload không đều.
- Thuật toán kết hợp kết quả có thể là nút nghẽn.
- Các thao tác I/O/lock có thể làm worker không xử lý được task khác.
- JVM JIT, warm-up, CPU throttling và GC tác động benchmark.

### 12.1. Threshold quá nhỏ

Nếu mỗi leaf chỉ cộng một số, việc allocate task và điều phối có thể đắt hơn phép cộng. Fork/join quá nhiều làm queue đầy và GC pressure. Đặt threshold dựa vào chi phí xử lý, không dựa vào “nhiều tasks đồng nghĩa nhanh”.

### 12.2. Threshold quá lớn

Nếu chỉ có 1–2 leaves lớn trên máy nhiều cores, worker khác rảnh mà không có task để steal. Chọn threshold để có đủ task đồng thời khi workload lớn, nhưng tránh quá nhiều task nhỏ.

### 12.3. Tùy chỉnh threshold bằng benchmark

Thử các mức 512, 2.048, 8.192, 32.768 **chỉ như bộ ứng viên đo đạc**, không phải giá trị khuyến nghị chung. Giữ nguyên dataset, parallelism, logic phép toán; đo throughput, p95 latency, allocations, GC và accuracy. Chạy warm-up và nhiều iterations với JMH hoặc công cụ benchmark đáng tin.

### 12.4. Chia theo chi phí, không chỉ chia theo số phần tử

Nếu một số phần tử có công việc nặng bất thường, chia 50/50 theo count có thể rất lệch theo thời gian. Có thể chọn task partition dựa trên estimated work, chunking thích ứng hoặc work queue; chỉ đừng làm code phân nhánh phức tạp đến mức overhead lớn hơn lợi ích.

## 13. Work stealing không chữa được mọi bottleneck

ForkJoinPool có thể phân phối subtasks khi worker khác nhàn rỗi, nhưng không thể:

- Làm một vòng lặp tuần tự không chia nhỏ tự động chạy trên nhiều cores.
- Tránh mọi lock contention trong dữ liệu dùng chung.
- Bảo đảm mọi fork chạy trên worker khác.
- Vượt quá memory bandwidth của máy.
- Biến blocking I/O thành nonblocking mà không cần thay thiết kế.
- Cứu một thuật toán task dependency **có chu trình chờ**.
- Giảm chi phí tạo hàng triệu tasks nếu ngưỡng quá nhỏ.
- Làm cho phép toán kết hợp không associative/không deterministic trở thành deterministic.

### 13.1. Một task ở main thread khác với task trong pool

Nếu ở ngoài pool bạn gọi `new SumTask(...).fork()` trực tiếp, Javadoc `ForkJoinTask` nói nó dùng **common pool** khi không đang chạy trong ForkJoinPool. Đây có thể là điều **khác với ý định sử dụng custom pool**. Với entry point rõ ràng, hãy dùng `pool.invoke(root)` hoặc `pool.submit(root)` rồi lấy kết quả từ handle.

### 13.2. Không trộn nhiều pool tùy tiện trong recursion

Fork một child từ worker trong custom pool thông thường đưa task tới **pool hiện tại**. Nếu trong compute của một pool lại cố nộp subtasks sang pool khác rồi chờ nhau theo vòng, sẽ tạo dependencies phức tạp và nguy cơ deadlock/starvation. Giữ một root computation và một pool owner khi không có lý do thật sự để phân chia.

## 14. Join và các mối quan hệ phụ thuộc

### 14.1. DAG, không tạo chu trình

Fork/Join phù hợp với task graph dạng **DAG (directed acyclic graph)**. Mỗi task cha đợi children, nhưng children **không được ngược lại đợi cha**. Ví dụ sai:

```text
Task A fork Task B, sau đó join B
Task B lại chờ Task A hoàn thành
           A --> B --> A
```

Một chu trình chờ không thể thỏa mãn, có nguy cơ deadlock. Javadoc ForkJoinTask yêu cầu các join dependencies nên acyclic.

### 14.2. Join không giải quyết data race

Cho dù parent đợi join trước khi kết hợp, hai children có thể cùng sửa một biến shared trong **lúc chạy song song**:

```java
sharedCounter++; // Sai nếu hai tasks cùng chạy mà sharedCounter không đồng bộ.
```

Đây là anti-pattern. Nếu mỗi task trả một `long` cục bộ, parent kết hợp sau join, thường không cần shared counter. Nếu bắt buộc cập nhật thống kê chia sẻ, dùng `LongAdder`/atomics/locks đúng ngữ nghĩa, nhưng đo contention.

### 14.3. Quan hệ memory visibility

ForkJoinTask Javadoc cung cấp các quan hệ visibility khi task được fork và sau khi kết quả đã được join/hoàn thành. Trong code chia để trị tốt:

- Parent tạo children với các tham số/miền bất biến trước `fork()`.
- Children tính trên dữ liệu **riêng hoặc vùng không chồng lấp**.
- Parent không đọc kết quả/side effects của child đang chạy trước join.
- Sau join thành công, parent dùng giá trị child đã hoàn thành.
- Root hoàn tất trước khi main dùng kết quả từ `pool.invoke(root)`.

Đừng viết một biến Boolean thường ở một thread rồi bận rộn chờ thay đổi từ thread khác mà không có quan hệ đồng bộ. Dùng kết quả `join`/`invoke` và các primitives concurrency có hợp đồng rõ.

### 14.4. Không phụ thuộc thứ tự kết quả tạm

Log của children hoặc completion order có thể khác giữa các lần chạy. Kết quả cuối phải được kết hợp theo quy tắc đúng, ví dụ tổng số, max hoặc hợp nhất có thứ tự dựa trên phạm vi dữ liệu.

## 15. Phép kết hợp: associative, commutative và tính đúng

Với tổng số, phép cộng toán học associative/commutative. Nhưng trong máy tính cần xét:

- `int/long` có thể overflow; dùng `Math.addExact` nếu cần phát hiện thay vì wrap.
- `double` có sai số dấu phẩy động; thay đổi thứ tự cộng giữa các nhóm có thể cho sai khác cuối cùng.
- Nối String không commutative: “left + right” khác “right + left”.
- Một số phép kết hợp không associative, ví dụ phép trừ: `(a-b)-c` khác `a-(b-c)`.
- Nếu combine có side effects (ghi file, update DB), trình tự completion và retry trở nên quan trọng.

**Quy tắc:** thuật toán Fork/Join cần phép chia và combine bảo toàn ý nghĩa của bài toán. Không được đổi thứ tự dữ liệu chỉ vì một task kết thúc sớm hơn. Nếu dữ liệu yêu cầu ordering, hãy combine theo **vị trí/sequence** chứ không theo lịch worker.

### 15.1. Tổng double có deterministic không?

Cây chia cố định kết hợp kết quả theo cấu trúc cây cố định có thể giữ một thứ tự phép cộng nhất định trong code, dù scheduling khác. Nhưng kết quả có thể **khác với phép cộng tuần tự trái-to-phải**, vì phép cộng floating-point không associative. Đừng coi mọi sai khác phần thập phân là lỗi race; đánh giá theo độ chính xác và sai số chấp nhận được.

### 15.2. Có nên dùng parallel streams thay cho Fork/Join thủ công?

Với tác vụ map/filter/reduce đơn giản, Java parallel streams có thể ngắn gọn và ít code hơn, thường sử dụng ForkJoinPool.commonPool() theo cách triển khai. Nhưng khi cần kiểm soát cụ thể việc chia task, threshold, ownership vùng dữ liệu và combine, một `RecursiveTask`/`RecursiveAction` tự viết vẫn có giá trị. Tránh giả định parallel stream luôn nhanh hơn stream tuần tự, nhất là với dữ liệu nhỏ hoặc tác vụ blocking.

## 16. Blocking I/O và thread pool: điều cần tránh

ForkJoinPool được tối ưu cho những task chia nhỏ để tính toán, phần lớn **CPU-bound và không block lâu**. Tài liệu Java SE 17 khuyến nghị tránh I/O chặn và các synchronized waits kéo dài trong `ForkJoinTask.compute()`.

### 16.1. Anti-pattern đọc file mạng/DB trong leaf

```java
@Override
protected Long compute() {
    // Không nên gọi blocking HTTP/DB/Files.readAllBytes trong hàng nghìn lá
    // mà không có thiết kế thread/pool riêng và giới hạn concurrency.
    return fetchFromRemoteService();
}
```

Đây là **mã minh họa anti-pattern**, method `fetchFromRemoteService()` không được định nghĩa trong ví dụ đầy đủ. Nếu nhiều workers block vì external I/O, chúng không có CPU để xử lý các forked subtasks khác, có thể gây starvation và throughput kém. Work stealing **không bảo đảm** pool tự bù đầy đủ khi threads bị block bởi I/O hoặc synchronization thông thường.

### 16.2. ManagedBlocker là công cụ nâng cao

`ForkJoinPool.ManagedBlocker` và `ForkJoinPool.managedBlock(...)` cho phép pool **nhận diện một thao tác có thể block** và có thể bố trí thêm worker khi cần để duy trì parallelism. Nó không biến external I/O thành nonblocking và không là lý do để đưa vô hạn blocking operations vào pool.

Dùng ManagedBlocker khi thật sự cần phối hợp với ForkJoinPool và đã hiểu hợp đồng `isReleasable()`, `block()`, exception/cancellation. Với nhiều ứng dụng, giải pháp sạch hơn là **tách I/O sang executor chuyên biệt** hoặc dùng API async phù hợp, rồi chỉ submit CPU work vào ForkJoinPool.

### 16.3. Không gọi join vào một external task graph bị treo

`join` phù hợp nhất khi dependencies có cấu trúc chia để trị rõ, kết thúc được. Nếu task đợi một external event mà event đó lại cần một worker bị block để xử lý, có nguy cơ starvation/deadlock. Không dùng join như cơ chế đợi tín hiệu tùy ý giữa các tasks không liên quan.

## 17. Pool riêng và commonPool(): quyền sở hữu và vòng đời

### 17.1. Pool riêng

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    long result = pool.invoke(new SumTask(...));
    // Dùng result.
} finally {
    pool.shutdown();
    pool.awaitTermination(5, TimeUnit.SECONDS);
}
```

Đây là snippet minh họa với `SumTask` và constructor phù hợp, xử lý InterruptedException. Pool do ứng dụng tạo cần được quản lý lifecycle rõ, không để thread resources tồn tại không cần thiết. Khi shutdown mà tasks còn chạy, cần chính sách graceful vs forced, timeout và báo lỗi.

### 17.2. Java 17 không có try-with-resources cho ForkJoinPool

Trong **Java 17**, `ForkJoinPool` không implements `AutoCloseable`. Mẫu:

```java
try (ForkJoinPool pool = new ForkJoinPool(4)) {
    // ...
}
```

**không biên dịch với `javac --release 17`.** Từ các JDK mới hơn, ExecutorService đã có cơ chế AutoCloseable, nhưng trong bài này baseline là Java 17: dùng `try/finally` và `shutdown()/awaitTermination()`.

### 17.3. Pool dùng chung

`ForkJoinPool.commonPool()` là pool chia sẻ JVM, dùng bởi nhiều APIs/ứng dụng. Nó thường phù hợp cho tác vụ CPU ngắn nhưng **không thuộc quyền sở hữu riêng của module**. Theo Java SE 17, gọi `shutdown()`/`shutdownNow()` trên common pool không có tác dụng làm common pool termination như pool riêng.

Đừng gửi hàng triệu task blocking vào common pool và nghĩ chúng sẽ chỉ ảnh hưởng một module của mình. Nếu muốn isolation, tạo pool riêng; nhưng vẫn phải chọn parallelism/throttle đúng.

### 17.4. Parallelism không phải số worker chạy đồng thời cố định

`new ForkJoinPool(4)` cấu hình target parallelism 4. Pool quản lý worker lifecycle động; không có bảo đảm đúng bốn threads đang chạy trong mọi thời điểm. Tăng parallelism vô hạn không làm CPU có thêm lõi, có thể tăng contention và memory overhead.

## 18. Xử lý exception, cancellation và interrupt

### 18.1. Exception ở task con

Nếu một leaf `compute()` ném `RuntimeException` hoặc `Error`, `join()` của task đó có thể ném lỗi tương ứng. Với ví dụ dùng `Math.addExact`, nếu dữ liệu tràn `long`, `ArithmeticException` có thể lan lên `pool.invoke(root)`.

**Không nuốt exception và thay bằng 0**, vì kết quả tổng có thể sai mà caller không biết. Hãy report hoặc áp chính sách bỏ qua dữ liệu có tài liệu rõ ràng.

### 18.2. ForkJoinTask.join khác Future.get

- `join()` không ném `InterruptedException` khi thread đang đợi, không có timeout overload.
- `Future.get()` có thể ném `InterruptedException`, `ExecutionException`.
- `Future.get(timeout, unit)` có giới hạn thời gian chờ.
- `ForkJoinTask.isDone()` true với cả trạng thái thành công, lỗi hoặc hủy; dùng `isCompletedNormally()`/`isCompletedAbnormally()` khi cần phân biệt.
- `cancel(true)` trên ForkJoinTask không phải cơ chế chắc chắn interrupt worker đang tính; theo ForkJoinTask Javadoc, tham số mayInterruptIfRunning không có tác dụng ở implementation mặc định.

### 18.3. Cancellation không là rollback của side effects

Nếu `RecursiveAction` đã nhân đôi một phần của mảng rồi một nhánh bị hủy/lỗi, mảng **có thể đã biến đổi một phần**. ForkJoinTask không cung cấp transaction rollback. Nếu yêu cầu atomicity của toàn mảng, tính vào mảng/buffer riêng rồi chỉ publish khi root success, hoặc thiết kế cơ chế khôi phục.

### 18.4. invokeAll khi một task thất bại

Nếu `invokeAll(left,right)` gặp abnormal completion, nó có thể ném exception và những task còn lại có thể bị cancel; trạng thái sau đó cần kiểm tra, đừng giả định cả hai đã hoàn thành bình thường. Dùng `isCompletedNormally()`/`getException()` khi cần diagnostic.

## 19. Tính đúng cho dữ liệu chia sẻ

### 19.1. Đọc cùng dữ liệu immutable thường an toàn

Nhiều SumTasks cùng đọc các vùng của một `long[]` **không thay đổi trong suốt computation** có thể tính song song an toàn, miễn array đã được truyền/đưa vào task trước fork theo đúng quan hệ đồng bộ. Không mutate array từ main thread trong khi pool đang đọc.

### 19.2. Ghi vào những vùng không chồng lấp

Trong RecursiveAction demo, mỗi leaf ghi đúng `[from,to)`; các leaf khác không động tới phần tử đó. Parent join children rồi mới hoàn thành. Đây là pattern hữu ích cho image tiles, array transforms và một số thuật toán sort.

### 19.3. Ghi chồng vùng cần synchronization

Nếu hai tasks cùng sửa `values[5]`, có race. Chọn partition khác, hoặc dùng atomic/lock phù hợp. Tránh dùng coarse-grained lock quanh mọi phần tử, vì có thể vô hiệu hóa lợi ích parallelism.

### 19.4. Không dùng biến chung để chứa kết quả tạm nếu không cần

Sai:

```java
sharedSum += partialSum; // Race nếu nhiều tasks cùng thực hiện.
```

Tốt hơn: mỗi child **return partial result**, parent `join` rồi combine. Điều này đơn giản, giảm contention, làm code dễ test và tránh lost update.

## 20. Các chiến lược hiệu năng và giám sát

Để tối ưu Fork/Join, có thể đo:

- Wall-clock time toàn root computation.
- CPU utilization và số lõi thực.
- Số tasks/fork operations; số leaves và kích thước leaf.
- `ForkJoinPool.getStealCount()` — số steal ước lượng, **không phải** số task chắc chắn đã chạy song song.
- `getQueuedTaskCount()`, `getQueuedSubmissionCount()` — các số liệu ước lượng cho quan sát, không dùng để khẳng định tính đúng.
- Allocation rate/GC pressure.
- Memory bandwidth/cache misses nếu có profiler.
- Phân phối thời gian chạy các leaf.
- Thời gian combine và contention.

### 20.1. Không đo bằng một lần chạy vài phần tử

Ví dụ 16 số phục vụ giải thích, không chứng minh Fork/Join nhanh hơn vòng for. Một phép cộng 16 số thường nên làm tuần tự. Chỉ áp dụng parallelism khi công việc mỗi task đủ lớn để bù overhead.

### 20.2. JMH và benchmark thực tế

Khi so benchmark:

1. Tạo dataset đủ lớn, đúng phân phối workload.
2. Warm-up JVM/JIT.
3. So loop tuần tự, Fork/Join và các lựa chọn phù hợp như streams.
4. Thử threshold khác nhau và parallelism khác nhau.
5. Đảm bảo mọi biến thể cho cùng kết quả.
6. Đo nhiều lần, thống kê variance/tail.
7. Không in console trong vòng đo.
8. Kiểm tra CPU throttling, memory pressure và GC.

Không gọi `System.nanoTime()` quanh một lần chạy rất ngắn rồi đưa ra tuyên bố “fork/join luôn nhanh hơn”.

### 20.3. Heuristic getSurplusQueuedTaskCount

`ForkJoinTask.getSurplusQueuedTaskCount()` trả **ước lượng** số tác vụ đang nằm trong queue local so với workers có thể steal. Một số thuật toán nâng cao dùng nó để ngừng fork khi local queue đã quá nhiều. Đây là **tối ưu hóa tùy workload**, không thay ngưỡng base-case hay phép kiểm chứng correctness.

Đừng dùng giá trị heuristic làm luật “luôn phải fork khi count < 3” trong mọi tình huống; queue state biến động theo scheduling.

## 21. Checklist thiết kế

- [ ] Bài toán có thể chia thành các phần độc lập mà vẫn kết hợp kết quả đúng?
- [ ] Đã xác định đúng miền [from,to) và mid không chồng lấp?
- [ ] Có điều kiện dừng để xử lý leaf tuần tự?
- [ ] Threshold không quá nhỏ gây hàng triệu task?
- [ ] Ở nút trong có sử dụng mẫu **fork một nhánh → compute nhánh kia → join** khi phù hợp?
- [ ] Tránh `join()` ngay sau `fork()` khi vẫn còn nhánh cục bộ cần làm?
- [ ] Có kết hợp cả hai kết quả sau join?
- [ ] Có phân biệt fork là scheduling chứ không tạo thread mới?
- [ ] Có hiểu compute() được gọi trực tiếp trên thread hiện tại?
- [ ] Không giả định thread name/thứ tự fork là thứ tự execution?
- [ ] Nếu fork nhiều tasks, có cân nhắc join ngược thứ tự fork/invokeAll?
- [ ] Có bảo đảm phụ thuộc join là DAG, không có chu trình chờ?
- [ ] Shared input không bị sửa đồng thời ngoài sự điều phối?
- [ ] Các RecursiveAction leaves không ghi chồng vùng array?
- [ ] Kết quả intermediate dùng local variables/return thay vì shared mutation thiếu đồng bộ?
- [ ] Với số nguyên lớn, đã cân nhắc overflow/Math.addExact?
- [ ] Với floating-point, đã cân nhắc sai khác do thứ tự phép cộng?
- [ ] Không đưa I/O chặn/DB calls dài vào pool CPU mà thiếu chính sách?
- [ ] Có cân nhắc ManagedBlocker hoặc executor I/O riêng khi thật sự cần?
- [ ] Không fork task lặp khi task cũ vẫn đang chạy?
- [ ] Không gọi `new Task().fork()` ngoài pool rồi ngỡ đang dùng custom pool?
- [ ] Pool do mình tạo có owner shutdown và chờ termination?
- [ ] Java 17 baseline không dùng try-with-resources cho ForkJoinPool?
- [ ] Không shutdown commonPool do hệ thống dùng chung?
- [ ] Có báo lỗi của children ra caller thay vì nuốt?
- [ ] Có hiểu cancellation không rollback tác động của RecursiveAction?
- [ ] Tests so giá trị cuối, không assert scheduling/thread name?
- [ ] Benchmark so cùng input/output, có warm-up và workload đủ lớn?

## 22. Những lỗi phổ biến

**1. “fork() tạo Thread mới.”** Sai. Nó lên lịch ForkJoinTask trong pool.

**2. “Fork một nhánh thì nó chắc chắn chạy trên worker khác.”** Sai. Work-stealing cho phép, không bảo đảm việc steal xảy ra.

**3. “compute() luôn chạy song song.”** Sai nếu được gọi trực tiếp; nó chạy trong thread gọi, chỉ các forked subtasks có cơ hội được xử lý song song.

**4. “left.fork(); left.join(); right.compute() tối ưu như compute trước join.”** Thường kém khả năng overlap giữa hai nhánh.

**5. “Phải fork cả hai nhánh của mọi nút.”** Không. Fork one/compute one/join thường tiết kiệm overhead.

**6. “fork both rồi join theo thứ tự nào cũng có cùng hiệu năng.”** Không nhất thiết; Javadoc gợi ý join ngược fork order thường tốt hơn.

**7. “join() chỉ trả status, không trả kết quả.”** Với RecursiveTask, nó trả `V`; với RecursiveAction, không có business result.

**8. “Không cần join nếu đã fork.”** Sai khi parent cần kết quả/hoàn thành của child.

**9. “join() không bao giờ đợi.”** Sai. Nó chờ nếu cần, dù ForkJoinPool có cơ chế hỗ trợ tiến triển.

**10. “join() ném InterruptedException giống get().”** Sai. Hai APIs có interrupt/exception semantics khác.

**11. “Leaf làm một phép cộng là tốt vì task càng nhỏ càng parallel.”** Sai; overhead thường lớn hơn công việc.

**12. “Threshold 4 tốt cho mọi mảng.”** Sai; chỉ là cấu hình demo.

**13. “Hai nhánh có thể cùng sửa một biến long thường mà không khóa.”** Sai; lost updates/data races.

**14. “Hai RecursiveActions cùng sửa index giống nhau là an toàn vì có join sau đó.”** Sai; join không xóa race xảy ra trước join.

**15. “Số ForkJoinTask equals số Thread.”** Sai; có thể nhiều tasks trên ít workers.

**16. “ForkJoinPool parallelism 4 chứng minh có 4 thread làm việc cùng lúc.”** Sai; nó là cấu hình mức song song mục tiêu.

**17. “In thread name để assert chương trình đúng.”** Sai; scheduling không deterministic.

**18. “Không cần quan tâm overflow khi gộp tổng.”** Sai nếu bài toán yêu cầu số nguyên chính xác.

**19. “Floating-point reduce luôn giống tuần tự bit-for-bit.”** Không bảo đảm nếu thứ tự toán học thay đổi.

**20. “ForkJoinPool tự động tối ưu blocking I/O.”** Không bảo đảm đối với unmanaged blocking.

**21. “ManagedBlocker làm I/O trở thành async.”** Sai; chỉ hỗ trợ pool quản lý parallelism khi biết một task có thể block.

**22. “Task graph có thể join theo vòng vì pool sẽ giải quyết.”** Sai; phụ thuộc vòng có thể deadlock.

**23. “Cứ gọi commonPool.shutdown() sẽ dừng tất cả task của JVM.”** Với Java 17, shutdown common pool không có hiệu ứng như shutdown pool riêng.

**24. “ForkJoinPool dùng AutoCloseable trong Java 17.”** Sai; phải dùng shutdown/finally.

**25. “Cancel sẽ hoàn tác mọi phần tử mà RecursiveAction đã sửa.”** Sai; không có transaction tự động.

**26. “Kết quả trong demo từ nhiều thread nên fork count thay đổi mỗi lần.”** Không; cây chia và counter thread-safe làm số call xác định.

**27. “Parallel stream luôn hiệu quả hơn RecursiveTask hoặc vòng for.”** Không; tùy workload và triển khai.

**28. “Có thể tái fork cùng instance task đang chạy để tiết kiệm cấp phát.”** Sai theo quy tắc sử dụng task.

## 23. Câu hỏi tự kiểm tra

**1.** Fork/Join dùng cho kiểu bài toán nào? — CPU workload chia được thành các subproblems độc lập và có quy tắc combine.

**2.** `fork()` làm gì? — Lên lịch một task để pool thực hiện, không trực tiếp lấy kết quả.

**3.** `compute()` được gọi trực tiếp chạy ở đâu? — Trong thread hiện tại.

**4.** `join()` làm gì? — Chờ/hỗ trợ task hoàn thành rồi trả kết quả hoặc propagate lỗi.

**5.** Thứ tự ba bước khuyên dùng khi chia đôi? — `left.fork(); right.compute(); left.join();`.

**6.** Tại sao phải compute trước join? — Tận dụng CPU của worker hiện tại, cho child forked cơ hội chạy song song, hạn chế chờ sớm.

**7.** Có thể fork cả hai nhánh không? — Có, nhưng thêm overhead; cân nhắc invokeAll hoặc join reverse order.

**8.** `RecursiveTask<V>` trả kiểu gì? — V thông qua compute()/join().

**9.** `RecursiveAction` trả kết quả nghiệp vụ không? — Không; dùng để thực hiện actions.

**10.** `ForkJoinPool.invoke(root)` có thể đợi không? — Có, nó chờ root hoàn thành và trả kết quả.

**11.** `fork()` có bảo đảm một thread mới không? — Không.

**12.** Work-stealing là gì? — Worker rảnh lấy các tasks chưa thực hiện từ queue của worker khác.

**13.** Vì sao có THRESHOLD? — Tránh chia các tác vụ nhỏ đến mức scheduling cost lớn hơn compute cost.

**14.** Với 16 phần tử, threshold 4, có bao nhiêu leaves? — 4.

**15.** Với mẫu fork một trong hai nhánh, cây 4 leaves có mấy calls fork? — 3.

**16.** Vì sao parent phải join child trước khi combine? — Cần result và quan hệ completion đúng.

**17.** Join có bảo đảm không có data race giữa hai leaves không? — Không; phải chia vùng độc lập hoặc synchronize.

**18.** Có thể dùng chung long[] input chỉ đọc cho nhiều tasks không? — Có, nếu dữ liệu không bị mutate đồng thời.

**19.** Hai RecursiveActions trên mảng có thể an toàn khi nào? — Ghi các miền không chồng lấp và join trước khi dùng kết quả.

**20.** `join()` khác `Future.get()` thế nào khi task lỗi? — Join propagate unchecked, get thường dùng ExecutionException.

**21.** `join()` có ném InterruptedException khi chờ không? — Không.

**22.** `Future.get(timeout)` dùng làm gì? — Chờ completion có giới hạn thời gian.

**23.** Những phép toán nào dễ có vấn đề khi thay thứ tự combine? — Phép trừ, nối có thứ tự, floating-point reduction.

**24.** Tại sao không nên dùng blocking DB/file I/O kéo dài trong ForkJoin worker? — Có thể làm workers bận chờ và starvation.

**25.** ManagedBlocker giúp điều gì? — Pool có thể nhận biết và bù workers khi blocking được khai báo, không biến I/O thành async.

**26.** Khi gọi `fork()` ngoài ForkJoinPool, mặc định sẽ sử dụng gì? — common pool nếu task không đang chạy trong pool riêng.

**27.** Pool riêng cần cleanup thế nào trong Java 17? — finally gọi shutdown và awaitTermination theo chính sách.

**28.** `commonPool()` có nên do một module shutdown không? — Không; pool chia sẻ và shutdown của nó không có tác dụng như pool riêng trên Java 17.

**29.** Vì sao không dùng thread name để assert output? — Scheduling/work-stealing không cố định.

**30.** Đo hiệu năng thế nào? — Benchmark cùng workload, kiểm tra correctness, thử threshold/parallelism và đo overhead, CPU, GC.

## 24. Tài liệu chính thức Java SE 17

- [Java SE 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, `invokeAll`, exception semantics, join ordering, work-stealing hints và yêu cầu DAG.
- [Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): mẫu đệ quy có kết quả, fork một nhánh rồi compute/join, nhấn mạnh threshold.
- [Java SE 17 — RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): mẫu đệ quy không trả kết quả, xử lý array ranges.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, commonPool, parallelism, pool lifecycle và ManagedBlocker.
- [Java SE 17 — ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): managed blocking contract.
- [Java SE 17 — LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): thống kê counters cập nhật đồng thời.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): khác biệt giữa get/join, timeout/cancellation.

**Ghi nhớ:** Trong cây Fork/Join chia đôi, mẫu **`left.fork(); long right = rightTask.compute(); long leftResult = left.join(); combine(leftResult,right)`** cho worker hiện tại làm việc hữu ích trong khi nhánh forked có cơ hội được worker khác steal. Dùng **threshold** để tạo lá đủ lớn, **join** trước khi dùng kết quả/side effects, chia data ranges không chồng lấp, tránh shared mutable state và blocking I/O dài. Việc fork **không tạo thread riêng**, còn `join()` không đảm bảo “không đợi”; tốc độ thực phụ thuộc workload, scheduling, parallelism và chi phí task.