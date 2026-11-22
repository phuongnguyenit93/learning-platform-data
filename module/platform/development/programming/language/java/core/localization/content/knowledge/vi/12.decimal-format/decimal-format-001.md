# Mẫu định dạng và vai trò của DecimalFormatSymbols trong Java

**DecimalFormat** là lớp thuộc **java.text** dùng để biến số thành chuỗi hiển thị và phân tích chuỗi số theo một mẫu. Điểm dễ nhầm là mẫu **#,##0.00** không có nghĩa lúc nào cũng in dấu phẩy để ngăn nhóm và dấu chấm làm dấu thập phân. Trong mẫu chuẩn, **,** và **.** là ký hiệu cú pháp; khi hiển thị, **DecimalFormatSymbols** cung cấp các ký tự phù hợp với locale như **1,234.50** ở Hoa Kỳ hoặc **1.234,50** ở Đức.

Bài này giải thích cú pháp mẫu, quan hệ giữa **DecimalFormat** và **DecimalFormatSymbols**, mẫu chuẩn và mẫu bản địa hóa, cách tự cấu hình dấu/ký hiệu, định dạng tiền tệ và phần trăm, phân tích số, làm tròn và những lỗi cần tránh khi Java chạy trên các môi trường khác nhau. Ví dụ ưu tiên Java 17+ và locale tường minh để kết quả có thể kiểm chứng.

## 1. Ba lớp cần tách biệt: số, pattern và ký hiệu

Một phép định dạng có thể hình dung như sau:

~~~text
Giá trị số (Number / BigDecimal)
             |
             v
Mẫu DecimalFormat: #,##0.00
             |
             v
DecimalFormatSymbols của Locale
             |
             v
Chuỗi hiển thị: 12,345.60 hoặc 12.345,60
~~~

- **Giá trị số:** kiểu như **int**, **long**, **double**, **BigInteger** hoặc **BigDecimal**; chứa ý nghĩa số học, không chứa dấu phân nhóm hay tên ngôn ngữ.
- **Pattern:** quyết định có bao nhiêu chữ số bắt buộc/tùy chọn, phân nhóm ở đâu, có tiền tố/hậu tố, nhân theo tỷ lệ phần trăm, dùng ký pháp khoa học hay không.
- **DecimalFormatSymbols:** cung cấp dấu thập phân, dấu phân nhóm, chữ số 0, dấu âm, ký hiệu phần trăm, tiền tệ và các ký hiệu khác dùng khi phân tích/hiển thị.

Để cùng một số được hiển thị theo hai locale, thông thường **giữ nguyên pattern chuẩn**, chỉ thay **DecimalFormatSymbols**. Đây là hai quyết định độc lập: cấu trúc hiển thị và ngôn ngữ/vùng.

Ví dụ cùng một giá trị **12345.6** với pattern **#,##0.00**:

| Locale / symbols | Chuỗi hiển thị | Giải thích |
| --- | --- | --- |
| **Locale.US** | **12,345.60** | Dấu phẩy nhóm nghìn, dấu chấm thập phân |
| **Locale.GERMANY** | **12.345,60** | Dấu chấm nhóm nghìn, dấu phẩy thập phân |
| Symbols tùy chỉnh | **12_345,60** | Dấu gạch dưới nhóm nghìn, dấu phẩy thập phân |
| Locale.US, pattern **000000.00** | **012345.60** | Đệm chữ số nguyên bằng 0, không nhóm nghìn |

Các chuỗi trên là các trường hợp cấu hình cụ thể; **DecimalFormatSymbols** có thể phụ thuộc dữ liệu locale/CLDR của phiên bản JDK. Khi sản phẩm cần một dấu phân cách tuyệt đối xác định, có thể cấu hình symbols tường minh thay vì phụ thuộc hoàn toàn vào môi trường.

## 2. Tạo DecimalFormat theo locale

**DecimalFormat** kế thừa **NumberFormat**, nhưng bổ sung khả năng tạo mẫu bằng chuỗi và thay đổi các ký hiệu. Có các constructor hữu ích:

~~~java
DecimalFormat implicit = new DecimalFormat("#,##0.00");

DecimalFormat explicit = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
~~~

Đây là mã minh họa trong một phương thức, cần import **java.text.DecimalFormat**, **java.text.DecimalFormatSymbols** và **java.util.Locale**.

Constructor không có **DecimalFormatSymbols** dùng ký hiệu mặc định thuộc locale **FORMAT** của JVM. Kết quả vì thế có thể khác giữa máy phát triển, CI và production. Constructor nhận symbols là lựa chọn phù hợp khi ứng dụng đã xác định locale của người dùng hoặc quy tắc xuất dữ liệu.

Cách lấy thông tin qua NumberFormat:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(locale);
String text = number.format(12345.6);
~~~

Đây là đoạn minh họa cần import **java.text.NumberFormat** và biến **locale**. **NumberFormat.getNumberInstance(locale)** tự chọn cấu hình số được khuyến nghị cho locale. Không nên luôn ép kiểu giá trị trả về sang DecimalFormat vì hợp đồng factory chỉ bảo đảm kiểu **NumberFormat**. Nếu cần pattern chuyên biệt, tự tạo **new DecimalFormat(pattern, symbols)**.

## 3. Ngữ pháp cơ bản của mẫu DecimalFormat

