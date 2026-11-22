# Bản đồ chuyển đổi giữa các kiểu ngày giờ chính trong Java

Trong `java.time`, các kiểu dữ liệu thời gian **không chỉ khác tên**: mỗi kiểu mang một lượng thông tin và ý nghĩa khác nhau. Một `LocalDate` chỉ là ngày lịch, `LocalTime` chỉ là giờ đồng hồ, còn `Instant` biểu diễn mốc thời gian toàn cầu. Muốn chuyển giữa chúng đúng cách, trước tiên cần biết **đang có dữ liệu gì**, **cần giữ lại dữ liệu gì**, và **thông tin nào phải được bổ sung**.

Ví dụ, `2025-01-15T09:30` chưa thể tự chuyển thành một `Instant` duy nhất vì chưa biết nó là 09:30 tại Hà Nội, Paris hay New York. Ngược lại, `2025-01-15T02:30:00Z` là một `Instant` đã xác định; khi hiển thị tại Việt Nam vào ngày đó sẽ là 09:30, offset `+07:00`.

**Quy tắc gốc:** Chuyển từ thời điểm tuyệt đối sang giờ địa phương phải chọn **múi giờ/offset**; chuyển từ ngày giờ địa phương sang thời điểm tuyệt đối cũng phải chọn **múi giờ/offset và giải quyết giờ DST mơ hồ nếu có**. Các phép trích xuất ngày/giờ có thể **làm mất thông tin**, không nhất thiết chuyển ngược lại được.

## 1. Nhận diện tám thành phần thường gặp

| Kiểu | Có ngày? | Có giờ? | Offset / zone? | Xác định một `Instant`? | Ví dụ |
| --- | --- | --- | --- | --- | --- |
| `LocalDate` | Có | Không | Không | Không | `2025-01-15` |
| `LocalTime` | Không | Có | Không | Không | `09:30` |
| `LocalDateTime` | Có | Có | Không | **Không** | `2025-01-15T09:30` |
| `Instant` | Mốc thời gian tuyệt đối | Mốc thời gian tuyệt đối | Không lưu tên zone; thường biểu diễn UTC | **Có** | `2025-01-15T02:30:00Z` |
| `OffsetTime` | Không | Có | UTC offset cố định | Không, vì thiếu ngày | `09:30+07:00` |
| `OffsetDateTime` | Có | Có | UTC offset cố định | **Có** | `2025-01-15T09:30+07:00` |
| `ZonedDateTime` | Có | Có | `ZoneId` và offset ứng với thời điểm | **Có** | `2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]` |
| `ZoneId` / `ZoneOffset` | Không phải thời gian | Không phải thời gian | Quy tắc vùng / độ lệch UTC | Tự nó không | `Asia/Ho_Chi_Minh` / `+07:00` |

Hai kiểu quan trọng khác nhưng **không phải điểm thời gian**:

- `Duration`: **thời lượng đã trôi** đo theo giây/nano giây, chẳng hạn `PT1H30M`. Nó không tự có ngày bắt đầu hay múi giờ.
- `Period`: **khoảng theo lịch** (năm, tháng, ngày), chẳng hạn `P1M`. Một tháng không thể đổi thành một số giây cố định nếu chưa chọn ngày/vùng áp dụng.

**Đừng nhầm `LocalDateTime` với `Instant`:** chữ “Local” là thông tin cốt lõi. Nó không lưu offset và không phải timestamp toàn cầu. Tên kiểu nào đã có zone hoặc offset phải được ghi rõ trong tên biến/hợp đồng API khi dữ liệu đi qua nhiều hệ thống.

## 2. Bản đồ tổng quan các nhánh chuyển đổi

```text
                       LocalDate + LocalTime
                         |           |
                         +---- of() --+
                               |
                               v
                         LocalDateTime
                         /           \
                atZone(ZoneId)    atOffset(ZoneOffset)
                     /                 \
                    v                   v
              ZonedDateTime       OffsetDateTime
                  |     \             /     |
      toLocal*()  |      toInstant()  /      | toLocal*()
                  |         \        /       |
                  v          v      v        v
           LocalDate/Time       Instant    LocalDateTime
                 ^               |   |
                 |   atZone(zone)|   |atOffset(offset)
                 +---------------+---+
                                 |
                     Date.from / Date.toInstant
                                 |
                          java.util.Date
```

Đây là sơ đồ định hướng, không phải tất cả mũi tên đều hoàn toàn đối xứng. Chú ý:

1. `Instant → ZonedDateTime` với một `ZoneId` là ánh xạ **không mơ hồ**: `instant.atZone(zone)`.
2. `Instant → OffsetDateTime` với một `ZoneOffset` cũng không mơ hồ: `instant.atOffset(offset)`.
3. `LocalDateTime → ZonedDateTime` cần `ZoneId`; tại DST gap/overlap còn cần biết chính sách xử lý.
4. `LocalDateTime → OffsetDateTime` chỉ cần `ZoneOffset` được cung cấp; cách này **không tự kiểm tra offset có hợp lệ trong một vùng địa lý hay không**, vì vùng không phải đầu vào.
5. `ZonedDateTime/OffsetDateTime → Instant` có thể làm bằng `toInstant()`. Nếu bỏ zone/offset bằng `toLocalDateTime()`, bạn **mất dữ liệu phân biệt mốc thực**.
6. `LocalDate` và `LocalTime` có thể ghép thành `LocalDateTime` bằng `date.atTime(time)`, nhưng không thể tự đi tới `Instant` nếu chưa bổ sung vùng/offset.
7. `java.util.Date` có thể nối với `Instant`, nhưng giới hạn độ chính xác tới **mili giây**.

