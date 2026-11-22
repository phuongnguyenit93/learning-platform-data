# Chuyển `ZonedDateTime` thành `OffsetDateTime` và thông tin bị mất

Trong Java, `ZonedDateTime` biểu diễn một ngày giờ gắn với **vùng thời gian** (`ZoneId`) và offset đã được xác định theo quy tắc vùng tại thời điểm đó. `OffsetDateTime` chỉ giữ **ngày giờ địa phương + offset cố định so với UTC**, không giữ tên vùng địa lý cùng quy tắc đổi offset theo lịch sử, DST hay tương lai.

Phương thức `ZonedDateTime.toOffsetDateTime()` rất hữu ích khi cần trao đổi timestamp đã có offset, nhưng phép chuyển đổi này **không bảo toàn toàn bộ ý nghĩa vùng thời gian**. Nói chính xác:

- **Giữ:** năm, tháng, ngày, giờ, phút, giây, nano giây của giá trị địa phương; offset đang có; thời điểm tương ứng (`Instant`).
- **Mất:** `ZoneId` vùng như `America/New_York` hay `Europe/Berlin`, nếu nguồn sử dụng ID vùng; khả năng truy xuất trực tiếp lịch sử và các quy tắc đổi offset của vùng từ chính kết quả `OffsetDateTime`.
- **Hệ quả:** cùng một timestamp hiện tại vẫn chính xác, nhưng tính lịch tương lai hay đổi ngày qua DST có thể khác nếu chỉ còn offset cố định.

Đây là một ví dụ về **chuyển đổi kiểu có mất thông tin** (*lossy conversion*) về ngữ nghĩa vùng, dù không làm mất phần nano giây hay thay đổi `Instant` tại thời điểm chuyển đổi.

## 1. Nhắc lại vai trò của từng kiểu

| Kiểu | Giữ ngày giờ địa phương | Giữ offset | Giữ ID vùng có quy tắc | Xác định được `Instant` |
| --- | --- | --- | --- | --- |
| `LocalDateTime` | Có | Không | Không | Chưa |
| `OffsetDateTime` | Có | Có, cố định trong giá trị | Không | Có |
| `ZonedDateTime` với vùng IANA | Có | Có, được phân giải từ vùng tại ngày giờ đó | Có | Có |
| `Instant` | Không biểu diễn trường địa phương riêng | Không | Không | Chính là thời điểm |

Ví dụ hai ID vùng `America/New_York` và `America/Toronto` có thể cùng offset `-05:00` tại ngày 15/01/2024. Chuyển `ZonedDateTime` của cả hai sang `OffsetDateTime` có thể cho **cùng một giá trị**. Không có phương thức toán học nào lấy lại chính xác tên vùng ban đầu chỉ từ ngày giờ và offset: có thể có nhiều vùng khớp nhau.

Cũng cần phân biệt `ZoneOffset` với `ZoneId`:

- `ZoneOffset.of("-05:00")` là độ lệch **cố định** UTC−05:00.
- `ZoneId.of("America/New_York")` là ID vùng có **bộ quy tắc**: tháng 1/2024 là `-05:00`, nhưng tháng 7/2024 là `-04:00`.
- Một `ZonedDateTime` cũng có thể sử dụng `ZoneOffset` làm chính `ZoneId`. Trong trường hợp nguồn vốn chỉ có offset cố định, không tồn tại danh tính vùng IANA để mất. Bài học nhấn mạnh trường hợp nguồn có ID vùng thực sự.

## 2. Cách chuyển bằng `toOffsetDateTime()`

```java
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime zoned = ZonedDateTime.of(
        2024, 1, 15, 9, 0, 0, 0, zone);

OffsetDateTime offset = zoned.toOffsetDateTime();

System.out.println(zoned);
// 2024-01-15T09:00-05:00[America/New_York]

System.out.println(offset);
// 2024-01-15T09:00-05:00
```

