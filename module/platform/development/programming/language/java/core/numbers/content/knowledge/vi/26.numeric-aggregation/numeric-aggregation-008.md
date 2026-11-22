# Reduce song song và yêu cầu tính kết hợp trong tổng hợp số Java

## 1. Mục tiêu và vấn đề

Trong Java Stream, `reduce` gộp nhiều phần tử thành một kết quả: tổng, tích, giá trị lớn nhất, hoặc một đối tượng tổng hợp như tổng và số lượng mẫu. Khi xử lý **song song** bằng `parallel()` hay `parallelStream()`, Stream có thể chia đầu vào thành nhiều phần, tổng hợp mỗi phần riêng rồi gộp các kết quả đó lại. Vì **cách nhóm phép tính có thể thay đổi**, phép kết hợp (*reduction operator*) phải tuân thủ những quy tắc nhất định.

Với phép cộng số nguyên thông thường trong miền không tràn, mọi cách nhóm đều cho cùng một tổng:

```text
(2 + 3) + 5 = 10
2 + (3 + 5) = 10
```

Nhưng với phép trừ:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Đó là lý do **không thể lấy một phép gộp chạy được khi tuần tự rồi mặc định chuyển sang song song**. Kết quả song song chỉ đáng tin khi operation có tính kết hợp, giá trị khởi tạo là phần tử đơn vị phù hợp, và lambda không phụ thuộc trạng thái ngoài hoặc gây can thiệp nguồn.

Bài này tập trung vào **tổng hợp số** với `reduce`, gồm tổng/tích/giá trị thống kê; giải thích hợp đồng API, tương tác với `int`/`long`/`double`/`BigDecimal`, cách viết combiner và giải pháp thay thế bằng `sum()` hoặc `collect()`.

## 2. Reduce hoạt động ra sao?

