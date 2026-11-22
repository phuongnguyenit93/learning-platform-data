# Ngày đầu năm và ranh giới năm theo tuần

## 1. Vì sao đổi năm lịch mà số năm của tuần chưa đổi?

Ngày `2021-01-01` có năm lịch là 2021 nhưng thuộc tuần ISO `2020-W53`. Ngược lại, ngày `2018-12-31` vẫn ở năm lịch 2018 nhưng thuộc tuần ISO `2019-W01`. Không có ngày nào bị di chuyển: hai cách mô tả đang dùng hai loại năm khác nhau.

Hiểu đúng tình huống “thuộc tuần của năm trước hoặc năm sau” là xét **ranh giới giữa hai năm**: một số ngày đầu tháng 1 có thể thuộc năm theo tuần trước, còn một số ngày cuối tháng 12 có thể thuộc năm theo tuần sau. Không có quy tắc ISO nói rằng chính ngày 1 tháng 1 thuộc năm theo tuần của năm kế tiếp nữa.

Phân biệt hai khái niệm:

- **Năm lịch:** năm chứa ngày trong biểu diễn tháng/ngày, đọc bằng `LocalDate.getYear()`.
- **Năm theo tuần (week-based-year):** năm mà cả tuần được gán vào; đi cùng số tuần trong năm đó.

Nếu báo cáo doanh thu được gom theo tuần, đây là sự khác biệt có thể làm dữ liệu bị đặt sai nhóm ở cuối tháng 12 hoặc đầu tháng 1, dù các ngày giữa năm trông hoàn toàn bình thường.

## 2. Quy tắc ISO giữ nguyên cả tuần

Theo [Java SE 21 — IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html), tuần ISO bắt đầu vào thứ Hai; tuần 1 là tuần có ít nhất bốn ngày nằm trong năm mới. Năm theo tuần thường có 52 tuần và đôi khi có 53 tuần.

Có thể nhận diện tuần 1 ISO bằng tuần chứa ngày 4 tháng 1. Những ngày cuối tháng 12 nằm trong tuần ấy cũng mang năm theo tuần mới. Còn nếu tuần chứa ngày 1 tháng 1 chưa đủ bốn ngày của năm mới, nó vẫn thuộc năm theo tuần cũ.

Ví dụ năm lịch 2021 bắt đầu vào thứ Sáu:

```text
Tuần ISO 2020-W53
Thứ Hai   ...  Thứ Năm     Thứ Sáu    Thứ Bảy    Chủ nhật
2020-12-28 ...  2020-12-31  2021-01-01 2021-01-02 2021-01-03
                                └── chỉ 3 ngày trong năm 2021 ──┘

Tuần ISO 2021-W01 bắt đầu thứ Hai 2021-01-04.
```

Giữ cả tuần ở năm 2020 giúp tuần không bị tách thành “nửa cũ, nửa mới” trong mô hình năm theo tuần. Dù vậy, mọi ngày đầu tháng 1 trong sơ đồ vẫn giữ tháng, ngày và năm lịch 2021 của chúng.

Bảng dưới mô tả mốc bắt đầu tuần 1 ISO theo thứ của ngày 1 tháng 1:

| Ngày 1/1 là | Tuần 1 của năm theo tuần bắt đầu |
| --- | --- |
| Thứ Hai | 1/1 |
| Thứ Ba | 31/12 của năm lịch trước |
| Thứ Tư | 30/12 của năm lịch trước |
| Thứ Năm | 29/12 của năm lịch trước |
| Thứ Sáu | 4/1 |
| Thứ Bảy | 3/1 |
| Chủ nhật | 2/1 |

Khi ngày 1/1 là thứ Sáu, thứ Bảy hoặc Chủ nhật, những ngày trước mốc bắt đầu ở cột phải thuộc năm theo tuần trước. Khi tuần 1 bắt đầu từ tháng 12, các ngày cuối tháng 12 tương ứng thuộc năm theo tuần sau của năm lịch đang xét.

## 3. Lấy đúng cặp năm–tuần trong Java

Với yêu cầu ISO, đọc hai trường đi cùng nhau:

```java
// Minh họa trong một phương thức.
LocalDate date = LocalDate.of(2021, 1, 1);
int weekYear = date.get(IsoFields.WEEK_BASED_YEAR);       // 2020
int week = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);  // 53
```

Cách tương đương qua quy tắc ISO:

```java
WeekFields rule = WeekFields.ISO;
int weekYear = date.get(rule.weekBasedYear());
int week = date.get(rule.weekOfWeekBasedYear());
```

Không tạo khóa bằng `date.getYear()` ghép với `weekOfWeekBasedYear()`: ngày `2021-01-01` sẽ bị gán nhầm nhãn `2021-W53`. Cũng không chỉ lưu số tuần 53, vì nó chưa xác định năm nào và chưa xác định quy tắc nào được dùng.

