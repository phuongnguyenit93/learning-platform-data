# Kiểm thử round-trip parse, format và cơ số trong Java

## 1. Round-trip là gì và vì sao phải kiểm thử?

Dữ liệu số thường đi qua hai hướng chuyển đổi:

```text
Giá trị số -> format/toString -> chuỗi văn bản
Chuỗi văn bản -> parse         -> giá trị số
```

**Round-trip** là phép chuyển đổi đi rồi quay về. Với một giá trị `x` và cơ chế định dạng/phân tích tương ứng, ta muốn kiểm tra:

```text
parse(format(x)) == x
```

Nhưng ký hiệu `==` ở đây phải được xác định rõ: **bằng giá trị số học**, **bằng tất cả các thuộc tính của biểu diễn** (ví dụ scale của `BigDecimal`), hay **bằng chính xác các bit** (ví dụ dấu âm của `-0.0` trong `double`)?

Một ví dụ quan trọng:

```java
BigDecimal a = new BigDecimal("1E+3");   // giá trị 1000, scale -3
BigDecimal b = new BigDecimal(a.toPlainString()); // "1000", scale 0

System.out.println(a.compareTo(b) == 0); // true: giá trị số học như nhau
System.out.println(a.equals(b));         // false: scale khác nhau
```

Như vậy, chuỗi `"1000"` đủ để phục hồi **giá trị số học** nhưng không đủ để phục hồi **scale** ban đầu của `1E+3`. Nếu hệ thống lưu trữ định dạng/độ chi tiết theo scale, bài test chỉ dùng `compareTo()` sẽ bỏ sót lỗi.

Kiểm thử round-trip đặc biệt quan trọng khi số đi qua cấu hình, file CSV/JSON, dữ liệu giao tiếp với hệ thống khác, thông điệp, format hiển thị và các cơ số 2/8/10/16/36.

## 2. Ba mức độ cần kiểm thử

| Mức round-trip | Tiêu chí | Ví dụ |
| --- | --- | --- |
| **Giữ giá trị số học** | Parse lại cùng giá trị số | `new BigDecimal("1E+3").compareTo(new BigDecimal("1000")) == 0` |
| **Giữ thuộc tính biểu diễn** | Ngoài giá trị, giữ scale, dấu 0, v.v. theo hợp đồng | `BigDecimal.equals()` kiểm tra cả giá trị và scale |
| **Giữ bit** | Mọi bit của kiểu số sau parse trùng với ban đầu | `Double.doubleToRawLongBits(a) == Double.doubleToRawLongBits(b)` |

Không phải bài toán nào cũng cần cùng mức. Giá trị hiển thị cho con người có thể chấp nhận làm tròn. Mã lưu trữ để tái dựng chính xác một đối tượng có thể cần bảo toàn bit hoặc các thuộc tính biểu diễn.

Cũng phải phân biệt **chuỗi đầu vào gốc** với **chuỗi chuẩn hóa**. Chẳng hạn `Integer.parseInt("+00042")` cho 42, nhưng `Integer.toString(42)` là `"42"`. Round-trip giá trị thành công, round-trip văn bản nguyên trạng thất bại. Nếu cần bảo toàn dấu `+` hoặc số 0 đứng đầu, lưu thêm chuỗi gốc.

## 3. Round-trip số nguyên có dấu với các cơ số

### 3.1. Integer.toString và Integer.parseInt

Với `int value` và cơ số `radix` hợp lệ trong khoảng **2 đến 36**:

```java
int value = -255;
String text = Integer.toString(value, 16); // "-ff"
int parsed = Integer.parseInt(text, 16);   // -255
```

Hợp đồng nên kiểm thử:

```java
Integer.parseInt(Integer.toString(value, radix), radix) == value
```

