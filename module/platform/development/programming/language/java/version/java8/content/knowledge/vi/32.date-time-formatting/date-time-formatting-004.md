# Locale, FormatStyle và tên ngày, tháng trong Java 8

Ứng dụng hiển thị cùng một ngày theo nhiều ngôn ngữ thường phải đáp ứng những kỳ vọng rất khác nhau. Ngày **06/11/2026** có thể được trình bày là **“Friday, November 6, 2026”** đối với người dùng Mỹ, **“vendredi 6 novembre 2026”** tại Pháp, hoặc **“Thứ Sáu, 6 tháng 11, 2026”** trong ngữ cảnh tiếng Việt. Không chỉ dịch từ: thứ tự ngày/tháng/năm, dấu phân cách, dạng viết tắt, kiểu đồng hồ 12/24 giờ và cách chia tuần đều có thể phụ thuộc **Locale**.

Trong Java 8, **`java.time.format.DateTimeFormatter`**, **`FormatStyle`**, **`TextStyle`** cùng **`java.util.Locale`** cung cấp công cụ định dạng ngày giờ theo ngữ cảnh người dùng. Các API này vẫn đang được sử dụng trên Java hiện đại. Bài học tập trung vào cách chọn Locale, dùng các mức FormatStyle, lấy và hiển thị đúng **tên ngày trong tuần/tên tháng**, xử lý dạng ngữ pháp tháng phụ thuộc ngữ cảnh, parse văn bản có tên tháng, kiểm thử và tránh dùng chuỗi hiển thị làm định dạng dữ liệu máy.

**Ý chính:** giá trị `LocalDate`/`LocalTime`/`LocalDateTime` và cách **trình bày** nó là hai khái niệm khác nhau. Đổi Locale không đổi ngày thực, và cũng **không tự đổi múi giờ**. Cần chọn rõ Locale ở ranh giới hiển thị và chọn định dạng máy ổn định ở ranh giới dữ liệu.

## 1. Locale là gì và nó ảnh hưởng những gì?

`Locale` mô tả quy ước ngôn ngữ và khu vực mà ứng dụng muốn dùng, thường có **language tag** như:

| Locale | Language tag | Ngữ cảnh điển hình |
| --- | --- | --- |
| `Locale.US` | `en-US` | Tiếng Anh theo quy ước Mỹ |
| `Locale.UK` | `en-GB` | Tiếng Anh theo quy ước Anh |
| `Locale.FRANCE` | `fr-FR` | Tiếng Pháp tại Pháp |
| `Locale.GERMANY` | `de-DE` | Tiếng Đức tại Đức |
| `Locale.forLanguageTag("vi-VN")` | `vi-VN` | Tiếng Việt tại Việt Nam |
| `Locale.forLanguageTag("ru-RU")` | `ru-RU` | Tiếng Nga tại Nga |
| `Locale.JAPAN` | `ja-JP` | Tiếng Nhật tại Nhật |

Trong Java 8:

```java
// Đoạn minh họa.
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale french = Locale.FRANCE;
Locale us = Locale.US;
```

Ngôn ngữ và khu vực có tác động tới các lựa chọn hiển thị như:

- Tên đầy đủ hoặc viết tắt của **thứ trong tuần** và **tháng**.
- Thứ tự **ngày/tháng/năm**, dấu phẩy, dấu chấm hoặc dấu gạch chéo.
- Biểu diễn 12 giờ với AM/PM hoặc đồng hồ 24 giờ trong các style cục bộ.
- Cách viết ngày/tháng tùy ngữ pháp, ví dụ tiếng Nga có **tháng trong ngữ cảnh ngày** khác với **tên tháng đứng riêng**.
- Một số quy ước **ngày đầu tuần, số ngày tối thiểu trong tuần đầu năm**, liên quan `WeekFields`.

Locale **không phải** timezone: `Locale.FRANCE` không có nghĩa người dùng chắc chắn ở `Europe/Paris`, và `Locale.US` không thể nói event đang thuộc múi giờ New York hay Los Angeles.

## 2. Tách domain date/time và chuỗi hiển thị

Giả sử hệ thống lưu ngày hóa đơn:

```java
LocalDate invoiceDate = LocalDate.of(2026, 11, 6);
```

Nó là một ngày lịch ISO, chưa chứa chuỗi tiếng Anh hay tiếng Việt. Cùng một đối tượng có thể format theo nhiều Locale:

```java
// Đoạn minh họa.
DateTimeFormatter us = DateTimeFormatter
    .ofLocalizedDate(FormatStyle.FULL)
    .withLocale(Locale.US);

DateTimeFormatter vi = DateTimeFormatter
    .ofLocalizedDate(FormatStyle.FULL)
    .withLocale(Locale.forLanguageTag("vi-VN"));

String usText = invoiceDate.format(us);
String viText = invoiceDate.format(vi);
```

**Không thay đổi ngày trong dữ liệu** chỉ để phù hợp định dạng cho một locale. Nếu ở Mỹ người dùng muốn đọc “November 6” còn ở Việt Nam đọc “6 tháng 11”, đó là **presentation**, không phải hai ngày khác nhau.

Phân biệt ba tầng:

1. **Domain:** `LocalDate`, `LocalTime`, `LocalDateTime` hoặc `ZonedDateTime` theo nghĩa nghiệp vụ.
2. **Presentation:** `DateTimeFormatter` với Locale/FormatStyle phù hợp người xem.
3. **Wire/storage:** định dạng máy có hợp đồng rõ, thường là ISO-8601 hoặc kiểu thời gian native của database.

Đừng dùng chuỗi “Thứ Sáu, 6 tháng 11, 2026” làm khóa sắp xếp hay kiểu gốc của ngày hóa đơn. Chuỗi hiển thị có thể thay đổi theo locale data và khó parse chính xác nếu ngôn ngữ không được quy định.

## 3. FormatStyle.FULL, LONG, MEDIUM và SHORT

`FormatStyle` là enum của `java.time.format` trong Java 8, với bốn mức biểu diễn:

| Style | Mục tiêu | Ví dụ mô tả (không phải format cố định mọi locale) |
| --- | --- | --- |
| `FULL` | Ngày/giờ với thông tin văn bản đầy đủ | Thứ Sáu, ngày 6 tháng 11... |
| `LONG` | Dạng dài nhưng có thể ít chi tiết hơn FULL | 6 tháng 11 năm 2026 |
| `MEDIUM` | Gọn vừa phải, thường có tên tháng rút gọn | Nov 6, 2026 hoặc 6 nov. 2026 |
| `SHORT` | Ngắn gọn, thường dạng số và năm ngắn | 11/6/26 hoặc 06/11/2026 |

**Không xem bảng này là quy chuẩn cụ thể về số ký tự.** FormatStyle mô tả **mức độ**. Mẫu chi tiết do locale data provider của JDK quyết định. Chẳng hạn SHORT không nhất thiết có cùng thứ tự ngày-tháng tại Mỹ và Pháp, và FULL không nhất thiết có cùng dấu câu giữa các ngôn ngữ.

Những nhà máy tạo formatter cần biết:

