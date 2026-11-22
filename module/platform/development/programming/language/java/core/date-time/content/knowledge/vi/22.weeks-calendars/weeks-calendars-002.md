# `WeekFields` và quy tắc tuần phụ thuộc `Locale`

## 1. Cùng một ngày có thể mang số tuần khác nhau

Một báo cáo ghi “tuần 1 năm 2021” chưa mô tả đủ quy tắc chia tuần. Tuần bắt đầu vào thứ Hai hay Chủ nhật? Một tuần chỉ có vài ngày nằm trong năm mới đã được coi là tuần đầu tiên chưa? Hai hệ thống trả lời khác nhau có thể gán số tuần khác nhau cho cùng một ngày mà cả hai vẫn tính đúng theo hợp đồng riêng.

`WeekFields` mô tả quy tắc tuần và cung cấp các `TemporalField` để đọc số thứ trong tuần, tuần trong tháng, tuần trong năm hoặc năm theo tuần. Theo [Java SE 21 — WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html), quy tắc được quyết định bởi hai giá trị: ngày đầu tuần và số ngày tối thiểu của tuần đầu tiên.

Cần phân biệt quy tắc tuần với tên hiển thị của thứ. Đổi ngôn ngữ từ “Monday” sang “thứ Hai” chỉ là thay cách viết; đổi ngày đầu tuần hoặc số ngày tối thiểu sẽ thay cách đánh số tuần.

## 2. Hai thành phần của quy tắc

### Ngày đầu tuần

`getFirstDayOfWeek()` cho biết mốc bắt đầu chu kỳ. Với quy tắc bắt đầu thứ Hai, thứ Hai mang số cục bộ 1; với quy tắc bắt đầu Chủ nhật, Chủ nhật mang số cục bộ 1. Đây là cách đánh số của trường `weekFields.dayOfWeek()`.

### Số ngày tối thiểu trong tuần đầu

`getMinimalDaysInFirstWeek()` nằm trong khoảng 1–7. Nó quyết định phần tuần nằm ở đầu năm/tháng có đủ điều kiện nhận số 1 hay chưa. Nếu chưa đủ, trường tuần trong năm/tháng có thể cho số 0; trong mô hình năm theo tuần, những ngày đó được gán cho năm theo tuần trước.

Ví dụ ISO dùng thứ Hai và ít nhất 4 ngày. Tuần chứa ngày `2021-01-01` bắt đầu từ thứ Hai `2020-12-28`; chỉ có ba ngày của tuần đó nằm trong năm 2021, nên tuần ấy chưa là tuần 1 theo ISO của năm 2021. Ngày đầu năm vẫn thuộc tuần 53 của năm theo tuần 2020.

Nếu quy tắc bắt đầu Chủ nhật và chỉ cần 1 ngày trong năm mới, tuần bắt đầu `2020-12-27` đã đủ điều kiện trở thành tuần 1 của năm theo tuần 2021. Một quyết định nhỏ về ngưỡng đủ ngày làm thay đổi cả năm gắn với tuần.

## 3. Tạo quy tắc từ hợp đồng hoặc từ `Locale`

Ví dụ minh họa trong một phương thức:

```java
WeekFields iso = WeekFields.ISO;
WeekFields sunday = WeekFields.of(DayOfWeek.SUNDAY, 1);
WeekFields userRule = WeekFields.of(userLocale); // userLocale đã được xác định.
```

`WeekFields.ISO` cố định cặp thứ Hai/4 ngày. `WeekFields.SUNDAY_START` là quy tắc Chủ nhật/1 ngày. `WeekFields.of(firstDay, minimalDays)` thích hợp khi báo cáo có hợp đồng quy định rõ hai tham số. `WeekFields.of(locale)` thích hợp khi muốn áp dụng thông lệ tuần của vùng được chọn, chẳng hạn giao diện lịch cho người dùng.

