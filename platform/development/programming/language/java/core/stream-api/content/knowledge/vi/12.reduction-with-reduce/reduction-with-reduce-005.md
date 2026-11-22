# Tính kết hợp và phần tử đơn vị trong phép rút gọn

`reduce` trong Java Stream API gom nhiều phần tử của một stream thành một kết quả: tổng, tích, chuỗi ghép, giá trị lớn nhất hoặc một cấu trúc tổng hợp. Tuy nhiên, để kết quả có ý nghĩa khi Java thay đổi cách chia dữ liệu và kết hợp các kết quả trung gian, phép rút gọn phải thỏa **tính kết hợp** (*associativity*) và dùng **phần tử đơn vị** (*identity*) đúng.

Đây là bài thuộc chương **Phép rút gọn với reduce** của module **JAVA_STREAM_API**. Bài tập trung vào hợp đồng toán học và hợp đồng thực thi của `reduce`, từ stream tuần tự đến `parallelStream()`, cách thiết kế accumulator/combiner, cùng giới hạn về trạng thái dùng chung, độ chính xác số và hiệu năng. Sau khi học, bạn sẽ giải thích được *vì sao một biểu thức reduce có thể chạy đúng trên vài phần tử nhưng sai khi chạy song song*, và biết chọn `collect` khi cần tích lũy vào đối tượng mutable.

## 1. Phép rút gọn diễn đạt điều gì?

Xét danh sách các số:

```java
import java.util.List;

List<Integer> values = List.of(2, 4, 6);

int sum = values.stream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 12
```

`reduce(0, Integer::sum)` mô tả một phép tính với hai thành phần:

- **Identity**: `0`, giá trị trung hòa và cũng là kết quả khi stream rỗng.
- **Accumulator**: `Integer::sum`, phép kết hợp hai giá trị thành một giá trị cùng kiểu.

Về mặt khái niệm, cách cộng tuần tự từ trái sang phải là:

```text
Ban đầu: acc = 0
Phần tử 2: acc = 0 + 2 = 2
Phần tử 4: acc = 2 + 4 = 6
Phần tử 6: acc = 6 + 6 = 12
```

Đó là một cách hình dung hữu ích để học, nhưng **không phải ràng buộc cách thực thi của `reduce`**. Framework có thể nhóm các phần tử khác đi, nhất là trong pipeline song song. Hai quy tắc toán học dưới đây giải thích khi nào việc nhóm khác đi vẫn cho cùng kết quả.

## 2. Tính kết hợp (*associativity*)

Một phép toán nhị phân `⊕` được gọi là **có tính kết hợp** nếu với mọi `a`, `b`, `c` hợp lệ:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

Phép toán có thể được nhóm theo nhiều cách mà không đổi kết quả. Đây là điều kiện trọng tâm vì một stream có thể được chia thành các đoạn để tính tổng con rồi kết hợp.

Ví dụ phép cộng các số nguyên trong miền không tràn số:

```text
(2 + 4) + 6 = 12
2 + (4 + 6) = 12
```

Phép nối chuỗi cũng có tính kết hợp:

```text
("Ja" + "v") + "a" = "Java"
"Ja" + ("v" + "a") = "Java"
```

Nhưng phép trừ thì **không**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Do đó, dùng phép trừ làm phép rút gọn song song không thỏa hợp đồng accumulator có tính kết hợp.

### 2.1. Tính kết hợp khác tính giao hoán

**Tính giao hoán** (*commutativity*) là quy tắc khác:

```text
a ⊕ b = b ⊕ a
```

Phép nối chuỗi có tính kết hợp nhưng **không giao hoán**: `"ab"` khác `"ba"`. Đừng nhầm yêu cầu có tính kết hợp của `reduce` thành yêu cầu phải giao hoán.

```java
String word = List.of("Ja", "v", "a").parallelStream()
        .reduce("", String::concat);

System.out.println(word); // Java
```

