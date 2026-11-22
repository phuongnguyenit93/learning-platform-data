# Chọn `double` hay `BigDecimal` theo mô hình dữ liệu trong Java

## 1. Câu hỏi đúng không phải “kiểu nào chính xác hơn?”

Khi thiết kế chương trình Java, lựa chọn giữa `double` và `BigDecimal` cần bắt đầu từ **ý nghĩa và quy tắc của dữ liệu**, không chỉ từ việc kiểu nào lưu được nhiều chữ số hơn.

- **`double`** là kiểu nguyên thủy dấu phẩy động nhị phân 64 bit (*IEEE 754 binary64*). Nó phù hợp với các phép đo, mô phỏng, thống kê và thuật toán số mà **sai số xấp xỉ được chấp nhận và kiểm soát**.
- **`BigDecimal`** là lớp số thập phân có phần trị nguyên độ lớn tùy ý và một *scale* thập phân. Nó phù hợp với dữ liệu và quy tắc tính toán cần **biểu diễn thập phân chính xác**, đặc biệt khi chính sách làm tròn có ý nghĩa nghiệp vụ.
- **Số nguyên `long` (hoặc `int`) lưu đơn vị nhỏ nhất** là một lựa chọn thứ ba hữu ích, chẳng hạn lưu số tiền bằng xu khi đơn vị và độ chính xác luôn cố định, miễn là kiểm soát miền số và tràn.

Không có quy tắc “mọi phép tính tiền đều phải dùng `BigDecimal`” hay “`double` luôn sai”. Điều quan trọng là: **nguồn dữ liệu có chính xác không, phép toán nào được thực hiện, kết quả nào phải bảo toàn và khi nào phải làm tròn?**

## 2. Bảng quyết định nhanh

| Trường hợp | Lựa chọn thường hợp lý | Lý do |
|---|---|---|
| Nhiệt độ từ cảm biến, vị trí, đo đạc | `double` | Số đo vốn có sai số; hiệu năng và API số học thuận tiện |
| Mô phỏng vật lý, thống kê, hàm lượng giác | `double` | Thư viện toán số và thuật toán thường sử dụng số thực nhị phân |
| Giá niêm yết “19.90” cần bảo toàn đúng số thập phân | `BigDecimal` từ chuỗi | `19.90` là giá trị decimal có ý nghĩa nghiệp vụ |
| Thuế, chiết khấu, tỷ giá với quy định làm tròn | `BigDecimal` cùng chính sách `RoundingMode` | Kiểm soát scale, độ chính xác và điểm làm tròn |
| Số dư chỉ có hai chữ số thập phân, lưu theo xu | `long` nếu phạm vi đủ | Tính cộng/trừ số nguyên chính xác, nhưng phải quản lý đơn vị |
| Số lượng nguyên rất lớn vượt `long` | `BigInteger` | Không cần phần thập phân và không bị giới hạn 64 bit |
| Tiền lưu decimal nhưng cần nhân với số lượng | `BigDecimal` nhân với số lượng nguyên | Giữ chính xác các hằng decimal của nghiệp vụ |
| Dữ liệu JSON/API ghi rõ một decimal tùy ý | `BigDecimal` nếu phải bảo toàn decimal | Tránh làm tròn qua `double` trước khi parse |
| Một thuật toán chuyên biệt được đặc tả bằng IEEE 754 | `double`/`float` theo đặc tả | Cần đúng ngữ nghĩa floating-point và tính tương thích |
| Giá trị đo được đưa vào báo cáo có hai chữ số | `double` có thể vẫn phù hợp | **Định dạng hiển thị** hai chữ số không đồng nghĩa cần lưu decimal chính xác |

Bảng chỉ là gợi ý thiết kế. Ví dụ ứng dụng tài chính vẫn có thể dùng `double` trong mô hình rủi ro thống kê; ngược lại một hệ thống khoa học vẫn có thể dùng `BigDecimal` nếu phép đo đặc biệt cần số học decimal ở độ chính xác quy định.

## 3. Vì sao `double` không biểu diễn chính xác mọi số thập phân?

`double` lưu giá trị dưới dạng nhị phân hữu hạn. Nhiều phân số thập phân, chẳng hạn \(0.1 = 1/10\), **không có biểu diễn nhị phân hữu hạn**. JVM lưu một số binary64 gần với 0.1, chứ không lưu phân số toán học 1/10 chính xác.

Ví dụ quen thuộc:

```java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
```

Giá trị `0.3` được viết trong mã nguồn cũng được làm tròn thành một mẫu binary64, nhưng mẫu đó không bằng kết quả binary64 của phép cộng `0.1 + 0.2`. Đây là hành vi dự kiến của số học dấu phẩy động, **không phải lỗi của Java**.