```java
DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL);
DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT);
DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM);
DateTimeFormatter.ofLocalizedDateTime(
    FormatStyle.LONG, FormatStyle.SHORT);
```

Chúng tạo formatter dùng các quy tắc định dạng locale. Nên gọi `withLocale(locale)` rõ ràng để áp Locale người dùng/chi nhánh.

### Chú ý dữ liệu mà style đòi hỏi

Một formatter FULL/LONG cho **time** ở nhiều locale cần thông tin về timezone để hiển thị phần tên vùng. Vì vậy định dạng `LocalTime` không có zone bằng FULL time có thể ném `DateTimeException` do thiếu trường thời gian được formatter yêu cầu.

Không mặc định rằng mọi tổ hợp `FormatStyle` với mọi kiểu temporal đều có thể format. Đối với `LocalTime`, các style ngắn như SHORT thường phù hợp; đối với một thời điểm có zone, có thể dùng `ZonedDateTime` và formatter phù hợp.

## 4. ofLocalizedDate với Locale: cùng ngày, định dạng khác

Một chương trình độc lập cho thấy sự khác nhau của FULL, MEDIUM, SHORT.

### LocalizedDateStylesDemo.java

```java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class LocalizedDateStylesDemo {
    static void show(LocalDate date, Locale locale) {
        DateTimeFormatter full =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
                .withLocale(locale);
        DateTimeFormatter medium =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);
        DateTimeFormatter shortDate =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale);

        System.out.println(locale.toLanguageTag() + " FULL=" +
            date.format(full));
        System.out.println(locale.toLanguageTag() + " MEDIUM=" +
            date.format(medium));
        System.out.println(locale.toLanguageTag() + " SHORT=" +
            date.format(shortDate));
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 11, 6);

        show(date, Locale.US);
        show(date, Locale.FRANCE);
        show(date, Locale.forLanguageTag("vi-VN"));

        String iso = date.format(DateTimeFormatter.ISO_LOCAL_DATE);
        if (!"2026-11-06".equals(iso)) {
            throw new AssertionError("ISO format");
        }

        System.out.println("ISO=" + iso);
        System.out.println("PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LocalizedDateStylesDemo.java
java LocalizedDateStylesDemo
```

Khi dùng JDK mới và muốn xác minh chỉ sử dụng API Java 8:

```bash
javac --release 8 -encoding UTF-8 LocalizedDateStylesDemo.java
java LocalizedDateStylesDemo
```

**Stdout đã quan sát và kiểm thử trên JDK chạy ví dụ:**

```text
en-US FULL=Friday, November 6, 2026
en-US MEDIUM=Nov 6, 2026
en-US SHORT=11/6/26
fr-FR FULL=vendredi 6 novembre 2026
fr-FR MEDIUM=6 nov. 2026
fr-FR SHORT=06/11/2026
vi-VN FULL=Thứ Sáu, 6 tháng 11, 2026
vi-VN MEDIUM=6 thg 11, 2026
vi-VN SHORT=6/11/26
ISO=2026-11-06
PASS
```

**Lưu ý về stdout locale:** tên ngày/tháng, dấu câu, viết hoa và các mẫu local có thể thay đổi theo phiên bản JDK, nhà cung cấp locale data hoặc cấu hình locale provider. Đầu ra trên là **kết quả thật của môi trường thử nghiệm**, không phải lời hứa mọi JDK phải trả đúng từng dấu phẩy. Trong unit test cross-JDK, nên kiểm **đúng semantic và round-trip** cho formatter được cấu hình, hoặc cố định môi trường khi cần snapshot output.

Đọc ví dụ:

- Ngày cố định `2026-11-06` luôn là ngày đó, dù hiển thị ở ba ngôn ngữ.
- FULL có thể gồm tên thứ; SHORT có thể dùng ngày dạng số.
- Locale tiếng Việt có “Thứ Sáu”, tên tháng và từ “tháng”.
- `DateTimeFormatter.ISO_LOCAL_DATE` cho `2026-11-06`, phù hợp làm format trao đổi ngày trong API khi hợp đồng dùng ISO.
- Ngay trong SHORT, `en-US` dùng tháng trước ngày trong khi `fr-FR` thường dùng ngày trước tháng.

## 5. Khác biệt giữa FormatStyle và ofPattern

Có hai hướng định dạng, đừng nhầm chúng:

**A. Định dạng theo quy ước locale với FormatStyle**

```java
// Để JDK chọn mẫu theo Locale đã chỉ định.
DateTimeFormatter localized = DateTimeFormatter
    .ofLocalizedDate(FormatStyle.LONG)
    .withLocale(Locale.FRANCE);
```

Lợi thế: cách trình bày phù hợp quy ước của locale được hỗ trợ. Hạn chế: mẫu cụ thể có thể thay đổi khi locale data thay đổi, không phù hợp nếu API yêu cầu output cố định từng dấu.

**B. Định dạng theo mẫu do bạn viết**

```java
// Cố định thứ tự trường, nhưng tên tháng vẫn chịu ảnh hưởng Locale.
DateTimeFormatter custom = DateTimeFormatter
    .ofPattern("EEEE, d MMMM uuuu",
               Locale.forLanguageTag("vi-VN"));
```

Lợi thế: chủ động chọn thứ tự, trường và dấu phân cách. Hạn chế: mẫu tự viết không tự động trở thành cách diễn đạt **tự nhiên trong mọi ngôn ngữ**. Thứ tự và ngữ pháp hợp với tiếng Việt có thể không hợp tiếng Nga, tiếng Nhật hoặc tiếng Pháp.

**Nguyên tắc chọn:** FormatStyle khi ưu tiên quy ước địa phương của người đọc; ofPattern khi có yêu cầu biểu diễn rất cụ thể và **đã biết Locale**. Đối với giao tiếp máy, thường dùng formatter ISO chuẩn hơn là pattern giao diện địa phương.

## 6. Ký hiệu pattern cho tên ngày/tháng

Các ký hiệu cần nhớ trong `DateTimeFormatter.ofPattern`:

| Ký hiệu | Ý nghĩa | Hướng dùng |
| --- | --- | --- |
| `E`, `EEE` | Tên thứ trong tuần viết tắt | Fri, ven., Th 6... tùy locale |
| `EEEE` | Tên thứ đầy đủ | Friday, vendredi, Thứ Sáu... |
| `EEEEE` | Tên thứ dạng rất ngắn | Có thể một chữ hoặc dạng narrow |
| `M` hoặc `MM` | Tháng dạng số | 11, 11 |
| `MMM` | Tên tháng rút gọn trong ngữ cảnh ngày | Nov, nov., thg 11... |
| `MMMM` | Tên tháng đầy đủ trong ngữ cảnh ngày | November, novembre, ноября... |
| `L`, `LLL`, `LLLL` | Tháng dạng stand-alone | Tên tháng khi đứng riêng, có thể khác `M` |
| `d`, `dd` | Ngày trong tháng | 6 hoặc 06 |
| `u`, `uuuu` | Năm proleptic | 2026 |
| `H`, `HH` | Giờ 24h | 9 hoặc 09 |
| `h`, `hh` | Giờ 12h | Dùng với AM/PM `a` khi cần |
| `a` | AM/PM theo locale | Phụ thuộc ngôn ngữ |
| `e` / `c` | Day-of-week dạng localized/stand-alone | Mục đích chuyên biệt, cần kiểm pattern count |

