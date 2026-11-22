# Phân biệt M với L và dạng tên tháng độc lập trong Java

## 1. Vì sao cùng một tháng có thể có hai tên khác nhau?

Khi định dạng ngày tháng theo `Locale`, một số ngôn ngữ dùng **dạng tên tháng theo ngữ cảnh của một ngày** khác với **dạng tên tháng đứng độc lập**. Trong Java, hai chữ cái mẫu quan trọng là:

- **`M`** (*month-of-year*, dạng theo ngữ cảnh): dùng khi tên tháng là thành phần của biểu thức ngày, ví dụ “ngày 5 tháng Ba”.
- **`L`** (*stand-alone month-of-year*, dạng độc lập): dùng khi tên tháng là nhãn riêng của lịch, tiêu đề tháng hoặc mục chọn tháng, không nằm trong câu có ngày.

Đây **không phải hai loại tháng khác nhau**. Cả `M` và `L` cùng chỉ **giá trị tháng trong năm**, ví dụ tháng 3. Khác biệt nằm ở **cách biểu diễn tên tháng**, phụ thuộc ngôn ngữ và dữ liệu locale.

Ví dụ với `Locale.forLanguageTag("ru-RU")` trong Java 17+ có dữ liệu locale thông dụng:

| Ngữ cảnh | Mẫu Java | Kết quả tiếng Nga | Ý nghĩa |
| --- | --- | --- | --- |
| Ngày đầy đủ | `d MMMM uuuu` | `5 марта 2025` | `марта` là dạng tên tháng đi cùng ngày |
| Tên tháng riêng | `LLLL` | `март` | `март` là tên tháng đứng độc lập |
| Chỉ lấy trường tháng ở dạng theo ngữ cảnh | `MMMM` | `марта` | Không thích hợp làm tiêu đề tháng độc lập ở locale này |
| Số tháng | `MM` hoặc `LL` | `03` | Khi dùng dạng số, cả hai có thể giống nhau |

Với tiếng Anh `en-US`, `MMMM` và `LLLL` đều thường cho `March`. Chính vì vậy một chương trình chỉ thử ở tiếng Anh có thể **không phát hiện** việc dùng sai loại tên tháng ở tiếng Nga, Ba Lan hoặc Séc.

**Nguyên tắc:** Khi hiển thị ngày có số ngày, ưu tiên `M` theo đúng mẫu ngày của locale; khi hiển thị **tên tháng độc lập**, ưu tiên `L` và kiểm thử trên các locale mà ứng dụng hỗ trợ. Không giả định tất cả ngôn ngữ có quy tắc ngữ pháp tương tự tiếng Anh.

## 2. M và L trong DateTimeFormatter

`java.time.format.DateTimeFormatter` sử dụng ký tự mẫu để chọn trường thời gian, độ dài biểu diễn và kiểu văn bản. Với tháng:

| Pattern | `M` — dạng ngữ cảnh | `L` — dạng đứng độc lập |
| --- | --- | --- |
| `M` / `L` | Tháng dạng số, ví dụ `3` | Tháng dạng số, ví dụ `3` |
| `MM` / `LL` | Tháng dạng số có hai chữ số, ví dụ `03` | Tháng dạng số có hai chữ số, ví dụ `03` |
| `MMM` / `LLL` | Tên ngắn theo ngữ cảnh, ví dụ tiếng Nga có thể là `мар.` | Tên ngắn độc lập, ví dụ tiếng Nga có thể là `март` |
| `MMMM` / `LLLL` | Tên đầy đủ theo ngữ cảnh, ví dụ `марта` | Tên đầy đủ độc lập, ví dụ `март` |
| `MMMMM` / `LLLLL` | Dạng rất ngắn (*narrow*) theo ngữ cảnh | Dạng rất ngắn (*narrow stand-alone*) |

Bảng này mô tả **ý nghĩa mẫu**, không phải hứa rằng kết quả khác nhau trong mọi locale. Tùy ngôn ngữ và dữ liệu JDK, các dạng có thể giống hệt nhau, một số dạng viết tắt có thể không tồn tại riêng, hoặc provider phải fallback sang hình thức sẵn có.

Đối với `java.time`, số lần lặp ký tự `M`/`L` có ý nghĩa:

- **Một ký tự:** biểu diễn tháng dưới dạng số không yêu cầu thêm số 0.
- **Hai ký tự:** biểu diễn tháng dưới dạng số hai chữ số.
- **Ba ký tự:** tên tháng ngắn.
- **Bốn ký tự:** tên tháng đầy đủ.
- **Năm ký tự:** dạng *narrow*, thường rất ngắn và có thể trùng nhau giữa nhiều tháng.

