# So sánh ngày giờ và giới hạn thứ tự (Java 8)

Ngày giờ là một trong những loại dữ liệu dễ bị so sánh sai nhất trong ứng dụng. “Ngày A có trước ngày B không?”, “09:00 có sớm hơn 10:00 không?”, “Ca làm 22:00–06:00 có chứa 05:00 không?”, “Event ở Hà Nội xảy ra trước event ở Tokyo không?” đều là câu hỏi về thứ tự, nhưng **không dùng cùng một khái niệm thời gian**. Một phép so sánh có thể đúng trên đồng hồ cục bộ nhưng sai khi hiểu thành thứ tự sự kiện trên dòng thời gian.

Trong Java 8, các kiểu `java.time.LocalDate`, `LocalTime` và `LocalDateTime` mang giá trị lịch/giờ **không gắn ZoneId hay UTC offset**. Chúng cung cấp `isBefore`, `isAfter`, các phép kiểm bằng nhau và `compareTo` để xác định **thứ tự cục bộ**. Khi muốn sắp các sự kiện thực sự đã xảy ra ở nhiều múi giờ, cần có thông tin vùng hoặc offset để chuyển sang `Instant`; khi dùng cửa sổ lặp mỗi ngày, cần hiểu chu kỳ qua nửa đêm; khi lập lịch vùng có DST, có thể gặp giờ bị bỏ qua hoặc lặp lại.

Bài này trình bày các API Java 8 **vẫn được dùng trên JDK hiện đại**, quy tắc biên khoảng, sorting và tie-breaker, giới hạn ngữ nghĩa, cùng bốn chương trình Java chạy độc lập với expected stdout.

## 1. Chọn đúng miền so sánh

| Giá trị | Ý nghĩa dữ liệu | So sánh được điều gì? | Điều không tự biết |
| --- | --- | --- | --- |
| `LocalDate` | Năm, tháng, ngày trong lịch ISO | Ngày 06/11 trước ngày 07/11 | Giờ, timezone, thời điểm cụ thể |
| `LocalTime` | Giờ, phút, giây, nano trong đồng hồ một ngày | 09:30 đứng trước 10:00 theo thứ tự đồng hồ | Ngày, ca qua nửa đêm, timezone |
| `LocalDateTime` | Ngày lịch + giờ đồng hồ | 06/11 09:30 đứng trước 06/11 10:00 | Offset, ZoneId, một Instant xác định |
| `Instant` | Thời điểm trên trục thời gian | Event A thực sự xảy ra trước/sau event B | Giờ địa phương hoặc vị trí ban đầu |
| `ZonedDateTime` | Ngày giờ đã resolve với vùng | Có thể suy ra Instant và hiển thị đúng vùng | Chính sách nghiệp vụ cho giờ DST mơ hồ trước khi resolve |

**Nhận định quan trọng:** LocalDate, LocalTime và LocalDateTime đều có thứ tự tự nhiên, nhưng thứ tự đó là **thứ tự giá trị cục bộ**. Nó không thể tự xác nhận rằng “sự kiện nào xảy ra trước” nếu các giá trị lấy từ nhiều múi giờ.

### Ví dụ câu hỏi đúng và sai miền

Nếu một chi nhánh chỉ lưu ngày giao hàng, dùng `LocalDate.isBefore` là chính xác. Nếu một danh sách log toàn cầu ghi `LocalDateTime` theo giờ máy của từng service rồi sort, thứ tự có thể sai, dù API `compareTo` hoạt động đúng.

Nếu một cửa hàng mở từ 22:00 tới 06:00 ngày sau, `LocalTime.of(22,0).isBefore(LocalTime.of(6,0))` trả false vì 22:00 lớn hơn 06:00 trong **một vòng đồng hồ**. Nó không có nghĩa ca làm kéo dài âm: muốn biết khoảng thời gian thực phải mang ngày vào mô hình.

## 2. isBefore, isAfter, isEqual và equals

### So sánh trước/sau

```java
// Đoạn minh họa trong phương thức có import java.time.*.
LocalDate from = LocalDate.of(2026, 11, 6);
LocalDate to = LocalDate.of(2026, 11, 7);

boolean before = from.isBefore(to); // true
boolean after = from.isAfter(to);   // false
```

- `isBefore(other)` đúng khi giá trị đứng trước giá trị khác trong thứ tự của kiểu.
- `isAfter(other)` đúng khi đứng sau.
- Nếu hai giá trị **bằng nhau**, cả isBefore lẫn isAfter đều false.
- Nếu cần một khoảng gồm cả start, dùng `!value.isBefore(start)`; nếu cần loại trừ end, dùng `value.isBefore(end)`.

`LocalDate.isEqual` kiểm cùng ngày trên dòng ngày lịch (epoch day), hữu ích cả khi làm việc với interface chronology. Với hai `LocalDate` ISO bình thường, `a.isEqual(b)` và `a.equals(b)` đều đúng nếu cùng ngày. `equals` là kiểm bình đẳng giá trị của object, không phải kiểm hai biến có trỏ cùng object hay không.

**Không dùng `==` để so giá trị của hai LocalDateTime tạo riêng.** Toán tử này so identity tham chiếu; các đối tượng java.time thuộc loại value-based, nên hãy dùng `equals` hoặc so các trường ngữ nghĩa phù hợp.

### compareTo

`compareTo` trả **số âm, 0 hoặc số dương**:

```java
// Đoạn minh họa:
int ordering = from.compareTo(to);

if (ordering < 0) {
    // from trước to
} else if (ordering == 0) {
    // cùng giá trị theo thứ tự
} else {
    // from sau to
}
```

**Không dùng `compareTo(to) == -1` để kiểm “nhỏ hơn”**: interface Comparable chỉ bảo đảm dấu, không bảo đảm độ lớn chính xác 1. Trong ví dụ nào đó kết quả có thể là -1, nhưng đó không phải lý do viết code phụ thuộc giá trị đó.

Với yêu cầu dễ hiểu như ngày hết hạn, `isBefore/isAfter` thường đọc rõ hơn. Với sorting, `Comparator` và `compareTo` là lựa chọn tự nhiên.

## 3. Thứ tự của LocalDate qua tháng, năm và năm nhuận

