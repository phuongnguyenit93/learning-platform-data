# Bảng tra cứu BigDecimal: precision, scale, MathContext và RoundingMode

## 1. Bản đồ khái niệm

Khi xử lý số decimal trong Java, bốn khái niệm thường bị nhầm với nhau:

| Khái niệm | Câu hỏi cần trả lời | Được biểu diễn bởi |
| --- | --- | --- |
| **Giá trị số học** | Đây là số bao nhiêu? | Một `BigDecimal` với `unscaledValue` và `scale` |
| **Precision của BigDecimal** | Hệ số nguyên không có số 0 đầu có bao nhiêu chữ số? | `value.precision()` |
| **Scale của BigDecimal** | Dấu thập phân nằm ở đâu so với hệ số nguyên? | `value.scale()`, có thể âm |
| **MathContext** | Phép tính/rounding được phép giữ bao nhiêu **chữ số có nghĩa**? | `new MathContext(precision, roundingMode)` |
| **RoundingMode** | Nếu phải bỏ chữ số thì chọn phía nào? | `RoundingMode.HALF_EVEN`, `HALF_UP`, v.v. |

**Quy tắc quan trọng nhất:** `setScale(2, mode)` yêu cầu hai chữ số **sau dấu thập phân**; `round(new MathContext(2, mode))` yêu cầu tối đa hai chữ số **có nghĩa**. Hai thao tác giải quyết hai vấn đề khác nhau và thường cho hai kết quả khác nhau.

```java
BigDecimal x = new BigDecimal("1234.567");

System.out.println(x.setScale(2, RoundingMode.HALF_UP)); // 1234.57
System.out.println(x.round(new MathContext(3, RoundingMode.HALF_UP))); // 1.23E+3
```

Kết quả thứ nhất giữ hai vị trí thập phân; kết quả thứ hai giữ ba chữ số có nghĩa, tương đương trị số `1230`. Các đoạn code ngắn trong bài giả định đã import `java.math.BigDecimal`, `java.math.MathContext` và `java.math.RoundingMode`; phần 11 cung cấp chương trình Java 17+ độc lập.

## 2. Công thức nền: unscaled value, scale và precision

Theo mô hình của `BigDecimal`:

```text
numeric value = unscaledValue × 10^(-scale)
```

`unscaledValue` là `BigInteger` có dấu; `scale` là số nguyên có thể dương, bằng 0 hoặc âm.

Ví dụ `new BigDecimal("123.4500")` có:

- `unscaledValue() = 1234500`
- `scale() = 4`
- `precision() = 7`
- Trị số bằng `1234500 × 10^-4 = 123.4500`

**Precision không phải “số chữ số trước dấu chấm” hay “số chữ số sau dấu chấm”.** Precision của `BigDecimal` là số chữ số thập phân trong phần hệ số nguyên không dấu, tính từ chữ số khác 0 đầu tiên; với giá trị 0, precision là 1.

| Cách tạo | `toString()` | `unscaledValue()` | `scale()` | `precision()` |
| --- | --- | ---: | ---: | ---: |
| `new BigDecimal("123.4500")` | `123.4500` | 1234500 | 4 | 7 |
| `new BigDecimal("12.34")` | `12.34` | 1234 | 2 | 4 |
| `new BigDecimal("0.00120")` | `0.00120` | 120 | 5 | 3 |
| `new BigDecimal("1000")` | `1000` | 1000 | 0 | 4 |
| `new BigDecimal("1E+3")` | `1E+3` | 1 | -3 | 1 |
| `new BigDecimal("0.000")` | `0.000` | 0 | 3 | 1 |

Bảng cho thấy hai biểu diễn `1000` và `1E+3` có **cùng trị số** nhưng scale/precision khác nhau; `BigDecimal` không chỉ giữ một số thực trừu tượng mà còn mang trạng thái biểu diễn decimal.

### 2.1. Scale âm không phải lỗi

`new BigDecimal("1E+3")` có scale `-3`, tức `1 × 10^3 = 1000`. Khi làm tròn về hàng chục/hàng trăm, `setScale` cũng có thể tạo scale âm:

```java
BigDecimal x = new BigDecimal("1234.56");
BigDecimal hundreds = x.setScale(-2, RoundingMode.HALF_UP);

System.out.println(hundreds);                // 1.2E+3
System.out.println(hundreds.toPlainString()); // 1200
System.out.println(hundreds.scale());         // -2
```

**Scale = -2** nghĩa là vị trí làm tròn ở **hàng trăm**, không phải “giữ -2 chữ số”. Giá trị đã làm tròn là 1200.

