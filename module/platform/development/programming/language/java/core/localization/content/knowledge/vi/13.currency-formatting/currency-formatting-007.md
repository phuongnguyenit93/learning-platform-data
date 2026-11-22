# Khoảng trắng, vị trí ký hiệu và định dạng âm theo dữ liệu locale

Một số tiền không chỉ là số có thêm ký hiệu tiền tệ. Cùng giá trị **1234,50 EUR**, người dùng ở các vùng khác nhau có thể quen với ký hiệu đứng **trước** hoặc **sau** con số, dùng dấu **chấm** hay **phẩy** làm dấu thập phân, có hoặc không có **khoảng trắng** giữa số và ký hiệu, và thể hiện số âm bằng dấu trừ hay cặp ngoặc. Ngay cả khi nhìn giống dấu cách thông thường, ký tự thực tế có thể là **U+0020 SPACE**, **U+00A0 NO-BREAK SPACE** hoặc **U+202F NARROW NO-BREAK SPACE**.

Trong Java Core, **NumberFormat.getCurrencyInstance(locale)** và các lớp **DecimalFormat**, **DecimalFormatSymbols** sử dụng dữ liệu locale của runtime để tạo cách biểu diễn tiền tệ. Bài học này đi sâu vào **khoảng trắng, vị trí ký hiệu và cách định dạng giá trị âm**, cách quan sát chúng một cách chính xác, thiết kế mẫu tùy chỉnh khi cần, và phân biệt định dạng dành cho người đọc với dữ liệu tiền tệ dùng trong nghiệp vụ.

## 1. Tách giá trị tiền khỏi cách biểu diễn

Một đối tượng nghiệp vụ có thể chứa:

- **Giá trị số:** chẳng hạn một **BigDecimal** biểu diễn 1234.50.
- **Đơn vị tiền:** mã ISO 4217 như **EUR**, **USD**, **VND** được thể hiện bằng **java.util.Currency**.
- **Locale hiển thị:** ví dụ **en-US**, **de-DE**, **fr-FR** hoặc **vi-VN**.
- **Chính sách trình bày:** quy định vị trí ký hiệu, khoảng trắng, số chữ số thập phân, dấu âm hoặc kiểu kế toán nếu sản phẩm yêu cầu.

Bốn điều trên không đồng nghĩa. Một người chọn giao diện tiếng Việt vẫn có thể thanh toán bằng EUR. **Currency** không quyết định ngôn ngữ giao diện; **Locale** không chứng minh giao dịch dùng loại tiền nào; **NumberFormat** không quy đổi tỷ giá.

Mô hình đúng:

~~~text
Money = (BigDecimal amount, Currency currency)
                         +
             Locale người xem
                         +
             Chính sách hiển thị
                         |
                         v
            Chuỗi tiền đã định dạng
~~~

Nếu mục tiêu là lưu trữ hoặc truyền dữ liệu qua API, hãy lưu **amount** và **currency** thành các trường dữ liệu có kiểu. Chuỗi như **1.234,50 €** chỉ là đầu ra phục vụ con người, không nên trở thành biểu diễn chuẩn duy nhất của giá trị tiền.

## 2. Locale ảnh hưởng những thuộc tính nào?

Đối với định dạng tiền, runtime có thể cung cấp những thông tin sau:

| Thuộc tính | Vai trò |
| --- | --- |
| **Decimal separator** | Ký hiệu phân cách phần nguyên và phần thập phân |
| **Grouping separator** | Ký hiệu phân nhóm hàng nghìn và các nhóm khác |
| **Currency symbol** | Ký hiệu hiển thị như **€**, **$**, **₫** hoặc dạng phân biệt khác |
| **Currency pattern** | Cấu trúc quy định vị trí ký hiệu và khoảng trắng |
| **Negative subpattern/prefix/suffix** | Cách biểu diễn giá trị âm |
| **Fraction digits** | Số chữ số tối thiểu/tối đa trong cấu hình formatter |
| **Digit symbols** | Hệ chữ số, dấu trừ và các ký hiệu liên quan |

Trong Java, các thông tin này được lấy chủ yếu qua **NumberFormat** và cấu hình của **DecimalFormat** cùng **DecimalFormatSymbols**. Phần lớn runtime Java hiện đại tích hợp dữ liệu địa phương hóa từ CLDR, nhưng chi tiết có thể đổi khi nâng cấp bản JDK, dữ liệu locale hoặc provider.

**Đừng viết test giả định rằng mọi bản JDK luôn cho cùng một chuỗi tiền từng byte.** Nên biết bạn đang kiểm thử khả năng bản địa hóa của runtime hay hợp đồng định dạng riêng của ứng dụng.

## 3. Vị trí ký hiệu tiền tệ có thể thay đổi theo locale

Có ít nhất ba kiểu thường gặp về mặt trải nghiệm:

~~~text
Ký hiệu trước số:       €1,234.50
Ký hiệu sau số:         1.234,50 €
Mã tiền thay ký hiệu:   EUR 1,234.50
~~~

Đây là những dạng minh họa, **không phải bảng cam kết output chính xác của mọi JDK**. Thực tế ký hiệu có thể cần khoảng trắng đặc biệt, vị trí có thể thay đổi giữa mã ISO và ký hiệu, và giá trị âm có thể đặt dấu trừ ở vị trí khác.