Năm theo tuần là một thuộc tính đọc từ ngày, không phải yêu cầu thay năm của đối tượng `LocalDate`. Gọi `date.withYear(2020)` chỉ để làm cho năm trùng nhãn tuần sẽ tạo ngày lịch khác và làm sai dữ liệu.

## 4. Chương trình kiểm chứng ranh giới năm

Lưu mã vào `WeekYearBoundaryDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.time.temporal.IsoFields;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekYearBoundaryDemo {
    private static void show(LocalDate date) {
        System.out.printf(Locale.ROOT,
                "%s | calendar=%d | ISO=%d-W%02d | weekday=%s%n",
                date, date.getYear(),
                date.get(IsoFields.WEEK_BASED_YEAR),
                date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR),
                date.getDayOfWeek());
    }

    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2020, 12, 28);
        for (int i = 0; i < 8; i++) {
            show(first.plusDays(i));
        }
        show(LocalDate.of(2018, 12, 31));
        show(LocalDate.of(2019, 1, 1));

        LocalDate january = LocalDate.of(2021, 1, 1);
        System.out.println("ISO string = "
                + january.format(DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("parsed back = "
                + LocalDate.parse("2020-W53-5", DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("hybrid pattern = " + january.format(
                DateTimeFormatter.ofPattern("YYYY-MM-dd", Locale.UK)));
        System.out.println("calendar pattern = " + january.format(
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)));

        WeekFields iso = WeekFields.ISO;
        System.out.println("calendar-year week = " + january.get(iso.weekOfYear()));
        System.out.println("week-year week = "
                + january.get(iso.weekOfWeekBasedYear()));
        LocalDate sunday = LocalDate.of(2020, 12, 27);
        System.out.println("same Sunday ISO = "
                + sunday.get(iso.weekBasedYear()) + "-W"
                + sunday.get(iso.weekOfWeekBasedYear()));
        WeekFields sundayRule = WeekFields.of(java.time.DayOfWeek.SUNDAY, 1);
        System.out.println("same Sunday Sunday/1 = "
                + sunday.get(sundayRule.weekBasedYear()) + "-W"
                + sunday.get(sundayRule.weekOfWeekBasedYear()));

        long days = ChronoUnit.DAYS.between(
                LocalDate.of(2020, 12, 31), LocalDate.of(2021, 1, 1));
        System.out.println("actual days = " + days);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 WeekYearBoundaryDemo.java
java WeekYearBoundaryDemo
```

Kết quả đã kiểm chứng:

```text
2020-12-28 | calendar=2020 | ISO=2020-W53 | weekday=MONDAY
2020-12-29 | calendar=2020 | ISO=2020-W53 | weekday=TUESDAY
2020-12-30 | calendar=2020 | ISO=2020-W53 | weekday=WEDNESDAY
2020-12-31 | calendar=2020 | ISO=2020-W53 | weekday=THURSDAY
2021-01-01 | calendar=2021 | ISO=2020-W53 | weekday=FRIDAY
2021-01-02 | calendar=2021 | ISO=2020-W53 | weekday=SATURDAY
2021-01-03 | calendar=2021 | ISO=2020-W53 | weekday=SUNDAY
2021-01-04 | calendar=2021 | ISO=2021-W01 | weekday=MONDAY
2018-12-31 | calendar=2018 | ISO=2019-W01 | weekday=MONDAY
2019-01-01 | calendar=2019 | ISO=2019-W01 | weekday=TUESDAY
ISO string = 2020-W53-5
parsed back = 2021-01-01
hybrid pattern = 2020-01-01
calendar pattern = 2021-01-01
calendar-year week = 0
week-year week = 53
same Sunday ISO = 2020-W52
same Sunday Sunday/1 = 2021-W1
actual days = 1
```

Những mốc đều cố định nên việc kiểm chứng không phụ thuộc ngày chạy. Các dòng dùng mẫu với Locale minh họa dữ liệu quy tắc tuần của runtime; phần đọc trực tiếp `IsoFields` hoặc `WeekFields.ISO` chỉ rõ yêu cầu ISO.

## 5. Những điểm cần đọc từ kết quả

### Tuần đổi năm ở ngày đầu tuần, không nhất thiết ở ngày 1/1

Bảy ngày từ `2020-12-28` đến `2021-01-03` cùng thuộc `2020-W53`. Sang thứ Hai `2021-01-04`, nhãn đổi thành `2021-W01`. Ở ví dụ ngược lại, thứ Hai `2018-12-31` đã mở tuần `2019-W01`, rồi thứ Ba `2019-01-01` tiếp tục thuộc chính tuần ấy.

Đây là lý do không nên reset số tuần về 1 chỉ vì vừa gặp ngày 1 tháng 1 trong vòng lặp xử lý dữ liệu. Hãy lấy các trường của quy tắc đã chọn từ từng ngày.

### Ngày vẫn là ngày cũ và khoảng cách vẫn bình thường

