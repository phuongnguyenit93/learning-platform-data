# Kiểm thử ranh giới chuyển giờ và thay đổi quy tắc múi giờ trong Java

## 1. Mục tiêu bài học

Một lỗi thời gian khó phát hiện thường không nằm ở câu lệnh cộng phút, mà ở giả định rằng **mỗi giờ địa phương chỉ xuất hiện đúng một lần** và **các quy tắc múi giờ sẽ mãi không đổi**. Ở một số múi giờ, đồng hồ chuyển tiến làm một khoảng giờ địa phương **không tồn tại** (*gap*); chuyển lùi làm một khoảng giờ địa phương **xảy ra hai lần** (*overlap*). Quy định về múi giờ và daylight saving time (DST) còn có thể được chính quyền thay đổi, sau đó được cập nhật trong cơ sở dữ liệu IANA TZDB và bản JDK mới.

Với Java hiện hành, ta có thể kiểm thử chính xác các tình huống này bằng `java.time`, đặc biệt là `ZoneId`, `ZoneRules`, `ZoneOffsetTransition`, `LocalDateTime`, `ZonedDateTime`, `Instant` và `Clock`.

Sau bài này, bạn có thể:

- Phân biệt **instant trên timeline** với **ngày giờ địa phương** và **UTC offset**.
- Xác định một giờ địa phương có **0, 1 hay 2 offset hợp lệ** bằng `ZoneRules.getValidOffsets`.
- Xử lý giờ không tồn tại bằng chính sách **từ chối** hoặc **điều chỉnh** có chủ đích; kiểm tra hành vi mặc định của `LocalDateTime.atZone`.
- Giải quyết giờ bị lặp bằng offset **earlier/later** hoặc yêu cầu người dùng chọn rõ ràng.
- Viết test cho **trước, đúng tại, sau** instant chuyển đổi (kể cả sát ranh giới nanosecond).
- So sánh cộng theo lịch `plusDays(1)` với cộng thời lượng `plusHours(24)` qua ngày đổi giờ.
- Kiểm thử thay đổi quy tắc múi giờ bằng **ZoneRules mô phỏng**, độc lập phiên bản TZDB cài trên máy.
- Kiểm thử code đọc thời gian hiện tại qua `Clock.fixed` thay vì `Thread.sleep` hoặc phụ thuộc hệ điều hành.
- Thiết kế regression test và quy trình cập nhật TZDB/JDK mà không “đóng đinh” quy tắc tương lai đã có thể thay đổi.

Các API chính được giới thiệu từ Java 8 và **vẫn còn được hỗ trợ**. Các chương trình độc lập trong bài dùng **Java 17+** (có `List.of` từ Java 9); chỉ dùng các ví dụ mà thời điểm và đầu ra có thể xác minh. Các tình huống lịch sử ở `Europe/Paris` năm 2024 và `Pacific/Apia` năm 2011 dùng để minh họa, **không phải** dự báo rằng chính sách tương lai của những vùng này sẽ luôn như vậy.

## 2. Chỉ một instant, nhưng có thể hai cách đọc “giờ địa phương”

Một `Instant` xác định một điểm duy nhất trên timeline UTC. Khi đưa Instant vào `ZoneId`, Java áp dụng quy tắc của vùng tại instant đó để tính ngày, giờ và offset. Hướng **Instant → ZonedDateTime** không mơ hồ đối với một bộ quy tắc đã biết.

Chiều ngược lại **LocalDateTime + ZoneId → Instant** có thể mơ hồ, bởi vì `LocalDateTime` không chứa offset:

| Tình huống | Số offset hợp lệ | Ví dụ giờ địa phương | Nghĩa nghiệp vụ |
| --- | ---: | --- | --- |
| **Normal** | 1 | Paris `2024-05-01T12:00` | Có đúng một cách quy về UTC |
| **Gap** | 0 | Paris `2024-03-31T02:30` | Giờ này không tồn tại trong quy tắc vùng |
| **Overlap** | 2 | Paris `2024-10-27T02:30` | Giờ này xảy ra hai lần, ở hai instant khác nhau |

Tại Paris theo quy tắc áp dụng năm 2024:

```text
Chuyển tiến — 31/03/2024:
01:59:59.999...+01:00 → 03:00:00+02:00
Không có 02:00 đến 02:59:59.999... theo giờ địa phương.

Chuyển lùi — 27/10/2024:
02:59:59.999...+02:00 → 02:00:00+01:00
Khoảng 02:00–02:59 xuất hiện lần thứ nhất (+02:00)
và lần thứ hai (+01:00).
```

Điều này không có nghĩa thời gian UTC bị đứt hoặc chạy lùi. **Timeline của Instant vẫn liên tục**. Chính cách ánh xạ sang đồng hồ địa phương có bước nhảy hoặc phần bị lặp.

**Không nhầm `ZoneOffset.ofHours(1)` với `ZoneId.of("Europe/Paris")`.** Offset chỉ là một độ dịch cố định, còn region zone dùng tập quy tắc theo ngày. Nếu chỉ kiểm thử một offset cố định, bạn đã bỏ qua đúng vấn đề cần kiểm thử: thay đổi độ dịch theo thời gian.

## 3. Bộ API cần nắm

| API | Công dụng |
| --- | --- |
| `ZoneId.of("Europe/Paris")` | Chọn múi giờ vùng, lấy quy tắc bằng `getRules()` |
| `ZoneRules.getValidOffsets(LocalDateTime)` | Trả 0/1/2 offset hợp lệ cho một giờ địa phương |
| `ZoneRules.getTransition(LocalDateTime)` | Trả chuyển đổi liên quan đến local time trong gap/overlap; ngoài trường hợp đó thường là `null` |
| `ZoneRules.isValidOffset(LocalDateTime, ZoneOffset)` | Kiểm tra offset được chọn có thực sự hợp lệ |
| `ZoneRules.nextTransition(Instant)` | Chuyển đổi kế tiếp **sau** instant được đưa vào |
| `ZoneRules.previousTransition(Instant)` | Chuyển đổi gần nhất **trước** instant được đưa vào |
| `ZoneOffsetTransition.isGap()/isOverlap()` | Phân loại kiểu chuyển đổi |
| `ZoneOffsetTransition.getInstant()` | Instant UTC nơi chuyển đổi có hiệu lực |
| `ZoneOffsetTransition.getOffsetBefore()/getOffsetAfter()` | Offset ở hai phía |
| `ZoneOffsetTransition.getDuration()` | Thời lượng biến thiên theo đồng hồ địa phương (có thể dương/âm) |
| `LocalDateTime.atZone(zone)` | Dựng `ZonedDateTime` với chính sách resolve mặc định |
| `ZonedDateTime.ofStrict(local, offset, zone)` | **Kiểm tra chặt** local + offset theo quy tắc vùng, sai thì ném exception |
| `ZonedDateTime.ofLocal(local, zone, preferredOffset)` | Giữ offset ưu tiên nếu hợp lệ; nếu không, áp dụng chính sách mặc định |
| `withEarlierOffsetAtOverlap()/withLaterOffsetAtOverlap()` | Chọn lần xuất hiện thứ nhất/thứ hai của giờ bị lặp |
| `Clock.fixed(instant, zone)` | Mô phỏng “bây giờ” tại một instant cụ thể, giúp unit test xác định |

