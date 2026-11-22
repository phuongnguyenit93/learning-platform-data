# Dùng reduce không có giá trị khởi đầu

Trong Java Stream API, `reduce` là thao tác kết thúc (*terminal operation*) dùng để **gộp nhiều phần tử thành một kết quả** theo một quy tắc kết hợp. Một dạng đặc biệt hữu ích là `reduce(BinaryOperator<T>)`, tức **reduce không truyền giá trị khởi đầu** (*identity*). Khi nguồn có phần tử, kết quả được gộp từ chính các phần tử đó; khi nguồn rỗng, không có một kết quả nào để trả về, nên phương thức trả `Optional.empty()`.

Bài thuộc chương **Phép rút gọn với reduce** của module **JAVA_STREAM_API**. Mục tiêu là hiểu cách chọn phiên bản `reduce`, xử lý nguồn rỗng, viết phép gộp hợp lệ cho Stream tuần tự và song song, và biết khi nào các API chuyên dụng như `sum`, `min`, `max` hoặc `collect` phù hợp hơn. Kiến thức này nối tiếp pipeline khai báo, lazy, `filter`, `map` và mở rộng sang grouping, collector tùy chỉnh, `Spliterator`, xử lý song song cũng như giới hạn về trạng thái, tài nguyên và độ chính xác.

## 1. Chữ ký của reduce không có identity

Đối với `java.util.stream.Stream<T>`, Java 8 trở lên định nghĩa:

```java
Optional<T> reduce(BinaryOperator<T> accumulator);
```

Trong đó:

- `T` là kiểu phần tử của Stream và kiểu kết quả được gộp.
- `BinaryOperator<T>` là functional interface trong `java.util.function`, biểu diễn hàm nhận **hai giá trị `T`** và trả về **một giá trị `T`**. Nó kế thừa `BiFunction<T, T, T>`.
- `accumulator` mô tả **cách ghép hai kết quả từng phần** thành một kết quả.
- `Optional<T>` thể hiện rằng **nguồn rỗng có thể không có kết quả**.

Ví dụ:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> total = Stream.of(5, 10, 15)
        .reduce(Integer::sum);

System.out.println(total); // Optional[30]
```

Không có tham số `0` hay một giá trị nào khác làm điểm xuất phát. Với một Stream **tuần tự và có thứ tự**, ta có thể hình dung:

```text
Nguồn:       [5, 10, 15]
                 \   /
     gộp:       15
                  \    /
     gộp:         30
                   |
                 Optional[30]
```

Đây là mô hình giải thích đơn giản. Trong Stream song song, runtime có thể chia dữ liệu thành nhiều phần, gộp cục bộ rồi kết hợp các kết quả. Vì vậy, tính đúng đắn phải dựa trên **hợp đồng phép toán**, không dựa vào sơ đồ thứ tự gọi hàm ở trên.

### 1.1. Trường hợp 0, 1 và nhiều phần tử

```java
Optional<Integer> none = Stream.<Integer>empty()
        .reduce(Integer::sum);

Optional<Integer> one = Stream.of(42)
        .reduce(Integer::sum);

Optional<Integer> many = Stream.of(8, -8)
        .reduce(Integer::sum);

System.out.println(none); // Optional.empty
System.out.println(one);  // Optional[42]
System.out.println(many); // Optional[0]
```

| Nguồn | Kết quả | Ý nghĩa |
|---|---|---|
| `[]` | `Optional.empty()` | Không có phần tử để rút gọn |
| `[42]` | `Optional[42]` | Chính phần tử duy nhất là kết quả; không cần gộp với phần tử khác |
| `[8, -8]` | `Optional[0]` | Có dữ liệu và tổng thực sự bằng 0 |

**Điểm quan trọng:** `Optional.empty()` và `Optional[0]` **khác nhau**. Dạng `reduce` này giữ được thông tin “không có dữ liệu”; nếu mặc định giá trị 0 ngay lập tức, thông tin ấy có thể bị mất.

## 2. Cách xử lý Optional sau reduce

`Optional<T>` không phải `T`. Muốn sử dụng kết quả, cần xác định **chính sách cho nguồn rỗng**.

### 2.1. Nếu có kết quả thì sử dụng

```java
Optional<Integer> result = Stream.of(3, 4, 5)
        .reduce(Integer::sum);

