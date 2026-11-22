# Locale của MessageFormat và các formatter thành phần

**MessageFormat** trong Java Core xây dựng thông điệp có tham số từ một mẫu văn bản: câu chữ do bản dịch cung cấp, còn các giá trị được chèn có thể là số, ngày, giờ, phần trăm hoặc tiền tệ. Việc truyền một **Locale** đúng giúp các tham số hiển thị theo quy ước của người đọc. Tuy nhiên, MessageFormat có một chi tiết dễ gây lỗi: **locale được giữ trong MessageFormat không tự cập nhật các formatter thành phần đã tạo trước đó**.

Bài học này phân tích cơ chế locale của **java.text.MessageFormat**, các formatter con như **NumberFormat**, **DecimalFormat**, **DateFormat**, **SimpleDateFormat** và **ChoiceFormat**, cách thay thế chúng, cách dùng với **java.time** hiện đại và lỗi thường gặp khi ứng dụng chạy trên nhiều môi trường hoặc phục vụ nhiều người dùng. Các ví dụ dùng Java 17+.

## 1. Locale nằm ở đâu trong quá trình tạo thông điệp?

Một thông điệp bản địa hóa có ba lớp riêng:

1. **Ngôn ngữ câu chữ:** được quyết định bởi mẫu đã dịch, thường lấy từ **ResourceBundle**.
2. **Vị trí và kiểu tham số:** được ghi trong mẫu bằng các placeholder như **{0}**, **{1,number,integer}** hoặc **{2,date,short}**.
3. **Cách biến tham số thành chuỗi:** do formatter thành phần thực hiện, với locale và có thể cả múi giờ, tiền tệ hoặc pattern riêng.

Ví dụ mẫu:

~~~text
Xin chào {0}, tổng tiền của bạn là {1,number,currency}.
~~~

Argument **0** có thể là tên người, argument **1** là số tiền. Dù mẫu là tiếng Việt, nếu formatter tiền được tạo theo **en-US** thì ký hiệu và dấu phân cách vẫn có thể theo Hoa Kỳ. **MessageFormat không dịch tự động**; nó chỉ thay thế tham số và sử dụng formatter phù hợp.

| Đối tượng | Vai trò | Điều không làm thay |
| --- | --- | --- |
| **ResourceBundle** | Tìm mẫu thông điệp theo locale/candidate chain | Không quyết định mọi formatter custom |
| **MessageFormat** | Parse mẫu, quản lý placeholder, dùng locale để tạo formatter | Không tự thay mọi formatter đã tồn tại khi đổi locale |
| **NumberFormat/DecimalFormat** | Chuyển số thành chuỗi | Không xác nhận giá trị tiền hay tỷ giá nghiệp vụ |
| **DateFormat/SimpleDateFormat** | Chuyển Date thành chuỗi ngày/giờ | Không tự biết múi giờ người dùng |
| **ChoiceFormat** | Chọn nhánh từ các ngưỡng số | Không cung cấp đầy đủ ngữ pháp số nhiều mọi ngôn ngữ |

Locale là ngữ cảnh ngôn ngữ/vùng, **không đồng nhất** với ZoneId, mã Currency, charset hoặc bản dịch đã tồn tại của ứng dụng.

## 2. Constructor nào nhận Locale?

Hai cách tạo thường dùng:

~~~java
MessageFormat implicit = new MessageFormat(pattern);
MessageFormat explicit = new MessageFormat(pattern, locale);
~~~

Đây là mã minh họa trong một phương thức, với import **java.text.MessageFormat**, biến **pattern** và **locale**. Constructor đầu dùng **Locale mặc định thuộc Locale.Category.FORMAT** của JVM. Constructor thứ hai nhận locale tường minh.

Java không có factory **MessageFormat.getInstance(locale)** như NumberFormat. Dùng constructor tường minh là cách rõ ràng để ứng dụng đa người dùng tránh phụ thuộc vào locale của máy chủ.

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class BasicMessageLocale {
    public static void main(String[] args) {
        MessageFormat us = new MessageFormat(
                "Value: {0,number,0.00}", Locale.US);
        MessageFormat de = new MessageFormat(
                "Value: {0,number,0.00}", Locale.GERMANY);

        System.out.println(us.format(new Object[] {1.5}));
        System.out.println(de.format(new Object[] {1.5}));
    }
}
~~~