`toOffsetDateTime()` lấy các trường ngày giờ và **offset tại thời điểm đang xét** của `ZonedDateTime`. Kết quả là một kiểu giá trị bất biến. Không có chuyển động thời gian hoặc tái tính giờ địa phương khi chuyển; `zoned` cũng không bị sửa đổi.

Sơ đồ khái niệm:

```text
ZonedDateTime
2024-01-15T09:00-05:00[America/New_York]
       |
       | toOffsetDateTime()
       v
OffsetDateTime
2024-01-15T09:00-05:00
                 |
                 +-- local date/time: còn
                 +-- offset -05:00: còn
                 +-- Instant 14:00Z: còn
                 +-- "America/New_York": MẤT
                 +-- quy tắc DST vùng: không còn trong giá trị
```

Từ một giá trị `OffsetDateTime`, gọi `toInstant()` vẫn chính xác vì ngày, giờ và offset là đủ để tính mốc UTC.

```java
System.out.println(zoned.toInstant());
// 2024-01-15T14:00:00Z

System.out.println(offset.toInstant());
// 2024-01-15T14:00:00Z

System.out.println(zoned.toInstant().equals(offset.toInstant()));
// true
```

**Điểm cần nhớ:** “Mất zone” **không phải** “mất offset”. Hai khái niệm này khác nhau về dữ liệu và ngữ nghĩa.

## 3. Bảng kiểm kê: chính xác đã giữ và mất gì?

| Thuộc tính của `zoned` ban đầu | Trạng thái sau `toOffsetDateTime()` | Cách kiểm chứng |
| --- | --- | --- |
| Ngày ISO | Giữ nguyên | `toLocalDate()` |
| Giờ địa phương (đến nano giây) | Giữ nguyên | `toLocalTime()`, `getNano()` |
| Offset tại thời điểm | Giữ nguyên | `getOffset()` |
| Thời điểm tuyệt đối | Giữ nguyên | `toInstant()` |
| ID vùng `America/New_York` | **Không giữ** | `OffsetDateTime` không có `getZone()` |
| Quy tắc đổi offset theo mùa/lịch sử | **Không giữ dưới dạng vùng** | `OffsetDateTime` chỉ mang `ZoneOffset` |
| Khả năng biết offset của vùng ngày khác | **Không thể suy ra duy nhất** | Cần `ZoneId` thực và dữ liệu quy tắc vùng |
| Thông tin locale/tên hiển thị ban đầu | Không được lưu bởi hai kiểu này | Phải quản lý locale/format riêng |

Nếu xử lý một bản ghi **đã xảy ra**, `OffsetDateTime` có thể hoàn toàn đủ để gửi timestamp chính xác. Nếu xử lý “mỗi ngày 09:00 tại New York”, offset lấy từ một ngày **không** thay thế được ID vùng cho các lần đặt lịch kế tiếp.

### `equals()` và `toInstant()` trả lời câu hỏi khác nhau

`ZonedDateTime.equals(...)` kiểm tra giá trị ngày giờ, offset và zone trong **cùng kiểu**. Sau khi đổi thành `OffsetDateTime`, không thể so sánh trực tiếp bằng `equals` rồi kỳ vọng chúng tương đương về đối tượng/kiểu:

```java
boolean sameObjectValue = zoned.equals(offset);   // false
boolean sameInstant = zoned.toInstant()
        .equals(offset.toInstant());               // true
```

Để so sánh **thời điểm**, chuyển cả hai về `Instant`. Không coi `equals()` giữa các kiểu khác nhau là phép kiểm tra khả năng bảo toàn thời điểm.

## 4. Có đổi ngược `OffsetDateTime` thành `ZonedDateTime` được không?

**Đổi được kiểu, nhưng không tự khôi phục vùng gốc.**

`OffsetDateTime.toZonedDateTime()` tạo `ZonedDateTime` với **zone là chính offset hiện tại**, không tự biết vùng `America/New_York` của dữ liệu nguồn.