Dạng đơn giản:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(sum); // 10
```

Đây là đoạn mã minh họa có thể đặt trong thân một phương thức Java. `rangeClosed(1, 4)` tạo `1, 2, 3, 4`; `reduce(0, Integer::sum)` dùng `0` làm giá trị đơn vị và `Integer::sum` làm phép kết hợp.

Một cách chia **minh họa** (Stream không cam kết sẽ chọn đúng cách chia này):

```text
Dữ liệu:           1    2    3    4
Nhóm thứ nhất:    (1 + 2)  = 3
Nhóm thứ hai:     (3 + 4)  = 7
Kết hợp:           3 + 7  = 10
```

Một lịch thực thi khác có thể nhóm `1 + (2 + (3 + 4))`. Vì phép cộng tương ứng có tính kết hợp nên không ảnh hưởng tới kết quả toán học. `parallel()` cho phép framework chia và gộp lại công việc; **không cam kết số luồng, cách chia, thứ tự thực thi hoặc tốc độ luôn nhanh hơn**.

Với `Stream<T>` có ba dạng `reduce` chính:

| Dạng API | Kết quả | Điểm chính |
| --- | --- | --- |
| `reduce(BinaryOperator<T> accumulator)` | `Optional<T>` | Không có identity; stream rỗng cho `Optional.empty()`. |
| `reduce(T identity, BinaryOperator<T> accumulator)` | `T` | Có identity; stream rỗng cho identity. |
| `reduce(U identity, BiFunction<U,? super T,U> accumulator, BinaryOperator<U> combiner)` | `U` | Kiểu kết quả có thể khác kiểu phần tử; combiner gộp kết quả giữa các nhánh song song. |

Với primitive stream, các biến thể `IntStream.reduce`, `LongStream.reduce` và `DoubleStream.reduce` tránh boxing không cần thiết. Khi chỉ cộng primitive, `sum()` thường diễn đạt ý định rõ ràng hơn `reduce(0, Integer::sum)`.

## 3. Tính kết hợp (*associativity*) là điều kiện cốt lõi

Một phép toán nhị phân `op` có **tính kết hợp** nếu đối với mọi `a`, `b`, `c` trong miền dữ liệu hợp lệ:

```text
op(op(a, b), c) == op(a, op(b, c))
```

Tính kết hợp cho phép thay đổi vị trí dấu ngoặc mà không đổi kết quả. Đây chính là điều reduction song song cần để gộp các đoạn được xử lý ở những nhóm khác nhau.

### 3.1. Ví dụ có tính kết hợp

- Tổng các số nguyên trong miền mà phép tính được định nghĩa đúng theo hợp đồng cần có: `(a + b) + c = a + (b + c)`.
- Tích các số nguyên tương tự: `(a × b) × c = a × (b × c)`, lưu ý giới hạn kiểu số và quy tắc tràn.
- `min(a, b)` hoặc `max(a, b)` với phép so sánh nhất quán.
- Phép cộng `BigInteger` và phép cộng `BigDecimal` **chính xác** theo giá trị số học.
- Gộp cặp thông tin `(sum, count)` bằng cộng tương ứng từng thành phần, khi kiểu lưu trữ có đủ miền giá trị.

### 3.2. Ví dụ không có tính kết hợp

- `a - b`: `(10 - 3) - 2 = 5`, còn `10 - (3 - 2) = 9`.
- `a / b`: thay đổi dấu ngoặc thường đổi kết quả, kể cả số hữu tỉ.
- Trung bình đôi `(a + b) / 2`: ba phần tử bị cho trọng số khác nhau tùy nhóm; không tương đương tổng chia cho số lượng.
- Cộng số dấu phẩy động `double` theo nghĩa phép tính máy có làm tròn: về toán học phép cộng là kết hợp, nhưng biểu diễn hữu hạn khiến `(a + b) + c` có thể khác `a + (b + c)`.
- Các phép cộng decimal có làm tròn ở **mỗi bước trung gian** bằng `MathContext` hoặc `setScale`: mất chữ số ở các nhóm khác nhau có thể tạo kết quả khác.

**Không nhầm kết hợp với giao hoán.** Tính giao hoán là `op(a,b) = op(b,a)`, nghĩa là đổi thứ tự toán hạng. Một phép như nối chuỗi có tính kết hợp nhưng không giao hoán. Với stream có encounter order xác định, reduction kết hợp có thể giữ được ý nghĩa thứ tự đó; còn với nguồn/operation không có yêu cầu thứ tự, đừng tự phụ thuộc vào thứ tự gộp để tạo kết quả mà phép toán không giao hoán.

## 4. Identity: phần tử đơn vị phải đúng

Trong `reduce(identity, accumulator)`, `identity` phải là **phần tử đơn vị** của operation:

```text
op(identity, x) == x
op(x, identity) == x
```

Một số ví dụ:

| Phép gộp | Identity phù hợp | Vì sao |
| --- | --- | --- |
| Cộng `int`/`long` | `0`/`0L` | `x + 0 = 0 + x = x` |
| Nhân số | `1` | `x × 1 = 1 × x = x` |
| `min` trên miền `int` đầy đủ | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |
| `max` trên miền `int` đầy đủ | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Cộng `BigDecimal` | `BigDecimal.ZERO` | Bằng nhau theo **trị số**; cân nhắc scale khi hợp đồng kết quả yêu cầu biểu diễn cụ thể. |
| Gộp cặp `(sum,count)` | `(0,0)` | Cộng từng thành phần không đổi kết quả. |

Identity sai dễ tạo lỗi khi song song vì nó có thể được dùng làm kết quả khởi tạo cho nhiều phần chia:

```java
// Sai: 10 không phải phần tử đơn vị của phép cộng.
int suspicious = java.util.stream.IntStream.of(1, 2, 3, 4)
        .parallel()
        .reduce(10, Integer::sum);
```

Không nên dựa vào một kết quả cụ thể của đoạn **cố ý sai** này: nó vi phạm contract identity, nên cách chia stream có thể làm phần `10` xuất hiện nhiều lần. Nếu thật sự muốn cộng thêm một lượng cố định `10` một lần, hãy tính tổng với `0` rồi cộng `10` ở **ngoài** phép reduce:

```java
int correct = 10 + java.util.stream.IntStream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, Integer::sum);
System.out.println(correct); // 20
```

Identity đúng còn quan trọng với **stream rỗng**: `IntStream.empty().reduce(0, Integer::sum)` trả `0`. Ngược lại, `IntStream.empty().reduce(Integer::sum)` trả `OptionalInt.empty()`; tùy nghiệp vụ, một tổng rỗng có thể là 0 còn min/max rỗng lại nên biểu diễn là “không có giá trị”.

## 5. Accumulator và combiner ở reduce ba tham số

Dạng tổng quát:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
```

Ở đây `T` là kiểu phần tử input, `U` là kiểu kết quả. `accumulator` tích lũy một phần tử `T` vào một kết quả `U`; `combiner` gộp **hai kết quả `U`** được tính từ các phần chia.

