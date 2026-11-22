# Locale, mẫu định dạng và dấu phân cách số trong Java

Một số có **giá trị** và có **cách trình bày**. Ví dụ, cùng một giá trị một triệu hai trăm ba mươi bốn nghìn năm trăm sáu mươi bảy phẩy năm có thể hiển thị như `1,234,567.50` hoặc `1.234.567,50` tùy quy ước vùng. Dấu phẩy không phải lúc nào cũng là dấu thập phân; dấu chấm cũng không phải lúc nào cũng là dấu nhóm hàng nghìn.

Trong Java, `Locale` mô tả quy ước ngôn ngữ/vùng để **định dạng** và **đọc** giá trị cho con người. `Formatter`, `printf`, `NumberFormat`, `DecimalFormat` và `Scanner` có những cách sử dụng `Locale` khác nhau. Bài học thuộc nhóm **Console và định dạng**, tập trung vào định dạng số khi in console, mẫu định dạng, dấu tách nhóm, dấu thập phân, parsing đầu vào và các lỗi dễ gây sai số.

## 1. Ba lớp vấn đề cần phân biệt

**Giá trị số:** Một biến `long total = 1234567;` hay `BigDecimal amount = new BigDecimal("1234567.50");` chứa giá trị số. Bản thân biến không chứa dấu nhóm hàng nghìn hay quy ước hiển thị thập phân.

**Biểu diễn số dưới dạng văn bản:** Khi ứng dụng gọi `String.format(...)` hay `NumberFormat.format(...)`, kết quả là `String`. Chuỗi có thể có dấu nhóm (`,`, `.` hoặc khoảng trắng đặc biệt), dấu thập phân, chữ số bản địa, dấu âm, ký hiệu tiền tệ, v.v.

**Diễn giải văn bản thành số:** Khi người dùng nhập `1.234,50`, chương trình cần biết đó là số theo quy ước nào. Nếu áp dụng ngữ pháp US một cách máy móc, có thể hiểu sai hoặc từ chối input. `Scanner` và `NumberFormat` hỗ trợ một phần quá trình chuyển ngược này.

Ba lớp này cần được định nghĩa rõ khi thiết kế giao diện console:

```text
Giá trị số (BigDecimal, long, double...)
          |
          | format với Locale + quy tắc hiển thị
          v
Chuỗi hiển thị (ví dụ "1.234,50")
          |
          | parse với Locale + kiểm tra hợp lệ
          v
Giá trị số (nếu chuyển đổi thành công)
```

**`Locale` là lựa chọn biểu diễn và quy tắc văn hóa, không phải cơ chế chuyển đổi kiểu số lưu trong bộ nhớ.** Thay `Locale.US` bằng `Locale.GERMANY` không làm giá trị `1234567.5` thay đổi. Nó cũng không tự đổi charset console thành UTF-8.

## 2. `Locale` và quy ước phân cách số

`java.util.Locale` định danh một ngôn ngữ và tùy chọn vùng, ví dụ:

- `Locale.US`: một cấu hình tiếng Anh/Mỹ, thường dùng dấu **phẩy** để nhóm hàng nghìn và dấu **chấm** để ngăn phần thập phân.
- `Locale.GERMANY`: tiếng Đức/Đức, thường dùng dấu **chấm** để nhóm và dấu **phẩy** cho thập phân.
- `Locale.forLanguageTag("vi-VN")`: tiếng Việt/Việt Nam, hữu ích khi ứng dụng dành cho người dùng Việt. Ký tự phân cách, cách hiển thị tiền tệ, chữ số và các chi tiết cụ thể có thể phụ thuộc dữ liệu locale của môi trường Java; nên kiểm tra bằng API thay vì hard-code mọi quy tắc.
- `Locale.FRANCE`: ví dụ về trường hợp nhóm chữ số bằng **khoảng trắng chuyên biệt** (có thể là narrow no-break space tùy dữ liệu locale), khác với dấu cách ASCII thông thường.

Bảng minh họa cho giá trị `1234567.5`, giả định luôn hiển thị hai chữ số sau dấu thập phân:

| Locale | Biểu diễn số phổ biến | Phân cách nhóm | Phân cách thập phân |
|---|---|---|---|
| `Locale.US` | `1,234,567.50` | `,` | `.` |
| `Locale.GERMANY` | `1.234.567,50` | `.` | `,` |
| `Locale.forLanguageTag("vi-VN")` | Theo dữ liệu locale của JDK đang dùng | Tra từ `DecimalFormatSymbols` | Tra từ `DecimalFormatSymbols` |

Mốc ba chữ số chỉ là một ví dụ; không phải mọi vùng trên thế giới đều nhóm số theo cụm ba chữ số giống US. Dấu tách còn có thể là **ký tự Unicode không nhìn thấy rõ**, nhất là các dạng space. Vì vậy không nên so sánh trực tiếp với `" "` khi xử lý output của mọi locale.

### Kiểm tra ký tự phân cách thực tế

Trong một phương thức Java (đoạn minh họa, cần import các kiểu):

```java
Locale locale = Locale.forLanguageTag("vi-VN");
DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(locale);
char grouping = symbols.getGroupingSeparator();
char decimal = symbols.getDecimalSeparator();
```

