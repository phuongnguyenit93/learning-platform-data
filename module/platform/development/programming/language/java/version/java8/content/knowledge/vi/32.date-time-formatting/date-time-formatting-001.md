# DateTimeFormatter và các hằng định dạng ISO trong Java

Trong `java.time`, **`DateTimeFormatter`** dùng để chuyển một giá trị ngày giờ thành chuỗi (**format**) hoặc đọc chuỗi về giá trị ngày giờ (**parse**). Từ **Java 8**, thư viện có các hằng định dạng ISO dùng ngay như `ISO_LOCAL_DATE`, `ISO_LOCAL_DATE_TIME`, `ISO_OFFSET_DATE_TIME`, `ISO_ZONED_DATE_TIME` và `ISO_INSTANT`. Chúng giúp ứng dụng mô tả rõ kiểu dữ liệu ngày giờ được trao đổi, thay vì tự ghép chuỗi hoặc tự cắt ký tự.

Ví dụ:

~~~java
LocalDate day = LocalDate.of(2024, 2, 29);
String text = DateTimeFormatter.ISO_LOCAL_DATE.format(day);
// text = "2024-02-29"

LocalDate parsed =
    LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
// parsed.equals(day) == true
~~~

Đoạn trên là **mã minh họa**, cần import `LocalDate` và `DateTimeFormatter` trong lớp Java hoàn chỉnh.

**Điểm cốt lõi:** formatter chỉ quyết định **cách biểu diễn/đọc các trường thời gian**. Nó không tự bổ sung múi giờ vào `LocalDateTime`, không biến một ngày lịch thành một `Instant` nếu thiếu offset/zone, và không giải quyết mọi quy tắc DST theo ý định nghiệp vụ. Chọn đúng formatter phải đi cùng **chọn đúng kiểu temporal**.

Các API trình bày trong bài **vẫn được hỗ trợ trong các JDK hiện đại**. Ví dụ chính sử dụng API có từ Java 8 và chạy được trên JDK 17+, đồng thời lưu ý những điểm dễ nhầm giữa ISO-8601, ISO-like của Java, formatter có sẵn và formatter tùy chỉnh.

## 1. Phân biệt format, parse và kiểu giá trị

`DateTimeFormatter` có hai nhóm thao tác:

1. **Format:** nhận `TemporalAccessor` hoặc kiểu ngày giờ tương ứng, trả một `String`. Ví dụ `formatter.format(instant)`.
2. **Parse:** nhận một chuỗi và tạo dữ liệu temporal; sau đó có thể dùng `LocalDate.parse`, `OffsetDateTime.parse`, `Instant.from` hoặc một `TemporalQuery` để chuyển thành kiểu ứng dụng cần.

~~~java
LocalDateTime local =
    LocalDateTime.of(2024, 2, 29, 9, 30, 45);

String encoded =
    DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local);
// "2024-02-29T09:30:45"

LocalDateTime decoded =
    LocalDateTime.parse(
        encoded, DateTimeFormatter.ISO_LOCAL_DATE_TIME);
~~~

Đoạn trên là mã minh họa. `LocalDateTime` có **ngày và đồng hồ địa phương**, nhưng **không có offset hay ZoneId**. Chuỗi `2024-02-29T09:30:45` chưa nói đó là 09:30 ở Việt Nam, Nhật Bản hay UTC.

Ngược lại:

~~~text
2024-02-29T09:30:45+07:00
2024-02-29T02:30:45Z
~~~

Hai chuỗi này có thể biểu diễn **cùng một instant**: 09:30:45 ở offset `+07:00` tương ứng 02:30:45 UTC. Dùng `OffsetDateTime` hoặc `Instant` để thể hiện đầy đủ thông tin cần so thời điểm thực, không chỉ chọn một formatter có chữ “ISO”.

## 2. Bảng các hằng `DateTimeFormatter` ISO được dùng nhiều

Các hằng sau thuộc `java.time.format.DateTimeFormatter` và đã có từ Java 8:

| Hằng | Ví dụ văn bản | Ý nghĩa và kiểu thường dùng |
| --- | --- | --- |
| `ISO_LOCAL_DATE` | `2024-02-29` | Ngày ISO không có offset, dùng với `LocalDate` |
| `ISO_LOCAL_TIME` | `09:30:45` | Đồng hồ địa phương không có offset, dùng với `LocalTime` |
| `ISO_LOCAL_DATE_TIME` | `2024-02-29T09:30:45` | Ngày và giờ địa phương, dùng với `LocalDateTime` |
| `ISO_OFFSET_DATE` | `2024-02-29+07:00` | Ngày có offset; lưu ý **không có giờ cụ thể** |
| `ISO_OFFSET_TIME` | `09:30:45+07:00` | Giờ trong ngày + offset, dùng với `OffsetTime` |
| `ISO_OFFSET_DATE_TIME` | `2024-02-29T09:30:45+07:00` | Ngày giờ + offset, dùng với `OffsetDateTime` |
| `ISO_ZONED_DATE_TIME` | `2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]` | Dạng ISO-like có region zone, dùng với `ZonedDateTime` |
| `ISO_INSTANT` | `2024-02-29T02:30:45Z` | Một instant theo UTC, dùng với `Instant` |
| `ISO_DATE` | `2024-02-29` hoặc kèm offset | Ngày ISO có phần offset **tùy chọn** |
| `ISO_TIME` | `09:30:45` hoặc kèm offset | Giờ ISO có phần offset **tùy chọn** |
| `ISO_DATE_TIME` | `2024-02-29T09:30:45` hoặc có offset/zone | Dạng tổng quát với các trường tùy chọn, có thể cần `parseBest` |
| `ISO_ORDINAL_DATE` | `2024-060` | Năm và **ngày thứ 60 trong năm** (29/2 năm nhuận) |
| `ISO_WEEK_DATE` | `2024-W09-4` | Năm theo ISO week-based-year, tuần thứ 9, thứ Năm |
| `BASIC_ISO_DATE` | `20240229` | Dạng compact không có dấu gạch nối; có thể có offset tùy chọn |

**`RFC_1123_DATE_TIME` cũng là hằng hiện hành**, nhưng **không phải hằng ISO**: nó phục vụ định dạng theo RFC 1123, thường gặp trong một số header/protocol internet. Không xếp nó nhầm thành ISO-8601.

### Những điều bảng này không có nghĩa

