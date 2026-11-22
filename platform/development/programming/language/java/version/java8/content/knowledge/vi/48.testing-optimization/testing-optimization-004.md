# Kiểm thử Collector theo luật đồng nhất và kết hợp trong Java Streams

## 1. Vì sao custom Collector cần kiểm thử theo luật?

Java Streams gom dữ liệu bằng `Stream.collect(Collector)`. Với collector có sẵn như `Collectors.toList()` hoặc `Collectors.groupingBy()`, hợp đồng đã được JDK triển khai. Khi tự viết `Collector<T, A, R>`, bạn phải bảo đảm việc tích lũy và ghép các phần kết quả vẫn đúng dù stream chạy tuần tự hay chia nhỏ để chạy song song.

Hai luật đại số quan trọng nhất là:

- **Luật đồng nhất (identity constraint):** ghép một trạng thái tích lũy với accumulator rỗng do supplier tạo ra phải cho kết quả tương đương trạng thái ban đầu.
- **Luật kết hợp (associativity constraint):** chia input thành các phần, tích lũy riêng rồi ghép theo các cách đặt ngoặc khác nhau phải cho kết quả tương đương với tích lũy tuần tự.

Đây là điều kiện đúng đắn của custom collector. Stream runtime có quyền chia dữ liệu thành nhiều phần và gọi combiner theo cấu trúc cây. Một collector chỉ đúng khi các cách phân hoạch hợp lệ đều giữ được ngữ nghĩa kết quả.

Ví dụ, collector tính tổng phải ghép tổng của các partition thành tổng toàn bộ input. Collector gom chuỗi phải giữ encounter order nếu kết quả có thứ tự. Collector đếm hoặc tính min/max phải xử lý đúng cả partition rỗng.

Bài này xây dựng quy trình kiểm thử luật cho custom collector: kiểm tra trạng thái qua finisher, thử nhiều điểm chia và parenthesization, xác minh characteristics, rồi đối chiếu sequential với parallel stream.

## 2. Cấu trúc của Collector

Một collector gồm năm thành phần:

| Thành phần | Kiểu | Trách nhiệm |
| --- | --- | --- |
| Supplier | `Supplier<A>` | Tạo accumulator rỗng mới |
| Accumulator | `BiConsumer<A, T>` | Thêm phần tử T vào accumulator A |
| Combiner | `BinaryOperator<A>` | Ghép hai accumulator thành một |
| Finisher | `Function<A, R>` | Chuyển accumulator A thành kết quả R |
| Characteristics | `Set<Collector.Characteristics>` | Khai báo đặc tính về concurrency, ordering và finishing |

Chữ ký khái quát:

```java
public interface Collector<T, A, R> {
    Supplier<A> supplier();
    BiConsumer<A, T> accumulator();
    BinaryOperator<A> combiner();
    Function<A, R> finisher();
    Set<Characteristics> characteristics();
}
```

`T` là kiểu phần tử stream, `A` là kiểu trạng thái trung gian, còn `R` là kết quả cuối. Chúng có thể giống nhau nhưng không bắt buộc.

Ví dụ collector thống kê:

- `T = Integer`: mỗi phần tử đầu vào là số nguyên.
- `A = Stats`: trạng thái mutable giữ count, sum, min, max.
- `R = StatsResult`: kết quả immutable trả về sau khi finish.

Tách `A` và `R` giúp collector dùng cấu trúc mutable hiệu quả khi gom dữ liệu nhưng vẫn trả kết quả immutable cho caller.

## 3. Luật đồng nhất (identity constraint)

### 3.1. Phát biểu của luật

Với accumulator đã có dữ liệu `a`, gọi supplier để tạo trạng thái rỗng `e`. Khi kết hợp `a` với `e`, kết quả phải tương đương với `a`:

```java
A a = ...;
A empty = supplier.get();
A combined = combiner.apply(a, empty);
```

Điều kiện:

```text
equivalent(combiner.apply(a, supplier.get()), a)
```

Đây là **right identity** của combiner theo hợp đồng Collector. Với collector có phép ghép được thiết kế như monoid, nên kiểm tra thêm left identity:

```java
equivalent(combiner.apply(supplier.get(), a), a)
```

Hợp đồng Collector nêu rõ phép ghép với accumulator rỗng ở phía phải. Kiểm tra cả hai phía là kiểm tra mạnh hơn cho collector có identity hai phía.

### 3.2. Ví dụ accumulator thống kê

```java
final class Stats {
    long count;
    long sum;
    int min = Integer.MAX_VALUE;
    int max = Integer.MIN_VALUE;
}
```

Accumulator rỗng có `count = 0`, `sum = 0`. Khi ghép với accumulator rỗng, các trường của accumulator có dữ liệu phải không đổi. Khi accumulator bên trái rỗng và bên phải có dữ liệu, kết quả phải tương đương bên phải.

Combiner sai có thể đặt min/max về giá trị mặc định hoặc cộng thêm giá trị khởi tạo không hợp lệ. Identity test phát hiện lỗi này ngay cả khi một vài stream không rỗng vẫn chạy qua.

### 3.3. Supplier phải tạo container mới