**Đừng nhầm chữ hoa chữ thường.** Trong `DateTimeFormatter`, `M` là **tháng**, còn `m` là **phút**; `H` là giờ 24 tiếng, `h` là giờ 12 tiếng. Một lỗi mẫu có thể khiến output sai dù code vẫn chạy.

Để parse ngày ISO nghiêm ngặt, mẫu `uuuu` thường đơn giản hơn `yyyy` trong cách dùng `ResolverStyle.STRICT`: `u` là năm proleptic, còn `y` là year-of-era và có thể cần era để resolve một `LocalDate`. Không thay `uuuu` bằng `yyyy` vô điều kiện khi đang xây formatter nghiêm ngặt.

## 7. DayOfWeek và Month.getDisplayName(TextStyle, Locale)

Ngoài `DateTimeFormatter`, Java 8 cho phép lấy tên từng thành phần:

```java
// Đoạn minh họa.
Locale vi = Locale.forLanguageTag("vi-VN");
String friday = DayOfWeek.FRIDAY
    .getDisplayName(TextStyle.FULL, vi);

String month = Month.NOVEMBER
    .getDisplayName(TextStyle.FULL, vi);
```

`TextStyle` có những dạng:

| TextStyle | Ngữ nghĩa |
| --- | --- |
| `FULL` | Tên đầy đủ trong ngữ cảnh thông thường |
| `SHORT` | Tên ngắn/viết tắt |
| `NARROW` | Dạng hẹp, thường dùng khi giao diện bị giới hạn |
| `FULL_STANDALONE` | Tên đầy đủ khi thành phần **đứng riêng** |
| `SHORT_STANDALONE` | Tên ngắn đứng riêng |
| `NARROW_STANDALONE` | Dạng hẹp đứng riêng |

Dạng `NARROW` không nhất thiết **duy nhất**: nhiều thứ trong tuần có thể cùng một chữ đầu trong một ngôn ngữ. Không dùng nó làm ID, key hay dữ liệu cần phân biệt chính xác thứ. Dùng `DayOfWeek` enum hay giá trị số đã xác định cho logic, rồi mới format tên cho UI.

**Đáng chú ý:** `TextStyle.FULL_STANDALONE` và pattern `LLLL` khác với `TextStyle.FULL`/`MMMM` ở một số ngôn ngữ có biến cách ngữ pháp.

## 8. Tên tháng theo ngữ cảnh và đứng riêng: ví dụ tiếng Nga

Tiếng Nga minh họa rõ sự khác nhau giữa “tên tháng trong một ngày” và “tiêu đề tháng”.

Với ngày **6 tháng 11 năm 2026**:

- Khi là một phần của câu ngày: **“6 ноября 2026”** (dạng tháng phụ thuộc ngữ pháp).
- Khi tên tháng đứng riêng như tiêu đề lịch: **“ноябрь”**.

Java 8 có các pattern:

```java
// Minh họa, date=LocalDate.of(2026,11,6).
Locale ru = Locale.forLanguageTag("ru-RU");

String inDate = date.format(
    DateTimeFormatter.ofPattern("d MMMM uuuu", ru));

String monthHeading = date.format(
    DateTimeFormatter.ofPattern("LLLL", ru));
```

**Không tự thay `MMMM` bằng `LLLL` trong mọi câu**, vì ở ngôn ngữ có biến cách, dạng đứng riêng có thể không phù hợp trong cụm ngày đầy đủ. Ngược lại, `MMMM` có thể không phải tên tháng tự nhiên để làm heading không có số ngày.

Trong vài locale không phân biệt hai dạng hoặc dữ liệu locale có thể fallback, nên hai kết quả có thể giống nhau. Thiết kế cần dựa trên **ngữ cảnh sử dụng** thay vì đòi mọi locale phải cho hai chuỗi khác.

## 9. Chương trình 2: tên thứ, tên tháng và dạng đứng riêng

Tệp **`DayMonthTextDemo.java`** minh họa cả tiếng Nga và tiếng Việt.

```java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class DayMonthTextDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 11, 6);
        Locale ru = Locale.forLanguageTag("ru-RU");
        Locale vi = Locale.forLanguageTag("vi-VN");

        String russianInDate = date.format(
            DateTimeFormatter.ofPattern("d MMMM uuuu", ru));

        String russianMonthStandalone = date.format(
            DateTimeFormatter.ofPattern("LLLL", ru));

        String russianMonthContext = date.format(
            DateTimeFormatter.ofPattern("MMMM", ru));

        String vietnameseFull = date.format(
            DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", vi));

        String vietnameseShort = date.format(
            DateTimeFormatter.ofPattern("EEE, d MMM uuuu", vi));

        String fridayVi = DayOfWeek.FRIDAY
            .getDisplayName(TextStyle.FULL, vi);

        String novemberRu = Month.NOVEMBER
            .getDisplayName(TextStyle.FULL_STANDALONE, ru);

        System.out.println("ruDate=" + russianInDate);
        System.out.println("ruContext=" + russianMonthContext);
        System.out.println("ruStandalone=" + russianMonthStandalone);
        System.out.println("ruMonthName=" + novemberRu);
        System.out.println("viDate=" + vietnameseFull);
        System.out.println("viShort=" + vietnameseShort);
        System.out.println("viFriday=" + fridayVi);

        if (russianInDate.isEmpty() || russianMonthStandalone.isEmpty()
                || vietnameseFull.isEmpty() || fridayVi.isEmpty()) {
            throw new AssertionError("localized text");
        }
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 DayMonthTextDemo.java
java DayMonthTextDemo
```

**Stdout đã quan sát:**

```text
ruDate=6 ноября 2026
ruContext=ноября
ruStandalone=ноябрь
ruMonthName=ноябрь
viDate=Thứ Sáu, 6 tháng 11 2026
viShort=Th 6, 6 thg 11 2026
viFriday=Thứ Sáu
PASS
```

**Giải thích:**

1. `MMMM` trong câu ngày cho “ноября”; `LLLL` đứng riêng cho “ноябрь”.
2. `TextStyle.FULL_STANDALONE` cho tên tháng phù hợp khi hiển thị riêng.
3. Format pattern có dấu phẩy do **bạn** đặt, không nhất thiết trùng định dạng FULL tự nhiên do JDK chọn.
4. `EEEE` cho tên thứ đầy đủ; `EEE` cho dạng rút gọn theo locale data, ở ví dụ có thể là “Th 6”.
5. Các chuỗi trên là output thử nghiệm của JDK đang chạy. Một bản JDK khác có thể dùng từ viết tắt, dấu cách hoặc cách viết hoa khác nhưng vẫn đúng theo locale provider của nó.

### Khi nào dùng getDisplayName thay vì format cả ngày?

Dùng `getDisplayName` khi UI cần một **nhãn độc lập** như tiêu đề cột lịch “Thứ Hai” hoặc tên tháng “Tháng Mười Một”. Dùng `DateTimeFormatter` cho **cả ngày**, vì việc ghép tên thứ + số ngày + tên tháng bằng tay dễ sai ngữ pháp hoặc dấu câu giữa các locale.