`LocalDate` xử lý ngày lịch ISO-8601, bao gồm chuyển tháng và năm:

```text
2026-11-05 < 2026-11-06 < 2026-11-07
2026-12-31 < 2027-01-01
2028-02-28 < 2028-02-29 < 2028-03-01
```

Không cần lấy year/month/day rồi viết hàng loạt nhánh so sánh. API đã thực hiện việc so thứ tự đúng theo lịch ISO.

Một ngày như 31/02 không hợp lệ; khi tạo bằng `LocalDate.of(2026,2,31)`, Java ném `DateTimeException` thay vì tạo một giá trị có thứ tự nhưng vô nghĩa.

`LocalDate` phù hợp cho hạn theo **ngày**: “nộp sau ngày hạn mới trễ”. Đừng tự đặt một giờ mặc định cho dữ liệu chỉ là ngày lịch rồi đổi UTC không cần thiết, vì việc đó có thể thay đổi ngày khi hiển thị ở vùng khác.

## 4. Thứ tự LocalTime và điểm giới hạn 24 giờ

`LocalTime` có miền từ `00:00` đến `23:59:59.999999999`. Có thể so:

```java
// Minh họa:
LocalTime opening = LocalTime.of(9, 30);
LocalTime closing = LocalTime.of(18, 0);
boolean early = opening.isBefore(closing); // true
```

`LocalTime` không chứa ngày. Vì vậy:

- 00:15 đứng trước 23:45 về giá trị đồng hồ **trong cùng ngày**, nhưng có thể là **sau** 23:45 nếu 00:15 là ngày kế tiếp.
- 22:00–06:00 là một **cửa sổ lặp qua nửa đêm**, không phải khoảng tuyến tính tăng trong một ngày.
- Hai hoạt động cùng `LocalTime.of(9,0)` ở hai thành phố khác nhau chưa chắc cùng Instant.
- Một giá trị “24:00” thường được biểu diễn là **00:00 ngày hôm sau** khi có ngày đi kèm; kiểu LocalTime không có giá trị 24:00.
- Khi giờ chỉ là một đồng hồ lặp theo ngày, so thứ tự không tự xử lý ngày nghỉ, DST, giờ mở cửa ngoại lệ hay ca kéo dài nhiều ngày.

Vì `LocalTime` hỗ trợ nano giây, 09:30:00.000000001 đứng **sau** 09:30:00.000000000. Nếu downstream chỉ lưu mili giây, thứ tự của hai giá trị gần nhau có thể bị mất sau khi làm tròn.

## 5. LocalDateTime so ngày trước, giờ sau

`LocalDateTime` là sự kết hợp ngày lịch và thời gian đồng hồ:

```text
2026-11-05T23:59 < 2026-11-06T00:00
2026-11-06T09:30 < 2026-11-06T09:35
2026-11-06T09:35 < 2026-11-06T10:00
```

Thứ tự ưu tiên ngày, sau đó thời gian trong ngày, gồm cả nano. Nếu hai bản ghi ở **cùng vùng địa phương được xác định rõ**, sorting theo LocalDateTime có thể phản ánh thứ tự hiển thị trên lịch. Nếu các bản ghi ở nhiều vùng, thứ tự đó **chưa** xác định thứ tự sự kiện.

`LocalDateTime` không thêm bất kỳ vùng mặc định nào khi gọi `compareTo` hoặc `isBefore`. Nếu cần biết hai event thuộc cùng một thời điểm, phải quy đổi bằng ZoneId/offset phù hợp trước khi so.

## 6. Ví dụ Java hoàn chỉnh 1 — so sánh và sorting local

Tệp **`LocalDateTimeCompareDemo.java`**:

```java
import java.time.*;
import java.util.*;

public class LocalDateTimeCompareDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 11, 6);
        LocalDate nextDay = day.plusDays(1);
        LocalTime opening = LocalTime.of(9, 30);
        LocalTime closing = LocalTime.of(10, 0);
        LocalTime precise = opening.plusNanos(1);
        LocalDateTime first = LocalDateTime.of(day, opening);
        LocalDateTime later = LocalDateTime.of(day, closing);

        check(day.isBefore(nextDay), "date before");
        check(day.compareTo(nextDay) < 0, "date compareTo");
        check(day.isEqual(LocalDate.parse("2026-11-06")),
              "same calendar date");
        check(opening.isBefore(closing), "time before");
        check(precise.isAfter(opening), "nano precision");
        check(first.isBefore(later), "local datetime before");

        List<LocalDateTime> appointments = new ArrayList<>(
            Arrays.asList(later, first.plusMinutes(5), first));
        Collections.sort(appointments);

        List<LocalDateTime> expected = Arrays.asList(
            first, first.plusMinutes(5), later);
        check(expected.equals(appointments), "sorted ISO times");

        System.out.println("dateBefore=" + day.isBefore(nextDay));
        System.out.println("sameDate=" + day.isEqual(
            LocalDate.parse("2026-11-06")));
        System.out.println("timeBefore=" + opening.isBefore(closing));
        System.out.println("nanosAfter=" + precise.isAfter(opening));
        System.out.println("localDateTimeBefore=" + first.isBefore(later));
        System.out.println("sorted=" + appointments);
        System.out.println("originalDate=" + day);
        System.out.println("PASS");
    }
}
```

Lệnh chạy với Java 8 trở lên:

```bash
javac -encoding UTF-8 LocalDateTimeCompareDemo.java
java LocalDateTimeCompareDemo
```

Với JDK mới và muốn kiểm chỉ dùng API Java 8:

```bash
javac --release 8 -encoding UTF-8 LocalDateTimeCompareDemo.java
java LocalDateTimeCompareDemo
```

Stdout đã kiểm tra:

```text
dateBefore=true
sameDate=true
timeBefore=true
nanosAfter=true
localDateTimeBefore=true
sorted=[2026-11-06T09:30, 2026-11-06T09:35, 2026-11-06T10:00]
originalDate=2026-11-06
PASS
```

Giải thích:

1. `isBefore` và dấu âm của `compareTo` thống nhất về ngày đứng trước.
2. `isEqual` đúng cho hai LocalDate cùng một ngày.
3. Nano giây quyết định thứ tự khi giờ/phút/giây bằng nhau.
4. `Collections.sort` áp dụng thứ tự tự nhiên của LocalDateTime.
5. `day.plusDays(1)` trả đối tượng mới. `day` vẫn không thay đổi vì các kiểu ngày giờ của `java.time` bất biến.
6. Chương trình dùng assertion nên thất bại nếu kết quả thực khác hợp đồng, không chỉ in màn hình.

## 7. Thiết kế khoảng: start-inclusive, end-exclusive

Một ứng dụng lọc lịch hẹn từ 09:00 đến 10:00 phải trả lời: **có lấy đúng 10:00 không?**

Một quy ước rất hữu ích là **khoảng nửa mở `[start, end)`**:

- Lấy `start`.
- Lấy mọi giá trị **sau start và trước end**.
- Không lấy `end`.

Công thức:

```java
// start, end, value là LocalDateTime của cùng miền ngữ nghĩa.
boolean inside = !value.isBefore(start) && value.isBefore(end);
```

Bảng so các quy ước:

| Ký hiệu | start | end | Biểu thức kiểm |
| --- | --- | --- | --- |
| `[start,end)` | Bao gồm | Loại trừ | `!v.isBefore(start) && v.isBefore(end)` |
| `(start,end]` | Loại trừ | Bao gồm | `v.isAfter(start) && !v.isAfter(end)` |
| `[start,end]` | Bao gồm | Bao gồm | `!v.isBefore(start) && !v.isAfter(end)` |
| `(start,end)` | Loại trừ | Loại trừ | `v.isAfter(start) && v.isBefore(end)` |

Tại sao nửa mở dễ dùng cho lịch hoặc log?

```text
Slot A: [09:00, 10:00)
Slot B: [10:00, 11:00)

09:59:59.999999999 thuộc A.
10:00:00 thuộc B, không thuộc A.
```

Hai slot liền nhau không trùng ở biên. Kiểu này cũng giúp xây khoảng truy vấn timestamp mà không cần đoán số chữ số phần thập phân lưu trong database.

### start == end và start > end

Đó là vấn đề thuộc **chính sách nghiệp vụ**:

- Với một interval tuyến tính cần độ dài dương: từ chối khi `!start.isBefore(end)`.
- Với một interval rỗng cho phép: start == end có thể đại diện tập rỗng.
- Với cửa sổ LocalTime lặp qua nửa đêm: start > end có thể **hợp lệ**, nhưng cần công thức khác.

Đừng tự động đảo hai đầu mút để chữa “start > end” nếu yêu cầu không cho phép, vì điều này có thể che một lỗi input.

## 8. Khoảng ngày bao gồm cả ngày cuối

Dữ liệu “từ 06/11 tới hết 08/11” là một khoảng **LocalDate bao gồm cả hai ngày**:

```java
// Mã minh họa, date là LocalDate.
LocalDate from = LocalDate.of(2026, 11, 6);
LocalDate toInclusive = LocalDate.of(2026, 11, 8);

boolean included =
    !date.isBefore(from) && !date.isAfter(toInclusive);
```

Nếu cần chuyển thành khoảng Instant để truy vấn các sự kiện thực, dùng ZoneId nghiệp vụ và **đầu ngày tiếp theo** làm end-exclusive:

```java
// Mã minh họa trong bối cảnh có ZoneId zone.
Instant start = from.atStartOfDay(zone).toInstant();
Instant endExclusive =
    toInclusive.plusDays(1).atStartOfDay(zone).toInstant();

// Truy vấn theo [start, endExclusive).
```

Không khuyến nghị tự tạo mốc `23:59:59.999` để diễn đạt “đến hết ngày”. Event có micro/nano giây sau mốc này có thể bị bỏ sót. Khoảng nửa mở không phụ thuộc mức precision cụ thể.

**Giới hạn của miền:** `LocalDate.MAX.plusDays(1)` không hợp lệ. Khi đầu cuối của khoảng là giá trị lớn nhất mà Java cho phép, phải dùng kiểm inclusive trực tiếp hoặc biểu diễn đầu vô hạn theo yêu cầu, không cộng 1 ngày một cách vô điều kiện.

**Giới hạn múi giờ:** `atStartOfDay(zone)` xác định thời điểm bắt đầu hợp lệ trong một ZoneId. Không được tự giả định mọi ngày ở mọi vùng đều dài 24 giờ; DST có thể làm một ngày ngắn/dài khác nhau.

## 9. Khoảng LocalTime đi qua nửa đêm

Một ca làm theo đồng hồ lặp hàng ngày từ 22:00 đến 06:00 không thể kiểm bằng công thức tuyến tính `!t.isBefore(22:00) && t.isBefore(06:00)`.

Để xử lý **chu kỳ ngày**:

- Nếu `open < close`: lấy `t >= open && t < close`.
- Nếu `open > close`: lấy `t >= open || t < close`.
- Nếu `open == close`: phải định nghĩa riêng. Trong ví dụ của bài, chọn **cửa sổ rỗng**, không tự suy ra mở cả 24 giờ.

```text
Cửa sổ 22:00–06:00 lặp hằng ngày:

22:00 ........... 23:59 | 00:00 .......... 05:59 | 06:00
       thuộc cửa sổ               thuộc cửa sổ       ngoài
```

Lưu ý: đây là kiểm **giờ trong vòng đồng hồ**. Nó không tính số giờ làm thực qua DST, không phân biệt ngày nào và không xử lý lịch ngày nghỉ. Nếu một ca có ngày bắt đầu cụ thể, nên kết hợp LocalDate/LocalTime và ZoneId để xác định các thời điểm thực tế.

## 10. Ví dụ Java hoàn chỉnh 2 — kiểm tra biên và ca đêm

Tệp **`LocalRangeBoundaryDemo.java`**:

```java
import java.time.*;

public class LocalRangeBoundaryDemo {
    static boolean inHalfOpen(LocalDateTime value,
                              LocalDateTime fromInclusive,
                              LocalDateTime toExclusive) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("invalid interval");
        }
        return !value.isBefore(fromInclusive)
            && value.isBefore(toExclusive);
    }

    static boolean inDailyWindow(LocalTime value,
                                 LocalTime opening,
                                 LocalTime closing) {
        if (opening.equals(closing)) return false; // explicit: empty
        if (opening.isBefore(closing)) {
            return !value.isBefore(opening)
                && value.isBefore(closing);
        }
        return !value.isBefore(opening)
            || value.isBefore(closing); // crosses midnight
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDateTime from = LocalDateTime.of(2026, 11, 6, 9, 0);
        LocalDateTime to = LocalDateTime.of(2026, 11, 6, 10, 0);

        boolean atStart = inHalfOpen(from, from, to);
        boolean beforeEnd =
            inHalfOpen(to.minusNanos(1), from, to);
        boolean atEnd = inHalfOpen(to, from, to);
        boolean beforeStart =
            inHalfOpen(from.minusNanos(1), from, to);

        LocalTime open = LocalTime.of(22, 0);
        LocalTime close = LocalTime.of(6, 0);
        boolean at2300 =
            inDailyWindow(LocalTime.of(23, 0), open, close);
        boolean at0500 =
            inDailyWindow(LocalTime.of(5, 0), open, close);
        boolean at1200 =
            inDailyWindow(LocalTime.NOON, open, close);
        boolean at0600 =
            inDailyWindow(close, open, close);
        boolean equalBoundsAreEmpty =
            !inDailyWindow(open, open, open);

        check(atStart && beforeEnd && !atEnd && !beforeStart,
              "half-open boundaries");
        check(at2300 && at0500 && !at1200 && !at0600
              && equalBoundsAreEmpty, "overnight window");

        System.out.println("atStart=" + atStart);
        System.out.println("beforeEnd=" + beforeEnd);
        System.out.println("atEnd=" + atEnd);
        System.out.println("beforeStart=" + beforeStart);
        System.out.println("overnight23=" + at2300);
        System.out.println("overnight05=" + at0500);
        System.out.println("overnight12=" + at1200);
        System.out.println("overnight06=" + at0600);
        System.out.println("equalBoundsAreEmpty=" + equalBoundsAreEmpty);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocalRangeBoundaryDemo.java
java LocalRangeBoundaryDemo
```

Stdout đã kiểm tra:

```text
atStart=true
beforeEnd=true
atEnd=false
beforeStart=false
overnight23=true
overnight05=true
overnight12=false
overnight06=false
equalBoundsAreEmpty=true
PASS
```

Giải thích:

- Mốc 09:00 thuộc khoảng; mốc ngay trước 10:00 thuộc; đúng 10:00 không thuộc.
- Cửa sổ 22:00–06:00 chứa 23:00 và 05:00 nhưng không chứa 12:00 hay đúng 06:00.
- `opening == closing` được định nghĩa là cửa sổ rỗng, không phải 24 giờ.
- `minusNanos(1)` chỉ để test độ chính xác ranh giới, không phải cách tạo timestamp kết thúc cho mọi hệ thống.
- Các assertion đều kiểm chính sách được ghi trong mã; nếu nghiệp vụ có cách hiểu khác, cần đổi cả logic lẫn expected.

## 11. Thứ tự LocalDateTime có thể NGƯỢC thứ tự sự kiện thật

Đây là **giới hạn quan trọng nhất** khi sử dụng kiểu local cho hệ thống đa vùng.

Cùng ngày 06/11/2026:

```text
Hà Nội: LocalDateTime 09:00, ZoneId Asia/Ho_Chi_Minh
        => Instant 02:00Z

Tokyo:  LocalDateTime 10:00, ZoneId Asia/Tokyo
        => Instant 01:00Z
```

Phép so local cho:

```text
09:00 < 10:00
=> Giờ Hà Nội đứng trước giờ Tokyo nếu chỉ nhìn đồng hồ.
```

Phép so Instant cho:

```text
02:00Z > 01:00Z
=> Sự kiện Hà Nội thực tế xảy ra SAU sự kiện Tokyo.
```

Vì vậy **không thể xếp sự kiện thực tế từ nhiều timezone bằng LocalDateTime đơn lẻ**. Cần ZoneId hoặc offset đã được xác minh theo nguồn rồi so các Instant:

```java
// Mã minh họa trong phương thức có import java.time.*.
Instant hanoi = hanoiWall.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();

Instant tokyo = tokyoWall.atZone(
    ZoneId.of("Asia/Tokyo")).toInstant();

boolean actualOrder = hanoi.isAfter(tokyo);
```

Nếu chỉ có LocalDateTime mà không còn timezone/offset gốc, **không có đủ dữ liệu để kết luận thứ tự tuyệt đối**. Không nên lặng lẽ dùng `ZoneId.systemDefault()`: múi giờ server hoặc CI không nhất thiết là múi giờ của sự kiện.

## 12. DST: một giờ local có thể không tồn tại hoặc tồn tại hai lần

Daylight Saving Time (DST) tạo hai trường hợp khó:

- **Gap:** đồng hồ nhảy lên, một số giờ local **không tồn tại**.
- **Overlap:** đồng hồ lùi xuống, một số giờ local **xuất hiện hai lần** với offset khác nhau.

Trong lịch Berlin theo tzdb được dùng cho ví dụ năm 2026:

```text
2026-03-29 02:30 ở Europe/Berlin:
    Không có offset hợp lệ (gap).

2026-10-25 02:30 ở Europe/Berlin:
    Có hai offset hợp lệ: +02:00 và +01:00 (overlap).
```

`LocalDateTime.of(2026,10,25,2,30)` vẫn là **một giá trị local**, nhưng có thể ứng với **hai Instant**. Vì vậy hai event có cùng LocalDateTime có thể thực sự xảy ra ở hai thời điểm khác nhau. Ngược lại, một LocalDateTime nằm trong gap có thể **không ứng với Instant nào** ở vùng đó.

Java 8 cung cấp:

```java
ZoneId zone = ZoneId.of("Europe/Berlin");
List<ZoneOffset> valid =
    zone.getRules().getValidOffsets(localDateTime);
```

| Số offset | Nghĩa | Chính sách cần lựa chọn |
| --- | --- | --- |
| 0 | Giờ local không tồn tại | Từ chối, yêu cầu chọn lại hoặc dịch có chủ đích |
| 1 | Giờ local hợp lệ một lần | Có thể chuyển thành Instant |
| 2 | Giờ local xuất hiện hai lần | Chọn offset sớm/muộn hoặc hỏi người dùng |