Lưu **BasicMessageLocale.java** và chạy:

~~~bash
javac BasicMessageLocale.java
java BasicMessageLocale
~~~

Stdout:

~~~text
Value: 1.50
Value: 1,50
~~~

Giá trị đầu vào đều là **double 1.5**. Chỉ cách trình bày dấu thập phân khác vì hai **DecimalFormat** con được tạo theo locale khác nhau. Chính phần mẫu **Value:** không đổi ngôn ngữ vì MessageFormat không dịch mẫu.

## 3. Pattern xác định formatter con như thế nào?

Cú pháp placeholder thường có ba dạng:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Chỉ số đối số bắt đầu từ 0 và trỏ vào mảng **Object[]**. Các format type được Java 17 MessageFormat chuẩn hỗ trợ gồm **number**, **date**, **time** và **choice**.

| Placeholder | Formatter con |
| --- | --- |
| **{0,number}** | NumberFormat.getInstance(locale) |
| **{0,number,integer}** | NumberFormat.getIntegerInstance(locale) |
| **{0,number,percent}** | NumberFormat.getPercentInstance(locale) |
| **{0,number,currency}** | NumberFormat.getCurrencyInstance(locale) |
| **{0,number,0.00}** | DecimalFormat với DecimalFormatSymbols theo locale |
| **{0,date}** | DateFormat.getDateInstance(DEFAULT, locale) |
| **{0,date,short}** | DateFormat.getDateInstance(SHORT, locale) |
| **{0,time,short}** | DateFormat.getTimeInstance(SHORT, locale) |
| **{0,date,dd/MM/yyyy}** | SimpleDateFormat với pattern và locale |
| **{0,choice,...}** | ChoiceFormat từ chuỗi ngưỡng và nhánh |
| **{0}** | Không có formatter cố định ở lúc parse pattern |

Các formatter cho phần tử đã khai báo kiểu như **{0,number,...}** được tạo khi constructor hoặc **applyPattern(...)** phân tích mẫu. Còn với placeholder không khai báo kiểu như **{0}**, khi chạy **format**, MessageFormat xét đối số: **Number** được định dạng theo NumberFormat mặc định của **getLocale()**; **java.util.Date** được định dạng ngày/giờ short theo locale; **String** được chèn nguyên văn, còn đối tượng khác có thể dùng **toString()**.

Vì thế **setLocale** có thể ảnh hưởng tới placeholder không có formatter cố định, nhưng **không sửa** những DecimalFormat/DateFormat đã tạo. Phải phân biệt hai thời điểm này khi debug kết quả.

## 4. setLocale không tự sửa formatter thành phần đã tạo

API có:

~~~java
message.getLocale();
message.setLocale(newLocale);
message.applyPattern(pattern);
~~~

**getLocale()** trả locale mà MessageFormat giữ. **setLocale(...)** đổi ngữ cảnh dùng cho những formatter tạo sau này và những placeholder không có format type. **applyPattern(...)** đọc lại pattern, tạo mới formatter cho những placeholder đã khai báo kiểu dựa trên locale hiện tại.

Nếu bạn làm:

~~~java
MessageFormat message = new MessageFormat(
        "{0,number,0.00}", Locale.US);
message.setLocale(Locale.GERMANY);
~~~

formatter đã tạo theo Hoa Kỳ vẫn còn. Dù **message.getLocale()** đã là **de-DE**, số vẫn có thể sử dụng dấu chấm. Thực tế này được nêu rõ trong hợp đồng API Java 17.

### 4.1. Thí nghiệm đầy đủ có kết quả chính xác

**File MessageFormatLocaleDemo.java**

