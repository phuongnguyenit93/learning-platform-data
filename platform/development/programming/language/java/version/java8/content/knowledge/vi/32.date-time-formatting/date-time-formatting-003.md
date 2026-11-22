# Phân biệt năm u, y và năm theo tuần Y trong Java DateTimeFormatter

## Mục tiêu bài học

Trong Java, ba ký tự pattern **u**, **y** và **Y** của DateTimeFormatter **không đồng nghĩa**. Với phần lớn ngày hiện đại thuộc Công nguyên, hai mẫu uuuu và yyyy thường in cùng một con số; nhưng khi xử lý năm 0, năm trước Công nguyên, parsing nghiêm ngặt hoặc lịch dựa trên tuần, khác biệt của chúng trở nên rất quan trọng. Chỉ cần viết hoa nhầm một chữ cái, hệ thống có thể gắn **31/12/2020** với một năm khác trong báo cáo, khóa dữ liệu hoặc chuỗi ngày được xuất.

Bài thuộc chủ đề **Định dạng ngày giờ** của Java 8, tập trung vào những API **vẫn còn áp dụng hiện nay** trong java.time. Sau khi học, bạn có thể:

1. Giải thích **u = proleptic year (YEAR)**, **y = year-of-era (YEAR_OF_ERA)**, **Y = localized week-based-year**.
2. Dùng đúng **uuuu-MM-dd** cho ngày lịch ISO theo kiểu năm có thể đi qua mốc 1 BCE/1 CE; dùng **G** khi cần biểu thị era cùng year-of-era.
3. Biết vì sao Java sử dụng **năm 0** cho 1 BCE và **năm -1** cho 2 BCE trong mô hình proleptic ISO.
4. Phân biệt **năm của ngày lịch** với **năm chứa tuần được tính theo quy tắc tuần**, đặc biệt quanh 29–31/12 và 1–3/1.
5. Hiểu **WeekFields**, ngày bắt đầu tuần, số ngày tối thiểu của tuần đầu tiên, và lý do **Y phụ thuộc Locale**.
6. Dùng **w** (số tuần của week-based-year), **e** (ngày trong tuần theo Locale) đúng với Y; không lẫn với **W** (week-of-month).
7. Parse ngày ISO với **ResolverStyle.STRICT** một cách có chủ đích; nhận biết vì sao yyyy-MM-dd không có era có thể thất bại dưới STRICT.
8. Dùng **DateTimeFormatter.ISO_LOCAL_DATE**, **ISO_WEEK_DATE**, **IsoFields** hoặc **WeekFields.ISO** cho API/báo cáo cần quy tắc ISO ổn định.
9. Tránh lỗi gắn năm sai khi làm báo cáo tuần, khóa lưu trữ, phân vùng dữ liệu, xử lý lịch qua múi giờ và đổi Locale.
10. Chạy các chương trình Java 17+ minh họa kết quả, parsing và kiểm thử tại ranh giới năm.

**Phiên bản:** DateTimeFormatter, WeekFields, IsoFields, ResolverStyle và LocalDate là API từ Java 8, vẫn được hỗ trợ trong JDK hiện đại. Ví dụ dùng các API đó, biên dịch với **javac --release 17**; không cần giải pháp định dạng ngày giờ đã legacy.

## 1. Bảng phân biệt nhanh: chữ thường và chữ hoa mang ý nghĩa khác nhau

| Ký tự pattern | Trường thời gian | Ý nghĩa | Câu hỏi nó trả lời |
|---|---|---|---|
| **u** | ChronoField.YEAR | Proleptic year (năm theo trục liên tục) | Ngày đó thuộc năm ISO nào, kể cả năm 0 và số âm? |
| **y** | ChronoField.YEAR_OF_ERA | Year-of-era | Đang là năm thứ mấy trong một era? |
| **Y** | WeekFields.weekBasedYear() theo Locale | Week-based-year | Tuần chứa ngày đó được gắn vào năm tuần nào? |
| **G** | ChronoField.ERA | Era | BC hay AD, hoặc tên era theo chronology? |
| **w** | Week-of-week-based-year theo Locale | Số tuần thuộc năm theo tuần | Tuần số mấy trong week-based-year? |
| **W** | Week-of-month theo Locale | Tuần của tháng | Tuần số mấy theo quy tắc tháng? |
| **e** | Localized day-of-week | Ngày trong tuần theo Locale | Ngày thứ mấy nếu tuần bắt đầu theo Locale đó? |
| **E** | Text day-of-week | Tên thứ trong tuần | Mon, Tue hoặc tên tương ứng Locale |

Hai chữ **Y** và **y** khác nhau hoàn toàn: **Y** không có nghĩa “YEAR viết hoa để in bốn chữ số đẹp hơn”; nó là **năm theo tuần**. Cũng vậy, **u** không phải phiên bản mới của **Y**. Mỗi chữ chọn một trường thời gian khác nhau.

Các chuỗi pattern:

~~~java
// Mảnh mã, cần import java.time.format.DateTimeFormatter.
DateTimeFormatter calendar =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");
DateTimeFormatter eraYear =
        DateTimeFormatter.ofPattern("G yyyy-MM-dd");
DateTimeFormatter weekDate =
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e");
~~~

Dòng đầu format một **ngày lịch**; dòng hai format **era + năm trong era**; dòng ba format **năm theo tuần + tuần + ngày trong tuần theo Locale**. Khi dùng Y/w/e, phải xác định Locale hoặc quy tắc tuần rõ ràng.

### Một ngày có thể có hai con số năm khác nhau mà không hề mâu thuẫn

Ngày **2019-12-30** thuộc năm lịch 2019 nhưng là **thứ Hai của tuần 1, week-based-year ISO 2020**:

~~~text
Ngày lịch ISO:          2019-12-30
Năm lịch (u):           2019
Năm trong era (y):      2019 AD
ISO week-based-year:    2020
ISO week number:        01
ISO day-of-week:        1 (Monday)

ISO week date:          2020-W01-1
~~~

Ngày thực vẫn là **30/12/2019**. Giá trị 2020 trong week date chỉ định **năm của tuần**, không phải lịch chuyển sang ngày 30/12/2020.

## 2. u — proleptic year trong lịch ISO

**u** là năm proleptic, tương ứng **ChronoField.YEAR**. Trong chronology ISO mặc định:

- 2024 CE là năm u=2024.
- 1 CE là u=1.
- 1 BCE là u=0.
- 2 BCE là u=-1.
- 3 BCE là u=-2.

Từ **proleptic** nghĩa là trục năm được mở rộng liên tục khi đi về quá khứ; nó có một **năm 0** trong hệ thống đánh số ISO của java.time. Điều này hữu ích cho tính toán lịch và ánh xạ ngày trước Công nguyên, nhưng khác cách ghi “1 BCE” truyền thống.

