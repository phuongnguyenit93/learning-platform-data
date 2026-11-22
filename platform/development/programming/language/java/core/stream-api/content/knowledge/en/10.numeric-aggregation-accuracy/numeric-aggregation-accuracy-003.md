# Sai số dấu phẩy động và thứ tự cộng trong phép rút gọn

Trong Java Stream API, `reduce`, `sum` và các collector giúp tổng hợp một dãy số bằng cú pháp khai báo. Tuy nhiên, kết quả của phép cộng `double` không phải lúc nào cũng trùng với phép cộng số thực trong toán học. Hai pipeline cùng cộng những giá trị giống nhau có thể cho ra kết quả hơi khác chỉ vì **thứ tự cộng hoặc cách nhóm các phép cộng thay đổi**.

Bài này thuộc chương **Độ chính xác khi tổng hợp số** của module **JAVA_STREAM_API**. Ta sẽ đi từ biểu diễn số dấu phẩy động, hiểu điều kiện kết hợp của `reduce`, phân tích việc gộp kết quả khi chạy song song, sau đó lựa chọn giữa `reduce`, `DoubleStream.sum()`, `BigDecimal` và các biện pháp kiểm soát sai số. Kiến thức này giúp xây dựng pipeline `filter`, `map`, `reduce`, `collect` đúng hợp đồng, đồng thời đánh giá độ chính xác, trạng thái chia sẻ và hiệu năng.

## 1. Vì sao cộng `double` có thể có sai số?

Java dùng biểu diễn dấu phẩy động nhị phân theo IEEE 754 cho `float` và `double`. `double` có độ chính xác hữu hạn (53 bit significand, tính cả bit dẫn đầu ngầm định với số normal). Nhiều phân số thập phân quen thuộc **không có biểu diễn nhị phân hữu hạn**, nên phải làm tròn khi lưu hoặc trong mỗi phép tính.

```java
double a = 0.1;
double b = 0.2;
double actual = a + b;

System.out.println(actual);         // 0.30000000000000004
System.out.println(actual == 0.3);  // false
```

`0.1`, `0.2` và `0.3` trong mã nguồn đều được làm tròn thành giá trị `double` gần nhất có thể biểu diễn. Hai số đầu được cộng rồi làm tròn lần nữa; kết quả đó khác giá trị `double` được tạo trực tiếp từ literal `0.3`.

Điều này không có nghĩa Java tính sai: hệ thống đang tuân theo phép toán dấu phẩy động với độ chính xác hữu hạn. Để suy luận đúng về phép tổng hợp, cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Giá trị toán học lý tưởng | Phép tính trên số thực với độ chính xác không giới hạn | `0.1 + 0.2 = 0.3` |
| Giá trị lưu trong `double` | Xấp xỉ nhị phân của một số | Literal `0.1` không biểu diễn chính xác một phần mười |
| Kết quả phép toán dấu phẩy động | Kết quả đã làm tròn theo quy tắc số học của `double` | `0.1 + 0.2` in ra `0.30000000000000004` |
| Sai số tổng hợp | Sai khác tích lũy từ các giá trị đầu vào và các lần làm tròn | Tổng nhiều khoản rất nhỏ bên cạnh một khoản lớn |

Độ chính xác tương đối của `double` thường khoảng 15–17 chữ số thập phân có nghĩa; đây **không** phải cam kết rằng phép cộng hàng triệu số luôn đúng 15 chữ số cuối. Sai số còn phụ thuộc độ lớn, dấu và trình tự của các phép tính.

### 1.1. Khi số lớn che mất số nhỏ

```java
double large = 1e16;
double small = 1.0;

System.out.println(large + small == large); // true
```

Khoảng cách giữa hai giá trị `double` liên tiếp quanh `1e16` lớn hơn `1`. Vì vậy, cộng thêm `1` không làm thay đổi giá trị `double` sau khi làm tròn. Hiện tượng này đặc biệt quan trọng khi tổng hợp dữ liệu có chênh lệch rất lớn về độ lớn.