## 3. Bản đồ phương thức cụ thể: từ đâu sang đâu?

| Từ kiểu | Sang kiểu | Cách chuyển đổi chuẩn | Cần thêm thông tin hoặc có mất mát? |
| --- | --- | --- | --- |
| `LocalDate` + `LocalTime` | `LocalDateTime` | `LocalDateTime.of(date, time)` hoặc `date.atTime(time)` | Ghép ngày và giờ đã có, không gắn zone. |
| `LocalDateTime` | `LocalDate` | `local.toLocalDate()` | **Bỏ phần giờ**. |
| `LocalDateTime` | `LocalTime` | `local.toLocalTime()` | **Bỏ phần ngày**. |
| `Instant` | `ZonedDateTime` | `instant.atZone(zone)` | **Cần `ZoneId`**, giữ nguyên mốc. |
| `Instant` | `OffsetDateTime` | `instant.atOffset(offset)` | **Cần `ZoneOffset`**, giữ nguyên mốc. |
| `Instant` | `LocalDateTime` | `LocalDateTime.ofInstant(instant, zone)` | **Cần vùng/offset**, bỏ thông tin đó trong kết quả. |
| `ZonedDateTime` | `Instant` | `zoned.toInstant()` | Giữ mốc, **mất tên vùng** trong kiểu trả về. |
| `OffsetDateTime` | `Instant` | `offsetDateTime.toInstant()` | Giữ mốc, **mất offset hiển thị** trong kiểu trả về. |
| `ZonedDateTime` | `LocalDateTime` | `zoned.toLocalDateTime()` | **Mất vùng + offset**. |
| `OffsetDateTime` | `LocalDateTime` | `offsetDateTime.toLocalDateTime()` | **Mất offset**. |
| `ZonedDateTime` | `LocalDate` / `LocalTime` | `zoned.toLocalDate()` / `zoned.toLocalTime()` | Chỉ lấy ngày hoặc giờ, bỏ những phần khác. |
| `OffsetDateTime` | `OffsetTime` | `offsetDateTime.toOffsetTime()` | **Bỏ ngày**, còn giờ + offset. |
| `LocalTime` + `ZoneOffset` | `OffsetTime` | `time.atOffset(offset)` | Thêm offset, vẫn thiếu ngày. |
| `OffsetTime` + `LocalDate` | `OffsetDateTime` | `offsetTime.atDate(date)` hoặc `date.atTime(offsetTime)` | Thêm ngày, có thể đổi sang `Instant`. |
| `LocalDateTime` | `ZonedDateTime` | `local.atZone(zone)` | Cần vùng; có quy tắc mặc định xử lý DST. |
| `LocalDateTime` | `OffsetDateTime` | `local.atOffset(offset)` | Cần offset cố định; chưa kiểm tra `ZoneRules`. |
| `OffsetDateTime` | `ZonedDateTime` | `offsetDateTime.atZoneSameInstant(zone)` | Cần vùng; **giữ mốc**, giờ địa phương có thể đổi. |
| `ZonedDateTime` | `OffsetDateTime` | `zoned.toOffsetDateTime()` | Giữ mốc và offset hiện tại; mất tên vùng. |
| `ZonedDateTime` | `ZonedDateTime` ở vùng khác | `zoned.withZoneSameInstant(otherZone)` | **Giữ `Instant`**, thường đổi giờ hiển thị. |
| `LocalDate` | `ZonedDateTime` đầu ngày | `date.atStartOfDay(zone)` | Cần `ZoneId`, theo thời điểm đầu ngày hợp lệ trong vùng. |
| `Instant` | `java.util.Date` | `Date.from(instant)` | Có thể **mất phần nhỏ hơn mili giây**. |
| `java.util.Date` | `Instant` | `date.toInstant()` | Giá trị `Date` chỉ có độ chính xác mili giây. |

**Hai hướng khác nhau:** Khi lấy các thành phần từ một giá trị phong phú hơn như `ZonedDateTime.toLocalDateTime()`, thông tin bị bỏ có thể làm **không chuyển ngược chính xác được**. Ngược lại, chuyển từ `Instant` sang kiểu có zone được cung cấp là một phép biểu diễn của **cùng mốc thực**. Để hoàn nguyên về thời điểm ban đầu, cần giữ các thông tin bổ sung thích hợp.

## 4. Chuyển từ `Instant` sang giờ của người dùng

Giả sử một sự kiện diễn ra tại:

```text
2025-01-15T02:30:00Z
```

Người dùng Việt Nam cần xem giờ tại `Asia/Ho_Chi_Minh`. Tạo `ZonedDateTime`:

```java
Instant event = Instant.parse("2025-01-15T02:30:00Z");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localView = event.atZone(vietnam);
// 2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]
```

Đoạn minh họa cần `import java.time.*;`. `atZone` **không làm sự kiện diễn ra muộn hơn 7 giờ**. Nó chỉ thay biểu diễn của cùng `Instant` bằng giờ địa phương và offset phù hợp. Khi chuyển về:

```java
Instant sameEvent = localView.toInstant();
// 2025-01-15T02:30:00Z
```

Bạn cũng có thể chuyển thẳng thành ngày giờ địa phương:

```java
LocalDateTime displayOnly =
        LocalDateTime.ofInstant(event, vietnam);
// 2025-01-15T09:30
```

Kết quả chỉ còn `LocalDateTime`, nghĩa là thông tin zone đã **không được lưu trong đối tượng mới**. Nếu hệ thống muốn hiển thị, điều đó thường phù hợp; nếu cần trao đổi timestamp toàn cầu, lưu `Instant` và `ZoneId` riêng nếu có nhu cầu.

### `ZoneId` khác `ZoneOffset`

- `ZoneId.of("Asia/Ho_Chi_Minh")` đại diện cho **vùng có quy tắc theo lịch sử/tương lai**. `ZonedDateTime` có thể được áp các quy tắc vùng tương ứng.
- `ZoneOffset.ofHours(7)` chỉ đại diện độ lệch **cố định +07:00**. Nó không chứa tên thành phố hoặc toàn bộ lịch sử quy tắc vùng.
- `OffsetDateTime` có thể cho một timestamp toàn cầu đầy đủ khi có ngày, giờ và offset, nhưng nếu nghiệp vụ cần lịch lặp ở một nơi, giữ `ZoneId` vẫn quan trọng.

Đối với một `Instant` đã biết, dùng `event.atOffset(ZoneOffset.ofHours(7))` sẽ cho `OffsetDateTime` `2025-01-15T09:30+07:00`, vẫn trỏ tới cùng `Instant` đó.

## 5. Từ ngày giờ địa phương tới thời điểm toàn cầu

`LocalDateTime.of(2025, 1, 15, 9, 30)` tự nó **không xác định** một `Instant`. Phải bổ sung vùng hoặc offset.

### Có `ZoneId`: tạo `ZonedDateTime` rồi `Instant`

```java
LocalDateTime local = LocalDateTime.of(2025, 1, 15, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant moment = zoned.toInstant();
// 2025-01-15T02:30:00Z
```

Cách này **áp dụng `ZoneRules`** của vùng. Với giờ bình thường, có một offset hợp lệ. Nhưng qua DST:

- **Gap:** giờ địa phương có thể không tồn tại. `atZone(zone)` mặc định điều chỉnh qua khoảng bị khuyết.
- **Overlap:** giờ địa phương có thể ứng với **hai offset**. `atZone(zone)` mặc định thường chọn offset sớm hơn trên dòng thời gian; nghiệp vụ có thể phải chọn lần sau hoặc từ chối mơ hồ.

### Có `ZoneOffset`: tính mốc từ offset cố định

```java
LocalDateTime local = LocalDateTime.of(2025, 1, 15, 9, 30);
ZoneOffset offset = ZoneOffset.ofHours(7);

Instant moment = local.toInstant(offset);
OffsetDateTime offsetValue = local.atOffset(offset);
// Cả moment và offsetValue.toInstant() là 2025-01-15T02:30:00Z
```

`toInstant(offset)` và `atOffset(offset).toInstant()` dùng **offset đã cung cấp**, chứ không kiểm tra nó có phù hợp với một `ZoneId` địa lý nào hay không. Nếu dữ liệu đến từ một lịch hẹn tại thành phố có DST, hãy dùng vùng thực và giải quyết gap/overlap rõ ràng, không ép offset được suy đoán.

### Tại sao không gọi `local.toInstant()` không tham số?

Bởi `LocalDateTime` không chứa vùng hoặc offset để xác định một mốc thực, Java cần bạn truyền `ZoneOffset` nếu dùng `toInstant` trực tiếp. Bạn không thể suy luận UTC từ chuỗi `2025-01-15T09:30` chỉ vì tên trường trong DB là `createdAt`.

## 6. Ghép và tách `LocalDate`, `LocalTime`, `LocalDateTime`

Khi dữ liệu UI có hai input riêng:

```java
LocalDate date = LocalDate.of(2025, 1, 15);
LocalTime time = LocalTime.of(9, 30);

LocalDateTime local = LocalDateTime.of(date, time);
// Tương đương: date.atTime(time)
// Tương đương: time.atDate(date)
```

Lấy ngược từng phần:

```java
LocalDate extractedDate = local.toLocalDate();
LocalTime extractedTime = local.toLocalTime();
```

Các đoạn này minh họa bên trong một phương thức có `import java.time.*;`. **Ghép ngày + giờ không đồng nghĩa gắn múi giờ.** Ngược lại, trích riêng ngày hoặc giờ làm mất thông tin còn lại.

