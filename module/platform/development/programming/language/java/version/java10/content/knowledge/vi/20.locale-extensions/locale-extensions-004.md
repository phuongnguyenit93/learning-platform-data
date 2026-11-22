# Java 10 – Mở rộng Locale: Khóa fw cho ngày đầu tuần

> **Phạm vi:** Java 10 → **Mở rộng Locale** → **Khóa fw cho ngày đầu tuần**. Bài này trình bày Unicode locale extension **fw** (*first day of week*), cách nó được Java 10 hỗ trợ và cách sử dụng an toàn với `java.util.Locale`, `java.time.temporal.WeekFields`, `java.time.DayOfWeek` và `java.time.LocalDate` trên Java 17+ cùng các JDK hiện đại. Không dựa vào API lỗi thời hay những chi tiết nội bộ của một bản JDK. Chương trình Java hoàn chỉnh đã được biên dịch với `javac --release 17` và kiểm tra output.

## 1. Mục tiêu và ý nghĩa thực tế

Sau bài học, bạn có thể:

1. Giải thích `fw` là **Unicode locale key** quy định **ngày đầu tuần mong muốn** khi hiển thị hoặc tính toán tuần theo locale.
2. Đọc language tag như `en-US-u-fw-mon` và chỉ ra đâu là ngôn ngữ, khu vực, Unicode extension key và giá trị.
3. Biết bảy giá trị chuẩn `mon`, `tue`, `wed`, `thu`, `fri`, `sat` và `sun`.
4. Tạo Locale có `fw` bằng `Locale.forLanguageTag` hoặc `Locale.Builder.setUnicodeLocaleKeyword`; đọc lại bằng `getUnicodeLocaleType("fw")`.
5. Dùng `WeekFields.of(locale).getFirstDayOfWeek()` để lấy `DayOfWeek` được locale quy định.
6. Tạo lưới lịch và tính **ngày bắt đầu tuần chứa một ngày cụ thể** với `TemporalAdjusters.previousOrSame`.
7. Phân biệt **ngày đầu tuần** với **ngày đầu tiên đi làm** hay **ngày cuối tuần**; `fw` không định nghĩa weekend/work schedules.
8. Hiểu mức ưu tiên giữa `fw` và Unicode region override `rg`, không nhầm locale mở rộng với việc đổi country/language.
9. Phân biệt `fw-mon` với **ISO-8601 week rules**: chỉ đổi ngày đầu tuần không đồng nghĩa quy tắc **ít nhất bốn ngày trong tuần đầu của năm**.
10. Phân biệt thứ tự/ngày trong tuần theo locale với giá trị ISO cố định của `DayOfWeek.getValue()` và `ChronoField.DAY_OF_WEEK`.
11. Dùng `DateTimeFormatter`/`WeekFields` đúng khi format day-of-week hoặc week-based-year theo vùng.
12. Validate giá trị `fw` từ cấu hình/người dùng, tránh coi “tag đúng cú pháp” là “day code hợp lệ về ngữ nghĩa”.
13. Thiết kế API tường minh, không sửa `Locale.setDefault` toàn JVM chỉ để điều chỉnh cách hiển thị lịch cho một người dùng.
14. Viết bài test ổn định dù dữ liệu locale/CLDR mặc định có thể cập nhật qua phiên bản JDK.

**Kết luận nhanh:** Trong một Locale như `en-US-u-fw-mon`, `fw=mon` yêu cầu thứ Hai là ngày đầu tuần, dù dữ liệu vùng `US` thường có ngày đầu tuần là Chủ nhật. Với Java hiện đại, lấy kết quả bằng `WeekFields.of(locale).getFirstDayOfWeek()`; nếu bài toán cần **cố định cả quy tắc đánh số tuần**, chỉ rõ thêm `minimalDaysInFirstWeek` bằng `WeekFields.of(DayOfWeek, int)`.

## 2. Bối cảnh Java 10 và chuẩn Unicode locale extension

Java từ lâu dùng `Locale` để diễn đạt ngôn ngữ/khu vực cho định dạng ngày, số và chuỗi. Chuẩn IETF BCP 47 cho phép gắn **extension** để mô tả các tùy chọn địa phương hóa cụ thể.

Java 10 mở rộng mức hỗ trợ của các API liên quan đối với bốn Unicode locale keywords:

| Khóa | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `cu` | Currency type | `en-US-u-cu-eur` |
| **`fw`** | **First day of week** | **`en-US-u-fw-mon`** |
| `rg` | Region override | `en-US-u-rg-gbzzzz` |
| `tz` | Time zone theo Unicode locale type | `en-US-u-tz-usnyc` |

Đây là **bối cảnh** của tính năng Java 10; bài này tập trung vào `fw`. Không nhầm `fw` với tính năng `var`, với thứ/ngày được viết bằng tiếng nào, hay với timezone của thời điểm thực. `fw` là một **tùy chọn ưu tiên địa phương hóa về ranh giới tuần**.

Oracle *Internationalization Enhancements in JDK 10* và Javadoc `WeekFields.of(Locale)` xác nhận khả năng hỗ trợ này. Unicode CLDR/UTS #35 quy định tập giá trị và ý nghĩa của `fw`.

### 2.1. Cấu trúc một language tag có `fw`

~~~text
en-US-u-fw-mon
│  │  │ │  └── mon: thứ Hai
│  │  │ └───── fw: first day of week
│  │  └─────── u: Unicode locale extension
│  └────────── US: vùng Hoa Kỳ
└───────────── en: ngôn ngữ English
~~~

Một Locale với tag này vẫn có:

- Language là `en`.
- Country/region gốc là `US`.
- Unicode extension `u`.
- Unicode keyword `fw` mang type `mon`.

`fw` **không thay** region `US` bằng region khác; nó thêm một **override có phạm vi** đến những API có sử dụng dữ liệu ngày đầu tuần.

~~~java
import java.util.Locale;

Locale custom = Locale.forLanguageTag("en-US-u-fw-mon");

System.out.println(custom.getLanguage());             // en
System.out.println(custom.getCountry());              // US
System.out.println(custom.getUnicodeLocaleType("fw")); // mon
System.out.println(custom.toLanguageTag());           // en-US-u-fw-mon
~~~

Đây là đoạn code minh họa trong phương thức; ví dụ độc lập ở phần 15 kiểm tra cùng các thuộc tính.

### 2.2. Vì sao không đổi luôn quốc gia để đổi đầu tuần?

Một người có thể muốn giao diện tiếng Anh và định dạng theo vùng US nhưng lịch bắt đầu thứ Hai. Nếu chỉ đổi `en-US` thành `en-GB` để có thứ Hai, ứng dụng có thể vô tình đổi **những quy tắc vùng khác** như cách hiển thị ngày, số, tiền tệ hoặc quy ước khác.

`fw` cho phép **chỉ mô tả sở thích ngày đầu tuần**. Đây là lý do Unicode locale extensions hữu ích: tránh đổi cả vùng khi chỉ muốn một thuộc tính địa phương hóa.

## 3. Bảy giá trị hợp lệ của Unicode keyword `fw`

Theo Unicode CLDR, khóa `fw` có bảy type tiêu chuẩn:

| `fw` type | `DayOfWeek` của Java | Tiếng Việt | Giá trị ISO `DayOfWeek.getValue()` |
| --- | --- | --- | --- |
| `mon` | `MONDAY` | Thứ Hai | 1 |
| `tue` | `TUESDAY` | Thứ Ba | 2 |
| `wed` | `WEDNESDAY` | Thứ Tư | 3 |
| `thu` | `THURSDAY` | Thứ Năm | 4 |
| `fri` | `FRIDAY` | Thứ Sáu | 5 |
| `sat` | `SATURDAY` | Thứ Bảy | 6 |
| `sun` | `SUNDAY` | Chủ nhật | 7 |

