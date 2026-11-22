# BigDecimal.valueOf và các hằng ZERO, ONE, TEN trong Java

`java.math.BigDecimal` là kiểu số thập phân có độ chính xác tùy ý trong Java. Khi tạo giá trị `BigDecimal`, hai câu hỏi cần được trả lời riêng: **đầu vào mang ý nghĩa gì** (số nguyên, decimal có scale hay số thực nhị phân `double`) và **cách biểu diễn thập phân nào cần giữ**. Các factory `valueOf` cùng ba hằng `ZERO`, `ONE`, `TEN` là các công cụ nền tảng cho việc đó.

Ví dụ:

```java
import java.math.BigDecimal;

BigDecimal a = BigDecimal.valueOf(42L);       // 42, scale 0
BigDecimal b = BigDecimal.valueOf(12345L, 2); // 123.45, scale 2
BigDecimal c = BigDecimal.valueOf(0.1);       // 0.1, scale 1
BigDecimal zero = BigDecimal.ZERO;            // 0, scale 0
BigDecimal one = BigDecimal.ONE;              // 1, scale 0
BigDecimal ten = BigDecimal.TEN;              // 10, scale 0
```

Đây là **mảnh mã minh họa** để đặt trong một phương thức. Điểm quan trọng: `valueOf(double)` **khác** `new BigDecimal(double)`; các hằng có **scale bằng 0**; và hai số có cùng giá trị nhưng khác scale có thể `compareTo` bằng 0 trong khi `equals` trả false.

## 1. Mô hình số thập phân của BigDecimal

Một `BigDecimal` được diễn giải bằng công thức:

```text
Giá trị = unscaledValue × 10^(-scale)
```

`unscaledValue()` là một `BigInteger` có dấu. `scale()` là một số nguyên `int` có thể dương, bằng 0 hoặc âm. `precision()` là số chữ số có nghĩa của unscaled value; **precision không phải scale**.

| Unscaled value | Scale | Giá trị số |
| ---: | ---: | ---: |
| 12345 | 0 | 12345 |
| 12345 | 2 | 123.45 |
| 12345 | 4 | 1.2345 |
| 12345 | -2 | 1234500 |
| 10 | 1 | 1.0 |
| 1 | 0 | 1 |
| 0 | 2 | 0.00 |

Hai đối tượng có thể cùng giá trị số học mà khác biểu diễn: `1` và `1.0` có giá trị bằng nhau, nhưng cặp `(unscaled=1, scale=0)` khác `(unscaled=10, scale=1)`. Vì vậy khi học các factory và hằng, phải luôn quan sát **cả giá trị và scale**.

## 2. Các overload của valueOf

| API | Kiểu đối số | Hành vi chính |
| --- | --- | --- |
| `BigDecimal.valueOf(long val)` | `long` | Tạo số decimal từ số nguyên chính xác, scale 0 |
| `BigDecimal.valueOf(long unscaledVal, int scale)` | `long`, `int` | Tạo cặp unscaled/scale theo công thức decimal |
| `BigDecimal.valueOf(double val)` | `double` | Tạo từ biểu diễn decimal round-trip của `Double.toString(val)` |

Chọn overload theo **loại thông tin bạn thật sự có**. Nếu nguồn là số nguyên lớn đang lưu trong `long`, tránh đổi sang `double` trước. Nếu nguồn là số nguyên lớn hơn cả `long`, dùng constructor từ `BigInteger` hoặc chuỗi số, thay vì ép về primitive.

Factory là phương thức `static`. Nó không làm tròn toàn bộ dữ liệu một cách “thần kỳ”; nó tạo đối tượng từ **giá trị truyền vào** theo ngữ nghĩa của từng overload.

## 3. valueOf(long): số nguyên chính xác, scale bằng 0

```java
BigDecimal count = BigDecimal.valueOf(12345L);
System.out.println(count);                 // 12345
System.out.println(count.unscaledValue()); // 12345
System.out.println(count.scale());         // 0
```

Mọi giá trị `long` đều có thể biểu diễn chính xác bằng `BigDecimal`. Do đó, factory này rất phù hợp với các trường số nguyên, bộ đếm hoặc giá trị đơn vị nhỏ nhất đã được xác định.

