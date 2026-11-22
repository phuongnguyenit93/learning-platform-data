# Kiểm thử biên tuần, quy ước tiền tệ và múi giờ với `Locale` trong ứng dụng Java

## 1. Mục tiêu và phạm vi

Trong ứng dụng đa ngôn ngữ, `Locale` ảnh hưởng đến cách hiển thị lịch, tuần, số và tiền tệ. Nhưng **`Locale` không phải múi giờ**, không tự bảo đảm một thuật toán tính tuần duy nhất và không thể thay thế những quy tắc nghiệp vụ về tiền bạc hoặc thời điểm.

Những sai sót thường chỉ xuất hiện ở **ranh giới**: ngày đầu/cuối năm thuộc số tuần nào, đơn vị tiền tệ nào được chọn khi vùng người dùng khác vùng kinh doanh, hoặc giờ địa phương nào bị **bỏ qua/lặp lại** khi chuyển giờ mùa hè (DST).

Java 10 mở rộng hỗ trợ các Unicode Locale Extensions **`cu`** (currency), **`fw`** (first day of week), **`rg`** (region override) và **`tz`** (time zone) trong các API liên quan. Java 10 cũng bổ sung `DateTimeFormatter.localizedBy(Locale)`. Đây là các API **vẫn dùng được trong Java hiện đại**. Các khóa `ca` (calendar) và `nu` (numbering system) đã tồn tại trước Java 10 và có thể xuất hiện cùng các khóa trên.

Sau bài này, bạn có thể:

- Thiết kế bộ test tại đầu/cuối tuần và ranh giới **week-based year**.
- Phân biệt `WeekFields.ISO`, `WeekFields.of(locale)`, `WeekFields.SUNDAY_START`, cùng quy tắc ngày đầu tuần và số ngày tối thiểu của tuần đầu năm.
- Xác thực `fw`, `rg`, `cu` và thứ tự ưu tiên của các Unicode locale keyword.
- Kiểm tra chọn `Currency` và định dạng tiền tệ mà không phụ thuộc chuỗi ký hiệu `$`, `€` hoặc dấu phân cách thay đổi theo CLDR.
- Kiểm thử múi giờ bằng `ZoneId`, `Instant`, `LocalDateTime`, `ZoneRules`; phát hiện **gap** và **overlap** của DST.
- Hiểu `tz` trong BCP 47 và sự khác nhau giữa `DateTimeFormatter.localizedBy(locale)` với `withLocale(locale)`.
- Chạy các kiểm thử Java 17+ có đầu ra xác định và biết điều gì phải thử trên môi trường triển khai thật.

> Nguyên tắc xuyên suốt: **tách dữ liệu lõi khỏi cách trình bày**, chỉ định locale/zone/currency đúng hợp đồng, kiểm thử bằng ngày và thời điểm cố định, không dùng ngày hôm nay hoặc môi trường mặc định làm fixture.

## 2. Ba loại ranh giới cần kiểm thử

| Nhóm | Dữ liệu lõi | Phụ thuộc vào | Cạm bẫy |
| --- | --- | --- | --- |
| Tuần | `LocalDate` | Ngày đầu tuần, số ngày tối thiểu trong tuần đầu tiên, quy tắc năm-tuần | 01/01 có thể thuộc **năm-tuần trước** |
| Tiền tệ | `BigDecimal`, mã `Currency` | Mã ISO 4217, vùng/khóa `cu`, quy tắc hiển thị, cách làm tròn | Ngôn ngữ `en` không đồng nghĩa tiền USD; ký hiệu có thể giống nhau |
| Múi giờ | `Instant`, `ZoneId` hoặc local date-time với chính sách chuyển đổi | IANA time-zone rules, DST và phiên bản tzdb, khóa `tz` khi formatter hỗ trợ | Một giờ địa phương có thể **không tồn tại** hoặc **tồn tại hai lần** |

Một `Locale` có thể mô tả cùng lúc nhiều sở thích, ví dụ:

~~~text
en-US-u-cu-eur-fw-mon-tz-usnyc
~~~

Ở đây:

- `en-US`: ngôn ngữ Anh, vùng Hoa Kỳ.
- `cu-eur`: ưu tiên đồng Euro ở dịch vụ tiền tệ có hỗ trợ.
- `fw-mon`: tuần bắt đầu thứ Hai ở dịch vụ lịch/tuần có hỗ trợ.
- `tz-usnyc`: Unicode time-zone type cho New York ở dịch vụ có hỗ trợ `tz`.

**Lưu ý:** một thẻ Locale chỉ mang **sở thích**. Không có bảo đảm mọi API đều dùng tất cả extension; phải kiểm tra **hợp đồng của API thực sự gọi**.

## 3. Kiểm thử ngày đầu tuần: `fw`, `rg` và `WeekFields`

`java.time.temporal.WeekFields` mô tả hai yếu tố:

1. **First day of week**: ví dụ thứ Hai hoặc Chủ nhật.
2. **Minimal days in first week**: cần tối thiểu bao nhiêu ngày của năm mới để nhóm ngày đó được tính là **tuần đầu của năm-tuần**.

Chỉ biết ngày đầu tuần **chưa đủ** để xác định số tuần tại đầu/cuối năm.

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

Locale mon = Locale.forLanguageTag("en-US-u-fw-mon");
Locale sun = Locale.forLanguageTag("en-US-u-fw-sun");

WeekFields mondayFirst = WeekFields.of(mon);
WeekFields sundayFirst = WeekFields.of(sun);

System.out.println(mondayFirst.getFirstDayOfWeek()); // MONDAY
System.out.println(sundayFirst.getFirstDayOfWeek()); // SUNDAY
~~~

Từ Java 10, `WeekFields.of(Locale)` tôn trọng các extension **`fw`** và **`rg`** nếu dữ liệu locale/provider hỗ trợ. Nếu cả hai có mặt, **`fw` tường minh ưu tiên** so với ngày đầu tuần suy ra từ `rg`.

