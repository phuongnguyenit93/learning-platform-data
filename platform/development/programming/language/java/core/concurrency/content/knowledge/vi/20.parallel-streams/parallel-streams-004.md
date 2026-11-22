# Associativity của phép reduce và tính đúng đắn trong Parallel Streams

> Nội dung về Java Stream API (Java 17+) và các quy tắc để phép rút gọn giữ nguyên ý nghĩa khi JVM chia việc song song. Phạm vi là Java concurrency thuần, không phụ thuộc framework.

## 1. Vì sao song song đòi hỏi phép gộp có tính kết hợp?

`reduce` là phép **rút gọn** (reduction): đi qua các phần tử và tổng hợp thành một giá trị, chẳng hạn tổng số, giá trị lớn nhất, một chuỗi, hay một thống kê. Ví dụ:

```java
int result = java.util.stream.Stream.of(1, 2, 3, 4)
        .reduce(0, Integer::sum); // 10
```

Với stream tuần tự, có thể hình dung cách tính:

```text
(((0 + 1) + 2) + 3) + 4 = 10
```

Với `parallel()`, dữ liệu được phân chia thành các nhóm, mỗi nhóm tạo **subtotal**, rồi một **combiner** gộp các subtotal. Chẳng hạn:

```text
                  [1, 2, 3, 4]
                     /    \
                 [1, 2]  [3, 4]
                   |        |
                 (1+2)    (3+4)
                   \        /
                     3 + 7
                       |
                      10
```

Stream API **không hứa** một cây phân hoạch cố định hay một lịch chạy giống nhau qua mọi lần thực thi. Để nhiều cây hợp lệ đều tạo ra cùng một kết quả, phép gộp phải có **associativity** (tính kết hợp).

Một toán tử `⊕` có tính kết hợp nếu:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

Đây là khả năng **thay đổi cách đặt dấu ngoặc**. Nó khác **commutativity** (tính giao hoán), tức khả năng **đổi thứ tự các toán hạng**:

```text
Associativity: (a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
Commutativity: a ⊕ b = b ⊕ a
```

Ví dụ nối chuỗi có tính kết hợp:

```text
("a" + "b") + "c" = "abc"
"a" + ("b" + "c") = "abc"
```

Nhưng nối chuỗi **không giao hoán** vì `"ab" != "ba"`. Với **ordered stream** (như `List.stream()`), một phép reduce nối chuỗi hợp lệ có thể chạy song song mà vẫn bảo toàn **encounter order**. Đừng lẫn thứ tự worker hoàn tất với thứ tự phần tử trong kết quả. Ngược lại, gọi `unordered()` nghĩa là bạn không còn yêu cầu giữ encounter order.

## 2. Phép trừ phá vỡ tính kết hợp

```text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
```

Hai biểu thức khác kết quả; phép trừ không associative. Vì vậy đoạn sau **vi phạm hợp đồng reduce song song**:

```java
int invalid = java.util.stream.Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, (a, b) -> a - b);
```

Cùng dữ liệu nhưng có thể hình dung hai cách gộp:

```text
Tuần tự: (((0 - 1) - 2) - 3) - 4 = -10

Phân hoạch: [1, 2] và [3, 4]
    phần trái  = (0 - 1) - 2 = -3
    phần phải  = (0 - 3) - 4 = -7
    phép gộp   = -3 - (-7)  = 4
```

**Không** khẳng định mọi lần chạy Java đều cho `4` hoặc `-10`: kết quả phân hoạch không phải hợp đồng công khai. Hai phép tính trên là bằng chứng độc lập rằng cách đặt ngoặc có thể đổi nghĩa.

Hãy viết đúng phép toán nghiệp vụ: nếu mục tiêu là `start - sum(items)`, ta có thể tính `sum = items.parallelStream().reduce(0, Integer::sum)`, sau đó `start - sum` đúng **một lần**, thay vì dùng phép trừ như accumulator.

## 3. Ba overload của Stream.reduce

### 3.1. `Optional<T> reduce(BinaryOperator<T> accumulator)`

Không có giá trị `identity` tường minh. Nếu stream rỗng sẽ nhận `Optional.empty()`; nếu không rỗng, accumulator gộp các phần tử và bắt buộc **associative, stateless, non-interfering**:

```java
java.util.Optional<Integer> largest =
        java.util.stream.Stream.of(4, 8, 3)
                .parallel()
                .reduce(Integer::max); // Optional[8]
```

`Integer::max` associative. Tránh gọi `get()` ngay khi nguồn có thể rỗng; sử dụng `orElse` hoặc `orElseThrow` tùy nghiệp vụ.

### 3.2. `T reduce(T identity, BinaryOperator<T> accumulator)`

```java
int sum = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum); // 6
```

Cần:

1. **Identity trung hòa**: với mọi `t`, `accumulator(identity, t) == t` theo semantics giá trị cần giữ. Trong thiết kế reduction, thường yêu cầu cả `op(t, identity) = t` cho mọi giá trị subtotal có thể xuất hiện.
2. **Associativity**: `op(op(a,b),c) = op(a,op(b,c))`.
3. **Stateless/non-interfering**: không phụ thuộc vào biến chia sẻ đang thay đổi và không sửa nguồn stream khi stream đang chạy.

Bảng identity thường gặp:

| Phép gộp | Identity | Lý do |
|---|---|---|
| Cộng số nguyên | `0` | `0 + x = x` |
| Nhân số nguyên | `1` | `1 * x = x` |
| Nối chuỗi | `""` | `"" + s = s` |
| Boolean AND | `true` | `true && b = b` |
| Boolean OR | `false` | `false || b = b` |
| `max` cho mọi `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| `min` cho mọi `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

**Bẫy: seed khác identity.** Ví dụ sai:

```java
int broken = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum); // SAI: 10 không là identity của phép cộng
```

Tuần tự: `10 + 1 + 2 + 3 = 16`. Nếu ba phần độc lập dùng `10` mỗi phần, khi gộp có thể được `(10+1) + (10+2) + (10+3) = 36`. Con số `36` là một khả năng minh họa, **không phải stdout được JVM bảo đảm**. Nếu muốn cộng hằng số `10` đúng một lần:

```java
int correct = 10 + java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum); // 16
```

Một identity phù hợp với miền dữ liệu rất quan trọng: `0` không là identity cho `max` nếu có số âm. Nếu stream có thể rỗng và “không có max” khác với giá trị nhỏ nhất, dùng `Optional` là cách biểu đạt thích hợp hơn.

### 3.3. `<U> U reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)`

Dùng overload ba tham số khi kiểu phần tử `T` và kết quả `U` khác nhau. Ví dụ tổng độ dài của các chuỗi:

```java
int totalLength = java.util.stream.Stream.of("a", "bb", "ccc")
        .parallel()
        .reduce(
                0,
                (current, word) -> current + word.length(),
                Integer::sum
        ); // 6
```

- **Identity**: kết quả tạm trung hòa `0`.
- **Accumulator**: `a(u,t) = u + length(t)`, cập nhật subtotal bởi một phần tử đầu vào.
- **Combiner**: `c(u,v) = u + v`, gộp hai subtotal có cùng kiểu `U`.

Ngoài identity và associativity của combiner, API đòi **compatibility** giữa accumulator và combiner:

```text
c(identity, u) = u
c(c(x, y), z) = c(x, c(y, z))
c(u, a(identity, t)) = a(u, t)
```

Phương trình cuối nói rằng “tích lũy phần tử `t` vào subtotal `u`” phải tương đương “tích lũy `t` trong một nhánh riêng rồi gộp vào `u`”. **Chỉ kiểm tra combiner associative là chưa đủ.**

Ví dụ sai:

```java
// SAI: accumulator cộng nhưng combiner lại trừ.
int broken = java.util.stream.Stream.of("a", "bb", "ccc")
        .parallel()
        .reduce(0,
                (sum, word) -> sum + word.length(),
                (left, right) -> left - right);
```

Với pipeline tuần tự, combiner có thể không được gọi nên lỗi này khó lộ ra trong bài test đơn luồng. Cách sửa là `Integer::sum`, hoặc thiết kế lại cả accumulator/combiner theo cùng một phép toán có tính kết hợp.

## 4. Một ví dụ Java 17+ chạy độc lập

