# Nhận diện phép chuyển đổi làm mất ngày, múi giờ hoặc độ chính xác trong `java.time`

Khi chuyển giữa các kiểu ngày giờ Java, điều nguy hiểm không chỉ là “chương trình có biên dịch được không”, mà còn là **ý nghĩa nào đã bị bỏ đi**. Một câu lệnh rất ngắn như `zoned.toLocalDate()` có thể đúng khi muốn ngày trên lịch, nhưng sẽ sai nếu giá trị đích được dùng như một timestamp của sự kiện.

Có ba nhóm thông tin cần kiểm tra riêng:

1. **Ngày và giờ địa phương** — bạn còn biết năm, tháng, ngày và giờ/phút/giây không?
2. **Múi giờ/offset và mốc thời gian tuyệt đối** — bạn còn xác định được một `Instant` duy nhất không? Bạn còn biết vùng địa lý `ZoneId` không?
3. **Độ chính xác** — giây, mili giây, micro giây và nano giây có được giữ nguyên hay bị cắt/làm tròn?

**Nguyên tắc quan trọng:** “Mất thông tin” phụ thuộc vào mục tiêu sử dụng. Chuyển `ZonedDateTime` thành `LocalDate` là hợp lý nếu chỉ cần *ngày tại vùng đã chọn*. Nhưng đó **không phải** chuyển đổi bảo toàn một sự kiện theo UTC.

## 1. Bản đồ thông tin của những kiểu ngày giờ thường gặp

| Kiểu Java | Có ngày lịch? | Có giờ địa phương? | Có offset/ZoneId? | Có mốc UTC duy nhất? |
| --- | --- | --- | --- | --- |
| `LocalDate` | Có | Không | Không | Không |
| `LocalTime` | Không | Có | Không | Không |
| `LocalDateTime` | Có | Có | Không | Không |
| `OffsetTime` | Không | Có | Offset, nhưng **thiếu ngày** | Không xác định sự kiện trên timeline khi thiếu ngày |
| `OffsetDateTime` | Có | Có | Offset; **không có region ID** | Có |
| `ZonedDateTime` | Có | Có | `ZoneId` và offset đã giải quyết | Có |
| `Instant` | Không giữ ngày giờ địa phương | Không giữ giờ địa phương | Không giữ zone/offset hiển thị | Có |

`Instant` vẫn có thể **được biểu diễn** dưới dạng ngày giờ UTC (ví dụ `2026-01-15T00:30:45Z`); nói “không giữ ngày địa phương” nghĩa là nó không mang sẵn ngày theo `Asia/Ho_Chi_Minh`, `Europe/Paris` hay một vùng cụ thể.

Một `OffsetDateTime` có offset `+07:00` nhưng không biết đó là `Asia/Ho_Chi_Minh` hay một vùng khác cũng đang dùng `+07:00`. `ZoneId` vùng có quy tắc offset thay đổi theo thời gian; `ZoneOffset` là một độ lệch tại thời điểm hoặc cố định.

### Ba câu hỏi trước mọi phép chuyển

- **Giá trị nguồn có những trường gì?** Ví dụ: một `ZonedDateTime` chứa local date-time, zone ID và offset.
- **Giá trị đích giữ được những trường gì?** Ví dụ: `LocalDateTime` không có zone/offset.
- **Để hoàn nguyên có cần hỏi hoặc lưu thêm dữ liệu không?** Ví dụ: từ `LocalDateTime` chưa chắc xác định một instant, nhất là lúc DST overlap.

Nếu phép chuyển cần tự “thêm 00:00”, “chọn zone mặc định” hoặc “bỏ chữ số thập phân giây”, đó là dấu hiệu phải rà soát hợp đồng dữ liệu.

## 2. Những phép chuyển đổi dễ mất ngày, giờ hoặc múi giờ

### 2.1. `LocalDateTime → LocalDate`: giữ ngày, mất toàn bộ giờ

~~~java
LocalDateTime appointment =
        LocalDateTime.of(2026, 1, 15, 7, 30, 45, 123_456_789);

LocalDate dateOnly = appointment.toLocalDate();
// 2026-01-15
~~~

Trong đoạn minh họa trên (đặt trong method với import các kiểu `java.time`), các trường `07:30:45.123456789` **không nằm trong `dateOnly`**. Từ `LocalDate` không thể biết ban đầu lịch hẹn diễn ra lúc 07:30 hay 18:30.

