# BigInteger, BigDecimal và giới hạn biểu diễn qua số thực trong Java

## 1. Vì sao phải quan tâm đến độ chính xác khi chuyển từ String?

Khi nhận dữ liệu dưới dạng `String`, ví dụ mã giao dịch `"9007199254740993"` hoặc số tiền `"10.005"`, việc chuyển qua `double` hoặc `float` có thể **mất thông tin trước khi chương trình bắt đầu tính toán**.

Trong Java:

- `BigInteger` biểu diễn **số nguyên có độ lớn tùy ý** về mặt API; giới hạn thực tế do bộ nhớ, kích thước mảng và chi phí tính toán. Nó giữ chính xác các chữ số nguyên mà `int`, `long` hoặc `double` không giữ nổi.
- `BigDecimal` biểu diễn **giá trị thập phân chính xác** bằng một số nguyên không chia tỷ lệ (unscaled value) và một `scale`; rất hữu ích khi chuỗi đầu vào là số tiền, tỷ lệ hoặc số đo thập phân cần quy tắc làm tròn rõ ràng.
- `float` và `double` là **số thực dấu chấm động nhị phân**, chỉ biểu diễn chính xác một tập hữu hạn các giá trị. Nhiều phân số thập phân quen thuộc như `0.1` không có biểu diễn hữu hạn trong hệ nhị phân, dù giá trị in ra có thể trông như `0.1`.

**Nguyên tắc xuyên suốt:** Nếu chuỗi nguồn mang số thập phân cần chính xác, hãy parse **trực tiếp chuỗi** sang `BigDecimal`; nếu mang số nguyên lớn, parse trực tiếp sang `BigInteger`. Tránh vòng `String → double → BigDecimal` hoặc `String → double → BigInteger` vì thông tin mất tại bước `double` sẽ không tự quay lại.

## 2. Mô hình biểu diễn: nguyên lớn, thập phân chính xác và số thực nhị phân

### 2.1. BigInteger: chính xác ở miền số nguyên

`BigInteger` lưu số nguyên với độ chính xác tùy ý và cung cấp các phép `add`, `subtract`, `multiply`, `divide`, `mod`, `pow`, v.v. Ví dụ:

```java
BigInteger population = new BigInteger("9007199254740993");
BigInteger next = population.add(BigInteger.ONE);

System.out.println(next); // 9007199254740994
```

`new BigInteger("9007199254740993")` đọc đầy đủ mọi chữ số của chuỗi. `BigInteger` là kiểu **bất biến (immutable)**: `add` trả về đối tượng kết quả mới; giá trị `population` không bị thay đổi. Với chuỗi số nguyên có dấu `-`, constructor đọc dấu âm đúng cách; với các cơ số khác nhau có thể dùng `new BigInteger(text, radix)`.

### 2.2. BigDecimal: giá trị thập phân = unscaled × 10^(-scale)

`BigDecimal` mô tả giá trị theo công thức:

```text
value = unscaledValue × 10^(-scale)

"123.4500" → unscaledValue = 1234500, scale = 4
"1.23"    → unscaledValue = 123,     scale = 2
"1E+3"    → unscaledValue = 1,       scale = -3
```

Ví dụ:

```java
BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.toPlainString()); // 123.4500
```

`scale` không phải số chữ số có nghĩa (precision). Hai giá trị `new BigDecimal("1.0")` và `new BigDecimal("1.00")` so sánh bằng nhau về **giá trị số học**, nhưng có scale khác nhau.

### 2.3. double: hữu hạn bit và quy tắc làm tròn nhị phân

`double` dùng định dạng IEEE 754 binary64 thông dụng, có **53 bit độ chính xác phần trị** (gồm bit ẩn). Vì vậy, nó biểu diễn **chính xác mọi số nguyên có trị tuyệt đối không vượt quá `2^53 = 9_007_199_254_740_992`**. Khi vượt ngưỡng, **không phải mọi số nguyên liên tiếp** đều còn biểu diễn chính xác; không có nghĩa tất cả số lớn hơn ngưỡng đều sai.

