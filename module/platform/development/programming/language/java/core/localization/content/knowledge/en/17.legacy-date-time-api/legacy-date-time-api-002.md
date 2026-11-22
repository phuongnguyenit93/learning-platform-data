# SimpleDateFormat và DateFormatSymbols trong Java: định dạng ngày giờ theo Locale bằng API cũ

## Mục tiêu

Trước khi Java 8 đưa `java.time` vào thư viện chuẩn, các ứng dụng Java thường dùng `java.util.Date`, `java.util.Calendar`, `java.text.DateFormat` và `java.text.SimpleDateFormat` để định dạng hoặc phân tích ngày giờ. `java.text.DateFormatSymbols` bổ sung những tên hiển thị theo ngôn ngữ — tháng, thứ, thời kỳ sáng/chiều, kỷ nguyên và tên múi giờ — mà `SimpleDateFormat` có thể sử dụng.

Bài học giúp bạn:

- Phân biệt **`SimpleDateFormat` quyết định cách ghép/parse ngày giờ theo pattern** với **`DateFormatSymbols` cung cấp các tên và ký hiệu được bản địa hóa**.
- Tạo formatter với `Locale` tường minh, đặt `TimeZone` phù hợp và hiểu `Date` biểu diễn một thời điểm, không gắn ngôn ngữ hay múi giờ giao diện.
- Đọc những ký hiệu pattern dễ nhầm như `M`/`L`, `y`/`Y`, `H`/`h`, `a`, `E`, `z`, `Z`, `X`.
- Tùy chỉnh tên tháng bằng `DateFormatSymbols` mà không tự thay đổi dữ liệu hoặc logic lịch.
- Phân biệt **kiểm tra ngày hợp lệ** và **parse hết chuỗi**, nhận biết `setLenient(false)`, `ParsePosition` và rủi ro năm có hai chữ số.
- Tránh chia sẻ `SimpleDateFormat` mutable giữa các luồng; xác định khi nào nên chuyển sang `java.time.format.DateTimeFormatter` trên Java 17+.

Đây là bài về **API ngày giờ cũ**. Những dự án mới thường ưu tiên `java.time`, nhưng hiểu hai lớp trên vẫn quan trọng khi bảo trì ứng dụng legacy, tương tác với thư viện cũ hoặc kiểm tra chuỗi ngày giờ đang được xử lý ở các tầng hệ thống.

## 1. Vị trí của hai lớp trong mô hình API cũ

`SimpleDateFormat` kế thừa `DateFormat`; `DateFormatSymbols` là lớp chứa thông tin ký hiệu/chuỗi cần thiết cho việc bản địa hóa ngày giờ.

```text
Date / Calendar         Locale + TimeZone
       |                       |
       v                       v
    SimpleDateFormat <---- DateFormatSymbols
       |                         |
       |                         +-- tên tháng / tên thứ
       |                         +-- AM/PM / kỷ nguyên
       |                         +-- tên múi giờ / ký tự pattern cục bộ
       |
       +-- format(Date) -> String hiển thị
       +-- parse(String) -> Date
```

Phân biệt trách nhiệm:

| Thành phần | Vai trò |
| --- | --- |
| `Date` | Đại diện một thời điểm trên trục thời gian; không tự lưu `Locale` hoặc tên múi giờ hiển thị. |
| `Calendar` | Chuyển đổi và tính toán các trường lịch theo múi giờ, quy tắc lịch và locale liên quan. |
| `Locale` | Quy ước ngôn ngữ/vùng cần áp dụng khi định dạng hoặc đọc tên ngày tháng. |
| `TimeZone` | Quy tắc offset/múi giờ để chuyển một thời điểm thành ngày giờ cục bộ. |
| `SimpleDateFormat` | Pattern, định dạng và phân tích ngày giờ; có trạng thái mutable. |
| `DateFormatSymbols` | Bộ tên/chuỗi và ký hiệu được bản địa hóa phục vụ bộ định dạng kiểu cũ. |

**Không đồng nhất ngôn ngữ với múi giờ.** Một người đọc tiếng Việt có thể đang ở Paris; một người đọc tiếng Anh có thể muốn trình bày dữ liệu theo giờ UTC. `Locale` quyết định kiểu biểu diễn theo văn hóa, còn `TimeZone` quyết định quy đổi thời điểm sang giờ địa phương.

Ví dụ, `2026-10-28T15:04:05Z` là một thời điểm UTC. Khi định dạng với UTC, các trường giờ là 15:04:05; khi định dạng theo một múi giờ khác, các trường đó có thể thay đổi dù `Date` đầu vào không đổi.

## 2. SimpleDateFormat: pattern + Locale + TimeZone

Một cách tạo formatter:

```java
import java.text.SimpleDateFormat;
import java.util.Locale;
import java.util.TimeZone;

SimpleDateFormat format = new SimpleDateFormat(
        "dd MMMM yyyy HH:mm:ss", Locale.forLanguageTag("vi-VN"));
format.setTimeZone(TimeZone.getTimeZone("UTC"));
```