## 2. Phép cộng dấu phẩy động không có tính kết hợp tuyệt đối

Trong toán học trên số thực, tính kết hợp nói rằng:

```text
(a + b) + c = a + (b + c)
```

Với `double`, mỗi bước cộng đều có thể bị làm tròn, nên hai cách nhóm có thể trả kết quả khác nhau:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double leftGrouped  = (a + b) + c;
double rightGrouped = a + (b + c);

System.out.println(leftGrouped);  // 1.0
System.out.println(rightGrouped); // 0.0
```

Giải thích cụ thể:

1. `(1e16 + -1e16) + 1`: hai số lớn triệt tiêu thành `0`, sau đó cộng `1` nên kết quả là `1`.
2. `1e16 + (-1e16 + 1)`: ở bước cộng bên trong, `1` bị mất do làm tròn bên cạnh `-1e16`; bước cuối cho `0`.

Cùng ba giá trị đầu vào, cùng toán tử `+`, nhưng **cách nhóm** khác dẫn đến sai khác đúng `1.0`. Tổng chính xác theo số học trên các giá trị đó là `1.0`; cách nhóm bên phải đã làm mất đóng góp của phần tử nhỏ.

Sơ đồ cho thấy vị trí làm tròn:

```text
Nhóm bên trái                         Nhóm bên phải

  1e16 + (-1e16)                       -1e16 + 1
         |                                  |
         0                           -1e16 (làm tròn)
         |                                  |
        + 1                            + 1e16
         |                                  |
         1                                  0
```

**Hệ quả với Stream:** `reduce` chỉ có thể tự do chia nhỏ rồi kết hợp các kết quả trung gian mà không làm thay đổi ngữ nghĩa nếu phép tích lũy có tính kết hợp theo hợp đồng. Phép cộng `double` không bảo đảm kết hợp tuyệt đối ở cấp độ bit.

## 3. Cộng bằng `reduce` trong Stream API

Đối với `Stream<Double>`, một cách tổng hợp là:

```java
import java.util.List;

List<Double> values = List.of(2.5, 1.5, 3.0);

double total = values.stream()
        .reduce(0.0, Double::sum);

System.out.println(total); // 7.0
```

Ở đây:

- `0.0` là *identity* được dùng để khởi tạo phép rút gọn.
- `Double::sum` là một `BinaryOperator<Double>` kết hợp hai giá trị.
- `reduce` là terminal operation, kích hoạt việc tiêu thụ pipeline.

Tương tự, với `DoubleStream`:

```java
import java.util.stream.DoubleStream;

double total = DoubleStream.of(2.5, 1.5, 3.0)
        .reduce(0.0, Double::sum);
System.out.println(total); // 7.0
```

Overload có identity trả `double`; overload `reduce(DoubleBinaryOperator)` không có identity trả `OptionalDouble`, vì stream có thể rỗng:

```java
import java.util.OptionalDouble;

OptionalDouble totalMaybe = DoubleStream.empty()
        .reduce(Double::sum);
System.out.println(totalMaybe.isEmpty()); // true
```

### 3.1. Điều kiện kết hợp của `reduce`

Hợp đồng của `reduce(identity, accumulator)` yêu cầu accumulator có tính kết hợp; `identity` phải là phần tử trung hòa cho phép kết hợp. Đây là yêu cầu quan trọng vì Java Stream API có thể thực hiện giảm song song bằng cách tính nhiều tổng con rồi gộp chúng.

Đối với các số thực toán học, phép cộng có tính kết hợp. Đối với `double`, tính kết hợp chỉ là một xấp xỉ do giới hạn biểu diễn và làm tròn. Vì vậy, dùng `Double::sum` trong `reduce` hữu ích nhưng **không thể yêu cầu mọi cách chia nhóm đều cho cùng kết quả bit-for-bit**.

Ngoài ra, `+0.0` và `-0.0` khác nhau về bit dấu. Dùng `0.0` làm identity có ý nghĩa tự nhiên khi tính tổng số học thông thường, nhưng có thể làm thay đổi dấu của `-0.0` trong các trường hợp đặc biệt. Nếu ứng dụng cần giữ phân biệt signed zero, phải đặt chính sách cụ thể thay vì dựa vào phép tổng hợp mặc định.

### 3.2. Một ví dụ dễ bị ảnh hưởng bởi thứ tự

```java
import java.util.List;

