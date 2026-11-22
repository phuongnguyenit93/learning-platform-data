# Biểu diễn `LocalDate`, `LocalTime` và `LocalDateTime` theo ngữ nghĩa

Khi trao đổi ngày giờ qua JSON, điều quan trọng không chỉ là định dạng chuỗi mà còn là **ý nghĩa thời gian** mà giá trị đại diện. `LocalDate`, `LocalTime` và `LocalDateTime` thuộc Java Time API (`java.time`), nhưng không kiểu nào trong ba kiểu này chứa múi giờ hoặc UTC offset.

- `LocalDate` biểu diễn một ngày trên lịch, không có giờ.
- `LocalTime` biểu diễn giờ trên đồng hồ, không có ngày.
- `LocalDateTime` biểu diễn ngày và giờ trên lịch/đồng hồ, không xác định một thời điểm duy nhất trên dòng thời gian.

Jackson có thể serialize và deserialize các kiểu này qua module Java Time. Tuy nhiên, Jackson không thể tự suy ra múi giờ mà dữ liệu không mang theo. Nếu ứng dụng coi một `LocalDateTime` là thời điểm toàn cầu rồi tự động gắn UTC hoặc múi giờ máy chủ, kết quả có thể lệch giờ so với ý nghĩa ban đầu.

Các ví dụ dưới đây dùng Jackson 2.x với `jackson-datatype-jsr310` và package `com.fasterxml.jackson`. Hãy giữ các module Jackson cùng một dòng version tương thích bằng BOM hoặc dependency management của dự án.

## 1. Ba kiểu thời gian biểu diễn ba loại thông tin khác nhau

| Kiểu Java | Thông tin chứa trong giá trị | Ví dụ ISO | Có xác định được một instant không? |
|---|---|---|---|
| `LocalDate` | Năm, tháng, ngày | `2026-11-12` | Không |
| `LocalTime` | Giờ, phút, giây, phần giây | `14:30:15.250` | Không |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương | `2026-11-12T14:30:15.250` | Không |

`LocalDateTime` không có chữ `Local` chỉ vì tên gọi. Nó thực sự là một cặp thông tin ngày và giờ không gắn với offset hay zone. Cùng một giá trị `2026-11-12T14:30` có thể tương ứng với những instant khác nhau tùy múi giờ được áp dụng.

Các kiểu thường được dùng khi cần thêm thông tin múi giờ:

| Kiểu Java | Ý nghĩa |
|---|---|
| `Instant` | Một điểm trên dòng thời gian, thường biểu diễn theo UTC |
| `OffsetDateTime` | Ngày giờ kèm UTC offset, ví dụ `+07:00` |
| `ZonedDateTime` | Ngày giờ kèm `ZoneId`, ví dụ `Asia/Ho_Chi_Minh`, bao gồm quy tắc múi giờ |

Chọn kiểu theo thông tin nghiệp vụ thực sự cần lưu. Một ngày sinh thường là `LocalDate`; giờ mở cửa hằng ngày có thể là `LocalTime`; thời điểm người dùng đặt lịch trong một múi giờ cụ thể thường cần `OffsetDateTime` hoặc `ZonedDateTime`; thời điểm sự kiện đã xảy ra thường phù hợp với `Instant`.

## 2. Ý nghĩa của `LocalDate`

`LocalDate` đại diện cho một ngày lịch, chẳng hạn ngày sinh, ngày phát hành hóa đơn hoặc ngày nghỉ. Nó không chứa thời gian trong ngày và không phụ thuộc múi giờ.

```java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1995, 4, 18);
LocalDate invoiceDate = LocalDate.parse("2026-11-12");
```

Biểu diễn ISO mặc định là `yyyy-MM-dd` theo quy ước ngày ISO. Ví dụ:

```text
2026-11-12
```

