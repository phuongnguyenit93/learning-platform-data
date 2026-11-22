# Kiểm thử định dạng theo locale và chuyển mã hai chiều trong Java

Ứng dụng Java thường cần trình bày số, ngày tháng và văn bản theo ngôn ngữ/vùng miền (**Locale**), đồng thời chuyển đổi giữa **String (ký tự Unicode)** và **byte[] (dữ liệu có mã hóa Charset)**. Hai loại chuyển đổi này dễ gây lỗi âm thầm: chuỗi hiển thị đúng ở máy phát triển nhưng sai trên máy khác; dấu thập phân bị đọc nhầm; ký tự tiếng Việt hoặc emoji biến thành dấu hỏi; dữ liệu chỉ được phân tích một phần mà chương trình vẫn coi là hợp lệ.

Bài học tập trung vào **kiểm thử có tính tái lập**, **round-trip (chuyển đổi rồi chuyển ngược)** và cách phân biệt **khôi phục được dữ liệu gốc**, **khôi phục được giá trị ngữ nghĩa**, hoặc **mất thông tin không thể phục hồi**. Các ví dụ dùng Java 17+ và cố ý chọn Locale/Charset cụ thể để không phụ thuộc cài đặt mặc định của máy.

## 1. Hai loại chuyển đổi cần kiểm thử riêng

| Luồng xử lý | API Java thường dùng | Giá trị đầu vào và đầu ra | Điều cần kiểm thử |
| --- | --- | --- | --- |
| Số → văn bản theo vùng miền | NumberFormat, DecimalFormat, String.format(Locale, ...) | Number/BigDecimal → String | Dấu thập phân, phân nhóm, làm tròn, số chữ số, ký hiệu âm |
| Văn bản theo vùng miền → số | NumberFormat.parse, DecimalFormat.parse | String → Number | Đúng Locale, dùng hết đầu vào, độ chính xác, lỗi dữ liệu |
| Ngày → văn bản theo vùng miền | DateTimeFormatter.withLocale(...) | LocalDate/... → String | Thứ tự ngày-tháng, tên tháng, độ dài và vùng miền |
| Văn bản ngày → ngày | LocalDate.parse(..., formatter) | String → LocalDate | Ngày hợp lệ, đúng formatter, không mất thông tin cần thiết |
| Chuỗi Unicode → byte | String.getBytes(Charset), CharsetEncoder | String → byte[] | Charset đích biểu diễn được ký tự, có thay thế ký tự hay không |
| Byte → chuỗi Unicode | new String(bytes, Charset), CharsetDecoder | byte[] → String | Charset giải mã đúng, byte lỗi, không âm thầm làm mất dữ liệu |

**Locale không phải Charset.** Locale điều khiển quy tắc biểu diễn/thông dịch văn bản theo ngôn ngữ và vùng miền (ví dụ 1.234,50 so với 1,234.50). Charset quy định cách biến nội dung ký tự thành byte và ngược lại (ví dụ UTF-8 hoặc ISO-8859-1). Chọn Locale.GERMANY không tự biến dữ liệu thành một bộ mã hóa nào đó; chọn UTF-8 cũng không quyết định cách hiển thị số thập phân.

## 2. Chọn điều kiện kiểm thử có thể lặp lại

Một bài kiểm thử tốt cần tránh phụ thuộc môi trường chạy. Nên làm rõ:

1. **Locale cụ thể:** ví dụ Locale.US, Locale.GERMANY, Locale.FRANCE hoặc Locale.forLanguageTag("vi-VN"), thay vì tùy tiện lấy Locale.getDefault().
2. **Charset cụ thể:** ví dụ StandardCharsets.UTF_8, StandardCharsets.ISO_8859_1, StandardCharsets.US_ASCII; tránh mã hóa mặc định nếu đang kiểm thử giao thức/tệp.
3. **Quy tắc định dạng:** số chữ số thập phân, phân nhóm hàng nghìn, kiểu làm tròn, định dạng ngày và timezone khi có thời điểm tuyệt đối.
4. **Miền dữ liệu:** giá trị 0, số âm, biên lớn, số có phần thập phân, dấu phân nhóm, chuỗi có dấu tiếng Việt, ký tự ngoài BMP (emoji), chuỗi rỗng và dữ liệu sai.
5. **Hợp đồng round-trip:** cần bằng nhau **từng ký tự**, **từng byte** hay chỉ **giá trị số/ngày**?

