# Tạo BigDecimal từ String, BigInteger, long và unscaled value trong Java

`java.math.BigDecimal` là kiểu số thập phân có độ chính xác tùy ý, thích hợp khi cần biểu diễn các giá trị decimal mà `float`/`double` không thể giữ chính xác, chẳng hạn số tiền, đơn giá, tỷ lệ hoặc dữ liệu số thập phân do hệ thống bên ngoài gửi tới. Khi tạo `BigDecimal`, một lựa chọn constructor tưởng như nhỏ có thể **thay đổi scale, độ chính xác, ý nghĩa của dữ liệu và kết quả `equals`**.

Bốn hướng khởi tạo chính trong bài:

1. **Từ chuỗi decimal:** `new BigDecimal("12.3400")` — giữ chính xác các chữ số thập phân đã nhập và scale.
2. **Từ số nguyên lớn `BigInteger`:** `new BigDecimal(new BigInteger("123400"))` — tạo decimal có scale bằng 0.
3. **Từ `long`:** `new BigDecimal(123400L)` hoặc `BigDecimal.valueOf(123400L)` — cũng có scale bằng 0.
4. **Từ *unscaled value* cùng *scale*:** `new BigDecimal(new BigInteger("123400"), 4)` hoặc `BigDecimal.valueOf(123400L, 4)` — tạo giá trị `12.3400`.

Điểm cốt lõi là công thức:

\[
\boxed{\text{BigDecimal value}=\text{unscaledValue}\times 10^{-\text{scale}}}
\]

**Giữ nguyên giá trị số** chưa đủ để giữ nguyên mô hình `BigDecimal`: hai đối tượng có cùng giá trị toán học nhưng khác scale có thể cho `equals() == false`. Chọn cách xây dựng phù hợp với *ngữ nghĩa dữ liệu đầu vào*, không chỉ chọn cách nào biên dịch được.

## 1. Mô hình nội tại: unscaledValue × 10^(-scale)

Một `BigDecimal` về bản chất có hai thành phần:

- Một **giá trị nguyên không scale** (*unscaled value*) với độ chính xác tùy ý, có thể lấy qua `unscaledValue()`.
- Một **scale** kiểu `int`, có thể lấy qua `scale()`.

Ví dụ:

| Cách biểu diễn | Unscaled value | Scale | Giá trị toán học |
| --- | ---: | ---: | ---: |
| `"12.34"` | 1234 | 2 | 12.34 |
| `"12.3400"` | 123400 | 4 | 12.3400 |
| `"1234"` | 1234 | 0 | 1234 |
| `"1.234E+3"` | 1234 | 0 | 1234 |
| `"1.23E+4"` | 123 | -2 | 12300 |
| `"0.000"` | 0 | 3 | 0.000 |
| `"-12.34"` | -1234 | 2 | -12.34 |

Với `scale = 4`, lấy `123400 × 10^-4 = 12.3400`. Với `scale = -2`, lấy `123 × 10^2 = 12300`. **Scale có thể âm**, không phải lúc nào cũng là “số chữ số sau dấu chấm”. Đây là lỗi suy luận thường gặp khi đọc dữ liệu ở ký hiệu khoa học.

Quan sát trực tiếp:

```java
import java.math.BigDecimal;

BigDecimal x = new BigDecimal("12.3400");
System.out.println(x.unscaledValue()); // 123400
System.out.println(x.scale());         // 4
System.out.println(x.precision());     // 6
```

`precision()` là số chữ số có nghĩa của **unscaled value** trong cách biểu diễn thập phân, khác `scale()`. `123400` có sáu chữ số, nên precision bằng 6. Không nhầm precision với tổng số chữ số ở phần lẻ.

`BigDecimal` là **immutable**: constructor tạo giá trị mới, còn các phép cộng/nhân/`setScale` trả giá trị mới, không sửa đối tượng cũ.

## 2. Tạo từ String: giữ đúng giá trị decimal nhập vào

Khi nguồn đã là **chuỗi thập phân**, lựa chọn trực tiếp nhất là:

```java
BigDecimal price = new BigDecimal("12.3400");
BigDecimal tiny = new BigDecimal("0.000000001");
BigDecimal large = new BigDecimal("123456789012345678901234567890.123");
```

Constructor `BigDecimal(String)` **phân tích giá trị decimal chính xác** của chuỗi; nó không đi qua `double`, nên không nhận thêm sai số nhị phân. Các số có rất nhiều chữ số vẫn được biểu diễn theo precision cần thiết trong giới hạn tài nguyên.

### Chuỗi quyết định scale

```java
BigDecimal a = new BigDecimal("12.34");
BigDecimal b = new BigDecimal("12.3400");

System.out.println(a.scale()); // 2
System.out.println(b.scale()); // 4
System.out.println(a.compareTo(b)); // 0: bằng nhau về giá trị số
System.out.println(a.equals(b));    // false: scale khác
```

Các số 0 ở cuối **có thể mang thông tin biểu diễn**. Nếu hệ thống yêu cầu lưu số đo đến bốn chữ số sau dấu thập phân hoặc lưu đơn giá với scale chuẩn, giá trị `"12.3400"` khác `"12.34"` về biểu diễn, mặc dù hai số so sánh bằng nhau theo `compareTo`.

### Cú pháp chuỗi decimal

Những chuỗi sau được hỗ trợ:

```java
new BigDecimal("+12.5");
new BigDecimal("-0.25");
new BigDecimal(".5");
new BigDecimal("5.");
new BigDecimal("1.23E+4");
new BigDecimal("1e-7");
```

Hậu tố exponent `e`/`E` có thể tạo **scale âm hoặc dương** tùy vị trí dấu chấm và độ lớn số mũ. Ví dụ:

```java
BigDecimal scientific = new BigDecimal("1.23E+4");
System.out.println(scientific.unscaledValue()); // 123
System.out.println(scientific.scale());         // -2
System.out.println(scientific.toString());      // 1.23E+4
System.out.println(scientific.toPlainString()); // 12300
```

Constructor nhận String **không phải parser số địa phương** và không tự động làm sạch mọi dữ liệu:

- `new BigDecimal("1,5")` gây `NumberFormatException`, không phụ thuộc vào Locale máy.
- `new BigDecimal("1_000")` gây `NumberFormatException`; dấu gạch dưới có thể hợp lệ trong literal nguồn Java, nhưng **không** trong chuỗi BigDecimal.
- `new BigDecimal("NaN")` và `new BigDecimal("Infinity")` không tạo giá trị BigDecimal đặc biệt; cả hai đều sai cú pháp.
- `new BigDecimal(" 12.5 ")` không tự động loại khoảng trắng đầu/cuối. Nếu hợp đồng cho phép khoảng trắng, có thể chuẩn hóa **có kiểm soát** trước khi parse.
- Tham số String `null` không đại diện cho số 0; cần kiểm tra null trước khi parse, thay vì tự nhận là 0.

**Không âm thầm xóa dấu, separator hoặc ký tự lạ**. Với dữ liệu đầu vào từ API/CSV, hãy định nghĩa rõ ngữ pháp được phép rồi báo lỗi khi không hợp lệ.

## 3. Tạo từ BigInteger: scale mặc định là 0

`BigInteger` là số nguyên có dấu với precision tùy ý. Constructor:

```java
import java.math.BigInteger;

BigInteger integer = new BigInteger("123400");
BigDecimal decimal = new BigDecimal(integer);

System.out.println(decimal.toPlainString()); // 123400
System.out.println(decimal.unscaledValue()); // 123400
System.out.println(decimal.scale());         // 0
```

**Đừng suy luận số nguyên `123400` có dấu thập phân ẩn.** `new BigDecimal(BigInteger)` đặt **scale 0**, nên đại diện cho **123400**, không phải `12.3400`. Nếu `BigInteger` lưu số tiền ở đơn vị cent, micro-unit hoặc tỷ lệ đã nhân hệ số, cần **chuyển scale theo contract**.

Ví dụ dữ liệu đầu vào chứa 123400 **đơn vị nhỏ nhất 1/10000**:

