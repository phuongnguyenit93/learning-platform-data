# Kiểm thử chuyển giờ mùa hè và thời điểm sát ranh giới ngày

Khi xử lý ngày giờ trong Java, nhiều lỗi chỉ xuất hiện vào những thời điểm đặc biệt: đồng hồ địa phương nhảy qua một giờ khi bắt đầu giờ mùa hè, lặp lại một giờ khi kết thúc giờ mùa hè, hoặc một sự kiện nằm sát nửa đêm. Nếu chỉ kiểm thử các thời điểm thông thường, ứng dụng có thể vẫn sai khi quy đổi múi giờ, tính khoảng thời gian trong ngày hoặc lọc dữ liệu theo ngày.

Với Jackson, bài toán còn có thêm một lớp: JSON biểu diễn ngày giờ dưới dạng chuỗi hoặc timestamp, còn Java có nhiều kiểu với ý nghĩa khác nhau như `Instant`, `LocalDate`, `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime`. Kiểm thử đúng cần xác định rõ dữ liệu biểu diễn một thời điểm tuyệt đối hay một giờ trên lịch địa phương, sau đó kiểm tra cả chuyển đổi Java lẫn serialize/deserialize JSON.

## 1. Phân biệt thời điểm, ngày lịch và giờ địa phương

Trước khi viết test, cần chọn đúng kiểu Java cho ý nghĩa của dữ liệu.

| Kiểu | Ý nghĩa | Có xác định duy nhất một thời điểm không? |
|---|---|---|
| `Instant` | Một thời điểm trên dòng thời gian UTC | Có |
| `LocalDate` | Ngày lịch, không có giờ và múi giờ | Không |
| `LocalTime` | Giờ trên đồng hồ, không có ngày và múi giờ | Không |
| `LocalDateTime` | Ngày và giờ địa phương, không có múi giờ hoặc offset | Không |
| `OffsetDateTime` | Ngày giờ kèm UTC offset cố định | Có |
| `ZonedDateTime` | Ngày giờ kèm `ZoneId` và quy tắc múi giờ khu vực | Có, sau khi xác định offset hợp lệ |

Ví dụ:

```java
Instant instant = Instant.parse("2024-10-27T01:30:00Z");
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime parisTime = instant.atZone(paris);
```

`Instant` biểu diễn một thời điểm duy nhất. `parisTime` là cách hiển thị thời điểm đó theo quy tắc của `Europe/Paris` tại ngày tương ứng.

Ngược lại:

```java
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
```

`LocalDateTime` chỉ nói “ngày 27 tháng 10 lúc 02:30”. Nó không nói đang ở múi giờ nào và không xác định offset. Ở một khu vực có chuyển giờ mùa hè, cùng một `LocalDateTime` có thể không tương ứng với thời điểm nào cả hoặc tương ứng với hai thời điểm khác nhau.

Quy tắc lựa chọn thực tế:

- Dùng `Instant` cho thời điểm sự kiện, thời điểm tạo bản ghi, thời điểm giao dịch hoặc timestamp cần so sánh toàn cầu.
- Dùng `LocalDate` cho ngày sinh, ngày nghỉ, ngày thanh toán theo lịch hoặc ngày nghiệp vụ không phụ thuộc thời điểm.
- Dùng `LocalTime` cho giờ mở cửa hoặc giờ hẹn lặp theo lịch địa phương, khi ngày và múi giờ được cung cấp ở nơi khác.
- Dùng `LocalDateTime` khi cần giữ nguyên giờ trên lịch nhưng chưa gắn múi giờ; không dùng nó như một instant.
- Dùng `OffsetDateTime` khi offset trong dữ liệu đầu vào là đủ để xác định thời điểm.
- Dùng `ZonedDateTime` khi cần cả thời điểm và quy tắc của một vùng như `Europe/Paris` hoặc `Asia/Ho_Chi_Minh`.

