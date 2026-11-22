# DateTimeParseException và thông tin lỗi khi parse ngày giờ trong Java

## 1. `DateTimeParseException` là gì và vì sao phải hiểu nó?

Khi một chuỗi ngày giờ đi qua `java.time`, Java phải trả lời ít nhất ba câu hỏi: **chuỗi có đúng cú pháp dự kiến không**, **các trường tạo thành giá trị lịch hợp lệ không**, và **dữ liệu ấy có đủ thông tin để tạo đúng kiểu kết quả không**. Khi không thể parse theo yêu cầu, nhiều API như `LocalDate.parse`, `LocalDateTime.parse`, `Instant.parse` hoặc `DateTimeFormatter.parse` sẽ ném **`java.time.format.DateTimeParseException`**.

Đây là ngoại lệ thuộc `java.time`, được cung cấp từ **Java 8** và vẫn được sử dụng trong Java hiện đại. Nó là **unchecked exception**, kế thừa từ `java.time.DateTimeException`. Không cần khai báo `throws` chỉ vì gọi `LocalDate.parse`; nhưng ở **ranh giới nhận dữ liệu bên ngoài** (form, JSON, CSV, cấu hình), cần xử lý lỗi có chủ đích.

Ví dụ:

```java
LocalDate valid = LocalDate.parse("2024-02-29");
// 2024-02-29: hợp lệ vì năm nhuận

// DateTimeParseException: năm 2023 không có ngày 29/2
LocalDate invalid = LocalDate.parse("2023-02-29");
```

Đây là **snippet minh họa**, không phải một chương trình hoàn chỉnh: dòng thứ hai cố ý ném exception. Nếu ứng dụng nhận input từ người dùng và để exception thoát thẳng tới giao diện/HTTP response, người dùng có thể nhìn thấy thông báo khó hiểu hoặc hệ thống làm lộ nguyên chuỗi đầu vào. Ngược lại, nếu bắt tất cả exception rồi âm thầm dùng ngày hiện tại, hệ thống có thể **biến dữ liệu sai thành dữ liệu hợp lệ giả**. Cách đúng là đọc thông tin lỗi, phân loại và ánh xạ thành thông báo phù hợp với hợp đồng nhập liệu.

### 1.1. Những tình huống thường dẫn tới parse exception

| Đầu vào | Kiểu được yêu cầu | Vấn đề |
| --- | --- | --- |
| `2024-05-20` | `LocalDate` | Hợp lệ theo ISO local date |
| `2024-0X-20` | `LocalDate` | Sai ký tự/sai cú pháp phần tháng |
| `2024-05-20XYZ` | `LocalDate` | Chuỗi thừa phía sau phần ngày |
| `2023-02-29` | `LocalDate` | Cú pháp giống ngày hợp lệ nhưng **sai ngày trong năm thường** |
| `2024-13-01` | `LocalDate` | Tháng ngoài miền 1–12 |
| `2024-05-01T09:30:00` | `LocalDate` | Input có thêm phần giờ; đích chỉ nhận ngày |
| `2024-05-01T09:30:00+07:00` | `OffsetDateTime` | Hợp lệ vì đủ offset |
| `2024-05-01T09:30:00` | `OffsetDateTime` | Thiếu offset để tạo kiểu đích |
| `--02-29` | `MonthDay` | Hợp lệ, biểu diễn tháng-ngày không có năm |
| `2024-02` | `YearMonth` | Hợp lệ, biểu diễn năm-tháng không có ngày |

Một chuỗi thất bại **không nhất thiết** là dữ liệu “bậy”: nó có thể hợp lệ ở một **kiểu ngày giờ khác**, nhưng không phù hợp formatter hoặc kiểu kết quả đang yêu cầu. Hãy xác định rõ hợp đồng đầu vào trước khi sửa parser.

## 2. Những thông tin lỗi mà exception thực sự cung cấp

Khai báo rút gọn:

```java
public class DateTimeParseException extends DateTimeException {
    public String getParsedString();
    public int getErrorIndex();
    // getMessage(), getCause() được kế thừa từ Throwable.
}
```

Đây là **sơ đồ API để giải thích**, không phải source code định nghĩa lại lớp chuẩn. Những thông tin có ích:

1. **`getParsedString()`**: chuỗi mà parser đã cố phân tích. Nó giúp đối chiếu với input đã nhận, nhưng cũng có thể chứa **dữ liệu riêng tư**.
2. **`getErrorIndex()`**: vị trí chỉ số lỗi được ghi lại trong chuỗi. Chỉ số này bắt đầu từ **0**, không phải số thứ tự bắt đầu từ 1.
3. **`getMessage()`**: mô tả kỹ thuật dạng văn bản, có thể bao gồm đầu vào và thông tin vị trí; **không nên parse thông báo bằng regex** như một protocol ổn định, cũng không nên gửi nguyên văn tới người dùng cuối.
4. **`getCause()`**: nguyên nhân gốc nếu lỗi phát sinh từ bước resolution hoặc một thao tác con và có cause; **có thể là `null`**. Không được giả định mọi lỗi parse đều chứa một nested cause.
5. Stack trace cho lập trình viên biết đường code dẫn tới lỗi; nó **không phải** dữ liệu thông báo an toàn để gửi lên UI/API.

Ví dụ đọc thông tin có chủ đích:

```java
String raw = "2024-0X-20";

try {
    LocalDate.parse(raw);
} catch (DateTimeParseException exception) {
    int index = exception.getErrorIndex();
    String attempted = exception.getParsedString();
    Throwable cause = exception.getCause();
    // Chỉ dùng attempted/cause trong log tin cậy, có redaction.
}
```

Đây là snippet cần import `LocalDate`, `DateTimeParseException`. Muốn trả lỗi cho UI, hãy tạo **mã lỗi ổn định** như `INVALID_DATE_FORMAT` thay vì trả `exception.toString()`.

### 2.1. Hai constructor của `DateTimeParseException`

API có constructor nhận ba hoặc bốn đối số:

```java
DateTimeParseException(
    String message,
    CharSequence parsedData,
    int errorIndex)

DateTimeParseException(
    String message,
    CharSequence parsedData,
    int errorIndex,
    Throwable cause)
```

Dùng khi bạn **tự xây bộ phân tích** muốn cung cấp đúng loại ngoại lệ này. Nhưng với validator nghiệp vụ (“ngày này nằm ngoài giờ làm việc”, “tài khoản hết hạn”), thường nên có **ngoại lệ/domain result riêng**, vì đó không còn là lỗi parse cú pháp ngày giờ. Đừng dùng `DateTimeParseException` làm một nhãn tổng quát cho mọi quy tắc nghiệp vụ liên quan đến ngày.

## 3. Hiểu `getErrorIndex()`: vị trí kỹ thuật, không phải tên trường bị sai

Một chuỗi có các vị trí ký tự theo chỉ số Java:

```text
Chuỗi:  2 0 2 4 - 0 X - 2 0
Index:  0 1 2 3 4 5 6 7 8 9
                  ^
              vùng tháng bị lỗi
```