`float` có 24 bit precision của phần trị, nên giới hạn bảo đảm cho mọi số nguyên liên tiếp là `2^24 = 16_777_216`. Cả hai còn có giới hạn **phạm vi** biểu diễn; độ chính xác và phạm vi là hai khái niệm khác nhau.

Ví dụ:

```java
BigInteger original = new BigInteger("9007199254740993");
double rounded = original.doubleValue();

System.out.println(original);                            // 9007199254740993
System.out.println(BigDecimal.valueOf(rounded)
        .toPlainString());                                 // 9007199254740992
```

Giá trị đã đổi thành số nguyên kề bên sau khi qua `double`. Ép trở lại `BigInteger` hoặc `BigDecimal` chỉ lưu **giá trị đã bị làm tròn**; không biết số ban đầu là gì.

## 3. Parse trực tiếp từ String để bảo toàn dữ liệu

### 3.1. Chuỗi số nguyên → BigInteger

```java
String rawId = "9007199254740993";
BigInteger exactId = new BigInteger(rawId);

System.out.println(exactId);  // 9007199254740993
System.out.println(exactId.add(BigInteger.ONE));
// 9007199254740994
```

Với hệ thập lục phân:

```java
BigInteger hex = new BigInteger("FF", 16);
System.out.println(hex); // 255
```

Constructor `BigInteger(String)` đòi cú pháp số nguyên hợp lệ; `"1.5"`, `"1e3"` hoặc chuỗi có khoảng trắng thừa không phải dạng số nguyên thập phân hợp lệ của constructor đó. Có thể chuẩn hóa `strip()` nếu giao thức dữ liệu cho phép khoảng trắng ở hai đầu; không tự loại dấu phân nhóm hoặc dấu phân cách hàng nghìn khi chưa định nghĩa định dạng.

### 3.2. Chuỗi thập phân → BigDecimal

```java
String rawMoney = "0.10";
BigDecimal money = new BigDecimal(rawMoney);

System.out.println(money.toPlainString()); // 0.10
System.out.println(money.scale());         // 2
```

`BigDecimal(String)` giữ **giá trị thập phân được biểu diễn trong văn bản** và scale tương ứng. Không cần đi qua `Double.parseDouble(rawMoney)`. Với `"00123.4500"`, giá trị số học được lưu chính xác, nhưng thông tin **định dạng ban đầu** như các số `0` đứng trước không được giữ nguyên trong `BigDecimal`; nếu phải khôi phục chính xác chuỗi gốc, hãy lưu riêng chuỗi đầu vào.

Một số trường hợp hợp lệ và không hợp lệ:

| Chuỗi | Cách xử lý |
| --- | --- |
| `"123456789012345678901234567890"` | `new BigInteger(text)` giữ đúng số nguyên lớn |
| `"-100.0250"` | `new BigDecimal(text)` giữ chính xác số thập phân và scale |
| `"1.23E+4"` | `new BigDecimal(text)` chấp nhận ký pháp khoa học |
| `"1,25"` | Không phải cú pháp decimal dùng dấu chấm mà constructor mong đợi; cần parser theo locale nếu dữ liệu thật sự có dấu phẩy thập phân |
| `"NaN"` hoặc `"Infinity"` | Không phải số thập phân hữu hạn của `BigDecimal(String)` |
| `" 42 "` | Cần quyết định có `strip()` hai đầu hay coi là dữ liệu không hợp lệ |

`NumberFormatException` là ngoại lệ thường gặp khi chuỗi không hợp lệ. Với dữ liệu người dùng, xử lý rõ ràng thay vì mặc định các chuỗi đều parse thành công.

## 4. Sự khác nhau giữa new BigDecimal(0.1) và BigDecimal.valueOf(0.1)

Ví dụ kinh điển:

```java
System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(BigDecimal.valueOf(0.1));
// 0.1

System.out.println(new BigDecimal("0.1"));
// 0.1
```

Ba trường hợp khác nhau:

1. `new BigDecimal(0.1)` nhận **giá trị binary64 của literal `0.1`**, tức giá trị nhị phân gần `0.1` nhất. Constructor biểu diễn **chính xác giá trị double đã nhận**, nên phần đuôi dài lộ ra.
2. `BigDecimal.valueOf(0.1)` dựa trên biểu diễn thập phân mà `Double.toString(0.1)` trả về, ở đây là `"0.1"`; vì vậy kết quả dễ đọc, giá trị decimal là `0.1`.
3. `new BigDecimal("0.1")` đọc thẳng văn bản thập phân, không có giai đoạn qua `double`. Đây là lựa chọn đúng khi cần bảo toàn chính xác số thập phân từ dữ liệu nguồn.

**Cảnh báo về `valueOf(double)`:** Nó không thể khôi phục thông tin đã mất ở phép tính double trước đó:

```java
double sum = 0.1 + 0.2;

System.out.println(sum);                       // 0.30000000000000004
System.out.println(BigDecimal.valueOf(sum));   // 0.30000000000000004
System.out.println(new BigDecimal("0.1")
        .add(new BigDecimal("0.2")));           // 0.3
```

Do đó `BigDecimal.valueOf(double)` hữu ích khi **bắt buộc** giao tiếp với một API trả `double`, nhưng không đồng nghĩa “chuyển double thành số thập phân ban đầu một cách hoàn hảo”. Nếu đầu vào gốc là `String`, hãy parse thẳng.

## 5. Chuyển đổi chính xác, chuyển đổi bị cắt và chuyển đổi mất mát

### 5.1. BigInteger → int/long

`BigInteger.intValue()` và `BigInteger.longValue()` có thể **mất các bit cao** khi giá trị không vừa kiểu đích, không nhất thiết ném ngoại lệ. Khi nghiệp vụ đòi nguyên vẹn, dùng các phiên bản `intValueExact()` và `longValueExact()`:

```java
BigInteger small = new BigInteger("123");
System.out.println(small.intValueExact()); // 123

BigInteger oversized = new BigInteger("9223372036854775808");
// oversized.longValueExact() ném ArithmeticException
```

Giá trị `9223372036854775808` lớn hơn `Long.MAX_VALUE` đúng 1. Dùng `longValueExact()` để phát hiện vấn đề trước khi ghi vào bảng dữ liệu hoặc gọi API chỉ nhận `long`. Tương tự, không dùng `Integer.parseInt(...)` hay `Long.parseLong(...)` cho chuỗi có thể vượt miền tương ứng; chúng ném `NumberFormatException` khi tràn giới hạn.

### 5.2. BigDecimal → BigInteger: mất phần lẻ

`BigDecimal.toBigInteger()` **cắt bỏ phần thập phân về phía 0**, không làm tròn theo `HALF_UP` và không ném lỗi vì có phần lẻ:

```java
System.out.println(new BigDecimal("99.9").toBigInteger()); // 99
System.out.println(new BigDecimal("-99.9").toBigInteger()); // -99
```

Ngược lại, `toBigIntegerExact()` ném `ArithmeticException` nếu phần thập phân khác 0. Ví dụ `new BigDecimal("99.0").toBigIntegerExact()` hợp lệ vì phần lẻ bằng 0, nhưng `new BigDecimal("99.9").toBigIntegerExact()` không hợp lệ.

Muốn làm tròn trước khi lấy số nguyên thì chọn chính sách rõ ràng:

```java
BigInteger rounded = new BigDecimal("99.9")
        .setScale(0, RoundingMode.HALF_UP)
        .toBigIntegerExact();
System.out.println(rounded); // 100
```

### 5.3. BigDecimal → int/long

`intValue()`, `longValue()` có thể bỏ phần lẻ và/hoặc mất bit do vượt phạm vi. `intValueExact()`, `longValueExact()` ném `ArithmeticException` nếu có phần lẻ không bằng 0 hoặc phần nguyên không vừa kiểu đích. Dùng phiên bản `Exact` tại ranh giới của các API đòi kiểu nguyên cố định.

### 5.4. BigInteger/BigDecimal → float/double

`doubleValue()` và `floatValue()` là chuyển đổi **có thể mất độ chính xác**. Nếu độ lớn vượt phạm vi số thực nhị phân, kết quả có thể là `Infinity` hoặc `-Infinity`; nếu giá trị quá nhỏ (với `BigDecimal`), chuyển đổi có thể làm tròn thành `0.0`. Không dùng `doubleValue()` cho giá trị định danh, số tiền hoặc phép so sánh bắt buộc chính xác.

