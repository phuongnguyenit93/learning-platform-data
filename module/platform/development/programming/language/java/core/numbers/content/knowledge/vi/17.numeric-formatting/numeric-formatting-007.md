# DecimalFormat, pattern và DecimalFormatSymbols trong Java

## 1. Mục tiêu: định dạng một giá trị số không đồng nghĩa thay đổi giá trị đó

Trong Java Core — Numbers, một giá trị số có thể phải xuất hiện khác nhau tùy quốc gia, hệ thống hoặc yêu cầu giao diện:

```text
Cùng giá trị số: 1234567.5

Theo quy ước Hoa Kỳ:     1,234,567.50
Theo quy ước Đức:       1.234.567,50
Định dạng đặc biệt:     1^234^567|50
```

`java.text.DecimalFormat` thực hiện phần lớn công việc định dạng kiểu này. Nó cho phép chọn số chữ số, nhóm hàng nghìn, dấu âm, hậu tố phần trăm, dạng khoa học hoặc tiền tệ. Chuỗi **pattern** mô tả bố cục, còn `java.text.DecimalFormatSymbols` quyết định những ký hiệu thực sự được dùng để hiển thị, chẳng hạn dấu phân cách thập phân và dấu tách nhóm.

**Điều quan trọng nhất:** định dạng một `double`/`long`/`BigDecimal` thành `String` **không tự sửa giá trị số đang lưu**. Phép format có thể làm tròn phần **hiển thị**, còn cách parse ngược một chuỗi thành số là một hoạt động riêng có hợp đồng và rủi ro riêng.

Sau bài này, bạn có thể:

1. Dùng `DecimalFormat` để định dạng số bằng những pattern như `#,##0.00` và `0.###`.
2. Giải thích ký hiệu `0`, `#`, `.`, `,`, `;`, `%`, `‰`, `E`, `¤` và cơ chế quote `'...'`.
3. Hiểu sự khác biệt giữa **pattern không bản địa hóa** và **các ký hiệu đã bản địa hóa**, biết dùng `applyPattern` và `applyLocalizedPattern` đúng ngữ cảnh.
4. Tạo `DecimalFormatSymbols` từ một `Locale` cụ thể và tự điều chỉnh dấu tách nhóm, dấu thập phân, dấu trừ, đơn vị tiền tệ nếu cần.
5. Kiểm soát làm tròn bằng `RoundingMode`, biết lợi ích của `BigDecimal` khi cần làm tròn thập phân chính xác.
6. Phân tích chuỗi với `parse`, `ParsePosition`, `setParseBigDecimal(true)` và hiểu nguy cơ **parse chỉ một tiền tố**.
7. Phân biệt định dạng trình bày, định dạng trao đổi dữ liệu, dữ liệu tiền tệ và input theo locale.
8. Biết tránh sử dụng chung một `DecimalFormat` mutable giữa các luồng mà không đồng bộ.

Các chương trình hoàn chỉnh sử dụng **Java 17+**; lệnh biên dịch/chạy và stdout được cung cấp để tự kiểm chứng.

## 2. Vai trò của NumberFormat, DecimalFormat, DecimalFormatSymbols và Locale

Bốn khái niệm liên quan nhưng không đồng nhất:

| Thành phần | Chức năng |
| --- | --- |
| `NumberFormat` | API tổng quát định dạng/phân tích số có quan tâm `Locale`; cung cấp factory cho số thường, số nguyên, tiền tệ, phần trăm |
| `DecimalFormat` | Implementation có **pattern** và các thuộc tính chi tiết: số chữ số, grouping, rounding, multiplier, phần âm, scientific notation |
| `DecimalFormatSymbols` | Bộ ký hiệu: decimal separator, grouping separator, zero digit, dấu âm, %, ‰, ký hiệu tiền tệ, NaN, Infinity... |
| `Locale` | Chọn quy ước ngôn ngữ/vùng; ảnh hưởng symbols, kiểu định dạng mặc định và một số dữ liệu liên quan |

### 2.1. Cách bắt đầu với NumberFormat

Nếu chỉ muốn số được định dạng theo `Locale`, thường nên dùng factory:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat formatter = NumberFormat.getNumberInstance(Locale.US);
String result = formatter.format(1234567.5);
```

Đây là một **mảnh mã minh họa**; đặt trong phương thức hoặc class để chạy. Dùng factory cho phép Java lấy định dạng phù hợp với locale, thay vì bạn tự phỏng đoán dấu phân cách.

**Không mặc định cast vô điều kiện** kết quả của `NumberFormat.getNumberInstance(locale)` thành `DecimalFormat`: nhiều provider thường trả `DecimalFormat`, nhưng API factory không bảo đảm luôn trả đúng subclass ấy. Nếu cần tính năng chỉ có trong `DecimalFormat`:

```java
NumberFormat nf = NumberFormat.getNumberInstance(Locale.US);
if (nf instanceof java.text.DecimalFormat df) {
    df.applyPattern("#,##0.00");
}
```

Đoạn dùng **pattern matching for instanceof** hợp lệ trong Java 17. Nếu API nghiệp vụ bắt buộc có đúng `DecimalFormat`, cũng có thể khởi tạo `new DecimalFormat(pattern, symbols)` với bộ symbols chọn tường minh, như trong những ví dụ tiếp theo.

### 2.2. Không ngầm phụ thuộc locale mặc định

`new DecimalFormat("#,##0.00")` lấy bộ ký hiệu của locale mặc định cho định dạng. Cùng chương trình có thể in `1,234.50` trên máy này và `1.234,50` trên máy khác. Để tài liệu, test và giao thức ổn định, chọn `Locale` hoặc `DecimalFormatSymbols` một cách rõ ràng.

Ví dụ:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormatSymbols us =
        DecimalFormatSymbols.getInstance(Locale.US);
DecimalFormat moneyLike = new DecimalFormat("#,##0.00", us);
```