Đây là đoạn minh họa trong một phương thức, không phải chương trình chạy độc lập. Các thao tác có ý nghĩa riêng:

- `"dd MMMM yyyy HH:mm:ss"` là **pattern định dạng**: ngày hai chữ số, tên tháng đầy đủ, năm, giờ 24h, phút và giây.
- `Locale.forLanguageTag("vi-VN")` yêu cầu tên tháng cùng quy ước liên quan theo tiếng Việt.
- `setTimeZone(...)` chọn múi giờ dùng để diễn giải một `Date` khi format hoặc parse.

`SimpleDateFormat` có nhiều constructor, trong đó có `SimpleDateFormat(String pattern)` sử dụng default locale thích hợp, `SimpleDateFormat(String pattern, Locale locale)` và `SimpleDateFormat(String pattern, DateFormatSymbols symbols)`. Khi muốn hành vi nhất quán giữa máy phát triển/CI/production, **truyền `Locale` tường minh** thay vì dựa hoàn toàn vào default JVM.

Một điểm cần nhớ: formatter được xây dựng từ những cấu hình đó tại thời điểm tạo. Đổi `Locale.setDefault(...)` trong JVM về sau **không có nghĩa đối tượng `SimpleDateFormat` cũ tự cập nhật** toàn bộ pattern, ký hiệu và cấu hình.

### Format một Date

```java
import java.time.Instant;
import java.util.Date;

Date moment = Date.from(
        Instant.parse("2026-10-28T15:04:05Z"));

String text = format.format(moment);
```

Đây là đoạn minh họa trong một phương thức, sử dụng biến `format` đã tạo trước đó. `Date.from(Instant)` giúp chọn **thời điểm đầu vào cố định** để ví dụ không phụ thuộc đồng hồ hệ thống. `SimpleDateFormat` nhận `Date` và trả `String` đã định dạng.

Dù `Date` có tên dễ khiến người học nghĩ là “một ngày”, `java.util.Date` mang thông tin thời điểm (độ chính xác mili giây), không phải đối tượng `LocalDate` độc lập múi giờ. Việc format thành ngày/tháng/năm phụ thuộc múi giờ mà formatter đang dùng.

## 3. Đọc pattern của SimpleDateFormat

Pattern gồm các **chữ cái có ý nghĩa đặc biệt** và phần chữ văn bản cố định. Số lần lặp chữ có thể quyết định dạng số hay dạng tên.

| Chữ pattern | Ý nghĩa thông thường | Minh họa |
| --- | --- | --- |
| `y` | Năm của lịch (year) | `yyyy` → `2026` |
| `M` | Tháng, dạng số hoặc tên theo ngữ cảnh | `MM` → `10`, `MMMM` → `October` |
| `L` | Tháng dạng stand-alone, khi dữ liệu locale hỗ trợ phân biệt | `LLLL` → tên tháng ở ngữ cảnh độc lập |
| `d` | Ngày trong tháng | `dd` → `28` |
| `E` | Tên thứ | `EEEE` → `Wednesday` |
| `u` | Số ngày trong tuần, thứ Hai là 1 | `u` cho thứ Tư → `3` |
| `H` | Giờ trong ngày, 0–23 | `HH` → `15` |
| `h` | Giờ theo chu kỳ 1–12 | `hh` → `03`, cần ngữ cảnh AM/PM |
| `a` | Ký hiệu AM/PM | `a` → `PM` ở en-US |
| `m` | Phút | `mm` → `04` |
| `s` | Giây | `ss` → `05` |
| `S` | Mili giây | `SSS` → `123` |
| `z` | Múi giờ theo tên/biểu diễn chung | `z` → tên hoặc dạng offset |
| `Z` | Offset theo dạng RFC 822 | `Z` → `+0700` |
| `X` | Offset theo dạng ISO 8601, tùy số chữ X | `XXX` → `+07:00`, UTC có thể là `Z` |
| `Y` | Week-based year (năm theo tuần) | Có thể khác `y` quanh năm mới |

Ví dụ trong `Locale.US` và UTC, `"EEEE, dd MMMM yyyy HH:mm:ss XXX"` có thể tạo:

```text
Wednesday, 28 October 2026 15:04:05 Z
```

### Những cặp dễ nhầm

**`M` so với `m`:** `M` viết hoa là tháng; `m` viết thường là phút. `"MM:mm"` không phải “tháng:tháng”, mà là “tháng:phút”.

**`H` so với `h`:** `H` dành cho giờ 24h; `h` cho giờ 12h. Nếu dùng `hh` mà không có `a`, chuỗi có thể mơ hồ giữa sáng/chiều.

**`y` so với `Y`:** `Y` là **năm theo tuần**, liên quan tuần đầu/cuối của năm và quy tắc tuần của `Calendar`/locale. Gần giao thừa, `YYYY` có thể tạo con số khác năm dương lịch `yyyy`. Đối với ngày đơn thông thường, thường muốn `yyyy-MM-dd` chứ không phải `YYYY-MM-dd`.

