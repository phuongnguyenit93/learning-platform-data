# Chọn BigDecimal cho yêu cầu tính toán thập phân chính xác trong Java Stream

## 1. Bài toán và mục tiêu

Trong Java, các primitive stream như `IntStream`, `LongStream`, `DoubleStream` giúp xử lý số nguyên và số thực nguyên thủy mà không phải boxing từng phần tử. Tuy nhiên, **tốc độ và tính tiện lợi của `DoubleStream` không đồng nghĩa với khả năng biểu diễn chính xác mọi số thập phân**.

Nếu ứng dụng phải xử lý **giá tiền, hóa đơn, thuế, lãi suất, tỷ lệ cần quy tắc làm tròn xác định, hoặc số liệu thập phân đòi hỏi tính toán đúng chữ số đã nhập**, kiểu `BigDecimal` thường phù hợp hơn `double`. Điểm cần phân biệt là:

- `double` là số dấu phẩy động nhị phân theo IEEE 754, có tập giá trị biểu diễn hữu hạn; nhiều số thập phân như `0.1` không có biểu diễn nhị phân chính xác.
- `BigDecimal` lưu số theo **unscaled integer × 10^(-scale)**, nhờ đó có thể giữ chính xác các giá trị và phép cộng/nhân thập phân, nếu nguồn đầu vào được tạo đúng và các phép chia/làm tròn được thiết kế rõ.
- Java có `IntStream`, `LongStream` và `DoubleStream`, **không có `BigDecimalStream` chuẩn**. Với `BigDecimal`, ta thường dùng `Stream<BigDecimal>`, `map` và `reduce`; khi bắt đầu từ primitive stream, dùng `mapToObj(...)` để chuyển phần tử thành `BigDecimal`.
- Chuyển một kết quả `double` đã sai số sang `BigDecimal` **không thể tự khôi phục chính xác giá trị thập phân mà nghiệp vụ vốn mong muốn**.

Mục tiêu của bài là biết khi nào chọn `BigDecimal`, tạo số chính xác từ đầu vào, tính tổng bằng Stream, đặt scale và rounding đúng chỗ, đồng thời tránh những lỗi khi dùng các API primitive stream.

## 2. Vì sao `double` không luôn đúng với yêu cầu thập phân?

Các số `double` dùng cơ số 2. Một số như `0.5` có biểu diễn nhị phân hữu hạn, nhưng `0.1` và `0.2` thì không. Giá trị xấp xỉ này có thể bộc lộ khi cộng:

```java
System.out.println(0.1 + 0.2);
```

Đầu ra:

```text
0.30000000000000004
```

Đây không phải “Java cộng sai”; đó là hậu quả của cách số nhị phân hữu hạn biểu diễn giá trị thập phân. `DoubleStream.sum()` cũng làm việc trên `double`, vì vậy **không biến phép tính thành số học thập phân chính xác**.

