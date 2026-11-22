# Mẫu chuẩn so với mẫu được bản địa hóa trong Java `DecimalFormat`

## 1. Hai loại mẫu, một mục tiêu: định dạng số đúng locale

`java.text.DecimalFormat` biến một giá trị số thành chuỗi hoặc phân tích chuỗi thành số dựa trên **pattern** (mẫu định dạng) và **`DecimalFormatSymbols`** (bộ ký hiệu). Khi định dạng số cho nhiều ngôn ngữ, cần phân biệt:

- **Mẫu chuẩn / không bản địa hóa (standard hoặc non-localized pattern):** các ký tự cú pháp như `.` cho vị trí thập phân và `,` cho phân nhóm được hiểu theo **quy tắc cố định của `DecimalFormat`**, bất kể locale đang dùng. Ví dụ `#,##0.00`.
- **Mẫu được bản địa hóa (localized pattern):** các ký tự cú pháp tương ứng được biểu diễn bằng ký hiệu trong `DecimalFormatSymbols` của formatter. Với locale Đức `de-DE`, mẫu cùng ý nghĩa thường được viết `#.##0,00`: `.` là ký hiệu grouping, `,` là dấu thập phân.

Đừng nhầm **cú pháp của pattern** với **dấu phân cách trong chuỗi kết quả**. Đặt locale Đức không buộc bạn phải tự đổi mẫu chuẩn sang `#.##0,00` nếu dùng `applyPattern` hay constructor `DecimalFormat(String, DecimalFormatSymbols)`. `DecimalFormat` sẽ dùng ký hiệu Đức để tạo ra kết quả `1.234.567,89` từ mẫu chuẩn `#,##0.00`.

```text
Pattern chuẩn:       #,##0.00
         |                         DecimalFormatSymbols(de-DE)
         +--- applyPattern(...)  --------------------------+
                                                          |
                                                    format(1234567.89)
                                                          |
                                               "1.234.567,89"

Pattern bản địa hóa de-DE: #.##0,00
         |
         +--- applyLocalizedPattern(...), symbols(de-DE) -- cùng ý nghĩa
```

**Quy tắc vàng:** pattern dùng cho **mã nguồn/cấu hình chung** thường nên ở dạng chuẩn; pattern người dùng **nhập bằng ký hiệu địa phương** cần được giải mã bằng `applyLocalizedPattern` và đúng bộ `DecimalFormatSymbols`.

## 2. Các API dễ bị dùng nhầm

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `new DecimalFormat(pattern, symbols)` | Tạo formatter từ **pattern chuẩn**, dùng `symbols` để hiển thị | Không truyền pattern đã bản địa hóa vào constructor này |
| `applyPattern(String)` | Áp dụng **pattern chuẩn** | Không tự suy luận nghĩa của `.`/`,` theo locale |
| `applyLocalizedPattern(String)` | Áp dụng **pattern đã bản địa hóa** theo symbols hiện tại | Cần thiết lập đúng symbols **trước** khi gọi |
| `toPattern()` | Trả về biểu diễn pattern **chuẩn** của formatter | Có thể là dạng được chuẩn hóa, không phải đúng từng ký tự đầu vào |
| `toLocalizedPattern()` | Trả về biểu diễn pattern theo **symbols hiện tại** | Không phù hợp để dùng nguyên xi cho locale khác |
| `DecimalFormatSymbols.getInstance(locale)` | Lấy các ký hiệu địa phương cho số, tiền, phần trăm... | Cung cấp ký hiệu; không có nghĩa locale tự chọn nghiệp vụ |
| `setDecimalFormatSymbols(symbols)` | Thay bộ ký hiệu của formatter | Ảnh hưởng output và cách diễn giải các **localized pattern** tiếp theo |

Hai chiều chuyển đổi quan trọng là:

```text
String canonical = formatter.toPattern();
String localized = formatter.toLocalizedPattern();

formatter.applyPattern(canonical);             // đọc cú pháp chuẩn
formatter.applyLocalizedPattern(localized);    // đọc cú pháp địa phương
```

Hai thao tác `apply...` này **không hoán đổi cho nhau**. Đặc biệt, `applyLocalizedPattern` đọc theo symbols của **chính formatter tại thời điểm gọi**, không dựa vào việc chuỗi có trông “giống” tiếng Đức, Pháp hay Mỹ.