**Không vòng qua double:**

```java
long large = 9_007_199_254_740_993L; // 2^53 + 1.
BigDecimal exact = BigDecimal.valueOf(large); // Chính xác 9007199254740993.
BigDecimal lossy = BigDecimal.valueOf((double) large);
// Double đã làm tròn thành 9007199254740992 trước khi valueOf được gọi.
```

`double` có 53 bit significand hiệu dụng nên không biểu diễn được mọi số nguyên lớn hơn `2^53`. Nếu đã mất một đơn vị ở bước cast, `BigDecimal` không thể phục hồi bit thông tin đó.

## 4. valueOf(long, int): xây dựng từ unscaled value và scale

```java
BigDecimal dollars = BigDecimal.valueOf(12345L, 2);
System.out.println(dollars); // 123.45
```

Hai đối số **không phải “phần nguyên” và “phần thập phân”**. Đối số đầu là unscaled integer, đối số hai là scale. Ví dụ:

| Lời gọi | Giá trị toán học | Kết quả `toString()` trên Java 17 |
| --- | ---: | --- |
| `valueOf(12345L,0)` | 12345 | 12345 |
| `valueOf(12345L,2)` | 123.45 | 123.45 |
| `valueOf(12345L,-2)` | 1234500 | 1.2345E+6 |
| `valueOf(0L,2)` | 0 | 0.00 |

**Scale âm là hợp lệ**: unscaled 12345, scale -2 nghĩa là nhân với `10^2`. Vì thế `toString()` có thể dùng dạng số mũ. Khi một biểu diễn không có số mũ được yêu cầu, dùng `toPlainString()`.

Ứng dụng thường gặp là số tiền lưu bằng đơn vị nhỏ nhất, ví dụ 125 cents và quy tắc decimal scale 2:

```java
long cents = 125;
BigDecimal amount = BigDecimal.valueOf(cents, 2); // 1.25.
```

Cần ghi rõ đơn vị và scale ở hợp đồng dữ liệu. Nếu nguồn đã tính theo đơn vị lớn, áp scale 2 một lần nữa sẽ làm giá trị bị chia cho 100 ngoài ý muốn.

## 5. valueOf(double) được tạo như thế nào?

Với `BigDecimal.valueOf(double)`, Java dùng **biểu diễn chuỗi decimal round-trip** của `double` (tương tự chuyển `Double.toString` rồi dựng BigDecimal). Ví dụ:

```java
BigDecimal value = BigDecimal.valueOf(0.1);
System.out.println(value.toPlainString()); // 0.1
System.out.println(value.scale());         // 1
```

Một `double` lưu gần đúng 0.1 theo nhị phân, nhưng `Double.toString(0.1)` trả `"0.1"` vì đó là chuỗi thập phân ngắn thích hợp để parse ngược về cùng giá trị double. `valueOf(0.1)` từ đó tạo ra **decimal 0.1 với scale 1**.

Điều này không có nghĩa mọi phép tính đã thực hiện trước đó bằng `double` được sửa lại cho chính xác:

```java
double computed = 0.1 + 0.2;
System.out.println(computed);                   // 0.30000000000000004
System.out.println(BigDecimal.valueOf(computed)); // 0.30000000000000004
```

Nếu nghiệp vụ yêu cầu cộng decimal chính xác, nên tạo BigDecimal từ decimal gốc **trước khi cộng**, không sau khi phép cộng double đã gây sai khác.

## 6. valueOf(0.1) khác new BigDecimal(0.1)

Đây là một trong những nhầm lẫn phổ biến nhất:

```java
BigDecimal a = BigDecimal.valueOf(0.1);
BigDecimal b = new BigDecimal(0.1);
BigDecimal c = new BigDecimal("0.1");
```

| Biểu thức | Giá trị hiển thị |
| --- | --- |
| `BigDecimal.valueOf(0.1)` | `0.1` |
| `new BigDecimal("0.1")` | `0.1` |
| `new BigDecimal(0.1)` | `0.1000000000000000055511151231257827021181583404541015625` |

