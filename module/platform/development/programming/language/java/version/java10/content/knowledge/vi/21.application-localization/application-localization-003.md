# WeekFields.of(Locale) và phần mở rộng fw

## 1. Bài toán: cùng một ngày, các ứng dụng có thể bắt đầu tuần khác nhau

Trong nhiều ứng dụng, lịch tuần không chỉ là một dãy bảy ngày. Giao diện lịch, báo cáo doanh thu theo tuần, phân ca làm việc, biểu đồ “tuần hiện tại” hoặc số tuần của một năm có thể tuân theo quy ước địa phương hoặc cấu hình của người dùng.

Ví dụ:

- Một lịch được cấu hình tuần bắt đầu **thứ Hai**.
- Một lịch khác hiển thị **Chủ nhật** ở cột đầu tiên.
- Một người dùng muốn xem lịch bằng tiếng Anh nhưng đặt **thứ Bảy** làm ngày đầu tuần.
- Bộ phận kế toán dùng chuẩn **ISO-8601**, trong đó tuần bắt đầu thứ Hai và tuần đầu năm phải có tối thiểu bốn ngày thuộc năm đó.

Java cung cấp `java.time.temporal.WeekFields` để mô tả **hai tham số**:

1. **Ngày đầu tuần**: `DayOfWeek` từ `MONDAY` đến `SUNDAY`.
2. **Số ngày tối thiểu của tuần thứ nhất** trong tháng/năm: số nguyên từ `1` đến `7`.

`WeekFields.of(Locale)` lấy các quy tắc tuần theo dữ liệu bản địa hóa của `Locale`. Từ **Java 10**, các thư viện liên quan nhận biết thêm Unicode locale extension **`fw`** (*first day of week*) để một Locale có thể **ghi đè ngày đầu tuần**.

~~~java
// Ví dụ Java 17+, trong một method có các import tương ứng.
Locale mondayFirst = Locale.forLanguageTag("en-US-u-fw-mon");
WeekFields fields = WeekFields.of(mondayFirst);

System.out.println(fields.getFirstDayOfWeek()); // MONDAY
~~~

Đây là cách đặt **ngày đầu tuần theo lựa chọn của người dùng mà không bắt buộc thay đổi ngôn ngữ hoặc quốc gia của Locale**.

**Điểm cần nhớ:** `fw` tác động đến ngày đầu tuần, **không tự đặt số ngày tối thiểu thành 4**, không tự biến quy tắc tuần thành ISO, không đổi múi giờ và không xác định ngày nghỉ cuối tuần.

## 2. Những API đang được hỗ trợ

### WeekFields đã tồn tại trước Java 10; hỗ trợ fw là phần mở rộng của Java 10

`WeekFields` thuộc `java.time.temporal` và xuất hiện từ **Java 8**. Java 10 không phát minh lại lớp này, mà mở rộng hỗ trợ các keyword Unicode locale để `WeekFields.of(Locale)` có thể nhận quy tắc bổ sung từ tag.

Các phương thức quan trọng:

~~~java
// Các chữ ký API để đọc, không phải khai báo ở đầu chương trình.
static WeekFields of(Locale locale);
static WeekFields of(DayOfWeek firstDayOfWeek,
                     int minimalDaysInFirstWeek);

DayOfWeek getFirstDayOfWeek();
int getMinimalDaysInFirstWeek();

TemporalField dayOfWeek();
TemporalField weekOfMonth();
TemporalField weekOfYear();
TemporalField weekOfWeekBasedYear();
TemporalField weekBasedYear();
~~~

Hai overload `of` phục vụ các mục tiêu khác nhau:

- `WeekFields.of(locale)`: lấy định nghĩa tuần theo **Locale**, có tính đến `fw` và `rg` khi được hỗ trợ.
- `WeekFields.of(DayOfWeek.MONDAY, 4)`: lấy định nghĩa **tường minh** với thứ Hai và tối thiểu bốn ngày, không cần phụ thuộc locale data.

`WeekFields` là một lớp bất biến và an toàn khi chia sẻ giữa các luồng. Các instance có cùng cặp tham số được tái sử dụng theo hợp đồng; ứng dụng nên so sánh quy tắc qua giá trị/`equals`, không xây logic nghiệp vụ quanh identity.

### Hai hằng số cần phân biệt

~~~java
WeekFields iso = WeekFields.ISO;
WeekFields sundayStart = WeekFields.SUNDAY_START;

System.out.println(iso.getFirstDayOfWeek()); // MONDAY
System.out.println(iso.getMinimalDaysInFirstWeek()); // 4

System.out.println(sundayStart.getFirstDayOfWeek()); // SUNDAY
System.out.println(sundayStart.getMinimalDaysInFirstWeek()); // 1
~~~

`WeekFields.ISO` có đúng cặp `(MONDAY,4)`. `WeekFields.SUNDAY_START` có cặp `(SUNDAY,1)`. Không mặc định rằng mọi Locale có thứ Hai làm ngày đầu tuần đều phải có `minimalDays=4`.

## 3. Unicode locale extension fw được viết thế nào?

Java sử dụng `Locale` với thẻ ngôn ngữ theo BCP 47. Một Unicode extension bắt đầu bằng `-u-` và gồm các cặp keyword–type.

Mẫu thường dùng:

~~~text
language-REGION-u-fw-day
~~~

Ví dụ:

~~~text
en-US-u-fw-mon
en-US-u-fw-sun
en-US-u-fw-sat
vi-VN-u-fw-mon
~~~

Giải thích `en-US-u-fw-mon`:

| Thành phần | Ý nghĩa |
| --- | --- |
| `en` | Ngôn ngữ tiếng Anh |
| `US` | Vùng/quốc gia Hoa Kỳ |
| `u` | Đoạn Unicode locale extension |
| `fw` | Keyword *first day of week* |
| `mon` | Chọn Monday, tức thứ Hai, làm ngày đầu tuần |

Các giá trị `fw` theo ngày trong tuần:

| Type | DayOfWeek |
| --- | --- |
| `mon` | `MONDAY` |
| `tue` | `TUESDAY` |
| `wed` | `WEDNESDAY` |
| `thu` | `THURSDAY` |
| `fri` | `FRIDAY` |
| `sat` | `SATURDAY` |
| `sun` | `SUNDAY` |

`fw` là giá trị cấu hình **ngày đầu tuần**. Nó không tương đương từ khóa “ngày làm việc đầu tiên”, không mặc định thứ Hai luôn là ngày đi làm và không trực tiếp mô tả thứ Bảy/Chủ nhật là ngày nghỉ.

### Tạo Locale từ thẻ ngôn ngữ

~~~java
// Java 17+.
Locale firstMonday = Locale.forLanguageTag("en-US-u-fw-mon");
Locale firstSaturday = Locale.forLanguageTag("en-US-u-fw-sat");

System.out.println(firstMonday.getUnicodeLocaleType("fw")); // mon
System.out.println(
        WeekFields.of(firstMonday).getFirstDayOfWeek()
); // MONDAY
System.out.println(
        WeekFields.of(firstSaturday).getFirstDayOfWeek()
); // SATURDAY
~~~

`Locale.getUnicodeLocaleType("fw")` dùng để **đọc keyword**. `WeekFields.of(Locale)` mới áp dụng dữ liệu locale và keyword vào quy tắc tuần.

Không nhầm `locale.getCountry()` với giá trị `fw`: country vẫn có thể là `US`, nhưng ngày đầu tuần được ghi đè thành thứ Hai hoặc thứ Bảy.

### Tạo Locale bằng Builder

~~~java
Locale mondayFirst = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("fw", "mon")
        .build();

System.out.println(
        WeekFields.of(mondayFirst).getFirstDayOfWeek()
); // MONDAY
~~~

`Locale.Builder` kiểm tra cú pháp BCP 47 tốt hơn cách đoán/ghép chuỗi thủ công. Khi chương trình có nhiều tùy chọn locale, nó giúp gắn các keyword một cách rõ ràng. Lưu ý: Builder kiểm tra **cú pháp**, không bảo đảm mọi giá trị keyword đều có ý nghĩa được provider hỗ trợ; ứng dụng vẫn phải validate yêu cầu nghiệp vụ.

## 4. WeekFields.of(Locale) lấy quy tắc từ đâu?

~~~java
WeekFields fields = WeekFields.of(locale);
~~~

Phương thức hỏi **locale data provider** của JDK để lấy quy tắc tuần thích hợp. Không có một bảng ngày đầu tuần do code ứng dụng hard-code sẵn cho mọi nước.

Với một Locale thông thường **không có `fw`**, ngày đầu tuần được quyết định từ dữ liệu bản địa hóa tương ứng, có thể theo vùng/quốc gia hoặc các quy tắc override khác. Theo Javadoc hiện hành:

- Nếu Locale có Unicode extension `fw` hợp lệ, giá trị này quyết định **ngày đầu tuần**.
- Nếu Locale có extension `rg` (*region override*), dữ liệu vùng được ghi đè có thể ảnh hưởng quy tắc tuần.
- Nếu **cả `fw` và `rg`** đều được cung cấp, `fw` **ưu tiên** so với giá trị ngày đầu tuần ngầm định từ `rg`.
- `getMinimalDaysInFirstWeek()` là thuộc tính riêng, lấy từ định nghĩa tuần phù hợp của locale data. Đừng coi nó mặc nhiên bằng `4` khi `fw=mon`.

Một ví dụ có cả hai extension:

~~~java
Locale mixed = Locale.forLanguageTag(
        "en-US-u-fw-sat-rg-gbzzzz");

System.out.println(mixed.getUnicodeLocaleType("fw")); // sat
System.out.println(mixed.getUnicodeLocaleType("rg")); // gbzzzz

WeekFields fields = WeekFields.of(mixed);
System.out.println(fields.getFirstDayOfWeek()); // SATURDAY
~~~

Ý nghĩa:

- Ngôn ngữ/vùng cơ sở vẫn là `en-US`.
- `rg-gbzzzz` yêu cầu dùng vùng GB làm region override cho các quy tắc locale-sensitive tương ứng.
- `fw-sat` đặt rõ ngày đầu tuần là **thứ Bảy**, và **thắng** ngày đầu tuần ngầm định theo vùng `GB`.

**Chú ý:** `rg` có cú pháp vùng kèm `zzzz` trong ví dụ này; không được viết `rg-gb` rồi mặc định có cùng nghĩa. Khi phải nhận locale tag từ ngoài ứng dụng, hãy validate cả cấu trúc lẫn các giá trị được hỗ trợ.

### Không hard-code minimalDays theo locale trong unit test chung

Ví dụ:

~~~java
WeekFields fields = WeekFields.of(
        Locale.forLanguageTag("en-US-u-fw-mon"));

System.out.println(fields.getFirstDayOfWeek()); // MONDAY

int minDays = fields.getMinimalDaysInFirstWeek();
// Nên kiểm tra minDays nằm trong [1,7].
// Không tự assert minDays == 4 chỉ vì fw=mon.
~~~

Giá trị `minDays` có thể chịu ảnh hưởng từ locale/provider data. Bản JDK, dữ liệu CLDR và cấu hình runtime là bối cảnh liên quan. Nếu nghiệp vụ **bắt buộc** dùng đúng quy tắc thứ Hai/bốn ngày, hãy yêu cầu:

~~~java
WeekFields rules = WeekFields.of(DayOfWeek.MONDAY, 4);
// Hoặc dùng hằng WeekFields.ISO.
~~~

Đừng dùng `WeekFields.of(Locale.forLanguageTag("en-US-u-fw-mon"))` rồi gọi đó là ISO nếu chưa xác định đúng cả hai tham số.

## 5. Hai tham số của tuần: first day và minimal days

### Ngày đầu tuần: firstDayOfWeek

Thứ Hai hay Chủ nhật ở vị trí đầu ảnh hưởng:

- Thứ tự bảy cột trên giao diện lịch.
- Tuần mà một ngày nằm trong đó.
- Giá trị **ngày trong tuần được đánh số theo địa phương**.
- Biên của từng tuần khi thống kê hoặc tính lịch theo tuần.
- Có thể ảnh hưởng tuần dựa trên năm ở gần ranh giới năm mới.

Với ISO, thứ Hai là ngày đầu và số ngày trong tuần lần lượt là `1..7` từ Monday đến Sunday.

Với quy tắc bắt đầu Chủ nhật, **Chủ nhật** mới là ngày `1` nếu đọc qua `WeekFields.dayOfWeek()`.

~~~java
LocalDate sunday = LocalDate.of(2021, 1, 3);

int isoNumber = sunday.get(WeekFields.ISO.dayOfWeek());
int sundayStartNumber = sunday.get(
        WeekFields.SUNDAY_START.dayOfWeek());

System.out.println(isoNumber);         // 7
System.out.println(sundayStartNumber); // 1
~~~

Điều này **không đổi enum `DayOfWeek.SUNDAY`** và không đổi `ChronoField.DAY_OF_WEEK`. Chỉ có field **localized day-of-week** của `WeekFields` dùng cách đánh số bắt đầu tại ngày được cấu hình.

### Số ngày tối thiểu: minimalDaysInFirstWeek

Giá trị từ 1 đến 7 quyết định tuần nào được tính là **tuần 1** của tháng/năm.

- Nếu là `1`, chỉ cần ít nhất một ngày thuộc tháng/năm mới.
- Nếu là `4`, một tuần chỉ được xem là tuần đầu khi có ít nhất bốn ngày thuộc tháng/năm mới.
- Nếu là `7`, tuần đầu phải chứa đủ bảy ngày thuộc tháng/năm mới.

~~~java
WeekFields iso = WeekFields.of(DayOfWeek.MONDAY, 4);

System.out.println(iso.getFirstDayOfWeek());        // MONDAY
System.out.println(iso.getMinimalDaysInFirstWeek()); // 4
~~~

Hai thông số độc lập. Ví dụ `WeekFields.of(DayOfWeek.SATURDAY, 4)` hợp lệ, dù không phải chuẩn ISO. `fw=sat` đặt ngày đầu tuần; nó **không trực tiếp cho biết** minimalDays.

### Giá trị minimalDays nằm ngoài [1,7]

~~~java
// Đoạn minh họa lỗi được bắt.
try {
    WeekFields.of(DayOfWeek.MONDAY, 0);
} catch (IllegalArgumentException expected) {
    System.out.println("invalid minimal days");
}
~~~

`WeekFields.of(DayOfWeek, int)` ném `IllegalArgumentException` khi số ngày tối thiểu không thuộc `1..7`. Đây là kiểm tra input khác với cấu hình Unicode `fw`.

## 6. Dùng WeekFields để đọc các trường của LocalDate

`WeekFields` cung cấp các `TemporalField` chuyên về tuần.

| Field | Ý nghĩa chính | Lưu ý |
| --- | --- | --- |
| `dayOfWeek()` | Ngày trong tuần, đánh số 1..7 theo firstDay | Khác cách đánh số cố định ISO nếu tuần không bắt đầu Monday |
| `weekOfMonth()` | Số tuần trong tháng, các tuần không vượt ranh giới tháng | Có thể có tuần 0 |
| `weekOfYear()` | Số tuần thuộc **năm dương lịch** | Có thể có tuần 0 gần đầu năm |
| `weekOfWeekBasedYear()` | Số tuần trong **năm tính theo tuần** | Thường 1..52 hoặc 53 |
| `weekBasedYear()` | Năm tính theo tuần | Có thể khác `LocalDate.getYear()` gần ranh giới năm mới |

Ví dụ đọc field:

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);

WeekFields iso = WeekFields.ISO;

int calendarYear = date.getYear();                  // 2021
int weekYear = date.get(iso.weekBasedYear());        // 2020
int weekNumber = date.get(iso.weekOfWeekBasedYear()); // 53

System.out.println(calendarYear); // 2021
System.out.println(weekYear);     // 2020
System.out.println(weekNumber);   // 53
~~~

Ngày **2021-01-01** là thứ Sáu. Theo ISO, tuần thứ nhất của 2021 bắt đầu thứ Hai **2021-01-04** vì đây là tuần đầu có đủ ít nhất bốn ngày thuộc năm 2021. Do đó, 1/1 vẫn thuộc **tuần 53 của week-based-year 2020**.

### weekOfYear khác weekOfWeekBasedYear

Với quy tắc ISO:

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);
WeekFields iso = WeekFields.ISO;

System.out.println(date.get(iso.weekOfYear())); // 0
System.out.println(date.get(iso.weekOfWeekBasedYear())); // 53
~~~

`weekOfYear()` thuộc **năm dương lịch của ngày đó**: phần đầu năm chưa được tính là tuần 1 sẽ thuộc tuần 0. `weekOfWeekBasedYear()` thuộc **hệ năm theo tuần** và có thể trả tuần của năm theo tuần trước. Đây không phải lỗi.

### Quy tắc bắt đầu Chủ nhật và minimalDays=1

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);
WeekFields sunday = WeekFields.SUNDAY_START;

System.out.println(date.get(sunday.weekBasedYear())); // 2021
System.out.println(date.get(sunday.weekOfWeekBasedYear())); // 1
~~~

Cùng một `LocalDate`, khi thay cặp quy tắc tuần, năm/tuần thu được khác. Vì vậy, **mã tuần dùng trong báo cáo phải đi kèm định nghĩa tuần**. Không nên lưu một con số `week=1` rồi giả định mọi khách hàng hiểu đó là cùng kỳ thời gian.

## 7. WeekFields.of(Locale) và định dạng ngày theo tuần

Ứng dụng có thể muốn hiển thị:

~~~text
2020-W53-5
~~~

Đó là biểu diễn theo **week-based-year / week number / localized day-of-week**, không phải chuỗi ngày dương lịch.