`ZoneRules.getOffset(LocalDateTime)` là phương thức tiện dụng nhưng **không phải bộ kiểm tra tính hợp lệ**. Trong gap hoặc overlap, nó trả một offset “phù hợp nhất” (thông thường offset trước chuyển đổi), không đủ để biết liệu thời điểm có tồn tại hoặc có mơ hồ hay không. Khi tính đúng đắn quan trọng, hãy dùng `getValidOffsets` và `getTransition`.

## 4. Viết bài kiểm tra đầu tiên: 0, 1 hoặc 2 offset

Lưu thành `DstBoundaryClassificationDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstBoundaryClassificationDemo {
    private static void show(ZoneRules rules,
                             String label,
                             String localText) {
        LocalDateTime local = LocalDateTime.parse(localText);
        List<java.time.ZoneOffset> valid =
                rules.getValidOffsets(local);
        System.out.println(label + " = " + valid.size()
                + " " + valid);
    }

    public static void main(String[] args) {
        ZoneRules paris =
                ZoneId.of("Europe/Paris").getRules();

        show(paris, "beforeGap", "2024-03-31T01:59");
        show(paris, "inGap", "2024-03-31T02:30");
        show(paris, "afterGap", "2024-03-31T03:00");
        show(paris, "normal", "2024-05-01T12:00");
        show(paris, "inOverlap", "2024-10-27T02:30");
        show(paris, "afterOverlap", "2024-10-27T03:00");
    }
}
```

Biên dịch và chạy:

```bash
javac DstBoundaryClassificationDemo.java
java DstBoundaryClassificationDemo
```

Stdout theo dữ liệu lịch sử Paris áp dụng năm 2024:

```text
beforeGap = 1 [+01:00]
inGap = 0 []
afterGap = 1 [+02:00]
normal = 1 [+02:00]
inOverlap = 2 [+02:00, +01:00]
afterOverlap = 1 [+01:00]
```

Giải thích:

1. Trong mùa xuân, `02:30` **không tồn tại** ở Paris, vì vậy danh sách offset rỗng.
2. Sau khi chuyển tiến, `03:00` đã mang offset `+02:00`.
3. Trong mùa thu, `02:30` có **hai offset hợp lệ**. `+02:00` là lần xuất hiện trước khi chuyển lùi, `+01:00` là lần sau.
4. Sau `03:00` ngày chuyển lùi, chỉ còn `+01:00`.

**Bộ test tối thiểu** cho một transition không chỉ có “ngày trước/ngày sau”; cần kiểm tra điểm ngay trước, ngay sau, **nằm trong gap/overlap** và một ngày bình thường. Với vùng không đổi offset trong năm, các tình huống này có thể không tồn tại; đừng tự giả định mọi `ZoneId` đều có DST.

## 5. Gap: Java giải quyết giờ không tồn tại như thế nào?

Với `LocalDateTime.parse("2024-03-31T02:30")` và `Europe/Paris`, Java không thể xác định một instant dùng local time nguyên trạng, bởi vì giờ `02:30` không xảy ra trong vùng này.

Hành vi mặc định của `local.atZone(zone)` là **đẩy local time tiến theo độ dài gap**. Ở ví dụ này, `02:30` trở thành `03:30+02:00`. Chính sách này tiện với một số tác vụ hiển thị, nhưng có thể **không** đúng nghiệp vụ: chẳng hạn lệnh chuyển khoản phải đúng giờ, lịch khám bệnh hoặc quy tắc cutoff giờ địa phương có thể cần **từ chối** input.

Muốn từ chối thay vì tự điều chỉnh, kiểm tra `getValidOffsets(local).isEmpty()` hoặc dùng `ZonedDateTime.ofStrict(...)` với offset do người dùng cung cấp.

Lưu `DstGapPolicyDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;

public class DstGapPolicyDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneRules rules = paris.getRules();
        LocalDateTime local =
                LocalDateTime.of(2024, 3, 31, 2, 30);

        ZoneOffsetTransition transition =
                rules.getTransition(local);

        System.out.println("valid = " +
                rules.getValidOffsets(local));
        System.out.println("gap = " + transition.isGap());
        System.out.println("from = " +
                transition.getDateTimeBefore());
        System.out.println("to = " +
                transition.getDateTimeAfter());
        System.out.println("duration = " +
                transition.getDuration());

        ZonedDateTime adjusted = local.atZone(paris);
        System.out.println("adjusted = " + adjusted);

        try {
            ZonedDateTime.ofStrict(
                    local, ZoneOffset.ofHours(1), paris);
            System.out.println("unexpected");
        } catch (DateTimeException ex) {
            System.out.println("strict rejected gap");
        }
    }
}
```

```bash
javac DstGapPolicyDemo.java
java DstGapPolicyDemo
```

```text
valid = []
gap = true
from = 2024-03-31T02:00
to = 2024-03-31T03:00
duration = PT1H
adjusted = 2024-03-31T03:30+02:00[Europe/Paris]
strict rejected gap
```

Chính sách lựa chọn:

- **Reject:** đầu vào một giờ local không tồn tại phải bị từ chối và yêu cầu người dùng chọn thời gian hợp lệ.
- **Shift forward:** nếu nghiệp vụ cho phép, tiến theo độ dài gap. Thể hiện chính sách này minh bạch, tránh “sửa giờ” âm thầm trong sổ sách nhạy cảm.
- **Anchor to next valid instant:** có bài toán cần chạy ngay tại thời điểm chuyển tiếp thay vì cùng số phút sau gap; đây là **một chính sách khác** so với `atZone` và cần mã riêng dùng `ZoneOffsetTransition.getInstant()`.
- **Use Instant:** nếu sự kiện đã được xác định bằng UTC timestamp, đừng convert qua LocalDateTime rồi tự giải ambiguity; `instant.atZone(zone)` không có vấn đề gap ở chiều hiển thị.

**Không lấy `rules.getOffset(local)` rồi cho rằng local đã hợp lệ.** Trong gap, phương thức này có thể trả offset trước chuyển đổi, dù không có instant nào tương ứng với local time đó dưới quy tắc vùng.

## 6. Overlap: giờ bị lặp phải có chính sách chọn lần nào

