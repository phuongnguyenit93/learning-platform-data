# Tạo, đọc, cộng trừ và phân tích OffsetDateTime trong Java

## 1. OffsetDateTime giải quyết vấn đề gì?

Một chuỗi ngày giờ như **2026-10-24T17:15:30** cho biết các con số trên đồng hồ, nhưng chưa xác định được lúc nào trên dòng thời gian. Khi thêm offset **+07:00**, ta có **2026-10-24T17:15:30+07:00**, tương ứng chính xác với **2026-10-24T10:15:30Z** (UTC). Java biểu diễn loại giá trị này bằng **java.time.OffsetDateTime**.

**OffsetDateTime = LocalDateTime + ZoneOffset.**

- **LocalDateTime**: ngày và giờ địa phương (năm, tháng, ngày, giờ, phút, giây, nano).
- **ZoneOffset**: độ lệch của giờ đồng hồ so với UTC, ví dụ +07:00, -05:00 hoặc Z (= +00:00).
- Khi kết hợp hai thông tin này, Java có thể xác định một **Instant** duy nhất.

Bài học tập trung vào các thao tác: **tạo**, **đọc thuộc tính**, **parse/format**, **cộng trừ**, **so sánh**, **phân tích và chuyển đổi** OffsetDateTime; kèm các quy tắc quan trọng về sai khác giữa offset cố định và múi giờ khu vực.

Sau bài học bạn có thể chọn đúng constructor/API, chuyển cùng một Instant sang offset khác mà không làm sai timestamp, tính toán các mốc thời gian, xử lý lỗi nhập liệu, và hiểu khi nào nên chuyển sang **ZonedDateTime**.

## 2. Phân biệt OffsetDateTime với các kiểu ngày giờ khác

| Kiểu | Chứa gì? | Biết chính xác một thời điểm? | Ví dụ sử dụng |
| --- | --- | --- | --- |
| **LocalDate** | Ngày, không có giờ | Chưa | Ngày sinh, ngày hóa đơn |
| **LocalTime** | Giờ, không có ngày | Chưa | Giờ mở cửa hằng ngày |
| **LocalDateTime** | Ngày và giờ trên đồng hồ | Chưa | 09:00 ngày 25/10 tại địa điểm chưa xác định |
| **ZoneOffset** | Chỉ một độ lệch UTC | Chưa | +07:00 |
| **OffsetDateTime** | Ngày giờ + offset | **Có** | Timestamp API: 2026-10-24T17:15:30+07:00 |
| **Instant** | Mốc tuyệt đối trên timeline | **Có** | Log/audit, timestamp trung lập với vùng |
| **ZonedDateTime** | Ngày giờ + ZoneId + offset được áp dụng | **Có** | Lịch hẹn tại America/New_York, cần quy tắc DST |

OffsetDateTime **không lưu ZoneId khu vực** như Asia/Ho_Chi_Minh hay America/New_York; nó chỉ biết một offset đã chọn. Hai nơi có thể dùng cùng offset nhưng có luật đổi giờ/lịch sử khác nhau. Với cuộc hẹn lặp trong tương lai theo giờ địa phương ở một thành phố, **ZoneId** và quy tắc vùng quan trọng hơn chỉ một offset cố định.

### Phép đổi từ đồng hồ địa phương sang UTC

Tại một thời điểm với offset đã biết:

~~~text
UTC = local date-time − offset

2026-10-24 17:15:30 +07:00
                 ↓ trừ 7 giờ
2026-10-24 10:15:30Z

2026-10-24 08:30:00 -04:00
                 ↓ cộng 4 giờ
2026-10-24 12:30:00Z
~~~

Dấu **+** nghĩa là đồng hồ địa phương nhanh hơn UTC; dấu **-** nghĩa là chậm hơn. Khi đổi offset có thể đổi ngày, tháng hoặc năm; không chỉ thay con số giờ.

## 3. Tạo OffsetDateTime

### 3.1. Tạo từ các trường ngày giờ và ZoneOffset

~~~java
ZoneOffset vietnamOffset = ZoneOffset.ofHours(7);

OffsetDateTime meeting = OffsetDateTime.of(
        2026, 10, 24, 17, 15, 30, 0, vietnamOffset);

// 2026-10-24T17:15:30+07:00
~~~

Đây là đoạn trích: import **java.time.OffsetDateTime**, **java.time.ZoneOffset** và đặt trong phương thức. Các tham số số học lần lượt là **năm, tháng, ngày, giờ, phút, giây, nano**. Ví dụ **ZoneOffset.ofHoursMinutes(5, 30)** dùng cho offset +05:30.

**ZoneOffset.of("+07:00")** và **ZoneOffset.ofHours(7)** cùng tạo giá trị +07:00. **ZoneOffset.UTC** là hằng số offset 0; khi in theo ISO, Java thường ghi offset 0 thành **Z**.

### 3.2. Tạo từ LocalDate, LocalTime hoặc LocalDateTime

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(17, 15, 30);
ZoneOffset offset = ZoneOffset.of("+07:00");

OffsetDateTime a = OffsetDateTime.of(date, time, offset);
OffsetDateTime b = OffsetDateTime.of(
        LocalDateTime.of(date, time), offset);

boolean sameValue = a.equals(b); // true
~~~

