# Kiểm tra khoảng hiệu lực bằng quy ước nửa mở

## 1. Khoảng nửa mở giải quyết câu hỏi tại ranh giới

Giả sử một chính sách có hiệu lực từ 09:00 đến 10:00. Đúng 09:00 đã có hiệu lực chưa? Đúng 10:00 còn hiệu lực không? Nếu khoảng tiếp theo bắt đầu lúc 10:00, thời điểm đó thuộc khoảng nào?

Quy ước nửa mở trả lời rõ:

```text
[fromInclusive, untilExclusive)

Bao gồm thời điểm bắt đầu.
Không bao gồm thời điểm kết thúc.
```

Với khoảng `[09:00, 10:00)`:

| Thời điểm kiểm tra | Có hiệu lực? |
| --- | --- |
| Trước 09:00 | Không |
| Đúng 09:00 | Có |
| Sau 09:00 và trước 10:00 | Có |
| Đúng 10:00 | Không |
| Sau 10:00 | Không |

Quy ước này đặc biệt hữu ích cho khoảng hiệu lực nối tiếp, lịch đặt chỗ, dữ liệu phân theo ngày và các phiên bản chính sách theo thời gian.

Bài thực hành dùng khoảng hữu hạn, không rỗng, với điều kiện `fromInclusive < untilExclusive`. Cả hai cận là `Instant`, vì đang kiểm tra hiệu lực tại thời điểm cụ thể trên trục thời gian.

## 2. Điều kiện chứa một thời điểm

Một thời điểm `t` thuộc khoảng khi:

```text
fromInclusive <= t AND t < untilExclusive
```

Trong Java:

```java
// Minh họa khi fromInclusive, untilExclusive và t đều là Instant.
boolean active =
        !t.isBefore(fromInclusive) && t.isBefore(untilExclusive);
```

Phần đầu dùng `!isBefore` để bao gồm trường hợp bằng cận đầu. Phần sau dùng `isBefore` để loại trường hợp bằng cận cuối.

Hai cách viết dễ sai:

- Dùng `t.isAfter(from)`: làm mất hiệu lực đúng tại cận đầu.
- Dùng `!t.isAfter(until)`: đưa cả cận cuối vào khoảng.

Không dùng so chuỗi đã định dạng để thay những phép so này. `Instant` so thời điểm, không phụ thuộc cách in ra ngày giờ địa phương. Mô hình và phép so được mô tả tại [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).

## 3. Vì sao hai khoảng liền nhau không đếm trùng?

Xét:

```text
Khoảng A: [09:00, 10:00)
Khoảng B: [10:00, 11:00)
```

Tại 10:00:

- A không chứa thời điểm đó.
- B chứa thời điểm đó.

Như vậy, cùng một ranh giới được dùng làm cuối khoảng trước và đầu khoảng sau mà không bị đếm hai lần. Cũng không cần tạo một khe hở bằng cách cộng/trừ một mili giây.

Nếu cả hai khoảng đều bao gồm cận cuối, 10:00 có thể thuộc cả A và B. Nếu cả hai đều bỏ cận đầu, có thể bỏ sót thời điểm bắt đầu. Nửa mở cung cấp một quy ước nối tiếp nhất quán.

Các khoảng vẫn có thể chồng lấn nếu dữ liệu được tạo như `[09:00, 10:30)` và `[10:00, 11:00)`. Quy ước cận không tự bảo đảm mọi bản ghi không chồng nhau; điều đó cần quy tắc dữ liệu riêng nếu nghiệp vụ yêu cầu.

## 4. Xác thực khoảng trước khi kiểm tra hiệu lực

Mẫu trong bài yêu cầu:

1. Hai cận khác `null`.
2. Cận đầu phải trước cận cuối.
3. Kiểu dữ liệu và ngữ nghĩa của hai cận phải thống nhất.

Về toán học, `[a, a)` là khoảng rỗng. Nhưng đối tượng `Window` trong bài biểu diễn một khoảng hiệu lực phải có độ dài dương, nên từ chối cả cận bằng nhau lẫn đảo thứ tự.

