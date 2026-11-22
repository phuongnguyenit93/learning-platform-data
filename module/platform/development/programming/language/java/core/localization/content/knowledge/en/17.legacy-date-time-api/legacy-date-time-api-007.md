# Chuyển đổi giữa Date, Instant và các kiểu java.time trong Java

## 1. Vì sao cần chuyển đổi giữa hai thế hệ API?

Trong nhiều hệ thống Java, dữ liệu thời gian đi qua cả mã cũ lẫn mã mới:

- API cũ, driver hoặc một số thư viện có thể dùng `java.util.Date` và `java.util.Calendar`.
- Code hiện đại thường dùng các kiểu trong `java.time` như `Instant`, `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime` và `OffsetDateTime`.
- Dữ liệu SQL đôi khi dùng `java.sql.Date`, `java.sql.Time` hoặc `java.sql.Timestamp`, vốn **không** nên bị đồng nhất với `java.util.Date` dù có quan hệ kế thừa.

Mục tiêu của việc chuyển đổi là **giữ nguyên ý nghĩa thời gian**, tránh nhầm thời điểm tuyệt đối với giờ hiển thị của một vùng. Một dòng code biên dịch được chưa chắc đúng nghiệp vụ nếu bỏ qua múi giờ, độ chính xác hoặc daylight saving time (DST).

Ví dụ một thời điểm UTC:

```text
2024-02-29T23:30:00Z
```

là **cùng một thời điểm** với giờ địa phương tại `Asia/Ho_Chi_Minh`:

```text
2024-03-01T06:30:00+07:00
```

Hai chuỗi có **ngày tháng khác nhau** nhưng cùng trỏ đến một instant. Vì vậy, chuyển từ `Date` sang `LocalDate` **bắt buộc có chính sách múi giờ**; Java không thể suy ra một ngày địa phương duy nhất chỉ từ epoch time.

## 2. Bản đồ các kiểu thời gian cần nhớ

| Kiểu | Biểu diễn gì? | Có múi giờ/offset? | Dùng khi nào? |
|---|---|---|---|
| `java.util.Date` | Một thời điểm trên trục thời gian, độ phân giải API theo mili-giây | Bản thân đối tượng không giữ zone | Tương thích thư viện cũ |
| `Instant` | Một điểm trên timeline UTC, độ chính xác nano-giây | Là thời điểm tuyệt đối; không giữ tên zone | Timestamps, log, giao tiếp hệ thống |
| `LocalDate` | Năm-tháng-ngày trong lịch | Không | Ngày sinh, ngày đặt lịch, ngày nghiệp vụ |
| `LocalTime` | Giờ-phút-giây trong một ngày | Không | Giờ mở cửa hoặc giờ hẹn theo ngày |
| `LocalDateTime` | Ngày và giờ “trên đồng hồ” | Không | Lịch địa phương chưa gắn zone |
| `OffsetDateTime` | Ngày/giờ kèm offset cố định như `+07:00` | Có offset | Thời gian có offset trong API |
| `ZonedDateTime` | Ngày/giờ gắn `ZoneId` như `Europe/Paris`, sử dụng zone rules | Có zone và offset tại thời điểm cụ thể | Lịch, sự kiện xuyên DST |
| `ZoneId` | Bộ quy tắc của vùng giờ | Chính nó đại diện zone | Diễn giải giờ địa phương |
| `ZoneOffset` | Độ lệch cố định so với UTC | Có offset | Giao tiếp dạng `+07:00`, `Z` |

**Chốt ngữ nghĩa:** `Date` và `Instant` nói về “**khi nào**”; `LocalDateTime` nói về “**đồng hồ hiển thị mấy giờ**” nhưng không xác định được một instant duy nhất nếu chưa gắn vùng giờ.

`Instant` không phải là “thời gian local dùng GMT”; nó là một điểm tuyệt đối trên timeline. `Date.toString()` có thể hiển thị theo múi giờ mặc định JVM, nhưng điều đó **không biến Date thành đối tượng lưu timezone**.

## 3. Chuyển đổi chuẩn giữa java.util.Date và Instant

Hai API trực tiếp nhất:

```java
Instant instant = legacyDate.toInstant(); // Date -> Instant
Date legacyDate = Date.from(instant);     // Instant -> Date
```

Với `Date`, cần import đúng `java.util.Date` và `java.time.Instant`. Khi hai đoạn được dùng chung, khai báo biến theo thứ tự hợp lý:

```java
Instant instant = Instant.parse("2024-02-29T23:30:00Z");
Date legacyDate = Date.from(instant);
Instant restored = legacyDate.toInstant();
```

Các lệnh này không phụ thuộc múi giờ mặc định JVM để xác định **instant**. Dữ liệu epoch được giữ, **trong giới hạn độ chính xác và phạm vi của Date**.

### Tại sao Instant -> Date có thể mất độ chính xác?

`Instant` có nano-giây; `java.util.Date` biểu diễn thời điểm bằng số mili-giây từ epoch, thông qua `getTime()`. Khi tạo `Date` từ một `Instant` có phần nano-giây không chia hết cho 1 triệu, **phần dưới mili-giây không được giữ lại**.

Ví dụ:

```text
Instant gốc:             2024-02-29T23:30:00.123456789Z
Sau Date.from(...):      2024-02-29T23:30:00.123Z
```

Đây không phải lỗi timezone mà là **mất độ chính xác** do chuyển sang kiểu có granularity mili-giây. Nếu ứng dụng cần nano-giây, không thể yêu cầu một `java.util.Date` bảo toàn chúng; hãy giữ `Instant` hoặc dùng kiểu lưu trữ thích hợp.

`Date.from(Instant)` cũng có thể ném `IllegalArgumentException` nếu `Instant` nằm ngoài phạm vi biểu diễn của `Date`; tránh giả định mọi `Instant.MIN/MAX` đều chuyển được.

### Tại sao không nên dùng Date.toString để kiểm chứng?

`System.out.println(date)` gọi `Date.toString()`, mà chuỗi hiển thị phụ thuộc timezone/default của môi trường. Để có kết quả ổn định khi so sánh, log `date.toInstant()`, `date.getTime()` hoặc dùng formatter có `ZoneId` tường minh.

## 4. Chương trình Java 17+: Date ⇄ Instant với timestamp cố định

Lưu thành `DateInstantDemo.java`:

```java
import java.time.Instant;
import java.util.Date;

public class DateInstantDemo {
    public static void main(String[] args) {
        Instant original =
                Instant.parse("2024-02-29T23:30:00.123456789Z");

        Date legacy = Date.from(original);
        Instant restored = legacy.toInstant();

        System.out.println("instant=" + original);
        System.out.println("legacyMillis=" + legacy.getTime());
        System.out.println("restored=" + restored);
        System.out.println("same=" + original.equals(restored));
    }
}
```

Biên dịch và chạy:

```bash
javac DateInstantDemo.java
java DateInstantDemo
```

Kết quả kiểm chứng trên Java 17+:

```text
instant=2024-02-29T23:30:00.123456789Z
legacyMillis=1709249400123
restored=2024-02-29T23:30:00.123Z
same=false
```

Giải thích:

1. `Instant.parse(...)` tạo điểm trên timeline UTC.
2. `Date.from(original)` chuyển sang đối tượng legacy với mili-giây.
3. `Date.getTime()` trả số mili-giây kể từ Unix epoch (`1970-01-01T00:00:00Z`).
4. `Date.toInstant()` tái tạo một instant từ mili-giây đã giữ lại.
5. `original.equals(restored)` là `false` do phần `456789` nano-giây bị mất.

Nếu `Instant` ban đầu chỉ có precision mili-giây và nằm trong phạm vi được hỗ trợ, round-trip thông thường sẽ giữ nguyên instant.

**Lưu ý về giá trị âm trước epoch:** Khi chuyển đổi epoch sub-millisecond quanh `1970-01-01T00:00:00Z`, không nên tự thay thế `Date.from(instant)` bằng phép chia số nano/1.000.000 theo kiểu truncate-toward-zero, vì các phép chuyển đổi epoch có quy tắc đối với số âm. Dùng API chuẩn thay cho toán tử tự xây dựng.

## 5. Date / Instant sang ZonedDateTime và LocalDateTime