Các giá trị này là **mã ngày trong Unicode locale tag**, không phải giá trị `1..7` truyền trực tiếp vào tag.

Ví dụ:

~~~text
vi-VN-u-fw-mon    // giao diện/ngữ cảnh Việt Nam; lịch bắt đầu thứ Hai
en-US-u-fw-mon    // ngôn ngữ và vùng US; lịch bắt đầu thứ Hai
fr-FR-u-fw-sun    // vùng Pháp; lịch bắt đầu Chủ nhật
en-US-u-fw-sat    // vùng US; lịch bắt đầu thứ Bảy
en-US-u-fw-wed    // ngày đầu tuần là thứ Tư nếu ứng dụng yêu cầu
~~~

**Không giới hạn `fw` chỉ ở `mon` và `sun`.** Cả bảy ngày đều có mã chuẩn; ứng dụng có thể cho người dùng tùy chọn bất kỳ ngày nào. Điều này **không có nghĩa** mọi ngày đều là mặc định của một quốc gia cụ thể; nó là một tùy chọn hiển thị/định nghĩa đầu tuần.

### 3.1. Mã ngày không phải mã ngôn ngữ

`fw-mon` không phải tiếng Mông Cổ, `fw-sun` không phải tùy chọn bật ngày nghỉ. Chúng chỉ là keyword type mang nghĩa **Monday/Sunday**. Ngày đầu tuần có thể khác ngày đầu lịch làm việc và khác tập ngày nghỉ cuối tuần. Không suy diễn các quy tắc nhân sự từ `fw`.

## 4. API chính: `WeekFields.of(Locale)`

Trong `java.time.temporal.WeekFields`:

~~~java
static WeekFields of(Locale locale)
DayOfWeek getFirstDayOfWeek()
int getMinimalDaysInFirstWeek()
~~~

Cách dùng:

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

Locale enWithMonday = Locale.forLanguageTag("en-US-u-fw-mon");
DayOfWeek start = WeekFields.of(enWithMonday).getFirstDayOfWeek();

System.out.println(start); // MONDAY
~~~

Java SE 17 Javadoc quy định `WeekFields.of(Locale)` tra cứu dữ liệu địa phương hóa, nhận biết `fw` và `rg`. Nếu cả hai có mặt, **`fw` ghi đè ngày đầu tuần suy ra từ `rg`**.

### 4.1. Tại sao dùng `WeekFields` thay vì tự kiểm tra chuỗi trong mọi view?

Một cách dễ mắc lỗi:

~~~java
// Đừng hard-code chính sách ngày đầu tuần kiểu:
boolean startMonday = locale.getCountry().equals("VN");
~~~

Nó bỏ qua:

- Quy tắc locale dựa trên CLDR và provider.
- Trường hợp người dùng đã gắn `-u-fw-sun`.
- Trường hợp region override `-u-rg-...`.
- Locale không có region rõ ràng.
- Những thay đổi dữ liệu địa phương hóa giữa phiên bản runtime.

`WeekFields.of(locale)` là cầu nối được API định nghĩa để lấy ngày đầu tuần **phù hợp với Locale đang chọn**. Ứng dụng nên chuyển từ result `DayOfWeek` sang cách sắp xếp lịch, thay vì lập bảng hard-code theo country code.

### 4.2. `WeekFields` có hai tham số, không chỉ một

Một tuần được xác định bởi:

1. **First day of week:** ngày nào mở đầu chu kỳ bảy ngày.
2. **Minimal days in first week:** cần ít nhất bao nhiêu ngày của năm/tháng mới để tính tuần chứa những ngày ấy là tuần số 1.

Ví dụ:

~~~java
WeekFields local = WeekFields.of(enWithMonday);
System.out.println(local.getFirstDayOfWeek());       // MONDAY
System.out.println(local.getMinimalDaysInFirstWeek()); // 1 trên JDK/CLDR dùng trong demo
~~~

`fw=mon` đặt **tham số thứ nhất**, không tự ép **tham số thứ hai** thành 4. Vì vậy `en-US-u-fw-mon` **không tự động tương đương `WeekFields.ISO`**.

## 5. `fw` và mặc định theo vùng

Không có `fw`, kết quả thường lấy từ dữ liệu locale dựa trên khu vực:

~~~java
Locale us = Locale.forLanguageTag("en-US");
Locale usMonday = Locale.forLanguageTag("en-US-u-fw-mon");

System.out.println(WeekFields.of(us).getFirstDayOfWeek());
// SUNDAY trong môi trường CLDR đã kiểm thử

System.out.println(WeekFields.of(usMonday).getFirstDayOfWeek());
// MONDAY vì có override fw=mon
~~~

Dữ liệu locale đi kèm runtime hoặc provider có thể được cập nhật. Vì vậy:

- Không nên viết nghiệp vụ quan trọng dựa trên **country defaults** không được version/control nếu kết quả phải ổn định tuyệt đối.
- Khi người dùng chỉ có một sở thích “thứ Hai bắt đầu tuần”, dùng `fw-mon` để truyền sở thích đó rõ ràng.
- Với báo cáo có yêu cầu chuẩn cố định, dùng `WeekFields.of(DayOfWeek, minimalDays)` thay vì chỉ dựa vào defaults của CLDR.
- Khi cần hiển thị địa phương hóa cho người dùng và không có override, lấy `WeekFields.of(locale)` từ runtime là giải pháp hợp lý.

### 5.1. Locale riêng không làm thay đổi global default

~~~java
var userLocale = Locale.forLanguageTag("en-US-u-fw-mon");
var userWeeks = WeekFields.of(userLocale);
~~~

Tạo `userLocale` chỉ tạo một giá trị Locale mới. Nó **không gọi `Locale.setDefault`**, không tác động global default của toàn JVM.

Trong một web application có nhiều user, nên chuyển `Locale` vào phương thức/render service theo request hoặc profile. Tránh gọi `Locale.setDefault(...)` mỗi khi một người thay tùy chọn lịch; thay đổi default toàn tiến trình có thể ảnh hưởng request khác.

## 6. Khi có thêm `rg`: khóa nào được ưu tiên?

`rg` là Unicode **region override**; type có dạng vùng kèm hậu tố theo chuẩn, ví dụ `gbzzzz` cho vùng GB. Nó có thể ảnh hưởng các quy tắc dựa trên region, bao gồm ngày đầu tuần và minimal days.

### 6.1. Chỉ có `rg`

~~~java
var locale = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
var weeks = WeekFields.of(locale);

System.out.println(weeks.getFirstDayOfWeek()); // MONDAY ở JDK đã kiểm thử
System.out.println(weeks.getMinimalDaysInFirstWeek()); // 4 ở JDK đã kiểm thử
~~~

Mặc dù Locale vẫn có region chính `US`, `rg-gbzzzz` yêu cầu các quy tắc vùng có thể ưu tiên GB trong các API hỗ trợ.

### 6.2. Có cả `fw` và `rg`

~~~java
var locale = Locale.forLanguageTag(
        "en-US-u-fw-sat-rg-gbzzzz");
var weeks = WeekFields.of(locale);

System.out.println(weeks.getFirstDayOfWeek());       // SATURDAY
System.out.println(weeks.getMinimalDaysInFirstWeek()); // 4 ở JDK đã kiểm thử
~~~

**Quy tắc Java SE:** Khi có cả `fw` và `rg`, **`fw` có ưu tiên cao hơn đối với ngày đầu tuần**. Điều này không có nghĩa toàn bộ thông số của `rg` bị xóa.