```java
BigInteger storedUnits = new BigInteger("123400");
BigDecimal restored = new BigDecimal(storedUnits, 4);
// 12.3400
```

Dùng số nguyên lớn là cách tốt khi dữ liệu upstream đã lưu bằng **unscaled integer**, chẳng hạn số lượng micro-unit vượt phạm vi `long`. Đó là mô hình **số nguyên + scale**, không phải phép “làm tròn sang số thực”.

### Khác nhau giữa toString(2) và chuỗi decimal

`new BigInteger("101101", 2)` tạo số 45 từ chuỗi nhị phân; `new BigDecimal(theBigInteger)` cho **45** decimal với scale 0. `new BigDecimal("101101")` lại tạo số thập phân một trăm linh một nghìn một trăm linh một. **Radix** là một phần của constructor `BigInteger`, không tự được áp dụng cho chuỗi truyền vào `BigDecimal(String)`.

## 4. Tạo từ long: số nguyên đúng giá trị, scale bằng 0

Đối với một `long` đã có:

```java
long units = 123400L;

BigDecimal fromConstructor = new BigDecimal(units);
BigDecimal fromFactory = BigDecimal.valueOf(units);
```

Cả hai cách đều có giá trị số **123400** và `scale() == 0`. Vì `long` chứa giá trị nguyên chính xác trong miền \([-2^{63}, 2^{63}-1]\), việc chuyển từ `long` sang `BigDecimal` không làm mất chữ số nguyên nào.

`BigDecimal.valueOf(long)` là factory thuận tiện và **có thể tái sử dụng các đối tượng đã tạo**, nên thường được ưu tiên khi không cần constructor trực tiếp. Tuy nhiên, **không dựa vào identity của object** khi viết nghiệp vụ:

```java
BigDecimal a = BigDecimal.valueOf(7L);
BigDecimal b = BigDecimal.valueOf(7L);

System.out.println(a.equals(b)); // true
// Đừng dùng a == b để kiểm tra hai giá trị số bằng nhau.
```

`BigDecimal` là đối tượng. `a == b` hỏi chúng có cùng tham chiếu hay không, không phải hai số có cùng giá trị.

### Nếu long là đơn vị nhỏ nhất, phải truyền scale

Giả sử 12345 là số cent và 1 đơn vị chính chứa 100 cent:

```java
long cents = 12345L;
BigDecimal amount = BigDecimal.valueOf(cents, 2);
// 123.45
```

Nếu viết `BigDecimal.valueOf(cents)` không truyền scale, kết quả là `12345` — **lệch 100 lần** so với giá trị thật. Đây là lỗi dữ liệu, không phải lỗi làm tròn.

Không chuyển số rất lớn vượt `long` thành `long` chỉ để gọi factory; khi giá trị unscaled vượt miền `long`, hãy giữ nó trong `BigInteger`.

## 5. Tạo từ unscaled value: truyền đúng scale

`BigDecimal` có hai cách thuận tiện để gắn decimal scale lên **một giá trị nguyên**:

```java
// Với BigInteger không giới hạn phạm vi long:
BigDecimal a = new BigDecimal(new BigInteger("123400"), 4);

// Với giá trị unscaled đã nằm trong long:
BigDecimal b = BigDecimal.valueOf(123400L, 4);

System.out.println(a.toPlainString()); // 12.3400
System.out.println(b.toPlainString()); // 12.3400
```

Với unscaled value `123400` và scale `4`:

\[
123400\times10^{-4}=12.3400.
\]

Hãy coi `scale` là **tham số mang ngữ nghĩa**, không phải một gợi ý định dạng tùy ý. Chỉ cần đổi scale từ 4 thành 2, giá trị toán học sẽ đổi từ `12.3400` thành `1234.00` dù unscaled value không đổi.

| Unscaled | Scale | `toPlainString()` |
| ---: | ---: | --- |
| 123400 | 0 | `123400` |
| 123400 | 2 | `1234.00` |
| 123400 | 4 | `12.3400` |
| 123400 | 6 | `0.123400` |
| 123 | -2 | `12300` |
| -123400 | 4 | `-12.3400` |