Với `BigDecimal` được tạo từ chuỗi thập phân:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal result = a.add(b);
System.out.println(result.toPlainString());
```

Kết quả:

```text
0.3
```

Đoạn ví dụ thứ hai nằm trong một phương thức, cần import `java.math.BigDecimal`. Ở đây hai giá trị 0.1 và 0.2 được lưu theo thập phân đúng như cách viết; phép cộng không bắt buộc trải qua biểu diễn `double`.

**Không nên hiểu rằng `BigDecimal` tự giải quyết mọi vấn đề độ chính xác.** Số thập phân vô hạn như `1 / 3` cần chỉ định precision/scale và quy tắc làm tròn. Các quy tắc tính tiền như “làm tròn từng dòng hay làm tròn sau khi cộng” vẫn là quyết định nghiệp vụ, không phải hành vi tự đoán của kiểu dữ liệu.

## 3. Khi nào nên chọn kiểu nào?

| Nhu cầu | Kiểu/luồng thường phù hợp | Lý do |
| --- | --- | --- |
| Đếm số lượng, chỉ số, giá trị nguyên trong phạm vi `int` | `int`, `IntStream` | Chính xác với số nguyên trong phạm vi; không boxing từng phần tử |
| Tổng số nguyên lớn hơn phạm vi `int` nhưng trong phạm vi `long` | `long`, `LongStream` | Vẫn là số nguyên chính xác trong phạm vi |
| Dữ liệu đo lường, khoa học, mô phỏng chấp nhận xấp xỉ nhị phân | `double`, `DoubleStream` | Hỗ trợ tính toán dấu phẩy động hiệu quả |
| Tiền tệ, thuế, tỷ lệ cần giữ chữ số thập phân và quy tắc rounding rõ | `BigDecimal`, `Stream<BigDecimal>` | Mô hình thập phân theo scale và phép toán chính xác có kiểm soát |
| Tiền biểu diễn bằng số nguyên đơn vị nhỏ nhất (ví dụ đồng/xu không chia nhỏ thêm) | `long` / `LongStream` với kiểm tra tràn số | Số nguyên cũng chính xác nếu quy ước đơn vị và giới hạn được kiểm soát |
| Số nguyên có độ lớn vượt giới hạn `long` | `BigInteger` | Số nguyên tùy ý độ lớn; không cần scale |

Chọn `BigDecimal` khi yêu cầu cần tính thập phân **theo đúng chữ số và cách làm tròn**, không chỉ vì dữ liệu có dấu chấm. Với ứng dụng khoa học cần tốc độ và chấp nhận sai số trong giới hạn xác định, `double` thường vẫn là lựa chọn đúng.

Ngược lại, `BigDecimal` không ngăn lỗi thiết kế như sai tỷ lệ, sai thời điểm rounding, chuyển đổi đơn vị nhầm hoặc thiếu validation. Sự chính xác của **kiểu số** chỉ là một phần của sự chính xác **nghiệp vụ**.

## 4. Khởi tạo `BigDecimal` đúng: tránh đưa sai số `double` vào

### 4.1. Ba cách khởi tạo cần phân biệt

```java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal canonical = BigDecimal.valueOf(0.1);
BigDecimal binaryExpansion = new BigDecimal(0.1);
```

Đây là đoạn mã nằm trong phương thức, cần import `BigDecimal`.

- `new BigDecimal("0.1")`: **tạo số thập phân chính xác từ văn bản**; là lựa chọn rõ nhất khi nhận giá trị thập phân cần độ chính xác.
- `BigDecimal.valueOf(0.1)`: chuyển giá trị `double` theo biểu diễn chuỗi của `Double.toString(double)`; thường cho `0.1` trong ví dụ này. Tuy nhiên nếu upstream đã tính sai số, phương thức không thể biết giá trị mục tiêu ban đầu.
- `new BigDecimal(0.1)`: tạo BigDecimal biểu diễn **đúng giá trị nhị phân xấp xỉ đang lưu trong double**, nên thường chứa rất nhiều chữ số thập phân ngoài mong đợi.

**Quy tắc an toàn:** dữ liệu tiền đọc từ tệp/JSON/database hoặc user input nên được chuyển từ **chuỗi thập phân** hoặc từ loại decimal đã có ý nghĩa, tránh đi qua `double`. Nếu một thư viện đã trả `double`, phải biết rõ hợp đồng của nguồn trước khi chọn cách chuyển đổi.

### 4.2. Ví dụ chạy được: nhìn thấy sai khác

Tạo `BigDecimalCreationDemo.java`:

```java
import java.math.BigDecimal;

