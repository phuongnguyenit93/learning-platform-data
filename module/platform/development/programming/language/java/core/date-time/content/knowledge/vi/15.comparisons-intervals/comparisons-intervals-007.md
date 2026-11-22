# Phát hiện giao nhau, tiếp giáp và khoảng rỗng

Khi so sánh hai khoảng thời gian, cần phân biệt ba quan hệ: **giao nhau** (*overlap/intersection*), **tiếp giáp** (*adjacent/touching*) và **có khoảng rỗng ở giữa** (*gap*). Hai khoảng có thể nằm sát nhau nhưng không chia sẻ thời điểm; có thể giao nhau một phần; hoặc có một khoảng thời gian chưa được bao phủ giữa chúng.

Java cung cấp các kiểu như `Instant`, `LocalDateTime`, `ZonedDateTime` và `Duration`, nhưng không có lớp khoảng tổng quát `Interval` trong `java.time`. Thông thường, hãy biểu diễn khoảng bằng **mốc bắt đầu và mốc kết thúc**, rồi định nghĩa quy tắc so sánh phù hợp với nghiệp vụ.

Bài này dùng khoảng nửa mở `[start, end)`: **bao gồm đầu, không bao gồm cuối**. Quy ước này hữu ích cho lịch đặt chỗ, ca làm, thời gian hiệu lực và các khoảng liên tiếp.

## 1. Quy ước đầu và cuối

Khoảng `[10:00, 11:00)` bao gồm mọi thời điểm từ 10:00 trở đi nhưng **không bao gồm chính 11:00**. Vì thế:

- `[10:00, 11:00)` và `[11:00, 12:00)` tiếp giáp.
- Chúng không giao nhau, vì khoảng thứ nhất không chứa 11:00 còn khoảng thứ hai bắt đầu tại 11:00.
- Ghép hai khoảng liên tiếp tạo thành `[10:00, 12:00)`, không có khoảng trống và không tính lặp điểm ranh giới.

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `[a, b)` | Bao gồm a, không bao gồm b |
| `[a, b]` | Bao gồm cả a và b |
| `(a, b)` | Không bao gồm a lẫn b |
| `max(startA, startB)` | Bắt đầu phần giao |
| `min(endA, endB)` | Kết thúc phần giao |

Với lịch tính theo phút hoặc nano giây, `[start, end)` tránh việc phải tự tìm “nano giây cuối” của một khoảng. Điều quan trọng là dùng quy ước nhất quán giữa dữ liệu, thuật toán và API.

## 2. Giao nhau, tiếp giáp và gap khác nhau ra sao?

Giả sử A = `[10:00, 11:00)`:

| Khoảng B | Quan hệ | Có phần giao dương? | Có gap? |
| --- | --- | --- | --- |
| `[10:30, 11:30)` | Giao một phần | Có, 10:30–11:00 | Không |
| `[10:00, 11:00)` | Trùng hoàn toàn | Có, toàn bộ A | Không |
| `[11:00, 12:00)` | Tiếp giáp | Không | Không |
| `[12:00, 13:00)` | Rời nhau, B ở sau | Không | Có: 11:00–12:00 |
| `[09:00, 10:00)` | Tiếp giáp ở phía trước | Không | Không |
| `[08:00, 09:00)` | Rời nhau, B ở trước | Không | Có: 09:00–10:00 |
| `[10:15, 10:45)` | B nằm trong A | Có, toàn bộ B | Không |
| `[10:00, 10:00)` | Khoảng rỗng | Không | Cần quy ước riêng |

**Gap** ở đây nghĩa là phần thời gian giữa hai khoảng rời nhau, không phải khoảng có độ dài bằng 0. Khoảng `[t, t)` là khoảng rỗng theo mô hình nửa mở: nó không bao phủ thời điểm nào.

## 3. Công thức giao nhau của khoảng nửa mở

Cho A = `[startA, endA)` và B = `[startB, endB)`. Hai khoảng giao nhau với độ dài dương khi:

```text
startA < endB && startB < endA
```

Điều kiện đầu nói A bắt đầu trước khi B kết thúc; điều kiện thứ hai nói B bắt đầu trước khi A kết thúc. Nếu thiếu một trong hai, một khoảng nằm hoàn toàn bên trái/phải khoảng kia hoặc hai khoảng chỉ tiếp giáp.

Phần giao, nếu có:

```text
intersectionStart = max(startA, startB)
intersectionEnd   = min(endA, endB)

Nếu intersectionStart < intersectionEnd:
    giao = [intersectionStart, intersectionEnd)
Ngược lại:
    không có phần giao có độ dài dương
```