Với accumulator mutable, mỗi lần gọi supplier phải tạo container độc lập:

```java
A first = supplier.get();
A second = supplier.get();

if (first == second) {
    throw new AssertionError("supplier reused a mutable container");
}
```

Nếu supplier trả về cùng object dùng chung, các partition có thể ghi đè dữ liệu lẫn nhau. Đừng dùng mutable static singleton làm accumulator rỗng.

### 3.4. Chụp kết quả trước khi combiner mutate

Nhiều combiner được phép mutate accumulator bên trái và trả lại nó. Vì vậy, khi test identity, hãy chụp kết quả kỳ vọng **trước khi gọi combiner**:

```java
R expected = finisher.apply(a);
A combined = combiner.apply(a, supplier.get());
R actual = finisher.apply(combined);

assertEquivalent(expected, actual);
```

Nếu giữ reference `a` rồi so sánh sau khi combiner mutate nó, bạn có thể vô tình so sánh cùng một object với chính nó và bỏ lọt lỗi.

## 4. Luật kết hợp (associativity constraint)

### 4.1. Phát biểu của luật

Giả sử input được chia thành ba đoạn liên tiếp `P1`, `P2`, `P3`. Tích lũy từng đoạn tạo ra `a`, `b`, `c`. Hai cách đặt ngoặc phải cho kết quả tương đương:

```text
left  = combine(combine(a, b), c)
right = combine(a, combine(b, c))
```

Cả hai phải tương đương với kết quả tích lũy tuần tự toàn bộ input:

```text
sequential = accumulate(P1 + P2 + P3)
```

Luật kết hợp cho phép runtime chọn cấu trúc cây ghép khác nhau. Nếu combiner chỉ đúng với một thứ tự ghép cụ thể, parallel reduction có thể trả kết quả sai.

### 4.2. Vì sao một lần parallelStream chưa đủ?

Một lần gọi `input.parallelStream().collect(customCollector)` chỉ chạy một cách phân hoạch/ghép mà runtime chọn trong lần thực thi đó. Nó không bảo đảm đã thử mọi điểm chia, mọi cách đặt ngoặc hoặc partition rỗng.

Một lỗi combiner có thể tình cờ không xuất hiện với kích thước input, số thread hoặc cách chia dữ liệu của test hiện tại. Vì vậy cần kiểm tra luật trực tiếp với partition có kiểm soát, sau đó vẫn chạy test parallel stream.

### 4.3. Kiểm tra ba partition và hai parenthesization

Với mỗi cặp điểm chia `0 <= i <= j <= n`:

- `P1 = input[0, i)`.
- `P2 = input[i, j)`.
- `P3 = input[j, n)`.

Tính ba accumulator độc lập rồi kiểm tra cả:

```java
combine(combine(a, b), c)
combine(a, combine(b, c))
```

Cách lặp này bao gồm partition rỗng ở đầu, giữa hoặc cuối. Với input có `n` phần tử, số bộ ba đoạn liên tiếp theo hai điểm chia là `(n + 1)(n + 2) / 2`.

### 4.4. Combiner có thể mutate bên trái

Mẫu phổ biến:

```java
static Stats combine(Stats left, Stats right) {
    left.count += right.count;
    left.sum += right.sum;
    left.min = Math.min(left.min, right.min);
    left.max = Math.max(left.max, right.max);
    return left;
}
```

Mutation bên trái được chấp nhận. Nhưng không được phụ thuộc vào việc một accumulator luôn là bên trái hoặc được ghép đúng một lần theo thứ tự cố định. Tạo accumulator mới cho từng nhánh kiểm thử; không tái sử dụng trạng thái đã bị consume ở phép ghép khác.

## 5. Định nghĩa “tương đương” cho kết quả collector

Luật không yêu cầu mọi accumulator nội bộ có cùng object identity hoặc cùng bố trí bộ nhớ. Điều cần giữ là **ngữ nghĩa kết quả**.

Với collector có finisher, cách so sánh thường là:

```java
R expected = finisher.apply(sequentialAccumulator);
R actual = finisher.apply(combinedAccumulator);

assertEquivalent(expected, actual);
```

Nếu `R` có `equals` đúng theo domain, có thể dùng `assertEquals`. Nếu kết quả là số thực, thứ tự cộng có thể tạo sai khác làm tròn; cần comparator/tolerance hoặc quy tắc số học phù hợp.

Ví dụ:

- Thống kê count/sum/min/max: so sánh từng trường.
- Tập hợp không thứ tự: so sánh theo set equality.
- Danh sách có thứ tự: so sánh chính xác phần tử và thứ tự.
- Tổng tiền tệ: dùng kiểu số học phù hợp như `BigDecimal` và scale/rounding rule được xác định.
- Tổng floating-point: xác định tolerance hoặc thuật toán cộng có độ ổn định số học.

Không dùng `toString()` cho mọi collector; equivalence phải phản ánh hợp đồng nghiệp vụ.

## 6. Ba Characteristics của Collector

`Collector.Characteristics` có ba giá trị:

| Characteristic | Ý nghĩa | Chỉ khai báo khi |
| --- | --- | --- |
| `CONCURRENT` | Accumulator có thể được gọi đồng thời trên cùng một result container | Accumulator thực sự thread-safe |
| `UNORDERED` | Collection operation không cam kết giữ encounter order | Kết quả không phụ thuộc thứ tự đầu vào |
| `IDENTITY_FINISH` | Finisher là identity; A có thể cast sang R | A và R tương thích, không cần chuyển đổi |

### 6.1. CONCURRENT không đồng nghĩa “parallel được”

Collector không có `CONCURRENT` vẫn có thể dùng với parallel stream. Runtime thường tạo accumulator riêng cho partition rồi kết hợp bằng combiner.

`CONCURRENT` có nghĩa accumulator có thể được gọi từ nhiều thread trên **cùng một container**. Nếu mutable state là `ArrayList` hoặc object không đồng bộ, không được tự ý khai báo characteristic này.

Với concurrent collector, phải test race condition và thread-safety riêng. Identity/associativity test đơn luồng không chứng minh accumulator an toàn khi nhiều thread cùng mutate.

### 6.2. UNORDERED chỉ đúng khi kết quả không phụ thuộc encounter order

Collector tính count, sum, min, max thường không phụ thuộc thứ tự, nên có thể đánh dấu `UNORDERED` nếu phép toán và kiểu số học thực sự giữ semantics đó.

Collector nối chuỗi thành danh sách hoặc tạo chuỗi theo thứ tự input thường **không** được đánh dấu `UNORDERED`. Phép ghép có thể associative nhưng không commutative:

```text
("ab" + "c") == ("a" + "bc")  // true
"ab" + "c" != "c" + "ab"      // true
```

Luật kết hợp không đòi hỏi phép ghép giao hoán. Đừng thêm `UNORDERED` chỉ vì parallel test hiện tại cho kết quả trùng.

### 6.3. IDENTITY_FINISH chỉ dùng khi finisher thật sự là identity

Nếu accumulator `A` cũng chính là kết quả `R` và finisher chỉ trả nguyên object đó, có thể khai báo `IDENTITY_FINISH`. Nếu finisher tạo DTO mới, immutable result, string hoặc aggregate khác kiểu, không được khai báo.

Khi có `IDENTITY_FINISH`, runtime được phép bỏ qua finisher và thực hiện unchecked cast từ A sang R. Khai báo sai có thể gây lỗi kiểu hoặc trả về trạng thái trung gian thay vì kết quả dự kiến.

## 7. Ordered collector và unordered collector

Một collector giữ encounter order cần bảo toàn thứ tự khi combiner ghép hai partition: partition bên trái phải đứng trước partition bên phải nếu stream có encounter order.

Ví dụ collector gom danh sách:

```java
List<String> left = new ArrayList<>(Arrays.asList("A", "B"));
List<String> right = new ArrayList<>(Arrays.asList("C", "D"));
left.addAll(right);
```

Kết quả `A, B, C, D` đúng khi left là đoạn input trước right. Nếu đảo thứ tự ghép, kết quả thay đổi.

Không đổi vị trí hai operand rồi bắt buộc kết quả giống nhau nếu collector ordered. Associativity không cho phép hoán đổi thứ tự operand.

Nếu collector được đánh dấu `UNORDERED`, hãy thử permutation đầu vào và xác nhận kết quả tương đương. Nếu không đánh dấu `UNORDERED`, không được bỏ qua thứ tự khi so sánh.

**Phân biệt ba khái niệm:**

- **Associative:** thay đổi cách đặt ngoặc khi ghép không đổi kết quả.
- **Commutative:** đổi vị trí hai toán hạng không đổi kết quả.
- **Unordered collector:** kết quả không cam kết giữ encounter order.

Associativity không kéo theo commutativity. Ordered collector hoàn toàn có thể associative nhưng không unordered.

## 8. Kiểm thử finisher

Finisher chuyển accumulator `A` thành kết quả `R`. Nó cũng là một phần của hợp đồng và phải được test.

### 8.1. Finisher không nên phụ thuộc số lần được gọi

Thông thường, finisher được gọi sau khi accumulation hoàn tất. Không viết finisher có side effect, ghi database hoặc tăng counter nghiệp vụ. Collector nên tạo kết quả từ trạng thái trung gian một cách rõ ràng.

### 8.2. Finisher có thể tạo snapshot immutable

```java
StatsResult finish(Stats stats) {
    return new StatsResult(stats.count, stats.sum, stats.min, stats.max);
}
```

Cách này tách mutable accumulator khỏi result công khai. Test nên xác nhận kết quả không bị thay đổi khi accumulator tiếp tục bị mutate sau khi đã finish, nếu API result được kỳ vọng immutable.

### 8.3. Không khai báo IDENTITY_FINISH cho finisher chuyển kiểu

Nếu `Stats` được chuyển thành `StatsResult`, finisher không phải identity. Characteristics của collector phải bỏ `IDENTITY_FINISH`. Đây là lỗi cấu hình dễ bị bỏ qua vì test tuần tự vẫn có thể chạy trước khi runtime tối ưu reduction.

## 9. Thiết kế collector thống kê dùng trong bài kiểm thử

