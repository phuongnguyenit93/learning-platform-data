# Mô hình hóa khoảng thời gian và quy tắc biên đóng hoặc mở

Trong mô hình miền, thời gian thường không chỉ là một timestamp đơn lẻ. Nhiều khái niệm nghiệp vụ tồn tại trong một khoảng: thời hạn giữ hàng, thời gian hiệu lực của hợp đồng, kỳ tính phí, khung giờ đặt lịch, thời gian bảo hành hoặc giai đoạn một chính sách được áp dụng. Để biểu diễn đúng các khái niệm này, cần xác định rõ điểm bắt đầu, điểm kết thúc và việc hai đầu mút có thuộc khoảng hay không.

Một khoảng thời gian có thể đóng ở đầu mút, mở ở đầu mút hoặc kết hợp cả hai. Ví dụ `[09:00, 10:00)` bao gồm 09:00 nhưng không bao gồm 10:00. Quy ước nửa mở này thường thuận tiện cho các khoảng liên tiếp: khoảng đầu kết thúc đúng lúc khoảng sau bắt đầu mà không bị tính trùng thời điểm.

Trong Domain-Driven Design (DDD), cách biểu diễn khoảng thời gian nên được đóng gói thành Value Object có ngữ nghĩa rõ, bảo vệ invariant và cung cấp các phép toán như kiểm tra chứa, giao nhau, liền kề và tính thời lượng. Bài học này trình bày các loại biên, cách chọn quy ước, cách dùng Java Time, cách lưu trữ và truy vấn, cùng các tình huống dễ gây lỗi khi xử lý lịch, múi giờ và dữ liệu lịch sử.

## 1. Khoảng thời gian là một khái niệm miền

Một khoảng thời gian mô tả tập hợp các thời điểm hoặc ngày nằm giữa hai đầu mút theo một quy tắc xác định. Nó thường có:

- **Start (đầu bắt đầu):** thời điểm hoặc ngày bắt đầu.
- **End (đầu kết thúc):** thời điểm hoặc ngày kết thúc.
- **Boundary semantics:** mỗi đầu mút được bao gồm hay loại trừ.
- **Temporal domain:** giá trị đang được xét là ngày lịch, thời điểm tuyệt đối hay giờ địa phương.
- **Business meaning:** khoảng đó đại diện cho hiệu lực, thời hạn, lịch hẹn hay một giai đoạn khác.

Ví dụ:

- Hợp đồng có hiệu lực từ ngày 01/01 đến hết ngày 31/12.
- Một phòng được đặt từ 14:00 đến 15:00.
- Reservation có hiệu lực trong 15 phút kể từ thời điểm tạo.
- Giá khuyến mãi được áp dụng trong một kỳ xác định.
- Một nhân viên thuộc một phòng ban trong giai đoạn từ ngày A đến ngày B.

Không nên chỉ lưu hai timestamp rồi để mỗi nơi tự suy đoán cách hiểu. Cùng một cặp giá trị `start` và `end` có thể biểu diễn các tập thời gian khác nhau tùy biên đóng/mở.

## 2. Biên đóng và biên mở

Ký hiệu toán học giúp diễn đạt rõ đầu mút có được bao gồm hay không.

| Loại khoảng | Ký hiệu | Ý nghĩa |
|---|---|---|
| Đóng cả hai đầu | `[a, b]` | Bao gồm cả `a` và `b` |
| Mở cả hai đầu | `(a, b)` | Không bao gồm `a` và `b` |
| Đóng trái, mở phải | `[a, b)` | Bao gồm `a`, loại trừ `b` |
| Mở trái, đóng phải | `(a, b]` | Loại trừ `a`, bao gồm `b` |

Ví dụ với khoảng `[09:00, 10:00)`:

- 09:00 thuộc khoảng.
- 09:30 thuộc khoảng.
- 10:00 không thuộc khoảng.
- 10:00 có thể thuộc khoảng kế tiếp `[10:00, 11:00)`.

Đầu mút đóng thường được gọi là inclusive; đầu mút mở là exclusive. Khi đặt tên thuộc tính hoặc method trong code/API, nên thể hiện rõ ngữ nghĩa như `startInclusive`, `endExclusive`, `contains`, thay vì dùng tên mơ hồ `from` và `to` nếu người đọc không biết quy ước.

### 2.1. Vì sao biên phải được xác định rõ?

Nếu một hợp đồng kết thúc lúc 00:00 ngày 01/07, câu “có hiệu lực đến ngày 30/06” có thể tương ứng với thời điểm kết thúc loại trừ 00:00 ngày 01/07. Nếu hiểu end là inclusive, cùng giá trị timestamp có thể được diễn giải khác.

