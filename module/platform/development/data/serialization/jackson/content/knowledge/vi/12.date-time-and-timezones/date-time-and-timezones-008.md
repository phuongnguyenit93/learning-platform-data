# Làm việc với Date và Calendar trong mô hình cũ

Trong nhiều ứng dụng Java lâu năm, ngày giờ được biểu diễn bằng `java.util.Date` và `java.util.Calendar`. Những kiểu này vẫn xuất hiện trong entity, DTO, API cũ, thư viện bên thứ ba và hệ thống tích hợp. Jackson hỗ trợ đọc và ghi chúng, nhưng cần hiểu rõ ý nghĩa của từng kiểu, cách Jackson biểu diễn thời gian trong JSON và ảnh hưởng của múi giờ.

`Date` chủ yếu biểu diễn một thời điểm trên dòng thời gian, tính bằng mili giây kể từ Unix epoch. `Calendar` cũng giữ một thời điểm, đồng thời cung cấp cách diễn giải thời điểm đó theo múi giờ, locale và các trường lịch như năm, tháng, ngày, giờ. Hai kiểu này thuộc mô hình ngày giờ cũ của Java; với code mới, `java.time` thường dễ diễn đạt ý nghĩa hơn. Tuy nhiên, khi phải làm việc với hệ thống hiện hữu, cần biết cách Jackson ánh xạ đúng `Date` và `Calendar` mà không làm sai thời điểm hoặc mất thông tin múi giờ cần thiết.

## 1. Phân biệt Date và Calendar

### 1.1. Date biểu diễn một thời điểm

`java.util.Date` đại diện cho một instant: một điểm trên trục thời gian, được lưu dưới dạng số mili giây kể từ `1970-01-01T00:00:00Z`.

```java
Date now = new Date();
long epochMillis = now.getTime();
```

Giá trị `epochMillis` không mang theo múi giờ. Cùng một `Date` có thể được hiển thị thành giờ địa phương khác nhau tùy múi giờ dùng khi format.

Ví dụ, một instant có thể được biểu diễn là:

- `2026-11-12T09:00:00Z` ở UTC.
- `2026-11-12T16:00:00+07:00` tại múi giờ UTC+07:00.

Đây là cùng một thời điểm. `Date` không lưu thông tin rằng nó ban đầu được tạo từ múi giờ nào. Phương thức `Date.toString()` hiển thị theo múi giờ mặc định của môi trường, nên không nên dùng chuỗi này làm hợp đồng trao đổi dữ liệu.

### 1.2. Calendar diễn giải thời điểm theo múi giờ

`Calendar` cung cấp các trường lịch và múi giờ để thao tác với thời gian:

```java
Calendar calendar = Calendar.getInstance(
    TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
);

calendar.set(2026, Calendar.NOVEMBER, 12, 16, 0, 0);
calendar.set(Calendar.MILLISECOND, 0);
```

Lưu ý `Calendar` dùng tháng bắt đầu từ 0: `Calendar.JANUARY` là tháng 0 và `Calendar.DECEMBER` là tháng 11. Vì vậy, khi dùng `calendar.set(year, month, day, ...)`, nên dùng hằng số `Calendar` thay vì truyền số tháng theo cách đánh số thông thường.

`Calendar` giữ một instant cùng cách diễn giải theo múi giờ. Một `GregorianCalendar` được tạo với `Asia/Ho_Chi_Minh` có thể hiển thị cùng instant theo giờ địa phương của múi giờ đó. Nếu chuyển thành `Date` bằng `calendar.getTime()`, kết quả là instant tương ứng; đối tượng `Date` không giữ lại múi giờ của Calendar.

### 1.3. So sánh nhanh

| Đặc điểm | `Date` | `Calendar` |
|---|---|---|
| Bản chất | Instant theo epoch milliseconds | Instant cùng bộ trường lịch và múi giờ |
| Lưu múi giờ riêng | Không | Có |
| Lấy epoch milliseconds | `getTime()` | `getTimeInMillis()` |
| Thay đổi giá trị | Mutable | Mutable |
| Thao tác trường năm/tháng/ngày | Không thuận tiện | Có các trường `Calendar.YEAR`, `MONTH`, `DAY_OF_MONTH` |
| Khởi tạo hiện tại | `new Date()` | `Calendar.getInstance()` |
| Thường gặp trong | API/DTO/entity cũ | Lịch, ứng dụng cũ cần trường lịch hoặc múi giờ |