Ví dụ chuyển chuỗi số thành tổng kiểu `long`:

```java
long total = java.util.stream.Stream.of("10", "20", "30")
        .parallel()
        .reduce(
                0L,
                (sum, text) -> sum + Long.parseLong(text),
                Long::sum);

System.out.println(total); // 60
```

Để đúng với việc gộp song song, hợp đồng Java Stream yêu cầu:

1. `combiner` có **tính kết hợp**.
2. `identity` là **phần tử đơn vị** cho `combiner`.
3. **Tính tương thích giữa accumulator và combiner**: với mọi `u`, `t` hợp lệ,

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

Ví dụ trên: `accumulator(0, "20") = 20`. Khi có tổng phần trước `u = 10`, `combiner(10, 20) = 30`, giống `accumulator(10, "20") = 30`. Do đó kết quả không phụ thuộc cách chia.

**Ví dụ sai** là dùng accumulator cộng phần tử nhưng combiner trừ hai tổng. Dù một lần chạy tuần tự có thể cho đúng vì không phải gộp nhánh, phép gộp song song sẽ thay đổi ý nghĩa; không dùng:

```java
// Sai: accumulator cộng còn combiner trừ, vi phạm compatibility.
long incorrect = java.util.stream.Stream.of("10", "20", "30")
        .parallel()
        .reduce(0L,
                (sum, text) -> sum + Long.parseLong(text),
                (left, right) -> left - right);
```

Không cần chạy để “thử may mắn” một kết quả: đây là lỗi thiết kế cần sửa bằng `Long::sum`.

### Accumulator phải stateless và non-interfering

Lambda trong reduce không được phụ thuộc trạng thái thay đổi từ bên ngoài, hoặc sửa nguồn Stream trong lúc pipeline chạy. Đặc biệt, không nên ghi vào biến cộng dồn bên ngoài bằng `forEach`:

```java
int[] total = {0};
java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(n -> total[0] += n); // Sai: data race.
```

Kết quả có thể bị mất cập nhật vì nhiều luồng cùng đọc/sửa một phần tử mảng. Cách đúng cho phép cộng:

```java
int total = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();
System.out.println(total); // 500500
```

Một `AtomicInteger` có thể giúp tránh data race ở phép cộng đơn giản, nhưng dùng mutation bên ngoài vẫn làm ý định tổng hợp kém rõ ràng và có thể tạo contention; `reduce` hoặc `sum()` thể hiện cách tiếp cận phù hợp hơn.

## 6. Vì sao cộng double không thật sự có tính kết hợp?

`double` theo IEEE 754 biểu diễn hữu hạn chữ số nhị phân. Nhiều phép cộng cần làm tròn ngay khi tạo ra kết quả trung gian. Xét:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
```

Giải thích:

- `a + b = 0` nên `(a + b) + c = 1`.
- `b + c` được làm tròn về `-1e16` vì `1.0` quá nhỏ so với độ lớn của `-1e16` ở precision của `double`; sau đó cộng `a` cho `0`.

Vì vậy, khi `DoubleStream.parallel().sum()` hoặc một `reduce(0.0, Double::sum)` được thực hiện, **không nên kỳ vọng từng bit của kết quả luôn trùng với một vòng lặp cộng tuần tự theo thứ tự trái sang phải**. Cả thứ tự nhóm và thuật toán tổng có thể ảnh hưởng độ chính xác. Đặc biệt `DoubleStream.sum()` có thể dùng kỹ thuật cộng bù (*compensated summation*) để cải thiện độ chính xác, nhưng kết quả vẫn không được coi là phép cộng số thực chính xác tuyệt đối.

Tình huống đặc biệt của `NaN`, dương/âm vô cực và `-0.0` cũng cần được kiểm thử nếu bộ dữ liệu chứa chúng. Chẳng hạn `Double.sum()`/`DoubleStream.sum()` có những quy tắc riêng về `NaN` và vô cực; không tự so sánh các kết quả dấu phẩy động như thể chúng là số decimal chính xác.

Các chiến lược thực tế:

- Nếu cần **tổng decimal chính xác** theo nghiệp vụ, cân nhắc `BigDecimal` với cách khởi tạo và scale phù hợp.
- Nếu `double` đủ cho mô phỏng/thống kê, chấp nhận sai khác trong một dung sai được định nghĩa, đồng thời kiểm tra trường hợp giá trị lớn/nhỏ chênh lệch mạnh.
- Nếu cần tái hiện chính xác bit khi chạy ở những lịch thực thi khác nhau, kiểm soát thuật toán, thứ tự nhóm và môi trường; chỉ gọi `parallel()` không đảm bảo yêu cầu đó.
- Không dùng `==` làm kiểm tra tổng quát cho các tổng tính qua hai đường khác nhau khi phần sai số làm tròn được cho phép; thay vào đó so sánh theo ngưỡng có nghĩa và xử lý riêng `NaN`/vô cực.

## 7. BigDecimal: phép cộng chính xác và phép cộng làm tròn trung gian

`BigDecimal.add(other)` **không truyền `MathContext`** thực hiện phép cộng decimal chính xác, với scale kết quả phản ánh scale của các toán hạng. Về trị số, phép cộng chính xác có tính kết hợp nên là lựa chọn hợp lý khi cần cộng các khoản decimal trước lúc làm tròn theo nghiệp vụ:

```java
import java.math.BigDecimal;
import java.util.stream.Stream;