Từ một `Instant` muốn hiển thị ngày giờ của một khu vực cụ thể, hãy gắn `ZoneId`:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned =
        legacyDate.toInstant().atZone(zone);

LocalDateTime localDateTime =
        zoned.toLocalDateTime();
```

Công thức:

```text
Date -> Instant -> ZonedDateTime(zone) -> LocalDateTime
```

Với instant `2024-02-29T23:30:00.123Z`, tại `Asia/Ho_Chi_Minh` sẽ thành `2024-03-01T06:30:00.123`.

### Ví dụ Java 17+ độc lập

Lưu `DateToLocalDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Date;

public class DateToLocalDemo {
    public static void main(String[] args) {
        Date legacy = Date.from(
                Instant.parse("2024-02-29T23:30:00.123Z"));

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDateTime local =
                legacy.toInstant().atZone(zone).toLocalDateTime();
        LocalDate date =
                legacy.toInstant().atZone(zone).toLocalDate();

        System.out.println("local=" + local);
        System.out.println("date=" + date);
        System.out.println("utcLocal=" +
                legacy.toInstant()
                        .atZone(ZoneOffset.UTC)
                        .toLocalDateTime());
    }
}
```

Chạy:

```bash
javac DateToLocalDemo.java
java DateToLocalDemo
```

Kết quả:

```text
local=2024-03-01T06:30:00.123
date=2024-03-01
utcLocal=2024-02-29T23:30:00.123
```

Cùng một `Date`, nhưng ngày địa phương ở UTC và Việt Nam khác nhau. Nếu doanh nghiệp hỏi “ngày của sự kiện” mà không có zone, bài toán **chưa đủ thông tin**.

**Không nên** lấy `LocalDateTime` bằng cách cắt `Date.toString()`; định dạng chuỗi phụ thuộc JVM và locale. Cũng không dùng `LocalDateTime.now()` để “chuyển” một `Date` đã có: `now()` lấy thời điểm hiện tại, không phải timestamp của đầu vào.

## 6. LocalDateTime / ZonedDateTime / OffsetDateTime trở lại Date

Muốn có `Date` từ một ngày giờ địa phương, phải xác định **zone hoặc offset** để chuyển sang instant:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime local =
        LocalDateTime.of(2024, 3, 1, 6, 30, 0, 123_000_000);

Date date = Date.from(local.atZone(zone).toInstant());
```

Kết quả:

```text
2024-02-29T23:30:00.123Z
```

Khi viết mã hoàn chỉnh, dùng `date.toInstant()` để hiển thị kết quả ổn định.

Các đường chuyển đổi hay dùng:

| Nguồn | Chuyển về Instant | Sau đó |
|---|---|---|
| `ZonedDateTime` | `zoned.toInstant()` | `Date.from(...)` |
| `OffsetDateTime` | `offsetDateTime.toInstant()` | `Date.from(...)` |
| `LocalDateTime` | `localDateTime.atZone(zone).toInstant()` | `Date.from(...)` |
| `LocalDate` | `localDate.atStartOfDay(zone).toInstant()` | `Date.from(...)` |
| `LocalTime` | Cần ghép với một `LocalDate` và zone/offset | Không đủ để tự có Instant |

**Tránh tự gọi `localDateTime.toEpochSecond(ZoneOffset.UTC)`** nếu giờ địa phương đó thực sự thuộc khu vực có offset khác UTC. Lệnh này chỉ đúng nếu bạn **chủ động định nghĩa** giờ trong `LocalDateTime` là giờ UTC.

### LocalDate sang Date: không có một chuyển đổi duy nhất

Một `LocalDate` ví dụ `2024-03-01` có nhiều thời điểm ứng với cùng ngày trong các zone khác nhau. Nếu cần “đầu ngày theo quy tắc zone”, dùng:

```java
LocalDate localDate = LocalDate.of(2024, 3, 1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Date startOfDay =
        Date.from(localDate.atStartOfDay(zone).toInstant());
```

`atStartOfDay(zone)` xử lý quy tắc múi giờ cho ngày đó. Nó không luôn đơn giản bằng việc ghép `LocalTime.MIDNIGHT` và giả định mọi ngày địa phương có mốc 00:00 hợp lệ: trong một số vùng có chuyển DST lúc nửa đêm hoặc biến động lịch sử, giờ đầu ngày có thể được điều chỉnh tới thời điểm hợp lệ sớm nhất.