### 2.2. Adjusted exponent và biểu diễn khoa học

Một thuộc tính có ích khi đọc tài liệu là *adjusted exponent*:

```text
adjusted exponent = precision - scale - 1
```

Nó cho biết bậc của chữ số có nghĩa đầu tiên đối với các giá trị khác 0. Ví dụ `123.45` có precision 5, scale 2 nên adjusted exponent 2; viết dạng khoa học là khoảng `1.2345 × 10^2`.

`toString()` có thể chọn dạng khoa học; `toPlainString()` viết đủ chữ số không dùng `E`. **Không đánh đồng chuỗi hiển thị với scale**: parse lại chuỗi plain của một `BigDecimal` có scale âm có thể tạo đối tượng cùng trị số nhưng scale 0.

## 3. Bảng đối chiếu các thao tác scale và precision

| API | Ý nghĩa | Có thể phải làm tròn? | Thay đổi đối tượng nguồn? |
| --- | --- | --- | --- |
| `precision()` | Đếm chữ số của hệ số nguyên | Không | Không |
| `scale()` | Trả scale đang lưu | Không | Không |
| `unscaledValue()` | Trả hệ số nguyên `BigInteger` | Không | Không |
| `setScale(newScale)` | Yêu cầu scale cụ thể, **không cho mất chữ số có giá trị** | Nếu cần làm tròn sẽ ném `ArithmeticException` | Không |
| `setScale(newScale, mode)` | Yêu cầu scale cụ thể với mode | Có nếu giảm scale và phải bỏ chữ số khác 0 | Không |
| `round(mathContext)` | Làm tròn theo precision có nghĩa của context | Có nếu `precision > 0` và vượt mức cho phép | Không |
| `plus(mathContext)` | Trả giá trị theo context | Có thể | Không |
| `stripTrailingZeros()` | Bỏ số 0 cuối có thể bỏ trong biểu diễn, giữ trị số | Không đổi trị số | Không |
| `movePointLeft(n)` | Dịch dấu thập phân sang trái `n` vị trí | Không mất precision số học | Không |
| `movePointRight(n)` | Dịch dấu thập phân sang phải `n` vị trí | Không mất precision số học | Không |
| `toPlainString()` | Xuất decimal text không số mũ | Không | Không |

`BigDecimal` là **immutable**. Mỗi phép tính trả kết quả; lời gọi `x.setScale(2, mode);` mà không lưu kết quả **không thay** giá trị `x`. Không cần khẳng định JVM luôn cấp phát một object vật lý mới; điều quan trọng là **ngữ nghĩa bất biến**.

### 3.1. Thay đổi scale có thể chỉ thêm hoặc bỏ các số 0

```java
BigDecimal a = new BigDecimal("12.3");
BigDecimal moreZeros = a.setScale(4);
System.out.println(moreZeros); // 12.3000

BigDecimal b = new BigDecimal("12.3400");
BigDecimal fewerZeros = b.setScale(2);
System.out.println(fewerZeros); // 12.34
```

Hai lời gọi một tham số đều hợp lệ vì **không phải bỏ chữ số khác 0**. Nhưng `new BigDecimal("12.345").setScale(2)` ném `ArithmeticException` do mất chữ số `5`. Muốn cho phép làm tròn, truyền `RoundingMode` rõ ràng.

## 4. MathContext: precision tính toán và rounding mode

`MathContext` chứa hai trường chính:

- `precision`: **số chữ số có nghĩa** được giữ trong phép tính có context; precision `0` nghĩa là **không giới hạn**.
- `roundingMode`: cách chọn kết quả khi phải làm tròn. Nó không có nghĩa “áp dụng rounding dù không mất chữ số”.

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal original = new BigDecimal("1234.567");
BigDecimal rounded = original.round(mc);

System.out.println(rounded);                // 1.23E+3
System.out.println(rounded.toPlainString()); // 1230
```

Khi giới hạn ba chữ số có nghĩa, phép rounding giữ `1, 2, 3` rồi đổi bậc số; vì vậy scale kết quả có thể trở thành âm. `MathContext` **không buộc fixed-scale** và không thay thế `setScale` dùng ở ranh giới hiển thị hoặc lưu trữ.

### 4.1. Những MathContext định nghĩa sẵn

| Hằng số | Precision | Rounding mode | Cách hiểu |
| --- | ---: | --- | --- |
| `MathContext.UNLIMITED` | 0 | `HALF_UP` (ít ý nghĩa vì không ép làm tròn) | Số học thập phân chính xác nếu operation có biểu diễn hữu hạn |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` | Giới hạn 7 chữ số có nghĩa |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` | Giới hạn 16 chữ số có nghĩa |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` | Giới hạn 34 chữ số có nghĩa |