Ví dụ `rg-gbzzzz` yêu cầu quy ước vùng GB (thường tuần bắt đầu thứ Hai), nhưng `fw-sun` yêu cầu rõ Chủ nhật:

~~~java
Locale override = Locale.forLanguageTag(
        "en-US-u-fw-sun-rg-gbzzzz"
);

DayOfWeek first = WeekFields.of(override).getFirstDayOfWeek();
// SUNDAY ở JDK hỗ trợ Unicode locale extensions
~~~

Không chỉ nhìn `locale.getCountry()` để suy luận mọi quy ước: `rg` có thể override vùng **dùng cho dữ liệu bản địa hóa** trong khi country subtag gốc vẫn là `US`.

### 3.1. `fw` không đặt `minimalDaysInFirstWeek` thành ISO

Một hiểu lầm quan trọng: `fw-mon` **chỉ yêu cầu thứ Hai là ngày đầu tuần**, không hứa `getMinimalDaysInFirstWeek() == 4`.

Trên JDK đã kiểm tra, với `en-US-u-fw-mon`:

~~~java
WeekFields fields = WeekFields.of(
        Locale.forLanguageTag("en-US-u-fw-mon")
);

System.out.println(fields.getFirstDayOfWeek()); // MONDAY
System.out.println(fields.getMinimalDaysInFirstWeek()); // 1
~~~

Trong khi đó:

~~~java
WeekFields iso = WeekFields.ISO;
System.out.println(iso.getFirstDayOfWeek()); // MONDAY
System.out.println(iso.getMinimalDaysInFirstWeek()); // 4
~~~

**Hai bộ quy tắc đều bắt đầu vào thứ Hai nhưng có thể cho số tuần khác nhau ở biên năm.**

Nếu nghiệp vụ yêu cầu ISO-8601, nên dùng **`WeekFields.ISO`** tường minh. Nếu yêu cầu quy tắc của người dùng theo vùng, dùng `WeekFields.of(locale)`; khi cần kiểm thử ổn định, hãy xác định rõ locale provider hoặc kiểm tra riêng các thuộc tính nhận được.

## 4. Biên năm: tuần 53 của năm trước hay tuần 1 của năm mới?

Xét **thứ Sáu, 01/01/2021**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;

LocalDate date = LocalDate.of(2021, 1, 1);

int isoWeek = date.get(WeekFields.ISO.weekOfWeekBasedYear());
int isoWeekYear = date.get(WeekFields.ISO.weekBasedYear());

int sundayWeek = date.get(
        WeekFields.SUNDAY_START.weekOfWeekBasedYear()
);
int sundayWeekYear = date.get(
        WeekFields.SUNDAY_START.weekBasedYear()
);
~~~

Kết quả:

| Quy tắc | Ngày đầu tuần | Ngày tối thiểu của tuần đầu | Số tuần | Năm-tuần |
| --- | --- | --- | --- | --- |
| `WeekFields.ISO` | Thứ Hai | 4 | **53** | **2020** |
| `WeekFields.SUNDAY_START` | Chủ nhật | 1 | **1** | **2021** |

Đó không phải lỗi: ngày 01/01/2021 vẫn thuộc **năm dương lịch 2021**, nhưng theo ISO nó nằm trong **tuần 53 của năm-tuần 2020**.

Ba trường khác nhau:

- `date.getYear()`: năm dương lịch, bằng `2021`.
- `date.get(wf.weekBasedYear())`: năm-tuần theo `WeekFields` đã chọn, có thể bằng `2020`.
- `date.get(wf.weekOfWeekBasedYear())`: số tuần trong năm-tuần, có thể bằng `53`.

Không ghép `date.getYear()` với `weekOfWeekBasedYear()` theo một cách tùy ý để tạo mã `2021-W53`: đó có thể là nhãn tuần sai.

### 4.1. Các ngày nên có trong bộ test

| Fixture ngày | Lý do |
| --- | --- |
| 2020-12-28 (thứ Hai) | Đầu tuần ISO cuối năm 2020 |
| 2020-12-31 | Ngày cuối năm 2020, sát tuần ISO 53 |
| **2021-01-01** | Ngày đầu năm nhưng thuộc ISO week-based-year 2020 |
| 2021-01-03 | Chủ nhật, sát thời điểm chuyển tuần theo các quy tắc |
| 2021-01-04 (thứ Hai) | Bắt đầu ISO week 1 năm-tuần 2021 |
| Ngày giao tháng, ví dụ 2024-09-01 | Kiểm tra `weekOfMonth()` có thể khác khi đổi `fw`/minimal days |

Bài kiểm thử không nhất thiết gắn cứng mọi số tuần vào dữ liệu người dùng. Hãy tách **bộ test ISO bất biến theo hợp đồng** và **bộ test locale-sensitive** cần đối chiếu provider trên môi trường đích.

### 4.2. `weekOfYear()` khác `weekOfWeekBasedYear()`

`WeekFields.weekOfYear()` đếm tuần **trong năm dương lịch** và có thể trả **tuần 0** cho những ngày trước tuần 1 theo quy tắc minimal days. `weekOfWeekBasedYear()` đi cùng `weekBasedYear()` và cho số tuần của **năm-tuần** tương ứng.

Khi lưu mã tuần cho báo cáo, cần xác định có dùng **ISO week-year** hay **calendar-year week**; không thay đổi hai kiểu tính mà vẫn giữ cùng tên trường `year`, `week`.

Một lựa chọn định dạng cần thận trọng:

~~~java
// YYYY là week-based-year; uuuu là proleptic calendar year.
// Pattern "YYYY-'W'ww-e" dùng quy tắc tuần theo Locale của formatter.
~~~

Dùng `DateTimeFormatter.ISO_WEEK_DATE` hoặc `WeekFields.ISO` nếu định dạng lưu trữ đòi hỏi ISO; không phụ thuộc Locale mặc định của JVM.

## 5. Kiểm thử quy ước tiền tệ với `cu` và `rg`