Số `double` có **53 bit độ chính xác phần trị** (kể cả bit ẩn) — khoảng 15–17 chữ số thập phân có nghĩa tùy số cụ thể. Điều đó không có nghĩa mọi số có 15 chữ số thập phân đều được lưu chính xác. Độ chính xác theo chữ số và khả năng biểu diễn đúng một phân số decimal là **hai vấn đề khác nhau**.

### Khi nào sai số này chấp nhận được?

Giả sử một cảm biến cung cấp nhiệt độ khoảng 23.7°C với sai số thiết bị ±0.1°C. Sai khác ở mức vài đơn vị phần cuối nhị phân của `double` thường nhỏ hơn nhiều so với sai số đo; điều quan trọng hơn có thể là hiệu chuẩn và cách tổng hợp số đo.

Trong khi đó, nếu hợp đồng yêu cầu lưu **đúng 0.10 đơn vị tiền** và đối soát đến xu, dùng `double` rồi so sánh trực tiếp từng giá trị thập phân có thể gây rắc rối. Mô hình thập phân chính xác giúp biểu diễn và thực thi quy tắc nghiệp vụ dễ giải thích hơn.

## 4. `BigDecimal` biểu diễn số theo cách nào?

Một `BigDecimal` hữu hạn có thể hiểu bằng công thức:

\[
\text{value}=\text{unscaledValue}\times 10^{-\text{scale}}
\]

Ví dụ, `new BigDecimal("12.3400")` có:

- Giá trị toán học là **12.3400**, bằng 12.34.
- `unscaledValue()` bằng **123400**.
- `scale()` bằng **4**.
- `precision()` bằng **6** (số chữ số trong phần trị nguyên, không phải số chữ số sau dấu chấm).

Với `BigDecimal`, chuỗi thập phân `"0.1"` được biểu diễn **chính xác**. Cộng với `"0.2"` cho giá trị đúng **0.3**, không phải xấp xỉ binary64.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b); // 0.3, biểu diễn chính xác
```

Đây là đoạn mã minh họa đặt **bên trong một phương thức Java**, không phải một chương trình độc lập. `BigDecimal` là lớp bất biến (*immutable*): `add` trả về đối tượng biểu diễn kết quả, không sửa `a` hay `b`.

**Giới hạn quan trọng:** `BigDecimal` không tạo ra “số thực chính xác vô hạn” cho mọi phép toán. Nó biểu diễn chính xác các số thập phân hữu hạn được cung cấp chính xác; phép chia như \(1/3\) cho decimal vô hạn và cần quy tắc làm tròn hoặc số chữ số cho phép.

## 5. Sai lầm kinh điển: `new BigDecimal(0.1)`

Hai cách tạo sau **không tương đương**:

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromBinaryDouble = new BigDecimal(0.1);
```

- `"0.1"` là chuỗi decimal chính xác, nên constructor từ `String` tạo giá trị đúng 0.1.
- `0.1` không có hậu tố là literal `double`, đã được làm tròn thành một giá trị binary64 gần 0.1. Constructor `BigDecimal(double)` ghi lại **chính xác giá trị binary64 đó** dưới dạng decimal, nên không bằng 0.1 toán học.

Vì vậy, khi bạn **biết hằng số nghiệp vụ dưới dạng decimal**, nên dùng:

```java
BigDecimal price = new BigDecimal("19.90");
BigDecimal taxRate = new BigDecimal("0.075");
```

Hoặc trong một số trường hợp:

```java
BigDecimal decimal = BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` sử dụng biểu diễn thập phân chuẩn từ `Double.toString(double)`. Với literal 0.1, kết quả có giá trị decimal `0.1` như mong muốn; tuy nhiên **không thể lấy lại chữ số gốc bị mất nếu một phép tính `double` đã xảy ra trước đó**.

Ví dụ, `BigDecimal.valueOf(0.1 + 0.2)` cho giá trị decimal **0.30000000000000004**, không tự sửa thành 0.3. Với dữ liệu tiền đọc từ form, file hoặc API, nên parse trực tiếp từ **chuỗi decimal ban đầu**, tránh đi vòng qua `double` rồi mới đổi thành `BigDecimal`.

## 6. Chương trình Java 17+: so sánh trên dữ liệu thực tế

Tạo tệp `DoubleVsBigDecimalDemo.java`:

```java
import java.math.BigDecimal;

public class DoubleVsBigDecimalDemo {
    public static void main(String[] args) {
        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        System.out.println("double: " + binarySum);
        System.out.println("double == 0.3: " + (binarySum == 0.3));
        System.out.println("decimal: " + decimalSum.toPlainString());

        BigDecimal direct = new BigDecimal(0.1);
        BigDecimal fromText = new BigDecimal("0.1");

        System.out.println("double constructor equals text: "
                + direct.equals(fromText));
        System.out.println("valueOf(0.1): "
                + BigDecimal.valueOf(0.1).toPlainString());
        System.out.println("valueOf(computed double): "
                + BigDecimal.valueOf(binarySum).toPlainString());
        System.out.println("double sum finite: "
                + Double.isFinite(binarySum));
    }
}
```

Biên dịch và chạy:

```bash
javac DoubleVsBigDecimalDemo.java
java DoubleVsBigDecimalDemo
```

Kết quả:

```text
double: 0.30000000000000004
double == 0.3: false
decimal: 0.3
double constructor equals text: false
valueOf(0.1): 0.1
valueOf(computed double): 0.30000000000000004
double sum finite: true
```

Phần cuối là điểm rất đáng nhớ: **`Double.isFinite` trả true không có nghĩa giá trị decimal chính xác**. Nó chỉ kiểm tra số không phải NaN hoặc ±Infinity.

## 7. Số học `BigDecimal`: không dùng trực tiếp `+`, `-`, `*`, `/`

Trong Java, `BigDecimal` là đối tượng, không hỗ trợ nạp chồng các toán tử số học như `+` hay `*` cho hai `BigDecimal`. Dùng các phương thức:

| Phép toán | API | Ghi chú |
|---|---|---|
| Cộng | `a.add(b)` | Kết quả thập phân chính xác nếu không truyền `MathContext` |
| Trừ | `a.subtract(b)` | Tương tự |
| Nhân | `a.multiply(b)` | Tích decimal chính xác khi không giới hạn precision |
| Chia | `a.divide(b)` | Có thể ném `ArithmeticException` nếu thương decimal vô hạn |
| Chia có làm tròn | `a.divide(b, scale, mode)` | Chỉ rõ chữ số thập phân và quy tắc làm tròn |
| Đặt số chữ số thập phân | `a.setScale(scale, mode)` | Có thể cần làm tròn |
| So sánh giá trị | `a.compareTo(b)` | So sánh giá trị số, bỏ qua khác biệt scale |
| Chuyển chính xác thành `long` | `a.longValueExact()` | Ném lỗi nếu có phần lẻ hoặc ngoài miền `long` |

Ví dụ:

```java
BigDecimal subtotal = new BigDecimal("19.90")
        .multiply(BigDecimal.valueOf(3)); // 59.70

BigDecimal discount = subtotal
        .multiply(new BigDecimal("0.075")) // 4.47750
        .setScale(2, java.math.RoundingMode.HALF_UP); // 4.48

BigDecimal total = subtotal.subtract(discount); // 55.22
```

Cần quyết định **khi nào được làm tròn**: làm tròn từng dòng hóa đơn, tổng trước khi làm tròn, hay làm tròn sau khi tính thuế có thể cho kết quả khác nhau. Không có một công thức chung thay thế chính sách tính toán được hợp đồng/quy định chỉ định.

## 8. Chia `BigDecimal` và lựa chọn `RoundingMode`

Một số thương thập phân không biểu diễn hữu hạn. Ví dụ:

\[
\frac{1}{3} = 0.333333333\ldots
\]

Nếu gọi:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);
// BigDecimal invalid = one.divide(three);
```

Dòng comment sẽ **ném `ArithmeticException` lúc chạy** do decimal vô hạn và không có quy tắc làm tròn. Không phải mọi phép chia `BigDecimal` tự chạy mãi để tìm “độ chính xác vô hạn”.

Cần chọn số chữ số sau dấu thập phân hoặc `MathContext`:

```java
BigDecimal quotient = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        4,
        java.math.RoundingMode.HALF_UP
); // 0.3333
```

### Scale khác precision

- **Scale**: số vị trí thập phân của giá trị biểu diễn (có thể âm), ví dụ `12.3400` có scale 4.
- **Precision**: số chữ số có nghĩa của phần trị nguyên không chia tỷ lệ, ví dụ `12.3400` có precision 6.
- **`MathContext(5, RoundingMode.HALF_EVEN)`**: giới hạn **5 chữ số có nghĩa**, **không phải 5 chữ số sau dấu thập phân**.

Nhờ vậy một quy tắc `MathContext` có thể phù hợp cho phép tính với độ chính xác tương đối, còn `setScale(2, ...)` thường dễ hiểu khi cần số tiền với hai chữ số lẻ.

### `HALF_UP` và `HALF_EVEN`

Ở một điểm đúng nửa:

- `HALF_UP` làm tròn ra xa 0.
- `HALF_EVEN` làm tròn đến chữ số chẵn gần nhất ở vị trí giữ lại (còn gọi là *banker's rounding*).

Ví dụ decimal **chính xác**:

```java
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP);   // 2.35
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN); // 2.34
new BigDecimal("2.355").setScale(2, RoundingMode.HALF_EVEN); // 2.36
```

Ba dòng là biểu thức minh họa; để biên dịch, đặt trong phương thức có import `java.math.BigDecimal` và `java.math.RoundingMode`, đồng thời gán/sử dụng kết quả. **Đừng tự chọn mode theo cảm tính**: quy tắc làm tròn cần phù hợp yêu cầu sản phẩm và các quy định áp dụng.

## 9. `equals` không giống `compareTo` với `BigDecimal`

Đây là một bẫy API thường gặp:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));  // false
System.out.println(a.compareTo(b)); // 0
```