Nếu chỉ có `LocalDate` và muốn mốc đầu ngày cho một vùng, dùng:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime startOfBusinessDay = date.atStartOfDay(zone);
Instant dayStart = startOfBusinessDay.toInstant();
```

`date.atTime(LocalTime.MIDNIGHT)` chỉ tạo `LocalDateTime` tại `00:00`, chưa gắn vùng. `date.atStartOfDay(zone)` tìm **thời điểm đầu ngày hợp lệ theo vùng**; tại một số vùng có đổi offset ngay nửa đêm, hai cách không được xem là hoàn toàn tương đương ở bước xác định mốc thực.

### Bổ sung offset cho giờ không có ngày

`OffsetTime` mang giờ đồng hồ và offset, nhưng **chưa có ngày**:

```java
OffsetTime officeTime = LocalTime.of(9, 30)
        .atOffset(ZoneOffset.ofHours(7));
// 09:30+07:00

OffsetDateTime dated = officeTime.atDate(LocalDate.of(2025, 1, 15));
// 2025-01-15T09:30+07:00

Instant instant = dated.toInstant();
// 2025-01-15T02:30:00Z
```

Muốn có `Instant` phải thêm ngày; `OffsetTime` một mình không đủ. Offset cũng không thay `ZoneId` khi lịch giờ làm việc lặp theo vùng có quy tắc đổi giờ.

## 7. Ví dụ Java 17+ hoàn chỉnh: đi qua các kiểu chính

Tạo tệp **`DateTimeConversionMapDemo.java`**. Ví dụ cố định `Instant` để output không phụ thuộc thời gian chạy và múi giờ mặc định của JVM:

```java
import java.time.*;
import java.util.Date;

public class DateTimeConversionMapDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2025-01-15T02:30:00Z");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        ZonedDateTime zoned = instant.atZone(zone);
        LocalDate localDate = zoned.toLocalDate();
        LocalTime localTime = zoned.toLocalTime();
        LocalDateTime localDateTime =
                LocalDateTime.of(localDate, localTime);
        ZoneOffset offset = zoned.getOffset();
        OffsetDateTime offsetDateTime = instant.atOffset(offset);
        OffsetTime offsetTime = offsetDateTime.toOffsetTime();

        System.out.println("Instant           : " + instant);
        System.out.println("ZonedDateTime     : " + zoned);
        System.out.println("LocalDate         : " + localDate);
        System.out.println("LocalTime         : " + localTime);
        System.out.println("LocalDateTime     : " + localDateTime);
        System.out.println("OffsetDateTime    : " + offsetDateTime);
        System.out.println("OffsetTime        : " + offsetTime);
        System.out.println("Round-trip via zone   : "
                + localDateTime.atZone(zone).toInstant());
        System.out.println("Round-trip via offset : "
                + localDateTime.toInstant(offset));
        System.out.println("Date + time       : "
                + localDate.atTime(localTime));
        System.out.println("Epoch millis      : "
                + instant.toEpochMilli());

        Date legacy = Date.from(instant);
        System.out.println("Legacy round-trip : "
                + legacy.toInstant());
        System.out.println("Time preserved    : "
                + instant.equals(legacy.toInstant()));
    }
}
```

Lệnh chạy JDK 17+:

```bash
javac DateTimeConversionMapDemo.java
java DateTimeConversionMapDemo
```

Kết quả đã biên dịch và kiểm tra:

```text
Instant           : 2025-01-15T02:30:00Z
ZonedDateTime     : 2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]
LocalDate         : 2025-01-15
LocalTime         : 09:30
LocalDateTime     : 2025-01-15T09:30
OffsetDateTime    : 2025-01-15T09:30+07:00
OffsetTime        : 09:30+07:00
Round-trip via zone   : 2025-01-15T02:30:00Z
Round-trip via offset : 2025-01-15T02:30:00Z
Date + time       : 2025-01-15T09:30
Epoch millis      : 1736908200000
Legacy round-trip : 2025-01-15T02:30:00Z
Time preserved    : true
```

**Đọc kết quả:**

1. `Instant` cố định ở `02:30Z`, còn `ZonedDateTime` hiển thị `09:30+07:00`. Hai biểu diễn là **cùng mốc thực**.
2. `LocalDate` và `LocalTime` được trích từ `zoned`; `LocalDateTime.of(date, time)` ghép lại ngày giờ. Việc tách và ghép ở đây chưa làm mất chữ số ngày/giờ, nhưng **bản thân giá trị mới không còn mang vùng hay offset**.
3. `OffsetDateTime` biểu diễn ngày/giờ với `+07:00`, nên có thể đổi thẳng về `Instant`. `OffsetTime` chỉ giữ giờ `09:30+07:00`, không còn ngày.
4. Hai đường round-trip trả lại `Instant` ban đầu vì ngày, giờ, zone và offset đã biết ở đây là nhất quán, và ví dụ không nằm trong DST gap/overlap.
5. `Date.from(instant)` và `legacy.toInstant()` bảo toàn mốc trong ví dụ vì nó có độ chính xác đến giây, phù hợp giới hạn mili giây của `java.util.Date`.

## 8. Những chuyển đổi không thể đảo ngược mà không thêm dữ liệu

| Đã thực hiện | Thông tin mất | Muốn khôi phục cần gì? |
| --- | --- | --- |
| `ZonedDateTime → LocalDateTime` | Zone và offset | Cần zone/offset ban đầu; overlap có thể cần cả lựa chọn offset. |
| `OffsetDateTime → LocalDateTime` | Offset | Cần offset gốc để biết `Instant` ban đầu. |
| `ZonedDateTime → LocalDate` | Giờ, zone, offset | Cần giờ và chính sách vùng; chỉ ngày không thể suy ra sự kiện cụ thể. |
| `ZonedDateTime → LocalTime` | Ngày, zone, offset | Cần ngày và vùng/offset. |
| `OffsetDateTime → OffsetTime` | Ngày | Cần ngày gốc. |
| `Instant → LocalDateTime` | Thông tin zone dùng để biểu diễn | Cần giữ zone ban đầu; áp zone khác sẽ tạo mốc khác từ cùng giờ địa phương. |
| `ZonedDateTime → OffsetDateTime` | Tên `ZoneId` với quy tắc vùng | Cần vùng gốc nếu muốn lịch tương lai theo quy tắc địa điểm. |
| `Instant → java.util.Date` | Phần nhỏ hơn mili giây | Không khôi phục được phần nano giây đã mất. |

**Ví dụ hai `Instant` cùng một giờ địa phương:** `2024-11-03T01:30` ở New York có thể là `2024-11-03T05:30:00Z` (offset `-04:00`) hoặc `2024-11-03T06:30:00Z` (offset `-05:00`). Nếu chuyển cả hai thành `LocalDateTime` bằng cách bỏ offset, chúng trở thành cùng một giá trị và không thể tự biết mốc gốc.

Không nên dùng phép chuyển đổi về kiểu “ít thông tin” rồi xem đó là định dạng lưu timestamp toàn cầu. Đối với event log, thanh toán, bản ghi hệ thống, **ưu tiên `Instant`** và lưu thêm `ZoneId` khi cần bảo tồn ngữ cảnh địa phương.

## 9. Bản đồ cần DST: *gap*, *overlap* và chiều chuyển đổi

Một `Instant` luôn tương ứng với **một** ngày giờ địa phương trong một `ZoneId` tại một mốc xác định. Nhưng chiều ngược lại, `LocalDateTime + ZoneId → Instant` có thể:

- Có **một** offset hợp lệ (giờ bình thường).
- Có **không** offset hợp lệ (gap, giờ bị nhảy qua).
- Có **hai** offset hợp lệ (overlap, giờ bị lặp).

Java cho kiểm tra bằng `zone.getRules().getValidOffsets(local)`. Với `local.atZone(zone)`, mặc định giờ trong gap được đẩy sang giờ hợp lệ và overlap thường chọn offset sớm; nghiệp vụ có thể cần chính sách khác.

### Ví dụ Java 17+: chuyển qua gap/overlap

Tạo tệp **`ConversionDstDemo.java`**:

```java
import java.time.*;
import java.util.List;

