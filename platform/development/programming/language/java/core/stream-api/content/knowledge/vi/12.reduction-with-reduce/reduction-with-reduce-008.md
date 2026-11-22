# Rút gọn chuỗi, đối tượng giá trị và kết quả tổng hợp

## 1. Từ nhiều phần tử về một kết quả có ý nghĩa

Trong chương **Phép rút gọn với reduce** của **JAVA_STREAM_API**, `reduce` là terminal operation kết hợp nhiều phần tử thành một kết quả. Đầu ra có thể là số, chuỗi, **đối tượng giá trị bất biến** hoặc một **bản tổng hợp chứa nhiều chỉ tiêu**. Khi hiểu hợp đồng của `reduce`, ta có thể tiếp tục ghép nó với pipeline khai báo `filter`, `map` và các nguồn dữ liệu lazy, kể cả khi xử lý song song.

Ví dụ:

- Một tập từ khóa thành một chuỗi để hiển thị.
- Các khoản tiền cùng đơn vị tiền tệ thành tổng tiền.
- Nhiều bản ghi bán hàng thành kết quả gồm số đơn, số lượng và doanh thu.
- Nhiều điểm số thành thống kê gồm số phần tử, tổng, nhỏ nhất, lớn nhất và trung bình.

~~~text
Nguồn           Các bước trung gian               Terminal reduce
[ x1, x2, x3 ] ─► filter ─► map ──────────────────► GỘP THÀNH KẾT QUẢ
                                                        │
                          ┌─────────────────────────────┼────────────────────────┐
                          ▼                             ▼                        ▼
                       String                  Money / Value Object       Summary / Report
~~~

`reduce` không chỉ là “cộng các số”. Nó định nghĩa **cách gộp hai kết quả cùng cấu trúc** hoặc **cách đưa một phần tử vào một kết quả tổng hợp**. Muốn biểu thức đúng khi pipeline được phân chia và kết hợp, ta phải tuân thủ quy tắc về *identity* (phần tử đơn vị), *associativity* (tính kết hợp), tính độc lập và *combiner*.

Các ví dụ dùng **Java 17+**, chủ yếu với `List`, `record`, `BigDecimal` và Stream. Chúng tập trung vào tính đúng của phép gộp, sau đó mới bàn đến hiệu năng.

## 2. Ba dạng reduce và kiểu trả về

`Stream<T>` có ba overload quan trọng:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator);

T reduce(T identity, BinaryOperator<T> accumulator);

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
~~~

| Dạng | Kết quả | Khi phù hợp |
| --- | --- | --- |
| `reduce(operator)` | `Optional<T>` | Không có identity tự nhiên hoặc muốn thể hiện nguồn rỗng. |
| `reduce(identity, operator)` | `T` | Phần tử và kết quả cùng kiểu `T`, có identity hợp lệ. |
| `reduce(identity, accumulator, combiner)` | `U` | Đầu vào kiểu `T` nhưng đầu ra tổng hợp kiểu `U`. |

Ví dụ với số nguyên:

~~~java
import java.util.List;
import java.util.Optional;

public class ReduceOverloads {
    public static void main(String[] args) {
        List<Integer> values = List.of(3, 4, 5);

        Optional<Integer> one = values.stream().reduce(Integer::sum);
        int two = values.stream().reduce(0, Integer::sum);

        long three = values.stream().reduce(
            0L,
            (sum, value) -> sum + value,
            Long::sum
        );

        System.out.println(one.orElseThrow()); // 12
        System.out.println(two);                // 12
        System.out.println(three);              // 12
    }
}
~~~

Dạng thứ ba cho phép kết quả là `Long` trong khi các phần tử đầu vào là `Integer`. Nó đặc biệt hữu ích khi tính toán một cấu trúc tổng hợp khác kiểu dữ liệu nguồn. Trong các bài toán tổng số nguyên thông thường, primitive stream như `mapToLong(...).sum()` có thể gọn hơn và tránh boxing.

### Nguồn rỗng cho kết quả gì?

~~~java
import java.util.List;
import java.util.Optional;

List<String> empty = List.of();

Optional<String> noValue = empty.stream().reduce(String::concat);
String emptyText = empty.stream().reduce("", String::concat);

// noValue == Optional.empty()
// emptyText.equals("") == true
~~~

Dạng không có identity trả Optional để biểu diễn trường hợp **không có phần tử để rút gọn**. Dạng có identity trả chính identity khi nguồn rỗng. Việc chọn identity vì thế ảnh hưởng trực tiếp đến ý nghĩa nghiệp vụ của kết quả.

## 3. Hợp đồng toán học: identity, associativity và compatibility

### 3.1. Identity phải thực sự trung hòa

Với phép gộp `op` trên kiểu `T`, identity `e` phải thỏa mãn:

~~~text
op(e, x) = x
op(x, e) = x
~~~

Ví dụ:

| Phép gộp | Identity phù hợp | Kiểm tra nhanh |
| --- | --- | --- |
| Cộng số nguyên | `0` | `0 + x = x + 0 = x` |
| Nhân số nguyên | `1` | `1 * x = x * 1 = x` |
| Nối chuỗi | `""` | `"".concat(x) = x.concat("") = x` |
| Cộng `BigDecimal` | `BigDecimal.ZERO` | `0 + amount = amount` về mặt giá trị số |
| Hợp nhất tập hợp theo phép hợp | Tập rỗng | `empty ∪ S = S ∪ empty = S` |

**Sai lầm dễ gặp:** dùng giá trị “mặc định cho dễ nhìn” thay cho identity.

~~~java
import java.util.List;

// Không đúng để tính tổng thông thường:
int wrong = List.of(2, 3).stream().reduce(10, Integer::sum);
// wrong == 15, không phải 5.

// Đúng:
int total = List.of(2, 3).stream().reduce(0, Integer::sum);
// total == 5.
~~~

Identity của một đối tượng giá trị có thể cần thêm ngữ cảnh, ví dụ **loại tiền** hoặc **đơn vị đo**. Một `Money(0, "USD")` chỉ là identity hợp lệ cho những Money có cùng đơn vị USD và một phép cộng cho phép cộng USD.

### 3.2. Phép gộp phải có tính kết hợp

Với các giá trị `a`, `b`, `c`:

~~~text
op(op(a, b), c) = op(a, op(b, c))
~~~

Lấy ví dụ nối chuỗi bằng `String::concat`:

~~~text
("Java" + " Stream") + " API"
=
"Java" + (" Stream" + " API")
=
"Java Stream API"
~~~

Một Stream song song có quyền rút gọn các phần dữ liệu riêng rồi ghép kết quả. Vì thế, phép gộp **phụ thuộc vị trí dấu ngoặc** có thể trả kết quả khác khi phân nhóm khác nhau.

Phép trừ là ví dụ **không có tính kết hợp**:

~~~java
import java.util.List;

int result = List.of(10, 3, 2).stream()
    .reduce(0, (a, b) -> a - b);

System.out.println(result); // -15 trong pipeline tuần tự này.
~~~

Đây không phải một phép rút gọn phù hợp khi muốn giữ kết quả ổn định trên parallel stream. Hơn nữa, `0` không phải identity hai phía cho phép trừ vì `0 - x` khác `x`.

### 3.3. Với reduce ba tham số còn cần compatibility

Với đầu vào kiểu `T`, kết quả tích lũy kiểu `U`, `accumulator` và `combiner` phải phối hợp nhất quán. Với mọi kết quả trung gian `u` và phần tử `t`, cần có:

~~~text
combiner(u, accumulator(identity, t)) = accumulator(u, t)
~~~

`combiner` cũng phải có identity `identity` và có tính kết hợp. Quy tắc này đảm bảo một phần tử được xử lý trong một nhánh riêng rồi ghép vào kết quả chung vẫn cho cùng kết quả như xử lý trực tiếp trên kết quả chung.

Ta sẽ áp dụng chính xác nguyên tắc này cho đối tượng tổng hợp trong các ví dụ sau.

## 4. Nối chuỗi bằng reduce: từ danh sách thành văn bản

Với `String`, phép nối là ví dụ tự nhiên vì `String` bất biến: mỗi lần nối tạo ra một giá trị kết quả mới.

~~~java
import java.util.List;

public class StringReduce {
    public static void main(String[] args) {
        List<String> words = List.of("Java", " ", "Stream", " ", "API");

        String text = words.stream()
            .reduce("", String::concat);

        System.out.println(text); // Java Stream API
    }
}
~~~

`""` là identity. `String::concat` kết hợp được: đặt dấu ngoặc khác nhau không thay đổi chuỗi ký tự khi thứ tự các phần tử giữ nguyên.

Ví dụ này phù hợp khi cần **giải thích nguyên tắc reduce**; với dữ liệu rất lớn, nên cân nhắc `Collectors.joining()` vì `String` bất biến khiến mỗi phép nối có thể sao chép chuỗi đã tích lũy.

### 4.1. Rút gọn chuỗi sau bước làm sạch

~~~java
import java.util.List;

List<String> tags = List.of("  Java ", "", " Stream ", " API  ");

String joined = tags.stream()
    .map(String::strip)
    .filter(text -> !text.isEmpty())
    .reduce("", String::concat);

System.out.println(joined); // JavaStreamAPI
~~~

Với ví dụ này, `filter` loại chuỗi rỗng; `map` làm sạch; `reduce` nối phần còn lại. Pipeline là lazy cho đến khi terminal `reduce` chạy.

Nếu muốn nối các từ bằng một dấu phân cách có ý nghĩa, không thể đơn giản viết `reduce("", (a, b) -> a + ", " + b)`: với phần tử đầu tiên, cách đó sẽ tạo dấu phẩy ở đầu chuỗi.

### 4.2. Nối bằng dấu phân cách mà không có identity

~~~java
import java.util.List;

List<String> cities = List.of("Hà Nội", "Đà Nẵng", "TP.HCM");

String label = cities.stream()
    .reduce((left, right) -> left + " | " + right)
    .orElse("(không có địa điểm)");

