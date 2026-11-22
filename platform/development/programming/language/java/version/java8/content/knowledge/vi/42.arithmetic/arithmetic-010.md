# SplittableRandom và nguồn ngẫu nhiên cho tính toán

**`java.util.SplittableRandom`** là lớp sinh **số giả ngẫu nhiên** (*pseudorandom number generator — PRNG*) có mặt từ **Java 8**, đặc biệt hữu ích để hiểu cách cung cấp **nguồn số ngẫu nhiên riêng cho các tác vụ tính toán có thể phân nhánh**. Điểm nổi bật là phương thức **`split()`**: tạo một generator con có trạng thái thay đổi độc lập với generator cha. Cách dùng phù hợp là **mỗi tác vụ hoặc mỗi thread sở hữu riêng một generator**, chứ không chia sẻ một instance `SplittableRandom` giữa các thread.

**Cần biết khi dùng Java hiện đại:** Từ Java 17, JDK bổ sung `java.util.random.RandomGenerator`, `RandomGenerator.SplittableGenerator` và họ thuật toán **LXM**. Tài liệu package JDK hiện tại xếp `SplittableRandom` vào **nhóm PRNG “legacy” theo lịch sử thuật toán**, nhưng **class chưa bị loại bỏ và các method đang bàn vẫn được hỗ trợ**. Vì vậy bài học giải thích chính xác API `SplittableRandom` để đọc/vận hành code Java 8+ còn dùng nó, **không quảng bá thuật toán cũ này như mặc định tốt nhất cho phần mềm mới**. Khi thiết kế dự án Java 17+, nên đánh giá các generator hiện đại như **`L64X128MixRandom`** qua `RandomGeneratorFactory` và chỉ chọn thuật toán sau khi hiểu yêu cầu về thống kê, hiệu năng, khả năng tái lập và bảo mật.

Nội dung gồm: tạo và seed generator, `nextInt`/`nextLong`/`nextDouble` theo khoảng, `split` và **ownership** theo tác vụ, sinh streams, lập mô phỏng Monte Carlo, reproducibility trong xử lý song song, kiểm thử histogram, các sai lầm như `Math.random`/`new Random` chia sẻ hoặc modulo bias, lựa chọn PRNG hiện hành, và giới hạn bảo mật. Có **bảy chương trình Java 17+ độc lập, đã chạy kiểm tra với OpenJDK 24**; ví dụ ghi rõ API nào cần Java 17 thay vì Java 8.

## 1. Ngẫu nhiên thật và giả ngẫu nhiên khác nhau ở đâu?

Một PRNG là thuật toán tạo dãy giá trị từ **trạng thái nội bộ**. Khi đầu vào/thứ tự các lời gọi được giữ nguyên, một instance có seed xác định sẽ cho **dãy tái lập** trong cùng điều kiện thực thi. Dãy trông ngẫu nhiên trong các phép thống kê phù hợp nhưng vẫn là **deterministic computation**, không phải phép đo entropy vật lý.

Ví dụ tác vụ mô phỏng:
- Sinh một số từ 1 tới 6 để mô phỏng xúc xắc.
- Lấy tọa độ điểm đều trong hình vuông để xấp xỉ số π.
- Sinh các mẫu input cho thuật toán Monte Carlo.
- Chia nguồn PRNG cho những bài toán con theo worker.
- Tạo test data **không mang ý nghĩa bảo mật**.
- Dùng seed đã ghi nhận để tái chạy một thí nghiệm.

PRNG khác với **nguồn mật mã**: việc các giá trị có histogram trông đều không đủ đảm bảo không ai dự đoán được trạng thái. Token đăng nhập, reset-password, API key, nonce mật mã, salt cần đúng mô hình bảo mật — **không dùng `SplittableRandom`**.

Trong khoa học tính toán, đôi khi **khả năng tái lập** quan trọng ngang hoặc hơn việc một seed “khó đoán”. Việc lưu seed và partition ID giúp gỡ lỗi hoặc tái tạo một simulation. Nhưng seed một mình chưa đủ nếu lịch phân chia tác vụ hoặc thuật toán sinh số đã thay đổi.

## 2. SplittableRandom được thiết kế cho điều gì?

Theo JavaDoc hiện hành, `SplittableRandom`:
- Sinh `int`, `long`, `double` giả ngẫu nhiên với một số phương thức tương tự `Random`.
- Có chu kỳ của một dãy là **2^64**, theo mô tả class.
- Hỗ trợ `split()` tạo một `SplittableRandom` mới **không chia sẻ mutable state** với instance hiện tại.
- Hai generator cha/con có kỳ vọng về **đặc tính thống kê** giống các lần tạo giá trị độc lập thích hợp, với xác suất rất cao; đây không phải định lý “mọi giá trị khác nhau” hoặc bảo đảm không bao giờ va chạm.
- **Không thread-safe**: không được chia sẻ một instance để nhiều thread gọi `nextX` đồng thời.
- **Không cryptographically secure**.
- Có nguồn stream `ints`, `longs`, `doubles`, có cơ chế splitting khi dùng parallel stream.

Một thiết kế fork/join có thể hoạt động:
```text
Generator cha (owner: task A)
   ├─ sử dụng riêng trong task A
   ├─ split() → child B (owner: task B)
   │             └─ split() → child D (owner: task D)
   └─ split() → child C (owner: task C)
```

**Mỗi generator có một owner tại một thời điểm**. `split` không có nghĩa tạo hẳn một tập random bytes hoàn toàn độc lập theo nghĩa toán học tuyệt đối; nó thiết kế để giảm nguy cơ tương quan thống kê và tránh chia sẻ state.

Khi chia một task, hãy gọi `split()` **ở thread đang sở hữu parent** rồi chuyển child cho task con. Đừng để nhiều tasks cùng gọi `parent.split()` đồng thời trên một parent không đồng bộ.

## 3. Khởi tạo: constructor không seed và constructor có seed

```java
SplittableRandom variable = new SplittableRandom();

SplittableRandom seeded = new SplittableRandom(2026L);
```

Đây là snippet đặt trong method sau khi `import java.util.SplittableRandom;`.

`new SplittableRandom()` khởi tạo seed được chọn nội bộ, thông thường có thể thay đổi giữa các lần chạy. Nó phù hợp nếu không cần replay dựa vào một seed cụ thể. **Đừng in một giá trị từ default constructor rồi dùng làm output cố định cho unit test**: seed không do test kiểm soát.

`new SplittableRandom(long seed)` dùng seed được chỉ định. Ví dụ dùng `2026L` là một số `long`, không phải timestamp trong giao thức. Khi tạo hai generator bằng cùng seed và dùng cùng thứ tự API trong cùng điều kiện, dãy có thể tái lập; đây là cơ chế thích hợp để tạo các trường hợp test có thể chạy lại.

**Không có `setSeed(long)` trên `SplittableRandom` như ở `Random`.** Muốn bắt đầu lại từ seed, tạo **instance mới**. Sau mỗi lần `nextInt`/`split`, trạng thái instance tiến lên.

Cũng đừng nhầm default seed với cryptographic seed. JavaDoc cảnh báo: default construction không dùng nguồn seed mật mã trừ khi có cấu hình system property thích hợp; nhưng kể cả có seed khó đoán, **bản thân algorithm vẫn không phải CSPRNG**.

## 4. Tái lập không chỉ là nhớ một số seed

Để phát lại một dãy, thường cần giữ:
1. **Thuật toán/generator family** đã dùng.
2. Seed ban đầu của generator.
3. Thứ tự và loại lệnh gọi: `nextInt`, `nextLong`, `nextDouble`, `split`, các bound.
4. Cấu trúc chia task và thứ tự tạo generators con.
5. Phiên bản runtime hoặc kiểm tra tương thích khi đòi một golden output byte-for-byte trên nhiều JDK.
6. Cách xử lý floating-point/reduction nếu kết quả tổng hợp là số thực.
7. Tập dữ liệu và logic mô phỏng cùng phiên bản.

**Dùng cùng seed không đủ nếu thứ tự các lời gọi khác nhau.** Chỉ cần một lần `nextInt()` thêm ở nhánh logging/debug cũng có thể làm các giá trị tiếp theo dịch đi. Tương tự, `split()` tiêu thụ/biến đổi state, nên cách phân chia tasks ảnh hưởng dãy từng child.

