# LocalDate và LocalTime kết hợp thành LocalDateTime trong Java

**LocalDate** biểu diễn ngày theo lịch (năm–tháng–ngày), còn **LocalTime** biểu diễn giờ trong ngày (giờ–phút–giây–nano giây). Khi một nghiệp vụ có **cả ngày và giờ**, Java cho phép kết hợp hai đối tượng này thành **LocalDateTime**. Ví dụ ngày **24/10/2026** và giờ **09:30** tạo **2026-10-24T09:30**.

**Điểm cốt lõi:** LocalDateTime vẫn là **ngày giờ địa phương chưa gắn múi giờ**. Phép ghép không tạo một Instant, không tự chọn offset UTC và không tự biết đó là giờ ở Việt Nam, Tokyo hay New York.

Bài học dùng Java 17+, tập trung vào **LocalDate.atTime(LocalTime)**, **LocalDateTime.of(LocalDate, LocalTime)**, cách tách ngược, parse dữ liệu đầu vào, phép tính qua nửa đêm và việc bổ sung ZoneId khi cần xác định một thời điểm thật.

## 1. Ý nghĩa của ba kiểu dữ liệu

| Kiểu | Dữ liệu giữ lại | Ví dụ | Không chứa |
|---|---|---|---|
| **LocalDate** | Năm–tháng–ngày | 2026-10-24 | Giờ, offset, ZoneId |
| **LocalTime** | Giờ–phút–giây–nano giây | 09:30:15.123 | Ngày, offset, ZoneId |
| **LocalDateTime** | Ngày và giờ địa phương | 2026-10-24T09:30:15.123 | Offset, ZoneId |

Dùng LocalDate khi chỉ cần ngày sinh hoặc ngày nghỉ. Dùng LocalTime khi chỉ cần giờ mở cửa lặp lại mỗi ngày. Dùng LocalDateTime khi cần một **ngày + giờ cụ thể**, chẳng hạn lịch hẹn hoặc giờ bắt đầu bài thi. Dùng Instant khi cần **thời điểm tuyệt đối** như createdAt, và cần thêm ZoneId để chuyển một LocalDateTime có ý nghĩa địa phương thành Instant.

Tên **Local** không có nghĩa “tự dùng timezone của máy chủ”. Nó nói rằng kiểu đó **chưa chứa thông tin về vùng hay offset**.

## 2. Ghép bằng LocalDate.atTime(LocalTime)

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.LocalDateTime;

LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime meeting = date.atTime(time);
~~~

Đây là **đoạn minh họa trong một phương thức**, không phải chương trình đầy đủ. **meeting** có giá trị **2026-10-24T09:30**.

**date.atTime(time)** giữ toàn bộ thành phần năm/tháng/ngày của date và toàn bộ giờ/phút/giây/nano của time. Nó **không** gắn múi giờ hay chuyển đổi UTC.

Ba kiểu này là **immutable**:

- Ghép không sửa date hoặc time.
- Phép **meeting.plusHours(2)** trả một LocalDateTime mới; nếu không gán kết quả thì biến meeting không thay đổi.
- So sánh nội dung bằng **equals()**, **isBefore()**, **isAfter()**; không dùng **==** để so sánh giá trị.

## 3. Ghép bằng LocalDateTime.of(date, time)

Cách tương đương:

~~~java
LocalDateTime first = date.atTime(time);
LocalDateTime second = LocalDateTime.of(date, time);
boolean same = first.equals(second); // true
~~~

Cả hai là API chuẩn. **date.atTime(time)** tự nhiên khi đã có LocalDate; **LocalDateTime.of(date,time)** rõ ràng khi bắt đầu từ tên kiểu đích.

Nếu chưa có hai đối tượng riêng, dùng overload nhận các trường:

~~~java
LocalDateTime simple =
        LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDateTime precise =
        LocalDateTime.of(2026, 10, 24, 9, 30, 15, 123_000_000);
~~~

Kết quả là **2026-10-24T09:30** và **2026-10-24T09:30:15.123**.

LocalDate cũng có tiện ích:

~~~java
LocalDate day = LocalDate.of(2026, 10, 24);
LocalDateTime afternoon = day.atTime(17, 45);
LocalDateTime midnight = day.atStartOfDay();
~~~

**afternoon** là **2026-10-24T17:45**; **midnight** là **2026-10-24T00:00**.

**Phân biệt overload:** **date.atStartOfDay()** trả LocalDateTime không vùng, còn **date.atStartOfDay(zone)** trả ZonedDateTime và áp dụng quy tắc đầu ngày của vùng đó, có thể không đúng 00:00 trong trường hợp đặc biệt.