Sai lệch ở biên có thể gây:

- Tính phí thêm hoặc thiếu một ngày.
- Hai lịch hẹn cùng chiếm một thời điểm.
- Một reservation hết hạn sớm hoặc muộn hơn chính sách.
- Hai phiên bản chính sách cùng có hiệu lực tại một thời điểm.
- Bỏ sót hoặc tính trùng giao dịch đúng tại mốc chuyển kỳ.

Vì vậy, quy tắc biên là một phần của ngôn ngữ nghiệp vụ và hợp đồng dữ liệu, không chỉ là chi tiết code.

## 3. Quy ước nửa mở `[start, end)`

Khoảng đóng trái, mở phải thường là lựa chọn mặc định hữu ích cho dữ liệu thời gian liên tục và các kỳ liên tiếp.

Một khoảng `[start, end)` có các đặc điểm:

- `start` được bao gồm.
- `end` không được bao gồm.
- Độ dài thời gian là `end - start`.
- Hai khoảng `[a, b)` và `[b, c)` không giao nhau.
- Hợp của hai khoảng liền kề là `[a, c)`.
- Một thời điểm đúng tại `b` thuộc khoảng thứ hai, không thuộc khoảng thứ nhất.

Ví dụ:

```text
[09:00, 10:00)  [10:00, 11:00)
|--------------)|--------------)
09:00          10:00          11:00
```

Không có khoảng trống giữa hai đoạn và cũng không có thời điểm bị tính hai lần. Đây là lý do quy ước nửa mở thường được dùng cho time slot, kỳ báo cáo và khoảng hiệu lực.

### 3.1. Kiểm tra thuộc khoảng

Với `[start, end)`, một thời điểm `t` thuộc khoảng khi:

\[
start \leq t < end
\]

Nếu dùng khoảng đóng cả hai đầu, điều kiện sẽ là `start <= t && t <= end`. Nếu dùng khoảng mở cả hai đầu, điều kiện là `start < t && t < end`. Không nên dùng cùng một method `contains` cho nhiều quy ước mà không lưu hoặc biết rõ loại biên.

### 3.2. Không dùng “trừ một đơn vị nhỏ nhất” để tạo biên đóng

Một cách làm dễ sai là biến `[start, end]` thành `[start, end + 1 millisecond)` hoặc trừ một nano giây khỏi end. Cách này phụ thuộc độ chính xác của hệ thống, kiểu dữ liệu và database. Có thể thất bại khi độ chính xác timestamp khác nhau hoặc khi miền thời gian không có đơn vị nhỏ nhất chung.

Hãy biểu diễn trực tiếp quy tắc biên. Nếu nghiệp vụ nói “đến hết ngày 30/06”, với ngày lịch có thể chuyển thành khoảng từ đầu ngày 30/06 đến đầu ngày 01/07 theo múi giờ nghiệp vụ, dùng end-exclusive.

## 4. Chọn temporal type đúng với ý nghĩa

Java cung cấp nhiều kiểu thời gian. Không nên dùng `java.util.Date`, `LocalDateTime` hoặc epoch milliseconds cho mọi tình huống.

| Kiểu Java | Biểu diễn | Dùng khi |
|---|---|---|
| `Instant` | Một thời điểm trên timeline UTC | Timestamp sự kiện, thời điểm commit, deadline tuyệt đối |
| `LocalDate` | Ngày lịch không kèm giờ/múi giờ | Ngày sinh, ngày hiệu lực theo lịch, kỳ theo ngày |
| `LocalTime` | Giờ trong ngày không có ngày/múi giờ | Giờ mở cửa, giờ bắt đầu ca lặp hằng ngày |
| `LocalDateTime` | Ngày và giờ địa phương, không có zone | Giá trị lịch địa phương cần được diễn giải cùng một ZoneId ở nơi khác |
| `ZonedDateTime` | Ngày giờ cùng múi giờ | Quy tắc lịch địa phương gắn với vùng địa lý |
| `OffsetDateTime` | Ngày giờ cùng UTC offset | Trao đổi timestamp có offset trong API |
| `Duration` | Độ dài thời gian theo giây/nanosecond | Timeout, thời gian giữ 15 phút, thời lượng chính xác |
| `Period` | Khoảng thời gian theo năm/tháng/ngày lịch | Một tháng hợp đồng, một năm bảo hành theo lịch |

