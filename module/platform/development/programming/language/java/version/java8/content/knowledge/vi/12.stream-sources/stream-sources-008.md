# Random.ints, longs, doubles — tạo nguồn Stream số giả ngẫu nhiên trong Java 8

## 1. Tổng quan

Trong Java 8, `java.util.Random` cung cấp ba nhóm phương thức **`ints(...)`**, **`longs(...)`** và **`doubles(...)`** để sinh **primitive streams** gồm các giá trị **giả ngẫu nhiên** (*pseudorandom*). Đây là các **nguồn Stream** (*stream sources*), không phải các phương thức trả về danh sách số đã được lưu sẵn.

```java
Random random = new Random();

IntStream a = random.ints(5L, 0, 10);
LongStream b = random.longs(3L, 100L, 200L);
DoubleStream c = random.doubles(4L, 0.0, 1.0);
```

Đây là đoạn minh họa trong một method, với import `java.util.Random` và các kiểu trong `java.util.stream`. Chưa có terminal operation, nên các biến `a`, `b`, `c` là **các pipeline**, không phải `List` hay `array` đã materialize.

**Sau bài học, bạn sẽ:**

1. Phân biệt `IntStream`, `LongStream`, `DoubleStream` và các dạng overload của Random.
2. Dùng đúng `streamSize`, `randomNumberOrigin`, `randomNumberBound`; biết **cận dưới bao gồm, cận trên loại trừ**.
3. Hiểu nguồn hữu hạn so với nguồn **effectively unlimited**, `limit`, `toArray`, `boxed`, `collect`, `sum`, `average`.
4. Hiểu **lazy evaluation**, **single-use**, trạng thái PRNG và tái lập kết quả bằng seed.
5. Biết nguyên nhân và cách xử lý các lỗi `IllegalArgumentException`, stream vô hạn, overflow, lặp giá trị, sai số `double`, chia sẻ RNG trong parallel.
6. Phân biệt `Random` với `ThreadLocalRandom`, `SplittableRandom`, `SecureRandom` và API mới `RandomGenerator`.
7. Chọn API đúng cho simulation, test, batch processing, sampling và nhu cầu bảo mật.

**Special Note của module:** chỉ sử dụng kiến thức còn áp dụng trong Java hiện đại. Các phương thức Java 8 trong bài vẫn được duy trì; những lựa chọn ra đời sau được nêu rõ version chứ không coi các API cũ này là lỗi thời.

## 2. Vì sao Random là một nguồn Stream?

`Random` là **pseudo-random number generator (PRNG)** có trạng thái; việc sinh các giá trị kế tiếp thay đổi trạng thái của generator. Stream được tạo từ Random mô tả cách các giá trị được cấp cho pipeline khi cần, chứ không sở hữu một collection có thể truy cập bằng index.

```text
Random(seed)
    │
    ├── ints(...)       → IntStream
    ├── longs(...)      → LongStream
    └── doubles(...)    → DoubleStream
                               │
                        map/filter/limit
                      (intermediate, lazy)
                               │
                      toArray/sum/collect
                       (terminal operation)
                               │
                         Giá trị kết quả
```

Ví dụ tạo dãy số và lưu thành mảng:

```java
int[] sample = new Random(123L).ints(6L, 0, 10).toArray();
```

`sample` là **mảng int[]** lưu sáu phần tử, có thể dùng lại nhiều lần. Stream được `toArray()` tiêu thụ là **single-use**; không thể gọi terminal operation lần thứ hai trên chính instance đó.

**Không nhầm:** `ints(6L)` là stream hữu hạn sáu số; `ints(6, 10)` là stream không giới hạn, mỗi giá trị thuộc [6,10). Chữ ký overload, không phải tên method chung, quyết định ý nghĩa các tham số.

## 3. Bảng 12 overload của Random

Ba nhóm có **bốn overload mỗi nhóm**:

| Phương thức | Kiểu trả về | Số lượng phần tử | Khoảng giá trị |
| --- | --- | --- | --- |
| `ints()` | `IntStream` | Hiệu dụng không giới hạn | Toàn miền `int` |
| `ints(long streamSize)` | `IntStream` | `streamSize` | Toàn miền `int` |
| `ints(int origin, int bound)` | `IntStream` | Hiệu dụng không giới hạn | `origin <= x < bound` |
| `ints(long streamSize, int origin, int bound)` | `IntStream` | `streamSize` | `origin <= x < bound` |
| `longs()` | `LongStream` | Hiệu dụng không giới hạn | Toàn miền `long` |
| `longs(long streamSize)` | `LongStream` | `streamSize` | Toàn miền `long` |
| `longs(long origin, long bound)` | `LongStream` | Hiệu dụng không giới hạn | `origin <= x < bound` |
| `longs(long streamSize, long origin, long bound)` | `LongStream` | `streamSize` | `origin <= x < bound` |
| `doubles()` | `DoubleStream` | Hiệu dụng không giới hạn | `0.0 <= x < 1.0` |
| `doubles(long streamSize)` | `DoubleStream` | `streamSize` | `0.0 <= x < 1.0` |
| `doubles(double origin, double bound)` | `DoubleStream` | Hiệu dụng không giới hạn | `origin <= x < bound` |
| `doubles(long streamSize, double origin, double bound)` | `DoubleStream` | `streamSize` | `origin <= x < bound` |

**Hữu hạn:** với `streamSize` hợp lệ, stream được thiết kế để tạo đúng số phần tử đó **nếu toàn bộ stream được duyệt**. Một pipeline thêm `filter` có thể đưa ra ít phần tử hơn; một terminal short-circuit có thể dừng trước khi hết nguồn.

**Hiệu dụng không giới hạn:** các overload không có `streamSize` không có điểm kết thúc tự nhiên. Không `collect(toList())` hay `toArray()` trên chúng mà thiếu điều kiện dừng phù hợp.

### Cách đọc nhanh các chữ ký dễ nhầm

```java
rng.ints(10);                 // Mười số int, toàn miền int.
rng.ints(10, 20);             // Không giới hạn số lượng; mỗi số từ 10 đến 19.
rng.ints(5L, 10, 20);         // Năm số; mỗi số từ 10 đến 19.

rng.longs(10L);               // Mười số long, toàn miền long.
rng.longs(10L, 20L);          // Không giới hạn; long từ 10 đến 19.
rng.longs(5L, 10L, 20L);      // Năm số long từ 10 đến 19.

rng.doubles();                // Không giới hạn; double trong [0,1).
rng.doubles(4L);              // Bốn số double trong [0,1).
rng.doubles(0.2, 0.8);        // Không giới hạn; double trong [0.2,0.8).
rng.doubles(4L, 0.2, 0.8);    // Bốn số double trong [0.2,0.8).
```

Đây là các snippet trong method với biến `rng` kiểu `Random`. **Không có overload `doubles(double bound)` một cận**: nếu muốn [0,bound), gọi `doubles(0.0, bound)` hoặc overload có size và hai cận.

## 4. `Random.ints(...)` và các khoảng int

### 4.1. Không giới hạn so với hữu hạn

```java
int[] fromInfinite = new Random().ints().limit(5).toArray();
int[] fromFinite = new Random().ints(5L).toArray();
```

Cả hai tạo mảng gồm năm số int, nhưng **nguồn và cấu trúc pipeline khác nhau**. `ints()` hiệu dụng không giới hạn, nên phải `limit(5)` nếu muốn mảng có năm phần tử. `ints(5L)` đã hữu hạn.

Hai cách không nhất thiết cho **chuỗi số bằng nhau** khi thay thế trong một pipeline tùy ý: trạng thái RNG, consumption pattern, splitting hoặc các terminal operation khác có thể ảnh hưởng cách giá trị được sinh.

### 4.2. Cận dưới inclusive, cận trên exclusive

```java
int[] dice = new Random().ints(6L, 1, 7).toArray();
int[] grades = new Random().ints(10L, 0, 101).toArray();
int[] signed = new Random().ints(4L, -3, 4).toArray();
```

- `dice`: sáu giá trị trong [1,7), tức **1 tới 6**.
- `grades`: mười giá trị trong [0,101), tức **0 tới 100**.
- `signed`: bốn giá trị trong [-3,4), tức **-3 tới 3**.

Một khoảng có đúng một số nguyên hợp lệ vẫn được phép:

```java
int[] zeros = new Random().ints(3L, 0, 1).toArray();
// zeros là [0, 0, 0].
```

