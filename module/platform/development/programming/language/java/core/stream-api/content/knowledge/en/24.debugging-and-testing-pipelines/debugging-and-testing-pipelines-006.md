# Kiểm thử tính kết hợp của reduce và Collector

## 1. Vì sao pipeline chạy tuần tự đúng nhưng song song lại sai?

Trong **JAVA_STREAM_API**, các pipeline `filter`, `map`, `reduce` và `collect` cho phép biểu diễn cách xử lý dữ liệu khai báo. Một pipeline có thể chuyển từ `stream()` sang `parallelStream()` để phân chia công việc giữa nhiều nhánh. Tuy nhiên, nếu hàm tổng hợp không tuân thủ **tính kết hợp** (*associativity*) và các luật về **identity**, kết quả có thể phụ thuộc vào cách chia dữ liệu.

~~~text
Nguồn: [10, 3, 2]
Phép gộp: phép trừ

Cách gộp 1: (10 - 3) - 2 = 5
Cách gộp 2: 10 - (3 - 2) = 9

Cùng dữ liệu, kết quả khác vì phép trừ không kết hợp.
~~~

Phép chia nguồn trong Stream API không được cam kết theo một lịch cố định. Nếu một kết quả chỉ đúng khi accumulator được gọi theo đúng một trật tự thực thi cụ thể, thuật toán có thể sai khi đổi số phần tử, JDK, khả năng chia của Spliterator hoặc chế độ song song.

Bài thuộc chương **Gỡ lỗi và kiểm thử pipeline**, giúp người học:

- Kiểm tra luật `identity`, `associativity` và tính tương thích `accumulator–combiner` của `reduce`.
- Kiểm tra các thành phần `supplier`, `accumulator`, `combiner`, `finisher` và `Characteristics` của `Collector`.
- Mô phỏng các cách chia nguồn và cây gộp khác nhau, thay vì chỉ gọi `parallel()` một lần.
- Phát hiện các phản ví dụ liên quan tới phép trừ, phép lấy trung bình sai, state mutable dùng chung, thứ tự kết quả và số thực.
- Viết chương trình kiểm thử bằng Java 17+ không phụ thuộc thư viện ngoài; đồng thời hiểu giới hạn của kiểm thử ngẫu nhiên và của việc so sánh tuần tự–song song.

**Ngữ cảnh:** Các ví dụ tập trung vào Java Stream API, nơi phép tổng hợp thường nằm ở terminal `reduce` hoặc `collect`. Những vấn đề về thứ tự, hiệu năng, trạng thái và Spliterator ảnh hưởng trực tiếp tới việc xác minh một pipeline có thể chạy song song đúng hay không.

## 2. Mô hình chia và gộp nguồn

~~~text
Nguồn [1, 2, 3, 4, 5, 6]
                 │
             Spliterator
             /         \
       [1, 2, 3]     [4, 5, 6]
           │             │
        giảm riêng     giảm riêng
           │             │
           6             15
            \           /
               combiner
                   │
                   21
~~~

Đây chỉ là sơ đồ khái niệm. Stream không cam kết chia đúng thành hai phần hoặc sử dụng một thread trên mỗi phần. Một terminal reduction có thể kết hợp nhiều partial result theo **những cách nhóm khác nhau**.

**Tính kết hợp** cho phép đổi dấu ngoặc nhóm mà không đổi kết quả:

~~~text
op(op(a, b), c) = op(a, op(b, c))
~~~

**Tính giao hoán** cho phép đổi chỗ các giá trị:

~~~text
op(a, b) = op(b, a)
~~~

Hai tính chất khác nhau. Nối chuỗi có tính kết hợp nhưng không giao hoán:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
"A" + "B" != "B" + "A"
~~~

Với nguồn **ordered**, collector/reduction có thể đúng dù toán tử không giao hoán nếu thứ tự encounter order được giữ. Với collector **UNORDERED**, không được dựa vào thứ tự nhập để quyết định bản ghi thắng khi các phần tử trùng khóa.

### An toàn luồng không đủ để chứng minh tính đúng

Một hàm không có data race vẫn có thể **sai về toán học** nếu không kết hợp. Ngược lại, phép cộng kết hợp đúng nhưng được thực hiện trên một biến mutable dùng chung trong callback có thể mất cập nhật. Vì vậy, kiểm thử cần xét **cả luật phép gộp và thiết kế trạng thái**.

## 3. Luật identity và associativity của reduce

Overload hai tham số:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Giá trị `identity` phải là phần tử đơn vị thích hợp; phép `accumulator` phải kết hợp được. Với `e` là identity và `op` là toán tử, các kiểm tra hữu ích:

~~~text
op(e, x) = x
op(x, e) = x

op(op(a, b), c) = op(a, op(b, c))
~~~

Hợp đồng `Stream.reduce` nêu cụ thể `accumulator(identity, t)` phải tương đương `t`. Với phép tổng hợp có phần tử đơn vị hai phía, nên kiểm tra cả `op(t, identity)` để bắt lỗi suy luận về các nhánh rỗng và phép kết hợp.

| Phép tổng hợp | Identity phù hợp | Kết hợp? | Giao hoán? | Lưu ý |
| --- | --- | --- | --- | --- |
| Cộng `long` | `0L` | Có theo ngữ nghĩa Java | Có | Có thể tràn nếu miền nghiệp vụ lớn |
| Nhân `long` | `1L` | Có theo ngữ nghĩa Java | Có | Có thể tràn |
| `Integer::max` | `Integer.MIN_VALUE` | Có | Có | Không dùng 0 cho mọi số nguyên |
| `Integer::min` | `Integer.MAX_VALUE` | Có | Có | Giá trị biên có thể là dữ liệu thật |
| Nối `String` | `""` | Có | Không | Cần giữ encounter order |
| Phép trừ | Không có identity hai phía phù hợp | Không | Không | Không dùng cho parallel reduction |
| `(a + b) / 2` | Không có identity thích hợp | Không | Có | Không dùng làm phép tổng hợp trung bình |
| Cộng `double` | Phức tạp khi xét chính xác bit | Không tuyệt đối | Xét riêng NaN và signed zero | Sai số do cách nhóm phép cộng |

### Identity sai với giá trị âm

~~~java
import java.util.List;

public class WrongIdentity {
    public static void main(String[] args) {
        List<Integer> values = List.of(-10, -5, -20);

        int wrong = values.parallelStream()
            .reduce(0, Integer::max);

        var correct = values.parallelStream()
            .reduce(Integer::max);

        System.out.println(wrong);   // 0: không có trong nguồn
        System.out.println(correct); // Optional[-5]
    }
}
~~~

`0` không là identity của `max` trên miền có số âm vì `max(0, -10) != -10`. Với nguồn có thể rỗng, `reduce(Integer::max)` trả `Optional<Integer>`, giúp phân biệt không có giá trị với một sentinel tự chọn.

## 4. Bài kiểm tra luật bằng Java thuần

