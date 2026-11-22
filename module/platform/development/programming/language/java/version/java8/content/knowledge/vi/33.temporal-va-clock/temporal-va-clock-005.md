# TemporalQuery, TemporalQueries và truy vấn riêng trong Java

> **Module:** Java 8 — Temporal và Clock. Chủ đề chính: cách **hỏi một đối tượng thời gian để lấy thông tin** bằng `TemporalAccessor.query(TemporalQuery<R>)`, các bộ truy vấn có sẵn `TemporalQueries` và cách tự xây `TemporalQuery` theo quy tắc nghiệp vụ. Toàn bộ API cốt lõi của bài có từ Java 8 và vẫn được dùng trong JDK hiện đại.

## 1. TemporalQuery giải quyết bài toán gì?

Trong `java.time`, mỗi loại dữ liệu thời gian chứa thông tin khác nhau:

- `LocalDate` biết **năm, tháng, ngày**, nhưng không biết giờ hoặc múi giờ.
- `LocalTime` biết **giờ, phút, giây**, nhưng không có ngày.
- `LocalDateTime` có ngày và giờ địa phương, nhưng **không có offset/zone**.
- `OffsetDateTime` có ngày/giờ với một **UTC offset** như `+07:00`.
- `ZonedDateTime` có ngày/giờ gắn `ZoneId` với quy tắc múi giờ vùng.
- `Instant` có vị trí trên timeline, nhưng bản thân nó không chứa một **ngày địa phương** hoặc **múi giờ**.

Vậy khi viết một hàm nhận một giá trị thời gian tổng quát, làm sao để hỏi:

- Giá trị này có ngày địa phương không?
- Có giờ địa phương không?
- Có `ZoneId` thực sự hay chỉ có `ZoneOffset`?
- Lịch của giá trị này là lịch nào?
- Đơn vị nhỏ nhất mà loại dữ liệu hỗ trợ là gì?
- Theo quy tắc của ứng dụng, đây có phải là ngày cuối tuần không?
- Ngày thứ Hai tiếp theo là ngày nào?

Đó là vai trò của **`TemporalQuery<R>`**: đóng gói logic **truy xuất hoặc suy ra một thông tin** từ một `TemporalAccessor`, rồi trả kết quả kiểu `R`.

Ví dụ đầu tiên:

~~~java
LocalDateTime value = LocalDateTime.of(2025, 7, 5, 9, 30);

LocalDate date = value.query(TemporalQueries.localDate());
LocalTime time = value.query(TemporalQueries.localTime());

System.out.println(date); // 2025-07-05
System.out.println(time); // 09:30
~~~

Đây là **đoạn minh họa**, cần import `java.time.LocalDate`, `java.time.LocalDateTime`, `java.time.LocalTime` và `java.time.temporal.TemporalQueries`.

Một query có thể trả **một object phức tạp, enum, chuỗi, boolean hoặc dữ liệu nghiệp vụ**, chứ không giới hạn ở số nguyên như một `TemporalField`. Nó là **Strategy Pattern** cho việc hỏi thông tin, giúp tái sử dụng cùng một quy tắc trên nhiều kiểu temporal khác nhau **nếu kiểu đó cung cấp dữ liệu cần thiết**.

## 2. Cây khái niệm: TemporalAccessor, Temporal, TemporalQuery và TemporalAdjuster

### 2.1. TemporalAccessor: giao diện đọc các trường thời gian

`java.time.temporal.TemporalAccessor` biểu diễn một đối tượng có thể **đọc** một số trường thời gian. Các phương thức quan trọng:

~~~java
boolean isSupported(TemporalField field);
long getLong(TemporalField field);
int get(TemporalField field);
<R> R query(TemporalQuery<R> query);
~~~

`TemporalAccessor` **không hứa** mọi field đều được hỗ trợ. Chẳng hạn `LocalDate` có thể hỗ trợ `ChronoField.DAY_OF_MONTH`, nhưng không thể cung cấp `ChronoField.HOUR_OF_DAY`.

Đoạn minh họa:

~~~java
TemporalAccessor temporal = LocalDate.of(2025, 7, 5);

boolean hasDay = temporal.isSupported(ChronoField.DAY_OF_MONTH);
boolean hasHour = temporal.isSupported(ChronoField.HOUR_OF_DAY);

// hasDay == true, hasHour == false.
~~~

Nếu muốn lấy trường số học mà có thể không được hỗ trợ, hãy kiểm tra trước bằng `isSupported` hoặc định nghĩa hành vi lỗi theo hợp đồng ứng dụng. `getLong`/`get` có thể ném `UnsupportedTemporalTypeException` hay `DateTimeException` khi thiếu trường hoặc giá trị không hợp lệ.

### 2.2. Temporal: đọc và điều chỉnh được

`Temporal` mở rộng `TemporalAccessor`, bổ sung khả năng tạo giá trị đã điều chỉnh bằng các thao tác như `with`, `plus` và `minus`. Hầu hết các lớp ngày giờ chính là immutable: việc điều chỉnh trả **giá trị mới**, không sửa giá trị cũ.

**`TemporalQuery` không dùng để sửa temporal.** Nếu mục tiêu là tìm thông tin, dùng query. Nếu mục tiêu là điều chỉnh ngày giờ, tìm `TemporalAdjuster`, `TemporalAmount` hoặc các method cụ thể như `plusDays`.

### 2.3. TemporalField: truy cập giá trị số

Một `TemporalField` như `ChronoField.MONTH_OF_YEAR` mô tả một trường số trong đối tượng ngày giờ.

~~~java
LocalDate date = LocalDate.of(2025, 7, 5);
int month = date.get(ChronoField.MONTH_OF_YEAR);
// 7
~~~

`TemporalField` đặc biệt phù hợp khi cần trường số theo một bộ quy ước đã xác định. Nhưng nếu cần lấy `ZoneId`, `LocalDate`, một object domain hoặc câu trả lời phức tạp, `TemporalQuery<R>` là công cụ phù hợp hơn.

### 2.4. TemporalQuery<R>: giao diện hàm truy vấn

Trong Java 8, `TemporalQuery<R>` là functional interface chỉ có một phương thức trừu tượng:

~~~java
R queryFrom(TemporalAccessor temporal);
~~~

Kiểu `R` là kiểu **kết quả**, ví dụ:

~~~java
TemporalQuery<LocalDate> dateQuery = TemporalQueries.localDate();
TemporalQuery<ZoneId> zoneQuery = TemporalQueries.zone();
TemporalQuery<Boolean> flagQuery = t -> true;
TemporalQuery<String> labelQuery = t -> "example";
~~~

Đây là **các đoạn minh họa**, không phải một file Java độc lập. `flagQuery` và `labelQuery` chỉ biểu diễn tính tổng quát của kiểu `R`; truy vấn thật cần logic dựa trên `TemporalAccessor`.

Hai cách gọi hợp lệ:

~~~java
LocalDate result1 = TemporalQueries.localDate().queryFrom(temporal);
LocalDate result2 = temporal.query(TemporalQueries.localDate());
~~~

Đoạn này giả định `temporal` là một `TemporalAccessor` có ngày, và hai kết quả đều là ngày đó. **Ưu tiên dạng `temporal.query(query)`** vì dễ đọc và cho phép implementation của `TemporalAccessor` tham gia xử lý.

## 3. TemporalQueries: bảy factory chuẩn của JDK

