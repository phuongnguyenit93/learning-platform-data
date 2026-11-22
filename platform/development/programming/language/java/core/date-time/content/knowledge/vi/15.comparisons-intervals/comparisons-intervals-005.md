# Quy ước khoảng đóng, khoảng mở và khoảng nửa mở trong Java date-time

Khi mô tả một khoảng thời gian, cần xác định rõ **đầu mút nào được tính vào khoảng**. Hai khoảng có cùng giá trị bắt đầu và kết thúc nhưng dùng quy ước khác nhau có thể chứa những thời điểm khác nhau. Quy ước này ảnh hưởng đến điều kiện kiểm tra, ghép các khoảng liên tiếp, phát hiện giao nhau, truy vấn cơ sở dữ liệu và tránh đếm trùng sự kiện ở ranh giới.

Trong toán học:

- **Khoảng đóng** `[a, b]`: bao gồm cả điểm đầu `a` và điểm cuối `b`.
- **Khoảng mở** `(a, b)`: loại cả hai đầu mút.
- **Nửa mở phải đóng** `(a, b]`: loại `a`, bao gồm `b`.
- **Nửa mở trái đóng phải** `[a, b)`: bao gồm `a`, loại `b`.

Trong phần mềm, quy ước **`[start, end)` — đầu bao gồm, cuối loại trừ** thường là lựa chọn tiện lợi. Thời điểm bắt đầu được tính, thời điểm kết thúc thuộc khoảng kế tiếp (nếu có), không thuộc khoảng hiện tại.

## 1. Điều kiện xác định phần tử thuộc khoảng

| Ký hiệu | Đầu | Cuối | Điều kiện với thời điểm `t` |
| --- | --- | --- | --- |
| `[a, b]` | Bao gồm | Bao gồm | `a <= t && t <= b` |
| `(a, b)` | Loại trừ | Loại trừ | `a < t && t < b` |
| `(a, b]` | Loại trừ | Bao gồm | `a < t && t <= b` |
| `[a, b)` | Bao gồm | Loại trừ | `a <= t && t < b` |

Các toán tử trong bảng diễn tả khái niệm. Với các kiểu Java như `Instant`, `LocalDateTime` hay `LocalDate`, hãy dùng `isBefore`, `isAfter`, `equals` hoặc `compareTo` để so sánh.

Ví dụ khoảng `[09:00, 10:00)` chứa đúng 09:00, nhưng không chứa 10:00. Khi ghép khoảng kế tiếp `[10:00, 11:00)`, thời điểm 10:00 chỉ thuộc khoảng sau. Ngược lại, nếu cả hai khoảng đều đóng ở ranh giới 10:00, cùng một sự kiện tại đó có thể bị đếm hai lần.

Không nên mô tả “cuối ngày” bằng một timestamp giả định như `23:59:59.999`: dữ liệu có thể có độ phân giải micro giây hoặc nano giây. Nên biểu diễn ranh giới bằng **đầu ngày kế tiếp, loại trừ**.

## 2. Tại sao `[start, end)` hữu ích?

Xét hai khoảng liền nhau:

```text
A = [09:00, 10:00)
B = [10:00, 11:00)

A: 09:00 <= t < 10:00
B: 10:00 <= t < 11:00
```

Thời điểm 10:00 không thuộc A nhưng thuộc B. Không có chỗ hở và không đếm trùng ranh giới.

Các lợi ích:

1. **Ghép liên tục:** `[a,b)` và `[b,c)` ghép thành `[a,c)`.
2. **Không đếm hai lần:** mỗi điểm ranh giới thuộc tối đa một khoảng liền nhau.
3. **Độ dài không cần bù:** `Duration.between(start, end)` đã đo khoảng cách giữa hai mốc; không cộng thêm một nano giây vì cuối khoảng bị loại.
4. **Khoảng rỗng rõ nghĩa:** `[a,a)` không chứa phần tử nào.
5. **Tương thích truy vấn:** `timestamp >= start AND timestamp < end` không phụ thuộc độ phân giải nhỏ nhất mà database lưu được.

Ví dụ, các khoảng giờ theo ngày có thể được biểu diễn liên tiếp là `[09:00, 10:00)`, `[10:00, 11:00)`, `[11:00, 12:00)`. Quy ước không phụ thuộc timestamp được lưu đến mili giây hay nano giây.

## 3. Kiểm tra thành viên trong Java

Với `Instant`, hàm kiểm tra khoảng nửa mở có thể viết:

```java
static boolean containsHalfOpen(Instant start, Instant end, Instant t) {
    return !t.isBefore(start) && t.isBefore(end);
}
```

- `!t.isBefore(start)` tương đương `t >= start`.
- `t.isBefore(end)` tương đương `t < end`.

