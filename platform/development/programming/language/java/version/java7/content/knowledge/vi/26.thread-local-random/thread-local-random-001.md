# Java 7 — ThreadLocalRandom: Giảm tranh chấp khi nhiều luồng cần số ngẫu nhiên

## 1. Bài toán: nhiều threads cùng cần số ngẫu nhiên

Trong ứng dụng đa luồng, một số tác vụ thường cần sinh số ngẫu nhiên để mô phỏng, lấy mẫu, điều chỉnh thời gian retry (*jitter*), thử các lựa chọn không yêu cầu bảo mật, hoặc phân tán tải trong một thuật toán được thiết kế phù hợp. Nếu mọi worker **cùng gọi vào một đối tượng bộ sinh có trạng thái dùng chung**, mỗi lần tạo số mới có thể phải tranh chấp với các luồng khác để cập nhật trạng thái bộ sinh.

Một cách tiếp cận phổ biến:

```java
private static final Random SHARED_RANDOM = new Random();
```

Đây là **khai báo minh họa** trong một class có import `java.util.Random`. Trong Java SE 17, `Random` là **thread-safe**, nên không phải vì dùng chung mà kết quả trở nên “không an toàn về luồng”. Tuy nhiên, cùng một instance phải điều phối cập nhật trạng thái của nó; khi nhiều threads đồng thời gọi thường xuyên, chi phí đồng bộ/tranh chấp có thể làm giảm throughput. Đây là **vấn đề hiệu năng**, không nên mô tả sai thành lỗi data race của `Random`. <https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html>

Thay vì dùng chung instance, Java cung cấp:

```java
int value = ThreadLocalRandom.current().nextInt(1, 7);
```

Đây là **snippet trong phương thức** có import `java.util.concurrent.ThreadLocalRandom`. Lệnh trả một số xúc xắc từ **1 đến 6**, vì giới hạn dưới **bao gồm**, giới hạn trên **không bao gồm**.

**`ThreadLocalRandom`** được thiết kế để tạo số giả ngẫu nhiên với **trạng thái dành riêng cho luồng đang chạy**, giúp nhiều worker có thể tiến hành mà không phải liên tục tranh nhau cập nhật **một trạng thái generator dùng chung**. Theo Javadoc Java 17, khi phù hợp, nó thường có overhead và contention thấp hơn so với việc dùng chung một `Random` trong chương trình đồng thời.

**Trọng tâm bài:** Hiểu vì sao giảm tranh chấp, dùng `current()` đúng trong từng luồng, chọn overload sinh số theo khoảng hợp lệ, phân biệt thread-local với task-local, hiểu giới hạn về reproducibility/bảo mật, kiểm thử và đo hiệu năng mà không đưa ra tuyên bố tốc độ tuyệt đối.

API `ThreadLocalRandom` có từ Java 7 và **vẫn áp dụng trong Java 17+**. Nội dung sử dụng những API còn được hỗ trợ, đồng thời giới thiệu `RandomGenerator` và `SplittableRandom` như các phương án hiện hành khi có nhu cầu khác.

## 2. Tranh chấp là gì? Vấn đề không nằm ở phép toán “random”

Giả sử bốn threads cùng dùng một bộ sinh `Random`:

```text
                   Một Random instance dùng chung
                    [trạng thái RNG duy nhất]
                          ^
        +-----------------+-----------------+
        |                 |                 |
     Worker A          Worker B          Worker C ... 
     nextInt()         nextInt()         nextInt()

Mọi lời gọi đều có thể cạnh tranh cập nhật trạng thái dùng chung.
```

Bên trong `java.util.Random` truyền thống, trạng thái seed được cập nhật nguyên tử. Các cập nhật có thể cần thử lại khi nhiều threads đồng thời can thiệp. Điều này bảo toàn tính an toàn, nhưng dưới tải lớn có thể tạo contention.

Khi các tasks dùng `ThreadLocalRandom.current()`:

```text
Worker A --------> trạng thái RNG dành cho thread A
Worker B --------> trạng thái RNG dành cho thread B
Worker C --------> trạng thái RNG dành cho thread C

Không có một seed dùng chung mà tất cả lời gọi nextInt()
của ba workers bắt buộc cùng giành quyền cập nhật.
```

**Phân biệt hai nghĩa:**

- **Thread safety:** nhiều threads dùng một `Random` cùng lúc vẫn theo hợp đồng thread-safe.
- **Contention avoidance:** thiết kế `ThreadLocalRandom` giảm việc các luồng phải tranh chấp một trạng thái generator duy nhất.

Vì vậy câu “`Random` dùng chung gây lỗi dữ liệu” **không chính xác**. Câu đúng là “`Random` dùng chung có thể tạo nút nghẽn hiệu năng khi có nhiều lần gọi đồng thời”.

### 2.1. Đây có phải lúc nào cũng là bottleneck?

Không. Nếu mỗi request chỉ cần một số ngẫu nhiên, thời gian chạy DB/HTTP, khóa dữ liệu, serialization hoặc network thường lớn hơn rất nhiều. Việc thay `Random` bằng `ThreadLocalRandom` có thể không mang lại cải thiện đo được.

Nhưng nếu có hàng triệu lần sinh số bên trong các workers CPU-bound, contention trên shared generator có thể đáng kể. Hãy đo trên workload thật. **Không công bố một phần trăm speedup cố định** chỉ dựa vào lý thuyết.

### 2.2. Vì sao không cứ tạo new Random() cho mỗi lần gọi?

Tạo `new Random()` mỗi khi muốn một số vừa có thêm chi phí cấp phát/khởi tạo vừa khiến việc quản lý sequence trở nên khó hiểu. Với nhu cầu ngẫu nhiên theo luồng thường xuyên, `ThreadLocalRandom.current()` cung cấp cách truy cập thuận tiện và không yêu cầu application tự quản lý một đối tượng `Random` mới cho mỗi lần gọi.

Nếu bài toán lại yêu cầu **tái lập kết quả theo tác vụ cụ thể**, không phụ thuộc thread chạy task, việc tạo generator riêng **theo task với seed có chủ đích** có thể phù hợp hơn. Ta sẽ thấy ở phần `RandomGenerator` và `SplittableRandom`.

## 3. Cách dùng đúng ThreadLocalRandom.current()

Cách dùng được Javadoc khuyên:

```java
int index = ThreadLocalRandom.current().nextInt(100);
long delayMillis = ThreadLocalRandom.current().nextLong(100L, 251L);
double sample = ThreadLocalRandom.current().nextDouble();
```

Đây là snippet trong phương thức, có import `ThreadLocalRandom`. Kết quả:

- `index` thuộc **[0, 100)**, tức 0–99.
- `delayMillis` thuộc **[100, 251)**, tức từ 100 đến 250 mili-giây.
- `sample` thuộc **[0.0, 1.0)**, không bao gồm 1.0.

Đối tượng hiện hành được truy cập thông qua **`ThreadLocalRandom.current()` trong chính thread đang dùng nó**. Nếu một method gọi nhiều lần liên tiếp trong cùng thread, có thể giữ biến cục bộ:

```java
ThreadLocalRandom rng = ThreadLocalRandom.current();
for (int i = 0; i < 100; i++) {
    int number = rng.nextInt(1, 7);
    // Dùng number bên trong chính thread này.
}
```

Đây là snippet trong phương thức. Việc giữ biến **local** giúp code gọn mà không phải đưa generator sang thread khác.

### 3.1. Không gán generator lấy từ current() thành một trường chia sẻ xuyên threads

Mẫu cần tránh:

```java
class DiceService {
    private final ThreadLocalRandom cached = ThreadLocalRandom.current();

    int roll() {
        return cached.nextInt(1, 7);
    }
}
```

Đây là **anti-pattern về quyền sở hữu thread**. Đối tượng `cached` được lấy ở thread khởi tạo service, rồi có thể được sử dụng ở những threads khác. Javadoc Java 17 nói các method của đối tượng được lấy bằng `current()` nên được gọi **chỉ từ current thread**, không chuyển cho threads khác.

Thay bằng:

```java
class DiceService {
    int roll() {
        return ThreadLocalRandom.current().nextInt(1, 7);
    }
}
```

Đây là class snippet Java 17+ với import `ThreadLocalRandom`. Bất kỳ worker nào gọi `roll()` cũng lấy RNG trong **thread đang thực thi phương thức**.

Đừng dựa vào chi tiết hiện thực cụ thể như việc có thể trả một instance nội bộ giống nhau, tên biến seed trong JDK hoặc bố trí thread fields. Hợp đồng public ổn định là **dùng `current()` ở thread đang cần số**.

### 3.2. current() không tạo một Thread mới

Nó truy cập bộ sinh cho thread hiện tại. Không có chuyện mỗi lời gọi `current()` tự tạo một OS thread, `ExecutorService` mới, hay một task được gửi vào pool. Cũng không cần lock quanh từng lời gọi `nextInt` để bảo vệ một shared `Random`.

