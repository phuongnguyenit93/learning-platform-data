# Tên tháng, tên ngày, kỳ trong ngày và TextStyle trong Java

Khi hiển thị thời gian cho người dùng, chương trình Java không chỉ đổi **28/10/2026** thành một chuỗi số. Giao diện còn phải biết **tên tháng** (tháng Mười, October), **tên ngày trong tuần** (thứ Tư, Wednesday), **kỳ trong ngày** (AM/PM hoặc sáng, chiều, tối) và cách những tên ấy thay đổi theo ngôn ngữ, vị trí trong câu, độ dài nhãn và dữ liệu locale. Với Java 17+, các API chính là **java.time.Month**, **java.time.DayOfWeek**, **java.time.format.TextStyle**, **DateTimeFormatter**, **DateTimeFormatterBuilder** và **ChronoField**.

Điểm quan trọng: **TextStyle không phải kiểu chữ CSS hay JavaFX**. Nó là enum mô tả **dạng chữ của giá trị thời gian**: đầy đủ, viết tắt, hẹp và dạng dùng khi đứng riêng. Việc chọn đúng locale cùng đúng TextStyle giúp hiển thị ngày giờ tự nhiên hơn và tránh phụ thuộc ngầm vào ngôn ngữ của máy chủ.

## 1. Cần bản địa hóa thành phần nào của ngày giờ?

Xét thời điểm ngày **28/10/2026** lúc **09:30**. Dữ liệu gồm những giá trị có kiểu:

- **Month.OCTOBER**: tháng thứ 10 theo lịch ISO.
- **DayOfWeek.WEDNESDAY**: thứ Tư, giá trị ISO là 3 (thứ Hai = 1).
- **LocalDate.of(2026, 10, 28)**: ngày lịch, chưa có múi giờ.
- **LocalTime.of(9, 30)**: giờ địa phương 09:30, chưa gắn với ngày hoặc múi giờ.
- **ChronoField.AMPM_OF_DAY**: phần nửa ngày, **0** cho AM và **1** cho PM.

Với cùng dữ liệu, một giao diện tiếng Anh có thể hiển thị **Wednesday, October 28, 2026 at 9:30 AM**. Giao diện tiếng Việt có thể dùng tên ngày, tháng và nhãn thời gian khác. Các ký tự, chữ viết tắt, thứ tự thành phần và cách đặt giới từ phụ thuộc locale và pattern.

**Phân biệt ba lớp:**

| Lớp | Đại diện | Điều chịu trách nhiệm |
| --- | --- | --- |
| Dữ liệu ngày giờ | LocalDate, LocalTime, LocalDateTime, ZonedDateTime | Giá trị thời gian có kiểu |
| Tên và quy tắc ngôn ngữ | Locale, TextStyle, dữ liệu CLDR của JDK | Tên tháng, ngày, kỳ trong ngày |
| Cách ghép câu | DateTimeFormatter pattern, bản dịch ResourceBundle | Thứ tự thành phần, từ nối, dấu câu |

**Locale** không tự lựa chọn múi giờ và cũng không quyết định ngôn ngữ của một chuỗi chữ cố định bạn viết trong pattern.

## 2. TextStyle là gì?

**java.time.format.TextStyle** có sáu hằng số:

| TextStyle | Ý nghĩa | Khi nào cân nhắc |
| --- | --- | --- |
| **FULL** | Tên đầy đủ trong ngữ cảnh định dạng | Ngày/tháng nằm trong một câu hoặc ngày đầy đủ |
| **SHORT** | Tên rút gọn trong ngữ cảnh định dạng | Nhãn ngắn hơn, danh sách, biểu đồ |
| **NARROW** | Dạng rất ngắn trong ngữ cảnh định dạng | Ô lịch cực hẹp, cần tránh nhầm lẫn |
| **FULL_STANDALONE** | Tên đầy đủ khi đứng độc lập | Tiêu đề một tháng hoặc nhãn riêng |
| **SHORT_STANDALONE** | Dạng rút gọn khi đứng độc lập | Nhãn tự đứng một mình |
| **NARROW_STANDALONE** | Dạng hẹp khi đứng độc lập | Nhãn lịch độc lập có rất ít chỗ |

Java còn cung cấp **TextStyle.isStandalone()** để hỏi một style có thuộc nhóm standalone không, và **TextStyle.asStandalone()** hoặc **TextStyle.asNormal()** để chuyển giữa hai nhóm tương ứng.

**FULL khác FULL_STANDALONE về ngữ cảnh ngôn ngữ**, không phải chỉ khác độ dài. Một số ngôn ngữ có biến cách tên tháng tùy việc nó đi cùng ngày hay đứng một mình. Ví dụ trong tiếng Nga, cách viết tên tháng khi gắn với ngày có thể khác cách đặt tên tháng làm tiêu đề. Ngôn ngữ không có sự phân biệt đó có thể trả về cùng một chuỗi cho hai style. Không nên giả định mọi locale đều có sáu văn bản phân biệt.

**NARROW không bảo đảm duy nhất.** Nhiều tháng hoặc ngày trong tuần có thể cùng bắt đầu bằng một chữ cái, nên dạng hẹp thường không đủ để người dùng phân biệt khi không có thêm ngữ cảnh. Với lịch có khả năng truy cập (accessibility), nên có nhãn đầy đủ bên cạnh hoặc ở thuộc tính mô tả.

## 3. Lấy tên tháng bằng Month.getDisplayName

**Month** là enum của Java Time:

~~~java
import java.time.Month;
import java.time.format.TextStyle;
import java.util.Locale;

public class MonthNameDemo {
    public static void main(String[] args) {
        Month month = Month.OCTOBER;

        System.out.println(
                month.getDisplayName(TextStyle.FULL, Locale.US));
        System.out.println(
                month.getDisplayName(TextStyle.SHORT, Locale.US));
        System.out.println(
                month.getDisplayName(
                        TextStyle.FULL_STANDALONE, Locale.US));
    }
}
~~~

Lưu thành **MonthNameDemo.java**, chạy Java 17+:

~~~bash
javac -encoding UTF-8 MonthNameDemo.java
java MonthNameDemo
~~~

Với dữ liệu locale tiếng Anh Hoa Kỳ thông dụng trong JDK 17, các tên tương ứng là **October**, **Oct**, **October**. Cùng một từ xuất hiện ở FULL và FULL_STANDALONE vì tiếng Anh không cần biến cách riêng ở đây. Với các ngôn ngữ có khác biệt ngữ pháp, chuỗi trả về có thể khác.