Nếu miền dữ liệu là **ngày sinh, ngày hết hạn, ngày lễ** và hoàn toàn không yêu cầu một thời điểm tuyệt đối, tốt nhất là **giữ `LocalDate`**. Chuyển thành `Date` chỉ khi API đích thực sự bắt buộc và nghiệp vụ đã chọn zone/quy tắc ngày.

## 7. ZonedDateTime khác OffsetDateTime ở điểm nào?

Một offset `+07:00` là độ lệch cố định so với UTC tại một thời điểm, nhưng `ZoneId` như `Europe/Paris` chứa **quy tắc lịch sử và thay đổi theo mùa**.

Ví dụ:

```java
Instant moment = Instant.parse("2024-02-29T23:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = moment.atZone(zone);
OffsetDateTime offset = moment.atOffset(ZoneOffset.ofHours(7));
```

Cả hai có thể hiện cùng giờ đồng hồ, nhưng:

- `zoned` mang `ZoneId` của vùng, có thể tính toán theo các chuyển đổi offset trong tương lai.
- `offset` chỉ mang offset cố định `+07:00`.
- Cả hai `toInstant()` trở về cùng thời điểm tuyệt đối.

Khi format API giao tiếp, `OffsetDateTime` thường phù hợp cho timestamp có offset, còn các lịch hẹn lặp theo “9 giờ sáng tại Paris” cần `ZoneId` vì offset có thể đổi theo mùa. Đừng thay toàn bộ zone bằng offset hiện tại rồi giả định offset đó đúng cho mọi ngày trong quá khứ và tương lai.

`Instant` không chứa `ZoneId` gốc. Chuyển `ZonedDateTime -> Instant -> ZonedDateTime` bằng **zone khác** vẫn giữ thời điểm, nhưng không bảo toàn cách hiển thị địa phương và tên zone ban đầu.

## 8. Daylight Saving Time: gap và overlap làm đổi kết quả

Một số zone có **DST**. Khi đồng hồ được chỉnh tiến, một khoảng giờ địa phương **không tồn tại** (*gap*). Khi đồng hồ lùi, một khoảng giờ địa phương có thể diễn ra **hai lần** với hai offset khác nhau (*overlap*).

`LocalDateTime` chỉ có ngày/giờ đồng hồ, vì vậy chuyển `LocalDateTime.atZone(zone)` có thể cần áp dụng quy tắc mặc định của zone:

- **Gap:** thời gian địa phương không tồn tại được điều chỉnh tiến tới thời gian hợp lệ, thường bằng độ dài khoảng gap.
- **Overlap:** thời gian địa phương có hai offset hợp lệ; `atZone` thường chọn offset sớm hơn theo quy tắc Java. Có thể dùng `withLaterOffsetAtOverlap()` để chọn offset còn lại.

### Chương trình Java 17+ minh họa DST

Lưu `DstConversionDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstConversionDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime gap =
                LocalDateTime.parse("2024-03-31T02:30:00")
                        .atZone(paris);

        ZonedDateTime overlap =
                LocalDateTime.parse("2024-10-27T02:30:00")
                        .atZone(paris);

        System.out.println("gap=" + gap);
        System.out.println("overlap=" + overlap);
        System.out.println("later=" +
                overlap.withLaterOffsetAtOverlap());
    }
}
```

Chạy:

```bash
javac DstConversionDemo.java
java DstConversionDemo
```

Kết quả trên Java 17 với quy tắc múi giờ tương ứng:

```text
gap=2024-03-31T03:30+02:00[Europe/Paris]
overlap=2024-10-27T02:30+02:00[Europe/Paris]
later=2024-10-27T02:30+01:00[Europe/Paris]
```

Ngày 31/03/2024 ở Paris, `02:30` không tồn tại do đồng hồ nhảy từ 02 giờ lên 03 giờ, nên Java điều chỉnh thành `03:30+02:00`. Ngày 27/10/2024, `02:30` xảy ra hai lần: lần đầu ở `+02:00`, lần sau ở `+01:00`.

