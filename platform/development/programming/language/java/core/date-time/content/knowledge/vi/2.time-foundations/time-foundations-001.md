# Lịch ISO-8601 và quy tắc Gregorian mở rộng về quá khứ trong Java

## 1. Mục tiêu và ranh giới

Trong Java, một ngày như **2024-02-29** vừa có **cách biểu diễn theo ISO 8601** (chuỗi năm–tháng–ngày) vừa có **quy tắc lịch** để quyết định ngày đó tồn tại hay không. Hai khái niệm liên quan nhưng khác vai trò:

- **ISO 8601** chuẩn hóa cách biểu diễn và trao đổi ngày, giờ, tuần, thời điểm và độ lệch UTC. Ví dụ dạng mở rộng `2024-02-29`, tuần ISO `2020-W53-5`, thời điểm `2024-02-29T10:15:30Z`.
- **Lịch Gregorian mở rộng về quá khứ** (*proleptic Gregorian calendar*) áp dụng **cùng quy tắc Gregorian hiện đại cho cả các năm trước khi lịch này được ban hành**. Java `java.time.LocalDate` sử dụng hệ lịch ISO dựa trên quy tắc đó.

Bài này tập trung vào ngày lịch và ý nghĩa các năm lịch sử trong **Java core – date-time**. Độ lệch UTC, múi giờ và timestamp chỉ được giải thích để tránh đánh đồng chúng với ngày lịch.

## 2. Gregorian mở rộng về quá khứ là gì?

Lịch Gregorian hiện đại có 12 tháng; độ dài tháng thông thường là 28–31 ngày. Tháng 2 có 29 ngày trong **năm nhuận** theo quy tắc:

1. Năm chia hết cho 4 thường là năm nhuận.
2. Nếu chia hết cho 100 thì **không** nhuận.
3. Nếu đồng thời chia hết cho 400 thì **vẫn** nhuận.

Có thể viết điều kiện toán học: `(year % 4 == 0) && ((year % 100 != 0) || (year % 400 == 0))`. Trong Java, toán tử `%` vẫn cho số dư bằng 0 chính xác với số chia hết, kể cả năm âm và năm 0.

| Năm theo quy ước ISO | Kết quả | Lý do |
|---|---|---|
| 2024 | Nhuận | Chia hết cho 4, không chia hết cho 100 |
| 1900 | Không nhuận | Chia hết cho 100 nhưng không cho 400 |
| 2000 | Nhuận | Chia hết cho 400 |
| 1700 | Không nhuận | Chia hết cho 100 nhưng không cho 400 |
| 0 | Nhuận | Theo phép mở rộng toán học, chia hết cho 400 |
| -4 | Nhuận | Chia hết cho 4, không cho 100 |

**“Mở rộng về quá khứ” không có nghĩa thế giới đã dùng lịch Gregorian thời cổ đại.** Nó chỉ là một mô hình thống nhất để tính toán. Trước khi cải cách Gregorian được áp dụng, nhiều vùng dùng lịch Julian hoặc lịch khác; thời điểm chuyển đổi cũng khác nhau theo quốc gia.

### 2.1. Cải cách năm 1582 và ngày “bị bỏ qua”

Tại một số nơi tiếp nhận cải cách năm 1582, ngày **1582-10-04** theo lịch Julian được nối tiếp bằng **1582-10-15** theo lịch Gregorian; các nhãn ngày 05–14 tháng 10 không được sử dụng trong lịch dân sự của những nơi đó. Điều này **không phải quy tắc chung cho mọi quốc gia** và không phải cách `LocalDate` vận hành.

Với lịch **proleptic Gregorian**, chuỗi ngày là liên tục:

~~~text
1582-10-04 -> 1582-10-05 -> ... -> 1582-10-14 -> 1582-10-15
~~~

Vì vậy, trong `java.time`:

- `LocalDate.of(1582, 10, 4).plusDays(1)` trả `1582-10-05`.
- Khoảng cách từ `1582-10-04` đến `1582-10-15` là **11 ngày**.
- `LocalDate.of(1500, 2, 29)` không hợp lệ: năm 1500 không nhuận theo Gregorian, dù là năm nhuận theo quy tắc Julian. Đây là khác biệt quan trọng khi xử lý sử liệu.

