# Clock.system, fixed và offset — java.time (Java 8+)

> **Chủ đề:** Temporal và Clock. `java.time.Clock` là abstraction cung cấp Instant hiện tại và ZoneId dùng để xác định ngày-giờ địa phương. Ba factory `Clock.system(...)`, `Clock.fixed(...)` và `Clock.offset(...)` giải quyết ba mục tiêu khác nhau: đọc đồng hồ thực, đóng băng thời điểm, dịch thời điểm bằng `Duration`. Những API này tồn tại từ Java 8 và vẫn được dùng trên các JDK hiện đại.

## 1. Mục tiêu

Sau bài này, bạn có thể phân biệt `systemUTC`, `system(ZoneId)`, `systemDefaultZone`; tạo test cố định với `fixed`; mô phỏng trước/đúng/sau hạn bằng `offset`; hiểu `Clock.withZone` khác `Clock.offset`; inject Clock vào service; và biết vì sao một ngày lịch có thể khác 24 giờ thực ở vùng DST.

## 2. Mô hình Clock: một nguồn Instant và một ZoneId

| Method | Công dụng |
| --- | --- |
| `clock.instant()` | Lấy Instant (mốc tuyệt đối trên timeline) |
| `clock.getZone()` | ZoneId dùng khi xác định ngày giờ local |
| `clock.withZone(newZone)` | Tạo clock cùng cơ chế nguồn thời gian nhưng theo zone khác |
| `clock.millis()` | Số milliseconds kể từ Unix epoch theo clock |

```java
Clock clock = Clock.systemUTC();
Instant now = clock.instant();
Instant alsoNow = Instant.now(clock);
ZoneId zone = clock.getZone();
long epochMillis = clock.millis();
```

Đối với system clock, hai lần đọc `clock.instant()` và `Instant.now(clock)` có thể chênh nhau vì thời gian đang trôi. Chỉ với clock **fixed** mới có thể assert hai lần đọc luôn bằng nhau. `Clock` không phải một bản ghi ngày-giờ để lưu trong database: lưu `Instant` cho sự kiện đã xảy ra, dùng `LocalDate` cho ngày dân sự và `ZonedDateTime` cho ngày-giờ gắn ZoneId.

## 3. So sánh ba factory

| Factory | Nguồn Instant | Zone | Clock tự trôi? |
| --- | --- | --- | --- |
| `Clock.systemUTC()` | System clock thật | UTC (ID `Z`) | Có |
| `Clock.system(zone)` | System clock thật | Zone chỉ định | Có |
| `Clock.systemDefaultZone()` | System clock thật | Default zone của máy khi tạo | Có |
| `Clock.fixed(instant,zone)` | Một Instant đã cho | Zone chỉ định | **Không** |
| `Clock.offset(base,duration)` | Instant từ base + duration | **Kế thừa zone của base** | Tùy base |

### 3.1. `Clock.systemUTC()`

```java
Clock utc = Clock.systemUTC();
Instant createdAt = Instant.now(utc);
```

Đây là cách thích hợp khi cần timestamp tuyệt đối mà không cần ngày giờ địa phương. Theo JavaDoc, nó tương đương về ý nghĩa với `Clock.system(ZoneOffset.UTC)`. Không nhầm `Instant` với `LocalDateTime`: LocalDateTime **không có offset hay zone** nên không tự là timestamp UTC.

### 3.2. `Clock.system(ZoneId zone)`

```java
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
Clock vietnam = Clock.system(hcm);
Instant eventTime = Instant.now(vietnam);
LocalDate localDate = LocalDate.now(vietnam);
ZonedDateTime localDateTime = ZonedDateTime.now(vietnam);
```

System clock vẫn báo mốc thực. Zone `Asia/Ho_Chi_Minh` chỉ ảnh hưởng cách chuyển mốc đó sang ngày và giờ địa phương. Không được nói rằng `Clock.system(hcm)` làm Instant chạy “nhanh hơn UTC 7 giờ”.

### 3.3. `Clock.systemDefaultZone()`

```java
Clock dependentOnMachine = Clock.systemDefaultZone();
ZoneId zone = dependentOnMachine.getZone();
```