Tạo tệp **`ReduceAssociativityDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class ReduceAssociativityDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4);

        int sum = numbers.parallelStream().reduce(0, Integer::sum);
        String letters = List.of("a", "b", "c", "d")
                .parallelStream().reduce("", String::concat);
        int lengths = List.of("a", "bb", "ccc")
                .parallelStream()
                .reduce(0, (n, s) -> n + s.length(), Integer::sum);

        Optional<Integer> empty = List.<Integer>of()
                .parallelStream().reduce(Integer::sum);

        // Minh họa hai cây gộp mà không bắt JVM chọn cây cụ thể.
        int sequentialSubtraction = numbers.stream()
                .reduce(0, (a, b) -> a - b);
        int left = (0 - 1) - 2;
        int right = (0 - 3) - 4;
        int groupedSubtraction = left - right;

        System.out.println("sum=" + sum);
        System.out.println("letters=" + letters);
        System.out.println("lengths=" + lengths);
        System.out.println("empty=" + empty);
        System.out.println("sequentialSubtraction=" + sequentialSubtraction);
        System.out.println("groupedSubtraction=" + groupedSubtraction);
    }
}
```

Biên dịch và chạy:

```bash
javac ReduceAssociativityDemo.java
java ReduceAssociativityDemo
```

Stdout chính xác:

```text
sum=10
letters=abcd
lengths=6
empty=Optional.empty
sequentialSubtraction=-10
groupedSubtraction=4
```

Kết quả ba phép reduce hợp lệ không phụ thuộc cây gộp. Hai dòng subtraction chứng minh sự khác nhau **bằng phép tính tường minh**; chương trình không hề kỳ vọng một kết quả cố định từ phép trừ chạy parallel.

## 5. Associativity khác tính giao hoán và tính an toàn luồng

Một phép nối chuỗi như `String::concat` là associative nhưng **không commutative**. Khi còn encounter order, `List.of("a","b","c").parallelStream().reduce("", String::concat)` phải có ý nghĩa `"abc"` dù worker chạy theo lịch bất kỳ. Nếu bỏ ràng buộc order bằng `unordered()`, một kết quả chỉ đúng khi giữ thứ tự ban đầu không còn được bảo đảm.

Đồng thời, **thread-safe** không có nghĩa là **associative**. Một lambda viết vào `AtomicInteger` chung có thể không có data race trên chính biến đếm, nhưng logic phụ thuộc lịch chạy, số lần gọi accumulator và trạng thái ngoài pipeline, nên không đáp ứng yêu cầu hàm stateless. `reduce` phải tính kết quả từ input/partial results, không dùng side effect ngoài để “thu gom” dữ liệu.

Bốn câu hỏi riêng biệt khi review:

| Thuộc tính | Điều phải đúng |
|---|---|
| Associativity | Đổi dấu ngoặc của gộp subtotal vẫn đúng |
| Commutativity | Chỉ cần nếu bạn thật sự cho phép đổi vị trí phần tử |
| Identity / compatibility | Các nhánh độc lập, nhánh rỗng và việc nhập subtotal cho cùng kết quả |
| Stateless / non-interfering | Hàm không phụ thuộc mutable state chia sẻ và không sửa nguồn |

Đối với stream được khai báo unordered hoặc collector có đặc tính đặc biệt, phải đọc hợp đồng của operation cụ thể thay vì áp một quy tắc đơn giản về order cho mọi trường hợp.

## 6. Số thực và overflow: phép toán toán học chưa chắc đúng theo biểu diễn Java

Trong số học thực, phép cộng kết hợp. Với `double` theo IEEE 754, mỗi phép cộng có thể làm tròn, vì vậy cây gộp ảnh hưởng kết quả.

Tạo tệp **`FloatingPointGrouping.java`**:

```java
public class FloatingPointGrouping {
    public static void main(String[] args) {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        System.out.println("left=" + ((a + b) + c));
        System.out.println("right=" + (a + (b + c)));
    }
}
```

Chạy:

```bash
javac FloatingPointGrouping.java
java FloatingPointGrouping
```

Stdout chính xác:

```text
left=1.0
right=0.0
```

`b + c` làm mất phần `1.0` do sai số làm tròn gần `-1.0e16`. Vì vậy `reduce(0.0, Double::sum)` không thỏa tính kết hợp **chính xác từng bit**. `DoubleStream.sum()` có thể dùng thuật toán nâng độ chính xác hơn phép reduce thủ công, nhưng kết quả vẫn có thể phụ thuộc thứ tự cộng/sự làm tròn; ứng dụng cần định nghĩa tolerance hoặc phép toán chính xác hơn nếu muốn deterministic về giá trị.