Cho mọi giá trị `int`, kể cả `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, khi cả format và parse sử dụng cùng cơ số 2..36. Những chữ cái đại diện cho chữ số lớn hơn 9 thường theo quy ước `a..z` hoặc `A..Z` trong lúc parse, còn `toString` tạo chữ thường.

`Long.toString(longValue, radix)` và `Long.parseLong(text, radix)` có cơ chế tương tự cho số nguyên 64 bit.

Bảng minh họa một giá trị:

| Radix | `Integer.toString(255, radix)` | `Integer.parseInt(text, radix)` |
| ---: | --- | ---: |
| 2 | `11111111` | 255 |
| 8 | `377` | 255 |
| 10 | `255` | 255 |
| 16 | `ff` | 255 |
| 36 | `73` | 255 |

`radix` là tham số khi parse; ký tự `"ff"` không thể giải mã trong cơ số 10. `Integer.parseInt("ff", 16)` cho 255 nhưng `Integer.parseInt("ff", 10)` ném `NumberFormatException`.

### 3.2. Dấu âm và dạng bit bù hai

Không nhầm:

```java
Integer.toString(-1, 16); // "-1"
Integer.toHexString(-1);   // "ffffffff"
```

`Integer.toString(value, radix)` biểu diễn **số có dấu** với dấu `-`. Ngược lại, `toHexString`, `toBinaryString`, `toOctalString` của `Integer` sử dụng dạng **không dấu của mẫu bit bù hai**. Do đó `Integer.toHexString(-1)` tạo chuỗi 8 chữ `f`.

Nếu muốn khôi phục mẫu bit từ `"ffffffff"`, dùng:

```java
int bits = Integer.parseUnsignedInt("ffffffff", 16);
// bits == -1 về cách diễn giải signed int;
// Integer.toUnsignedLong(bits) == 4294967295L
```

Không dùng `Integer.parseInt("ffffffff", 16)` vì giá trị 4.294.967.295 vượt phạm vi `int` có dấu.

### 3.3. Parse unsigned

Dùng `Integer.toUnsignedString(value)` và `Integer.parseUnsignedInt(text)` nếu dữ liệu văn bản biểu diễn số nguyên 32 bit **không dấu**:

```java
int rawBits = -1;
String unsignedText = Integer.toUnsignedString(rawBits); // "4294967295"
int restoredBits = Integer.parseUnsignedInt(unsignedText); // -1
boolean sameBits = rawBits == restoredBits; // true
```

Giá trị `-1` trong `int` cuối cùng là **mẫu bit ban đầu được phục hồi**, không phải phép parse thất bại. Tương tự, Java có `Long.toUnsignedString` và `Long.parseUnsignedLong`.

### 3.4. Tiền tố cơ số không tự được parseInt nhận

`Integer.parseInt("0xff", 16)` **không** chấp nhận tiền tố `0x` và ném `NumberFormatException`. Bản thân `parseInt` chỉ parse chuỗi chữ số hợp lệ (có thể có dấu `+`/`-` ở đầu) theo cơ số đã cho.

`Integer.decode("0xff")` có thể nhận các ký hiệu tiền tố như `0x`, `0X`, `#`; nó còn có cách hiểu số có số 0 đứng đầu theo quy ước octal. **Không đánh tráo `decode` và `parseInt` trong một giao thức dữ liệu** nếu chưa định nghĩa chuẩn input, bởi cùng `"010"` có thể mang nghĩa khác theo API.

Cơ số vượt giới hạn 2..36 và chữ số không hợp lệ đều là ca cần test. Với API `Integer.parseInt`, đầu vào quá dài/tràn phạm vi hoặc chứa dấu cách không được chấp nhận như thể đã được `trim()` tự động.

## 4. Số nguyên lớn với BigInteger

`BigInteger` không bị giới hạn bởi miền `int`/`long` có dấu. Khi dữ liệu có thể vượt `Long.MAX_VALUE`, dùng:

```java
BigInteger original = new BigInteger("123456789012345678901234567890");
String base36 = original.toString(36);
BigInteger parsed = new BigInteger(base36, 36);
boolean same = original.equals(parsed); // true
```

Các ký tự chữ số ở cơ số 36 có thể từ `0` tới `9` và `a` tới `z`. Test trên số dương, số âm, 0, và những giá trị lớn hơn phạm vi 64 bit. Khi parse, đảm bảo đối số radix đúng với format và xử lý `NumberFormatException` đối với đầu vào lỗi.

**Chú ý phạm vi:** `BigInteger.toString(radix)` và constructor `new BigInteger(text, radix)` thiết kế cho **giá trị nguyên**. Không suy từ đó rằng `BigDecimal` có thể parse trực tiếp phần thập phân trong mọi cơ số. Với phần lẻ cơ số 2/16 hay những biểu diễn số thực khác, cần một định dạng hoặc thuật toán được định nghĩa riêng; không tùy ý dùng `BigDecimal(String)` cho văn bản không phải cú pháp thập phân.