```java
OffsetDateTime offset = zoned.toOffsetDateTime();
ZonedDateTime fromOffset = offset.toZonedDateTime();

System.out.println(fromOffset);
// 2024-01-15T09:00-05:00

System.out.println(fromOffset.getZone());
// -05:00

System.out.println(zoned.equals(fromOffset));
// false

System.out.println(zoned.toInstant().equals(fromOffset.toInstant()));
// true
```

Kết quả vẫn là một `ZonedDateTime` hợp lệ, nhưng `getZone()` là `ZoneOffset` `-05:00` chứ không phải vùng `America/New_York`. Đây **không phải khôi phục nguyên vẹn**.

### Nếu còn lưu `ZoneId` gốc

Khi hệ thống biết rõ ID vùng từ trường dữ liệu riêng, có thể gắn lại thông qua:

```java
ZoneId originalZone = ZoneId.of("America/New_York");

ZonedDateTime recovered = offset.atZoneSameInstant(originalZone);

System.out.println(recovered);
// 2024-01-15T09:00-05:00[America/New_York]

System.out.println(recovered.toInstant()
        .equals(offset.toInstant()));
// true
```

`OffsetDateTime.atZoneSameInstant(zone)` **giữ nguyên instant**, rồi biểu diễn nó theo quy tắc của vùng được cung cấp. Đó là phép chuyển có thêm **thông tin ngoài** `OffsetDateTime`, không phải suy luận lại vùng từ offset.

Cẩn thận: nếu gắn vùng khác, kết quả vẫn là **cùng instant** nhưng ngày/giờ và offset có thể thay đổi.

```java
System.out.println(offset.atZoneSameInstant(ZoneId.of("Asia/Tokyo")));
// 2024-01-15T23:00+09:00[Asia/Tokyo]
```

Vùng Tokyo ở đây là **lựa chọn mới của ứng dụng**, không chứng minh sự kiện gốc xảy ra tại Tokyo.

### `atZoneSimilarLocal(...)` không giống `atZoneSameInstant(...)`

Java còn cung cấp `OffsetDateTime.atZoneSimilarLocal(zone)`, mục tiêu là **cố giữ ngày giờ địa phương** khi gắn vùng mới; nếu offset cũ hợp lệ tại vùng và local time đó thì ưu tiên giữ, nếu không sẽ phân giải theo quy tắc vùng. Nó **có thể thay đổi instant**.

Ví dụ `2024-01-15T09:00-05:00` gắn vào Tokyo:

```java
ZoneId tokyo = ZoneId.of("Asia/Tokyo");

ZonedDateTime sameInstant = offset.atZoneSameInstant(tokyo);
ZonedDateTime similarLocal = offset.atZoneSimilarLocal(tokyo);

System.out.println(sameInstant);
// 2024-01-15T23:00+09:00[Asia/Tokyo]

System.out.println(similarLocal);
// 2024-01-15T09:00+09:00[Asia/Tokyo]
```

Một bên cùng instant, một bên cùng đồng hồ 09:00; **không** dùng `atZoneSimilarLocal` cho việc chỉ đổi múi giờ hiển thị của một giao dịch đã xảy ra. Với gap hoặc overlap, quy tắc phân giải của `ZonedDateTime` còn có thể điều chỉnh giờ/offset.

## 5. Cùng offset không xác định một vùng duy nhất

Giả sử hai cuộc họp diễn ra lúc 09:00 ngày 15/01/2024 lần lượt theo giờ New York và Toronto:

```java
ZonedDateTime newYork = ZonedDateTime.of(
        2024, 1, 15, 9, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime toronto = ZonedDateTime.of(
        2024, 1, 15, 9, 0, 0, 0,
        ZoneId.of("America/Toronto"));

System.out.println(newYork.toOffsetDateTime()
        .equals(toronto.toOffsetDateTime()));
// true

System.out.println(newYork.getZone().equals(toronto.getZone()));
// false
```

