# Vì sao `Duration.ofDays(1)` luôn là 24 giờ?

Trong Java, `Duration.ofDays(1)` có nghĩa là **một khoảng thời gian cố định dài 24 giờ**, tức **86.400 giây**. Phương thức này không hỏi ngày nào, múi giờ nào hay có đổi giờ mùa hè (DST) hay không. Vì vậy, một `Duration` gồm một ngày luôn được diễn giải như 24 giờ đã trôi qua.

Điều đó khác với câu nói thường ngày **“ngày mai, cùng giờ địa phương”**. Trên đồng hồ của một vùng có DST, ngày dân sự có thể dài 23 hoặc 25 giờ. Chẳng hạn tại Paris vào lúc bắt đầu DST ngày 31/03/2024, từ 12:00 ngày 30/03 tới 12:00 ngày 31/03 chỉ có **23 giờ thực**. Cộng 24 giờ từ điểm đầu sẽ đến 13:00 ngày 31/03, chứ không phải 12:00.

Vì thế cần phân biệt **thời lượng đã trôi qua** với **đơn vị theo lịch**:

- `Duration.ofDays(1)`: khoảng 24 giờ trên timeline.
- `ZonedDateTime.plusDays(1)`: ngày lịch kế tiếp theo giờ địa phương và quy tắc vùng.
- `Period.ofDays(1)`: một ngày theo lịch, thích hợp khi tính trên ngày/giờ dân sự; nó không phải thời lượng giây cố định độc lập múi giờ.

## 1. `Duration` đo thời lượng, không phải ngày dân sự

`Duration` biểu diễn một lượng thời gian theo giây và nano giây. Các đơn vị được xây dựng theo quy ước cố định:

| Phép tạo | Độ dài chính xác | `getSeconds()` |
| --- | --- | ---: |
| `Duration.ofSeconds(1)` | 1 giây | 1 |
| `Duration.ofMinutes(1)` | 60 giây | 60 |
| `Duration.ofHours(1)` | 3.600 giây | 3.600 |
| `Duration.ofDays(1)` | 24 × 3.600 giây | 86.400 |
| `Duration.ofDays(2)` | 2 × 86.400 giây | 172.800 |

`Duration.ofDays(n)` định nghĩa một ngày bằng **24 giờ**, không phải “độ dài của ngày lịch ở một vùng”. Do vậy:

~~~java
Duration oneDay = Duration.ofDays(1);

System.out.println(oneDay);                 // PT24H
System.out.println(oneDay.getSeconds());    // 86400
System.out.println(oneDay.toNanos());       // 86400000000000
~~~

Đây là đoạn minh họa đặt trong một method với `import java.time.Duration;`. Chuỗi `PT24H` là dạng biểu diễn theo ISO-8601 của một thời lượng 24 giờ; chữ `T` đánh dấu phần thời gian. Một `Duration` có thể chứa giây và phần nano giây, nên không chỉ giới hạn ở giờ nguyên.

**Điều `Duration` không biết:** nó không lưu ngày bắt đầu, ngày kết thúc, tên vùng như `Europe/Paris`, offset mùa hè/mùa đông hay ý định “cùng giờ ngày mai”. Nó chỉ lưu **độ dài của khoảng thời gian**.

## 2. Ví dụ: qua ngày bắt đầu DST tại Paris

Ngày 30/03/2024, Paris dùng offset `+01:00`. Khi sang ngày 31/03/2024, đồng hồ được chỉnh tiến để dùng `+02:00`. Bởi vậy, từ trưa ngày 30/03 đến trưa ngày 31/03, đồng hồ hiển thị cùng 12:00 nhưng chỉ có 23 giờ đã trôi qua.

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 30, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime sameClockTomorrow = start.plusDays(1);
ZonedDateTime after24Hours = start.plus(Duration.ofDays(1));

System.out.println("start = " + start);
System.out.println("plusCalendarDay = " + sameClockTomorrow);
System.out.println("plus24Hours = " + after24Hours);
System.out.println("calendarDayElapsedHours = "
        + Duration.between(
            start.toInstant(), sameClockTomorrow.toInstant()
        ).toHours());