**`M` so với `L`:** trong một số ngôn ngữ, tên tháng ở câu chứa ngày khác dạng tên tháng đứng một mình. `M` mô tả dạng theo ngữ cảnh định dạng; `L` mô tả dạng stand-alone. Không phải locale/provider nào cũng thể hiện sự khác biệt và không nên tự suy rằng mọi `DateFormatSymbols` tùy biến sẽ thay đúng mọi dạng `L`.

**`u` ở SimpleDateFormat khác `u` ở java.time:** trong `SimpleDateFormat`, `u` là ngày trong tuần theo thứ tự từ thứ Hai. Trong `DateTimeFormatter` hiện đại, `u` biểu thị năm proleptic. **Không sao chép pattern giữa hai API mà không rà lại ý nghĩa từng ký hiệu**.

### Dấu nháy và ký tự văn bản

Để chèn văn bản cố định có chữ cái vốn là pattern, bao quanh bằng dấu nháy đơn:

```java
new SimpleDateFormat("yyyy-MM-dd 'at' HH:mm", Locale.US);
```

Nếu muốn một dấu nháy đơn literal trong pattern, dùng `''`. Một pattern sai dấu nháy hoặc chứa chữ pattern không hợp lệ có thể dẫn đến `IllegalArgumentException` hay kết quả không mong muốn.

Đừng xem pattern là văn bản tùy ý: các chữ cái ASCII thuộc bảng pattern có ngữ nghĩa riêng. Đặc biệt, pattern định dạng ngày của API cũ không tự tương thích hoàn toàn với cú pháp ICU, JavaScript hoặc `java.time`.

## 4. DateFormatSymbols là gì?

`DateFormatSymbols` lưu những mảng/tập chuỗi bản địa hóa mà formatter có thể sử dụng để diễn đạt **các trường lịch bằng chữ**.

Một số API quan trọng:

| API | Thông tin |
| --- | --- |
| `DateFormatSymbols.getInstance(locale)` | Lấy bộ ký hiệu theo locale được yêu cầu |
| `getMonths()` / `setMonths(...)` | Tên tháng đầy đủ |
| `getShortMonths()` / `setShortMonths(...)` | Tên tháng viết tắt |
| `getWeekdays()` / `setWeekdays(...)` | Tên thứ đầy đủ |
| `getShortWeekdays()` / `setShortWeekdays(...)` | Tên thứ viết tắt |
| `getAmPmStrings()` / `setAmPmStrings(...)` | Các chuỗi cho AM/PM |
| `getEras()` / `setEras(...)` | Tên kỷ nguyên dùng trong lịch liên quan |
| `getZoneStrings()` / `setZoneStrings(...)` | Bảng chuỗi tên múi giờ phục vụ hiển thị |
| `getLocalPatternChars()` / `setLocalPatternChars(...)` | Tập ký tự pattern được bản địa hóa cho `applyLocalizedPattern` |
| `clone()` | Tạo bản sao khi cần tách trạng thái |

Ví dụ:

```java
import java.text.DateFormatSymbols;
import java.util.Calendar;
import java.util.Locale;

DateFormatSymbols us = DateFormatSymbols.getInstance(Locale.US);
String october = us.getMonths()[Calendar.OCTOBER];
String wednesday = us.getWeekdays()[Calendar.WEDNESDAY];
```

Đây là đoạn minh họa trong một phương thức. Với locale en-US thông thường, `october` là `October`, `wednesday` là `Wednesday`.

### Chỉ số của mảng không giống nhau

Đây là lỗi cực dễ mắc:

- Các hằng `Calendar.JANUARY` đến `Calendar.DECEMBER` nhận giá trị từ **0 đến 11**. Vì thế `months[Calendar.OCTOBER]` trỏ đến tháng Mười.
- `Calendar.SUNDAY` đến `Calendar.SATURDAY` dùng giá trị từ **1 đến 7**. Mảng `getWeekdays()` thường dành phần tử index 0 không sử dụng, và vị trí thực tương ứng với các hằng `Calendar`.

Không viết `weekdays[0]` rồi nghĩ đó là Chủ nhật. Không lấy `months[10]` rồi nghĩ index 10 là tháng Mười; theo hằng `Calendar`, tháng Mười là index 9.

Mảng tháng của API cũ có thể có phần tử thứ 13 dành cho lịch hỗ trợ tháng bổ sung. Đừng giả định mọi locale đều đúng 12 tên hoặc mọi giá trị ngoài 12 đều nên tự gán vào dữ liệu khác. Khi cần một tháng chuẩn của Gregorian, dùng hằng `Calendar` thích hợp.

### Không dùng DateFormatSymbols làm kho dữ liệu múi giờ

`getZoneStrings()` chủ yếu là bảng **tên hiển thị**, không phải nguồn tính offset, quy tắc daylight saving time hoặc danh sách múi giờ chuẩn để định tuyến dữ liệu. Các quy tắc thuộc `TimeZone` trong API cũ hoặc `ZoneId`/`ZoneRules` trong `java.time`.

Tương tự, `DateFormatSymbols` không thay thế `ResourceBundle` của ứng dụng để quản lý thông điệp dịch. Nó là tập ký hiệu lịch do formatter dùng; tiêu đề màn hình, thông báo lỗi và nhãn nút vẫn cần bộ tài nguyên riêng.

