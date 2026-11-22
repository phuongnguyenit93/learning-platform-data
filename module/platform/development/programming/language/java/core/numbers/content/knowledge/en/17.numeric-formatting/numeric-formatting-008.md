# Locale, dấu thập phân, nhóm chữ số và dấu âm trong Java

## 1. Vì sao cùng một con số lại có nhiều cách viết?

Giá trị số và cách **hiển thị** số là hai khái niệm khác nhau. Ví dụ, một giá trị toán học có độ lớn một triệu hai trăm ba mươi bốn nghìn năm trăm sáu mươi bảy và 89 phần trăm có thể được trình bày như sau:

| Locale | Ví dụ hiển thị số âm | Dấu thập phân | Dấu nhóm chữ số |
| --- | --- | --- | --- |
| `Locale.US` (tiếng Anh, Hoa Kỳ) | `-1,234,567.89` | `.` | `,` |
| `Locale.GERMANY` (tiếng Đức, Đức) | `-1.234.567,89` | `,` | `.` |
| `Locale.FRANCE` (tiếng Pháp, Pháp) | `-1 234 567,89` | `,` | Dấu cách hẹp không ngắt dòng trong nhiều JDK hiện nay |
| `Locale.forLanguageTag("vi-VN")` (tiếng Việt, Việt Nam) | `-1.234.567,89` trên cấu hình CLDR phổ biến | `,` | `.` |

Dòng tiếng Pháp ở trên sử dụng dấu cách **U+202F NARROW NO-BREAK SPACE** giữa các nhóm. Nó có thể trông giống khoảng trắng ASCII `U+0020` nhưng **khác ký tự**. Quy tắc và ký hiệu locale có thể thay đổi theo phiên bản dữ liệu địa phương hóa hoặc bộ cung cấp locale của môi trường chạy; không dùng các ví dụ minh họa này như định dạng bất biến cho mọi máy và mọi phiên bản JDK.

Trong Java, `double amount = -1234567.89;` chứa một giá trị nhị phân; biến `amount` **không tự mang dấu phân cách `,` hoặc `.` của quốc gia**. Dấu thập phân, dấu nhóm, chữ số và quy ước âm xuất hiện khi ta chuyển số thành chuỗi hoặc phân tích một chuỗi do người dùng nhập.

Bài học này tập trung vào bốn yếu tố:

1. **Locale:** bộ quy tắc ngôn ngữ/vùng áp dụng khi trình bày và đọc chuỗi số.
2. **Dấu thập phân:** tách phần nguyên và phần lẻ.
3. **Dấu nhóm chữ số:** giúp người đọc phân biệt hàng nghìn, triệu...; **không thay đổi giá trị số**.
4. **Dấu âm/định dạng âm:** dấu `-`, đôi khi ký tự âm khác hoặc ngoặc đơn, tùy ngữ cảnh và pattern.

Mục tiêu là tạo ứng dụng hiểu đúng đầu vào của người dùng, hiển thị đúng ngôn ngữ và **không nhầm chuỗi dành cho giao diện với chuỗi trao đổi dữ liệu máy**.

## 2. `Locale` là gì và nên được chọn như thế nào?

Lớp `java.util.Locale` mô tả lựa chọn ngôn ngữ, vùng và một số đặc trưng văn hóa dùng cho chức năng địa phương hóa. Nó **không** chứa giá trị số và **không** tự thay đổi cách Java lưu `int`, `double` hay `BigDecimal`.

```java
import java.util.Locale;

Locale us = Locale.US;
Locale german = Locale.GERMANY;
Locale french = Locale.FRANCE;
Locale vietnamese = Locale.forLanguageTag("vi-VN");
```

Locale của chương trình có thể đến từ cài đặt môi trường hoặc được chỉ định tường minh. Ví dụ:

```java
Locale configured = Locale.getDefault();
```

`Locale.getDefault()` phụ thuộc máy/JVM. Vì vậy không nên dùng locale mặc định trong giao thức hay test mà kết quả phải ổn định giữa nhiều môi trường.

### Quy tắc chọn locale

- **Hiển thị cho người dùng:** lấy locale của tài khoản/giao diện, hoặc locale người dùng chọn. Không mặc định mọi người ở Việt Nam đều nhập số theo cùng một chuẩn nếu yêu cầu ứng dụng khác.
- **Đọc chuỗi người dùng nhập:** dùng đúng locale/quy ước mà ô nhập đã thông báo.
- **Định dạng theo chuẩn giao tiếp giữa máy:** dùng định dạng độc lập locale theo hợp đồng, chẳng hạn chữ số ASCII với dấu thập phân `.` và không có dấu nhóm; không dùng locale của máy chủ.
- **Unit test:** truyền `Locale` rõ ràng thay vì dựa vào `Locale.getDefault()`.