Dòng `actual days = 1` đo từ `2020-12-31` đến `2021-01-01`. Nhãn năm theo tuần không thêm hoặc bớt thời gian đã trôi qua. Không dùng chênh lệch nhãn tuần như số ngày nếu chưa hiểu quy tắc và ranh giới năm.

Chuỗi `2020-W53-5` đọc lại thành `2021-01-01` với `ISO_WEEK_DATE`. Phần `5` là thứ Sáu theo ISO, giúp xác định một ngày trong tuần. Chỉ cặp `2020-W53` xác định tuần chứ chưa chọn duy nhất một ngày; nếu muốn ngày đầu tuần, phải có quy ước chọn thứ Hai rõ ràng.

### Tuần 0 không phải tuần 53

Ngày `2021-01-01` cho `WeekFields.ISO.weekOfYear()` bằng 0 nhưng `weekOfWeekBasedYear()` bằng 53. [Java SE 21 — WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html) phân biệt trường tuần nằm trong năm lịch và cặp trường của năm theo tuần.

`weekOfYear()` giữ phạm vi năm lịch hiện tại và có thể đánh phần đầu chưa đủ ngày là tuần 0. Cặp năm theo tuần lại đặt cả tuần vào năm tương ứng. Đừng đổi số 0 thành 53 bằng một công thức cố định: năm trước có thể chỉ có 52 tuần, và cách chuyển phải xét đúng năm/quy tắc.

## 6. Tránh ghép năm theo tuần với tháng/ngày lịch

Trong chương trình, mẫu `YYYY-MM-dd` với Locale UK của runtime cho chuỗi `2020-01-01` từ ngày gốc `2021-01-01`. `Y` đang lấy năm theo tuần, trong khi `MM-dd` vẫn lấy tháng/ngày lịch. Chuỗi ghép như vậy có thể trông như một ngày bình thường nhưng đã diễn tả sai ngày nguồn.

Nếu cần ngày lịch, dùng mẫu thích hợp như `uuuu-MM-dd`. Nếu cần ngày ISO theo tuần, dùng `DateTimeFormatter.ISO_WEEK_DATE`. Với một định dạng tuần tùy chỉnh, phải dùng các trường năm theo tuần, số tuần và số thứ theo cùng quy tắc.

Không hiểu `YYYY` là cách viết hoa của `yyyy` hoặc `uuuu`. Khác biệt chỉ dễ lộ ở sát ranh giới năm, nên một bộ thử chỉ dùng các ngày tháng 6 có thể bỏ qua lỗi này.

## 7. Khi quy tắc tuần không phải ISO

Quy tắc `WeekFields.of(DayOfWeek.SUNDAY, 1)` trong chương trình cho Chủ nhật `2020-12-27` là tuần 1 của năm theo tuần 2021, trong khi ISO cho cùng ngày là tuần 52 của năm 2020. Hai kết quả khác nhau do ngày đầu tuần và ngưỡng số ngày tối thiểu, không phải do thay đổi bản thân ngày.

Nếu nghiệp vụ yêu cầu tuần theo vùng người dùng, có thể dùng `WeekFields.of(locale)` và ghi rõ Locale đó. Nếu nghiệp vụ quy định ISO, hãy dùng ISO tường minh thay vì để Locale mặc định quyết định. Không dùng quy tắc này ở nơi tính khóa rồi quy tắc khác ở nơi hiển thị hoặc phân tích chuỗi.

Báo cáo từ `Instant` còn cần chọn vùng báo cáo để chuyển thời điểm thành ngày trước khi tính tuần. Ranh giới năm theo tuần được xét trên ngày địa phương đã chọn, không tự giải quyết việc một thời điểm đang là ngày nào ở các vùng khác nhau.

## 8. Tự kiểm tra trước khi dùng làm khóa báo cáo

Một khóa nhóm tuần cần cặp năm theo tuần và số tuần đúng quy tắc. Nếu cần sắp xếp theo thời gian, có thể giữ hai số hoặc giữ ngày đầu tuần đã tính theo quy tắc; tránh dựa vào chuỗi tùy ý chưa thêm số 0, vì `W10` và `W2` không sắp theo số bằng so sánh ký tự thông thường.

Các trường hợp nên kiểm chứng gồm: ngày 31/12 thuộc năm theo tuần sau, ngày 1/1 thuộc năm theo tuần trước, ngày đầu tiên của tuần 1 và năm có tuần 53. Đồng thời xác nhận việc thay nhãn không làm thay ngày nguồn.

Bài tập: ngày `2022-01-01` là thứ Bảy. Theo ISO, nó thuộc `2021-W52`; thứ Hai `2022-01-03` mới bắt đầu `2022-W01`. Đối chiếu với ví dụ năm 2021 để thấy rằng đầu tháng 1 thuộc năm trước không đồng nghĩa luôn thuộc tuần 53. Số tuần cuối của năm theo tuần trước phải được thư viện tính từ đúng quy tắc.