List<Double> samples = List.of(1e16, -1e16, 1.0);

double reduced = samples.stream()
        .reduce(0.0, Double::sum);

System.out.println(reduced);
// Với lối cộng lần lượt theo thứ tự List: 1.0
```

Trên pipeline tuần tự đơn giản, ta thường quan sát phép cộng theo thứ tự phần tử của `List`. Tuy nhiên, mục đích của ví dụ không phải khẳng định mọi triển khai `reduce` sẽ luôn dùng đúng một cây phép cộng cố định: hợp đồng `reduce` chủ yếu yêu cầu toán tử có tính kết hợp để cho phép thực thi song song.

## 4. Vì sao `parallelStream().reduce(...)` có thể cho kết quả khác?

Trong stream song song, Java có thể chia dữ liệu thành các đoạn, rút gọn từng đoạn, sau đó kết hợp tổng con. Việc chia đoạn và kết hợp đó không bị buộc phải giống một phép cộng tuần tự từ trái sang phải.

```java
List<Double> samples = List.of(1e16, -1e16, 1.0);

double sequential = samples.stream()
        .reduce(0.0, Double::sum);

double parallel = samples.parallelStream()
        .reduce(0.0, Double::sum);

System.out.println("Sequential: " + sequential);
System.out.println("Parallel:   " + parallel);
// Không khẳng định hai dòng phải khác nhau hay phải giống nhau tuyệt đối.
```

Mỗi lần thực thi có thể tạo cách nhóm cộng hợp lệ theo chiến lược chia việc:

```text
Nguồn: [1e16, -1e16, 1]

Cách A: ((1e16 + -1e16) + 1) = 1

Cách B: (1e16 + (-1e16 + 1)) = 0
```

Java không cam kết `parallelStream()` phải dùng cách A hay cách B trong ví dụ. Kết quả thực tế có thể phụ thuộc kích thước dữ liệu, cách phân tách `Spliterator`, triển khai terminal operation và môi trường chạy. **Đừng viết bài kiểm thử yêu cầu tổng dấu phẩy động song song luôn chính xác bằng tổng tính theo một thứ tự tuần tự cụ thể.**

### 4.1. Encounter order và thứ tự cộng là hai vấn đề khác nhau

Nguồn `List` có encounter order xác định; `toList()` có thể bảo toàn thứ tự kết quả ngay cả khi pipeline song song. Nhưng **bảo toàn encounter order của phần tử không đồng nghĩa bảo toàn cách nhóm phép cộng** bên trong `reduce`.

```java
List<Double> values = List.of(1e16, -1e16, 1.0);

System.out.println(values.parallelStream().toList());
// [1.0E16, -1.0E16, 1.0]: thứ tự phần tử được giữ

System.out.println(values.parallelStream().reduce(0.0, Double::sum));
// Tổng chịu ảnh hưởng của cách kết hợp các tổng con
```

`sequential()` giúp yêu cầu xử lý tuần tự, nhưng **không biến số học dấu phẩy động thành số học chính xác**. Ngay cả khi luôn cộng tuần tự theo một thứ tự cố định, sai số làm tròn vẫn có thể tồn tại.

### 4.2. Không cập nhật biến tổng dùng chung trong lambda

```java
double[] total = {0.0};