`new BigDecimal(double)` lưu **đúng giá trị thực của mẫu nhị phân double đã có**, diễn đạt nó bằng số thập phân chính xác. Giá trị nhị phân của literal `0.1` hơi lớn hơn đúng 1/10, nên chuỗi dài xuất hiện.

`valueOf(0.1)` dùng chuỗi decimal round-trip `"0.1"`, còn `new BigDecimal("0.1")` đi thẳng từ ký tự người viết nhập. Cả hai tạo decimal chính xác 0.1 trong ví dụ, nhưng nguồn dữ liệu và ý nghĩa API vẫn khác.

**Lựa chọn thực tiễn:** nếu nguồn là chuỗi số tiền, số đo decimal hay dữ liệu JSON decimal cần exact, đọc từ chuỗi decimal với `new BigDecimal(text)`; nếu nguồn là `long`, dùng `valueOf(long)`; nếu phải tiếp nhận `double`, `valueOf(double)` thường có kết quả decimal dễ giải thích hơn constructor trực tiếp từ double, nhưng phải nhớ double đã là đầu vào xấp xỉ.

## 7. Ba hằng ZERO, ONE, TEN

Ba hằng có sẵn:

```java
BigDecimal zero = BigDecimal.ZERO;
BigDecimal one = BigDecimal.ONE;
BigDecimal ten = BigDecimal.TEN;
```

| Hằng | `unscaledValue()` | `scale()` | Giá trị |
| --- | ---: | ---: | ---: |
| `BigDecimal.ZERO` | 0 | 0 | 0 |
| `BigDecimal.ONE` | 1 | 0 | 1 |
| `BigDecimal.TEN` | 10 | 0 | 10 |

Chúng rất hữu ích làm giá trị khởi tạo, số hạng tăng thêm một đơn vị hoặc nhân với 10. Không cần viết `new BigDecimal("0")` lặp đi lặp lại.

```java
BigDecimal total = BigDecimal.ZERO;
total = total.add(BigDecimal.ONE); // 1.
total = total.multiply(BigDecimal.TEN); // 10.
```

**Cả ba hằng có scale 0**, không tự mang scale 2 của tiền tệ. Nếu muốn biểu diễn zero là `0.00`, hãy tạo giá trị có scale 2 từ `ZERO.setScale(2)` hoặc `valueOf(0L,2)`.

## 8. Hằng có giá trị 0 không đồng nghĩa mọi BigDecimal 0 bằng nhau theo equals

Xét:

```java
BigDecimal zero = BigDecimal.ZERO;          // 0, scale 0.
BigDecimal moneyZero = BigDecimal.valueOf(0L, 2); // 0.00, scale 2.

System.out.println(zero.equals(moneyZero));   // false.
System.out.println(zero.compareTo(moneyZero)); // 0.
```

Cả hai bằng zero về mặt toán học. Tuy nhiên:

- `equals()` so sánh **giá trị và scale**, do đó false;
- `compareTo()` so sánh **giá trị số học**, do đó 0;
- `signum()` là 0 đối với mọi BigDecimal có giá trị zero, bất kể scale.

Nếu muốn kiểm tra “số này có bằng 0 không” theo nghiệp vụ số học, dùng `value.signum() == 0` hoặc `value.compareTo(BigDecimal.ZERO) == 0`. Nếu muốn kiểm tra cả biểu diễn scale, dùng `equals` là hợp lý.

**Hệ quả cho collection:** `HashSet<BigDecimal>` dựa trên `equals/hashCode`, trong khi `TreeSet<BigDecimal>` với thứ tự tự nhiên dùng `compareTo`; do đó `1.0` và `1.00` có thể được xem là hai giá trị khóa khác nhau trong HashSet nhưng cùng vị trí thứ tự trong TreeSet. Chọn cấu trúc dữ liệu theo hợp đồng nghiệp vụ.

## 9. valueOf(1L) không giống valueOf(1.0) về scale

Java quyết định overload theo **kiểu tĩnh của tham số**:

```java
BigDecimal integerOne = BigDecimal.valueOf(1L); // 1, scale 0.
BigDecimal decimalOne = BigDecimal.valueOf(1.0); // 1.0, scale 1.

System.out.println(integerOne.equals(BigDecimal.ONE)); // true
System.out.println(decimalOne.equals(BigDecimal.ONE)); // false
System.out.println(decimalOne.compareTo(BigDecimal.ONE)); // 0
```

