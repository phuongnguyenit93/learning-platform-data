# Phân biệt uuuu, yyyy và YYYY trong DateTimeFormatter

## Mục tiêu

Trong mẫu định dạng ngày giờ của Java, các chữ `u`, `y` và `Y` không đồng nghĩa:

- `u` là **năm theo lịch ISO dạng proleptic** (proleptic year), bao gồm năm 0 và năm âm.
- `y` là **năm trong kỷ nguyên** (year-of-era), thường thấy dưới dạng năm dương trong kỷ nguyên CE/AD.
- `Y` là **năm theo tuần** (week-based-year), gắn với tuần trong năm và quy tắc tuần của locale.

Với phần lớn ngày giữa năm, `uuuu` và `yyyy` trông giống nhau. Tuy nhiên, gần đầu hoặc cuối năm, `YYYY` có thể hiện năm khác hoàn toàn so với năm lịch. Chọn sai pattern có thể làm báo cáo, tên file, hóa đơn hoặc khóa ngày bị gắn nhầm năm.

## 1. Ba ký hiệu, ba ý nghĩa

| Pattern | Ý nghĩa | Dùng cho |
|---|---|---|
| `uuuu` | Năm lịch proleptic, có thể là 0 hoặc năm âm | Ngày ISO thông thường; dữ liệu cần năm lịch rõ ràng |
| `yyyy` | Năm trong era hiện hành | Ngày lịch gắn với kỷ nguyên; khi cần biểu diễn era trước/sau CE nên ghép với `G` |
| `YYYY` | Năm tuần (week-based-year) | Mã tuần như `2020-W01`, báo cáo theo tuần, lịch theo quy tắc tuần |
| `ww` | Số tuần của năm theo quy tắc tuần | Ghép với `YYYY` khi biểu diễn tuần |
| `G` | Era, ví dụ AD/BC trong locale phù hợp | Phân biệt năm CE và BCE khi dùng `yyyy` |

Pattern phân biệt hoa/thường. `yyyy` và `YYYY` là hai trường ngày khác nhau; đổi chữ thường thành chữ hoa làm thay đổi ý nghĩa dữ liệu.

Đối với lịch ISO dùng bởi `LocalDate`, năm lịch của ngày `2019-12-30` là 2019. Nhưng ngày này là ngày thứ Hai của tuần ISO số 1 thuộc **week-based-year 2020**. Vì thế `uuuu`/`yyyy` có thể in 2019 trong khi `YYYY` in 2020.

## 2. uuuu: năm lịch proleptic

`u` biểu thị năm theo lịch proleptic, tức quy tắc lịch được kéo dài qua các năm trước và sau mốc kỷ nguyên. Với các ngày CE thông thường, `uuuu` hiển thị năm lịch quen thuộc:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2024, 6, 15);
DateTimeFormatter calendarYear =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

System.out.println(calendarYear.format(date));
```

Kết quả:

```text
2024-06-15
```

`uuuu` đặc biệt hữu ích khi cần định dạng/parsing ngày theo ISO một cách rõ nghĩa. Khác với year-of-era, proleptic year có biểu diễn năm 0 và các năm âm. Trong hệ quy chiếu proleptic Gregorian mà Java sử dụng, năm 0 tương ứng năm 1 BCE; các giá trị âm biểu diễn những năm BCE tiếp theo theo quy ước số học của kiểu lịch.

Đa số ứng dụng nghiệp vụ chỉ làm việc với ngày dương hiện đại, nên `uuuu` và `yyyy` thường tạo ra cùng chuỗi. Nhưng chúng không tương đương về mô hình dữ liệu cho toàn bộ miền ngày được hỗ trợ.

## 3. yyyy: năm trong era

`y` là năm trong era (year-of-era). Mốc năm bắt đầu lại khi chuyển era, nên bản thân `yyyy` không đủ để phân biệt hai ngày thuộc các era khác nhau nếu ứng dụng xử lý ngày lịch cổ hoặc BCE/CE.

Khi cần era, ghép với `G`:

```java
DateTimeFormatter eraDate =
        DateTimeFormatter.ofPattern("G yyyy-MM-dd", Locale.US);