Không suy ra rằng mọi Locale dùng tiếng Anh đều có cùng quy tắc tuần; thông tin vùng cũng quan trọng. Cũng không cần thay Locale mặc định toàn JVM để tính báo cáo của một người dùng: truyền Locale hoặc `WeekFields` thích hợp vào nơi tính toán sẽ làm phụ thuộc rõ ràng hơn.

Các quy tắc lấy từ Locale dựa vào dữ liệu địa phương hóa của runtime. Với hợp đồng trao đổi cố định, nên chọn quy tắc tường minh như ISO hoặc cặp tham số đã thống nhất. Khi chẩn đoán kết quả khác môi trường, hãy in hai tham số thực tế thay vì chỉ nhìn nhãn ngôn ngữ.

## 4. Chọn đúng trường, đặc biệt ở ranh giới năm

| Trường | Ý nghĩa cần dùng đúng |
| --- | --- |
| `dayOfWeek()` | Số thứ 1–7 theo ngày đầu tuần của quy tắc này |
| `weekOfMonth()` | Tuần trong tháng lịch hiện tại; có thể có tuần 0 |
| `weekOfYear()` | Tuần trong năm lịch hiện tại; có thể có tuần 0 |
| `weekOfWeekBasedYear()` | Số tuần thuộc một năm theo tuần |
| `weekBasedYear()` | Năm theo tuần đi kèm số tuần ở dòng trên |

### Năm lịch và năm theo tuần

Năm lịch của `2021-01-01` là 2021. Nhưng theo ISO, cặp năm–tuần là `2020-W53`. Muốn tạo nhãn nhận diện tuần đầy đủ, phải lấy `weekBasedYear()` cùng `weekOfWeekBasedYear()` từ **cùng một** `WeekFields`.

Không ghép `date.getYear()` với `weekOfWeekBasedYear()` rồi gọi đó là tuần ISO. Làm vậy sẽ ghi nhầm `2021-W53` cho ngày đầu năm trong ví dụ. Cũng không ghép số tuần từ quy tắc Chủ nhật với năm theo tuần của quy tắc ISO.

### Vì sao có tuần 0?

`weekOfYear()` phân chia bên trong năm lịch, nên những ngày đầu năm chưa đủ tiêu chuẩn tuần 1 có thể nằm ở tuần 0. Nó không tự đổi năm lịch để đưa các ngày đó sang tuần 53 của năm trước.

`weekOfWeekBasedYear()` và `weekBasedYear()` làm công việc khác: mỗi tuần thuộc một năm theo tuần, có thể vượt qua ranh giới năm lịch. Do đó `2021-01-01` vừa có `weekOfYear() == 0`, vừa có cặp năm theo tuần ISO `2020-W53`. Hai giá trị không mâu thuẫn; chúng trả lời hai câu hỏi khác nhau.

`weekOfMonth()` có ý tương tự đối với đầu tháng. Ví dụ ngày thứ Bảy `2021-05-01` chỉ nằm trong hai ngày đầu tháng của tuần bắt đầu thứ Hai trước đó; với ngưỡng ISO 4 ngày, trường tuần trong tháng cho 0. Đừng mặc định số tuần luôn bắt đầu từ 1 khi dùng các trường này.

## 5. Chương trình kiểm chứng đầy đủ