// Không an toàn: nhiều thread cùng cập nhật total[0].
// values.parallelStream().forEach(x -> total[0] += x);
```

Việc đọc, cộng, rồi ghi vào `total[0]` có thể xảy ra đồng thời, gây *data race* và mất cập nhật. Kể cả thay bằng một bộ cộng thread-safe, thứ tự cộng vẫn có thể thay đổi và sai số số học vẫn tồn tại. Dùng `reduce` hoặc collector phù hợp để Java quản lý các tổng con; sau đó chọn chiến lược chính xác tương ứng với yêu cầu.

## 5. `reduce(Double::sum)` và `DoubleStream.sum()` khác nhau thế nào?

Java cung cấp terminal operation chuyên dụng `DoubleStream.sum()`:

```java
double total = DoubleStream.of(0.1, 0.2).sum();
System.out.println(total);
```

`DoubleStream.sum()` được tài liệu Java mô tả là có thể dùng **compensated summation** (cộng bù sai số) hoặc kỹ thuật khác để giảm sai số khi cộng các giá trị dấu phẩy động. Vì vậy, trong nhiều trường hợp, `sum()` có thể cho kết quả số học tốt hơn việc tự viết `reduce(0.0, Double::sum)`.

Điều cần phân biệt:

| Tiêu chí | `reduce(0.0, Double::sum)` | `DoubleStream.sum()` |
|---|---|---|
| Ý nghĩa | Rút gọn bằng toán tử do người viết chọn | Tính tổng theo terminal operation chuyên dụng |
| Kỹ thuật tính tổng | Áp dụng phép cộng `double` cho mỗi lần gộp | Triển khai có thể dùng cộng bù sai số/kỹ thuật khác |
| Kết quả chính xác toán học tuyệt đối | Không bảo đảm | **Không** bảo đảm |
| Phụ thuộc thứ tự/cách nhóm | Có thể | Có thể |
| Khả năng dùng với stream số nguyên thủy | Có, nhưng tổng quát hơn | Có trực tiếp trên `DoubleStream` |
| Khi nên chọn | Muốn minh họa `reduce` hoặc có toán tử riêng | Muốn tính tổng `double` thông thường |

Ví dụ:

```java
import java.util.stream.DoubleStream;

double viaReduce = DoubleStream.of(1e16, -1e16, 1.0)
        .reduce(0.0, Double::sum);
double viaSum = DoubleStream.of(1e16, -1e16, 1.0)
        .sum();

System.out.println("reduce = " + viaReduce);
System.out.println("sum    = " + viaSum);
// Đánh giá theo sai số và yêu cầu nghiệp vụ, không giả định luôn bằng nhau.
```

**Không nên tự suy ra** thuật toán `DoubleStream.sum()` phải dùng cách cộng bù cụ thể hoặc kết quả phải ổn định tuyệt đối qua mọi JDK, mọi cách chạy song song. API có quyền lựa chọn kỹ thuật và thứ tự cộng phù hợp.

### 5.1. Các terminal operation tổng hợp khác

`DoubleStream.average()`, `DoubleSummaryStatistics` và các collector như `Collectors.summingDouble`, `Collectors.averagingDouble`, `Collectors.summarizingDouble` cũng làm việc với số dấu phẩy động. Chúng hữu ích để biểu đạt mục đích nhưng **không xóa bỏ bản chất sai số của `double`**.

```java
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<Double> readings = List.of(0.1, 0.2, 0.3);

DoubleSummaryStatistics stats = readings.stream()
        .collect(Collectors.summarizingDouble(Double::doubleValue));

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // Tổng double xấp xỉ
System.out.println(stats.getAverage()); // Trung bình double xấp xỉ
```

Lưu ý: `average()` trên stream rỗng trả `OptionalDouble.empty()`; các API có identity hoặc statistics có thể chọn quy ước khác cho trường hợp rỗng. Không lấy `sum / count` khi `count == 0` nếu chưa định nghĩa chính sách xử lý.

## 6. Cộng số rất lớn, rất nhỏ và dữ liệu có dấu trái nhau

Khi các giá trị có độ lớn chênh lệch mạnh, phần nhỏ có thể bị mất trong từng bước cộng. Khi có các giá trị dương và âm gần như triệt tiêu, sai số đó có thể trở nên lớn **so với tổng thực**.

```java
List<Double> values = List.of(1e16, 1.0, -1e16);

