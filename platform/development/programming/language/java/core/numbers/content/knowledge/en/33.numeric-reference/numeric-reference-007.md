# Bảng tra cứu parse, format và chuyển đổi exact trong Java Core Numbers

## 1. Ba thao tác khác nhau, không thể dùng thay thế tùy tiện

Khi làm việc với số trong Java, cần phân biệt:

1. **Parse (đọc/giải mã):** từ `String` hoặc nguồn văn bản thành giá trị số. Ví dụ `Integer.parseInt("42")`.
2. **Format (biểu diễn):** từ giá trị số thành `String` theo cơ số, số chữ số, dấu phân cách hoặc `Locale`. Ví dụ `number.toPlainString()` hay `DecimalFormat.format(...)`.
3. **Convert (chuyển kiểu):** từ một kiểu số sang kiểu số khác. Một số phép chuyển bảo toàn giá trị; một số **cắt phần lẻ, overflow, làm tròn hoặc mất precision**. Ví dụ `BigDecimal.intValueExact()` khác hẳn `BigDecimal.intValue()`.

Từ khóa **exact** ở đây có ý nghĩa cụ thể: phép chuyển hoặc phép toán phải **không mất giá trị toán học**, hoặc sẽ **ném ngoại lệ** khi không thể bảo toàn theo điều kiện của API. Exact không đồng nghĩa "giữ nguyên chuỗi hiển thị", "giữ nguyên scale" trong mọi trường hợp, hay "mọi phép tính số thực đều chính xác".

Các câu hỏi tra cứu nhanh:

- Chuỗi là thập phân hay cơ số 2/8/16? Có dấu `+`/`-`, tiền tố `0x`, dấu phân cách hàng nghìn?
- Kiểu đích là `int`/`long`, `BigInteger`, `double` hay `BigDecimal`?
- Đầu vào có khả năng `null`, rỗng, ký hiệu `NaN`/`Infinity` hoặc vượt miền số?
- Kết quả cần **giá trị chính xác**, **thập phân với scale cố định**, hay **format theo vùng miền**?
- Nếu không thể chuyển exact, cần ném lỗi, chọn rounding được chỉ định hay dùng kiểu lớn hơn?

## 2. Bảng parse String → kiểu số

| Kiểu cần nhận | Cách parse | Ví dụ | Lưu ý quan trọng |
|---|---|---|---|
| `byte` | `Byte.parseByte(s)` | `"127" → 127` | Chỉ trong miền [-128, 127] |
| `short` | `Short.parseShort(s)` | `"32000" → 32000` | Chỉ trong miền [-32768, 32767] |
| `int` | `Integer.parseInt(s)` | `"42" → 42` | Mặc định thập phân có dấu; sai cú pháp/vượt miền → `NumberFormatException` |
| `long` | `Long.parseLong(s)` | `"9000000000" → 9000000000L` | Cần literal/hàm có kiểu `long` tương ứng |
| `float` | `Float.parseFloat(s)` | `"1.25" → 1.25f` | IEEE 754; có thể làm tròn, hỗ trợ `NaN`/Infinity |
| `double` | `Double.parseDouble(s)` | `"1.25e2" → 125.0` | IEEE 754; chuỗi hữu hạn về cú pháp vẫn có thể vượt phạm vi và thành Infinity |
| `BigInteger` | `new BigInteger(s)` | `"12345678901234567890"` | Số nguyên độ lớn tùy ý theo tài nguyên máy; không nhận phần thập phân |
| `BigDecimal` | `new BigDecimal(s)` | `"123.4500"` | Bảo toàn giá trị thập phân được viết và scale được biểu đạt |
| Wrapper đối tượng | `Integer.valueOf(s)`, `Long.valueOf(s)`... | `Integer.valueOf("42")` | Trả wrapper; không mặc nhiên an toàn với `null` |

Đối với `Integer.parseInt`/`Long.parseLong`, chuỗi có dấu cộng hoặc trừ được hỗ trợ khi cú pháp hợp lệ:

~~~java
int positive = Integer.parseInt("+42"); // 42
int negative = Integer.parseInt("-42"); // -42
~~~

Nhưng dấu phân cách không tự động được chấp nhận:

~~~java
// Integer.parseInt("1,234"); // NumberFormatException
// Integer.parseInt("42.0");  // NumberFormatException
// Integer.parseInt(" 42 ");  // NumberFormatException
~~~

Muốn nhận chuỗi có khoảng trắng, có thể chuẩn hóa theo contract:

~~~java
String raw = " 42 ";
int number = Integer.parseInt(raw.trim()); // 42
~~~

Lưu ý: `trim()` thay đổi chuỗi đầu vào và không đồng nghĩa với xử lý mọi loại khoảng trắng Unicode. Hợp đồng nhập liệu phải quy định có được bỏ khoảng trắng không; đừng chuẩn hóa thầm nếu dữ liệu đòi dạng chặt chẽ.

**Quan trọng:** `Double.parseDouble("NaN")` có thể trả NaN mà **không ném ngoại lệ**. `Double.parseDouble("Infinity")` trả vô cực dương; `Double.parseDouble("1e400")` có thể trở thành vô cực do vượt phạm vi hữu hạn của `double`. Khi ứng dụng chỉ cho phép số hữu hạn, parse xong phải kiểm tra `Double.isFinite(result)`.

## 3. Parse theo cơ số (radix): 2, 8, 10, 16

Có hai nhóm API dễ nhầm.

### 3.1. parseInt(s, radix), parseLong(s, radix)

~~~java
int binary = Integer.parseInt("101010", 2); // 42
int octal = Integer.parseInt("52", 8);      // 42
int hex = Integer.parseInt("2A", 16);       // 42
long l = Long.parseLong("FF", 16);          // 255L
~~~

Tham số `radix` nằm trong khoảng `Character.MIN_RADIX` đến `Character.MAX_RADIX` (2 đến 36). Các chữ cái A–Z/a–z đại diện các chữ số từ 10 đến 35 khi phù hợp. Lưu ý `parseInt("0x2A", 16)` **không** nhận tiền tố `0x` như một chữ số hex hợp lệ; muốn parse chuỗi với tiền tố, có thể dùng `Integer.decode(...)` khi phù hợp.