Hai kiểu đều mutable. Nếu chia sẻ một instance giữa nhiều thành phần, một nơi có thể thay đổi giá trị mà nơi khác không mong đợi. Khi cần giữ trạng thái ổn định, hãy tạo bản sao hoặc chuyển sang kiểu immutable như `Instant`/`ZonedDateTime` ở ranh giới phù hợp.

## 2. Jackson hỗ trợ Date và Calendar như thế nào?

Jackson Databind hỗ trợ sẵn `java.util.Date` và `java.util.Calendar` trong các kiểu dữ liệu ngày giờ cũ. Với các kiểu này, thông thường không cần đăng ký `JavaTimeModule` chỉ để đọc/ghi `Date` hoặc `Calendar`.

Ví dụ DTO:

```java
import java.util.Calendar;
import java.util.Date;

public class LegacyEvent {
    private Date createdAt;
    private Calendar scheduledAt;

    public Date getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Date createdAt) {
        this.createdAt = createdAt;
    }

    public Calendar getScheduledAt() {
        return scheduledAt;
    }

    public void setScheduledAt(Calendar scheduledAt) {
        this.scheduledAt = scheduledAt;
    }
}
```

Với cấu hình mặc định phổ biến của Jackson 2, `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS` được bật, nên `Date` và `Calendar` thường được ghi thành số timestamp mili giây. Ví dụ:

```json
{
  "createdAt": 1794474000000,
  "scheduledAt": 1794477600000
}
```

Timestamp này là số mili giây tính từ Unix epoch, không phải số giây. Khi đọc JSON number vào `Date` hoặc `Calendar`, Jackson diễn giải theo đơn vị mili giây.

Không nên tự giả định mọi API dùng cùng đơn vị. Một hệ thống bên ngoài có thể quy ước Unix timestamp theo giây. Nếu nhận số giây nhưng truyền thẳng vào `Date(long)`, thời điểm sẽ nằm gần năm 1970 thay vì thời điểm mong muốn. Hợp đồng phải ghi rõ đơn vị; nếu cần, chuyển đổi rõ ràng bằng phép nhân 1000 có kiểm soát.

## 3. Ghi Date và Calendar thành chuỗi ISO-8601

Timestamp mili giây dễ xử lý bằng máy nhưng không dễ đọc trực tiếp. Nhiều API muốn biểu diễn thời gian thành chuỗi ISO-8601 có offset hoặc ký hiệu UTC.

Có thể tắt `WRITE_DATES_AS_TIMESTAMPS`:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Jackson sẽ dùng định dạng ngày giờ dạng chuỗi theo date format và timezone của mapper. Với `StdDateFormat`, chuỗi thường có dạng ISO-8601/RFC 3339 tương thích, ví dụ:

```json
{
  "createdAt": "2026-11-12T09:00:00.000+00:00"
}
```

Hình thức chính xác phụ thuộc date format, timezone và phiên bản/cấu hình Jackson. Nếu hợp đồng yêu cầu chính xác chuỗi UTC kết thúc bằng `Z`, hoặc yêu cầu số chữ số phần giây cố định, hãy cấu hình và kiểm thử định dạng thay vì dựa vào mặc định.

## 4. Cấu hình timezone thống nhất cho ObjectMapper

Nếu API quy định tất cả giá trị ngày giờ được serialize và deserialize theo UTC, có thể đặt timezone cho mapper:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.util.StdDateFormat;
import java.util.TimeZone;