`LocalDateTime.atZone(zone)` có quy tắc mặc định đối với gap/overlap, nhưng một hệ thống đặt lịch hoặc tài chính nên **định nghĩa chính sách rõ ràng**, không mặc định rằng một giờ local luôn tương ứng đúng một event.

## 13. Ví dụ Java hoàn chỉnh 3 — local order so với Instant

Tệp **`LocalOrderingVsInstantDemo.java`**:

```java
import java.time.*;
import java.util.*;

public class LocalOrderingVsInstantDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDateTime hanoiWall =
            LocalDateTime.of(2026, 11, 6, 9, 0);
        LocalDateTime tokyoWall =
            LocalDateTime.of(2026, 11, 6, 10, 0);
        Instant hanoiInstant = hanoiWall.atZone(
            ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
        Instant tokyoInstant = tokyoWall.atZone(
            ZoneId.of("Asia/Tokyo")).toInstant();

        boolean wallOrder = hanoiWall.isBefore(tokyoWall);
        boolean instantOrder = hanoiInstant.isAfter(tokyoInstant);
        check(wallOrder && instantOrder,
              "local order can disagree with timeline order");

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime gap =
            LocalDateTime.of(2026, 3, 29, 2, 30);
        LocalDateTime overlap =
            LocalDateTime.of(2026, 10, 25, 2, 30);
        int gapOffsets = berlin.getRules().getValidOffsets(gap).size();
        int overlapOffsets =
            berlin.getRules().getValidOffsets(overlap).size();
        check(gapOffsets == 0 && overlapOffsets == 2,
              "DST gap and overlap");

        System.out.println("wallOrder=" + wallOrder);
        System.out.println("hanoiInstant=" + hanoiInstant);
        System.out.println("tokyoInstant=" + tokyoInstant);
        System.out.println("instantReverseOrder=" + instantOrder);
        System.out.println("berlinGapOffsets=" + gapOffsets);
        System.out.println("berlinOverlapOffsets=" + overlapOffsets);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocalOrderingVsInstantDemo.java
java LocalOrderingVsInstantDemo
```

Stdout đã kiểm chứng (với các quy tắc vùng của JDK dùng để chạy):

```text
wallOrder=true
hanoiInstant=2026-11-06T02:00:00Z
tokyoInstant=2026-11-06T01:00:00Z
instantReverseOrder=true
berlinGapOffsets=0
berlinOverlapOffsets=2
PASS
```

Kết luận:

1. LocalDateTime 09:00 đứng trước 10:00, nhưng Instant 02:00Z đứng **sau** 01:00Z.
2. Gap và overlap là lý do một giá trị local không luôn xác định đúng một thời điểm ở vùng có DST.
3. Muốn so sự kiện đã diễn ra, lưu và so `Instant` hoặc resolve đúng offset/ZoneId của event.
4. Muốn giữ giờ theo đồng hồ cho lịch hẹn trong tương lai, lưu `LocalDateTime + ZoneId` và chính sách chọn offset/điều chỉnh gap.
5. Luật múi giờ và tzdb có thể thay đổi. Những test phụ thuộc quy tắc một vùng trong tương lai nên ghi rõ giả định về dữ liệu timezone của runtime.

## 14. Sắp xếp danh sách có nhiều bản ghi trùng giờ

Hai booking có thể cùng LocalDateTime, ví dụ cùng bắt đầu 09:00. Nếu thứ tự hiển thị phải ổn định, nên có một **tie-breaker** theo trường khác:

```java
// Đoạn minh họa; Booking có hai getter tương ứng.
Comparator<Booking> byStartAndId =
    Comparator.comparing(Booking::getLocalStart)
              .thenComparing(Booking::getId);
```

Thứ tự sẽ là theo giờ bắt đầu rồi theo ID. Với dữ liệu trong bài:

```text
B → 09:00
C → 09:30
A → 09:00
```

Kết quả theo thời gian, rồi ID, là A, B, C.

**Không phụ thuộc vào thứ tự lấy từ nguồn không có cam kết**, chẳng hạn kết quả database không có ORDER BY. Ngay cả khi thuật toán sorting ổn định, nó chỉ giữ thứ tự đầu vào cho các khóa bằng nhau; nếu thứ tự đầu vào vốn bất định, kết quả hiển thị vẫn có thể biến đổi.

### Comparator có null?

Nếu một field ngày giờ thật sự là tùy chọn, có thể định nghĩa:

```java
// Mã minh họa; getter có thể trả null.
Comparator<Booking> nullableLocalTime =
    Comparator.comparing(
        Booking::getLocalStart,
        Comparator.nullsLast(Comparator.naturalOrder()));
```

Nhưng đây chỉ là **quy tắc hiển thị**: giờ chưa biết đặt cuối danh sách. Không có nghĩa một event không biết thời gian đã xảy ra sau tất cả event có timestamp. Nếu nghiệp vụ yêu cầu timestamp bắt buộc, nên validate thay vì xếp null tùy tiện.

### Comparator phải nhất quán

Comparator cần tuân thủ quan hệ thứ tự, nhất là tính bắc cầu. Không dùng một comparator đọc đồng hồ `now()` ở mỗi lời gọi hoặc dùng trạng thái mutable thay đổi trong lúc sort. Không dùng phép trừ timestamp/ID kiểu int rồi trả thẳng vì có thể tràn; dùng API so sánh theo kiểu.

## 15. Ví dụ Java hoàn chỉnh 4 — sort với tie-breaker

Tệp **`LocalBusinessSortDemo.java`**:

```java
import java.time.*;
import java.util.*;
import java.util.stream.*;

public class LocalBusinessSortDemo {
    static final class Booking {
        private final String id;
        private final LocalDateTime localStart;

        Booking(String id, LocalDateTime localStart) {
            this.id = id;
            this.localStart = localStart;
        }
        String getId() { return id; }
        LocalDateTime getLocalStart() { return localStart; }
        public String toString() {
            return id + "@" + localStart;
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 11, 6);
        LocalDateTime nine =
            LocalDateTime.of(day, LocalTime.of(9, 0));
        LocalDateTime nineThirty =
            LocalDateTime.of(day, LocalTime.of(9, 30));

        List<Booking> bookings = Arrays.asList(
            new Booking("B", nine),
            new Booking("C", nineThirty),
            new Booking("A", nine)
        );

        List<Booking> ordered = bookings.stream()
            .sorted(Comparator.comparing(Booking::getLocalStart)
                    .thenComparing(Booking::getId))
            .collect(Collectors.toList());

        String ids = ordered.stream().map(Booking::getId)
            .collect(Collectors.joining(","));
        check("A,B,C".equals(ids), "stable business tie-break");

        boolean sameValueDifferentInstances =
            LocalDateTime.of(2026, 11, 6, 9, 0)
            .equals(LocalDateTime.of(2026, 11, 6, 9, 0));
        check(sameValueDifferentInstances, "value equality");

        System.out.println("ordered=" + ordered);
        System.out.println("ids=" + ids);
        System.out.println("valueEquals=" + sameValueDifferentInstances);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocalBusinessSortDemo.java
java LocalBusinessSortDemo
```

Stdout đã kiểm chứng:

```text
ordered=[A@2026-11-06T09:00, B@2026-11-06T09:00, C@2026-11-06T09:30]
ids=A,B,C
valueEquals=true
PASS
```

**Phân tích:**

- A và B cùng local start 09:00; `thenComparing(Booking::getId)` làm A đứng trước B.
- C ở 09:30 đứng sau.
- Hai LocalDateTime được tạo riêng có thể bằng nhau theo `equals` vì so **giá trị**, không so tham chiếu.
- `Stream.sorted` không biến các local timestamp thành Instant; nếu booking đến từ nhiều vùng, sort theo local vẫn chỉ là thứ tự đồng hồ.
- Kết quả `collect(toList())` là một List mới; danh sách gốc trong ví dụ không bị sắp xếp tại chỗ.

## 16. So sánh ZonedDateTime và OffsetDateTime: chú ý đúng câu hỏi

`OffsetDateTime` có ngày giờ + offset nên xác định được một Instant. `ZonedDateTime` có ZoneId và offset được resolve theo quy tắc vùng.

Khi muốn biết hai event có **cùng thời điểm**, hãy so Instant:

```java
// Minh họa; zonedA/zonedB là ZonedDateTime.
boolean sameInstant =
    zonedA.toInstant().equals(zonedB.toInstant());

boolean realBefore =
    zonedA.toInstant().isBefore(zonedB.toInstant());
```

Hai ZonedDateTime ở hai vùng có thể biểu thị cùng Instant nhưng có giá trị local/ZoneId khác nhau. Vì vậy không dùng `equals` của ZonedDateTime để thay thế mọi câu hỏi “có cùng lúc không?” nếu điều bạn cần chỉ là thời điểm thực.

Offset cố định không thay cho ZoneId có DST. Một lịch hẹn tương lai ở Berlin cần giữ giờ đồng hồ theo địa phương có thể phải lưu `LocalDateTime + ZoneId` và policy resolve, không chỉ lưu offset hiện tại.

**Nguyên tắc:** so local khi ý nghĩa là thứ tự đồng hồ/lịch; so Instant khi ý nghĩa là thứ tự sự kiện toàn cầu; so các thuộc tính vùng khi nghiệp vụ thực sự cần cùng vùng.

## 17. Precision, database và tính ổn định của sort

`LocalDateTime` và `LocalTime` có độ chính xác nano giây. Nhưng một database hoặc API có thể chỉ giữ tới mili giây hoặc micro giây.

Ví dụ:

```text
Java A: 2026-11-06T09:00:00.000000001
Java B: 2026-11-06T09:00:00.000000002
```

Theo Java, A trước B. Nếu lưu ở precision mili giây, cả hai có thể thành cùng timestamp khi đọc lại. Hệ quả:

1. Comparator theo timestamp có thể trả 0 cho hai bản ghi trước đó khác nhau.
2. Nếu dùng timestamp đơn lẻ làm cursor phân trang, có thể bỏ sót record trùng giá trị.
3. Lọc sự kiện ở biên query có thể sai khi độ chính xác hoặc cách làm tròn không thống nhất.
4. Các API parse/format mất nano có thể làm round-trip không tái lập giá trị ban đầu.

**Cách làm đúng:** xác định precision của storage/API, kiểm round-trip và thêm một khóa tiebreak khi cần thứ tự bản ghi toàn phần, ví dụ cặp `(createdAt, id)`.

### Phân trang theo cursor

Với thứ tự tăng dần theo timestamp và ID, điều kiện trang kế tiếp thường theo ý tưởng:

```text
ORDER BY created_at ASC, id ASC

WHERE created_at > :lastTimestamp
   OR (created_at = :lastTimestamp AND id > :lastId)
```

Đây là ý tưởng SQL cần điều chỉnh theo database và index thật. Nếu `created_at` là LocalDateTime từ nhiều vùng, vẫn phải làm rõ **nghĩa của timestamp** trước; tiebreaker không thể chữa việc thiếu ZoneId.

## 18. Chuỗi định dạng không phải khóa sắp xếp đáng tin

Hai chuỗi theo `dd/MM/yyyy`:

```text
06/11/2026
31/10/2026
```

Khi sắp theo thứ tự ký tự, “06/11” có thể đứng **trước** “31/10”, nhưng ngày 06/11 thực ra nằm **sau** 31/10.

Đừng dùng String được format cho giao diện để quyết định thứ tự nghiệp vụ. Hãy parse bằng `DateTimeFormatter` phù hợp thành LocalDate hoặc LocalDateTime rồi so. Với thời điểm toàn cầu, parse đủ timezone/offset để tạo Instant.

Ngay cả khi định dạng ISO-8601 trong một số tình huống cho thứ tự chuỗi trùng thứ tự thời gian, nó chỉ an toàn khi cấu trúc, precision, zone/offset và phép chuẩn hóa **thống nhất**. Dùng kiểu ngày giờ rõ ràng vẫn tốt hơn dựa vào sự trùng hợp của một format.

## 19. Biên kiểu và phép cộng/trừ ngoài miền

`LocalDate.MIN` và `LocalDate.MAX` đại diện biên miền kiểu. Phép cộng `LocalDate.MAX.plusDays(1)` hoặc trừ `LocalDate.MIN.minusDays(1)` có thể ném exception.

Đối với khoảng inclusive end theo ngày:

- Nếu end còn có ngày tiếp theo, có thể chuyển thành end-exclusive bằng `end.plusDays(1)`.
- Nếu end là giá trị biên tối đa, dùng so inclusive hoặc mô hình hóa “không có giới hạn trên” thay vì phép cộng ngoài miền.
- Không dùng `LocalTime.MAX` 23:59:59.999999999 làm biên end-day trong mọi trường hợp, vì DB precision và ZoneId có thể khác nhau.
- Không giả định một ngày lịch luôn có 86.400 giây; DST có thể khiến ngày local ngắn/dài hơn.

**Không có “timestamp vô hạn” tự nhiên được giải quyết chỉ bằng việc chọn LocalDateTime.MAX.** Nếu business rule có bound không giới hạn, mô hình hóa sự vắng mặt của bound rõ ràng.

## 20. Quy tắc nghiệp vụ không tự nằm trong isBefore

Một lời gọi `a.isBefore(b)` chỉ trả lời câu hỏi giá trị a đứng trước b **theo kiểu**. Nó không tự biết:

- Hai lịch hẹn có thuộc cùng chi nhánh, cùng ZoneId hay không.
- Ngày đó có nghỉ lễ hoặc giờ mở cửa đặc biệt.
- Ca làm có qua nửa đêm và có DST hay không.
- Hai event có cùng LocalDateTime nhưng khác offset hay không.
- Một ngày hạn “đến hết ngày” là inclusive hay end-exclusive ở đầu hôm sau.
- Một task cần 24 giờ thực tế hay 1 ngày lịch.
- Thứ tự sắp có cần tie-break để phân trang không.
- Một timestamp bị mất phần nano khi lưu database hay không.
- Một field null là “không biết” hay “không áp dụng”.
- LocalDateTime parse được có hợp lệ trong ZoneId ngày DST cụ thể hay không.

Vì vậy thứ tự là **thành phần của quy tắc**, không thay thế mô hình nghiệp vụ.

## 21. Kiểm thử theo ma trận trạng thái

| Test | Kỳ vọng |
| --- | --- |
| Hai LocalDate cùng giá trị | isBefore=false, isAfter=false, equals=true |
| Hai ngày liên tiếp qua đầu tháng/năm | Thứ tự lịch đúng |
| Năm nhuận với 29/02 | Ngày hợp lệ và so thứ tự chính xác |
| Cùng giờ/phút nhưng khác nano | Nano quyết định thứ tự |
| LocalTime 23:00 và 01:00 | Thứ tự đồng hồ khác nghĩa ca qua nửa đêm |
| Hai LocalDateTime ở ngày khác | Ngày quyết định trước giờ |
| [start,end) tại start | Được lấy |
| [start,end) sát end | Được lấy |
| [start,end) đúng end | Bị loại |
| start == end | Theo chính sách khoảng rỗng hoặc lỗi |
| start > end với LocalDateTime | Từ chối nếu interval tuyến tính cần tăng |
| 22:00–06:00 mỗi ngày | 23:00 và 05:00 thuộc; 06:00 không |
| Hai local date-time ở hai ZoneId | Có thể cho thứ tự Instant đảo chiều |
| DST gap | Không có offset hợp lệ |
| DST overlap | Có hai offset hợp lệ |
| Sorting có hai booking trùng giờ | Tiebreak ID rõ |
| Giá trị null | Null policy tường minh hoặc validation |
| Lưu và đọc lại với precision thấp | Kiểm rounding/truncation |
| Ngày cuối LocalDate.MAX | Không cộng ngoài miền |
| So từ chuỗi dd/MM/yyyy | Parse trước khi sắp |
| So event đã xảy ra | Dùng Instant/UTC semantics rõ |

Test nên có **đường bình thường, ranh giới và phản ví dụ**. Chỉ so hai ngày bình thường giữa tháng không giúp phát hiện lỗi timezone, DST hoặc khoảng end-inclusive.

## 22. Những lỗi phổ biến và cách khắc phục

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Dùng `==` với java.time | So object reference | Dùng equals/isEqual/compareTo |
| Kiểm `compareTo == -1` | Không được hợp đồng bảo đảm giá trị -1 | So `< 0` |
| Dùng `value.isAfter(start)` cho khoảng gồm start | Loại mất start | `!value.isBefore(start)` |
| Dùng `!value.isAfter(end)` cho end-exclusive | Lấy cả end | `value.isBefore(end)` |
| Biểu diễn “hết ngày” bằng 23:59:59.999 | Bỏ sót precision | Đầu ngày hôm sau, khoảng nửa mở |
| Cộng 1 ngày vào LocalDate.MAX | Vượt miền | Kiểm bound hoặc dùng inclusive |
| So giờ LocalTime ca 22:00–06:00 như interval tuyến tính | Không hiểu chu kỳ | Công thức qua nửa đêm hoặc ngày+giờ |
| Dùng LocalDateTime sort event ở nhiều zone | Có thể đảo timeline | Resolve ZoneId rồi so Instant |
| Dùng systemDefault cho timezone client | Gán ngữ cảnh server sai | ZoneId từ domain |
| Không xử lý DST overlap | Một local time có hai Instant | Chọn offset hoặc policy |
| Không xử lý DST gap | Local time không tồn tại | Kiểm ZoneRules |
| Dùng String dd/MM/yyyy để sort | Thứ tự từ vựng sai | Parse thành LocalDate |
| Sort theo timestamp có thể trùng | Pagination bất ổn | Tie-breaker như ID |
| Comparator phụ thuộc state thay đổi | Vi phạm thứ tự nhất quán | Comparator thuần, bắc cầu |
| Dùng LocalDateTime.MIN làm sentinel null | Tạo một thời điểm giả | Optional/validation/null policy |
| Giả định một ngày luôn 24 giờ | DST có thể khác | Duration/Period đúng nghĩa |
| Bỏ qua precision DB | Kết quả so khác sau round-trip | Định nghĩa precision + test |
| Nghĩ equals của ZonedDateTime chỉ so Instant | ZoneId và cấu trúc giá trị quan trọng | So toInstant nếu cần cùng mốc |

## 23. Bài tập thực hành và đáp án

**Bài 1 — hạn nộp theo ngày.** Deadline là 06/11/2026. Nếu chỉ coi là trễ khi nộp **sau ngày hạn**, nộp trong ngày 06/11 có trễ không?