Ví dụ sẽ tạo collector nhận `Integer` và trả `StatsResult`:

- `supplier` tạo `Stats` rỗng.
- `accumulator` tăng count, cộng sum, cập nhật min/max.
- `combiner` ghép count, sum, min/max vào trạng thái bên trái.
- `finisher` tạo kết quả immutable.
- `UNORDERED` được khai báo vì thống kê không phụ thuộc thứ tự.
- Không khai báo `CONCURRENT` vì `Stats` mutable không thread-safe.
- Không khai báo `IDENTITY_FINISH` vì `Stats` được chuyển thành `StatsResult`.

Để tránh overflow trong ví dụ, count và sum dùng `Math.addExact`. Với miền input lớn hơn, overflow sẽ báo lỗi rõ ràng thay vì wrap-around âm thầm.

## 10. Chương trình Java 8 hoàn chỉnh kiểm tra identity và associativity

Tạo file **CollectorLawDemo.java**. Chương trình chỉ dùng JDK, không cần database hoặc thư viện test ngoài.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.function.BiConsumer;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.stream.Collector;

public class CollectorLawDemo {
    static final class Stats {
        long count;
        long sum;
        int min = Integer.MAX_VALUE;
        int max = Integer.MIN_VALUE;

        void add(Integer value) {
            if (value == null) {
                throw new NullPointerException("value");
            }
            count = Math.addExact(count, 1L);
            sum = Math.addExact(sum, value.longValue());
            min = Math.min(min, value);
            max = Math.max(max, value);
        }

        static Stats combine(Stats left, Stats right) {
            boolean leftWasEmpty = left.count == 0L;

            left.count = Math.addExact(left.count, right.count);
            left.sum = Math.addExact(left.sum, right.sum);

            if (right.count != 0L) {
                if (leftWasEmpty) {
                    left.min = right.min;
                    left.max = right.max;
                } else {
                    left.min = Math.min(left.min, right.min);
                    left.max = Math.max(left.max, right.max);
                }
            }
            return left;
        }
    }

    static final class StatsResult {
        final long count;
        final long sum;
        final int min;
        final int max;

        StatsResult(Stats stats) {
            this.count = stats.count;
            this.sum = stats.sum;
            this.min = stats.count == 0L ? 0 : stats.min;
            this.max = stats.count == 0L ? 0 : stats.max;
        }

        double average() {
            return count == 0L ? 0.0 : (double) sum / count;
        }

        @Override
        public boolean equals(Object other) {
            if (!(other instanceof StatsResult)) {
                return false;
            }
            StatsResult that = (StatsResult) other;
            return count == that.count
                && sum == that.sum
                && min == that.min
                && max == that.max;
        }

        @Override
        public int hashCode() {
            int result = (int) (count ^ (count >>> 32));
            result = 31 * result + (int) (sum ^ (sum >>> 32));
            result = 31 * result + min;
            result = 31 * result + max;
            return result;
        }

        @Override
        public String toString() {
            return "count=" + count
                + ", sum=" + sum
                + ", min=" + min
                + ", max=" + max
                + ", average=" + average();
        }
    }

    static final Supplier<Stats> SUPPLIER = Stats::new;
    static final BiConsumer<Stats, Integer> ACCUMULATOR = Stats::add;
    static final BinaryOperator<Stats> COMBINER = Stats::combine;
    static final Function<Stats, StatsResult> FINISHER = StatsResult::new;

    static final Collector<Integer, Stats, StatsResult> COLLECTOR =
        Collector.of(
            SUPPLIER,
            ACCUMULATOR,
            COMBINER,
            FINISHER,
            Collector.Characteristics.UNORDERED
        );

    static Stats accumulate(List<Integer> values) {
        Stats state = SUPPLIER.get();
        for (Integer value : values) {
            ACCUMULATOR.accept(state, value);
        }
        return state;
    }

    static StatsResult finish(Stats state) {
        return FINISHER.apply(state);
    }