## 5. BigDecimal: bảo toàn giá trị khác bảo toàn scale

### 5.1. toString để khôi phục biểu diễn BigDecimal

`BigDecimal.toString()` có dạng biểu diễn chuẩn, có thể dùng ký pháp khoa học khi cần. Khi tạo lại bằng `new BigDecimal(text)`, nó bảo toàn **giá trị số học và scale**:

```java
BigDecimal x = new BigDecimal("123.4500");
String encoded = x.toString();        // "123.4500"
BigDecimal back = new BigDecimal(encoded);

System.out.println(x.equals(back));   // true
System.out.println(back.scale());     // 4
```

Đây là tiêu chí nghiêm ngặt hơn `compareTo() == 0`. `equals()` của `BigDecimal` phân biệt `1.0` và `1.00`, còn `compareTo()` xem chúng bằng nhau về số học.

Nên kiểm thử thêm:
- số 0 với các scale khác nhau (`"0"`, `"0.000"`);
- số âm và số rất lớn/nhỏ;
- `"1E+3"` với **scale âm**;
- số 0 tận cùng (`"123.4500"`);
- giá trị chính xác có nhiều hơn 15–17 chữ số, để chắc rằng dữ liệu không vô tình đi qua `double`.

### 5.2. toPlainString ưu tiên đọc, có thể không giữ scale âm

`BigDecimal.toPlainString()` bỏ ký pháp mũ, phù hợp trường hợp cần biểu diễn dạng thường. Nhưng với số có scale âm, round-trip qua `toPlainString()` rồi `new BigDecimal(...)` có thể đổi scale:

```java
BigDecimal original = new BigDecimal("1E+3"); // scale -3
String plain = original.toPlainString();       // "1000"
BigDecimal reparsed = new BigDecimal(plain);  // scale 0

boolean equalValue = original.compareTo(reparsed) == 0; // true
boolean equalRepresentation = original.equals(reparsed); // false
```

Nếu cần khôi phục scale một cách nghiêm ngặt, ưu tiên `toString()` (hoặc lưu riêng `unscaledValue` và `scale` theo schema rõ ràng). Nếu chỉ cần giá trị số học, `toPlainString()` có thể phù hợp.

### 5.3. setScale, stripTrailingZeros và format làm tròn

`setScale` có thể làm tròn theo `RoundingMode`; `stripTrailingZeros()` giữ nguyên giá trị số học nhưng có thể đổi scale. Vì vậy test phải nêu rõ:
- có chấp nhận thay đổi giá trị không?
- có chấp nhận thay đổi scale không?
- số chữ số lẻ do **dữ liệu nguồn** hay **quy tắc hiển thị** quyết định?

Ví dụ, định dạng `12.3456` thành `"12.35"` đã làm mất thông tin. Parse về `BigDecimal` sẽ ra 12.35, không thể tự suy ra 12.3456.

Không dùng `new BigDecimal(doubleValue)` như cách khôi phục một chuỗi thập phân nếu không hiểu sai số nhị phân của `double`. Với dữ liệu thập phân ở dạng chuỗi, thường dùng trực tiếp `new BigDecimal(text)`.

## 6. Round-trip double và float

### 6.1. Double.toString/Double.parseDouble

Với giá trị `double` hữu hạn, `Double.toString(value)` tạo dạng chuỗi thập phân đủ thông tin để `Double.parseDouble(text)` khôi phục **cùng giá trị double** (bao gồm mẫu bit của `-0.0`). Ví dụ:

```java
double value = Math.PI;
String text = Double.toString(value);
double back = Double.parseDouble(text);

boolean identicalBits =
        Double.doubleToRawLongBits(value)
        == Double.doubleToRawLongBits(back); // true
```

Các điểm biên phải test gồm `0.0`, `-0.0`, số rất nhỏ (*subnormal*), `Double.MIN_VALUE`, `Double.MAX_VALUE` và giá trị gần biên biểu diễn. Với `float` có `Float.toString()` và `Float.parseFloat()` cùng ý tưởng.

**Đừng dùng `a == b` làm phép kiểm round-trip bit cho mọi tình huống:**
- `0.0 == -0.0` là `true`, dù bit dấu khác nhau.
- `Double.NaN == Double.NaN` là `false` dù cả hai đều NaN.
- `Double.doubleToLongBits` chuẩn hóa các bit NaN thành dạng canonical; `Double.doubleToRawLongBits` giữ raw payload bit của giá trị đang kiểm tra.