- Không phải tất cả hằng ISO đều chấp nhận cùng một kiểu `TemporalAccessor`.
- Không phải `ISO_DATE` luôn có offset; phần offset là **optional**.
- Không phải `ISO_DATE_TIME` có đủ thông tin để suy ra một instant; bản local date-time không có offset.
- `ISO_ZONED_DATE_TIME` thêm phần `[Region/City]`, **đây là phần mở rộng ISO-like của Java, không thuộc cú pháp ISO-8601 thuần**. Nếu giao thức đối tác chỉ chấp nhận ISO-8601 chuẩn, cần thống nhất schema trước khi gửi.
- `ISO_WEEK_DATE` dùng **week-based-year**; tại ranh giới tháng 12/tháng 1, năm của tuần ISO có thể khác năm lịch `YEAR`.

Các formatter ISO dựng sẵn chủ yếu dùng **`ResolverStyle.STRICT`**: khi parse, chúng đòi các trường ngày/giờ hợp lệ theo tiêu chuẩn tương ứng. Điều này khác với `ofPattern(...)` mặc định dùng `ResolverStyle.SMART`, sẽ được phân tích kỹ ở phần sau.

## 3. `ISO_LOCAL_DATE`, `ISO_LOCAL_TIME` và `ISO_LOCAL_DATE_TIME`

### 3.1. Ngày địa phương

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

String value =
    leapDay.format(DateTimeFormatter.ISO_LOCAL_DATE);
// "2024-02-29"

LocalDate roundTrip =
    LocalDate.parse(value, DateTimeFormatter.ISO_LOCAL_DATE);
~~~

Dạng `yyyy-MM-dd` nhìn giống ngày ISO thông thường, nhưng khi tự viết pattern cho parsing strict cần hiểu sự khác nhau giữa ký hiệu `yyyy` (year-of-era) và `uuuu` (proleptic year). Hằng ISO của JDK đã được thiết kế chuẩn xác; đừng thay bằng pattern tự viết chỉ vì ký tự hiển thị trông tương tự.

`ISO_LOCAL_DATE` không kèm múi giờ; lưu **ngày sinh**, **ngày đến hạn**, **ngày nghỉ** dạng lịch thường hợp lý, còn log một giao dịch tại instant cụ thể thì chưa đủ.

### 3.2. Giờ địa phương

~~~java
LocalTime time = LocalTime.of(9, 30, 45);
String value = DateTimeFormatter.ISO_LOCAL_TIME.format(time);
// "09:30:45"
~~~

`LocalTime` không có năm-tháng-ngày hoặc offset. Nếu một thiết bị ghi “09:30:45” mà không ghi thêm date/offset, không thể suy ra duy nhất một `Instant`.

Với phần giây bằng 0, định dạng ISO có thể bỏ giây:

~~~java
LocalTime t = LocalTime.of(9, 30);
String value = DateTimeFormatter.ISO_LOCAL_TIME.format(t);
// "09:30"
~~~

Không mặc định ISO_LOCAL_TIME luôn có đúng tám ký tự `HH:mm:ss`; biểu diễn có thể có giây và phần nano khi cần. Nếu giao thức bắt buộc đúng sáu chữ số `HHmmss` hoặc luôn có giây, thiết kế pattern cố định thay vì suy từ hằng ISO có tính linh hoạt.

### 3.3. Ngày giờ địa phương

~~~java
LocalDateTime meeting =
    LocalDateTime.of(2024, 2, 29, 9, 30, 45);

String value =
    DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(meeting);
// "2024-02-29T09:30:45"
~~~

Chữ `T` phân tách phần date và time. Cặp `LocalDateTime` + `ISO_LOCAL_DATE_TIME` rất phù hợp khi ứng dụng thực sự muốn **giờ theo lịch địa phương** (ví dụ lịch mở cửa hoặc lựa chọn 09:30 từ giao diện). Nhưng nếu dữ liệu phải thể hiện một sự kiện đã xảy ra trên dòng thời gian toàn cầu, cần biết thêm zone/offset.

## 4. `ISO_OFFSET_DATE_TIME` và sự khác nhau giữa offset với zone

Một `OffsetDateTime` gồm local date-time và offset cụ thể so với UTC:

~~~java
OffsetDateTime event =
    OffsetDateTime.parse(
        "2024-02-29T09:30:45+07:00",
        DateTimeFormatter.ISO_OFFSET_DATE_TIME
    );

Instant moment = event.toInstant();
// 2024-02-29T02:30:45Z
~~~

Bởi vì đã có offset `+07:00`, ánh xạ sang instant không mơ hồ. Đây là lựa chọn phù hợp cho trao đổi timestamp giữa dịch vụ nếu giao thức cần giữ **local fields + offset**.

### 4.1. Một instant, nhiều biểu diễn offset

~~~java
Instant moment =
    Instant.parse("2024-02-29T02:30:45Z");

OffsetDateTime plusSeven =
    moment.atOffset(ZoneOffset.ofHours(7));

OffsetDateTime utc =
    moment.atOffset(ZoneOffset.UTC);
~~~

Hai giá trị có thể hiển thị khác nhau nhưng `plusSeven.isEqual(utc)` là `true` vì cùng một instant; `plusSeven.equals(utc)` có thể là `false` do local fields/offset khác. Formatter chỉ viết ra representation mà object đang chứa, không quyết định **hai event cùng thời điểm hay không**.

### 4.2. Chỉ offset không đủ cho lịch vùng trong tương lai

`+07:00` và `Europe/Paris` là hai loại thông tin khác nhau. `ZoneOffset` là độ lệch **cố định**. `ZoneId` vùng có bộ quy tắc có thể đổi offset theo mùa hoặc theo luật quốc gia. Nếu cuộc họp tương lai phải diễn ra lúc “09:30 giờ Paris” qua các kỳ DST, cần giữ region zone, không thay thế bằng offset lấy từ một ngày bất kỳ.

**Hãy chọn dữ liệu theo nghiệp vụ:** event đã xảy ra → `Instant` hoặc `OffsetDateTime`; cuộc hẹn theo giờ vùng → `LocalDateTime + ZoneId` và quy tắc DST/`ZonedDateTime` khi đã giải quyết.

## 5. `ISO_ZONED_DATE_TIME`: chuỗi có `[ZoneId]` của Java

`ZonedDateTime` gắn ngày-giờ địa phương với offset đã được xác định và region zone:

~~~java
ZonedDateTime inHcm =
    ZonedDateTime.of(
        2024, 2, 29, 9, 30, 45, 0,
        ZoneId.of("Asia/Ho_Chi_Minh")
    );

