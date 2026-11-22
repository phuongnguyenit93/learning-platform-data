# Thiết kế dữ liệu thời gian ở biên API, lưu trữ và hiển thị với `java.time`

Một timestamp là dữ liệu nghiệp vụ, không chỉ là chuỗi để hiển thị. Dòng `"2026-01-20 09:30"` không thể tự xác định một khoảnh khắc toàn cầu: đó là giờ đồng hồ tại địa điểm nào, có chịu quy tắc giờ mùa hè (DST) không, đã được chốt thành một instant hay là một giờ hẹn dự định? Nếu API, backend, database và UI tự suy đoán các câu trả lời khác nhau, hệ thống có thể lệch giờ, lệch ngày hoặc tính sai hạn.

Java 8 cung cấp gói `java.time` gồm các kiểu bất biến như `Instant`, `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime`, `ZoneId`, `Duration`, `Period`, `DateTimeFormatter` và `Clock`. Đây vẫn là mô hình được hỗ trợ trong Java hiện đại.

**Nguyên tắc:** phân biệt **một thời điểm thực**, **một ngày lịch**, **một giờ địa phương**, và **ý định đặt lịch tại một vùng múi giờ**. Quyết định kiểu dữ liệu trước khi quyết định format.

## 1. Ba câu hỏi trước khi tạo field thời gian

1. **Có phải mốc thời gian đã xảy ra hoặc được xác định duy nhất?** Ví dụ `createdAt`, `paidAt`, `eventOccurredAt`: dùng `Instant` hoặc biểu diễn ISO 8601 có offset rõ.
2. **Có phải ngày/giờ theo lịch địa phương?** Ví dụ ngày sinh, ngày nghỉ, giờ cửa hàng mở: dùng `LocalDate`, `LocalTime`; nếu có cả ngày và giờ chưa gắn vùng, dùng `LocalDateTime`.
3. **Cần lịch tại vùng nào?** Với lịch hẹn tại New York hay Paris, cần `ZoneId` vùng theo IANA, không chỉ offset +01:00/-05:00. Khi nhận dữ liệu, phải có chính sách cho giờ địa phương không tồn tại hoặc bị lặp trong DST.

Tương ứng, một phiếu hẹn có thể có `createdAt: Instant`, `appointmentDate: LocalDate`, `appointmentTime: LocalTime`, `appointmentZone: ZoneId` và `resolvedStartAt: Instant`. Những trường này diễn tả **các sự thật khác nhau**; không nên thay tất cả bằng một `String` hoặc `LocalDateTime`.

## 2. Chọn đúng kiểu trong Java

| Kiểu | Ý nghĩa | Ví dụ | Phạm vi sử dụng |
| --- | --- | --- | --- |
| `Instant` | Một điểm trên dòng thời gian | `2026-01-20T02:30:00Z` | Sự kiện, nhật ký, mốc đã chốt, so sánh thời điểm |
| `LocalDate` | Ngày lịch không có giờ, offset, zone | `2026-01-20` | Sinh nhật, ngày nghỉ, hạn theo ngày |
| `LocalTime` | Giờ đồng hồ không có ngày/zone | `09:30` | Giờ hoạt động, ca làm |
| `LocalDateTime` | Ngày + giờ địa phương, không biết zone | `2026-01-20T09:30` | Ý định đặt lịch trước khi resolve zone |
| `ZoneOffset` | Offset cố định so với UTC | `+07:00` | Offset đã biết ở một thời điểm |
| `ZoneId` | Vùng múi giờ với quy tắc lịch sử/tương lai | `Asia/Ho_Chi_Minh` | Lịch theo địa điểm, hiển thị theo vùng |
| `OffsetDateTime` | Ngày/giờ + offset | `2026-01-20T09:30:00+07:00` | Payload API có offset |
| `ZonedDateTime` | Ngày/giờ + vùng + offset được giải quyết | `2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh]` | Chuyển đổi lịch địa phương thành instant |
| `Duration` | Độ dài thời gian theo giây/nano | `PT30M` | Timeout, SLA tính giờ thực |
| `Period` | Độ dài theo năm/tháng/ngày lịch | `P1M` | Gia hạn một tháng, tính tuổi theo lịch |
| `Clock` | Nguồn thời gian thay thế được | `Clock.fixed(...)` | Viết test không phụ thuộc đồng hồ máy |

**Cần phân biệt:**

- `LocalDateTime` **không phải** một instant UTC. Nó chưa biết múi giờ. Không tự ép `LocalDateTime` sang UTC trừ khi hợp đồng dữ liệu xác định rõ như vậy.
- `ZoneOffset` chỉ là chênh lệch số giờ/phút, **không phải** tên vùng. Vùng `Europe/Paris` có offset khác nhau theo lịch; một offset hiện tại không đủ cho lịch lặp trong tương lai.
- `Instant` chưa quy định ngày/giờ để **hiển thị** ở đâu. Cùng instant có thể thuộc các ngày địa phương khác nhau.

