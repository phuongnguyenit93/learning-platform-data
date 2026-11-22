# Định dạng BigInteger, BigDecimal và giới hạn chuyển đổi qua double

## 1. Tại sao định dạng số lớn cần chú ý đến kiểu dữ liệu?

Ứng dụng Java thường cần hiển thị những con số vượt quá phạm vi `long` hoặc những giá trị thập phân đòi hỏi độ chính xác cao. Ví dụ:

- Một mã định danh dạng số có giá trị `9007199254740993`.
- Một phép tính số học có kết quả `12345678901234567890.123456789`.
- Một khoản tiền `1.005` cần làm tròn theo quy tắc kinh doanh.
- Cùng một giá trị nhưng hiển thị theo quy ước `en-US` hoặc `de-DE` với dấu nhóm nghìn, dấu thập phân khác nhau.

Java cung cấp `BigInteger` và `BigDecimal` để **lưu trữ và tính toán chính xác**, còn `NumberFormat` và `DecimalFormat` để **trình bày số theo locale**. Lỗi thường gặp là chuyển giá trị sang `double` trước khi định dạng:

```java
BigInteger value = new BigInteger("9007199254740993");
double converted = value.doubleValue(); // Mất 1 đơn vị.
```

`double` chỉ có 53 bit độ chính xác của significand (kể cả bit ẩn); không thể biểu diễn chính xác mọi số nguyên lớn và phần lớn số thập phân hữu hạn theo hệ cơ số 10. Nếu một bước định dạng dựa trên giá trị `double` đã bị làm tròn, thay đổi `Locale` hay thêm chữ số thập phân **không khôi phục được dữ liệu đã mất**.

Mục tiêu của bài: dùng đúng đường định dạng `BigInteger`/`BigDecimal` mà không chuyển qua `double`, kiểm soát số chữ số và cách làm tròn, phân biệt dữ liệu gốc với chuỗi hiển thị, parse giá trị theo locale và nhận diện các giới hạn thực tế của formatter.

## 2. Ba kiểu số và độ chính xác khác nhau

| Kiểu | Đặc điểm | Điểm phải lưu ý |
| --- | --- | --- |
| `BigInteger` | Số nguyên có độ lớn tùy ý, chính xác | Không có phần thập phân; chuyển qua `long`/`double` có thể mất thông tin |
| `BigDecimal` | Số thập phân chính xác dựa trên unscaled integer và scale | Không tự giới hạn số chữ số; cần quy tắc làm tròn và scale phù hợp nghiệp vụ |
| `double` | Số thực nhị phân IEEE 754, độ chính xác hữu hạn | Thường khoảng 15–17 chữ số thập phân có nghĩa; không biểu diễn chính xác đa số phân số thập phân |

### 2.1. BigInteger

`java.math.BigInteger` biểu diễn số nguyên có độ lớn tùy ý, giới hạn chủ yếu bởi tài nguyên hệ thống và giới hạn triển khai. Nó lý tưởng cho số nguyên lớn cần giữ chính xác; `new BigInteger(String)` đọc giá trị từ chuỗi mà không thông qua `double`.

```java
BigInteger exact = new BigInteger("9007199254740993");
System.out.println(exact);                    // 9007199254740993
System.out.println(exact.doubleValue());      // 9.007199254740992E15
```

Con số `9007199254740993 = 2^53 + 1` không thể biểu diễn chính xác dưới dạng `double`. Khi đổi sang `double` theo làm tròn IEEE 754, giá trị trở thành `9007199254740992`. Các số nguyên liên tiếp từ `-2^53` đến `2^53` có thể được biểu diễn chính xác; vượt khoảng đó **không phải mọi số nguyên** còn biểu diễn được (một số bội của bước biểu diễn vẫn có thể chính xác).

### 2.2. BigDecimal

`java.math.BigDecimal` lưu số ở dạng:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ `new BigDecimal("123.4500")` có giá trị số học 123.4500, unscaled value là 1234500 và scale là 4. Hai giá trị có thể bằng nhau về số học nhưng khác scale:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

