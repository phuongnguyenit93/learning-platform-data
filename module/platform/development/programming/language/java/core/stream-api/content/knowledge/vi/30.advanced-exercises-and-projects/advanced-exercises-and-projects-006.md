# Đo và giải thích hiệu năng của ba cách xử lý cùng bài toán

Một giải pháp dùng **Java Stream API** có thể ngắn gọn, dễ đọc và đúng về mặt ngữ nghĩa, nhưng điều đó **không tự động chứng minh nó nhanh hơn** vòng lặp truyền thống. Tương tự, thêm `parallel()` không bảo đảm tăng tốc: việc chia nguồn bằng `Spliterator`, lập lịch tác vụ, gộp kết quả, áp lực bộ nhớ và độ lớn công việc đều ảnh hưởng tới thời gian chạy.

Bài thực hành nâng cao này hướng dẫn thiết kế **một thí nghiệm có thể tái lập**, so sánh **ba cách giải cùng một bài toán**: vòng lặp `for`, stream tuần tự và stream song song. Mục tiêu không phải tuyên bố cách nào luôn thắng, mà là **đo đúng, kiểm tra cùng kết quả và giải thích vì sao tốc độ thay đổi** giữa các kích thước dữ liệu và mức độ tính toán.

Đây là một bài thuộc chương **Bài tập nâng cao và dự án** của mô-đun `JAVA_STREAM_API`, kết nối kiến thức về pipeline lazy, `filter`, `mapToLong`, `sum`/`reduce`, primitive stream, Spliterator và giới hạn hiệu năng của parallel stream.

## 1. Đầu bài dự án và tiêu chí hoàn thành

Cho một mảng `int[] data`. Chỉ xét các phần tử **chẵn**. Với mỗi phần tử được chọn, áp dụng một hàm biến đổi số nguyên xác định `score(value, rounds)`, sau đó **cộng tất cả điểm** thành một `long`.

Viết và so sánh ba cách:

1. **Imperative loop:** một vòng `for` duyệt mảng, kiểm tra chẵn/lẻ, tính điểm và cộng kết quả.
2. **Sequential stream:** `Arrays.stream(data).filter(...).mapToLong(...).sum()`.
3. **Parallel stream:** cùng pipeline nhưng bật `parallel()` để cho phép chia mảng thành các phần xử lý.

Ba phiên bản phải dùng **cùng dữ liệu, cùng hàm `score`, cùng điều kiện lọc và cùng kiểu tổng hợp**. Không được làm cho một phiên bản ít việc hơn rồi kết luận nó nhanh hơn.

### Sản phẩm cần nộp

| Sản phẩm | Mục tiêu |
| --- | --- |
| Ba phương thức Java | Cùng bài toán, dễ đọc và không dùng trạng thái chia sẻ mutable. |
| Kiểm tra tính đúng | Cả ba trả cùng tổng trên nhiều kích thước và trường hợp biên. |
| Benchmark JMH | Có warm-up, measurement, fork và cách tiêu thụ kết quả. |
| Bảng số liệu | Ghi rõ `n`, mức tính toán, đơn vị thời gian và môi trường chạy. |
| Phần phân tích | Giải thích overhead, chia nguồn, JIT, CPU, GC và khả năng mở rộng. |
| Kết luận có điều kiện | Nêu cách phù hợp cho workload đã đo, không khái quát quá mức. |

## 2. Xác định phép tính để ba lời giải thực sự tương đương

Hãy chọn một hàm tính toán **thuần** (*pure*): nó chỉ phụ thuộc vào `value` và `rounds`, không đọc đồng hồ, I/O hay thay đổi biến toàn cục. Trong ví dụ, mỗi vòng lặp trộn các bit của một giá trị `long`, cuối cùng giữ lại 16 bit thấp để điểm nằm trong khoảng `[0, 65_535]`.

```java
static long score(int value, int rounds) {
    long x = Integer.toUnsignedLong(value)
        + 0x9E3779B97F4A7C15L;

    for (int i = 0; i < rounds; i++) {
        x ^= x >>> 30;
        x *= 0xBF58476D1CE4E5B9L;
        x ^= x >>> 27;
        x *= 0x94D049BB133111EBL;
        x ^= x >>> 31;
    }
    return x & 0xFFFFL;
}
```

Các phép nhân `long` có thể tràn theo quy tắc số nguyên 64 bit của Java; ở đây đó là **chủ đích của thuật toán trộn bit**, không phải yêu cầu độ chính xác số học của một tổng tiền. Kết quả `score` luôn không âm và không quá 65.535. Với mảng tối đa một triệu phần tử, tổng lớn nhất có thể là `65_535_000_000L`, nằm an toàn trong phạm vi `long`.