Lớp `java.time.temporal.TemporalQueries` cung cấp các static factory trả về `TemporalQuery`:

| Factory | Kết quả `R` | Ý nghĩa |
| --- | --- | --- |
| `TemporalQueries.zoneId()` | `ZoneId` | Truy vấn **strict** region/zone được lưu trong temporal; **không** tự xem offset đơn thuần là zone |
| `TemporalQueries.zone()` | `ZoneId` | Truy vấn **lenient**: ưu tiên zone ID, nếu không có thì dùng offset |
| `TemporalQueries.offset()` | `ZoneOffset` | Lấy UTC offset nếu temporal cung cấp |
| `TemporalQueries.chronology()` | `Chronology` | Lấy hệ lịch, chẳng hạn ISO |
| `TemporalQueries.localDate()` | `LocalDate` | Lấy phần ngày theo ISO nếu có dữ liệu ngày đầy đủ |
| `TemporalQueries.localTime()` | `LocalTime` | Lấy phần giờ nếu có dữ liệu giờ đầy đủ |
| `TemporalQueries.precision()` | `TemporalUnit` | Lấy **đơn vị nhỏ nhất loại temporal hỗ trợ** |

Mỗi method này trả một **đối tượng query**, không phải kết quả được hỏi ngay. Ví dụ:

~~~java
TemporalQuery<ZoneId> q = TemporalQueries.zone();
ZoneId result = someTemporal.query(q);
~~~

Đây là **đoạn minh họa** với `someTemporal` là `TemporalAccessor`. Đối tượng query có thể được truyền qua method, gán field hoặc tái sử dụng.

### 3.1. Tại sao có cả zoneId và zone?

Bởi vì **vùng** như `Europe/Paris` khác một **offset cố định** như `+01:00`. Một `OffsetDateTime` chỉ giữ offset; một `ZonedDateTime` giữ ZoneId. Khi viết một hàm dùng chung cho hai kiểu, ứng dụng phải quyết định:

- Chỉ chấp nhận zone ID thực sự? Dùng `zoneId()`.
- Chấp nhận một `ZoneOffset` nếu không có zone ID? Dùng `zone()`.
- Chỉ cần số giây lệch UTC? Dùng `offset()`.

**Không đồng nhất offset với quy tắc múi giờ vùng có DST.** Với lịch tương lai, một offset cố định không đủ để suy ra quy tắc chuyển giờ của vùng theo thời gian.

### 3.2. Kết quả được phép là null

Nhiều query chuẩn cố ý trả `null` nếu dữ liệu không có:

~~~java
LocalDate date = LocalTime.NOON.query(
        TemporalQueries.localDate());
// null

ZoneId zone = LocalDateTime.now().query(
        TemporalQueries.zone());
// null
~~~

Đây là **đoạn minh họa**; kết quả `zone == null` không phụ thuộc thời gian thực, vì `LocalDateTime` không có thông tin zone. Tuy nhiên, tránh dùng `now()` trong bài test cần expected value cố định; các phần runnable sau dùng giá trị tạo sẵn.

**Null có nghĩa "không truy xuất được theo hợp đồng query", không nhất thiết giá trị đầu vào bị null.** Một `TemporalAccessor` hợp lệ có thể thiếu một thành phần mà caller đang hỏi.

## 4. ZoneId strict, zone lenient và offset: so sánh bằng ví dụ

Xét ba object có cùng mặt đồng hồ `09:30` nhưng khác thông tin múi giờ:

~~~java
LocalDateTime local =
        LocalDateTime.of(2025, 7, 5, 9, 30);

OffsetDateTime offset = OffsetDateTime.of(
        2025, 7, 5, 9, 30, 0, 0,
        ZoneOffset.ofHours(7));

