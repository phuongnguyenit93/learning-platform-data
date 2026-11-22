# Tính giới hạn của OffsetTime khi suy luận một thời điểm

Trong Java Date-Time API (`java.time`), `OffsetTime` là **giờ trong ngày cộng với một độ lệch UTC cố định**, ví dụ `19:00+07:00`. Nó trả lời “đồng hồ là mấy giờ tại offset này?” nhưng **chưa trả lời được sự kiện xảy ra lúc nào trên dòng thời gian** vì **không chứa ngày lịch**.

Cùng một `OffsetTime` dưới đây có thể đưa tới hai thời điểm thực khác nhau:

~~~java
OffsetTime t = OffsetTime.parse("19:00+07:00");
Instant a = t.atDate(LocalDate.of(2024, 2, 29)).toInstant();
Instant b = t.atDate(LocalDate.of(2024, 3, 1)).toInstant();
~~~

~~~text
a = 2024-02-29T12:00:00Z
b = 2024-03-01T12:00:00Z
~~~

Hai instant cách nhau **24 giờ**. Thiếu ngày không phải lỗi Java; đó là **thiếu thông tin đầu vào**, nên không thể suy ra một `Instant` duy nhất.

## 1. OffsetTime có những gì?

Về mặt cấu trúc, `OffsetTime` gồm:

- **`LocalTime`**: giờ, phút, giây và phần nano trong giây.
- **`ZoneOffset`**: độ lệch cố định so với UTC, như `+07:00` hoặc `-05:00`.

~~~java
OffsetTime t = OffsetTime.of(
        LocalTime.of(19, 0), ZoneOffset.of("+07:00"));

LocalTime wallClock = t.toLocalTime(); // 19:00
ZoneOffset offset = t.getOffset();     // +07:00
int hour = t.getHour();                // 19
~~~

Ngược lại, `OffsetTime` **không có**:

1. Năm, tháng, ngày (`LocalDate`).
2. Một timestamp đầy đủ tương ứng với sự kiện (`Instant`).
3. ID vùng có quy tắc giờ dân sự theo lịch sử/tương lai (`ZoneId` dạng `Asia/Ho_Chi_Minh`).
4. Thông tin về DST của một vùng, ngày chuyển đồng hồ, hoặc các lần thay đổi luật múi giờ.

Sự khác nhau giữa các kiểu:

| Kiểu | Có ngày? | Có giờ? | Có offset? | Có vùng? | Xác định một Instant duy nhất? |
|---|---|---|---|---|---|
| `LocalTime` | Không | Có | Không | Không | Không |
| **`OffsetTime`** | **Không** | **Có** | **Có** | Không | **Không** |
| `LocalDateTime` | Có | Có | Không | Không | Không |
| `OffsetDateTime` | Có | Có | Có | Không nhất thiết | **Có** |
| `ZonedDateTime` | Có | Có | Offset được xác định theo vùng | Có | **Có**, sau khi giải quyết quy tắc vùng |
| `Instant` | Không chứa dạng ngày giờ địa phương | Không chứa dạng giờ địa phương | Không | Không | **Chính là một điểm thời gian** |

`ZoneOffset` cũng là một loại `ZoneId` trong API Java, nhưng **offset cố định** không tương đương **ID vùng** có các quy tắc thay đổi theo thời điểm.

## 2. Có offset vẫn không biết ngày UTC hoặc timestamp

Cho `19:00+07:00`:

~~~text
Giờ UTC tương ứng trong ngày: 19:00 - 07:00 = 12:00
Ngày địa phương:              chưa biết
Ngày UTC:                     chưa biết
Instant:                      chưa xác định
~~~

Có vô số ứng viên: `2024-02-29T12:00:00Z`, `2024-03-01T12:00:00Z`, `2024-03-02T12:00:00Z`, v.v. Nếu một bảng chỉ lưu cột `time_with_offset`, không thể dùng nó một mình để sắp xếp chính xác toàn bộ sự kiện theo lịch sử.

Điều này vẫn đúng nếu giờ lưu rất chi tiết:

~~~text
19:00:00.123456789+07:00
~~~

Phần nano giây cho biết độ chi tiết **trong ngày**, không bù được **ngày bị thiếu**. Độ phân giải cao không có nghĩa dữ liệu đủ để suy ra timestamp.

### Offset cũng có thể làm ngày UTC khác ngày địa phương