Nguồn `List` có encounter order, phép nối chuỗi có tính kết hợp và chuỗi rỗng là identity. Do đó, việc kết hợp các đoạn liên tiếp có thể tạo kết quả `"Java"` mà không cần thực hiện từng phép nối trên một thread. Nếu dùng nguồn **không có encounter order** hoặc bỏ ràng buộc thứ tự, đừng trông đợi cùng thứ tự ghép ký tự.

### 2.2. Một số phép toán thường gặp

| Phép toán | Có tính kết hợp trong miền nào? | Lưu ý |
|---|---|---|
| Cộng `int`, `long` | Có theo số học nguyên modulo của Java; theo số học thông thường khi không tràn | Overflow có thể phá ý nghĩa nghiệp vụ |
| Nhân `int`, `long` | Có theo số học nguyên modulo; theo số học thông thường khi không tràn | Cần chọn identity `1` |
| `Math.min`, `Math.max` | Có với miền số nguyên phù hợp | Identity phải thật sự trung hòa trong toàn miền |
| Nối `String` | Có | Không giao hoán; giữ đúng thứ tự nguồn nếu cần |
| Cộng `BigDecimal` không dùng làm tròn theo `MathContext` | Có theo giá trị số | Phù hợp khi cần số thập phân chính xác |
| Trừ, chia | Không có tính kết hợp tổng quát | Không dùng làm accumulator song song tùy ý |
| Cộng `double` | Không tuyệt đối do làm tròn | Thứ tự nhóm cộng có thể thay đổi bit kết quả |
| Tính trung bình trực tiếp từ hai trung bình | Không hợp lệ nếu bỏ qua số phần tử | Phải giữ thêm tổng và số lượng |

**Chú ý:** quy tắc dùng cho `reduce` là hợp đồng trên **toàn bộ miền dữ liệu thực tế**, không chỉ vài mẫu thử cho kết quả giống nhau.

## 3. Phần tử đơn vị (*identity*)

Phần tử `e` là identity của phép `⊕` nếu với mọi `x` hợp lệ:

```text
e ⊕ x = x
x ⊕ e = x
```

Đối với một số overload `reduce`, Java yêu cầu identity là phần tử trung hòa của phép kết hợp. Vì một pipeline song song có thể tạo các kết quả từng đoạn bắt đầu từ identity, việc chọn sai identity sẽ gây sai số hoặc kết quả thừa.

| Phép kết hợp | Identity đúng | Minh họa |
|---|---|---|
| Tổng số nguyên | `0` | `0 + x = x` |
| Tích số nguyên | `1` | `1 * x = x` |
| Ghép chuỗi | `""` | `"" + s = s` |
| Hợp của các tập hợp bất biến | Tập rỗng | `∅ ∪ S = S` |
| Giá trị lớn nhất trong miền `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Giá trị nhỏ nhất trong miền `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

Ví dụ tổng và tích:

```java
List<Integer> numbers = List.of(2, 3, 4);

int sum = numbers.stream().reduce(0, Integer::sum);
int product = numbers.stream().reduce(1, (a, b) -> a * b);

System.out.println(sum);     // 9
System.out.println(product); // 24
```

### 3.1. Sai identity: chương trình có thể chạy nhưng trả sai

```java
int wrongSum = List.of(2, 3, 4).stream()
        .reduce(10, Integer::sum);

System.out.println(wrongSum); // 19, vì 10 bị cộng thêm
```

`10` không phải identity của phép cộng. Với pipeline tuần tự, nó làm tổng bị cộng thêm `10` một lần; với pipeline song song, nhiều tác vụ có thể sử dụng identity cho các đoạn khác nhau, nên mức sai lệch có thể còn khác nữa. Không suy luận identity chỉ được áp dụng đúng một lần trong mọi cách triển khai.

Một sai lầm tương tự khi tìm min:

```java
int wrongMin = List.of(4, 8, 6).stream()
        .reduce(0, Integer::min);

System.out.println(wrongMin); // 0, không có trong dữ liệu nguồn!
```

