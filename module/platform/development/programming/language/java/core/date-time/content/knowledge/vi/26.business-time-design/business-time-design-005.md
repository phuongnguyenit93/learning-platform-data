# Quy ước thời điểm hết hạn bao gồm hay không bao gồm điểm cuối

## 1. Đúng thời điểm hết hạn còn được dùng không?

Giả sử quyền truy cập có mốc cuối `10:15:00Z`. So sánh lúc `10:14:59Z` hoặc `10:15:01Z` thường dễ; lỗi hay nằm ở **đúng `10:15:00Z`**. Có hai hợp đồng đều diễn đạt được:

- **Không bao gồm điểm cuối:** tại mốc cuối đã hết hiệu lực.
- **Bao gồm điểm cuối:** tại đúng mốc cuối vẫn còn hiệu lực; chỉ hết hiệu lực khi vượt qua.

Java không chọn hợp đồng nghiệp vụ thay ứng dụng. Cần thống nhất nó trước khi viết toán tử, truy vấn và thông báo cho người dùng.

## 2. Viết hợp đồng bằng khoảng thời gian

Gọi `start` là điểm bắt đầu, `end` là mốc cuối. Nếu điểm đầu được tính:

| Khoảng | Còn hiệu lực khi | Đúng `now == end` |
| --- | --- | --- |
| `[start, end)` | `start <= now && now < end` | Hết hiệu lực |
| `[start, end]` | `start <= now && now <= end` | Còn hiệu lực |

Dấu `[`/`]` nghĩa là tính điểm biên; dấu `(`/`)` nghĩa là loại điểm biên. Khi chỉ nói về hết hạn, cần nhớ còn điều kiện chưa đến giờ bắt đầu: “chưa hết hạn” không đồng nghĩa “đang có hiệu lực”.

Khoảng nửa mở `[start, end)` thường thuận tiện cho lịch và dữ liệu: hai khoảng `[A, B)` và `[B, C)` không chồng nhau, cũng không để hở điểm B. Nếu dùng cả hai đầu đóng, thời điểm B có thể thuộc cả hai khoảng. Đây là lợi ích của mô hình, không phải quy định bắt buộc mọi nghiệp vụ.

## 3. Biểu diễn bằng Instant và các phép so sánh

Với mốc toàn cầu, dùng `Instant` để tránh việc múi giờ hiển thị tác động đến so sánh. Các phương thức `isBefore` và `isAfter` đều là so sánh nghiêm ngặt: khi hai mốc bằng nhau, cả hai trả `false`.

| Hợp đồng mốc cuối | Còn chưa hết hạn | Đã hết hạn |
| --- | --- | --- |
| Loại trừ `end` | `now.isBefore(end)` | `!now.isBefore(end)` |
| Bao gồm `end` | `!now.isAfter(end)` | `now.isAfter(end)` |

Sai sót điển hình là chọn điểm cuối loại trừ nhưng dùng `now.isAfter(end)` để kiểm tra hết hạn: đúng tại mốc cuối vẫn bị coi là chưa hết hạn.

Để kiểm tra cả khoảng nửa mở, viết `!now.isBefore(start) && now.isBefore(end)`. Không dùng toán tử `==` để so sánh giá trị các đối tượng thời gian. [Instant: so sánh thời điểm](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

## 4. “Đến hết ngày” là một hợp đồng riêng

Nếu quyền có hiệu lực **đến hết ngày 30/3 theo giờ Berlin**, đầu vào là ngày lịch và vùng. Có thể chuyển thành mốc cuối loại trừ là đầu ngày 31/3 trong vùng đó.

```java
// Đoạn trong một phương thức, với validThrough và zone đã xác định.
Instant endExclusive = validThrough.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
```

Không chọn `23:59:59` hoặc `23:59:59.999` làm “giây cuối cùng”: ý nghĩa đó phụ thuộc độ chính xác, dễ bỏ sót phần lẻ nhỏ hơn. Không lấy đầu ngày cộng 24 giờ để tìm hết ngày ở vùng có đổi giờ mùa hè.

`atStartOfDay(zone)` dùng thời điểm hợp lệ sớm nhất của ngày theo quy tắc vùng. Ngày địa phương có thể dài 23 hoặc 25 giờ; chính ngày kế tiếp trong lịch mới là ranh giới cần tìm. Nếu ngày đầu vào ở biên `LocalDate.MAX`, phép tìm ngày tiếp theo cần chính sách riêng hoặc từ chối vì vượt miền. [LocalDate.atStartOfDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId))