Một lỗi phổ biến là tự nối:

~~~java
String display = currency.getSymbol(locale)
        + numberFormatter.format(amount);
~~~

Đoạn trên chỉ là minh họa. Nó ngầm bắt ký hiệu đứng trước, không quan tâm khoảng cách, dấu âm hoặc mẫu tiền tệ của locale. Với một số vùng, chính sách tự ghép này tạo ra cách trình bày không tự nhiên.

Thay vào đó, để runtime quyết định theo locale:

~~~java
NumberFormat money =
        NumberFormat.getCurrencyInstance(locale);
money.setCurrency(currency);
String display = money.format(amount);
~~~

Đoạn này cần import **java.text.NumberFormat**, biến **Locale locale**, **Currency currency** và giá trị **amount**. Hàm factory quyết định bố cục dựa trên locale; **setCurrency** chỉ định đơn vị tiền cụ thể. Giá trị **amount** không được tự chuyển đổi tỷ giá.

### 3.1. Ký hiệu tiền không phải lúc nào cũng duy nhất

**$** có thể được dùng cho nhiều đồng tiền. **Currency.getSymbol(locale)** có thể trả về một ký hiệu địa phương hóa hoặc dạng phân biệt như mã tiền tùy trường hợp và dữ liệu runtime. Vì vậy:

- Giao dịch và lưu trữ phải dựa vào **mã tiền ISO**, không dựa vào ký hiệu hiển thị.
- Ký hiệu trước/sau số phải tuân thủ pattern, không suy từ ký hiệu.
- Nếu sản phẩm cần luôn in **USD**, **CAD** hay **AUD**, có thể dùng mẫu cho mã ISO hoặc in mã tiền thành phần riêng, nhưng phải giữ vị trí, khoảng trắng và dấu âm theo hợp đồng đã chọn.

Không nên giả định một ký tự **$** đủ để suy ra Currency trong parser hoặc trong hóa đơn.

## 4. Khoảng trắng Unicode trong chuỗi tiền

Các chuỗi dưới đây có thể giống nhau ở một font, nhưng khác code point:

| Code point | Tên | Đặc tính cần biết |
| --- | --- | --- |
| **U+0020** | SPACE | Dấu cách thường, có thể cho phép xuống dòng |
| **U+00A0** | NO-BREAK SPACE (NBSP) | Dấu cách không ngắt dòng |
| **U+202F** | NARROW NO-BREAK SPACE (NNBSP) | Dấu cách hẹp, không ngắt dòng |
| **U+2009** | THIN SPACE | Dấu cách mảnh, không nhất thiết là ký tự được một locale tiền tệ dùng |
| **U+200E / U+200F** | LEFT-TO-RIGHT MARK / RIGHT-TO-LEFT MARK | Ký tự điều hướng hai chiều, **không phải dấu cách** |
| **U+061C** | ARABIC LETTER MARK | Dấu điều hướng bidi, **không phải dấu cách** |

Ví dụ một chuỗi **1 234,50 €** có thể sử dụng **NNBSP** để nhóm chữ số và **NBSP** giữa số với ký hiệu €. Nếu bạn thay tất cả ký tự khoảng trắng bằng U+0020, kết quả có thể trông giống ban đầu nhưng thay đổi hành vi xuống dòng và quy tắc hiển thị.

**Không gán cố định rằng tất cả locale tiếng Pháp luôn dùng U+202F và U+00A0.** Tập dữ liệu locale và phiên bản JDK có thể khác. Kiểm tra **code point của chuỗi thực tế** là cách đáng tin hơn việc nhìn chuỗi trên terminal.

### 4.1. Vì sao không nên dùng trim hoặc replaceAll một cách tùy tiện?

Trong Java:

- **String.trim()** có quy tắc loại bỏ các ký tự ở hai đầu theo khoảng mã nhỏ, không phải bộ xử lý Unicode whitespace đầy đủ.
- **String.strip()** dựa vào **Character.isWhitespace**, vốn không xem mọi ký tự no-break space là whitespace cần bỏ.
- Biểu thức chính quy **\\s** theo cấu hình mặc định không thể được mặc nhiên xem là “mọi khoảng trắng Unicode”.
- **Character.isSpaceChar** và **Character.isWhitespace** có phạm vi khác nhau; kiểm tra chúng theo mục đích.

Đặc biệt, việc thay hàng loạt khoảng trắng trong chuỗi tiền có thể biến NBSP thành SPACE, làm số và ký hiệu bị tách sang hai dòng trên giao diện. Nên giữ nguyên output formatter khi gửi cho tầng hiển thị, hoặc áp dụng một quy tắc chuẩn hóa được kiểm thử kỹ nếu thực sự cần.

### 4.2. Cách kiểm tra chính xác code point

Khi chuỗi trông có khoảng cách lạ, dùng **String.codePoints()** để kiểm tra. Đây là phương pháp không phụ thuộc font và không làm mất ký tự vô hình.

**File CurrencyCodePoints.java**

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyCodePoints {
    public static void main(String[] args) {
        Locale locale = Locale.FRANCE;
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(Currency.getInstance("EUR"));

        String result = formatter.format(1234.5);
        System.out.println("locale=" + locale.toLanguageTag());
        System.out.println("length=" + result.length());

        result.codePoints().forEach(cp ->
                System.out.printf(
                        Locale.ROOT, "U+%04X%n", cp));
    }
}
~~~