Tại ngày đó hai vùng đều có `-05:00`. `OffsetDateTime` không có cách phân biệt New York với Toronto. Tình huống tương tự xảy ra giữa nhiều vùng khác trong thế giới, ngay cả khi quy tắc hiện tại trùng nhau: tên vùng vẫn là **dữ liệu ngữ cảnh** riêng.

Dùng `ZoneId` còn quan trọng khi hai vùng có cùng offset hôm nay nhưng **khác chính sách lịch sử, DST hoặc tương lai**. Chỉ biết `-05:00` lúc 09:00 không nói được offset vùng đó vào một ngày cụ thể khác.

## 6. Hậu quả thực tế: cộng một ngày qua DST

Xét New York trước ngày chuyển sang giờ mùa hè **10/03/2024**. Ngày 09/03, offset là `-05:00`; trưa 10/03 đã là `-04:00`.

```java
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, ny);

ZonedDateTime zonedNextDay = start.plusDays(1);
OffsetDateTime offsetOnly = start.toOffsetDateTime();
OffsetDateTime offsetNextDay = offsetOnly.plusDays(1);

System.out.println(start);
// 2024-03-09T12:00-05:00[America/New_York]

System.out.println(zonedNextDay);
// 2024-03-10T12:00-04:00[America/New_York]

System.out.println(offsetOnly);
// 2024-03-09T12:00-05:00

System.out.println(offsetNextDay);
// 2024-03-10T12:00-05:00
```

Hai phép `plusDays(1)` đều chuyển ngày địa phương lên một, nhưng:

- `ZonedDateTime.plusDays(1)` sử dụng **quy tắc vùng New York** của ngày mới và áp dụng offset `-04:00`.
- `OffsetDateTime.plusDays(1)` chỉ giữ **offset cố định `-05:00`**, vì trong chính giá trị `OffsetDateTime` không có ID vùng/quy tắc DST để tự cập nhật.

```text
Nguồn 09/03/2024 12:00 New York:
    2024-03-09T12:00-05:00 = 17:00Z

Đúng "ngày mai 12:00 New York":
    2024-03-10T12:00-04:00 = 16:00Z
    => 23 giờ thực trôi qua

Nếu đã bỏ vùng, chỉ giữ offset -05:00:
    2024-03-10T12:00-05:00 = 17:00Z
    => 24 giờ thực trôi qua
```

Vì thế việc chuyển sang `OffsetDateTime` là **an toàn để lưu mốc sự kiện của một lần cụ thể**, nhưng có thể gây lỗi khi muốn **tiếp tục tính lịch theo quy tắc địa phương**.

Nếu chuyển vào **mùa thu** khi New York rời DST (03/11/2024), hiệu ứng theo chiều ngược: một ngày lịch giữa hai buổi trưa có thể dài **25 giờ**, trong khi phép cộng theo `OffsetDateTime` với offset cố định vẫn dài 24 giờ.

### Vì sao chuyện này không chỉ là “mất tên để hiển thị”?

Mất `ZoneId` làm mất dữ liệu cần thiết để **xác định offset tương lai**, không chỉ mất một chuỗi trang trí trong log. `OffsetDateTime` không biết khi nào New York đổi từ `-05:00` sang `-04:00`. Do đó, lịch gửi thông báo hằng ngày, lịch họp và hạn chót theo “ngày mai cùng giờ địa phương” có thể bị lệch.

Lưu ý các vùng IANA có thể thay đổi chính sách theo quyết định của chính phủ và các phiên bản tzdb. Đối với lịch tương lai, giữ `ZoneId` giúp hệ thống sử dụng quy tắc của vùng theo dữ liệu thời gian hiện hành; cũng cần kế hoạch cập nhật và tính lại lịch khi quy tắc thay đổi.

## 7. Ví dụ hoàn chỉnh Java 17+ (độc lập, chạy được)