**Không hứa dữ liệu không trùng:** `Random.ints(6L,1,7)` có thể ra cùng một mặt xúc xắc nhiều lần. Đúng mục tiêu sinh mẫu giả ngẫu nhiên không có nghĩa giá trị duy nhất.

## 5. `Random.longs(...)` và miền số 64 bit

Với số nguyên kiểu `long`:

```java
Random rng = new Random();

long[] allRange = rng.longs(3L).toArray();
long[] bounded = rng.longs(4L, 100_000L, 200_000L).toArray();
long[] firstFour = rng.longs(100L, 200L).limit(4L).toArray();
```

- `longs(3L)`: ba giá trị toàn miền `long`.
- `longs(4L,100_000L,200_000L)`: bốn giá trị trong [100000,200000).
- `longs(100L,200L)`: **overload origin/bound**, vẫn hiệu dụng không giới hạn; `limit(4L)` giới hạn đầu ra.

**Không tự tính số trong khoảng bằng modulo một cách thiếu kiểm tra:**

```java
long r = Math.abs(rng.nextLong()) % (bound - origin); // Cách làm nên tránh.
```

Đây là snippet **cố ý không khuyến nghị**. `bound - origin` có thể overflow, `Math.abs(Long.MIN_VALUE)` vẫn âm, và phép modulo không kiểm soát thích hợp có thể tạo sai lệch phân phối. Dùng overload bounded `longs(..., origin, bound)` của thư viện khi cần miền giá trị đó.

**Không dùng `longs()` như ID service** nếu cần tính duy nhất được bảo đảm. Random có thể sinh trùng và không bảo đảm tính khó đoán.

## 6. `Random.doubles(...)` và phạm vi số thực

Hai overload không có cận trả `double` thuộc **[0.0,1.0)**:

```java
double[] rates = new Random().doubles(5L).toArray();
```

Overload có cận:

```java
double[] prices = new Random().doubles(6L, 10.5, 25.0).toArray();
double[] deviations = new Random().doubles(-1.0, 1.0)
        .limit(4L).toArray();
```

- `prices`: sáu giá trị trong [10.5,25.0).
- `deviations`: bốn giá trị trong [-1.0,1.0), vì dùng nguồn không giới hạn với `limit(4L)`.

**`double` có độ chính xác hữu hạn**: API sinh các giá trị floating-point giả ngẫu nhiên theo miền được quy định; không tạo mẫu liên tục trên mọi số thực toán học. Giá trị có thể trùng. `double` cũng không phù hợp để biểu diễn tiền tệ cần độ chính xác thập phân tuyệt đối.

### Cận cho double phải có thứ tự hợp lệ

`origin < bound` là điều kiện quan trọng khi dùng bounded overload; `NaN` không đáp ứng điều kiện này. Khi mô phỏng thông thường, nên dùng **các cận hữu hạn** có ý nghĩa và tránh cực trị vô hạn hoặc khoảng khiến phép tính số dấu phẩy động không phù hợp với mô hình.

**Không nhầm với `nextGaussian()`:** `Random.doubles()` sinh theo mô hình phân phối uniform trong [0,1), không phải phân phối chuẩn. Nếu bài toán cần Gaussian hoặc phân phối khác, chọn thuật toán/API tương ứng, đừng đổi tên biến thành `normal` rồi coi `doubles()` tự biến đổi phân phối.

## 7. Kiểm tra tham số và tình huống biên

| Lời gọi | Kết quả |
| --- | --- |
| `rng.ints(-1L)` | `IllegalArgumentException`: size âm |
| `rng.longs(-1L)` | `IllegalArgumentException`: size âm |
| `rng.doubles(-1L)` | `IllegalArgumentException`: size âm |
| `rng.ints(5L, 10, 10)` | `IllegalArgumentException`: origin == bound |
| `rng.longs(5L, 20L, 10L)` | `IllegalArgumentException`: origin > bound |
| `rng.doubles(5L, 1.0, 1.0)` | `IllegalArgumentException`: origin == bound |
| `rng.ints(0L)` | Stream rỗng |
| `rng.longs(0L, 5L, 10L)` | Stream rỗng, vì size = 0 và khoảng hợp lệ |
| `rng.doubles(0L)` | Stream rỗng |