## 4. Chương trình Java 17+ đầy đủ

Tạo tệp **CombineDateTimeDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class CombineDateTimeDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30, 15, 123_000_000);

        LocalDateTime meeting = day.atTime(time);
        LocalDateTime alternative = LocalDateTime.of(day, time);

        System.out.println("meeting=" + meeting);
        System.out.println("same=" + meeting.equals(alternative));
        System.out.println("atTimeHourMinute=" + day.atTime(17, 45));
        System.out.println("midnight=" + day.atStartOfDay());
        System.out.println("date=" + meeting.toLocalDate());
        System.out.println("time=" + meeting.toLocalTime());
        System.out.println("nextDay=" + meeting.plusDays(1));
    }
}
~~~

Chạy:

~~~bash
javac CombineDateTimeDemo.java
java CombineDateTimeDemo
~~~

Stdout:

~~~text
meeting=2026-10-24T09:30:15.123
same=true
atTimeHourMinute=2026-10-24T17:45
midnight=2026-10-24T00:00
date=2026-10-24
time=09:30:15.123
nextDay=2026-10-25T09:30:15.123
~~~

Giải thích: **123_000_000 nano giây** là **0,123 giây**, nên phép ghép vẫn giữ **09:30:15.123**. Hai cách ghép cho giá trị bằng nhau. **toLocalDate()** và **toLocalTime()** lấy lại từng phần. **plusDays(1)** trả ngày mới nhưng vẫn là giá trị ngày giờ địa phương chưa biết ZoneId.

## 5. Tách ngược lại hai thành phần

~~~java
LocalDateTime event =
        LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDate datePart = event.toLocalDate();
LocalTime timePart = event.toLocalTime();

LocalDateTime restored = datePart.atTime(timePart);
boolean same = restored.equals(event); // true
~~~

Đoạn mã minh họa đặt trong phương thức đã import **java.time**.

Có thể dùng các phương thức này khi một API trả LocalDateTime nhưng giao diện có hai ô chọn ngày/giờ riêng. Phép tách và ghép giữ các thành phần đến độ chính xác nano giây. Tuy nhiên nếu giao diện hoặc cơ sở dữ liệu chỉ giữ **HH:mm**, các giây và nano giây có thể bị mất **ở tầng format/lưu trữ**, không phải do atTime.

Ví dụ, **LocalTime.of(9, 30, 15, 123_000_000)** khác với **LocalTime.of(9, 30)**; cần quyết định nghiệp vụ lưu chính xác đến phút, giây hay nano giây.

## 6. LocalDateTime không có ZoneId và không phải Instant

Giả sử hai trường nhập là:

~~~text
date = 2026-01-01
time = 00:30
combined = 2026-01-01T00:30
~~~

Nếu **combined** được hiểu theo UTC, Instant tương ứng là **2026-01-01T00:30:00Z**. Nếu hiểu theo **Asia/Ho_Chi_Minh**, Instant là **2025-12-31T17:30:00Z**. Hai thời điểm khác nhau 7 giờ dù cùng một LocalDateTime.

Để quy đổi, cần ZoneId hoặc ZoneOffset hợp lệ:

~~~java
LocalDateTime local =
        LocalDate.of(2026, 1, 1).atTime(LocalTime.of(0, 30));

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(zone).toInstant();
~~~

Đoạn mã trên cần import **java.time.\***. **atZone(zone)** giải quyết quy tắc múi giờ để tạo ZonedDateTime; **toInstant()** mới chuyển thành thời điểm tuyệt đối.

Không có phương thức **local.toInstant()** không cần offset. Không tự dùng **ZoneId.systemDefault()** nếu nghiệp vụ đã biết vùng của cửa hàng hoặc người dùng: timezone mặc định JVM có thể thay đổi giữa máy phát triển, CI và production.

### Chương trình runnable: cùng LocalDateTime, hai Instant khác nhau

Tạo tệp **CombineWithZoneDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class CombineWithZoneDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 1, 1);
        LocalTime time = LocalTime.of(0, 30);
        LocalDateTime local = day.atTime(time);

        Instant utc = local.atZone(ZoneOffset.UTC).toInstant();
        Instant hcm = local.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh")
        ).toInstant();

        System.out.println("local=" + local);
        System.out.println("utc=" + utc);
        System.out.println("hcm=" + hcm);
        System.out.println("equal=" + utc.equals(hcm));
    }
}
~~~

Chạy:

~~~bash
javac CombineWithZoneDemo.java
java CombineWithZoneDemo
~~~

Stdout:

~~~text
local=2026-01-01T00:30
utc=2026-01-01T00:30:00Z
hcm=2025-12-31T17:30:00Z
equal=false
~~~

**LocalDateTime** giữ ý định ngày/giờ; **ZonedDateTime** gắn vùng và offset hợp lệ; **Instant** ghi mốc tuyệt đối. Chọn đúng kiểu theo việc nghiệp vụ muốn lưu, tính toán hay trình bày.

## 7. DST: ghép được chưa chắc giờ đó tồn tại tại một vùng

Ở nơi có **giờ mùa hè (DST)**:

- **Gap**: đồng hồ nhảy tới trước, một số giờ địa phương không tồn tại.
- **Overlap**: đồng hồ lùi, một giờ địa phương tương ứng hai offset.
- **Normal**: chỉ có một offset hợp lệ.

**LocalDateTime** không có ZoneId nên vẫn tạo được giá trị trong gap. Chẳng hạn **2026-03-08T02:30** tại **America/New_York** là giờ không tồn tại.

Tạo tệp **DstCombineDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public class DstCombineDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 3, 8);
        LocalTime time = LocalTime.of(2, 30);
        LocalDateTime local = day.atTime(time);

        ZoneId zone = ZoneId.of("America/New_York");
        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        System.out.println("requested=" + local);
        System.out.println("validOffsets=" + valid);
        System.out.println("resolved=" + local.atZone(zone));
    }
}
~~~

Chạy:

~~~bash
javac DstCombineDemo.java
java DstCombineDemo
~~~

Stdout theo dữ liệu múi giờ New York năm 2026:

~~~text
requested=2026-03-08T02:30
validOffsets=[]
resolved=2026-03-08T03:30-04:00[America/New_York]
~~~

**atZone** có chính sách mặc định: với gap, nó thường đẩy giờ sang khoảng hợp lệ tiếp theo; với overlap, nó chọn một offset theo quy tắc API. Nếu nghiệp vụ phải **từ chối giờ không tồn tại**, hoặc **hỏi người dùng chọn offset** ở overlap, phải kiểm tra **getValidOffsets** và áp dụng quy tắc riêng, không chỉ dựa vào atZone.

Quy tắc DST phụ thuộc dữ liệu múi giờ IANA và có thể thay đổi theo luật địa phương.

## 8. Cộng giờ qua nửa đêm: ghép trước, tính sau

**LocalTime** chỉ nằm trong một ngày, nên:

~~~java
LocalTime.of(23, 30).plusMinutes(90); // 01:00
~~~

Kết quả không biết ngày đã thay đổi. Khi có ngày bắt đầu:

~~~java
LocalDate day = LocalDate.of(2026, 12, 31);
LocalTime time = LocalTime.of(23, 30);

LocalDateTime begin = day.atTime(time);
LocalDateTime end = begin.plusMinutes(90);
// end = 2027-01-01T01:00
~~~

Tạo tệp **CrossMidnightDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class CrossMidnightDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 12, 31);
        LocalTime time = LocalTime.of(23, 30);

        LocalDateTime begin = day.atTime(time);
        LocalDateTime end = begin.plusMinutes(90);

        System.out.println("begin=" + begin);
        System.out.println("end=" + end);
        System.out.println("timeOnly=" + time.plusMinutes(90));
        System.out.println("elapsed=" +
                Duration.between(begin, end).toMinutes());
    }
}
~~~

Chạy:

~~~bash
javac CrossMidnightDemo.java
java CrossMidnightDemo
~~~

Stdout:

~~~text
begin=2026-12-31T23:30
end=2027-01-01T01:00
timeOnly=01:00
elapsed=90
~~~

Lưu ý **Duration.between** trên hai LocalDateTime chưa phản ánh các thay đổi offset theo DST. Nếu câu hỏi là “bao nhiêu phút **thực tế** trôi qua ở vùng này?”, cần xác định hai mốc thành Instant theo ZoneId/offset rồi đo Duration trên các Instant.

## 9. Parse từ form và format để hiển thị

Một request minh họa:

~~~json
{
  "date": "2026-10-24",
  "time": "09:30",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Tách riêng ngày và giờ để parse:

~~~java
LocalDate date = LocalDate.parse("2026-10-24");
LocalTime time = LocalTime.parse("09:30");
LocalDateTime combined = date.atTime(time);
~~~

**LocalDate.parse** và **LocalTime.parse** mặc định xử lý định dạng ISO tương ứng. Nếu API nhận chuỗi **24/10/2026 09:30**, phải cung cấp DateTimeFormatter:

~~~java
DateTimeFormatter f =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
LocalDateTime parsed =
        LocalDateTime.parse("24/10/2026 09:30", f);
~~~

Hai đoạn trên là **minh họa**, cần các import trong **java.time** và **java.time.format**.

### Chương trình đầy đủ

Tạo tệp **ParseAndCombineDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

public class ParseAndCombineDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.parse("2026-10-24");
        LocalTime time = LocalTime.parse("09:30");
        LocalDateTime combined = day.atTime(time);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");

        System.out.println("combined=" + combined);
        System.out.println("formatted=" +
                combined.format(formatter));
        System.out.println("parsed=" +
                LocalDateTime.parse("24/10/2026 09:30", formatter));
    }
}
~~~

Chạy:

~~~bash
javac ParseAndCombineDemo.java
java ParseAndCombineDemo
~~~

Stdout:

~~~text
combined=2026-10-24T09:30
formatted=24/10/2026 09:30
parsed=2026-10-24T09:30
~~~

Nếu form chỉ ghi **HH:mm**, phải xác định giây/nano được đặt về 0 theo hợp đồng. Nếu dữ liệu cần giữ độ chính xác dưới giây, việc lưu/hiển thị phải giữ đủ thành phần.

## 10. Validation và các trường hợp đặc biệt

- **LocalDate.of(2026,2,30)** ném **DateTimeException** vì ngày không tồn tại.
- **LocalTime.of(24,0)** hoặc **LocalTime.of(25,0)** ném **DateTimeException** vì giờ ngoài phạm vi.
- **LocalDate.parse("24/10/2026")** với parser ISO mặc định ném **DateTimeParseException** do sai định dạng.
- **date.atTime(null)** không hợp lệ; cần xử lý dữ liệu thiếu và kiểm tra null.
- Ghép được LocalDateTime **không chứng minh** thời điểm hợp lệ theo chính sách đặt lịch hoặc theo ZoneId.

Nếu giao diện chấp nhận **24:00** với ý nghĩa “cuối ngày”, không được đưa trực tiếp vào LocalTime. Hợp đồng ứng dụng phải chuẩn hóa thành **00:00 ngày kế tiếp**; chỉ đổi thành 00:00 mà không tăng ngày sẽ làm mất thông tin.

Hãy tách bốn mức xác thực:

1. **Cú pháp**: chuỗi có đúng định dạng không?
2. **Lịch và đồng hồ**: ngày/giờ có hợp lệ không?
3. **Nghiệp vụ**: ngày nghỉ, ca làm, giờ mở cửa và giới hạn đặt lịch?
4. **Múi giờ**: tại ZoneId có gap/overlap DST không?

Không nuốt mọi exception rồi gán ngày/giờ mặc định; làm vậy có thể tạo cuộc hẹn sai nhưng trông như hợp lệ.

## 11. Thiết kế API và lưu trữ

Một lịch hẹn thực tế có thể biểu diễn theo các trường:

~~~text
date       = 2026-10-24
time       = 09:30
zoneId     = Asia/Ho_Chi_Minh
local      = 2026-10-24T09:30
instant    = 2026-10-24T02:30:00Z
~~~

**date/time** giữ lựa chọn của người dùng, **local** là kết quả ghép, **zoneId** xác định vùng, **instant** là mốc tuyệt đối sau khi áp dụng quy tắc vùng. Không cần lưu cả bốn trường trong mọi ứng dụng, nhưng phải xác định **nguồn sự thật** và chính sách chuyển đổi.

Ví dụ lớp tiện ích:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

public class BookingTime {
    public static Instant toInstant(
            LocalDate date, LocalTime time, ZoneId zone) {
        LocalDateTime local = date.atTime(time);
        return local.atZone(zone).toInstant();
    }
}
~~~

Đây là lớp biên dịch được, **không có main**. Nó minh họa cách kết hợp và chuyển đổi theo chính sách mặc định của atZone. Trong sản phẩm cần kiểm tra DST trước khi chuyển nếu không cho phép tự điều chỉnh gap/overlap.

Đối với timestamp của sự kiện đã xảy ra, thường lưu **Instant**. Với một cuộc hẹn tương lai có ý nghĩa “09:30 tại vùng X”, cần giữ ý định **ngày–giờ địa phương và ZoneId** theo chính sách để có thể xử lý cập nhật quy tắc múi giờ.

## 12. Bảng tra nhanh