Không nên định nghĩa “reproducibility” là “bất kể số thread, mọi lần chạy sẽ sinh đúng cùng một dãy theo lịch scheduler”. Muốn kết quả ổn định **theo work item**, gán một generator/seed cố định cho từng work item trước khi chạy song song.

## 5. `nextInt`, `nextLong`, `nextDouble`

| API | Kết quả |
| --- | --- |
| `nextInt()` | Một giá trị `int` giả ngẫu nhiên trên miền int |
| `nextInt(bound)` | `int` trong **[0, bound)**, bound phải dương |
| `nextInt(origin,bound)` | `int` trong **[origin, bound)** |
| `nextLong()` | Một giá trị `long` giả ngẫu nhiên |
| `nextLong(bound)` | `long` trong **[0, bound)**, bound phải dương |
| `nextLong(origin,bound)` | `long` trong **[origin, bound)** |
| `nextDouble()` | `double` trong **[0.0, 1.0)** |
| `nextDouble(bound)` | `double` trong **[0.0, bound)** với bound dương và hữu hạn |
| `nextDouble(origin,bound)` | `double` trong **[origin, bound)**, hai mốc hữu hạn và origin nhỏ hơn bound |

Ký hiệu **[a,b)** nghĩa là `a` **bao gồm**, `b` **loại trừ**. Đây là convention quan trọng khi mô phỏng xúc xắc, chọn chỉ số mảng, hoặc sampling trên khoảng giá trị.

Ví dụ:
```java
SplittableRandom random = new SplittableRandom(17L);

int die = random.nextInt(1, 7);    // 1..6
int index = random.nextInt(10);    // 0..9
long delta = random.nextLong(-5, 6); // -5..5
double ratio = random.nextDouble();  // 0.0 <= ratio < 1.0
```

Các biến local là kết quả của lệnh gọi theo thứ tự. **Không biết trước cụ thể một giá trị nếu không chạy cùng thuật toán và seed**, nhưng có thể đảm bảo chúng nằm trong khoảng hợp lệ.

Đừng dùng `nextInt(1,6)` để mô phỏng xúc xắc sáu mặt: nó chỉ sinh **1..5**. Không cộng 1 vào mọi result mà không kiểm tra bound — thêm thao tác không đúng có thể đưa kết quả ra ngoài miền mong muốn.

## 6. Vì sao nên dùng bounded API thay vì lấy modulo?

Một pattern dễ viết sai:

```java
int bad = Math.abs(random.nextInt()) % 6;
```

Đây là **phản ví dụ** trong method có `random`. Có nhiều rủi ro:
- `Math.abs(Integer.MIN_VALUE)` vẫn âm vì overflow `int`.
- Chia lấy dư `% 6` có thể tạo **modulo bias** nếu số trạng thái đầu vào không chia hết cho 6.
- Khi muốn 1..6 còn phải cộng 1 và kiểm soát dấu.
- Với `long` và range lớn, tính `bound-origin` không đúng kiểu có thể overflow.

Dùng:

```java
int die = random.nextInt(1, 7);
```

API sẽ sinh trong miền có hai biên đúng và xử lý kỹ thuật mapping/rejection cần thiết theo contract, thay vì áp phép modulo ngây thơ. Không cần tự viết vòng rejection sampling nếu chỉ muốn giá trị đồng đều trong một khoảng nguyên.

**Lưu ý thống kê:** một PRNG tốt vẫn chỉ mô phỏng phân phối đều theo giả định nguồn sinh. Bounded API không biến thuật toán thành cryptographic RNG, không loại bỏ mọi rủi ro sai mô hình và không bảo đảm histogram nhỏ sẽ chia đều chính xác.

## 7. Ví dụ 1 — cùng seed, cùng dãy và split có thể tái lập

Tạo `SeedReproDemo.java`:

```java
import java.util.Arrays;
import java.util.SplittableRandom;

public class SeedReproDemo {
    public static void main(String[] args) {
        SplittableRandom a = new SplittableRandom(2026L);
        SplittableRandom b = new SplittableRandom(2026L);

        int[] seqA = a.ints(8, 1, 11).toArray();
        int[] seqB = b.ints(8, 1, 11).toArray();

        System.out.println(
                "first=" + Arrays.toString(seqA));
        System.out.println(
                "same seed=" + Arrays.equals(seqA, seqB));

        SplittableRandom x = new SplittableRandom(42);
        SplittableRandom y = new SplittableRandom(42);

        SplittableRandom childX = x.split();
        SplittableRandom childY = y.split();

        System.out.println(
                "split child same seed=" +
                (childX.nextLong() == childY.nextLong()));

        System.out.println(
                "parent after split reproducible=" +
                (x.nextInt() == y.nextInt()));
    }
}
```

```bash
javac -encoding UTF-8 SeedReproDemo.java
java SeedReproDemo
```

Đầu ra đã chạy trên OpenJDK 24:

```text
first=[3, 2, 10, 8, 10, 3, 1, 8]
same seed=true
split child same seed=true
parent after split reproducible=true
```

Tại sao hai child được tạo từ hai parents cùng seed lại cho cùng một giá trị? Vì hai parents có **cùng trạng thái tại thời điểm gọi `split()`**, nên các child được tạo theo cùng quá trình. Đây là kiểm chứng của **replay**, không phải bảo đảm các children từ **cùng một parent được split ở các lần khác nhau** sẽ bằng nhau.

**Chú ý về golden output:** các con số cụ thể phản ánh thuật toán/triển khai trong môi trường đã kiểm tra. Với các yêu cầu tái lập qua nhiều phiên bản JDK hoặc một algorithm khác, lưu thông tin algorithm và kiểm tra version compatibility; đừng gắn một bài toán khoa học dài hạn vào các số demo mà chưa có kiểm chứng liên phiên bản.

## 8. Giới hạn khoảng nguyên, số thực và argument validation

Với `nextInt(origin,bound)`, cần `origin < bound`, dù origin có thể âm. Với `nextInt(bound)`, cần `bound > 0`. Các overload tương ứng cho long có nguyên tắc như vậy.

Với `double`, cần để ý `NaN`, `Infinity` và khoảng rỗng. Cú pháp:
```java
random.nextDouble(2.5, 3.5); // [2.5,3.5)
```

Nếu origin không hữu hạn, bound không hữu hạn hoặc origin >= bound, overload hai tham số ném `IllegalArgumentException`. Đây là lựa chọn API hiện hành an toàn hơn tự tính `origin + (bound-origin) * nextDouble()` mà không xét overflow, rounding, Infinity.

**Các sample double không được kỳ vọng chia đều chính xác từng real number**, vì `double` chỉ biểu diễn một tập rời rạc các giá trị nổi dấu phẩy động. Độ chính xác và rounding là đặc điểm của floating-point; nó không phải phân phối liên tục lý tưởng theo toán học.

**Cẩn thận với “bao gồm bound”**: muốn xúc xắc tới 6, dùng bound=7; với double thông thường nên giữ half-open interval theo API. Không tự `nextDouble(0,1+epsilon)` để lấy 1.0 vì điều đó thay đổi phân phối và có nguy cơ chọn sai epsilon.

## 9. Ví dụ 2 — kiểm tra các biên và lỗi input

Tạo `BoundsDemo.java`:

```java
import java.util.SplittableRandom;

public class BoundsDemo {
    public static void main(String[] args) {
        SplittableRandom r = new SplittableRandom(17);

        boolean valid = true;
        for (int i = 0; i < 10_000; i++) {
            int die = r.nextInt(1, 7);
            long offset = r.nextLong(-5L, 6L);
            double v = r.nextDouble(2.5, 3.5);

            valid &= die >= 1 && die < 7
                    && offset >= -5 && offset < 6
                    && v >= 2.5 && v < 3.5;
        }

        System.out.println("all within bounds=" + valid);

        try {
            r.nextInt(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("bound 0 rejected=true");
        }

        try {
            r.nextInt(9, 9);
        } catch (IllegalArgumentException ex) {
            System.out.println("origin==bound rejected=true");
        }

        try {
            r.nextDouble(Double.NaN, 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("NaN origin rejected=true");
        }

        try {
            r.nextLong(5L, 5L);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "long empty interval rejected=true");
        }

        try {
            r.ints(-1L, 1, 7);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "negative stream size rejected=true");
        }
    }
}
```