Với import `java.util.Locale` và `java.text.DecimalFormatSymbols`, hai ký tự trên cho biết dấu nhóm và dấu thập phân mà API cung cấp cho locale. Nếu cần debug khoảng trắng, hãy in **Unicode code point** thay vì chỉ nhìn ký tự.

Một số thành phần hiển thị (như dấu phần trăm, đơn vị tiền tệ, vị trí ký hiệu, số lượng chữ số thập phân mặc định) còn tùy API `NumberFormat` và thiết lập vùng.

## 3. `printf` và `String.format`: định dạng trực tiếp với Locale

Java `System.out.printf` (thông qua `PrintStream`) và `String.format` dùng ngôn ngữ định dạng của `java.util.Formatter`. Cả hai cho phép truyền **`Locale` tường minh**, ví dụ:

```java
String us = String.format(Locale.US, "%,.2f", 1234567.5);
System.out.printf(Locale.GERMANY, "%,.2f%n", 1234567.5);
```

Đây là **đoạn minh họa**: cần import `java.util.Locale`. Nên truyền locale khi đầu ra phải ổn định trên nhiều máy; phiên bản không nhận locale sẽ dùng locale mặc định phù hợp với API và môi trường đang chạy, vốn có thể khác.

### Cấu trúc của format specifier

Một format specifier kiểu thông dụng:

```text
% [flags] [width] [.precision] conversion
```

Ví dụ `%,12.2f`:

- `%`: mở đầu một phép định dạng.
- `,`: **flag grouping** yêu cầu sử dụng dấu nhóm theo locale với conversion được hỗ trợ.
- `12`: **minimum width** (độ rộng tối thiểu); không phải số ký tự tối đa và không cắt bớt giá trị dài.
- `.2`: precision, với `%f` là số chữ số sau dấu thập phân.
- `f`: định dạng số dạng thập phân cố định.

Các mẫu hữu ích:

| Format | Ý nghĩa | Ví dụ khi dùng US |
|---|---|---|
| `%d` | Số nguyên thập phân, không chủ động tách nhóm | `1234567` |
| `%,d` | Số nguyên có nhóm theo locale | `1,234,567` |
| `%.2f` | Số thực với hai chữ số thập phân, không grouping | `1234567.50` |
| `%,.2f` | Số thực với grouping và hai chữ số thập phân | `1,234,567.50` |
| `%12.2f` | Tối thiểu 12 ký tự, mặc định canh phải | Thêm khoảng trắng bên trái nếu cần |
| `%-12.2f` | Tối thiểu 12 ký tự, canh trái | Thêm khoảng trắng bên phải nếu cần |
| `%n` | Xuống dòng theo môi trường | Dùng trong định dạng console thay vì tự gắn `\n` nếu muốn quy ước hệ thống |
| `%%` | In ký tự `%` literal | `%` |

**Flag `,` ở đây là ký hiệu cú pháp của Formatter, không có nghĩa dấu nhóm xuất ra luôn là ký tự dấu phẩy.** Với `Locale.GERMANY`, cùng format `%,.2f` sẽ in dấu nhóm `.` và dấu thập phân `,`.

Không phải conversion nào cũng nhận mọi flag. Ví dụ dùng grouping với `%s` là không phù hợp. `%s` định dạng đối tượng dưới dạng chuỗi và không biến số thành biểu diễn grouping tự động. Sử dụng conversion phù hợp với kiểu dữ liệu.

### Ví dụ 1 — so sánh định dạng US và Đức trên console

Tạo file `PrintfLocaleDemo.java` (Java 17+):

```java
import java.util.Locale;

public class PrintfLocaleDemo {
    public static void main(String[] args) {
        double amount = 1_234_567.5;

        System.out.println("US grouping: "
                + String.format(Locale.US, "%,.2f", amount));
        System.out.println("DE grouping: "
                + String.format(Locale.GERMANY, "%,.2f", amount));
        System.out.println("US no grouping: "
                + String.format(Locale.US, "%.2f", amount));
        System.out.println("US integer: "
                + String.format(Locale.US, "%,d", 1234567));
        System.out.println("DE integer: "
                + String.format(Locale.GERMANY, "%,d", 1234567));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 PrintfLocaleDemo.java
java PrintfLocaleDemo
```

Kết quả đã kiểm tra:

```text
US grouping: 1,234,567.50
DE grouping: 1.234.567,50
US no grouping: 1234567.50
US integer: 1,234,567
DE integer: 1.234.567
```

Hai dòng đầu dùng cùng `amount` nhưng cho chuỗi khác nhau. Dòng thứ ba không có flag `,` nên không nhóm số. Hai dòng cuối cho thấy `%,d` cũng chịu tác động của locale; dữ liệu đầu vào là cùng số nguyên `1234567`.

**Về kiểu số:** `double` thuận tiện cho ví dụ nhưng biểu diễn nhị phân của nó không chính xác tuyệt đối với nhiều phân số thập phân (ví dụ `0.1`). Với tiền, thuế hoặc các phép làm tròn thập phân có ràng buộc, ưu tiên `BigDecimal` khởi tạo từ chuỗi và quy định `RoundingMode` rõ ràng.