Sự khác nhau này quan trọng khi kiểm soát cách biểu diễn như số chữ số sau dấu thập phân. `BigDecimal.toPlainString()` hiển thị dạng thập phân thông thường mà không cần locale; `DecimalFormat` có thể thêm dấu phân tách và lựa chọn số chữ số khi hiển thị.

**Tạo từ chuỗi khi cần chính xác:**

```java
BigDecimal precise = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
```

- `precise` là giá trị thập phân chính xác `0.1`.
- `fromDouble` nhận giá trị nhị phân thực tế của literal `0.1` và tạo biểu diễn thập phân chính xác của **giá trị double ấy**, nên không bằng `0.1` về số học.
- `BigDecimal.valueOf(0.1)` dựa trên dạng biểu diễn chuỗi chuẩn của `double` (thông qua `Double.toString`), thường cho `0.1` với trường hợp này. Nó hữu ích hơn `new BigDecimal(double)` trong nhiều tình huống, nhưng **không thể khôi phục độ chính xác đã mất trước đó**: nếu một số lớn đã bị ép sang `double`, `valueOf` chỉ nhận giá trị double bị làm tròn.

## 3. Định dạng số theo Locale với NumberFormat và DecimalFormat

`NumberFormat` là API ở mức khái quát để trình bày số theo locale:

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat germany = NumberFormat.getNumberInstance(Locale.GERMANY);
```

`DecimalFormat` là lớp triển khai rất thường gặp cho hệ số thập phân, hỗ trợ pattern, dấu phân nhóm, giới hạn số chữ số và rounding mode:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
DecimalFormat formatter = new DecimalFormat("#,##0.00", symbols);
```

Ở hai dòng trên, dấu phẩy và dấu chấm trong **pattern** là ký hiệu cú pháp phi địa phương hóa; `DecimalFormatSymbols` quy định các ký tự xuất ra cho locale thực tế. Không nên tự ghép chuỗi `","`/`"."` vào số để giả lập định dạng.

Các API liên quan:

| API | Chức năng |
| --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Nhận formatter số tổng quát theo locale |
| `NumberFormat.getIntegerInstance(locale)` | Nhận formatter số nguyên; thường làm tròn phần lẻ khi định dạng |
| `NumberFormat.getCurrencyInstance(locale)` | Nhận formatter tiền tệ theo quy ước mặc định của locale |
| `DecimalFormat(pattern, symbols)` | Tạo formatter theo pattern và bộ ký hiệu |
| `setGroupingUsed(boolean)` | Bật/tắt phân nhóm chữ số |
| `setMinimumFractionDigits(int)` | Số chữ số sau dấu thập phân ít nhất |
| `setMaximumFractionDigits(int)` | Số chữ số sau dấu thập phân nhiều nhất |
| `setMinimumIntegerDigits(int)` | Số chữ số phần nguyên tối thiểu |
| `setMaximumIntegerDigits(int)` | Giới hạn phần nguyên hiển thị theo formatter |
| `setRoundingMode(RoundingMode)` | Chính sách làm tròn khi định dạng |
| `format(Object)` | Định dạng đối tượng số; `DecimalFormat` hỗ trợ `BigInteger`/`BigDecimal` |
| `DecimalFormat.setParseBigDecimal(true)` | Đọc số thập phân theo locale thành `BigDecimal` thay vì chủ yếu `Long`/`Double` |

**Điểm then chốt:** `DecimalFormat` hỗ trợ định dạng trực tiếp đối tượng `BigInteger` và `BigDecimal`, không buộc phải gọi `doubleValue()`. Khi viết:

```java
BigDecimal amount = new BigDecimal("12345678901234567890.123456789");
String display = formatter.format(amount);
```

lời gọi có thể dùng đường `format(Object)` để xử lý giá trị `BigDecimal` trực tiếp. Tránh cố chuyển sang `double` chỉ vì nghĩ formatter chỉ nhận primitive `double` hoặc `long`.

Tuy nhiên, **định dạng không có nghĩa in vô hạn chữ số**. Pattern và các mức minimum/maximum digits quyết định độ dài hiển thị; formatter có thể làm tròn hoặc cắt bớt phần hiển thị theo quy tắc của nó. “Hỗ trợ BigDecimal không mất precision do ép sang double” **không đồng nghĩa** “mặc định in mọi chữ số thập phân gốc”.