```

Mẫu này biểu diễn era cùng với year-of-era. Tên era được bản địa hóa theo locale, ví dụ thông thường ở locale tiếng Anh có thể là `AD` hoặc `BC`; định dạng chính xác phụ thuộc dữ liệu locale/JDK. Đừng xem phần chữ era là một hằng chuỗi ổn định cho mọi ngôn ngữ.

Với một ngày thông thường thuộc CE, `yyyy-MM-dd` thường in cùng số năm với `uuuu-MM-dd`:

```java
LocalDate date = LocalDate.of(2024, 6, 15);
DateTimeFormatter yearOfEra =
        DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.ROOT);
System.out.println(yearOfEra.format(date));
```

Kết quả:

```text
2024-06-15
```

Khi mục tiêu là chuỗi ngày ISO không cần era và muốn biểu diễn trực tiếp năm lịch, ưu tiên `uuuu-MM-dd`. Khi mục tiêu yêu cầu năm gắn với era, dùng `yyyy` cùng `G` và xác định cách parsing tương ứng.

## 4. YYYY: week-based-year, không phải year thông thường

`Y` biểu thị năm gắn với tuần. Nó phải được hiểu cùng các trường tuần như `w` (week of week-based-year) và quy tắc định nghĩa tuần. Năm tuần có thể bắt đầu trước ngày 1/1 hoặc kéo dài sang những ngày đầu năm lịch kế tiếp.

Hai yếu tố chính ảnh hưởng week-based-year:

1. Ngày nào được coi là ngày đầu tuần (ví dụ thứ Hai trong ISO).
2. Số ngày tối thiểu của tuần đầu tiên phải nằm trong năm mới (ISO yêu cầu ít nhất bốn ngày).

Với ISO week date, tuần bắt đầu vào thứ Hai; tuần 1 là tuần có ít nhất bốn ngày trong năm mới. Vì thế một số ngày cuối tháng 12 đã thuộc năm tuần kế tiếp, và một số ngày đầu tháng 1 vẫn thuộc năm tuần trước.

`YYYY` **không nên dùng như cách viết hoa để thay cho `yyyy`** trong mẫu ngày thường. Dùng nó với `MM-dd` tạo chuỗi ghép year-from-week với tháng/ngày-calendar, có thể tạo ra một ngày hiển thị mâu thuẫn như `2020-12-30` khi đầu vào thực là `2019-12-30`.

## 5. Ví dụ rõ ràng ở ranh giới năm

Tạo tệp `YearPatternDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class YearPatternDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2019, 12, 30);

        DateTimeFormatter calendarU =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.UK);
        DateTimeFormatter calendarY =
                DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.UK);
        DateTimeFormatter weekYear =
                DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.UK);
        DateTimeFormatter mixed =
                DateTimeFormatter.ofPattern("YYYY-MM-dd", Locale.UK);

        System.out.println("Input:        " + date);
        System.out.println("uuuu-MM-dd:   " + calendarU.format(date));
        System.out.println("yyyy-MM-dd:   " + calendarY.format(date));
        System.out.println("Week pattern: " + weekYear.format(date));
        System.out.println("Mixed pattern:" + mixed.format(date));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac YearPatternDemo.java