Tham số `rounds` biểu diễn **mức độ công việc trên một phần tử**:

- `rounds = 4`: phép biến đổi tương đối nhẹ; overhead tạo và chia pipeline có thể chiếm tỷ lệ đáng kể.
- `rounds = 64`: nhiều phép toán hơn trên mỗi phần tử; chi phí song song có cơ hội được bù lại.

Đây là hàm **mô phỏng tải CPU để đo đạc**, không phải thuật toán mật mã hay hàm băm chất lượng thống kê đã được thẩm định. Không dùng nó để tạo token bảo mật.

## 3. Triển khai ba phương án trong cùng một lớp

Ví dụ đầy đủ sau dùng Java 8+. Mọi phương thức nhận **đúng cùng mảng** và không thay đổi dữ liệu nguồn.

```java
package example;

import java.util.Arrays;

public final class ThreeWays {
    private ThreeWays() {}

    public static long score(int value, int rounds) {
        long x = Integer.toUnsignedLong(value)
            + 0x9E3779B97F4A7C15L;
        for (int i = 0; i < rounds; i++) {
            x ^= x >>> 30;
            x *= 0xBF58476D1CE4E5B9L;
            x ^= x >>> 27;
            x *= 0x94D049BB133111EBL;
            x ^= x >>> 31;
        }
        return x & 0xFFFFL;
    }

    // Phương án A: xử lý trực tiếp, tuần tự.
    public static long loop(int[] data, int rounds) {
        long total = 0L;
        for (int value : data) {
            if ((value & 1) == 0) {
                total += score(value, rounds);
            }
        }
        return total;
    }

    // Phương án B: pipeline Stream tuần tự.
    public static long sequentialStream(int[] data, int rounds) {
        return Arrays.stream(data)
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> score(value, rounds))
            .sum();
    }

    // Phương án C: cùng pipeline, cho phép xử lý song song.
    public static long parallelStream(int[] data, int rounds) {
        return Arrays.stream(data)
            .parallel()
            .filter(value -> (value & 1) == 0)
            .mapToLong(value -> score(value, rounds))
            .sum();
    }

    public static int[] makeInput(int size) {
        if (size < 0 || size > 1_000_000) {
            throw new IllegalArgumentException("size ngoài phạm vi thử");
        }
        int[] result = new int[size];
        for (int i = 0; i < size; i++) {
            result[i] = i * 37 + 11; // Dữ liệu xác định, không cần RNG.
        }
        return result;
    }

    public static void main(String[] args) {
        int[] data = makeInput(10_000);
        int rounds = 64;

        long a = loop(data, rounds);
        long b = sequentialStream(data, rounds);
        long c = parallelStream(data, rounds);

        System.out.println("loop     = " + a);
        System.out.println("sequence = " + b);
        System.out.println("parallel = " + c);

        if (a != b || a != c) {
            throw new AssertionError("Ba kết quả không khớp");
        }
    }
}
```

**Vì sao so sánh này công bằng hơn nhiều ví dụ benchmark tùy tiện?**

- **Chỉ một thuật toán `score`:** cả ba gọi cùng hàm; không thay hàm nặng bằng hàm nhẹ ở một nhánh.
- **Chỉ một điều kiện lọc:** `(value & 1) == 0` tương ứng với số chẵn cho mọi giá trị `int`.
- **Dùng primitive stream:** `Arrays.stream(int[])` tạo `IntStream` và `mapToLong` tạo `LongStream`, tránh boxing sang `Integer`/ `Long` không cần thiết.
- **Cùng kiểu tổng:** mọi cách cộng vào `long`. Với giới hạn dữ liệu trên, tổng không tràn `long`.
- **Không có side effect:** việc xử lý các phần tử độc lập; `parallel()` không chia sẻ một `ArrayList` hay bộ đếm mutable bên ngoài.
- **Đầu vào cố định:** `makeInput` không phụ thuộc thời gian hoặc seed không được ghi lại.

Không được coi riêng việc `main` in ra ba tổng bằng nhau là bằng chứng đầy đủ về đúng đắn. Cần kiểm thử cả mảng rỗng, toàn số lẻ, toàn số chẵn, số âm, một phần tử và các độ lớn lớn hơn.

## 4. Hiểu chính xác công việc của mỗi phương án

### A. Vòng lặp `for`

Vòng lặp thực thi phép lọc và phép cộng trực tiếp trên mảng. Nó thường có overhead khởi tạo thấp, không cần đối tượng pipeline Stream và không tạo các tác vụ fork/join.

**Không suy ra** vòng lặp luôn nhanh hơn stream: JVM có thể inline lambda, tối ưu primitive stream và có các tối ưu phụ thuộc JDK. Mức nhanh/chậm chỉ có thể kết luận khi đo workload cụ thể.