System.out.println(label); // Hà Nội | Đà Nẵng | TP.HCM
~~~

Không có identity nên khi nguồn rỗng, `reduce` trả `Optional.empty()`. Với chuỗi đầu vào khác rỗng, phép ghép có dấu `" | "` giữa các nhóm có thể kết hợp được; khi stream có encounter order, kết quả giữ thứ tự nguồn.

Nếu có khả năng các phần tử là chuỗi rỗng, cần xác định rõ chúng có được giữ lại không; chuỗi rỗng ở giữa hai dấu phân cách có thể vẫn là một giá trị nghiệp vụ hợp lệ. Không tự động lọc chuỗi rỗng nếu yêu cầu là giữ nguyên số trường.

### 4.3. Chọn cách đúng cho chuỗi dài

Trong ứng dụng, nếu mục tiêu chỉ là ghép chuỗi với dấu phân cách, dùng collector chuyên dụng thường hiệu quả và rõ ràng hơn:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> cities = List.of("Hà Nội", "Đà Nẵng", "TP.HCM");

String joined = cities.stream()
    .collect(Collectors.joining(" | "));

System.out.println(joined); // Hà Nội | Đà Nẵng | TP.HCM
~~~

`Collectors.joining` sử dụng cơ chế tích lũy chuỗi có thể thay đổi bên trong collector theo hợp đồng, tránh phải tự nối một chuỗi lớn lặp đi lặp lại như `reduce`. Nó còn hỗ trợ `joining(delimiter, prefix, suffix)`.

| Bài toán chuỗi | Cách làm gợi ý |
| --- | --- |
| Minh họa reduce và luật kết hợp | `reduce("", String::concat)` |
| Ghép vài chuỗi bằng quy tắc riêng, nguồn nhỏ | `reduce(BinaryOperator)` nếu quy tắc gộp thực sự có tính kết hợp |
| Ghép nhiều chuỗi, có dấu phân cách | `Collectors.joining(delimiter)` |
| Cần thay đổi các phần tử văn bản trong quá trình duyệt | Collector phù hợp thay vì dùng `StringBuilder` mutable làm identity trong `reduce` |

## 5. Rút gọn đối tượng giá trị bất biến

Đối tượng giá trị (*value object*) mô tả một giá trị miền nghiệp vụ thông qua các thuộc tính của nó, ví dụ khoản tiền, độ dài hay một vector. Khi dùng `reduce`, kiểu dữ liệu này nên có phép kết hợp **trả đối tượng mới** thay vì sửa chính đối tượng đang được sử dụng.

Ta định nghĩa `Money` có số tiền và đơn vị tiền tệ. Phép cộng chỉ hợp lệ khi hai khoản tiền có cùng đơn vị.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class MoneyReduce {
    record Money(BigDecimal amount, String currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }

        Money plus(Money other) {
            if (!currency.equals(other.currency())) {
                throw new IllegalArgumentException(
                    "Không thể cộng hai loại tiền khác nhau"
                );
            }

            return new Money(amount.add(other.amount()), currency);
        }
    }

    public static void main(String[] args) {
        List<Money> payments = List.of(
            new Money(new BigDecimal("125000"), "VND"),
            new Money(new BigDecimal("24900"), "VND"),
            new Money(new BigDecimal("100"), "VND")
        );

        Money zero = new Money(BigDecimal.ZERO, "VND");

        Money total = payments.stream().reduce(zero, Money::plus);

        System.out.println(total);
        // Money[amount=150000, currency=VND]
    }
}
~~~

**Vì sao cách viết này phù hợp?**

- `Money` là record có thành phần `BigDecimal` và `String` bất biến; hàm `plus` tạo bản ghi mới.
- Identity `Money(BigDecimal.ZERO, "VND")` giữ giá trị của mọi Money cùng tiền tệ khi cộng.
- Với các khoản tiền hợp lệ cùng đơn vị, phép cộng `BigDecimal` có tính kết hợp về **giá trị toán học**, vì đây là phép cộng thập phân chính xác, không có sai số làm tròn trong `BigDecimal.add` khi không áp đặt `MathContext` làm tròn.
- Mapper không sửa đối tượng nguồn, không cập nhật biến dùng chung.

**Giới hạn nghiệp vụ:** Dữ liệu có nhiều loại tiền cần được quy đổi theo tỷ giá và quy tắc làm tròn thích hợp **trước khi cộng**, hoặc nhóm theo đơn vị tiền tệ bằng collector. Đừng lấy `Money(0, "VND")` làm identity cho dữ liệu hỗn hợp USD/VND rồi bỏ qua việc quy đổi.

### 5.1. Reduce không có identity khi không thể chọn giá trị không mặc định

Nếu đơn vị tiền tệ của nguồn chỉ được xác định từ chính phần tử đầu tiên, không cần “đoán” identity:

~~~java
import java.util.Optional;

// payments là List<Money> ở ví dụ MoneyReduce.
Optional<Money> total = payments.stream()
    .reduce(Money::plus);