Với tiền tệ, cân nhắc biểu diễn integer minor units (ví dụ cent) hoặc `BigDecimal` cộng chính xác, chú ý scale và tràn số. `BigDecimal.add` không truyền `MathContext` có phép cộng chính xác theo giá trị; nếu làm tròn từng bước bằng `MathContext`, associativity có thể không còn. `BigDecimal.equals` còn phân biệt scale; nếu cần so giá trị số hãy cân nhắc `compareTo` theo thiết kế.

Với `int` và `long`, phép cộng có tràn số theo số học modulo; phép cộng đó vẫn associative **trên các bit của kiểu nguyên Java** nhưng có thể sai với tổng toán học ứng dụng. `Math.addExact` có thể ném `ArithmeticException` ở một cây gộp có tổng trung gian vượt miền dù cây khác chưa vượt, nên không tự bảo đảm reduction được phép tái nhóm vô điều kiện.

## 7. Không dùng mutable container làm identity của reduce

Lỗi nguy hiểm:

```java
// Đoạn minh họa SAI, giả sử words là List<String>.
List<String> result = words.parallelStream()
    .reduce(new ArrayList<>(),
            (list, word) -> { list.add(word); return list; },
            (left, right) -> { left.addAll(right); return left; });
```

Đoạn này cần import `java.util.List` và `java.util.ArrayList` nếu đưa vào lớp Java. Vì cùng một object `new ArrayList<>()` được đưa làm identity, các nhánh có thể sửa **chung object**; combiner thậm chí có thể nhập một list vào chính nó. Đây là vi phạm hợp đồng giá trị và có thể có data race, nhân đôi phần tử hoặc lỗi runtime.

Với mutable aggregation, dùng **`collect`**:

```java
// Đoạn minh họa đúng khi words là List<String>.
List<String> result = words.parallelStream()
        .collect(java.util.stream.Collectors.toList());
```

Hoặc:

```java
List<String> result = words.parallelStream()
        .collect(java.util.ArrayList::new,
                 java.util.List::add,
                 java.util.List::addAll);
```

`collect` có supplier tạo **container riêng cho từng phần tích lũy**, accumulator đưa từng phần tử vào container, combiner gộp các container; cả hai đoạn trên là fragment cần biến `words` và import `java.util.List` trong chương trình xung quanh. Với ordered stream và collector tương thích, encounter order được duy trì. Loại cụ thể/tính mutable của list trả từ `Collectors.toList()` không được API cam kết; tránh phụ thuộc triển khai.

Nếu cần kết quả bất biến hay phép gộp tính ra **giá trị mới** mỗi lần, `reduce` là lựa chọn tự nhiên. Nếu cần xây danh sách/map/set bằng thay đổi container, thường dùng `collect`.

## 8. Kiểm tra các luật trước khi benchmark parallel

Đừng chỉ so kết quả sequential/parallel trên một bộ input: vi phạm hợp đồng có thể tình cờ không xuất hiện nếu runtime chia ít nhánh hoặc lịch chạy giống nhau.

Có thể kiểm tra các luật trên miền dữ liệu đại diện:

```text
identity:
    op(identity, x) == x
    op(x, identity) == x

associativity:
    op(op(a,b),c) == op(a,op(b,c))

3-argument reduce:
    combine(identity, u) == u
    combine(combine(x,y),z) == combine(x,combine(y,z))
    combine(u, accumulate(identity,t)) == accumulate(u,t)

state:
    cùng input => cùng kết quả; không đọc/ghi shared mutable state
```

Ví dụ test đơn giản bằng **Java 17+**. Tạo tệp **`ReduceLawsCheck.java`**:

```java
import java.util.function.BinaryOperator;

public class ReduceLawsCheck {
    static void test(BinaryOperator<Integer> op, int identity) {
        int[] values = {-3, -1, 0, 1, 2, 7};

        for (int x : values) {
            if (op.apply(identity, x) != x || op.apply(x, identity) != x) {
                throw new AssertionError("identity failed: " + x);
            }
        }
        for (int a : values) {
            for (int b : values) {
                for (int c : values) {
                    int left = op.apply(op.apply(a, b), c);
                    int right = op.apply(a, op.apply(b, c));
                    if (left != right) {
                        throw new AssertionError(
                                "associativity failed: " + a + "," + b + "," + c);
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        test(Integer::sum, 0);
        test(Integer::max, Integer.MIN_VALUE);
        System.out.println("reduction laws: PASS");
    }
}
```