Ba context `DECIMAL32`/`64`/`128` đặt precision và mode như trên; **đừng mặc định rằng chúng tự áp đặt mọi giới hạn exponent, xử lý NaN/Infinity và tất cả quy tắc encoding của định dạng phần cứng IEEE 754 tương ứng**. `BigDecimal` có mô hình kiểu dữ liệu riêng.

`MathContext.UNLIMITED` hoặc `new MathContext(0, mode)` **không phải phép màu** giúp `1 / 3` trở thành thập phân hữu hạn. Khi chia chính xác mà thương là chuỗi decimal vô hạn, `divide` vẫn có thể ném `ArithmeticException`.

### 4.2. Ví dụ context không tương đương setScale

```java
BigDecimal n = new BigDecimal("1234.567");
BigDecimal fixedDecimals = n.setScale(2, RoundingMode.HALF_UP);
BigDecimal significantDigits = n.round(
        new MathContext(3, RoundingMode.HALF_UP));

System.out.println(fixedDecimals);   // 1234.57
System.out.println(significantDigits); // 1.23E+3
```

Tham số 2 của `setScale` là **scale**, còn tham số 3 của `MathContext` là **precision**. Hai số này không cùng đơn vị.

## 5. RoundingMode: bảng đủ tám giá trị

`java.math.RoundingMode` là enum gồm tám chế độ. Bảng dưới làm tròn `+2.5` và `-2.5` tới **scale 0**; cả hai số nằm đúng điểm giữa hai số nguyên kề nhau.

| RoundingMode | Quy tắc | `+2.5 → scale 0` | `-2.5 → scale 0` |
| --- | --- | ---: | ---: |
| `UP` | **Ra xa 0** nếu có phần bị bỏ khác 0 | 3 | -3 |
| `DOWN` | **Về 0**, bỏ phần dư | 2 | -2 |
| `CEILING` | Về **dương vô cực** | 3 | -2 |
| `FLOOR` | Về **âm vô cực** | 2 | -3 |
| `HALF_UP` | Gần nhất, nếu hòa thì **xa 0** | 3 | -3 |
| `HALF_DOWN` | Gần nhất, nếu hòa thì **về 0** | 2 | -2 |
| `HALF_EVEN` | Gần nhất, nếu hòa thì chọn kết quả có chữ số cuối **chẵn** | 2 | -2 |
| `UNNECESSARY` | Yêu cầu kết quả **chính xác, không mất chữ số** | Exception | Exception |

### 5.1. Phân biệt UP/DOWN và CEILING/FLOOR

Tên `UP` trong `RoundingMode` **không đồng nghĩa tăng giá trị số học**: với `-2.5`, `UP` cho `-3` (xa 0), còn `CEILING` cho `-2` (hướng về +∞).

Với `+2.5`: `UP == CEILING` và `DOWN == FLOOR`.

Với `-2.5`: `UP == FLOOR` và `DOWN == CEILING`.

Đó là lý do mọi hàm rounding nhận giá trị có dấu cần test cả dương lẫn âm.

### 5.2. Ba chế độ HALF chỉ khác khi đúng midpoint

Với `2.4` về scale 0, `HALF_UP`, `HALF_DOWN` và `HALF_EVEN` đều cho 2.

Với `2.6`, cả ba đều cho 3.

Với `2.5`:

- `HALF_UP` → 3 (xa 0).
- `HALF_DOWN` → 2 (về 0).
- `HALF_EVEN` → 2 (chọn số chẵn).

Với `3.5`, `HALF_EVEN` → 4 (không phải lúc nào cũng xuống). Tính “even” xét chữ số cuối của **kết quả** ở vị trí đang làm tròn.

### 5.3. UNNECESSARY là công cụ validation

`RoundingMode.UNNECESSARY` không đồng nghĩa “làm tròn xuống” hoặc “không làm gì”. Nó nói: nếu operation yêu cầu làm tròn mất chữ số khác 0 thì **ném `ArithmeticException`**.

```java
System.out.println(new BigDecimal("1.2300")
        .setScale(2, RoundingMode.UNNECESSARY)); // 1.23

// Ném ArithmeticException vì phải bỏ chữ số 4:
new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
```

Sử dụng khi định dạng dữ liệu **phải đúng** với scale quy định; chẳng hạn trường đơn giá chỉ cho tối đa hai chữ số sau dấu phẩy mà chương trình không được tự làm tròn.

