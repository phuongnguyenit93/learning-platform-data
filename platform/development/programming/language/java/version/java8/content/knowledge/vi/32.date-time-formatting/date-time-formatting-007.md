# DateTimeFormatterBuilder và phần tùy chọn trong Java

## 1. Mục tiêu và bài toán cần giải quyết

Trong Java hiện đại, `java.time.format.DateTimeFormatter` là đối tượng chịu trách nhiệm **chuyển các giá trị ngày giờ thành văn bản (format)** và **phân tích văn bản thành dữ liệu ngày giờ (parse)**. Khi định dạng rất đơn giản, `DateTimeFormatter.ofPattern("uuuu-MM-dd")` là đủ. Nhưng giao tiếp với người dùng, API hoặc dữ liệu cũ thường có **nhiều thành phần không bắt buộc**:

- Có thể nhập **chỉ ngày**: `2026-04-05`.
- Có thể nhập **ngày và giờ**: `2026-04-05T09:07`.
- Có thể kèm **giây**: `2026-04-05T09:07:05`.
- Có thể kèm **phần giây**: `2026-04-05T09:07:05.1200`.
- Có thể có **UTC offset**: `2026-04-05T09:07+07:00`, hoặc không có offset.
- Có thể kèm **ZoneId khu vực** để áp dụng quy tắc múi giờ.
- Có thể cần **giá trị mặc định** cho những trường chưa được nhập.

Đây là lúc **`DateTimeFormatterBuilder`** phát huy tác dụng. Builder cho phép ghép từng thành phần định dạng theo thứ tự, mở/đóng **phần tùy chọn** bằng `optionalStart()`/`optionalEnd()`, thêm một formatter con tùy chọn bằng `appendOptional(...)`, đặt các trường mặc định khi parse qua `parseDefaulting(...)`, cấu hình cách parse chữ hoa/thường và cách kiểm tra dữ liệu.

Bài học này giải thích đầy đủ các điểm cần dùng của **“DateTimeFormatterBuilder và phần tùy chọn”** thuộc nhóm **“Định dạng ngày giờ”**, đặc biệt là **sự khác biệt giữa việc không có dữ liệu và dữ liệu có giá trị 0**, giải quyết ngày hợp lệ, thành phần tùy chọn lồng nhau, offset và parser nhiều dạng. Toàn bộ API được nêu vẫn được hỗ trợ trong Java hiện đại, không dựa vào `SimpleDateFormat`, `java.util.Date` hoặc cách làm legacy. Chương trình hoàn chỉnh dùng **Java 17+**.

Sau bài, bạn có thể tự thiết kế một formatter hỗ trợ nhiều dạng ngày giờ mà vẫn kiểm soát được **độ chặt chẽ, kiểu đầu ra và dữ liệu thiếu**.

## 2. Các khái niệm phải phân biệt

`DateTimeFormatterBuilder` là **đối tượng xây dựng mutable**; bạn gọi các phương thức trên cùng builder để thêm quy tắc theo thứ tự. Kết quả của `toFormatter()` là một **`DateTimeFormatter` immutable, thread-safe**, phù hợp tái sử dụng giữa các request/thread.

Hình dung một cấu trúc như sau:

```text
DateTimeFormatterBuilder (mutable, đang ghép quy tắc)
  |
  |-- năm-tháng-ngày (bắt buộc)
  |
  |-- [ bắt đầu khối tùy chọn
  |      chữ 'T' + giờ:phút
  |      [ bắt đầu khối tùy chọn lồng
  |          ':' + giây + phần nano (có thể có/không)
  |      ] kết thúc
  |   ] kết thúc
  |
  v
toFormatter(Locale.ROOT)
  |
  v
DateTimeFormatter (immutable, thread-safe, dùng parse/format)
```

Các thuật ngữ:

| Thuật ngữ | Nghĩa |
| --- | --- |
| Printer | Quy tắc **in** một trường từ `TemporalAccessor` thành chuỗi |
| Parser | Quy tắc **đọc** một phần chuỗi thành các trường ngày giờ |
| Optional section | Một **nhóm thành phần** có thể vắng mặt khi parse, hoặc bị bỏ khỏi output khi không đủ trường dữ liệu để in |
| Nested optional | Một nhóm tùy chọn nằm bên trong nhóm tùy chọn khác |
| Resolver | Bước **giải quyết/kiểm tra** các trường đã parse thành ngày giờ có ý nghĩa, ví dụ ngày 29/2 |
| `TemporalAccessor` | Giao diện truy cập các trường temporal; một kết quả parse có thể chứa ngày, giờ, offset hoặc zone tùy chuỗi |
| `parseBest` | Thử nhiều cách chuyển parsed temporal thành loại có ý nghĩa, theo **thứ tự ưu tiên** được đưa vào |

**Cực kỳ quan trọng:** “Tùy chọn” không đồng nghĩa “giá trị nào bằng 0 thì bỏ”. Nó phụ thuộc vào **khả năng lấy dữ liệu của temporal khi format**, và vào **sự hiện diện của đoạn văn bản phù hợp khi parse**.

## 3. Các phương thức then chốt của builder

| Phương thức | Vai trò |
| --- | --- |
| `appendPattern(String)` | Thêm pattern theo ký hiệu DateTimeFormatter |
| `appendLiteral(char/String)` | Thêm ký tự hoặc chuỗi **cố định** |
| `append(DateTimeFormatter)` | Ghép toàn bộ formatter con như **phần bắt buộc** |
| `optionalStart()` | Bắt đầu một nhóm tùy chọn, có thể lồng nhóm khác |
| `optionalEnd()` | Kết thúc nhóm tùy chọn gần nhất |
| `appendOptional(DateTimeFormatter)` | Ghép **toàn bộ formatter con như một nhóm tùy chọn** |
| `appendFraction(field,min,max,decimalPoint)` | In/parse phần thập phân của trường, ví dụ nano giây |
| `parseDefaulting(field,value)` | Gán giá trị trường **chưa có** trong quá trình parse, không tác động format |
| `parseCaseInsensitive()` | Chuyển parser sang so khớp văn bản không phân biệt hoa/thường |
| `parseCaseSensitive()` | Bật lại phân biệt hoa/thường từ điểm đó |
| `parseStrict()` / `parseLenient()` | Điều chỉnh việc **khớp ký tự/độ rộng** trong giai đoạn parse |
| `toFormatter(Locale)` | Hoàn thành builder và tạo immutable DateTimeFormatter với locale rõ ràng |
| `withResolverStyle(ResolverStyle)` | Trên formatter, chọn cách **giải quyết ngày giờ** đã parse |

Một builder thường nên được dùng để **xây một lần** trong khởi tạo class hoặc factory, sau đó chia sẻ đối tượng `DateTimeFormatter`. Không chia sẻ một builder mutable đang được nhiều thread tiếp tục sửa.

### 3.1. Builder không tự biết bạn muốn kiểu kết quả nào

`DateTimeFormatter.parse(text)` trả một `TemporalAccessor`. Chuỗi chỉ có ngày **không thể tự biến thành `LocalDateTime`** nếu không có dữ liệu giờ hoặc mặc định giờ; chuỗi có offset cần kiểu như `OffsetDateTime` nếu muốn giữ offset. Bạn có thể:

- Gọi `LocalDate.parse(text,formatter)` nếu chỉ cần ngày.
- Gọi `LocalDateTime.parse(text,formatter)` nếu đã đủ ngày/giờ.
- Gọi `OffsetDateTime.parse(text,formatter)` nếu chuỗi đã chứa offset cần thiết.
- Gọi `formatter.parseBest(text, OffsetDateTime::from, LocalDateTime::from)` để phân nhánh theo dữ liệu thật.
- Dùng `parseDefaulting` nếu quy định nghiệp vụ cho phép bổ sung giờ/phút/giây thiếu.