ZonedDateTime zoned = ZonedDateTime.of(
        2025, 7, 5, 9, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là **đoạn minh họa**. Sau khi có ba biến trên:

| Query | `local` | `offset` | `zoned` |
| --- | --- | --- | --- |
| `zoneId()` | `null` | `null` | `Asia/Ho_Chi_Minh` |
| `zone()` | `null` | `+07:00` | `Asia/Ho_Chi_Minh` |
| `offset()` | `null` | `+07:00` | `+07:00` |

### 4.1. zoneId() strict không lấy offset từ OffsetDateTime

~~~java
ZoneId strict = offset.query(TemporalQueries.zoneId());
ZoneId lenient = offset.query(TemporalQueries.zone());

// strict == null
// lenient.equals(ZoneOffset.ofHours(7)) == true
~~~

Lý do: `OffsetDateTime` biểu diễn một offset, không lưu một region zone. `zone()` được thiết kế có thể **fallback** sang offset. Tên kiểu trả về `ZoneId` không nói giá trị cụ thể luôn là vùng có bộ quy tắc riêng; `ZoneOffset` cũng là một kiểu `ZoneId`.

### 4.2. ZonedDateTime có cả zone và offset hiện hành

~~~java
ZoneId region = zoned.query(TemporalQueries.zoneId());
ZoneOffset currentOffset = zoned.query(TemporalQueries.offset());
~~~

Khi biết vùng và ngày giờ cụ thể, đối tượng có thể cung cấp offset đang áp dụng. Với ví dụ `Asia/Ho_Chi_Minh` ngày 05/07/2025, offset là `+07:00`.

Một `ZoneId` như `Asia/Ho_Chi_Minh` vẫn khác string `+07:00` về ý nghĩa: bộ quy tắc múi giờ vùng có thể thay đổi theo lịch sử hoặc cập nhật cơ sở dữ liệu timezone. Đừng xây logic lịch dài hạn chỉ trên một offset lấy ra ở **một thời điểm**.

### 4.3. Instant không tự có ZoneId

~~~java
Instant instant = Instant.parse("2025-07-05T02:30:00Z");

ZoneId zone = instant.query(TemporalQueries.zone());
// null
~~~

`Instant` biết một mốc UTC, **không mang vùng hiển thị địa phương**. Nếu cần hỏi ngày ở Việt Nam:

~~~java
LocalDate dateInVietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .query(TemporalQueries.localDate());
// 2025-07-05
~~~

Đây là đoạn minh họa. **Phải chọn zone trước**; việc query một ngày local trực tiếp từ `Instant` không tự suy ra múi giờ.

## 5. localDate() và localTime(): trích xuất mềm khi có đủ trường

### 5.1. localDate()

`TemporalQueries.localDate()` tìm thông tin ngày tương ứng với `ChronoField.EPOCH_DAY` và dựng một `LocalDate` nếu temporal cung cấp trường thích hợp.

~~~java
LocalDateTime dateTime =
        LocalDateTime.of(2025, 7, 5, 9, 30);

LocalDate date = dateTime.query(TemporalQueries.localDate());
// 2025-07-05
~~~

`YearMonth.of(2025,7)` không có ngày cụ thể, nên query `localDate()` không thể tự bịa một ngày đầu/tháng cuối mặc định. Nếu muốn **ngày cuối của tháng**, đó là **quy tắc nghiệp vụ cần viết rõ**, không phải chức năng của `localDate()`.

~~~java
YearMonth ym = YearMonth.of(2025, 7);

LocalDate missing = ym.query(TemporalQueries.localDate());
// null

LocalDate lastDay = ym.atEndOfMonth();
// 2025-07-31
~~~

Đây là **đoạn minh họa**, dùng `java.time.YearMonth`. Gọi `atEndOfMonth` là quyết định ứng dụng, không phải do query mặc định.

### 5.2. localTime()

`TemporalQueries.localTime()` dựa trên dữ liệu `ChronoField.NANO_OF_DAY` khi có đủ giờ trong ngày:

~~~java
OffsetDateTime timestamp =
        OffsetDateTime.parse("2025-07-05T09:30:00+07:00");

LocalTime time = timestamp.query(TemporalQueries.localTime());
// 09:30
~~~

Cần phân biệt: `09:30` ở đây là **giờ local gắn với offset đã có**, không nhất thiết là giờ UTC. Nếu muốn thời gian hiển thị ở một vùng khác, chuyển `OffsetDateTime` theo **cùng instant** sang zone mong muốn trước khi lấy localTime.

### 5.3. Query chuẩn và conversion bằng from khác nhau ở failure mode

Một số method reference như `LocalDate::from` và `LocalTime::from` cũng là `TemporalQuery` phù hợp:

~~~java
LocalDate dateA = dateTime.query(TemporalQueries.localDate());
LocalDate dateB = dateTime.query(LocalDate::from);
~~~

Khi temporal chứa đủ ngày, kết quả tương đương.

Nhưng nếu không có ngày:

~~~java
LocalDate soft =
        LocalTime.NOON.query(TemporalQueries.localDate());
// soft == null

// Lời gọi sau ném DateTimeException:
// LocalTime.NOON.query(LocalDate::from);
~~~

Chọn theo hợp đồng:

- **Có thể không có dữ liệu**, muốn biểu diễn missing bằng `null` hoặc `Optional`: dùng query mềm thích hợp.
- **Bắt buộc có dữ liệu ngày**, muốn dữ liệu thiếu là lỗi: dùng `LocalDate::from` hoặc kiểm tra và ném exception rõ ràng.

Không coi mọi lỗi `DateTimeException` là bằng chứng người dùng nhập ngày sai; có thể đơn giản caller yêu cầu một thành phần **không tồn tại** trong loại temporal.

## 6. chronology() và precision(): nghĩa thật của hai truy vấn

### 6.1. chronology() — hệ lịch của giá trị

`TemporalQueries.chronology()` trả `Chronology` nếu đối tượng có khái niệm hệ lịch. Các ví dụ:

~~~java
Chronology iso = LocalDate.of(2025, 7, 5)
        .query(TemporalQueries.chronology());

Chronology none = LocalTime.NOON
        .query(TemporalQueries.chronology());

// iso == IsoChronology.INSTANCE
// none == null
~~~

Đây là **đoạn minh họa**, cần import `java.time.chrono.Chronology` và `java.time.chrono.IsoChronology`.

Không phải tất cả `TemporalAccessor` đều thuộc lịch ISO. `ChronoLocalDate` hoặc các lớp thuộc chronology khác có thể có ngày theo hệ lịch khác. Nếu custom query dựa vào `LocalDate` theo ISO, cần **tài liệu hóa phạm vi hỗ trợ** hoặc chuyển đổi rõ ràng theo epoch day.

### 6.2. precision() — đơn vị nhỏ nhất loại dữ liệu hỗ trợ

~~~java
TemporalUnit datePrecision = LocalDate.of(2025, 7, 5)
        .query(TemporalQueries.precision());

TemporalUnit timePrecision = LocalTime.NOON
        .query(TemporalQueries.precision());

// datePrecision == ChronoUnit.DAYS
// timePrecision == ChronoUnit.NANOS
~~~

Đây là **đoạn minh họa**, cần import `TemporalUnit` và `ChronoUnit`.

Một số kết quả chuẩn:

| Kiểu | `TemporalQueries.precision()` |
| --- | --- |
| `LocalDate` | `ChronoUnit.DAYS` |
| `LocalTime` | `ChronoUnit.NANOS` |
| `LocalDateTime` | `ChronoUnit.NANOS` |
| `OffsetDateTime` | `ChronoUnit.NANOS` |
| `ZonedDateTime` | `ChronoUnit.NANOS` |
| `Instant` | `ChronoUnit.NANOS` |
| `YearMonth` | `ChronoUnit.MONTHS` |

**Cảnh báo quan trọng:** `precision()==NANOS` có nghĩa là **kiểu dữ liệu hỗ trợ độ phân giải nano giây**, không chứng minh đồng hồ hệ thống thực tế đo được với độ đúng 1 ns. Nó cũng không chứng minh JSON serializer/JDBC/SQL column của ứng dụng đang giữ đủ chín chữ số phần giây.

### 6.3. chronology null không nhất thiết là lỗi

`LocalTime` không có ngày/lịch, nên `chronology()` là `null`; `Instant` là mốc timeline, cũng không mang chronology địa phương. Hãy mô hình hóa đúng khái niệm trước khi suy luận “temporal này không hợp lệ”.

### 6.4. Custom query có thể kiểm tra chronology

Nếu một nghiệp vụ áp dụng **chỉ** cho lịch ISO, có thể yêu cầu `temporal.query(TemporalQueries.chronology())` tương ứng `IsoChronology.INSTANCE` hoặc chuyển sang `LocalDate` theo quy tắc được phép. Không âm thầm áp `ChronoField.YEAR` trên các hệ lịch mà không hiểu chronology, vì con số năm có thể mang ý nghĩa khác.

## 7. Viết TemporalQuery riêng bằng lambda

### 7.1. Ví dụ: phân loại cuối tuần

Một query có thể trả `String` mô tả ngày là cuối tuần/ngày làm việc. Dùng `TemporalQueries.localDate()` để trích xuất ngày khi có, rồi xử lý:

~~~java
TemporalQuery<String> dayKind = temporal -> {
    LocalDate date = temporal.query(TemporalQueries.localDate());
    if (date == null) {
        return "NO_DATE";
    }
    int dayOfWeek = date.getDayOfWeek().getValue();
    return dayOfWeek >= 6 ? "WEEKEND" : "WEEKDAY";
};
~~~

Đây là **đoạn minh họa**, cần `TemporalQuery`, `TemporalQueries` và `LocalDate`.

~~~java
String weekend = LocalDate.of(2025, 7, 5).query(dayKind);
// WEEKEND

String unknown = LocalTime.NOON.query(dayKind);
// NO_DATE
~~~

Ở đây thứ Bảy/Chủ nhật theo ISO được xem là weekend. **Đó là một quy tắc minh họa**, không phải định nghĩa ngày làm việc của tất cả quốc gia, công ty hoặc lịch nghỉ lễ. Ứng dụng thực có thể cần Holiday Calendar hoặc cấu hình workweek.

### 7.2. Vì sao chọn query trả String thay vì Boolean?

Một kiểu `Boolean` đơn giản có thể dùng nếu chỉ cần true/false và không có dữ liệu được coi là false. Nhưng một `TemporalAccessor` không có ngày **không nhất thiết tương đương “không phải cuối tuần”**.

Có thể chọn ba trạng thái:

- `"WEEKEND"`.
- `"WEEKDAY"`.
- `"NO_DATE"`.

Đây là một chính sách dễ biểu diễn bằng `String`, tuy trong hệ thống lớn **enum** hoặc result type chuyên biệt có thể an toàn kiểu hơn. Bài học là kiểu `R` của `TemporalQuery<R>` được quyết định bởi kết quả cần truyền đạt.

### 7.3. Đưa query vào field static final

Khi query không có state thay đổi, có thể dùng lại:

~~~java
private static final TemporalQuery<String> DAY_KIND = temporal -> {
    LocalDate date = temporal.query(TemporalQueries.localDate());
    if (date == null) return "NO_DATE";
    return date.getDayOfWeek().getValue() >= 6
            ? "WEEKEND" : "WEEKDAY";
};
~~~

Đây là **khai báo minh họa bên trong class**, không phải source file độc lập. Java 8 hỗ trợ lambda và interface này nên không cần một class chỉ để triển khai một phương thức đơn giản.

### 7.4. Query tùy biến có thể trả đối tượng khác String

Ví dụ xác định ngày thứ Hai **sau** ngày được hỏi:

~~~java
TemporalQuery<LocalDate> nextMonday = temporal -> {
    LocalDate date = temporal.query(TemporalQueries.localDate());
    if (date == null) {
        return null;
    }
    return date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
};
~~~

Đoạn minh họa, cần `TemporalAdjusters` và `DayOfWeek`. Nó trả một `LocalDate`:

~~~java
LocalDate saturday = LocalDate.of(2025, 7, 5);
LocalDate next = saturday.query(nextMonday);
// 2025-07-07
~~~

**`TemporalAdjusters.next(MONDAY)` luôn là thứ Hai tiếp theo**, nên nếu ngày đầu đã là thứ Hai, kết quả là **thứ Hai tuần sau**. Nếu muốn thứ Hai hiện tại hoặc tiếp theo, chọn `TemporalAdjusters.nextOrSame(MONDAY)`. Đây là khác biệt ngữ nghĩa quan trọng trong lịch làm việc.

## 8. Truy vấn bằng class riêng thay vì lambda

Lambda phù hợp cho logic ngắn, thuần và dễ hiểu. Khi query có nhiều chính sách, cần tài liệu hóa hoặc tái sử dụng qua module, một class triển khai `TemporalQuery<R>` là lựa chọn rõ ràng.

~~~java
public final class WorkingDayQuery
        implements TemporalQuery<Boolean> {

    @Override
    public Boolean queryFrom(TemporalAccessor temporal) {
        LocalDate date =
                temporal.query(TemporalQueries.localDate());

        if (date == null) {
            return null;
        }

        int isoDay = date.getDayOfWeek().getValue();
        return isoDay >= 1 && isoDay <= 5;
    }
}
~~~

Đây là **lớp minh họa riêng** (cần import `java.time.LocalDate`, `java.time.temporal.TemporalAccessor`, `TemporalQuery`, `TemporalQueries`). Nó minh họa policy Monday–Friday, chưa bao gồm ngày lễ. Kiểu trả về `Boolean` wrapper cho phép `null` nếu thiếu ngày.

Nếu không muốn có `null` trong domain, định nghĩa enum hoặc dùng `Optional<Boolean>`; không dùng `boolean` primitive nếu business cần trạng thái “không xác định”.

### 8.1. Hợp đồng queryFrom

Một implementation nên:

1. **Không sửa** `TemporalAccessor` đầu vào.
2. Thực hiện logic **read-only**.
3. Hoạt động **thread-safe** nếu cùng query được dùng bởi nhiều thread; ưu tiên immutable/stateless.
4. Nói rõ kết quả có thể `null` hay không.
5. Nói rõ hỗ trợ kiểu temporal nào và khi nào ném `DateTimeException`.
6. Không giả định mọi temporal đều chứa ISO date, local time hoặc zone.

Nếu logic của query cần truy cập I/O, trạng thái mutable hoặc hệ thống bên ngoài, hãy cân nhắc tách phần dịch vụ khỏi `TemporalQuery`. Query thường có giá trị nhất khi nhỏ, ổn định, dễ kiểm thử và có thể tái sử dụng.

### 8.2. Không tái gọi chính query từ queryFrom

Đây là **phản ví dụ** gây đệ quy:

~~~java
// SAI: cùng query gọi lại chính nó.
TemporalQuery<String> recursive = new TemporalQuery<String>() {
    @Override
    public String queryFrom(TemporalAccessor temporal) {
        return temporal.query(this);
    }
};
~~~

Từ `temporal.query(recursive)`, implementation sẽ quay về `recursive.queryFrom(temporal)`, không lấy được thông tin mới và có thể làm tràn stack. Truy vấn tùy biến nên gọi những **query thành phần khác** như `TemporalQueries.localDate()` hoặc đọc trường có thật, không tự gọi lại chính mình.

### 8.3. Không ghi đè TemporalAccessor.query sai hợp đồng

Một lớp temporal tùy biến có thể cần cung cấp thông tin riêng về `chronology`, `zoneId`, `precision`. `TemporalAccessor` có default implementation đặc biệt cho những query này; một implementation tùy biến cần xem kỹ Javadoc và thường gọi `TemporalAccessor.super.query(query)` cho những trường hợp còn lại.

Bài này **không yêu cầu tự viết TemporalAccessor** để học custom query. Khi chỉ cần quy tắc truy xuất mới, viết `TemporalQuery` là đủ và ít rủi ro hơn.

## 9. Trả null, Optional hay ném lỗi khi không đủ dữ liệu?

Không có một chính sách chung đúng cho mọi query, nhưng cần nhất quán theo hợp đồng.

### 9.1. Null là cách query chuẩn biểu thị thiếu dữ liệu

~~~java
LocalDate date = LocalTime.NOON.query(
        TemporalQueries.localDate());
// null
~~~

Một số query built-in chấp nhận missing và trả null; ở bước dùng tiếp theo, đừng gọi `date.getDayOfWeek()` mà không kiểm tra null.

### 9.2. Optional trong query riêng

Bạn có thể thiết kế query trả `Optional<LocalDate>` thay vì null:

~~~java
TemporalQuery<Optional<LocalDate>> optionalDate =
        temporal -> Optional.ofNullable(
                temporal.query(TemporalQueries.localDate()));
~~~

Đây là **đoạn minh họa**, cần `java.util.Optional`. Kết quả là một `Optional` có mặt hoặc rỗng, thuận tiện khi caller muốn dùng `map`/`orElse`.

Không bọc `Optional` nhiều tầng một cách không cần thiết. Ví dụ `Optional<Optional<LocalDate>>` thường là dấu hiệu API chưa rõ.

### 9.3. Trường bắt buộc: lỗi minh bạch

Nếu query nghiệp vụ chỉ hợp lệ trên các temporal chứa ngày, có thể ném `DateTimeException` khi không có ngày:

~~~java
TemporalQuery<LocalDate> requiredDate = temporal -> {
    LocalDate date = temporal.query(TemporalQueries.localDate());
    if (date == null) {
        throw new DateTimeException(
                "Temporal does not contain an ISO date");
    }
    return date;
};
~~~

Đây là **đoạn minh họa**, cần import `DateTimeException`. Policy này tránh âm thầm coi ngày không tồn tại là một ngày giả. Đừng biến `null` thành ngày hiện tại (`LocalDate.now()`) nếu nghiệp vụ không yêu cầu; điều đó có thể tạo dữ liệu thay đổi theo lúc chạy và timezone.

### 9.4. Quyết định cho caller

| Chính sách | Thiết kế | Khi nào phù hợp |
| --- | --- | --- |
| Missing trả null | `TemporalQuery<LocalDate>` | Query thấp tầng, caller có quy tắc null |
| Missing trả Optional.empty | `TemporalQuery<Optional<LocalDate>>` | Domain muốn biểu diễn "có hoặc không" tường minh |
| Missing ném lỗi | `TemporalQuery<LocalDate>` + `DateTimeException` | Bắt buộc temporal phải chứa ngày |
| Missing gán label | `TemporalQuery<String>` | Kết quả phân loại dùng trong báo cáo |
| Missing dùng ngày fallback | Query riêng có chính sách rõ | Chỉ khi yêu cầu nghiệp vụ quy định một fallback hợp lệ |

**Không ngầm coi `null` của query là null của `TemporalAccessor`:** chính object đầu vào thường vẫn tồn tại, nhưng thiếu một khả năng được hỏi.

## 10. Cách kết hợp TemporalQuery với DateTimeFormatter

`DateTimeFormatter` không chỉ dùng để chuyển text thành một temporal rồi tự tách field. Java 8 hỗ trợ:

~~~java
<T> T parse(CharSequence text, TemporalQuery<T> query);
~~~

Đây là **chữ ký khái niệm** của overload trên `DateTimeFormatter`. Ví dụ parse chuỗi ngày ISO và lấy `LocalDate` ngay:

~~~java
LocalDate date = DateTimeFormatter.ISO_LOCAL_DATE.parse(
        "2025-07-05",
        LocalDate::from);
// 2025-07-05
~~~

Dạng method reference `LocalDate::from` là query strict; chuỗi không chứa đủ thông tin ngày hoặc sai định dạng sẽ bị từ chối theo exception tương ứng.

### 10.1. Trả kết quả nghiệp vụ ngay trong parse

~~~java
TemporalQuery<String> weekendKind = temporal -> {
    LocalDate date = temporal.query(TemporalQueries.localDate());
    if (date == null) return "NO_DATE";
    return date.getDayOfWeek().getValue() >= 6
            ? "WEEKEND" : "WEEKDAY";
};

String kind = DateTimeFormatter.ISO_LOCAL_DATE.parse(
        "2025-07-05",
        weekendKind);
// WEEKEND
~~~

Đây là **đoạn minh họa**. Formatter parse chuỗi ra cấu trúc temporal, sau đó áp query; không cần tự cắt chuỗi lấy thứ từ ngày-tháng-năm.

### 10.2. Query không sửa nội dung text hoặc timezone

Query chỉ đọc kết quả parse. Nếu chuỗi đầu vào có offset mà cần đổi sang một vùng khác, việc chuyển đổi offset/zone là **một thao tác nghiệp vụ riêng**. Đừng kỳ vọng `TemporalQueries.localDate()` tự đổi ngày sang timezone máy đang chạy.

### 10.3. Parse một timestamp không offset không tạo ra Instant

~~~java
LocalDateTime local = LocalDateTime.parse(
        "2025-07-05T09:30:00");
~~~

Đây là **đoạn minh họa**. Giá trị local không đủ xác định một mốc UTC. Query `zone()` trả null vì dữ liệu đầu vào không cung cấp zone. Nếu cần Instant, phải kết hợp với zone/offset theo hợp đồng ứng dụng; không gắn `UTC` tùy tiện.

## 11. Phân biệt Query, Adjuster, Clock và TemporalAmount

Một API dễ dùng đúng khi tên phương thức phản ánh ý định:

| Công cụ | Nhận gì? | Trả gì? | Mục tiêu |
| --- | --- | --- | --- |
| `TemporalQuery<R>` | `TemporalAccessor` | `R` | Đọc, trích xuất, phân loại |
| `TemporalQueries` | Không tham số hoặc static factory | Query có sẵn | Zone/date/time/precision/chronology |
| `TemporalAdjuster` | `Temporal` | `Temporal` đã điều chỉnh | Đổi ngày/giờ theo quy tắc |
| `TemporalAdjusters` | Tham số quy tắc như thứ trong tuần | Adjuster | Ví dụ chuyển sang thứ Hai tiếp theo |
| `TemporalAmount` | Thời lượng như Period/Duration | Lượng để cộng/trừ | Lịch hoặc elapsed time |
| `Clock` | Clock instance | Instant và zone từ nguồn thời gian | Đọc "hiện tại" có thể kiểm thử |

### 11.1. Query có thể dùng Adjuster *bên trong* nhưng không phải Adjuster

Custom query `nextMonday` ở mục 7 dùng `date.with(TemporalAdjusters.next(...))` để **tính** một ngày kết quả. Nó vẫn trả `LocalDate` chứ không ghi đè ngày ban đầu.

Nếu mục tiêu của caller là điều chỉnh một `LocalDate` đã biết, cú pháp trực tiếp thường rõ hơn:

~~~java
LocalDate date = LocalDate.of(2025, 7, 5);
LocalDate nextMonday =
        date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
~~~

Nếu mục tiêu là **truy vấn trên nhiều loại TemporalAccessor** có hoặc không có ngày, `TemporalQuery<LocalDate>` là lớp trừu tượng hữu ích.

### 11.2. Clock không phải TemporalAccessor

`Clock` là một nguồn để hỏi thời gian hiện tại và zone, nhưng **không phải** một đối tượng ngày giờ `TemporalAccessor` trên đó gọi `query(TemporalQueries...)`.

Cách đúng:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2025-07-05T02:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime local = LocalDateTime.now(fixed);
LocalDate date = local.query(TemporalQueries.localDate());
// 2025-07-05
~~~

Đây là đoạn minh họa. Với logic phụ thuộc hiện tại, inject `Clock` vào service để test dùng fixed clock và tránh phụ thuộc timezone mặc định của máy.

### 11.3. Precision query không phải độ đúng của Clock

`LocalDateTime.now(clock).query(TemporalQueries.precision())` có thể trả `ChronoUnit.NANOS` bởi **kiểu LocalDateTime** hỗ trợ nanosecond. Điều đó **không chứng minh** clock đã đo chính xác tới một nano giây, cũng không nói gì về độ chính xác DB/JSON của ứng dụng.

## 12. Chương trình hoàn chỉnh Java 8: built-in queries và custom queries

Lưu nội dung sau thành file **TemporalQueryDemo.java**. Mã đã được kiểm tra với `javac --release 8` và chạy trên JDK hiện hành. Chương trình chỉ dùng giá trị cố định, không phụ thuộc đồng hồ hệ thống hoặc locale, nên kết quả đầu ra có thể kiểm chứng.

~~~java
import java.time.*;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.temporal.*;

public class TemporalQueryDemo {
    private static final TemporalQuery<String> DAY_KIND = temporal -> {
        LocalDate date = temporal.query(TemporalQueries.localDate());
        if (date == null) {
            return "NO_DATE";
        }
        return date.getDayOfWeek().getValue() >= 6 ? "WEEKEND" : "WEEKDAY";
    };

    private static final TemporalQuery<String> TIME_PART = temporal -> {
        LocalTime time = temporal.query(TemporalQueries.localTime());
        if (time == null) {
            return "NO_TIME";
        }
        return time.getHour() < 12 ? "MORNING" : "AFTERNOON";
    };

    private static final TemporalQuery<LocalDate> NEXT_MONDAY = temporal -> {
        LocalDate date = temporal.query(TemporalQueries.localDate());
        return date == null ? null
                : date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
    };

    public static void main(String[] args) {
        LocalDate saturday = LocalDate.of(2025, 7, 5);
        LocalDate monday = LocalDate.of(2025, 7, 7);
        LocalTime clockTime = LocalTime.of(15, 45);
        LocalDateTime local = LocalDateTime.of(2025, 7, 5, 9, 30);
        OffsetDateTime offset = OffsetDateTime.of(
                2025, 7, 5, 9, 30, 0, 0, ZoneOffset.ofHours(7));
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = ZonedDateTime.of(
                2025, 7, 5, 9, 30, 0, 0, hcm);
        Instant instant = Instant.parse("2025-07-05T02:30:00Z");

        System.out.println("local date = "
                + local.query(TemporalQueries.localDate()));
        System.out.println("local time = "
                + local.query(TemporalQueries.localTime()));
        System.out.println("local zone = "
                + local.query(TemporalQueries.zone()));
        System.out.println("OffsetDateTime zoneId = "
                + offset.query(TemporalQueries.zoneId()));
        System.out.println("OffsetDateTime zone = "
                + offset.query(TemporalQueries.zone()));
        System.out.println("OffsetDateTime offset = "
                + offset.query(TemporalQueries.offset()));
        System.out.println("ZonedDateTime zoneId = "
                + zoned.query(TemporalQueries.zoneId()));
        System.out.println("ZonedDateTime offset = "
                + zoned.query(TemporalQueries.offset()));
        System.out.println("LocalDate precision DAYS = "
                + (saturday.query(TemporalQueries.precision())
                        == ChronoUnit.DAYS));
        System.out.println("LocalDateTime precision NANOS = "
                + (local.query(TemporalQueries.precision())
                        == ChronoUnit.NANOS));
        System.out.println("LocalDate ISO chronology = "
                + (saturday.query(TemporalQueries.chronology())
                        == IsoChronology.INSTANCE));
        System.out.println("LocalTime chronology = "
                + clockTime.query(TemporalQueries.chronology()));
        System.out.println("Instant local date = "
                + instant.query(TemporalQueries.localDate()));
        System.out.println("Instant date in HCM = "
                + instant.atZone(hcm).query(TemporalQueries.localDate()));
        System.out.println("Saturday kind = " + saturday.query(DAY_KIND));
        System.out.println("Monday kind = " + monday.query(DAY_KIND));
        System.out.println("LocalTime kind = " + clockTime.query(DAY_KIND));
        System.out.println("Local date-time part = " + local.query(TIME_PART));
        System.out.println("LocalDate time part = "
                + saturday.query(TIME_PART));
        System.out.println("Next Monday after Saturday = "
                + saturday.query(NEXT_MONDAY));
        System.out.println("Next Monday after Monday = "
                + monday.query(NEXT_MONDAY));
        System.out.println("Parsed Saturday kind = "
                + DateTimeFormatter.ISO_LOCAL_DATE.parse(
                        "2025-07-05", DAY_KIND));
        System.out.println("Direct queryFrom same result = "
                + DAY_KIND.queryFrom(saturday).equals(
                        saturday.query(DAY_KIND)));
        try {
            clockTime.query(LocalDate::from);
            System.out.println("Strict date conversion = success");
        } catch (DateTimeException ex) {
            System.out.println("Strict date conversion = DateTimeException");
        }
        System.out.println("Original Saturday = " + saturday);
    }
}
~~~

Biên dịch bằng JDK có hỗ trợ tùy chọn `--release 8` và chạy:

~~~bash
javac --release 8 TemporalQueryDemo.java
java TemporalQueryDemo
~~~

**Stdout đã được kiểm chứng:**

~~~text
local date = 2025-07-05
local time = 09:30
local zone = null
OffsetDateTime zoneId = null
OffsetDateTime zone = +07:00
OffsetDateTime offset = +07:00
ZonedDateTime zoneId = Asia/Ho_Chi_Minh
ZonedDateTime offset = +07:00
LocalDate precision DAYS = true
LocalDateTime precision NANOS = true
LocalDate ISO chronology = true
LocalTime chronology = null
Instant local date = null
Instant date in HCM = 2025-07-05
Saturday kind = WEEKEND
Monday kind = WEEKDAY
LocalTime kind = NO_DATE
Local date-time part = MORNING
LocalDate time part = NO_TIME
Next Monday after Saturday = 2025-07-07
Next Monday after Monday = 2025-07-14
Parsed Saturday kind = WEEKEND
Direct queryFrom same result = true
Strict date conversion = DateTimeException
Original Saturday = 2025-07-05
~~~

### 12.1. Đối chiếu kết quả: ngày/giờ và zone

1. `LocalDateTime` có ngày `2025-07-05` và giờ `09:30`, nhưng zone null.
2. `OffsetDateTime` có offset `+07:00`, vì thế `zone()` và `offset()` trả offset, còn strict `zoneId()` trả null.
3. `ZonedDateTime` có region `Asia/Ho_Chi_Minh` và offset đang áp dụng `+07:00`. Đây là hai loại thông tin khác nhau.

### 12.2. Đối chiếu kết quả: chronology/precision

4. `LocalDate` hỗ trợ độ phân giải tới `DAYS`; `LocalDateTime` hỗ trợ tới `NANOS`. Hai biểu thức kiểm tra enum identity trả true.
5. `LocalDate` thuộc `IsoChronology`; `LocalTime` không có lịch nên `chronology()` trả null.
6. `Instant` không chứa ngày local: query trực tiếp trả null. Sau khi gắn `ZoneId`, ngày local trở thành `2025-07-05`.

### 12.3. Đối chiếu kết quả: custom queries

7. Ngày 05/07/2025 là thứ Bảy nên `DAY_KIND` trả `WEEKEND`; ngày 07/07/2025 là thứ Hai nên trả `WEEKDAY`.
8. `LocalTime` không có ngày, nên `DAY_KIND` trả `NO_DATE`, không giả định nó thuộc một ngày làm việc bất kỳ.
9. `LocalDateTime` lúc 09:30 được phân loại `MORNING`; `LocalDate` thiếu giờ nên `TIME_PART` trả `NO_TIME`.
10. `TemporalAdjusters.next(MONDAY)` cho thứ Hai kế tiếp: sau thứ Bảy 05/07 là 07/07, nhưng sau một thứ Hai 07/07 là 14/07.
11. `DateTimeFormatter.parse(text, DAY_KIND)` áp dụng chính query trên dữ liệu vừa parse, cho `WEEKEND`.
12. Truy vấn bằng `DAY_KIND.queryFrom(saturday)` và `saturday.query(DAY_KIND)` đều tạo cùng nhãn.
13. `LocalDate::from` yêu cầu đủ thông tin ngày; gọi trên `LocalTime` ném `DateTimeException` nên chương trình bắt và in tên lỗi.
14. Bản gốc `saturday` không đổi sau các truy vấn — query chỉ trích xuất/tính kết quả.

## 13. Lỗi phổ biến khi dùng TemporalQuery

### Lỗi 1 — Nhầm query với việc sửa đối tượng

`temporal.query(...)` trả thông tin; không thay đổi ngày giờ. Nếu cần chuyển sang ngày thứ Hai hoặc cộng ngày, dùng adjuster/`plusDays`/`with` theo ý định.

### Lỗi 2 — Giả định mọi TemporalAccessor đều chứa ngày

`LocalTime` và `Instant` có thể không cung cấp ngày local; `TemporalQueries.localDate()` có thể trả null. Muốn ngày của Instant, chọn zone trước rồi trích xuất.

### Lỗi 3 — Nhầm zoneId() với zone()

`zoneId()` strict, không tự fallback offset. Với `OffsetDateTime` có `+07:00`: strict trả null, lenient `zone()` trả `+07:00`.

### Lỗi 4 — Nghĩ ZoneOffset luôn là region ZoneId

Một offset `+07:00` không cho biết quy tắc vùng như `Asia/Ho_Chi_Minh`, càng không thể suy ra region có DST hay không. Cần lưu `ZoneId` thật nếu nghiệp vụ cần vùng.

### Lỗi 5 — Không kiểm tra null

Nhiều built-in query trả null khi thiếu dữ liệu. Gọi `date.getYear()` ngay sau một query có thể thiếu dữ liệu dẫn đến NPE. Xác định policy ở boundary.

### Lỗi 6 — Dùng LocalDate::from và nghĩ nó luôn trả null nếu thiếu ngày

`LocalDate::from` là lựa chọn strict; có thể ném `DateTimeException`. Dùng `TemporalQueries.localDate()` nếu cần kết quả thiếu dữ liệu là null.

### Lỗi 7 — Nhầm precision() với độ chính xác vật lý

`ChronoUnit.NANOS` nói về khả năng biểu diễn của kiểu, không chứng minh clock thực tế chính xác một nano giây hoặc DB giữ đủ chín chữ số.

### Lỗi 8 — Nhầm chronology() null là object thời gian không hợp lệ

`LocalTime` không có hệ lịch. Null ở chronology có thể là hoàn toàn bình thường.

### Lỗi 9 — Truy vấn đệ quy chính nó

Trong `queryFrom`, gọi `temporal.query(this)` làm cùng query tiếp tục chạy lặp, có thể stack overflow. Gọi các query thành phần **khác** hoặc đọc field an toàn.

### Lỗi 10 — Đọc ChronoField không hỗ trợ mà không kiểm tra

Không phải mọi temporal cung cấp `EPOCH_DAY`, `NANO_OF_DAY`, `OFFSET_SECONDS`. Dùng `isSupported`/`TemporalQueries` hoặc fail fast với lỗi minh bạch.

### Lỗi 11 — Dùng query có state mutable trong nhiều thread

Hợp đồng `TemporalQuery.queryFrom` yêu cầu thread-safe; tránh lưu cache thay đổi không đồng bộ hoặc chia sẻ buffer mutable. Query stateless/immutable thường phù hợp nhất.

### Lỗi 12 — Dùng LocalDate.now() làm fallback tự động

Nếu temporal không có ngày, lấy “hôm nay” ngầm định làm thay đổi kết quả theo clock và timezone. Chỉ chọn fallback theo hợp đồng rõ, inject Clock nếu cần.

### Lỗi 13 — Xem query weekend là định nghĩa ngày làm việc toàn cầu

Thứ Bảy/Chủ nhật không nhất thiết là ngày nghỉ ở mọi nơi và còn ngày lễ/ca làm việc. Query minh họa `DAY_KIND` cố định theo ISO weekend, không phải một business calendar hoàn chỉnh.

### Lỗi 14 — Nhầm TemporalQuery với TemporalAdjuster

Query trả kết quả tổng quát, adjuster tạo ngày/giờ mới từ temporal. Tách trách nhiệm giúp API dễ hiểu.

### Lỗi 15 — Bỏ qua hệ lịch

Các TemporalAccessor không ISO có thể dùng chronology khác. Nếu custom query chỉ áp cho ISO, xác nhận hoặc mô tả rõ điều kiện. Đừng áp lịch ISO theo trực giác lên một hệ lịch khác.

### Lỗi 16 — Viết query trả Object chung chung

`TemporalQuery<Object>` làm caller phải ép kiểu không an toàn. Dùng `TemporalQuery<LocalDate>`, `TemporalQuery<String>` hoặc kiểu domain cụ thể để compiler hỗ trợ.

### Lỗi 17 — Nhầm parse(text,query) với parse mặc định

`DateTimeFormatter.parse(text,query)` áp query lên dữ liệu sau parse. Nếu text không có thành phần bắt buộc hoặc sai format, vẫn có thể ném `DateTimeParseException`, không tự hoàn thiện bằng zone máy.

### Lỗi 18 — Dùng query riêng khi đã có getter ngắn, rõ ràng

Với một `LocalDate` đã biết, `date.getDayOfWeek()` thường đơn giản hơn tạo custom query. Query có giá trị khi cần tái sử dụng policy, làm việc với nhiều loại temporal, hoặc tích hợp với `DateTimeFormatter`.

## 14. Checklist để thiết kế một custom TemporalQuery tốt

1. **Đầu vào:** query chấp nhận mọi `TemporalAccessor` hay chỉ vài kiểu?
2. **Dữ liệu cần:** ngày, giờ, offset, zone, chronology, field nào?
3. **Truy vấn thiếu dữ liệu:** trả null, Optional, enum NO_DATA, hay ném lỗi?
4. **Semantics timezone:** nếu lấy ngày của Instant, zone được truyền từ đâu?
5. **Chronology:** chỉ ISO hay hỗ trợ nhiều hệ lịch?
6. **Độ phân giải:** có phụ thuộc phút/giây hay chỉ theo ngày?
7. **Không đệ quy:** query có vô tình gọi chính nó không?
8. **Read-only:** không sửa temporal đầu vào hay state ngoài?
9. **Thread-safe:** có chia sẻ mutation giữa các thread?
10. **Functional interface:** có cần lambda hoặc class riêng?
11. **Tính dễ đọc:** có getter/built-in query nào đơn giản hơn không?
12. **Kết quả typed:** dùng `TemporalQuery<R>` với `R` cụ thể?
13. **Bảo toàn ngữ nghĩa:** có nhầm zoneId, offset, instant và local?
14. **Test missing:** kiểm tra `LocalTime` hoặc `Instant` khi query cần ngày?
15. **Test date-only/time-only:** kiểm tra đầy đủ các kiểu input?
16. **Test zone:** phân biệt `OffsetDateTime` và `ZonedDateTime`?
17. **Test formatter:** parse với query trên chuỗi hợp lệ và không hợp lệ?
18. **Tài liệu hóa policy:** đặc biệt với weekend, ngày nghỉ và lịch nghiệp vụ?

### 14.1. Bộ test tối thiểu

| Input | Query | Kỳ vọng |
| --- | --- | --- |
| `LocalDate.of(2025,7,5)` | `localDate()` | `2025-07-05` |
| `LocalTime.NOON` | `localDate()` | `null` |
| `LocalTime.NOON` | `LocalDate::from` | `DateTimeException` |
| `LocalDateTime` | `zone()` | `null` |
| `OffsetDateTime` | `zoneId()` | `null` |
| `OffsetDateTime` | `zone()` | Offset tương ứng |
| `ZonedDateTime` | `zoneId()` | Region hoặc zone được lưu |
| `Instant` | `localDate()` | `null` |
| `Instant.atZone(zone)` | `localDate()` | Ngày địa phương ở vùng đó |
| `LocalDate` | `precision()` | `DAYS` |
| `LocalDateTime` | `precision()` | `NANOS` |
| `LocalTime` | `chronology()` | `null` |
| Thứ Bảy `2025-07-05` | `DAY_KIND` | `WEEKEND` |
| Thứ Hai `2025-07-07` | `DAY_KIND` | `WEEKDAY` |
| Thứ Hai `2025-07-07` | `NEXT_MONDAY` | `2025-07-14` |
| Chuỗi ISO date | `DateTimeFormatter.parse(text,DAY_KIND)` | Nhãn theo ngày |
| Temporal không có ngày | Query nghiệp vụ strict | Lỗi rõ ràng |
| Query chia sẻ giữa thread | Truy vấn nhiều lần | Không có side effect hoặc data race |

## 15. Bài tập tự kiểm tra và đáp án

**Câu 1.** `TemporalQuery<R>` khác `TemporalField` ở đâu?

**Đáp án:** `TemporalField` mô tả một trường số được đọc bằng `get`/`getLong`; `TemporalQuery<R>` đóng gói logic hỏi từ TemporalAccessor và có thể trả **bất kỳ kiểu `R` phù hợp**.

**Câu 2.** Vì sao `LocalDateTime.query(TemporalQueries.zone())` trả null?

**Đáp án:** Vì `LocalDateTime` không chứa zone hay offset. Tên "Local" không nghĩa nó lưu zone mặc định của máy.

**Câu 3.** `OffsetDateTime` có offset nhưng `zoneId()` vẫn null — đúng hay sai?

**Đáp án:** Đúng. `zoneId()` strict, còn `zone()` fallback sang offset.

**Câu 4.** Khi cần một `LocalDate` từ temporal có thể thiếu ngày, dùng gì?

**Đáp án:** `temporal.query(TemporalQueries.localDate())` trả null nếu không có; nếu thiếu ngày phải là lỗi, dùng `LocalDate::from` hoặc query strict tự viết.

**Câu 5.** `TemporalQueries.precision()` trả NANOS trên `Instant` có nghĩa đồng hồ đang dùng đo chính xác đến 1 ns không?

**Đáp án:** Không. Nó nói kiểu `Instant` hỗ trợ đơn vị nhỏ nhất là nanosecond, không nói gì về độ chính xác của clock vật lý.

**Câu 6.** Có nên dùng `temporal.query(this)` ngay trong `queryFrom` của chính query không?

**Đáp án:** Không. Nó có thể dẫn đến đệ quy không kết thúc. Gọi query thành phần khác hoặc đọc field đã được temporal cung cấp.

**Câu 7.** Query cuối tuần nên trả false nếu temporal chỉ có giờ?

**Đáp án:** Không mặc định. Vì **không có ngày** khác với "ngày không phải cuối tuần"; có thể trả `NO_DATE` hoặc giá trị không xác định theo hợp đồng.

**Câu 8.** `DateTimeFormatter.ISO_LOCAL_DATE.parse("2025-07-05", DAY_KIND)` làm gì?

**Đáp án:** Parse chuỗi ngày ISO rồi áp query để trả `WEEKEND`, không cần caller tự parse ngày và gọi query trong hai bước.

**Câu 9.** `TemporalAdjusters.next(MONDAY)` với đầu vào đã là thứ Hai trả hôm nay hay tuần sau?

**Đáp án:** Tuần sau. Muốn hôm nay hoặc thứ Hai tiếp theo thì dùng `nextOrSame(MONDAY)`.

**Câu 10.** `Instant.query(TemporalQueries.localDate())` có tự dùng timezone hệ thống để lấy ngày không?

**Đáp án:** Không. Phải chọn zone để tạo `ZonedDateTime` hoặc biểu diễn local phù hợp rồi mới lấy ngày.

**Câu 11.** `TemporalQueries.chronology()` trên LocalTime trả gì?

**Đáp án:** `null`, vì LocalTime chỉ có giờ, không xác định hệ lịch của ngày.

**Câu 12.** Query riêng có nên chứa state thay đổi dùng chung giữa thread không?

**Đáp án:** Không nếu chưa có đồng bộ và hợp đồng đúng. Nên làm query stateless, thuần, read-only và thread-safe.

**Câu 13.** Khi nào nên dùng `TemporalQuery<Optional<LocalDate>>`?

**Đáp án:** Khi API muốn buộc caller xét trường hợp thiếu ngày một cách tường minh thay vì truyền `null`. Không bắt buộc mọi custom query dùng Optional.

**Câu 14.** `TemporalQueries.zone()` có thể trả một `ZoneOffset` không?

**Đáp án:** Có. Khi temporal không có zone ID nhưng có offset, zone() fallback sang `ZoneOffset`, một lớp con của `ZoneId`.

**Câu 15.** Custom query có thể dùng trên output của formatter không?

**Đáp án:** Có. `DateTimeFormatter.parse(text,query)` áp query sau parse. Kết quả phụ thuộc dữ liệu mà formatter đã giải quyết và hợp đồng query.

**Câu 16.** Khi cần lấy thứ trong tuần từ một `LocalDate` cụ thể, luôn phải tạo custom query?

**Đáp án:** Không. `date.getDayOfWeek()` đơn giản, trực tiếp hơn. Query riêng hữu ích khi đóng gói chính sách tái sử dụng hoặc làm việc trên `TemporalAccessor` tổng quát.

## 16. Tổng kết

- **`TemporalQuery<R>`** là một chiến lược **read-only** lấy hoặc suy ra kết quả kiểu `R` từ một `TemporalAccessor`.
- Ưu tiên viết **`temporal.query(query)`**; `queryFrom(temporal)` là phương thức functional interface cơ sở.
- **`TemporalQueries` cung cấp bảy factory:** `zoneId`, `zone`, `offset`, `chronology`, `localDate`, `localTime`, `precision`.
- **`zoneId()` strict khác `zone()` lenient**: `OffsetDateTime` có thể cho `zoneId()==null` nhưng `zone()==offset`.
- **`localDate()`/`localTime()` có thể trả null** khi thiếu dữ liệu, khác với các conversion strict như `LocalDate::from`.
- **`precision()==NANOS` không khẳng định clock đo được 1 ns**; chỉ nói về đơn vị nhỏ nhất mà kiểu temporal hỗ trợ.
- **Custom query** có thể trả String, enum, Boolean, LocalDate hoặc Optional; phải định nghĩa rõ trường hợp thiếu dữ liệu.
- **Không gọi lại chính query từ queryFrom**, không thay đổi temporal đầu vào; query stateless/immutable giúp bảo đảm thread-safety.
- **`DateTimeFormatter.parse(text,query)`** tích hợp query trực tiếp với việc parse chuỗi ngày/giờ.
- **`TemporalAdjuster` điều chỉnh**, **`TemporalQuery` truy vấn**, còn **`Clock` là nguồn giờ hiện tại** — ba vai trò khác nhau.
- Các API trên là một phần của `java.time` từ Java 8 và **vẫn còn áp dụng hiện nay**.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — TemporalQuery](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/TemporalQuery.html)
- [Oracle Java SE 8 — TemporalQueries: zoneId, zone, offset, chronology, localDate, localTime, precision](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/TemporalQueries.html)
- [Oracle Java SE 8 — TemporalAccessor.query](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/TemporalAccessor.html)
- [Oracle Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 8 — TemporalAdjusters](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/TemporalAdjusters.html)
- [Oracle Java SE 8 — Clock](https://docs.oracle.com/javase/8/docs/api/java/time/Clock.html)
- [Oracle Java SE 25 — TemporalQueries (API hiện hành)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalQueries.html)
- [Oracle Java SE 25 — TemporalQuery (API hiện hành)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalQuery.html)