```bash
javac -encoding UTF-8 BoundsDemo.java
java BoundsDemo
```

```text
all within bounds=true
bound 0 rejected=true
origin==bound rejected=true
NaN origin rejected=true
long empty interval rejected=true
negative stream size rejected=true
```

Một vòng 10.000 lần giúp kiểm thử property **giá trị sinh ra nằm trong miền**, nhưng không chứng minh phân phối lý tưởng. Các trường hợp lỗi được bao trong `try/catch` để bài học tiếp tục chạy và thể hiện `IllegalArgumentException` đúng.

Với stream size âm, ngoại lệ được tạo khi gọi `ints(-1L,...)`. Không cần tiêu thụ stream mới biết tham số đếm phần tử không hợp lệ.

## 10. `split()`: tách một generator thành hai trạng thái riêng

API cốt lõi từ Java 8:

```java
SplittableRandom parent = new SplittableRandom(123L);

SplittableRandom child = parent.split();

int a = parent.nextInt(1, 7);
int b = child.nextInt(1, 7);
```

`parent` và `child` sau `split()` là **hai object khác nhau**, không dùng chung mutable state. Mỗi object có thể tiếp tục sinh số; mỗi object cũng có thể được split thêm để tạo cây PRNG.

Quan trọng:
- `split` **có ảnh hưởng tới state của parent**, nên thứ tự gọi split quan trọng cho replay.
- `split` không tạo một shared “pool” để thread nào cũng lấy giá trị ngẫu nhiên một cách thread-safe.
- `child` nên được chuyển cho một owner mới (thread/task) và không dùng tiếp trong parent nếu cùng lúc task con đang sử dụng.
- Khả năng sinh các dãy ít tương quan là **kỳ vọng thống kê**, không phải cam kết hai generator không bao giờ sinh cùng một số.
- “Independent state” là tính chất về **object state**, khác với một lời đảm bảo tuyệt đối về statistical independence.

Sơ đồ ownership:

```text
Thread A:
  parent = seeded PRNG
  childB = parent.split()
  childC = parent.split()
  submit Task B(childB)
  submit Task C(childC)
  tiếp tục dùng parent ở Thread A

Thread B chỉ sử dụng childB
Thread C chỉ sử dụng childC
```

Nếu application muốn xử lý 4 tasks cố định, một cách đơn giản là **split 4 children theo thứ tự task IDs rồi mới submit**. Sự phân tách xác định trước giúp output từng task không phụ thuộc vào thread nào được scheduler chạy trước.

## 11. Vì sao không nên chia sẻ một SplittableRandom giữa threads?

JavaDoc ghi rõ `SplittableRandom` **không thread-safe**. Khi hai thread cùng gọi `nextInt` lên cùng instance, state updates có thể race; thứ tự sinh số và trạng thái có thể không hợp lệ theo giả định của chương trình.

Phản ví dụ:

```java
// PHẢN VÍ DỤ: cùng đối tượng generator dùng ở nhiều threads.
SplittableRandom shared = new SplittableRandom(123);
executor.submit(() -> shared.nextInt());
executor.submit(() -> shared.nextInt());
```

Đây là snippet trong class có `ExecutorService executor`. Dù hai lời gọi đều trả một số int, **không có hợp đồng thread safety** và không nên dựa vào lịch chạy ngẫu nhiên để coi output là đúng.

Thay vào đó:

```java
SplittableRandom master = new SplittableRandom(123);
SplittableRandom forTaskA = master.split();
SplittableRandom forTaskB = master.split();

executor.submit(() -> forTaskA.nextInt());
executor.submit(() -> forTaskB.nextInt());
```

Phần tạo children được thực hiện **tuần tự trước khi submit** ở một thread sở hữu master. Từ đây mỗi task chỉ dùng instance của riêng mình.

Đừng giải quyết bằng `synchronized(shared)` theo phản xạ nếu mục đích là **hiệu năng song song**, vì sẽ đưa contention trở lại một tài nguyên chung và khiến kết quả phụ thuộc thứ tự các thread tranh khóa. Có thể đúng về an toàn nếu đồng bộ đầy đủ, nhưng thường đánh mất động cơ dùng `SplittableRandom`.

## 12. Reproducibility trong parallel tasks: gắn RNG với **work item**

Có hai mô hình dễ lẫn:
1. **Per-thread generator:** mỗi thread có RNG; phù hợp việc xử lý tùy ý nhưng kết quả gắn với worker được phân công. Thay số threads hoặc scheduling có thể thay thứ tự các số dùng cho mỗi work item.
2. **Per-work-item generator:** mỗi job ID có RNG riêng, tạo theo thứ tự xác định trước. Job được chạy bởi thread nào cũng dùng cùng RNG và cùng các lời gọi, nên có thể tái lập output theo job.

Nếu cần so sánh kết quả chạy sequential và parallel, cách thứ hai thường mạnh hơn.

Ví dụ:
- Dùng một master seed.
- Gọi `master.split()` bốn lần **ở caller thread**, theo thứ tự task 0,1,2,3.
- Mỗi task chạy đúng 10.000 lần `nextInt(1,7)` trên child của chính nó.
- Collect `Future` **theo thứ tự jobs**, không theo completion order.
- So với bản sequential tạo master từ cùng seed và chia children cùng thứ tự.

Khi thuật toán tính từng job là deterministic và không phụ thuộc shared mutable state, output từng job sẽ khớp. Không cần scheduler phải chạy jobs theo một thứ tự nhất định.

**Không đảm bảo** kết quả dạng floating-point giảm tổng song song theo một reduction tree bất kỳ luôn bitwise-identical với sequential, bởi phép cộng floating-point không kết hợp tuyệt đối. Muốn so sánh exact cần thiết kế reduction/order tương ứng.

## 13. Ví dụ 3 — chia child theo work item, chạy song song và tuần tự

Tạo `OwnedSplitTasksDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.SplittableRandom;

public class OwnedSplitTasksDemo {
    static List<Long> compute(
            boolean threaded) throws Exception {

        SplittableRandom master = new SplittableRandom(99L);
        List<Callable<Long>> jobs = new ArrayList<>();

        for (int i = 0; i < 4; i++) {
            SplittableRandom local = master.split();

            jobs.add(() -> {
                long total = 0;
                for (int n = 0; n < 10_000; n++) {
                    total += local.nextInt(1, 7);
                }
                return total;
            });
        }

        List<Long> output = new ArrayList<>();

        if (threaded) {
            ExecutorService pool =
                    Executors.newFixedThreadPool(4);

            try {
                for (Future<Long> f : pool.invokeAll(jobs)) {
                    output.add(f.get());
                }
            } finally {
                pool.shutdown();
            }
        } else {
            for (Callable<Long> job : jobs) {
                output.add(job.call());
            }
        }

        return output;
    }

    public static void main(String[] args) throws Exception {
        List<Long> serial = compute(false);
        List<Long> parallel = compute(true);

        System.out.println(
                "parallel per-job totals=" + parallel);
        System.out.println(
                "parallel equals serial=" +
                        serial.equals(parallel));
        System.out.println(
                "total=" +
                        parallel.stream()
                                .mapToLong(Long::longValue)
                                .sum());
    }
}
```

```bash
javac -encoding UTF-8 OwnedSplitTasksDemo.java
java OwnedSplitTasksDemo
```

```text
parallel per-job totals=[35336, 35082, 34952, 34998]
parallel equals serial=true
total=140368
```

**Vì sao output tái lập?** Hai lần gọi `compute` đều tạo cùng master seed `99L`, split ra 4 children theo cùng thứ tự, mỗi child dùng chỉ trong một Callable để cộng **10.000 lần gieo xúc xắc**. `invokeAll` trả danh sách `Future` theo thứ tự jobs đầu vào; code thu kết quả theo thứ tự đó. Scheduler có thể chạy job 3 trước job 0, nhưng mỗi job vẫn giữ child PRNG của chính mình.

Không chia sẻ một child cho hai jobs. Không dùng một `AtomicInteger` để tự tăng thứ tự lấy random từ master giữa nhiều threads rồi kỳ vọng tái lập theo task. Nếu thay số jobs, cách split sẽ thay; muốn thí nghiệm so sánh phải ghi **seed và partition scheme**.