ObjectMapper mapper = new ObjectMapper();
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
mapper.setTimeZone(TimeZone.getTimeZone("UTC"));
mapper.setDateFormat(
    new StdDateFormat()
        .withTimeZone(TimeZone.getTimeZone("UTC"))
        .withColonInTimeZone(true)
);
```

Đặt timezone toàn mapper hữu ích khi toàn bộ hợp đồng dùng cùng quy ước. Nếu một trường có yêu cầu riêng, có thể dùng `@JsonFormat` tại property đó.

Hãy nhớ:

- `Date` vốn là instant, không chứa múi giờ. Timezone chỉ ảnh hưởng cách Jackson định dạng hoặc diễn giải chuỗi không có offset.
- `Calendar` có timezone riêng. Khi serialize dạng timestamp, JSON chỉ giữ instant; timezone gốc của Calendar không được thể hiện trong số timestamp.
- Khi serialize dạng chuỗi, timezone dùng để format có thể làm thay đổi phần giờ và offset hiển thị nhưng không nhất thiết thay đổi instant.
- Chuỗi có `Z` hoặc offset như `+07:00` mô tả instant rõ ràng hơn chuỗi không có timezone.

## 5. Dùng JsonFormat cho từng thuộc tính

Nếu một DTO chứa các trường có quy ước khác nhau, `@JsonFormat` cho phép khai báo format riêng.

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.util.Date;

public class AuditRecord {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        timezone = "UTC"
    )
    private Date occurredAt;

    public Date getOccurredAt() {
        return occurredAt;
    }

    public void setOccurredAt(Date occurredAt) {
        this.occurredAt = occurredAt;
    }
}
```

Pattern trên có các thành phần:

| Ký hiệu | Ý nghĩa |
|---|---|
| `yyyy` | Năm theo lịch |
| `MM` | Tháng |
| `dd` | Ngày trong tháng |
| `HH` | Giờ theo hệ 24 giờ |
| `mm` | Phút |
| `ss` | Giây |
| `SSS` | Mili giây |
| `XXX` | Offset múi giờ dạng `Z` hoặc `+07:00` |
| `'T'` | Ký tự T cố định phân cách ngày và giờ |

Không nhầm `MM` (tháng) với `mm` (phút). Cũng nên dùng `yyyy` thay vì `YYYY` nếu muốn năm theo lịch; `YYYY` là week-based year trong hệ pattern của `SimpleDateFormat` và có thể tạo kết quả bất ngờ gần ranh giới năm.

Nếu API muốn múi giờ Việt Nam:

```java
@JsonFormat(
    shape = JsonFormat.Shape.STRING,
    pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
    timezone = "Asia/Ho_Chi_Minh"
)
private Date occurredAt;
```

Với cùng một instant, chuỗi sẽ hiển thị giờ địa phương và offset tương ứng. Nếu API trao đổi giữa nhiều quốc gia, UTC hoặc offset tường minh thường dễ xử lý hơn việc gửi giờ địa phương không có offset.

## 6. Làm việc với Calendar và timezone

`Calendar` lưu timezone, nhưng cách Jackson serialize quyết định thông tin đó có được giữ trong JSON hay không.

### 6.1. Timestamp không bảo toàn timezone gốc

Ví dụ:

```java
Calendar calendar = Calendar.getInstance(
    TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
);
calendar.setTimeInMillis(1794474000000L);

String json = mapper.writeValueAsString(calendar);
```

Nếu mapper đang ghi timestamp, JSON chỉ chứa số mili giây. Khi deserialize số đó thành `Calendar`, Jackson phải tạo Calendar theo timezone mặc định hoặc timezone đã cấu hình cho mapper; timezone ban đầu của object không thể suy ra từ timestamp.

Nếu cần giữ cả instant và timezone như một phần của hợp đồng, hãy serialize thành chuỗi có offset hoặc gửi hai trường riêng (ví dụ instant UTC và zone ID). Offset như `+07:00` không đồng nhất với zone ID `Asia/Ho_Chi_Minh`: zone ID chứa quy tắc lịch sử và thay đổi theo thời gian, còn offset chỉ là độ lệch tại một thời điểm.

### 6.2. Định dạng Calendar bằng chuỗi

Có thể đặt `@JsonFormat` cho Calendar:

```java
public class Appointment {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        timezone = "Asia/Ho_Chi_Minh"
    )
    private Calendar startAt;

    public Calendar getStartAt() {
        return startAt;
    }

    public void setStartAt(Calendar startAt) {
        this.startAt = startAt;
    }
}
```

Timezone trong annotation quy định cách format và parse property theo cấu hình đó. Nếu cần giữ nguyên zone ID tùy theo từng người dùng, chỉ có offset trong chuỗi không đủ để lưu toàn bộ quy tắc timezone. Hãy lưu zone ID riêng hoặc dùng kiểu `ZonedDateTime` ở mô hình mới.

## 7. Chuỗi ngày giờ không có timezone rất dễ gây nhầm lẫn