Lưu thành **CurrencyCodePoints.java**, chạy:

~~~bash
javac -encoding UTF-8 CurrencyCodePoints.java
java CurrencyCodePoints
~~~

Output đầu tiên bắt đầu bằng **locale=fr-FR**; các dòng tiếp theo cho biết độ dài UTF-16 và từng code point của chính output do runtime hiện tại sinh ra. **Không cố định toàn bộ stdout** vì đây là công cụ chẩn đoán trực tiếp sự khác biệt dữ liệu locale của JDK. Hãy đối chiếu những code point như **U+0020**, **U+00A0**, **U+202F**, ký hiệu tiền và chữ số.

Lưu ý **String.length()** đếm đơn vị UTF-16, còn **codePoints()** duyệt các điểm mã Unicode. Không nhầm hai số đo khi chuỗi có ký tự ngoài BMP.

## 5. Ví dụ khảo sát nhiều locale mà không tự khẳng định dấu cách

Chạy cùng một giá trị và **cùng một Currency** dưới một vài locale là cách thấy khác biệt trong bố cục mà không trộn nó với việc đổi đơn vị tiền.

**File CurrencyLocaleSurvey.java**

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public class CurrencyLocaleSurvey {
    public static void main(String[] args) {
        Currency eur = Currency.getInstance("EUR");
        BigDecimal amount = new BigDecimal("-1234.50");

        List<Locale> locales = List.of(
                Locale.US,
                Locale.GERMANY,
                Locale.FRANCE,
                Locale.forLanguageTag("vi-VN"));

        for (Locale locale : locales) {
            NumberFormat formatter =
                    NumberFormat.getCurrencyInstance(locale);
            formatter.setCurrency(eur);

            System.out.println(
                    locale.toLanguageTag() + ": "
                    + formatter.format(amount));
        }
    }
}
~~~

Lưu **CurrencyLocaleSurvey.java**, chạy:

~~~bash
javac -encoding UTF-8 CurrencyLocaleSurvey.java
java CurrencyLocaleSurvey
~~~

Chương trình in bốn dòng bắt đầu lần lượt bằng **en-US:**, **de-DE:**, **fr-FR:** và **vi-VN:**. Phần giá trị sau dấu hai chấm phụ thuộc dữ liệu locale của JDK: vị trí ký hiệu, dấu âm, khoảng trắng và dấu phân cách có thể khác. Đó là điều cần quan sát chứ không nên hardcode thành một stdout duy nhất cho tất cả bản phát hành Java.

**Vì sao dùng cùng EUR?** Nếu để factory tự chọn currency từ locale, khác biệt xuất ra còn bao gồm việc en-US mặc định USD, de-DE mặc định EUR và vi-VN có thể gợi ý VND. Cùng một currency giúp phép so sánh tập trung vào quy tắc định dạng.

**Vì sao dùng số âm?** Nó cho thấy vị trí dấu âm so với ký hiệu và số, không chỉ vị trí ký hiệu so với số dương.

## 6. Các kiểu hiển thị âm: dấu trừ, prefix/suffix, dấu ngoặc

Định dạng tiền âm có thể có các cấu trúc khác nhau theo locale hoặc theo yêu cầu thiết kế:

~~~text
-€1,234.50
€-1,234.50
-1.234,50 €
(€1,234.50)
(1.234,50 €)
~~~

Các chuỗi trên là **kiểu biểu diễn minh họa**, không phải cam kết mọi kiểu đều do mỗi locale tự động tạo ra. Việc dùng ngoặc tròn thường gặp trong một số báo cáo kế toán; nó không nhất thiết là pattern mặc định của **NumberFormat.getCurrencyInstance(locale)** cho cùng locale.

Trong **DecimalFormat**, formatter có thể có:

- **Positive prefix** và **positive suffix**.
- **Negative prefix** và **negative suffix**.
- **Pattern dương và âm** ngăn cách bằng dấu chấm phẩy trong ngữ pháp pattern.
- Ký hiệu dấu âm từ **DecimalFormatSymbols**, có thể được áp dụng khi không đặt nhánh âm riêng.

Nhánh âm quan trọng vì nó quy định cả vị trí dấu và phần văn bản đi kèm. Đừng xử lý số âm bằng cách nối dấu trừ phía trước chuỗi tiền dương: bạn có thể tạo ra sai vị trí dấu, hai dấu trừ hoặc mất kiểu trình bày mà locale định nghĩa.

### 6.1. Pattern tiền tệ của DecimalFormat

Một ví dụ pattern tùy chỉnh:

~~~text
¤#,##0.00;(¤#,##0.00)
~~~

Trong pattern chuẩn:

- **¤** là placeholder biểu diễn ký hiệu tiền tệ.
- **#,##0.00** mô tả chữ số, dấu phân nhóm và hai chữ số thập phân.
- **;** tách nhánh dương và âm.
- **(...)** tạo cách biểu diễn số âm bằng cặp ngoặc.

Với symbols Hoa Kỳ và một currency phù hợp, pattern đó có thể tạo dạng **$1,234.50** và **($1,234.50)**. Chú ý: **pattern được ứng dụng viết tường minh**, không phải khẳng định kiểu kế toán mặc định của locale đó.