## 5. SimpleDateFormat sử dụng DateFormatSymbols như thế nào?

Khi bạn tạo:

```java
SimpleDateFormat formatter = new SimpleDateFormat(
        "EEEE, dd MMMM yyyy", Locale.US);
```

`SimpleDateFormat` có bộ ký hiệu phù hợp với locale để biến `EEEE` thành tên thứ và `MMMM` thành tên tháng. Không cần tự tra tên trong mảng rồi nối văn bản bằng chuỗi.

`DateFormatSymbols` cho phép **ghi đè bộ tên và ký hiệu** khi có yêu cầu cụ thể, ví dụ một báo cáo chuyên biệt muốn gọi tháng Mười là “Harvest” thay vì “October”. Đây là nhu cầu tùy biến có chủ đích, không phải cách dịch tên tháng thường dùng cho toàn ứng dụng.

### Tùy chỉnh tên tháng

```java
import java.text.DateFormatSymbols;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

DateFormatSymbols symbols = DateFormatSymbols.getInstance(Locale.US);
String[] months = symbols.getMonths();

months[Calendar.OCTOBER] = "Harvest";
symbols.setMonths(months);

SimpleDateFormat custom = new SimpleDateFormat(
        "dd MMMM yyyy", symbols);
```

Đây là đoạn minh họa trong một phương thức; để format một thời điểm chính xác cần đặt `TimeZone` và truyền `Date` phù hợp.

Điểm quan trọng:

1. Lấy mảng tháng từ bộ ký hiệu dự định dùng.
2. Sửa index theo `Calendar.OCTOBER`, không đoán bằng số thứ tự tháng hiển thị.
3. Gọi `setMonths(...)` để cung cấp mảng đã sửa cho `DateFormatSymbols`.
4. Truyền symbols vào constructor `SimpleDateFormat(String, DateFormatSymbols)`, hoặc dùng `formatter.setDateFormatSymbols(symbols)` trên formatter đã có.
5. Sau đó formatter được cấu hình với tên tháng tùy chỉnh khi xử lý dạng tháng phù hợp với bộ ký hiệu.

Tùy biến này có thể ảnh hưởng **cả format lẫn parse tên tháng**. Vì thế, nếu chỉ muốn đổi văn bản trong một báo cáo, hãy cô lập formatter đó; đừng thay đổi một cấu hình dùng chung với parser đầu vào mà không đánh giá hậu quả.

Các phương thức getter/setter của `DateFormatSymbols` xử lý các mảng theo hợp đồng lớp. Dù có các cơ chế sao chép bảo vệ, cách dễ hiểu là tạo một bộ symbols riêng cho mỗi cấu hình chuyên dụng, sửa mảng rồi gọi setter, tránh dùng một biến symbols mutable như tài nguyên toàn cục có thể bị đổi tùy ý.

### Khác nhau giữa thay pattern và thay symbols

- **Thay pattern:** quyết định **trường nào, theo thứ tự nào, và có hiện tên tháng hay không**. Ví dụ `"dd/MM/yyyy"` → `"EEEE, dd MMMM yyyy"`.
- **Thay symbols:** quyết định **chuỗi tên tháng/thứ/AM-PM nào** được dùng cho các trường chữ tương ứng.
- **Thay locale:** chọn bộ quy ước bản địa hóa, thường gồm tên và một số quy tắc lịch/hiển thị.
- **Thay múi giờ:** quyết định ngày/giờ cục bộ và offset tương ứng khi format/parse.

Không gọi `DateFormatSymbols.setMonths` rồi kỳ vọng chuỗi `"dd/MM/yyyy"` bỗng hiển thị tên tháng: pattern `MM` vẫn yêu cầu tháng dạng số. Muốn tên đầy đủ, dùng `MMMM` trong pattern.

## 6. Ví dụ Java 17+ đầy đủ: formatter, symbols và parse

Ví dụ sau được thiết kế để chạy độc lập trên JDK 17 trở lên, không phụ thuộc đồng hồ hiện tại hoặc múi giờ mặc định.

Tạo file `LegacyDateFormattingDemo.java`:

```java
import java.text.DateFormatSymbols;
import java.text.ParseException;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDateFormattingDemo {
    public static void main(String[] args) {
        Date moment = Date.from(
                Instant.parse("2026-10-28T15:04:05Z"));
        TimeZone utc = TimeZone.getTimeZone("UTC");

        SimpleDateFormat standard = new SimpleDateFormat(
                "EEEE, dd MMMM yyyy HH:mm:ss XXX", Locale.US);
        standard.setTimeZone(utc);

        System.out.println(standard.format(moment));

        DateFormatSymbols symbols =
                DateFormatSymbols.getInstance(Locale.US);
        System.out.println(
                symbols.getMonths()[Calendar.OCTOBER]);
        System.out.println(
                symbols.getWeekdays()[Calendar.WEDNESDAY]);

        String[] months = symbols.getMonths();
        months[Calendar.OCTOBER] = "Harvest";
        symbols.setMonths(months);

        SimpleDateFormat custom = new SimpleDateFormat(
                "dd MMMM yyyy", symbols);
        custom.setTimeZone(utc);

        System.out.println(custom.format(moment));
        System.out.println(standard.format(moment));

        SimpleDateFormat parser = new SimpleDateFormat(
                "yyyy-MM-dd", Locale.US);
        parser.setLenient(false);
        parser.setTimeZone(utc);

        try {
            parser.parse("2026-02-30");
            System.out.println("Invalid date accepted");
        } catch (ParseException ex) {
            System.out.println("Invalid date rejected");
        }

        String input = "2026-10-28tail";
        ParsePosition position = new ParsePosition(0);
        Date parsed = parser.parse(input, position);

        System.out.println("Parsed prefix: "
                + (parsed != null)
                + ", index=" + position.getIndex()
                + "/" + input.length());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LegacyDateFormattingDemo.java
java LegacyDateFormattingDemo
```

Stdout:

```text
Wednesday, 28 October 2026 15:04:05 Z
October
Wednesday
28 Harvest 2026
Wednesday, 28 October 2026 15:04:05 Z
Invalid date rejected
Parsed prefix: true, index=10/14
```

### Giải thích từng kết quả

1. Pattern `EEEE, dd MMMM yyyy HH:mm:ss XXX` hiển thị tên thứ/tên tháng tiếng Anh, giờ 24h và offset UTC ký hiệu `Z` cho `XXX`.
2. `symbols.getMonths()[Calendar.OCTOBER]` trả `October`.
3. `symbols.getWeekdays()[Calendar.WEDNESDAY]` trả `Wednesday`.
4. Sau khi sửa bộ ký hiệu riêng, formatter `custom` dùng tên `Harvest` cho tháng Mười và tạo `28 Harvest 2026`.
5. Formatter `standard` đã tạo riêng trước đó vẫn hiển thị `October`. Việc sửa `symbols` dành cho formatter mới không làm thay đổi trạng thái của formatter này.
6. `setLenient(false)` khiến parser từ chối ngày `2026-02-30` không tồn tại trong lịch Gregorian được dùng ở ví dụ.
7. Tuy vậy `parse(input, position)` vẫn đọc được tiền tố `2026-10-28` rồi dừng trước `tail`. Index 10 trên chuỗi 14 ký tự nghĩa là **chưa tiêu thụ hết đầu vào**, dù ngày trong tiền tố hợp lệ.

Đây chính là hai nhóm vấn đề tách biệt: **ngôn ngữ hiển thị** được quyết định qua symbols và pattern; **kiểm tra đầu vào** đòi xét cả leniency lẫn số ký tự đã đọc.

## 7. Parse: từ chuỗi thành Date có những bẫy gì?

`SimpleDateFormat.parse(String)` trả `Date`; `parse(String, ParsePosition)` cho phép theo dõi vị trí đã đọc. Cần hiểu ít nhất ba vấn đề:

### 7.1. Mặc định lenient có thể sửa ngày “sai” thành ngày khác

`DateFormat`/`Calendar` thường cho phép diễn giải linh hoạt khi parsing nếu chưa tắt chế độ lenient. Ví dụ ngày “30 tháng 2” không tồn tại có thể bị chuẩn hóa sang ngày của tháng 3 nếu parser đang lenient.

```java
SimpleDateFormat parser = new SimpleDateFormat(
        "yyyy-MM-dd", Locale.US);
parser.setLenient(false);
```

Đoạn minh họa trong một phương thức. `setLenient(false)` yêu cầu kiểm tra ngày tháng nghiêm ngặt hơn theo lịch mà formatter sử dụng. Một chuỗi `"2026-02-30"` sẽ bị từ chối trong lịch Gregorian thông thường, thay vì silently đổi thành ngày mới.

Tuy vậy, **`setLenient(false)` không có nghĩa parse sẽ đọc hết chuỗi**. Ví dụ `"2026-10-28tail"` vẫn có thể được parse thành một `Date` từ phần đầu hợp lệ.

### 7.2. Parser có thể chỉ đọc một tiền tố

Đây là logic kiểm tra toàn phần:

```java
String input = "2026-10-28tail";

ParsePosition pos = new ParsePosition(0);
Date parsed = parser.parse(input, pos);

boolean complete = parsed != null
        && pos.getIndex() == input.length();
```

Đoạn này giả định biến `parser` đã tạo ở trên, đã import `ParsePosition` và `Date`. `complete` là `false` vì parser dừng trước chữ `tail`.

Khi `parse(String)` không nhận được đầu vào ngay từ đầu, nó có thể ném `ParseException`; khi parser trả kết quả cho phần đầu mà còn suffix, overload đó vẫn có thể **không ném lỗi**. Vì vậy không thể chỉ dựa vào “không exception”.

`ParsePosition.getErrorIndex()` giúp chẩn đoán khi parse thất bại. Nó không thay cho kiểm tra `getIndex()` nếu yêu cầu không còn ký tự thừa.

### 7.3. Năm có hai chữ số phụ thuộc cửa sổ diễn giải