## 6. Bảng lựa chọn API theo yêu cầu

| Yêu cầu thực tế | API gợi ý | Điều phải chú ý |
| --- | --- | --- |
| Đọc số chữ số có nghĩa của value | `value.precision()` | Zero có precision 1. |
| Đọc số vị trí scale | `value.scale()` | Scale có thể âm. |
| Hiển thị đúng 2 chữ số thập phân | `value.setScale(2, mode).toPlainString()` | Mode do nghiệp vụ quy định. |
| Chỉ chấp nhận tối đa 2 số lẻ, không làm tròn | `value.setScale(2, UNNECESSARY)` | Thất bại nếu chữ số lẻ vượt mức và khác 0. |
| Làm tròn thành 3 chữ số có nghĩa | `value.round(new MathContext(3, mode))` | Không cố định số chữ số sau dấu chấm. |
| Tính decimal exact khi có thể | `add`, `subtract`, `multiply` không context | Vẫn cần quan tâm giới hạn bộ nhớ/scale và chia không hữu hạn. |
| Cộng/nhân với precision giới hạn | `add(other, mc)`, `multiply(other, mc)` | Kết quả từng bước có thể bị làm tròn. |
| Chia kết quả đúng 2 chữ số sau dấu chấm | `divide(divisor, 2, mode)` | Chọn rounding mode. |
| Chia kết quả tối đa p chữ số có nghĩa | `divide(divisor, new MathContext(p, mode))` | Scale kết quả không cố định. |
| Chia hoàn toàn chính xác | `divide(divisor)` | Nếu thương decimal vô hạn, ném exception. |
| Bỏ số 0 cuối không có ý nghĩa trị số | `stripTrailingZeros()` | Có thể làm scale trở thành âm. |
| Xuất decimal text không số mũ | `toPlainString()` | Không tự chọn scale hay rounding. |
| So sánh trị số thập phân | `a.compareTo(b) == 0` | `equals` còn xét scale. |

Lựa chọn đúng phụ thuộc vào **đơn vị nghĩa của yêu cầu**: “2 chữ số sau dấu chấm” là scale, “2 chữ số có nghĩa” là precision, “làm tròn nửa lên” là mode, “chỉ làm tròn ở bước kết toán” là **thời điểm áp dụng**.

## 7. Bảng tác động của phép toán lên precision và scale

Khi dùng `BigDecimal` không truyền `MathContext`, các phép toán cơ bản thường cho **kết quả thập phân chính xác**. Scale “ưu tiên” của các phép toán giúp người đọc dự đoán cách biểu diễn:

| Phép toán | Giá trị toán học | Scale ưu tiên của kết quả chính xác |
| --- | --- | --- |
| `a.add(b)` | `a + b` | `max(a.scale(), b.scale())` |
| `a.subtract(b)` | `a - b` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a × b` | `a.scale() + b.scale()` |
| `a.divide(b)` | `a / b` | `a.scale() - b.scale()` là scale ưu tiên, nhưng scale kết quả thực có thể tăng để biểu diễn thương hữu hạn chính xác |
| `a.setScale(s, mode)` | Trị số được làm tròn nếu cần | Chính xác `s` |
| `a.round(mc)` | Trị số giới hạn precision | Scale do kết quả rounding quyết định |

Ví dụ:

```java
BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.456"); // scale 3

System.out.println(a.add(b));      // 4.656 (scale 3)
System.out.println(a.multiply(b)); // 4.14720 (scale 5)
```

`multiply` giữ scale cộng từ các toán hạng và có thể in số 0 cuối. Kết quả trị số `4.14720` bằng `4.1472`, nhưng hai đối tượng có thể có scale khác nhau.

### Chia phải phân biệt “chính xác” và “bị làm tròn”

```java
System.out.println(new BigDecimal("1")
        .divide(new BigDecimal("8"))); // 0.125

System.out.println(new BigDecimal("1")
        .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP)); // 0.33