String text =
    DateTimeFormatter.ISO_ZONED_DATE_TIME.format(inHcm);
// 2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]
~~~

Lưu ý:

- Phần `+07:00` là **offset tại instant đó**.
- Phần `[Asia/Ho_Chi_Minh]` là **region ZoneId**, mang ngữ nghĩa về rules theo vùng.
- `[Region/City]` là phần mở rộng **ISO-like** của định dạng Java, **không phải thành phần tiêu chuẩn của ISO-8601**.
- Đối tác nhận dữ liệu có thể chỉ hiểu `2024-02-29T09:30:45+07:00`; khi trao đổi qua JSON/protocol, cần thỏa thuận định dạng và việc mang zone riêng thành field khác nếu cần.

Parse rõ kiểu:

~~~java
ZonedDateTime restored = ZonedDateTime.parse(
    text, DateTimeFormatter.ISO_ZONED_DATE_TIME
);
~~~

Đoạn này dùng biến `text` ở ví dụ trên, không độc lập. Nếu có phần `ZoneId` thuộc một vùng có DST, việc xác định local date-time có thể gặp **gap** hoặc **overlap**; chính sách giải quyết mơ hồ thuộc `ZonedDateTime`/`ZoneRules` và nghiệp vụ, không chỉ thuộc formatter.

## 6. `ISO_INSTANT`: biểu diễn thời điểm UTC bằng `Z`

`ISO_INSTANT` làm việc với một `Instant` và xuất dạng UTC có ký tự `Z`:

~~~java
Instant instant =
    Instant.parse("2024-02-29T02:30:45Z");

String encoded =
    DateTimeFormatter.ISO_INSTANT.format(instant);
// "2024-02-29T02:30:45Z"
~~~

`Z` thể hiện offset 0 so với UTC. Khi parse, `ISO_INSTANT` có thể chuyển chuỗi có offset hợp lệ về cùng instant UTC theo hợp đồng formatter.

**Độ chính xác:** formatter xuất giây và phần nanosecond theo nhu cầu, với **0, 3, 6 hoặc 9 chữ số thập phân** khi format:

~~~java
Instant precise =
    Instant.parse("2024-02-29T02:30:45.123456789Z");

String encoded =
    DateTimeFormatter.ISO_INSTANT.format(precise);
// "2024-02-29T02:30:45.123456789Z"
~~~

Vì phần nano có thể được biểu diễn với độ dài phù hợp, đừng giả định mọi chuỗi ISO_INSTANT đều đúng 20 ký tự hoặc luôn có `.000`.

### 6.1. Hằng ISO_INSTANT và API của Instant

~~~java
Instant moment =
    Instant.parse("2024-02-29T02:30:45Z");

String viaToString = moment.toString();
String viaFormatter =
    DateTimeFormatter.ISO_INSTANT.format(moment);
~~~

Cả hai cung cấp dạng ISO UTC phù hợp cho trường hợp này. Việc dùng `Instant`/`ISO_INSTANT` tốt hơn kiểu dữ liệu chỉ có `LocalDateTime` nếu mục tiêu là lưu **mốc sự kiện toàn cầu**, bởi một local date-time không chứa offset.

### 6.2. Khi format một Instant sang giờ địa phương

`DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")` **không tự có zone** khi format một `Instant` vì `Instant` không mang các trường lịch địa phương như tháng/ngày/giờ. Cách đúng là gắn ZoneId thông qua `withZone` hoặc chuyển sang `ZonedDateTime`:

~~~java
Instant moment =
    Instant.parse("2024-02-29T02:30:45Z");

DateTimeFormatter inHcm =
    DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm XXX", Locale.ROOT)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String text = inHcm.format(moment);
// "2024-02-29 09:30 +07:00"
~~~

Đoạn trên là minh họa, cần import `Locale` cùng các kiểu java.time. Việc chọn ZoneId phải rõ ràng và có chủ ý; đừng để kết quả phụ thuộc vào timezone mặc định của server nếu đây là hợp đồng API cần tái lập.

## 7. Các hằng ISO tổng quát và khi cần `parseBest`

### 7.1. `ISO_DATE`, `ISO_TIME`

`ISO_DATE` có ngày ISO và **có thể có offset**; `ISO_TIME` có giờ ISO và **có thể có offset**. Không nên dùng tên “DATE” hay “TIME” để suy rằng tất cả thông tin đủ cho một instant.

~~~java
LocalDate day = LocalDate.parse(
    "2024-02-29", DateTimeFormatter.ISO_DATE
);

OffsetTime withOffset = OffsetTime.parse(
    "09:30:45+07:00", DateTimeFormatter.ISO_TIME
);
~~~

Chọn kiểu `OffsetTime` khi muốn giữ offset cùng giờ, `LocalTime` khi cố ý bỏ offset. `OffsetTime` vẫn **không có ngày**, nên không đại diện đầy đủ cho một event duy nhất trên lịch.

### 7.2. `ISO_DATE_TIME` có thành phần tùy chọn

`ISO_DATE_TIME` chấp nhận các dạng local, offset hoặc có zone:

~~~text
2024-02-29T09:30:45
2024-02-29T09:30:45+07:00
2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]
~~~

Nếu không biết trước biến thể mà input chứa, có thể dùng `parseBest` để thử các kiểu từ **cụ thể nhất đến ít thông tin nhất**:

~~~java
TemporalAccessor parsed =
    DateTimeFormatter.ISO_DATE_TIME.parseBest(
        input,
        ZonedDateTime::from,
        OffsetDateTime::from,
        LocalDateTime::from
    );
~~~

Đây là **mã minh họa**, biến `input` đến từ nơi gọi và cần import `TemporalAccessor`/các kiểu java.time. Dữ liệu parse sẽ được truy vấn lần lượt theo thứ tự phương thức được đưa vào. Thứ tự query có ý nghĩa vì một đối tượng đã parse chứa offset có thể đủ thông tin cho nhiều kiểu.

**Khuyến nghị thiết kế API mới:** thường nên **chọn một schema rõ ràng** thay vì cho phép mọi biến thể tùy ý. Nếu bắt buộc có instant, yêu cầu offset/UTC trong input và parse sang `OffsetDateTime`/`Instant`; đừng nhận text thiếu offset rồi âm thầm suy từ zone mặc định của hệ điều hành.

### 7.3. ISO week date và ordinal date

`ISO_ORDINAL_DATE` viết **năm và ngày thứ N trong năm**:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