`Instant` phù hợp với một thời điểm tuyệt đối. `LocalDate` phù hợp với ngày lịch. `LocalDateTime` không tự xác định được một thời điểm duy nhất nếu thiếu múi giờ hoặc offset.

### 4.1. Ngày lịch khác với 24 giờ

“Một ngày” theo lịch không phải lúc nào cũng bằng 24 giờ. Khi chuyển sang hoặc ra khỏi giờ mùa hè (DST), một ngày địa phương có thể dài 23 hoặc 25 giờ. Vì vậy:

- “Giữ hàng trong 24 giờ” thường là `Duration.ofHours(24)` trên timeline.
- “Giữ đến cùng giờ ngày mai theo giờ địa phương” là phép tính lịch theo `ZonedDateTime` và `ZoneId`.
- “Có hiệu lực đến hết ngày 30/06” là quy tắc ngày lịch, cần chuyển ranh giới theo múi giờ xác định.

Không thay thế `Period.ofDays(1)` và `Duration.ofHours(24)` một cách tùy tiện; chúng thể hiện ý nghĩa khác nhau.

## 5. Thiết kế Value Object cho khoảng thời gian

Trong DDD, khoảng thời gian thường phù hợp với Value Object vì nó được xác định bởi các đầu mút và quy tắc biên, không cần identity riêng. Có thể đặt tên theo ngữ nghĩa miền như `ValidityPeriod`, `ReservationWindow`, `BookingInterval` hoặc `EmploymentPeriod` thay vì luôn dùng tên kỹ thuật chung `DateRange`.

Một Value Object tốt nên:

- Bất biến sau khi tạo.
- Kiểm tra invariant của hai đầu mút.
- Nêu rõ loại biên.
- Cung cấp các phép toán có ngữ nghĩa thống nhất.
- Dùng đúng temporal type.
- Không tự suy đoán múi giờ hoặc độ chính xác.

### 5.1. Ví dụ `InstantRange` nửa mở trong Java

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public record InstantRange(Instant startInclusive, Instant endExclusive) {
    public InstantRange {
        Objects.requireNonNull(startInclusive, "startInclusive");
        Objects.requireNonNull(endExclusive, "endExclusive");

        if (endExclusive.isBefore(startInclusive)) {
            throw new IllegalArgumentException("End must not be before start");
        }
    }

    public boolean contains(Instant instant) {
        Objects.requireNonNull(instant, "instant");
        return !instant.isBefore(startInclusive)
                && instant.isBefore(endExclusive);
    }

    public boolean isEmpty() {
        return startInclusive.equals(endExclusive);
    }

    public Duration duration() {
        return Duration.between(startInclusive, endExclusive);
    }

    public boolean overlaps(InstantRange other) {
        Objects.requireNonNull(other, "other");
        return startInclusive.isBefore(other.endExclusive)
                && other.startInclusive.isBefore(endExclusive);
    }
}
```

Ví dụ cho phép khoảng rỗng khi `startInclusive == endExclusive`, nhưng không cho phép end trước start. Một khoảng rỗng không chứa thời điểm nào và có duration bằng zero. Nếu nghiệp vụ như reservation hoặc booking bắt buộc khoảng phải có độ dài dương, hãy siết invariant thành `endExclusive.isAfter(startInclusive)` hoặc dùng factory/Value Object chuyên biệt.

### 5.2. Vì sao không cho phép sửa start/end?

Value Object bất biến giúp hai đầu mút luôn được kiểm tra cùng nhau. Nếu thay start mà quên thay end, có thể tạo khoảng có thứ tự sai hoặc thời lượng không hợp lệ. Khi thay đổi, tạo một `InstantRange` mới và thay giá trị tại Entity/Aggregate sở hữu nó.

## 6. Giao nhau, liền kề và giao của hai khoảng

Với hai khoảng nửa mở:

\[
A = [a_s, a_e), \quad B = [b_s, b_e)
\]

Chúng giao nhau khi:

\[
a_s < b_e \quad \land \quad b_s < a_e
\]

Điều kiện dùng so sánh nghiêm ngặt (`<`) vì đầu kết thúc bị loại trừ. Nếu `a_e == b_s`, hai khoảng liền kề nhưng không giao nhau.

### 6.1. Ví dụ

| Khoảng A | Khoảng B | Kết quả |
|---|---|---|
| `[09:00, 10:00)` | `[09:30, 10:30)` | Giao nhau |
| `[09:00, 10:00)` | `[10:00, 11:00)` | Liền kề, không giao nhau |
| `[09:00, 10:00)` | `[10:01, 11:00)` | Tách rời, có khoảng trống |
| `[09:00, 10:00)` | `[08:00, 09:00)` | Liền kề ở đầu trái, không giao nhau |
| `[09:00, 10:00)` | `[09:00, 10:00)` | Trùng hoàn toàn, có giao nhau |

### 6.2. Tính khoảng giao

Khoảng giao của hai khoảng nửa mở có:

\[
start = \max(a_s, b_s), \quad end = \min(a_e, b_e)
\]

Nếu `start < end`, giao là `[start, end)`. Nếu `start == end`, giao rỗng. Nếu `start > end`, hai khoảng không giao nhau.

```java
public java.util.Optional<InstantRange> intersection(InstantRange other) {
    Instant start = startInclusive.isAfter(other.startInclusive)
            ? startInclusive : other.startInclusive;
    Instant end = endExclusive.isBefore(other.endExclusive)
            ? endExclusive : other.endExclusive;

    if (!start.isBefore(end)) {
        return java.util.Optional.empty();
    }
    return java.util.Optional.of(new InstantRange(start, end));
}
```

Với khoảng nửa mở, hai đoạn chỉ chạm ở một đầu mút không có thời điểm chung. Vì vậy, method trả `Optional.empty()` khi `start >= end`; khoảng giao chỉ được tạo khi có độ dài dương.

### 6.3. Kiểm tra liền kề

Hai khoảng nửa mở liền kề nếu:

\[
a_e = b_s \quad \lor \quad b_e = a_s
\]

Liền kề không có nghĩa giao nhau. Điều này quan trọng khi ghép các ca làm việc hoặc các phiên bản chính sách liên tục.

## 7. Quy tắc biên cho ngày lịch

Với kỳ theo ngày, quy ước nửa mở cũng thường hữu ích. Một kỳ “từ ngày 01/01 đến hết ngày 31/01” có thể biểu diễn bằng:

\[
[2026\text{-}01\text{-}01,\ 2026\text{-}02\text{-}01)
\]

trên miền `LocalDate`.

Ví dụ Java:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate startInclusive, LocalDate endExclusive) {
    public DateRange {
        Objects.requireNonNull(startInclusive, "startInclusive");
        Objects.requireNonNull(endExclusive, "endExclusive");
        if (endExclusive.isBefore(startInclusive)) {
            throw new IllegalArgumentException("Invalid date range");
        }
    }

    public boolean contains(LocalDate date) {
        return !date.isBefore(startInclusive) && date.isBefore(endExclusive);
    }
}
```