    static void assertEquivalent(
            StatsResult expected, StatsResult actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                label + ": expected " + expected + " but got " + actual);
        }
    }

    static int[] verifyLaws(List<List<Integer>> cases) {
        int identityChecks = 0;
        int associativityPartitions = 0;

        for (List<Integer> values : cases) {
            StatsResult baseline = finish(accumulate(values));

            for (int i = 0; i <= values.size(); i++) {
                List<Integer> prefix = values.subList(0, i);

                Stats rightState = accumulate(prefix);
                StatsResult rightExpected = finish(rightState);
                Stats rightCombined = COMBINER.apply(
                    rightState, SUPPLIER.get());
                assertEquivalent(
                    rightExpected, finish(rightCombined), "right identity");
                identityChecks++;

                Stats leftState = accumulate(prefix);
                StatsResult leftExpected = finish(leftState);
                Stats leftCombined = COMBINER.apply(
                    SUPPLIER.get(), leftState);
                assertEquivalent(
                    leftExpected, finish(leftCombined), "left identity");
                identityChecks++;
            }

            for (int i = 0; i <= values.size(); i++) {
                for (int j = i; j <= values.size(); j++) {
                    List<Integer> first = values.subList(0, i);
                    List<Integer> second = values.subList(i, j);
                    List<Integer> third = values.subList(j, values.size());

                    Stats leftGrouped = COMBINER.apply(
                        COMBINER.apply(
                            accumulate(first), accumulate(second)),
                        accumulate(third));

                    Stats rightGrouped = COMBINER.apply(
                        accumulate(first),
                        COMBINER.apply(
                            accumulate(second), accumulate(third)));

                    assertEquivalent(
                        baseline, finish(leftGrouped), "left association");
                    assertEquivalent(
                        baseline, finish(rightGrouped), "right association");

                    associativityPartitions++;
                }
            }
        }

        return new int[] {identityChecks, associativityPartitions};
    }

    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(
            -4, 10, 10, 0, 3, -9,
            Integer.MIN_VALUE, Integer.MAX_VALUE);

        List<List<Integer>> cases = Arrays.asList(
            Collections.<Integer>emptyList(),
            Collections.singletonList(42),
            values
        );

        Stats first = SUPPLIER.get();
        Stats second = SUPPLIER.get();
        if (first == second) {
            throw new AssertionError("supplier reused a mutable container");
        }

        int[] checks = verifyLaws(cases);

        if (!COLLECTOR.characteristics().contains(
                Collector.Characteristics.UNORDERED)) {
            throw new AssertionError("UNORDERED characteristic missing");
        }
        if (COLLECTOR.characteristics().contains(
                Collector.Characteristics.CONCURRENT)) {
            throw new AssertionError("mutable Stats is not concurrent");
        }
        if (COLLECTOR.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH)) {
            throw new AssertionError("finisher is not identity");
        }

        StatsResult sequential = values.stream().collect(COLLECTOR);
        StatsResult parallel = values.parallelStream().collect(COLLECTOR);
        assertEquivalent(
            sequential, parallel, "sequential vs parallel");

        List<Integer> reversed = Arrays.asList(
            Integer.MAX_VALUE, Integer.MIN_VALUE,
            -9, 3, 0, 10, 10, -4);
        StatsResult reversedResult = reversed.stream().collect(COLLECTOR);
        assertEquivalent(
            sequential, reversedResult, "unordered permutation");

        System.out.println("fresh supplier containers: PASS");
        System.out.println("identity checks: " + checks[0]);
        System.out.println(
            "associativity partitions checked: " + checks[1]);
        System.out.println("sequential result: " + sequential);
        System.out.println("parallel result: " + parallel);
        System.out.println(
            "collector characteristics: " + COLLECTOR.characteristics());
        System.out.println("unordered permutation: PASS");
        System.out.println("law checks: PASS");
    }
}
```

Biên dịch và chạy bằng JDK mới có hỗ trợ `--release`:

```bash
javac --release 8 -encoding UTF-8 CollectorLawDemo.java
java CollectorLawDemo
```

Nếu chạy trực tiếp bằng JDK 8, bỏ cờ `--release 8`:

```bash
javac -encoding UTF-8 CollectorLawDemo.java
java CollectorLawDemo
```

**Stdout chính xác:**

```text
fresh supplier containers: PASS
identity checks: 24
associativity partitions checked: 49
sequential result: count=8, sum=9, min=-2147483648, max=2147483647, average=1.125
parallel result: count=8, sum=9, min=-2147483648, max=2147483647, average=1.125
collector characteristics: [UNORDERED]
unordered permutation: PASS
law checks: PASS
```

## 11. Đọc kết quả kiểm thử

### 11.1. Vì sao có 24 identity checks?

Chương trình thử ba bộ input:

- Danh sách rỗng: 1 prefix.
- Danh sách một phần tử: 2 prefix.
- Danh sách tám phần tử: 9 prefix.

Mỗi prefix kiểm tra right identity và left identity. Tổng số kiểm tra:

```text
2 × (1 + 2 + 9) = 24
```

Right identity là luật được Collector contract nêu rõ; left identity được thêm để xác minh phép ghép của collector ví dụ có identity hai phía.

### 11.2. Vì sao có 49 associativity partitions?

Với mỗi danh sách có `n` phần tử, chương trình thử mọi cặp điểm chia `0 <= i <= j <= n`. Số bộ partition là `(n + 1)(n + 2) / 2`:

- Danh sách rỗng: 1 partition.
- Danh sách một phần tử: 3 partition.
- Danh sách tám phần tử: 45 partition.

Tổng là `1 + 3 + 45 = 49`. Mỗi partition được kiểm tra với cả left-associated và right-associated grouping, rồi so sánh với kết quả sequential baseline.

### 11.3. Vì sao dùng giá trị min/max biên?

Input có `Integer.MIN_VALUE` và `Integer.MAX_VALUE`. Điều này kiểm tra collector không khởi tạo min/max bằng giá trị giả định nằm ngoài miền số nguyên. Sum được giữ trong long nên tổng của bộ input này vẫn chính xác.

### 11.4. Vì sao sequential và parallel cho cùng kết quả?

Stats là aggregate không phụ thuộc thứ tự, và combiner tuân theo luật identity/associativity trên bộ dữ liệu này. Parallel stream có thể chia container, tích lũy riêng rồi ghép mà không đổi kết quả.

Test này là bằng chứng hữu ích, nhưng không thay thế luật trực tiếp và test trên miền dữ liệu rộng hơn.

## 12. Kiểm thử partition rỗng và input biên

Partition rỗng thường xuất hiện khi một nhánh của cây reduction không có phần tử. Vì vậy identity test nên luôn có:

- Input rỗng.
- Prefix rỗng.
- Middle partition rỗng.
- Suffix rỗng.
- Một phần tử.
- Nhiều phần tử có giá trị trùng nhau.
- Giá trị biên của kiểu dữ liệu.

Ví dụ các split:

```text
[] | [1, 2, 3]
[1] | [] | [2, 3]
[1, 2] | [3] | []
[] | [] | []
```

Một combiner có thể xử lý đúng khi cả hai phía có dữ liệu nhưng lỗi khi một phía rỗng. Những test này làm lỗi đó xuất hiện có chủ đích.

Với collector nhóm dữ liệu, kiểm tra partition không có key, key chỉ xuất hiện ở một partition và key xuất hiện ở cả hai partition. Với collector đếm, kiểm tra count 0 và count lớn. Với collector tạo map, kiểm tra key collision và merge function.

## 13. Kiểm thử collector ordered

Nếu collector cần giữ encounter order, hãy test các partition theo thứ tự:

```java
List<String> first = Arrays.asList("A", "B");
List<String> second = Arrays.asList("C", "D");