~~~java
int hex = Integer.decode("0x2A"); // 42
int oct = Integer.decode("052");  // 42 theo cơ số 8
~~~

### 3.2. decode xử lý tiền tố khác với parseInt(radix)

| Chuỗi | `Integer.parseInt(s)` | `Integer.decode(s)` | Giải thích |
|---|---|---|---|
| `"42"` | 42 | 42 | Decimal thông thường |
| `"0x2A"` | Lỗi | 42 | `decode` nhận `0x`/`0X` hoặc `#` |
| `"#2A"` | Lỗi | 42 | Tiền tố hex của `decode` |
| `"052"` | 52 | 42 | `decode` xem số bắt đầu bằng 0 là octal |
| `"08"` | 8 | Lỗi | `8` không phải chữ số octal |
| `"-0x2A"` | Lỗi | -42 | `decode` hỗ trợ dấu trước tiền tố |

`Long.decode` tương tự nhưng cho kiểu `Long`. Hãy dùng `decode` chỉ khi định dạng nguồn thực sự chấp nhận quy tắc tiền tố và octal cũ. Nếu mục tiêu là số nguyên thập phân `"052"` nghĩa là 52, `Integer.parseInt(s, 10)` rõ ràng hơn.

### 3.3. BigInteger theo cơ số

~~~java
BigInteger a = new BigInteger("FF", 16);  // 255
BigInteger b = new BigInteger("1010", 2); // 10

System.out.println(a.toString(16)); // ff
System.out.println(b.toString(2));  // 1010
~~~

`BigInteger(String, radix)` giải mã chữ số theo cơ số được chỉ định; `toString(radix)` xuất cơ số tương ứng. Constructor không tự nhận tiền tố `0x` theo cách của `decode`. `BigInteger` cho số nguyên có độ lớn vượt `long` mà không cần giả làm số nguyên có dấu 64 bit.

## 4. Số nguyên không dấu: parseUnsignedInt/parseUnsignedLong

Java `int` và `long` vẫn là các kiểu nguyên thủy **có dấu**. Các API "unsigned" diễn giải mẫu bit theo miền số không dấu, không tạo một kiểu primitive mới:

~~~java
int bits = Integer.parseUnsignedInt("4294967295");
System.out.println(bits);                          // -1 (nếu in như int có dấu)
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toUnsignedLong(bits));   // 4294967295
~~~

| API | Ý nghĩa |
|---|---|
| `Integer.parseUnsignedInt(s)` | Parse số nguyên không dấu 32 bit thập phân vào mẫu bit của `int` |
| `Integer.parseUnsignedInt(s, radix)` | Parse số nguyên không dấu theo cơ số |
| `Integer.toUnsignedString(int)` | In mẫu bit `int` theo giá trị 0..2^32−1 |
| `Integer.toUnsignedLong(int)` | Nâng giá trị `int` không dấu thành `long` dương, bảo toàn số 0..2^32−1 |
| `Long.parseUnsignedLong(s)` | Parse số không dấu 64 bit vào mẫu bit `long` |
| `Long.toUnsignedString(long)` | In mẫu bit `long` theo giá trị không dấu 0..2^64−1 |

Ví dụ với `Long.parseUnsignedLong("18446744073709551615")`, mẫu bit kết quả có dạng `-1L` khi hiểu là `long` có dấu; `Long.toUnsignedString(...)` sẽ in lại `18446744073709551615`. Muốn thao tác số nguyên vượt miền signed `long` theo **giá trị số học** mà không chỉ thao tác bit, `BigInteger` thường rõ ràng hơn.

Đừng dùng `parseUnsignedInt` rồi tưởng một `int` sẽ biểu diễn số 4.294.967.295 như một `int` dương: điều đó không thể vì `int` chỉ có 32 bit và miền signed tối đa là 2.147.483.647.

## 5. Bảng chuyển đổi số → String (không định dạng locale)

| Mục tiêu | API | Ví dụ/kết quả | Lưu ý |
|---|---|---|---|
| Primitive bất kỳ → chuỗi mặc định | `String.valueOf(value)` | `String.valueOf(42) → "42"` | Có overload cho primitive; không thêm dấu nhóm |
| `int` → decimal | `Integer.toString(42)` | `"42"` | Không thay đổi giá trị |
| `long` → decimal | `Long.toString(42L)` | `"42"` | Không có grouping |
| `int` → hex | `Integer.toHexString(255)` | `"ff"` | Với số âm, thể hiện mẫu bit hai bù; cần hiểu semantics |
| `int` → binary | `Integer.toBinaryString(10)` | `"1010"` | Thể hiện bit theo quy tắc API |
| `int` → octal | `Integer.toOctalString(8)` | `"10"` | Không tự thêm tiền tố `0` |
| `BigInteger` → decimal | `bigInteger.toString()` | Chuỗi số nguyên thập phân | Không giới hạn `int/long` |
| `BigInteger` → radix | `bigInteger.toString(16)` | `255 → "ff"` | Chữ cái thường |
| `BigDecimal` → canonical | `value.toString()` | `1E+4 → "1E+4"` | Parse lại với `BigDecimal(String)` giữ cả giá trị và scale |
| `BigDecimal` → plain | `value.toPlainString()` | `1E+4 → "10000"` | Không có `E`; parse lại có thể mất scale âm |
| `BigDecimal` → engineering | `value.toEngineeringString()` | `1E+4 → "10E+3"` | Nếu dùng số mũ, số mũ bội của 3; parse lại có thể đổi scale |
| `double` → canonical | `Double.toString(value)` | `125.0 → "125.0"` | Có thể dùng dạng `E`, `NaN`, `Infinity` |
| `float` → canonical | `Float.toString(value)` | `1.5f → "1.5"` | Biểu diễn ngắn cho giá trị nhị phân theo quy tắc Java |

Ví dụ phân biệt ba phương thức của `BigDecimal`:

~~~java
BigDecimal x = new BigDecimal("1E+4");

System.out.println(x.toString());            // 1E+4
System.out.println(x.toEngineeringString()); // 10E+3
System.out.println(x.toPlainString());       // 10000
~~~

Cả ba chuỗi thể hiện cùng giá trị `10000`, nhưng **không có bảo đảm cả ba khi parse lại sẽ giữ cùng scale**:

~~~java
BigDecimal original = new BigDecimal("1E+4"); // scale -4
BigDecimal fromPlain = new BigDecimal(original.toPlainString()); // scale 0

System.out.println(original.compareTo(fromPlain) == 0); // true
System.out.println(original.equals(fromPlain));          // false
~~~

`compareTo` so giá trị; `equals` so cả giá trị lẫn scale. Nếu cần serialize rồi parse lại để bảo toàn biểu diễn `BigDecimal`, `toString()` phù hợp hơn `toPlainString()`/`toEngineeringString()`.

## 6. Format theo locale, số chữ số lẻ và dấu nhóm

**Parse/format mặc định của `Integer.parseInt`, `BigDecimal(String)` và `toString()` không dùng dấu phân cách locale**, thường dùng dấu `.` làm dấu thập phân trong chuỗi Java. Nhưng giao diện người dùng có thể cần dấu nhóm và dấu thập phân của từng vùng.

### 6.1. String.format với Locale rõ ràng

~~~java
import java.util.Locale;

String text = String.format(Locale.US, "%,.2f", 12345.67);
// "12,345.67"
~~~

Với format string, `%,.2f` có nghĩa hiển thị số thực với dấu nhóm theo locale và hai chữ số sau dấu thập phân. `%.2f` không phải cơ chế chính để xác định **quy tắc làm tròn tài chính**; khi cần rounding mode nghiệp vụ, hãy chọn và kiểm soát phép làm tròn rõ ràng trước khi xuất.

Một số conversion thường gặp:

| Ký hiệu trong format | Ví dụ | Ý nghĩa |
|---|---|---|
| `%d` | `String.format(Locale.US, "%d", 42)` | Số nguyên decimal |
| `%x` | `String.format(Locale.US, "%x", 255)` | Hex lowercase |
| `%o` | `String.format(Locale.US, "%o", 8)` | Octal |
| `%.2f` | Format số thực 2 chữ số lẻ | Dạng fixed-point, chịu quy tắc của Formatter |
| `%e` | Format số thực dạng số mũ | Dạng scientific theo Formatter |
| `%,.2f` | `12,345.67` | Grouping và 2 chữ số lẻ theo locale |
| `%s` | `String.format("%s", value)` | Chuỗi biểu diễn đối tượng, không phải format số chuyên biệt |

Lưu ý `%d` không áp dụng cho `Double`; loại đối số và conversion phải tương thích. `String.format` có overload nhận `Locale`; không truyền `Locale` có thể khiến kết quả phụ thuộc locale mặc định của JVM.

### 6.2. DecimalFormat / NumberFormat

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

DecimalFormat format = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);

format.setGroupingUsed(true);
format.setMinimumFractionDigits(2);
format.setMaximumFractionDigits(2);
format.setRoundingMode(RoundingMode.HALF_UP);

String output = format.format(new BigDecimal("12345.675"));
// "12,345.68"
~~~

Ở đây `RoundingMode.HALF_UP` được chỉ định rõ. `setMinimumFractionDigits(2)` đệm đủ hai vị trí lẻ khi cần; `setMaximumFractionDigits(2)` hạn chế số vị trí lẻ ở đầu ra. **Việc format không thay đổi đối tượng `BigDecimal` gốc.**

`NumberFormat` và `DecimalFormat` là đối tượng **mutable**, nhìn chung không an toàn để dùng đồng thời từ nhiều thread mà không có phối hợp thích hợp. Trong request nhiều thread, dùng instance cho từng ngữ cảnh hoặc thiết kế tương ứng, không vô tư chia sẻ một formatter rồi sửa thông số.

Khi cần format tiền, có thể dùng `NumberFormat.getCurrencyInstance(locale)`, nhưng ký hiệu tiền tệ, nhóm và số chữ số lẻ là **quy tắc hiển thị**, không đủ để xác định hoàn chỉnh việc tính tiền, đơn vị đồng tiền, làm tròn giao dịch hay chuyển đổi tỷ giá.

## 7. Parse số có định dạng locale: khác parse số kỹ thuật

Chuỗi `"1,234.50"` dùng dấu phẩy ngăn nghìn theo `Locale.US`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

DecimalFormat parser = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
parser.setParseBigDecimal(true);

Number value = parser.parse("1,234.50"); // Có thể ném ParseException.
BigDecimal decimal = (BigDecimal) value; // 1234.50 trong ví dụ hữu hạn này.
~~~

**Không dùng** `new BigDecimal("1,234.50")`: constructor của `BigDecimal` không parse dấu grouping locale. Và `Integer.parseInt("1,234")` cũng không chấp nhận grouping.

### 7.1. Parse locale có thể chấp nhận tiền tố chuỗi — phải kiểm tra hết đầu vào

`NumberFormat.parse(String)` có thể xử lý linh hoạt hơn parser số kỹ thuật và không nhất thiết từ chối toàn bộ chuỗi có phần dư không hợp lệ. Với dữ liệu cần kiểm soát chặt, dùng `ParsePosition`:

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

String input = "1,234.50";
NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);
ParsePosition position = new ParsePosition(0);

Number parsed = parser.parse(input, position);
if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid numeric input");
}
~~~

Kiểm tra `getIndex()` đảm bảo **tất cả ký tự đã được tiêu thụ**. Nhưng điều này **chưa đủ** nếu hợp đồng còn yêu cầu định dạng nhóm hoàn toàn chính xác: parser locale có thể cho phép các dạng linh hoạt. Khi đó cần thêm validation cú pháp theo schema trước khi parse, đồng thời chọn rõ cơ chế dấu decimal/grouping.

Nếu dùng `setParseBigDecimal(true)`, không cast mù kết quả ở mọi đầu vào đặc biệt: một số đầu vào như NaN/Infinity có thể được biểu diễn theo quy tắc riêng của parser và không trả `BigDecimal`. Hãy kiểm tra kiểu kết quả và trạng thái hợp lệ nếu dữ liệu không được đảm bảo hữu hạn.

### 7.2. Format không phải lúc nào có phép nghịch đảo hoàn hảo