Nếu API nhận ngày kết thúc theo nghĩa “bao gồm ngày cuối”, application boundary có thể chuyển thành `endDate.plusDays(1)` để tạo `endExclusive`, nhưng phải làm rõ đây là ngày lịch và kiểm tra giới hạn kiểu dữ liệu. Không áp dụng cách cộng một ngày cho timestamp hoặc cho một deadline tính bằng giờ.

### 7.1. Ví dụ tính ngày cuối

Người dùng chọn từ ngày 01/06 đến hết ngày 30/06. Date range nội bộ có thể là `[2026-06-01, 2026-07-01)`. Điều kiện chọn ngày là:

\[
2026\text{-}06\text{-}01 \leq date < 2026\text{-}07\text{-}01
\]

Không cần giả lập thời điểm cuối ngày là `23:59:59.999999999`. Cách đó phụ thuộc độ chính xác timestamp và dễ bỏ sót dữ liệu có độ chính xác cao hơn.

## 8. Ngày giờ địa phương và múi giờ

Một khung giờ như “từ 09:00 đến 17:00 tại TP. Hồ Chí Minh” cần gắn với ngày và múi giờ nếu muốn chuyển thành thời điểm tuyệt đối. `LocalTime` đơn lẻ không đủ để xác định một interval trên timeline.

Ví dụ chuyển ngày giờ địa phương sang `Instant`:

```java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 6, 30);

ZonedDateTime localStart = date.atTime(LocalTime.of(9, 0)).atZone(zone);
ZonedDateTime localEnd = date.atTime(LocalTime.of(17, 0)).atZone(zone);

InstantRange range = new InstantRange(
        localStart.toInstant(),
        localEnd.toInstant()
);
```

Ở đây `ZoneId` làm rõ cách diễn giải giờ địa phương. Khi dùng vùng có DST, một `LocalDateTime` có thể rơi vào khoảng giờ không tồn tại hoặc giờ xuất hiện hai lần. API phải định nghĩa cách xử lý gap/overlap: từ chối, chọn offset sớm/muộn hay áp dụng chính sách lịch cụ thể.

### 8.1. Không hard-code offset thay cho ZoneId