**Quy tắc chung:** `streamSize >= 0` và (với bounded overload) **`origin < bound`**. Cần validate input trước khi xây pipeline; không chờ `collect` phát hiện lỗi.

`streamSize` là `long`, nhưng bộ nhớ và kích thước mảng trên JVM vẫn hữu hạn. Tránh làm `rng.ints(Long.MAX_VALUE).toArray()` hoặc dùng `collect` trên nguồn rất lớn mà không có chiến lược giới hạn dữ liệu.

Đặc biệt, muốn khoảng số nguyên **cận trên inclusive** bằng `max`, công thức `bound=max+1` chỉ đúng **khi không overflow**. Với `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE`, không thể cộng một vào cận bằng cùng kiểu rồi vẫn giữ ý nghĩa ban đầu; cần cách chọn miền giá trị khác theo yêu cầu.

## 8. Lazy generation, PRNG state và seed

`Random` có state và seed. Dùng một seed cụ thể có ích cho mô phỏng và unit test vì **hai generator mới có cùng seed, được tiêu thụ bằng cùng chuỗi thao tác tuần tự**, có thể cho cùng kết quả:

```java
int[] left = new Random(42L).ints(5L, 0, 100).toArray();
int[] right = new Random(42L).ints(5L, 0, 100).toArray();
boolean same = Arrays.equals(left, right); // true
```

Đây là snippet trong method. Không kết luận rằng hai stream khác nhau tạo từ **cùng một instance Random** sẽ có cùng values:

```java
Random rng = new Random(42L);
int[] first = rng.ints(5L, 0, 100).toArray();
int[] next = rng.ints(5L, 0, 100).toArray();
// "first" và "next" là hai lần tiêu thụ state kế tiếp.
```

**Stream lazy và single-use:** `filter`, `map`, `limit` thiết lập pipeline, còn terminal operation kích hoạt traversal theo nhu cầu. Một instance stream đã được tiêu thụ **không dùng lại** cho terminal thứ hai. Muốn sinh số mới, tạo stream mới từ RNG; muốn tái hiện số cũ, lưu mảng/list hoặc khởi tạo generator mới với seed/cách tiêu thụ đúng.

### Không dựa vào side effect của `peek`

```java
long count = new Random(7L).ints(10L)
        .peek(System.out::println)
        .count();
```

Đây là **mã minh họa nên tránh nếu mục tiêu là in đủ mười số**. `count()` có thể được Stream implementation tối ưu khi kích thước đã biết, bỏ qua các callback `peek` không ảnh hưởng kết quả. Không được suy ra số lần `peek` chạy luôn bằng count, hay rằng RNG luôn đã tiến trạng thái theo đúng số phần tử được đếm.

**Khi cần tái lập trạng thái PRNG chính xác**, hãy kiểm soát seed, trình tự tiêu thụ, cách phân chia công việc, và tránh dựa vào các side effects không có bảo đảm. Seed là công cụ phục vụ test/simulation, **không phải secret an toàn**.

## 9. Dùng primitive streams với terminal operations

Vì `ints`, `longs`, `doubles` trả các **primitive specializations**, bạn có thể xử lý số mà không phải boxing mọi phần tử:

```java
int sum = new Random(3L).ints(100L, 1, 7).sum();

OptionalDouble average = new Random(4L)
        .doubles(100L, 0.0, 100.0)
        .average();

IntSummaryStatistics stats = new Random(5L)
        .ints(100L, 0, 10)
        .summaryStatistics();
```

Đây là snippets trong method với import `Random`, `OptionalDouble`, `IntSummaryStatistics`. `average()` trả `OptionalDouble` vì stream rỗng không có trung bình.

**Lưu ý overflow:** `IntStream.sum()` có kiểu trả về `int`. Với số lượng lớn, tổng có thể vượt miền int. Khi cần `long`, dùng `mapToLong(...).sum()`, chẳng hạn:

```java
long sum = new Random(3L).ints(100_000L, 1, 1_000_000)
        .mapToLong(n -> n)
        .sum();
```

Với `DoubleStream.sum()`, tổng là floating-point, có thể có sai số do làm tròn. Không dùng `DoubleStream` khi bài toán kế toán cần số thập phân chính xác.

### Muốn `List<Integer>` thì cần `boxed()`