Các ký hiệu ở từng locale đến từ dữ liệu địa phương hóa. Một số thay đổi giữa các phiên bản JDK và CLDR có thể ảnh hưởng kết quả. Hãy test chính môi trường đích nếu ứng dụng yêu cầu chính xác ký tự định dạng, nhất là khi xử lý tài liệu tài chính, nhập liệu nghiêm ngặt hoặc so khớp chuỗi.

## 3. `NumberFormat` — API định dạng số theo locale

Lớp `java.text.NumberFormat` cung cấp các factory như `getNumberInstance(locale)`, `getIntegerInstance(locale)`, `getPercentInstance(locale)` và `getCurrencyInstance(locale)`.

Ví dụ định dạng số thực:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

us.setMinimumFractionDigits(2);
us.setMaximumFractionDigits(2);
de.setMinimumFractionDigits(2);
de.setMaximumFractionDigits(2);

System.out.println(us.format(-1234567.89)); // -1,234,567.89
System.out.println(de.format(-1234567.89)); // -1.234.567,89
```

Đây là các câu lệnh **minh họa trong một phương thức**, chưa phải chương trình độc lập. Phần 10 có một file Java 17 hoàn chỉnh.

Những cấu hình phổ biến:

| API | Tác dụng |
| --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Factory định dạng số thông thường |
| `setGroupingUsed(boolean)` | Bật/tắt dùng dấu nhóm chữ số |
| `setMinimumFractionDigits(int)` | Ít nhất bao nhiêu chữ số phần lẻ khi format |
| `setMaximumFractionDigits(int)` | Nhiều nhất bao nhiêu chữ số phần lẻ khi format |
| `setMinimumIntegerDigits(int)` | Số chữ số tối thiểu phần nguyên |
| `setRoundingMode(RoundingMode)` | Chọn quy tắc làm tròn khi định dạng, trên formatter hỗ trợ |
| `format(number)` | Biến số thành chuỗi trình bày |
| `parse(text)` | Đọc chuỗi theo định dạng được cấu hình, trả `Number` |

Nếu tắt grouping:

```java
NumberFormat formatter = NumberFormat.getNumberInstance(Locale.GERMANY);
formatter.setGroupingUsed(false);
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);

System.out.println(formatter.format(1234.5)); // 1234,50
```

**Định dạng không sửa giá trị đầu vào.** `setMaximumFractionDigits(2)` chỉ quyết định chuỗi xuất hiện bao nhiêu chữ số lẻ; nó không làm biến `double` hay `BigDecimal` đang giữ bị thay đổi.

### Format khác toán tử `+` nối chuỗi

Biểu thức `"value=" + someDouble` sử dụng biểu diễn mặc định của kiểu Java, không trình bày theo locale người dùng. Muốn localized number, hãy gọi `NumberFormat.format` rõ ràng.

`System.out.printf`/`String.format` cũng có overload nhận `Locale`:

```java
String us = String.format(Locale.US, "%,.2f", 1234567.89);
String de = String.format(Locale.GERMANY, "%,.2f", 1234567.89);

// us = "1,234,567.89"
// de = "1.234.567,89"
```

Đối với formatter `printf`, dấu `,` trong format specifier `%,.2f` là **cờ grouping**, không có nghĩa ký tự phân nhóm trong kết quả luôn là dấu phẩy ASCII. Ký hiệu thực tế phụ thuộc `Locale`.

## 4. `DecimalFormat` và `DecimalFormatSymbols`

`NumberFormat` có API chung; `java.text.DecimalFormat` cho phép kiểm soát pattern và ký hiệu. Với các locale phổ biến, `NumberFormat.getNumberInstance(locale)` thường trả một `DecimalFormat`, nhưng không nên ép kiểu tùy tiện khi không biết chính xác triển khai trả về.

Để tự tạo formatter theo pattern định nghĩa rõ:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

DecimalFormat fmt = new DecimalFormat("#,##0.00", symbols);
System.out.println(fmt.format(12345.678)); // 12.345,68
```

Ở đây **cú pháp pattern chuẩn** có dấu `,` biểu thị vị trí grouping và dấu `.` biểu thị ranh giới phần lẻ. Chúng **không** có nghĩa chuỗi đầu ra luôn dùng đúng hai ký tự đó; `DecimalFormatSymbols` chuyển chúng sang ký hiệu thực tế của locale.

### Pattern thường dùng

| Pattern | Ý nghĩa |
| --- | --- |
| `0` | Bắt buộc một chữ số nếu cần |
| `#` | Chữ số tùy chọn |
| `#,##0` | Có nhóm nghìn, ít nhất một chữ số phần nguyên |
| `#,##0.00` | Nhóm nghìn, đúng 2 chữ số phần lẻ khi định dạng |
| `#,##0.###` | Nhóm nghìn, tối đa 3 chữ số phần lẻ, không ép thêm số 0 |
| `#,##0.00;(#,##0.00)` | Pattern dương trước dấu `;`, pattern âm sau dấu `;` hiển thị trong ngoặc |