BigDecimal total = Stream.of("0.10", "0.20", "0.30")
        .map(BigDecimal::new)
        .parallel()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total.toPlainString()); // 0.60
```

Mỗi giá trị đầu vào có scale 2. Khi cộng chính xác, kết quả có scale phù hợp; việc dùng `BigDecimal.ZERO` làm identity hợp lý về trị số. Nếu dữ liệu có scale khác nhau, cần phân biệt **bằng nhau về trị số** (dùng `compareTo()`) và **bằng nhau theo `equals()`** (xét cả scale). Khi hợp đồng đầu ra yêu cầu scale cố định, chuẩn hóa ở ranh giới được định nghĩa bằng `setScale(requiredScale, roundingMode)`.

### Rounding ở từng lần cộng làm mất tính kết hợp

Nếu một lambda làm tròn sau **mỗi phép cộng**, tình huống thay đổi cách nhóm có thể tạo sai khác. Ví dụ với `HALF_UP` về scale 2:

```text
(a + b) + c, mỗi bước làm tròn:
a = 1.24, b = 0.005, c = 0.005
round2(1.24 + 0.005) = 1.25
round2(1.25 + 0.005) = 1.26

a + (b + c), mỗi bước làm tròn:
round2(0.005 + 0.005) = 0.01
round2(1.24 + 0.01) = 1.25
```

Biểu thức kiểm chứng bằng Java:

```java
BigDecimal a = new BigDecimal("1.24");
BigDecimal b = new BigDecimal("0.005");
BigDecimal c = new BigDecimal("0.005");
java.util.function.BinaryOperator<BigDecimal> roundedAdd =
        (x, y) -> x.add(y).setScale(2, java.math.RoundingMode.HALF_UP);

System.out.println(roundedAdd.apply(roundedAdd.apply(a, b), c)); // 1.26
System.out.println(roundedAdd.apply(a, roundedAdd.apply(b, c))); // 1.25
```

**Không truyền `roundedAdd` này vào `parallel().reduce(...)` nếu bạn kỳ vọng một kết quả độc lập cách phân nhóm.** Tương tự, `a.add(b, mathContext)` có thể làm tròn ở mỗi bước và không tự đảm bảo tính kết hợp theo nghĩa kết quả máy. Trong nghiệp vụ cho phép, hãy cộng ở độ chính xác thích hợp rồi làm tròn **một lần ở ranh giới cuối**:

```java
BigDecimal result = Stream.of(a, b, c)
        .parallel()
        .reduce(BigDecimal.ZERO, BigDecimal::add)
        .setScale(2, java.math.RoundingMode.HALF_UP);

System.out.println(result); // 1.25
```

Nếu quy tắc nghiệp vụ buộc phải làm tròn từng hóa đơn hoặc từng hạng mục trước khi cộng, đó là **phép tính khác** và phải được mô hình hóa rõ; không được tự ý đổi chính sách để tối ưu song song.

## 8. Tràn số nguyên và ý nghĩa của tổng

Trong Java, phép cộng `int`/`long` có thể tràn giới hạn kiểu số mà không ném lỗi. Phép cộng wraparound trên các kiểu nguyên có hành vi xác định, và thực tế phép cộng modulo theo độ rộng bit vẫn có tính kết hợp, nhưng **kết quả không còn bằng tổng số nguyên toán học bạn có thể đang mong đợi**.

Ví dụ:

```java
int result = java.util.stream.IntStream.of(
        Integer.MAX_VALUE, 1)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(result); // -2147483648