Không lấy chuỗi thiếu offset rồi tự coi là UTC chỉ vì mục tiêu cuối cùng cần một `Instant`. Phải có quy tắc chọn `ZoneId`/`ZoneOffset` từ nguồn đáng tin hoặc từ business requirement.

## 4. `optionalStart()` và `optionalEnd()`: mở/đóng một nhóm

Cú pháp cốt lõi:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .optionalStart()
            .appendLiteral('T')
            .appendPattern("HH:mm")
        .optionalEnd()
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Đây là một đoạn Java trong method đã import `java.time.format.*` và `java.util.Locale`. Nó mô tả:

```text
uuuu-MM-dd[THH:mm]
```

Dấu ngoặc vuông trong sơ đồ có nghĩa **nhóm `T` + `HH:mm` cùng tùy chọn**. Không đặt `T` ở ngoài:

```java
// Không nên nếu muốn date-only được chấp nhận:
new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .appendLiteral('T') // T bị bắt buộc!
        .optionalStart().appendPattern("HH:mm").optionalEnd();
```

Đoạn trên là **anti-pattern minh họa**. Nếu ký tự `T` được yêu cầu ngay cả khi không có giờ, chuỗi chỉ ngày sẽ không khớp parser. Khi format `LocalDate`, printer có thể tạo một chữ `T` không có giờ theo sau; đó là dữ liệu xuất sai hợp đồng.

### 4.1. Khi parse, nhóm tùy chọn có thể vắng mặt hoàn toàn

Với formatter ở trên:

- `2026-04-05` → parse thành giá trị ngày.
- `2026-04-05T09:07` → parse thành ngày + giờ.
- `2026-04-05T09:` → **không hoàn chỉnh**; không nên chấp nhận như dữ liệu hợp lệ.

Ở trường hợp thứ ba, phần parser tùy chọn có thể thử và **quay lui** khi không đủ trường. Nhưng những ký tự `T09:` vẫn còn thừa so với văn bản cần được parse toàn bộ, vì vậy lời gọi parse chuẩn vẫn báo `DateTimeParseException`. **Optional không có nghĩa parser tự bỏ qua một suffix sai bất kỳ.**

### 4.2. Khi format, nhóm tùy chọn được in nếu đủ trường

Với `LocalDate.of(2026,4,5)`, temporal không có `HOUR_OF_DAY` và `MINUTE_OF_HOUR`; nhóm giờ bị bỏ, output chỉ có ngày. Với `LocalDateTime` đủ các trường, nhóm giờ được in. `DateTimeFormatter` không bắt người dùng tạo một formatter riêng cho hai đối tượng này nếu cấu trúc tùy chọn đáp ứng yêu cầu.

Tuy nhiên, việc optional được in **không dựa trên việc một trường bằng 0**. `LocalDateTime.of(2026,4,5,9,7,0)` có trường `SECOND_OF_MINUTE` bằng `0` và vẫn có thể in `:00` nếu bạn đưa giây vào optional section, vì trường giây **có mặt**.

**Khác biệt cần nhớ:** một trường có giá trị 0 là **dữ liệu hiện diện**; một trường không được hỗ trợ trong `TemporalAccessor` là **dữ liệu không tồn tại**.

## 5. Các nhóm tùy chọn lồng nhau: ngày, giờ, giây, nano

Ví dụ formatter linh hoạt có cấu trúc:

```text
Ngày (bắt buộc)
└── [T + giờ:phút]
    └── [:giây + phần nano]
```

Cài đặt:

```java
DateTimeFormatter flexible = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .optionalStart()
            .appendLiteral('T')
            .appendPattern("HH:mm")
            .optionalStart()
                .appendLiteral(':')
                .appendPattern("ss")
                .appendFraction(ChronoField.NANO_OF_SECOND, 0, 9, true)
            .optionalEnd()
        .optionalEnd()
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Cần `import java.time.format.*;`, `import java.time.temporal.ChronoField;` và `import java.util.Locale;`. Formatter này đọc được:

```text
2026-04-05
2026-04-05T09:07
2026-04-05T09:07:05
2026-04-05T09:07:05.1200
```

Vì `optionalStart` mở theo **ngăn xếp**, nhóm `:ss` chỉ có thể xuất hiện khi nhóm ngoài `T + HH:mm` có mặt. Không nên tạo một optional giây độc lập bên ngoài phần giờ nếu định dạng không cho phép kiểu `ngày:ss`.

### 5.1. Vì sao khi format có thể xuất hiện `:00` dù input bỏ giây?

Giả sử đã parse `2026-04-05T09:07` thành `LocalDateTime`. Kiểu này luôn có thành phần giây, mặc định bằng 0 sau khi parse giờ/phút. Khi format lại bằng formatter trên:

```text
2026-04-05T09:07:00
```

**Không phải bug.** Khi format, builder hỏi temporal có trường giây không; LocalDateTime **có**. Nó không lưu metadata rằng “trong chuỗi gốc người dùng không nhập giây”. Do đó phần `:ss` được in, mặc dù giây bằng 0.

Nếu yêu cầu **tái tạo đúng nguyên văn input** (giữ việc người dùng có/không nhập giây), chỉ lưu `LocalDateTime` là **không đủ thông tin**. Hãy lưu thêm trạng thái độ chính xác/mẫu ban đầu hoặc duy trì raw input đã được validate.

### 5.2. Nếu giây hoặc nano không được cung cấp thì sao?

Khi parse `HH:mm` thành LocalDateTime, Java có thể giải quyết giây bằng 0; điều này khác với `parseDefaulting` được sử dụng để biến **date-only** thành LocalDateTime ở mục 7. Khi parse date-only, thiếu cả giờ/phút nên không thể gọi `LocalDateTime.from(...)` nếu không có default.

## 6. `appendFraction`: phần nano tùy chọn và độ chính xác

Signature thường dùng:

```java
builder.appendFraction(
        ChronoField.NANO_OF_SECOND, minWidth, maxWidth, decimalPoint);
```

Các tham số:

- `ChronoField.NANO_OF_SECOND`: phần nano trong giây.
- `minWidth`: số chữ số phần thập phân ít nhất có thể in/parse.
- `maxWidth`: số chữ số phần thập phân nhiều nhất.
- `decimalPoint=true`: tự thêm dấu thập phân của DecimalStyle khi có phần cần in; không phải tự viết một dấu chấm riêng.
- `decimalPoint=false`: không tự thêm dấu thập phân; nếu cần separator thì phải ghép hợp lý ở builder.

Với `appendFraction(NANO_OF_SECOND, 0, 9, true)` và dữ liệu 120.000.000 nano giây:

```java
LocalDateTime t = LocalDateTime.of(
        2026, 4, 5, 9, 7, 5, 120_000_000);
