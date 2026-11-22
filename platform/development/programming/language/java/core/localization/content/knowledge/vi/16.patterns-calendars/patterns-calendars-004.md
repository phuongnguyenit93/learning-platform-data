# WeekFields: ngày đầu tuần và số ngày tối thiểu của tuần đầu

Trong Java, `java.time.temporal.WeekFields` mô tả **quy tắc đánh số tuần dựa trên tập quán lịch của một locale**. Hai tham số nền tảng là:

1. **Ngày đầu tuần** (`firstDayOfWeek`): một tuần được tính bắt đầu vào **Thứ hai**, **Chủ nhật**, hoặc một ngày khác?
2. **Số ngày tối thiểu của tuần đầu** (`minimalDaysInFirstWeek`): tuần đầu tiên được tính thuộc tháng/năm mới phải chứa ít nhất **bao nhiêu ngày của tháng/năm đó**?

Hai lựa chọn này ảnh hưởng trực tiếp tới **tuần thứ mấy trong tháng**, **tuần thứ mấy trong năm**, và đặc biệt là **năm-tuần** (*week-based year*) tại ranh giới năm. Một ngày trong tháng 12 có thể thuộc **tuần 1 của năm-tuần kế tiếp**; một ngày đầu tháng 1 có thể thuộc **tuần cuối của năm-tuần trước**.

Ví dụ, với ngày **2021-01-01 (Thứ sáu)**:

- Quy tắc kiểu Mỹ phổ biến: bắt đầu tuần **Chủ nhật**, yêu cầu **ít nhất 1 ngày** của năm mới để tạo tuần đầu. Kết quả: **tuần 1, năm-tuần 2021**.
- Quy tắc ISO 8601: bắt đầu tuần **Thứ hai**, yêu cầu **ít nhất 4 ngày** của năm mới. Kết quả: **tuần 53, năm-tuần 2020**.

Đây không phải lỗi JDK. Đó là **hai định nghĩa tuần khác nhau** áp dụng lên **cùng một ngày**. Trong ứng dụng quốc tế, phải thống nhất định nghĩa trước khi nhóm dữ liệu theo tuần, in báo cáo hoặc tạo khóa tuần.

Bài học sử dụng Java 17+ để làm rõ hai tham số, các trường tuần của `WeekFields`, cách chọn theo `Locale`, khác biệt ISO/US, quan hệ với `DateTimeFormatter` và các lỗi phổ biến.

## 1. `WeekFields` là gì, không phải là gì?

`WeekFields` nằm trong gói `java.time.temporal` và đại diện cho một **bộ quy tắc lịch tuần**. Nó **không** phải lớp chứa một ngày, không thay đổi đồng hồ hệ thống, và không tự chuyển đổi thời điểm hay múi giờ.

Các cách tạo thông dụng:

~~~java
WeekFields iso = WeekFields.ISO;
WeekFields sunday = WeekFields.SUNDAY_START;
WeekFields us = WeekFields.of(Locale.US);
WeekFields germany = WeekFields.of(Locale.GERMANY);
WeekFields custom = WeekFields.of(DayOfWeek.MONDAY, 1);
~~~

Đây là **snippet trong phương thức**, cần import:

~~~java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;
~~~

Ý nghĩa:

- `WeekFields.ISO` định nghĩa **Thứ hai** là ngày đầu tuần, và yêu cầu **4 ngày** trong tuần đầu.
- `WeekFields.SUNDAY_START` định nghĩa **Chủ nhật** là ngày đầu tuần, và yêu cầu **1 ngày** trong tuần đầu.
- `WeekFields.of(locale)` hỏi bộ dữ liệu locale/provider của JDK để lấy tập quán tuần phù hợp.
- `WeekFields.of(DayOfWeek, int)` cho phép đặt chính sách độc lập với locale.

Đối tượng `WeekFields` là **immutable** và thread-safe; có thể sử dụng lại theo cấu hình. Quan trọng hơn, các `TemporalField` lấy từ nó cũng biểu diễn những quy tắc tuần đã chọn.

## 2. Ngày đầu tuần: `firstDayOfWeek`

Tham số này quyết định **ranh giới giữa hai tuần liên tiếp**. Nếu tuần bắt đầu **Thứ hai**, một tuần chạy từ Thứ hai đến Chủ nhật. Nếu bắt đầu **Chủ nhật**, tuần chạy từ Chủ nhật đến Thứ bảy.

Tạo `WeekStartDemo.java`:

~~~java
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekStartDemo {
    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields de = WeekFields.of(Locale.GERMANY);
        WeekFields iso = WeekFields.ISO;

        System.out.println("US: " + us.getFirstDayOfWeek()
                + ", " + us.getMinimalDaysInFirstWeek());
        System.out.println("DE: " + de.getFirstDayOfWeek()
                + ", " + de.getMinimalDaysInFirstWeek());
        System.out.println("ISO: " + iso.getFirstDayOfWeek()
                + ", " + iso.getMinimalDaysInFirstWeek());
    }
}
~~~

~~~bash
javac WeekStartDemo.java
java WeekStartDemo
~~~

Trong môi trường JDK 17+ có dữ liệu tuần thông dụng:

~~~text
US: SUNDAY, 1
DE: MONDAY, 4
ISO: MONDAY, 4
~~~

Hai chuỗi `SUNDAY` và `MONDAY` là tên hằng của enum `DayOfWeek`, không phải tên ngày được dịch sang locale. Đối với các locale khác, hãy đọc trực tiếp dữ liệu trên runtime mà ứng dụng dùng; không đoán từ mã ngôn ngữ.

**Điểm phân biệt:** Một người chọn ngôn ngữ tiếng Anh không đồng nghĩa với việc họ muốn tuần bắt đầu Chủ nhật. Quy tắc tuần thường gắn với **vùng/quốc gia, cấu hình sản phẩm hoặc yêu cầu nghiệp vụ**, không chỉ tên ngôn ngữ.

## 3. Số ngày tối thiểu của tuần đầu là gì?

Giả sử năm mới bắt đầu vào **Thứ sáu** như ngày 2021-01-01.

Với tuần bắt đầu **Thứ hai**, tuần chứa ngày đó là:

~~~text
Thứ hai  2020-12-28
Thứ ba   2020-12-29
Thứ tư   2020-12-30
Thứ năm  2020-12-31
Thứ sáu  2021-01-01
Thứ bảy  2021-01-02
Chủ nhật 2021-01-03
~~~

Tuần này chứa đúng **3 ngày của năm mới**: 01, 02 và 03 tháng 1.

- Nếu `minimalDaysInFirstWeek = 4`, **3 không đủ 4**, nên đây **chưa phải tuần 1 của năm-tuần 2021**. Tuần 1 bắt đầu **Thứ hai 2021-01-04**; 2021-01-01 vẫn nằm trong tuần cuối của **năm-tuần 2020**.
- Nếu `minimalDaysInFirstWeek = 1`, **3 đủ 1**, nên tuần bắt đầu 2020-12-28 đã được tính là tuần 1 của **năm-tuần 2021** (nếu dùng **Thứ hai** làm ngày đầu tuần).

Vì vậy **không chỉ ngày đầu tuần**, mà **cả số ngày tối thiểu** quyết định năm-tuần.

### Điều kiện hợp lệ

`WeekFields.of(DayOfWeek firstDay, int minimalDays)` nhận `minimalDays` trong khoảng **1–7**. Nếu giá trị ngoài phạm vi, phương thức ném `IllegalArgumentException`; ngày đầu tuần phải hợp lệ và không được null.

Ví dụ:

~~~java
WeekFields custom = WeekFields.of(DayOfWeek.MONDAY, 1);
~~~

Đây là cấu hình khác với `WeekFields.ISO` mặc dù **cùng bắt đầu Thứ hai**: ISO yêu cầu 4 ngày, còn cấu hình tùy chỉnh chỉ yêu cầu 1 ngày.

## 4. Hai tham số hoạt động cùng nhau

Để tạo tuần 1 của tháng hoặc năm, Java xem **tuần chứa ngày đầu kỳ** có bao nhiêu ngày thuộc kỳ đó:

1. Xác định ngày đầu tuần theo `firstDayOfWeek`.
2. Tìm tuần có chứa ngày 1 của tháng/năm.
3. Đếm số ngày của tháng/năm mới nằm trong tuần.
4. Nếu số ngày **ít nhất bằng** `minimalDaysInFirstWeek`, tuần đó là **tuần 1**.
5. Nếu chưa đủ, tuần kế tiếp trở thành **tuần 1**.

Quy tắc này được áp dụng ở ranh giới tháng cho `weekOfMonth()` và ranh giới năm cho `weekOfYear()`; riêng cách gán **week-based-year** có thêm khả năng phần cuối tháng 12 chuyển sang **năm-tuần kế tiếp**.

**Ví dụ với ngày 2021-05-01 (Thứ bảy)**:

- Theo ISO (Thứ hai, 4 ngày), tuần 2021-04-26 tới 2021-05-02 chỉ có **2 ngày** trong tháng 5. Do đó **chưa phải tuần 1 của tháng 5**, và `weekOfMonth()` có thể trả **0**.
- Theo US (Chủ nhật, 1 ngày), tuần 2021-04-25 tới 2021-05-01 có **1 ngày** trong tháng 5. Vì đủ 1 ngày, `weekOfMonth()` trả **1**.

Cùng ngày 2021-05-01 nhưng kết quả khác nhau là hoàn toàn có lý do.

## 5. Những `TemporalField` mà `WeekFields` cung cấp

`WeekFields` không trực tiếp có phương thức `weekNumber(LocalDate)`. Thay vào đó, nó cho ta các đối tượng `TemporalField` để hỏi `LocalDate.get(field)` hoặc dùng với `DateTimeFormatterBuilder`.

| Phương thức | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `dayOfWeek()` | Thứ tự ngày **trong tuần cục bộ** | Ngày đầu tuần có giá trị 1 |
| `weekOfMonth()` | Tuần thứ mấy của **tháng lịch** | Có thể bằng **0** gần đầu tháng |
| `weekOfYear()` | Tuần thứ mấy của **năm lịch** | Có thể bằng **0** gần đầu năm |
| `weekOfWeekBasedYear()` | Tuần thứ mấy của **năm-tuần** | Thường 1 đến 52/53 |
| `weekBasedYear()` | **Năm-tuần** tương ứng | Có thể khác năm lịch |

Cần phân biệt đặc biệt:

- `weekOfYear()` gắn với **năm lịch** của ngày đó; ở ranh giới năm, nó có thể bằng 0 hoặc có giá trị cuối năm.
- `weekOfWeekBasedYear()` gắn với **năm-tuần**; phải đi **cùng** `weekBasedYear()` để tạo một định danh tuần hợp lệ.
- `dayOfWeek()` của `WeekFields` là **thứ tự theo ngày bắt đầu tuần đã chọn**; nó không thay đổi giá trị của enum `DayOfWeek`.

Ví dụ để lấy tuần ISO:

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);
WeekFields rule = WeekFields.ISO;

int weekYear = date.get(rule.weekBasedYear());       // 2020
int week = date.get(rule.weekOfWeekBasedYear());     // 53
int localDay = date.get(rule.dayOfWeek());           // 5
~~~

Đoạn trên là **snippet trong method**, cần import `java.time.LocalDate` và `java.time.temporal.WeekFields`.

## 6. `dayOfWeek()`: thứ tự cục bộ khác `DayOfWeek.getValue()`

Enum `DayOfWeek` trong Java tuân theo thứ tự ISO:

~~~text
MONDAY=1, TUESDAY=2, ..., SUNDAY=7
~~~

Nhưng với `WeekFields.of(Locale.US)`, **Chủ nhật** là ngày đầu tuần, nên:

~~~text
SUNDAY=1, MONDAY=2, ..., SATURDAY=7
~~~

Cùng một ngày **Chủ nhật 2021-01-03**:

- `date.getDayOfWeek().getValue()` trả **7** theo enum/ISO.
- `date.get(WeekFields.ISO.dayOfWeek())` trả **7**.
- `date.get(WeekFields.of(Locale.US).dayOfWeek())` trả **1**.