Để yêu cầu người dùng chọn một thời điểm **chính xác** trong overlap, cần thông tin offset hay chính sách bổ sung. Với dữ liệu lịch quan trọng, nên kiểm tra `zone.getRules().getValidOffsets(localDateTime)` trước khi gắn zone nếu muốn từ chối gap/overlap thay vì dùng mặc định.

**Sai lầm phổ biến:** viết “`LocalDateTime` và `Instant` chuyển qua lại một-một”. Không đúng: có những `LocalDateTime` không ánh xạ tới instant nào trong zone nhất định (gap), và có những giờ ánh xạ tới hai instant (overlap).

## 9. java.util.Date khác java.sql.Date và java.sql.Timestamp

Tên `Date` trùng nhau dễ gây nhầm lẫn.

### `java.util.Date`

Đây là class legacy biểu diễn một instant với mili-giây. Sử dụng:

```java
Instant instant = utilDate.toInstant();
java.util.Date converted = java.util.Date.from(instant);
```

Đây là đoạn code minh họa có biến `utilDate` đã khai báo.

### `java.sql.Date`

`java.sql.Date` được thiết kế cho SQL `DATE` — một **ngày trong lịch**, không phải timestamp có giờ chính xác. Dù là lớp con của `java.util.Date`, nó **ghi đè `toInstant()` để ném `UnsupportedOperationException`**.

Vì vậy, mã sau **không an toàn**:

```java
java.sql.Date sqlDate =
        java.sql.Date.valueOf("2024-03-01");
Instant instant = sqlDate.toInstant(); // UnsupportedOperationException
```

Nếu dữ liệu SQL là một ngày không có giờ, dùng:

```java
LocalDate day = sqlDate.toLocalDate();
java.sql.Date converted = java.sql.Date.valueOf(day);
```

Khi làm việc với JDBC hiện đại, nếu driver hỗ trợ JDBC 4.2, có thể đọc SQL DATE trực tiếp bằng `ResultSet.getObject(column, LocalDate.class)` thay vì chuyển vòng qua legacy class. Hãy kiểm tra khả năng hỗ trợ thực tế của driver.

**Không ép `java.sql.Date` thành `java.util.Date` để rồi gọi `toInstant()` với hy vọng né lỗi.** Gọi phương thức ảo vẫn thực thi bản override của `java.sql.Date`.

### `java.sql.Timestamp`

`java.sql.Timestamp` phục vụ SQL TIMESTAMP và có phần nano-giây bổ sung so với `java.util.Date`. Có các phương thức:

```java
java.sql.Timestamp timestamp =
        java.sql.Timestamp.from(instant);

Instant restored = timestamp.toInstant();
```

Với ví dụ `Instant` `2024-02-29T23:30:00.123456789Z`, `Timestamp.from(instant).toInstant()` có thể giữ nguyên độ chính xác nano-giây. Tuy vậy, **kiểu cột SQL và cơ sở dữ liệu** có thể chỉ hỗ trợ một độ chính xác nhất định hoặc có ngữ nghĩa timezone khác, nên lưu rồi đọc lại DB không được bảo đảm luôn giữ chính xác mọi nano-giây.

Phân biệt SQL `TIMESTAMP WITHOUT TIME ZONE` với `TIMESTAMP WITH TIME ZONE` theo **ngữ nghĩa của driver/DB cụ thể**; không được tự suy ra mọi `Timestamp` luôn là instant UTC đúng nghĩa. Nếu SQL column là local date-time không zone, dùng `LocalDateTime` có thể phù hợp hơn khi JDBC hỗ trợ.

## 10. Calendar sang java.time và ngược lại

`java.util.Calendar` chứa thêm cấu hình timezone, lịch, trạng thái mutable; muốn lấy thời điểm:

```java
Calendar calendar = Calendar.getInstance();
Instant instant = calendar.toInstant();
```

Nếu muốn giữ thông tin zone của một `GregorianCalendar`:

```java
java.util.GregorianCalendar calendar =
        new java.util.GregorianCalendar(
                java.util.TimeZone.getTimeZone("Europe/Paris"));

java.time.ZonedDateTime zoned =
        calendar.toZonedDateTime();
```