`BigDecimal.valueOf(long unscaledVal, int scale)` chấp nhận cả **scale âm**. Ví dụ:

```java
BigDecimal x = BigDecimal.valueOf(123L, -2);
System.out.println(x.toString());      // 1.23E+4
System.out.println(x.toPlainString()); // 12300
System.out.println(x.unscaledValue()); // 123
System.out.println(x.scale());         // -2
```

**Scale âm không phải lỗi**: có nghĩa nhân với \(10^{|\text{scale}|}\). Khi xuất chuỗi, `toString()` và `toPlainString()` có thể khác định dạng. Nếu phải truyền giá trị cùng scale giữa các hệ thống, nên truyền riêng unscaled value + scale, hoặc chọn biểu diễn văn bản có quy tắc round-trip rõ ràng.

## 6. Mối quan hệ với setScale và movePointLeft

Ba thao tác có thể cùng cho `12.3400` nhưng mang **đầu vào và mục đích khác nhau**:

```java
BigDecimal x = new BigDecimal(new BigInteger("123400"), 4);
BigDecimal y = BigDecimal.valueOf(123400L, 4);
BigDecimal z = BigDecimal.valueOf(123400L).movePointLeft(4);
```

Với `x`, `y`, `z`, kết quả số đều bằng `12.3400` và trong trường hợp cụ thể này có cùng scale 4. Tuy nhiên, các phương thức không có ý nghĩa chung cho mọi đầu vào:

- **Constructor/factory với unscaled + scale:** diễn giải cặp dữ liệu lưu trữ thành đúng một BigDecimal.
- **`movePointLeft(n)`:** biến đổi giá trị số có sẵn bằng nhân \(10^{-n}\); scale mới còn phụ thuộc ngữ nghĩa đặc tả của phương thức, đặc biệt khi đang có scale âm.
- **`setScale(newScale, mode)`:** đổi **scale biểu diễn** nhưng giữ cùng giá trị toán học nếu có thể; khi phải loại chữ số có nghĩa, cần chính sách **rounding**.

Ví dụ không được coi `setScale(4)` giống `movePointLeft(4)`:

```java
BigDecimal value = BigDecimal.valueOf(123400L);
BigDecimal changedScale = value.setScale(4); // 123400.0000
BigDecimal shiftedPoint = value.movePointLeft(4); // 12.3400
```

`setScale(4)` thêm bốn số 0 phần lẻ để giữ nguyên **giá trị 123400**; `movePointLeft(4)` thực sự chia giá trị cho \(10^4\).

Nếu mục đích là khôi phục từ unscaled value, cách rõ nhất vẫn là constructor hoặc factory **hai tham số**.

## 7. Khi có MathContext: constructor có thể làm tròn ngay lúc khởi tạo

Các overload nhận `MathContext` như `new BigDecimal(String, MathContext)`, `new BigDecimal(BigInteger, MathContext)` và `new BigDecimal(long, MathContext)` **khác** constructor không truyền context: chúng có thể chủ động giới hạn **precision** và làm tròn giá trị.

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal exact = new BigDecimal("12345");
BigDecimal rounded = new BigDecimal("12345", context);