`Currency.getInstance(Locale)` xét mã vùng và các Unicode locale keyword liên quan. Từ Java 10, **`cu`** có thể chỉ rõ loại tiền tệ, còn **`rg`** có thể override vùng dùng để chọn đồng tiền mặc định.

~~~java
import java.util.Currency;
import java.util.Locale;

Locale euroInUS = Locale.forLanguageTag("en-US-u-cu-eur");
Locale gbRegion = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
Locale gbButEuro = Locale.forLanguageTag(
        "en-US-u-cu-eur-rg-gbzzzz"
);

System.out.println(Currency.getInstance(euroInUS).getCurrencyCode()); // EUR
System.out.println(Currency.getInstance(gbRegion).getCurrencyCode()); // GBP
System.out.println(Currency.getInstance(gbButEuro).getCurrencyCode()); // EUR
~~~

**Thứ tự ưu tiên:** nếu cả `cu` và `rg` có mặt, mã tiền từ **`cu` tường minh ưu tiên** so với đồng tiền ngầm định từ vùng `rg`. Ngôn ngữ `en` và vùng gốc `US` không bắt buộc người dùng phải định dạng USD trong mọi trường hợp.

### 5.1. Kiểm tra mã tiền, không phụ thuộc glyph hiển thị

~~~java
import java.text.NumberFormat;

NumberFormat formatter = NumberFormat.getCurrencyInstance(euroInUS);
Currency selected = formatter.getCurrency();

System.out.println(selected.getCurrencyCode()); // EUR
~~~

Khi định dạng số tiền, **ký hiệu tiền**, dấu phân cách nghìn, vị trí ký hiệu, khoảng trắng và dấu thập phân phụ thuộc locale/provider và có thể thay đổi khi CLDR được cập nhật. Vì thế nếu mục tiêu là kiểm tra **đồng tiền được chọn**, test nên so **`getCurrencyCode()`** thay vì so tuyệt đối chuỗi như `"€12.50"`.

Chỉ so chuỗi hiển thị đầy đủ khi chính **giao diện đó** là phần cần kiểm chứng và bạn có kiểm soát locale provider/runtime. Cần lưu ý một số ký hiệu như `$` không xác định duy nhất một mã tiền nếu không có thông tin vùng.

### 5.2. Quy tắc làm tròn và phần thập phân không đồng nhất

Các đơn vị tiền tệ không nhất thiết đều có **hai** chữ số thập phân theo quy tắc chuẩn. `Currency.getDefaultFractionDigits()` giúp tra số chữ số chuẩn hoặc trả `-1` với loại tiền tệ không xác định số chữ số thập phân.

Trong nghiệp vụ thanh toán, không nên giả định:

~~~java
// Sai nếu coi là quy tắc cho mọi currency:
int fractionDigits = 2;
~~~

Hãy dùng `BigDecimal` cho lượng tiền, quy tắc làm tròn **được nêu rõ** (ví dụ `RoundingMode.HALF_EVEN` nếu được nghiệp vụ quy định) và mã `Currency` phù hợp. Dữ liệu/metadata của đơn vị tiền có thể được cập nhật theo thời gian; **quy tắc thanh toán của nhà cung cấp hoặc ngân hàng** không nhất thiết trùng hoàn toàn với số chữ số mặc định của JDK.

Ví dụ trong một phương thức:

~~~java
BigDecimal amount = new BigDecimal("12.50");
Currency currency = Currency.getInstance("EUR");

System.out.println(currency.getCurrencyCode()); // EUR
System.out.println(amount.toPlainString());      // 12.50
~~~

Nên lưu **giá trị và đơn vị tiền** riêng biệt; format thành chuỗi bản địa hóa **ở biên hiển thị**. Không parse một chuỗi đã được định dạng của locale khác để quyết định số tiền thanh toán.

### 5.3. `Locale` không tự chứng minh giao dịch được phép dùng loại tiền đó

`cu-eur` thể hiện **ưu tiên/định dạng** mà API hỗ trợ; nó không tự thay đổi đơn vị của một số tiền đang lưu trong hệ thống, không thực hiện chuyển đổi EUR/USD và không xác nhận phương thức thanh toán có hỗ trợ EUR. Cần tách:

- **Transaction currency**: đơn vị tiền thực sự của giao dịch, thường do hợp đồng nghiệp vụ quyết định.
- **Display locale/currency**: lựa chọn biểu diễn cho người xem.
- **Exchange rate/conversion**: nghiệp vụ riêng nếu cần đổi tiền; không tự diễn ra trong `Currency` hoặc `NumberFormat`.

Không được lấy `Currency.getInstance(userLocale)` rồi mặc nhiên thay mã tiền đã gắn với giao dịch.

## 6. Múi giờ: `Locale` và `ZoneId` là hai thứ khác nhau

Một `Locale` cho biết sở thích về định dạng; **`ZoneId`** mới đại diện cho tập các quy tắc tính chênh lệch múi giờ theo thời gian.

Trong Java, với thời điểm cụ thể:

~~~java
import java.time.Instant;
import java.time.ZoneId;

Instant when = Instant.parse("2024-07-01T12:00:00Z");
ZoneId newYork = ZoneId.of("America/New_York");

System.out.println(when.atZone(newYork).toLocalTime()); // 08:00
~~~

`ZoneId.of("America/New_York")` là **IANA region-based identifier**. `America/New_York` mang quy tắc chuyển đổi DST theo thời điểm; không chỉ là một offset cố định `-05:00`.

Không coi **`en-US`** là timezone New York: một vùng có thể chứa nhiều múi giờ, và `Locale.forLanguageTag("en-US")` không tự đặt `ZoneId.systemDefault()`.

### 6.1. Unicode key `tz` trong Java 10

Unicode Locale Extension `tz` có type riêng theo chuẩn, ví dụ:

~~~text
en-US-u-tz-usnyc
~~~

`usnyc` là mã Unicode time-zone type cho New York, **không phải chuỗi IANA `America/New_York`**. Đừng đưa `usnyc` vào `ZoneId.of` và mong đó là mã IANA hợp lệ.