Nếu mô hình của ứng dụng cho phép khoảng rỗng, phải triển khai và kiểm tra hành vi đó nhất quán. Đặc biệt, công thức kiểm tra chồng lấn không nên vô tình cho một khoảng rỗng “chồng” với khoảng khác.

Bài cũng không dùng `null` để biểu diễn “không có ngày hết hạn”. Khoảng không giới hạn là một thiết kế khác, cần được nêu rõ. Không dùng một ngày cực lớn tùy ý làm cận cuối rồi giả định mọi kho và phép chuyển múi giờ đều biểu diễn được.

## 5. Kiểm tra hiện tại bằng Clock

Một hàm hỏi “đang có hiệu lực không?” cần nguồn thời điểm hiện tại. Thay vì gọi `Instant.now()` rải rác, có thể nhận `Clock`:

```java
// Minh họa bên trong một phương thức có window và clock.
Instant reference = clock.instant();
boolean active = window.contains(reference);
```

Đọc một thời điểm tham chiếu rồi dùng lại cho các quyết định thuộc cùng lần xử lý. Nếu đọc đồng hồ nhiều lần gần cận cuối, các kết quả có thể thuộc hai phía ranh giới.

Trong kiểm thử, dùng `Clock.fixed` tại đúng đầu và đúng cuối khoảng. Không dùng `Thread.sleep` để hy vọng chương trình chạy đúng lúc cần kiểm tra. `Clock` được thiết kế để thay nguồn thời gian trong kiểm thử; xem [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).

Lưu ý: `contains` trả `false` có thể vì **chưa bắt đầu** hoặc **đã hết hiệu lực**. Không đồng nhất “không có hiệu lực” với “đã hết hạn”. Nếu giao diện cần phân biệt, kiểm tra trạng thái theo ba miền:

```text
t < from             → chưa bắt đầu
from <= t < until    → có hiệu lực
t >= until           → hết hiệu lực
```

## 6. Hai khoảng chồng lấn khi nào?

Với hai khoảng không rỗng:

```text
A = [aStart, aEnd)
B = [bStart, bEnd)
```

Chúng chồng lấn khi:

```text
aStart < bEnd AND bStart < aEnd
```

Các dấu so sánh đều nghiêm ngặt. Nhờ vậy, A kết thúc đúng lúc B bắt đầu không bị coi là chồng lấn.

Khi có phần giao:

- Cận đầu phần giao là cận đầu muộn hơn.
- Cận cuối phần giao là cận cuối sớm hơn.

Trong chương trình, `intersection` trả `Optional.empty()` khi không giao. Nếu chỉ chạm ở một điểm, phần giao cũng rỗng vì điểm chung không thuộc cả hai khoảng nửa mở.

Không tạo đối tượng `Window` có hai cận bằng nhau để biểu diễn trường hợp không giao trong mô hình này, vì hàm dựng đã công bố không chấp nhận khoảng rỗng.

## 7. Đổi khoảng ngày người dùng chọn sang khoảng thời điểm

Người dùng có thể nhập “từ ngày 1/5 đến hết ngày 31/5”. Đây là hai ngày **bao gồm cả ngày cuối**, khác với cận thời điểm loại trừ.

Nếu nghiệp vụ chọn múi giờ `Asia/Ho_Chi_Minh`, chuyển như sau:

```text
Cận đầu:  đầu ngày 01/05/2024 trong vùng nghiệp vụ
Cận cuối: đầu ngày 01/06/2024 trong cùng vùng, không bao gồm
```

Tương ứng các thời điểm trong ví dụ:

```text
[2024-04-30T17:00Z, 2024-05-31T17:00Z)
```

Ngày UTC ở cận có thể khác ngày người dùng nhập. Điều đó không tự nói rằng phép đổi sai; cần nhìn cận trong đúng vùng nghiệp vụ.

Cách tính:

```java
// Minh họa bên trong một phương thức.
Instant from = firstDate.atStartOfDay(zone).toInstant();
Instant until = lastDateInclusive.plusDays(1)
        .atStartOfDay(zone).toInstant();
```