### B. Stream tuần tự

```java
Arrays.stream(data)
    .filter(value -> (value & 1) == 0)
    .mapToLong(value -> score(value, rounds))
    .sum();
```

`filter` và `mapToLong` là các **intermediate operation lazy**. `sum()` là terminal operation kích hoạt traversal; pipeline thường được kết hợp để từng phần tử đi qua các bước mà không cần materialize danh sách trung gian.

Khi `n` nhỏ, chi phí thiết lập pipeline và gọi các lớp trừu tượng có thể đáng kể so với vòng lặp. Khi phép `score` chiếm phần lớn thời gian, tỷ trọng overhead này thường giảm.

### C. Stream song song

```java
Arrays.stream(data)
    .parallel()
    .filter(value -> (value & 1) == 0)
    .mapToLong(value -> score(value, rounds))
    .sum();
```

`parallel()` không tạo thread riêng cho **mỗi phần tử**. Framework sử dụng Spliterator của mảng để phân chia công việc; các tác vụ xử lý phần nguồn rồi kết hợp tổng bộ phận. Phép cộng số nguyên với tổng trong giới hạn `long` phù hợp cho reduction song song.

Chi phí bổ sung có thể gồm **chia nguồn, lập lịch, đồng bộ hóa kết quả, truy cập bộ nhớ và tranh chấp CPU**. Với ít phần tử và hàm `score` nhẹ, các chi phí này dễ áp đảo lợi ích. Với dữ liệu đủ lớn và CPU còn tài nguyên, song song có thể thắng.

## 5. Trước khi đo thời gian: xác nhận tính tương đương

Một benchmark chỉ có ý nghĩa khi so sánh các giải pháp cho **cùng kết quả nghiệp vụ**. Với dự án này, cần kiểm tra:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Mảng rỗng | Cả ba trả `0L`. |
| Một phần tử chẵn | Cả ba trả `score(value, rounds)`. |
| Một phần tử lẻ | Cả ba trả `0L`. |
| Giá trị âm hoặc `Integer.MIN_VALUE` | Kiểm tra chẵn/lẻ thống nhất; không lỗi ép kiểu. |
| Dữ liệu nhiều phần tử | Cùng tổng, không mất hoặc cộng trùng phần tử. |
| `rounds` khác nhau | Ba cách vẫn khớp với mỗi cấu hình. |
| Lặp lại cùng dữ liệu | Tổng không phụ thuộc lịch chạy của các worker. |

Ví dụ kiểm tra đơn giản với Java 8+, không cần thư viện kiểm thử:

```java
package example;

import java.util.Arrays;

public class ThreeWaysCheck {
    static void check(int[] data, int rounds) {
        long expected = ThreeWays.loop(data, rounds);
        long actualSequential =
            ThreeWays.sequentialStream(data, rounds);
        long actualParallel =
            ThreeWays.parallelStream(data, rounds);

        if (expected != actualSequential || expected != actualParallel) {
            throw new AssertionError(
                "Không khớp với input " + Arrays.toString(data)
            );
        }
    }

    public static void main(String[] args) {
        for (int rounds : new int[] {4, 64}) {
            check(new int[] {}, rounds);
            check(new int[] {2}, rounds);
            check(new int[] {3}, rounds);
            check(new int[] {-4, -3, 0, Integer.MIN_VALUE}, rounds);
            check(ThreeWays.makeInput(1_000), rounds);
        }
        System.out.println("Các trường hợp kiểm tra đã khớp");
    }
}
```

Đây là **kiểm tra kết quả**, chưa phải benchmark hiệu năng. Cũng chưa phải một bộ kiểm thử bao phủ mọi trường hợp. Hãy tách việc kiểm tra đúng/sai khỏi mã được đo để không vô tình đo thêm chi phí `assert`, tạo mảng hoặc xuất log.

## 6. Vì sao không lấy một lần `System.nanoTime()` làm kết luận?

Đo một lần:

```java
long start = System.nanoTime();
long result = ThreeWays.parallelStream(data, 64);
long duration = System.nanoTime() - start;
```

có thể dùng để quan sát sơ bộ, nhưng **không đủ** để kết luận phương án nào tối ưu. Thời gian có thể thay đổi do:

- **JIT compilation:** JVM thường cần chạy một số lần trước khi tối ưu mã nóng; lần đầu không đại diện cho trạng thái đã warm-up.
- **Dead-code elimination:** nếu chương trình không dùng kết quả, trình biên dịch có thể loại bỏ một số công việc.
- **Garbage collection:** cấp phát và GC xuất hiện bất thường có thể làm một lần đo chậm hơn.
- **Scheduling:** hệ điều hành hoặc tiến trình khác lấy CPU làm độ trễ thay đổi.
- **Dynamic frequency / thermal throttling:** tốc độ CPU không luôn cố định, đặc biệt khi có tải liên tục.
- **JVM và môi trường:** phiên bản JDK, số core, kích thước heap và giới hạn container ảnh hưởng đến kết quả.

Ngoài ra, việc đo `makeInput` cùng với xử lý sẽ làm lẫn **chi phí chuẩn bị dữ liệu** vào chi phí của ba thuật toán. Nếu yêu cầu đo toàn bộ quy trình từ đầu đến cuối, phép đo đó cũng có giá trị, nhưng phải gọi tên rõ ràng và áp dụng **nhất quán** cho mọi phương án.

## 7. Benchmark bằng JMH

**JMH (Java Microbenchmark Harness)** là bộ công cụ được thiết kế để đo các thao tác Java có xét đến warm-up, lặp đo, fork JVM và tối ưu của JIT. JMH không có sẵn như một API trong JDK; cần một **dự án JMH có cấu hình thư viện và annotation processor tương thích**.

Thông thường, một dự án Maven JMH sử dụng `org.openjdk.jmh:jmh-core` cùng `org.openjdk.jmh:jmh-generator-annprocess` có **cùng phiên bản**. Có thể tạo cấu trúc dự án bằng JMH Maven archetype hoặc cấu hình tương đương. Không cần tự đo thời gian bằng `System.nanoTime()` bên trong phương thức `@Benchmark`.

Đặt lớp sau trong dự án đã có JMH và cùng package `example` với `ThreeWays`:

```java
package example;

import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
@Threads(1)
public class ThreeWaysBenchmark {

    @Param({"1000", "1000000"})
    public int size;

    @Param({"4", "64"})
    public int rounds;

    private int[] data;

    @Setup(Level.Trial)
    public void setup() {
        data = ThreeWays.makeInput(size);
    }

    @Benchmark
    public long imperativeLoop() {
        return ThreeWays.loop(data, rounds);
    }

    @Benchmark
    public long sequentialStream() {
        return ThreeWays.sequentialStream(data, rounds);
    }

    @Benchmark
    public long parallelStream() {
        return ThreeWays.parallelStream(data, rounds);
    }
}
```

### Vì sao bố trí benchmark như vậy?

| Thiết lập | Mục đích |
| --- | --- |
| `@State(Scope.Benchmark)` | Lưu dữ liệu đầu vào dùng chung trong lần chạy benchmark; mảng chỉ đọc nên không có tranh chấp ghi. |
| `@Setup(Level.Trial)` | Tạo input **ngoài đoạn tính thời gian**. |
| `@Param({"1000", "1000000"})` | Thử nguồn nhỏ và nguồn lớn, tránh kết luận chỉ từ một `n`. |
| `@Param({"4", "64"})` | Thử phép xử lý nhẹ và nặng trên cùng thuật toán. |
| `@Warmup` | Cho JVM cơ hội JIT tối ưu trước các lượt đo. |
| `@Measurement` | Thu nhiều lần đo độc lập theo cấu hình harness. |
| `@Fork(2)` | Thử trên nhiều tiến trình JVM để giảm phụ thuộc một lần khởi động. |
| `@Threads(1)` | Chỉ một luồng **gọi phương thức benchmark** cùng lúc; bên trong `parallelStream()` vẫn có thể dùng nhiều worker. |
| Trả `long` từ `@Benchmark` | JMH tiêu thụ giá trị trả về, giúp tránh việc kết quả không được quan sát. |

Từng cấu hình tham số tạo ra những benchmark case riêng. Trong phép đo này, **tạo stream và terminal operation đều nằm trong thời gian đo**: điều đó phản ánh chi phí gọi pipeline trong một ứng dụng thực tế. Việc tạo mảng không nằm trong thời gian đo, vì mục tiêu là so sánh ba cách **xử lý một input đã có**.

JMH không tự chứng minh phép tính đúng, và cũng không bảo đảm giải pháp nhanh nhất trong production. Nó cung cấp số liệu đáng tin hơn phép đo một lần khi cấu hình và môi trường phù hợp.

### Chạy và xuất kết quả

Với dự án JMH Maven đã cấu hình tạo tệp `target/benchmarks.jar`, có thể chạy:

```text
java -jar target/benchmarks.jar ThreeWaysBenchmark -rf csv -rff results.csv
```

Để quan sát thêm cấp phát bộ nhớ và hoạt động GC, JMH có profiler hỗ trợ:

```text
java -jar target/benchmarks.jar ThreeWaysBenchmark -prof gc
```