**getDisplayName(style, locale)** lấy tên theo style và locale bạn chỉ định. Không cần gọi **Locale.setDefault()** để chuyển ngôn ngữ. Giá trị Month vẫn là tháng Mười, dù chuỗi hiển thị thay đổi.

Ví dụ khảo sát tiếng Việt và tiếng Nga:

~~~java
Month october = Month.OCTOBER;

Locale vi = Locale.forLanguageTag("vi-VN");
Locale ru = Locale.forLanguageTag("ru-RU");

System.out.println(
        october.getDisplayName(TextStyle.FULL, vi));
System.out.println(
        october.getDisplayName(TextStyle.FULL_STANDALONE, ru));
~~~

Đây là đoạn minh họa trong một phương thức, cần import **Month**, **TextStyle**, **Locale**. Kết quả bằng chữ cụ thể dựa trên dữ liệu locale của runtime. Không nên mặc định rằng tên tháng Việt luôn có một cách viết hoa duy nhất, hoặc mọi JDK có cùng hình thức biến cách Nga trong từng style.

## 4. Lấy tên ngày trong tuần bằng DayOfWeek

Tương tự Month, **DayOfWeek** cung cấp:

~~~java
DayOfWeek day = DayOfWeek.WEDNESDAY;
String label = day.getDisplayName(
        TextStyle.FULL, Locale.US);
~~~

Đoạn minh họa cần import **java.time.DayOfWeek**, **java.time.format.TextStyle** và **java.util.Locale**; **label** là tên thứ Tư bằng tiếng Anh (**Wednesday**).

Các DayOfWeek được định nghĩa **MONDAY** đến **SUNDAY**, bất kể locale:

~~~text
MONDAY.getValue() = 1
TUESDAY.getValue() = 2
WEDNESDAY.getValue() = 3
THURSDAY.getValue() = 4
FRIDAY.getValue() = 5
SATURDAY.getValue() = 6
SUNDAY.getValue() = 7
~~~

**getValue() luôn theo ISO-8601**, không thay đổi thành Chủ nhật = 1 chỉ vì dùng en-US. Locale tác động tên ngày, còn **ngày bắt đầu tuần của lịch địa phương** là quyết định khác, có thể lấy qua **WeekFields.of(locale).getFirstDayOfWeek()**.

Ví dụ:

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekStartDemo {
    public static void main(String[] args) {
        System.out.println(
                DayOfWeek.WEDNESDAY.getValue());

        System.out.println(
                WeekFields.ISO.getFirstDayOfWeek());

        System.out.println(
                WeekFields.of(Locale.US).getFirstDayOfWeek());
    }
}
~~~

Chạy **javac WeekStartDemo.java** và **java WeekStartDemo**. Stdout:

~~~text
3
MONDAY
SUNDAY
~~~

Thí nghiệm cho thấy **giá trị ISO của thứ Tư vẫn là 3**, nhưng mô hình tuần của locale Hoa Kỳ có thể đặt Chủ nhật ở đầu tuần. Đừng dùng **getDisplayName** hay **getValue** để suy ra thứ tự cột trong lịch; hãy dùng WeekFields hoặc chính sách của sản phẩm.

## 5. Ví dụ hoàn chỉnh: tên tháng, tên ngày và AM/PM

Ví dụ này dùng dữ liệu cố định và **Locale.US** tường minh để dễ quan sát. Nó không phụ thuộc locale mặc định của máy.

**File MonthDayPeriodDemo.java**

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.TextStyle;
import java.util.Locale;

public class MonthDayPeriodDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        LocalDate date = LocalDate.of(2026, 10, 28);
        LocalTime morning = LocalTime.of(9, 30);
        LocalTime evening = LocalTime.of(21, 30);

        System.out.println("month="
                + date.getMonth()
                      .getDisplayName(TextStyle.FULL, locale));
        System.out.println("weekday="
                + date.getDayOfWeek()
                      .getDisplayName(TextStyle.FULL, locale));

        DateTimeFormatter amPm =
                DateTimeFormatter.ofPattern("a", locale);

        System.out.println("morning=" + amPm.format(morning));
        System.out.println("evening=" + amPm.format(evening));

        DateTimeFormatter full = DateTimeFormatter.ofPattern(
                "EEEE, MMMM d, uuuu 'at' h:mm a", locale);

        LocalDateTime moment = LocalDateTime.of(date, morning);
        System.out.println("full=" + full.format(moment));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MonthDayPeriodDemo.java
java MonthDayPeriodDemo
~~~

Kết quả với dữ liệu en-US của JDK 17:

~~~text
month=October
weekday=Wednesday
morning=AM
evening=PM
full=Wednesday, October 28, 2026 at 9:30 AM
~~~

Các phần liên hệ với nhau:

- **getDisplayName(TextStyle.FULL, Locale.US)** sinh tên riêng của Month/DayOfWeek theo locale.
- **"a"** trong DateTimeFormatter pattern yêu cầu nhãn AM/PM.
- **"h"** là giờ theo hệ 12 giờ, **"mm"** là phút.
- **"EEEE"** là tên ngày trong tuần đầy đủ.
- **"MMMM"** là tên tháng đầy đủ trong ngữ cảnh format.
- **"uuuu"** là năm proleptic, phù hợp nhiều định dạng dựa trên ISO.
- **'at'** được quote trong pattern vì đó là chữ cố định, không phải ký hiệu định dạng.

**Điểm học tập:** nếu thay **Locale.US** bằng **Locale.forLanguageTag("vi-VN")**, Java sẽ dùng tên tháng/ngày và nhãn kỳ trong ngày theo dữ liệu locale tiếng Việt; nhưng chữ literal **at** vẫn là tiếng Anh vì nó được hardcode trong pattern. Câu hoàn chỉnh cần pattern hoặc resource đúng ngôn ngữ, không thể chỉ thay locale.

## 6. Pattern DateTimeFormatter: M và L

Một số ký hiệu trong **java.time.format.DateTimeFormatter** có ý nghĩa khác nhau theo TextStyle:

| Pattern | Ý nghĩa điển hình |
| --- | --- |
| **M** | Số tháng, không đệm 0 nếu không cần |
| **MM** | Tháng dạng số, thường đệm thành hai chữ số |
| **MMM** | Tên tháng ngắn trong ngữ cảnh định dạng |
| **MMMM** | Tên tháng đầy đủ trong ngữ cảnh định dạng |
| **MMMMM** | Tên tháng dạng hẹp trong ngữ cảnh định dạng |
| **L** / **LL** | Tháng dạng số trong ngữ cảnh đứng độc lập |
| **LLL** | Tên tháng ngắn dạng standalone |
| **LLLL** | Tên tháng đầy đủ dạng standalone |
| **LLLLL** | Tên tháng hẹp dạng standalone |

**M** và **L** không phải hai chữ số tháng khác nhau: chúng đại diện hai **ngữ cảnh ngữ pháp**. Với chuỗi ngày đầy đủ như **28 October 2026**, thường dùng dạng format (**MMMM**) còn tiêu đề tháng độc lập có thể dùng **LLLL**. Cần kiểm thử theo locale cụ thể, vì một số ngôn ngữ trả cùng tên cho hai dạng.

### 6.1. Minh họa tiếng Nga

Ví dụ minh họa:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ContextualMonthDemo {
    public static void main(String[] args) {
        Locale russian = Locale.forLanguageTag("ru-RU");
        LocalDate day = LocalDate.of(2026, 10, 28);

        System.out.println(
                DateTimeFormatter.ofPattern("d MMMM uuuu", russian)
                        .format(day));
        System.out.println(
                DateTimeFormatter.ofPattern("LLLL", russian)
                        .format(day));
    }
}
~~~

Lưu **ContextualMonthDemo.java**, chạy:

~~~bash
javac -encoding UTF-8 ContextualMonthDemo.java
java ContextualMonthDemo
~~~

Chương trình in **ngày tháng với tên tháng trong ngữ cảnh định dạng** ở dòng thứ nhất và **tên tháng đứng độc lập** ở dòng thứ hai. Một số bản dữ liệu locale tiếng Nga phân biệt hình thức biến cách tên tháng giữa hai dòng. Vì chính mục tiêu ở đây là quan sát dữ liệu CLDR của JDK, không nên ấn định một chuỗi tiếng Nga là stdout bất biến cho mọi bản runtime.

**Sai lầm cần tránh:** dùng tên standalone để lắp thẳng vào cấu trúc câu mà ngôn ngữ yêu cầu dạng biến cách, hoặc dùng tên format làm tiêu đề tháng độc lập. Trong tiếng Anh có thể không lộ lỗi; trong một số ngôn ngữ khác nó sẽ thành cách diễn đạt không tự nhiên.

### 6.2. getDisplayName và pattern tương ứng

~~~java
Month month = Month.OCTOBER;
Locale locale = Locale.US;

String full = month.getDisplayName(TextStyle.FULL, locale);
String standalone = month.getDisplayName(
        TextStyle.FULL_STANDALONE, locale);
~~~

Đoạn minh họa cần import **Month**, **TextStyle**, **Locale**. Tương ứng, một formatter dùng **MMMM** sẽ yêu cầu tên đầy đủ ở ngữ cảnh format; formatter dùng **LLLL** sẽ yêu cầu tên đầy đủ ở ngữ cảnh standalone. Kết quả cuối cùng còn phụ thuộc vào pattern, ngữ pháp câu và dữ liệu locale.

## 7. Pattern tên ngày: E, e và c

**DateTimeFormatter** hỗ trợ nhiều ký hiệu cho ngày trong tuần:

| Pattern | Cách dùng |
| --- | --- |
| **E**, **EE**, **EEE** | Tên ngày dạng ngắn |
| **EEEE** | Tên ngày đầy đủ |
| **EEEEE** | Tên ngày dạng hẹp |
| **EEEEEE** | Tên ngày dạng ngắn hơn theo dữ liệu |
| **e** hoặc **ee** | Số ngày trong tuần theo quy tắc localized week của locale |
| **eee** | Tên ngày dạng ngắn |
| **eeee** | Tên ngày đầy đủ |
| **eeeee** | Tên ngày dạng hẹp |
| **c** | Số ngày trong tuần theo quy tắc locale |
| **ccc** | Tên ngày ngắn dạng standalone |
| **cccc** | Tên ngày đầy đủ dạng standalone |
| **ccccc** | Tên ngày hẹp dạng standalone |