Đây là đoạn trích; cần import từ java.time. Tùy dữ liệu đầu vào đã có, chọn overload **of(LocalDate, LocalTime, ZoneOffset)** hoặc **of(LocalDateTime, ZoneOffset)**. Đây là cách gắn **offset** với một ngày-giờ chưa mang thông tin offset. Nó **không kiểm tra** xem offset đó có phải offset đúng của một thành phố vào ngày ấy hay không; muốn xác thực theo vùng phải dùng **ZoneId/ZoneRules**.

Một cách khác là gọi **localDateTime.atOffset(offset)**, trả OffsetDateTime tương ứng.

### 3.3. Tạo từ một Instant: thay cách biểu diễn mà vẫn giữ thời điểm

~~~java
Instant instant = Instant.parse("2026-10-24T10:15:30Z");
ZoneOffset offset = ZoneOffset.ofHours(7);

OffsetDateTime a = instant.atOffset(offset);
OffsetDateTime b = OffsetDateTime.ofInstant(instant, offset);
// a và b đều là 2026-10-24T17:15:30+07:00
~~~

Đây là đoạn trích cần import java.time.*. Vì đầu vào đã là **Instant**, offset chỉ quyết định cách hiển thị ngày/giờ; mốc tuyệt đối không thay đổi. **ofInstant(instant, zone)** còn nhận **ZoneId khu vực** và tra offset của vùng tại Instant đó, nhưng kết quả OffsetDateTime **chỉ lưu offset đã tính**, không giữ lại ZoneId.

### 3.4. Lấy thời điểm hiện tại

~~~java
OffsetDateTime current =
        OffsetDateTime.now(ZoneOffset.UTC);
~~~

Kết quả phụ thuộc đồng hồ khi chạy. Để test lặp lại được, dùng **Clock.fixed(...)**:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-10-24T10:15:30Z"),
        ZoneOffset.ofHours(7));
OffsetDateTime stable = OffsetDateTime.now(fixed);
// 2026-10-24T17:15:30+07:00
~~~

Đây là đoạn trích cần import java.time.*. **Clock** cho phép inject thời gian thay vì phụ thuộc thời điểm test đang chạy. **OffsetDateTime.now()** không tham số sử dụng đồng hồ và múi giờ mặc định của hệ thống; trong môi trường máy chủ/container, mặc định có thể khác máy phát triển. Trong logic nghiệp vụ nên truyền Clock/ZoneId/ZoneOffset rõ ràng.

## 4. Đọc các thành phần ngày giờ và offset

OffsetDateTime có các getter giống LocalDateTime cho trường ngày/giờ, cùng **getOffset()**:

| Phương thức | Với 2026-10-24T17:15:30+07:00 | Ý nghĩa |
| --- | --- | --- |
| **getYear()** | 2026 | Năm ISO |
| **getMonth()** | OCTOBER | Enum Month |
| **getMonthValue()** | 10 | Tháng dạng số |
| **getDayOfMonth()** | 24 | Ngày trong tháng |
| **getDayOfYear()** | 297 | Số thứ tự ngày trong năm 2026 |
| **getDayOfWeek()** | SATURDAY | Thứ trong tuần |
| **getHour()** | 17 | Giờ 0–23 |
| **getMinute()** | 15 | Phút 0–59 |
| **getSecond()** | 30 | Giây |
| **getNano()** | 0 | Phần nano giây |
| **getOffset()** | +07:00 | Độ lệch UTC |
| **toLocalDate()** | 2026-10-24 | Bỏ giờ/offset |
| **toLocalTime()** | 17:15:30 | Bỏ ngày/offset |
| **toLocalDateTime()** | 2026-10-24T17:15:30 | Bỏ offset |
| **toInstant()** | 2026-10-24T10:15:30Z | Chuyển sang mốc tuyệt đối |

**toLocalDateTime()** chỉ lấy phần ngày/giờ đã hiển thị, không còn offset. Nếu truyền giá trị này qua API mà không gửi offset/ZoneId, bên nhận **không thể tự suy ra Instant gốc**. **toInstant()** nên dùng khi muốn so sánh hoặc lưu sự kiện tuyệt đối.

Cũng có thể đọc trường theo Temporal API:

~~~java
int hour = meeting.get(ChronoField.HOUR_OF_DAY);
long epochSecond = meeting.toEpochSecond();
~~~

Đây là đoạn trích: meeting đã được khai báo; cần import **java.time.temporal.ChronoField**. **toEpochSecond()** trả giây Unix từ epoch, khác millisecond. Khi cần millisecond, **meeting.toInstant().toEpochMilli()** có thể làm mất phần nano giây dưới millisecond.

## 5. Parse chuỗi ngày giờ có offset

### 5.1. Định dạng ISO mặc định

~~~java
OffsetDateTime a = OffsetDateTime.parse(
        "2026-10-24T17:15:30+07:00");

OffsetDateTime b = OffsetDateTime.parse(
        "2026-10-24T10:15:30Z");

boolean sameMoment = a.isEqual(b); // true
~~~