Trong overlap, `LocalDateTime.of(2024,10,27,2,30)` ở Paris có thể gắn:

- `+02:00`: lần xảy ra sớm hơn trên timeline.
- `+01:00`: lần xảy ra muộn hơn trên timeline, **cách lần đầu 60 phút thực**.

`local.atZone(zone)` thường chọn offset sớm hơn (`+02:00` trong ví dụ). Bạn có thể chọn lại bằng `withEarlierOffsetAtOverlap()` hoặc `withLaterOffsetAtOverlap()`, hoặc dùng `ZonedDateTime.ofStrict(local, preferredOffset, zone)` để xác nhận chính offset mà người dùng đã chọn.

Lưu `DstOverlapPolicyDemo.java`:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class DstOverlapPolicyDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime local =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        ZonedDateTime defaultChoice = local.atZone(paris);
        ZonedDateTime earlier =
                defaultChoice.withEarlierOffsetAtOverlap();
        ZonedDateTime later =
                defaultChoice.withLaterOffsetAtOverlap();

        System.out.println("default = " + defaultChoice);
        System.out.println("earlier = " + earlier);
        System.out.println("later = " + later);
        System.out.println("earlierUTC = " +
                earlier.toInstant());
        System.out.println("laterUTC = " +
                later.toInstant());
        System.out.println("elapsedMinutes = " +
                Duration.between(
                        earlier.toInstant(),
                        later.toInstant()).toMinutes());
        System.out.println("sameLocal = " +
                earlier.toLocalDateTime().equals(
                        later.toLocalDateTime()));
        System.out.println("strictLater = " +
                ZonedDateTime.ofStrict(
                        local, ZoneOffset.ofHours(1), paris));
    }
}
```

```bash
javac DstOverlapPolicyDemo.java
java DstOverlapPolicyDemo
```

```text
default = 2024-10-27T02:30+02:00[Europe/Paris]
earlier = 2024-10-27T02:30+02:00[Europe/Paris]
later = 2024-10-27T02:30+01:00[Europe/Paris]
earlierUTC = 2024-10-27T00:30:00Z
laterUTC = 2024-10-27T01:30:00Z
elapsedMinutes = 60
sameLocal = true
strictLater = 2024-10-27T02:30+01:00[Europe/Paris]
```

**Chính sách nghiệp vụ cần ghi rõ:** đặt lịch lúc `02:30` trong overlap là lần trước hay lần sau? Với giao dịch tài chính, lịch thực thi hoặc log sự kiện, nên lưu **`Instant` hoặc `OffsetDateTime` với offset đã chọn** để không phải đoán lại. Nếu người dùng không cung cấp offset và nghiệp vụ không có default hợp lệ, **yêu cầu lựa chọn** rõ ràng tốt hơn tự chọn im lặng.

## 7. Ranh giới ở cấp instant: trước, đúng tại và sau chuyển đổi

Khi viết test chính xác, thay vì dựa trên `LocalDateTime` mơ hồ, hãy chọn **instant UTC** nơi chuyển đổi bắt đầu có hiệu lực. Trong dữ liệu Paris 2024:

- Bắt đầu chuyển tiến: `2024-03-31T01:00:00Z`.
- Bắt đầu chuyển lùi: `2024-10-27T01:00:00Z`.

`ZoneRules.nextTransition(instant)` và `previousTransition(instant)` giúp tìm ra instant tương ứng cho dữ liệu vùng mà hệ thống thực dùng. Cẩn thận từ **“sau”** và **“trước”**: các method này không có nghĩa bao gồm chính instant truyền vào.

Lưu `TransitionInstantDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

public class TransitionInstantDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneRules rules = paris.getRules();

        Instant spring =
                Instant.parse("2024-03-31T01:00:00Z");
        Instant autumn =
                Instant.parse("2024-10-27T01:00:00Z");

        System.out.println("springBefore = " +
                spring.minusNanos(1).atZone(paris));
        System.out.println("springAt = " +
                spring.atZone(paris));
        System.out.println("springAfter = " +
                spring.plusNanos(1).atZone(paris));

        System.out.println("autumnBefore = " +
                autumn.minusNanos(1).atZone(paris));
        System.out.println("autumnAt = " +
                autumn.atZone(paris));

        System.out.println("next = " +
                rules.nextTransition(
                        Instant.parse("2024-03-30T00:00:00Z"))
                        .getInstant());
        System.out.println("previous = " +
                rules.previousTransition(
                        Instant.parse("2024-11-01T00:00:00Z"))
                        .getInstant());
    }
}
```

```bash
javac TransitionInstantDemo.java
java TransitionInstantDemo
```

```text
springBefore = 2024-03-31T01:59:59.999999999+01:00[Europe/Paris]
springAt = 2024-03-31T03:00+02:00[Europe/Paris]
springAfter = 2024-03-31T03:00:00.000000001+02:00[Europe/Paris]
autumnBefore = 2024-10-27T02:59:59.999999999+02:00[Europe/Paris]
autumnAt = 2024-10-27T02:00+01:00[Europe/Paris]
next = 2024-03-31T01:00:00Z
previous = 2024-10-27T01:00:00Z
```

**Tại ranh giới chuyển đổi,** chính instant transition đã thuộc offset **sau**. Các thời điểm trước transition dù chỉ 1 ns vẫn theo offset **trước**. Việc biểu diễn timestamp tại cấp nanosecond không chứng minh đồng hồ thực có độ phân giải 1 ns; ở đây tất cả instant được **dựng cố định** nên test phản ánh quy tắc của thư viện chính xác.

Một `ZoneId` cố định có thể không có lần chuyển đổi tiếp theo. `nextTransition`/`previousTransition` được phép trả `null` khi không tìm thấy, do đó trong code tổng quát không được gọi thẳng `getInstant()` nếu chưa xác nhận kết quả khác null.

## 8. Cộng theo lịch khác cộng thời lượng khi có DST

Một lỗi kinh điển là đồng nhất “một ngày lịch địa phương” với “đúng 24 giờ đã trôi qua”. Trong ngày chuyển tiến ở Paris 2024, khoảng từ **12:00 ngày 30/03** đến **12:00 ngày 31/03** chỉ là **23 giờ thực**; ngày chuyển lùi, khoảng cùng giờ qua một ngày có **25 giờ thực**.

- `zoned.plusDays(1)`: cộng **một ngày trên local timeline**, sau đó giải theo quy tắc vùng.
- `zoned.plusHours(24)`: cộng **24 giờ thực trên instant timeline**, có thể cho local time khác giờ ban đầu.
- `Duration.ofDays(1)` biểu thị thời lượng đúng 24 giờ, không phải mọi “ngày trên lịch”.
- `Period.ofDays(1)` dùng đơn vị lịch, thích hợp với quy tắc cộng ngày theo lịch địa phương.

Lưu `DstArithmeticDemo.java`:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstArithmeticDemo {
    private static void show(String label,
                             ZonedDateTime start) {
        ZonedDateTime calendar = start.plusDays(1);
        ZonedDateTime elapsed = start.plusHours(24);

        System.out.println(label + " calendar = " + calendar);
        System.out.println(label + " elapsed = " + elapsed);
        System.out.println(label + " calendarHours = " +
                Duration.between(
                        start.toInstant(),
                        calendar.toInstant()).toHours());
        System.out.println(label + " elapsedHours = " +
                Duration.between(
                        start.toInstant(),
                        elapsed.toInstant()).toHours());
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        show("spring", LocalDateTime.of(
                2024, 3, 30, 12, 0).atZone(paris));
        show("autumn", LocalDateTime.of(
                2024, 10, 26, 12, 0).atZone(paris));
    }
}
```

