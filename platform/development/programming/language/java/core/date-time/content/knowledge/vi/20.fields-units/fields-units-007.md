# TemporalAmount và mối liên hệ với Duration, Period

## 1. Phân biệt mốc thời gian, đơn vị và lượng thời gian

`2024-08-20` là một ngày; `DAYS` là đơn vị ngày; “thêm 3 ngày” là một lượng thời gian. `TemporalAmount` biểu diễn loại thông tin thứ ba: **một lượng để cộng vào hoặc trừ khỏi một đối tượng thời gian**, chưa gắn với một mốc cụ thể.

Ví dụ, “gia hạn một tháng” và “hết hạn sau 24 giờ” đều là lượng thời gian nhưng có ý nghĩa khác nhau. Một tháng lịch phụ thuộc ngày bắt đầu, còn 24 giờ diễn tả thời lượng theo giờ. Nếu chỉ giữ một số nguyên mà bỏ ý nghĩa đơn vị và quy tắc, mã rất dễ tính sai hạn.

```text
TemporalAmount
├── Duration                 lượng theo giây và nano giây
└── ChronoPeriod
    └── Period               lượng theo năm, tháng, ngày của lịch ISO
```

`Duration` và `Period` là hai triển khai phổ biến của `TemporalAmount`. Chúng không phải `Temporal`: bản thân “2 giờ” không có năm, tháng hoặc giờ trong ngày để đọc như một mốc thời gian. [TemporalAmount](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAmount.html)

## 2. Hợp đồng TemporalAmount

| Phương thức | Ý nghĩa |
| --- | --- |
| `getUnits()` | Danh sách đơn vị biểu diễn đầy đủ lượng này |
| `get(unit)` | Giá trị của một đơn vị được triển khai hỗ trợ |
| `addTo(temporal)` | Áp dụng phép cộng vào một mốc |
| `subtractFrom(temporal)` | Áp dụng phép trừ khỏi một mốc |

`getUnits()` trả danh sách không sửa được, sắp từ đơn vị lớn đến nhỏ. Danh sách thể hiện cấu trúc của lượng, không phải danh sách những đơn vị bất kỳ mà mọi phép chuyển đổi đều dùng được.

Cách gọi thông dụng là `dateTime.plus(amount)` hoặc `dateTime.minus(amount)`. Hợp đồng của lượng định nghĩa cách thực hiện điều chỉnh; không nên thay nó bằng một vòng lặp tự cộng từng đơn vị khi chưa hiểu quy tắc triển khai.

Đoạn minh họa trong một phương thức:

```java
LocalDate start = LocalDate.of(2024, 8, 20);
TemporalAmount extension = Period.ofMonths(1);
LocalDate a = start.plus(extension);
Temporal b = extension.addTo(start);
// a và b cùng biểu diễn 2024-09-20.
```