// Ném ArithmeticException vì 1/3 không thể là thập phân hữu hạn chính xác:
new BigDecimal("1").divide(new BigDecimal("3"));
```

Không phải cứ `BigDecimal` là tự động chia ra kết quả vô hạn chữ số. Quy tắc rounding là một phần API và cần được chỉ rõ ở phép chia.

### Khi dùng MathContext tại mỗi bước

`a.add(b, mc)`, `a.multiply(b, mc)` và `a.divide(b, mc)` có thể trả giá trị **đã được làm tròn ngay ở bước đó**. Nếu làm tròn sau từng bước rồi cộng tiếp, tổng cuối có thể khác việc tính ở precision đủ cao rồi làm tròn một lần cuối.

Ví dụ `RoundingMode.HALF_UP` với scale 2:

```text
round2(0.006) + round2(0.006) = 0.01 + 0.01 = 0.02
round2(0.006 + 0.006) = round2(0.012) = 0.01
```

Đây không phải bug của `BigDecimal`: hai quy trình có **thời điểm làm tròn khác nhau**. Nếu nghiệp vụ yêu cầu làm tròn mỗi dòng hóa đơn, cách đầu có thể đúng; nếu chỉ làm tròn tổng cuối, cách sau phù hợp. Cần xác định trước khi dùng context trong mọi phép toán.

## 8. Bảng dấu âm, điểm giữa và các ranh giới

Những test chỉ có số dương dễ bỏ qua lỗi rounding.

| Giá trị gốc | Scale đích | Mode | Kết quả | Lý do |
| --- | ---: | --- | --- | --- |
| `2.5` | 0 | `HALF_UP` | `3` | Midpoint, xa 0 |
| `-2.5` | 0 | `HALF_UP` | `-3` | Midpoint, xa 0 |
| `2.5` | 0 | `HALF_DOWN` | `2` | Midpoint, về 0 |
| `-2.5` | 0 | `HALF_DOWN` | `-2` | Midpoint, về 0 |
| `2.5` | 0 | `HALF_EVEN` | `2` | Midpoint, kết quả chẵn |
| `3.5` | 0 | `HALF_EVEN` | `4` | Midpoint, kết quả chẵn |
| `-2.5` | 0 | `CEILING` | `-2` | Hướng +∞ |
| `-2.5` | 0 | `FLOOR` | `-3` | Hướng -∞ |
| `1.2300` | 2 | `UNNECESSARY` | `1.23` | Bỏ zero, không mất trị số |
| `1.234` | 2 | `UNNECESSARY` | Lỗi | Bỏ chữ số khác 0 |
| `1234.56` | -2 | `HALF_UP` | `1200` | Làm tròn về hàng trăm |

**Phân biệt với `Math.round`:** `Math.round(-2.5)` trả `-2` vì quy tắc điểm giữa của `Math.round` ưu tiên phía dương vô cực, trong khi `new BigDecimal("-2.5").setScale(0, HALF_UP)` trả `-3`. Không đổi qua lại hai API chỉ vì cùng được gọi là “rounding”.

## 9. Precision/scale sau stripTrailingZeros và khi so sánh

`stripTrailingZeros()` bỏ những số 0 cuối không làm đổi trị số. Nhưng representation/scale có thể thay đổi đáng kể:

```java
BigDecimal before = new BigDecimal("1000.00");
BigDecimal after = before.stripTrailingZeros();

System.out.println(before.scale());         // 2
System.out.println(after);                  // 1E+3
System.out.println(after.scale());           // -3
System.out.println(after.toPlainString());  // 1000
```

Với `new BigDecimal("0.000").stripTrailingZeros()`, kết quả là zero chuẩn hóa có scale 0, không còn scale 3.

**Chú ý `equals` khác `compareTo`:**

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));             // false
System.out.println(a.compareTo(b) == 0);     // true
```

`equals` phân biệt scale vì hai biểu diễn khác nhau. `compareTo` so sánh **giá trị số học**. Điều này ảnh hưởng đến khóa `HashMap`/`HashSet` khi dùng `BigDecimal` khác scale: các collection phụ thuộc `equals` không xử lý chúng như cùng object theo trị số.

Nếu hợp đồng định danh là “cùng giá trị decimal”, nên chọn quy tắc chuẩn hóa đầu vào hoặc cấu trúc key phù hợp. Nhưng đừng `stripTrailingZeros` bừa bãi với dữ liệu mà số chữ số lẻ thể hiện ý nghĩa nghiệp vụ (ví dụ các đơn vị tính hoặc format chuẩn).

## 10. Những lựa chọn thiết kế thực tế

### 10.1. Tiền và hóa đơn

Với các giá trị decimal cần tính theo quy định, thường chọn:

1. Đọc decimal chính xác từ chuỗi hoặc kiểu decimal của database, không đi qua `double` không cần thiết.
2. Giữ precision trung gian theo phép toán và hợp đồng.
3. Chỉ áp dụng `setScale(targetScale, roundingMode)` tại **ranh giới làm tròn được chỉ định**.
4. Xuất chuỗi bằng `toPlainString` hoặc formatter theo locale; format không tự thay thế chính sách rounding.