Tạo chương trình độc lập **`LocalizedDayNumberDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class LocalizedDayNumberDemo {
    public static void main(String[] args) {
        LocalDate sunday = LocalDate.of(2021, 1, 3);
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        System.out.println(sunday.getDayOfWeek());
        System.out.println(sunday.getDayOfWeek().getValue());
        System.out.println(sunday.get(us.dayOfWeek()));
        System.out.println(sunday.get(iso.dayOfWeek()));
    }
}
~~~

~~~bash
javac LocalizedDayNumberDemo.java
java LocalizedDayNumberDemo
~~~

Kết quả:

~~~text
SUNDAY
7
1
7
~~~

**Không** tự sử dụng `getDayOfWeek().getValue()` để xây một lịch có cột **Chủ nhật đứng đầu**, nếu thuật toán thực sự muốn đánh số cột từ 1 theo locale. Hãy dùng `WeekFields.dayOfWeek()` hoặc chuyển đổi rõ ràng.

Ngược lại, nếu giao thức của ứng dụng công bố ngày trong tuần theo ISO 1–7, hãy giữ `DayOfWeek.getValue()`, không thay đổi ý nghĩa chỉ vì locale của người dùng.

## 7. `weekOfMonth()`: tại sao có tuần 0?

Theo `WeekFields.ISO`, tháng 5 năm 2021 bắt đầu vào **Thứ bảy**. Hai ngày 1 và 2 tháng 5 thuộc một tuần bắt đầu từ **Thứ hai 26/4** và chỉ có **2 ngày của tháng mới**. Vì vậy tuần đó không đủ 4 ngày để trở thành tuần 1 của tháng 5.

Ví dụ **`WeekOfMonthDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekOfMonthDemo {
    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        for (int day : new int[]{1, 2, 3}) {
            LocalDate date = LocalDate.of(2021, 5, day);
            System.out.printf("%s US=%d ISO=%d%n",
                    date,
                    date.get(us.weekOfMonth()),
                    date.get(iso.weekOfMonth()));
        }
    }
}
~~~

~~~bash
javac WeekOfMonthDemo.java
java WeekOfMonthDemo
~~~

Kết quả với quy tắc Mỹ thông dụng:

~~~text
2021-05-01 US=1 ISO=0
2021-05-02 US=2 ISO=0
2021-05-03 US=2 ISO=1
~~~

**Tuần 0 không phải lỗi dữ liệu.** Nó biểu diễn phần đầu tháng chưa thỏa tiêu chí của tuần đầu tiên. Khi hiển thị “tuần thứ mấy trong tháng”, ứng dụng phải quyết định muốn:
- giữ đúng giá trị `WeekFields.weekOfMonth()`, kể cả tuần 0;
- hay đánh số **các hàng trên lịch** từ 1 (một quy ước UI khác);
- hay hiển thị các **khoảng ngày** thay vì chỉ con số tuần.

Tránh cộng 1 vào kết quả một cách máy móc: làm vậy chỉ che giấu khác biệt quy tắc và có thể gây trùng số tuần.

## 8. `weekOfYear()` không đồng nghĩa `weekOfWeekBasedYear()`

Đây là lỗi quan trọng nhất khi tổng hợp báo cáo theo tuần.

Với ngày **2021-01-01** theo ISO:

- Năm lịch: **2021**.
- `weekOfYear()`: **0**, vì tuần chứa ngày 1/1 chưa đủ 4 ngày thuộc năm 2021.
- `weekBasedYear()`: **2020**.
- `weekOfWeekBasedYear()`: **53**.

Với quy tắc Mỹ thông dụng cho đúng ngày ấy:

- Năm lịch: **2021**.
- `weekOfYear()`: **1**.
- `weekBasedYear()`: **2021**.
- `weekOfWeekBasedYear()`: **1**.

Trong logic báo cáo:
- Nếu cần **một nhãn tuần nhất quán có thể chạy xuyên qua tháng 12/tháng 1**, dùng **cặp `weekBasedYear + weekOfWeekBasedYear`**.
- Nếu thực sự đang hỏi “tuần thứ mấy **trong năm lịch này**”, `weekOfYear` có ngữ nghĩa riêng, bao gồm khả năng tuần 0.
- Không lấy `date.getYear()` ghép với `weekOfWeekBasedYear()` rồi coi là định danh tuần chuẩn.

### Ví dụ có thể chạy

Tạo **`WeekFieldsBoundaryDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekFieldsBoundaryDemo {
    private static String label(LocalDate date, WeekFields fields) {
        int weekBasedYear = date.get(fields.weekBasedYear());
        int week = date.get(fields.weekOfWeekBasedYear());
        int calendarWeek = date.get(fields.weekOfYear());

        return weekBasedYear + "-W" + week + " / y" + calendarWeek;
    }

    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        for (String input : new String[]{
                "2020-12-31", "2021-01-01", "2021-01-04"}) {
            LocalDate date = LocalDate.parse(input);
            System.out.println(date + " US=" + label(date, us)
                    + " ISO=" + label(date, iso));
        }
    }
}
~~~

~~~bash
javac WeekFieldsBoundaryDemo.java
java WeekFieldsBoundaryDemo
~~~

Kết quả trên JDK với quy tắc US phổ biến:

~~~text
2020-12-31 US=2021-W1 / y53 ISO=2020-W53 / y53
2021-01-01 US=2021-W1 / y1 ISO=2020-W53 / y0
2021-01-04 US=2021-W2 / y2 ISO=2021-W1 / y1
~~~

Dòng đầu rất đáng chú ý: **2020-12-31 thuộc năm lịch 2020**, nhưng theo US nó đã nằm trong **năm-tuần 2021**. Vì thế nếu nhóm bằng `calendarYear=2020, week=1` bạn có thể tạo một nhóm báo cáo sai hoặc trùng.

## 9. Tuần đầu năm ISO: quy tắc “ít nhất 4 ngày”

Quy tắc ISO 8601 thường được mô tả bằng ba cách tương đương:

- Tuần bắt đầu **Thứ hai**, và tuần 1 là tuần có **ít nhất bốn ngày của năm mới**.
- Tuần 1 là tuần có **ngày 4 tháng 1**.
- Tuần 1 là tuần có **ngày Thứ năm đầu tiên của năm**.

Ví dụ năm 2021:
- 2021-01-01 là Thứ sáu.
- Tuần 2020-12-28 đến 2021-01-03 chỉ có ba ngày thuộc 2021.
- Tuần 1 năm-tuần 2021 bắt đầu vào **2021-01-04**.
- Ngày 2021-01-01 thuộc **2020-W53**.

Một năm-tuần có thể có **52 hoặc 53 tuần**. Đó là lý do mã “2021-W53” không thể tự động coi là một tuần hợp lệ trong mọi định nghĩa. Kiểm tra số tuần tồn tại theo năm-tuần và quy tắc thật sự được dùng.

`WeekFields.ISO` là lựa chọn rõ ràng khi **hợp đồng dữ liệu yêu cầu ISO tuần**, bất kể người dùng đang ở quốc gia nào. `WeekFields.of(locale)` là lựa chọn khi **giao diện lịch nên theo tập quán của người dùng**.

## 10. `WeekFields.of(Locale)` và độ ổn định của locale

Một số locale có thể dùng quy tắc đầu tuần và số ngày tối thiểu khác nhau. Java lấy chúng từ dịch vụ locale trên runtime:

~~~java
WeekFields fields = WeekFields.of(locale);
DayOfWeek first = fields.getFirstDayOfWeek();
int minimal = fields.getMinimalDaysInFirstWeek();
~~~

Đây là snippet; `locale` phải được cung cấp tại nơi dùng. Các locale như `en-US`, `de-DE` thường cho những quy tắc đã minh họa, nhưng dữ liệu của JDK/provider có thể thay đổi giữa phiên bản hoặc cấu hình runtime.

**Không nên coi ngôn ngữ và quốc gia là một.** Locale `en-US` và `en-GB` có thể có quy tắc tuần khác nhau; locale không xác định region có thể dùng dữ liệu fallback. Nếu hệ thống cần một quy tắc tuần bất biến do nghiệp vụ quyết định, hãy cấu hình **ngày đầu tuần + minimal days** một cách tường minh, hoặc dùng `WeekFields.ISO`.

Đối với ứng dụng:
1. **UI lịch cá nhân**: có thể dựa trên `WeekFields.of(userLocale)`.
2. **Báo cáo chuẩn doanh nghiệp**: nên dùng quy tắc được mô tả trong hợp đồng, có thể là ISO dù locale người dùng khác.
3. **Đồng bộ nhiều hệ thống**: trao đổi cả loại quy tắc hoặc cố định ISO để tránh khác nhau khi giải mã con số tuần.

Không được lấy “ngày đầu tuần của thiết bị” làm tiêu chuẩn cho tất cả báo cáo nghiệp vụ nếu hệ thống đã có quy định cố định.

## 11. Tùy chỉnh ngày đầu tuần và minimal days

Có thể tạo chính sách riêng:

~~~java
WeekFields mondayOneDay = WeekFields.of(DayOfWeek.MONDAY, 1);
WeekFields mondayFourDays = WeekFields.of(DayOfWeek.MONDAY, 4);
~~~

Cả hai đều bắt đầu **Thứ hai** nhưng cách chọn tuần 1 khác nhau. Đối với ngày đầu năm 2021:

- `mondayOneDay`: tuần bắt đầu 2020-12-28 có ba ngày trong năm 2021, đủ **1** ⇒ thuộc tuần 1 của **năm-tuần 2021**.
- `mondayFourDays`: ba ngày không đủ **4** ⇒ thuộc tuần 53 của **năm-tuần 2020**.

Tạo **`CustomWeekRuleDemo.java`**:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.WeekFields;

public class CustomWeekRuleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);

        WeekFields one = WeekFields.of(DayOfWeek.MONDAY, 1);
        WeekFields four = WeekFields.of(DayOfWeek.MONDAY, 4);

        System.out.println(one.getFirstDayOfWeek());
        System.out.println(one.getMinimalDaysInFirstWeek());
        System.out.println(date.get(one.weekBasedYear())
                + "-W" + date.get(one.weekOfWeekBasedYear()));
        System.out.println(date.get(four.weekBasedYear())
                + "-W" + date.get(four.weekOfWeekBasedYear()));
    }
}
~~~

~~~bash
javac CustomWeekRuleDemo.java
java CustomWeekRuleDemo
~~~

Kết quả:

~~~text
MONDAY
1
2021-W1
2020-W53
~~~

Thử nghiệm này chứng minh **không thể chỉ biết ngày bắt đầu tuần mà suy ra số tuần**. Cần biết cả tham số thứ hai.

Nếu dự án xây “lịch tài chính” hay “tuần bán hàng”, kiểm tra chính sách đó có thực sự đồng nhất với một cấu hình `WeekFields` không. Một số lịch tài chính dùng kỳ 4-4-5 hoặc quy tắc riêng, cần mô hình nghiệp vụ chuyên biệt, không tự động quy về `WeekFields`.

## 12. Đặt tên tuần đúng khi lưu báo cáo hoặc làm khóa

Giả sử hệ thống lưu dữ liệu nhóm theo tuần. Một thiết kế dễ sai:

~~~text
key = calendarYear + "-" + weekOfWeekBasedYear
~~~

Ở `2021-01-01` theo ISO, nó sẽ tạo `2021-53`. Nhưng ngày này thuộc **năm-tuần 2020**, không phải 2021.

Thiết kế đúng hơn với quy tắc ISO:

~~~java
WeekFields fields = WeekFields.ISO;

int year = date.get(fields.weekBasedYear());
int week = date.get(fields.weekOfWeekBasedYear());

String key = "%04d-W%02d".formatted(year, week);
~~~

Đây là **snippet** trong phương thức, cần import `WeekFields`; biến `date` là `LocalDate` đã xác thực. Với ngày 2021-01-01, `key` là:

~~~text
2020-W53
~~~

Nếu sản phẩm dùng quy tắc US, cặp `weekBasedYear` và `weekOfWeekBasedYear` phải được lấy từ **cùng một** `WeekFields.of(Locale.US)`. Không lấy năm-tuần ISO rồi ghép với tuần US, hoặc lấy năm lịch theo ngữ cảnh khác.

Ngoài ra, nếu cùng hệ thống cho phép **nhiều quy tắc tuần** thì cùng một nhãn như `2021-W01` có thể biểu diễn **những khoảng ngày khác nhau**. Khóa dữ liệu cần bao gồm tên quy tắc hoặc tốt hơn là **ngày bắt đầu và kết thúc của tuần**, được tính theo một chính sách được lưu rõ.

## 13. `DateTimeFormatter` và các ký tự `Y`, `w`, `e`

Java có thể dùng quy tắc tuần theo locale ngay trong pattern ngày giờ:

| Ký hiệu pattern | Ý nghĩa trong `DateTimeFormatter` |
| --- | --- |
| `u` | Năm theo lịch ISO proleptic year |
| `y` | Năm trong kỷ nguyên (*year-of-era*) |
| `Y` | **Năm-tuần được bản địa hóa** (*localized week-based-year*) |
| `w` | **Tuần của năm-tuần** được bản địa hóa |
| `W` | **Tuần của tháng** được bản địa hóa |
| `e` / `c` | Ngày trong tuần theo quy tắc địa phương |
| `E` | Tên thứ trong tuần (ví dụ Mon, Monday) |

Cú pháp `Y` **không đồng nghĩa** với `y` hoặc `u`. Một chuỗi như `YYYY-MM-dd` dùng **năm-tuần** nhưng lại dùng **tháng và ngày lịch**, tức là trộn hai hệ khái niệm.

Ở cuối tháng 12, `YYYY` có thể thành **năm sau**. Đây là lỗi định dạng thường xuất hiện trong nhãn file log hoặc biểu mẫu do nhầm `YYYY` với `yyyy`/`uuuu`.

### Ví dụ runnable

Tạo **`LocalizedWeekPatternDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocalizedWeekPatternDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2020, 12, 31);

        DateTimeFormatter us =
                DateTimeFormatter.ofPattern(
                        "YYYY-'W'ww-e", Locale.US);

        DateTimeFormatter de =
                DateTimeFormatter.ofPattern(
                        "YYYY-'W'ww-e", Locale.GERMANY);

        DateTimeFormatter mixed =
                DateTimeFormatter.ofPattern(
                        "YYYY-MM-dd", Locale.US);

        System.out.println(us.format(date));
        System.out.println(de.format(date));
        System.out.println(mixed.format(date));
    }
}
~~~