Cả hai có giá trị số học là 1. Nhưng `Double.toString(1.0)` cho `"1.0"`, nên factory từ double giữ dạng decimal scale 1. Điều này quan trọng với báo cáo số chữ số sau dấu thập phân, mã hóa decimal và các quy tắc nhất quán cho equality/hash.

Có thể đặt scale chủ động:

```java
BigDecimal oneAtScale2 = BigDecimal.ONE.setScale(2);
System.out.println(oneAtScale2.toPlainString()); // 1.00
```

`setScale` trả về kết quả BigDecimal có scale mới; nó không sửa hằng `ONE`.

## 10. BigDecimal không có negative zero riêng

`double` có hai mẫu bit `+0.0` và `-0.0`. `BigDecimal` thì biểu diễn zero với unscaled value bằng 0; không có giá trị toán học zero âm độc lập.

```java
BigDecimal z = BigDecimal.valueOf(-0.0);
System.out.println(z);          // 0.0
System.out.println(z.scale());  // 1
System.out.println(z.signum()); // 0
```

Dấu âm của `-0.0` không được giữ như một trạng thái bit-level của BigDecimal, nhưng **scale 1** của chuỗi `"0.0"` vẫn được giữ. Vì vậy `z.equals(BigDecimal.ZERO)` là false, còn `z.compareTo(BigDecimal.ZERO)` bằng 0.

Nếu một định dạng dữ liệu yêu cầu **bảo toàn bit dấu IEEE 754**, không dùng BigDecimal làm bước trung gian rồi mong khôi phục raw bit zero. Dùng giá trị `double` hoặc raw bits theo một hợp đồng truyền tải thích hợp.

## 11. NaN và Infinity có tạo được BigDecimal hay không?

Không. BigDecimal chỉ biểu diễn những số decimal **hữu hạn**. Vì vậy:

```java
// BigDecimal.valueOf(Double.NaN) -> NumberFormatException.
// BigDecimal.valueOf(Double.POSITIVE_INFINITY) -> NumberFormatException.
```

Kiểm tra trước khi gọi nếu input từ nguồn floating-point không bảo đảm hữu hạn:

```java
static BigDecimal requireFiniteDecimal(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Expected finite value");
    }
    return BigDecimal.valueOf(value);
}
```

Đây là **phương thức minh họa trong lớp** có import BigDecimal, không phải chương trình độc lập. Kiểm tra `Double.isFinite` chỉ xử lý NaN/Infinity, không thể phục hồi số decimal lý tưởng đã mất chính xác trong các phép tính double trước đó.

## 12. BigDecimal bất biến: add không cập nhật đối tượng cũ

`BigDecimal` là lớp **immutable**, nên `add`, `subtract`, `multiply`, `divide`, `setScale` và `stripTrailingZeros` đều trả kết quả, không tự sửa đối tượng gốc.

```java
BigDecimal total = BigDecimal.ZERO;
total.add(BigDecimal.ONE);        // Không dùng giá trị trả về: total vẫn là 0.
total = total.add(BigDecimal.ONE); // total trở thành 1.
```

Đặc biệt khi viết accumulator:

```java
BigDecimal sum = BigDecimal.ZERO;
for (BigDecimal x : amounts) {
    sum = sum.add(x);
}
```

Mảnh mã này giả định `amounts` là danh sách BigDecimal đã có. Với yêu cầu tiền tệ có scale 2, cần định nghĩa chính sách scale/ràng buộc đầu vào thay vì nghĩ rằng hằng ZERO đã tự có đúng hai chữ số thập phân.

Không nên dùng toán tử cộng `+` giữa hai BigDecimal: Java không cho nạp chồng toán tử `+` cho đối tượng này. Dùng `sum.add(x)`.

## 13. MathContext và RoundingMode: valueOf không thay thế chính sách làm tròn

`valueOf` chỉ tạo giá trị; các phép toán tiếp theo có thể cần quy tắc precision/rounding.

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3L);

// one.divide(three) sẽ ném ArithmeticException vì 1/3 vô hạn decimal.