Tên biến `moneyLike` chỉ nói **cách hiển thị hai số lẻ**. Pattern `#,##0.00` không tự gắn đơn vị tiền, mã ISO, luật thuế hoặc chính sách làm tròn tiền tệ.

## 3. Pattern là gì? Phân biệt ký tự cấu trúc và ký tự được in ra

`DecimalFormat` có **pattern không bản địa hóa** sử dụng các ký hiệu cấu trúc chuẩn. Pattern `#,##0.00` không có nghĩa lúc nào chuỗi kết quả cũng chứa dấu phẩy và dấu chấm y hệt; những vị trí này được thay bằng ký hiệu phù hợp của `DecimalFormatSymbols`.

Bảng ký hiệu quan trọng:

| Ký hiệu | Vai trò trong pattern không localized | Ví dụ ý nghĩa |
| --- | --- | --- |
| `0` | Chữ số **bắt buộc**, thêm số 0 khi thiếu | `0000` định dạng 12 thành `0012` |
| `#` | Chữ số **tùy chọn**, không thêm zero không cần thiết | `0.##` có tối đa 2 số lẻ |
| `.` | Vị trí dấu thập phân | Hiển thị `.`, `,` hoặc ký hiệu khác theo symbols |
| `,` | Vị trí chia nhóm phần nguyên | Hàng nghìn hoặc kích thước nhóm tùy pattern/cấu hình |
| `;` | Phân tách pattern cho số dương và số âm | `0.00;(0.00)` |
| `%` | Phần trăm; nhân 100 khi format, chia 100 khi parse theo multiplier | `0.0%` |
| `‰` | Phần nghìn (per mille); multiplier 1000 | `0.0‰` |
| `E` | Dạng khoa học/exponential notation | `0.00E0` |
| `¤` | Ký hiệu tiền tệ theo symbols/locale | `¤#,##0.00` |
| `¤¤` | Mã tiền tệ quốc tế (ví dụ USD) | `¤¤ #,##0.00` |
| `'` | Dùng để quote văn bản/ký hiệu đặc biệt | `'Total:' #,##0.00` |

Trong Java string literal, phần lớn các pattern ở bảng viết trực tiếp như `"#,##0.00"` hoặc `"0.0%"`. Ký hiệu `‰` là Unicode U+2030, có thể viết trong Java source dưới dạng `"\u2030"` nếu cần tránh phụ thuộc cách lưu file nguồn. Ký hiệu tiền tệ `¤` là U+00A4.

### 3.1. `0` và `#`: bắt buộc hay tùy chọn

Cho số `12.5`:

```text
Pattern        Kết quả với symbols Locale.US
0.00           12.50
0.##           12.5
0000.000       0012.500
```

Với `0.00`, định dạng hiển thị **đúng hai chữ số** sau dấu thập phân. Với `0.##`, có **tối đa hai chữ số**, không bắt buộc giữ zero ở cuối. Với `0000.000`, phần nguyên được đệm zero tới bốn chữ số và phần lẻ tới ba chữ số.

**Lưu ý:** `DecimalFormat` không phải cách lưu số thành chuỗi với độ chính xác vô hạn. Nếu format chỉ cho hai chữ số sau dấu thập phân, những chữ số còn lại không xuất hiện trong kết quả và có thể đã được **làm tròn ở bước biểu diễn chuỗi**.

### 3.2. Grouping và pattern `#,##0.00`

`#,##0.00` có ý nghĩa:

- Hiển thị nhóm hàng nghìn trong phần nguyên.
- Có ít nhất một chữ số nguyên.
- Có đúng hai chữ số phần lẻ.
- Dùng dấu phân cách do symbols quy định.

Ví dụ:

```java
DecimalFormat usFormatter =
        new DecimalFormat("#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(usFormatter.format(1234567.5));
// 1,234,567.50
```

Dấu phẩy **trong pattern** là placeholder cho grouping. Dấu phẩy **trong kết quả US** là glyph được `DecimalFormatSymbols` cung cấp. Hai việc này trùng ký tự trong `Locale.US` nhưng không bắt buộc trùng ở locale khác.

### 3.3. Group size và giới hạn chữ số

Bạn cũng có thể thay đổi thuộc tính bằng method:

```java
DecimalFormat df = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

df.setGroupingUsed(true);
df.setGroupingSize(4);
df.setMinimumFractionDigits(2);
df.setMaximumFractionDigits(2);
```

Với `setGroupingSize(4)`, các nhóm xuất hiện từ phải sang trái theo bốn chữ số trong phần nguyên. Cần hiểu đây là **độ rộng nhóm hiển thị**, không làm đổi giá trị số. Nếu tạo pattern với nhiều dấu phẩy grouping, quy tắc `DecimalFormat` không phải hệ thống tổng quát tùy ý cho mọi thứ bậc nhóm địa phương; tài liệu mô tả cách pattern được diễn giải và dấu grouping có ảnh hưởng chính là vùng cuối gần chữ số nguyên.

Đừng xem `setMaximumFractionDigits` là một bộ kiểm tra input: giới hạn chữ số hiển thị không tự bảo đảm người dùng chỉ nhập tối đa số chữ số đó.

## 4. Hai phần pattern: số dương và số âm

Pattern có thể chứa hai subpattern, ngăn bằng `;`:

```text
#,##0.00;(#,##0.00)
```

Ví dụ kết quả `Locale.US`:

```text
 1234.5 ->  1,234.50
-1234.5 -> (1,234.50)
```

Điều này phù hợp một số báo cáo kế toán muốn viết **số âm trong ngoặc**. Nếu không khai báo subpattern âm, Java thường dùng subpattern dương với dấu âm đứng trước.

Chú ý: theo hợp đồng `DecimalFormat`, subpattern âm chủ yếu quyết định **prefix/suffix âm**; cấu trúc chữ số tối thiểu/tối đa và phần phân nhóm của pattern dương được sử dụng chung. Vì vậy không nên kỳ vọng khai báo hai dãy chữ số hoàn toàn khác nhau cho positive/negative trong cùng pattern sẽ tạo hai bộ precision độc lập.

Khi parse lại số âm có ngoặc, phải sử dụng đúng một formatter và pattern phù hợp. Không dùng quy tắc tự cắt dấu trừ rồi gắn lại nếu dữ liệu có tiền tố/hậu tố đã được bản địa hóa.

## 5. Prefix, suffix và quote văn bản

Pattern có thể đính kèm từ hoặc ký hiệu:

```java
DecimalFormat df = new DecimalFormat(
        "'Total:' #,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(1234.5));
// Total: 1,234.50
```

Cặp dấu quote `'...'` buộc Java hiểu `Total:` là chuỗi ký tự literal trong prefix, chứ không là ký hiệu pattern. Nếu cần một ký tự apostrophe literal trong phần prefix/suffix, thường viết hai dấu quote liên tiếp `''` theo quy tắc pattern.

**Đừng ghép đơn vị tiền tệ, giá trị và dấu phân cách bằng phép nối chuỗi tùy tiện** nếu hệ thống đa locale: một số locale đặt ký hiệu trước, số khác đặt sau; khoảng trắng và quy ước ký hiệu cũng có thể khác. Với nội dung tiền tệ, hãy dùng factory currency hoặc pattern có `¤` và currency metadata phù hợp.

## 6. Phần trăm và phần nghìn: thay đổi multiplier

Một lỗi thường gặp là nghĩ `0.0%` chỉ “thêm ký hiệu %”. Thực tế `%` còn **nhân giá trị với 100 khi format**.

```java
DecimalFormat percent = new DecimalFormat("0.0%",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(percent.format(0.256)); // 25.6%
```

Giá trị input `0.256` được biểu diễn thành `25.6%`, đúng vì `0.256×100=25.6`. Nếu input đã có giá trị 25.6 đại diện “25.6%”, đem format bằng pattern `0.0%` sẽ nhân thêm 100 lần; dữ liệu đầu vào phải dùng một quy ước thống nhất.

Ký hiệu `‰` (U+2030) thể hiện **per mille**, nhân giá trị với **1000** khi format:

```java
DecimalFormat perMille = new DecimalFormat(
        "0.0\u2030",
        DecimalFormatSymbols.getInstance(Locale.US));
```

Mảnh code này hiển thị giá trị `0.256` tương ứng `256.0‰` khi symbol per-mille theo bộ US là `‰`. Java source sử dụng Unicode escape để tệp có thể lưu pattern độc lập với bàn phím nhập ký hiệu.

Khi parse chuỗi có hậu tố phần trăm bằng formatter percent, **multiplier được áp dụng ngược lại**. Chẳng hạn `percent.parse("25.6%")` trả giá trị số gần `0.256` (kiểu cụ thể có thể là `Double` tùy parse config). Không tự chia 100 một lần nữa sau khi parser đã xử lý multiplier.

## 7. Scientific notation: `E` trong pattern

`E` phân tách phần significand và phần mũ thập phân của **chuỗi hiển thị**:

```java
DecimalFormat scientific = new DecimalFormat("0.00E0",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(scientific.format(12345));
// 1.23E4
```

`0.00E0` yêu cầu:

- Một chữ số bắt buộc trước dấu thập phân trong phần significand.
- Hai chữ số phần lẻ.
- Chữ `E` và ít nhất một chữ số phần mũ.

`DecimalFormat` có các quy tắc riêng cho kiểu scientific/engineering notation khi pattern có số lượng chữ số nguyên khác nhau, chẳng hạn `##0.###E0`. Không nên tự chia input cho 10ⁿ rồi nối chữ `"E"` khi Java đã hỗ trợ format exponent và ký hiệu exponent có thể được `DecimalFormatSymbols` tùy chỉnh.

**Lưu ý hai loại E:** chữ `e/E` trong `Double.parseDouble("1.23e4")` là cú pháp **đọc một chuỗi số**, còn `E` trong pattern `"0.00E0"` là **chỉ thị cách xuất chuỗi**. Không hoán đổi chúng như thể `DecimalFormat` đọc source literal của Java.

## 8. Ký hiệu tiền tệ: `¤`, `¤¤` và Currency

`DecimalFormat` hiểu:

- `¤` (U+00A4) là vị trí ký hiệu tiền tệ của `DecimalFormatSymbols`, ví dụ `$` cho USD trong ngữ cảnh Hoa Kỳ.
- `¤¤` là vị trí mã tiền tệ quốc tế, ví dụ `USD`.
- Pattern tiền tệ có thể sử dụng **monetary decimal separator** khác decimal separator thường nếu locale/symbols quy định như vậy.

Ví dụ:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Currency;
import java.util.Locale;

DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
symbols.setCurrency(Currency.getInstance("USD"));

DecimalFormat formatter =
        new DecimalFormat("\u00A4#,##0.00", symbols);