result.ifPresent(sum -> System.out.println("Tổng: " + sum));
// Tổng: 12
```

Nếu nguồn rỗng, `ifPresent` không thực hiện hành động. Phù hợp khi “không có kết quả thì không cần thực hiện bước tiếp theo”.

### 2.2. Cung cấp giá trị mặc định

```java
int totalForDisplay = Stream.<Integer>empty()
        .reduce(Integer::sum)
        .orElse(0);

System.out.println(totalForDisplay); // 0
```

Với phép **tính tổng**, 0 có thể là mặc định hợp lý. Nhưng nếu nghiệp vụ phải phân biệt “chưa có giao dịch” với “các giao dịch cộng lại bằng 0”, hãy giữ `Optional` hoặc kèm thêm số lượng phần tử.

`orElseGet(() -> fallback)` chỉ tính giá trị dự phòng khi Optional rỗng. Nếu giá trị dự phòng phải được tính tốn kém hoặc có tác dụng phụ, `orElseGet` có thể phù hợp hơn `orElse`, vì biểu thức đối số của `orElse` được đánh giá ngay khi gọi.

### 2.3. Yêu cầu phải có kết quả

```java
int requiredTotal = Stream.of(1, 2, 3)
        .reduce(Integer::sum)
        .orElseThrow(() ->
                new IllegalStateException("Không có số liệu để tổng hợp"));

System.out.println(requiredTotal); // 6
```

Với Stream rỗng, đoạn code sẽ ném `IllegalStateException` có thông điệp nghiệp vụ thay vì giả vờ kết quả tồn tại. Không gọi `get()` trực tiếp trên Optional rỗng: `get()` ném `NoSuchElementException`.

Java 9 bổ sung `ifPresentOrElse`, và Java 10 bổ sung `Optional.orElseThrow()` không tham số. Các ví dụ trong bài vẫn sử dụng cú pháp có từ Java 8 để tiện thực hành.

## 3. So sánh reduce có và không có giá trị khởi đầu

Java cung cấp hai dạng thường gặp:

```java
// Không có identity: trả Optional<T>.
Optional<Integer> withoutIdentity = Stream.<Integer>empty()
        .reduce(Integer::sum);

// Có identity: trả T.
Integer withIdentity = Stream.<Integer>empty()
        .reduce(0, Integer::sum);

System.out.println(withoutIdentity); // Optional.empty
System.out.println(withIdentity);    // 0
```

| Khía cạnh | `reduce(BinaryOperator<T>)` | `reduce(T identity, BinaryOperator<T>)` |
|---|---|---|
| Giá trị khởi đầu | Không truyền | Có truyền `identity` |
| Kiểu trả về | `Optional<T>` | `T` |
| Nguồn rỗng | `Optional.empty()` | Chính `identity` |
| Một phần tử `x` | `Optional[x]` | `accumulator(identity, x)`, phải bằng `x` nếu identity hợp lệ |
| Bài toán thường gặp | Tìm cực trị, tổng chỉ khi có dữ liệu, ghép không có phần tử đơn vị rõ ràng | Tổng bằng 0 khi rỗng, tích bằng 1 khi rỗng, phép gộp có phần tử đơn vị xác định |

**Identity phải là phần tử đơn vị thật sự của phép gộp.** Nếu `op` là phép cộng thì `0` là identity, không phải `100`. Nếu `op` là phép nhân thì `1` là identity. Một giá trị mặc định tùy ý có thể làm sai kết quả, nhất là với pipeline song song.

```java
int sum = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum); // 9

int product = Stream.of(2, 3, 4)
        .reduce(1, (a, b) -> a * b); // 24

Optional<Integer> productIfPresent = Stream.<Integer>empty()
        .reduce((a, b) -> a * b); // Optional.empty