`Double.toString(Double.NaN)` sinh `"NaN"` và `Double.parseDouble("NaN")` phục hồi trạng thái NaN; **không bảo đảm giữ từng bit payload** của mọi NaN có thể biểu diễn. Nếu bắt buộc round-trip chính xác **mọi mẫu bit**, gồm NaN payload, serialize kết quả từ `Double.doubleToRawLongBits(x)` theo một giao thức bit cố định rồi khôi phục bằng `Double.longBitsToDouble(bits)`.

Tương tự, `Infinity` và `-Infinity` được API `Double.toString/parseDouble` hiểu, nhưng không phải mọi định dạng dữ liệu trao đổi (chẳng hạn JSON chuẩn nghiêm ngặt) đều cho phép hai giá trị không hữu hạn này. Phải phân biệt hợp đồng của **Java parser** và hợp đồng của **định dạng lưu trữ**.

### 6.2. Format với ít chữ số có thể phá round-trip

`String.format(Locale.US, "%.2f", Math.PI)` trả chuỗi `"3.14"`. Khi `Double.parseDouble`, giá trị sau parse là double gần 3.14, khác bit với `Math.PI`.

```java
String shown = String.format(Locale.US, "%.2f", Math.PI);
// shown = "3.14"; đây là format hiển thị đã làm tròn
double reconstructed = Double.parseDouble(shown);
// reconstructed không có cùng bit với Math.PI
```

Vì vậy:
- dùng `Double.toString()` cho hành trình văn bản cần giữ cùng giá trị double;
- dùng `String.format`/`DecimalFormat` với precision cụ thể cho **hiển thị**, hiểu rằng kết quả thường mất thông tin;
- không tự suy rằng 2 chữ số thập phân đủ cho bất kỳ `double` nào.

Các trường hợp như `0.1 + 0.2` còn chịu đặc tính nhị phân của `double`. Test round-trip có thể thành công 100% nhưng điều đó **không chứng minh phép tính đầu vào chính xác theo thập phân**.

## 7. Locale, dấu phân cách và DecimalFormat

Cùng số 12345.67 có thể được hiển thị:

| Bối cảnh | Ví dụ văn bản | Ý nghĩa |
| --- | --- | --- |
| Dạng máy đọc, không phụ thuộc Locale | `12345.67` | Dấu chấm là dấu thập phân |
| Đức, nhóm hàng nghìn và thập phân | `12.345,67` | Dấu chấm để nhóm, dấu phẩy là thập phân |
| Định dạng làm tròn còn hai chữ số | `12,35` từ 12.3456 (theo mẫu và chế độ làm tròn) | Đã bỏ thông tin chính xác |

Để parse chuỗi theo quy tắc địa phương, cần **cùng quy ước Locale, mẫu format và quy tắc làm tròn**. Ví dụ với `DecimalFormat`:

```java
DecimalFormat german = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
german.setParseBigDecimal(true);

BigDecimal source = new BigDecimal("12345.67");
String text = german.format(source);   // "12.345,67"

ParsePosition position = new ParsePosition(0);
Number parsed = german.parse(text, position);
// parsed instanceof BigDecimal == true
// position.getIndex() == text.length()
```

Đây là **đoạn minh họa**: cần import `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.text.ParsePosition`, `java.math.BigDecimal` và `java.util.Locale`, đặt mã trong phương thức/lớp.

Chú ý:
1. `DecimalFormat` phục vụ format/parse theo mẫu. Nếu mẫu **làm tròn hoặc cắt thông tin**, parse lại không thể khôi phục giá trị gốc.
2. `setParseBigDecimal(true)` giúp parse thành `BigDecimal` thay vì tự nhận kết quả số bằng các kiểu như `Long` hoặc `Double`; điều này quan trọng khi dữ liệu thập phân yêu cầu tính chính xác.
3. `NumberFormat.parse`/`DecimalFormat.parse` có thể parse được **phần đầu** của chuỗi và dừng trước ký tự không hợp lệ. Vì thế không đủ để thấy return không null: phải kiểm tra **đã tiêu thụ toàn bộ chuỗi**, ví dụ `ParsePosition.getIndex() == text.length()`, và kiểm tra lỗi parse nếu có.
4. Không mặc định kết quả Locale này được `Double.parseDouble` hay `new BigDecimal(text)` hiểu; các API parse số chuẩn đó sử dụng cú pháp riêng, không phải parser cho mọi Locale.
5. Nếu kiểm thử một định dạng có dấu nhóm hàng nghìn, dấu tiền tệ, chữ số phi Latin hoặc dấu âm đặc thù, hãy định nghĩa schema đầu vào và toàn bộ tiêu chí chấp nhận. Một parser hỗ trợ ký tự phân nhóm không nhất thiết kiểm tra **mọi quy tắc phân nhóm chặt chẽ**; có thể cần validate pattern riêng.