Nếu yêu cầu tái dựng đúng **lịch dân sự của một địa điểm trong một thời kỳ**, phải biết địa điểm, thời điểm đổi lịch và lịch gốc của tài liệu. Không thể suy ra tất cả từ một chuỗi ngày ISO.

## 3. Năm 0, BCE/CE và cách đếm năm

Java ISO chronology dùng **proleptic year** (năm thiên văn, trường `YEAR`) để tính toán liên tục qua ranh giới kỷ nguyên:

| Proleptic year (`YEAR`) | Cách gọi theo kỷ nguyên | `ERA` | `YEAR_OF_ERA` |
|---|---|---|---|
| 2 | 2 CE | CE | 2 |
| 1 | 1 CE | CE | 1 |
| 0 | 1 BCE | BCE | 1 |
| -1 | 2 BCE | BCE | 2 |
| -2 | 3 BCE | BCE | 3 |

Điểm mấu chốt: **lịch sử BCE/CE truyền thống không có năm 0; hệ đánh số ISO trong Java có năm 0**. Vì vậy, nếu cần chuyển năm lịch sử `n BCE` sang proleptic year thì dùng **`1 - n`**. Ví dụ: 44 BCE là `-43` theo ISO, không phải `-44`.

`LocalDate.of(0, 1, 1)` và `LocalDate.of(-1, 1, 1)` đều hợp lệ. Để lấy năm lịch sử theo kỷ nguyên, đọc `getEra()` và `get(ChronoField.YEAR_OF_ERA)`; để tính toán liên tục, dùng `getYear()` hoặc `ChronoField.YEAR`.

**Chú ý:** Việc có năm 0 và việc năm 0 được xem là nhuận đều là **quy ước của proleptic Gregorian**, không phải một khẳng định lịch sử về lịch từng dùng năm 1 BCE.

## 4. ISO 8601: biểu diễn ngày, ngày thứ bao nhiêu và tuần

Một ngày có thể được trình bày theo nhiều dạng ISO 8601:

| Kiểu biểu diễn | Ví dụ | Ý nghĩa |
|---|---|---|
| Ngày lịch dạng mở rộng | `2024-02-29` | Năm–tháng–ngày |
| Ngày lịch dạng cơ bản | `20240229` | Cùng ngày, bỏ dấu phân tách |
| Ngày thứ bao nhiêu trong năm | `2024-060` | Ngày thứ 60 của năm 2024 |
| Ngày trong tuần ISO | `2020-W53-5` | Thứ Sáu thuộc tuần ISO 53 của **năm tuần 2020** |
| Ngày–giờ địa phương | `2024-02-29T10:15:30` | Chưa có độ lệch UTC hay múi giờ |
| Ngày–giờ với offset | `2024-02-29T10:15:30+07:00` | Độ lệch +07:00 so với UTC |
| Thời điểm UTC | `2024-02-29T03:15:30Z` | Cùng thời điểm với dòng +07:00 ở trên |

Trong **tuần ISO**, thứ Hai là ngày 1, Chủ nhật là ngày 7; tuần 1 là tuần có ít nhất bốn ngày của năm mới (tương đương tuần chứa ngày 4/1 hoặc thứ Năm đầu tiên). Vì vậy, **năm của tuần ISO có thể khác năm của ngày lịch**. Ngày **2021-01-01** là thứ Sáu thuộc **2020-W53-5**.

Ngày theo số thứ tự trong năm dùng ngày từ 001 trở đi. Vì 2024 nhuận, `2024-02-29` là ngày **060**. Một năm thường có 365 ngày; năm nhuận có 366 ngày.

Các biểu diễn này phục vụ mục đích khác nhau. Không nên coi `2020-W53-5` như ngày **2020-12-...** bằng cách thay số tuần thành tháng, hoặc coi chữ `Z` là tên múi giờ địa phương. `Z` ký hiệu offset UTC bằng 0.

### 4.1. ISO 8601 không tự giải quyết mọi vấn đề múi giờ

`2024-01-01` chỉ là **ngày lịch**, chưa xác định giờ hoặc múi giờ. `2024-01-01T00:30+07:00` chỉ ra thời điểm tương đương `2023-12-31T17:30Z`: cùng một tức thời có thể thuộc **hai ngày lịch khác nhau** khi hiển thị ở hai offset. Múi giờ vùng như `Asia/Ho_Chi_Minh` còn có tập quy tắc lịch sử và pháp lý riêng; offset `+07:00` không thay thế đầy đủ một `ZoneId` cho mọi thời kỳ.