## 2. Giờ mùa hè tạo ra khoảng trống và khoảng lặp

Chuyển giờ mùa hè (Daylight Saving Time, DST) thường làm đồng hồ địa phương tiến hoặc lùi một giờ. Không phải mọi quốc gia đều áp dụng DST, và quy tắc có thể thay đổi theo năm. Vì vậy, không được giả định mọi ngày đều có 24 giờ hoặc mọi múi giờ đều có chuyển đổi giống nhau.

Hai tình huống cần kiểm thử là:

- **Gap (khoảng trống):** đồng hồ nhảy tiến. Một số giờ địa phương không tồn tại.
- **Overlap (khoảng lặp):** đồng hồ lùi. Một số giờ địa phương xuất hiện hai lần.

Ví dụ với `Europe/Paris` trong năm 2024:

**Chuyển sang giờ mùa hè — 31/03/2024:** đồng hồ nhảy từ 01:59:59 lên 03:00:00 theo giờ địa phương.

```text
01:59:59  ->  [02:00–02:59 không tồn tại]  ->  03:00:00
```

**Trở lại giờ chuẩn — 27/10/2024:** đồng hồ lùi từ 03:00 về 02:00, nên khoảng 02:00–02:59 xuất hiện hai lần.

```text
02:30 UTC+02:00  ->  02:30 UTC+01:00
      lần thứ nhất        lần thứ hai
```

Trong ví dụ trên, hai lần 02:30 có cùng ngày và giờ trên đồng hồ nhưng cách nhau một giờ trên dòng thời gian. Nếu ứng dụng chỉ lưu `LocalDateTime`, thông tin phân biệt hai lần xuất hiện này bị mất.

## 3. Dùng ZoneRules để phát hiện gap và overlap

Java Time cung cấp `ZoneRules` để truy vấn offset hợp lệ cho một `LocalDateTime` trong một `ZoneId`.

```java
ZoneId zone = ZoneId.of("Europe/Paris");
ZoneRules rules = zone.getRules();

LocalDateTime local = LocalDateTime.of(2024, 3, 31, 2, 30);
List<ZoneOffset> offsets = rules.getValidOffsets(local);
```

Kết quả có ý nghĩa:

| Số offset hợp lệ | Ý nghĩa |
|---:|---|
| 0 | Local time nằm trong gap, không tồn tại trong vùng đó. |
| 1 | Local time bình thường, chỉ có một offset hợp lệ. |
| 2 | Local time nằm trong overlap, có hai offset hợp lệ. |

Thông thường, overlap có hai offset. API `getValidOffsets()` trả về danh sách offset hợp lệ; nếu cần chính sách rõ ràng, hãy chọn offset dựa trên quy tắc nghiệp vụ thay vì mặc định chọn phần tử đầu tiên.

### 3.1. Kiểm tra khoảng trống mùa xuân

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime missingTime = LocalDateTime.of(2024, 3, 31, 2, 30);

List<ZoneOffset> offsets = paris.getRules().getValidOffsets(missingTime);
assertTrue(offsets.isEmpty());

ZoneOffsetTransition transition = paris.getRules().getTransition(missingTime);
assertNotNull(transition);
assertTrue(transition.isGap());
```

Vì không có offset hợp lệ, `02:30` không đại diện cho một thời điểm thực tế ở Paris vào ngày đó. `getTransition()` cung cấp thông tin về lần chuyển đổi gây ra khoảng trống.

### 3.2. Kiểm tra khoảng lặp mùa thu

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime repeatedTime = LocalDateTime.of(2024, 10, 27, 2, 30);

List<ZoneOffset> offsets = paris.getRules().getValidOffsets(repeatedTime);
assertEquals(2, offsets.size());

ZonedDateTime first = ZonedDateTime.ofStrict(repeatedTime, offsets.get(0), paris);
ZonedDateTime second = ZonedDateTime.ofStrict(repeatedTime, offsets.get(1), paris);

assertNotEquals(first.toInstant(), second.toInstant());
```