String formatted = formatter.format(1234.5);
```

Đây là mảnh code trong phương thức Java. Với thông số `Locale.US` và USD theo JDK thông thường, kết quả có dạng **`$1,234.50`**. Với `¤¤`, kết quả biểu thị mã như `USD` thay vì ký hiệu đồng tiền ngắn.

**Không dùng `¤` như phép chuyển đổi tiền tệ.** Nếu input là 1234.5 đơn vị tiền X, việc đổi symbol thành USD **không** tính tỷ giá và **không** thay đổi số lượng tiền. Ứng dụng phải biết đồng tiền thực của giá trị và thực hiện chuyển đổi tỷ giá riêng nếu cần.

Đối với format tiền tệ theo locale mặc định, `NumberFormat.getCurrencyInstance(locale)` thường thích hợp hơn tự vẽ mọi pattern. Nhưng với yêu cầu mã ISO cố định, ký hiệu và số lẻ, hãy kiểm soát `Currency`, locale và rounding theo chuẩn nghiệp vụ.

## 9. DecimalFormatSymbols: tách mẫu số và glyph hiển thị

Lấy cùng pattern `#,##0.00` nhưng dùng ký hiệu cho hai locale:

```java
DecimalFormat us = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

DecimalFormat de = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
```

Với giá trị `1234567.5`:

```text
US: 1,234,567.50
DE: 1.234.567,50
```

Pattern **không đổi**. Bộ symbols khác nhau nên chuỗi kết quả đổi.

Các phương thức thường dùng của `DecimalFormatSymbols`:

| Method | Ý nghĩa |
| --- | --- |
| `getDecimalSeparator()` / `setDecimalSeparator(char)` | Dấu thập phân thường |
| `getGroupingSeparator()` / `setGroupingSeparator(char)` | Dấu tách nhóm |
| `getMinusSign()` / `setMinusSign(char)` | Dấu số âm |
| `getZeroDigit()` / `setZeroDigit(char)` | Chữ số zero gốc cho hệ chữ số localized |
| `getPercent()` / `setPercent(char)` | Dấu phần trăm |
| `getPerMill()` / `setPerMill(char)` | Dấu phần nghìn |
| `getCurrencySymbol()` / `setCurrencySymbol(String)` | Ký hiệu tiền tệ hiển thị |
| `getInternationalCurrencySymbol()` | Mã tiền tệ quốc tế |
| `getExponentSeparator()` / `setExponentSeparator(String)` | Ký hiệu phần mũ |
| `getNaN()` / `setNaN(String)` | Biểu diễn NaN |
| `getInfinity()` / `setInfinity(String)` | Biểu diễn vô cực |

Một số API còn có monetary grouping separator/monetary decimal separator. Nếu thay ký hiệu cho currency, hãy xem kỹ contract và sự nhất quán của nhiều thuộc tính liên quan thay vì chỉ đổi một dấu thập phân.

### 9.1. Tự định nghĩa dấu phân cách

```java
DecimalFormatSymbols custom =
        DecimalFormatSymbols.getInstance(Locale.US);
custom.setGroupingSeparator('^');
custom.setDecimalSeparator('|');

DecimalFormat df = new DecimalFormat("#,##0.00", custom);
System.out.println(df.format(1234567.5));
// 1^234^567|50
```

**Ý nghĩa:** `#,##0.00` vẫn dùng `,` và `.` làm **placeholders trong pattern**. Khi hiển thị, ký tự nhóm trở thành `^`, dấu thập phân trở thành `|`. Đây là cách kiểm chứng trực quan sự khác nhau giữa pattern và symbols.

Nếu bạn tùy chỉnh để cho **cùng một ký tự** làm dấu thập phân và dấu nhóm, hoặc dấu âm trùng chữ số, việc parse sẽ trở nên mơ hồ. `DecimalFormat`/`DecimalFormatSymbols` không tự suy ra ý định trong mọi cấu hình không hợp lý. Thiết kế bộ symbols sao cho có thể phân biệt được các thành phần.

## 10. applyPattern và applyLocalizedPattern không cùng ngữ nghĩa

`DecimalFormat.applyPattern(String)` nhận **pattern chuẩn không localized**: `.` là placeholder decimal, `,` là placeholder grouping. Nó vẫn dùng `DecimalFormatSymbols` hiện có để hiển thị glyph theo locale.

`DecimalFormat.applyLocalizedPattern(String)` nhận **pattern đã bản địa hóa**, trong đó ký hiệu decimal/grouping trong **chuỗi pattern đầu vào** là những ký hiệu phù hợp với bộ symbols của formatter.

Ví dụ với `Locale.GERMANY`:

```java
DecimalFormat df = new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));

df.applyPattern("#,##0.00");          // non-localized
df.applyLocalizedPattern("#.##0,00"); // localized theo ký hiệu Đức
```

Cả hai pattern trên mô tả cùng dạng định dạng và đều có thể cho chuỗi `1.234.567,50` khi format `1234567.5`. Nếu lấy `"#.##0,00"` rồi đưa vào `applyPattern`, Java **không** coi dấu `.` đó là nhóm theo cách đọc của người Đức; nó dùng quy tắc cấu trúc **không localized**, nên có thể lỗi hoặc cho nghĩa khác.

Hai method đi kèm là `toPattern()` và `toLocalizedPattern()` để lấy pattern ở hai dạng biểu diễn tương ứng. Điều này quan trọng khi **lưu cấu hình**: hãy ghi rõ file đang lưu pattern chuẩn hay pattern localized, không đổi locale khi đọc lại mà quên chuyển cú pháp.