Không có bảo đảm rằng `new BigDecimal(...).doubleValue()` rồi `BigDecimal.valueOf(...)` sẽ giữ nguyên `BigDecimal` ban đầu.

## 6. Ví dụ Java 17+ chạy độc lập

Tạo file **`BigNumbersFromStringDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class BigNumbersFromStringDemo {
    public static void main(String[] args) {
        BigInteger id = new BigInteger("9007199254740993");
        System.out.println("integer exact = " + id);
        System.out.println("double roundtrip = "
                + BigDecimal.valueOf(id.doubleValue()).toPlainString());

        System.out.println("new BigDecimal(0.1) = " + new BigDecimal(0.1));
        System.out.println("valueOf(0.1) = " + BigDecimal.valueOf(0.1));

        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("double sum = " + binarySum);
        System.out.println("decimal sum = " + decimalSum);

        BigDecimal rounded = new BigDecimal("10.005")
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println("round = " + rounded);

        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"), 4, RoundingMode.HALF_UP);
        System.out.println("third = " + third);

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal anotherOne = new BigDecimal("1.00");
        System.out.println("equals = " + one.equals(anotherOne));
        System.out.println("compareTo = " + one.compareTo(anotherOne));

        BigDecimal fractional = new BigDecimal("99.9");
        System.out.println("truncated = " + fractional.toBigInteger());
        try {
            fractional.toBigIntegerExact();
        } catch (ArithmeticException ex) {
            System.out.println("fraction rejected");
        }

        System.out.println("plain = " + new BigDecimal("1000.00")
                .stripTrailingZeros().toPlainString());
        System.out.println("scientific = " + new BigDecimal("1000.00")
                .stripTrailingZeros().toString());
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 BigNumbersFromStringDemo.java
java BigNumbersFromStringDemo
```

Stdout mong đợi (đã kiểm tra các biểu thức bằng JDK, dùng các API có trên Java 17):

```text
integer exact = 9007199254740993
double roundtrip = 9007199254740992
new BigDecimal(0.1) = 0.1000000000000000055511151231257827021181583404541015625
valueOf(0.1) = 0.1
double sum = 0.30000000000000004
decimal sum = 0.3
round = 10.01
third = 0.3333
equals = false
compareTo = 0
truncated = 99
fraction rejected
plain = 1000
scientific = 1E+3
```

Giải thích:

- `id` được đọc chính xác từ `String`. Chuyển qua `doubleValue()` làm số `9007199254740993` thành `9007199254740992`: sai khác đúng 1 đơn vị.
- `new BigDecimal(0.1)` diễn tả chính xác giá trị **binary64** xấp xỉ `0.1`; `valueOf(0.1)` chọn chuỗi thập phân ngắn tương ứng. `new BigDecimal("0.1")` không đi qua binary64.
- Phép cộng hai `BigDecimal` tạo từ chuỗi cho `0.3`; phép cộng double cho `0.30000000000000004`.
- `setScale(2, HALF_UP)` làm tròn `10.005` thành `10.01`. `1 / 3` cần scale và rounding vì không có biểu diễn thập phân hữu hạn chính xác.
- `equals` so cả giá trị và scale, nên `1.0` khác `1.00` theo `equals`. `compareTo` so giá trị số học, trả `0`.
- `toBigInteger` cắt phần lẻ; `toBigIntegerExact` bảo vệ khỏi việc bỏ lẻ âm thầm.
- `stripTrailingZeros()` có thể làm scale âm nên `toString()` in dạng `1E+3`; `toPlainString()` in `1000`.

## 7. Scale, precision và làm tròn trong BigDecimal

### 7.1. Scale khác precision

`scale` biểu thị vị trí dấu thập phân theo hệ số 10. `precision()` biểu thị **số chữ số có nghĩa** của unscaled value. Ví dụ:

```java
BigDecimal x = new BigDecimal("12.3400");
System.out.println(x.scale());     // 4
System.out.println(x.precision()); // 6
```