Hai `ZonedDateTime` có cùng local date-time và cùng zone nhưng khác offset, vì vậy `toInstant()` cho hai thời điểm khác nhau.

## 4. Chọn chính sách khi gặp giờ không tồn tại hoặc xuất hiện hai lần

`LocalDateTime.atZone(zone)` có hành vi điều chỉnh mặc định:

- Trong gap, Java dịch giờ địa phương về phía trước theo độ dài gap để tạo một thời điểm hợp lệ.
- Trong overlap, Java mặc định chọn offset sớm hơn (offset trước khi chuyển đổi); có thể chọn offset muộn hơn bằng `withLaterOffsetAtOverlap()`.

Hành vi mặc định tiện lợi cho một số ứng dụng lịch, nhưng có thể không phù hợp với hệ thống đặt vé, thanh toán, lịch giao dịch hoặc tác vụ cần thời điểm chính xác.

### 4.1. Không tự động chấp nhận giờ trong gap

Nếu giờ do người dùng nhập phải tồn tại đúng như đã chọn, hãy từ chối gap:

```java
static ZonedDateTime resolveStrict(
        LocalDateTime local,
        ZoneId zone,
        ZoneOffset selectedOffset) {

    List<ZoneOffset> validOffsets = zone.getRules().getValidOffsets(local);

    if (validOffsets.isEmpty()) {
        throw new DateTimeException("Local time does not exist in zone: " + local + " " + zone);
    }

    if (validOffsets.size() > 1 && selectedOffset == null) {
        throw new DateTimeException("Local time is ambiguous; an offset must be selected");
    }

    ZoneOffset offset = selectedOffset != null ? selectedOffset : validOffsets.get(0);
    return ZonedDateTime.ofStrict(local, offset, zone);
}
```

`ZonedDateTime.ofStrict()` kiểm tra offset có hợp lệ cho local time và zone hay không. Với overlap, caller phải chọn offset; với giờ bình thường, có thể dùng offset duy nhất.

### 4.2. Cho người dùng chọn lần xuất hiện trong overlap

Nếu nghiệp vụ cho phép cả hai lần 02:30, giao diện cần hiển thị offset hoặc lựa chọn “lần thứ nhất/lần thứ hai”. Có thể tạo hai lựa chọn:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
List<ZoneOffset> offsets = paris.getRules().getValidOffsets(local);

ZonedDateTime firstOccurrence = ZonedDateTime.ofStrict(local, offsets.get(0), paris);
ZonedDateTime secondOccurrence = ZonedDateTime.ofStrict(local, offsets.get(1), paris);
```

Trong một số nghiệp vụ, quy tắc có thể luôn chọn offset sớm hoặc muộn. Hãy mã hóa quy tắc đó thành một hàm có tên rõ ràng và test riêng; không để quyết định quan trọng phụ thuộc vào hành vi mặc định không được ghi nhận.

### 4.3. Khi nào nên dùng atZone()?

`atZone()` hữu ích khi quy tắc “điều chỉnh gap và chọn offset mặc định trong overlap” đúng với nghiệp vụ. Ví dụ, khi tạo lịch nhắc theo giờ địa phương, ứng dụng có thể muốn một giờ không tồn tại được chuyển tới giờ hợp lệ kế tiếp.

Nếu không muốn hành vi đó, hãy kiểm tra `ZoneRules` trước khi chuyển đổi hoặc dùng `ofStrict()` với offset do nghiệp vụ lựa chọn.

## 5. Kiểm thử ranh giới ngày trong múi giờ cụ thể

Một ngày trên lịch địa phương không phải lúc nào cũng dài 24 giờ. Ngày có chuyển đổi DST có thể dài 23 hoặc 25 giờ. Vì vậy, không nên tính cuối ngày bằng cách cộng 24 giờ vào đầu ngày.

### 5.1. Tính khoảng ngày bằng ngày lịch kế tiếp

Để lấy khoảng thời gian của một ngày trong zone:

```java
static Instant startOfDay(LocalDate date, ZoneId zone) {
    return date.atStartOfDay(zone).toInstant();
}