Ví dụ A = `[10:00, 11:00)` và B = `[10:30, 11:30)`. Đầu giao là max(10:00, 10:30) = 10:30; cuối giao là min(11:00, 11:30) = 11:00. Phần giao có độ dài 30 phút.

Nếu `intersectionStart == intersectionEnd`, chúng không giao nhau với độ dài dương; trường hợp thường gặp là hai khoảng tiếp giáp. Không dùng `<=` thay cho `<` nếu cần phát hiện phần giao của các khoảng nửa mở.

## 4. Xác thực khoảng trước khi so sánh

Một khoảng thông thường phải thỏa `start <= end`:

- `start < end`: khoảng không rỗng.
- `start == end`: khoảng rỗng theo quy ước `[start, end)`.
- `start > end`: khoảng không hợp lệ; nên từ chối hoặc chuẩn hóa bằng một quy tắc nghiệp vụ công khai.

Đừng tự động đổi chỗ đầu và cuối cho mọi đầu vào. Nếu dữ liệu sai `[13:00, 12:00)`, đổi nó thành `[12:00, 13:00)` sẽ che giấu lỗi nguồn. Với ca làm qua nửa đêm, lưu ngày bắt đầu và ngày kết thúc thực tế; đừng giả định giờ kết thúc nhỏ hơn giờ bắt đầu luôn có nghĩa dữ liệu đúng.

Dùng `Instant` nếu hai đầu là thời điểm tuyệt đối. `LocalDateTime` chỉ chứa ngày và giờ trên đồng hồ, chưa xác định dòng thời gian nếu thiếu zone/offset. Chọn kiểu theo ý nghĩa dữ liệu trước khi so sánh.

## 5. So sánh bằng Instant

Với sự kiện đã xảy ra, thời hạn chính xác hoặc hiệu lực toàn cục, `Instant` thường phù hợp:

```java
import java.time.Instant;

Instant startA = Instant.parse("2024-01-01T10:00:00Z");
Instant endA = Instant.parse("2024-01-01T11:00:00Z");
Instant startB = Instant.parse("2024-01-01T10:30:00Z");
Instant endB = Instant.parse("2024-01-01T11:30:00Z");

boolean overlaps =
        startA.isBefore(endB) && startB.isBefore(endA);
// true
```

Đây là đoạn minh họa để đặt trong một phương thức Java. `isBefore` và `isAfter` so sánh mốc thời gian mà không cần chuyển sang chuỗi. Tránh so sánh chuỗi timestamp tùy ý: định dạng và offset khác nhau có thể làm thứ tự từ điển không phản ánh thứ tự thời gian.

`Instant` không chứa múi giờ hiển thị. Khi cần trình bày mốc ở địa phương, chuyển từng mốc sang `ZonedDateTime`; nhưng hãy dùng các `Instant` gốc để so sánh thời gian thực.

## 6. Tiếp giáp và gap

Với hai khoảng không rỗng, quan hệ tiếp giáp xuất hiện khi một đầu cuối bằng đầu đầu của khoảng kia:

```text
endA == startB || endB == startA
```

Theo quy ước nửa mở, các khoảng hợp lệ có chung ranh giới như vậy không giao nhau. Nếu A nằm trước B và `endA < startB` thì gap là:

```text
gap = [endA, startB)
gapDuration = startB - endA
```

Chỉ tạo gap với điều kiện nghiêm ngặt `endA < startB`. Nếu bằng nhau, hai khoảng tiếp giáp và gap dài 0; nếu `endA > startB`, chúng có thể giao nhau.

| A | B | Kết quả |
| --- | --- | --- |
| `[10:00, 11:00)` | `[11:00, 12:00)` | Tiếp giáp, không gap |
| `[10:00, 11:00)` | `[11:15, 12:00)` | Gap `[11:00, 11:15)`, 15 phút |
| `[10:00, 11:00)` | `[10:30, 12:00)` | Giao nhau, không gap |
| `[12:00, 13:00)` | `[10:00, 11:00)` | Gap `[11:00, 12:00)` |

Thuật toán nên xác định khoảng nào kết thúc trước để gap trả về đúng thứ tự thời gian, bất kể thứ tự đối số. Nếu hai khoảng giao hoặc tiếp giáp, không có gap dương.

## 7. Java 17+ hoàn chỉnh: overlap, intersection, touches và gap