Với pattern `"yy"`, `SimpleDateFormat` dùng một **cửa sổ 100 năm** để giải thích năm hai chữ số. Mặc định của cửa sổ này phụ thuộc thời điểm tạo formatter (thường bắt đầu khoảng 80 năm trước và kết thúc khoảng 20 năm sau), nên cùng chuỗi `"30"` có thể được hiểu khác khi chương trình chạy ở thời điểm khác.

Nếu bắt buộc xử lý năm hai chữ số legacy, có thể kiểm soát bằng `set2DigitYearStart(Date startDate)`, đồng thời ghi rõ hợp đồng nhập. Nhưng với input mới, **ưu tiên năm bốn chữ số** và yêu cầu người dùng nhập đầy đủ, thay vì dựa vào cửa sổ năm ngầm.

### 7.4. Tên tháng và thứ là dữ liệu ngôn ngữ

Parser dùng `"dd MMMM yyyy"` cần nhận tên tháng phù hợp với locale và symbols của formatter. Chuỗi tên tháng tiếng Anh không mặc nhiên parse đúng với một formatter được tạo bằng locale tiếng Việt, và ngược lại.

Nếu người dùng nhập số ngày dưới dạng `yyyy-MM-dd` theo một hợp đồng máy đọc cố định, không cần tạo parser dựa vào tên tháng đã dịch. Đối với dữ liệu nhập từ hệ thống khác, nên dùng API parse ISO hoặc schema riêng thay vì tùy tiện dùng locale mặc định JVM.

## 8. DateFormatSymbols: tùy chỉnh được nhưng không thay thế định dạng nghiệp vụ

Một số ứng dụng legacy từng tùy biến `DateFormatSymbols` để đổi tên thứ, tên tháng hoặc chuỗi AM/PM. Kỹ thuật này vẫn có ích trong tình huống hẹp, nhưng nên phân biệt:

- **Tên theo ngôn ngữ thông thường:** thường chỉ cần `new SimpleDateFormat(pattern, locale)`. JDK/provider đã có dữ liệu tên tháng/thứ cho nhiều locale.
- **Tên chuyên ngành hoặc yêu cầu riêng:** có thể tùy biến symbols trong formatter của đúng màn hình/báo cáo.
- **Chính sách lịch hoặc cách tính ngày:** không thể giải quyết chỉ bằng đổi text của symbols.
- **Múi giờ và chuyển DST:** không thể điều khiển chính xác bằng cách đổi tên trong `getZoneStrings`.
- **Dịch thông báo ứng dụng:** dùng `ResourceBundle`/hệ thống i18n thay vì nhét mọi chuỗi vào `DateFormatSymbols`.

Tùy biến tên tháng có thể có tác dụng ngược khi input được parse: một tháng được đổi tên có thể yêu cầu parser nhận tên mới, còn tên chuẩn có thể không được nhận như trước. Cần kiểm thử cả hai chiều nếu formatter dùng cho nhập liệu.

### Tên múi giờ có thể thay đổi theo provider

Pattern `z` có thể hiển thị tên múi giờ hoặc dạng offset phụ thuộc zone/locale/dữ liệu JDK. Tên có thể thay đổi theo bản cập nhật dữ liệu ngôn ngữ hoặc múi giờ. Nếu cần output máy đọc ổn định, đừng dùng tên `z` làm giao thức.

Pattern `X` hoặc `XXX` tạo offset theo cú pháp ISO 8601 nhưng offset đơn lẻ **không chứa đầy đủ ZoneId hoặc quy tắc lịch sử DST**. Ví dụ `+07:00` không thay thế định danh khu vực như `Asia/Ho_Chi_Minh` khi hệ thống cần xử lý lịch sử/quy tắc vùng.

Khi trao đổi thời điểm giữa dịch vụ, ưu tiên định dạng ISO-8601 có offset/UTC thích hợp theo schema, hoặc dùng kiểu thời gian mà thư viện serialization hỗ trợ, không dùng một `SimpleDateFormat` UI có tên tháng được dịch.

## 9. Rủi ro thread safety: SimpleDateFormat mutable

**`SimpleDateFormat` không bảo đảm an toàn khi nhiều luồng cùng format/parse trên một instance mà không đồng bộ.** Formatter lưu trạng thái như calendar, number format và timezone, có thể thay đổi trong lúc xử lý. Chia sẻ một formatter ở biến `static` rồi dùng đồng thời cho mọi request có thể gây dữ liệu sai, exception bất thường hoặc lỗi khó tái hiện.

Anti-pattern:

```java
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("yyyy-MM-dd", Locale.US);
```

Đây chỉ là khai báo minh họa trong một lớp. `final` chỉ ngăn thay tham chiếu, **không làm bản thân `SimpleDateFormat` bất biến hoặc thread-safe**.

Các hướng xử lý:

1. **Tạo instance riêng cho mỗi tác vụ:** đơn giản và rõ ràng khi lưu lượng không quá lớn.
2. **Dùng đồng bộ hóa thích hợp** nếu bắt buộc dùng một formatter chung, nhưng phải kiểm soát cả lời gọi đổi cấu hình.
3. **Dùng `ThreadLocal` có kỷ luật** trong hệ thống legacy nếu cần, đánh giá vòng đời thread pool và nguy cơ rò rỉ/giữ trạng thái.
4. **Ưu tiên `DateTimeFormatter`** của `java.time` khi có thể chuyển đổi; formatter này bất biến và được thiết kế an toàn cho sử dụng đồng thời.

Không nên gắn một `DateFormatSymbols` mutable dùng chung cho nhiều formatter rồi đổi nó trong khi nhiều request đang chạy. Hãy xây formatter cục bộ/độc lập và coi dữ liệu cấu hình đã xuất bản là cố định.

### Cẩn thận với việc thay config sau khi dùng

`SimpleDateFormat` có setter như `applyPattern(...)`, `setTimeZone(...)`, `setLenient(...)` và `setDateFormatSymbols(...)`. Một formatter có thể bị thay đổi từ nơi khác mà người gọi không hay biết. Nếu một đối tượng cần trình bày theo nhiều locale/múi giờ, cách chắc chắn là tạo formatter theo request, không sửa một instance global theo từng người dùng.

## 10. Những khác biệt cần nhớ khi chuyển sang java.time

Từ Java 8, các loại trong `java.time` tách rõ vai trò:

| API cũ | Hướng thay thế thường gặp |
| --- | --- |
| `Date` đại diện thời điểm | `Instant` cho điểm thời gian UTC |
| `Calendar` + timezone | `ZonedDateTime` hoặc `OffsetDateTime` tùy ý nghĩa |
| Ngày không gắn giờ | `LocalDate` |
| `TimeZone` | `ZoneId`, `ZoneOffset` |
| `SimpleDateFormat` | `DateTimeFormatter` |
| Tên tháng/thứ tùy biến qua symbols | Formatter theo `Locale` hoặc `DateTimeFormatterBuilder` với map text nếu có nhu cầu đặc biệt |

Ví dụ hiện đại:

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("EEEE, dd MMMM uuuu HH:mm:ss XXX", Locale.US)
        .withZone(ZoneOffset.UTC);

String text = formatter.format(
        Instant.parse("2026-10-28T15:04:05Z"));
```

Đây là đoạn minh họa trong một phương thức. Kết quả theo locale en-US và UTC là:

```text
Wednesday, 28 October 2026 15:04:05 Z
```

Điểm quan trọng:

- Với `DateTimeFormatter`, ký hiệu năm proleptic là `u`/`uuuu`. Không sao chép nguyên `SimpleDateFormat` pattern theo thói quen nếu nó dùng các ký hiệu có ngữ nghĩa khác.
- `DateTimeFormatter` là **immutable** và thread-safe; có thể lưu một instance phù hợp làm cấu hình dùng lại.
- `java.time` tách rõ thời điểm, ngày riêng, ngày giờ cục bộ và vùng giờ. Chọn đúng kiểu giúp tránh lỗi suy múi giờ từ locale.
- Các tùy chọn parse nghiêm ngặt và resolver style của `DateTimeFormatter` có hợp đồng khác `SimpleDateFormat#setLenient(false)`; migration cần test input/output thật, không chỉ thay tên class.

Nếu code cũ đưa vào/ra `Date`, có thể chuyển đổi `Date#toInstant()` và `Date.from(Instant)` ở ranh giới tích hợp. Không nhất thiết thay toàn bộ codebase một lần; có thể chuyển dần formatter UI và parser đầu vào trước.

## 11. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `new SimpleDateFormat(pattern)` ở mọi nơi | Đầu ra phụ thuộc default locale của JVM | Truyền locale rõ ràng |
| Không đặt `TimeZone` cho dữ liệu cần quy đổi nhất quán | Cùng Date có thể hiển thị giờ khác giữa máy | Chọn zone theo nghiệp vụ/người dùng |
| Nghĩ `Date` tự mang locale và zone | Nhầm vai trò của instant và trình bày | Tách `Date/Instant`, `Locale` và `TimeZone` |
| Dùng `MM` thay cho tên tháng | `MM` ra số tháng, không ra tên | Dùng `MMMM` hoặc `MMM` |
| Dùng `mm` thay cho tháng | `mm` là phút | Dùng `MM` hoặc `MMMM` |
| Dùng `YYYY` cho ngày lịch thông thường | Week-based year có thể lệch quanh giao thừa | Thường dùng `yyyy` trong SimpleDateFormat |
| Dùng `hh` không có `a` | Mơ hồ giờ sáng/chiều | Dùng `HH` hoặc `hh a` |
| Nghĩ `DateFormatSymbols` quyết định múi giờ | Tên hiển thị khác quy tắc offset/DST | Dùng `TimeZone`/`ZoneId` đúng vai trò |
| Dùng index 0 cho Chủ nhật | Mảng thứ theo `Calendar.SUNDAY=1` | Dùng hằng `Calendar` |
| Đổi tên tháng bằng symbols nhưng pattern vẫn là `MM` | Không thấy tên tùy chỉnh | Dùng `MMMM` |
| Bỏ `setLenient(false)` khi parse đầu vào ngày nghiêm ngặt | Ngày sai có thể bị chuẩn hóa | Tắt lenient và kiểm tra phần dư |
| Chỉ dùng `parse(String)` làm validation | Có thể parse tiền tố rồi bỏ hậu tố | Dùng `ParsePosition` kiểm tra hết input |
| Dùng `yy` mà không kiểm soát cửa sổ năm | Kết quả phụ thuộc thời điểm tạo formatter | Dùng năm đầy đủ, hoặc `set2DigitYearStart` |
| Dùng chung một `SimpleDateFormat` trong nhiều thread | Lỗi race vì formatter mutable | Instance riêng hoặc chuyển sang `DateTimeFormatter` |
| Sao chép pattern từ SimpleDateFormat sang DateTimeFormatter nguyên xi | Một số chữ pattern, ví dụ `u`, khác nghĩa | Rà bảng pattern của từng API |
| Dùng tên timezone theo `z` để trao đổi API | Văn bản thay theo locale/provider và không đủ ZoneId | Dùng schema ISO-8601/zone ID rõ nghĩa |