Tạo file **`ZonedToOffsetDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ZonedToOffsetDemo {
    public static void main(String[] args) {
        ZoneId newYorkZone = ZoneId.of("America/New_York");
        ZoneId torontoZone = ZoneId.of("America/Toronto");

        ZonedDateTime original = ZonedDateTime.of(
                2024, 1, 15, 9, 0, 0, 0, newYorkZone);
        OffsetDateTime converted = original.toOffsetDateTime();

        System.out.println("original = " + original);
        System.out.println("converted = " + converted);
        System.out.println("same instant = "
                + original.toInstant().equals(converted.toInstant()));
        System.out.println("offset retained = "
                + original.getOffset().equals(converted.getOffset()));
        System.out.println("nano retained = "
                + (original.getNano() == converted.getNano()));

        ZonedDateTime rebuiltWithoutRegion = converted.toZonedDateTime();
        System.out.println("rebuilt without region = "
                + rebuiltWithoutRegion);
        System.out.println("rebuilt zone = "
                + rebuiltWithoutRegion.getZone());
        System.out.println("original equals rebuilt = "
                + original.equals(rebuiltWithoutRegion));

        ZonedDateTime recoveredWithZone =
                converted.atZoneSameInstant(newYorkZone);
        System.out.println("restored with explicit zone = "
                + recoveredWithZone);
        System.out.println("restored equals original = "
                + original.equals(recoveredWithZone));

        ZonedDateTime asToronto =
                converted.atZoneSameInstant(torontoZone);
        System.out.println("Toronto same instant = " + asToronto);
        System.out.println("Toronto same offset date-time = "
                + asToronto.toOffsetDateTime().equals(converted));

        OffsetDateTime sameInstantUtc =
                converted.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime sameLocalUtc =
                converted.withOffsetSameLocal(ZoneOffset.UTC);
        System.out.println("UTC same instant = " + sameInstantUtc);
        System.out.println("UTC same local = " + sameLocalUtc);
        System.out.println("UTC local changes instant = "
                + !sameLocalUtc.toInstant().equals(converted.toInstant()));

        ZonedDateTime spring = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, newYorkZone);
        ZonedDateTime zonedNextDay = spring.plusDays(1);
        OffsetDateTime offsetNextDay =
                spring.toOffsetDateTime().plusDays(1);

        System.out.println("spring starting zoned = " + spring);
        System.out.println("zoned +1 calendar day = "
                + zonedNextDay);
        System.out.println("offset +1 calendar day = "
                + offsetNextDay);
        System.out.println("zoned elapsed hours = "
                + Duration.between(
                        spring.toInstant(),
                        zonedNextDay.toInstant()).toHours());
        System.out.println("offset elapsed hours = "
                + Duration.between(
                        spring.toInstant(),
                        offsetNextDay.toInstant()).toHours());
        System.out.println("different destination instants = "
                + !zonedNextDay.toInstant()
                        .equals(offsetNextDay.toInstant()));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac ZonedToOffsetDemo.java
java ZonedToOffsetDemo
```

Kết quả dự kiến khi môi trường dùng dữ liệu quy tắc New York/Toronto cho năm 2024:

```text
original = 2024-01-15T09:00-05:00[America/New_York]
converted = 2024-01-15T09:00-05:00
same instant = true
offset retained = true
nano retained = true
rebuilt without region = 2024-01-15T09:00-05:00
rebuilt zone = -05:00
original equals rebuilt = false
restored with explicit zone = 2024-01-15T09:00-05:00[America/New_York]
restored equals original = true
Toronto same instant = 2024-01-15T09:00-05:00[America/Toronto]
Toronto same offset date-time = true
UTC same instant = 2024-01-15T14:00Z
UTC same local = 2024-01-15T09:00Z
UTC local changes instant = true
spring starting zoned = 2024-03-09T12:00-05:00[America/New_York]
zoned +1 calendar day = 2024-03-10T12:00-04:00[America/New_York]
offset +1 calendar day = 2024-03-10T12:00-05:00
zoned elapsed hours = 23
offset elapsed hours = 24
different destination instants = true
```