~~~java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatLocaleDemo {
    private static final String PATTERN =
            "Value: {0,number,0.00}";

    public static void main(String[] args) {
        MessageFormat message =
                new MessageFormat(PATTERN, Locale.US);
        Object[] values = {1.5};

        System.out.println(
                "start=" + message.format(values));

        message.setLocale(Locale.GERMANY);
        System.out.println(
                "setLocale=" + message.format(values));

        message.applyPattern(PATTERN);
        System.out.println(
                "applyPattern=" + message.format(values));

        DecimalFormat us = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        message.setFormatByArgumentIndex(0, us);

        System.out.println(
                "custom=" + message.format(values));

        message.setLocale(Locale.US);
        System.out.println(
                "afterSetLocale=" + message.format(values));
    }
}
~~~

Lưu **MessageFormatLocaleDemo.java**, biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MessageFormatLocaleDemo.java
java MessageFormatLocaleDemo
~~~

Stdout:

~~~text
start=Value: 1.50
setLocale=Value: 1.50
applyPattern=Value: 1,50
custom=Value: 1.50
afterSetLocale=Value: 1.50
~~~

**Phân tích:** Constructor tạo DecimalFormat theo en-US; **setLocale(Locale.GERMANY)** không sửa formatter cũ; **applyPattern** tạo mới DecimalFormat theo de-DE; **setFormatByArgumentIndex** gắn một formatter tường minh theo en-US; đổi locale MessageFormat lần nữa không ghi đè formatter custom đó.

Đây là điểm phân biệt quan trọng nhất giữa **locale của MessageFormat** và **locale/cấu hình của formatter thành phần**.

## 5. Cách an toàn để đổi ngôn ngữ thông điệp

Với hệ thống xử lý từng request, dễ hiểu nhất là **tạo một MessageFormat mới** bằng pattern đã dịch và locale đã resolve:

~~~java
String localizedPattern = bundle.getString("order.total");

MessageFormat formatter = new MessageFormat(
        localizedPattern, selectedLocale);

String result = formatter.format(
        new Object[] {amount});
~~~

Đoạn này là minh họa, cần có **bundle**, **selectedLocale**, **amount** và import phù hợp. Mỗi lần tạo, các formatter con được khởi tạo nhất quán theo locale đã chọn.

Nếu dùng lại instance trong một luồng tuần tự, có thể làm:

~~~java
message.setLocale(newLocale);
message.applyPattern(newPattern);
~~~

Nhưng **applyPattern** sẽ tạo lại các formatter con theo mẫu; những tùy chỉnh cũ bằng **setFormat...** cần được đánh giá và gắn lại. Đặc biệt, **không làm kiểu này trên một MessageFormat được dùng chung giữa request đồng thời**, vì các setter và formatter legacy là mutable.

Cũng đừng dùng **Locale.setDefault** để chuyển ngôn ngữ cho một request. Đây là trạng thái toàn JVM, có thể khiến request khác nhận định dạng sai.

## 6. Gắn formatter tùy chỉnh bằng setFormatByArgumentIndex

Các phương thức chính:

| API | Cách xác định placeholder |
| --- | --- |
| **setFormat(int index, Format)** | Thứ tự phần tử trong câu pattern, từ trái qua phải |
| **setFormatByArgumentIndex(int argumentIndex, Format)** | Chỉ số đối số; áp dụng cho mọi vị trí dùng chỉ số đó |
| **setFormats(Format[])** | Theo thứ tự các phần tử định dạng xuất hiện |
| **setFormatsByArgumentIndex(Format[])** | Theo chỉ số đối số |
| **getFormats()** | Trả formatter theo thứ tự xuất hiện |
| **getFormatsByArgumentIndex()** | Trả formatter theo chỉ số đối số; với chỉ số lặp, formatter ở lần xuất hiện cuối được phản ánh trong phần tử đó |

Bản dịch có thể đảo thứ tự tham số. Ví dụ:

~~~text
Pattern A: "{0} bought {1,number,integer} items."
Pattern B: "{1,number,integer} sản phẩm đã được {0} mua."
~~~