Nếu ứng dụng cần in mã ISO thay cho ký hiệu, pattern có thể dùng **¤¤** tùy định dạng mong muốn; cần kiểm tra hỗ trợ của runtime và bố cục khi kết hợp cùng dấu âm/khoảng trắng. Không tự thay ký hiệu bằng **String.replace** sau khi format, vì điều đó có thể làm mất cấu trúc của pattern.

### 6.2. Prefix và suffix không phải lúc nào cũng chỉ có dấu trừ

Một DecimalFormat có thể cung cấp **getPositivePrefix()**, **getPositiveSuffix()**, **getNegativePrefix()**, **getNegativeSuffix()** và các setter tương ứng. Khi inspect formatter được tạo bởi factory, các chuỗi này hữu ích để hiểu dấu âm và vị trí ký hiệu.

Nhưng chỉ xem prefix/suffix chưa đủ để kết luận toàn bộ code point đầu ra: phần số còn có dấu nhóm, dấu thập phân, chữ số bản địa và dấu hiệu bidi.

## 7. Ví dụ hoàn toàn xác định: khoảng trắng và định dạng âm tự cấu hình

Khi cần một hợp đồng output **bất biến** cho báo cáo cụ thể, ứng dụng có thể tự thiết lập pattern và symbols, thay vì phụ thuộc kiểu mặc định của locale. Ví dụ sau cố ý dùng **NNBSP** (U+202F) giữa các nhóm chữ số, dấu phẩy làm thập phân, SPACE (U+0020) trước mã **EUR**, và dấu ngoặc cho số âm.

**File ExplicitCurrencyLayout.java**

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;
import java.util.stream.Collectors;

public class ExplicitCurrencyLayout {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.ROOT);

        symbols.setGroupingSeparator('\u202F');
        symbols.setDecimalSeparator(',');

        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00 'EUR';(#,##0.00 'EUR')",
                symbols);

        String positive =
                formatter.format(new BigDecimal("1234.50"));
        String negative =
                formatter.format(new BigDecimal("-1234.50"));

        System.out.println(
                "positive=" + visible(positive));
        System.out.println(
                "negative=" + visible(negative));
        System.out.println(
                "spaces=" + spaceCodes(positive));
    }

    private static String visible(String value) {
        return value.replace("\u202F", "<NNBSP>");
    }

    private static String spaceCodes(String value) {
        return value.codePoints()
                .filter(Character::isSpaceChar)
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(","));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ExplicitCurrencyLayout.java
java ExplicitCurrencyLayout
~~~

**Stdout chính xác theo cấu hình tường minh:**

~~~text
positive=1<NNBSP>234,50 EUR
negative=(1<NNBSP>234,50 EUR)
spaces=U+202F,U+0020
~~~

Trong đoạn code, **\\u202F** biểu diễn Unicode NARROW NO-BREAK SPACE; khi biên dịch Java, escape Unicode được xử lý và ký tự NNBSP xuất hiện trong literal. Hàm **visible** thay nó bằng một nhãn dễ đọc chỉ để chẩn đoán. Dòng **spaces** sử dụng **Character.isSpaceChar** để nhận diện các ký tự kiểu space separator; kết quả có cả **U+202F** giữa các nhóm và **U+0020** trước **EUR**.

Chú ý về chính sách:

1. Đây là **định dạng do ứng dụng quy định**, không phải mặc định của Đức, Pháp hay Việt Nam.
2. **EUR** là hậu tố literal cố định. Trong ứng dụng thực tế, cần lấy Currency từ dữ liệu giao dịch và chọn định dạng phù hợp; không hardcode EUR nếu sản phẩm xử lý nhiều đồng tiền.
3. Dấu ngoặc được tạo qua **nhánh âm**; không phải phép trừ hay cách mã hóa số âm trong cơ sở dữ liệu.
4. Pattern dùng cú pháp chuẩn **#,##0.00** dù dấu được in thực tế là NNBSP và phẩy.
5. **BigDecimal** giữ giá trị chính xác; formatter không thay đổi nội dung BigDecimal.

Nếu nghiệp vụ muốn cùng hợp đồng nhưng ký hiệu thật của Currency, hãy định nghĩa rõ vị trí của ký hiệu và dùng DecimalFormat/NumberFormat phù hợp thay vì chèn chuỗi tùy tiện sau khi đã định dạng.

## 8. Pattern chuẩn và pattern bản địa hóa

Một ngộ nhận là thấy chuỗi **1.234,50 €** rồi dùng chuỗi pattern **#.##0,00 €** với **applyPattern(...)**. Trong cú pháp pattern chuẩn của Java:

- **.** là vị trí thập phân **trong pattern**.
- **,** biểu diễn nhóm chữ số **trong pattern**.
- **0** là chữ số bắt buộc.
- **#** là chữ số tùy chọn.
- **¤** là ký hiệu tiền tệ đặc biệt.
- **;** tách nhánh dương/âm.

Ký tự thực tế in ra lấy từ **DecimalFormatSymbols**. Vì vậy pattern chuẩn **#,##0.00** áp vào symbols **de-DE** có thể hiển thị số như **1.234,50**.