~~~

Khi `payments` rỗng, kết quả là `Optional.empty()`. Ứng dụng có thể giữ trạng thái “không có khoản tiền”, yêu cầu cung cấp đơn vị tiền tệ mặc định, hoặc ném lỗi nếu một giao dịch bắt buộc phải có khoản tiền.

Không thay `Optional.empty()` bằng một khoản tiền giả nếu điều đó làm mất thông tin kinh doanh.

### 5.2. Lưu ý về BigDecimal

`BigDecimal.add` không tự đổi đơn vị tiền tệ. Ngoài ra, `BigDecimal.equals` phân biệt cả **scale**:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true: cùng giá trị số.
System.out.println(a.equals(b));         // false: scale khác nhau.
~~~

Nếu hệ thống yêu cầu biểu diễn tiền có scale nhất quán, hãy đặt chính sách chuẩn hóa ở tầng value object hoặc ranh giới nhập dữ liệu. Đừng suy luận từ một lần in ra rằng mọi định dạng đều được bảo toàn theo ý nghĩa mong muốn.

## 6. Từ bản ghi đầu vào thành kết quả tổng hợp khác kiểu

Một chương trình có thể cần báo cáo nhiều chỉ tiêu trong một lần duyệt: tổng số dòng đơn hàng, số sản phẩm và doanh thu. Phần tử nguồn là `OrderLine`, còn giá trị tích lũy là `SalesSummary`. Đây là trường hợp phù hợp với **reduce ba tham số**.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class SalesSummaryReduce {
    record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        BigDecimal lineTotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record SalesSummary(
        long lineCount,
        long units,
        BigDecimal revenue
    ) {
        static SalesSummary zero() {
            return new SalesSummary(0L, 0L, BigDecimal.ZERO);
        }

        SalesSummary add(OrderLine line) {
            return new SalesSummary(
                lineCount + 1,
                units + line.quantity(),
                revenue.add(line.lineTotal())
            );
        }

        SalesSummary combine(SalesSummary other) {
            return new SalesSummary(
                lineCount + other.lineCount(),
                units + other.units(),
                revenue.add(other.revenue())
            );
        }
    }

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 2, new BigDecimal("19.90")),
            new OrderLine("PEN", 3, new BigDecimal("5.25"))
        );

        SalesSummary summary = lines.parallelStream().reduce(
            SalesSummary.zero(), // identity: trạng thái tổng hợp rỗng.
            SalesSummary::add,    // accumulator: đưa OrderLine vào Summary.
            SalesSummary::combine // combiner: gộp hai Summary.
        );

        System.out.println(summary);
        // SalesSummary[lineCount=2, units=5, revenue=55.55]
    }
}
~~~

Giải thích từng thành phần:

1. `SalesSummary.zero()` tạo một kết quả rỗng: 0 dòng, 0 đơn vị, 0 doanh thu.
2. `SalesSummary::add` là `BiFunction<SalesSummary, OrderLine, SalesSummary>`. Hàm tạo một đối tượng mới sau khi nhập thêm một dòng.
3. `SalesSummary::combine` là `BinaryOperator<SalesSummary>`. Nó ghép kết quả do các nhánh khác nhau tạo ra.
4. Cả hai phép toán đều giữ trạng thái bất biến, không phụ thuộc lịch chạy của parallel stream.

Nếu `a` là một summary bất kỳ và `line` là một dòng đơn, thì:

~~~text
combine(a, add(zero, line)) = add(a, line)
~~~

Hai phía đều cộng thêm đúng một dòng, đúng số lượng của dòng đó và đúng thành tiền. Đây là **điều kiện tương thích** giữa accumulator và combiner.

**Lưu ý:** Ví dụ giả định `quantity` không âm, `unitPrice` hợp lệ và tất cả giá trị tiền có cùng đơn vị. Trong hệ thống thực cần kiểm tra dữ liệu đầu vào, giới hạn phép cộng số `long` và chính sách quy đổi/làm tròn trước khi kết luận tổng hợp là hợp lệ.

### 6.1. Biến thể tuần tự

~~~java
// Trong ngữ cảnh lớp SalesSummaryReduce với List<OrderLine> lines:
SalesSummary summary = lines.stream().reduce(
    SalesSummary.zero(),
    SalesSummary::add,
    SalesSummary::combine
);
~~~

Dạng ba tham số cũng chạy tuần tự. Tuy nhiên, thiết kế vẫn phải đáp ứng hợp đồng combiner vì mã có thể chuyển sang parallel stream hoặc được tái sử dụng với nguồn khác.

### 6.2. Khi chỉ cần một đại lượng

Nếu yêu cầu chỉ là tổng doanh thu, việc dựng `SalesSummary` nhiều trường có thể không cần thiết:

~~~java
import java.math.BigDecimal;