Độ chính xác toán học và số chữ số hiển thị là hai vấn đề riêng: `"1.00"` và `"1.0"` bằng nhau về giá trị, nhưng scale khác nhau.

### 7.2. Chọn chính sách làm tròn một cách tường minh

`setScale(targetScale, mode)` thay đổi scale và có thể làm tròn:

```java
BigDecimal price = new BigDecimal("10.005");

System.out.println(price.setScale(2, RoundingMode.HALF_UP));  // 10.01
System.out.println(price.setScale(2, RoundingMode.HALF_EVEN)); // 10.00
```

`HALF_UP` tăng độ lớn khi gặp trường hợp đúng nửa (ví dụ số dương 10.005 ở scale 2), còn `HALF_EVEN` chọn chữ số cuối chẵn trong trường hợp đúng nửa. Chính sách nào đúng phụ thuộc quy định tính toán của hệ thống, không có một kiểu làm tròn luôn đúng cho mọi loại tiền và thuế.

Nếu yêu cầu tuyệt đối **không được làm tròn**, dùng `RoundingMode.UNNECESSARY`. Khi buộc phải bỏ một chữ số có nghĩa, phép toán sẽ ném `ArithmeticException`.

### 7.3. Phép chia không kết thúc

`new BigDecimal("1").divide(new BigDecimal("3"))` ném `ArithmeticException` vì `1/3` không có biểu diễn thập phân hữu hạn. Chỉ rõ scale + rounding, hoặc dùng `MathContext`:

```java
BigDecimal a = new BigDecimal("1");
BigDecimal b = new BigDecimal("3");

System.out.println(a.divide(b, 2, RoundingMode.HALF_UP)); // 0.33

MathContext mc = new MathContext(5, RoundingMode.HALF_EVEN);
System.out.println(a.divide(b, mc)); // 0.33333
```

`MathContext(5, ...)` giới hạn **5 chữ số có nghĩa (precision)**, không phải 5 chữ số sau dấu thập phân (scale). Nhớ `import java.math.MathContext;` khi sử dụng đoạn mã này trong một lớp riêng.

### 7.4. So sánh giá trị và khóa trong collection

`BigDecimal.equals` xét cả value lẫn scale, còn `compareTo` chỉ xét thứ tự số học:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

Vì vậy `HashSet<BigDecimal>` và `TreeSet<BigDecimal>` có thể cho kết quả khác về việc coi hai giá trị này là trùng, do quy tắc so bằng nhau khác nhau. Cần xác định chính sách chuẩn hóa scale và chính sách so sánh trước khi dùng trong map, set hoặc khóa nghiệp vụ.

## 8. Chuyển số chính xác trở lại String

| API | Kết quả / ý nghĩa |
| --- | --- |
| `bigInteger.toString()` | Văn bản số nguyên thập phân chính xác |
| `bigInteger.toString(16)` | Văn bản ở hệ 16, không làm mất giá trị |
| `bigDecimal.toString()` | Dạng chuẩn của đối tượng, có thể chứa ký pháp khoa học `E` |
| `bigDecimal.toPlainString()` | Dạng thập phân không dùng số mũ |
| `bigDecimal.toEngineeringString()` | Có thể dùng lũy thừa của 10 với số mũ bội của 3 |
| `bigDecimal.stripTrailingZeros()` | Loại số `0` thừa ở cuối; có thể thay đổi scale và cách `toString()` hiển thị |

Ví dụ:

```java
BigDecimal raw = new BigDecimal("1000.00");

System.out.println(raw.toPlainString()); // 1000.00
System.out.println(raw.stripTrailingZeros().toString()); // 1E+3
System.out.println(raw.stripTrailingZeros().toPlainString()); // 1000
```

Nếu dữ liệu đầu vào yêu cầu **định dạng hiển thị cố định hai chữ số phần lẻ**, có thể dùng `setScale(2, roundingMode)` trước khi xuất, nhưng chỉ sau khi xác định quy tắc làm tròn. Không đồng nhất việc giữ **giá trị số học** với việc giữ **nguyên văn chuỗi đầu vào** (dấu `+`, chữ số `0` dẫn đầu, ký pháp `E`, dấu phân nhóm). Cần lưu chuỗi gốc nếu những thông tin đó là bắt buộc.

