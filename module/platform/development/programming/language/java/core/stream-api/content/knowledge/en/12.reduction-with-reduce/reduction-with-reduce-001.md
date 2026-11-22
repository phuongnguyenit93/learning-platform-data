# Tư duy rút gọn dữ liệu và lựa chọn reduce

Khi xử lý dữ liệu bằng Java Stream API, nhiều bài toán không cần trả về toàn bộ tập phần tử. Ta chỉ muốn **một kết quả tổng hợp**: tổng tiền, điểm cao nhất, chuỗi mô tả, giá trị gộp theo quy tắc nghiệp vụ hoặc một trạng thái có thể kết hợp. Tư duy này gọi là **rút gọn** (*reduction*): biến một dãy nhiều phần tử thành một giá trị kết quả.

Bài học thuộc chương **Phép rút gọn với reduce** của module `JAVA_STREAM_API`. Mục tiêu là hiểu ý nghĩa của phép gộp, cách chọn giá trị khởi tạo, tính kết hợp để chạy đúng trên parallel stream, và đặc biệt **khi nào nên dùng `reduce` thay vì `collect` hoặc một terminal operation chuyên dụng**. Kiến thức này kết nối trực tiếp với các pipeline lazy, `filter`, `map`, `collect` và những giới hạn về trạng thái, độ chính xác số học, tài nguyên và hiệu năng.

## 1. Rút gọn là gì?

Giả sử có các giá trị `[3, 5, 7, 9]` và muốn tính tổng. Ta có thể hình dung việc gộp dần:

```text
Dữ liệu đầu vào: 3, 5, 7, 9

Giá trị ban đầu = 0
       │
       ├─ kết hợp 3 → 3
       ├─ kết hợp 5 → 8
       ├─ kết hợp 7 → 15
       └─ kết hợp 9 → 24

Kết quả: 24
```

Với Java Stream API:

```java
import java.util.stream.Stream;

int total = Stream.of(3, 5, 7, 9)
        .reduce(0, Integer::sum);

System.out.println(total); // 24
```

Trong ví dụ trên, `0` là **giá trị đồng nhất** (*identity*) của phép cộng; `Integer::sum` là **phép kết hợp** (*accumulator*) giữa kết quả tạm và phần tử tiếp theo. `reduce` là terminal operation: nó **tiêu thụ** pipeline, trả về một giá trị và không cho phép sử dụng lại cùng instance Stream.

Có thể mô tả trực quan:

```text
Stream<T> ── filter / map / ... ── reduce(identity, operator) ──► T
                    intermediate          terminal
```

Tuy nhiên, mô hình “đi từ trái sang phải, cộng lần lượt” chỉ là một cách **giải thích dễ hiểu**. Với parallel stream, Java có thể chia dữ liệu thành nhiều nhánh, rút gọn từng nhánh rồi kết hợp các kết quả nhánh. Vì thế không được dựa vào thứ tự gọi thực tế của lambda khi viết phép rút gọn.

## 2. Ba biến thể reduce phổ biến của Stream<T>

`Stream<T>` định nghĩa ba overload chính:

| Dạng gọi | Dạng kết quả | Sử dụng khi |
| --- | --- | --- |
| `reduce(BinaryOperator<T> accumulator)` | `Optional<T>` | Không có identity tự nhiên, cần phân biệt Stream rỗng |
| `reduce(T identity, BinaryOperator<T> accumulator)` | `T` | Phép gộp có identity và đầu ra cùng kiểu phần tử |
| `reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)` | `U` | Kết quả khác kiểu phần tử; cần cách gộp các kết quả từng nhánh |

Cả ba đã có từ **Java 8**. Các ví dụ sau tách riêng mỗi dạng để tránh nhầm lẫn về tình huống đầu vào rỗng và đặc tính chạy song song.

### 2.1. reduce không truyền identity: trả Optional<T>