static Instant startOfNextDay(LocalDate date, ZoneId zone) {
    return date.plusDays(1).atStartOfDay(zone).toInstant();
}
```

Sử dụng khoảng nửa mở `[startInclusive, endExclusive)`:

```java
static boolean belongsToDate(Instant instant, LocalDate date, ZoneId zone) {
    Instant start = date.atStartOfDay(zone).toInstant();
    Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
    return !instant.isBefore(start) && instant.isBefore(end);
}
```

Khoảng nửa mở có nghĩa:

- Bao gồm đúng thời điểm bắt đầu ngày.
- Không bao gồm thời điểm bắt đầu ngày kế tiếp.
- Không cần tạo “23:59:59.999999999” để đại diện cuối ngày.
- Tránh lỗi khi độ chính xác timestamp thay đổi từ milliseconds sang microseconds hoặc nanoseconds.

### 5.2. Không cộng Duration.ofHours(24) để tìm ngày kế tiếp

Ví dụ kiểm tra ngày chuyển sang giờ mùa hè ở Paris:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDate date = LocalDate.of(2024, 3, 31);

Instant start = date.atStartOfDay(paris).toInstant();
Instant end = date.plusDays(1).atStartOfDay(paris).toInstant();

Duration dayLength = Duration.between(start, end);
assertEquals(Duration.ofHours(23), dayLength);
```

Ngày kết thúc DST có 25 giờ:

```java
LocalDate date = LocalDate.of(2024, 10, 27);
Instant start = date.atStartOfDay(paris).toInstant();
Instant end = date.plusDays(1).atStartOfDay(paris).toInstant();

assertEquals(Duration.ofHours(25), Duration.between(start, end));
```

Nếu lấy `start.plus(Duration.ofHours(24))` làm cuối ngày, kết quả sẽ sai trong hai trường hợp này. Hãy cộng một ngày lịch (`date.plusDays(1)`) rồi mới chuyển sang instant theo zone.

### 5.3. atStartOfDay() có ý nghĩa theo quy tắc zone

`LocalDate.atStartOfDay(zone)` trả về thời điểm bắt đầu ngày sớm nhất hợp lệ trong zone. Ở một số khu vực, chuyển đổi múi giờ có thể xảy ra ngay gần nửa đêm, khiến `00:00` không tồn tại hoặc có offset đặc biệt. Vì vậy, dùng `atStartOfDay(zone)` an toàn hơn việc tự ghép `date.atTime(0, 0).atZone(zone)` rồi giả định mọi ngày đều bắt đầu đúng 00:00.

Đối với báo cáo theo ngày, cần xác định zone nghiệp vụ trước khi tính start/end. Cùng một instant có thể thuộc ngày khác nhau trong `UTC`, `Asia/Ho_Chi_Minh` và `America/Los_Angeles`.

## 6. Kiểm thử các thời điểm sát ranh giới

Một lỗi phổ biến là dùng điều kiện cuối ngày bao gồm một timestamp giả định như `23:59:59.999`. Điều này phụ thuộc độ chính xác và có thể bỏ sót dữ liệu có phần lẻ lớn hơn.

Với khoảng nửa mở, test ba điểm:

```java
Instant start = date.atStartOfDay(zone).toInstant();
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();

assertTrue(belongsToDate(start, date, zone));
assertTrue(belongsToDate(end.minusNanos(1), date, zone));
assertFalse(belongsToDate(end, date, zone));
```

Các điểm quan trọng:

| Điểm kiểm tra | Kỳ vọng |
|---|---|
| `start` | Thuộc ngày đang xét |
| `start.minusNanos(1)` | Không thuộc ngày đang xét |
| `end.minusNanos(1)` | Thuộc ngày đang xét |
| `end` | Thuộc ngày kế tiếp, không thuộc ngày đang xét |

Nếu hệ thống lưu timestamp ở độ chính xác milliseconds, vẫn nên kiểm tra với `Instant` có nanosecond để xác nhận logic khoảng không phụ thuộc độ chính xác lưu trữ. Khi ghi xuống database, cần hiểu độ chính xác cột timestamp có thể bị làm tròn hoặc cắt.

### 6.1. Kiểm thử quanh đúng thời điểm chuyển đổi DST

`ZoneOffsetTransition` cung cấp instant chính xác mà offset thay đổi:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneOffsetTransition transition = paris.getRules().getTransition(
    LocalDateTime.of(2024, 3, 31, 2, 30)
);

Instant transitionInstant = transition.getInstant();
ZonedDateTime before = transitionInstant.minusNanos(1).atZone(paris);
ZonedDateTime after = transitionInstant.atZone(paris);

assertNotEquals(before.getOffset(), after.getOffset());
```

Test sát trước và đúng tại transition giúp xác nhận offset thay đổi tại ranh giới chính xác. Có thể thêm test một giây trước/sau nếu hệ thống làm việc với độ chính xác giây.

### 6.2. Kiểm thử khoảng thời gian qua DST

Hai local time cách nhau một giờ trên đồng hồ không nhất thiết cách nhau một giờ trên dòng thời gian, và ngược lại. Khi tính thời lượng thực, hãy chuyển về `Instant`:

```java
ZonedDateTime start = ZonedDateTime.of(
    2024, 3, 31, 1, 30, 0, 0, paris
);
ZonedDateTime end = ZonedDateTime.of(
    2024, 3, 31, 3, 30, 0, 0, paris
);

Duration elapsed = Duration.between(start.toInstant(), end.toInstant());
```

Trong ngày chuyển sang giờ mùa hè tại Paris, khoảng cách trên đồng hồ từ 01:30 đến 03:30 là hai giờ, nhưng thời gian thực đã trôi qua chỉ là một giờ. Nếu tính thời lượng công việc, thời gian chờ hoặc thời hạn thực, hãy tính trên instant. Nếu tính số giờ hiển thị trên lịch, hãy dùng quy tắc lịch phù hợp với nghiệp vụ.

## 7. Dùng Clock để kiểm thử ngày giờ ổn định

Code gọi trực tiếp `LocalDate.now()` hoặc `Instant.now()` phụ thuộc đồng hồ hệ thống, khiến test khó tái lập. Java cung cấp `Clock` để tiêm thời gian vào logic.

```java
public class BillingService {
    private final Clock clock;
    private final ZoneId businessZone;

    public BillingService(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public LocalDate currentBusinessDate() {
        return LocalDate.now(clock.withZone(businessZone));
    }
}
```

Trong production, có thể inject clock hệ thống:

```java
Clock clock = Clock.systemUTC();
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
```

Trong test, dùng clock cố định:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2024-03-31T00:30:00Z"),
    ZoneOffset.UTC
);

BillingService service = new BillingService(
    fixedClock,
    ZoneId.of("Europe/Paris")
);

assertEquals(LocalDate.of(2024, 3, 31), service.currentBusinessDate());
```

`Clock.fixed()` giúp test luôn chạy tại cùng một instant bất kể ngày thực tế. Khi muốn kiểm thử thời gian tiến triển, có thể tạo clock test riêng hoặc truyền trực tiếp các instant vào hàm tính toán.

Tránh thay đổi `TimeZone.setDefault()` toàn cục trong test nếu không cần thiết. Cấu hình timezone mặc định có thể ảnh hưởng test khác chạy song song. Truyền `ZoneId` và `Clock` rõ ràng giúp test độc lập hơn.

## 8. Cấu hình Jackson cho Java Time

Để Jackson đọc/ghi các kiểu `java.time`, ứng dụng thường cần module `jackson-datatype-jsr310` và đăng ký `JavaTimeModule` (hoặc dùng cấu hình framework đã đăng ký module này).

Ví dụ mapper độc lập:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
    .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID);