Các lệnh này là **hướng dẫn cho dự án JMH**, không phải kết quả benchmark đã được thực thi trong bài. Tùy cấu hình build, tên JAR và cách kích hoạt annotation processor có thể khác; phải sử dụng runner thực tế của dự án. Đo khi máy tương đối ổn định, hạn chế tác vụ nền và ghi lại phiên bản JDK, CPU, RAM, hệ điều hành cùng mức tải máy.

## 8. Cách đọc bảng kết quả và tính mức tăng tốc

JMH ở chế độ `Mode.AverageTime` cho kết quả thời gian trung bình trên mỗi lần thực hiện (*time/op*); **nhỏ hơn là nhanh hơn**. Nếu chuyển sang `Mode.Throughput`, đơn vị là số lần thực hiện trên một đơn vị thời gian; **lớn hơn là nhanh hơn**. Không trộn hai loại số liệu trong cùng một phép chia mà không đổi đơn vị.

Mẫu bảng để điền kết quả **sau khi chạy thực tế**:

| `size` | `rounds` | Loop (µs/op) | Sequential (µs/op) | Parallel (µs/op) | Phương án nhanh nhất |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1.000 | 4 | Điền số đo | Điền số đo | Điền số đo | Rút ra sau khi đo |
| 1.000 | 64 | Điền số đo | Điền số đo | Điền số đo | Rút ra sau khi đo |
| 1.000.000 | 4 | Điền số đo | Điền số đo | Điền số đo | Rút ra sau khi đo |
| 1.000.000 | 64 | Điền số đo | Điền số đo | Điền số đo | Rút ra sau khi đo |

**Không có số liệu đo sẵn** ở đây. Mọi giá trị thời gian phải do benchmark thật tạo ra; không điền những số chỉ dựa trên kỳ vọng rằng song song sẽ nhanh hơn.

Nếu muốn diễn giải mức tăng tốc giữa hai phương án, dùng:

\[
\text{Speedup} = \frac{\text{Thời gian phương án gốc}}{\text{Thời gian phương án mới}}
\]

Ví dụ **giả định để hiểu công thức**, không phải số đo của dự án: nếu một phương án mất 24 ms và phương án khác mất 8 ms trên cùng đầu vào, thì speedup là `24 / 8 = 3`, tức khoảng **3 lần**. Mức tăng tốc ấy không đồng nghĩa chương trình sử dụng đúng ba core, cũng không chứng minh chi phí bộ nhớ không tăng.

Khi đánh giá số đo, nên xem cả độ biến thiên (confidence interval hoặc độ lệch giữa các fork/iteration), không chỉ chọn lần chạy nhanh nhất. Chênh lệch nhỏ hơn nhiễu đo thì chưa đủ cơ sở khẳng định một cách xử lý nhanh hơn.

## 9. Giải thích kết quả theo ba kịch bản

### Kịch bản A: đầu vào nhỏ, hàm `score` nhẹ

Với `size = 1_000`, `rounds = 4`, lượng tính toán hữu ích ít. Các chi phí tương đối nổi bật có thể là:

- Tạo pipeline và bộ máy traversal đối với stream.
- Tạo và phối hợp các tác vụ song song.
- Gộp các kết quả bộ phận cho `sum`.

Vòng lặp có thể nhanh nhất ở trường hợp này. Nếu kết quả đo thực tế ngược lại, cần kiểm tra nhiễu, cách JIT tối ưu, độ chính xác của benchmark và đặc điểm phần cứng **trước khi phủ nhận kết quả**.

### Kịch bản B: đầu vào lớn, hàm `score` nặng

Với `size = 1_000_000`, `rounds = 64`, phần lớn thời gian có thể nằm ở hàm biến đổi CPU-bound. Mảng `int[]` có Spliterator chia nguồn thuận lợi, mỗi phần tử độc lập và phép gộp có tính kết hợp. Vì vậy stream song song có **cơ hội** thắng hai cách tuần tự trên máy có nhiều core rảnh.

Tuy nhiên, speedup thường **không tỷ lệ tuyến tính vô hạn với số core**. Công việc chia/gộp, tranh chấp băng thông bộ nhớ, tải hệ thống, turbo/thermal và các phần không song song hóa được sẽ giới hạn lợi ích.

### Kịch bản C: đầu vào lớn nhưng biến đổi rẻ

Với `size = 1_000_000`, `rounds = 4`, phép tính trên mỗi phần tử có thể chưa đủ nặng để bù overhead phân chia. Kết quả có thể cho thấy vòng lặp hoặc stream tuần tự cạnh tranh tốt với song song.

