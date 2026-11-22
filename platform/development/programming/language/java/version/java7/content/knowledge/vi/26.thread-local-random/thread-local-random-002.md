# Lấy bộ sinh ngẫu nhiên qua ThreadLocalRandom.current() trong Java

**Chủ đề:** Java 7 — ThreadLocalRandom  
**Bài học:** Lấy bộ sinh qua `current`  
**Phiên bản áp dụng:** Java 17+; `java.util.concurrent.ThreadLocalRandom` được giới thiệu từ Java 7 và **vẫn là API hiện hành, được hỗ trợ**. Ngoài API gốc, bài chỉ dùng các API vẫn còn phù hợp trong Java hiện đại, gồm `java.util.random.RandomGenerator` (Java 17), `SplittableRandom` và `SecureRandom` cho mục đích so sánh đúng phạm vi.

## 1. Vấn đề: nhiều luồng cần số ngẫu nhiên mà không tranh chấp một bộ sinh dùng chung

Giả sử có một ứng dụng chạy nhiều worker threads. Mỗi worker cần tạo một giá trị giả ngẫu nhiên để mô phỏng, chọn mẫu, chọn một phần tử trong danh sách hoặc phân bổ một tác vụ thử nghiệm.

Một cách quen thuộc với chương trình nhỏ là tạo một `java.util.Random` rồi mọi luồng cùng gọi:

```java
Random shared = new Random();
int sample = shared.nextInt(100);
```

Đây là **snippet** minh họa, cần import và phạm vi biến thích hợp. `Random` **thread-safe**, nhưng nhiều luồng cùng truy cập một đối tượng `Random` có thể gặp contention và giảm throughput tùy JDK/workload. Đây là vấn đề hiệu năng, **không phải khẳng định `Random` tự động gây data race**.

Java cung cấp `ThreadLocalRandom` để mỗi luồng thực hiện các phép sinh số sử dụng **trạng thái ngẫu nhiên gắn với luồng hiện tại**, thay vì nhiều luồng cùng phải tranh chấp một trạng thái chung.

Cách dùng đúng:

```java
int sample = ThreadLocalRandom.current().nextInt(100);
```

**`ThreadLocalRandom.current()` là trọng tâm của bài.** Phương thức static `current()` trả bộ sinh được dùng trong **ngữ cảnh thread đang gọi**. Bạn không tự khởi tạo bằng `new ThreadLocalRandom()`, không đặt seed thủ công, và không cần tự tạo một `ThreadLocal<Random>` chỉ để có bộ sinh thông thường cho mỗi thread.

### 1.1. Cách hình dung

```text
                      Executor / thread pool
                              |
                +-------------+-------------+
                |             |             |
             Worker A      Worker B      Worker C
                |             |             |
  ThreadLocalRandom.current() ở mỗi worker
                |             |             |
           nextInt()      nextLong()   nextDouble()
                |             |             |
          state của      state của      state của
          thread A       thread B       thread C
```

**Không suy rằng mỗi lần gọi `current()` phải tạo một object mới hoặc mỗi thread nhận một object có identity khác nhau.** Hợp đồng quan trọng là các thao tác lấy số dùng **trạng thái phù hợp với thread hiện tại** và tránh tranh chấp một shared generator state theo thiết kế. Cơ chế/object identity cụ thể là chi tiết triển khai không nên được dùng làm invariant.

### 1.2. Điều gì vẫn đúng trên Java mới?

`ThreadLocalRandom` ra đời từ Java 7 nhưng **không phải API legacy**. Trong Java 17+, nó còn tích hợp với họ giao diện `RandomGenerator`; việc lấy bộ sinh bằng `ThreadLocalRandom.current()` vẫn phù hợp cho nhu cầu ngẫu nhiên **không liên quan bảo mật** trên nhiều threads.

Sự tồn tại của `SplittableRandom`, `RandomGeneratorFactory` hoặc virtual threads không làm `current()` hết giá trị. Chọn công cụ theo yêu cầu về concurrency, khả năng tái lập, bảo mật và đặc điểm thuật toán.

## 2. Khái niệm chính xác: bộ sinh giả ngẫu nhiên và current thread

`ThreadLocalRandom` là **pseudorandom number generator (PRNG)**. Các giá trị tạo ra có tính ngẫu nhiên thống kê phù hợp cho nhiều thao tác mô phỏng/lựa chọn thông thường, nhưng **không được thiết kế để chống dự đoán bởi đối thủ**.

**Thread-local state** nghĩa là luồng đang thực thi phương thức sinh số có trạng thái riêng phục vụ thao tác đó. Điều này giúp tránh bottleneck khi nhiều luồng phải update cùng một biến seed chung.

### 2.1. Từ khóa current có nghĩa gì?

`current()` là một **static method**:

```java
public static ThreadLocalRandom current();
```

Đây là **chữ ký API rút gọn**, không phải file Java độc lập. Nó được gọi ở nơi computation đang chạy:

```java
ThreadLocalRandom random = ThreadLocalRandom.current();
int value = random.nextInt(10);
```

Hai bước có thể rút thành một dòng:

```java
int value = ThreadLocalRandom.current().nextInt(10);
```

**Không gọi `new ThreadLocalRandom()`:** constructor không được cung cấp để client khởi tạo trực tiếp. **Không cần `synchronized` quanh `current()`** trong mã ứng dụng để ngăn các luồng tranh chấp random state; mục tiêu của class chính là xử lý tình huống đa luồng này.

### 2.2. Khi gọi current trong executor

Hãy hình dung main tạo 3 jobs, submit vào một executor:

```text
Main thread:
   submit(job1), submit(job2), submit(job3)

Executor:
   worker-1 runs job1 -> ThreadLocalRandom.current()
   worker-2 runs job2 -> ThreadLocalRandom.current()
   worker-3 runs job3 -> ThreadLocalRandom.current()
```

Mỗi job nên lấy generator **bên trong thân job**, không lấy một generator ở main rồi chuyền qua job và coi đó là một “nguồn ngẫu nhiên được seed riêng cho job”.

Thực tế API `ThreadLocalRandom` dựa vào current executing thread, nên **không thể dùng identity của generator để xác định task/thread nào đang sở hữu seed**. Nếu task di chuyển giữa workers, việc lấy `current()` trong phần code thực thi là cách diễn đạt rõ ràng nhất.

### 2.3. Không nhầm thread-local với task-local

**Thread-local ≠ task-local**. Thread pool thường **tái sử dụng worker threads**. Hai tasks chạy nối tiếp trên cùng worker có thể dùng trạng thái giả ngẫu nhiên của cùng thread, chứ không tự có một chuỗi seed độc lập theo task ID.

Nếu thuật toán yêu cầu **một PRNG độc lập, có seed định trước cho mỗi task**, hãy sử dụng một `RandomGenerator` được tạo/inject theo task (ví dụ `SplittableRandom` với seed dẫn xuất được quản lý), **không** mặc định `ThreadLocalRandom.current()` cung cấp reproducibility theo task.

## 3. Chương trình cơ bản: lấy current rồi sinh int, long, double

Tạo file `CurrentBasicsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class CurrentBasicsDemo {
  public static void main(String[] args) {
    ThreadLocalRandom generator = ThreadLocalRandom.current();
    int number = generator.nextInt(10, 20);
    long stamp = generator.nextLong(1_000L, 2_000L);
    double fraction = generator.nextDouble(0.0, 1.0);
    System.out.println("current-present=" + (ThreadLocalRandom.current() != null));
    System.out.println("int-in-range=" + (number >= 10 && number < 20));
    System.out.println("long-in-range=" + (stamp >= 1_000L && stamp < 2_000L));
    System.out.println("double-in-range=" + (fraction >= 0.0 && fraction < 1.0));
  }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 -Xlint:all CurrentBasicsDemo.java
java CurrentBasicsDemo
```

**stdout đã kiểm thử:**

```text
current-present=true
int-in-range=true
long-in-range=true
double-in-range=true
```

### 3.1. Vì sao không in các số ngẫu nhiên cụ thể?

Các số `number`, `stamp` và `fraction` được PRNG tạo ra mỗi lần chạy. Nếu README ghi “lần nào cũng in 17”, đó là **mô tả không đúng về hành vi của `ThreadLocalRandom`**.

Bài kiểm thử chỉ in **những thuộc tính API bảo đảm**: tồn tại generator và mọi số nằm đúng range. Vì vậy stdout vẫn xác định trong mỗi lần chạy hợp lệ dù các số thực tế khác nhau.

### 3.2. Một lần gọi current hay gọi lại nhiều lần?

Cả hai phong cách đều hợp lệ:

```java
// Dùng một tham chiếu cục bộ trong cùng worker.
ThreadLocalRandom rng = ThreadLocalRandom.current();
int left = rng.nextInt(100);
int right = rng.nextInt(100);

// Hoặc lấy ngay tại callsite.
int third = ThreadLocalRandom.current().nextInt(100);
```

Đây là snippet. **Không cần cache thành một static field dùng chung rồi tin rằng nó là “một PRNG có một seed kiểm soát được”**. Khai báo tham chiếu cục bộ trong method/lambda chạy trên worker giúp người đọc hiểu rõ nơi lấy bộ sinh.

`current()` có thể được gọi nhiều lần; không có lý do để dùng một khóa ứng dụng chỉ để bảo vệ việc gọi method này.

## 4. Quy tắc khoảng giá trị: origin inclusive, bound exclusive

Đây là nhóm lỗi quan trọng nhất khi dùng `current()`.

Với những overload có khoảng:

```java
int n = ThreadLocalRandom.current().nextInt(origin, bound);
```

Kết quả nằm trong **[origin, bound)**, tức là:

- **`origin` được phép xuất hiện**.
- **`bound` không bao giờ là giá trị kết quả**.
- Phải có **`origin < bound`**, nếu không sẽ ném `IllegalArgumentException`.

Các dạng điển hình:

| Lời gọi | Khoảng hợp lệ | Ứng dụng |
| --- | --- | --- |
| `nextInt()` | Toàn bộ miền `int` | Số nguyên giả ngẫu nhiên không đặt giới hạn |
| `nextInt(bound)` | `[0, bound)` | Chỉ số list/array khi bound = size |
| `nextInt(origin, bound)` | `[origin, bound)` | Khoảng có cận dưới khác 0 |
| `nextLong()` | Toàn miền `long` | Số nguyên 64-bit |
| `nextLong(bound)` | `[0, bound)` | Số lượng lớn hơn `int` |
| `nextLong(origin, bound)` | `[origin, bound)` | Khoảng long tùy chọn |
| `nextDouble()` | `[0.0, 1.0)` | Xác suất mô phỏng |
| `nextDouble(bound)` | `[0.0, bound)` | Thang liên tục bắt đầu 0 |
| `nextDouble(origin, bound)` | `[origin, bound)` | Khoảng double |
| `nextBoolean()` | `true` hoặc `false` | Một sự kiện kiểu boolean |
| `nextFloat()` | `[0.0f, 1.0f)` | Mẫu float khi thích hợp |

Khi viết bài/thiết kế API, nhớ rằng `bound` là **exclusive**. Muốn một con xúc xắc 1–6:

```java
int dice = ThreadLocalRandom.current().nextInt(1, 7);
```

Không viết `nextInt(1, 6)` nếu muốn cả 6. Không viết `nextInt(6) + 1` là sai — cách đó **cũng đúng** cho 1–6, nhưng overload hai cận nói rõ intent hơn và giảm phép tính tự chế.

### 4.1. Khoảng một phần tử

`nextInt(5, 6)` luôn trả 5; `nextLong(100L, 101L)` luôn trả 100, vì chỉ có một giá trị nguyên trong nửa-khoảng.

`nextInt(3, 3)` không tạo một tập rỗng rồi trả giá trị đặc biệt. Nó ném `IllegalArgumentException` vì origin không nhỏ hơn bound.

### 4.2. Đừng dùng phép % để ép random vào khoảng

Anti-pattern:

```java
int chosen = Math.abs(ThreadLocalRandom.current().nextInt()) % size;
```

Đây là snippet có lỗi. `Math.abs(Integer.MIN_VALUE)` vẫn **âm** (do overflow của `int`), và phép `% size` có thể dẫn tới thiên lệch modulo. Nếu `size==0`, còn có lỗi chia cho 0. Cách đúng:

```java
if (size <= 0) {
    throw new IllegalArgumentException("size must be positive");
}
int chosen = ThreadLocalRandom.current().nextInt(size);
```

Đây là snippet được dùng trong method có `size` hợp lệ. `nextInt(size)` cung cấp bounded random theo đúng API, không cần tự cân bằng các giá trị modulo.

### 4.3. Không tính bound+1 vô điều kiện

Muốn sinh số nguyên trong đoạn **đóng** `[min,max]`, một mẹo phổ biến là `nextInt(min,max+1)`. **Cẩn thận:** nếu `max==Integer.MAX_VALUE`, `max+1` tràn và range bị sai. Khi phạm vi có thể chạm cực trị, dùng cách chuyên biệt có validation và kiểu số rộng hơn nếu cần; hoặc thiết kế API trực tiếp theo **[min,maxExclusive)**.

**Khuyến nghị:** định nghĩa input domain theo half-open interval ngay từ đầu; tránh tự làm arithmetic trên cận cực trị nếu không chứng minh được an toàn.

## 5. Ví dụ kiểm tra ranh giới và những tham số sai

Tạo file `CurrentBoundsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class CurrentBoundsDemo {
  public static void main(String[] args) {
    ThreadLocalRandom r = ThreadLocalRandom.current();
    System.out.println("single-int=" + r.nextInt(5, 6));
    System.out.println("single-long=" + r.nextLong(100L, 101L));
    int errors = 0;
    try { r.nextInt(3, 3); } catch (IllegalArgumentException ex) { errors++; }
    try { r.nextLong(9L, 8L); } catch (IllegalArgumentException ex) { errors++; }
    try { r.nextDouble(1.0, 1.0); } catch (IllegalArgumentException ex) { errors++; }
    try { r.nextInt(0); } catch (IllegalArgumentException ex) { errors++; }
    System.out.println("invalid-ranges-rejected=" + errors);
    System.out.println("abs-min-still-negative=" + (Math.abs(Integer.MIN_VALUE) < 0));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentBoundsDemo.java
java CurrentBoundsDemo
```

**stdout đã kiểm thử:**

```text
single-int=5
single-long=100
invalid-ranges-rejected=4
abs-min-still-negative=true
```

Kết quả minh họa:

1. Range [5,6) của `int` chỉ có 5.
2. Range [100,101) của `long` chỉ có 100.
3. Bốn lời gọi có origin/bound không hợp lệ bị từ chối, không trả “một số đoán chừng”.
4. `Math.abs(Integer.MIN_VALUE)` không tạo số không âm như nhiều người tưởng; đừng dùng cách đó để lấy list index.

### 5.1. Validating bounds trước khi gọi current

`ThreadLocalRandom.current()` tự có thể trả generator hợp lệ; **nhưng nó không tự hợp lệ hóa các giới hạn nghiệp vụ**. Nếu bounds đến từ HTTP request, database hoặc file cấu hình, kiểm tra:

- `min < maxExclusive` và cùng đơn vị.
- List không rỗng trước `nextInt(list.size())`.
- Bound không bị overflow khi tính từ `maxInclusive`.
- Với `double`, tránh NaN, infinity hoặc range vô nghĩa đối với nghiệp vụ.
- Không dùng một mẫu random để bỏ qua authentication/authorization kiểm soát tài nguyên.

### 5.2. Phân biệt kiểm tra input với kiểm tra output

Nếu một hàm trả về int trong [10,20), điều kiện kiểm tra đúng là:

```java
boolean valid = sample >= 10 && sample < 20;
```

Đây là snippet, `sample` là kết quả sinh. Đừng viết `sample <= 20` rồi kết luận range đúng; 20 là **bound exclusive**, dù kết quả 20 hiếm đến mức không bao giờ được tạo bởi API hợp lệ.

## 6. Thread pool: lấy current **bên trong** mỗi task

Với ứng dụng thực, luồng được quản lý bởi `ExecutorService` chứ không phải tự tạo một thread cho từng sample. Pattern chuẩn:

```java
executor.submit(() -> {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    int sample = rng.nextInt(100);
    // Dùng sample tại worker này.
});
```

Đây là snippet. Điều đặc biệt là lời gọi `current()` **nằm trong lambda được executor thực thi**, chứ không ở main trước khi submit.

### 6.1. Ví dụ runnable: ba worker tạo số trong range

Tạo file `CurrentWorkerTasksDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class CurrentWorkerTasksDemo {
  public static void main(String[] args) throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(3);
    try {
      List<Callable<Boolean>> tasks = new ArrayList<>();
      for (int worker = 0; worker < 3; worker++) {
        tasks.add(() -> {
          ThreadLocalRandom local = ThreadLocalRandom.current();
          for (int j = 0; j < 1000; j++) {
            int sample = local.nextInt(-100, 100);
            if (sample < -100 || sample >= 100) return false;
          }
          return true;
        });
      }
      List<Future<Boolean>> results = pool.invokeAll(tasks, 5, TimeUnit.SECONDS);
      int passed = 0;
      for (Future<Boolean> future : results) if (future.get()) passed++;
      System.out.println("workers=" + results.size());
      System.out.println("passed=" + passed);
      System.out.println("all-passed=" + (passed == 3));
    } finally {
      pool.shutdownNow();
      pool.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentWorkerTasksDemo.java
java CurrentWorkerTasksDemo
```

