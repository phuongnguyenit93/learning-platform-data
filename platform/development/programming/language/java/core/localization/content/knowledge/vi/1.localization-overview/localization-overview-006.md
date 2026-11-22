# Các nhóm API Java Core phục vụ bản địa hóa

Bản địa hóa (localization, l10n) là quá trình trình bày nội dung theo ngôn ngữ và quy ước của người dùng: câu chữ, chữ số, tiền tệ, ngày giờ, tên vùng, thứ tự sắp xếp và ranh giới ký tự. Trong Java Core, công việc này không thuộc một API duy nhất; nhiều nhóm API phối hợp với nhau. Bài này giới thiệu chức năng, cách lựa chọn và cách kết hợp các nhóm API đó trên Java 17+.

## 1. Phân biệt quốc tế hóa và bản địa hóa

- **Quốc tế hóa (internationalization, i18n):** Thiết kế chương trình để nội dung hiển thị có thể thay đổi theo ngôn ngữ/vùng mà không phải sửa logic nghiệp vụ. Ví dụ: lấy thông báo qua khóa thay vì ghi cứng trong mã nguồn.
- **Bản địa hóa (localization, l10n):** Cung cấp bản dịch và lựa chọn quy ước phù hợp cho một locale cụ thể. Ví dụ: bản dịch tiếng Việt, dấu phân cách số, kiểu trình bày ngày.
- **Locale:** Tập hợp đặc điểm ngôn ngữ, vùng, chữ viết và biến thể; không đồng nghĩa với múi giờ, đơn vị tiền tệ, vị trí địa lý hiện tại hoặc bản dịch hoàn chỉnh.
- **Unicode:** Cách biểu diễn văn bản của nhiều hệ chữ viết. Mọi ứng dụng bản địa hóa cần xử lý đúng Unicode, nhưng chỉ dùng UTF-8 chưa đủ để dịch thông điệp hay định dạng ngày giờ.

Ví dụ, cùng một giá trị số **1234567.5** có thể được trình bày khác nhau theo locale. Dữ liệu số trong nghiệp vụ vẫn là một giá trị số; dấu phân cách chỉ thuộc tầng hiển thị. Tương tự, thời điểm nên được lưu bằng kiểu thời gian phù hợp, rồi mới hiển thị theo locale và múi giờ của người dùng.

## 2. Bản đồ các nhóm API chính

| Nhu cầu | Nhóm API Java Core | Vai trò và giới hạn |
| --- | --- | --- |
| Xác định ngôn ngữ/vùng | **java.util.Locale**, **Locale.Builder** | Tạo, đọc, truyền ngữ cảnh locale; tự nó không dịch nội dung. |
| Tra cứu bản dịch | **java.util.ResourceBundle**, **PropertyResourceBundle**, **ListResourceBundle** | Lấy chuỗi theo khóa, lựa chọn bundle theo locale, hỗ trợ cơ chế fallback. |
| Chèn tham số vào câu | **java.text.MessageFormat**, **ChoiceFormat** | Định dạng thông điệp có tham số theo locale; không phải hệ thống dịch tự động hoặc giải pháp đầy đủ cho mọi quy tắc số nhiều. |
| Số, phần trăm, tiền tệ | **java.text.NumberFormat**, **DecimalFormat**, **DecimalFormatSymbols**, **java.util.Currency** | Định dạng và phân tích chuỗi số; không chuyển đổi tỷ giá. |
| Ngày, giờ | **java.time.format.DateTimeFormatter**, **FormatStyle**, **java.time.ZoneId**; API **java.text.DateFormat** legacy | Hiển thị ngày giờ, kiểm soát locale và múi giờ. |
| Sắp xếp chuỗi theo ngôn ngữ | **java.text.Collator**, **CollationKey** | So sánh văn bản theo quy tắc ngôn ngữ, khác so sánh ký tự thô. |
| Tách văn bản | **java.text.BreakIterator** | Tìm ranh giới từ, câu, dòng hoặc cụm ký tự mà API cung cấp. |
| Chuẩn hóa Unicode | **java.text.Normalizer**, **java.nio.charset.StandardCharsets** | Xử lý các dạng chuẩn Unicode và mã hóa dữ liệu văn bản; không thay thế dịch/so sánh theo locale. |
| Định dạng văn bản có tham số | **java.util.Formatter**, **String.format(Locale, …)** | Hữu ích cho nội dung kỹ thuật, số và bố cục; cấu trúc câu cần dịch thường phù hợp **MessageFormat** hơn. |

