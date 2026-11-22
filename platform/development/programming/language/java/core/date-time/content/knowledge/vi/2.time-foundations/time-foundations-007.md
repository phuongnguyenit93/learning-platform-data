# Giờ mùa hè và nguyên nhân ngày không luôn dài 24 giờ trong Java

**Một ngày trên lịch không nhất thiết tương ứng với đúng 24 giờ đã trôi qua.** Ở những khu vực áp dụng giờ mùa hè (*daylight saving time*, DST), đồng hồ dân sự có thể được chỉnh tiến hoặc lùi tại thời điểm chuyển đổi. Vì vậy khoảng thời gian thực giữa **đầu hai ngày lịch liên tiếp** có thể là 23 giờ, 25 giờ hoặc một giá trị khác nếu quy định múi giờ thay đổi theo cách đặc biệt.

Bài này tập trung vào sự khác nhau giữa **ngày lịch** (theo giờ địa phương của một vùng), **khoảng thời gian thực** trên dòng thời gian và cách API `java.time` của Java xử lý chúng. Đây là kiến thức quan trọng khi đặt lịch, tính thời hạn, tính phí theo ngày, tổng hợp dữ liệu và lưu timestamp.

## 1. “Ngày” trong ngữ cảnh nào?

Từ “ngày” có thể chỉ các khái niệm khác nhau:

| Khái niệm | Ý nghĩa | Công cụ Java thường dùng |
|---|---|---|
| **Ngày lịch địa phương** | Ngày có năm, tháng, ngày theo một vùng, ví dụ 10/03/2024 tại New York. | `LocalDate` |
| **Thời điểm tuyệt đối** | Một điểm trên dòng thời gian; không phụ thuộc cách hiển thị múi giờ. | `Instant` |
| **Ngày và giờ có quy tắc vùng** | Thời điểm được diễn giải theo `ZoneId`, có thể chuyển offset theo DST. | `ZonedDateTime` |
| **Khoảng đã trôi qua** | Lượng thời gian vật lý/timeline giữa hai `Instant`. | `Duration` |
| **Một đơn vị ngày lịch** | Bước sang ngày tương ứng trong lịch, có thể qua thay đổi offset. | `Period.ofDays(1)`, `LocalDate.plusDays(1)`, `ZonedDateTime.plusDays(1)` |

**Trong `java.time`, `Duration.ofDays(1)` là đúng 86.400 giây**, còn “ngày mai cùng giờ địa phương” có thể cách hiện tại 23 hoặc 25 giờ theo quy tắc múi giờ. Hai phép toán trả lời hai câu hỏi khác nhau:

- “**Sau đúng 24 giờ** kể từ thời điểm này?” → cộng `Duration.ofHours(24)` vào thời điểm, hoặc `ZonedDateTime.plusHours(24)`.
- “**Cùng giờ địa phương vào ngày mai**?” → cộng một ngày lịch bằng `ZonedDateTime.plusDays(1)` rồi để `ZoneRules` áp dụng offset thích hợp.

Đừng dùng số 86.400 giây làm định nghĩa bắt buộc cho mọi **ngày lịch dân sự trong mọi múi giờ**. Con số đó là thời lượng 24 giờ tiêu chuẩn, không phải lời hứa rằng mọi khoảng từ nửa đêm hôm nay tới nửa đêm ngày mai đều dài như vậy.

## 2. DST là gì và tại sao tạo ra ngày 23 hoặc 25 giờ?

**DST (giờ mùa hè)** là quy ước pháp lý điều chỉnh giờ đồng hồ địa phương trong một phần của năm; nhiều nơi tiến đồng hồ lên một giờ khi bắt đầu mùa DST và lùi một giờ khi kết thúc. Mục đích, thời điểm và độ lớn chuyển đổi phụ thuộc từng quốc gia/vùng và từng giai đoạn lịch sử.

Ví dụ cụ thể với vùng IANA `America/New_York` năm 2024:

### 2.1. Bắt đầu DST: ngày 10/03/2024 chỉ có 23 giờ thực

Rạng sáng 10/03/2024, đồng hồ New York đi từ `01:59:59` ở offset `-05:00` tới `03:00:00` ở offset `-04:00`. Khoảng từ `02:00` đến `02:59:59...` **không tồn tại** trong lịch giờ địa phương ngày này.

~~~text
America/New_York — bắt đầu DST, 10/03/2024