Ví dụ `12345.675` format thành `"12,345.68"` sẽ **mất ba phần nghìn** do làm tròn. Parse chuỗi đó trở lại chỉ thu được giá trị đã làm tròn, không thể khôi phục `12345.675`.

Quy tắc:

- **Dùng chuỗi chuẩn để lưu/truyền dữ liệu số chính xác** khi cần round trip, không dùng chuỗi đẹp của giao diện.
- **Dùng formatter cho trình bày**, có thể làm tròn/đệm 0 hoặc chèn dấu nhóm.
- **Lưu thêm đơn vị, scale và chính sách rounding** nếu chúng là phần thiết yếu của hợp đồng nghiệp vụ.

## 8. Bảng chuyển đổi từ primitive/wrapper: widening, narrowing và exact

| Chuyển đổi | Ví dụ | Có bảo toàn mọi giá trị nguồn không? | Ghi chú |
|---|---|---|---|
| `int → long` | `long l = i;` | **Có** | Widening integer |
| `int → double` | `double d = i;` | **Có** | Mọi `int` được biểu diễn chính xác bởi `double` |
| `long → double` | `double d = l;` | **Không** | Số nguyên lớn hơn ngưỡng chính xác `2^53` có thể bị làm tròn |
| `long → int` | `int i = (int) l;` | **Không** | Mất các bit cao nếu không nằm trong miền int |
| `double → int` | `int i = (int) d;` | **Không** | Cắt phần lẻ về 0 và có quy tắc bão hòa/NaN riêng |
| `double → long` | `long l = (long) d;` | **Không** | Có thể cắt/làm mất precision; phải xác thực trước |
| `float → double` | `double d = f;` | **Có đối với giá trị float đã được lưu** | Không biến số thập phân gốc bị làm tròn thành chính xác |
| `double → float` | `float f = (float) d;` | **Không** | Có thể overflow thành vô cực hoặc mất precision |
| `Integer → int` | `int i = wrapper;` | Khi wrapper khác null | Null gây `NullPointerException` |
| `BigInteger → long` | `bi.longValue()` | Không | Có thể mất bit cao |
| `BigDecimal → int` | `bd.intValue()` | Không | Bỏ phần lẻ và có thể mất thông tin do vượt miền |
| `BigDecimal → double` | `bd.doubleValue()` | Không | Có thể làm tròn, underflow/overflow thành 0/Infinity |

Các phép cast và phương thức `intValue()` không có chữ `Exact` là **chuyển đổi cho phép mất thông tin** trong những tình huống nhất định. Không thể chỉ nhìn rằng mã biên dịch thành công để kết luận giá trị được giữ nguyên.

Ví dụ:

~~~java
int truncated = new BigDecimal("12.9").intValue(); // 12

// Có thể khác dữ liệu gốc rất nhiều khi ngoài miền int:
int wrapped = new BigInteger("4294967296").intValue(); // 0 (2^32 bit thấp bằng 0)
~~~

`(int) Double.NaN` cho 0 theo quy tắc narrowing của primitive; `(int) Double.POSITIVE_INFINITY` cho `Integer.MAX_VALUE`. Đây là các quy tắc chuyển đổi ngôn ngữ, **không phải** kiểm tra "giá trị hợp lệ". Nếu NaN/Infinity không được chấp nhận, phải từ chối **trước** khi cast.

## 9. Bảng API chuyển đổi exact

Đây là bảng tham chiếu quan trọng nhất khi quy tắc yêu cầu "không mất giá trị":

| Nguồn → đích | API chính | Thành công khi nào? | Nếu không exact |
|---|---|---|---|
| `long → int` | `Math.toIntExact(long)` | Trong miền signed int | `ArithmeticException` |
| `BigInteger → int` | `bigInteger.intValueExact()` | Trong miền signed int | `ArithmeticException` |
| `BigInteger → long` | `bigInteger.longValueExact()` | Trong miền signed long | `ArithmeticException` |
| `BigInteger → short` | `bigInteger.shortValueExact()` | Trong miền short | `ArithmeticException` |
| `BigInteger → byte` | `bigInteger.byteValueExact()` | Trong miền byte | `ArithmeticException` |
| `BigDecimal → int` | `bd.intValueExact()` | Không có phần lẻ khác 0 và trong miền int | `ArithmeticException` |
| `BigDecimal → long` | `bd.longValueExact()` | Không có phần lẻ khác 0 và trong miền long | `ArithmeticException` |
| `BigDecimal → short/byte` | `bd.shortValueExact()` / `bd.byteValueExact()` | Là số nguyên đúng miền đích | `ArithmeticException` |
| `BigDecimal → BigInteger` | `bd.toBigIntegerExact()` | Giá trị toán học là số nguyên | `ArithmeticException` |
| `BigInteger → BigDecimal` | `new BigDecimal(bi)` | Luôn giữ giá trị nguyên tương ứng | Không mất precision ở bước này |
| `long → BigInteger` | `BigInteger.valueOf(l)` | Toàn bộ miền signed long | Không mất giá trị |
| `long → BigDecimal` | `BigDecimal.valueOf(l)` | Toàn bộ miền signed long | Không mất giá trị |
| Unscaled long + scale → BigDecimal | `BigDecimal.valueOf(unscaled, scale)` | Giá trị chính xác `unscaled × 10^-scale` | Không làm tròn |
| `BigDecimal → BigDecimal scale nhỏ hơn` | `bd.setScale(n, UNNECESSARY)` | Không bỏ chữ số ảnh hưởng giá trị | `ArithmeticException` |

Ví dụ:

~~~java
BigDecimal one = new BigDecimal("12.000");
int exact = one.intValueExact(); // 12 vì phần lẻ đều là 0.

// Hai trường hợp này phải bị từ chối nếu cần chuyển exact:
// new BigDecimal("12.9").intValueExact();        // ArithmeticException
// new BigInteger("2147483648").intValueExact();  // ArithmeticException

long value = 2147483648L;
// Math.toIntExact(value); // ArithmeticException
~~~

**Tính exact đo theo giá trị**, không nhất thiết theo chuỗi. `new BigDecimal("12.000").intValueExact()` cho 12 dù scale ban đầu là 3. Chuyển sang `int` không giữ scale, vì `int` vốn không có scale.

Ví dụ `toBigIntegerExact` với số âm:

~~~java
BigDecimal value = new BigDecimal("-8.000");
BigInteger exact = value.toBigIntegerExact(); // -8

// new BigDecimal("-8.001").toBigIntegerExact();
// ArithmeticException: có phần lẻ khác 0.
~~~

### Có API exact cho BigDecimal → double không?

Không có `BigDecimal.doubleValueExact()` trong API chuẩn. `doubleValue()` có thể mất precision, overflow thành vô cực hoặc underflow. Nếu nghiệp vụ **bắt buộc** biểu diễn chính xác trong `double`, cần quy định phép kiểm tra riêng phù hợp miền và quy tắc ứng dụng; không coi việc cast rồi parse/format trở lại là bằng chứng đủ cho mọi trường hợp.

Ví dụ `BigDecimal("0.1")` là số thập phân chính xác nhưng không thể biểu diễn đúng bằng giá trị nhị phân `double`. Chuyển sang `double` thường chỉ gần đúng.

## 10. Exact arithmetic: phép cộng/nhân không tràn và phép chia

Chuyển đổi exact không thay thế việc kiểm tra **phép tính** exact. Các phép toán primitive signed `int`/`long` có thể overflow và wrap nếu dùng toán tử thường:

~~~java
int max = Integer.MAX_VALUE;
int wrapped = max + 1; // -2147483648

// Math.addExact(max, 1); // ArithmeticException
~~~

Các phương thức toán học kiểm tra overflow gồm:

| Phép | API | Lỗi khi |
|---|---|---|
| Cộng `int/long` | `Math.addExact(a, b)` | Tổng ngoài miền kiểu đích |
| Trừ `int/long` | `Math.subtractExact(a, b)` | Hiệu ngoài miền |
| Nhân `int/long` | `Math.multiplyExact(a, b)` | Tích ngoài miền |
| Tăng/giảm `int/long` | `Math.incrementExact(x)` / `decrementExact(x)` | Vượt giới hạn |
| Đổi dấu `int/long` | `Math.negateExact(x)` | Ví dụ đổi dấu MIN_VALUE |
| Chuyển `long → int` | `Math.toIntExact(x)` | Ngoài miền int |

`BigInteger` thường là giải pháp khi kết quả số nguyên cần vượt giới hạn `long`. Tuy nhiên, số lớn vẫn tiêu thụ bộ nhớ và thời gian; API exact không làm tài nguyên trở nên vô hạn.

### BigDecimal.divide và tính exact

~~~java
BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"));
// 0.125: khai triển thập phân hữu hạn.

// BigDecimal.ONE.divide(new BigDecimal("3"));
// ArithmeticException: biểu diễn thập phân vô hạn nếu không chọn rounding.
~~~

Muốn kết quả xấp xỉ theo quy tắc minh bạch:

~~~java
BigDecimal quotient = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        4,
        RoundingMode.HALF_UP); // 0.3333, scale = 4
~~~

Hoặc dùng precision theo chữ số có nghĩa:

~~~java
BigDecimal q = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        new MathContext(4, RoundingMode.HALF_EVEN)); // 0.3333
~~~

**Khác nhau:** `setScale(4)` / `divide(..., 4, mode)` nói đến **4 chữ số sau dấu thập phân**, còn `MathContext(4)` nói đến **4 chữ số có nghĩa**. Đây là hai kiểu yêu cầu độc lập.

## 11. BigDecimal(String), valueOf(double) và new BigDecimal(double)

Ba cách tạo `BigDecimal` từ ý nghĩa thập phân dễ gây nhầm:

| Cách tạo | Ví dụ | Hành vi |
|---|---|---|
| `new BigDecimal("0.1")` | 0,1 theo hệ thập phân | Lưu chính xác giá trị số thập phân được ghi |
| `BigDecimal.valueOf(0.1)` | Giá trị `double` 0.1 được chuyển qua `Double.toString` | Tạo kết quả biểu diễn ngắn `0.1`, thường phù hợp khi nguồn đã là double |
| `new BigDecimal(0.1)` | Constructor nhận `double` | Biểu diễn **chính xác giá trị double nhị phân đã được lưu**, thường có nhiều chữ số thập phân |

Minh họa:

~~~java
System.out.println(new BigDecimal("0.1"));
// 0.1

System.out.println(BigDecimal.valueOf(0.1));
// 0.1

System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625
~~~

Hai chuỗi `0.1` đầu tiên không chứng minh đầu vào `double 0.1` có thể biểu diễn chính xác 0,1 thập phân. `BigDecimal.valueOf(double)` đi theo chuỗi biểu diễn được `Double.toString` chọn để round-trip giá trị double; `new BigDecimal(double)` phơi bày giá trị nhị phân đã được lưu dưới dạng thập phân chính xác.

Đối với số tiền hoặc giá trị nghiệp vụ thuần thập phân, tốt nhất nhận dữ liệu trực tiếp dưới dạng chuỗi được xác thực hoặc nguồn thập phân có độ chính xác thích hợp rồi tạo `BigDecimal(String)`. Không chuyển `BigDecimal` sang `double` rồi quay lại chỉ để "chuẩn hóa", vì có thể mất precision.

### Giá trị NaN và Infinity

`BigDecimal` không có NaN/Infinity:

~~~java
// BigDecimal.valueOf(Double.NaN); // NumberFormatException
// BigDecimal.valueOf(Double.POSITIVE_INFINITY); // NumberFormatException
~~~

Với nguồn `double` chỉ cho phép số hữu hạn:

~~~java
static BigDecimal requireFiniteDecimal(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("non-finite number");
    }
    return BigDecimal.valueOf(value);
}
~~~

## 12. Chuyển đổi exact không đồng nghĩa làm tròn

Khi một số có phần lẻ, có ít nhất ba chính sách:

1. **Từ chối mất thông tin:** dùng `intValueExact()` / `toBigIntegerExact()`.
2. **Cắt phần lẻ:** dùng `intValue()` / `toBigInteger()` có chủ đích. Đây không phải phép làm tròn gần nhất.
3. **Làm tròn rồi chuyển:** chọn `setScale(0, roundingMode)`, sau đó `intValueExact()` để phát hiện overflow.

~~~java
BigDecimal source = new BigDecimal("12.6");

