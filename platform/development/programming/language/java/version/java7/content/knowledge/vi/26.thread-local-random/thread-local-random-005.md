# Java 7 — ThreadLocalRandom: Quản lý trạng thái theo luồng và giới hạn đặt seed

## 1. Bài học giải quyết vấn đề gì?

`java.util.concurrent.ThreadLocalRandom` được thêm từ Java 7 và vẫn là API hiện hành trong Java 17+. Nó cung cấp một nguồn số giả ngẫu nhiên tiện dụng khi **nhiều threads cùng tạo số ngẫu nhiên**, đặc biệt khi không cần seed do ứng dụng tự kiểm soát. Điểm cốt lõi của bài này không chỉ là cú pháp `nextInt()`, mà là cơ chế **trạng thái sinh số gắn với thread**, tác động của **thread pool tái sử dụng threads**, và lý do **không được đặt seed thủ công** qua `ThreadLocalRandom.setSeed()`.

Sau bài này, bạn có thể giải thích và áp dụng:

1. Vì sao `ThreadLocalRandom.current()` là cách truy cập được khuyến nghị.
2. Vì sao tránh chia sẻ một `Random` duy nhất chỉ để nhiều threads cùng sinh số.
3. Ý nghĩa của **trạng thái theo thread**, khác với object `ThreadLocal<T>` do lập trình viên quản lý.
4. Vì sao gọi `setSeed(long)` trên `ThreadLocalRandom` sẽ ném `UnsupportedOperationException`.
5. Vì sao không có cách supported để yêu cầu ThreadLocalRandom sinh chính xác cùng chuỗi sau khi một task khởi chạy.
6. Thread pool **tái sử dụng threads**, nên “một task mới” không tương đương “một RNG được reset”.
7. Cách dùng bounded `nextInt(origin,bound)`, `nextLong`, `nextDouble` đúng khoảng.
8. Cách viết tests cho random behavior bằng **bất biến/range**, không hardcode một số do ThreadLocalRandom trả ra.
9. Cách viết test tái lập bằng `SplittableRandom(seed)` hoặc Java 17 `RandomGeneratorFactory`.
10. Cách seed **theo định danh tác vụ** để kết quả không phụ thuộc vào thứ tự scheduling.
11. Vì sao seeded PRNG dành cho simulation/test **không** trở thành nguồn random mật mã.
12. Lưu ý thread safety, performance, thread-local leaks, lifecycle và giới hạn của reproducibility.

**Phạm vi:** “Quản lý trạng thái theo luồng và giới hạn đặt seed”, thuộc chủ đề cha `ThreadLocalRandom`. Các ví dụ biên dịch với `javac --release 17` và chỉ dùng các API còn được hỗ trợ; không hướng dẫn can thiệp fields private/internal hoặc dựa vào implementation details.

## 2. PRNG và trạng thái sinh số

Một pseudorandom number generator (**PRNG**) tiến qua một dãy trạng thái nội bộ; kết quả tiếp theo được tính từ trạng thái trước đó. Chẳng hạn ở mức khái niệm:

```text
                next()           next()           next()
State S0  --------------> S1 --------------> S2 --------------> S3
   |                        |                  |
 result r0                result r1          result r2
```

Số nhìn có vẻ ngẫu nhiên, nhưng chuỗi thực chất được tạo bởi thuật toán. Tính phân phối thống kê tốt **không tự bảo đảm khó dự đoán trước đối thủ**. ThreadLocalRandom là PRNG **không dành cho mật mã**.

### 2.1. Một PRNG có seed nghĩa là gì?

Seed là dữ liệu khởi tạo trạng thái ban đầu. Với **thuật toán và môi trường triển khai phù hợp**, cùng seed có thể dẫn tới cùng chuỗi. Điều này có ích để:

- Debug một mô phỏng gặp lỗi.
- So sánh hai lần chạy benchmark một cách kiểm soát.
- Reproduce test case.
- Sinh input có vẻ ngẫu nhiên nhưng được kiểm soát.

Không nên trộn mục đích tái lập này với **bí mật**: seed cố định là dự đoán được và không phù hợp làm token/khóa/session secret.

### 2.2. Điều gì xảy ra khi một RNG dùng chung?

Một `java.util.Random` chia sẻ giữa nhiều threads có các cơ chế an toàn thread theo API, nhưng các lời gọi có thể tranh chấp cập nhật trạng thái, và **thứ tự thread thực thi ảnh hưởng chuỗi thread nào lấy được số nào**. Một số use cases có thể chậm do contention.

`ThreadLocalRandom` phục vụ tình huống nhiều threads cùng cần các giá trị không cần tái lập: không cần một shared mutable PRNG state để mọi thread tranh giành.

## 3. ThreadLocalRandom dùng current(), không tạo new

Cách gọi chuẩn:

```java
int dice = ThreadLocalRandom.current().nextInt(1, 7);
```

Đây là **mảnh minh họa**, cần `import java.util.concurrent.ThreadLocalRandom;` và một method.

- `ThreadLocalRandom.current()` trả về đối tượng RNG dùng cho các lời gọi từ **thread hiện tại**.
- Trong triển khai JDK, các threads có trạng thái PRNG riêng và tránh tranh chấp một seed shared giữa threads.
- Không có API public để caller lấy/thiết lập seed của ThreadLocalRandom.
- Class được thiết kế cho **các lời gọi từ thread hiện tại**, không cần lưu reference rồi chuyền qua threads khác.
- Trạng thái nội bộ và thuật toán có thể thay đổi giữa Java versions/implementations; không lập trình dựa vào fields private.

