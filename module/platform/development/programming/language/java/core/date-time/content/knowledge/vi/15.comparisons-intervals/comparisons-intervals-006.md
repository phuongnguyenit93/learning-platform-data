# Kiểm tra một thời điểm nằm trong khoảng bằng Instant

`Instant` biểu diễn một mốc xác định trên dòng thời gian. Để kiểm tra xem `point` có nằm giữa `start` và `end` hay không, hãy so sánh các `Instant` bằng `isBefore()`, `isAfter()` và `equals()`. Không cần chuyển timestamp thành chuỗi hoặc tự trừ mili giây để so sánh.

Trước tiên phải xác định **quy ước của hai biên**. Khoảng nửa mở `[start, end)` thường phù hợp với log, truy vấn dữ liệu và cửa sổ thời gian: lấy mốc bắt đầu nhưng loại trừ chính xác mốc kết thúc.

## 1. Instant là mốc thời gian; Duration là khoảng thời gian

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| `Instant` | Một mốc tuyệt đối trên timeline. | Sự kiện lúc `2024-06-01T12:00:00Z`. |
| `Duration` | Lượng thời gian giữa hai mốc. | 30 phút hoặc `Duration.between(start, end)`. |
| `LocalDateTime` | Ngày và giờ địa phương không có offset/zone. | `2024-06-01T19:00` chưa đủ xác định instant. |
| `ZonedDateTime` | Ngày giờ được diễn giải theo luật `ZoneId`. | Hiển thị instant theo Hà Nội/New York. |

Nếu đã có `Instant`, so sánh trực tiếp với các biên cũng là `Instant`. Hai chuỗi `2024-06-01T12:00:00Z` và `2024-06-01T19:00:00+07:00` biểu diễn cùng mốc, dù cách viết khác nhau. Không so sánh các chuỗi timestamp có format hoặc offset khác nhau; hãy parse về `Instant` trước.

`Instant` giữ độ chính xác tới nano giây trong mô hình Java. Nếu chỉ so sánh `getEpochSecond()`, hai instant có cùng giây nhưng nano khác nhau sẽ bị coi như bằng nhau ngoài ý muốn. Dùng các phương thức so sánh trực tiếp để giữ độ chính xác.

## 2. Khoảng nửa mở [start, end)

Khoảng `[start, end)` chứa điểm bắt đầu và mọi điểm sau đó, cho tới **trước** biên kết thúc:

~~~text
start <= point < end
~~~

Điều kiện Java:

~~~java
boolean contains = !point.isBefore(start) && point.isBefore(end);
~~~

`!point.isBefore(start)` có nghĩa `point >= start`. `point.isBefore(end)` có nghĩa điểm phải sớm hơn biên cuối. Vì vậy:

| Điểm kiểm tra | Thuộc `[12:00, 12:30)`? | Lý do |
|---|---|---|
| 11:59:59.999999999 | Không | Sớm hơn start. |
| 12:00:00 | Có | Biên đầu được bao gồm. |
| 12:15:00 | Có | Nằm trong khoảng. |
| 12:29:59.999999999 | Có | Vẫn trước end. |
| 12:30:00 | Không | Biên cuối bị loại. |
| 12:30:00.000000001 | Không | Muộn hơn end. |

Khoảng nửa mở rất hữu ích khi nối các cửa sổ: `[10:00, 11:00)` và `[11:00, 12:00)`. Mốc 11:00 bị loại khỏi khoảng thứ nhất và thuộc khoảng thứ hai, nên không bị đếm hai lần cũng không bị bỏ qua.

## 3. Bốn quy ước biên thường dùng

| Quy ước | Điều kiện Java | start bằng point | end bằng point |
|---|---|---|---|
| Đóng hai đầu `[start, end]` | `!point.isBefore(start) && !point.isAfter(end)` | Có | Có |
| Mở hai đầu `(start, end)` | `point.isAfter(start) && point.isBefore(end)` | Không | Không |
| Mở đầu, đóng cuối `(start, end]` | `point.isAfter(start) && !point.isAfter(end)` | Không | Có |
| Nửa mở `[start, end)` | `!point.isBefore(start) && point.isBefore(end)` | Có | Không |