Với input `"2024-0X-20"`, parser ISO báo lỗi khi phần tháng không đúng cú pháp. Không nên bắt UI phải đoán ngay rằng `errorIndex` luôn nằm ở “chữ X”; trong một số tình huống parser báo vị trí **bắt đầu đoạn không khớp** (ví dụ bắt đầu trường tháng), và trong lỗi **resolving giá trị lịch**, vị trí thường gắn với toàn giá trị ngày thay vì riêng ký tự cần sửa.

**Hợp đồng quan trọng:** `getErrorIndex()` cung cấp **chỉ số mà bộ phân tích báo gặp lỗi**, không cam kết luôn chỉ đúng một ký tự sai duy nhất hay đủ để xác định trường nghiệp vụ bị lỗi.

### 3.1. Dữ liệu thừa phía sau định dạng

`LocalDate.parse("2024-05-20XYZ")` có thể đọc được 10 ký tự ngày rồi phát hiện phần `XYZ` chưa được tiêu thụ. Với `DateTimeFormatter.parse(CharSequence)`, thao tác parse đầy đủ yêu cầu **xử lý toàn bộ chuỗi**, nếu còn nội dung dư sẽ báo lỗi.

Đừng “sửa” bằng cách mặc định lấy `raw.substring(0, 10)`: làm vậy có thể che khuất dữ liệu bị lỗi hoặc một hậu tố có ý nghĩa quan trọng (offset, thời gian, mã vùng...). Nếu giao thức cho phép hậu tố, hãy định nghĩa một formatter/kiểu đầu vào **rõ ràng**.

### 3.2. Chỉ số tính theo `String` Java, không phải pixel trên UI

`getErrorIndex()` là chỉ số của chuỗi parser nhận được. Trong Java, `String` dùng **UTF-16 code unit** cho các phép truy cập `charAt`/`substring`. Nếu input có emoji hoặc ký tự Unicode ngoài BMP, một ký tự có thể dùng **hai** code unit. Một vị trí Java không nhất thiết là cùng số vị trí mà giao diện đếm theo Unicode code point hoặc grapheme cluster.

Vì vậy, khi vẽ dấu gạch dưới lỗi trong trình duyệt/ứng dụng:

- Dùng đúng **chuỗi thực sự được parse**, không phải chuỗi đã được tự động trim/normalize ở bước khác.
- Chuyển đổi vị trí nếu UI dùng code point thay vì UTF-16 index.
- Chặn chỉ số nằm ngoài miền hợp lệ trước khi truy cập `charAt`/`substring`; vị trí lỗi có thể ở **cuối chuỗi** khi đầu vào thiếu phần bắt buộc.
- Không phơi ra chuỗi bí mật hoặc dữ liệu cá nhân chỉ để đánh dấu vị trí lỗi.

### 3.3. Đừng hứa giá trị index cố định cho mọi lỗi semantic

Với input `"2023-02-29"`, lexical parser có thể đọc đủ các số `2023`, `02`, `29`. Thất bại diễn ra **sau đó** trong bước kết hợp trường, nên chỉ số lỗi không nhất thiết trỏ vào chữ số `29`. Một API thân thiện nên báo **“Ngày không tồn tại trong tháng/năm đã chọn”** hơn là dùng chỉ số để suy ra tên trường bằng một quy tắc thiếu chắc chắn.

## 4. Parser hoạt động hai giai đoạn: đọc văn bản và resolve trường

`DateTimeFormatter` không đơn thuần “chạy regex có dấu `-`”. Mô hình parse có **hai pha**:

1. **Lexical parse:** theo formatter, đọc văn bản và sinh ra các cặp field–value, ví dụ `YEAR=2023`, `MONTH_OF_YEAR=2`, `DAY_OF_MONTH=29`.
2. **Resolve:** ghép các field thành `LocalDate`, `LocalTime`, `OffsetDateTime` hoặc kiểu cần thiết theo quy tắc lịch, giá trị hợp lệ, chronologies và `ResolverStyle`.

Hai loại lỗi:

| Pha | Ví dụ | Cách phân tích |
| --- | --- | --- |
| Đọc ký tự/không khớp pattern | `2024-0X-20` | Không có phần tháng đúng định dạng |
| Không tiêu thụ hết input | `2024-05-20abc` | Có hậu tố ngoài hợp đồng formatter |
| Resolve ngày | `2023-02-29` | Các field số đọc được, nhưng không tạo được ngày hợp lệ ở năm thường |
| Resolve kiểu đích | Chỉ có `2024-05` nhưng yêu cầu `LocalDate` | Thiếu trường ngày để tạo kết quả nếu không có chính sách mặc định |
| Yêu cầu offset | Chuỗi `2024-05-01T09:30` đưa vào `OffsetDateTime.parse` | Không đủ thông tin offset |

Điều này giải thích tại sao `DateTimeParseException` có thể bọc một `DateTimeException` khác làm `cause` trong lỗi semantic, trong khi lỗi lexical đơn giản có thể không có cause.

### 4.1. `parseUnresolved` không thay thế validation

`DateTimeFormatter.parseUnresolved(text, ParsePosition)` chủ yếu thực hiện pha đọc trường **chưa resolve** và trả một `TemporalAccessor` chưa áp dụng đầy đủ bước kết hợp ngày. Vì vậy, việc parseUnresolved không bị lỗi **không chứng minh một `LocalDate` hợp lệ**.

```java
DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("uuuu-MM-dd");

ParsePosition position = new ParsePosition(0);
TemporalAccessor partial =
    formatter.parseUnresolved("2023-02-29", position);

// Phần ký tự có thể được đọc; ngày 29/2/2023
// vẫn không được coi là hợp lệ khi resolve STRICT.
```

Đây là snippet cần import `java.text.ParsePosition`, `java.time.temporal.TemporalAccessor`, `DateTimeFormatter`. `ParsePosition` còn có các trường `getIndex()`, `getErrorIndex()` mô tả vị trí đọc; đừng nhầm ý nghĩa chúng với `DateTimeParseException.getErrorIndex()` trong toàn bộ quy trình resolve.

Phần lớn ứng dụng nên dùng `LocalDate.parse(input, formatter)` hoặc `formatter.parse(input, LocalDate::from)` để **thực sự lấy giá trị đã resolve**, thay vì tự quản lý `ParsePosition`.

## 5. `ResolverStyle.STRICT`, `SMART` và `LENIENT`

`ResolverStyle` quyết định **cách giải quyết những field đã đọc được**:

- **`STRICT`:** yêu cầu các giá trị tạo thành ngày giờ hợp lệ chính xác, ví dụ từ chối `2023-02-29`.
- **`SMART`:** có thể điều chỉnh một số field trong phạm vi hợp lý; ví dụ ngày 29 tháng 2 năm thường được đưa về ngày 28 tháng 2.
- **`LENIENT`:** có thể chấp nhận giá trị vượt miền và tính tràn theo phép cộng lịch; ví dụ một tháng 2 có ngày 32 có thể trở thành tháng 3.