Không nên chuyển ngày sinh thành `Instant` chỉ để ghi vào JSON nếu nghiệp vụ chỉ quan tâm ngày trên lịch. Khi đổi ngày lịch thành instant, ứng dụng buộc phải chọn một giờ và múi giờ; hai thông tin này không có trong `LocalDate` ban đầu.

### 2.1. Ví dụ dùng `LocalDate` trong DTO

```java
import java.time.LocalDate;

public class EmployeeRequest {
    private String name;
    private LocalDate birthDate;

    public EmployeeRequest() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public LocalDate getBirthDate() {
        return birthDate;
    }

    public void setBirthDate(LocalDate birthDate) {
        this.birthDate = birthDate;
    }
}
```

JSON:

```json
{
  "name": "An",
  "birthDate": "1995-04-18"
}
```

Jackson đọc chuỗi ngày thành `LocalDate`. Không có giờ mặc định được thêm vào; giá trị vẫn chỉ là ngày `1995-04-18`.

## 3. Ý nghĩa của `LocalTime`

`LocalTime` đại diện cho giờ trên đồng hồ, chẳng hạn giờ mở cửa, giờ bắt đầu ca làm hoặc thời điểm diễn ra một hoạt động lặp lại mỗi ngày.

```java
import java.time.LocalTime;

LocalTime openingTime = LocalTime.of(8, 30);
LocalTime meetingTime = LocalTime.parse("14:30:15");
```

Biểu diễn ISO thường có dạng `HH:mm:ss`, có thể có phần giây thập phân:

```text
08:30:00
14:30:15.250
```

`LocalTime` không chứa ngày. Vì vậy, `08:30` không đủ để xác định một instant và cũng không cho biết đó là 08:30 ở Hà Nội, Tokyo hay New York.

### 3.1. Ví dụ giờ mở cửa

```java
public class StoreHours {
    private LocalTime opensAt;
    private LocalTime closesAt;

    public StoreHours() {
    }

    public LocalTime getOpensAt() {
        return opensAt;
    }

    public void setOpensAt(LocalTime opensAt) {
        this.opensAt = opensAt;
    }

    public LocalTime getClosesAt() {
        return closesAt;
    }

    public void setClosesAt(LocalTime closesAt) {
        this.closesAt = closesAt;
    }
}
```

JSON:

```json
{
  "opensAt": "08:30:00",
  "closesAt": "21:00:00"
}
```

Nếu cửa hàng hoạt động tại một địa điểm cụ thể, múi giờ thường thuộc cấu hình của địa điểm đó. Không cần nhúng múi giờ vào từng `LocalTime` nếu giờ mở cửa chỉ là giờ địa phương lặp lại theo lịch của cửa hàng. Khi cần tính instant của ngày cụ thể, kết hợp ngày, giờ và `ZoneId` ở bước nghiệp vụ.

## 4. Ý nghĩa của `LocalDateTime`

`LocalDateTime` kết hợp ngày và giờ nhưng vẫn không có UTC offset hoặc múi giờ:

```java
import java.time.LocalDateTime;

LocalDateTime appointment = LocalDateTime.of(2026, 11, 12, 14, 30);
LocalDateTime parsed = LocalDateTime.parse("2026-11-12T14:30:00");
```

Biểu diễn ISO thường có dạng:

```text
2026-11-12T14:30:00
```

Ký tự `T` phân cách phần ngày và phần giờ. Giá trị này không nói rằng cuộc hẹn diễn ra tại UTC, UTC+7 hay bất kỳ zone nào khác.

### 4.1. Dùng `LocalDateTime` khi nghiệp vụ thực sự là ngày giờ địa phương

Ví dụ, một biểu mẫu nội bộ yêu cầu người dùng nhập “ngày 12 tháng 11 năm 2026 lúc 14:30” theo giờ địa phương của một địa điểm đã biết. Có thể nhận giá trị thành `LocalDateTime`:

```json
{
  "appointmentTime": "2026-11-12T14:30:00"
}
```