public class BigDecimalCreationDemo {
    public static void main(String[] args) {
        BigDecimal fromText = new BigDecimal("0.1");
        BigDecimal viaValueOf = BigDecimal.valueOf(0.1);
        BigDecimal fromDouble = new BigDecimal(0.1);

        System.out.println("double sum=" + (0.1 + 0.2));
        System.out.println("decimal sum=" +
                new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("text=" + fromText.toPlainString());
        System.out.println("valueOf=" + viaValueOf.toPlainString());
        System.out.println("equal by value=" +
                (fromText.compareTo(viaValueOf) == 0));
        System.out.println("new double equals text=" +
                fromDouble.equals(fromText));
        System.out.println("converted late=" +
                BigDecimal.valueOf(0.1 + 0.2).toPlainString());
    }
}
```

Chạy Java 17+:

```bash
javac BigDecimalCreationDemo.java
java BigDecimalCreationDemo
```

Output:

```text
double sum=0.30000000000000004
decimal sum=0.3
text=0.1
valueOf=0.1
equal by value=true
new double equals text=false
converted late=0.30000000000000004
```

Giá trị `converted late` cho thấy **không nên cộng bằng `double` trước rồi chuyển sang `BigDecimal` để mong tự sửa sai số**. Nếu nguồn là chuỗi `"0.1"` và `"0.2"`, chuyển cả hai sang `BigDecimal` **trước phép cộng**.

`BigDecimal.valueOf(long)` và `BigDecimal.valueOf(long unscaledValue, int scale)` là những API khác: khi bắt đầu từ số nguyên, chúng xây dựng giá trị chính xác; ví dụ `BigDecimal.valueOf(12345L, 2)` tương ứng `123.45`.

## 5. Không có primitive stream cho BigDecimal: dùng `Stream<BigDecimal>`

Các primitive stream tiêu chuẩn gồm:

- `IntStream`: giá trị `int`, có `sum()`, `average()`, `mapToObj(...)`.
- `LongStream`: giá trị `long`, có các phép toán tương tự cho số nguyên dài.
- `DoubleStream`: giá trị `double`, phù hợp với số thực nhị phân.
- Không có `BigDecimalStream` trong thư viện Java chuẩn.

Để tính tổng các giá trị thập phân, một cách thông dụng là:

```java
BigDecimal total = values.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Đây là đoạn mã trong phương thức, giả định `values` có kiểu `List<BigDecimal>` hoặc collection tương thích, cần import `java.math.BigDecimal`. `BigDecimal.ZERO` là **giá trị đơn vị** cho phép cộng: `0 + x = x`. `BigDecimal::add` nối hai phần tử thành tổng.

Với stream rỗng, phép `reduce(BigDecimal.ZERO, ...)` trả `BigDecimal.ZERO`; không cần gọi `Optional.get()` và không có trường hợp thiếu tổng.

Khi dữ liệu là primitive nhưng mỗi đơn vị cần chuyển sang decimal, dùng `mapToObj(...)` thay vì làm tiếp bằng `DoubleStream`:

```java
BigDecimal total = IntStream.of(10, 20, 30)
        .mapToObj(cents -> BigDecimal.valueOf(cents, 2))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Đoạn mã nằm trong phương thức với import `IntStream` và `BigDecimal`. Số nguyên 10, 20, 30 đại diện **đơn vị nhỏ nhất**; `BigDecimal.valueOf(cents, 2)` tương ứng 0.10, 0.20, 0.30; tổng là `0.60`. Đây là chuyển đổi từ **int chính xác** sang BigDecimal chính xác, khác với chuyển từ giá trị `double` gần đúng.

Nếu muốn tiếp tục xử lý kiểu BigDecimal bằng `map` hoặc `filter`, các phương thức Stream hoạt động bình thường; chỉ không có tiện ích `BigDecimalStream.sum()` trong Java chuẩn. Dùng `reduce` với một phép toán phù hợp.

## 6. Ví dụ độc lập: tính tổng decimal bằng Stream và từ số xu

Tạo tệp `BigDecimalStreamDemo.java`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.IntStream;

public class BigDecimalStreamDemo {
    public static void main(String[] args) {
        List<BigDecimal> prices = List.of(
                new BigDecimal("10.25"),
                new BigDecimal("0.10"),
                new BigDecimal("2.65")
        );

        BigDecimal total = prices.stream()
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal fromCents = IntStream.of(1025, 10, 265)
                .mapToObj(cents -> BigDecimal.valueOf(cents, 2))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println("total=" + total.toPlainString());
        System.out.println("cents total=" + fromCents.toPlainString());
        System.out.println("empty=" +
                List.<BigDecimal>of().stream()
                        .reduce(BigDecimal.ZERO, BigDecimal::add));
    }
}
```

Biên dịch/chạy:

```bash
javac BigDecimalStreamDemo.java
java BigDecimalStreamDemo
```

Output:

```text
total=13.00
cents total=13.00
empty=0
```

Phân tích:

1. Các số được tạo từ chuỗi nên biểu diễn thập phân chính xác.
2. `BigDecimal::add` được dùng để gộp từng phần tử vào tổng; giá trị 10.25 + 0.10 + 2.65 bằng 13.00.
3. `mapToObj` chuyển số nguyên cent thành `BigDecimal` có scale 2. Giá trị từ `1025` cent là 10.25.
4. Với nguồn rỗng, identity `BigDecimal.ZERO` có scale 0 nên in là `0`, **không tự thành `0.00`**. Nếu nghiệp vụ muốn hiển thị hai chữ số thập phân, có thể chuẩn hóa tổng bằng `setScale(2)` ở ranh giới xuất dữ liệu.

**Không nhầm:** `IntStream.sum()` trả `int` và phép cộng có thể tràn vùng giá trị; `LongStream.sum()` cũng có thể tràn `long`. Khi yêu cầu số tiền có thể vượt giới hạn primitive, `BigDecimal` là lựa chọn thích hợp, hoặc phải kiểm soát tràn và giới hạn bằng nghiệp vụ.

## 7. Tính hóa đơn: tổng, thuế và rounding

Một ứng dụng thực tế thường gồm các dòng hàng có số lượng nguyên và đơn giá thập phân. Có thể chuyển mỗi dòng thành thành tiền, rồi cộng bằng BigDecimal.

Lưu tệp `DecimalInvoiceDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

public class DecimalInvoiceDemo {
    record Line(String sku, int quantity, BigDecimal unitPrice) {
        Line {
            Objects.requireNonNull(sku);
            Objects.requireNonNull(unitPrice);
            if (quantity < 0) {
                throw new IllegalArgumentException("Negative quantity");
            }
        }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("BOOK", 2, new BigDecimal("19.99")),
                new Line("PEN", 3, new BigDecimal("5.00")),
                new Line("BAG", 1, new BigDecimal("14.99"))
        );

        BigDecimal subtotal = lines.stream()
                .map(Line::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal taxRate = new BigDecimal("0.075");
        BigDecimal tax = subtotal.multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal grandTotal = subtotal.add(tax);

        System.out.println("subtotal=" + subtotal.toPlainString());
        System.out.println("tax=" + tax.toPlainString());
        System.out.println("total=" + grandTotal.toPlainString());
    }
}
```

Chạy:

```bash
javac DecimalInvoiceDemo.java
java DecimalInvoiceDemo
```

Output:

```text
subtotal=69.97
tax=5.25
total=75.22
```

Các bước:

- `19.99 × 2 = 39.98`; `5.00 × 3 = 15.00`; `14.99 × 1 = 14.99`; tổng là `69.97`.
- Thuế 7,5% được biểu diễn là tỷ lệ `0.075`, không phải `7.5`. Tích `69.97 × 0.075 = 5.24775`.
- Trong ví dụ **quy tắc nghiệp vụ giả định** là làm tròn số thuế đến 2 chữ số thập phân bằng `HALF_UP`, nên thuế thành `5.25`.
- Tổng thanh toán là `69.97 + 5.25 = 75.22`.

Không thể suy ra một quy tắc làm tròn thuế chuẩn cho mọi quốc gia, hóa đơn hay tổ chức từ ví dụ này. Cần theo quy định và nghiệp vụ thực tế: làm tròn từng dòng hay toàn hóa đơn, loại tiền có bao nhiêu chữ số thập phân, xử lý hoàn tiền và thuế suất. Một model lưu giá tiền nên công bố rõ currency và scale mong muốn.

**Chú ý:** dùng `Stream<BigDecimal>` để tính thành tiền không làm thay đổi các đối tượng `Line`. `BigDecimal` là immutable: các phương thức `add`, `multiply`, `setScale` trả **đối tượng kết quả**, không chỉnh sửa chính receiver.

## 8. Scale, precision và biểu diễn: vì sao `equals` khác `compareTo`?

`BigDecimal` biểu diễn giá trị bằng phần không scale và scale. Ví dụ:

```text
1.0  = 10   × 10^(-1)   (scale 1)
1.00 = 100  × 10^(-2)   (scale 2)
```

Chúng bằng nhau về **giá trị số** nhưng có biểu diễn và scale khác nhau. Vì vậy:

- `a.compareTo(b) == 0` kiểm tra bằng nhau theo **giá trị số**.
- `a.equals(b)` xem xét cả giá trị và scale; hai BigDecimal có scale khác nhau có thể không `equals` dù so sánh bằng 0.
- `a.setScale(2, roundingMode)` chọn scale kết quả theo quy tắc; nếu không cần thay đổi giá trị thì không cần rounding.
- `precision()` là số chữ số trong phần unscaled value (theo định nghĩa của BigDecimal), **khác** với `scale()` là số chữ số bên phải dấu thập phân, có thể âm.

Ví dụ chạy độc lập, tạo `BigDecimalScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class BigDecimalScaleDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("compare=" + a.compareTo(b));
        System.out.println("equals=" + a.equals(b));
        System.out.println("a scale=" + a.scale());
        System.out.println("b scale=" + b.scale());
        System.out.println("rounded=" +
                new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("distinct=" +
                List.of(a, b).stream().distinct().count());
    }
}
```

Chạy:

```bash
javac BigDecimalScaleDemo.java
java BigDecimalScaleDemo
```

Output:

```text
compare=0
equals=false
a scale=1
b scale=2
rounded=1.01
distinct=2
```

Điểm học tập từ Stream: `distinct()` dựa trên `equals` (và hash code) để xác định phần tử trùng, nên có thể giữ cả `1.0` và `1.00`; trong khi `sorted()` theo thứ tự tự nhiên dùng `compareTo` và xem chúng bằng nhau về thứ tự. Nếu ứng dụng yêu cầu gộp số thập phân theo **giá trị số** thay vì cả scale, phải chuẩn hóa hoặc xây phép so sánh/gom phù hợp; không mặc định hai khái niệm là một.

Một biểu diễn như `0.00` thường có ý nghĩa hiển thị tiền; `stripTrailingZeros()` có thể thay đổi scale và cách in (kể cả dạng khoa học). Đừng gọi nó tùy tiện trước khi xuất dữ liệu hoặc làm khóa HashMap nếu scale thuộc hợp đồng.

## 9. Phép chia và quy tắc làm tròn: nơi cần quyết định rõ

Cộng và nhân `BigDecimal` có thể cho kết quả thập phân chính xác với các đầu vào hữu hạn, trong khi phép chia có thể có phần thập phân **không kết thúc**. Ví dụ `1 / 3` không có số chữ số thập phân hữu hạn.

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);