Không lấy `23:59:59` của ngày cuối. Cách đó bỏ phần giây còn lại. Cũng không trừ một nano khỏi đầu ngày sau để tạo “thời điểm cuối cùng”, vì độ chính xác của kho có thể khác Java.

`atStartOfDay(zone)` trả thời gian hợp lệ sớm nhất theo quy tắc vùng. Đầu ngày sau phải được tính từ ngày lịch tiếp theo, không mặc định bằng cận đầu cộng 24 giờ. Các quy tắc này được mô tả tại [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

Ngày 31/3/2024 tại Paris trong chương trình có khoảng từ đầu ngày đến đầu ngày kế tiếp dài 23 giờ. Những thay đổi offset khác cũng có thể xảy ra; quy ước nửa mở vẫn giữ nguyên, chỉ các thời điểm của cận thay đổi theo lịch vùng.

Nếu ngày cuối đã ở giới hạn biểu diễn và không thể cộng thêm một ngày, phép chuyển phải được xử lý theo hợp đồng miền dữ liệu. Không bỏ qua lỗi rồi tự dùng một cận sai.

## 8. Chương trình Java 17+ chạy độc lập

Lưu mã sau thành `HalfOpenValidity.java`. Chương trình không cần thư viện ngoài.

`Window` biểu diễn khoảng hiệu lực không rỗng. `forInclusiveDates` là hàm chuyển giao diện ngày bao gồm hai đầu sang khoảng thời điểm nửa mở trong một vùng được truyền rõ.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.Optional;

public class HalfOpenValidity {
    public record Window(Instant fromInclusive, Instant untilExclusive) {
        public Window {
            Objects.requireNonNull(fromInclusive, "fromInclusive");
            Objects.requireNonNull(untilExclusive, "untilExclusive");
            if (!fromInclusive.isBefore(untilExclusive)) {
                throw new IllegalArgumentException("from must be before until");
            }
        }

        public boolean contains(Instant value) {
            Objects.requireNonNull(value, "value");
            return !value.isBefore(fromInclusive) && value.isBefore(untilExclusive);
        }

        public boolean isActive(Clock clock) {
            return contains(Objects.requireNonNull(clock, "clock").instant());
        }

        public boolean overlaps(Window other) {
            Objects.requireNonNull(other, "other");
            return fromInclusive.isBefore(other.untilExclusive)
                    && other.fromInclusive.isBefore(untilExclusive);
        }

        public Optional<Window> intersection(Window other) {
            if (!overlaps(other)) {
                return Optional.empty();
            }
            Instant from = fromInclusive.isAfter(other.fromInclusive)
                    ? fromInclusive : other.fromInclusive;
            Instant until = untilExclusive.isBefore(other.untilExclusive)
                    ? untilExclusive : other.untilExclusive;
            return Optional.of(new Window(from, until));
        }
    }

    public static Window forInclusiveDates(LocalDate first, LocalDate last,
                                           ZoneId zone) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(last, "last");
        Objects.requireNonNull(zone, "zone");
        if (first.isAfter(last)) {
            throw new IllegalArgumentException("first date must not be after last");
        }
        return new Window(first.atStartOfDay(zone).toInstant(),
                last.plusDays(1).atStartOfDay(zone).toInstant());
    }

    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        Instant a = Instant.parse("2024-05-01T09:00:00Z");
        Instant b = Instant.parse("2024-05-01T10:00:00Z");
        Instant c = Instant.parse("2024-05-01T11:00:00Z");
        Window first = new Window(a, b);
        Window adjacent = new Window(b, c);
        Window crossing = new Window(a.plusSeconds(1800), c);

        eq(first.contains(a.minusNanos(1)), false);
        eq(first.contains(a), true);
        eq(first.contains(a.plusNanos(1)), true);
        eq(first.contains(b.minusNanos(1)), true);
        eq(first.contains(b), false);
        eq(first.contains(b.plusNanos(1)), false);
        eq(adjacent.contains(b), true);
        eq(first.overlaps(adjacent), false);
        eq(adjacent.overlaps(first), false);
        eq(first.overlaps(crossing), true);
        eq(crossing.overlaps(first), true);
        eq(first.intersection(adjacent), Optional.empty());
        eq(first.intersection(crossing),
                Optional.of(new Window(a.plusSeconds(1800), b)));
        eq(first.overlaps(first), true);
        eq(first.isActive(Clock.fixed(a, ZoneOffset.UTC)), true);
        eq(first.isActive(Clock.fixed(b, ZoneOffset.UTC)), false);
        rejects(() -> new Window(a, a));
        rejects(() -> new Window(b, a));

        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        Window may = forInclusiveDates(LocalDate.of(2024, 5, 1),
                LocalDate.of(2024, 5, 31), businessZone);
        eq(may.fromInclusive(), Instant.parse("2024-04-30T17:00:00Z"));
        eq(may.untilExclusive(), Instant.parse("2024-05-31T17:00:00Z"));
        eq(may.contains(may.untilExclusive().minusNanos(1)), true);
        eq(may.contains(may.untilExclusive()), false);
        rejects(() -> forInclusiveDates(LocalDate.of(2024, 6, 1),
                LocalDate.of(2024, 5, 31), businessZone));

        Window spring = forInclusiveDates(LocalDate.of(2024, 3, 31),
                LocalDate.of(2024, 3, 31), ZoneId.of("Europe/Paris"));
        eq(Duration.between(spring.fromInclusive(),
                spring.untilExclusive()).toHours(), 23L);

        System.out.println("activeAtStart=" + first.contains(a));
        System.out.println("activeAtEnd=" + first.contains(b));
        System.out.println("adjacentActiveAtBoundary=" + adjacent.contains(b));
        System.out.println("adjacentOverlap=" + first.overlaps(adjacent));
        System.out.println("crossingOverlap=" + first.overlaps(crossing));
        System.out.println("mayStart=" + may.fromInclusive());
        System.out.println("mayEndExclusive=" + may.untilExclusive());
        System.out.println("springDayHours=" + Duration.between(
                spring.fromInclusive(), spring.untilExclusive()).toHours());
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HalfOpenValidity.java
java HalfOpenValidity
```

Stdout:

```text
activeAtStart=true
activeAtEnd=false
adjacentActiveAtBoundary=true
adjacentOverlap=false
crossingOverlap=true
mayStart=2024-04-30T17:00:00Z
mayEndExclusive=2024-05-31T17:00:00Z
springDayHours=23
PASS checks=24
```

Hàm `eq` chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Hàm `rejects` xác nhận các khoảng nằm ngoài hợp đồng bị từ chối.

Các ca kiểm tra gồm:

- Ngay trước, đúng và ngay sau cận đầu.
- Ngay trước, đúng và ngay sau cận cuối.
- Hai khoảng tiếp giáp.
- Hai khoảng giao nhau và tính đối xứng của kiểm tra giao.
- Phần giao đúng cận.
- Khoảng bằng nhau.
- Clock cố định ở hai ranh giới.
- Hai cận bằng nhau hoặc đảo thứ tự.
- Ngày cuối bao gồm được đổi sang cận thời điểm loại trừ.
- Ngày nghiệp vụ có độ dài khác 24 giờ.

Một nano giây trước/sau được dùng để thử ranh giới của `Instant` trong bộ nhớ. Đó không phải yêu cầu kho dữ liệu phải lưu được nano giây; kiểm tra tích hợp cần chọn các giá trị phù hợp với độ chính xác thật của kho.

## 9. Giữ cùng quy ước khi truy vấn và lưu trữ

Đối với sự kiện thuộc một khoảng, điều kiện SQL minh họa là:

```sql
WHERE event_time >= :from_inclusive
  AND event_time <  :until_exclusive
```

Đối với các bản ghi khoảng hiệu lực đang hoạt động tại một thời điểm:

```sql
WHERE valid_from <= :reference_time
  AND :reference_time < valid_until
```

Đây là hình dạng điều kiện; cú pháp tham số thực tế tùy API và hệ quản trị. Các tham số cần được ánh xạ theo đúng ngữ nghĩa thời điểm, không ghép chuỗi hiển thị vào SQL.

Không đổi điều kiện trên thành một phép kiểm tra bao gồm cả cận cuối mà vẫn giữ tên `untilExclusive`. Cả Java, truy vấn, dữ liệu lưu và giao diện phải thống nhất ý nghĩa.

Nếu kho làm giảm độ chính xác của cận, hãy xác định quy tắc cắt/làm tròn và kiểm tra lại những thời điểm sát cận. Quy ước nửa mở giải quyết tính bao gồm, không tự ngăn kho thay đổi giá trị cận.

Khi công bố một API, tên như `fromInclusive` và `untilExclusive` giúp bên gọi không phải đoán. Với màn hình dùng “đến hết ngày”, chuyển đổi ở ranh giới giao diện như ví dụ thay vì buộc người dùng hiểu một mốc thời gian kỹ thuật.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Bỏ cả cận đầu và cận cuối | Không có hiệu lực đúng lúc bắt đầu | Bao gồm cận đầu |
| Bao gồm cận cuối | Hai khoảng liền nhau cùng nhận ranh giới | Dùng `t < until` |
| Tạo khe hở bằng cộng/trừ một đơn vị nhỏ | Phụ thuộc độ chính xác | Dùng chung ranh giới nửa mở |
| Dùng chuỗi ngày giờ để so | Lệch thứ tự hoặc mất thông tin | So kiểu thời gian phù hợp |
| Coi `!contains` luôn là hết hạn | Nhầm chưa bắt đầu với đã hết hạn | Phân biệt ba trạng thái |
| Không kiểm tra thứ tự cận | Khoảng sai vẫn được lưu | Xác thực khi tạo |
| Lấy ngày cuối lúc 23:59:59 | Bỏ phần lẻ của giây | Lấy đầu ngày kế tiếp làm cận loại trừ |
| Cộng cố định 24 giờ cho mọi ngày | Sai khi offset thay đổi | Tính từ ngày lịch kế tiếp và vùng |
| Java và SQL dùng hai quy ước khác nhau | Kết quả kiểm tra không nhất quán | Công bố và kiểm chứng cùng hợp đồng |

## 11. Thực hành có kết quả mong đợi

### Bài 1: Điểm ranh giới của hai phiên bản

A có khoảng `[09:00, 10:00)`, B có khoảng `[10:00, 11:00)`.

- Đúng 10:00: A không có hiệu lực, B có hiệu lực.
- Hai khoảng không chồng lấn.
- Không cần trừ một mili giây từ cận cuối A.

### Bài 2: Tìm phần giao

A là `[09:00, 10:00)`, B là `[09:30, 11:00)`.

Phần giao phải là `[09:30, 10:00)`. Đúng 10:00 không thuộc phần giao.

### Bài 3: Khoảng không hợp lệ

Tạo khoảng có hai cận đều là 09:00. Theo hợp đồng của chương trình, thao tác phải báo lỗi. Giải thích khác biệt giữa “khoảng rỗng có thể định nghĩa về toán học” và “khoảng hiệu lực được mô hình này chấp nhận”.

### Bài 4: Bộ lọc một ngày

Người dùng chọn chỉ ngày 1/5/2024. Cận cuối phải là đầu ngày 2/5/2024 theo vùng đã chọn. Sự kiện đúng cận cuối không được tính vào ngày 1/5.

### Bài 5: Hạn không giới hạn

Thiết kế một mô hình cho phép không có cận cuối. Nêu rõ cách chứa một thời điểm, chồng lấn và biểu diễn dữ liệu thiếu. Không chỉ truyền `null` vào `Window` hiện có rồi mong các phương thức tự hiểu.

Một khoảng nửa mở đúng cần ba điều nhất quán: cận đầu được bao gồm, cận cuối bị loại trừ và mọi lớp xử lý cùng dùng ý nghĩa đó. Các ca kiểm tra tại đúng ranh giới là bằng chứng quan trọng nhất.