// 1. Exact: bị từ chối.
// source.intValueExact(); // ArithmeticException

// 2. Truncate về 0:
int truncated = source.intValue(); // 12

// 3. Làm tròn theo chính sách rồi kiểm tra miền int:
int rounded = source.setScale(0, RoundingMode.HALF_UP)
        .intValueExact(); // 13
~~~

Mô hình ở lựa chọn 3 minh bạch: **làm tròn là quyết định nghiệp vụ**, còn `intValueExact` kiểm tra bước chuyển sau rounding còn nằm trong miền int hay không.

Với số âm:

~~~java
BigDecimal minus = new BigDecimal("-12.6");

int towardZero = minus.intValue(); // -12
int floor = minus.setScale(0, RoundingMode.FLOOR)
        .intValueExact(); // -13
~~~

Cắt phần lẻ về 0 khác `FLOOR` khi số âm. Không dùng từ "làm tròn xuống" mơ hồ nếu cần phân biệt hai hành vi.

## 13. Phân biệt precision và scale khi tra cứu

`BigDecimal` biểu diễn giá trị theo:

~~~text
value = unscaledValue × 10^(-scale)
~~~

- `scale()`: độ chia tỷ lệ thập phân, có thể dương, 0 hoặc âm.
- `precision()`: số chữ số của unscaled value, không tính dấu.
- `setScale(n, mode)`: đổi scale về `n`, làm tròn nếu cần.
- `round(new MathContext(p, mode))`: giới hạn tối đa `p` chữ số có nghĩa, không ấn định số chữ số sau dấu chấm.

Ví dụ:

~~~java
BigDecimal amount = new BigDecimal("123.4500");
System.out.println(amount.precision()); // 7
System.out.println(amount.scale());     // 4
~~~

| Yêu cầu | API phù hợp |
|---|---|
| Hiển thị đúng hai chữ số thập phân theo nghiệp vụ | Làm tròn/chuẩn hóa bằng `setScale(2, mode)` trước khi format |
| Giữ ba chữ số có nghĩa | `round(new MathContext(3, mode))` |
| Chỉ bỏ các số 0 cuối không ảnh hưởng giá trị | `stripTrailingZeros()`, lưu ý có thể đổi scale |
| Giảm scale nhưng tuyệt đối không được đổi giá trị | `setScale(newScale, RoundingMode.UNNECESSARY)` |
| Chia lấy đúng hai chữ số sau dấu chấm | `divide(divisor, 2, mode)` |
| Chia theo số chữ số có nghĩa | `divide(divisor, new MathContext(p, mode))` |

`stripTrailingZeros()` giữ nguyên giá trị nhưng có thể làm `equals()` thay đổi do scale khác đi. Ví dụ `new BigDecimal("1000.00").stripTrailingZeros()` có thể trở thành dạng `1E+3`. Đừng áp dụng nếu contract cần giữ đúng scale ban đầu.

### HALF_UP và HALF_EVEN

~~~java
BigDecimal x = new BigDecimal("1.245");

System.out.println(x.setScale(2, RoundingMode.HALF_UP));
// 1.25

System.out.println(x.setScale(2, RoundingMode.HALF_EVEN));
// 1.24
~~~

`HALF_UP` chọn xa 0 khi đúng giữa; `HALF_EVEN` chọn chữ số cuối được giữ là chẵn khi đúng giữa. Chính sách nào đúng phụ thuộc yêu cầu tính toán, không phụ thuộc việc một cách cho chuỗi "đẹp hơn".

## 14. Ví dụ đầy đủ Java 17+: tra cứu parse, format và exact