**stdout đã kiểm thử:**

```text
workers=3
passed=3
all-passed=true
```

**Giải thích:**

- Main tạo 3 `Callable<Boolean>` rồi gửi cho pool.
- Mỗi callable **tự lấy `ThreadLocalRandom.current()`** trong worker chạy nó.
- Mỗi job thử 1.000 mẫu trong `[-100,100)`, chỉ trả true nếu **mọi** mẫu nằm trong range.
- Main dùng `invokeAll(tasks,5,SECONDS)` của `ExecutorService` để có deadline cho cả batch; `Future.get` nhận boolean.
- Không in mẫu ngẫu nhiên cụ thể nên kết quả kiểm thử ổn định.
- `finally` shutdown executor, không để worker threads sống vô hạn sau demo.

**Lưu ý:** `pool.invokeAll` là API của `ExecutorService`, không phải `ThreadLocalRandom`. Nó chỉ dùng để minh họa chạy jobs trên nhiều threads; không thay đổi semantics của `current()`.

### 6.2. Có cần tạo một Random mới trong mỗi task không?

Không cần nếu chỉ cần pseudorandom nhanh, không yêu cầu seed tái lập theo task. Gọi `current()` trong worker dễ đọc và không phải xây một `Random`/`SplittableRandom` mới theo mỗi request.

**Nhưng** nếu test yêu cầu mỗi task có một sequence cố định theo task ID, `ThreadLocalRandom` không đủ; dùng dependency-injected `RandomGenerator` có seed được quyết định bởi test/configuration.

### 6.3. Không khẳng định luôn có ba threads chạy cùng lúc

`newFixedThreadPool(3)` có mức worker tối đa phù hợp, nhưng task thực tế có thể kết thúc trước khi cả ba worker cùng active. `current()` không cam kết số threads, thứ tự chạy hoặc một sequence giá trị riêng mà bạn có thể dự đoán.

Test correctness dựa trên **mỗi sample nằm trong range**, không dựa vào thread name hoặc lịch worker.

## 7. ThreadLocalRandom.current() không cho đặt seed thủ công

Đây là ranh giới quan trọng cho kiểm thử và replay.

`ThreadLocalRandom.current()` quản lý trạng thái seed của luồng theo runtime. Phương thức `setSeed(long)` được kế thừa từ `Random` nhưng **ném `UnsupportedOperationException` khi caller cố đặt lại seed** sau khi generator được khởi tạo.

**Không dùng**:

```java
ThreadLocalRandom.current().setSeed(12345L); // UnsupportedOperationException
```

Đây là snippet có hành vi ném lỗi có chủ đích, **không** phải cách cấu hình reproducibility.

Java cũng có `new Random(seed)` và `new SplittableRandom(seed)` dùng cho nhu cầu test/simulation có seed. `SplittableRandom` hữu ích cho tính toán chia nhánh, nhưng một instance **không nên được dùng đồng thời bởi nhiều threads**; nếu song song, tạo/split các generator theo quy tắc ownership.

### 7.1. Ví dụ runnable: cố setSeed và dùng generator có seed

Tạo file `CurrentSeedDemo.java`:

```java
import java.util.Random;
import java.util.SplittableRandom;
import java.util.concurrent.ThreadLocalRandom;
public class CurrentSeedDemo {
  public static void main(String[] args) {
    boolean rejected = false;
    try { ThreadLocalRandom.current().setSeed(42L); }
    catch (UnsupportedOperationException ex) { rejected = true; }
    Random a = new Random(12345L);
    Random b = new Random(12345L);
    boolean sameRandom = true;
    for (int i = 0; i < 10; i++) sameRandom &= a.nextInt() == b.nextInt();
    SplittableRandom s1 = new SplittableRandom(2026L);
    SplittableRandom s2 = new SplittableRandom(2026L);
    boolean sameSplit = true;
    for (int i = 0; i < 10; i++) sameSplit &= s1.nextLong() == s2.nextLong();
    System.out.println("thread-local-set-seed-rejected=" + rejected);
    System.out.println("seeded-random-repeatable=" + sameRandom);
    System.out.println("seeded-splittable-repeatable=" + sameSplit);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentSeedDemo.java
java CurrentSeedDemo
```

**stdout đã kiểm thử:**

```text
thread-local-set-seed-rejected=true
seeded-random-repeatable=true
seeded-splittable-repeatable=true
```

**Điểm chính:**

- `ThreadLocalRandom.setSeed` bị từ chối bằng exception như API quy định.
- Hai `Random` có cùng seed tạo cùng chuỗi đầu ra cho cùng các calls trong ví dụ.
- Hai `SplittableRandom` có cùng seed cũng tạo chuỗi giống nhau trong môi trường kiểm thử.
- **Đây là tính tái lập của seeded generators**, không phải kết luận `ThreadLocalRandom` có thể được seed hoặc sẽ xuất cùng chuỗi giữa hai lần chạy.

### 7.2. Vì sao seed của ThreadLocalRandom không phải input test?

Trong ứng dụng song song, thứ tự tasks đến worker là không xác định; thậm chí một worker có thể thực thi nhiều tasks theo những lịch khác nhau. Vì vậy “đặt cùng seed cho tất cả threads” không tự động tạo reproducible output theo task.

Để replay:

1. Quy định seed ở cấp job/task.
2. Tạo một generator có seed cho **mỗi task hoặc mỗi partition**, không trộn state giữa tasks.
3. Tránh phụ thuộc thứ tự worker scheduling.
4. Lưu seed, algorithm/config version nếu cần tái lập dài hạn.
5. Kiểm thử các giá trị thuộc tính bằng property-based assertions thay vì hard-code ngẫu nhiên production vào stdout.

### 7.3. Tính xác định ≠ tính bảo mật

`Random(seed)` hoặc `SplittableRandom(seed)` có thể tái tạo các chuỗi giả ngẫu nhiên, thích hợp cho simulations/test. Chính khả năng tái tạo và thiết kế PRNG làm chúng **không thích hợp để tạo bí mật bảo mật**. `ThreadLocalRandom` cũng **không thích hợp cho security-sensitive randomness** chỉ vì không cho bạn đặt seed.

## 8. Lấy mẫu phần tử trong danh sách bằng current()

Một tình huống quen thuộc là chọn một phần tử bất kỳ trong danh sách ứng viên.

**Cách đúng:** xác nhận danh sách không rỗng rồi sinh index trong `[0,size)`.

```java
int index = ThreadLocalRandom.current().nextInt(items.size());
T selected = items.get(index);
```

Đây là snippet dạng generic, cần `items` và `T` trong method phù hợp.

### 8.1. Ví dụ runnable: chọn ứng viên và tung xúc xắc

Tạo file `CurrentChoiceDemo.java`:

```java
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;
public class CurrentChoiceDemo {
  static <T> T choose(List<T> items) {
    if (items.isEmpty()) throw new IllegalArgumentException("empty candidates");
    return items.get(ThreadLocalRandom.current().nextInt(items.size()));
  }
  public static void main(String[] args) {
    List<String> names = List.of("An", "Binh", "Chi");
    String selected = choose(names);
    System.out.println("choice-valid=" + names.contains(selected));
    boolean rejected = false;
    try { choose(List.of()); } catch (IllegalArgumentException ex) { rejected = true; }
    System.out.println("empty-rejected=" + rejected);
    int dice = ThreadLocalRandom.current().nextInt(1, 7);
    System.out.println("dice-valid=" + (dice >= 1 && dice <= 6));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentChoiceDemo.java
java CurrentChoiceDemo
```

**stdout đã kiểm thử:**

```text
choice-valid=true
empty-rejected=true
dice-valid=true
```

**Đọc output:** bài không hứa ứng viên được chọn luôn là “An”, vì đó là số ngẫu nhiên; chỉ xác nhận ứng viên nằm trong danh sách. Với list rỗng, `nextInt(0)` sẽ invalid, nên helper trả `IllegalArgumentException` sớm và rõ ràng hơn.

### 8.2. Chọn một phần tử không giống xáo trộn không lặp

`items.get(nextInt(items.size()))` chọn mẫu **có thay thế** nếu gọi nhiều lần. Có thể chọn cùng một phần tử nhiều lần. Nếu cần chọn N phần tử **không trùng**, cần một thuật toán khác:

- Shuffle danh sách có copy thích hợp rồi lấy N items đầu, hoặc
- Reservoir sampling khi dữ liệu lớn/dạng stream, hoặc
- Dùng một cấu trúc tracking các items đã chọn.

**Không** viết vòng lặp retry chọn random cho đến khi đủ phần tử độc nhất nếu N gần bằng số ứng viên mà không xét chi phí và điều kiện dừng.

### 8.3. Lựa chọn ngẫu nhiên không tự động là công bằng nghiệp vụ

`nextInt(size)` giúp sinh index giả ngẫu nhiên hợp lệ; nhưng nếu danh sách nguồn có phần tử trùng lặp/độ ưu tiên không đồng đều, xác suất chọn theo **đơn vị list entry** khác xác suất chọn theo **người dùng thực**.

Nếu dùng để phân bổ phần thưởng/quyền lợi có yêu cầu minh bạch, cần định nghĩa chính sách chọn mẫu, kiểm tra bias của dữ liệu đầu vào và sử dụng RNG đúng cấp độ bảo mật khi có giá trị chống gian lận.

## 9. Parallel stream: lấy current ở worker thực thi lambda

Một `IntStream.parallel()` có thể thực hiện các phần của pipeline trên nhiều worker threads. Nếu muốn mỗi phần tử được lấy random trong thread thực sự xử lý nó, cách rõ ràng là gọi `current()` **bên trong lambda**:

```java
IntStream.range(0, 1_000)
    .parallel()
    .map(i -> ThreadLocalRandom.current().nextInt(100))
    .toArray();
```

Đây là snippet, cần import `IntStream` và sử dụng kết quả.

**Tránh** lấy một tham chiếu tại main, capture nó vào lambda, rồi tưởng rằng generator đã được gắn seed theo từng task. `ThreadLocalRandom` được thiết kế theo context của thread gọi, và việc gọi tại nơi chạy lambda thể hiện rõ hợp đồng. Nếu cần reproducible parallel simulation, mỗi logical task cần generator seeded riêng, thay vì lấy seed theo worker scheduling.

### 9.1. Ví dụ runnable: 2.000 phần tử, tất cả trong [100,200)

Tạo file `CurrentParallelStreamDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.IntStream;
public class CurrentParallelStreamDemo {
  public static void main(String[] args) {
    long valid = IntStream.range(0, 2_000).parallel()
        .map(index -> ThreadLocalRandom.current().nextInt(100, 200))
        .filter(value -> value >= 100 && value < 200)
        .count();
    System.out.println("count=" + valid);
    System.out.println("all-in-range=" + (valid == 2_000));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentParallelStreamDemo.java
java CurrentParallelStreamDemo
```

**stdout đã kiểm thử:**

```text
count=2000
all-in-range=true
```

Mỗi input position được chuyển thành một số trong [100,200), rồi filter giữ các số hợp lệ. Vì **tất cả** samples do API sinh trong miền đó, count vẫn là 2.000.

**Đây không phải benchmark** chứng minh parallel nhanh hơn sequential. Pipeline rất nhỏ có thể chậm hơn vì overhead của parallel execution. Khi xử lý thực tế, chọn parallel stream chỉ khi dữ liệu/cost phù hợp; `ThreadLocalRandom` giúp tránh shared-generator contention nhưng không tự giải quyết mọi bottleneck.

### 9.2. Không lạm dụng parallel stream để tạo ngẫu nhiên một cách phức tạp

Nếu chỉ cần một số, dùng `ThreadLocalRandom.current().nextInt(...)` trực tiếp. Tạo parallel stream để sinh một giá trị làm tăng độ phức tạp vô ích. Với một simulation nhiều phần tử, hãy cân nhắc:

- Mức CPU-bound thực sự của công việc.
- Tính tái lập theo test seed.
- Chi phí tạo/thu collect dữ liệu.
- Thứ tự kết quả có quan trọng không.
- Hạn mức threads của executor/common pool.
- Liệu pipeline có gọi blocking I/O không.

## 10. Java 17 RandomGenerator: giữ logic thuật toán độc lập bộ sinh

Java 17 cung cấp interface `java.util.random.RandomGenerator` để diễn đạt một abstraction chung cho nhiều pseudorandom algorithms. `ThreadLocalRandom` có thể được dùng qua interface này:

```java
RandomGenerator rng = ThreadLocalRandom.current();
int roll = rng.nextInt(1, 7);
```

Đây là snippet cần imports. Tách interface khỏi implementation giúp test dễ dàng:

- **Production thông thường:** inject `ThreadLocalRandom.current()` ngay trong worker hoặc gọi trực tiếp ở helper.
- **Test cần tái lập:** truyền một `SplittableRandom(seed)` hoặc `Random(seed)` có owner rõ ràng.
- **Simulation theo partition:** quản lý generator riêng cho từng partition, tránh dùng một mutable generator không thread-safe ở nhiều threads.
- **Bảo mật:** chuyển sang `SecureRandom` và protocol phù hợp khi kết quả phải khó dự đoán.

### 10.1. Ví dụ runnable: inject RandomGenerator để test lặp lại được

Tạo file `CurrentInjectedGeneratorDemo.java`:

```java
import java.util.SplittableRandom;
import java.util.concurrent.ThreadLocalRandom;
import java.util.random.RandomGenerator;
import java.util.stream.IntStream;
public class CurrentInjectedGeneratorDemo {
  static int roll(RandomGenerator generator) {
    return generator.nextInt(1, 7);
  }
  public static void main(String[] args) {
    RandomGenerator a = new SplittableRandom(42L);
    RandomGenerator b = new SplittableRandom(42L);
    int[] first = IntStream.range(0, 20).map(i -> roll(a)).toArray();
    int[] second = IntStream.range(0, 20).map(i -> roll(b)).toArray();
    boolean matches = java.util.Arrays.equals(first, second);
    int live = roll(ThreadLocalRandom.current());
    System.out.println("repeatable-test=" + matches);
    System.out.println("real-dice-valid=" + (live >= 1 && live <= 6));
    System.out.println("test-sample-count=" + first.length);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentInjectedGeneratorDemo.java
java CurrentInjectedGeneratorDemo
```

**stdout đã kiểm thử:**

```text
repeatable-test=true
real-dice-valid=true
test-sample-count=20
```

### 10.2. Vì sao helper nhận RandomGenerator là thiết kế tốt?

`roll(RandomGenerator generator)` có logic miền giá trị độc lập với lớp cụ thể. Trong test, hai `SplittableRandom` nhận cùng seed, gọi cùng thứ tự, nên 20 phần tử tạo ra giống nhau; trong production, `ThreadLocalRandom.current()` cung cấp random phục vụ worker hiện tại.

**Không hiểu rằng mọi RandomGenerator đều tự thread-safe.** Interface không tự ban cho implementation một chính sách synchronization giống nhau. `SplittableRandom` phù hợp khi sử dụng độc quyền mỗi thread/task hoặc phân nhánh bằng `split`; nếu nhiều threads cùng dùng một mutable instance không được thiết kế thread-safe, có thể tạo race.

### 10.3. Lưu ý khi test deterministic

Một bài test có thể xác nhận:

- Với seeded generator, cùng seed và cùng thuật toán/calls sẽ tạo chuỗi như mong đợi trong môi trường được kiểm soát.
- Mọi số xúc xắc nằm trong 1..6.
- Không có ngoại lệ cho valid range.
- Các input không hợp lệ được báo đúng.

Với `ThreadLocalRandom.current()`, **không** nên assert chuỗi cụ thể như [3,2,1,6] giữa các lần chạy hoặc giữa các threads. Nếu muốn kiểm tra xác suất, phải dùng statistical testing với sample size, confidence/tolerance, tránh assert một biến cố may rủi trong unit test.

## 11. Khi nào phải dùng SecureRandom thay vì current?

**Không bao giờ dùng `ThreadLocalRandom` để tạo bí mật phải khó đoán** như:

- Password reset tokens.
- Session secrets/bearer tokens.
- API keys/OTP không được phép dễ dự đoán.
- CSRF secrets nếu thiết kế yêu cầu unpredictability.
- Khóa mã hóa, nonce có yêu cầu mật mã.
- Tham số auth hoặc phần thưởng có nguy cơ bị đối thủ dự đoán/gian lận.

`ThreadLocalRandom` tối ưu cho **non-security** workloads, không phải cryptographically secure RNG (CSPRNG). Việc trạng thái seed không cho người dùng tự set không đồng nghĩa attacker không thể dự đoán đầu ra theo mô hình an toàn mật mã.

Chọn `java.security.SecureRandom` khi cần entropy/cryptographic unpredictability, và chọn định dạng/độ dài token theo mức bảo mật/threat model. Không tự viết PRNG bảo mật dựa trên `current().nextLong()`.