Ở chữ ký interface, `addTo` trả `Temporal`, trong khi `LocalDate.plus` trả `LocalDate`. Dù cách gọi khác nhau, đối tượng đầu vào không bị sửa; cần giữ kết quả trả về. [Temporal.plus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/Temporal.html#plus(java.time.temporal.TemporalAmount))

## 3. Duration: lượng theo giây và nano giây

`Duration` lưu giây và phần nano giây. Các factory như `ofHours`, `ofMinutes`, `ofDays` là cách tạo tiện dụng; một ngày của `Duration.ofDays(1)` luôn bằng **24 giờ**, không mang quy tắc “cùng giờ địa phương ngày mai”.

Ví dụ `Duration.ofMinutes(90)` biểu diễn 5.400 giây. `getUnits()` của nó là `[Seconds, Nanos]`; `get(SECONDS)` đọc thành phần giây, nhưng `get(MINUTES)` không được hỗ trợ. Để lấy tổng số phút trọn vẹn, dùng `toMinutes()`.

`toHours()` là tổng số giờ trọn vẹn, còn `toHoursPart()` là phần giờ sau khi tách theo ngày 24 giờ. Cả hai đều khác với `get(HOURS)`. Tên factory tạo lượng không quyết định danh sách đơn vị nội bộ của lượng đó.

`Duration` có thể bằng không hoặc âm và là kiểu bất biến. Những phép chuyển đổi tổng như `toNanos()` có thể tràn `long` với lượng lớn; không chuyển tất cả về nano giây chỉ để tiện so sánh. `Duration` có `compareTo` vì so sánh thời lượng theo cùng mô hình giây/nano giây. [Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)

## 4. Period: lượng theo năm, tháng và ngày lịch

`Period` lưu ba thành phần năm, tháng, ngày trong lịch ISO. `Period.of(1, 2, 3)` là 1 năm, 2 tháng, 3 ngày; `getUnits()` luôn liệt kê `[Years, Months, Days]`, kể cả khi một thành phần bằng 0.

`getDays()` chỉ đọc **thành phần ngày**, không phải tổng số ngày của toàn bộ lượng. Không có tổng số ngày cố định cho “1 tháng 3 ngày” nếu chưa chọn ngày bắt đầu. `toTotalMonths()` gộp năm và tháng, không tính thành phần ngày.

`normalized()` cân lại năm và tháng: `Period.of(1, 14, 40)` thành `P2Y2M40D`. Nó không tự đổi 40 ngày thành một số tháng, vì độ dài tháng cần ngữ cảnh. `Period.ofMonths(12)` và `Period.ofYears(1)` cũng không `equals` theo cấu trúc ban đầu.

Khi cộng `Period`, phần năm/tháng được áp dụng trước phần ngày; năm và tháng có thể được gộp để điều chỉnh cùng nhau. Ở cuối tháng, phép cộng có thể chọn ngày hợp lệ cuối tháng đích. Vì vậy không được mặc định “cộng rồi trừ cùng lượng chắc chắn trở lại ngày ban đầu”. `Period` còn gắn với hệ lịch ISO; với ngày thuộc hệ lịch khác, cần hợp đồng lượng phù hợp. [Period](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html)

## 5. Cùng interface không có nghĩa thay thế nhau ở mọi nơi

| Mốc nhận | Lượng minh họa | Kết quả khả năng |
| --- | --- | --- |
| `LocalDate` | `Period.ofDays(1)` | Cộng được theo ngày lịch |
| `LocalDate` | `Duration.ofDays(1)` | Không cộng được: phép áp dụng dùng giây |
| `Instant` | `Duration.ofHours(2)` | Cộng được theo trục thời gian |
| `Instant` | `Period.ofMonths(1)` | Không hỗ trợ tháng lịch |
| `LocalTime` | `Duration.ofMinutes(30)` | Cộng được, có thể vòng qua nửa đêm |
| `LocalTime` | `Period.ofDays(1)` | Không hỗ trợ ngày lịch |
| `ZonedDateTime` | Một ngày `Period` hoặc `Duration` | Đều có thể cộng, nhưng ý nghĩa khác nhau |

Bảng áp dụng cho đúng các lượng được nêu; đừng suy thành “mọi `Period` đều thất bại trên `Instant`”. Chẳng hạn lượng chỉ có ngày có cách áp dụng khác với lượng chứa tháng. Chính đơn vị được áp dụng, hệ lịch và kiểu nhận quyết định tính tương thích.

`TemporalAmount` không cung cấp `isSupported(...)`. Có thể đọc `getUnits()` và giá trị thành phần để mô tả lượng, nhưng kiểm tra đơn vị trên mốc không thay thế hoàn toàn quy tắc của `addTo`, kiểm tra hệ lịch hoặc giới hạn kết quả. Nếu nghiệp vụ chỉ nhận thời lượng hết hạn, chữ ký nhận `Duration` thường rõ hơn nhận mọi `TemporalAmount`.

## 6. Chương trình minh chứng

Lưu thành `AmountDemo.java`. Ví dụ dùng quy tắc giờ mùa hè Berlin năm 2024 để cho thấy một ngày lịch và 24 giờ có thể dẫn đến hai mốc khác nhau.

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAmount;
import java.time.temporal.UnsupportedTemporalTypeException;

public class AmountDemo {
    public static void main(String[] args) {
        TemporalAmount clockAmount = Duration.ofMinutes(90);
        TemporalAmount calendarAmount = Period.of(1, 2, 3);

        System.out.println("durationUnits=" + clockAmount.getUnits());
        System.out.println("durationSeconds=" + clockAmount.get(ChronoUnit.SECONDS));
        System.out.println("periodUnits=" + calendarAmount.getUnits());
        System.out.println("periodMonths=" + calendarAmount.get(ChronoUnit.MONTHS));

        Duration ninetyMinutes = Duration.ofMinutes(90);
        System.out.println("totalMinutes=" + ninetyMinutes.toMinutes());
        try {
            clockAmount.get(ChronoUnit.MINUTES);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("getMinutesUnsupported");
        }

        LocalDate date = LocalDate.of(2024, 1, 31);
        Period month = Period.ofMonths(1);
        LocalDate advanced = date.plus(month);
        System.out.println("advanced=" + advanced);
        System.out.println("reverse=" + advanced.minus(month));
        System.out.println("original=" + date);
        System.out.println("normalized=" + Period.of(1, 14, 40).normalized());

        try {
            date.plus(Duration.ofDays(1));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("dateRejectsDuration");
        }

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, ZoneId.of("Europe/Berlin"));
        ZonedDateTime byCalendar = start.plus(Period.ofDays(1));
        ZonedDateTime byClock = start.plus(Duration.ofDays(1));
        System.out.println("byPeriod=" + byCalendar);
        System.out.println("byDuration=" + byClock);
        System.out.println("calendarElapsedHours="
                + Duration.between(start, byCalendar).toHours());
        System.out.println("durationElapsedHours="
                + Duration.between(start, byClock).toHours());
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac --release 17 AmountDemo.java
java AmountDemo
```

Stdout với dữ liệu múi giờ IANA tương ứng quy tắc Berlin năm 2024:

```text
durationUnits=[Seconds, Nanos]
durationSeconds=5400
periodUnits=[Years, Months, Days]
periodMonths=2
totalMinutes=90
getMinutesUnsupported
advanced=2024-02-29
reverse=2024-01-29
original=2024-01-31
normalized=P2Y2M40D
dateRejectsDuration
byPeriod=2024-03-31T12:00+02:00[Europe/Berlin]
byDuration=2024-03-31T13:00+02:00[Europe/Berlin]
calendarElapsedHours=23
durationElapsedHours=24
```

Ngày 31 tháng 1 cộng một tháng đến ngày 29 tháng 2, vì năm 2024 nhuận. Trừ một tháng từ ngày 29 tháng 2 ra ngày 29 tháng 1; thông tin “ban đầu là ngày 31” không còn được lưu trong kết quả.

Ở mốc chuyển giờ mùa hè, `Period` tiến ngày lịch và cố giữ giờ địa phương 12:00; `Duration` tiến đủ 24 giờ thực trôi nên đến 13:00. Đây là lựa chọn về ý nghĩa nghiệp vụ, không phải phép tối ưu kiểu dữ liệu.

## 7. Tạo lượng từ hai mốc

Đoạn minh họa trong một phương thức:

```java
Period calendarGap = Period.between(
        LocalDate.of(2024, 1, 15), LocalDate.of(2024, 3, 20));
// P2M5D: phân rã theo tháng và ngày lịch.

Duration elapsed = Duration.between(
        java.time.Instant.parse("2024-01-15T00:00:00Z"),
        java.time.Instant.parse("2024-01-15T01:30:00Z"));
// PT1H30M: 90 phút thời lượng.
```

`Period.between` nhận hai `LocalDate`; `Duration.between` cần các mốc tương thích với tính toán theo giây/nano giây. Hai ngày `LocalDate` đơn thuần chưa cho biết thời lượng thực trôi: cần chọn giờ và múi giờ nếu muốn biến chúng thành các thời điểm. Nếu chỉ cần số ngày lịch, dùng `ChronoUnit.DAYS.between` thay vì lấy `Period.getDays()`.

`Period` không có thứ tự độ dài độc lập với ngày bắt đầu như `Duration`: một tháng có thể ngắn hơn, bằng hoặc dài hơn 30 ngày. Nếu cần so sánh hai lượng lịch cho một nghiệp vụ, áp dụng chúng lên cùng mốc theo cùng quy tắc rồi so sánh kết quả.

## 8. Chọn đúng hợp đồng cho ứng dụng

- “Khóa mã xác thực sau 120 giây”, “đo thời gian tác vụ”, “đợi thêm 30 phút”: dùng `Duration` và mốc phù hợp như `Instant`.
- “Gia hạn hợp đồng một tháng”, “ngày kỷ niệm sau một năm”: dùng `Period` với ngày lịch và quy tắc cuối tháng rõ ràng.
- “Chạy lại cùng giờ ngày mai tại một địa điểm”: dùng quy tắc ngày lịch với múi giờ; xác định cách xử lý giờ địa phương không tồn tại hoặc trùng khi đổi giờ.
- Dùng `TemporalAmount` trong tiện ích cần nhận nhiều triển khai thật sự; ghi rõ kiểu mốc, đơn vị và hệ lịch được chấp nhận.

Không tạo một hàm chuyển mọi `TemporalAmount` thành số giây bằng cách nhân từng đơn vị với `unit.getDuration()`: thời lượng tháng/năm chỉ là ước lượng. Không tự coi `Period` là chuỗi hoặc một `Duration` dưới tên khác.

## 9. Tự thực hành

1. Vì sao `Duration.ofHours(2).get(HOURS)` không phải cách đọc tổng số giờ?
2. `Period.of(0, 1, 10).getDays()` có trả tổng số ngày không?
3. Viết hai mốc `ZonedDateTime` trước một lần chuyển giờ mùa hè, rồi so sánh cộng `Period.ofDays(1)` và `Duration.ofDays(1)`.
4. Một tham số `TemporalAmount` có bảo đảm cộng được vào mọi `Temporal` không?

Đối chiếu: (1) `get` chỉ đọc đơn vị biểu diễn được hỗ trợ, dùng `toHours`; (2) chỉ trả thành phần 10 ngày; (3) có thể khác giờ địa phương và thời lượng thực trôi; (4) không, cần hợp đồng tương thích giữa lượng và mốc nhận.