BigDecimal result = one.divide(
        three,
        new java.math.MathContext(10, java.math.RoundingMode.HALF_UP));
System.out.println(result.toPlainString()); // 0.3333333333
```

Một `MathContext` với precision 10 giới hạn kết quả **10 chữ số có nghĩa**, không phải scale 10 mặc định. `setScale(2, RoundingMode.HALF_UP)` là quyết định khác: yêu cầu hai chữ số sau dấu thập phân.

Đừng nhầm `valueOf(12345L,2)` với “làm tròn 12345 đến hai chữ số thập phân”: nó chỉ đặt scale để giá trị trở thành 123.45.

## 14. toString, toPlainString và stripTrailingZeros

Cách in phụ thuộc scale:

```java
BigDecimal a = BigDecimal.valueOf(12345L, -2);
System.out.println(a.toString());       // 1.2345E+6
System.out.println(a.toPlainString()); // 1234500
```

Một số zero ở cuối có thể là **thông tin biểu diễn** mà nghiệp vụ quan tâm:

```java
BigDecimal original = new BigDecimal("10.00");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original); // 10.00
System.out.println(stripped); // 1E+1
```

Hai giá trị đều bằng 10 theo số học, nhưng scale khác. `stripTrailingZeros` không đơn thuần là trang trí hiển thị; nó có thể làm thay đổi scale và kết quả `equals`. Nếu số chữ số sau dấu thập phân được dùng trong báo cáo/hợp đồng, không strip một cách mặc định.

`valueOf(1e20)` cũng cho thấy scale âm tự nhiên xuất hiện từ chuỗi khoa học: trên Java 17, kết quả là `1.0E+20`, unscaled 10, scale -19.

## 15. Hằng TEN, dịch dấu thập phân và đơn vị

`BigDecimal.TEN` có giá trị 10 với scale 0. Có thể nhân với TEN:

```java
BigDecimal hundred = BigDecimal.TEN.multiply(BigDecimal.TEN); // 100.
```

Nếu mục tiêu của bạn là **nhân với lũy thừa 10** hoặc đổi vị trí dấu thập phân, xem các phương thức phù hợp:

```java
BigDecimal amount = new BigDecimal("12.34");
BigDecimal cents = amount.movePointRight(2);       // 1234.
BigDecimal scaled = amount.scaleByPowerOfTen(2);   // 1234 về giá trị.
```

Hai lời gọi có thể cho scale không giống nhau ở một số trường hợp, đặc biệt khi chuyển qua scale âm. Cần xác định yêu cầu về **giá trị** và **scale** riêng, không suy rằng mọi cách nhân 10 đều đồng nhất theo `equals`.

## 16. Có nên so sánh hai giá trị BigDecimal bằng == không?

Không, nếu mục đích là so sánh giá trị. `==` trên đối tượng Java là so sánh **identity tham chiếu**, không phải giá trị decimal. Một số factory có thể tối ưu bằng cách **cache/tái sử dụng đối tượng** cho các số thường gặp; vì thế càng không được dùng kết quả `==` trong nghiệp vụ.

```java
BigDecimal a = BigDecimal.valueOf(1L);
BigDecimal b = BigDecimal.ONE;