Khi cần bridge từ `ZonedDateTime` sang legacy GregorianCalendar, có:

```java
java.util.GregorianCalendar restored =
        java.util.GregorianCalendar.from(zoned);
```

Hai đoạn trên là **mảnh mã minh họa**, không phải chương trình hoàn chỉnh và không khẳng định mọi đặc tính cấu hình của `Calendar` được bảo toàn. Ví dụ, tuần đầu năm, lịch và các tùy chọn leniency của legacy Calendar có thể cần kiểm soát riêng.

Cẩn thận với `Calendar.MONTH` trong API cũ: thường dùng chỉ số tháng 0–11, còn `LocalDate.getMonthValue()` là 1–12. Không chuyển bằng cách sao chép số tháng mà quên khác biệt.

## 11. Chọn default ZoneId hay zone tường minh?

Một đoạn code có thể trông tiện:

```java
LocalDateTime local =
        date.toInstant()
                .atZone(ZoneId.systemDefault())
                .toLocalDateTime();
```

`ZoneId.systemDefault()` đọc zone mặc định của môi trường JVM. Nó có thể phù hợp cho ứng dụng **chỉ phục vụ một zone đã cấu hình cố định**, nhưng dễ gây lỗi trên hệ thống cloud, container, CI hoặc dịch vụ nhiều người dùng:

- Máy phát triển dùng `Asia/Ho_Chi_Minh`, container dùng `UTC`.
- Dữ liệu lịch của một khách hàng ở Paris lại được diễn giải theo zone của server tại Việt Nam.
- Một thay đổi cấu hình môi trường làm ngày địa phương bị lệch qua nửa đêm.

**Khuyến nghị:** luân chuyển `ZoneId` có ý nghĩa nghiệp vụ qua tham số hoặc cấu hình rõ ràng. Với timestamp dùng cho lưu trữ/trao đổi, giữ `Instant` càng lâu càng tốt; chỉ áp zone ở ranh giới hiển thị hoặc khi tính logic ngày địa phương.

Không nên gọi `TimeZone.setDefault(...)` trên mỗi request: đó là trạng thái toàn cục có thể ảnh hưởng các luồng khác. Trong test, tạo `ZoneId` tường minh để kết quả ổn định.

## 12. Sai lệch precision: nano, milli và độ lớn phạm vi

Các kiểu có độ chính xác khác nhau:

| Kiểu | Khả năng biểu diễn thời gian |
|---|---|
| `Instant` | Nano-giây theo mô hình java.time |
| `LocalDateTime` | Nano-giây, **chưa có instant** |
| `ZonedDateTime` | Nano-giây cộng quy tắc zone |
| `java.util.Date` | Mili-giây |
| `java.sql.Timestamp` | Có phần nano-giây bổ sung, nhưng độ chính xác lưu DB có thể thấp hơn |

Nên ghi rõ ranh giới làm mất precision trong code và test:

```java
Instant original =
        Instant.parse("2024-02-29T23:30:00.123456789Z");

Instant afterLegacy =
        java.util.Date.from(original).toInstant();

// afterLegacy = 2024-02-29T23:30:00.123Z
```

Mili-giây không phải chỉ là “hiển thị 3 chữ số thập phân”; đó là **mức độ phân giải của giá trị Date**. Nếu hệ thống dùng timestamp để sắp xếp nhiều sự kiện xảy ra sát nhau, việc đi qua legacy `Date` có thể làm hai sự kiện khác nhau trở thành cùng mili-giây.

Ngoài độ phân giải, miền ngày mà các kiểu hỗ trợ cũng không hoàn toàn trùng nhau. Các chuyển đổi giữa kiểu phạm vi rất rộng và `Date`/epoch milliseconds có thể thất bại. Đừng tự biến timestamp lớn thành phép nhân mili-giây mà không kiểm tra overflow.

## 13. Giữ đúng ngữ nghĩa khi chuyển đổi trong ứng dụng

### Sự kiện xảy ra ở một thời điểm

Ví dụ “Thanh toán đã xác nhận tại 2024-02-29T23:30Z”. Đó là instant. Dùng `Instant` ở domain/API; khi bắt buộc tương thích legacy, dùng `Date.from(instant)` và chấp nhận giới hạn milli. Hiển thị bằng `instant.atZone(userZone)`.