double leftToRight = 0.0;
for (double value : values) {
    leftToRight += value;
}

System.out.println(leftToRight); // 0.0
// Tổng toán học của ba giá trị là 1.0.
```

Ở bước cộng `1e16 + 1`, giá trị `1` bị làm tròn mất. Sau đó trừ đi `1e16`, kết quả còn `0`. Nếu đổi thứ tự thành `1e16, -1e16, 1`, tổng tuần tự của ba giá trị lại ra `1`.

Một số trường hợp cần nhận diện thêm:

- **NaN:** nếu đầu vào chứa `Double.NaN`, phép cộng và kết quả tổng hợp có thể là `NaN`. Không kiểm tra `NaN` bằng `value == Double.NaN`; dùng `Double.isNaN(value)`.
- **Vô cực:** cộng các số hữu hạn cực lớn có thể tràn thành `Infinity`; tổng chứa cả `+Infinity` và `-Infinity` có thể thành `NaN`.
- **Dấu của số không:** `+0.0` và `-0.0` có bit khác nhau; một phép cộng hoặc identity `+0.0` có thể ảnh hưởng dấu.
- **Tràn số/thiếu độ chính xác ở đầu vào:** một giá trị đã bị làm tròn khi đọc thành `double` không thể được phục hồi đơn giản chỉ bằng đổi phương pháp cộng ở cuối.

Vì vậy, việc “tổng vẫn là một `double` hợp lệ” **không** tự chứng minh kết quả đủ chính xác cho ứng dụng.

## 7. Chiến lược tăng độ chính xác và tính tái lập

Không có một chiến lược duy nhất tối ưu cho mọi bài toán. Cần xác định rõ ứng dụng coi trọng **độ chính xác số học**, **tính lặp lại bit-for-bit**, hay **tốc độ**.

### 7.1. Ưu tiên `DoubleStream.sum()` cho tổng dấu phẩy động thông thường

```java
double total = readings.stream()
        .mapToDouble(Double::doubleValue)
        .sum();
```

`mapToDouble` chuyển từ `Stream<Double>` sang `DoubleStream` và tránh boxing không cần thiết trong phần tính tổng. `sum()` biểu đạt rõ mục đích và cho phép Java chọn kỹ thuật giảm sai số phù hợp. Tuy nhiên, kết quả vẫn là xấp xỉ.

### 7.2. Kiểm soát thứ tự cộng nếu tính tái lập quan trọng

Khi cần một quy trình tính tổng lặp lại được với đầu vào có thứ tự cố định, có thể yêu cầu tính tuần tự, bảo toàn thứ tự đầu vào và xác định rõ thuật toán tính:

```java
static double leftFold(List<Double> values) {
    double total = 0.0;
    for (double value : values) {
        total += value;
    }
    return total;
}
```

Đoạn mã này nêu rõ phép cộng theo thứ tự phần tử của `List`; nó **không** sửa sai số. Nếu muốn dùng stream, hãy tránh nguồn `unordered` và tránh giả định việc đổi sang `parallel()` vẫn giữ đúng cách nhóm của một vòng lặp cố định.

Đôi khi sắp xếp các giá trị theo độ lớn trước khi cộng có thể cải thiện độ chính xác, nhưng không phải quy tắc luôn đúng cho mọi phân bố dữ liệu, và đổi thứ tự có thể ảnh hưởng yêu cầu nghiệp vụ. Không mặc định `sorted()` là “thuốc chữa” sai số.

### 7.3. Cộng bù sai số

Các thuật toán như Kahan summation và Neumaier summation dùng biến bù để giữ lại một phần sai số làm tròn của các phép cộng trước. Chúng thường giúp giảm sai số so với cộng tuần tự đơn giản, nhất là khi tổng hợp nhiều giá trị có độ lớn chênh lệch.

Tuy nhiên:

- Cộng bù không làm cho kết quả `double` trở thành chính xác tuyệt đối.
- Thuật toán có trạng thái cần được thiết kế đúng nếu muốn chia dữ liệu và gộp kết quả song song.
- Không thể tùy tiện dùng một accumulator có trạng thái chia sẻ trong `parallelStream().forEach(...)` rồi coi đó là phép rút gọn an toàn.

Đối với nhiều ứng dụng, `DoubleStream.sum()` là điểm khởi đầu tốt trước khi tự viết thuật toán cộng bù và đo sai số.

### 7.4. Dùng `BigDecimal` khi cần phép cộng thập phân chính xác

Với số tiền hoặc dữ liệu yêu cầu cộng thập phân chính xác, `BigDecimal` thường phù hợp hơn `double`. **Khởi tạo từ chuỗi thập phân**, không mặc định lấy `new BigDecimal(0.1)`.

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> amounts = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.60
```