`0` không phải identity của phép min trên mọi số nguyên. `Integer.MAX_VALUE` có thể là identity cho phép min trên `int`, nhưng khi không muốn phải chọn phần tử đơn vị giả định, dùng `reduce(BinaryOperator)` hoặc `min` để nhận `Optional`.

### 3.2. Identity quyết định kết quả trên stream rỗng

```java
import java.util.stream.Stream;

System.out.println(Stream.<Integer>empty()
        .reduce(0, Integer::sum)); // 0

System.out.println(Stream.<Integer>empty()
        .reduce(1, (a, b) -> a * b)); // 1

System.out.println(Stream.<String>empty()
        .reduce("", String::concat)); // ""
```

Đây là đặc điểm của overload có identity: nó trả về chính identity khi nguồn không có phần tử. Nếu `0` hay chuỗi rỗng có thể gây hiểu lầm giữa “kết quả thật bằng 0” và “không có dữ liệu”, cân nhắc overload trả `Optional`.

## 4. Ba overload `reduce` cần phân biệt

| Chữ ký khái niệm | Kết quả trả về | Đặc điểm |
|---|---|---|
| `reduce(BinaryOperator<T> accumulator)` | `Optional<T>` | Không cần cung cấp identity; rỗng trả `Optional.empty()` |
| `reduce(T identity, BinaryOperator<T> accumulator)` | `T` | Phần tử trung hòa bắt buộc đúng |
| `reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` | `U` | Có thể rút gọn từ `T` sang kiểu `U`; accumulator và combiner phải tương thích |

Các primitive stream như `IntStream`, `LongStream`, `DoubleStream` có overload giảm tương ứng với kiểu primitive; `sum()`, `min()`, `max()` cũng là những terminal operation chuyên dụng.

### 4.1. `reduce(BinaryOperator)`: không cần identity

```java
import java.util.Optional;

Optional<Integer> max = List.of(4, 9, 2).stream()
        .reduce(Integer::max);

System.out.println(max.orElseThrow()); // 9
```

Nếu nguồn rỗng:

```java
Optional<Integer> missing = Stream.<Integer>empty()
        .reduce(Integer::max);

System.out.println(missing.isEmpty()); // true
```

Overload này cho phép tránh identity không phù hợp hoặc không tự nhiên. Khi chỉ cần cực trị, `stream.max(Integer::compareTo)` hay `stream.min(Integer::compareTo)` thường trực tiếp hơn. `Optional` mô tả trường hợp không có phần tử; không dùng `get()` thiếu kiểm tra nếu stream có thể rỗng.

### 4.2. `reduce(identity, accumulator)`: cùng kiểu

```java
int totalLength = List.of("Java", "API").stream()
        .map(String::length)
        .reduce(0, Integer::sum);

System.out.println(totalLength); // 7
```

Ở đây `map` chuyển từng chuỗi sang số nguyên, nên phép `reduce` cùng làm việc với `Integer`. Khi có `IntStream`, có thể diễn đạt ngắn hơn:

```java
int length = List.of("Java", "API").stream()
        .mapToInt(String::length)
        .sum();

System.out.println(length); // 7
```

`IntStream.sum()` nói rõ mục tiêu tính tổng, tránh boxing không cần thiết trong giai đoạn tổng hợp.

### 4.3. `reduce(identity, accumulator, combiner)`: khác kiểu đầu vào và kết quả

Ví dụ một đơn hàng có số lượng và đơn giá tính bằng xu, nhưng ta muốn tổng doanh thu kiểu `long`:

```java
record Line(String sku, int quantity, long unitPriceCents) {}

List<Line> lines = List.of(
        new Line("A", 2, 150L),
        new Line("B", 1, 425L),
        new Line("C", 3, 100L)
);

long revenueCents = lines.parallelStream().reduce(
        0L,
        (subtotal, line) -> subtotal
                + line.quantity() * line.unitPriceCents(),
        Long::sum
);

System.out.println(revenueCents); // 1025
```