### DateTimeFormatter có ký hiệu cần chú ý

Trong `DateTimeFormatter`:

- `u`: năm theo lịch (proleptic year), ví dụ `uuuu-MM-dd`.
- `y`: year-of-era, thường tương ứng năm dương lịch hiện đại nhưng có ngữ nghĩa era.
- `Y`: **week-based-year theo locale**, có thể khác năm của ngày.
- `w`: số tuần trong week-based-year theo locale.
- `W`: số tuần trong tháng.
- `e`: ngày trong tuần đánh số theo locale.
- `E`: tên thứ trong tuần theo kiểu văn bản.

Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("en-US-u-fw-mon");

DateTimeFormatter localizedWeek = DateTimeFormatter.ofPattern(
        "YYYY-'W'ww-e", locale);

String rendered = localizedWeek.format(LocalDate.of(2021, 1, 1));
// Nội dung phụ thuộc đầy đủ quy tắc tuần của locale, không chỉ fw.
~~~

Ở đây formatter nhận Locale có `fw` để dùng quy tắc tuần tương ứng. **Không khẳng định** kết quả trên là `2020-W53-5` nếu chưa kiểm soát `minimalDaysInFirstWeek`; riêng việc `fw=mon` không đảm bảo dùng ISO.

### Khi cần ISO chính xác

Dùng `WeekFields.ISO` và `DateTimeFormatterBuilder` để chọn đúng các field, tránh phụ thuộc locale data:

~~~java
WeekFields iso = WeekFields.ISO;

DateTimeFormatter isoWeekFormatter = new DateTimeFormatterBuilder()
        .appendValue(iso.weekBasedYear(), 4)
        .appendLiteral("-W")
        .appendValue(iso.weekOfWeekBasedYear(), 2)
        .appendLiteral('-')
        .appendValue(iso.dayOfWeek(), 1)
        .toFormatter(Locale.ROOT);

System.out.println(
        isoWeekFormatter.format(LocalDate.of(2021, 1, 1))
); // 2020-W53-5
~~~

`LocalDate.of(2021,1,1)` là thứ Sáu (ISO day-of-week `5`), thuộc ISO week 53 / week-based-year 2020.

### Bẫy ký hiệu YYYY trong định dạng ngày thông thường

~~~java
// Phản mẫu nếu mục tiêu là ngày theo lịch:
DateTimeFormatter wrong = DateTimeFormatter.ofPattern(
        "YYYY-MM-dd", Locale.US);
~~~

`YYYY` là **week-based-year**, không phải năm lịch. Gần đầu/cuối năm, nó có thể không trùng năm của tháng/ngày đang in. Khi biểu diễn một ngày theo lịch bình thường, ưu tiên mẫu như:

~~~java
DateTimeFormatter calendarDate = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd", Locale.ROOT);
~~~

Nếu muốn số tuần theo locale, dùng formatter/field tuần có chủ đích, không vô tình áp `Y` vào một chuỗi ngày lịch.

## 8. Tính khoảng tuần trong giao diện và báo cáo

Để tạo giao diện bảy cột, thường cần lấy **ngày đầu của tuần chứa một LocalDate**. Không nên tự mặc định thứ Hai khi Locale có `fw`.

~~~java
LocalDate date = LocalDate.of(2021, 1, 3); // Chủ nhật.
Locale custom = Locale.forLanguageTag("en-US-u-fw-sat");
WeekFields fields = WeekFields.of(custom);

DayOfWeek start = fields.getFirstDayOfWeek();

LocalDate first = date.with(
        TemporalAdjusters.previousOrSame(start));
LocalDate last = first.plusDays(6);

System.out.println(first); // 2021-01-02
System.out.println(last);  // 2021-01-08
~~~

`previousOrSame` đưa ngày về thứ Bảy gần nhất không sau ngày đang xét; cộng sáu ngày được đúng khoảng 7 ngày.

Đoạn code tạo **khoảng các ngày trên lịch**, chưa phải khoảng thời gian tức thời trên UTC. Nếu cần truy vấn bản ghi với `Instant` / `ZonedDateTime`, hãy:

1. Xác định `ZoneId` của đơn vị nghiệp vụ/người dùng.
2. Xác định ngày đầu tuần bằng `LocalDate` và `WeekFields`.
3. Chuyển **start-of-day tại ZoneId** thành `Instant` cho biên đầu.
4. Tạo biên cuối bằng `first.plusDays(7).atStartOfDay(zone)`, lấy khoảng **[start, end)**.

Không lấy một thời điểm rồi cộng cố định `7 × 24` giờ để đại diện mọi tuần địa phương, vì chuyển đổi DST có thể làm độ dài thời gian thực thay đổi. `fw` chọn ngày đầu tuần; nó **không mang theo múi giờ**.

### Tạo bảy cột lịch

~~~java
LocalDate first = LocalDate.of(2021, 1, 3)
        .with(TemporalAdjusters.previousOrSame(
                WeekFields.of(
                        Locale.forLanguageTag("en-US-u-fw-sat"))
                .getFirstDayOfWeek()));

for (int i = 0; i < 7; i++) {
    LocalDate cell = first.plusDays(i);
    // Render cell bằng formatter của locale giao diện.
}
~~~

Với `fw=sat`, cột đầu là thứ Bảy. Đừng suy ra ngày này là ngày bắt đầu tuần làm việc hoặc ngày nghỉ: cấu hình hiển thị tuần và lịch làm việc/holiday là hai khái niệm khác nhau.

## 9. Thứ tự ưu tiên fw và rg: những tình huống cần thử

Một số ứng dụng cho phép chọn quốc gia/region khác cho định dạng, đồng thời vẫn giữ sở thích riêng về ngày đầu tuần. Locale extension `rg` đóng vai trò ghi đè vùng; `fw` là lựa chọn ngày đầu tuần tường minh.