// OrderLine đã được định nghĩa trong lớp ví dụ phía trên.
BigDecimal total = lines.stream()
    .map(OrderLine::lineTotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Với dữ liệu lớn, lựa chọn giữa primitive terminal, `reduce` và `collect` phụ thuộc vào kiểu giá trị, khả năng tổng hợp và chi phí tạo đối tượng. Không cần một summary phức tạp nếu đầu ra chỉ là một tổng đơn giản.

## 7. Gộp nhiều chỉ tiêu số và xử lý tập rỗng

Giả sử một lớp học cần thống kê số bài đã chấm, tổng điểm, điểm nhỏ nhất, lớn nhất và điểm trung bình. Ta có thể dùng **một record bất biến** với phép `add` và `merge`.

~~~java
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class ScoreStatisticsReduce {
    record Stats(long count, long sum, int min, int max) {
        static Stats empty() {
            return new Stats(
                0L,
                0L,
                Integer.MAX_VALUE,
                Integer.MIN_VALUE
            );
        }

        Stats add(int score) {
            return new Stats(
                count + 1,
                sum + score,
                Math.min(min, score),
                Math.max(max, score)
            );
        }

        Stats merge(Stats other) {
            return new Stats(
                count + other.count(),
                sum + other.sum(),
                Math.min(min, other.min()),
                Math.max(max, other.max())
            );
        }

        OptionalDouble average() {
            return count == 0
                ? OptionalDouble.empty()
                : OptionalDouble.of((double) sum / count);
        }

        OptionalInt minimum() {
            return count == 0
                ? OptionalInt.empty()
                : OptionalInt.of(min);
        }

        OptionalInt maximum() {
            return count == 0
                ? OptionalInt.empty()
                : OptionalInt.of(max);
        }
    }

    public static void main(String[] args) {
        List<Integer> scores = List.of(8, 5, 9, 6);

        Stats stats = scores.parallelStream().reduce(
            Stats.empty(),
            Stats::add,
            Stats::merge
        );

        System.out.println(stats.count()); // 4
        System.out.println(stats.sum()); // 28
        System.out.println(stats.minimum().orElseThrow()); // 5
        System.out.println(stats.maximum().orElseThrow()); // 9
        System.out.println(stats.average().orElseThrow()); // 7.0

        Stats empty = List.<Integer>of().stream().reduce(
            Stats.empty(),
            Stats::add,
            Stats::merge
        );

        System.out.println(empty.count()); // 0
        System.out.println(empty.average()); // OptionalDouble.empty
    }
}
~~~

`Integer.MAX_VALUE` và `Integer.MIN_VALUE` ở đây chỉ là **giá trị trung hòa nội bộ** để hàm `Math.min` và `Math.max` có thể kết hợp với summary rỗng. Chúng **không** được công bố như số liệu thực khi `count == 0`. Hai phương thức `minimum()` và `maximum()` trả Optional để biểu diễn việc không có quan sát.

Nếu chỉ cần các thống kê `count/sum/min/max/average` cho số nguyên, Java đã có giải pháp chuyên dụng:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;

IntSummaryStatistics stats = List.of(8, 5, 9, 6).stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 28
System.out.println(stats.getMin());     // 5
System.out.println(stats.getMax());     // 9
System.out.println(stats.getAverage()); // 7.0
~~~

Trong ứng dụng thông thường, **ưu tiên operation/collector có sẵn** khi chúng đã đáp ứng chính xác đầu ra. Dùng record với `reduce` khi có thêm chỉ tiêu miền nghiệp vụ hoặc kết quả tổng hợp cần kiểu riêng.

## 8. Nối chuỗi và reduce khi chạy song song

Một số phép gộp **có tính kết hợp nhưng không giao hoán**. Ví dụ nối chuỗi:

~~~text
"a" + "b" = "ab"
"b" + "a" = "ba"
~~~

Phép nối có tính kết hợp về cấu trúc chuỗi, nhưng đổi **thứ tự phần tử** sẽ đổi kết quả. Với ordered stream và phép rút gọn đúng hợp đồng, parallel reduce vẫn phải bảo toàn ngữ nghĩa thứ tự tương ứng. Ta không cần các callback chạy theo đúng trình tự thời gian; kết quả cuối phụ thuộc **encounter order**, không phụ thuộc lịch xử lý thread.

~~~java
import java.util.List;

List<String> letters = List.of("J", "A", "V", "A");

String text = letters.parallelStream()
    .reduce("", String::concat);

System.out.println(text); // JAVA
~~~

Nếu gọi `unordered()` trước đó, ta bỏ ràng buộc encounter order. Đối với phép nối phụ thuộc vị trí, **không nên dựa vào kết quả luôn là "JAVA"**.

~~~java
String textWithoutOrder = letters.parallelStream()
    .unordered()
    .reduce("", String::concat);

// textWithoutOrder chứa các chữ cái đã ghép;
// thứ tự ký tự không còn là một bảo đảm của pipeline.
~~~

Nếu nghiệp vụ cần một chuỗi đã sắp xếp, phải thiết lập thứ tự rõ ràng trước khi nối:

~~~java
String sortedText = letters.parallelStream()
    .sorted()
    .collect(java.util.stream.Collectors.joining());

System.out.println(sortedText); // AAJV
~~~

### 8.1. Tác dụng phụ không thay thế giá trị kết quả

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> shared = new ArrayList<>();

String text = List.of("a", "b", "c").parallelStream()
    .reduce(
        "",
        (acc, value) -> {
            shared.add(value); // SAI: mutation ngoài reduce, không thread-safe.
            return acc + value;
        }
    );
~~~

Trong ví dụ này, kết quả `text` là đầu ra của `reduce`, còn `shared` là tác dụng phụ ngoài hợp đồng. Với parallel stream, việc ghi `ArrayList` dùng chung có thể tạo race condition. Đừng dùng callback của `reduce` để thu thập phần tử vào danh sách; nên để terminal operation hoặc collector phù hợp tạo kết quả.

### 8.2. Những việc không được đưa vào accumulator

Không nên cập nhật cơ sở dữ liệu, gửi email, ghi file hoặc tăng bộ đếm nghiệp vụ trong accumulator chỉ để “bảo đảm xử lý từng phần tử”. Khi pipeline song song, accumulator và combiner có thể được gọi theo lịch khác với tuần tự. Công việc yêu cầu giao dịch hoặc side effect cần được tổ chức riêng, với điều kiện idempotency và xử lý lỗi tương ứng.

## 9. Sai lầm nghiêm trọng: reduce với identity mutable

Một đoạn mã nhìn qua có thể “đúng” khi tuần tự:

~~~java
import java.util.ArrayList;
import java.util.List;

// MINH HỌA CÁCH SAI: không dùng cho pipeline thật.
List<String> broken = List.of("a", "b", "c").parallelStream()
    .reduce(
        new ArrayList<String>(),
        (acc, item) -> {
            acc.add(item);  // Sửa identity mutable dùng chung.
            return acc;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

`reduce` yêu cầu phép tích lũy **không can thiệp, không trạng thái**, và identity phải hoạt động như phần tử đơn vị. Với identity là một `ArrayList` mutable được chia sẻ giữa các phần tính toán, accumulator liên tục sửa cùng đối tượng. Các nhánh có thể đua nhau ghi, còn combiner có thể nhận các tham chiếu trỏ đến cùng một list. Kết quả sai hoặc hành vi bất thường là điều có thể xảy ra.

Để thu thập danh sách, dùng `collect`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> good = List.of("a", "b", "c").parallelStream()
    .collect(Collectors.toList());
~~~

Nếu cần một `ArrayList` có thể thay đổi được:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

ArrayList<String> mutable = List.of("a", "b", "c").parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));
~~~

Collectors tạo những container tích lũy theo hợp đồng của cơ chế reduction có thể thay đổi (*mutable reduction*) rồi kết hợp chúng theo cách thích hợp. Đây là nhiệm vụ của `collect`, không nên mô phỏng bằng cách sửa identity trong `reduce`.

## 10. Những giới hạn số học dễ làm reduce sai

### 10.1. Cộng số nguyên có thể tràn

~~~java
import java.util.List;

int wrapped = List.of(Integer.MAX_VALUE, 1).stream()
    .reduce(0, Integer::sum);

// wrapped == Integer.MIN_VALUE do tràn số int.
~~~

Nếu miền giá trị có thể lớn, chọn kiểu phù hợp và kiểm soát overflow:

~~~java
long safe = List.of(Integer.MAX_VALUE, 1).stream()
    .mapToLong(Integer::longValue)
    .sum();

// safe == 2147483648
~~~

`long` vẫn có giới hạn. `Math.addExact` có thể phát hiện overflow, còn `BigInteger` / `BigDecimal` phù hợp khi yêu cầu kết quả vượt miền primitive. Với các phép cộng có thể overflow nhưng tổng toán học cuối cùng vừa miền, kết quả hoặc ngoại lệ còn có thể phụ thuộc cách phân nhóm; không tự động coi phép cộng có kiểm tra overflow là phép gộp song song an toàn cho mọi miền đầu vào.

### 10.2. Số thực dấu chấm động không kết hợp tuyệt đối

Về mặt toán học, cộng là phép kết hợp. Với số thực dấu chấm động IEEE 754, việc làm tròn có thể khiến:

~~~text
(a + b) + c  !=  a + (b + c)
~~~

Ví dụ:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double left = (a + b) + c;  // 1.0
double right = a + (b + c); // 0.0

System.out.println(left == right); // false
~~~

Vì vậy, `DoubleStream.sum()` và các cách reduce số thực có thể cho chênh lệch làm tròn phụ thuộc cách tích lũy/nhóm phần tử. Khi cần kết quả có độ chính xác chặt chẽ, phải cân nhắc cấu trúc số liệu, sai số chấp nhận được và thuật toán tổng hợp chuyên dụng. Không dùng `double` làm đại diện mặc định cho tiền cần chính xác thập phân.

### 10.3. Kết hợp không đúng hoặc phụ thuộc state

Một phép toán như “lấy trung bình của hai giá trị trung bình” không tạo trung bình đúng khi các nhóm có kích thước khác nhau:

~~~text
Nhóm A: [10, 20, 30]  → trung bình 20
Nhóm B: [100]         → trung bình 100

Trung bình hai trung bình = (20 + 100) / 2 = 60    (sai)
Trung bình toàn bộ       = (10 + 20 + 30 + 100)/4 = 40 (đúng)
~~~

Để gộp trung bình đúng, phải giữ ít nhất **tổng** và **số lượng** trong bản tổng hợp, rồi tính trung bình sau khi kết thúc reduction. Đó là lý do record kiểu `Stats(count, sum, ...)` đáng tin hơn chỉ lưu một giá trị `average`.

## 11. reduce hay collect? Chọn theo bản chất kết quả

`reduce` dùng cách gộp giá trị, thường thích hợp với những đối tượng **bất biến** và phép kết hợp có identity rõ ràng. `collect` dùng cơ chế tích lũy vào container có thể thay đổi được thông qua supplier, accumulator và combiner.

| Yêu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Cộng các số `int`/`long` | `mapToInt(...).sum()`, `mapToLong(...).sum()` | Dùng primitive terminal, tránh boxing. |
| Nối một vài chuỗi để hiểu phép gộp | `reduce("", String::concat)` | Identity và associative rõ ràng. |
| Ghép văn bản lớn có phân cách | `Collectors.joining(...)` | Hỗ trợ tích lũy chuỗi hiệu quả. |
| Cộng các `Money` bất biến cùng tiền tệ | `reduce(zero, Money::plus)` | Đúng ngữ nghĩa value object. |
| Kết quả record có nhiều chỉ tiêu riêng | `reduce(identityU, accumulator, combiner)` | Trực tiếp tạo kết quả tổng hợp bất biến. |
| Thống kê số học chuẩn | `summaryStatistics()`, `summarizingLong(...)` | Thư viện đã cung cấp giải pháp phù hợp. |
| Tạo `List` hoặc `Map` | `collect(toList())`, `collect(toMap(...))` | Có cơ chế mutable accumulation phù hợp. |
| Gom theo nhóm khóa | `groupingBy(...)` / `groupingByConcurrent(...)` khi phù hợp | Bản chất là gom nhiều kết quả theo nhóm. |

Nếu một `reduce` tạo ra nhiều đối tượng trung gian bất biến và hiệu năng trở thành vấn đề, có thể cân nhắc một collector tùy chỉnh. Tuy nhiên, collector cũng phải bảo đảm các quy tắc identity/associativity tương ứng, và characteristics như `CONCURRENT` chỉ nên khai báo khi accumulator/container thực sự cho phép cập nhật đồng thời theo hợp đồng.

Trong thực hành xử lý song song, **đúng kết quả** luôn cần được chứng minh trước khi đo tốc độ.

## 12. Vòng đời Stream, nguồn rỗng và null

### 12.1. reduce kích hoạt pipeline lazy

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = List.of(2, 4, 6).stream()
    .filter(n -> n > 2)
    .map(n -> n * 10);

// Đến đây chưa cần xử lý phần tử.
int total = pipeline.reduce(0, Integer::sum); // 100
~~~

`reduce` là terminal operation; sau khi gọi, `pipeline` đã được sử dụng và không được thực hiện terminal operation khác trên chính Stream đó. Với nguồn hữu hạn, reduction thường phải duyệt đủ dữ liệu còn lại để tính kết quả; với Stream vô hạn không giới hạn, một phép reduce kiểu tính tổng có thể không bao giờ kết thúc.

### 12.2. Tránh null trong phần tử và kết quả gộp

Với `reduce(BinaryOperator)`, một kết quả trung gian `null` không biểu diễn “không có kết quả” đúng nghĩa; nó có thể gây `NullPointerException`. Nếu dữ liệu đầu vào chứa null hoặc logic gộp có thể trả null, hãy xác định chính sách lọc hoặc chuyển đổi trước khi reduce.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> words = Arrays.asList("Java", null, "Stream");

String text = words.stream()
    .filter(Objects::nonNull)
    .reduce("", String::concat);

System.out.println(text); // JavaStream
~~~

Không chọn `null` làm identity để “tiết kiệm” việc thiết kế phần tử đơn vị. Identity phải là giá trị hợp lệ, trung hòa đối với phép gộp.

### 12.3. Nguồn tài nguyên vẫn phải được đóng

Với Stream từ file:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countChars(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
            .mapToLong(String::length)
            .sum();
    }
}
~~~

