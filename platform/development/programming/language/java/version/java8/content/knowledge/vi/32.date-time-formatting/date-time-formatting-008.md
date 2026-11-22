# parse, parseBest và truy vấn kết quả trong Java DateTimeFormatter

Trong Java 8 và các bản Java hiện hành, `java.time.format.DateTimeFormatter` cung cấp API để **định dạng** và **phân tích chuỗi ngày-giờ**. Ba thao tác thường bị nhầm là:

- `formatter.parse(text)`: phân tích chuỗi thành `TemporalAccessor` đã được resolve, chưa phải một `LocalDate`, `LocalDateTime` hay `ZonedDateTime` cụ thể.
- `formatter.parse(text, query)`: phân tích và dùng `TemporalQuery<T>` để nhận kết quả đúng kiểu `T`; ví dụ `LocalDate::from`, `LocalDateTime::from`, `YearMonth::from`.
- `formatter.parseBest(text, q1, q2, ...)`: phân tích một định dạng có thể có **trường tùy chọn**, thử các query **theo thứ tự được truyền vào**, rồi trả đối tượng tương thích đầu tiên; kiểu trả về của phương thức là `TemporalAccessor`.

Sau parse, `TemporalQueries` giúp hỏi ngày, giờ, offset, vùng hoặc chronology. Query có thể trả `null` nếu không có dữ liệu cần hỏi; điều đó **không đồng nghĩa chuỗi vừa parse bị lỗi**.

Bài học giải thích chính xác ba cách parse, các query và kiểu trả về, optional sections trong pattern, thứ tự ưu tiên của `parseBest`, sự khác nhau giữa `ZoneId` với `ZoneOffset`, `ResolverStyle`, lỗi dữ liệu và những cách kiểm thử thực tế. Mọi API được dùng đều còn hiệu lực hiện nay.

## 1. Luồng xử lý từ text tới kết quả

`DateTimeFormatter` về bản chất thực hiện **hai giai đoạn**:

1. **Parse theo cấu trúc:** đọc các chữ và số theo pattern/formatter, lấy trường như `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `HOUR_OF_DAY`, `OFFSET_SECONDS`, vùng.
2. **Resolve các trường:** kiểm và ghép các giá trị thành ngày/giờ hợp lệ theo chronology và `ResolverStyle`. Chẳng hạn 29/02/2024 hợp lệ, nhưng 30/02/2024 không tồn tại nếu kiểm STRICT.

Ví dụ:

~~~text
Input:     2024-02-29 10:15
Pattern:   uuuu-MM-dd HH:mm
Raw fields: year=2024, month=2, day=29, hour=10, minute=15
Resolve:   ngày nhuận hợp lệ, giờ 10:15
Có được:   LocalDate và LocalTime
Chưa có:   ZoneId/UTC offset/Instant
~~~

**Phân tích cú pháp thành công không đảm bảo kết quả đủ dữ liệu cho mọi kiểu đích.** Chuỗi `2024-02` có thể hợp lệ với pattern `uuuu-MM` để tạo `YearMonth`, nhưng chưa đủ thông tin làm `LocalDate`. Chuỗi có giờ địa phương nhưng thiếu offset hoặc vùng thì chưa tự xác định một `Instant` duy nhất.

### 1.1. Kiểu đầu ra cần gì?

| Kiểu mong muốn | Thông tin cần có | Tình huống sử dụng |
|---|---|---|
| `YearMonth` | Năm và tháng | Tháng kế toán, kỳ thanh toán |
| `LocalDate` | Ngày đầy đủ | Ngày sinh hoặc ngày sự kiện |
| `LocalTime` | Giờ/phút và các trường thời gian đủ resolve | Giờ mở cửa |
| `LocalDateTime` | Ngày và giờ không bắt buộc có zone | Lịch theo đồng hồ |
| `OffsetDateTime` | Ngày-giờ và offset | Timestamp có `+07:00` |
| `ZonedDateTime` | Ngày-giờ cùng ZoneId/offset thích hợp | Hiển thị và lập lịch theo vùng |
| `Instant` | Một thời điểm xác định trên timeline UTC | Event timestamp, log |
| `TemporalAccessor` | Những trường sau parse/resolve | Kiểm tra trường, truy vấn linh hoạt |

Một `TemporalAccessor` không phải dạng “giá trị ngày giờ đầy đủ nhất”; nó là **giao diện truy cập thông tin thời gian**. Hãy xác định output contract trước khi chọn overload parse.

## 2. parse(CharSequence): nhận TemporalAccessor

Ví dụ:

~~~java
DateTimeFormatter fmt = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm")
        .withResolverStyle(ResolverStyle.STRICT);

TemporalAccessor parsed = fmt.parse("2024-02-29 10:15");
~~~

Mảnh code nằm trong phương thức, cần `java.time.format.*` và `java.time.temporal.*`.

`fmt.parse(text)` yêu cầu **toàn bộ text** khớp định dạng, trả `TemporalAccessor` đã resolve. Nó **không** hứa trả một đối tượng class cụ thể như `LocalDateTime`. Nếu cần một đối tượng đích, hãy dùng query.

~~~java
LocalDate date = parsed.query(TemporalQueries.localDate());
LocalTime time = parsed.query(TemporalQueries.localTime());
ZoneOffset offset = parsed.query(TemporalQueries.offset());

// date = 2024-02-29
// time = 10:15
// offset = null
~~~

Nhận `null` ở offset trong ví dụ này là **đúng hợp đồng** vì pattern và input không cung cấp offset. Nó không phải lỗi parse. Đừng dùng `null` để tự cho là UTC, trừ khi ứng dụng có chính sách rõ ràng.

### 2.1. Đọc một ChronoField

~~~java
int day = parsed.get(ChronoField.DAY_OF_MONTH); // 29
boolean hasOffset = parsed.isSupported(
        ChronoField.OFFSET_SECONDS); // false
~~~

`get(field)` lấy giá trị int nếu field được hỗ trợ. Nếu không hỗ trợ, Java có thể ném `UnsupportedTemporalTypeException`. `getLong(field)` phù hợp các field có miền long, còn `isSupported(field)` kiểm trước.

Khi cần **một ngày hoàn chỉnh**, nên dùng `TemporalQueries.localDate()` hoặc `LocalDate.from(parsed)` thay vì tự ráp ngày/tháng/năm từ field, vì quá trình resolve/chronology có thể quyết định ý nghĩa cuối cùng.

### 2.2. Text còn ký tự thừa

~~~java
fmt.parse("2024-02-29 10:15");       // Đúng.
fmt.parse("2024-02-29 10:15 extra"); // DateTimeParseException.
~~~

Dòng thứ hai là **phản ví dụ**, không phải chương trình chạy liên tục với dòng trên. `parse(text)` không tự bỏ đi phần đuôi không khớp. Điều này rất quan trọng khi nhận ngày giờ từ API, tệp cấu hình hoặc biểu mẫu người dùng.

Các overload nhận `ParsePosition` có thể parse một phần nhưng yêu cầu tự kiểm index, khác với parse toàn văn thông thường.

## 3. parse(text, query): kết quả đúng kiểu

Overload generic là:

~~~java
T value = formatter.parse(text, temporalQuery);
~~~

Query thông thường là method reference tới `from(TemporalAccessor)` của kiểu đích.

~~~java
LocalDateTime value = fmt.parse(
        "2024-02-29 10:15",
        LocalDateTime::from);
// 2024-02-29T10:15
~~~

Hai cách parse ngày sau cho cùng kết quả:

~~~java
LocalDate a = LocalDate.parse(
        "2024-02-29", DateTimeFormatter.ISO_LOCAL_DATE);

LocalDate b = DateTimeFormatter.ISO_LOCAL_DATE.parse(
        "2024-02-29", LocalDate::from);
~~~

Nếu mục tiêu **chắc chắn** là LocalDate, `LocalDate.parse` thường rõ ràng hơn. Nếu cần chọn giữa nhiều kiểu hoặc đọc các field query phức tạp, dùng DateTimeFormatter.

### 3.1. Khác nhau giữa query tùy chọn và từ kiểu bắt buộc

Hai cách hỏi ngày có mục tiêu khác nhau:

~~~java
LocalDate optional = parsed.query(TemporalQueries.localDate());
LocalDate required = LocalDate.from(parsed);
~~~

`TemporalQueries.localDate()` **trả null** khi không có đủ ngày; `LocalDate.from(parsed)` **ném DateTimeException** nếu không tạo được ngày. Chọn cách bắt buộc khi schema yêu cầu ngày đầy đủ; chọn query null-tolerant nếu ngày là trường tùy chọn.

Ví dụ `uuuu-MM`:

~~~java
DateTimeFormatter ym = DateTimeFormatter.ofPattern("uuuu-MM");
YearMonth month = ym.parse("2024-02", YearMonth::from);
// 2024-02

// ym.parse("2024-02", LocalDate::from); // Không đủ ngày.
~~~

Không thể “sửa” lỗi bằng cách tự đưa ngày 1 vào nếu ứng dụng cần biết người dùng có thực sự gửi ngày hay không.

### 3.2. Query không thay thế validation nghiệp vụ

Ngay cả khi parse thành công và tạo được `LocalDate`, ngày đó có thể nằm ngoài khoảng sản phẩm hỗ trợ. Khi parse được `LocalDateTime`, nó có thể là giờ không tồn tại hoặc lặp đôi ở vùng có DST. Khi parse được `OffsetDateTime`, hệ thống chưa chắc biết tên vùng địa lý cần dùng cho lịch tương lai.

Nên tách **đúng cú pháp và lịch** với **đúng chính sách nghiệp vụ**; đừng xem parse thành công là đáp ứng toàn bộ điều kiện.

## 4. parseBest: định dạng tùy chọn, nhiều kiểu đầu ra

`DateTimeFormatter.parseBest(text, query1, query2, ...)` thử các query **theo thứ tự**. Query thành công đầu tiên sẽ quyết định đối tượng kết quả. Tài liệu chính thức khuyến nghị **kiểu đầy đủ hơn đứng trước kiểu tối thiểu hơn**.

Pattern cho phép chỉ ngày hoặc ngày kèm giờ:

~~~java
DateTimeFormatter flexible = DateTimeFormatter
        .ofPattern("uuuu-MM-dd['T'HH:mm]")
        .withResolverStyle(ResolverStyle.STRICT);

TemporalAccessor dayOnly = flexible.parseBest(
        "2024-02-29",
        LocalDateTime::from, LocalDate::from);

TemporalAccessor withTime = flexible.parseBest(
        "2024-02-29T10:15",
        LocalDateTime::from, LocalDate::from);
~~~

Kết quả:

~~~text
dayOnly -> LocalDate: 2024-02-29
withTime -> LocalDateTime: 2024-02-29T10:15
~~~

Tại sao?

- Với chuỗi chỉ có ngày, `LocalDateTime::from` thất bại vì thiếu giờ; `LocalDate::from` thành công.
- Với chuỗi ngày và giờ, `LocalDateTime::from` thành công ngay nên Java không dùng query thứ hai.
- Nếu viết `LocalDate::from` trước, nó có thể **thành công trước và bỏ thông tin giờ trong kết quả** mặc dù text có cả giờ.

### 4.1. Bảng về thứ tự query

| Đầu vào | Thứ tự query | Kết quả |
|---|---|---|
| `2024-02-29` | `LocalDateTime::from` rồi `LocalDate::from` | LocalDate |
| `2024-02-29T10:15` | `LocalDateTime::from` rồi `LocalDate::from` | LocalDateTime |
| `2024-02-29T10:15` | `LocalDate::from` rồi `LocalDateTime::from` | LocalDate, không giữ giờ |
| Ngày giờ và zone ID | `ZonedDateTime::from` rồi `LocalDateTime::from` | ZonedDateTime khi đủ zone |
| Ngày giờ không có zone | `ZonedDateTime::from` rồi `LocalDateTime::from` | LocalDateTime khi không có zone override |

**Hạn chế:** `parseBest` yêu cầu ít nhất **hai query**. Với một query đơn lẻ, dùng `parse(text, query)`, không dùng `parseBest`. Những query cho `parseBest` phải tạo kết quả kiểu triển khai `TemporalAccessor`.

### 4.2. Kết quả cần kiểm kiểu

~~~java
TemporalAccessor best = flexible.parseBest(
        input, LocalDateTime::from, LocalDate::from);

if (best instanceof LocalDateTime dateTime) {
    // Có cả ngày và giờ.
} else if (best instanceof LocalDate date) {
    // Có ngày, chưa có giờ.
} else {
    throw new IllegalStateException("Unexpected parse result");
}
~~~

Đây là **mảnh code Java 17+**; `flexible` và `input` phải được khai báo trước. Java 8 cũng hỗ trợ `instanceof`, nhưng chưa có pattern matching trong điều kiện, nên phải cast trong nhánh sau khi kiểm kiểu.

Không cast mù `(ZonedDateTime) best` khi input có thể chỉ là LocalDateTime. `parseBest` trả `TemporalAccessor` vì bản chất nó có **nhiều khả năng kết quả**.

### 4.3. parseBest không bỏ qua text sai

Nếu formatter không khớp text hoặc không query nào tạo được temporal có thể dùng, `parseBest` sẽ thất bại theo hợp đồng, thường dưới `DateTimeParseException`. Nó không lấy một đoạn khớp ở đầu rồi tự bỏ ký tự dư; không dùng nó làm parser “nhắm mắt nhận mọi thứ”.

## 5. Optional section trong DateTimeFormatter pattern

Pattern `[ ... ]` dùng để đánh dấu một đoạn **tùy chọn**:

~~~java
DateTimeFormatter flexible =
        DateTimeFormatter.ofPattern("uuuu-MM-dd['T'HH:mm]");
~~~

Trong đó:

- `uuuu-MM-dd` là ngày bắt buộc.
- `[ ... ]` là đoạn có hoặc không.
- `'T'` được đặt trong nháy đơn vì đây là **ký tự literal**, không phải trường pattern.
- Dữ liệu có thể là `2024-02-29` hoặc `2024-02-29T10:15`.

Không nhầm **optional** với **default**. Nếu không có HH:mm, formatter **không tự tạo 00:00** cho LocalDateTime. Để tạo mặc định, `DateTimeFormatterBuilder.parseDefaulting` có thể được dùng có chủ đích, nhưng không nên tự điền giá trị mà nghiệp vụ chưa phê duyệt.

### 5.1. Tùy chọn ZoneId

~~~java
DateTimeFormatter optionalZone = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm[ VV]")
        .withResolverStyle(ResolverStyle.STRICT);

TemporalAccessor local = optionalZone.parseBest(
        "2024-02-29 10:15",
        ZonedDateTime::from, LocalDateTime::from);

TemporalAccessor zoned = optionalZone.parseBest(
        "2024-02-29 10:15 Asia/Ho_Chi_Minh",
        ZonedDateTime::from, LocalDateTime::from);
~~~

`VV` là pattern của **zone ID**. Dấu cách nằm trong đoạn tùy chọn nên chuỗi không có zone không cần dấu cách cuối.

Trong ví dụ đầu, `local` là `LocalDateTime`; trong ví dụ thứ hai, `zoned` là `ZonedDateTime` mang ID `Asia/Ho_Chi_Minh`. Không suy ra timezone của người dùng từ vị trí máy chủ khi chuỗi đầu vào không có zone.

### 5.2. Chú ý chữ trong pattern

| Mã pattern | Ý nghĩa | Ví dụ |
|---|---|---|
| `u` / `uuuu` | Proleptic year | 2024 |
| `y` / `yyyy` | Year-of-era | 2024 thuộc một era |
| `M` / `MM` | Tháng bằng số | 02 |
| `d` / `dd` | Ngày trong tháng | 29 |
| `H` / `HH` | Giờ 0–23 | 10 |
| `m` / `mm` | Phút | 15 |
| `s` / `ss` | Giây | 30 |
| `VV` | Zone ID | Asia/Ho_Chi_Minh |
| `XXX` | Offset dạng ISO | +07:00 hoặc Z |
| `[ ... ]` | Đoạn tùy chọn | Có hoặc không có thời gian |
| `'T'` | Ký tự literal T | Phân cách ngày và giờ |

Với `ResolverStyle.STRICT`, thường dùng `uuuu` thay `yyyy` cho năm ISO thông thường: `yyyy` là **year-of-era** và có thể cần thông tin era để resolve thành LocalDate. Đừng tùy tiện coi `u` và `y` tương đương hoàn toàn.

## 6. TemporalQueries: truy vấn thuộc tính đã parse

`TemporalAccessor.query(TemporalQuery<R>)` trả một giá trị thuộc kiểu `R`. `TemporalQueries` cung cấp các query phổ biến:

| Query | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `localDate()` | LocalDate hoặc null | Có ngày hoàn chỉnh không? |
| `localTime()` | LocalTime hoặc null | Có giờ đã resolve không? |
| `offset()` | ZoneOffset hoặc null | Có UTC offset không? |
| `zoneId()` | ZoneId hoặc null | Có ZoneId theo nghĩa nghiêm ngặt không? |
| `zone()` | ZoneId hoặc null | Có zone; nếu không thì fallback offset |
| `chronology()` | Chronology hoặc null | Hệ lịch đang dùng |
| `precision()` | TemporalUnit hoặc null | Đơn vị chính xác nhỏ nhất khi xác định |

Ví dụ:

~~~java
TemporalAccessor parsed = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm")
        .parse("2024-02-29 10:15");

LocalDate day = parsed.query(TemporalQueries.localDate());
LocalTime time = parsed.query(TemporalQueries.localTime());
ZoneOffset offset = parsed.query(TemporalQueries.offset());

// day = 2024-02-29; time = 10:15; offset = null.
~~~

`null` là khả năng bình thường cho query tùy chọn. Nếu input phải chứa offset, **validate** `offset != null` và trả lỗi khi thiếu; không âm thầm biến thành +00:00.

### 6.1. zoneId khác zone

Với chuỗi chỉ có offset:

~~~java
TemporalAccessor value = DateTimeFormatter
        .ISO_OFFSET_DATE_TIME
        .parse("2024-02-29T10:15+07:00");

ZoneId explicitZoneId = value.query(
        TemporalQueries.zoneId()); // null

ZoneId fallbackZone = value.query(
        TemporalQueries.zone());   // +07:00

ZoneOffset offset = value.query(
        TemporalQueries.offset()); // +07:00
~~~

- `zoneId()` nghiêm ngặt: yêu cầu một ZoneId ở mức ngữ nghĩa của temporal; nó **không xem riêng offset** như một region được cung cấp.
- `zone()` linh hoạt hơn: nếu không có zone ID, lấy offset làm ZoneId.
- `offset()` lấy đúng số chênh lệch UTC nếu có.

**Offset không phải region ID.** Một `+07:00` có thể đúng cho nhiều địa điểm, không đủ mô tả lịch sử hay quy tắc giờ tương lai của `Asia/Ho_Chi_Minh`.

### 6.2. Query typed và đọc ChronoField không thay thế nhau

~~~java
boolean hasDay = parsed.isSupported(
        ChronoField.DAY_OF_MONTH);
int day = parsed.get(ChronoField.DAY_OF_MONTH);
~~~

`isSupported` cho biết field có thể đọc; `get` có thể ném `UnsupportedTemporalTypeException` nếu field thiếu. Dùng query typed `localDate()` khi muốn **ngày hoàn chỉnh**, vì ngày được tạo từ các field đã qua xử lý lịch; chỉ dùng `get` để lấy thành phần riêng khi phù hợp.

### 6.3. TemporalQuery tự định nghĩa

~~~java
TemporalQuery<Boolean> hasCompleteDateTime = temporal ->
        temporal.query(TemporalQueries.localDate()) != null
                && temporal.query(TemporalQueries.localTime()) != null;

Boolean complete = formatter.parse(
        "2024-02-29 10:15", hasCompleteDateTime);
~~~

Đây là mảnh code minh họa, cần `formatter` với pattern phù hợp và import `java.time.temporal.*`. Khi cần quy tắc phức tạp, query tự viết cho phép suy luận từ nhiều trường, nhưng không nên có side effect hoặc bí mật thay dữ liệu đã parse.

## 7. Bẫy parseBest với OffsetDateTime và ZonedDateTime

Trường hợp rất quan trọng:

~~~java
String value = "2024-02-29T10:15+07:00";

TemporalAccessor zonedFirst = DateTimeFormatter.ISO_DATE_TIME
        .parseBest(value,
                ZonedDateTime::from,
                OffsetDateTime::from,
                LocalDateTime::from);

TemporalAccessor offsetFirst = DateTimeFormatter.ISO_DATE_TIME
        .parseBest(value,
                OffsetDateTime::from,
                ZonedDateTime::from,
                LocalDateTime::from);
~~~

Cùng input, nhưng đầu ra có thể là:

~~~text
zonedFirst: ZonedDateTime
offsetFirst: OffsetDateTime
~~~

**Giải thích:** `ZonedDateTime::from` có thể tạo một `ZonedDateTime` sử dụng chính `ZoneOffset` làm zone, **ngay cả khi không có tên vùng IANA**. Vì vậy nó có thể thành công trước `OffsetDateTime::from`. `parseBest` chọn **query đầu tiên thành công**, không nhận biết một sự “ưu tiên tự động” theo chữ trong input.

Muốn biết text có thực sự chứa **region ZoneId** thì cần schema/pattern và kiểm tra rõ. Chỉ thấy `ZonedDateTime` **không chứng minh** người dùng đã nhập `America/New_York` hay một vùng khác.

### 7.1. Chuỗi có cả offset và region

~~~text
2024-02-29T10:15+07:00[Asia/Ho_Chi_Minh]
~~~

Có thể parse:

~~~java
ZonedDateTime result = DateTimeFormatter
        .ISO_ZONED_DATE_TIME
        .parse(
            "2024-02-29T10:15+07:00[Asia/Ho_Chi_Minh]",
            ZonedDateTime::from);
~~~

Offset và ZoneId không nhất thiết chứa cùng mức thông tin. Nếu input có cả hai mà không nhất quán với rules của vùng ở ngày đang xét, việc parse được thành instant theo offset không nên thay thế **kiểm tra tính nhất quán nghiệp vụ**. Đối với lịch hẹn tương lai, một region đầy đủ là thông tin rất quan trọng vì DST có thể thay đổi offset theo ngày.

## 8. STRICT, SMART và LENIENT khi resolve

`ResolverStyle` quyết định cách các trường đã đọc được biến thành giá trị ngày giờ.

| Chế độ | Quy tắc | Khi nào dùng |
|---|---|---|
| `STRICT` | Ngày/tháng/giờ sai bị từ chối theo quy tắc nghiêm ngặt | API validation, dữ liệu lịch pháp lý |
| `SMART` | Một số trường có thể được điều chỉnh hợp lý | UI chấp nhận sửa nhẹ có công bố |
| `LENIENT` | Cho phép nhiều trường vượt giới hạn rồi chuẩn hóa | Trường hợp nhập linh hoạt có chủ đích |

Ví dụ:

~~~java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter smart = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.SMART);

// strict.parse("2024-02-30", LocalDate::from); // Lỗi.
LocalDate corrected = smart.parse(
        "2024-02-30", LocalDate::from);
// 2024-02-29
~~~

Ngày 30/02 không tồn tại. SMART có thể điều chỉnh về ngày cuối tháng, còn STRICT từ chối. Nếu nghiệp vụ yêu cầu người dùng **thực sự nhập một ngày tồn tại**, nên dùng STRICT, tránh âm thầm đổi ngày sinh/ngày ký hợp đồng.

`DateTimeFormatter.ofPattern(...)` mặc định resolver SMART; `DateTimeFormatter.ISO_LOCAL_DATE` là formatter định sẵn dùng STRICT. Không mặc định mọi formatter có cùng chính sách.

### 8.1. Vì sao uuuu thường phù hợp hơn yyyy với STRICT?

`uuuu` mô tả **proleptic year**, còn `yyyy` là **year-of-era**. Một pattern STRICT chỉ có `yyyy-MM-dd` có thể thiếu thông tin era để resolve thành LocalDate như mong đợi. Dùng `uuuu-MM-dd` nếu dữ liệu là năm ISO thông thường và muốn strict parse.

### 8.2. Parse không tự làm validation theo nghiệp vụ

Ngoài ngày-giờ hợp lệ, ứng dụng còn phải kiểm:
- Khoảng ngày được chấp nhận;
- ID vùng hợp lệ và chính sách offset;
- Giờ địa phương rơi vào DST gap/overlap hay không;
- Người dùng có được phép bỏ trống giờ/offset không;
- Truy vấn kết quả có đủ kiểu dữ liệu yêu cầu không.

`STRICT` chỉ giúp đảm bảo **giải quyết các trường theo quy tắc chặt chẽ**, không thay thế toàn bộ hợp đồng API và lịch làm việc.

## 9. parseUnresolved và ParsePosition: chỉ dành cho xử lý nâng cao

`DateTimeFormatter.parseUnresolved(text, ParsePosition)` mới thực hiện giai đoạn **đọc field thô**, chưa resolve thành ngày giờ hợp lệ. Ví dụ chuỗi có tháng 0 hoặc ngày 65 vẫn có thể xuất hiện trong các field chưa resolve nếu cấu trúc ký tự phù hợp.

Không dùng nó để chấp nhận ngày sinh hoặc timestamp thông thường, bởi:
- Dữ liệu có thể không hợp lệ theo lịch;
- Caller phải xử lý `ParsePosition` và những bước validation tiếp theo;
- Kết quả không tương đương với LocalDate được xác minh.

### 9.1. Đọc một phần chuỗi khác parse toàn bộ

Các overload:

~~~java
formatter.parse(text, parsePosition);
formatter.parseUnresolved(text, parsePosition);
~~~

là **mẫu chữ ký**, trong đó `parsePosition` là `java.text.ParsePosition`. Chúng có thể không đọc hết text, nên khi API yêu cầu chuỗi ngày giờ hoàn chỉnh bạn phải kiểm vị trí cuối đã parse và phần văn bản dư.

Thông thường nên dùng `parse(text, Type::from)`, `Type.parse(text, formatter)` hoặc `parseBest`, vì chúng kiểm đủ toàn chuỗi và có resolve.

### 9.2. Lỗi parse có thông tin phục vụ validation

~~~java
try {
    LocalDate.parse(
            "2024-02-30",
            DateTimeFormatter.ISO_LOCAL_DATE);
} catch (DateTimeParseException e) {
    int index = e.getErrorIndex();
    String input = e.getParsedString();
    // Hiển thị thông báo phù hợp, tránh log input nhạy cảm.
}
~~~

`getErrorIndex()` có thể là `-1` trong một số trường hợp; đừng giả định mọi lỗi có đúng một ký tự sai. Khi xử lý input đến từ người dùng, giới hạn kích thước và bảo vệ thông tin riêng tư trong log.

## 10. Các query chuyên biệt: 24:00 và leap second

`DateTimeFormatter.parsedExcessDays()` trả `Period` cho biết **số ngày dư** khi resolver xử lý những giá trị giờ đặc biệt.

Ví dụ SMART xử lý `24:00` khi chỉ có giờ:

~~~java
DateTimeFormatter time = DateTimeFormatter
        .ofPattern("HH:mm")
        .withResolverStyle(ResolverStyle.SMART);

TemporalAccessor parsed = time.parse("24:00");

LocalTime resolvedTime =
        parsed.query(TemporalQueries.localTime()); // 00:00

Period extra =
        parsed.query(DateTimeFormatter.parsedExcessDays()); // P1D
~~~

Đầu vào `24:00` được hiểu là **00:00 của ngày kế tiếp** trong tình huống SMART hỗ trợ. Vì chuỗi không có ngày, query cần giữ `P1D` để caller biết đã vượt qua ranh giới ngày. Nếu văn bản có cả ngày đầy đủ, resolver có thể đã cộng ngày dư vào ngày và query excess trả ZERO.

Đừng chỉ lưu `00:00` rồi làm mất thông tin ngày dư khi nghiệp vụ định nghĩa `24:00` là thời điểm kết thúc ngày hôm trước.

`DateTimeFormatter.parsedLeapSecond()` là query boolean phục vụ trường hợp parser hỗ trợ giây nhuận, đặc biệt qua `DateTimeFormatterBuilder.appendInstant()`. Không phải mọi pattern `HH:mm:ss` đều chấp nhận giây 60. Dùng đúng các formatter được tài liệu hóa nếu hệ thống thật sự có yêu cầu về leap second.

## 11. Locale và Zone override không chỉ là trang trí

`DateTimeFormatter.withLocale(locale)` cho phép dùng dữ liệu tên tháng/tên ngày theo ngôn ngữ đã xác định. Ví dụ:

~~~java
DateTimeFormatter english = DateTimeFormatter.ofPattern(
        "dd MMM uuuu", java.util.Locale.ENGLISH);

LocalDate date = english.parse(
        "29 Feb 2024", LocalDate::from);
~~~

Với pattern có `MMM`, việc phụ thuộc default locale của máy chủ có thể khiến input thất bại khi triển khai ở môi trường khác. Nên đặt locale tường minh nếu giao thức hoặc UX yêu cầu một ngôn ngữ nhất định.

### 11.1. withZone có thể đưa zone vào kết quả

~~~java
DateTimeFormatter configured = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm")
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`withZone` trả một formatter mới có **override zone**. Khi parse chuỗi không có zone, override có thể cung cấp ZoneId cho kết quả. Vì thế `parsed.query(TemporalQueries.zoneId()) != null` **không chứng minh người dùng đã tự nhập zone**. Nếu cần biết zone đến từ text hay cấu hình, phải lưu bối cảnh từ input hoặc dùng formatter/schema tách biệt.

Không tự xem LocalDateTime chưa có zone là Instant. Nếu ứng dụng chấp nhận giờ địa phương mà thiếu vùng, cần chính sách zone rõ ràng và xử lý DST khi xác định mốc thực tế.

### 11.2. Ưu tiên formatter ISO khi giao tiếp giữa hệ thống

- `ISO_LOCAL_DATE`: ngày ISO.
- `ISO_LOCAL_DATE_TIME`: ngày giờ địa phương, không offset.
- `ISO_OFFSET_DATE_TIME`: ngày giờ có offset.
- `ISO_ZONED_DATE_TIME`: ngày giờ kèm zone khi có.
- `ISO_INSTANT`: Instant UTC.

Không tự tách chuỗi bằng `split` rồi tự xử lý năm nhuận, offset hay DST nếu JDK đã có DateTimeFormatter cung cấp hợp đồng rõ.

## 12. Chương trình Java độc lập và stdout đã kiểm chứng

Lưu file **`ParseQueriesDemo.java`**, biên dịch trên **JDK 17+**; code chỉ dùng các API Java hiện hành. Chương trình minh họa parse thường và typed, truy vấn ngày/giờ/offset, parseBest với ngày/giờ/zone tùy chọn, ảnh hưởng thứ tự query, strict/smart, ký tự dư và 24:00.

~~~java
import java.time.*;
import java.time.format.*;
import java.time.temporal.*;

public class ParseQueriesDemo {
    public static void main(String[] args) {
        DateTimeFormatter exact = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm")
                .withResolverStyle(ResolverStyle.STRICT);

        String input = "2024-02-29 10:15";
        LocalDateTime direct = exact.parse(input, LocalDateTime::from);
        TemporalAccessor parsed = exact.parse(input);
        System.out.println("Typed parse: " + direct);
        System.out.println("Query date: " + parsed.query(TemporalQueries.localDate()));
        System.out.println("Query time: " + parsed.query(TemporalQueries.localTime()));
        System.out.println("Query offset: " + parsed.query(TemporalQueries.offset()));
        System.out.println("Day field: " + parsed.get(ChronoField.DAY_OF_MONTH));

        DateTimeFormatter flexible = DateTimeFormatter
                .ofPattern("uuuu-MM-dd['T'HH:mm]")
                .withResolverStyle(ResolverStyle.STRICT);

        TemporalAccessor dateOnly = flexible.parseBest(
                "2024-02-29",
                LocalDateTime::from, LocalDate::from);
        TemporalAccessor dateTime = flexible.parseBest(
                "2024-02-29T10:15",
                LocalDateTime::from, LocalDate::from);
        System.out.println("Best date: " + dateOnly.getClass().getSimpleName()
                + " " + dateOnly);
        System.out.println("Best date-time: " + dateTime.getClass().getSimpleName()
                + " " + dateTime);

        DateTimeFormatter zoneOptional = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm[ VV]")
                .withResolverStyle(ResolverStyle.STRICT);
        TemporalAccessor local = zoneOptional.parseBest(
                "2024-02-29 10:15",
                ZonedDateTime::from, LocalDateTime::from);
        TemporalAccessor zoned = zoneOptional.parseBest(
                "2024-02-29 10:15 Asia/Ho_Chi_Minh",
                ZonedDateTime::from, LocalDateTime::from);
        System.out.println("Best local: " + local.getClass().getSimpleName());
        System.out.println("Best zoned: " + zoned);
        System.out.println("Zone query: " + zoned.query(TemporalQueries.zoneId()));

        String withOffset = "2024-02-29T10:15+07:00";
        TemporalAccessor firstZoned = DateTimeFormatter.ISO_DATE_TIME
                .parseBest(withOffset, ZonedDateTime::from,
                        OffsetDateTime::from, LocalDateTime::from);
        TemporalAccessor firstOffset = DateTimeFormatter.ISO_DATE_TIME
                .parseBest(withOffset, OffsetDateTime::from,
                        ZonedDateTime::from, LocalDateTime::from);
        System.out.println("Offset-first type: "
                + firstOffset.getClass().getSimpleName());
        System.out.println("Zone-first type: "
                + firstZoned.getClass().getSimpleName());

        TemporalAccessor offsetParsed =
                DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(withOffset);
        System.out.println("Strict zoneId query: "
                + offsetParsed.query(TemporalQueries.zoneId()));
        System.out.println("Fallback zone query: "
                + offsetParsed.query(TemporalQueries.zone()));
        System.out.println("Offset query: "
                + offsetParsed.query(TemporalQueries.offset()));

        DateTimeFormatter smart = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withResolverStyle(ResolverStyle.SMART);
        System.out.println("SMART Feb30: "
                + smart.parse("2024-02-30", LocalDate::from));

        try {
            DateTimeFormatter.ISO_LOCAL_DATE
                    .parse("2024-02-30", LocalDate::from);
        } catch (DateTimeParseException expected) {
            System.out.println("STRICT invalid date rejected");
        }
        try {
            exact.parse("2024-02-29 10:15 extra", LocalDateTime::from);
        } catch (DateTimeParseException expected) {
            System.out.println("Trailing text rejected");
        }

        DateTimeFormatter endOfDay = DateTimeFormatter
                .ofPattern("HH:mm")
                .withResolverStyle(ResolverStyle.SMART);
        TemporalAccessor midnight = endOfDay.parse("24:00");
        System.out.println("24:00 resolved time: "
                + midnight.query(TemporalQueries.localTime()));
        System.out.println("24:00 excess days: "
                + midnight.query(DateTimeFormatter.parsedExcessDays()));
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ParseQueriesDemo.java
java ParseQueriesDemo
~~~

Stdout đã được đối chiếu bằng chạy Java thực:

~~~text
Typed parse: 2024-02-29T10:15
Query date: 2024-02-29
Query time: 10:15
Query offset: null
Day field: 29
Best date: LocalDate 2024-02-29
Best date-time: LocalDateTime 2024-02-29T10:15
Best local: LocalDateTime
Best zoned: 2024-02-29T10:15+07:00[Asia/Ho_Chi_Minh]
Zone query: Asia/Ho_Chi_Minh
Offset-first type: OffsetDateTime
Zone-first type: ZonedDateTime
Strict zoneId query: null
Fallback zone query: +07:00
Offset query: +07:00
SMART Feb30: 2024-02-29
STRICT invalid date rejected
Trailing text rejected
24:00 resolved time: 00:00
24:00 excess days: P1D
~~~

### 12.1. Đọc output

- `Query offset: null`: ngày giờ đã parse được nhưng input không có offset.
- `Best date: LocalDate` và `Best date-time: LocalDateTime`: formatter cho phép time tùy chọn, query đầy đủ được thử trước.
- `Best zoned` in cả region `Asia/Ho_Chi_Minh`, cho thấy trường vùng đã có trong input.
- `Zone-first type: ZonedDateTime` trong trường hợp offset-only **không có nghĩa input có region IANA**; offset cũng có thể được dùng làm ZoneId.
- `Strict zoneId query: null` và `Fallback zone query: +07:00` là hai kết quả đúng với cùng một chuỗi có offset.
- `SMART Feb30: 2024-02-29`: nếu ứng dụng cần từ chối ngày không có thật, chọn STRICT.
- `Trailing text rejected`: parse toàn văn không cho phép chữ dư.
- `24:00 resolved time: 00:00` cùng `24:00 excess days: P1D` giữ ý nghĩa vượt sang ngày kế tiếp.

Không đưa giờ hiện tại của máy vào ví dụ để có kết quả lặp lại. Chương trình không phụ thuộc vào việc timezone mặc định của máy đang là UTC hay địa phương nào.

## 13. Quyết định API theo use case

### 13.1. Ngày sinh/khai báo hợp đồng

Input chỉ có ngày ISO:

~~~java
LocalDate birthDate = LocalDate.parse(
        input, DateTimeFormatter.ISO_LOCAL_DATE);
~~~

Cần STRICT, không nhận giờ hoặc zone không mong muốn, và có thể kiểm miền tuổi/ngày sau khi parse. `parseBest` không đem lại lợi ích khi schema chỉ chấp nhận một kiểu.

### 13.2. Bộ lọc ngày hoặc ngày giờ

Input có thể là:

~~~text
2024-02-29
2024-02-29T10:15
~~~

Dùng optional pattern và `parseBest` với `LocalDateTime::from` trước `LocalDate::from`. Sau đó phân nhánh: một ngày có thể đại diện **cả ngày** theo vùng của khách hàng, còn ngày-giờ là mốc đồng hồ cần được giải thích thêm nếu chưa có zone.

Không tự lấy đầu ngày UTC để biến cả ngày địa phương thành một instant khi nghiệp vụ chưa xác định.

### 13.3. API timestamp giữa microservices

Nếu giao ước bắt buộc offset:

~~~java
OffsetDateTime timestamp = OffsetDateTime.parse(
        input, DateTimeFormatter.ISO_OFFSET_DATE_TIME);
~~~

Nếu cần một instant tuyệt đối, dùng `Instant.parse` với ISO instant hoặc chuyển offset timestamp đã kiểm tra bằng `toInstant()`. Tránh parse qua LocalDateTime rồi bỏ offset.

### 13.4. Lịch sự kiện có vùng giờ

Input có thể gồm `LocalDateTime` và zone ID như `America/New_York`. Nên lưu ZoneId rõ ràng để quy tắc DST được áp dụng khi tính thời điểm. Nếu input chỉ có offset `-05:00`, nó không đại diện đầy đủ mọi quy tắc New York trong các mùa khác nhau.

Nếu thời gian rơi vào DST gap/overlap, cần xác định chính sách chọn hoặc từ chối. Parse thành ZonedDateTime không làm vấn đề này tự động biến mất theo nghiệp vụ.

## 14. Kiểm thử và tình huống biên

| Ca thử | Điều cần xác minh |
|---|---|
| Ngày nhuận 29/02/2024 với STRICT | Chấp nhận |
| Ngày 30/02/2024 với STRICT | DateTimeParseException |
| Ngày 30/02/2024 với SMART | Có thể điều chỉnh về ngày cuối tháng |
| Input chỉ có year-month | YearMonth hợp lệ, LocalDate thiếu trường |
| Input chỉ có ngày | parseBest chọn LocalDate |
| Input có ngày và giờ | parseBest chọn LocalDateTime khi xếp ưu tiên trước |
| Đổi thứ tự query | Có thể tạo một kiểu khác dù text giống nhau |
| parseBest chỉ một query | IllegalArgumentException |
| Input chỉ offset không region | zoneId() có thể null, zone() fallback offset |
| Query trường không có | Query tùy chọn null hoặc get(field) ném lỗi |
| Input có phần văn bản dư | parse(text) báo lỗi |
| Input có zone override từ formatter | Không suy ra zone có mặt trong text |
| SMART 24:00 không có ngày | 00:00 và excess P1D |
| Input tên tháng với locale | Chọn locale tường minh |
| ParseUnresolved tháng 0/ngày 65 | Không coi là dữ liệu hợp lệ đã resolve |
| LocalDateTime ở vùng có DST | Cần zone, chính sách gap/overlap |
| Dữ liệu nhập quá dài hoặc format mơ hồ | Validate độ dài, format và kiểu đích |

### 14.1. Test giá trị, không phụ thuộc class nội bộ

~~~java
LocalDateTime expected =
        LocalDateTime.of(2024, 2, 29, 10, 15);

LocalDateTime actual = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm")
        .withResolverStyle(ResolverStyle.STRICT)
        .parse("2024-02-29 10:15", LocalDateTime::from);

if (!expected.equals(actual)) {
    throw new AssertionError("Wrong parsed value");
}
~~~

Khi dùng `formatter.parse(text)`, implementation có thể trả một lớp nội bộ không có tên API ổn định; không test `getClass().getName()` của parsed raw. Với `parseBest`, nên kiểm `instanceof` những class công khai đã truyền vào query và so sánh nội dung.

### 14.2. Test không phụ thuộc môi trường

- Đặt ngày giờ đầu vào cố định, không dùng `now()` khi kiểm exact output.
- Với tên tháng, đặt `Locale` rõ ràng.
- Nếu cần kiểm zone, chọn `ZoneId` tường minh thay vì `systemDefault()`.
- Với dữ liệu nghiêm ngặt, set `ResolverStyle.STRICT`.
- Khi parse lỗi, kiểm loại exception và trạng thái được ghi nhận; không khóa test vào thông điệp tiếng Anh nguyên văn của JDK.

## 15. Các lỗi phổ biến cần tránh

**1. Nhầm parse(text) trả LocalDate.** Nó trả TemporalAccessor; dùng parse(text, LocalDate::from) khi cần ngày.

**2. Cast TemporalAccessor thành kiểu mong muốn.** Raw parsed không nhất thiết là kiểu đó, nên dùng query đúng.

**3. Coi parse thành công là đủ dữ liệu.** `2024-02` hợp lệ cho YearMonth nhưng thiếu ngày cho LocalDate.

**4. Đặt query nhỏ trước query lớn trong parseBest.** LocalDate có thể được chọn trước dù văn bản có cả giờ.

**5. Xem parseBest là cơ chế tự chọn kiểu tốt nhất.** Nó chỉ thử tuần tự theo ưu tiên đã khai báo.

**6. Coi ZonedDateTime luôn chứng minh có region trong text.** ZonedDateTime có thể tạo bằng ZoneOffset.

**7. Nhầm zoneId() và zone().** Query zone có fallback offset, zoneId không làm điều đó.

**8. Coi null query là parse thất bại.** Null có thể chỉ biểu thị field tùy chọn vắng mặt.

**9. Đọc get(field) không kiểm isSupported.** Field thiếu có thể ném lỗi.

**10. Dùng SMART cho dữ liệu cần strict.** Ngày không tồn tại có thể bị điều chỉnh.

**11. Nhầm uuuu và yyyy.** Year-of-era không phải proleptic year, nhất là khi STRICT.

**12. Cho rằng optional section tự tạo default.** Vắng giờ không tự cho LocalDateTime 00:00.

**13. Coi LocalDateTime thiếu zone là instant.** Cần ZoneId hoặc offset theo chính sách rõ.

**14. Dùng parseUnresolved như validation.** Nó chưa xử lý tính đúng của ngày.

**15. Dùng ParsePosition mà bỏ qua phần dư.** Partial parse khác full parse.

**16. Bỏ qua parsedExcessDays khi chấp nhận 24:00.** 00:00 có thể thuộc ngày tiếp theo.

**17. Cho rằng mọi formatter dùng một ResolverStyle mặc định.** ofPattern SMART, ISO_LOCAL_DATE STRICT.

**18. Không cố định locale.** Input có tên tháng có thể được parse khác giữa môi trường.

**19. Nhầm zone override với zone do user gửi.** withZone có thể thêm zone vào parse result.

**20. Không kiểm chính sách DST/miền nghiệp vụ sau parse.** Ngày giờ hợp lệ về trường vẫn có thể không phù hợp lịch hẹn.

## 16. Bài tập tự luyện

1. Với formatter `uuuu-MM-dd`, `parse("2024-02-29", LocalDate::from)` trả gì?
2. Tại sao `YearMonth::from` nhận `2024-02`, còn `LocalDate::from` không?
3. `parse(text)` trả kiểu khai báo gì?
4. So sánh `TemporalQueries.localDate()` và `LocalDate::from` khi thiếu ngày.
5. Vì sao thứ tự query trong `parseBest` quan trọng?
6. `parseBest` có được cung cấp duy nhất một query không?
7. Pattern `uuuu-MM-dd['T'HH:mm]` cho phép những dạng text nào?
8. Chỉ có chuỗi `2024-02-29T10:15+07:00` thì có biết vùng IANA không?
9. Tại sao `ZonedDateTime::from` vẫn có thể thành công khi đầu vào chỉ có offset?
10. `zoneId()` và `zone()` khác nhau thế nào?
11. Dùng ResolverStyle nào để từ chối `2024-02-30`?
12. Vì sao `uuuu` thường phù hợp hơn `yyyy` khi parse STRICT năm ISO?
13. Query nào lấy ngày, query nào lấy giờ, query nào lấy offset?
14. Với SMART, `24:00` không có ngày được giải quyết thế nào?
15. Vì sao `parseUnresolved` không dùng làm validation cuối cùng?
16. Khi parse chuỗi có trailing text bằng `parse(text)`, điều gì xảy ra?
17. Vì sao `withZone(UTC)` làm ta không thể tự khẳng định user nhập UTC dựa trên zone query?
18. Nêu một ví dụ nghiệp vụ nên dùng parseBest thay vì parse cố định.

**Gợi ý đáp án:** (1) LocalDate 2024-02-29. (2) Thiếu DAY_OF_MONTH. (3) TemporalAccessor. (4) Truy vấn tùy chọn trả null, phương thức from có thể ném DateTimeException. (5) Chọn query thành công đầu tiên, có thể mất trường. (6) Không, ít nhất hai query. (7) Ngày thuần và ngày kèm T HH:mm. (8) Không, chỉ có offset. (9) ZoneOffset cũng có thể dùng làm ZoneId. (10) zone có fallback offset, zoneId nghiêm ngặt. (11) STRICT. (12) uuuu là proleptic year. (13) localDate, localTime, offset. (14) LocalTime 00:00 và excess P1D. (15) Field chưa được resolve. (16) DateTimeParseException. (17) Zone có thể đến từ formatter. (18) Một trường cho phép ngày hoặc ngày kèm giờ.

## Tóm tắt

`parse(text)` trả `TemporalAccessor`; `parse(text, query)` trả đối tượng typed; `parseBest` thử **ít nhất hai query theo thứ tự ưu tiên** và rất hữu ích khi pattern có phần tùy chọn. `TemporalQueries` cho phép hỏi ngày/giờ/offset/zone và có thể trả null khi thiếu. `ResolverStyle` điều khiển cách giải quyết dữ liệu, vì vậy cần chọn STRICT khi đầu vào không được tự sửa. **Không nhầm offset với ZoneId vùng, không nhầm parse thành công với validation nghiệp vụ, và không dùng parser cũ khi bộ `java.time` hiện hành đã đáp ứng yêu cầu.**

### Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — DateTimeFormatter: parse, parseBest, parsedExcessDays](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 26 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
- [Oracle Java SE 26 — ResolverStyle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle Java SE 26 — TemporalAccessor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAccessor.html)
- [Oracle Java SE 26 — TemporalQuery](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalQuery.html)
- [Oracle Java SE 26 — TemporalQueries](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalQueries.html)
- [Oracle Java SE 26 — ChronoField](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoField.html)