Đây là đoạn trích cần import OffsetDateTime. **OffsetDateTime.parse(CharSequence)** dùng ISO_OFFSET_DATE_TIME, có offset bắt buộc. Chuỗi **2026-10-24T17:15:30** không có offset nên không parse được thành OffsetDateTime bằng parser mặc định: hãy dùng **LocalDateTime** cho chuỗi thuần, hoặc yêu cầu nguồn cung cấp offset.

Các chuỗi:

~~~text
2026-10-24T17:15:30+07:00     hợp lệ: offset +07:00
2026-10-24T10:15:30Z          hợp lệ: offset 0
2026-10-24T17:15:30           thiếu offset
2026-10-24T17:15:30[Asia/Ho_Chi_Minh]
                              không phải dạng OffsetDateTime ISO mặc định có offset
~~~

**Z** là ký hiệu UTC+00:00; một offset có thể có phút và giây theo những giới hạn Java cho phép, không nhất thiết chỉ tròn giờ.

### 5.2. Parse theo mẫu và Locale

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

OffsetDateTime appointment = OffsetDateTime.parse(
        "2026-10-24 17:15 +07:00", formatter);
~~~

Đây là đoạn trích, cần import **java.time.OffsetDateTime**, **java.time.format.DateTimeFormatter** và **java.util.Locale**.

Phân biệt ký hiệu thường gặp:

- **uuuu**: năm proleptic ISO, thường dễ dùng với parse nghiêm ngặt.
- **MM**: tháng; **mm**: phút.
- **dd**: ngày trong tháng; **HH**: giờ 0–23.
- **ss**: giây; **SSS**: phần giây theo số chữ số.
- **XXX**: offset kiểu **+07:00**, **-04:00** hoặc **Z** cho zero offset.
- **VV**: ZoneId vùng (phục vụ xử lý thời gian vùng, không thay thế offset bắt buộc cho bài này).

Các formatter có tên tháng/ngày trong tuần phụ thuộc **Locale**. Nếu nhập từ người dùng, định dạng phải rõ ràng, tốt nhất dùng ISO 8601 có offset để tránh “01/02” là ngày 1 tháng 2 hay 2 tháng 1.

### 5.3. Xử lý input lỗi

~~~java
try {
    OffsetDateTime value = OffsetDateTime.parse(userText);
    // Chỉ xử lý sau khi parse thành công.
} catch (DateTimeParseException ex) {
    // Trả lỗi: thiếu offset, sai định dạng hoặc ngày không hợp lệ.
}
~~~

Đây là đoạn trích, cần biến **userText**, import OffsetDateTime và **java.time.format.DateTimeParseException**. Không “đoán” offset từ timezone máy chủ khi đầu vào thiếu thông tin. Nếu hợp đồng API cho phép thiếu offset, hãy công bố rõ cách gắn **ZoneId** và quy tắc giải quyết gap/overlap.

## 6. Format OffsetDateTime để xuất dữ liệu

**toString()** trả biểu diễn ISO có offset, nhưng phần giây có thể bị lược nếu bằng 0. Muốn định dạng cố định:

~~~java
OffsetDateTime value = OffsetDateTime.parse(
        "2026-10-24T17:15:30+07:00");
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm:ss XXX", Locale.ROOT);

String text = value.format(formatter);
// 2026-10-24 17:15:30 +07:00
~~~

Đây là đoạn trích, import java.time.*, java.time.format.* và java.util.Locale. Dùng **DateTimeFormatter.ISO_OFFSET_DATE_TIME** cho hợp đồng ISO rõ nghĩa, tránh format mất offset. Formatter là immutable, dùng lại an toàn.

Trong hệ thống nhiều dịch vụ, ưu tiên truyền timestamp có offset hoặc UTC với **Z**; không lưu chuỗi format tùy ý rồi mong bên nhận suy ra ZoneId. Với API chỉ cần thời điểm thực, truyền **Instant** là lựa chọn đơn giản hơn.

## 7. Cộng, trừ ngày và giờ

OffsetDateTime có API bất biến:

- **plusDays(n)**, **minusDays(n)**: cộng/trừ số ngày theo lịch.
- **plusHours(n)**, **minusHours(n)**: cộng/trừ số giờ.
- **plusMinutes(n)**, **plusSeconds(n)**, **plusNanos(n)**: cộng theo đơn vị nhỏ.
- **plusWeeks(n)**, **plusMonths(n)**, **plusYears(n)**: thao tác theo lịch.
- **plus(amount, TemporalUnit)** hoặc **minus(...)**: thao tác bằng ChronoUnit khi phù hợp.

~~~java
OffsetDateTime base = OffsetDateTime.parse(
        "2026-10-24T17:15:30+07:00");

OffsetDateTime nextDay = base.plusDays(1);
// 2026-10-25T17:15:30+07:00

OffsetDateTime afterTenHours = base.plusHours(10);
// 2026-10-25T03:15:30+07:00

OffsetDateTime beforeThirtyMinutes = base.minusMinutes(30);
// 2026-10-24T16:45:30+07:00
~~~

Đây là đoạn trích, cần import OffsetDateTime. **base** không thay đổi. Đừng gọi **base.plusDays(1)** mà bỏ qua kết quả rồi nghĩ base đã được cộng ngày.

### 7.1. Cộng tháng và năm có thể điều chỉnh cuối tháng

Trong lịch ISO, không phải tháng nào cũng có ngày 31 và không phải năm nào có 29/02:

~~~java
OffsetDateTime jan31 = OffsetDateTime.parse(
        "2025-01-31T08:00+07:00");
OffsetDateTime nextMonth = jan31.plusMonths(1);
// 2025-02-28T08:00+07:00

OffsetDateTime leapDay = OffsetDateTime.parse(
        "2024-02-29T09:00+07:00");
OffsetDateTime nextYear = leapDay.plusYears(1);
// 2025-02-28T09:00+07:00
~~~

Java điều chỉnh về **ngày cuối tháng hợp lệ** nếu ngày gốc không tồn tại ở tháng/năm đích. Với lịch hợp đồng hoặc sinh nhật ngày 29/02, chính sách nghiệp vụ có thể khác: một số hệ thống muốn 01/03 thay vì 28/02. Hãy biểu diễn chính sách riêng.

### 7.2. Duration và Period

**Duration** mô tả khoảng giây/nano; **Period** mô tả năm/tháng/ngày lịch. OffsetDateTime giữ **offset cố định**, nên cộng một ngày địa phương theo ISO bằng **24 giờ tuyệt đối** trong điều kiện không vượt giới hạn kiểu, không có bước đổi DST nội bộ. Điều này khác **ZonedDateTime** tại ZoneId khu vực: qua DST, **plusDays(1)** có thể chênh 23 hoặc 25 giờ thực.

Đối với sự kiện, nên so sánh hai Instant:

~~~java
Duration elapsed = Duration.between(
        base.toInstant(), afterTenHours.toInstant());
// PT10H
~~~

Đây là đoạn trích cần import Duration; hai biến đã được định nghĩa trước. Để tính tuổi hoặc kỳ hạn theo lịch, dùng LocalDate/Period và quy tắc nghiệp vụ thay vì mặc định tính số ngày trôi qua chia 365.

## 8. Chuyển đổi offset: same instant khác same local

Đây là hai phương thức quan trọng nhất khi đổi offset:

**withOffsetSameInstant(newOffset)** giữ nguyên mốc tuyệt đối, nhưng **thay đổi ngày/giờ địa phương** sao cho phù hợp offset mới.

**withOffsetSameLocal(newOffset)** giữ nguyên các con số ngày/giờ địa phương, chỉ thay offset, do đó **thường đổi Instant**.

~~~java
OffsetDateTime vietnam = OffsetDateTime.parse(
        "2026-10-24T17:15:30+07:00");

OffsetDateTime sameInstant =
        vietnam.withOffsetSameInstant(ZoneOffset.UTC);
// 2026-10-24T10:15:30Z

OffsetDateTime sameLocal =
        vietnam.withOffsetSameLocal(ZoneOffset.UTC);
// 2026-10-24T17:15:30Z
~~~

Đây là đoạn trích cần import OffsetDateTime, ZoneOffset.

| Giá trị | LocalDateTime | Offset | Instant |
| --- | --- | --- | --- |
| Gốc | 2026-10-24 17:15:30 | +07:00 | 10:15:30Z |
| **withOffsetSameInstant(UTC)** | 2026-10-24 10:15:30 | Z | **10:15:30Z** |
| **withOffsetSameLocal(UTC)** | 2026-10-24 17:15:30 | Z | **17:15:30Z** |

Nếu muốn **hiển thị cùng một sự kiện ở UTC**, dùng **withOffsetSameInstant(ZoneOffset.UTC)** hoặc **toInstant()**. Nếu muốn **gắn lại offset** theo một nguồn dữ liệu trước đó bị gán sai, thao tác sameLocal có thể có ý nghĩa, nhưng đó là **thay đổi mốc được diễn giải** và phải có lý do rõ ràng.

Lưu ý: thay offset có thể chuyển sang **ngày hôm trước/hôm sau**. Ví dụ 2026-10-25T01:00+07:00 đổi giữ cùng Instant sang UTC sẽ là 2026-10-24T18:00Z.

## 9. So sánh: bằng cách biểu diễn hay bằng Instant?

Xét:

~~~text
A = 2026-10-24T17:15:30+07:00
B = 2026-10-24T10:15:30Z
~~~

A và B biểu diễn **cùng một Instant**, nhưng ngày giờ địa phương và offset khác nhau.

| Phương thức | Ý nghĩa | Với A và B |
| --- | --- | --- |
| **a.equals(b)** | Mọi thành phần ngày giờ và offset giống nhau | **false** |
| **a.isEqual(b)** | Cùng một Instant | **true** |
| **a.isBefore(b)** | Instant a sớm hơn b | **false** |
| **a.isAfter(b)** | Instant a muộn hơn b | **false** |
| **a.toInstant().equals(b.toInstant())** | Instant bằng nhau | **true** |
| **a.compareTo(b)** | So sánh theo Instant rồi tie-break bằng ngày giờ địa phương | Có thể khác 0 khi cùng Instant |

**OffsetDateTime.compareTo** có hai bước: so sánh Instant trước, nếu trùng thì so sánh LocalDateTime để giữ thứ tự phù hợp với equals. Vì thế **compareTo() == 0** không phải điều kiện phù hợp nếu chỉ quan tâm “cùng một mốc trên timeline” bất kể offset.

Nếu cần sort **theo Instant thuần**, dùng **OffsetDateTime.timeLineOrder()**:

~~~java
Comparator<OffsetDateTime> byInstant =
        OffsetDateTime.timeLineOrder();
boolean equalOnTimeline = byInstant.compare(a, b) == 0;
// true
~~~

Đây là đoạn trích, cần import OffsetDateTime và java.util.Comparator, khai báo **a**, **b** phù hợp. Khi làm deduplication của các mốc tuyệt đối, xem xét chuyển sang **Instant** hoặc dùng comparator theo timeline. Nếu lưu OffsetDateTime trong **TreeSet** dùng compareTo mặc định, hai biểu diễn cùng Instant nhưng khác offset **không bị coi là một phần tử trùng** theo ordering đó.

## 10. Phân tích một OffsetDateTime bằng Temporal API

Các phương thức hữu ích:

- **isSupported(field)**: kiểm tra TemporalField được hỗ trợ.
- **range(field)**: miền giá trị hợp lệ theo kiểu/giá trị.
- **get(field)** hoặc **getLong(field)**: đọc trường theo ChronoField.
- **with(field, value)**: trả OffsetDateTime mới có trường được thay đổi.
- **truncatedTo(ChronoUnit.MINUTES)**: cắt giây/nano để chuẩn hóa độ chính xác.
- **until(other, unit)**: tính độ chênh theo đơn vị chỉ định.
- **toEpochSecond()**: timestamp tính theo giây.
- **query(TemporalQueries...)**: truy vấn thông tin theo Temporal API khi dùng thuật toán generic.

Ví dụ:

~~~java
OffsetDateTime appointment = OffsetDateTime.parse(
        "2026-10-24T17:15:30.987654321+07:00");

int second = appointment.getSecond();      // 30
int nano = appointment.getNano();          // 987654321

OffsetDateTime minutePrecision =
        appointment.truncatedTo(ChronoUnit.MINUTES);
// 2026-10-24T17:15+07:00

OffsetDateTime changedHour = appointment.withHour(18);
// 2026-10-24T18:15:30.987654321+07:00
~~~

Đây là đoạn trích; import **java.time.OffsetDateTime** và **java.time.temporal.ChronoUnit**. **truncatedTo** chỉ bỏ các thành phần nhỏ hơn đơn vị được chọn; nó **không làm tròn**. Không nhầm các phép **with...** (đặt giá trị trường) với **plus...** (tăng tương đối).

**get(...)** chỉ trả int cho trường phù hợp; với giá trị vượt miền int như **INSTANT_SECONDS**, dùng **getLong(ChronoField.INSTANT_SECONDS)** hoặc **toEpochSecond()**.

### Between và thứ tự mốc

Để tính thời lượng thực giữa hai OffsetDateTime, dùng **Duration.between(start.toInstant(), end.toInstant())** hoặc **ChronoUnit.SECONDS.between(start, end)** theo yêu cầu. Khi so sánh thời gian thực, luôn giải thích rõ đơn vị giây, millisecond hay nano và cách làm tròn.

Không so sánh chuỗi hiển thị theo thứ tự từ điển nếu các timestamp có offset khác nhau; chuỗi 2026-10-24T09:00+09:00 có thể **sớm hơn** 2026-10-24T08:00+07:00 trên timeline dù giờ đồng hồ lớn hơn.

## 11. Java 17+ demo độc lập: tạo, đọc, cộng trừ, parse, đổi offset, so sánh