Hai giá trị **bằng nhau theo toán học**, nhưng khác **scale** (1 so với 2). `BigDecimal.equals` xét cả giá trị phần trị và scale, còn `compareTo` xét quan hệ giá trị số.

Khi cần kiểm tra **hai số tiền có cùng giá trị**, thường nên dùng:

```java
boolean sameAmount = a.compareTo(b) == 0;
```

Khi cần so khớp **cả định dạng/scale** theo hợp đồng dữ liệu, `equals` có thể là chủ đích đúng. Điều này ảnh hưởng đến `HashSet<BigDecimal>` hay `HashMap<BigDecimal, ...>`: chúng dùng `equals`/`hashCode`, nên `2.0` và `2.00` là hai key khác nhau. Một `TreeSet<BigDecimal>` sắp theo so sánh tự nhiên có thể xem hai giá trị đó là tương đương theo thứ tự.

Nếu cần chuẩn hóa scale, có thể dùng `setScale` với quy tắc phù hợp. `stripTrailingZeros()` cũng thay đổi scale; một số giá trị như `1000.00` có thể nhận scale âm sau khi bỏ số 0 không cần thiết, nên không phải phép chuẩn hóa định dạng tùy ý.

### Ví dụ Java 17+: scale, compare và chia

Tạo tệp `BigDecimalRulesDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalRulesDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo: " + a.compareTo(b));
        System.out.println("a scale: " + a.scale());
        System.out.println("b scale: " + b.scale());

        BigDecimal sample = new BigDecimal("12.3400");
        System.out.println("precision: " + sample.precision());
        System.out.println("scale: " + sample.scale());
        System.out.println("stripped: "
                + sample.stripTrailingZeros().toPlainString());

        try {
            System.out.println(
                    BigDecimal.ONE.divide(BigDecimal.valueOf(3)));
        } catch (ArithmeticException e) {
            System.out.println("1/3 without rounding: ArithmeticException");
        }

        System.out.println("1/3 scale 4: "
                + BigDecimal.ONE.divide(
                        BigDecimal.valueOf(3), 4, RoundingMode.HALF_UP));
        System.out.println("half up: " + new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_UP));
        System.out.println("half even: " + new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN));
    }
}
```

Chạy:

```bash
javac BigDecimalRulesDemo.java
java BigDecimalRulesDemo
```

Kết quả:

```text
equals: false
compareTo: 0
a scale: 1
b scale: 2
precision: 6
scale: 4
stripped: 12.34
1/3 without rounding: ArithmeticException
1/3 scale 4: 0.3333
half up: 2.35
half even: 2.34
```

## 10. Tình huống thực tế: giá, số lượng và chiết khấu

Giả sử một dòng hóa đơn có:

- Đơn giá **19.90**.
- Số lượng **3**.
- Chiết khấu **7.5%**.
- Quy tắc giả định: **làm tròn tiền chiết khấu đến 2 chữ số thập phân theo HALF_UP**.

Đây là **ví dụ quy tắc nghiệp vụ giả định**, không phải quy định thuế/làm tròn áp dụng cho mọi hệ thống. Phương án tính:

1. Thành tiền trước giảm: 19.90 × 3 = 59.70.
2. Tiền giảm chưa làm tròn: 59.70 × 0.075 = 4.47750.
3. Tiền giảm sau làm tròn: 4.48.
4. Số tiền phải trả: 59.70 - 4.48 = 55.22.