DTO:

```java
public class AppointmentRequest {
    private LocalDateTime appointmentTime;

    public LocalDateTime getAppointmentTime() {
        return appointmentTime;
    }

    public void setAppointmentTime(LocalDateTime appointmentTime) {
        this.appointmentTime = appointmentTime;
    }
}
```

Nếu hệ thống cần thực hiện nhắc lịch trên toàn cầu, phải biết múi giờ của địa điểm/người dùng và chuyển đổi có chủ đích. Chỉ lưu `LocalDateTime` có thể chưa đủ để khôi phục instant chính xác sau này.

## 5. Cấu hình Jackson để xử lý Java Time

Jackson Core/Databind không tự cung cấp toàn bộ hỗ trợ cho các kiểu `java.time` trong mọi cấu hình. Với Jackson 2.x, module cần dùng là `jackson-datatype-jsr310`.

Ví dụ dependency Gradle:

```groovy
dependencies {
    implementation platform("com.fasterxml.jackson:jackson-bom:<jackson-2-version>")
    implementation "com.fasterxml.jackson.core:jackson-databind"
    implementation "com.fasterxml.jackson.datatype:jackson-datatype-jsr310"
}
```

Thay `<jackson-2-version>` bằng version 2.x mà dự án sử dụng. Nếu framework đã quản lý Jackson qua BOM, nên dùng cơ chế quản lý phiên bản đó để tránh các module lệch version.

Đăng ký module:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Hai dòng cấu hình có mục đích khác nhau:

- `registerModule(new JavaTimeModule())` đăng ký serializer/deserializer cho các kiểu Java Time.
- `disable(WRITE_DATES_AS_TIMESTAMPS)` yêu cầu Jackson ghi ngày giờ theo dạng chuỗi thay vì dạng timestamp/array ở những kiểu có hỗ trợ dạng đó.

Nên cấu hình mapper hoàn tất trước khi chia sẻ nó giữa các luồng xử lý. Không thay đổi cấu hình sau khi mapper đã được đưa vào sử dụng.

Một số framework tự đăng ký Java Time module hoặc cấu hình Jackson sẵn. Hãy kiểm tra cấu hình hiện tại trước khi đăng ký trùng lặp hoặc tạo thêm mapper ngoài ý muốn.

## 6. Serialize ba kiểu thành chuỗi ISO

Với cấu hình module và chuỗi ở phần trước:

```java
LocalDate date = LocalDate.of(2026, 11, 12);
LocalTime time = LocalTime.of(14, 30, 15);
LocalDateTime dateTime = LocalDateTime.of(2026, 11, 12, 14, 30, 15);

String dateJson = mapper.writeValueAsString(date);
String timeJson = mapper.writeValueAsString(time);
String dateTimeJson = mapper.writeValueAsString(dateTime);
```

Các kết quả có dạng:

```json
"2026-11-12"
```

```json
"14:30:15"
```

```json
"2026-11-12T14:30:15"
```

Đây là ba JSON string riêng biệt. Khi là property của một DTO, các chuỗi này xuất hiện ở vị trí value của property tương ứng.

### 6.1. Tắt timestamp để tránh dạng array

Trong Jackson 2.x, `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS` có thể làm một số kiểu Java Time không có instant được ghi thành dạng array các thành phần thay vì chuỗi ISO. Ví dụ, ngày có thể được biểu diễn bằng các thành phần năm/tháng/ngày; ngày giờ có thể được biểu diễn bằng các thành phần ngày và giờ.

Dạng array không nhất thiết sai, nhưng thường khó đọc và dễ gây hiểu nhầm khi API mong đợi một chuỗi ngày giờ. Nếu hợp đồng yêu cầu ISO text, hãy tắt feature như sau:

```java
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Không nên dựa vào default của framework hoặc mapper được tạo ở nơi khác. Hãy xác nhận output thực tế và cấu hình tường minh theo hợp đồng API.

## 7. Deserialize chuỗi ISO thành Java Time

Khi module đã được đăng ký, Jackson có thể đọc các chuỗi ISO tương ứng:

```java
LocalDate date = mapper.readValue("\"2026-11-12\"", LocalDate.class);
LocalTime time = mapper.readValue("\"14:30:15\"", LocalTime.class);
LocalDateTime dateTime = mapper.readValue(
        "\"2026-11-12T14:30:15\"",
        LocalDateTime.class
);
```

Kết quả giữ nguyên ngữ nghĩa của kiểu đích:

- `LocalDate` không tự sinh giờ 00:00.
- `LocalTime` không tự sinh ngày hôm nay.
- `LocalDateTime` không tự gắn zone mặc định hoặc `Z` ở cuối.

Nếu chuỗi chứa thông tin mà kiểu đích không thể biểu diễn, ví dụ `Z` hoặc `+07:00` cho một `LocalDateTime`, cần chọn kiểu có offset/zone hoặc định nghĩa rõ cách xử lý ở biên hệ thống. Đừng bỏ thông tin offset một cách vô thức.

## 8. Dùng các `DateTimeFormatter` ISO phù hợp

Java Time API cung cấp formatter chuẩn cho các kiểu local:

| Formatter | Kiểu tương ứng | Dạng ví dụ |
|---|---|---|
| `DateTimeFormatter.ISO_LOCAL_DATE` | `LocalDate` | `2026-11-12` |
| `DateTimeFormatter.ISO_LOCAL_TIME` | `LocalTime` | `14:30:15.250` |
| `DateTimeFormatter.ISO_LOCAL_DATE_TIME` | `LocalDateTime` | `2026-11-12T14:30:15.250` |

Có thể dùng trực tiếp trong Java:

```java
String dateText = date.format(DateTimeFormatter.ISO_LOCAL_DATE);
String timeText = time.format(DateTimeFormatter.ISO_LOCAL_TIME);
String dateTimeText = dateTime.format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
```

Đọc lại:

```java
LocalDate date = LocalDate.parse(dateText, DateTimeFormatter.ISO_LOCAL_DATE);
LocalTime time = LocalTime.parse(timeText, DateTimeFormatter.ISO_LOCAL_TIME);
LocalDateTime dateTime = LocalDateTime.parse(
        dateTimeText,
        DateTimeFormatter.ISO_LOCAL_DATE_TIME
);
```

Với định dạng API riêng, có thể tạo formatter bằng `DateTimeFormatter.ofPattern(...)`. Formatter nên được dùng nhất quán cho cả chiều đọc và ghi. `DateTimeFormatter` là immutable và thread-safe, nên có thể tái sử dụng.

## 9. Quy định định dạng riêng bằng `@JsonFormat`

Nếu API yêu cầu ngày theo dạng `dd/MM/yyyy` thay vì ISO, có thể khai báo pattern cho property:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

public class ReportRequest {
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "dd/MM/uuuu")
    private LocalDate reportDate;

    public LocalDate getReportDate() {
        return reportDate;
    }

    public void setReportDate(LocalDate reportDate) {
        this.reportDate = reportDate;
    }
}
```

JSON:

```json
{
  "reportDate": "12/11/2026"
}
```

Với `LocalTime` và `LocalDateTime`, có thể quy định pattern tương tự:

```java
public class ShiftRequest {
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "HH:mm:ss")
    private LocalTime startsAt;

    @JsonFormat(shape = JsonFormat.Shape.STRING,
                pattern = "dd/MM/uuuu HH:mm:ss")
    private LocalDateTime localStartsAt;

    // getters và setters
}
```

Pattern phải khớp chính xác hợp đồng. Ví dụ `MM` là tháng, còn `mm` là phút; `HH` là giờ theo hệ 24 giờ, còn `hh` là hệ 12 giờ và thường cần thông tin AM/PM. Dùng sai chữ hoa/thường có thể tạo ra dữ liệu sai hoặc lỗi parse.