```bash
javac DstArithmeticDemo.java
java DstArithmeticDemo
```

```text
spring calendar = 2024-03-31T12:00+02:00[Europe/Paris]
spring elapsed = 2024-03-31T13:00+02:00[Europe/Paris]
spring calendarHours = 23
spring elapsedHours = 24
autumn calendar = 2024-10-27T12:00+01:00[Europe/Paris]
autumn elapsed = 2024-10-27T11:00+01:00[Europe/Paris]
autumn calendarHours = 25
autumn elapsedHours = 24
```

**Chọn theo nghiệp vụ:**

- Lịch giao hàng “mỗi ngày lúc 12:00 địa phương” → cộng ngày theo vùng hoặc dựng mỗi ngày từ `LocalDate` + `LocalTime` + `ZoneId`.
- Timeout “sau đúng 24 giờ” → thời lượng `Duration.ofHours(24)` / `plusHours(24)`.
- Báo cáo doanh thu “theo ngày địa phương” → xác định ranh giới ngày trong vùng; **không** mặc định mỗi ngày dài 86.400 giây.

Ngày có chuyển giờ không nhất thiết chỉ thay đổi ±1 giờ. Có nơi từng đổi offset 30 phút, nhiều giờ hoặc **bỏ cả một ngày lịch**; code không nên hardcode độ dài transition là 3.600 giây.

## 9. Kiểm thử bằng `Clock.fixed` thay vì phụ thuộc giờ thật

Nếu service gọi `ZonedDateTime.now()` trực tiếp, test phụ thuộc thời gian chạy và default zone của máy. Thay bằng tiêm `Clock`:

```java
ZonedDateTime now = ZonedDateTime.now(clock);
```

*Đây là snippet; `clock` phải được cung cấp từ bên ngoài và đã khai báo đúng kiểu.*

Trong unit test, dùng `Clock.fixed(instant, zone)` để tạo các mốc ở hai phía chuyển đổi. Vì đầu vào là **Instant**, không có sự mơ hồ rằng máy đang ở “lần thứ nhất” hay “lần thứ hai” của một giờ lặp.

Lưu `FixedClockTransitionDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class FixedClockTransitionDemo {
    private static ZonedDateTime read(Instant instant,
                                      ZoneId zone) {
        Clock fake = Clock.fixed(instant, zone);
        return ZonedDateTime.now(fake);
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        Instant justBefore =
                Instant.parse("2024-03-31T00:59:59Z");
        Instant atTransition =
                Instant.parse("2024-03-31T01:00:00Z");

        ZonedDateTime before = read(justBefore, paris);
        ZonedDateTime after = read(atTransition, paris);

        System.out.println("before = " + before);
        System.out.println("after = " + after);
        System.out.println("elapsedSeconds = " +
                Duration.between(
                        before.toInstant(),
                        after.toInstant()).toSeconds());
        System.out.println("clockHourJumped = " +
                (after.getHour() - before.getHour()));
    }
}
```

```bash
javac FixedClockTransitionDemo.java
java FixedClockTransitionDemo
```

```text
before = 2024-03-31T01:59:59+01:00[Europe/Paris]
after = 2024-03-31T03:00+02:00[Europe/Paris]
elapsedSeconds = 1
clockHourJumped = 2
```

Mặc dù đồng hồ địa phương nhảy từ giờ 1 sang giờ 3, **chỉ 1 giây thực** đã trôi qua. Thử nghiệm này ổn định, không cần `Thread.sleep`, và vẫn đúng dù máy đang chạy ở múi giờ khác Paris.

**Ghi nhớ:** `Clock.fixed` giúp giả lập thời điểm, không tự tạo/sửa quy tắc vùng. Nếu JDK/TZDB thay đổi quy tắc của zone, kết quả từ `ZonedDateTime.now(fixedClock)` có thể khác đối với instant tương lai. Muốn test chính sách quy tắc thay đổi độc lập TZDB, xem `ZoneRules` mô phỏng ở mục 12.

## 10. Chính sách strict vs default phải kiểm thử tách biệt

`LocalDateTime.atZone(zone)` giải quyết input *best-effort*: với gap, đẩy giờ lên; với overlap, thường chọn offset sớm hơn nếu không có offset trước đó để giữ. `ZonedDateTime.ofStrict(local, offset, zone)` **chỉ chấp nhận** local và offset hợp lệ theo rules, không tự chọn thay người dùng.

`ZonedDateTime.ofLocal(local, zone, preferredOffset)` có thể giữ offset ưu tiên nếu nó hợp lệ cho local; nếu không hợp lệ hoặc `null` thì áp dụng lựa chọn mặc định. Nó **không phải trình kiểm tra strict**.

Lưu `StrictResolutionDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class StrictResolutionDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime ambiguous =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        ZonedDateTime preferredLater =
                ZonedDateTime.ofLocal(
                        ambiguous, paris, ZoneOffset.ofHours(1));
        ZonedDateTime invalidPreferred =
                ZonedDateTime.ofLocal(
                        ambiguous, paris, ZoneOffset.ofHours(3));

        System.out.println("preferredLater = " + preferredLater);
        System.out.println("invalidFallsBack = " +
                invalidPreferred);
        System.out.println("strictLater = " +
                ZonedDateTime.ofStrict(
                        ambiguous, ZoneOffset.ofHours(1), paris));

        try {
            ZonedDateTime.ofStrict(
                    ambiguous, ZoneOffset.ofHours(3), paris);
            System.out.println("unexpected");
        } catch (DateTimeException ex) {
            System.out.println("strictRejectedInvalidOffset");
        }
    }
}
```

```bash
javac StrictResolutionDemo.java
java StrictResolutionDemo
```

```text
preferredLater = 2024-10-27T02:30+01:00[Europe/Paris]
invalidFallsBack = 2024-10-27T02:30+02:00[Europe/Paris]
strictLater = 2024-10-27T02:30+01:00[Europe/Paris]
strictRejectedInvalidOffset
```