**Lưu ý cho số tiền:** Một số văn bản hiển thị có số chữ số thập phân cố định, ví dụ `"12.30"`, trong khi số gốc `BigDecimal("12.3")` có scale 1. Round-trip của **giá trị số** có thể thành công nhưng `equals()` có thể thất bại nếu formatter chủ động thêm số 0 tận cùng. Hãy xác định muốn kiểm tra giá trị hay scale.

## 8. Chương trình Java 17 chạy độc lập: kiểm thử nhiều kiểu round-trip

Tạo tệp **`NumberRoundTripDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberRoundTripDemo {
    static void require(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        int[] sample = {Integer.MIN_VALUE, -255, -1, 0, 1, 255, Integer.MAX_VALUE};
        int[] bases = {2, 8, 10, 16, 36};
        int checked = 0;
        for (int base : bases) {
            for (int number : sample) {
                String text = Integer.toString(number, base);
                require(Integer.parseInt(text, base) == number, "int base=" + base);
                checked++;
            }
        }
        System.out.println("integerCases=" + checked);
        System.out.println("minus255Hex=" + Integer.toString(-255, 16));

        String unsigned = Integer.toUnsignedString(-1);
        int u = Integer.parseUnsignedInt(unsigned);
        require(u == -1, "unsigned bits");
        System.out.println("unsignedText=" + unsigned + ",signedBits=" + u);

        BigInteger big = new BigInteger("123456789012345678901234567890");
        String base36 = big.toString(36);
        require(new BigInteger(base36, 36).equals(big), "BigInteger");
        System.out.println("bigBase36=" + base36);

        BigDecimal amount = new BigDecimal("123.4500");
        BigDecimal restored = new BigDecimal(amount.toString());
        System.out.println("decimalEquals=" + amount.equals(restored)
                + ",scale=" + restored.scale());

        BigDecimal exponential = new BigDecimal("1E+3");
        BigDecimal plainBack = new BigDecimal(exponential.toPlainString());
        System.out.println("plainValueEqual=" + (exponential.compareTo(plainBack) == 0)
                + ",plainEquals=" + exponential.equals(plainBack)
                + ",scales=" + exponential.scale() + "," + plainBack.scale());

        double[] values = {0.0, -0.0, 0.1, Math.PI,
                Double.MIN_VALUE, Double.MAX_VALUE,
                Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY};
        int doubleCount = 0;
        for (double original : values) {
            double back = Double.parseDouble(Double.toString(original));
            require(Double.doubleToRawLongBits(original)
                    == Double.doubleToRawLongBits(back), "double bits");
            doubleCount++;
        }
        System.out.println("doubleBitCases=" + doubleCount);
        String roundedPi = String.format(Locale.US, "%.2f", Math.PI);
        System.out.println("piText=" + roundedPi
                + ",bitwiseEqual=" + (Double.doubleToRawLongBits(Math.PI)
                    == Double.doubleToRawLongBits(Double.parseDouble(roundedPi))));

        DecimalFormat german = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.GERMANY));
        german.setParseBigDecimal(true);
        BigDecimal localizedValue = new BigDecimal("12345.67");
        String localized = german.format(localizedValue);
        ParsePosition position = new ParsePosition(0);
        Number parsed = german.parse(localized, position);
        require(parsed instanceof BigDecimal, "localized parse type");
        require(position.getIndex() == localized.length(), "complete locale parse");
        require(((BigDecimal) parsed).compareTo(localizedValue) == 0,
                "localized number value");
        System.out.println("germanText=" + localized
                + ",parsed=" + parsed + ",fullyConsumed=true");

        ParsePosition trailing = new ParsePosition(0);
        german.parse(localized + "X", trailing);
        System.out.println("trailingJunkDetected="
                + (trailing.getIndex() != (localized + "X").length()));

        try {
            Integer.parseInt("0xff", 16);
            throw new AssertionError("expected parse failure");
        } catch (NumberFormatException expected) {
            System.out.println("prefixedHexRejected=true");
        }
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac NumberRoundTripDemo.java
java NumberRoundTripDemo
```