// Chia không chỉ định rounding cho thương không kết thúc:
// one.divide(three); // ném ArithmeticException khi chạy.

BigDecimal ratio = one.divide(
        three, 4, RoundingMode.HALF_UP); // 0.3333
```

Đây là đoạn minh họa trong phương thức, cần import `BigDecimal` và `RoundingMode`. Khi chọn `scale = 4`, Java giữ bốn chữ số sau dấu thập phân. Nếu nghiệp vụ cần kết quả 2 chữ số thì chọn scale 2. Nếu yêu cầu làm tròn theo độ chính xác tổng thể (số chữ số có nghĩa), có thể dùng `MathContext` với precision và rounding mode; **MathContext precision không giống với scale**.

Một số kiểu rounding phổ biến:

| RoundingMode | Ý nghĩa khái quát |
| --- | --- |
| `HALF_UP` | Đến trường hợp đúng nửa đơn vị làm tròn thì hướng ra xa 0 |
| `HALF_EVEN` | Đến trường hợp đúng nửa thì chọn chữ số cuối chẵn; hay gọi là banker’s rounding |
| `DOWN` | Bỏ phần vượt scale, hướng về 0 |
| `UP` | Làm tròn ra xa 0 nếu có phần bị bỏ |
| `UNNECESSARY` | Báo lỗi nếu phép toán buộc phải làm tròn |

Không có quy tắc một-cỡ-cho-tất-cả. `HALF_UP` dễ giải thích cho nhiều mô hình thu phí, nhưng không mặc định đúng mọi hệ thống kế toán. `HALF_EVEN` có thể hữu ích khi cần giảm thiên lệch tích lũy qua nhiều phép làm tròn, song phải phù hợp hợp đồng thực tế.

### Tránh làm tròn sớm trong reducer

Phép cộng BigDecimal **không làm tròn** với chữ ký `add(BigDecimal)` là một phép toán chính xác, thích hợp cho `reduce(BigDecimal.ZERO, BigDecimal::add)`. Đừng tự thêm `setScale(2, ...)` vào *mỗi* bước reduce nếu yêu cầu phải cộng toàn bộ giá trị chính xác rồi mới làm tròn kết quả.

Xét ba giá trị 0.005: tổng chính xác là `0.015`, sau đó làm tròn 2 chữ số theo `HALF_UP` thành `0.02`. Nhưng nếu làm tròn từng dòng 0.005 thành 0.01 trước khi cộng, tổng thành `0.03`. Cả hai có thể là quy tắc nghiệp vụ hợp lệ trong ngữ cảnh khác nhau; **không tự ý chuyển đổi vị trí rounding khi đổi từ vòng lặp sang Stream**.

## 10. Reduce, parallel stream và tính kết hợp của phép toán

Chữ ký dạng phổ biến:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

Hàm dùng để gộp phần tử cần có tính **kết hợp (associative)** và identity thích hợp để Stream có thể xử lý hợp lệ, đặc biệt khi chia nhóm trong parallel stream. Phép cộng chính xác `BigDecimal::add` với identity `BigDecimal.ZERO` là một lựa chọn tự nhiên:

```java
BigDecimal sum = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Nếu cùng dữ liệu được xử lý bằng `parallelStream()`, phép cộng chính xác vẫn phù hợp về giá trị số với các đầu vào không-null. Tuy nhiên việc chia nhóm, trạng thái scale và chi phí lập đối tượng không tự động khiến parallel nhanh hơn; hãy đo trên workload thật và kiểm tra hợp đồng biểu diễn/scale nếu điều đó quan trọng.