Quy tắc “ngày cuối được tính” không có nghĩa phải dùng một timestamp cuối bao gồm. Có thể giữ ngày cuối bao gồm ở mô hình nghiệp vụ và chuyển thành thời điểm đầu ngày sau loại trừ ở ranh giới thực thi.

## 5. Chương trình kiểm tra đúng các điểm biên

Lưu thành `ExpiryBoundaryDemo.java`. `TimeWindow` dưới đây chủ động chỉ nhận khoảng không rỗng với điểm đầu bao gồm, điểm cuối loại trừ.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class ExpiryBoundaryDemo {
    record TimeWindow(Instant startInclusive, Instant endExclusive) {
        TimeWindow {
            Objects.requireNonNull(startInclusive, "startInclusive");
            Objects.requireNonNull(endExclusive, "endExclusive");
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException("Window must be non-empty");
            }
        }

        boolean contains(Instant value) {
            return !value.isBefore(startInclusive) && value.isBefore(endExclusive);
        }
    }

    static boolean expiredExclusive(Instant now, Instant end) {
        return !now.isBefore(end);
    }

    static boolean expiredInclusive(Instant now, Instant end) {
        return now.isAfter(end);
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2025-03-30T10:00:00Z");
        Instant end = Instant.parse("2025-03-30T10:15:00Z");
        TimeWindow window = new TimeWindow(start, end);

        System.out.println("beforeStart=" + window.contains(start.minusNanos(1)));
        System.out.println("atStart=" + window.contains(start));
        System.out.println("beforeEnd=" + window.contains(end.minusNanos(1)));
        System.out.println("atEnd=" + window.contains(end));
        System.out.println("afterEnd=" + window.contains(end.plusNanos(1)));
        System.out.println("exclusiveExpiredAtEnd=" + expiredExclusive(end, end));
        System.out.println("inclusiveExpiredAtEnd=" + expiredInclusive(end, end));

        Clock fixed = Clock.fixed(end, ZoneOffset.UTC);
        Instant evaluationTime = Instant.now(fixed);
        System.out.println("fixedClockExpired="
                + expiredExclusive(evaluationTime, end));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDate validThrough = LocalDate.of(2025, 3, 30);
        Instant dayStart = validThrough.atStartOfDay(berlin).toInstant();
        Instant dayEnd = validThrough.plusDays(1).atStartOfDay(berlin).toInstant();
        System.out.println("dayEndExclusive=" + dayEnd);
        System.out.println("dayLengthHours="
                + Duration.between(dayStart, dayEnd).toHours());
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 ExpiryBoundaryDemo.java
java ExpiryBoundaryDemo
```

Stdout với quy tắc IANA Berlin năm 2025:

```text
beforeStart=false
atStart=true
beforeEnd=true
atEnd=false
afterEnd=false
exclusiveExpiredAtEnd=true
inclusiveExpiredAtEnd=false
fixedClockExpired=true
dayEndExclusive=2025-03-30T22:00:00Z
dayLengthHours=23
```

`minusNanos(1)` và `plusNanos(1)` chỉ tạo dữ liệu kiểm tra trước/sau biên. Chúng không phải cách sửa hợp đồng bằng cách dịch mốc hết hạn một lượng rất nhỏ. Ngày 30/3 trong ví dụ dài 23 giờ, nhưng mốc đầu ngày kế tiếp vẫn xác định được rõ ràng.

`Clock.fixed` giúp kiểm tra chính xác điểm bằng nhau mà không phụ thuộc tốc độ máy hoặc thời điểm chạy. Trong mã nghiệp vụ, truyền `Clock` hoặc một `Instant` đánh giá vào hàm thay vì gọi trực tiếp đồng hồ ở nhiều nhánh. [Clock.fixed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId))

## 6. Độ chính xác lưu trữ không được âm thầm đổi quy ước

Một hệ thống có thể xử lý nano giây trong Java, chỉ lưu micro giây ở DB và hiển thị đến giây trên giao diện. Nếu mốc cuối bị làm tròn khi ghi hoặc đọc, điểm so sánh thực tế có thể khác mốc đã tạo ban đầu.

Hãy xác định độ chính xác được bảo toàn, quy tắc làm tròn/cắt và biểu diễn chuẩn dùng để quyết định. Kiểm tra sau khi dữ liệu đi qua API/DB, không chỉ kiểm tra giá trị còn trong bộ nhớ.

Không chuyển điểm cuối bao gồm thành loại trừ bằng cách luôn cộng 1 nano giây nếu hạ tầng không bảo toàn nano giây; cũng không trừ 1 mili giây để giả lập “hết ngày”. So sánh trực tiếp theo hợp đồng hoặc dùng ranh giới lịch tự nhiên như đầu ngày kế tiếp.

Hiển thị `10:15:00` có thể che phần lẻ thật của mốc; khi truy vết lỗi biên, cần biết giá trị chính xác và đơn vị. Thời lượng còn lại hiển thị bằng phút nguyên cũng không phải điều kiện duy nhất để quyết định hết hạn.

## 7. Dùng cùng hợp đồng ở Java, truy vấn và API

Một truy vấn cho khoảng nửa mở có thể diễn đạt:

```sql
WHERE valid_from <= :evaluation_time
  AND :evaluation_time < expires_at
```

Đây là biểu thức minh họa dùng tham số có tên; cách binding cụ thể tùy thư viện/DB. Nếu hợp đồng là điểm cuối bao gồm, phép so sánh cuối phải là `<=` với cùng ý nghĩa. Không để Java dùng `<` nhưng truy vấn lại dùng `<=`.

Ví dụ, PostgreSQL định nghĩa `BETWEEN` bao gồm cả hai đầu; không thay trực tiếp điều kiện khoảng nửa mở bằng biểu thức đó. [PostgreSQL: BETWEEN](https://www.postgresql.org/docs/current/functions-comparison.html)

Tên như `endExclusive`, `validThroughDate`, `expiresAt` kèm mô tả ranh giới giúp truyền đạt ý định. Một tên chung như `endTime` mà không có hợp đồng sẽ để lại câu hỏi đúng điểm cuối cho từng người viết mã.

Nếu cho phép mốc hết hạn không có giới hạn, mô hình phải thể hiện điều đó rõ ràng; không tự dùng `null`, epoch hay `Instant.MAX` thay thế mà mọi thành phần hiểu khác nhau.

## 8. Chọn thời điểm đánh giá cho cả quyết định

Trong một lần xử lý, nên lấy mốc đánh giá một lần rồi dùng nhất quán. Nếu gọi `now()` khi kiểm tra điều kiện đầu và gọi lần nữa cho điều kiện cuối, hai mốc có thể nằm hai phía của một ranh giới.

Cũng cần xác định quyết định dựa trên lúc nhận yêu cầu, lúc bắt đầu thao tác hay thời điểm DB đánh giá. Một yêu cầu đến trước hạn nhưng xử lý sau hạn có kết quả tùy chính sách đó; đổi `>` thành `>=` không giải quyết toàn bộ câu hỏi.

Với một thao tác cập nhật cần bảo đảm điều kiện hết hạn tại DB, có thể đặt điều kiện thời gian cùng thao tác ghi theo hợp đồng giao dịch, rồi kiểm tra kết quả cập nhật. Việc kiểm tra trước ở ứng dụng không tự giữ điều kiện đúng mãi trong lúc xử lý tiếp.

## 9. Tự thực hành

1. Viết bảng kết quả ở trước, đúng và sau điểm cuối cho hai hợp đồng.
2. Chia khoảng `[09:00, 11:00)` thành hai khoảng liền nhau ở 10:00; thời điểm 10:00 thuộc khoảng nào?
3. Chuyển yêu cầu “còn dùng được hết ngày 31/12 tại Việt Nam” thành mốc cuối loại trừ.
4. Kiểm tra trường hợp mốc lưu trong DB bị cắt từ nano giây xuống mili giây.

Đối chiếu: (1) chỉ khác nhau tại điểm bằng nhau; (2) thuộc `[10:00, 11:00)`; (3) đầu ngày 1/1 năm sau theo `Asia/Ho_Chi_Minh`; (4) phải so sánh với biểu diễn đã được thống nhất và kiểm tra sau vòng ghi/đọc.