public class ConversionDstDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime overlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> choices =
                zone.getRules().getValidOffsets(overlap);
        ZonedDateTime earlier =
                overlap.atZone(zone).withEarlierOffsetAtOverlap();
        ZonedDateTime later =
                overlap.atZone(zone).withLaterOffsetAtOverlap();

        System.out.println("Overlap offsets : " + choices);
        System.out.println("Earlier instant : " + earlier.toInstant());
        System.out.println("Later instant   : " + later.toInstant());
        System.out.println("Same local      : " +
                earlier.toLocalDateTime()
                        .equals(later.toLocalDateTime()));

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("Gap offsets     : " +
                zone.getRules().getValidOffsets(gap));
        System.out.println("Gap resolved    : " + gap.atZone(zone));

        Instant fixed = Instant.parse("2024-03-10T07:30:00Z");
        System.out.println("Instant to zone : " + fixed.atZone(zone));

        LocalDate date = LocalDate.of(2024, 3, 10);
        System.out.println("Start of day    : "
                + date.atStartOfDay(zone));
    }
}
```

```bash
javac ConversionDstDemo.java
java ConversionDstDemo
```

Kết quả đã kiểm tra:

```text
Overlap offsets : [-04:00, -05:00]
Earlier instant : 2024-11-03T05:30:00Z
Later instant   : 2024-11-03T06:30:00Z
Same local      : true
Gap offsets     : []
Gap resolved    : 2024-03-10T03:30-04:00[America/New_York]
Instant to zone : 2024-03-10T03:30-04:00[America/New_York]
Start of day    : 2024-03-10T00:00-05:00[America/New_York]
```

**Ý nghĩa đối với bản đồ chuyển đổi:**

- `LocalDateTime → ZonedDateTime` ở **overlap** có hai cách chọn offset: lần sớm và lần muộn; `toInstant()` cho hai mốc cách một giờ.
- `LocalDateTime → ZonedDateTime` trong **gap** được `atZone` mặc định điều chỉnh sang 03:30 hợp lệ. Nếu bắt buộc phải giữ chính xác giờ người dùng nhập, cần kiểm tra và từ chối thay vì dùng mặc định.
- `Instant → ZonedDateTime` luôn xác định rõ trong vùng; `07:30Z` ánh xạ thẳng thành `03:30-04:00`, không có lựa chọn offset mơ hồ.
- `date.atStartOfDay(zone)` được dùng khi cần **đầu ngày hợp lệ theo vùng**. Ngay cả khi ngày này có DST vào 02:00, đầu ngày 00:00 vẫn theo `-05:00`. Trong vùng khác, một chuyển đổi offset có thể xảy ra gần nửa đêm, nên không mặc định mọi ngày đều bắt đầu đúng 00:00 theo quy tắc mọi vùng.

## 10. Đổi múi giờ: giữ cùng mốc hay giữ cùng giờ trên đồng hồ?

Hai phương thức trên `ZonedDateTime` có mục đích khác nhau:

```java
ZonedDateTime hcm =
        Instant.parse("2025-01-15T02:30:00Z")
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime parisSameInstant =
        hcm.withZoneSameInstant(ZoneId.of("Europe/Paris"));