Nên xác thực thứ tự đầu mút. Nếu khoảng không rỗng là yêu cầu, bắt buộc `start.isBefore(end)`. Nếu khoảng rỗng được phép, `start.equals(end)` có nghĩa không có thời điểm nào được chứa trong khoảng `[start,end)`. Nếu `start.isAfter(end)`, từ chối dữ liệu thay vì tự động đổi chỗ hai đầu mút.

Các hàm cho quy ước khác:

```java
static boolean containsClosed(Instant start, Instant end, Instant t) {
    return !t.isBefore(start) && !t.isAfter(end);
}

static boolean containsOpen(Instant start, Instant end, Instant t) {
    return t.isAfter(start) && t.isBefore(end);
}

static boolean containsOpenClosed(Instant start, Instant end, Instant t) {
    return t.isAfter(start) && !t.isAfter(end);
}
```

Đây là các **đoạn phương thức minh họa**; cần đặt trong lớp Java và thêm `import java.time.Instant;`. Dùng tên hàm phản ánh rõ quy ước để người gọi không vô tình sử dụng khoảng đóng khi hợp đồng API quy định khoảng nửa mở.

## 4. Phát hiện giao nhau giữa hai khoảng

Giả sử cả hai khoảng đều hợp lệ và nửa mở:

- A = `[aStart, aEnd)`
- B = `[bStart, bEnd)`

Chúng giao nhau nếu và chỉ nếu:

```text
aStart < bEnd && bStart < aEnd
```

Trong Java:

```java
static boolean overlapsHalfOpen(
        Instant aStart, Instant aEnd,
        Instant bStart, Instant bEnd) {
    return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
}
```

Công thức giả định mỗi khoảng đã được xác thực `start <= end`. Nên xử lý khoảng rỗng theo chính sách rõ ràng; đừng để logic kiểm tra giao nhau âm thầm chấp nhận khoảng đảo đầu mút.

| A | B | Giao nhau? | Vì sao |
| --- | --- | --- | --- |
| `[09:00, 10:00)` | `[10:00, 11:00)` | Không | Điểm 10:00 bị loại ở cuối A và được nhận ở đầu B |
| `[09:00, 10:00)` | `[09:30, 10:30)` | Có | Cùng chứa một đoạn thời gian |
| `[09:00, 10:00)` | `[08:00, 09:00)` | Không | 09:00 bị loại khỏi B |
| `[09:00, 10:00)` | `[09:00, 10:00)` | Có | Hai khoảng trùng nhau |
| `[10:00, 10:00)` | `[09:00, 11:00)` | Không | Khoảng đầu tiên rỗng |

Với hai khoảng đóng, quy tắc ở ranh giới thay đổi: `[09:00,10:00]` và `[10:00,11:00]` có chung điểm 10:00. Vì vậy, không dùng công thức dành cho khoảng nửa mở nếu dữ liệu có quy ước đầu mút khác.

## 5. Đo khoảng cách khác với kiểm tra thành viên

Với hai instant, `Duration.between(start, end)` tính khoảng cách trên timeline:

```java
Duration duration = Duration.between(start, end);
```

Không cộng thêm một nano giây để “bao gồm end”. Việc một đầu mút có thuộc khoảng hay không là quy ước **thành viên**; `Duration` đo khoảng cách giữa hai mốc. Nếu end trước start, `Duration` có thể âm, nên xác nhận thứ tự trước nếu nghiệp vụ yêu cầu thời lượng không âm.

Không đồng nhất khoảng cách timeline với số ngày lịch. Với sự kiện toàn cầu, dùng `Instant`. Với ngày lịch, dùng `LocalDate`. Với lịch địa phương theo múi giờ, tạo các mốc đầu và cuối theo cùng `ZoneId`; DST có thể làm một ngày địa phương dài 23 hoặc 25 giờ.

## 6. Khoảng ngày lịch và truy vấn dữ liệu

Giả sử cần tất cả sự kiện của ngày 24/10/2026 theo UTC. Ta tạo đầu ngày và đầu ngày kế tiếp:

```java
LocalDate day = LocalDate.of(2026, 10, 24);
ZoneId zone = ZoneOffset.UTC;

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
```

Khoảng truy vấn là `[start,end)`. Với một vùng khác, chẳng hạn `America/New_York`, tính hai mốc từ chính `ZoneId` đó; không giả định một ngày địa phương luôn bằng 86.400 giây.

Truy vấn tương ứng:

```sql
SELECT *
FROM events
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant;
```

Cách này bao gồm bản ghi đúng đầu ngày, loại bản ghi đúng đầu ngày kế tiếp và tránh dựng `23:59:59.999999999`.

