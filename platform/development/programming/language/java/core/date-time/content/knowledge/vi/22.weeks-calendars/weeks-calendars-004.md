# IsoFields cho quý và năm theo tuần

## 1. Một ngày có nhiều cách xác định vị trí trong lịch

Ngày 01/01/2021 thuộc quý 1 của năm lịch 2021, nhưng theo cách đánh số tuần ISO, nó nằm trong tuần 53 của **năm theo tuần 2020**. Hai kết quả đều đúng vì dùng hai cách chia lịch khác nhau.

`java.time.temporal.IsoFields` cung cấp các trường và đơn vị dành cho lịch ISO, bổ sung cho những trường thông dụng của `ChronoField`. Hai nhóm nổi bật là:

- Quý trong năm và ngày trong quý.
- Năm theo tuần và số tuần trong năm theo tuần.

Chúng hữu ích khi tạo khóa tổng hợp báo cáo, mô tả một ngày bằng quý/ngày thứ bao nhiêu, hoặc trao đổi mã tuần ISO. Điều quan trọng là dùng đúng **cặp trường đi cùng nhau**, tránh ghép năm lịch với số tuần thuộc một năm theo tuần khác.

## 2. Nhận diện các trường và đơn vị

| Thành viên | Loại | Ý nghĩa |
|---|---|---|
| `QUARTER_OF_YEAR` | `TemporalField` | Quý 1–4 trong năm lịch ISO |
| `DAY_OF_QUARTER` | `TemporalField` | Ngày thứ bao nhiêu tính từ đầu quý, bắt đầu từ 1 |
| `WEEK_BASED_YEAR` | `TemporalField` | Năm theo tuần ISO |
| `WEEK_OF_WEEK_BASED_YEAR` | `TemporalField` | Số tuần 1–52 hoặc 1–53 của năm theo tuần |
| `QUARTER_YEARS` | `TemporalUnit` | Đơn vị quý, bằng 3 tháng trong lịch ISO |
| `WEEK_BASED_YEARS` | `TemporalUnit` | Đơn vị năm theo tuần, khác với một số ngày cố định |

Trường dùng để đọc hoặc điều chỉnh một giá trị qua `get`, `getLong`, `with` hoặc builder. Đơn vị dùng cho các phép cộng/trừ qua `plus` hoặc `minus` khi kiểu nguồn hỗ trợ.

Đừng truyền một trường vào vị trí cần đơn vị hay ngược lại. `date.get(IsoFields.QUARTER_OF_YEAR)` đọc quý; `date.plus(1, IsoFields.QUARTER_YEARS)` cộng một quý.

Không phải mọi kiểu `java.time` đều có đủ dữ liệu cho mọi trường ISO. `LocalDate` có đầy đủ ngày để tính số tuần và ngày trong quý. Một giá trị chỉ có giờ không đủ thông tin, còn hệ lịch không phải ISO cần kiểm tra khả năng hỗ trợ thay vì áp dụng máy móc.

## 3. Quý ISO gắn với năm lịch

Quý được chia cố định theo tháng:

| Quý | Các tháng | Số ngày |
|---|---|---|
| Q1 | Tháng 1–3 | 90 ngày ở năm thường, 91 ngày ở năm nhuận |
| Q2 | Tháng 4–6 | 91 ngày |
| Q3 | Tháng 7–9 | 92 ngày |
| Q4 | Tháng 10–12 | 92 ngày |

Ví dụ:

```java
LocalDate date = LocalDate.of(2024, 3, 31);
int quarter = date.get(IsoFields.QUARTER_OF_YEAR); // 1
int dayInQuarter = date.get(IsoFields.DAY_OF_QUARTER); // 91
```

Đoạn trên minh họa trong một phương thức Java, cần các import tương ứng. Năm 2024 nhuận, nên ngày cuối tháng 3 là ngày thứ 91 của quý 1.

Một quý đơn lẻ không xác định khoảng báo cáo duy nhất: quý 1/2024 khác quý 1/2025. Khóa nhóm cần **năm lịch + số quý**, chẳng hạn `(2024, 1)`. Không chỉ dùng số `1`, cũng không thay năm lịch bằng `WEEK_BASED_YEAR` trong khóa quý.