Kết quả thực tế, đã biên dịch với `javac --release 17` và thực thi:

```text
integerCases=35
minus255Hex=-ff
unsignedText=4294967295,signedBits=-1
bigBase36=byw97um9s91dlz68tsi
decimalEquals=true,scale=4
plainValueEqual=true,plainEquals=false,scales=-3,0
doubleBitCases=8
piText=3.14,bitwiseEqual=false
germanText=12.345,67,parsed=12345.67,fullyConsumed=true
trailingJunkDetected=true
prefixedHexRejected=true
```

Giải thích bằng chứng:
- **35 ca số nguyên** = 7 giá trị biên/điển hình × 5 cơ số. Mọi ca đều được parse về `int` ban đầu.
- **Unsigned**: chuỗi `4294967295` giữ bit 32 bit của `-1`, không phải trả về `long`.
- **BigInteger**: số vượt xa `long` đã được chuyển qua cơ số 36 và khôi phục nguyên vẹn.
- **BigDecimal**: `toString()` giữ scale 4, nhưng `toPlainString()` với scale âm mất đặc tính scale.
- **double**: tám trường hợp gồm `-0.0`, số cực nhỏ/cực lớn, hai vô cực đều giữ raw bits khi dùng `toString/parseDouble`. Giá trị NaN payload không nằm trong bộ tám này.
- **Format hai chữ số**: `Math.PI` biến thành văn bản `3.14`, nên parse không giữ bit cũ.
- **Locale Đức**: dấu phân tách được tạo theo Locale và parser tiêu thụ hết chuỗi hợp lệ; hậu tố `X` được phát hiện nhờ kiểm tra vị trí parse.
- **Tiền tố hex**: `parseInt("0xff", 16)` bị từ chối đúng như hợp đồng.

## 9. Thiết kế test đủ mạnh cho parse/format

### 9.1. Tổ hợp ca hợp lệ