Các API của Java dùng dữ liệu vùng miền từ JDK (bao gồm nhà cung cấp dữ liệu locale). Chuỗi hiển thị cụ thể, tên tháng hoặc dấu cách phân nhóm có thể thay đổi tùy Locale, cấu hình và phiên bản JDK. Vì vậy, các bài test hợp đồng nên kết hợp: dữ liệu có quy tắc cố định do ứng dụng kiểm soát; và kiểm tra **round-trip** thay vì cố định mọi chuỗi bản địa hóa.

## 3. Kiểm thử định dạng và phân tích số theo Locale

Ở Mỹ, chuỗi biểu diễn số có thể dùng dấu phẩy phân nhóm và dấu chấm thập phân; ở Đức thường đảo ngược hai dấu. Nếu một chuỗi được định dạng theo Locale này rồi phân tích bằng Locale khác, chương trình có thể đọc sai giá trị hoặc chỉ đọc được một phần chuỗi.

Với dữ liệu tiền tệ hoặc độ chính xác thập phân quan trọng, **BigDecimal** thường an toàn hơn double trong các phép tính yêu cầu giá trị thập phân chính xác. DecimalFormat có thể cấu hình để parse thành BigDecimal.

### Ví dụ Java 17: format → parse và kiểm tra toàn bộ đầu vào