### 3.1. current() không đồng nghĩa mỗi lần new một RNG

`ThreadLocalRandom.current()` không phải constructor tạo một RNG mới, và không hứa mỗi task có sequence độc lập. Thread pool có thể chạy nhiều tasks liên tiếp trên cùng worker thread.

### 3.2. Không thể gọi constructor public

`ThreadLocalRandom` không có public constructor cho ứng dụng tạo new như `new Random()`. Hãy dùng `current()`, không reflection/Unsafe để vượt API nhằm ép một internal state.

## 4. Cơ chế state theo thread và tác động scheduling

```text
              Thread 1                         Thread 2
       ThreadLocalRandom.current()       ThreadLocalRandom.current()
                   |                                 |
                state A                           state B
                   |                                 |
           nextInt() -> A'                      nextInt() -> B'
           nextInt() -> A''                     nextInt() -> B''

        No application-managed shared seed between two threads.
```

Điều này giúp các threads không phải đồng bộ mỗi lần sinh giá trị qua một state chung.

**Giới hạn:** Không suy rằng:
- Hai threads chắc chắn sinh ra hai giá trị khác nhau ở cùng lượt.
- Thứ tự random values của từng task sẽ lặp lại sau khi restart.
- Seed của mỗi thread do API public cho phép người dùng kiểm soát.
- Mỗi request có RNG state riêng chỉ vì request là một tác vụ khác.
- `current()` là một đối tượng riêng biệt theo `==` giữa các threads theo hợp đồng cần dựa vào. Hãy tập trung vào behavior thay vì identity implementation.

### 4.1. ThreadLocalRandom và ThreadLocal<T> khác nhau

`ThreadLocal<T>` là container để bạn lưu **dữ liệu ứng dụng theo thread**. Bạn gọi `get/set/remove`, cung cấp `initialValue`; cần cleanup khi threads sống lâu.

`ThreadLocalRandom` là PRNG tiện dụng với trạng thái theo thread do JDK quản lý. Nó không cho bạn một `setSeed` hay `remove` để reset state theo task.

| Khía cạnh | `ThreadLocal<T>` do bạn tạo | `ThreadLocalRandom` |
| --- | --- | --- |
| Mục tiêu | Bất kỳ per-thread application state | Sinh giá trị ngẫu nhiên thông thường |
| Truy cập | `threadLocal.get()` | `ThreadLocalRandom.current()` |
| Tự đặt initial value | Có thể `withInitial(supplier)` | Không có public seed setter |
| Set/replace value | `set(value)` | Không có set-state được hỗ trợ |
| Xóa state theo thread | `remove()` | Không có API reset seed tương ứng |
| Thread pool | Giá trị cũ còn nếu không remove | PRNG sequence tiếp tục theo thread |
| Bảo mật | Tùy loại dữ liệu bạn lưu | Không phải CSPRNG |

**Không** tự tạo `ThreadLocal<Random>` để “sửa” giới hạn setSeed của ThreadLocalRandom nếu yêu cầu thực sự là reproducibility *theo job*. Khi đó một generator rõ ràng **per job** thường dễ kiểm soát và test hơn.

## 5. Thread pool reuse: task không phải thread

Một `ExecutorService` với một worker có thể thực thi:

```text
Worker-thread-1:
     Task A -> ThreadLocalRandom.current().nextInt()
     Task B -> ThreadLocalRandom.current().nextInt()
     Task C -> ThreadLocalRandom.current().nextInt()

Three tasks. One worker thread reused. No per-task seed reset.
```

Nếu cùng worker xử lý A rồi B, không có contract reset RNG về đầu chuỗi trước task B.

### 5.1. Tại sao bug “randomness thay đổi khi tăng parallelism” thường xảy ra?

Khi thay số threads, scheduling thay đổi, dẫn đến các tasks được phân cho threads khác nhau. Nếu code dùng `ThreadLocalRandom.current()` bên trong từng task, task có thể lấy random values khác dù **input nghiệp vụ giống nhau**. Đó là hành vi bình thường, không phải data race của RNG.

Nếu yêu cầu tái lập theo task, phải dùng deterministic PRNG khởi tạo từ **stable job ID/seed**.

## 6. Chương trình A — SeedUnsupportedDemo.java

Một đặc điểm nổi bật nhất của `ThreadLocalRandom` là inherited `setSeed` không được hỗ trợ khi ứng dụng dùng đối tượng do `current()` trả về.

```java
import java.util.concurrent.ThreadLocalRandom;

public final class SeedUnsupportedDemo {
 public static void main(String[] args) {
   boolean rejected = false;
   try {
     ThreadLocalRandom.current().setSeed(123L);
   } catch (UnsupportedOperationException expected) {
     rejected = true;
   }
   System.out.println("setSeedRejected=" + rejected);
   System.out.println("rangeSupported=" +
     (ThreadLocalRandom.current().nextInt(10,20) >= 10));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SeedUnsupportedDemo.java
java SeedUnsupportedDemo
```

Stdout đã kiểm thử:

```text
setSeedRejected=true
rangeSupported=true
```