Factory này phụ thuộc timezone mặc định của môi trường (máy dev, CI, container, server). JavaDoc khuyên nên tránh phụ thuộc ngầm vào default zone khi có thể; dùng `system(zone)` với zone nghiệp vụ đã được cấu hình rõ. Nó có ý nghĩa tương đương với `Clock.system(ZoneId.systemDefault())` ở lúc tạo clock.

### 3.4. Độ chính xác và tính monotonic

System clock dùng nguồn đồng hồ tốt nhất mà runtime có: độ phân giải có thể là milliseconds hoặc tốt hơn, nhưng **không cam kết nanoseconds** chỉ vì `Instant` có nano precision. Wall clock có thể được điều chỉnh bởi hệ điều hành/NTP; nó **không được đảm bảo monotonic**.

Để đo elapsed time của một đoạn code trong cùng JVM, dùng hiệu `System.nanoTime()` (không biến nó thành timestamp ngày-giờ). Với benchmark chuyên nghiệp, dùng JMH. `Clock` vẫn là abstraction đúng để đọc **wall-clock timestamp**.

## 4. `Clock.fixed(Instant, ZoneId)`

```java
Instant anchor = Instant.parse("2024-02-29T02:15:30Z");
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
Clock fixed = Clock.fixed(anchor, hcm);

Instant a = fixed.instant();
Instant b = fixed.instant();
// a.equals(b) là true, bất kể test chạy bao lâu.
```

Giá trị cố định:

```java
LocalDate d = LocalDate.now(fixed);           // 2024-02-29.
LocalTime t = LocalTime.now(fixed);           // 09:15:30.
LocalDateTime dt = LocalDateTime.now(fixed);  // 2024-02-29T09:15:30.
ZonedDateTime zdt = ZonedDateTime.now(fixed);
// 2024-02-29T09:15:30+07:00[Asia/Ho_Chi_Minh].
```

`fixed` luôn trả đúng anchor, không tự tiến khi thời gian thực trôi. Nó rất hữu ích để test ngày nhuận, nửa đêm, thời hạn thanh toán, ngày chốt sổ hoặc hết hạn token mà không cần `Thread.sleep`, đổi thời gian hệ điều hành hay mock static `now()`.

**Lưu ý:** fixed không có bộ đếm tự động tiến. Muốn kiểm tra một mốc khác, tạo clock khác, ví dụ `Clock.offset(fixed, Duration.ofMinutes(45))`; nếu cần test tiến từng bước qua nhiều event, thiết kế abstraction test có điều khiển riêng.

## 5. `Clock.offset(Clock base, Duration offset)`

Ngữ nghĩa của factory:

```text
shifted.instant() = base.instant() + offsetDuration
shifted.getZone() = base.getZone()
```

Đây là công thức minh họa, không phải source code nội bộ của Java. `Clock.offset` dịch **Instant**, giữ nguyên ZoneId.

```java
Clock base = Clock.fixed(
        Instant.parse("2024-02-29T02:15:30Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

Clock ahead = Clock.offset(base, Duration.ofHours(2));
Clock behind = Clock.offset(base, Duration.ofDays(-1));

// ahead.instant()  = 2024-02-29T04:15:30Z.
// behind.instant() = 2024-02-28T02:15:30Z.
// ZoneId cả hai vẫn là Asia/Ho_Chi_Minh.
```

Duration âm đi ngược về quá khứ. `Duration.ofDays(1)` là **24 giờ elapsed**, không phải mọi trường hợp “ngày mai cùng giờ local”. Không dùng duration quá lớn nếu có thể làm Instant vượt giới hạn hỗ trợ.

### 5.1. Offset fixed thì vẫn cố định; offset system vẫn trôi

```java
Clock frozen = Clock.fixed(
        Instant.parse("2024-02-29T02:15:30Z"), ZoneOffset.UTC);

Clock frozenPlus2 = Clock.offset(frozen, Duration.ofHours(2));
Clock realPlus2 = Clock.offset(Clock.systemUTC(),
        Duration.ofHours(2));
```

`frozenPlus2` luôn là 04:15:30Z. `realPlus2` vẫn lấy thời gian thực từ system clock và cộng hai giờ mỗi lần đọc, vì thế **không deterministic**. Trong unit test muốn exact output, chọn base là fixed.

### 5.2. Clock offset không phải ZoneOffset