Trong hai mẫu, **argument 1** là số lượng, nhưng vị trí xuất hiện của phần tử số lượng đã đổi. **setFormatByArgumentIndex(1, formatter)** vẫn chọn đúng đối số; **setFormat(1, formatter)** có thể chọn sai phần tử khi bản dịch đảo câu.

### 6.1. Ví dụ chạy được

**File ArgumentIndexDemo.java**

~~~java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class ArgumentIndexDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "Items={1,number,integer}; ratio={0,number,integer}",
                Locale.US);

        message.setFormatByArgumentIndex(
                0, NumberFormat.getPercentInstance(Locale.US));

        System.out.println(
                message.format(new Object[] {0.25, 4}));
    }
}
~~~

Chạy:

~~~bash
javac ArgumentIndexDemo.java
java ArgumentIndexDemo
~~~

Stdout:

~~~text
Items=4; ratio=25%
~~~

Dù **argument 0** nằm ở placeholder thứ hai, formatter phần trăm vẫn gắn đúng nó.

**Bẫy:** Nếu cùng argument xuất hiện nhiều lần với những kiểu khác nhau, ví dụ **{0,number,integer}** và **{0,number,0.00}**, thì **setFormatByArgumentIndex(0, custom)** ghi đè formatter ở **tất cả** vị trí chứa argument 0. Khi mỗi lần xuất hiện cần định dạng riêng, hãy cân nhắc **setFormat(elementIndex, ...)** có kiểm soát hoặc tách đối số cho rõ nghĩa.

## 7. NumberFormat, DecimalFormat và tiền tệ

Với placeholder **{0,number}**, MessageFormat tạo NumberFormat theo locale hiện tại khi pattern được áp dụng. Với **{0,number,0.00}**, nó tạo DecimalFormat dựa trên pattern và DecimalFormatSymbols của locale. DecimalFormat có thể có cấu hình số chữ số thập phân, phân nhóm và rounding riêng.

Một ví dụ NumberFormat tường minh:

~~~java
Locale locale = Locale.GERMANY;
MessageFormat message = new MessageFormat(
        "Amount: {0}", locale);
NumberFormat number =
        NumberFormat.getNumberInstance(locale);
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
message.setFormatByArgumentIndex(0, number);
~~~

Đây là đoạn minh họa cần import **MessageFormat**, **NumberFormat**, **Locale**. Khi gọi format với số, formatter được gắn sẽ kiểm soát cách hiển thị.

### 7.1. Locale không xác định đơn vị tiền giao dịch

**{0,number,currency}** chọn mặc định tiền tệ từ locale. Nhưng một đơn hàng USD hoàn toàn có thể được hiển thị bằng giao diện tiếng Việt. Với tiền thực tế, đơn vị tiền đến từ dữ liệu giao dịch:

~~~java
Locale displayLocale = Locale.forLanguageTag("vi-VN");
NumberFormat money =
        NumberFormat.getCurrencyInstance(displayLocale);
money.setCurrency(Currency.getInstance("USD"));

MessageFormat message = new MessageFormat(
        "Thành tiền: {0}", displayLocale);
message.setFormatByArgumentIndex(0, money);
~~~

Cần import **Locale**, **Currency**, **NumberFormat**, **MessageFormat**. **setCurrency** không đổi tỷ giá hay giá trị tiền, mà chỉ thay thông tin về đơn vị tiền hiển thị. Với tiền tệ cần tính toán chính xác, sử dụng **BigDecimal** và quy tắc rounding nghiệp vụ; định dạng không thể thay thế phép tính đó.

### 7.2. Cấu hình formatter có thể khác getLocale()

Sau khi gọi **setFormatByArgumentIndex(0, NumberFormat.getInstance(Locale.US))**, MessageFormat vẫn có thể giữ **Locale.GERMANY**. Vì formatter custom là một object riêng, **getLocale() không chứng minh toàn bộ subformatter đang dùng cùng locale**. Khi output trộn dấu phân cách hoặc ký hiệu, kiểm tra các formatter gắn thủ công và tùy chọn của chúng.