Đây là các ký hiệu cú pháp trong **pattern chuẩn** (non-localized pattern). Chúng không nhất thiết giống ký tự được in ra:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **0** | Chữ số bắt buộc, thiếu thì đệm 0 | **0000** biến 42 thành **0042** |
| **#** | Chữ số tùy chọn, không ép hiển thị 0 ở vị trí không cần | **#.##** |
| **.** | Vị trí phần thập phân trong pattern | **0.00** |
| **,** | Xác định kích thước nhóm chữ số | **#,##0** |
| **;** | Tách nhánh dương và âm | **0.00;(0.00)** |
| **%** | Nhân giá trị với 100 khi định dạng, biểu thị phần trăm | **0.0%** |
| **‰** | Nhân với 1000, biểu thị phần nghìn | **0.0‰** |
| **E** | Ký pháp số mũ khoa học | **0.00E0** |
| **¤** | Placeholder tiền tệ; có thể ảnh hưởng ký hiệu và phần thập phân | **¤#,##0.00** |
| **'** | Quote ký tự có nghĩa cú pháp thành literal | **0.00' kg'** |

Quy tắc thực hành: **0** quyết định số chữ số tối thiểu; **#** cho phép bỏ vị trí không cần; **.** chia phần nguyên/thập phân; **,** mô tả nhóm, còn **DecimalFormatSymbols** quyết định ký tự nhóm và dấu thập phân được in thực tế.

Ví dụ dùng **Locale.US**:

| Pattern | Số đầu vào | Chuỗi kết quả |
| --- | ---: | --- |
| **0000** | 42 | **0042** |
| **#,##0** | 12345 | **12,345** |
| **#,##0.00** | 12345.6 | **12,345.60** |
| **0.##** | 12.5 | **12.5** |
| **0.00** | 12.5 | **12.50** |
| **0.00;(0.00)** | -12.5 | **(12.50)** |
| **0.0%** | 0.25 | **25.0%** |
| **0.00' kg'** | 12.5 | **12.50 kg** |

Trong pattern **#,##0.00**, hai chữ số **0** sau dấu thập phân buộc in hai chữ số, dù giá trị chỉ có một. Trong **0.##**, các chữ số sau dấu thập phân tùy chọn, nên không tự in các số 0 thừa.

**Nhớ rằng format không thay đổi bản thân dữ liệu số.** Chuỗi **12.50** xuất phát từ giá trị **12.5** và yêu cầu hiển thị hai chữ số thập phân; đó không phải thao tác lưu lại giá trị mới.

## 4. Chạy thử: cùng pattern, khác DecimalFormatSymbols