Tìm số lớn nhất mà không tự chọn một “giá trị nhỏ nhất giả định”:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> scores = Arrays.asList(5, 12, 8);

Optional<Integer> highest = scores.stream()
        .reduce(Integer::max);

System.out.println(highest); // Optional[12]
```

Nếu nguồn rỗng, kết quả là `Optional.empty()`, bởi không có phần tử nào để rút gọn:

```java
Optional<Integer> absent = java.util.stream.Stream
        .<Integer>empty()
        .reduce(Integer::max);

System.out.println(absent.isPresent()); // false
```

Không nên gọi `get()` khi chưa kiểm tra sự tồn tại. Có thể dùng `orElse`, `orElseThrow` hoặc xử lý bằng `ifPresent` tùy hợp đồng nghiệp vụ.

### 2.2. reduce có identity: luôn trả về T

```java
int sum = Arrays.asList(5, 12, 8).stream()
        .reduce(0, Integer::sum);

int emptySum = java.util.stream.Stream.<Integer>empty()
        .reduce(0, Integer::sum);

System.out.println(sum);      // 25
System.out.println(emptySum); // 0
```

`identity` không nhất thiết “là phần tử đầu tiên”, mà phải là **giá trị trung tính thực sự** của phép gộp: kết hợp nó với bất kỳ kết quả nào cũng giữ nguyên kết quả đó. Với phép cộng số nguyên, đó là `0`; với phép nhân, đó là `1`; với phép nối chuỗi, đó là chuỗi rỗng `""`.

### 2.3. reduce ba tham số: kết quả kiểu U

Khi phần tử đầu vào kiểu `T`, nhưng kết quả rút gọn kiểu `U`, Java có overload:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
)
```

Ví dụ tính tổng **độ dài chuỗi** thành một `long`:

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("Java", "Stream", "API");

long totalLength = words.stream()
        .reduce(
                0L,
                (length, word) -> length + word.length(),
                Long::sum
        );

System.out.println(totalLength); // 13
```

Ở đây:

- `identity = 0L` là một kết quả kiểu `Long` trung tính.
- `accumulator` gộp kết quả kiểu `Long` với phần tử `String`.
- `combiner` gộp **hai kết quả kiểu `Long`**; nó cần thiết để hợp nhất các nhánh parallel.

Để tính tổng độ dài, cách thường **dễ đọc và hiệu quả về kiểu dữ liệu hơn** là ánh xạ sang `IntStream` rồi dùng `sum`:

```java
int lengthSum = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(lengthSum); // 13
```

Ví dụ ba tham số giúp hiểu hợp đồng của `reduce`; không có nghĩa đây là lựa chọn tốt nhất cho mọi phép tính khác kiểu.

## 3. Tư duy đúng: chọn phép gộp trước khi chọn API

Bước quan trọng nhất không phải là nhớ cú pháp `reduce` mà là xác định phép toán:

1. **Đầu ra là gì?** Một số, một chuỗi, một giá trị tối ưu, hay một cấu trúc có nhiều trường?
2. **Hai kết quả từng phần có thể gộp thành một kết quả tương đương không?**
3. **Có giá trị trung tính phù hợp không?**
4. **Nguồn rỗng nên cho kết quả nào?** Giá trị mặc định hay “không tồn tại”?
5. **Có API chuyên dụng hoặc Collector phù hợp hơn không?**

Một số phép toán mẫu:

| Nhu cầu | Phép gộp | Identity nếu dùng reduce có identity | API thường nên xét trước |
| --- | --- | --- | --- |
| Tổng số nguyên | Cộng | `0` | `IntStream.sum()` |
| Tích số nguyên | Nhân | `1` | `reduce(1, (a,b) -> a*b)` |
| Giá trị lớn nhất | `max` | Không cần tự chọn | `max(Comparator)` / `IntStream.max()` |
| Tất cả điều kiện đúng | Logic AND | `true` | `allMatch(predicate)` |
| Ít nhất một điều kiện đúng | Logic OR | `false` | `anyMatch(predicate)` |
| Ghép chuỗi | Nối | `""` | `Collectors.joining(...)` |
| Gom các phần tử vào List | Thêm phần tử | Bộ chứa mutable | `collect(Collectors.toList())` |
| Gom theo khóa | Tính nhóm | Map mutable | `collect(Collectors.groupingBy(...))` |

Hai hàng điều kiện logic là một khác biệt quan trọng: có thể rút gọn các `Boolean` bằng AND/OR, nhưng `allMatch` và `anyMatch` thường tốt hơn vì **short-circuit** khi đã đủ thông tin.

## 4. Identity phải thực sự trung tính

Với một phép toán gộp ký hiệu là `⊕`, identity `e` phải đáp ứng:

```text
e ⊕ x = x
x ⊕ e = x
```

Nếu không thỏa, kết quả có thể sai ngay cả với Stream tuần tự, và càng dễ sai khi Java tạo nhiều nhánh parallel.

### Ví dụ sai: lấy 0 làm identity cho giá trị lớn nhất

```java
List<Integer> temperatures = Arrays.asList(-7, -3, -11);