Không phải nhóm API nào cũng cần trong mọi ứng dụng. Một màn hình đơn giản thường chỉ cần **Locale**, **ResourceBundle**, **MessageFormat**, **NumberFormat** và **DateTimeFormatter**; công cụ tìm kiếm, danh bạ hay trình biên tập có thể cần thêm **Collator**, **Normalizer** và **BreakIterator**.

## 3. Locale: ngữ cảnh chung cho các API

### 3.1. Tạo và truyền Locale

**Locale** là kiểu dữ liệu bất biến để mô tả lựa chọn ngôn ngữ/vùng. Nên dùng mã ngôn ngữ BCP 47 rõ ràng, ví dụ **vi-VN**, **en-US** hoặc **zh-Hant-TW** (ngôn ngữ Trung Quốc, chữ Phồn thể, Đài Loan).

~~~java
import java.util.Locale;

public class LocaleExample {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        Locale traditionalChinese = new Locale.Builder()
                .setLanguage("zh")
                .setScript("Hant")
                .setRegion("TW")
                .build();

        System.out.println(vietnamese.toLanguageTag());
        System.out.println(traditionalChinese.toLanguageTag());
    }
}
~~~

Lưu thành **LocaleExample.java**, chạy:

~~~bash
javac LocaleExample.java
java LocaleExample
~~~

Kết quả:

~~~text
vi-VN
zh-Hant-TW
~~~

Một locale có thể chỉ mang ngôn ngữ như **vi**, hoặc có ngôn ngữ và vùng như **vi-VN**. Vùng ảnh hưởng đến quy ước trình bày nhưng không tự xác định múi giờ. **Locale.ROOT** là locale trung lập cho những thao tác cần tính độc lập ngôn ngữ; nó không phải ngôn ngữ dành cho giao diện người dùng. Hãy ưu tiên truyền locale tường minh vào các hàm định dạng, tra cứu bản dịch, so sánh chuỗi.

### 3.2. Locale mặc định và bẫy trạng thái toàn cục

**Locale.getDefault()** phản ánh locale mặc định của JVM; **Locale.setDefault(...)** thay đổi trạng thái dùng chung trong tiến trình. Java cũng phân biệt **Locale.Category.DISPLAY** (tên vùng/ngôn ngữ) và **Locale.Category.FORMAT** (quy ước định dạng). Dựa vào mặc định khiến kết quả thay đổi giữa máy lập trình, CI và máy chủ.

Trong ứng dụng nhiều người dùng, mỗi request hoặc mỗi hồ sơ người dùng nên mang locale riêng; không gọi **Locale.setDefault(...)** để chuyển ngôn ngữ cho từng request. Locale do người dùng yêu cầu cũng cần được kiểm tra đối chiếu danh sách ngôn ngữ mà ứng dụng thực sự hỗ trợ. Locale hợp lệ không bảo đảm mọi bản dịch đều có mặt.

## 4. ResourceBundle: quản lý chuỗi theo ngôn ngữ

### 4.1. Ý tưởng và cơ chế

**ResourceBundle** tách câu chữ giao diện khỏi Java. Mỗi thông điệp có một **khóa ổn định** như **welcome**, **validation.required** hoặc **order.confirmed**. Cùng khóa có thể trỏ đến văn bản khác nhau trong từng tệp **.properties** hoặc trong các lớp kế thừa **ListResourceBundle**.

Ví dụ với base name **messages**:

~~~text
messages.properties
messages_vi.properties
messages_vi_VN.properties
~~~

Khi chọn **vi-VN**, bundle cụ thể nhất phù hợp được ưu tiên, thường xét từ biến thể/vùng đến ngôn ngữ và cuối cùng đến bundle gốc. Cơ chế mặc định còn có nhánh fallback về locale mặc định của JVM trong một số trường hợp; không được coi mọi yêu cầu thiếu bản dịch sẽ đi thẳng về file gốc. Nếu ứng dụng yêu cầu fallback xác định, có thể cấu hình **ResourceBundle.Control** (với cách đóng gói hỗ trợ API đó) hoặc thiết kế chính sách chọn ngôn ngữ ngay tại tầng ứng dụng.

Các tệp phải nằm trong classpath đúng gói. Ví dụ file **com/example/i18n/messages_vi.properties** tương ứng base name **com.example.i18n.messages**. Khi dùng resource đặt cùng thư mục chạy và classpath hiện hành, base name đơn giản **messages** là đủ.

**Lưu ý mã hóa:** Từ Java 9, **PropertyResourceBundle** được tải từ luồng byte bằng UTF-8 theo mặc định, có cơ chế tương thích với ISO-8859-1 đối với byte không hợp lệ. Điều này khác với **java.util.Properties.load(InputStream)** vốn có quy ước ISO-8859-1; dùng **Reader** với charset rõ ràng khi cần. Nên lưu các file dịch ở UTF-8, kiểm tra mã hóa ngay trong pipeline.

### 4.2. Sử dụng

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle labels = ResourceBundle.getBundle("messages", locale);
String title = labels.getString("page.title");
~~~

**getString** ném **MissingResourceException** nếu bundle hoặc khóa không tồn tại. Nên có tệp gốc, kiểm tra mọi khóa giữa các ngôn ngữ khi build, ghi nhận khóa thiếu và chọn chính sách lỗi phù hợp. **ResourceBundle** có cache; chỉnh file trong lúc chương trình chạy không mặc nhiên làm nội dung mới được nạp lại. **ResourceBundle.clearCache()** có thể xóa cache, nhưng quy trình reload cần được thiết kế rõ ràng.

Không đưa mật khẩu, mã nghiệp vụ hoặc bản dịch sinh từ người dùng chưa kiểm soát vào khóa động một cách tùy tiện. Khóa ổn định giúp phát hiện thiếu dịch, hỗ trợ tìm kiếm và kiểm thử.

## 5. MessageFormat: lắp ghép thông điệp theo ngữ cảnh ngôn ngữ

Nội dung kiểu **"Xin chào, " + name + "!"** tuy chạy được nhưng khó đổi thứ tự tham số khi dịch sang ngôn ngữ khác. **MessageFormat** cho phép bản dịch quyết định vị trí của các tham số.

~~~properties
# messages_vi.properties
welcome=Xin chào, {0}!
purchase={0} đã mua {1,number,integer} sản phẩm.
~~~

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

String pattern = bundle.getString("welcome");
MessageFormat formatter = new MessageFormat(pattern, locale);
String result = formatter.format(new Object[] {"Mai"});
System.out.println(result);
~~~

Kết quả của đoạn minh họa, khi đã khai báo biến **locale**, import và nạp bundle như trên: **Xin chào, Mai!**. Các placeholder **{0}**, **{1}** tham chiếu theo chỉ số tham số; cú pháp **{1,number,integer}** bảo MessageFormat định dạng giá trị thứ hai như số nguyên theo locale. Có thể dùng các kiểu định dạng **number**, **date**, **time**, **choice** được MessageFormat hỗ trợ.