Nếu gọi `dateOnly.atStartOfDay()`, bạn nhận **`LocalDateTime` với giờ 00:00**; đó là **thời gian mới được giả định**, không phải phục hồi giờ gốc. Điều này đặc biệt quan trọng khi xử lý lịch hẹn, sự kiện thanh toán và dữ liệu kiểm toán.

`LocalDate` vẫn là kiểu **đúng** cho ngày sinh, ngày hóa đơn, ngày hiệu lực của quy định khi nghiệp vụ chỉ hỏi **ngày nào trên lịch**.

### 2.2. `LocalDateTime → LocalTime`: giữ giờ, mất ngày

~~~java
LocalDateTime recorded =
        LocalDateTime.of(2026, 1, 15, 23, 45);

LocalTime timeOnly = recorded.toLocalTime();
// 23:45
~~~

Không thể khôi phục **ngày 15/01/2026** từ `timeOnly`. Nếu hôm sau một bản ghi cũng hiển thị `23:45`, hai bản ghi có cùng `LocalTime` nhưng không nhất thiết cùng sự kiện.

Chỉ dùng `LocalTime` khi dữ liệu thực sự là một giờ trong ngày, chẳng hạn “cửa hàng mở cửa lúc 09:00 mỗi ngày”. Khi một sự kiện phải có ngày chính xác, cần kiểu mang đủ ngày hoặc giữ ngày thành một trường riêng.

### 2.3. `ZonedDateTime → LocalDateTime`: bỏ zone và offset

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");
ZonedDateTime inVietnam =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime local = inVietnam.toLocalDateTime();
// 2026-01-15T07:30:45.123456789
~~~

`local` vẫn giữ **đủ các trường ngày giờ và nano giây** của biểu diễn Việt Nam, nhưng **không còn `Asia/Ho_Chi_Minh` và `+07:00`**. Nếu chỉ lưu `local`, về sau người đọc không biết phải dùng offset nào để chuyển về UTC.

Đặc biệt tại một ngày DST overlap, **hai instant khác nhau có thể cùng `LocalDateTime`**. Vì vậy chuyển `ZonedDateTime → LocalDateTime` có thể làm mất tính duy nhất của mốc thời gian, dù ngày/giờ trên đồng hồ không đổi.

### 2.4. `ZonedDateTime → OffsetDateTime`: bỏ tên vùng, giữ offset

~~~java
OffsetDateTime withOffset = inVietnam.toOffsetDateTime();
// 2026-01-15T07:30:45.123456789+07:00
~~~

`OffsetDateTime` này **vẫn xác định đúng instant**, vì ngày giờ + offset đủ để suy ra UTC. Nhưng nó **không còn ID vùng `Asia/Ho_Chi_Minh`**. Nếu dùng kết quả làm mẫu cho lịch lặp tháng sau, offset `+07:00` không chứa lịch sử và quy tắc múi giờ tương lai của một địa phương.

**Đừng đánh đồng “mất zone” với “mất instant”:** `ZonedDateTime → OffsetDateTime` giữ instant, nhưng mất *region ID*. Nếu ứng dụng chỉ cần timestamp của sự kiện, mất tên vùng có thể chấp nhận; nếu cần lịch hẹn theo giờ tại một địa điểm, không nên bỏ zone.

### 2.5. `ZonedDateTime → Instant`: giữ sự kiện, bỏ cách hiển thị tại vùng

~~~java
Instant timestamp = inVietnam.toInstant();
// 2026-01-15T00:30:45.123456789Z
~~~

Đây là phép chuyển **không làm mất mốc tuyệt đối** và giữ nano giây. Nhưng giá trị `Instant` không còn ghi nhận rằng người dùng từng xem sự kiện theo Việt Nam. Nếu sau đó chuyển timestamp theo `America/Los_Angeles`, bạn sẽ thấy **ngày 14/01**, không phải 15/01.

Muốn phục hồi *cùng biểu diễn theo vùng gốc*, phải **còn biết `ZoneId` gốc** và sử dụng quy tắc múi giờ thích hợp:

~~~java
ZonedDateTime restored =
        timestamp.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là phép khôi phục dựa vào **thông tin vùng bổ sung từ bên ngoài**, không phải vì `Instant` tự chứa vùng. Nếu cơ sở dữ liệu quy tắc múi giờ được cập nhật, việc tái tạo cách hiển thị lịch sử trong những trường hợp đặc biệt còn cần cân nhắc yêu cầu audit.

### 2.6. `Instant → LocalDate`: phải chọn zone trước, rồi mới lấy ngày