## 3. Thiết kế API cho mốc thời gian tuyệt đối

Nếu trường là `createdAt`, `completedAt`, `eventTime` hay `expiresAt` đã được xác định, nên gửi chuỗi ISO có **offset rõ**; dùng UTC với `Z` là lựa chọn dễ trao đổi:

```json
{
  "id": "booking-42",
  "createdAt": "2026-01-15T02:03:04.123Z",
  "appointmentStartsAt": "2026-01-20T02:30:00Z"
}
```

Một biểu diễn khác của cùng mốc hẹn:

```json
{
  "appointmentStartsAt": "2026-01-20T09:30:00+07:00"
}
```

`2026-01-20T02:30:00Z` và `2026-01-20T09:30:00+07:00` là **cùng một instant**, mặc dù khác chuỗi. Backend có thể parse dạng có offset rồi chuẩn hóa:

```java
OffsetDateTime apiTime =
    OffsetDateTime.parse("2026-01-20T09:30:00+07:00");
Instant normalized = apiTime.toInstant();
// 2026-01-20T02:30:00Z.
```

Dạng không offset như `2026-01-20T09:30:00` **không đủ** cho một instant dùng toàn cầu. Không suy đoán rằng server/app/client ở cùng timezone. Định nghĩa rõ trong OpenAPI/JSON schema: field là timestamp offset-aware, precision được chấp nhận, có bắt buộc UTC hay không, và xử lý input thiếu offset như thế nào.

**Tên field và đơn vị:** `epochSeconds` khác `epochMillis`. Một số số nguyên dài không gắn đơn vị dễ bị parser diễn giải lệch 1.000 lần. Nếu buộc dùng epoch numeric, ghi đúng đơn vị và cách xử lý số âm/quá lớn; khi có thể, ISO timestamp rõ offset dễ đọc và trao đổi hơn.

## 4. API cho lịch hẹn theo địa phương

Trường hợp người dùng chọn **ngày 20/01/2026, lúc 09:30 tại Việt Nam** không nên chỉ lưu một string mơ hồ. Một hợp đồng tốt là:

```json
{
  "appointmentDate": "2026-01-20",
  "appointmentTime": "09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

Backend có thể parse thành `LocalDate`, `LocalTime` và `ZoneId`; từ đó ghép thành `LocalDateTime` rồi resolve thành một `Instant`.

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 1, 20);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime local = LocalDateTime.of(date, time);
ZonedDateTime zoned = local.atZone(businessZone);
Instant actual = zoned.toInstant();
// 2026-01-20T02:30:00Z.
```

Ở chiều ngược lại, từ một instant đã lưu:

```java
Instant actual = Instant.parse("2026-01-20T02:30:00Z");
ZonedDateTime forVietnam =
    actual.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
// 2026-01-20T09:30+07:00[Asia/Ho_Chi_Minh].
```

Đối với lịch hẹn ở vùng có DST, việc resolve `LocalDateTime` phải xét giờ thiếu hoặc trùng (mục 6). Nếu API gửi cả `appointmentLocal`, `timeZone` và `appointmentStartsAt`, server cần kiểm tra tính nhất quán và quyết định trường nào là nguồn sự thật, thay vì tin cả ba trường một cách độc lập.

Một **lịch lặp** thứ Hai hằng tuần lúc 09:00 New York cần giữ quy tắc lặp, `LocalTime` và `ZoneId.of("America/New_York")`. Nếu chỉ lưu một instant rồi cộng `Duration.ofDays(7)` cho mỗi lần tiếp theo, giờ hiển thị có thể đổi từ 09:00 sang 10:00 hoặc 08:00 sau DST.

## 5. Offset và ZoneId không thể thay cho nhau

`ZoneOffset.of("+07:00")` cho biết chênh lệch cố định từ UTC. `ZoneId.of("Asia/Ho_Chi_Minh")` thể hiện vùng theo quy tắc lịch sử/tương lai từ time-zone database. Một zone có thể thay đổi offset qua các năm hoặc các mùa.

Ví dụ `America/New_York` có offset `-05:00` hoặc `-04:00` tùy thời điểm. Vì vậy:

- **Instant tại thời điểm xác định:** đủ để xác định mốc toàn cầu.
- **OffsetDateTime:** chứa local fields và offset nên cũng xác định được một instant.
- **ZonedDateTime:** còn giữ zone vùng, giúp chuyển đổi theo quy tắc của địa điểm.
- **LocalDateTime:** không thể xác định một instant cho tới khi có zone hoặc offset được quy định.

Không thể **suy ngược duy nhất** ZoneId từ một instant hoặc một offset: nhiều vùng có cùng offset ở một thời điểm. Nếu địa điểm ban đầu quan trọng cho audit, chính sách tính lịch hoặc báo cáo, hãy **lưu zone ID riêng**.