Đây là ví dụ sử dụng `sum()` thay vì `reduce` vì chỉ cần tổng độ dài. Quan trọng là `try-with-resources` quản lý tài nguyên do `Files.lines` nắm giữ. `reduce` hay terminal operation khác không thay thế nghĩa vụ đóng tài nguyên nguồn.

## 13. Kiểm tra tính đúng của một phép reduction

Trước khi chuyển từ tuần tự sang song song, hãy kiểm tra các tính chất có thể thử bằng dữ liệu nhỏ:

1. **Identity:** Gộp với identity ở hai phía vẫn ra cùng giá trị.
2. **Associativity:** Cách đặt nhóm khác nhau vẫn cho cùng kết quả theo mô hình số học/miền dữ liệu đã chọn.
3. **Compatibility:** Với reduce ba tham số, xử lý một phần tử riêng rồi combine bằng xử lý phần tử đó trực tiếp trên summary hiện có.
4. **Nguồn rỗng:** Có trả identity hoặc Optional.empty đúng ý nghĩa nghiệp vụ?
5. **Tính độc lập:** Mapper/accumulator/combiner có tránh sửa nguồn và state mutable chia sẻ?
6. **Phạm vi giá trị:** Có overflow, làm tròn hoặc giới hạn kiểu số cần kiểm soát?
7. **Thứ tự:** Phép gộp có nhạy thứ tự không? Nếu có, nguồn và pipeline có encounter order không?