Bài học: nếu người dùng gửi `2024-10-27T02:30` kèm offset `+03:00` nhưng vùng là Paris, **không** nên âm thầm chấp nhận một instant khác bằng fallback khi chính sách yêu cầu validation. Dùng `ofStrict` hoặc `isValidOffset` để báo lỗi chính xác.

### 10.1. Cẩn thận khi parse chuỗi chứa cả offset và zone

Chuỗi ISO-8601 như `2024-10-27T02:30+01:00[Europe/Paris]` chứa **cả offset lẫn region zone**. `ZonedDateTime.parse` có thể dùng offset để xác định instant rồi suy ra local time hợp lệ của zone. Không mặc định mọi chuỗi chứa offset không phù hợp zone sẽ bị từ chối theo cách strict.

Nếu hợp đồng API yêu cầu “local + offset phải đúng với zone rules”, parse thành các thành phần cần thiết rồi kiểm tra bằng `ZonedDateTime.ofStrict` và chính sách validation rõ ràng. Đừng chỉ dựa vào việc `parse` không ném exception.

## 11. Một chuyển đổi không nhất thiết dài đúng một giờ

Ví dụ lịch sử nổi bật: vùng `Pacific/Apia` đã bỏ qua ngày địa phương **30/12/2011** khi đổi offset. Tại giờ `2011-12-30T12:00`, không có offset hợp lệ, và chuyển đổi có độ dài **24 giờ**, không phải 1 giờ.

Lưu `ApiaDateSkipDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;

public class ApiaDateSkipDemo {
    public static void main(String[] args) {
        ZoneId apia = ZoneId.of("Pacific/Apia");
        ZoneRules rules = apia.getRules();
        LocalDateTime skipped =
                LocalDateTime.of(2011, 12, 30, 12, 0);

        ZoneOffsetTransition transition =
                rules.getTransition(skipped);

        System.out.println("valid = " +
                rules.getValidOffsets(skipped));
        System.out.println("gap = " + transition.isGap());
        System.out.println("duration = " +
                transition.getDuration());
        System.out.println("resolved = " +
                skipped.atZone(apia));
    }
}
```

```bash
javac ApiaDateSkipDemo.java
java ApiaDateSkipDemo
```

```text
valid = []
gap = true
duration = PT24H
resolved = 2011-12-31T12:00+14:00[Pacific/Apia]
```

**Từ ví dụ này:** đừng cài cứng `local.plusHours(1)` để xử lý mọi gap. Muốn tuân theo chính sách “dịch đúng độ dài gap”, hãy lấy `ZoneOffsetTransition.getDuration()`. Muốn chạy tại **instant đầu tiên có hiệu lực sau chuyển tiếp**, dùng `getInstant()` và chuyển về zone; đó có thể là thời điểm khác với cách giữ nguyên phút của một input nằm giữa gap.

Test hệ thống toàn cầu còn cần những ngày biến đổi **không ở 02:00**, thay đổi offset không tròn giờ và các vùng có lịch sử chính trị khác nhau. Đừng sao chép giả định “DST luôn vào 02:00 Chủ nhật” từ Paris sang một khu vực khác.

## 12. Kiểm thử **thay đổi quy tắc** bằng ZoneRules mô phỏng

Khi code thực tế phụ thuộc vào phiên bản IANA TZDB, cố đoán quy tắc trong tương lai là rủi ro: chính quyền có thể thay đổi giờ mùa hè, đổi offset chuẩn hoặc dừng DST. Regression test chỉ hardcode “ngày X của năm 2035 Paris chắc chắn nhảy giờ” có thể thất bại sau khi JDK cập nhật dữ liệu, **dù code ứng dụng vẫn đúng**.

Để kiểm tra **logic xử lý thay đổi quy tắc** một cách ổn định, dùng `ZoneRules.of(...)` và `ZoneOffsetTransition.of(...)` để tạo hai bộ quy tắc mô phỏng:

- Phiên bản A: offset cố định `+01:00`.
- Phiên bản B: tại một mốc mô phỏng trong năm 2030, chuyển từ `+01:00` sang `+02:00`, tạo gap 1 giờ.

Ví dụ **không tuyên bố** vùng Paris hoặc bất cứ quốc gia nào thực sự sẽ đổi giờ theo quy tắc này vào năm 2030. Mục tiêu là kiểm thử cách ứng dụng phản ứng trước **hai bộ rule khác nhau**.

Lưu `SyntheticRuleChangeDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public class SyntheticRuleChangeDemo {
    public static void main(String[] args) {
        ZoneOffset before = ZoneOffset.ofHours(1);
        ZoneOffset after = ZoneOffset.ofHours(2);

        ZoneOffsetTransition transition =
                ZoneOffsetTransition.of(
                        LocalDateTime.of(2030, 3, 31, 2, 0),
                        before, after);

        ZoneRules versionA = ZoneRules.of(before);
        ZoneRules versionB = ZoneRules.of(
                before, before,
                List.of(), List.of(transition), List.of());

        LocalDateTime candidate =
                LocalDateTime.of(2030, 3, 31, 2, 30);

        System.out.println("versionA = " +
                versionA.getValidOffsets(candidate));
        System.out.println("versionB = " +
                versionB.getValidOffsets(candidate));
        System.out.println("becameGap = " +
                versionB.getValidOffsets(candidate).isEmpty());
        System.out.println("syntheticDuration = " +
                transition.getDuration());
        System.out.println("syntheticBefore = " +
                transition.getOffsetBefore());
        System.out.println("syntheticAfter = " +
                transition.getOffsetAfter());
    }
}
```

```bash
javac SyntheticRuleChangeDemo.java
java SyntheticRuleChangeDemo
```

```text
versionA = [+01:00]
versionB = []
becameGap = true
syntheticDuration = PT1H
syntheticBefore = +01:00
syntheticAfter = +02:00
```

Cùng một local timestamp, bộ quy tắc A có **1** offset hợp lệ, bộ B có **0**. Vì vậy việc kết quả đổi sau cập nhật luật **không nhất thiết là bug parser**. Điều đúng cần kiểm tra là code có định nghĩa cách xử lý **theo bộ rules đang được áp dụng**, có thông báo khi cuộc hẹn tương lai thay đổi instant và có cơ chế quyết định version/rule policy hay không.

`ZoneRules` chỉ là bộ quy tắc, **không phải `ZoneId` tự động đăng ký**. Đừng cài đặt thử thành “múi giờ thật của Paris” hoặc ép sử dụng `ZoneRulesProvider.registerProvider` trong ứng dụng chỉ để chạy unit test. Với test của một service nhận `ZoneId`, có thể tách lớp chuyển local → kết quả theo `ZoneRules` thành hàm thuần để bơm quy tắc mô phỏng, rồi dùng integration test riêng với `ZoneId` thực.