`+07:00` chỉ là một offset cố định. `Asia/Ho_Chi_Minh` là một vùng múi giờ có quy tắc lịch sử và có thể thay đổi theo luật. Với lịch gắn với địa điểm, nên lưu ZoneId khi cần tái diễn giải quy tắc địa phương trong tương lai.

### 8.2. Lưu cả ý định lịch và thời điểm đã xác định khi cần

Một cuộc hẹn tương lai “09:00 giờ địa phương vào ngày X” có thể cần lưu `LocalDate`, `LocalTime` và `ZoneId`, vì luật múi giờ có thể thay đổi trước ngày hẹn. Một giao dịch đã xảy ra cần lưu `Instant` để giữ thời điểm tuyệt đối. Hai loại thông tin phục vụ mục đích khác nhau.

## 9. Khoảng thời gian không giới hạn một đầu

Một số khái niệm có thể không có điểm kết thúc xác định:

- Một mức giá có hiệu lực từ ngày bắt đầu cho đến khi bị thay thế.
- Một quan hệ lao động có hiệu lực từ ngày vào làm và chưa có ngày kết thúc.
- Một chính sách hiện hành chưa có ngày hết hiệu lực.

Có thể biểu diễn đầu mút mở vô hạn bằng `Optional<Instant>` hoặc một kiểu rõ nghĩa như `Bound`/`Unbounded`. Không nên dùng một timestamp giả như `9999-12-31` nếu nó không có ý nghĩa nghiệp vụ và có thể gây lỗi khi tính toán.

Ví dụ:

```java
public record EffectivePeriod(
        java.time.Instant startInclusive,
        java.util.Optional<java.time.Instant> endExclusive
) {
    public EffectivePeriod {
        java.util.Objects.requireNonNull(startInclusive);
        java.util.Objects.requireNonNull(endExclusive);
        endExclusive.ifPresent(end -> {
            if (end.isBefore(startInclusive)) {
                throw new IllegalArgumentException("End before start");
            }
        });
    }

    public boolean contains(java.time.Instant instant) {
        return !instant.isBefore(startInclusive)
                && endExclusive.map(instant::isBefore).orElse(true);
    }
}
```

Nếu nghiệp vụ cũng cho phép không có đầu bắt đầu (vô hiệu lực từ quá khứ), cần mô hình hóa riêng. Tránh dùng `null` tùy tiện vì nó không cho biết đầu mút nào là unbounded và cách so sánh ra sao.

## 10. Khoảng rỗng và khoảng không hợp lệ

Hai khái niệm này cần được phân biệt:

- **Khoảng rỗng:** hai đầu mút bằng nhau trong quy ước nửa mở `[a, a)`, không chứa thời điểm nào và có độ dài zero.
- **Khoảng không hợp lệ:** end nằm trước start, trái với invariant thứ tự.

Một số domain cho phép khoảng rỗng để biểu diễn kết quả giao hoặc truy vấn không có dữ liệu. Domain khác yêu cầu một reservation, ca làm việc hoặc kỳ hợp đồng phải có độ dài dương. Không có quy tắc chung cho mọi loại interval.

Nên chọn theo ngữ nghĩa:

- `SearchWindow` có thể cho phép rỗng.
- `BookingPeriod` thường yêu cầu độ dài dương.
- `ValidityPeriod` có thể cho phép end bằng start nếu nghiệp vụ định nghĩa đó là một phiên bản không có hiệu lực, hoặc có thể từ chối.

Không nên dùng cùng một Value Object chung nếu các loại khoảng có invariant khác nhau đáng kể. Có thể dùng một primitive interval bên dưới nhưng expose các kiểu miền có tên riêng.

## 11. Tính thời lượng: Duration và Period

Với hai `Instant`, `Duration.between(start, end)` tính thời lượng chính xác trên timeline. Với hai `LocalDate`, `Period.between(start, end)` diễn đạt chênh lệch theo năm/tháng/ngày lịch.

Ví dụ:

```java
Duration elapsed = Duration.between(startInstant, endInstant);
Period calendarDifference = Period.between(startDate, endDate);
```

Không nên dùng `Duration.ofDays(30)` để đại diện cho “một tháng” nếu chính sách nói theo tháng lịch. Một tháng có thể có 28, 29, 30 hoặc 31 ngày. Tương tự, “một năm” theo lịch không luôn bằng 365 ngày.

Khi tính thời lượng của interval, hãy xác định có tính đầu cuối hay không. Với `[start, end)`, độ dài là `end - start`, không cộng thêm một đơn vị. Với ngày lịch bao gồm cả ngày cuối, chuyển về end-exclusive trước khi tính số ngày để tránh sai lệch.