Khi thực sự cần mẫu được viết bằng các ký hiệu địa phương, dùng **applyLocalizedPattern(...)** và **toLocalizedPattern(...)** với symbols tương ứng, không dùng nhầm **applyPattern**. Với cấu hình ứng dụng, mẫu chuẩn thường dễ quản lý và ít nhầm hơn.

Các phép thay thế pattern đơn giản không giải quyết hết khoảng trắng hoặc ký hiệu âm; pattern phải được kiểm thử với currency, số dương, số âm, số 0 và các mức giá trị.

## 9. DecimalFormatSymbols chứa ký hiệu nào liên quan đến tiền?

**DecimalFormatSymbols** cung cấp các API đáng chú ý:

| API | Công dụng |
| --- | --- |
| **getDecimalSeparator()** | Dấu thập phân số thông thường |
| **getGroupingSeparator()** | Dấu phân nhóm chữ số |
| **getMonetaryDecimalSeparator()** | Dấu thập phân được dùng trong ngữ cảnh tiền tệ |
| **getCurrencySymbol()** | Ký hiệu tiền đang cấu hình |
| **getInternationalCurrencySymbol()** | Mã tiền ISO 4217 |
| **getMinusSign()** | Ký tự dấu trừ |
| **getPercent() / getPerMill()** | Ký hiệu phần trăm/phần nghìn |
| **getZeroDigit()** | Ký tự số 0 dùng cho bộ chữ số thích hợp |
| **getExponentSeparator()** | Ký hiệu phân cách mũ trong định dạng khoa học |

Các getter/setter giúp quan sát hoặc thay đổi từng phần. Ví dụ, nếu muốn dấu thập phân tiền tệ khác dấu thập phân thường, có **setMonetaryDecimalSeparator(...)**. Không đồng nhất điều đó với dấu thập phân mọi loại số.

Một điểm quan trọng: **DecimalFormatSymbols** chứa một số ký hiệu, nhưng **không phải toàn bộ bố cục tiền tệ nằm trong một ký hiệu đơn lẻ**. Vị trí Currency, tiền tố/hậu tố âm và các khoảng trắng gắn với chúng còn được mô tả bởi **pattern của DecimalFormat** được runtime lựa chọn. Vì vậy muốn kiểm tra vị trí ký hiệu, cần quan sát cả pattern và output.

### 9.1. Có thể lấy DecimalFormat từ NumberFormat không?

Thông thường factory tiền tệ trên các JDK phổ biến trả về DecimalFormat, nhưng hợp đồng phương thức **NumberFormat.getCurrencyInstance(locale)** trả kiểu **NumberFormat**. Không nên luôn ép kiểu mà không kiểm tra.

~~~java
NumberFormat number =
        NumberFormat.getCurrencyInstance(locale);

if (number instanceof DecimalFormat decimal) {
    System.out.println(decimal.toPattern());
    System.out.println(decimal.getNegativePrefix());
    System.out.println(decimal.getNegativeSuffix());
}
~~~

Đây là đoạn minh họa trong một phương thức, cần import **java.text.NumberFormat**, **java.text.DecimalFormat** và biến **locale**. Với Java 17+, cú pháp **instanceof DecimalFormat decimal** hợp lệ. Nếu provider trả lớp NumberFormat khác, nhánh kiểm tra không chạy; vẫn có thể sử dụng factory để định dạng.

**toPattern()** trả pattern chuẩn hiện hành. **toLocalizedPattern()** trả pattern theo ký hiệu của symbols. Chúng phục vụ chẩn đoán/trình bày cấu hình, không phải cách duy nhất để dựng lại toàn bộ hành vi đã tùy chỉnh của một formatter bất kỳ.

### 9.2. Đổi ký hiệu sau khi tạo formatter

Nếu thay đổi symbols của formatter đã tạo, hãy dùng **getDecimalFormatSymbols()**, sửa bản trả về rồi **setDecimalFormatSymbols(...)** để cập nhật. Không trông đợi một object symbols bên ngoài được sửa sau constructor sẽ tự cập nhật mọi formatter đã tồn tại.

**DecimalFormat và NumberFormat có trạng thái mutable**, không mặc nhiên thread-safe. Tránh chia sẻ rồi thay currency, grouping, negative prefix/suffix giữa hai request đồng thời.

## 10. Khoảng trắng và dấu âm trong văn bản hai chiều

Với các ngôn ngữ viết từ phải sang trái (RTL), ký hiệu tiền, chữ số và dấu âm có thể cần những ký tự điều hướng bidirectional để hiển thị đúng. Một chuỗi Unicode có thể chứa **U+200E**, **U+200F** hoặc **U+061C**, dù không nhìn thấy chúng.

Cần phân biệt:

- **Khoảng trắng:** tách phần số và ký hiệu, có thể cấm ngắt dòng.
- **Dấu âm:** có ý nghĩa về dấu giá trị và trình bày.
- **Ký tự điều hướng bidi:** giúp văn bản hiển thị đúng thứ tự trực quan trong ngữ cảnh trộn hướng trái/phải.

Không tự xóa mọi ký tự “vô hình” trước khi hiển thị tiền tệ. Làm vậy có thể khiến dấu âm và ký hiệu bị đảo hướng khi một chuỗi RTL được đặt trong trang LTR. Nếu có yêu cầu bảo mật/chuẩn hóa đầu vào, cần tách **chuỗi hiển thị** và **giá trị được parse**; không xử lý bằng thao tác xóa ký tự hàng loạt không có chính sách.