~~~java
OffsetTime time = OffsetTime.parse("00:30+14:00");
Instant result = time.atDate(LocalDate.of(2024, 3, 1)).toInstant();
// 2024-02-29T10:30:00Z
~~~

Cùng một giá trị có ngày địa phương **01/03/2024** nhưng ngày UTC **29/02/2024**. Nếu tự trừ 14 giờ rồi **bỏ qua việc vượt qua nửa đêm**, ta sẽ gán nhầm ngày UTC. Hãy dùng API có đủ ngày và offset để chuyển đổi.

## 3. Cách đúng để tạo Instant khi biết ngày

`OffsetTime` không có phương thức `toInstant()` trực tiếp vì thiếu ngày. Khi có **ngày địa phương đúng** của giá trị đồng hồ, dùng:

~~~text
OffsetTime (time + offset)
           + LocalDate
                |
                | atDate(localDate)
                v
OffsetDateTime (date + time + offset)
                |
                | toInstant()
                v
Instant (thời điểm thực)
~~~

Ví dụ:

~~~java
LocalDate day = LocalDate.of(2024, 2, 29);
OffsetTime withOffset = OffsetTime.parse("19:00+07:00");
OffsetDateTime complete = withOffset.atDate(day);
// 2024-02-29T19:00+07:00

Instant timestamp = complete.toInstant();
// 2024-02-29T12:00:00Z
~~~

`atDate(LocalDate)` **ghép ngày đã biết** với giờ + offset cố định trong `OffsetTime`. `toInstant()` xác định vị trí trên timeline từ ba yếu tố ngày/giờ/offset.

**Điều kiện thiết yếu:** `day` phải là ngày **thuộc đồng hồ địa phương của chính bản ghi**. Nếu phía gửi nói ngày UTC thay vì ngày địa phương, phải làm rõ giao thức; gắn nhầm loại ngày có thể tạo timestamp sai, đặc biệt khi offset khiến ngày UTC và ngày địa phương khác nhau.

### Nếu ngày và offset cùng nằm trong một chuỗi

Đừng loại bỏ ngày rồi parse bằng `OffsetTime`. Dùng `OffsetDateTime`:

~~~java
OffsetDateTime event =
        OffsetDateTime.parse("2024-02-29T19:00:00+07:00");
Instant instant = event.toInstant();
// 2024-02-29T12:00:00Z
~~~

Còn nếu API truyền hai trường riêng:

~~~json
{
  "localDate": "2024-02-29",
  "localTimeWithOffset": "19:00+07:00"
}
~~~

Thì đọc từng phần có thể hợp lệ:

~~~java
LocalDate date = LocalDate.parse("2024-02-29");
OffsetTime time = OffsetTime.parse("19:00+07:00");
Instant when = time.atDate(date).toInstant();
~~~

Không tự chọn `LocalDate.now()` khi ngày thiếu: việc đó âm thầm biến dữ liệu lịch sử thành dữ liệu của thời điểm chạy chương trình. Không dùng `ZoneId.systemDefault()` để đoán vùng chỉ từ offset; một offset có thể thuộc nhiều vùng.

## 4. So sánh hai OffsetTime: điều gì được, điều gì chưa được?

`OffsetTime` có `isBefore(...)`, `isAfter(...)` và `isEqual(...)`. Chúng so **thứ tự tương đối của các giá trị giờ có offset** theo quy tắc API, chứ không dựng ra ngày thật cho từng sự kiện.

~~~java
OffsetTime hcm = OffsetTime.parse("19:00+07:00");
OffsetTime utc = OffsetTime.parse("12:00Z");

boolean sameRelativeTime = hcm.isEqual(utc); // true
boolean sameValue = hcm.equals(utc);          // false
~~~

- `isEqual(utc)` là `true` vì 19:00 ở `+07:00` và 12:00 ở UTC tương đương về giờ quy đổi trên một mốc ngày tham chiếu chung.
- `equals(utc)` là `false` vì hai đối tượng mang **giờ địa phương** và **offset** khác nhau.
- `isBefore` và `isAfter` hữu ích khi so các giờ có offset theo hợp đồng API, nhưng chưa chứng minh hai event không có ngày xảy ra trước/sau nhau trên timeline thật.
- `compareTo` có quy tắc sắp xếp nhất quán với `equals`; không đồng nhất `compareTo(...) == 0` với mọi trường hợp `isEqual(...)` trả `true`.