**Bẫy quan trọng:**
- Dấu nháy đơn có ý nghĩa đặc biệt trong pattern của **MessageFormat**. Muốn hiển thị một dấu nháy đơn theo nghĩa thông thường, thường phải viết hai dấu liên tiếp trong pattern, ví dụ **You''re {0}**. Cần kiểm thử bản dịch có dấu nháy.
- **MessageFormat** dùng mô hình định dạng ngày/giờ legacy cho các tham số kiểu date; đối với **java.time.LocalDate** hay **Instant**, thường nên định dạng trước bằng **DateTimeFormatter** rồi chuyển chuỗi vào pattern.
- **ChoiceFormat** có thể mô tả lựa chọn đơn giản, nhưng quy tắc số nhiều/phân loại giống và biến cách của nhiều ngôn ngữ rất phức tạp. Đừng giả định Java Core có đầy đủ cú pháp plural của ICU MessageFormat; dự án cần quy tắc phức tạp có thể cân nhắc ICU4J hoặc tầng bản địa hóa chuyên biệt.
- **MessageFormat** có thể thay đổi trạng thái và không nên chia sẻ một instance mutable giữa các luồng mà không đồng bộ/kiểm soát; tạo instance theo lần dùng hoặc giữ cấu hình riêng an toàn.

## 6. NumberFormat, DecimalFormat và Currency

### 6.1. Định dạng để hiển thị

**NumberFormat** là API mức cao, tùy locale để chọn ký hiệu nhóm nghìn, dấu thập phân, tỷ lệ phần trăm và ký hiệu tiền. Các factory thường dùng:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat number = NumberFormat.getNumberInstance(locale);
NumberFormat integer = NumberFormat.getIntegerInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
NumberFormat money = NumberFormat.getCurrencyInstance(locale);

System.out.println(number.format(1234567.5));
System.out.println(integer.format(1234567));
System.out.println(percent.format(0.25));
System.out.println(money.format(1234567));
~~~

Đây là đoạn minh họa nằm trong một phương thức và cần import **java.text.NumberFormat** cùng **java.util.Locale**. Kết quả hiển thị cụ thể có thể thay đổi theo dữ liệu locale và phiên bản JDK, nên không ghi cứng dấu cách hay dấu phân cách vào bài kiểm thử. Đặc biệt, phần trăm nhận giá trị tỷ lệ: **0.25** có nghĩa **25%**, không phải 0,25%.

**Currency** đại diện cho mã tiền tệ ISO 4217. Locale có vùng thường giúp chọn tiền mặc định cho **getCurrencyInstance**; khi nghiệp vụ quyết định loại tiền, hãy đặt tường minh:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance(Locale.US);
formatter.setCurrency(java.util.Currency.getInstance("JPY"));
~~~

Việc đặt **JPY** thay đổi thông tin tiền tệ và ký hiệu/số chữ số thập phân liên quan đến định dạng; **không** chuyển đổi giá trị USD sang JPY hay lấy tỷ giá. Không suy diễn một đơn vị tiền chỉ từ locale của người dùng. Với dữ liệu tiền tệ trong nghiệp vụ, nên dùng **BigDecimal** cùng mã tiền tệ rõ ràng để tránh sai số dấu phẩy động.

### 6.2. Mẫu tùy biến và phân tích ngược

**DecimalFormat** hỗ trợ pattern như **#,##0.00**; **DecimalFormatSymbols** cung cấp ký tự đặc thù locale. Nếu cần phân tích một chuỗi số thành giá trị, dùng **NumberFormat.parse** với locale tương ứng. Kiểu trả về là **Number**, không mặc nhiên là **BigDecimal**.

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberParsingExample {
    public static void main(String[] args) throws Exception {
        NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
        DecimalFormat decimal = (DecimalFormat) format;
        decimal.setParseBigDecimal(true);

        BigDecimal value = (BigDecimal) decimal.parse("1,234.50");
        System.out.println(value.toPlainString());
    }
}
~~~

Lưu thành **NumberParsingExample.java**, chạy bằng **javac NumberParsingExample.java** rồi **java NumberParsingExample**. Kết quả chính xác:

~~~text
1234.50
~~~