Ở overload ba đối số:

- `T` là `Line`, phần tử nguồn.
- `U` là `Long`, kiểu kết quả trung gian và kết quả cuối.
- `identity = 0L` là phần tử trung hòa của combiner `Long::sum`.
- Accumulator chuyển một `Line` thành phần đóng góp và cộng với tổng con.
- Combiner gộp hai tổng con; đặc biệt cần khi chạy song song.

Trong ví dụ, `2 * 150 + 1 * 425 + 3 * 100 = 1025`. Cách tính bằng số nguyên được dùng để tránh sai số thập phân với đơn vị tiền nhỏ nhất; dữ liệu thực phải kiểm soát nguy cơ tràn `long`.

## 5. Tính tương thích giữa accumulator và combiner

Overload ba đối số đòi hỏi nhiều hơn việc từng lambda “trông có vẻ đúng”. Theo hợp đồng Stream API:

1. Combiner phải có tính kết hợp.
2. Identity phải là phần tử trung hòa của combiner.
3. Accumulator và combiner phải **tương thích**: một phần tử nguồn đóng góp như nhau dù được cộng trực tiếp vào tổng con hay được tích lũy thành tổng con riêng rồi kết hợp.

Biểu diễn bằng `u` thuộc kiểu kết quả `U`, `t` thuộc kiểu đầu vào `T`, `e` là identity:

```text
combiner(u, accumulator(e, t)) = accumulator(u, t)
```

Với ví dụ cộng độ dài chuỗi:

```java
int characterCount = List.of("ab", "cde", "f").parallelStream()
        .reduce(
                0,
                (subtotal, text) -> subtotal + text.length(),
                Integer::sum
        );

System.out.println(characterCount); // 6
```

Giả sử `u = 5`, `t = "abc"`, `e = 0`:

```text
accumulator(0, "abc") = 3
combiner(5, 3) = 8
accumulator(5, "abc") = 8
```

Hai vế bằng nhau nên phép tính tương thích. Nếu thay combiner bằng phép nhân, biểu thức có thể vẫn biên dịch nhưng không còn đúng hợp đồng:

```java
// Sai về ngữ nghĩa: combiner không tương thích với phép cộng độ dài.
int wrong = List.of("ab", "cde", "f").parallelStream()
        .reduce(
                0,
                (subtotal, text) -> subtotal + text.length(),
                (left, right) -> left * right
        );
// Không có bảo đảm cho kết quả đếm ký tự mong muốn.
```

`0` cũng không phải identity của phép nhân; lỗi vi phạm cả hai yêu cầu. Trong các trường hợp khó phát hiện, pipeline tuần tự có thể tình cờ trả kết quả đúng vì combiner không được gọi theo cách bạn quan sát, rồi thất bại khi chạy song song.

## 6. Vì sao tính kết hợp quan trọng khi chạy song song?

Với nguồn hữu hạn `[2, 4, 6, 8]`, một cách nhóm tổng hợp có thể là:

```text
Nguồn:       [ 2, 4, 6, 8 ]
                  /     \
Nhóm 1:        [2,4]   [6,8]
                 |       |
Tổng con:        6      14
                  \    /
                 Kết hợp
                    |
                   20
```

Tính kết hợp cho phép framework chia việc theo cách phù hợp. Java không cam kết mỗi lần chạy song song phải chia đúng hai nhóm như sơ đồ. Khi toán tử không kết hợp, các cách nhóm khác nhau có thể sinh ra kết quả khác.

### 6.1. Phép trừ: phản ví dụ

```java
List<Integer> values = List.of(10, 3, 2);

int difference = values.stream()
        .reduce(0, (a, b) -> a - b);

System.out.println(difference); // Theo phép giảm tuần tự thông thường: -15
```