**File DecimalFormatSymbolsDemo.java**

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class DecimalFormatSymbolsDemo {
    public static void main(String[] args) {
        String pattern = "#,##0.00";

        DecimalFormat us = new DecimalFormat(
                pattern,
                DecimalFormatSymbols.getInstance(Locale.US));

        DecimalFormat de = new DecimalFormat(
                pattern,
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        DecimalFormatSymbols customSymbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        customSymbols.setDecimalSeparator(',');
        customSymbols.setGroupingSeparator('_');

        DecimalFormat custom = new DecimalFormat(
                pattern, customSymbols);

        System.out.println("US: " + us.format(12345.6));
        System.out.println("DE: " + de.format(12345.6));
        System.out.println("Custom: " + custom.format(12345.6));

        DecimalFormat negatives = new DecimalFormat(
                "#,##0.00;(#,##0.00)",
                DecimalFormatSymbols.getInstance(Locale.US));
        System.out.println(
                "Negative: " + negatives.format(-12.5));

        custom.setParseBigDecimal(true);
        String input = "12_345,60";
        ParsePosition position = new ParsePosition(0);
        Number parsed = custom.parse(input, position);

        if (parsed == null ||
                position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid number");
        }

        BigDecimal exact = (BigDecimal) parsed;
        System.out.println("Parsed: " + exact.toPlainString());
        System.out.println("Consumed: " + position.getIndex());
    }
}
~~~

Chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 DecimalFormatSymbolsDemo.java
java DecimalFormatSymbolsDemo
~~~

Stdout:

~~~text
US: 12,345.60
DE: 12.345,60
Custom: 12_345,60
Negative: (12.50)
Parsed: 12345.60
Consumed: 9
~~~

Giải thích:

1. **us** và **de** có cùng pattern **#,##0.00**, nhưng dùng bộ symbols khác, nên dấu thập phân và phân nhóm đảo chỗ.
2. **custom** chỉ định dấu thập phân **,** và dấu phân nhóm **_**. Đây là ví dụ minh họa cơ chế, không phải quy tắc định dạng thông thường nên áp dụng cho dữ liệu của người dùng.
3. Nhánh âm **;(#,##0.00)** làm số âm được bao trong ngoặc.
4. **setParseBigDecimal(true)** giúp phân tích chuỗi thành **BigDecimal** thay vì dựa vào kiểu Number mặc định.
5. **ParsePosition** giúp xác nhận toàn bộ 9 ký tự đã được đọc; nếu chỉ một tiền tố được chấp nhận, ứng dụng không coi input là hợp lệ.

Kết quả cho thấy **DecimalFormatSymbols điều khiển ký tự thực tế**, còn pattern điều khiển cấu trúc số và sự phân nhóm.

## 5. Phân nhóm chữ số: dấu phẩy trong pattern có nghĩa gì?

Trong pattern **#,##0**, dấu phẩy **,** không mang nghĩa “hiển thị đúng dấu phẩy”, mà cho biết **kích thước nhóm**. Formatter thường lấy vị trí nhóm ở bên phải làm căn cứ, chẳng hạn nhóm 3 chữ số đối với **#,##0**.

Khi dùng:

~~~java
DecimalFormat de = new DecimalFormat(
        "#,##0",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));

System.out.println(de.format(1234567));
~~~

Đây là đoạn minh họa trong phương thức, cần imports tương ứng. Kết quả với pattern đó là **1.234.567**: dấu phân nhóm thực tế là dấu chấm từ symbols của tiếng Đức.

Nếu đổi **setGroupingUsed(false)**, formatter không còn thêm dấu nhóm, dù pattern ban đầu có phần nhóm. **setGroupingSize(...)** cho phép thay kích thước nhóm trong cấu hình formatter. Vì vậy pattern không phải nguồn cấu hình duy nhất sau khi object được tạo; các setter có thể sửa hành vi.

**Lưu ý về phân nhóm không đều:** DecimalFormat của Java có giới hạn trong cách diễn giải các dấu nhóm của pattern; không nên nghĩ rằng chỉ việc thêm nhiều dấu phẩy sẽ mô tả được mọi quy tắc nhóm theo ngôn ngữ. Khi cần quy tắc nhóm đặc thù, kiểm thử formatter với dữ liệu lớn và runtime mục tiêu.

## 6. DecimalFormatSymbols chứa những gì?

**DecimalFormatSymbols** là đối tượng chứa các ký hiệu địa phương dùng khi DecimalFormat hiển thị hoặc phân tích số. Các method tiêu biểu:

| API | Vai trò |
| --- | --- |
| **getDecimalSeparator / setDecimalSeparator** | Dấu phân tách phần nguyên và thập phân |
| **getGroupingSeparator / setGroupingSeparator** | Dấu phân nhóm chữ số |
| **getZeroDigit / setZeroDigit** | Chữ số 0 cơ sở trong tập chữ số bản địa |
| **getMinusSign / setMinusSign** | Ký tự dấu trừ |
| **getPercent / setPercent** | Ký hiệu phần trăm |
| **getPerMill / setPerMill** | Ký hiệu phần nghìn |
| **getCurrencySymbol / setCurrencySymbol** | Ký hiệu tiền tệ hiển thị |
| **getInternationalCurrencySymbol / setInternationalCurrencySymbol** | Mã tiền tệ quốc tế |
| **getMonetaryDecimalSeparator / setMonetaryDecimalSeparator** | Dấu thập phân dùng trong các trường hợp định dạng tiền tệ |
| **getInfinity / setInfinity** | Chuỗi hiển thị cho dương/vô cùng tùy sign |
| **getNaN / setNaN** | Chuỗi hiển thị cho NaN |
| **getExponentSeparator / setExponentSeparator** | Chuỗi ký hiệu phân cách mũ trong ký pháp khoa học |
| **getPatternSeparator / setPatternSeparator** | Ký hiệu tách nhánh pattern khi dùng localized pattern |

Các symbols thường được lấy qua:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
~~~

Đây là đoạn minh họa với import **java.text.DecimalFormatSymbols** và biến **locale**. **Locale** ở đây không tự dịch văn bản ngoài số, và không tự quyết định rằng một giao dịch dùng đồng tiền nào. Nó chỉ cung cấp các quy ước mặc định phù hợp theo dữ liệu locale của JDK.

Có thể sửa từng ký hiệu trước khi tạo DecimalFormat:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
symbols.setDecimalSeparator(',');
symbols.setGroupingSeparator('_');

DecimalFormat formatter =
        new DecimalFormat("#,##0.00", symbols);
~~~

Nếu cần đổi symbols của **một formatter đã tồn tại**, hãy lấy và cập nhật nó tường minh:

~~~java
DecimalFormatSymbols symbols =
        formatter.getDecimalFormatSymbols();
symbols.setGroupingSeparator(' ');
formatter.setDecimalFormatSymbols(symbols);
~~~

Các đoạn trên là minh họa trong phương thức, cần **DecimalFormat**, **DecimalFormatSymbols**, **Locale**, và biến **formatter** có sẵn. Đừng dựa vào việc chỉ sửa object symbols bên ngoài sau khi DecimalFormat đã được tạo mà mong formatter tự cập nhật: cấu hình ký hiệu phải được áp dụng lại bằng **setDecimalFormatSymbols**.

### 6.1. Vì sao nên dùng getInstance(locale)?

**DecimalFormatSymbols.getInstance(locale)** lấy thông tin từ locale provider mà JVM hỗ trợ. Việc dùng mã locale rõ ràng thuận tiện hơn lấy mặc định, vì cho phép formatter phục vụ đúng người dùng và tránh kết quả khác nhau giữa máy.

Tuy nhiên, dữ liệu bản địa hóa trong CLDR/JDK có thể thay đổi qua các bản phát hành. Cùng **vi-VN** có thể gặp khác biệt về dấu cách, tên đơn vị hoặc ký hiệu tiền ở các bản runtime khác nhau. Với đầu ra cần so khớp chính xác từng byte, nên xác định cả locale, phiên bản JDK và những ký hiệu cần ổn định; đừng giả định chỉ truyền locale là khóa cứng toàn bộ định dạng.

### 6.2. Chữ số bản địa

Một locale có thể sử dụng những ký tự chữ số khác dạng ASCII **0–9**. **setZeroDigit** giúp xác định điểm bắt đầu của dãy chữ số trong những hệ chữ số phù hợp với cách DecimalFormat ánh xạ; không nên dùng nó để xử lý tùy ý mọi hệ chữ số không liên tiếp hoặc mọi biến thể Unicode.

Khi người dùng nhập số bằng chữ số bản địa, khả năng parse còn phụ thuộc vào bộ formatter, symbols và quy tắc được JDK hỗ trợ. Cần kiểm thử đầu vào thực tế thay vì mặc định rằng mọi chữ số Unicode đều được hiểu giống nhau.

## 7. Pattern chuẩn và pattern bản địa hóa

Đây là một khác biệt nền tảng:

- **Pattern chuẩn:** dùng ký hiệu cố định của cú pháp DecimalFormat như **.**, **,**, **0**, **#**, **;**, **%**. Dùng **applyPattern(String)** hoặc constructor DecimalFormat(pattern, symbols).
- **Pattern bản địa hóa:** dùng các ký hiệu cục bộ của DecimalFormatSymbols ngay **trong chuỗi pattern**. Dùng **applyLocalizedPattern(String)** để Java hiểu chúng theo symbols hiện tại.

Ví dụ với Đức, mẫu chuẩn **#,##0.00** tương ứng về ý nghĩa với mẫu bản địa hóa **#.##0,00**. Nếu đem **#.##0,00** truyền vào **applyPattern** (mẫu chuẩn), Java sẽ hiểu dấu chấm và phẩy theo **cú pháp chuẩn**, không theo ngôn ngữ Đức, nên có thể sai hoặc không hợp lệ.

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocalizedPatternDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.GERMANY);

        DecimalFormat formatter =
                new DecimalFormat("#,##0.00", symbols);

        System.out.println(formatter.format(12345.6));

        formatter.applyLocalizedPattern("#.##0,00");
        System.out.println(formatter.format(12345.6));
    }
}
~~~