Nếu giao diện cho người dùng chọn cả ngày bắt đầu và ngày cuối **theo kiểu bao gồm**, ví dụ ngày 24/10 đến 26/10, có thể chuyển ngày cuối thành mốc loại trừ:

```java
LocalDate first = LocalDate.of(2026, 10, 24);
LocalDate lastInclusive = LocalDate.of(2026, 10, 26);
LocalDate endExclusive = lastInclusive.plusDays(1);
// Phạm vi ngày: [2026-10-24, 2026-10-27)
```

Đây là chuyển đổi trên `LocalDate`. Nếu `lastInclusive` là `LocalDate.MAX`, `plusDays(1)` vượt miền biểu diễn và ném ngoại lệ; xử lý riêng nếu ứng dụng hỗ trợ các biên cực đại. Không thay bằng một “thời điểm cuối ngày” giả định theo mili hoặc nano giây.

## 7. Múi giờ và DST ảnh hưởng ranh giới thế nào?

Với `LocalDate`, một ngày lịch là một đơn vị lịch. Khi cần biến ngày địa phương thành các instant, cần vùng thời gian:

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDate day = LocalDate.of(2024, 3, 10);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

System.out.println(Duration.between(start, end).toHours()); // 23
```

Ngày 10/03/2024 tại New York bắt đầu DST, nên phạm vi từ đầu ngày đến đầu ngày kế tiếp có 23 giờ theo timeline. Vào ngày lùi đồng hồ, phạm vi có thể dài 25 giờ. Dùng khoảng nửa mở vẫn đúng: các mốc bắt đầu ngày kế tiếp liên tục nhau, dù khoảng cách thực tế không bằng 24 giờ.

Đừng thay mốc `end` bằng `start.plus(Duration.ofDays(1))` khi yêu cầu là “đầu ngày kế tiếp theo lịch địa phương”. `Duration.ofDays(1)` bằng 86.400 giây; `day.plusDays(1).atStartOfDay(zone)` theo lịch và quy tắc vùng.

Với lịch hẹn theo vùng có DST gap/overlap, chính sách giải quyết giờ không tồn tại hoặc lặp lại vẫn cần được xác định. Quy ước khoảng nửa mở chỉ xác định đầu mút; nó không tự giải quyết cách chuyển một `LocalDateTime` mơ hồ thành instant.

## 8. Chọn quy ước phù hợp

| Bài toán | Quy ước thường dùng | Lý do |
| --- | --- | --- |
| Các khoảng log hoặc sự kiện liền nhau | `[start,end)` | Không trùng ranh giới |
| Truy vấn tất cả bản ghi trong ngày | `[startOfDay,nextStartOfDay)` | Không phụ thuộc độ phân giải timestamp |
| Lịch đặt chỗ và kiểm tra lịch có va chạm | `[start,end)` nếu hợp đồng quy định thời điểm kết thúc là rảnh | Hai lịch liên tiếp có thể chạm nhau mà không chồng lấn |
| Biểu diễn khoảng đóng theo toán học | `[a,b]` | Khi điểm cuối thực sự thuộc tập giá trị |
| Vùng cần loại cả hai đầu | `(a,b)` | Dùng khi nghiệp vụ xác định rõ đầu mút loại trừ |
| Báo cáo ngày cuối được người dùng chọn là ngày bao gồm | Chuyển sang đầu ngày sau làm end-exclusive | Tránh giá trị cuối ngày giả định |

Ví dụ đặt chỗ: nếu một cuộc họp kết thúc lúc 10:00 và cuộc kế tiếp bắt đầu lúc 10:00, mô hình `[start,end)` coi hai lịch không giao nhau. Nếu nghiệp vụ yêu cầu thời gian vệ sinh 10 phút giữa hai lần đặt, hãy cộng buffer thành quy tắc riêng, thay vì đổi quy ước đầu mút không nhất quán.

## 9. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`IntervalConventionDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;

public class IntervalConventionDemo {
    static boolean containsHalfOpen(
            Instant start, Instant end, Instant t) {
        return !t.isBefore(start) && t.isBefore(end);
    }

    static boolean overlapsHalfOpen(
            Instant aStart, Instant aEnd,
            Instant bStart, Instant bEnd) {
        return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
    }

    static boolean validHalfOpen(Instant start, Instant end) {
        return !start.isAfter(end);
    }