- `Clock.offset(clock, Duration.ofHours(2))`: thay mốc **Instant** +2 giờ, không thay ZoneId.
- `clock.withZone(ZoneOffset.ofHours(2))`: thay **zone hiển thị** thành UTC+02:00, không thay Instant.
- `ZoneOffset.ofHours(2)`: một đối tượng múi giờ, **không phải Clock**.

Cho base là 02:15:30Z, ZoneId Việt Nam:

| Cách | Instant | Zone | LocalDateTime |
| --- | --- | --- | --- |
| Base | 02:15:30Z | Asia/Ho_Chi_Minh | 09:15:30 |
| `Clock.offset(base,+2h)` | **04:15:30Z** | Asia/Ho_Chi_Minh | **11:15:30** |
| `base.withZone(+02:00)` | **02:15:30Z** | +02:00 | **04:15:30** |

`Clock.system(ZoneOffset.ofHours(2))` cũng **không** tăng Instant hai giờ: nó chỉ chọn zone +02:00 cho system clock thật.

## 6. `withZone` và mốc qua ngày mới

```java
Instant moment = Instant.parse("2024-02-29T20:30:00Z");
Clock utc = Clock.fixed(moment, ZoneOffset.UTC);
Clock vietnam = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate a = LocalDate.now(utc);      // 2024-02-29.
LocalDate b = LocalDate.now(vietnam); // 2024-03-01.
```

`utc.instant().equals(vietnam.instant())` là true, nhưng `LocalDate.now` khác nhau. Do đó “hôm nay” phải tính theo **ZoneId nghiệp vụ**, không mặc định ngày UTC luôn bằng ngày chi nhánh. `withZone` là cách tạo góc nhìn khác cho cùng nguồn clock; với clock system, hai lần đọc liên tiếp vẫn có thể chênh do thời gian thực trôi.


## 7. Inject Clock vào service thay vì gọi `now()` trực tiếp

Cách khó kiểm thử:

```java
final class HardToTest {
    boolean expired(Instant cutoff) {
        return !Instant.now().isBefore(cutoff);
    }
}
```

Cách nên dùng: truyền Clock qua constructor, để logic vẫn đúng ở production nhưng test có thể cấp Clock.fixed.

```java
final class ExpiryService {
    private final Clock clock;

    ExpiryService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant cutoffInclusive) {
        return !Instant.now(clock).isBefore(cutoffInclusive);
    }
}
```

Đây là class snippet với các import từ `java.time`; chương trình đầy đủ ở dưới tự chứa tất cả import. Chính sách được chọn: hết hạn **khi now bằng hoặc sau cutoff**. Nếu hợp đồng yêu cầu “sau cutoff mới hết hạn”, phải đổi sang `isAfter` và test điều kiện đúng tại biên.

Production:

```java
Clock production = Clock.systemUTC();
ExpiryService service = new ExpiryService(production);
```

Test:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-29T02:15:30Z"), ZoneOffset.UTC);
Instant cutoff = Instant.parse("2024-02-29T03:00:30Z");

Clock exactlyAt = Clock.offset(fixed, Duration.ofMinutes(45));
Clock after = Clock.offset(fixed, Duration.ofHours(2));

// ExpiryService(fixed) -> false.
// ExpiryService(exactlyAt) -> true.
// ExpiryService(after) -> true.
```

**Thiết kế thêm:** Trong một phép tính cần dùng nhiều nhánh từ “now”, đọc `Instant now = clock.instant();` **một lần** và truyền snapshot đó xuống. Trên system clock, đọc lại nhiều lần có thể ở hai phía một ranh giới ngày/hạn.

## 8. DST: một ngày lịch không luôn bằng 24 giờ

Với `ZonedDateTime`, `plusDays(1)` tăng một **ngày theo lịch địa phương**. Trong zone có DST, nó không nhất thiết kéo dài 24 giờ thực. Còn `Clock.offset(base, Duration.ofHours(24))` luôn dịch Instant đúng **24 giờ**:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
Clock clock = Clock.fixed(
        Instant.parse("2024-03-30T11:00:00Z"), paris);

ZonedDateTime start = ZonedDateTime.now(clock);
// 2024-03-30T12:00+01:00[Europe/Paris].

ZonedDateTime calendarNext = start.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris].

ZonedDateTime elapsedNext = ZonedDateTime.now(
        Clock.offset(clock, Duration.ofHours(24)));
// 2024-03-31T13:00+02:00[Europe/Paris].
```