## 10. Locale trong parsing: không chỉ dùng cho đầu ra

Nếu dữ liệu đầu vào có tên tháng dạng chữ, parser phải biết Locale. Ví dụ “6 novembre 2026” là tiếng Pháp; nếu parser dùng Locale.US, nó không thể được kỳ vọng hiểu đúng chữ `novembre`.

Một formatter:

```java
// Minh họa.
DateTimeFormatter french = DateTimeFormatter
    .ofPattern("d MMMM uuuu", Locale.FRANCE)
    .withResolverStyle(ResolverStyle.STRICT);
```

có thể dùng cả:

```java
String text = date.format(french);
LocalDate parsed = LocalDate.parse(text, french);
```

**ResolverStyle.STRICT** yêu cầu thông tin lịch nhất quán, giúp từ chối ngày sai thay vì âm thầm điều chỉnh. Nếu pattern chứa **tên thứ** đồng thời với ngày/tháng/năm, giá trị thứ không khớp với ngày cũng nên bị phát hiện trong parsing strict.

Một vài ranh giới parsing quan trọng:

- Locale phải trùng với ngôn ngữ của văn bản đầu vào, không chỉ lấy mặc định của server.
- Pattern phải phù hợp với cấu trúc văn bản đã nhận, bao gồm dấu chấm/ dấu phẩy/ khoảng trắng.
- Tên tháng và thứ phụ thuộc locale data provider; nếu nhận input tự do đa ngôn ngữ, cần chính sách ngôn ngữ rõ hoặc parser riêng.
- Parser mặc định không phải công cụ đoán ngôn ngữ hoặc chuẩn hóa mọi cách viết tắt tùy ý.
- Parsing không sửa sai timezone: một `LocalDate` parse đúng vẫn chỉ là ngày lịch, chưa có múi giờ.

### Có nên parse trực tiếp chuỗi UI của mọi locale bằng một formatter?

Không. Nếu hệ thống có nhiều locale, mỗi request phải mang hoặc suy ra ngôn ngữ đã được xác thực từ ngữ cảnh user. Một formatter tiếng Anh không phải parser đa ngôn ngữ tổng quát.

Khi bạn kiểm soát cả producer/consumer qua API, nên dùng dữ liệu ngày ở dạng ISO thay vì gửi chuỗi tên tháng theo ngôn ngữ người dùng. Việc parse chữ là nhu cầu **giao diện hoặc nhập liệu**, không phải định dạng máy tối ưu.

## 11. Chương trình 3: parse tháng tiếng Pháp và từ chối thứ không khớp

Tệp **`LocaleParsingDemo.java`** minh họa round-trip cùng Locale, sai Locale, và kiểm tính nhất quán của ngày trong tuần bằng STRICT.

```java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class LocaleParsingDemo {
    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        LocalDate expected = LocalDate.of(2026, 11, 6);

        DateTimeFormatter french = DateTimeFormatter
            .ofPattern("d MMMM uuuu", Locale.FRANCE)
            .withResolverStyle(ResolverStyle.STRICT);

        String frenchText = expected.format(french);
        LocalDate parsed = LocalDate.parse(frenchText, french);

        boolean wrongLocaleRejected = false;
        try {
            LocalDate.parse(frenchText,
                DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US));
        } catch (DateTimeParseException ex) {
            wrongLocaleRejected = true;
        }

        DateTimeFormatter strictEnglish = DateTimeFormatter
            .ofPattern("EEEE d MMMM uuuu", Locale.US)
            .withResolverStyle(ResolverStyle.STRICT);

        boolean weekdayConflictRejected = false;
        try {
            LocalDate.parse("Thursday 6 November 2026", strictEnglish);
        } catch (DateTimeParseException ex) {
            weekdayConflictRejected = true;
        }

        check(expected.equals(parsed), "localized round trip");
        check(wrongLocaleRejected, "wrong locale should fail");
        check(weekdayConflictRejected, "wrong weekday should fail");

        System.out.println("frText=" + frenchText);
        System.out.println("parsed=" + parsed);
        System.out.println("wrongLocaleRejected=" + wrongLocaleRejected);
        System.out.println(
            "weekdayConflictRejected=" + weekdayConflictRejected);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocaleParsingDemo.java
java LocaleParsingDemo
```

**Stdout đã kiểm chứng:**

```text
frText=6 novembre 2026
parsed=2026-11-06
wrongLocaleRejected=true
weekdayConflictRejected=true
PASS
```

Chú ý: `2026-11-06` là **Friday**, không phải Thursday. Parser strict phát hiện khi tên thứ mâu thuẫn với ngày lịch trong cùng input.

### Có dùng equals để so ngày sau khi parse không?

Có. `LocalDate.equals` so giá trị ngày, không phải chuỗi trình bày. Đó là cách đúng để kiểm round-trip khi chuỗi format có thể thay đổi theo Locale.

### Nếu muốn chấp nhận chữ hoa/chữ thường linh hoạt thì sao?

`DateTimeFormatterBuilder.parseCaseInsensitive()` là API Java 8 hiện còn dùng, có thể bổ sung vào formatter **khi chính sách nhập liệu cho phép**. Không tùy tiện chuẩn hóa hay tự dịch tên tháng bằng `String.toLowerCase()` với locale mặc định; các ngôn ngữ có quy tắc case mapping khác nhau. Với input nhạy tính hợp lệ, hãy rõ ràng về mức linh hoạt và test.

## 12. Locale và định dạng giờ theo kiểu 12/24 tiếng

Locale cũng ảnh hưởng cách biểu diễn giờ:

```java
// Minh họa có LocalTime time=LocalTime.of(14,5).
DateTimeFormatter us = DateTimeFormatter
    .ofLocalizedTime(FormatStyle.SHORT)
    .withLocale(Locale.US);

DateTimeFormatter fr = DateTimeFormatter
    .ofLocalizedTime(FormatStyle.SHORT)
    .withLocale(Locale.FRANCE);
```

Trong một JDK dùng CLDR, một giờ 14:05 có thể hiển thị như “2:05 PM” cho US và “14:05” cho France. Đừng hardcode mẫu `hh:mm a` cho mọi locale nếu mong hiển thị tự nhiên. Ngược lại, nếu sản phẩm yêu cầu **24 giờ bất kể locale**, bạn có thể dùng pattern rõ ràng `HH:mm` và nêu chính sách UI.

### Locale không thay thế ZoneId

`LocalTime.of(14,5)` chỉ là thời gian đồng hồ, không tự biết nó ở Mỹ hay Pháp. `withLocale(Locale.US)` **không biến** 14:05 thành giờ New York. Nếu chuyển thời điểm giữa vùng, dùng `Instant`/`ZonedDateTime` và ZoneId có nghĩa nghiệp vụ trước, sau đó mới format.

### FULL time có thể cần timezone

