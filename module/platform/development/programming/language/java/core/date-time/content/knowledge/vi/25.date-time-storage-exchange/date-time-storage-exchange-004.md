# Lưu `ZoneId` riêng khi cần giữ quy tắc múi giờ vùng

## 1. Giữ thời điểm và giữ vùng là hai nhu cầu khác nhau

Một sự kiện xảy ra tại `2025-01-15T08:00:00Z` đã có thời điểm xác định. Nhưng chỉ từ giá trị đó, không thể biết người dùng đã nhìn nó theo giờ Paris, Berlin hay một vùng khác. Nếu nghiệp vụ cần giữ vùng nguồn để hiển thị hoặc tính lịch địa phương về sau, phải lưu thêm ID vùng như `Europe/Paris`.

Độ lệch `+01:00` ở ngày xảy ra sự kiện cũng không thay được ID vùng. Nhiều vùng có cùng độ lệch tại một thời điểm, và một vùng có thể thay đổi độ lệch theo ngày.

Theo [Java SE 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html), `ZoneId` định danh tập quy tắc để chuyển giữa thời điểm và ngày–giờ địa phương; các quy tắc thực nằm trong `ZoneRules`. **Lưu ID là giữ tham chiếu tới quy tắc vùng, không phải lưu bản chụp bất biến của toàn bộ dữ liệu quy tắc.**

Đó là ý nghĩa cần hiểu khi nói “giữ quy tắc múi giờ vùng”: tiếp tục biết vùng nào cần được áp dụng, thay vì chỉ giữ một độ lệch rời rạc đã tính ở quá khứ.

## 2. Mỗi lựa chọn lưu được những thông tin gì?

| Dữ liệu giữ lại | Điều có thể xác định | Điều chưa được giữ |
| --- | --- | --- |
| `Instant` | Một thời điểm trên dòng thời gian | Vùng nguồn/ngữ cảnh giờ địa phương ban đầu |
| `OffsetDateTime` hoặc thời điểm kèm độ lệch | Thời điểm và độ lệch đã ghi | ID vùng và quy tắc độ lệch của vùng ở các ngày khác |
| `Instant` + chuỗi `zoneId` | Thời điểm và vùng cần dùng để tái hiển thị | Bản chụp phiên bản quy tắc cũ nếu dữ liệu vùng đổi |
| `LocalDateTime` + `zoneId` | Ý định ngày–giờ địa phương tại vùng | Có thể cần chính sách cho giờ không tồn tại/trùng và quyết định khi quy tắc đổi |

Không cần lưu vùng cho mọi bản ghi chỉ để có một trường bổ sung. Nếu nghiệp vụ chỉ cần thời điểm và luôn hiển thị theo vùng người xem, `Instant` có thể đủ. Lưu thêm vùng khi nó là một phần ý nghĩa phải bảo toàn: địa điểm của lịch hẹn, vùng của đơn vị lập báo cáo hoặc lựa chọn vùng của người tạo.

Một lịch lặp như “09:00 mỗi thứ Hai theo giờ Paris” còn cần quy tắc lặp và giờ địa phương, không thể được mô hình hóa đầy đủ chỉ bằng một `Instant` đầu tiên kèm vùng.

## 3. Vì sao lưu độ lệch hiện tại là chưa đủ?

Trong ví dụ của bài, lịch hẹn 09:00 ở Paris ngày 15 tháng 1 năm 2025 dùng `+01:00`. Khi xét ngày 15 tháng 7 cùng năm, quy tắc vùng dùng `+02:00` theo dữ liệu runtime.

Nếu lưu vùng, 09:00 mùa hè tương ứng 07:00 UTC. Nếu chỉ giữ độ lệch mùa đông `+01:00` rồi áp lại cho 09:00 mùa hè, thời điểm thành 08:00 UTC: lệch một giờ so với ý định theo vùng.

Không có lỗi cộng giờ ngẫu nhiên ở đây. Hai phép tính dùng hai hợp đồng khác nhau: một bên áp quy tắc `Europe/Paris` tại ngày cần tính, một bên giữ độ lệch cố định. Lưu mỗi độ lệch chỉ đúng khi chính yêu cầu nghiệp vụ nói tới độ lệch cố định ấy.

Cũng không suy ngược ID từ độ lệch. Paris và Berlin trong ví dụ có cùng độ lệch mùa đông, nhưng điều đó không làm hai ID bằng nhau hoặc chứng minh người dùng đã chọn vùng nào.

## 4. Một hợp đồng trao đổi rõ ràng

Với sự kiện đã có thời điểm và cần giữ vùng nguồn, có thể tách hai thuộc tính:

```json
{
  "occurredAt": "2025-01-15T08:00:00Z",
  "zoneId": "Europe/Paris"
}
```

Đây là ví dụ hợp đồng dữ liệu, không tự quy định thư viện JSON hoặc kiểu cột cơ sở dữ liệu. Một thuộc tính giữ thời điểm; thuộc tính còn lại giữ ID vùng đầy đủ.