### Lịch hẹn theo giờ địa phương

Ví dụ “hẹn lúc 09:00 ngày 27/10/2024 tại Paris”. Để xác định chính xác thời điểm, cần `LocalDateTime` **cùng** `ZoneId`, và trong ngày DST overlap có thể cần offset/chính sách xử lý. Chỉ lưu epoch milliseconds sau khi đã quyết định instant, nếu domain thực sự cần một thời điểm duy nhất.

### Ngày sinh/ngày hết hạn

Ví dụ “ngày 01/03/2024” không có thời gian trong ngày. Nên dùng `LocalDate`. Việc chuyển qua `Date` bằng đầu ngày UTC rồi hiển thị ở vùng giờ âm có thể biến thành ngày trước đó, gây lỗi lịch. Chỉ chuyển sang instant nếu nghiệp vụ đã định nghĩa “đầu ngày ở zone nào”.

### API trả timestamp có offset

Ví dụ `2024-03-01T06:30:00+07:00` có thể parse bằng `OffsetDateTime.parse(...)`, rồi `toInstant()` để so sánh thời điểm:

```java
OffsetDateTime fromApi =
        OffsetDateTime.parse("2024-03-01T06:30:00+07:00");
Instant timestamp = fromApi.toInstant();

// timestamp = 2024-02-29T23:30:00Z
```

Không gọi `LocalDateTime.parse(...)` trên chuỗi chứa offset rồi bỏ offset đi. Nếu cần giữ đúng thông tin nguồn để hiển thị lại, hãy lưu offset/zone riêng theo yêu cầu nghiệp vụ.

## 14. Kiểm thử những ca dễ sai

Một bộ kiểm thử chuyển đổi nên bao gồm:

| Kiểm thử | Điều cần xác nhận |
|---|---|
| `Date.from(instant).toInstant()` với mili-giây tròn | Giữ nguyên instant |
| Instant có nano phần lẻ dưới milli | Xác nhận precision bị giảm |
| Instant sát nửa đêm UTC | LocalDate khác nhau giữa UTC và vùng khác |
| `LocalDateTime.atZone(...)` trong DST gap | Biết rõ chính sách điều chỉnh hoặc từ chối |
| LocalDateTime trong DST overlap | Chọn offset nào và có cần người dùng xác nhận |
| `ZoneId.of("Europe/Paris")` vs offset `+01:00` | Không đánh đồng zone với offset cố định |
| `java.sql.Date.toInstant()` | Biết phương thức này ném `UnsupportedOperationException` |
| `java.sql.Date.toLocalDate()` | Chuyển ngày lịch đúng kiểu |
| `Timestamp.from(instant).toInstant()` | Nano-giây trong bộ nhớ và precision thực tế của DB |
| Hệ thống chạy ở `UTC` và `Asia/Ho_Chi_Minh` | Kết quả không đổi nếu đã chọn zone tường minh |
| Số tháng legacy `Calendar` | Không nhầm chỉ số tháng 0–11 với 1–12 |

Với code mới, unit tests nên dùng **dữ liệu thời gian cố định** như `Instant.parse("...Z")` và `ZoneId.of("...")`. Tránh `Instant.now()` hoặc `ZoneId.systemDefault()` trong test cần output tuyệt đối, vì kết quả sẽ phụ thuộc máy và thời điểm chạy.

## 15. Các lỗi thường gặp