### 3.1. Cẩn thận khi ép NumberFormat sang DecimalFormat

Trong các runtime với provider định dạng mặc định của JDK, `NumberFormat.getNumberInstance(Locale.US)` thường trả một `DecimalFormat`. Nhưng API `NumberFormat` chỉ hứa đối tượng triển khai `NumberFormat`; môi trường có provider riêng có thể thay thế. Nếu cần chắc chắn có các API dành riêng cho `DecimalFormat`, tạo trực tiếp:

```java
DecimalFormat f = new DecimalFormat(
        "#,##0.000", DecimalFormatSymbols.getInstance(Locale.US)
);
```

Để chọn pattern chuẩn của một locale rồi tùy chỉnh, có thể kiểm tra kiểu trước khi cast thay vì mặc định mọi formatter đều là `DecimalFormat`.

## 4. Vì sao chuyển BigInteger sang double làm sai giá trị?

`double` là dạng floating-point nhị phân có 53 bit significand. Ở độ lớn gần `2^53`, các giá trị double liên tiếp cách nhau 2 đơn vị. Vì vậy giá trị nguyên lẻ `9007199254740993` sẽ được làm tròn thành `9007199254740992` khi chuyển đổi.

Tạo file **`BigNumberFormattingDemo.java`** — chương trình đầy đủ dùng Java 17+:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class BigNumberFormattingDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);

        BigInteger hugeInteger =
                new BigInteger("9007199254740993");
        DecimalFormat integerFormat =
                new DecimalFormat("0", us);

        System.out.println("BigInteger direct: "
                + integerFormat.format(hugeInteger));
        System.out.println("BigInteger through double: "
                + integerFormat.format(hugeInteger.doubleValue()));

        BigDecimal hugeDecimal =
                new BigDecimal("12345678901234567890.123456789");
        DecimalFormat decimalFormat =
                new DecimalFormat("0.000000000", us);
        decimalFormat.setRoundingMode(RoundingMode.HALF_EVEN);

        System.out.println("BigDecimal direct: "
                + decimalFormat.format(hugeDecimal));
        System.out.println("BigDecimal through double: "
                + decimalFormat.format(hugeDecimal.doubleValue()));

        BigDecimal amount = new BigDecimal("1.005");
        DecimalFormat twoDigits =
                new DecimalFormat("0.00", us);

        twoDigits.setRoundingMode(RoundingMode.HALF_EVEN);
        System.out.println("HALF_EVEN: "
                + twoDigits.format(amount));

        twoDigits.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("HALF_UP: "
                + twoDigits.format(amount));

        System.out.println("Original: " + amount.toPlainString());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BigNumberFormattingDemo.java