Một số formatter FULL time có trường tên múi giờ, và `LocalTime` không cung cấp trường đó. Khi format, chương trình có thể ném `DateTimeException`. Đây là lý do phải chọn kiểu temporal phù hợp với độ chi tiết muốn hiển thị. Nếu cần FULL datetime với tên vùng, truyền một `ZonedDateTime` có ZoneId phù hợp.

## 13. Chương trình 4: localized time và FormatStyle.MEDIUM datetime

Tệp **`LocalizedTimeDemo.java`**:

```java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class LocalizedTimeDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalTime time = LocalTime.of(14, 5);
        LocalDateTime local = LocalDateTime.of(2026, 11, 6, 14, 5);

        DateTimeFormatter usShort =
            DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                .withLocale(Locale.US);
        DateTimeFormatter frShort =
            DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                .withLocale(Locale.FRANCE);
        DateTimeFormatter viDateTime =
            DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"));

        boolean fullNeedsZone = false;
        try {
            time.format(DateTimeFormatter
                .ofLocalizedTime(FormatStyle.FULL)
                .withLocale(Locale.US));
        } catch (DateTimeException ex) {
            fullNeedsZone = true;
        }

        check(fullNeedsZone, "full localized time generally needs zone");

        System.out.println("usShortTime=" + time.format(usShort));
        System.out.println("frShortTime=" + time.format(frShort));
        System.out.println(
            "viMediumDateTime=" + local.format(viDateTime));
        System.out.println(
            "fullTimeWithoutZoneRejected=" + fullNeedsZone);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocalizedTimeDemo.java
java LocalizedTimeDemo
```

**Stdout quan sát trong môi trường kiểm thử** (dòng US có thể chứa dấu cách Unicode hẹp trước PM):

```text
usShortTime=2:05 PM
frShortTime=14:05
viMediumDateTime=14:05:00 6 thg 11, 2026
fullTimeWithoutZoneRejected=true
PASS
```

**Lưu ý khi copy kết quả:** không suy từ vẻ ngoài của khoảng trắng rằng đó luôn là ASCII space; locale data có thể dùng no-break space, narrow no-break space hoặc các ký tự Unicode khác. Đừng so bằng chuỗi mong đợi tự viết một cách tùy tiện khi ứng dụng cần hỗ trợ nhiều JDK/locale provider.

Chương trình minh họa rằng:

1. SHORT time có thể khác định dạng 12/24 giờ theo Locale.
2. MEDIUM datetime ghép cả date và time theo quy ước của locale, không chỉ nối hai format tùy ý.
3. FULL time từ LocalTime có thể thất bại do thiếu zone; với ngữ cảnh thử nghiệm, hành vi này được assert rõ.
4. Không có phép đổi múi giờ trong câu lệnh `withLocale`.

## 14. Tên thứ, quy ước đầu tuần và WeekFields

Ngoài việc **hiển thị tên thứ**, Locale còn có thể ảnh hưởng cách đánh số tuần và xác định “tuần 1”.

Java 8 có `WeekFields.of(locale)`:

- `getFirstDayOfWeek()` trả ngày mở đầu tuần theo quy ước locale.
- `getMinimalDaysInFirstWeek()` trả số ngày tối thiểu cần có ở tuần đầu tiên.
- `weekBasedYear()` và `weekOfWeekBasedYear()` cho các trường tuần theo quy ước tương ứng.

Ví dụ quy ước phổ biến:

- US: tuần thường bắt đầu **Chủ Nhật**, tối thiểu **1 ngày** để tạo tuần 1.
- France: tuần thường bắt đầu **Thứ Hai**, tối thiểu **4 ngày** để tạo tuần 1.

Điều này **không đổi giá trị DayOfWeek của ngày thật**. Ngày 1/1/2021 là Friday trong cả hai locale. Tuy nhiên khi tính **week-based-year**, hai locale có thể cho năm tuần khác nhau.

**Không nhầm `DayOfWeek.getValue()` với số thứ theo locale.** `DayOfWeek.MONDAY.getValue()` theo ISO là 1; điều đó không nói rằng UI của mọi locale coi thứ Hai là ngày đầu tuần. Nếu cần tuần theo locale, dùng WeekFields.

## 15. Chương trình 5: quy ước tuần của US và France

Tệp **`WeekFieldsLocaleDemo.java`**:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.*;
import java.util.*;

public class WeekFieldsLocaleDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields fr = WeekFields.of(Locale.FRANCE);
        LocalDate yearBoundary = LocalDate.of(2021, 1, 1);

        check(us.getFirstDayOfWeek() == DayOfWeek.SUNDAY,
              "US starts Sunday");
        check(fr.getFirstDayOfWeek() == DayOfWeek.MONDAY,
              "France starts Monday");
        check(us.getMinimalDaysInFirstWeek() == 1,
              "US min days");
        check(fr.getMinimalDaysInFirstWeek() == 4,
              "France min days");

        int usWeekYear = yearBoundary.get(us.weekBasedYear());
        int frWeekYear = yearBoundary.get(fr.weekBasedYear());
        check(usWeekYear == 2021, "US week year");
        check(frWeekYear == 2020, "FR week year");

        System.out.println("usFirst=" + us.getFirstDayOfWeek());
        System.out.println("frFirst=" + fr.getFirstDayOfWeek());
        System.out.println(
            "usMinDays=" + us.getMinimalDaysInFirstWeek());
        System.out.println(
            "frMinDays=" + fr.getMinimalDaysInFirstWeek());
        System.out.println("usWeekYear=" + usWeekYear);
        System.out.println("frWeekYear=" + frWeekYear);
        System.out.println("date=" + yearBoundary);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 WeekFieldsLocaleDemo.java
java WeekFieldsLocaleDemo
```

**Stdout đã kiểm chứng:**

```text
usFirst=SUNDAY
frFirst=MONDAY
usMinDays=1
frMinDays=4
usWeekYear=2021
frWeekYear=2020
date=2021-01-01
PASS
```

Ứng dụng báo cáo theo tuần có thể cho kết quả khác nhau tại **biên năm** nếu lấy locale của người xem làm nguồn xác định week-based-year. Vì thế phải hỏi: “tuần của báo cáo theo chuẩn nào?” Có thể dùng **quy tắc ISO cố định** hoặc WeekFields của một locale nghiệp vụ; không tùy tiện áp locale của trình duyệt cho số liệu tài chính rồi khiến cùng dữ liệu thuộc hai kỳ báo cáo khác nhau.

Lựa chọn này liên quan đến Locale và quy ước địa phương, nhưng không phải chuyện “dịch tên thứ”: nó tác động tới **phân nhóm dữ liệu** và cần chính sách nghiệp vụ rõ.

## 16. Locale mặc định: nguy cơ test và môi trường khác nhau

Nếu không ghi rõ Locale:

```java
// Minh họa: ngữ cảnh Locale phụ thuộc môi trường.
DateTimeFormatter formatter =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL);
```

formatter sử dụng Locale mặc định cho định dạng tại thời điểm được tạo. Locale này có thể khác giữa máy lập trình, CI, server, container hoặc thiết bị của người dùng. Vì vậy code có thể hiển thị tên tháng/tên thứ khác mà không có thay đổi logic ngày giờ.

### Cách viết có ngữ nghĩa rõ

```java
Locale userLocale = Locale.forLanguageTag("vi-VN");
DateTimeFormatter formatter =
    DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
        .withLocale(userLocale);