Khi đọc lại trong Java:

```java
// Minh họa trong một phương thức; instant và storedZoneId đã được đọc.
ZoneId zone = ZoneId.of(storedZoneId);
ZonedDateTime view = instant.atZone(zone);
```

Nếu cần ID vùng, đừng ghi `value.getOffset().getId()` thay cho `value.getZone().getId()`: phương thức đầu chỉ lấy độ lệch hiện tại của giá trị, còn phương thức sau lấy vùng mà đối tượng đang mang. Đồng thời, `getZone()` có thể là một vùng độ lệch cố định nếu ngay từ đầu nguồn chỉ cung cấp offset; nó không tự khám phá địa điểm.

Khi lưu qua cơ sở dữ liệu hoặc thư viện ánh xạ, kiểm tra hợp đồng thực tế của kiểu/cột và quá trình ghi–đọc. Tên lớp Java `ZonedDateTime` hoặc tên kiểu lưu trữ có chữ “time zone” không tự chứng minh ID vùng được giữ nguyên. Nếu ID vùng là dữ liệu nghiệp vụ, lưu và kiểm chứng thuộc tính đó riêng sẽ làm yêu cầu rõ ràng hơn.

## 5. Chương trình kiểm chứng đầy đủ

Lưu mã vào `StoreRegionZoneDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.util.Objects;

public class StoreRegionZoneDemo {
    record StoredEvent(Instant occurredAt, String zoneId) {
        StoredEvent {
            Objects.requireNonNull(occurredAt);
            ZoneId.of(Objects.requireNonNull(zoneId));
        }

        ZonedDateTime restore() {
            return occurredAt.atZone(ZoneId.of(zoneId));
        }
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime winter = ZonedDateTime.of(
                2025, 1, 15, 9, 0, 0, 0, paris);
        StoredEvent stored = new StoredEvent(
                winter.toInstant(), winter.getZone().getId());

        System.out.println("stored instant = " + stored.occurredAt());
        System.out.println("stored zoneId = " + stored.zoneId());
        System.out.println("restored = " + stored.restore());
        System.out.println("round trip equal = " + winter.equals(stored.restore()));

        LocalDateTime sixMonthsLater = winter.toLocalDateTime().plusMonths(6);
        ZonedDateTime regional = sixMonthsLater.atZone(paris);
        OffsetDateTime fixedOffset = sixMonthsLater.atOffset(winter.getOffset());
        System.out.println("summer with region = " + regional);
        System.out.println("summer with saved offset = " + fixedOffset);
        System.out.println("region instant = " + regional.toInstant());
        System.out.println("fixed instant = " + fixedOffset.toInstant());

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        System.out.println("same winter offset = "
                + winter.getOffset().equals(
                        winter.toInstant().atZone(berlin).getOffset()));
        System.out.println("same zone ID = " + paris.equals(berlin));

        LocalDateTime gap = LocalDateTime.of(2025, 3, 30, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2025, 10, 26, 2, 30);
        System.out.println("gap offset count = "
                + paris.getRules().getValidOffsets(gap).size());
        System.out.println("overlap offset count = "
                + paris.getRules().getValidOffsets(overlap).size());

        try {
            new StoredEvent(winter.toInstant(), "Europe/Paris_typo");
        } catch (DateTimeException ex) {
            System.out.println("invalid stored zone = DateTimeException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StoreRegionZoneDemo.java
java StoreRegionZoneDemo
```

Kết quả đã kiểm chứng với dữ liệu quy tắc vùng của runtime dùng trong bài:

```text
stored instant = 2025-01-15T08:00:00Z
stored zoneId = Europe/Paris
restored = 2025-01-15T09:00+01:00[Europe/Paris]
round trip equal = true
summer with region = 2025-07-15T09:00+02:00[Europe/Paris]
summer with saved offset = 2025-07-15T09:00+01:00
region instant = 2025-07-15T07:00:00Z
fixed instant = 2025-07-15T08:00:00Z
same winter offset = true
same zone ID = false
gap offset count = 0
overlap offset count = 2
invalid stored zone = DateTimeException
```

`StoredEvent` chỉ mô phỏng dữ liệu đã lưu bằng một `record`; nó không thực hiện ghi cơ sở dữ liệu. Kiểm tra vòng chuyển trong ví dụ xác nhận giữ được thời điểm và ID trong cùng runtime, không thay thế việc kiểm chứng bộ lưu trữ/thư viện thực tế của ứng dụng.

## 6. Phục hồi sự kiện khác với tính lại lịch hẹn tương lai

### Sự kiện đã xảy ra

`restore()` lấy `occurredAt` rồi áp `zoneId` để tạo cách nhìn có vùng. Thời điểm không đổi; chỉ các trường địa phương được dựng theo quy tắc runtime. Với dữ liệu ví dụ, ta nhận lại đúng `2025-01-15T09:00+01:00[Europe/Paris]`.