java BigNumberFormattingDemo
```

**Stdout với Java 17+ và các ký hiệu `Locale.US`:**

```text
BigInteger direct: 9007199254740993
BigInteger through double: 9007199254740992
BigDecimal direct: 12345678901234567890.123456789
BigDecimal through double: 12345678901234567000.000000000
HALF_EVEN: 1.00
HALF_UP: 1.01
Original: 1.005
```

Quan sát:

1. `DecimalFormat.format(hugeInteger)` giữ số nguyên chính xác. Chỉ việc gọi `hugeInteger.doubleValue()` mới làm giá trị đổi thành `9007199254740992`.
2. `DecimalFormat` có thể định dạng trực tiếp `BigDecimal` với 9 chữ số sau dấu thập phân. Khi ép giá trị lớn ấy qua `double`, phần nguyên và phần lẻ đều mất thông tin; thêm đuôi `.000000000` chỉ làm **đầu ra trông có 9 chữ số**, không làm dữ liệu chính xác hơn.
3. Hai cách làm tròn `HALF_EVEN` và `HALF_UP` khác nhau ở giá trị `1.005` khi hiển thị hai chữ số thập phân.
4. `amount` vẫn là `1.005` sau cả hai lời gọi `format`. Định dạng chỉ sinh ra **chuỗi mới**, không sửa đối tượng `BigDecimal` gốc.

Kết quả của ví dụ được thiết kế để không phụ thuộc dấu phân nhóm hoặc định dạng dấu thập phân của máy: formatter sử dụng `DecimalFormatSymbols` lấy theo `Locale.US` và pattern không phân nhóm.

## 5. Giới hạn của double: phải hiểu chính xác điều bị mất

### 5.1. Đối với số nguyên

Khoảng nguyên liên tiếp mà `double` có thể biểu diễn chính xác là:

\[
-2^{53} \le n \le 2^{53}
\]

Ở ngoài khoảng này, vẫn có **một số** số nguyên biểu diễn được (ví dụ số chẵn gần `2^53`), nhưng không phải mọi số. Nếu một `BigInteger` vượt khoảng ấy được chuyển thành `double`, nên coi đây là phép chuyển **có thể mất độ chính xác**, không dùng nó cho ID, khóa số, tiền hoặc dữ liệu đòi hỏi chính xác tuyệt đối.

Ngoài precision, `BigInteger.doubleValue()` cũng có thể cho `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY` khi giá trị vượt phạm vi hữu hạn của `double`. Formatter không thể tái tạo giá trị nguyên từ infinity.

### 5.2. Đối với số thập phân

Trong hệ nhị phân, những số như `0.1` không có biểu diễn hữu hạn chính xác. Để thấy rõ:

```java
System.out.println(new BigDecimal("0.1").toPlainString());
// 0.1