String ordinal =
    DateTimeFormatter.ISO_ORDINAL_DATE.format(leapDay);
// "2024-060"
~~~

`ISO_WEEK_DATE` viết **ISO week-based-year, số tuần và ngày trong tuần**:

~~~java
String week =
    DateTimeFormatter.ISO_WEEK_DATE.format(leapDay);
// "2024-W09-4"
~~~

Năm theo tuần ISO đôi khi khác **năm lịch** gần đầu/cuối năm. Không dùng `yyyy`/`uuuu` một cách máy móc khi hệ thống muốn báo cáo theo ISO week-based-year. Với dữ liệu báo cáo tuần, xác định rõ bộ quy tắc tuần và locale, tránh nhầm “tuần thứ 1” của lịch ISO với tuần theo ngôn ngữ/địa phương khác.

### 7.4. BASIC_ISO_DATE

`BASIC_ISO_DATE` là cách viết compact:

~~~java
LocalDate day = LocalDate.of(2024, 2, 29);

String basic =
    DateTimeFormatter.BASIC_ISO_DATE.format(day);
// "20240229"
~~~

Dạng này phù hợp khi giao thức quy định tám chữ số liền nhau, nhưng **đừng tự đoán** rằng chuỗi `20240229` có thể parse bằng `ISO_LOCAL_DATE`. Chọn formatter khớp schema dữ liệu.

## 8. `ofPattern` và các hằng ISO: khác nhau ở đâu?

Một khi hằng dựng sẵn khớp hợp đồng, thường **ưu tiên dùng hằng ISO** vì nhất quán, dễ nhận diện, xử lý các trường và resolver style được định nghĩa trong tài liệu. Khi cần văn bản hiển thị cho người dùng hoặc định dạng riêng của đối tác, dùng `DateTimeFormatter.ofPattern(...)`:

~~~java
DateTimeFormatter custom =
    DateTimeFormatter.ofPattern(
        "dd/MM/uuuu HH:mm", Locale.ROOT);

String shown = custom.format(
    LocalDateTime.of(2024, 2, 29, 9, 30));
// "29/02/2024 09:30"
~~~

**Hai mục tiêu khác nhau:** dữ liệu trao đổi giữa service thường dùng ISO-8601 có schema rõ ràng; dữ liệu hiển thị cho người dùng có thể dùng locale và format riêng. Không nên dùng tùy ý một chuỗi hiển thị để làm timestamp chuẩn toàn hệ thống.

### 8.1. Bảng ký hiệu pattern thường gặp

| Ký hiệu | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `u` / `uuuu` | Proleptic year | Thường thích hợp khi tự parse ngày ISO với STRICT |
| `y` / `yyyy` | Year-of-era | Dưới STRICT có thể cần thêm thông tin era |
| `Y` | Week-based-year | **Không** thay cho năm lịch `u` trong ngày thông thường |
| `M` / `MM` / `MMM` | Tháng dạng số hoặc chữ | `MMM` phụ thuộc locale |
| `d` / `dd` | Ngày trong tháng | Không phải day-of-year |
| `D` | Ngày thứ N trong năm | Không nhầm với `d` |
| `H` / `HH` | Giờ 0–23 | Thích hợp với giờ kiểu 24h |
| `h` / `hh` | Giờ 1–12 | Thường cần `a` (AM/PM) để rõ nghĩa |
| `m` | Phút trong giờ | Chữ **m thường**; `M` lớn là tháng |
| `s` | Giây trong phút | Không phải instant epoch-second |
| `S` | Fraction-of-second | Độ dài chữ S quy định số chữ số phần giây |
| `X` / `XX` / `XXX` | Offset dạng ISO có `Z` khi zero | Số chữ X quyết định cách viết dấu hai chấm/độ rộng |
| `x` | Offset có dạng số khi zero | Khác `X` ở cách hiển thị offset zero |
| `V` (thường `VV`) | Zone ID | Chỉ dùng khi temporal/formatter có ZoneId |
| `z` | Tên múi giờ dạng văn bản | Phụ thuộc locale/dữ liệu vùng |

Một lỗi phổ biến là viết `YYYY-MM-dd` thay cho `uuuu-MM-dd`. `YYYY` là **week-based-year**, có thể khác năm lịch ở ranh giới tháng 12/1. Ngày format thành năm khác với năm lịch có thể dẫn tới phân vùng dữ liệu sai.

### 8.2. `uuuu` và `yyyy` trong strict parsing

`ofPattern("yyyy-MM-dd")` dùng `year-of-era`; khi thiết lập `ResolverStyle.STRICT`, thiếu thông tin era có thể làm parse thất bại. `ofPattern("uuuu-MM-dd")` dùng proleptic year và thường rõ ràng hơn khi dữ liệu là ngày ISO không có era:

~~~java
DateTimeFormatter strict =
    DateTimeFormatter.ofPattern(
        "uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate valid = LocalDate.parse("2024-02-29", strict);
// 2024-02-29
~~~

Điều này **không có nghĩa `yyyy` luôn sai**: trong các định dạng có era hoặc giao diện hiển thị theo hệ lịch phù hợp, `y` là ký hiệu đúng. Điểm quan trọng là biết ngữ nghĩa từng ký tự và resolver style.

## 9. ResolverStyle: ISO dựng sẵn STRICT, custom thường SMART

Phân tích parsing gồm hai bước:

1. Nhận diện cấu trúc văn bản và trích các trường `YEAR`/`MONTH`/`DAY`/... theo formatter.
2. **Resolve** các trường đó thành một ngày giờ thực sự có hợp lệ hay không, theo `ResolverStyle`.

Các kiểu:

- **`STRICT`:** yêu cầu ngày giờ hợp lệ, không tự chấp nhận “30/02”.
- **`SMART`:** có thể điều chỉnh một số trường ngày đến giá trị hợp lý tùy trường hợp, ví dụ khi ngày tháng vượt quá số ngày của tháng.
- **`LENIENT`:** cho phép một số phép chuẩn hóa giá trị trường ngoài phạm vi bằng toán lịch; không phù hợp khi input cần được kiểm tra nghiêm ngặt.

Các hằng ISO dựng sẵn chủ yếu dùng `STRICT`. `DateTimeFormatter.ofPattern(...)` theo mặc định dùng `SMART`. Ví dụ:

~~~java
DateTimeFormatter smart =
    DateTimeFormatter.ofPattern(
        "uuuu-MM-dd", Locale.ROOT);

DateTimeFormatter strict =
    smart.withResolverStyle(ResolverStyle.STRICT);

LocalDate adjusted =
    LocalDate.parse("2024-02-30", smart);
// 2024-02-29

// LocalDate.parse("2024-02-30", strict);
// ném DateTimeParseException
~~~

Đây là minh họa của behavior `SMART` trong trường hợp ngày 30/2, không phải quy tắc “mọi dữ liệu sai đều được chữa”. `withResolverStyle` trả **formatter mới**, không sửa `smart` vì `DateTimeFormatter` immutable.

**Khi parse dữ liệu từ API, giao dịch hay đăng ký lịch:** thường nên chọn `STRICT` để bắt lỗi ở biên, ghi nhận input sai và yêu cầu sửa, thay vì âm thầm chỉnh ngày mà người dùng không biết. Nếu quy tắc nghiệp vụ cố ý chấp nhận ngày vượt giới hạn và tự điều chỉnh, thiết kế/test policy đó rõ ràng.

### 9.1. Parse lỗi ném `DateTimeParseException`

~~~java
try {
    LocalDate.parse(
        "2023-02-29",
        DateTimeFormatter.ISO_LOCAL_DATE
    );
} catch (DateTimeParseException ex) {
    System.out.println("Ngày không hợp lệ");
}
~~~

`2023` không phải năm nhuận. Khi nhận input từ người dùng, nên chỉ ra trường không hợp lệ, lưu log đúng mức độ nhạy cảm và trả lỗi có thể xử lý; không bắt mọi ngoại lệ rồi thay bằng một ngày tùy tiện.

Một lỗi format khác: dùng formatter yêu cầu **offset** với `LocalDateTime` chỉ có ngày/giờ. Nó có thể ném `DateTimeException` hoặc subtype liên quan vì thiếu trường cần thiết. Giải pháp là chọn formatter phù hợp kiểu, hoặc cung cấp offset/zone có ngữ nghĩa thực sự.

## 10. Locale, chữ tháng và định dạng ISO

Các hằng ISO không nên bị thay đổi ngữ nghĩa chỉ vì máy chạy có locale khác. Dạng ISO cho trao đổi máy–máy cần ổn định về schema. Ngược lại, định dạng thân thiện với người dùng nên chọn locale có chủ đích:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

DateTimeFormatter english =
    DateTimeFormatter.ofPattern(
        "dd MMM uuuu", Locale.ENGLISH);

String shown = english.format(date);
// "29 Feb 2024"
~~~

Với `ofLocalizedDate` hoặc `ofLocalizedDateTime`, mẫu hiển thị có thể **phụ thuộc locale, dữ liệu CLDR/runtime và lựa chọn format style**. Đừng hardcode output của `FormatStyle.LONG` cho mọi máy mà không cố định locale và môi trường test.

~~~java
DateTimeFormatter localized =
    DateTimeFormatter
        .ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"));
~~~

Đây là đoạn minh họa; output chính xác phụ thuộc dữ liệu locale của môi trường. Không dùng `ofLocalizedDate` làm định dạng lưu trữ máy–máy chỉ vì nó trông dễ đọc trong một địa phương.

### `RFC_1123_DATE_TIME` là một lựa chọn khác, không phải ISO

Một số protocol như HTTP dùng ngày giờ theo RFC 1123:

~~~java
DateTimeFormatter httpStyle =
    DateTimeFormatter.RFC_1123_DATE_TIME;
~~~

Hằng này vẫn có giá trị khi giao thức **quy định** RFC 1123, nhưng không nên dùng thay `ISO_INSTANT` để thiết kế schema JSON ISO mới. Ngược lại, nếu đối tác yêu cầu RFC 1123, không nên gửi ISO vì “ISO hiện đại hơn”; phải tuân thủ protocol đã được thống nhất.

## 11. DateTimeFormatter là immutable và dùng được giữa nhiều luồng

`DateTimeFormatter` được tài liệu Java xác định **immutable và thread-safe**. Có thể dùng một formatter cho nhiều request/thread sau khi cấu hình xong, chẳng hạn:

~~~java
private static final DateTimeFormatter API_FORMAT =
    DateTimeFormatter.ISO_OFFSET_DATE_TIME;
~~~

Phương thức `format` và `parse` không sửa cấu hình của formatter dùng chung. `withZone`, `withLocale`, `withResolverStyle`, `withChronology` trả **một formatter mới về mặt ngữ nghĩa**:

~~~java
DateTimeFormatter utc =
    DateTimeFormatter.ISO_INSTANT.withZone(
        ZoneOffset.UTC
    );
~~~

Đoạn này minh họa việc tạo biến thể cấu hình, không đòi hỏi luôn phải gọi `withZone` cho `ISO_INSTANT` (vốn đã biểu diễn UTC). Với formatter tùy chỉnh, bạn có thể dùng `withZone` để cung cấp zone khi format `Instant` ra các trường lịch địa phương.

**Phân biệt `DateTimeFormatterBuilder`:** builder là đối tượng cấu hình **mutable**, được dùng để tạo formatter:

~~~java
DateTimeFormatter format =
    new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .toFormatter();
~~~

Không chia sẻ cùng builder cho nhiều thread cùng sửa cấu hình rồi suy nó an toàn chỉ vì thuộc package `java.time.format`. Sau khi `toFormatter` trả `DateTimeFormatter`, giá trị formatter được tạo mới có thể chia sẻ.

### Những điều thread-safe không có nghĩa

- Nếu nhiều thread cùng sửa một `ArrayList` lưu kết quả parse, formatter không làm `ArrayList` thread-safe.
- Nếu ứng dụng lấy `ZoneId.systemDefault()` từ môi trường có cấu hình thay đổi, sự khác biệt output có thể đến từ **cấu hình nguồn**, không phải formatter bị mutate.
- Nếu code parse từ một `StringBuilder` mutable đang bị thread khác sửa không đồng bộ, formatter không bảo vệ dữ liệu đầu vào.
- Nếu một service cần snapshot giữa nhiều trường thời gian và database, formatter không tạo transaction cho các tác vụ đó.

## 12. Chương trình Java đầy đủ: hằng ISO, parser, resolver và formatter chia sẻ

Lưu chương trình dưới đây thành **`IsoDateTimeFormatterDemo.java`**. Mã chỉ sử dụng API có từ Java 8, biên dịch/chạy bằng JDK 17+ không cần thư viện ngoài.

~~~java
import java.time.*;
import java.time.format.*;
import java.time.temporal.TemporalAccessor;
import java.util.*;
import java.util.concurrent.*;

public class IsoDateTimeFormatterDemo {

    private static final DateTimeFormatter SHARED =
            DateTimeFormatter.ISO_OFFSET_DATE_TIME;

    private static final DateTimeFormatter STRICT_DATE =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) throws Exception {
        LocalDate day = LocalDate.of(2024, 2, 29);
        LocalTime clock = LocalTime.of(9, 30, 45);
        LocalDateTime local = LocalDateTime.of(day, clock);
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        OffsetDateTime offset = OffsetDateTime.of(
                local, ZoneOffset.ofHours(7));
        ZonedDateTime zoned = local.atZone(zone);
        Instant moment = offset.toInstant();

        System.out.println("date="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(day));
        System.out.println("time="
                + DateTimeFormatter.ISO_LOCAL_TIME.format(clock));
        System.out.println("localDateTime="
                + DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local));
        System.out.println("offsetDateTime="
                + SHARED.format(offset));
        System.out.println("zonedDateTime="
                + DateTimeFormatter.ISO_ZONED_DATE_TIME.format(zoned));
        System.out.println("instant="
                + DateTimeFormatter.ISO_INSTANT.format(moment));

        System.out.println("basic="
                + DateTimeFormatter.BASIC_ISO_DATE.format(day));
        System.out.println("ordinal="
                + DateTimeFormatter.ISO_ORDINAL_DATE.format(day));
        System.out.println("week="
                + DateTimeFormatter.ISO_WEEK_DATE.format(day));

        LocalDate parsedBasic = LocalDate.parse(
                "20240229", DateTimeFormatter.BASIC_ISO_DATE);
        LocalDate parsedOrdinal = LocalDate.parse(
                "2024-060", DateTimeFormatter.ISO_ORDINAL_DATE);
        LocalDate parsedWeek = LocalDate.parse(
                "2024-W09-4", DateTimeFormatter.ISO_WEEK_DATE);

        System.out.println("parsedBasic=" + parsedBasic);
        System.out.println("parsedOrdinal=" + parsedOrdinal);
        System.out.println("parsedWeek=" + parsedWeek);

        OffsetDateTime parsedOffset = OffsetDateTime.parse(
                "2024-02-29T09:30:45+07:00",
                DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        ZonedDateTime parsedZoned = ZonedDateTime.parse(
                "2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]",
                DateTimeFormatter.ISO_ZONED_DATE_TIME);
        Instant parsedInstant = Instant.from(
                DateTimeFormatter.ISO_INSTANT.parse(
                    "2024-02-29T02:30:45Z"));

        System.out.println("offsetToInstant="
                + parsedOffset.toInstant());
        System.out.println("parsedZoned=" + parsedZoned);
        System.out.println("parsedInstant=" + parsedInstant);
        System.out.println("sameInstant="
                + parsedZoned.toInstant().equals(parsedInstant));

        TemporalAccessor bestLocal =
                DateTimeFormatter.ISO_DATE_TIME.parseBest(
                    "2024-02-29T09:30:45",
                    ZonedDateTime::from,
                    OffsetDateTime::from,
                    LocalDateTime::from);
        System.out.println("parseBestType="
                + bestLocal.getClass().getSimpleName());

        DateTimeFormatter inHcm =
                DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd HH:mm XXX", Locale.ROOT)
                    .withZone(zone);
        System.out.println("formattedZone="
                + inHcm.format(moment));

        DateTimeFormatter english =
                DateTimeFormatter.ofPattern(
                    "dd MMM uuuu", Locale.ENGLISH);
        System.out.println("english="
                + english.format(day));

        DateTimeFormatter smart =
                DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd", Locale.ROOT);
        System.out.println("smartAdjusted="
                + LocalDate.parse("2024-02-30", smart));
        System.out.println("strictValid="
                + LocalDate.parse("2024-02-29", STRICT_DATE));

        try {
            LocalDate.parse("2024-02-30", STRICT_DATE);
        } catch (DateTimeParseException ex) {
            System.out.println("strictRejected=true");
        }

        try {
            SHARED.format(local);
        } catch (DateTimeException ex) {
            System.out.println("missingOffset=true");
        }

        Instant nanos = Instant.parse(
                "2024-02-29T02:30:45.123456789Z");
        System.out.println("nanoseconds="
                + DateTimeFormatter.ISO_INSTANT.format(nanos));

        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < 4; worker++) {
                futures.add(pool.submit(() -> {
                    int verified = 0;
                    for (int i = 0; i < 250; i++) {
                        String encoded = SHARED.format(offset);
                        OffsetDateTime restored =
                                OffsetDateTime.parse(encoded, SHARED);
                        if (!offset.equals(restored)) {
                            throw new AssertionError("round-trip failed");
                        }
                        verified++;
                    }
                    return verified;
                }));
            }

            int totalVerified = 0;
            for (Future<Integer> f : futures) {
                totalVerified += f.get();
            }
            System.out.println("sharedFormatterRoundTrips="
                    + totalVerified);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 IsoDateTimeFormatterDemo.java
java IsoDateTimeFormatterDemo
~~~

**Đầu ra dự kiến với rules vùng `Asia/Ho_Chi_Minh` áp dụng cho ngày năm 2024:**

~~~text
date=2024-02-29
time=09:30:45
localDateTime=2024-02-29T09:30:45
offsetDateTime=2024-02-29T09:30:45+07:00
zonedDateTime=2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]
instant=2024-02-29T02:30:45Z
basic=20240229
ordinal=2024-060
week=2024-W09-4
parsedBasic=2024-02-29
parsedOrdinal=2024-02-29
parsedWeek=2024-02-29
offsetToInstant=2024-02-29T02:30:45Z
parsedZoned=2024-02-29T09:30:45+07:00[Asia/Ho_Chi_Minh]
parsedInstant=2024-02-29T02:30:45Z
sameInstant=true
parseBestType=LocalDateTime
formattedZone=2024-02-29 09:30 +07:00
english=29 Feb 2024
smartAdjusted=2024-02-29
strictValid=2024-02-29
strictRejected=true
missingOffset=true
nanoseconds=2024-02-29T02:30:45.123456789Z
sharedFormatterRoundTrips=1000
~~~