~~~bash
javac LocalizedWeekPatternDemo.java
java LocalizedWeekPatternDemo
~~~

Kết quả với quy tắc US/DE phổ biến:

~~~text
2021-W01-5
2020-W53-4
2021-12-31
~~~

Dòng cuối là **ví dụ cảnh báo**: ngày thực tế là **2020-12-31**, nhưng pattern `YYYY-MM-dd` tạo chuỗi `2021-12-31` do phần năm `YYYY` là năm-tuần theo US.

Khi chỉ cần ngày lịch ổn định, có thể dùng:

~~~java
DateTimeFormatter dateFormat =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");
~~~

Hoặc với `LocalDate`, ưu tiên `LocalDate.toString()` hay `DateTimeFormatter.ISO_LOCAL_DATE` cho chuỗi ISO. Khi cần nhãn **tuần**, hãy dùng `Y`/`w`/`e` nhất quán hoặc các trường của một `WeekFields` tường minh.

## 14. So sánh `WeekFields.ISO` với `IsoFields` và `ChronoField`

Trong Java, có nhiều cách truy xuất “tuần”; tên gần giống nhưng ý nghĩa khác nhau.

| API | Định nghĩa |
| --- | --- |
| `WeekFields.ISO` | Quy tắc tuần ISO: Thứ hai, tối thiểu 4 ngày |
| `WeekFields.of(locale)` | Quy tắc tuần theo dữ liệu locale |
| `IsoFields.WEEK_OF_WEEK_BASED_YEAR` | Tuần theo hệ ISO, tương đương mục đích tuần của năm-tuần ISO |
| `IsoFields.WEEK_BASED_YEAR` | Năm-tuần ISO |
| `ChronoField.ALIGNED_WEEK_OF_YEAR` | Chia các ngày trong năm thành nhóm liên tục từ ngày 1/1, **không dựa trên ngày đầu tuần của locale** |
| `ChronoField.ALIGNED_WEEK_OF_MONTH` | Nhóm 7 ngày liên tiếp tính từ đầu tháng, **khác `WeekFields.weekOfMonth()`** |

Ví dụ ngày **2021-01-01**:

~~~text
ISO weekOfYear:                 0
ISO weekOfWeekBasedYear:       53
ISO weekBasedYear:           2020
ALIGNED_WEEK_OF_YEAR:          1
~~~

`ALIGNED_WEEK_OF_YEAR` đếm ngày 1–7 là nhóm 1, ngày 8–14 là nhóm 2, v.v.; đây **không** phải định nghĩa “tuần từ Thứ hai đến Chủ nhật”. Do đó không dùng `ALIGNED_WEEK_OF_YEAR` để thay `WeekFields.weekOfWeekBasedYear()` khi sản phẩm yêu cầu tuần lịch.

### Cách xác nhận bằng code

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);

System.out.println(date.get(
        java.time.temporal.ChronoField.ALIGNED_WEEK_OF_YEAR));
System.out.println(date.get(WeekFields.ISO.weekOfYear()));
System.out.println(date.get(WeekFields.ISO.weekOfWeekBasedYear()));
~~~

Đây là **snippet**, cần import `LocalDate` và `WeekFields`. Kết quả:

~~~text
1
0
53
~~~

`WeekFields.ISO` là cấu hình theo quy tắc; `IsoFields` là nhóm các trường ISO chuyên biệt; `ChronoField.ALIGNED_*` là phân nhóm theo ngày đầu kỳ. Chọn đúng loại cho bài toán.

## 15. Tạo và parse nhãn tuần có ngữ nghĩa rõ ràng

Một nhãn tuần thường gồm:
- **Năm-tuần**, không nhất thiết là năm lịch;
- **Số tuần** trong năm-tuần đó;
- Nếu cần chỉ định một ngày duy nhất, thêm **ngày trong tuần**.

Java có formatter ISO chuẩn:

~~~java
DateTimeFormatter.ISO_WEEK_DATE
~~~

Nó dùng định nghĩa tuần ISO và biểu diễn dạng:

~~~text
2020-W53-5
~~~

Nghĩa là năm-tuần ISO 2020, tuần 53, ngày thứ 5 trong tuần ISO, tương ứng **2021-01-01**.

Tạo **`IsoWeekParseDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public class IsoWeekParseDemo {
    public static void main(String[] args) {
        String source = "2020-W53-5";
        LocalDate parsed =
                LocalDate.parse(source, DateTimeFormatter.ISO_WEEK_DATE);

        System.out.println(parsed);
        System.out.println(DateTimeFormatter.ISO_WEEK_DATE.format(parsed));
    }
}
~~~

~~~bash
javac IsoWeekParseDemo.java
java IsoWeekParseDemo
~~~

Kết quả:

~~~text
2021-01-01
2020-W53-5
~~~

**Lưu ý:** Nhãn chỉ có `2020-W53` mô tả **cả một tuần**, không phải một ngày duy nhất. Nếu muốn biến thành `LocalDate`, phải chọn rõ ngày nào trong tuần (ví dụ Thứ hai bắt đầu tuần) và bộ quy tắc tuần phù hợp. Không tự đoán ngày.

### Pattern theo locale có thể parse lại bằng cùng locale

Ví dụ:

~~~java
DateTimeFormatter us =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.US);

DateTimeFormatter de =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.GERMANY);

System.out.println(LocalDate.parse("2021-W01-6", us));
System.out.println(LocalDate.parse("2020-W53-5", de));
~~~

Đây là **snippet trong một method**, cần import `LocalDate`, `DateTimeFormatter` và `Locale`. Với quy tắc US/DE phổ biến, kết quả là:

~~~text
2021-01-01
2021-01-01
~~~

Mỗi đầu vào dùng **hệ đánh số ngày trong tuần và năm-tuần của locale tương ứng**. Không lấy `2021-W01-6` theo US rồi parse bằng formatter ISO, vì số 6 có ý nghĩa ngày trong tuần khác nhau giữa hai hệ.

## 16. Tính ngày bắt đầu tuần để dựng lịch

Nhiều giao diện muốn biết **ngày đầu tuần** hơn là con số tuần. Có thể dùng `TemporalAdjusters.previousOrSame(fields.getFirstDayOfWeek())`.

Tạo **`WeekStartDateDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekStartDateDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields iso = WeekFields.ISO;

        LocalDate usStart = date.with(
                TemporalAdjusters.previousOrSame(
                        us.getFirstDayOfWeek()));

        LocalDate isoStart = date.with(
                TemporalAdjusters.previousOrSame(
                        iso.getFirstDayOfWeek()));

        System.out.println(usStart);
        System.out.println(isoStart);
    }
}
~~~

~~~bash
javac WeekStartDateDemo.java
java WeekStartDateDemo
~~~

Kết quả:

~~~text
2020-12-27
2020-12-28
~~~

Đây là khoảng cách một ngày giữa tuần US và tuần ISO có chứa 2021-01-01.

**Phân biệt rõ:** `getFirstDayOfWeek()` **chỉ** cho biết ranh giới tuần; nó **không** cần `minimalDaysInFirstWeek` để tính ngày bắt đầu của **tuần đang chứa date**. Tham số minimal days vẫn cần để xác định **nhãn số tuần/năm-tuần** cho tuần đó.

Nếu cần lấy ngày cuối tuần, có thể cộng thêm sáu ngày vào ngày bắt đầu vừa tìm:

~~~java
LocalDate end = start.plusDays(6);
~~~

Đây là snippet; `start` là `LocalDate` đã tính. Giao diện nên trình bày khoảng ngày qua locale, còn hệ thống lưu định danh chuẩn hoặc ngày ISO.

## 17. Dùng cùng một quy tắc ở UI, API và báo cáo

Một dự án thường có nhiều nơi dùng tuần:

- **Date picker**: vị trí Thứ hai/Chủ nhật ở cột đầu tiên;
- **Lịch công việc**: khoảng ngày đầu và cuối tuần;
- **Báo cáo doanh số**: nhãn tuần và phép tổng hợp;
- **Xuất dữ liệu CSV/JSON**: mã định danh tuần;
- **Query database**: grouping theo tuần;
- **Đồng bộ bên ngoài**: so khớp ISO week hoặc quy ước đối tác.

Nếu UI dùng `WeekFields.of(userLocale)`, nhưng backend mặc định ISO và database dùng hàm tuần với quy tắc mặc định khác, **nhãn và khoảng ngày có thể lệch**. Ví dụ một giao dịch 2020-12-31 có thể thuộc `2021-W01` trên UI US nhưng `2020-W53` ở báo cáo ISO.

Hướng thiết kế bền vững:

1. Quy định **nghiệp vụ nào dùng tuần ISO**, nghiệp vụ nào cho phép lịch theo locale.
2. Lưu/chuyển **quy tắc tuần** khi nhãn tuần có ý nghĩa nghiệp vụ lâu dài.
3. Với dữ liệu trao đổi, cân nhắc lưu **ngày đầu tuần** hoặc khoảng [start, end) dưới dạng ngày ISO, kèm timezone nếu dữ liệu bắt đầu từ timestamp.
4. Dùng `weekBasedYear + weekOfWeekBasedYear` lấy từ **cùng một WeekFields** để tạo nhãn.
5. Kiểm thử ngày biên năm và biên tháng, không chỉ ngày giữa năm.

### Tách tuần của date và zone của timestamp

`WeekFields` xử lý quy tắc trên **ngày lịch**, trong khi `Instant` là thời điểm tuyệt đối. Nếu đầu vào là timestamp, trước hết xác định `ZoneId` rồi chuyển:

~~~java
LocalDate localDate = instant.atZone(zone).toLocalDate();
int weekYear = localDate.get(fields.weekBasedYear());
int week = localDate.get(fields.weekOfWeekBasedYear());
~~~

Đây là snippet; `instant`, `zone` và `fields` phải được cung cấp rõ ràng. Cùng một `Instant` có thể rơi vào **hai ngày khác nhau ở hai zone**, nên cũng có thể rơi vào **hai tuần khác nhau**. `WeekFields` không tự chọn zone; đừng truyền timezone ngầm qua locale.