Ví dụ:

```java
DecimalFormat accounting = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(accounting.format(-1234.5)); // (1,234.50)
```

Nếu định nghĩa **negative subpattern**, pattern có thể tự áp dụng ngoặc hoặc dấu hiệu riêng cho giá trị âm. Đừng mặc định mọi chuỗi âm phải có dấu gạch ngang đứng đầu.

### Lấy ký tự phân cách và dấu âm

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.forLanguageTag("vi-VN"));

char decimal = symbols.getDecimalSeparator();
char grouping = symbols.getGroupingSeparator();
char minus = symbols.getMinusSign();
```

`getDecimalSeparator()`, `getGroupingSeparator()` và `getMinusSign()` trả các ký tự theo dữ liệu locale của JVM. Ví dụ trên nhiều JDK có dữ liệu CLDR hiện đại, locale `vi-VN` dùng dấu `,` cho thập phân và dấu `.` cho grouping.

Nếu cần debug ký tự ẩn hoặc dễ nhầm:

```java
System.out.printf(Locale.ROOT, "U+%04X%n", (int) grouping);
```

Cùng là **dấu âm**, ký tự U+002D HYPHEN-MINUS (`-`) và U+2212 MINUS SIGN (`−`) không phải cùng code point. Khi một số hiển thị không parse được, hãy xem ký hiệu thực tế thay vì chỉ nhìn mắt thường.

`DecimalFormatSymbols` có các setter như `setDecimalSeparator(char)`, `setGroupingSeparator(char)`, `setMinusSign(char)` để điều chỉnh biểu diễn **nếu ứng dụng có yêu cầu riêng**. Không thay thế mù quáng ký tự trong một chuỗi bất kỳ: dấu `.` có thể đang là thập phân trong một locale nhưng là dấu nhóm trong locale khác.

### `applyPattern` và `applyLocalizedPattern`

`DecimalFormat.applyPattern` nhận **cú pháp pattern chuẩn**; `applyLocalizedPattern` nhận pattern theo ký hiệu địa phương hóa. Trộn lẫn hai dạng có thể khiến dấu phân cách bị hiểu sai.

Nếu không cần pattern đặc thù, `NumberFormat.getNumberInstance(locale)` thường dễ bảo trì hơn tự tạo một bộ ký hiệu.

## 5. Dấu thập phân và dấu nhóm không thể suy đoán bằng cách đếm dấu

Xét các chuỗi:

| Chuỗi | Cách hiểu có thể có |
| --- | --- |
| `"1,234"` | Một nghìn hai trăm ba mươi bốn ở US, hoặc một phẩy hai ba bốn ở Germany |
| `"1.234"` | Một phẩy hai ba bốn ở US, hoặc một nghìn hai trăm ba mươi bốn ở Germany |
| `"1 234,50"` | Có thể biểu diễn grouping bằng dấu cách ở một số cách nhập, nhưng loại ký tự cách rất quan trọng |
| `"1 234,50"` | Dùng U+202F để nhóm; khác dấu cách ASCII |
| `"-1,234.50"` | Dạng US của một số âm |
| `"-1.234,50"` | Dạng Đức hoặc Việt Nam phổ biến của cùng giá trị âm |

Một hàm “chuẩn hóa” ngây thơ:

```java
text = text.replace(".", "").replace(",", ".");
```

chỉ tình cờ hoạt động với **một tập quy tắc đầu vào đã biết**, và sẽ biến `"1,234.50"` thành `"1.23450"` (sai khoảng một nghìn lần) nếu áp dụng không đúng locale.

Cách khác cũng sai là xóa mọi dấu cách, bởi trong Unicode có nhiều dạng khoảng trắng và dấu nhóm được dùng theo locale. Hơn nữa, chuỗi dữ liệu có thể chứa ký tự lạ cần **từ chối**, không nên im lặng biến đổi thành một giá trị số khác.

**Đừng suy đoán locale từ chuỗi nhập một cách tùy ý.** Hãy yêu cầu ứng dụng biết locale từ UI/config/schema; nếu hỗ trợ nhiều kiểu nhập, cần quy tắc xác định, mô tả mơ hồ và validation rõ ràng.

## 6. Parse số theo locale: `NumberFormat.parse` không giống `Double.parseDouble`

Parser primitive:

```java
Double.parseDouble("1.5"); // 1.5
```

thường dùng dấu `.` theo cú pháp Java, **không tự chuyển sang dấu `,` vì máy đang đặt locale Germany**. Chuỗi `"1,5"` không hợp lệ với `Double.parseDouble`.

Khi chuỗi đến từ giao diện người dùng kiểu Đức:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);
Number value = de.parse("1.234,50"); // 1234.5
```