## 12. Truy vấn khoảng thời gian trong database

Nếu cột thời gian lưu `start_at` và `end_at` theo quy ước `[start, end)`, truy vấn hai khoảng có giao nhau thường dùng:

```sql
SELECT *
FROM booking
WHERE start_at < :query_end_exclusive
  AND end_at > :query_start_inclusive;
```

Điều kiện tương ứng với:

\[
booking.start < query.end \quad \land \quad query.start < booking.end
\]

Vì end-exclusive, hai booking chạm nhau đúng tại đầu mút không được xem là overlap.

### 12.1. Truy vấn các khoảng chứa một thời điểm

```sql
SELECT *
FROM price_period
WHERE valid_from <= :instant
  AND :instant < valid_until;
```

Nếu `valid_until` có thể không giới hạn, cần diễn đạt rõ:

```sql
WHERE valid_from <= :instant
  AND (valid_until IS NULL OR :instant < valid_until)
```

Không nên dùng `BETWEEN` một cách máy móc vì SQL `BETWEEN` thường bao gồm cả hai đầu, khác với khoảng `[start, end)`.

### 12.2. Ràng buộc không cho phép khoảng sai

Có thể thêm constraint ở database:

```sql
CHECK (end_at >= start_at)
```

Nếu domain không cho phép khoảng rỗng, dùng `end_at > start_at`. Constraint bảo vệ dữ liệu ở storage, còn Value Object vẫn cần kiểm tra và cung cấp lỗi có ý nghĩa nghiệp vụ.

### 12.3. Ngăn các khoảng đặt lịch bị chồng lấn

Một quy tắc đặt lịch có thể yêu cầu không có hai booking active của cùng một tài nguyên bị overlap. Chỉ kiểm tra trong application rồi insert có thể bị race khi hai request đồng thời.

Cần cơ chế bảo vệ ở database hoặc transaction phù hợp, chẳng hạn exclusion constraint trên range type trong PostgreSQL, locking theo tài nguyên, hoặc một thiết kế cập nhật nguyên tử có kiểm soát. Ví dụ PostgreSQL với range type:

```sql
-- Ý tưởng minh họa: tên bảng, trạng thái và kiểu range tùy schema.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE booking
ADD CONSTRAINT no_overlapping_active_booking
EXCLUDE USING gist (
    resource_id WITH =,
    tstzrange(start_at, end_at, '[)') WITH &&
)
WHERE (status = 'ACTIVE');
```

`[)` thể hiện biên đóng trái, mở phải; toán tử `&&` kiểm tra overlap. Đây là cú pháp PostgreSQL-specific, cần kiểm tra kiểu dữ liệu, index và điều kiện thực tế của hệ thống. Không phải database nào cũng có range type hoặc exclusion constraint tương đương.

## 13. Mô hình hóa hiệu lực và lịch sử

Khoảng thời gian thường được dùng để mô hình hóa khi nào một sự thật nghiệp vụ có hiệu lực. Ví dụ một mức giá có hiệu lực trong một giai đoạn, hoặc một nhân viên thuộc phòng ban trong một khoảng.

### 13.1. Valid Time và Transaction Time

Trong mô hình lịch sử, cần phân biệt:

- **Valid time:** khoảng thời gian sự thật có hiệu lực trong thế giới nghiệp vụ.
- **Transaction time:** khoảng thời gian thông tin đó được lưu/biết trong hệ thống.

Ví dụ: ngày 10/06 hệ thống nhận được thông tin rằng mức giá mới thực tế có hiệu lực từ 01/06. Valid time bắt đầu 01/06; transaction time bắt đầu khi thông tin được ghi nhận ngày 10/06.

Hai trục thời gian trả lời hai câu hỏi khác nhau:

- “Giá nào có hiệu lực vào ngày 05/06?” — valid time.
- “Vào ngày 07/06, hệ thống đang biết giá nào?” — transaction time.

Nếu nghiệp vụ cần audit hoặc tái dựng quyết định lịch sử, có thể cần lưu cả hai. Không nên dùng một `createdAt` để thay thế valid time.

### 13.2. Phiên bản hiệu lực liền kề

Giả sử một chính sách có các phiên bản:

```text
Version 1: [2026-01-01, 2026-04-01)
Version 2: [2026-04-01, 2026-07-01)
Version 3: [2026-07-01, infinity)
```

Tại đúng 01/04, Version 1 không còn hiệu lực và Version 2 bắt đầu. Quy ước nửa mở giúp tránh thời điểm một chính sách vừa thuộc hai phiên bản.