### 10.1. Giao diện cho người dùng nhập pattern

Nếu giao diện cho người dùng Đức gõ `#.##0,00`, bạn có thể cần `applyLocalizedPattern`, vì người dùng đang viết theo ký hiệu Đức. Nếu file config nội bộ do hệ thống sinh ra dùng `#,##0.00`, hãy dùng `applyPattern` để tránh phụ thuộc cách viết địa phương. Phải xác định rõ nguồn pattern ngay từ API, không trộn hai chuẩn.

Không nhận pattern tùy ý từ bên ngoài rồi chạy vô hạn trong một hệ thống nhạy hiệu năng mà không có giới hạn độ dài/độ phức tạp, chính sách về ký hiệu và test các trường hợp biên. Một pattern hợp lệ có thể không đáp ứng yêu cầu nghiệp vụ về tiền tệ hoặc số chữ số; validation cần vượt qua bước “không ném exception”.

## 11. RoundingMode kết hợp với pattern

Pattern `0.00` quy định hai chữ số sau dấu thập phân; `setRoundingMode` quyết định hướng chọn số khi cần bỏ phần lẻ. Với `BigDecimal("2.345")`, `HALF_EVEN` cho `2.34`, còn `HALF_UP` cho `2.35`. Formatter chỉ xuất chuỗi, không thay đổi `BigDecimal` gốc. Cách phân loại đủ tám `RoundingMode`, số âm, `UNNECESSARY` và sự khác nhau giữa làm tròn hiển thị/tính toán thuộc bài `RoundingMode của bộ định dạng`.

## 12. Chương trình hoàn chỉnh A: các pattern phổ biến

Lưu thành **`DecimalFormatPatterns.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatPatterns {
    public static void main(String[] args) {
        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);

        System.out.println(new DecimalFormat("#,##0.00", us)
                .format(1234567.5));
        System.out.println(new DecimalFormat("#,##0.##", us)
                .format(1234567.5));
        System.out.println(new DecimalFormat("0000.000", us)
                .format(12.5));
        System.out.println(new DecimalFormat("#,##0.00;(#,##0.00)", us)
                .format(-1234.5));
        System.out.println(new DecimalFormat("0.0%", us)
                .format(0.256));
        System.out.println(new DecimalFormat("0.00E0", us)
                .format(12345));
        System.out.println(new DecimalFormat("'Total:' #,##0.00", us)
                .format(1234.5));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 DecimalFormatPatterns.java
java DecimalFormatPatterns
```

**Stdout chính xác** với symbols US đã chỉ định:

```text
1,234,567.50
1,234,567.5
0012.500
(1,234.50)
25.6%
1.23E4
Total: 1,234.50
```

Mỗi dòng cho thấy một đặc trưng: nhóm chữ số, phần lẻ tùy chọn, số 0 bắt buộc, pattern âm trong ngoặc, multiplier phần trăm, scientific notation và prefix được quote.

## 13. Chương trình hoàn chỉnh B: locale, symbols và localized pattern

Lưu thành **`DecimalFormatLocales.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatLocales {
    public static void main(String[] args) {
        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormatSymbols de =
                DecimalFormatSymbols.getInstance(Locale.GERMANY);

        DecimalFormat usFormat = new DecimalFormat("#,##0.00", us);
        DecimalFormat deFormat = new DecimalFormat("#,##0.00", de);

        System.out.println(usFormat.format(1234567.5));
        System.out.println(deFormat.format(1234567.5));

        DecimalFormatSymbols custom =
                (DecimalFormatSymbols) us.clone();
        custom.setGroupingSeparator('^');
        custom.setDecimalSeparator('|');

        DecimalFormat customFormat =
                new DecimalFormat("#,##0.00", custom);
        System.out.println(customFormat.format(1234567.5));

        deFormat.applyLocalizedPattern("#.##0,00");
        System.out.println(deFormat.toPattern());
        System.out.println(deFormat.format(1234567.5));
    }
}
```

Chạy:

```bash
javac --release 17 DecimalFormatLocales.java
java DecimalFormatLocales
```

**Stdout chính xác:**

```text
1,234,567.50
1.234.567,50
1^234^567|50
#,##0.00
1.234.567,50
```

Với `Locale.GERMANY`, dấu nhóm và dấu thập phân được đổi chỗ trong **chuỗi xuất ra**. Pattern chuẩn `#,##0.00` không đổi; pattern localized `#.##0,00` được `applyLocalizedPattern` chuyển thành cấu trúc chuẩn tương ứng.

Dùng `clone()` để có bộ symbols riêng trước khi thay ký hiệu giúp tránh vô tình chỉnh một bộ đối tượng mà code khác có thể đang sử dụng. Tính mutable của formatter/symbols là lý do nên thiết kế scope và thread ownership rõ.

## 14. Chương trình hoàn chỉnh C: rounding bằng BigDecimal

Lưu thành **`DecimalFormatRounding.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatRounding {
    public static void main(String[] args) {
        DecimalFormat df = new DecimalFormat("0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        System.out.println(df.getRoundingMode());
        System.out.println(df.format(new BigDecimal("2.345")));
        System.out.println(df.format(new BigDecimal("2.355")));

        df.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println(df.format(new BigDecimal("2.345")));
        System.out.println(df.format(new BigDecimal("-2.345")));

        BigDecimal original = new BigDecimal("2.345");
        String display = df.format(original);
        System.out.println(display);
        System.out.println(original.toPlainString());
    }
}
```

Chạy:

```bash
javac --release 17 DecimalFormatRounding.java
java DecimalFormatRounding
```

**Stdout:**