int wrongMax = temperatures.stream()
        .reduce(0, Integer::max);

System.out.println(wrongMax); // 0, không xuất hiện trong nguồn!
```

`0` **không** trung tính với phép lấy lớn nhất trên toàn bộ miền số nguyên, vì `max(0, -7) = 0` thay vì `-7`. Để biểu diễn “không có giá trị nếu nguồn rỗng”, dùng:

```java
Optional<Integer> correctMax = temperatures.stream()
        .reduce(Integer::max);

System.out.println(correctMax); // Optional[-3]
```

Nếu chắc chắn mọi số là `int` và muốn một identity hợp lệ cho phép max trên toàn miền `int`, có thể chọn `Integer.MIN_VALUE`, nhưng lúc này nguồn rỗng cũng trả `Integer.MIN_VALUE`. Điều đó có thể khiến caller nhầm giá trị thật với giá trị mặc định; trong nhiều trường hợp, `OptionalInt` hoặc `Optional<Integer>` phù hợp hơn.

### Ví dụ với phép nhân

```java
int product = Arrays.asList(2, 3, 4).stream()
        .reduce(1, (a, b) -> a * b);

System.out.println(product); // 24
```

Identity đúng là `1`, bởi `1 * x = x`. Nếu dùng `0`, mọi kết quả sẽ thành 0. Lưu ý `int` vẫn có thể tràn khi tích quá lớn.

## 5. Associativity: điều kiện để kết hợp theo nhiều nhánh

Một phép gộp là **có tính kết hợp** (*associative*) nếu:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

Đây là điều kiện cốt lõi để Java có thể phân hoạch Stream, rút gọn từng phần và kết hợp mà không làm đổi ý nghĩa kết quả.

Phép cộng số nguyên có tính kết hợp theo số học nguyên (xét kết quả trong miền biểu diễn kiểu số); phép nối chuỗi cũng có tính kết hợp:

```text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
```

Ngược lại, phép trừ **không có tính kết hợp**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Vì thế:

```java
// KHÔNG phù hợp cho phép rút gọn yêu cầu kết quả nhất quán khi parallel.
int result = Arrays.asList(10, 3, 2).stream()
        .reduce(0, (a, b) -> a - b);