**Lý do:** `ThreadLocalRandom` kế thừa API shape từ `Random`, nhưng việc tự ý đặt seed không phù hợp với cách JDK quản lý state theo thread. Vì vậy `setSeed(long)` ném `UnsupportedOperationException` theo public contract. Không có “mật khẩu”/JVM trick supported để biến nó thành một seeded RNG theo task.

## 7. Giới hạn setSeed: điều gì chính xác không được hứa?

- Không được `ThreadLocalRandom.current().setSeed(42)` để tái lập sequence.
- Không được giả định seed ban đầu có thể đọc từ thread để logging/replay.
- Không có public API `getSeed()` của ThreadLocalRandom.
- Không được giả định `ThreadLocalRandom.current()` ở một worker vừa được reuse tự khởi tạo seed mới.
- Không có constructor public nhận seed.
- Không hứa cùng số thread và cùng workload sẽ cho cùng output giữa hai lần chạy.
- Không cố truy cập private JDK classes/fields để sửa seed; Java module encapsulation và semantics nội bộ không đảm bảo.
- Không sử dụng seed cố định để làm **security tokens**; cả seeded lẫn không seeded `ThreadLocalRandom` đều không phải CSPRNG.

### 7.1. Constructor và override setSeed không phải “lỗi Java”

`java.util.Random` có public `setSeed(long)`; `ThreadLocalRandom` purposely overrides behavior. JDK documentation công khai giới hạn này. Nên **chọn đúng API**, không gọi reflection để can thiệp internal state.

### 7.2. Không có một seed ứng dụng toàn cục được bảo đảm

Chỉ gọi một lần `Random(seed)` trong main rồi sau đó dùng `ThreadLocalRandom` ở workers không biến chúng thành seeded streams tương ứng. Hai generators có state khác nhau và không chia sẻ seed contract.

## 8. Chương trình B — ThreadStateReuseDemo.java

`Executors.newSingleThreadExecutor()` thực thi các tasks tuần tự trên một worker (trong điều kiện worker không chết/thay mới), giúp thấy task và thread là hai khái niệm khác nhau.

```java
import java.util.concurrent.*;

public final class ThreadStateReuseDemo {
 public static void main(String[] args) throws Exception {
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<String> a = pool.submit(() -> {
       ThreadLocalRandom r = ThreadLocalRandom.current();
       return Thread.currentThread().getName();
     });
     Future<String> b = pool.submit(() -> {
       int value = ThreadLocalRandom.current().nextInt(1,7);
       if (value < 1 || value > 6)
         throw new AssertionError();
       return Thread.currentThread().getName();
     });
     System.out.println("sameWorkerForBothTasks=" +
       a.get(5, TimeUnit.SECONDS).equals(
         b.get(5, TimeUnit.SECONDS)));
     System.out.println("separateSeedPerTaskNotGuaranteed=true");
   } finally {
     pool.shutdown();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ThreadStateReuseDemo.java
java ThreadStateReuseDemo
```

Stdout đã kiểm thử:

```text
sameWorkerForBothTasks=true
separateSeedPerTaskNotGuaranteed=true
```

Demo kiểm **worker được reuse** và output range hợp lệ; nó không cố đọc internal seed. `sameWorkerForBothTasks=true` là kết quả trên executor một worker chạy bình thường, không nên biến thread name thành một định danh nghiệp vụ lâu dài hoặc giả định worker tuyệt đối không bao giờ được thay khi có lỗi.

## 9. nextInt, nextLong, nextDouble: khoảng đóng/mở

Java 17 hỗ trợ những dạng hữu ích:

```java
int a = ThreadLocalRandom.current().nextInt();       // arbitrary int
int b = ThreadLocalRandom.current().nextInt(10);     // 0..9
int c = ThreadLocalRandom.current().nextInt(5, 11);  // 5..10
long d = ThreadLocalRandom.current().nextLong(100L,1000L);
double e = ThreadLocalRandom.current().nextDouble(0.0,1.0);
```

Đây là mảnh minh họa. Với bounds `origin/bound`, quy tắc chuẩn là **origin inclusive, bound exclusive**. Sai cặp bounds, ví dụ `nextInt(5,5)`, ném `IllegalArgumentException`.

### 9.1. Công thức thường dùng

- Xúc xắc 1..6: `nextInt(1,7)`.
- Chọn một chỉ số trong array length N>0: `nextInt(N)`.
- Test một bucket từ 0..99: `nextInt(100)`.
- Random timeout jitter trong [100,500): `nextLong(100L,500L)`.
- Xác suất double trong [0,1): `nextDouble()`.

Không áp đặt `Math.abs(r.nextInt()) % bound`: có overflow ở `Integer.MIN_VALUE` và phân phối có thể bị lệch. Dùng bounded API.

## 10. Chương trình C — RangeContractsDemo.java

```java
import java.util.concurrent.*;

public final class RangeContractsDemo {
 public static void main(String[] args) {
   ThreadLocalRandom r = ThreadLocalRandom.current();
   boolean valid = true;
   for (int i = 0; i < 1000; i++) {
     int n = r.nextInt(-3,4);
     long l = r.nextLong(100,1000);
     double d = r.nextDouble(0.0,1.0);
     valid &= n >= -3 && n < 4
           && l >= 100 && l < 1000
           && d >= 0.0 && d < 1.0;
   }
   boolean badBound = false;
   try { r.nextInt(5,5); }
   catch (IllegalArgumentException e) { badBound = true; }
   System.out.println("allRangesValid=" + valid);
   System.out.println("upperBoundExclusive=true");
   System.out.println("equalBoundsRejected=" + badBound);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RangeContractsDemo.java
java RangeContractsDemo
```