```

Các thiết lập có ý nghĩa:

- `JavaTimeModule` cung cấp serializer/deserializer cho các kiểu Java Time.
- Tắt `WRITE_DATES_AS_TIMESTAMPS` giúp dùng biểu diễn chuỗi ISO thay vì timestamp/array tùy kiểu.
- Tắt `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` khi cần giữ offset hoặc zone của dữ liệu đầu vào thay vì điều chỉnh theo timezone context của mapper.
- Bật `WRITE_DATES_WITH_ZONE_ID` nếu output `ZonedDateTime` cần mang cả ID vùng như `[Europe/Paris]`.

Các lựa chọn trên cần phù hợp hợp đồng JSON của ứng dụng. Ví dụ, nếu API chỉ muốn truyền instant chuẩn hóa UTC, có thể dùng `Instant` và chuỗi UTC; nếu cần giữ vùng địa lý để xử lý lịch tương lai, `ZonedDateTime` cùng zone ID có ý nghĩa hơn.

### 8.1. Không nhầm offset với ZoneId

Chuỗi:

```text
2024-10-27T02:30:00+01:00
```

chứa offset `+01:00`, đủ để xác định một instant. Nhưng nó không cho biết vùng địa lý là `Europe/Paris`, `Europe/Berlin` hay một vùng khác có cùng offset tại thời điểm đó.

Chuỗi:

```text
2024-10-27T02:30:00+01:00[Europe/Paris]
```

có cả offset và zone ID. Điều này hữu ích khi cần giữ ngữ cảnh vùng địa lý và quy tắc DST.

Nếu API chỉ gửi `LocalDateTime` như `2024-10-27T02:30:00`, server không thể tự biết lần 02:30 nào trong overlap. Hãy yêu cầu offset/zone và một chính sách lựa chọn, hoặc từ chối local time mơ hồ.

### 8.2. @JsonFormat và pattern

`@JsonFormat` có thể định dạng property:

```java
public class Appointment {
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    private ZonedDateTime startsAt;

    private LocalDate serviceDate;
}
```

Nếu khai báo pattern tùy chỉnh, phải bảo đảm pattern chứa đủ thông tin để khôi phục dữ liệu cần thiết. Pattern chỉ có ngày giờ mà không có offset/zone sẽ không thể phân biệt hai lần xuất hiện trong overlap.

Ví dụ, pattern `yyyy-MM-dd'T'HH:mm:ss` chỉ biểu diễn local date-time. Nếu cần xác định instant, hãy dùng biểu diễn ISO có offset hoặc zone, hoặc lưu thêm thông tin zone riêng. Đừng loại bỏ offset chỉ vì muốn JSON ngắn hơn.

## 9. Kiểm thử round-trip JSON tại DST

Round-trip test giúp xác nhận Java object sau deserialize vẫn biểu diễn cùng dữ liệu thời gian như trước serialize.

```java
public class Appointment {
    private ZonedDateTime startsAt;

    public ZonedDateTime getStartsAt() {
        return startsAt;
    }

    public void setStartsAt(ZonedDateTime startsAt) {
        this.startsAt = startsAt;
    }
}
```

Test với thời điểm trong overlap:

```java
ObjectMapper mapper = new ObjectMapper()
    .registerModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
    .enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID);

ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
ZoneOffset laterOffset = ZoneOffset.ofHours(1);
ZonedDateTime expected = ZonedDateTime.ofStrict(local, laterOffset, paris);

Appointment appointment = new Appointment();
appointment.setStartsAt(expected);