Quý ISO cũng không tự đại diện cho quý tài chính của mọi tổ chức. Nếu năm tài chính bắt đầu vào tháng 4 hoặc có cấu trúc tuần riêng, cần mô hình quy tắc tương ứng thay vì đổi tên nhãn của kết quả `QUARTER_OF_YEAR` rồi cho rằng đã tính đúng.

### Đọc miền giá trị trên ngày cụ thể

`date.range(IsoFields.DAY_OF_QUARTER)` phản ánh số ngày thực tế trong quý của ngày đó. Với quý 1/2024 là `1 - 91`; quý 1/2023 chỉ có 90 ngày.

Miền tổng quát của trường có thể bao phủ nhiều quý với độ dài khác nhau. Muốn xác nhận giá trị cho một quý cụ thể, phải dùng năm và quý ấy, không chỉ thấy rằng trường này có lúc nhận giá trị 92.

## 4. Năm theo tuần ISO có thể khác năm lịch

Tuần ISO có các quy tắc:

- Tuần bắt đầu vào thứ Hai.
- Thứ trong tuần đánh số 1–7, từ thứ Hai đến Chủ nhật.
- Tuần 1 là tuần chứa ít nhất 4 ngày thuộc năm mới; có thể hiểu tương đương là tuần chứa ngày 04/01 hoặc thứ Năm đầu tiên của năm.
- Một năm theo tuần có 52 hoặc 53 tuần.

Bởi một tuần được giữ nguyên qua ranh giới năm lịch, những ngày cuối tháng 12 có thể thuộc tuần 1 của năm theo tuần tiếp theo. Những ngày đầu tháng 1 có thể thuộc tuần cuối của năm theo tuần trước.

| Ngày lịch | Năm lịch | Năm theo tuần ISO | Tuần ISO | Thứ ISO |
|---|---|---|---|---|
| `2019-12-30` | 2019 | 2020 | 1 | 1, thứ Hai |
| `2021-01-01` | 2021 | 2020 | 53 | 5, thứ Sáu |
| `2024-03-31` | 2024 | 2024 | 13 | 7, Chủ nhật |

Vì vậy, khóa nhóm báo cáo tuần là **`WEEK_BASED_YEAR` + `WEEK_OF_WEEK_BASED_YEAR`**, không phải `getYear()` + số tuần ISO. Nếu muốn xác định một ngày từ hệ tuần, cần thêm `DAY_OF_WEEK`.

Ví dụ, ngày 01/01/2021 được viết `2020-W53-5`. Viết `2021-W53-5` không đơn thuần thay nhãn năm: nó yêu cầu một tuần khác, mà năm theo tuần 2021 còn không có tuần 53.

## 5. Tuần ISO, tuần theo vùng và pattern năm là những khái niệm khác nhau

`IsoFields` dùng quy tắc ISO cố định; nó không đổi ngày bắt đầu tuần theo `Locale`. Nếu cần tuần theo quy ước vùng, `WeekFields` cho phép lựa chọn ngày đầu tuần và số ngày tối thiểu của tuần đầu.

Không dùng pattern `YYYY` như một cách viết hoa thay cho `yyyy` hoặc `uuuu`. `Y` biểu diễn năm theo tuần và các trường tuần trong pattern có thể chịu quy tắc `WeekFields` theo locale. Vì vậy một pattern nhìn giống mã tuần không tự đảm bảo là tuần ISO trên mọi máy.

Khi hợp đồng yêu cầu mã tuần ISO, `DateTimeFormatter.ISO_WEEK_DATE` là lựa chọn rõ ràng để định dạng/đọc các giá trị như `2020-W53-5`. Không cần tự ghép `getYear()` vào trước số tuần.

Đây là lý do một mã báo cáo sai có thể chỉ xuất hiện vài ngày quanh năm mới dù các ngày khác đều trông hợp lý. Kiểm thử ngày giữa năm không đủ để phát hiện việc trộn năm lịch với năm theo tuần.

## 6. Điều chỉnh trường không đồng nghĩa kiểm tra đầu vào nghiêm ngặt

`with(IsoFields.QUARTER_OF_YEAR, 2)` chuyển tháng đi một số quý phù hợp và giữ các phần có thể giữ; nếu ngày trong tháng không còn tồn tại thì có thể được điều chỉnh về ngày cuối tháng theo phép tính tháng của kiểu.