### 12.1. Vì sao test synthetic quan trọng?

Nó cho phép bắt các lỗi như:

- Code chỉ xét `validOffsets.get(0)` mà không kiểm tra list rỗng.
- Code mặc định gap luôn một giờ.
- Code lưu offset từ lần tính cũ rồi áp vào lịch tương lai sau khi rules đổi.
- Code coi `LocalDateTime + ZoneId` luôn là một instant duy nhất.
- Code không có lộ trình xử lý/thông báo khi lịch đã lưu thay đổi instant vì tzdb được nâng cấp.

Đặc biệt, nếu lưu lịch tái diễn, nên lưu **local time + zone region + rule nghiệp vụ**, còn instant cụ thể có thể phải **tính lại cho ngày tương lai** khi tzdb thay đổi. Với lịch đã xác định là “đúng một instant trên timeline”, lưu Instant và xem offset chỉ là biểu diễn. Đó là hai chính sách khác nhau.

## 13. TZDB/JDK cập nhật: kiểm thử dữ liệu thực và quy tắc tương lai

Dữ liệu múi giờ thường đến từ IANA TZDB thông qua provider của Java. Mỗi bản JDK có thể tích hợp một phiên bản TZDB khác nhau; các bản cập nhật Java có thể điều chỉnh lịch sử hoặc dự báo giờ tương lai khi thông tin mới xuất hiện.

`ZoneRulesProvider.getVersions(zoneId)` cho phép hỏi các phiên bản mà provider cung cấp cho một region zone. **Không mặc định provider phải giữ toàn bộ lịch sử các phiên bản**; nhiều hệ thống chỉ cung cấp phiên bản đang đóng gói. `ZoneRulesProvider.refresh()` là cơ chế dành cho provider có khả năng cập nhật động, nhưng **provider mặc định của JDK không hỗ trợ làm mới quy tắc động** theo Javadoc; không gọi `refresh()` và mong toàn bộ container/JVM thay rules mà không triển khai cơ chế riêng.

Lưu `ZoneRulesProviderDemo.java`:

```java
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRulesProvider;
import java.util.NavigableMap;

public class ZoneRulesProviderDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        NavigableMap<String, java.time.zone.ZoneRules> versions =
                ZoneRulesProvider.getVersions("Europe/Paris");

        System.out.println("hasParis = " +
                ZoneId.getAvailableZoneIds()
                        .contains("Europe/Paris"));
        System.out.println("hasVersion = " +
                !versions.isEmpty());
        System.out.println("parisFixed = " +
                paris.getRules().isFixedOffset());
        System.out.println("utcFixed = " +
                ZoneOffset.UTC.getRules().isFixedOffset());
    }
}
```

```bash
javac ZoneRulesProviderDemo.java
java ZoneRulesProviderDemo
```

```text
hasParis = true
hasVersion = true
parisFixed = false
utcFixed = true
```

Chương trình cố tình **không** in chuỗi version cụ thể vì điều đó sẽ biến stdout thành phụ thuộc cấu hình JDK/tzdb. Trong CI/CD, nên ghi lại **runtime Java version, timezone rules provider và phiên bản TZDB khi có** làm metadata để điều tra khi một test theo quy tắc thực thay đổi.

**Hai lớp test nên có:**

1. **Unit test không phụ thuộc TZDB:** dùng quy tắc synthetic để kiểm tra nhánh normal/gap/overlap/đổi chính sách.
2. **Integration/regression test với JDK triển khai:** chạy các vùng/lịch sử đại diện, kiểm tra quy tắc thực đang có và phát hiện thay đổi so với yêu cầu nghiệp vụ.

Khi nâng JDK/tzdb, nếu test tương lai thay đổi, không sửa test một cách máy móc: xác nhận xem rule mới phản ánh thay đổi chính sách chính thức, sau đó quyết định điều chỉnh lịch/chấp nhận/tái thông báo. Nếu kết quả trước/sau không còn cùng instant, có thể phải **di chuyển lịch tương lai** hoặc **giữ thời điểm cũ** tùy contract.

## 14. Thiết kế hàm resolve local time có chính sách rõ ràng

Thay vì dùng `local.atZone(zone)` ở mọi nơi, có thể định nghĩa một resolver “không chấp nhận nhập mơ hồ”:

- Nếu có **0 offset**: từ chối gap.
- Nếu có **1 offset**: tạo ZonedDateTime strict với offset duy nhất.
- Nếu có **2 offset**: yêu cầu caller cung cấp offset mong muốn; nếu thiếu, từ chối để người dùng chọn. Offset chọn phải là một trong các giá trị hợp lệ.
- Không tự lấy offset từ timezone mặc định của máy.

Lưu `StrictSchedulerResolverDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictSchedulerResolverDemo {
    private static ZonedDateTime resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset preference) {
        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException("gap");
        }
        if (valid.size() == 2 && preference == null) {
            throw new IllegalArgumentException(
                    "overlap needs offset");
        }

        ZoneOffset chosen =
                preference == null ? valid.get(0) : preference;

        return ZonedDateTime.ofStrict(local, chosen, zone);
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        System.out.println("normal = " + resolve(
                LocalDateTime.of(2024, 5, 1, 9, 0),
                paris, null));

        try {
            resolve(LocalDateTime.of(
                    2024, 3, 31, 2, 30), paris, null);
        } catch (IllegalArgumentException e) {
            System.out.println("gap rejected");
        }

        try {
            resolve(LocalDateTime.of(
                    2024, 10, 27, 2, 30), paris, null);
        } catch (IllegalArgumentException e) {
            System.out.println("overlap needs choice");
        }

        System.out.println("selected = " + resolve(
                LocalDateTime.of(2024, 10, 27, 2, 30),
                paris, ZoneOffset.ofHours(1)));
    }
}
```

```bash
javac StrictSchedulerResolverDemo.java
java StrictSchedulerResolverDemo
```

```text
normal = 2024-05-01T09:00+02:00[Europe/Paris]
gap rejected
overlap needs choice
selected = 2024-10-27T02:30+01:00[Europe/Paris]
```

Ở đây nếu caller cung cấp offset sai ngay cả cho giờ normal, `ZonedDateTime.ofStrict` vẫn từ chối. Chương trình tách rõ **validation** và **normalization**, tránh cho một lần chuyển đổi ngầm làm thay đổi giờ đăng ký mà người dùng không hay biết.

Với bài toán khác như cron hoặc hệ thống có quy tắc “nếu giờ bị bỏ qua thì chạy tại mốc hợp lệ kế tiếp”, hãy viết chính sách riêng và test các trường hợp theo `ZoneRules`. Không có một câu trả lời đúng cho mọi nghiệp vụ.