String json = mapper.writeValueAsString(appointment);
Appointment restored = mapper.readValue(json, Appointment.class);

assertEquals(expected.toInstant(), restored.getStartsAt().toInstant());
assertEquals(paris, restored.getStartsAt().getZone());
assertEquals(laterOffset, restored.getStartsAt().getOffset());
```

Test kiểm tra cả instant, zone và offset. Chỉ kiểm tra local date-time là chưa đủ vì hai lần 02:30 trong overlap có cùng local value.

Nếu hợp đồng JSON chỉ lưu offset mà không lưu zone ID, test nên xác nhận instant và offset; không thể kỳ vọng deserialize khôi phục đúng `ZoneId` ban đầu.

## 10. Ví dụ JUnit 5 cho DST và ranh giới ngày

Các test sau minh họa cách kiểm tra gap, overlap, độ dài ngày và khoảng nửa mở. Ví dụ dùng `Europe/Paris` vì có hai lần chuyển đổi DST trong năm 2024.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.*;
import java.time.zone.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class DateTimeBoundaryTest {
    private static final ZoneId PARIS = ZoneId.of("Europe/Paris");

    @Test
    void springForwardLocalTimeDoesNotExist() {
        LocalDateTime local = LocalDateTime.of(2024, 3, 31, 2, 30);
        List<ZoneOffset> offsets = PARIS.getRules().getValidOffsets(local);

        assertTrue(offsets.isEmpty());
        assertTrue(PARIS.getRules().getTransition(local).isGap());
    }

    @Test
    void fallBackLocalTimeHasTwoValidOffsets() {
        LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
        List<ZoneOffset> offsets = PARIS.getRules().getValidOffsets(local);

        assertEquals(2, offsets.size());
        ZonedDateTime first = ZonedDateTime.ofStrict(local, offsets.get(0), PARIS);
        ZonedDateTime second = ZonedDateTime.ofStrict(local, offsets.get(1), PARIS);

        assertNotEquals(first.toInstant(), second.toInstant());
        assertEquals(Duration.ofHours(1),
            Duration.between(first.toInstant(), second.toInstant()));
    }

    @Test
    void springForwardDayHasTwentyThreeElapsedHours() {
        LocalDate date = LocalDate.of(2024, 3, 31);
        Instant start = date.atStartOfDay(PARIS).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(PARIS).toInstant();

        assertEquals(Duration.ofHours(23), Duration.between(start, end));
    }

    @Test
    void fallBackDayHasTwentyFiveElapsedHours() {
        LocalDate date = LocalDate.of(2024, 10, 27);
        Instant start = date.atStartOfDay(PARIS).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(PARIS).toInstant();

        assertEquals(Duration.ofHours(25), Duration.between(start, end));
    }

    @Test
    void dayRangeUsesStartInclusiveEndExclusive() {
        LocalDate date = LocalDate.of(2024, 3, 31);
        Instant start = date.atStartOfDay(PARIS).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(PARIS).toInstant();

        assertTrue(belongsToDate(start, date, PARIS));
        assertTrue(belongsToDate(end.minusNanos(1), date, PARIS));
        assertFalse(belongsToDate(end, date, PARIS));
    }

    private static boolean belongsToDate(Instant instant, LocalDate date, ZoneId zone) {
        Instant start = date.atStartOfDay(zone).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
        return !instant.isBefore(start) && instant.isBefore(end);
    }
}
```

Các test trên dùng ngày chuyển đổi cụ thể. Khi kiểm thử hệ thống thực tế, hãy chọn zone nghiệp vụ thật và các mốc chuyển đổi có ý nghĩa với ứng dụng. Quy tắc múi giờ được cung cấp bởi cơ sở dữ liệu timezone của JDK và có thể được cập nhật khi luật địa phương thay đổi.

## 11. Các lỗi thường gặp khi kiểm thử ngày giờ