Với số nguyên:
- 0, 1, -1;
- min/max của kiểu (`Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, `Long.MAX_VALUE`);
- giá trị thường, số âm, lũy thừa của cơ số, số ngay trước/sau mốc (ví dụ 15, 16, 17 ở radix 16);
- cơ số 2, 8, 10, 16, 36, và có thể kiểm tra mọi cơ số từ 2 tới 36;
- định dạng ký tự viết hoa/viết thường, dấu `+`/`-` và số 0 đứng đầu nếu hợp đồng parser cho phép.

Với `BigDecimal`:
- số 0 với nhiều scale;
- có số 0 tận cùng;
- số rất lớn và rất nhỏ;
- scale âm và dạng mũ;
- phép format giữ nguyên giá trị nhưng thay scale;
- số sau làm tròn có thể khác giá trị ban đầu.

Với `double` và `float`:
- +0 và -0;
- số cực trị và subnormal;
- các giá trị số bình thường và gần điểm làm tròn;
- NaN và vô cực theo **quy định riêng** của schema;
- các mẫu bit sinh ngẫu nhiên để khảo sát nhiều trường hợp, tách riêng NaN payload.

### 9.2. Ca input không hợp lệ

Các test chỉ kiểm tra “happy path” dễ bỏ sót lỗi parse. Bổ sung:
- chuỗi rỗng, toàn dấu cách, thừa dấu `+`/`-`;
- chữ số không thuộc cơ số (ví dụ `"2"` ở radix 2, `"g"` ở radix 16);
- radix nhỏ hơn 2 hoặc lớn hơn 36;
- số lớn vượt phạm vi `int` hoặc `long`;
- tiền tố `0x` đưa nhầm cho `parseInt`;
- dấu phân cách nhóm hàng nghìn với Locale không phù hợp;
- chuỗi hợp lệ nhưng có hậu tố rác;
- chuỗi có dấu âm nhưng parser unsigned không hỗ trợ theo hợp đồng.

Đối với parser chuỗi thuần như `Integer.parseInt`, kiểm tra `NumberFormatException`. Đối với `DecimalFormat.parse`/`NumberFormat.parse`, kiểm tra đồng thời **kiểu số trả về**, **lỗi parse**, **vị trí đã tiêu thụ** và **quy tắc làm tròn**, vì có tình huống parser dừng ở phần đầu mà không báo lỗi theo cách chương trình mong muốn.

### 9.3. Thuộc tính cần được kiểm thử

Một số *property* hữu ích:

```text
Signed radix:
parseInt(toString(n, r), r) == n, với mọi n và 2 <= r <= 36.

BigInteger:
new BigInteger(n.toString(r), r).equals(n).

BigDecimal representation:
new BigDecimal(x.toString()).equals(x).

BigDecimal numeric value, khi dùng format có chủ đích:
parsed.compareTo(x) == 0 (nếu format không làm tròn).

Double finite:
rawBits(parseDouble(Double.toString(x))) == rawBits(x).

Localized format:
parser đúng Locale phải parse hết chuỗi;
nếu định dạng không làm mất thông tin, so sánh kết quả theo mục tiêu.
```

Đây là các **thuộc tính tham chiếu**, không phải đoạn code Java độc lập. Với generator dữ liệu ngẫu nhiên, hãy ghi lại *seed* để tái hiện ca thất bại, có giới hạn thời gian và chụp cả giá trị đầu vào, chuỗi trung gian, radix/Locale khi assertion sai.

## 10. Kiểm thử theo cơ số và tính nhất quán giữa hệ thống

**Cơ số là một phần của định dạng.** Chuỗi `"10"` biểu diễn 2 trong radix 2, 8 trong radix 8, 10 trong radix 10, 16 trong radix 16. Nếu bên gửi và nhận không trao đổi radix, round-trip có thể parse **thành công về mặt cú pháp nhưng sai giá trị**.

Với giao thức lưu trữ, nên quy định rõ:
1. kiểu giá trị và miền (signed/unsigned, số nguyên/số thực);
2. radix, cách ghi dấu và có cho phép tiền tố hay không;
3. bảng ký tự chữ số/casing cho radix lớn hơn 10;
4. có cho phép số 0 đứng đầu, ký tự khoảng trắng, dấu phân tách hay không;
5. Locale, dấu nhóm, dấu thập phân khi cần hiển thị;
6. định nghĩa round-trip: đúng số, đúng scale, đúng raw bits hay đúng chuỗi;
7. chính sách lỗi: từ chối đầu vào không hợp lệ, không âm thầm đổi radix hoặc cắt dữ liệu.

Ví dụ gửi `"ff"` không kèm radix và phía nhận dùng `Integer.parseInt(text)` (mặc định thập phân) sẽ thất bại; nhưng gửi `"10"` mà không kèm radix nguy hiểm hơn vì parser có thể trả một **giá trị khác mà không ném lỗi**.

## 11. Những lỗi phổ biến và cách phòng tránh

1. **Kiểm thử `Integer.toString(n)` rồi parse bằng radix 16.** Format và parse không cùng radix. Luôn truyền radix nhất quán ở hai phía.
2. **Nhầm `toHexString(-1)` với `Integer.toString(-1,16)`.** Một bên biểu diễn bit không dấu `ffffffff`, một bên biểu diễn số có dấu `-1`.
3. **Giả định `Integer.parseInt("0xff",16)` hiểu tiền tố.** Không: phải xử lý tiền tố theo giao thức hoặc dùng API decode phù hợp.
4. **Chỉ dùng `BigDecimal.compareTo()` khi cần giữ scale.** Giá trị bằng nhau có thể có scale khác nhau; sử dụng `equals()` nếu cần tính đầy đủ của biểu diễn.
5. **Dùng `toPlainString()` để serialize `BigDecimal` rồi muốn giữ scale âm.** Nó có thể biến `1E+3` thành `1000` và làm mất scale -3. Dùng `toString()` hoặc lưu riêng scale.
6. **Dùng `%.2f` hay `DecimalFormat` làm phương án lưu trữ lossless.** Format hiển thị có thể làm tròn hoặc đổi scale; lưu dữ liệu gốc ở định dạng đúng mức cần bảo toàn.
7. **Đo double bằng `==` rồi bỏ qua -0.0/NaN.** So sánh bit theo yêu cầu; xử lý NaN payload riêng nếu phải giữ raw bits.
8. **Cho rằng Locale Đức hoặc Việt Nam luôn dùng dấu chấm thập phân.** Dấu thập phân/nhóm phụ thuộc Locale và định dạng. Xác định rõ Locale ở cả encode và decode.
9. **Parse cục bộ được đoạn đầu rồi coi như thành công.** Với `DecimalFormat`, xác nhận `ParsePosition.getIndex() == input.length()`.
10. **Không test overflow và input sai.** Round-trip trên các số nhỏ không chứng minh parser xử lý ranh giới kiểu hoặc radix bất hợp lệ.
11. **Nhầm độ chính xác double với khả năng round-trip.** Có thể serialize/parse chính xác một *giá trị double vốn đã xấp xỉ*, nhưng nó vẫn khác số thập phân lý tưởng.
12. **So sánh văn bản chuẩn hóa với chuỗi nhập ban đầu.** Các biểu diễn như `"0007"` và `"7"` có cùng giá trị. Nếu phải bảo toàn văn bản gốc, lưu văn bản gốc.

## 12. Bài tập tự kiểm tra

**Bài 1.** `Integer.toString(31,16)` trả gì, và parse lại bằng gì?  
**Đáp án:** chuỗi `"1f"`; `Integer.parseInt("1f",16)` trả 31.

**Bài 2.** Tại sao `Integer.parseInt(Integer.toHexString(-1),16)` thất bại?  
**Đáp án:** `toHexString(-1)` trả `"ffffffff"` biểu diễn bit không dấu, giá trị vượt phạm vi signed `int`. Dùng `Integer.parseUnsignedInt("ffffffff",16)` để phục hồi cùng mẫu bit.

**Bài 3.** `new BigDecimal("5.00").toString()` parse lại có cùng scale không?  
**Đáp án:** có. Tạo lại bằng `new BigDecimal("5.00")` giữ scale 2, nên `equals()` trả true.

**Bài 4.** Nếu `BigDecimal("1E+3")` được format bằng `toPlainString()` rồi parse lại, `equals()` ra sao?  
**Đáp án:** false vì scale đổi từ -3 sang 0; `compareTo() == 0` vẫn true.

**Bài 5.** `String.format(Locale.US, "%.2f", Math.PI)` có tạo chuỗi có thể khôi phục đúng mọi bit của π dưới dạng double không?  
**Đáp án:** không. Chuỗi `"3.14"` đã làm tròn và thiếu thông tin.

**Bài 6.** Parser Locale đã trả một số khi nhập `"12.345,67X"`. Có nên coi đây là thành công không?  
**Đáp án:** không, nếu schema yêu cầu toàn bộ input hợp lệ. Dùng `ParsePosition` để kiểm tra parser đã tiêu thụ hết văn bản.

**Bài 7.** Vì sao chuỗi `"10"` có thể nguy hiểm hơn `"ff"` khi bên gửi và nhận không thống nhất radix?  
**Đáp án:** `"10"` là cú pháp hợp lệ trong nhiều radix nhưng mang giá trị khác, có thể sai âm thầm; `"ff"` lại bị parser thập phân từ chối.

## 13. Kết luận

- **Round-trip phải định nghĩa rõ mục tiêu:** bảo toàn số học, biểu diễn như scale, bit số thực, hay chuỗi nguyên trạng.
- Với số nguyên, dùng cặp `toString(value, radix)` và `parseInt(text, radix)`/`parseLong(text, radix)` đúng phạm vi 2..36; phân biệt signed với unsigned và ký pháp bù hai.
- Với số nguyên lớn, dùng `BigInteger`; với `BigDecimal` cần giữ scale, dùng `toString()` và `new BigDecimal(text)` để round-trip theo `equals()`.
- Với `double`/`float`, dùng `toString/parseDouble` hoặc `toString/parseFloat` để giữ lại giá trị floating-point. Nếu phải bảo toàn *raw NaN payload*, cần định dạng bit chuyên biệt.
- Với Locale/format hiển thị, hãy kiểm tra khả năng làm tròn, kiểu parse, dấu phân cách và tiêu thụ toàn bộ đầu vào.
- Một bộ kiểm thử đáng tin phải bao gồm trường hợp biên, cơ số, chuỗi không hợp lệ, overflow và phép so sánh phù hợp với hợp đồng dữ liệu.

Tài liệu tra cứu chính thức (Java SE 17):
- [`Integer` — toString, parseInt, unsigned](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html)
- [`Long`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html)
- [`BigInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [`Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)
- [`DecimalFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [`ParsePosition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