Java không có lớp `Interval` tổng quát trong `java.time`. Ví dụ dùng một record chứa hai `Instant` và định nghĩa hành vi cho khoảng nửa mở `[start, end)`.

Lưu tệp **`IntervalRelationsDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

public class IntervalRelationsDemo {
    record Interval(Instant start, Instant end) {
        Interval {
            if (start == null || end == null) {
                throw new IllegalArgumentException("Bounds must not be null");
            }
            if (end.isBefore(start)) {
                throw new IllegalArgumentException("End must not precede start");
            }
        }

        boolean isEmpty() {
            return start.equals(end);
        }

        boolean overlaps(Interval other) {
            return !isEmpty() && !other.isEmpty()
                    && start.isBefore(other.end) && other.start.isBefore(end);
        }

        boolean touches(Interval other) {
            return !isEmpty() && !other.isEmpty() && !overlaps(other)
                    && (end.equals(other.start) || other.end.equals(start));
        }

        Optional<Interval> intersection(Interval other) {
            Instant from = start.isAfter(other.start) ? start : other.start;
            Instant to = end.isBefore(other.end) ? end : other.end;
            return from.isBefore(to)
                    ? Optional.of(new Interval(from, to))
                    : Optional.empty();
        }

        Optional<Interval> gapTo(Interval other) {
            if (isEmpty() || other.isEmpty() || overlaps(other) || touches(other)) {
                return Optional.empty();
            }
            if (end.isBefore(other.start)) {
                return Optional.of(new Interval(end, other.start));
            }
            if (other.end.isBefore(start)) {
                return Optional.of(new Interval(other.end, start));
            }
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2024-01-01T10:00:00Z");
        Interval a = new Interval(t0, t0.plusSeconds(3600));
        Interval overlap = new Interval(t0.plusSeconds(1800), t0.plusSeconds(5400));
        Interval adjacent = new Interval(t0.plusSeconds(3600), t0.plusSeconds(7200));
        Interval apart = new Interval(t0.plusSeconds(9000), t0.plusSeconds(10800));

        System.out.println("A overlaps B: " + a.overlaps(overlap));
        System.out.println("A intersection B: " + a.intersection(overlap).orElseThrow());
        System.out.println("A touches adjacent: " + a.touches(adjacent));
        System.out.println("A overlaps adjacent: " + a.overlaps(adjacent));
        System.out.println("A gap to apart: " + a.gapTo(apart).orElseThrow());

        Interval intersection = a.intersection(overlap).orElseThrow();
        System.out.println("Intersection duration: "
                + Duration.between(intersection.start(), intersection.end()).toMinutes()
                + " minutes");

        Interval empty = new Interval(t0, t0);
        System.out.println("Zero-length interval empty: " + empty.isEmpty());
        System.out.println("Zero-length interval overlaps A: " + empty.overlaps(a));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac IntervalRelationsDemo.java
java IntervalRelationsDemo
```

**stdout chính xác**, đã kiểm tra bằng Java 17:

```text
A overlaps B: true
A intersection B: Interval[start=2024-01-01T10:30:00Z, end=2024-01-01T11:00:00Z]
A touches adjacent: true
A overlaps adjacent: false
A gap to apart: Optional[Interval[start=2024-01-01T11:00:00Z, end=2024-01-01T12:30:00Z]]
Intersection duration: 30 minutes
Zero-length interval empty: true
Zero-length interval overlaps A: false
```

### Đọc kết quả và cách triển khai

- Constructor record kiểm tra hai mốc không null và từ chối trường hợp kết thúc trước bắt đầu.
- `overlaps` yêu cầu cả hai khoảng không rỗng và dùng hai phép so sánh nghiêm ngặt `isBefore`. Vì vậy chỉ tiếp xúc tại ranh giới không phải là giao.
- `intersection` chọn đầu lớn hơn và cuối nhỏ hơn; chỉ trả khoảng nếu đầu giao trước cuối giao. Không có phần giao dương thì trả `Optional.empty()`.
- `touches` phát hiện hai khoảng không rỗng có ranh giới bằng nhau nhưng không giao.
- `gapTo` chỉ trả một khoảng giữa hai khoảng rời nhau và không rỗng. Gap được trả theo trật tự thời gian, kể cả khi khoảng kia truyền vào trước.
- `Duration.between` đo độ dài phần giao; trong ví dụ, 10:30–11:00 dài 30 phút.

Vì ví dụ dùng `Instant`, quan hệ khoảng không phụ thuộc vùng hiển thị hoặc DST. Với lịch đặt chỗ theo giờ địa phương, hãy phân giải giờ bằng `ZoneId`/offset theo chính sách nghiệp vụ trước khi so sánh thời điểm thực.