```

Với pipeline tuần tự, đoạn này có thể cho giá trị cụ thể từ cách duyệt tuần tự, nhưng không đáp ứng hợp đồng toán học để thay đổi cách chia nhánh; không nên dùng nó như một phép reduce có thể song song hóa.

**Tính kết hợp khác với tính giao hoán**. Nối chuỗi có tính kết hợp nhưng `"AB"` khác `"BA"`, nên không giao hoán. `reduce` không đòi phép gộp phải giao hoán trong mọi trường hợp; với Stream có encounter order, vẫn cần giữ thứ tự logic để đạt kết quả đúng theo hợp đồng. Nếu muốn cho phép thay đổi thứ tự, phép gộp cũng phải phù hợp với yêu cầu đó.

### Số thực và sai số

`double` không bảo đảm kết hợp tuyệt đối do làm tròn:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Khi dùng `reduce` để cộng số thực, thứ tự nhóm có thể làm sai khác chữ số thấp, đặc biệt với parallel stream. Đây là giới hạn số học, không chỉ là vấn đề API. Nếu xử lý tiền tệ cần số thập phân chính xác, cân nhắc `BigDecimal` và quy tắc scale/làm tròn rõ ràng; nếu tính thống kê số thực, cân nhắc các thuật toán cộng ổn định hoặc `DoubleStream.sum()` với hợp đồng độ chính xác phù hợp.

## 6. reduce và collect: bất biến hay thay đổi trạng thái?

Một phân biệt quan trọng trong Java Stream API:

- `reduce` thường phù hợp với **immutable reduction**: mỗi bước tạo/trả **giá trị kết quả mới**, không sửa đối tượng kết quả chung.
- `collect` phù hợp với **mutable reduction**: các phần tử được thêm vào một container riêng (danh sách, bản đồ, bộ thống kê), rồi các container được gộp khi cần.

### Anti-pattern: dùng reduce để sửa ArrayList

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

// SAI: biến danh sách mutable thành identity của reduce.
List<String> bad = Arrays.asList("A", "B", "C").parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

Đoạn mã trên vi phạm cách sử dụng `reduce`: identity là **cùng một instance mutable** có thể bị nhiều nhánh sửa; accumulator thay đổi chính đối tượng nhận vào; combiner có thể gộp một đối tượng với chính nó. Kết quả có thể sai hoặc xảy ra vấn đề đồng thời. Đừng cho rằng thêm `parallel()` chỉ làm đoạn mã này “nhanh hơn”.

Dùng `collect`:

```java
List<String> good = Arrays.asList("A", "B", "C").parallelStream()
        .collect(java.util.stream.Collectors.toList());
```

Nếu cần xây một danh sách từ Stream nguyên thủy, sử dụng `boxed().collect(...)` hoặc `IntStream.collect(supplier, accumulator, combiner)` với bộ chứa riêng phù hợp. Chọn cơ chế tổng hợp theo hình dạng kết quả.

### So sánh hai kiểu API

| Khía cạnh | `reduce` | `collect` |
| --- | --- | --- |
| Bản chất | Kết hợp giá trị thành một kết quả | Tích lũy vào container |
| Trạng thái trung gian | Nên là kết quả bất biến hoặc không bị sửa dùng chung | Container mutable do supplier cấp |
| Kết hợp nhánh | `BinaryOperator` trả giá trị kết quả | Collector có combiner gộp container |
| Dùng cho | Tổng, tích, phép gộp giá trị nghiệp vụ, chọn cực trị | List, Set, Map, grouping, phân vùng, thống kê có trạng thái |
| Lưu ý | Identity, associativity, tính thuần | Supplier riêng, hợp đồng accumulator/combiner |

`Collectors.counting()`, `summingInt()` hoặc `reducing()` cũng là các collector, thường hữu ích khi lồng trong `groupingBy`. Đây là lý do đôi khi có thể “rút gọn” trong một collector mà không gọi trực tiếp terminal `Stream.reduce`.

## 7. Lựa chọn với Stream nguyên thủy

Khi kết quả là phép tính số học thông dụng, ưu tiên `IntStream`, `LongStream` hoặc `DoubleStream`:

```java
import java.util.Arrays;

int[] values = {3, 5, 7, 9};

int sum = Arrays.stream(values).sum();
long count = Arrays.stream(values).count();
double average = Arrays.stream(values)
        .average()
        .orElse(Double.NaN);