```text
HALF_EVEN
2.34
2.36
2.35
-2.35
2.35
2.345
```

Hai dòng cuối đặc biệt hữu ích: `display` đã được làm tròn thành chuỗi `"2.35"` theo mode HALF_UP, nhưng `original` vẫn là `BigDecimal("2.345")`. Cần thao tác dữ liệu thực sự nếu muốn kết quả làm tròn được lưu.

### 14.1. Tác dụng của setRoundingMode và setMaximumFractionDigits

`DecimalFormat` có thuộc tính mutable. Nếu tạo formatter một lần rồi chỉnh `setMaximumFractionDigits(4)`, các lần `format` sau có thể in tối đa bốn chữ số lẻ. Khi người dùng đổi cách format, tránh dùng lại cùng đối tượng formatter để đồng thời phục vụ nhiều cấu hình khác nhau.

Nếu dùng `RoundingMode.UNNECESSARY`, thao tác format đòi loại bỏ chữ số có thể ném `ArithmeticException`. Chọn mode này khi **chính sách không cho phép rounding**, và xử lý exception thay vì âm thầm làm tròn.

## 15. Parse với DecimalFormat có giới hạn riêng

`DecimalFormat` đọc chuỗi theo pattern, symbols và locale hiện hành. `parse(String)` có thể chỉ lấy tiền tố hợp lệ; khi cần toàn chuỗi, dùng `ParsePosition` và so `getIndex()` với `text.length()`. Nếu muốn decimal hữu hạn chính xác, bật `setParseBigDecimal(true)` nhưng vẫn kiểm tra kiểu kết quả, vì một số giá trị đặc biệt có thể là `Double`. `setParseIntegerOnly(true)` ảnh hưởng parse và không có nghĩa định dạng output chỉ còn số nguyên.

Các bài `ParsePosition và kiểm tra toàn bộ chuỗi khi parse theo locale` và `setParseBigDecimal và giới hạn an toàn khi dùng formatter đồng thời` dạy đầy đủ ví dụ parse strict, edge cases và thread safety.

## 16. Đối chiếu nhanh khi cần parse một chuỗi localized

```java
java.text.DecimalFormat f = new java.text.DecimalFormat(
        "#,##0.00",
        java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US));
f.setParseBigDecimal(true);
java.text.ParsePosition p = new java.text.ParsePosition(0);
String text = "1,234.50";
Number result = f.parse(text, p);
System.out.println(result instanceof java.math.BigDecimal
        && p.getIndex() == text.length()); // true
```

Đoạn trên minh họa cách pattern và symbols đang được dùng ở **chiều parse**. Muốn ràng buộc placement grouping, miền giá trị hoặc chữ số cho phép nghiêm ngặt hơn, cần thêm validation theo schema; parse toàn chuỗi chỉ là điều kiện cần.

## 17. Format và parse không phải hai phép nghịch đảo hoàn hảo

Giả sử dùng `DecimalFormat("0.00")` để in giá trị:

```text
Giá trị nguồn: 2.345
Chuỗi hiển thị: "2.34" hoặc "2.35" tùy rounding
Giá trị parse lại: 2.34 hoặc 2.35
```

Parse lại không tái tạo mọi chữ số của số nguồn ban đầu, vì **format đã cắt/làm tròn số chữ số hiển thị**. Vậy:

```text
parse(format(x)) == x
```

**Không phải đẳng thức tổng quát**. Những nguyên nhân gồm:

1. Rounding và giới hạn chữ số ở pattern.
2. Grouping/decimal separator theo locale.
3. Multiplier phần trăm/phần nghìn.
4. Prefix/suffix tiền tệ hoặc số âm.
5. Chuỗi đặc biệt NaN/Infinity và signed zero.
6. Chính sách parse trả `Long`, `Double` hay `BigDecimal`, có thể làm đổi kiểu và khả năng giữ scale.

Để trao đổi dữ liệu máy–máy cần round-trip chính xác của `double`, thường dùng `Double.toString` và `Double.parseDouble` (với các ràng buộc schema và giá trị đặc biệt cần kiểm soát) thay vì định dạng trình bày `#,##0.00`.

Đối với decimal chính xác và tiền tệ, gửi dạng chuẩn theo schema được xác định rõ (chẳng hạn chuỗi decimal canonical cùng mã tiền tệ/scale), không dùng UI string tùy locale làm định dạng lưu trữ nội bộ.

## 18. Formatter có trạng thái thay đổi

`DecimalFormat` cho phép đổi pattern, symbols, multiplier, fraction digits và mode trong khi dùng; do đó không mặc định an toàn khi cùng instance bị nhiều thread truy cập đồng thời. Bài riêng về `setParseBigDecimal` và sử dụng formatter đồng thời hướng dẫn tạo instance cục bộ, `ThreadLocal` và đồng bộ ngoài.

## 19. Locale và định dạng nghiệp vụ

`DecimalFormatSymbols` làm thay đổi ký hiệu thập phân, phân nhóm, dấu âm và tiền tệ; không được đoán mọi locale sử dụng cùng grouping hoặc glyph. Các pattern và symbols phục vụ trình bày, không xác định đơn vị, loại tiền hoặc quy tắc tính thuế. Bài `Locale, dấu thập phân, nhóm chữ số và dấu âm` và bài wire-format cuối chương giải thích chính sách đầu vào/đầu ra chi tiết.

## 20. Những lỗi phổ biến và hướng xử lý