Mẫu kiểm thử sau thử nhiều bộ ba số với seed cố định. Nó kiểm tra identity hai chiều và associativity của một `LongBinaryOperator`.

~~~java
import java.util.Random;
import java.util.function.LongBinaryOperator;

public class ReduceLawsTest {

    static void assertLaws(
        long identity,
        LongBinaryOperator operation,
        long seed,
        int trials
    ) {
        Random random = new Random(seed);

        for (int i = 0; i < trials; i++) {
            long a = random.nextInt(2001) - 1000;
            long b = random.nextInt(2001) - 1000;
            long c = random.nextInt(2001) - 1000;

            if (operation.applyAsLong(identity, a) != a
                || operation.applyAsLong(a, identity) != a) {
                throw new AssertionError(
                    "Vi phạm identity với a=" + a
                );
            }

            long left = operation.applyAsLong(
                operation.applyAsLong(a, b), c
            );

            long right = operation.applyAsLong(
                a, operation.applyAsLong(b, c)
            );

            if (left != right) {
                throw new AssertionError(
                    "Vi phạm associativity với a="
                    + a + ", b=" + b + ", c=" + c
                );
            }
        }
    }

    public static void main(String[] args) {
        assertLaws(0L, Long::sum, 2026L, 2000);
        assertLaws(1L, (a, b) -> a * b, 2026L, 2000);

        // Đây là một phép gộp sai, không phải trường hợp PASS:
        // assertLaws(0L, (a, b) -> a - b, 2026L, 2000);

        System.out.println("PASS");
    }
}
~~~

Với kiểu nguyên thủy `long`, phép cộng và nhân của Java có thể tràn theo ngữ nghĩa biểu diễn máy, nhưng vẫn kết hợp được theo phép toán modulo 2^64. Nếu nghiệp vụ cần **kết quả toán học không tràn**, phải chọn miền an toàn, kiểm tra overflow hoặc dùng `BigInteger`.

### Phạm vi của kiểm thử ngẫu nhiên

Test với 2.000 bộ ba **không chứng minh** luật cho mọi phần tử của miền đầu vào. Seed cố định giúp tái hiện lỗi, nhưng cần thêm các trường hợp ranh giới như giá trị âm, 0, ±1, số rất lớn, nguồn rỗng và bộ ba có phần tử trùng. Nếu tìm được phản ví dụ, hãy ghi lại đầu vào và chuyển thành test hồi quy cụ thể.

## 5. Ép các cách chia nguồn khác nhau thay vì chỉ gọi parallel

Một lần `parallelStream()` cho kết quả đúng có thể chỉ phản ánh **một lịch chia may mắn**. Để kiểm tra tính độc lập với phân hoạch, ép mọi vị trí chia trên một danh sách nhỏ, giảm hai phần rồi kết hợp.

~~~java
import java.util.List;

public class SplitReduceTest {

    static void assertAllSplits(List<Long> input) {
        long reference = input.stream()
            .reduce(0L, Long::sum);

        for (int split = 0; split <= input.size(); split++) {
            long left = input.subList(0, split).stream()
                .reduce(0L, Long::sum);

            long right = input.subList(split, input.size()).stream()
                .reduce(0L, Long::sum);

            long combined = Long.sum(left, right);

            if (reference != combined) {
                throw new AssertionError(
                    "Sai kết quả tại split=" + split
                );
            }
        }
    }

    public static void main(String[] args) {
        assertAllSplits(List.of());
        assertAllSplits(List.of(7L));
        assertAllSplits(List.of(7L, -2L, 5L, 8L, -1L));
        System.out.println("PASS");
    }
}
~~~

`split = 0` và `split = size` đặc biệt quan trọng: một nhánh rỗng, nên identity phải biểu diễn chính xác “không có kết quả của nhánh”.

### Thử hai cây gộp ba nhánh

Với ba partial result `a`, `b`, `c`, hãy so sánh:

~~~text
comb(comb(a, b), c)
comb(a, comb(b, c))
~~~

Nếu khác nhau, combiner không kết hợp. **Không tự đổi thứ tự các nhánh** đối với phép tổng hợp nhạy với encounter order như nối chuỗi.

### Smoke test song song

~~~java
import java.util.List;

List<Long> input = List.of(7L, -2L, 5L, 8L, -1L);

long serial = input.stream().reduce(0L, Long::sum);
long parallel = input.parallelStream().reduce(0L, Long::sum);

System.out.println(serial == parallel); // true
~~~

Test song song vẫn hữu ích, nhưng không thay thế test luật và các cách phân hoạch có chủ đích.


## 6. Reduce không có identity: Optional không sửa phép gộp sai

Overload không cung cấp identity:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

trả `Optional.empty()` nếu nguồn rỗng. Nó giúp tránh việc đặt một giá trị mặc định không thuộc miền nghiệp vụ.

~~~java
import java.util.List;
import java.util.Optional;

public class OptionalReduceDemo {
    public static void main(String[] args) {
        Optional<Integer> max = List.of(-10, -5, -20)
            .parallelStream()
            .reduce(Integer::max);

        Optional<Integer> missing = List.<Integer>of()
            .stream()
            .reduce(Integer::max);

        System.out.println(max);     // Optional[-5]
        System.out.println(missing); // Optional.empty
    }
}
~~~

Tuy nhiên, **bỏ identity không loại bỏ yêu cầu associativity**. `reduce((a, b) -> a - b)` vẫn có thể sai trên parallel stream.

Không thiết kế accumulator trả `null` để biểu diễn “chưa có kết quả”; `reduce(BinaryOperator)` có thể ném `NullPointerException` nếu kết quả rút gọn là null. Hãy dùng Optional từ terminal hoặc một kiểu trạng thái được mô hình hóa rõ ràng.

## 7. Reduce ba tham số: kiểm thử compatibility

Overload:

~~~java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
~~~

được dùng khi phần tử đầu vào kiểu `T`, còn kết quả tổng hợp kiểu `U`. `accumulator(U,T)` xử lý **một phần tử nguồn**; `combiner(U,U)` gộp **hai kết quả từng phần**.

Ví dụ tính tổng độ dài các String:

~~~java
import java.util.List;

public class ThreeArgumentReduce {
    public static void main(String[] args) {
        List<String> values = List.of("Java", "Stream", "API");

        int length = values.parallelStream()
            .reduce(
                0,
                (sum, word) -> sum + word.length(),
                Integer::sum
            );

        System.out.println(length); // 13
    }
}
~~~

Ba nhóm luật cần kiểm tra là:

**Identity cho combiner:**

~~~text
comb(identity, u) = u
~~~

**Associativity cho combiner:**

~~~text
comb(comb(u, v), w) = comb(u, comb(v, w))
~~~

**Compatibility giữa accumulator và combiner:**

~~~text
comb(u, acc(identity, t)) = acc(u, t)
~~~

Đây là yêu cầu quan trọng để “giảm phần tử `t` trong nhánh riêng rồi gộp” tương đương “thêm trực tiếp `t` vào partial result `u`”.