## 6. DST: giờ bị thiếu (gap) và bị lặp (overlap)

Một local date-time có ba trạng thái theo `zone.getRules().getValidOffsets(localDateTime)`:

| Trạng thái | Số offset hợp lệ | Ý nghĩa |
| --- | --- | --- |
| Bình thường | 1 | Có một instant tương ứng |
| Gap | 0 | Đồng hồ nhảy tiến, local time không tồn tại |
| Overlap | 2 | Đồng hồ quay lùi, local time xảy ra hai lần |

Theo quy tắc New York năm 2024:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

System.out.println(ny.getRules().getValidOffsets(gap));
// []

System.out.println(ny.getRules().getValidOffsets(overlap));
// [-04:00, -05:00]
```

`LocalDateTime.atZone(zone)` có quy tắc mặc định: khi gặp gap, thường dịch giờ tiến lên bằng độ dài gap; trong overlap, thường dùng offset trước/earlier offset. Với ứng dụng đặt vé hoặc lịch giao dịch, **tự chọn ngầm** có thể sai nghiệp vụ.

Có thể chọn chính sách nghiêm ngặt: chỉ chấp nhận local time có đúng **một** offset:

```java
static ZonedDateTime resolveStrict(LocalDateTime local, ZoneId zone) {
    List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
    if (valid.size() != 1) {
        throw new IllegalArgumentException(
            "invalid or ambiguous local time");
    }
    return ZonedDateTime.ofStrict(local, valid.get(0), zone);
}
```

Đây là method minh họa; cần import `java.time.*` và `java.util.*`. Nếu gặp gap, ứng dụng có thể yêu cầu người dùng chọn giờ khác; nếu overlap, có thể yêu cầu chọn offset và xác minh thuộc danh sách valid offsets trước khi gọi `ZonedDateTime.ofStrict(local, selectedOffset, zone)`.

Đừng dùng offset từ **thời điểm hiện tại** để resolve một lịch vào tháng khác: offset phải được tra cho **ngày và giờ của chính lịch đó**.

### Một ngày địa phương không luôn dài 24 giờ

Khi chuyển sang DST, một ngày tại New York có thể chỉ dài 23 giờ; khi quay lại giờ mùa đông, có thể dài 25 giờ. Ví dụ:

```java
ZonedDateTime before = ZonedDateTime.of(
    LocalDate.of(2024, 3, 9),
    LocalTime.NOON,
    ZoneId.of("America/New_York"));

long elapsedHours = Duration.between(
    before.toInstant(),
    before.plusDays(1).toInstant()).toHours();
// 23 giờ.
```

`plusDays(1)` trên `ZonedDateTime` là cộng một ngày **lịch địa phương**, khác `plus(Duration.ofDays(1))` là cộng 24 giờ thực. Chọn cách nào tùy yêu cầu (gia hạn theo ngày địa phương hay SLA đúng số giờ).

## 7. Lưu trữ theo ngữ nghĩa, không dùng một `TIMESTAMP` cho tất cả

Khi thiết kế database, phân biệt:

- **Instant đã xảy ra:** dùng cột timestamp có ngữ nghĩa offset/instant đúng với database đang dùng.
- **Ngày lịch:** dùng cột `DATE`, không ép ngày sinh/hạn ngày thành 00:00 UTC.
- **Giờ địa phương chưa resolve:** cột local timestamp không có zone **kèm** vùng `ZoneId`.
- **Lịch định kỳ:** có thêm quy tắc tái diễn và zone; không cố định tất cả lượt xảy ra bằng một offset.
- **Khoảng thời gian:** lưu hai mốc instant hoặc thời lượng theo đơn vị rõ, tùy nghiệp vụ.

### 7.1. Schema PostgreSQL minh họa

```sql
CREATE TABLE appointment (
    id                  BIGINT PRIMARY KEY,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    local_start         TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    time_zone_id        VARCHAR(64) NOT NULL,
    resolved_start_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    service_date        DATE NOT NULL
);
```

- `created_at`: event thực đã diễn ra.
- `local_start`: giờ hẹn theo đồng hồ địa phương.
- `time_zone_id`: ví dụ `Asia/Ho_Chi_Minh`.
- `resolved_start_at`: instant đã resolve tại thời điểm chốt.
- `service_date`: ngày nghiệp vụ, **không** bị dịch sang ngày khác theo offset UTC.

**PostgreSQL cụ thể:** `TIMESTAMP WITH TIME ZONE`, hay `timestamptz`, lưu mốc thời gian theo UTC; **không lưu tên múi giờ/offset đầu vào**. Cách hiển thị từ SQL có thể phụ thuộc `TimeZone` của session. `TIMESTAMP WITHOUT TIME ZONE` không tự chuyển đổi múi giờ và không thể biểu diễn duy nhất một instant; với input đã được xác định là kiểu without time zone, offset trong chuỗi có thể bị bỏ qua.

Không áp đặt semantics PostgreSQL lên mọi RDBMS: MySQL, SQL Server và engine/driver khác có mapping, precision và hành vi time-zone session riêng. Xem tài liệu của **engine và phiên bản thực tế**, rồi test.

### 7.2. Java JDBC, ORM và precision

JDBC 4.2 và driver hiện đại hỗ trợ nhiều kiểu `java.time` qua `setObject/getObject`, nhưng mức hỗ trợ trực tiếp của `Instant`, `OffsetDateTime` hoặc cách ánh xạ `TIMESTAMP WITH TIME ZONE` phụ thuộc driver/ORM. Đừng mặc định mọi driver tự xử lý UTC giống nhau.

Ví dụ ý tưởng, nếu có `PreparedStatement ps` và `LocalDate serviceDate`:

```java
ps.setObject(1, serviceDate);
```

Trong integration test, hãy tạo dữ liệu có nano, một timezone session không phải UTC, ghi → đọc lại và so **giá trị domain**. `Instant` chứa phần nano trong Java, trong khi PostgreSQL thường lưu timestamp với độ phân giải microsecond. So exact `Instant.equals` không qua chuẩn hóa precision có thể thất bại dù database hoạt động đúng theo hợp đồng.

Nếu contract dùng millisecond:

```java
Instant normalized =
    incoming.truncatedTo(ChronoUnit.MILLIS);