`Instant` không có phương thức `toLocalDate()` trực tiếp; cần chuyển qua vùng:

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");

LocalDate vietnamDate =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
// 2026-01-15

LocalDate losAngelesDate =
        event.atZone(ZoneId.of("America/Los_Angeles")).toLocalDate();
// 2026-01-14
~~~

**Hai ngày khác nhau từ cùng một instant là hoàn toàn hợp lệ.** Sai lầm là lấy `LocalDate` theo zone của server mà không nói rõ nghiệp vụ yêu cầu zone nào.

Khi đã chọn `LocalDate`, bạn còn mất **giờ, phút, giây, nano giây**. Ví dụ `vietnamDate.atStartOfDay(zone).toInstant()` ra **`2026-01-14T17:00:00Z`**, không bằng event gốc `2026-01-15T00:30:45.123456789Z`. Không coi `atStartOfDay` là phép nghịch đảo của `toLocalDate`.

## 3. Bảng phân loại: phép nào mất gì, phép nào vẫn giữ instant?

| Phép chuyển | Dữ liệu giữ lại | Dữ liệu bị bỏ/giả định | Có thể quay về giá trị gốc tự động? |
| --- | --- | --- | --- |
| `localDateTime.toLocalDate()` | Năm/tháng/ngày | Toàn bộ giờ/phút/giây/nano giây | **Không** |
| `localDateTime.toLocalTime()` | Giờ/phút/giây/nano giây | Năm/tháng/ngày | **Không** |
| `zoned.toLocalDateTime()` | Ngày giờ địa phương, nano giây | Zone ID, offset, nên có thể mất instant | **Không bảo đảm** |
| `zoned.toOffsetDateTime()` | Local date-time, offset, instant | `ZoneId` vùng | Chỉ khi biết lại vùng |
| `zoned.toInstant()` | Instant, nano giây | Zone ID và cách hiển thị địa phương | Khôi phục biểu diễn vùng nếu biết zone |
| `instant.atZone(zone)` | Instant và độ chính xác | Không mất instant; **thêm** biểu diễn vùng | `toInstant()` trở lại đúng instant |
| `offsetDateTime.toInstant()` | Instant, nano giây | Local date-time và offset ban đầu | Không biết lại offset gốc nếu không lưu |
| `instant.truncatedTo(SECONDS)` | Thời gian đến giây | Phần nhỏ hơn giây | **Không** |
| `Instant.ofEpochMilli(instant.toEpochMilli())` | Timestamp đến mili giây | Phần micro/nano giây dư | **Không** nếu nguồn có phần dư |
| `Date.from(instant).toInstant()` | Timestamp đến mili giây | Phần dưới mili giây | **Không** nếu nguồn có phần dư |
| `format("uuuu-MM-dd HH:mm")` | Ngày, giờ và phút hiển thị | Giây, nano giây, offset và zone nếu không ghi vào chuỗi | **Không** |

“Mất” ở bảng này nghĩa là **giá trị đích không tự mang đủ thông tin để tự khôi phục giá trị nguồn**, không phải JVM xóa nội dung của biến nguồn. Các kiểu `java.time` chính là immutable; đối tượng gốc vẫn tồn tại nếu còn tham chiếu đến nó.

## 4. Hai vấn đề khác nhau: mất vùng múi giờ và thay đổi mốc UTC

Một phương thức có thể **đổi cách hiển thị** mà vẫn giữ mốc thời gian:

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");

ZonedDateTime hcm =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime la =
        hcm.withZoneSameInstant(ZoneId.of("America/Los_Angeles"));

System.out.println(hcm.toInstant().equals(la.toInstant()));
// true
~~~

Ngày giờ đồng hồ đổi, thậm chí đổi ngày, nhưng **instant không đổi**. Đây không phải lỗi mất thông tin về sự kiện.

Ngược lại, phép gắn zone/offset cho `LocalDateTime` có thể tạo hoặc đổi ý nghĩa instant:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 1, 15, 7, 30);

OffsetDateTime withPlusSeven =
        local.atOffset(ZoneOffset.ofHours(7));
// 2026-01-15T07:30+07:00

OffsetDateTime withMinusFive =
        local.atOffset(ZoneOffset.ofHours(-5));
// 2026-01-15T07:30-05:00
~~~

Ở đây **cùng local date-time** nhưng hai offset tạo **hai instant khác nhau** cách nhau 12 giờ. `atOffset` **không đoán** vùng địa lý; offset do người gọi đưa vào phải xuất phát từ hợp đồng dữ liệu đáng tin.