Lưu `MoneyCalculationDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyCalculationDemo {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.90");
        int quantity = 3;
        BigDecimal discountRate = new BigDecimal("0.075");

        BigDecimal subtotal = unitPrice
                .multiply(BigDecimal.valueOf(quantity));

        BigDecimal discount = subtotal.multiply(discountRate)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal total = subtotal.subtract(discount)
                .setScale(2, RoundingMode.UNNECESSARY);

        long cents = total.movePointRight(2).longValueExact();

        System.out.println("subtotal: " + subtotal.toPlainString());
        System.out.println("discount: " + discount.toPlainString());
        System.out.println("total: " + total.toPlainString());
        System.out.println("cents: " + cents);
    }
}
```

Chạy:

```bash
javac MoneyCalculationDemo.java
java MoneyCalculationDemo
```

Kết quả:

```text
subtotal: 59.70
discount: 4.48
total: 55.22
cents: 5522
```

`RoundingMode.UNNECESSARY` có nghĩa **không cho phép phải làm tròn** ở bước đặt scale cuối: nếu tổng chưa có thể biểu diễn ở 2 chữ số thập phân mà không mất dữ liệu, bước này ném `ArithmeticException`. Nó hữu ích khi muốn khẳng định một bất biến dữ liệu ở điểm lưu kết quả.

Chuyển sang số xu ở cuối bằng `movePointRight(2).longValueExact()` yêu cầu không có phần lẻ còn lại và không vượt miền `long`. Nếu tiền tệ dùng độ lớn đơn vị thập phân khác, con số 2 cần được thay theo **currency và hợp đồng lưu trữ**, không nên mã hóa cứng trong mọi hệ thống.

## 11. Phương án thứ ba: dùng số nguyên theo đơn vị nhỏ nhất

Nếu tất cả dữ liệu luôn nằm trong một đơn vị cố định, chẳng hạn số tiền có đúng **hai chữ số thập phân**, lưu `long cents` cũng là mô hình có thể **đúng tuyệt đối trong miền số nguyên**:

```java
long unitPriceCents = 1_990L;
int quantity = 3;
long subtotalCents = Math.multiplyExact(
        unitPriceCents, quantity); // 5970 xu
```

Ưu điểm:

- Cộng, trừ và kiểm tra bằng nhau là **phép toán số nguyên chính xác** khi không tràn.
- Không phụ thuộc biểu diễn binary64 của 0.1.
- Dữ liệu lưu truyền có thể rất rõ đơn vị khi được đặt tên `amountInCents` thay vì `amount`.

Rủi ro:

- Nếu có tỷ lệ chiết khấu, thuế hoặc tỷ giá thập phân, vẫn phải đặt quy tắc **nhân/chia và làm tròn**.
- Các đơn vị tiền khác nhau có quy ước số chữ số thập phân khác nhau; “cent” không phải đơn vị chung cho mọi currency.
- `long` có thể tràn; dùng `Math.addExact`/`Math.multiplyExact` hoặc kiểm tra miền phù hợp.
- Nếu nghiệp vụ cần độ chính xác thay đổi hoặc hỗ trợ số decimal với nhiều scale, cách lưu xu cố định có thể quá cứng nhắc.

**Cách kết hợp hợp lý:** dùng `BigDecimal` để tính và làm tròn theo chính sách nghiệp vụ, sau đó chuyển chính xác sang đơn vị nguyên tại ranh giới lưu trữ nếu mô hình đã quy định đơn vị đó. Hoặc sử dụng số nguyên từ đầu nếu hệ thống được thiết kế hoàn toàn bằng đơn vị nhỏ nhất.

## 12. `double` vẫn là lựa chọn rất tốt cho tính toán khoa học

Trong nhiều ứng dụng, dùng `BigDecimal` thay `double` không những không cần thiết mà còn làm thuật toán phức tạp hơn:

- `Math.sin`, `Math.cos`, `Math.sqrt` cùng nhiều API khoa học nhận/trả `double`.
- Các phương pháp phân tích số, mô phỏng và thống kê thường chấp nhận sai số xấp xỉ có kiểm soát.
- `double` có **miền độ lớn rất rộng**, hỗ trợ số dưới chuẩn, ±Infinity, NaN và các quy tắc số học IEEE 754.
- `BigDecimal` có thể tốn tài nguyên hơn do dùng đối tượng và số học thập phân theo độ chính xác yêu cầu.

Nhưng `double` không bảo đảm phép toán có tính chất đại số như số thực toán học với độ chính xác vô hạn. Ví dụ, thứ tự cộng có thể ảnh hưởng đến sai số:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Giải thích: `b + c` làm tròn thành `-1.0e16` dưới `double` do số 1 quá nhỏ so với độ lớn của b; sau đó `a + (b+c)` bằng 0.0. Còn `(a+b)+c` cho 1.0. Như vậy với `double`, bạn phải quan tâm **ổn định số**, thứ tự tích lũy, thang giá trị và sai số chứ không chỉ kiểm tra NaN/Infinity.