```

Việc **không truyền identity** không đồng nghĩa “phép gộp không cần tuân thủ hợp đồng toán học”. Cả hai dạng đều yêu cầu accumulator có tính kết hợp nhóm (*associativity*) để reduction hợp lệ khi Stream tự lựa chọn cách chia việc.

## 4. Ví dụ hoàn chỉnh: tổng tiền và đơn hàng lớn nhất

Giả sử ứng dụng có đơn hàng đã thanh toán và chưa thanh toán. Ta cần:

1. Tính tổng số tiền đã thanh toán **nếu có đơn phù hợp**.
2. Chọn một đơn đã thanh toán có số tiền lớn nhất, khi bằng nhau thì chọn mã lớn hơn.
3. Phân biệt trường hợp **không có đơn hoàn tiền** với tổng hoàn tiền bằng 0.

Ví dụ độc lập sau chạy với Java 8:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ReduceWithoutIdentityDemo {
    static final class Order {
        private final String id;
        private final String status;
        private final long amountCents;

        Order(String id, String status, long amountCents) {
            this.id = id;
            this.status = status;
            this.amountCents = amountCents;
        }

        String getId() {
            return id;
        }

        String getStatus() {
            return status;
        }

        long getAmountCents() {
            return amountCents;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("HD01", "PAID", 20_000L),
                new Order("HD02", "PENDING", 70_000L),
                new Order("HD03", "PAID", 30_000L),
                new Order("HD04", "PAID", 30_000L)
        );

        // Chỉ những đơn đã thanh toán mới tham gia phép tính.
        Optional<Long> paidTotal = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .map(Order::getAmountCents)
                .reduce(Long::sum);

        System.out.println(paidTotal);          // Optional[80000]
        System.out.println(paidTotal.orElse(0L)); // 80000

        // Comparator tạo quy tắc phá hòa mang tính xác định.
        Comparator<Order> byAmountThenId =
                Comparator.comparingLong(Order::getAmountCents)
                        .thenComparing(Order::getId);

        Optional<Order> largestPaid = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .reduce((best, candidate) ->
                        byAmountThenId.compare(best, candidate) >= 0
                                ? best : candidate);

        System.out.println(largestPaid
                .map(Order::getId)
                .orElse("(không có đơn)")); // HD04

        // Trạng thái REFUNDED không tồn tại trong dữ liệu mẫu.
        Optional<Long> refundedTotal = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .map(Order::getAmountCents)
                .reduce(Long::sum);

        System.out.println(refundedTotal); // Optional.empty
        System.out.println(refundedTotal.isPresent()); // false
    }
}
```

Trong ví dụ, `map(Order::getAmountCents)` chuyển `Stream<Order>` thành `Stream<Long>`; `reduce(Long::sum)` gộp các phần tử kiểu `Long`. Với hai đơn HD03 và HD04 cùng số tiền, `thenComparing(Order::getId)` quyết định HD04 lớn hơn theo quy tắc so sánh đã chọn.

Cách chọn đơn cực đại bằng `reduce` giúp thấy cách một `BinaryOperator<Order>` gộp hai ứng viên. Trong mã sản xuất, thường dễ đọc hơn nếu viết `max(byAmountThenId)`:

```java
Optional<Order> largestPaid = orders.stream()
        .filter(order -> "PAID".equals(order.getStatus()))
        .max(byAmountThenId);
```

Với tổng tiền tệ, kiểu `long` ở đơn vị nhỏ nhất có thể tránh sai số của `double` trong phạm vi không bị tràn. Nếu tổng có thể vượt `long` hoặc cần phép chia thập phân chính xác, cân nhắc `BigInteger` hoặc `BigDecimal` theo miền dữ liệu.

## 5. Reduce không có identity trên IntStream, LongStream và DoubleStream

Các Stream nguyên thủy có overload `reduce` nhận toán tử tương ứng và trả về Optional chuyên dụng:

| API | Tham số | Kiểu trả về khi không có identity |
|---|---|---|
| `IntStream.reduce(...)` | `IntBinaryOperator` | `OptionalInt` |
| `LongStream.reduce(...)` | `LongBinaryOperator` | `OptionalLong` |
| `DoubleStream.reduce(...)` | `DoubleBinaryOperator` | `OptionalDouble` |
| `Stream<T>.reduce(...)` | `BinaryOperator<T>` | `Optional<T>` |

Ví dụ:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt max = IntStream.of(4, 9, 1)
        .reduce(Integer::max);          // OptionalInt[9]

OptionalLong total = LongStream.empty()
        .reduce(Long::sum);             // OptionalLong.empty

OptionalDouble product = DoubleStream.of(2.0, 3.0)
        .reduce((a, b) -> a * b);        // OptionalDouble[6.0]

System.out.println(max.orElse(-1));      // 9
System.out.println(total.orElse(0L));    // 0
System.out.println(product.orElse(1.0)); // 6.0
```

Chú ý phân biệt `IntStream.empty().reduce(Integer::sum)` trả `OptionalInt.empty()`, trong khi `IntStream.empty().sum()` trả `0`. Đây là quyết định về **cách biểu diễn thiếu dữ liệu**; không phải phép tính nào có kết quả trả kiểu Optional cũng nhanh hơn hoặc chính xác hơn.

Khi làm việc với rất nhiều số nguyên thủy, `IntStream`/`LongStream`/`DoubleStream` có thể tránh chi phí boxing/unboxing của `Stream<Integer>`/`Stream<Long>`/`Stream<Double>`. Nếu mục tiêu thực sự chỉ là tính tổng, `sum()` rõ ý định hơn `reduce(Integer::sum)`.

## 6. Tính kết hợp nhóm quyết định tính đúng của reduction

Với accumulator ký hiệu `op`, tính **kết hợp nhóm** nghĩa là:

\[
(a\ \mathrm{op}\ b)\ \mathrm{op}\ c
=a\ \mathrm{op}\ (b\ \mathrm{op}\ c)
\]

Phép cộng số nguyên (trong ngữ nghĩa số học và phạm vi dữ liệu hợp lệ), phép nhân và phép chọn cực đại theo một thứ tự nhất quán là những ví dụ quen thuộc. Phép trừ và phép chia nói chung **không có tính kết hợp nhóm**.

### 6.1. Sai: dùng phép trừ với reduce

```java
import java.util.stream.Stream;

int sequential = Stream.of(10, 5, 2)
        .reduce((a, b) -> a - b)
        .orElseThrow(() -> new IllegalStateException("Rỗng"));

System.out.println(sequential); // 3: (10 - 5) - 2
```

Nhưng `(10 - 5) - 2 = 3`, trong khi `10 - (5 - 2) = 7`. Việc đổi cách chia nhóm làm đổi kết quả. Đừng đem reducer này sang `parallelStream()` và kỳ vọng kết quả ổn định hay ý nghĩa nghiệp vụ giống phép trừ tuần tự.

**Lưu ý:** Ngay cả khi code tuần tự hiện tại có vẻ “chạy đúng”, contract `reduce` yêu cầu phép toán kết hợp nhóm. Nếu thuật toán thực chất là phép trừ lần lượt theo thứ tự, vòng lặp trực tiếp với điểm xuất phát xác định có thể thể hiện yêu cầu rõ ràng hơn.

### 6.2. Chọn cực trị: phép gộp hợp lệ khi comparator nhất quán

```java
import java.util.Comparator;
import java.util.Optional;
import java.util.stream.Stream;

Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());

Optional<String> longest = Stream.of("A", "BBB", "CC")
        .reduce((a, b) ->
                byLengthThenText.compare(a, b) >= 0 ? a : b);