Đối với dữ liệu đầu vào, **parse(String)** có thể chấp nhận phần tiền tố hợp lệ mà không kiểm tra phần dư; để xác nhận đã tiêu thụ toàn chuỗi, dùng overload nhận **ParsePosition** và kiểm tra chỉ số kết thúc. Phân tích số từ người dùng cũng cần xử lý khoảng trắng, giá trị sai và ràng buộc miền giá trị nghiệp vụ. Các formatter **NumberFormat/DecimalFormat** là mutable và không được mặc định coi là an toàn khi nhiều luồng cùng sử dụng.

## 7. Ngày, giờ và múi giờ: DateTimeFormatter là lựa chọn hiện đại

Java 17+ ưu tiên hệ **java.time**: **LocalDate** là ngày lịch không kèm giờ/múi giờ; **LocalDateTime** không biểu diễn một thời điểm toàn cầu; **Instant** biểu diễn thời điểm trên trục UTC; **ZonedDateTime** gắn thời điểm/ngày giờ với **ZoneId**. Locale và múi giờ là hai quyết định độc lập.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class DateLocalizationExample {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter localDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);
        System.out.println(localDate.format(date));

        Instant instant = Instant.parse("2026-10-28T03:00:00Z");
        DateTimeFormatter localDateTime = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(locale)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println(localDateTime.format(instant));
    }
}
~~~

Lưu **DateLocalizationExample.java** và chạy **javac DateLocalizationExample.java**, **java DateLocalizationExample**. Dòng đầu là ngày 28/10/2026 theo quy ước tiếng Việt; dòng thứ hai là thời gian tương ứng tại múi giờ **Asia/Ho_Chi_Minh**. Cách viết chữ tháng, dấu phân tách hoặc dấu cách có thể khác nhau giữa các phiên bản dữ liệu locale của JDK, nên kiểm thử giá trị thời gian và cấu trúc thay vì so khớp một chuỗi dịch cứng nếu không cố định môi trường.

- **DateTimeFormatter.ofLocalizedDate/Time/DateTime** và **FormatStyle** là lựa chọn tốt cho màn hình người dùng.
- **DateTimeFormatter.ofPattern(...)** dùng khi sản phẩm có định dạng được chỉ định; truyền locale khi pattern có tên tháng/thứ bằng chữ.
- Với bản ghi thời gian hoặc giao tiếp API, ưu tiên định dạng chuẩn xác định, ví dụ **DateTimeFormatter.ISO_INSTANT**, không tùy tiện dùng mẫu hiển thị theo locale.
- **DateTimeFormatter** là immutable, an toàn để dùng chung giữa luồng. **java.text.DateFormat/SimpleDateFormat**, **java.util.Date**, **Calendar** và **TimeZone** thuộc hệ API cũ; cần hiểu khi bảo trì nhưng tránh chọn làm mặc định cho mã mới.
- **WeekFields.of(locale)** hỗ trợ quy ước ngày đầu tuần và số ngày tối thiểu của tuần đầu tiên; không giả định mọi nơi đều bắt đầu tuần bằng thứ Hai. Các lịch không theo ISO là mối quan tâm riêng của **Chronology**, không tự suy ra đúng chỉ từ ngôn ngữ.

Đừng định dạng **Instant** bằng cách suy ra **ZoneId** từ Locale; cùng một ngôn ngữ có thể dùng ở nhiều múi giờ. Hãy lấy zone từ cài đặt, hồ sơ người dùng hoặc quy tắc nghiệp vụ.

## 8. Collator: so sánh và sắp xếp văn bản theo ngôn ngữ

**String.compareTo** so sánh thứ tự dựa trên đơn vị ký tự Unicode/UTF-16; nó không thực thi quy tắc sắp xếp của từng ngôn ngữ. Ví dụ, thứ tự các chữ cái có dấu có thể khác nhau giữa tiếng Việt, tiếng Đức và tiếng Thụy Điển.

~~~java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

public class SortingExample {
    public static void main(String[] args) {
        String[] names = {"Ánh", "An", "Ân", "Bình"};
        Collator collator = Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
        Arrays.sort(names, collator);
        System.out.println(Arrays.toString(names));
    }
}
~~~