**Tránh accumulator có side effect dùng chung:**

```java
// Không nên dùng mutable holder/chia sẻ biến bên ngoài:
AtomicReference<BigDecimal> holder = new AtomicReference<>(BigDecimal.ZERO);
prices.parallelStream().forEach(x ->
        holder.updateAndGet(current -> current.add(x)));
```

Đây là minh họa **điều nên tránh**, cần import `AtomicReference`, có thể hoạt động đúng về cập nhật nhờ atomic nhưng khó đọc, tạo tranh chấp khi song song và không cần thiết. Ưu tiên `reduce` hoặc collector phù hợp. Đặc biệt, BigDecimal là immutable nên `sum.add(x)` **không** sửa `sum`: phải dùng giá trị trả về.

Nếu dùng phép chia, phép trừ hoặc rounding tại từng bước như một reducer, chúng không nhất thiết associative. Kết quả có thể phụ thuộc thứ tự gộp, nhất là parallel. Hãy giữ phép gộp chính xác nếu có thể và đặt bước rounding ở vị trí do nghiệp vụ yêu cầu.

Một pattern gọn và dễ kiểm thử:

```java
BigDecimal total = prices.stream()
        .filter(java.util.Objects::nonNull)
        .reduce(BigDecimal.ZERO, BigDecimal::add)
        .setScale(2, RoundingMode.HALF_UP);
```