System.out.println(sum);     // 24
System.out.println(count);   // 4
System.out.println(average); // 6.0
```

`sum()` thường dễ đọc hơn `reduce(0, Integer::sum)`. Các primitive stream tránh boxing/unboxing cho nhiều phép xử lý, và có API `min`, `max`, `summaryStatistics` phù hợp.

Để tính một tổng có thể vượt `int`, nâng kiểu trước khi cộng:

```java
long saferSum = java.util.stream.IntStream.of(
        2_000_000_000, 2_000_000_000
).asLongStream().sum();

System.out.println(saferSum); // 4000000000
```

`asLongStream()` chuyển từng `int` thành `long` trước phép cộng. Nếu dùng `IntStream.sum()` trên cùng nguồn, có nguy cơ tràn số 32 bit; `long` cũng có giới hạn riêng.

Với bài toán tổng tiền theo số thập phân, một ví dụ `reduce` rõ ý nghĩa:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

List<BigDecimal> amounts = Arrays.asList(
        new BigDecimal("12.50"),
        new BigDecimal("7.25"),
        new BigDecimal("0.25")
);

BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 20.00
```

`BigDecimal` bất biến; `add` trả về một giá trị mới. Cần xây `BigDecimal` từ chuỗi hoặc nguồn được kiểm soát để tránh những sai khác biểu diễn do tạo trực tiếp từ literal kiểu `double`.

## 8. Một reducer nghiệp vụ tự định nghĩa

Giả sử mỗi đơn hàng có số tiền kiểu `BigDecimal` và cần lấy **tổng tiền của đơn đã thanh toán**. Để tập trung vào phép rút gọn, dùng một lớp đơn giản:

```java
import java.math.BigDecimal;

final class Order {
    private final BigDecimal amount;
    private final boolean paid;

    Order(String amount, boolean paid) {
        this.amount = new BigDecimal(amount);
        this.paid = paid;
    }

    BigDecimal amount() {
        return amount;
    }

    boolean isPaid() {
        return paid;
    }
}
```

Pipeline:

```java
import java.util.Arrays;
import java.util.List;

List<Order> orders = Arrays.asList(
        new Order("100.50", true),
        new Order("200.00", false),
        new Order("30.25", true)
);

BigDecimal paidTotal = orders.stream()
        .filter(Order::isPaid)
        .map(Order::amount)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(paidTotal); // 130.75
```

Các bước giữ trách nhiệm rõ ràng: `filter` chọn đơn đã thanh toán, `map` đưa phần tử về số tiền, `reduce` gộp những số tiền đó. Vì `BigDecimal::add` tạo giá trị mới và phép cộng với `ZERO` là trung tính, ví dụ đáp ứng hợp đồng của `reduce` với số thập phân cộng chính xác.

Nếu cần **tổng tiền theo từng trạng thái, từng cửa hàng hoặc từng khách hàng**, bài toán chuyển thành **grouping**. Khi đó `Collectors.groupingBy` kết hợp downstream collector thường diễn đạt đúng hơn một `reduce` phức tạp.

## 9. Reduce ba tham số và điều kiện tương thích giữa accumulator và combiner

Với overload `reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)`, không đủ để accumulator và combiner “trông hợp lý”. Chúng phải **phù hợp với nhau**.

Ví dụ tổng độ dài từ phần 2:

```java
long total = words.parallelStream()
        .reduce(
                0L,
                (partial, word) -> partial + word.length(),
                Long::sum
        );
```

Xét một phần từ `"Java"`, tổng độ dài tăng 4. Nếu một nhánh có tổng cục bộ là 6, việc ghép thêm kết quả của từ này phải tương đương:

```text
accumulator(6, "Java") = 10
combiner(6, accumulator(0, "Java")) = combiner(6, 4) = 10
```

Hợp đồng có thể tóm tắt:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