Stdout đã kiểm thử:

```text
allRangesValid=true
upperBoundExclusive=true
equalBoundsRejected=true
```

Một test tốt cho `ThreadLocalRandom` là kiểm **contract** chứ không mong output thứ nhất sẽ là 42. Trường hợp bounds không hợp lệ phải được test bằng exception.

## 11. Nhiều threads cùng gọi current()

Các threads có thể dùng `ThreadLocalRandom.current()` trong mỗi task, không cần synchronized block bên ngoài chỉ để sinh số. Điều đó không có nghĩa **business state** dùng các số ấy tự thread-safe.

Ví dụ:
- Random chọn số rồi ghi vào `ArrayList` chung **không đồng nghĩa** thao tác add tự thread-safe.
- Random quyết định thử network call nhưng chính HTTP client/connection pool vẫn cần lifecycle riêng.
- Random lấy index, sau đó array bị thread khác thay kích thước vẫn có thể xảy ra race.

`ThreadLocalRandom` bảo vệ/điều phối state RNG của nó; không bảo vệ dữ liệu ứng dụng.

## 12. Chương trình D — ThreadIsolationDemo.java

```java
import java.util.concurrent.*;
import java.util.*;

public final class ThreadIsolationDemo {
 public static void main(String[] args) throws Exception {
   ExecutorService pool = Executors.newFixedThreadPool(4);
   try {
     List<Future<Boolean>> jobs = new ArrayList<>();
     for (int t=0; t<4; t++) jobs.add(pool.submit(() -> {
       ThreadLocalRandom r = ThreadLocalRandom.current();
       for (int i=0; i<2000; i++) {
         int n = r.nextInt(1,7);
         if (n<1 || n>6) return false;
       }
       return true;
     }));
     boolean all=true;
     for (Future<Boolean> job : jobs)
       all &= job.get(5, TimeUnit.SECONDS);
     System.out.println("allWorkersWithinRange=" + all);
     System.out.println("sampleCount=" + (4*2000));
   } finally {
     pool.shutdown();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ThreadIsolationDemo.java
java ThreadIsolationDemo
```

Stdout đã kiểm thử:

```text
allWorkersWithinRange=true
sampleCount=8000
```

Không cần assert số random values khác nhau giữa threads; duplicates là hoàn toàn bình thường. Cũng không dùng thứ tự task execution để kỳ vọng một chuỗi cố định.

## 13. Deterministic tests: vì sao không seed ThreadLocalRandom?

Một unit test muốn tái lập lỗi cần **cùng chuỗi test inputs** giữa các lần chạy. Vì `ThreadLocalRandom` không cho đặt seed, nó không phù hợp làm nguồn test data cố định.

### 13.1. Tách RNG khỏi business logic

Thay vì method tự gọi random cố định:

```java
int choose() {
    return ThreadLocalRandom.current().nextInt(10);
}
```

đây là mảnh minh họa, hãy thiết kế API nhận `RandomGenerator`/`SplittableRandom` hoặc một interface sampling nhỏ. Khi chạy production có thể dùng `ThreadLocalRandom.current()` cho random thông thường, khi test truyền seeded PRNG.

Java 17 có interface `java.util.random.RandomGenerator`. Nên chọn một thuật toán **theo tên** hoặc object `SplittableRandom` seed rõ nếu việc tái lập là yêu cầu.

### 13.2. Không dùng shared seeded generator không được thread-safe đúng cách

`SplittableRandom` không được thiết kế để nhiều threads cùng gọi một instance một cách không đồng bộ. Muốn deterministic parallel results, dùng **một instance per task** hoặc chia nguồn một cách an toàn; không dùng một global `SplittableRandom(42)` trên mọi threads.

## 14. Chương trình E — SeededSplittableDemo.java

`SplittableRandom` là PRNG hiệu quả, hỗ trợ seed trong constructor, có thể `split()` để tạo streams. Nó **không** phải nguồn mật mã.

```java
import java.util.SplittableRandom;

public final class SeededSplittableDemo {
 public static void main(String[] args) {
   SplittableRandom a = new SplittableRandom(42L);
   SplittableRandom b = new SplittableRandom(42L);
   boolean identical = true;
   int first=0;
   for (int i=0; i<5; i++) {
     int x = a.nextInt(0,1000);
     int y = b.nextInt(0,1000);
     if (i==0) first=x;
     identical &= x==y;
   }
   System.out.println("sameSeedSameSequence=" + identical);
   System.out.println("firstValue=" + first);
   System.out.println("notCryptographic=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SeededSplittableDemo.java
java SeededSplittableDemo
```

Stdout đã kiểm thử trên JDK Java 17-compatible:

```text
sameSeedSameSequence=true
firstValue=31
notCryptographic=true
```

`firstValue=31` là một golden result đã kiểm chứng với JDK sử dụng cho bài. Với những thuật toán/generator có thay đổi implementation, nên xem liệu cần khóa thuật toán và runtime version hay chỉ assert hai generators cùng seed cho kết quả giống nhau.

### 14.1. Lựa chọn seeded PRNG không biến nó thành CSPRNG

Seed biết trước hoặc thuật toán có thể suy đoán khiến output không phù hợp cho password reset/session tokens. **Khả năng tái lập có ích cho test nhưng trái mục tiêu bảo mật khi giá trị là secret.**