```

Đây là đoạn mã minh họa, cần `import java.time.temporal.ChronoUnit;`. `truncatedTo` **cắt** độ chính xác nhỏ hơn milliseconds, không phải round-half-up.

### 7.3. Đừng mất ý định lịch trong dữ liệu lưu trữ

Đối với event đã xảy ra, `Instant` thường đủ. Với lịch hẹn tương lai hoặc lịch lặp, chỉ lưu `Instant` có thể làm mất ý định `09:30 theo giờ địa phương` khi các quy tắc timezone thay đổi.

Hãy cân nhắc lưu cả `local_start` + `time_zone_id` + `resolved_start_at` và quy định rõ chính sách:

1. Nếu cuộc hẹn đã chốt thì giữ nguyên instant đã xác nhận hay cập nhật để giữ giờ địa phương khi luật múi giờ đổi?
2. Nếu lịch lặp, mỗi lần xảy ra có resolve lại từ local calendar theo zone rules mới không?
3. Nếu cần audit pháp lý, có lưu offset lúc xác nhận hoặc snapshot thông báo hiển thị cho người dùng không?

Đó là yêu cầu domain; không có một lựa chọn đúng cho mọi sản phẩm.

## 8. Truy vấn theo ngày địa phương: khoảng nửa mở

Để tìm mọi event thuộc ngày `2026-01-20` của một chi nhánh ở Việt Nam, **không** suy từ `DATE(timestamp)` trong timezone session bất kỳ. Tính hai ranh giới theo zone nghiệp vụ:

```java
LocalDate day = LocalDate.of(2026, 1, 20);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant fromInclusive = day.atStartOfDay(zone).toInstant();
Instant toExclusive =
    day.plusDays(1).atStartOfDay(zone).toInstant();
```

Và truy vấn:

```sql
SELECT id, created_at
FROM appointment
WHERE created_at >= :from_inclusive
  AND created_at < :to_exclusive