`NumberFormat.parse` trả một `Number`, không mặc định là `Double` trong mọi trường hợp; kiểu thực tế phụ thuộc formatter và chuỗi. Giá trị `doubleValue()` có thể có sai số do biểu diễn nhị phân.

**Không trộn formatter của một locale với chuỗi của locale khác.** Ví dụ, formatter US gặp `"1.234,50"` có thể phân tích thành `1.234` rồi dừng ở dấu `,`/phần dư, thay vì ném lỗi. Nếu hệ thống chỉ kiểm tra “không ném exception”, nó có thể âm thầm nhận giá trị sai.

### Cảnh báo: có thể parse được *một phần* chuỗi

`NumberFormat.parse(String)` không bắt buộc tiêu thụ hết ký tự nguồn. Ví dụ với locale Germany:

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);

ParsePosition position = new ParsePosition(0);
Number result = parser.parse("1.234,50xyz", position);

System.out.println(result);              // 1234.5
System.out.println(position.getIndex()); // 8
```

Giá trị `1234.5` nhìn có vẻ parse thành công, nhưng chuỗi có thêm `"xyz"` và **chưa được đọc hết**. Muốn coi toàn bộ chuỗi là một số hợp lệ, phải kiểm tra `position.getIndex() == text.length()` và trường hợp parser trả `null`.

Hàm kiểm tra này chỉ đảm bảo **parser đã tiêu thụ hết**, không đảm bảo cách đặt grouping hợp chuẩn. `DecimalFormat` có thể parse khá dễ dãi với nhóm chữ số sai hoặc ký hiệu ở vị trí không chuẩn; nếu đầu vào cần nghiêm ngặt, xem mục 8.

## 7. Parse decimal thành `BigDecimal` để không làm tròn sang binary floating point

Khi nguồn là giá trị decimal cần bảo toàn chữ số (ví dụ dữ liệu tài chính hoặc các con số trong báo cáo), hãy cân nhắc `BigDecimal`.

Với đầu vào **đã chuẩn hóa sang decimal ASCII**:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("1234.50");
// Bảo toàn chính xác giá trị decimal 1234.50 và scale = 2.
```

Với đầu vào localized, `DecimalFormat` có thể được yêu cầu trả `BigDecimal`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);

parser.setParseBigDecimal(true);
String text = "1.234,50";
ParsePosition position = new ParsePosition(0);
Number n = parser.parse(text, position);

if (!(n instanceof BigDecimal amount)
        || position.getIndex() != text.length()) {
    throw new IllegalArgumentException("Invalid decimal input");
}

// amount là BigDecimal(1234.50), không phải một double gần đúng.
```

Đoạn trên sử dụng **pattern matching `instanceof` của Java 17**, hợp lệ từ Java 16 trở lên. `setParseBigDecimal(true)` là API của `DecimalFormat`, không phải của lớp cơ sở `NumberFormat`.

Ngoại lệ cần biết: parser có thể trả các đối tượng biểu diễn giá trị đặc biệt như vô cực, `NaN` hoặc `-0.0` theo các quy tắc riêng dù bật `parseBigDecimal`. Vì vậy kiểm tra `n instanceof BigDecimal` là cần thiết nếu hợp đồng chỉ cho phép **decimal hữu hạn có giá trị số**.

Đối với số âm kiểu `-0.00`, `BigDecimal` không bảo toàn khái niệm IEEE-754 *negative zero* như `double`; nếu dấu âm trên số 0 mang ý nghĩa nghiệp vụ, cần chính sách biểu diễn khác hoặc giữ chuỗi nguồn.

## 8. Xác thực đầu vào chặt chẽ hơn: locale, grouping và chữ số

### 8.1. Một parser `BigDecimal` an toàn cho toàn bộ chuỗi

Lưu phương thức này trong một class, với các import tương ứng:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

static BigDecimal parseLocalizedDecimal(
        String text, Locale locale) {

    if (text == null || locale == null) {
        throw new IllegalArgumentException("Missing input or locale");
    }

    DecimalFormat parser =
            (DecimalFormat) NumberFormat.getNumberInstance(locale);
    parser.setParseBigDecimal(true);

    ParsePosition pos = new ParsePosition(0);
    Number number = parser.parse(text, pos);

    if (!(number instanceof BigDecimal)
            || pos.getIndex() != text.length()) {
        throw new IllegalArgumentException("Invalid decimal: " + text);
    }

    return (BigDecimal) number;
}
```

Phương thức này:

- Không phụ thuộc locale mặc định: nhận `Locale` tường minh.
- Không âm thầm lấy giá trị `double` khi muốn decimal chính xác.
- Từ chối phần đuôi không parse được.
- Không chấp nhận `null` như một số.