Chạy **javac LocalizedPatternDemo.java** rồi **java LocalizedPatternDemo**. Với hai mẫu tương đương, cả hai dòng đều là **12.345,60**. **toPattern()** trả biểu diễn mẫu chuẩn của formatter; **toLocalizedPattern()** trả biểu diễn tương ứng với ký hiệu bản địa.

**Khuyến nghị:** lưu pattern cấu hình và pattern trong mã nguồn bằng **cú pháp chuẩn** rồi áp dụng với symbols đã chọn. Chỉ dùng localized pattern khi thật sự nhận pattern do con người nhập hoặc hiển thị mẫu theo quy ước của họ; lúc đó phải dùng đúng **applyLocalizedPattern/toLocalizedPattern**.

### 7.1. Phân biệt ký hiệu cú pháp và ký hiệu hiển thị

Giả sử formatter sử dụng **DecimalFormatSymbols** có decimal **,** và grouping **_**. Pattern chuẩn vẫn phải là **#,##0.00**. Nếu ghi **#_##0,00** như thể ký tự hiển thị có thể thay luôn ký hiệu cú pháp, việc parse pattern sẽ không còn giống ý định.

Ngược lại, nếu bắt buộc dùng localized pattern, chuỗi mẫu phải được tạo đúng theo bộ symbols đã chọn; trường hợp ký hiệu mới xung đột với ký hiệu pattern khác cần xử lý rõ ràng. Đừng cho rằng mọi cách phối hợp ký hiệu tùy chỉnh đều hợp lệ.

## 8. Tiền tố, hậu tố, nhánh âm và literal

Pattern có thể đặt văn bản trước/sau số. Ví dụ **0.00' kg'** thêm đơn vị kg sau số. Dấu nháy đơn dùng để quote ký tự có nghĩa đặc biệt; muốn in dấu nháy đơn literal trong pattern, dùng cơ chế escape bằng hai dấu nháy đơn thích hợp.

~~~java
DecimalFormat quantity = new DecimalFormat(
        "0.00' kg'",
        DecimalFormatSymbols.getInstance(Locale.US));
System.out.println(quantity.format(12.5));
~~~

Đây là đoạn minh họa trong phương thức. Output là **12.50 kg**. Phần **kg** chỉ là suffix văn bản; DecimalFormat không tự chuyển đổi đơn vị.

### 8.1. Hai nhánh dương và âm

Mẫu **#,##0.00;(#,##0.00)** gồm phần dương và phần âm. Với **Locale.US**, **-12.5** thành **(12.50)**. Một nhánh âm có thể thay đổi prefix/suffix hiển thị, nhưng không nên giả định có thể tạo hai bộ chính sách chữ số hoàn toàn độc lập chỉ bằng cách viết hai mẫu khác nhau trong cùng pattern. Chỉ viết các subpattern được API chấp nhận và kiểm thử với số âm, số 0, số nhỏ.

Nếu không có nhánh âm riêng, DecimalFormat dùng tiền tố âm theo symbols, thường có dấu âm trước biểu diễn dương. Nếu ký hiệu dấu trừ của locale khác nhau, **DecimalFormatSymbols** sẽ tham gia quyết định ký tự xuất ra.