## 15. Test matrix nên bao phủ gì?

Khi triển khai code liên quan múi giờ, test ít nhất những lớp tình huống sau (tùy phạm vi sản phẩm):

| Nhóm | Ví dụ cần xác minh | Assertion nên viết |
| --- | --- | --- |
| Normal | Một ngày bình thường trong zone | Đúng một offset, convert local ↔ instant round-trip |
| Trước gap | Ngay trước chuyển tiến | Dùng offset trước |
| Trong gap | Local time không tồn tại | Offset list rỗng; resolver reject/shift đúng policy |
| Ngay tại gap end | Instant transition | Dùng offset sau |
| Trước overlap | Ngay trước chuyển lùi | Dùng offset trước |
| Trong overlap | Giờ bị lặp | Hai offset; hai instants khác nhau |
| Sau overlap | Sau giờ lặp | Chỉ một offset |
| Chuyển đổi không ±1h | Apia bỏ 24h | Không hardcode 3600 giây |
| Cộng 1 ngày | Ngày chuyển tiến/lùi | 23/25 giờ thực ở ví dụ Paris |
| Cộng 24 giờ | Cùng start instant | Luôn đúng 24 giờ elapsed, local time có thể khác |
| Giờ vùng cố định | `ZoneOffset.UTC` | Không có transition; không gọi method trên null |
| Quy tắc bị sửa | Synthetic A/B | Cùng local có thể đổi từ normal thành gap |
| Dữ liệu provider | JDK/TZDB nâng phiên bản | Nhận diện và đánh giá thay đổi có chủ đích |
| Lịch qua nửa đêm | Offset chuyển trong đêm | Không mất ngày hay đổi instant do lỗi convert |
| Giao dịch nhiều máy | Log và offset khác nhau | So theo Instant, không theo LocalDateTime hoặc string raw |
| Test giờ hiện tại | `Clock.fixed` ở hai phía transition | Không dùng sleep hay dựa vào timezone host |

**Với mỗi transition:** xác minh cả **instant boundary** và **local-time ambiguity**. Nếu chỉ kiểm tra `atZone` của một instant, bạn bỏ qua việc local time có thể không có offset. Nếu chỉ kiểm tra một local time trong gap, bạn chưa biết chính xác ranh giới nào có hiệu lực.

## 16. Round-trip và độ chính xác của dữ liệu đã lưu

Để lưu một sự kiện đã xảy ra, dùng `Instant` hoặc một biểu diễn đủ ngày, giờ và offset như `OffsetDateTime`. Khi hiển thị lại theo region zone:

```java
Instant stored = Instant.parse("2024-10-27T01:30:00Z");
ZonedDateTime displayed =
        stored.atZone(ZoneId.of("Europe/Paris"));
```

*Đoạn này là snippet; các class `Instant`, `ZonedDateTime` và `ZoneId` cần được import. Kết quả hiển thị là `2024-10-27T02:30+01:00[Europe/Paris]`.*

**Mất thông tin cần tránh:**

- `ZonedDateTime.toLocalDateTime()` bỏ offset và vùng; trong overlap, **không thể biết lần nào** chỉ từ local time.
- `ZonedDateTime.toOffsetDateTime()` còn giữ offset và đủ thông tin instant, nhưng **không giữ tên region zone**, nên không thể suy ra DST rule trong tương lai.
- `Instant` giữ instant UTC, nhưng không giữ “người dùng đã chọn múi giờ nào” để dựng lại đúng ý định lịch tái diễn.
- Chuỗi timestamp chuyển sang `epochMillis` có thể mất phần nanosecond; khi test ranh giới sát nanosecond cần kiểm tra precision của storage/serialization.

Nếu lập lịch trong tương lai theo giờ địa phương, có thể cần lưu **LocalDateTime/LocalTime + ZoneId + chính sách gap/overlap + trạng thái offset đã chọn nếu cần**, không chỉ một Instant cố định. Nếu đây là event đã xảy ra, lưu Instant thường phù hợp hơn. Việc chọn schema phụ thuộc rõ ràng vào yêu cầu “giữ thời điểm” hay “giữ giờ địa phương khi luật đổi”.

### 16.1. Đừng suy luận từ tên vùng hoặc chuỗi đã format

Các chuỗi ISO có region `[Europe/Paris]` và offset là dữ liệu có ý nghĩa. Nhưng nếu parse một chuỗi chứa **offset không hợp lệ cho local time của zone**, Java có thể dùng offset để xác định instant rồi chuyển về local time khác theo rules, tùy API. Đối với dữ liệu cần validation nghiêm ngặt, **tách thông tin và kiểm tra strict**. Test nên bao gồm input offset sai, input thiếu offset, zone không tồn tại và ngày không hợp lệ.

Đừng dựa vào thứ tự từ vựng của chuỗi local timestamp để so sánh event từ các múi giờ khác nhau; chuẩn hóa về `Instant` rồi so timeline.

## 17. Lỗi thường gặp và cách tránh

| Lỗi | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Coi mọi local time là hợp lệ | Lịch trượt giờ trong gap | `getValidOffsets` và gap policy |
| Coi mọi local time có đúng một instant | Lịch overlap chọn sai lần | Yêu cầu offset hoặc quy tắc earlier/later |
| Dùng `getOffset(local)` làm validation | Trả offset “best” ngay cả trong gap | `getValidOffsets`/`getTransition` |
| Dùng `local.atZone` dù cần strict | Tự dịch gap theo default | `ofStrict` và lỗi rõ ràng |
| Coi `ofLocal` là strict | Offset sai bị fallback | `ofStrict` khi cần kiểm tra đầu vào |
| Cộng đúng 24h để diễn tả 1 ngày lịch | Lệch giờ trong DST | Dùng `plusDays` hoặc lịch local |
| Cộng `plusDays` khi thực sự cần 24h | Elapsed time 23/25h | Dùng `Duration`/`plusHours` |
| Hardcode gap luôn 1 giờ | Sai ở thay đổi 30 phút/24 giờ | Đọc `ZoneOffsetTransition.getDuration` |
| Kiểm thử DST bằng `Thread.sleep` | Flaky, phụ thuộc OS | `Clock.fixed`, instant cố định |
| Chọn zone từ `ZoneId.systemDefault()` ẩn | Test khác máy cho kết quả khác | Tiêm `ZoneId`/`Clock` rõ ràng |
| Hardcode DST tương lai thành chuẩn bất biến | Sai sau khi tzdb đổi | Synthetic unit test + integration test theo rule version |
| Mong `ZoneRulesProvider.refresh()` cập nhật mặc định ngay | Provider mặc định không dynamic refresh | Nâng cấp JDK/tzdb theo quy trình triển khai |
| Gắn offset cố định vào giờ họp vùng địa lý | Sai khi chính sách thay đổi | Lưu tên region zone và ngày cụ thể |
| Chỉ lưu `LocalDateTime` của event trong overlap | Không biết sự kiện thứ nhất hay thứ hai | Lưu Instant hoặc offset kèm theo |
| Coi `ZonedDateTime` là mutable | Có thể bỏ kết quả `plusDays` | Dùng object kết quả được trả về |
| Bắt exception rồi âm thầm chọn một giờ khác | Thay đổi nghiệp vụ ngoài ý muốn | Công bố policy và test |
| Dùng một bộ test cố định năm 2024 để “chứng minh luật 2035” | Suy luận vượt phạm vi | Phân biệt lịch sử đã biết và tương lai có thể đổi |