```java
DateTimeFormatter base =
    DateTimeFormatter.ofPattern("uuuu-MM-dd");

DateTimeFormatter strict =
    base.withResolverStyle(ResolverStyle.STRICT);
DateTimeFormatter smart =
    base.withResolverStyle(ResolverStyle.SMART);
DateTimeFormatter lenient =
    base.withResolverStyle(ResolverStyle.LENIENT);

// SMART: 2023-02-29 -> 2023-02-28
LocalDate adjusted = LocalDate.parse("2023-02-29", smart);

// LENIENT: 2023-02-32 -> 2023-03-04
LocalDate rolled = LocalDate.parse("2023-02-32", lenient);

// STRICT: dòng này ném DateTimeParseException.
// LocalDate.parse("2023-02-29", strict);
```

Lưu ý: `DateTimeFormatter.ofPattern` mặc định dùng `ResolverStyle.SMART` cho pha resolution; nhiều lập trình viên tưởng pattern `"uuuu-MM-dd"` tự động strict tuyệt đối. Nếu đang kiểm tra **ngày sinh, ngày thanh toán, ngày chốt dữ liệu**, hãy lựa chọn `STRICT` một cách tường minh.

### 5.1. `parseStrict()` không phải `withResolverStyle(STRICT)`

`DateTimeFormatterBuilder.parseStrict()` và `parseLenient()` điều chỉnh **độ nghiêm ngặt trong pha đọc ký tự**, gồm độ rộng/chế độ ghép và cách parse field. Chúng **không thay thế** `ResolverStyle` trong pha resolve.

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
    .parseStrict()                   // Pha 1: đọc text
    .appendPattern("uuuu-MM-dd")
    .toFormatter(Locale.ROOT)
    .withResolverStyle(ResolverStyle.STRICT); // Pha 2: resolve
```

Đây là snippet cần import `DateTimeFormatter`, `DateTimeFormatterBuilder`, `ResolverStyle`, `Locale`. `parseStrict` vốn là trạng thái mặc định của builder ở pha đọc, nhưng viết ra có thể giúp người đọc thấy hai trách nhiệm khác nhau. Dù dùng `parseLenient()`, không được tự suy ra quy tắc kiểm tra ngày lịch sẽ tự lenient nếu resolver vẫn `STRICT`.

### 5.2. Khi nào cần `SMART` hoặc `LENIENT`?

Chỉ sử dụng khi **hợp đồng nghiệp vụ yêu cầu chuyển đổi/điều chỉnh đầu vào**; ví dụ một tool dữ liệu cũ cho phép dùng ngày vượt tháng để biểu diễn cộng ngày. Nếu người dùng nhập “29/02/2023” trong form ngày sinh, việc âm thầm chuyển thành “28/02/2023” là thay đổi dữ liệu chứ không phải chấp nhận chính xác dữ liệu người dùng nhập.

Với đầu vào người dùng có ràng buộc rõ, **STRICT thường là mặc định thiết kế tốt hơn**; khác với suy nghĩ “càng dễ parse càng tốt”.

## 6. Pattern rất dễ nhầm: `uuuu`, `yyyy`, `YYYY`, `MM` và `mm`

Trong `DateTimeFormatter`, các chữ cái pattern **phân biệt chữ hoa/chữ thường**:

| Pattern | Ý nghĩa | Bẫy |
| --- | --- | --- |
| `u`, `uuuu` | *proleptic year* | Hữu ích với strict ISO date, kể cả năm 0/âm |
| `y`, `yyyy` | *year of era* | Strict resolution có thể cần thêm thông tin era |
| `Y`, `YYYY` | *week-based year* theo locale | Không nhất thiết bằng calendar year ở ngày cuối/đầu năm |
| `M`, `MM` | Tháng trong năm | `MM` không phải phút |
| `m`, `mm` | Phút trong giờ | `mm` không phải tháng |
| `d`, `dd` | Ngày trong tháng | Không phải ngày trong năm |
| `D` | Ngày thứ mấy trong năm | Khác `d` |
| `H` | Giờ 0–23 | Phù hợp format 24 giờ |
| `h` | Giờ 1–12 | Cần kết hợp `a` (AM/PM) khi muốn giải nghĩa đầy đủ |
| `S` | Phần lẻ nano giây | Cách xuất/đọc phụ thuộc số chữ S |
| `X`, `XXX` | Offset dạng ISO | Cần đúng pattern/kiểu dữ liệu |

### 6.1. Vì sao `yyyy-MM-dd` với STRICT có thể không parse?

`yyyy` đọc **YEAR_OF_ERA**; trong strict resolver mà không có era, chỉ riêng giá trị đó không đủ để giải quyết thành proleptic year cho `LocalDate`. `uuuu` đọc trực tiếp **YEAR** và thường phù hợp hơn cho một chuỗi năm–tháng–ngày ISO đầy đủ.

```java
DateTimeFormatter correct =
    DateTimeFormatter.ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

// Parse hợp lệ:
LocalDate day = LocalDate.parse("2024-02-29", correct);