### 8.2. Không ghép chuỗi để giả lập pattern

Một sai lầm thường gặp là định dạng số rồi tự thêm dấu âm hoặc đơn vị tiền ở ngoài mà không xét locale. Khi ký hiệu tiền có thể đứng trước hay sau, có khoảng trắng đặc biệt hoặc thay đổi theo vùng, cách ghép thủ công dễ làm mất tính bản địa hóa. Sử dụng pattern hoặc NumberFormat với quy tắc tiền tệ đúng, còn giá trị số lưu riêng.

## 9. Phần trăm và phần nghìn: ký hiệu có tác dụng số học

Trong pattern, **%** và **‰** không chỉ đơn thuần là hậu tố. Chúng còn tác động tới hệ số nhân/chiều phân tích:

- **0.0%** format giá trị **0.25** thành **25.0%** với Locale.US.
- **0.0‰** format giá trị **0.025** thành **25.0‰** với symbols và định dạng tương ứng.

Nếu muốn hiển thị **%** như một ký tự literal mà **không nhân 100**, phải quote/escape ký hiệu trong pattern hoặc thêm văn bản sau khi đã định dạng theo hợp đồng rõ ràng. Không được nhập **25** với pattern phần trăm rồi mong ra **25%**: nó có thể thành **2500%**.

Đối với giá trị đầu vào, cần quy ước rõ **0.25** nghĩa là tỷ lệ **25%** hay một con số đã được tính theo phần trăm. Việc lưu một số không kèm đơn vị/ý nghĩa dẫn đến lỗi nghiệp vụ mà DecimalFormat không thể tự phát hiện.

## 10. Tiền tệ và ký hiệu ¤

Ký hiệu **¤** trong DecimalFormat pattern là placeholder tiền tệ. Một ký hiệu thường dùng biểu diễn symbol của currency, hai ký hiệu có thể yêu cầu mã tiền tệ ISO 4217. Cách hiển thị chi tiết còn phụ thuộc locale, bộ symbols và dữ liệu JDK.

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Currency;
import java.util.Locale;

public class CurrencyPatternDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        DecimalFormat symbolsOnly = new DecimalFormat(
                "¤#,##0.00",
                DecimalFormatSymbols.getInstance(locale));
        symbolsOnly.setCurrency(Currency.getInstance("USD"));

        System.out.println(symbolsOnly.format(1234.5));
    }
}
~~~

Chạy **javac CurrencyPatternDemo.java**, **java CurrencyPatternDemo**. Với cấu hình Hoa Kỳ minh họa, chuỗi tương đương **$1,234.50**. Cần tránh khẳng định mã/ký hiệu tiền ở mọi locale và phiên bản JDK là bất biến; một số ký hiệu có thể có tiền tố, hậu tố, khoảng trắng đặc biệt.

**Ba điều cần phân biệt:**

1. **Currency** cho biết đơn vị tiền tệ; nó không quy đổi tỷ giá.
2. **DecimalFormatSymbols** chứa các ký hiệu tiền tệ hiển thị và dấu thập phân tiền tệ; với pattern tiền tệ, DecimalFormat có thể dùng **monetary decimal separator** thay cho dấu thập phân thường.
3. **Pattern và cấu hình chữ số thập phân** quyết định số chữ số được in; đừng giả định một pattern luôn tự chọn số chữ số tối ưu cho mọi loại tiền.

Nếu tiền giao dịch là **JPY**, **VND**, **USD** hoặc **EUR**, hãy lấy mã tiền từ nghiệp vụ và thiết lập formatter theo hợp đồng. Locale giao diện tiếng Việt không có nghĩa mọi giao dịch đều là VND. Với báo cáo tài chính, dùng **BigDecimal**, giữ mã Currency bên cạnh giá trị và thiết lập rounding phù hợp. Nếu tỷ giá cần chuyển đổi, đó là bài toán xử lý dữ liệu riêng.

## 11. Rounding và lượng chữ số thập phân

DecimalFormat có thể định dạng số theo pattern, nhưng khi phải in ít chữ số hơn giá trị gốc, nó cần **làm tròn**. Một số phương thức liên quan:

- **setRoundingMode(RoundingMode)**: quy tắc làm tròn.
- **setMinimumFractionDigits(int)** và **setMaximumFractionDigits(int)**: giới hạn chữ số sau dấu thập phân.
- **setMinimumIntegerDigits(int)** và **setMaximumIntegerDigits(int)**: giới hạn phần nguyên.
- **setGroupingUsed(boolean)** và **setGroupingSize(int)**: cách nhóm chữ số.
- **setDecimalSeparatorAlwaysShown(boolean)**: có bắt buộc hiển thị dấu thập phân khi không có phần lẻ hay không.

**DecimalFormat** dùng rounding mode mặc định **HALF_EVEN**. Trong các trường hợp tài chính cần HALF_UP, DOWN hay quy tắc khác, phải thiết lập tường minh thay vì dựa vào mặc định.

Ví dụ chạy được với BigDecimal để tránh sai số nhị phân của double:

**File RoundingDemo.java**

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        BigDecimal value = new BigDecimal("1.245");

        System.out.println(
                "HALF_EVEN=" + formatter.format(value));

        formatter.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println(
                "HALF_UP=" + formatter.format(value));
    }
}
~~~