## 9. Các luồng chuyển đổi nên dùng và nên tránh

### 9.1. Đúng: String → BigInteger/BigDecimal → phép toán chính xác

```text
"9007199254740993" --BigInteger(String)--> 9007199254740993
"0.1" --BigDecimal(String)--> decimal 0.1
"0.2" --BigDecimal(String)--> decimal 0.2
decimal 0.1 + decimal 0.2 --> decimal 0.3
```

Không có bước ép qua `float` hoặc `double`. Dùng `BigDecimal` cho số tiền cần đơn vị thập phân, `BigInteger` cho số nguyên lớn không có phần lẻ.

### 9.2. Có thể mất mát: String → double → BigDecimal

```text
"9007199254740993"
    -> Double.parseDouble(...)
    -> 9007199254740992 (đã làm tròn)
    -> BigDecimal.valueOf(...) = 9007199254740992
```

Ngay cả khi sau đó chuyển thành `BigInteger`, số ban đầu vẫn đã mất. Nếu đã có `double` từ hệ thống ngoài, phải chấp nhận và mô tả độ chính xác đầu vào của hệ thống đó; `BigDecimal` không “sửa” được lịch sử tính toán.

### 9.3. Có thể mất mát: BigDecimal → BigInteger, long hoặc double

- `toBigInteger()` bỏ phần lẻ.
- `longValue()` có thể cắt phần lẻ hoặc làm mất bit.
- `doubleValue()` có thể làm tròn, tràn thành Infinity, hoặc mất giá trị rất nhỏ.
- Dùng `toBigIntegerExact()` / `longValueExact()` khi cần từ chối đầu vào không bảo toàn được.

### 9.4. Khi bắt buộc làm việc với float/double

Một số thư viện khoa học và API legacy nhận `double`; khi chuyển qua, hãy kiểm tra phạm vi, hữu hạn (`Double.isFinite(value)`) và độ chính xác chấp nhận được. `BigDecimal.valueOf(Double.NaN)` / `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` không thể tạo đối tượng BigDecimal hữu hạn và ném `NumberFormatException`.

Nếu tài chính yêu cầu chính xác tuyệt đối theo đơn vị nhỏ nhất, cân nhắc mô hình **số nguyên đơn vị nhỏ** (`BigInteger` hoặc `long` đủ phạm vi) hoặc `BigDecimal` với scale và rounding được quy định thống nhất.

## 10. Sai lầm thường gặp

1. **Parse sang double trước rồi tạo BigDecimal.** `new BigDecimal(Double.parseDouble(text))` có thể chứa giá trị gần đúng nhị phân; `BigDecimal.valueOf(Double.parseDouble(text))` cũng không khôi phục được tất cả chữ số nếu double đã làm tròn. Dùng `new BigDecimal(text)`.
2. **Dùng BigDecimal.valueOf(0.1) rồi kết luận phép cộng double là chính xác.** `valueOf` chỉ chuyển đổi biểu diễn của giá trị double đã có; `valueOf(0.1 + 0.2)` vẫn ra `0.30000000000000004`.
3. **Dùng double cho ID/số đếm lớn.** Khi số nguyên vượt ngưỡng biểu diễn liên tiếp chính xác, hai giá trị khác nhau có thể thành cùng một double. Giữ dạng `String` hoặc `BigInteger`.
4. **Dùng BigInteger để biểu diễn phần lẻ.** `new BigInteger("12.34")` gây `NumberFormatException`. Dùng `BigDecimal` nếu cần phần lẻ.
5. **Tin rằng `BigInteger.longValue()` luôn chính xác.** Nếu tràn phạm vi, phép đổi có thể mất bit. Dùng `longValueExact()` khi mất mát là lỗi.
6. **Tin rằng `BigDecimal.toBigInteger()` làm tròn.** Nó cắt phần lẻ hướng về 0. Chọn `setScale(0, mode)` trước, hoặc dùng `toBigIntegerExact()`.
7. **Gọi `divide` mà không xác định quy tắc chia.** Với phân số vô hạn như `1/3`, mặc định có thể ném `ArithmeticException`. Chỉ rõ `scale`/`RoundingMode` hoặc `MathContext`.
8. **Nhầm `equals` và `compareTo`.** `1.0` và `1.00` có cùng giá trị số học nhưng `equals` trả false. Cẩn thận khi dùng làm khóa collection.
9. **Nhầm precision với scale.** `MathContext(5)` không có nghĩa giữ 5 chữ số thập phân; đó là 5 chữ số có nghĩa.
10. **Mong BigDecimal giữ nguyên định dạng đầu vào.** `"0001.2300"` có thể giữ scale thập phân nhưng không giữ số `0` dẫn đầu. Lưu riêng chuỗi gốc nếu cần khôi phục ký tự.
11. **Không xét dữ liệu không hợp lệ.** Chuỗi có khoảng trắng, dấu phẩy locale, NaN hoặc số mũ sai có thể gây `NumberFormatException`. Định nghĩa cú pháp hợp lệ từ đầu.
12. **Cho rằng BigInteger/BigDecimal là “vô hạn” về bộ nhớ hay tốc độ.** Chúng vẫn tiêu tốn tài nguyên theo độ dài số và độ phức tạp phép toán; kiểm soát kích thước input, nhất là khi nhận dữ liệu không tin cậy.