List<String> combined = new ArrayList<>(first);
combined.addAll(second);
```

Kết quả `A, B, C, D` đúng khi left là đoạn input trước right. Nếu đảo thứ tự ghép, kết quả thay đổi.

Không đổi vị trí hai operand rồi bắt buộc kết quả giống nhau nếu collector ordered. Associativity không cho phép hoán đổi thứ tự operand.

Nếu collector được đánh dấu `UNORDERED`, hãy thử permutation đầu vào và xác nhận kết quả tương đương. Nếu không đánh dấu `UNORDERED`, không được bỏ qua thứ tự khi so sánh.

## 14. Kiểm thử floating-point và phép toán không chính xác tuyệt đối

Cộng `double` trong Java không associative theo bit pattern do làm tròn floating-point:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);
System.out.println(right);
```

Hai cách đặt ngoặc có thể tạo kết quả khác nhau. Vì vậy collector sum double có thể có kết quả parallel khác tuần tự ở bit cuối, dù mỗi phép cộng tuân theo IEEE 754.

Khi test collector số thực:

- Chọn equivalence theo tolerance được nghiệp vụ chấp nhận.
- Xác định cách xử lý NaN, infinity và signed zero.
- Nếu cần kết quả deterministic chính xác, xem xét kiểu decimal hoặc thuật toán cộng bù phù hợp.
- Không dùng exact equality như một phép kiểm tra chung nếu contract chấp nhận sai số.
- Đừng đánh dấu `UNORDERED` nếu việc đổi thứ tự làm thay đổi kết quả vượt tolerance.

Với tiền tệ, không dùng `double` làm phép thử luật cộng tiền chính xác. Chọn `BigDecimal` với scale và rounding policy rõ ràng.

## 15. Kiểm thử CONCURRENT collector

Một collector có `CONCURRENT` cho phép accumulator được gọi đồng thời trên cùng một container. Đây là hợp đồng mạnh hơn collector mutable thông thường.

Trước khi khai báo:

- Xác định accumulator thread-safe bằng cơ chế phù hợp.
- Kiểm tra mọi field mutable, nested collection và counter.
- Xác định có cần `UNORDERED` hay không.
- Kiểm tra cách stream runtime có thể sử dụng concurrent reduction.
- Test nhiều thread cùng tích lũy trên một container chia sẻ.
- Kiểm tra memory visibility và tính nguyên tử của thao tác cập nhật.

Không thể kết luận concurrent-safe chỉ vì gọi `parallelStream()` không báo exception. Runtime có thể tạo nhiều container riêng và dùng combiner thay vì chia sẻ một container cho nhiều thread.

Nếu collector dùng `LongAdder` hoặc concurrent map, kiểm tra kết quả sau khi tất cả worker hoàn tất và xác minh không mất update. Không khai báo `CONCURRENT` cho `ArrayList` hoặc `HashMap` mutable thông thường chỉ để tăng tốc.

## 16. Kiểm thử IDENTITY_FINISH

Khi khai báo `IDENTITY_FINISH`, finisher được xem là identity. Ví dụ collector trả chính accumulator:

```java
Collector<String, List<String>, List<String>> collector =
    Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.IDENTITY_FINISH);
```

Với collector này, `A` và `R` đều là `List<String>`. Không có bước chuyển đổi sang result type khác.

Nếu muốn trả một immutable copy:

```java
list -> Collections.unmodifiableList(new ArrayList<>(list))
```

thì finisher không còn identity; không được khai báo `IDENTITY_FINISH`. Hãy test result thực sự immutable nếu API cam kết điều đó, và test rằng accumulator nội bộ không bị lộ ngoài ý muốn.

## 17. Property-based testing cho custom Collector