ZonedDateTime parisSameLocal =
        hcm.withZoneSameLocal(ZoneId.of("Europe/Paris"));
```

- `withZoneSameInstant` **giữ đúng `Instant`** ban đầu. Giờ hiển thị tại Paris thay đổi để phản ánh cùng thời điểm.
- `withZoneSameLocal` cố giữ **09:30 trên đồng hồ** rồi diễn giải tại Paris; `Instant` thường thay đổi. Có thể gặp gap/overlap và quy tắc giải quyết vùng.
- Với một `Instant` đã biết, cách chuyển zone trực tiếp, dễ đọc là `instant.atZone(otherZone)`.

Khi đổi múi giờ cho timestamp sự kiện đã diễn ra, thông thường chọn **same instant**, không phải **same local**. Khi chuyển một lịch giờ cố định giữa hai địa điểm và muốn giữ nguyên giờ trên đồng hồ, có thể cần same local nhưng phải diễn đạt nghiệp vụ rõ ràng.

## 11. Kết nối với thư viện cũ: `Date`, `Calendar`, epoch millis

Ở ứng dụng Java cũ, bạn có thể gặp `java.util.Date`, `java.util.Calendar`, `TimeZone` và con số Unix epoch. Hãy coi chúng là **cầu nối** khi tích hợp, ưu tiên `java.time` trong code nghiệp vụ mới.

### `java.util.Date` ↔ `Instant`

```java
Instant instant = Instant.parse("2025-01-15T02:30:00Z");
java.util.Date oldDate = java.util.Date.from(instant);
Instant back = oldDate.toInstant();
```

`java.util.Date` lưu mốc với **độ chính xác mili giây**, không lưu tên zone. Nếu `instant` có phần nano dưới mili giây, chuyển thành `Date` sẽ làm mất độ chính xác đó. `Date.toString()` hiển thị theo thiết lập múi giờ hệ thống, nhưng bản thân `Date` không mang vùng địa phương trong giá trị.

### Unix epoch milliseconds ↔ `Instant`

```java
Instant fromMillis = Instant.ofEpochMilli(1_736_908_200_000L);
long epochMillis = fromMillis.toEpochMilli();
// epochMillis = 1736908200000
```

`ofEpochMilli` nhận số mili giây tính từ `1970-01-01T00:00:00Z`. Đừng nhầm số giây epoch với số mili giây epoch: chênh nhau hệ số **1.000**. `Instant.toEpochMilli()` chuyển về độ chính xác mili giây, không giữ nanosecond lẻ; với giá trị rất lớn có thể có giới hạn/tràn số.

Nếu dữ liệu bên ngoài dùng **epoch seconds**, chọn `Instant.ofEpochSecond(seconds)` và lưu giây với đơn vị rõ ràng. Không lấy `System.nanoTime()` để chuyển thành timestamp epoch: nguồn đó chỉ dùng đo thời lượng trong JVM với mốc tùy ý.

### `Calendar` và `TimeZone`

`java.util.Calendar` có thể chuyển sang `Instant` bằng `calendar.toInstant()`. `TimeZone` có thể lấy `ZoneId` bằng `timeZone.toZoneId()`. Ngược lại, nếu phải giao tiếp API cũ, `GregorianCalendar.from(zonedDateTime)` tạo `GregorianCalendar` từ `ZonedDateTime`. Cần phân biệt timestamp tuyệt đối với việc quy đổi các trường giờ địa phương và thận trọng với cấu hình lenient/historical của API cũ.

**JDBC:** `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp` là các kiểu riêng trong JDBC, không nên mặc nhiên coi toàn bộ là `java.util.Date` với cùng ngữ nghĩa. Driver và loại cột SQL có thể khác nhau trong việc xử lý zone/offset; cần kiểm tra hợp đồng mapping của driver và lược đồ. `LocalDate` thường phù hợp với cột DATE; `LocalDateTime` với kiểu ngày giờ không zone; còn timestamp toàn cầu phải có quy ước lưu/đọc rõ (ví dụ UTC + kiểu cột/driver tương ứng).

## 12. `Duration` và `Period`: khoảng thời gian không phải “mốc”

Một nhầm lẫn phổ biến khi đọc bản đồ chuyển đổi là nghĩ có thể lấy `Duration` đổi trực tiếp sang `Instant`. `Duration` không có mốc bắt đầu, còn `Instant` là mốc cụ thể. Bạn phải cung cấp một `Instant` gốc:

```java
Instant issuedAt = Instant.parse("2025-01-15T10:00:00Z");
Duration ttl = Duration.ofMinutes(90);
Instant expiresAt = issuedAt.plus(ttl);
// 2025-01-15T11:30:00Z
```

Để tính độ dài giữa hai thời điểm:

```java
Duration elapsed = Duration.between(issuedAt, expiresAt);
// PT1H30M
```

`Period.ofMonths(1)` lại mang ý nghĩa tháng lịch. Muốn “một tháng sau cùng giờ tại Paris”, phải có vùng, đổi sang `ZonedDateTime`, rồi cộng `plusMonths(1)` và chuyển lại `Instant` nếu cần:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
Instant nextMonth =
        issuedAt.atZone(zone).plusMonths(1).toInstant();
```