## 18. Hiệu năng, immutable và cache

`WeekFields` là immutable. Tạo `WeekFields.ISO` hoặc `WeekFields.of(locale)` không phải thao tác cần đặt trong vòng lặp tối ưu hóa bằng mọi giá; có thể lưu cấu hình trong một biến và dùng lại:

~~~java
private static final WeekFields BUSINESS_WEEK =
        WeekFields.ISO;
~~~

Đây là snippet đặt trong một class.

Nếu ứng dụng cache kết quả tổng hợp tuần, cần xem **quy tắc tuần** là một chiều của key:
- Ngày hoặc khoảng ngày nguồn;
- `firstDayOfWeek`;
- `minimalDaysInFirstWeek`;
- Zone áp dụng khi nguồn là timestamp;
- Phiên bản chính sách nếu doanh nghiệp thay quy tắc.

Chỉ cache theo `weekNumber` mà không có `weekBasedYear` là sai; tuần 1 xảy ra trong nhiều năm. Chỉ cache theo `year + week` mà không biết dùng ISO hay US cũng có thể sai vì **khác khoảng ngày**.

Formatter số tuần dựa trên `DateTimeFormatter` cũng nên có locale rõ ràng. `DateTimeFormatter` immutable nên có thể chia sẻ nếu cấu hình đã đúng; không lạm dụng `Locale.setDefault(...)` để đổi quy tắc cho từng request.

## 19. Kiểm thử: tập trường hợp tối thiểu

| Trường hợp | Ý cần xác minh |
| --- | --- |
| `WeekFields.ISO` | `MONDAY`, minimal days = 4 |
| `WeekFields.SUNDAY_START` | `SUNDAY`, minimal days = 1 |
| `WeekFields.of(Locale.US)` | Dữ liệu runtime thường là Chủ nhật / 1 |
| `WeekFields.of(Locale.GERMANY)` | Dữ liệu runtime thường là Thứ hai / 4 |
| 2021-01-01 theo ISO | `2020-W53`, `weekOfYear() == 0` |
| 2021-01-01 theo US | `2021-W1` |
| 2020-12-31 theo US | Năm lịch 2020 nhưng năm-tuần 2021 |
| 2021-05-01 theo ISO | `weekOfMonth() == 0` |
| Ngày Chủ nhật theo US | `fields.dayOfWeek() == 1` |
| `ALIGNED_WEEK_OF_YEAR` vs `weekOfYear` | Không nhầm hai định nghĩa |
| `YYYY` ở cuối năm | Có thể đổi sang năm-tuần kế tiếp |
| Parse tuần | Dùng cùng quy tắc locale và kiểm tra tuần có hợp lệ |
| Từ timestamp sang tuần | Zone rõ ràng trước khi lấy `LocalDate` |
| Thay JDK/provider | Kiểm tra dữ liệu tuần theo locale nếu dùng quy tắc địa phương |

### Kiểm thử Java đơn giản không cần thư viện ngoài

Tạo **`WeekFieldsAssertions.java`**:

~~~java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekFieldsAssertions {
    public static void main(String[] args) {
        LocalDate boundary = LocalDate.of(2021, 1, 1);
        WeekFields iso = WeekFields.ISO;
        WeekFields us = WeekFields.of(Locale.US);

        if (boundary.get(iso.weekBasedYear()) != 2020
                || boundary.get(iso.weekOfWeekBasedYear()) != 53) {
            throw new AssertionError("Unexpected ISO week");
        }

        if (boundary.get(us.weekBasedYear()) != 2021
                || boundary.get(us.weekOfWeekBasedYear()) != 1) {
            throw new AssertionError("Unexpected US week");
        }

        LocalDate monthStart = LocalDate.of(2021, 5, 1);
        if (monthStart.get(iso.weekOfMonth()) != 0) {
            throw new AssertionError("Unexpected ISO week of month");
        }

        System.out.println("PASS");
    }
}
~~~

~~~bash
javac WeekFieldsAssertions.java
java WeekFieldsAssertions
~~~

Kết quả trên runtime dùng quy tắc tuần US được nêu:

~~~text
PASS
~~~

Nếu muốn tránh phụ thuộc vào dữ liệu locale của JDK khi kiểm thử thuật toán cố định, dùng `WeekFields.SUNDAY_START` thay cho `WeekFields.of(Locale.US)` ở những test cần quy tắc **Chủ nhật / 1 ngày**, và dành test riêng để xác nhận dữ liệu locale đang dùng.

## 20. Sai lầm thường gặp

1. **“Mọi nơi đều bắt đầu tuần vào Thứ hai.”** Sai. Quy tắc ngày đầu tuần khác nhau giữa các vùng hoặc chính sách sản phẩm.
2. **“Chỉ cần ngày đầu tuần là tính được mọi số tuần.”** Sai. `minimalDaysInFirstWeek` còn quyết định tuần 1.
3. **“Tuần đầu năm luôn chứa ngày 1/1.”** Không theo nghĩa `weekOfWeekBasedYear() == 1` cho ngày 1/1. Với ISO, 2021-01-01 thuộc `2020-W53`.
4. **“Năm-tuần luôn giống năm lịch.”** Sai ở ranh giới; 2020-12-31 theo US có thể thuộc năm-tuần 2021.
5. **“`weekOfYear()` và `weekOfWeekBasedYear()` là một.”** Sai; chúng có cách xử lý biên năm khác nhau.
6. **“Tuần 0 là dữ liệu không hợp lệ.”** Sai; `weekOfMonth` hoặc `weekOfYear` có thể trả 0 hợp lệ theo quy tắc tối thiểu ngày.
7. **“`DayOfWeek.getValue()` luôn là thứ tự cột lịch của locale.”** Sai; enum dùng ISO từ Thứ hai = 1, còn `WeekFields.dayOfWeek()` là cục bộ.
8. **“`ChronoField.ALIGNED_WEEK_OF_YEAR` dùng tuần theo ISO.”** Sai; trường aligned chia năm thành các nhóm 7 ngày từ 1/1.
9. **“`YYYY-MM-dd` là định dạng ngày lịch chuẩn.”** Sai; `YYYY` là **năm-tuần** và có thể cho năm sai so với ngày lịch.
10. **“Locale và zone là một.”** Sai; locale quyết định tập quán tuần/hiển thị, zone chuyển timestamp thành ngày địa phương.
11. **“Chỉ lưu số tuần là đủ cho báo cáo.”** Sai; cần năm-tuần và quy tắc tuần.
12. **“Tuần ISO và tuần US có thể đổi nhãn bằng cách cộng/trừ 1.”** Sai; điểm bắt đầu tuần và biên năm khác nhau.
13. **“Mọi tháng đều bắt đầu ở tuần 1.”** `weekOfMonth()` có thể bằng 0 khi phần đầu tháng chưa đủ minimal days.
14. **“Có `Locale.US` thì hệ thống nghiệp vụ bắt buộc dùng tuần Mỹ.”** Không; dữ liệu nghiệp vụ có thể quy định tuần ISO cố định.