Khi cộng nhiều mẫu đo, có thể cân nhắc thuật toán cộng ổn định như **Kahan summation** hoặc chiến lược tính phù hợp thay vì tự động chuyển toàn bộ hệ thống sang `BigDecimal`.

## 13. Nhập liệu, JSON, database và hợp đồng API

Kiểu dữ liệu không chỉ là quyết định ở biến Java. Hãy thống nhất **ý nghĩa số tại mọi ranh giới**:

### Nhận dữ liệu từ giao diện hoặc file

Nếu nguồn có chuỗi thập phân chính xác, ví dụ `"123.45"`, hãy đưa trực tiếp vào `BigDecimal`:

```java
String input = "123.45";
BigDecimal amount = new BigDecimal(input);
```

Việc parse trước thành `double` có thể đánh mất biểu diễn decimal mong muốn. Với dữ liệu người dùng, cũng cần kiểm tra chuỗi rỗng, cú pháp, giới hạn độ lớn, scale tối đa và lỗi parse `NumberFormatException`.

### JSON và API

Một token JSON kiểu number như `19.90` thường **không tự mang metadata về đơn vị hoặc chính sách scale**. Tùy thư viện parse, nó có thể đi qua `double` hoặc được đọc trực tiếp thành `BigDecimal`. Đừng giả định mọi thư viện JSON tự bảo toàn độ chính xác decimal hoặc số 0 cuối.

Nếu API tài chính cần giao tiếp ổn định, hãy quy định rõ trường nào là:

- Số thập phân được parse chính xác.
- Số nguyên theo đơn vị nhỏ nhất (kèm currency/unit).
- Số xấp xỉ đo đạc.
- Hoặc chuỗi decimal để tránh mất ý nghĩa khi qua hệ thống khác.

### Database

Cột `DECIMAL`/`NUMERIC` thường phù hợp với `BigDecimal` khi database và ORM có cấu hình precision/scale tương ứng; `DOUBLE`/`FLOAT` thường phù hợp giá trị xấp xỉ. Tuy nhiên, chi tiết phụ thuộc engine, driver và mapping thực tế. Hãy kiểm tra **schema, precision, scale, phép làm tròn ở database và mapping ORM**, không chỉ kiểu Java.

Một hệ thống dùng `BigDecimal` trong code nhưng ghi xuống cột floating-point vẫn có thể mất chính xác; ngược lại, một cột decimal có precision/scale quá hẹp có thể làm tròn hoặc từ chối giá trị.

## 14. So sánh, đồng nhất và giá trị không hợp lệ

### Với `double`

Tránh kỳ vọng `0.1 + 0.2 == 0.3`. Khi so kết quả xấp xỉ, sử dụng tiêu chí sai số phù hợp thang giá trị và ngữ cảnh. Ví dụ kiểm tra gần bằng:

```java
static boolean approximatelyEqual(double a, double b,
                                  double tolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(tolerance) || tolerance < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= tolerance;
}
```

Đây là **phương thức minh họa**. Sai số tuyệt đối cố định không phù hợp mọi miền số; ứng dụng cần có thể kết hợp sai số tương đối, so sánh theo ULP hoặc tiêu chí đặc thù. Ngoài ra, phép trừ có thể tràn thành Infinity nếu hai số hữu hạn cực lớn khác dấu, khiến phép thử trên trả false dù ngưỡng không cho phép khác biệt đó; vì vậy phải hiểu giới hạn của chiến lược so sánh.

Với `double` còn cần xử lý **NaN, ±Infinity, -0.0** khi hợp đồng đầu vào cấm hoặc yêu cầu phân biệt các giá trị đặc biệt.

### Với `BigDecimal`