Paris nhảy DST trong ngày 31/3/2024; từ 12:00 hôm trước đến 12:00 hôm sau có **23 giờ elapsed**. Nếu yêu cầu là “ngày mai lúc 12:00 theo vùng Paris”, chọn calendar operation. Nếu yêu cầu “sau chính xác 24 giờ”, chọn Duration trên Instant (hoặc Clock.offset trong test).

`Clock` không phải scheduler: đọc clock không tự kích hoạt callback khi đến hạn. Hệ thống cần scheduler/service riêng với policy retry, múi giờ và xử lý giờ DST mơ hồ nếu thực thi tác vụ theo lịch địa phương.

## 9. `Clock.tick` và InstantSource: phân biệt phạm vi

`Clock.tick(base, duration)` hay `Clock.tickMinutes(zone)` giảm độ phân giải các instant quan sát, không dịch tương lai như `offset`, cũng không đóng băng như `fixed`. Các tick factory có từ Java 8; dùng khi muốn clock nhảy theo các bước thời gian, nhưng không dùng chúng để benchmark thời lượng chính xác.

JDK hiện đại có thêm abstraction `InstantSource` khi chỉ cần nguồn Instant mà không cần ZoneId. Để giữ ví dụ tương thích Java 8 và phục vụ cả ngày giờ local, bài này sử dụng `Clock`. Không có nhu cầu dùng API cũ mutable như `java.util.Calendar` để lấy ngày giờ hiện tại cho ứng dụng mới.

## 10. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `Clock.offset` là `ZoneOffset` | Nhầm dịch Instant với đổi múi giờ | `Clock.offset` thêm Duration; `withZone` đổi ZoneId |
| Coi `Clock.system(hcm)` nhanh hơn UTC 7 giờ | Hiểu sai timeline | Instant không mang offset địa phương |
| Dùng `systemDefaultZone` không kiểm soát | Khác kết quả giữa server và CI | Inject ZoneId nghiệp vụ |
| Mong `fixed` tự chạy theo thời gian thật | Test mãi cùng một mốc | Tạo clock khác với `offset` |
| Dùng `offset(systemClock,...)` để test exact | Nó vẫn đọc wall clock thật | Bắt đầu bằng `Clock.fixed` |
| Nhầm 1 ngày lịch với Duration 24 giờ | Sai gần DST | `plusDays` cho lịch, Duration cho elapsed |
| So sánh hai lần đọc system clock bằng `equals` | Thời gian đã trôi | Chụp một Instant snapshot |
| Dùng `LocalDateTime.now` làm UTC timestamp | LocalDateTime không có offset | `Instant.now(clock)` |
| Cho rằng `Instant` có nano thì system clock nano chính xác | Độ phân giải không được bảo đảm | Xem hợp đồng runtime |
| Dùng system wall clock đo elapsed monotonic | Clock có thể bị điều chỉnh | Hiệu `System.nanoTime()` |
| Inject Clock nhưng gọi `Instant.now()` tĩnh bên trong | Test vẫn phụ thuộc máy thật | Dùng `Instant.now(clock)` xuyên logic |
| Nghĩ Clock là scheduler | Không tự chạy tác vụ | Dùng scheduler riêng |


## 11. Chương trình Java 8 chạy được