Ví dụ tuần tự có thể khiến ta nghĩ rằng `reduce(0, (a, b) -> a - b)` nghĩa là “trừ lần lượt mọi phần tử”. Nhưng `0` không là phần tử trung hòa **hai phía** của phép trừ và phép trừ không có tính kết hợp. Đừng sử dụng phép giảm này để biểu đạt một phép tổng hợp song song.

Nếu mục tiêu là **đổi dấu rồi cộng**, hãy biểu đạt bằng toán tử cộng có tính kết hợp:

```java
int negativeSum = values.parallelStream()
        .mapToInt(n -> -n)
        .sum();

System.out.println(negativeSum); // -15
```

Việc đổi từ phép trừ sang cộng các số âm giải quyết hợp đồng kết hợp cho miền `int` theo số học Java; với dữ liệu nguyên có thể vượt miền biểu diễn, cần kiểm tra overflow riêng.

### 6.2. Phép chia và phép trung bình đơn giản

Các phép chia liên tiếp cũng không có tính kết hợp:

```text
(100 / 10) / 2 = 5
100 / (10 / 2) = 20
```

Tương tự, công thức `(a + b) / 2` dùng để “gộp hai trung bình” thường sai khi hai nhóm có số phần tử khác nhau. Ví dụ nhóm `[10, 20]` có trung bình `15`, nhóm `[90]` có trung bình `90`; `(15 + 90) / 2 = 52.5` không phải trung bình của ba số, vốn bằng `40`.

Nếu cần trung bình, phải giữ **tổng và số phần tử** rồi chia ở cuối, hoặc dùng `IntStream.average()`, `DoubleStream.average()` hay `Collectors.averagingInt(...)` theo mục tiêu.

## 7. Một phép rút gọn đúng cho thống kê tổng và số lượng

Ta có thể thiết kế một kiểu kết quả bất biến để tích lũy hai thông tin cùng lúc. Ví dụ dùng `long` cho số lượng và tổng của đầu vào nguyên nhỏ:

```java
record Stats(long count, long sum) {
    Stats combine(Stats other) {
        return new Stats(
                this.count + other.count,
                this.sum + other.sum
        );
    }
}

Stats identity = new Stats(0, 0);

Stats result = List.of(10, 20, 90).parallelStream()
        .map(n -> new Stats(1, n))
        .reduce(identity, Stats::combine);

double average = (double) result.sum() / result.count();

System.out.println(result);  // Stats[count=3, sum=120]
System.out.println(average); // 40.0
```

Phép `combine` cộng số lượng và tổng **theo từng thành phần**, nên có tính kết hợp đối với số học nguyên Java; `Stats(0, 0)` là identity. Các `Stats` là record bất biến, không có đối tượng tích lũy mutable dùng chung giữa các nhánh.

Cần phân biệt hai vấn đề:

- **Hợp đồng reduce:** phép gộp hai kết quả thống kê có tính kết hợp, cho phép kết hợp tổng con.
- **Độ chính xác và giới hạn miền dữ liệu:** tổng `long` có thể tràn. Với dữ liệu thực, chọn loại số và xử lý overflow/precision phù hợp.

Đây là ví dụ để hiểu luật của `reduce`; trong ứng dụng đơn giản, `Collectors.summarizingInt(...)`, `IntStream.summaryStatistics()` hoặc `average()` thường là API tiện hơn.

## 8. Vì sao mutable accumulator dễ sai với `reduce`?

Không dùng một `ArrayList`, `StringBuilder` hoặc `HashMap` mutable làm identity rồi chỉnh sửa nó ngay trong accumulator của `reduce`, đặc biệt khi chạy song song:

```java
import java.util.ArrayList;

// Ví dụ không nên dùng:
// List<String> bad = List.of("A", "B", "C").parallelStream()
//         .reduce(
//                 new ArrayList<String>(),
//                 (list, text) -> {
//                     list.add(text);
//                     return list;
//                 },
//                 (left, right) -> {
//                     left.addAll(right);
//                     return left;
//                 }
//         );
```

Lý do:

1. Identity mutable có thể được dùng lại làm giá trị khởi đầu cho các nhánh. Nhiều nhánh cùng sửa một đối tượng có thể gây **data race**.
2. Phép `add` trên chính identity làm biến đổi giá trị vốn phải là phần tử trung hòa, phá điều kiện của phép rút gọn.
3. Khi kết hợp, `left` và `right` có thể tham chiếu đến cùng một đối tượng; `addAll` có thể nhân đôi phần tử hoặc dẫn đến kết quả không hợp lệ.

Nếu mục đích là gom phần tử thành danh sách, dùng **mutable reduction** qua `collect`:

```java
List<String> result = List.of("A", "B", "C").parallelStream()
        .collect(java.util.stream.Collectors.toList());

System.out.println(result); // [A, B, C]
```

Hoặc nếu muốn tạo chuỗi bằng `StringBuilder`, để collector tạo container riêng cho mỗi phần tích lũy rồi kết hợp:

```java
StringBuilder joined = List.of("Ja", "v", "a").parallelStream()
        .collect(
                StringBuilder::new,
                (builder, part) -> builder.append(part),
                (left, right) -> left.append(right)
        );

System.out.println(joined); // Java
```

Với chuỗi có dấu phân cách, `Collectors.joining(", ")` thường đơn giản hơn. `collect` là lựa chọn tự nhiên khi kết quả là một container mutable; `reduce` thích hợp cho phép kết hợp giá trị không cần sửa đối tượng được chia sẻ.

## 9. `reduce` không có nghĩa tất cả phép toán đều chính xác tuyệt đối

Điều kiện kết hợp của API và tính chính xác của kiểu số không hoàn toàn giống nhau. Các phép cộng trên `double` có thể khác nhau theo cách nhóm do làm tròn nhị phân:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Do đó:

```java
List<Double> values = List.of(1e16, -1e16, 1.0);

double sequential = values.stream()
        .reduce(0.0, Double::sum);

double parallel = values.parallelStream()
        .reduce(0.0, Double::sum);

System.out.println("Sequential: " + sequential);
System.out.println("Parallel: " + parallel);
// Không yêu cầu hai kết quả luôn giống nhau từng bit.
```

Trong nhiều ứng dụng số học, có thể chấp nhận sai số với dung sai được xác định từ yêu cầu nghiệp vụ. `DoubleStream.sum()` cho phép triển khai dùng thuật toán cộng có bù sai số và thường phù hợp hơn `reduce(0.0, Double::sum)` nếu mục đích duy nhất là tổng `double`. Khi cần phép cộng thập phân chính xác, cân nhắc `BigDecimal` tạo từ chuỗi decimal:

```java
import java.math.BigDecimal;

BigDecimal amount = List.of("0.10", "0.20", "0.30").stream()
        .map(BigDecimal::new)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(amount); // 0.60
```

Phép cộng `BigDecimal` không dùng `MathContext` là chính xác theo giá trị thập phân; đừng khởi tạo bằng `new BigDecimal(0.1)` khi mục tiêu là đúng `0.1` thập phân. Với số nguyên, `Integer::sum` và `Long::sum` có thể overflow; bài toán có giới hạn nghiêm ngặt có thể cần `BigInteger` hoặc phát hiện tràn bằng `Math.addExact` theo thuật toán thích hợp.

## 10. Liên hệ đến vòng đời, nguồn vô hạn và hiệu năng

`reduce` là **terminal operation**: nó tiêu thụ stream và trả về kết quả cuối. Không thể gọi một terminal operation khác trên chính đối tượng stream đã được tiêu thụ.

```java
var stream = List.of(1, 2, 3).stream();
int total = stream.reduce(0, Integer::sum);
System.out.println(total); // 6

// stream.count(); // Sai: stream đã được tiêu thụ.
```

Với nguồn vô hạn không có điều kiện dừng, `reduce` thông thường không thể hoàn tất vì phải duyệt hết các phần tử. Hãy chặn nguồn bằng `limit` nếu yêu cầu là xử lý một số lượng hữu hạn:

```java
import java.util.stream.Stream;

int sampleTotal = Stream.generate(() -> 2)
        .limit(5)
        .reduce(0, Integer::sum);

System.out.println(sampleTotal); // 10
```

Không đặt `reduce` lên `Stream.generate(...)` vô hạn mà không kiểm soát điểm dừng. Đối với nguồn liên quan đến tài nguyên như `Files.lines(path)`, dùng `try-with-resources` để đóng stream ngay cả khi có exception; `reduce` không tự giải phóng tài nguyên mà nhà cung cấp nguồn mở ra.

Về hiệu năng, `parallelStream()` có chi phí phân chia công việc và kết hợp kết quả. Một phép giảm đơn giản trên vài trăm phần tử có thể nhanh hơn khi chạy tuần tự. Chỉ chọn song song khi phép toán đúng hợp đồng, dữ liệu đủ lớn và phép đo thực tế chứng minh lợi ích. Không đưa side effect vào accumulator/combiner để “đếm số lần gọi”: framework không cam kết thứ tự và số lần kết hợp theo cấu trúc cố định.

## 11. Ví dụ tổng hợp có thể chạy (Java 17+)

Chương trình sau tổng hợp các quy tắc trên: identity đúng cho tổng/tích, `Optional` khi không có identity, phép nối chuỗi có tính kết hợp, overload ba đối số và thống kê bất biến.

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ReduceLawsDemo {
    record Line(String code, int quantity, long unitPriceCents) {}

    record Stats(long count, long sum) {
        Stats combine(Stats other) {
            return new Stats(count + other.count, sum + other.sum);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 4);

        int sum = numbers.parallelStream().reduce(0, Integer::sum);
        int product = numbers.parallelStream()
                .reduce(1, (a, b) -> a * b);
        System.out.println(sum);     // 9
        System.out.println(product); // 24

        Optional<Integer> max = numbers.stream().reduce(Integer::max);
        System.out.println(max.orElseThrow()); // 4
        System.out.println(Stream.<Integer>empty()
                .reduce(Integer::max).isEmpty()); // true

        String word = List.of("Ja", "v", "a").parallelStream()
                .reduce("", String::concat);
        System.out.println(word); // Java

        List<Line> lines = List.of(
                new Line("A", 2, 150L),
                new Line("B", 1, 425L),
                new Line("C", 3, 100L)
        );
        long revenue = lines.parallelStream().reduce(
                0L,
                (subtotal, line) -> subtotal
                        + line.quantity() * line.unitPriceCents(),
                Long::sum
        );
        System.out.println(revenue); // 1025

        Stats stats = numbers.parallelStream()
                .map(n -> new Stats(1, n))
                .reduce(new Stats(0, 0), Stats::combine);
        System.out.println(stats); // Stats[count=3, sum=9]
        System.out.println((double) stats.sum() / stats.count());
        // 3.0

        List<Integer> doubled = numbers.parallelStream()
                .map(n -> n * 2)
                .collect(Collectors.toList());
        System.out.println(doubled); // [4, 6, 8]
    }
}
```

Trong ví dụ, các giá trị đủ nhỏ nên không có overflow. Khi thiết kế nghiệp vụ thực, cần xác định miền số liệu, chính sách đối với dữ liệu rỗng và yêu cầu về tính tái lập trước khi chọn kiểu số và chế độ chạy.

## 12. Những lỗi thường gặp

| Cách nghĩ hoặc cách viết | Vấn đề | Cách xử lý |
|---|---|---|
| “Mọi toán tử nhị phân đều dùng được cho reduce song song” | Trừ/chia không kết hợp | Dùng phép kết hợp đúng hợp đồng hoặc thuật toán chuyên dụng |
| “Identity chỉ được sử dụng một lần” | Song song có thể dùng identity ở nhiều nhánh | Chọn phần tử trung hòa thật sự |
| “`reduce(10, Integer::sum)` tính tổng bình thường” | `10` là giá trị cộng thêm, không phải identity | Dùng `0` cho phép cộng |
| “`reduce(0, Integer::min)` trả min của số dương” | `0` có thể làm sai kết quả | Dùng overload `Optional` hoặc identity hợp lệ |
| “Phép nối chuỗi không giao hoán nên không thể reduce” | Nhầm tính kết hợp và giao hoán | Có thể reduce với nguồn có encounter order và identity `""` |
| “Accumulator cộng độ dài, combiner nhân vẫn ổn” | Vi phạm tương thích giữa accumulator và combiner | Chọn combiner cộng các tổng con |
| “Có thể dùng `new ArrayList<>()` làm identity rồi `add` trong reduce” | Identity mutable dùng chung và bị biến đổi | Dùng `collect` cho mutable container |
| “Chạy song song với `double` luôn đúng từng bit như tuần tự” | Phép cộng dấu phẩy động không kết hợp tuyệt đối | Dùng dung sai hoặc chiến lược số học phù hợp |
| “`reduce` tự dừng trên nguồn vô hạn” | Terminal operation cần tiêu thụ toàn bộ nguồn | Giới hạn nguồn hoặc chọn cách xử lý có điều kiện kết thúc |
| “Bật `parallel()` luôn giúp nhanh hơn” | Có overhead chia việc và kết hợp | Đo hiệu năng trên dữ liệu thực |

## 13. Tự kiểm tra

1. **Hai điều kiện cơ bản của `reduce(identity, accumulator)` là gì?** Accumulator có tính kết hợp; identity là phần tử trung hòa của phép kết hợp.
2. **Vì sao `reduce(1, (a, b) -> a * b)` dùng `1`?** Vì `1 * x = x * 1 = x`.
3. **Với danh sách `[2, 3]`, `reduce(5, Integer::sum)` trả gì nếu cộng tuần tự?** Trả `10`; nó đã cộng thêm identity sai `5`.
4. **Tính kết hợp có đồng nghĩa giao hoán không?** Không. Nối chuỗi có tính kết hợp nhưng `"ab"` khác `"ba"`.
5. **Vì sao `reduce(0, (a, b) -> a - b)` không phù hợp để chạy song song?** Phép trừ không kết hợp và `0` không trung hòa hai phía.
6. **Overload `reduce(BinaryOperator)` trả gì khi stream rỗng?** `Optional.empty()`, cho phép xử lý tình huống không có giá trị mà không tự đặt identity.
7. **Trong overload ba đối số, combiner có tác dụng gì?** Kết hợp các kết quả trung gian kiểu `U`; nó phải kết hợp được và tương thích với accumulator.
8. **Vì sao không dùng `StringBuilder` hoặc `ArrayList` mutable làm identity trong `reduce`?** Vì identity có thể bị dùng chung và thay đổi, phá hợp đồng và gây race; dùng `collect` để tạo các container tích lũy riêng.
9. **Vì sao tổng `double` tuần tự và song song có thể khác?** Thứ tự nhóm phép cộng khác làm thay đổi sai số làm tròn; cộng `double` không kết hợp tuyệt đối.
10. **Muốn tính trung bình từ các tổng con, phải lưu gì?** Cả tổng và số lượng; chỉ lấy trung bình của các trung bình không đủ nếu kích thước nhóm khác nhau.

**Ghi nhớ:** Hãy kiểm tra **phép kết hợp có tính kết hợp không**, **identity có trung hòa ở cả hai phía không**, và với overload ba đối số, **accumulator có tương thích với combiner không**. Khi những điều kiện này đúng, Java có thể chia và kết hợp dữ liệu một cách an toàn về mặt hợp đồng. Khi cần tích lũy trạng thái có thể thay đổi, hãy chọn `collect`; khi làm việc với số dấu phẩy động, tiếp tục đánh giá sai số và yêu cầu độ chính xác riêng.