### Giải thích đầu ra quan trọng

1. **`date/time/localDateTime`:** các hằng local có trường ngày/giờ tương ứng mà không thêm offset.
2. **`offsetDateTime` và `zonedDateTime`:** cả hai có `+07:00`, nhưng bản zoned còn giữ `[Asia/Ho_Chi_Minh]`.
3. **`instant` và `offsetToInstant`:** cùng `02:30:45Z` sau khi trừ offset bảy tiếng.
4. **`basic/ordinal/week`:** cùng ngày nhuận 29/2 được biểu diễn bằng ba schema khác nhau; các phép parse đưa cả ba về cùng `LocalDate`.
5. **`parseBestType=LocalDateTime`:** input không chứa offset hoặc zone nên các truy vấn yêu cầu chúng không đủ trường; truy vấn `LocalDateTime::from` thành công.
6. **`formattedZone`:** `withZone` cho phép format một `Instant` bằng các trường lịch địa phương trong HCM, thay vì giả định timezone mặc định của JVM.
7. **`smartAdjusted`:** custom `ofPattern` mặc định SMART có thể điều chỉnh 30/2 thành ngày cuối tháng; `strictRejected` chứng minh cấu hình STRICT từ chối.
8. **`missingOffset`:** `LocalDateTime` không có trường offset để format bằng hằng ISO_OFFSET_DATE_TIME. Bắt ngoại lệ ở ranh giới, không tự tưởng formatter sẽ chọn `+00:00`.
9. **`nanoseconds`:** formatter ISO_INSTANT giữ phần lẻ tới 9 chữ số trong ví dụ.
10. **`sharedFormatterRoundTrips=1000`:** bốn worker, mỗi worker 250 lượt format/parse bằng cùng một `SHARED` immutable. Không có state mutable chung để formatter phải khóa. Kết quả chỉ được in sau `Future.get()`, nên không lệ thuộc thứ tự task hoàn tất.