String output = flexible.format(t);
// 2026-04-05T09:07:05.12
```

**Vì sao không còn `00` cuối?** Formatter in **số chữ số vừa đủ** trong giới hạn min/max; trailing zero của phần nano được lược bỏ khi không bắt buộc. Khi parse lại, `.12` có nghĩa `120_000_000` nano giây, nên **giá trị thời gian được giữ**, dù chuỗi hiển thị khác chuỗi gốc `.1200`.

### 6.1. Không nhầm “độ dài phần thập phân” với “làm tròn”

Theo hợp đồng `appendFraction`, khi `maxWidth` ít hơn precision của temporal, phần chữ số vượt quá có thể bị **bỏ**, **không làm tròn**. Ví dụ muốn chỉ ba chữ số milliseconds, bạn cần xác định liệu nghiệp vụ muốn **cắt** hay **round** và xử lý chủ động trước khi format.

Nếu dùng:

```java
.appendFraction(ChronoField.NANO_OF_SECOND, 3, 3, true)
```

thì bạn yêu cầu **đúng 3 chữ số phần giây**. `.1` chưa đủ 3 chữ số cho parser strict. Nếu muốn chấp nhận cả `.1`, `.12` và `.123`, chọn dải min/max tương ứng.

### 6.2. Khi nano bằng 0

Với `minWidth=0`, một nano-of-second bằng 0 có thể **không tạo phần thập phân nào**. Với `minWidth=1`, formatter có thể in tối thiểu một chữ số zero. Điều này khác optional section có chứa `:ss`: giây có giá trị 0 nhưng vẫn **được in**, nếu pattern yêu cầu.

**Không nhét dấu chấm vào trước appendFraction** khi đã dùng `decimalPoint=true`; nếu không, bạn có thể tạo hai dấu chấm hoặc dấu chấm treo khi phần thập phân được bỏ.

## 7. `parseDefaulting`: bổ sung trường thiếu khi parse

Dạng API:

```java
DateTimeFormatterBuilder.parseDefaulting(TemporalField field, long value)
```

Nó **không format thêm dữ liệu**, mà khi parse sẽ **tiêm ngay** một giá trị vào parsed state nếu trường đó **chưa có**. Nó đặc biệt hữu ích khi dữ liệu đầu vào có optional date/time nhưng ứng dụng muốn luôn nhận một `LocalDateTime`.

Ví dụ: date-only được hiểu là **00:00:00** theo chính sách rõ ràng:

```java
DateTimeFormatter defaulted = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .optionalStart()
            .appendLiteral('T')
            .appendPattern("HH:mm")
        .optionalEnd()
        .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
        .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
        .parseDefaulting(ChronoField.SECOND_OF_MINUTE, 0)
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDateTime a = LocalDateTime.parse("2026-04-05", defaulted);
// 2026-04-05T00:00

LocalDateTime b = LocalDateTime.parse("2026-04-05T09:07", defaulted);
// 2026-04-05T09:07
```

Cả hai là `LocalDateTime` vì sau parse đã có đủ năm/tháng/ngày/giờ/phút/giây.

### 7.1. Đặt `parseDefaulting` sau optional

Theo tài liệu Oracle, việc tiêm giá trị là **ngay lúc parser chạy**, và trường đã tiêm sẽ được nhìn thấy bởi các thành phần parser **sau** nó. Vì thế nên đặt `parseDefaulting` **ở cuối builder**, sau những thành phần có thể thực sự mang trường đó từ chuỗi.

Nếu đặt mặc định `HOUR_OF_DAY=0` quá sớm rồi parser sau đó gặp `HH=09`, bạn có thể tạo xung đột giá trị hoặc dữ liệu bị từ chối. `parseDefaulting` không có nghĩa “để giá trị người dùng luôn ghi đè default bất kể thứ tự”; thứ tự trong builder rất quan trọng.

### 7.2. Khi field đã có, default không ghi đè

Nếu đầu vào là `2026-04-05T09:07`, `HOUR_OF_DAY` đã có giá trị 9 và `MINUTE_OF_HOUR` là 7. Default của hai field này **không thay thế** các giá trị đã parse. Default của giây bằng 0 chỉ bổ sung trường chưa có.

**Bẫy dữ liệu:** Chọn `00:00` làm default là **quy tắc nghiệp vụ**, không phải một phép toán trung lập. Với lịch giao dịch, date-only đôi khi phải hiểu là **toàn bộ ngày** chứ không phải “bắt đầu ngày lúc 00:00”. Nếu hệ thống cần một khoảng ngày, hãy biểu diễn bằng `LocalDate` và các biên ngày phù hợp, không tự ép thành một thời điểm 00:00 không có ZoneId.

### 7.3. Default không được dùng để che input lỗi

`parseDefaulting` chỉ bổ sung trường thiếu, không sửa năm/tháng/ngày không hợp lệ. `2025-02-29` vẫn phải bị từ chối khi dùng `ResolverStyle.STRICT`, dù bạn đã tiêm thêm giờ 00:00.

Đừng mặc định offset `UTC` cho chuỗi không có zone/offset nếu nguồn chỉ ghi giờ địa phương. Việc đó thay đổi **ý nghĩa timestamp** và có thể gây lỗi khi so sánh sự kiện ở nhiều địa điểm.

## 8. `appendOptional(DateTimeFormatter)`: ghép formatter con tùy chọn

Nếu đã có một formatter con độc lập, bạn không cần viết lại toàn bộ quy tắc trong builder cha.

Ví dụ formatter giờ có offset **không bắt buộc**:

```java
DateTimeFormatter offsetPart = new DateTimeFormatterBuilder()
        .appendOffsetId()
        .toFormatter();

DateTimeFormatter dateTimeOptionalOffset =
        new DateTimeFormatterBuilder()
            .appendPattern("uuuu-MM-dd'T'HH:mm")
            .appendOptional(offsetPart)
            .toFormatter(Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);
```

`appendOptional(offsetPart)` về hiệu quả tương đương:

```java
.optionalStart()
    .append(offsetPart)
.optionalEnd()
```

Cách sử dụng:

```java
TemporalAccessor noOffset = dateTimeOptionalOffset.parseBest(
        "2026-04-05T09:07",
        OffsetDateTime::from,
        LocalDateTime::from);
// Một LocalDateTime.

TemporalAccessor withOffset = dateTimeOptionalOffset.parseBest(
        "2026-04-05T09:07+07:00",
        OffsetDateTime::from,
        LocalDateTime::from);
// Một OffsetDateTime.
```

Với `OffsetDateTime`, bạn giữ được UTC offset; với `LocalDateTime`, chuỗi không có offset vẫn chỉ là ngày giờ cục bộ. Không ép mọi chuỗi vào `OffsetDateTime` bằng cách đoán offset nếu hợp đồng nguồn không xác định vùng.

### 8.1. Format với và không có offset

```java
OffsetDateTime odt = OffsetDateTime.of(
        2026, 4, 5, 9, 7, 0, 0, ZoneOffset.ofHours(7));

String formattedWith = dateTimeOptionalOffset.format(odt);
// 2026-04-05T09:07+07:00

String formattedWithout = dateTimeOptionalOffset.format(
        LocalDateTime.of(2026, 4, 5, 9, 7));