Ví dụ minh họa ba bất biến cho `String::concat`:

~~~java
public class ReduceLawsCheck {
    public static void main(String[] args) {
        String a = "Java";
        String b = " Stream";
        String c = " API";
        String e = "";

        if (!e.concat(a).equals(a) || !a.concat(e).equals(a)) {
            throw new AssertionError("Identity không hợp lệ");
        }

        String left = a.concat(b).concat(c);
        String right = a.concat(b.concat(c));
        if (!left.equals(right)) {
            throw new AssertionError("Phép gộp không kết hợp");
        }

        System.out.println(left); // Java Stream API
    }
}
~~~

Ví dụ này kiểm tra trường hợp minh họa, không phải chứng minh hình thức cho mọi giá trị đầu vào. Với phép gộp nghiệp vụ, cần kiểm thử nhiều trường hợp biên: rỗng, một phần tử, giá trị trùng, giá trị lớn, nhóm có kích thước lệch, và phép gộp thứ tự khác nhau.

## 14. Câu hỏi tự kiểm tra

1. **`reduce("", String::concat)` trả gì khi Stream rỗng?** Chuỗi rỗng vì `""` là identity.
2. **`reduce(String::concat)` trả gì khi Stream rỗng?** `Optional.empty()` vì không có identity.
3. **Tại sao `reduce(10, Integer::sum)` không phù hợp để tính tổng thông thường?** Vì `10` không phải identity của phép cộng; kết quả bị cộng thêm giá trị đó.
4. **Nối chuỗi có kết hợp không? Có giao hoán không?** Có tính kết hợp theo thứ tự ký tự; không giao hoán vì `"ab"` khác `"ba"`.
5. **Vì sao StringBuilder mutable không nên làm identity của `reduce`?** Accumulator sửa đối tượng dùng chung, vi phạm hợp đồng rút gọn và có thể gây race/ghép sai khi chạy song song.
6. **Khi nguồn là `Stream<OrderLine>` nhưng kết quả là `SalesSummary`, dùng overload nào?** `reduce(identityU, accumulator, combiner)`.
7. **Combiner của reduce ba tham số dùng để làm gì?** Ghép hai kết quả tích lũy kiểu `U`, nhất là khi xử lý các nhánh song song.
8. **Tính trung bình bằng cách lấy trung bình của các trung bình nhóm có đúng không?** Không nói chung; cần mang theo tổng và số lượng của từng nhóm.
9. **Khi xử lý tập điểm rỗng, nên trả min/max bằng một giá trị sentinel như dữ liệu thật không?** Không; nên trả Optional hoặc kiểu kết quả giữ trạng thái không có quan sát.
10. **Khi chỉ cần nối một danh sách lớn với dấu phẩy, chọn `reduce` hay `Collectors.joining`?** Thường dùng `Collectors.joining`.
11. **Có thể dùng `unordered()` trước reduce nối chuỗi mà vẫn đòi kết quả theo thứ tự nguồn không?** Không; `unordered` loại bỏ bảo đảm encounter order.
12. **Tại sao cộng `double` khi parallel có thể chênh lệch so với tuần tự?** Do phép cộng dấu chấm động có sai số làm tròn và không kết hợp tuyệt đối.
13. **Khi nào cần BigDecimal trong value object?** Khi miền nghiệp vụ yêu cầu giá trị thập phân chính xác, kết hợp với chính sách scale và đơn vị tiền tệ rõ ràng.
14. **Một Stream đã chạy `reduce` có dùng lại để gọi `count` được không?** Không; cần tạo một Stream mới từ nguồn.
15. **Nếu kết quả là một `List` có thể thay đổi, có nên dùng reduce với ArrayList identity không?** Không; dùng `collect` với collector phù hợp.

**Ghi nhớ:** `reduce` là phép rút gọn **từ nhiều phần tử thành một giá trị**: chuỗi, value object hoặc một summary bất biến. Hãy chọn đúng overload, định nghĩa identity trung hòa, bảo đảm tính kết hợp và compatibility của accumulator/combiner, rồi tính đến hiệu năng. Dùng `collect` khi cần mutable reduction, giữ `Optional` khi nguồn rỗng có ý nghĩa, và kiểm soát giới hạn số học khi tổng hợp dữ liệu lớn hoặc chạy song song.