Tạo file **OffsetDateTimeDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OffsetDateTimeDemo {
    public static void main(String[] args) {
        ZoneOffset vietnam = ZoneOffset.ofHours(7);

        OffsetDateTime base = OffsetDateTime.of(
                2026, 10, 24, 17, 15, 30, 0, vietnam);
        OffsetDateTime parsed = OffsetDateTime.parse(
                "2026-10-24T17:15:30+07:00");

        System.out.println("Created: " + base);
        System.out.println("Parsed equals created: " +
                parsed.equals(base));
        System.out.println("Year: " + base.getYear());
        System.out.println("Hour: " + base.getHour());
        System.out.println("Offset: " + base.getOffset());
        System.out.println("Local: " + base.toLocalDateTime());
        System.out.println("Instant: " + base.toInstant());

        OffsetDateTime plusDay = base.plusDays(1);
        OffsetDateTime plusHours = base.plusHours(10);
        OffsetDateTime minusMinutes = base.minusMinutes(30);

        System.out.println("Plus day: " + plusDay);
        System.out.println("Plus 10 hours: " + plusHours);
        System.out.println("Minus 30 minutes: " + minusMinutes);
        System.out.println("Elapsed hours: " +
                Duration.between(
                        base.toInstant(),
                        plusHours.toInstant()).toHours());

        OffsetDateTime utcSameInstant =
                base.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime utcSameLocal =
                base.withOffsetSameLocal(ZoneOffset.UTC);

        System.out.println("Same instant UTC: " + utcSameInstant);
        System.out.println("Same local UTC: " + utcSameLocal);
        System.out.println("isEqual UTC: " +
                base.isEqual(utcSameInstant));
        System.out.println("equals UTC: " +
                base.equals(utcSameInstant));
        System.out.println("isBefore plus day: " +
                base.isBefore(plusDay));

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.ROOT);
        System.out.println("Formatted: " +
                base.format(formatter));

        Instant instant = Instant.parse(
                "2026-10-24T10:15:30Z");
        OffsetDateTime fromInstant =
                instant.atOffset(vietnam);
        System.out.println("From instant equals: " +
                fromInstant.equals(base));

        LocalDateTime local = base.toLocalDateTime();
        OffsetDateTime fromLocal =
                local.atOffset(vietnam);
        System.out.println("From local equals: " +
                fromLocal.equals(base));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OffsetDateTimeDemo.java
java OffsetDateTimeDemo
~~~

**Stdout mong đợi chính xác:**

~~~text
Created: 2026-10-24T17:15:30+07:00
Parsed equals created: true
Year: 2026
Hour: 17
Offset: +07:00
Local: 2026-10-24T17:15:30
Instant: 2026-10-24T10:15:30Z
Plus day: 2026-10-25T17:15:30+07:00
Plus 10 hours: 2026-10-25T03:15:30+07:00
Minus 30 minutes: 2026-10-24T16:45:30+07:00
Elapsed hours: 10
Same instant UTC: 2026-10-24T10:15:30Z
Same local UTC: 2026-10-24T17:15:30Z
isEqual UTC: true
equals UTC: false
isBefore plus day: true
Formatted: 2026-10-24 17:15 +07:00
From instant equals: true
From local equals: true
~~~

Từng nhóm kết quả:

1. **Parsed equals created** chứng minh parser ISO đọc đủ ngày/giờ và offset.
2. **Local** bỏ offset, **Instant** chuyển về timeline UTC.
3. Các phép cộng/trừ trả giá trị mới, giữ **+07:00**.
4. **withOffsetSameInstant(UTC)** giữ Instant; **withOffsetSameLocal(UTC)** giữ ngày giờ đồng hồ và đổi mốc tuyệt đối.
5. **isEqual** theo timeline khác **equals** theo toàn bộ giá trị.
6. Formatter **XXX** ghi offset +07:00.
7. Tạo từ Instant và LocalDateTime với thông tin offset thích hợp đều tái tạo được OffsetDateTime gốc.

Ví dụ sử dụng dữ liệu cố định nên đầu ra không phụ thuộc múi giờ hay đồng hồ của máy chạy.

## 12. Offset cố định không tự xử lý DST

Một điểm dễ nhầm: khi OffsetDateTime giữ offset **-05:00**, gọi **plusHours(2)** sẽ giữ -05:00, **không tự đổi sang -04:00** khi New York chuyển sang DST.

Xét mốc địa phương New York ngay trước ngày đổi giờ mùa xuân:

~~~java
OffsetDateTime before = OffsetDateTime.parse(
        "2026-03-08T01:30-05:00");
OffsetDateTime twoHoursLater = before.plusHours(2);
// 2026-03-08T03:30-05:00 (vẫn dùng offset cố định -05:00)

ZonedDateTime ny = twoHoursLater.atZoneSameInstant(
        ZoneId.of("America/New_York"));
// 2026-03-08T04:30-04:00[America/New_York]
~~~

Đây là đoạn trích; cần import **java.time.OffsetDateTime**, **java.time.ZonedDateTime**, **java.time.ZoneId**. Lúc **01:30-05:00** tương ứng **06:30Z**, sau hai giờ thực là **08:30Z**, khi đồng hồ New York đã đổi sang **04:30-04:00**. Nếu dùng OffsetDateTime thuần, kết quả vẫn **03:30-05:00**: có Instant đúng theo offset số học nhưng cách trình bày ấy **không còn là giờ địa phương hợp lệ của New York tại Instant đó**.

Nếu nghiệp vụ là “mỗi ngày lúc 09:00 tại New York”, đừng lặp lại **OffsetDateTime.plusDays(1)** với offset ban đầu cho cả năm. Cần **LocalTime/LocalDateTime + ZoneId** và quy tắc đổi giờ; dùng ZonedDateTime hoặc ZoneRules để tính mỗi lần phát sinh.

### Gắn OffsetDateTime với khu vực

- **offsetDateTime.atZoneSameInstant(zone)**: giữ mốc tuyệt đối; chuyển sang cách hiển thị theo ZoneId.
- **offsetDateTime.atZoneSimilarLocal(zone)**: cố giữ giờ địa phương nếu phù hợp, nếu không có thể điều chỉnh theo quy tắc gap/overlap; **có thể làm đổi Instant**.
- **offsetDateTime.toZonedDateTime()**: tạo ZonedDateTime với **ZoneId chính là offset hiện có**, không thể tự phục hồi tên thành phố từng tạo ra dữ liệu.

Nếu cần giải quyết giờ do người dùng nhập theo vùng, dùng **ZoneRules.getValidOffsets(localDateTime)** để xử lý **normal (1)**, **gap (0)**, **overlap (thường 2)**, hoặc dùng **ZonedDateTime.ofStrict(...)** với offset được xác thực. **OffsetDateTime.of(local, offset)** tự nó không kiểm tra độ lệch có hợp lệ ở một ZoneId khu vực hay không.

## 13. Sửa trường ngày/giờ và lưu ý miền hợp lệ

Để thay đổi trường cụ thể, dùng **withYear**, **withMonth**, **withDayOfMonth**, **withHour**, **withMinute**, **withSecond**, **withNano** hoặc **withOffsetSameInstant/withOffsetSameLocal** theo ngữ nghĩa.

~~~java
OffsetDateTime original = OffsetDateTime.parse(
        "2026-10-24T17:15:30+07:00");

OffsetDateTime newHour = original.withHour(9);
// 2026-10-24T09:15:30+07:00

OffsetDateTime newDay = original.withDayOfMonth(25);
// 2026-10-25T17:15:30+07:00
~~~

Đây là đoạn trích. **withHour(9)** thay trường đồng hồ, không có nghĩa “giảm chính xác 8 giờ” trong mọi mô hình múi giờ; với OffsetDateTime offset cố định, chênh tại đây đúng là -8 giờ thực, nhưng với lịch thành phố qua DST nên dùng kiểu ZoneId khi diễn tả ý định nghiệp vụ.

### Ngày tháng và offset không hợp lệ

- Tháng 13, ngày 31/02, giờ 25, phút 90 đều không hợp lệ; constructor hoặc parser ném **DateTimeException** (parser thường là DateTimeParseException).
- **ZoneOffset** trong Java hỗ trợ độ lệch trong khoảng từ **-18:00 đến +18:00**, với các quy tắc ràng buộc giờ/phút/giây tương ứng. Đừng tự chấp nhận mọi số nguyên lệch giờ.
- Các phép cộng quá miền ngày giờ hỗ trợ có thể ném ngoại lệ.
- Phần nano chính xác hơn millisecond; chuyển sang kiểu legacy/database có thể làm tròn hoặc mất phần lẻ tùy API/driver.

Không nên tự đặt một “timezone mặc định” để sửa input thiếu offset mà không thông báo cho nguồn gửi. Khi sai offset, dữ liệu có thể bị dịch nhiều giờ trên timeline.

## 14. Ứng dụng trong REST API, database và log

### Truyền timestamp qua API

Một API có thể nhận:

~~~json
{
  "occurredAt": "2026-10-24T17:15:30+07:00"
}
~~~

Nếu ý định chỉ là “sự kiện đã xảy ra lúc nào”, sau khi parse OffsetDateTime nên chuẩn hóa sang **Instant** để lưu và so sánh. Có thể giữ thêm chuỗi offset ban đầu nếu cần trình bày đúng với dữ liệu nguồn, nhưng nó **không chứng minh địa điểm/múi giờ thực tế**.

Với lịch hẹn ở một địa phương tương lai, cần lưu **ZoneId** riêng; không thể dựa vào +07:00 để suy ra một thành phố. Hợp đồng API nên công bố có chấp nhận offset thiếu hay không, độ chính xác của giây và cách xử lý chuỗi “Z”.

### JDBC và timestamp có múi giờ

Một số CSDL/driver hỗ trợ ánh xạ OffsetDateTime cho các kiểu cột như **TIMESTAMP WITH TIME ZONE**, nhưng chi tiết không đồng nhất giữa các hệ quản trị. Không được giả định cột này lưu nguyên **ZoneId IANA** hoặc giữ nguyên offset đã gửi; có CSDL lưu/chuẩn hóa timestamp và trả offset được chuyển đổi. Hãy kiểm tra tài liệu JDBC/driver/ORM cụ thể và test round-trip.

Đối với một sự kiện, có thể chọn **Instant** hoặc timestamp chuẩn UTC trong mô hình lưu trữ phù hợp. Đối với lịch hẹn địa phương, tách **local date-time, ZoneId**, cùng **Instant đã xác nhận** nếu nghiệp vụ yêu cầu giữ cố định mốc sau khi đặt lịch.

### Logging và sắp xếp

Máy chủ ở các vùng khác nhau có thể ghi timestamp cùng một Instant dưới nhiều offset. Nếu sort theo chuỗi địa phương hay so sánh chỉ trường hour, kết quả có thể sai. Hãy convert về **Instant**, hoặc dùng **isBefore/isAfter** trên OffsetDateTime. Khi cần thiết giữ offset gốc để điều tra, lưu cả cách biểu diễn gốc lẫn Instant chuẩn.

## 15. Lỗi thường gặp và cách sửa

| Sai lầm | Vấn đề | Cách đúng |
| --- | --- | --- |
| Gọi OffsetDateTime.parse với chuỗi không offset | Parse lỗi hoặc thông tin thời điểm không đủ | Dùng LocalDateTime hoặc yêu cầu offset |
| Nghĩ OffsetDateTime lưu thành phố | Không có quy tắc DST hoặc vùng | Lưu ZoneId riêng, dùng ZonedDateTime khi cần |
| Dùng **withOffsetSameLocal** để hiển thị sự kiện ở UTC | Làm đổi Instant | Dùng **withOffsetSameInstant** |
| So sánh **equals** để biết “cùng lúc” | Hai offset khác nhau có thể cùng Instant | Dùng **isEqual**, toInstant hoặc timeLineOrder |
| Dùng **compareTo()==0** để deduplicate Instant | compareTo có tie-break theo local date-time | So sánh Instant |
| Dùng plusDays cho lịch lặp theo giờ địa phương ở vùng DST | Offset giữ cố định và lệch giờ vùng | Giữ LocalTime + ZoneId và giải quyết từng ngày |
| Nhầm phút và tháng trong formatter | **mm** khác **MM** | Viết pattern có kiểm thử |
| Dùng “timezone” của máy chủ cho input không offset | Sai mốc giữa môi trường | Truyền ZoneId/offset theo hợp đồng |
| Quên lưu giá trị từ **plus...**/**with...** | OffsetDateTime immutable | Gán đối tượng kết quả |
| Coi 1 tháng = 30 ngày | Sai ở cuối tháng/năm nhuận | Dùng plusMonths hoặc chính sách lịch |
| Chuyển nano sang milli rồi đòi khôi phục toàn bộ | Mất độ chính xác | Quy định đơn vị và mức chính xác |
| Giả định TIMESTAMP WITH TIME ZONE giữ ZoneId | Sai tùy CSDL | Kiểm tra driver/schema và lưu ZoneId riêng |

## 16. Các tình huống tự kiểm tra

**Câu 1.** Hai giá trị **2026-10-24T17:15+07:00** và **2026-10-24T10:15Z** có cùng mốc không?

Có. Cả hai biểu diễn **2026-10-24T10:15Z** trên timeline. **isEqual** true, còn **equals** false.

**Câu 2.** Chuyển **2026-10-25T01:00+07:00** sang offset Z mà giữ Instant, ngày giờ mới là gì?

**2026-10-24T18:00Z**, tức là ngày hôm trước theo UTC. Dùng **withOffsetSameInstant(ZoneOffset.UTC)**.

**Câu 3.** **withOffsetSameLocal(ZoneOffset.UTC)** trên **2026-10-25T01:00+07:00** tạo Instant nào?

**2026-10-25T01:00Z**. Nó giữ giờ đồng hồ 01:00, nên Instant đã thay đổi 7 giờ.

**Câu 4.** Có thể parse chuỗi **2026-10-24T17:15:30** trực tiếp bằng OffsetDateTime.parse mặc định không?

Không, vì chuỗi thiếu offset. Nó là LocalDateTime; cần bổ sung ZoneOffset hoặc ZoneId cùng chính sách chuyển đổi.

**Câu 5.** Cộng 1 ngày vào OffsetDateTime trong vùng đang chuyển DST có tự chọn offset mới của vùng không?

Không. OffsetDateTime chỉ giữ một offset, không giữ ZoneId khu vực. Muốn giờ lịch của thành phố, dùng ZonedDateTime hoặc LocalDateTime + ZoneId.

**Câu 6.** Nếu hai bản ghi có OffsetDateTime khác nhau nhưng **isEqual** true, có chắc chuỗi hiển thị giống nhau không?

Không. Chúng cùng Instant nhưng có thể hiển thị ngày/giờ và offset khác nhau.

**Câu 7.** OffsetDateTime được tạo từ Instant có thể được đổi hiển thị sang offset mới mà không thay Instant không?

Có. Dùng **withOffsetSameInstant**; hoặc đổi Instant qua **Instant.atOffset(newOffset)**.

**Câu 8.** Nếu muốn tính timeout 90 giây từ một thời điểm, nên dùng gì?

Ưu tiên **Instant.plusSeconds(90)** hoặc **Duration** trên hai Instant. Với OffsetDateTime, plusSeconds(90) cũng tăng 90 giây thật vì offset cố định; còn việc hiển thị theo vùng có thể được chuyển sang kiểu khác sau đó.

## 17. Tóm tắt áp dụng

- **Tạo:** **OffsetDateTime.of(...)**, **LocalDateTime.atOffset(...)**, **Instant.atOffset(...)**, **OffsetDateTime.ofInstant(...)**, **OffsetDateTime.now(clock)**.
- **Đọc:** **getYear/getHour/getOffset**, **toLocalDate/Time/DateTime**, **toInstant**, **toEpochSecond**.
- **Parse/format:** **OffsetDateTime.parse** với chuỗi ISO có offset; **DateTimeFormatter** cho mẫu rõ ràng.
- **Cộng trừ:** **plusDays/plusHours/plusMonths**, **minus...**, **with...**; đối tượng immutable.
- **Đổi offset:** **withOffsetSameInstant** giữ thời điểm, **withOffsetSameLocal** giữ giờ đồng hồ.
- **So sánh:** **isEqual/isBefore/isAfter** theo Instant, **equals** theo toàn giá trị; **timeLineOrder()** nếu chỉ muốn ordering theo mốc.
- **Vùng và DST:** **OffsetDateTime không giữ ZoneId**, nên không tự áp luật chuyển offset theo khu vực.
- **Dữ liệu:** đối với sự kiện đã xảy ra, lưu **Instant** và quy ước rõ độ chính xác; đối với lịch tại địa phương trong tương lai, giữ thêm **ZoneId** và quy tắc lịch.

## Tài liệu tham khảo

- [Java SE 17 — OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html): constructor, getter, parse, plus/minus, compare và chuyển đổi.
- [Java SE 17 — ZoneOffset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html): cấu trúc và miền offset UTC.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): mốc thời gian và tính toán trên timeline.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): giờ địa phương có ZoneId và DST.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO_OFFSET_DATE_TIME và định dạng offset.
- [Java SE 17 — ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html): số đơn vị giữa các Temporal.