Chạy:

~~~bash
javac RoundingDemo.java
java RoundingDemo
~~~

Stdout:

~~~text
HALF_EVEN=1.24
HALF_UP=1.25
~~~

Kết quả minh họa tại điểm giữa: HALF_EVEN chọn chữ số cuối chẵn (4), HALF_UP làm tròn lên (5). **Formatter không thay đổi BigDecimal value**; nó chỉ sinh chuỗi hiển thị. Những quy tắc làm tròn dùng trong tính toán nghiệp vụ nên áp dụng tại tầng dữ liệu theo chính sách, trước khi định dạng khi cần.

## 12. Phân tích số: parse theo đúng symbols

DecimalFormat không chỉ format mà còn **parse** văn bản có dấu phân cách theo locale. Nếu đầu vào **12.345,60** đến từ người dùng Đức, phân tích bằng symbols Hoa Kỳ có thể hiểu sai hoặc chỉ nhận một phần chuỗi.

~~~java
DecimalFormat de = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
de.setParseBigDecimal(true);

ParsePosition pos = new ParsePosition(0);
Number parsed = de.parse("12.345,60", pos);
~~~

Đây là đoạn minh họa trong phương thức, cần import **DecimalFormat**, **DecimalFormatSymbols**, **Locale**, **ParsePosition**. **parseBigDecimal** giúp kết quả là BigDecimal khi phân tích thành công; **ParsePosition** ghi vị trí đã được đọc và vị trí lỗi.

### 12.1. Phải kiểm tra phần dư

**DecimalFormat.parse(String)** có thể đọc một tiền tố hợp lệ rồi dừng mà không tự xác nhận toàn bộ chuỗi đã được tiêu thụ. Do đó, với input yêu cầu tính đúng đắn, dùng:

~~~java
ParsePosition pos = new ParsePosition(0);
Number n = de.parse(text, pos);

if (n == null || pos.getIndex() != text.length()) {
    throw new IllegalArgumentException("Malformed amount");
}
~~~

Đoạn minh họa dùng biến **de**, **text** đã khai báo và import **java.text.ParsePosition**. Với dữ liệu nhập thực tế, còn cần kiểm tra khoảng trắng, giới hạn giá trị, quy tắc phân nhóm mong muốn và việc đầu vào có được phép dùng các ký hiệu khác không.

### 12.2. Hiểu đúng parser lenient

Không thể mặc định **DecimalFormat.parse** là bộ validator nghiêm ngặt cho mọi pattern. Nó có thể chấp nhận chuỗi không đúng hoàn toàn quy tắc phân nhóm hoặc một số dạng ký hiệu mà ứng dụng không muốn. Kiểm tra **ParsePosition** chỉ bảo đảm parser đi tới cuối, chưa chứng minh văn bản có đúng toàn bộ style quy định.

Khi cần nhập số rất nghiêm ngặt, có thể kết hợp validation của miền dữ liệu, quy tắc độ dài, cấu trúc chuỗi, hoặc một parser được thiết kế riêng. Không dùng kết quả của **format(parse(text))** làm chứng cứ duy nhất về tính hợp lệ, vì chuẩn hóa có thể thay đổi chuỗi theo cách hợp lệ về số học nhưng trái quy tắc đầu vào.

### 12.3. BigDecimal và dữ liệu chính xác

Nếu muốn đọc số thập phân chính xác, **setParseBigDecimal(true)** là lựa chọn hợp lý. Điều này khác với việc gọi **Double.parseDouble(...)**, vốn chỉ chấp nhận cú pháp số kiểu Java/ASCII, không tự hiểu các dấu nhóm của mỗi locale.

Với số được trao đổi giữa máy bằng JSON, CSV theo schema hay dữ liệu cơ sở dữ liệu, nên dùng **định dạng máy đã quy định rõ**. Không dùng locale của máy chủ để đọc file hợp đồng có cú pháp cố định.

## 13. Ký pháp khoa học và các chuỗi đặc biệt

**DecimalFormat** có hỗ trợ ký pháp khoa học bằng chữ **E** trong pattern. Ví dụ mẫu **0.00E0** định dạng số theo phần hệ số và mũ; **DecimalFormatSymbols** quyết định ký hiệu exponent trong output, còn số chữ số hệ số, độ chính xác và cách làm tròn chịu pattern/formatter.

Với Locale.US, một dạng như **1.23E4** có nghĩa **1.23 × 10⁴**. Khi đổi locale, ký hiệu thập phân có thể đổi theo symbols. Nếu hệ thống trao đổi dữ liệu cần cú pháp khoa học cố định, không nên dùng một localized formatter tùy mặc định JVM.

DecimalFormatSymbols còn có **NaN**, **Infinity** và dấu trừ. Khi formatter gặp **Double.NaN**, **Double.POSITIVE_INFINITY** hoặc số âm vô cùng, nó dùng các biểu diễn phù hợp cấu hình. Những chuỗi này thường không phù hợp với dữ liệu nghiệp vụ như số tiền; hãy kiểm tra tính hữu hạn và miền giá trị trước khi định dạng hoặc parse.

Các chữ số không Latin cũng có thể ảnh hưởng hiển thị. Việc chọn locale không bảo đảm mọi font hoặc phía nhận dữ liệu đều đọc/hiển thị chúng chính xác, vì vậy cần kiểm thử giao diện và hợp đồng trao đổi.