## 8. Khoảng rỗng và kiểm tra một thời điểm có nằm trong khoảng

Khoảng `[t, t)` dài 0 và không chứa thời điểm nào. Nếu ứng dụng không cho phép khoảng rỗng, hãy từ chối `start == end` ngay trong constructor, thay vì cho phép rồi xử lý ở nhiều chỗ.

Với khoảng nửa mở, một thời điểm nằm trong khoảng khi:

```java
boolean contains(Instant instant) {
    return !instant.isBefore(start) && instant.isBefore(end);
}
```

Đây là thân phương thức minh họa bên trong record `Interval`. Điều kiện tương đương `start <= instant && instant < end`. Nếu đổi sang quy ước đóng cả hai đầu `[start, end]`, công thức và khái niệm tiếp giáp phải được định nghĩa lại; không thể sao chép công thức nửa mở mà không đổi các phép so sánh.

Lưu ý rằng một khoảng rỗng có thể nằm về mặt số học bên trong khoảng lớn hơn, nhưng theo quy ước nửa mở, nó vẫn không chứa thời điểm nào và không giao nhau với khoảng khác. Code ví dụ cố ý coi khoảng rỗng không overlap, touches hoặc tạo gap.

## 9. Giờ địa phương, múi giờ và DST

Nếu bài toán là “phòng họp được đặt từ 01:30 đến 03:30 tại New York”, đầu vào có thể là `LocalDateTime`, nhưng cần `ZoneId` để chuyển thành mốc trên dòng thời gian:

```java
import java.time.*;

ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime startLocal = LocalDateTime.of(2024, 3, 10, 1, 30);
LocalDateTime endLocal = LocalDateTime.of(2024, 3, 10, 3, 30);

Instant start = startLocal.atZone(newYork).toInstant();
Instant end = endLocal.atZone(newYork).toInstant();

Duration elapsed = Duration.between(start, end);
System.out.println(elapsed.toMinutes()); // 60
```

Ngày 10/03/2024, New York bắt đầu DST và bỏ qua giờ 02:00–02:59. Đồng hồ hiển thị từ 01:30 đến 03:30 là hai giờ theo mặt số, nhưng thời gian thực chỉ 60 phút. Đây là lý do **không nên trừ giờ địa phương đơn thuần** để đo thời lượng thực qua DST.

Cũng có giờ địa phương không tồn tại hoặc bị lặp khi DST chuyển đổi. Với lịch hẹn hoặc đặt chỗ, hãy quyết định gap/overlap được từ chối, tự điều chỉnh hay yêu cầu người dùng chọn. Khi từng mốc đã được phân giải thành `Instant`, công thức overlap/touch/gap phản ánh đúng quan hệ trên dòng thời gian.

## 10. Ứng dụng thực tế

### Phát hiện lịch đặt chồng

Đối với lịch đặt phòng hoặc thiết bị, hai khoảng `[startA, endA)` và `[startB, endB)` có xung đột khi:

```text
startA < endB && startB < endA
```

Đặt 10:00–11:00 và 11:00–12:00 không chồng nhau. Đặt 10:30–11:30 với khoảng 10:00–11:00 có phần giao 30 phút.

### Tìm lỗ trống giữa các lịch

Sắp xếp khoảng theo đầu bắt đầu. Giữ mốc kết thúc xa nhất trong các khoảng đã xử lý. Nếu khoảng kế tiếp bắt đầu sau mốc này, phần giữa hai mốc là gap; nếu khoảng kế tiếp bắt đầu trước mốc này, chúng giao/bao phủ nhau.

Khi gộp nhiều khoảng, cập nhật mốc kết thúc bằng `max(endSoFar, currentEnd)`. Nếu khoảng mới được lồng hoàn toàn trong khoảng đã xử lý mà bạn đặt mốc theo `currentEnd` đơn thuần, thuật toán sẽ quên phần đuôi vẫn đang được bao phủ.

### Thời gian hiệu lực của bản ghi

Có thể biểu diễn hiệu lực là `[validFrom, validTo)`. Hai phiên bản liên tiếp tiếp giáp khi `previous.validTo == next.validFrom`. Nếu hai khoảng giao nhau, có thể có hai bản ghi cùng hiệu lực; nếu có gap, không bản ghi nào bao phủ khoảng đó. Hãy định nghĩa rõ quy ước đầu/cuối trong schema hoặc hợp đồng API.