```

Đây là hành vi tràn `int`, không phải do Stream song song tự tạo lỗi. Nếu tổng có thể vượt miền `int`, cân nhắc `long` hoặc `BigInteger`:

```java
long exactWithinLong = java.util.stream.IntStream.of(
        Integer.MAX_VALUE, 1)
        .asLongStream()
        .parallel()
        .sum();

System.out.println(exactWithinLong); // 2147483648
```

`long` cũng có giới hạn. `Math.addExact` giúp **phát hiện** overflow bằng `ArithmeticException`, nhưng nó không phải phép toán luôn xác định cho mọi bộ ba số `long`: với những dãy chứa giá trị bù trừ, một cách nhóm có thể tràn trung gian trong khi cách khác không. Nếu yêu cầu tính chính xác cho tổng lớn không giới hạn, `BigInteger::add` an toàn hơn về miền giá trị.

## 9. Thiết kế tổng hợp số có nhiều đại lượng

Muốn tính cả tổng và số lượng để lấy trung bình, **trung bình đôi không có tính kết hợp**:

```text
avg2(avg2(2, 4), 6) = 4.5
avg2(2, avg2(4, 6)) = 3.5
```

Trong khi trung bình cộng của ba số là `(2 + 4 + 6) / 3 = 4.0`. Thay vì reduce bằng công thức trung bình hai số, gộp một trạng thái gồm **tổng + số đếm** rồi chia một lần cuối:

```java
record SumCount(long sum, long count) {}

SumCount left = new SumCount(10, 1);
SumCount right = new SumCount(20, 1);
SumCount joined = new SumCount(
        left.sum() + right.sum(),
        left.count() + right.count());

System.out.println(joined); // SumCount[sum=30, count=2]
```

Đây là ví dụ **đặt record vào một lớp hoặc source file Java hợp lệ** (không đặt trực tiếp trong thân phương thức nếu code phụ thuộc phạm vi ngoài mà không rõ). Chương trình hoàn chỉnh ở phần 11 cho thấy việc tạo record bất biến và reduce song song.

Về toán học, phép gộp hai `SumCount`:

```text
combine((s1, n1), (s2, n2)) = (s1 + s2, n1 + n2)
identity = (0, 0)
mean = sum / count   (chỉ sau khi hoàn thành reduce)
```

có tính kết hợp cho các phép cộng chính xác. Nếu dùng kiểu `long`, tổng và count vẫn cần nằm trong miền hợp lệ hoặc chuyển sang cấu trúc có miền giá trị lớn hơn.

Trường hợp cơ bản có thể dùng API thư viện:

```java
java.util.IntSummaryStatistics stats =
        java.util.stream.IntStream.of(10, 20, 30, 40)
                .parallel()
                .summaryStatistics();

System.out.println(stats.getSum());   // 100
System.out.println(stats.getCount()); // 4
System.out.println(stats.getAverage()); // 25.0
```

`summaryStatistics()` thể hiện rõ mục tiêu thống kê (count, sum, min, max, average) mà không cần tự viết combiner. Tuy nhiên, nó vẫn dùng các kiểu số primitive và có giới hạn tràn/độ chính xác phù hợp với kiểu đó.

## 10. Giữa reduce, collect, sum và summaryStatistics nên chọn gì?

| Mục tiêu | API phù hợp | Lý do |
| --- | --- | --- |
| Tổng `int`/`long`/`double` | `IntStream.sum()`, `LongStream.sum()`, `DoubleStream.sum()` | Dễ đọc, tránh boxing không cần thiết; vẫn tôn trọng giới hạn số học. |
| Tổng `BigDecimal` chính xác | `stream.reduce(BigDecimal.ZERO, BigDecimal::add)` | Phép gộp tạo giá trị BigDecimal bất biến. |
| Max/min của stream có thể rỗng | `max()`/`min()` hoặc `reduce(BinaryOperator)` | Kết quả `Optional*` phản ánh tình huống không có phần tử. |
| Sum + count + min + max primitive | `summaryStatistics()` | API chuyên dụng, không phải tự ghép nhiều reduce. |
| Gộp nhiều đại lượng khác nhau vào một immutable result | `reduce` với record và combiner có tính kết hợp | Kiểm soát rõ mô hình trạng thái và identity. |
| Gom phần tử vào danh sách/map/set hoặc bộ tích lũy mutable | `collect()` / `Collectors` | Mutable reduction có supplier, accumulator và combiner được thiết kế để hợp nhất container. |

**Đừng mutate một identity chung trong `reduce`.** Ví dụ:

```java
// Sai cho reduce: List mutable được dùng làm identity và bị sửa bên trong.
java.util.List<Integer> numbers = java.util.stream.Stream.of(1, 2, 3)
        .parallel()
        .reduce(
                new java.util.ArrayList<>(),
                (list, x) -> { list.add(x); return list; },
                (left, right) -> { left.addAll(right); return left; });