### Dùng LocalDateTime để so sánh thời điểm toàn cầu

Hai `LocalDateTime` giống nhau ở hai zone có thể đại diện cho hai instant khác nhau. Nếu cần so sánh sự kiện xảy ra trước/sau, hãy chuyển sang `Instant` hoặc dùng `ZonedDateTime` đã xác định offset.

### Cộng 24 giờ để tìm đầu ngày kế tiếp

Một ngày DST có thể dài 23 hoặc 25 giờ. Hãy tính `date.plusDays(1).atStartOfDay(zone)` thay vì `start.plus(Duration.ofHours(24))`.

### Dùng cuối ngày là 23:59:59.999

Độ chính xác timestamp có thể cao hơn milliseconds. Dùng khoảng `[start, end)` để không bỏ sót dữ liệu tại ranh giới.

### Chỉ test thời điểm thông thường

Hãy bổ sung gap, overlap, thời điểm ngay trước/sau transition, start/end của ngày và timestamp có phần nanosecond.

### Dựa vào timezone mặc định của máy

Test chạy trên máy developer và CI có thể cho kết quả khác nhau nếu dùng timezone mặc định. Truyền `ZoneId` rõ ràng và dùng `Clock` cố định.

### Lưu local date-time mà không có zone/offset

Nếu dữ liệu đại diện một sự kiện đã xảy ra hoặc một cuộc hẹn cần xác định duy nhất, chỉ lưu `LocalDateTime` sẽ không đủ trong overlap. Hãy lưu `Instant` và zone ID nếu cần giữ ngữ cảnh vùng.

### Jackson làm mất zone trong round-trip

Nếu JSON chỉ chứa offset, không thể khôi phục `ZoneId` ban đầu. Nếu cần giữ vùng địa lý, hãy xuất zone ID hoặc lưu riêng zone; kiểm tra `WRITE_DATES_WITH_ZONE_ID` và `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` theo hợp đồng.

## 12. Bộ trường hợp nên có trong test suite

Một test suite cho ngày giờ và múi giờ nên bao gồm:

| Nhóm | Trường hợp |
|---|---|
| Gap | Local time không tồn tại khi đồng hồ nhảy tiến |
| Gap | Chính sách từ chối hoặc điều chỉnh gap được kiểm tra rõ |
| Overlap | Local time có hai offset hợp lệ |
| Overlap | Chọn offset sớm và offset muộn tạo hai instant khác nhau |
| Transition instant | Kiểm tra ngay trước, đúng tại và ngay sau instant chuyển đổi |
| Day boundary | Đúng start, một nanosecond trước end và đúng end |
| DST day length | Ngày 23 giờ và ngày 25 giờ |
| Zone conversion | Cùng instant hiển thị thành local date/time khác nhau ở các zone |
| Jackson round-trip | Giữ instant, offset và zone theo hợp đồng JSON |
| Clock | Test không phụ thuộc thời gian thực hoặc timezone mặc định của máy |
| Precision | Nanosecond/millisecond tại ranh giới và độ chính xác database |

## Kết luận

Kiểm thử DST cần phát hiện hai tình huống đặc biệt: giờ địa phương không tồn tại trong gap và giờ địa phương xuất hiện hai lần trong overlap. Dùng `ZoneRules` để xác định offset hợp lệ, chọn chính sách rõ ràng và dùng `Instant` khi cần thời lượng thực. Với ranh giới ngày, tính đầu ngày kế tiếp từ `LocalDate.plusDays(1)` trong zone nghiệp vụ và dùng khoảng nửa mở `[start, end)`, vì ngày địa phương có thể dài 23 hoặc 25 giờ. Khi kết hợp Jackson, đăng ký `JavaTimeModule`, xác định rõ dạng JSON và kiểm thử round-trip để bảo toàn instant, offset hoặc zone theo đúng hợp đồng dữ liệu.