| Ngộ nhận/lỗi | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| “`#,##0.00` luôn in dấu phẩy nhóm, dấu chấm lẻ” | Symbols tùy locale | Chọn `DecimalFormatSymbols` rõ ràng |
| “`#` và `0` giống nhau” | `0` ép xuất chữ số, `#` tùy chọn | Đặt min/max digits theo yêu cầu |
| “Format hai chữ số sẽ sửa giá trị nguồn” | `format` tạo chuỗi mới | Làm tròn dữ liệu riêng nếu nghiệp vụ yêu cầu |
| “`0.0%` chỉ gắn dấu phần trăm” | Multiplier 100 | Xác định input đang là fraction hay percent |
| “`¤` tự đổi tiền” | Symbol không tính tỷ giá | Quản lý currency và phép chuyển đổi riêng |
| “`applyPattern("#.##0,00")` đọc như ký hiệu Đức” | `applyPattern` nhận pattern chuẩn | Dùng `applyLocalizedPattern` với localized pattern |
| “`new DecimalFormat(pattern)` không phụ thuộc locale” | Constructor lấy symbols từ default locale | Chỉ định symbols/locale |
| “parse thành công nghĩa là cả chuỗi hợp lệ” | Parser có thể chỉ tiêu thụ tiền tố | Kiểm tra `ParsePosition` và input grammar |
| “`setMaximumFractionDigits` giới hạn số lẻ đầu vào” | Chủ yếu là quy tắc format | Validation đầu vào riêng |
| “`parse(String)` luôn trả `Double`” | `Number` có nhiều subtype | Kiểm tra/cấu hình `setParseBigDecimal` |
| “`parseBigDecimal` biến NaN thành decimal” | NaN/Infinity có xử lý đặc biệt | Chặn giá trị không hữu hạn theo schema |
| “`DecimalFormat` mặc định luôn HALF_UP” | Mặc định `HALF_EVEN` | Set `RoundingMode` tường minh |
| “Định dạng 2.345 double là tie decimal chính xác” | binary64 có rounding | Dùng `BigDecimal("2.345")` nếu minh họa decimal tie |
| “Một static final formatter dùng chung thread luôn an toàn” | Formatter mutable, không mặc định synchronized | Dùng instance riêng/đồng bộ |
| “UI string có thể làm format lưu trữ chung mọi quốc gia” | Locale, rounding, separators thay đổi | Chọn định dạng interchange chuẩn riêng |

## 21. Bài tập tự luyện có đáp án

### Bài 1 — Ý nghĩa của pattern

Pattern `#,##0.00` trong `Locale.US` in `1234.5` như thế nào?

**Đáp án:** `1,234.50`. Chữ `0` ở phần lẻ yêu cầu đủ hai chữ số; dấu phẩy nhóm hàng nghìn được hiển thị theo US.

### Bài 2 — `0` và `#`

Với `12.5` và symbols US, pattern `0000.000` và `0.##` khác nhau ra sao?

**Đáp án:** `0012.500` và `12.5`. Pattern thứ nhất đệm zero; thứ hai chỉ in số chữ số lẻ cần thiết (tối đa 2).

### Bài 3 — Positive/negative subpatterns

Với `#,##0.00;(#,##0.00)`, giá trị `-1234.5` được biểu diễn ra sao?

**Đáp án:** `(1,234.50)` trong Locale.US. Subpattern âm thay prefix/suffix âm thành dấu ngoặc.

### Bài 4 — Phần trăm

`new DecimalFormat("0.0%", us).format(0.256)` cho chuỗi nào? Vì sao?

**Đáp án:** `25.6%`. Pattern `%` nhân input với 100 và kèm ký hiệu phần trăm.

### Bài 5 — Scientific notation

`"0.00E0"` in `12345` thành chuỗi nào trong US?

**Đáp án:** `1.23E4`. Một chữ số trước decimal, hai chữ số sau, mũ thập phân.

### Bài 6 — Locale

Cùng giá trị `1234567.5` và cùng pattern chuẩn `#,##0.00`, kết quả US và Đức khác nhau thế nào?

**Đáp án:** US `1,234,567.50`; Đức `1.234.567,50`. Symbols đổi glyph, không đổi giá trị.

### Bài 7 — Custom symbols

Nếu grouping separator là `^` và decimal separator là `|`, pattern chuẩn `#,##0.00` in `1234567.5` thế nào?

**Đáp án:** `1^234^567|50`. Không phải sửa pattern thành `#^##0|00`; hai ký hiệu custom chỉ nằm trong output symbols.

### Bài 8 — applyPattern so với applyLocalizedPattern

Với bộ symbols Đức, chuỗi pattern `"#.##0,00"` nên đưa cho method nào?

**Đáp án:** `applyLocalizedPattern`. `applyPattern` cần chuẩn `"#,##0.00"`, độc lập ký hiệu địa phương.

### Bài 9 — Half-even và half-up

Với `BigDecimal("2.345")` và pattern `0.00`, `HALF_EVEN` và `HALF_UP` cho gì?

**Đáp án:** `2.34` và `2.35`. Với HALF_EVEN, trường hợp tie chọn chữ số cuối chẵn.

### Bài 10 — Format có làm mất dữ liệu nguồn?

Một `BigDecimal("2.345")` được format thành `"2.35"`. `toPlainString()` của BigDecimal ban đầu sau khi format là gì?

**Đáp án:** vẫn `2.345`. Formatter sinh chuỗi, không mutate giá trị `BigDecimal`.

### Bài 11 — Parse tiền tố

`df.parse("123abc", new ParsePosition(0))` trả `123` và vị trí 3. Có nên chấp nhận toàn bộ input không?

**Đáp án:** không nếu schema yêu cầu toàn bộ chuỗi là số. So `ParsePosition.getIndex()` với `input.length()` và kiểm tra thêm ngữ pháp nếu cần.