01:59:59  (-05:00)
    ↓ một giây thực
03:00:00  (-04:00)

02:00–02:59:59... là local time bị bỏ qua (gap).
00:00 ngày 10/03  → 00:00 ngày 11/03 = 23 giờ thực.
~~~

Vì nửa đêm đầu ngày 10/03 mang offset `-05:00`, còn nửa đêm đầu ngày 11/03 mang offset `-04:00`, khi đổi sang UTC:

- `2024-03-10T00:00-05:00` = `2024-03-10T05:00Z`.
- `2024-03-11T00:00-04:00` = `2024-03-11T04:00Z`.
- Hiệu bằng **23 giờ = 82.800 giây**.

Không phải Trái Đất đột nhiên tự quay nhanh hơn; độ dài trên đồng hồ dân sự bị thay đổi vì quy tắc offset.

### 2.2. Kết thúc DST: ngày 03/11/2024 dài 25 giờ thực

Ngày 03/11/2024, đồng hồ New York lùi từ `01:59:59` ở offset `-04:00` về `01:00:00` ở offset `-05:00`. **Giờ `01:00–01:59...` xuất hiện hai lần** theo hai offset khác nhau.

~~~text
America/New_York — kết thúc DST, 03/11/2024

01:00–01:59  (-04:00)  lượt thứ nhất
       ↓ đồng hồ lùi
01:00–01:59  (-05:00)  lượt thứ hai

01:30 tại New York có thể biểu diễn hai Instant khác nhau.
00:00 ngày 03/11 → 00:00 ngày 04/11 = 25 giờ thực.
~~~

Đổi sang UTC:

- `2024-11-03T00:00-04:00` = `2024-11-03T04:00Z`.
- `2024-11-04T00:00-05:00` = `2024-11-04T05:00Z`.
- Hiệu bằng **25 giờ = 90.000 giây**.

Các con số 23 và 25 giờ chỉ minh họa **vùng chuyển offset đúng một giờ**. Không phải mọi vùng, mọi năm và mọi thay đổi múi giờ đều theo quy luật đó. Có nơi không áp dụng DST; có nơi đổi 30 phút; có thay đổi chính sách làm ngày lịch ngắn hoặc dài khác thường, thậm chí bỏ hẳn ngày lịch ở một lần đổi múi giờ lịch sử.

## 3. Ba thành phần cốt lõi của Java: LocalDate, ZoneId và Instant

### 3.1. `LocalDate` không có độ dài theo giây

`LocalDate.of(2024, 3, 10)` chỉ xác định một ngày theo lịch ISO. Nó không chứa giờ, offset hay vùng; không thể suy ra “ngày này dài bao nhiêu giây” nếu chưa chỉ ra múi giờ.

### 3.2. `ZoneId` và `ZoneRules` chứa quy tắc chuyển đổi

`ZoneId.of("America/New_York")` mô tả **một vùng có lịch sử và quy tắc offset**, khác với offset cố định `ZoneOffset.of("-05:00")`. Trong năm 2024, New York có `-05:00` vào mùa đông và `-04:00` trong DST. Chỉ lưu `-05:00` sẽ **không đủ** để suy ra chuyển đổi của vùng qua các tháng.

Java sử dụng cơ sở dữ liệu quy tắc múi giờ (*TZDB*) đi cùng môi trường chạy hoặc bản cập nhật nền tảng. Chính sách thời gian do chính phủ quyết định có thể thay đổi; vì thế các lịch tương lai cần dựa trên `ZoneId` và một TZDB phù hợp, tránh tự mã hóa lịch “chủ nhật thứ hai tháng 3” cho mọi vùng.

### 3.3. `Instant` cho biết thời điểm thực trên dòng thời gian

Một local date/time **cần** vùng hoặc offset để xác định `Instant`. Ngược lại, một `Instant` có thể được hiển thị tại nhiều vùng mà vẫn là **cùng một thời điểm**:

~~~java
Instant timestamp = Instant.parse("2024-03-10T07:30:00Z");
ZonedDateTime ny = timestamp.atZone(ZoneId.of("America/New_York"));
~~~

Đoạn trên là **mã minh họa**, cần import các lớp `java.time` và được đặt trong phương thức/class nếu muốn chạy. Kết quả `ny` là `2024-03-10T03:30-04:00[America/New_York]`: vào thời điểm đó, giờ New York đã qua bước nhảy DST.

