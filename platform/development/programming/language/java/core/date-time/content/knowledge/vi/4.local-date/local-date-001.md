# LocalDate biểu diễn ngày không có giờ hoặc múi giờ

`LocalDate` trong Java là kiểu dữ liệu mô tả **một ngày trên lịch ISO-8601**, ví dụ `2025-04-09`, gồm **năm, tháng và ngày**. Một đối tượng `LocalDate` **không chứa giờ, phút, giây, độ lệch UTC (offset) hay mã vùng múi giờ (time zone)**. Điều này đặc biệt quan trọng: “ngày 09/04/2025” là một *ngày lịch*, còn “09/04/2025 lúc 00:00 tại Việt Nam” mới có thể xác định một thời điểm cụ thể trên trục thời gian khi gắn đúng múi giờ.

## 1. Mô hình dữ liệu và ý nghĩa

`LocalDate` thuộc gói `java.time` (có từ Java 8, sử dụng tốt trên Java 17+). Nó biểu diễn ngày theo lịch ISO-8601, là immutable (*bất biến*) và thread-safe (*an toàn khi dùng chung giữa các luồng*). Những thao tác như `plusDays`, `plusMonths` và `withDayOfMonth` đều trả về đối tượng ngày mới; đối tượng ban đầu không đổi.

Một `LocalDate` như `2025-04-09` chứa ba thành phần:

- **Year:** `2025`.
- **Month:** `04` (tháng tư).
- **Day of month:** `09` (ngày thứ chín trong tháng).

Nó **không** chứa `00:00:00` ngầm định, cũng không chứa `UTC`, `Z` hay `Asia/Ho_Chi_Minh`. Vì thế, không thể suy ra duy nhất một `Instant` chỉ từ `LocalDate`: ngày 09/04 bắt đầu ở các vùng trên thế giới tại các thời điểm UTC khác nhau.

`LocalDate` phù hợp cho ngày sinh, ngày nghỉ lễ, hạn nộp theo ngày, ngày trên hóa đơn, ngày khởi hành được chọn trên lịch và những quy tắc nghiệp vụ chỉ quan tâm **ngày nào**. Nếu cần “mấy giờ”, dùng `LocalTime` hoặc `LocalDateTime`; nếu cần một thời điểm toàn cầu, dùng `Instant`; nếu cần cả giờ và múi giờ địa lý, dùng `ZonedDateTime`.

| Kiểu | Ngày | Giờ | Offset/múi giờ | Ý nghĩa điển hình |
| --- | --- | --- | --- | --- |
| `LocalDate` | Có | Không | Không | Ngày trên lịch |
| `LocalTime` | Không | Có | Không | Giờ trên đồng hồ |
| `LocalDateTime` | Có | Có | Không | Ngày + giờ địa phương, chưa thành instant |
| `OffsetDateTime` | Có | Có | Có offset | Ngày giờ gắn độ lệch UTC |
| `ZonedDateTime` | Có | Có | Có `ZoneId`/offset được xác định | Ngày giờ theo vùng |
| `Instant` | Thời điểm tuyệt đối | Không lưu ngày giờ địa phương | Không lưu vùng địa phương | Timestamp của sự kiện |

## 2. Tạo LocalDate, truy xuất thành phần và tính bất biến

Các API thông dụng:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalDate parsed = LocalDate.parse("2025-04-09");
int year = date.getYear();            // 2025
int month = date.getMonthValue();     // 4
int day = date.getDayOfMonth();       // 9
DayOfWeek dayOfWeek = date.getDayOfWeek(); // WEDNESDAY
LocalDate tomorrow = date.plusDays(1);
~~~

`LocalDate.of(year, month, dayOfMonth)` kiểm tra tính hợp lệ của ngày. Ví dụ `LocalDate.of(2025, 2, 29)` ném `DateTimeException` vì năm 2025 không nhuận. Ngược lại, `2024-02-29` hợp lệ. Không nên lưu ngày ở dạng ba số tùy ý rồi tự tính số ngày của tháng; hãy để thư viện kiểm tra.

`LocalDate.parse(String)` theo mặc định chờ định dạng ISO như `2025-04-09`. Chuỗi `09/04/2025` cần formatter riêng. `toString()` trả về biểu diễn ISO của ngày, độc lập với locale của máy.