`isBefore()` và `isAfter()` đều trả `false` khi hai instant bằng nhau. Vì vậy để bao gồm một biên, thường dùng phủ định của phép so sánh tương ứng. Đừng viết `point.isAfter(start)` nếu yêu cầu thực sự là point lớn hơn **hoặc bằng** start.

Các hàm minh họa sau thể hiện từng quy ước:

~~~java
static boolean containsHalfOpen(Instant p, Instant s, Instant e) {
    return !p.isBefore(s) && p.isBefore(e);
}

static boolean containsClosed(Instant p, Instant s, Instant e) {
    return !p.isBefore(s) && !p.isAfter(e);
}

static boolean containsOpen(Instant p, Instant s, Instant e) {
    return p.isAfter(s) && p.isBefore(e);
}

static boolean containsOpenClosed(Instant p, Instant s, Instant e) {
    return p.isAfter(s) && !p.isAfter(e);
}
~~~

Đây là các phương thức minh họa cần import `java.time.Instant` và đặt trong class. Hãy phản ánh quy ước biên trong tên hàm hoặc Javadoc, tránh một hàm `contains` mơ hồ.

## 4. Ví dụ Java 17+ chạy được: kiểm tra biên chính xác

Lưu tệp `InstantRangeDemo.java`:

~~~java
import java.time.Instant;

public class InstantRangeDemo {
    static boolean containsHalfOpen(Instant point, Instant start, Instant end) {
        return !point.isBefore(start) && point.isBefore(end);
    }

    static boolean containsClosed(Instant point, Instant start, Instant end) {
        return !point.isBefore(start) && !point.isAfter(end);
    }

    static boolean containsOpen(Instant point, Instant start, Instant end) {
        return point.isAfter(start) && point.isBefore(end);
    }