Muốn so giá trị toán học dùng `compareTo`:

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");
boolean sameNumber = a.compareTo(b) == 0; // true
```

`equals` còn xét scale, nên có thể false. `BigDecimal` không có các giá trị NaN hoặc Infinity theo mô hình lớp; `BigDecimal.valueOf(Double.NaN)` không biến nó thành một đối tượng “decimal NaN” mà sẽ thất bại khi chuyển đổi.

Điều này giúp mô hình decimal tránh một lớp lỗi NaN/Infinity, nhưng vẫn cần kiểm tra các lỗi khác như **chia cho 0**, vượt giới hạn nghiệp vụ, hoặc phép chia không kết thúc decimal.

## 15. Hiệu năng và chi phí của sự chính xác

`double` là primitive 64 bit, phù hợp với các cấu trúc dữ liệu mảng primitive, phép tính số học lặp lại và nhiều thư viện tính toán được tối ưu. `BigDecimal` là đối tượng bất biến, thường tạo kết quả mới sau mỗi phép toán và cần xử lý phần trị/scale.

Trong một vòng lặp hàng triệu phép tính, sự khác biệt về cấp phát và CPU **có thể đáng kể**, nhưng không thể kết luận bằng một con số tốc độ chung nếu chưa đo trong ứng dụng cụ thể.

Một cách ra quyết định:

1. Xác nhận loại chính xác mà bài toán cần: **xấp xỉ nhị phân**, **decimal chính xác**, hay **số nguyên theo đơn vị cố định**.
2. Dùng kiểu phù hợp trước, kiểm tra kết quả và trường hợp biên.
3. Nếu hiệu năng là vấn đề, dùng benchmark thực tế (ví dụ JMH) trên đường đi quan trọng, thay vì tối ưu theo phỏng đoán.
4. Đừng đổi kiểu chỉ để đạt hiệu năng nếu nó phá vỡ quy tắc làm tròn hoặc làm sai dữ liệu nghiệp vụ.

Thực tế có thể sử dụng **nhiều mô hình số trong cùng hệ thống**: số tiền giao dịch bằng `BigDecimal`, các tổng hợp số nguyên bằng `long`, các dự báo thống kê bằng `double`. Quan trọng là các bước chuyển đổi giữa mô hình phải rõ ràng và có kiểm tra.

## 16. Những lỗi thiết kế phổ biến

| Lỗi | Vì sao sai/rủi ro | Cách sửa |
|---|---|---|
| “`double` có 15 chữ số nên 0.1 phải chính xác” | 1/10 không có biểu diễn nhị phân hữu hạn | Nhận biết xấp xỉ hoặc dùng decimal khi cần |
| `new BigDecimal(0.1)` để biểu diễn chính xác 0.1 | Tham số là một `double` đã xấp xỉ | Dùng `new BigDecimal("0.1")` |
| Chuyển `double` sai sang `BigDecimal` để “sửa” | Chữ số mất trước đó không được khôi phục | Parse từ nguồn decimal nếu có |
| Gọi `divide` cho 1/3 mà không rounding | Thương decimal vô hạn, có thể ném ngoại lệ | Chọn scale/mode hoặc `MathContext` |
| Dùng `equals` để so giá trị `BigDecimal` | `2.0` và `2.00` khác scale | Dùng `compareTo(...) == 0` nếu so giá trị |
| Đặt `setScale(2)` tùy ý ở mọi bước | Làm tròn sớm có thể đổi số tiền cuối | Quy định điểm làm tròn nghiệp vụ |
| Nghĩ `BigDecimal` có độ chính xác vô hạn miễn phí | Số học đối tượng/decimal có chi phí, phép chia cần chính sách | Chọn precision và yêu cầu đúng |
| Nghĩ `double` finite là số chính xác | Finite chỉ loại NaN/Infinity | Kiểm soát sai số, miền và độ chính xác |
| Dùng đơn vị tiền nhỏ nhất nhưng không ghi đơn vị | Dễ nhầm xu với đơn vị tiền chính | Đặt tên rõ, lưu metadata currency/scale |
| Dùng `long` cho tiền và quên overflow | Số nguyên vẫn có miền hữu hạn | `Math.addExact`, `multiplyExact` hoặc giới hạn |
| Lưu `BigDecimal` trong cột DB `DOUBLE` | Cột đích có thể mất chính xác decimal | Dùng mapping `DECIMAL/NUMERIC` phù hợp |
| Gọi `toString` như cơ chế chuẩn hóa scale | Biểu diễn có thể có số mũ và scale khác | Dùng `toPlainString`/`setScale` theo hợp đồng |
| Dùng decimal cho mọi cảm biến để “bảo đảm đo đúng” | Sai số vật lý của nguồn không tự biến mất | Giữ mô hình đo, sai số và độ chính xác hợp lý |

## 17. Bài tập tự kiểm tra

**Câu 1.** Vì sao `double x = 0.1 + 0.2;` có thể in `0.30000000000000004`?  
**Đáp án:** 0.1 và 0.2 được lưu dưới dạng các giá trị binary64 gần đúng; phép cộng tiếp tục chịu làm tròn nhị phân.

**Câu 2.** Với giá literal decimal `"19.90"`, nên tạo `BigDecimal` thế nào?  
**Đáp án:** `new BigDecimal("19.90")` (hoặc parse trực tiếp chuỗi decimal nguồn).

**Câu 3.** `BigDecimal.valueOf(0.1 + 0.2)` có trở thành 0.3 chính xác không?  
**Đáp án:** Không. Đầu vào đã là `double` 0.30000000000000004, nên phương thức biểu diễn decimal giá trị đó.

**Câu 4.** Vì sao `BigDecimal.ONE.divide(BigDecimal.valueOf(3))` ném ngoại lệ?  
**Đáp án:** 1/3 có biểu diễn thập phân vô hạn; không có quy tắc làm tròn thì không thể tạo một kết quả decimal hữu hạn chính xác.

**Câu 5.** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` và `compareTo` cho kết quả gì?  
**Đáp án:** `equals` là false, `compareTo` trả 0; các scale khác nhau nhưng giá trị toán học bằng nhau.