```java
List<Integer> scores = new Random(6L).ints(5L, 0, 101)
        .boxed()
        .collect(Collectors.toList());
```

`IntStream` không phải `Stream<Integer>`; `boxed()` chuyển primitive values thành wrappers. Với kiểu long/double, `LongStream.boxed()` và `DoubleStream.boxed()` có ý nghĩa tương tự.

Nếu chỉ cần `int[]`, dùng `toArray()` thường đơn giản hơn. Trong Java 17+, `Stream.toList()` đã có (từ Java 16), nhưng **đoạn code muốn biên dịch với Java 8** vẫn nên dùng `Collectors.toList()`. Đừng giả định `Collectors.toList()` luôn trả một implementation/mutability cụ thể.

## 10. Sampling và phân phối: số ngẫu nhiên không có nghĩa unique

Các bounded random methods sinh số theo **mô hình giả ngẫu nhiên gần đều** trong khoảng được hỗ trợ. Với một mẫu nhỏ, không có bảo đảm các giá trị phân bổ chính xác theo tỉ lệ mong muốn; không có bảo đảm không trùng.

Ví dụ mô phỏng xúc xắc:

```java
int[] frequencies = new int[6];
new Random().ints(600L, 1, 7)
        .forEach(face -> frequencies[face - 1]++);
```

Đây là snippet cho **stream tuần tự**. Tổng `frequencies[0] + ... + frequencies[5]` bằng 600, nhưng sáu tần suất thường khác nhau. Nếu bạn chuyển pipeline sang **parallel**, cập nhật `int[] frequencies` dùng chung trong `forEach` sẽ gây race; nên dùng collector/reduction thích hợp.

Ba khái niệm phải tách riêng:

- **Randomness:** phân phối giả ngẫu nhiên.
- **Uniqueness:** không trùng giá trị — **không** được `Random.ints/longs/doubles` bảo đảm.
- **Cryptographic unpredictability:** kẻ tấn công khó đoán kết quả — `java.util.Random` **không** cung cấp bảo đảm thích hợp.

Nếu cần lấy một tập giá trị **không hoàn lại** từ một miền hữu hạn, chọn thuật toán sampling/shuffling phù hợp. `distinct().limit(k)` trên nguồn vô hạn có thể rất chậm khi k gần số giá trị phân biệt có thể có, và có thể **không kết thúc** nếu k lớn hơn cardinality miền.

Tránh tự dùng `Math.abs(rng.nextInt()) % n` hoặc công thức modulo chưa kiểm chứng để tạo khoảng: có thể có bias và lỗi với `Integer.MIN_VALUE`. Dùng bounded overload của thư viện.

## 11. Ví dụ Java hoàn chỉnh — `RandomStreamsDemo.java`

Chương trình sau cho thấy **ba kiểu stream**, kiểm tra cận, seed, stream rỗng, reduction, tham số sai và single-use.

```java
import java.util.Arrays;
import java.util.Random;
import java.util.stream.IntStream;

public class RandomStreamsDemo {
    public static void main(String[] args) {
        Random rng = new Random(2026L);

        int[] digits = rng.ints(7, 0, 10).toArray();
        long[] codes = rng.longs(4, 100L, 1000L).toArray();
        double[] rates = rng.doubles(5, 0.0, 1.0).toArray();

        System.out.println("digits=" + Arrays.toString(digits));
        System.out.println("digitsInRange=" + Arrays.stream(digits)
                .allMatch(n -> n >= 0 && n < 10));
        System.out.println("codes=" + Arrays.toString(codes));
        System.out.println("codesInRange=" + Arrays.stream(codes)
                .allMatch(n -> n >= 100L && n < 1000L));
        System.out.println("rateCount=" + rates.length);
        System.out.println("ratesInRange=" + Arrays.stream(rates)
                .allMatch(n -> n >= 0.0 && n < 1.0));

        int[] a = new Random(42L).ints(5, 0, 100).toArray();
        int[] b = new Random(42L).ints(5, 0, 100).toArray();
        System.out.println("sameSeed=" + Arrays.equals(a, b));

        int[] zeros = new Random(11L).ints(3, 0, 1).toArray();
        System.out.println("zeros=" + Arrays.toString(zeros));

        long empty = new Random(8L).longs(0L).count();
        System.out.println("emptyCount=" + empty);

        int sum = new Random(5L).ints(10, 1, 7)
                .filter(n -> n % 2 == 0)
                .sum();
        System.out.println("evenSum=" + sum);

        try {
            new Random().ints(3L, 10, 10);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidBounds=rejected");
        }

        try {
            new Random().doubles(-1L);
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeSize=rejected");
        }

        IntStream oneShot = new Random(1L).ints(2L);
        System.out.println("consumedCount=" + oneShot.count());
        try {
            oneShot.sum();
        } catch (IllegalStateException expected) {
            System.out.println("reused=rejected");
        }
    }
}
```