### 3.3. Một request không nhất thiết tương ứng một thread

Trong `ExecutorService`, thread pool có thể **tái sử dụng cùng worker** cho nhiều tasks. State ngẫu nhiên là **theo thread**, nên hai tasks chạy lần lượt trên cùng worker có thể sử dụng tiếp sequence của thread đó. Điều này khác “mỗi task tự có generator mới”.

Trong `CompletableFuture` hoặc các callback có thể thực thi trên threads khác nhau, gọi `ThreadLocalRandom.current()` **bên trong callback đang chạy**. Không lấy một RNG ở thread A rồi chuyển reference tới callback chắc chắn chạy trên B.

Tương tự với Java hiện đại có virtual threads (JDK 21+): không đồng nhất “mỗi logical task” với “một pool thread cố định”; đo đặc tính workload và chọn ownership đúng. Các ví dụ của bài sử dụng Java 17+ không đòi hỏi virtual threads.

## 4. Những phương thức sinh số cần dùng thành thạo

| Lời gọi | Miền giá trị | Tình huống |
| --- | --- | --- |
| `nextInt()` | Toàn bộ giá trị `int` có thể có | Giá trị nguyên không giới hạn |
| `nextInt(bound)` | `[0, bound)` | Index trong một collection có size dương |
| `nextInt(origin,bound)` | `[origin,bound)` | Biến số trên một khoảng nguyên |
| `nextLong()` | Giá trị `long` ngẫu nhiên | Dữ liệu giả không bảo mật |
| `nextLong(bound)` | `[0,bound)` | Giá trị lớn với upper bound |
| `nextLong(origin,bound)` | `[origin,bound)` | Backoff/jitter hoặc mô phỏng |
| `nextDouble()` | `[0.0,1.0)` | Lấy mẫu xác suất |
| `nextDouble(bound)` | `[0.0,bound)` | Khoảng thực dương |
| `nextDouble(origin,bound)` | `[origin,bound)` | Biến thực trong khoảng |
| `nextBoolean()` | `true` hoặc `false` | Lựa chọn nhị phân không bảo mật |
| `nextFloat(...)` | Các overload float trong Java 17 | Biến thực kiểu `float` |
| `ints(...) / longs(...) / doubles(...)` | Các streams giá trị ngẫu nhiên | Khi stream hợp với thiết kế dữ liệu |

**Công thức quan trọng:** khoảng đa số bounded overload dùng **origin inclusive, bound exclusive**. Tức [a,b) bao gồm a nhưng không bao gồm b. Đừng đảo dấu ngoặc hoặc giả định `nextInt(1, 6)` có thể cho 6.

### 4.1. Tung xúc xắc sáu mặt

```java
int face = ThreadLocalRandom.current().nextInt(1, 7);
```

Cho các giá trị 1, 2, 3, 4, 5, 6. **Cận trên 7 không xuất hiện**.

### 4.2. Chọn index mảng có ít nhất một phần tử

```java
if (items.isEmpty()) {
    throw new IllegalArgumentException("items must not be empty");
}
int index = ThreadLocalRandom.current().nextInt(items.size());
var selected = items.get(index);
```

Đây là **snippet trong phương thức**, `items` là `List<T>` hợp lệ. Nếu `items.size()==0`, gọi `nextInt(0)` ném `IllegalArgumentException`. Phải validate kích thước trước khi chọn.

### 4.3. Chọn phần trăm xác suất

```java
double probability = 0.25;
boolean sampled = ThreadLocalRandom.current().nextDouble() < probability;
```

Đây là snippet minh họa chính sách **lấy mẫu không bảo mật** với xác suất mục tiêu 25%. Nó không bảo đảm đúng 25% trong mỗi 100 lần chạy; xác suất là đặc tính của **phân phối qua nhiều lần thử**, không phải quota cứng. Validate `probability` thuộc [0,1] và hữu hạn trước khi sử dụng dữ liệu cấu hình đầu vào.

Nếu business đòi “chính xác 25 trong 100 phần tử”, random comparison **không đáp ứng quota chính xác**; cần thuật toán chọn mẫu theo count/partition phù hợp.

### 4.4. Tạo jitter cho retry

```java
long jitterMillis = ThreadLocalRandom.current().nextLong(100L, 251L);
```

Giá trị nằm trong 100..250 ms. Nó có thể dùng làm **thành phần độ trễ ngẫu nhiên** trong một backoff policy đã được thiết kế hợp lệ. Không được suy ra việc gọi `Thread.sleep(jitterMillis)` là tối ưu trong mọi server: ngủ/chặn quá nhiều request threads có thể làm cạn thread pool. Khi có scheduler hoặc asynchronous API, dùng cơ chế phù hợp.

### 4.5. Cận không hợp lệ

Các lỗi điển hình:

```java
ThreadLocalRandom.current().nextInt(0);
ThreadLocalRandom.current().nextInt(5, 5);
ThreadLocalRandom.current().nextLong(9L, 2L);
ThreadLocalRandom.current().nextDouble(2.0, 2.0);
```

Đây là các **anti-pattern minh họa**, mỗi lời gọi ném `IllegalArgumentException` do phạm vi không hợp lệ. Với `nextInt(bound)`, bound phải **dương**. Với `nextInt(origin,bound)`, origin phải **nhỏ hơn** bound. Các overload floating-point cũng có yêu cầu cận hợp lệ/hữu hạn trong API.

## 5. Vì sao không dùng modulo hoặc Math.abs cho khoảng giá trị?

Một lỗi thường gặp:

```java
int index = Math.abs(ThreadLocalRandom.current().nextInt()) % size;
```

Nếu `size` hợp lệ dương, biểu thức này vẫn có hai vấn đề:

1. `Math.abs(Integer.MIN_VALUE)` vẫn là **số âm**, vì không có giá trị int dương tương ứng.
2. Lấy modulo từ một dải kích thước không chia hết cho bound có thể làm phân phối không đều (*modulo bias*).

Thay bằng:

```java
int index = ThreadLocalRandom.current().nextInt(size);
```

với `size > 0`. Bounded API xử lý việc lấy mẫu trong khoảng theo hợp đồng mà không cần người viết tự thêm phép `abs` và `%`.

### 5.1. Không cộng bừa bound + 1

Ví dụ muốn số từ `min` tới `max` **bao gồm cả max**. Có người viết:

```java
int value = ThreadLocalRandom.current().nextInt(min, max + 1);
```

Đây là snippet **chỉ hợp lệ nếu `max < Integer.MAX_VALUE`** và `min <= max`. Nếu `max==Integer.MAX_VALUE`, phép `max+1` overflow, khiến bound sai và ném lỗi.

Trong trường hợp muốn lấy đủ toàn bộ dải int bao gồm `Integer.MAX_VALUE`, cân nhắc làm việc với `nextLong((long)min, (long)max + 1L)` rồi cast khi giá trị nằm trong int, hoặc thiết kế helper giới hạn/chuyển kiểu được kiểm chứng. Không dùng công thức inclusive blindly với số nguyên biên.

### 5.2. Không nhân nextDouble nếu overload theo khoảng đã có

Cách thủ công `(int)(Math.random()*range) + start` dễ làm người đọc quên bound, overflow, bias hoặc khác biệt kiểu dữ liệu. Với số nguyên, dùng `nextInt(origin,bound)`; với long, dùng `nextLong(origin,bound)`. Với double, dùng `nextDouble(origin,bound)` và validate các cận.

## 6. Chương trình Java 17+ hoàn chỉnh: nhiều workers tung xúc xắc

**Tệp: `ConcurrentDiceDemo.java`**

Ví dụ tạo **4 tasks** trên một `ExecutorService` có 4 worker threads. Mỗi task:

1. Tự lấy `ThreadLocalRandom.current()` **bên trong task**, tức trong thread thực thi.
2. Tung xúc xắc **10.000 lần** với `nextInt(1,7)`.
3. Tính sum cục bộ, đếm số lần và kiểm tra mọi kết quả đều trong [1,7).
4. Trả một `record Result` immutable cho main.