Ví dụ:

~~~java
// Mảnh mã: cần import java.time.LocalDate.
LocalDate oneBce = LocalDate.of(0, 1, 1);
LocalDate twoBce = LocalDate.of(-1, 1, 1);
~~~

Hai giá trị này **không phải lỗi**, vì LocalDate hỗ trợ proleptic ISO calendar theo phạm vi API. Nếu dùng **uuuu-MM-dd**, năm 0 in dưới dạng **0000**, năm -1 in dưới dạng **-0001**.

### Khi nào dùng uuuu?

- Khi tạo một định dạng **ngày lịch ISO** có năm đầy đủ.
- Khi parse với **ResolverStyle.STRICT** và không dùng era.
- Khi cần phân biệt ngày có proleptic year 0/âm một cách nhất quán.
- Khi tạo khóa lưu trữ “ngày lịch” của LocalDate, thay vì khóa “năm theo tuần”.

Một lựa chọn an toàn hơn pattern thủ công cho ngày ISO là **DateTimeFormatter.ISO_LOCAL_DATE** hoặc **LocalDate.toString()**. Chúng diễn đạt đúng semantics ISO calendar-date và tránh lỗi gõ nhầm Y thành y/u.

**Lưu ý:** Bốn chữ **uuuu** không có nghĩa giới hạn năm trong 0000..9999; một proleptic year có độ lớn hơn bốn chữ số có thể được format với dấu và thêm chữ số theo quy tắc DateTimeFormatter. Đừng dùng regex ép bốn chữ số nếu phạm vi nghiệp vụ cần năm rất xa.

## 3. y — year-of-era cần hiểu cùng G

**y** là **year-of-era**, tương ứng ChronoField.YEAR_OF_ERA. Nó trả lời “năm thứ mấy trong era này?”, **không** phải năm có dấu qua trục BCE/CE.

Trong ISO chronology:

| LocalDate | u (YEAR) | y (YEAR_OF_ERA) | G (ERA với English locale) |
|---|---:|---:|---|
| 2024-01-01 | 2024 | 2024 | AD |
| 0001-01-01 | 1 | 1 | AD |
| 0000-01-01 | 0 | 1 | BC |
| -0001-01-01 | -1 | 2 | BC |

Thế nên cả **1 CE** và **1 BCE** đều có y=1. Nếu chỉ lưu hoặc hiển thị **yyyy** mà không có **G** trong bài toán hỗ trợ BCE, thông tin era bị mất. Mẫu **G yyyy-MM-dd** sẽ phân biệt BC 0001-01-01 với AD 0001-01-01.

### y và u thường trùng nhau với dữ liệu hiện đại

Với các ngày như 2024-01-01 ở ISO/AD, **yyyy** và **uuuu** đều in 2024. Đây là lý do lỗi dễ lọt qua unit test chỉ chứa ngày hiện đại. Nhưng một formatter trùng nhau ở dữ liệu dương **không chứng minh** hai pattern tương đương trong mọi ngữ cảnh.

### Tại sao Java cho năm 0 nhưng era BC bắt đầu từ 1?

Proleptic year là một trục có số âm/0/dương giúp thuật toán tính theo năm. Year-of-era là cách người đọc gắn năm với tên era; hệ thống BCE/CE không có năm “0 BCE”. Công thức dưới ISO chronology có thể hiểu là:

~~~text
Proleptic YEAR >= 1: era AD, YEAR_OF_ERA = YEAR

Proleptic YEAR <= 0: era BC, YEAR_OF_ERA = 1 - YEAR

Ví dụ YEAR =  0 => 1 BCE
       YEAR = -1 => 2 BCE
~~~

**Không áp dụng mù quáng công thức ISO** cho mọi chronology. DateTimeFormatter có thể dùng chronology khác; khi hiển thị một hệ lịch khác, ý nghĩa era và cách đếm year-of-era cần theo chronology đó.

## 4. Ví dụ hoàn chỉnh 1 — u và y qua mốc BCE/CE

Tạo file **YearLettersDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class YearLettersDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "uuuu | yyyy | G yyyy", Locale.ENGLISH);

        LocalDate modern = LocalDate.of(2024, 1, 1);
        LocalDate firstCe = LocalDate.of(1, 1, 1);
        LocalDate firstBce = LocalDate.of(0, 1, 1);
        LocalDate secondBce = LocalDate.of(-1, 1, 1);

        System.out.println("modern=" + modern.format(formatter));
        System.out.println("firstCE=" + firstCe.format(formatter));
        System.out.println("firstBCE=" + firstBce.format(formatter));
        System.out.println("secondBCE=" + secondBce.format(formatter));
    }
}
~~~

Biên dịch và chạy:

~~~text
javac --release 17 YearLettersDemo.java
java YearLettersDemo
~~~

Stdout:

~~~text
modern=2024 | 2024 | AD 2024
firstCE=0001 | 0001 | AD 0001
firstBCE=0000 | 0001 | BC 0001
secondBCE=-0001 | 0002 | BC 0002
~~~

Giải thích:

1. Với năm hiện đại, u và y in cùng con số.
2. Năm proleptic 0 (1 BCE) được in bởi uuuu là 0000, còn yyyy là 0001; phải dùng G mới biết 0001 này thuộc BC.
3. Năm proleptic -1 là 2 BCE nên yyyy ra 0002.
4. Locale.ENGLISH chỉ được dùng để cố định chữ AD/BC trong stdout; năm proleptic và logic era do chronology quyết định.

**Ứng dụng:** Nếu dữ liệu chỉ có ngày ISO và muốn round-trip đầy đủ, chọn **uuuu-MM-dd**. Nếu muốn in theo cách nói của lịch sử BCE/CE, chọn **G yyyy-MM-dd** cùng một Locale rõ ràng.

## 5. Y — week-based-year không phải năm lịch

**Y viết hoa** đại diện cho **năm theo tuần** (week-based-year). Một tuần phải thuộc về **một** năm tuần, dù bảy ngày của nó có thể nằm ở hai năm lịch khác nhau.

Để xác định tuần 1 và năm theo tuần, cần hai quy tắc:

1. **Ngày bắt đầu tuần** là thứ mấy?
2. **Tuần đầu tiên của năm** cần tối thiểu bao nhiêu ngày nằm trong năm lịch mới?

Java biểu diễn chúng qua **WeekFields**. Với **WeekFields.ISO**:

- Tuần bắt đầu vào **thứ Hai**.
- Tuần đầu tiên phải có **ít nhất 4 ngày** trong năm mới.
- Đây là quy tắc ISO-8601; thường được mô tả bằng “tuần chứa ngày 4/1” hoặc “tuần chứa thứ Năm đầu năm”.
- Một tuần ISO có bảy ngày, đánh số thứ Hai=1 đến Chủ nhật=7.
- Có các năm tuần gồm **52** tuần, một số có **53** tuần.

Ví dụ ở cuối năm:

~~~text
2019-12-29 (Sun) -> 2019-W52-7
2019-12-30 (Mon) -> 2020-W01-1
2019-12-31 (Tue) -> 2020-W01-2
2020-01-01 (Wed) -> 2020-W01-3

2020-12-31 (Thu) -> 2020-W53-4
2021-01-01 (Fri) -> 2020-W53-5
2021-01-03 (Sun) -> 2020-W53-7
2021-01-04 (Mon) -> 2021-W01-1
~~~

Ngày **01/01/2021** có u=2021 nhưng ISO week-based-year=2020. Vì vậy dùng Y để xuất dữ liệu **ngày lịch** dễ gắn sai nhãn năm; nó chỉ đúng khi bạn thực sự làm việc với **tuần**.

### Y không mặc định là ISO ở mọi Locale

Trong DateTimeFormatter.ofPattern, các field week-based-year **theo Locale**. Nhiều thiết lập tại Hoa Kỳ dùng:

- Chủ nhật là ngày đầu tuần.
- Tuần đầu tiên chỉ cần tối thiểu 1 ngày thuộc năm mới.

Đó là quy tắc **WeekFields.SUNDAY_START** (Sunday, minimalDays=1), khác ISO. Locale.US thường dùng chính quy tắc đó; Locale.UK thường dùng Monday/minimalDays=4. Điều này có thể đổi Y và w ở ngày giáp năm.

**Lưu ý tính tái lập:** Cấu hình tuần cho Locale được lấy từ dữ liệu locale của JDK/provider và có thể cập nhật. Nếu hệ thống cần **hợp đồng ISO không thay đổi theo máy**, ưu tiên **WeekFields.ISO, IsoFields hoặc DateTimeFormatter.ISO_WEEK_DATE** thay vì ngầm phụ thuộc Locale mặc định.

## 6. WeekFields, IsoFields và các field số tuần

Đừng đánh đồng các field sau:

- **WeekFields.ISO.weekBasedYear()**: năm theo tuần ISO.
- **WeekFields.ISO.weekOfWeekBasedYear()**: số tuần **trong năm theo tuần**, từ 1 đến 52/53.
- **WeekFields.ISO.weekOfYear()**: số tuần **bên trong năm lịch**, có thể là tuần 0 đầu năm; **khác** weekOfWeekBasedYear.
- **WeekFields.ISO.dayOfWeek()**: ngày trong tuần theo quy tắc ISO.
- **IsoFields.WEEK_BASED_YEAR** và **IsoFields.WEEK_OF_WEEK_BASED_YEAR**: các field ISO-8601 cố định, tiện cho code tính báo cáo.
- **ChronoField.DAY_OF_WEEK**: thứ trong tuần theo ISO, Monday=1 đến Sunday=7.

Các cách lấy field:

~~~java
// Mảnh mã, cần import java.time.temporal.*.
LocalDate date = LocalDate.of(2021, 1, 1);

int calendarYear = date.getYear();
int isoWeekYear = date.get(IsoFields.WEEK_BASED_YEAR);
int isoWeekNumber =
        date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);
int isoDayNumber =
        date.get(ChronoField.DAY_OF_WEEK);
~~~

Giá trị là calendarYear=2021, isoWeekYear=2020, isoWeekNumber=53, isoDayNumber=5.

### Một bẫy tên giống nhau

**weekOfYear()** trong WeekFields **không phải** weekOfWeekBasedYear(). Week-of-year cố chia các tuần trong ranh giới của năm lịch, nên có thể xuất hiện **tuần 0**; còn week-of-week-based-year tính theo năm tuần có thể chạy xuyên ranh giới 31/12. Với báo cáo theo ISO week date, phải dùng đúng **weekOfWeekBasedYear** hoặc **IsoFields.WEEK_OF_WEEK_BASED_YEAR**.

## 7. Ví dụ hoàn chỉnh 2 — so năm tuần ISO và US ở ranh giới năm