System.out.println(exact.toString());   // 12345
System.out.println(rounded.toString()); // 1.23E+4
```

Giá trị mới `1.23E+4` là `12300`; **không còn giữ nguyên giá trị 12345**. Vì vậy lời gọi constructor không phải lúc nào chỉ “chuyển kiểu” mà không đổi số.

| Dạng constructor | Scale khi không dùng MathContext | Có thể làm tròn trong lúc tạo? |
| --- | --- | --- |
| `BigDecimal(String)` | Suy ra từ cú pháp decimal | Không, giữ giá trị decimal chính xác |
| `BigDecimal(BigInteger)` | 0 | Không |
| `BigDecimal(long)` | 0 | Không |
| `BigDecimal(BigInteger, int)` | Scale truyền vào | Không |
| `BigDecimal(String, MathContext)` | Theo kết quả sau round | Có |
| `BigDecimal(BigInteger, MathContext)` | Theo kết quả sau round | Có |
| `BigDecimal(long, MathContext)` | Theo kết quả sau round | Có |

`MathContext.precision()` **không phải** số chữ số sau dấu chấm. Nó giới hạn số **chữ số có nghĩa**. Nếu mục tiêu nghiệp vụ là làm tròn số tiền đến 2 chữ số decimal, không tự dùng `new MathContext(2)` thay cho `setScale(2, roundingMode)`.

Nếu cần lưu giá trị gốc chính xác rồi chỉ làm tròn tại bước chốt, hãy tạo BigDecimal chính xác trước và tách bước làm tròn riêng.

## 8. Giá trị BigDecimal bằng nhau nhưng scale có thể khác

`BigDecimal.compareTo` so sánh **giá trị số**; `BigDecimal.equals` yêu cầu **cùng giá trị và cùng scale**.

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b)); // 0
System.out.println(a.equals(b));    // false
System.out.println(a.scale());      // 1
System.out.println(b.scale());      // 2
```

Điều này có ảnh hưởng trực tiếp khi dùng `BigDecimal` làm khóa trong collection:

- `HashSet<BigDecimal>` sử dụng `equals`/`hashCode`, nên có thể giữ **hai phần tử** `1.0` và `1.00`.
- `TreeSet<BigDecimal>` với thứ tự tự nhiên sử dụng `compareTo` nên thường xem hai giá trị ấy là **trùng nhau**.

Nếu nghiệp vụ muốn bỏ qua trailing zeros để so sánh khóa, có thể dùng chuẩn hóa `stripTrailingZeros()`, nhưng phải hiểu rằng **scale có thể trở thành số âm**:

```java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal normalized = x.stripTrailingZeros();
System.out.println(normalized.toString()); // 1E+3
System.out.println(normalized.scale());    // -3
```

Chuẩn hóa là **quyết định nghiệp vụ**, không phải bước bắt buộc sau mọi constructor. Nếu scale mang ý nghĩa như độ chính xác đo lường hoặc đơn vị tiền tệ, đừng vô tình loại bỏ nó.

## 9. Tránh bẫy tạo BigDecimal qua double

Lý do thường xuyên cần `BigDecimal(String)` là nhiều phân số thập phân **không thể biểu diễn chính xác bằng double**.

```java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal fromDoubleConstructor = new BigDecimal(0.1);
BigDecimal fromDoubleFactory = BigDecimal.valueOf(0.1);
```

Ba cách không hoàn toàn tương đương:

- `new BigDecimal("0.1")`: giá trị decimal đúng bằng một phần mười.
- `new BigDecimal(0.1)`: biểu diễn **chính xác giá trị nhị phân xấp xỉ 0.1** đang nằm trong `double`; thường có rất nhiều chữ số decimal.
- `BigDecimal.valueOf(0.1)`: dùng chuỗi biểu diễn chuẩn của `double` (`Double.toString`) để tạo BigDecimal; với `0.1` cho `0.1`, nhưng **không hồi phục mọi chữ số decimal đã mất trước đó**.

```java
System.out.println(new BigDecimal("0.1").toPlainString());
// 0.1
System.out.println(BigDecimal.valueOf(0.1).toPlainString());
// 0.1
System.out.println(new BigDecimal(0.1).toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

Nếu dữ liệu gốc là decimal từ JSON, database hoặc chuỗi người dùng, giữ **dữ liệu gốc dạng chuỗi hoặc dạng số nguyên + scale** đến khi tạo BigDecimal. Đừng đưa qua `double` rồi hy vọng constructor `BigDecimal` sẽ tái dựng precision đã mất.

## 10. Số 0, số âm và exponent

### Zero có scale vẫn có ý nghĩa biểu diễn

```java
BigDecimal a = new BigDecimal("0");
BigDecimal b = new BigDecimal("0.00");
BigDecimal c = BigDecimal.valueOf(0L, 2);
```

Tất cả có **giá trị số 0**, nhưng `a.scale() == 0`, còn `b.scale() == 2` và `c.scale() == 2`. Nếu đầu vào `"-0.00"`, `BigDecimal` không bảo tồn “âm zero” theo cách `double` làm: kết quả có giá trị **zero với signum() bằng 0**, scale vẫn 2.

```java
BigDecimal negativeZeroText = new BigDecimal("-0.00");
System.out.println(negativeZeroText.toPlainString()); // 0.00
System.out.println(negativeZeroText.signum());        // 0
System.out.println(negativeZeroText.scale());         // 2
```

Nếu hệ thống cần lưu **dấu âm nguyên văn người dùng đã nhập** ở zero, phải lưu thông tin văn bản/dấu đó riêng, không chỉ lưu BigDecimal.

### Exponent ảnh hưởng scale

```java
BigDecimal a = new BigDecimal("1.23E+4");
BigDecimal b = new BigDecimal("12300");