### Kiểm tra compatibility bằng một test có thể chạy

~~~java
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;

public class ReduceCompatibilityTest {
    public static void main(String[] args) {
        int identity = 0;

        BiFunction<Integer, String, Integer> accumulate =
            (sum, word) -> sum + word.length();

        BinaryOperator<Integer> combine = Integer::sum;

        for (int partial : List.of(0, 1, 10, 100)) {
            for (String word : List.of("", "A", "Java")) {
                int viaSeparateBranch = combine.apply(
                    partial,
                    accumulate.apply(identity, word)
                );
                int viaDirectAccumulation =
                    accumulate.apply(partial, word);

                if (viaSeparateBranch != viaDirectAccumulation) {
                    throw new AssertionError(
                        "Compatibility sai: " + partial + "/" + word
                    );
                }
            }
        }

        System.out.println("PASS");
    }
}
~~~

Một combiner sai, chẳng hạn phép nhân, có thể khiến các nhánh được gộp sai dù accumulator tính đúng tổng độ dài từng nhánh. Test compatibility bắt lỗi này mà không cần phụ thuộc lịch thực thi của parallel stream.

### Test ba tham số phải xét cả kết quả nguồn rỗng

~~~java
import java.util.List;

int emptyLength = List.<String>of()
    .parallelStream()
    .reduce(0, (sum, word) -> sum + word.length(), Integer::sum);

System.out.println(emptyLength); // 0
~~~

Nếu identity khác 0, kết quả nguồn rỗng sẽ phản ánh identity sai ngay lập tức.

## 8. Phản ví dụ: dùng mutable identity trong reduce

`reduce` đòi một phép rút gọn không có side effect làm thay đổi state chia sẻ. Dùng một `ArrayList` mutable làm identity và gọi `add` trong accumulator là sai về thiết kế, đặc biệt khi chạy song song:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> input = List.of("A", "B", "C");