Trong chương trình, `Duration` tính khoảng cách giữa các **instant**. Dòng `rebuilt zone = -05:00` chứng minh `toZonedDateTime()` không hồi sinh `America/New_York`. Dòng `restored equals original = true` thành công **vì chương trình cung cấp vùng gốc từ biến `newYorkZone`**, chứ `converted` không tự nhớ vùng ấy.

`Instant` được import trong ví dụ nhưng không bắt buộc khai báo biến `Instant` riêng; import không ảnh hưởng kết quả biên dịch hoặc runtime.

## 8. Cách chuyển đổi cùng instant và cùng giờ địa phương

Khi di chuyển dữ liệu giữa vùng, phải diễn đạt rõ yêu cầu:

| Ý định | API | Có giữ instant? | Có giữ giờ địa phương? |
| --- | --- | --- | --- |
| Bỏ vùng, giữ offset tại thời điểm | `zoned.toOffsetDateTime()` | Có | Có |
| Bỏ cả vùng và offset để giữ điểm thời gian | `zoned.toInstant()` | Có | Không lưu trực tiếp |
| Hiển thị `OffsetDateTime` ở vùng mới | `offset.atZoneSameInstant(zone)` | Có | Không nhất thiết |
| Cố giữ giờ đồng hồ, gắn vùng mới | `offset.atZoneSimilarLocal(zone)` | Không bảo đảm | Cố giữ, có thể điều chỉnh khi gap |
| Đổi offset trên `OffsetDateTime`, giữ instant | `offset.withOffsetSameInstant(newOffset)` | Có | Thường không |
| Đổi offset trên `OffsetDateTime`, giữ local time | `offset.withOffsetSameLocal(newOffset)` | Không, trừ khi offset không đổi | Có |
| Đưa `OffsetDateTime` thành `ZonedDateTime` dùng offset làm zone | `offset.toZonedDateTime()` | Có | Có |

**Lưu ý:** `OffsetDateTime` còn các phép so sánh như `isEqual`, `isBefore`, `isAfter` dựa trên instant. Hai `OffsetDateTime` có offset/local time khác nhau nhưng trỏ cùng instant có thể trả `equals == false` và `isEqual == true`:

```java
OffsetDateTime ny = OffsetDateTime.parse(
        "2024-01-15T09:00-05:00");
OffsetDateTime utc = OffsetDateTime.parse(
        "2024-01-15T14:00Z");

System.out.println(ny.equals(utc));  // false
System.out.println(ny.isEqual(utc)); // true
```

Đừng chuyển các đối tượng có biểu diễn khác nhau về cùng một múi giờ chỉ để có thể so sánh: dùng `toInstant()` khi câu hỏi là “cùng thời điểm hay không?”.

## 9. Thiết kế lưu trữ/trao đổi timestamp an toàn

### Trường hợp A — Log, sự kiện đã xảy ra, giao dịch toàn cầu

Nếu chỉ cần **thời điểm sự kiện**, `Instant` hoặc timestamp ISO kèm offset là đủ để xác định mốc thời gian:

```json
{
  "occurredAt": "2024-01-15T14:00:00Z"
}
```

Nếu cần biết sự kiện được ghi nhận theo giờ địa phương nào, lưu thêm `ZoneId` hoặc thông tin nguồn. Chỉ `Instant` không lưu vùng gốc.

### Trường hợp B — Cần hiển thị lại đúng vùng gốc

Lưu mốc UTC **và** vùng địa lý riêng:

```json
{
  "occurredAt": "2024-01-15T14:00:00Z",
  "zoneId": "America/New_York"
}
```

Có thể dựng `Instant.parse(occurredAt).atZone(ZoneId.of(zoneId))` để hiển thị theo vùng; kết quả dựa trên quy tắc timezone của môi trường. Nếu cần bảo toàn **chính xác ảnh chụp local time/offset đã được người dùng nhìn thấy** lúc tạo, cân nhắc lưu thêm các giá trị này hoặc phiên bản quy tắc liên quan, vì dữ liệu tzdb có thể thay đổi.