Ở API có hỗ trợ, chẳng hạn `DateTimeFormatter.localizedBy(Locale)` (Java 10+), mã này có thể được dịch thành `ZoneId` tương ứng:

~~~java
import java.time.format.DateTimeFormatter;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("en-US-u-tz-usnyc");
DateTimeFormatter base = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm XXX", Locale.US
);
DateTimeFormatter localized = base.localizedBy(locale);

// Trên JDK đã kiểm tra: localized.getZone() là America/New_York.
~~~

Với xử lý nghiệp vụ đặt lịch theo vùng của người dùng, thường rõ nghĩa hơn khi lưu **IANA `ZoneId` tường minh** trong cấu hình/người dùng và `Instant` cho thời điểm. Dùng `tz` để điều khiển formatter khi ứng dụng tiếp nhận sở thích bản địa hóa bằng Unicode language tag.

### 6.2. `withLocale` không đồng nghĩa `localizedBy`

`DateTimeFormatter.withLocale(locale)` thay Locale, chủ yếu dùng cho chuỗi/pattern có yếu tố bản địa hóa. Nó **không tự áp dụng** toàn bộ Unicode keyword để đặt chronology, numbering system hoặc time zone.

Ngược lại `localizedBy(locale)` có thể áp dụng `ca`, `nu`, `rg` và `tz` theo hợp đồng:

~~~java
Locale tz = Locale.forLanguageTag("en-US-u-tz-usnyc");
DateTimeFormatter f = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm XXX", Locale.US
);

System.out.println(f.withLocale(tz).getZone()); // null
System.out.println(f.localizedBy(tz).getZone()); // America/New_York
~~~

Nếu đã đặt `withZone(...)` tường minh và cũng gọi `localizedBy(...)`, **thứ tự chaining ảnh hưởng kết quả**: lệnh sau có thể thay thiết lập trước. Cần kiểm tra formatter cuối bằng `getZone()` và thử với một `Instant` cố định.

## 7. Biên DST: giờ không tồn tại và giờ xuất hiện hai lần

Các trường hợp dễ phát sinh lỗi đặt lịch là **DST gap** và **DST overlap**. Dùng ví dụ lịch sử tại vùng `America/New_York`, năm **2024**, để kiểm thử thay vì dựa vào năm hiện tại.

### 7.1. Gap: 02:30 ngày 10/03/2024 không tồn tại

Khi New York chuyển từ UTC-05:00 sang UTC-04:00 vào buổi sáng 10/03/2024, đồng hồ nhảy từ **01:59:59** lên **03:00:00**. Vì vậy:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);

int validOffsets = zone.getRules().getValidOffsets(gap).size();
// 0: không có offset hợp lệ.
~~~

Việc gọi `gap.atZone(zone)` thông thường **điều chỉnh** giờ không tồn tại về sau khoảng gap (trong trường hợp này `03:30`), không ném lỗi mặc định. Nếu nghiệp vụ **không cho phép tự dời lịch hẹn**, bạn phải kiểm tra `ZoneRules.getValidOffsets(localDateTime)` và từ chối hoặc yêu cầu người dùng xác nhận.

### 7.2. Overlap: 01:30 ngày 03/11/2024 xuất hiện hai lần

Khi New York trở lại UTC-05:00, giờ **01:30** diễn ra hai lần với hai offset hợp lệ:

~~~java
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
var offsets = zone.getRules().getValidOffsets(overlap);

// Có 2 offset hợp lệ: -04:00 và -05:00.
~~~

Nếu không có chính sách phân biệt, `overlap.atZone(zone)` mặc định chọn offset sớm hơn của vùng overlap (trong trường hợp này `-04:00`). Đây là một quy tắc có thể kiểm thử, nhưng **không được tự cho là quy tắc phù hợp với mọi nghiệp vụ**.

Đối với lịch hẹn, có thể cần người dùng chọn **lần 01:30 đầu tiên hay lần thứ hai**. Khi đã có lựa chọn, hãy lưu instant hoặc `ZonedDateTime` có offset thực sự, không chỉ chuỗi `2024-11-03 01:30`.

### 7.3. Kiểm tra độ dài của một ngày địa phương

Một “ngày” theo lịch không phải lúc nào cũng là 24 giờ tính theo `Duration`:

~~~java
ZoneId ny = ZoneId.of("America/New_York");

long springHours = Duration.between(
        LocalDate.of(2024, 3, 10).atStartOfDay(ny),
        LocalDate.of(2024, 3, 11).atStartOfDay(ny)
).toHours(); // 23

long autumnHours = Duration.between(
        LocalDate.of(2024, 11, 3).atStartOfDay(ny),
        LocalDate.of(2024, 11, 4).atStartOfDay(ny)
).toHours(); // 25
~~~

Với kỳ báo cáo theo **ngày địa phương**, nên tính biên bằng `LocalDate.atStartOfDay(zone)` của ngày bắt đầu và ngày tiếp theo. Không cứ lấy đầu ngày rồi cộng `24` giờ cố định trong mọi vùng, bởi DST làm thay đổi độ dài ngày.

Nếu bài toán tính thời lượng thực giữa hai thời điểm, dùng `Instant` và `Duration`. Nếu bài toán cộng ngày trên lịch, dùng `LocalDate.plusDays(1)` rồi chuyển qua `ZoneId` phù hợp. Không đồng nhất “thêm một ngày lịch” với “thêm 24 giờ”.

## 8. Chương trình Java 17+ kiểm chứng ba nhóm biên

Chương trình sau có **ngày/giờ cố định**, không phụ thuộc múi giờ mặc định hoặc `LocalDate.now()`. Nó dùng các API từ Java 10 trở đi, nhưng biên dịch và chạy trực tiếp trên **JDK 17+**.

Lưu thành tệp **LocaleBoundaryTests.java**:

~~~java
import java.text.NumberFormat;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class LocaleBoundaryTests {
    private static void require(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        // (1) Khóa fw, rg và biên năm-tuần.
        Locale mon = Locale.forLanguageTag("en-US-u-fw-mon");
        Locale sun = Locale.forLanguageTag("en-US-u-fw-sun");
        Locale both = Locale.forLanguageTag(
                "en-US-u-fw-sun-rg-gbzzzz"
        );

        WeekFields monday = WeekFields.of(mon);
        WeekFields sunday = WeekFields.of(sun);

        System.out.println("fw mon: " + monday.getFirstDayOfWeek());
        System.out.println("fw sun: " + sunday.getFirstDayOfWeek());
        System.out.println(
                "fw beats rg: "
                        + WeekFields.of(both).getFirstDayOfWeek()
        );
        System.out.println(
                "fw mon minimal days: "
                        + monday.getMinimalDaysInFirstWeek()
        );

        LocalDate jan1 = LocalDate.of(2021, 1, 1);
        WeekFields iso = WeekFields.ISO;
        WeekFields sunStart = WeekFields.SUNDAY_START;

        System.out.println("ISO week: "
                + jan1.get(iso.weekOfWeekBasedYear()));
        System.out.println("ISO week-year: "
                + jan1.get(iso.weekBasedYear()));
        System.out.println("Sunday week: "
                + jan1.get(sunStart.weekOfWeekBasedYear()));
        System.out.println("Sunday week-year: "
                + jan1.get(sunStart.weekBasedYear()));

        // (2) cu/rg và mã tiền, không so ký hiệu phụ thuộc CLDR.
        Locale eur = Locale.forLanguageTag("en-US-u-cu-eur");
        Locale gb = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
        Locale gbEur = Locale.forLanguageTag(
                "en-US-u-cu-eur-rg-gbzzzz"
        );

        System.out.println("cu override: "
                + Currency.getInstance(eur).getCurrencyCode());
        System.out.println("rg override: "
                + Currency.getInstance(gb).getCurrencyCode());
        System.out.println("cu beats rg: "
                + Currency.getInstance(gbEur).getCurrencyCode());
        System.out.println("currency formatter: "
                + NumberFormat.getCurrencyInstance(eur)
                        .getCurrency().getCurrencyCode());

        // (3) DST gap/overlap: dùng region-based ZoneId.
        ZoneId ny = ZoneId.of("America/New_York");
        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        System.out.println("gap valid offsets: "
                + ny.getRules().getValidOffsets(gap).size());
        System.out.println("overlap valid offsets: "
                + ny.getRules().getValidOffsets(overlap).size());
        System.out.println("gap adjusted time: "
                + gap.atZone(ny).toLocalTime());
        System.out.println("overlap earlier offset: "
                + overlap.atZone(ny).getOffset());

        Instant before = Instant.parse("2024-03-10T06:59:59Z");
        Instant after = before.plusSeconds(1);

        System.out.println("before transition: "
                + before.atZone(ny).toLocalTime() + " "
                + before.atZone(ny).getOffset());
        System.out.println("after transition: "
                + after.atZone(ny).toLocalTime() + " "
                + after.atZone(ny).getOffset());

        long springHours = Duration.between(
                LocalDate.of(2024, 3, 10).atStartOfDay(ny),
                LocalDate.of(2024, 3, 11).atStartOfDay(ny)
        ).toHours();
        long fallHours = Duration.between(
                LocalDate.of(2024, 11, 3).atStartOfDay(ny),
                LocalDate.of(2024, 11, 4).atStartOfDay(ny)
        ).toHours();

        System.out.println("spring day hours: " + springHours);
        System.out.println("fall day hours: " + fallHours);

        // (4) tz từ Unicode Locale Extension.
        Locale tz = Locale.forLanguageTag("en-US-u-tz-usnyc");
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US
        );
        DateTimeFormatter localized = base.localizedBy(tz);

        System.out.println("tz token: "
                + tz.getUnicodeLocaleType("tz"));
        System.out.println("localized zone: " + localized.getZone());
        System.out.println("withLocale zone: "
                + base.withLocale(tz).getZone());
        System.out.println("localized instant: " + localized.format(
                Instant.parse("2024-07-01T12:00:00Z")
        ));
        System.out.println("explicit zone wins: "
                + localized.withZone(ZoneId.of("UTC")).getZone());

        // Invariants quan trọng, không dựa vào text tiền tệ.
        require(monday.getFirstDayOfWeek().toString()
                .equals("MONDAY"), "fw-mon");
        require(sunday.getFirstDayOfWeek().toString()
                .equals("SUNDAY"), "fw-sun");
        require(jan1.get(iso.weekOfWeekBasedYear()) == 53,
                "ISO week");
        require(jan1.get(iso.weekBasedYear()) == 2020,
                "ISO week-year");
        require(Currency.getInstance(gbEur).getCurrencyCode()
                .equals("EUR"), "cu beats rg");
        require(ny.getRules().getValidOffsets(gap).isEmpty(),
                "DST gap");
        require(ny.getRules().getValidOffsets(overlap).size() == 2,
                "DST overlap");
        require(springHours == 23 && fallHours == 25,
                "DST day length");

        System.out.println("assertions: PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocaleBoundaryTests.java
java LocaleBoundaryTests
~~~

Kết quả đã xác minh trên JDK có dữ liệu Unicode locale và tzdb tương ứng:

~~~text
fw mon: MONDAY
fw sun: SUNDAY
fw beats rg: SUNDAY
fw mon minimal days: 1
ISO week: 53
ISO week-year: 2020
Sunday week: 1
Sunday week-year: 2021
cu override: EUR
rg override: GBP
cu beats rg: EUR
currency formatter: EUR
gap valid offsets: 0
overlap valid offsets: 2
gap adjusted time: 03:30
overlap earlier offset: -04:00
before transition: 01:59:59 -05:00
after transition: 03:00 -04:00
spring day hours: 23
fall day hours: 25
tz token: usnyc
localized zone: America/New_York
withLocale zone: null
localized instant: 2024-07-01 08:00 -04:00
explicit zone wins: UTC
assertions: PASS
~~~

Những kết quả trên được chọn để làm rõ **hợp đồng API** và tình huống biên, không phải để tuyên bố mọi runtime đều có cùng phiên bản CLDR/tzdb. Nếu triển khai trên một runtime tùy biến thiếu locale data hoặc có cơ sở dữ liệu múi giờ khác, hãy xác minh trên môi trường đó. Bộ assert ISO week và các kiểm tra hành vi cơ bản giúp phân biệt lỗi logic với khác biệt dữ liệu bản địa hóa.

## 9. Giải thích các phép test chính

### 9.1. Tuần theo locale không nhất thiết tương đương ISO

Dòng `fw mon minimal days: 1` nhấn mạnh `fw-mon` không tự nâng quy tắc tuần thành ISO. Với vùng US và dữ liệu JDK đã kiểm tra, Monday-first vẫn có **minimal days = 1**, khác ISO = 4. Trường `WeekFields.of(locale)` phù hợp khi ứng dụng muốn quy tắc theo người dùng; `WeekFields.ISO` phù hợp khi một giao thức hoặc báo cáo đã quy định ISO.

### 9.2. `cu` và `rg` là lựa chọn tiền, không phải chuyển đổi tỷ giá

`rg-gbzzzz` khiến Java chọn GBP theo vùng override; thêm `cu-eur` làm EUR ưu tiên. Nhưng một số tiền đã lưu với mã GBP không được tự động đổi thành EUR. `NumberFormat.getCurrencyInstance(eur).getCurrency()` chứng minh đồng tiền được formatter chọn, không chứng minh giá trị giao dịch đã được quy đổi.

### 9.3. DST gap/overlap là bài toán chuyển local time thành instant

`ZoneRules.getValidOffsets(local)` thể hiện số lựa chọn:

| Kích thước danh sách | Ý nghĩa | Chính sách ứng dụng cần quyết định |
| --- | --- | --- |
| `1` | Giờ địa phương bình thường | Ánh xạ sang một instant |
| `0` | Gap: giờ không tồn tại | Từ chối, dời giờ hoặc yêu cầu chọn lại |
| `2` | Overlap: giờ xuất hiện hai lần | Chọn offset trước/sau theo nghiệp vụ |

`LocalDateTime.atZone(zone)` có hành vi mặc định để xử lý gap/overlap. Không phải tất cả ứng dụng đặt lịch đều muốn lựa chọn mặc định đó. Khi nhận `LocalDateTime` từ biểu mẫu người dùng, hãy xét `zone.getRules().getValidOffsets(...)` trước khi lưu một `Instant` cụ thể.

### 9.4. `tz` được `localizedBy` áp dụng, không phải được mọi API ngầm dùng

`localized.getZone()` xác minh formatter nhận lựa chọn `tz=usnyc`. `base.withLocale(tz).getZone() == null` trong chương trình nhắc rằng **chỉ thay locale** chưa tự đặt zone. Lệnh `withZone(UTC)` đặt sau `localizedBy` cho kết quả UTC; thứ tự cấu hình cần được làm rõ.

## 10. Tình huống kiểm thử ở cấp ứng dụng

Bộ test unit đủ tốt cần kết hợp với integration tests trong môi trường thật. Có thể xây checklist theo từng lớp:

| Lớp/luồng xử lý | Fixture | Điều cần xác minh |
| --- | --- | --- |
| API báo cáo theo ISO week | 2021-01-01 | Trả `2020-W53`, không phải `2021-W53` |
| Lịch giao diện theo locale US | `fw=sun` | Cột đầu tuần là Chủ nhật |
| Lịch giao diện US nhưng người dùng chọn thứ Hai | `fw=mon` | Cột đầu là thứ Hai; **không suy ra ISO week-year** |
| Vùng override nhưng có `fw` tường minh | `en-US-u-fw-sun-rg-gbzzzz` | `fw` được ưu tiên |
| Định dạng tiền tệ được override | `en-US-u-cu-eur` | `Currency` có mã `EUR` |
| Đồng tiền ngầm định theo vùng override | `en-US-u-rg-gbzzzz` | Chọn `GBP` theo metadata runtime |
| Có cả `cu` và `rg` | `en-US-u-cu-eur-rg-gbzzzz` | `cu=EUR` ưu tiên |
| Lịch hẹn tại DST gap | New York, 2024-03-10 02:30 | Phát hiện **không có offset hợp lệ** |
| Lịch hẹn tại DST overlap | New York, 2024-11-03 01:30 | Phát hiện **hai offset**, áp chính sách chọn |
| Báo cáo ngày qua DST | 2024-03-10 và 2024-11-03 tại New York | Cửa sổ thực tương ứng 23 và 25 giờ |
| Formatter nhận `tz` | `en-US-u-tz-usnyc` | Kiểm tra `getZone()` sau `localizedBy` |
| Thay đổi timezone mặc định của host | Chạy test với hai thiết lập `user.timezone` khác nhau | Logic dùng `ZoneId` tường minh phải không đổi |
| Provider/CLDR khác | Runtime JDK mục tiêu | Xác nhận glyph/ký hiệu/mẫu hiển thị mà UX cần |

Đối với logic ngày đầu tuần của giao diện, có thể xác định đầu một tuần như sau:

~~~java
LocalDate date = LocalDate.of(2024, 9, 1);
WeekFields fields = WeekFields.of(
        Locale.forLanguageTag("en-US-u-fw-mon")
);

LocalDate startOfWeek = date.with(
        java.time.temporal.TemporalAdjusters.previousOrSame(
                fields.getFirstDayOfWeek()
        )
);
~~~

Đây là **đoạn minh họa trong một phương thức**. Việc lùi tới ngày đầu tuần chỉ giải quyết khoảng ngày để trình bày; khi tính số tuần/năm-tuần vẫn phải dùng quy tắc `minimalDaysInFirstWeek` tương ứng.

## 11. Viết unit test ổn định với `Clock` và cấu hình tường minh

Trong code production, chức năng dùng thời gian hiện tại nên nhận một `Clock` hoặc một thời điểm từ bên ngoài để có thể kiểm thử:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

Clock fixed = Clock.fixed(
        Instant.parse("2024-03-10T07:00:00Z"),
        ZoneId.of("America/New_York")
);

Instant now = Instant.now(fixed);
// Luôn đúng bằng 2024-03-10T07:00:00Z trong test.
~~~

Với logic theo local date:

~~~java
LocalDate localToday = LocalDate.now(fixed);
// 2024-03-10 trong trường hợp fixture này.
~~~

**Không dùng `LocalDate.now()` trống tham số** trong test phụ thuộc ngày, hoặc `ZoneId.systemDefault()` khi kiểm tra múi giờ của người dùng; hai cách này gây phụ thuộc môi trường CI, máy developer và thời điểm test chạy.

Cũng không đặt `Locale.setDefault(...)` toàn cục cho một test thông thường nếu có thể truyền Locale tường minh: thay đổi mặc định toàn JVM có thể tác động các test chạy song song.

Nếu dùng JUnit 5, có thể biến các điều kiện `require(...)` trong chương trình chạy được thành `assertEquals`/`assertTrue` theo từng fixture. Tuy nhiên bài học này không yêu cầu thêm dependency; phương thức `main` vẫn cho phép xác minh contract bằng lệnh `javac`/`java` chuẩn.

## 12. Vùng thời gian không phải offset cố định

Các kiểu thường bị nhầm:

| Kiểu | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `Instant` | Một thời điểm tuyệt đối | Ghi nhận event/transaction xảy ra lúc nào |
| `ZoneId.of("America/New_York")` | Vùng với quy tắc lịch sử và DST | Đặt lịch hoặc hiển thị giờ của người dùng |
| `ZoneOffset.ofHours(-5)` | Chênh lệch cố định UTC-05:00 | Dữ liệu đã biết offset cụ thể, không mô tả toàn bộ DST |
| `LocalDateTime` | Ngày/giờ tường, chưa gắn zone/offset | Input hiển thị của người dùng; cần resolve nếu chuyển thành instant |
| `ZonedDateTime` | Ngày/giờ có zone và offset đã giải quyết | Đặt lịch vùng địa lý với quy tắc thời gian |

Nếu chỉ lưu `UTC-05:00` cho New York quanh mùa hè, những thời điểm ở DST sẽ sai một giờ vì New York có thể dùng `UTC-04:00`. Nếu cần đại diện cho quy tắc toàn vùng, lưu **IANA ZoneId**, không chỉ offset.

Quy tắc timezone có thể thay đổi do quyết định chính sách và phiên bản **tzdb**. Vì vậy bộ test tương lai rất xa không nên coi các chuyển đổi DST như một chân lý bất biến. Khi cập nhật JDK/tzdb, nên rà soát các fixture về múi giờ và chính sách lịch hẹn.

## 13. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ mọi tuần bắt đầu thứ Hai đều là ISO | ISO còn yêu cầu tối thiểu 4 ngày cho tuần đầu | Dùng `WeekFields.ISO` khi cần ISO, kiểm tra `minimalDaysInFirstWeek` |
| Dùng `date.getYear()` cùng `weekOfWeekBasedYear()` | Có thể ghép sai năm-tuần ở biên 01/01 | Dùng `weekBasedYear()` cùng `weekOfWeekBasedYear()` |
| Nhầm `weekOfYear` với `weekOfWeekBasedYear` | Khác hợp đồng, có thể có week 0 | Chọn một mô hình và test ranh giới |
| Nghĩ `fw` ghi đè mọi quy tắc tuần | `fw` chỉ chọn ngày đầu tuần | Kiểm tra cả minimal days |
| Nghĩ mã quốc gia `US` luôn bắt buộc USD | `cu` và `rg` có thể override lựa chọn | Kiểm tra `Currency.getCurrencyCode()` |
| So sánh chuỗi tiền tệ đúng tuyệt đối trong unit test xuyên provider | Symbol, dấu nhóm, khoảng trắng, mẫu hiển thị có thể đổi | Test mã tiền và định dạng riêng |
| Giả định mọi currency có 2 số lẻ | ISO và quy định nghiệp vụ khác nhau | Dùng `Currency`/quy tắc tài chính tường minh |
| Nghĩ đổi `Locale` sẽ quy đổi giá trị tiền | `Locale` chỉ hỗ trợ lựa chọn hiển thị | Xử lý tỷ giá/giao dịch độc lập |
| Nghĩ `Locale` là múi giờ | `Locale` không đồng nghĩa `ZoneId` | Lưu zone địa lý tường minh |
| Dùng offset cố định cho New York quanh năm | Bỏ qua DST và lịch sử | Dùng `America/New_York` |
| Nghĩ local time nào cũng hợp lệ và duy nhất | Gap có 0 offset, overlap có 2 | Kiểm tra `ZoneRules.getValidOffsets` |
| Nghĩ một ngày luôn bằng 24 giờ thực | Ngày qua DST có thể 23 hoặc 25 giờ | Tính từ start-of-day của hai ngày theo zone |
| Nghĩ `withLocale` áp dụng `tz` như `localizedBy` | Hai phương thức có hợp đồng khác nhau | Dùng `localizedBy` nếu muốn áp Unicode keywords |
| Dùng `usnyc` trực tiếp với `ZoneId.of` | Đây là Unicode timezone type, không phải IANA ZoneId | Dùng `America/New_York` cho zone nghiệp vụ |
| Test dựa vào `now`, default locale/timezone | Test phụ thuộc CI và thời điểm chạy | Dùng fixture cố định, `Clock.fixed`, Locale và ZoneId tường minh |
| Thay `Locale.setDefault` trong test song song | Ảnh hưởng toàn JVM | Truyền Locale trực tiếp cho API |

## 14. Bộ câu hỏi tự đánh giá

### Câu 1 — biên năm-tuần

Với `LocalDate.of(2021,1,1)`, `WeekFields.ISO.weekOfWeekBasedYear()` và `weekBasedYear()` trả gì?

**Đáp án:** `53` và `2020`. Năm dương lịch của ngày đó vẫn là 2021.

### Câu 2 — chỉ định `fw-mon`

Nếu `WeekFields.of(Locale.forLanguageTag("en-US-u-fw-mon"))` có ngày đầu là thứ Hai, có được kết luận nó giống hệt `WeekFields.ISO` không?

**Đáp án:** không. Còn `minimalDaysInFirstWeek`; trên JDK kiểm chứng, locale US với `fw-mon` vẫn có minimal days = 1, trong khi ISO là 4.

### Câu 3 — ưu tiên `cu` và `rg`

Locale `en-US-u-cu-eur-rg-gbzzzz` yêu cầu loại tiền gì từ `Currency.getInstance`?

**Đáp án:** **EUR**, vì `cu` được khai báo tường minh, ưu tiên so với đồng tiền chọn theo `rg`.

### Câu 4 — ký hiệu `$`

Một unit test so sánh `NumberFormat.getCurrencyInstance(locale).format(amount)` với một chuỗi cố định có ký hiệu `$`. Test đó có đủ để xác nhận giao dịch dùng đúng USD không?

**Đáp án:** không. Ký hiệu phụ thuộc locale/provider và có thể gây nhập nhằng. Cần kiểm tra **mã tiền ISO** của giao dịch và formatter; việc tính toán/đổi tiền là nghiệp vụ riêng.

### Câu 5 — giờ không tồn tại

Người dùng chọn New York, ngày **10/03/2024**, lúc **02:30**. `ZoneRules.getValidOffsets` trả bao nhiêu offset?

**Đáp án:** **0**. Đó là DST gap; ứng dụng phải có chính sách từ chối hoặc điều chỉnh, không âm thầm coi như một instant duy nhất.

### Câu 6 — giờ lặp lại

Người dùng chọn New York, ngày **03/11/2024**, lúc **01:30**. Có bao nhiêu offset hợp lệ?

**Đáp án:** **2** (`-04:00` và `-05:00`). Nếu cần xác định thời điểm duy nhất, phải chọn offset theo chính sách.

### Câu 7 — `tz` trong Locale

`DateTimeFormatter.localizedBy(Locale.forLanguageTag("en-US-u-tz-usnyc"))` và `withLocale(...)` có cùng tác động lên zone không?

**Đáp án:** không. `localizedBy` có thể ánh xạ `tz` thành vùng New York; `withLocale` không tự ghi đè zone từ extension theo cách đó.

### Câu 8 — phạm vi đúng của bài toán

Một báo cáo theo ngày New York lấy `start` lúc nửa đêm 10/03/2024 rồi tính `end = start.plusHours(24)`. Đó có chắc là đầu ngày 11/03/2024 không?

**Đáp án:** **không**. Do DST, ngày 10/03 chỉ kéo dài **23 giờ thực**; nên tính đầu ngày kế tiếp bằng `LocalDate.plusDays(1).atStartOfDay(zone)` khi báo cáo theo ngày lịch.

## 15. Ghi nhớ và tài liệu tham khảo

- Java 10 mở rộng các Unicode locale keyword **`cu`, `fw`, `rg`, `tz`**; các API vẫn được dùng trong Java hiện hành.
- Kiểm thử tuần phải xét **ngày đầu tuần** lẫn **số ngày tối thiểu trong tuần đầu**. Với giao thức ISO, chọn `WeekFields.ISO`; khi hiển thị theo người dùng, xét `WeekFields.of(locale)`.
- `weekBasedYear()` **có thể khác năm dương lịch** tại ranh giới năm.
- Đối với tiền tệ, `cu` tường minh ưu tiên `rg` khi API hỗ trợ. Luôn test **ISO currency code**, không chỉ ký hiệu hay text được bản địa hóa.
- `Currency`/`NumberFormat` không tự thực hiện quy đổi tiền hoặc xác thực giao dịch.
- `Locale` không thay thế `ZoneId`; dùng **IANA ZoneId** cho nghiệp vụ thời gian.
- DST có thể tạo **gap = 0 offset** và **overlap = 2 offset**. Ngày lịch qua DST không nhất thiết dài 24 giờ.
- `DateTimeFormatter.localizedBy(Locale)` từ Java 10 có thể áp dụng `tz`; `withLocale(Locale)` không tương đương.
- Test đáng tin cậy dùng **ngày/Instant cố định**, `Clock.fixed`, locale/zone/currency tường minh và kiểm tra môi trường CLDR/tzdb mục tiêu.

Tài liệu chuẩn vẫn áp dụng:

- [Oracle — Internationalization Enhancements in JDK 10](https://docs.oracle.com/en/java/javase/17/intl/internationalization-enhancements1.html)
- [Java SE 17 — `Locale` và Unicode Locale Extensions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Java SE 17 — `WeekFields.of(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html)
- [Java SE 17 — `Calendar`, first week và `fw`/`rg`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Calendar.html)
- [Java SE 17 — `Currency.getInstance(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [Java SE 17 — `NumberFormat.getCurrencyInstance(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 17 — `DateTimeFormatter.localizedBy(Locale)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 17 — `ZoneRules.getValidOffsets(LocalDateTime)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Java SE 17 — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)

**Kết luận:** Để kiểm thử `Locale` trong ứng dụng, hãy chủ động chọn fixture **ngày sát biên tuần/năm**, **mã tiền có override**, và **thời điểm ở DST gap/overlap**. Đừng biến sở thích hiển thị thành quy tắc nghiệp vụ hoặc phụ thuộc mặc định runtime. Các bài test đúng sẽ kiểm tra **hợp đồng dữ liệu và quy tắc thời gian** trước, rồi mới kiểm tra chuỗi hiển thị của locale ở môi trường đích.