```

Đối với sản phẩm đa ngôn ngữ, Locale nên lấy từ thiết lập người dùng hoặc quy tắc ứng dụng, không phụ thuộc ngẫu nhiên vào máy chủ.

**Không sử dụng `Locale.setDefault(...)` như cách chuyển ngôn ngữ riêng cho từng request web.** Đó là thay đổi trạng thái mặc định của tiến trình và có thể ảnh hưởng các request/luồng khác. Giữ Locale của người dùng trong dữ liệu request và truyền tường minh khi format.

Với thiết lập mặc định của JDK, có thể phân biệt `Locale.getDefault(Locale.Category.FORMAT)` và `Locale.getDefault(Locale.Category.DISPLAY)`. Khi tự chọn Locale cụ thể bằng `withLocale`, bạn giảm phụ thuộc vào các mặc định đó.

## 17. DateTimeFormatter là immutable và thread-safe

`DateTimeFormatter` được thiết kế **bất biến và an toàn khi dùng chung giữa các luồng**. Vì vậy có thể tái sử dụng một formatter cho cùng một locale/style:

```java
// Mã minh họa trong một class ứng dụng.
private static final DateTimeFormatter DATE_FR =
    DateTimeFormatter
        .ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(Locale.FRANCE);
```

Không cần tạo formatter lại trong mọi vòng lặp khi locale/style cố định. Với nhiều locale, có thể có cache các formatter theo locale và style, nhưng phải có chính sách bộ nhớ/phạm vi phù hợp; đừng xây một cache không giới hạn chỉ vì tất cả language tags từ client đều hợp lệ.

`withLocale(locale)` trả **formatter mới**, không thay đổi formatter gốc. Tương tự, `LocalDate.format(formatter)` chỉ tạo chuỗi biểu diễn, không mutate LocalDate.

### Khi nào tạo formatter mới?

- Khi locale thay đổi theo người dùng.
- Khi style thay đổi giữa màn hình đầy đủ và danh sách gọn.
- Khi business cần pattern khác.
- Khi muốn resolver style khác cho parsing hoặc phải gắn zone vào formatter.

Không tự đồng bộ formatter vốn đã bất biến như một đối tượng mutable; điều quan trọng là **không trộn state request** vào đối tượng chia sẻ.

## 18. FormatStyle thay đổi theo JDK locale data

Tên tháng/ngày, dấu câu, khoảng trắng, viết tắt và một số quy ước có thể đến từ dữ liệu **CLDR** hoặc locale provider được JDK dùng. Vì vậy:

- Một JDK có thể hiển thị `“Thứ Sáu”`, bản khác có thể đổi một cách viết tắt.
- Khoảng trắng giữa giờ và AM/PM có thể là Unicode đặc biệt.
- Một tháng viết tắt có thể có hoặc không có dấu chấm theo locale.
- Phần thứ tự ngày/tháng/năm và dấu câu nên được coi là **định dạng của locale provider**, không phải chuỗi chuẩn bất biến của ứng dụng.
- Những locale hiếm có thể có dữ liệu giới hạn hoặc fallback.

**Đừng tự dựng snapshot test cố định từng ký tự cho mọi JDK rồi xem mọi khác biệt là lỗi logic.** Nếu sản phẩm yêu cầu cách trình bày luôn y hệt, cần kiểm soát phiên bản dữ liệu locale hoặc dùng pattern/nguồn bản địa hóa mà sản phẩm quản lý. Đổi lại, pattern tùy chỉnh phải được kiểm ngữ pháp từng ngôn ngữ.

Các ví dụ trong bài in ra output đã chạy thực tế. Output là bằng chứng của một môi trường, không phải một chuẩn byte-for-byte bất biến.

## 19. Giao diện đa ngôn ngữ: FormatStyle hay tài nguyên dịch riêng?

FormatStyle giải quyết **ngày giờ theo quy ước địa phương**, nhưng không phải toàn bộ i18n của sản phẩm.

Ví dụ:

- “Created on {date}” là **câu thông báo**, cần hệ thống localization/resource message phù hợp.
- Giá trị `{date}` có thể được tạo bằng formatter theo Locale.
- Nút “Today”, “Tomorrow”, “Yesterday” là **nhãn tương đối**; không có yêu cầu rằng FormatStyle tự dịch chúng thành cách diễn đạt sản phẩm mong muốn.
- Màn hình lịch có tiêu đề tháng dùng `Month.getDisplayName(TextStyle.FULL_STANDALONE, locale)`, trong khi ngày đầy đủ dùng formatter context.
- Một báo cáo máy hoặc API nên có ngày theo định dạng kỹ thuật rõ, thay vì dùng ngôn ngữ của người đăng nhập để thay đổi schema.

Một hướng tổ chức:

1. Domain lưu LocalDate hoặc Instant đúng nghĩa.
2. Presentation nhận Locale của người xem.
3. Các nhãn/câu dịch dùng resource bundle/localization tool.
4. Các thành phần ngày giờ dùng DateTimeFormatter với Locale và style phù hợp.
5. API/storage dùng các kiểu hoặc chuỗi ISO theo hợp đồng, không lấy text UI làm nguồn dữ liệu.

## 20. DateTimeFormatter không tự giải quyết timezone và DST

Nếu có `LocalDateTime.of(2026,11,6,9,30)`, chọn Locale.FRANCE không khiến ngày giờ trở thành thời điểm ở Pháp. Locale chỉ ảnh hưởng **định dạng**.

Nếu cần trình bày một sự kiện thực tại một địa điểm:

```java
// Mã minh họa có Instant event.
ZoneId eventZone = ZoneId.of("Europe/Paris");
ZonedDateTime localizedMoment = event.atZone(eventZone);

String text = localizedMoment.format(
    DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.FULL)
        .withLocale(Locale.FRANCE));