Trong ví dụ:

- `fw-sat` → đầu tuần là thứ Bảy.
- `rg-gbzzzz` → dữ liệu vùng GB vẫn có thể chi phối các thông số khác, chẳng hạn `minimalDaysInFirstWeek`.
- Kết quả `SATURDAY` + `4` là một tổ hợp hoàn toàn có thể xảy ra.

### 6.3. Mức ưu tiên theo Unicode CLDR

Đối với **ngày đầu tuần**, chuẩn Unicode CLDR mô tả thứ tự xem xét các gợi ý như `fw` trước, rồi `rg`, sau đó các nguồn dữ liệu thích hợp khác. Với Java, điều cần dựa trực tiếp là lời hứa trong Javadoc `WeekFields.of(Locale)`: **`fw` thắng quy tắc ngầm từ `rg`**.

Không tự đặt cách ưu tiên khác chỉ vì code của bạn nhìn thấy country `US`. Cũng không suy diễn rằng `fw` sẽ override múi giờ, lịch làm việc hoặc cách hiển thị currency.

## 7. Ngày đầu tuần khác quy tắc đánh số tuần ISO-8601

Đây là bẫy kỹ thuật quan trọng nhất của đề mục.

### 7.1. ISO-8601 định nghĩa cả hai yếu tố

`WeekFields.ISO` tương ứng:

- `DayOfWeek.MONDAY`: bắt đầu tuần thứ Hai.
- `minimalDaysInFirstWeek = 4`: tuần số 1 phải chứa ít nhất bốn ngày của năm/tháng mới theo quy tắc tương ứng.

~~~java
WeekFields iso = WeekFields.ISO;
System.out.println(iso.getFirstDayOfWeek());       // MONDAY
System.out.println(iso.getMinimalDaysInFirstWeek()); // 4
~~~

Ngược lại, với locale US có `fw-mon`, trong môi trường đã kiểm thử:

~~~java
WeekFields usMonday =
        WeekFields.of(Locale.forLanguageTag("en-US-u-fw-mon"));

System.out.println(usMonday.getFirstDayOfWeek());       // MONDAY
System.out.println(usMonday.getMinimalDaysInFirstWeek()); // 1
~~~

Cả hai cùng bắt đầu thứ Hai, nhưng **tuần đầu của năm có thể được gán nhãn khác nhau**. Không dùng `fw-mon` làm viết tắt của “tuần ISO” trong báo cáo tài chính, xuất dữ liệu hoặc nghiệp vụ yêu cầu ISO week date.

### 7.2. Ví dụ ngày 1/1/2021

`2021-01-01` là thứ Sáu.

- Theo `WeekFields.ISO`, nó nằm trong **tuần 53 của week-based-year 2020**.
- Với `en-US-u-fw-mon` và quy tắc minDays=1 trong môi trường đã kiểm thử, nó thuộc **tuần 1**.

~~~java
var date = java.time.LocalDate.of(2021, 1, 1);
var locale = Locale.forLanguageTag("en-US-u-fw-mon");

int localWeek = date.get(
        WeekFields.of(locale).weekOfWeekBasedYear());
int isoWeek = date.get(WeekFields.ISO.weekOfWeekBasedYear());
int isoWeekYear = date.get(WeekFields.ISO.weekBasedYear());

System.out.println(localWeek);    // 1
System.out.println(isoWeek);      // 53
System.out.println(isoWeekYear);  // 2020
~~~

Đừng chỉ lưu số tuần `53` mà không kèm **week-based-year** hoặc bộ quy tắc. Ngay gần ranh giới năm, week-based-year có thể khác calendar year.

### 7.3. Khi muốn cố định quy tắc kinh doanh

~~~java
WeekFields businessWeeks =
        WeekFields.of(DayOfWeek.MONDAY, 4);
~~~

Ở đây ứng dụng **chủ động chọn** Monday + 4, không cần dữ liệu vùng đang thay đổi. API kiểm tra `minimalDays` từ 1 đến 7; giá trị ngoài khoảng sẽ ném `IllegalArgumentException`.

Nếu business nói “tuần của chúng tôi bắt đầu thứ Hai, tuần đầu phải có ít nhất bốn ngày của năm”, sử dụng object này hoặc `WeekFields.ISO`. Nếu business nói “lịch hiển thị theo sở thích của người dùng”, dùng `WeekFields.of(userLocale)`.

## 8. `DayOfWeek` ISO khác đánh số ngày theo locale

Một ngày `LocalDate` không thay đổi chỉ vì đổi Locale. Ngày Chủ nhật 2024-01-07 vẫn là Chủ nhật.

~~~java
var sunday = java.time.LocalDate.of(2024, 1, 7);
System.out.println(sunday.getDayOfWeek()); // SUNDAY
System.out.println(sunday.getDayOfWeek().getValue()); // 7
~~~

`DayOfWeek.getValue()` và `ChronoField.DAY_OF_WEEK` luôn dùng quy ước ISO: Monday=1 … Sunday=7. `fw` không sửa enum hoặc những con số ISO này.

Tuy nhiên, `WeekFields.dayOfWeek()` là **TemporalField theo locale**:

~~~java
var us = Locale.forLanguageTag("en-US");
var monStart = Locale.forLanguageTag("en-US-u-fw-mon");

System.out.println(sunday.get(WeekFields.of(us).dayOfWeek()));
// 1 vì Sunday là ngày đầu tuần của en-US mặc định trong môi trường thử

System.out.println(sunday.get(WeekFields.of(monStart).dayOfWeek()));
// 7 vì tuần bắt đầu Monday, Sunday là ngày thứ bảy trong tuần đó
~~~

### 8.1. Hai hệ đánh số cho cùng một ngày

| Ngữ cảnh | Giá trị của Sunday 2024-01-07 |
| --- | --- |
| `DayOfWeek.getValue()` | `7` |
| `ChronoField.DAY_OF_WEEK` | `7` |
| `WeekFields.of(en-US).dayOfWeek()` | `1` trong dữ liệu US đã thử |
| `WeekFields.of(en-US-u-fw-mon).dayOfWeek()` | `7` |
| `WeekFields.of(en-US-u-fw-sat-rg-gbzzzz).dayOfWeek()` | `2` |

**Không gán giá trị localized `1..7` vào một API đang mong ISO `DayOfWeek.of(1)` mà không chuyển đổi đúng.** Ví dụ nếu một calendar view đánh số Sunday=1 mà nghiệp vụ gọi `DayOfWeek.of(1)`, kết quả lại là Monday.

Khi cần giữ dữ liệu ổn định trong database/API, nên lưu một representation được định nghĩa rõ, ví dụ ISO weekday (1=Monday) hoặc tên enum; chỉ dùng localized numbering ở tầng trình bày hoặc một giao thức có schema tường minh.

## 9. Tạo lịch và tính ngày bắt đầu tuần của một ngày bất kỳ

Mục đích phổ biến nhất của `fw` là hiển thị lưới lịch bắt đầu từ ngày mà người dùng thích.

### 9.1. Tìm thứ/ngày mở đầu tuần chứa một ngày

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.Locale;

static LocalDate startOfWeek(LocalDate date, Locale locale) {
    DayOfWeek firstDay = WeekFields.of(locale).getFirstDayOfWeek();
    return date.with(TemporalAdjusters.previousOrSame(firstDay));
}
~~~

Đây là **phương thức mẫu** nằm trong class. `previousOrSame(firstDay)` trả lại chính ngày đầu tuần nếu `date` đã đúng thứ, nếu không sẽ lui về lần gần nhất của thứ đó.