Đoạn này giả định dữ liệu `prices` có thể chứa null và **quy định nghiệp vụ cho phép bỏ qua null**. Nếu null nghĩa là dữ liệu không hợp lệ, phải ném lỗi/validate thay vì âm thầm lọc. Đừng sử dụng `List.of(...)` để tạo list có null, vì API đó không cho phép phần tử null.

## 11. Đầu vào, định dạng và đơn vị tiền tệ

Chọn `BigDecimal` không đủ nếu chưa làm rõ nguồn và đơn vị:

1. **Dữ liệu nhập:** với chuỗi `"12.30"`, tạo `new BigDecimal("12.30")` để giữ decimal đúng. Với dấu phẩy phân cách hàng nghìn/thập phân theo locale, cần parse có cấu hình địa phương hóa; constructor `BigDecimal(String)` không tự hiểu mọi định dạng ngôn ngữ.
2. **JSON/API:** nếu thư viện parse số JSON thành `double` trước rồi trả cho ứng dụng, bạn có thể đã mất ý nghĩa số thập phân ban đầu. Dùng cấu hình parser / model decimal phù hợp, ví dụ đọc một chuỗi decimal hoặc kiểu `BigDecimal` khi API hỗ trợ.
3. **Database:** kiểu SQL `DECIMAL/NUMERIC` có thể ánh xạ sang `BigDecimal`; cần kiểm tra precision/scale của cột và driver.
4. **Tiền tệ:** đơn vị VND, USD, JPY... có quy tắc số chữ số thập phân khác nhau. Scale 2 trong ví dụ chỉ là **giả định minh họa**, không phải quy định cho mọi đồng tiền.
5. **Giá trị âm và hoàn tiền:** quy tắc làm tròn cần kiểm tra trên cả số dương lẫn số âm; `HALF_UP`, `UP`, `DOWN` có ý nghĩa hướng khác nhau.
6. **Dữ liệu trống:** tổng của stream rỗng với identity `BigDecimal.ZERO` là `0`; nếu xuất theo định dạng tiền tệ hai chữ số, chuẩn hóa ở boundary bằng `setScale(2, ...)` hoặc formatter phù hợp.
7. **Sai đơn vị:** cùng giá trị số `100` nhưng “100 đồng”, “100 xu”, “100 điểm” khác nhau. Dùng model và tên biến nói rõ đơn vị; `BigDecimal` không tự biết currency.