**Giới hạn quan trọng:** nó chưa phải bộ parser **nghiêm ngặt về grouping**. Một số triển khai `DecimalFormat` vẫn có thể chấp nhận chuỗi có nhóm đặt sai vị trí; việc parser tiêu thụ hết chuỗi không chứng minh kiểu nhóm của chuỗi đó đúng mẫu dành cho người dùng.

### 8.2. Cần nghiêm ngặt dấu nhóm thì làm thế nào?

Nếu bài toán yêu cầu chỉ chấp nhận đúng mẫu (ví dụ `1.234,50` hợp lệ, nhưng `12.34,50` phải bị từ chối), hãy quy định chính xác cấu trúc nhóm của miền đầu vào. Các lựa chọn gồm:

1. **Bắt buộc định dạng nhập cố định** (ví dụ chỉ `1234.50` dạng ASCII không grouping) và parse bằng kiểu decimal chuẩn.
2. **Dùng regex được thiết kế theo một locale/định dạng cụ thể** để kiểm tra cấu trúc dấu nhóm, dấu âm và chữ số trước khi parse. Không dùng một regex duy nhất cho mọi locale.
3. **Dùng parser có chế độ strict phù hợp trên môi trường Java đích**, sau khi kiểm tra API/version, hoặc kiểm tra bổ sung theo hợp đồng ứng dụng.
4. **Nếu chấp nhận giá trị biểu diễn lại ở dạng canonical**, có thể format rồi so khớp theo quy tắc được công bố, nhưng cách này cũng cần xử lý leading zeros, trailing zeros, scale, negative zero, khoảng trắng và các dạng nhập tương đương.

Với ví dụ tiếng Đức đơn giản, quy tắc nhập có thể cho phép:

```text
1234,50
1.234,50
-1.234,50
```

nhưng từ chối:

```text
12.34,50       (nhóm không đúng 3 chữ số)
1,234.50       (đổi chỗ dấu decimal/grouping)
1.234,50xyz    (phần đuôi không phải số)
```

**Không nên quảng cáo `NumberFormat.parse` tự xác thực chặt cấu trúc**; parsing thường mang tính dung thứ để đọc đầu vào người dùng, không phải validator đầy đủ cho schema tài chính hoặc giao thức.

### 8.3. Unicode và các ký tự dễ nhầm

Các chuỗi có thể hiển thị gần giống nhau nhưng chứa những ký tự khác nhau:

- `-` U+002D so với `−` U+2212 cho dấu âm.
- ` ` U+0020 so với U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE cho dấu nhóm.
- `0`–`9` ASCII so với chữ số theo hệ chữ khác.
- `.` U+002E so với `,` U+002C; một số ký tự toàn chiều rộng có hình dạng tương tự.

Nếu cần kiểm tra vì sao cùng một chuỗi “trông giống nhau” mà parse ra khác, in code point thay vì chỉ so sánh ảnh hiển thị:

```java
String text = "1\u202F234,50";
text.codePoints().forEach(cp ->
        System.out.printf(Locale.ROOT, "U+%04X ", cp));
// U+0031 U+202F U+0032 U+0033 U+0034 U+002C U+0035 U+0030
```

`String.codePoints()` xử lý cả ký tự Unicode ngoài BMP; đây là cách quan sát ký tự chính xác hơn giả định mỗi chữ nhìn thấy là một ký tự `char`.

Không dùng `String.replace` theo kiểu “xóa mọi khoảng trắng, dấu phẩy, dấu chấm” để sửa các chuỗi không tin cậy. Nó có thể biến lỗi dữ liệu thành giá trị số khác mà không báo cho người dùng.

## 9. Dấu âm, ngoặc và số 0 âm

### 9.1. Dấu âm là thuộc tính của cách biểu diễn văn bản

Một số âm có thể hiển thị bằng dấu âm phía trước:

```text
-1,234.50
-1.234,50
```

hoặc, trong một số định dạng kế toán, bằng dấu ngoặc:

```text
(1,234.50)
```

`DecimalFormat` cho phép mô tả pattern âm rõ ràng:

```java
DecimalFormat accounting = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(accounting.format(-1234.5)); // (1,234.50)
```

Không thể suy ra giá trị âm chỉ bằng cách kiểm tra chuỗi có bắt đầu bằng `"-"` hay không. Pattern có thể dùng ngoặc, ký hiệu âm khác, thậm chí tiền tố/suffix tùy định dạng. Nếu người dùng có thể nhập dạng kế toán, parser phải hỗ trợ đúng hợp đồng.

### 9.2. Dấu âm ASCII không phải mọi ký tự trông như dấu trừ