// 2026-04-05T09:07
```

Đây là một ưu điểm của nhóm optional khi format: nếu temporal không có `OFFSET_SECONDS`, phần offset được bỏ đi. Nhưng với `OffsetDateTime` có `ZoneOffset.UTC`, offset **hiện diện** và `appendOffsetId()` in `Z`, chứ không “bỏ vì offset bằng zero”.

### 8.2. Không dùng appendOptional như “thử vô hạn các định dạng”

`appendOptional(formatter)` phù hợp khi một phần của **cùng cấu trúc chuỗi** có thể vắng. Nó không phải cơ chế tự nhận mọi kiểu ngày giờ mơ hồ.

Nếu hệ thống nhận cả `dd/MM/uuuu` và `uuuu-MM-dd`, có thể cần hai formatter xác định và một tầng chọn định dạng/parse theo quy tắc. Cố ghép hai cấu trúc hoàn toàn khác nhau thành hai optional độc lập có thể tạo trường hợp cả hai bị bỏ hoặc chỉ parse một phần nhưng vẫn còn ký tự thừa.

## 9. Pattern dấu ngoặc vuông tương đương tùy chọn builder

`DateTimeFormatter.ofPattern(...)` hỗ trợ `[` và `]` để biểu diễn optional sections. Về ý nghĩa, chúng tương đương với `optionalStart()` và `optionalEnd()` trong `DateTimeFormatterBuilder`.

Ví dụ:

```java
DateTimeFormatter byPattern = DateTimeFormatter
        .ofPattern("uuuu-MM-dd['T'HH:mm[:ss]]", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Nó hỗ trợ date-only, ngày + giờ:phút, và ngày + giờ:phút:giây. So với builder:

```java
DateTimeFormatter byBuilder = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .optionalStart()
            .appendLiteral('T')
            .appendPattern("HH:mm")
            .optionalStart()
                .appendLiteral(':')
                .appendPattern("ss")
            .optionalEnd()
        .optionalEnd()
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

**Khi nào dùng cách nào?**

- Pattern ngắn, dễ nhìn và ít yêu cầu khác → `ofPattern` có `[...]`.
- Cần `parseDefaulting`, `appendOptional` formatter con, `appendFraction` với min/max khác nhau, parse case-insensitive theo từng đoạn, custom offset/zone parser → `DateTimeFormatterBuilder` rõ ràng và linh hoạt hơn.

**Lưu ý kỹ thuật:** Mỗi chữ trong pattern có ý nghĩa riêng. `T` không phải pattern letter được chỉ định thông thường, nên viết `'T'` để in/parse một chữ T cố định. Không chèn các chữ cái literal chưa được quote tùy tiện; chúng có thể trở thành ký hiệu pattern trong các phiên bản API.

## 10. `parseBest`: lấy kiểu kết quả giàu thông tin nhất

Khi formatter có optional, kết quả parse có thể giàu hoặc nghèo trường. Một cách làm rõ ràng:

```java
TemporalAccessor parsed = flexible.parseBest(
        input,
        LocalDateTime::from,
        LocalDate::from);
```

Nếu chuỗi có giờ, `LocalDateTime::from` thành công; nếu chỉ ngày, `LocalDateTime::from` không thể lấy giờ, và parser thử `LocalDate::from`.

Với offset:

```java
TemporalAccessor parsed = dateTimeOptionalOffset.parseBest(
        input,
        OffsetDateTime::from,
        LocalDateTime::from);
```

**Thứ tự truy vấn rất quan trọng.** `LocalDateTime.from(OffsetDateTime)` có thể thành công, vì OffsetDateTime cũng chứa trường ngày và giờ. Nếu hỏi `LocalDateTime` trước, bạn có thể **vô tình bỏ mất offset**, dù input thực sự chứa offset.

Vì vậy, hỏi kết quả **giàu thông tin hơn trước**:

```text
OffsetDateTime -> LocalDateTime
ZonedDateTime  -> OffsetDateTime -> LocalDateTime
LocalDateTime  -> LocalDate
```

Sơ đồ thứ tự là gợi ý theo cấu trúc dữ liệu đang được parse; không có nghĩa luôn phải yêu cầu đủ bốn loại cho mọi formatter.

### 10.1. Không tự giả định TemporalAccessor là LocalDateTime

`formatter.parse(text)` trả `TemporalAccessor` đã được giải quyết theo formatter, nhưng nó không cam kết một concrete class public như `LocalDateTime`. Không ép kiểu:

```java
// Anti-pattern: không làm như sau.
LocalDateTime x = (LocalDateTime) formatter.parse(text);
```

Đoạn này là ví dụ sai. Dùng `LocalDateTime.from(parsed)`, `LocalDateTime.parse(text, formatter)` hoặc `parseBest`.

### 10.2. Kiểm tra thành phần có hay không

Khi cần biết một trường có mặt:

```java
TemporalAccessor fields = formatter.parse(text);

boolean hasOffset = fields.isSupported(ChronoField.OFFSET_SECONDS);
ZoneId zone = fields.query(TemporalQueries.zone());
```

Đoạn này cần import `java.time.temporal.*`. `zone` có thể là null khi parse không có dữ liệu zone, và `hasOffset` có thể false. Cần hiểu khác nhau giữa offset và ZoneId khu vực: `ZoneOffset` cũng là một `ZoneId`, nhưng không có đầy đủ quy tắc của vùng địa lý.

Nếu đã dùng `parseDefaulting(OFFSET_SECONDS,0)`, trường offset sẽ **được tạo mặc định** và phép `isSupported` không còn phân biệt input có viết offset thật hay không. Muốn ghi nhận sự hiện diện nguyên văn, cần thiết kế thêm metadata đầu vào hoặc parser riêng.

## 11. Phần ZoneId tùy chọn trong ngoặc vuông

Nếu giao thức chấp nhận chuỗi có **region zone** trong ngoặc vuông:

```text
2026-04-05T09:07
2026-04-05T09:07[Asia/Ho_Chi_Minh]
```

có thể dùng:

```java
DateTimeFormatter zoned = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd'T'HH:mm")
        .optionalStart()
            .appendLiteral('[')
            .appendZoneRegionId()
            .appendLiteral(']')
        .optionalEnd()
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Khi parse dạng có region ID:

```java
ZonedDateTime value = ZonedDateTime.parse(
        "2026-04-05T09:07[Asia/Ho_Chi_Minh]", zoned);
// 2026-04-05T09:07+07:00[Asia/Ho_Chi_Minh]
```

Khi format `LocalDateTime` không có zone, phần trong ngoặc được bỏ. Khi format một `ZonedDateTime` có `ZoneId` khu vực, nó có thể được in:

```text
2026-04-05T09:07[Asia/Ho_Chi_Minh]
```

**Chọn đúng thành phần zone:**

- `appendZoneRegionId()` yêu cầu region-style ZoneId; không phải formatter tổng quát cho mọi offset ID.
- `appendZoneId()` có thể làm việc với zone ID hoặc offset ID theo quy tắc API.
- `appendZoneOrOffsetId()` chọn zone hoặc offset ID có sẵn phù hợp cho cấu trúc cần thiết.
- `appendOffsetId()` dành cho **UTC offset** như `+07:00` hoặc `Z`.

**Đừng đồng nhất zone với offset.** `America/New_York` có quy tắc DST, trong khi `-05:00` là offset cố định. Khi parse một lịch hẹn tương lai, một zone region thường quan trọng hơn chụp offset của hiện tại.

### 11.1. Gap và overlap không được xóa bỏ bởi optional

Một chuỗi với `LocalDateTime` và `ZoneId` có thể rơi vào **DST gap** (giờ không tồn tại) hoặc **overlap** (giờ lặp lại). Các phương thức chuyển sang `ZonedDateTime` có chính sách giải mặc định; với lịch giao dịch hoặc hẹn giờ cần chính xác, xác thực `ZoneRules.getValidOffsets(localDateTime)` và áp chính sách nghiệp vụ.

Optional zone chỉ nói **có hoặc không có phần chuỗi zone**, không nói rằng mọi local time đều hợp lệ/duy nhất ở zone đó.

## 12. Parse case-insensitive và văn bản ngày tháng theo Locale

Nếu dữ liệu đầu vào có tên tháng kiểu tiếng Anh:

```text
05 Mar 2026
05 mAr 2026
05 MAR 2026
```

thì parser có thể hỗ trợ các biến thể chữ hoa/thường:

```java
DateTimeFormatter english = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("dd MMM uuuu")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate value = LocalDate.parse("05 mAr 2026", english);
// 2026-03-05
```

Khi format cùng object, kết quả theo Locale.ENGLISH thường là:

```text
05 Mar 2026
```

**`parseCaseInsensitive()` áp dụng cho parser từ vị trí được bật về sau.** Nó không có nghĩa output format sẽ dùng chữ thường. Nếu muốn bật trở lại chế độ phân biệt hoa/thường sau một phần, gọi `parseCaseSensitive()` ở vị trí tương ứng.

Đối với dữ liệu có ngôn ngữ khác, chọn `Locale` rõ ràng thay vì dựa vào default locale của máy chủ. Case-insensitive **không đồng nghĩa** bỏ dấu tiếng Việt, dịch tên tháng, hoặc chấp nhận mọi loại Unicode tương đương.

### 12.1. Builder mặc định và locale

`new DateTimeFormatterBuilder().toFormatter()` sử dụng **default FORMAT locale**. Nếu ứng dụng cần log, file, API ổn định giữa môi trường, nên dùng `toFormatter(Locale.ROOT)` cho dữ liệu số đơn giản hoặc locale xác định cho tên tháng/ngày.

Không hardcode chữ tháng tiếng Anh mà quên cấu hình `Locale.ENGLISH`. Một sự khác biệt locale có thể làm output và parse thay đổi mà không phải lỗi logic của builder.

### 12.2. Parse lenient khác ResolverStyle.LENIENT

Có hai giai đoạn khác nhau:

1. **Lexical parse:** ký tự, chữ hoa/thường, dấu phân cách, số chữ số… chịu ảnh hưởng `parseStrict()/parseLenient()`.
2. **Resolution:** giải quyết năm/tháng/ngày và xác thực quy tắc lịch; chịu ảnh hưởng `withResolverStyle(STRICT/SMART/LENIENT)`.

`parseLenient()` **không tương đương** `withResolverStyle(ResolverStyle.LENIENT)`. Và ngược lại, `withResolverStyle(STRICT)` không mặc nhiên ép mọi pattern thành dạng ký tự duy nhất nếu bạn đã cho phép parser lenient.

Với input là ngày giờ quan trọng (đặt lịch, giao dịch), nên lựa chọn chính sách xác thực minh bạch. Không bật lenient chỉ để dữ liệu xấu “đi qua”.

## 13. `ResolverStyle.STRICT` và `SMART`: ví dụ năm không nhuận

Một chi tiết quan trọng: formatter tạo qua `DateTimeFormatterBuilder.toFormatter()` mặc định có **ResolverStyle.SMART**. `SMART` có thể điều chỉnh một số ngày không tồn tại tới ngày cuối tháng phù hợp.

Ví dụ:

```java
DateTimeFormatter smart = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .toFormatter(Locale.ROOT);

LocalDate parsed = LocalDate.parse("2025-02-29", smart);
// 2025-02-28 (SMART tự điều chỉnh)
```

Nếu muốn từ chối ngày 29/2 của năm không nhuận:

```java
DateTimeFormatter strict =
        smart.withResolverStyle(ResolverStyle.STRICT);

LocalDate.parse("2025-02-29", strict);
// DateTimeParseException
```

Trong ví dụ, năm 2025 không nhuận. **Tuy nhiên, `ResolverStyle.SMART` không biến mọi input ngoài phạm vi thành hợp lệ**; nó chỉ có hành vi chỉnh ngày trong những trường hợp cụ thể theo hợp đồng JDK.

### 13.1. Vì sao nên dùng `uuuu` thay vì `yyyy` khi parse STRICT?

Pattern:

- `uuuu` → **proleptic year**, dùng được với ISO và không cần field ERA tách biệt.
- `yyyy` → **year-of-era**, tức năm trong một kỷ nguyên (BCE/CE), có thể cần thông tin ERA để resolve nghiêm ngặt.
- `YYYY` → **week-based-year**, không phải calendar year và có thể khác quanh ranh giới năm.

Khi parse ngày ISO theo `ResolverStyle.STRICT` với `yyyy-MM-dd` nhưng không có ERA, dữ liệu có thể không resolve thành `LocalDate` như bạn mong muốn. Dùng `uuuu-MM-dd` khi đầu vào là năm proleptic của ISO.

Không đánh đồng `yyyy` và `uuuu` chỉ vì cả hai thường in giống nhau đối với ngày hiện đại.

## 14. Đọc/ghi có phần tùy chọn: các nguyên tắc quan trọng

### 14.1. Có optional không có nghĩa format và parse đối xứng về nguyên văn

Một input:

```text
2026-04-05T09:07
```

khi parse thành `LocalDateTime` rồi format lại bằng builder có giây tùy chọn, có thể ra:

```text
2026-04-05T09:07:00
```

Hai chuỗi khác nhau nhưng **diễn đạt cùng giá trị thời gian**, nếu chính sách cho phép bỏ giây khi parse. Với nano, input `.1200` có thể format thành `.12`. **Đừng đặt mục tiêu “raw string round-trip exact”** nếu không bảo toàn metadata về thành phần hiện diện và số chữ số ban đầu.

**Round-trip quan trọng cho dữ liệu thời gian thường là so giá trị** bằng `equals` hoặc so phần field/Instant cần thiết.

### 14.2. Khi nào nên tách parser và printer?

Nếu yêu cầu parse chấp nhận nhiều kiểu linh hoạt nhưng output luôn theo **một format chuẩn**, nên dùng:

- **Flexible input formatter:** nhiều optional, case-insensitive khi cần, nhưng STRICT resolution.
- **Canonical output formatter:** một pattern cố định theo contract, ví dụ ISO_INSTANT hoặc chuẩn JSON/API của ứng dụng.

Không bắt một formatter phải “giữ nguyên cách người dùng nhập” khi TemporalAccessor không lưu thông tin đó.

### 14.3. Cấm dữ liệu thiếu nhưng vẫn cho optional thành phần khác

Một trường dữ liệu **bắt buộc theo business rule** phải nằm ngoài optional section. Ví dụ endpoint yêu cầu luôn có giờ:phút nhưng chấp nhận giây tùy chọn, hãy đặt `HH:mm` ngoài phần tùy chọn, chỉ bọc `:ss`. Nếu bọc cả giờ trong optional, date-only cũng có thể được chấp nhận, trái contract.

### 14.4. Optional không tạo “OR business logic” tự động

Hai nhóm tùy chọn độc lập có thể đồng thời vắng mặt. Nếu bạn muốn **bắt buộc chính xác một trong hai định dạng**, cần logic kiểm tra/dispatch ngoài parser, hoặc thiết kế một grammar phù hợp. DateTimeFormatterBuilder optional giúp tạo văn phạm từng phần, không thay thế toàn bộ validation của ứng dụng.

## 15. Chương trình Java 17+ hoàn chỉnh: nested optional, default, offset, STRICT

Chương trình sau kiểm thử toàn bộ hành vi cốt lõi trên dữ liệu cố định, có assertion và stdout dự đoán được. Nó chỉ dùng `java.time`, không cần thư viện ngoài.

Tạo tệp **`FormatterBuilderOptionalDemo.java`**:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.*;
import java.util.*;

public class FormatterBuilderOptionalDemo {
    static void check(boolean test, String what) {
        if (!test) {
            throw new AssertionError(what);
        }
    }

    static final DateTimeFormatter FLEX = new DateTimeFormatterBuilder()
            .appendPattern("uuuu-MM-dd")
            .optionalStart()
                .appendLiteral('T')
                .appendPattern("HH:mm")
                .optionalStart()
                    .appendLiteral(':')
                    .appendPattern("ss")
                    .appendFraction(ChronoField.NANO_OF_SECOND,
                            0, 9, true)
                .optionalEnd()
            .optionalEnd()
            .toFormatter(Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    static final DateTimeFormatter DEFAULTED =
            new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd")
                .optionalStart()
                    .appendLiteral('T')
                    .appendPattern("HH:mm")
                .optionalEnd()
                .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
                .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                .parseDefaulting(ChronoField.SECOND_OF_MINUTE, 0)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

    static final DateTimeFormatter OFFSET =
            new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd'T'HH:mm")
                .appendOptional(
                    new DateTimeFormatterBuilder()
                        .appendOffsetId()
                        .toFormatter())
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

    static final DateTimeFormatter ENGLISH =
            new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("dd MMM uuuu")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        TemporalAccessor d = FLEX.parseBest(
                "2026-04-05",
                LocalDateTime::from, LocalDate::from);
        TemporalAccessor dt = FLEX.parseBest(
                "2026-04-05T09:07",
                LocalDateTime::from, LocalDate::from);
        TemporalAccessor fractional = FLEX.parseBest(
                "2026-04-05T09:07:05.1200",
                LocalDateTime::from, LocalDate::from);

        check(d instanceof LocalDate, "date");
        check(dt instanceof LocalDateTime, "datetime");
        check(LocalDateTime.from(fractional).getNano()
                        == 120_000_000, "nanos");

        System.out.println("dateType=" +
                d.getClass().getSimpleName());
        System.out.println("dateTimeType=" +
                dt.getClass().getSimpleName());
        System.out.println("fractionNano=" +
                LocalDateTime.from(fractional).getNano());

        System.out.println("dateOnlyFormat=" +
                FLEX.format(LocalDate.of(2026, 4, 5)));
        System.out.println("timeFormat=" +
                FLEX.format(LocalDateTime.of(2026, 4, 5, 9, 7)));
        System.out.println("fractionFormat=" + FLEX.format(
                LocalDateTime.of(2026, 4, 5,
                        9, 7, 5, 120_000_000)));

        System.out.println("defaultDateToDateTime=" +
                LocalDateTime.parse("2026-04-05", DEFAULTED));
        System.out.println("defaultWithTime=" +
                LocalDateTime.parse(
                        "2026-04-05T09:07", DEFAULTED));
        System.out.println("defaultDoesNotPrintTime=" +
                DEFAULTED.format(LocalDate.of(2026, 4, 5)));

        TemporalAccessor plain = OFFSET.parseBest(
                "2026-04-05T09:07",
                OffsetDateTime::from, LocalDateTime::from);
        TemporalAccessor tz = OFFSET.parseBest(
                "2026-04-05T09:07+07:00",
                OffsetDateTime::from, LocalDateTime::from);

        check(plain instanceof LocalDateTime
                && tz instanceof OffsetDateTime,
                "optionalOffset");
        System.out.println("offsetAbsentType=" +
                plain.getClass().getSimpleName());
        System.out.println("offsetPresentType=" +
                tz.getClass().getSimpleName());
        System.out.println("offsetPresentInstant=" +
                OffsetDateTime.from(tz).toInstant());
        System.out.println("offsetPresentFormat=" +
                OFFSET.format(OffsetDateTime.from(tz)));
        System.out.println("offsetAbsentFormat=" +
                OFFSET.format(
                        LocalDateTime.of(2026, 4, 5, 9, 7)));

        System.out.println("englishMixedCase=" +
                LocalDate.parse("05 mAr 2026", ENGLISH));
        System.out.println("englishFormat=" +
                ENGLISH.format(LocalDate.of(2026, 3, 5)));

        DateTimeFormatter smart = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd")
                .toFormatter(Locale.ROOT);

        System.out.println("smartInvalidDay=" +
                LocalDate.parse("2025-02-29", smart));

        boolean strictRejected = false;
        try {
            LocalDate.parse("2025-02-29",
                    smart.withResolverStyle(
                            ResolverStyle.STRICT));
        } catch (DateTimeParseException ex) {
            strictRejected = true;
        }
        System.out.println("strictInvalidDayRejected=" +
                strictRejected);

        boolean incompleteRejected = false;
        try {
            FLEX.parseBest("2026-04-05T09:",
                    LocalDateTime::from, LocalDate::from);
        } catch (DateTimeParseException ex) {
            incompleteRejected = true;
        }
        System.out.println("partialOptionalRejected=" +
                incompleteRejected);

        boolean invalidHourRejected = false;
        try {
            FLEX.parseBest("2026-04-05T25:07",
                    LocalDateTime::from, LocalDate::from);
        } catch (DateTimeParseException ex) {
            invalidHourRejected = true;
        }
        System.out.println("invalidHourRejected=" +
                invalidHourRejected);

        check(strictRejected && incompleteRejected
                && invalidHourRejected, "errors must reject");
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac FormatterBuilderOptionalDemo.java
java FormatterBuilderOptionalDemo
```

**Stdout chính xác (kết quả đã kiểm thử với JDK hiện đại):**

```text
dateType=LocalDate
dateTimeType=LocalDateTime
fractionNano=120000000
dateOnlyFormat=2026-04-05
timeFormat=2026-04-05T09:07:00
fractionFormat=2026-04-05T09:07:05.12
defaultDateToDateTime=2026-04-05T00:00
defaultWithTime=2026-04-05T09:07
defaultDoesNotPrintTime=2026-04-05
offsetAbsentType=LocalDateTime
offsetPresentType=OffsetDateTime
offsetPresentInstant=2026-04-05T02:07:00Z
offsetPresentFormat=2026-04-05T09:07+07:00
offsetAbsentFormat=2026-04-05T09:07
englishMixedCase=2026-03-05
englishFormat=05 Mar 2026
smartInvalidDay=2025-02-28
strictInvalidDayRejected=true
partialOptionalRejected=true
invalidHourRejected=true
ALL CHECKS PASSED
```

### 15.1. Giải thích kết quả

- **dateType/ dateTimeType:** `parseBest` chọn `LocalDate` khi chỉ có ngày, `LocalDateTime` khi có thời gian.
- **fractionNano:** văn bản có `.1200` được parse thành `120000000` nano giây. Khi in lại, builder bỏ trailing zero không bắt buộc, được `.12`.
- **timeFormat:** dù không truyền second theo constructor `LocalDateTime.of(...,hour,minute)`, object vẫn có second=0 và optional `:ss` được in `:00`. Đây là quy tắc quan trọng nhất về optional **khi format**.
- **defaultDateToDateTime:** `parseDefaulting` tạo 00:00 khi input thiếu giờ. `defaultDoesNotPrintTime` chứng minh mặc định chỉ áp dụng khi **parse**, không làm LocalDate chứa giờ khi format.
- **offsetAbsentType / offsetPresentType:** cùng một formatter hỗ trợ một chuỗi không offset và một chuỗi có offset, nhưng trả về những kiểu khác nhau. `+07:00` chuyển thành Instant 02:07Z.
- **englishMixedCase:** `parseCaseInsensitive` cho phép đọc `mAr`; khi format với Locale.ENGLISH, formatter in `Mar` chuẩn.
- **smartInvalidDay / strictInvalidDayRejected:** mặc định SMART có thể điều chỉnh ngày 29/2 năm 2025 thành 28/2; STRICT từ chối.
- **partialOptionalRejected:** có suffix `T09:` nhưng thiếu phút, parser không âm thầm bỏ qua phần ký tự sai.
- **invalidHourRejected:** chuỗi `25:07` không hợp lệ dù giờ nằm trong optional section.

## 16. Ma trận kiểm thử nên có khi dùng optional

| Tình huống | Input/temporal | Kỳ vọng |
| --- | --- | --- |
| Date-only | `2026-04-05` | Parse được `LocalDate` |
| Date + phút | `2026-04-05T09:07` | Parse được `LocalDateTime` |
| Date + giây | `2026-04-05T09:07:05` | Có second=5 |
| Date + nano | `2026-04-05T09:07:05.1200` | Nano=120.000.000 |
| Format `LocalDate` bằng nested optional | `LocalDate.of(2026,4,5)` | Chỉ `2026-04-05` |
| Format `LocalDateTime` có second=0 | `2026-04-05T09:07` | Có thể in `:00` |
| Default date-only | `2026-04-05` | 00:00 theo policy nếu `parseDefaulting` |
| Default không ghi đè field có sẵn | `2026-04-05T09:07` | Giữ 09:07 |
| Optional offset vắng | `2026-04-05T09:07` | `LocalDateTime`, không tự là UTC |
| Optional offset hiện diện | `2026-04-05T09:07+07:00` | `OffsetDateTime` và Instant đúng |
| Optional zone region | `[Asia/Ho_Chi_Minh]` | Parse được ZoneId khu vực nếu grammar hỗ trợ |
| Parse tên tháng mixed-case | `05 mAr 2026` | Thành ngày 2026-03-05 nếu bật case-insensitive |
| Lịch SMART ngày không nhuận | `2025-02-29` | Có thể thành 2025-02-28 |
| Lịch STRICT ngày không nhuận | `2025-02-29` | Bị từ chối |
| Optional mới mở nhưng input dang dở | `2026-04-05T09:` | Không được nuốt suffix sai |
| Offset sai định dạng | `+99:00` | Reject, không dùng default |
| Thông tin yêu cầu bắt buộc thiếu | Chuỗi chỉ ngày khi API bắt buộc giờ | Reject ở grammar/business boundary |
| Formatter immutable dùng từ nhiều thread | Formatter đã tạo xong | Cùng quy tắc parse/format, không sửa builder |

**Dữ liệu nên test thêm:** năm nhuận 29/2, ngày cuối tháng, giờ 00:00 và 23:59:59, fraction 1/3/6/9 chữ số, UTC `Z`, offset `+07:00`/`-05:00`, ZoneId có DST, dữ liệu null, chuỗi trống và chuỗi có ký tự thừa.

### 16.1. Test tính nhất quán kiểu dữ liệu, không chỉ chuỗi

Ví dụ cùng một formatter có thể parse 09:07 rồi format thành 09:07:00. Unit test theo `input.equals(output)` sẽ báo lỗi giả. Đúng hơn là kiểm tra `LocalDateTime.from(parsed).equals(expected)` và so offset/Instant nếu cần.

Ngược lại, nếu yêu cầu API quy định **chuỗi canonical exact**, unit test phải cố định formatter **đầu ra** và assert chuỗi cụ thể. Hai loại test phục vụ hai mục tiêu khác nhau.

## 17. Các lỗi phổ biến khi dùng DateTimeFormatterBuilder

### Lỗi 1: Ký tự `T` nằm ngoài optional

Formatter date-only bị bắt in hoặc parse một chữ `T` dù không có trường giờ. **Sửa:** bọc cả separator và các trường giờ trong cùng `optionalStart/optionalEnd`.

### Lỗi 2: Nghĩ optional tự ẩn `:00` hoặc offset `Z`

Giây bằng 0 hay offset bằng 0 **vẫn là dữ liệu có mặt** trong LocalDateTime/OffsetDateTime. **Sửa:** định nghĩa output canonical riêng hoặc bảo toàn metadata đầu vào nếu cần in đúng những thành phần đã nhập.

### Lỗi 3: Lồng optional sai thứ tự

Một optional `:ss` ở ngoài `T HH:mm` khiến grammar chấp nhận/format cấu trúc không mong muốn. **Sửa:** dùng nesting theo quan hệ phụ thuộc: phải có time trước seconds, phải có seconds trước fraction.

### Lỗi 4: Gọi `optionalEnd()` mà không có `optionalStart()`

Builder ném `IllegalStateException`. **Sửa:** ghép các nhóm cân bằng, kiểm tra cấu trúc mỗi khi refactor.

### Lỗi 5: Quên đóng optional

`toFormatter()` sẽ tự kết thúc những optional còn mở theo hợp đồng, nhưng sự phụ thuộc vào tự đóng làm code khó đọc và có thể che cấu trúc sai. **Sửa:** gọi `optionalEnd()` tường minh ở các nhóm quan trọng.

### Lỗi 6: Dùng `append(...)` khi lẽ ra cần `appendOptional(...)`

Phần formatter con bị bắt buộc, làm parse date-time không có offset bị lỗi hoặc format LocalDateTime không có offset không đúng contract. **Sửa:** dùng appendOptional hoặc bọc append trong optionalStart/End.

### Lỗi 7: Đặt `parseDefaulting` trước phần parse thật

Default được chèn ngay, có thể xung đột khi field xuất hiện sau đó. **Sửa:** đặt ở cuối và chỉ default những field được phép thiếu.

### Lỗi 8: Dùng default UTC cho timestamp thiếu offset

Chuyển một lịch hẹn địa phương thành thời điểm UTC không căn cứ, gây lệch giờ. **Sửa:** giữ LocalDateTime hoặc có ZoneId từ yêu cầu nghiệp vụ và xử lý DST.

### Lỗi 9: Hỏi `parseBest` theo thứ tự quá nghèo thông tin

Nếu hỏi LocalDateTime trước OffsetDateTime, có thể bỏ offset đã được parse. **Sửa:** ưu tiên `OffsetDateTime::from`, rồi mới `LocalDateTime::from`.

### Lỗi 10: Chỉ thêm `parseStrict()` mà quên `ResolverStyle.STRICT`

Một ngày như 29/2 năm không nhuận có thể vẫn được SMART điều chỉnh sau parse. **Sửa:** hiểu hai giai đoạn và chọn resolver strict khi cần dữ liệu lịch chính xác.

### Lỗi 11: Nhầm `yyyy` với `uuuu` trong parser strict

Năm theo era không giống proleptic year; thiếu field ERA có thể làm resolve thất bại. **Sửa:** dùng `uuuu` cho ISO proleptic year theo contract.

### Lỗi 12: Tự đặt dấu chấm trước `appendFraction(...,true)`

Có thể tạo dấu chấm hai lần hoặc separator thừa khi fraction không được in. **Sửa:** để appendFraction điều khiển dấu thập phân nếu `decimalPoint=true`.

### Lỗi 13: Xem optional như bộ lọc input sai

Parser có thể quay lui bên trong nhóm optional, nhưng lời gọi parse chuẩn vẫn phải tiêu thụ toàn bộ input. **Sửa:** bắt DateTimeParseException và trả lỗi validation rõ, không bỏ suffix bất hợp lệ.

### Lỗi 14: Dùng locale mặc định cho API quốc tế

Tên tháng và chữ theo locale có thể khác giữa server. **Sửa:** dùng `toFormatter(Locale.ENGLISH)` hoặc Locale.ROOT theo dữ liệu.

### Lỗi 15: Chia sẻ builder mutable giữa nhiều thread

Builder chỉ dùng để xây, không được thiết kế làm formatter thread-safe. **Sửa:** hoàn thành builder, chia sẻ `DateTimeFormatter` immutable.

### Lỗi 16: Đồng nhất ZoneId với offset

Một vùng có DST hoặc quy tắc lịch sử khác với offset cố định. **Sửa:** giữ zone region khi nghiệp vụ cần lịch theo địa điểm.

## 18. Bài luyện tập có lời giải

**Bài 1.** Muốn chấp nhận `2026-04-05` và `2026-04-05T09:07`, separator `T` phải nằm ở đâu?

**Đáp án:** Bên trong cùng optional section với `HH:mm`. Nếu chỉ bọc giờ mà không bọc `T`, date-only không khớp đúng contract.

**Bài 2.** Vì sao `LocalDateTime` có second=0 vẫn có thể in `:00` khi seconds nằm trong optional?

**Đáp án:** Optional print xét **field có được temporal cung cấp hay không**, không xét giá trị có khác 0 hay không. LocalDateTime luôn có `SECOND_OF_MINUTE`.

**Bài 3.** `appendFraction(NANO_OF_SECOND,0,9,true)` format 120.000.000 nanos thành bao nhiêu?

**Đáp án:** `.12`. Khi parse lại, nó mang cùng giá trị 120.000.000 nanos.

**Bài 4.** Muốn `LocalDateTime.parse("2026-04-05",formatter)` thành 00:00, cần gì?

**Đáp án:** Có thể đặt `parseDefaulting(HOUR_OF_DAY,0)` và `parseDefaulting(MINUTE_OF_HOUR,0)` sau các phần optional; đây là **business policy** về thời gian thiếu.

**Bài 5.** Dùng `parseDefaulting` có làm formatter in thêm `T00:00` khi format `LocalDate` không?

**Đáp án:** Không. Parse defaulting không có hiệu lực khi format; LocalDate vẫn không có các trường giờ.

**Bài 6.** Formatter có offset tùy chọn nên gọi `parseBest` theo thứ tự nào?

**Đáp án:** `OffsetDateTime::from` trước, rồi `LocalDateTime::from`. Nếu hỏi LocalDateTime trước, bạn có thể bỏ mất offset.

**Bài 7.** Với SMART resolver, `2025-02-29` có thể ra giá trị nào? Còn STRICT?

**Đáp án:** SMART theo mẫu `uuuu-MM-dd` có thể điều chỉnh thành `2025-02-28`; STRICT từ chối ngày không hợp lệ.

**Bài 8.** `parseCaseInsensitive()` có làm formatter khi in tháng trả `mar` thay vì `Mar` không?

**Đáp án:** Không. Nó điều chỉnh việc **khớp lúc parse**. Cách in phụ thuộc pattern và Locale.

**Bài 9.** Nếu muốn ngày có giờ bắt buộc nhưng giây tùy chọn, nên bọc phần nào?

**Đáp án:** Để `uuuu-MM-dd'T'HH:mm` ngoài optional và chỉ bọc `:ss` (kèm fraction nếu cần). Không bọc cả `T HH:mm`.

**Bài 10.** `parseBest` trả một `TemporalAccessor` được lấy bằng LocalDate khi chỉ có ngày. Ép kiểu trực tiếp từ `formatter.parse` sang LocalDateTime có đúng không?

**Đáp án:** Không. Dùng `LocalDate.from`/`LocalDateTime.from`, các phương thức `parse` của kiểu cần thiết, hoặc `parseBest`.

**Bài 11.** Phần giờ là optional nhưng input có `T09:` bị cắt ngang. Có nên chấp nhận ngày rồi bỏ suffix không?

**Đáp án:** Không. Lời gọi parse chuẩn phải xử lý toàn văn input; suffix dang dở khiến parse thất bại.

**Bài 12.** Khi format LocalDateTime có `2026-04-05T09:07:00`, làm sao in đúng `2026-04-05T09:07` nếu contract yêu cầu không in `:00`?

**Đáp án:** Không dựa vào việc seconds nằm trong optional để ẩn zero. Hãy chọn **formatter đầu ra** có pattern chỉ tới phút, hoặc có logic xác định độ chính xác trước khi chọn formatter; nhớ rằng điều này có thể cắt giây nếu input có dữ liệu giây khác zero.

**Bài 13.** Một formatter có Optional ZoneId khu vực nhưng input không có zone. Có nên tự chuyển thành Instant UTC?

**Đáp án:** Không. Chuỗi không có zone/offset mới xác định local date-time, chưa xác định instant. Cần ZoneId/offset từ contract mới resolve được.

**Bài 14.** `optionalEnd()` khi không có nhóm đang mở sẽ xảy ra gì?

**Đáp án:** `IllegalStateException` theo hợp đồng builder.

## 19. Quy trình thiết kế formatter tùy chọn an toàn

**Bước 1 — Viết rõ grammar.** Ví dụ chấp nhận date-only, date+HH:mm, date+HH:mm:ss và nano, có/không có offset; xác định chính xác thành phần nào được phép thiếu và cái nào bắt buộc.

**Bước 2 — Lựa chọn cấu trúc lồng.** Một phần chỉ có ý nghĩa khi phần cha hiện diện phải nằm trong optional cha, ví dụ fraction nằm sau seconds và seconds nằm sau time.

**Bước 3 — Tách dấu phân cách đi cùng nhóm.** Ký tự `T` đi với time, dấu `:` đi với seconds, dấu `.` do appendFraction chịu trách nhiệm khi `decimalPoint=true`.

**Bước 4 — Chọn kiểu parse đầu ra.** Nếu tùy chọn offset: OffsetDateTime trước LocalDateTime. Nếu tùy chọn time: LocalDateTime trước LocalDate. Nếu cần zone: thiết kế parser vùng và policy DST.

**Bước 5 — Xác định default có được phép không.** Date-only mặc định 00:00 là một quy tắc nghiệp vụ chứ không phải phép suy luận từ dữ liệu. `parseDefaulting` phải đặt sau những phần parse thật.

**Bước 6 — Cấu hình STRICT/SMART rõ ràng.** Với input dữ liệu quan trọng, nên cân nhắc `withResolverStyle(STRICT)` và dùng `uuuu` nếu năm ISO proleptic. Không bật lenient tùy tiện.

**Bước 7 — Chọn Locale.** Parser tháng tiếng Anh dùng Locale.ENGLISH; dữ liệu ISO số thuần có thể dùng Locale.ROOT; không để server locale thay đổi contract.

**Bước 8 — Thiết kế output canonical tách khỏi input flexible.** Không giả định input có optional rồi format lại nhất định tái tạo đúng văn bản ban đầu.

**Bước 9 — Test tất cả tổ hợp.** Có/không có time, seconds, fraction, offset, zone; bad separator, bad hour, invalid leap date, số chữ số fraction ở biên, offset sai.

**Bước 10 — Hoàn thành builder, chia sẻ formatter.** Đặt `DateTimeFormatter` immutable trong final/static field khi phù hợp, không chia sẻ builder đang bị chỉnh từ nhiều thread.

## 20. Checklist production

- [ ] Mọi trường bắt buộc nằm ngoài optional, mọi separator nằm cùng phần dữ liệu liên quan.
- [ ] Optional lồng đúng thứ tự phụ thuộc giữa date/time/seconds/fraction.
- [ ] Hiểu optional **không ẩn trường zero**; format theo field presence.
- [ ] Đã chọn `appendFraction` min/max width và chính sách precision/trailing zero.
- [ ] `parseDefaulting` chỉ bổ sung trường thiếu và nằm sau các phần parse có thể chứa field ấy.
- [ ] Không mặc định offset/zone tùy tiện khi dữ liệu gốc không cung cấp.
- [ ] `parseBest` thử loại dữ liệu **giàu thông tin trước** để không mất offset/zone.
- [ ] Không ép kiểu `formatter.parse` trực tiếp thành LocalDateTime.
- [ ] Dùng `withResolverStyle(STRICT)` khi không cho SMART sửa ngày sai.
- [ ] Phân biệt parser lexical lenient với resolver lenient.
- [ ] Dùng `uuuu` đúng cho proleptic ISO year; không nhầm `yyyy` hoặc `YYYY`.
- [ ] Locale được chỉ định khi có text tháng/ngày; formatter output đủ ổn định cho API.
- [ ] Có test input dang dở/suffix thừa, leap-day sai, giờ 25, offset sai.
- [ ] Có chính sách DST khi chuyển local date-time + region ZoneId thành Instant.
- [ ] Có test format–parse theo **giá trị dữ liệu**, không buộc văn bản raw giữ nguyên nếu không lưu metadata precision.
- [ ] Không chia sẻ builder mutable giữa nhiều thread; chỉ chia sẻ DateTimeFormatter immutable.

## Tài liệu chính thức, hiện hành

1. [Oracle JDK 25 — DateTimeFormatterBuilder: optionalStart/optionalEnd, appendOptional, parseDefaulting, appendFraction, parseCaseInsensitive, parseStrict và toFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
2. [Oracle JDK 25 — DateTimeFormatter: pattern `[...]`, parseBest, resolver styles, parse/format và Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html)
3. [Oracle JDK 25 — ResolverStyle: STRICT, SMART, LENIENT và resolve ngày không hợp lệ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/ResolverStyle.html)
4. [Oracle JDK 25 — TemporalAccessor: query/isSupported, không mặc định một concrete temporal type](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalAccessor.html)
5. [Oracle JDK 25 — ChronoField: NANO_OF_SECOND và OFFSET_SECONDS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/ChronoField.html)
6. [Oracle JDK 25 — OffsetDateTime: giữ UTC offset của chuỗi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html)
7. [Oracle JDK 25 — ZonedDateTime: khi parse với ZoneId và xử lý gap/overlap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html)

**Ghi nhớ:** `optionalStart/optionalEnd` giúp mô tả **một đoạn văn bản ngày giờ có thể vắng mặt**, không tự nhớ độ chính xác input và không ẩn những trường bằng 0 khi format. Dùng `parseDefaulting` cho giá trị mặc định có chủ đích, `parseBest` để giữ kiểu dữ liệu giàu thông tin nhất, và `ResolverStyle.STRICT` nếu dữ liệu lịch sai phải bị từ chối.