java YearPatternDemo
```

Kết quả với locale `Locale.UK` (quy tắc tuần theo ISO):

```text
Input:        2019-12-30
uuuu-MM-dd:   2019-12-30
yyyy-MM-dd:   2019-12-30
Week pattern: 2020-W01-1
Mixed pattern:2020-12-30
```

Dòng `Week pattern` là biểu diễn tuần hợp lý: ngày thuộc tuần 1 của week-based-year 2020 và thứ Hai được đánh số 1 trong locale này. Dòng `Mixed pattern` được tạo có chủ đích để minh họa lỗi: `YYYY` lấy năm tuần 2020, còn `MM-dd` giữ tháng/ngày của ngày lịch đầu vào. Chuỗi `2020-12-30` **không còn là định dạng lại đúng của ngày ban đầu**; đó là các trường trộn từ hai hệ quy chiếu khác nhau.

Để tránh output phụ thuộc locale mặc định của máy, ví dụ chỉ định `Locale.UK` tường minh. Trong ứng dụng thực tế, nếu muốn tuần ISO, hãy dùng locale hoặc quy tắc ISO được chỉ định rõ ràng. Đừng dựa vào locale mặc định, vì locale có thể thay đổi quy tắc ngày đầu tuần và tuần đầu tiên của năm.

## 6. Tại sao YYYY thay đổi theo locale?

`YYYY` dùng week-based-year theo quy tắc tuần của formatter. Với các locale kiểu ISO (như `Locale.UK`), quy tắc thường tương ứng tuần bắt đầu thứ Hai và ít nhất bốn ngày trong tuần 1 thuộc năm mới. Locale khác có thể dùng ngày bắt đầu tuần và quy tắc số ngày tối thiểu khác, khiến ranh giới tuần/năm khác nhau.

Ví dụ tổng quan với cùng ngày lịch:

| Ý nghĩa | Trường cần định dạng |
|---|---|
| Năm lịch của ngày | `uuuu` hoặc `yyyy` |
| Năm thuộc tuần theo quy tắc locale | `YYYY` |
| Số tuần trong week-based-year | `ww` |
| Ngày trong tuần theo kiểu số bản địa hóa | `e` |
| Ngày trong tuần theo số ISO cố định | `c` phụ thuộc cách dùng/pattern; với ứng dụng ISO nên chọn bộ quy tắc nhất quán |

Nếu cần kết quả theo ISO bất kể locale toàn ứng dụng, cân nhắc dùng `WeekFields.ISO` để trích xuất `weekBasedYear()`, `weekOfWeekBasedYear()` và `dayOfWeek()` hoặc dùng `DateTimeFormatter` với locale/quy tắc ISO tường minh. Điều quan trọng là các trường năm tuần, số tuần và thứ trong tuần phải dùng **cùng một quy tắc tuần**.

## 7. Pattern đúng cho các định dạng phổ biến

| Ý định | Pattern gợi ý | Ghi chú |
|---|---|---|
| Ngày ISO theo năm lịch | `uuuu-MM-dd` | Lựa chọn rõ nghĩa cho ngày lịch |
| Ngày lịch gắn với era | `G yyyy-MM-dd` | Cần era để phân biệt BCE/CE |
| Tuần ISO, ví dụ tuần 1 năm 2020 | `YYYY-'W'ww-e` với locale/quy tắc ISO rõ ràng | Dùng các trường week-based một cách đồng bộ |
| Thời điểm ISO có offset | `uuuu-MM-dd'T'HH:mm:ssXXX` | Nếu cần phân tích/định dạng offset, dùng kiểu temporal phù hợp |
| Tạo khóa file/báo cáo theo tháng | `uuuu-MM` | Tránh dùng `YYYY-MM` trừ khi chủ ý lấy năm tuần, thường không phù hợp cho tháng |

Không dùng `YYYY-MM-dd` cho tên file ngày thường, báo cáo ngày, cơ sở dữ liệu hoặc nhãn hóa đơn chỉ vì nó “có vẻ giống yyyy-MM-dd”. Ở ranh giới năm, chuỗi được tạo có thể sai năm.

## 8. Parsing và ResolverStyle

Mẫu không chỉ ảnh hưởng đầu ra; khi phân tích chuỗi thành ngày, các trường năm cũng quyết định ý nghĩa. Nếu pattern chứa `YYYY` nhưng đi cùng tháng/ngày lịch, formatter có thể không cung cấp tổ hợp trường phù hợp để dựng `LocalDate` như mong đợi.

- Dùng `uuuu-MM-dd` để đọc/ghi ngày ISO theo năm lịch.
- Dùng bộ trường tuần như `YYYY-'W'ww-e` cho dữ liệu week date, với locale/quy tắc nhất quán.
- Khi nhận dữ liệu không đáng tin cậy, xác định rõ `ResolverStyle.STRICT`, `SMART` hoặc `LENIENT` tùy hợp đồng parsing. `DateTimeFormatter` mặc định dùng resolver style `SMART`, nhưng pattern đúng và hợp đồng dữ liệu vẫn là điều cốt lõi.

Ví dụ formatter strict để parsing theo năm lịch:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strictCalendarDate = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("2024-02-29", strictCalendarDate);
```

Đây là đoạn mã minh họa dùng trong một phương thức; nó cần các import và một vị trí trong chương trình như `main` để chạy độc lập. Với năm lịch, `uuuu` tránh sự mơ hồ về year-of-era khi dùng strict resolver. Nếu dùng `yyyy` mà không cung cấp era trong ngữ cảnh strict parsing, formatter có thể không resolve được ngày vì thiếu thông tin era.