`@JsonFormat` trên `LocalDateTime` chỉ định cách trình bày các thành phần local. Thuộc tính `timezone` không thể biến `LocalDateTime` thành một kiểu có zone; nếu cần offset hoặc zone trong JSON, hãy dùng kiểu Java có mang thông tin đó.

## 10. Không gắn `Z` hoặc offset vào `LocalDateTime` nếu không có ý nghĩa

Các chuỗi sau mang ý nghĩa khác nhau:

```text
2026-11-12T14:30:00
2026-11-12T14:30:00Z
2026-11-12T14:30:00+07:00
```

- Chuỗi đầu tiên là ngày giờ địa phương, không có offset.
- Chuỗi thứ hai chỉ rõ thời điểm UTC.
- Chuỗi thứ ba chỉ rõ thời điểm có offset UTC+7.

Không nên nối thêm `Z` vào chuỗi `LocalDateTime` chỉ để làm cho nó trông giống timestamp. `Z` là ký hiệu UTC, nghĩa là đã có một quy ước về instant. Nếu dữ liệu gốc không có thông tin đó, thêm `Z` sẽ tự tạo ra một ý nghĩa mới và có thể khiến hệ thống khác diễn giải sai.

Tương tự, không nên dùng `LocalDateTime` để đọc chuỗi có offset rồi bỏ offset đi nếu offset quan trọng đối với nghiệp vụ. Hãy deserialize vào `OffsetDateTime` hoặc `Instant` theo hợp đồng.

## 11. Chuyển `LocalDateTime` thành instant cần `ZoneId`

Một `LocalDateTime` chỉ trở thành một instant khi được kết hợp với múi giờ. Ví dụ:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 12, 14, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant = local.atZone(zone).toInstant();
```

Múi giờ phải đến từ nghiệp vụ hoặc metadata đã biết, ví dụ zone của chi nhánh, lịch hẹn hoặc người dùng. Không nên mặc định lấy `ZoneId.systemDefault()` cho dữ liệu cần nhất quán giữa máy phát triển, server và môi trường triển khai.

Nếu cần gửi lại thời điểm đã xác định cho hệ thống khác, có thể ghi `Instant` hoặc `OffsetDateTime`:

```java
import java.time.OffsetDateTime;

OffsetDateTime offsetDateTime = local.atZone(zone).toOffsetDateTime();
```

JSON của `OffsetDateTime` có thể mang offset, ví dụ `2026-11-12T14:30:00+07:00`; JSON của `Instant` thường được biểu diễn theo UTC với `Z`. Đây là những kiểu phù hợp hơn khi hợp đồng cần một thời điểm cụ thể.

## 12. Giờ địa phương và quy tắc DST

Với các múi giờ có áp dụng daylight saving time (DST), một `LocalDateTime` có thể rơi vào:

- **Giờ không tồn tại:** đồng hồ nhảy tới phía trước, bỏ qua một khoảng giờ địa phương.
- **Giờ xuất hiện hai lần:** đồng hồ lùi lại, một khoảng giờ địa phương xảy ra hai lần với hai offset khác nhau.

Trong các trường hợp đó, `LocalDateTime` tự nó không đủ để xác định instant duy nhất. Khi gọi `local.atZone(zone)`, Java áp dụng quy tắc xử lý mặc định của `ZonedDateTime` cho khoảng giờ bị trùng hoặc bị thiếu. Nếu lịch hẹn, giao dịch hoặc lịch vận hành cần chính sách cụ thể, ứng dụng nên kiểm tra `ZoneRules` và yêu cầu người dùng/chính sách nghiệp vụ giải quyết trường hợp mơ hồ.

Ví dụ kiểm tra các offset hợp lệ tại một local date-time:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import java.time.ZoneOffset;
import java.util.List;

LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

List<ZoneOffset> validOffsets = rules.getValidOffsets(local);

if (validOffsets.isEmpty()) {
    // Local time nằm trong khoảng bị bỏ qua khi chuyển DST.
} else if (validOffsets.size() > 1) {
    // Local time xuất hiện hai lần; cần chọn offset theo chính sách.
} else {
    // Có đúng một offset hợp lệ.
}
```