Chạy:

```bash
javac ReduceLawsCheck.java
java ReduceLawsCheck
```

Stdout chính xác:

```text
reduction laws: PASS
```

Đây chỉ là **test tập mẫu**, không phải chứng minh cho mọi input và mọi operator. Bổ sung property-based testing, dữ liệu rỗng, số âm, cực trị, duplicate, overflow và các giá trị có scale/precision khác nhau. Với overload ba tham số, test **compatibility** trên các subtotal có thể tạo thực tế. Chọn phép so sánh kết quả đúng theo nghiệp vụ: `equals` cho object có contract phù hợp, tolerance có chủ đích cho số thực, hoặc so sánh theo giá trị thập phân.

### Checklist QA khi gặp `parallelStream().reduce(...)`

1. Xác định giá trị/ý nghĩa cần tính và stream có encounter order không.
2. Kiểm tra identity (bao gồm stream rỗng và subtotal của từng phần).
3. Chứng minh tính kết hợp của accumulator hoặc combiner theo **semantics của kiểu Java**, không chỉ ký hiệu trên giấy.
4. Với overload ba tham số, kiểm tra luật tương thích giữa accumulator/combiner.
5. Bảo đảm lambda stateless, non-interfering, không mutate một identity chung.
6. Xem chính sách overflow, floating-point error, order và equality.
7. Test sequential/parallel với nhiều kích thước và dữ liệu, rồi mới benchmark throughput/latency. `parallel()` không mặc định nhanh hơn vì chi phí split, scheduling và merging.

## 9. Những sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| `reduce(10, Integer::sum)` để thêm hằng số 10 | Hằng số có thể áp dụng ở mỗi nhánh | `10 + reduce(0, Integer::sum)` |
| `reduce(0, (a,b)->a-b)` | Phép trừ không kết hợp | Rút gọn bằng phép phù hợp rồi áp dụng phép trừ một lần |
| Accumulator cộng, combiner trừ | Vi phạm compatibility | Dùng combiner đúng semantics của subtotal |
| Shared mutable `ArrayList` làm identity | Các nhánh có thể cùng mutate object | `collect` với supplier |
| `AtomicInteger` cập nhật bên ngoài | State phụ thuộc lịch chạy, phá tính thuần | Đưa kết quả vào reduction |
| Ghép chuỗi nhưng bỏ encounter order | Kết quả có thể đổi thứ tự chuỗi | Giữ ordered source/operation |
| Đòi sum `double` giống nhau từng bit | Rounding không associative | Chấp nhận tolerance hoặc biểu diễn chính xác |
| Dùng `Integer::sum` và bỏ qua overflow | Đúng modulo nhưng sai tổng nghiệp vụ | Dùng miền số thích hợp hoặc kiểm soát overflow |
| Chỉ test tuần tự | Không thử cây gộp/combiner | Kiểm tra luật và test trên stream parallel |
| Chỉ đo thời gian chạy | Có thể nhanh nhưng sai kết quả | Khóa correctness trước performance |

## Tài liệu chuẩn

- [Oracle Java 21 — Stream API, reduce](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): hợp đồng identity, associative, non-interfering, stateless và compatibility.
- [Oracle Java 21 — java.util.stream package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): giải thích reduction và parallelizable aggregation.
- [Oracle Java 21 — Collector API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html): quy tắc cho mutable reduction.
- [Oracle Java 21 — DoubleStream.sum](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/DoubleStream.html#sum()): độ chính xác số thực và phụ thuộc thứ tự cộng.

**Ghi nhớ:** `parallel()` thay đổi cách chia và gộp dữ liệu. Kết quả `reduce` đáng tin chỉ khi phép gộp **associative**, identity **trung hòa**, overload ba tham số **compatible**, lambda **stateless/non-interfering** và semantics thực tế (thứ tự, overflow, sai số số thực) đáp ứng nghiệp vụ.