### Một số lỗi cú pháp Formatter

- `String.format(Locale.US, "%,.2f", "1234.5")` là **sai kiểu**: chuỗi không phải đối số số thực cho `%f`; có thể ném `IllegalFormatConversionException`.
- `String.format(Locale.US, "%s", 1234.5)` không tự thêm dấu nhóm hay thập phân theo locale; vì `%s` dùng biểu diễn chuỗi của đối tượng.
- `System.out.printf("%f", value)` không chọn cố định precision hai chữ số; cần `%.2f` hoặc quy tắc độ chính xác khác.
- `String.format(Locale.GERMANY, "%,.2f", value)` **đúng** dù cú pháp chứa ký tự comma: đây là flag group, không phải ký tự cố định trong output.
- Không dùng một chuỗi hiển thị có grouping như `"1,234.50"` rồi gọi `Double.parseDouble` và mong JVM hiểu dấu phân cách vùng; `Double.parseDouble` dùng ngữ pháp số của Java, không phải locale.

## 4. `NumberFormat`: biểu diễn số, phần trăm và tiền tệ

`java.text.NumberFormat` là API chuyên cho biểu diễn số theo locale. Các factory thường dùng:

- `NumberFormat.getNumberInstance(locale)`: số thông thường.
- `NumberFormat.getIntegerInstance(locale)`: biểu diễn số nguyên theo cài đặt locale.
- `NumberFormat.getCurrencyInstance(locale)`: hiển thị tiền tệ theo locale/đồng tiền tương ứng.
- `NumberFormat.getPercentInstance(locale)`: hiển thị phần trăm; với giá trị `0.125` thường biểu diễn `12.5%` nếu chọn một chữ số thập phân.

Ví dụ:

```java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
number.setGroupingUsed(true);
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
String view = number.format(new BigDecimal("1234567.5"));
```

Đây là **mã minh họa**, cần import `java.text.NumberFormat`, `java.util.Locale` và `java.math.BigDecimal`. `view` theo US sẽ là `"1,234,567.50"` trong môi trường Java thông thường.

Tính năng cấu hình:

- `setGroupingUsed(boolean)`: bật/tắt nhóm chữ số.
- `setMinimumFractionDigits(int)` / `setMaximumFractionDigits(int)`: giới hạn số chữ số phần thập phân ở đầu ra.
- `setRoundingMode(RoundingMode)`: quy định cách làm tròn ở implementation hỗ trợ. Với Java `DecimalFormat`, có thể dùng `RoundingMode.HALF_UP`, `HALF_EVEN`, v.v.
- `format(...)`: biến giá trị thành `String`; **không sửa** biến số gốc.

### Tiền tệ và phần trăm không chỉ là dấu tách

Đừng cố format tiền tệ bằng mỗi `%,.2f` rồi tự nối ký hiệu `$`/`₫`. Quy ước tiền tệ còn bao gồm vị trí ký hiệu, chữ số thập phân mặc định, ký tự cách, dấu âm và lựa chọn currency.

Tương tự, định dạng phần trăm trong `NumberFormat.getPercentInstance` **nhân giá trị với 100 để hiển thị**. Chẳng hạn `0.125` ứng với `12.5%`, không phải `0.125%`. Nếu input đã là số “12.5” đại diện cho 12,5%, đừng truyền trực tiếp vào percent formatter mà chưa xác định đơn vị miền nghiệp vụ.

Để cố định đồng tiền bất kể locale, có thể thiết lập `Currency` cho formatter, nhưng ký hiệu, cách đặt và quy tắc hiển thị vẫn phải được kiểm tra cho trường hợp sử dụng cụ thể.

## 5. `DecimalFormat` và ngôn ngữ mẫu định dạng

`java.text.DecimalFormat` là implementation mạnh của `NumberFormat` cho phép quy định mẫu như:

```text
#,##0.00
```

Các ký hiệu **trong mẫu chưa bản địa hóa**:

| Ký hiệu pattern | Ý nghĩa |
|---|---|
| `0` | Vị trí chữ số **bắt buộc**; thêm số 0 nếu cần |
| `#` | Vị trí chữ số **tùy chọn** |
| `,` | Vị trí **nhóm chữ số** trong pattern; ký tự nhóm thật lấy từ symbols/locale |
| `.` | Vị trí **phân cách thập phân** trong pattern; dấu thật lấy từ symbols/locale |
| `;` | Phân tách subpattern dương và âm nếu định nghĩa hai nhánh |
| `%` | Hệ số biểu diễn phần trăm (nhân 100) và ký hiệu phần trăm theo locale |
| `'...'` | Quote ký tự literal theo cú pháp pattern khi cần |

Với pattern `#,##0.00`, formatter nhóm các chữ số và luôn hiển thị **đúng hai** chữ số phần thập phân. Locale quyết định `,` hay `.` được in ra thực tế.

**Điểm rất dễ nhầm:** `applyPattern("#,##0.00")` nhận cú pháp pattern chuẩn sử dụng dấu `,` cho grouping và `.` cho decimal **bất kể locale hiển thị**. Khi dùng `applyLocalizedPattern(...)`, cú pháp pattern lại theo `DecimalFormatSymbols` của locale. Không được tráo lẫn hai phương thức.