Trong HTML hoặc ứng dụng UI, hướng văn bản và thành phần giao diện cũng ảnh hưởng thứ tự hiển thị. Đừng kết luận rằng dữ liệu đã sai chỉ vì terminal khác trình duyệt; kiểm tra code point, locale, Unicode bidi và rendering context.

## 11. Định dạng âm và yêu cầu kế toán

Nhiều hệ thống tài chính muốn phân biệt:

- **Biểu diễn âm phổ thông:** sử dụng dấu trừ ở vị trí được locale hỗ trợ.
- **Biểu diễn kế toán:** có thể dùng ngoặc hoặc quy tắc được tổ chức xác định.
- **Biểu diễn báo cáo:** có thể dùng cột riêng chỉ debit/credit, màu sắc hoặc chữ, nhưng không được coi màu sắc là thông tin âm duy nhất.

Java Core **NumberFormat.getCurrencyInstance(locale)** cung cấp kiểu tiền tệ địa phương hóa theo dữ liệu của JDK. Không suy rằng nó luôn có một phương thức riêng chọn “accounting style” tương đương mọi sản phẩm ICU/CLDR. Nếu báo cáo kế toán yêu cầu **(1,234.50)**, hãy viết pattern âm bằng DecimalFormat hoặc chọn formatter phù hợp, rồi kiểm thử.

Cần quan tâm đến **âm không**:

- Với **double**, giá trị **-0.0** tồn tại và có thể có cách trình bày khác 0.0.
- Với **BigDecimal**, dấu của một giá trị số 0 không được giữ như một trạng thái âm tương đương double.
- Khi làm tròn một số âm rất nhỏ tới 0.00, chuỗi đầu ra có thể giữ dấu âm theo formatter, dù giá trị hiển thị không còn phần khác 0.

Nếu nghiệp vụ quy định không hiển thị **-0,00**, cần quyết định ngưỡng và chuẩn hóa dữ liệu **trước** bước format, đặc biệt khi kết quả làm tròn về 0. Không nên sửa chuỗi đầu ra bằng replace dấu trừ một cách tùy tiện vì dễ gây lỗi với dấu trừ địa phương hóa và các ký hiệu bidi.

## 12. Rounding và số chữ số thập phân là quyết định riêng

Vị trí ký hiệu và khoảng trắng không xác định chính xác số chữ số phần lẻ. **Currency.getDefaultFractionDigits()** cung cấp một thông tin về số chữ số thập phân mặc định của currency; giá trị có thể là **-1** khi không áp dụng. **NumberFormat.getCurrencyInstance(locale)** sẽ có quy tắc fraction digits theo cấu hình của nó và dữ liệu locale.

Tuy nhiên:

1. Giá trị nghiệp vụ như **BigDecimal("1234.50")** không tự thay đổi vì formatter in hai chữ số.
2. Một đồng tiền có thể có quy tắc làm tròn tiền mặt khác số chữ số dùng cho thanh toán điện tử.
3. **setCurrency(...)** là khai báo currency, không quy đổi giá trị và không thay thế việc đặt fraction digits/rounding theo chính sách nghiệp vụ.
4. Nếu phải in một số chữ số xác định, hãy cấu hình **setMinimumFractionDigits**, **setMaximumFractionDigits** và **setRoundingMode** một cách tường minh.

Với dữ liệu tài chính, tránh thực hiện phép tính tiền bằng **double** khi cần độ chính xác thập phân. Ưu tiên **BigDecimal** và quy tắc rounding nghiệp vụ, sau đó mới đưa cho formatter. Format là **trình bày**, không phải tính toán tỷ giá hoặc kiểm tra số dư.

## 13. Phân tích chuỗi tiền đã bản địa hóa: rủi ro mất thông tin

Nếu chuỗi có một dấu cách no-break và dấu âm được bản địa hóa, parser sử dụng **NumberFormat** theo locale khác có thể đọc sai hoặc bỏ phần chuỗi. Không coi **Double.parseDouble("1 234,50 €")** là một parser tiền tệ theo locale; API này không được thiết kế để hiểu mọi ký hiệu địa phương hóa.

Khi cần đọc input người dùng:

1. **Xác định locale của input**, không lấy ngầm locale server.
2. Tạo formatter phù hợp và chỉ định Currency theo hợp đồng.
3. Với DecimalFormat, có thể cấu hình **setParseBigDecimal(true)** khi cần BigDecimal.
4. Dùng **ParsePosition** để kiểm tra toàn bộ văn bản đã được tiêu thụ; không chỉ kiểm tra parse trả một Number.
5. Xác minh Currency kỳ vọng, khoảng giá trị, chữ số và dấu âm theo yêu cầu sản phẩm.

Ví dụ minh họa:

~~~java
DecimalFormat decimal = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
decimal.setParseBigDecimal(true);

String input = "1.234,50";
ParsePosition pos = new ParsePosition(0);
Number amount = decimal.parse(input, pos);

if (amount == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid amount");
}
~~~