## 14. Streams của SplittableRandom

Bên cạnh các lời gọi từng số, API Java 8 có:
- `ints()`: stream rất dài các `int` giả ngẫu nhiên.
- `ints(streamSize)`: stream giới hạn số phần tử.
- `ints(origin,bound)`: stream với khoảng giá trị.
- `ints(streamSize,origin,bound)`: giới hạn cả số lượng lẫn khoảng.
- Tương tự `longs()`/`longs(...)` và `doubles()`/`doubles(...)`.

Ví dụ:

```java
SplittableRandom r = new SplittableRandom(123);

int[] dice = r.ints(12, 1, 7).toArray();

long sum = r.longs(100, -5, 6).sum();

double average = r.doubles(10_000).average()
        .orElseThrow();
```

Đây là snippet trong method. **Các method stream là lazy**: giá trị được sinh khi terminal operation tiêu thụ. Một instance được dùng để tạo stream nên không đồng thời cho thread khác gọi `nextX` nếu không có protocol ownership rõ.

Các overload không có `streamSize` tạo một stream **hiệu quả là vô hạn**. Đừng gọi `r.ints().count()` rồi đợi hữu hạn; hãy dùng `limit(n)` hoặc tham số `streamSize`.

Ví dụ dùng `toArray()`/`sum()`/`average()` chỉ thích hợp với số lượng mẫu có kiểm soát; stream tạo hàng trăm triệu phần tử có thể tốn CPU/time ngay cả khi không cần lưu tất cả.

## 15. `ints(...).parallel()` có ý nghĩa gì?

Theo JavaDoc, stream sinh bởi `SplittableRandom` được thiết kế hỗ trợ **cơ chế splitting khi dùng parallel stream**. Thực thi có thể dùng các generator tách ra khi chia traversal cho nhiều worker.

Ví dụ:

```java
long count = new SplittableRandom(123)
        .ints(100_000, 1, 7)
        .parallel()
        .count();
```

Trong bài này, phép count có kết quả **100000** theo số phần tử đã khai báo; nhưng không nên dựa vào dãy từng phần tử trong một parallel stream **giống hệt thứ tự dãy sequential**. Việc stream bị chia/tiêu thụ có thể ảnh hưởng generator nào phát từng số.

**Không suy ra một `SplittableRandom` tự trở thành thread-safe vì một stream được gọi `parallel()`.** Hợp đồng của stream do class cung cấp có cơ chế splitting; việc bạn tự chia sẻ cùng instance trực tiếp cho các thread là câu chuyện khác.

Nếu cần **kết quả deterministic theo job IDs**, nên tạo các generators riêng có ownership rõ như ví dụ `OwnedSplitTasksDemo` thay vì dùng một parallel random stream và mong mỗi index nhận đúng một giá trị giống bản sequential trong mọi lịch.

## 16. Ví dụ 4 — finite streams và thống kê cơ bản

Tạo `StreamsAndStatisticsDemo.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.SplittableRandom;

public class StreamsAndStatisticsDemo {
    public static void main(String[] args) {
        SplittableRandom r = new SplittableRandom(123);

        System.out.println(
                "dice sample=" +
                        Arrays.toString(
                                r.ints(12, 1, 7).toArray()));

        System.out.println(
                "empty stream count=" +
                        new SplittableRandom(1)
                                .ints(0, 1, 7).count());

        int[] sample = new SplittableRandom(123)
                .ints()
                .limit(5)
                .toArray();

        System.out.println(
                "limit 5 count=" + sample.length);

        IntSummaryStatistics stats =
                new SplittableRandom(123)
                        .ints(100_000, 1, 7)
                        .parallel()
                        .summaryStatistics();

        System.out.println(
                "parallel count=" + stats.getCount());

        System.out.println(
                "parallel min/max valid=" +
                (stats.getMin() >= 1
                        && stats.getMax() <= 6));

        System.out.println(
                "sample and stream finite=" +
                        (stats.getCount() == 100_000));
    }
}
```

```bash
javac -encoding UTF-8 StreamsAndStatisticsDemo.java
java StreamsAndStatisticsDemo
```

```text
dice sample=[3, 2, 1, 1, 4, 1, 3, 4, 2, 6, 4, 1]
empty stream count=0
limit 5 count=5
parallel count=100000
parallel min/max valid=true
sample and stream finite=true
```

Bài test không kiểm tra các số cụ thể mà parallel stream đã sinh — điều ổn định theo **hợp đồng API** là đúng count và các giá trị thuộc khoảng `[1,7)`. Trong một run có seed cố định và cùng triển khai, dãy sequential đầu tiên có thể được lặp lại như ví dụ; với parallel stream không nên gắn regression vào thứ tự các số nếu không kiểm soát splitting.

`ints(0,1,7)` trả stream rỗng vì yêu cầu đúng 0 phần tử, khác với `ints()` không có giới hạn.

## 17. Monte Carlo là gì và vì sao hợp với PRNG?

Monte Carlo dùng nhiều **mẫu giả ngẫu nhiên** để xấp xỉ một đại lượng khó tính trực tiếp. Ví dụ kinh điển ước lượng π:

- Chọn `x`, `y` độc lập trong **[0,1)**.
- Điểm nằm trong góc phần tư hình tròn bán kính 1 khi `x*x + y*y <= 1`.
- Xác suất lý tưởng của điều kiện là diện tích góc phần tư hình tròn chia diện tích hình vuông đơn vị: **π/4**.
- Sau `N` điểm, đặt `hits` là số điểm nằm trong vùng tròn: **π ≈ 4 × hits / N**.

Công thức:

```text
N = 100000
hits = số lần x*x + y*y <= 1
estimatedPi = 4.0 * hits / N
```

Đây là một **ước lượng thống kê**, không phải phép tính π chính xác. Dùng nhiều mẫu thường giúp giảm sai số trung bình theo cỡ `1/sqrt(N)`, nhưng không đảm bảo từng lần tăng N luôn tiến gần π hơn. PRNG quality, cách tính và floating-point đều có vai trò.

Nguồn `SplittableRandom` thích hợp làm ví dụ Java 8 cho loại simulation **không đòi tính bảo mật**; với Java 17+ và mô phỏng nặng, nên so sánh với các PRNG mới hơn thuộc `java.util.random` theo tài liệu hiện hành.

## 18. Ví dụ 5 — Monte Carlo ước lượng π có thể phát lại

Tạo `PiMonteCarloDemo.java`:

```java
import java.util.Locale;
import java.util.SplittableRandom;

public class PiMonteCarloDemo {
    static long hits(long seed, int count) {
        SplittableRandom r = new SplittableRandom(seed);
        long hits = 0;

        for (int i = 0; i < count; i++) {
            double x = r.nextDouble();
            double y = r.nextDouble();

            if (x * x + y * y <= 1.0) {
                hits++;
            }
        }

        return hits;
    }

    public static void main(String[] args) {
        int n = 100_000;
        long hits = hits(12345, n);
        double pi = 4.0 * hits / n;

        System.out.println("samples=" + n);
        System.out.println("inside=" + hits);

        System.out.printf(
                Locale.ROOT,
                "estimated pi=%.5f%n", pi);

        System.out.println(
                "replay equal=" +
                        (hits == hits(12345, n)));

        System.out.println(
                "plausible=" +
                        (pi > 3.0 && pi < 3.3));
    }
}
```

```bash
javac -encoding UTF-8 PiMonteCarloDemo.java
java PiMonteCarloDemo
```

```text
samples=100000
inside=78644
estimated pi=3.14576
replay equal=true
plausible=true
```

`3.14576` là kết quả **một lần chạy đã kiểm tra trên OpenJDK 24** với seed và thuật toán cụ thể. Nó là ước lượng, không phải giá trị thật của π. Đừng yêu cầu mọi bản JDK/thuật toán cho cùng số chữ số trong tất cả điều kiện nếu chưa có contract portability.

`Locale.ROOT` giúp dùng dấu thập phân `.` nhất quán khi in. Điều này quan trọng khi viết stdout test hoặc dữ liệu kết quả để so sánh trong các môi trường có locale khác nhau.

Với mô phỏng có nhiều tasks, cho mỗi task **seed/split child riêng**, sau đó cộng `hits` dạng `long` theo thứ tự ổn định. Không chia sẻ generator mutable giữa các tasks. Với sample count rất lớn, kiểm tra tràn `int`/`long` khi cộng số mẫu.