Không phải múi giờ nào cũng có DST. Ví dụ `Asia/Ho_Chi_Minh` hiện không áp dụng quy tắc DST theo lịch thông dụng, nhưng vẫn nên lưu zone ID nếu nghiệp vụ cần quy tắc địa phương dài hạn thay vì tự giả định offset cố định mãi mãi.

## 13. Phân biệt `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime`

| Kiểu | Ví dụ | Mang thông tin gì? | Khi nên dùng |
|---|---|---|---|
| `LocalDateTime` | `2026-11-12T14:30:00` | Ngày và giờ địa phương, không zone/offset | Giờ trên lịch địa phương khi zone được quản lý riêng hoặc chưa cần xác định instant |
| `OffsetDateTime` | `2026-11-12T14:30:00+07:00` | Ngày giờ và offset cụ thể | API cần biểu diễn một thời điểm với offset |
| `ZonedDateTime` | Ngày giờ cùng `Asia/Ho_Chi_Minh` | Ngày giờ, zone ID và quy tắc múi giờ | Lịch địa phương cần tuân theo quy tắc của một vùng |
| `Instant` | `2026-11-12T07:30:00Z` | Một thời điểm tuyệt đối | Audit, event timestamp, thời điểm tạo/cập nhật |

Một offset như `+07:00` không giống một `ZoneId` như `Asia/Ho_Chi_Minh`. Offset là độ lệch tại một thời điểm; zone ID đại diện cho bộ quy tắc có thể thay đổi theo lịch sử hoặc tương lai. Nếu cần tái hiện lịch địa phương qua nhiều năm, zone ID thường mang ý nghĩa đầy đủ hơn.

## 14. Những lỗi thường gặp khi xử lý Local date/time

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Jackson không hỗ trợ `LocalDate`/`LocalDateTime` | Thiếu `jackson-datatype-jsr310` hoặc chưa đăng ký `JavaTimeModule` | Thêm module đúng version và đăng ký vào mapper |
| JSON ngày giờ thành array | `WRITE_DATES_AS_TIMESTAMPS` đang bật | Tắt feature nếu hợp đồng yêu cầu chuỗi |
| Chuỗi có `Z` không đọc được vào `LocalDateTime` | Input có offset nhưng target không có offset | Dùng `OffsetDateTime`/`Instant` hoặc xử lý offset rõ ràng |
| Giờ bị lệch sau khi chuyển sang timestamp | Tự gắn system default zone hoặc chuyển local time không có zone | Xác định `ZoneId` từ nghiệp vụ và chuyển đổi tường minh |
| Ngày sinh lệch một ngày ở hệ thống khác | Biến `LocalDate` thành instant ở một zone rồi đọc ở zone khác | Giữ ngày sinh là `LocalDate` xuyên suốt hợp đồng |
| Giờ lịch hẹn không xác định duy nhất | Local time rơi vào DST overlap/gap | Dùng zone rules và chính sách xử lý mơ hồ |
| Pattern parse sai tháng/phút | Nhầm `MM` với `mm`, `HH` với `hh` | Kiểm tra pattern và test cả chiều đọc/ghi |
| Dữ liệu thiếu phần giây bị từ chối | Pattern hoặc hợp đồng yêu cầu chính xác độ chính xác | Thống nhất độ chính xác và formatter; không tự cắt dữ liệu nếu không có quy tắc |

## 15. Kiểm thử biểu diễn và round-trip