Điểm then chốt là **không chỉ tăng số phần tử, mà còn phải xét chi phí xử lý trên từng phần tử**. Đó là lý do benchmark sử dụng hai tham số `size` và `rounds` thay vì chỉ thử một cấu hình.

## 10. Spliterator và độ hạt tác vụ giải thích một phần hiệu năng

Stream song song được tổ chức qua `Spliterator`: `trySplit` cung cấp các phần dữ liệu con, `estimateSize` và `characteristics` giúp framework quyết định cách chia/tối ưu. Nguồn `Arrays.stream(int[])` có các đặc tính phù hợp cho việc chia theo khoảng chỉ số; không phải mọi nguồn đều như vậy.

| Nguồn | Đặc điểm có thể ảnh hưởng benchmark |
| --- | --- |
| `int[]`, `IntStream.range` | Kích thước rõ ràng, thường dễ chia đều. |
| `ArrayList` | Có chỉ số, nguồn khá thuận lợi cho chia. |
| `LinkedList` | Traversal/chia có thể tốn chi phí khác mảng. |
| `Stream.iterate` | Dãy truy hồi có phụ thuộc trạng thái, không giống công việc theo chỉ số độc lập. |
| `Files.lines` | Có I/O, tài nguyên phải đóng, dữ liệu và khả năng chia phụ thuộc nguồn. |
| Nguồn tự viết với `trySplit() == null` | Khó khai thác song song vì không chia được phần việc. |

Đừng “tối ưu” bằng cách tự khai báo `SIZED`/`SUBSIZED` sai trên một custom Spliterator. Các characteristics là **cam kết về ngữ nghĩa**, không phải gợi ý tăng tốc vô điều kiện.

Nếu workload thực tế là nhiều nhóm dữ liệu không cân đối, có thể thử chia nhóm lớn thành **chunk** và song song hóa theo chunk. Đừng tự động lồng `parallelStream()` ở cả outer lẫn inner; việc đó có thể tăng tác vụ, tranh chấp pool và độ trễ mà không tăng số core CPU.

## 11. Tại sao không dùng `Stream<Integer>` để so sánh với `int[]` trong thí nghiệm chính?

Nếu vòng lặp duyệt `int[]`, nhưng stream lại dùng `List<Integer>` với `map` và `reduce`, thí nghiệm đã đổi **hình dạng dữ liệu và chi phí boxing/unboxing**. Kết quả có thể phản ánh chi phí wrapper `Integer` nhiều hơn khác biệt giữa vòng lặp với Stream API.

Trong bài này, cả ba đều bắt đầu từ **cùng `int[]`** và dùng giá trị số nguyên thủy. Có thể làm **thí nghiệm phụ** riêng:

```java
long total = boxedValues.stream()
    .filter(value -> (value & 1) == 0)
    .mapToLong(value -> ThreeWays.score(value, rounds))
    .sum();
```

Khi báo cáo thí nghiệm phụ, cần ghi rõ input là `List<Integer>` và phân biệt thời gian chuẩn bị `boxedValues` có được tính hay không. Đừng lấy số liệu từ hai kiểu dữ liệu khác nhau để tuyên bố “Stream luôn chậm hơn vòng lặp”.

## 12. Cảnh giác với số học, trạng thái và phép tổng hợp

Ba pipeline trong dự án dùng kết quả `score` hữu hạn, cộng bằng `long` và không thay đổi nguồn. Nếu thay bài toán, các điều kiện đúng đắn có thể thay đổi:

| Thay đổi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Dùng `int` cho tổng rất lớn | Tràn `int`, số đo vẫn nhanh nhưng kết quả sai. | Dùng `long` đúng từ trước phép cộng hoặc kiểm tra tràn. |
| Dùng `double` và so sánh bằng `==` | Sai số dấu phẩy động, kết quả song song có thể lệch bit cuối. | Định nghĩa sai số phù hợp; lưu ý thứ tự gộp. |
| Đọc `Math.random()` trong mapper | Dữ liệu từng lượt không tái lập. | Cố định bộ dữ liệu và seed, không chia sẻ trạng thái generator tùy tiện. |
| Ghi vào `ArrayList` ngoài trong `parallel().forEach` | Tranh chấp, mất hoặc trùng phần tử. | Dùng `collect` hoặc reduction hợp lệ. |
| Dùng một phép `reduce` không kết hợp | Kết quả phụ thuộc cách chia/gộp. | Chọn combiner có identity và tính kết hợp đúng hợp đồng. |
| Sửa mảng nguồn trong lúc đo | Các lần chạy không còn cùng input. | Giữ dữ liệu bất biến trong toàn phiên benchmark. |
| Gọi API mạng hoặc DB trong `score` | Benchmark bị chi phối bởi I/O, timeout và giới hạn kết nối. | Thiết kế benchmark I/O riêng có điều phối đồng thời rõ ràng. |