    public static void main(String[] args) {
        Instant nine = Instant.parse("2026-10-24T09:00:00Z");
        Instant ten = Instant.parse("2026-10-24T10:00:00Z");
        Instant eleven = Instant.parse("2026-10-24T11:00:00Z");
        Instant nineThirty = Instant.parse("2026-10-24T09:30:00Z");

        System.out.println("contains start = "
                + containsHalfOpen(nine, ten, nine));
        System.out.println("contains end = "
                + containsHalfOpen(nine, ten, ten));
        System.out.println("adjacent overlap = "
                + overlapsHalfOpen(nine, ten, ten, eleven));
        System.out.println("partial overlap = "
                + overlapsHalfOpen(nine, ten, nineThirty, eleven));
        System.out.println("empty interval valid = "
                + validHalfOpen(ten, ten));
        System.out.println("empty interval contains point = "
                + containsHalfOpen(ten, ten, ten));
        System.out.println("duration hours = "
                + Duration.between(nine, ten).toHours());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac IntervalConventionDemo.java
java IntervalConventionDemo
```

Đầu ra:

```text
contains start = true
contains end = false
adjacent overlap = false
partial overlap = true
empty interval valid = true
empty interval contains point = false
duration hours = 1
```

Mã dùng thời điểm cố định nên không phụ thuộc đồng hồ hiện tại hoặc múi giờ mặc định. Khoảng `[10:00,10:00)` được xem là hợp lệ nhưng rỗng; nếu nghiệp vụ cấm khoảng rỗng, hãy yêu cầu `start.isBefore(end)`.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `timestamp <= end` cho mọi khoảng | Sự kiện ở ranh giới có thể bị đếm hai lần | Chuẩn hóa sang `[start,end)` khi hợp với nghiệp vụ |
| Dùng `23:59:59.999` làm cuối ngày | Bỏ sót timestamp có độ phân giải cao hơn | Dùng đầu ngày kế tiếp làm `endExclusive` |
| Dùng `start.plus(Duration.ofDays(1))` cho ngày địa phương kế tiếp | Sai qua DST | Tính ngày kế tiếp bằng lịch và cùng `ZoneId` |
| Quên xác thực thứ tự đầu mút | Khoảng đảo có thể cho kết quả khó hiểu | Kiểm tra `start <= end` trước khi dùng |
| Xem `[a,a]` và `[a,a)` là giống nhau | Khoảng đóng chứa a, nửa mở thì rỗng | Ghi rõ quy ước trong API |
| Cộng một nano giây để bao gồm end | Phụ thuộc độ phân giải và dễ sai | Xác định quy ước đầu mút thay vì bù bằng đơn vị |
| Dùng `LocalDateTime` như instant tuyệt đối | Thiếu offset/vùng | Phân giải bằng `ZoneId` hoặc offset đã biết |
| Dùng công thức giao nhau mà không xác thực khoảng | Che giấu khoảng đảo/rỗng | Validate đầu mút và quy tắc khoảng |
| Ghép hai khoảng đóng liền nhau | Điểm nối bị lặp | Dùng nửa mở cho partition liên tiếp |
| Cho rằng ngày địa phương luôn 24 giờ | Sai ở DST | Tính duration từ các instant đã được phân giải |

## 11. Checklist và tự kiểm tra

Trước khi thiết kế API hoặc truy vấn, xác định quy ước đầu mút; chọn kiểu thời gian đúng; validate đầu mút; kiểm thử ngay trước, đúng tại và ngay sau mỗi ranh giới; tính ngày địa phương theo `ZoneId` khi cần; dùng cùng chính sách trong API, database, báo cáo và giao diện.

**Câu hỏi tự kiểm tra**

1. Với `[09:00,10:00)`, 09:00 có được tính không? → Có.
2. 10:00 có được tính không? → Không.
3. Hai khoảng `[09:00,10:00)` và `[10:00,11:00)` có giao nhau không? → Không.
4. Có nên đặt cuối ngày là `23:59:59.999999999`? → Thường không; lấy đầu ngày kế tiếp làm mốc loại trừ.
5. `Duration.between(start,end)` có cộng thêm nano giây vì khoảng nửa mở không? → Không.
6. Phạm vi ngày địa phương ở New York nên được tính thế nào? → Từ đầu ngày và đầu ngày kế tiếp trong `America/New_York`, rồi quy đổi sang `Instant`.
7. Khoảng rỗng `[a,a)` có chứa a không? → Không.
8. Vì sao quy ước chung cần được ghi rõ? → Để các tầng ứng dụng không đếm trùng, bỏ sót ranh giới hoặc diễn giải đầu mút khác nhau.

### Tài liệu API Java

- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): so sánh thời điểm và biểu diễn timestamp.
- [Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): đo khoảng cách giữa các mốc.
- [Java SE 17 — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): phép toán ngày lịch.
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): ngày giờ địa phương gắn vùng và quy tắc DST.

**Ghi nhớ:** `[start,end)` bao gồm đầu, loại cuối. Quy ước này cho phép ghép khoảng không trùng ranh giới, truy vấn timestamp không phụ thuộc độ phân giải, và biểu diễn khoảng rỗng rõ ràng. Tách biệt khoảng ngày lịch với thời lượng tuyệt đối trên timeline.