Với `date = 2024-01-07` (Chủ nhật):

| Locale | Bắt đầu tuần | Ngày đầu tuần chứa 2024-01-07 |
| --- | --- | --- |
| `en-US` mặc định trong JDK thử | Sunday | `2024-01-07` |
| `en-US-u-fw-mon` | Monday | `2024-01-01` |
| `en-US-u-fw-sat-rg-gbzzzz` | Saturday | `2024-01-06` |

Việc chọn đầu tuần **không đổi ngày giờ thực hoặc múi giờ**. Nếu user cung cấp `Instant`, phải chuyển `Instant` sang `LocalDate` trong `ZoneId` phù hợp **trước khi** tính tuần của user; `fw` không quyết định múi giờ.

### 9.2. Tạo thứ tự tiêu đề cột cho lưới lịch

~~~java
DayOfWeek first = WeekFields.of(locale).getFirstDayOfWeek();

var headerDays = java.util.stream.IntStream.range(0, 7)
        .mapToObj(i -> first.plus(i))
        .toList(); // Java 16+
~~~

`DayOfWeek.plus` xoay tuần theo bảy ngày, nên:

- `fw-mon` → Monday, Tuesday, …, Sunday.
- `fw-sun` → Sunday, Monday, …, Saturday.
- `fw-wed` → Wednesday, Thursday, …, Tuesday.

Để hiển thị tên thứ bằng ngôn ngữ của user:

~~~java
var labels = headerDays.stream()
        .map(d -> d.getDisplayName(
                java.time.format.TextStyle.SHORT, locale))
        .toList();
~~~

`fw` chọn **thứ tự**, còn `locale`/dữ liệu ngôn ngữ chọn **tên được trình bày**. Không hard-code tên tiếng Anh hay một bảng cố định Mon→Sun cho mọi locale.

### 9.3. Những điểm cần chú ý khi dựng lưới tháng

- Tháng có ngày đầu và cuối không trùng ranh giới tuần; lưới thường cần thêm các ô của tháng trước/sau.
- `startOfWeek(firstDayOfMonth, locale)` cho biết ô đầu của lưới nếu mỗi hàng có bảy ô.
- Có thể dùng `LocalDate.plusDays(1)` để duyệt từng ô; không tính bằng cộng mili-giây cố định vì ngày giờ với timezone/DST là chủ đề khác.
- Nếu giao diện hiển thị **số tuần**, phải thống nhất thêm `minimalDaysInFirstWeek` và week-based-year; chỉ `fw` chưa đủ.
- Nếu tính thời gian công việc theo giờ địa phương, cần thêm `ZoneId`; `Locale` không thay thế timezone.

## 10. Khóa `fw` tác động đến DateTimeFormatter đến đâu?

`java.time.format.DateTimeFormatter` hỗ trợ một số pattern **localized** cho ngày/thứ/tuần:

- `e`/`c` liên quan đến dạng ngày trong tuần theo locale (số hoặc text tùy số lượng ký tự/pattern).
- `E` thường dùng tên thứ theo locale.
- `Y` liên quan đến week-based-year theo quy tắc tuần được locale xác định; khác `y` là year-of-era.

Ví dụ:

~~~java
var sunday = java.time.LocalDate.of(2024, 1, 7);
var locale = Locale.forLanguageTag("en-US-u-fw-mon");

var numeric = java.time.format.DateTimeFormatter.ofPattern("e", locale);
System.out.println(sunday.format(numeric)); // 7 trên JDK thử
~~~

Ở đây `e` một ký tự dùng localized day-of-week numbering: Sunday là ngày thứ bảy nếu tuần bắt đầu Monday. `DateTimeFormatter.ofPattern("E", locale)` diễn đạt **tên thứ**, không có nghĩa Locale làm cho Sunday biến thành Monday.

### 10.1. Tránh nhầm `Y` với `y`

Khi tuần đầu năm phụ thuộc `fw` và `minimalDaysInFirstWeek`, `weekBasedYear` có thể khác năm dương lịch ở đầu/cuối năm. Do đó:

- Với date string theo lịch, dùng pattern/năm phù hợp với yêu cầu, thường `uuuu` cho proleptic-year khi cần technical date và các pattern ngày/tháng chính xác.
- Với ISO week date, dùng `WeekFields.ISO` và các API dành cho week-based-year.
- Không dùng `YYYY-MM-dd` như một công thức mặc định cho ngày tháng thông thường; `Y` là week-based-year, có thể tạo năm bất ngờ gần 1/1.

Nếu người dùng cần đúng chuẩn ISO-8601 week calendar, đừng nghĩ `fw-mon` tự đặt `minimalDays=4`; nó không làm việc đó.

### 10.2. Không tự nhận mọi định dạng ngày đều đổi vì `fw`

`fw` có ý nghĩa với **những API dùng dữ liệu định nghĩa tuần**. Nó không nhất thiết làm tất cả format text ngày, tên tháng, kiểu ngày/giờ, lịch làm việc hay công cụ bên thứ ba thay đổi. Đừng thử một pattern format không liên quan rồi kết luận Locale fw “không hoạt động”. Hãy kiểm tra trực tiếp `WeekFields.of(locale)`.

## 11. Tạo Locale có `fw` bằng Java API

Có hai cách chính, đều phù hợp Java 17+.

### 11.1. `Locale.forLanguageTag` khi có BCP 47 tag

~~~java
Locale monday = Locale.forLanguageTag("en-US-u-fw-mon");
Locale saturday = Locale.forLanguageTag("en-US-u-fw-sat");
Locale frenchSunday = Locale.forLanguageTag("fr-FR-u-fw-sun");
~~~

Đây là cách dễ dùng khi nhận tag đã được chuẩn hóa từ profile, HTTP header hoặc một nguồn cấu hình đáng tin. Dùng `getUnicodeLocaleType("fw")` để xem type đang được giữ:

~~~java
System.out.println(monday.getUnicodeLocaleType("fw")); // mon
~~~

`Locale.forLanguageTag` là parser language tag, **không phải bộ xác thực tất cả các giá trị Unicode keyword có đúng nghĩa CLDR hay không**. Với input không đáng tin, cần validate business codes.

### 11.2. `Locale.Builder.setUnicodeLocaleKeyword` khi có Locale gốc

~~~java
Locale configured = new Locale.Builder()
        .setLocale(Locale.US)
        .setUnicodeLocaleKeyword("fw", "wed")
        .build();

System.out.println(configured.toLanguageTag()); // en-US-u-fw-wed
System.out.println(WeekFields.of(configured).getFirstDayOfWeek());
// WEDNESDAY
~~~

Ưu điểm:

- Giữ language/region và những thuộc tính đã có trong `baseLocale`.
- Bổ sung hoặc thay riêng Unicode keyword `fw`.
- Kiểm tra **cú pháp** của key/type.
- Có thể bỏ một keyword bằng cách đặt type là `null`.

~~~java
Locale withoutOverride = new Locale.Builder()
        .setLocale(configured)
        .setUnicodeLocaleKeyword("fw", null)
        .build();

System.out.println(withoutOverride.getUnicodeLocaleType("fw") == null);
// true
~~~

**Không nhầm với `setExtension('u', ...)`**: method đó thay cả extension `u`, có thể làm mất những Unicode keywords khác nếu không ghép lại đúng. Khi chỉ muốn sửa một keyword, `setUnicodeLocaleKeyword("fw", value)` rõ ràng hơn.

### 11.3. Không tùy tiện gọi `setDefault`