**Câu 6.** Hai giá trị được dùng cho mô phỏng vật lý với sai số đo lớn hơn sai số binary64 nhiều lần: nên ưu tiên kiểu nào?  
**Đáp án:** Thường `double` nếu thuật toán/API phù hợp, đồng thời kiểm soát ổn định số và các giá trị đặc biệt.

**Câu 7.** Lưu 59.70 bằng xu trong `long` thì biểu diễn ra sao?  
**Đáp án:** 5970 xu, với giả thiết currency có đúng 100 xu trên một đơn vị chính và miền `long` đủ.

**Câu 8.** `new BigDecimal("12.3400")` có `scale` và `precision` bao nhiêu?  
**Đáp án:** Scale 4, precision 6. Bỏ số 0 cuối có thể thay đổi scale.

**Câu 9.** Khi nào `HALF_UP` khác `HALF_EVEN`?  
**Đáp án:** Ở điểm giữa đúng nửa, ví dụ 2.345 làm tròn hai chữ số: `HALF_UP` cho 2.35, `HALF_EVEN` cho 2.34.

**Câu 10.** Có nên làm tròn mỗi phép nhân/chiết khấu ngay lập tức không?  
**Đáp án:** Chỉ khi chính sách nghiệp vụ yêu cầu; thời điểm làm tròn ảnh hưởng kết quả nên phải được đặc tả và kiểm thử.

**Câu 11.** Lưu `BigDecimal` xuống cột database kiểu `DOUBLE` có bảo đảm chính xác decimal không?  
**Đáp án:** Không; phải kiểm tra kiểu cột, precision/scale và mapping thực tế.

**Câu 12.** Nếu `double` được sử dụng để tính toán khoa học, nên quan tâm điều gì ngoài chuyện `isFinite`?  
**Đáp án:** Sai số biểu diễn, tích lũy sai số, ổn định số của thuật toán, miền dữ liệu và tiêu chí so sánh gần đúng.

## 18. Quy trình chọn kiểu và tài liệu tham khảo

**Bước 1 — xác định bản chất nguồn:** số đo, số đếm nguyên, hay decimal có ý nghĩa pháp lý/nghiệp vụ? Có cần bảo toàn đúng chuỗi decimal đầu vào không?

**Bước 2 — xác định bất biến cần giữ:** giá trị toán học chính xác, độ lớn sai số cho phép, số chữ số thập phân, số chữ số có nghĩa, hoặc đơn vị lưu trữ.

**Bước 3 — xác định phép toán và quy tắc làm tròn:** cộng tổng, chia tỷ lệ, thuế, phần trăm, chuyển đơn vị; làm tròn ở bước nào, theo mode nào, có chấp nhận overflow/NaN không?

**Bước 4 — chọn mô hình:**
- **`double`** nếu bài toán là tính toán xấp xỉ nhị phân có sai số kiểm soát.
- **`BigDecimal`** nếu cần biểu diễn và tính toán decimal theo chính sách chính xác.
- **`long`/`BigInteger`** nếu dữ liệu là số nguyên hoặc đơn vị nhỏ nhất và cần số học nguyên chính xác.

**Bước 5 — kiểm thử tại ranh giới:** decimal có số 0 cuối, 0.1 + 0.2, âm/dương, các giá trị cực lớn, chia không kết thúc, nhiều bước làm tròn, chuyển kiểu, serialization, database và overflow.

**Ghi nhớ:** Không chọn `BigDecimal` chỉ vì `double` có sai số; hãy chọn nó khi **đòi hỏi của dữ liệu là decimal chính xác và cần kiểm soát làm tròn**. Không chọn `double` cho số tiền chỉ vì cú pháp thuận tiện nếu hợp đồng cần bảo toàn thập phân. Và nếu dữ liệu thực sự là số nguyên theo đơn vị cố định, `long` cùng kiểm tra tràn có thể là mô hình đơn giản nhất.

Tài liệu tham khảo chính thức:
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html)
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)
- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)