**Cần tách ba câu hỏi:**

1. *Ngày nào hợp lệ?* → Quy tắc lịch/chronology.
2. *Ngày/giờ được ghi bằng cú pháp nào?* → ISO 8601 và formatter.
3. *Đó là thời điểm nào trên dòng thời gian toàn cầu?* → Offset/múi giờ và dữ liệu quy tắc múi giờ.

## 5. Những kiểu `java.time` cần phân biệt

| Kiểu Java | Nắm giữ điều gì | Ví dụ sử dụng |
|---|---|---|
| `LocalDate` | Năm–tháng–ngày ISO, không có giờ/múi giờ | Ngày sinh, ngày giao hàng |
| `LocalTime` | Giờ–phút–giây, không có ngày | Giờ mở cửa theo bảng lịch |
| `LocalDateTime` | Ngày và giờ địa phương, chưa chọn múi giờ | Lịch họp dự kiến |
| `OffsetDateTime` | Ngày–giờ và offset cố định so với UTC | Dữ liệu ngày giờ có `+07:00` |
| `ZonedDateTime` | Ngày–giờ trong `ZoneId` có quy tắc vùng | Lịch họp theo vùng |
| `Instant` | Một thời điểm trên dòng thời gian toàn cầu | Audit timestamp, sự kiện |
| `Year`, `YearMonth` | Năm, hoặc năm–tháng ISO | Chu kỳ kế toán, kỳ thanh toán |
| `IsoChronology` | Hệ lịch ISO dựa trên proleptic Gregorian | Kiểm tra/diễn đạt quy tắc lịch |

`LocalDate` mặc định theo `IsoChronology.INSTANCE`; không cần tự cài đặt quy tắc chia hết năm nhuận trong ứng dụng thường ngày. Sử dụng `LocalDate.isLeapYear()`, `Year.isLeap(year)`, `YearMonth.lengthOfMonth()`, hoặc `LocalDate.lengthOfYear()` khi cần.

**Giới hạn cần nhớ:** `LocalDate` hỗ trợ năm từ **-999999999** đến **+999999999** theo proleptic year. Các kiểu thời điểm/offset/múi giờ có các giới hạn, phép chiếu và quy tắc riêng; không suy luận rằng một giá trị `LocalDate` có thể luôn ánh xạ sang mọi kiểu thời gian khác theo cùng cách.

## 6. Chương trình Java 17+ chạy độc lập