Lưu **SortingExample.java**, biên dịch/chạy tương tự các ví dụ trước. Kết quả phụ thuộc các quy tắc collation mà phiên bản JDK hỗ trợ, nên không áp đặt thứ tự cụ thể trong bài kiểm thử không cố định môi trường.

Các mức **Collator.PRIMARY**, **SECONDARY**, **TERTIARY** điều khiển mức khác biệt chữ được xét đến, ví dụ khác biệt dấu hoặc chữ hoa/thường, nhưng tác động chính xác vẫn tùy locale. Không dùng so sánh theo locale như một tiêu chuẩn định danh tài khoản, mã ID hoặc khóa bảo mật. Với nhiều lần so sánh cùng dữ liệu, **CollationKey** có thể hữu ích, nhưng các key phải đến từ cấu hình Collator tương thích. Vì Collator mutable, không chia sẻ rồi thay đổi strength giữa các luồng.

## 9. Normalizer, BreakIterator và xử lý Unicode

Hai chuỗi trông giống nhau có thể khác chuỗi mã Unicode: ví dụ một ký tự có dấu được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cơ sở cộng dấu kết hợp. **Normalizer** đưa văn bản về các dạng chuẩn, phổ biến là **NFC** (kết hợp) và **NFD** (phân rã).

~~~java
import java.text.Normalizer;

public class UnicodeExample {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(composed.equals(decomposed));
        System.out.println(Normalizer.normalize(composed, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC)));
    }
}
~~~

Lưu **UnicodeExample.java**, chạy **javac UnicodeExample.java** và **java UnicodeExample**. Kết quả:

~~~text
false
true
~~~

**Normalization không đồng nghĩa với bỏ dấu**: NFD chỉ phân rã, không tự xóa các dấu kết hợp. Không tự ý bỏ dấu ở tên riêng, dữ liệu pháp lý hoặc văn bản cần giữ chính tả. Chuẩn hóa nên có chính sách nhất quán tại điểm nhập, tìm kiếm hoặc so khớp; không thay thế Collator khi cần sắp xếp theo ngôn ngữ.

**BreakIterator** dùng để tìm các ranh giới phù hợp hơn với văn bản tự nhiên so với việc cắt chuỗi theo vị trí tùy ý:

~~~java
BreakIterator words = BreakIterator.getWordInstance(locale);
BreakIterator sentences = BreakIterator.getSentenceInstance(locale);
BreakIterator characters = BreakIterator.getCharacterInstance(locale);
~~~

Đây là các dòng minh họa, cần import **java.text.BreakIterator** và định nghĩa **locale**. Dùng **setText(text)**, **first()**, **next()** và hằng **BreakIterator.DONE** để duyệt các biên. Không giả định mọi đoạn giữa hai biên từ đều là một từ có nghĩa; dấu câu và khoảng trắng cũng có thể tạo đoạn. Quy tắc phân đoạn, đặc biệt với emoji ghép và các hệ chữ viết phức tạp, phụ thuộc khả năng Unicode của phiên bản JDK.

**String.length()** đếm đơn vị mã UTF-16, không đếm số ký tự mà người dùng nhìn thấy. **String.codePoints()** giúp duyệt code point, nhưng một cụm ký tự hiển thị vẫn có thể gồm nhiều code point. Vì vậy kiểm tra độ dài input, tô sáng và cắt văn bản phải xác định trước muốn đếm đơn vị mã, code point hay cụm ký tự hiển thị.

## 10. Formatter, Charset và các API hỗ trợ

**String.format(locale, pattern, args...)** và **Formatter** cho phép định dạng số theo locale trong chuỗi kỹ thuật. Ví dụ dùng **String.format(Locale.US, "%.2f", 1.5)** cho kết quả **1.50**. Nhưng biểu thức định dạng như **"Hello %s"** thường để nguyên thứ tự từ, còn **MessageFormat** ghép từ một thông điệp đã dịch linh hoạt hơn. Không nên coi **String.format** là hệ thống dịch.