Một phép toán có thể **rất nhanh nhưng sai ngữ nghĩa**, nhất là khi có side effect hoặc lấy ít phần tử hơn yêu cầu. Tính đúng đắn luôn là điều kiện trước khi đánh giá tốc độ.

## 13. Phân tích cấp phát bộ nhớ, GC và độ trễ

Time/op không phải chỉ số duy nhất của hiệu năng. Hãy xem xét:

1. **Allocation rate:** số byte/op hoặc byte/giây từ JMH GC profiler; có tăng đáng kể khi dùng pipeline không?
2. **Garbage collection:** số lần và thời gian GC có ảnh hưởng đến các fork không?
3. **CPU utilization:** stream song song có thực sự khai thác nhiều core không, hay bị giới hạn bởi một nguồn khó chia?
4. **Latency variance:** các lần đo có ổn định không, đặc biệt khi nhiều request cùng dùng common pool?
5. **Memory bandwidth/cache:** nhiều worker cùng đọc mảng có thể tranh chấp tài nguyên bộ nhớ.

Trong ví dụ chuẩn, chúng ta dùng primitive stream, `filter`, `mapToLong` và `sum` nên **không cần tạo `List<Long>` trung gian chứa toàn bộ phần tử**. Nhưng stream vẫn có thể tạo các đối tượng pipeline hoặc tác vụ nội bộ; một benchmark có thể cho thấy khác biệt cấp phát ngay cả khi không boxing từng giá trị.

Tách biệt **độ trễ một phép gọi** với **throughput của toàn ứng dụng**. Một phép gọi `parallelStream()` có thể kết thúc sớm hơn khi chạy riêng lẻ, nhưng nhiều request đồng thời cùng dùng tài nguyên CPU/pool có thể khiến throughput hoặc p99 latency xấu đi. Đây là phép thử khác với JMH `@Threads(1)` và nên được báo cáo riêng.

## 14. Cấu trúc báo cáo thí nghiệm

Một báo cáo có thể gồm những phần sau:

### A. Môi trường và cách đo

```text
JDK:                <phiên bản thực tế>
CPU / logical cores:<thông tin máy đo>
RAM / giới hạn heap:<thông tin thực tế>
OS:                 <hệ điều hành>
JMH:                <phiên bản dùng trong dự án>
Benchmark mode:     AverageTime, microseconds/op
Warm-up:            3 iterations x 1 second
Measurement:        5 iterations x 1 second
Forks:              2
JMH calling threads:1
Inputs:             size = 1000 / 1000000
                    rounds = 4 / 64
```

Đây là **mẫu khai báo**, không phải cấu hình máy đã được quan sát trong bài. Người thực hành cần điền dữ liệu thật thay cho các dấu chỗ trống.

### B. Kết quả và tính đúng

Lưu bảng time/op theo `size`, `rounds` và tên phương án, kèm mức biến thiên. Ghi cách đã xác nhận ba cách cho cùng tổng. Nếu có trường hợp lệch kết quả, **dừng kết luận hiệu năng** để điều tra ngữ nghĩa trước.

### C. Giải thích có dẫn chứng từ số liệu

Với mỗi cấu hình, đặt câu hỏi:

- Phần tử ít hay nhiều? `score` nặng hay nhẹ?
- Chi phí pipeline, tách nguồn và gộp có chiếm tỷ lệ lớn không?
- JMH có cho thấy nhiễu cao giữa các lần đo hoặc fork không?
- CPU, GC hoặc bộ nhớ có dấu hiệu nghẽn không?
- Vì sao một phương án thắng ở cấu hình này nhưng thua ở cấu hình khác?

### D. Kết luận và giới hạn

Không viết “`parallelStream` nhanh gấp N lần” nếu N chưa được đo. Viết kết luận có phạm vi: **trên JDK, phần cứng, dữ liệu và mức tải đã thử**, phương án X tốt hơn hoặc các phương án không khác đáng kể. Nêu điều kiện có thể khiến kết luận đổi khác.

## 15. Mở rộng dự án sau phép so sánh cơ bản

### Mở rộng 1 — Độ lớn dữ liệu và ngưỡng hòa vốn

Thêm các mức `size` trung gian như `10_000`, `100_000` và `500_000`. Quan sát xem từ mức nào parallel stream bắt đầu cạnh tranh với tuần tự. **Ngưỡng hòa vốn** không cố định giữa các máy và mức `rounds`.

### Mở rộng 2 — Nguồn object và boxing