## 3. Cú pháp pattern chuẩn: `.` và `,` chỉ có nghĩa cấu trúc

Trong **pattern chuẩn** của `DecimalFormat`:

| Ký hiệu | Vai trò chính |
| --- | --- |
| `0` | Vị trí chữ số bắt buộc; thêm chữ số 0 khi cần |
| `#` | Vị trí chữ số tùy chọn |
| `.` | Dấu **định vị phần thập phân trong pattern** |
| `,` | Dấu **định vị nhóm chữ số trong pattern** |
| `%` | Nhân giá trị với 100 và biểu thị phần trăm |
| `‰` | Nhân giá trị với 1000 và biểu thị phần nghìn |
| `¤` | Ký hiệu tiền tệ trong pattern, phụ thuộc symbols/currency |
| `E` | Thành phần ký hiệu dạng số khoa học |
| `;` | Phân tách phần mẫu số dương và số âm |
| `'` | Quote các ký tự literal trong phần tiền tố/hậu tố mẫu |

Ví dụ `#,##0.00` có ý nghĩa: dùng phân nhóm hàng nghìn, tối thiểu một chữ số phần nguyên và đúng hai chữ số phần thập phân.

**Cực kỳ quan trọng:** dấu `.` trong pattern chuẩn **không cam kết** output có dấu chấm thập phân. Đầu ra dùng dấu thập phân thực tế từ `DecimalFormatSymbols`, chẳng hạn:

| Giá trị | Pattern chuẩn | Symbols | Đầu ra |
| ---: | --- | --- | --- |
| `1234567.89` | `#,##0.00` | `Locale.US` | `1,234,567.89` |
| `1234567.89` | `#,##0.00` | `Locale.GERMANY` | `1.234.567,89` |

Các ví dụ chỉ nói về **ký hiệu phân cách**, không chuyển đổi đơn vị đo hoặc tiền tệ. `1234567.89` vẫn là cùng giá trị số; ngôn ngữ/vùng chỉ tác động cách trình bày.

## 4. Chương trình Java 17+: cùng pattern chuẩn, hai locale

Tạo tệp **`StandardPatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class StandardPatternDemo {
    private static DecimalFormat create(Locale locale) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        return new DecimalFormat("#,##0.00", symbols);
    }

    public static void main(String[] args) {
        DecimalFormat us = create(Locale.US);
        DecimalFormat de = create(Locale.GERMANY);

        double value = 1234567.89;

        System.out.println("US=" + us.format(value));
        System.out.println("DE=" + de.format(value));
        System.out.println("US standard=" + us.toPattern());
        System.out.println("DE standard=" + de.toPattern());
        System.out.println("DE localized=" + de.toLocalizedPattern());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 StandardPatternDemo.java
java -cp . StandardPatternDemo
```

Kết quả trên JDK có dữ liệu locale Đức/Mỹ thông dụng:

```text
US=1,234,567.89
DE=1.234.567,89
US standard=#,##0.00
DE standard=#,##0.00
DE localized=#.##0,00
```

Quan sát hai dòng `US standard` và `DE standard`: chúng giống nhau vì **pattern chuẩn không đổi theo locale**. Chỉ `toLocalizedPattern()` phản ánh ký hiệu `de-DE`. Dòng output khác nhau nhờ symbols.

Ở đây constructor nhận `DecimalFormatSymbols.getInstance(locale)` để tách bạch rõ cấu hình. `new DecimalFormat("#,##0.00")` không nhận locale mà dùng ký hiệu mặc định của môi trường; tránh dùng kiểu đó khi cần kết quả ổn định theo ngôn ngữ người dùng.

## 5. `applyLocalizedPattern`: đọc cú pháp theo locale đã chọn

Một biểu mẫu cấu hình tại Đức có thể cho người dùng nhập trực tiếp pattern `#.##0,00`. Chuỗi đó **không phải** pattern chuẩn. Khi cần nạp nó:

1. Khởi tạo `DecimalFormat`.
2. Thiết lập `DecimalFormatSymbols` cho locale Đức.
3. Gọi `applyLocalizedPattern("#.##0,00")`.
4. Dùng `toPattern()` để lấy phiên bản chuẩn cho lưu trữ/chia sẻ hoặc kiểm tra.

Tạo **`LocalizedPatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocalizedPatternDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat();
        formatter.setDecimalFormatSymbols(
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        formatter.applyLocalizedPattern("#.##0,00");

        System.out.println("canonical=" + formatter.toPattern());
        System.out.println("localized=" + formatter.toLocalizedPattern());
        System.out.println("number=" + formatter.format(1234567.89));

        DecimalFormat wrong = new DecimalFormat();
        wrong.setDecimalFormatSymbols(
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        try {
            // Sai: pattern tiếng Đức lại đưa vào parser chuẩn.
            wrong.applyPattern("#.##0,00");
            System.out.println("wrong accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong: IllegalArgumentException");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocalizedPatternDemo.java
java -cp . LocalizedPatternDemo
```

Kết quả với cú pháp ví dụ trên:

```text
canonical=#,##0.00
localized=#.##0,00
number=1.234.567,89
wrong: IllegalArgumentException
```

**Phân tích:** khi dùng `applyLocalizedPattern`, dấu `.` trong chuỗi Đức được hiểu là grouping, dấu `,` là decimal. Khi gọi sai `applyPattern("#.##0,00")`, parser chuẩn phải hiểu dấu `.` là decimal và `,` là grouping; tổ hợp này không hợp lệ trong ví dụ, nên ném `IllegalArgumentException`.

Không được suy rộng rằng **mọi** pattern bản địa hóa đưa sai API đều ném exception. Một số chuỗi có thể **được chấp nhận nhưng mang ý nghĩa sai**, nhất là khi dấu và ký hiệu trong hai cú pháp trùng nhau một phần. Bởi vậy, luôn ghi rõ nguồn gốc pattern và kiểm thử kết quả; không coi việc không có exception là bằng chứng cấu hình đúng.

## 6. `toPattern()` và `toLocalizedPattern()`: biểu diễn, không phải hai formatter khác nhau

Hai phương thức trả về cách viết **cùng cấu hình pattern đang được formatter nắm giữ**:

```text
formatter:
  pattern logic  = phân nhóm + 2 chữ số thập phân
  symbols        = de-DE

  toPattern()          => "#,##0.00"
  toLocalizedPattern() => "#.##0,00"
```

**Không nên lưu localized pattern như một mẫu “dùng chung mọi locale”.** Ví dụ `#.##0,00` khi đọc bằng symbols Mỹ sẽ có cú pháp/nghĩa khác hoặc bị từ chối. Nếu ứng dụng cho phép người dùng chỉnh pattern theo locale riêng, nên:

- Lưu **pattern chuẩn** bằng `toPattern()` sau khi nạp và xác thực.
- Lưu **locale/symbol-set liên quan** khi bản thân quy tắc định dạng có ý nghĩa địa phương.
- Khi mở lại giao diện cấu hình cho người dùng, tạo formatter với symbols của locale hiện hành, `applyPattern(storedCanonical)`, rồi gọi `toLocalizedPattern()` để hiển thị trong cú pháp địa phương.

**Lưu ý về round-trip:** `toPattern()` và `toLocalizedPattern()` có thể trả **mẫu được chuẩn hóa**. Chúng không cam kết trả lại y nguyên từng ký tự, khoảng trắng hay biểu diễn đồng nghĩa mà người dùng nhập ban đầu. Kiểm thử **ý nghĩa định dạng và đầu ra** thay vì so sánh chuỗi nhập nguyên bản trong mọi trường hợp.

## 7. Format output khác pattern input

Có ba tầng thường bị đánh đồng:

```text
             Pattern logic
     standard hoặc localized syntax
                   |
        DecimalFormatSymbols
       (decimal, grouping, %, ...)
                   |
                DecimalFormat
                   |
              format(number)
                   |
         Chuỗi số đã bản địa hóa
```

Vì `DecimalFormat` có cả `format` và `parse`, lưu ý thêm một tầng thứ tư khi **đọc ngược chuỗi do người dùng nhập**: parser phải biết symbols và các thiết lập tương ứng.

Ví dụ:

```java
DecimalFormat de = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));

String output = de.format(1234567.89);
// output: "1.234.567,89"
```

Đây là **đoạn mã minh họa**, cần import `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.util.Locale`. Nếu dùng để parse dữ liệu người dùng, `DecimalFormat.parse(...)` có thể phân tích được **một phần** chuỗi rồi dừng; để bắt lỗi dữ liệu dư, nên dùng `ParsePosition` và kiểm tra vị trí đã tiêu thụ hết chuỗi.

Đừng nhầm:

- `applyPattern` phân tích **cú pháp mô tả cách format**.
- `format` tạo **văn bản số**.
- `parse` đọc **văn bản số** thành giá trị số.
- `toLocalizedPattern` không tự định dạng giá trị; nó chỉ diễn tả lại pattern bằng ký hiệu địa phương.

Một con số như `1.234` có thể mang nghĩa một nghìn hai trăm ba mươi bốn ở Đức hoặc một phẩy hai ba bốn ở Mỹ. Cần biết locale của **văn bản số**, không phỏng đoán bằng cách đếm dấu chấm và dấu phẩy.

## 8. Mẫu chuẩn và mẫu bản địa hóa khi có phần trăm, tiền tệ và hậu tố

Quy tắc khác biệt không chỉ nằm ở dấu thập phân và grouping. `DecimalFormatSymbols` có các ký hiệu về phần trăm, phần nghìn, dấu âm, ký hiệu số 0, dấu phân cách mẫu âm và ký hiệu tiền tệ; mức độ bản địa hóa cụ thể tùy dữ liệu và cấu hình.

### 8.1. Phần trăm

Pattern chuẩn:

```text
#,##0.0%
```

Với symbols Đức, `format(0.1234)` cho:

```text
12,3%
```

Và `toLocalizedPattern()` trong ví dụ tương ứng là:

```text
#.##0,0%
```

Ký hiệu `%` trong `DecimalFormat` không chỉ là một hậu tố để in: nó **nhân giá trị số với 100 khi format** và có hệ quả tương ứng khi parse. Đừng tự nhân 100 trong dữ liệu rồi áp pattern có `%`, nếu không sẽ nhân hai lần.

Ví dụ chương trình độc lập **`PercentPatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PercentPatternDemo {
    public static void main(String[] args) {
        DecimalFormat percent = new DecimalFormat(
                "#,##0.0%",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        System.out.println(percent.format(0.1234));
        System.out.println(percent.toPattern());
        System.out.println(percent.toLocalizedPattern());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PercentPatternDemo.java
java -cp . PercentPatternDemo
```

Đầu ra:

```text
12,3%
#,##0.0%
#.##0,0%
```

### 8.2. Tiền tệ

`¤` là ký hiệu đặc biệt của currency pattern, ví dụ `¤#,##0.00`. Kết quả hiển thị có thể thay đổi theo `Currency` và `DecimalFormatSymbols` (ký hiệu đồng tiền, dấu phân cách, cách trình bày). **Pattern không thực hiện chuyển đổi tỷ giá.** Nếu số đầu vào là 12.5 USD, thay locale sang Đức không biến 12.5 USD thành EUR.

Một ứng dụng thanh toán nên quản lý **mã tiền tệ** và **độ chính xác/rounding theo nghiệp vụ** riêng, không đoán tiền chỉ từ ngôn ngữ giao diện. Với yêu cầu hiển thị tiền theo quy tắc locale mặc định, `NumberFormat.getCurrencyInstance(locale)` thường là điểm khởi đầu thích hợp; nếu custom `DecimalFormat`, cần cấu hình currency đúng.

### 8.3. Quoting cho chữ literal

Pattern `DecimalFormat` có cơ chế quote bằng dấu nháy đơn cho các ký tự literal trong tiền tố/hậu tố, ví dụ một nhãn đơn vị đứng sau số. Không tự coi các ký tự đặc biệt của `DecimalFormat` là văn bản bình thường khi thêm đơn vị, phần trăm hoặc ký hiệu tiền.