System.out.println(a.compareTo(b)); // 0
System.out.println(a.equals(b));    // false
System.out.println(a.scale());      // -2
System.out.println(b.scale());      // 0
```

Dù `a.toPlainString()` và `b.toPlainString()` đều có thể in `"12300"`, biến `a` lưu scale âm. Muốn round-trip cả **giá trị và scale**, `toString()` có quy tắc biểu diễn chuẩn phù hợp hơn `toPlainString()` trong các trường hợp scale âm. Hoặc truyền **unscaledValue và scale thành hai trường dữ liệu riêng**.

## 11. Chương trình Java 17+ chạy độc lập

Lưu thành tệp **`BigDecimalConstructionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalConstructionDemo {
    public static void main(String[] args) {
        BigDecimal fromString = new BigDecimal("0012.3400");
        System.out.println("fromString=" + fromString.toPlainString());
        System.out.println("stringUnscaled=" + fromString.unscaledValue());
        System.out.println("stringScale=" + fromString.scale());
        System.out.println("stringPrecision=" + fromString.precision());

        BigInteger integer = new BigInteger("123400");
        BigDecimal fromBigInteger = new BigDecimal(integer);
        BigDecimal fromLong = new BigDecimal(123400L);
        BigDecimal fromLongFactory = BigDecimal.valueOf(123400L);
        System.out.println("fromBigInteger=" +
                fromBigInteger.toPlainString());
        System.out.println("fromLong=" + fromLong.toPlainString());
        System.out.println("fromLongFactory=" +
                fromLongFactory.toPlainString());
        System.out.println("integerScale=" + fromBigInteger.scale());

        BigDecimal fromUnscaledBig = new BigDecimal(integer, 4);
        BigDecimal fromUnscaledLong = BigDecimal.valueOf(123400L, 4);
        System.out.println("unscaledBig=" +
                fromUnscaledBig.toPlainString());
        System.out.println("unscaledLong=" +
                fromUnscaledLong.toPlainString());
        System.out.println("sameRepresentation=" +
                fromString.equals(fromUnscaledBig));

        BigDecimal negativeScale = BigDecimal.valueOf(123L, -2);
        System.out.println("negativeScaleText=" +
                negativeScale.toString());
        System.out.println("negativeScalePlain=" +
                negativeScale.toPlainString());
        System.out.println("negativeScaleValue=" +
                negativeScale.unscaledValue());
        System.out.println("negativeScaleScale=" +
                negativeScale.scale());

        BigDecimal fromScientific = new BigDecimal("1.23E+4");
        System.out.println("scientificUnscaled=" +
                fromScientific.unscaledValue());
        System.out.println("scientificScale=" +
                fromScientific.scale());
        System.out.println("scientificEqualsPlain=" +
                fromScientific.equals(new BigDecimal("12300")));
        System.out.println("scientificComparePlain=" +
                fromScientific.compareTo(new BigDecimal("12300")));

        BigDecimal differentScaleA = new BigDecimal("1.0");
        BigDecimal differentScaleB = new BigDecimal("1.00");
        System.out.println("equalsDifferentScale=" +
                differentScaleA.equals(differentScaleB));
        System.out.println("compareDifferentScale=" +
                differentScaleA.compareTo(differentScaleB));

        Set<BigDecimal> hashValues = new HashSet<>();
        hashValues.add(differentScaleA);
        hashValues.add(differentScaleB);
        Set<BigDecimal> sortedValues = new TreeSet<>();
        sortedValues.add(differentScaleA);
        sortedValues.add(differentScaleB);
        System.out.println("hashSetSize=" + hashValues.size());
        System.out.println("treeSetSize=" + sortedValues.size());

        BigDecimal zeroText = new BigDecimal("-0.00");
        System.out.println("zeroText=" + zeroText.toPlainString());
        System.out.println("zeroScale=" + zeroText.scale());
        System.out.println("zeroSignum=" + zeroText.signum());

        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
        BigDecimal exact = new BigDecimal("12345");
        BigDecimal rounded = new BigDecimal("12345", mc);
        System.out.println("contextExact=" + exact.toString());
        System.out.println("contextRounded=" + rounded.toString());
        System.out.println("contextScale=" + rounded.scale());

        System.out.println("scaledCents=" +
                BigDecimal.valueOf(12345L, 2).toPlainString());
        System.out.println("setScaleNotShift=" +
                BigDecimal.valueOf(123400L).setScale(4).toPlainString());
        System.out.println("movePoint=" +
                BigDecimal.valueOf(123400L).movePointLeft(4).toPlainString());

        BigDecimal normalized = new BigDecimal("1000.00")
                .stripTrailingZeros();
        System.out.println("stripTrailingZeros=" +
                normalized.toString());
        System.out.println("stripScale=" + normalized.scale());

        System.out.println("decimalFromString=" +
                new BigDecimal("0.1").toPlainString());
        System.out.println("decimalFromValueOfDouble=" +
                BigDecimal.valueOf(0.1).toPlainString());
        System.out.println("decimalFromDoubleConstructor=" +
                new BigDecimal(0.1).toPlainString());

        try {
            new BigDecimal("1,5");
            System.out.println("invalidComma=missed");
        } catch (NumberFormatException ex) {
            System.out.println("invalidComma=detected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalConstructionDemo.java
java BigDecimalConstructionDemo
```

Kết quả:

```text
fromString=12.3400
stringUnscaled=123400
stringScale=4
stringPrecision=6
fromBigInteger=123400
fromLong=123400
fromLongFactory=123400
integerScale=0
unscaledBig=12.3400
unscaledLong=12.3400
sameRepresentation=true
negativeScaleText=1.23E+4
negativeScalePlain=12300
negativeScaleValue=123
negativeScaleScale=-2
scientificUnscaled=123
scientificScale=-2
scientificEqualsPlain=false
scientificComparePlain=0
equalsDifferentScale=false
compareDifferentScale=0
hashSetSize=2
treeSetSize=1
zeroText=0.00
zeroScale=2
zeroSignum=0
contextExact=12345
contextRounded=1.23E+4
contextScale=-2
scaledCents=123.45
setScaleNotShift=123400.0000
movePoint=12.3400
stripTrailingZeros=1E+3
stripScale=-3
decimalFromString=0.1
decimalFromValueOfDouble=0.1
decimalFromDoubleConstructor=0.1000000000000000055511151231257827021181583404541015625
invalidComma=detected
```

Chương trình cho thấy **giá trị toán học**, **unscaled value**, **scale** và **representation equality** là những khái niệm khác nhau. Chú ý cặp `fromBigInteger=123400` và `unscaledBig=12.3400`: cùng `BigInteger("123400")` nhưng **scale được chọn khác**, nên khác giá trị theo hệ số \(10^4\).

## 12. Các lỗi phổ biến và checklist chọn constructor

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`BigDecimal("12.3400")` tự bỏ trailing zero khi tạo.” | Constructor từ String giữ scale 4 theo cú pháp gốc. |
| “`new BigDecimal(BigInteger("123400"))` tạo 12.3400.” | Không: không truyền scale thì giá trị là 123400, scale 0. |
| “`BigDecimal.valueOf(12345L)` hiểu đó là cent và trả 123.45.” | Không: chỉ `valueOf(12345L,2)` mới mang scale 2. |
| “Scale luôn không âm.” | Sai: `BigDecimal.valueOf(123L,-2)` có giá trị 12300 và scale -2. |
| “`setScale(4)` giống `movePointLeft(4)`.” | Sai: `setScale` giữ giá trị số (hoặc làm tròn nếu cần); movePointLeft thay đổi giá trị. |
| “`equals` và `compareTo` đều chỉ so sánh giá trị số.” | Sai: `equals` xét cả scale, `compareTo` xét giá trị. |
| “`precision=scale`.” | Không: precision là chữ số có nghĩa, scale là độ lớn lũy thừa 10. |
| “BigDecimal lưu âm zero như `double`.” | Không: `new BigDecimal("-0.00")` có `signum()==0` và in `0.00`. |
| “Constructor với `MathContext` không bao giờ làm tròn.” | Có thể giới hạn precision và làm tròn ngay lúc tạo. |
| “`new BigDecimal(0.1)` tái tạo số thập phân 0.1 chính xác.” | Nó tạo giá trị đúng của xấp xỉ nhị phân `double`, không phải decimal 0.1. |
| “`BigDecimal.valueOf(0.1)` khôi phục mọi decimal đã mất trước đó.” | Nó đi qua `Double.toString`; không thể lấy lại precision nguồn đã mất. |
| “BigDecimal(String) đọc theo Locale tiếng Việt mặc định.” | Không: dùng cú pháp decimal, không tự nhận dấu phẩy thập phân. |
| “`toPlainString()` luôn round-trip cả scale.” | Với scale âm, chuỗi plain có thể mất thông tin scale khi parse lại. |
| “`==` thích hợp so sánh hai BigDecimal.” | `==` so sánh reference identity, không phải cùng giá trị số. |

Để chọn cách tạo cho đúng:

1. **Nguồn là String decimal chính xác?** Dùng `new BigDecimal(text)`; xác thực cú pháp và giữ precision đầu vào.
2. **Nguồn là BigInteger với giá trị nguyên thực sự?** Dùng `new BigDecimal(integer)` để có scale 0.
3. **Nguồn là long nguyên thực sự?** Dùng `BigDecimal.valueOf(value)` hoặc `new BigDecimal(value)`, scale 0.
4. **Nguồn là unscaled value có đơn vị ngầm?** Dùng `new BigDecimal(bigInteger, scale)` hoặc `BigDecimal.valueOf(longUnscaled, scale)`; **đừng quên scale**.
5. **Có cần giữ trailing zeros hoặc độ phân giải phép đo không?** Xem `scale()` và chọn canonicalization có chủ đích.
6. **Có cần rounding khi tạo không?** Chỉ truyền `MathContext` nếu đó là yêu cầu; đừng mặc định giới hạn precision ở bước parse.
7. **Dữ liệu đã đi qua double?** Xác định xem có chấp nhận mất precision hay phải quay về decimal string gốc.
8. **Giá trị được lưu/truyền ra hệ ngoài thế nào?** Cân nhắc cặp `unscaledValue + scale` để giữ đầy đủ ngữ nghĩa, và phân biệt `toString` với `toPlainString`.
9. **So sánh hoặc làm khóa collection?** Hiểu khác nhau giữa `equals` và `compareTo`; nếu scale là phần của identity dữ liệu, không tự strip.
10. **Dữ liệu có thể rất lớn hoặc xấu?** Đặt giới hạn độ dài chuỗi và scale hợp lệ theo yêu cầu ứng dụng để tránh xử lý tốn tài nguyên.

**Ghi nhớ:** `BigDecimal` không chỉ là “một số có nhiều chữ số” mà là **unscaled integer cùng scale**. `String` giữ ý nghĩa thập phân của văn bản, `BigInteger` và `long` tạo số nguyên scale 0 khi không chỉ định khác, còn các overload nhận **unscaled value + scale** diễn giải đúng dữ liệu theo đơn vị đã quy định. Chọn constructor đúng giúp tránh lỗi nhân/chia lệch hệ số 10, mất scale và nhầm lẫn trong so sánh.

Tài liệu tham khảo: [Oracle Java 17 — BigDecimal Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).