ORDER BY created_at, id;
```

**Tại sao dùng `[start, end)`?** Một event đúng thời điểm bắt đầu ngày sau thuộc **ngày sau**, không bị đếm hai lần. Không cần đoán độ chính xác millisecond/microsecond để tính 23:59:59.999999.

Hai ranh giới được tính độc lập từ hai ngày lịch; khoảng giữa có thể dài 23/25 giờ tại vùng có DST. `LocalDate.atStartOfDay(zone)` chọn thời điểm sớm nhất hợp lệ của ngày; với một số vùng/lịch sử có thay đổi vào lúc nửa đêm, không mặc định mọi đầu ngày đều là 00:00.

Truy vấn trực tiếp cột timestamp với điều kiện range cũng thường thuận lợi hơn cho chỉ mục so với bọc hàm chuyển đổi lên cột, nhưng hiệu năng phải được xác nhận bằng query plan thực tế.

## 9. Hiển thị là trách nhiệm của ranh giới UI

Backend nên trả time có **ngữ nghĩa**, còn UI định dạng theo **zone + locale** của người dùng hoặc đơn vị nghiệp vụ. Không tự chọn zone theo timezone hệ điều hành của server và không dùng string display làm dữ liệu giao tiếp giữa các service.

Ví dụ:

```java
Instant instant = Instant.parse("2026-01-20T02:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
DateTimeFormatter format = DateTimeFormatter.ofPattern(
    "dd/MM/uuuu HH:mm",
    Locale.forLanguageTag("vi-VN"));

String visible = format.format(instant.atZone(zone));
// "20/01/2026 09:30".
```

Những quyết định UX cần nêu rõ:

- Người xem muốn giờ của **chính mình**, giờ **chi nhánh**, hay giờ **địa điểm diễn ra sự kiện**?
- Có cần hiện **zone/offset** bên cạnh để tránh nhầm giờ khi trao đổi quốc tế?
- Dùng ngày/tháng/năm hay tháng/ngày/năm, giờ 12h hay 24h, và ngôn ngữ của nhãn?
- Giá trị `null`/chưa xác định nên hiển thị ra sao để không nhầm là Unix epoch?
- Nếu người xem đổi zone, **instant lưu trữ phải giữ nguyên**; chỉ phần trình bày đổi.

`DateTimeFormatter` là immutable và thread-safe, thuận lợi khi tái sử dụng ở backend. Với định dạng hoàn toàn theo locale, `ofLocalizedDateTime(...)` có thể phù hợp hơn pattern tự đặt. Trong mẫu, `uuuu` là năm proleptic; **`YYYY` là week-based-year** và có thể cho năm sai ở ranh giới năm. Đừng dùng `YYYY-MM-dd` để format ngày lịch thông thường.

Không dùng các tên viết tắt múi giờ `CST`/`IST`/`EST` làm dữ liệu API vì có thể mơ hồ hoặc không mô tả đủ DST. Dùng zone IANA và offset ISO rõ ràng.

## 10. `Duration` hay `Period`?

`Duration` biểu diễn khoảng thời gian thực tính theo giây/nano. `Period` biểu diễn khoảng theo năm/tháng/ngày lịch.

| Trường hợp | Nên dùng | Lý do |
| --- | --- | --- |
| Timeout request 30 giây | `Duration.ofSeconds(30)` | Giây thực |
| Hạn 48 giờ kể từ mốc đã ghi | `Instant.plus(Duration.ofHours(48))` | Chính xác 48 giờ |
| Gia hạn thêm một tháng lịch | `LocalDate.plusMonths(1)` hoặc `Period.ofMonths(1)` | Tháng có số ngày khác nhau |
| Hẹn 09:00 hằng ngày | `LocalTime` + lịch lặp + `ZoneId` | Giữ giờ địa phương qua DST |
| Tuổi theo ngày sinh | `Period.between(birthDate, todayInZone)` | Năm/tháng/ngày theo lịch |

Ví dụ:

```java
Instant start = Instant.parse("2026-01-20T02:30:00Z");
Instant finish = start.plus(Duration.ofMinutes(30));
Duration elapsed = Duration.between(start, finish);
// PT30M.
```

"1 tháng nữa" không tự động bằng 30 ngày. "24 giờ nữa" không phải lúc nào giống "cùng giờ đồng hồ ngày mai" ở vùng có DST.

## 11. Test thời gian bằng `Clock` và dữ liệu biên

Gọi `Instant.now()` trực tiếp ở mọi chỗ làm test phụ thuộc đồng hồ thực. `Clock` có từ Java 8 giúp tạo thời điểm ổn định:

```java
Clock clock = Clock.fixed(
    Instant.parse("2026-01-15T02:03:04.123Z"),
    ZoneOffset.UTC);

Instant createdAt = Instant.now(clock);
// 2026-01-15T02:03:04.123Z.
```

Ứng dụng có thể inject `Clock` qua constructor; production chọn `Clock.systemUTC()`/`system(zone)` với ý nghĩa rõ, test truyền `Clock.fixed(...)`. Để biết "hôm nay" theo một chi nhánh, dùng `LocalDate.now(clock.withZone(businessZone))` thay vì mặc định lấy ngày trên máy CI.

### Ma trận test cần có

1. **Serialize/parse:** ISO instant qua API và parse ngược vẫn cùng instant trong precision đã quy định.
2. **Hai offset cùng instant:** `2026-01-20T02:30:00Z` và `2026-01-20T09:30:00+07:00`.
3. **Ngày địa phương khác UTC:** instant gần nửa đêm có thể thuộc ngày khác ở zone xa.
4. **DST gap:** local time không tồn tại bị từ chối hoặc dịch theo policy.
5. **DST overlap:** local time có hai offset được xử lý có chủ đích.
6. **Độ dài ngày:** một ngày có thể 23/24/25 giờ; so `plusDays` với `Duration`.
7. **Khoảng `[start,end)`:** bắt đầu được tính, kết thúc bị loại.
8. **Precision:** round-trip database giữ micro/milli/nano đúng với hợp đồng.
9. **Timezone session:** thử với zone kết nối database khác zone người dùng.
10. **Ngày và năm biên:** tháng 2 nhuận, 31/02 không hợp lệ, cuối tháng, ranh giới week-year.
11. **Lịch lặp:** local time ổn định ở nhiều lần xuất hiện qua DST.
12. **Đầu vào xấu:** zone ID sai, thiếu offset, epoch sai đơn vị, timestamp ngoài miền cho phép.

Nếu ứng dụng cần tính chính xác một nghiệp vụ, test cả **kiểu domain** lẫn SQL mapping và UI; không chỉ test một hàm format.

## 12. Chương trình Java hoàn chỉnh: kiểm tra API, zone, UI và DST

Tạo file **`TimeBoundaryDemo.java`**. Chương trình chỉ dùng API có từ Java 8 và chạy được với JDK 17+; không kết nối database. Mọi mốc được cố định để kết quả dễ kiểm chứng.

```java
import java.time.*;
import java.time.format.*;
import java.time.zone.*;
import java.util.*;

public class TimeBoundaryDemo {
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");
    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    static ZonedDateTime resolveStrict(LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);
        if (valid.size() != 1) {
            throw new IllegalArgumentException("invalid or ambiguous local time");
        }
        return ZonedDateTime.ofStrict(local, valid.get(0), zone);
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-15T02:03:04.123Z"),
                ZoneOffset.UTC);
        Instant createdAt = Instant.now(fixed);

        LocalDate bookingDate = LocalDate.of(2026, 1, 20);
        LocalTime bookingTime = LocalTime.of(9, 30);
        LocalDateTime localBooking =
                LocalDateTime.of(bookingDate, bookingTime);
        ZonedDateTime booking =
                resolveStrict(localBooking, BUSINESS_ZONE);
        Instant storedInstant = booking.toInstant();

        String apiUtc = DateTimeFormatter.ISO_INSTANT.format(storedInstant);
        String apiOffset = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd'T'HH:mm:ssXXX").format(booking);
        Instant decoded = OffsetDateTime.parse(
                apiOffset, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant();

        String display = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"))
                .format(storedInstant.atZone(BUSINESS_ZONE));

        Instant endExclusive =
                storedInstant.plus(Duration.ofMinutes(30));

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> overlapOffsets =
                NEW_YORK.getRules().getValidOffsets(overlap);
        Instant laterInstant = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.of("-05:00"), NEW_YORK).toInstant();

        ZonedDateTime beforeDst = ZonedDateTime.of(
                LocalDate.of(2024, 3, 9),
                LocalTime.NOON,
                NEW_YORK);
        long hoursInCalendarDay = Duration.between(
                beforeDst.toInstant(),
                beforeDst.plusDays(1).toInstant()).toHours();

        System.out.println("created: " + createdAt);
        System.out.println("local booking: " + localBooking);
        System.out.println("stored: " + apiUtc);
        System.out.println("API offset: " + apiOffset);
        System.out.println("same instant: " + storedInstant.equals(decoded));
        System.out.println("UI: " + display + " [" + BUSINESS_ZONE + "]");
        System.out.println("business date: " +
                storedInstant.atZone(BUSINESS_ZONE).toLocalDate());
        System.out.println("duration: " +
                Duration.between(storedInstant, endExclusive));
        System.out.println("start in interval: " +
                (!storedInstant.isBefore(storedInstant)
                        && storedInstant.isBefore(endExclusive)));
        System.out.println("end in interval: " +
                (!endExclusive.isBefore(storedInstant)
                        && endExclusive.isBefore(endExclusive)));
        System.out.println("gap offsets: " +
                NEW_YORK.getRules().getValidOffsets(gap).size());
        System.out.println("overlap offsets: " + overlapOffsets);
        System.out.println("chosen overlap instant: " + laterInstant);
        System.out.println("NY calendar day hours: " + hoursInCalendarDay);
        System.out.println("fixed-clock local date: " +
                LocalDate.now(fixed.withZone(BUSINESS_ZONE)));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TimeBoundaryDemo.java
java TimeBoundaryDemo
```

Kết quả chuẩn:

```text
created: 2026-01-15T02:03:04.123Z
local booking: 2026-01-20T09:30
stored: 2026-01-20T02:30:00Z
API offset: 2026-01-20T09:30:00+07:00
same instant: true
UI: 20/01/2026 09:30 [Asia/Ho_Chi_Minh]
business date: 2026-01-20
duration: PT30M
start in interval: true
end in interval: false
gap offsets: 0
overlap offsets: [-04:00, -05:00]
chosen overlap instant: 2024-11-03T06:30:00Z
NY calendar day hours: 23
fixed-clock local date: 2026-01-15
```

Mười lăm dòng kết quả minh họa: cùng instant dưới hai dạng UTC/offset; hiển thị giờ địa phương không sửa dữ liệu gốc; khoảng nửa mở; local time gap có 0 offset; overlap có 2 offset; chọn `-05:00` được instant cụ thể; và một ngày lịch ở New York có 23 giờ thực khi chuyển DST.

Demo sử dụng các quy tắc timezone hiện có cho mốc 2024/2026. Nếu một tổ chức phải tái dựng lịch sử pháp lý với phiên bản quy tắc khác, cần xác định chính sách lưu offset/phiên bản/snapshot trước khi chỉ dựa vào tzdb của môi trường hiện tại.

## 13. Phân chia trách nhiệm theo lớp

```text
Client chọn LocalDate + LocalTime + ZoneId
                  |
                  v
API parse và kiểm tra hợp đồng
                  |
                  v
Domain resolve DST gap/overlap với policy rõ
                  |
                  v
Instant đã xác định   +   ý định local/ZoneId
         |                       |
         v                       v
  DB: instant              DB: lịch địa phương
         |                       |
         +-----------+-----------+
                     v
       API response có ISO timestamp
                     |
                     v
       UI chọn zone + locale hiển thị
                     |
                     v
       dd/MM/uuuu HH:mm + nhãn vùng
```

Không bắt buộc mọi dịch vụ đều lưu hai nhánh: dịch vụ audit có thể chỉ cần instant; dịch vụ lịch định kỳ cần dữ liệu lịch địa phương và zone. **Điểm mấu chốt** là conversion phải xảy ra ở bước được định nghĩa rõ, không để ORM/frontend tự phỏng đoán từ cấu hình hệ điều hành.

## 14. Những lỗi thiết kế hay gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Lưu event bằng `LocalDateTime` thiếu offset | Các vùng hiểu thành mốc khác nhau | Dùng `Instant` |
| Gửi timestamp thiếu `Z` hoặc offset | Không xác định được instant | Hợp đồng ISO timestamp offset-aware |
| Lưu sinh nhật bằng 00:00 UTC | Người ở zone âm có thể thấy ngày trước | `LocalDate`/SQL `DATE` |
| Lưu offset hiện tại cho lịch hẹn tương lai | Sai ở vùng DST hoặc khi quy tắc đổi | Dùng `ZoneId` IANA |
| Gán `LocalDateTime` bất kỳ vào UTC | Tự diễn giải sai dữ liệu địa phương | Bắt buộc biết zone/offset đúng |
| Để `atZone` tự quyết định DST mà không kiểm tra | Lịch có thể đổi giờ hoặc chọn nhầm lượt 01:30 | Kiểm tra `getValidOffsets` và policy |
| Dùng timezone máy chủ để format cho mọi khách | Hiển thị lệch khi triển khai ở khu vực khác | Zone người dùng/chi nhánh |
| Coi `timestamptz` giữ tên vùng ban đầu | Không còn ZoneId ban đầu | Lưu zone riêng nếu cần |
| Coi `timestamp without time zone` tự là UTC | Không có semantics UTC mặc định | Tách local với instant |
| Không kiểm tra precision khi round-trip DB | `Instant.equals` sai vì mất nano | Định nghĩa precision và test |
| Nhầm epoch seconds/millis | Mốc lệch hàng nghìn lần | Ghi rõ đơn vị trong field |
| Dùng `<= end` cho khoảng liên tiếp | Đếm trùng ranh giới | `[start,end)` |
| Cộng đúng 24 giờ để tìm ngày hôm sau theo địa phương | Sai khi DST khiến ngày 23/25 giờ | `LocalDate.plusDays` và zone |
| Format với `YYYY-MM-dd` | Week-year có thể lệch năm | `uuuu-MM-dd`/ISO |
| So timestamp raw string khác offset | Cùng instant có chuỗi khác nhau | Parse và so `Instant` |
| Giữ một `Instant` cho lịch lặp hằng tuần | Lịch có thể trượt giờ sau DST | Local time + zone + recurrence |
| Test phụ thuộc `Instant.now()`/OS zone | Flaky, khó tái hiện | `Clock.fixed` và zone tường minh |
| Thay đổi dữ liệu nguồn giữa các lần convert | Không nhất quán | Chốt dữ liệu/timezone policy trong request |
| Mặc định driver JDBC nào cũng map time giống nhau | Sai precision/offset/timezone session | Integration test theo DB/driver |
| Format giờ sự kiện mà không cho biết vùng | Khách khác quốc gia hiểu sai | Hiển thị nhãn zone khi cần |

## 15. Bài tập ứng dụng

**Bài 1 — Sinh nhật.** Trường birthday là `1999-07-12`. Vì sao không nên lưu `1999-07-12T00:00:00Z`?

**Đáp án:** Sinh nhật là **ngày lịch**, không phải một instant toàn cầu. Đổi timezone của instant có thể ra ngày trước. Chọn `LocalDate` và SQL `DATE`.

**Bài 2 — API có offset.** `2026-01-20T02:30:00Z` và `2026-01-20T09:30:00+07:00` có cùng instant không?

**Đáp án:** Có. Dùng `OffsetDateTime.parse(...).toInstant()` để so. Không so raw string.

**Bài 3 — Lịch hằng tuần.** Một lớp học ở New York bắt đầu 09:00 thứ Hai. Có nên cộng 7×24 giờ cho mỗi lần?

**Đáp án:** Không nếu yêu cầu luôn giữ 09:00 địa phương. Lưu `LocalTime`, `ZoneId`, quy tắc lặp theo lịch và resolve từng occurrence.

**Bài 4 — Gap.** Người dùng chọn `2024-03-10T02:30` ở `America/New_York`. Có valid offset không?

**Đáp án:** Không. `getValidOffsets` là danh sách rỗng. Từ chối hoặc áp dụng chính sách dịch giờ được công bố.

**Bài 5 — Overlap.** `2024-11-03T01:30` tại New York có bao nhiêu instant hợp lệ?

**Đáp án:** Hai, tương ứng `-04:00` và `-05:00`. Phải xác định offset hoặc policy trước khi chốt instant.

**Bài 6 — Truy vấn theo ngày.** Lấy mọi event trong ngày 20/01 theo giờ Việt Nam bằng gì?

**Đáp án:** Hai `Instant` từ `day.atStartOfDay(zone)` và `day.plusDays(1).atStartOfDay(zone)`; query `>= start AND < end`.

**Bài 7 — Thời hạn.** "48 giờ" có dùng `Period.ofDays(2)` được không?

**Đáp án:** Với SLA đúng giờ thực, ưu tiên `Duration.ofHours(48)`. `Period` là đơn vị lịch và có thể khác 48 giờ qua DST.

**Bài 8 — Database.** Đọc lại `Instant` mất ba chữ số nano so với dữ liệu gửi. Hệ thống chắc chắn có bug?

**Đáp án:** Chưa chắc. Xem độ phân giải cột, driver và quy tắc rounding/truncation; chuẩn hóa precision theo contract.

**Bài 9 — Hiển thị.** Cùng event được xem từ Tokyo và Việt Nam, có cần lưu hai timestamp không?

**Đáp án:** Không nếu là một event duy nhất. Lưu `Instant`, chuyển sang zone thích hợp lúc format.

## 16. Checklist trước khi phát hành

- [ ] Mỗi field biết rõ là `Instant`, `LocalDate`, `LocalTime` hay local schedule + `ZoneId`.
- [ ] Timestamp tuyệt đối của API có `Z` hoặc numeric offset và precision thống nhất.
- [ ] Lịch địa phương có IANA zone khi cần resolve hoặc lặp lại.
- [ ] DST gap/overlap có chính sách xử lý minh bạch.
- [ ] Database schema không trộn ngày lịch với mốc tức thời.
- [ ] Nếu dùng PostgreSQL `timestamptz`, đã biết tên ZoneId đầu vào không được lưu trong cột đó.
- [ ] JDBC/ORM đã có round-trip test với các timezone session và precision khác nhau.
- [ ] Đơn vị epoch seconds/millis/micros được đặt tên rõ.
- [ ] Truy vấn theo ngày địa phương sử dụng khoảng nửa mở tạo theo zone.
- [ ] UI format theo locale và zone phù hợp, tránh lệ thuộc server timezone.
- [ ] Đã kiểm tra pattern `uuuu` và không dùng nhầm week-based-year `YYYY`.
- [ ] Tính khoảng thực bằng `Duration`, ngày/tháng lịch bằng `Period` hoặc calendar methods.
- [ ] Test dùng `Clock.fixed` cùng các ca ranh giới và DST.
- [ ] Lịch lặp bảo toàn ý định giờ địa phương, không chỉ lặp theo số giây.
- [ ] Chính sách tzdb update, audit và sửa lịch đã được xác định.

**Ghi nhớ:** thời gian ở API phải có **ngữ nghĩa rõ**, dữ liệu lưu phải bảo toàn **instant hoặc ý định local** tương ứng, và hiển thị phải dựa trên **zone + locale** xác định. Đây là thiết kế hiện hành từ Java 8 đến các JDK mới.

### Tài liệu API/chính thức còn áp dụng

- [`java.time` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html): mô hình ngày giờ và các kiểu.
- [`Instant` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): thời điểm tuyệt đối.
- [`LocalDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html): local date-time không zone.
- [`ZonedDateTime` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): DST gap/overlap và zone rules.
- [`ZoneRules` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets` và chuyển đổi.
- [`DateTimeFormatter` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): parse, format, locale.
- [`Clock` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): test thời gian xác định.
- [PostgreSQL 18 — Date/Time Types](https://www.postgresql.org/docs/18/datatype-datetime.html): ngữ nghĩa timestamptz, time zones và precision.