System.out.println(new BigDecimal(0.1).toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

Đoạn trên là **snippet** đặt trong phương thức với `import java.math.BigDecimal;`. Vấn đề không nằm ở locale, mà ở việc giá trị literal `0.1` đã là `double` trước khi tạo `BigDecimal`.

Nếu kết quả tính toán của ứng dụng cần 20–30 chữ số thập phân đúng, chuyển sang `double` ở bất kỳ bước trung gian nào đều có thể phá hỏng giả định đó. Hãy giữ các phép tính trong `BigDecimal` với `MathContext`/`RoundingMode` đã được định nghĩa, chỉ format ở ranh giới xuất dữ liệu.

### 5.3. Đừng nhầm giới hạn double và giới hạn formatter

Có ba loại giới hạn khác nhau:

| Tầng | Giới hạn / chính sách | Ví dụ |
| --- | --- | --- |
| Kiểu lưu trữ | `double` chỉ có hữu hạn bit precision | `9007199254740993` bị làm tròn qua `double` |
| Quy tắc làm tròn số học | `BigDecimal` có scale và `MathContext` tùy thao tác | `divide` có thể cần rounding mode |
| Quy tắc hiển thị | `DecimalFormat` giới hạn chữ số phần nguyên/lẻ, grouping, rounding mode | `1.005` hiển thị `1.00` hoặc `1.01` |

Khi chỉ định `setMaximumFractionDigits(2)`, bạn đang hạn chế **chuỗi hiển thị**, không trực tiếp chuyển đổi `BigDecimal` thành một đối tượng mới có scale 2. Nếu cần lưu tiền với scale cụ thể, phải dùng phép toán như `setScale(2, roundingMode)` theo chính sách nghiệp vụ.

## 6. RoundingMode khi format BigDecimal

`DecimalFormat` có thể làm tròn giá trị khi số chữ số lẻ cần hiển thị ít hơn số chữ số thực tế. Hai mode rất thường gặp:

- `RoundingMode.HALF_EVEN`: khi đúng giữa hai kết quả có thể biểu diễn, chọn kết quả có chữ số cuối là chẵn (banker's rounding).
- `RoundingMode.HALF_UP`: khi đúng giữa, làm tròn theo hướng ra xa 0.

Với dữ liệu thập phân **chính xác**:

| Giá trị | Hai số lẻ, HALF_EVEN | Hai số lẻ, HALF_UP |
| ---: | ---: | ---: |
| `1.005` | `1.00` | `1.01` |
| `1.015` | `1.02` | `1.02` |
| `2.225` | `2.22` | `2.23` |
| `-1.005` | `-1.00` | `-1.01` |

Đây là kết quả số học chính xác khi đầu vào là `BigDecimal` tạo từ chuỗi. Nếu trước đó giá trị đã qua `double`, điều kiện “đúng giữa” có thể không còn đúng như kỳ vọng.

Để cấu hình:

```java
DecimalFormat decimal = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US)
);
decimal.setRoundingMode(RoundingMode.HALF_UP);
String result = decimal.format(new BigDecimal("1.005"));
// result là "1.01"
```

Đoạn này là **snippet**, không phải một chương trình Java độc lập; cần `import java.text.DecimalFormat;`, `DecimalFormatSymbols`, `java.math.BigDecimal;`, `RoundingMode;`, và `java.util.Locale;`.

**Không sử dụng số đã được format để tính toán tiếp.** Ví dụ hai số tiền 1.005 và 1.005 nếu làm tròn mỗi dòng trước rồi cộng có thể cho kết quả khác với cộng chính xác rồi làm tròn tổng. Thứ tự làm tròn phải theo nghiệp vụ và quy định pháp lý liên quan, không do formatter ngầm quyết định.

### Giới hạn số chữ số tối thiểu và tối đa

`setMinimumFractionDigits(2)` buộc hiển thị đủ hai chữ số lẻ, có thể thêm số 0. `setMaximumFractionDigits(2)` đặt giới hạn trên hai chữ số lẻ và có thể làm tròn. Khi cả hai đều là 2, `1.2` hiển thị `1.20`, còn `1.234` hiển thị giá trị đã làm tròn với hai chữ số lẻ.

`setMaximumIntegerDigits(...)` có tác động trực tiếp tới số chữ số phần nguyên được in; đừng đặt một giới hạn tùy tiện đối với mã ID hoặc số nguyên chính xác rất lớn. Các giới hạn nội bộ áp dụng cho format `double`/`long` khác với khả năng định dạng trực tiếp `BigInteger`/`BigDecimal` của `DecimalFormat`. Để bảo toàn mọi chữ số cần hiển thị, phải kiểm tra mẫu, các giới hạn và toàn bộ giá trị thực tế.

Đặc biệt, nếu bạn cần một định dạng **tối đa chín chữ số lẻ** nhưng không bắt buộc có đủ chín số 0, có thể dùng pattern như `0.#########`. Nếu cần giữ đủ đúng chín chữ số cho một giao diện cố định, dùng `0.000000000` như demo.

## 7. Định dạng BigInteger theo ngôn ngữ/vùng

`BigInteger.toString()` cho biểu diễn số nguyên không có dấu phân nhóm theo locale. Trên giao diện người dùng, có thể dùng `NumberFormat`:

```java
BigInteger population = new BigInteger("12345678901234567890");

NumberFormat english = NumberFormat.getIntegerInstance(Locale.US);
NumberFormat german = NumberFormat.getIntegerInstance(Locale.GERMANY);

String a = english.format(population);
String b = german.format(population);
```

Đây là **snippet**. Với dữ liệu locale chuẩn, hai formatter có thể dùng dấu phân nhóm khác nhau, ví dụ dấu phẩy tại `en-US`, dấu chấm tại `de-DE`. Tuy nhiên, việc định dạng tùy thuộc dữ liệu locale và provider của JDK. Không hardcode ví dụ output từng vùng khi không cố định môi trường chạy.

**Cần chú ý:** `NumberFormat.getIntegerInstance(...)` thường cấu hình định dạng số nguyên. Nếu đầu vào là `BigDecimal` có phần lẻ, formatter này có thể **làm tròn phần lẻ**; nó không phải phương thức ép kiểu `toBigIntegerExact()` và không chứng minh giá trị ban đầu là số nguyên. Nếu cần bảo đảm dữ liệu không có phần lẻ, hãy kiểm tra bằng `toBigIntegerExact()` trước khi định dạng hoặc so sánh phần lẻ một cách rõ ràng.

Khi formatter mặc định là `DecimalFormat` của JDK, nó xử lý trực tiếp `BigInteger`. Nếu dùng một provider `NumberFormat` tùy chỉnh, cần kiểm tra hợp đồng của implementation; không nên suy ra mọi implementation đều hỗ trợ mọi đường định dạng độ chính xác tùy ý.

## 8. Định dạng BigDecimal theo locale mà vẫn giữ nghiệp vụ

Đối với số thập phân:

```java
BigDecimal value = new BigDecimal("12345.6789");

NumberFormat localeNumber =
        NumberFormat.getNumberInstance(Locale.GERMANY);
localeNumber.setMinimumFractionDigits(4);
localeNumber.setMaximumFractionDigits(4);

String formatted = localeNumber.format(value);
```

Đoạn là **snippet**; các cài đặt phần lẻ thể hiện mong muốn hiển thị bốn chữ số, nhưng việc hiển thị thực tế (separator, grouping) phụ thuộc locale và implementation. Nếu đã phải chọn format chi tiết, dùng `DecimalFormat` và `DecimalFormatSymbols` tường minh.

### Khi định dạng tiền

`NumberFormat.getCurrencyInstance(locale)` chọn **cách hiển thị tiền tệ theo vùng**, không quyết định tiền tệ của giao dịch. Ví dụ đơn hàng bằng USD phục vụ người dùng ở Đức thì locale có thể là `Locale.GERMANY` nhưng currency vẫn là `USD`.

```java
NumberFormat money = NumberFormat.getCurrencyInstance(Locale.GERMANY);
money.setCurrency(Currency.getInstance("USD"));
String label = money.format(new BigDecimal("1234.50"));
```

Đoạn này minh họa việc định dạng trực tiếp `BigDecimal` mà **không gọi `doubleValue()`**. Kiểu hiển thị mã tiền, vị trí ký hiệu, dấu phân nhóm và chữ số lẻ do formatter/currency quyết định. Một số quy định kế toán, đơn vị tiền hay nghiệp vụ thanh toán có chính sách làm tròn riêng: cần thiết lập rõ thay vì chỉ tin vào mặc định.

Lưu ý việc gọi `setCurrency` không phải trong mọi implementation đều tự thay đổi tất cả giới hạn fraction digits đã thiết lập trước đó; hãy kiểm tra `getMinimumFractionDigits()`, `getMaximumFractionDigits()` và rounding mode nếu nghiệp vụ yêu cầu đúng số chữ số.

## 9. Parse số theo locale: tránh mất precision khi đọc đầu vào

Từ chuỗi hiển thị, `NumberFormat.parse(...)` thường trả `Long` hoặc `Double` tùy giá trị và implementation. Nếu cần giữ phần thập phân chính xác trong ứng dụng tài chính, một `DecimalFormat` có thể được cấu hình:

```java
DecimalFormat parser = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
parser.setParseBigDecimal(true);
```

Khi đó `parse` trả về `BigDecimal` cho giá trị hữu hạn thông thường, thay vì buộc đi qua `double`. Tuy nhiên, vì có thể có provider khác, nên kiểm tra kiểu formatter trước khi cast hoặc tạo một `DecimalFormat` tường minh với `DecimalFormatSymbols`.

**Để tránh chấp nhận một chuỗi chỉ được parse một phần**, dùng `ParsePosition`:

Tạo file **`ParsePreciseDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParsePreciseDecimalDemo {
    public static void main(String[] args) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.#########", 
                DecimalFormatSymbols.getInstance(Locale.US)
        );
        parser.setParseBigDecimal(true);

        String input = "12,345.678";
        ParsePosition position = new ParsePosition(0);
        Number number = parser.parse(input, position);

        if (!(number instanceof BigDecimal parsed)
                || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid number: " + input);
        }

        System.out.println("Type: " + parsed.getClass().getSimpleName());
        System.out.println("Value: " + parsed.toPlainString());
        System.out.println("Complete: " 
                + (position.getIndex() == input.length()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ParsePreciseDecimalDemo.java
java ParsePreciseDecimalDemo
```

Kết quả:

```text
Type: BigDecimal
Value: 12345.678
Complete: true
```

`setParseBigDecimal(true)` phù hợp cho những giá trị hữu hạn thông thường; các trường hợp đặc biệt như NaN/vô cực có thể dẫn đến kiểu trả về khác. Bên cạnh kiểm tra parse hết chuỗi, ứng dụng vẫn phải quyết định quy tắc chấp nhận grouping, ký tự dấu, giới hạn scale, kích thước input và khoảng giá trị. **Parse thành công không đồng nghĩa input hợp lệ theo nghiệp vụ.**

Ngoài ra, không sử dụng `new BigDecimal("12,345.678")` để đọc chuỗi đã định dạng theo locale: constructor này không phải parser locale và sẽ báo lỗi định dạng. Nếu dữ liệu trao đổi giữa dịch vụ theo giao thức máy, tốt hơn dùng biểu diễn chuẩn không phụ thuộc locale (ví dụ chuỗi decimal dạng `12345.678`) thay vì parse chuỗi đã hiển thị cho người dùng.

## 10. Bảo toàn precision và giới hạn hiển thị: cách chọn API

| Yêu cầu | Giải pháp ưu tiên | Tránh |
| --- | --- | --- |
| Lưu và tính số nguyên vượt `long` | `BigInteger` | Ép sang `long`/`double` rồi tính |
| Lưu tiền hoặc số thập phân cần chính xác | `BigDecimal(String)` hoặc nguồn decimal chính xác | `new BigDecimal(double)` cho dữ liệu nghiệp vụ thập phân |
| Hiển thị `BigInteger` theo locale | Đưa trực tiếp vào formatter hỗ trợ `BigInteger` | `format(bigInteger.doubleValue())` |
| Hiển thị `BigDecimal` với số chữ số cố định | `DecimalFormat` với locale symbols, pattern/rounding rõ ràng | Chuyển `BigDecimal` qua `double` trước |
| Làm tròn số học để ghi nhận kết quả | `setScale`/`MathContext` theo chính sách | Lấy chuỗi `format` rồi parse lại để tính |
| Đọc số thập phân giao diện theo locale | `DecimalFormat.setParseBigDecimal(true)`, kiểm tra parse hết chuỗi | `Double.parseDouble(...)` sau khi tự xóa dấu phân nhóm tùy tiện |
| Dữ liệu máy-máy, cần biểu diễn trung lập | `BigDecimal.toPlainString()` hoặc dạng canonical thống nhất | Dùng formatter locale như một serialization format |
| Hiển thị tiền cho người dùng vùng khác | `NumberFormat.getCurrencyInstance(locale)`, currency giao dịch tường minh | Dùng locale để suy ra loại tiền thật của giao dịch |

### Những lỗi thường gặp

1. **Chuyển `BigInteger` sang `double` chỉ để gọi `format(double)`.** Kết quả có thể sai từ chữ số đơn vị. `DecimalFormat` có đường format đối tượng lớn trực tiếp.
2. **Dùng `new BigDecimal(0.1)` và nghĩ giá trị chính xác là một phần mười.** Literal `0.1` là `double` đã xấp xỉ; hãy dùng `new BigDecimal("0.1")` cho giá trị thập phân do nghiệp vụ cung cấp.
3. **Tăng `maximumFractionDigits` sau khi đã mất precision.** Formatter không thể tái tạo dữ liệu bị làm tròn ở bước ép kiểu trước.
4. **Tin rằng mặc định `NumberFormat` in hết mọi chữ số.** Mặc định thường giới hạn số lẻ và dùng grouping; cần cấu hình theo yêu cầu hiển thị.
5. **Nhầm rounding của formatter với rounding của dữ liệu nghiệp vụ.** `format` trả chuỗi, không sửa `BigDecimal`.
6. **Định dạng tiền bằng một locale rồi dùng số đã được format để tính.** Chuỗi hiển thị phụ thuộc dấu nhóm/decimal và có thể làm tròn; giữ giá trị số trong model.
7. **Parse bằng `Double.parseDouble` một chuỗi của locale khác.** Thường không hiểu grouping separator hoặc decimal separator theo người dùng; dùng parser theo locale.
8. **Dùng `Double.toString` như bằng chứng mọi chữ số của nguồn đã được giữ nguyên.** Chuỗi đó là dạng round-trip của giá trị `double` hiện có, không phải nguồn thập phân ban đầu.
9. **Chia sẻ một `DecimalFormat` mutable giữa nhiều request và thay đổi cài đặt.** `NumberFormat`/`DecimalFormat` không được bảo đảm thread-safe; tạo formatter riêng hoặc đồng bộ hóa khi chia sẻ.
10. **Coi mã định danh lớn là số cần định dạng.** ID thường là token, có thể có số 0 đầu hoặc yêu cầu biểu diễn ổn định; không tự thêm grouping hay đổi dạng. Chỉ định dạng số nếu dữ liệu thực sự có ngữ nghĩa số lượng.

## 11. Bài tập tự kiểm tra

**Câu 1.** Vì sao `new BigInteger("9007199254740993").doubleValue()` khác giá trị gốc?

**Đáp án:** `double` có 53 bit precision; số nguyên `2^53+1` không biểu diễn được chính xác nên làm tròn thành `2^53`. Số nguyên dạng `BigInteger` không bị lỗi đó.

**Câu 2.** Cho `new BigDecimal("12345678901234567890.123456789")`. Muốn in chín số lẻ mà không mất precision, nên dùng API nào?

**Đáp án:** `DecimalFormat` có pattern hay cấu hình 9 chữ số lẻ, truyền trực tiếp `BigDecimal` vào `format(Object)`. Không ép `double`.

**Câu 3.** `DecimalFormat("0.00")` với `HALF_EVEN` và `HALF_UP` định dạng `BigDecimal("1.005")` ra sao?

**Đáp án:** `HALF_EVEN` → `1.00`; `HALF_UP` → `1.01`. Trong cả hai trường hợp, giá trị `BigDecimal` đầu vào vẫn là `1.005`.

**Câu 4.** Tại sao `new BigDecimal(0.1)` và `new BigDecimal("0.1")` khác nhau?

**Đáp án:** Constructor nhận `double` lấy giá trị nhị phân đã xấp xỉ, trong khi constructor chuỗi đọc các chữ số thập phân được chỉ định chính xác.

**Câu 5.** Khi parse `"12,345.678"` với `Locale.US` và cần giữ kiểu thập phân chính xác, làm gì?

**Đáp án:** Dùng `DecimalFormat` với symbols của `Locale.US`, bật `setParseBigDecimal(true)` và xác nhận `ParsePosition` đã tiêu thụ toàn bộ chuỗi; sau đó kiểm tra ràng buộc nghiệp vụ.

**Câu 6.** Nếu formatter in `1.20` từ `BigDecimal("1.2")`, đối tượng gốc có bị đổi scale không?

**Đáp án:** Không. Formatter tạo chuỗi hiển thị; muốn đổi scale của số dùng `setScale(...)` theo chính sách.

**Câu 7.** Formatter in một số lớn dưới dạng `12345678901234567000.000000000`. Có nên coi phần chín chữ số 0 là bằng chứng dữ liệu thập phân chính xác?

**Đáp án:** Không. Đây có thể là đầu ra từ `double` đã làm tròn; chữ số 0 do pattern thêm vào chỉ là trình bày.

## 12. Kết luận và tài liệu tham khảo

- `BigInteger` bảo toàn số nguyên lớn; `BigDecimal` bảo toàn thập phân chính xác nếu được tạo và thao tác đúng. `double` là xấp xỉ nhị phân có phạm vi/precision hữu hạn.
- `DecimalFormat` có thể định dạng trực tiếp `BigInteger` và `BigDecimal`; **không cần và không nên ép sang `double`** chỉ vì muốn trình bày.
- Kiểm soát `Locale`, `DecimalFormatSymbols`, grouping, minimum/maximum digits và `RoundingMode`. Mỗi quyết định này liên quan đến **chuỗi hiển thị**, không tự sửa dữ liệu gốc.
- Giữ phép tính trong kiểu chính xác, làm tròn số học theo quy tắc nghiệp vụ và chỉ định dạng ở lớp giao diện/xuất báo cáo.
- Khi parse số do người dùng nhập theo locale, dùng `DecimalFormat.setParseBigDecimal(true)` và xác thực rằng đã parse toàn bộ chuỗi.

Tài liệu chính thức:

- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 21 — BigInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