Với các đầu vào `BigDecimal` được tạo đúng từ chuỗi, phép `add` là phép cộng thập phân **chính xác**, không bị làm tròn nhị phân như `double`. Phép cộng `BigDecimal` không thay đổi đối tượng nguồn; kết quả là đối tượng mới.

```java
System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(new BigDecimal("0.1")); // 0.1
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

`new BigDecimal(0.1)` chuyển **giá trị nhị phân thực đã lưu** trong `double` sang dạng thập phân chính xác của giá trị đó. `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi chuẩn của `double`, thường tiện hơn, nhưng không phục hồi được độ chính xác thập phân gốc nếu dữ liệu đã bị làm tròn hoặc tính toán sai ở bước trước. Với dữ liệu tiền tệ, ưu tiên nhận và lưu ngay từ nguồn dưới dạng decimal.

Lưu ý rằng `BigDecimal.divide` có thể yêu cầu quy định precision hoặc `RoundingMode` nếu kết quả thập phân không hữu hạn; độ chính xác của phép **cộng** không đồng nghĩa mọi phép toán BigDecimal đều tự có kết quả thập phân hữu hạn.

### 7.5. Dùng đơn vị nguyên khi miền dữ liệu cho phép

Nếu nghiệp vụ cho phép quy đổi về đơn vị nhỏ nhất, ví dụ số tiền tính bằng xu hoặc số đo tính bằng đơn vị nguyên cố định, có thể tính tổng bằng `long` và chuyển đổi để hiển thị ở cuối:

```java
import java.util.stream.LongStream;

long totalCents = LongStream.of(125, 250, 375).sum();
System.out.println(totalCents); // 750 (xu)
```

Cộng số nguyên loại bỏ vấn đề làm tròn nhị phân của các phân số, nhưng **vẫn có thể tràn số**. `LongStream.sum()` không tự phát hiện overflow. Khi cần phát hiện tràn, dùng `Math.addExact` trong một thuật toán phù hợp, hoặc dùng `BigInteger`/`BigDecimal` tùy miền dữ liệu. Cũng cần xác định cách làm tròn khi chuyển giá trị thập phân sang đơn vị nguyên.

## 8. Kiểm thử các kết quả số học đúng cách

So sánh trực tiếp bằng `==` phù hợp khi muốn kiểm tra **bằng nhau đúng theo giá trị dấu phẩy động**, nhưng thường không phù hợp để kiểm tra kết quả tính toán xấp xỉ:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual == expected); // false
```

Với các giá trị hữu hạn và dung sai được xác định theo nghiệp vụ, có thể dùng một kiểm tra kết hợp sai số tuyệt đối và tương đối:

```java
static boolean approximatelyEqual(double a, double b,
                                  double absoluteTolerance,
                                  double relativeTolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return a == b; // NaN không được coi là bằng nhau.
    }
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return Math.abs(a - b)
            <= absoluteTolerance + relativeTolerance * scale;
}
```

```java
System.out.println(
        approximatelyEqual(0.1 + 0.2, 0.3, 1e-12, 1e-12)
); // true
```

Ví dụ này minh họa chiến lược cơ bản cho các giá trị hữu hạn ở miền thông thường. Với giá trị cực lớn, hiệu `a - b` hoặc phép tính ngưỡng có thể overflow; bài toán số học chuyên biệt cần phép so sánh được thiết kế cho miền dữ liệu và sai số dự kiến. **Không lấy một epsilon cố định tùy ý** rồi áp dụng cho mọi thang đo hoặc mọi phép tính.

Với `BigDecimal`:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y) == 0); // true: bằng giá trị số
System.out.println(x.equals(y));         // false: khác scale
```