### Trường hợp C — Lịch tương lai, lịch lặp theo giờ địa phương

Ví dụ “09:00 mỗi ngày tại New York” không thể biểu diễn trọn vẹn bằng một `OffsetDateTime` hoặc `Instant` duy nhất. Nên lưu **`LocalTime`, `ZoneId` và quy tắc lặp**, cộng với ngày/ngoại lệ theo nghiệp vụ:

```json
{
  "localTime": "09:00:00",
  "zoneId": "America/New_York",
  "recurrence": "DAILY"
}
```

Khi chạy lịch cho từng ngày:

```java
LocalDate nextDate = LocalDate.of(2024, 3, 10);
LocalTime scheduledTime = LocalTime.of(9, 0);
ZoneId zoneId = ZoneId.of("America/New_York");

ZonedDateTime nextRun = nextDate.atTime(scheduledTime)
        .atZone(zoneId);
Instant triggerInstant = nextRun.toInstant();
```

Đây là ví dụ minh họa, cần import `java.time.LocalDate`, `LocalTime`, `ZoneId`, `ZonedDateTime`, `Instant`.

Nếu giờ lịch rơi vào DST gap hoặc overlap, phải xác định chính sách: dịch giờ, từ chối, hoặc chọn offset sớm/muộn. `ZoneRules.getValidOffsets(localDateTime)` giúp phát hiện trường hợp không có offset hoặc có hai offset.

### Trường hợp D — Chỉ nhận một `OffsetDateTime` từ đối tác

Nếu đối tác gửi:

```text
2024-01-15T09:00:00-05:00
```

Bạn **biết chắc instant** của chuỗi, nhưng **không biết chắc địa điểm**. Đừng đoán zone bằng cách xem danh sách vùng có cùng `-05:00` và lấy đại một vùng. Có thể hiển thị timestamp theo offset mà đối tác cung cấp, hoặc yêu cầu thêm trường `zoneId` nếu lịch sử/lịch tương lai có ý nghĩa.

## 10. Những lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách đúng |
| --- | --- | --- |
| “`toOffsetDateTime()` làm mất giờ UTC.” | Hiểu sai: instant được bảo toàn. | Kiểm bằng `toInstant()`; mất ID vùng, không mất instant. |
| “Giữ `-05:00` là giữ New York.” | Nhiều vùng có cùng offset. | Lưu `ZoneId` riêng nếu ngữ cảnh vùng quan trọng. |
| “`OffsetDateTime.toZonedDateTime()` lấy lại vùng gốc.” | Kết quả chỉ dùng offset làm zone. | Dùng ID vùng gốc lưu riêng và `atZoneSameInstant(zone)`. |
| “Cộng 1 ngày trên `OffsetDateTime` vẫn theo DST New York.” | Offset không tự chuyển `-05:00` ↔ `-04:00`. | Cộng ngày trên `ZonedDateTime` có ID vùng. |
| “Hai vùng có cùng offset thì là cùng một vùng.” | Mất nhận dạng địa điểm và quy tắc theo ngày. | Phân biệt `ZoneId` với `ZoneOffset`. |
| “Gắn zone mới bằng cách giữ local time sẽ giữ instant.” | `atZoneSimilarLocal` có thể đổi instant. | Dùng `atZoneSameInstant` nếu cần bảo toàn thời điểm. |
| “Đổi offset bằng `withOffsetSameLocal` là đổi múi giờ hiển thị.” | Instant thường thay đổi. | Dùng `withOffsetSameInstant` khi đổi cách hiển thị. |
| “`equals()` là cách duy nhất để kiểm tra cùng instant.” | Khác offset có thể cùng thời điểm. | Dùng `toInstant()` hoặc `isEqual` cùng kiểu. |
| “Có `Instant` là khôi phục được `ZoneId` gốc.” | Một instant được biểu diễn theo vô số vùng. | Lưu `ZoneId` như dữ liệu riêng. |
| “Dữ liệu timezone không bao giờ thay đổi.” | Lịch tương lai có thể sai nếu luật đổi. | Quản lý cập nhật tzdb và chính sách tính lại lịch. |