Lưu trong file **`ClockFactoriesDemo.java`**. Chương trình kiểm tra `systemUTC/system(zone)`, fixed, offset dương/âm, withZone, điều kiện hết hạn và DST. Các output thời gian cụ thể lấy từ Clock.fixed nên tái lập được.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ClockFactoriesDemo {
    static final class ExpiryService {
        private final Clock clock;
        ExpiryService(Clock clock) { this.clock = clock; }
        boolean isExpired(Instant cutoffInclusive) {
            return !Instant.now(clock).isBefore(cutoffInclusive);
        }
    }
    public static void main(String[] args) {
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant baseInstant = Instant.parse("2024-02-29T02:15:30Z");
        Clock systemUtc = Clock.systemUTC();
        Clock systemVietnam = Clock.system(hcm);
        Clock fixed = Clock.fixed(baseInstant, hcm);
        Clock twoHoursLater = Clock.offset(fixed, Duration.ofHours(2));
        Clock oneDayEarlier = Clock.offset(fixed, Duration.ofDays(-1));
        Clock sameInstantUtc = fixed.withZone(ZoneOffset.UTC);
        Clock exactCutoff = Clock.offset(fixed, Duration.ofMinutes(45));
        Instant expiresAt = Instant.parse("2024-02-29T03:00:30Z");

        System.out.println("systemUTC zone: " + systemUtc.getZone());
        System.out.println("system(HCM) zone: " + systemVietnam.getZone());
        System.out.println("fixed instant: " + fixed.instant());
        System.out.println("fixed date: " + LocalDate.now(fixed));
        System.out.println("fixed time: " + LocalTime.now(fixed));
        System.out.println("fixed local: " + LocalDateTime.now(fixed));
        System.out.println("fixed zoned: " + ZonedDateTime.now(fixed));
        System.out.println("same instant UTC: " + ZonedDateTime.now(sameInstantUtc));
        System.out.println("offset +2h instant: " + twoHoursLater.instant());
        System.out.println("offset +2h zone: " + twoHoursLater.getZone());
        System.out.println("offset +2h local: " + LocalDateTime.now(twoHoursLater));
        System.out.println("offset -1d instant: " + oneDayEarlier.instant());
        System.out.println("before expiry: " + new ExpiryService(fixed).isExpired(expiresAt));
        System.out.println("at expiry: " + new ExpiryService(exactCutoff).isExpired(expiresAt));
        System.out.println("after expiry: " + new ExpiryService(twoHoursLater).isExpired(expiresAt));

        Clock parisFixed = Clock.fixed(
                Instant.parse("2024-03-30T11:00:00Z"),
                ZoneId.of("Europe/Paris"));
        ZonedDateTime parisStart = ZonedDateTime.now(parisFixed);
        ZonedDateTime calendarNext = parisStart.plusDays(1);
        ZonedDateTime elapsedNext = ZonedDateTime.now(
                Clock.offset(parisFixed, Duration.ofHours(24)));
        System.out.println("Paris calendar +1d: " + calendarNext);
        System.out.println("Paris clock offset +24h: " + elapsedNext);
        System.out.println("Elapsed hours for calendar day: "
                + Duration.between(parisStart, calendarNext).toHours());

        if (!systemUtc.getZone().equals(ZoneOffset.UTC)
                || !systemVietnam.getZone().equals(hcm)
                || !fixed.instant().equals(baseInstant)
                || !LocalDate.now(fixed).equals(LocalDate.of(2024, 2, 29))
                || !LocalTime.now(fixed).equals(LocalTime.of(9, 15, 30))
                || !LocalDateTime.now(fixed).equals(
                        LocalDateTime.of(2024, 2, 29, 9, 15, 30))
                || !ZonedDateTime.now(fixed).toString().equals(
                        "2024-02-29T09:15:30+07:00[Asia/Ho_Chi_Minh]")
                || !sameInstantUtc.instant().equals(fixed.instant())
                || !sameInstantUtc.getZone().equals(ZoneOffset.UTC)
                || !twoHoursLater.instant().equals(
                        Instant.parse("2024-02-29T04:15:30Z"))
                || !twoHoursLater.getZone().equals(hcm)
                || !LocalDateTime.now(twoHoursLater).equals(
                        LocalDateTime.of(2024, 2, 29, 11, 15, 30))
                || !oneDayEarlier.instant().equals(
                        Instant.parse("2024-02-28T02:15:30Z"))
                || new ExpiryService(fixed).isExpired(expiresAt)
                || !new ExpiryService(exactCutoff).isExpired(expiresAt)
                || !new ExpiryService(twoHoursLater).isExpired(expiresAt)
                || !calendarNext.toString().equals(
                        "2024-03-31T12:00+02:00[Europe/Paris]")
                || !elapsedNext.toString().equals(
                        "2024-03-31T13:00+02:00[Europe/Paris]")
                || Duration.between(parisStart, calendarNext).toHours() != 23) {
            throw new AssertionError("Clock factory example failed");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch với JDK 17+ ở chế độ Java 8 (hoặc dùng `javac` của JDK 8):

```bash
javac --release 8 ClockFactoriesDemo.java
java ClockFactoriesDemo
```

**Stdout đã kiểm thử trên OpenJDK 24:**

```text
systemUTC zone: Z
system(HCM) zone: Asia/Ho_Chi_Minh
fixed instant: 2024-02-29T02:15:30Z
fixed date: 2024-02-29
fixed time: 09:15:30
fixed local: 2024-02-29T09:15:30
fixed zoned: 2024-02-29T09:15:30+07:00[Asia/Ho_Chi_Minh]
same instant UTC: 2024-02-29T02:15:30Z
offset +2h instant: 2024-02-29T04:15:30Z
offset +2h zone: Asia/Ho_Chi_Minh
offset +2h local: 2024-02-29T11:15:30
offset -1d instant: 2024-02-28T02:15:30Z
before expiry: false
at expiry: true
after expiry: true
Paris calendar +1d: 2024-03-31T12:00+02:00[Europe/Paris]
Paris clock offset +24h: 2024-03-31T13:00+02:00[Europe/Paris]
Elapsed hours for calendar day: 23
Checks passed.
```

**Cách đọc output:** Zone của hai system clocks có thể kiểm tra mà không in thời gian thực. Tất cả Instant và local time khác đều dựa trên fixed anchor. `offset +2h` tăng Instant nhưng vẫn giữ ZoneId Việt Nam; `same instant UTC` đổi view sang UTC nhưng không đổi Instant. Ba trường hợp deadline kiểm tra đúng quy tắc inclusive. DST ở Paris cho hai giờ hiển thị khác nhau khi cộng 1 ngày lịch và cộng 24 giờ elapsed.

## 12. Bài tập và đáp án

**Bài 1.** Tạo clock system UTC và clock system cho Việt Nam.

```java
Clock utc = Clock.systemUTC();
Clock hcm = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
```

**Bài 2.** Cố định 2024-12-31T17:00Z rồi lấy ngày Việt Nam.

```java
Clock fixed = Clock.fixed(
        Instant.parse("2024-12-31T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate date = LocalDate.now(fixed); // 2025-01-01.
```

**Bài 3.** Dịch Clock.fixed về 90 phút: `Clock.offset(fixed,Duration.ofMinutes(-90))`. Zone không đổi.

**Bài 4.** Chuyển view của một fixed Clock sang UTC mà không đổi Instant: `fixed.withZone(ZoneOffset.UTC)`.

**Bài 5.** Clock.offset(Clock.systemUTC(), Duration.ofHours(2)) có fixed không? **Không**. Nó vẫn đọc system clock thật.

**Bài 6.** `Clock.system(ZoneOffset.ofHours(7))` có làm Instant chạy nhanh hơn UTC bảy giờ? **Không**. Zone chỉ ảnh hưởng local representation.

**Bài 7.** Service hết hạn đúng tại cutoff phải dùng `now.isAfter(cutoff)` hay `!now.isBefore(cutoff)`? Đáp án thứ hai, nếu policy inclusive.

**Bài 8.** Paris khi chuyển sang DST: ngày mai cùng 12:00 và sau đúng 24 giờ có luôn trùng không? **Không**; ví dụ 31/3/2024 lệch một giờ local.

**Bài 9.** Tại sao không dùng `Clock.fixed` production cho timestamp event? Vì mọi lần đọc là cùng mốc, trái yêu cầu ghi lại thời gian phát sinh thực tế.

**Bài 10.** Inject Clock vào service nhưng bên trong vẫn gọi `Instant.now()` không tham số có deterministic không? **Không**. Phải dùng `Instant.now(clock)` ở mọi nơi phụ thuộc thời gian.

## 13. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): systemUTC/systemDefaultZone/system, fixed, offset, withZone, tick và độ phân giải.
- [Oracle Java SE 26 — Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): mốc tuyệt đối và `now(Clock)`.
- [Oracle Java SE 26 — Duration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html): lượng giờ/giây thực.
- [Oracle Java SE 26 — ZoneId](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): vùng và quy tắc DST.
- [Oracle Java SE 26 — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): lịch địa phương và `plusDays`.
- [Oracle Java SE 8 — Clock](https://docs.oracle.com/javase/8/docs/api/java/time/Clock.html): API tương thích Java 8.

**Kết luận:** `system` lấy thời gian thật, `fixed` giữ nguyên Instant, `offset` dịch Instant theo Duration nhưng **không thay ZoneId**. `withZone` đổi cách xem giờ địa phương nhưng không dịch Instant. Inject Clock để tách business logic khỏi thời gian thật và dùng fixed + offset cho các bài test qua ranh giới thời gian.