Đây là đoạn minh họa trong phương thức, cần import **DecimalFormat**, **DecimalFormatSymbols**, **Locale**, **ParsePosition**. Nó parse **số**, không tự xác nhận mã tiền trong một chuỗi tổng hợp. Với input như **1.234,50 €**, phải có chính sách nhận diện đơn vị tiền và khoảng trắng, không chỉ gỡ ký hiệu rồi parse số.

**Parser có thể lenient** về phân nhóm hoặc ký tự; việc tiêu thụ hết văn bản không phải là validator đầy đủ cho mọi yêu cầu nhập số. Khi dữ liệu là hợp đồng máy, thay vì parse chuỗi tiền đã format, hãy dùng cấu trúc dữ liệu có **amount** và **currency** riêng.

## 14. Những sai lầm thường gặp

### Sai lầm 1: Luôn đặt ký hiệu tiền phía trước

Tự nối **Currency.getSymbol(locale) + amount** sẽ bỏ qua vị trí và khoảng trắng theo mẫu. Dùng **NumberFormat.getCurrencyInstance(locale)** hoặc một pattern đã được sản phẩm quy định.

### Sai lầm 2: Coi mọi khoảng trống là U+0020

NBSP và NNBSP có thể được dùng để ngăn ngắt dòng hoặc tạo khoảng cách hẹp. Chuỗi nhìn giống nhau nhưng byte/code point khác nhau. Dùng **String.codePoints()** để xác minh; không chuẩn hóa bừa bằng trim, strip hay regex.

### Sai lầm 3: Giả định output fr-FR/de-DE bất biến giữa mọi JDK

Dữ liệu CLDR, locale provider và ký hiệu tiền có thể được cập nhật. Kiểm thử hành vi theo locale hoặc cố định runtime/formatter nếu phải so khớp exact. Tránh golden test phụ thuộc mặc định ngầm của máy CI.

### Sai lầm 4: Tự thêm dấu trừ trước chuỗi tiền

Điều này có thể làm sai bố cục âm của locale hoặc pattern kế toán. Format trực tiếp **giá trị âm** với formatter phù hợp; nếu cần kiểu kế toán, định nghĩa nhánh âm trong pattern.

### Sai lầm 5: Hiểu ngoặc tròn là quy tắc mặc định toàn cầu

**(€1,234.50)** có thể là lựa chọn của báo cáo kế toán; không phải locale nào cũng mặc định dùng ngoặc. Viết rõ lựa chọn sản phẩm và kiểm thử số âm.

### Sai lầm 6: Trộn currency với locale

Locale có thể gợi ý currency thông thường cho vùng, nhưng không biết đơn vị giao dịch. Một hóa đơn USD cho người dùng ở Việt Nam phải giữ mã USD từ nghiệp vụ.

### Sai lầm 7: Dùng ký hiệu hiển thị làm mã tiền

Ký hiệu **$** không xác định duy nhất USD. Dùng **Currency.getCurrencyCode()** hoặc mã tiền từ dữ liệu giao dịch để lưu trữ/kiểm tra.

### Sai lầm 8: Dùng formatter mutable làm singleton rồi đổi currency mỗi request

**NumberFormat** và **DecimalFormat** không nên chia sẻ có sửa đổi đồng thời. Tạo instance theo nhu cầu hoặc có chiến lược đồng bộ/cách ly rõ ràng; không thay đổi **Locale.setDefault** để xử lý từng người dùng.

### Sai lầm 9: Đồng nhất chuẩn hóa chuỗi với chuẩn hóa giá trị tiền

Xóa dấu cách và ký hiệu sau khi format có thể làm mất ngữ nghĩa hiển thị. Giá trị nghiệp vụ phải được giữ ở dạng dữ liệu có kiểu; chuỗi địa phương hóa chỉ là view.

### Sai lầm 10: Test bằng mắt thay vì inspect Unicode

Terminal, browser và font có thể hiện các dấu cách trông giống nhau. Nếu có nghi ngờ, log code point hoặc so sánh chuỗi có tính đến Unicode, không chỉ xem ảnh chụp màn hình.

## 15. Ma trận kiểm thử thiết yếu

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Cùng EUR ở **en-US**, **de-DE**, **fr-FR**, **vi-VN** | Ký hiệu, vị trí và phân cách theo locale của runtime |
| Giá trị **1234.5**, **-1234.5**, **0** | Bố cục dương/âm và số 0 |
| Giá trị rất nhỏ âm gần 0 | Quy tắc rounding và cách hiển thị âm không |
| Chuỗi có U+00A0/U+202F | Không làm mất no-break space khi render/xử lý |
| Mẫu explicit với NNBSP | Test được output code point chính xác |
| Currency khác currency mặc định locale | Giữ đúng đơn vị tiền giao dịch |
| Pattern kế toán có ngoặc | Dạng âm rõ ràng và không phụ thuộc ngầm locale |
| Chuỗi RTL có ký tự bidi | Dấu âm, ký hiệu và số không bị đảo sai hướng |
| Parse input dùng đúng locale | Không phân tích sai dấu nhóm/thập phân |
| ParsePosition sau parse | Không bỏ sót hậu tố hoặc phần dư |
| JDK và CLDR bản khác | Phát hiện thay đổi output mặc dù locale giống nhau |
| Request đồng thời khác locale/currency | Không rò rỉ cấu hình formatter giữa request |