Tạo tệp **LocaleNumberRoundTrip.java**:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberRoundTrip {
    private static void verify(Locale locale, BigDecimal original) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale)
        );
        format.setParseBigDecimal(true);

        String rendered = format.format(original);
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(rendered, position);

        boolean consumedAll = parsed != null
                && position.getErrorIndex() < 0
                && position.getIndex() == rendered.length();

        boolean sameValue = parsed instanceof BigDecimal value
                && value.compareTo(original) == 0;

        System.out.println(locale.toLanguageTag() + ": " + rendered);
        System.out.println("full parse: " + consumedAll);
        System.out.println("same value: " + sameValue);
    }

    public static void main(String[] args) {
        BigDecimal number = new BigDecimal("1234.50");
        verify(Locale.US, number);
        verify(Locale.GERMANY, number);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LocaleNumberRoundTrip.java
java LocaleNumberRoundTrip
~~~

Kết quả với các dấu phân cách của Locale.US và Locale.GERMANY:

~~~text
en-US: 1,234.50
full parse: true
same value: true
de-DE: 1.234,50
full parse: true
same value: true
~~~

**Giải thích:** DecimalFormatSymbols xác định dấu thập phân/phân nhóm cho mỗi Locale; mẫu "#,##0.00" yêu cầu hai chữ số phần lẻ khi format. ParsePosition cho biết parser đã dùng tới vị trí nào. Kiểm tra **position.getIndex() == rendered.length()** ngăn trường hợp chỉ phân tích được một tiền tố.

**BigDecimal.compareTo(...) == 0** xác nhận giá trị toán học tương đương. BigDecimal.equals(...) còn xét cả scale, ví dụ 1.0 và 1.00 có giá trị số bằng nhau nhưng equals có thể khác nhau. Trong hệ thống cần giữ nguyên chính xác scale của đầu vào, format → parse có thể không đáp ứng hợp đồng đó nếu quy tắc định dạng đã làm tròn hoặc thay đổi số chữ số thập phân.

### Tại sao phải kiểm tra đã đọc hết chuỗi?

Một số parser định dạng số có thể chấp nhận tiền tố hợp lệ và dừng trước phần còn lại. Giả sử input là "1,234.50abc": parser có thể đọc được 1,234.50 nhưng không dùng hết các ký tự "abc". Việc parse trả về Number **không chứng minh** cả chuỗi đều hợp lệ.

Đoạn minh họa dưới đây (chưa phải chương trình độc lập) dùng cùng DecimalFormat đã cấu hình:

~~~java
String input = "1,234.50abc";
ParsePosition position = new ParsePosition(0);
Number number = format.parse(input, position);
boolean valid = number != null
        && position.getErrorIndex() < 0
        && position.getIndex() == input.length();
~~~

Kết quả valid là **false** nếu parser chỉ đọc được tiền tố số. Tùy chính sách ứng dụng, có thể cần kiểm tra nghiêm ngặt hơn về dấu phân nhóm, ký hiệu âm, khoảng trắng hoặc chuẩn hóa trước khi chấp nhận dữ liệu nhập. Kiểm tra dùng hết đầu vào **chưa bảo đảm** chuỗi đúng mọi quy tắc trình bày mong muốn, vì một số parser có tính dễ dãi (lenient).

## 4. Không phải mọi phép format → parse đều giữ nguyên giá trị

Nếu DecimalFormat chỉ hiển thị hai chữ số phần lẻ, giá trị có nhiều chữ số hơn có thể bị làm tròn:

~~~java
BigDecimal original = new BigDecimal("1.2345");
DecimalFormat format = new DecimalFormat(
        "0.00",
        DecimalFormatSymbols.getInstance(Locale.US)
);
format.setParseBigDecimal(true);

String text = format.format(original);  // "1.23" theo rounding mặc định ở trường hợp này
Number parsed = format.parse(text);    // 1.23, không phải 1.2345
~~~

Đoạn trên là minh họa cơ chế mất độ chính xác do định dạng. Khi bài toán yêu cầu kết quả làm tròn cụ thể, **đặt rõ RoundingMode** thay vì phụ thuộc giá trị mặc định của formatter.

Vì vậy phải chọn rõ hợp đồng:

- **Round-trip chính xác:** parse(format(x)) bằng x đối với mọi x được chấp nhận; chỉ có thể bảo đảm trong miền đầu vào và định dạng không mất thông tin.
- **Round-trip trong sai số:** kết quả có thể lệch trong ngưỡng nghiệp vụ khi chấp nhận làm tròn; dùng kiểm tra giới hạn thích hợp cho giá trị floating-point.
- **Round-trip chuẩn hóa:** format(parse(text)) có thể biến chuỗi thành cách biểu diễn chuẩn; không đòi hỏi từng ký tự văn bản giống đầu vào ban đầu.
- **Chỉ hiển thị:** nếu định dạng đã cố ý làm tròn/chuyển đơn vị, không nên dùng lại chuỗi hiển thị làm nguồn dữ liệu tính toán chính.

**Tránh biến dữ liệu nghiệp vụ thành chuỗi rồi parse trở lại chỉ để truyền giữa các lớp.** Giữ giá trị số/ngày ở dạng kiểu dữ liệu thích hợp, chỉ format ở ranh giới hiển thị hoặc xuất tệp có hợp đồng cụ thể.

## 5. String.format và DateTimeFormatter cũng cần Locale rõ ràng

String.format(Locale, ...) có thể định dạng số theo Locale. Ví dụ:

~~~java
String us = String.format(Locale.US, "%,.2f", 1234.5);
String de = String.format(Locale.GERMANY, "%,.2f", 1234.5);
~~~

Với hai Locale trên, kết quả tương ứng thông thường là **1,234.50** và **1.234,50**. Nhưng **String.format** tạo văn bản, không cung cấp riêng một parser đảo ngược hoàn toàn của chính cú pháp format; muốn round-trip cần định nghĩa parser thích hợp.

Với ngày, **java.time.format.DateTimeFormatter** cho phép tạo formatter bản địa hóa và dùng cùng formatter để phân tích. Ví dụ đầy đủ, tệp **LocaleDateRoundTrip.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleDateRoundTrip {
    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2026, 10, 23);
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(Locale.FRANCE);

        String text = formatter.format(original);
        LocalDate parsed = LocalDate.parse(text, formatter);

        System.out.println("date round-trip: " + original.equals(parsed));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleDateRoundTrip.java
java LocaleDateRoundTrip
~~~

~~~text
date round-trip: true
~~~

Không cố định chính xác tên tháng tiếng Pháp trong output mẫu vì dữ liệu locale của môi trường có thể thay đổi cách hiển thị; ví dụ chỉ kiểm tra **giá trị ngày sau khi phân tích lại**. Với thời điểm có múi giờ, cần xác định ZoneId và loại giá trị (Instant, ZonedDateTime, LocalDateTime...), vì một chuỗi chỉ ghi ngày hoặc giờ có thể không mang đủ thông tin để phục hồi một Instant. Khi cần dữ liệu trao đổi độc lập với ngôn ngữ/vùng miền, nên ưu tiên định dạng ISO hoặc định dạng hợp đồng rõ ràng.

## 6. Chuyển mã hai chiều: String ⇄ byte[]

**Charset** mô tả quy tắc ánh xạ từ chuỗi ký tự sang bytes và từ bytes trở lại ký tự. Hai thao tác phổ biến:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa; các biến và import cần được khai báo trong chương trình sử dụng. **Phải dùng đúng charset ở cả hai chiều**. Nếu bên gửi mã hóa UTF-8 nhưng bên nhận giải mã ISO-8859-1, những ký tự nhiều byte có thể biến thành chuỗi sai (mojibake).

Với **UTF-8**, một String gồm các Unicode scalar value hợp lệ (không chứa surrogate đơn lẻ chưa ghép cặp) có thể round-trip mà không mất thông tin: **decode(encode(s, UTF-8), UTF-8).equals(s)**. Không nên xem đó là cam kết cho mọi dãy char Java có thể tạo được, vì String có thể chứa surrogate bị lỗi.

Tệp **CharsetRoundTripDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetRoundTripDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt 😀";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);

        System.out.println("UTF-8 round-trip: "
                + original.equals(decoded));
        System.out.println("bytes stable: "
                + Arrays.equals(utf8, decoded.getBytes(StandardCharsets.UTF_8)));

        String word = "café";
        byte[] encoded = word.getBytes(StandardCharsets.UTF_8);
        String wrong = new String(encoded, StandardCharsets.ISO_8859_1);
        System.out.println("wrong charset preserved: "
                + word.equals(wrong));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CharsetRoundTripDemo.java
java CharsetRoundTripDemo
~~~

~~~text
UTF-8 round-trip: true
bytes stable: true
wrong charset preserved: false
~~~

Ở đây chuỗi có dấu và emoji kiểm tra đường đi có các ký tự nhiều byte. Dòng thứ ba cố ý giải mã sai charset và kiểm tra thất bại; đây là kiểm thử âm (negative test). Kiểm tra bytes sau khi giải mã lại cũng hữu ích khi hợp đồng cần **byte-level round-trip**, nhưng nếu chuỗi được chuẩn hóa hoặc định dạng truyền dữ liệu cho phép nhiều cách mã hóa tương đương thì phải định nghĩa lại tiêu chí kiểm thử.

## 7. Chuyển mã có mất thông tin và chế độ lỗi nghiêm ngặt

Một số charset không thể biểu diễn mọi ký tự Unicode. Ví dụ **US_ASCII** chỉ biểu diễn tập ký tự ASCII; nó không mã hóa trực tiếp được toàn bộ chữ tiếng Việt. Các phương thức tiện dụng như String.getBytes(Charset) thường **thay ký tự không biểu diễn được bằng replacement bytes**, khiến việc encode có vẻ thành công nhưng dữ liệu gốc đã mất.

Đừng chỉ gọi encode rồi mặc định thành công nghĩa là an toàn: phải **đối chiếu round-trip** hoặc dùng **CharsetEncoder** với CodingErrorAction.REPORT để yêu cầu báo lỗi.

Tạo tệp **StrictCharsetDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictCharsetDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt";

        byte[] lossyBytes = original.getBytes(StandardCharsets.US_ASCII);
        String lossy = new String(lossyBytes, StandardCharsets.US_ASCII);
        System.out.println("ASCII round-trip equal: "
                + original.equals(lossy));

        CharsetEncoder asciiEncoder = StandardCharsets.US_ASCII.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            asciiEncoder.encode(CharBuffer.wrap(original));
            System.out.println("strict ASCII rejected: false");
        } catch (CharacterCodingException ex) {
            System.out.println("strict ASCII rejected: true");
        }

        byte[] malformedUtf8 = {(byte) 0xC3, (byte) 0x28};
        CharsetDecoder utf8Decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            utf8Decoder.decode(ByteBuffer.wrap(malformedUtf8));
            System.out.println("malformed UTF-8 rejected: false");
        } catch (CharacterCodingException ex) {
            System.out.println("malformed UTF-8 rejected: true");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictCharsetDemo.java
java StrictCharsetDemo
~~~

~~~text
ASCII round-trip equal: false
strict ASCII rejected: true
malformed UTF-8 rejected: true
~~~

**Giải thích:** round-trip ASCII không khôi phục được chuỗi có dấu. Ở chế độ nghiêm ngặt, CharsetEncoder báo lỗi khi gặp ký tự không biểu diễn được; CharsetDecoder báo lỗi với byte UTF-8 sai cú pháp. Nếu ứng dụng cần an toàn dữ liệu, phải xác định cách xử lý khi lỗi phát sinh: báo lỗi cho người dùng, từ chối bản ghi, hoặc thay thế có ghi nhận rõ ràng. Không âm thầm chuyển sang charset khác rồi giả định sẽ luôn sửa được dữ liệu.

**Malformatted và unmappable khác nhau:** malformed biểu thị dãy byte/ký tự đầu vào không hợp lệ theo bộ mã; unmappable là ký tự hợp lệ nhưng charset đích không ánh xạ được. CharsetEncoder và CharsetDecoder có thể được cấu hình riêng để REPORT, REPLACE hoặc IGNORE theo hợp đồng dữ liệu. Khi yêu cầu bảo toàn văn bản, REPLACE/IGNORE làm mất thông tin.

## 8. Kiểm thử hai chiều không có nghĩa mọi dạng văn bản là một

Hai chuỗi có thể trông giống nhau nhưng không có cùng các đơn vị Unicode. Chẳng hạn, một chữ é có thể được biểu diễn bằng một code point **U+00E9**, hoặc bằng chữ e **U+0065** cộng dấu sắc tổ hợp **U+0301**. UTF-8 round-trip sẽ giữ đúng **biểu diễn ban đầu** của mỗi chuỗi hợp lệ; nó **không tự chuẩn hóa Unicode**.

Ví dụ tệp **NormalizationDemo.java**:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

public class NormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equal initially: "
                + composed.equals(decomposed));
        System.out.println("equal after NFC: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));

        String decoded = new String(
                decomposed.getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8
        );
        System.out.println("UTF-8 keeps representation: "
                + decomposed.equals(decoded));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NormalizationDemo.java
java NormalizationDemo
~~~

~~~text
equal initially: false
equal after NFC: true
UTF-8 keeps representation: true
~~~

Đây là ba phép kiểm tra khác nhau: **bằng nhau theo Java String.equals**, **tương đương sau chuẩn hóa NFC**, và **khôi phục chính xác code unit sau encode/decode UTF-8**. Không nên tùy tiện chuẩn hóa mọi dữ liệu khi chưa có yêu cầu nghiệp vụ: chuẩn hóa có thể thay đổi biểu diễn nguyên bản quan trọng với chữ ký số, so sánh bytes hoặc định dạng giao tiếp.

Nếu kiểm thử tìm kiếm không phân biệt dấu/hoa thường, còn phải xác định quy tắc collation/case folding theo Locale; chỉ thay đổi charset không giải quyết được vấn đề so sánh ngôn ngữ.

## 9. Thiết kế test theo bất biến (property) và trường hợp biên

Thay vì chỉ chụp một chuỗi hiển thị duy nhất, có thể đặt các bất biến rõ ràng:

| Loại kiểm thử | Bất biến đáng kiểm tra | Trường hợp biên |
| --- | --- | --- |
| Format/parse số trong miền an toàn | parse(format(x)) giữ giá trị số và dùng hết chuỗi | Số âm, số 0, rất lớn, phần lẻ, có làm tròn |
| Format/parse ngày với đầy đủ thông tin | parse(format(date)) bằng date | Ngày nhuận, cuối tháng, thay đổi Locale |
| UTF-8 round-trip | decode(encode(s)) bằng s với Unicode hợp lệ | Tiếng Việt, emoji, chuỗi rỗng, ký tự tổ hợp |
| Byte-level round-trip | encode(decode(bytes)) khôi phục bytes hợp lệ khi charset/hợp đồng bảo đảm | Dãy byte biên, BOM, dữ liệu sai |
| Negative test mã hóa | Charset không hỗ trợ phải báo lỗi hoặc round-trip thất bại rõ ràng | US_ASCII với chữ có dấu, surrogate đơn |
| Negative test parse | Chuỗi sai bị từ chối, không chỉ chấp nhận một tiền tố | Văn bản thừa, sai dấu phân cách, số không hợp lệ |
| Normalization | Bằng nhau sau quy tắc chuẩn hóa nếu hợp đồng yêu cầu | Ký tự dựng sẵn và tổ hợp |

Với input ngẫu nhiên hoặc property-based testing, hãy giới hạn miền sinh dữ liệu theo **hợp đồng thực sự**. Ví dụ, không thể yêu cầu mọi BigDecimal đều round-trip chính xác với format chỉ in hai chữ số phần lẻ; không thể yêu cầu US_ASCII giữ nguyên mọi ký tự Unicode. Test nên cố tình có cả **trường hợp thành công** và **trường hợp mong đợi thất bại**.

### Một bài kiểm thử tích hợp Java 17 không cần framework

Tệp **LocaleCharsetContractTest.java**:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleCharsetContractTest {
    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US)
        );
        format.setParseBigDecimal(true);

        BigDecimal value = new BigDecimal("1234.50");
        String formatted = format.format(value);
        ParsePosition pos = new ParsePosition(0);
        Number parsed = format.parse(formatted, pos);

        check(parsed instanceof BigDecimal, "Expected BigDecimal");
        check(pos.getIndex() == formatted.length(), "Partial parse");
        check(((BigDecimal) parsed).compareTo(value) == 0, "Value changed");

        String text = "Hà Nội 😀";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        check(text.equals(new String(bytes, StandardCharsets.UTF_8)),
                "UTF-8 round-trip failed");

        String wrong = new String(
                text.getBytes(StandardCharsets.US_ASCII),
                StandardCharsets.US_ASCII
        );
        check(!text.equals(wrong), "Expected lossy ASCII conversion");

        System.out.println("PASS: locale numeric round-trip");
        System.out.println("PASS: UTF-8 text round-trip");
        System.out.println("PASS: negative ASCII test");
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocaleCharsetContractTest.java
java LocaleCharsetContractTest
~~~