`Locale.setDefault` thay đổi cài đặt mặc định ở phạm vi JVM và dễ ảnh hưởng request khác trong dịch vụ multi-tenant. Thay vì vậy, nhận hoặc lưu `Locale` riêng của user/request và truyền nó đến `WeekFields.of`, `DateTimeFormatter` và UI rendering logic.

Nếu cần lấy mặc định locale cho formatting, `Locale.getDefault(Locale.Category.FORMAT)` có thể phù hợp ở ranh giới giao diện; nhưng lựa chọn riêng của user vẫn nên được truyền tường minh, không dùng global mutation như cơ chế request-scoped.

## 12. Phân biệt **hợp lệ về cú pháp** và **hợp lệ về ngữ nghĩa**

Đây là vấn đề cần đặc biệt chú ý khi giá trị `fw` đến từ user input.

`Locale.Builder` kiểm tra tính *well-formed* theo BCP 47, nhưng **không tra danh sách các giá trị được đăng ký cho mọi Unicode keyword** để khẳng định type đó đúng nghĩa.

Ví dụ đã chạy:

~~~java
Locale unusual = new Locale.Builder()
        .setLocale(Locale.US)
        .setUnicodeLocaleKeyword("fw", "xyz")
        .build();

System.out.println(unusual.getUnicodeLocaleType("fw")); // xyz
~~~

`xyz` gồm ba ký tự chữ nên có thể đạt kiểm tra **cú pháp type**, nhưng **không nằm trong bảy giá trị ngày đầu tuần chuẩn** của `fw`. Đừng dựa vào việc Builder chấp nhận chuỗi đó để coi nó là lựa chọn hợp lệ của người dùng.

Nếu type sai **cú pháp**, ví dụ chứa ký tự `!`:

~~~java
try {
    new Locale.Builder().setLanguage("en")
            .setUnicodeLocaleKeyword("fw", "m!");
} catch (java.util.IllformedLocaleException expected) {
    System.out.println("invalid syntax");
}
~~~

Hãy phân biệt:

- **Sai cú pháp:** Builder ném `IllformedLocaleException`.
- **Đúng cú pháp nhưng không được đăng ký:** Builder vẫn có thể chấp nhận, như `xyz`.
- **Được đăng ký:** một trong `mon` đến `sun` theo danh sách chính xác, không đoán.
- **Kết quả fallback khi type không được hỗ trợ:** có thể phụ thuộc dữ liệu/provider; không dựa vào để xử lý lỗi input.

### 12.1. Validate bảy mã trước khi tạo Locale

~~~java
private static final java.util.Set<String> VALID_FW =
        java.util.Set.of("mon", "tue", "wed", "thu",
                         "fri", "sat", "sun");

static Locale withFirstDay(Locale base, String requestedFw) {
    java.util.Objects.requireNonNull(base, "base");
    java.util.Objects.requireNonNull(requestedFw, "requestedFw");

    String code = requestedFw.toLowerCase(Locale.ROOT);
    if (!VALID_FW.contains(code)) {
        throw new IllegalArgumentException(
                "Invalid first-day code: " + requestedFw);
    }
    return new Locale.Builder()
            .setLocale(base)
            .setUnicodeLocaleKeyword("fw", code)
            .build();
}
~~~

Đây là hai thành viên **minh họa đặt bên trong class**, không phải ứng dụng main độc lập. `Locale.ROOT` chỉ dùng để normalize **mã ASCII kỹ thuật**; với input locale từ một parser không tin cậy, có thể cần thêm chính sách khoảng trắng/canonical casing/bảo vệ kích thước. Không tự strip/tự sửa mã sai ngoài phạm vi spec nếu API yêu cầu chỉ nhận mã chính xác.

Với API business, có thể trả 400/validation error khi `requestedFw` không thuộc allowlist thay vì âm thầm dùng default làm người dùng khó hiểu.

## 13. Khóa `fw` **không** quyết định điều gì?

### 13.1. Không xác định ngày nghỉ cuối tuần

Unicode CLDR có dữ liệu **weekend start/end** riêng. Ngày bắt đầu hiển thị tuần là một thông tin khác với:

- Người dùng có làm việc thứ Bảy/Chủ nhật hay không.
- Quốc gia có ngày nghỉ lễ hay không.
- Ngày bắt đầu tuần làm việc của tổ chức.
- Quy tắc tính SLA, số ngày làm việc hoặc lịch giao hàng.
- Ngày nào trong tuần dùng để chạy batch job.

Ví dụ người dùng có `fw-mon` vẫn có thể làm việc từ thứ Ba đến thứ Bảy. Đừng tính business days bằng phép thử “ngày có localized index 1..5” mà chưa có lịch làm việc và holidays của hệ thống.

### 13.2. Không thay múi giờ

`Locale.forLanguageTag("en-US-u-fw-mon")` không đặt `ZoneId`. Nếu hệ thống nhận `Instant`, date địa phương phụ thuộc timezone:

~~~java
java.time.Instant instant = java.time.Instant.parse(
        "2024-01-07T00:30:00Z");