// PHẢN VÍ DỤ: không dùng để thu thập song song.
ArrayList<String> wrong = input.parallelStream()
    .reduce(
        new ArrayList<String>(),
        (list, value) -> {
            list.add(value);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

**Vấn đề:**

- Identity là **một object cụ thể**, không phải factory cung cấp container riêng cho từng nhánh.
- Accumulator thay đổi object đó, tạo side effect, vi phạm hợp đồng non-interfering/stateless của reduction.
- Nhiều nhánh có thể cùng tham chiếu container hoặc combiner có thể gộp những tham chiếu đã bị sửa.
- Kết quả có thể lặp phần tử, mất phần tử hoặc tạo tình huống unsafe; việc một lần chạy đúng không chứng minh thuật toán đúng.

### Sửa bằng Collector cho mutable reduction

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> correct = input.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(correct); // [A, B, C]
~~~

`collect` có `supplier` tạo container mới, `accumulator` cập nhật container của từng phần và `combiner` hợp nhất theo hợp đồng Collector.

Nếu vẫn muốn dùng `reduce` để sinh một giá trị tổng hợp, hãy chọn object **bất biến** và tạo object mới trong accumulator/combiner, hoặc dùng các operation chuyên biệt như `mapToLong().sum()`.

## 9. Luật của Collector: không chỉ là combiner có tính kết hợp

Một Collector là chiến lược *mutable reduction*. Ta xét kiểu:

~~~java
Collector<T, A, R>
~~~

Trong đó `T` là phần tử đầu vào, `A` là container tích lũy, `R` là kết quả cuối. Thành phần chính:

| Thành phần | Hợp đồng | Lỗi thường gặp |
| --- | --- | --- |
| `supplier()` | Tạo container tích lũy mới phù hợp | Trả về cùng object mutable cho mọi lần gọi |
| `accumulator()` | Đưa một phần tử vào container `A` | Thay đổi nguồn hoặc biến dùng chung ngoài container |
| `combiner()` | Gộp hai container `A` thành một container tương đương | Làm mất/lặp dữ liệu, đảo thứ tự, dùng gộp không kết hợp |
| `finisher()` | Chuyển container `A` thành kết quả `R` | Bỏ dữ liệu, trả view mutable không mong muốn |
| `characteristics()` | Khai báo đặc tính collector thực sự bảo đảm | Khai báo `UNORDERED`, `CONCURRENT` hoặc `IDENTITY_FINISH` sai |

### 9.1. Luật identity của combiner

Với một trạng thái tích lũy hợp lệ `a`, nếu `e = supplier.get()` là một container mới/rỗng, việc combine `a` với `e` phải **tương đương** `a`.

~~~text
combine(a, supplier()) ≈ a
~~~

Dấu `≈` là **tương đương về kết quả theo hợp đồng collector**, không nhất thiết là cùng object hoặc cùng kiểu mutable state. Khi kiểm thử, cần chuyển trạng thái qua finisher hoặc so sánh bất biến nghiệp vụ, thay vì đòi cùng tham chiếu.

### 9.2. Luật associativity của toàn quá trình collect

Với một nguồn có thứ tự `[a,b,c,d]`, hai cách tạo kết quả phải tương đương:

~~~text
Cách 1:
  A = supplier()
  acc(A,a), acc(A,b), acc(A,c), acc(A,d)
  result = finish(A)

Cách 2:
  L = supplier(); acc(L,a), acc(L,b)
  R = supplier(); acc(R,c), acc(R,d)
  result = finish(combine(L,R))
~~~

Nếu đổi vị trí cắt thành `[a] + [b,c,d]` hay `[] + [a,b,c,d]`, kết quả vẫn phải tương đương. Một combiner đúng **không chỉ trả một object có cùng kích thước**; nó phải giữ đúng mọi giá trị và thứ tự được yêu cầu.

### 9.3. Đặc tính collector và ý nghĩa tương đương

Với collector **không UNORDERED**, hai kết quả trên ordered source phải tương đương theo **encounter order**. Với collector `UNORDERED`, thứ tự có thể không quan trọng; ví dụ Map `{"A"→1,"B"→2}` có thể được kiểm bằng `Map.equals` thay vì thứ tự chuỗi in ra.

Cần phân biệt: `Collector.Characteristics.UNORDERED` là thông báo **kết quả không phụ thuộc thứ tự nguồn**, không có nghĩa “bất kỳ phép gộp nào cũng hợp lệ”.

## 10. Tự xây Collector đúng: ghép String theo thứ tự

Để nhìn rõ vai trò của accumulator và combiner, ta xây một collector ghép chuỗi. Phép nối String có tính kết hợp **nhưng không giao hoán**, nên combiner phải giữ thứ tự nhánh trái rồi nhánh phải.

~~~java
import java.util.List;
import java.util.stream.Collector;

public class OrderedStringCollector {

    static Collector<String, StringBuilder, String> joining() {
        return Collector.of(
            StringBuilder::new,
            (builder, element) -> builder.append(element),
            (left, right) -> left.append(right),
            StringBuilder::toString
        );
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");

        String sequential = words.stream()
            .collect(joining());

        String parallel = words.parallelStream()
            .collect(joining());

        System.out.println(sequential); // ABCD
        System.out.println(parallel);   // ABCD
    }
}
~~~

**Giải thích:**

- `supplier()` tạo một `StringBuilder` **mới** mỗi lần.
- `accumulator` thêm một phần tử vào cuối builder.
- `combiner` nối nội dung builder bên phải vào **sau** builder bên trái.
- `finisher` chuyển builder thành `String`.
- Collector này **không** được khai báo `UNORDERED` hoặc `CONCURRENT`. Bởi kết quả là `String` còn trạng thái là `StringBuilder`, cũng không được khai báo `IDENTITY_FINISH`.

Việc mutable `StringBuilder` không thread-safe tự thân **không làm collector này sai**, vì collector thường được hệ thống dùng với các container riêng biệt trước khi combine. Sai lầm sẽ xuất hiện nếu chia sẻ **cùng một builder giữa các nhánh** hoặc công bố sai đặc tính `CONCURRENT`.

## 11. Kiểm thử Collector bằng cách ép mọi điểm chia

Bài kiểm tra sau sử dụng chính `supplier`, `accumulator`, `combiner` và `finisher` của collector. Nó bắt buộc một số phần tử đi vào container trái, phần còn lại vào container phải, rồi kết hợp chúng.

~~~java
import java.util.List;
import java.util.stream.Collector;

public class CollectorSplitChecks {

    static String collectWithSplit(
        List<String> input,
        int cut,
        Collector<String, StringBuilder, String> collector
    ) {
        StringBuilder left = collector.supplier().get();
        StringBuilder right = collector.supplier().get();

        for (int i = 0; i < cut; i++) {
            collector.accumulator().accept(left, input.get(i));
        }
        for (int i = cut; i < input.size(); i++) {
            collector.accumulator().accept(right, input.get(i));
        }

        StringBuilder merged = collector.combiner()
            .apply(left, right);

        return collector.finisher().apply(merged);
    }

    public static void main(String[] args) {
        List<String> input = List.of("A", "B", "C", "D");
        var collector = OrderedStringCollector.joining();

        String reference = input.stream().collect(collector);

        for (int cut = 0; cut <= input.size(); cut++) {
            String actual = collectWithSplit(input, cut, collector);

            if (!reference.equals(actual)) {
                throw new AssertionError(
                    "Sai tại cut=" + cut + ": " + actual
                );
            }
        }

        System.out.println("PASS");
    }
}
~~~

**Lưu ý:** Hai state được tạo **mới** cho mỗi test. Sau khi combiner chạy, nó có thể **làm thay đổi** state trái/phải, nên không nên tái sử dụng chúng làm oracle cho lần kiểm tra khác.

### Combiner bị đảo thứ tự

Một phản ví dụ:

~~~java
import java.util.stream.Collector;

Collector<String, StringBuilder, String> broken = Collector.of(
    StringBuilder::new,
    (builder, element) -> builder.append(element),
    (left, right) -> right.append(left), // SAI cho ordered stream.
    StringBuilder::toString
);
~~~

Khi ép chia `["A","B"] + ["C","D"]`, combiner sai có thể trả `"CDAB"`, dù collector tuần tự không dùng combiner sẽ trả `"ABCD"`.

Đây là loại lỗi mà test một lần `stream().collect(...)` thường không bắt được. Hãy dùng chính `CollectorSplitChecks.collectWithSplit` để chạy với `broken`; khi có ít nhất hai nhánh không rỗng, kết quả sẽ không tương đương thứ tự nguồn.

### Không chỉ kiểm tra một cách chia

Với nguồn độ dài 4, thử `cut = 0,1,2,3,4`. Đặc biệt `cut = 0` và `cut = 4` thử **identity của combiner khi một nhánh rỗng**. Nếu chỉ thử split ở giữa, dễ bỏ sót trường hợp combiner làm mất giá trị khi container bên phải rỗng.

## 12. Kiểm thử nhiều cây gộp và luật của combiner

Ép một điểm chia chỉ kiểm tra hai nhánh. Với Collector phức tạp, hãy kiểm tra thêm cách nhóm **ba hoặc nhiều** container tích lũy.

~~~text
Nguồn ordered: [A, B] | [C] | [D, E]

Cây trái:  combine(combine(L, M), R)
Cây phải: combine(L, combine(M, R))
~~~

Cả hai phải tạo kết quả tương đương theo hợp đồng. Với `StringBuilder`, combiner có mutation, nên **không được dùng chung cùng object L/M/R** để tính cả hai cây. Phải tạo các trạng thái độc lập cho từng phép thử.

Đoạn kiểm tra sau tái tạo state cho mỗi cây:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class CollectorTreesTest {

    static StringBuilder part(
        List<String> values,
        Collector<String, StringBuilder, String> collector
    ) {
        StringBuilder result = collector.supplier().get();

        for (String value : values) {
            collector.accumulator().accept(result, value);
        }

        return result;
    }

    static String combineTree(
        List<String> leftPart,
        List<String> midPart,
        List<String> rightPart,
        boolean leftAssociative,
        Collector<String, StringBuilder, String> collector
    ) {
        StringBuilder a = part(leftPart, collector);
        StringBuilder b = part(midPart, collector);
        StringBuilder c = part(rightPart, collector);

        StringBuilder combined = leftAssociative
            ? collector.combiner().apply(
                collector.combiner().apply(a, b), c
            )
            : collector.combiner().apply(
                a, collector.combiner().apply(b, c)
            );

        return collector.finisher().apply(combined);
    }

    public static void main(String[] args) {
        var collector = OrderedStringCollector.joining();
        var left = List.of("A", "B");
        var middle = List.of("C");
        var right = List.of("D", "E");

        String tree1 = combineTree(
            left, middle, right, true, collector
        );
        String tree2 = combineTree(
            left, middle, right, false, collector
        );

        if (!tree1.equals(tree2) || !tree1.equals("ABCDE")) {
            throw new AssertionError("Collector không kết hợp");
        }

        System.out.println("PASS");
    }
}
~~~

**Ý nghĩa:** Kiểm thử này xác nhận gộp hai lần theo các dấu ngoặc khác nhau. Nó chưa mô phỏng mọi lịch concurrent, nhưng mạnh hơn chỉ so sánh một lượt chạy tuần tự với một lượt chạy song song.


## 13. Các lỗi Collector không thể thấy từ một lần chạy tuần tự

Một collector có thể chạy tuần tự đúng vì lúc đó chỉ dùng **một container duy nhất** và **ít hoặc không gọi combiner**. Khi nguồn bị chia, các giả định ẩn mới bộc lộ.

### 13.1. Supplier trả cùng một container mutable

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

ArrayList<String> shared = new ArrayList<>();

// PHẢN VÍ DỤ: supplier trả cùng một object cho nhiều lần gọi.
Collector<String, ArrayList<String>, ArrayList<String>> broken =
    Collector.of(
        () -> shared,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

`supplier` phải tạo container tích lũy phù hợp cho **từng phần đánh giá**. Nếu nhiều nhánh nhận cùng một `ArrayList`, việc combine hai tham chiếu có thể tạo bản sao lặp hoặc có vấn đề đồng thời.

**Cách sửa:**

~~~java
Collector<String, ArrayList<String>, ArrayList<String>> correct =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

Khi chưa cần custom collector, `Collectors.toCollection(ArrayList::new)` thường ngắn gọn và an toàn hơn.

### 13.2. Combiner bỏ qua một nhánh

~~~java
// Sai: không gộp dữ liệu phía phải.
// (left, right) -> left
~~~

Collector như vậy có thể trả đúng trong một lượt tuần tự nhưng bỏ qua dữ liệu khi parallel. Test ép `split = 1` hoặc `split = 2` sẽ phát hiện lỗi nếu nhánh phải có phần tử.

### 13.3. Combiner vô tình gộp một container với chính nó

Nếu supplier trả chung một object hoặc combiner nhận hai tham chiếu alias không được dự tính, lệnh `left.addAll(right)` với `left == right` có thể nhân đôi dữ liệu. Do đó, kiểm tra **fresh supplier** và quyền sở hữu state quan trọng không kém tính kết hợp của nội dung.

### 13.4. Finisher làm mất dữ liệu

Giả sử accumulator thu đủ phần tử, combiner đúng, nhưng finisher chỉ trả một phần:

~~~java
// PHẢN VÍ DỤ: bỏ phần tử cuối.
builder -> builder.length() == 0
    ? ""
    : builder.substring(0, builder.length() - 1)
~~~

Khi kiểm thử `Collector<T,A,R>`, phải dùng **finisher thực tế** ở cả kết quả reference lẫn kết quả ép chia. Tuy nhiên, cũng cần có **oracle nghiệp vụ độc lập**, ví dụ kết quả mong đợi là `"ABCD"`, vì nếu finisher sai giống nhau ở cả hai nhánh thì chỉ so sánh “tuần tự == chia đôi” vẫn có thể PASS.

### 13.5. Khai báo IDENTITY_FINISH sai

`Collector.Characteristics.IDENTITY_FINISH` có nghĩa phép hoàn tất về cơ bản là identity, kết quả `A` tương ứng trực tiếp với `R` theo hợp đồng. Không khai báo cờ này khi:

- State `A` là `StringBuilder` nhưng kết quả `R` là `String`.
- Finisher cần chuyển mutable Map thành một value object khác.
- Finisher thêm bước chuẩn hóa, kiểm tra hoặc tạo snapshot.

Ví dụ collector `OrderedStringCollector.joining()` ở trên có finisher `StringBuilder::toString`, nên **không có IDENTITY_FINISH**. Khai báo sai có thể khiến framework bỏ qua bước hoàn tất hoặc dẫn tới lỗi kiểu/chất lượng kết quả.

### 13.6. Khai báo CONCURRENT sai

`Collector.Characteristics.CONCURRENT` chỉ nên khai báo khi accumulator cho phép được gọi **đồng thời trên cùng một container** theo hợp đồng. Một `StringBuilder` thông thường không thread-safe; không thể tùy tiện đánh dấu collector của mục 10 là concurrent.

`UNORDERED` cũng không phải cờ bật để tăng tốc bằng mọi giá. Nếu kết quả yêu cầu giữ thứ tự ký tự `"ABCD"`, không khai báo `UNORDERED` và kỳ vọng cách merge sẽ tự giữ thứ tự nguồn.

## 14. Bài toán trung bình: tại sao (a+b)/2 không kết hợp?

Một lỗi tổng hợp trung bình rất phổ biến là thử dùng phép gộp:

~~~java
(a, b) -> (a + b) / 2.0
~~~

Thử ba giá trị `0, 10, 20`:

~~~text
((0 + 10) / 2 + 20) / 2 = 12.5

(0 + (10 + 20) / 2) / 2 = 7.5

Trung bình thực sự của 0, 10, 20 = 10
~~~

Phép “lấy trung bình của hai số” không kết hợp và không có identity phù hợp cho việc giảm một tập số tùy ý. Thậm chí hai nhóm có trung bình giống nhau cũng có thể có **số phần tử khác nhau**, nên không thể lấy trung bình các trung bình nhóm khi không biết trọng số.

### 14.1. Mô hình trạng thái đúng: (sum, count)

Một giải pháp là tích lũy **tổng** và **số lượng**; hai trạng thái từng phần kết hợp bằng cách cộng thành phần tương ứng.

~~~java
import java.util.List;

public class AverageWithImmutableState {

    record Stats(long sum, long count) {

        Stats add(int value) {
            return new Stats(
                Math.addExact(sum, value),
                Math.addExact(count, 1L)
            );
        }

        Stats merge(Stats other) {
            return new Stats(
                Math.addExact(sum, other.sum),
                Math.addExact(count, other.count)
            );
        }

        double averageOrThrow() {
            if (count == 0) {
                throw new IllegalStateException("Không có dữ liệu");
            }
            return (double) sum / count;
        }
    }

    static Stats summarize(List<Integer> values, boolean parallel) {
        var stream = parallel
            ? values.parallelStream()
            : values.stream();

        return stream.reduce(
            new Stats(0L, 0L),
            Stats::add,
            Stats::merge
        );
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(0, 10, 20);

        Stats serial = summarize(values, false);
        Stats parallel = summarize(values, true);

        if (!serial.equals(parallel)) {
            throw new AssertionError("Hai mode khác kết quả");
        }

        System.out.println(serial.averageOrThrow()); // 10.0
        System.out.println(summarize(List.of(), false));
        // Stats[sum=0, count=0]
    }
}
~~~

**Vì sao kiểu Stats phù hợp?**

- Identity là `Stats(0,0)`.
- `merge` cộng tổng và cộng số lượng; nó kết hợp được trên miền giá trị không gây overflow.
- `add` và `merge` tạo **record mới**, không sửa một identity mutable dùng chung.
- Việc chia nguồn không ảnh hưởng đến tổng/số lượng khi mọi phép cộng hợp lệ.
- Nguồn rỗng có count bằng 0; **không** coi trung bình bằng 0.0 là hiển nhiên.

Một collector chuẩn như `Collectors.averagingInt` hoặc `IntStream.average` thường phù hợp hơn nếu chỉ cần trung bình. Ví dụ Stats nhằm làm rõ **cách thiết kế accumulator/combiner đúng**.

### 14.2. Kiểm thử compatibility của Stats

Giả sử `u = Stats(10,2)` và phần tử mới `t = 5`:

~~~text
identity = Stats(0,0)

merge(u, add(identity,5))
= merge(Stats(10,2), Stats(5,1))
= Stats(15,3)

add(u,5)
= Stats(15,3)
~~~

Cả hai đường đi cho cùng kết quả. Đối với production, có thể kiểm tra property này với nhiều Stats hợp lệ và đầu vào ngẫu nhiên, đồng thời thử các biên có thể gây overflow.

## 15. Số thực: associativity về toán học khác với bằng nhau tuyệt đối theo bit

Phép cộng `double` chịu ảnh hưởng của quy tắc làm tròn IEEE 754. Đổi cách nhóm phép cộng có thể cho kết quả khác nhau dù toán học thực có tính kết hợp.

~~~java
public class FloatingPointAssociativity {
    public static void main(String[] args) {
        double a = 1e16;
        double b = -1e16;
        double c = 1.0;

        double left = (a + b) + c;
        double right = a + (b + c);

        System.out.println(left);  // 1.0
        System.out.println(right); // 0.0
        System.out.println(left == right); // false
    }
}
~~~

Một parallel stream cộng `double` có thể gộp các partial result theo cây khác với phép cộng tuần tự. Vì vậy, không nên yêu cầu mọi thứ phải **bằng bit** nếu nghiệp vụ chỉ cần sai số trong ngưỡng cho phép. Tuy nhiên, cũng không nên dùng `Math.abs(a-b) < epsilon` một cách mù quáng.

### Chiến lược so sánh kết quả double

- Với dữ liệu có độ lớn biết trước, chọn ngưỡng **sai số tuyệt đối** dựa trên yêu cầu nghiệp vụ.
- Khi các giá trị có độ lớn rất khác nhau, cân nhắc sai số **tương đối** hoặc kết hợp tuyệt đối–tương đối.
- Xử lý riêng `NaN`, vô hạn, overflow và `-0.0` nếu chúng có ý nghĩa với bài toán.
- Kiểm tra rằng sai khác nhỏ **không che** một lỗi thật như thiếu cả một nhóm dữ liệu.
- Nếu cần tiền tệ thập phân chính xác, dùng `BigDecimal` và chính sách scale/rounding rõ ràng; đừng dùng `double` để mô hình hóa tiền tệ tùy tiện.

Một helper so sánh hữu hạn cơ bản:

~~~java
public class FloatingComparison {

    static boolean close(double expected, double actual) {
        if (Double.isNaN(expected) || Double.isNaN(actual)) {
            return false;
        }
        if (expected == actual) {
            return true; // Bao gồm +∞ với +∞, -∞ với -∞.
        }
        if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
            return false;
        }

        double absoluteTolerance = 1e-9;
        double relativeTolerance = 1e-9;
        double scale = Math.max(
            Math.abs(expected), Math.abs(actual)
        );

        return Math.abs(expected - actual)
            <= Math.max(absoluteTolerance, relativeTolerance * scale);
    }
}
~~~

Các ngưỡng `1e-9` **chỉ là minh họa**, không phải chuẩn dùng chung. Các tổng triệt tiêu lớn như `1e16 - 1e16 + 1` có thể gây sai khác tương đối đáng kể; phải quyết định yêu cầu độ chính xác trước khi đặt tolerance.

### Đừng nhầm không kết hợp của double với lỗi Collector khác

Nếu kết quả song song lệch nhỏ ở chữ số cuối khi cộng rất nhiều `double`, có thể do làm tròn. Nếu thiếu hoàn toàn một nhóm, số đếm sai hoặc có phần tử lặp, đó **không phải** sai số làm tròn đơn thuần. Hãy kiểm tra **count**, tập khóa, tổng theo nhóm và các bất biến khác song song với phép so sánh số thực.

## 16. Chọn oracle kiểm thử theo kiểu kết quả

Không phải mọi kết quả đều được so sánh bằng `toString()` hoặc cùng một thứ tự duyệt. Hãy xác định **điều gì được hợp đồng bảo đảm**.

| Kết quả | Cách so sánh thường phù hợp | Điều cần tránh |
| --- | --- | --- |
| `long` tổng/số đếm | Bằng chính xác, nếu miền tính toán đã xác định | Bỏ qua overflow nghiệp vụ |
| `List<T>` từ ordered stream | `List.equals` để kiểm tra nội dung và thứ tự | So sánh tập khi thứ tự thực sự quan trọng |
| `Set<T>` | `Set.equals` | Đòi iterator order giống nhau |
| `Map<K,V>` | `Map.equals` | So sánh chuỗi in từ HashMap |
| `ConcurrentMap<K,V>` | `Map.equals` sau khi collect xong | Đòi thứ tự duyệt, “last wins” theo lịch thread |
| `Optional<T>` | `Optional.equals` hoặc trạng thái và giá trị | Tự thay Optional.empty bằng null |
| `double` | So sánh theo chính sách độ chính xác | Dùng một epsilon tùy tiện cho mọi bài toán |
| Collector ordered nối chuỗi | So sánh chuỗi chính xác | Khai báo UNORDERED rồi yêu cầu giữ thứ tự |
| Nhóm trùng theo khóa | So sánh khóa, kích thước, phần tử nhóm theo hợp đồng | Chỉ so số nhóm và bỏ qua payload |

Ví dụ kiểm tra grouping:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupingOracle {
    public static void main(String[] args) {
        List<String> values = List.of("A", "B", "A", "C", "B");

        Map<String, Long> serial = values.stream()
            .collect(Collectors.groupingBy(
                item -> item, Collectors.counting()
            ));

        Map<String, Long> parallel = values.parallelStream()
            .collect(Collectors.groupingBy(
                item -> item, Collectors.counting()
            ));

        if (!serial.equals(parallel)) {
            throw new AssertionError("Nhóm khác nhau");
        }

        if (!Long.valueOf(2L).equals(serial.get("A"))) {
            throw new AssertionError("Sai nhóm A");
        }

        System.out.println("PASS");
    }
}
~~~

Không viết `serial.toString().equals(parallel.toString())` vì Map không có hợp đồng chung về thứ tự duyệt. Khi dùng `groupingByConcurrent`, danh sách các phần tử bên trong nhóm cũng **không được bảo đảm** giữ encounter order; phải chọn oracle theo đúng yêu cầu nghiệp vụ.

### Lưu ý về Concurrent Collector

`Collectors.toConcurrentMap` có `CONCURRENT` và `UNORDERED`. Nếu merge function nhạy với thứ tự, ví dụ `(left,right) -> right`, kết quả “bản ghi cuối” có thể phụ thuộc lịch xử lý. Nếu cần bản ghi mới nhất theo nghiệp vụ, dùng `version`/`timestamp` và phép chọn đại diện xác định, hoặc chọn chiến lược thu thập có thứ tự.


## 17. Quy trình điều tra khi sequential và parallel cho kết quả khác nhau

Nếu phát hiện một pipeline trả kết quả khác nhau theo chế độ, không nên chỉ thêm `sequential()` để che lỗi. Hãy cô lập nguyên nhân theo thứ tự:

1. **Đóng băng đầu vào:** dùng một danh sách nhỏ, bất biến, có cả phần tử âm, khóa trùng, nguồn rỗng và dữ liệu biên. Nếu dữ liệu đọc từ file/database, bảo đảm hai chế độ nhìn cùng snapshot.
2. **Tách pipeline:** xác minh kết quả `filter`/`map` độc lập, rồi kiểm tra riêng `reduce` hoặc `collect`. Không nhồi I/O, chuẩn hóa, tổng hợp, ghi log vào một phép thử khó quan sát.
3. **Kiểm tra luật:** identity, associativity, compatibility của reduce; tính đúng `supplier`/`combiner`/`finisher` của Collector.
4. **Ép phân hoạch:** thử cắt ở đầu, giữa, cuối; kiểm tra nhánh rỗng, nhánh một phần tử và các cây gộp khác nhau.
5. **Xem lại thứ tự:** collector có `UNORDERED` hay không, kết quả có phụ thuộc bản ghi “đầu/cuối” không, và oracle có yêu cầu đúng thứ tự dù API không cam kết không.
6. **Xem lại mutable state:** mapper/accumulator có đụng biến dùng chung, thay đổi nguồn, hoặc dùng supplier trả cùng object không?
7. **Chọn cách so sánh phù hợp:** số nguyên, List ordered, Map, Set, Optional và double có quy tắc xác minh khác nhau.

### Bảng chẩn đoán nhanh

| Triệu chứng | Nghi vấn | Cách kiểm tra |
| --- | --- | --- |
| `reduce` sai chỉ khi chia nguồn | Toán tử không kết hợp | Thử `(a op b) op c` với `a op (b op c)` |
| Nguồn rỗng trả giá trị sai | Identity sai | Test `List.of()` và split có nhánh trống |
| Collector thiếu một nửa dữ liệu | Combiner bỏ nhánh | Ép split ở giữa |
| Kết quả lặp phần tử | Supplier dùng chung state, alias | Kiểm tra object được tạo mới mỗi lần |
| Ký tự trong String bị đảo | Combiner ghép sai thứ tự | Ép `["A","B"] + ["C","D"]` |
| Bản ghi theo khóa trùng sai | Merge function phụ thuộc lịch | Test nhiều phần tử cùng khóa và các thứ tự |
| Hai Map in khác nhau | So sánh sai oracle | Dùng `Map.equals` |
| `double` lệch chữ số cuối | Floating-point rounding | Kiểm tra sai số và các bất biến khác |
| Lỗi chỉ khi chạy concurrent | State ngoài không an toàn | Xem callback và characteristics |
| Kết quả sai kiểu hoặc thiếu bước chuyển | Khai báo `IDENTITY_FINISH` sai | Xác minh `A`, `R` và finisher |

**Lưu ý:** Với Collector phức tạp, chỉ so sánh hai cách collect bằng cùng một collector chưa đủ; nếu cả hai cùng sai ở finisher, kết quả vẫn có thể bằng nhau. Hãy thêm **oracle nghiệp vụ độc lập**.

## 18. Kiểm thử ngẫu nhiên có seed cố định và mọi điểm chia

Ta có thể sinh nhiều danh sách nhỏ rồi thử mọi vị trí cắt với Collector nối chuỗi ở mục 10. `String.join` là oracle độc lập, không dùng chính Collector đang kiểm thử để tạo expected value.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class RandomizedCollectorChecks {
    public static void main(String[] args) {
        Random random = new Random(2026L);
        var collector = OrderedStringCollector.joining();

        for (int trial = 0; trial < 200; trial++) {
            int count = random.nextInt(9);
            List<String> values = new ArrayList<>();

            for (int i = 0; i < count; i++) {
                values.add(
                    String.valueOf((char) ('A' + random.nextInt(4)))
                );
            }

            String expected = String.join("", values);

            for (int split = 0; split <= values.size(); split++) {
                String actual =
                    CollectorSplitChecks.collectWithSplit(
                        values, split, collector
                    );

                if (!expected.equals(actual)) {
                    throw new AssertionError(
                        "trial=" + trial
                        + ", split=" + split
                        + ", input=" + values
                        + ", actual=" + actual
                    );
                }
            }
        }

        System.out.println("PASS");
    }
}
~~~

Với cách này, ta kiểm tra mọi split cho 200 danh sách giả lập. **Nó không phải chứng minh hình thức**: miền dữ liệu chỉ gồm ký tự `A`–`D` và độ dài nhỏ. Để tăng độ tin cậy, nên thêm các ca biên, miền dữ liệu lớn hơn, `null` theo chính sách input, và cách chia thành ba/nhiều nhánh.

Khi phát hiện phản ví dụ, nên thu nhỏ dữ liệu (*shrinking*) để tạo một test hồi quy ngắn, ví dụ `["A","B","C"]` thay vì hàng trăm phần tử. Với concurrent collector, kiểm thử phân hoạch tuần tự chưa phát hiện hết các data race; cần các phép thử đồng thời phù hợp, nhưng không dựa vào tên thread hay lịch callback cố định.

## 19. Những lỗi suy luận dễ mắc

### 19.1. Giao hoán nghĩa là kết hợp

Sai. `(a+b)/2` giao hoán nhưng không kết hợp; kết quả thay đổi khi gộp theo nhóm khác nhau.

### 19.2. Identity của mọi phép tổng hợp là 0

Sai. Phép nhân dùng 1; max trên `int` dùng `Integer.MIN_VALUE`; nối chuỗi dùng `""`. Nếu không có identity phù hợp, nên dùng overload trả Optional hoặc thiết kế kiểu trạng thái khác.

### 19.3. Một lần parallel bằng sequential đủ để khẳng định đúng

Sai. Cách chia nguồn có thể chưa kích hoạt combiner lỗi, hoặc dữ liệu chưa chạm trường hợp biên. Dùng kiểm thử luật và phân hoạch cưỡng bức.

### 19.4. Chỉ kiểm tra combiner của Collector

Chưa đủ. Supplier có thể dùng chung state, accumulator có side effect, finisher có thể bỏ dữ liệu, và characteristics có thể khai báo sai.

### 19.5. Có thể dùng ArrayList mutable làm identity của reduce

Không nên. `reduce` không có supplier tạo container mới theo từng nhánh; mutable reduction cần thiết kế bằng `collect` hoặc Collector.

### 19.6. String nối đúng khi tuần tự thì chắc chắn đúng khi parallel

Không. Nếu combiner nối nhánh phải trước nhánh trái, kết quả bị đảo, trong khi chạy tuần tự có thể không dùng combiner.

### 19.7. HashMap in thứ tự khác nghĩa là nội dung sai

Không nhất thiết. Nếu contract chỉ yêu cầu cùng các entry, `Map.equals` mới là so sánh chính xác.

### 19.8. Bất kỳ chênh lệch double nào cũng có thể bỏ qua

Sai. Cần chính sách sai số và kiểm tra thêm count/tập khóa. Lỗi mất dữ liệu không phải chỉ là floating-point rounding.

### 19.9. Collector CONCURRENT tự làm mọi giá trị bên trong Map thread-safe

Không. `ConcurrentMap<K,List<V>>` không tự bảo đảm mọi List value an toàn cho sửa đổi đồng thời sau khi collect.

### 19.10. sequential() là cách sửa triệt để

Chuyển tuần tự có thể che bug. Nếu nghiệp vụ bắt buộc stateful processing theo thứ tự, hãy diễn đạt rõ; nếu cần song song, phải sửa thuật toán gộp.

## 20. Checklist trước khi cho phép chạy song song

| Kiểm tra | Tiêu chí đạt |
| --- | --- |
| Identity | Phần tử đơn vị đúng trên miền dữ liệu |
| Associativity | Hai cách nhóm cho kết quả tương đương |
| Compatibility | Accumulator và combiner của reduce ba tham số tương thích |
| Supplier | Tạo container mới, không chia sẻ mutable state sai |
| Accumulator | Không can thiệp nguồn, không phụ thuộc shared state |
| Combiner | Không làm mất/lặp; bảo toàn encounter order nếu cần |
| Finisher | Chuyển `A → R` đúng, không mất dữ liệu |
| Characteristics | Không khai báo `UNORDERED`, `CONCURRENT`, `IDENTITY_FINISH` sai |
| Nguồn rỗng | Trả identity/Optional/collector result đúng hợp đồng |
| Nhánh một phần tử | Kết quả đúng |
| Nhiều cách chia | Đã thử các vị trí split và nhiều cây gộp |
| Số học | Có chính sách overflow, NaN, Infinity và tolerance |
| Kiểu kết quả | Oracle phù hợp List/Set/Map/Optional |
| Thứ tự | Không dựa vào thứ tự khi API không bảo đảm |
| Concurrency | Nếu accumulator concurrent, state hỗ trợ đúng |
| Hiệu năng | Chỉ benchmark sau khi bảo đảm tính đúng |

## 21. Câu hỏi tự kiểm tra và bài mở rộng

1. **Associativity là gì?** `op(op(a,b),c) = op(a,op(b,c))`.
2. **Associativity và commutativity giống nhau không?** Không; nối chuỗi kết hợp nhưng không giao hoán.
3. **Vì sao phép trừ không thích hợp cho parallel reduce?** Đổi dấu ngoặc nhóm làm đổi kết quả.
4. **Vì sao `reduce(0, Integer::max)` sai với các số âm?** 0 không là identity trên miền số âm.
5. **Reduce không identity trên nguồn rỗng trả gì?** `Optional.empty()`.
6. **Luật bổ sung của reduce ba tham số?** Compatibility giữa accumulator và combiner.
7. **Công thức compatibility?** `comb(u, acc(identity,t)) = acc(u,t)`.
8. **Vì sao không dùng ArrayList mutable làm identity của reduce?** State dùng chung và callback có mutation không hợp đồng.
9. **Supplier của Collector phải cung cấp gì?** Container tích lũy mới phù hợp cho mỗi phần đánh giá.
10. **Combiner cần đảm bảo gì?** Gộp các partial state mà không mất/lặp dữ liệu, giữ thứ tự khi cần.
11. **Vì sao thử split=0 và split=size?** Hai ca đó kiểm tra nhánh rỗng và identity.
12. **Combiner nối String có thể đảo nhánh không?** Không trên ordered stream.
13. **Vì sao phải tạo state mới cho mỗi cây gộp?** Vì combiner có thể mutate object cũ.
14. **Có thể khai báo IDENTITY_FINISH khi finisher biến StringBuilder thành String?** Không.
15. **Khi nào khai báo CONCURRENT?** Khi accumulator an toàn khi gọi đồng thời trên cùng container.
16. **UNORDERED có tự bảo đảm merge function đúng không?** Không, phải thiết kế phép gộp độc lập thứ tự.
17. **Vì sao `(a+b)/2` không thể dùng để gộp trung bình tùy ý?** Nó không kết hợp và không giữ trọng số của nhóm.
18. **Cách tính trung bình đúng từ các partial result?** Gộp `(sum,count)`, rồi tính `sum/count` cuối cùng.
19. **Vì sao double sum có thể khác theo cách chia?** Sai số làm tròn.
20. **Map nên được so sánh thế nào?** Thường dùng `Map.equals`, không so chuỗi in.
21. **Random test có chứng minh mọi trường hợp?** Không, chỉ tăng độ bao phủ.
22. **Có nên dùng `peek` để đếm chính xác callback làm bằng chứng correctness?** Không, vì lazy/short-circuit/optimization.
23. **Tại sao phải có oracle độc lập?** Cả hai cách chạy có thể cùng chứa một lỗi.
24. **Nên kiểm thử điều gì trước benchmark?** Luật, các nhánh rỗng, phân hoạch, trạng thái và output.
25. **Khi nào giữ Stream tuần tự?** Khi thuật toán có ràng buộc thứ tự không được thiết kế để combine song song; phải diễn đạt rõ giới hạn.

### Bài mở rộng A — Collector cho count và sum

Viết Collector nhận số nguyên và trả `Stats(count,sum)`. Xác minh kết quả tuần tự/song song, mọi split và hai cây gộp. Đối chiếu với `IntStream.summaryStatistics()`.

### Bài mở rộng B — Tìm phản ví dụ phép trừ

Sinh toàn bộ bộ ba `a,b,c` trong dải `[-3,3]`, tìm trường hợp `(a-b)-c != a-(b-c)` và viết test hồi quy tối giản.

### Bài mở rộng C — Finisher sai nhưng test phân hoạch vẫn PASS

Tạo Collector ghép StringBuilder nhưng finisher bỏ ký tự cuối. Hai kiểu phân hoạch có thể cùng sai; bổ sung oracle `String.join("", input)` để tìm lỗi.

### Bài mở rộng D — Collector đồng thời và bản ghi mới nhất

Dùng `toConcurrentMap` với các bản ghi có `version`. Thay đổi thứ tự nguồn và chạy song song. So sánh quy tắc chọn bản ghi theo version với merge `(left,right)->right` không có bảo đảm thứ tự.

### Bài mở rộng E — Số thực lớn và nhỏ

Tạo dãy có các số rất lớn, rất nhỏ và trái dấu. Đo khác biệt giữa tổng tuần tự và song song, nêu chính sách sai số và xác minh count để phân biệt rounding với mất dữ liệu.

**Ghi nhớ:** Một phép `reduce` hoặc `Collector` chỉ đáng tin cậy khi việc **phân hoạch và kết hợp các partial result** không làm thay đổi kết quả ngoài những giới hạn số học được thừa nhận. Kiểm tra **identity**, **associativity**, **compatibility**, state độc lập, combiner/finisher và characteristics. So sánh tuần tự–song song là điểm khởi đầu; kiểm thử cưỡng bức nhiều split/cây và oracle nghiệp vụ độc lập giúp phát hiện lỗi khó thấy trong các pipeline nhỏ.