Với ứng dụng có hợp đồng xuất dữ liệu máy bất biến, thử thêm các test không dùng locale người dùng: **BigDecimal.toPlainString()** hoặc một định dạng số kỹ thuật được chỉ định rõ thường phù hợp hơn chuỗi định dạng tiền tệ. Đầu ra JSON nên có giá trị và currency riêng.

Nếu snapshot test so sánh từng ký tự của chuỗi tiền, phải quyết định liệu muốn test **dữ liệu locale của runtime** hay **quy tắc ứng dụng**. Với quy tắc ứng dụng, kiểm soát DecimalFormatSymbols và pattern tường minh. Với dữ liệu locale, chạy và kiểm chứng trên các JDK nằm trong danh sách hỗ trợ.

## 16. Quy trình chẩn đoán khi dev và production hiển thị tiền khác nhau

Giả sử dev hiển thị ký hiệu EUR cách số bằng một khoảng, nhưng máy chủ có khoảng hẹp hoặc dấu âm ở nơi khác. Phân tích theo các bước:

1. **So sánh dữ liệu gốc:** BigDecimal amount, currency code và việc số có âm hay không.
2. **So sánh locale:** giá trị locale được truyền thực sự cho NumberFormat, không chỉ default JVM.
3. **So sánh JDK:** phiên bản runtime và dữ liệu locale/provider có thể khác.
4. **In code point của output:** phát hiện U+0020, U+00A0, U+202F hoặc ký tự bidi.
5. **Inspect formatter:** nếu là DecimalFormat, xem pattern, positive/negative prefix/suffix, symbols.
6. **Kiểm tra custom code:** tìm chỗ tự nối ký hiệu, replace whitespace, xóa dấu âm hoặc format trước rồi format lại.
7. **Đối chiếu hợp đồng sản phẩm:** định dạng theo người dùng hay phải cố định cho báo cáo/tài liệu.
8. **Sửa tại tầng đúng:** truyền locale/currency tường minh hoặc thiết lập pattern và symbols riêng nếu yêu cầu ổn định từng ký tự.
9. **Bổ sung kiểm thử:** gồm cả số âm, khoảng trắng Unicode và thay đổi runtime.

Không kết luận “bug Java” chỉ vì một chuỗi khác nhau: định dạng bản địa hóa **được phép** khác khi dữ liệu locale thay đổi. Điều cần làm là xác định xem khác biệt đó có phù hợp hợp đồng của sản phẩm hay không.

## 17. Checklist triển khai

- Xác định **amount** và **Currency** riêng khỏi chuỗi hiển thị.
- Chọn **Locale** của người xem hoặc locale được tổ chức quy định.
- Dùng **NumberFormat.getCurrencyInstance(locale)** khi mong muốn quy tắc bản địa hóa của runtime.
- Gọi **setCurrency(currency)** với đơn vị tiền đúng giao dịch, không chỉ suy từ locale.
- Không tự nối ký hiệu tiền vào trước/sau số trừ khi hợp đồng yêu cầu một layout đặc biệt đã được kiểm thử.
- Bảo toàn các khoảng trắng Unicode và ký tự bidi có ý nghĩa trình bày.
- Đừng coi mọi dấu cách là U+0020; chẩn đoán bằng code point.
- Format giá trị âm trực tiếp; chọn pattern kế toán nếu sản phẩm yêu cầu, không tự ghép dấu trừ.
- Nếu phải cố định từng ký tự, cấu hình **DecimalFormatSymbols** và pattern tường minh.
- Kiểm soát rounding, fraction digits, tiền mặt/điện tử và trường hợp âm không theo nghiệp vụ.
- Không parse chuỗi hiển thị bằng cách bỏ ký hiệu thủ công; nếu cần parse, biết locale và validate toàn bộ input.
- Không chia sẻ formatter mutable giữa các request thiếu cách ly; không dùng Locale.setDefault theo người dùng.
- Kiểm thử ít nhất số dương, số âm, số 0, tiền khác locale, Unicode spaces, JDK/CLDR và môi trường UI LTR/RTL nếu có hỗ trợ.

## 18. Tổng kết

**Khoảng trắng, vị trí ký hiệu và định dạng âm của chuỗi tiền tệ là kết quả phối hợp giữa locale, dữ liệu JDK, Currency, pattern và DecimalFormatSymbols.** Sự khác nhau không chỉ nằm ở dấu phẩy hay dấu chấm: khoảng trắng có thể là NBSP/NNBSP, dấu âm có thể đứng ở nhiều vị trí, và cách viết kế toán bằng ngoặc có thể là yêu cầu riêng của sản phẩm.

Với giao diện đa ngôn ngữ, hãy để **NumberFormat.getCurrencyInstance(locale)** thể hiện quy tắc địa phương hóa rồi chỉ định currency thực tế. Với báo cáo có hợp đồng cố định từng ký tự, hãy dùng pattern và DecimalFormatSymbols tường minh, nhất là về khoảng trắng và nhánh âm. Dù ở trường hợp nào, luôn giữ **giá trị tiền có kiểu và mã tiền tệ riêng**, kiểm tra code point khi có nghi ngờ, và coi chuỗi đã format là cách trình bày dành cho người đọc chứ không phải nguồn dữ liệu tài chính.