Các đoạn là minh họa trong phương thức cần `import java.time.*;`. Một tháng không có số giây cố định, nên đừng đổi `Period.ofMonths(1)` thành một `Duration` tùy ý 30 ngày.

## 13. Chọn kiểu và đường chuyển đổi trong dự án

| Tình huống nghiệp vụ | Kiểu dữ liệu ưu tiên | Đường chuyển đổi / lời khuyên |
| --- | --- | --- |
| Ghi thời điểm thanh toán, đăng nhập, log | `Instant` | Lưu mốc tuyệt đối; khi hiển thị dùng `atZone(userZone)`. |
| Ngày sinh, ngày nghỉ lễ | `LocalDate` | Không thêm giờ/zone khi dữ liệu chỉ có ngày lịch. |
| Giờ mở cửa hằng ngày | `LocalTime` + `ZoneId` theo địa điểm | Chỉ tạo `ZonedDateTime` khi biết ngày cụ thể. |
| Lịch họp một lần theo địa điểm | `LocalDateTime` + `ZoneId` và chính sách DST | `local.atZone(zone).toInstant()` sau khi giải quyết gap/overlap. |
| Lịch định kỳ tại một thành phố | `LocalTime`/ngày lặp + `ZoneId` + quy tắc DST | Không thay vùng bằng một offset cố định. |
| API gửi timestamp có offset | `OffsetDateTime` hoặc `Instant` | `offsetDateTime.toInstant()` để so/lưu mốc; giữ offset nếu cần hiển thị đúng input. |
| API nhận chuỗi ngày giờ thiếu offset | `LocalDateTime` | Yêu cầu/định nghĩa zone từ hợp đồng; không ngầm đoán UTC. |
| Thời lượng xử lý API | `Duration` | Không cần giờ lịch; đo khoảng trôi bằng nguồn phù hợp. |
| Ngày giờ theo kế toán tháng/năm | `LocalDate` hoặc `ZonedDateTime` + `Period` | Tính theo lịch, không ép thành số giây cố định. |
| Hệ thống cũ dùng `Date` | `Instant` tại ranh giới tích hợp | `Date.toInstant()` / `Date.from(instant)`; lưu ý độ chính xác ms. |

### Ba câu hỏi trước khi chuyển

1. **Giá trị hiện tại đã là một mốc tuyệt đối chưa?** Nếu có `Instant`, `OffsetDateTime` hoặc `ZonedDateTime`, bạn có thể giữ mốc khi đổi cách hiển thị.
2. **Đầu ra cần giữ ngày, giờ, offset, vùng hay chỉ một phần?** Các lệnh `toLocalDate()`, `toLocalTime()`, `toLocalDateTime()` là phép trích xuất có mất dữ liệu.
3. **Nếu từ giờ địa phương sang mốc thực, zone/offset đến từ đâu?** Phải đến từ nghiệp vụ, input hoặc hợp đồng dữ liệu; không tự lấy mặc định của máy khi ý nghĩa yêu cầu là múi giờ của người dùng/địa điểm.

## 14. Các lỗi chuyển đổi thường gặp