Với trường hợp mọi khoản tiền đều thuộc một đơn vị nhỏ nhất cố định, biểu diễn bằng số xu (`long`) cũng là lựa chọn chính xác, miễn phạm vi không tràn và không phát sinh đơn vị nhỏ hơn. Ví dụ `12345` xu có thể được biểu diễn thành `BigDecimal.valueOf(12345L, 2) == 123.45` về giá trị. Khi cần tính tỷ lệ hoặc chia, có thể phải chuyển sang decimal và chọn rounding theo nghiệp vụ.

## 12. Sự khác nhau giữa `Stream<BigDecimal>` và `DoubleStream` về API

| Mục | `DoubleStream` | `Stream<BigDecimal>` |
| --- | --- | --- |
| Phần tử | `double` | `BigDecimal` object |
| Số học | Nhị phân, thường xấp xỉ | Thập phân chính xác với phép toán phù hợp |
| Tổng | `sum()` | `reduce(BigDecimal.ZERO, BigDecimal::add)` |
| Trung bình | `average()` trả `OptionalDouble` | Tính tổng/số phần tử rồi `divide(...)` với rounding |
| Giữ scale | Không có scale thập phân | Có `scale()`, `setScale(...)` |
| Hiệu năng/bộ nhớ | Có lợi khi xử lý khối lượng số lớn phù hợp xấp xỉ | Thường nhiều object và phép toán đắt hơn |
| Phù hợp | Đo lường, mô phỏng, số thực xấp xỉ | Tiền, thuế, decimal nghiệp vụ chính xác |

Với trung bình của một tập BigDecimal, trước hết phải xác định xử lý **stream rỗng**. Nếu có n phần tử, tổng là BigDecimal rồi chia cho n với scale/rounding đã định. Không thể dùng `BigDecimal.divide(BigDecimal.valueOf(n))` không rounding và mong mọi trường hợp thành công: nhiều thương không có biểu diễn thập phân hữu hạn.

Để tránh duyệt stream hai lần, có thể dùng collector/accumulator giữ cả tổng và số lượng. Một stream chỉ nên được dùng trong một pipeline với terminal operation; không lấy cùng một stream để gọi `count()` rồi `reduce()` lần hai. Tạo stream mới từ collection nếu cần hoặc sử dụng accumulator được thiết kế đúng.

## 13. Lỗi thường gặp

1. **Dùng `DoubleStream.sum()` rồi mong được tổng decimal chính xác.** `double` là số thực nhị phân, không bảo đảm chính xác chữ số thập phân.
2. **Tạo `BigDecimal` bằng `new BigDecimal(0.1)`.** Nó nhận đúng giá trị nhị phân xấp xỉ của 0.1; ưu tiên chuỗi thập phân hoặc input decimal chính xác.
3. **Chuyển sang BigDecimal sau khi đã cộng bằng double.** `BigDecimal.valueOf(0.1 + 0.2)` chứa `0.30000000000000004`; chuyển từng giá trị chính xác trước phép tính.
4. **Tìm `BigDecimalStream.sum()` trong Java chuẩn.** Không có; sử dụng `Stream<BigDecimal>.reduce(...)`.
5. **Bỏ quên scale và định dạng.** `0` khác cách trình bày `0.00`; quy ước scale phải được quyết định ở boundary thích hợp.
6. **Dùng `equals` để so sánh giá trị số mà bỏ qua scale.** `1.0` và `1.00` có `compareTo == 0` nhưng `equals == false`.
7. **Chia số thập phân không chỉ định rounding.** `1 / 3` theo divide không rounding sẽ ném `ArithmeticException`.
8. **Làm tròn tại mỗi bước reduce không có lý do.** Có thể đổi tổng khi làm tròn trước/sau; phép gộp còn có thể không associative.
9. **Dùng mutable holder trong parallel stream.** Làm tăng rủi ro race/side effect và chi phí đồng bộ; ưu tiên reduce với phép gộp phù hợp.
10. **Chọn scale 2 cho mọi tiền tệ.** Cần xác định đơn vị, currency và pháp lý/nghiệp vụ trước.
11. **Bỏ qua tràn số nguyên khi dùng cent.** `int` và `long` có giới hạn; chọn phạm vi và kiểm tra overflow.
12. **Cho rằng `BigDecimal` tự biết giá trị nào hợp lệ.** Dữ liệu âm, thuế suất sai, currency không khớp vẫn phải được validate.
13. **Trộn `BigDecimal` và `double` không kiểm soát.** Một đoạn map tính toán bằng double có thể mang sai số vào pipeline dù bước cuối là BigDecimal.
14. **Tưởng `BigDecimal.add` thay đổi receiver.** BigDecimal immutable, luôn giữ kết quả trả về của phép toán.
15. **Coi mọi bài toán số thực đều phải dùng BigDecimal.** Với phép tính chấp nhận xấp xỉ và đòi hỏi tốc độ, `double` có thể phù hợp hơn.