| Cấu hình Locale | Ý nghĩa ưu tiên |
| --- | --- |
| `en-US` | Theo locale data của US, không ép bằng một giá trị trong code |
| `en-US-u-fw-mon` | Ngày đầu tuần là thứ Hai |
| `en-US-u-fw-sat` | Ngày đầu tuần là thứ Bảy |
| `en-US-u-rg-gbzzzz` | Áp dụng region override GB cho dữ liệu có liên quan, gồm quy tắc tuần |
| `en-US-u-fw-sat-rg-gbzzzz` | `fw=sat` thắng ngày đầu tuần ngầm định từ `rg` |

Tính ưu tiên được Javadoc `WeekFields.of(Locale)` nêu rõ. Nếu cả hai key cùng tồn tại, **ngày bắt đầu tuần** là của `fw`. Tuy nhiên, **minimalDays** vẫn cần được đọc từ `getMinimalDaysInFirstWeek()` nếu dùng lựa chọn theo locale.

Ví dụ dùng Builder thay vì ghép chuỗi tag:

~~~java
Locale settings = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .setUnicodeLocaleKeyword("fw", "sat")
        .build();

System.out.println(
        WeekFields.of(settings).getFirstDayOfWeek()
); // SATURDAY
~~~

Nếu một quy tắc kinh doanh cần chuẩn cố định `(MONDAY,4)`, ưu tiên `WeekFields.ISO`; không cần mang các keyword địa phương vào phép tính chuẩn hóa đó.

## 10. Chương trình Java 17+ hoàn chỉnh và stdout ổn định

Mục tiêu của chương trình:

- Xác nhận `fw=mon`, `fw=sat`, `fw=tue` áp dụng được.
- Chứng minh `fw` ưu tiên `rg` đối với ngày đầu tuần.
- Đọc keyword bằng `Locale.getUnicodeLocaleType`.
- Kiểm tra `minimalDays` chỉ thuộc `1..7`, không hard-code giá trị theo CLDR của một bản JDK.
- Phân biệt localized `dayOfWeek` và ISO day-of-week.
- Tính năm và số tuần ở ranh giới 2021 bằng hai quy tắc **tường minh**.
- Tính tuần bắt đầu thứ Bảy từ một ngày Chủ nhật.
- Kiểm tra input `minimalDays=0` và một giá trị `fw` không được ứng dụng hỗ trợ.