Với **e**/**c**, các số ngày trong tuần theo locale có thể khác **DayOfWeek.getValue()**. Chẳng hạn một locale có Chủ nhật là đầu tuần thì **e = 1** có thể là Chủ nhật, dù **DayOfWeek.SUNDAY.getValue() = 7**. Không sử dụng các ký hiệu đó để lưu giá trị ngày trong tuần làm khóa dữ liệu khi hợp đồng yêu cầu mã ISO.

Mặt khác, **E** chủ yếu biểu diễn dạng **chữ**, không phải số thứ tự. Với nhãn lịch độc lập, các biến thể standalone **c** có thể phù hợp nếu ngôn ngữ phân biệt dạng này. Một số ngôn ngữ không có dữ liệu riêng, nên có thể gặp nhãn giống nhau.

**Giới hạn pattern:** không phải mọi số lần lặp chữ đều hợp lệ. Ví dụ hai chữ **cc** không phải mẫu được hỗ trợ như **ee**. Nên viết pattern được tài liệu API hỗ trợ và có test chạy thực tế, thay vì áp dụng quy luật nhân đôi máy móc.

## 8. Kỳ trong ngày: AM/PM là gì?

**AM/PM** chia ngày thành hai nửa:

| ChronoField.AMPM_OF_DAY | Giờ 24h | Ý nghĩa |
| ---: | --- | --- |
| **0** | 00:00–11:59:59… | Trước trưa, AM |
| **1** | 12:00–23:59:59… | Sau trưa, PM |

Trong Java:

~~~java
import java.time.LocalTime;
import java.time.temporal.ChronoField;

public class HalfDayDemo {
    public static void main(String[] args) {
        System.out.println(
                LocalTime.MIDNIGHT.get(ChronoField.AMPM_OF_DAY));
        System.out.println(
                LocalTime.NOON.get(ChronoField.AMPM_OF_DAY));
        System.out.println(
                LocalTime.of(23, 59).get(ChronoField.AMPM_OF_DAY));
    }
}
~~~

Chạy **javac HalfDayDemo.java** và **java HalfDayDemo**. Stdout chính xác, độc lập locale:

~~~text
0
1
1
~~~

Dùng **DateTimeFormatter.ofPattern("a", locale)** để in nhãn theo locale. Ở en-US, nhãn quen thuộc là **AM** và **PM**; ở các locale khác, tên có thể được bản địa hóa và dùng dấu câu hoặc cách viết khác. Không tự động hardcode **"AM"** hoặc **"PM"** lên giao diện nhiều ngôn ngữ nếu người dùng mong đợi cách viết địa phương.

### 8.1. Kết hợp a với giờ 12 tiếng

Một số ký hiệu giờ:

| Pattern | Phạm vi giờ | Ví dụ ý nghĩa |
| --- | --- | --- |
| **H** / **HH** | 0–23 | Giờ hệ 24h |
| **h** / **hh** | 1–12 | Giờ hệ 12h, thường đi cùng **a** |
| **K** / **KK** | 0–11 | Giờ trong AM/PM theo hệ 0–11 |
| **k** / **kk** | 1–24 | Giờ đồng hồ hệ 1–24 |
| **a** | Nhãn AM/PM | Nửa ngày |
| **m** / **mm** | Phút | Không liên quan đến tên tháng **M** |

Ví dụ với Locale.US:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TwelveHourDemo {
    public static void main(String[] args) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US);

        for (LocalTime time : new LocalTime[] {
                LocalTime.MIDNIGHT,
                LocalTime.NOON,
                LocalTime.of(21, 5)
        }) {
            System.out.println(format.format(time));
        }
    }
}
~~~

Lưu **TwelveHourDemo.java**, chạy:

~~~bash
javac TwelveHourDemo.java
java TwelveHourDemo
~~~

Stdout với en-US:

~~~text
12:00 AM
12:00 PM
9:05 PM
~~~

**00:00 không phải 00:00 AM khi dùng h; nó là 12:00 AM.** **12:00** là 12:00 PM, không phải AM. Dùng giờ **H** (24h) cùng nhãn **a** thường dư thừa và có thể gây nhầm lẫn trong giao diện. Đối với dữ liệu trao đổi giữa máy, chuỗi giờ ISO-8601 thường thích hợp hơn nhãn AM/PM.

## 9. TextStyle cho kỳ trong ngày với DateTimeFormatterBuilder

Enum **Month** và **DayOfWeek** có trực tiếp **getDisplayName(...)**, nhưng không có enum **AMPM** tương đương để gọi cùng phương thức. Với kỳ trong ngày kiểu nửa ngày, ta có thể format trường **ChronoField.AMPM_OF_DAY** bằng **DateTimeFormatterBuilder.appendText(...)**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class AmPmTextStyleDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;

        DateTimeFormatter label = new DateTimeFormatterBuilder()
                .appendText(
                        ChronoField.AMPM_OF_DAY,
                        TextStyle.SHORT)
                .toFormatter(locale);

        System.out.println(label.format(LocalTime.of(8, 0)));
        System.out.println(label.format(LocalTime.of(20, 0)));
    }
}
~~~

Lưu **AmPmTextStyleDemo.java**, chạy:

~~~bash
javac AmPmTextStyleDemo.java
java AmPmTextStyleDemo
~~~

Với en-US trong Java 17, hai nhãn thông dụng thu được là:

~~~text
AM
PM
~~~

Ở đây **TextStyle.SHORT** chọn mức dạng chữ cho trường AM/PM. Tuy nhiên, một locale không nhất thiết có ba nhãn khác nhau cho FULL, SHORT và NARROW. Bản dữ liệu locale có thể cung cấp cùng nhãn hoặc fallback. Nếu sản phẩm có quy tắc nhãn riêng, **DateTimeFormatterBuilder.appendText(field, Map<Long,String>)** cho phép định nghĩa ánh xạ văn bản cụ thể; khi đó phải xác định rõ phạm vi locale và ngôn ngữ của map.

**Không nhầm nhãn AM/PM với các kỳ trong ngày chi tiết** như sáng sớm, trưa, chiều, tối. AM/PM chỉ chia hai nửa ngày, còn kỳ trong ngày linh hoạt có thể chia nhiều khoảng.

## 10. Pattern B: kỳ trong ngày linh hoạt

Java 17 **DateTimeFormatter** hỗ trợ ký hiệu pattern **B** cho **period-of-day** linh hoạt. Khác với **a**, vốn dựa trên AM/PM, **B** cho phép tên kỳ trong ngày phù hợp với quy tắc locale như “in the morning”, “in the afternoon”, “at night”, “noon”, “midnight” khi dữ liệu locale hỗ trợ.

Ví dụ khảo sát:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

public class FlexiblePeriodDemo {
    public static void main(String[] args) {
        DateTimeFormatter amPm =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US);
        DateTimeFormatter flexible =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);

        for (LocalTime time : List.of(
                LocalTime.MIDNIGHT,
                LocalTime.of(9, 30),
                LocalTime.NOON,
                LocalTime.of(15, 15),
                LocalTime.of(22, 0))) {
            System.out.println(
                    "a=" + amPm.format(time)
                    + " | B=" + flexible.format(time));
        }
    }
}
~~~

Lưu **FlexiblePeriodDemo.java**, chạy:

~~~bash
javac FlexiblePeriodDemo.java
java FlexiblePeriodDemo
~~~

Chương trình in **năm dòng**, mỗi dòng cho biết nhãn **a** và **B** tại một thời điểm. Cách gọi **a** sẽ đưa nhãn AM/PM; cách gọi **B** có thể biểu diễn kỳ trong ngày cụ thể hơn. **Không đưa một stdout nguyên văn cố định cho B**, vì tên và ranh giới các kỳ được xác định bởi dữ liệu locale của runtime và có thể thay đổi theo bản JDK hoặc locale provider.

Trong Java 17, số chữ B trong pattern có thể yêu cầu các mức dạng chữ theo ngữ cảnh; hãy sử dụng mẫu hợp lệ như **B**, **BBBB** hoặc **BBBBB** và kiểm thử. Không nên gắn nhãn “buổi sáng” cố định cho một khoảng giờ tự chọn rồi coi đó là hành vi chuẩn của mọi locale.

### 10.1. B không phải phép biến đổi của a

Hai giờ **09:00** và **11:59** đều là AM. Tuy nhiên, tùy ngôn ngữ có thể có các tên kỳ trong ngày cụ thể hoặc cách đặt nhãn “trưa” đặc biệt. **a** chỉ phân biệt nửa ngày; **B** tra quy tắc nhiều kỳ trong ngày.

Vì vậy trong một ứng dụng đa ngôn ngữ, cần chọn công cụ theo ngữ nghĩa câu:

- Nhập hoặc hiển thị giờ kiểu **9:30 AM**: dùng **h:mm a** khi đây là quy ước của locale.
- Câu tiếng Anh như **9:30 in the morning**: cân nhắc **h:mm B** khi dữ liệu locale và yêu cầu UI phù hợp.
- Hiển thị bảng thời gian 24h: dùng **HH:mm**, thường không cần AM/PM.
- Câu nghiệp vụ có kỳ riêng như “ca sáng”, “ca đêm”: đó là **định nghĩa miền nghiệp vụ**; không tự đồng nhất với day-period của CLDR.

## 11. Tên tháng/ngày trong một câu không chỉ là TextStyle

Một DateTimeFormatter nhận **pattern và locale**, nhưng không tự dịch văn bản literal:

~~~java
DateTimeFormatter en = DateTimeFormatter.ofPattern(
        "EEEE, MMMM d 'at' h:mm a", Locale.US);
~~~

Với pattern trên, chữ **at** đã được ghi cứng. Chuyển sang **Locale.forLanguageTag("vi-VN")** sẽ thay các tên/thành phần bản địa hóa, nhưng chữ **at** vẫn tồn tại. Do đó:

1. **Locale** chọn tên tháng/ngày/kỳ trong ngày theo dữ liệu bản địa.
2. **Pattern** chọn thứ tự và thành phần.
3. **Từ nối/giới từ** phải nằm trong pattern đã dịch hoặc một nguồn nội dung theo locale (chẳng hạn ResourceBundle).

Đối với ứng dụng phục vụ nhiều ngôn ngữ, hãy tạo pattern/formatter theo locale người xem thay vì dùng một mẫu tiếng Anh với các tên ngày được chuyển ngôn ngữ tự động. Một số ngôn ngữ yêu cầu cách đặt ngày/tháng đặc thù, dấu phẩy hoặc cấu trúc giới từ khác.

Đối với giao diện ngày ngắn/dài thông thường, **DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)** kết hợp **withLocale(locale)** thường thuận tiện hơn tự đặt thứ tự tên tháng/ngày. Java sử dụng mẫu ngày địa phương hóa do runtime cung cấp thay vì một mẫu cố định do bạn viết.

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedFullDate {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
                        .withLocale(
                                Locale.forLanguageTag("vi-VN"));

        System.out.println(formatter.format(date));
    }
}
~~~

Lưu **LocalizedFullDate.java**, chạy bằng **javac** rồi **java**. Kết quả là cách trình bày ngày đầy đủ theo vi-VN của JDK, có thể chứa tên ngày, tháng và quy ước riêng. Không khóa một stdout cụ thể ở đây vì chính mục đích ví dụ là dùng định dạng địa phương hóa của runtime.

## 12. Bảng đối chiếu: chọn TextStyle hay pattern nào?

| Nhu cầu UI | Lựa chọn nên xem xét | Lý do |
| --- | --- | --- |
| Tiêu đề tháng trong lịch | **Month.getDisplayName(FULL_STANDALONE, locale)** hoặc **LLLL** | Ngữ cảnh tháng đứng riêng |
| Tên tháng trong ngày đầy đủ | **MMMM** hoặc DateTimeFormatter localized style | Ngữ cảnh định dạng |
| Nhãn tháng ngắn trong biểu đồ | **MMM** / **TextStyle.SHORT** | Gọn, nhưng cần biết có thể trùng |
| Nhãn tháng cực ngắn | **MMMMM** / **TextStyle.NARROW** | Tiết kiệm chỗ; thường không duy nhất |
| Tiêu đề ngày trong tuần | **DayOfWeek.getDisplayName(...)** | Dùng locale và style tường minh |
| Ngày trong câu dài | **EEEE** | Tên ngày đầy đủ |
| Dạng số ngày theo tuần địa phương | **e** hoặc WeekFields | Không đồng nhất ISO getValue |
| Giờ kiểu 12h | **h:mm a** | Nhãn AM/PM |
| Kỳ trong ngày linh hoạt | **B** | Tên kỳ theo dữ liệu locale của Java 17 |
| Dữ liệu máy cần 24h | **HH:mm** hoặc ISO formatter | Không phụ thuộc tên kỳ trong ngày |
| Chuỗi ngày đầy đủ tự nhiên | **ofLocalizedDate(FormatStyle.FULL)** | Dùng thứ tự và dấu câu theo locale |
| Pattern do người dịch kiểm soát | **ofPattern(pattern, locale)** | Câu hoàn chỉnh thuộc bản dịch |

**Cùng một TextStyle không bảo đảm chuỗi dài đúng bằng một số ký tự**: SHORT/NARROW là danh mục kiểu tên, không phải thuật toán cắt chuỗi. Không được lấy FULL rồi gọi substring để tự giả lập SHORT hoặc NARROW, vì cách viết tắt đúng có thể khác chữ đầu của tên đầy đủ.

## 13. Tính khác nhau giữa locale và dữ liệu JDK/CLDR

Ngay khi chỉ định rõ **Locale.forLanguageTag("vi-VN")**, kết quả chữ vẫn có thể thay đổi giữa runtime:

- Bản phát hành JDK tích hợp phiên bản dữ liệu địa phương hóa khác nhau.
- Dữ liệu CLDR cập nhật viết hoa/viết thường, cách viết tắt hoặc cách đặt dấu.
- Locale provider đang được cấu hình khác nhau.
- Một style chưa có dữ liệu riêng nên formatter có thể fallback sang dạng chữ khác hoặc biểu diễn số.
- Một ngôn ngữ có biến thể script/region riêng không nên tự gộp với biến thể khác.

Vì vậy, **truyền locale tường minh giúp tránh phụ thuộc vào default locale của máy**, nhưng không biến tên tháng/ngày thành hằng số bất biến qua mọi bản JDK. Nếu hệ thống dùng snapshot test so sánh toàn bộ văn bản, cần xác định phiên bản runtime được hỗ trợ hoặc đặt assertion theo phạm vi có ý nghĩa.

Đối với tên tiếng Anh phổ thông như October/Wednesday, kết quả thường rất ổn định. Đối với ngôn ngữ có biến cách, tên dạng NARROW, cách viết tắt có dấu hoặc các kỳ trong ngày **B**, không nên tự gán output tuyệt đối mà chưa chạy kiểm thử trên runtime triển khai.

## 14. Parsing tên tháng và ngày trong tuần

DateTimeFormatter không chỉ format mà còn có thể parse văn bản đã bản địa hóa. Tuy nhiên, nếu chuỗi đầu vào có tên tháng/ngày bằng chữ, phải biết **locale và style** của nguồn nhập.

Ví dụ full English:

**File ParseMonthNameDemo.java**

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class ParseMonthNameDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "d MMMM uuuu", Locale.US);

        String input = "28 October 2026";

        try {
            LocalDate date =
                    LocalDate.parse(input, formatter);

            System.out.println(date);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid localized date");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ParseMonthNameDemo.java
java ParseMonthNameDemo
~~~

Stdout:

~~~text
2026-10-28
~~~

Trường hợp này dùng **MMMM** đúng tên tháng đầy đủ và **Locale.US** tường minh. Nếu người dùng nhập tên tháng tiếng Việt hoặc tiếng Nga, cần formatter và style phù hợp. Đừng dùng locale của server để parse dữ liệu theo ngôn ngữ của người dùng.

### 14.1. Tên NARROW có thể nhập nhằng

Khi **TextStyle.NARROW** dùng một ký tự cho nhiều tháng hoặc ngày, cùng chuỗi có thể ứng với nhiều giá trị. Vì vậy:

- Dùng NARROW cho **nhãn trực quan** chỉ khi có ngữ cảnh đủ.
- Không dùng NARROW làm định dạng nhập liệu ngày chính nếu hệ thống cần giải mã duy nhất.
- Ưu tiên ISO numeric cho API hoặc bộ chọn ngày có cấu trúc.
- Với dữ liệu người dùng tự do, thiết kế validation và thông báo lỗi theo locale.

### 14.2. Case, dấu câu và ký tự Unicode

Tên tháng/ngày có thể có dấu, dấu chấm viết tắt hoặc cách viết hoa khác nhau. **DateTimeFormatter** mặc định dùng quy tắc parse có phân biệt hoa/thường trong các trường hợp; nếu cần parse không phân biệt hoa/thường, có thể dùng **DateTimeFormatterBuilder.parseCaseInsensitive()** trước khi append pattern. Tuy vậy, **case-insensitive không đồng nghĩa bỏ dấu hoặc chuẩn hóa Unicode hoàn toàn**.

Ví dụ xây dựng formatter trong phương thức:

~~~java
DateTimeFormatter formatter =
        new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("d MMMM uuuu")
                .toFormatter(Locale.US);
~~~

Đoạn minh họa cần import **DateTimeFormatterBuilder**, **DateTimeFormatter**, **Locale**. Cần kiểm tra chuỗi thực và xử lý **DateTimeParseException**; với các ngôn ngữ có case mapping phức tạp, không tự giả định mọi cách gõ đều được nhận.

## 15. WeekFields và tuần bắt đầu từ ngày nào

Tên thứ và vị trí trong lịch có liên quan nhưng không phải một:

- **DayOfWeek.MONDAY.getValue()** luôn bằng 1 theo ISO.
- **WeekFields.of(Locale.US)** thường dùng Chủ nhật làm ngày đầu tuần.
- Một locale khác có thể có ngày đầu tuần và số ngày tối thiểu của tuần đầu năm khác.

Khi hiển thị nhãn lịch theo locale, bạn có thể cần **getDisplayName(TextStyle.SHORT_STANDALONE, locale)** cho tiêu đề cột. Khi sắp cột, cần **WeekFields.of(locale).getFirstDayOfWeek()** hoặc chính sách người dùng chọn, chứ không sắp từ thứ Hai vì ISO luôn 1.

Ví dụ code minh họa tính thứ tự bảy cột theo locale:

~~~java
DayOfWeek first =
        WeekFields.of(locale).getFirstDayOfWeek();

for (int i = 0; i < 7; i++) {
    DayOfWeek day = first.plus(i);
    String label = day.getDisplayName(
            TextStyle.SHORT_STANDALONE, locale);
    // Đưa label vào cột lịch thứ i.
}
~~~

Đoạn minh họa cần import **DayOfWeek**, **WeekFields**, **TextStyle**, **Locale**, và biến **locale**. **DayOfWeek.plus(...)** tự xoay vòng sau Chủ nhật, không cần tự dùng modulo.

**Không nhầm tuần của locale với timezone**: tuần bắt đầu ngày nào không cho biết ngày hiện tại của người dùng đang là ngày nào nếu chưa biết múi giờ cho thời điểm đó.

## 16. Locale khác múi giờ và đồng hồ 12/24h

Một thời điểm thực tế được biểu diễn bằng **Instant**, còn ngày/giờ người dùng nhìn thấy cần **ZoneId**. Locale quyết định tên tháng, tên ngày và cách viết, nhưng **không tự đổi instant sang giờ địa phương**.

Ví dụ:

~~~java
Instant instant =
        Instant.parse("2026-10-28T00:30:00Z");
ZonedDateTime inVietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "EEEE, d MMMM uuuu HH:mm",
                Locale.forLanguageTag("vi-VN"));

String output = formatter.format(inVietnam);
~~~

Đây là đoạn minh họa cần import **Instant**, **ZonedDateTime**, **ZoneId**, **DateTimeFormatter**, **Locale**. **instant** xác định thời điểm; **ZoneId** xác định lịch/giờ tại Việt Nam; **Locale** chọn tên ngày/tháng và dấu tương ứng. Không gán một stdout ngôn ngữ bản địa cố định vì các tên dựa trên dữ liệu JDK.

Nếu dùng **LocalDateTime** không gắn timezone, nó là giá trị lịch + giờ địa phương, không tự tương ứng một Instant. Không nên lấy LocalDateTime của server rồi coi nó là thời điểm thực tế của mọi người dùng.

**Quy ước 12/24h** cũng khác với timezone. Locale có thể có quy tắc ưa dùng một hệ nhưng pattern **h:mm a** đã chọn 12h, còn **HH:mm** đã chọn 24h. Nếu giao diện để người dùng chọn hệ giờ, quyết định pattern phải theo preference, không chỉ locale.

## 17. ResourceBundle và văn bản bản dịch

Khi muốn viết câu có ngày tháng trong một ngôn ngữ cụ thể, pattern có thể được lưu trong ResourceBundle:

~~~properties
# messages_en.properties
appointment=Appointment: {0}
~~~

~~~properties
# messages_vi.properties
appointment=Lịch hẹn: {0}
~~~

Đây là hai tệp minh họa trên classpath. Trong một phương thức Java, bạn có thể:

1. Resolve locale người dùng theo danh sách ứng dụng hỗ trợ.
2. Định dạng ngày/giờ bằng DateTimeFormatter với locale/zone thích hợp.
3. Lấy câu văn từ ResourceBundle theo cùng locale và chính sách fallback.
4. Dùng **MessageFormat** hoặc phương thức ghép an toàn để chèn văn bản đã định dạng.

Đừng kỳ vọng **ResourceBundle** tự tạo tên tháng/ngày khi một chuỗi literal được hardcode. Nó chỉ chọn nội dung bản dịch có sẵn. Nếu đưa một **LocalDate** trực tiếp vào **MessageFormat** với **{0,date}**, hãy lưu ý Java 17 MessageFormat vẫn dùng hệ **java.text.DateFormat** cho kiểu ngày truyền thống; cần chủ động dùng adapter **DateTimeFormatter.toFormat()** hoặc định dạng trước thành String.

Một câu dịch có thể đặt ngày trước hoặc sau từ nối, nên xây dựng pattern/cấu trúc theo ngôn ngữ chứ không chỉ thay vài từ tiếng Anh trong một mẫu cố định.

## 18. Những lỗi phổ biến

### Lỗi 1: Tưởng TextStyle là CSS

**TextStyle.FULL/SHORT/NARROW** là kiểu tên ngày/tháng theo ngôn ngữ, không đặt font-size, font-weight hay màu sắc. Không thể dùng NARROW để bảo đảm chuỗi vừa một số pixel nhất định.

### Lỗi 2: Dùng FULL thay FULL_STANDALONE trong tiêu đề

Trong một số ngôn ngữ có biến cách, tên tháng khi đứng độc lập khác tên tháng đi kèm ngày. Dùng **LLLL** hoặc **FULL_STANDALONE** cho tiêu đề khi phù hợp.

### Lỗi 3: Hardcode chữ cái đầu làm nhãn NARROW

Chữ đầu của tên đầy đủ không đảm bảo tương đương tên hẹp chính thức và có thể trùng nhau. Dùng TextStyle.NARROW/NARROW_STANDALONE từ dữ liệu locale, hoặc một nhãn sản phẩm được thiết kế riêng.

### Lỗi 4: Nhầm getValue với số thứ trong lịch địa phương

**DayOfWeek.getValue()** là ISO; vị trí cột theo locale nên dùng WeekFields và không phải lúc nào thứ Hai cũng đứng đầu.

### Lỗi 5: Dùng h mà quên a

Định dạng **9:30** theo hệ 12 giờ có thể không phân biệt 09:30 và 21:30. Khi cần, dùng **h:mm a**; hoặc dùng **HH:mm** để tránh nhập nhằng.

### Lỗi 6: Cho rằng 12:00 là AM

**LocalTime.NOON** là PM, **LocalTime.MIDNIGHT** là AM. Với hệ 12 giờ, nửa đêm là 12:00 AM và giữa trưa là 12:00 PM.

### Lỗi 7: Coi B đồng nghĩa với a

**B** là period-of-day linh hoạt, còn **a** chỉ là AM/PM. Các nhãn và ranh giới B phụ thuộc dữ liệu locale; không tự gán hẳn “ca sáng/ca tối” của doanh nghiệp vào nó.

### Lỗi 8: Tưởng đổi Locale sẽ dịch cả literal trong pattern

Pattern **"EEEE 'at' HH:mm"** luôn giữ chữ **at**; tên thứ thay đổi theo locale nhưng từ nối không thay. Dùng pattern hoặc ResourceBundle đã dịch đầy đủ.

### Lỗi 9: Cho rằng tên tháng/ngày không đổi giữa mọi JDK

Dữ liệu CLDR, provider và phiên bản Java có thể cập nhật dạng chữ. Với snapshot test exact, kiểm soát runtime hoặc assertion theo tính chất có ý nghĩa.

### Lỗi 10: Parse bằng NARROW hoặc sai locale

Tên hẹp có thể nhập nhằng; tên tháng tiếng Nga/Việt có thể không đọc được bằng formatter en-US. Chọn formatter đúng ngôn ngữ và style của input, kiểm tra lỗi parse.

### Lỗi 11: Dùng TextStyle để suy ra timezone

TextStyle và Locale không xác định ZoneId. Một Instant có thể rơi vào ngày lịch khác ở hai múi giờ. Chọn zone theo dữ liệu của người dùng/nghiệp vụ.

### Lỗi 12: Dùng DateTimeFormatter không truyền locale trong server

**DateTimeFormatter.ofPattern(pattern)** không có locale tường minh có thể sử dụng default locale của môi trường. Hai máy có thể sinh tên tháng/ngày hoặc nhãn AM/PM khác. Với đầu ra theo user, dùng **ofPattern(pattern, locale)** hoặc **withLocale(locale)**.

## 19. Kiểm thử bản địa hóa tên tháng/ngày và kỳ trong ngày

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| **Month.OCTOBER** dưới en-US/vi-VN/ru-RU | Tên đúng locale; full/standalone theo nhu cầu |
| **DayOfWeek.WEDNESDAY** FULL/SHORT/NARROW | Tên đầy đủ, viết tắt, dạng hẹp đúng ngữ cảnh |
| Lịch en-US và ISO | Khác biệt ngày đầu tuần nhưng getValue ISO không đổi |
| **MMMM** so với **LLLL** | Tên tháng trong câu và tiêu đề độc lập |
| **EEEE** so với **cccc** | Ngữ cảnh tên ngày trong tuần |
| **00:00**, **12:00**, **21:05** với **h:mm a** | AM/PM và giờ 12 tiếng không nhầm |
| **B** tại 00:00, 09:30, 12:00, 15:15, 22:00 | Nhãn day period theo dữ liệu locale |
| Parse **28 October 2026** theo en-US | Trả LocalDate chính xác |
| Parse tên viết tắt có dấu | Không tự bỏ dấu/case khi không có chính sách |
| Chuỗi pattern có literal tiếng Anh | Kiểm tra literal không tự dịch khi đổi locale |
| Cùng locale qua hai JDK hỗ trợ | Nhận diện khác biệt CLDR/provid­er nếu cần |
| Cùng Instant qua hai ZoneId | Ngày lịch/giờ địa phương tính đúng zone |
| Không gian lịch rất hẹp | TextStyle.NARROW không làm mất khả năng phân biệt/accessibility |

Nên **test logic có kiểu** (LocalDate, LocalTime, Month, DayOfWeek, AMPM_OF_DAY) riêng với **test nội dung bản địa hóa**. Đối với dữ liệu locale, chỉ chốt các chuỗi nguyên văn khi sản phẩm thực sự cần và môi trường đã được xác định. Đối với logic, assert giá trị ISO hoặc Instant thay vì phụ thuộc tên tháng hoặc ngày bằng chữ.

### 19.1. Test ổn định khi locale mặc định JVM khác

Một chương trình đã truyền locale vào mọi formatter có thể được chạy dưới các môi trường mặc định khác nhau bằng startup properties trong các tiến trình riêng:

~~~bash
java -Duser.language=en -Duser.country=US MonthDayPeriodDemo
java -Duser.language=de -Duser.country=DE MonthDayPeriodDemo
~~~

Các lệnh trên chạy cùng class sau khi biên dịch. Vì chương trình dùng **Locale.US** tường minh, nhãn en-US không nên đổi chỉ vì default JVM khác. Không nên dùng **Locale.setDefault()** trong test chạy song song; đó là trạng thái toàn JVM, dễ gây race.

**Với test B hoặc locale khác nhau theo phiên bản**, hãy chạy trên runtime mà ứng dụng hỗ trợ và ghi rõ dữ liệu localizations được dùng thay vì bắt mọi JDK trả một chuỗi y hệt.

## 20. Bài tập tự kiểm tra

1. Viết một tiêu đề tháng cho người dùng tiếng Nga: nên thử **MMMM** hay **LLLL**? Tại sao?
2. Tại sao **DayOfWeek.SUNDAY.getValue()** vẫn bằng 7 dù lịch Hoa Kỳ mở đầu bằng Chủ nhật?
3. Dùng TextStyle.NARROW làm duy nhất nhãn nhập ngày trong tuần có rủi ro gì?
4. Vì sao **h:mm** có thể nhập nhằng, còn **h:mm a** ít nhập nhằng hơn?
5. **B** và **a** khác gì nhau nếu cùng format LocalTime 09:30?
6. Chỉ thay locale của formatter có dịch được literal **'at'** trong pattern không?
7. Khi cần hiển thị cùng Instant ở Việt Nam và Hoa Kỳ, vì sao phải xác định ZoneId?
8. Nếu snapshot tiếng Việt khác sau nâng cấp JDK nhưng LocalDate không đổi, cần kiểm tra gì?

**Gợi ý trả lời:** (1) **LLLL** cho tiêu đề standalone, kiểm thử theo locale; (2) getValue là ISO, WeekFields điều khiển lịch địa phương; (3) nhãn hẹp có thể trùng/khó đọc; (4) thiếu AM/PM không phân biệt hai nửa ngày; (5) a chia hai nửa, B dùng quy tắc kỳ linh hoạt; (6) không; (7) Instant không có ngày giờ địa phương nếu chưa chọn zone; (8) phiên bản JDK/CLDR, locale provider và pattern/style.

## 21. Checklist thực hành

- Dùng **Month.getDisplayName(TextStyle, Locale)** cho tên tháng và **DayOfWeek.getDisplayName(TextStyle, Locale)** cho tên ngày.
- Chọn **FULL/SHORT/NARROW** theo không gian hiển thị và khả năng đọc, không tự cắt chuỗi thủ công.
- Dùng **STANDALONE** khi ngôn ngữ và ngữ cảnh yêu cầu tên tháng/ngày độc lập.
- Phân biệt **MMMM** với **LLLL**, **EEEE** với **cccc**, và **e/c** dạng số tuần địa phương với ISO DayOfWeek.getValue.
- Dùng **a** cho AM/PM; cân nhắc **B** khi cần period-of-day linh hoạt trong Java 17.
- Không nhầm **H**, **h**, **K**, **k**, nhất là ở 00:00 và 12:00.
- Với kỳ AM/PM dạng text, có thể dùng **DateTimeFormatterBuilder.appendText(ChronoField.AMPM_OF_DAY, TextStyle)**.
- Dùng **DateTimeFormatter.ofPattern(pattern, locale)** hoặc localized format kết hợp **withLocale(locale)**, không vô tình dựa trên default JVM.
- Đảm bảo các literal, giới từ và câu văn xung quanh được dịch, không nghĩ TextStyle dịch toàn bộ pattern.
- Khi định dạng Instant, truyền **ZoneId** tường minh theo dữ liệu user/nghiệp vụ.
- Khi parse, dùng locale/style đúng của input, tránh NARROW nhập nhằng và xử lý DateTimeParseException.
- Kiểm thử tên bản địa trên các JDK hỗ trợ, đặc biệt FULL_STANDALONE, SHORT và pattern B.
- Với API/dữ liệu máy, ưu tiên ISO numeric thay vì tên tháng, ngày hoặc kỳ trong ngày đã địa phương hóa.

## 22. Kết luận

**TextStyle trong Java Time quyết định hình thức chữ của tên tháng, tên ngày và một số trường thời gian, không thay thế Locale hoặc pattern.** **Month** và **DayOfWeek** cung cấp **getDisplayName(TextStyle, Locale)**; **DateTimeFormatter** dùng **M/L**, **E/e/c** và **a/B** để mô tả tên, ngữ cảnh độc lập và kỳ trong ngày. Với AM/PM, **ChronoField.AMPM_OF_DAY** biểu diễn hai nửa ngày, còn pattern **B** dùng quy tắc kỳ trong ngày linh hoạt theo dữ liệu locale của Java 17.

Để chương trình rõ ràng và dễ kiểm thử, luôn xác định **locale người xem**, dùng **STANDALONE** nơi phù hợp, giữ riêng ngày giờ có kiểu khỏi văn bản bản địa hóa và quản lý **ZoneId** khi chuyển Instant sang giờ địa phương. Tránh hardcode tên tháng hoặc cắt chữ viết tắt, đồng thời kiểm thử đúng phiên bản JDK/CLDR để xử lý thay đổi dữ liệu bản địa hóa có chủ đích.