~~~text
PASS: locale numeric round-trip
PASS: UTF-8 text round-trip
PASS: negative ASCII test
~~~

Phương thức check ném AssertionError nếu hợp đồng bị vi phạm, nên phép kiểm tra chạy được mà không phụ thuộc vào tùy chọn -ea của Java. Khi dự án đã dùng JUnit, có thể chuyển các mệnh đề này thành assertEquals/assertThrows và chạy qua nhiều bộ tham số Locale, Charset, trường hợp âm; nhưng cốt lõi vẫn là **định nghĩa rõ điều kiện được chấp nhận**.

## 10. Những lỗi phổ biến trong hệ thống thực tế

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Định dạng số thay đổi theo máy | Dùng Locale mặc định hoặc dữ liệu vùng miền khác nhau | Truyền Locale tường minh, cố định formatter theo hợp đồng |
| Chuỗi số bị đọc sai hoặc một phần bị bỏ | Locale format và parse khác nhau; parser chỉ ăn tiền tố | Kiểm tra dấu, ParsePosition và tính hợp lệ toàn chuỗi |
| Mất phần lẻ khi chuyển đổi hai chiều | Định dạng làm tròn hoặc giới hạn số chữ số | Xác định miền round-trip, dùng BigDecimal và quy tắc rounding rõ |
| Ngày đổi cách viết theo JDK | Dữ liệu bản địa hóa/tên tháng khác nhau | Kiểm thử giá trị round-trip; chỉ đóng băng output nếu đặc tả yêu cầu |
| Tiếng Việt thành dấu hỏi | Charset không biểu diễn được ký tự và âm thầm thay thế | Chọn UTF-8 khi phù hợp, bật REPORT với yêu cầu không mất dữ liệu |
| Chữ bị lỗi kiểu mojibake | Bên encode/decode dùng Charset khác nhau | Theo dõi bytes tại ranh giới, thống nhất Charset end-to-end |
| Byte lỗi nhưng chương trình vẫn chạy | Decoder mặc định thay thế ký tự | Dùng CharsetDecoder với CodingErrorAction.REPORT nếu cần nghiêm ngặt |
| Emoji hoặc surrogate gây lỗi | String có surrogate chưa ghép cặp hoặc hệ thống không hỗ trợ | Tạo bộ dữ liệu Unicode hợp lệ, kiểm thử input malformed riêng |
| Hai chuỗi trông giống nhau nhưng equals false | Khác cách tổ hợp code point, ví dụ NFC và NFD | Xác định quy tắc normalization, không nhầm với charset |
| Test pass ở máy này nhưng fail ở CI | Locale/charset/timezone mặc định hoặc dữ liệu JDK khác | Chỉ định mọi tham số, khóa môi trường cần thiết và test bất biến |
| Dữ liệu gốc khác sau format rồi parse | Chuỗi hiển thị vốn là dạng mất thông tin | Chuyển qua kiểu dữ liệu chính xác; không dùng output cho tính toán chính |