Giữ cùng bài toán nhưng chuyển mảng thành `List<Integer>`. So sánh `Stream<Integer>` với `IntStream`. Ghi riêng chi phí dựng dữ liệu boxed và cảnh giác với tác động của GC.

### Mở rộng 3 — Thử nhiều request đồng thời

Benchmark nhiều lời gọi xử lý diễn ra cùng lúc. Quan sát throughput và p95/p99, thay vì chỉ nhìn độ trễ một lời gọi. Đừng kết luận từ `@Threads(1)` rằng production với nhiều request cũng có hiệu năng giống vậy.

### Mở rộng 4 — Dữ liệu nhóm mất cân bằng

Thay một mảng phẳng bằng các lô có kích thước khác nhau. So sánh một pipeline song song trên từng lô, một pipeline phẳng và cách chia thành chunk. Tránh mặc định việc song song hóa hai tầng sẽ tối ưu.

### Mở rộng 5 — Thống kê thay vì một tổng

Thay `sum` bằng `summaryStatistics` hoặc `Collectors.summarizingLong` để lấy count/sum/min/max/average. Khi cần nhiều chỉ số, hãy so sánh **một lần tổng hợp** với nhiều pipeline độc lập, bảo đảm thời gian đo bao gồm cùng lượng công việc và dữ liệu rỗng được xử lý đúng.

## 16. Bài tập tự đánh giá

1. **Đúng trước nhanh:** Tại sao cần so sánh kết quả ba cách trước khi đo? Cho một ví dụ parallel stream chạy nhanh nhưng trả sai do shared mutable state.
2. **Dữ liệu nhỏ:** Vì sao `size=1000` và `rounds=4` có thể khiến parallel stream chậm hơn vòng lặp?
3. **Nguồn chia được:** Vai trò của `Spliterator.trySplit`, `SIZED` và đặc tính nguồn mảng trong xử lý song song là gì?
4. **Đo lường:** Giải thích `@Warmup`, `@Fork`, `@Param`, `@Threads(1)` và vì sao phương thức `@Benchmark` trả kết quả `long`.
5. **Hai loại chỉ số:** Phân biệt latency/time-op và throughput. Vì sao một phép xử lý nhanh hơn trong điều kiện chạy đơn lẻ chưa chắc cải thiện throughput dưới tải cao?
6. **Phân tích có điều kiện:** Nếu kết quả đo cho thấy parallel thắng rõ ở `size=1_000_000, rounds=64` nhưng thua ở `size=1000, rounds=4`, hãy viết kết luận không khái quát quá mức.
7. **Kiểm tra phạm vi:** Tổng `long` trong ví dụ có thể tràn với mảng lớn nhất được tạo bởi `makeInput` không? Hãy dùng cận trên của `score` và `size` để giải thích.
8. **Thiết kế lại workload:** Nếu dữ liệu nằm trong nhiều tệp và phần lớn thời gian chờ I/O, vì sao benchmark CPU-bound ở bài này không đủ cơ sở để áp dụng `parallelStream()` cho tác vụ đọc tệp?

## 17. Checklist hoàn thành dự án

- [ ] Ba phương án dùng cùng input và cùng `score`, chỉ khác cách duyệt và chế độ song song.
- [ ] Mảng nguồn không bị thay đổi trong benchmark.
- [ ] Các trường hợp rỗng, nhỏ, âm và lớn đều được kiểm tra tính đúng.
- [ ] Đã chạy JMH với warm-up, nhiều lần đo và fork hợp lý.
- [ ] Kết quả trả về từ mỗi `@Benchmark` được JMH quan sát.
- [ ] Thời gian tạo dữ liệu được loại ra hoặc được tính một cách nhất quán theo mục tiêu phép đo.
- [ ] Bảng kết quả ghi rõ size, rounds, đơn vị và mức biến thiên.
- [ ] Có giải thích overhead, JIT, Spliterator, CPU/GC và giới hạn của song song.
- [ ] Không sử dụng các số liệu **giả định** như thể đó là số đo thực.
- [ ] Kết luận ghi rõ môi trường áp dụng và những giới hạn của thử nghiệm.

**Ghi nhớ:** Đo hiệu năng tốt không bắt đầu bằng việc thêm `parallel()`, mà bằng **xác định chính xác bài toán, xây các cách giải tương đương và kiểm tra kết quả**. Dùng JMH để quan sát ba cách xử lý trên nhiều kích thước và mức chi phí CPU, sau đó giải thích kết quả bằng chi phí pipeline, khả năng chia của Spliterator, phép reduction, tài nguyên phần cứng và biến động JVM. Hãy chỉ chọn phương án tối ưu **trong phạm vi số liệu đã đo**, thay vì coi một mẫu benchmark là quy luật chung cho toàn bộ Java Stream API.