Chọn `compareTo` khi muốn so sánh giá trị số; chọn `equals` nếu cả biểu diễn scale cũng là một phần yêu cầu.

## 9. Sai lầm thường gặp

| Suy luận/cách viết | Vấn đề | Cách xử lý |
|---|---|---|
| “Phép cộng toán học có tính kết hợp nên `Double::sum` cũng vậy” | Mỗi phép cộng `double` có thể làm tròn | Chấp nhận dung sai hoặc chọn kiểu số/thuật toán chính xác hơn |
| “Stream có encounter order nên reduce phải cộng đúng từ trái sang phải” | `reduce` có thể gộp tổng con theo cách khác | Không suy ra cây phép cộng từ thứ tự phần tử |
| “Chạy song song chỉ đổi tốc độ, kết quả double phải giống từng bit” | Thay cách nhóm cộng có thể thay kết quả | Dùng chiến lược tái lập hoặc so sánh có dung sai |
| “Thay `reduce` bằng `sum()` sẽ luôn có kết quả chính xác tuyệt đối” | `sum()` chỉ có thể giảm sai số, không xóa nó | Xác định yêu cầu precision và chọn `BigDecimal` nếu cần |
| “`new BigDecimal(0.1)` lưu đúng 0,1 thập phân” | Nó lưu chính xác giá trị double đã xấp xỉ | Dùng `new BigDecimal("0.1")` từ nguồn decimal |
| “Cứ thêm `sorted()` là cộng chính xác” | Đổi thứ tự chỉ có thể cải thiện một số trường hợp | Đo sai số; dùng thuật toán phù hợp |
| “Dùng `peek` hoặc `forEach` cộng vào biến chung là được” | Side effect có thể bị bỏ qua, gây data race hoặc sai thứ tự | Dùng terminal operation và collector an toàn |
| “Kiểm thử bằng `actual == expected` cho mọi tổng double” | Sai số làm tròn có thể khiến kiểm thử sai | So sánh bằng dung sai có căn cứ |
| “Cộng `long` luôn an toàn” | Có thể overflow | Giới hạn miền dữ liệu hoặc phát hiện tràn |
| “`Double.NaN == Double.NaN` là true” | NaN không bằng bất kỳ số nào, kể cả chính nó | Dùng `Double.isNaN` |

## 10. Ví dụ tổng hợp có thể chạy (Java 17+)

Chương trình sau kết nối ví dụ về thứ tự cộng với `reduce`, `DoubleStream.sum()` và `BigDecimal`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.DoubleStream;