### 11.1. Ví dụ runnable: fast simulation RNG và SecureRandom

Tạo file `CurrentSecureRandomDemo.java`:

```java
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.concurrent.ThreadLocalRandom;
import java.util.random.RandomGenerator;
public class CurrentSecureRandomDemo {
  public static void main(String[] args) {
    RandomGenerator simulation = ThreadLocalRandom.current();
    int sample = simulation.nextInt(100);
    SecureRandom secure = new SecureRandom();
    byte[] secret = new byte[16];
    secure.nextBytes(secret);
    String hex = HexFormat.of().formatHex(secret);
    System.out.println("simulation-sample-valid=" + (sample >= 0 && sample < 100));
    System.out.println("secure-token-bytes=" + secret.length);
    System.out.println("secure-hex-length=" + hex.length());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentSecureRandomDemo.java
java CurrentSecureRandomDemo
```

**stdout đã kiểm thử:**

```text
simulation-sample-valid=true
secure-token-bytes=16
secure-hex-length=32
```

Phân tích:

- `simulation.nextInt(100)` tạo số giả ngẫu nhiên thông thường dùng cho simulation.
- `SecureRandom.nextBytes(secret)` điền 16 bytes ngẫu nhiên thích hợp hơn cho mục đích bảo mật.
- 16 bytes chuyển sang **hex** có 32 ký tự vì mỗi byte thành 2 ký tự hex.
- Bài **không in token thật** ra stdout, tránh đưa các bytes bí mật vào logs; chỉ in chiều dài.
- Việc dùng 16 bytes trong ví dụ là minh họa encoding, **không phải policy bảo mật áp dụng mọi hệ thống**. Chọn số bytes theo entropy/guess resistance và yêu cầu nghiệp vụ.

**Đừng chọn RNG chỉ theo tốc độ.** Đối với key/token, security requirement có ưu tiên cao hơn throughput của một bounded number generator.

### 11.2. Randomness tốt không làm thay thế authorization

Ngay cả token từ `SecureRandom` vẫn cần expiration, secure transport/storage, scope, replay controls và auditing phù hợp. Ngược lại, một `ThreadLocalRandom` number không nên dùng như authorization secret chỉ vì range rất lớn.

## 12. Đếm thống kê trong nhiều tasks: giữ kết quả local trước khi gộp

Một lỗi dễ xảy ra trong simulation đa luồng là mọi worker cùng sửa một array counters:

```java
counts[ThreadLocalRandom.current().nextInt(4)]++;
```

Đây là snippet anti-pattern **nếu nhiều threads đồng thời chạy trên cùng `counts[]`**. Phép `++` không atomic; có thể mất cập nhật dù random generator là thread-friendly.

**ThreadLocalRandom giải quyết contention của PRNG, không giải quyết data races của dữ liệu ứng dụng.** Giải pháp thường đơn giản là mỗi worker giữ `long[] localCounts` riêng rồi main gộp sau khi tasks thành công.

### 12.1. Ví dụ runnable: 4 workers, 4 buckets, không shared writes

Tạo file `CurrentLocalAggregationDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class CurrentLocalAggregationDemo {
  public static void main(String[] args) throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    try {
      List<Callable<long[]>> tasks = new ArrayList<>();
      for (int worker = 0; worker < 4; worker++) {
        tasks.add(() -> {
          long[] local = new long[4];
          ThreadLocalRandom rng = ThreadLocalRandom.current();
          for (int sample = 0; sample < 1_000; sample++) local[rng.nextInt(4)]++;
          return local;
        });
      }
      long[] combined = new long[4];
      for (Future<long[]> f : pool.invokeAll(tasks, 5, TimeUnit.SECONDS)) {
        long[] local = f.get();
        for (int bucket = 0; bucket < 4; bucket++) combined[bucket] += local[bucket];
      }
      long total = 0;
      for (long amount : combined) total += amount;
      System.out.println("buckets=" + combined.length);
      System.out.println("samples=" + total);
      System.out.println("no-shared-counter=" + (total == 4_000));
    } finally {
      pool.shutdownNow();
      pool.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CurrentLocalAggregationDemo.java
java CurrentLocalAggregationDemo
```

**stdout đã kiểm thử:**

```text
buckets=4
samples=4000
no-shared-counter=true
```

### 12.2. Vì sao tổng luôn 4.000?

Bốn tasks, mỗi task tạo đúng **1.000** mẫu. Mỗi mẫu được gán vào **một** bucket 0..3 trong một **array cục bộ** của worker. Vì thế, không phụ thuộc mẫu ngẫu nhiên nào xuất hiện, tổng bốn buckets của một worker luôn là 1.000; tổng bốn workers luôn 4.000.

Các bucket counts **riêng lẻ không cố định**; chương trình không in chúng và không assert “mỗi bucket đúng 1000”. Uniform random **không bảo đảm** mọi sample batch nhỏ có số lượng cân bằng tuyệt đối.

### 12.3. Định nghĩa “không shared counter” ở đây

Mỗi task trả `long[]` local, và main gộp **sau khi Future hoàn tất**. Các arrays không bị nhiều threads sửa đồng thời. Chỉ kết quả đã hoàn thành được đưa về main. Tính an toàn đến từ **ownership + synchronization của Future**, không phải từ việc `ThreadLocalRandom` tự “đồng bộ cả chương trình”.

## 13. So sánh các bộ sinh hiện hành

| API | Mục tiêu | Khả năng tái lập bằng seed | Lưu ý về concurrency | Dùng cho bí mật? |
| --- | --- | --- | --- | --- |
| `ThreadLocalRandom.current()` | Tạo nonsecure pseudorandom nhanh trong các worker threads | **Không cho setSeed thủ công** | Trạng thái phù hợp current thread, giảm contention | **Không** |
| `new Random(seed)` | Logic đơn giản, test có seed | **Có** | Instances thread-safe; shared instance có thể contention | **Không** |
| `new SplittableRandom(seed)` | Mô phỏng/chia nhánh độc lập, test có seed | **Có** | Không chia sẻ cùng instance giữa threads; có `split` | **Không** |
| `RandomGenerator` (interface) | Tách logic sử dụng RNG khỏi implementation | Tùy implementation | Không có một chính sách thread safety chung cho mọi implementation | Tùy algorithm, không tự bảo đảm |
| `RandomGeneratorFactory` | Chọn các thuật toán PRNG được cung cấp bởi JDK | Phụ thuộc algorithm và cách create | Phụ thuộc generator được tạo | Không tự đảm bảo crypto security |
| `SecureRandom` | Randomness dùng cho cryptographic/security-sensitive workloads | Có cơ chế seed nhưng không nên dùng như test PRNG tùy tiện | Thiết kế riêng, tùy implementation/provider | **Có, khi dùng đúng** |
| `Math.random()` | Số double tiện dụng `[0,1)` trong code rất nhỏ | Không có seed injection qua callsite | Không cho kiểm soát current-thread RNG rõ như `ThreadLocalRandom` | **Không** |

**Đừng kết luận rằng `Random` “không thread-safe”**: JavaDoc xác nhận instances của `Random` thread-safe; vấn đề chủ yếu là contention của shared instance trong concurrency và việc test seed requirements khác nhau. `ThreadLocalRandom` là lựa chọn được tài liệu Java khuyên cân nhắc cho multi-thread designs cần giảm contention.

### 13.1. Khi cần tái lập mà vẫn chạy song song

Ví dụ một tính toán có 100 partitions cần kết quả giống nhau dù số workers thay đổi. Nếu mỗi worker lấy `ThreadLocalRandom.current()`, thứ tự partitions được xử lý có thể thay đổi nên sequences không còn gắn với partition cố định.

Giải pháp: gán mỗi partition một seed theo một hàm deterministic của job seed và partition ID, tạo generator độc quyền cho partition đó; đảm bảo hàm dẫn xuất seed được thiết kế tránh va chạm/hai partitions cùng chuỗi khi chất lượng simulation quan trọng. Không dùng cùng một `SplittableRandom` mutable instance ở nhiều threads.

### 13.2. Có nên viết static final ThreadLocalRandom SHARED?

**Không cần.** Dù implementation có thể cho phép lời gọi vận hành theo trạng thái của current thread, một static field có tên `SHARED` dễ đánh lừa người đọc rằng đây là **một** generator thông thường có seed được kiểm soát trong object. Viết `ThreadLocalRandom.current()` tại nơi dùng giúp truyền đạt rõ semantics và không phụ thuộc vào object identity.

**Lưu ý:** nói “đừng chia sẻ tham chiếu” là hướng dẫn readability/ownership, không phải khẳng định mọi thao tác thông qua tham chiếu đó chắc chắn bị data race. API được thiết kế theo thread-local state; không tự tạo invariant về generator object identity.