System.out.println(longest.orElse("(trống)")); // BBB
```

Reducer chọn phần tử lớn hơn theo một comparator nhất quán và phá hòa cụ thể nên có ý nghĩa cả khi dữ liệu được chia thành các phần con. Để diễn đạt yêu cầu này gọn hơn, có thể dùng `stream.max(byLengthThenText)`.

### 6.3. Double có sai số phụ thuộc thứ tự cộng

Với `double`, phép cộng không kết hợp nhóm **chính xác theo bit** do giới hạn biểu diễn và làm tròn:

```java
double left = (1.0e16 + -1.0e16) + 1.0; // 1.0
double right = 1.0e16 + (-1.0e16 + 1.0); // 0.0
```

Vì vậy, reduction song song trên số thực có thể khác kết quả tuần tự do cách phân nhóm phép cộng, dù phép cộng là kết hợp nhóm trong toán học thực. Khi yêu cầu chính xác cao, hãy chọn phương pháp tổng hợp thích hợp, cân nhắc `DoubleStream.sum()` (có thể tăng độ chính xác bằng phép cộng bù) hoặc `BigDecimal` đối với dữ liệu thập phân, và đặt mức sai số chấp nhận được.

## 7. Accumulator phải thuần và không thay đổi dữ liệu dùng chung

Accumulator dùng trong `reduce` cần là hàm **không can thiệp vào nguồn** (*non-interfering*) và **không có trạng thái dùng chung** (*stateless*). Hàm có thể được gọi theo cách khác nhau giữa Stream tuần tự và song song; không nên phụ thuộc số lần gọi, thứ tự chạy thread hoặc tác dụng phụ.

**Không nên** sửa một đối tượng mutable và dùng nó làm kết quả trung gian:

```java
// KHÔNG NÊN: cùng sửa một StringBuilder được trả về làm trạng thái
// của phép reduce; kết quả phụ thuộc aliasing và cách chạy song song.
StringBuilder unsafe = Stream.of("A", "B", "C")
        .parallel()
        .reduce(new StringBuilder(),
                (builder, text) -> builder.append(text),
                (left, right) -> left.append(right));
```

Đoạn trên dùng **overload ba tham số** để minh họa nguy cơ: các nhánh có thể chia sẻ cùng identity mutable, vi phạm các giả thiết cần có để reduction song song hoạt động đúng. Với bài toán xây chuỗi, dùng collector:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String joined = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining());

System.out.println(joined); // ABC
```

Lý do không dùng `reduce(String::concat)` cho mọi bài ghép chuỗi là ở chi phí: chuỗi bất biến có thể tạo nhiều bản sao trung gian. `Collectors.joining()` được thiết kế dành riêng cho việc ghép chuỗi. Nếu chỉ nối một số ít phần tử, reduce vẫn có thể diễn đạt được ý nghĩa, nhưng cần cân nhắc số lượng và hiệu năng.

### 7.1. Không dùng null như tín hiệu “bỏ qua kết quả”

`Optional` không chứa phần tử null. Theo hợp đồng của `reduce(BinaryOperator)`, **nếu kết quả phép rút gọn là null thì có thể ném `NullPointerException`**; riêng trường hợp reducer trả null khi gộp những phần tử có dữ liệu sẽ là lỗi.

```java
// SAI: không dùng null làm kết quả của reducer.
// Stream.of(1, 2).reduce((a, b) -> null);

// ĐÚNG nếu muốn bỏ một số phần tử:
Optional<Integer> totalPositive = Stream.of(-1, 2, -3, 4)
        .filter(n -> n > 0)
        .reduce(Integer::sum); // Optional[6]
```

Nếu dữ liệu nguồn có phần tử null, hãy lọc hoặc chuẩn hóa **trước** khi rút gọn. Không dùng reducer để “nuốt” phần tử null một cách ngầm định.

## 8. Giới hạn của reduce không identity khi tính nhiều đại lượng

`reduce(BinaryOperator<T>)` nhận hai phần tử **cùng kiểu `T`** và gộp về `T`. Nó phù hợp khi kết quả và các phần tử cùng kiểu; ví dụ tổng các `Long`, chọn `Order` lớn nhất hoặc ghép một số chuỗi.

Nếu đầu ra có **kiểu khác** hoặc cần tính **nhiều thông số cùng lúc**, nên cân nhắc thao tác khác:

- `map` trước `reduce` khi có thể chuyển mỗi đầu vào thành kiểu kết quả cần gộp, ví dụ `Stream<Order> -> Stream<Long>`.
- `collect` hoặc `summaryStatistics` khi cần cả số lượng, tổng, trung bình, cực trị và các bộ tích lũy có thể thay đổi.
- `Collectors.groupingBy(..., downstream)` khi cần kết quả cho từng nhóm, thay vì một giá trị chung cho toàn Stream.

Ví dụ `Collectors.reducing(BinaryOperator<T>)` là collector tương ứng với reducer không identity, thuận tiện khi muốn gộp theo từng nhóm:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(3, 7, 2, 10);

Map<String, Optional<Integer>> maxByParity = numbers.stream()
        .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "CHẴN" : "LẺ",
                Collectors.reducing(Integer::max)));

System.out.println(maxByParity.get("CHẴN")); // Optional[10]
System.out.println(maxByParity.get("LẺ"));    // Optional[7]
```

`groupingBy` chỉ tạo khóa nhóm xuất hiện trong dữ liệu. Với danh sách rỗng, Map kết quả rỗng và **không có khóa “CHẴN” hay “LẺ”**. Các Optional trong Map biểu thị kết quả reducer của từng nhóm. Nếu chỉ cần cực đại, `Collectors.maxBy(Comparator.naturalOrder())` là biểu thức chuyên dụng và dễ đọc hơn.

### 8.1. Reduce không có identity và short-circuit

`reduce` là terminal operation, nhưng **không phải thao tác ngắn mạch** (*short-circuiting*) như `findFirst` hoặc `anyMatch`. Để biết kết quả gộp của một nguồn hữu hạn, nó thường phải tiêu thụ toàn bộ các phần tử sau lọc. Với Stream vô hạn, lời gọi `reduce` có thể không kết thúc nếu không có cơ chế giới hạn trước đó:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> totalFirstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .reduce(Integer::sum); // Optional[15]
```

`limit(5)` giới hạn năm phần tử đầu của nguồn vô hạn. Không nhầm việc có giá trị cuối cùng kiểu `Optional` với khả năng tự dừng của phép reduction.

## 9. Chọn đúng thao tác cho từng tình huống

| Nhu cầu | Lựa chọn thường dễ hiểu nhất | Khi nguồn rỗng |
|---|---|---|
| Tổng số nguyên, mặc định 0 | `IntStream.sum()` hoặc `reduce(0, Integer::sum)` | `0` |
| Tổng số nguyên nhưng muốn giữ thông tin chưa có dữ liệu | `reduce(Integer::sum)` | `Optional.empty()` |
| Phần tử nhỏ nhất/lớn nhất theo comparator | `min(comparator)` / `max(comparator)` | `Optional.empty()` |
| Nối các chuỗi | `Collectors.joining()` | Chuỗi rỗng `""` |
| Tính số lượng | `count()` | `0L` |
| Trung bình số nguyên thủy | `IntStream.average()` | `OptionalDouble.empty()` |
| Tính count, sum, min, max cùng lúc | `summaryStatistics()` hoặc collector thích hợp | Đếm bằng 0; cần kiểm tra trước khi hiển thị cực trị |
| Gộp từng nhóm theo phép toán riêng | `groupingBy(..., reducing(op))` | Không tự xuất hiện nhóm thiếu dữ liệu |

Chọn `reduce` không có identity **khi việc không có phần tử là một trạng thái có ý nghĩa** hoặc phép gộp tự nhiên không có identity phù hợp. Nếu đã có terminal operation chuyên dụng, sử dụng nó thường làm code dễ đọc, dễ kiểm chứng và có cơ hội tối ưu tốt hơn.