Một chuỗi như:

```json
{
  "scheduledAt": "2026-11-12 16:00:00"
}
```

không cho biết 16:00 thuộc múi giờ nào. Nếu server ở UTC nhưng người dùng nhập giờ Việt Nam, cùng chuỗi đó có thể được hiểu thành hai instant khác nhau.

Nếu buộc phải duy trì định dạng cũ không có offset, cần quy định timezone ở hợp đồng và cấu hình nhất quán:

```java
@JsonFormat(
    shape = JsonFormat.Shape.STRING,
    pattern = "yyyy-MM-dd HH:mm:ss",
    timezone = "Asia/Ho_Chi_Minh"
)
private Date scheduledAt;
```

Định dạng này vẫn có rủi ro nếu producer và consumer không tuân theo cùng quy ước. Với API mới, ưu tiên ISO-8601 có `Z` hoặc offset:

```json
{
  "scheduledAt": "2026-11-12T16:00:00+07:00"
}
```

Một chuỗi giờ địa phương không có offset có thể là yêu cầu hợp lệ nếu nó mô tả giờ trên lịch, ví dụ “cuộc hẹn lúc 9 giờ sáng theo giờ địa phương của chi nhánh”. Trong trường hợp đó, cần truyền cả zone ID hoặc xác định zone theo tài nguyên, thay vì tự coi nó là instant UTC.

## 8. Đơn vị timestamp: giây hay mili giây?

`Date` và `Calendar` dùng mili giây từ epoch. Một số API khác gửi Unix timestamp theo giây.

Ví dụ:

```java
long epochSeconds = 1794474000L;
Date fromSeconds = new Date(Math.multiplyExact(epochSeconds, 1000L));

long epochMillis = 1794474000000L;
Date fromMillis = new Date(epochMillis);
```

`Math.multiplyExact` giúp phát hiện tràn số khi nhân giây với 1000. Không nên tự đoán đơn vị dựa trên số chữ số vì điều đó dễ sai ở dữ liệu lịch sử, tương lai hoặc timestamp có đơn vị khác. Hãy ghi rõ đơn vị trong schema, tên field hoặc hợp đồng.

Nếu JSON number được ánh xạ thẳng vào `Date`, Jackson dùng mili giây. Nếu API gửi giây, hãy chuyển đổi ở adapter hoặc dùng custom deserializer có hợp đồng rõ ràng. Không thay đổi ý nghĩa timestamp toàn cục của mapper nếu chỉ một đối tác gửi đơn vị khác.

## 9. Calendar có tính mutable và lenient

`Calendar` có thể bị thay đổi sau khi được tạo:

```java
Calendar calendar = Calendar.getInstance();
calendar.add(Calendar.DAY_OF_MONTH, 1);
```

Một reference dùng chung có thể bị thay đổi ngoài ý muốn. Khi lưu trữ giá trị trong domain object hoặc truyền giữa nhiều thành phần, cân nhắc copy:

```java
Calendar copy = (Calendar) original.clone();
```

`Calendar` cũng mặc định có thể lenient. Ví dụ, một ngày vượt phạm vi tháng có thể được chuẩn hóa sang tháng kế tiếp thay vì bị từ chối ngay. Nếu đọc dữ liệu lịch cũ và cần kiểm tra chặt chẽ:

```java
Calendar calendar = new GregorianCalendar(
    TimeZone.getTimeZone("UTC")
);
calendar.setLenient(false);
```

Jackson không tự bảo đảm mọi giá trị lịch hợp lệ theo quy tắc nghiệp vụ. Nếu format đầu vào cho phép ngày tháng, hãy kiểm tra ngày hợp lệ sau khi parse hoặc dùng kiểu `java.time` có API parse/validation rõ ràng hơn.

## 10. Các lỗi thường gặp khi dùng Jackson với Date và Calendar

### 10.1. Nhầm timestamp mili giây với giây

Đưa timestamp giây vào `new Date(long)` sẽ tạo thời điểm sai rất xa. Xác định đơn vị trước khi chuyển đổi.

### 10.2. Dựa vào timezone mặc định của máy chủ

Máy local có thể dùng UTC+07, trong khi container production dùng UTC. Nếu chuỗi không có offset, kết quả có thể khác nhau giữa môi trường. Hãy đặt timezone tường minh hoặc dùng chuỗi có offset.