Kiểm tra mọi split của một vài fixture là bước đầu tốt. Với collector phức tạp, có thể sinh nhiều input để tìm tổ hợp mà test viết tay bỏ sót.

Một property test có thể tạo:

- Danh sách có độ dài ngẫu nhiên, bao gồm rỗng.
- Giá trị âm/dương, trùng lặp và biên.
- Các điểm chia ngẫu nhiên hoặc toàn bộ điểm chia với danh sách ngắn.
- Các cây kết hợp ngẫu nhiên của accumulator.
- Các permutation nếu collector khai báo unordered.

Pseudocode:

```java
for (List<T> input : generatedInputs) {
    R sequential = input.stream().collect(collector);

    for (Partition<T> partition : partitions(input)) {
        A left = accumulate(partition.left());
        A right = accumulate(partition.right());

        R combined = finish(collector.combiner().apply(left, right));
        assertEquivalent(sequential, combined);
    }
}
```

Đây là pseudocode, cần định nghĩa `Partition`, `accumulate`, `finish` và `assertEquivalent` theo collector cụ thể. Có thể tích hợp với property-testing framework hiện hành mà project đã dùng; không cần đưa dependency vào code production chỉ để chạy law test.

Dùng seed cố định khi tái hiện lỗi trong CI. Khi phát hiện input làm vi phạm luật, giữ input đó thành regression test rõ ràng.

## 18. Tích hợp kiểm thử với JUnit

Có thể tách law checks thành các test method:

```java
@Test
public void supplierCreatesIndependentContainers() {
    Stats first = collector.supplier().get();
    Stats second = collector.supplier().get();

    assertNotSame(first, second);
}

@Test
public void combinerHasRightIdentity() {
    Stats state = accumulate(Arrays.asList(1, 2, 3));
    StatsResult expected = finish(state);

    Stats combined = collector.combiner().apply(
        state, collector.supplier().get());

    assertEquals(expected, finish(combined));
}

@Test
public void sequentialAndParallelResultsAreEquivalent() {
    StatsResult sequential = values.stream().collect(collector);
    StatsResult parallel = values.parallelStream().collect(collector);

    assertEquals(sequential, parallel);
}
```

Đây là snippet JUnit; cần import assertion/test APIs và khai báo fixture/helper tương ứng. Nên có test riêng cho associativity với nhiều partition, không chỉ một test parallel.

Tổ chức test theo contract giúp khi một law fail, thông báo chỉ ra rõ supplier, identity, associativity, ordering, finisher hay concurrency là nguồn lỗi.

## 19. Những lỗi thường gặp khi viết combiner

1. **Combiner không xử lý accumulator rỗng.** Identity test sẽ phát hiện khi một phía không có dữ liệu.
2. **Supplier trả về cùng mutable instance.** Các partition có thể ghi đè trạng thái nhau.
3. **Combiner chỉ đúng khi luôn ghép trái trước.** Kiểm tra parenthesization và operand ordering đúng contract.
4. **Nhầm associative với commutative.** Ordered collector có thể associative nhưng không commutative.
5. **Đánh dấu UNORDERED quá sớm.** Kết quả có thể thay đổi khi input permutation.
6. **Đánh dấu CONCURRENT cho container không thread-safe.** Có thể mất update hoặc race.
7. **Đánh dấu IDENTITY_FINISH khi finisher chuyển kiểu.** Runtime có thể bỏ qua bước chuyển đổi.
8. **So sánh accumulator sau khi combiner mutate.** Chụp expected result trước khi combine.
9. **Dùng lại accumulator đã consume trong nhiều nhánh test.** Tạo state mới cho mỗi parenthesization.
10. **Chỉ test một input không rỗng.** Bỏ sót empty/singleton/partition empty.
11. **Chỉ test parallelStream một lần.** Không bao phủ mọi cách phân hoạch.
12. **Dùng equals không đúng domain.** Chọn equivalence relation phù hợp kết quả.
13. **Dùng exact equality cho floating-point.** Chọn tolerance hoặc arithmetic strategy.
14. **Bỏ qua overflow.** Kiểm tra giới hạn kiểu số và chính sách overflow.
15. **Finisher có side effect.** Kết quả có thể phụ thuộc số lần hoặc thời điểm gọi.
16. **Accumulator giữ reference ngoài không kiểm soát.** Partition khác hoặc caller có thể làm thay đổi trạng thái đang gom.
17. **Combiner mutate cả hai input rồi caller còn tái sử dụng.** Xác định ownership và không tái sử dụng accumulator đã ghép.
18. **Giả định parallel stream luôn dùng concurrent reduction.** Runtime còn phụ thuộc characteristic và ordered/unordered stream.
19. **Không test permutation cho unordered collector.** Có thể đã khai báo sai characteristic.
20. **Chỉ test dữ liệu nhỏ, không có duplicate/extreme values.** Bổ sung biên và property-generated inputs.

## 20. Quy trình review một custom Collector