**StandardCharsets.UTF_8**, **InputStreamReader**, **OutputStreamWriter**, **Files.readString(path, UTF_8)** và **Files.writeString(path, text, UTF_8)** giúp đọc/ghi văn bản nhất quán. UTF-8 là nền tảng truyền dữ liệu, không tự quyết định dấu phân cách số hay quy tắc sắp xếp. Với JSON/HTTP, hãy thiết lập charset hoặc media type theo hợp đồng giao tiếp thay vì trông chờ encoding mặc định của nền tảng.

Ngoài ra, **Locale.getDisplayLanguage(...)**, **getDisplayCountry(...)** và **Locale.getDisplayName(...)** có thể hiển thị tên ngôn ngữ/vùng; **java.util.spi** chứa các điểm mở rộng locale provider cho trường hợp đặc biệt. Đây là nhóm nâng cao, thường không cần tự triển khai chỉ để đổi ngôn ngữ giao diện.

## 11. Ví dụ hoàn chỉnh: ghép ResourceBundle, MessageFormat, NumberFormat và DateTimeFormatter

Ví dụ sau chạy trên Java 17+ với ba file cùng thư mục. Chương trình nhận language tag từ tham số dòng lệnh, mặc định **vi-VN**, lấy câu chào từ resource và định dạng số/ngày bằng cùng locale.

**File messages.properties**

~~~properties
greeting=Hello, {0}!
~~~

**File messages_vi.properties**

~~~properties
greeting=Xin chào, {0}!
~~~

**File LocalizationDemo.java**

~~~java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizationDemo {
    public static void main(String[] args) {
        String languageTag = args.length == 0 ? "vi-VN" : args[0];
        Locale locale = Locale.forLanguageTag(languageTag);

        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);
        String greeting = new MessageFormat(
                messages.getString("greeting"), locale)
                .format(new Object[] {"Mai"});

        NumberFormat numbers = NumberFormat.getNumberInstance(locale);
        DateTimeFormatter dates = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);

        System.out.println("Locale: " + locale.toLanguageTag());
        System.out.println(greeting);
        System.out.println("Số: " + numbers.format(1234567.5));
        System.out.println("Ngày: " + dates.format(LocalDate.of(2026, 10, 28)));
    }
}
~~~

Chạy trong thư mục có ba file:

~~~bash
javac -encoding UTF-8 LocalizationDemo.java
java -cp . LocalizationDemo vi-VN
~~~

Hai dòng stdout đầu **chính xác** là:

~~~text
Locale: vi-VN
Xin chào, Mai!
~~~

Sau đó chương trình in thêm hai dòng bắt đầu bằng **Số:** và **Ngày:**. Biểu diễn dấu phân cách, khoảng trắng, chữ tháng và thứ tự thành phần phụ thuộc dữ liệu bản địa hóa của JDK đang dùng. Khi chạy **en-US** trên môi trường có resource tương ứng hoặc fallback phù hợp, nội dung và cách trình bày thay đổi. Ví dụ không sửa locale mặc định toàn cục nên an toàn hơn với ứng dụng đa người dùng.

Luồng xử lý của ví dụ:

1. Chuyển lựa chọn ngôn ngữ thành đối tượng **Locale**.
2. Tìm bundle tương ứng và lấy văn bản theo khóa.
3. Điền tên vào vị trí được bản dịch quy định bằng **MessageFormat**.
4. Dùng **NumberFormat** và **DateTimeFormatter** để hiển thị dữ liệu có kiểu, không lưu chuỗi đã định dạng làm dữ liệu gốc.

Nếu ứng dụng mở rộng sang nhiều ngôn ngữ, bổ sung file bundle tương ứng (ví dụ **messages_ja.properties**) và dùng danh sách locale được hỗ trợ để chọn ngôn ngữ. Các đoạn demo dùng classpath thông thường; trong ứng dụng module Java có khai báo **module-info.java**, quy tắc đóng gói và tra cứu resource cần được kiểm tra riêng.