Ví dụ: hai log ghi `19:00+07:00` và `12:00Z` có thể đến từ **hai ngày khác nhau**. `isEqual` vẫn `true` cho hai giá trị `OffsetTime`, dù `Instant` của các log không bằng nhau.

Nếu nghiệp vụ hỏi “event A có trước event B?”:

~~~java
Instant a = firstTime.atDate(firstDate).toInstant();
Instant b = secondTime.atDate(secondDate).toInstant();
boolean earlier = a.isBefore(b);
~~~

Đây là **đoạn mã minh họa trong một phương thức**, giả định hai `OffsetTime` và hai `LocalDate` tương ứng đã được xác định theo nguồn dữ liệu. Không dùng một ngày chung tùy tiện nếu event thực sự xảy ra ở các ngày khác nhau.

## 5. Offset cố định không thay thế được múi giờ vùng

`OffsetTime.parse("09:00-05:00")` biểu diễn một giờ kèm **offset -05:00 cố định**. Nó **không có thông tin** đây là giờ New York, Toronto hay vùng nào khác.

Nếu ý định là “09:00 theo giờ New York”, `ZoneId.of("America/New_York")` mới mô tả đầy đủ quy tắc vùng. Trong năm 2024, tại New York:

| Ngày giờ địa phương | Offset theo vùng | Instant tương ứng |
|---|---|---|
| `2024-01-15T09:00` | `-05:00` | `2024-01-15T14:00:00Z` |
| `2024-07-15T09:00` | `-04:00` | `2024-07-15T13:00:00Z` |

Chỉ lưu `09:00-05:00` rồi ghép ngày **15/07/2024** sẽ ra **14:00Z** — lệch một giờ so với “09:00 theo giờ New York” (**13:00Z**) do quy tắc DST.

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime julyMeeting = LocalDateTime.of(2024, 7, 15, 9, 0);

Instant byRegion = julyMeeting.atZone(ny).toInstant();
// 2024-07-15T13:00:00Z

Instant byFixedOffset = julyMeeting
        .atOffset(ZoneOffset.of("-05:00")).toInstant();
// 2024-07-15T14:00:00Z
~~~

Như vậy, `OffsetTime` còn có **giới hạn thứ hai ngoài thiếu ngày**: chỉ có offset, **không có luật múi giờ theo địa điểm**. Một offset gắn sẵn có thể không phải offset hợp lệ của vùng vào ngày bạn muốn sử dụng.

Các vùng có DST còn có thể tạo **gap** (giờ địa phương không tồn tại) và **overlap** (giờ địa phương có hai offset hợp lệ). Khi yêu cầu theo lịch dân sự của một vùng, dùng `LocalDateTime` + `ZoneId` hoặc `ZonedDateTime` và quy định rõ chính sách giải quyết trường hợp DST. Không thể suy ra các thông tin đó từ một `OffsetTime`.

### Khi nào OffsetTime vẫn phù hợp?

`OffsetTime` phù hợp khi nghiệp vụ thật sự mô tả **giờ trong ngày với một offset cố định**, ví dụ “chạy tác vụ lúc `09:00+07:00` mỗi ngày tính theo offset cố định”. Để chuyển thành từng instant thực, hệ thống vẫn phải biết **ngày thực hiện** rồi `atDate(date).toInstant()`.

Nếu lịch mang ý nghĩa “09:00 giờ dân sự tại TP.HCM/New York”, nên lưu **tên vùng** cùng ngày/giờ lịch; không suy đoán tên vùng từ `+07:00` hoặc `-05:00`.

## 6. Ví dụ Java 17 hoàn chỉnh

Lưu chương trình dưới tên **`OffsetTimeLimitDemo.java`**:

~~~java
import java.time.*;