| Nhu cầu | API | Kiểu trả về |
|---|---|---|
| Ghép hai đối tượng | **date.atTime(time)** | LocalDateTime |
| Ghép bằng factory | **LocalDateTime.of(date,time)** | LocalDateTime |
| Tạo từ các trường | **LocalDateTime.of(2026,10,24,9,30)** | LocalDateTime |
| Gắn giờ vào ngày | **date.atTime(9,30)** | LocalDateTime |
| Lấy 00:00 không có vùng | **date.atStartOfDay()** | LocalDateTime |
| Tách ngày | **local.toLocalDate()** | LocalDate |
| Tách giờ | **local.toLocalTime()** | LocalTime |
| Gắn vùng | **local.atZone(zone)** | ZonedDateTime |
| Xác định UTC | **local.atZone(zone).toInstant()** | Instant |

**Không lấy “hiện tại” bằng cách ghép LocalDate.now() và LocalTime.now() trong hai lời gọi riêng**. Chúng có thể diễn ra ở hai phía của nửa đêm. Với yêu cầu hiện tại, dùng **LocalDateTime.now(clock)** hoặc lấy một Instant rồi chuyển sang ZoneId:

~~~java
Instant sampled = Instant.now(clock);
LocalDateTime localNow =
        sampled.atZone(zone).toLocalDateTime();
~~~

Đây là đoạn minh họa với **clock** và **zone** đã được cung cấp. Kết quả ngày–giờ lúc đó cùng đến từ một thời điểm quan sát.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ ghép tạo ra Instant | Thiếu ZoneId/offset | Gắn vùng khi cần thời điểm tuyệt đối |
| Dùng systemDefault() cho mọi khách hàng | Deploy sang vùng khác làm lệch giờ | ZoneId nghiệp vụ tường minh |
| Cộng LocalTime qua nửa đêm rồi ghép vào ngày cũ | Mất ngày mới | Ghép LocalDateTime trước khi cộng |
| Tưởng atStartOfDay() trả ZonedDateTime | Không có vùng | Chọn overload atStartOfDay(zone) |
| Không xử lý DST | Gap/overlap bị giải quyết ngầm | getValidOffsets và chính sách rõ |
| So sánh bằng **==** | So sánh tham chiếu | Dùng equals/isBefore/isAfter |
| Form cắt giây/nano mà không xác nhận | Mất độ chính xác | Định nghĩa hợp đồng format/lưu trữ |
| Lưu LocalDateTime như audit timestamp | Không chứa offset/ZoneId | Dùng Instant |
| Ghép hai lời gọi now() riêng | Có thể lệch ngày tại nửa đêm | Lấy một Instant hoặc now(clock) |
| Gán 24:00 vào LocalTime | Ngoại lệ | 00:00 ngày kế tiếp nếu hợp đồng cho phép |

## 14. Checklist và câu hỏi tự kiểm tra

Trước khi đưa vào ứng dụng: đã xác định ngữ nghĩa của ngày/giờ, định dạng parse, độ chính xác, xử lý ngày chuyển qua nửa đêm, ZoneId của sự kiện, DST gap/overlap, cách lưu dữ liệu, và các test ở ranh giới ngày/năm chưa?

**1. date.atTime(time) và LocalDateTime.of(date,time) cho cùng giá trị?**  
Có, với cùng các giá trị hợp lệ.

**2. Ghép 24/10/2026 với 09:30 đã biết timezone Việt Nam chưa?**  
Chưa. Kết quả là **2026-10-24T09:30**, thiếu ZoneId.

**3. LocalTime có 09:30:15.123, atTime có giữ phần nano?**  
Có. Nó giữ đầy đủ thành phần thời gian.

**4. Bắt đầu 31/12/2026 23:30, cộng 90 phút trên LocalDateTime?**  
**2027-01-01T01:00**.

**5. New York 08/03/2026 02:30 có tạo được LocalDateTime?**  
Có, nhưng đó là giờ không tồn tại theo vùng New York tại DST gap.

**6. Cách chuyển LocalDateTime sang Instant?**  
Phải có ZoneId hoặc offset hợp lệ, ví dụ **local.atZone(zone).toInstant()**.

**7. Vì sao không ghép LocalDate.now() và LocalTime.now() khi cần cùng một “bây giờ”?**  
Hai lần đọc có thể qua ranh giới ngày; lấy một thời điểm quan sát từ Clock rồi chuyển sang dạng mong muốn.

**Ghi nhớ:** Hai API **date.atTime(time)** và **LocalDateTime.of(date,time)** ghép ngày và giờ mà không làm mất các thành phần, nhưng **không tạo múi giờ**. Dùng LocalDateTime để giữ ngày trong các phép tính; bổ sung ZoneId/offset để xác định Instant khi nghiệp vụ đòi hỏi.