## 11. Checklist trước khi thay `ZonedDateTime` bằng `OffsetDateTime`

1. **Giá trị này là sự kiện đã xảy ra hay lịch tương lai?** Nếu lịch gắn địa điểm, thường cần giữ `ZoneId`.
2. **Có yêu cầu khôi phục vùng gốc không?** Nếu có, lưu trường `zoneId` riêng.
3. **Có yêu cầu bảo toàn instant không?** Xác minh bằng `source.toInstant().equals(converted.toInstant())`.
4. **Có phép cộng ngày/tuần/tháng/năm sau chuyển kiểu không?** Kiểm tra kỹ DST và quy tắc vùng: `OffsetDateTime` không tự cập nhật offset.
5. **Có đổi vùng để hiển thị không?** Dùng phương thức `SameInstant`, tránh nhầm với `SameLocal`.
6. **Có chấp nhận timezone lịch sử/tương lai thay đổi theo phiên bản dữ liệu không?** Thiết kế lưu metadata hoặc tái tính khi cần.
7. **Có kiểm thử ranh giới DST không?** Test cả mùa xuân, mùa thu, gap, overlap và ngày bình thường.

### Tự kiểm tra

**1.** Chuyển `2024-01-15T09:00-05:00[America/New_York]` sang `OffsetDateTime` được gì?  
→ `2024-01-15T09:00-05:00`, giữ offset, local time và instant.

**2.** Có thể tự biết `America/New_York` từ `2024-01-15T09:00-05:00` không?  
→ Không. Nhiều vùng có thể cùng offset tại thời điểm đó.

**3.** `offset.toZonedDateTime().getZone()` trả gì nếu `offset` là `2024-01-15T09:00-05:00`?  
→ `-05:00`, không phải `America/New_York`.

**4.** Vì sao `start.toOffsetDateTime().plusDays(1)` có thể khác `start.plusDays(1)` qua DST?  
→ `OffsetDateTime` giữ offset cố định; `ZonedDateTime` cập nhật offset theo quy tắc vùng ở ngày đích.

**5.** Có `OffsetDateTime` và ID vùng ban đầu lưu riêng; chuyển thế nào để giữ thời điểm?  
→ `offset.atZoneSameInstant(ZoneId.of(originalZoneId))`.

**6.** `offset.atZoneSameInstant(zone)` khác `offset.atZoneSimilarLocal(zone)` ở đâu?  
→ Cách đầu giữ instant; cách sau cố giữ ngày giờ địa phương và có thể đổi instant.

### Tài liệu API Java

- [Oracle Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): `toOffsetDateTime()`, `getZone()`, `getOffset()`, `plusDays()` và phân giải DST.
- [Oracle Java SE 17 — `OffsetDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html): `toZonedDateTime()`, `atZoneSameInstant()`, `atZoneSimilarLocal()`, `withOffsetSameInstant()`, `withOffsetSameLocal()`.
- [Oracle Java SE 17 — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): định danh và quy tắc múi giờ.
- [Oracle Java SE 17 — `ZoneRules`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): các offset hợp lệ trong DST gap/overlap.

**Ghi nhớ:** `ZonedDateTime.toOffsetDateTime()` là phép chuyển **bảo toàn instant nhưng mất thông tin vùng** nếu nguồn có ID vùng. Hãy dùng `OffsetDateTime` khi timestamp cùng offset là đủ; nếu cần lập lịch địa phương qua các lần đổi DST, **lưu `ZoneId` riêng** hoặc tiếp tục dùng `ZonedDateTime`.