Ví dụ, 31/01/2026 đổi sang quý 2 thành 30/04/2026. Cộng một `QUARTER_YEARS` từ ngày ấy cũng là thêm 3 tháng, cho 30/04/2026. Tuy kết quả trùng trong ví dụ, một lời gọi là đặt số quý, lời gọi kia là cộng một lượng; không được coi chúng luôn tương đương cho mọi đầu vào và giá trị.

Một chi tiết quan trọng: đặt `DAY_OF_QUARTER` cho phép một số giá trị vượt độ dài thực tế của quý trong miền 1–92, rồi chuyển sang quý kế tiếp. Ví dụ:

```java
LocalDate adjusted = LocalDate.of(2023, 1, 1)
        .with(IsoFields.DAY_OF_QUARTER, 91);
// 2023-04-01, vì quý 1/2023 chỉ có 90 ngày.
```

Nếu mục tiêu là **xác nhận một đầu vào năm-quý-ngày thuộc đúng quý**, không dùng riêng phép `with` này như một bộ kiểm tra nghiêm ngặt. Có thể đọc ba trường bằng bộ định dạng với `ResolverStyle.STRICT`, hoặc kiểm tra độ dài thực tế của quý trước khi tạo kết quả.

Tương tự, tuần 53 không tồn tại trong mọi năm theo tuần. Khi đọc mã tuần được cung cấp từ bên ngoài, hãy chọn chính sách giải quyết trường tường minh và kiểm tra theo năm đích. Các đơn vị năm theo tuần cũng không phải số giây hay số ngày cố định; nếu cần xử lý ranh giới tuần 53 khi cộng năm, phải kiểm tra hợp đồng của phép tính cụ thể thay vì thay bằng `plusYears` hoặc một hằng ngày.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `IsoFieldsDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Bộ định dạng quý trong ví dụ giới hạn phần năm ở bốn chữ số không dấu.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.IsoFields;
import java.util.Locale;

public class IsoFieldsDemo {
    private static final DateTimeFormatter QUARTER_DATE =
            new DateTimeFormatterBuilder()
                    .appendValue(ChronoField.YEAR, 4)
                    .appendLiteral("-Q")
                    .appendValue(IsoFields.QUARTER_OF_YEAR)
                    .appendLiteral('-')
                    .appendValue(IsoFields.DAY_OF_QUARTER)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        for (LocalDate date : new LocalDate[]{
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2019, 12, 30),
                LocalDate.of(2024, 3, 31)
        }) {
            System.out.println(date
                    + " quarter=" + date.get(IsoFields.QUARTER_OF_YEAR)
                    + " dayOfQuarter=" + date.get(IsoFields.DAY_OF_QUARTER)
                    + " weekYear=" + date.get(IsoFields.WEEK_BASED_YEAR)
                    + " week=" + date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR)
                    + " weekday=" + date.getDayOfWeek().getValue());
        }

        LocalDate leap = LocalDate.of(2024, 3, 31);
        System.out.println("quarterKey=" + leap.getYear() + "-Q"
                + leap.get(IsoFields.QUARTER_OF_YEAR));
        System.out.println("quarterDayRange="
                + leap.range(IsoFields.DAY_OF_QUARTER));
        System.out.println("quarterParsed="
                + LocalDate.parse("2024-Q1-91", QUARTER_DATE));
        try {
            LocalDate.parse("2023-Q1-91", QUARTER_DATE);
        } catch (DateTimeParseException e) {
            System.out.println("invalidQuarterDay=ERROR");
        }

        LocalDate jan31 = LocalDate.of(2026, 1, 31);
        System.out.println("setQuarter="
                + jan31.with(IsoFields.QUARTER_OF_YEAR, 2));
        System.out.println("plusQuarter="
                + jan31.plus(1, IsoFields.QUARTER_YEARS));
        System.out.println("setDay91="
                + LocalDate.of(2023, 1, 1)
                           .with(IsoFields.DAY_OF_QUARTER, 91));

        LocalDate boundary = LocalDate.of(2021, 1, 1);
        String weekText = DateTimeFormatter.ISO_WEEK_DATE.format(boundary);
        System.out.println("weekText=" + weekText);
        System.out.println("weekParsed="
                + LocalDate.parse(weekText, DateTimeFormatter.ISO_WEEK_DATE));
        System.out.println("actualWeekRange="
                + boundary.range(IsoFields.WEEK_OF_WEEK_BASED_YEAR));
        try {
            LocalDate.parse("2021-W53-1", DateTimeFormatter.ISO_WEEK_DATE);
        } catch (DateTimeParseException e) {
            System.out.println("invalidWeek53=ERROR");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac IsoFieldsDemo.java
java IsoFieldsDemo
```