Nên kiểm tra JSON output và việc đọc lại bằng cùng hợp đồng. Ví dụ với JUnit 5:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JavaTimeJsonTest {
    private final ObjectMapper mapper = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    @Test
    void writesLocalDateAsIsoDate() throws Exception {
        String json = mapper.writeValueAsString(LocalDate.of(2026, 11, 12));
        assertEquals("\"2026-11-12\"", json);
    }

    @Test
    void writesLocalTimeAsIsoTime() throws Exception {
        String json = mapper.writeValueAsString(LocalTime.of(14, 30));
        assertEquals("\"14:30:00\"", json);
    }

    @Test
    void writesLocalDateTimeWithoutInventingZone() throws Exception {
        LocalDateTime value = LocalDateTime.of(2026, 11, 12, 14, 30);
        String json = mapper.writeValueAsString(value);

        assertEquals("\"2026-11-12T14:30:00\"", json);
        assertEquals(value, mapper.readValue(json, LocalDateTime.class));
    }
}
```

Các test trên giả định formatter ISO mặc định của Java Time module và cấu hình chuỗi như đã nêu. Nếu API dùng pattern riêng, hãy kiểm tra chính xác chuỗi mong đợi. Ngoài round-trip, nên có test cho null, giá trị thiếu, phần giây thập phân và input có offset để bảo đảm ứng dụng không âm thầm bỏ thông tin.

## 16. Quy tắc chọn kiểu và thiết kế JSON

| Nhu cầu nghiệp vụ | Kiểu Java nên cân nhắc | JSON thường dùng |
|---|---|---|
| Ngày sinh, ngày hóa đơn, ngày nghỉ | `LocalDate` | `"2026-11-12"` |
| Giờ mở cửa hoặc giờ lặp hằng ngày | `LocalTime` | `"08:30:00"` |
| Ngày giờ địa phương chưa gắn zone | `LocalDateTime` | `"2026-11-12T14:30:00"` |
| Thời điểm sự kiện tuyệt đối | `Instant` | `"2026-11-12T07:30:00Z"` |
| Ngày giờ kèm offset đã biết | `OffsetDateTime` | `"2026-11-12T14:30:00+07:00"` |
| Lịch gắn với quy tắc vùng | `ZonedDateTime` và zone ID | Ngày giờ cùng zone/offset theo hợp đồng |

Khi thiết kế API, nên quy định rõ:

- Chuỗi ngày/giờ dùng định dạng ISO hay pattern riêng.
- Có cho phép phần giây thập phân không và độ chính xác tối đa là bao nhiêu.
- Giá trị là ngày địa phương, giờ địa phương hay một instant.
- Nếu là lịch địa phương, zone ID được lấy từ đâu và xử lý DST thế nào.
- Nếu client gửi offset, server có giữ lại offset hay chuẩn hóa thành UTC.

Không nên dùng một kiểu Java chỉ vì nó deserialize được chuỗi JSON. Hãy chọn kiểu phản ánh đúng dữ liệu nghiệp vụ để tránh làm mất thông tin hoặc tạo ra một thời điểm không có trong dữ liệu gốc.

## 17. Kết luận

`LocalDate`, `LocalTime` và `LocalDateTime` lần lượt biểu diễn ngày, giờ và ngày giờ địa phương; cả ba đều không chứa múi giờ hoặc UTC offset. Với Jackson 2.x, đăng ký `JavaTimeModule` để xử lý chúng và tắt `WRITE_DATES_AS_TIMESTAMPS` nếu API yêu cầu chuỗi ISO. Dùng `@JsonFormat` khi hợp đồng cần pattern riêng, nhưng không coi pattern là cách bổ sung zone cho một kiểu local. Nếu cần xác định một instant, hãy kết hợp local date-time với `ZoneId` đã biết hoặc dùng `Instant`/`OffsetDateTime`/`ZonedDateTime` ngay từ đầu.