```

**ZoneId** xác định giờ địa phương và quy tắc DST, còn **Locale** xác định ngôn ngữ/cách trình bày. Hai thông tin này có thể khác nhau: người dùng dùng giao diện tiếng Anh nhưng đang xem event ở Paris, hoặc dùng giao diện tiếng Việt nhưng xem lịch tại Berlin.

Đừng lấy Locale để tự đoán ZoneId: một quốc gia có thể có nhiều múi giờ, người dùng đi du lịch, và ngôn ngữ có thể được sử dụng ngoài quốc gia gốc.

## 21. Khi nào dùng ISO thay vì localized format?

| Ngữ cảnh | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Hiển thị ngày trong UI địa phương | `ofLocalizedDate(FormatStyle...)` + Locale | Dễ đọc theo quy ước người dùng |
| Hiển thị tên thứ đầy đủ | `DayOfWeek.getDisplayName` hoặc pattern EEEE | Có tên theo ngôn ngữ |
| Tiêu đề tháng của lịch | `Month.getDisplayName(FULL_STANDALONE,locale)` | Ngữ cảnh tháng đứng riêng |
| Nhập ngày có tên tháng | Formatter có Locale và resolver rõ | Parser hiểu tên tháng |
| API chỉ truyền ngày lịch | `DateTimeFormatter.ISO_LOCAL_DATE` | Chuỗi ISO ổn định, dễ xác định |
| API truyền Instant | Chuỗi ISO UTC với `Z` | Không mơ hồ timezone |
| Lưu LocalDate trong domain | Kiểu `LocalDate` | Không mất ngữ nghĩa vì String |
| Truy vấn/sort ngày | So giá trị LocalDate/Instant | Không so tên tháng hoặc format UI |
| Báo cáo tuần chính thức | `WeekFields` theo quy tắc đã chọn | Tránh phân kỳ khác nhau tùy Locale UI |

Nếu truyền ISO ngày `2026-11-06` rồi người dùng muốn UI tiếng Pháp, phía UI có thể parse thành LocalDate và format theo Locale.FRANCE. Dữ liệu máy không cần đổi mỗi khi người dùng đổi ngôn ngữ.

## 22. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Nghĩ Locale là timezone | Hiển thị giờ sai vùng | Tách `ZoneId` và `Locale` |
| Không truyền Locale | Kết quả phụ thuộc server/JVM | `withLocale(userLocale)` |
| Dùng `Locale.setDefault` cho request | State toàn tiến trình, có thể ảnh hưởng luồng khác | Truyền Locale tường minh |
| So String `dd/MM/yyyy` để sắp ngày | Thứ tự chữ không phải thứ tự lịch | Parse LocalDate rồi so |
| Dùng FormatStyle làm format API | Chuỗi khác theo locale/provider | Dùng ISO/hợp đồng rõ |
| Nghĩ FULL/MEDIUM/SHORT luôn có mẫu cố định | Dấu câu/chữ/spacing thay đổi | Coi chúng là mức độ định dạng |
| Dùng `MMMM` như tên tháng đứng riêng ở mọi ngôn ngữ | Sai biến cách ngữ pháp | Dùng `LLLL`/FULL_STANDALONE khi phù hợp |
| Dùng `LLLL` trong câu ngày mọi ngôn ngữ | Có thể sai ngữ pháp ngữ cảnh | Dùng `MMMM`/FormatStyle |
| Dùng `NARROW` làm định danh thứ | Nhiều thứ có cùng ký tự hẹp | Dùng DayOfWeek enum |
| Parse tên tháng với Locale sai | DateTimeParseException | Chọn Locale của input |
| Dùng `yyyy` vô điều kiện với STRICT | Year-of-era có thể thiếu era | Dùng `uuuu` khi thích hợp |
| Định dạng FULL time từ LocalTime thiếu zone | Có thể thiếu trường formatter cần | Chọn kiểu có zone hoặc style phù hợp |
| Test so literal output locale trên mọi JDK | Test dễ hỏng vì CLDR/spacing | Test semantic, quản lý provider khi cần |
| Nghĩ US và France có cùng ngày đầu tuần | Kỳ tuần/biên năm có thể khác | `WeekFields.of(locale)` hoặc ISO cố định |
| Không kiểm timezone ở report local | Giờ hiển thị đúng ngôn ngữ nhưng sai thời điểm | Resolve Instant với ZoneId trước khi format |
| Dùng pattern `mm` để biểu diễn tháng | `m` là phút, không phải tháng | Dùng `MM` |
| Dùng pattern `hh` nhưng quên AM/PM | Dễ mơ hồ 12h | Dùng `h:mm a` hoặc 24h `HH:mm` |
| Dựng câu ngày bằng nối tên thứ và tháng | Dấu câu/ngữ pháp sai tùy locale | Ưu tiên localized formatter cho cả ngày |
| Tưởng java.time formatter không dùng chung được | Tạo mới không cần thiết/đồng bộ thừa | DateTimeFormatter bất biến, thread-safe |

## 23. Ma trận kiểm thử định dạng địa phương

Một bộ test tốt cần bao phủ cả **ngữ nghĩa ngày** và **các định dạng locale**.

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| LocalDate cố định, en-US FULL | Có tên thứ/tháng theo locale provider |
| Cùng LocalDate, fr-FR FULL | Ngữ nghĩa ngày không thay đổi |
| Cùng LocalDate, vi-VN FULL | Hiển thị tiếng Việt có dấu phù hợp môi trường |
| FULL/MEDIUM/SHORT | Mức chi tiết thay đổi theo locale |
| Pattern `EEEE` và `EEE` | Tên thứ đầy đủ và ngắn theo locale |
| Pattern `MMMM` và `LLLL` | Ngữ cảnh so với đứng riêng |
| TextStyle.FULL/NARROW | Không dùng narrow như ID |
| Input tiếng Pháp có tên tháng | Parse với Locale.FRANCE thành cùng LocalDate |
| Input tiếng Pháp parse với Locale.US | Từ chối hoặc báo lỗi theo hợp đồng |
| Day-of-week sai với ngày | STRICT parser phát hiện mâu thuẫn |
| LocalTime 14:05 en-US | Hiển thị 12 giờ theo quy ước provider |
| LocalTime 14:05 fr-FR | Hiển thị 24 giờ theo quy ước provider |
| FULL time thiếu zone | Kiểm DateTimeException khi formatter cần zone |
| ISO_LOCAL_DATE | Chuỗi `2026-11-06` độc lập locale UI |
| WeekFields US/France | Đầu tuần, minimal days, week-based-year khác |
| Vào ngày đầu/cuối năm | Week-based-year có thể không trùng calendar year |
| Locale mặc định server khác | Logic không đổi nếu truyền Locale rõ |
| Thay đổi phiên bản JDK locale data | Không làm hỏng quy tắc nghiệp vụ vì dấu câu |
| Múi giờ khác nhưng cùng Locale | ZoneId xử lý thời điểm, Locale xử lý presentation |
| Unicode spacing trước AM/PM | Không assume mọi dấu cách là ASCII |
| Round-trip storage/API | Không dùng text localized làm dữ liệu chuẩn |

Phân loại test:

- **Unit test về kiểu và logic**: so LocalDate, parse round-trip, enum DayOfWeek/Month, WeekFields đã chọn.
- **Integration/snapshot test về presentation**: kiểm các chuỗi khi môi trường JDK/CLDR được quản lý cố định.
- **Cross-runtime test**: không coi khác dấu câu hoặc tên viết tắt giữa locale provider là bug nếu ngữ nghĩa vẫn đúng và sản phẩm không có ràng buộc chuỗi tuyệt đối.

## 24. Bài tập thực hành

**Bài 1 — cùng một ngày, ba ngôn ngữ.**  
Yêu cầu hiển thị 06/11/2026 với US, France và Việt Nam theo FULL. Có nên tạo ba đối tượng ngày khác nhau?

**Đáp án:** không. Tạo một `LocalDate.of(2026,11,6)` rồi format ba lần với formatter cùng `FormatStyle.FULL` nhưng khác Locale. Dữ liệu gốc không đổi.

**Bài 2 — tiêu đề lịch tiếng Nga.**  
Cần in tên tháng “November” đứng riêng bằng tiếng Nga. Dùng `MMMM` hay `LLLL`?

**Đáp án:** với ngữ cảnh tiêu đề tháng, cân nhắc `LLLL` hoặc `Month.NOVEMBER.getDisplayName(TextStyle.FULL_STANDALONE,ru)`. Trong câu ngày “6 tháng 11”, `MMMM` có thể cho hình thái khác.

**Bài 3 — parse “6 novembre 2026”.**  
Một API nhập văn bản tiếng Pháp; dùng formatter nào?

**Đáp án:** dùng `DateTimeFormatter.ofPattern("d MMMM uuuu",Locale.FRANCE)` với resolver policy rõ, rồi `LocalDate.parse`. Không lấy locale mặc định của server nếu input đã biết là tiếng Pháp.

**Bài 4 — muốn ngày máy đọc được.**  
Một endpoint trả chuỗi ngày cho nhiều client. Có nên trả “Thứ Sáu, 6 tháng 11, 2026” theo ngôn ngữ người đang gọi?

**Đáp án:** thường không nếu đó là dữ liệu máy. Dùng kiểu hoặc chuỗi ISO `2026-11-06` theo hợp đồng; client tự format cho presentation.

**Bài 5 — cùng giao diện tiếng Việt, hai khu vực.**  
Hai event xảy ra tại Tokyo và Berlin; UI đều dùng Locale tiếng Việt. Có đủ để hiển thị thời điểm local chính xác không?

**Đáp án:** không. Cần ZoneId của từng event để đổi Instant sang giờ địa phương, sau đó mới dùng Locale tiếng Việt để format.

**Bài 6 — AM/PM.**  
Một màn hình luôn muốn giờ 24h bất kể Locale. Có nên chỉ dùng FormatStyle.SHORT?

**Đáp án:** không chắc vì SHORT theo locale có thể dùng 12h. Dùng pattern `HH:mm` hoặc cấu hình formatter do sản phẩm kiểm soát, và test.

**Bài 7 — đầu tuần.**  
Báo cáo tuần phải tuân theo chuẩn ISO, nhưng người dùng có Locale.US. Có nên lấy `WeekFields.of(Locale.US)` để phân kỳ báo cáo không?

**Đáp án:** không nếu hợp đồng báo cáo là ISO. Dùng `WeekFields.ISO` hoặc chính sách tuần đã thống nhất; Locale giao diện không được làm đổi số liệu.

**Bài 8 — test output trước PM.**  
Unit test so `"2:05 PM"` nhưng output JDK dùng một loại no-break space. Điều gì nên thay đổi?

**Đáp án:** nếu chỉ kiểm logic formatting, tránh so chuỗi không kiểm soát provider; nếu cần output chính xác, phải chuẩn hóa/kiểm soát nguồn locale data hoặc đặt format riêng theo sản phẩm. Không kết luận rằng date/time object sai.

## 25. Câu hỏi tự kiểm tra

**1. Locale có tự thay đổi ngày của LocalDate không?**  
Không. Locale quyết định presentation và một số quy ước liên quan; LocalDate vẫn cùng giá trị.

**2. Locale.FRANCE có tự chọn Europe/Paris không?**  
Không. Locale và ZoneId là hai thông tin khác nhau.

**3. FormatStyle.FULL có là một pattern chuỗi cố định giữa mọi locale không?**  
Không. Nó mô tả mức độ; pattern thực do dữ liệu locale quyết định.

**4. Vì sao nên gọi withLocale?**  
Để đầu ra không phụ thuộc locale mặc định của server/JVM và đúng ngữ cảnh người xem.

**5. Dùng EEEE khác EEE ra sao?**  
EEEE dùng tên thứ đầy đủ, EEE dùng dạng rút gọn theo locale.

**6. Vì sao MMMM và LLLL có thể khác nhau?**  
Một bên là dạng tháng trong ngữ cảnh ngày, bên kia là dạng đứng riêng; vài ngôn ngữ có biến cách ngữ pháp.

**7. NARROW có dùng làm key định danh thứ được không?**  
Không nên, vì các nhãn hẹp có thể không duy nhất.

**8. Parse một tên tháng tiếng Pháp cần gì?**  
Locale.FRANCE hoặc Locale phù hợp với ngôn ngữ input và pattern/resolver tương ứng.

**9. Ngày trong tuần sai với ngày/tháng/năm có thể bị phát hiện không?**  
Có, khi parser dùng các trường phù hợp và resolver strict.

**10. Tại sao WeekFields phụ thuộc locale lại ảnh hưởng số liệu?**  
Vì quy tắc đầu tuần và tuần 1 khác nhau, có thể làm đổi week-based-year ở biên năm.

**11. Định dạng nào nên dùng cho API chỉ truyền ngày?**  
Thường là ISO_LOCAL_DATE, ví dụ 2026-11-06, nếu hợp đồng API dùng ISO.

**12. DateTimeFormatter có an toàn để tái sử dụng giữa các thread không?**  
Có. Nó immutable và thread-safe theo API Java 8.

## Tài liệu chính thức của Java

- [Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html): các factory localized, ofPattern, withLocale và pattern letters.
- [Java SE 8 — FormatStyle](https://docs.oracle.com/javase/8/docs/api/java/time/format/FormatStyle.html): FULL, LONG, MEDIUM, SHORT.
- [Java SE 8 — TextStyle](https://docs.oracle.com/javase/8/docs/api/java/time/format/TextStyle.html): FULL/SHORT/NARROW và biến thể STANDALONE.
- [Java SE 8 — DateTimeFormatterBuilder](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatterBuilder.html): parseCaseInsensitive, xây formatter chuyên biệt.
- [Java SE 8 — Locale](https://docs.oracle.com/javase/8/docs/api/java/util/Locale.html): Locale, language tag, FORMAT/DISPLAY default.
- [Java SE 8 — LocalDate](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDate.html), [LocalTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalTime.html), [LocalDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDateTime.html): dữ liệu ngày giờ độc lập với định dạng.
- [Java SE 8 — DayOfWeek](https://docs.oracle.com/javase/8/docs/api/java/time/DayOfWeek.html), [Month](https://docs.oracle.com/javase/8/docs/api/java/time/Month.html): lấy tên bản địa hóa.
- [Java SE 8 — WeekFields](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/WeekFields.html): các trường tuần theo quy ước locale.
- [Java SE 8 — ResolverStyle](https://docs.oracle.com/javase/8/docs/api/java/time/format/ResolverStyle.html): STRICT/SMART/LENIENT khi resolve các trường parse.

**Ghi nhớ:** hãy dùng `Locale` để quyết định **ngôn ngữ và quy ước trình bày**, `FormatStyle` để chọn **mức độ chi tiết bản địa hóa**, `TextStyle`/`MMMM`/`LLLL` để hiển thị **tên thứ và tháng đúng ngữ cảnh**, và `DateTimeFormatter` cho formatting/parsing bất biến, an toàn đa luồng. Giữ kiểu thời gian theo domain, chỉ format ở biên UI; dùng ISO rõ ràng cho giao tiếp máy; không nhầm Locale với ZoneId, không dựa vào chuỗi localized làm key/sort, và kiểm soát ảnh hưởng locale provider/JDK trong các snapshot test.