1. **Nhầm Date có timezone.** `java.util.Date` giữ một instant; `toString()` định dạng theo timezone môi trường.
2. **Chuyển Date trực tiếp thành LocalDate không chọn zone.** Ngày địa phương phụ thuộc zone.
3. **Dùng `LocalDateTime.now()` để chuyển một Date cũ.** Nó lấy thời gian hiện tại, không dùng đầu vào.
4. **Coi LocalDateTime là instant UTC.** LocalDateTime không mang zone/offset.
5. **Cố dùng một offset cố định thay ZoneId.** Không giữ được lịch sử/quy tắc DST.
6. **Bỏ qua gap và overlap của DST.** Có thể tự điều chỉnh giờ không tồn tại hoặc chọn một offset trong hai offset.
7. **Mong `Date.from(instant)` bảo toàn nano-giây.** Date chỉ giữ mili-giây.
8. **Dùng Date.toString() làm serializer.** Chuỗi phụ thuộc default timezone và không phải hợp đồng ổn định.
9. **Đánh đồng `java.sql.Date` với `java.util.Date`.** `java.sql.Date.toInstant()` ném `UnsupportedOperationException`; dùng `toLocalDate()` cho SQL DATE.
10. **Cho rằng SQL TIMESTAMP luôn có zone.** Ngữ nghĩa phụ thuộc kiểu cột và driver.
11. **Lưu ngày sinh như đầu ngày UTC rồi hiển thị ở zone khác.** Ngày có thể lùi một ngày.
12. **Dùng default timezone của server cho mọi người dùng.** Kết quả thay đổi theo môi trường, không theo địa điểm/ngữ nghĩa dữ liệu.
13. **Không test precision milli vs nano.** Round-trip qua legacy Date có thể mất dữ liệu.
14. **Dùng `Calendar.MONTH` như tháng 1–12.** Legacy Calendar thường đánh số tháng bắt đầu từ 0.
15. **Tự tính epoch bằng phép nhân/cộng int/long không có kiểm tra.** Dễ overflow hoặc sai với số âm trước 1970.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Từ `java.util.Date` sang `Instant` dùng phương thức nào?

**Đáp án:** `date.toInstant()`.

**Câu 2.** Từ `Instant` sang `java.util.Date` dùng gì, và có điểm hạn chế gì?

**Đáp án:** `Date.from(instant)`; có thể mất nano-giây dưới mức mili-giây.

**Câu 3.** Có thể chuyển một `Date` sang `LocalDate` mà không biết zone không?

**Đáp án:** Không thể xác định **ngày địa phương mong muốn** một cách duy nhất; cần `date.toInstant().atZone(zone).toLocalDate()` với zone đúng nghiệp vụ.

**Câu 4.** Tại `Asia/Ho_Chi_Minh`, `2024-02-29T23:30:00Z` là ngày nào?

**Đáp án:** `2024-03-01`, lúc 06:30 local.

**Câu 5.** Nếu `LocalDateTime` rơi vào DST overlap, nó có luôn xác định đúng một instant không?

**Đáp án:** Không. Có thể có hai offset/instant hợp lệ; cần quy tắc chọn.

**Câu 6.** `java.sql.Date.toInstant()` có giống `java.util.Date.toInstant()` không?

**Đáp án:** Không. SQL Date override và ném `UnsupportedOperationException`; dùng `toLocalDate()` để nhận ngày.

**Câu 7.** Có thể dùng `LocalDate.atStartOfDay(zone).toInstant()` để lưu ngày sinh mà không giữ zone không?

**Đáp án:** Không nên. Ngày sinh là `LocalDate`; nếu buộc chuyển thành instant phải định nghĩa rõ zone và tránh mất ngữ nghĩa ngày.

**Câu 8.** `Timestamp.from(instant).toInstant()` giữ nano-giây trong Java; có thể chắc chắn DB cũng giữ nano-giây không?

**Đáp án:** Không. Precision và semantics của cột/driver DB có thể thấp hơn.

## 17. Ghi nhớ

Hãy chọn kiểu thời gian theo **nghĩa của dữ liệu** trước khi chuyển đổi: `Instant`/`Date` cho thời điểm tuyệt đối, `LocalDate` cho ngày lịch, `LocalDateTime` cho giờ địa phương chưa gắn zone, `ZonedDateTime` cho thời gian theo vùng có quy tắc DST. Bridge trực tiếp **`Date.toInstant()`** và **`Date.from(Instant)`** đơn giản nhưng có giới hạn mili-giây. Chuyển từ instant sang dạng local cần **`ZoneId` tường minh**. Đối với SQL DATE, dùng `LocalDate` thay vì cố biến nó thành instant.

**Tài liệu chính thức:** [Java SE 17 — java.util.Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html) · [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) · [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html) · [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html) · [Java SE 17 — java.sql.Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Date.html) · [Java SE 17 — Timestamp](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Timestamp.html).