Phân biệt tiếp:

- `OffsetDateTime.withOffsetSameInstant(newOffset)` giữ instant và đổi giờ đồng hồ.
- `OffsetDateTime.withOffsetSameLocal(newOffset)` giữ giờ đồng hồ, **đổi instant**.
- `ZonedDateTime.withZoneSameInstant(zone)` giữ instant và đổi biểu diễn theo zone.
- `ZonedDateTime.withZoneSameLocal(zone)` cố giữ local date-time và **có thể đổi instant**.

**Một phép chuyển có đổi instant không?** Hãy kiểm tra trực tiếp `source.toInstant().equals(result.toInstant())` khi cả hai kiểu hỗ trợ `toInstant()`, đừng chỉ nhìn số giờ trên giao diện.

## 5. DST chứng minh vì sao mất offset có thể mất khả năng hoàn nguyên

Xét `Europe/Paris` ngày **27/10/2024**, lúc kết thúc giờ mùa hè. Giờ địa phương **02:30 xảy ra hai lần**:

~~~java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);

System.out.println(paris.getRules().getValidOffsets(overlap));
// [+02:00, +01:00]

ZonedDateTime first = overlap.atZone(paris);
ZonedDateTime second = first.withLaterOffsetAtOverlap();

// first : 2024-10-27T02:30+02:00[Europe/Paris]
// second: 2024-10-27T02:30+01:00[Europe/Paris]
~~~

Cả `first.toLocalDateTime()` và `second.toLocalDateTime()` đều là **`2024-10-27T02:30`**, nhưng:

- `first.toInstant()` = **`2024-10-27T00:30:00Z`**.
- `second.toInstant()` = **`2024-10-27T01:30:00Z`**.

Nếu lưu mỗi `LocalDateTime` cùng zone mà bỏ offset đã chọn, về sau không đủ thông tin để biết 02:30 **lần thứ nhất hay thứ hai**.

Chiều ngược còn có **DST gap**: ngày **31/03/2024** lúc 02:30 tại Paris **không tồn tại**. Lời gọi `LocalDateTime.of(2024, 3, 31, 2, 30).atZone(paris)` mặc định **điều chỉnh thành 03:30+02:00**, chứ không giữ nguyên giờ người dùng nhập. Nếu nghiệp vụ không được tự điều chỉnh, phải chủ động kiểm tra `ZoneRules.getValidOffsets(local)` (rỗng đối với gap, hai giá trị đối với overlap), áp quy tắc nghiệp vụ và có thể dùng `ZonedDateTime.ofStrict(local, offset, zone)` khi cần từ chối tổ hợp không hợp lệ.

**Chuyển từ `Instant` sang `ZonedDateTime` theo một zone là chiều xác định**: khi instant đã rõ, zone cho offset hợp lệ duy nhất tại instant đó. Việc mơ hồ chỉ xuất hiện khi bắt đầu từ các trường giờ địa phương chưa đủ ngữ cảnh.

## 6. Mất độ chính xác: nano giây, mili giây và định dạng chuỗi

`Instant`, `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime` có thể lưu **phần nhỏ giây đến nano giây**. Tuy nhiên, không phải phép chuyển nào cũng giữ đủ 9 chữ số thập phân của giây.

Lấy ví dụ:

`2026-01-15T00:30:45.123456789Z`

| Kết quả | Phần nhỏ giây còn lại | Thông tin đã bỏ |
| --- | --- | --- |
| `instant` ban đầu | `.123456789` | Không |
| `instant.truncatedTo(ChronoUnit.SECONDS)` | Không còn | 123.456.789 nano giây |
| `Instant.ofEpochSecond(instant.getEpochSecond())` | Không còn | 123.456.789 nano giây |
| `Instant.ofEpochMilli(instant.toEpochMilli())` | `.123` | 456.789 nano giây |
| `Date.from(instant).toInstant()` | `.123` | 456.789 nano giây |

### Giây nguyên không tương đương mili giây nguyên

~~~java
Instant event = Instant.parse(
        "2026-01-15T00:30:45.123456789Z");

Instant secondsOnly =
        Instant.ofEpochSecond(event.getEpochSecond());
// 2026-01-15T00:30:45Z

Instant millisOnly =
        Instant.ofEpochMilli(event.toEpochMilli());
// 2026-01-15T00:30:45.123Z
~~~

`getEpochSecond()` chỉ lấy phần giây; muốn mang đủ độ chính xác khi lưu từng phần cần ghi cả `getNano()`, hoặc dùng biểu diễn ISO đầy đủ.