Main đợi các Futures rồi tổng hợp. Không dùng một `Random` object chia sẻ hoặc một biến tổng mutable chưa đồng bộ giữa workers.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public class ConcurrentDiceDemo {
    private static final int TASKS = 4;
    private static final int ROLLS_PER_TASK = 10_000;

    private record Result(int count, long sum, boolean inRange) {}

    private static Result rollDice() {
        ThreadLocalRandom rng = ThreadLocalRandom.current();
        long sum = 0L;
        boolean inRange = true;
        for (int i = 0; i < ROLLS_PER_TASK; i++) {
            int dice = rng.nextInt(1, 7);
            inRange &= dice >= 1 && dice < 7;
            sum += dice;
        }
        return new Result(ROLLS_PER_TASK, sum, inRange);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(TASKS);
        try {
            List<Future<Result>> futures = new ArrayList<>();
            for (int i = 0; i < TASKS; i++) {
                futures.add(pool.submit(ConcurrentDiceDemo::rollDice));
            }

            int count = 0;
            long sum = 0L;
            boolean valid = true;
            for (Future<Result> future : futures) {
                Result result = future.get(5, TimeUnit.SECONDS);
                count += result.count();
                sum += result.sum();
                valid &= result.inRange();
            }

            System.out.println("tasks = " + TASKS);
            System.out.println("rolls = " + count);
            System.out.println("all dice in [1, 7) = " + valid);
            System.out.println("sum within limits = " +
                    (sum >= count && sum <= count * 6L));
            System.out.println("one result per task = " +
                    (futures.size() == TASKS));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac --release 17 ConcurrentDiceDemo.java
java ConcurrentDiceDemo
```

**Stdout đã kiểm thử với Windows/JDK 24 (mã dùng tính năng Java 17):**

```text
tasks = 4
rolls = 40000
all dice in [1, 7) = true
sum within limits = true
one result per task = true
```

### 6.1. Tại sao không in tổng số điểm cụ thể?

Tổng số điểm phụ thuộc các lượt tạo số giả ngẫu nhiên, **thường khác giữa các lần chạy**. Nếu in `sum`, không thể viết một stdout cố định đáng tin cho mọi lần. Vì vậy demo chỉ in điều kiện **bất biến**:

- Có 4 tasks.
- Mỗi task tung 10.000 lần, tổng là 40.000.
- Mọi giá trị thuộc [1,7) — đúng theo API.
- Tổng điểm nằm trong [40.000, 240.000].
- Có một Future/result cho mỗi task.

Đây là kiểu kiểm thử đúng cho random production path: **assert properties**, không assert một chuỗi số ngẫu nhiên tưởng tượng.

### 6.2. Tại sao dùng Future<Result>?

`Callable<Result>` trả giá trị cho main. Main chờ `future.get(timeout)` để biết công việc đã hoàn thành, rồi tổng hợp. Không dùng `Thread.sleep(100)` để hy vọng workers xong. Nếu worker throw exception, `Future.get` có thể báo `ExecutionException`; nếu vượt deadline có thể báo `TimeoutException`. Các lỗi này không được phép bị biến thành kết quả giả.

### 6.3. Trong task, mỗi RNG chỉ được dùng ở đâu?

Biến `rng` được tạo **sau khi task đã chạy trong worker thread** và được dùng duy nhất trong method `rollDice()` của chính thread đó. Không có code nào đẩy `rng` sang shared field, queue cho consumer khác hoặc tham số task chạy trên thread khác.

### 6.4. Tại sao dùng sum cục bộ?

Để demo không thêm contention ngoài RNG. Mỗi worker chỉ cập nhật local `long sum` và trả một record. Nếu dùng `static long sum` và để cả bốn threads `sum += dice`, chính biến tổng đó sẽ tạo data race. Có thể dùng `LongAdder` cho counters được nhiều threads cập nhật, nhưng return local result rồi combine trong main đơn giản và dễ chứng minh hơn.

### 6.5. Có phải mẫu này luôn nhanh hơn sequential?

Không. Công việc chỉ 40.000 phép tạo số; chi phí executor, Future và scheduling có thể lớn so với loop thuần. Ví dụ chứng minh **API và thread ownership đúng**, không phải một benchmark công bố speedup. Khi thực sự cần tối ưu, đo với JMH và workload đủ lớn.

## 7. Chương trình Java 17+ hoàn chỉnh: cận, kiểm tra phạm vi và setSeed

**Tệp: `BoundsAndSeedDemo.java`**

Chương trình sử dụng một `ThreadLocalRandom` trong thread hiện tại để sinh 20.000 samples theo ba kiểu:

- `int` trong [5,11).
- `long` trong [1.000.000,2.000.000).
- `double` trong [-2.0,3.0).

Nó cũng kiểm tra hai hợp đồng lỗi quan trọng: cận không hợp lệ và không được tự thay seed của `ThreadLocalRandom`.

```java
import java.util.concurrent.ThreadLocalRandom;

public class BoundsAndSeedDemo {
    public static void main(String[] args) {
        ThreadLocalRandom rng = ThreadLocalRandom.current();
        boolean allIntsInRange = true;
        boolean allLongsInRange = true;
        boolean allDoublesInRange = true;

        for (int i = 0; i < 20_000; i++) {
            int a = rng.nextInt(5, 11);
            long b = rng.nextLong(1_000_000L, 2_000_000L);
            double c = rng.nextDouble(-2.0, 3.0);
            allIntsInRange &= a >= 5 && a < 11;
            allLongsInRange &= b >= 1_000_000L && b < 2_000_000L;
            allDoublesInRange &= c >= -2.0 && c < 3.0;
        }

        boolean invalidBoundsRejected = false;
        try {
            rng.nextInt(7, 7);
        } catch (IllegalArgumentException expected) {
            invalidBoundsRejected = true;
        }

        boolean seedChangeRejected = false;
        try {
            rng.setSeed(12345L);
        } catch (UnsupportedOperationException expected) {
            seedChangeRejected = true;
        }

        System.out.println("ints in [5, 11) = " + allIntsInRange);
        System.out.println("longs in [1000000, 2000000) = " + allLongsInRange);
        System.out.println("doubles in [-2.0, 3.0) = " + allDoublesInRange);
        System.out.println("invalid bounds rejected = " + invalidBoundsRejected);
        System.out.println("setSeed unsupported = " + seedChangeRejected);
    }
}
```

Chạy:

```bash
javac --release 17 BoundsAndSeedDemo.java
java BoundsAndSeedDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
ints in [5, 11) = true
longs in [1000000, 2000000) = true
doubles in [-2.0, 3.0) = true
invalid bounds rejected = true
setSeed unsupported = true
```

### 7.1. Có phải 20.000 lần đủ để “chứng minh ngẫu nhiên”?

Không. Các điều kiện trong demo kiểm tra **hợp đồng phạm vi** của phương thức và việc exception được ném đúng. Nó **không kiểm định độ ngẫu nhiên thống kê**, không chứng minh các chuỗi không tương quan và không kiểm thử bảo mật.

Nếu cần đánh giá chất lượng thống kê của một PRNG cho simulation, phải dùng tập kiểm thử/thí nghiệm được thiết kế riêng, kích thước mẫu phù hợp, phân tích phân phối và giả thuyết, không chỉ kiểm tra tất cả giá trị nằm trong khoảng.

### 7.2. Vì sao setSeed không được hỗ trợ?

`ThreadLocalRandom` tự khởi tạo seed nội bộ cho thread; việc application gọi `setSeed(long)` **luôn ném `UnsupportedOperationException`**. Điều này khác `new Random(seed)` hoặc `new SplittableRandom(seed)`. Không thể ép `ThreadLocalRandom` phát ra một sequence dự kiến chỉ bằng cách gọi `setSeed(123)`.

### 7.3. Giá trị âm có phải lỗi không?

Không, nếu dùng `nextInt()` không giới hạn hoặc `nextInt(origin,bound)` với origin âm. Chỉ giá trị **ngoài miền được yêu cầu** mới là lỗi. `nextInt()` có thể trả số âm theo hợp đồng, nên các thuật toán dùng `Math.abs(nextInt())` để tạo index có thể sai ở MIN_VALUE.

## 8. Seed, tái lập kết quả và bài toán kiểm thử

Đối với simulation hoặc test, đôi khi quan trọng hơn throughput là **reproducibility** — chạy lại cùng input/seed có cùng output. `ThreadLocalRandom` không cho application chủ động đặt seed bằng `setSeed`, vì vậy không phải lựa chọn đúng khi test cần chuỗi giá trị **xác định trước**.

Cần tách hai việc:

- **Production path không bảo mật:** dùng `ThreadLocalRandom.current()` trong thread đang chạy để giảm contention.
- **Testing/replay path:** đưa RNG qua dependency injection; test dùng implementation có seed xác định, production dùng ThreadLocalRandom.

Trong Java 17, `java.util.random.RandomGenerator` là **interface chung** được `Random`, `ThreadLocalRandom`, `SplittableRandom` và nhiều generators hiện hành triển khai.

### 8.1. Chỉ phụ thuộc RandomGenerator thay vì class cụ thể

```java
static int rollDie(RandomGenerator rng) {
    return rng.nextInt(1, 7);
}
```

Đây là snippet với `import java.util.random.RandomGenerator;`. Logic tung xúc xắc chỉ cần phương thức `nextInt(1,7)`; nó không cần biết RNG là thread-local, seeded `Random` hay một generator khác.

### 8.2. Chương trình Java 17+ hoàn chỉnh: InjectedRandomDemo

**Tệp: `InjectedRandomDemo.java`**

```java
import java.util.Arrays;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;
import java.util.random.RandomGenerator;

public class InjectedRandomDemo {
    static int rollDie(RandomGenerator rng) {
        return rng.nextInt(1, 7);
    }

    static int[] sample(RandomGenerator rng) {
        int[] result = new int[6];
        for (int i = 0; i < result.length; i++) {
            result[i] = rollDie(rng);
        }
        return result;
    }

    public static void main(String[] args) {
        int[] first = sample(new Random(2026L));
        int[] second = sample(new Random(2026L));
        int productionSample = rollDie(ThreadLocalRandom.current());

        System.out.println("seeded rolls = " + Arrays.toString(first));
        System.out.println("same seed reproducible = " +
                Arrays.equals(first, second));
        System.out.println("all seeded values in [1, 7) = " +
                Arrays.stream(first).allMatch(n -> n >= 1 && n < 7));
        System.out.println("production value in [1, 7) = " +
                (productionSample >= 1 && productionSample < 7));
    }
}
```

Chạy:

```bash
javac --release 17 InjectedRandomDemo.java
java InjectedRandomDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
seeded rolls = [6, 5, 2, 1, 4, 5]
same seed reproducible = true
all seeded values in [1, 7) = true
production value in [1, 7) = true
```

Với `new Random(2026L)` và **cùng thứ tự sáu lời gọi**, Java bảo đảm sequence xác định theo thuật toán của class `Random`. Dòng cuối không in giá trị RNG thread-local cụ thể, chỉ kiểm tra nó nằm trong miền đúng.

### 8.3. Dependency injection chưa tự tạo thread safety

`RandomGenerator` chỉ là **giao diện chức năng**; không phải mọi implementation đều thread-safe. Nếu giữ một `RandomGenerator` do test tạo rồi chia sẻ giữa hàng chục workers, bạn phải xét thread safety của implementation đó. Trong production, khi mỗi worker tự gọi `ThreadLocalRandom.current()`, bạn đang **tránh** việc dùng chung một stateful instance.

### 8.4. Tests nên tách hai tầng

- **Unit test của business logic:** inject seeded generator hoặc test double có output xác định; kiểm tra mapping từ input random tới quyết định.
- **Concurrency/integration test:** dùng `ThreadLocalRandom` thực ở nhiều workers, assert range, tổng count, completion, không dùng số cụ thể.
- **Performance test:** benchmark shared Random vs per-thread RNG dưới workload tương đương; không lẫn kết quả correctness với performance.

Khi test cần tái lập mọi chi tiết dù task scheduling thay đổi, hãy cấp **một generator theo logical task**, không phụ thuộc việc thread pool phân phối task cho thread nào.

## 9. Thread-local khác task-local: vấn đề khi task chuyển threads

Đây là một khác biệt quan trọng:

```text
Thread pool:
  worker-A: task-1, rồi task-4
  worker-B: task-2, rồi task-5
  worker-C: task-3

ThreadLocalRandom:
  state-A được task-1 rồi task-4 dùng tiếp
  state-B được task-2 rồi task-5 dùng tiếp
  state-C được task-3 dùng
```

Lần chạy sau, scheduler có thể đưa `task-4` sang worker-B. Khi ấy **task-4 nhận sequence khác**. Điều này không làm `ThreadLocalRandom` bị lỗi; nó chỉ cho thấy RNG là **thread-local**, không phải **job-local**.

### 9.1. Khi nào task-local có lợi?

- Simulation phân chia thành nhiều tasks và phải replay đúng cùng seed/input.
- Unit test có expected output cố định cho task N.
- Pipeline phân tán cần mỗi partition có sequence xác định.
- Một thuật toán fork/join chia subproblems phải tránh việc shared mutable RNG làm kết quả phụ thuộc scheduling.

Có thể cấp mỗi task một generator từ seed riêng, hoặc từ `SplittableRandom.split()` được gọi bởi owner trước khi giao generator cho task.

### 9.2. Cần phân biệt “tách seed” và “chia sẻ instance”

Nếu mỗi task có một `SplittableRandom` riêng, không có tranh chấp cập nhật cùng một generator. Nhưng nếu tạo **một** `SplittableRandom root` rồi để nhiều workers đồng thời gọi `root.nextInt()` hoặc `root.split()` trên **cùng instance**, đó không phải pattern hợp lệ: `SplittableRandom` **không thread-safe**.

Chủ sở hữu tạo những generators con theo một thứ tự xác định, rồi giao mỗi generator con cho **chính một task**. Nếu tạo/split ở nhiều threads không điều phối, replay có thể thay đổi.

## 10. Chương trình Java 17+ hoàn chỉnh: SplittableRandom riêng cho từng task

**Tệp: `SplitPerTaskDemo.java`**

Ví dụ này không thay thế `ThreadLocalRandom` ở mọi tình huống; nó minh họa **phương án phù hợp hơn khi cần tái lập theo task**:

1. Owner tạo `SplittableRandom(2026L)`.
2. Owner gọi `split()` **tuần tự**, cấp mỗi child generator cho đúng một task.
3. Các workers dùng generator riêng nên không cùng thay đổi một state.
4. Main đợi Futures theo thứ tự submit và thu các tổng task.
5. Chạy lại từ cùng seed và cùng quy trình split thu được **cùng kết quả** dù task scheduling thay đổi.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SplitPerTaskDemo {
    private static List<Long> calculate(long seed) throws Exception {
        SplittableRandom root = new SplittableRandom(seed);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<Long>> jobs = new ArrayList<>();
            for (int task = 0; task < 4; task++) {
                SplittableRandom child = root.split();
                jobs.add(pool.submit(() -> {
                    long sum = 0L;
                    for (int i = 0; i < 100; i++) {
                        sum += child.nextInt(0, 10);
                    }
                    return sum;
                }));
            }

            List<Long> totals = new ArrayList<>();
            for (Future<Long> job : jobs) {
                totals.add(job.get(5, TimeUnit.SECONDS));
            }
            return totals;
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        List<Long> a = calculate(2026L);
        List<Long> b = calculate(2026L);
        System.out.println("tasks = " + a.size());
        System.out.println("all task sums in [0, 900] = " +
                a.stream().allMatch(v -> v >= 0 && v <= 900));
        System.out.println("fixed-seed replay = " + a.equals(b));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SplitPerTaskDemo.java
java SplitPerTaskDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
tasks = 4
all task sums in [0, 900] = true
fixed-seed replay = true
```

### 10.1. Vì sao tổng thuộc [0,900]?

Mỗi task tạo 100 số nguyên trong [0,10), tức mỗi số 0..9. Tổng thấp nhất bằng 0 và cao nhất bằng 100 × 9 = 900. Ví dụ chỉ in thuộc miền hợp lệ, không in một tổng ngẫu nhiên cụ thể.

### 10.2. Vì sao kết quả replay không phụ thuộc thread scheduling?

Mỗi task sở hữu một `SplittableRandom child` riêng và thực hiện cùng 100 lời gọi trong cùng thứ tự. Không có thread khác sử dụng child đó, nên task nào chạy trước không thay đổi sequence của task khác. Chủ sở hữu tạo các child generators theo thứ tự xác định từ root seed 2026L; việc tạo danh sách Future cũng theo thứ tự cố định.

### 10.3. Điều gì vẫn có thể làm kết quả khác?

Nếu thay đổi số lần `split()`, thứ tự cấp generator cho tasks, số lần mỗi task gọi RNG hoặc thuật toán/phiên bản RNG, kết quả có thể khác. Khi cần replay lâu dài qua nhiều môi trường/versions, ghi rõ **generator algorithm, seed, task partition, số lần gọi và version**. `SplittableRandom` không phải CSPRNG và không tạo độ bảo mật cho seed.

### 10.4. Khi nào vẫn nên chọn ThreadLocalRandom?

Khi không cần seed cố định và cần sinh các số không bảo mật từ nhiều worker threads, ví dụ randomized sampling nhỏ, jitter, randomized backoff trong nhiều tasks độc lập. `ThreadLocalRandom.current()` tiện hơn việc tự chia root seed và quản lý generator theo task.

## 11. So sánh Random, ThreadLocalRandom, SplittableRandom và SecureRandom

| API | Chia sẻ một instance giữa threads? | Chủ động seed/replay | Phù hợp chính |
| --- | --- | --- | --- |
| `java.util.Random` | Thread-safe, nhưng shared instance có thể contend | Có: `new Random(seed)` | Chương trình đơn giản/test cần seed |
| `ThreadLocalRandom` | Nên truy cập bằng `current()` trong **current thread**, không truyền instance giữa threads | Không có `setSeed` ứng dụng | Nhiều threads tạo số phi bảo mật thường xuyên |
| `SplittableRandom` | **Không thread-safe**; dùng riêng/split per task | Có: constructor seed và split có thứ tự | Parallel simulation/fork-join có quản lý task state |
| `RandomGenerator` | Interface; thread-safety tùy implementation | Tùy implementation | Abstraction/test injection/đổi thuật toán |
| `SecureRandom` | CSPRNG API, có providers/đặc điểm triển khai riêng | Có cơ chế seed/provider nhưng không giống Random | Token, nonce, key material và dữ liệu bảo mật |

**Không dùng `ThreadLocalRandom`, `Random` hoặc `SplittableRandom` để tạo secrets, mã OTP, session token hoặc password-reset token.** Chúng là bộ sinh giả ngẫu nhiên **không đảm bảo tính an toàn mật mã**. Dùng `SecureRandom` và thiết kế bảo mật phù hợp.

### 11.1. Random không phải legacy cấm dùng

`java.util.Random` **vẫn hỗ trợ** và có giá trị trong các tests cần seeded deterministic output hoặc code tương thích cũ. Nhưng với khối lượng lớn nhiều threads dùng chung một instance, có thể chịu contention. Java SE 17 cũng cung cấp nhiều thuật toán RNG mới qua `java.util.random` để chọn theo yêu cầu thống kê/hiệu năng. Không phải lựa chọn nào cũng nên dùng cho bảo mật.

### 11.2. RandomGenerator trong Java 17

`RandomGenerator` và `RandomGeneratorFactory` nằm trong `java.util.random`. Đây là API hiện hành để viết code phụ thuộc **interface** thay vì hardcode một implementation. Một factory có thể chọn thuật toán theo nhu cầu và môi trường, nhưng người viết cần xem tài liệu đặc tính thống kê, seed, period, split/jump support và bảo đảm version.

**Không mặc định mọi RandomGenerator thread-safe.** Điều này được Java SE 17 Javadoc nêu rõ; hãy chọn cách sở hữu generator theo thread/task.

### 11.3. Khi nào dùng SecureRandom?

Các trường hợp như:

- Reset-password token và session secret.
- Key material.
- Nonce ngẫu nhiên khi protocol yêu cầu.
- Mã xác thực ngẫu nhiên có yêu cầu chống đoán.
- Security-sensitive identifier.

Ví dụ đơn giản:

```java
SecureRandom secure = new SecureRandom();
byte[] tokenBytes = new byte[32];
secure.nextBytes(tokenBytes);
```

Đây là snippet trong phương thức, cần `import java.security.SecureRandom;`. Kết quả là 32 bytes có nguồn từ CSPRNG/provider phù hợp, không in ra plaintext token. Việc chuyển token thành chuỗi, lưu hash, thiết lập expiration/authorization và chống replay còn phải tuân thủ thiết kế bảo mật của hệ thống.

`SecureRandom` có thể có chi phí/provider behavior khác PRNG thường. Đừng tối ưu bằng cách thay thành ThreadLocalRandom cho token nhạy cảm chỉ vì thấy nhanh hơn.

### 11.4. Math.random có dùng được không?

`Math.random()` vẫn tồn tại và hữu ích ở ví dụ đơn giản. Nhưng nó không cung cấp rõ ràng cấu hình per-thread như `ThreadLocalRandom.current()`. Nếu code đồng thời tạo rất nhiều giá trị trong hot path và cần giảm contention, ThreadLocalRandom hoặc generator thread/task-confined phù hợp hơn. Không kết luận `Math.random()` luôn chậm dựa vào một lần chạy trên máy.

## 12. Chọn RNG theo mục đích thay vì một quy tắc cho mọi hệ thống

### 12.1. Randomized retry jitter

Bài toán: nhiều requests lỗi cùng lúc và retry đồng thời có thể tạo *thundering herd*. Dùng jitter được tính bằng:

```java
long retryDelayMs = ThreadLocalRandom.current().nextLong(100L, 251L);
```

Hãy đưa jitter vào một **backoff policy** có giới hạn lần thử, tổng deadline, cancellation và rate limit. Không thay thế exponential backoff bằng một con số random nếu business cần retry strategy nghiêm túc. Nguồn ngẫu nhiên chỉ cung cấp **một thành phần** của policy.

### 12.2. Sampling telemetry

Nếu muốn lấy khoảng 5% request để thu thập thông tin phi nhạy cảm:

```java
boolean include = ThreadLocalRandom.current().nextDouble() < 0.05;
```

Tỷ lệ thực trong từng tập nhỏ biến động; không dùng làm quota cứng, billing decision hoặc phép chọn mẫu yêu cầu chứng minh không thiên lệch cho từng cohort mà thiếu thiết kế riêng. Vẫn phải áp chính sách privacy/data-minimization đối với dữ liệu telemetry.

### 12.3. Tạo test data đa luồng

Để stress-test concurrency, có thể dùng `ThreadLocalRandom` để tạo dữ liệu không bảo mật khác nhau cho các workers. Nhưng khi phát hiện bug khó tái lập, nên ghi seed/algorithm hoặc chuyển qua task-local seeded generators để replay. Chỉ log những metadata cần thiết, không in dữ liệu nhạy cảm.

### 12.4. Mô phỏng Monte Carlo

Nếu chỉ cần chạy nhanh và không yêu cầu replay chính xác theo từng task, ThreadLocalRandom có thể phù hợp. Nếu kết quả phải reproducible dù work-stealing thay đổi, `SplittableRandom` hoặc một `RandomGenerator.SplittableGenerator` được cấp riêng theo subtask thường giúp quản lý state/seed tốt hơn.

### 12.5. Load balancing có nên chọn server ngẫu nhiên?

Cần xem yêu cầu ổn định, cân bằng tải, health status và routing consistency. Random choice không thay cho weighted/least-load/consistent-hash nếu hệ thống có policy rõ. Nếu cần random tie-breaker không bảo mật, ThreadLocalRandom là một primitive tốt; nhưng algorithm load balancing quyết định tính đúng tổng thể.

## 13. Random per thread có tạo các kết quả luôn khác nhau không?

**Không.** Hai threads dùng RNG riêng có thể cùng sinh số 42 trong một lần thử. Các dải giá trị hữu hạn không có bảo đảm uniqueness chỉ vì generators được tách ra. Ngay cả một generator duy nhất cũng có thể lặp lại giá trị.

Ví dụ:

```java
int ticket = ThreadLocalRandom.current().nextInt(1_000_000);
```

Không thể coi `ticket` là ID unique chắc chắn trong distributed system hoặc là secret không thể đoán. Nếu yêu cầu ID duy nhất, dùng cơ chế ID generator theo yêu cầu (ví dụ database sequence, Snowflake-like service theo thiết kế, UUID với đánh giá collision/uniqueness). Nếu yêu cầu bảo mật, dùng CSPRNG và protocol thích hợp.

### 13.1. Tách state khác với bảo đảm statistical independence tuyệt đối

ThreadLocalRandom được thiết kế để cung cấp chuỗi ngẫu nhiên cho từng thread với chất lượng phù hợp nhiều use cases phi bảo mật. Nó không cam kết mọi số từ các threads đều khác nhau hoặc không có bất kỳ tương quan thống kê nào trong mọi bài toán. Với simulation nghiêm túc, đánh giá thuật toán/period/test suite nếu cần.

### 13.2. Không suy “vì seed riêng nên khó đoán như SecureRandom”

Per-thread state giảm contention, **không mang bảo đảm cryptographic unpredictability**. Kẻ tấn công có thể có phương pháp đoán PRNG output hoặc trạng thái tùy thuật toán/bối cảnh. Phân biệt hoàn toàn yêu cầu performance và security.

## 14. Cách đo contention đúng cách

Để trả lời “ThreadLocalRandom có giảm tranh chấp trên workload của tôi không?”, nên tạo benchmark có điều kiện kiểm soát.

### 14.1. Các phương án so sánh công bằng

1. **Shared Random:** tất cả worker threads dùng **cùng** một `Random`.
2. **ThreadLocalRandom:** mỗi worker lấy `ThreadLocalRandom.current()`.
3. **Per-thread Random:** mỗi thread có một `Random` riêng, không share.
4. **Per-task SplittableRandom:** mỗi task có generator riêng, seed/split có chủ đích.

Lựa chọn 3/4 quan trọng: nếu so **shared Random** với ThreadLocalRandom mà không so với **per-thread Random**, ta không phân biệt được lợi ích do tránh shared state với lợi ích do thuật toán RNG/chi phí của class cụ thể.

### 14.2. Giữ workload tương đồng

- Cùng số thread workers và số lượt sinh số.
- Cùng dạng API, ví dụ cả hai đều sinh số int trong [0,100).
- Cùng cách sử dụng output, tránh compiler loại bỏ kết quả.
- Cùng data allocation/aggregation nếu có thể.
- Warm-up JVM/JIT trước khi đo.
- Đo nhiều forks/iterations với JMH hoặc công cụ benchmark đáng tin.
- Tránh `System.out.println()` bên trong hot loop vì I/O console làm kết quả méo.
- Không dùng `new Random()` bên trong mỗi iteration ở một variant nhưng không ở variant kia; như vậy đang đo allocation chứ không chỉ contention.

### 14.3. Metrics nên quan sát

- Throughput (random draws/giây).
- Latency trung bình và tail của phần công việc.
- CPU utilization và số lõi đang bận.
- Lock/CAS contention nếu profiler hỗ trợ.
- Allocation rate và GC pauses.
- Số workers, task scheduling và context switches.
- Độ khác biệt khi đổi từ 1 → 2 → 4 → 8 threads và cao hơn tùy CPU.
- End-to-end service latency, không chỉ microbenchmark.

### 14.4. Không kết luận “ThreadLocalRandom nhanh hơn x lần” trên mọi JDK

Kết quả phụ thuộc CPU, JIT, JDK version, chi phí tạo mẫu, work distribution, contention thực tế và hệ thống đo. Với 1 thread, shared Random có thể không gây contention. Với code chủ yếu làm I/O, thay RNG có thể không thấy khác biệt. Với CPU loop nhiều threads, khác biệt có thể rõ.

Nếu cần số liệu, hãy **thực sự chạy benchmark**, công bố môi trường và phương pháp đo. Không lấy con số tùy ý từ lý thuyết hoặc từ output kiểm thử range rồi biến thành kết luận hiệu năng.

## 15. Tối ưu hóa những điểm không phải RNG

Trong bài toán nhiều threads, vấn đề performance thường nằm ở nơi khác:

- Shared counters cập nhật bằng `synchronized` hoặc atomic quá nhiều.
- Một global lock bảo vệ object không cần thiết.
- Thread pool quá ít workers cho lượng công việc.
- Queue producer–consumer đầy hoặc consumers bị block.
- I/O network/DB dài làm che mất chi phí RNG.
- Mỗi task tạo hàng nghìn objects mới.
- Kết quả random được đẩy ngay vào một shared `ArrayList` không an toàn.
- Logging từng số random trong hot loop.

Giải pháp nên bắt đầu bằng profiler, không phải “đổi RNG sẽ tự hết mọi tranh chấp”. Bản thân ThreadLocalRandom **chỉ** giảm contention trên phần tạo random; nếu sau đó mọi thread tranh chấp cùng một khóa để dùng kết quả, bottleneck vẫn còn.

### 15.1. LongAdder hay local result?

Nếu chỉ tính số lượt tạo thành công, `LongAdder` là công cụ counter phù hợp trong môi trường nhiều threads. Tuy nhiên bài toán tổng hợp đơn giản có thể hiệu quả hơn khi mỗi task tính **local result** rồi main gộp sau khi `Future.get()`. Cả hai đều là kiến thức Java hiện hành; chọn theo mô hình concurrency và số lần cập nhật.

### 15.2. ThreadLocalRandom không thay cho ThreadLocal của ứng dụng

`ThreadLocalRandom` cung cấp cách tạo random theo thread; nó **không** là nơi bạn nên lưu object nghiệp vụ tùy ý. Nếu cần context/request data, xem lại thiết kế truyền tham số và lifecycle của worker thread. Lạm dụng ThreadLocal cho request context trong thread pool có rủi ro giữ state của request trước; không liên quan tới việc `ThreadLocalRandom.current()` được JDK quản lý.

## 16. Vấn đề khi sử dụng trong ForkJoinPool và parallel tasks

Javadoc `ThreadLocalRandom` nêu đây là lựa chọn phù hợp khi nhiều tasks, chẳng hạn `ForkJoinTask`, cần số ngẫu nhiên song song.

Một task chia để trị có thể viết:

```java
@Override
protected Long compute() {
    if (to - from <= THRESHOLD) {
        ThreadLocalRandom rng = ThreadLocalRandom.current();
        long sum = 0L;
        for (int i = from; i < to; i++) {
            sum += rng.nextInt(0, 100);
        }
        return sum;
    }
    // Chia tasks, fork một nhánh, compute nhánh kia, join rồi gộp.
}
```

Đây là **snippet trong subclass `RecursiveTask<Long>`**, với `from/to/THRESHOLD` do class định nghĩa. Nó chỉ minh họa leaf tạo số local theo **worker thread thực thi leaf**. Không là full runnable program; phần chia tasks cần implement.

### 16.1. Work-stealing làm replay thay đổi

Nếu một subtask hôm nay chạy ở worker-A và lần sau ở worker-B, `ThreadLocalRandom.current()` có thể cung cấp sequence khác. Chấp nhận nếu ứng dụng chỉ cần random samples hợp lệ, không cần tái hiện chính xác từng task.

Nếu muốn replay từng subtask, mang theo generator riêng hoặc seed đã định theo subtask ID, không dựa vào thread-local seed của worker.

### 16.2. ThreadLocalRandom giảm contention RNG chứ không chống starvation

Nếu ForkJoinPool workers đều chờ lock/I/O, dù RNG không contended, throughput vẫn kém. Với I/O-bound tasks, chọn executor/asynchronous flow phù hợp. RNG optimization không sửa một task graph có vòng chờ, quá nhiều blocking operations hoặc chia không đều.

### 16.3. Không coi cùng random sample ở hai workers là race

Hai workers hoàn toàn có thể tạo cùng số 5 trong miền [1,7). Random collision là hiện tượng bình thường. Tính đúng phải được xác nhận bằng sự phân bố/thống kê hoặc business constraints, không phải “tất cả threads phải cho số khác nhau”.

## 17. Dùng RandomGenerator trong thiết kế API sạch

Một service có thể nhận RNG qua phương thức:

```java
static int chooseBucket(RandomGenerator rng, int bucketCount) {
    if (bucketCount <= 0) {
        throw new IllegalArgumentException("bucketCount must be positive");
    }
    return rng.nextInt(bucketCount);
}
```

Đây là snippet Java 17+ có import `java.util.random.RandomGenerator`, không phải chương trình độc lập. Caller có thể truyền:

- `ThreadLocalRandom.current()` khi chạy **trong thread cần sample**.
- `new Random(fixedSeed)` cho unit test.
- `new SplittableRandom(seed)` cho task có generator riêng.
- Một generator khác có đặc tính được ứng dụng lựa chọn.

### 17.1. Không giữ một RNG phụ thuộc luồng trong singleton service

Tối ưu không đúng:

```java
final class BucketService {
    private final RandomGenerator rng = ThreadLocalRandom.current();

    int select(int count) {
        return rng.nextInt(count);
    }
}
```

Đây là anti-pattern vì field có thể bị dùng từ các threads khác. Nếu service singleton xử lý nhiều requests đồng thời, nên gọi `ThreadLocalRandom.current()` **tại nơi tạo số**, hoặc nhận RNG **theo lời gọi**.

### 17.2. Phương pháp test không cần đổi code production

Unit tests gọi `chooseBucket(new Random(2026L), 10)`. Production gọi `chooseBucket(ThreadLocalRandom.current(), 10)`. Có thể test cùng validation rules mà không làm production path phải nhận seed cố định hoặc dùng một RNG shared.

### 17.3. RandomGenerator không phải một cái khóa

Interface `RandomGenerator` không tự bảo đảm mọi implementation safe để chia sẻ giữa threads. Đừng đưa một đối tượng implement interface vào field singleton rồi nghĩ “vì là interface concurrency” nên không cần kiểm tra.

## 18. Bảo mật: sai lầm nghiêm trọng khi dùng RNG nhanh cho token

Tốc độ sinh số ngẫu nhiên và tính không thể đoán của mã bí mật là **hai yêu cầu khác nhau**.

**Không dùng ThreadLocalRandom để tạo:**

- Session ID cần chống dự đoán.
- Password reset token.
- OTP hoặc mã xác thực đòi hỏi bảo vệ trước attacker.
- Secret key/nonce cryptographic theo yêu cầu protocol.
- Access token chứa khả năng truy cập.
- Mã bảo mật dùng làm căn cứ xác thực người dùng.

### 18.1. Vì sao không an toàn?

`ThreadLocalRandom` là **pseudorandom generator không được thiết kế để chống tấn công dự đoán**. Việc seed được JDK quản lý và có state riêng theo thread không biến nó thành cryptographically secure PRNG. Javadoc Java SE 17 nêu rõ hãy xem xét `SecureRandom` cho security-sensitive applications.

### 18.2. Khi nào “không bảo mật” vẫn dùng được?

- Mô phỏng xác suất.
- Random sampling telemetry đã có chính sách dữ liệu.
- Retry jitter.
- Game mechanics không liên quan tiền/tài sản và không cần anti-cheat mạnh.
- Load simulation/test data.
- Lựa chọn ngẫu nhiên không ảnh hưởng quyền truy cập.

Nhưng với game có phần thưởng hoặc lottery chịu yêu cầu công bằng và anti-tampering, có thể cần cơ chế có kiểm chứng và bảo mật mạnh hơn; không chỉ dựa vào TLR.

### 18.3. Đừng nâng seed thành secret

Dùng `new Random(secretSeed)` không tự tạo CSPRNG. Thuật toán và state update của Random không có cam kết cryptographic unpredictability. Nếu cần security, dùng SecureRandom/provider đạt yêu cầu thay vì “giấu seed”.

## 19. Failure modes và cách xử lý

| Tình huống | Hành vi/hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng một `Random` instance cho nhiều workers ở hot loop | Thread-safe nhưng có thể contention | Cân nhắc ThreadLocalRandom hoặc per-thread RNG |
| `ThreadLocalRandom.current()` ở thread A rồi truyền object sang B | Vi phạm usage recommendation của API | Gọi `current()` trong thread thực thi |
| `nextInt(0)` | `IllegalArgumentException` | Validate bound dương |
| `nextInt(5,5)` | `IllegalArgumentException` | Origin phải nhỏ hơn bound |
| `nextLong(10,5)` | `IllegalArgumentException` | Kiểm tra cận |
| `nextDouble(a,b)` với cận không hợp lệ | `IllegalArgumentException` | Validate finite/range |
| `setSeed(123)` trên ThreadLocalRandom | `UnsupportedOperationException` | Dùng seeded RNG khác cho test |
| Dùng `Math.abs(nextInt()) % n` | MIN_VALUE âm và modulo bias | Dùng `nextInt(n)` |
| Dùng `nextInt(min,max+1)` khi max==MAX_VALUE | Int overflow | Dùng logic cận với long hoặc xử lý biên |
| Dùng ThreadLocalRandom để cấp token | Không an toàn mật mã | Dùng SecureRandom |
| Coi mỗi sample phải unique | Collisions bình thường | Dùng ID protocol nếu cần uniqueness |
| Mong output random giống nhau ở mỗi lần test | Thread-local seed không điều khiển được | Inject seeded RandomGenerator |
| Chia sẻ một SplittableRandom giữa workers | Không thread-safe | Split và giao mỗi child cho một task |
| Đo benchmark có log trong loop | Đo logging nhiều hơn RNG | Tách logging khỏi hot path |
| Cache một ThreadLocalRandom trong singleton | Object có thể dùng khác current thread | Lấy current ở method đang chạy |
| CPU-bound loop tạo số nhưng dùng shared result List | Race/contended result collection | Local results, kết hợp sau Future |
| Dùng ThreadLocalRandom để tăng throughput I/O-bound API | Có thể không cải thiện gì | Profile và tối ưu bottleneck thật |

Các exception ở bảng là **những hành vi của API**. Đừng catch mọi RuntimeException rồi trả ngẫu nhiên bằng 0: 0 có thể là một giá trị business hợp lệ và che giấu cấu hình sai.

## 20. Kiểm thử tính đúng và performance

### 20.1. Property tests với ThreadLocalRandom

Dùng nhiều samples và assert:

- `nextInt(1,7)` luôn thuộc 1..6.
- `nextInt(0, n)` luôn thuộc 0..n-1 khi n>0.
- `nextLong(origin,bound)` có giá trị trong khoảng.
- `nextDouble()` trong [0,1).
- Các lời gọi với origin>=bound ném lỗi.
- `setSeed` ném UnsupportedOperationException.
- Nhiều tasks kết thúc; số lượt tạo/tổng counter không mất.
- Không có shared mutable result được cập nhật thiếu đồng bộ.

Không assert “mọi lần tung xúc xắc nhất định sẽ thấy đủ sáu mặt” với một số mẫu nhỏ, vì đó là biến cố xác suất, không phải bảo đảm tuyệt đối.

### 20.2. Seeded tests cho logic nghiệp vụ

Nếu business rules cần predictable output:

- Truyền `RandomGenerator` như một dependency.
- Dùng `new Random(fixedSeed)` hoặc generator seed được hỗ trợ.
- Giữ cố định số lần gọi và thứ tự gọi.
- Test expected output/decision.
- Đừng làm test phụ thuộc thread pool scheduling khi không phải nội dung cần test.
- Tạo fresh generator cho mỗi test nếu muốn tests độc lập.

### 20.3. Benchmark tests cho contention

Dùng JMH hoặc công cụ đáng tin, nhiều threads, workload đủ lớn. So shared Random, ThreadLocalRandom và per-thread/per-task alternatives trên cùng loại phép gọi. Thu thập throughput, latency, GC, allocation và tính đúng, không chốt kết luận chỉ từ một lần thử.

### 20.4. Test của helper validate trước khi gọi RNG

Một helper chọn index phải trả lỗi sớm nếu n<=0; đừng gọi RNG rồi vô tình nuốt IllegalArgumentException. Khi test index trong collection có thể rỗng, hãy có case `empty`, `size=1`, `size=Integer.MAX_VALUE` nếu logic có tính toán cận cần kiểm tra.

### 20.5. Điều kiện nào là deterministic?

- **Deterministic:** số tasks submit, số draws mỗi task, sum nằm trong bound, exception rules, seeded sequences theo algorithm cố định.
- **Không deterministic:** thread nào thực thi từng task, số random thực tế từ `ThreadLocalRandom`, thứ tự log từ workers, timing/steal counts.
- **Phụ thuộc môi trường:** throughput và mức contention, CPU/JIT/runtime/JDK version.

## 21. Checklist code review

- [ ] Có thực sự cần RNG tại nhiều threads trong hot path?
- [ ] Đã phân biệt “Random shared thread-safe” với “có thể contention”?
- [ ] Dùng `ThreadLocalRandom.current()` ở đúng thread thực thi?
- [ ] Không lưu một RNG lấy ở thread khởi tạo singleton rồi dùng qua threads khác?
- [ ] Nếu giữ biến cục bộ `rng`, nó chỉ được dùng trong cùng thread?
- [ ] Không tạo `new Random()` ở mỗi lần gọi vô ích?
- [ ] Chọn `nextInt/nextLong/nextDouble` với cận hợp lệ?
- [ ] Hiểu origin inclusive/bound exclusive?
- [ ] `nextInt(1,7)` trả 1..6, không phải 1..7?
- [ ] Không truyền bound 0 hoặc âm?
- [ ] Không dùng `Math.abs(nextInt()) % bound`?
- [ ] Có xử lý nguy cơ overflow ở `max+1` nếu muốn inclusive max?
- [ ] Có validate xác suất đầu vào [0,1] khi dùng `nextDouble()<p`?
- [ ] Nếu dùng jitter, có upper bound, retry policy và cancellation/deadline?
- [ ] Không xem random sampling là quota/chứng minh thống kê tuyệt đối?
- [ ] Không dùng TLR để tạo token, mật khẩu, OTP hoặc key bảo mật?
- [ ] Khi cần security, dùng `SecureRandom` theo protocol phù hợp?
- [ ] Không giả định random integer là ID unique?
- [ ] Khi cần test reproducible, không gọi `ThreadLocalRandom.setSeed`?
- [ ] Có injection seam như `RandomGenerator`?
- [ ] Không chia sẻ implementation RandomGenerator chưa được xác định thread-safe?
- [ ] Khi cần replay theo task, mỗi task có seeded/split generator riêng?
- [ ] Với `SplittableRandom`, không chia sẻ cùng instance cho nhiều workers?
- [ ] Không dùng thread-local RNG để kỳ vọng output cố định theo task scheduling?
- [ ] Có dùng Future/await thay vì sleep tùy ý để đợi tasks?
- [ ] Không cập nhật shared sum/counter bằng data race?
- [ ] Trong benchmark có warm-up, nhiều threads và output usage hợp lệ?
- [ ] Không in console bên trong hot loop benchmark?
- [ ] Có so per-thread Random/per-task SplittableRandom trước khi kết luận?
- [ ] Có đo end-to-end throughput/latency, không chỉ chi phí RNG?
- [ ] Có kiểm tra source tài liệu Java SE 17+ và version requirement?
- [ ] Không giả định JDK implementation details là public contract?

## 22. Các sai lầm phổ biến

**1. “Một Random instance dùng chung chắc chắn bị race.”** Sai; Java Random thread-safe, nhưng có thể chịu contention.

**2. “ThreadLocalRandom làm mọi thread dùng cùng seed hiệu quả hơn.”** Sai; mục tiêu là tách trạng thái sử dụng theo current thread, không cùng tranh seed.

**3. “current() tạo một thread mới.”** Sai; nó lấy RNG trong thread đang chạy.

**4. “Có thể lấy current() trong main rồi truyền cho mọi worker.”** Không phải cách dùng được Javadoc khuyên; lấy current trong worker.

**5. “ThreadLocalRandom là biến RNG dành cho mỗi request.”** Không nhất thiết; thread pool có thể tái sử dụng thread cho nhiều requests/tasks.

**6. “Mỗi task chạy hai lần sẽ nhận cùng số từ ThreadLocalRandom.”** Không; seed/sequence không được application kiểm soát và scheduling thay đổi.

**7. “ThreadLocalRandom.setSeed cho reproducible tests.”** Sai; ném UnsupportedOperationException.

**8. “ThreadLocalRandom.nextInt(1,7) có thể trả 7.”** Sai; bound exclusive.

**9. “ThreadLocalRandom.nextInt(0) trả 0.”** Sai; ném IllegalArgumentException.

**10. “Chỉ cần Math.abs(nextInt()) là không âm.”** Sai với Integer.MIN_VALUE.

**11. “Modulo giúp phân phối hoàn toàn đều cho mọi bound.”** Không; có thể modulo bias.

**12. “nextInt(min,max+1) an toàn với mọi int max.”** Sai nếu max+1 overflow.

**13. “Mỗi worker có generator riêng nên mọi random values luôn khác nhau.”** Sai; random collision bình thường.

**14. “Per-thread nghĩa là cryptographically secure.”** Sai; ThreadLocalRandom không phải CSPRNG.

**15. “Bỏ SecureRandom thay ThreadLocalRandom để tăng throughput tạo reset token.”** Không an toàn.

**16. “Chỉ cần một seed bí mật là Random thành RNG bảo mật.”** Sai.

**17. “RandomGenerator interface bảo đảm mọi implementation thread-safe.”** Sai; implementation có thể không thread-safe.

**18. “SplittableRandom có thể dùng chung giữa nhiều threads vì tên có split.”** Sai; dùng split per task, không share instance.

**19. “Dùng ThreadLocalRandom không cần quan tâm thread scheduling khi cần replay.”** Sai; task chuyển thread có thể làm output khác.

**20. “Chạy 100 samples mà không trùng chứng minh RNG bảo đảm uniqueness.”** Sai.

**21. “Độ lệch tỷ lệ lấy mẫu là bug nếu trong 100 samples không đúng chính xác 25%.”** Sai với sampling theo xác suất.

**22. “Gọi Thread.sleep với jitter trong mọi callback luôn tối ưu.”** Sai; có thể block request threads.

**23. “Shared result List tự thread-safe vì random generation thread-safe.”** Sai; data race ở result collection là vấn đề độc lập.

**24. “JMH không cần vì System.nanoTime chạy một lần đủ.”** Không; JVM warm-up, JIT, scheduling và environment ảnh hưởng nhiều.

**25. “ThreadLocalRandom chắc chắn nhanh hơn mọi RNG khác trên mọi máy.”** Không có bảo đảm.

**26. “Các nguồn ngẫu nhiên không bảo mật thay được DB sequence nếu cần ID không trùng.”** Sai; phải xét uniqueness protocol.

**27. “String/byte[] chứa token được tạo từ TLR là đủ bảo mật nếu dài.”** Sai; bảo mật không chỉ phụ thuộc độ dài.

**28. “Dùng RandomGenerator là tự có deterministic sequence.”** Không; tính tái lập phụ thuộc implementation/seed/call order.

**29. “Unit test nên assert ThreadLocalRandom.current().nextInt(1,7)==3.”** Sai; không có giá trị cố định.

**30. “Bỏ qua invalid bounds bằng catch rồi return 0 luôn an toàn.”** Sai; che lỗi cấu hình và có thể vi phạm business logic.

## 23. Câu hỏi tự kiểm tra

**1.** Vì sao `ThreadLocalRandom` hữu ích khi nhiều threads cần random? — Tách trạng thái RNG theo current thread, giảm contention so với một Random instance dùng chung.

**2.** `Random` có thread-safe không? — Có trong Java 17, nhưng chia sẻ nhiều threads có thể contend.

**3.** Cách lấy ThreadLocalRandom đúng? — `ThreadLocalRandom.current()` trong thread đang sử dụng.

**4.** Có nên chia sẻ một ThreadLocalRandom object lấy từ main sang workers không? — Không, dùng current trong mỗi worker.

**5.** `nextInt(10)` trả các giá trị nào? — 0..9.

**6.** `nextInt(1,7)` trả những gì? — 1..6.

**7.** Bound của overloaded range được tính ra sao? — Origin inclusive, bound exclusive.

**8.** `nextLong(100,251)` có thể trả 251 không? — Không; tối đa 250.

**9.** `nextDouble()` trả trong khoảng nào? — [0.0,1.0).

**10.** `nextInt(0)` gây gì? — IllegalArgumentException.

**11.** `nextInt(5,5)` có hợp lệ không? — Không, origin không nhỏ hơn bound.

**12.** Vì sao không dùng `Math.abs(nextInt())%n`? — MIN_VALUE và modulo bias.

**13.** Vì sao `max+1` nguy hiểm ở int MAX_VALUE? — Overflow.

**14.** `setSeed` trên ThreadLocalRandom làm gì? — Ném UnsupportedOperationException.

**15.** Muốn test reproducible nên chọn gì? — Seeded Random hoặc SplittableRandom qua RandomGenerator abstraction.

**16.** Java 17 có interface RNG chung nào? — `java.util.random.RandomGenerator`.

**17.** RandomGenerator có luôn thread-safe không? — Không, tùy implementation.

**18.** Vì sao per-thread không phải per-task? — Thread pool tái sử dụng threads cho tasks và scheduling khác giữa lần chạy.

**19.** Muốn replay theo task thì làm sao? — Giao seeded/split generator riêng và giữ thứ tự cấp seeds.

**20.** SplittableRandom có thread-safe để share instance không? — Không; split rồi giao từng child cho task.

**21.** ThreadLocalRandom có bảo đảm các luồng không bao giờ tạo cùng số không? — Không; có thể trùng.

**22.** RNG này dùng cho token bảo mật được không? — Không; dùng SecureRandom.

**23.** `nextDouble()<0.1` bảo đảm đúng 10 mẫu trong 100 không? — Không; đó là xác suất, không quota.

**24.** Jitter giúp gì? — Phân tán thời điểm retry, nhưng còn cần backoff/deadline policy.

**25.** Vì sao không in giá trị random trong stdout kiểm thử cố định? — Chúng có thể khác giữa các lần chạy.

**26.** Ví dụ 4 tasks × 10.000 rolls kiểm tra điều gì? — Tổng 40.000 samples và mọi output thuộc miền [1,7), không benchmark tốc độ.

**27.** Cách tổng hợp kết quả an toàn từ nhiều workers? — Local results và Future.get rồi combine, hoặc primitive đồng bộ phù hợp.

**28.** Test hiệu năng nên so những phương án nào? — Shared Random, per-thread ThreadLocalRandom, per-thread Random, per-task SplittableRandom.

**29.** Điều gì quyết định hiệu quả performance? — Workload, contention, JIT/JDK, CPU, số threads, allocation và downstream bottlenecks.

**30.** Khi nào dùng `ThreadLocalRandom` là lựa chọn tốt? — Nhiều threads cần pseudorandom non-security với API đơn giản, không yêu cầu seeded replay theo task.

## 24. Tài liệu chính thức — Java SE 17

- [ThreadLocalRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): per-thread generator, `current()`, bounded nextInt/nextLong/nextDouble, setSeed unsupported và cảnh báo noncryptographic.
- [Random — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): thread safety, shared instance contention, seed/reproducibility và giới hạn bảo mật.
- [SplittableRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): generator split, sử dụng trong parallel computations và không thread-safe khi dùng chung instance.
- [RandomGenerator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface chung cho pseudorandom generators, thread-safety theo implementation.
- [java.util.random — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): lựa chọn thuật toán RNG hiện hành, thống kê và phân nhóm.
- [SecureRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): CSPRNG cho trường hợp cần tính không thể đoán.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý concurrent tasks, Futures và lifecycle.
- [Future — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion, timeout và truyền kết quả giữa worker/main.

**Ghi nhớ:** `java.util.Random` dùng chung **thread-safe nhưng có thể gây contention** dưới tải nhiều threads. `ThreadLocalRandom.current()` trong **mỗi thread thực thi** giúp tránh một trạng thái generator dùng chung và là lựa chọn đơn giản cho random **không yêu cầu bảo mật**. Dùng bounded APIs với **cận dưới bao gồm, cận trên loại trừ**; không tự setSeed vì sẽ ném UnsupportedOperationException. Khi cần **replay có seed theo task**, inject `RandomGenerator` hoặc dùng `SplittableRandom` riêng cho từng task. Khi cần **bí mật chống dự đoán**, dùng `SecureRandom`. Hiệu năng thật chỉ được kết luận từ benchmark phù hợp, không từ một con số speedup giả định.