## 9. Kiểm tra ranh giới năm trong test

Không chỉ test giữa năm. Bộ kiểm thử cho formatter nên bao gồm các ngày sát ranh giới như 28–31 tháng 12 và 1–4 tháng 1, đặc biệt khi có logic theo tuần. Kiểm thử phải cố định locale/quy tắc tuần và mong đợi chính xác.

Các điểm nên xác nhận:

- Ngày giữa năm có năm lịch giống giữa pattern `uuuu` và `yyyy` trong CE.
- Ngày 30/12/2019 theo ISO thuộc `2020-W01`.
- Các pattern lịch không sử dụng `YYYY` nếu ý nghĩa là năm lịch.
- Các pattern tuần sử dụng đồng bộ `YYYY`, `ww` và trường ngày trong tuần.
- Parsing strict được test với năm nhuận và chuỗi sai như 2023-02-29.
- Test không phụ thuộc locale hoặc múi giờ mặc định của môi trường chạy.

## 10. Lỗi thường gặp

1. **Dùng chữ `Y` hoa cho năm thông thường.** `YYYY` là week-based-year, không phải năm lịch.
2. **Trộn năm tuần với tháng/ngày lịch.** `YYYY-MM-dd` có thể tạo ra chuỗi không biểu diễn lại đúng ngày đầu vào ở ranh giới năm.
3. **Cho rằng uuuu và yyyy luôn giống nhau.** Chúng giống ở đa số ngày CE thông thường nhưng khác ý nghĩa ở phần miền năm trước/sau era.
4. **Dùng yyyy mà không kèm G khi cần xử lý BCE/CE.** Year-of-era không tự phân biệt hai era.
5. **Để locale mặc định quyết định tuần đầu năm.** Ranh giới week-based-year có thể thay đổi theo quy tắc locale; đặt rõ locale hoặc dùng quy tắc ISO.
6. **Dùng mẫu week-based để parsing ngày lịch.** Mã tuần phải có trường tuần và ngày trong tuần tương ứng; dùng `uuuu-MM-dd` cho ngày lịch.
7. **Chỉ kiểm thử ngày giữa năm.** Sai lệch của `YYYY` thường chỉ lộ ra ở cuối tháng 12 hoặc đầu tháng 1.
8. **Dùng chuỗi định dạng làm khóa ngày chuẩn tắc mà không định nghĩa pattern.** Hãy xác định rõ dữ liệu biểu diễn ngày lịch, tuần, hay thời điểm.

## 11. Tự kiểm tra

**Câu 1.** Muốn định dạng ngày lịch 30/12/2019, pattern nào nên dùng giữa `uuuu-MM-dd` và `YYYY-MM-dd`?

**Đáp án:** `uuuu-MM-dd`. Nó biểu diễn năm lịch 2019. `YYYY-MM-dd` có thể tạo `2020-12-30` vì năm tuần đã chuyển sang 2020.

**Câu 2.** Trong `YYYY-'W'ww-e`, các trường biểu diễn điều gì?

**Đáp án:** Năm tuần, số tuần trong week-based-year và ngày trong tuần theo quy tắc locale được chọn.

**Câu 3.** Khi cần phân biệt năm BCE/CE trong định dạng, có nên chỉ ghi `yyyy-MM-dd` không?

**Đáp án:** Không. Year-of-era bắt đầu lại theo era; dùng `G yyyy-MM-dd` nếu cần thông tin era.

**Câu 4.** Vì sao ví dụ formatter nên chỉ định `Locale.UK`?

**Đáp án:** Để cố định quy tắc tuần cho ví dụ và tránh phụ thuộc locale mặc định của máy.

**Câu 5.** `uuuu` có ích gì khi dùng `ResolverStyle.STRICT` để parse ngày lịch?

**Đáp án:** Nó biểu diễn trực tiếp proleptic year, tránh cần giải quyết year-of-era khi pattern thiếu era và giúp mô hình parsing ngày lịch rõ ràng.

---

**Ghi nhớ:** Dùng `uuuu` cho năm lịch, `yyyy` cho năm trong era, và `YYYY` chỉ khi thực sự định dạng năm theo tuần. Nếu pattern có `YYYY`, hãy ghép nó với số tuần và ngày trong tuần; đừng trộn nó vô tình với tháng/ngày lịch.