## 11. Bài tập tự kiểm tra

**Bài 1 — Giữ một số nguyên lớn từ chuỗi.**

Đầu vào `"9007199254740993"` cần cộng thêm `1` mà không mất chữ số. Viết:

```java
BigInteger result = new BigInteger("9007199254740993")
        .add(BigInteger.ONE);
System.out.println(result); // 9007199254740994
```

Không ép qua `double` ở bất kỳ bước nào.

**Bài 2 — Tính tổng số tiền thập phân.**

Hai chuỗi `"0.10"` và `"0.20"`, kết quả mong muốn là `0.30`:

```java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");

BigDecimal total = a.add(b);
System.out.println(total.toPlainString()); // 0.30
```

Scale của kết quả cộng thông thường phù hợp với scale lớn nhất của hai toán hạng trong ví dụ. Nếu cần format hai chữ số sau dấu phẩy cho những đầu vào khác, đặt chính sách scale/rounding rõ ràng.

**Bài 3 — Từ chối làm mất phần lẻ.**

Đầu vào `"42.1"` cần chuyển sang số nguyên nhưng phải báo lỗi nếu có phần lẻ:

```java
BigDecimal input = new BigDecimal("42.1");
// input.toBigIntegerExact() sẽ ném ArithmeticException.
```

Không chọn `toBigInteger()` vì nó âm thầm trả `42`.

**Bài 4 — So sánh hai số tiền.**

Tại sao `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả false nhưng `compareTo` trả 0? Vì `equals` xét cả scale, trong khi `compareTo` xét giá trị số học. Chọn một tiêu chí phù hợp nghiệp vụ và giữ nhất quán.

**Bài 5 — Phát hiện vòng chuyển đổi sai.**

```java
String source = "9007199254740993";
double d = Double.parseDouble(source);
BigDecimal x = BigDecimal.valueOf(d);
```

`x` không thể bằng chính xác giá trị trong `source`: `double` đã làm tròn thành `9007199254740992`. Cách sửa là `new BigDecimal(source)` hoặc `new BigInteger(source)` nếu dữ liệu là số nguyên.

## 12. Ghi nhớ

`BigInteger` dành cho **số nguyên chính xác vượt phạm vi kiểu nguyên cơ bản**; `BigDecimal` dành cho **giá trị thập phân chính xác và chính sách scale/rounding rõ ràng**. Khi nguồn là `String`, parse trực tiếp sang kiểu mong muốn. `float`/`double` có giới hạn bit, miền giá trị và có thể mất chữ số; đi qua chúng có thể khiến chuyển đổi về BigInteger/BigDecimal không thể bảo toàn dữ liệu ban đầu. Trước khi chuyển đổi có nguy cơ mất mát, hãy dùng các phép `Exact` hoặc quyết định làm tròn tường minh.

**Tài liệu chính thức:** [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html), [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).