Trong một số locale/cấu hình, ký tự U+2212 MINUS SIGN (`−`) có thể xuất hiện thay U+002D HYPHEN-MINUS (`-`). Hãy lấy `DecimalFormatSymbols.getMinusSign()` thay vì đoán. Cẩn thận khi copy số từ PDF, website hoặc tài liệu có dàn trang vì dấu âm có thể khác ký tự bàn phím thông thường.

### 9.3. `-0.0` khác `+0.0` ở dấu bit

Kiểu `double` có cả `+0.0` và `-0.0`:

```java
double negativeZero = -0.0;

System.out.println(negativeZero == 0.0); // true
System.out.println(1.0 / negativeZero);   // -Infinity
```

Định dạng theo locale có thể hiện dấu `-0,00` hoặc `-0.00` tùy cấu hình. Khi parsing vào `BigDecimal`, dấu âm của zero theo IEEE 754 không được bảo toàn như với `double`; cần ghi chú hoặc lưu riêng nếu nghiệp vụ yêu cầu phân biệt.

**Lưu ý về làm tròn khi format:** một giá trị âm rất nhỏ như `-0.0001` có thể được format ở độ chính xác hai chữ số phần lẻ thành dạng hiển thị `-0.00`. Chuỗi đó có thể khiến người dùng hiểu số đúng bằng 0; cần chọn độ chính xác hiển thị phù hợp với nghiệp vụ.

## 10. Demo Java 17 đầy đủ và đầu ra kiểm chứng

Lưu dưới tên `LocaleNumberDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberDemo {

    private static BigDecimal parseAll(String text, Locale locale) {
        DecimalFormat parser =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        parser.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number number = parser.parse(text, pos);

        if (!(number instanceof BigDecimal)
                || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid input");
        }
        return (BigDecimal) number;
    }

    public static void main(String[] args) {
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

        for (NumberFormat format : new NumberFormat[] { us, de }) {
            format.setMinimumFractionDigits(2);
            format.setMaximumFractionDigits(2);
        }

        System.out.println("US: " + us.format(-1234567.89));
        System.out.println("DE: " + de.format(-1234567.89));

        BigDecimal parsed = parseAll("1.234,50", Locale.GERMANY);
        System.out.println("DE parsed: " + parsed.toPlainString());

        DecimalFormat accounting = new DecimalFormat(
                "#,##0.00;(#,##0.00)",
                DecimalFormatSymbols.getInstance(Locale.US));
        System.out.println("Accounting: " + accounting.format(-1234.5));

        String withJunk = "1.234,50xyz";
        DecimalFormat parser =
                (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
        ParsePosition pos = new ParsePosition(0);
        Number partial = parser.parse(withJunk, pos);
        System.out.println("Partial value: " + partial);
        System.out.println("Consumed: " + pos.getIndex() + "/"
                + withJunk.length());

        System.out.println("US format: "
                + String.format(Locale.US, "%,.2f", 1234567.89));
        System.out.println("DE format: "
                + String.format(Locale.GERMANY, "%,.2f", 1234567.89));
    }
}
```

Biên dịch và chạy:

```bash
javac LocaleNumberDemo.java
java LocaleNumberDemo
```

Đầu ra trên một JDK 17 với dữ liệu locale tiêu chuẩn thường gặp:

```text
US: -1,234,567.89
DE: -1.234.567,89
DE parsed: 1234.50
Accounting: (1,234.50)
Partial value: 1234.5
Consumed: 8/11
US format: 1,234,567.89
DE format: 1.234.567,89
```

Đầu ra minh họa dùng US/Germany vì các ký hiệu cơ bản rõ ràng; nếu dùng `Locale.FRANCE` hoặc locale khác, **không nên hardcode dấu cách, dấu âm hay grouping** vào test xuyên phiên bản mà chưa kiểm tra dữ liệu CLDR/JDK đích.

### Vì sao ví dụ dùng `parseAll` thay vì `parse` trực tiếp?

`ParsePosition` ghi lại vị trí parse đã đi đến đâu. Khi chuỗi `"1.234,50xyz"` có 11 ký tự, parser Germany có thể đọc đúng `"1.234,50"` với độ dài 8 và để lại `"xyz"`. Nếu chỉ lấy `Number` và không kiểm tra vị trí, đầu vào sai bị chấp nhận.

Hàm `parseAll` loại tình huống này. Tuy nhiên, như đã giải thích ở mục 8, việc tiêu thụ hết chuỗi **không** đồng nghĩa nhóm hàng nghìn được validate nghiêm ngặt.

## 11. Phân biệt định dạng hiển thị và dữ liệu trao đổi

### Chuỗi cho người dùng

Với giao diện, hãy để formatter nhận `Locale` phù hợp:

```java
String display = NumberFormat
        .getNumberInstance(Locale.forLanguageTag("vi-VN"))
        .format(1234567.89);
```

Chuỗi `display` dùng để **hiển thị**; không coi nó là định dạng ổn định để lưu DB hoặc làm chữ ký số.