**Biên dịch/chạy với JDK 17+** (code chỉ dùng các API từ Java 8):

```bash
javac RandomStreamsDemo.java
java RandomStreamsDemo
```

**Stdout chính xác của chương trình đã chạy trên OpenJDK 24:**

```text
digits=[9, 0, 7, 0, 9, 8, 3]
digitsInRange=true
codes=[690, 375, 135, 814]
codesInRange=true
rateCount=5
ratesInRange=true
sameSeed=true
zeros=[0, 0, 0]
emptyCount=0
evenSum=22
invalidBounds=rejected
negativeSize=rejected
consumedCount=2
reused=rejected
```

### Phân tích kết quả

1. **`digits=[9,...]` và `digitsInRange=true`**: bảy số int nằm trong [0,10); kết quả có thể trùng, và bound 10 không được chọn.
2. **`codes=[690,...]` và `codesInRange=true`**: bốn số long thuộc [100,1000).
3. **`rateCount=5` và `ratesInRange=true`**: năm số double trong [0,1); chương trình kiểm phạm vi thay vì in nhiều chữ số thập phân ngẫu nhiên.
4. **`sameSeed=true`**: hai `Random(42L)` độc lập được tiêu thụ cùng cách cho mảng giống nhau.
5. **`zeros=[0,0,0]`**: khoảng số nguyên [0,1) chỉ chứa số 0, nên mọi phần tử đều bằng 0.
6. **`emptyCount=0`**: size 0 tạo stream rỗng hợp lệ.
7. **`evenSum=22`**: `filter` chọn số chẵn trong mười giá trị giả ngẫu nhiên, terminal `sum` tính tổng.
8. **`invalidBounds=rejected`, `negativeSize=rejected`**: tham số không hợp lệ gây `IllegalArgumentException`.
9. **`consumedCount=2`, `reused=rejected`**: stream hữu hạn được tiêu thụ một lần; gọi `sum` lần nữa trên cùng `IntStream` bị từ chối.

Những giá trị random ở stdout chỉ là kết quả minh họa của seed và trình tự code này; **không dùng seed cố định như dữ liệu bí mật**.

## 12. Java hiện đại: Random, SplittableRandom, ThreadLocalRandom, RandomGenerator

### `java.util.Random` vẫn sử dụng được

`Random` không bị loại bỏ. Nó phù hợp với bài tập, mô phỏng đơn giản, unit test cần seed và các tác vụ tuần tự. Với một đối tượng `Random` **dùng chung giữa nhiều thread**, cập nhật state có thể gây contention; thứ tự task tiêu thụ số có thể thay đổi giữa các lần chạy, dù seed ban đầu giống nhau.

### `ThreadLocalRandom` cho các thread độc lập

`java.util.concurrent.ThreadLocalRandom.current()` hữu ích khi nhiều thread cần sinh số nhưng không muốn tranh chấp một `Random` dùng chung. Nó thường được dùng qua `ThreadLocalRandom.current().nextInt(...)` và những API bounded tương ứng. Không dùng nó để cố tái lập test bằng cách tùy tiện đặt seed thủ công; mục đích của nó khác `new Random(seed)`.

### `SplittableRandom` (từ Java 8)

`java.util.SplittableRandom` cũng có `ints`, `longs`, `doubles`, và `split()` giúp tạo generator độc lập cho các nhánh tính toán:

```java
SplittableRandom parent = new SplittableRandom(2026L);
SplittableRandom child = parent.split();

int[] parentValues = parent.ints(3L, 0, 10).toArray();
int[] childValues = child.ints(3L, 0, 10).toArray();
```