## 21. Bài tập tự kiểm tra

**Câu 1.** `WeekFields.ISO` có ngày đầu tuần nào và cần tối thiểu bao nhiêu ngày để có tuần đầu?

**Đáp án:** `MONDAY` và `4`.

**Câu 2.** Vì sao `2021-01-01` là `2020-W53` theo ISO dù năm lịch là 2021?

**Đáp án:** Tuần 2020-12-28 tới 2021-01-03 chỉ có ba ngày thuộc năm 2021, chưa đủ bốn, nên nằm trong năm-tuần 2020.

**Câu 3.** Với ngày Chủ nhật, tại sao `DayOfWeek.getValue()` trả 7 nhưng `WeekFields.SUNDAY_START.dayOfWeek()` trả 1?

**Đáp án:** Enum `DayOfWeek` dùng thứ tự ISO, còn trường `WeekFields.dayOfWeek()` đánh số theo ngày đầu tuần được chọn.

**Câu 4.** Vì sao `weekOfMonth()` theo ISO có thể trả 0 cho `2021-05-01`?

**Đáp án:** Tuần đầu chứa 1/5 chỉ có hai ngày thuộc tháng 5, chưa đủ yêu cầu bốn ngày.

**Câu 5.** Để lưu mã tuần ISO của `2021-01-01`, dùng `year` nào và `week` nào?

**Đáp án:** `weekBasedYear=2020` và `weekOfWeekBasedYear=53`, tạo nhãn `2020-W53`.

**Câu 6.** Muốn chỉ biết ngày đầu tuần của `2021-01-01` theo quy tắc US, dùng gì?

**Đáp án:** `date.with(TemporalAdjusters.previousOrSame(fields.getFirstDayOfWeek()))`, nhận `2020-12-27` với cấu hình Chủ nhật.

**Câu 7.** Khi nào nên dùng `WeekFields.of(locale)` và khi nào nên dùng `WeekFields.ISO`?

**Đáp án:** Dùng theo locale cho lịch giao diện mang tính địa phương; dùng ISO khi hợp đồng báo cáo hoặc trao đổi yêu cầu tuần ISO ổn định.

**Câu 8.** Một hệ thống xử lý `Instant`, vì sao không gọi thẳng quy tắc tuần mà cần `ZoneId`?

**Đáp án:** `Instant` là thời điểm tuyệt đối; ngày lịch có thể khác theo zone. Phải chuyển thành `LocalDate` trong zone nghiệp vụ rồi mới xác định tuần.

**Câu 9.** Mẫu `YYYY-MM-dd` sai ở đâu nếu mục tiêu là ngày lịch?

**Đáp án:** Chữ `Y` hoa là năm-tuần theo locale; phần `MM-dd` là tháng và ngày lịch, có thể tạo chuỗi mang năm không khớp ngày thực tế.

**Câu 10.** Minimal days = 1 và 4 có tạo cùng kết quả khi ngày đầu tuần đều là Thứ hai không?

**Đáp án:** Không nhất thiết. Ngày 2021-01-01 là một ví dụ: với 1 ngày, nó thuộc năm-tuần 2021; với 4 ngày, nó thuộc năm-tuần 2020.

## 22. Quy trình sử dụng đúng trong dự án

1. **Định nghĩa “tuần” của từng chức năng**: tuần UI, tuần báo cáo, tuần giao tiếp đối tác hay tuần tài chính.
2. **Quyết định hai tham số cốt lõi**: ngày đầu tuần và số ngày tối thiểu của tuần đầu; dùng `WeekFields.ISO` hoặc một cấu hình tường minh khi cần ổn định.
3. **Nếu dùng locale**, lấy `WeekFields.of(userLocale)`, đồng thời kiểm thử các locale mục tiêu và phiên bản runtime.
4. **Khi tạo nhãn tuần**, lấy `weekBasedYear()` và `weekOfWeekBasedYear()` từ **cùng một** `WeekFields`.
5. **Khi dựng lịch**, lấy ngày đầu tuần bằng `getFirstDayOfWeek()` và `TemporalAdjusters`, không suy luận từ số thứ tự enum ISO nếu lịch bắt đầu Chủ nhật.
6. **Khi nguồn là timestamp**, chuyển thành ngày theo `ZoneId` đúng trước khi áp dụng quy tắc tuần.
7. **Khi xuất dữ liệu**, dùng định danh ISO khi đối tác yêu cầu ISO; ghi rõ quy tắc tuần nếu không phải ISO, và tránh pattern `YYYY-MM-dd` cho ngày lịch.
8. **Kiểm thử những ngày biên**, ví dụ cuối tháng 12/đầu tháng 1, đầu tháng rơi vào Thứ bảy/Chủ nhật, và các năm có tuần 53.
9. **Giữ quy tắc nhất quán** giữa backend, UI và các hàm nhóm dữ liệu trong database.

**Ghi nhớ:** `WeekFields` được xác định bởi **hai tham số** — **ngày đầu tuần** và **số ngày tối thiểu của tuần đầu**. `weekOfYear` là tuần trong **năm lịch**; `weekBasedYear` đi cùng `weekOfWeekBasedYear` để xác định **năm-tuần** có thể khác năm lịch. Những khác biệt này quyết định tính đúng của lịch, báo cáo và dữ liệu nhóm theo tuần.

**Tài liệu Java SE 17:** [WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html), [IsoFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/IsoFields.html), [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).