**Cẩn thận với ký tự:** `M` (chữ hoa) là tháng; `m` (chữ thường) là **phút**. `L` (chữ L hoa) là tháng độc lập, không phải chữ số `1`. Ví dụ, `"HH:mm"` có `mm` chỉ phút, còn `"uuuu-MM-dd"` có `MM` chỉ tháng.

### “Độc lập” ở đây là dạng ngữ pháp, không phải kiểu dữ liệu khác

Một `LocalDate` chứa các trường năm, tháng và ngày. Khi format cùng ngày bằng `MMMM` và `LLLL`, số tháng trong dữ liệu vẫn bằng `3`. Chỉ có quy tắc đặt tên tháng được chọn khác nhau.

Không diễn giải `L` như một “loại lịch khác”, “múi giờ khác”, hay “chuyển đổi tháng sang một giá trị khác”. Cả `M` và `L` đều làm việc với `MONTH_OF_YEAR`, theo chronology và locale của formatter.

## 3. Ví dụ Java 17+ hoàn chỉnh: tháng Ba trong bốn locale

Tạo tệp `MonthContextDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

public class MonthContextDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 3, 5);
        List<String> tags = List.of(
                "ru-RU", "pl-PL", "cs-CZ", "en-US"
        );

        for (String tag : tags) {
            Locale locale = Locale.forLanguageTag(tag);

            DateTimeFormatter dayAndMonth =
                    DateTimeFormatter.ofPattern("d MMMM uuuu", locale);
            DateTimeFormatter standalone =
                    DateTimeFormatter.ofPattern("LLLL", locale);

            System.out.println(tag);
            System.out.println("  In a date: "
                    + date.format(dayAndMonth));
            System.out.println("  Month title: "
                    + date.format(standalone));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MonthContextDemo.java
java MonthContextDemo
~~~

Với dữ liệu locale CLDR thường dùng trên JDK hiện đại, kết quả tham khảo:

~~~text
ru-RU
  In a date: 5 марта 2025
  Month title: март
pl-PL
  In a date: 5 marca 2025
  Month title: marzec
cs-CZ
  In a date: 5 března 2025
  Month title: březen
en-US
  In a date: 5 March 2025
  Month title: March
~~~

### Giải thích kết quả

**Tiếng Nga (ru-RU).** Khi viết một ngày đầy đủ, tháng thường ở dạng `марта`. Khi tiêu đề chỉ có tên tháng, dạng độc lập `март` phù hợp hơn.

**Tiếng Ba Lan (pl-PL).** Trong ngày `5 marca 2025`, tên tháng ở dạng `marca`; khi đứng một mình là `marzec`.

**Tiếng Séc (cs-CZ).** Mẫu ngày có `března`; tên tháng đứng riêng có `březen`.

**Tiếng Anh (en-US).** Cả hai tình huống đều dùng `March`, nên chỉ kiểm tra ngôn ngữ này có thể che giấu lỗi thiết kế.

Các chuỗi cụ thể phụ thuộc dữ liệu locale của phiên bản JDK và provider. Không nên gắn cứng kết quả vào mọi môi trường Java rồi coi mọi khác biệt là lỗi API; cần kiểm thử trên môi trường sản phẩm thật và xác nhận chính sách ngôn ngữ mong muốn.

## 4. Chọn M hoặc L theo tình huống giao diện

### 4.1. Ngày đầy đủ trong câu hoặc lịch hẹn

Nếu giao diện in ngày, chẳng hạn “5 tháng Ba năm 2025”, hãy dùng dạng tên tháng theo ngữ cảnh:

~~~java
Locale ru = Locale.forLanguageTag("ru-RU");
LocalDate day = LocalDate.of(2025, 3, 5);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("d MMMM uuuu", ru);

String text = day.format(formatter);
~~~

Đoạn trên là **mảnh mã minh họa trong method**, cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter` và `java.util.Locale`.

Trong `ru-RU`, `text` thường là `5 марта 2025`.

**Không thay `MMMM` bằng `LLLL` chỉ vì muốn tháng viết đầy đủ.** `LLLL` có thể đưa tên tháng về dạng độc lập dù nó đang nằm trong một biểu thức có ngày. Ví dụ `"d LLLL uuuu"` có thể tạo `"5 март 2025"`, không đúng hình thái ngữ pháp thông thường của tiếng Nga.