Đây là snippet trong method với import `java.util.SplittableRandom`. **Không chia sẻ cùng một instance SplittableRandom cho nhiều thread** vì class này không thread-safe; tạo các generator con theo contract để chia việc.

### `RandomGenerator` (Java 17+)

Từ Java 17, `java.util.random.RandomGenerator` và các API liên quan giúp chọn các thuật toán generator khác nhau. Đây là lựa chọn hiện đại, nhưng **không biến Random.ints/longs/doubles thành API lỗi thời**.

```java
// Chỉ dùng khi project target Java 17+.
java.util.random.RandomGenerator generator =
        java.util.random.RandomGenerator.getDefault();

int[] sample = generator.ints(5L, 0, 10).toArray();
```

Không dùng snippet này nếu compiler target Java 8, vì package `java.util.random` chưa có trong Java 8.

### `SecureRandom` cho bảo mật

`Random`, `ThreadLocalRandom` và `SplittableRandom` **không phải generator có tính bảo mật mật mã**. Nếu tạo OTP, reset tokens, session secrets, nonce hoặc mã khó đoán, dùng **`java.security.SecureRandom`** cùng quy trình security phù hợp. Không thay thế bằng seed cố định hoặc seed thời gian.

**Parallel streams không tự bảo đảm tái lập:** xử lý song song có thể thay đổi cách các random values được tiêu thụ. Nếu yêu cầu tái lập cho mô phỏng song song, thiết kế seed/subgenerator **theo từng công việc** và kiểm soát scheduling semantics thay vì chỉ chia sẻ một Random rồi gọi `.parallel()`.

## 13. Lỗi thường gặp

| Lỗi | Cách đúng |
| --- | --- |
| `ints(10,20)` bị hiểu là "10 số dưới 20" | Đây là **origin/bound**, nguồn không giới hạn |
| `ints(3L,1,6)` được hiểu là sinh 1..6 | Bound 6 **không được bao gồm**; giá trị là 1..5 |
| `doubles(1.0)` được tưởng có overload chỉ bound | Không có `doubles(double bound)`; dùng `doubles(0.0,1.0)` |
| `ints().toArray()` trên nguồn không giới hạn | Dùng size overload hoặc `limit(n)` |
| Size âm | Validate `streamSize >= 0` |
| `origin >= bound` | Validate `origin < bound` |
| Nghĩ `Random.longs` sinh ID duy nhất | Có thể trùng; tính duy nhất là bài toán khác |
| Nghĩ cùng seed luôn cho kết quả giống bất kể pipeline | Phải kiểm soát thứ tự gọi, stream consumption và parallel |
| Dùng `Math.abs(nextLong()) % width` | Dễ overflow/bias; dùng bounded API |
| Gọi terminal hai lần trên cùng stream | Stream single-use; tạo stream mới |
| Nghĩ `peek` luôn được gọi khi `count` | Các stage không cần thiết có thể bị tối ưu bỏ |
| Dùng shared `ArrayList` trong parallel `forEach` | Data race; chọn collector/reduction phù hợp |
| Dùng `Random` sinh token bảo mật | Dùng `SecureRandom` |
| Dùng `Stream.toList()` rồi đòi Java 8 compile | `Stream.toList()` có từ Java 16; dùng `Collectors.toList()` |
| Tưởng `boxed()` không cần khi dùng collector trên `IntStream` | `boxed()` chuyển primitive thành wrapper Stream |
| Dùng `IntStream.sum()` cho tổng lớn mà không kiểm tra overflow | Chuyển `mapToLong` hoặc chọn numeric type phù hợp |

## 14. Bài tập và đáp án

**1.** `new Random().ints(5L)` cho bao nhiêu phần tử nếu duyệt hết?  
**Đáp án:** Năm giá trị int trong toàn miền int.

**2.** `new Random().ints(5,10)` là nguồn hữu hạn hay không?  
**Không giới hạn:** đó là bounded overload với origin=5, bound=10.

**3.** Viết cách sinh ba số int thuộc [-2,2].  
`new Random().ints(3L,-2,3)`.

**4.** Sinh bốn số long thuộc [100,200).  
`new Random().longs(4L,100L,200L)`.

**5.** `doubles(3L)` có sinh 1.0 không?  
**Không.** Mỗi giá trị thuộc [0.0,1.0).