Cũng không đánh đồng cú pháp quote của `DecimalFormat` với `MessageFormat`: cả hai có khái niệm dấu nháy đơn, nhưng chúng là **hai parser và hai hợp đồng pattern khác nhau**. Nếu đặt `DecimalFormat` bên trong một hệ thống tạo thông báo, cần kiểm tra đúng từng tầng.

## 9. Dùng `DecimalFormatSymbols` có chủ đích

`DecimalFormatSymbols.getInstance(Locale.GERMANY)` là cách đơn giản tạo symbols theo locale. Có thể kiểm tra:

```java
DecimalFormatSymbols german =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

System.out.println(german.getDecimalSeparator());  // ,
System.out.println(german.getGroupingSeparator()); // .
```

Đây là trích đoạn cần import các class tương ứng; với dữ liệu Đức thông dụng, in ra dấu phẩy và dấu chấm. `DecimalFormatSymbols` còn có phương thức cấu hình ký hiệu, ví dụ `setDecimalSeparator`, `setGroupingSeparator`, `setMinusSign`, `setPercent`...

Khi **tự chỉnh symbols**, phải xem pattern bản địa hóa theo **symbols tùy chỉnh đó**, không mặc định theo tiếng Đức hay tiếng Anh. Ví dụ cùng locale `de-DE` nhưng grouping separator đã được chỉnh, `toLocalizedPattern()` phản ánh ký hiệu hiện đang cấu hình.

**Trình tự đúng nếu nhận localized pattern từ người dùng:**

```text
Xác định locale / bộ ký hiệu của người nhập
      ↓
Tạo DecimalFormat + DecimalFormatSymbols phù hợp
      ↓
applyLocalizedPattern(userPattern)
      ↓
Kiểm tra pattern hợp lệ và format các giá trị mẫu
      ↓
toPattern() để có biểu diễn chuẩn dùng nội bộ
```

Nếu muốn cho cùng một mẫu chuẩn hiển thị với bộ ký hiệu khác, **không cần** chuyển sang localized pattern bằng thao tác thay thế `String.replace`. Chỉ cần dùng đúng symbols trong formatter.

## 10. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Đưa `#.##0,00` của Đức vào `applyPattern` | Đọc sai dấu hoặc lỗi `IllegalArgumentException` | Dùng `applyLocalizedPattern` với symbols Đức |
| Đưa `#,##0.00` chuẩn vào `applyLocalizedPattern` của Đức | Các dấu có thể bị diễn giải ngược | Dùng `applyPattern` cho mẫu chuẩn |
| Lưu `toLocalizedPattern()` làm mẫu chung | Đọc sai khi runtime/locale khác | Lưu biểu diễn chuẩn `toPattern()`, kèm metadata locale khi cần |
| Dùng `new DecimalFormat(pattern)` cho mọi user | Phụ thuộc default locale của môi trường | Chọn `DecimalFormatSymbols` theo locale người dùng |
| Tự replace mọi `,` thành `.` và ngược lại | Dễ hỏng syntax, hậu tố, phần trăm, literal | Dùng parser/API pattern tương ứng |
| Thấy pattern `.` rồi kết luận output có chấm thập phân | Pattern chuẩn và output dùng hai bộ quy tắc khác nhau | Tách `applyPattern` khỏi symbols dùng khi `format` |
| Nhân 100 trước khi dùng pattern `%` | Hiển thị phần trăm gấp 100 lần nữa | Dùng giá trị tỷ lệ gốc, để `DecimalFormat` xử lý |
| Đổi locale rồi tự cho rằng đổi được tiền tệ | Locale không thực hiện chuyển tỷ giá | Quản lý `Currency`, số tiền, FX độc lập |
| Chỉ kiểm tra pattern không ném lỗi | Có thể format sai ý định | Kiểm thử output với 0, số âm, số thập phân, số lớn |
| Dùng một `DecimalFormat` mutable cho nhiều thread | `DecimalFormat` không đồng bộ/an toàn để chia sẻ tùy ý | Tạo instance riêng cho tác vụ/thread hoặc kiểm soát đồng bộ |
| Giả định mọi JDK cho mọi locale cùng ký hiệu/chuẩn | Dữ liệu locale provider/CLDR có thể thay đổi | Cố định/ghi nhận runtime và kiểm thử các locale mục tiêu |

## 11. Kiểm thử đúng cả pattern lẫn kết quả