    static boolean containsOpenClosed(Instant point, Instant start, Instant end) {
        return point.isAfter(start) && !point.isAfter(end);
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2024-06-01T12:00:00Z");
        Instant end = Instant.parse("2024-06-01T12:30:00Z");

        Instant before = start.minusNanos(1);
        Instant atStart = start;
        Instant middle = Instant.parse("2024-06-01T12:15:00Z");
        Instant atEnd = end;
        Instant after = end.plusNanos(1);

        System.out.println("Half-open before: " + containsHalfOpen(before, start, end));
        System.out.println("Half-open at start: " + containsHalfOpen(atStart, start, end));
        System.out.println("Half-open middle: " + containsHalfOpen(middle, start, end));
        System.out.println("Half-open at end: " + containsHalfOpen(atEnd, start, end));
        System.out.println("Half-open after: " + containsHalfOpen(after, start, end));
        System.out.println("Closed at end: " + containsClosed(atEnd, start, end));
        System.out.println("Open at start: " + containsOpen(atStart, start, end));
        System.out.println("Open-closed at end: " + containsOpenClosed(atEnd, start, end));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac InstantRangeDemo.java
java InstantRangeDemo
~~~

Stdout:

~~~text
Half-open before: false
Half-open at start: true
Half-open middle: true
Half-open at end: false
Half-open after: false
Closed at end: true
Open at start: false
Open-closed at end: true
~~~

Các mốc được tạo cố định bằng `Instant.parse`, `minusNanos(1)` và `plusNanos(1)` nên đầu ra xác định, không phụ thuộc timezone mặc định hay đồng hồ thật.

## 5. Xác thực start, end và null

Trước khi kiểm tra chứa điểm, quyết định rõ phải làm gì nếu `start` sau `end`. Khoảng `start > end` thường là đầu vào sai, nên từ chối thay vì âm thầm đổi chỗ hai biên:

~~~java
if (start.isAfter(end)) {
    throw new IllegalArgumentException("start must not be after end");
}
~~~

Đây là mã minh họa cần có `start` và `end`. Nếu `start.equals(end)` thì khoảng `[start, end)` rỗng: không có điểm nào vừa lớn hơn hoặc bằng start vừa nhỏ hơn end. Trong khi đó, khoảng đóng `[start, end]` với hai biên bằng nhau chứa đúng một điểm.

Các phương thức so sánh sẽ ném `NullPointerException` nếu đối tượng bị gọi là `null`. Ứng dụng nên chọn hợp đồng thống nhất: coi các tham số là bắt buộc và từ chối sớm, hoặc định nghĩa riêng rằng điểm null có nghĩa là false. Không để hành vi khác nhau giữa các hàm.

Ví dụ kiểm tra nghiêm ngặt:

~~~java
static boolean containsHalfOpen(Instant point, Instant start, Instant end) {
    if (point == null || start == null || end == null) {
        throw new IllegalArgumentException("point/start/end are required");
    }
    if (start.isAfter(end)) {
        throw new IllegalArgumentException("start must not be after end");
    }
    return !point.isBefore(start) && point.isBefore(end);
}
~~~

Đây là một phiên bản thay thế của hàm cùng tên trong ví dụ trước, không dán cả hai phiên bản vào cùng class. `Objects.requireNonNull` cũng phù hợp nếu hợp đồng mong muốn là ném `NullPointerException`.

## 6. So sánh Instant thay vì chuỗi hay giờ địa phương

`Instant.compareTo(other)` dùng được để sắp xếp mốc thời gian; `isBefore` và `isAfter` thường diễn đạt rõ hơn khi kiểm tra điều kiện.

Tránh các lỗi sau:

- So sánh chuỗi timestamp có format hoặc UTC offset khác nhau.
- So sánh riêng giờ/phút địa phương, bỏ qua ngày và zone.
- Chuyển xuống epoch milliseconds khi nghiệp vụ phải phân biệt nano giây.
- Dùng `LocalDateTime` như một mốc tuyệt đối dù nó không chứa offset/zone.

Ví dụ hai cách viết biểu diễn cùng một mốc:

~~~java
Instant utc = Instant.parse("2024-06-01T12:00:00Z");
Instant withOffset = Instant.parse("2024-06-01T19:00:00+07:00");

System.out.println(utc.equals(withOffset));
System.out.println(utc.isBefore(withOffset));
System.out.println(utc.isAfter(withOffset));
~~~

Đây là mã minh họa. Kết quả:

~~~text
true
false
false
~~~

`equals` đúng vì hai chuỗi chỉ cùng một instant. `isBefore` và `isAfter` đều sai khi chúng bằng nhau.

## 7. Ứng dụng cho query, hiệu lực và ngày địa phương

### Truy vấn log và phân trang

Khoảng nửa mở `[from, until)` dùng tốt cho truy vấn:

~~~sql
SELECT *
FROM events
WHERE occurred_at >= :fromInstant
  AND occurred_at <  :untilInstant
ORDER BY occurred_at, event_id;
~~~

Đây là SQL minh họa; bind tham số và dùng kiểu cột phù hợp với quy ước timestamp của database. Cách này tránh trùng sự kiện đúng tại ranh giới khi ghép cửa sổ liên tiếp. Nếu nhiều sự kiện có timestamp giống nhau, dùng khóa phụ như `event_id` để tạo thứ tự phân trang ổn định.

### Hạn hiệu lực

Nếu `createdAt` là mốc bắt đầu và `expiresAt` là hạn hết hiệu lực, quy ước nửa mở phổ biến là:

~~~java
boolean active = !now.isBefore(createdAt) && now.isBefore(expiresAt);
boolean expired = !now.isBefore(expiresAt);
~~~

Tại đúng `expiresAt`, đối tượng đã hết hiệu lực. Chỉ dùng `now.isAfter(expiresAt)` để xác định quá hạn sẽ bỏ sót thời điểm bằng hạn. Trong hệ thống bảo mật, nguồn tạo mốc thời gian phải đáng tin cậy và kiểm tra cần thực hiện phía server; điều kiện khoảng đúng không tự xử lý clock skew hay race.

### Sự kiện thuộc một ngày theo múi giờ

Nếu cần sự kiện của một ngày địa phương, trước hết xác định hai ranh giới theo `ZoneId`:

~~~java
Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

Đây là mã minh họa cần khai báo `LocalDate date` và `ZoneId zone`. Sau đó lọc theo `[from, until)`. Không thay bằng `from.plus(Duration.ofHours(24))` vì một ngày ở vùng có DST có thể dài 23 hoặc 25 giờ; ranh giới ngày cũng phụ thuộc quy tắc vùng.

### Duration không thay thế quy tắc biên

`Duration.between(start, point)` cho biết thời lượng có dấu từ start đến point. Nhưng để xác định point còn trong khoảng hay đã vượt end, vẫn phải xét cả end và quy ước biên. So sánh trực tiếp Instant thường làm ý nghĩa điều kiện dễ đọc hơn.

## 8. Giao nhau của hai khoảng

Với hai khoảng nửa mở hợp lệ `A = [aStart, aEnd)` và `B = [bStart, bEnd)`, chúng giao nhau khi:

~~~java
boolean overlaps =
        aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
~~~

Đây là mã minh họa, giả định mỗi khoảng đã được xác thực `start <= end`. Hai khoảng chỉ chạm tại một biên — chẳng hạn `[10:00, 11:00)` và `[11:00, 12:00)` — không giao nhau vì 11:00 bị loại khỏi khoảng đầu.

Giao của hai khoảng hợp lệ có:

~~~text
intersectionStart = max(aStart, bStart)
intersectionEnd   = min(aEnd, bEnd)

Có giao nếu intersectionStart < intersectionEnd.
~~~

Ví dụ `A = [10:00, 12:00)` và `B = [11:00, 13:00)` cho giao `[11:00, 12:00)`. Nếu biên bắt đầu của giao bằng biên kết thúc, khoảng giao là rỗng.

### Ví dụ Java 17+: Interval

Lưu `InstantIntervalsDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;

public class InstantIntervalsDemo {
    record Interval(Instant start, Instant end) {
        Interval {
            if (start == null || end == null) {
                throw new IllegalArgumentException("bounds are required");
            }
            if (start.isAfter(end)) {
                throw new IllegalArgumentException("start after end");
            }
        }

        boolean contains(Instant point) {
            return point != null
                    && !point.isBefore(start)
                    && point.isBefore(end);
        }

        boolean isEmpty() {
            return start.equals(end);
        }

        boolean overlaps(Interval other) {
            return start.isBefore(other.end)
                    && other.start.isBefore(end);
        }

        Interval intersection(Interval other) {
            if (!overlaps(other)) {
                return null;
            }
            Instant s = start.isAfter(other.start) ? start : other.start;
            Instant e = end.isBefore(other.end) ? end : other.end;
            return new Interval(s, e);
        }
    }

    public static void main(String[] args) {
        Interval a = new Interval(
                Instant.parse("2024-06-01T10:00:00Z"),
                Instant.parse("2024-06-01T12:00:00Z"));
        Interval b = new Interval(
                Instant.parse("2024-06-01T11:00:00Z"),
                Instant.parse("2024-06-01T13:00:00Z"));
        Interval touching = new Interval(
                Instant.parse("2024-06-01T12:00:00Z"),
                Instant.parse("2024-06-01T14:00:00Z"));

        Instant atStart = a.start();
        Instant atEnd = a.end();
        Interval common = a.intersection(b);

        System.out.println("Contains start: " + a.contains(atStart));
        System.out.println("Contains end: " + a.contains(atEnd));
        System.out.println("A overlaps B: " + a.overlaps(b));
        System.out.println("A overlaps touching: " + a.overlaps(touching));
        System.out.println("Intersection: " + common);
        System.out.println("Intersection seconds: "
                + Duration.between(common.start(), common.end()).toSeconds());
        System.out.println("Empty [x,x): "
                + new Interval(atStart, atStart).isEmpty());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InstantIntervalsDemo.java
java InstantIntervalsDemo
~~~

Stdout:

~~~text
Contains start: true
Contains end: false
A overlaps B: true
A overlaps touching: false
Intersection: Interval[start=2024-06-01T11:00:00Z, end=2024-06-01T12:00:00Z]
Intersection seconds: 3600
Empty [x,x): true
~~~

Trong ví dụ, `record` có compact constructor xác thực biên. `intersection` trả `null` khi không có giao; ứng dụng thực tế có thể dùng `Optional<Interval>` để thể hiện kết quả có thể không tồn tại. `contains` trả false nếu point null, còn biên null bị từ chối tại constructor — đây là hợp đồng cụ thể của ví dụ.

## 9. Đồng hồ hiện tại và clock skew

Để kiểm tra với thời điểm hiện tại, dùng `Instant.now()`; trong code nghiệp vụ, inject `Clock` giúp unit test cố định được mốc tham chiếu:

~~~java
Instant now = clock.instant();
boolean active = !now.isBefore(start) && now.isBefore(end);
~~~

Đây là mã minh họa cần khai báo `Clock clock`. Chụp một giá trị `now` rồi dùng xuyên suốt một quyết định giúp kết quả ổn định hơn so với gọi đồng hồ nhiều lần.

`Instant` xác định một điểm, nhưng timestamp không đảm bảo đồng hồ vật lý tuyệt đối chính xác. Trong hệ phân tán, clock của hai server có thể lệch; sự kiện có thể xuất hiện theo thứ tự timestamp không phản ánh đúng quan hệ nhân quả. Với hạn bảo mật và thao tác đồng thời, cần nguồn thời gian có thẩm quyền, kiểm soát clock skew và kiểm tra điều kiện trong giao dịch phù hợp.

Dùng `Clock.fixed` trong test để kiểm soát thời gian; không cần `Thread.sleep`. Có thể tạo các mốc sát biên bằng `end.minusNanos(1)`, `end` và `end.plusNanos(1)`.

## 10. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Dùng `point.isAfter(start)` khi muốn bao gồm start. | Điểm bằng start bị loại. | Dùng `!point.isBefore(start)`. |
| Dùng `!point.isAfter(end)` cho khoảng nửa mở. | Điểm bằng end bị tính nhầm. | Dùng `point.isBefore(end)`. |
| Dùng `now.isAfter(expiresAt)` để xác định hết hạn. | Mốc bằng expiresAt không bị coi là hết hạn. | Dùng `!now.isBefore(expiresAt)`. |
| So sánh chuỗi timestamp. | Format và offset khác nhau có thể gây sai thứ tự. | Parse về Instant. |
| Chỉ so sánh epoch second. | Bỏ qua khác biệt nano giây. | Dùng `Instant.isBefore/isAfter/equals`. |
| Cộng 24 giờ để tìm đầu ngày kế tiếp của vùng. | Sai ở ngày DST hoặc quy tắc đặc biệt. | Dùng `atStartOfDay(zone)` cho cả hai ngày. |
| Bỏ qua start sau end. | Khoảng vô nghĩa hoặc điều kiện bất ngờ. | Xác thực thứ tự trước khi dùng. |
| Dùng timestamp làm thứ tự nhân quả duy nhất. | Clock skew hoặc timestamp trùng làm đảo thứ tự. | Dùng sequence/version/ID nếu cần. |
| Gọi thời gian hiện tại nhiều lần cho một quyết định. | Giá trị thay đổi giữa các lần đọc. | Chụp `now` một lần. |

## 11. Câu hỏi tự kiểm tra

**1.** Với `[start, end)`, point bằng start có thuộc khoảng không?

**Đáp án:** Có. Điều kiện `!point.isBefore(start)` cho phép bằng biên đầu.

**2.** Với `[start, end)`, point bằng end có thuộc khoảng không?

**Đáp án:** Không. Biên cuối bị loại để các cửa sổ liên tiếp không đếm trùng.

**3.** Hai khoảng `[10:00, 11:00)` và `[11:00, 12:00)` có giao nhau không?

**Đáp án:** Không. Mốc 11:00 bị loại khỏi khoảng đầu và được bao gồm ở khoảng sau.

**4.** Tại sao `isAfter()` không đủ để kiểm tra point lớn hơn hoặc bằng start?

**Đáp án:** Nó trả false khi hai giá trị bằng nhau. Dùng `!point.isBefore(start)` hoặc kết hợp `isAfter` với `equals`.

**5.** Vì sao không dùng string timestamp để kiểm tra khoảng?

**Đáp án:** Chuỗi có thể thiếu offset hoặc có format khác nhau. Hãy dùng `Instant` để so sánh các mốc tuyệt đối.

**6.** Nếu start bằng end, `[start, end)` có chứa điểm nào không?

**Đáp án:** Không. Đó là khoảng rỗng; quy ước đóng hai đầu sẽ có ý nghĩa khác.

## Ghi nhớ

Trước khi triển khai phép kiểm tra, hãy xác định biên nào được bao gồm. Với khoảng nửa mở `[start, end)`, điều kiện là `!point.isBefore(start) && point.isBefore(end)`. So sánh bằng `Instant` giữ đúng timeline và độ chính xác nano; xác thực thứ tự biên, quy định null và dùng cùng quy ước trong code, truy vấn database, hiệu lực và kiểm thử.