## 8. DateFormat, SimpleDateFormat và múi giờ

MessageFormat Java 17 sử dụng **java.text.DateFormat** cho **{0,date}**/**{0,time}**. Với format style **short**, **medium**, **long** hoặc **full**, MessageFormat chọn DateFormat factory tương ứng. Với style là pattern như **dd/MM/yyyy**, nó tạo **SimpleDateFormat** theo locale.

**DateFormat/SimpleDateFormat** thuộc hệ API cũ và thường nhận **java.util.Date**. Không nên đưa trực tiếp **LocalDate** hoặc **Instant** vào **{0,date,short}** và mong Java tự chuyển kiểu.

Một ví dụ kiểm soát timezone:

~~~java
Locale locale = Locale.US;
MessageFormat message =
        new MessageFormat("Date: {0}", locale);

DateFormat date = DateFormat.getDateInstance(
        DateFormat.SHORT, locale);
date.setTimeZone(TimeZone.getTimeZone("UTC"));

message.setFormatByArgumentIndex(0, date);

String output = message.format(new Object[] {
        java.util.Date.from(
                java.time.Instant.parse("2026-10-28T00:00:00Z"))
});
~~~

Đoạn minh họa cần import **Locale**, **MessageFormat**, **DateFormat**, **TimeZone** và đặt trong một phương thức. **Locale** chọn cách viết ngày; **TimeZone** quy định chuyển thời điểm sang ngày giờ địa phương. Vì cách trình bày ngày có thể đổi theo dữ liệu locale của JDK, không nên ghi cứng output cho mọi bản JDK trong test nếu chưa cố định runtime.

Nếu không đặt timezone, DateFormat có thể phụ thuộc default timezone của máy chủ. Hai máy cùng locale vẫn có thể in ngày khác nhau nếu cùng một Instant rơi qua ranh giới ngày. Với server và API, hãy chọn **ZoneId** hoặc TimeZone theo dữ liệu thực tế, không suy ra nó từ locale.

## 9. Kết hợp java.time với MessageFormat

API **java.time** mới hơn dùng **DateTimeFormatter**, một đối tượng immutable. Nhưng DateTimeFormatter không trực tiếp là subclass của **java.text.Format**; vì thế không thể chỉ ép kiểu nó thành DateFormat.

Có hai chiến lược rõ ràng:

- **Định dạng trước** bằng DateTimeFormatter rồi đưa String vào placeholder không định dạng **{0}**.
- **Gắn adapter** do **DateTimeFormatter.toFormat()** trả về, dùng **MessageFormat.setFormatByArgumentIndex(...)** với đối tượng thời gian phù hợp.

Ví dụ đầy đủ có output ổn định:

**File ModernTimeMessage.java**

~~~java
import java.text.MessageFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ModernTimeMessage {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        DateTimeFormatter date = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale);

        MessageFormat message = new MessageFormat(
                "Ngày giao hàng: {0}", locale);
        message.setFormatByArgumentIndex(
                0, date.toFormat());

        System.out.println(
                message.format(new Object[] {
                        LocalDate.of(2026, 10, 28)
                }));
    }
}
~~~

Lưu **ModernTimeMessage.java**, chạy:

~~~bash
javac -encoding UTF-8 ModernTimeMessage.java
java ModernTimeMessage
~~~

Stdout:

~~~text
Ngày giao hàng: 28/10/2026
~~~

**Giải thích:** Adapter **toFormat()** biến DateTimeFormatter thành một Format có thể gắn vào MessageFormat. Locale nằm ở DateTimeFormatter và được thiết lập khi tạo đối tượng, còn pattern **dd/MM/uuuu** định nghĩa chính xác hình thức. Nếu gọi **message.setLocale(Locale.US)** về sau thì formatter adapter này không tự đổi.

Với Instant cần hiển thị giờ địa phương, dùng DateTimeFormatter có ZoneId tường minh; một locale không tự quyết định múi giờ. Nếu đã định dạng trước thành chuỗi, MessageFormat chỉ chèn chuỗi đó và không tự chuyển đổi lại.

## 10. ChoiceFormat và giới hạn của locale

**ChoiceFormat** lựa chọn chuỗi dựa trên một giá trị số và các khoảng/ngưỡng định nghĩa trong pattern hoặc mảng. Nó hữu ích cho vài điều kiện đơn giản nhưng **không thay thế hệ thống xử lý số nhiều đầy đủ** của nhiều ngôn ngữ. Locale của MessageFormat không tự dịch các nhánh ChoiceFormat.

Ví dụ minh họa:

~~~java
ChoiceFormat choice = new ChoiceFormat(
        new double[] {0, 1, 2},
        new String[] {
                "không có mục",
                "một mục",
                "{0,number,integer} mục"
        });

MessageFormat message = new MessageFormat(
        "Giỏ hàng: {0}", Locale.forLanguageTag("vi-VN"));
message.setFormatByArgumentIndex(0, choice);

System.out.println(
        message.format(new Object[] {3}));
~~~

Cần import **ChoiceFormat**, **MessageFormat**, **Locale**; đây là đoạn code bên trong một phương thức. Với đối số 3, ChoiceFormat lấy nhánh cuối. Nhánh này chứa placeholder lồng, vì vậy MessageFormat định dạng số đó theo locale của chính nó. Ý nghĩa đầu ra: **Giỏ hàng: 3 mục**.

**Lưu ý:** các từ trong ba nhánh là câu chữ tiếng Việt được viết sẵn, không phải bản dịch sinh tự động. Với tiếng Anh, tiếng Nga, tiếng Ả Rập hoặc các ngôn ngữ có quy tắc số nhiều khác, cần bản dịch và cơ chế điều kiện phù hợp. Đừng chỉ thay locale của MessageFormat rồi giữ ChoiceFormat tiếng Việt, vì ngôn ngữ của nhánh sẽ không đổi.

Nếu pattern có lựa chọn số nhiều phức tạp, giới tính, cách biến cách hoặc điều kiện lồng, cân nhắc một cơ chế bản địa hóa chuyên biệt đã được thiết kế cho các ngôn ngữ sản phẩm hỗ trợ.

## 11. Pattern và quy tắc dấu nháy đơn

MessageFormat có cú pháp escape đặc biệt. Dấu nháy đơn trong pattern là ký tự cú pháp dùng để quote các đoạn literal; muốn hiển thị một dấu nháy đơn thực sự thường phải viết **hai dấu nháy đơn liên tiếp**.

~~~text
Pattern sai ý định: You're {0}
Pattern phù hợp:   You''re {0}
~~~

Đoạn thứ nhất có thể thay đổi cách placeholder được phân tích. Đây là lỗi rất thường gặp khi người dịch hoặc lập trình viên ghép pattern từ câu văn tự nhiên chứa dấu nháy. Quy tắc escape của MessageFormat còn khác với escape của chuỗi Java và của file **.properties**.

Dấu ngoặc nhọn **{** và **}** cũng tham gia cú pháp placeholder; nếu muốn chúng xuất hiện như văn bản thông thường, phải quote đúng. Với pattern phức tạp, hãy chạy test format bằng những tham số mẫu cho từng ngôn ngữ, thay vì chỉ kiểm tra file dịch tồn tại.

**Không coi pattern từ nguồn không tin cậy là một chuỗi bất kỳ để format.** Mẫu có thể gây lỗi cú pháp hoặc lựa chọn định dạng ngoài mong muốn. Chỉ dùng những pattern đã xác minh, có chính sách cập nhật và kiểm thử phù hợp.

## 12. ResourceBundle cung cấp ngôn ngữ, MessageFormat định dạng giá trị

Trong ứng dụng đa ngôn ngữ, luồng thường là:

~~~text
Người dùng / hồ sơ / Accept-Language
              |
              v
     Chọn supported Locale
              |
              v
     ResourceBundle theo Locale
              |
              v
       Lấy pattern đã dịch
              |
              v
 new MessageFormat(pattern, Locale)
              |
              v
  Gắn formatter con đặc thù
  (Currency, TimeZone, java.time)
              |
              v
      format(Object[] values)
~~~

Ví dụ các file ở classpath:

**messages.properties**

~~~properties
notice=You have {0,number,integer} messages.
~~~

**messages_vi.properties**

~~~properties
notice=Bạn có {0,number,integer} tin nhắn.
~~~

Đoạn Java:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);

MessageFormat message = new MessageFormat(
        bundle.getString("notice"), locale);

System.out.println(
        message.format(new Object[] {3}));
~~~

Cần import **Locale**, **ResourceBundle**, **MessageFormat**. Với các resource nêu trên trong classpath, stdout:

~~~text
Bạn có 3 tin nhắn.
~~~

Cần phân biệt hai lớp fallback: **lựa chọn ResourceBundle** có chuỗi ứng viên và có thể xét JVM default trong một số trường hợp không có bundle phù hợp; còn **MessageFormat** định dạng tham số bằng locale/subformatter đã được thiết lập. Để kết quả hoàn toàn ổn định, chính sách fallback bundle cũng phải được kiểm soát; chỉ truyền locale vào MessageFormat không làm thay điều đó.

Với named module/JPMS và cách đóng gói tài nguyên đặc thù, cần kiểm thử cách tìm bundle tương ứng. ResourceBundle được dùng để tìm mẫu văn bản, không phải để ép một formatter con đã tự tạo dùng locale mới.

## 13. Lỗi phổ biến khi dùng locale của formatter con

| Lỗi | Hiện tượng | Hướng xử lý |
| --- | --- | --- |
| Dùng **MessageFormat.format(pattern, args...)** tĩnh | Kết quả theo locale FORMAT mặc định của JVM | Dùng constructor có locale |
| Gọi **setLocale** sau khi tạo **{0,number}** | Số vẫn theo locale cũ | Tạo MessageFormat mới hoặc applyPattern đúng lúc |
| Gắn NumberFormat của locale khác | Dấu phân cách không thống nhất với câu dịch | Tạo formatter custom theo locale đã resolve |
| Gắn **setFormat(0, ...)** trong bản dịch đảo chỗ | Formatter rơi vào argument khác | Ưu tiên setFormatByArgumentIndex khi thích hợp |
| Dùng **{0,date}** với **LocalDate** | Không tương thích DateFormat legacy | toFormat adapter hoặc định dạng trước |
| Dùng DateFormat không chỉ định timezone | Ngày/giờ khác giữa dev và server | Đặt timezone theo nghiệp vụ |
| Dùng currency theo locale để diễn giải giao dịch | Hiển thị sai đơn vị tiền | Lấy Currency từ dữ liệu thanh toán |
| Gắn ChoiceFormat đã hardcode tiếng Việt vào locale khác | Câu pha ngôn ngữ | Dịch nhánh hoặc thay cơ chế plural |
| Chia sẻ MessageFormat mutable giữa thread | Race hoặc kết quả ngôn ngữ không ổn định | Tạo instance theo request/cách ly phù hợp |
| Cho rằng String.format và MessageFormat là một | Pattern được xử lý sai | Chọn API và cú pháp tương ứng |
| Không kiểm tra bản dịch có dấu nháy | Placeholder biến mất, pattern sai | Test các pattern sau khi dịch |

**Một khác biệt quan trọng:** **String.format(Locale, ...) / Formatter** dùng cú pháp dấu phần trăm như **%.2f**, còn **MessageFormat** dùng placeholder trong ngoặc nhọn như **{0,number,0.00}**. Không chuyển pattern giữa hai API mà không viết lại cú pháp.

## 14. Kiểm thử hành vi quan trọng

Các kiểm thử nên bao gồm:

1. Cùng một số với **Locale.US** và **Locale.GERMANY** phải dùng dấu thập phân theo locale đã chọn.
2. **getLocale()** phản ánh locale mới sau **setLocale**; formatter số đã tạo trước đó vẫn giữ định dạng cũ.
3. Gọi **applyPattern** sau khi đổi locale tạo formatter mới theo locale mới.
4. **setFormatByArgumentIndex** áp vào đúng argument dù thứ tự xuất hiện thay đổi giữa bản dịch.
5. Với một argument lặp nhiều lần, hiểu việc setFormatByArgumentIndex ghi đè tất cả vị trí.
6. Formatter custom có locale hoặc currency khác vẫn giữ cấu hình riêng của nó.
7. DateFormat được gắn timezone tường minh khi cần kết quả thời gian ổn định.
8. LocalDate được format bởi DateTimeFormatter.toFormat hoặc chuyển thành chuỗi phù hợp trước khi truyền vào MessageFormat.
9. ResourceBundle cung cấp đúng pattern và các trường hợp thiếu khóa/fallback được kiểm soát.
10. Mỗi bản dịch có dấu nháy, ngoặc nhọn và placeholder được parse/format đúng.
11. Test chạy dưới các JVM default khác nhau mà vẫn cho cùng kết quả khi đã truyền mọi locale tường minh.
12. Phiên bản JDK và dữ liệu CLDR được tính đến nếu snapshot bắt buộc trùng từng byte của tên tháng, ký hiệu tiền tệ hoặc dấu cách.

Để mô phỏng JVM default khác nhau, ưu tiên **chạy các test trong process riêng**. **Locale.setDefault** sửa trạng thái toàn JVM và có thể làm các test chạy song song can thiệp nhau.

**Không nên chỉ assert một chuỗi ngày dài hoặc ký hiệu tiền trên mọi JDK** nếu chưa cố định dữ liệu locale; một số dấu cách, ký hiệu và tên tháng có thể thay đổi giữa các bản JDK. Với numeric pattern đơn giản như ví dụ 0.00, stdout được chỉ định rõ và dễ đối chiếu.

## 15. Checklist khi triển khai

- Resolve **supported Locale** trước khi tra bản dịch và định dạng thông điệp.
- Đọc pattern theo đúng ngôn ngữ từ resource đã chuẩn bị.
- Tạo **new MessageFormat(pattern, locale)** thay vì ngầm dùng default JVM.
- Dùng formatter thành phần tương ứng với cùng locale, trừ khi yêu cầu nghiệp vụ bắt buộc dùng cấu hình khác.
- Đặt rõ **Currency**, **TimeZone** và quy tắc rounding; không suy từ locale.
- Hiểu **setLocale** không cập nhật các formatter đã được tạo.
- Khi dùng **applyPattern** để đổi locale, kiểm tra và gắn lại formatter tùy chỉnh.
- Dùng **setFormatByArgumentIndex** khi bản dịch có thể đảo thứ tự các tham số; xử lý riêng khi một argument cần nhiều kiểu format.
- Dùng **DateTimeFormatter.toFormat()** hoặc định dạng trước khi đầu vào là kiểu java.time.
- Kiểm tra cú pháp MessageFormat cho mọi bản dịch, nhất là dấu nháy đơn và ngoặc nhọn.
- Không chia sẻ instance mutable rồi thay đổi locale/pattern trong nhiều request đồng thời.
- Kiểm thử ResourceBundle fallback và output dưới nhiều locale/JDK phù hợp với hợp đồng của sản phẩm.

## 16. Ghi nhớ

**Locale của MessageFormat chỉ là ngữ cảnh dùng khi tạo hoặc lựa chọn formatter con, không phải một công tắc đổi toàn bộ định dạng đã tồn tại.** Những placeholder có type như **number/date/time** tạo formatter khi pattern được áp dụng; **setLocale** sau đó không đổi chúng. Formatter được gắn tường minh bằng **setFormatByArgumentIndex** còn có thể dùng locale, timezone và currency riêng.

Cách thiết kế dễ kiểm soát là lấy pattern đã dịch theo locale người dùng, tạo MessageFormat mới bằng chính locale đó, cấu hình formatter thành phần có chủ đích, rồi format các tham số có kiểu. Việc này giúp thông điệp nhất quán trên Java 17+, giữa các request và giữa dev, CI, production.