Trong một ứng dụng có phần cấu hình mẫu số, nên kiểm thử:

1. **Pattern chuẩn:** nạp `#,##0.00` vào `applyPattern` với ít nhất hai locale; khẳng định `toPattern()` đúng ý nghĩa.
2. **Pattern localized:** nạp `#.##0,00` với symbols Đức bằng `applyLocalizedPattern`; khẳng định kết quả format và pattern chuẩn thu được.
3. **Thứ tự khởi tạo:** symbols phải được thiết lập trước khi phân tích localized pattern. Nếu symbols bị đổi sau đó, cần quyết định liệu phần cấu hình localized có phải được phân tích lại hay không.
4. **Round-trip:** đọc localized pattern → `toPattern()` → khôi phục formatter khác cùng symbols → so kết quả format trên bộ số mẫu. Không yêu cầu chuỗi pattern ban đầu giữ nguyên từng ký tự.
5. **Giá trị biên:** 0, số âm, số nhỏ, giá trị có grouping, số lớn, giá trị cần rounding; nếu ứng dụng có yêu cầu chính xác cao, dùng `BigDecimal` và chọn `RoundingMode` rõ ràng.
6. **Locale khác:** ký hiệu ở Đức, Mỹ và các locale khác có thể khác. Với một số hệ chữ số, localized pattern còn có ký hiệu chữ số và phân cách không quen thuộc với ASCII.
7. **Đọc dữ liệu nhập:** nếu dùng `parse`, kiểm tra toàn bộ chuỗi đã được tiêu thụ; không hiểu `NumberFormat` như trình kiểm tra văn bản nghiêm ngặt mặc định.
8. **Cấu hình không hợp lệ:** bắt `IllegalArgumentException` từ `applyPattern`/`applyLocalizedPattern` và hiển thị hướng dẫn phù hợp, không cố đoán/đảo dấu bằng replace.
9. **Môi trường:** ghi nhận phiên bản JDK, locale-data provider và symbols tùy chỉnh để tránh kết luận sai khi output thay đổi.

Có thể viết kiểm thử Java nhỏ kiểm tra hợp đồng theo locale:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalPatternAssertions {
    private static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + ", received " + actual);
        }
    }

    public static void main(String[] args) {
        DecimalFormat de = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        check("#,##0.00", de.toPattern());
        check("#.##0,00", de.toLocalizedPattern());
        check("1.234.567,89", de.format(1234567.89));

        DecimalFormat copy = new DecimalFormat();
        copy.setDecimalFormatSymbols(
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        copy.applyLocalizedPattern("#.##0,00");

        check(de.toPattern(), copy.toPattern());
        check(de.format(1234567.89), copy.format(1234567.89));
        System.out.println("5 checks passed");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DecimalPatternAssertions.java
java -cp . DecimalPatternAssertions
```

Kết quả nếu các quy tắc và symbols tương ứng đúng:

```text
5 checks passed
```

Chương trình tự kiểm tra bằng `AssertionError`, không cần bật Java `-ea`. Đây là kiểm thử pattern/symbols có chủ đích; nếu ứng dụng hỗ trợ nhiều locale và nhu cầu định dạng nghiệp vụ riêng, cần mở rộng bộ ca.

## 12. Ghi nhớ

- **Mẫu chuẩn** dùng cú pháp cố định của `DecimalFormat` như `#,##0.00`, bất kể kết quả số có dấu phẩy hay dấu chấm.
- **Mẫu được bản địa hóa** dùng ký hiệu trong `DecimalFormatSymbols`, ví dụ `#.##0,00` cho ký hiệu Đức.
- `applyPattern` chỉ dùng cho mẫu **chuẩn**; `applyLocalizedPattern` chỉ dùng cho mẫu **localized** đúng symbols.
- `toPattern()` trả một biểu diễn chuẩn nên thích hợp cho cấu hình dùng chung; `toLocalizedPattern()` thích hợp để **hiển thị** mẫu theo ký hiệu của người dùng.
- **Cú pháp pattern, cách in số và cách parse số là ba việc khác nhau.** Hãy kiểm thử với locale, symbols và runtime thực tế; không đảo dấu bằng xử lý chuỗi tùy tiện.