### 13.3. Virtual threads có làm thay đổi API không?

Java 21+ có virtual threads, nhưng cú pháp `ThreadLocalRandom.current()` vẫn hợp lệ trong thread hiện tại. Các tác vụ có thể chờ I/O nhiều hơn nhưng CPU-bound simulation vẫn chịu giới hạn CPU. Đừng tạo hàng triệu virtual threads chỉ để sinh vài random numbers; chọn mức concurrency theo công việc thực.

Nếu cần request/job reproducibility, virtual threads cũng không tự bảo đảm seed gắn với request. Dùng generator rõ ownership per logical task khi đó là yêu cầu.

## 14. Cách dùng current trong các bài toán thực tế

### 14.1. Backoff có jitter — chỉ ở mức lịch chạy thông thường

Khi nhiều workers cùng retry một dịch vụ, nếu tất cả retry chính xác sau 1 giây, có thể tạo thundering herd. Có thể chọn delay trong một miền hợp lệ:

```java
long jitterMillis = ThreadLocalRandom.current().nextLong(200L, 500L);
```

Đây là snippet, trả giá trị từ 200 đến 499 ms. **Không** dùng giá trị này như security nonce hay auth token. Backoff production cần exponential limits, max retries, deadlines và phân biệt lỗi có thể retry với lỗi vĩnh viễn; random jitter chỉ là một phần của chính sách.

**Không dùng `Thread.sleep(jitterMillis)` trong event-loop hoặc task giữ lock quan trọng.** Delay nên được schedule bằng cơ chế phù hợp, không chiếm worker thread chờ khi đó là bottleneck.

### 14.2. Random sampling cho telemetry

Một collector có thể lấy một tỷ lệ mẫu:

```java
boolean sampled = ThreadLocalRandom.current().nextDouble() < 0.01;
```

Đây là snippet. Nếu giá trị random được sinh trong [0,1), điều kiện trên xấp xỉ một phần trăm các sự kiện trong nhiều lần thử độc lập theo mô hình PRNG.

**Không được assert cứ 100 events có đúng 1 sampled event.** Đó là xác suất, không phải hạn ngạch. Nếu cần “đúng 1% được gửi” với giới hạn ngân sách chính xác, dùng sampling + quota/counter hoặc algorithm khác.

### 14.3. Trộn workload demo

Để tạo input đa dạng trong stress test không cần reproducibility, mỗi worker có thể:

```java
int workloadKind = ThreadLocalRandom.current().nextInt(3); // 0, 1 hoặc 2
```

Đây là snippet. Nếu bug khó tái hiện, lưu seed của một generator deterministic per-test tốt hơn, thay vì sử dụng ThreadLocalRandom rồi cố đoán sequence ở lần chạy sau.

### 14.4. Partition routing

Chọn shard bằng random có thể tạo phân bố xấp xỉ nhưng **không ổn định theo key**:

```java
int shard = ThreadLocalRandom.current().nextInt(shardCount);
```

Đây là snippet, `shardCount>0` phải được validate. Nếu cùng một customer/key cần luôn tới cùng shard để duy trì order, **không** dùng random routing; dùng stable hash/partition key policy. Đây là ví dụ khác về **randomness không thay thế business semantics**.

### 14.5. Chọn random cho retry không đồng nghĩa workload fairness

Một scheduler phân bổ jobs ngẫu nhiên có thể khiến một worker/tenant nhận ít hoặc nhiều jobs hơn kỳ vọng trong một khoảng ngắn. Nếu SLA yêu cầu fairness, dùng thuật toán scheduling/quota/priority phù hợp. `ThreadLocalRandom` chỉ sinh số, không định nghĩa chiến lược fairness.

## 15. Tính đồng thời: các lỗi độc lập với PRNG

Việc thay `Random` bằng `ThreadLocalRandom` **không tự sửa những lỗi sau**:

- Hai workers cùng cập nhật `HashMap` hoặc `ArrayList` không thread-safe.
- Mỗi worker dùng random để lấy index rồi cùng sửa object tại index đó mà không có synchronization.
- Worker A tự cho phép thực hiện side effect khi worker B chưa kết thúc phase trước.
- Hai tasks cùng lấy generator có seed đã lưu nhưng vô tình chia sẻ mutable task state.
- Một generator instance không thread-safe bị dùng đồng thời bởi nhiều threads.
- Shared accumulator dùng `sum += value` mà không có cơ chế atomic/partition.
- A đang giữ lock L và chờ B, trong khi B cần lock L.
- Worker pool không đủ threads cho những tasks đang block/chờ lẫn nhau.

`ThreadLocalRandom` giúp **giảm tranh chấp quanh random state**, không phải một công cụ để tạo critical section, barrier hoặc transaction.

### 15.1. Thông điệp khi đọc JavaDoc

Tài liệu của `ThreadLocalRandom` nêu rằng dùng bộ sinh này trong multithreaded designs có thể giảm contention so với shared `Random`. Nhưng lời khẳng định đó **không** có nghĩa luôn chạy nhanh hơn trên mọi platform, mọi CPU/JDK version hoặc mọi workload. Phần lớn thời gian của ứng dụng có thể nằm ở I/O, DB, locks khác, memory bandwidth hoặc GC.

### 15.2. Khi nào nên dùng local reference?

Một method cùng worker tạo nhiều samples có thể dùng:

```java
ThreadLocalRandom rng = ThreadLocalRandom.current();
for (int index = 0; index < count; index++) {
    int sample = rng.nextInt(100);
    // Xử lý sample, không chia sẻ mutable state sai.
}
```

Đây là snippet. Không cần gọi `current()` một triệu lần chỉ để tạo một triệu numbers, dù bản thân method này nhẹ. Local variable làm mã dễ hiểu. Nhưng nếu coroutine/task thay đổi **executing thread** tại các boundaries, bạn nên lấy `current()` tại nơi công việc thực thi thực tế, không mang assumption “task này luôn dùng một thread” xuyên toàn bộ luồng xử lý.

## 16. Các trường hợp biên cần kiểm soát

### 16.1. Bound bằng 0 hoặc âm

`nextInt(0)` và `nextInt(-1)` ném `IllegalArgumentException`; `nextInt(size)` chỉ hợp lệ khi size dương. Nếu list rỗng, decide policy: throw, `Optional.empty()` hoặc business fallback — không gọi bừa rồi catch và coi như một sample hợp lệ.

### 16.2. origin bằng bound

`nextInt(5,5)` không hợp lệ. Tương tự `nextLong(100,100)` và `nextDouble(0.0,0.0)`. Với miền chỉ có **một số nguyên**, dùng [5,6), không dùng [5,5).

### 16.3. Double NaN và Infinity

Khi bounds của double lấy từ dữ liệu bên ngoài, validate **finite** và đúng chiều. Các quy tắc xác suất/đo đạc không có ý nghĩa nếu origin/bound là NaN hoặc infinity mà ứng dụng không có domain policy.

### 16.4. Số cực đại và số cực tiểu

`Math.abs(Integer.MIN_VALUE)` không phải phép ép không âm an toàn; `max+1` có thể overflow. Nếu cần sinh trong toàn miền `int`, `nextInt()` đã hỗ trợ. Nếu cần một khoảng giới hạn, dùng overload trực tiếp với cận rõ.

### 16.5. Không dùng randomness làm kết quả unit test cố định

Sai:

```java
assertEquals(6, ThreadLocalRandom.current().nextInt(1, 7));
```

Đây là snippet minh họa một unit test **không ổn định**: nhiều lần chạy nó có thể trả 1..6. Hãy assert thuộc tính:

```java
int value = ThreadLocalRandom.current().nextInt(1, 7);
assertTrue(value >= 1 && value <= 6);
```

Đây cũng là snippet, `assertTrue` là hàm assertion của framework test (không thuộc Java SE mặc định). Hoặc inject một seeded generator nếu cần compare exact deterministic sequence.

## 17. Quy tắc phát biểu xác suất và thống kê

`ThreadLocalRandom` dùng PRNG, không cung cấp “bảo đảm mỗi lần thử xảy ra tỷ lệ đúng tuyệt đối”. Ví dụ gọi `nextInt(10)` 1.000 lần:

- Mỗi giá trị 0..9 là giá trị hợp lệ.
- Không có nghĩa mỗi giá trị sẽ xuất hiện đúng 100 lần.
- Không có nghĩa kết quả liên tiếp không thể trùng.
- Không thể dùng một mẫu nhỏ để kết luận chất lượng thuật toán phân phối.
- Không có đảm bảo security unpredictability.

### 17.1. Đừng viết test giả định không có trùng lặp