1. **Gắn UTC nhầm cho `LocalDateTime`:** `2025-01-15T09:30` không đồng nghĩa `09:30Z`. Cần vùng/offset trước khi tạo `Instant`.
2. **Lấy `ZoneId.systemDefault()` tùy tiện:** Container server có thể chạy UTC trong khi người dùng ở Việt Nam. Vùng được chọn phải theo yêu cầu nghiệp vụ.
3. **Làm mất offset ở DST overlap:** Hai `ZonedDateTime` khác mốc có thể có cùng `LocalDateTime`. Đừng chỉ lưu ngày giờ địa phương nếu cần tái lập mốc.
4. **Dùng offset cố định cho lịch lặp tại một thành phố:** Offset không thể hiện quy tắc DST của `ZoneId`.
5. **Coi `Instant.atZone(zone)` là cộng/trừ số giờ vào mốc:** Nó chỉ đổi cách biểu diễn cùng một thời điểm.
6. **Nhầm `withZoneSameInstant` với `withZoneSameLocal`:** Một cách giữ mốc, cách kia cố giữ giờ địa phương; không thay thế tùy tiện.
7. **Lấy `LocalDate.atTime(0,0)` rồi suy ra mốc đầu ngày mọi vùng:** Cần áp `ZoneId` và xét chuyển offset gần nửa đêm; dùng `atStartOfDay(zone)` khi đúng bài toán.
8. **Dùng `OffsetTime` làm timestamp:** Nó không có ngày nên không thể đại diện một sự kiện một lần.
9. **Giả định `Date` giữ tới nanosecond:** `java.util.Date` chỉ có mức mili giây.
10. **Nhầm epoch milliseconds với epoch seconds:** Sai đơn vị tạo ngày hàng nghìn năm lệch so với dự kiến.
11. **Biến `Period` thành 30 ngày:** Một tháng lịch không có độ dài giây cố định.
12. **Quên tính bất biến:** Các kiểu `java.time` trả giá trị mới, không tự sửa biến đã có.
13. **Parse chuỗi như thể đã hoàn tất chuyển đổi kiểu:** `LocalDateTime.parse(...)` không tự tạo `Instant`; dữ liệu vẫn thiếu zone.
14. **Bỏ qua lỗi parse hoặc dữ liệu không hợp lệ:** Chuỗi ngày sai, vùng không hợp lệ hoặc giờ bị khuyết phải có kiểm tra và thông báo thích hợp.

## 15. Bài tập tự kiểm tra

**Bài 1.** Chuyển `Instant.parse("2025-01-15T02:30:00Z")` sang giờ Việt Nam.

**Đáp án:** `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` cho `2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]`. Mốc UTC không đổi.

**Bài 2.** Có `LocalDate.of(2025, 1, 15)` và `LocalTime.of(9, 30)`. Tạo `LocalDateTime` bằng cách nào?

**Đáp án:** `LocalDateTime.of(date, time)` hoặc `date.atTime(time)`. Sau bước này vẫn chưa có `Instant` nếu chưa chọn vùng/offset.

**Bài 3.** Từ `LocalDateTime.of(2025, 1, 15, 9, 30)` chuyển sang `Instant` với offset `+07:00`.

**Đáp án:** `local.toInstant(ZoneOffset.ofHours(7))`, kết quả `2025-01-15T02:30:00Z`.

**Bài 4.** Chuyển một `ZonedDateTime` sang `LocalDateTime` có giữ đủ thông tin để chuyển ngược không?

**Đáp án:** Không. Zone/offset bị bỏ; ở overlap có thể mất cả lựa chọn lần sớm hay muộn.

**Bài 5.** Vì sao `OffsetTime.of(9,30,0,0,ZoneOffset.ofHours(7))` chưa đổi thẳng thành một sự kiện `Instant`?

**Đáp án:** Nó thiếu ngày. Thêm ngày bằng `offsetTime.atDate(date)` để có `OffsetDateTime` rồi `toInstant()`.

**Bài 6.** Từ `java.util.Date` tới `Instant`, API nào phù hợp và cần lưu ý gì?

**Đáp án:** `date.toInstant()`; `Date` có độ chính xác tới mili giây, không giữ phần nano giây nhỏ hơn mili giây.

**Bài 7.** Ngày 03/11/2024 lúc 01:30 tại New York có thể tương ứng bao nhiêu `Instant`?

**Đáp án:** Hai, vì DST overlap: `05:30Z` hoặc `06:30Z` tùy offset `-04:00` hay `-05:00`.

**Bài 8.** Bạn muốn thay cách hiển thị từ Việt Nam sang Paris mà giữ cùng sự kiện. Dùng `withZoneSameLocal` hay `withZoneSameInstant`?

**Đáp án:** `withZoneSameInstant(ZoneId.of("Europe/Paris"))`, vì cần giữ đúng `Instant` ban đầu.

## Ghi nhớ cuối bài

**Bản đồ chuyển đổi phải bắt đầu bằng ý nghĩa dữ liệu, không chỉ tên API.** `LocalDate`, `LocalTime` và `LocalDateTime` không tự xác định mốc toàn cầu; `OffsetDateTime`, `ZonedDateTime` và `Instant` có thể đại diện một mốc, nhưng giữ những ngữ cảnh khác nhau. Dùng `atZone(zone)`, `atOffset(offset)` và `toInstant()` để đi giữa giờ địa phương và mốc thực; dùng `toLocalDate()/toLocalTime()/toLocalDateTime()` khi muốn trích xuất phần thông tin và **chấp nhận mất ngữ cảnh**. Luôn cung cấp vùng/offset rõ ràng, kiểm tra DST ở chiều từ giờ địa phương sang mốc thực, và chọn `Duration`/`Period` cho khoảng thời gian theo ý nghĩa phù hợp.