## 12. Bài tập tự kiểm tra

**Bài 1 — Pattern.** Với `"dd/MM/yyyy HH:mm"`, giải thích từng chữ pattern. Nếu muốn tên tháng đầy đủ bằng tiếng Anh và tên thứ, hãy viết pattern phù hợp. Vì sao `MM` không hiển thị `October`?

**Bài 2 — Mảng symbols.** Gọi `DateFormatSymbols.getInstance(Locale.US)`. Nêu index để lấy tháng Mười và thứ Tư bằng hằng `Calendar`. Tại sao không thể dùng index 0 làm Chủ nhật?

**Bài 3 — Tùy biến.** Đổi tên tháng Mười thành `Harvest` bằng `getMonths`/`setMonths` rồi tạo `SimpleDateFormat("dd MMMM yyyy", symbols)`. Nếu pattern đổi thành `"dd/MM/yyyy"`, có còn thấy chữ `Harvest` không? Vì sao?

**Bài 4 — Locale so với TimeZone.** Một `Date` cho thời điểm `2026-10-28T15:04:05Z`. Nếu giữ `Locale.US` nhưng đổi `TimeZone` từ UTC sang một vùng khác, phần nào của output có thể thay đổi? Nếu giữ UTC nhưng đổi locale, phần nào thay đổi?

**Bài 5 — Parse.** `SimpleDateFormat("yyyy-MM-dd")` có `setLenient(false)`. Nó nên xử lý `2026-02-30` ra sao? Nếu input là `2026-10-28tail`, vì sao chỉ tắt lenient vẫn chưa đủ để xác thực toàn chuỗi? Hãy dùng `ParsePosition`.

**Bài 6 — Year.** Giải thích vì sao `YYYY-MM-dd` có thể nguy hiểm ở cuối năm. Phân biệt `y` và `Y` trong `SimpleDateFormat`, rồi so sánh ý nghĩa `u` ở `SimpleDateFormat` và `DateTimeFormatter`.

**Bài 7 — Concurrency.** Một backend đặt `static final SimpleDateFormat` dùng cho mọi request. Tại sao `final` không đảm bảo thread safety? Đề xuất hai cách xử lý với code legacy và một phương án dùng `DateTimeFormatter`.

**Bài 8 — Migration.** Chuyển đoạn định dạng `Date` theo UTC/Locale.US sang `DateTimeFormatter`. Hãy chọn `Instant`, `ZoneOffset.UTC` và pattern có `uuuu`. Trường hợp nào vẫn cần `Date.from(Instant)` để tương tác với thư viện cũ?

## 13. Ghi nhớ

**`SimpleDateFormat` là bộ định dạng/parser mutable dựa trên pattern, `Locale` và `TimeZone`; `DateFormatSymbols` là nguồn tên tháng/thứ/AM-PM và các chuỗi lịch được bản địa hóa có thể tùy chỉnh.** Hai lớp phối hợp để biến dữ liệu thời gian thành văn bản mà con người đọc được, nhưng không phải nguồn sự thật cho quy tắc múi giờ hay dữ liệu thông điệp của ứng dụng.

Khi duy trì ứng dụng cũ:

1. Chọn `Locale` và `TimeZone` tường minh.
2. Kiểm tra kỹ ký hiệu pattern, nhất là `M`/`m`, `y`/`Y`, `H`/`h` và cách quote.
3. Khi parse, kết hợp `setLenient(false)` với `ParsePosition` nếu cần từ chối chuỗi có phần dư.
4. Không chia sẻ `SimpleDateFormat` mutable giữa các luồng mà không đồng bộ.
5. Với thiết kế mới, ưu tiên `java.time` và `DateTimeFormatter`, đồng thời kiểm tra sự khác biệt pattern khi di chuyển mã.

### Tài liệu API tham khảo

- [`SimpleDateFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html)
- [`DateFormatSymbols` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormatSymbols.html)
- [`DateFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DateFormat.html)
- [`DateTimeFormatter` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