## 19. Histogram: ngẫu nhiên đều không có nghĩa số lần bằng nhau

Gieo một xúc xắc công bằng `N=120000` lần thì **kỳ vọng** mỗi mặt xuất hiện `20000` lần, nhưng không bắt buộc đúng 20000 trong một lần mô phỏng.

Kiểm tra đơn giản:
- Sinh nhiều `nextInt(1,7)`.
- Đếm vào sáu bins.
- Kiểm tra không có giá trị ngoài `1..6`.
- Xem tổng bins bằng N.
- Xem mức chênh lệch giữa các bins có hợp lý đối với lượng mẫu.
- Nếu cần đánh giá nghiêm túc chất lượng PRNG, dùng bộ kiểm tra thống kê chuyên dụng; đừng suy tính an toàn từ một histogram nhỏ.

Một kết quả như `[19822,20149,...]` không chứng minh hoàn hảo, nhưng là test để phát hiện lỗi mapping, bound và data collection. Nếu dùng modulo thay vì bounded API, histogram ngắn vẫn có thể trông khá đều, nên không dùng mỗi histogram để chứng minh không có modulo bias.

## 20. Ví dụ 6 — đếm phân phối xúc xắc

Tạo `DistributionSanityDemo.java`:

```java
import java.util.Arrays;
import java.util.SplittableRandom;

public class DistributionSanityDemo {
    public static void main(String[] args) {
        SplittableRandom r = new SplittableRandom(321);
        int[] bins = new int[6];

        for (int i = 0; i < 120_000; i++) {
            bins[r.nextInt(1, 7) - 1]++;
        }

        System.out.println(
                "counts=" + Arrays.toString(bins));

        int minimum =
                Arrays.stream(bins).min().orElseThrow();
        int maximum =
                Arrays.stream(bins).max().orElseThrow();

        System.out.println(
                "total=" + Arrays.stream(bins).sum());
        System.out.println(
                "all bins populated=" + (minimum > 0));
        System.out.println(
                "spread=" + (maximum - minimum));
    }
}
```

```bash
javac -encoding UTF-8 DistributionSanityDemo.java
java DistributionSanityDemo
```

```text
counts=[19822, 20149, 20006, 20035, 19942, 20046]
total=120000
all bins populated=true
spread=327
```

Các bin counts được kiểm thử trên OpenJDK 24. `spread` là difference max-min, không phải metric chất lượng PRNG đủ mạnh để chọn thuật toán cho nghiên cứu. Với một thí nghiệm khoa học lớn, nên kiểm tra autocorrelation, independence, period và properties cần thiết riêng; khi cần đặc tính thống kê cao hơn, xem các thuật toán hiện đại thuộc `java.util.random`.

Vì `nextInt(1,7)` sinh 1..6, chỉ số bin được tính bằng `face-1` nên luôn nằm trong `0..5`. Đừng dùng `r.nextInt(7)` rồi trừ 1, sẽ có thể sinh -1.

## 21. Phân phối đều không thay thế mọi phân phối khác

`SplittableRandom.nextDouble()` cung cấp mẫu đều trên `[0,1)`. Nhiều bài toán lại cần phân phối **không đều**:
- Gaussian/normal cho nhiễu đo đạc.
- Exponential cho một số mô hình thời gian chờ.
- Poisson cho số lần xảy ra sự kiện trong khoảng thời gian.
- Weighted categorical sampling cho xác suất không bằng nhau.
- Uniform sampling trên một miền hình học không phải hình chữ nhật.

Không được dùng `nextInt(1,7)` để mô hình một xúc xắc có trọng số nếu xác suất từng mặt khác nhau. Cần một phương pháp sampling đúng theo phân phối mong muốn.

**Phân biệt phiên bản:** từ Java 17, `SplittableRandom` implement `RandomGenerator` và có thể thừa hưởng các phương thức mặc định hiện hành như `nextGaussian`/`nextExponential`. **Không dạy rằng mọi phương thức mới này đã có trên `SplittableRandom` của Java 8**. Với ứng dụng Java 17+, cân nhắc thiết kế theo interface `RandomGenerator` và thuật toán thích hợp; nếu cần thư viện phân phối xác suất chuyên biệt, lựa chọn theo mô hình thống kê thay vì tự ghép đại vài lần nextDouble.

## 22. RandomGenerator API từ Java 17 thay đổi thiết kế thế nào?

`java.util.random` là package được giới thiệu trong **JDK 17** để cung cấp một framework thống nhất cho các PRNG. Các interface quan trọng:
- `RandomGenerator`: hợp đồng sinh số giả ngẫu nhiên và nhiều phương thức bounded/stream.
- `RandomGenerator.SplittableGenerator`: hỗ trợ `split()` để tạo generator mới cho tác vụ.
- `RandomGenerator.StreamableGenerator`: tạo streams các generators cho lập trình song song.
- `RandomGeneratorFactory`: tạo instance theo tên algorithm, có thể khám phá lựa chọn.

`SplittableRandom` đã có từ Java 8, và trên JDK 17+ implements các interface phù hợp. Tuy nhiên tài liệu `java.util.random` **xếp SplittableRandom vào nhóm legacy** cùng các generator cũ; đó là phân loại theo **họ thuật toán tồn tại trước JDK 17**, không tự có nghĩa class bị xóa khỏi Java hay code đang dùng nó bỗng không chạy.

**Lựa chọn hiện đại cho code mới:** package Java SE hiện hành nêu `L64X128MixRandom` như thuật toán có cân bằng tốt về hiệu năng, trạng thái và period cho nhiều use case không yêu cầu mật mã. Các LXM khác thích hợp khi cần period hoặc đặc tính tương quan khác. Không suy từ điều đó rằng một thuật toán thắng mọi workload; hãy tham khảo tài liệu, yêu cầu mô phỏng và benchmark.

Nếu dự án bắt buộc chạy trên Java 8, `RandomGeneratorFactory` và các LXM interfaces **không khả dụng** ở runtime đó. Trong phạm vi Java 8, `SplittableRandom` và `split()` vẫn là kiến thức vận hành hợp lệ cho thuật toán hiện có; với yêu cầu nâng cấp, đây là điểm để lên kế hoạch migration.

## 23. So sánh các nguồn random trong Java hiện tại

| Lựa chọn | Mục đích | Giới hạn/cảnh báo |
| --- | --- | --- |
| `SplittableRandom` | Java 8+ simulation, fork/join có child RNG riêng | Legacy family theo Java 17+, không thread-safe, không CSPRNG |
| `RandomGeneratorFactory.of("L64X128MixRandom")` | Java 17+ non-crypto simulation với generator LXM hiện đại | Chọn và quản lý owner; không thread-safe theo mặc định |
| `ThreadLocalRandom.current()` | Lấy RNG gắn thread hiện tại, giảm contention so với shared Random | Không seed dễ dàng cho replay per-task; không mật mã |
| `java.util.Random` | Code cũ cần tương thích API/seeding của Random | Thuật toán truyền thống trong legacy group, không phải khuyến nghị mặc định về statistical quality |
| `SecureRandom` | Token, key/nonce/salt thuộc phạm vi bảo mật | Chi phí khác, phụ thuộc provider; cần thiết kế cryptographic workflow đúng |
| `Math.random()` | Convenience số `double` nhanh cho logic đơn giản | Không kiểm soát seed/partition per task theo API, không phù hợp replay quy mô lớn |
| `RandomGenerator` interface | Tách code tiêu thụ random khỏi thuật toán cụ thể | Java 17+; mỗi concrete implementation có contract/state riêng |

Đối với chương trình non-crypto và phát triển mới trên JDK 17+, nên **lập trình qua `RandomGenerator` hoặc `SplittableGenerator`** thay vì buộc mọi method phải nhận đúng `SplittableRandom`, nếu không cần một phương thức cụ thể của class cũ. Điều này giúp đổi algorithm khi có kết quả benchmark và đánh giá thống kê mới.

**SecureRandom không phải thuật toán mô phỏng mặc định** chỉ vì “random càng bảo mật càng tốt”; nó thuộc use case cryptographic và có trade-off riêng. Ngược lại, **SplittableRandom/LXM không dùng cho token bảo mật** dù seed có vẻ bí mật hoặc nhiều bytes.