## 18. Bài tập tự kiểm tra

**Bài 1 — Phân loại.** Giải thích vì sao `2024-03-31T02:30` tại `Europe/Paris` có 0 offset, còn `2024-10-27T02:30` có 2 offset. Liệt kê offset của trường hợp overlap và đổi cả hai sang UTC.

**Bài 2 — Ranh giới.** Viết test trước transition 1 ns, tại transition và sau 1 ns. Chứng minh instant vẫn tiến đều, nhưng local hour có thể nhảy.

**Bài 3 — Policy.** Nếu sản phẩm đặt lịch khám yêu cầu đúng giờ người dùng nhập, bạn sẽ chọn reject gap hay shift forward? Trường hợp overlap cần thêm thông tin gì để không đặt nhầm lịch?

**Bài 4 — Arithmetic.** Tại sao khoảng từ 12:00 ngày 30/03 đến 12:00 ngày 31/03/2024 ở Paris chỉ là 23 giờ thực? Khi nào nên dùng `plusDays(1)` thay vì `plusHours(24)`?

**Bài 5 — Thay đổi quy tắc.** Với synthetic version A (+01 cố định) và version B (+01 → +02), cùng local `2030-03-31T02:30` chuyển từ 1 valid offset thành 0. Thiết kế cách hiển thị thông báo cho người có lịch tương lai nếu backend vừa cập nhật bộ rules.

### Lời giải thực hành

Lưu `DstBoundaryPractice.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;

public class DstBoundaryPractice {
    private static String classification(
            ZoneId zone, LocalDateTime local) {
        int count = zone.getRules()
                .getValidOffsets(local).size();
        return count == 0 ? "GAP"
                : count == 1 ? "NORMAL" : "OVERLAP";
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        LocalDateTime spring =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        LocalDateTime normal =
                LocalDateTime.of(2024, 5, 1, 12, 0);
        LocalDateTime autumn =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println("spring = " +
                classification(paris, spring));
        System.out.println("normal = " +
                classification(paris, normal));
        System.out.println("autumn = " +
                classification(paris, autumn));

        ZonedDateTime first = autumn.atZone(paris)
                .withEarlierOffsetAtOverlap();
        ZonedDateTime second = autumn.atZone(paris)
                .withLaterOffsetAtOverlap();

        System.out.println("firstUTC = " + first.toInstant());
        System.out.println("secondUTC = " + second.toInstant());
        System.out.println("sameLocal = " +
                first.toLocalDateTime().equals(
                        second.toLocalDateTime()));
        System.out.println("sameInstant = " +
                first.toInstant().equals(second.toInstant()));
    }
}
```

```bash
javac DstBoundaryPractice.java
java DstBoundaryPractice
```

```text
spring = GAP
normal = NORMAL
autumn = OVERLAP
firstUTC = 2024-10-27T00:30:00Z
secondUTC = 2024-10-27T01:30:00Z
sameLocal = true
sameInstant = false
```

**Giải thích:** cùng local `02:30` trong overlap thuộc **hai** instants khác nhau; khi sản phẩm chỉ lưu local time mà không biết offset, thông tin để phân biệt hai lượt đã bị mất. Code kiểm thử cần xác nhận lựa chọn nghiệp vụ rõ ràng chứ không mặc định một offset.

## 19. Checklist trước khi merge/deploy

- Đã phân biệt input `Instant` với `LocalDateTime` và `ZoneId` chưa?
- Dùng `getValidOffsets(local)` để xét trường hợp 0/1/2, không chỉ `getOffset(local)`?
- Chính sách **gap** là reject, shift theo duration hay chuyển tới boundary kế tiếp? Đã viết test?
- Chính sách **overlap** chọn lần đầu/lần sau/yêu cầu người dùng chọn? Đã lưu offset khi cần?
- Có test ngay trước, đúng tại và sau instant chuyển đổi?
- Có test ngày thường và zone không đổi offset?
- Có test ví dụ chuyển đổi không dài 1 giờ, như bỏ ngày lịch?
- Đã phân biệt cộng 1 ngày lịch với 24 giờ thực qua DST?
- Code lấy “now” có tiêm `Clock` để test ổn định?
- Có unit test bằng **ZoneRules mô phỏng** thay vì chỉ hardcode quy tắc tương lai từ TZDB?
- Có integration test vùng thật và metadata phiên bản JDK/TZDB khi nâng cấp?
- Có tránh giả định `ZoneRulesProvider.refresh()` tự cập nhật provider mặc định?
- Có cơ chế nhận diện lịch tương lai bị thay đổi instant khi chính quyền đổi luật?
- Có tránh làm mất offset/zone khi serialize timestamp, nhất là giờ trong overlap?
- Có phân biệt “giữ nguyên instant” với “giữ nguyên local hour” trong yêu cầu nghiệp vụ?
- Có giới hạn test vào đúng phương thức/các ô dữ liệu sở hữu, không tạo side effect ngoài test?

## 20. Tham khảo Java API hiện hành

- `ZonedDateTime`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html
- `ZoneId`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- `ZoneRules`, valid offsets và next/previous transition: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html
- `ZoneOffsetTransition`, gap/overlap, duration: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html
- `ZoneRulesProvider`, versions và dynamic refresh: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRulesProvider.html
- `LocalDateTime`, atZone: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html
- `Instant`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html
- `Clock`, fixed/offset: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html

**Kết luận:** kiểm thử múi giờ không chỉ là kiểm tra phép cộng giờ. Với một local time, trước hết phải biết nó có **0, 1 hay 2 offset hợp lệ**; ở ranh giới chuyển giờ phải xác minh cả instant và local time, đồng thời tách **ngày lịch** khỏi **duration**. Vì quy tắc vùng có thể được cập nhật, hãy kiểm thử logic bằng synthetic rules và kiểm thử tích hợp bằng TZDB của môi trường triển khai; đừng coi quy tắc tương lai là bất biến.