java.time.LocalDate date = instant.atZone(
        java.time.ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();

DayOfWeek first = WeekFields.of(
        Locale.forLanguageTag("vi-VN-u-fw-mon"))
        .getFirstDayOfWeek();
~~~

Đây là đoạn code minh họa. `ZoneId` quyết định một instant rơi vào **ngày địa phương nào**; `fw` quyết định **ngày nào mở đầu tuần chứa ngày địa phương ấy**. Đừng dùng `fw` thay cho timezone hoặc ngày đầu của giờ giao dịch.

### 13.3. Không đổi ngày thực hoặc giá trị ISO của weekday

Dùng `fw-sat` không làm `LocalDate.of(2024,1,7)` trở thành thứ Bảy. Nó vẫn là Sunday; chỉ là Sunday được tính như **ngày thứ hai của tuần bắt đầu Saturday** khi dùng `WeekFields.dayOfWeek()`. Các thuật toán cần giá trị ISO vẫn dùng `DayOfWeek.getValue()`/`ChronoField.DAY_OF_WEEK`.

### 13.4. Không bảo đảm mọi thư viện thứ ba hiểu `fw`

Một thư viện calendar UI tự có tùy chọn `firstDayOfWeek` riêng có thể **không đọc** BCP47 Unicode extension của Locale Java. Khi tích hợp, chuyển `WeekFields.of(locale).getFirstDayOfWeek()` sang enum/code mà thư viện đó yêu cầu. Không cho rằng chỉ cần gắn `-u-fw-mon` là mọi hệ thống từ Java đến frontend tự đồng bộ.

## 14. Chương trình Java 17+ đầy đủ đã kiểm thử

Chương trình kiểm tra cả region default, `fw`, `rg`, cách tạo bằng Builder, localized numbering, đầu tuần của một ngày, tuần ISO và phân biệt syntax/semantics của mã `fw`.

Lưu đúng tên **`LocaleFirstDayDemo.java`**:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleFirstDayDemo {
    static LocalDate startOfWeek(LocalDate date, Locale locale) {
        DayOfWeek first = WeekFields.of(locale).getFirstDayOfWeek();
        return date.with(TemporalAdjusters.previousOrSame(first));
    }

    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale usMon = Locale.forLanguageTag("en-US-u-fw-mon");
        Locale frSun = Locale.forLanguageTag("fr-FR-u-fw-sun");
        Locale gbOverride = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
        Locale fwWins = Locale.forLanguageTag("en-US-u-fw-sat-rg-gbzzzz");

        System.out.println("us-default=" + WeekFields.of(us).getFirstDayOfWeek());
        System.out.println("us-mon=" + WeekFields.of(usMon).getFirstDayOfWeek());
        System.out.println("us-mon-tag=" + usMon.toLanguageTag());
        System.out.println("us-mon-key=" + usMon.getUnicodeLocaleType("fw"));
        System.out.println("us-mon-region=" + usMon.getCountry());
        System.out.println("fr-sun=" + WeekFields.of(frSun).getFirstDayOfWeek());
        System.out.println("rg-gb=" + WeekFields.of(gbOverride).getFirstDayOfWeek());
        System.out.println("fw-over-rg=" + WeekFields.of(fwWins).getFirstDayOfWeek());
        System.out.println("us-minimal=" +
                WeekFields.of(usMon).getMinimalDaysInFirstWeek());
        System.out.println("gb-minimal=" +
                WeekFields.of(fwWins).getMinimalDaysInFirstWeek());

        LocalDate sunday = LocalDate.of(2024, 1, 7);
        System.out.println("iso-day=" + sunday.getDayOfWeek());
        System.out.println("iso-day-number=" +
                sunday.get(ChronoField.DAY_OF_WEEK));
        System.out.println("localized-mon-number=" +
                sunday.get(WeekFields.of(usMon).dayOfWeek()));
        System.out.println("localized-sun-number=" +
                sunday.get(WeekFields.of(us).dayOfWeek()));
        System.out.println("pattern-e-mon=" +
                sunday.format(DateTimeFormatter.ofPattern("e", usMon)));
        System.out.println("week-start-mon=" + startOfWeek(sunday, usMon));
        System.out.println("week-start-sun=" + startOfWeek(sunday, us));
        System.out.println("week-start-sat=" + startOfWeek(sunday, fwWins));

        LocalDate janFirst = LocalDate.of(2021, 1, 1);
        System.out.println("us-fw-mon-week=" +
                janFirst.get(WeekFields.of(usMon).weekOfWeekBasedYear()));
        System.out.println("iso-week=" +
                janFirst.get(WeekFields.ISO.weekOfWeekBasedYear()));
        System.out.println("iso-week-year=" +
                janFirst.get(WeekFields.ISO.weekBasedYear()));

        Locale built = new Locale.Builder()
                .setLocale(Locale.US)
                .setUnicodeLocaleKeyword("fw", "wed")
                .build();
        System.out.println("built-tag=" + built.toLanguageTag());
        System.out.println("built-first=" +
                WeekFields.of(built).getFirstDayOfWeek());
        Locale removed = new Locale.Builder()
                .setLocale(built)
                .setUnicodeLocaleKeyword("fw", null)
                .build();
        System.out.println("removed-key=" +
                (removed.getUnicodeLocaleType("fw") == null));
        Locale unknown = new Locale.Builder()
                .setLocale(Locale.US)
                .setUnicodeLocaleKeyword("fw", "xyz")
                .build();
        System.out.println("unknown-syntax-accepted=" +
                "xyz".equals(unknown.getUnicodeLocaleType("fw")));
        try {
            new Locale.Builder().setLanguage("en")
                    .setUnicodeLocaleKeyword("fw", "m!");
        } catch (IllformedLocaleException expected) {
            System.out.println("malformed-keyword=rejected");
        }

        System.out.println("iso-fixed=" +
                WeekFields.of(DayOfWeek.MONDAY, 4).equals(WeekFields.ISO));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 LocaleFirstDayDemo.java
java LocaleFirstDayDemo
~~~

**Stdout đã kiểm chứng trên JDK hiện có** (các mặc định vùng/minimal days có thể chịu ảnh hưởng dữ liệu locale của JDK, còn kết quả explicit `fw` và các quy tắc API là trọng tâm):

~~~text
us-default=SUNDAY
us-mon=MONDAY
us-mon-tag=en-US-u-fw-mon
us-mon-key=mon
us-mon-region=US
fr-sun=SUNDAY
rg-gb=MONDAY
fw-over-rg=SATURDAY
us-minimal=1
gb-minimal=4
iso-day=SUNDAY
iso-day-number=7
localized-mon-number=7
localized-sun-number=1
pattern-e-mon=7
week-start-mon=2024-01-01
week-start-sun=2024-01-07
week-start-sat=2024-01-06
us-fw-mon-week=1
iso-week=53
iso-week-year=2020
built-tag=en-US-u-fw-wed
built-first=WEDNESDAY
removed-key=true
unknown-syntax-accepted=true
malformed-keyword=rejected
iso-fixed=true
~~~

### 14.1. Phân tích theo nhóm output

**Đọc và ghi Locale:**

- `us-mon-tag=en-US-u-fw-mon`: language tag được giữ theo chuẩn BCP 47.
- `us-mon-key=mon`: `getUnicodeLocaleType("fw")` trả loại ngày đã gắn.
- `us-mon-region=US`: thêm `fw` không đổi country gốc.

**Ghi đè ngày đầu tuần:**

- `us-default=SUNDAY` so với `us-mon=MONDAY`: cùng ngôn ngữ/vùng US nhưng sở thích ngày đầu tuần khác.
- `fr-sun=SUNDAY`: dù vùng FR thường dùng Monday, `fw-sun` điều chỉnh về Sunday.
- `rg-gb=MONDAY` và `fw-over-rg=SATURDAY`: có region override nhưng `fw` vẫn quyết định first day.
- `us-minimal=1`, `gb-minimal=4`: minh họa `fw` không tự đổi minDays thành 4; dữ liệu vùng vẫn quan trọng.

**Ngày thực và localized day number:**

- `iso-day=SUNDAY`, `iso-day-number=7`: `LocalDate` và ISO number không thay khi đổi Locale.
- `localized-mon-number=7` nhưng `localized-sun-number=1`: cùng Sunday được đánh số khác khi bắt đầu tuần khác.
- `pattern-e-mon=7`: pattern `e` một ký tự phản ánh cách đánh số theo locale trong trường hợp minh họa.

**Dịch ranh giới tuần:**

- `week-start-mon=2024-01-01`: ngày Chủ nhật 7/1 thuộc tuần bắt đầu Monday 1/1.
- `week-start-sun=2024-01-07`: theo Sunday-first, ngày đó chính là đầu tuần.
- `week-start-sat=2024-01-06`: theo Saturday-first, đầu tuần là thứ Bảy hôm trước.

**Đánh số tuần theo năm:**

- `us-fw-mon-week=1` nhưng `iso-week=53`, `iso-week-year=2020` với `2021-01-01`: có thể cùng Monday-start nhưng khác `minimalDaysInFirstWeek`.

**Builder và validation:**

- `built-tag=en-US-u-fw-wed`, `built-first=WEDNESDAY`: Builder gắn keyword.
- `removed-key=true`: type `null` xóa Unicode keyword `fw`.
- `unknown-syntax-accepted=true`: keyword type `xyz` đúng cú pháp nhưng không phải giá trị `fw` được đăng ký.
- `malformed-keyword=rejected`: Builder phát hiện type chứa ký tự không hợp lệ.
- `iso-fixed=true`: explicit Monday + 4 tương đương `WeekFields.ISO`.

### 14.2. Những điều ví dụ **không** khẳng định

- Không coi mọi quốc gia có cùng CLDR defaults vĩnh viễn; các phiên bản data có thể được cập nhật.
- Không coi `fw-mon` đồng nghĩa với tuần ISO ở mọi Locale.
- Không coi `Locale.Builder` là bộ kiểm tra semantics của đăng ký Unicode keywords.
- Không coi `DateTimeFormatter` làm thay đổi `LocalDate` hoặc ISO weekday.
- Không coi `fw` tự xác định timezone, ngày nghỉ hay kỳ làm việc của tổ chức.

## 15. Unit test tốt: kiểm tra cam kết thay vì dữ liệu vùng ngẫu nhiên

### 15.1. Những test nên có

~~~java
Locale custom = Locale.forLanguageTag("en-US-u-fw-mon");

assert WeekFields.of(custom).getFirstDayOfWeek()
        == DayOfWeek.MONDAY;

assert "mon".equals(custom.getUnicodeLocaleType("fw"));

assert WeekFields.of(
        Locale.forLanguageTag("en-US-u-fw-sat-rg-gbzzzz"))
        .getFirstDayOfWeek() == DayOfWeek.SATURDAY;
~~~

Đây là **mẫu điều kiện kiểm thử** bên trong một phương thức có các import `Locale`, `WeekFields` và `DayOfWeek`; dùng JUnit assertion khi viết test project thực, vì Java `assert` có thể bị tắt nếu không bật `-ea`.

Các điều kiện này dựa trên **giá trị override explicit** và hợp đồng precedence, nên phù hợp hơn cho regression test cross-JDK.

### 15.2. Tránh test dựa vào defaults không kiểm soát

~~~java
// Tránh coi đây là ràng buộc kinh doanh bất biến:
assert WeekFields.of(Locale.forLanguageTag("en-US"))
        .getMinimalDaysInFirstWeek() == 1;
~~~

Đây là **ví dụ test không nên ràng buộc khi sản phẩm không kiểm soát nguồn CLDR**, không phải câu khẳng định nó luôn sai. Dữ liệu vùng có thể khác theo provider/JDK/version; nếu báo cáo cần rule cố định, dùng `WeekFields.of(DayOfWeek.MONDAY, 4)` hoặc cấu hình nghiệp vụ rõ ràng.

### 15.3. Test trộn ranh giới năm

Hãy có test cho các ngày:

- 30/12, 31/12, 01/01 và các ngày đầu tháng.
- Tuần có `minimalDays=1` vs `minimalDays=4`.
- Lịch bắt đầu Sunday, Monday, Saturday.
- Một user đổi preference `fw` mà ngôn ngữ/vùng không đổi.
- Locale có cả `fw` và `rg`.
- Input `fw` sai cú pháp và input đúng cú pháp nhưng ngoài bảy giá trị đăng ký.
- Hiển thị tiêu đề lịch theo ngày đầu tuần và thứ tự bảy cột.
- Khi ứng dụng lưu week number, phải lưu **week-based-year + week number + week-rule version** đủ để tái dựng.

## 16. Các sai lầm thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “`fw` là mã ngày nghỉ cuối tuần” | Tính sai lịch làm việc, SLA | `fw` chỉ là first day of week |
| “`fw` chỉ nhận `mon` hoặc `sun`” | Chặn cấu hình hợp lệ | Cả bảy mã `mon..sun` |
| “`fw-mon` chính là ISO tuần” | Sai week number ở ranh giới năm | ISO còn yêu cầu minDays=4 |
| “`fw` đổi ngày thực/`DayOfWeek`” | Sai logic date/time | `LocalDate` và ISO weekday không đổi |
| “`DayOfWeek.getValue()` theo locale” | Sunday luôn 7 dù tuần Sunday-first | Dùng `WeekFields.dayOfWeek()` nếu cần đánh số theo locale |
| “Chỉ cần country để biết first day” | Bỏ qua `fw`/`rg` | `WeekFields.of(locale)` |
| “`fw` ghi đè cả region `rg`” | Hiểu sai minDays/format khác | `fw` ưu tiên first day; `rg` vẫn có tác động khác |
| “Locale.Builder chấp nhận `xyz` tức là fw=xyz hợp lệ” | Dữ liệu cấu hình không được nhận diện | Validate allowlist bảy type |
| “Một locale tag không có region có đầu tuần cố định” | Phụ thuộc likely-subtags/provider | Kiểm tra runtime hoặc đặt explicit override |
| “Đổi ngôn ngữ sang `en-GB` chỉ để có Monday” | Vô tình đổi các quy tắc vùng khác | Giữ locale gốc và thêm `fw-mon` |
| “Có `fw` thì timezone tự đổi” | Tính sai LocalDate từ Instant | ZoneId là khía cạnh khác |
| “Đổi `Locale.setDefault` cho từng request” | Ảnh hưởng request khác trong JVM | Truyền Locale tường minh |
| “`YYYY` và `yyyy` giống nhau” | Sai năm ở giao điểm ISO week-based-year | Phân biệt `Y` và calendar year |
| “Mọi calendar library sẽ tự đọc `fw`” | Frontend và backend khác thứ tự tuần | Chuyển explicit DayOfWeek nếu cần |
| “Kiểm thử defaults vùng ở một JDK áp dụng vĩnh viễn” | Test brittle sau nâng cấp CLDR | Test explicit fw; version hóa rule nếu nghiệp vụ cần |
| “Ngày đầu tuần là ngày đầu làm việc” | Sai lịch nghỉ/ca trực | Dùng work-calendar/holiday data riêng |
| “Java 10 chỉ có thể dùng cách cũ” | Bỏ qua java.time và locale extensions | Ưu tiên WeekFields/java.time hiện hành |
| “`fw` luôn làm số tuần bằng tuần ISO” | Báo cáo tuần không nhất quán | Chỉ rõ minDays/week-based-year |

## 17. Bài tập tự kiểm tra có đáp án

**Bài 1.** Trong `en-US-u-fw-mon`, key và value nào thể hiện ngày bắt đầu tuần?

**Đáp án:** `fw` là Unicode locale key; `mon` là type chỉ Monday. `u` đánh dấu Unicode extension.

**Bài 2.** Vì sao không cần đổi `en-US` sang `en-GB` để yêu cầu Monday-first?

**Đáp án:** Có thể dùng `en-US-u-fw-mon`, giữ ngôn ngữ/vùng chính mà override chỉ thuộc tính first day.

**Bài 3.** Giá trị `fw` hợp lệ gồm những gì?

**Đáp án:** `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`.

**Bài 4.** Lấy ngày đầu tuần được xác định bởi `Locale` bằng API nào?

**Đáp án:** `WeekFields.of(locale).getFirstDayOfWeek()`, trả `DayOfWeek`.

**Bài 5.** `WeekFields.of(Locale.forLanguageTag("en-US-u-fw-mon")).getFirstDayOfWeek()` có giá trị gì?

**Đáp án:** `DayOfWeek.MONDAY`.

**Bài 6.** `fw-mon` có tự đồng nghĩa ISO-8601 week rules không?

**Đáp án:** Không. ISO yêu cầu Monday + ít nhất bốn ngày trong tuần đầu năm; `fw` chỉ đặt first day. `minimalDaysInFirstWeek` vẫn theo locale/region/provider.

**Bài 7.** Với `en-US-u-fw-sat-rg-gbzzzz`, ngày đầu tuần là gì?

**Đáp án:** `SATURDAY` vì `fw-sat` ưu tiên hơn ngày đầu tuần suy ra từ `rg-gbzzzz`.

**Bài 8.** `Locale.getCountry()` của `en-US-u-fw-mon` là gì?

**Đáp án:** `US`. Keyword `fw` không thay region gốc.

**Bài 9.** `LocalDate.of(2024,1,7).getDayOfWeek().getValue()` thay đổi theo `fw` không?

**Đáp án:** Không; Sunday có ISO value 7. Locale chỉ tác động tới các API tính/hiển thị theo locale khi được truyền vào.

**Bài 10.** Vì sao Sunday có thể là số 1 trong lịch US nhưng vẫn có ISO number 7?

**Đáp án:** `WeekFields.dayOfWeek()` đánh số từ first day của locale, còn `ChronoField.DAY_OF_WEEK`/`DayOfWeek.getValue()` dùng Monday=1..Sunday=7 cố định.

**Bài 11.** Cách tìm đầu tuần của một `LocalDate` theo locale?

**Đáp án:** Lấy `DayOfWeek first = WeekFields.of(locale).getFirstDayOfWeek()`, rồi `date.with(TemporalAdjusters.previousOrSame(first))`.

**Bài 12.** Nếu user chọn Wednesday-first, dùng type gì và có hợp lệ không?

**Đáp án:** `fw-wed`; là một trong bảy type được đăng ký.

**Bài 13.** Có thể gọi `new Locale.Builder().setUnicodeLocaleKeyword("fw","xyz")` mà không lỗi cú pháp không?

**Đáp án:** Có, vì Builder chỉ kiểm tra **well-formed syntax**, không phải mọi type đúng nghĩa CLDR. Ứng dụng nên reject `xyz` bằng allowlist.

**Bài 14.** Ký tự `!` trong type `m!` dẫn đến điều gì khi dùng Builder?

**Đáp án:** `IllformedLocaleException` vì sai cú pháp language tag extension.

**Bài 15.** Vì sao `Locale.setDefault(...)` không phù hợp để đặt sở thích từng user trong web server?

**Đáp án:** Nó có tác động global trong JVM, ảnh hưởng những request/thread khác. Truyền Locale theo request/user thay vì sửa mặc định tiến trình.

**Bài 16.** `fw-mon` có tự cung cấp ngày nghỉ thứ Bảy, Chủ nhật không?

**Đáp án:** Không. Đầu tuần hiển thị khác với thông tin weekend/working days/holidays. Cần work-calendar riêng.

**Bài 17.** Nếu ứng dụng tính tuần ISO trong báo cáo tài chính, nên dùng gì?

**Đáp án:** `WeekFields.ISO` hoặc `WeekFields.of(DayOfWeek.MONDAY,4)`. Không dựa một mình vào `fw-mon`.

**Bài 18.** Vì sao ngày 2021-01-01 có thể thuộc năm tuần 2020?

**Đáp án:** Theo ISO (Monday + minimalDays=4), 1/1/2021 là thứ Sáu trong tuần 53 của week-based-year 2020. Week-based-year không nhất thiết bằng calendar year.

**Bài 19.** `fw` có tự đổi múi giờ hoặc LocalDate từ Instant không?

**Đáp án:** Không. Trước hết chuyển Instant theo `ZoneId` của user để lấy LocalDate, rồi xác định đầu tuần dựa `fw`.

**Bài 20.** Nếu frontend calendar không nhận Unicode locale extensions, xử lý thế nào?

**Đáp án:** Backend hoặc tầng tích hợp có thể chuyển `WeekFields.of(locale).getFirstDayOfWeek()` sang cấu hình firstDayOfWeek mà frontend hỗ trợ; xác minh mapping ISO/localized numbering.

## 18. Checklist áp dụng trong dự án Java

Trước khi sử dụng khóa `fw`, kiểm tra:

1. Đang giải quyết **đầu tuần hiển thị**, **số tuần trong năm** hay **ngày làm việc đầu tiên**? Ba bài toán khác nhau.
2. Locale gốc có language/region phù hợp không, có cần giữ nguyên chúng không?
3. Người dùng có `fw` explicit hay dùng default của provider/CLDR?
4. Nếu xây tag từ input, đã validate đúng bảy `fw` types chưa?
5. Có lấy ngày đầu tuần qua `WeekFields.of(locale)` thay vì hard-code quốc gia không?
6. Nếu có thêm `rg`, đã hiểu `fw` có ưu tiên first day chưa?
7. Nếu cần tính week number, đã thống nhất `minimalDaysInFirstWeek` và week-based-year chưa?
8. Nếu cần ISO, đã dùng `WeekFields.ISO` hoặc Monday+4 rõ ràng chưa?
9. Có đang nhầm localized day-of-week index với ISO `DayOfWeek.getValue()` không?
10. Có lấy `LocalDate` trong đúng `ZoneId` trước khi tính tuần không?
11. Có tránh `Locale.setDefault` global khi xử lý nhiều user không?
12. UI có dùng cùng sở thích đầu tuần với backend không?
13. Với lịch có tên thứ, có lấy tên theo Locale và thứ tự theo `WeekFields` không?
14. Với scheduling/HR, có quy tắc weekend/holiday/working calendar độc lập không?
15. Unit test đã bao gồm `fw-mon`, `fw-sun`, `fw-sat` và cả `fw`+`rg` chưa?
16. Test near year boundary có kiểm tra tuần/năm-tuần không?
17. Có kiểm soát thay đổi dữ liệu locale/CLDR qua nâng cấp JDK nếu business cần ổn định tuyệt đối không?
18. Có tài liệu API rõ về ngày đầu tuần, cách đánh số weekday, tuần ISO và timezone không?

## 19. Tài liệu chính thức còn áp dụng

1. [Oracle – Internationalization Enhancements in JDK 10](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): xác nhận Java 10 bổ sung mức hỗ trợ Unicode locale extensions `cu`, `fw`, `rg` và `tz`.
2. [Java SE 17 – WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html): `of(Locale)`, ưu tiên `fw` so với `rg`, `getFirstDayOfWeek`, `getMinimalDaysInFirstWeek`, `dayOfWeek` và các trường đánh số tuần.
3. [Java SE 25 – WeekFields](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html): chứng cứ hành vi `fw`/`rg` vẫn áp dụng trên JDK hiện đại.
4. [Java SE 17 – Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): BCP 47, Unicode locale keywords, `forLanguageTag`/`toLanguageTag` và `getUnicodeLocaleType`.
5. [Java SE 17 – Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): `setUnicodeLocaleKeyword` và sự khác nhau giữa kiểm tra cú pháp với kiểm tra semantics.
6. [Unicode CLDR / UTS #35 – Unicode First Day Identifier](https://www.unicode.org/reports/tr35/tr35.html): định nghĩa `fw` và danh sách các giá trị chuẩn cho first day of week.
7. [Unicode CLDR – BCP47 calendar keyword registry](https://github.com/unicode-org/cldr/blob/main/common/bcp47/calendar.xml): các type `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`.
8. [Unicode CLDR – Week Data / First Day Overrides](https://www.unicode.org/reports/tr35/tr35-dates.html): first day khác weekend/working day, và quy tắc ưu tiên day override.
9. [Java SE 17 – DayOfWeek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DayOfWeek.html): thứ tự enum ISO và `getValue()`.
10. [Java SE 17 – TemporalAdjusters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjusters.html): `previousOrSame(DayOfWeek)` để lấy ngày bắt đầu tuần.
11. [Java SE 17 – DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern localized weekday `e`/`c` và week-based-year `Y`.
12. [Java SE 17 – LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): xử lý ngày độc lập Locale/ZoneId khi đã có LocalDate.

**Tóm tắt:** Unicode locale extension **`fw`** cho phép chỉ định **ngày đầu tuần** mà không cần đổi language/region: `en-US-u-fw-mon` nghĩa là US English với Monday-first. `WeekFields.of(locale)` là API chuẩn đọc quy tắc đó; `fw` có ưu tiên so với ngày đầu tuần suy ra từ `rg`. Không nhầm sở thích đầu tuần với **weekend, working day, timezone** hoặc toàn bộ **ISO-8601 week rules**. Với mục tiêu tính tuần ISO cố định, dùng `WeekFields.ISO`; với lịch địa phương hóa, dùng Locale có `fw` rõ ràng và kiểm tra input bằng allowlist bảy giá trị.