public class OffsetTimeLimitDemo {
    public static void main(String[] args) {
        OffsetTime withOffset = OffsetTime.parse("19:00+07:00");
        OffsetTime utcClock = OffsetTime.parse("12:00Z");
        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        LocalDate nextDay = leapDay.plusDays(1);

        OffsetDateTime onLeapDay = withOffset.atDate(leapDay);
        OffsetDateTime onNextDay = withOffset.atDate(nextDay);
        System.out.println("offset time = " + withOffset);
        System.out.println("same reference UTC time = " + withOffset.isEqual(utcClock));
        System.out.println("offset time equals = " + withOffset.equals(utcClock));
        System.out.println("at leap day = " + onLeapDay);
        System.out.println("instant on leap day = " + onLeapDay.toInstant());
        System.out.println("instant on next day = " + onNextDay.toInstant());
        System.out.println("gap hours = " +
                Duration.between(onLeapDay.toInstant(), onNextDay.toInstant()).toHours());
        System.out.println("same UTC on leap day = " +
                onLeapDay.toInstant().equals(utcClock.atDate(leapDay).toInstant()));

        OffsetTime beforeMidnight = OffsetTime.parse("00:30+14:00");
        System.out.println("local 00:30+14 at Mar 1 UTC = " +
                beforeMidnight.atDate(LocalDate.of(2024, 3, 1)).toInstant());

        ZoneId newYork = ZoneId.of("America/New_York");
        LocalDateTime winterNine = LocalDateTime.of(2024, 1, 15, 9, 0);
        LocalDateTime summerNine = LocalDateTime.of(2024, 7, 15, 9, 0);
        System.out.println("NY winter offset = " + winterNine.atZone(newYork).getOffset());
        System.out.println("NY summer offset = " + summerNine.atZone(newYork).getOffset());
        System.out.println("NY summer UTC correct = " + summerNine.atZone(newYork).toInstant());
        System.out.println("NY summer UTC fixed -05 = " +
                summerNine.atOffset(ZoneOffset.of("-05:00")).toInstant());
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac OffsetTimeLimitDemo.java
java OffsetTimeLimitDemo
~~~

Đầu ra đã được kiểm tra khi biên dịch với `javac --release 17`:

~~~text
offset time = 19:00+07:00
same reference UTC time = true
offset time equals = false
at leap day = 2024-02-29T19:00+07:00
instant on leap day = 2024-02-29T12:00:00Z
instant on next day = 2024-03-01T12:00:00Z
gap hours = 24
same UTC on leap day = true
local 00:30+14 at Mar 1 UTC = 2024-02-29T10:30:00Z
NY winter offset = -05:00
NY summer offset = -04:00
NY summer UTC correct = 2024-07-15T13:00:00Z
NY summer UTC fixed -05 = 2024-07-15T14:00:00Z
~~~

Giải thích:

1. `19:00+07:00` và `12:00Z` có `isEqual` bằng `true` vì giờ sau quy đổi offset tương ứng nhau, nhưng `equals` bằng `false` vì giá trị giờ/offset khác.
2. `atDate` gắn 29/02 hoặc 01/03 vào cùng một `OffsetTime` tạo hai instant cách nhau **24 giờ**.
3. `00:30+14:00` thuộc ngày 01/03 tại địa phương nhưng rơi vào **29/02 UTC**.
4. Với New York, offset mùa đông `-05:00` khác offset mùa hè `-04:00`. Dùng sai offset cố định mùa hè gây sai timestamp một giờ.

Kết quả New York dựa vào quy tắc tzdb tích hợp trong JDK đã chạy thử. Ứng dụng phụ thuộc quy tắc lịch sử/tương lai cần xác nhận bản dữ liệu múi giờ đang dùng và có chính sách cập nhật thích hợp.

## 7. Áp dụng vào thiết kế dữ liệu

**Ghi nhận giao dịch:** cần “xảy ra khi nào?”, lưu `Instant` (hoặc timestamp UTC với đơn vị và độ chính xác rõ ràng), không chỉ `OffsetTime`. Nếu đầu vào là chuỗi ISO có ngày và offset, đọc `OffsetDateTime.parse(...).toInstant()`.

**Giờ thực hiện cố định theo offset:** có thể lưu `OffsetTime` như một cấu hình tái sử dụng, nhưng khi tạo lần thực thi cụ thể phải gắn `LocalDate` tương ứng rồi mới chuyển `Instant`.

**Lịch hẹn theo vùng địa lý:** cần `LocalDateTime` kèm `ZoneId` của địa điểm, rồi kiểm tra gap/overlap nếu cần. Không tự kết luận từ một offset ra một ID vùng múi giờ.

**Hai bản ghi cần so thứ tự:** nếu chỉ có hai `OffsetTime`, chưa đủ để kết luận event nào trước/sau trên timeline. Phải có ngày và dùng hai `Instant`; không nên thêm ngày hiện tại để né kiểm tra đầu vào.

| Yêu cầu | Kiểu/thao tác nên chọn |
|---|---|
| “09:00 theo offset +07:00, chưa nói ngày” | `OffsetTime` |
| “19:00 ngày 29/02/2024 theo +07:00” | `OffsetDateTime` |
| “Một timestamp duy nhất cho event” | `Instant` |
| “09:00 theo giờ vùng New York vào ngày X” | `LocalDateTime` + `ZoneId` hoặc `ZonedDateTime` |
| “Cùng giờ có offset, nhưng ngày ở trường riêng” | `OffsetTime.atDate(date).toInstant()` |

## 8. Những lỗi phổ biến

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| Tưởng `OffsetTime` đã là timestamp | Nó thiếu ngày | Bổ sung `LocalDate` rồi tạo `Instant` |
| Gọi `offsetTime.toInstant()` | `OffsetTime` không có API này | `offsetTime.atDate(date).toInstant()` |
| Dùng `LocalDate.now()` để bù ngày thiếu | Sẽ gán nhầm ngày của môi trường chạy | Lấy ngày chính xác từ hợp đồng dữ liệu |
| Xem `isEqual` là bằng nhau của hai event thực | Chưa có ngày để định vị event | So hai `Instant` sau khi bổ sung ngày |
| Coi `equals` giống `isEqual` | `equals` xét cả giờ/offset của đối tượng | Chọn phép so sánh theo nhu cầu |
| Bỏ qua đổi ngày khi quy UTC | Offset có thể đưa ngày UTC sang hôm trước/hôm sau | Dùng `OffsetDateTime.toInstant()` |
| Cho rằng offset là tên vùng | Nhiều vùng cùng offset, vùng có lịch sử thay đổi | Dùng `ZoneId` khi nghiệp vụ yêu cầu |
| Dùng offset -05:00 cho New York cả năm | Mùa hè ở ví dụ 2024 dùng -04:00 | Dùng quy tắc `ZoneId` |
| Dùng `OffsetTime.now()` làm input test cố định | Kết quả phụ thuộc đồng hồ | Dùng `parse(...)` hoặc `of(...)` với giá trị cố định |
| Nhầm `OffsetTime` và `OffsetDateTime` | Chỉ kiểu thứ hai có ngày | Chọn loại phù hợp với độ đầy đủ dữ liệu |

## 9. Tự kiểm tra

1. `OffsetTime.parse("19:00+07:00")` có ngày không? **Không**; chỉ có giờ và offset.
2. Vì sao không thể trực tiếp suy ra `Instant`? **Không biết ngày địa phương**.
3. Muốn biến nó thành một `Instant` khi đã biết ngày, gọi gì? **`time.atDate(date).toInstant()`**.
4. `19:00+07:00` tại ngày địa phương 29/02/2024 ứng với gì? **2024-02-29T12:00:00Z**.
5. Cùng giá trị đó tại ngày 01/03/2024 ứng với gì? **2024-03-01T12:00:00Z**.
6. `19:00+07:00` và `12:00Z` có `isEqual` là true. Có khẳng định hai event ghi log tương ứng xảy ra cùng lúc không? **Không**, còn thiếu ngày của từng event.
7. Ngày địa phương 01/03/2024 lúc `00:30+14:00` ứng với ngày UTC nào? **29/02/2024**.
8. “09:00 tại New York ngày 15/07/2024” nên dựa vào offset cứng `-05:00` hay vùng `America/New_York`? **Vùng**, áp dụng offset `-04:00` ở ngày đó theo tzdb 2024.
9. API gửi `2024-02-29T19:00:00+07:00`: nên parse bằng kiểu nào để tạo instant? **`OffsetDateTime`**, rồi `toInstant()`.
10. Nếu bản ghi thiếu ngày, có nên tự lấy ngày hôm nay để xử lý? **Không**; phải xác định từ nguồn có thẩm quyền.

**Ghi nhớ:** `OffsetTime = giờ + offset`, **không có ngày**. Giờ với offset chỉ đủ để quy đổi **giờ trong một ngày đã xác định**, chưa phải một điểm trên timeline. Khi cần thời điểm sự kiện, ghép **ngày đúng** bằng `atDate(date)` và gọi `toInstant()`; khi cần lịch theo vùng, áp dụng `ZoneId` chứ không tự dùng offset cố định.

### Tài liệu tham khảo

- [Java SE 17 — OffsetTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetTime.html)
- [Java SE 17 — OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — ZoneOffset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html)
- [Java SE 17 — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