### 4.2. Tiêu đề một tháng trong calendar

Khi in nhãn `March 2025` ở phía trên lịch tháng, ngày cụ thể không xuất hiện. Hãy chọn `LLLL uuuu`:

~~~java
Locale ru = Locale.forLanguageTag("ru-RU");
LocalDate day = LocalDate.of(2025, 3, 5);

DateTimeFormatter header =
        DateTimeFormatter.ofPattern("LLLL uuuu", ru);

String title = day.format(header);
~~~

Kết quả tiếng Nga thông dụng: `март 2025`.

Đối với header, date picker, danh sách chọn tên tháng, ô filter “Tháng”, hay biểu đồ có tiêu đề chỉ chứa tháng, cách dùng `L` là lựa chọn rõ nghĩa. Nếu thiết kế muốn một cụm từ ngữ pháp riêng như “trong tháng Ba”, có thể phải dùng thông điệp được dịch hoặc mẫu khác, không giả định một pattern tự giải quyết toàn bộ biến cách ngữ pháp.

### 4.3. Tên ngắn và tên rất ngắn

Với tiếng Nga, trong dữ liệu JDK/CLDR thông dụng:

~~~java
DateTimeFormatter contextShort =
        DateTimeFormatter.ofPattern("MMM", ru);
DateTimeFormatter standaloneShort =
        DateTimeFormatter.ofPattern("LLL", ru);
~~~

Đoạn trên là **mảnh mã trong method**, có `ru` đã là `Locale` phù hợp. Chúng có thể cho `мар.` và `март`. Điều này cho thấy **khác biệt không chỉ giới hạn ở `MMMM`/`LLLL`**: dạng ngắn cũng có thể khác.

Mẫu `MMMMM` hoặc `LLLLL` thường cho dạng *narrow* như một chữ cái. Nó có thể mơ hồ vì nhiều tháng có cùng chữ cái đầu. Chỉ dùng dạng hẹp khi giao diện có ngữ cảnh bổ trợ (ví dụ lưới lịch với tháng được xác định theo năm/vị trí), và không mặc định nó đủ để người dùng phân biệt các tháng bằng tên.

### 4.4. Tháng dạng số

Với một ngày có tháng 3:

~~~java
DateTimeFormatter numericM =
        DateTimeFormatter.ofPattern("MM", Locale.US);
DateTimeFormatter numericL =
        DateTimeFormatter.ofPattern("LL", Locale.US);
~~~

Cả hai thường trả `03`. Khi chỉ cần số tháng, sự khác biệt hình thái của tên tháng không xuất hiện. Tuy nhiên, để code dễ đọc và theo quy ước phổ biến, khi xây dựng ngày ISO như `"uuuu-MM-dd"` nên dùng `MM`; còn `L` dành cho **dạng tên tháng độc lập** khi cần văn bản.

## 5. So sánh trực tiếp M/MM/MMM/MMMM/MMMMM với L/LL/LLL/LLLL/LLLLL