### Bài 12 — Number subtype

`DecimalFormat.parse("1,234.50")` luôn trả `Double` phải không?

**Đáp án:** không. `parse` khai báo trả `Number`; có thể trả subtype khác theo cài đặt/đầu vào, trong đó `setParseBigDecimal(true)` khiến số thập phân hữu hạn được trả dưới dạng `BigDecimal`.

### Bài 13 — setParseBigDecimal

Khi `setParseBigDecimal(true)` rồi parse `"1,234.50"` theo symbols US, giá trị hiển thị của `Number` là gì?

**Đáp án:** `1234.50`, kiểu `BigDecimal` trong trường hợp này. Điều này hữu ích khi cần giữ số decimal thay vì parse qua binary double.

### Bài 14 — Thread safety

Vì sao không nên dùng một đối tượng `static final DecimalFormat` chung cho hàng chục thread mà không đồng bộ?

**Đáp án:** `final` không khiến đối tượng mutable thành immutable; `DecimalFormat` không mặc định thread-safe/synchronized. Dùng scope riêng hoặc đồng bộ ngoài.

### Bài 15 — Tiền tệ

Pattern `¤#,##0.00` với USD được dùng để hiển thị một số tiền. Nó có tự đổi lượng EUR thành USD không?

**Đáp án:** không. Pattern chỉ chọn symbol/chuỗi và cách hiển thị, không có tỷ giá hay phép chuyển đơn vị.

### Bài 16 — Round-trip

Vì sao `parse(format(x))` có thể không bằng `x` sau khi format `x` với pattern `0.00`?

**Đáp án:** format đã làm tròn giới hạn phần lẻ, có thể bỏ mất thông tin của `x`. Parse chuỗi hiển thị không tự phục hồi những chữ số ban đầu.

## 22. Checklist khi dùng DecimalFormat trong dự án

- [ ] Tôi phân biệt **giá trị số** với **chuỗi format** và biết format không mutate input.
- [ ] Tôi dùng `NumberFormat` factory khi chỉ cần định dạng theo locale, không cast subclass vô điều kiện.
- [ ] Tôi biết `DecimalFormat` là class có pattern và các thuộc tính mutable.
- [ ] Tôi giải thích đúng `0`, `#`, `.`, `,`, `;`, `%`, `‰`, `E`, `¤` và quote `'`.
- [ ] Tôi biết pattern `#,##0.00` là **non-localized**, còn chuỗi kết quả lấy dấu theo `DecimalFormatSymbols`.
- [ ] Tôi dùng `DecimalFormatSymbols.getInstance(locale)` thay vì dựa vào môi trường ngẫu nhiên.
- [ ] Tôi phân biệt `applyPattern` và `applyLocalizedPattern` khi đọc cấu hình pattern.
- [ ] Tôi kiểm soát positive/negative subpattern và chính sách hiển thị số âm.
- [ ] Tôi hiểu multiplier phần trăm/phần nghìn, không nhân hoặc chia lần hai.
- [ ] Tôi biết ký hiệu `¤` gắn với currency metadata, không phải công thức tỷ giá.
- [ ] Tôi đặt `RoundingMode` theo yêu cầu, dùng `BigDecimal` cho trường hợp rounding thập phân cần chính xác.
- [ ] Tôi không coi `format` hai số lẻ là bước làm tròn và lưu dữ liệu nghiệp vụ.
- [ ] Tôi biết `parse` trả `Number` và có thể chỉ nhận một phần chuỗi.
- [ ] Tôi kiểm tra `ParsePosition`/độ dài, chọn `setParseBigDecimal` nếu phải giữ decimal.
- [ ] Tôi không dùng chung một instance mutable giữa nhiều thread mà không có đồng bộ.
- [ ] Tôi dùng format máy–máy có schema cố định thay vì dùng UI string theo locale.
- [ ] Tôi đã chạy bốn chương trình và kiểm thử số âm, zero, rounding tie, input rác và nhiều locale.

## 23. Tài liệu Java SE 17 chính thức

- [DecimalFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — patterns, positive/negative subpatterns, multipliers, rounding, parsing, symbols, thread safety.
- [DecimalFormatSymbols API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html) — các dấu thập phân, grouping, minus, currency, percent, exponent, NaN/Infinity.
- [NumberFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — factory methods và các thuộc tính format/parse.
- [ParsePosition API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html) — kiểm tra vị trí parser đã tiêu thụ dữ liệu.
- [Locale API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) — chọn locale và convention văn hóa.
- [RoundingMode API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) — quy tắc làm tròn.
- [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — biểu diễn decimal chính xác theo nguồn chuỗi và scale.
- [Currency API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html) — metadata tiền tệ.
- [Oracle Java Tutorial — Customizing Formats](https://docs.oracle.com/javase/tutorial/i18n/format/decimalFormat.html) — các ví dụ pattern/symbols (tài liệu tutorial cũ; đối chiếu API Java SE 17 nếu có chi tiết phiên bản).

**Tóm lại:** `DecimalFormat` quyết định **mẫu trình bày**, `DecimalFormatSymbols` quyết định **những ký hiệu được hiển thị**, và `Locale` cung cấp **quy ước địa phương**. Luôn tách bước **tính/lưu giá trị**, **format hiển thị**, **parse dữ liệu đầu vào** và **kiểm tra nghiệp vụ**; khi đó việc đổi dấu phân cách, định dạng tiền, phần trăm hay rounding sẽ không vô tình làm thay đổi ý nghĩa số trong chương trình.