Ví dụ `DecimalFormat` tạo từ `NumberFormat.getNumberInstance(Locale.GERMANY)` rồi áp dụng pattern `#,##0.00` sẽ hiển thị `1.234.567,50`. Không phải viết ngược pattern thành `#.##0,00` cho `applyPattern`.

### Ví dụ 2 — định dạng, làm tròn và phân tích số với `DecimalFormat`

Tạo file `DecimalFormatLocaleDemo.java` (Java 17+):

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class DecimalFormatLocaleDemo {
    public static void main(String[] args) {
        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
        format.applyPattern("#,##0.00");
        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);

        System.out.println("formatted=" + format.format(new BigDecimal("1234567.5")));
        System.out.println("rounded=" + format.format(new BigDecimal("12.345")));

        String input = "1.234.567,50";
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(input, position);
        System.out.println("parsed=" + ((BigDecimal) parsed).toPlainString());
        System.out.println("fully parsed="
                + (parsed != null && position.getIndex() == input.length()));

        String withSuffix = input + "oops";
        ParsePosition extraPosition = new ParsePosition(0);
        Number partial = format.parse(withSuffix, extraPosition);
        System.out.println("suffix rejected by full check="
                + (partial != null && extraPosition.getIndex() != withSuffix.length()));

        NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
        percent.setMinimumFractionDigits(1);
        System.out.println("percent=" + percent.format(new BigDecimal("0.125")));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DecimalFormatLocaleDemo.java
java DecimalFormatLocaleDemo
```

```text
formatted=1.234.567,50
rounded=12,35
parsed=1234567.50
fully parsed=true
suffix rejected by full check=true
percent=12.5%
```

**Giải thích:**

1. Factory tạo number formatter theo `Locale.GERMANY`; đoạn ví dụ sử dụng implementation `DecimalFormat` của bộ locale chuẩn trong JDK. `applyPattern("#,##0.00")` chọn grouping và hai chữ số phần thập phân.
2. `setRoundingMode(HALF_UP)` khiến `12.345` (được khởi tạo **chính xác** bằng chuỗi `BigDecimal`) được hiển thị là `12,35`.
3. `setParseBigDecimal(true)` yêu cầu `DecimalFormat` tạo kết quả parse ở dạng `BigDecimal` cho các giá trị số thông thường, tránh chuyển sang `Double` và mất độ chính xác thập phân không cần thiết. Các trường hợp ký hiệu đặc biệt như NaN/Infinity vẫn cần xem contract của parser.
4. `ParsePosition` cho biết **đã đọc đến đâu** trong chuỗi. Chỉ khi `parsed != null` và `position.getIndex() == input.length()` mới coi là đã tiêu thụ hết input.
5. `format.parse("1.234.567,50oops", ...)` có thể đọc **phần đầu hợp lệ** rồi dừng ở chữ `o` mà không ném exception; đây là lý do phải kiểm tra vị trí cuối.
6. `NumberFormat.getPercentInstance(Locale.US)` nhân `0.125` với 100 để hiển thị `12.5%`.

**Giới hạn của kiểm tra `ParsePosition`:** tiêu thụ toàn bộ chuỗi không đồng nghĩa mọi quy tắc nghiệp vụ hay mọi vị trí grouping đều được xác thực nghiêm ngặt. `DecimalFormat` có hành vi parsing khá dễ dãi ở nhiều trường hợp. Với input nhạy cảm (số tiền, số hợp đồng, giao thức), nên kiểm tra thêm mẫu ký tự, phạm vi, định dạng grouping và số lượng chữ số được phép trước khi nhận dữ liệu.

## 6. `DecimalFormatSymbols` và dấu tách số thật

`DecimalFormatSymbols` nắm các ký hiệu vùng, chẳng hạn:

- `getDecimalSeparator()`: ký tự phân cách phần nguyên và phần thập phân.
- `getGroupingSeparator()`: ký tự nhóm phần nguyên.
- `getMinusSign()`: dấu âm dùng trong định dạng theo locale.
- `getPercent()`: dấu phần trăm.
- `getZeroDigit()`: chữ số 0 để biểu diễn các bộ chữ số được locale dùng.
- `getCurrencySymbol()` và `getInternationalCurrencySymbol()`: ký hiệu tiền tệ.

Trong ứng dụng đa ngôn ngữ, **lấy dữ liệu từ symbols** thường an toàn hơn tự viết logic dạng `if (locale.equals(Locale.GERMANY)) ...`. Tuy nhiên, `Locale` chỉ là một phần của yêu cầu: nếu hệ thống cần định dạng cố định (ví dụ CSV phải dùng dấu chấm thập phân), chính **đặc tả dữ liệu đích** mới quyết định.

Các ví dụ parser dễ lỗi khi có ký tự khoảng trắng đặc biệt ở grouping, dấu âm Unicode, chữ số không phải 0–9 ASCII hoặc dấu phần trăm. Nếu giao diện nhận output từ thư viện i18n, hãy kiểm tra code point thực tế khi điều tra bug thay vì chỉ nhìn dấu in trên màn hình.

### Tùy biến ký hiệu có chủ đích

Có thể tạo `DecimalFormatSymbols` cho một locale rồi sửa grouping/decimal separator và truyền vào `DecimalFormat`. Nhưng cách này là **quy tắc tùy chỉnh của ứng dụng**, không còn chắc giống chuẩn địa phương. Nếu yêu cầu đơn thuần là in số đúng vùng, hãy chọn locale và dùng formatter mặc định trước khi nghĩ tới override.

Tương tự, không nên thay `,` thành `.` bằng `String.replace` trên **toàn chuỗi số đã format**; nếu cả hai dấu cùng xuất hiện, thứ tự thay có thể làm hỏng grouping, và điều này càng sai khi có tiền tệ hoặc khoảng trắng Unicode.

## 7. Đọc đầu vào console bằng `Scanner.useLocale`

`java.util.Scanner` phân tích token từ chuỗi, stdin, file hoặc nguồn khác. Khi gọi `Scanner.nextInt()`, `nextDouble()`, `nextBigDecimal()`, ... Scanner có thể dùng locale để diễn giải **dấu grouping, dấu thập phân và một số ký hiệu số**.

**Locale dành cho đầu vào** phải tương ứng với quy ước mà người dùng được yêu cầu nhập. Thay đổi locale **không** làm các ký tự có sẵn trong input tự đổi từ `,` sang `.`.

### Ví dụ 3 — cùng giá trị nhập theo hai quy ước

Tạo file `ScannerLocaleDemo.java` (Java 17+):

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Scanner;

public class ScannerLocaleDemo {
    public static void main(String[] args) {
        try (Scanner us = new Scanner("1,234.50").useLocale(Locale.US);
             Scanner de = new Scanner("1.234,50").useLocale(Locale.GERMANY)) {
            BigDecimal a = us.nextBigDecimal();
            BigDecimal b = de.nextBigDecimal();
            System.out.println("US parsed=" + a.toPlainString());
            System.out.println("DE parsed=" + b.toPlainString());
            System.out.println("same numeric value=" + (a.compareTo(b) == 0));
        }
        try (Scanner strictGerman = new Scanner("1234.50")
                .useLocale(Locale.GERMANY)) {
            System.out.println("DE accepts 1234.50="
                    + strictGerman.hasNextBigDecimal());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ScannerLocaleDemo.java
java ScannerLocaleDemo
```

```text
US parsed=1234.50
DE parsed=1234.50
same numeric value=true
DE accepts 1234.50=false
```

Giải thích:

- Cả hai token số có **giá trị tương đương**: `1,234.50` ở US và `1.234,50` ở Đức.
- `nextBigDecimal()` trả `BigDecimal`; so sánh giá trị bằng `compareTo`, vì `BigDecimal.equals` còn xét cả **scale** (ví dụ `1.0` và `1.00` có thể so sánh bằng giá trị nhưng `equals` khác).
- Scanner đặt locale Đức không nhận token `1234.50` theo cú pháp số thập phân Đức của ví dụ; `hasNextBigDecimal()` cho biết việc gọi `nextBigDecimal()` có phù hợp với token kế tiếp hay không.
- Đây là demo dùng **String input** để đầu ra có thể kiểm chứng; khi đọc `System.in`, cần thiết lập locale theo lựa chọn của người dùng và giải quyết rõ charset đầu vào.

Đối với dữ liệu không hợp lệ, `nextBigDecimal()` có thể ném `InputMismatchException`, hoặc `NoSuchElementException` nếu đã hết input. Trong một chương trình tương tác, hãy kiểm tra và báo người dùng nhập lại thay vì nuốt exception hoặc âm thầm suy đoán locale khác.

### Scanner: token và dòng khác nhau

`Scanner` mặc định phân tách token bằng khoảng trắng, **không** coi dấu nhóm số là token delimiter. Khi chuyển giữa `nextBigDecimal()` và `nextLine()`, cần lưu ý dấu kết thúc dòng còn lại (ví dụ sau khi nhập số rồi nhấn Enter, `nextLine()` đầu tiên có thể trả chuỗi rỗng). Đây là hành vi thao tác token-vs-line, độc lập với việc dấu thập phân là comma hay dot.

Một cách thiết kế rõ là: đọc **một dòng hoàn chỉnh** bằng `BufferedReader.readLine()` / `Scanner.nextLine()`, sau đó validate và parse dòng đó theo locale đã chọn. Cách này cho phép báo lỗi trên chính chuỗi người dùng gửi.

## 8. `BigDecimal` và dữ liệu trung gian không phụ thuộc locale

Đối với tiền và số thập phân cần chính xác, `BigDecimal` thường là lựa chọn thích hợp. Nhưng **`new BigDecimal(String)` không phải parser theo locale**:

```java
BigDecimal value = new BigDecimal("1234.50");
```

Đây là mã minh họa; cần import `java.math.BigDecimal`. Chuỗi dùng **dấu chấm** cho phần thập phân và không có grouping theo ngữ pháp `BigDecimal`, dù ứng dụng hiển thị theo `Locale.GERMANY`. `new BigDecimal("1.234,50")` là không hợp lệ đối với constructor này; để nhận input địa phương, hãy dùng parser locale và kiểm tra kết quả.

Khi truyền dữ liệu giữa các hệ thống, cần phân biệt:

- **Giá trị nội bộ:** `BigDecimal` hoặc các kiểu số theo quy tắc nghiệp vụ.
- **Đầu ra cho người dùng:** format theo locale (có grouping, ký hiệu phần trăm/tiền tệ).
- **Giao thức hoặc cấu hình máy đọc:** format **bất biến** do đặc tả quy định, thường không grouping và dùng dấu chấm decimal. Ví dụ `BigDecimal.toPlainString()` cho representation thập phân không có ký pháp số mũ ở mức chuỗi.
- **JSON number:** cú pháp JSON không chấp nhận dấu tách nhóm hàng nghìn; decimal separator theo grammar JSON là dấu chấm. Khi sinh JSON, dùng serializer thực sự, không đưa trực tiếp chuỗi đã format theo locale vào vị trí số.

**Không ghép output dành cho người đọc trở lại làm input cho parser máy đọc** nếu chưa xác nhận chính xác locale, định dạng và chính sách kiểm tra. Việc format rồi parse lại có thể mất chữ số vì quy tắc làm tròn, hoặc biến dữ liệu thành invalid khi môi trường triển khai thay đổi.

## 9. Khác nhau giữa độ chính xác, scale và làm tròn

Ví dụ giá trị thập phân `12.345`:

- `BigDecimal("12.345")` lưu ba chữ số phần thập phân một cách chính xác.
- `DecimalFormat` với pattern `"0.00"` chỉ **hiển thị** hai chữ số; nếu áp dụng `RoundingMode.HALF_UP` thì ra `12.35` theo US hoặc `12,35` theo Đức.
- `BigDecimal.setScale(2, RoundingMode.HALF_UP)` trả **giá trị BigDecimal mới** đã được làm tròn ở scale 2; đây là bước biến đổi dữ liệu, khác với chỉ format.
- `double` là dạng dấu phẩy động nhị phân; làm tròn giá trị double có thể gặp các trường hợp khó dự đoán theo trực giác thập phân.

Không nên dùng việc định dạng `%.2f` làm một quy trình tính tiền. Hãy quy định cách làm tròn nghiệp vụ, xử lý bằng kiểu số phù hợp, sau đó format chỉ để hiển thị.

**Grouping không làm tròn.** `setGroupingUsed(true)` chỉ yêu cầu phân cách các nhóm chữ số. Việc hiển thị hai chữ số sau dấu thập phân do pattern/precision/min-max fraction digits quyết định.

**Precision của `Formatter` và digit pattern của `DecimalFormat` khác cú pháp:**

- `%.2f`: cú pháp Formatter dành cho một argument dạng số thực.
- `#,##0.00`: cú pháp DecimalFormat biểu diễn một con số bằng ký hiệu pattern.
- Không truyền mẫu `#,##0.00` vào `printf` rồi mong Formatter hiểu nó như `DecimalFormat`.

## 10. Locale mặc định, khả năng tái lập và thread safety

### Không phụ thuộc vô thức vào locale mặc định

`Locale.getDefault()` lấy locale mặc định của môi trường. Giá trị có thể khác giữa máy phát triển, máy build, container, desktop người dùng và cấu hình runtime. Vì vậy hai cách gọi:

```java
String ambiguous = String.format("%,.2f", 1234.5);
String explicit = String.format(Locale.US, "%,.2f", 1234.5);
```

là **mã minh họa**; cần import `java.util.Locale`. Chuỗi `ambiguous` phụ thuộc locale mặc định, còn `explicit` buộc quy tắc US. Thay `Locale.setDefault(...)` toàn tiến trình để giải quyết một vị trí format cụ thể có thể ảnh hưởng nhiều mã thư viện khác, nên ưu tiên truyền locale tại điểm định dạng.

Với console, có hai vấn đề tách biệt:

1. **Locale**: dấu thập phân, dấu grouping, chữ số, cách hiển thị.
2. **Charset/encoding của console**: chuyển ký tự Unicode thành byte để terminal render. Đổi locale không bảo đảm terminal có font/glyph hoặc encoding đúng.

Nếu kết quả số trông sai ký tự, kiểm tra cả symbols của locale và encoding đầu ra (nhất là khi dùng dấu cách Unicode hoặc chữ số ngoài ASCII).

### Đừng chia sẻ tùy tiện `DecimalFormat`

`DecimalFormat` và `NumberFormat` (thông thường) là các formatter **có trạng thái, mutable và không bảo đảm thread-safe**. Thay pattern, rounding mode hoặc symbols trong một thread có thể làm thread khác thấy kết quả không mong đợi.

Với ứng dụng concurrent, tạo formatter theo từng lần sử dụng, per-thread hoặc bảo vệ truy cập theo một chính sách đồng bộ phù hợp. `Locale` có thể dùng như đối tượng chỉ định chính sách; đừng giữ một formatter mutable toàn cục rồi thay đổi pattern theo từng request.

`String.format(Locale, ...)` tạo formatter phục vụ lời gọi đó, thuận tiện cho các tác vụ hiển thị không yêu cầu giữ một formatter mutable.

## 11. Khi parse dữ liệu người dùng, cần kiểm tra gì?

Trước khi chấp nhận một chuỗi số thành dữ liệu nghiệp vụ:

1. **Chọn đúng locale đầu vào.** Người dùng biết mình phải nhập `1,234.50` hay `1.234,50` không? Trường nhập có hiển thị ví dụ minh họa không?
2. **Phân biệt kiểu dữ liệu.** Số nguyên, số thực, tiền, phần trăm, tỷ lệ hay số điện thoại/mã bưu chính? Không phải chuỗi toàn chữ số nào cũng nên parse thành số; mã định danh có thể cần giữ số 0 đầu.
3. **Xử lý grouping.** Có chấp nhận dấu nhóm hay yêu cầu input canonical không grouping? Nếu chấp nhận, parser có kiểm tra **đúng vị trí** nhóm hay chỉ bỏ dấu nhóm một cách khoan dung?
4. **Kiểm tra parse toàn bộ chuỗi.** Với `NumberFormat.parse` và `ParsePosition`, tránh chấp nhận `"1.234,50abc"` chỉ vì phần tiền tố parse được.
5. **Kiểm tra biên giá trị và scale.** Số có âm được không? Cho phép bao nhiêu chữ số thập phân? Giá trị có nằm trong khoảng nghiệp vụ?
6. **Quy định cách làm tròn.** Với tiền, sử dụng `BigDecimal` và `RoundingMode` theo chính sách được xác định.
7. **Không tự đổi tất cả dấu phân cách.** `replace(",", ".")` biến `"1,234.50"` thành `"1.234.50"` và phá giá trị. Thao tác thay ký tự tùy tiện không giải quyết được parser đa locale.
8. **Kiểm tra ký tự Unicode.** Grouping của một số locale dùng khoảng trắng đặc biệt. Sao chép từ trang web/bảng tính có thể đưa vào ký tự không phải ASCII space.
9. **Báo lỗi rõ ràng.** Thay vì âm thầm parse theo locale khác, cung cấp ví dụ đúng và để người dùng sửa chuỗi.
10. **Tách format UI khỏi format file/giao thức.** Log máy đọc, CSV, JSON và dữ liệu gửi API phải dùng cú pháp được định nghĩa bởi định dạng đích.

Việc `NumberFormat.parse` trả `Number` thành công **không phải** bảo đảm bảo toàn chính xác chữ số đầu vào, tính hợp lệ miền nghiệp vụ hay grouping nghiêm ngặt. `setParseBigDecimal(true)` chỉ giúp phần giá trị thập phân được biểu diễn phù hợp hơn, không thay thế bước validate.

## 12. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm tốt hơn |
|---|---|---|
| Coi `,` luôn là dấu nhóm và `.` luôn là thập phân | Vai trò có thể đảo theo locale | Truyền locale và dùng formatter/parser tương ứng |
| Viết `%,.2f` nhưng nghĩ flag comma phải in dấu phẩy | Formatter dùng flag cố định, output localized | Kiểm tra bằng US/Germany với cùng format |
| Lấy `Double.toString`/`%s` để hiển thị số theo locale | Chỉ có biểu diễn chuỗi không chọn grouping theo locale | `String.format(locale, "%,.2f", value)` hoặc `NumberFormat` |
| Tự viết `value.replace(".", ",")` | Dễ phá grouping, ký hiệu và nội dung | Dùng API formatting của Java |
| Gọi `new BigDecimal("1.234,50")` | Constructor không parse theo locale | Dùng parser localized có kiểm tra |
| Nhầm `applyPattern` và `applyLocalizedPattern` | Cú pháp ký hiệu pattern khác nhau | Dùng `applyPattern("#,##0.00")` với ký hiệu pattern chuẩn |
| Dùng `DecimalFormat.parse` rồi bỏ qua `ParsePosition` | Có thể chấp nhận đầu chuỗi hợp lệ và bỏ suffix | Xác thực parse toàn bộ chuỗi; validate thêm |
| Dùng `double` cho tiền mà không định nghĩa rounding | Sai lệch biểu diễn nhị phân và quy tắc làm tròn | `BigDecimal` + `RoundingMode` |
| Dùng percent formatter cho giá trị 12.5 khi muốn 12.5% | Percent formatter nhân 100 | Dùng tỷ lệ `0.125` |
| Ghi số localized vào JSON number hoặc cột CSV máy đọc | Định dạng máy đọc có grammar riêng | Dùng serializer và quy tắc định dạng chuẩn của file/giao thức |
| Giữ `DecimalFormat` mutable dùng chung nhiều thread | Không bảo đảm thread-safe | Formatter per-call hoặc đồng bộ thích hợp |
| Trông chờ `Locale` sửa font/encoding console | Locale chỉ quyết định quy ước định dạng | Kiểm tra charset terminal và font riêng |

## 13. Tình huống chọn API

### Tình huống A: In một bảng số lên console

Dùng `System.out.printf(locale, format, args...)` nếu cần chiều rộng cố định, căn cột và số chữ số thập phân rõ ràng:

```java
System.out.printf(Locale.US, "%-12s %12s%n", "Item", "Amount");
System.out.printf(Locale.US, "%-12s %,12.2f%n", "Books", 1234.5);
```

Đây là **đoạn minh họa** (cần import `Locale`); mã không tự giải quyết vấn đề độ rộng hiển thị Unicode hoặc emoji theo terminal. Với bảng sử dụng locale có dấu tách nhóm Unicode, cần kiểm tra thiết bị hiển thị có xử lý đúng chiều rộng các glyph hay không.

### Tình huống B: Hiển thị hóa đơn theo vùng của người dùng

Dùng `NumberFormat.getCurrencyInstance(locale)` và đồng tiền được xác định. Định nghĩa cách làm tròn bằng `BigDecimal` theo chính sách nghiệp vụ **trước khi in**; locale điều khiển cách hiển thị, không quyết định người dùng được tính tiền theo đơn vị nào.

### Tình huống C: Parse số người dùng nhập trong console

Dùng `Scanner.useLocale(locale)` với `hasNextBigDecimal` / `nextBigDecimal` khi ngữ pháp token của Scanner đáp ứng yêu cầu. Nếu cần kiểm tra toàn chuỗi hoặc pattern chính xác, đọc một dòng rồi dùng `DecimalFormat` + `ParsePosition` và bước validate riêng.

### Tình huống D: Lưu tỷ lệ hoặc số lượng vào file cấu hình

Dùng biểu diễn không grouping có cú pháp do file format quy định. Khi ứng dụng khác đọc file, không bắt nó biết locale trên máy đã tạo file. Dữ liệu máy đọc cần tính ổn định; chuỗi đẹp cho người dùng và chuỗi chuẩn cho giao thức là hai kết quả khác nhau.

### Tình huống E: Số lớn có phần thập phân chính xác

Dùng `BigDecimal` và `DecimalFormat` với pattern và `RoundingMode` phù hợp. Không chuyển qua `double` chỉ để áp dụng `printf` nếu làm mất chữ số có ý nghĩa.

## 14. Tự kiểm tra

**Câu 1.** Cùng `1234567.5` được format bằng `String.format(Locale.US, "%,.2f", n)` và bằng `Locale.GERMANY` thì kết quả là gì?  
**Đáp án:** `1,234,567.50` và `1.234.567,50`.

**Câu 2.** Dấu `,` trong `%,.2f` có buộc output chứa dấu phẩy không?  
**Đáp án:** không. Đó là grouping flag trong cú pháp `Formatter`; ký tự nhóm xuất ra do locale quy định.

**Câu 3.** `DecimalFormat` theo `Locale.GERMANY` có cần `applyPattern("#.##0,00")` không?  
**Đáp án:** không. `applyPattern("#,##0.00")` dùng cú pháp pattern chuẩn; dấu hiển thị được locale thay đổi. `applyLocalizedPattern` mới nhận cú pháp localized.

**Câu 4.** Người dùng nhập `"1.234,50"` theo Đức. `new BigDecimal("1.234,50")` có parse thành 1234.5 không?  
**Đáp án:** không. Constructor `BigDecimal(String)` không dùng `Locale`. Cần parser phù hợp và kiểm tra đầy đủ input.

**Câu 5.** `NumberFormat.getPercentInstance(Locale.US)` nhận `0.125` thì hiển thị phần trăm bao nhiêu?  
**Đáp án:** `12.5%` khi formatter được cấu hình một chữ số thập phân.

**Câu 6.** Vì sao cần so sánh `ParsePosition.getIndex()` với `input.length()`?  
**Đáp án:** parser có thể chỉ parse tiền tố hợp lệ rồi dừng, để lại phần dữ liệu chưa xử lý. Tuy nhiên kiểm tra này chưa đủ để xác thực mọi ràng buộc grouping/nghiệp vụ.

**Câu 7.** Với hóa đơn giá trị `BigDecimal("12.345")` cần hai chữ số thập phân và `HALF_UP`, kết quả US/DE là gì?  
**Đáp án:** `12.35` / `12,35`, cùng một kết quả làm tròn về giá trị và khác cách biểu diễn.

**Câu 8.** Có nên dùng cùng một `DecimalFormat` rồi đổi pattern theo từng request ở nhiều thread?  
**Đáp án:** không, trừ khi bảo vệ quyền truy cập thích hợp. `DecimalFormat` mutable và không bảo đảm thread-safe.

## Kết luận

**`Locale` quyết định quy tắc biểu diễn và phân tích số theo ngôn ngữ/vùng; giá trị số vẫn là giá trị số.** Với output console ngắn gọn, chọn `printf(locale, ...)` hoặc `String.format(locale, ...)`; với mẫu phức tạp, grouping, làm tròn và tiền tệ, dùng `NumberFormat` / `DecimalFormat`. Với input, chọn `Scanner.useLocale` hoặc parser locale có kiểm tra toàn chuỗi và điều kiện nghiệp vụ. Luôn phân biệt **dấu phân cách hiển thị**, **cú pháp pattern**, **độ chính xác số**, **charset console** và **định dạng dữ liệu máy đọc**.

### Tài liệu Java SE 17

- [`Locale`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [`Formatter` và các flag định dạng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
- [`NumberFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`DecimalFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html), [`DecimalFormatSymbols`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html)
- [`Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html)
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [`RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)