`toEpochMilli()` chỉ có độ chính xác **mili giây**; phần nhỏ hơn bị loại bỏ. Với mốc thời gian trước epoch (1970), cần đặc biệt thận trọng với các phép chia và làm tròn số âm — đừng thay các API chuẩn bằng phép số học tự viết không kiểm thử.

### `java.util.Date` có phải giữ nano giây không?

Không. `java.util.Date` truyền thống lưu thời gian với **độ chính xác mili giây**. Chuyển `Instant → Date → Instant` không phục hồi được phần micro/nano giây dư:

~~~java
Instant precise = Instant.parse(
        "2026-01-15T00:30:45.123456789Z");

Instant recovered = java.util.Date.from(precise).toInstant();
// 2026-01-15T00:30:45.123Z

System.out.println(precise.equals(recovered));
// false
~~~

Mặt khác, `java.util.Date` không “chứa timezone của máy”. Nó lưu lượng mili giây của mốc thời gian; cách hiển thị `Date.toString()` có thể dùng timezone mặc định của JVM. Cần phân biệt **mất độ chính xác** và **đổi zone khi hiển thị**.

### Làm tròn hay cắt bỏ?

`truncatedTo(unit)` **cắt phần nhỏ hơn đơn vị**, không phải làm tròn tới đơn vị gần nhất. Ví dụ `45.999999999` giây khi truncated to seconds thành **45 giây**, không thành 46 giây. Với các hệ thống yêu cầu làm tròn số, cần thiết kế quy tắc làm tròn riêng và kiểm thử ranh giới.

## 7. Mất dữ liệu trong quá trình `format()` / `parse()`

Ngay cả khi không đổi kiểu ngày giờ trực tiếp, việc **định dạng thành chuỗi** có thể loại bỏ thông tin mà chương trình không tự khôi phục:

~~~java
Instant event = Instant.parse(
        "2026-01-15T00:30:45.123456789Z");

ZonedDateTime zoned =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");

String label = zoned.format(formatter);
// 2026-01-15 07:30

LocalDateTime reparsed =
        LocalDateTime.parse(label, formatter);
// 2026-01-15T07:30
~~~

Đoạn này là ví dụ trong method với import `java.time` và `java.time.format.DateTimeFormatter`.

Chuỗi `label` đã **bỏ giây, nano giây, offset và zone**. Parse lại chỉ có thể có giờ phút 07:30 và giây/nano giây mặc định 0 theo khả năng của formatter. Vì thế `reparsed.equals(zoned.toLocalDateTime())` là **`false`**.

Không dùng một chuỗi chỉ để **hiển thị** làm nguồn lưu trữ timestamp nếu hệ thống cần phục hồi thời điểm chính xác. Hãy tách:

- **Giá trị nguồn chuẩn:** `Instant` hoặc `OffsetDateTime`/mô hình zoned khi thật sự cần.
- **Chuỗi hiển thị:** format theo locale, zone, độ chi tiết mong muốn.
- **Dữ liệu nhập:** parse theo hợp đồng có ghi rõ zone/offset và độ chính xác cần có.

`DateTimeFormatter.ISO_INSTANT` và `Instant.toString()` có thể giữ phần nano giây của `Instant` khi cần tuần tự hóa UTC. Dù vậy, một API/database ở bước kế tiếp vẫn có thể hạ precision, nên không thể kết luận **toàn bộ pipeline lossless** chỉ vì một formatter ban đầu đủ chữ số.

## 8. Chương trình Java 17+ độc lập và stdout đã kiểm tra

Tạo tệp **`DateTimeConversionLossDemo.java`**:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Date;

public class DateTimeConversionLossDemo {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2026-01-15T00:30:45.123456789Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = event.atZone(vietnam);

        System.out.println("event = " + event);
        System.out.println("zoned = " + zoned);
        System.out.println("dateOnly = " + zoned.toLocalDate());
        System.out.println("timeOnly = " + zoned.toLocalTime());
        System.out.println("localNoZone = "
                + zoned.toLocalDateTime());
        System.out.println("offsetNoRegion = "
                + zoned.toOffsetDateTime());
        System.out.println("originalInstant = " + zoned.toInstant());

        Instant midnight = zoned.toLocalDate()
                .atStartOfDay(vietnam).toInstant();
        System.out.println("midnightInstant = " + midnight);
        System.out.println("midnightIsEvent = "
                + midnight.equals(event));