## 15. Java 17 RandomGeneratorFactory: chọn thuật toán rõ ràng

Java 17 giới thiệu `java.util.random.RandomGenerator` và factory cho nhiều thuật toán, ví dụ `L64X128MixRandom`. Ta có thể tạo hai generators **cùng thuật toán và seed** và so sánh output:

```java
RandomGeneratorFactory<RandomGenerator> f =
    RandomGeneratorFactory.of("L64X128MixRandom");
RandomGenerator a = f.create(12345L);
RandomGenerator b = f.create(12345L);
```

Đây là mảnh minh họa; cần import `java.util.random.*;`.

### 15.1. Đừng dùng tên class mặc định nếu muốn repeatability

“Generator mặc định” là một lựa chọn của môi trường/phiên bản; nếu test yêu cầu deterministic algorithm, chọn **tên thuật toán ổn định** và quản lý version.

### 15.2. isStochastic không đồng nghĩa isCryptographic

`RandomGeneratorFactory.isStochastic()` nói về loại thuật toán/nguồn ngẫu nhiên của factory, **không** là phương pháp chứng minh suitability cho cryptographic purposes. Không viết `if(factory.isStochastic()) useForPasswordReset();`.

## 16. Chương trình F — NamedGeneratorDemo.java

```java
import java.util.random.*;

public final class NamedGeneratorDemo {
 public static void main(String[] args) {
   RandomGeneratorFactory<RandomGenerator> f =
      RandomGeneratorFactory.of("L64X128MixRandom");
   RandomGenerator a = f.create(12345L), b=f.create(12345L);
   boolean same = true;
   for (int i=0; i<100; i++)
     same &= a.nextLong()==b.nextLong();
   System.out.println("namedAlgorithm=" + f.name());
   System.out.println("seededReproducible=" + same);
   System.out.println("stochastic=" + f.isStochastic());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 NamedGeneratorDemo.java
java NamedGeneratorDemo
```

Stdout đã kiểm thử:

```text
namedAlgorithm=L64X128MixRandom
seededReproducible=true
stochastic=false
```

Output `stochastic=false` **không** tự nói “an toàn mật mã hay không” — Java 17 random-generation API mô tả category algorithm. Thuật toán LXM ở đây phù hợp sampling/simulation, **không** thay `SecureRandom` khi threat model đòi khó đoán.

## 17. ThreadLocal<T> trong thread pool: state dễ tồn tại lâu

Một vấn đề khác biệt nhưng liên quan: Nếu lập trình viên tự lưu state bằng `ThreadLocal<T>`, những giá trị đó **có thể sống tới khi worker thread được tái sử dụng**. Cần `remove()` sau request/task nếu dữ liệu không được giữ cho task sau, đặc biệt với user context hoặc dữ liệu nhạy cảm.

`ThreadLocalRandom` có internal state riêng, nhưng không có public `remove()` để reset như ThreadLocal do bạn tạo. Đây là thiết kế RNG, không phải lời khuyên tự giữ application context qua requests.

## 18. Chương trình G — ThreadLocalVsThreadLocalRandomDemo.java

```java
import java.util.concurrent.*;

public final class ThreadLocalVsThreadLocalRandomDemo {
 private static final ThreadLocal<Integer> COUNTER =
     ThreadLocal.withInitial(() -> 0);

 public static void main(String[] args) throws Exception {
   ExecutorService e = Executors.newSingleThreadExecutor();
   try {
     Future<Integer> a = e.submit(() -> {
       int x=COUNTER.get()+1;
       COUNTER.set(x);
       ThreadLocalRandom.current().nextInt();
       return x;
     });
     Future<Integer> b = e.submit(() -> {
       int x=COUNTER.get()+1;
       COUNTER.set(x);
       ThreadLocalRandom.current().nextInt();
       return x;
     });
     Future<Integer> c = e.submit(() -> {
       COUNTER.remove();
       return COUNTER.get();
     });
     System.out.println("counterAfterFirstTask=" +
       a.get(5,TimeUnit.SECONDS));
     System.out.println("counterAfterSecondTask=" +
       b.get(5,TimeUnit.SECONDS));
     System.out.println("afterRemove=" +
       c.get(5,TimeUnit.SECONDS));
     System.out.println(
       "threadLocalRandomHasNoUserSetSeed=true");
   } finally {
     e.shutdown();
     if (!e.awaitTermination(5,TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ThreadLocalVsThreadLocalRandomDemo.java
java ThreadLocalVsThreadLocalRandomDemo
```

Stdout đã kiểm thử:

```text
counterAfterFirstTask=1
counterAfterSecondTask=2
afterRemove=0
threadLocalRandomHasNoUserSetSeed=true
```

Hai tasks chia sẻ một worker nên tự tạo `ThreadLocal COUNTER` lần lượt nhận 1 rồi 2; `remove` khôi phục giá trị khởi tạo 0 cho lần `get` kế. Không dùng kết quả này để kết luận `ThreadLocalRandom` cũng có một method `remove` tương tự.

**Lưu ý:** Trong demo, `COUNTER` được lưu static để minh họa; production code phải dọn thread-local context trong `finally` của **chính request/task**. Đừng để dữ liệu nhạy cảm từ request A xuất hiện trong request B.

## 19. Deterministic random cho parallel jobs

Muốn mỗi task có input random **ổn định** dù task chạy trên worker nào, một pattern đơn giản là:

```java
SplittableRandom local = new SplittableRandom(masterSeed + taskId);
int choice = local.nextInt(bound);
```

Đây là mảnh minh họa; `masterSeed`, `taskId`, `bound` do ứng dụng cung cấp. Từng task có generator **riêng**. Trong hệ thống nghiêm ngặt về độc lập thống kê, hãy dùng cơ chế derivation/splitting được thiết kế và kiểm tra thay vì tùy tiện cộng seed; công thức đơn giản này minh họa **reproducibility**, không chứng minh độc lập mạnh hay an toàn mật mã.

### 19.1. Stable input là chìa khóa

- `taskId` không được dựa vào `Thread.currentThread().getId()` nếu scheduling có thể đổi.
- Không seed từ `System.currentTimeMillis()` rồi mong reproducible.
- Không phân phối seed bằng thứ tự một shared generator bị nhiều tasks race nhau.
- Nếu task được retry, quyết định nó cần dùng lại seed gốc hay seed theo attempt.
- Ghi algorithm name, master seed và task IDs khi cần reproduce chính xác simulation. Đừng ghi secrets vào logs nếu dùng cryptographic RNG.

## 20. Chương trình H — PerTaskSeedDemo.java

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.*;

public final class PerTaskSeedDemo {
 public static void main(String[] args) {
   List<Integer> x = IntStream.range(0,5).parallel()
     .mapToObj(i ->
       new SplittableRandom(1000L+i).nextInt(1000))
     .collect(Collectors.toList());
   List<Integer> y = IntStream.range(0,5).parallel()
     .mapToObj(i ->
       new SplittableRandom(1000L+i).nextInt(1000))
     .collect(Collectors.toList());
   System.out.println("parallelResultsReproducible=" +
     x.equals(y));
   System.out.println("taskCount=" + x.size());
   System.out.println("results=" + x);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PerTaskSeedDemo.java
java PerTaskSeedDemo
```

Stdout đã kiểm thử:

```text
parallelResultsReproducible=true
taskCount=5
results=[864, 257, 423, 515, 864]
```

### 20.1. Tại sao hai kết quả có thể giống nhau?

`results` có hai phần tử cùng bằng 864. Đó **không** phải lỗi — PRNG không đảm bảo uniqueness. Nếu cần mã định danh không trùng, một RNG riêng không cung cấp guarantee; phải có cơ chế đảm bảo uniqueness ở tầng storage/id allocation.

### 20.2. Vì sao thứ tự list vẫn theo task ID?

`IntStream.range(0,5)` là **ordered stream**. `collect(Collectors.toList())` giữ encounter order mặc dù xử lý song song; mỗi kết quả tương ứng với task ID ổn định, không phải thứ tự thread chạy.

### 20.3. Không dùng same global SplittableRandom trên parallel stream

Một `SplittableRandom` instance không dành cho concurrent access không đồng bộ. Pattern tạo một generator per task tránh shared mutable generator state. Trong ứng dụng lớn, có thể dùng `split()` một cách có kiểm soát và ghi mapping streams/tasks.

## 21. Khi nào dùng java.util.Random(seed)?

`Random` vẫn là API được hỗ trợ. Với một thread test hoặc một generator seed rõ, nó có thể phục vụ reproducibility. Khi cần concurrency hiệu quả, lựa chọn `SplittableRandom` / `RandomGenerator` per task thường phù hợp hơn, vì một shared Random có thể tạo contention.

### 21.1. Chương trình I — RandomSeedContrastDemo.java

```java
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;

public final class RandomSeedContrastDemo {
 public static void main(String[] args) {
   Random a=new Random(1234L),b=new Random(1234L);
   boolean same=true;
   for (int i=0;i<100;i++)
     same &= (a.nextInt()==b.nextInt());
   boolean rejected=false;
   try { ThreadLocalRandom.current().setSeed(1234L); }
   catch (UnsupportedOperationException e) { rejected=true; }
   System.out.println("seededRandomReproducible=" + same);
   System.out.println("threadLocalRandomSetSeedRejected=" + rejected);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RandomSeedContrastDemo.java
java RandomSeedContrastDemo
```

Stdout đã kiểm thử:

```text
seededRandomReproducible=true
threadLocalRandomSetSeedRejected=true
```

`Random(seed)` cho reproducibility; `ThreadLocalRandom` purposely không expose seed setter. Không vì vậy mà dùng `Random(seed)` để tạo password-reset token: deterministic seeded generators **không** đủ bảo mật.

## 22. Phân biệt random thông thường và crypto

`ThreadLocalRandom` **không** phải cryptographically secure PRNG. Nó hữu ích cho:

- Jitter không bảo mật, cân bằng randomized testing.
- Mô phỏng ngẫu nhiên có thể thay đổi mỗi lần chạy.
- Randomized work stealing / heuristic không quyết định quyền truy cập.
- Sampling telemetry không mang yêu cầu bí mật.
- Game logic không chống đối thủ dự đoán.

**Không dùng** `ThreadLocalRandom` cho:

- Session identifiers, password-reset links.
- CSRF tokens, API keys, invitation secrets.
- OTP secrets/keys, encryption keys hoặc salts cần nguồn mật mã.
- Giá trị dùng làm bằng chứng xác thực hoặc quyền truy cập.
- Lottery/gambling có adversarial fairness / regulation.
- Bất kỳ việc nào mà dự đoán đầu ra cho phép vượt kiểm soát an ninh.

Dùng `java.security.SecureRandom` khi threat model cần unpredictable output. Việc `SecureRandom` có API khác và seed management khác là **chủ đề riêng**; không gọi `setSeed` trên SecureRandom như cách bắt nó tạo reproducible test sequence.

## 23. Hiểu giới hạn random state trong thread pool

Một thread pool có thể tái sử dụng worker hàng nghìn lần:

```text
Worker #1:
  request A -> ThreadLocalRandom.current()
  request B -> ThreadLocalRandom.current()
  request C -> ThreadLocalRandom.current()

Worker #2:
  request D -> ThreadLocalRandom.current()
  request E -> ThreadLocalRandom.current()
```

Trạng thái PRNG gắn với thread, nên nó không tự reset giữa requests. Đừng suy ra:

- Request B có seed riêng biệt do default.
- Đổi kích thước worker pool không ảnh hưởng kết quả theo request.
- Ngắt thread sẽ reset PRNG seed.
- Task được retry sẽ dùng lại random sequence.
- Cùng application input sẽ cho cùng random outputs sau restart.

Nếu cần kết quả ổn định theo business input, tạo **explicit PRNG per request/task** bằng seed dẫn xuất có kiểm soát.

## 24. Ranh giới về reproducibility và version

Khả năng tái lập cần định nghĩa chính xác:

| Mục tiêu | Cách nên làm |
| --- | --- |
| Bảo đảm mỗi random value trong range | Assert bounds, không hardcode value |
| Cùng algorithm/seed tạo sequence giống | Seeded Random/SplittableRandom/RandomGenerator named |
| Đồng nhất trên mọi Java implementation trong mọi thời đại | Cần contract, pin algorithm/runtime và golden testing |
| Cùng output dù thread scheduling khác | Seed/stream state **per stable task ID**, không dùng ThreadLocalRandom |
| Replay một bug simulation | Ghi master seed, version, task mapping và dữ liệu đầu vào |
| Random secret khó đoán | SecureRandom, không yêu cầu reproducible/public seed |
| Bảo đảm IDs độc nhất tuyệt đối | Sequence/unique constraint/id allocator, không chỉ PRNG |

**Không mượn thread IDs làm task seeds** vì chúng có thể thay đổi khi executor được tái cấu hình.

## 25. Những sai lầm thường gặp

1. Gọi `new ThreadLocalRandom()` — không phải cách khởi tạo public được hỗ trợ.
2. Gọi `ThreadLocalRandom.current().setSeed(42)` — `UnsupportedOperationException`.
3. Cho rằng `ThreadLocalRandom.current()` tạo RNG mới cho mỗi method call.
4. Cho rằng trạng thái RNG mới được tạo cho từng HTTP request/task.
5. Dựa vào thread ID/name để định seed reproducible per business job.
6. Dùng ThreadLocalRandom với password reset/API token.
7. Test `nextInt(10) == 5` — phụ thuộc random state.
8. Test hai random values bắt buộc khác nhau — không có guarantee uniqueness.
9. Quên bound exclusive ở `nextInt(origin,bound)`.
10. Dùng `Math.abs(nextInt()) % bound` có rủi ro overflow/bias.
11. Truyền bounds bằng nhau hoặc đảo ngược — `IllegalArgumentException`.
12. Dùng một `SplittableRandom` shared qua nhiều threads không đồng bộ.
13. Dùng single shared seeded Random để yêu cầu per-task replay bất biến dù scheduling khác.
14. Nghĩ `setSeed` trên `SecureRandom` làm reset deterministic (không phải).
15. Dựa vào internal seed fields của JDK bằng reflection/Unsafe.
16. Dùng `ThreadLocal<T>` chứa user context trong pool mà quên `remove`.
17. Hiểu `ThreadLocalRandom` và `ThreadLocal<Random>` là cùng API.
18. Coi `RandomGeneratorFactory.isStochastic` là phép kiểm CSPRNG.
19. Coi cùng seed trên các thuật toán khác nhau phải cho cùng output.
20. Coi random jitter là cơ chế bảo mật chống replay.
21. Coi random values phân phối đều nghĩa random khó đoán đối thủ.
22. Dùng `System.currentTimeMillis()` làm seed rồi in/log như một secret.
23. Dùng `SplittableRandom.split()` đồng thời từ một instance shared mà không có ownership.
24. Hardcode thread scheduling order trong CI.
25. Dùng `ThreadLocalRandom.current()` trong test cần golden results.
26. Tự tạo quá nhiều PRNG object trong hot loops mà không đo performance.
27. Chọn global RNG khi mục tiêu thật sự là business-specific reproducibility.
28. Không phiên bản hóa thuật toán khi lưu simulation results lâu dài.
29. Cho rằng random thread-safe làm shared collections cũng thread-safe.
30. Không đặt chính sách xử lý seed/replay/logs phù hợp dữ liệu nhạy cảm.

## 26. Bài tập và đáp án

**1.** `ThreadLocalRandom.current()` dùng cho mục đích gì? **Random thông thường theo trạng thái thread hiện tại**.

**2.** `new ThreadLocalRandom()` có public constructor không? **Không**.

**3.** `ThreadLocalRandom.current().setSeed(123)`? **UnsupportedOperationException**.

**4.** ThreadLocalRandom có `getSeed()` public không? **Không**.

**5.** Có bảo đảm hai threads sinh số khác nhau ở cùng lượt không? **Không**.

**6.** Thread pool reuse có reset ThreadLocalRandom per task không? **Không có contract reset**.

**7.** `nextInt(2,7)` trả các số nào? **2,3,4,5,6**.

**8.** `nextInt(5,5)`? **IllegalArgumentException**.

**9.** Test ThreadLocalRandom bằng output cố định nên không? **Không**.

**10.** Có thể test bất biến nào? **Range, bound exceptions, correct data structures**.

**11.** Muốn reproducible test, chọn gì? **Seeded SplittableRandom/Random hoặc named RandomGenerator**.

**12.** Muốn reproducible parallel jobs dù scheduling khác? **Per stable task ID PRNG**.

**13.** Dùng thread name làm task ID có tốt không? **Không**.

**14.** `ThreadLocal<T>` có `remove()` không? **Có**.

**15.** `ThreadLocalRandom` có `remove()` public giống vậy không? **Không**.

**16.** Dùng `ThreadLocal<Random>` thay cho seeded per task có bắt buộc đúng không? **Không**, state theo thread vẫn khó replay theo job.

**17.** `RandomGeneratorFactory.isStochastic` có đảm bảo cryptographically strong? **Không**.

**18.** Một seeded `SplittableRandom` có tạo security token an toàn không? **Không**.

**19.** `SecureRandom` có tạo reproducible test sequence bằng `setSeed` không? **Không nên giả định; SecureRandom có seed/entropy policy riêng**.

**20.** `ThreadLocalRandom` có được dùng cho exponential backoff jitter thông thường? **Có, nếu jitter không cần bí mật và không cần replay**.

**21.** Số lần gọi nextInt trong một task ảnh hưởng state của thread không? **Có, nó tiêu thụ output/state**.

**22.** Nếu task chạy trên worker khác có chắc cùng random output? **Không**.

**23.** Cùng seed nhưng dùng Random và SplittableRandom cho giống chuỗi không? **Không**.

**24.** Dùng `Math.abs(Integer.MIN_VALUE)` có ra số âm không? **Có**, cần tránh modulo tùy tiện.

**25.** `nextDouble(0,1)` trả đúng 1.0 không? **Không, upper bound exclusive**.

**26.** Random per-thread có tự bảo vệ array shared được ghi sau đó không? **Không**.

**27.** Có nên so sánh RNG object `==` giữa threads để xác định seed isolation? **Không**, đó không phải contract cần dựa vào.

**28.** ThreadLocalRandom có tránh một số contention của shared Random không? **Có, đó là một lý do dùng**.

**29.** Muốn test chuỗi chính xác lâu dài, lưu gì? **Algorithm name/version, seed, task mapping và input**.

**30.** Muốn một identifier bảo đảm không trùng, chỉ dùng RNG được không? **Không, cần uniqueness policy/constraint**.

## 27. Checklist triển khai

- [ ] Chỉ dùng ThreadLocalRandom cho **non-security** randomness.
- [ ] Gọi `ThreadLocalRandom.current()` trong thread sử dụng.
- [ ] Không gọi new hoặc setSeed trên ThreadLocalRandom.
- [ ] Không giả định per-task state khi executor reuse workers.
- [ ] Random values được kiểm bằng range/invariants thay vì exact samples.
- [ ] Bounds origin inclusive, upper exclusive.
- [ ] Không tạo modulo bias/overflow qua Math.abs.
- [ ] Không dùng RNG làm khóa cho shared business state.
- [ ] Nếu cần deterministic replay, dùng PRNG seed rõ **per task**.
- [ ] Không chia sẻ SplittableRandom instance giữa threads không đồng bộ.
- [ ] Pin algorithm/version khi golden tests quan trọng.
- [ ] Không dùng thread IDs làm task seeds.
- [ ] Nếu dùng ThreadLocal<T> cho application context, cleanup bằng remove().
- [ ] Không lưu context người dùng sang task khác trong thread pool.
- [ ] Không dùng isStochastic như crypto-strength check.
- [ ] Mật mã dùng SecureRandom và threat modeling riêng.
- [ ] Không log raw token/secret hoặc secret seed.
- [ ] Bài test có thể chạy Java 17+ với output đáng tin.

## 28. Tài liệu Java chính thức

- [ThreadLocalRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): `current()`, per-thread random state, `setSeed` unsupported, bounds.
- [Random — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): seeded Random, thread-safe usage, inherited APIs.
- [ThreadLocal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread application context, `withInitial` và `remove`.
- [SplittableRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): seeded/splittable PRNG dùng cho parallel tasks, không crypto.
- [RandomGenerator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): RNG abstraction, Java 17.
- [RandomGeneratorFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): lựa chọn generator by name/seed, category info.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): thread pools, Futures và shutdown.
- [SecureRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): CSPRNG cho các bí mật và use cases có adversary.

**Tóm tắt:** `ThreadLocalRandom.current()` là cách hiệu quả để sinh số giả ngẫu nhiên **theo trạng thái thread** mà không chia sẻ một seed mutable cho mọi threads. API **không cho đặt seed** và **không hứa tái lập theo từng task**, đặc biệt với thread pools tái sử dụng workers. Hãy test bằng bất biến; nếu cần replay, tạo `SplittableRandom(seed)` hoặc named `RandomGenerator` **per task với ID ổn định**. Tuyệt đối không dùng ThreadLocalRandom để tạo bí mật mật mã: cần `SecureRandom`.