## 4. Ví dụ Java 17+: tính độ dài thực của ngày lịch

Ta chọn ngày ở New York để kết quả không phụ thuộc múi giờ mặc định trên máy. Giới hạn của một ngày lịch được xác định bằng `LocalDate.atStartOfDay(zone)` tại ngày đó và ngày kế tiếp. Sau đó lấy `Duration.between(start, end)`.

Lưu tệp `CivilDayLength.java`:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;

public class CivilDayLength {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        List<LocalDate> dates = List.of(
                LocalDate.of(2024, 3, 9),
                LocalDate.of(2024, 3, 10),
                LocalDate.of(2024, 3, 11),
                LocalDate.of(2024, 11, 3));

        for (LocalDate date : dates) {
            ZonedDateTime start = date.atStartOfDay(zone);
            ZonedDateTime nextStart = date.plusDays(1).atStartOfDay(zone);
            long hours = Duration.between(start, nextStart).toHours();

            System.out.printf(
                    "%s: %d gio (%s -> %s)%n",
                    date, hours, start.getOffset(), nextStart.getOffset());
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac CivilDayLength.java
java CivilDayLength
~~~

Stdout cho các quy tắc New York trong TZDB thông dụng:

~~~text
2024-03-09: 24 gio (-05:00 -> -05:00)
2024-03-10: 23 gio (-05:00 -> -04:00)
2024-03-11: 24 gio (-04:00 -> -04:00)
2024-11-03: 25 gio (-04:00 -> -05:00)
~~~

**Vì sao dùng `atStartOfDay(zone)`?** “Bắt đầu ngày” không nhất thiết tồn tại chính xác tại `00:00` ở mọi vùng/mọi giai đoạn lịch sử. API này tìm **thời điểm hợp lệ sớm nhất** cho ngày đã chỉ định theo luật vùng; khi có gap ở nửa đêm, nó điều chỉnh đến thời điểm hợp lệ sớm nhất. Cách tính trên đo độ dài thực của phạm vi ngày theo vùng, bao gồm những trường hợp chuyển đổi khác với DST một giờ.

**Vì sao dùng `Duration.between`?** Vì hai giá trị `ZonedDateTime` đã mang đầy đủ offset/zone, `Duration.between` tính khoảng trên timeline. Không lấy chênh lệch của mỗi trường giờ địa phương: phép trừ “00:00 đến 00:00 hôm sau = 24 giờ” đã bỏ mất đổi offset.

## 5. `plusDays(1)` khác `plusHours(24)` như thế nào?

Với `ZonedDateTime`, phép cộng **ngày** hoạt động theo trục ngày/giờ địa phương rồi giải quyết offset theo vùng; phép cộng **giờ** hoạt động theo trục thời gian đã trôi qua. Hai kết quả thường giống nhau vào ngày bình thường, nhưng tách ra ở vùng có DST.

Lưu `CalendarVsElapsed.java`:

~~~java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class CalendarVsElapsed {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime beforeSpring = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, zone);

        ZonedDateTime nextCalendarDay = beforeSpring.plusDays(1);
        ZonedDateTime after24Hours = beforeSpring.plusHours(24);

        System.out.println("Goc: " + beforeSpring);
        System.out.println("+ 1 ngay lich: " + nextCalendarDay);
        System.out.println("+ 24 gio: " + after24Hours);
        System.out.println("Thuc troi (ngay lich): "
                + Duration.between(beforeSpring, nextCalendarDay).toHours()
                + " gio");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CalendarVsElapsed.java
java CalendarVsElapsed
~~~

Stdout:

~~~text
Goc: 2024-03-09T12:00-05:00[America/New_York]
+ 1 ngay lich: 2024-03-10T12:00-04:00[America/New_York]
+ 24 gio: 2024-03-10T13:00-04:00[America/New_York]
Thuc troi (ngay lich): 23 gio
~~~

Tại thời điểm xuất phát, 12 giờ trưa ngày 09/03 ở New York:

- `plusDays(1)` giữ ý nghĩa “12 giờ trưa của ngày lịch kế tiếp” và đi qua giờ bị bỏ qua, nên thực tế chỉ trôi 23 giờ.
- `plusHours(24)` luôn cộng đúng 24 giờ trên timeline, nên đến **13 giờ** ngày 10/03 theo đồng hồ địa phương.
- Nếu bắt đầu vào trưa 02/11/2024 rồi cộng một ngày lịch thì sẽ tới trưa 03/11 nhưng **trôi 25 giờ**; cộng 24 giờ sẽ tới **11 giờ** ngày 03/11.

Quy tắc chọn:

| Ý định nghiệp vụ | Phép tính phù hợp |
|---|---|
| Cuộc hẹn **09:00 mỗi ngày** tại một thành phố | Theo `LocalDate` + `LocalTime` + `ZoneId` hoặc cộng ngày lịch với chính sách gap/overlap rõ ràng. |
| Gửi thông báo **sau đúng 24 giờ** | Dựa trên `Instant.plus(Duration.ofHours(24))`. |
| Thuê chỗ ở từ ngày nhận tới ngày trả | Đếm ngày lịch theo quy định nghiệp vụ; không chia mili giây cho 86.400.000. |
| Tính mức tiêu thụ thực tế theo giờ trôi qua | Tính `Duration` từ các `Instant`; ngày chuyển DST có thể có 23/25 giờ dữ liệu. |
| Thời hạn “hết ngày hôm nay” trong vùng của người dùng | Dựa trên **đầu ngày kế tiếp trong `ZoneId` đó**; ranh giới kết thúc thường dùng dạng loại trừ. |

**Lưu ý:** `LocalDateTime.plusHours(24)` không tự biết DST vì `LocalDateTime` **không chứa vùng**. Phải xác định vùng và giải quyết gap/overlap trước khi phát biểu về thời lượng thực.

## 6. Local time không tồn tại (gap) và local time lặp lại (overlap)

Khi kết hợp ngày-giờ địa phương với `ZoneId` có chuyển đổi, Java có thể gặp **0, 1 hoặc 2 offset hợp lệ**:

1. **Gap**: không có offset hợp lệ, ví dụ `2024-03-10T02:30` ở New York, do đồng hồ nhảy qua khoảng `02:00–02:59`.
2. **Bình thường**: đúng một offset hợp lệ.
3. **Overlap**: có hai offset hợp lệ, ví dụ `2024-11-03T01:30` ở New York, vì giờ này xảy ra hai lần.

`ZoneRules.getValidOffsets(LocalDateTime)` cho phép phát hiện điều đó. `LocalDateTime.atZone(zone)` mặc định **đẩy giờ trong gap tiến tới thời điểm hợp lệ tương ứng**, và với overlap thường chọn **offset trước chuyển đổi** (ở New York ví dụ này là `-04:00`). Đây là chính sách mặc định của Java, chưa chắc đáp ứng quy định nghiệp vụ.

Lưu tệp `GapOverlapDemo.java`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class GapOverlapDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime missing = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime repeated = LocalDateTime.of(2024, 11, 3, 1, 30);

        System.out.println("Gap offsets: "
                + rules.getValidOffsets(missing));
        System.out.println("Gap default: " + missing.atZone(zone));

        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(repeated));
        ZonedDateTime earlier = repeated.atZone(zone);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Overlap earlier: " + earlier);
        System.out.println("Overlap later: " + later);
        System.out.println("Two instants: "
                + !earlier.toInstant().equals(later.toInstant()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac GapOverlapDemo.java
java GapOverlapDemo
~~~

Stdout:

~~~text
Gap offsets: []
Gap default: 2024-03-10T03:30-04:00[America/New_York]
Overlap offsets: [-04:00, -05:00]
Overlap earlier: 2024-11-03T01:30-04:00[America/New_York]
Overlap later: 2024-11-03T01:30-05:00[America/New_York]
Two instants: true
~~~

Hai dòng “Overlap earlier” và “Overlap later” có cùng nhãn local `01:30` nhưng khác offset và khác `Instant` **đúng một giờ**. Nếu chỉ lưu chuỗi `2024-11-03 01:30`, bạn đã đánh mất khả năng biết đang nói tới lần thứ nhất hay lần thứ hai.

**Chiến lược xử lý trong ứng dụng:**

- Nếu nhập liệu yêu cầu một thời điểm không nhập nhằng, hãy hỏi người dùng chọn offset/nhánh khi overlap, hoặc dùng chính sách đã công bố (“lần đầu”, “lần sau”).
- Với gap, xác định nghiệp vụ sẽ **báo lỗi, dời tới giờ hợp lệ kế tiếp, hay dời tương ứng theo độ dài gap**. Không tự mặc định rằng việc dời một giờ luôn hợp lý.
- Dùng `zone.getRules().getValidOffsets(localDateTime)` để phát hiện; nếu cần kiểm soát nghiêm, `ZonedDateTime.ofStrict(localDateTime, desiredOffset, zone)` chỉ tạo giá trị khi offset đúng và sẽ ném `DateTimeException` nếu offset không hợp lệ.
- Khi overlap, có thể chọn rõ bằng `withEarlierOffsetAtOverlap()`, `withLaterOffsetAtOverlap()` hoặc xây dựng giá trị với offset hợp lệ đã chọn.
- Với lịch được người dùng nhập, lưu chính sách chuyển đổi và ý định múi giờ. Một `Instant` là tốt để chỉ định thời điểm duy nhất đã xác định; nhưng nó không thay thế thông tin “09:00 hằng ngày tại Paris” để tái lập lịch tương lai.

## 7. Vì sao không phải vùng nào cũng có ngày 23/25 giờ?

DST **không phải hiện tượng toàn cầu** và không phải nguồn duy nhất gây thay đổi độ dài ngày theo giờ dân sự. Quy tắc múi giờ thay đổi theo quốc gia, vùng lãnh thổ và thời kỳ.

- **Vùng không dùng DST:** `Asia/Ho_Chi_Minh` hiện không áp dụng chuyển đổi DST theo chu kỳ mùa. Trong các ngày thông thường hiện nay, độ dài ngày lịch tại đây là 24 giờ. Không suy ra mọi quy tắc lịch sử hoặc tương lai bất biến.
- **Mức chuyển offset khác một giờ:** `Australia/Lord_Howe` có lịch sử chuyển đổi DST với độ lớn 30 phút; ngày chuyển đổi có thể dài **23 giờ 30 phút** hoặc **24 giờ 30 phút**, thay vì 23/25 giờ.
- **Thay đổi đường đổi ngày/quy tắc pháp lý:** `Pacific/Apia` bỏ qua ngày 30/12/2011 khi đổi phía của đường đổi ngày quốc tế. Ví dụ này minh họa rằng ngày lịch có thể bị bỏ trống trong một vùng sau thay đổi offset rất lớn.
- **Quy tắc tương lai có thể đổi:** Hệ thống chạy trên hai bản TZDB khác nhau có thể cho kết quả khác nhau với lịch tương lai sau khi chính sách địa phương được sửa.

Đừng dựng luật cố định kiểu “mọi ngày DST đều dài 23 hay 25 giờ”, “cứ cuối tháng 3 là đổi giờ” hoặc “offset vùng X không bao giờ thay đổi”. Hãy truy vấn `ZoneRules` theo **vùng cụ thể và ngày cụ thể**.

Một ngày lịch **không đồng nghĩa với một chu kỳ tự quay chính xác 24 giờ của Trái Đất**, nhưng DST ở đây là câu chuyện về quy ước đồng hồ dân sự, không phải đo ngày thiên văn. **Giây nhuận (leap second)** là khái niệm khác, không phải nguyên nhân chính tạo ra các ngày 23/25 giờ trong ví dụ. Các lớp thông dụng của `java.time` vận hành trên thang thời gian Java và không yêu cầu lập trình viên đếm mỗi ngày DST bằng 86.399/86.401 giây.

## 8. Thiết kế ranh giới ngày, truy vấn DB và báo cáo

### 8.1. Truy vấn dữ liệu của một ngày địa phương

Để lấy bản ghi thuộc ngày `2024-03-10` theo giờ New York khi database lưu timestamp tuyệt đối, hãy tính **hai ranh giới bằng vùng New York**, rồi truy vấn khoảng nửa mở:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class DayBounds {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 3, 10);
        ZoneId zone = ZoneId.of("America/New_York");

        Instant from = date.atStartOfDay(zone).toInstant();
        Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();

        System.out.println("From:  " + from);
        System.out.println("Until: " + until);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DayBounds.java
java DayBounds
~~~

Stdout:

~~~text
From:  2024-03-10T05:00:00Z
Until: 2024-03-11T04:00:00Z
~~~

Ý nghĩa truy vấn SQL (ví dụ minh họa, cột `occurred_at` phải dùng kiểu/qui ước lưu instant tương thích):

~~~sql
SELECT *
FROM events
WHERE occurred_at >= :fromInstant
  AND occurred_at <  :untilInstant;
~~~

Khoảng `[fromInstant, untilInstant)` gồm mọi thời điểm nằm trong ngày địa phương, tránh phải sáng chế “23:59:59.999999” với độ phân giải không chắc chắn, tránh đếm trùng các bản ghi đúng tại ranh giới và vẫn đúng khi một ngày dài 23/25 giờ. Cặp ranh giới được tính bằng lịch và vùng, **không lấy `from.plus(Duration.ofHours(24))`**.

### 8.2. Tính thời lượng, số ngày và số giờ công

- **Số giờ làm thực:** lấy thời điểm bắt đầu/kết thúc được xác định duy nhất (ưu tiên `Instant` hoặc `ZonedDateTime` rõ offset), tính `Duration`. Một ca xuyên qua DST có thể khác số giờ ghi trên mặt đồng hồ.
- **Số ngày lịch:** dùng `LocalDate`/`Period` hoặc quy tắc ngày của ứng dụng; không lấy `Duration.toHours()/24` để suy ra số ngày hóa đơn.
- **Khối dữ liệu ngày:** độ dài theo giờ phải tính riêng cho từng ngày/vùng; mẫu biểu đồ theo giờ có thể thiếu một nhãn giờ hoặc có hai nhãn giờ giống nhau nhưng offset khác.
- **Lịch hẹn lặp:** lưu `LocalTime`, `ZoneId`, quy tắc lặp, cùng chính sách gap/overlap; mỗi lần chạy cần chuyển lịch dân sự sang `Instant` cho lần thực thi cụ thể.

### 8.3. Offset không thay thế ZoneId

`2024-03-10T09:00-04:00` đủ xác định một thời điểm trong năm đó, nhưng nếu người dùng yêu cầu “09:00 tại New York vào mỗi ngày làm việc”, **chỉ lưu `-04:00`** sẽ sai sau khi đồng hồ chuyển về `-05:00`. Lưu `America/New_York` để hệ thống áp dụng luật vùng cho từng ngày.

Cũng không nên dùng duy nhất `ZoneId.systemDefault()` cho nghiệp vụ phụ thuộc địa điểm người dùng: máy chủ, container và máy phát triển có thể có mặc định khác nhau. Ưu tiên vùng được cấu hình hoặc do người dùng lựa chọn có căn cứ.

## 9. Kiểm thử các ca chuyển đổi DST

Unit test tốt cần các nhóm sau:

1. **Ngày thường**, cùng offset hai ranh giới: ví dụ `2024-03-09` New York dài 24 giờ.
2. **Ngày có gap**, offset tăng: `2024-03-10` New York dài 23 giờ; `02:30` không hợp lệ.
3. **Ngày có overlap**, offset giảm: `2024-11-03` New York dài 25 giờ; `01:30` ánh xạ tới hai thời điểm khác nhau.
4. **Lịch so với elapsed time:** `plusDays(1)` giữ giờ địa phương theo chính sách giải quyết DST; `plusHours(24)` giữ thời lượng cố định.
5. **Vùng không chuyển DST và vùng chuyển khác một giờ**, nhằm không mã hóa cứng 23/25 trong mọi trường hợp.
6. **Truy vấn ranh giới và dữ liệu đặc biệt:** bản ghi đúng thời điểm đầu ngày được nhận, bản ghi đúng đầu ngày kế tiếp bị loại trừ, offset của dữ liệu trùng giờ được giữ đầy đủ.

Nếu code phải xử lý lịch tương lai, kiểm thử trên môi trường với TZDB được quản lý/ cập nhật và xác nhận lại khi chính sách múi giờ thay đổi. Ví dụ lịch sử năm 2024 ở trên được cố định ngày và vùng để dễ kiểm tra, nhưng lịch tương lai không thể bảo đảm từ một snapshot TZDB vĩnh viễn.

## 10. Những hiểu lầm dễ gây lỗi

| Hiểu lầm | Hệ quả | Cách đúng |
|---|---|---|
| “Một ngày lịch luôn là 86.400 giây.” | Tính sai ngày DST, mất hoặc dư một giờ dữ liệu. | Tính từ hai đầu ngày theo `ZoneId`. |
| “`plusDays(1)` và `plusHours(24)` luôn giống nhau.” | Lịch hằng ngày trượt một giờ hoặc timeout sai ý định. | Phân biệt lịch dân sự và thời lượng thực. |
| “`2024-11-03 01:30` ở New York chỉ có một thời điểm.” | Sự kiện bị nhập nhằng, tính sai thứ tự. | Giữ `ZoneId` + offset hoặc `Instant` sau khi giải quyết overlap. |
| “`2024-03-10 02:30` ở New York hợp lệ.” | Java có thể tự đẩy giờ mà nghiệp vụ không mong muốn. | Kiểm tra `ZoneRules` và thiết kế chính sách gap. |
| “Có offset cố định là đủ cho lịch dài hạn.” | Không theo đổi DST/quy định trong tương lai. | Lưu IANA `ZoneId`. |
| “DST diễn ra vào cùng ngày ở mọi nơi.” | Lập lịch sai khu vực, sai năm. | Đọc quy tắc TZDB của vùng cụ thể. |
| “Dùng giờ mặc định máy chủ là ổn.” | Chạy production ở môi trường khác gây sai ngày. | Truyền `ZoneId` rõ ràng. |
| “Đếm ngày bằng chia tổng mili giây cho 86.400.000.” | Sai với các ngày có offset đổi. | Đếm `LocalDate` theo quy tắc nghiệp vụ. |
| “DST liên quan trực tiếp đến leap second.” | Phân tích sai nguyên nhân ngày ngắn/dài. | Tách thay đổi giờ dân sự khỏi thời gian thiên văn/giây nhuận. |

## 11. Câu hỏi tự kiểm tra

**1. Tại sao 10/03/2024 ở New York dài 23 giờ mặc dù vẫn là một ngày lịch?**

Vì offset tiến từ `-05:00` sang `-04:00`; phần giờ địa phương `02:00–02:59...` bị bỏ qua. Khoảng giữa hai đầu ngày tương ứng chỉ là 82.800 giây.

**2. `ZonedDateTime` tại 12:00 ngày 09/03/2024 cộng `plusDays(1)` khác gì cộng `plusHours(24)`?**

`plusDays(1)` đến 12:00 ngày 10/03, trôi 23 giờ; `plusHours(24)` đến 13:00 cùng ngày, trôi 24 giờ. Khác nhau vì DST.

**3. Ngày 03/11/2024 lúc 01:30 ở New York thuộc `Instant` nào?**

Không thể xác định từ local date/time đơn lẻ. Có hai offset hợp lệ là `-04:00` và `-05:00`, tương ứng hai `Instant` cách nhau một giờ. Cần chọn offset/chính sách.

**4. Vì sao lấy “đầu ngày địa phương” và “đầu ngày kế tiếp” tốt hơn cộng 24 giờ khi lọc bản ghi một ngày?**

Vì khoảng lọc phải theo lịch dân sự trong vùng. Qua DST, ranh giới trên timeline cách nhau 23 hoặc 25 giờ; cộng 24 giờ có thể bỏ sót hoặc lấy thừa bản ghi.

**5. Ở Việt Nam hiện không chuyển DST theo mùa; có thể bỏ `ZoneId` trong mọi ứng dụng không?**

Không. Nghiệp vụ có thể phục vụ khách ở vùng khác, hoặc quy tắc múi giờ thay đổi về sau. Địa điểm và ý định lịch nên được biểu diễn tường minh khi cần.

## Ghi nhớ

- **Ngày lịch** được xác định bởi `LocalDate` và quy tắc `ZoneId`; **thời lượng thực** được đo bằng `Duration` giữa các thời điểm.
- Khi bắt đầu DST theo bước tiến một giờ, một ngày có thể dài **23 giờ**; khi kết thúc DST theo bước lùi một giờ, một ngày có thể dài **25 giờ**. Các vùng khác có thể có độ dài khác.
- **Gap** tạo giờ địa phương không tồn tại; **overlap** làm một giờ địa phương tương ứng với hai thời điểm tuyệt đối.
- Dùng `plusDays(1)` cho bước **lịch**, `plusHours(24)` hoặc `Duration.ofHours(24)` cho **24 giờ thực**. Để tính đầy đủ một ngày theo vùng, lấy `date.atStartOfDay(zone)` đến `date.plusDays(1).atStartOfDay(zone)`.
- **Luôn giữ ý nghĩa vùng và chính sách gap/overlap** khi xử lý lịch dài hạn; không giả định mọi ngày, mọi vùng và mọi năm đều cố định 24 giờ.