## 24. Ví dụ 7 — generator LXM hiện đại qua RandomGeneratorFactory

Tạo `ModernRngDemo.java` (yêu cầu **JDK 17+**):

```java
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class ModernRngDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(
                        "L64X128MixRandom");

        RandomGenerator a = factory.create(123L);
        RandomGenerator b = factory.create(123L);

        System.out.println(
                "algorithm=" + factory.name());

        System.out.println(
                "seed repeatable=" +
                        (a.nextLong() == b.nextLong()));

        System.out.println(
                "supports splitting=" +
                        (a instanceof
                                RandomGenerator.SplittableGenerator));

        RandomGenerator.SplittableGenerator p =
                (RandomGenerator.SplittableGenerator)
                        factory.create(123L);

        RandomGenerator child = p.split();

        System.out.println(
                "child is generator=" + (child != null));
        System.out.println(
                "split stream size=" + p.splits(4).count());

        System.out.println(
                "legacy SplittableRandom supported=" +
                        (new SplittableRandom(123L)
                                instanceof RandomGenerator
                                        .SplittableGenerator));
    }
}
```

```bash
javac -encoding UTF-8 ModernRngDemo.java
java ModernRngDemo
```

```text
algorithm=L64X128MixRandom
seed repeatable=true
supports splitting=true
child is generator=true
split stream size=4
legacy SplittableRandom supported=true
```

Giải thích:
- `RandomGeneratorFactory.of("L64X128MixRandom")` chọn một thuật toán LXM cụ thể, không mặc định vào một implementation không nêu tên.
- Hai generators tạo cùng algorithm và seed cho cùng kết quả khi gọi `nextLong` tương ứng.
- LXM cụ thể này supports splitting; ép sang `SplittableGenerator` cho phép `split` và `splits(4)`.
- `splits(4).count()` đếm **bốn generator được tạo từ stream**, không phải bốn số nguyên ngẫu nhiên.
- `SplittableRandom` vẫn implements interface splitting trong JDK 17+ dù được xếp nhóm legacy.

**Cần phân biệt API availability:** đoạn này **không chạy trên Java 8**, vì package `java.util.random` chỉ xuất hiện ở Java 17. Trong Java 8, dùng concrete `SplittableRandom` với `split()` và các `ints`/`longs`/`doubles` theo code ở các phần trước.

Không tự động cast mọi `RandomGenerator` sang `SplittableGenerator`; hãy kiểm tra `instanceof` hoặc chọn một factory algorithm đã được document hỗ trợ splitting.

## 25. Các phương thức Java 17+ không nên gán ngược cho Java 8

| Khả năng | Java 8 SplittableRandom | JDK 17+ |
| --- | --- | --- |
| Constructor `SplittableRandom(long seed)` | Có | Có |
| `nextInt`, `nextLong`, `nextDouble`, bounded overloads | Có | Có |
| `split()` không tham số | Có | Có |
| `ints`, `longs`, `doubles` và size/range overloads | Có | Có |
| `nextBytes(byte[])` | **Chưa có ở Java 8** (được bổ sung sau đó) | Có |
| `RandomGenerator` interface | Không | Có |
| `RandomGenerator.SplittableGenerator` | Không | Có |
| `RandomGeneratorFactory` | Không | Có |
| `SplittableRandom.splits(n)` generator stream | Không | Có |
| `RandomGenerator` default methods như `nextGaussian` | Không qua interface mới | Có theo API JDK 17+ |
| `L64X128MixRandom` | Không | Có |

Việc học một module tên “Java 8” không buộc ta xem Java 8 là runtime tốt nhất cho ứng dụng mới. Nó có nghĩa các khái niệm gốc từ Java 8 được giải thích và phân biệt với API hiện đại **không bị lẫn phiên bản**.

JDK 17+ đã có các lựa chọn PRNG mới được nghiên cứu để nâng cao statistical properties. Khi nâng cấp hệ thống, đánh giá khả năng chạy lại nghiên cứu cũ: **đổi algorithm có thể đổi toàn bộ dãy random ngay cả khi seed giữ nguyên**. Không thay nguồn RNG âm thầm rồi so sánh golden outputs cũ theo từng số.

## 26. Reproducibility và test science: nhiều mức “giống nhau”

Phân biệt:
1. **Same-seed, same-generator, same-call-order**: mục tiêu dãy giống nhau trong môi trường tương ứng.
2. **Same seed nhưng khác algorithm**: không yêu cầu giống dãy.
3. **Same seed nhưng khác split tree**: child RNG và kết quả theo task có thể thay đổi.
4. **Same seed nhưng khác số workers**: kết quả có thể đổi nếu owner là thread thay vì work item.
5. **Same stochastic model nhưng khác seed**: kết quả mẫu khác, song thống kê kỳ vọng gần nhau khi đủ mẫu.
6. **Same source nhưng parallel floating-point sum**: thứ tự cộng khác có thể tạo chênh lệch last bits.
7. **Same distribution nhưng hardware/JDK khác**: cần kiểm tra implementation, floating-point mode và version cho yêu cầu exact.

Trong CI, phù hợp hơn khi viết property tests như:
- Mọi `nextInt(1,7)` nằm trong 1..6.
- Các generators có cùng seed và cùng use sequence cho kết quả giống nhau.
- Task-level results từ generator riêng trùng khi chạy sequential/parallel với cùng partition scheme.
- Một số thống kê Monte Carlo nằm trong khoảng dung sai có cơ sở, **không** assert luôn chính xác π tới nhiều chữ số.
- Không chia sẻ generator mutable giữa tasks.

**Không dùng random test data không ghi seed** rồi để test thỉnh thoảng fail mà không tái tạo được. Khi fail, log **seed và test case ID**, nhưng không log secrets hoặc dữ liệu nhạy cảm của user.

## 27. Quản lý seed cho job có thể chạy lại

Một quy trình thực tế:
1. Chọn **master seed** (ví dụ `long 20261106L`) và lưu trong metadata job.
2. Ghi **algorithm name** và JDK/build version nếu yêu cầu reproducibility dài hạn.
3. Xác định danh sách work item IDs theo thứ tự ổn định.
4. Tạo child generators sequentially qua `split()` hoặc dùng một strategy deterministic seed derivation đã được thiết kế/test riêng.
5. Chuyển mỗi child cho đúng work item, không chia sẻ mutable RNG.
6. Không làm thay đổi thứ tự tạo children chỉ vì scheduler hoặc queue.
7. Thu kết quả theo order được định nghĩa.
8. Ghi model parameters, version input data và kết quả thống kê.
9. Nếu migrate từ SplittableRandom sang LXM, lưu algorithm trong metadata và chấp nhận số mẫu khác.
10. Nếu cần statistical reproducibility thay vì bitwise, xác định tolerance và cách kiểm định.

Không tự lấy `System.nanoTime()` ở mỗi task như một giải pháp tái lập: không thể replay, cũng không bảo đảm seed khác biệt theo cách phù hợp với mọi thiết kế.

`split()` tiện dụng khi task tree được quyết định theo thứ tự rõ, nhưng nếu job IDs được tạo động và phải độc lập hoàn toàn với thứ tự xuất hiện, một cơ chế **derive seed by stable ID** có thiết kế riêng có thể phù hợp hơn. Phải đánh giá chất lượng mixing và collisions, không chỉ viết `masterSeed + id` rồi tuyên bố an toàn trong mọi trường hợp.

## 28. Bảo mật: tuyệt đối không dùng SplittableRandom cho secrets

Các trường hợp **không dùng** `SplittableRandom`, `Random`, `ThreadLocalRandom` hoặc LXM PRNG thông thường:
- Sinh **password reset token** hoặc magic login link.
- Sinh session secret, API key hoặc OAuth state cần unpredictability.
- Sinh salt/IV/nonce mật mã khi giao thức yêu cầu randomness/security properties.
- Sinh private key hoặc các bytes cung cấp entropy cho key derivation.
- Sinh verification code nếu đối thủ có thể khai thác tính dự đoán của output.
- Sinh dữ liệu bí mật chỉ dựa vào một seed “khó đoán”.

Dùng `java.security.SecureRandom` hoặc thư viện mật mã chuyên dụng có thiết kế đúng cho use case. `SecureRandom` có provider, seed strategy và API riêng; cần tuân thủ hướng dẫn bảo mật của hệ thống, không chỉ thay class name.