**6.** Kích thước bằng 0 có hợp lệ không?  
**Có**, stream rỗng nếu các tham số còn lại hợp lệ.

**7.** Origin bằng bound có hợp lệ không?  
**Không**, bounded overload yêu cầu origin < bound.

**8.** Tại sao `Random.ints().collect(...)` có thể không kết thúc?  
Nguồn hiệu dụng không giới hạn và terminal cần duyệt hết mà không có điểm dừng.

**9.** Làm sao biến `IntStream` thành `List<Integer>`?  
`boxed().collect(Collectors.toList())`.

**10.** Dùng cùng seed có luôn tái hiện thứ tự số trong `parallel()` không?  
**Không bảo đảm**, vì consumption order/splitting và scheduling có thể khác.

**11.** `Random.longs()` có bảo đảm mọi số không trùng?  
**Không.**

**12.** `Random` có phù hợp tạo OTP hoặc reset token?  
**Không.** Dùng `SecureRandom` và policy bảo mật thích hợp.

**13.** Khi nào nên cân nhắc `SplittableRandom`?  
Khi muốn **tách generator** thành các nhánh tính toán; instance của nó không được share tùy ý qua nhiều thread.

**14.** Các phương thức Random.ints/longs/doubles có lỗi thời chỉ vì Java 17 có RandomGenerator?  
**Không.** Các API này vẫn được duy trì.

**15.** `new Random().ints(10L).peek(log).count()` có bảo đảm log mười lần không?  
**Không.** Stream có thể tối ưu không gọi các callbacks không ảnh hưởng kết quả count.

## 15. Checklist trước khi áp dụng

- [ ] Chọn đúng `IntStream`, `LongStream`, `DoubleStream`.
- [ ] Phân biệt rõ overload **size** với overload **origin/bound**.
- [ ] Chọn **cận dưới inclusive, cận trên exclusive**; kiểm tra overflow nếu cộng 1.
- [ ] Kiểm tra `streamSize >= 0`, `origin < bound` và tính hữu hạn/phù hợp của khoảng double.
- [ ] Không materialize nguồn vô hạn mà thiếu giới hạn.
- [ ] Dùng terminal operation đúng mục đích: `toArray`, `sum`, `average`, `boxed`/collector.
- [ ] Nếu cần reproducibility, xác định seed, trình tự tiêu thụ, cách dùng RNG trong parallel.
- [ ] Không dùng shared mutable state không an toàn trong parallel pipeline.
- [ ] Không coi random values là unique IDs hoặc cryptographic secrets.
- [ ] Nếu target Java 8, không dùng APIs chỉ có từ Java 16/17.
- [ ] Với ứng dụng thực, benchmark generator và Stream pipeline theo workload thay vì giả định parallel luôn nhanh hơn.

## 16. Tổng kết và nguồn chính thức

**`Random.ints()`, `Random.longs()`, `Random.doubles()` là các nguồn primitive streams sinh số giả ngẫu nhiên**. Mỗi nhóm có overload cho nguồn không giới hạn, số lượng hữu hạn, cận giá trị và cả size+cận. Giá trị bounded **bao gồm origin nhưng loại trừ bound**; size phải không âm; stream tiêu thụ một lần và các intermediate operations có tính lazy.

Chọn `Random` khi cần nguồn PRNG thông thường hoặc kết quả tái lập bằng seed, `SplittableRandom`/generator khác khi tổ chức parallel computations, `ThreadLocalRandom` cho nhiều thread, và **`SecureRandom`** khi có yêu cầu mật mã. Những phương thức Java 8 này vẫn áp dụng trong Java hiện đại.

**Tài liệu chính thức:**

- [Oracle Java SE — Random](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Random.html): các overload, cận, kích thước và exception.
- [Oracle Java SE — java.util.stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): nguồn, laziness, single-use và terminal operations.
- [Oracle Java SE — IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html): `boxed`, `sum`, `summaryStatistics`.
- [Oracle Java SE — SplittableRandom](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/SplittableRandom.html): splitting và parallel computations.
- [Oracle Java SE — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): random cho các threads.
- [Oracle Java SE — java.util.random package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/random/package-summary.html): RandomGenerator từ Java 17.
- [Oracle Java SE — SecureRandom](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html): generator phù hợp tình huống cryptographic.