~~~

Đoạn minh họa đặt trong method và cần import `java.time.Duration`, `java.time.ZoneId`, `java.time.ZonedDateTime`.

Kết quả:

~~~text
start = 2024-03-30T12:00+01:00[Europe/Paris]
plusCalendarDay = 2024-03-31T12:00+02:00[Europe/Paris]
plus24Hours = 2024-03-31T13:00+02:00[Europe/Paris]
calendarDayElapsedHours = 23
~~~

Cách đọc kết quả:

1. `plusDays(1)` giữ ý định theo ngày lịch: trưa hôm sau vẫn là 12:00 ở Paris.
2. Độ lệch đổi từ `+01:00` sang `+02:00`, nên khoảng giữa hai instant chỉ là 23 giờ.
3. `plus(Duration.ofDays(1))` cộng chính xác 24 giờ trên timeline; kết quả địa phương là 13:00.

Đây chính là lý do `Duration.ofDays(1)` luôn có 86.400 giây, kể cả khi một ngày trên lịch tại nơi cụ thể chỉ kéo dài 23 giờ.

## 3. Khi đồng hồ lùi: ngày địa phương có thể dài 25 giờ

Vào cuối DST, đồng hồ có thể lùi một giờ. Tại Paris, ngày **27/10/2024** chuyển từ offset `+02:00` về `+01:00`. Trong ngày này, từ trưa hôm trước tới trưa hôm sau là 25 giờ thực.

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2024, 10, 26, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

System.out.println("fallPlusDay = " + start.plusDays(1));
System.out.println("fallPlus24 = " + start.plusHours(24));
System.out.println("elapsedCalendarDay = "
        + Duration.between(
            start.toInstant(), start.plusDays(1).toInstant()
        ).toHours());
~~~

Kết quả:

~~~text
fallPlusDay = 2024-10-27T12:00+01:00[Europe/Paris]
fallPlus24 = 2024-10-27T11:00+01:00[Europe/Paris]
elapsedCalendarDay = 25
~~~

Trong tình huống này, `plusDays(1)` tạo trưa ngày hôm sau theo lịch. Vì đồng hồ lặp lại một giờ khi chuyển DST, khoảng giữa hai trưa là 25 giờ. Trong khi đó `plusHours(24)` tới 11:00 ngày 27/10 vì chỉ có 24 giờ trên timeline.

**Kết luận không phụ thuộc vùng:** `Duration.ofDays(1)` luôn là 24 giờ. Mốc giờ địa phương sau 24 giờ thì phụ thuộc zone và thời điểm bắt đầu; “ngày mai cùng giờ” không phải lúc nào cũng bằng “sau 24 giờ”.

## 4. So sánh `Duration` và `Period`

`Period` và `Duration` đều mô tả khoảng thời gian nhưng mang ý nghĩa khác nhau:

| Đặc điểm | `Duration` | `Period` |
| --- | --- | --- |
| Đơn vị chính | Giây, nano giây; API có thể tạo từ phút/giờ/ngày 24 giờ | Năm, tháng, ngày lịch |
| `ofDays(1)` nghĩa là | 86.400 giây | Một ngày lịch |
| Có biết múi giờ không? | Không | Không |
| Có tự quyết định DST không? | Không; không mang zone | Không; cũng không mang zone |
| Hay dùng với | `Instant`, timeout, thời lượng đã trôi qua | `LocalDate`, lịch và quy tắc ngày/tháng |
| Khi dùng với `ZonedDateTime` | Được cộng như lượng thời gian trên timeline | Ngày/tháng/năm được áp dụng theo lịch địa phương |

Ví dụ với ngày không có giờ:

~~~java
LocalDate date = LocalDate.of(2024, 3, 30);

System.out.println(date.plus(Period.ofDays(1)));
// 2024-03-31
~~~

Một `LocalDate` chỉ có ngày trên lịch, không có giờ hay zone. Cộng một ngày lịch tạo ra ngày kế tiếp, nhưng không có một instant nào để tính “đã trôi qua bao nhiêu giây”.