### 10.3. Nghĩ rằng Date giữ timezone

`Date` chỉ giữ instant. Gọi `toString()` có thể hiển thị timezone mặc định của máy nhưng đó không phải timezone được lưu trong Date.

### 10.4. Nghĩ timestamp bảo toàn Calendar timezone

Số epoch milliseconds chỉ giữ instant. Khi khôi phục thành Calendar, timezone được chọn từ cấu hình hoặc môi trường, không thể khôi phục zone ID ban đầu chỉ từ số đó.

### 10.5. Dùng pattern sai

`MM` là tháng, `mm` là phút; `HH` là giờ 24h, `hh` là giờ 12h; `XXX` biểu diễn offset. Pattern sai có thể parse được nhưng tạo thời gian không mong đợi.

### 10.6. Dùng chuỗi không offset cho nhiều múi giờ

`2026-11-12 16:00:00` không xác định một instant nếu không biết timezone. Hãy đưa offset hoặc zone ID vào hợp đồng.

### 10.7. Serialize Calendar nhưng quên nhu cầu giữ zone ID

Nếu hệ thống cần hiển thị lại theo đúng vùng lịch ban đầu, timestamp đơn lẻ không đủ. Lưu zone ID riêng hoặc chuyển mô hình sang `ZonedDateTime`.

## 11. Kiểm thử Date và Calendar

Nên kiểm thử giá trị epoch hoặc instant thay vì so sánh chuỗi `Date.toString()`, vì chuỗi đó phụ thuộc timezone mặc định của JVM.

Ví dụ kiểm thử Date với timestamp:

```java
class LegacyDateJacksonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsEpochMillisecondsIntoDate() throws Exception {
        long expectedMillis = 1794474000000L;
        Date date = mapper.readValue(
            Long.toString(expectedMillis),
            Date.class
        );

        assertEquals(expectedMillis, date.getTime());
    }
}
```

Với Calendar, kiểm tra cả instant và timezone khi hợp đồng yêu cầu giữ timezone:

```java
Calendar calendar = mapper.readValue(json, Calendar.class);

assertEquals(expectedMillis, calendar.getTimeInMillis());
assertEquals("UTC", calendar.getTimeZone().getID());
```

Test timezone chỉ có ý nghĩa khi mapper/annotation thực sự quy định timezone mong muốn. Nếu JSON chỉ là timestamp, hãy xác nhận rằng test không kỳ vọng khôi phục zone ID ban đầu vốn không có trong dữ liệu.

Với định dạng chuỗi, hãy kiểm thử:

- JSON đầu vào có offset `Z`.
- JSON đầu vào có offset `+07:00`.
- Chuỗi không có offset nếu API cũ vẫn hỗ trợ.
- Mili giây có đủ, thiếu hoặc khác số chữ số.
- Giá trị ở gần thời điểm chuyển DST của các timezone có quy tắc DST.
- Ngày không hợp lệ và timestamp ngoài miền nghiệp vụ.
- Cùng payload chạy trong môi trường có timezone mặc định khác nhau.

## 12. Khi nào nên chuyển sang java.time?

`Date` và `Calendar` vẫn cần thiết khi tích hợp code cũ, nhưng API `java.time` từ Java 8 trở lên mô tả ý nghĩa thời gian rõ ràng hơn:

| Kiểu cũ | Kiểu java.time thường phù hợp | Ý nghĩa |
|---|---|---|
| `Date` | `Instant` | Một thời điểm tuyệt đối trên dòng thời gian |
| `Calendar` khi cần vùng thời gian | `ZonedDateTime` | Ngày giờ cùng zone ID và quy tắc timezone |
| `Calendar` khi cần offset | `OffsetDateTime` | Ngày giờ cùng offset UTC |
| Trường ngày không có giờ | `LocalDate` | Ngày lịch, không có timezone |
| Trường giờ không có ngày | `LocalTime` | Giờ trong ngày, không có timezone |
| Ngày giờ địa phương không xác định zone | `LocalDateTime` | Ngày giờ trên lịch, chưa xác định instant |