Kết quả chuẩn:

```text
2021-01-01 quarter=1 dayOfQuarter=1 weekYear=2020 week=53 weekday=5
2019-12-30 quarter=4 dayOfQuarter=91 weekYear=2020 week=1 weekday=1
2024-03-31 quarter=1 dayOfQuarter=91 weekYear=2024 week=13 weekday=7
quarterKey=2024-Q1
quarterDayRange=1 - 91
quarterParsed=2024-03-31
invalidQuarterDay=ERROR
setQuarter=2026-04-30
plusQuarter=2026-04-30
setDay91=2023-04-01
weekText=2020-W53-5
weekParsed=2021-01-01
actualWeekRange=1 - 53
invalidWeek53=ERROR
```

`ERROR` là nhãn do chương trình in khi bắt `DateTimeParseException`, không phải thông điệp mặc định của Java.

Bộ định dạng `QUARTER_DATE` dùng ba trường **năm lịch, quý, ngày trong quý** để tạo ngày. `2024-Q1-91` hợp lệ, còn `2023-Q1-91` bị từ chối trong chế độ nghiêm ngặt. So sánh với dòng `setDay91` để thấy rõ phép điều chỉnh và phép xác nhận đầu vào có hợp đồng khác nhau.

`actualWeekRange` được hỏi trên 01/01/2021 nhưng trả miền đến 53 vì ngày đó thuộc năm theo tuần 2020. Muốn biết số tuần của năm theo tuần nào, phải chọn đúng ngữ cảnh, không chỉ nhìn năm lịch của ngày đang cầm.

## 8. Dùng trong tổng hợp và trao đổi dữ liệu

Khi nhóm dữ liệu, giữ các thành phần thành một khóa có cấu trúc, ví dụ một record năm-tuần hoặc năm-quý được đặt tên rõ ràng. Chuỗi `2024-Q1` hay `2020-W53` có thể là biểu diễn trao đổi, nhưng không nên làm mất ý nghĩa loại năm trong mã xử lý.

Trước khi lấy `IsoFields` từ một thời điểm như `Instant`, cần xác định ngày địa phương theo múi giờ của báo cáo. Cùng một thời điểm có thể rơi vào hai ngày khác nhau giữa các múi giờ, từ đó khác quý hoặc năm theo tuần. `Instant` không tự có một “tuần kinh doanh” chung cho mọi nơi.

Nếu dữ liệu đã là `LocalDate`, nó không chứa múi giờ và việc đọc trường chỉ dựa trên ngày đó. Không tự gắn thêm múi giờ máy chủ để diễn giải lại một ngày đã được xác định đúng trong miền nghiệp vụ.

## 9. Tự thực hành

1. Lấy trường tuần của `2021-01-04`. Kết quả là năm theo tuần 2021, tuần 1, thứ Hai; hãy so với `2021-01-01` để thấy ranh giới.
2. Lấy ngày trong quý của `2023-03-31` và `2024-03-31`. Hai kết quả là 90 và 91 vì năm nhuận thêm một ngày vào quý 1.
3. Nhóm ba ngày `2020-12-31`, `2021-01-01`, `2021-01-03` bằng cặp trường tuần ISO. Cả ba thuộc cùng tuần 53 của năm theo tuần 2020; dùng năm lịch sẽ chia sai nhóm.
4. Đổi `ResolverStyle.STRICT` của bộ định dạng quý sang `SMART`, rồi quan sát `2023-Q1-91`. Đối chiếu lại chính sách có được phép đi ra khỏi quý đầu vào hay phải báo lỗi.

Tham khảo: [IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html) và [DateTimeFormatter — ISO_WEEK_DATE](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#ISO_WEEK_DATE) trong Java SE 21.