Tạo `MonthWidthsDemo.java` để quan sát cùng một thời điểm:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class MonthWidthsDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2025, 3, 5);
        Locale ru = Locale.forLanguageTag("ru-RU");

        for (int width = 1; width <= 5; width++) {
            String mPattern = "M".repeat(width);
            String lPattern = "L".repeat(width);

            String contextual = day.format(
                    DateTimeFormatter.ofPattern(mPattern, ru)
            );
            String standalone = day.format(
                    DateTimeFormatter.ofPattern(lPattern, ru)
            );

            System.out.println(mPattern + ": " + contextual
                    + " | " + lPattern + ": " + standalone);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MonthWidthsDemo.java
java MonthWidthsDemo
~~~

Trên JDK có dữ liệu locale Nga như minh họa:

~~~text
M: 3 | L: 3
MM: 03 | LL: 03
MMM: мар. | LLL: март
MMMM: марта | LLLL: март
MMMMM: М | LLLLL: М
~~~

Bài học từ bảng kết quả:

- Dạng số giống nhau không làm cho hai ký tự mẫu tương đương ở mọi độ dài.
- Dạng ngắn `MMM`/`LLL` có thể khác.
- Dạng đầy đủ `MMMM`/`LLLL` có thể khác rõ nhất.
- Dạng rất ngắn `MMMMM`/`LLLLL` có thể giống nhau dù dạng đầy đủ khác, vì tên rút gọn quá ngắn để thể hiện biến cách.

Từ Java 11 trở lên có `String.repeat(int)`; do đó vòng lặp dùng `"M".repeat(width)` chạy tốt trên Java 17+.

## 6. Dùng TextStyle để diễn đạt trực tiếp dạng tên tháng

`DateTimeFormatter` không chỉ hỗ trợ chuỗi pattern. Nó còn có `DateTimeFormatterBuilder.appendText` và `java.time.format.TextStyle`. Cặp nhóm cần biết:

| Tên trong `TextStyle` | Ý nghĩa | Tương ứng pattern tháng |
| --- | --- | --- |
| `FULL` | Tên đầy đủ theo ngữ cảnh | `MMMM` |
| `FULL_STANDALONE` | Tên đầy đủ độc lập | `LLLL` |
| `SHORT` | Tên ngắn theo ngữ cảnh | `MMM` |
| `SHORT_STANDALONE` | Tên ngắn độc lập | `LLL` |
| `NARROW` | Tên hẹp theo ngữ cảnh | `MMMMM` |
| `NARROW_STANDALONE` | Tên hẹp độc lập | `LLLLL` |

Với trường tháng, cả hai nhóm đều lấy giá trị từ `ChronoField.MONTH_OF_YEAR`.

### Ví dụ hoàn chỉnh: pattern và builder tương đương về ý định

Lưu `MonthTextStyleDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class MonthTextStyleDemo {
    public static void main(String[] args) {
        Locale ru = Locale.forLanguageTag("ru-RU");
        LocalDate day = LocalDate.of(2025, 3, 5);

        DateTimeFormatter fromPattern =
                DateTimeFormatter.ofPattern("LLLL", ru);

        DateTimeFormatter fromBuilder =
                new DateTimeFormatterBuilder()
                        .appendText(ChronoField.MONTH_OF_YEAR,
                                TextStyle.FULL_STANDALONE)
                        .toFormatter(ru);

        DateTimeFormatter contextual =
                new DateTimeFormatterBuilder()
                        .appendText(ChronoField.MONTH_OF_YEAR,
                                TextStyle.FULL)
                        .toFormatter(ru);

        System.out.println("LLLL: " + day.format(fromPattern));
        System.out.println("FULL_STANDALONE: "
                + day.format(fromBuilder));
        System.out.println("FULL: " + day.format(contextual));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MonthTextStyleDemo.java
java MonthTextStyleDemo
~~~

Kết quả tham khảo với locale Nga thông dụng:

~~~text
LLLL: март
FULL_STANDALONE: март
FULL: марта
~~~

### Chọn pattern hay TextStyle?

- `ofPattern("LLLL", locale)` ngắn gọn khi mẫu ngày/tháng được cấu hình bằng một chuỗi.
- `DateTimeFormatterBuilder` phù hợp khi xây dựng formatter bằng code, cần ghép nhiều trường hoặc chọn `TextStyle` rõ ràng theo ý đồ.
- `TextStyle.FULL_STANDALONE` diễn đạt trực tiếp “dạng tên tháng độc lập”, có thể dễ hiểu hơn một chữ cái `L` với người đọc code chưa quen cú pháp pattern.
- Cả hai vẫn phụ thuộc **locale** và dữ liệu locale để lấy tên tháng; builder không tự dịch hay tự tạo biến cách ngữ pháp.

Không nhầm `TextStyle.FULL` với “luôn dùng trong mọi nơi muốn tên dài”. `FULL` là **dạng theo ngữ cảnh**, còn `FULL_STANDALONE` là **dạng độc lập**.

## 7. Parsing: có nên dùng M và L khác nhau khi đọc chuỗi?

Không chỉ việc format, `DateTimeFormatter` cũng có thể **parse** tên tháng từ văn bản. Pattern của parser cần phù hợp với dạng tên tháng được viết ra.

Ví dụ, khi muốn đọc tiêu đề tiếng Nga chứa tên tháng độc lập và năm, dùng `LLLL uuuu` thay vì cố ép parser nhận dạng ngày đầy đủ:

~~~java
Locale ru = Locale.forLanguageTag("ru-RU");
DateTimeFormatter monthTitle =
        DateTimeFormatter.ofPattern("LLLL uuuu", ru);

YearMonth input = YearMonth.parse("март 2025", monthTitle);
~~~

Đây là **mảnh mã minh họa trong method**, cần import `java.time.YearMonth`, `java.time.format.DateTimeFormatter` và `java.util.Locale`. Trong môi trường có dữ liệu tên tháng Nga tương ứng, `input` mang giá trị `2025-03`.

### Ví dụ chạy được tránh phụ thuộc cách gõ chữ Cyrillic

Lưu `MonthRoundTripDemo.java`:

~~~java
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class MonthRoundTripDemo {
    public static void main(String[] args) {
        Locale ru = Locale.forLanguageTag("ru-RU");
        YearMonth original = YearMonth.of(2025, 3);

        DateTimeFormatter standalone =
                DateTimeFormatter.ofPattern("LLLL uuuu", ru);
        DateTimeFormatter contextual =
                DateTimeFormatter.ofPattern("MMMM uuuu", ru);

        String title = original.format(standalone);
        String contextualText = original.format(contextual);

        YearMonth parsedTitle = YearMonth.parse(title, standalone);
        YearMonth parsedContext =
                YearMonth.parse(contextualText, contextual);

        System.out.println("Standalone title: " + title);
        System.out.println("Contextual month: " + contextualText);
        System.out.println("Parsed title: " + parsedTitle);
        System.out.println("Parsed context: " + parsedContext);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MonthRoundTripDemo.java
java MonthRoundTripDemo
~~~

Kết quả với dữ liệu locale tiếng Nga điển hình:

~~~text
Standalone title: март 2025
Contextual month: марта 2025
Parsed title: 2025-03
Parsed context: 2025-03
~~~

**Hai chuỗi có thể parse về cùng `YearMonth`**: sự khác biệt là hình thái của tên tháng trong văn bản. Khi tích hợp với form, không nên tạo chuỗi bằng `LLLL` rồi parse bằng `MMMM` và hy vọng parser luôn chấp nhận dạng kia. Chính sách parse có thể phụ thuộc provider, dữ liệu locale và cài đặt độ nghiêm ngặt của formatter.

### Không dùng narrow form làm đầu vào duy nhất

Dạng rất ngắn `MMMMM`/`LLLLL` đôi khi chỉ là một ký tự. Nhiều tháng có thể trùng chữ cái đầu, ví dụ cùng bắt đầu bằng `M`. Vì vậy nó không phù hợp để parse tháng một cách duy nhất trong trường hợp thiếu thông tin bổ trợ. Đối với input của người dùng, chọn dạng tháng đầy đủ, dạng số hoặc control ngày/tháng có cấu trúc.

Nếu dữ liệu trao đổi giữa các dịch vụ, nên ưu tiên số tháng `1–12`, `YearMonth`/ISO dạng `uuuu-MM` hoặc đối tượng cấu trúc, không biến tên tháng bản địa hóa thành giao thức máy.

## 8. DateTimeFormatter.ofLocalizedDate và mẫu tùy chỉnh

Một lựa chọn thường tốt hơn tự áp đặt mẫu ngày cho tất cả người dùng là:

~~~java
DateTimeFormatter localized = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.forLanguageTag("ru-RU"));
~~~

Đây là **mảnh mã minh họa trong method**, cần import `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle` và `java.util.Locale`.

`ofLocalizedDate(FormatStyle.LONG)` để locale/provider quyết định **thứ tự và cách biểu diễn các thành phần của ngày**. Khi định dạng `LocalDate`, kết quả có thể có dạng ngữ pháp phù hợp cho một ngày đầy đủ mà không phải tự chọn từng ký tự pattern.

So sánh:

- **Mẫu tự đặt** `"d MMMM uuuu"`: bạn kiểm soát bố cục ngày và chọn dạng tháng theo ngữ cảnh. Thích hợp khi UI có yêu cầu bố cục thống nhất.
- **Localized style**: để locale định nghĩa kiểu ngày đầy đủ. Thường tốt cho giao diện hướng người dùng quốc tế có nhiều quy ước ngày khác nhau.
- **Tên tháng riêng** `"LLLL"`: khi chỉ cần nhãn tháng, không phải một ngày hoàn chỉnh.

Không nên lấy pattern `"d MMMM uuuu"` rồi áp dụng nguyên cho mọi locale và khẳng định cách viết luôn tự nhiên: một số vùng có trật tự ngày/tháng/năm hoặc giới từ, dấu câu, dạng ký tự khác nhau. Mẫu chính xác cần xuất phát từ yêu cầu sản phẩm hoặc dữ liệu locale phù hợp.

## 9. SimpleDateFormat: M và L trong API cũ

Java cũng có `java.text.SimpleDateFormat` thuộc hệ API thời gian cũ. Với nhiều locale, nó hỗ trợ:

- `M`: tên tháng theo ngữ cảnh;
- `L`: tên tháng đứng độc lập.

Tạo `LegacyMonthDemo.java`:

~~~java
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;

public class LegacyMonthDemo {
    public static void main(String[] args) {
        Locale ru = Locale.forLanguageTag("ru-RU");

        Calendar calendar = new GregorianCalendar(
                2025, Calendar.MARCH, 5
        );
        Date date = calendar.getTime();

        SimpleDateFormat inDate =
                new SimpleDateFormat("d MMMM yyyy", ru);
        SimpleDateFormat standalone =
                new SimpleDateFormat("LLLL", ru);

        System.out.println("Date: " + inDate.format(date));
        System.out.println("Month title: " + standalone.format(date));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LegacyMonthDemo.java
java LegacyMonthDemo
~~~

Kết quả tham khảo:

~~~text
Date: 5 марта 2025
Month title: март
~~~

**Phân biệt về thiết kế:**

- `SimpleDateFormat` gắn với `java.util.Date`/`Calendar` và có trạng thái **mutable**, không an toàn để chia sẻ không đồng bộ giữa nhiều luồng.
- `DateTimeFormatter` thuộc `java.time`, **bất biến và thread-safe**, thích hợp cho Java mới.
- `Calendar.MARCH` là hằng số chỉ tháng 3 trong API cũ, nơi tháng của `Calendar` thường được đánh số từ 0. Trong `java.time`, `Month.MARCH` có giá trị tháng `3` và `LocalDate.of(2025, 3, 5)` dùng tháng 1–12. **Không nhầm đánh số tháng của Calendar với pattern M/L**.
- `SimpleDateFormat` có các quy tắc pattern và xử lý lịch/leniency riêng. Không suy mọi cấu trúc của `java.time` có cùng hành vi parse với API cũ.

Nếu dự án đang bắt đầu, ưu tiên `LocalDate`, `YearMonth`, `DateTimeFormatter`. Nếu bảo trì code cũ, vẫn cần nhận biết `L` để tránh nhãn tháng sai ngữ pháp.

## 10. Locale nào cần quan tâm đặc biệt?

Không có một danh sách bất biến áp dụng cho mọi phiên bản dữ liệu, nhưng một số ví dụ giàu tính học tập là:

| Locale | Mẫu `d MMMM uuuu`, tháng Ba | Mẫu `LLLL`, tháng Ba | Nhận xét |
| --- | --- | --- | --- |
| `ru-RU` | `5 марта 2025` | `март` | Có biến cách rõ ràng |
| `pl-PL` | `5 marca 2025` | `marzec` | Tên tháng trong ngày khác tên độc lập |
| `cs-CZ` | `5 března 2025` | `březen` | Tên tháng phụ thuộc ngữ cảnh |
| `en-US` | `5 March 2025` | `March` | Hai dạng thường giống nhau |
| `vi-VN` | Có thể dùng tên/số tháng theo dữ liệu Việt | Tên tháng độc lập theo dữ liệu Việt | Không suy mọi ngôn ngữ có hai dạng khác nhau |

Tháng Ba chỉ là một trường hợp để minh họa. Khi một locale có nhiều cách biến đổi tên tháng, mức độ khác nhau có thể tùy tháng, độ rộng (ngắn/đầy đủ/hẹp) và dữ liệu CLDR.

**Không tự dịch quy tắc Nga sang mọi ngôn ngữ:** `LLLL` có nghĩa *stand-alone* theo API, không phải quy tắc “đổi sang cách 1” cố định. Nếu ngôn ngữ không có hình thái riêng, tên tháng có thể giống `MMMM`.

## 11. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `MMMM` làm tiêu đề lịch tháng ở mọi locale | Một số ngôn ngữ hiện tên ở dạng dùng trong ngày | Dùng `LLLL` cho tên tháng độc lập |
| Dùng `LLLL` trong mẫu ngày có số ngày | Có thể tạo câu sai ngữ pháp như `5 март 2025` | Dùng `MMMM` hoặc `ofLocalizedDate` |
| Chỉ kiểm thử `en-US` | Không thấy khác biệt giữa `MMMM` và `LLLL` | Kiểm thử `ru-RU`, `pl-PL` hoặc locale liên quan |
| Nghĩ `M` và `L` có giá trị tháng khác nhau | Hiểu sai dữ liệu thời gian | Cùng biểu diễn `MONTH_OF_YEAR`, khác ngữ cảnh văn bản |
| Nhầm `MM` và `mm` | In phút ở nơi muốn tháng | `MM` là tháng, `mm` là phút |
| Lấy chuỗi `MMMMM`/`LLLLL` làm định danh tháng | Tên hẹp có thể trùng nhau | Lưu số tháng/`YearMonth` hoặc khóa nội bộ |
| Ép `MMMM` mọi nơi vì muốn tên “đầy đủ” | Sai trường hợp stand-alone | Chọn nhóm `M`/`L` theo ngữ cảnh trước, rồi chọn width |
| Tự thay tên tháng bằng `switch` cho từng locale | Khó bảo trì, bỏ sót hình thái/CLDR | Dùng `DateTimeFormatter` với locale |
| Dùng `Locale.getDefault()` cho người dùng nhiều vùng | Kết quả theo server chứ không theo người nhận | Truyền `Locale` tường minh |
| Giả định `L` tự giải quyết mọi biến cách trong câu | Một câu cụ thể có thể cần giới từ/cấu trúc khác | Dùng bản dịch/ResourceBundle nếu ngữ pháp vượt mẫu ngày |
| Share `SimpleDateFormat` giữa nhiều luồng | Có thể hỏng trạng thái và kết quả | Dùng `DateTimeFormatter` bất biến hoặc bảo vệ formatter cũ |
| Trộn số tháng `Calendar` 0-based với `LocalDate` 1-based | Lệch tháng khi chuyển đổi | Kiểm tra chỉ số của từng API, không gán nhầm |

## 12. Thiết kế ứng dụng: giữ ngày ở dạng có cấu trúc

Một giao diện lịch có thể cần đồng thời:

1. **Ngày của sự kiện:** `LocalDate`, ví dụ `2025-03-05`.
2. **Dòng ngày hiển thị:** formatter theo locale với dạng `M` và cấu trúc ngày thích hợp.
3. **Tiêu đề lịch:** formatter chỉ tên tháng đứng độc lập `LLLL`, có thể kèm năm `uuuu`.
4. **Giá trị máy:** giữ `YearMonth.of(2025,3)` hoặc tháng dạng số, không lấy chuỗi bản địa hóa làm khóa.
5. **Ngôn ngữ của UI:** `Locale` do người dùng lựa chọn, không mặc định lấy theo JVM.

Ví dụ class tiện ích:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class CalendarLabels {
    private CalendarLabels() {}

    public static String dayLabel(LocalDate day, Locale locale) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("d MMMM uuuu", locale);
        return day.format(format);
    }

    public static String monthHeader(LocalDate day, Locale locale) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("LLLL uuuu", locale);
        return day.format(format);
    }
}
~~~

Tạo tệp `CalendarLabels.java`. Class trên có hai method độc lập, mô tả rõ ý đồ. Khi hệ thống có nhiều thứ tự ngày tháng, thay `dayLabel` bằng formatter kiểu localized phù hợp chính sách ứng dụng. Để dùng class:

~~~java
LocalDate day = LocalDate.of(2025, 3, 5);
Locale ru = Locale.forLanguageTag("ru-RU");

System.out.println(CalendarLabels.dayLabel(day, ru));
System.out.println(CalendarLabels.monthHeader(day, ru));
~~~

Đây là **mảnh mã trong method** cần import `java.time.LocalDate` và `java.util.Locale`, đồng thời class `CalendarLabels` đã được biên dịch. Với dữ liệu Nga thông dụng, kết quả `5 марта 2025` và `март 2025`.

**Không lưu `"март 2025"` thay cho `YearMonth`.** Chuỗi tiêu đề có thể đổi khi người dùng chọn ngôn ngữ khác hoặc khi JDK cập nhật dữ liệu locale; dữ liệu ngày có cấu trúc không bị phụ thuộc hình thức trình bày.

## 13. M, L không thay thế chronology và timezone

Một số yêu cầu localization có lịch riêng (chronology), hệ chữ số khác hoặc múi giờ cụ thể. Chọn `MMMM` hay `LLLL` **không tự quyết định**:

- Hệ lịch (ISO, Buddhist, Japanese hay hệ khác).
- Múi giờ khi hiển thị một `Instant`.
- Hệ chữ số của trường ngày/tháng.
- Ngôn ngữ của toàn bộ câu ngoài phần tên tháng.

`LocalDate` trong ví dụ dùng ngày theo ISO chronology. Với `Instant`, cần chọn `ZoneId` trước khi diễn giải thành ngày địa phương; locale là yếu tố khác. Khi dùng chronology không phải ISO, cách tìm tên tháng còn tùy formatter, chronology và dữ liệu provider.

Ví dụ, một ngày ở `Asia/Ho_Chi_Minh` có thể khác ngày của cùng `Instant` ở `America/Los_Angeles`. Không thể sửa chênh lệch ngày bằng cách đổi `M` sang `L`. Hai chữ cái chỉ liên quan đến **cách biểu diễn tháng**, không phải phép chuyển đổi thời gian.

## 14. Kiểm thử thực tế trên nhiều locale

### 14.1. Checklist

- Với `ru-RU` và `pl-PL`, thử cùng `LocalDate.of(2025,3,5)` ở `d MMMM uuuu` và `LLLL`.
- Thử `MMM` và `LLL` để kiểm tra dạng viết tắt.
- Thử `MM` và `LL` để chứng minh cả hai dùng cùng giá trị số tháng.
- So sánh kết quả giữa `TextStyle.FULL` và `TextStyle.FULL_STANDALONE`.
- Kiểm tra `ofLocalizedDate(FormatStyle.LONG)` với giao diện ngày tự nhiên.
- Nếu parse tên tháng, kiểm thử `YearMonth.parse` bằng đúng formatter đã dùng khi format.
- Không dựa hoàn toàn vào test `en-US`, bởi tên tháng có thể giống giữa hai context.
- Nếu test exact text, chạy trên cùng JDK, cấu hình provider và dữ liệu locale với production.
- Kiểm thử trường hợp nhiều tháng khác nhau, không chỉ tháng Ba, đặc biệt nếu ứng dụng dùng dạng *narrow*.
- Dùng kiểu `YearMonth`/`LocalDate` làm dữ liệu chính; chuỗi tháng chỉ là lớp trình bày.

### 14.2. Bài tập

1. Dùng `Locale.forLanguageTag("ru-RU")` format ngày `2025-03-05` theo `"d MMMM uuuu"` và `"LLLL uuuu"`. Giải thích vì sao chúng không nên dùng hoán đổi trong cùng một vị trí UI.
2. Thử tương tự với `pl-PL`: vì sao tên tháng đơn lẻ thường là `marzec` nhưng trong ngày là `marca`?
3. Viết một vòng lặp so sánh `M`/`L`, `MM`/`LL`, `MMM`/`LLL`, `MMMM`/`LLLL`, `MMMMM`/`LLLLL`. Nhận xét dạng nào khác, dạng nào có thể trùng.
4. Dùng `TextStyle.FULL_STANDALONE` để xây dựng formatter tiêu đề tháng với `DateTimeFormatterBuilder` mà không sử dụng `ofPattern("LLLL")`.
5. Dùng `YearMonth` để format rồi parse tên tháng độc lập và năm. Nếu thay formatter parser từ `LLLL` thành `MMMM`, vì sao kết quả không còn được bảo đảm?
6. So sánh `SimpleDateFormat` và `DateTimeFormatter` trong Java 17 về loại đối tượng ngày và tính an toàn đa luồng.
7. Một date picker cần hiện tên tháng `LLLL`, một thông báo giao hàng cần ngày đầy đủ. Chọn API/mẫu phù hợp và giải thích cách tách model khỏi chuỗi hiển thị.
8. Tại sao `"MM"` có thể cho kết quả giống `"LL"`, nhưng `"MMMM"` lại có thể khác `"LLLL"`?

**Ghi nhớ:** Trong `DateTimeFormatter`, `M` là **tháng ở dạng văn bản theo ngữ cảnh**, còn `L` là **tên tháng đứng độc lập**. Khi dạng số, `M` và `L` thường giống nhau; khi dùng tên ngắn hoặc đầy đủ, nhiều locale như tiếng Nga và tiếng Ba Lan có khác biệt ngữ pháp rõ rệt. **Ngày có số ngày → ưu tiên `MMMM` hoặc formatter ngày địa phương hóa; tiêu đề/tháng đứng riêng → ưu tiên `LLLL`.** Chọn locale rõ ràng, giữ giá trị ngày ở dạng có cấu trúc và kiểm thử trên những ngôn ngữ thực sự có hai dạng tên tháng.

### Tài liệu tham khảo

- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — ký tự mẫu `M`/`L` và định dạng ngày theo locale.
- [Java SE 17 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) — `appendText` và trường tháng.
- [Java SE 17 — TextStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/TextStyle.html) — `FULL_STANDALONE` và các dạng tên tháng.
- [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html) — mẫu tháng ngữ cảnh và độc lập trong API cũ.
- [Java SE 17 — YearMonth](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/YearMonth.html) — đối tượng năm/tháng không phụ thuộc tên bản địa hóa.