`ThreadLocalRandom.current().nextLong()` có miền rất lớn, nhưng vẫn có khả năng tạo **hai giá trị bằng nhau** trong những lần gọi khác nhau. Nếu cần ID duy nhất, phải có **uniqueness protocol** như database constraint/sequence/UUID phù hợp; PRNG đơn thuần không tạo bảo đảm duy nhất.

### 17.2. Numeric distribution và fairness

Bộ sinh bounded `nextInt(origin,bound)` được thiết kế để trả số giả ngẫu nhiên phân bố phù hợp trong khoảng. Nhưng fairness của một **hệ thống** còn phụ thuộc vào:

- Cách chọn dữ liệu đầu vào.
- Công thức biến đổi số random thành lựa chọn.
- Số lần chọn và cách retry.
- Quy tắc loại trừ/loại ưu tiên.
- Thread/task scheduling.
- Cách quan sát outcomes và các bias ở tầng business.

Nếu kiểm chứng phân bố bằng thống kê, dùng tần suất đủ lớn, tiêu chuẩn thống kê rõ và không biến test thành một phép so “chắc chắn mỗi bucket phải bằng nhau”.

## 18. Bảo mật và vận hành an toàn

### 18.1. Security-sensitive randomness phải tách riêng

Một ví dụ **sai về bảo mật**:

```java
String token = Long.toHexString(ThreadLocalRandom.current().nextLong());
```

Đây là snippet anti-pattern. Token có vẻ dài và khó đọc nhưng **không** đạt yêu cầu của cryptographic random. Dùng `SecureRandom` để tạo secret bytes đủ entropy, có expiry/authorization/threat model phù hợp. Không log secret bytes ra stdout.

### 18.2. Input validation và quotas

Không vì sinh random được trong range mà mặc nhiên cho phép người dùng đặt một range quá lớn hoặc tạo 10 triệu jobs. Hệ thống cần:

1. Validate bounds và payload types.
2. Giới hạn số samples có thể yêu cầu trong mỗi request.
3. Giới hạn CPU/RAM/time per job.
4. Không dùng randomness làm rate limiting thay cho quota.
5. Không dùng random để bỏ qua authentication/authorization.
6. Không dùng `Math.abs(...) % size` để tạo index.
7. Không xem PRNG là secure secret generator.
8. Không đưa raw random secret vào metrics/logs.
9. Gắn request IDs nếu hệ thống có retry/deduplication.
10. Có cancellation/deadline cho jobs dài.

### 18.3. Thread pools và virtual threads

Dù `current()` tránh shared-random bottleneck, mỗi worker vẫn có công việc khác. Nếu service tạo hàng nghìn CPU-intensive threads để “sinh random nhanh hơn”, throughput có thể giảm vì context switches, cache pressure và CPU quota. Với Java 21+, virtual threads chủ yếu giúp xử lý nhiều tasks có thể block, **không tạo thêm CPU cores**. Chọn executor phù hợp workload.

### 18.4. Monitoring

Thu metrics:

- Tổng số samples/second.
- Latency của whole job, không chỉ nextInt.
- CPU utilization, GC allocation, memory pressure.
- Số workers thực sự active.
- Request failures do input invalid.
- Độ trễ các tác vụ sau bước sinh số.
- Tỷ lệ sampled telemetry thực theo khoảng dài nếu cần phân tích.

Không cần log từng số ngẫu nhiên để chứng minh hiệu năng; việc ghi log trong hot loop có thể áp đảo chi phí PRNG.

## 19. Performance: tối ưu nơi thực sự có nghẽn

**Trước khi khẳng định `ThreadLocalRandom` nhanh hơn `Random`**, đo:

- Baseline `Random` local per worker.
- Shared `Random` dưới concurrency thực tế.
- `ThreadLocalRandom.current()`.
- `SplittableRandom` có ownership rõ.
- Tổng thời gian xử lý công việc, không chỉ generate.
- CPU cores/container quota và số worker threads.
- Allocation/GC nếu benchmark tạo đối tượng không cần thiết.
- Chi phí locking trong những phần khác của code.

Với một thread duy nhất, lợi thế giảm contention có thể không đáng kể; với nhiều workers cạnh tranh một shared `Random`, `ThreadLocalRandom` có thể giúp. Không có tốc độ tăng cố định (ví dụ “nhanh gấp 10 lần”) được bảo đảm bởi API.

### 19.1. Dùng JMH thay vì một lần nanoTime

Với microbenchmark:

1. Warm-up đầy đủ để JIT hoạt động.
2. Dùng JMH của OpenJDK, tách benchmark state hợp lý.
3. Tạo input trước measurement nếu không cần đo setup.
4. Tiêu thụ random output để compiler không loại bỏ tác vụ.
5. Chạy nhiều forks/iterations.
6. So trên JDK và phần cứng dùng thực tế.
7. Phân biệt benchmark **generator throughput** và **application throughput**.
8. Tránh đưa `System.out.println` vào hot loop.
9. Kiểm tra correctness và output distribution assumptions.
10. Đo cả chi phí chọn object/cập nhật dữ liệu nếu đó là real workload.

**Không dùng JMH để “chứng minh generator secure”**; performance và cryptographic security là các thuộc tính khác nhau.

## 20. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách sửa |
| --- | --- | --- |
| `new ThreadLocalRandom()` | Không phải API khởi tạo client | `ThreadLocalRandom.current()` |
| Đặt seed bằng `current().setSeed(42)` | Ném `UnsupportedOperationException` | Dùng `Random(seed)`/`SplittableRandom(seed)` cho test |
| Cache một PRNG ở main rồi tin seed gắn với task | Thread context khác task context | Lấy `current()` trong worker |
| Khẳng định mỗi current() tạo object mới | Không phải contract của API | Chỉ phụ thuộc semantics per-thread state |
| Assert một số cụ thể từ `current()` | Test flaky | Assert range hoặc inject seeded generator |
| `nextInt(1,6)` để lấy xúc xắc 1..6 | Cận trên exclusive; thiếu 6 | `nextInt(1,7)` |
| `nextInt(list.size())` khi list rỗng | Bound = 0, ném IAE | Validate non-empty |
| `Math.abs(nextInt()) % size` | Overflow ở MIN_VALUE, bias | `nextInt(size)` |
| `nextInt(min,max+1)` với max cực đại | Overflow cận trên | Half-open bounds và xử lý extremes |
| `nextDouble() <= 0.01` khi cần dưới 1% | Quy tắc boundary có thể lệch policy | Xác định rõ `< 0.01` theo hợp đồng |
| Đồng bộ `synchronized` quanh `current()` không cần thiết | Lock overhead, bỏ ưu điểm | Bỏ lock nếu chỉ bảo vệ generator |
| Dùng `Random` shared rồi gọi là “không thread-safe” | Sai JavaDoc | Nói chính xác: thread-safe nhưng có thể contention |
| Chia sẻ `SplittableRandom` mutable giữa nhiều threads | Không được thiết kế thread-safe | Mỗi task/thread sở hữu generator riêng |
| Dùng `ThreadLocalRandom` tạo API keys | Không có bảo đảm crypto security | `SecureRandom` |
| Dùng random number làm unique ID chắc chắn | Có thể trùng | Sequence/uniqueness constraints/UUID policy |
| Dùng PRNG để “bảo đảm fairness” | Fairness đòi logic nghiệp vụ | Define selection/rate policy |
| Coi random selection là authorization | Randomness không thay quyền | Auth/ACL trước khi cho phép action |
| Multi-threaded counters ++ lên shared array | Lost updates | Local arrays + merge hoặc atomics |
| Gọi parallel stream cho một số | Overhead không cần | Một `current().nextInt` |
| Giả định parallel luôn nhanh hơn | Tốn scheduling/GC/memory bandwidth | Benchmark representative workload |
| Dùng current khi cần replay theo seed | Không điều khiển seed | Inject RandomGenerator seeded |
| Đưa seed/secret vào logs | Lộ thông tin nếu là secret | Hạn chế logging và secret handling |
| Suy object identity xác định thread | Không phải contract | Dùng thread/task context riêng cho tracking |
| Không validate dữ liệu từ request | Illegal bounds, resource exhaustion | Validate input, quota và deadline |

## 21. Checklist code review