Đồng thời, `identity` phải trung tính với `combiner`, và `combiner` phải có tính kết hợp. Các hàm hành vi cần stateless, không sửa nguồn và không phụ thuộc những tác dụng phụ có thể thay đổi kết quả theo cách Java phân chia công việc.

Nếu viết sai combiner, pipeline tuần tự vẫn có thể “trông đúng” vì chưa cần gộp nhánh, còn parallel stream lại cho kết quả khác. Đây là lý do khi định nghĩa reducer ba tham số cần kiểm tra **cả** đường tích lũy và đường kết hợp.

## 10. Reduce có dừng sớm không? Chi phí và nguồn vô hạn

`reduce` thường cần xử lý toàn bộ những phần tử được phép đi đến nó; nó **không phải** short-circuit terminal operation như `findFirst`, `anyMatch` hoặc `allMatch`.

Ví dụ muốn biết có số âm hay không:

```java
import java.util.stream.IntStream;

boolean hasNegative = IntStream.of(5, 4, -1, 8)
        .anyMatch(n -> n < 0);

System.out.println(hasNegative); // true
```

Về mặt toán học cũng có thể rút gọn các giá trị Boolean bằng OR, nhưng `anyMatch` diễn đạt mục đích tốt hơn và có thể dừng khi thấy số âm. Với Stream vô hạn, một phép `reduce` trên toàn bộ nguồn có thể không bao giờ hoàn tất; chỉ đặt `reduce` sau một bước cắt hữu hạn phù hợp nếu muốn kết thúc.

```java
long sumFirstTen = java.util.stream.LongStream.iterate(1L, n -> n + 1)
        .limit(10)
        .sum();

System.out.println(sumFirstTen); // 55
```

Trường hợp trên `limit(10)` tạo đoạn hữu hạn trước khi tính tổng. Đừng chạy `LongStream.iterate(1L, n -> n + 1).reduce(0L, Long::sum)` nếu không có điều kiện dừng khác: nguồn vô hạn sẽ khiến phép rút gọn không kết thúc theo cách thông thường.

### Chi phí boxing và tạo object

`Stream<Integer>.reduce(...)` có thể phát sinh boxing và unboxing trong khi `IntStream.sum()` hoặc `IntStream.reduce(...)` làm việc với giá trị nguyên thủy. Rút gọn chuỗi bằng `reduce("", String::concat)` có thể tạo nhiều chuỗi trung gian và khiến chi phí phân bổ bộ nhớ tăng lên; nếu mục tiêu là ghép văn bản, `Collectors.joining` hoặc `StringBuilder` trong `collect` thường phù hợp hơn.

Không có bảo đảm “reduce luôn nhanh hơn collect”. Chọn API theo dữ liệu và cách gộp trước; khi hiệu năng thực sự quan trọng, đo trên kích thước nguồn, JDK và điều kiện parallel thực tế.

## 11. Parallel reduce: điều nên và không nên giả định

Giả sử một Stream cần tính tổng các số:

```java
long parallelSum = java.util.stream.LongStream.rangeClosed(1, 1_000_000)
        .parallel()
        .sum();

System.out.println(parallelSum); // 500000500000
```

Kết quả phép cộng `long` ở đây nằm trong miền biểu diễn nên có thể gộp các nhánh theo nhiều cách mà vẫn ra cùng tổng. Tuy vậy, parallel stream không tự động nhanh hơn; việc tách nguồn, lập lịch và kết hợp nhánh cũng có chi phí.

Các nguyên tắc thiết kế:

- **Không chia sẻ trạng thái mutable** qua biến ngoài lambda để làm “bộ tích lũy” cho `reduce`. Trạng thái ngoài có thể bị cập nhật đồng thời hoặc gây kết quả không xác định.
- **Không phụ thuộc số lần hoặc thứ tự gọi accumulator/combiner**. Java được phép phân hoạch dữ liệu khác nhau.
- **Đảm bảo identity và associativity**. Nếu kết quả phụ thuộc cách nhóm, phép gộp không thích hợp cho general-purpose reduce.
- **Cân nhắc encounter order**. Với phép gộp không giao hoán, thứ tự logic của nguồn có thể quan trọng; đừng thêm `unordered()` nếu nghiệp vụ cần thứ tự.
- **Xem xét tài nguyên**. Terminal `reduce` không tự đóng các Stream giữ tệp/kết nối; nguồn I/O vẫn cần `try-with-resources`.

Ví dụ đọc giá trị từ tệp và cộng theo đúng vòng đời nguồn:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long sumLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .map(String::trim)
                .filter(text -> !text.isEmpty())
                .mapToLong(Long::parseLong)
                .sum();
    }
}
```

Ví dụ giả định các dòng không rỗng đều là số nguyên hợp lệ. Dữ liệu sai định dạng có thể làm `Long.parseLong` ném `NumberFormatException`, nhưng `try-with-resources` vẫn đóng tệp. Nếu lỗi đọc phát sinh trong khi duyệt lazy, Java có thể bọc lỗi I/O thành `UncheckedIOException`. Với nguồn giữ tài nguyên, giải phóng đúng cách là trách nhiệm riêng, không phụ thuộc việc chọn `reduce`, `sum` hay `collect`.

## 12. Những lỗi thường gặp khi chọn reduce

| Mẫu sử dụng hoặc giả định | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `reduce(0, Integer::max)` trên số âm | Identity không trung tính | Dùng `max` hoặc `reduce(Integer::max)` trả Optional |
| `reduce(0, (a,b) -> a-b)` | Phép trừ không kết hợp được | Diễn đạt bài toán khác hoặc xử lý tuần tự theo yêu cầu cụ thể |
| `reduce(new ArrayList<>(), (list,x) -> {list.add(x); return list;}, ...)` | Biến đổi mutable identity, sai hợp đồng khi parallel | Dùng `collect` |
| `reduce("", String::concat)` để ghép văn bản rất lớn | Tạo nhiều chuỗi tạm | Dùng `Collectors.joining` |
| `reduce(...)` để kiểm tra có phần tử thỏa điều kiện | Có thể xử lý toàn bộ nguồn | Dùng `anyMatch` |
| `reduce(...)` để tìm lớn nhất/nhỏ nhất | Viết dài và dễ chọn sai identity | Dùng `max`/`min` |
| `Stream<Integer>` rồi rút gọn số học rất lớn | Boxing, giới hạn số nguyên | Dùng primitive stream hoặc kiểu số phù hợp |
| Chọn `Integer.MIN_VALUE` làm identity nhưng không tính tới nguồn rỗng | Giá trị mặc định có thể bị hiểu là dữ liệu thật | Dùng Optional nếu vắng mặt cần phân biệt |
| Dùng cùng reducer cho sequential/parallel mà thiếu associativity | Kết quả khác khi cách nhóm thay đổi | Chứng minh phép gộp có tính kết hợp |
| Terminal operation xong là đóng tệp | `reduce` không tự gọi `close` | Dùng `try-with-resources` |

## 13. Quy trình lựa chọn công cụ rút gọn

Khi gặp yêu cầu tổng hợp dữ liệu, có thể ra quyết định theo thứ tự:

1. **Có phép kết thúc chuyên dụng không?** Nếu cần `sum`, `count`, `min`, `max`, `average`, `summaryStatistics`, ưu tiên phương thức phù hợp.
2. **Có thể dừng sớm không?** Nếu tìm phần tử hoặc kiểm tra điều kiện, xét `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`.
3. **Có cần container mutable không?** Nếu muốn `List`, `Map`, grouping, partitioning hoặc chuỗi dài, xem `collect` và các `Collector` chuẩn.
4. **Nếu đúng là một giá trị rút gọn, có phép gộp hợp lệ không?** Xác định identity, associativity, ý nghĩa nguồn rỗng và kiểu kết quả.
5. **Cần kết quả khác kiểu phần tử không?** Có thể ánh xạ trước `reduce`, dùng primitive stream hoặc ba tham số nếu hợp lý.
6. **Có cần parallel không?** Kiểm tra tính tương thích giữa accumulator và combiner, tính thuần và khả năng phân hoạch nguồn.
7. **Chi phí thực tế ra sao?** Cân nhắc boxing, tạo object tạm, tràn số, sai số dấu phẩy động và chi phí đọc dữ liệu.

### Ví dụ quyết định nhanh

| Yêu cầu | Biểu thức gợi ý |
| --- | --- |
| Tổng số nguyên từ List | `numbers.stream().mapToInt(Integer::intValue).sum()` |
| Lớn nhất trong List có thể rỗng | `numbers.stream().max(Integer::compareTo)` |
| Tích các số nguyên | `numbers.stream().reduce(1, (a,b) -> a*b)` |
| Nối danh sách từ ngữ bằng dấu phẩy | `words.stream().collect(Collectors.joining(", "))` |
| Gom đơn hàng theo trạng thái | `orders.stream().collect(Collectors.groupingBy(Order::status))` |
| Tổng tiền BigDecimal | `amounts.stream().reduce(BigDecimal.ZERO, BigDecimal::add)` |
| Kiểm tra tồn tại bản ghi sai | `records.stream().anyMatch(this::isInvalid)` |

Các ví dụ trên minh họa lựa chọn API, không tự giải quyết các quy tắc nghiệp vụ bổ sung như trùng lặp, làm tròn, quyền truy cập hay tính ổn định của dữ liệu nguồn.

## 14. Tự kiểm tra

1. `reduce(0, Integer::sum)` trên Stream rỗng trả gì? **0**, vì đó là identity của phép cộng.
2. `reduce(Integer::max)` trên Stream rỗng trả gì? **Optional.empty()**, vì không có phần tử nào.
3. Vì sao `reduce(0, Integer::max)` không đúng với nguồn toàn số âm? **0 không phải identity của max** trên miền đó.
4. Phép trừ có thể dùng làm reducer để bảo đảm cùng kết quả khi chia nhánh parallel không? **Không**, vì phép trừ không kết hợp.
5. Khi nào chọn `collect` thay `reduce`? **Khi xây container mutable** như List, Set, Map hoặc bộ thống kê có thể cập nhật.
6. Vì sao `String::concat` trong `reduce` có thể chậm khi kết quả rất dài? **Vì** tạo nhiều String bất biến trung gian.
7. Nếu chỉ muốn biết có số âm, `reduce` hay `anyMatch` hợp lý hơn? **anyMatch**, do diễn đạt rõ điều kiện và có thể dừng sớm.
8. Trong `reduce` ba tham số, combiner phải nhận kiểu gì? **Hai kết quả kiểu U**, rồi trả kết quả kiểu U.
9. Gọi `reduce` xong trên một Stream từ `Files.lines` có tự đóng tệp không? **Không**, vẫn cần đóng Stream trong phạm vi sở hữu tài nguyên.
10. Vì sao tổng `double` giữa sequential và parallel có thể chênh chút ít? **Vì** phép cộng số thực chịu sai số làm tròn và không kết hợp tuyệt đối.

**Nguyên tắc áp dụng:** `reduce` phù hợp khi bài toán thực sự là **gộp các giá trị thành một kết quả theo phép toán có tính kết hợp**. Hãy xác định đúng identity và cách xử lý nguồn rỗng, giữ accumulator thuần, rồi mới cân nhắc song song. Với các phép tổng hợp có API chuyên dụng hoặc có trạng thái mutable, chọn `sum`, `max`, `anyMatch` hay `collect` thường rõ nghĩa, an toàn và dễ tối ưu hơn.