        System.out.println("wholeSeconds = "
                + Instant.ofEpochSecond(event.getEpochSecond()));
        System.out.println("wholeMillis = "
                + Instant.ofEpochMilli(event.toEpochMilli()));
        System.out.println("javaUtilDate = "
                + Date.from(event).toInstant());
        System.out.println("truncatedSeconds = "
                + event.truncatedTo(ChronoUnit.SECONDS));
        System.out.println("roundTripInstant = "
                + zoned.toInstant().equals(event));

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");
        String display = formatter.format(zoned);
        LocalDateTime reparsed =
                LocalDateTime.parse(display, formatter);
        System.out.println("display = " + display);
        System.out.println("reparsed = " + reparsed);
        System.out.println("reparsedEqualsOriginalLocal = "
                + reparsed.equals(zoned.toLocalDateTime()));

        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);
        System.out.println("overlapOffsets = "
                + paris.getRules().getValidOffsets(overlap));

        ZonedDateTime first = overlap.atZone(paris);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();
        System.out.println("overlapFirst = " + first);
        System.out.println("overlapSecond = " + second);
        System.out.println("localSame = "
                + first.toLocalDateTime()
                    .equals(second.toLocalDateTime()));
        System.out.println("instantSame = "
                + first.toInstant().equals(second.toInstant()));

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        System.out.println("gapOffsets = "
                + paris.getRules().getValidOffsets(gap));
        System.out.println("gapResolved = " + gap.atZone(paris));

        System.out.println("laRepresentation = "
                + event.atZone(
                        ZoneId.of("America/Los_Angeles")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DateTimeConversionLossDemo.java
java DateTimeConversionLossDemo
~~~

Kết quả:

~~~text
event = 2026-01-15T00:30:45.123456789Z
zoned = 2026-01-15T07:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
dateOnly = 2026-01-15
timeOnly = 07:30:45.123456789
localNoZone = 2026-01-15T07:30:45.123456789
offsetNoRegion = 2026-01-15T07:30:45.123456789+07:00
originalInstant = 2026-01-15T00:30:45.123456789Z
midnightInstant = 2026-01-14T17:00:00Z
midnightIsEvent = false
wholeSeconds = 2026-01-15T00:30:45Z
wholeMillis = 2026-01-15T00:30:45.123Z
javaUtilDate = 2026-01-15T00:30:45.123Z
truncatedSeconds = 2026-01-15T00:30:45Z
roundTripInstant = true
display = 2026-01-15 07:30
reparsed = 2026-01-15T07:30
reparsedEqualsOriginalLocal = false
overlapOffsets = [+02:00, +01:00]
overlapFirst = 2024-10-27T02:30+02:00[Europe/Paris]
overlapSecond = 2024-10-27T02:30+01:00[Europe/Paris]
localSame = true
instantSame = false
gapOffsets = []
gapResolved = 2024-03-31T03:30+02:00[Europe/Paris]
laRepresentation = 2026-01-14T16:30:45.123456789-08:00[America/Los_Angeles]
~~~

Các phép tính và định dạng đầu ra đã được kiểm tra bằng Java. Chương trình dùng các instant cố định và timezone IANA; do đó phần kết quả zone dựa trên quy tắc tzdb của runtime Java. Với quy tắc lịch sử của các vùng trong ví dụ, kết quả như trên.

Từ chương trình có thể thấy hai nhóm mất dữ liệu **độc lập**:

1. `zoned.toLocalDate()`, `toLocalDateTime()`, `toOffsetDateTime()`: mất lần lượt thông tin giờ, múi giờ/offset hoặc region ID tùy kiểu đích.
2. `getEpochSecond()`, `toEpochMilli()`, `Date.from()` và formatter thiếu trường: giảm độ chi tiết dữ liệu mà không cần thay đổi zone.

`zoned.toInstant()` vẫn bảo toàn mốc và nano giây, cho nên `roundTripInstant = true`. Nhưng `zoned.toLocalDate().atStartOfDay(vietnam).toInstant()` thay sự kiện bằng **đầu ngày** của vùng, nên `midnightIsEvent = false`.

## 9. Lưu trữ dữ liệu và API: chú ý phép chuyển ẩn

### SQL/JDBC/ORM

Ánh xạ dữ liệu thời gian sang database là một phép chuyển kiểu nữa. Cần kiểm tra **loại cột và độ chính xác được cấu hình**:

| Mục đích | Giá trị Java thường phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Ngày sinh, ngày hóa đơn | `LocalDate` | Cột `DATE`; không tự gắn `00:00 UTC` |
| Ngày giờ theo đồng hồ chưa có zone | `LocalDateTime` | Không coi nó là instant nếu chưa có offset/zone |
| Mốc sự kiện đã xảy ra | `Instant` | Lưu timestamp có hợp đồng UTC rõ ràng; kiểm tra precision cột |
| Ngày giờ kèm offset | `OffsetDateTime` | Có DB chuẩn hóa về UTC và **không giữ offset ban đầu** |
| Lịch hẹn theo một địa điểm | Local date-time + `ZoneId`, chính sách DST | Muốn phục hồi giờ vùng gốc phải giữ zone và các lựa chọn cần thiết |

Ví dụ một cột timestamp chỉ hỗ trợ **mili giây** sẽ không giữ đủ `.123456789`; một cột `DATE` không giữ giờ/phút; một cột `TIMESTAMP WITHOUT TIME ZONE` không tự cho bạn biết instant. **Tên SQL type không đảm bảo mọi DB/driver có cùng hành vi**, nên phải kiểm tra schema, JDBC/ORM mapping, cách lưu UTC và độ chính xác trong hệ thống thực tế.

Nếu cần biết *cả sự kiện UTC* và *vùng do người dùng chọn*, lưu chúng như **hai thông tin nghiệp vụ**. Không cố suy lại `ZoneId` từ offset một cách không chắc chắn.

### JSON, format và hợp đồng truyền dữ liệu

Ví dụ yêu cầu lưu đầy đủ nano giây của sự kiện và zone hiển thị:

~~~json
{
  "occurredAt": "2026-01-15T00:30:45.123456789Z",
  "displayZone": "Asia/Ho_Chi_Minh"
}
~~~

Phía nhận parse `occurredAt` thành `Instant`, parse `displayZone` thành `ZoneId`, rồi `occurredAt.atZone(displayZone)` khi hiển thị.

Nếu API chỉ gửi `"2026-01-15"`, không thể biết sự kiện xảy ra lúc 00:30 UTC hay 23:59 UTC. Nếu API chỉ gửi `"2026-01-15T07:30"`, không đủ thông tin về offset/zone để xác định instant. Nếu API chỉ gửi số epoch **giây**, phần nano giây chưa được lưu và có thể bị mất. **Đừng suy độ chính xác thực từ số chữ số đang hiển thị nếu upstream đã cắt dữ liệu.**

### Chuyển đổi UTC sang ngày nghiệp vụ

Câu hỏi “giao dịch thuộc ngày 15/01 tại Việt Nam hay tại Los Angeles?” phải bắt đầu từ **một instant được giữ nguyên và một zone được lựa chọn**:

~~~java
LocalDate vietnamDay = event
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();

LocalDate laDay = event
        .atZone(ZoneId.of("America/Los_Angeles"))
        .toLocalDate();
~~~

Cùng `event` có thể thuộc hai **ngày lịch khác nhau**. Đây không phải lỗi ngày bị mất; đây là kết quả đúng của việc **chọn các ranh giới ngày theo vùng khác nhau**. Ngược lại, nếu nghiệp vụ chỉ cần **ngày sinh** đã khai báo, nên dùng `LocalDate` trực tiếp, không ép ngày sinh thành một UTC instant giả rồi chuyển qua zone của người xem.

## 10. Cách xác nhận phép chuyển có an toàn

Một quy trình kiểm tra đáng tin cậy gồm bốn bước.

**Bước 1 — Viết rõ “điều gì phải được bảo toàn”.** Đối với log thanh toán, đó thường là `Instant` tới độ chính xác cần thiết. Đối với ngày sinh, đó là `LocalDate`. Đối với lịch hẹn theo địa điểm, đó là local date-time, zone ID, và chính sách DST.

**Bước 2 — So sánh dữ liệu ngay trước và sau chuyển.** Khi có `toInstant()`, kiểm tra:

~~~java
boolean sameEvent = before.toInstant()
        .equals(after.toInstant());
~~~

*Đây là biểu thức minh họa trong method, chỉ áp dụng khi hai biến `before` và `after` đều có phương thức `toInstant()`.*

Khi quan tâm giờ đồng hồ, dùng `toLocalDateTime()` để so sánh **cùng giá trị local**. Khi quan tâm zone ID, so sánh `getZone()` của hai `ZonedDateTime`; so sánh offset `getOffset()` riêng. Đây là **các bất biến khác nhau**, không thể thay thế nhau bằng một phép `equals` duy nhất.

**Bước 3 — Kiểm tra precision ở cả đầu vào và đầu ra.** Ví dụ `instant.getNano()` phải được bảo toàn nếu hợp đồng hứa đủ nano giây. Kiểm tra tình huống `.123456789`, không chỉ trường hợp `.000`, vì test với giây nguyên sẽ không phát hiện mất precision.

**Bước 4 — Test ranh giới.** Dùng thời điểm quanh nửa đêm, ngày đổi tháng/năm, DST gap và overlap, timestamp trước 1970, và những con số sát giới hạn precision của DB/API.

### Bài tập nhỏ

1. Từ `2026-01-15T07:30+07:00`, gọi `toLocalDateTime()` rồi `atOffset(+07:00)` có khôi phục instant không? **Có**, nếu bạn **giữ và cung cấp lại đúng offset**; `LocalDateTime` tự nó không mang offset.
2. Từ một `ZonedDateTime`, gọi `toOffsetDateTime()` có mất instant không? **Không**; vẫn có offset và ngày giờ. Nhưng **mất `ZoneId` địa lý**.
3. Từ `ZonedDateTime`, gọi `toInstant()` có làm mất nano giây không? **Không**; `Instant` hỗ trợ nano giây. Nhưng không lưu lại zone hiển thị ban đầu.
4. `Instant → LocalDate` có phép nghịch đảo duy nhất không? **Không**; còn thiếu giờ trong ngày và cần zone để biết ranh giới.
5. Hai giá trị `2024-10-27T02:30` tại Paris có thể chỉ về hai instant không? **Có**, do DST overlap; cần offset đã chọn.
6. `Instant.ofEpochMilli(event.toEpochMilli())` có bảo toàn `.123456789` không? **Không**, chỉ còn `.123`.
7. Một chuỗi `2026-01-15 07:30` đã đủ làm timestamp giao dịch chưa? **Chưa**; còn thiếu offset/zone, giây và phần nhỏ giây nếu nghiệp vụ cần.
8. `Date.from(instant).toInstant()` có giữ mọi nano giây không? **Không**, chỉ đến độ chính xác mili giây.

## 11. Checklist tránh mất thông tin khi viết Java

- [ ] Xác định dữ liệu là **ngày lịch**, **giờ địa phương**, **lịch hẹn có zone** hay **instant sự kiện**.
- [ ] Ghi ra rõ các trường nguồn và trường nào **không còn trong kiểu đích**.
- [ ] Nếu bỏ `ZoneId` hoặc `ZoneOffset`, quyết định có cần giữ chúng trong trường riêng không.
- [ ] Nếu từ local date-time gắn zone, định nghĩa cách xử lý **DST gap/overlap** và offset được chọn.
- [ ] Nếu chuyển sang `LocalDate` hoặc `LocalTime`, không kỳ vọng phần đã bỏ có thể tự phục hồi.
- [ ] Nếu chuyển `Instant` sang local date, dùng **zone nghiệp vụ tường minh**, không ngầm lấy timezone mặc định của server.
- [ ] Nếu qua epoch seconds/millis, `java.util.Date`, DB hay formatter, xác nhận **độ chính xác tối đa của đích**.
- [ ] Tách chuỗi **hiển thị cho người dùng** khỏi dữ liệu chuẩn cần lưu trữ.
- [ ] Viết unit test so sánh instant, ngày/giờ local, zone, offset và nano giây **theo đúng thuộc tính nghiệp vụ**.
- [ ] Kiểm tra hành vi khi khác ngày giữa các vùng, DST overlap/gap, và ngày giờ trước epoch.
- [ ] Nhớ `java.time` immutable: gọi một phép chuyển hoặc biến đổi mà bỏ giá trị trả về **không thay đổi đối tượng nguồn**.

**Ghi nhớ:** Chuyển đổi ngày giờ không đơn thuần là đổi tên class. Hãy luôn hỏi **“đang giữ lại ngày, giờ địa phương, vùng múi giờ, instant hay độ chính xác nào?”**. Phép chuyển `ZonedDateTime → LocalDateTime` bỏ offset/zone; `LocalDateTime → LocalDate` bỏ giờ; `ZonedDateTime → Instant` giữ sự kiện nhưng bỏ cách biểu diễn theo vùng; còn epoch millis/`Date` hoặc formatter thiếu trường có thể làm mất nano giây. Giữ riêng mọi ngữ cảnh cần thiết để dữ liệu vẫn đúng khi lưu, truyền và đọc lại.