### Chuỗi cho máy hoặc giao thức cố định

Nếu hợp đồng yêu cầu decimal ASCII với dấu `.` và không grouping, dùng biểu diễn độc lập locale được quy định:

```java
String decimal = new BigDecimal("1234567.89").toPlainString();
// "1234567.89"

String floating = Double.toString(1234567.89);
// Dùng cú pháp số thực Java với '.' chứ không dùng grouping địa phương.
```

Chú ý `Double.toString` là biểu diễn thập phân có thể round-trip về cùng giá trị `double`, không bảo đảm mọi chữ số decimal ban đầu được lưu chính xác. Nếu cần tiền hay decimal chính xác, giữ nguồn trong `BigDecimal` với scale/quy tắc làm tròn phù hợp.

Giao thức máy có thể có chuẩn riêng (ví dụ JSON number không chấp nhận các giá trị không hữu hạn như `NaN` và `Infinity` theo chuẩn JSON thông thường). Hãy tuân thủ **đúng grammar của giao thức**, không dùng chuỗi mà người dùng thấy trên màn hình thay cho serialization chuẩn.

### Không dựa vào locale mặc định của server

```java
// Dễ thay đổi tùy máy chạy:
String unpredictable = String.format("%,.2f", 1234.5);

// Ổn định hơn khi giao diện đã biết locale:
String explicit = String.format(Locale.US, "%,.2f", 1234.5);
```

Nếu phần mềm chạy trên nhiều container/server, sử dụng locale mặc định khác nhau có thể dẫn đến báo cáo, test snapshot, CSV và các chuỗi lưu trữ sai khác mà không có thay đổi logic nghiệp vụ.

CSV còn có dấu phân tách cột riêng. Nếu định dạng số sử dụng dấu `,` làm dấu thập phân hoặc grouping, cần quoting và parsing CSV đúng chuẩn; đừng tự xây CSV bằng cách nối thẳng các chuỗi số localized bằng dấu phẩy.

## 12. Sai lầm thường gặp

1. **Dùng `Double.parseDouble("1,5")` rồi kỳ vọng kết quả `1.5`.** API này không phụ thuộc locale, thường yêu cầu dấu `.` theo cú pháp số thực Java. Dùng `NumberFormat` với locale phù hợp cho dữ liệu giao diện.
2. **Nhìn thấy `"1,234"` và suy ra chắc là `1234`.** Ở một số locale dấu phẩy là decimal. Cần có locale hoặc hợp đồng đầu vào.
3. **Thay mọi dấu `.` bằng rỗng rồi `,` bằng `.`.** Dễ làm sai chuỗi theo US hoặc chuỗi có dấu nhóm khác.
4. **Không đặt `Locale` khi format trong ứng dụng đa quốc gia.** Kết quả phụ thuộc máy chạy thay vì lựa chọn người dùng.
5. **Dùng `NumberFormat.parse` nhưng không xác nhận đọc hết chuỗi.** Parser có thể trả số hợp lệ từ một tiền tố, bỏ lại ký tự rác.
6. **Coi parse hết chuỗi là đã validate grouping.** `DecimalFormat` có thể nhận cách nhóm không đúng; cần quy tắc kiểm tra định dạng nếu nghiệp vụ yêu cầu nghiêm ngặt.
7. **Bỏ qua dấu cách Unicode.** U+202F và U+0020 nhìn tương tự nhưng không phải cùng ký tự.
8. **Coi mọi dấu âm là dấu `-` ASCII đứng đầu.** Locale hoặc pattern kế toán có thể dùng U+2212 hoặc ngoặc.
9. **Tự viết `"."` và `","` trong mẫu output mà không hiểu pattern.** Trong `DecimalFormat` pattern chuẩn, ký hiệu là placeholder; ký tự thực tế do `DecimalFormatSymbols` quyết định.
10. **Nghĩ format hai chữ số lẻ làm thay đổi dữ liệu số.** Format làm tròn **chuỗi hiển thị**, không đổi đối tượng `BigDecimal` hoặc giá trị số gốc.
11. **Dùng `double` để lưu decimal tiền chỉ vì đã parse theo locale.** Vẫn có vấn đề chính xác nhị phân. Dùng `BigDecimal` khi cần decimal exact.
12. **Giữ formatter `DecimalFormat` dùng chung giữa nhiều thread và sửa cấu hình trong lúc format.** `NumberFormat`/`DecimalFormat` là mutable và không được bảo đảm thread-safe; dùng instance riêng hoặc đồng bộ hóa thích hợp.
13. **So sánh bằng chuỗi đã format.** Hai giá trị khác nhau có thể cùng format thành một chuỗi sau làm tròn; dùng so sánh số và quy tắc tolerance/rounding theo nghiệp vụ.
14. **Dùng kết quả format localized để tạo khóa, checksum hoặc giao thức API.** Locale có thể thay đổi cách viết; dùng canonical representation rõ ràng.
15. **Bỏ qua dấu âm khi giá trị gần 0.** `-0.0` và số âm nhỏ bị format thành `-0,00` có thể mang thông tin dấu; cần chính sách hiển thị phù hợp.
16. **Cho rằng `NumberFormat` format/parse luôn đối xứng tuyệt đối cho mọi số.** Việc giới hạn chữ số lẻ, làm tròn, grouping và parser dễ dãi có thể khiến round-trip không phục hồi nguyên vẹn giá trị ban đầu.