// a == b không phải phép so sánh giá trị đáng tin cho mọi API/JDK.
// a.equals(b) là true; a.compareTo(b) == 0 cũng true.
```

Để so sánh **value + scale**, dùng `equals`. Để so sánh **giá trị số học**, dùng `compareTo`. Để kiểm tra **có bằng 0 về số học**, `signum() == 0` thường đơn giản hơn.

## 17. Chọn cách tạo BigDecimal theo nguồn dữ liệu

| Nguồn | Cách tạo khuyến nghị | Lý do |
| --- | --- | --- |
| `long` đã xác thực | `BigDecimal.valueOf(long)` | Bảo toàn số nguyên, scale 0 |
| Số nguyên đơn vị nhỏ nhất + quy ước decimal scale | `BigDecimal.valueOf(unscaled, scale)` | Bảo toàn cặp số decimal |
| Chuỗi decimal từ input/API | `new BigDecimal(String)` | Không vòng qua xấp xỉ nhị phân |
| `double` hữu hạn đã tồn tại | `BigDecimal.valueOf(double)` nếu ngữ nghĩa phù hợp | Dựa trên decimal round-trip |
| Cần nghiên cứu exact binary double | `new BigDecimal(double)` | Lộ rõ giá trị double nhị phân đã lưu |
| Zero làm giá trị khởi tạo | `BigDecimal.ZERO` | Rõ ý nghĩa, scale 0 |
| Một đơn vị | `BigDecimal.ONE` | Rõ ý nghĩa, scale 0 |
| Hệ số 10 | `BigDecimal.TEN` | Rõ ý nghĩa, scale 0 |
| Zero với 2 chữ số decimal | `BigDecimal.ZERO.setScale(2)` | Giữ scale 2 |
| Số nguyên vượt long | `new BigDecimal(BigInteger)` hoặc chuỗi | Không gây mất bit do ép primitive |

Nếu dữ liệu đến từ kết quả tính double `0.1 + 0.2`, chuyển sang BigDecimal sau cùng **không cho đúng decimal 0.3**; phải thiết kế kiểu dữ liệu ngay từ đầu.

## 18. Ví dụ Java 17+ hoàn chỉnh và kết quả chạy

Lưu tệp **`BigDecimalValueOfDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalValueOfDemo {
    static void describe(String label, BigDecimal number) {
        System.out.println(label + "=" + number.toString()
                + ",scale=" + number.scale()
                + ",unscaled=" + number.unscaledValue());
    }

    static String failure(Runnable work) {
        try {
            work.run();
            return "NO_EXCEPTION";
        } catch (ArithmeticException | NumberFormatException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        describe("zeroConstant", BigDecimal.ZERO);
        describe("oneConstant", BigDecimal.ONE);
        describe("tenConstant", BigDecimal.TEN);
        describe("longValueOf", BigDecimal.valueOf(12345L));
        describe("decimalScaled", BigDecimal.valueOf(12345L, 2));
        describe("negativeScale", BigDecimal.valueOf(12345L, -2));
        describe("zeroScale2", BigDecimal.valueOf(0L, 2));
        describe("doublePointOne", BigDecimal.valueOf(0.1));
        describe("doubleConstructor", new BigDecimal(0.1));
        describe("decimalString", new BigDecimal("0.1"));
        describe("onePointZero", BigDecimal.valueOf(1.0));
        describe("negativeDoubleZero", BigDecimal.valueOf(-0.0));
        describe("scientificDouble", BigDecimal.valueOf(1e20));

        System.out.println("valueOfEqualsString="
                + BigDecimal.valueOf(0.1).equals(new BigDecimal("0.1")));
        System.out.println("valueOfEqualsDoubleCtor="
                + BigDecimal.valueOf(0.1).equals(new BigDecimal(0.1)));
        System.out.println("onePointZeroEqualsONE="
                + BigDecimal.valueOf(1.0).equals(BigDecimal.ONE));
        System.out.println("onePointZeroCompareONE="
                + BigDecimal.valueOf(1.0).compareTo(BigDecimal.ONE));
        System.out.println("valueOfOneLongEqualsONE="
                + BigDecimal.valueOf(1L).equals(BigDecimal.ONE));
        System.out.println("scaledZeroEqualsZERO="
                + BigDecimal.valueOf(0L, 2).equals(BigDecimal.ZERO));
        System.out.println("scaledZeroCompareZERO="
                + BigDecimal.valueOf(0L, 2).compareTo(BigDecimal.ZERO));
        System.out.println("negativeZeroEqualsZERO="
                + BigDecimal.valueOf(-0.0).equals(BigDecimal.ZERO));
        System.out.println("negativeZeroSignum="
                + BigDecimal.valueOf(-0.0).signum());

        BigDecimal original = BigDecimal.valueOf(7L);
        BigDecimal increased = original.add(BigDecimal.ONE);
        System.out.println("immutableOriginal=" + original);
        System.out.println("immutableResult=" + increased);

        BigDecimal tenth = BigDecimal.valueOf(0.1);
        BigDecimal fifth = BigDecimal.valueOf(0.2);
        System.out.println("decimalSum=" + tenth.add(fifth).toPlainString());
        System.out.println("binaryDoubleComparison=" + ((0.1 + 0.2) == 0.3));

        System.out.println("divideExactThirdError="
                + failure(() -> BigDecimal.ONE.divide(BigDecimal.valueOf(3L))));
        System.out.println("divideRoundedThird="
                + BigDecimal.ONE.divide(BigDecimal.valueOf(3L),
                        new MathContext(10, RoundingMode.HALF_UP)).toPlainString());
        System.out.println("nanValueOfError="
                + failure(() -> BigDecimal.valueOf(Double.NaN)));
        System.out.println("positiveInfinityValueOfError="
                + failure(() -> BigDecimal.valueOf(Double.POSITIVE_INFINITY)));
        System.out.println("stripTrailingZeros="
                + new BigDecimal("10.00").stripTrailingZeros().toString());
        System.out.println("oneScaled=" + BigDecimal.ONE.setScale(2).toPlainString());
        System.out.println("tenTimesTen=" + BigDecimal.TEN.multiply(BigDecimal.TEN));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 BigDecimalValueOfDemo.java
java BigDecimalValueOfDemo
```

Stdout đã kiểm chứng:

```text
zeroConstant=0,scale=0,unscaled=0
oneConstant=1,scale=0,unscaled=1
tenConstant=10,scale=0,unscaled=10
longValueOf=12345,scale=0,unscaled=12345
decimalScaled=123.45,scale=2,unscaled=12345
negativeScale=1.2345E+6,scale=-2,unscaled=12345
zeroScale2=0.00,scale=2,unscaled=0
doublePointOne=0.1,scale=1,unscaled=1
doubleConstructor=0.1000000000000000055511151231257827021181583404541015625,scale=55,unscaled=1000000000000000055511151231257827021181583404541015625
decimalString=0.1,scale=1,unscaled=1
onePointZero=1.0,scale=1,unscaled=10
negativeDoubleZero=0.0,scale=1,unscaled=0
scientificDouble=1.0E+20,scale=-19,unscaled=10
valueOfEqualsString=true
valueOfEqualsDoubleCtor=false
onePointZeroEqualsONE=false
onePointZeroCompareONE=0
valueOfOneLongEqualsONE=true
scaledZeroEqualsZERO=false
scaledZeroCompareZERO=0
negativeZeroEqualsZERO=false
negativeZeroSignum=0
immutableOriginal=7
immutableResult=8
decimalSum=0.3
binaryDoubleComparison=false
divideExactThirdError=ArithmeticException
divideRoundedThird=0.3333333333
nanValueOfError=NumberFormatException
positiveInfinityValueOfError=NumberFormatException
stripTrailingZeros=1E+1
oneScaled=1.00
tenTimesTen=100
```

Các dòng đầu lần lượt chứng minh hằng ZERO/ONE/TEN có scale 0; `decimalScaled` và `negativeScale` kiểm tra công thức unscaled/scale. `doublePointOne` khác `doubleConstructor` vì đường chuyển đổi từ double khác nhau. `onePointZeroEqualsONE=false` nhưng `onePointZeroCompareONE=0` chứng minh so sánh representation khác so sánh giá trị. `scaledZeroEqualsZERO=false` và `negativeZeroSignum=0` minh họa zero decimal có scale nhưng không có negative-zero value riêng.

`immutableOriginal=7` và `immutableResult=8` chứng minh tính bất biến; `decimalSum=0.3` đối lập với `binaryDoubleComparison=false` khi nguồn số được tạo đúng thời điểm. Các dòng `divideExactThirdError`, `nanValueOfError` và `positiveInfinityValueOfError` cho thấy ràng buộc của phép chia và miền BigDecimal. Hai dòng cuối xác nhận `setScale` và nhân với TEN.

Hàm `failure` trong chương trình bắt ngoại lệ để **hiển thị tên trong bài học**; đây không phải gợi ý nuốt ngoại lệ khi lập trình production.

## 19. Sai lầm hay gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `new BigDecimal(0.1)` tưởng ra decimal 0.1 | Được giá trị binary double triển khai dưới dạng decimal dài | Dùng chuỗi decimal hoặc `valueOf(0.1)` khi phù hợp |
| Dùng `valueOf(double)` để chữa phép tính double đã sai | Giá trị double đã làm tròn trước đó | Tính BigDecimal từ đầu |
| Dùng `valueOf((double)bigLong)` | Mất đơn vị số nguyên lớn trên 2^53 | Gọi `valueOf(long)` |
| Nghĩ `valueOf(12345,2)` nghĩa 12345.2 | Hai tham số là unscaled và scale | Hiểu thành 123.45 |
| Nghĩ hằng ZERO có scale 2 | ZERO có scale 0 | Tạo `ZERO.setScale(2)` |
| Nghĩ `ZERO.equals(0.00)` luôn true | Scale khác khiến equals false | Dùng `compareTo` cho giá trị |
| So sánh BigDecimal bằng `==` | Đang so identity, không phải value | Dùng `equals`/`compareTo` |
| Gọi `sum.add(x)` nhưng không dùng kết quả | Tổng không đổi | Gán `sum = sum.add(x)` |
| Quên chính sách rounding khi chia 1/3 | `ArithmeticException` | Truyền `MathContext` hoặc scale + rounding mode |
| Cho NaN/Infinity vào `valueOf(double)` | `NumberFormatException` | Kiểm tra `Double.isFinite` |
| Dùng `stripTrailingZeros` khi phải giữ scale | Có thể đổi scale và toString | Giữ scale theo hợp đồng |
| Coi `valueOf(1L)` và `valueOf(1.0)` cùng representation | Scale 0 khác scale 1 | Chú ý kiểu đầu vào |

## 20. Câu hỏi tự kiểm tra

1. **BigDecimal được biểu diễn bằng công thức nào?** Unscaled value nhân với `10^(-scale)`.
2. **`valueOf(12345L,2)` tạo số gì?** 123.45.
3. **`valueOf(12345L,-2)` tạo số gì?** 1,234,500; `toString` có thể in `1.2345E+6`.
4. **Vì sao `valueOf(0.1)` khác `new BigDecimal(0.1)`?** Factory đi qua chuỗi decimal round-trip; constructor lấy chính xác giá trị binary double đã làm tròn.
5. **Ba hằng ZERO, ONE, TEN có scale bao nhiêu?** Đều scale 0.
6. **`valueOf(1.0).equals(BigDecimal.ONE)` là gì?** False, vì khác scale.
7. **Nếu muốn so sánh chúng theo giá trị số học?** Dùng `compareTo`, kết quả 0.
8. **Vì sao `BigDecimal.valueOf(0L,2).equals(ZERO)` false?** Hai zero có scale 2 và 0.
9. **Tạo zero với hai chữ số decimal thế nào?** `BigDecimal.ZERO.setScale(2)` hoặc `valueOf(0L,2)`.
10. **`valueOf(-0.0).signum()` bằng bao nhiêu?** 0; BigDecimal không có negative zero riêng.
11. **Có thể đưa `Double.NaN` vào `valueOf` không?** Không, ném `NumberFormatException`.
12. **`BigDecimal.ONE.divide(BigDecimal.valueOf(3L))` có thành công không?** Không nếu không cung cấp rounding context vì 1/3 không có biểu diễn decimal hữu hạn.
13. **Gọi `total.add(ONE)` mà không gán lại có đổi total không?** Không, BigDecimal immutable.
14. **Tạo BigDecimal từ long nguyên lớn bằng cách nào để giữ chính xác?** `valueOf(long)`.
15. **`stripTrailingZeros` có thể đổi scale không?** Có, ví dụ `10.00` thành `1E+1`.
16. **Factory có thể cache object thì có nên dùng `==`?** Không; caching không phải hợp đồng so sánh giá trị.

**Ghi nhớ:** `valueOf(long)` tạo số nguyên decimal chính xác với scale 0; `valueOf(long,scale)` dùng unscaled value và scale; `valueOf(double)` dựa trên biểu diễn decimal round-trip của double hiện có. Các hằng `ZERO`, `ONE`, `TEN` **bất biến** và đều có **scale 0**. Chú ý sự khác nhau giữa giá trị số học và representation scale, kiểm soát rounding ở phép toán, và không dùng `double` làm trung gian nếu cần decimal exact từ đầu.