public class FloatingPointReductionDemo {
    static double leftFold(List<Double> values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static boolean approximatelyEqual(double a, double b, double epsilon) {
        return Double.isFinite(a)
                && Double.isFinite(b)
                && Math.abs(a - b) <= epsilon;
    }

    public static void main(String[] args) {
        // 1. Sai số biểu diễn nhị phân.
        System.out.println(0.1 + 0.2); // 0.30000000000000004
        System.out.println(0.1 + 0.2 == 0.3); // false

        // 2. Tính không kết hợp.
        double a = 1e16, b = -1e16, c = 1.0;
        System.out.println((a + b) + c); // 1.0
        System.out.println(a + (b + c)); // 0.0

        // 3. Pipeline giảm tuần tự và song song.
        List<Double> numbers = List.of(a, b, c);
        double folded = leftFold(numbers);
        double reduced = numbers.stream().reduce(0.0, Double::sum);
        double parallel = numbers.parallelStream().reduce(0.0, Double::sum);
        double summed = numbers.stream().mapToDouble(Double::doubleValue).sum();

        System.out.println("Left fold: " + folded); // 1.0
        System.out.println("Reduce:    " + reduced);
        System.out.println("Parallel:  " + parallel);
        System.out.println("Sum:       " + summed);
        // Không đòi hỏi reduced/parallel/summed luôn giống nhau từng bit.

        // 4. Kiểm tra xấp xỉ ở miền giá trị nhỏ.
        System.out.println(approximatelyEqual(0.1 + 0.2, 0.3, 1e-12));
        // true

        // 5. Tổng thập phân chính xác từ dữ liệu nguồn dạng String.
        BigDecimal money = List.of("0.10", "0.20", "0.30").stream()
                .map(BigDecimal::new)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println(money); // 0.60

        // 6. Với bài toán tổng double thông thường, có API chuyên dụng.
        System.out.println(DoubleStream.of(2.5, 1.5, 3.0).sum()); // 7.0
    }
}
```

Ví dụ không khẳng định kết quả của `parallel` nhất thiết khác hoặc giống `reduced`, vì đó là điểm cần hiểu về quyền lựa chọn cách kết hợp của Stream API. Các dòng có kết quả được chú thích chính xác là những tình huống có giá trị rõ ràng với dữ liệu đã chọn.

## 11. Tự kiểm tra

1. **Vì sao `0.1 + 0.2 == 0.3` là `false`?** Vì các phân số thập phân này không biểu diễn chính xác bằng `double`; phép cộng tạo thêm bước làm tròn.
2. **Vì sao `(a+b)+c` có thể khác `a+(b+c)` khi `a=1e16`, `b=-1e16`, `c=1`?** Vì `1` có thể mất khi cộng với giá trị lớn trước khi hai số lớn triệt tiêu nhau.
3. **`reduce(0.0, Double::sum)` có bảo đảm kết quả giống nhau từng bit giữa tuần tự và song song không?** Không. Các phép cộng có thể được nhóm khác nhau.
4. **`DoubleStream.sum()` có phải phép cộng chính xác thập phân tuyệt đối không?** Không. Nó có thể dùng kỹ thuật giảm sai số nhưng vẫn trả kết quả `double`.
5. **Với dữ liệu tiền tệ dạng `"0.10"` và `"0.20"`, nên tạo `BigDecimal` từ đâu?** Từ chuỗi decimal (`new BigDecimal("0.10")`), tránh đưa dữ liệu qua `double` trước.
6. **`BigDecimal("1.0")` và `BigDecimal("1.00")` có cùng giá trị số không?** Có theo `compareTo`; `equals` khác vì scale.
7. **Dùng `parallelStream().forEach(x -> sum += x)` có đúng không?** Không an toàn: `sum` là trạng thái chia sẻ, có thể xảy ra race condition.
8. **Làm sao kiểm thử tổng `double`?** Xác định sai số chấp nhận được cho miền dữ liệu, xử lý NaN/vô cực rõ ràng và so sánh bằng dung sai thích hợp.
9. **Nếu chỉ cần tổng của một `DoubleStream` hữu hạn thông thường, nên thử API nào trước?** `DoubleStream.sum()`, vì API diễn đạt đúng phép tổng và có thể giảm sai số so với giảm bằng phép cộng đơn giản.

**Ghi nhớ:** sai số trong `double` đến từ biểu diễn nhị phân hữu hạn và các bước làm tròn. Do cộng `double` không kết hợp tuyệt đối, thay đổi thứ tự/cách nhóm trong `reduce`, đặc biệt khi chạy song song, có thể làm thay đổi tổng. Hãy chọn kiểu dữ liệu, thuật toán cộng, chế độ thực thi và chính sách kiểm thử theo yêu cầu **độ chính xác và tính tái lập** của bài toán.