## 13. Bài tập tự kiểm tra

**Câu 1.** Vì sao `"1.234,56"` có thể có nghĩa một nghìn hai trăm ba mươi bốn phẩy năm sáu trong `Locale.GERMANY`, nhưng không phải cùng ý nghĩa trong `Locale.US`?

**Đáp án:** Germany dùng dấu `.` làm grouping và dấu `,` làm decimal; US dùng ngược lại. Không thể suy ra giá trị chính xác chỉ từ chuỗi nếu chưa biết locale.

**Câu 2.** Muốn hiển thị `1234567.89` theo tiếng Đức với hai chữ số lẻ và nhóm nghìn, dùng API nào?

**Đáp án:** `NumberFormat.getNumberInstance(Locale.GERMANY)`, cấu hình `setMinimumFractionDigits(2)` và `setMaximumFractionDigits(2)`, rồi `format`. Kết quả minh họa: `"1.234.567,89"`.

**Câu 3.** Vì sao `NumberFormat.getNumberInstance(Locale.GERMANY).parse("1.234,50xyz")` có thể không ném exception?

**Đáp án:** Parser có thể chấp nhận một tiền tố đúng và dừng ở phần đuôi. Dùng `ParsePosition`, yêu cầu `pos.getIndex() == text.length()`, và kiểm tra kết quả không `null`.

**Câu 4.** Sau khi parse toàn bộ chuỗi thành `BigDecimal` bằng `DecimalFormat.setParseBigDecimal(true)`, có chắc dấu nhóm đúng cấu trúc chưa?

**Đáp án:** Chưa. Parse tiêu thụ hết không đồng nghĩa validation nghiêm ngặt grouping. Nếu cần kiểm tra đúng ba chữ số mỗi nhóm, định nghĩa validator tương ứng với locale/quy ước input.

**Câu 5.** Tại sao `new BigDecimal("1234.50")` phù hợp hơn `Double.parseDouble("1234.50")` nếu nghiệp vụ phải giữ đúng decimal scale và giá trị?

**Đáp án:** `BigDecimal(String)` giữ đúng số thập phân và scale của chuỗi; `double` là nhị phân gần đúng, không phải mọi decimal đều biểu diễn chính xác.

**Câu 6.** `"1 234,50"` và `"1 234,50"` có khác nhau không, dù nhìn khá giống?

**Đáp án:** Có thể khác: ký tự nhóm ở chuỗi đầu là U+202F, trong chuỗi thứ hai là khoảng trắng ASCII U+0020. Cần quan sát code point và cấu hình locale/parser, không đoán bằng mắt.

**Câu 7.** Vì sao định dạng âm `"(" + number + ")"` không nên được parse bằng cách chỉ tìm dấu `-` ở đầu?

**Đáp án:** Dạng kế toán dùng ngoặc biểu thị âm mà không có dấu `-` đầu chuỗi. Formatter/parser phải dùng cùng pattern và hợp đồng dữ liệu.

**Câu 8.** Có nên gọi `NumberFormat.format` theo locale người dùng để tạo chuỗi gửi trong REST API hay lưu số vào cơ sở dữ liệu không?

**Đáp án:** Thường không. Cần dùng schema và serialization chuẩn, độc lập locale. Chuỗi localized chỉ dành cho hiển thị hoặc trường nhập văn bản mà hợp đồng ghi rõ locale.

**Câu 9.** `NumberFormat` có thể được lưu làm một singleton mutable dùng cho tất cả request và đổi locale/precision theo từng request không?

**Đáp án:** Không nên. `NumberFormat`/`DecimalFormat` mutable, không có bảo đảm thread-safety. Tạo formatter riêng cho tác vụ hoặc quản lý truy cập và cấu hình cẩn thận.

**Ghi nhớ:** Locale quyết định cách số được viết và đọc cho con người: ký hiệu thập phân, nhóm chữ số, dấu âm và có thể cả bộ chữ số. Dùng `NumberFormat`/`DecimalFormat` với `Locale` tường minh; giữ số trong kiểu phù hợp; validate chuỗi nhập đủ chặt; đừng nhầm biểu diễn hiển thị với định dạng lưu trữ hay trao đổi máy.