Lưu mã sau trong tệp **`IsoGregorianDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.Year;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

public class IsoGregorianDemo {
    public static void main(String[] args) {
        System.out.println("Chronology: " + IsoChronology.INSTANCE.getId());
        System.out.println("2000 leap? " + Year.isLeap(2000));
        System.out.println("1900 leap? " + Year.isLeap(1900));

        LocalDate yearZero = LocalDate.of(0, 2, 29);
        System.out.println("Year 0: " + yearZero
                + ", era=" + yearZero.getEra()
                + ", year-of-era=" + yearZero.get(ChronoField.YEAR_OF_ERA));

        LocalDate yearMinusOne = LocalDate.of(-1, 1, 1);
        System.out.println("Year -1: " + yearMinusOne
                + ", era=" + yearMinusOne.getEra()
                + ", year-of-era=" + yearMinusOne.get(ChronoField.YEAR_OF_ERA));

        LocalDate before = LocalDate.of(1582, 10, 4);
        LocalDate after = LocalDate.of(1582, 10, 15);
        System.out.println("1582-10-04 + 1 day: " + before.plusDays(1));
        System.out.println("Days from 1582-10-04 to 1582-10-15: "
                + ChronoUnit.DAYS.between(before, after));

        LocalDate newYear = LocalDate.of(2021, 1, 1);
        System.out.println("ISO week date: "
                + DateTimeFormatter.ISO_WEEK_DATE.format(newYear));
        System.out.println("ISO ordinal date: "
                + DateTimeFormatter.ISO_ORDINAL_DATE.format(
                        LocalDate.of(2024, 2, 29)));
        System.out.println("Epoch day at 1970-01-01: "
                + LocalDate.of(1970, 1, 1).toEpochDay());
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac IsoGregorianDemo.java
java IsoGregorianDemo
~~~

Stdout xác định, không phụ thuộc ngày hiện tại hoặc múi giờ máy chạy:

~~~text
Chronology: ISO
2000 leap? true
1900 leap? false
Year 0: 0000-02-29, era=BCE, year-of-era=1
Year -1: -0001-01-01, era=BCE, year-of-era=2
1582-10-04 + 1 day: 1582-10-05
Days from 1582-10-04 to 1582-10-15: 11
ISO week date: 2020-W53-5
ISO ordinal date: 2024-060
Epoch day at 1970-01-01: 0
~~~

**Giải thích các kết quả cần chú ý:**

- `Year.isLeap(1900)` là `false`, phản ánh ngoại lệ thế kỷ của Gregorian.
- Năm `0` tồn tại, thuộc `BCE`, là **năm thứ 1 trong kỷ nguyên BCE**, và hợp lệ với ngày 29/2.
- `1582-10-04` cộng một ngày thành `1582-10-05`: Java dùng quy tắc proleptic liên tục và không mô phỏng việc một số nước bỏ nhãn ngày trong năm 1582.
- Ngày `2021-01-01` thuộc năm tuần ISO **2020**, nên formatter `ISO_WEEK_DATE` cho kết quả bắt đầu bằng `2020`.
- `toEpochDay()` đếm **ngày lịch** từ mốc ISO `1970-01-01`; không phải Unix timestamp tính bằng giây.

### 6.1. Kiểm tra ngày không hợp lệ

`LocalDate.of(2023, 2, 29)`, `LocalDate.of(1900, 2, 29)` và `LocalDate.of(1500, 2, 29)` đều ném `DateTimeException`. Hãy dùng kiểu thời gian có kiểm tra hợp lệ thay vì xử lý `String` rồi giả định mọi ngày có ngày 29/2.

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class InvalidDateDemo {
    public static void main(String[] args) {
        try {
            LocalDate.of(1900, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("Invalid Gregorian date");
        }
    }
}
~~~

Lưu ví dụ độc lập này thành **`InvalidDateDemo.java`**; biên dịch với `javac InvalidDateDemo.java` và chạy `java InvalidDateDemo`. Stdout:

~~~text
Invalid Gregorian date
~~~

## 7. Parse/format chính xác: `u`, `y`, `Y` và các formatter ISO

`LocalDate.parse("2024-02-29")` dùng formatter ngày ISO mặc định. Khi trao đổi dữ liệu, ưu tiên formatter dựng sẵn như:

- `DateTimeFormatter.ISO_LOCAL_DATE`: ngày như `2024-02-29`.
- `DateTimeFormatter.BASIC_ISO_DATE`: ngày cơ bản như `20240229` (có quy tắc tùy chọn cho offset).
- `DateTimeFormatter.ISO_ORDINAL_DATE`: ngày thứ bao nhiêu trong năm, như `2024-060`.
- `DateTimeFormatter.ISO_WEEK_DATE`: năm-tuần-thứ ISO, như `2020-W53-5`.
- `DateTimeFormatter.ISO_OFFSET_DATE_TIME`: ngày–giờ có offset, ví dụ `2024-02-29T10:15:30+07:00`.
- `DateTimeFormatter.ISO_INSTANT`: thời điểm có biểu diễn theo UTC, thường kết thúc bằng `Z`.

Ba chữ pattern thường gây lỗi:

| Pattern | Trường thời gian | Rủi ro |
|---|---|---|
| `u` / `uuuu` | Proleptic year (`YEAR`) | Phù hợp tính toán năm ISO kể cả 0 và âm |
| `y` / `yyyy` | Year-of-era (`YEAR_OF_ERA`) | Không thể hiểu riêng năm BCE nếu thiếu era |
| `Y` / `YYYY` | Week-based-year | Có thể khác năm lịch quanh đầu/cuối năm |

Dùng `uuuu-MM-dd` khi tạo pattern cho ngày lịch ISO và cần xử lý năm 0/BCE; tránh viết nhầm `YYYY-MM-dd` vì chữ `Y` lấy **năm tuần**, trong khi `MM-dd` vẫn là tháng/ngày lịch. Nếu định dạng ngày tuần ISO, dùng `ISO_WEEK_DATE` hoặc `WeekFields.ISO` nhất quán, thay vì ghép nhiều loại trường lịch.

Khi parser phải từ chối ngày sai, hiểu rõ resolver style (`STRICT`, `SMART`, `LENIENT`) và field pattern. Một pattern chỉ có `yyyy-MM-dd` trong chế độ **STRICT** thiếu trường era để xác định proleptic year; `uuuu-MM-dd` phù hợp hơn cho ngày ISO thuần túy.

**Ví dụ nhập dữ liệu:**

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public class ParseIsoDateDemo {
    public static void main(String[] args) {
        LocalDate d1 = LocalDate.parse("2024-02-29");
        LocalDate d2 = LocalDate.parse(
                "20240229", DateTimeFormatter.BASIC_ISO_DATE);
        System.out.println(d1.equals(d2));
        System.out.println(DateTimeFormatter.ISO_ORDINAL_DATE.format(d1));
    }
}
~~~

Lưu thành **`ParseIsoDateDemo.java`**, chạy `javac ParseIsoDateDemo.java` rồi `java ParseIsoDateDemo`. Stdout:

~~~text
true
2024-060
~~~

Chuỗi có năm lớn hơn 9999 có thể cần dấu `+` theo định dạng ISO mở rộng (ví dụ `+10000-01-01` với `LocalDate.toString()`). Không giả định mọi năm được biểu diễn bằng đúng bốn chữ số hoặc mọi dữ liệu lịch sử có năm dương.

## 8. Phép tính ngày theo lịch và phép tính thời lượng

Một phép cộng ngày trong `LocalDate` thao tác trên **ngày lịch**, độc lập với timezone. Ví dụ `LocalDate.of(2024, 2, 28).plusDays(1)` là `2024-02-29`; `LocalDate.of(2023, 2, 28).plusDays(1)` là `2023-03-01`.

- `Period` biểu diễn số **năm, tháng, ngày theo lịch**. `date.plusMonths(1)` có thể điều chỉnh ngày ở cuối tháng: `2024-01-31` cộng một tháng thành `2024-02-29`; cộng tiếp một tháng từ 29/2 thành 29/3. Hai lần cộng tháng không nhất thiết bằng cộng hai tháng trực tiếp từ ngày gốc.
- `Duration` biểu diễn lượng thời gian dựa trên giây/nanosecond. Với lịch theo múi giờ, việc cộng một **ngày lịch** có thể khác cộng chính xác **24 giờ** qua ranh giới giờ mùa hè. Đừng đổi ngày lịch thành `24 * 60 * 60` giây rồi giả định luôn tương đương.
- `ChronoUnit.DAYS.between(start, end)` trên `LocalDate` tính khoảng cách ngày proleptic. `toEpochDay()` chuyển ngày ISO thành số ngày tính từ `1970-01-01`, thuận tiện để so sánh/tính khoảng cách khi không liên quan giờ.

**Tính nhuận và cộng ngày không cần biết một địa phương đã đổi sang Gregorian vào ngày lịch sử nào.** Nếu bài toán cần đúng nhãn ngày lịch sử, phải bổ sung mô hình chuyển đổi Julian/Gregorian theo địa điểm, thay vì sửa thủ công `LocalDate.plusDays()`.

## 9. Phân biệt `java.time` với `java.util.GregorianCalendar`

Đối với mã hiện đại, `java.time` là lựa chọn mặc định nên ưu tiên. Kiểu cũ `java.util.GregorianCalendar` có cơ chế **cutover** giữa lịch Julian và Gregorian, mặc định gắn với cải cách năm 1582. Vì vậy hai API có thể diễn giải/di chuyển qua các ngày gần mốc này khác nhau:

- `LocalDate`: quy tắc ISO/proleptic Gregorian cho mọi ngày trong miền hỗ trợ; không có cutover 1582.
- `GregorianCalendar` cũ: có mốc chuyển lịch, đồng thời mang trạng thái múi giờ, thời gian trong ngày và chế độ lenient; cần xem cấu hình thực tế trước khi dùng cho lịch sử.

Có thể cấu hình `GregorianCalendar.setGregorianChange(...)` để điều chỉnh cutover trong tích hợp hệ thống cũ, nhưng đó không biến API này thành lựa chọn ưu tiên cho nghiệp vụ ngày ISO mới. Khi chuyển từ `Date`/`Calendar` sang `java.time`, xác định rõ dữ liệu đang biểu diễn **instant**, **local date**, **offset** hay **lịch lịch sử**; chuyển đổi máy móc có thể đổi nghĩa ngày.

## 10. Lỗi phổ biến và cách tránh

1. **Gắn ISO 8601 với quy tắc lịch một cách tuyệt đối:** ISO 8601 định nghĩa biểu diễn dữ liệu; tính hợp lệ ngày trong Java đến từ ISO chronology/proleptic Gregorian.
2. **Áp quy tắc Julian cho mọi ngày BCE hoặc trước 1582 trong `LocalDate`:** `LocalDate` không tự chọn Julian trước mốc cải cách.
3. **Giả định không có năm 0:** hệ BCE/CE lịch sử không có năm 0, còn proleptic year trong Java có năm 0; phải quy đổi khi nhập niên đại BCE.
4. **Quên ngoại lệ năm thế kỷ:** 1900 không nhuận, 2000 nhuận; tránh kiểm tra mỗi `year % 4 == 0`.
5. **Dùng `YYYY` cho năm của ngày lịch:** `YYYY` là năm của tuần, dễ gây sai dữ liệu quanh Tết dương lịch; dùng `uuuu` cho proleptic year.
6. **Nhầm ngày địa phương với timestamp:** `LocalDate` không có giờ/múi giờ, còn `Instant` biểu diễn tức thời; chuyển qua `ZoneId` có thể cho ngày khác.
7. **Giả định mọi nơi đổi lịch ngày 1582-10-15:** việc tiếp nhận Gregorian khác nhau; phải xác định nguồn sử liệu và địa lý.
8. **Dùng phép cộng giây thay cho phép cộng ngày lịch:** với `ZonedDateTime`, một ngày dân sự có thể không bằng 24 giờ vì quy tắc múi giờ.
9. **Trộn API legacy và hiện đại mà không xét cutover:** `GregorianCalendar` không có mặc định giống `LocalDate` cho mọi ngày lịch sử.
10. **Tự cắt/phân tích chuỗi ngày mà không validate:** dùng `LocalDate.parse`, formatter thích hợp và xử lý `DateTimeParseException` để phát hiện đầu vào sai.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Theo proleptic Gregorian, năm 1900 và 2000 có 29/2 không?  
**Đáp án:** 1900 không; 2000 có. Đây là quy tắc chia hết cho 100/400.

**Câu 2.** Java `LocalDate.of(1582, 10, 4).plusDays(1)` là ngày nào? Vì sao khác một số lịch sử ghi chép?  
**Đáp án:** `1582-10-05`. Java tiếp tục lịch Gregorian bằng công thức qua quá khứ; một số nước đã bỏ nhãn 05–14/10 khi cải cách năm 1582.

**Câu 3.** 44 BCE được ghi bằng proleptic year nào?  
**Đáp án:** `-43`, bởi `YEAR = 1 - YEAR_OF_ERA` với BCE.

**Câu 4.** Tại sao `DateTimeFormatter.ISO_WEEK_DATE` định dạng 2021-01-01 thành `2020-W53-5`?  
**Đáp án:** Vì tuần ISO bắt đầu thứ Hai và tuần 1 phải có ít nhất bốn ngày của năm; thứ Sáu ngày 01/01/2021 thuộc tuần cuối của năm tuần 2020.

**Câu 5.** Khi nào phải dùng `Instant` thay vì `LocalDate`?  
**Đáp án:** Khi cần biểu diễn và sắp xếp sự kiện theo **thời điểm tuyệt đối**, như timestamp log. `LocalDate` thích hợp khi thông tin bản chất chỉ là **ngày trên lịch**.

## 12. Ghi nhớ khi thiết kế hệ thống

Với ứng dụng Java cần lưu trữ ngày ISO hiện đại, hãy dùng `LocalDate` và formatter ISO cho trường dữ liệu **date-only**, `Instant` cho timestamp và kiểu offset/zoned khi thực sự có giờ cùng quy tắc múi giờ. Khi phân tích sử liệu, xác định trước ngày ghi theo lịch nào rồi mới chuyển về một mốc chuẩn. Luôn kiểm tra **năm 0/BCE**, **năm thế kỷ**, **ngày tháng 2**, **ranh giới năm tuần** và **cutover lịch sử** nếu miền nghiệp vụ có liên quan.