Tạo file **WeekBoundaryDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class WeekBoundaryDemo {
    public static void main(String[] args) {
        DateTimeFormatter iso = DateTimeFormatter.ISO_WEEK_DATE;
        DateTimeFormatter us = DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.US);

        LocalDate[] days = {
                LocalDate.of(2018, 12, 30),
                LocalDate.of(2018, 12, 31),
                LocalDate.of(2019, 12, 29),
                LocalDate.of(2019, 12, 30),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2022, 1, 1)
        };

        for (LocalDate day : days) {
            System.out.println(day
                    + " ISO=" + day.format(iso)
                    + " US=" + day.format(us));
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 WeekBoundaryDemo.java
java WeekBoundaryDemo
~~~

Stdout (theo quy tắc locale của JDK 17 đã kiểm thử):

~~~text
2018-12-30 ISO=2018-W52-7 US=2019-W01-1
2018-12-31 ISO=2019-W01-1 US=2019-W01-2
2019-12-29 ISO=2019-W52-7 US=2020-W01-1
2019-12-30 ISO=2020-W01-1 US=2020-W01-2
2020-12-31 ISO=2020-W53-4 US=2021-W01-5
2021-01-01 ISO=2020-W53-5 US=2021-W01-6
2022-01-01 ISO=2021-W52-6 US=2022-W01-7
~~~

Điểm cần rút ra:

1. Ngày **30/12/2018** có ISO week-year 2018 nhưng US week-year 2019.
2. Ngày **29/12/2019** thuộc ISO 2019-W52 nhưng US 2020-W01.
3. Ngày **31/12/2020** thuộc ISO 2020-W53 nhưng US 2021-W01.
4. Ngày **01/01/2021** thuộc ISO tuần 53 của năm 2020, trong khi tuần kiểu US đã thuộc năm 2021.
5. Trong US, pattern e có giá trị Chủ nhật=1; trong ISO, thứ Hai=1. Vì vậy hai chuỗi không chỉ khác Y/w, chúng còn khác cách đánh số ngày e.

**Không trộn** năm của một locale với số tuần của một locale khác: chẳng hạn lấy Y từ US nhưng w từ ISO sẽ tạo một bộ khóa sai hoặc không nhất quán.

## 8. Vì sao YYYY-MM-dd là một lỗi nghiêm trọng?

Một anti-pattern phổ biến khi muốn định dạng **ngày lịch** là:

~~~java
// PHẢN VÍ DỤ nếu ý định là calendar date:
DateTimeFormatter wrong = DateTimeFormatter.ofPattern(
        "YYYY-MM-dd", Locale.US);
String printed = LocalDate.of(2020, 12, 31).format(wrong);
~~~

Với quy tắc tuần kiểu US, **printed là 2021-12-31**, dù LocalDate gốc là 2020-12-31. Dữ liệu tháng và ngày được lấy từ năm lịch gốc, **nhưng Y lấy năm theo tuần**. Chuỗi là một tổ hợp các field khác hệ tọa độ thời gian.

Nếu sử dụng nó để đặt tên file, phân vùng bảng, lập khóa Redis, ký số, tạo URL hay ghi log, cùng một ngày có thể bị gán năm sai tại ranh giới. Khi parse ngược, một tổ hợp Y với M/d cũng **không phải bộ field chuẩn** để khôi phục calendar date bằng resolver; đừng dựa vào sự “chạy được” của format mà tưởng round-trip sẽ đúng.

**Đúng khi cần ngày lịch:**

~~~java
// Mảnh mã:
String safe = LocalDate.of(2020, 12, 31)
        .format(DateTimeFormatter.ISO_LOCAL_DATE);
// "2020-12-31"
~~~

Hoặc dùng pattern uuuu-MM-dd với chronology ISO và quy tắc parse phù hợp.

**Đúng khi cần một ngày theo tuần ISO:**

~~~java
// Mảnh mã:
String weekDate = LocalDate.of(2020, 12, 31)
        .format(DateTimeFormatter.ISO_WEEK_DATE);
// "2020-W53-4"
~~~

**Không coi hai chuỗi có cùng mục đích.** Calendar date trả lời năm-tháng-ngày; ISO week date trả lời năm tuần-tuần-thứ.

## 9. Các pattern liên quan: Y, w, W, e, E và G

Một số lỗi liên quan tới chữ hoa/chữ thường:

| Pattern | Ý nghĩa | Cảnh báo |
|---|---|---|
| uuuu-MM-dd | Proleptic calendar year + month + day | Phù hợp ISO LocalDate |
| yyyy-MM-dd | Year-of-era + month + day | Không có G có thể không resolve trong STRICT |
| G yyyy-MM-dd | Era + year-of-era + month + day | Có thể phân biệt BCE/CE |
| YYYY-'W'ww-e | Localized week-year + tuần + localized day-of-week | Cần Locale xác định |
| YYYY-'W'ww | Year + tuần, nhưng không có thứ | Không định danh một ngày đơn lẻ |
| YYYY-MM-dd | Week-year kết hợp month/day của calendar | Sai ý định nếu chỉ cần calendar date |
| W | Week-of-month | Không thay thế được w |
| w | Week-of-week-based-year | Phải gắn đúng week-year |
| e | Localized weekday number | Sunday có thể là 1 với US |
| E | Tên thứ trong tuần | Mon, Tue, ... theo Locale |
| G | Era | BC/AD với ISO + English |

### Chữ Y không phải ký hiệu năm ISO tự động trong mọi môi trường

Một formatter như DateTimeFormatter.ofPattern("YYYY-'W'ww-e") **không truyền Locale** sẽ lấy Locale mặc định của môi trường. Chạy trên máy cấu hình Locale.US và Locale.UK có thể tạo năm tuần hoặc số thứ khác nhau.

Khi cần dữ liệu trao đổi cố định giữa hệ thống, dùng **DateTimeFormatter.ISO_WEEK_DATE**. Nếu cần chính sách khác, dùng **WeekFields.of(DayOfWeek, minimalDays)** để quy tắc đó là quyết định của ứng dụng, không phải sự tình cờ của môi trường.

## 10. Parse khác format: uuuu và yyyy dưới STRICT

DateTimeFormatter thực hiện cả **parse text thành các field** và **resolve field thành ngày có nghĩa**. Hai bước này không giống nhau.

**u = YEAR** có thể trực tiếp cung cấp năm proleptic cho LocalDate. **y = YEAR_OF_ERA** đưa ra năm trong era, nhưng nếu **G/ERA không có trong input**, ở chế độ STRICT, resolver chưa biết đó là BCE hay CE.

Ví dụ:

~~~java
// Mảnh mã, cần import java.time.format.* và java.util.Locale.
DateTimeFormatter strictU = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter strictY = DateTimeFormatter
        .ofPattern("yyyy-MM-dd", Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

Với input **2024-02-29**:

- LocalDate.parse(input, strictU) **thành công** vì YEAR=2024 và ngày hợp lệ.
- LocalDate.parse(input, strictY) **thất bại** khi resolve thành LocalDate vì YEAR_OF_ERA=2024 nhưng không có ERA dưới STRICT.
- Dùng mẫu **G yyyy-MM-dd** và input có era, ví dụ **BC 0001-01-01**, có đủ dữ liệu để resolve thành proleptic year 0.

### Default ResolverStyle.SMART có thể che khuất sự khác biệt

DateTimeFormatter.ofPattern mặc định có **ResolverStyle.SMART**. Với chronology ISO, SMART có thể suy luận AD khi year-of-era dương thiếu era; do đó nhiều ứng dụng parse yyyy-MM-dd thành công trong ngày hiện đại.

SMART cũng có thể **điều chỉnh ngày không tồn tại**. Ví dụ 2023-02-29 có thể được đưa về 2023-02-28 khi parse theo mẫu year/month/day với SMART. Nếu hợp đồng API đòi ngày hợp lệ chính xác, cần STRICT và pattern trường năm đúng.

**Khuyến nghị:** Khi kiểm tra input ngày lịch ISO nghiêm ngặt, dùng **DateTimeFormatter.ISO_LOCAL_DATE**, hoặc **uuuu-MM-dd** kết hợp ResolverStyle.STRICT. Dùng **G yyyy-MM-dd** khi input thực sự biểu diễn year-of-era có tên era.

## 11. Ví dụ hoàn chỉnh 3 — parsing nghiêm ngặt, SMART và era

Tạo file **StrictYearParsingDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictYearParsingDemo {
    public static void main(String[] args) {
        DateTimeFormatter strictU = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter strictY = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter strictEra = DateTimeFormatter
                .ofPattern("G yyyy-MM-dd", Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter smartY = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ENGLISH);

        System.out.println("strictU="
                + LocalDate.parse("2024-02-29", strictU));

        try {
            LocalDate.parse("2024-02-29", strictY);
        } catch (DateTimeParseException expected) {
            System.out.println("strictY=DateTimeParseException");
        }

        System.out.println("smartY="
                + LocalDate.parse("2024-02-29", smartY));
        System.out.println("smartAdjusted="
                + LocalDate.parse("2023-02-29", smartY));

        System.out.println("bce="
                + LocalDate.parse("BC 0001-01-01", strictEra));

        try {
            LocalDate.parse("2023-02-29", strictU);
        } catch (DateTimeParseException expected) {
            System.out.println("badLeap=DateTimeParseException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 StrictYearParsingDemo.java
java StrictYearParsingDemo
~~~

Stdout:

~~~text
strictU=2024-02-29
strictY=DateTimeParseException
smartY=2024-02-29
smartAdjusted=2023-02-28
bce=0000-01-01
badLeap=DateTimeParseException
~~~

**Đọc kỹ:**

1. uuuu kết hợp STRICT cung cấp YEAR và xác nhận năm nhuận 2024.
2. yyyy kết hợp STRICT không có era nên không đủ để tạo LocalDate.
3. Default SMART của yyyy chấp nhận ngày hợp lệ và có thể **điều chỉnh** ngày không tồn tại 29/02/2023 về 28/02/2023.
4. G + yyyy cung cấp cả BC và year-of-era=1, khôi phục năm proleptic 0.
5. STRICT với uuuu từ chối 29/02/2023.

Điều cần quyết định là **loại dữ liệu muốn chấp nhận**, không phải “uuuu lúc nào cũng tốt hơn yyyy”. Khi domain thực sự là era-based chronology, y và G có ý nghĩa đúng. Với LocalDate ISO không có era, uuuu phù hợp hơn.

## 12. Parsing week date: cùng text có thể là hai ngày khác nhau

Pattern **YYYY-'W'ww-e** dùng year, week và day-of-week **theo Locale**. Vì e cũng phụ thuộc Locale, cùng một chuỗi **2020-W01-1** có thể được giải thích khác nhau:

- Theo quy tắc ISO/UK: tuần 1 năm 2020 bắt đầu **thứ Hai 30/12/2019**; e=1 là thứ Hai.
- Theo US: tuần 1 năm 2020 bắt đầu **Chủ nhật 29/12/2019**; e=1 là Chủ nhật.

Vì vậy, không serialize localized week date mà không ghi **quy tắc tuần đã được áp dụng**.

### Giải pháp an toàn với tuần ISO

DateTimeFormatter.ISO_WEEK_DATE hỗ trợ format và parse ISO week date. Ví dụ:

~~~java
// Mảnh mã:
LocalDate date = LocalDate.parse(
        "2020-W01-1", DateTimeFormatter.ISO_WEEK_DATE);
// Kết quả LocalDate là 2019-12-30.
~~~

Formatter này dùng hệ thống tuần ISO chứ không phụ thuộc mặc định US/UK. Nó được thiết kế để giữ year-of-week, week number và ISO day-of-week nhất quán.

### Chế độ STRICT cho tuần 53

Không phải week-based-year nào cũng có tuần 53. ISO week-based-year 2020 có tuần 53, nhưng 2021 không có tuần 53. Parse strict một chuỗi kiểu **2021-W53-1** theo ISO_WEEK_DATE sẽ thất bại. Không nên tùy tiện cho tuần 53 lăn sang năm tiếp theo nếu dữ liệu là khóa báo cáo hoặc lịch nghiệp vụ.

## 13. Ví dụ hoàn chỉnh 4 — cùng week date string, hai Locale

Tạo file **LocaleWeekParsingDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class LocaleWeekParsingDemo {
    public static void main(String[] args) {
        DateTimeFormatter uk = DateTimeFormatter
                .ofPattern("YYYY-'W'ww-e", Locale.UK)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter us = DateTimeFormatter
                .ofPattern("YYYY-'W'ww-e", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

        String text = "2020-W01-1";
        System.out.println("ISO="
                + LocalDate.parse(text, DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("UK=" + LocalDate.parse(text, uk));
        System.out.println("US=" + LocalDate.parse(text, us));

        try {
            LocalDate.parse("2021-W53-1",
                    DateTimeFormatter.ISO_WEEK_DATE);
        } catch (DateTimeParseException expected) {
            System.out.println("invalidISOWeek=DateTimeParseException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 LocaleWeekParsingDemo.java
java LocaleWeekParsingDemo
~~~

Stdout:

~~~text
ISO=2019-12-30
UK=2019-12-30
US=2019-12-29
invalidISOWeek=DateTimeParseException
~~~

Dòng ISO/UK và dòng US khác nhau **một ngày** dù chuỗi input giống hệt. Điều này đặc biệt nguy hiểm khi một service format với Locale.US nhưng service khác parse với Locale.UK. Nếu giao thức cần week date có thể trao đổi tin cậy, hãy thống nhất ISO_WEEK_DATE hoặc công bố quy tắc WeekFields riêng của giao thức.

## 14. Week-based-year ISO có thể có tuần 53

Nhiều người giả định mỗi năm có 52 tuần. Nhưng trong ISO week-based calendar, một số năm có **53** tuần.

Ví dụ:

- ISO week-year 2019 có 52 tuần.
- ISO week-year 2020 có 53 tuần.
- ISO week-year 2021 có 52 tuần.
- 31/12/2020 thuộc 2020-W53.
- 01/01/2021 vẫn thuộc 2020-W53.
- 04/01/2021 mới là 2021-W01.

**Không hardcode số tuần tối đa = 52** khi validate week-based-year. Đọc trường số tuần từ LocalDate/IsoFields, hoặc dùng ISO_WEEK_DATE với resolver STRICT để validate tuần hợp lệ của năm.

### WeekFields.ISO so với IsoFields

Hai cách trực tiếp tính ISO week year/week:

~~~java
// Mảnh mã:
int yearA = date.get(IsoFields.WEEK_BASED_YEAR);
int weekA = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);

int yearB = date.get(WeekFields.ISO.weekBasedYear());
int weekB = date.get(WeekFields.ISO.weekOfWeekBasedYear());
~~~

Với LocalDate và quy tắc ISO, hai cặp tương ứng cùng thông tin năm tuần và số tuần. **IsoFields** biểu thị các trường ISO trực tiếp; **WeekFields** còn cho phép những quy tắc khác, ví dụ bắt đầu tuần vào Chủ nhật và yêu cầu 1 ngày tối thiểu.

### Quy tắc tuần tùy chỉnh minh bạch

~~~java
// Mảnh mã:
WeekFields sundayRules = WeekFields.of(
        DayOfWeek.SUNDAY, 1);

int customWeekYear = date.get(sundayRules.weekBasedYear());
int customWeekNo = date.get(sundayRules.weekOfWeekBasedYear());
~~~

Cách này thể hiện rõ điều kiện của hệ thống, không phụ thuộc Locale mặc định trong runtime.

## 15. Ứng dụng: tạo khóa nhóm theo tuần mà không làm hỏng ngày lịch

Một lỗi phổ biến trong báo cáo là tạo khóa tuần bằng **yyyy-ww**. Year-of-era là năm lịch, trong khi w là số tuần của week-based-year; hai trường có thể mâu thuẫn quanh năm mới. Lỗi khác là dùng **YYYY-MM-dd** như khóa ngày.

**Mẫu đúng nếu cần nhóm tuần ISO:**

1. Mỗi event được xác định thành **LocalDate theo múi giờ báo cáo**.
2. Từ LocalDate ấy, lấy **IsoFields.WEEK_BASED_YEAR** và **IsoFields.WEEK_OF_WEEK_BASED_YEAR**.
3. Ghép thành khóa có cấu trúc hoặc format thống nhất: ví dụ 2020-W53.
4. Không đưa month/day từ calendar vào một khóa có Y.
5. Không dùng WeekFields của một Locale này rồi ghép với e/w từ một Locale khác.

Nếu một event được lưu là Instant, phải quyết định **ZoneId của doanh nghiệp** trước khi lấy LocalDate. Báo cáo theo ngày của cửa hàng tại Việt Nam không nhất thiết dùng cùng LocalDate với UTC, vì một số Instant nằm sát thời điểm chuyển ngày.

### Tính nhất quán khi nhóm

Nếu lưu hai field int **weekYear** và **weekNumber** thay cho chuỗi, nên coi chúng là một cặp. Chẳng hạn 2020-W53 hợp lệ nhưng 2021-W53 không hợp lệ trong ISO. Khi nhận input từ API, phải validate cả hai dựa trên quy tắc đúng, chứ không chỉ kiểm tra 1<=week<=53.

## 16. Ví dụ hoàn chỉnh 5 — báo cáo theo tuần ISO

Tạo file **IsoWeekReportingDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.IsoFields;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class IsoWeekReportingDemo {
    public static void main(String[] args) {
        List<LocalDate> dates = List.of(
                LocalDate.of(2020, 12, 30),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2021, 1, 4),
                LocalDate.of(2022, 1, 1)
        );

        Map<String, Long> grouped = dates.stream().collect(
                Collectors.groupingBy(
                        date -> String.format(Locale.ROOT, "%04d-W%02d",
                                date.get(IsoFields.WEEK_BASED_YEAR),
                                date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR)),
                        TreeMap::new,
                        Collectors.counting()
                )
        );

        LocalDate lastDay = LocalDate.of(2020, 12, 31);
        DateTimeFormatter wrong = DateTimeFormatter
                .ofPattern("YYYY-MM-dd", Locale.US);

        System.out.println("grouped=" + grouped);
        System.out.println("calendar="
                + lastDay.format(DateTimeFormatter.ISO_LOCAL_DATE));
        System.out.println("weekDate="
                + lastDay.format(DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("badMixedPattern="
                + lastDay.format(wrong));
    }
}
~~~

Chạy:

~~~text
javac --release 17 IsoWeekReportingDemo.java
java IsoWeekReportingDemo
~~~

Stdout:

~~~text
grouped={2020-W53=3, 2021-W01=1, 2021-W52=1}
calendar=2020-12-31
weekDate=2020-W53-4
badMixedPattern=2021-12-31
~~~

**Tại sao báo cáo đúng?**

- Ba ngày 30/12/2020, 31/12/2020 và 01/01/2021 đều thuộc ISO week-year 2020, tuần 53.
- Ngày 04/01/2021 thuộc ISO 2021-W01.
- Ngày 01/01/2022 thuộc ISO 2021-W52.
- TreeMap đảm bảo thứ tự khóa để stdout xác định.
- Mẫu **YYYY-MM-dd** trong Locale.US tạo một chuỗi trông như ngày lịch **2021-12-31** từ LocalDate thực **2020-12-31**. Đây là minh chứng cụ thể cho lỗi chữ hoa.

**Lưu ý:** String.format với bốn chữ số là mẫu trình bày cho các năm hiện đại trong ví dụ. Nếu miền nghiệp vụ trải sang năm âm hoặc trên 9999, nên dùng formatter ISO thích hợp hoặc một value object cho cặp weekYear/weekNumber thay vì giả định năm luôn đúng bốn chữ số.

## 17. Từ Instant sang LocalDate: chọn ZoneId trước khi tính u/y/Y

Pattern u/y/Y đều có ý nghĩa trên **ngày lịch đã được xác định**. Một Instant gần nửa đêm có thể thuộc hai LocalDate khác nhau khi nhìn từ hai ZoneId.

Ví dụ Instant **2021-01-01T00:30:00Z**:

- Theo UTC, LocalDate là **2021-01-01**, năm lịch 2021.
- Theo America/Los_Angeles (mùa đông 2020), LocalDate là **2020-12-31**, năm lịch 2020.
- Cả hai ngày này đều thuộc **ISO week-year 2020, week 53**.

Vì vậy trước khi chọn calendar-year, week-year hay reporting period của một event, cần quyết định **múi giờ báo cáo**. Chọn uuuu thay vì YYYY chỉ sửa đúng loại năm; nó không sửa được lỗi lấy ngày theo nhầm ZoneId.

## 18. Ví dụ hoàn chỉnh 6 — timezone và hai loại năm

Tạo file **InstantCalendarWeekDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.IsoFields;

public class InstantCalendarWeekDemo {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2021-01-01T00:30:00Z");

        LocalDate utc = event.atZone(ZoneOffset.UTC).toLocalDate();
        LocalDate losAngeles = event
                .atZone(ZoneId.of("America/Los_Angeles"))
                .toLocalDate();

        System.out.println("UTC.date=" + utc);
        System.out.println("LA.date=" + losAngeles);
        System.out.println("UTC.calendarYear=" + utc.getYear());
        System.out.println("LA.calendarYear=" + losAngeles.getYear());
        System.out.println("UTC.isoWeekYear="
                + utc.get(IsoFields.WEEK_BASED_YEAR));
        System.out.println("LA.isoWeekYear="
                + losAngeles.get(IsoFields.WEEK_BASED_YEAR));
        System.out.println("UTC.weekDate="
                + utc.format(DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("LA.weekDate="
                + losAngeles.format(DateTimeFormatter.ISO_WEEK_DATE));
    }
}
~~~

Chạy:

~~~text
javac --release 17 InstantCalendarWeekDemo.java
java InstantCalendarWeekDemo
~~~

Stdout:

~~~text
UTC.date=2021-01-01
LA.date=2020-12-31
UTC.calendarYear=2021
LA.calendarYear=2020
UTC.isoWeekYear=2020
LA.isoWeekYear=2020
UTC.weekDate=2020-W53-5
LA.weekDate=2020-W53-4
~~~

**Giải thích:** Một Instant có thể là ngày 1/1 ở UTC nhưng vẫn là 31/12 ở Los Angeles. Sau khi xác định LocalDate theo từng vùng, quy tắc năm lịch và năm ISO theo tuần được áp dụng nhất quán. Dùng LocalDate của vùng business thực sự khi tính báo cáo, không mặc định zone của máy chủ.

## 19. Định dạng, parsing, Locale và chronology

Một formatter có thể có nhiều thành phần ảnh hưởng ngữ nghĩa:

- **Pattern**: chọn các field cần format/parse, như u, y, Y, w, e, G.
- **Locale**: ảnh hưởng chữ tên era/thứ và **định nghĩa tuần khi dùng Y/w/e**.
- **Chronology**: quy tắc lịch và era; các ví dụ BCE/CE trong bài dùng chronology ISO mặc định.
- **ResolverStyle**: điều khiển quá trình kiểm tra/resolve từ field sang ngày.
- **ZoneId**: khi format/parse một thời điểm có zone, điều khiển phép biểu diễn địa phương theo contract.
- **DecimalStyle**: các ký hiệu chữ số và dấu; không phải yếu tố thay đổi loại năm.

DateTimeFormatter **immutable** và **thread-safe**, nên có thể tái sử dụng formatter đã xác định pattern/Locale/resolver style. Không dựa vào thay đổi Locale mặc định của request hoặc máy chủ để điều chỉnh đầu ra tùy hứng.

### Khi viết API hoặc schema

Cần định nghĩa rõ:

1. Dữ liệu là **calendar date** hay **week date**?
2. Nếu calendar date, có cần BCE/CE không? Dùng proleptic ISO hay year-of-era + era?
3. Nếu week date, tuần theo ISO hay quy tắc vùng? Ngày bắt đầu tuần, minimal days?
4. Locale của formatter có được truyền rõ không?
5. Input có được parse theo STRICT không? Ngày không hợp lệ có bị từ chối?
6. Có chuyển Instant sang LocalDate theo ZoneId đúng trước khi nhóm không?
7. Có kiểm thử ranh giới tháng 12 và tháng 1, năm 52/53 tuần không?

Các câu hỏi này là **hợp đồng dữ liệu**, không phải lựa chọn trang trí của mẫu hiển thị.

## 20. Những lỗi phổ biến

### 20.1. Dùng YYYY-MM-dd để in ngày

Đây là lỗi nguy hiểm nhất: Y chọn năm theo tuần, còn MM/dd chọn tháng/ngày lịch. Một số ngày cuối năm bị in với năm khác. Dùng ISO_LOCAL_DATE hoặc uuuu-MM-dd.

### 20.2. Dùng yyyy-ww cho khóa tuần

yyyy là year-of-era của calendar; ww là tuần của week-based-year. Chúng không phải một cặp thuộc cùng hệ thống. Dùng Y với w theo quy tắc xác định, hoặc tốt nhất dùng IsoFields với ISO.

### 20.3. Nghĩ yyyy và uuuu tương đương mọi lúc

Chúng chỉ thường in cùng số khi ngày nằm trong era AD. Năm 0, năm âm và parsing STRICT có kết quả khác. Nếu dùng y cho BCE, phải có G.

### 20.4. Nghĩ Y là năm ISO tự động

Trong pattern DateTimeFormatter, Y/w/e dựa vào locale week fields; US có thể khác ISO. Dùng ISO_WEEK_DATE hoặc IsoFields/WeekFields.ISO để cố định chuẩn.

### 20.5. Không chọn Locale rõ ràng

Định dạng YYYY-'W'ww-e với Locale mặc định có thể khác giữa máy dev và production. Cố định Locale hoặc WeekFields theo nghiệp vụ.

### 20.6. Dùng w thay cho W hoặc ngược lại

w là tuần của week-based-year, W là tuần của tháng. Nếu gọi W thay vì w, số có thể chỉ 0..5/6 chứ không phải 1..52/53. Đọc đúng bảng pattern.

### 20.7. Dùng e rồi suy ra thứ Hai luôn bằng 1

e là localized day-of-week. Với US, Chủ nhật thường bằng 1. Nếu cần ISO day-of-week Monday=1, dùng ChronoField.DAY_OF_WEEK hoặc ISO_WEEK_DATE.

### 20.8. Tưởng một năm ISO luôn có 52 tuần

Năm theo tuần ISO 2020 có tuần 53. Không hardcode tuần tối đa=52. Cần validate theo năm cụ thể.

### 20.9. Parse yyyy-MM-dd bằng STRICT nhưng bỏ G

YEAR_OF_ERA không có ERA có thể không resolve thành LocalDate. Dùng uuuu hoặc cung cấp G đúng khi cần era.

### 20.10. Chỉ test các ngày giữa năm

Trong khoảng tháng 3 tới tháng 10 của các năm AD, u/y/Y thường cho số năm giống nhau. Phải test **cuối tháng 12/đầu tháng 1**, ngày BCE, leap day và năm 53 tuần.

### 20.11. Sửa được format nhưng vẫn tính LocalDate sai ZoneId

Báo cáo event theo một ZoneId nghiệp vụ. Một Instant có thể thuộc ngày 31/12 ở vùng này nhưng 1/1 ở vùng khác; việc chọn uuuu không sửa lỗi vùng.

### 20.12. Ghi week-year nhưng gọi field là calendarYear

Tên field hoặc column sai nghĩa dẫn đến lỗi downstream. Đặt tên **calendarYear**, **yearOfEra**, **isoWeekYear**, **isoWeekNo** rõ ràng.

### 20.13. Cho rằng 2-digit YY phù hợp với mọi năm

Hai chữ Y vẫn chỉ week-based-year, không trở thành calendar year. Các year pattern rút gọn có quy tắc parse riêng cho năm hai chữ số. Với dữ liệu cần bảo toàn năm đầy đủ và thời gian dài, dùng format có năm đầy đủ hoặc type có cấu trúc.

### 20.14. Ghép số tuần với số năm từ hai quy tắc khác nhau

Một phần được tính theo Locale.US, phần kia theo ISO; chuỗi có thể biểu diễn tuần sai hoặc không thể round-trip. Chọn cùng WeekFields cho tất cả field.

## 21. Checklist QA cho hệ thống ngày giờ

- Dữ liệu cần **calendar year**, **year-of-era** hay **week-based-year**?
- Nếu cần LocalDate ISO, đã dùng ISO_LOCAL_DATE/uuuu-MM-dd chưa?
- Nếu cần era, đã có G và YEAR_OF_ERA đúng chưa?
- Khi parse nghiêm ngặt, đã thử trường hợp yyyy thiếu era chưa?
- Có nhận nhầm SMART normalization thành input hợp lệ không?
- Nếu dùng Y, đã xác định Locale hoặc WeekFields rõ chưa?
- Nếu dùng w, có gắn đúng weekBasedYear từ cùng bộ quy tắc không?
- Đã phân biệt w và W, e và E chưa?
- Đã test 2019-12-30, 2020-12-31, 2021-01-01 và một năm có tuần 53?
- Đã test cả US và ISO nếu phần mềm chạy ở nhiều locale?
- Nếu dữ liệu gốc là Instant, đã chọn ZoneId business trước khi lấy LocalDate?
- Có dùng STRICT/ISO_WEEK_DATE khi validate input week date không?
- Các formatter có được tái sử dụng dưới dạng immutable và không dựa vào default Locale ngầm định không?

## 22. Câu hỏi tự kiểm tra

**Câu 1.** u, y và Y khác nhau thế nào?

*Đáp án:* u là proleptic YEAR; y là YEAR_OF_ERA; Y là localized week-based-year.

**Câu 2.** Tại sao yyyy và uuuu thường giống nhau với năm 2024?

*Đáp án:* Trong chronology ISO và era AD, year-of-era bằng proleptic year; chúng khác nhau ở BCE/year 0 hoặc khi parse STRICT không có era.

**Câu 3.** LocalDate.of(0,1,1) ứng với năm nào?

*Đáp án:* Proleptic year 0, tương ứng **1 BCE** trong ISO chronology; y=1, G=BC.

**Câu 4.** 2019-12-30 thuộc ISO week-based-year nào?

*Đáp án:* 2020, tuần 1, thứ Hai (2020-W01-1). Calendar year vẫn là 2019.

**Câu 5.** 2021-01-01 thuộc ISO tuần nào?

*Đáp án:* 2020-W53-5, không phải 2021-W01.

**Câu 6.** YYYY-MM-dd có phù hợp để làm khóa ngày lịch không?

*Đáp án:* Không. Nó trộn năm theo tuần với tháng/ngày của calendar. Dùng ISO_LOCAL_DATE hoặc uuuu-MM-dd.

**Câu 7.** Tại sao Locale.US có thể cho year Y khác Locale.UK?

*Đáp án:* Vì quy tắc tuần khác nhau về ngày bắt đầu tuần và số ngày tối thiểu của tuần 1.

**Câu 8.** Pattern W khác w thế nào?

*Đáp án:* W là week-of-month; w là week-of-week-based-year.

**Câu 9.** Parse 2024-02-29 bằng yyyy-MM-dd với STRICT và thiếu G có chắc thành công không?

*Đáp án:* Không. YEAR_OF_ERA thiếu ERA nên không đủ để resolve thành LocalDate theo STRICT; dùng uuuu-MM-dd hoặc cung cấp G.

**Câu 10.** Muốn trao đổi ISO week date giữa hệ thống, dùng gì?

*Đáp án:* DateTimeFormatter.ISO_WEEK_DATE, hoặc IsoFields/WeekFields.ISO nhất quán; không phụ thuộc default Locale.

**Câu 11.** Vì sao 2023-02-29 với SMART có thể biến thành 2023-02-28?

*Đáp án:* SMART có chính sách resolve điều chỉnh ngày không tồn tại; nếu cần từ chối, dùng STRICT với bộ field phù hợp.

**Câu 12.** Một Instant có thể cho calendar year khác nhau theo hai vùng không?

*Đáp án:* Có. Khi đổi sang LocalDate ở các ZoneId khác nhau sát nửa đêm, ngày và năm lịch có thể khác.

## 23. Thực hành nâng cao và hướng mở rộng

- Thiết kế type **IsoWeekKey(int weekYear, int weekNumber)**, validate rằng weekNumber có tồn tại trong weekYear theo ISO; không dùng riêng calendarYear.
- Với JSON/DB, đặt tên trường **date** (ISO calendar date) khác **isoWeekYear** và **isoWeekNumber**; đảm bảo migration không âm thầm chuyển năm theo tuần thành năm lịch.
- Khi hiển thị cho người dùng, có thể chọn localized week notation, nhưng **đừng dùng cùng chuỗi làm khóa trao đổi** nếu hai bên có Locale khác nhau.
- Trong report theo thị trường, quyết định ZoneId của thị trường và quy tắc tuần phù hợp trước khi chuyển Instant thành LocalDate, rồi mới nhóm.
- Nếu ứng dụng hỗ trợ chronology khác ISO, kiểm tra lại ý nghĩa G/y; không mặc nhiên áp công thức BCE của ISO cho mọi hệ lịch.
- Với hệ thống đa ngôn ngữ, thêm các regression test cuối năm, không chỉ snapshot mẫu từ tháng 6.
- Một báo cáo chạy lại bằng JDK/tzdb/locale data mới có thể khác về quy tắc localized week nếu dùng Locale ngầm định; để reproducibility, lưu và công bố quy tắc ISO hoặc WeekFields cụ thể.

## Tài liệu API chính thức, còn được duy trì

- Oracle Java SE 25 — DateTimeFormatter, bảng ký hiệu pattern và ISO_WEEK_DATE: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Oracle Java SE 25 — ResolverStyle (STRICT, SMART, LENIENT): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/ResolverStyle.html
- Oracle Java SE 25 — WeekFields, first day-of-week và minimal days: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html
- Oracle Java SE 25 — IsoFields, WEEK_BASED_YEAR, WEEK_OF_WEEK_BASED_YEAR: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/IsoFields.html
- Oracle Java SE 25 — ChronoField, YEAR, YEAR_OF_ERA, ERA, DAY_OF_WEEK: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/ChronoField.html
- Oracle Java SE 25 — LocalDate và proleptic ISO calendar: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- Oracle Java SE 25 — DateTimeFormatterBuilder cho formatter với các field được chỉ định tường minh: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html

**Kết luận:** **u** là năm lịch proleptic; **y** là năm trong era, nên cần **G** nếu phải phân biệt BCE/CE; **Y** là năm theo tuần và phụ thuộc quy tắc tuần của Locale. Dùng **uuuu-MM-dd** hoặc **ISO_LOCAL_DATE** cho ngày ISO, và **ISO_WEEK_DATE/WeekFields.ISO/IsoFields** cho dữ liệu theo tuần ISO. Không dùng **YYYY-MM-dd** để xuất ngày lịch, đặc biệt khi dữ liệu nằm sát giao thừa.