Nếu cần giữ lịch sử thông tin mà người dùng đã biết tại từng thời điểm, hãy thêm transaction-time hoặc audit history thay vì ghi đè phiên bản cũ.

## 14. Khoảng thời gian trong API và hợp đồng tích hợp

API cần mô tả rõ:

- Định dạng timestamp, ví dụ ISO-8601.
- Có yêu cầu `Z` hoặc offset không.
- Múi giờ nào được dùng khi nhận ngày giờ địa phương.
- Đầu mút có inclusive hay exclusive.
- `end` có thể null/unbounded không.
- Khoảng rỗng có được chấp nhận không.
- Độ chính xác được hỗ trợ (seconds, milliseconds, microseconds...).

Ví dụ payload rõ nghĩa:

```json
{
  "startInclusive": "2026-06-30T09:00:00+07:00",
  "endExclusive": "2026-06-30T17:00:00+07:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

Nếu API chỉ truyền `from` và `to`, tài liệu cần nói rõ biên. Không nên để mỗi consumer tự chọn inclusive/exclusive.

Đối với ngày lịch, có thể dùng:

```json
{
  "startDateInclusive": "2026-06-01",
  "endDateExclusive": "2026-07-01"
}
```

Nếu giao diện cho phép người dùng chọn ngày cuối inclusive, adapter chuyển đổi theo quy tắc ngày lịch trước khi gọi domain. Không nên bắt consumer gửi `23:59:59.999` để biểu diễn hết ngày.

## 15. Độ chính xác và chuẩn hóa thời gian

Các hệ thống có thể hỗ trợ độ chính xác khác nhau: giây, milliseconds, microseconds hoặc nanoseconds. Nếu application dùng nanoseconds nhưng database chỉ lưu microseconds, hai timestamp khác nhau trong Java có thể trở thành cùng một giá trị khi persist.

Cần xác định:

- Độ chính xác chuẩn của domain/API.
- Cách làm tròn hoặc truncate khi lưu.
- Việc chuẩn hóa UTC có được áp dụng không.
- Equality có so sánh chính xác từng nano giây hay theo độ chính xác nghiệp vụ.
- Mọi adapter có cùng quy tắc chuyển đổi không.

Không nên tự ý làm tròn thời gian trong domain nếu nó có thể làm thay đổi quyết định tại biên. Nếu hệ thống chỉ hỗ trợ milliseconds, hãy chuẩn hóa ở boundary và dùng cùng độ chính xác cho so sánh, lưu trữ và kiểm thử.

## 16. Các lỗi thường gặp khi mô hình hóa khoảng

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Không ghi rõ biên inclusive/exclusive | Hai module hiểu khác nhau tại đầu mút | Dùng tên rõ như `startInclusive`/`endExclusive` |
| Dùng khoảng đóng cả hai đầu cho các kỳ liền kề | Dễ tính trùng thời điểm/ngày | Cân nhắc `[start, end)` |
| Trừ một millisecond/nanosecond để tạo cuối khoảng | Phụ thuộc precision và storage | Dùng end-exclusive trực tiếp |
| Dùng `LocalDateTime` như thời điểm tuyệt đối | Không xác định được instant nếu thiếu zone | Dùng `Instant` hoặc kèm `ZoneId` rõ ràng |
| Xem một ngày luôn là 24 giờ | Sai khi có DST hoặc quy tắc lịch | Phân biệt `Duration` và `Period` |
| Dùng `BETWEEN` cho interval nửa mở | SQL bao gồm cả hai đầu | Viết điều kiện `< end` và `>= start` rõ |
| Chỉ kiểm tra overlap trong Java | Race condition khi đặt lịch đồng thời | Constraint/locking/transaction phù hợp |
| Dùng null không có ngữ nghĩa | Không rõ end vô hạn hay dữ liệu thiếu | Dùng Optional/kiểu bound và contract rõ |
| Cho phép khoảng rỗng ngoài ý muốn | Reservation hoặc booking có thời lượng zero | Đặt invariant theo từng loại khoảng |
| Dùng một kiểu range cho mọi nghiệp vụ | Ngữ nghĩa hiệu lực, booking và kỳ tính phí bị trộn | Tạo Value Object có tên miền phù hợp |
| Bỏ qua valid time và transaction time | Không tái dựng được lịch sử đã biết | Lưu hai trục khi nghiệp vụ cần audit |

## 17. Kiểm thử Value Object khoảng thời gian

Kiểm thử nên tập trung vào các trường hợp biên vì lỗi interval thường xuất hiện đúng tại start hoặc end.

### 17.1. Kiểm tra contains

```java
@Test
void containsUsesInclusiveStartAndExclusiveEnd() {
    Instant start = Instant.parse("2026-06-30T02:00:00Z");
    Instant end = Instant.parse("2026-06-30T03:00:00Z");
    InstantRange range = new InstantRange(start, end);

    assertTrue(range.contains(start));
    assertTrue(range.contains(start.plusSeconds(1)));
    assertFalse(range.contains(end));
}
```

### 17.2. Kiểm tra overlap và adjacency

```java
@Test
void adjacentHalfOpenRangesDoNotOverlap() {
    Instant a = Instant.parse("2026-06-30T09:00:00Z");
    Instant b = Instant.parse("2026-06-30T10:00:00Z");
    Instant c = Instant.parse("2026-06-30T11:00:00Z");

    InstantRange first = new InstantRange(a, b);
    InstantRange second = new InstantRange(b, c);

    assertFalse(first.overlaps(second));
}
```

### 17.3. Kiểm tra invariant

- End trước start phải bị từ chối.
- Khoảng rỗng được chấp nhận hay không theo contract.
- Null đầu mút phải bị từ chối hoặc được biểu diễn bằng kiểu unbounded rõ ràng.
- Các phép giao, hợp và liền kề phải tuân theo cùng quy ước biên.
- Date range chuyển từ inclusive end sang exclusive end phải đúng qua tháng 2 và năm nhuận.
- Chuyển ngày giờ địa phương qua DST phải theo chính sách đã chọn.

### 17.4. Kiểm thử truy vấn database

Không chỉ test Value Object trong bộ nhớ. Cần integration test để xác minh SQL overlap, constraint chống booking trùng và độ chính xác timestamp trên database thực tế. Đặc biệt kiểm tra hai transaction đồng thời cùng đặt một tài nguyên trong các khoảng giao nhau.

## 18. Checklist thiết kế khoảng thời gian

- [ ] Đã xác định temporal domain: ngày lịch, giờ địa phương hay instant.
- [ ] Ý nghĩa nghiệp vụ của start và end được định nghĩa.
- [ ] Biên inclusive/exclusive được ghi rõ trong tên và contract.
- [ ] Đã cân nhắc quy ước `[start, end)` cho các kỳ liên tiếp.
- [ ] Invariant thứ tự và quy tắc khoảng rỗng đã được xác định.
- [ ] Unbounded endpoint được mô hình hóa rõ, không dùng timestamp giả.
- [ ] Múi giờ được chỉ định khi chuyển giờ địa phương thành instant.
- [ ] Phân biệt thời lượng tuyệt đối với khoảng lịch (`Duration`/`Period`).
- [ ] Độ chính xác timestamp thống nhất giữa application và database.
- [ ] Query overlap và containment dùng đúng toán tử cho biên.
- [ ] Quy tắc không chồng lấn được bảo vệ khi có giao dịch đồng thời.
- [ ] Valid time và transaction time được tách nếu cần lịch sử/audit.
- [ ] Có test cho start, end, adjacency, empty, overlap và timezone.

## 19. Kết nối với các khái niệm DDD khác

Khoảng thời gian thường là Value Object vì nó được xác định bởi các đầu mút và quy tắc biên. Entity hoặc Aggregate có thể sở hữu một hoặc nhiều khoảng như thời hạn hợp đồng, reservation hoặc giai đoạn hiệu lực. Aggregate Root bảo vệ invariant như không cho hai booking active của cùng tài nguyên bị chồng lấn; Repository truy vấn theo khoảng; Domain Event có thể ghi nhận một hiệu lực bắt đầu, kết thúc hoặc thay đổi.

Khi mô hình hóa lịch sử, cần phân biệt thời điểm sự kiện được ghi nhận với khoảng thời gian sự thật có hiệu lực. Khi tích hợp giữa bounded context, Published Language phải truyền rõ kiểu thời gian, múi giờ và quy tắc biên để các bên không diễn giải khác nhau.

Mô hình hóa khoảng thời gian đúng không chỉ là chọn hai field `start` và `end`. Nó là quyết định ngữ nghĩa về tập thời điểm được bao gồm, cách tính thời lượng, múi giờ, precision và cách xử lý giao dịch đồng thời. Một Value Object có tên rõ và quy tắc biên nhất quán giúp các quyết định nghiệp vụ về hiệu lực, đặt lịch và lịch sử trở nên chính xác, dễ kiểm thử và dễ trao đổi giữa các context.