`BigDecimal.valueOf(0.1)` thường tạo biểu diễn `0.1` mong đợi từ literal `double` này, còn `new BigDecimal(0.1)` giữ chính xác giá trị nhị phân xấp xỉ của `double`. Tốt nhất là parse thẳng decimal từ chuỗi khi dữ liệu gốc có sẵn dưới dạng văn bản decimal.

Không mặc định mọi đơn vị tiền tệ đều dùng scale 2 hoặc cùng rounding mode. Luật, hợp đồng, loại tiền và vị trí áp dụng rounding mới quyết định.

### 10.2. Đo lường và số liệu khoa học

Một số đo như `1.230 m` có thể mang thông tin về độ phân giải thiết bị. `precision()` là thuộc tính **biểu diễn BigDecimal**, không phải tự động là sai số đo hoặc số chữ số đáng tin của cảm biến. Có thể cần mô hình đơn vị và sai số đo riêng.

Nếu dữ liệu bản chất xấp xỉ và thuật toán cần hiệu năng, `double` có thể hợp lý. Nếu yêu cầu thập phân chính xác và có quy tắc rounding, `BigDecimal` phù hợp hơn. Không chọn kiểu số chỉ theo thói quen.

### 10.3. Lưu trong database hoặc API

Khi database quy định `DECIMAL(p,s)`, `p` và `s` thường là **precision tổng** và **scale**, nhưng cách cưỡng chế, làm tròn, tràn và giới hạn phụ thuộc hệ quản trị. Phải kiểm tra hợp đồng schema thật; không tự suy rằng `new MathContext(p)` thay thế kiểm tra toàn bộ ràng buộc `DECIMAL(p,s)`.

Ví dụ số có precision ≤9 **và** scale 2 có thể cần kiểm tra số chữ số ở phần nguyên, scale đích và hành vi rounding theo quy định. Một context precision 9 không tự bảo đảm scale chính xác 2.

### 10.4. Lỗi do chia hai lần hoặc round hai lần

`round(finalScale, round(intermediateScale, value))` có thể khác `round(finalScale, value)` với các chế độ gần nhất. Ví dụ `1.245`:

```text
setScale(2, HALF_UP) => 1.25
rồi setScale(1, HALF_UP) => 1.3

setScale(1, HALF_UP) trực tiếp => 1.2
```

Một bước rounding sớm có thể làm mất thông tin vị trí tương đối so với ngưỡng midpoint cuối. Khi cần kết quả có thể kiểm toán, lưu đầy đủ giá trị và chỉ áp dụng rounding tại điểm nghiệp vụ được phép.

## 11. Chương trình Java 17+ hoàn chỉnh (đã kiểm tra kết quả)

Lưu thành file **`PrecisionScaleReferenceDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionScaleReferenceDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.4500");
        BigDecimal z = new BigDecimal("0.000");
        BigDecimal e = new BigDecimal("1E+3");
        BigDecimal stripped = new BigDecimal("1000.00")
                .stripTrailingZeros();

        System.out.println("a precision=" + a.precision()
                + ", scale=" + a.scale());
        System.out.println("z precision=" + z.precision()
                + ", scale=" + z.scale());
        System.out.println("e precision=" + e.precision()
                + ", scale=" + e.scale());
        System.out.println("stripped=" + stripped
                + ", precision=" + stripped.precision()
                + ", scale=" + stripped.scale());

        BigDecimal x = new BigDecimal("1234.567");
        System.out.println("setScale="
                + x.setScale(2, RoundingMode.HALF_UP));
        BigDecimal rounded = x.round(
                new MathContext(3, RoundingMode.HALF_UP));
        System.out.println("mathContext=" + rounded);
        System.out.println("contextPlain=" + rounded.toPlainString());

        System.out.println("exactAdd="
                + new BigDecimal("1.20")
                        .add(new BigDecimal("3.456")));
        System.out.println("exactMultiply="
                + new BigDecimal("1.20")
                        .multiply(new BigDecimal("3.456")));
        System.out.println("divideRounded="
                + new BigDecimal("1")
                        .divide(new BigDecimal("3"), 2,
                                RoundingMode.HALF_UP));

        System.out.println("halfUpPositive="
                + new BigDecimal("2.5")
                        .setScale(0, RoundingMode.HALF_UP));
        System.out.println("halfUpNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.HALF_UP));
        System.out.println("halfEvenPositive="
                + new BigDecimal("2.5")
                        .setScale(0, RoundingMode.HALF_EVEN));
        System.out.println("halfEvenNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.HALF_EVEN));
        System.out.println("ceilingNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.CEILING));
        System.out.println("floorNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.FLOOR));

        BigDecimal hundreds = new BigDecimal("1234.56")
                .setScale(-2, RoundingMode.HALF_UP);
        System.out.println("negativeScale=" + hundreds);
        System.out.println("negativeScalePlain="
                + hundreds.toPlainString());

        System.out.println("unlimitedPrecision="
                + MathContext.UNLIMITED.getPrecision());
        System.out.println("decimal64Precision="
                + MathContext.DECIMAL64.getPrecision());
        System.out.println("trailingZeroScale="
                + z.stripTrailingZeros().scale());
    }
}
```