## 11. Nguyên tắc triển khai an toàn

- **Dùng định dạng bản địa hóa cho UI, không dùng làm định dạng trao đổi mặc định.** Giao thức nên định nghĩa chuẩn rõ ràng, chẳng hạn số ở dạng quy định hoặc ngày ISO-8601; giao diện trình bày theo Locale người dùng.
- **Khi đọc văn bản từ file/API, xác định Charset đúng chỗ.** Nếu tệp hoặc giao thức chỉ định UTF-8, hãy dùng UTF-8 cả khi ghi và đọc, tránh phụ thuộc mặc định của hệ điều hành.
- **Tách lỗi định dạng và lỗi mã hóa.** Số sai do dấu phẩy/thập phân khác với bytes không thể giải mã; cách phát hiện và khắc phục cũng khác.
- **Không dùng phương thức parse dễ dãi làm xác thực duy nhất.** Kiểm tra đã xử lý hết đầu vào, miền giá trị và cú pháp do nghiệp vụ quy định.
- **Đặt quy tắc xử lý lỗi rõ ràng.** Nếu dữ liệu phải được bảo toàn, ưu tiên chế độ REPORT rồi xử lý ngoại lệ thay vì REPLACE/IGNORE.
- **Không giả định round-trip luôn giữ mọi thuộc tính.** Định dạng có thể làm tròn, bỏ timezone, thay scale; Unicode normalization và charset loss có thể làm thay đổi chính bytes hoặc nội dung.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một số được format theo Locale.GERMANY thành 1.234,50. Có nên parse lại bằng Locale.US không?