## 14. Bài tự kiểm tra

Cho một stream các giá trị decimal:

```java
List<BigDecimal> values = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal total = values.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Đoạn mã nằm trong phương thức và cần import `List`, `BigDecimal`.

**Câu hỏi:**

1. `total.toPlainString()` cho gì và vì sao?
2. Đổi thành `DoubleStream.of(0.1, 0.2, 0.3).sum()` có còn cùng hợp đồng chính xác decimal không?
3. Nếu stream rỗng, reducer trên trả gì và có scale bao nhiêu?
4. Với `new BigDecimal("2.0")` và `new BigDecimal("2.00")`, `equals` và `compareTo` có cho cùng kết luận không?
5. Tại sao tính tỷ lệ `1 / 3` cần scale/rounding?

**Đáp án:**

1. `0.60` vì các số được tạo chính xác theo hệ thập phân và scale lớn nhất trong các phép cộng là 2.
2. Không. Kết quả kiểu double vẫn thuộc mô hình dấu phẩy động nhị phân, dù có thể được làm tròn hiển thị thành một số quen thuộc.
3. `BigDecimal.ZERO`, in `0` và scale 0. Có thể áp dụng `setScale(2)` nếu cần biểu diễn tiền như `0.00`.
4. `equals` trả false vì scale khác; `compareTo` trả 0 vì giá trị số bằng nhau.
5. Vì thương thập phân không kết thúc nên không thể trả BigDecimal chính xác với scale hữu hạn nếu không có chính sách làm tròn.

## 15. Checklist trước khi chọn `BigDecimal` trong Stream

- **Dữ liệu đầu vào có thực sự là decimal chính xác không?** Tránh chuyển một giá trị double đã sai số mà kỳ vọng khôi phục nguyên trạng.
- **Đơn vị có được nói rõ không?** Giá, đơn vị tiền nhỏ nhất, số lượng và tỷ lệ cần phân biệt.
- **Cách tạo số đã phù hợp?** Ưu tiên chuỗi decimal, `BigDecimal.valueOf(long)` hoặc `valueOf(unscaled, scale)` từ số nguyên chính xác.
- **Phép gộp đã đúng chưa?** Với tổng, dùng `reduce(BigDecimal.ZERO, BigDecimal::add)`; không dùng accumulator chia sẻ mutable state.
- **Có phép chia không?** Chỉ rõ scale hoặc MathContext, rounding mode và hành vi khi chia cho 0.
- **Rounding ở stage nào?** Trên từng dòng, sau tổng, hay trên kết quả cuối cùng là quyết định nghiệp vụ; không tự ý chuyển vị trí.
- **Cần so sánh theo giá trị hay cả biểu diễn?** `compareTo` khác `equals`; `distinct()` của Stream dựa trên equality.
- **Kết quả có cần format không?** `BigDecimal.toPlainString()` và scale thể hiện decimal, còn hiển thị tiền cần formatter/currency tương ứng.
- **Hiệu năng có phù hợp không?** BigDecimal thường đắt hơn primitive arithmetic; đo đạc sau khi đảm bảo tính đúng đắn.

**Kết luận:** Khi phép tính phải đúng theo thập phân, hãy chọn `BigDecimal` ngay từ **nguồn dữ liệu** và giữ phép cộng/nhân trong `Stream<BigDecimal>`; chuyển từ primitive integer bằng `mapToObj` khi có đơn vị nhỏ nhất rõ ràng. Đối với phép chia, rounding, scale và currency, ghi thành quy tắc minh bạch. `DoubleStream` là công cụ tốt cho số thực nhị phân chấp nhận xấp xỉ, nhưng không phải công cụ đảm bảo độ chính xác decimal.

**Tài liệu tham khảo:** Java SE API `java.math.BigDecimal`, `java.math.MathContext`, `java.math.RoundingMode`; `java.util.stream.Stream.reduce`, `java.util.stream.IntStream`, `java.util.stream.DoubleStream`; Java Language Specification về giá trị floating-point.