Với `ZonedDateTime`, nếu muốn giữ giờ địa phương trong ngày kế tiếp, dùng `zoned.plusDays(1)`. Đối với `ZonedDateTime`, `plusDays(1)` dùng logic ngày trên local timeline rồi giải quyết offset theo vùng. Nếu muốn thêm một lượng cố định, dùng `plus(Duration.ofDays(1))` hoặc `plusHours(24)`.

Đừng kết luận rằng `Period.ofDays(1)` và `Duration.ofDays(1)` là thay thế được cho nhau trong mọi trường hợp. `Period` thể hiện đơn vị lịch; `Duration` thể hiện lượng thời gian cố định. Ở một `LocalDateTime` không có zone, chúng có thể cho cùng trường ngày giờ khi cộng một ngày. Khác biệt trở nên thiết yếu khi phép tính gắn với timeline và `ZoneId`.

## 5. Chương trình Java 17+ đầy đủ

Tạo tệp **`DurationDayDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.LocalDate;

public class DurationDayDemo {
    public static void main(String[] args) {
        Duration oneDay = Duration.ofDays(1);
        System.out.println("duration = " + oneDay);
        System.out.println("durationSeconds = " + oneDay.getSeconds());
        System.out.println("durationNanos = " + oneDay.toNanos());

        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime springStart =
                ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);

        ZonedDateTime springCalendarDay = springStart.plusDays(1);
        ZonedDateTime springFixedDay = springStart.plus(oneDay);

        System.out.println("springStart = " + springStart);
        System.out.println("springCalendarDay = " + springCalendarDay);
        System.out.println("springFixedDay = " + springFixedDay);
        System.out.println("springElapsedHours = "
                + Duration.between(
                    springStart.toInstant(),
                    springCalendarDay.toInstant()
                ).toHours());

        ZonedDateTime fallStart =
                ZonedDateTime.of(2024, 10, 26, 12, 0, 0, 0, paris);

        ZonedDateTime fallCalendarDay = fallStart.plusDays(1);
        ZonedDateTime fallFixedDay = fallStart.plus(oneDay);

        System.out.println("fallCalendarDay = " + fallCalendarDay);
        System.out.println("fallFixedDay = " + fallFixedDay);
        System.out.println("fallElapsedHours = "
                + Duration.between(
                    fallStart.toInstant(),
                    fallCalendarDay.toInstant()
                ).toHours());

        LocalDate calendarDate = LocalDate.of(2024, 3, 30);
        System.out.println("periodDay = "
                + calendarDate.plus(Period.ofDays(1)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DurationDayDemo.java
java DurationDayDemo
~~~

Kết quả:

~~~text
duration = PT24H
durationSeconds = 86400
durationNanos = 86400000000000
springStart = 2024-03-30T12:00+01:00[Europe/Paris]
springCalendarDay = 2024-03-31T12:00+02:00[Europe/Paris]
springFixedDay = 2024-03-31T13:00+02:00[Europe/Paris]
springElapsedHours = 23
fallCalendarDay = 2024-10-27T12:00+01:00[Europe/Paris]
fallFixedDay = 2024-10-27T11:00+01:00[Europe/Paris]
fallElapsedHours = 25
periodDay = 2024-03-31
~~~

Các giá trị đã được đối chiếu bằng Java với ID vùng `Europe/Paris` và quy tắc DST của năm 2024. Phần `Duration` luôn trả về `PT24H`, 86.400 giây và 86.400.000.000.000 nano giây. Dữ liệu múi giờ dùng để diễn giải Paris được cung cấp bởi tzdb trong runtime Java; quy tắc lịch sử của ví dụ là các quy tắc vùng tương ứng cho năm 2024.

## 6. Khi nào nên dùng `Duration.ofDays(1)`?

Dùng `Duration.ofDays(1)` khi ý định nghiệp vụ là **đúng 24 giờ đã trôi qua**:

- Timeout: một tác vụ cần hết hạn sau 24 giờ.
- Thời lượng giám sát: đo khoảng cách giữa hai timestamp.
- Tính toán trên `Instant`: `instant.plus(Duration.ofDays(1))` tiến đúng 86.400 giây trên timeline.
- Khoảng cách giữa hai thời điểm: `Duration.between(start.toInstant(), end.toInstant())`.

Ví dụ timeout:

~~~java
Instant startedAt = Instant.parse("2026-01-15T00:00:00Z");
Instant deadline = startedAt.plus(Duration.ofDays(1));
// 2026-01-16T00:00:00Z — thêm đúng 24 giờ.
~~~

Đoạn minh họa này không chứa zone, vì timeout là thời lượng tuyệt đối. Nếu muốn hiển thị hạn theo vùng, chuyển kết quả sau đó bằng `deadline.atZone(zone)`.

**Đừng dùng `Duration.ofDays(1)` chỉ vì giao diện ghi “đến hết ngày mai”** mà không xác định vùng và quy tắc biên. Hết ngày địa phương thường là đầu ngày lịch kế tiếp của một `ZoneId`, không phải luôn luôn cộng 86.400 giây từ thời điểm bất kỳ.

## 7. Khi nào nên dùng phép tính ngày lịch?

Nếu yêu cầu là **“ngày mai cùng giờ tại Paris”**, hãy tính theo lịch địa phương:

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime meeting =
        ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);

ZonedDateTime tomorrowSameClock = meeting.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris]
~~~

Nếu yêu cầu là “sau 24 giờ”, hãy dùng:

~~~java
ZonedDateTime exactly24HoursLater =
        meeting.plus(Duration.ofHours(24));
// 2024-03-31T13:00+02:00[Europe/Paris]
~~~

Hai câu lệnh có cùng loại đối tượng kết quả `ZonedDateTime`, nhưng **ngữ nghĩa phép tính khác nhau**. Phần ngày/giờ theo đồng hồ có thể khác nhau; độ dài thực giữa các thời điểm cũng phụ thuộc DST.

Lịch hẹn lặp hằng ngày cần đặc biệt tường minh: “mỗi ngày lúc 09:00 địa phương” nên tính **ngày local kế tiếp + giờ hẹn + `ZoneId`**, sau đó xử lý gap/overlap theo quy tắc đã chọn. Không đơn giản lặp `instant.plus(Duration.ofDays(1))` nếu muốn giờ dân sự luôn là 09:00 tại vùng đổi DST.

## 8. Một ngày địa phương để lọc dữ liệu không phải 24 giờ

Giả sử hệ thống muốn lấy các giao dịch của ngày **31/03/2024 tại Paris**. Cách đúng là xác định hai biên của ngày trong vùng đó:

~~~java
LocalDate date = LocalDate.of(2024, 3, 31);
ZoneId paris = ZoneId.of("Europe/Paris");

Instant startInclusive = date.atStartOfDay(paris).toInstant();
Instant endExclusive =
        date.plusDays(1).atStartOfDay(paris).toInstant();

Duration dayLength = Duration.between(startInclusive, endExclusive);
System.out.println(dayLength.toHours()); // 23
~~~

Đoạn minh họa đặt trong method với `LocalDate`, `ZoneId`, `Instant`, `Duration`.

Khoảng thời gian để truy vấn timestamp nên được định nghĩa **nửa mở**: `[startInclusive, endExclusive)`. Khi đó mọi sự kiện có instant từ đầu ngày (bao gồm) đến đầu ngày kế tiếp (không bao gồm) thuộc ngày nghiệp vụ; hai ngày liên tiếp không chồng lấn ở biên.

Không dùng `endExclusive = startInclusive.plus(Duration.ofDays(1))` ở nơi cần đầu ngày kế tiếp theo local timeline. Với ngày đổi DST, phép cộng đó có thể đi tới sai giờ địa phương. Hãy tính `date.plusDays(1).atStartOfDay(zone)` để xác định biên lịch.

## 9. Sai lầm thường gặp

| Sai lầm | Tại sao sai? | Cách làm đúng |
| --- | --- | --- |
| Nghĩ một ngày lịch luôn dài 24 giờ thực | DST có thể làm ngày dài 23 hoặc 25 giờ | Chọn zone và tính hai đầu ngày lịch |
| Dùng `Duration.ofDays(1)` cho mọi lịch hẹn hằng ngày | Giờ địa phương có thể trôi khi DST | Tính theo ngày local với `ZoneId` |
| Nghĩ `Period.ofDays(1)` cũng là 86.400 giây | `Period` là đơn vị lịch | Dùng `Duration` khi cần lượng thời gian cố định |
| Nghĩ `Duration` chứa múi giờ | `Duration` chỉ chứa độ dài | Giữ zone riêng nếu cần hiển thị địa phương |
| Cộng 24 giờ rồi gọi đó là “đầu ngày kế tiếp” | Không đảm bảo đúng biên ngày địa phương | Tính ngày kế tiếp rồi dùng `atStartOfDay(zone)` |
| Coi giờ hệ thống là zone nghiệp vụ | Kết quả phụ thuộc máy deploy | Truyền rõ `ZoneId` |
| Nghĩ `Duration.toDays()` làm tròn lên | Phương thức trả số ngày hoàn chỉnh, phần dư bỏ qua | Dùng đơn vị đúng với câu hỏi nghiệp vụ |

Một ví dụ về `toDays()`:

~~~java
System.out.println(Duration.ofHours(47).toDays()); // 1
~~~

Kết quả là **1**, vì 47 giờ có một khoảng 24 giờ hoàn chỉnh và còn dư 23 giờ. Phương thức không làm tròn thành hai ngày. Nếu cần số giây, giờ hoặc phút đã trôi qua, dùng `getSeconds()`, `toHours()` hay `toMinutes()` phù hợp với loại phép tính.

## 10. Checklist chọn đúng đơn vị

1. Câu hỏi nói **“sau đúng 24 giờ”** hay **“cùng giờ ngày mai”**?
2. Dữ liệu đã là `Instant` hay còn là local date-time?
3. Nếu có địa điểm, đã chọn đúng `ZoneId` chứ chưa dùng offset cố định một cách vô tình?
4. Ngày bắt đầu/kết thúc có nằm quanh chuyển DST không?
5. Nếu lọc ngày địa phương, đã tính đầu ngày và đầu ngày sau bằng zone thay vì cộng 24 giờ chưa?
6. Nếu lịch lặp, chính sách gap/overlap đã rõ chưa?
7. Test đã bao gồm cả ngày xuân DST gap và ngày thu DST overlap chưa?

### Tự kiểm tra

- `Duration.ofDays(1).getSeconds()` bằng bao nhiêu? **86.400**.
- Tại sao Paris ngày 31/03/2024 từ 12:00 hôm trước đến 12:00 hôm sau chỉ 23 giờ? **Vì đồng hồ tiến từ UTC+01:00 lên UTC+02:00**.
- Nếu thêm 24 giờ vào 12:00 ngày 30/03/2024 tại Paris, kết quả địa phương là gì? **13:00 ngày 31/03/2024**.
- Paris ngày 27/10/2024 từ trưa hôm trước tới trưa hôm sau kéo dài bao lâu? **25 giờ** do đồng hồ lùi một giờ.
- Lấy giao dịch của ngày địa phương có nên dùng “đầu ngày + 24 giờ” không? **Không**, tính đầu ngày kế tiếp theo `ZoneId`.
- Khi nào nên dùng `Period.ofDays(1)`? **Khi muốn biểu đạt một ngày lịch**, không phải lượng giây cố định.

**Ghi nhớ:** `Duration.ofDays(1)` luôn biểu diễn 24 giờ, không phụ thuộc lịch địa phương. DST không thay đổi định nghĩa của `Duration`; nó làm thay đổi quan hệ giữa **thời lượng đã trôi qua** và **giờ đồng hồ ở một vùng**. Dùng `Duration` cho timeout/thời lượng tuyệt đối; dùng phép tính ngày lịch với `LocalDate`/`ZonedDateTime` và `ZoneId` cho lịch hẹn, ngày hiệu lực, hoặc truy vấn theo ngày địa phương.