## 10. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Không truyền identity thì reduce tự dùng 0.” | Nguồn rỗng trả `Optional.empty()`; `0` chỉ là identity của phép cộng khi được truyền rõ ràng hoặc do API `sum()` quy định. |
| “Optional rỗng nghĩa là phép cộng ra 0.” | `Optional.empty()` là **không có kết quả**; `Optional[0]` là **có kết quả bằng 0**. |
| “Có một phần tử thì reducer chạy một lần với chính nó.” | Không cần gọi reducer với một cặp; phần tử đơn là kết quả. |
| “Reduce luôn gộp từ trái sang phải.” | Với Stream song song, cách chia và kết hợp có thể khác; accumulator phải có tính kết hợp nhóm. |
| “Bất kỳ phép toán hai ngôi nào cũng dùng được cho reduce.” | Phép trừ/chia thường không kết hợp nhóm; trạng thái mutable cũng có thể vi phạm yêu cầu. |
| “Có thể dùng null để bỏ phần tử trong reducer.” | Reducer trả null có thể làm reduction lỗi; lọc/chuẩn hóa trước. |
| “Parallel reduce tự động nhanh hơn tuần tự.” | Chia việc, boxing, tổ chức phép gộp và chi phí từng phần tử có thể làm chậm hơn; cần đo. |
| “Dùng reduce để tạo List là cách chuẩn.” | `collect` phù hợp hơn cho tích lũy mutable vào List, Set hoặc Map. |

## 11. Bài tập vận dụng có đáp án

### Bài 1. Phân biệt rỗng và tổng bằng 0

```java
Optional<Integer> a = Stream.<Integer>empty()
        .reduce(Integer::sum);
Optional<Integer> b = Stream.of(6, -6)
        .reduce(Integer::sum);
```

**Đáp án:** `a` là `Optional.empty()`; `b` là `Optional[0]`. Chỉ `b` phản ánh có hai phần tử thật sự được cộng.

### Bài 2. Nguồn có một phần tử

```java
Optional<String> result = Stream.of("Java")
        .reduce(String::concat);
```

**Đáp án:** `Optional[Java]`. Không cần một chuỗi rỗng khởi đầu hoặc ghép chính phần tử đó với nó.

### Bài 3. Tìm phần tử dài nhất

Tìm từ dài nhất trong `["API", "Stream", "Java"]`. Nếu cùng chiều dài, chọn từ lớn hơn theo thứ tự từ điển.

```java
Comparator<String> rule = Comparator
        .comparingInt(String::length)
        .thenComparing(Comparator.naturalOrder());

Optional<String> longest = Stream.of("API", "Stream", "Java")
        .reduce((a, b) -> rule.compare(a, b) >= 0 ? a : b);
// Optional[Stream]
```

### Bài 4. Vì sao phép trừ nguy hiểm?

Với các số 20, 5, 3, hãy so sánh `(20 - 5) - 3` và `20 - (5 - 3)`.

**Đáp án:** Hai kết quả là 12 và 18, nên phép trừ không có tính kết hợp nhóm. Không dùng nó làm reducer cho pipeline có thể chạy song song.

### Bài 5. Quyết định đúng cho báo cáo

API cần trả **tổng tiền thanh toán** và phân biệt ngày chưa có giao dịch với ngày có các khoản tiền bù trừ nhau. Nên trả `long` với mặc định 0 hay `Optional<Long>`?

**Đáp án:** `Optional<Long>` sau `map(Order::getAmountCents).reduce(Long::sum)` bảo toàn tín hiệu không có đơn. Nếu đồng thời cần `count` để kiểm tra tính đầy đủ hoặc tránh lặp Stream, hãy dùng một phép thu thập thống kê có cả count và total.

## 12. Ghi nhớ

`reduce(BinaryOperator<T>)` dùng chính các phần tử Stream làm cơ sở gộp và trả `Optional<T>` vì **nguồn rỗng không có kết quả**. Nó phân biệt `Optional.empty()` với một kết quả thực sự bằng 0, đồng thời áp dụng được cho phép cộng, chọn cực trị và nhiều quy tắc kết hợp khác. Để sử dụng đúng, hãy viết accumulator **thuần, không can thiệp vào dữ liệu nguồn, không dựa vào trạng thái mutable chung và có tính kết hợp nhóm**; xử lý `Optional` theo quy tắc nghiệp vụ và cân nhắc API chuyên dụng như `sum`, `max`, `min` hoặc `collect` khi chúng diễn đạt mục tiêu rõ hơn.