1. Kết quả random này có dùng cho **bảo mật** hay chỉ simulation/sampling?
2. Nếu dùng cho security token/key, đã chuyển sang `SecureRandom` chưa?
3. Có gọi `ThreadLocalRandom.current()` **đúng thread thực thi** không?
4. Có bỏ việc tạo generator object mới không cần thiết trong hot code không?
5. Có tránh `new ThreadLocalRandom()` và `setSeed` không?
6. Có không phụ thuộc object identity của generator theo thread không?
7. Có hiểu thread-local state không phải task-local seed không?
8. Nếu cần reproducibility, có inject `RandomGenerator` có seed không?
9. Nếu một generator được chia sẻ, implementation đó thực sự thread-safe không?
10. Các bounded calls có dùng origin inclusive, bound exclusive không?
11. Các bounds có được validate từ dữ liệu nghiệp vụ không?
12. Có xử lý empty list trước `nextInt(size)` không?
13. Có tránh `Math.abs(randomInt)%size` và arithmetic overflow trên bounds không?
14. Có xử lý các extreme values, NaN/Infinity nếu dùng double không?
15. Test có tránh assert giá trị ngẫu nhiên cụ thể từ current không?
16. Test có kiểm tra range/semantics thay vì tần suất bucket chính xác không?
17. Có biết nhiều samples có thể trùng không, và unique IDs cần protocol riêng?
18. Có giữ kết quả local nếu nhiều threads cùng thống kê không?
19. Có không cho thread khác sửa mutable data mà worker đang dùng mà thiếu synchronization không?
20. Có không dùng ngẫu nhiên để làm authorization/rate limiting thay cho policy thực không?
21. Khi chạy parallel stream, có lấy current trong lambda nếu cần thread thực thi không?
22. Có phân biệt generator speed với whole pipeline throughput không?
23. Có bench bằng JMH/real data trước khi tối ưu không?
24. Có limits cho số tasks/samples, CPU và RAM trên public API không?
25. Có quy định seed, algorithm và input order nếu cần replay không?
26. Có tránh dùng seeded test PRNG làm secure secret generator không?
27. Có không giả định mỗi worker luôn chạy một task duy nhất không?
28. Có giải phóng executor/resources sau thử nghiệm không?
29. Có giữ logs khỏi các random token/secret bytes không?
30. Có biết ThreadLocalRandom và các APIs trong bài **vẫn hợp lệ trong Java 17+** không?

## 22. Bài tập thực hành

**Bài 1 — current cơ bản.** Chạy `CurrentBasicsDemo` ba lần. So sánh các boolean properties, không cố đoán các giá trị ngẫu nhiên cụ thể.

**Bài 2 — Hai overload của nextInt.** Dùng `nextInt(6)` và `nextInt(1,7)` để tạo xúc xắc 1..6. Vì sao cả hai cách hợp lệ nhưng các cận khác nhau?

**Bài 3 — Kiểm tra range.** Chạy `CurrentBoundsDemo`; bổ sung `nextInt(-5,5)` và xác nhận output luôn nằm trong `[-5,5)`.

**Bài 4 — Invalid bounds.** Thử `nextLong(7,7)`, `nextDouble(2,1)`, `nextInt(-1)`, kiểm tra `IllegalArgumentException`.

**Bài 5 — Thread pool.** Chạy `CurrentWorkerTasksDemo` với 8 tasks trên pool 3 workers. Vì sao task-local behavior không đồng nghĩa có 8 threads riêng?

**Bài 6 — Seed injection.** Chạy `CurrentSeedDemo`. Giải thích vì sao không thể gọi `setSeed` trên `ThreadLocalRandom.current()`.

**Bài 7 — Lựa chọn phần tử.** Chạy `CurrentChoiceDemo` với list dài 20 phần tử, kiểm tra chỉ số và kết quả luôn thuộc list. Với list rỗng, chọn policy rõ.

**Bài 8 — Random selection with replacement.** Gọi `choose` 100 lần trên list 10 phần tử; giải thích vì sao các phần tử có thể bị chọn lặp, không phải bug PRNG.

**Bài 9 — Parallel stream.** Chạy `CurrentParallelStreamDemo` với 20.000 phần tử rồi chạy bản sequential. Kiểm tra correctness và benchmark có kiểm soát.

**Bài 10 — RandomGenerator.** Chạy `CurrentInjectedGeneratorDemo` với nhiều seed; xác nhận cùng seed và cùng calls dẫn tới kết quả tái lập trong test.

**Bài 11 — Deterministic partitions.** Gán mỗi partition một `SplittableRandom(seedForPartition)` và chạy trên 1 worker/4 workers; kiểm tra outputs theo partition bằng nhau.

**Bài 12 — Security.** Chạy `CurrentSecureRandomDemo`, giải thích vì sao không in token thật và vì sao `ThreadLocalRandom` không nên tạo token.

**Bài 13 — Local aggregation.** Chạy `CurrentLocalAggregationDemo` với 8 workers × 5.000 mẫu; kiểm tra tổng bằng 40.000, không assert mỗi bucket đúng 10.000.

**Bài 14 — Data race.** Tạo ví dụ sandbox nhiều workers cùng cập nhật shared `int[]`, so với phiên bản local arrays + merge. Nêu tại sao random generator đúng nhưng counters vẫn sai.

**Bài 15 — Boundary extremes.** Phân tích `Integer.MAX_VALUE + 1`, `Math.abs(Integer.MIN_VALUE)` và cách dùng half-open bounds để tránh lỗi index.

**Bài 16 — Jitter.** Thiết kế exponential backoff có jitter bằng `nextLong(low,highExclusive)`, có max delay, max attempts, time budget và không block event loop.

**Bài 17 — Sampling rate.** Dùng `nextDouble() < 0.01` trong một simulation; phân biệt 1% kỳ vọng với “cứ 100 lần đúng 1 lần”.

**Bài 18 — Reproducible test.** Viết helper nhận `RandomGenerator` rồi test với `Random(seed)`/`SplittableRandom(seed)`. Không assert chuỗi cứng của current.

**Bài 19 — API design.** Viết một service lựa chọn load-test scenario theo random trong mỗi worker, có validates, bounded concurrency và metrics.

**Bài 20 — Threat model.** Với ba mục tiêu “mô phỏng”, “chọn avatar ngẫu nhiên”, “reset password token”, hãy chọn `ThreadLocalRandom`, seeded generator hoặc `SecureRandom` và giải thích.

## 23. Tổng kết

- Cách dùng cốt lõi là **`ThreadLocalRandom.current()`**, một static method lấy generator phù hợp với **thread đang gọi**, không phải tự `new` hoặc ép `setSeed`.
- `ThreadLocalRandom` hữu ích cho ngẫu nhiên **không cần bảo mật** trong thiết kế nhiều threads, vì tránh việc nhiều luồng phải tranh chấp cùng random state.
- `nextInt(origin,bound)`, `nextLong(origin,bound)` và `nextDouble(origin,bound)` dùng **[origin,bound)**; cận trên **không được lấy**.
- Trong executor/parallel stream, lấy `current()` **bên trong worker/lambda** để biểu đạt chính xác execution context; thread pool tái sử dụng threads nên thread-local không tự thành task-local.
- **Không thể setSeed** trên `ThreadLocalRandom.current()`; test cần tái lập nên inject seeded `RandomGenerator`, ví dụ `Random` hoặc `SplittableRandom` với ownership rõ.
- Không dùng random % list size hoặc `Math.abs(nextInt())` để tạo index, vì bias/tràn số; dùng overload `nextInt(size)`.
- `ThreadLocalRandom` không tạo token an toàn mật mã; dùng `SecureRandom` và security policy thích hợp.
- Random generator thread-friendly **không tự biến shared counters/collections thành thread-safe**; phân vùng state hoặc dùng synchronization đúng.
- Không assert số ngẫu nhiên cụ thể trong unit test; kiểm tra **range, input validation, result invariants** và deterministic seeded paths khi có yêu cầu.
- ThreadLocalRandom **vẫn là API Java hiện hành trên Java 17+** dù xuất hiện từ Java 7; các lựa chọn hiện đại khác là bổ sung theo mục đích, không phải lý do coi nó là legacy.

## Tài liệu chính thức

- [ThreadLocalRandom — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): `current()`, bounded generation, per-thread state, `setSeed`, random stream APIs và semantics thread use.
- [ThreadLocalRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): phiên bản tối thiểu cho mã ví dụ.
- [Random — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Random.html): seeded pseudorandom generator, thread safety và contention considerations.
- [RandomGenerator — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGenerator.html): abstraction Java 17+, bounded methods và generator behavior.
- [RandomGeneratorFactory — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): lựa chọn thuật toán PRNG qua factory.
- [SplittableRandom — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SplittableRandom.html): seeded và splittable generator cho parallel computations.
- [SecureRandom — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): randomness an toàn mật mã.
- [ExecutorService — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): task submission, futures, shutdown, timed invokeAll.
- [IntStream — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html): parallel stream và map/filter.
- [HexFormat — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html): biểu diễn bytes dưới dạng hex mà không tự viết encoding.