Lưu file **`WeekFieldsFwDemo.java`** với nội dung sau:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekFieldsFwDemo {

    static DayOfWeek checkedFw(String keyword) {
        if (keyword == null) {
            throw new IllegalArgumentException("fw is missing");
        }

        return switch (keyword) {
            case "mon" -> DayOfWeek.MONDAY;
            case "tue" -> DayOfWeek.TUESDAY;
            case "wed" -> DayOfWeek.WEDNESDAY;
            case "thu" -> DayOfWeek.THURSDAY;
            case "fri" -> DayOfWeek.FRIDAY;
            case "sat" -> DayOfWeek.SATURDAY;
            case "sun" -> DayOfWeek.SUNDAY;
            default -> throw new IllegalArgumentException(
                    "unsupported fw: " + keyword);
        };
    }

    public static void main(String[] args) {
        Locale mondayLocale = Locale.forLanguageTag(
                "en-US-u-fw-mon");
        Locale saturdayLocale = Locale.forLanguageTag(
                "en-US-u-fw-sat");
        Locale withRegionOverride = Locale.forLanguageTag(
                "en-US-u-fw-sat-rg-gbzzzz");

        WeekFields monday = WeekFields.of(mondayLocale);
        WeekFields saturday = WeekFields.of(saturdayLocale);
        WeekFields mixed = WeekFields.of(withRegionOverride);

        System.out.println("fwTag="
                + mondayLocale.getUnicodeLocaleType("fw"));
        System.out.println("fwMonday="
                + (monday.getFirstDayOfWeek()
                        == DayOfWeek.MONDAY));
        System.out.println("fwSaturday="
                + (saturday.getFirstDayOfWeek()
                        == DayOfWeek.SATURDAY));
        System.out.println("rgTag="
                + withRegionOverride.getUnicodeLocaleType("rg"));
        System.out.println("fwOverridesRg="
                + (mixed.getFirstDayOfWeek()
                        == DayOfWeek.SATURDAY));
        System.out.println("checkedFw="
                + checkedFw(mondayLocale.getUnicodeLocaleType("fw")));

        int minimumDays = monday.getMinimalDaysInFirstWeek();
        System.out.println("minDaysRange="
                + (minimumDays >= 1 && minimumDays <= 7));

        Locale built = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("fw", "tue")
                .build();

        System.out.println("builderTuesday="
                + (WeekFields.of(built).getFirstDayOfWeek()
                        == DayOfWeek.TUESDAY));

        WeekFields iso = WeekFields.ISO;
        WeekFields sunday = WeekFields.SUNDAY_START;

        System.out.println("isoRule="
                + (iso.getFirstDayOfWeek() == DayOfWeek.MONDAY
                        && iso.getMinimalDaysInFirstWeek() == 4));
        System.out.println("sundayRule="
                + (sunday.getFirstDayOfWeek() == DayOfWeek.SUNDAY
                        && sunday.getMinimalDaysInFirstWeek() == 1));

        LocalDate jan3 = LocalDate.of(2021, 1, 3);
        System.out.println("isoDayOfSunday="
                + jan3.get(iso.dayOfWeek()));
        System.out.println("mondayLocalDayOfSunday="
                + jan3.get(monday.dayOfWeek()));
        System.out.println("sundayLocalDayOfSunday="
                + jan3.get(sunday.dayOfWeek()));

        LocalDate jan1 = LocalDate.of(2021, 1, 1);
        System.out.println("calendarYear=" + jan1.getYear());
        System.out.println("isoWeekYear="
                + jan1.get(iso.weekBasedYear()));
        System.out.println("isoWeek="
                + jan1.get(iso.weekOfWeekBasedYear()));
        System.out.println("isoWeekOfCalendarYear="
                + jan1.get(iso.weekOfYear()));
        System.out.println("sundayWeekYear="
                + jan1.get(sunday.weekBasedYear()));
        System.out.println("sundayWeek="
                + jan1.get(sunday.weekOfWeekBasedYear()));

        LocalDate first = jan3.with(
                TemporalAdjusters.previousOrSame(
                        saturday.getFirstDayOfWeek()));
        System.out.println("satWeekStart=" + first);
        System.out.println("satWeekEnd="
                + first.plusDays(6));

        try {
            WeekFields.of(DayOfWeek.MONDAY, 0);
        } catch (IllegalArgumentException expected) {
            System.out.println("minDaysRejected=true");
        }

        try {
            checkedFw("xyz");
        } catch (IllegalArgumentException expected) {
            System.out.println("unsupportedFwRejected=true");
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn có hỗ trợ `--release 17`**:

~~~bash
javac --release 17 WeekFieldsFwDemo.java
java WeekFieldsFwDemo
~~~

**Stdout chính xác theo hợp đồng ngày đầu tuần và hai bộ quy tắc cố định ISO/SUNDAY_START:**

~~~text
fwTag=mon
fwMonday=true
fwSaturday=true
rgTag=gbzzzz
fwOverridesRg=true
checkedFw=MONDAY
minDaysRange=true
builderTuesday=true
isoRule=true
sundayRule=true
isoDayOfSunday=7
mondayLocalDayOfSunday=7
sundayLocalDayOfSunday=1
calendarYear=2021
isoWeekYear=2020
isoWeek=53
isoWeekOfCalendarYear=0
sundayWeekYear=2021
sundayWeek=1
satWeekStart=2021-01-02
satWeekEnd=2021-01-08
minDaysRejected=true
unsupportedFwRejected=true
~~~

### Kiểm tra các kết quả quan trọng

**`fwMonday=true` và `fwSaturday=true`:** Unicode locale keyword `fw` của hai Locale được Java 10+ áp dụng vào `WeekFields.of`. Không cần thay `Locale.US` thành Locale khác để có ngày đầu tuần tùy chọn.

**`rgTag=gbzzzz` và `fwOverridesRg=true`:** `rg` còn tồn tại trong Locale, nhưng `fw=sat` được ưu tiên khi xác định ngày đầu tuần. Đây là kiểm thử đúng đặc tính nổi bật của hỗ trợ Java 10.

**`minDaysRange=true`:** chương trình kiểm **phạm vi hợp lệ** thay vì đòi `en-US-u-fw-mon` có một số ngày tối thiểu cố định. Do locale data của JDK có thể được cập nhật, bài không tạo expected stdout phụ thuộc một chi tiết CLDR tùy cấu hình.

**`isoDayOfSunday=7` so với `sundayLocalDayOfSunday=1`:** cùng ngày Chủ nhật nhưng hai cách đánh số theo quy tắc khác nhau. Enum `DayOfWeek.SUNDAY` và `ChronoField.DAY_OF_WEEK` theo ISO không thay đổi.

**`calendarYear=2021` nhưng `isoWeekYear=2020` / `isoWeek=53`:** ngày 2021-01-01 nằm trong tuần cuối của ISO week-based-year 2020. `isoWeekOfCalendarYear=0` thể hiện phương pháp `weekOfYear` không giống `weekOfWeekBasedYear`.

**`sundayWeekYear=2021` / `sundayWeek=1`:** với quy tắc bắt đầu Chủ nhật và minimalDays=1, ngày 2021-01-01 được tính là tuần thứ nhất của week-based-year 2021.

**`satWeekStart=2021-01-02` và `satWeekEnd=2021-01-08`:** tuần chứa Chủ nhật 3/1/2021 bắt đầu thứ Bảy 2/1 nếu `fw=sat`. `TemporalAdjusters.previousOrSame` và cộng sáu ngày tạo ranh giới theo ngày.

**Hai dòng `Rejected=true`:** thứ nhất xác nhận `minimalDays` phải thuộc `1..7`; thứ hai cho thấy cách ứng dụng có thể tự validate type `fw` đã nhận. Không mặc định `Locale.Builder` sẽ biết tất cả giá trị keyword có được ứng dụng hỗ trợ về ngữ nghĩa hay không.

## 11. Những điểm cần kiểm tra khi nhận Locale từ người dùng

### Cần kiểm cú pháp và ý nghĩa keyword

`Locale.forLanguageTag(String)` phù hợp khi đọc tag BCP 47 có sẵn. Tuy nhiên việc tạo được một đối tượng `Locale` **không có nghĩa** mọi giá trị Unicode keyword được runtime hiểu và áp dụng theo cách mong muốn. `Locale.Builder` có thể kiểm tra dạng cú pháp, nhưng **không kiểm hết tính hợp lệ ngữ nghĩa** của keyword–type đăng ký.

Ví dụ nghiệp vụ chỉ chấp nhận một trong bảy type `fw`:

~~~java
static boolean isSupportedFw(String fw) {
    return "mon".equals(fw)
            || "tue".equals(fw)
            || "wed".equals(fw)
            || "thu".equals(fw)
            || "fri".equals(fw)
            || "sat".equals(fw)
            || "sun".equals(fw);
}
~~~

Hàm này dùng cho một **chuỗi type đã được chuẩn hóa chữ thường** như `Locale.getUnicodeLocaleType("fw")`. Nếu nhận text tự do trực tiếp từ người dùng, nên chuẩn hóa theo `Locale.ROOT` hoặc chuyển qua cấu trúc lựa chọn định sẵn, đồng thời xử lý `null` và chuỗi không hợp lệ.

**Không nên suy ra rằng `fw=xyz` là một ngày hợp lệ chỉ vì tag có thể được parse.** Khi ứng dụng có dropdown ngày đầu tuần, kiểm một trong bảy giá trị rồi mới lưu.

### Không phụ thuộc Locale.getDefault() khi quy tắc kinh doanh phải ổn định

~~~java
// Phù hợp khi quy tắc hiển thị thật sự theo môi trường:
WeekFields environmentRules = WeekFields.of(
        Locale.getDefault(Locale.Category.FORMAT));
~~~

Locale mặc định có thể thay đổi theo thiết lập môi trường, JVM, user hoặc runtime. Không dùng nó cho mã hóa kỳ kế toán hoặc định danh tuần ổn định qua các server nếu hệ thống đã công bố một quy tắc doanh nghiệp.

Giải pháp phụ thuộc nhu cầu:

- **Giao diện theo người dùng:** lấy Locale từ cài đặt user/request có kiểm tra, sử dụng `WeekFields.of(locale)`.
- **Quy tắc kế toán ISO:** sử dụng `WeekFields.ISO`.
- **Quy tắc sản phẩm riêng:** sử dụng `WeekFields.of(firstDay, minimalDays)`.
- **Báo cáo dùng chung nhiều vùng:** lưu rõ cả quy tắc tuần trong metadata hoặc query, không chỉ lưu week number.

### Dữ liệu CLDR có thể thay đổi khi nâng JDK

`WeekFields.of(Locale)` sử dụng locale data provider của runtime. Các bản JDK có thể mang dữ liệu CLDR ở phiên bản khác, hoặc ứng dụng có runtime image chỉ chứa tập locale data đã chọn. Vì vậy:

- Kiểm thử `fw=mon` → `MONDAY` theo hợp đồng là hợp lý.
- Không nên viết test chung đòi mọi locale/provider luôn có minimalDays một con số quan sát được trên một máy.
- Nếu kết quả tuần phải bất biến trong dữ liệu lưu trữ, chọn cặp quy tắc cụ thể và lưu kèm phiên bản/chính sách khi cần.
- Khi nâng JDK hoặc thay runtime image, chạy lại integration tests địa phương hóa để phát hiện thay đổi ảnh hưởng hành vi ứng dụng.

Đừng phỏng đoán một quốc gia có ngày bắt đầu tuần cố định suốt mọi thời điểm. Nguồn quy định là bộ locale data đang được dùng hoặc chính sách sản phẩm.

## 12. Các lỗi phổ biến và cách sửa

| Giả định sai | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| `WeekFields.of(Locale)` có từ Java 10 | `WeekFields` đã có từ Java 8; Java 10 mở rộng hỗ trợ keyword `fw`/`rg` | Phân biệt tuổi API với mốc hỗ trợ extension |
| `fw=mon` luôn đồng nghĩa `WeekFields.ISO` | `fw` chỉ đặt ngày đầu tuần, không bắt buộc minimalDays=4 | Dùng `WeekFields.ISO` hoặc `of(MONDAY,4)` khi cần ISO |
| Mọi Locale bắt đầu tuần vào thứ Hai | Dữ liệu locale khác nhau | Lấy `getFirstDayOfWeek()` hoặc đặt quy tắc tường minh |
| `fw` và `rg` cùng có thì `rg` luôn thắng | Javadoc quy định `fw` ưu tiên cho first day | Dùng `fw` cho lựa chọn ngày đầu tuần rõ ràng |
| `fw` xác định ngày nghỉ cuối tuần | Nó chỉ cho biết cột đầu của tuần | Dùng dữ liệu lịch làm việc/holiday riêng |
| `fw` điều khiển múi giờ | Locale week definition độc lập `ZoneId` | Xử lý timezone riêng khi đổi LocalDate thành Instant |
| `DayOfWeek.SUNDAY.getValue()` thay đổi khi `fw=sun` | Enum DayOfWeek vẫn theo ISO: Sunday=7 | Dùng `date.get(fields.dayOfWeek())` để đọc số thứ địa phương |
| `weekOfYear()` luôn giống `weekOfWeekBasedYear()` | Trường năm lịch có thể có tuần 0; năm theo tuần có thể lệch | Đọc đúng field và ghi rõ định nghĩa |
| `YYYY-MM-dd` luôn là ngày lịch | `Y` là week-based-year theo locale | Dùng `uuuu-MM-dd` cho ngày lịch |
| `Locale.forLanguageTag` luôn validate ý nghĩa type `fw` | Nó chủ yếu diễn giải cú pháp locale tag | Kiểm type thuộc bảy giá trị đã hỗ trợ |
| Assert số tuần của locale theo CLDR cụ thể trên mọi JDK | Locale data/version/config có thể thay đổi | Test theo hợp đồng hoặc dùng WeekFields tường minh |
| Chỉ lưu số `week=1` để tra báo cáo toàn cầu | Không có firstDay/minDays và weekBasedYear | Lưu đủ định danh kỳ hoặc khoảng ngày |
| Thêm `7 × 24` giờ để có tuần tiếp theo | DST có thể làm ngày địa phương không đúng số giờ cố định | Tính trên LocalDate và ZoneId |
| Dùng java.util.Calendar cho thiết kế mới dù đã có java.time | Không tận dụng mô hình API thời gian hiện đại | Ưu tiên `WeekFields`, `LocalDate`, `ZoneId`, `DateTimeFormatter` |

## 13. Checklist thiết kế và kiểm thử

### Checklist trước khi triển khai

1. Đã xác định mục tiêu là **hiển thị lịch theo locale**, hay **tính số tuần nghiệp vụ cố định**?
2. Nếu theo người dùng, Locale có thể chứa `fw` không? Đã parse và validate bảy type ngày chưa?
3. Có cần extension `rg` không, và đã kiểm trường hợp cả `fw`/`rg` cùng tồn tại?
4. Có đang hiểu `fw` chỉ ảnh hưởng ngày đầu tuần, không tự đặt minimalDays hay weekend?
5. Đã chọn đúng `WeekFields.of(locale)`, `WeekFields.ISO` hoặc `WeekFields.of(day,minDays)`?
6. UI có dùng `fields.getFirstDayOfWeek()` để xác định thứ tự cột lịch và ngày đầu kỳ?
7. Tính số tuần có dùng đúng `weekOfWeekBasedYear` với `weekBasedYear` khi báo cáo theo week-based-year?
8. Biểu diễn ngày lịch có tránh nhầm `Y` của formatter với `u`/`y`?
9. Biên ngày đầu tuần khi truy vấn timestamp có kết hợp `ZoneId` chính xác?
10. Test có dữ liệu ranh giới đầu/cuối năm, ví dụ `2021-01-01`?
11. Các kết quả phải ổn định lâu dài có dùng cặp quy tắc tường minh thay vì phụ thuộc mặc định/JDK locale data không?
12. Khi cập nhật JDK/CLDR, đã kiểm tra lại integration tests i18n?
13. Nếu dùng thông tin week trong cache key, DB key hoặc báo cáo, đã bao gồm cả week-based-year và định nghĩa tuần?
14. Có tránh dùng một con số week để suy ra “tuần quốc tế” khi người dùng có thể đặt `fw` tùy chọn?

### Câu hỏi tự đánh giá

**Câu 1.** `WeekFields.of(Locale)` được tạo từ Java 10 đúng không?

**Đáp án:** Không. `WeekFields`/`of(Locale)` có từ Java 8. Java 10 bổ sung hỗ trợ các Unicode locale keyword như `fw` trong hành vi locale-sensitive liên quan.

**Câu 2.** `Locale.forLanguageTag("en-US-u-fw-mon")` ảnh hưởng điều gì?

**Đáp án:** `WeekFields.of(locale).getFirstDayOfWeek()` trả `MONDAY` trên Java 10+, dù locale cơ sở là en-US.

**Câu 3.** Nếu `fw=mon` thì minimalDays luôn là 4?

**Đáp án:** Không. `fw` là *first day of week*. Minimal days là tham số độc lập từ locale data; muốn ISO phải chọn `WeekFields.ISO` hoặc `of(MONDAY,4)`.

**Câu 4.** `en-US-u-fw-sat-rg-gbzzzz` bắt đầu tuần theo ngày nào?

**Đáp án:** `SATURDAY`, vì `fw` tường minh ưu tiên hơn ngày đầu tuần ngầm định của `rg`.

**Câu 5.** `Sunday.getValue()` trong enum `DayOfWeek` có thành `1` khi dùng `fw=sun`?

**Đáp án:** Không. Enum Java cố định Sunday=7. Muốn số thứ địa phương, lấy `date.get(fields.dayOfWeek())`; với Sunday-first, Chủ nhật có giá trị 1.

**Câu 6.** Tại sao `2021-01-01` có thể thuộc tuần cuối năm 2020?

**Đáp án:** Theo ISO (Monday, minimalDays=4), ngày đó nằm trong tuần 53 của **week-based-year 2020** dù năm dương lịch là 2021.

**Câu 7.** `weekOfYear()` có thể là 0 không?

**Đáp án:** Có. Những ngày đầu năm nằm trước tuần 1 theo quy tắc minimal days có thể thuộc tuần 0 của **năm lịch**.

**Câu 8.** Để lưu kỳ báo cáo ISO ổn định nên dùng gì?

**Đáp án:** `WeekFields.ISO` (Monday/4) và lưu cả week-based-year lẫn week-of-week-based-year; hoặc lưu chính xác khoảng LocalDate của kỳ theo quy tắc nghiệp vụ.

**Câu 9.** `fw` có giúp xác định cuối tuần hoặc timezone không?

**Đáp án:** Không. Đây là thiết lập đầu tuần; ngày nghỉ và múi giờ là những cấu hình khác.

**Câu 10.** `Locale.Builder.setUnicodeLocaleKeyword("fw","xyz")` có tự bảo đảm đó là ngày hợp lệ không?

**Đáp án:** Không nên dựa vào Builder cho validation ngữ nghĩa của mọi Unicode key/type. App cần kiểm rằng `fw` thuộc `mon,tue,wed,thu,fri,sat,sun`.

## 14. Nguồn chính thức còn áp dụng hiện nay

- [Oracle Java SE 17 — WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html): đặc tả `WeekFields.of(Locale)`, hai tham số của tuần, `fw`/`rg` và thứ tự ưu tiên, các TemporalField.
- [Oracle Java SE 25 — WeekFields](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html): xác nhận API/Unicode extension vẫn được hỗ trợ ở các JDK mới.
- [Oracle JDK 10 — Internationalization Enhancements](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): hỗ trợ bổ sung `fw`, `rg` và những extension khác từ Java 10.
- [OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314): mốc và mục tiêu mở rộng các keyword Unicode locale trong Java 10.
- [Oracle Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): BCP 47, `forLanguageTag`, `getUnicodeLocaleType` và sự khác nhau giữa cú pháp với hỗ trợ ngữ nghĩa.
- [Oracle Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): `setUnicodeLocaleKeyword` và quy tắc tạo Locale.
- [Oracle Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): ký hiệu `Y`, `w`, `e`, `u`, `y` và cách định dạng ngày/tuần.
- [Oracle Java SE 17 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): xây formatter với `TemporalField` cụ thể.
- [Oracle Java SE 17 — TemporalAdjusters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html): `previousOrSame` cho ngày đầu tuần.
- [Unicode CLDR / UTS #35 — Dates, first-day overrides](https://www.unicode.org/reports/tr35/tr35-dates.html): quy tắc locale tuần và các override `fw` / `rg`.

**Ghi nhớ:** `WeekFields.of(Locale)` lấy định nghĩa tuần từ Locale. Từ Java 10, Unicode extension `fw` cho phép ghi đè **ngày đầu tuần** như `en-US-u-fw-mon`, và `fw` ưu tiên hơn `rg` khi cả hai cùng có mặt. **Không đồng nhất `fw=mon` với ISO**: ngày đầu tuần và số ngày tối thiểu ở tuần thứ nhất là **hai tham số riêng**. Hãy dùng `WeekFields.ISO` cho chuẩn ISO cố định, dùng `WeekFields.of(locale)` cho giao diện theo người dùng, và kiểm thử ranh giới đầu/cuối năm khi tính số tuần.