**Không hiểu nhầm** rằng `java.util.secureRandomSeed=true` biến SplittableRandom thành cryptographically secure. Property này liên quan nguồn seed mặc định, **không nâng cấp thuật toán** thành CSPRNG.

Nếu dữ liệu được lưu/đăng trong log, một seed không phải lúc nào cũng là secret, nhưng có thể tiết lộ cách tái tạo simulation. Với nhiệm vụ cần security, thiết kế threat model riêng thay vì lấy yêu cầu tái lập của Monte Carlo áp vào token generation.

## 29. ThreadLocalRandom và SplittableRandom: khác mục tiêu

`ThreadLocalRandom.current()` cho generator gắn thread hiện tại. Nó hữu ích khi mỗi thread muốn sinh vài số mà **không cần điều khiển seed** và không muốn tranh chấp một `Random` object chung.

`SplittableRandom` phù hợp khi một computation **fork thêm subtasks** và muốn phát các child generators riêng cho chúng. Nó hỗ trợ **seed cụ thể** để test và cách phân nhánh rõ qua `split()`.

| Câu hỏi | ThreadLocalRandom | SplittableRandom |
| --- | --- | --- |
| Dùng trực tiếp từ nhiều threads trên một instance? | Mỗi thread gọi `current()` của mình | Không chia sẻ instance; mỗi thread sở hữu child |
| Cần explicit seed để replay per-task? | Không phải thế mạnh | Có constructor `long seed` và split strategy |
| Có `split()`? | Không phải API công khai thông thường để chia cho jobs | Có |
| Tự an toàn cho cryptographic secrets? | Không | Không |
| Dễ dùng trong thread pool khi không cần replay? | Có | Cần ownership và setup rõ |
| Chọn cho code Java17+ mới? | Đánh giá cùng các PRNG hiện đại | Cân nhắc legacy classification và LXM |

**Đừng nhầm “ThreadLocalRandom không cần tự chia sẻ” với “đã có determinism theo work item”.** Khi task A hôm nay chạy trên thread 1 và ngày mai thread 3, dãy lấy từ ThreadLocalRandom có thể khác dù inputs khác không đổi.

## 30. Hiệu năng: đo đúng hơn là đoán

Không có nguồn ngẫu nhiên nào nhanh nhất trong tất cả workload. Đo:
- Số lần gọi `nextX` mỗi job.
- Tỷ lệ tạo/split generator so với thời gian simulation.
- Số tasks và số CPU cores thực.
- Lịch phân chia workload và memory locality.
- Lock contention nếu ai đó chia sẻ một generator và dùng synchronized.
- Distribution type và bound (một số phép rejection có chi phí khác nhau).
- Tỷ lệ overhead cho PRNG vs phần tính toán khoa học chính.
- Sự khác biệt giữa single-thread, parallel stream và per-task generator.
- Phân phối/period requirements của mô hình.
- Kết quả khi dùng `L64X128MixRandom` hoặc các LXM khác thay SplittableRandom.

Nếu cần microbenchmark JVM, dùng **JMH** thay cho `System.nanoTime` quanh vài vòng lặp mà không warmup. Compiler có thể tối ưu các giá trị không được tiêu thụ, khiến benchmark giả nhanh. Không gắn profiler hoặc logging quá nặng trong hot loop rồi coi đó là overhead thuật toán RNG.

**Correctness trước, speed sau**: một generator nhanh nhưng bị chia sẻ không đúng giữa threads có thể làm hỏng tính hợp lệ của simulation. Một thuật toán chất lượng cao hơn nhưng được gán seed sai cũng có thể tạo các kết quả tương quan ngoài ý muốn.

## 31. Những sai lầm phổ biến và cách sửa

| Sai lầm | Tại sao nguy hiểm? | Cách phù hợp |
| --- | --- | --- |
| Dùng một `SplittableRandom` instance cho mọi threads | Class không thread-safe | Split per-task, ownership rõ |
| Cho rằng `split` tạo ra hai dãy **không có giá trị trùng** | Sai tính chất xác suất | Hiểu “đặc tính thống kê tốt với xác suất cao” |
| Gọi `split()` đồng thời từ nhiều threads trên parent | Parent bị chia sẻ mutable state | Split ở owner thread trước submit |
| Cho rằng same seed đủ cho parallel replay | Lịch phân task/call-order thay đổi | Gắn RNG theo work item ID |
| Khởi tạo RNG ở mỗi vòng lặp | Tăng chi phí, mất kiểm soát seed | Tái dùng RNG trong scope owner |
| `Math.abs(nextInt()) % n` | MIN_VALUE overflow, modulo bias | `nextInt(n)` |
| `nextInt(1,6)` cho xúc xắc | Bound exclusive, không có mặt 6 | `nextInt(1,7)` |
| `nextInt(0)` | Bound phải dương | Validate before call |
| `nextInt(7,7)` | Khoảng rỗng | origin < bound |
| `nextDouble(NaN,1)` | NaN không hữu hạn | Valid finite bounds |
| `ints()` rồi `count()` không giới hạn | Stream effectively unbounded | `ints(n)` / `limit(n)` |
| Dùng `parallel` rồi test exact same sequence như sequential | Splitting/scheduling có thể đổi dãy | Test bounds/stats hoặc per-job RNG |
| Dùng `ThreadLocalRandom` và mong explicit seed/replay theo job | Thread-bound, không job-bound | Generator có seed theo task |
| Đổi sang LXM nhưng test exact output SplittableRandom | Khác thuật toán | Ghi algorithm/version, update protocol |
| Gọi API `java.util.random` trong Java 8 | Chỉ có từ Java 17 | Tách code theo minimum JDK |
| Cho rằng `nextBytes` là method SplittableRandom Java 8 | Bổ sung sau Java 8 | Version-check |
| Coi PRNG là mật mã vì seed khó đoán | Không CSPRNG | `SecureRandom` cho secrets |
| Dùng `secureRandomSeed` để “nâng cấp” SplittableRandom | Chỉ liên quan nguồn seed | Chọn CSPRNG thật |
| So sánh Monte Carlo với π chính xác từng lần | Có sai số lấy mẫu | Tolerance/statistical CI |
| Histogram hơi lệch rồi cho RNG hỏng | Sampling noise tự nhiên | Kích thước mẫu/test thống kê thích hợp |
| Histogram nhìn đều rồi cho crypto-safe | Không chứng minh unpredictability | Threat model/cryptographic testing |
| Giữ seed nhưng thay số lượng tasks và đòi exact output | Split tree đã đổi | Partition scheme cố định |
| Dùng floating-point reduction parallel rồi đòi exact bit equality | Thứ tự cộng không associative tuyệt đối | Cố định reduction/so tolerance |
| Không ghi algorithm, seed và config | Không tái tạo được bug | Metadata thực nghiệm |
| Dùng fixed seed trong security tokens | Dễ bị dự đoán | SecureRandom + threat model |
| Nhầm `SplittableRandom` legacy với đã bị remove | Nó vẫn là API được hỗ trợ | Dạy đúng API kèm modern alternatives |
| Coi SplittableRandom là PRNG khuyến nghị mặc định JDK26 | JDK giới thiệu LXM chất lượng cao hơn | Cân nhắc `RandomGeneratorFactory` |

## 32. Checklist code review cho tính toán ngẫu nhiên