Tạo tệp `NumericConversionReference.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.util.Locale;

public class NumericConversionReference {
    static void expectedFailure(String name, Runnable operation) {
        try {
            operation.run();
            System.out.println(name + ": unexpectedly succeeded");
        } catch (ArithmeticException | NumberFormatException ex) {
            System.out.println(name + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ParseException {
        System.out.println("parse int radix: " +
                Integer.parseInt("7F", 16));
        System.out.println("decode: " + Integer.decode("0x2A"));
        System.out.println("unsigned: " + Integer.toUnsignedString(
                Integer.parseUnsignedInt("4294967295")));
        System.out.println("parse long: " +
                Long.parseLong("9000000000"));
        System.out.println("parse double NaN: " + Double.isNaN(
                Double.parseDouble("NaN")));
        System.out.println("big integer: " +
                new BigInteger("FF", 16));

        BigDecimal decimal = new BigDecimal("123.4500");
        System.out.println("decimal: " + decimal.toPlainString()
                + ", precision=" + decimal.precision()
                + ", scale=" + decimal.scale());

        BigDecimal scientific = new BigDecimal("1E+4");
        System.out.println("strings: " + scientific
                + " | " + scientific.toEngineeringString()
                + " | " + scientific.toPlainString());

        System.out.println("exact int: " +
                new BigDecimal("12.000").intValueExact());
        System.out.println("truncating int: " +
                new BigDecimal("12.9").intValue());

        expectedFailure("fraction", () ->
                new BigDecimal("12.9").intValueExact());
        expectedFailure("out-of-range", () ->
                Math.toIntExact(2147483648L));
        expectedFailure("big-integer range", () ->
                new BigInteger("2147483648").intValueExact());

        System.out.println("HALF_UP: " +
                new BigDecimal("1.245").setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN: " +
                new BigDecimal("1.245").setScale(2, RoundingMode.HALF_EVEN));

        DecimalFormat format = (DecimalFormat)
                NumberFormat.getNumberInstance(Locale.US);
        format.setGroupingUsed(true);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("formatted: " +
                format.format(new BigDecimal("12345.675")));

        format.setParseBigDecimal(true);
        BigDecimal parsed = (BigDecimal) format.parse("1,234.50");
        System.out.println("localized parse: " + parsed.toPlainString());

        System.out.println("valueOf double: " +
                BigDecimal.valueOf(0.1));
        System.out.println("binary constructor: " +
                new BigDecimal(0.1));
    }
}
~~~

Chạy:

~~~bash
javac NumericConversionReference.java
java NumericConversionReference
~~~

Stdout:

~~~text
parse int radix: 127
decode: 42
unsigned: 4294967295
parse long: 9000000000
parse double NaN: true
big integer: 255
decimal: 123.4500, precision=7, scale=4
strings: 1E+4 | 10E+3 | 10000
exact int: 12
truncating int: 12
fraction: ArithmeticException
out-of-range: ArithmeticException
big-integer range: ArithmeticException
HALF_UP: 1.25
HALF_EVEN: 1.24
formatted: 12,345.68
localized parse: 1234.50
valueOf double: 0.1
binary constructor: 0.1000000000000000055511151231257827021181583404541015625
~~~

Kết quả được gắn với các quy tắc sau:

- `Integer.parseInt("7F",16)` là 127; `decode("0x2A")` nhận tiền tố hex và trả 42.
- `Integer.parseUnsignedInt("4294967295")` giữ bit pattern; `toUnsignedString` hiển thị lại theo giá trị unsigned.
- `new BigDecimal("123.4500")` giữ precision 7, scale 4.
- `1E+4` ở dạng engineering thành `10E+3`, trong khi plain là `10000`.
- `intValueExact` nhận 12.000 vì không có phần lẻ khác 0, từ chối 12.9 và số ngoài miền.
- `HALF_UP` và `HALF_EVEN` khác nhau ở điểm giữa 1.245.
- `DecimalFormat` dùng `Locale.US` và `HALF_UP` rõ ràng; parse ngược chuỗi đã được định dạng cho giá trị sau làm tròn.
- `new BigDecimal(0.1)` phơi bày giá trị nhị phân của `double`, khác với hai cách tạo chuỗi thập phân ngắn ở đầu.

`expectedFailure` chỉ dùng trong demo để biến ngoại lệ dự kiến thành dòng output kiểm tra được. Trong mã nghiệp vụ, không nên bắt `ArithmeticException`/`NumberFormatException` rồi mặc định tiếp tục không xử lý; hãy trả lỗi phù hợp hoặc xử lý input theo contract.

## 15. Bảng lựa chọn nhanh theo nhu cầu

| Nhu cầu thực tế | Chọn | Tránh |
|---|---|---|
| Đọc số nguyên decimal nhỏ trong miền int | `Integer.parseInt(s, 10)` | `Double.parseDouble` rồi cast |
| Đọc số nguyên vượt long | `new BigInteger(s)` | Parse long rồi cố sửa overflow |
| Đọc số tiền/decimal chính xác | `new BigDecimal(validatedString)` | `new BigDecimal(double)` từ input thập phân |
| Đọc số hex có tiền tố `0x` | `Integer.decode(s)` nếu chính sách octal phù hợp | `parseInt(s,16)` trực tiếp trên `0x...` |
| Đọc số hex không tiền tố | `Integer.parseInt(s,16)` hoặc `new BigInteger(s,16)` | Dùng `decode` rồi bỏ qua cú pháp nguồn |
| Đọc unsigned 32-bit | `Integer.parseUnsignedInt` và xuất `toUnsignedString` | Coi `int` kết quả là số dương signed |
| Chuyển long sang int phải exact | `Math.toIntExact` | `(int) longValue` nếu có thể overflow |
| Chuyển BigDecimal sang int phải exact | `intValueExact()` | `intValue()` hoặc cast qua double |
| Chuyển BigDecimal sang BigInteger phải nguyên vẹn | `toBigIntegerExact()` | `toBigInteger()` nếu không muốn cắt phần lẻ |
| Làm tròn decimal đến 2 vị trí | `setScale(2, mode)` | `intValue()`; `MathContext(2)` nếu ý nghĩa là 2 chữ số lẻ |
| In số không có `E` | `toPlainString()` | Giả định nó bảo toàn scale âm sau parse |
| In số để BigDecimal round trip scale | `toString()` | `toEngineeringString()` làm format lưu trữ bắt buộc |
| Hiển thị dấu nhóm và dấu thập phân | `DecimalFormat`/`NumberFormat` theo `Locale` | Ghép dấu bằng thao tác chuỗi tùy tiện |
| Parse số có dấu nhóm locale | `NumberFormat.parse` + kiểm tra hết chuỗi | `BigDecimal(String)` trực tiếp với `1,234.50` |
| Parse double nhưng chỉ chấp nhận hữu hạn | `Double.parseDouble` rồi `Double.isFinite` | Chỉ dựa vào ngoại lệ parse |
| Parse null/blank | Xác định chính sách missing hoặc invalid trước | Unbox/cast null thành primitive |
| Tính tổng số nguyên có thể overflow | `Math.addExact`/`BigInteger` hoặc kiểu lớn thích hợp | Cộng int rồi mới cast kết quả |
| Xuất JSON trao đổi giữa hệ thống | Số hữu hạn/decimal theo schema, xử lý nonfinite riêng | Đưa `NaN`/`Infinity` trực tiếp như số JSON chuẩn |

## 16. Các bẫy thường gặp

### 16.1. Parse số có vẻ đúng nhưng sai định dạng

~~~java
// "01" với parseInt decimal là 1.
// "01" với Integer.decode vẫn là octal, nhưng giá trị cũng là 1.
// "010" với parseInt decimal là 10.
// "010" với Integer.decode là 8.
~~~

Nếu dữ liệu chứa số có số 0 ở đầu, đừng thay `parseInt` bằng `decode` trừ khi hợp đồng thực sự cho phép octal.

### 16.2. Convert nhanh nhưng làm mất phần lẻ

`BigDecimal.intValue()` không ném lỗi chỉ vì có `.9`. Nếu quy tắc yêu cầu toàn bộ giá trị chính xác, hãy dùng `intValueExact()`. Nếu muốn làm tròn, hãy làm tròn theo quy tắc rồi chuyển exact.

### 16.3. Dùng DecimalFormat để chuẩn hóa giá trị bên trong

Format là công đoạn **trình bày**; có thể làm tròn và phụ thuộc locale. Không nên chuyển số thành chuỗi có dấu nhóm rồi parse lại trong lõi tính toán chỉ để "đẹp hơn". Giữ `BigDecimal` làm kiểu dữ liệu số trong thuật toán, định dạng ở biên xuất dữ liệu.

### 16.4. Nhầm exact của giá trị với exact của biểu diễn

`BigDecimal("1.20").compareTo(BigDecimal("1.2")) == 0`, nhưng `equals` là false vì scale khác nhau. `intValueExact()` chỉ đảm bảo số nguyên không mất giá trị; nó không giữ lại "hai chữ số lẻ" ban đầu. Nếu scale là một phần của hợp đồng, phải lưu/kiểm tra scale riêng.

### 16.5. Không phân biệt lỗi parse với lỗi miền

`Integer.parseInt("abc")` ném `NumberFormatException` do không đúng cú pháp. `Integer.parseInt("2147483648")` cũng ném `NumberFormatException` vì vượt miền int. Nếu API cần báo lỗi riêng, có thể kiểm tra cú pháp, sau đó parse vào `BigInteger` hoặc kiểm tra miền một cách có hệ thống; không suy ra mọi `NumberFormatException` đều là lỗi ký tự.

### 16.6. Chia cho 0 hoặc chia thập phân vô hạn mà quên chính sách

`BigDecimal.ONE.divide(BigDecimal.ZERO)` lỗi; `BigDecimal.ONE.divide(new BigDecimal("3"))` cũng có thể lỗi vì không có khai triển thập phân hữu hạn. Nhưng nguyên nhân khác nhau. Nếu kết quả được phép làm tròn, phải chỉ rõ precision/scale và rounding mode.

### 16.7. Dùng format mặc định cho hợp đồng trao đổi

Locale mặc định hoặc thiết lập phân cách có thể đổi giữa máy. Hãy truyền `Locale` cụ thể khi hiển thị, và dùng định dạng bất biến theo giao thức khi serialize. Không coi dấu nhóm giao diện là một phần bắt buộc của biểu diễn số chuẩn Java.

### 16.8. Parser locale có thể bỏ qua phần dư

Dùng `ParsePosition` và so `getIndex() == input.length()`. Đối với yêu cầu format nghiêm ngặt, kết hợp thêm bước validation, vì parser có thể khoan dung với grouping.

### 16.9. Boxing và null

`Integer.valueOf(s)` trả wrapper, `Integer.parseInt(s)` trả primitive. Một `Integer` có thể null, và gán tự động vào `int` sẽ gây `NullPointerException`. Parse/convert nên xác định rõ nullable input trước khi thực hiện phép số học.

## 17. Bài tập tra cứu và đáp án

**Câu 1.** Parse chuỗi `"7F"` thành 127 theo cơ số 16.

**Đáp án:**

~~~java
int value = Integer.parseInt("7F", 16); // 127
~~~

**Câu 2.** Chuyển `new BigDecimal("20.000")` thành `int` mà từ chối mọi trường hợp mất giá trị.

**Đáp án:**

~~~java
int exact = new BigDecimal("20.000").intValueExact(); // 20
~~~

Scale có thể khác 0 nhưng phần lẻ phải hoàn toàn là 0.

**Câu 3.** Vì sao `new BigDecimal("20.3").intValue()` không phù hợp nếu đầu vào phải là số nguyên chính xác?

**Đáp án:** Vì nó cắt phần lẻ và cho 20. Dùng `intValueExact()` để ném `ArithmeticException`.

**Câu 4.** `Math.toIntExact(2147483648L)` làm gì?

**Đáp án:** Ném `ArithmeticException` vì 2.147.483.648 nằm ngoài miền signed `int`.

**Câu 5.** Cần đọc `"1,234.50"` theo quy tắc `Locale.US`. Dùng `new BigDecimal(String)` trực tiếp được không?

**Đáp án:** Không; chuỗi có grouping. Dùng parser locale như `NumberFormat`/`DecimalFormat` theo `Locale.US`, bật parse BigDecimal khi phù hợp và kiểm tra hết chuỗi theo yêu cầu chặt chẽ.

**Câu 6.** So `new BigDecimal("0.1")` với `new BigDecimal(0.1)`.

**Đáp án:** Cách nhận `String` biểu diễn chính xác 0.1 thập phân. Constructor nhận `double` lưu chính xác giá trị nhị phân double, thường được hiển thị bằng nhiều chữ số thập phân.

**Câu 7.** Muốn in `new BigDecimal("1E+4")` ở dạng thường không `E` và vẫn bảo toàn scale -4 khi parse lại: một chuỗi `toPlainString()` có đủ không?

**Đáp án:** Không; `toPlainString()` cho `"10000"`, parse lại có scale 0. Nếu cần bảo toàn scale, `toString()` là định dạng canonical phù hợp.

**Câu 8.** Sau `Integer.parseUnsignedInt("4294967295")`, vì sao `System.out.println(value)` in -1?

**Đáp án:** Giá trị 32 bit toàn bit 1 được lưu trong kiểu signed `int`. In theo signed cho -1; dùng `Integer.toUnsignedString(value)` để hiển thị số không dấu.

**Câu 9.** Parse `"NaN"` vào double có báo lỗi không? Làm sao từ chối?

**Đáp án:** `Double.parseDouble("NaN")` trả NaN. Kiểm tra `Double.isFinite(value)` và từ chối nếu false.

**Câu 10.** Cần làm tròn `1.245` về hai chữ số thập phân theo HALF_EVEN rồi chuyển exact nếu kết quả là số nguyên; thực hiện mấy bước?

**Đáp án:** Thứ nhất `setScale(2, RoundingMode.HALF_EVEN)` cho `1.24`. Thứ hai `intValueExact()` sẽ ném `ArithmeticException` vì kết quả vẫn có phần lẻ khác 0. Làm tròn đến hai chữ số lẻ **không** khiến một giá trị đương nhiên là số nguyên.

---

**Ghi nhớ:** Hãy chọn API theo câu hỏi: **parse** từ chuỗi với đúng radix/locale, **format** số thành chuỗi theo yêu cầu hiển thị, và **convert exact** khi không được mất giá trị. Nếu cần kiểm soát rounding, thực hiện bằng `BigDecimal` với scale/precision và `RoundingMode` được chỉ định; sau đó dùng API `...Exact()` để phát hiện không thể chuyển sang kiểu đích. Đừng thay lỗi bằng một giá trị đã bị cắt, wrap hoặc định dạng lại mà không có hợp đồng nghiệp vụ.