## 11. Lỗi thường gặp

1. **Dùng `<=` trong công thức overlap nửa mở.** Hai khoảng tiếp giáp bị coi nhầm là chồng nhau.
2. **Không thống nhất quy ước đầu/cuối.** `[start, end)` và `[start, end]` cho kết quả biên khác nhau.
3. **Bỏ qua khoảng rỗng.** `[t, t)` không có phần giao dương; kiểm tra riêng nếu được phép tồn tại.
4. **Coi overlap và touches là cùng một quan hệ.** Cần định nghĩa hai điều kiện riêng.
5. **Tạo gap khi khoảng còn giao nhau.** Chỉ tạo gap khi một khoảng kết thúc nghiêm ngặt trước khoảng kia bắt đầu.
6. **Cho kết thúc trước bắt đầu.** Từ chối dữ liệu sai hoặc dùng quy tắc đã công bố, không đổi đầu/cuối âm thầm.
7. **So sánh chuỗi local date-time từ các múi giờ khác nhau.** Phân giải thành `Instant` trước nếu cần quan hệ trên dòng thời gian thực.
8. **Dùng LocalDateTime để đo thời lượng thật mà thiếu zone.** DST có thể tạo giờ không tồn tại/bị lặp.
9. **Không xử lý khoảng lồng khi gộp lịch.** Giữ mốc kết thúc lớn nhất đã bao phủ.
10. **Coi tiếp giáp là một gap dương.** Bằng nhau ở biên là tiếp giáp, không có thời lượng trống.

## 12. Kiểm thử cần có

| Ca | A | B | Mong đợi |
| --- | --- | --- | --- |
| Giao một phần | `[10:00, 11:00)` | `[10:30, 11:30)` | Giao `[10:30, 11:00)` |
| B nằm trong A | `[10:00, 12:00)` | `[10:30, 11:00)` | Giao bằng B |
| Trùng hoàn toàn | `[10:00, 11:00)` | `[10:00, 11:00)` | Giao bằng cả hai |
| Tiếp giáp | `[10:00, 11:00)` | `[11:00, 12:00)` | Không giao; touches true |
| Gap dương | `[10:00, 11:00)` | `[11:15, 12:00)` | Gap `[11:00, 11:15)` |
| Thứ tự ngược | `[12:00, 13:00)` | `[10:00, 11:00)` | Gap `[11:00, 12:00)` |
| Khoảng rỗng | `[10:00, 10:00)` | `[09:00, 11:00)` | Không giao |
| Khoảng sai | `[11:00, 10:00)` | Bất kỳ | Constructor từ chối |
| DST New York | 01:30–03:30 ngày 10/03/2024 | — | Thời lượng thực 60 phút sau phân giải zone |
| Điểm biên chung | `[a,b)` | `[b,c)` | Không có thời điểm chung |

Trong JUnit, dùng `assertTrue`/`assertFalse` cho quan hệ, `assertEquals` để so phần giao/gap mong đợi, và `assertThrows` để xác nhận kết thúc trước bắt đầu bị từ chối. Kiểm thử nên bao gồm điểm biên bằng nhau, khoảng rỗng, khoảng lồng, và hai thứ tự tham số.

## 13. Chọn cách biểu diễn phù hợp

| Nhu cầu | Lựa chọn |
| --- | --- |
| Khoảng thời gian thực | Hai `Instant` |
| Đo độ dài phần giao | `Duration.between(intersection.start(), intersection.end())` |
| Giờ lịch tại địa điểm | `LocalDateTime` + `ZoneId`, phân giải DST |
| Khoảng ngày lịch | Hai `LocalDate` với quy ước đầu/cuối rõ |
| Kiểm tra overlap của khoảng nửa mở | `startA < endB && startB < endA` và khoảng không rỗng |
| Kiểm tra tiếp giáp | `endA == startB` hoặc `endB == startA` |
| Tính gap | Khoảng trước kết thúc nghiêm ngặt trước khoảng sau bắt đầu |
| Thời lượng thực | `Duration.between(startInstant, endInstant)` |

**Ghi nhớ:** Với khoảng nửa mở `[start, end)`, hai khoảng giao nhau có độ dài dương khi `startA < endB && startB < endA`. Tiếp giáp là cùng ranh giới nhưng không giao; gap chỉ tồn tại khi hai khoảng rời nhau và có khoảng cách dương. Kiểm tra khoảng hợp lệ, thống nhất quy ước đầu/cuối, và dùng `Instant` khi cần quan hệ trên dòng thời gian thực.