// Dễ lỗi trong STRICT nếu không cung cấp era:
DateTimeFormatter yearOfEra =
    DateTimeFormatter.ofPattern("yyyy-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);
// LocalDate.parse("2024-02-29", yearOfEra);
```

Đây là snippet: lệnh cuối cố ý comment để ví dụ biên dịch/running không văng lỗi. `yyyy` **không phải legacy**; nó phù hợp khi ứng dụng thực sự mô hình hóa năm theo era. Nhưng trong ISO date strict phổ thông, chọn `uuuu` cho rõ.

### 6.2. `YYYY-MM-dd` không phải “năm hiện tại”

`Y` là **week-based-year** và quy tắc tuần còn phụ thuộc locale/`WeekFields`. Ở những ngày đầu/cuối năm, week-year có thể khác năm lịch; ghép `YYYY` với `MM-dd` là một thiết kế format dễ gây sai. Nếu contract là ISO date `2024-12-31`, dùng `uuuu-MM-dd` hoặc `DateTimeFormatter.ISO_LOCAL_DATE`, không tự đổi sang `YYYY`.

### 6.3. Nên dùng formatter chuẩn khi contract là ISO

`DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_LOCAL_DATE_TIME`, `ISO_OFFSET_DATE_TIME`, `ISO_INSTANT` đã mô tả rõ các định dạng chuẩn. Không tự viết pattern phức tạp chỉ vì không biết sẵn API.

```java
LocalDate date = LocalDate.parse("2024-05-20");
LocalDateTime time = LocalDateTime.parse("2024-05-20T09:30:00");
OffsetDateTime offset = OffsetDateTime.parse(
    "2024-05-20T09:30:00+07:00");
Instant event = Instant.parse("2024-05-20T02:30:00Z");
```

Nếu đầu vào không có offset, đừng tự thêm `Z` và gọi là parse đúng UTC: đó là **diễn giải ngữ nghĩa dữ liệu** cần hợp đồng riêng.

## 7. Parse date khác parse time, offset, timezone và các kiểu ngày không đủ trường

### 7.1. Chọn kiểu đúng mức thông tin

| Chuỗi | Kiểu thích hợp | Lý do |
| --- | --- | --- |
| `2024` | `Year` | Chỉ có năm |
| `2024-05` | `YearMonth` | Chỉ năm-tháng |
| `--02-29` | `MonthDay` | Tháng-ngày lặp lại |
| `2024-05-20` | `LocalDate` | Ngày đầy đủ |
| `09:30:00` | `LocalTime` | Chỉ giờ đồng hồ |
| `2024-05-20T09:30:00` | `LocalDateTime` | Ngày+giờ không offset |
| `2024-05-20T09:30:00+07:00` | `OffsetDateTime` | Ngày+giờ có offset |
| `2024-05-20T02:30:00Z` | `Instant` | Mốc thời gian UTC |
| `2024-05-20T09:30+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | Có định danh khu vực |

Lỗi “unable to obtain LocalDate from TemporalAccessor” có thể xuất phát từ việc formatter đọc được một số trường nhưng **không đủ trường** để tạo `LocalDate`. Nếu input thực sự chỉ là kỳ tháng, kết quả nên là `YearMonth` chứ không cố ép thành một ngày mặc định giả.

### 7.2. Nếu nghiệp vụ yêu cầu mặc định ngày, hãy khai báo tường minh

Khi thực sự muốn mặc định **ngày đầu tháng** cho `"2024-05"`:

```java
DateTimeFormatter monthWithDefaultDay =
    new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM")
        .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate firstDay = LocalDate.parse(
    "2024-05", monthWithDefaultDay);
// 2024-05-01
```

Đây là **quy tắc domain do lập trình viên bổ sung**, không có nghĩa chuỗi `2024-05` tự nhiên đã chứa ngày 01. Cần import `ChronoField` từ `java.time.temporal`, `Locale` và các lớp formatter. Không âm thầm thêm giá trị mặc định nếu hệ thống cần giữ tính chính xác “chỉ năm-tháng”.

### 7.3. Offset là thông tin ngữ nghĩa, không chỉ là hậu tố tùy chọn

`OffsetDateTime.parse("2024-05-20T09:30:00+07:00")` xác định được một `Instant`. Còn `LocalDateTime.parse("2024-05-20T09:30:00")` **chưa** xác định được instant, vì không có zone/offset. Nếu API yêu cầu timestamp tuyệt đối, lỗi do thiếu offset là tín hiệu cần yêu cầu client gửi dữ liệu đầy đủ, không “sửa” bằng `ZoneId.systemDefault()`.

Nếu dữ liệu mang region `[Europe/Paris]`, dùng `ZonedDateTime` và chọn formatter/hợp đồng tương ứng; offset hiện tại khác việc lưu chính sách múi giờ tương lai.

## 8. Locale, tên tháng và chữ hoa/thường

`DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.ENGLISH)` có thể parse chuỗi tháng tiếng Anh rút gọn. `Locale` là một phần của **cách giải nghĩa từ ngữ**, không chỉ là chọn ngôn ngữ hiển thị.

```java
DateTimeFormatter english =
    DateTimeFormatter.ofPattern(
        "dd MMM uuuu", Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse(
    "05 May 2024", english);
// 2024-05-05
```

Không dựa vào locale mặc định nếu contract của API cần tái lập giữa các server. Nếu người dùng nhập tên tháng theo ngôn ngữ khác, hãy truyền đúng locale hoặc dùng định dạng số ISO khi trao đổi giữa máy.

### 8.1. `parseCaseInsensitive()` cho phép thay đổi case của phần text

Khi contract nói tên tháng không phân biệt hoa/thường:

```java
DateTimeFormatter ignoreCase =
    new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("dd MMM uuuu")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate day = LocalDate.parse("05 mAy 2024", ignoreCase);
// 2024-05-05
```

`parseCaseInsensitive` điều khiển cách so khớp text trong pha lexical. Nó **không** biến tháng 13 thành hợp lệ và không thay thế resolver strict. `parseCaseInsensitive` cũng không tự biến từ tiếng Việt thành tên tháng tiếng Anh; ngôn ngữ được quyết định qua `Locale` và định nghĩa formatter.

### 8.2. Ký số và dấu phân cách cũng có quy ước

`DateTimeFormatter` làm việc với `DecimalStyle`, locale và ký số; không tự áp dụng việc bỏ dấu cách hoặc chuyển mọi kiểu chữ số trong tất cả trường hợp. Nếu input theo chuẩn máy, định nghĩa rõ `uuuu-MM-dd` và ràng buộc độ dài, dấu phân cách. Nếu là input do con người nhập, có thể có bước normalization được tài liệu hóa, nhưng phải **giữ nguyên input gốc ở mức cần thiết để báo lỗi**, và không làm mất thông tin trước khi validation.

## 9. Cách bắt lỗi an toàn ở ranh giới nhận dữ liệu

Một lớp parsing tốt nên tách hai mức trách nhiệm:

- **Mức kỹ thuật:** formatter tạo `LocalDate` hoặc ném `DateTimeParseException`; exception có input, error index, message, cause.
- **Mức sản phẩm:** API trả một **mã lỗi ổn định** và lời hướng dẫn phù hợp, ví dụ `INVALID_DATE` / “Ngày phải theo dạng YYYY-MM-DD và tồn tại trên lịch”.

Ví dụ:

```java
static LocalDate parseUserDate(String raw) {
    DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

    try {
        return LocalDate.parse(raw, strict);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
            "Ngày phải theo dạng năm-tháng-ngày hợp lệ", ex);
    }
}
```

Đây là **method snippet** yêu cầu import `LocalDate`, `DateTimeFormatter`, `ResolverStyle`, `Locale`, `DateTimeParseException`. Ứng dụng web có thể ánh xạ `IllegalArgumentException` có chủ đích này thành HTTP 400 hoặc mã lỗi domain theo framework đang sử dụng. Không nên biến tất cả `IllegalArgumentException` ở mọi nơi thành “input sai”: phân biệt nguồn lỗi theo layer.

### 9.1. Đừng ghi nguyên `getParsedString()` vào log mặc định

Chuỗi ngày giờ có thể đi kèm mã đặt lịch, thông tin cá nhân hoặc dữ liệu nhạy cảm ở cùng trường nhập. `getMessage()` có thể nhắc lại input. Vì vậy:

- Với người dùng cuối: trả tên trường và hướng dẫn dạng hợp lệ.
- Với log kỹ thuật: ưu tiên **error code**, vị trí, formatter ID, correlation/request ID đã được thiết kế an toàn; chỉ lưu phần input đã redacted khi được phép.
- Tránh stack trace và toàn bộ request body trong response.
- Đặt giới hạn độ dài input trước khi parse để giảm log phình to và xử lý chuỗi bất thường.
- Không ghi toàn bộ `getParsedString()` vào nơi phân tích bên thứ ba khi không có chính sách bảo mật phù hợp.

### 9.2. Hiển thị lỗi ở vị trí index chỉ khi có lợi ích

Nếu app hiển thị textbox ngày giờ, có thể tô sáng vùng lỗi theo `getErrorIndex()`. Nhưng không bắt buộc. Với ngày không tồn tại (29/2 năm thường), hiển thị lời giải thích theo field thường tốt hơn một con trỏ ở vị trí 0.

Khi cần cắt chuỗi:

```java
int error = ex.getErrorIndex();
String parsed = ex.getParsedString();

boolean inBounds = error >= 0 && error <= parsed.length();
// Chỉ dùng index cho UI sau khi kiểm tra, và xét UTF-16.
```

Đây là snippet trong một khối `catch (DateTimeParseException ex)`, chưa phải chương trình độc lập. Kiểm tra độ dài quan trọng vì vị trí cuối chuỗi có thể biểu diễn **thiếu dữ liệu**; không gọi `charAt(length)`. Nếu UI đếm code point/grapheme, cần ánh xạ index tương ứng.

## 10. Chương trình Java hoàn chỉnh và kiểm chứng được

Mã này dùng **chỉ API Java 8**, không phụ thuộc thời gian hiện tại hoặc múi giờ mặc định. Nó minh họa:

1. Parse ISO date thành công.
2. Lỗi ký tự và hậu tố thừa, đọc `getErrorIndex()` và `getParsedString()`.
3. Ngày không hợp lệ bị `STRICT` từ chối nhưng `SMART`, `LENIENT` có hành vi khác theo contract.
4. Sự khác nhau của `yyyy` với `uuuu` khi resolver `STRICT`.
5. Parse theo locale, hỗ trợ tên tháng không phân biệt chữ hoa/thường.
6. Parse `YearMonth`, `MonthDay` và timestamp có offset.
7. `parseDefaulting` được dùng một cách **có chủ đích**.
8. Bắt lỗi đầu vào tại ranh giới và trả thông báo ổn định thay vì message kỹ thuật.

Lưu thành **DateTimeParseDiagnosticsDemo.java**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.OffsetDateTime;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class DateTimeParseDiagnosticsDemo {
    private static final DateTimeFormatter STRICT_DATE =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    private static String safeParse(String input) {
        try {
            return LocalDate.parse(input, STRICT_DATE).toString();
        } catch (DateTimeParseException ex) {
            return "INVALID_DATE";
        }
    }

    public static void main(String[] args) {
        System.out.println("ISO valid: "
            + LocalDate.parse("2024-02-29"));

        String invalidChar = "2024-0X-20";
        try {
            LocalDate.parse(invalidChar, STRICT_DATE);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid character index: "
                + ex.getErrorIndex());
            System.out.println("Original input preserved: "
                + invalidChar.equals(ex.getParsedString()));
        }

        String trailing = "2024-05-20XYZ";
        try {
            LocalDate.parse(trailing, STRICT_DATE);
        } catch (DateTimeParseException ex) {
            System.out.println("Trailing index: "
                + ex.getErrorIndex());
        }

        try {
            LocalDate.parse("2023-02-29", STRICT_DATE);
        } catch (DateTimeParseException ex) {
            System.out.println("Strict leap date rejected: true");
            System.out.println("Semantic error index available: "
                + (ex.getErrorIndex() >= 0));
        }

        DateTimeFormatter base =
            DateTimeFormatter.ofPattern("uuuu-MM-dd");
        System.out.println("Smart adjusted: " + LocalDate.parse(
            "2023-02-29",
            base.withResolverStyle(ResolverStyle.SMART)));
        System.out.println("Lenient rolled: " + LocalDate.parse(
            "2023-02-32",
            base.withResolverStyle(ResolverStyle.LENIENT)));

        DateTimeFormatter yearOfEra =
            DateTimeFormatter.ofPattern("yyyy-MM-dd")
                .withResolverStyle(ResolverStyle.STRICT);
        boolean yearOfEraFailed = false;
        try {
            LocalDate.parse("2024-02-29", yearOfEra);
        } catch (DateTimeParseException ex) {
            yearOfEraFailed = true;
        }
        System.out.println("yyyy strict rejected: "
            + yearOfEraFailed);
        System.out.println("uuuu strict accepted: "
            + LocalDate.parse("2024-02-29", STRICT_DATE));

        DateTimeFormatter insensitive =
            new DateTimeFormatterBuilder()
                .parseCaseInsensitive()
                .appendPattern("dd MMM uuuu")
                .toFormatter(Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("English month case ignored: "
            + LocalDate.parse("05 mAy 2024", insensitive));

        System.out.println("YearMonth parsed: "
            + YearMonth.parse("2024-05"));
        System.out.println("MonthDay parsed: "
            + MonthDay.parse("--02-29"));

        DateTimeFormatter monthWithDefaultDay =
            new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM")
                .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("Explicit default day: "
            + LocalDate.parse("2024-05", monthWithDefaultDay));

        OffsetDateTime offset = OffsetDateTime.parse(
            "2024-05-20T09:30:00+07:00");
        Instant actualInstant = offset.toInstant();
        System.out.println("Offset to instant: "
            + actualInstant);

        System.out.println("Safe invalid result: "
            + safeParse("2024-02-30"));
        System.out.println("Safe valid result: "
            + safeParse("2024-02-29"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DateTimeParseDiagnosticsDemo.java
java DateTimeParseDiagnosticsDemo
```

**Stdout chính xác:**

```text
ISO valid: 2024-02-29
Invalid character index: 5
Original input preserved: true
Trailing index: 10
Strict leap date rejected: true
Semantic error index available: true
Smart adjusted: 2023-02-28
Lenient rolled: 2023-03-04
yyyy strict rejected: true
uuuu strict accepted: 2024-02-29
English month case ignored: 2024-05-05
YearMonth parsed: 2024-05
MonthDay parsed: --02-29
Explicit default day: 2024-05-01
Offset to instant: 2024-05-20T02:30:00Z
Safe invalid result: INVALID_DATE
Safe valid result: 2024-02-29
```

### 10.1. Đọc các kết quả có ý nghĩa

- Input có ký tự sai `"2024-0X-20"` làm parser báo vị trí bắt đầu phần tháng không khớp; code đọc trực tiếp index từ exception. Chương trình còn xác nhận `getParsedString()` giữ nguyên input cần parse.
- Khi có `XYZ` dư sau ngày hợp lệ, parser nhận diện nội dung dư bắt đầu ở vị trí `10` (đếm từ 0).
- `STRICT` từ chối `2023-02-29`. Bài không khẳng định semantic exception trỏ chính xác vào chữ `29`, chỉ kiểm tra rằng có index chẩn đoán.
- `SMART` biến ngày 29/2/2023 thành 28/2/2023; `LENIENT` quy ngày 32/2/2023 thành 04/03/2023. Đây là hành vi cho thấy độ “dễ dãi” **có thể thay đổi dữ liệu**.
- `yyyy` khi strict không đủ era để resolve `LocalDate` trong formatter ví dụ, trong khi `uuuu` strict chấp nhận ngày nhuận hợp lệ.
- `parseCaseInsensitive()` cho phép đọc `mAy` bằng bảng tên tháng tiếng Anh, nhưng không làm thay đổi việc kiểm tra ngày lịch.
- `parseDefaulting` cố ý bổ sung ngày `1` cho một kỳ `2024-05`; chỉ áp dụng khi điều này là quy tắc nghiệp vụ.
- Timestamp có offset xác định được một instant. `safeParse` minh họa việc **không chuyển nguyên message và input của exception ra bên ngoài**.

## 11. Test đúng loại lỗi thay vì so nguyên văn `getMessage()`

Các bài test nên kiểm tra:

1. **Kiểu exception:** input sai phải ném `DateTimeParseException`.
2. **Giá trị thành công:** date/time sau parse đúng như mong đợi.
3. **Thông tin chẩn đoán:** `getParsedString()` phản ánh input đã cố parse; `getErrorIndex()` là chỉ số hợp lệ trong ngữ cảnh kiểm thử.
4. **Quy tắc resolver:** ngày không tồn tại bị strict từ chối, smart/lenient chỉ được chấp nhận nếu nghiệp vụ muốn.
5. **Không có chuyển đổi ngầm:** formatter chọn đúng locale, zone, offset.
6. **Thông báo API:** error code và lời giải thích người dùng không phụ thuộc `getMessage()` do JDK tạo.
7. **Round-trip:** `formatter.format(parsedValue)` cho định dạng chuẩn; parse lại tạo cùng giá trị trong miền hỗ trợ.

Không nên viết test kiểu:

```java
// Dễ vỡ nếu thông điệp JDK có thay đổi:
// assertEquals("Text '...' could not be parsed ...", ex.getMessage());
```

Kiểm tra message nguyên văn thường không chứng minh độ đúng của parser và tạo coupling vào wording của JDK. Nếu test riêng một thông điệp do **ứng dụng tự tạo**, việc so exact là hợp lý.

### 11.1. Ma trận test đầu vào nên có

| Nhóm | Input mẫu | Kỳ vọng với `STRICT_DATE` |
| --- | --- | --- |
| Ngày hợp lệ | `2024-02-29` | Parse được `LocalDate` |
| Năm không nhuận | `2023-02-29` | `DateTimeParseException` |
| Tháng vượt miền | `2024-13-01` | `DateTimeParseException` |
| Ngày 0 | `2024-02-00` | `DateTimeParseException` |
| Ngày 31 trong tháng 4 | `2024-04-31` | `DateTimeParseException` |
| Sai dấu | `2024/05/20` | `DateTimeParseException` |
| Thiếu số 0 ở tháng | `2024-5-20` | `DateTimeParseException` |
| Hậu tố thừa | `2024-05-20XYZ` | `DateTimeParseException` |
| Có giờ trong LocalDate | `2024-05-20T09:30` | `DateTimeParseException` |
| Chuỗi rỗng | `""` | `DateTimeParseException` |
| Chuỗi null | `null` | Thường `NullPointerException` cho `parse`; validate null riêng |
| Năm rất lớn/ngoài miền | Chuỗi năm vượt phạm vi `LocalDate` | `DateTimeParseException` hoặc lỗi liên quan, tùy pha |
| Ký số/locale khác | Chữ số/locale ngoài hợp đồng | Có thể lỗi nếu formatter không hỗ trợ |
| Khoảng trắng trước/sau | `" 2024-05-20 "` | Không tự trim nếu ứng dụng chưa quy định |

Bảng là các **trường hợp nên đưa vào bộ kiểm thử**, không phải lời khuyên viết một “parser siêu linh hoạt” chấp nhận mọi biến thể. Việc chấp nhận dấu cách, chuỗi hai chữ số năm hoặc nhiều locale cần có contract và test rõ.

### 11.2. Dùng `parseBest` khi thật sự hỗ trợ nhiều dạng

`DateTimeFormatter.parseBest` cho phép thử nhiều `TemporalQuery` để chọn kiểu kết quả thích hợp; nhưng cần thiết kế formatter và thứ tự truy vấn đúng. Nó không phải cách “bắt mọi ngày giờ không chuẩn mà không có lỗi”. Nếu API cần cả date-only và date-time, có thể tạo **hai con đường parse rõ ràng** theo định dạng được công bố, hoặc một formatter có optional sections và `parseBest` cùng test đầy đủ.

Không bắt lỗi `DateTimeParseException` rồi thử hàng chục formatter ngẫu nhiên như một chiến lược mặc định: có thể khiến dữ liệu ngày-tháng mơ hồ kiểu `03/04/2024` bị hiểu khác nhau giữa hai quốc gia.

## 12. `DateTimeException`, `DateTimeParseException` và các lỗi liên quan

| Trường hợp | Ngoại lệ thường gặp | Ý nghĩa xử lý |
| --- | --- | --- |
| Không parse được input bằng formatter | `DateTimeParseException` | Đầu vào không phù hợp cú pháp/field/resolver/kiểu đích |
| Tạo ngày không tồn tại trực tiếp, ví dụ `LocalDate.of(2023,2,29)` | `DateTimeException` | Đối số ngày không hợp lệ, không nhất thiết là lỗi parse văn bản |
| Pattern không hợp lệ trong `ofPattern` | `IllegalArgumentException` | Lỗi cấu hình/lập trình, không đổ cho user input ngày |
| Truy vấn trường không được kiểu temporal hỗ trợ | `UnsupportedTemporalTypeException` (một loại `DateTimeException`) | Sai thao tác/kiểu, khác lỗi cú pháp |
| Input `null` trong API yêu cầu không null | `NullPointerException` | Kiểm tra tham số đầu vào riêng |
| Formatter không thể in một temporal thiếu field | `DateTimeException` | Lỗi format/query không nhất thiết là parse exception |

Khi chỉ xử lý đầu vào người dùng, **catch cụ thể `DateTimeParseException`** là lựa chọn dễ kiểm soát. Không catch mọi `RuntimeException` rồi trả “ngày sai” vì nó che giấu bug như `NullPointerException` do code, lỗi driver hoặc cấu hình formatter.

Nếu cần phân loại dữ liệu không hợp lệ **đã được tạo trực tiếp từ field** (không phải chuỗi), có thể xử lý `DateTimeException` ở một lớp validation chung với thông tin nguồn rõ ràng. Nhưng đừng vì thế coi mọi `DateTimeException` là lỗi format text.

### 12.1. `getCause()` và lớp exception lồng nhau

Khi parser đọc được trường nhưng không resolve được ngày, `getCause()` có thể chứa lỗi từ bước tạo ngày (ví dụ ngày ngoài tháng). Khi parse bị sai dấu phân cách, cause có thể là `null`. Một xử lý an toàn:

```java
try {
    return LocalDate.parse(input, formatter);
} catch (DateTimeParseException ex) {
    Throwable cause = ex.getCause();
    // Phân loại/ghi nhận cause trong log bảo vệ;
    // không phụ thuộc cause luôn có và không lộ stack trace.
    throw new InvalidDateInputException("INVALID_DATE", ex);
}
```

Đây là **snippet kiến trúc**, yêu cầu lớp `InvalidDateInputException` do ứng dụng tự định nghĩa, biến `input`/`formatter` và một method có kiểu trả `LocalDate`. Mã không độc lập; phần runnable mục 10 dùng `IllegalArgumentException`/error code đơn giản để minh họa.

### 12.2. Đừng biến lỗi parse thành fallback “ngày hôm nay”

`LocalDate.now()` là ngày hiện tại theo đồng hồ/múi giờ; nó không có liên hệ với chuỗi sai. Gán nó thay input mà người dùng đã nhập có thể phá lịch thanh toán, ngày sinh và dữ liệu audit. Chỉ dùng một fallback nếu **domain contract nói rõ giá trị mặc định** và người dùng hiểu quyết định đó.

## 13. Thiết kế endpoint/API để thông tin lỗi có cấu trúc

Nếu API cần nhận một ngày theo ISO:

```json
{
  "invoiceDate": "2024-05-20"
}
```

Một response lỗi tham khảo:

```json
{
  "error": "INVALID_DATE",
  "field": "invoiceDate",
  "message": "Ngày không hợp lệ. Hãy nhập theo dạng năm-tháng-ngày.",
  "expectedFormat": "uuuu-MM-dd"
}
```

Đây là **ví dụ contract do ứng dụng thiết kế**, không phải JSON được `DateTimeParseException` tự sinh. Không tự đưa `errorIndex` vào mọi response, vì index kỹ thuật có thể không giúp người dùng sửa lỗi semantic; với UI có caret highlighting, có thể đính kèm index **đã kiểm tra miền**.

### 13.1. Lớp xử lý nên ở đâu?

Một luồng xử lý tốt:

```text
Request JSON / form / CSV
         |
         v
Kiểm tra null / độ dài / kiểu dữ liệu
         |
         v
Formatter được cấu hình tường minh
(uuuu-MM-dd, STRICT, locale/zone nếu cần)
         |
   +-----+------------------+
   |                        |
Parse thành LocalDate       DateTimeParseException
   |                        |
   v                        v
Xử lý nghiệp vụ         Map sang INVALID_DATE
                             |
                             v
                       HTTP 400 / field error
                       (không gửi raw input/stack trace)
```

Với JSON, framework có thể wrap lỗi parse vào ngoại lệ binding/deserialization của riêng nó. Điều này không làm thay đổi ngữ nghĩa `DateTimeParseException` ở tầng `java.time`; nhưng tầng endpoint phải biết nó nằm trong cấu trúc lỗi nào để mapping chính xác.

### 13.2. Lỗi ngày và lỗi logic nghiệp vụ nên tách biệt

Ngày `2024-05-20` có thể parse hoàn toàn hợp lệ nhưng vẫn bị từ chối vì:

- Đơn đặt hàng không được đặt vào ngày nghỉ.
- Ngày thanh toán nằm ngoài kỳ kế toán.
- Ngày kết thúc nhỏ hơn ngày bắt đầu.
- Người dùng không có quyền sửa kỳ đã chốt.

Các lý do này **không phải DateTimeParseException**. Hãy trả error code nghiệp vụ riêng như `OUTSIDE_BILLING_PERIOD` hoặc `END_BEFORE_START`. Việc phân biệt giúp frontend đưa hướng dẫn đúng, hỗ trợ metrics và tránh làm khó việc sửa lỗi.

## 14. Hiệu năng, an toàn luồng và xử lý dữ liệu lớn

### 14.1. `DateTimeFormatter` là immutable và thread-safe

Các formatter Java thời hiện đại như `DateTimeFormatter` có thiết kế **bất biến** và có thể được dùng lại giữa các thread. Nếu parse cùng một định dạng nhiều lần, có thể khai báo `static final DateTimeFormatter`:

```java
private static final DateTimeFormatter STRICT_ISO =
    DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Đây là snippet một trường lớp. Không cần dựng lại formatter trong mỗi lần parse để tránh vấn đề đồng bộ. `DateTimeFormatterBuilder` là **builder để cấu hình**, sau khi tạo xong formatter thì dùng formatter đã xây dựng; đừng coi một builder mutable đang được sửa là đối tượng chia sẻ thread-safe.

### 14.2. Giới hạn input trước khi parse

Một endpoint chỉ chấp nhận `uuuu-MM-dd` thường không nên nhận một chuỗi hàng triệu ký tự. Kiểm tra độ dài theo contract giúp tránh chi phí xử lý và việc log nguyên đầu vào làm tăng rủi ro. Với năm ISO có thể lớn hơn bốn chữ số nếu domain hỗ trợ, giới hạn nên được thiết kế **theo domain**, không cắt cứng độ dài `10` một cách máy móc cho mọi trường hợp ngày.

Không cố tối ưu bằng một regex tự viết thay hoàn toàn việc resolve ngày; regex kiểm tra ký tự cơ bản không tự biết số ngày thực tế trong tháng 2 hay năm nhuận.

### 14.3. Phân tách input normalization và validation

Nếu ứng dụng muốn cho phép `" 2024-05-20 "` bằng cách trim, hãy quy định tường minh, dùng chuỗi sau trim để parse và giữ mối quan hệ với input gốc để báo lỗi đúng. Nếu không cho phép khoảng trắng, strict parser nên từ chối. Nếu chuyển full-width digits hoặc tên tháng locale khác, phải có test round-trip và không tự bỏ dữ liệu.

### 14.4. Nhận lỗi có cấu trúc trong xử lý hàng loạt

Khi đọc file CSV có 1000 dòng, một lỗi ngày có thể cần **ghi nhận theo từng dòng** thay vì dừng cả import. Kết quả có thể chứa:

```text
line=17, column=invoiceDate, code=INVALID_DATE,
errorIndex=5, expectedFormat=uuuu-MM-dd
```

Đây là bản ghi lỗi minh họa. Với dữ liệu nhạy cảm, không lưu nguyên toàn bộ cột raw date nếu không cần. Để giữ tính nhất quán, xác định chính sách “import tất cả dòng hợp lệ” hay “all-or-nothing” ở tầng nghiệp vụ; `DateTimeParseException` tự nó không phải transaction manager.

## 15. Lỗi thường gặp và cách sửa

### 15.1. Chỉ catch `DateTimeException` rồi coi mọi lỗi là ngày nhập sai

Lỗi xây formatter hoặc lỗi nghiệp vụ có thể không phải input parse. **Giải pháp:** catch cụ thể `DateTimeParseException` tại tầng nhận chuỗi, xử lý những lỗi code/config riêng.

### 15.2. Đọc `getErrorIndex` như “cột tháng/ngày bị lỗi”

Lỗi resolving có thể báo vị trí bắt đầu chuỗi, dù phần sai về logic ở cuối. **Giải pháp:** dùng chỉ số như thông tin chẩn đoán, không dùng làm bằng chứng duy nhất cho field lỗi.

### 15.3. Dùng `yyyy` thay vì `uuuu` trong ISO strict

`yyyy` là year-of-era và có thể thiếu thông tin era trong strict resolver. **Giải pháp:** dùng `uuuu-MM-dd` hoặc `ISO_LOCAL_DATE` nếu hợp đồng là ISO proleptic year.

### 15.4. Dùng `YYYY-MM-dd` để viết năm lịch

`YYYY` là week-based-year theo locale, có thể lệch năm tại tuần giao năm. **Giải pháp:** dùng `uuuu`/`y` đúng ngữ nghĩa, tránh `Y` nếu không mô hình hóa week-year.

### 15.5. Dựa vào `ofPattern` mặc định để kiểm tra strict

Formatter từ `ofPattern` mặc định sử dụng `SMART` trong pha resolve. **Giải pháp:** gọi `withResolverStyle(ResolverStyle.STRICT)` khi yêu cầu ngày chính xác.

### 15.6. Lẫn `parseStrict` với resolver `STRICT`

`parseStrict` là pha đọc text, không thay thế bước resolve lịch. **Giải pháp:** xác định rõ cả hai nếu cần, nhất là khi dùng `DateTimeFormatterBuilder`.

### 15.7. Cắt chuỗi để bỏ phần thừa

Input `2024-05-20XYZ` bị coi như `2024-05-20` nếu tự cắt 10 ký tự. **Giải pháp:** chỉ chấp nhận toàn bộ chuỗi theo contract hoặc định nghĩa định dạng có hậu tố rõ.

### 15.8. Log nguyên `getMessage()` và `getParsedString()`

Hai trường có thể chứa input và dữ liệu nhạy cảm. **Giải pháp:** log metadata có kiểm soát, mask/redact, đặt giới hạn độ dài, không lộ stack trace qua response.

### 15.9. Để locale mặc định quyết định tên tháng

`05 May 2024` là tên tháng tiếng Anh. **Giải pháp:** truyền `Locale.ENGLISH` hoặc dùng ISO numeric, không trông chờ máy chủ luôn cùng locale.

### 15.10. Tự thêm ngày cho chuỗi `YearMonth`

`2024-05` không có ngày. **Giải pháp:** trả `YearMonth` khi phù hợp; chỉ dùng `parseDefaulting(DAY_OF_MONTH, 1)` nếu hợp đồng định nghĩa ngày 01.

### 15.11. Tự thêm UTC cho `LocalDateTime`

Chuỗi local không offset chưa tạo được instant. **Giải pháp:** chọn đúng `LocalDateTime` hoặc yêu cầu offset/ZoneId theo domain, không gắn UTC hoặc system default tùy tiện.

### 15.12. Chỉ test chuỗi hợp lệ

Unit test phải có tháng 13, ngày 0, ngày 31/4, năm không nhuận, string dư, thiếu field, locale khác, null và input quá dài. **Giải pháp:** test cả cú pháp lẫn resolution và error mapping.

### 15.13. So exact thông báo `getMessage()`

Nội dung message do JDK tạo là chẩn đoán, không phải contract UI ổn định. **Giải pháp:** test exception type, giá trị, chỉ số trong trường hợp thích hợp, và error code do ứng dụng tự định nghĩa.

## 16. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** `DateTimeParseException` là checked hay unchecked exception?  
**Đáp án:** unchecked, kế thừa `DateTimeException`, thuộc dòng `RuntimeException`.

**Câu 2.** Hai getter đặc thù của nó là gì?  
**Đáp án:** `getParsedString()` và `getErrorIndex()`; ngoài ra có `getMessage()`/`getCause()` kế thừa.

**Câu 3.** Vì sao `"2023-02-29"` có thể vượt qua pha đọc ký tự nhưng vẫn lỗi?  
**Đáp án:** năm, tháng, ngày có đúng dạng số nhưng không resolve thành `LocalDate` hợp lệ vì 2023 không nhuận.

**Câu 4.** `withResolverStyle(STRICT)` khác `parseStrict()` thế nào?  
**Đáp án:** `STRICT` áp dụng ở pha resolve trường lịch; `parseStrict()` cấu hình độ nghiêm ngặt đọc văn bản trong builder.

**Câu 5.** Nếu formatter dùng SMART với `2023-02-29`, điều gì có thể xảy ra?  
**Đáp án:** ngày được điều chỉnh thành `2023-02-28`; không phù hợp nếu domain cần từ chối dữ liệu người dùng không đúng.

**Câu 6.** `yyyy` và `uuuu` có cùng ý nghĩa trong pattern không?  
**Đáp án:** không. `yyyy` là year-of-era; `uuuu` là proleptic year. Strict ISO date thường dùng `uuuu`.

**Câu 7.** Có nên gửi `getMessage()` nguyên văn trong JSON lỗi không?  
**Đáp án:** không nên, vì nó là thông điệp kỹ thuật và có thể chứa chuỗi input.

**Câu 8.** `getErrorIndex() == 0` có chắc “ký tự đầu tiên sai” không?  
**Đáp án:** không. Lỗi resolving có thể được báo ở đầu giá trị dù phần sai logic ở trường khác.

**Câu 9.** Input `2024-05` phù hợp `YearMonth` hay `LocalDate` hơn?  
**Đáp án:** `YearMonth` nếu chỉ có năm và tháng. Muốn `LocalDate` phải định nghĩa ngày mặc định có chủ đích.

**Câu 10.** Vì sao không tự cắt hậu tố của chuỗi sai định dạng?  
**Đáp án:** làm mất khả năng phát hiện dữ liệu dư/sai contract; có thể bỏ mất offset, giờ hoặc dữ liệu quan trọng.

**Câu 11.** `DateTimeFormatter` có dùng chung giữa các thread được không?  
**Đáp án:** có, formatter bất biến và thread-safe; builder cấu hình không nên bị mutate đồng thời.

**Câu 12.** Parser nhận chuỗi `2024-05-20T09:30+07:00` thì nên tạo kiểu nào?  
**Đáp án:** `OffsetDateTime` nếu contract giữ offset; chuyển thành `Instant` nếu muốn thời điểm tuyệt đối.

**Câu 13.** Chuỗi parse lỗi có thể chứa dữ liệu nhạy cảm không?  
**Đáp án:** có. Vì vậy không log tràn lan `getParsedString()`, không leak raw input qua error message.

**Câu 14.** Nếu truyền `null` vào `LocalDate.parse`, có chắc nhận `DateTimeParseException` không?  
**Đáp án:** không. API yêu cầu text không null và có thể ném `NullPointerException`; hãy validate null trước.

**Câu 15.** Có nên bắt lỗi parse rồi thay bằng `LocalDate.now()` không?  
**Đáp án:** không, trừ khi domain contract thật sự quy định fallback ấy và người dùng biết.

## 17. Tài liệu tham khảo chính thức

Các API sau thuộc `java.time`/`java.time.format` từ Java 8 và vẫn được duy trì trong Java hiện đại:

- [`DateTimeParseException` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeParseException.html): hai getter `getParsedString()` và `getErrorIndex()`, constructor và quan hệ kế thừa.
- [`DateTimeFormatter` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): hai pha parse/resolve, `parse(CharSequence)`, `parseUnresolved`, formatter chuẩn ISO và kiểu trả về.
- [`DateTimeFormatterBuilder` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): `parseStrict`, `parseLenient`, `parseCaseInsensitive`, `parseDefaulting`.
- [`ResolverStyle` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`/`SMART`/`LENIENT` và cách xử lý ngày không tồn tại.
- [`LocalDate` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html): `parse`, `of` và quy tắc năm nhuận.
- [`OffsetDateTime` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html): input có offset và chuyển đổi `toInstant()`.
- [`YearMonth` và `MonthDay` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/YearMonth.html): các kiểu có độ chính xác từng phần, không ép thành LocalDate khi thiếu trường.