```

Mẫu này có thể vi phạm hợp đồng reduction và gây hành vi không xác định do dữ liệu dùng chung giữa các nhánh. Dùng `collect(java.util.stream.Collectors.toList())` để tạo collection, hoặc một collector thích hợp với yêu cầu sắp xếp/đồng thời. `reduce` thích hợp nhất với kiểu accumulator **bất biến** hoặc phép gộp không gây side effect.

## 11. Chương trình Java 17+ hoàn chỉnh: kiểm tra kết hợp và song song

Lưu thành **`ParallelNumberReductionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelNumberReductionDemo {
    record SumCount(long sum, long count) {}

    public static void main(String[] args) {
        int parallelSum = IntStream.rangeClosed(1, 1000)
                .parallel()
                .reduce(0, Integer::sum);
        int sequentialSum = IntStream.rangeClosed(1, 1000)
                .reduce(0, Integer::sum);
        System.out.println("parallel integer sum = " + parallelSum);
        System.out.println("same as sequential = "
                + (parallelSum == sequentialSum));

        BigDecimal decimalSum = Stream.of("0.10", "0.20", "0.30")
                .map(BigDecimal::new)
                .parallel()
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("exact decimal sum = "
                + decimalSum.toPlainString());

        double a = 1e16;
        double b = -1e16;
        double c = 1.0;
        System.out.println("floating left = " + ((a + b) + c));
        System.out.println("floating right = " + (a + (b + c)));

        BigDecimal x = new BigDecimal("1.24");
        BigDecimal y = new BigDecimal("0.005");
        BigDecimal z = new BigDecimal("0.005");
        java.util.function.BinaryOperator<BigDecimal> roundedAdd =
                (left, right) -> left.add(right)
                        .setScale(2, RoundingMode.HALF_UP);
        System.out.println("rounded left = "
                + roundedAdd.apply(roundedAdd.apply(x, y), z));
        System.out.println("rounded right = "
                + roundedAdd.apply(x, roundedAdd.apply(y, z)));

        SumCount summary = List.of(10L, 20L, 30L, 40L)
                .parallelStream()
                .map(n -> new SumCount(n, 1))
                .reduce(new SumCount(0, 0),
                        (left, right) -> new SumCount(
                                left.sum() + right.sum(),
                                left.count() + right.count()));
        System.out.println("sum = " + summary.sum());
        System.out.println("count = " + summary.count());
        System.out.println("average = "
                + ((double) summary.sum() / summary.count()));

        long parsedTotal = Stream.of("10", "20", "30")
                .parallel()
                .reduce(0L,
                        (sum, text) -> sum + Long.parseLong(text),
                        Long::sum);
        System.out.println("parsed total = " + parsedTotal);
    }
}
```

Biên dịch và chạy trong thư mục chứa file, bằng JDK 17 hoặc mới hơn:

```bash
javac ParallelNumberReductionDemo.java
java ParallelNumberReductionDemo
```

Kết quả chuẩn:

```text
parallel integer sum = 500500
same as sequential = true
exact decimal sum = 0.60
floating left = 1.0
floating right = 0.0
rounded left = 1.26
rounded right = 1.25
sum = 100
count = 4
average = 25.0
parsed total = 60
```

Các giá trị trong output là **kết quả có thể kiểm tra**: phép cộng `int` ở miền không tràn, `BigDecimal.add` chính xác và record tổng/số đếm có tính kết hợp; còn hai cặp “left/right” được nhóm tường minh để minh họa sai khác do làm tròn. Chương trình không dựa vào một lịch chia nhánh cụ thể để tạo ra kết quả stdout.

Lưu ý: **không chứng minh operator sai bằng việc chạy `parallel().reduce` đúng một lần và quan sát kết quả bất thường**. Có những lần chạy tình cờ nhóm giống tuần tự, vẫn cho kết quả “đẹp”. Chứng minh bằng điều kiện toán học và phản ví dụ với dấu ngoặc như trên đáng tin hơn.

## 12. Hiệu năng, side effects và đặc điểm của nguồn dữ liệu

`parallel()` không tự động tăng hiệu năng. Việc chia tác vụ, chuyển dữ liệu giữa các luồng và gộp kết quả có chi phí. Với tập nhỏ hoặc operation rất rẻ như cộng vài chục số, tính song song có thể **chậm hơn** tuần tự. Benchmark cần cùng dữ liệu, kiểm soát khởi động JIT, số lần đo và môi trường; tránh suy luận từ một lượt chạy.

Sự phân chia của `Spliterator` nguồn, kích thước dữ liệu, số nhân CPU, độ phức tạp của phép xử lý mỗi phần tử và chi phí của combiner đều ảnh hưởng kết quả. Stream song song thường sử dụng cơ chế fork/join, nhưng **không cam kết một tập worker cố định** hoặc trật tự thực thi dự đoán được cho mọi pipeline.

Đặt câu hỏi trước khi chọn song song:

1. Phép gộp có **kết hợp** trên miền số liệu và chính sách làm tròn đang dùng không?
2. Identity có là phần tử đơn vị đối với mọi phần gộp không?
3. Với dạng ba tham số, combiner có tương thích accumulator không?
4. Các lambda có stateless, non-interfering, không chia sẻ trạng thái mutable không?
5. Nếu có stream không có thứ tự cố định, kết quả có phụ thuộc thứ tự các phần tử không?
6. Kiểu số có thể tràn hay mất precision đáng kể không?
7. Có đủ khối lượng công việc để bù chi phí song song không?

Một lưu ý nhỏ về luồng dữ liệu: `forEach` trên stream song song có thể gọi action ở những luồng/thứ tự không xác định. `forEachOrdered` bảo đảm encounter order đối với nguồn có thứ tự nhưng cũng có thể tăng chi phí. Điều này **khác** với cách `reduce` phân nhóm phép gộp: ngay cả khi encounter order được bảo toàn, một phép tính không kết hợp vẫn có thể cho kết quả khác do dấu ngoặc thay đổi.

## 13. Lỗi điển hình và cách khắc phục

**Lỗi 1 — Dùng phép trừ/chia làm reducer.** Những phép này không kết hợp; phải viết lại mục tiêu bằng trạng thái có phép gộp đúng, hoặc thực hiện theo trật tự tuần tự nếu ý nghĩa bắt buộc phụ thuộc thứ tự.

**Lỗi 2 — Dùng `identity` khác phần tử đơn vị.** Với tổng, chọn `0` thay vì một số cộng sẵn; cộng phần bù một lần bên ngoài `reduce`.

**Lỗi 3 — Accumulator cộng nhưng combiner trừ hoặc nhân.** Kiểm tra phương trình tương thích; một hàm combiner có tên “merge” không đủ, nó phải gộp đúng ngữ nghĩa của accumulator.

**Lỗi 4 — Mutate object identity hoặc biến ngoài.** Dùng immutable value trong `reduce`; dùng `collect` cho container mutable; tránh data race do `forEach`.

**Lỗi 5 — Cho rằng tổng `double` luôn giống từng bit khi tuần tự/song song.** Không đúng với floating point; cần kiểm tra dung sai hoặc một thuật toán có định nghĩa thứ tự gộp rõ ràng.

**Lỗi 6 — Làm tròn từng bước với `BigDecimal` rồi kỳ vọng tính kết hợp.** `add(..., MathContext)` hay `setScale` sau mỗi lần cộng có thể cho kết quả phụ thuộc cách nhóm; khi nghiệp vụ cho phép, cộng chính xác trước rồi round một lần.

**Lỗi 7 — Tính trung bình qua phép `(a+b)/2` lặp lại.** Cách nhóm làm thay đổi trọng số. Hãy tổng hợp `sum/count` rồi chia cuối.

**Lỗi 8 — Bỏ qua overflow.** `int`/`long` có thể wraparound; dùng kiểu rộng hơn hoặc `BigInteger` nếu tổng toán học phải chính xác.

**Lỗi 9 — Giả định kết quả nhanh hơn chỉ nhờ `parallel()`.** Đo lường mới quyết định; nhiều pipeline đơn giản hợp lý hơn khi chạy tuần tự.

**Lỗi 10 — Dùng equality nhầm mức ý nghĩa.** Với decimal có scale khác nhau, `BigDecimal.equals()` xét scale còn `compareTo()` xét trị số; với `double`, dùng kiểm tra số học có nhận thức về làm tròn, `NaN` và vô cực.

## 14. Tự kiểm tra

**Câu 1.** Khi giảm `Stream.of(10, 3, 2)` bằng phép trừ, vì sao `parallel()` không có kết quả toán học ổn định độc lập cách nhóm?

**Đáp án:** `(10 - 3) - 2 = 5` nhưng `10 - (3 - 2) = 9`; phép trừ không kết hợp.

**Câu 2.** Identity phù hợp của phép cộng và phép nhân là gì?

**Đáp án:** `0` và `1`. Identity phải trung hòa phần tử khi đứng ở cả hai phía của phép gộp.

**Câu 3.** Dạng `reduce(0L, accumulator, combiner)` đòi phương trình tương thích nào?

**Đáp án:** `combiner(u, accumulator(identity, t)) == accumulator(u, t)`, ngoài tính kết hợp của combiner và tính đơn vị của identity.

**Câu 4.** Vì sao `(1e16 + -1e16) + 1.0` có thể khác `1e16 + (-1e16 + 1.0)` với `double`?

**Đáp án:** Mỗi phép cộng bị giới hạn bởi độ chính xác dấu phẩy động. Phép cộng `-1e16 + 1.0` làm mất số 1.0 do làm tròn, dẫn đến `0.0` ở nhóm bên phải.

**Câu 5.** Có nên reduce song song bằng `(x,y) -> x.add(y).setScale(2, HALF_UP)`?

**Đáp án:** Không nếu cần kết quả độc lập cách chia. Phép cộng có làm tròn sau từng bước không kết hợp; ví dụ `1.24, 0.005, 0.005` cho `1.26` và `1.25` theo cách nhóm.

**Câu 6.** Muốn tính trung bình hàng triệu phần tử, vì sao không dùng reducer `(a+b)/2`?

**Đáp án:** Nó không giữ cùng trọng số của từng quan sát khi gộp nhiều lần. Gộp một state có tổng và số đếm, hoặc dùng `summaryStatistics()` theo yêu cầu độ chính xác.

**Câu 7.** Tổng `Integer.MAX_VALUE + 1` bằng `-2147483648` có phải lỗi do parallel reduce không?

**Đáp án:** Không. Đó là tràn kiểu `int`. Chọn `long`/`BigInteger` khi tổng toán học vượt miền `int`.

**Câu 8.** Với stream rỗng, `reduce(0, Integer::sum)` và `reduce(Integer::sum)` khác nhau thế nào?

**Đáp án:** Dạng có identity trả `0`; dạng không identity trả `Optional.empty()` hoặc `OptionalInt.empty()` đối với primitive stream.

**Câu 9.** Có thể dùng `Collectors.toList()` thay vì mutate `ArrayList` bên trong `reduce` không?

**Đáp án:** Có, đó là mục đích của `collect` dành cho mutable reduction. Accumulator của `reduce` nên tuân thủ contract và tránh chia sẻ mutation.

**Câu 10.** Điều kiện toán học đủ để nhận một phép tổng hợp làm reduction song song đúng về mặt ngữ nghĩa là gì?

**Đáp án:** Phép gộp có tính kết hợp trên miền hợp lệ, identity trung hòa, combiner tương thích accumulator ở dạng ba tham số; đồng thời các lambda phải stateless và non-interfering. Với số thực máy và phép làm tròn, còn phải quyết định nghĩa của “đúng” theo hợp đồng độ chính xác.

## 15. Tài liệu chính thức

- [Java SE 17 — Stream.reduce](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): overload, identity, yêu cầu associativity, stateless/non-interfering và phương trình compatibility.
- [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): reduce, sum, summaryStatistics và primitive stream.
- [Java SE 17 — DoubleStream.sum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html#sum()): hành vi tổng dấu phẩy động và chú ý về độ chính xác.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): cộng chính xác, MathContext, scale và rounding.

**Ghi nhớ:** Reduce song song được phép thay đổi cách **phân nhóm** các phần tử. Phép gộp đúng cần **tính kết hợp**, **identity** chuẩn, **combiner** tương thích và lambda không can thiệp trạng thái. Cộng `double` hoặc `BigDecimal` có làm tròn ở bước trung gian có thể đổi kết quả theo nhóm; hãy đặt chính sách độ chính xác và ranh giới làm tròn rõ ràng trước khi lựa chọn parallel reduction.