1. Đọc rõ ý nghĩa domain của kết quả cuối `R`.
2. Xác định accumulator `A` và invariant của trạng thái rỗng.
3. Kiểm tra supplier luôn tạo container mới, độc lập.
4. Kiểm tra accumulator thêm một phần tử mà không phá invariant.
5. Kiểm tra combiner xử lý empty-left và empty-right.
6. Kiểm tra identity và associativity qua finisher/equivalence.
7. Kiểm tra encounter order hoặc unordered semantics.
8. Chỉ khai báo characteristics có bằng chứng.
9. Kiểm tra finisher và khả năng lộ mutable state.
10. Chạy sequential, parallel, empty, singleton, partitioned và permutation tests.
11. Kiểm tra concurrency riêng nếu có `CONCURRENT`.
12. Kiểm tra overflow, floating-point, null policy và domain edge cases.
13. Giữ regression tests cho mọi law violation từng được phát hiện.

## 21. Câu hỏi ôn luyện và đáp án

**1. Collector có những thành phần nào?**  
Supplier, accumulator, combiner, finisher và characteristics.

**2. Luật identity yêu cầu điều gì?**  
`combiner.apply(a, supplier.get())` phải tương đương accumulator `a` ban đầu.

**3. Vì sao cần gọi supplier để tạo empty state mới?**  
Để không chia sẻ mutable accumulator giữa các lần kiểm thử hoặc partition.

**4. Luật associativity yêu cầu điều gì?**  
Các cách đặt ngoặc khác nhau khi ghép các phần tích lũy phải cho kết quả tương đương.

**5. Associativity có đồng nghĩa commutativity không?**  
Không. Ghép chuỗi có thể associative nhưng không commutative.

**6. Vì sao so sánh qua finisher?**  
Vì accumulator nội bộ có thể khác object/state nhưng vẫn biểu diễn cùng kết quả nghiệp vụ.

**7. CONCURRENT có bắt buộc để parallel stream hoạt động không?**  
Không. Collector thường có thể dùng parallel với các container riêng và combiner.

**8. Khi nào đánh dấu UNORDERED?**  
Khi kết quả không cam kết encounter order và thực sự không phụ thuộc thứ tự input.

**9. Khi nào đánh dấu IDENTITY_FINISH?**  
Khi finisher là identity và accumulator type có thể dùng trực tiếp làm result type.

**10. Vì sao một lần parallel test chưa đủ?**  
Runtime có thể chọn một cách phân hoạch duy nhất; cần kiểm tra nhiều split và parenthesization.

**11. Combiner có được mutate accumulator bên trái không?**  
Có, đây là pattern phổ biến; test cần chụp expected trước mutation và không tái sử dụng state đã consume.

**12. Có cần kiểm tra partition rỗng không?**  
Có. Identity law đặc biệt quan trọng khi partition không có phần tử.

**13. Với collector ordered, có được đổi vị trí hai operand không?**  
Không mặc định. Associativity không cho phép đổi thứ tự operand.

**14. Vì sao double sum có thể khác khi parallel?**  
Floating-point addition không associative tuyệt đối do làm tròn.

**15. Có nên dùng Double.equals để so sánh mọi phép cộng double?**  
Không. Chọn tolerance hoặc phép toán phù hợp với yêu cầu độ chính xác.

**16. Làm sao kiểm tra supplier độc lập?**  
Gọi supplier hai lần và xác nhận hai mutable containers không phải cùng một object.

**17. Có thể test combiner bằng input rỗng, singleton và nhiều phần tử không?**  
Nên làm. Đây là những trường hợp giúp lộ lỗi identity/partition boundary.

**18. UNORDERED có nghĩa combiner phải giao hoán không?**  
Collector phải không phụ thuộc encounter order; thiết kế phép ghép phải phù hợp semantics đó. Không suy luận characteristic chỉ từ tên.

**19. Test law có thay thế integration test parallel không?**  
Không. Nên có cả law tests trực tiếp lẫn kiểm tra kết quả qua stream tuần tự/song song.

**20. Cách tổ chức law test dễ chẩn đoán nhất?**  
Tách test supplier, identity, associativity, finisher, characteristics, ordering và concurrency thành các nhóm riêng.

## 22. Tài liệu API chính thức

- [Collector — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html): contract, identity constraint, associativity constraint, characteristics và Collector.of.
- [Collector — Java 8](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.html): API và hợp đồng collector có từ Java 8.
- [Stream.collect — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector)): cách stream thực hiện mutable reduction.
- [Collectors — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): các collector chuẩn và ví dụ về reduction.
- [Java Language Specification — Evaluation Order](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html): thứ tự đánh giá biểu thức và lời gọi method.
- [Java Tutorials — Reduction](https://docs.oracle.com/javase/tutorial/collections/streams/reduction.html): khái niệm reduction và cách dùng collect.

Các API được dùng trong chương trình mẫu thuộc Java 8. Không cần API deprecated hoặc collector implementation nội bộ của JDK để viết và kiểm thử custom collector.

**Nguyên tắc cuối:** kiểm thử collector bằng luật identity và associativity trực tiếp trên partition độc lập, so sánh kết quả sau finisher theo equivalence của domain, rồi mới đối chiếu stream tuần tự/song song. Chỉ khai báo CONCURRENT, UNORDERED và IDENTITY_FINISH khi implementation thực sự đáp ứng từng hợp đồng.