1. Số liệu cần **cryptographic unpredictability** hay chỉ statistical simulation?
2. Đang dùng algorithm nào, version JDK nào, có được ghi lại không?
3. Nếu code mới trên JDK 17+, đã đánh giá `RandomGenerator` và thuật toán LXM chưa?
4. Với Java 8, đang dùng `SplittableRandom` như class hiện có với API đúng phiên bản chứ?
5. Seed có cố định/log hợp lý để tái lập các lỗi không?
6. Có nhầm seed với bí mật/entropy mật mã không?
7. Có đảm bảo **mỗi instance một owner** hoặc một protocol đồng bộ được chứng minh không?
8. `split()` có được gọi ở owner thread, không chia parent cho nhiều threads?
9. Đã map child generator tới **work item** cố định trước khi chạy parallel?
10. Có tránh phụ thuộc hoàn toàn vào scheduler trong reproducibility?
11. Bounded range `[origin,bound)` có đúng business rule?
12. Có dùng API bounded thay cho `Math.abs(nextInt()) % n`?
13. Có kiểm tra bound invalid/NaN/Infinity và stream size âm?
14. Infinite random streams có được giới hạn trước terminal operation?
15. Có để side effects ngoài generator như mutable shared accumulator làm sai parallel results?
16. Có test same-seed same-call-order và deterministic task partition?
17. Có test miền giá trị và đủ sample cho những kiểm tra thống kê phù hợp?
18. Với floating-point, có đặt tolerance/reduction order thay vì so exact vô điều kiện?
19. Với Monte Carlo, có báo uncertainty thay vì in số chính xác giả?
20. Có benchmark trên workload thật trước khi tối ưu?
21. Có tránh API Java 17+ trong module compile Java 8 không?
22. Có tránh sử dụng PRNG thường cho token, key hoặc nonce bảo mật?
23. Có metadata mô tả algorithm, seed, task partition, model version?
24. Có kế hoạch migration/compatibility khi thay PRNG algorithm?

## 33. Câu hỏi tự kiểm tra

**Câu 1.** `SplittableRandom` có từ phiên bản nào?  
**Đáp án:** Java 8. Nó vẫn được hỗ trợ, nhưng thuộc nhóm PRNG legacy trong tài liệu `java.util.random` của Java 17+.

**Câu 2.** Tại sao gọi là pseudorandom?  
**Đáp án:** Giá trị được tạo bởi thuật toán với trạng thái/seed, chứ không phải entropy vật lý trực tiếp.

**Câu 3.** Có nên dùng một instance cho nhiều thread không?  
**Đáp án:** Không, class không thread-safe; mỗi task/thread nên sở hữu một generator riêng.

**Câu 4.** `split()` trả gì?  
**Đáp án:** Một `SplittableRandom` mới không chia sẻ mutable state với parent.

**Câu 5.** Split có bảo đảm hai generators không bao giờ trả cùng một số không?  
**Đáp án:** Không. API nói về khả năng có các đặc tính thống kê tốt, không loại trừ trùng output.

**Câu 6.** Hai generators cùng seed có bảo đảm same sequence khi lời gọi tương ứng giống nhau không?  
**Đáp án:** Đó là cơ sở replay trong cùng algorithm/điều kiện, nhưng phải xét version, call order và split pattern.

**Câu 7.** Vì sao `nextInt(1,7)` mô phỏng sáu mặt?  
**Đáp án:** `1` được bao gồm, `7` bị loại trừ, nên kết quả 1..6.

**Câu 8.** `nextDouble()` có thể trả 1.0 không?  
**Đáp án:** Không theo contract `[0.0,1.0)`.

**Câu 9.** `Math.abs(nextInt()) % 6` có gì sai?  
**Đáp án:** `Integer.MIN_VALUE` và modulo bias; nên dùng bounded API.

**Câu 10.** `nextInt(0)` và `nextInt(5,5)` có hợp lệ không?  
**Đáp án:** Không, ném IllegalArgumentException.

**Câu 11.** Dùng một parent để `split` trong các tasks đang chạy đồng thời có nên không?  
**Đáp án:** Không; hãy split ở owner trước khi chuyển child.

**Câu 12.** Muốn sequential và parallel cùng kết quả theo task phải làm gì?  
**Đáp án:** Gán child generator theo job ID và cố định thứ tự split/lời gọi, không theo lịch thread.

**Câu 13.** `ints()` tạo finite stream không?  
**Đáp án:** Không có giới hạn nhỏ tự động; dùng `ints(n)` hoặc `limit(n)`.

**Câu 14.** `parallel()` trên random stream có bắt buộc cùng dãy với sequential không?  
**Đáp án:** Không nên dựa vào điều đó; splitting có thể thay pattern tiêu thụ.

**Câu 15.** Monte Carlo π dùng điều kiện gì?  
**Đáp án:** Lấy x,y trong [0,1); nếu x²+y²<=1 thì đếm hit; pi≈4*hits/N.

**Câu 16.** Vì sao ước lượng π khác π thật?  
**Đáp án:** Có sai số lấy mẫu và floating-point; thêm mẫu chỉ cải thiện về xác suất.

**Câu 17.** Một histogram 120.000 lần phải có mỗi mặt đúng 20.000 không?  
**Đáp án:** Không. 20.000 là kỳ vọng; các counts dao động.

**Câu 18.** `RandomGeneratorFactory` có trong Java 8 không?  
**Đáp án:** Không; package `java.util.random` có từ JDK 17.

**Câu 19.** Tên một LXM phù hợp để đánh giá cho code mới là gì?  
**Đáp án:** `L64X128MixRandom`, theo hướng dẫn của package `java.util.random` hiện hành.

**Câu 20.** SplittableRandom có dùng cho API token không?  
**Đáp án:** Không. Dùng `SecureRandom`/cryptographic library với thiết kế bảo mật đúng.

**Câu 21.** Default constructor có tạo cùng dãy mỗi lần app chạy không?  
**Đáp án:** Không có bảo đảm đó; khi cần replay dùng explicit seed.

**Câu 22.** Giữ seed nhưng thay số work items có thể đổi output không?  
**Đáp án:** Có, vì cách tạo/chia generators và thứ tự calls có thể đổi.

**Câu 23.** `RandomGenerator.SplittableGenerator` có phải chỉ dành cho SplittableRandom không?  
**Đáp án:** Không, nhiều LXM generators hiện đại cũng triển khai.

**Câu 24.** Cần ghi gì để phát lại thí nghiệm?  
**Đáp án:** Algorithm, seed, JDK/build khi cần, model version, input, split tree/partition và call order.

## 34. Tổng kết kiến thức còn áp dụng

- **`SplittableRandom` là PRNG Java 8 hỗ trợ `split()`**, vẫn chạy và có API hợp lệ trong Java hiện nay.
- **Class không thread-safe**: không chia sẻ một generator cho nhiều threads. Hãy split và giao child generator cho từng task.
- `nextInt`, `nextLong`, `nextDouble` có các overload với khoảng **[origin,bound)**, tránh lỗi off-by-one và modulo bias.
- **Same seed + same algorithm + same call/split order** là nền tảng replay; scheduling có thể làm lệch kết quả nếu generator gắn theo thread thay vì theo work item.
- Dùng finite streams hoặc `limit`, tránh terminal operation trên infinite random stream.
- Monte Carlo và histogram giúp học thống kê, nhưng kết quả mẫu có sai số và không tự chứng minh RNG an toàn bảo mật.
- **Không dùng SplittableRandom cho secrets**: dùng `SecureRandom` hoặc các API mật mã phù hợp.
- Java 17+ có `RandomGenerator`, `SplittableGenerator` và các thuật toán **LXM**. `SplittableRandom` được phân nhóm “legacy” theo lịch sử thuật toán, nên với thiết kế mới cần cân nhắc nguồn RNG hiện đại thay vì xem class cũ là mặc định tối ưu.
- Các ví dụ Java 17+ ở đây dùng API hiện hành; nếu phải chạy Java 8, dùng constructor/split/nextX/streams tương ứng và **không gọi `java.util.random`**.

### Tài liệu chính thức

- [Oracle Java SE 26 — `SplittableRandom`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/SplittableRandom.html): hợp đồng `split()`, thread safety, phạm vi `nextInt/Long/Double`, streams, seed, giới hạn non-cryptographic.
- [Oracle Java SE 8 — `SplittableRandom`](https://docs.oracle.com/javase/8/docs/api/java/util/SplittableRandom.html): kiểm tra API gốc từ Java 8 và các overload có sẵn tại thời điểm đó.
- [Oracle Java SE 26 — `java.util.random`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/random/package-summary.html): khuyến nghị chọn thuật toán, phân nhóm legacy/LXM/Xoroshiro, `RandomGenerator` và các nguồn SplittableGenerator hiện đại.
- [Oracle Java SE 26 — `RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): tạo PRNG theo algorithm name.
- [Oracle Java SE 26 — `RandomGenerator.SplittableGenerator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html): interface splitting và generator streams.
- [Oracle Java SE 26 — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): nguồn theo thread.
- [Oracle Java SE 26 — `SecureRandom`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html): nguồn sinh số thích hợp cho mục đích bảo mật.