Chạy trong thư mục chứa file với JDK 17 trở lên:

```bash
javac PrecisionScaleReferenceDemo.java
java PrecisionScaleReferenceDemo
```

**Đầu ra đã đối chiếu khi chạy chương trình:**

```text
a precision=7, scale=4
z precision=1, scale=3
e precision=1, scale=-3
stripped=1E+3, precision=1, scale=-3
setScale=1234.57
mathContext=1.23E+3
contextPlain=1230
exactAdd=4.656
exactMultiply=4.14720
divideRounded=0.33
halfUpPositive=3
halfUpNegative=-3
halfEvenPositive=2
halfEvenNegative=-2
ceilingNegative=-2
floorNegative=-3
negativeScale=1.2E+3
negativeScalePlain=1200
unlimitedPrecision=0
decimal64Precision=16
trailingZeroScale=0
```

Điều cần đối chiếu trong kết quả:

- `a` có precision 7 dù phần thập phân hiển thị có bốn vị trí; `z` có precision 1 dù có ba chữ số 0 sau dấu chấm.
- `setScale` và `MathContext` cho hai kết quả khác vì ràng buộc khác nhau.
- Scale âm tạo chuỗi khoa học khi gọi `toString()`, nhưng `toPlainString()` viết đầy đủ số 0.
- `HALF_UP` đi ra xa 0 khi gặp midpoint; `HALF_EVEN` chọn kết quả chẵn.
- `MathContext.UNLIMITED.getPrecision() == 0` là ký hiệu **không giới hạn precision**, không phải “0 chữ số được giữ”.

## 12. Mẫu code ngắn để kiểm tra nghiệp vụ

### Mẫu A: yêu cầu đúng hai số lẻ, không cho làm tròn

```java
static BigDecimal requireTwoDecimals(BigDecimal value) {
    return value.setScale(2, RoundingMode.UNNECESSARY);
}
```

Nếu value là `1.2300`, kết quả `1.23`; nếu là `1.234`, ném `ArithmeticException`. Phương thức này chỉ minh họa chính sách xác thực, cần đặt trong lớp Java.

### Mẫu B: chỉ làm tròn khi kết toán

```java
static BigDecimal sumThenRound(
        java.util.List<BigDecimal> values) {
    BigDecimal total = BigDecimal.ZERO;
    for (BigDecimal value : values) {
        total = total.add(value);
    }
    return total.setScale(2, RoundingMode.HALF_UP);
}
```

Đây là chính sách mẫu; không phù hợp nếu quy tắc bắt buộc làm tròn **từng khoản trước khi cộng**. Cần tài liệu hóa lý do chọn scale 2 và mode thay vì rải hằng số này khắp codebase.

### Mẫu C: so sánh theo trị số

```java
static boolean numericallyEqual(
        BigDecimal left, BigDecimal right) {
    return left.compareTo(right) == 0;
}
```

`new BigDecimal("1.0")` và `new BigDecimal("1.00")` so sánh theo trị số là bằng nhau, nhưng `equals` cho false vì scale khác. Nếu cần dùng làm khóa hash, nên chuẩn hóa trước theo hợp đồng, không áp dụng ngẫu nhiên chiến lược so sánh khác nhau giữa các lớp.

### Mẫu D: chia với scale tường minh

```java
static BigDecimal divideToTwoDecimals(
        BigDecimal numerator, BigDecimal denominator) {
    return numerator.divide(denominator, 2,
            RoundingMode.HALF_EVEN);
}
```

Phải kiểm tra mẫu số khác 0 và chọn mode theo nghiệp vụ. Đây cũng chỉ là phương thức minh họa.