Jackson 2 cần module `jackson-datatype-jsr310` và `JavaTimeModule` để hỗ trợ tốt các kiểu `java.time`:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Đăng ký module và kiểm thử format theo phiên bản Jackson đang dùng. Với ứng dụng Spring Boot, thường nên để framework quản lý module và tùy chỉnh qua builder/customizer phù hợp thay vì tạo mapper độc lập làm mất cấu hình tự động.

### 12.1. Chuyển đổi giữa Date và Instant

`Date` và `Instant` cùng biểu diễn một thời điểm, nên chuyển đổi trực tiếp:

```java
Date legacyDate = new Date();
Instant instant = legacyDate.toInstant();

Date restored = Date.from(instant);
```

### 12.2. Chuyển đổi giữa Calendar và ZonedDateTime

```java
Calendar legacyCalendar = Calendar.getInstance(
    TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
);

ZonedDateTime zoned = legacyCalendar.toInstant()
    .atZone(legacyCalendar.getTimeZone().toZoneId());

GregorianCalendar restored = GregorianCalendar.from(zoned);
```

Khi chuyển đổi, hãy xác định rõ muốn giữ instant hay giữ giờ trên lịch. Nếu chỉ giữ instant, timezone có thể được chọn lại khi hiển thị. Nếu cần giữ vùng lịch, phải giữ cả `ZoneId`.

## 13. Quy trình cấu hình cho hệ thống dùng mô hình cũ

Khi tích hợp một API hoặc file cũ có `Date`/`Calendar`, hãy làm theo trình tự:

1. Xác định field biểu diễn instant, ngày lịch hay giờ địa phương.
2. Xác định JSON dùng timestamp hay chuỗi; nếu timestamp, ghi rõ giây hay mili giây.
3. Nếu là chuỗi, yêu cầu ISO-8601 có offset khi có thể; nếu không, quy định timezone cụ thể.
4. Cấu hình `ObjectMapper` ở một nơi, đặt timezone và date format trước khi dùng.
5. Dùng `@JsonFormat` cho property có format riêng; tránh thay đổi mapper chung theo từng request.
6. Kiểm tra nhu cầu giữ zone ID nếu DTO dùng `Calendar`; timestamp không lưu lại thông tin đó.
7. Kiểm thử hai chiều serialize/deserialize và chạy test với timezone mặc định khác nhau.
8. Với code mới, cân nhắc `Instant`, `OffsetDateTime`, `ZonedDateTime` hoặc `LocalDate` theo ý nghĩa dữ liệu.

## 14. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Đọc/ghi `Date` và `Calendar` bằng Jackson | Dùng hỗ trợ có sẵn của Jackson Databind |
| Ghi ngày giờ thành số epoch | Giữ `WRITE_DATES_AS_TIMESTAMPS` theo hợp đồng; đơn vị là mili giây |
| Ghi thành chuỗi | Tắt `WRITE_DATES_AS_TIMESTAMPS` hoặc đặt `@JsonFormat(shape = STRING)` |
| Dùng timezone chung | Cấu hình timezone và date format trên mapper trước khi dùng |
| Dùng format riêng cho một field | `@JsonFormat(pattern = ..., timezone = ...)` |
| Giữ instant | Dùng `Date`/`Instant` hoặc timestamp/chuỗi có offset |
| Giữ vùng lịch | Giữ zone ID cùng thời gian; cân nhắc `ZonedDateTime` |
| Nhận Unix timestamp theo giây | Chuyển đổi rõ ràng sang mili giây trước khi tạo `Date` |
| Tránh phụ thuộc timezone môi trường | Dùng UTC/offset tường minh và test trên nhiều timezone |

`Date` và `Calendar` vẫn xuất hiện rộng rãi trong hệ thống Java cũ và được Jackson hỗ trợ trực tiếp. Để tránh sai lệch, hãy nhớ `Date` biểu diễn instant, `Calendar` bổ sung cách diễn giải theo timezone, còn timestamp JSON thông thường chỉ giữ mili giây từ epoch. Đặt timezone và định dạng tường minh, phân biệt giây với mili giây, kiểm thử cả hai chiều chuyển đổi và lưu zone ID riêng nếu hợp đồng cần giữ vùng lịch. Với phần phát triển mới, chọn kiểu `java.time` theo đúng ý nghĩa thời gian sẽ giúp mô hình rõ ràng và ít phụ thuộc vào trạng thái mutable của API cũ.