Đáp án: không. Dùng `submittedDate.isAfter(deadline)`, bằng ngày trả false. Không cần tự thêm giờ nếu nghiệp vụ chỉ nói tới ngày.

**Bài 2 — hai khung liền kề.** Slot A là [09:00,10:00), slot B là [10:00,11:00). Giá trị đúng 10:00 thuộc khung nào?

Đáp án: chỉ thuộc B. Với khoảng nửa mở, start được lấy và end bị loại.

**Bài 3 — cửa sổ ca đêm.** Cửa hàng mở 22:00–06:00 hàng ngày; xác định 05:30, 12:00, 23:15, 06:00 có thuộc cửa sổ không.

Đáp án: 05:30 và 23:15 có; 12:00 và 06:00 không, khi dùng end-exclusive và policy ca qua nửa đêm.

**Bài 4 — thứ tự giữa hai vùng.** Hà Nội 09:00 cùng ngày, Tokyo 10:00 cùng ngày. Sự kiện nào trước theo timeline?

Đáp án: Tokyo: 10:00 UTC+09 = 01:00Z, Hà Nội 09:00 UTC+07 = 02:00Z. Không so LocalDateTime đơn lẻ để trả lời.

**Bài 5 — booking trùng giờ.** Hai booking A/B cùng 09:00, C lúc 09:30. Muốn sắp theo local start rồi ID.

Đáp án dùng `Comparator.comparing(Booking::getLocalStart).thenComparing(Booking::getId)`. Nếu dữ liệu nhiều vùng và cần thứ tự thực, thay khóa local bằng Instant đã resolve.

**Bài 6 — giờ overlap.** Một khách đặt 02:30 ở Berlin trong ngày chuyển giờ mùa thu. LocalDateTime đủ xác định một Instant không?

Đáp án: không. Có thể có hai offset; phải lựa chọn chính sách hoặc hỏi khách.

**Bài 7 — ngày cuối của truy vấn.** Muốn lấy mọi event ngày 06/11 ở một chi nhánh. Có nên lọc tới 23:59:59.999 không?

Đáp án: không nên phụ thuộc precision; tạo khoảng [startOfDay(06/11), startOfDay(07/11)) theo ZoneId chi nhánh, quy đổi về Instant nếu event lưu theo Instant.

**Bài 8 — giá trị LocalDate.MAX.** API nhận end-inclusive có thể bằng LocalDate.MAX. Có được luôn gọi `end.plusDays(1)` không?

Đáp án: không. Phải kiểm biên, giữ so inclusive hoặc dùng biểu diễn không có upper bound.

## 24. Câu hỏi tự kiểm tra

**1. isBefore của hai LocalDate bằng nhau trả gì?**  
False. isAfter cũng false; dùng equals/isEqual để kiểm ngày bằng nhau.

**2. Tại sao compareTo chỉ nên kiểm dấu?**  
Vì Comparable bảo đảm âm/0/dương, không cam kết giá trị âm chính xác bằng -1.

**3. LocalTime có biết 05:00 là ngày hôm sau không?**  
Không. Cần quy tắc ca đêm hoặc thêm LocalDate.

**4. Vì sao khoảng [start,end) phù hợp cho hai slot liền kề?**  
Biên end của slot trước được loại, biên start của slot sau được lấy, không bị đếm hai lần.

**5. LocalDateTime của hai event ở hai múi giờ có so thứ tự thực được không?**  
Không đủ dữ liệu. Cần ZoneId/offset đúng rồi so Instant.

**6. Một LocalDateTime có thể ứng với hai Instant không?**  
Có ở DST overlap. Ngược lại, ở gap có thể không ứng với Instant nào.

**7. Tại sao sorting nên có tie-breaker?**  
Nếu nhiều record cùng timestamp, cần một thứ tự ổn định/tổng quát để hiển thị và phân trang.

**8. Có nên sort ngày bằng String dd/MM/yyyy?**  
Không. Hãy parse LocalDate rồi so, vì thứ tự từ vựng có thể khác lịch.

**9. Dùng LocalDateTime.MAX làm đại diện “không có ngày” có ổn không?**  
Không mặc định. Dễ tạo thứ tự giả và lỗi cộng ngoài miền; mô hình hóa absent bound rõ ràng.

**10. Khi cần biết event nào xảy ra trước, kiểu nào phù hợp hơn LocalDateTime?**  
`Instant` sau khi resolve đúng thông tin vùng/offset.

## Tài liệu chính thức

- [Java SE 8 — LocalDate](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDate.html): isBefore/isAfter/isEqual, compareTo, giới hạn miền.
- [Java SE 8 — LocalTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalTime.html): thứ tự giờ đồng hồ, nano precision.
- [Java SE 8 — LocalDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDateTime.html): thứ tự ngày giờ cục bộ, không có zone.
- [Java SE 8 — Comparator](https://docs.oracle.com/javase/8/docs/api/java/util/Comparator.html): comparing, thenComparing, nullsFirst và nullsLast.
- [Java SE 8 — Instant](https://docs.oracle.com/javase/8/docs/api/java/time/Instant.html): thứ tự thời điểm toàn cầu.
- [Java SE 8 — ZoneId](https://docs.oracle.com/javase/8/docs/api/java/time/ZoneId.html) và [ZoneRules](https://docs.oracle.com/javase/8/docs/api/java/time/zone/ZoneRules.html): gap, overlap và offset hợp lệ.
- [Java SE 8 — ZonedDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/ZonedDateTime.html): ngày giờ cùng vùng, quy tắc chuyển sang Instant.
- [Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html): parse/format, không dùng chuỗi hiển thị để thay so sánh kiểu.

**Ghi nhớ:** `LocalDate`, `LocalTime` và `LocalDateTime` có thứ tự tự nhiên **trong miền ngày/giờ cục bộ**, nhưng không tự có múi giờ hoặc thời điểm tuyệt đối. Hãy chọn rõ biên khoảng, xử lý chu kỳ qua nửa đêm, có tiebreaker cho bản ghi trùng giờ, kiểm DST và precision, và chuyển sang `Instant` khi câu hỏi thật là “sự kiện nào xảy ra trước trên dòng thời gian”.