Vì bất biến, câu lệnh `date.plusDays(1)` **không sửa** biến `date`. Muốn cập nhật biến, cần gán lại:

~~~java
date = date.plusDays(1);
~~~

Để so sánh thứ tự ngày, dùng `isBefore`, `isAfter`, `isEqual`, `compareTo` hoặc `equals`; so sánh `LocalDate` là so sánh **ngày lịch**, không phải thứ tự các sự kiện trong ngày.

## 3. Ví dụ Java 17+ hoàn chỉnh

Lưu thành tệp `LocalDateLessonDemo.java`:

~~~java
import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class LocalDateLessonDemo {
    public static void main(String[] args) {
        LocalDate birthday = LocalDate.of(2024, 2, 29);
        LocalDate parsed = LocalDate.parse("2025-04-09");
        LocalDate jan31 = LocalDate.of(2025, 1, 31);
        LocalDate feb = jan31.plusMonths(1);

        DateTimeFormatter vietnameseDate =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu", Locale.forLanguageTag("vi-VN"));

        Instant fixedInstant =
                Instant.parse("2025-01-01T17:30:00Z");
        Clock vietnamClock = Clock.fixed(
                fixedInstant, ZoneId.of("Asia/Ho_Chi_Minh"));
        Clock utcClock = Clock.fixed(
                fixedInstant, ZoneOffset.UTC);

        System.out.println("birth=" + birthday);
        System.out.println("nextYear=" + birthday.plusYears(1));
        System.out.println("parsed=" + parsed);
        System.out.println("plusMonth=" + feb);
        System.out.println("difference="
                + ChronoUnit.DAYS.between(jan31, feb));
        System.out.println("formatted="
                + parsed.format(vietnameseDate));
        System.out.println("parsedVI="
                + LocalDate.parse("09/04/2025", vietnameseDate));

        LocalDateTime withTime = parsed.atTime(14, 30);
        System.out.println("timeOnlyAdded=" + withTime);
        System.out.println("VNtoday=" + LocalDate.now(vietnamClock));
        System.out.println("UTCtoday=" + LocalDate.now(utcClock));
        System.out.println("VNstart=" + parsed.atStartOfDay(
                ZoneId.of("Asia/Ho_Chi_Minh")));
        DayOfWeek dayOfWeek = parsed.getDayOfWeek();
        System.out.println("DOW=" + dayOfWeek);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocalDateLessonDemo.java
java LocalDateLessonDemo
~~~

Kết quả với dữ liệu cố định trong ví dụ:

~~~text
birth=2024-02-29
nextYear=2025-02-28
parsed=2025-04-09
plusMonth=2025-02-28
difference=28
formatted=09/04/2025
parsedVI=2025-04-09
timeOnlyAdded=2025-04-09T14:30
VNtoday=2025-01-02
UTCtoday=2025-01-01
VNstart=2025-04-09T00:00+07:00[Asia/Ho_Chi_Minh]
DOW=WEDNESDAY
~~~

Điểm cốt lõi: `parsed` chỉ là ngày 09/04/2025. `parsed.atTime(14, 30)` tạo `LocalDateTime` có giờ 14:30 nhưng **vẫn chưa có múi giờ**; `parsed.atStartOfDay(ZoneId.of(...))` mới đưa vùng giờ vào quá trình xác định thời điểm bắt đầu ngày. Hai lệnh `LocalDate.now(...)` cho **hai ngày khác nhau tại cùng một instant** vì một clock dùng UTC và clock kia dùng UTC+7.

## 4. Vì sao LocalDate không có múi giờ nhưng “hôm nay” cần múi giờ?

Cần phân biệt **giá trị được lưu** với **cách xác định giá trị hiện tại**:

- `LocalDate.of(2025, 4, 9)` tạo một ngày rõ ràng, không truy cập đồng hồ hệ thống.
- `LocalDate.parse("2025-04-09")` đọc ngày từ chuỗi, cũng không cần múi giờ.
- `LocalDate.now()` lấy **thời điểm hiện tại** theo đồng hồ hệ thống và **múi giờ mặc định của JVM**, rồi suy ra ngày. Kết quả phụ thuộc cấu hình máy chạy.
- `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` lấy “hôm nay theo lịch tại Việt Nam”.
- `LocalDate.now(clock)` nhận một `Clock` do ứng dụng cung cấp; phù hợp để chạy kiểm thử quyết định được kết quả.

Ví dụ, tại đúng `2025-01-01T17:30:00Z`, đồng hồ UTC vẫn ở **01/01/2025**, còn đồng hồ Việt Nam đã sang **02/01/2025 lúc 00:30**. Cả hai lần lấy `LocalDate` đều đúng trong vùng tương ứng. Sau khi tạo xong, từng giá trị `LocalDate` vẫn không lưu vùng giờ đã dùng để tính “hôm nay”.

Trong service hoặc bài kiểm thử cần tính “ngày hiện tại”, hãy xác định vùng nghiệp vụ (`ZoneId`) và cân nhắc truyền `Clock` qua dependency injection. Tránh giả định `LocalDate.now()` sẽ trả cùng một ngày trên máy cá nhân, CI, container và máy chủ đặt ở quốc gia khác.

## 5. Cộng trừ ngày, tháng, năm và các quy tắc biên

`LocalDate` hỗ trợ `plusDays`, `minusDays`, `plusWeeks`, `plusMonths`, `plusYears` và các toán tử thay trường như `withDayOfMonth`. Việc cộng tháng/năm có quy tắc điều chỉnh nếu ngày gốc không tồn tại trong tháng/năm đích:

~~~java
LocalDate.of(2025, 1, 31).plusMonths(1); // 2025-02-28
LocalDate.of(2024, 2, 29).plusYears(1);  // 2025-02-28
LocalDate.of(2024, 2, 29).plusDays(1);   // 2024-03-01
~~~

Với `plusMonths` và `plusYears`, Java cố giữ ngày-trong-tháng và điều chỉnh về **ngày hợp lệ cuối cùng** nếu cần. Trong khi đó, `withDayOfMonth(31)` có thể ném ngoại lệ nếu tháng hiện tại không có ngày 31. Không được giả định mọi tháng đều có 30 ngày hoặc cộng “một tháng” luôn bằng cộng 30 ngày.

Để đo khoảng cách:

~~~java
long days = ChronoUnit.DAYS.between(
        LocalDate.of(2025, 1, 31),
        LocalDate.of(2025, 2, 28)); // 28
~~~

`ChronoUnit.DAYS.between(a, b)` tính số ngày hoàn chỉnh từ `a` đến `b`; có thể âm nếu `b` trước `a`. `Period.between(a, b)` dùng thành phần **năm, tháng, ngày** trên lịch để diễn tả khoảng cách, nên không nên lấy `Period.getDays()` làm *tổng số ngày* của một khoảng dài.

Để kiểm tra năm nhuận hoặc số ngày trong tháng, có thể dùng `date.isLeapYear()` và `date.lengthOfMonth()` thay vì tự áp dụng công thức năm nhuận.

## 6. Ranh giới chuyển sang ngày giờ và instant

Từ `LocalDate`, các phép ghép thường gặp là:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalDateTime localDateTime = date.atTime(14, 30);
LocalDateTime midnight = date.atStartOfDay();
~~~

Cả `localDateTime` và `midnight` ở trên **không có zone/offset**. Riêng `atStartOfDay()` không tham số chỉ tạo `LocalDateTime` tại `00:00`, không phải UTC midnight.

Để biểu diễn điểm bắt đầu ngày theo một vùng:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant start = date.atStartOfDay(zone).toInstant();
~~~

`atStartOfDay(zone)` trả về `ZonedDateTime` tại **thời điểm hợp lệ sớm nhất của ngày đó** theo quy tắc múi giờ. Ở phần lớn ngày/vùng, đó là `00:00` địa phương. Tuy nhiên, tại vùng từng có chuyển giờ đúng nửa đêm hoặc thay đổi lịch dân sự, `00:00` có thể không tồn tại: khi đó kết quả có thể là giờ hợp lệ sau chuyển đổi. Vì thế, không nên coi `date.atStartOfDay(zone).toInstant()` bằng “00:00 UTC”.

Nếu xác định khoảng thời gian toàn bộ một ngày theo vùng, nên xác định **hai biên riêng**:

~~~java
Instant inclusiveStart = date.atStartOfDay(zone).toInstant();
Instant exclusiveEnd = date.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
// Sự kiện trong ngày: instant >= inclusiveStart
// và instant < exclusiveEnd.
~~~

Khoảng nửa kín `[start, end)` tránh bỏ sót mili/vi/nano giây ở cuối ngày và thường hoạt động đúng ở những ngày kéo dài **23 hoặc 25 giờ do DST**. Đừng mặc định một ngày lịch tại mọi vùng luôn dài đúng 24 giờ. Nếu ngày lịch bị bỏ qua hoàn toàn do thay đổi múi giờ lịch sử, nghiệp vụ phải xác định chính sách phù hợp.

Điều ngược lại cũng quan trọng: từ một `Instant`, phải áp vùng mong muốn trước khi lấy ngày:

~~~java
LocalDate localDay = instant.atZone(zone).toLocalDate();
~~~

Không nên cắt 10 ký tự đầu của chuỗi timestamp UTC để tìm ngày ở Việt Nam hay ở vùng khác.

## 7. Parse, format và locale

`LocalDate.parse("2025-04-09")` dùng ISO date mặc định. Nếu dữ liệu nhập dùng `dd/MM/uuuu`, cần có formatter cùng mẫu:

~~~java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu", Locale.forLanguageTag("vi-VN"));
LocalDate date = LocalDate.parse("09/04/2025", formatter);
String display = date.format(formatter); // "09/04/2025"
~~~

Mẫu `dd/MM/uuuu` là **ngày/tháng/năm proleptic**, không phải tháng/ngày/năm. Chữ `M` viết hoa biểu diễn tháng, `m` viết thường biểu diễn phút trong phần giờ. `MM` thường yêu cầu hai chữ số trong mẫu này. Phân tích chuỗi sai mẫu hoặc ngày không hợp lệ thường ném `DateTimeParseException`; ứng dụng nên bắt lỗi ở ranh giới nhận dữ liệu và trả thông báo rõ ràng cho người dùng.

Khi chỉ biểu diễn ngày, dùng `ISO_LOCAL_DATE` hoặc chuỗi `yyyy-MM-dd` theo hợp đồng API; không tự thêm `Z` vào `LocalDate`. Trong pattern của `DateTimeFormatter`, `uuuu` biểu diễn năm proleptic; `yyyy` là năm-trong-kỷ nguyên và có những khác biệt tại các năm trước Công nguyên. Đặc biệt, `YYYY` là **năm theo tuần** (week-based-year) và có thể khác năm lịch ở cuối/đầu năm, nên không thay `uuuu` bằng `YYYY` một cách tùy tiện.

Nếu một ứng dụng dùng ngày theo lịch khác ISO (ví dụ lịch địa phương ngoài Gregorian), cần xem xét các kiểu thời gian/chronology tương ứng; `LocalDate` mặc định là ngày theo lịch ISO, không tự chuyển sang lịch khác bằng cách đổi `Locale`.

## 8. Dùng trong model, API và cơ sở dữ liệu

Một số cách dùng tốt:

- **Sinh nhật/ngày lễ/ngày tốt nghiệp:** lưu `LocalDate` vì nghiệp vụ cần một ngày lịch, không có “giờ sinh” hay instant được ngầm xác định.
- **Ngày hóa đơn, hạn chót theo ngày:** lưu `LocalDate` nếu hợp đồng định nghĩa “đến hết ngày 09/04” theo ngày lịch. Khi cần kiểm tra deadline bằng thời gian thực, phải chọn vùng nghiệp vụ và ranh giới ngày rõ ràng.
- **REST JSON:** nếu trường `dueDate` mang nghĩa ngày, truyền chuỗi như `"2025-04-09"` và khai báo schema là ngày; đừng giả vờ nó là `"2025-04-09T00:00:00Z"` vì như vậy đã tạo một instant với nghĩa khác.
- **SQL:** cột kiểu `DATE` thường phù hợp với `LocalDate`; trong JDBC có thể dùng `PreparedStatement.setObject(index, localDate)` và `ResultSet.getObject(column, LocalDate.class)` nếu driver hỗ trợ JDBC 4.2. Phải kiểm tra mapping thực tế của driver/ORM và kiểu cột.
- **Lịch họp:** chỉ `LocalDate` chưa đủ nếu cuộc họp diễn ra 09:00 tại London; cần giờ cùng vùng hoặc offset theo quy tắc cụ thể.
- **Audit/log sự kiện:** “sự kiện đã xảy ra lúc nào” nên lưu `Instant`/timestamp tuyệt đối; có thể **suy ra** ngày địa phương sau khi biết vùng muốn báo cáo.

Ví dụ Java trong DTO:

~~~java
public record LeaveRequest(
        LocalDate startDate,
        LocalDate endDate
) {}
~~~

Đây là **đoạn khai báo kiểu** dùng trong tệp riêng (không phải ví dụ chạy độc lập). Nó diễn tả ngày nghỉ theo lịch. Ứng dụng phải tự xác định quy ước: `endDate` có bao gồm ngày cuối không, ngày nghỉ tính theo zone nào và có loại trừ cuối tuần/ngày lễ không. `LocalDate` không tự biết các chính sách đó.

## 9. Lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Cho rằng `LocalDate` luôn có `00:00:00` | Nhầm ngày lịch với thời điểm trên trục UTC | Chỉ ghép giờ/zone khi nghiệp vụ yêu cầu |
| Gắn `Z` vào `2025-04-09` | Biến một ngày không có giờ thành chuỗi vô nghĩa/khác kiểu | Để ở dạng `2025-04-09` |
| Dùng `LocalDate.now()` rồi trông chờ kết quả giống nhau trên mọi máy | Lệch ngày gần ranh giới 00:00 | Cung cấp `ZoneId` hoặc `Clock` |
| Xem `LocalDate.atStartOfDay()` là `Instant` | Không thể xác định thời điểm vì thiếu zone | Dùng `atStartOfDay(zone).toInstant()` |
| Cộng tháng bằng cộng cố định 30 ngày | Sai vào tháng ngắn/năm nhuận | Dùng `plusMonths` |
| Dùng `Period.getDays()` như tổng số ngày | Bỏ qua các thành phần năm/tháng | Dùng `ChronoUnit.DAYS.between` |
| Dùng `YYYY-MM-dd` để định dạng năm lịch | Có thể hiển thị sai năm gần Tết Dương lịch | Dùng `uuuu-MM-dd` hoặc ISO formatter |
| Để thời hạn “hết ngày” nhưng không chỉ định vùng | Các máy hiểu khác nhau lúc nào hết hạn | Xác định zone và biên `start/end` |
| Lưu ngày sinh bằng `Instant` ở 00:00 UTC | Khi đổi zone ngày hiển thị có thể thay đổi | Lưu `LocalDate` nếu chỉ cần ngày sinh |

## 10. Bài tập tự kiểm tra

**Câu 1:** `LocalDate.of(2025, 12, 31)` có phải luôn tương ứng `2025-12-31T00:00:00Z` không?

**Đáp án:** Không. `LocalDate` không có giờ hay zone. Chỉ khi chủ động quy định đầu ngày theo UTC mới ra instant tương ứng; đầu ngày ở vùng khác có thể là một instant khác.

**Câu 2:** `LocalDate.of(2024, 2, 29).plusYears(1)` trả gì?

**Đáp án:** `2025-02-28` vì năm 2025 không nhuận và `plusYears` điều chỉnh về ngày hợp lệ cuối cùng của tháng đích.

**Câu 3:** Cùng một instant `2025-01-01T17:30:00Z`, “hôm nay” theo UTC và theo `Asia/Ho_Chi_Minh` là ngày nào?

**Đáp án:** UTC: `2025-01-01`; Việt Nam: `2025-01-02`. Điều này không có nghĩa `LocalDate` chứa zone; nó chỉ cho thấy phải dùng zone khi **tính ra** một ngày từ instant hiện tại.

**Câu 4:** Muốn truy vấn sự kiện xảy ra trong ngày 09/04/2025 tại Việt Nam, nên so sánh timestamp UTC thế nào?

**Đáp án:** Tạo `start = LocalDate.of(2025, 4, 9).atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh")).toInstant()` và `end = date.plusDays(1).atStartOfDay(zone).toInstant()`, rồi lọc `timestamp >= start && timestamp < end`. Đây là khoảng theo **ngày địa phương** đã xác định, không phải cắt ngày từ chuỗi UTC.

**Ghi nhớ:** `LocalDate` trả lời **“ngày nào trên lịch?”**. Nó không tự trả lời **“mấy giờ?”**, **“ở múi giờ nào?”** hay **“lúc nào trên trục UTC?”**. Hãy giữ ranh giới này rõ ràng để tránh lỗi ngày tháng, lệch múi giờ và DST.