## 12. Chọn API theo tình huống và tránh lỗi thường gặp

| Tình huống | Lựa chọn thực tế | Điều cần tránh |
| --- | --- | --- |
| Nút bấm, thông báo lỗi, tiêu đề trang | **ResourceBundle** + khóa cố định | Hardcode tiếng Việt/Anh trong logic hoặc tạo khóa tùy ý. |
| Câu có tên người, số lượng, số tiền | **MessageFormat** + dữ liệu có kiểu; **NumberFormat** khi phù hợp | Ghép chuỗi cố định và bỏ qua thứ tự tham số/nháy đơn. |
| Giá và đơn vị tiền trong hóa đơn | **BigDecimal** + **Currency** + **NumberFormat** | Dùng **double** cho giá trị tiền chính xác; coi đổi ký hiệu là đổi tỷ giá. |
| Nhập số người dùng | **NumberFormat.parse** + kiểm tra phần dư/miền giá trị | Dùng **Double.parseDouble** cho mọi locale hoặc chấp nhận chuỗi có hậu tố rác. |
| Hiển thị ngày, giờ cho người dùng | **java.time** + **DateTimeFormatter** + locale/zone tường minh | Đoán múi giờ từ ngôn ngữ; lưu ngày hiển thị làm dữ liệu. |
| Sắp xếp danh sách tên theo ngôn ngữ | **Collator** | Chỉ dùng **String.compareTo** và mong đúng quy tắc địa phương. |
| Tìm kiếm/cắt chuỗi có dấu, emoji | **Normalizer**/**BreakIterator** cùng chính sách Unicode | Đếm ký tự hiển thị bằng **String.length()** hoặc xóa dấu không có chủ đích. |
| Ghi/đọc văn bản đa ngôn ngữ | **UTF-8** explicit | Nhầm charset với locale hoặc lệ thuộc platform default. |

Checklist triển khai:
- Xác định rõ **supported locales**, ngôn ngữ mặc định và thứ tự fallback; kiểm tra bundle thiếu khóa khi build.
- Dùng locale theo request/user và truyền tường minh; tránh thay đổi mặc định JVM để xử lý từng người dùng.
- Lưu dữ liệu nghiệp vụ ở kiểu chuẩn: số, mã tiền, ngày/instant, múi giờ; chỉ bản địa hóa tại giao diện/biên xuất dữ liệu.
- Kiểm thử với ít nhất hai locale có quy ước khác nhau, một locale không có bản dịch đầy đủ, bản dịch chứa dấu nháy đơn/tham số, văn bản Unicode gồm dấu kết hợp, và trường hợp múi giờ qua ranh giới ngày.
- Khi snapshot-test chuỗi được JDK định dạng theo locale, chốt phiên bản Java và dữ liệu locale nếu cần kết quả byte-for-byte; các bản JDK có thể thay đổi dữ liệu CLDR nên output hiển thị không nhất thiết bất biến.
- Kiểm tra độ dài chuỗi sau dịch (bản dịch có thể dài hơn câu gốc), khả năng đọc chữ từ phải sang trái nếu hỗ trợ, và thông báo lỗi thân thiện khi khóa thiếu hoặc dữ liệu nhập không hợp lệ.

## 13. Ghi nhớ

**Locale** xác định ngữ cảnh; **ResourceBundle** cung cấp văn bản; **MessageFormat** lắp thông điệp; **NumberFormat/Currency** và **DateTimeFormatter** trình bày dữ liệu có kiểu; **Collator/Normalizer/BreakIterator** xử lý văn bản theo quy tắc ngôn ngữ và Unicode. Chúng giải quyết các lớp vấn đề khác nhau và bổ trợ nhau. Thiết kế đúng là tách dữ liệu gốc khỏi chuỗi hiển thị, truyền locale và múi giờ có chủ đích, rồi kiểm thử theo các ngôn ngữ mà sản phẩm cam kết hỗ trợ.