Lưu mã vào `LocaleWeeksDemo.java`. Chương trình dùng Java 17 trở lên và không cần thư viện ngoài:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class LocaleWeeksDemo {
    private static void printRule(String name, WeekFields rule) {
        System.out.println(name + " = " + rule.getFirstDayOfWeek()
                + ", minimalDays=" + rule.getMinimalDaysInFirstWeek());
    }

    private static void printDate(LocalDate date, WeekFields rule, String name) {
        System.out.printf(Locale.ROOT,
                "%s %s -> day=%d, weekOfYear=%d, weekBased=%d-W%02d%n",
                date, name, date.get(rule.dayOfWeek()),
                date.get(rule.weekOfYear()),
                date.get(rule.weekBasedYear()),
                date.get(rule.weekOfWeekBasedYear()));
    }

    public static void main(String[] args) {
        WeekFields iso = WeekFields.ISO;
        WeekFields sunday = WeekFields.of(DayOfWeek.SUNDAY, 1);
        printRule("explicit ISO", iso);
        printRule("explicit Sunday", sunday);
        printRule("Locale.US", WeekFields.of(Locale.US));
        printRule("Locale.FRANCE", WeekFields.of(Locale.FRANCE));

        LocalDate[] dates = {
            LocalDate.of(2020, 12, 27),
            LocalDate.of(2021, 1, 1),
            LocalDate.of(2021, 1, 4)
        };
        for (LocalDate date : dates) {
            printDate(date, iso, "ISO");
            printDate(date, sunday, "Sunday");
        }

        LocalDate sundayDate = LocalDate.of(2021, 1, 3);
        System.out.println("ISO enum Sunday = "
                + sundayDate.getDayOfWeek().getValue());
        System.out.println("localized Sunday = "
                + sundayDate.get(sunday.dayOfWeek()));
        System.out.println("ISO weekOfMonth on 2021-05-01 = "
                + LocalDate.of(2021, 5, 1).get(iso.weekOfMonth()));

        LocalDate boundary = LocalDate.of(2021, 1, 1);
        String pattern = "YYYY-'W'ww-e";
        System.out.println("pattern US = "
                + boundary.format(DateTimeFormatter.ofPattern(pattern, Locale.US)));
        System.out.println("pattern France = "
                + boundary.format(DateTimeFormatter.ofPattern(pattern, Locale.FRANCE)));
        System.out.println("calendar year = " + boundary.getYear());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LocaleWeeksDemo.java
java LocaleWeeksDemo
```

Kết quả đã kiểm chứng trên runtime dùng trong bài:

```text
explicit ISO = MONDAY, minimalDays=4
explicit Sunday = SUNDAY, minimalDays=1
Locale.US = SUNDAY, minimalDays=1
Locale.FRANCE = MONDAY, minimalDays=4
2020-12-27 ISO -> day=7, weekOfYear=52, weekBased=2020-W52
2020-12-27 Sunday -> day=1, weekOfYear=53, weekBased=2021-W01
2021-01-01 ISO -> day=5, weekOfYear=0, weekBased=2020-W53
2021-01-01 Sunday -> day=6, weekOfYear=1, weekBased=2021-W01
2021-01-04 ISO -> day=1, weekOfYear=1, weekBased=2021-W01
2021-01-04 Sunday -> day=2, weekOfYear=2, weekBased=2021-W02
ISO enum Sunday = 7
localized Sunday = 1
ISO weekOfMonth on 2021-05-01 = 0
pattern US = 2021-W01-6
pattern France = 2020-W53-5
calendar year = 2021
```

Phần quy tắc tường minh cố định thứ Hai/4 và Chủ nhật/1. Các dòng lấy từ `Locale.US`/`Locale.FRANCE` đồng thời in cấu hình để kiểm tra dữ liệu Locale thực tế. Không có ngày hiện tại hoặc vùng máy ngầm tham gia vào các phép tính `LocalDate` của chương trình.

`printf(Locale.ROOT, ...)` chỉ ổn định cách xuất số trong dòng thí nghiệm; nó không thay `WeekFields` đã truyền vào hàm. Nhờ vậy người đọc thấy rõ Locale dùng để ghi chuỗi và quy tắc dùng để tính tuần là hai lựa chọn có thể được chỉ định độc lập.

## 6. Thứ theo ISO và thứ cục bộ không phải cùng một số

Với `DayOfWeek`, `MONDAY.getValue()` luôn là 1 và `SUNDAY.getValue()` là 7. Cấu hình `WeekFields` không sửa các hằng enum này.

Trường `sundayRule.dayOfWeek()` lại lấy Chủ nhật làm 1, thứ Hai làm 2, ... Vì thế chương trình cho cùng Chủ nhật `2021-01-03` hai số khác nhau: enum ISO là 7, số cục bộ là 1. Khi lưu hoặc nhận số thứ từ bên ngoài, phải biết số ấy dùng quy ước nào trước khi chuyển thành `DayOfWeek`.

Không dùng `ordinal()` để biểu diễn số thứ của nghiệp vụ. Tốt hơn là dùng hằng enum khi chọn ngày, còn khi xuất số thì chỉ rõ đang xuất số ISO hay số theo `WeekFields`.

## 7. Mẫu `Y`, `w`, `e` cũng có quy tắc theo Locale

Trong [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html), `Y` là năm theo tuần, `w` là tuần của năm theo tuần, còn `e` có dạng số thứ địa phương hóa. Bởi vậy cùng mẫu `YYYY-'W'ww-e` với hai Locale có thể cho kết quả khác nhau.

Chương trình xuất ngày `2021-01-01` thành `2021-W01-6` theo cấu hình US của runtime và `2020-W53-5` theo cấu hình France. Đây không phải lỗi định dạng; hai bộ định dạng đang dùng quy tắc tuần khác nhau.

Nếu cần định dạng ISO theo tuần, hãy dùng `DateTimeFormatter.ISO_WEEK_DATE` hoặc mô tả rõ các trường của quy tắc ISO. Không xem `Locale.ROOT` hoặc việc mẫu có chữ `W` là bảo đảm quy tắc ISO.

Một lỗi khác là dùng `YYYY-MM-dd` cho ngày lịch thông thường: `Y` đưa năm theo tuần vào cạnh tháng/ngày lịch, nên nhãn có thể sai ở cuối hoặc đầu năm. Với ngày lịch ISO, mẫu thường cần `uuuu-MM-dd`. Chỉ dùng `Y` khi muốn năm theo tuần và đi cùng các trường tuần tương ứng.

## 8. Ứng dụng vào khóa báo cáo và tự kiểm tra

Nếu gom dữ liệu theo tuần, hãy xác định một quy tắc chung cho toàn phép gom. Khóa nên chứa năm theo tuần và số tuần từ cùng quy tắc; nếu dữ liệu có thể dùng nhiều quy tắc, cấu hình quy tắc cũng phải được biết để giải thích khóa. Chỉ lưu số `1` hoặc `53` là không đủ nhận diện một tuần.

Nếu đầu vào ban đầu là `Instant`, cần chọn vùng báo cáo để chuyển thành ngày địa phương trước khi tính trường tuần. `WeekFields` không thay `ZoneId`: vùng quyết định ngày nào đang xét, còn quy tắc tuần quyết định số tuần của ngày đó.

`WeekFields` cũng không phải lịch nghỉ, lịch tài chính 4-4-5 hoặc định nghĩa tuần làm việc. Nó chia và đánh số theo chu kỳ bảy ngày với hai tham số đã nêu. Những quy tắc chuyên biệt vượt phạm vi đó cần mô hình nghiệp vụ riêng.

Khi kiểm tra thuật toán báo cáo tuần, đừng chỉ thử ngày giữa năm. Hãy thử vài ngày cuối tháng 12, đầu tháng 1, ngày đầu tuần và ngày liền trước nó. Tự đối chiếu ba thông tin: năm lịch, cặp năm–tuần và hai tham số của quy tắc.

Bài tập: đọc `2021-01-03` theo `WeekFields.ISO`. Kết quả phải có năm lịch 2021 nhưng cặp năm–tuần `2020-W53`, còn số thứ cục bộ là 7. Sau đó đọc ngày kế tiếp `2021-01-04`: cặp đổi thành `2021-W01`, số thứ về 1. Giải thích được ranh giới này quan trọng hơn việc ghi nhớ một số tuần đơn lẻ.