## 14. Pattern là cú pháp, không phải biểu thức tính toán

Định dạng giúp trình bày giá trị, **không** thay thế tính toán:

- **0000** không thay đổi giá trị số 42 thành 0042; nó chỉ sinh chuỗi **0042**.
- **0.00** không sửa giá trị gốc thành một BigDecimal mới có đúng hai chữ số thập phân.
- **0.0%** thay đổi tỷ lệ hiển thị bằng multiplier, không có nghĩa dữ liệu gốc được nhân 100 trong cơ sở dữ liệu.
- **¤#,##0.00** thêm tiền tệ khi hiển thị, không đổi USD sang VND.
- Pattern có hậu tố **kg** không đổi gram sang kilogram.

Tách giá trị chuẩn và cách trình bày là nguyên tắc cốt lõi của bản địa hóa. Một trường tiền giao dịch cần giữ **giá trị chính xác + mã tiền**, còn một trường tỷ lệ cần quy định **giá trị lưu** là 0.25 hay 25 trước khi formatter xuất chuỗi.

## 15. Dùng DecimalFormat bên trong MessageFormat

**MessageFormat** có thể tạo DecimalFormat con từ pattern chứa **{0,number,...}**. Ví dụ:

~~~java
MessageFormat message = new MessageFormat(
        "Amount: {0,number,#,##0.00}",
        Locale.GERMANY);
~~~

Đây là đoạn minh họa cần import **java.text.MessageFormat** và **java.util.Locale**. Locale của MessageFormat tác động đến bộ symbols của DecimalFormat được tạo khi pattern được áp dụng. Nếu gọi **message.setLocale(Locale.US)** sau đó, formatter con đã tồn tại không tự đổi symbols. Có thể tạo MessageFormat mới theo locale mong muốn hoặc gọi **applyPattern** đúng lúc rồi cấu hình lại các formatter custom.

Nếu muốn ký hiệu tùy chỉnh, có thể tạo **DecimalFormat** với symbols rõ ràng và gắn nó vào MessageFormat:

~~~java
DecimalFormat custom = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

MessageFormat message = new MessageFormat(
        "Amount: {0}", Locale.US);
message.setFormatByArgumentIndex(0, custom);
~~~

Đây là đoạn minh họa cần import **DecimalFormat**, **DecimalFormatSymbols**, **MessageFormat**, **Locale**. Khi có nhiều bản dịch đảo thứ tự argument, **setFormatByArgumentIndex** giúp gắn formatter vào đúng chỉ số đối số, không phụ thuộc vị trí xuất hiện trong câu.

## 16. Những sai lầm thường gặp

### Lỗi 1: Nhầm pattern chuẩn với dấu của locale

Nhà phát triển thấy số tiếng Đức **1.234,50**, nên tự viết mẫu chuẩn **#.##0,00**. Trong **applyPattern**, dấu **.** vẫn là dấu phần thập phân của cú pháp chuẩn; mẫu này có thể sai. Hãy dùng **#,##0.00** với **DecimalFormatSymbols.getInstance(Locale.GERMANY)**, hoặc gọi **applyLocalizedPattern** nếu thật sự có localized pattern.

### Lỗi 2: Dùng constructor không truyền symbols trong server

**new DecimalFormat("#,##0.00")** lấy symbols mặc định của JVM; dev, CI và server có thể tạo output khác nhau. Với dữ liệu phục vụ người dùng, truyền locale đã resolve; với dữ liệu máy, dùng hợp đồng biểu diễn cố định.

### Lỗi 3: Chỉ sửa DecimalFormatSymbols cũ rồi nghĩ formatter đã đổi

Vì DecimalFormat quản lý cấu hình symbols của mình, hãy dùng **setDecimalFormatSymbols(...)** khi muốn cập nhật instance có sẵn. Không dựa vào việc sửa object nằm ngoài formatter sau lúc khởi tạo.

### Lỗi 4: Nhầm dấu nhóm với dấu thập phân khi parse

Chuỗi **1,234** có thể là một nghìn hai trăm ba mươi tư theo en-US, nhưng là một phẩy hai ba bốn theo de-DE. Parse dùng symbols sai có thể đổi ý nghĩa số. Phải biết locale của **dữ liệu đầu vào**, không tự lấy locale server.

### Lỗi 5: Ghi cứng symbol tiền tệ nhưng quên mã tiền

Thêm một ký hiệu **$** trước số không nói rõ USD, CAD, AUD hoặc loại tiền nào. Nên giữ **Currency** và đơn vị giao dịch tường minh; chọn cách hiển thị theo yêu cầu sản phẩm và locale.

### Lỗi 6: Cho rằng setCurrency đã chuyển tỷ giá

Đặt Currency thành JPY chỉ thay metadata/ký hiệu định dạng; nó không tính lại số tiền. Việc đổi tỷ giá cần nguồn giá và phép tính nghiệp vụ riêng.

### Lỗi 7: Mặc định làm tròn không đúng chính sách

Một formatter mặc định dùng **HALF_EVEN**, nhưng yêu cầu nghiệp vụ là **HALF_UP** hoặc làm tròn về số bước cụ thể. Hãy thiết lập RoundingMode tường minh và dùng BigDecimal cho phép tính chính xác.