**Trả lời:** không, nếu không có một hợp đồng chuyển đổi rõ ràng. Dấu chấm và dấu phẩy có vai trò khác nhau. Dùng cùng Locale/format hoặc định dạng trao đổi được chuẩn hóa, và kiểm tra parser đã đọc hết đầu vào.

**Câu 2.** Gọi parse một chuỗi như "123abc" trả ra 123 có đủ chứng minh đầu vào hợp lệ không?

**Trả lời:** không. Cần kiểm tra toàn bộ chuỗi đã được tiêu thụ; có thể cần thêm điều kiện cú pháp/miền dữ liệu do nghiệp vụ đặt ra.

**Câu 3.** Vì sao encode rồi decode tiếng Việt bằng US_ASCII có thể trả về String khác ban đầu?

**Trả lời:** US_ASCII không biểu diễn được nhiều ký tự có dấu. Các API tiện dụng có thể thay bằng ký tự đại diện; muốn từ chối mất dữ liệu thì dùng encoder/decoder strict với REPORT.

**Câu 4.** Hai chuỗi é dạng dựng sẵn và e + dấu tổ hợp có thể cùng hiển thị, nhưng String.equals trả false. UTF-8 round-trip có tự làm chúng trở nên giống nhau không?

**Trả lời:** không. UTF-8 giữ được biểu diễn Unicode hợp lệ đã có; việc chuẩn hóa cần được thực hiện có chủ đích theo hợp đồng.

## 13. Ghi nhớ

Kiểm thử chuyển đổi hai chiều cần xác định **cái gì phải được giữ nguyên**. Với số/ngày, thường quan trọng nhất là **giá trị ngữ nghĩa** sau format rồi parse, đồng thời phải kiểm soát rounding, Locale, độ chính xác và việc phân tích hết chuỗi. Với văn bản, quan trọng là **ký tự Unicode** hoặc thậm chí **bytes** có được phục hồi, Charset ở hai chiều có nhất quán hay không, và phần nào của dữ liệu có thể bị thay thế.

Locale quy định **cách trình bày và diễn giải văn bản theo vùng miền**; Charset quy định **cách mã hóa nội dung thành bytes**. Đặt Locale/Charset tường minh, kiểm tra cả trường hợp đúng và sai, và dùng round-trip với điều kiện rõ ràng sẽ giúp bài kiểm thử ổn định hơn trên môi trường phát triển, máy chủ và CI.