Chương trình không dùng `LocalDateTime.now()`, locale mặc định hoặc timezone mặc định. Ngoại trừ dữ liệu region zone cần rules tương ứng, đầu ra của nó được xác định rõ theo input cố định.

## 13. Lỗi phổ biến và cách sửa

### Lỗi 1 — Dùng formatter của một kiểu với temporal thiếu trường

~~~java
LocalDateTime local =
    LocalDateTime.of(2024, 2, 29, 9, 30);

// Phản ví dụ: yêu cầu offset nhưng local không có.
DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(local);
~~~

Khi cần timestamp có offset, hãy có thông tin offset/zone **thật**, tạo `OffsetDateTime`/`ZonedDateTime` rồi format. Không tự gắn UTC cho một local datetime không xác định vùng.

### Lỗi 2 — Nhầm ISO_ZONED_DATE_TIME với ISO-8601 thuần

Chuỗi có `[Asia/Ho_Chi_Minh]` là tiện ích ISO-like của Java, không phải mọi parser ISO bên ngoài đều đọc được. Trong REST/JSON, thường có thể trao đổi `ISO_OFFSET_DATE_TIME` cho timestamp và một field `zoneId` riêng khi thật sự cần region.

### Lỗi 3 — Lấy `LocalDateTime` làm timestamp duy nhất

`2024-02-29T09:30:45` thiếu offset, không có một instant duy nhất. Nếu dữ liệu đến từ nhiều vùng, so thứ tự event phải dựa vào `Instant` hoặc thông tin đủ để quy đổi.

### Lỗi 4 — Dùng pattern `YYYY-MM-dd` khi muốn năm lịch

`Y` là **week-based-year**, có thể làm ngày cuối tháng 12 được ghi thuộc “năm mới” theo tuần. Dùng `uuuu-MM-dd` cho năm lịch ISO; test các ngày gần 31/12 và 01/01.

### Lỗi 5 — Dùng `yyyy` với STRICT mà thiếu era

`yyyy` là `YEAR_OF_ERA`. Trong strict parsing, thiếu era có thể khiến không resolve thành `LocalDate`. Chọn `uuuu` hoặc thiết kế pattern có era khi cần.

### Lỗi 6 — Tin mọi custom pattern mặc định strict

`ofPattern` mặc định SMART. Nếu hệ thống phải từ chối 30/2, cấu hình `withResolverStyle(ResolverStyle.STRICT)` và unit test ngày không hợp lệ.

### Lỗi 7 — Giả định ISO_LOCAL_TIME và ISO_INSTANT luôn có fixed-length

Phần giây/fraction được trình bày tùy giá trị; ISO_INSTANT có thể không có fraction hoặc có 3/6/9 chữ số. Nếu lưu trong cột CHAR cố định, phải cân nhắc độ dài biến thiên hoặc schema precision xác định.

### Lỗi 8 — Nhầm `MM` và `mm`, `HH` và `hh`

`MM` = tháng; `mm` = phút. `HH` = giờ 24h; `hh` = giờ 12h cần AM/PM để rõ nghĩa. Sai một chữ hoa/thường có thể khiến schema sai hoặc parse thất bại.

### Lỗi 9 — Dùng hằng ISO để format theo văn hóa người dùng

Hằng ISO thích hợp cho schema trao đổi kỹ thuật; giao diện người dùng có thể cần `Locale` và `FormatStyle` rõ ràng. Đừng dùng `ISO_LOCAL_DATE` rồi cho rằng nó sẽ thành `dd/MM/yyyy` chỉ vì locale vi-VN.

### Lỗi 10 — Dùng formatter không có ZoneId để format Instant thành giờ địa phương

`Instant` có mốc thời gian, chưa có trường ngày-giờ theo một zone địa phương. Dùng `instant.atZone(zone)` hoặc formatter tùy chỉnh `withZone(zone)`.

### Lỗi 11 — Coi parsing thành công là dữ liệu nghiệp vụ đã hợp lệ

Một timestamp được parse đúng cú pháp vẫn có thể ngoài khoảng cho phép, từ vùng sai, hoặc thuộc DST overlap mơ hồ khi người dùng nhập local time. Cần validate **nghiệp vụ** riêng sau bước parse; formatter không tự biết quy định hạn giao hàng, giờ mở cửa hay chính sách DST.

### Lỗi 12 — Chia sẻ mutable `DateTimeFormatterBuilder` giữa worker

`DateTimeFormatter` immutable/thread-safe; builder dùng để lắp cấu hình lại mutable. Chỉ chia sẻ formatter **sau khi hoàn tất** `toFormatter()`, không chia sẻ builder đang sửa.

### Lỗi 13 — Trông chờ mọi hằng ISO chứa timezone/offset

`ISO_LOCAL_DATE_TIME` chỉ local. `ISO_DATE_TIME` có offset/zone **tùy chọn**. Nếu bên nhận cần một instant, đừng cho phép thiếu offset rồi tự suy đoán vùng; schema cần ghi “offset bắt buộc” hoặc “UTC Instant”.