Nếu dữ liệu lịch sử của vùng được cập nhật và yêu cầu phải tái hiện chính xác các trường/độ lệch mà người dùng từng nhìn thấy, chỉ ID và Instant có thể chưa đủ cho yêu cầu kiểm toán đó. Khi ấy hợp đồng có thể cần giữ thêm độ lệch hoặc biểu diễn địa phương đã ghi và metadata phiên bản quy tắc, kèm quy định đối chiếu tính nhất quán.

Không tự thay thời điểm sự kiện đã xảy ra chỉ vì phiên bản quy tắc hiển thị thay đổi. Phải phân biệt giá trị sự kiện đã ghi với cách diễn giải lại để hiển thị.

### Ý định theo giờ địa phương ở tương lai

Phần `sixMonthsLater` lấy ngày–giờ địa phương mùa đông rồi cộng sáu tháng để so sánh cách diễn giải theo vùng và theo độ lệch. Nó minh họa việc giữ ý định 09:00 theo vùng; không phải một bộ lập lịch lặp hoàn chỉnh.

Với lịch hẹn tương lai, ứng dụng cần quyết định điều gì là nguồn chính: giờ địa phương đã thỏa thuận hay Instant đã chốt. Nếu quy tắc vùng tương lai thay đổi, giữ nguyên cả hai có thể không còn là lựa chọn nhất quán. Cần chính sách theo nghiệp vụ, không chỉ một hàm chuyển kiểu.

## 7. Có ID vùng vẫn cần xử lý giờ không tồn tại hoặc trùng

[Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html) phân biệt trường hợp giờ địa phương có một độ lệch hợp lệ, không có độ lệch do đồng hồ nhảy tới, hoặc có hai độ lệch khi đồng hồ lùi lại.

Chương trình dùng [ZoneRules.getValidOffsets()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime)) để kiểm tra Paris:

- `2025-03-30 02:30` có 0 độ lệch hợp lệ trong dữ liệu dùng ở bài.
- `2025-10-26 02:30` có 2 độ lệch hợp lệ.

Vì vậy, chỉ lưu `LocalDateTime + ZoneId` chưa luôn chọn được một Instant duy nhất theo ý định người dùng. Một lịch hẹn cần quy định khi gặp giờ bị bỏ hoặc trùng: từ chối, điều chỉnh, chọn độ lệch sớm/muộn theo hợp đồng. API có cách phân giải mặc định, nhưng mặc định kỹ thuật không tự thay thế yêu cầu nghiệp vụ.

Nếu đã có `Instant`, việc tra cách nhìn của nó trong vùng không có sự mơ hồ chọn giữa hai thời điểm như khi bắt đầu chỉ từ một giờ địa phương. Điều này giải thích vì sao mô hình lưu sự kiện và mô hình lưu ý định lịch hẹn có thể khác nhau.

## 8. ID không phải bản chụp quy tắc

Dữ liệu quy tắc vùng thường đến từ TZDB hoặc nhà cung cấp quy tắc của runtime. Lưu `Europe/Paris` rồi gọi `ZoneId.of()` ở một runtime khác sẽ dùng quy tắc mà runtime đó có, không tự tải đúng bản dữ liệu của thời điểm lưu.

Nếu yêu cầu chỉ là tiếp tục áp dụng quy tắc vùng được cập nhật cho lịch tương lai, ID là thông tin quan trọng cần giữ. Nếu yêu cầu tái lập tuyệt đối một phép tính cũ, phải xác định thêm cách quản lý phiên bản/dữ liệu quy tắc; không gọi một chuỗi ID là toàn bộ quy tắc đã được bảo quản.

Cần kiểm tra ID khi đọc/ghi theo hợp đồng. `ZoneId.of()` từ chối mã không hợp lệ như ví dụ `Europe/Paris_typo`; đừng âm thầm đổi nó thành UTC rồi tiếp tục coi bản ghi đúng. Với hệ thống chỉ nhận vùng chuẩn nhất định, có thể cần thêm kiểm tra theo tập ID được hỗ trợ; một ID độ lệch cố định hợp lệ về Java chưa chắc đáp ứng yêu cầu “vùng địa lý” của nghiệp vụ.

Chuỗi `ZonedDateTime.toString()` có thể chứa đoạn `[Europe/Paris]`, thuận tiện cho Java nhưng không nên mặc định mọi bên nhận đều hỗ trợ cú pháp đó. Hợp đồng tách Instant và `zoneId` giúp chỉ rõ từng thuộc tính cần được bên nhận bảo toàn.

Bài tập: lưu một sự kiện ở `Europe/Berlin` tại cùng Instant mùa đông trong ví dụ. Xác nhận độ lệch có thể bằng Paris nhưng ID đã lưu phải vẫn là `Europe/Berlin`. Sau đó thử chỉ lưu `+01:00` và giải thích vì sao không thể khôi phục chắc chắn vùng ban đầu hoặc giữ đúng 09:00 của lịch mùa hè chỉ từ độ lệch ấy.