## 13. Chẩn đoán nhanh các triệu chứng thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `setScale(2)` ném `ArithmeticException` | Cần loại chữ số khác 0 nhưng không truyền mode | Truyền mode **nếu được phép làm tròn**, hoặc dùng `UNNECESSARY` để chủ ý từ chối |
| `divide()` ném lỗi với `1/3` | Thương decimal không hữu hạn | Chọn scale + mode hoặc MathContext theo yêu cầu |
| Kết quả `1.23E+3` thay vì `1230` | Scale âm và cách `toString()` biểu diễn | Dùng `toPlainString()` nếu cần decimal text không số mũ |
| `precision()` ra 1 cho `0.000` | Precision của zero được định nghĩa là 1 | Đừng đồng nhất precision với số chữ số lẻ |
| `setScale(2)` và `round(mc)` khác số | Fixed-scale khác significant digits | Rà lại yêu cầu thật: vị trí decimal hay chữ số có nghĩa? |
| `equals` false dù nhìn số giống nhau | Scale khác nhau | Dùng `compareTo() == 0` nếu chỉ cần bằng trị số |
| Sau `stripTrailingZeros()` xuất hiện `1E+3` | Các zero cuối bị bỏ, scale chuyển âm | Xem yêu cầu giữ scale/trailing zero và chuỗi output |
| Tổng khi song song/làm tròn từng bước bị lệch | Rounding trung gian đổi kết quả | Đặt ranh giới rounding rõ, không làm tròn tùy ý |
| `MathContext.UNLIMITED` vẫn chia `1/3` lỗi | Unlimited precision không tạo decimal vô hạn | Xác định chính sách approximate/round hoặc biểu diễn phân số |
| `new BigDecimal(0.1)` có nhiều chữ số lạ | `double` đầu vào là xấp xỉ nhị phân | Dùng chuỗi decimal hoặc API chuyển phù hợp |

## 14. Câu hỏi tra cứu nhanh

**Câu 1.** `new BigDecimal("0.00120")` có precision và scale bao nhiêu?

**Đáp án:** Precision 3 (các chữ số có nghĩa 1,2,0), scale 5.

**Câu 2.** `new BigDecimal("1E+3")` có scale bao nhiêu?

**Đáp án:** Scale `-3`, precision 1. Trị số là 1000.

**Câu 3.** Muốn `"12.30"` từ `new BigDecimal("12.3")` nên dùng gì?

**Đáp án:** `setScale(2).toPlainString()`, vì thêm zero không làm mất chữ số có giá trị.

**Câu 4.** `setScale(2, HALF_UP)` có giống `round(new MathContext(2, HALF_UP))` không?

**Đáp án:** Không. Một bên giữ hai chữ số thập phân, bên kia giữ hai chữ số có nghĩa.

**Câu 5.** Chế độ nào làm `-2.5` thành `-3` ở scale 0?

**Đáp án:** `UP`, `FLOOR` và `HALF_UP`; `HALF_EVEN` chọn `-2` vì chẵn.

**Câu 6.** `RoundingMode.UNNECESSARY` dùng khi nào?

**Đáp án:** Khi operation phải chính xác tại scale/precision yêu cầu; nếu bắt buộc bỏ chữ số khác 0, API ném `ArithmeticException`.

**Câu 7.** `MathContext.DECIMAL64` có precision/mode nào?

**Đáp án:** Precision 16 và `HALF_EVEN`.

**Câu 8.** `stripTrailingZeros()` có thể tạo scale âm không?

**Đáp án:** Có; `new BigDecimal("1000.00").stripTrailingZeros()` thành biểu diễn `1E+3`, scale `-3`.

**Câu 9.** `BigDecimal.ONE.divide(new BigDecimal("3"))` có trả decimal exact không?

**Đáp án:** Không. Nó ném `ArithmeticException` vì `1/3` không có biểu diễn decimal hữu hạn.

**Câu 10.** Khi nào phải làm tròn tổng thay vì từng phần tử?

**Đáp án:** Khi hợp đồng nghiệp vụ chỉ định ranh giới rounding tại tổng cuối. Không thể suy chính sách từ kiểu `BigDecimal` hay `MathContext`; hai lựa chọn có thể tạo kết quả khác nhau.

## 15. Tài liệu chính thức

- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, `setScale`, `round`, `stripTrailingZeros` và phép toán.
- [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision có nghĩa, rounding mode và các context hằng.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): bảng hành vi đầy đủ các chế độ rounding.

**Tổng kết để tra cứu:** `precision()` đo **chữ số có nghĩa của biểu diễn**, `scale()` xác định **vị trí dấu thập phân**, `MathContext` giới hạn **precision khi tính/round**, `RoundingMode` quyết định **làm tròn về phía nào**, và `setScale` áp dụng một **scale kết quả cụ thể**. Luôn xác định cả **thời điểm làm tròn** và **ý nghĩa nghiệp vụ** trước khi kết hợp các API.