### Lỗi 14 — Dùng `parseBest` không kiểm tra kiểu trả về

`parseBest` trả `TemporalAccessor` được chọn theo thứ tự các query. Nếu một hệ thống nhận nhiều biến thể, cần phân nhánh hoặc chuyển đổi có kiểm tra để tránh dùng local time như instant. Trong API có thể kiểm soát input, một formatter và kiểu parse cụ thể thường dễ bảo trì hơn.

### Lỗi 15 — Cho rằng formatter tự nhận thay đổi timezone rules

`ZoneId` region có quy tắc tzdb có thể được cập nhật qua phiên bản JDK/runtime. Việc formatter immutable không có nghĩa mọi bản JDK sẽ hiển thị một local time giống nhau cho các vùng/ngày bị thay luật. Với test timestamp quan trọng, dùng Instant và ZoneId cố định, kiểm chứng version/rules thực tế.

## 14. So sánh nhanh: chọn formatter cho yêu cầu nào?

| Yêu cầu | Kiểu dữ liệu | Formatter thường phù hợp |
| --- | --- | --- |
| Lưu ngày sinh không có giờ | `LocalDate` | `ISO_LOCAL_DATE` |
| Lưu giờ mở cửa trong ngày | `LocalTime` | `ISO_LOCAL_TIME` |
| Đọc một lịch hẹn 09:30 theo giờ địa phương | `LocalDateTime` + ZoneId riêng khi cần | `ISO_LOCAL_DATE_TIME` |
| Giao tiếp timestamp có offset | `OffsetDateTime` | `ISO_OFFSET_DATE_TIME` |
| Giữ cả region zone theo định dạng dành cho Java | `ZonedDateTime` | `ISO_ZONED_DATE_TIME`, kiểm tra khả năng tương thích bên nhận |
| Lưu/log timestamp UTC duy nhất | `Instant` | `ISO_INSTANT` |
| Đọc ngày compact từ hệ thống quy định `yyyyMMdd` | `LocalDate` | `BASIC_ISO_DATE` |
| Báo cáo ngày thứ N trong năm | `LocalDate` | `ISO_ORDINAL_DATE` |
| Lịch báo cáo dựa vào tuần ISO | `LocalDate` | `ISO_WEEK_DATE` |
| Định dạng tùy chỉnh cho giao diện | `LocalDate`/`LocalDateTime` theo yêu cầu | `ofPattern(..., Locale)` hoặc `ofLocalizedDate` |
| Protocol yêu cầu RFC 1123 | Kiểu có đủ ngày/giờ/offset hoặc zone | `RFC_1123_DATE_TIME` |
| Input có/không có offset tùy nguồn | `TemporalAccessor` rồi query cụ thể | `ISO_DATE_TIME.parseBest`; ưu tiên schema rõ nếu có thể |

## 15. Checklist khi làm việc với DateTimeFormatter

1. **Mục đích là format hay parse?** Xác định chuỗi đầu ra và kiểu temporal đích.
2. **Có đúng hằng ISO không?** Phân biệt `ISO_LOCAL_DATE_TIME`, `ISO_OFFSET_DATE_TIME`, `ISO_ZONED_DATE_TIME`, `ISO_INSTANT`.
3. **Cần instant thật không?** Nếu có, input phải mang offset/zone hoặc có quy tắc chuyển đổi được cung cấp rõ ràng.
4. **Bên nhận có hiểu `[ZoneId]` không?** Đây là phần mở rộng ISO-like của Java.
5. **Đã chú ý optional parts?** `ISO_DATE`/`ISO_TIME`/`ISO_DATE_TIME` có thể thiếu offset; `parseBest` cần xử lý kiểu.
6. **Có yêu cầu ngày hợp lệ nghiêm ngặt không?** Dùng ISO STRICT hoặc custom `withResolverStyle(STRICT)`.
7. **Pattern có nhầm `u/y/Y` hoặc `M/m` không?** Test cả ranh giới năm và năm nhuận.
8. **Locale là gì?** ISO machine schema khác văn bản thân thiện người dùng.
9. **Múi giờ rõ ràng chưa?** Khi format `Instant` thành giờ địa phương, dùng `withZone` hoặc `atZone`.
10. **Đã xử lý precision chưa?** Phần giây có thể thay đổi độ dài; database/API phải bảo toàn mức chính xác cần thiết.
11. **Dùng formatter ở nhiều thread?** `DateTimeFormatter` dùng chung được; không chia sẻ builder mutable đang lắp.
12. **Đã kiểm thử dữ liệu sai?** 30/2, timezone thiếu, offset sai, giờ 25:00, DST gap/overlap nếu dùng region.
13. **Có phụ thuộc tzdb hoặc locale data của runtime không?** Với kết quả nhạy cảm, xác nhận môi trường đang chạy.
14. **Có round-trip test không?** Kiểm tra `parse(format(x))` ra đúng giá trị/các trường cần bảo toàn; đừng mặc định formatter local sẽ giữ instant chưa từng có.
15. **Cùng instant nhưng khác local?** Nếu cần so thời điểm, so `Instant`/`isEqual`, không so chuỗi hiển thị.

**Kết luận:** `DateTimeFormatter` và các hằng ISO là API hiện hành, bất biến, an toàn luồng và hữu ích để tạo schema ngày giờ rõ ràng. Chọn `ISO_LOCAL_*` cho giá trị **không có offset**, `ISO_OFFSET_*` cho giá trị **có offset**, `ISO_ZONED_DATE_TIME` khi cần mang thêm **ZoneId trong định dạng ISO-like**, và `ISO_INSTANT` cho **một thời điểm UTC**. Khi cần định dạng tùy chỉnh, hãy hiểu đúng ký hiệu pattern, locale và `ResolverStyle`; formatter không thay thế quyết định nghiệp vụ về múi giờ hoặc DST.

## Tài liệu chính thức

- [Oracle Java SE 26 — DateTimeFormatter: tất cả hằng ISO, pattern, parsing và thread-safety](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 26 — DateTimeFormatterBuilder: cấu hình formatter và optional sections](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
- [Oracle Java SE 26 — ResolverStyle: STRICT, SMART và LENIENT](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle Java SE 26 — LocalDate và LocalDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html)
- [Oracle Java SE 26 — OffsetDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html)
- [Oracle Java SE 26 — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [Oracle Java SE 26 — Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