### Lỗi 8: Tin parse(String) đã kiểm tra hết chuỗi

Parse có thể thành công với tiền tố hợp lệ và bỏ phần đuôi. Với dữ liệu nhập cần strict, kiểm tra ParsePosition và ràng buộc khác. Không chỉ kiểm tra **parsed != null**.

### Lỗi 9: Dùng DecimalFormat chung giữa nhiều luồng

**DecimalFormat** là mutable và không được coi là thread-safe. Đổi pattern, symbols, rounding hoặc parsing options trong khi luồng khác gọi format có thể gây lỗi không ổn định. Trong server, tạo instance riêng theo request/luồng hoặc đồng bộ đầy đủ; không tự ý thay JVM default để điều khiển formatter của từng người dùng.

### Lỗi 10: Nhầm format dữ liệu máy với hiển thị người dùng

Kết quả **12.345,60** có thể hoàn toàn đúng cho người Đức, nhưng file API/CSV máy đọc có thể yêu cầu **12345.60**. Định nghĩa hợp đồng dữ liệu trước, chọn formatter theo mục đích, không lấy locale ngẫu nhiên của máy tạo file.

## 17. Kiểm thử và vận hành

Một bộ test cho chức năng DecimalFormat nên kiểm tra:

| Trường hợp | Điều mong đợi |
| --- | --- |
| Cùng **#,##0.00** dưới en-US/de-DE | Dấu nhóm/thập phân khác, giá trị số giữ nguyên |
| Cùng pattern với symbols tùy chỉnh | Ký tự do setters quyết định |
| Pattern **0000**, **0.##**, **0.00** | Phân biệt chữ số bắt buộc và tùy chọn |
| Nhánh âm **;(...)** | Tiền tố/hậu tố âm đúng |
| **0.0%** và **0.0‰** | Multiplier đúng |
| **¤** và mã Currency | Symbol và mã tiền không bị hiểu nhầm thành quy đổi |
| **applyPattern** vs **applyLocalizedPattern** | Không tráo cú pháp chuẩn và bản địa hóa |
| Parse và ParsePosition | Đọc hết dữ liệu, phát hiện phần dư |
| **setParseBigDecimal(true)** | Số thập phân được giữ chính xác |
| **HALF_EVEN/HALF_UP** | Rounding theo hợp đồng |
| Locale mặc định khác nhau trên dev/CI | Kết quả với symbols tường minh không đổi |
| Nhiều luồng cùng xử lý | Không chia sẻ formatter mutable thiếu bảo vệ |

Đối với snapshot test cần output chính xác, dùng symbols/locale đã chọn và kiểm soát phiên bản JDK hoặc dữ liệu CLDR khi cần. Những ký hiệu như khoảng trắng đặc biệt, dấu âm hay biểu diễn tiền tệ có thể thay đổi theo dữ liệu locale của các bản JDK; đừng khẳng định mọi chuỗi bản địa hóa luôn bất biến.

## 18. Checklist lựa chọn DecimalFormat

1. Xác định đây là **đầu ra cho con người** hay **dữ liệu trao đổi máy**.
2. Nếu là hiển thị, chọn locale đúng của người dùng hoặc tổ chức; nếu là dữ liệu máy, theo hợp đồng định dạng bất biến.
3. Viết **pattern chuẩn** bằng ký hiệu DecimalFormat, ví dụ **#,##0.00**.
4. Lấy **DecimalFormatSymbols.getInstance(locale)** hoặc cấu hình symbols theo yêu cầu rõ ràng.
5. Tạo formatter **new DecimalFormat(pattern, symbols)**; nếu thay đổi symbols của formatter đã tạo, gọi setter phù hợp.
6. Thiết lập rounding và số chữ số thập phân, đặc biệt với tiền tệ.
7. Giữ mã Currency và ý nghĩa số liệu riêng; không suy tỷ giá từ ký hiệu.
8. Nếu parse, dùng locale của input, có thể dùng BigDecimal và kiểm tra hết văn bản.
9. Không dùng cùng một DecimalFormat mutable ở nhiều request đồng thời thiếu bảo vệ.
10. Kiểm thử âm, 0, số lớn, số nhỏ, locale khác nhau và chữ số/chuỗi đặc biệt.
11. Phân biệt **applyPattern** với **applyLocalizedPattern**.
12. Khi gắn vào MessageFormat, kiểm tra thời điểm formatter con được tạo và locale của chính formatter đó.

## 19. Ghi nhớ

**Pattern của DecimalFormat mô tả cấu trúc số; DecimalFormatSymbols quyết định ký hiệu được hiển thị và nhận khi parse.** Mẫu chuẩn **#,##0.00** có thể cho **12,345.60** hoặc **12.345,60** tùy symbols. Các setter như **setRoundingMode**, **setGroupingUsed** và **setDecimalFormatSymbols** có thể thay đổi hành vi sau khi tạo formatter.

Hãy giữ dữ liệu số có kiểu chính xác, truyền locale tường minh cho phần hiển thị, không nhầm localized pattern với pattern chuẩn, bảo vệ quá trình parse và định nghĩa quy tắc rounding/tiền tệ theo nghiệp vụ. Khi các quyết định đó được tách bạch và kiểm thử, DecimalFormat trở thành công cụ ổn định, có thể dự đoán trong ứng dụng Java 17+ đa ngôn ngữ.
