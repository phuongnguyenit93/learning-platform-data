# Cấu hình mẫu, locale và múi giờ bằng JsonFormat

Ngày giờ là một trong những loại dữ liệu dễ gây sai lệch khi trao đổi giữa các hệ thống. Cùng một thời điểm có thể được hiển thị theo nhiều múi giờ; tên tháng và ngày trong tuần phụ thuộc locale; chuỗi ngày giờ có thể dùng nhiều mẫu định dạng khác nhau. Nếu hai phía không thống nhất các quy tắc này, dữ liệu có thể đọc được về cú pháp nhưng mang ý nghĩa khác nhau.

Jackson cung cấp annotation @JsonFormat để mô tả cách một thuộc tính hoặc kiểu Java được biểu diễn trong JSON. Annotation này có thể khai báo mẫu định dạng (pattern), locale, timezone và hình dạng JSON (shape). Với các kiểu ngày giờ, @JsonFormat giúp quy định chuỗi đầu vào cần được phân tích như thế nào và giá trị Java được ghi ra JSON theo định dạng nào.

Ba thuộc tính pattern, locale và timezone giải quyết ba vấn đề khác nhau:

- **pattern** quy định cấu trúc văn bản, chẳng hạn ngày/tháng/năm hay năm-tháng-ngày.
- **locale** quy định ngôn ngữ và quy ước văn hóa dùng cho tên tháng, ngày trong tuần, AM/PM và một số ký hiệu định dạng.
- **timezone** quy định múi giờ dùng khi diễn giải hoặc hiển thị thời điểm có thông tin thời gian.

Không nên xem ba thuộc tính này là một thiết lập duy nhất. Pattern đúng nhưng locale sai có thể làm tên tháng không được phân tích; timezone đúng nhưng kiểu Java không biểu diễn múi giờ thì không thể tự tạo ra một thời điểm tuyệt đối.

## 1. Vai trò của @JsonFormat

@JsonFormat thuộc gói com.fasterxml.jackson.annotation. Nó cho Jackson metadata bổ sung về cách serialize và deserialize một thuộc tính hoặc kiểu dữ liệu.

Ví dụ, API yêu cầu ngày sinh được truyền dưới dạng ngày/tháng/năm:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

public class PersonRequest {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/uuuu"
    )
    private LocalDate birthday;

    public LocalDate getBirthday() {
        return birthday;
    }

    public void setBirthday(LocalDate birthday) {
        this.birthday = birthday;
    }
}
~~~

JSON:

~~~json
{
  "birthday": "17/06/1998"
}
~~~

Khi đọc, Jackson dùng mẫu dd/MM/uuuu để tạo LocalDate. Khi ghi, Jackson dùng cùng mẫu để xuất ngày thành chuỗi tương ứng.

Annotation có thể được đặt trên field, getter, setter, tham số creator hoặc ở cấp lớp tùy trường hợp. Đặt trực tiếp trên thuộc tính thường dễ thấy phạm vi áp dụng nhất, đặc biệt khi các trường ngày giờ trong cùng một DTO có định dạng khác nhau.

## 2. Các thuộc tính chính của JsonFormat

Các thuộc tính thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| pattern | Mẫu định dạng dùng để đọc hoặc ghi giá trị |
| locale | Locale dùng khi phân tích hoặc tạo các thành phần văn bản theo ngôn ngữ |
| timezone | Múi giờ dùng cho kiểu dữ liệu có ngữ nghĩa thời điểm |
| shape | Hình dạng JSON, ví dụ STRING, NUMBER hoặc cấu trúc khác mà kiểu hỗ trợ |
| with | Bật một hoặc nhiều JsonFormat.Feature |
| without | Tắt một hoặc nhiều JsonFormat.Feature |
| lenient | Điều khiển mức độ linh hoạt khi phân tích dữ liệu ở các deserializer hỗ trợ |

Với bài toán ngày giờ, pattern, locale, timezone và shape là những thuộc tính quan trọng nhất. Các feature bổ sung chỉ nên bật khi hợp đồng dữ liệu cần hành vi tương ứng và kiểu serializer/deserializer hỗ trợ chúng.

Ví dụ cấu hình đầy đủ:

~~~java
@JsonFormat(
    shape = JsonFormat.Shape.STRING,
    pattern = "dd MMMM uuuu",
    locale = "vi-VN",
    timezone = "Asia/Ho_Chi_Minh"
)
private Date displayDate;
~~~

Ví dụ này mô tả ngày theo chuỗi có tên tháng theo locale Việt Nam và timezone Việt Nam. Tác dụng cụ thể của timezone còn phụ thuộc kiểu Java: Date biểu diễn một thời điểm tuyệt đối, còn LocalDate chỉ biểu diễn ngày lịch.

## 3. Pattern là gì?

Pattern là chuỗi ký hiệu chỉ ra vị trí và cách hiển thị từng thành phần ngày giờ. Ký hiệu pattern phụ thuộc API định dạng mà Jackson sử dụng cho kiểu Java đích.

Đây là điểm cần chú ý:

- Với kiểu ngày giờ cũ như java.util.Date, Jackson thường dùng DateFormat, phổ biến là SimpleDateFormat. Pattern tuân theo quy tắc SimpleDateFormat.
- Với các kiểu java.time như LocalDate, LocalDateTime, Instant và OffsetDateTime khi dùng JavaTimeModule, pattern được xử lý theo quy tắc DateTimeFormatter.

Hai hệ pattern có nhiều ký hiệu giống nhau nhưng không hoàn toàn tương đương. Không nên sao chép pattern từ SimpleDateFormat sang DateTimeFormatter mà không kiểm tra ý nghĩa từng ký hiệu.

### Các ký hiệu thường gặp trong DateTimeFormatter

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| uuuu | Năm theo lịch (proleptic year) | 2026 |
| yyyy | Năm trong kỷ nguyên | 2026 |
| MM | Tháng dạng số có hai chữ số | 06 |
| MMM | Tên tháng dạng rút gọn theo locale | Jun |
| MMMM | Tên tháng đầy đủ theo locale | June |
| dd | Ngày trong tháng | 17 |
| EEE | Tên ngày trong tuần dạng rút gọn | Wed |
| EEEE | Tên ngày trong tuần đầy đủ | Wednesday |
| HH | Giờ theo hệ 24 giờ | 16 |
| hh | Giờ theo hệ 12 giờ | 04 |
| mm | Phút | 32 |
| ss | Giây | 08 |
| SSS | Phần mili giây | 125 |
| XXX | Offset UTC dạng ISO | +07:00 |
| VV | Mã vùng timezone | Asia/Ho_Chi_Minh |
| a | Ký hiệu AM/PM theo locale | PM |

Chữ hoa và chữ thường có ý nghĩa khác nhau. MM là tháng, mm là phút. HH là giờ 00–23, còn hh là giờ 01–12. Nhầm các ký hiệu này có thể khiến dữ liệu được ghi ra có vẻ hợp lệ nhưng mang giá trị sai.

Ký tự cố định cần được đặt trong dấu nháy đơn. Ví dụ:

~~~java
@JsonFormat(pattern = "uuuu-MM-dd'T'HH:mm:ssXXX")
private OffsetDateTime createdAt;
~~~

Ký tự T trong chuỗi ISO-8601 là ký tự phân cách cố định, không phải trường dữ liệu. Dấu nháy đơn cho DateTimeFormatter biết đây là literal.

### Vì sao thường nên dùng uuuu cho java.time?

Trong DateTimeFormatter, yyyy biểu diễn year-of-era, còn uuuu biểu diễn proleptic year. Với dữ liệu ngày lịch thông thường trong kỷ nguyên hiện tại, hai mẫu thường cho kết quả giống nhau. Tuy nhiên, uuuu tránh một số tình huống phân tích strict mà year-of-era thiếu thông tin era.

Đối với java.util.Date và SimpleDateFormat, dùng yyyy để biểu diễn năm; ý nghĩa ký hiệu u trong SimpleDateFormat khác với DateTimeFormatter. Vì vậy, ví dụ pattern phải được chọn theo kiểu Java thực tế.

## 4. Định dạng LocalDate

LocalDate biểu diễn ngày lịch, không chứa giờ, offset hoặc timezone. Ví dụ ngày sinh, ngày phát hành hóa đơn hoặc ngày nghỉ thường phù hợp với LocalDate.

~~~java
public class EmployeeRequest {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/uuuu"
    )
    private LocalDate startDate;

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }
}
~~~

JSON:

~~~json
{
  "startDate": "05/01/2026"
}
~~~

LocalDate không đại diện cho một thời điểm trên dòng thời gian. Đặt timezone = "Asia/Ho_Chi_Minh" trên LocalDate không biến ngày đó thành một instant theo múi giờ Việt Nam. Nếu hợp đồng chỉ truyền ngày lịch, không cần thêm timezone.

Nếu một API truyền ngày theo dạng ISO chuẩn yyyy-MM-dd, có thể khai báo:

~~~java
@JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "uuuu-MM-dd")
private LocalDate dueDate;
~~~

Với các API công khai, định dạng ISO yyyy-MM-dd thường dễ trao đổi và ít phụ thuộc locale hơn định dạng có dấu phân cách hoặc tên tháng.

## 5. Định dạng LocalTime và LocalDateTime

LocalTime biểu diễn giờ trong ngày, không có ngày và timezone. LocalDateTime kết hợp ngày với giờ địa phương nhưng vẫn không xác định một thời điểm tuyệt đối.

Ví dụ LocalTime:

~~~java
public class OpeningHours {
    @JsonFormat(pattern = "HH:mm:ss", shape = JsonFormat.Shape.STRING)
    private LocalTime opensAt;

    @JsonFormat(pattern = "HH:mm:ss", shape = JsonFormat.Shape.STRING)
    private LocalTime closesAt;

    // Getter và setter
}
~~~

JSON:

~~~json
{
  "opensAt": "08:30:00",
  "closesAt": "17:45:00"
}
~~~

Ví dụ LocalDateTime:

~~~java
public class Appointment {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/uuuu HH:mm:ss"
    )
    private LocalDateTime scheduledAt;

    // Getter và setter
}
~~~

JSON:

~~~json
{
  "scheduledAt": "17/06/2026 09:30:00"
}
~~~

LocalDateTime không chứa offset hoặc vùng timezone. Chuỗi 09:30 có thể là 09:30 tại Hà Nội, Paris hoặc một địa điểm khác. Nếu thông điệp cần xác định một thời điểm tuyệt đối, hãy dùng Instant hoặc OffsetDateTime và đưa offset/timezone vào hợp đồng.

Không nên dùng timezone trong @JsonFormat như cách gắn múi giờ vào LocalDateTime. Khi cần chuyển LocalDateTime sang thời điểm thực, ứng dụng phải biết vùng thời gian nghiệp vụ và thực hiện chuyển đổi rõ ràng bằng ZoneId.

## 6. Định dạng Instant và OffsetDateTime

Instant biểu diễn một thời điểm trên dòng thời gian UTC. OffsetDateTime biểu diễn ngày giờ cùng offset UTC, chẳng hạn +07:00.

Với Instant, có thể định dạng theo chuỗi ISO có offset:

~~~java
public record AuditEvent(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX",
        timezone = "UTC"
    )
    Instant occurredAt
) {}
~~~

JSON có thể là:

~~~json
{
  "occurredAt": "2026-11-12T09:32:00Z"
}
~~~

Instant không lưu timezone gốc của người gửi; nó chỉ lưu thời điểm tuyệt đối. Khi hiển thị cùng Instant theo một timezone khác, phần giờ và offset thay đổi nhưng thời điểm không đổi.

Với OffsetDateTime:

~~~java
public record Meeting(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime startsAt
) {}
~~~

JSON:

~~~json
{
  "startsAt": "2026-11-12T16:30:00+07:00"
}
~~~

OffsetDateTime giữ offset cụ thể trong giá trị Java. Tuy nhiên, cấu hình Jackson có thể điều chỉnh giá trị ngày giờ theo timezone context khi deserialize. Nếu ứng dụng cần giữ offset từ JSON, cần kiểm tra DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE và cấu hình phù hợp cho phiên bản Jackson đang dùng.

Ví dụ tắt điều chỉnh theo timezone context ở mapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
    .build();
~~~

Khi tắt tính năng này, Jackson không điều chỉnh các giá trị hỗ trợ theo timezone context trong quá trình đọc. Hãy kiểm tra riêng với kiểu dữ liệu và phiên bản Jackson của dự án; Instant vẫn luôn biểu diễn cùng một thời điểm, còn offset chỉ có ý nghĩa với kiểu lưu giữ offset như OffsetDateTime.

## 7. Múi giờ trong JsonFormat

Thuộc tính timezone nhận tên timezone hoặc mã phù hợp với Java TimeZone. Nên dùng tên vùng theo cơ sở dữ liệu timezone IANA:

- UTC
- Asia/Ho_Chi_Minh
- Asia/Tokyo
- Europe/Paris
- America/New_York

Ví dụ:

~~~java
public class LegacyEvent {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/uuuu HH:mm:ss",
        timezone = "Asia/Ho_Chi_Minh"
    )
    private Date happenedAt;

    // Getter và setter
}
~~~

Với java.util.Date, giá trị là một instant. Khi ghi, Jackson chuyển instant sang giờ địa phương theo timezone rồi định dạng chuỗi. Khi đọc, chuỗi ngày giờ được diễn giải theo timezone đã khai báo để tạo lại instant.

Ví dụ, cùng một instant có thể hiển thị:

| Timezone | Chuỗi giờ địa phương |
|---|---|
| UTC | 2026-11-12 09:00:00 |
| Asia/Ho_Chi_Minh | 2026-11-12 16:00:00 |
| Asia/Tokyo | 2026-11-12 18:00:00 |

Các chuỗi khác nhau nhưng biểu diễn cùng một thời điểm. Nếu bỏ timezone khỏi hợp đồng và chỉ truyền chuỗi giờ địa phương, bên nhận có thể hiểu sai instant.

Không nên dùng các chữ viết tắt mơ hồ như CST, IST hoặc PST khi có thể dùng tên vùng đầy đủ. Một chữ viết tắt có thể đại diện cho nhiều vùng hoặc nhiều offset khác nhau. Tên vùng IANA thể hiện quy tắc lịch sử và quy tắc DST của địa điểm.

## 8. Timezone mặc định của ObjectMapper và timezone trong JsonFormat

Nếu annotation không chỉ định timezone, Jackson có thể dùng timezone mặc định trong cấu hình mapper hoặc ngữ cảnh. Có thể thiết lập timezone mặc định khi tạo mapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();

mapper.setTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
~~~

Với các kiểu cũ như Date, timezone mặc định của mapper ảnh hưởng đến cách diễn giải/hiển thị khi không có timezone cụ thể hơn. Với java.time, hành vi còn phụ thuộc loại temporal và serializer/deserializer.

Khi thuộc tính có @JsonFormat(timezone = "UTC"), cấu hình tại thuộc tính mô tả timezone riêng cho thuộc tính đó. Nó có thể khác timezone mặc định của mapper.

Nên tổ chức chính sách như sau:

- Đặt timezone mặc định của mapper theo quy ước chung của ứng dụng nếu thật sự cần.
- Dùng timezone trong @JsonFormat khi một trường có hợp đồng khác biệt.
- Với thời điểm trao đổi giữa các hệ thống, ưu tiên Instant hoặc OffsetDateTime và biểu diễn rõ UTC/offset.
- Không dựa vào timezone mặc định của máy chạy ứng dụng, vì môi trường phát triển, máy chủ và container có thể khác nhau.

## 9. Locale trong JsonFormat

Locale quy định ngôn ngữ và quy ước định dạng văn bản. Nó đặc biệt quan trọng khi pattern chứa tên tháng hoặc tên ngày trong tuần.

Ví dụ:

~~~java
public class ReportRequest {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd MMMM uuuu",
        locale = "vi-VN"
    )
    private LocalDate reportDate;

    // Getter và setter
}
~~~

Với locale Việt Nam, tên tháng được định dạng theo quy tắc ngôn ngữ Việt Nam mà provider locale của JDK hỗ trợ. Nếu dùng locale en-US, cùng pattern có thể tạo tên tháng tiếng Anh.

Ví dụ khai báo locale tiếng Anh:

~~~java
@JsonFormat(
    pattern = "dd MMMM uuuu",
    locale = "en-US",
    shape = JsonFormat.Shape.STRING
)
private LocalDate reportDate;
~~~

Locale không phải timezone. Thay locale không làm thay đổi instant hoặc offset. Nó chỉ thay đổi cách thể hiện những thành phần có tính ngôn ngữ/văn hóa.

Đối với hợp đồng API cần ổn định giữa nhiều môi trường, nên ưu tiên định dạng số ISO như uuuu-MM-dd. Nếu bắt buộc dùng tên tháng, hãy khai báo locale rõ ràng thay vì dựa vào locale mặc định của máy.

## 10. Pattern có tên tháng và ngày trong tuần

Khi dùng MMM hoặc MMMM, Jackson cần locale phù hợp để phân tích hoặc tạo tên tháng:

~~~java
public class LocalizedDate {
    @JsonFormat(
        pattern = "EEEE, dd MMMM uuuu",
        locale = "vi-VN",
        shape = JsonFormat.Shape.STRING
    )
    private LocalDate date;

    // Getter và setter
}
~~~

Pattern có:

- EEEE: tên ngày trong tuần đầy đủ.
- dd: ngày trong tháng.
- MMMM: tên tháng đầy đủ.
- uuuu: năm.

Nếu locale là en-US, kết quả sẽ dùng tên ngày/tháng theo tiếng Anh. Nếu locale là vi-VN, kết quả dùng dữ liệu locale tiếng Việt của JDK.

Locale được hỗ trợ và cách viết tên tháng có thể phụ thuộc phiên bản JDK và locale data provider. Vì vậy, nếu chuỗi văn bản là hợp đồng trao đổi với đối tác, nên có fixture kiểm tra output trên môi trường triển khai.

## 11. Kết hợp pattern, locale và timezone

Ba thuộc tính có thể được dùng cùng lúc:

~~~java
public class LegacyReport {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "EEEE, dd MMMM uuuu HH:mm:ss",
        locale = "vi-VN",
        timezone = "Asia/Ho_Chi_Minh"
    )
    private Date generatedAt;

    // Getter và setter
}
~~~

Với Date, Jackson có một instant và có thể chuyển instant đó sang giờ Việt Nam trước khi định dạng. Locale Việt Nam điều khiển tên thứ/tháng. Pattern quyết định thứ tự và cách hiển thị các thành phần.

JSON minh họa:

~~~json
{
  "generatedAt": "Thứ Năm, 12 tháng 11 2026 16:30:00"
}
~~~

Chuỗi thực tế có thể phụ thuộc locale data của JDK. Đừng dựa vào ví dụ minh họa để giả định chính xác dấu câu hoặc cách viết tên tháng; hãy kiểm tra output trên runtime thực tế.

Với LocalDateTime, timezone không thể tự chuyển đổi một instant vì kiểu này không có timezone. Locale và pattern vẫn có thể dùng cho định dạng, nhưng cần tránh hiểu rằng chỉ thêm timezone vào annotation là đã xác định được thời điểm toàn cầu.

## 12. Shape điều khiển hình dạng JSON

JsonFormat.Shape mô tả hình dạng JSON mong muốn. Một số giá trị:

| Shape | Ý nghĩa |
|---|---|
| ANY | Để Jackson chọn hình dạng mặc định |
| NATURAL | Dùng biểu diễn tự nhiên của kiểu nếu được hỗ trợ |
| SCALAR | Biểu diễn dạng scalar |
| STRING | Biểu diễn dưới dạng JSON string |
| NUMBER | Biểu diễn dưới dạng JSON number |
| NUMBER_INT | Biểu diễn dưới dạng số nguyên |
| NUMBER_FLOAT | Biểu diễn dưới dạng số thực |
| ARRAY | Biểu diễn dưới dạng JSON array nếu kiểu hỗ trợ |
| OBJECT | Biểu diễn dưới dạng JSON object nếu kiểu hỗ trợ |

Với các trường ngày giờ trao đổi qua API, STRING thường dễ đọc và ít phụ thuộc cấu hình timestamp hơn:

~~~java
@JsonFormat(
    shape = JsonFormat.Shape.STRING,
    pattern = "uuuu-MM-dd"
)
private LocalDate date;
~~~

Nếu dùng NUMBER cho ngày giờ, hợp đồng phải xác định đơn vị timestamp và mốc thời gian. Một số cấu hình Jackson dùng milliseconds, một số kiểu java.time có thể dùng giây và phần nano tùy feature. Không nên dùng NUMBER chỉ vì nó ngắn hơn.

Shape không thay thế pattern. Pattern định dạng nội dung chuỗi; shape xác định JSON chứa chuỗi, số hay hình dạng khác.

## 13. Định dạng java.util.Date và SimpleDateFormat

Các hệ thống cũ có thể đang sử dụng java.util.Date hoặc Calendar. Jackson xử lý các kiểu này theo DateFormat, thường là SimpleDateFormat khi dùng pattern.

Ví dụ:

~~~java
public class LegacyInvoice {
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd HH:mm:ss",
        timezone = "Asia/Ho_Chi_Minh",
        locale = "vi-VN"
    )
    private Date issuedAt;

    // Getter và setter
}
~~~

Pattern SimpleDateFormat thường dùng:

| Ký hiệu | Ý nghĩa |
|---|---|
| yyyy | Năm |
| MM | Tháng |
| dd | Ngày |
| HH | Giờ 00–23 |
| hh | Giờ 01–12 |
| mm | Phút |
| ss | Giây |
| SSS | Mili giây |
| XXX | Offset ISO 8601 |
| z | Tên hoặc dạng viết tắt timezone theo formatter |

Như với DateTimeFormatter, MM là tháng và mm là phút. Pattern SimpleDateFormat không hoàn toàn giống DateTimeFormatter; ví dụ ký hiệu u trong SimpleDateFormat biểu diễn day number of week, không phải proleptic year.

Với hệ thống mới, nếu mô hình phù hợp, nên cân nhắc java.time. Các kiểu như Instant, LocalDate, LocalDateTime và OffsetDateTime diễn tả ý nghĩa ngày giờ rõ ràng hơn Date vốn chỉ lưu một số mili giây từ epoch.

## 14. Đăng ký JavaTimeModule

Các kiểu java.time cần module hỗ trợ trong Jackson Databind. Có thể đăng ký JavaTimeModule:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Tắt WRITE_DATES_AS_TIMESTAMPS thường hướng các kiểu ngày giờ Java Time đến biểu diễn chuỗi thay vì timestamp hoặc cấu trúc số/array mặc định. Nếu một thuộc tính có @JsonFormat(shape = STRING), annotation thể hiện rõ yêu cầu chuỗi cho thuộc tính đó.

Đảm bảo dependency jackson-datatype-jsr310 cùng phiên bản với Jackson Databind đang dùng. Không nên trộn các phiên bản khác nhau của các module Jackson trong cùng ứng dụng.

Ví dụ model:

~~~java
public record Booking(
    @JsonFormat(pattern = "dd/MM/uuuu")
    LocalDate date,

    @JsonFormat(pattern = "HH:mm")
    LocalTime time,

    @JsonFormat(
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX",
        timezone = "UTC"
    )
    Instant createdAt
) {}
~~~

Ba thuộc tính có ba ngữ nghĩa riêng: ngày lịch, giờ địa phương và thời điểm tuyệt đối. Định dạng cũng được chỉ định riêng theo từng kiểu.

## 15. Cấu hình toàn cục và cấu hình tại thuộc tính

@JsonFormat thường được dùng khi một thuộc tính cần định dạng riêng. Nếu toàn bộ ứng dụng có quy ước chung, có thể cấu hình ở cấp ObjectMapper.

Ví dụ với Date:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.setTimeZone(TimeZone.getTimeZone("UTC"));
mapper.setDateFormat(
    new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.ROOT)
);
~~~

Đối với java.time, đăng ký JavaTimeModule và cấu hình các feature liên quan:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Khi thuộc tính có @JsonFormat, metadata tại thuộc tính có thể cung cấp pattern, locale hoặc timezone cụ thể hơn cấu hình mặc định. Hành vi chính xác còn phụ thuộc serializer/deserializer của kiểu đó và phiên bản Jackson.

Nên dùng cấu hình toàn cục cho quy ước chung, còn @JsonFormat cho ngoại lệ rõ ràng theo thuộc tính. Không nên đặt một pattern toàn cục nếu các API khác nhau có hợp đồng ngày giờ khác nhau.

## 16. Locale mặc định của mapper

Jackson có thể dùng locale mặc định trong cấu hình mapper khi annotation không chỉ định locale. Có thể đặt locale của mapper:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.setLocale(Locale.forLanguageTag("vi-VN"));
~~~

Locale này là mặc định cho các thao tác cần locale trong mapper. Một thuộc tính có @JsonFormat(locale = "en-US") có thể chỉ định locale riêng cho trường đó.

Không nên dựa vào Locale.getDefault() của máy chủ nếu hợp đồng cần ổn định. Locale mặc định có thể khác giữa máy phát triển, máy CI, container hoặc server. Hãy khai báo locale trong annotation hoặc cấu hình mapper.

## 17. Múi giờ mặc định của mapper

Có thể đặt timezone mặc định bằng setTimeZone:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.setTimeZone(TimeZone.getTimeZone("UTC"));
~~~

Với kiểu Date, timezone mặc định ảnh hưởng đến cách Jackson định dạng hoặc diễn giải ngày giờ khi thuộc tính không khai báo timezone riêng.

Nếu muốn sử dụng múi giờ Việt Nam:

~~~java
mapper.setTimeZone(
    TimeZone.getTimeZone("Asia/Ho_Chi_Minh")
);
~~~

Trong ứng dụng phân tán, UTC thường là lựa chọn thuận tiện cho việc lưu trữ và trao đổi thời điểm. Ở tầng hiển thị, ứng dụng có thể chuyển instant sang timezone người dùng. Nếu hợp đồng API quy định offset hoặc timezone khác, hãy biểu diễn rõ trong JSON.

Không nên thay timezone mặc định của mapper theo từng request. ObjectMapper nên được cấu hình hoàn chỉnh trước khi chia sẻ giữa nhiều luồng. Nếu cần chính sách riêng theo thao tác, dùng mapper riêng hoặc cấu hình đọc/ghi phù hợp mà không thay đổi mapper dùng chung trong lúc xử lý.

## 18. Múi giờ và ngữ nghĩa của từng kiểu Java

Không phải mọi kiểu ngày giờ đều sử dụng timezone theo cùng cách:

| Kiểu Java | Có chứa timezone/offset? | Ý nghĩa |
|---|---|---|
| LocalDate | Không | Ngày lịch |
| LocalTime | Không | Giờ địa phương |
| LocalDateTime | Không | Ngày và giờ địa phương |
| OffsetTime | Có offset | Giờ trong ngày kèm offset |
| OffsetDateTime | Có offset | Ngày giờ kèm offset |
| ZonedDateTime | Có ZoneId | Ngày giờ trong vùng timezone |
| Instant | Không lưu timezone, biểu diễn thời điểm UTC | Một điểm tuyệt đối trên timeline |
| java.util.Date | Không lưu timezone, biểu diễn thời điểm | Một instant theo epoch milliseconds |

Timezone có ý nghĩa trực tiếp khi chuyển một instant thành giờ địa phương hoặc diễn giải giờ địa phương thành instant. Với LocalDate và LocalTime, không tồn tại thông tin đủ để làm phép chuyển đổi đó.

Ví dụ, 2026-11-12T09:00:00Z và 2026-11-12T16:00:00+07:00 là cùng một thời điểm. Nhưng LocalDateTime 2026-11-12T16:00:00 tự nó không cho biết đó là giờ ở đâu.

## 19. Daylight Saving Time và giờ địa phương mơ hồ

Một số vùng timezone có quy tắc daylight saving time (DST). Khi đồng hồ chuyển sang giờ mùa hè, có thể xuất hiện:

- Khoảng thời gian địa phương không tồn tại khi đồng hồ nhảy về phía trước.
- Một khoảng thời gian địa phương xuất hiện hai lần khi đồng hồ lùi về phía sau.

LocalDateTime không lưu ZoneId hoặc offset nên không thể tự phân biệt các trường hợp này. Khi xử lý lịch hẹn tại một địa điểm có DST, nên kết hợp LocalDateTime với ZoneId và xác định quy tắc xử lý giờ không tồn tại hoặc bị lặp.

Ví dụ Java:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Paris");

List<ZoneOffset> validOffsets = zone.getRules().getValidOffsets(local);
~~~

Danh sách offset hợp lệ có thể có:

- Không có phần tử: giờ địa phương không tồn tại do DST.
- Một phần tử: giờ địa phương xác định một offset.
- Hai phần tử: giờ địa phương xuất hiện hai lần khi chuyển DST.

Khi hợp đồng cần xác định một thời điểm chính xác, truyền Instant hoặc OffsetDateTime thường rõ ràng hơn chỉ truyền LocalDateTime. Nếu nghiệp vụ cần lịch địa phương, hãy truyền thêm timezone ID như Europe/Paris.

## 20. Phân biệt timezone và offset

Offset là chênh lệch cố định so với UTC tại một thời điểm, ví dụ +07:00. ZoneId là định danh vùng thời gian có bộ quy tắc lịch sử và có thể thay đổi theo thời điểm, ví dụ Europe/Paris.

| Giá trị | Loại | Đặc điểm |
|---|---|---|
| +07:00 | Offset | Chỉ biểu diễn độ lệch UTC |
| Z | Offset UTC | Offset bằng 0 |
| Asia/Ho_Chi_Minh | ZoneId | Quy tắc timezone của một vùng |
| Europe/Paris | ZoneId | Quy tắc timezone có thể thay đổi theo lịch DST |

OffsetDateTime giữ offset nhưng không giữ toàn bộ danh tính vùng. ZonedDateTime giữ ZoneId. Nếu ứng dụng cần tái hiện quy tắc lịch sử của địa điểm, ZoneId quan trọng hơn offset đơn lẻ.

Trong JSON, pattern XXX có thể ghi offset. Pattern VV có thể ghi ZoneId với DateTimeFormatter. Không phải serializer nào cũng hỗ trợ mọi pattern giống nhau; hãy kiểm tra kiểu temporal cụ thể.

## 21. Ảnh hưởng của ADJUST_DATES_TO_CONTEXT_TIME_ZONE

DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE điều khiển việc một số kiểu ngày giờ có timezone/offset được điều chỉnh theo timezone của context khi đọc.

Điều này đáng chú ý với OffsetDateTime và ZonedDateTime. Nếu ứng dụng muốn giữ offset hoặc zone nhận từ JSON, cần kiểm tra feature này và chính sách timezone mặc định của mapper.

Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
    .build();
~~~

Nếu ứng dụng muốn chuẩn hóa tất cả thời điểm về UTC, có thể chủ động chuyển đổi sang Instant trong tầng nghiệp vụ. Không nên vô tình làm mất offset chỉ vì mapper có timezone mặc định khác với offset trong JSON.

Feature này không làm cho LocalDateTime tự có timezone. Nó chỉ có ý nghĩa với các kiểu và deserializer có hỗ trợ việc điều chỉnh context timezone.

## 22. Một thuộc tính đọc và ghi theo mẫu khác nhau

@JsonFormat thường mô tả cùng một định dạng cho cả hai chiều. Nếu hợp đồng yêu cầu mẫu đọc và ghi khác nhau, có thể dùng custom serializer/deserializer hoặc tách DTO đầu vào và đầu ra.

Ví dụ API chấp nhận ngày dạng dd/MM/uuuu nhưng luôn trả về ISO uuuu-MM-dd. Có thể tạo hai DTO:

~~~java
public record DateRequest(
    @JsonFormat(pattern = "dd/MM/uuuu")
    LocalDate date
) {}

public record DateResponse(
    @JsonFormat(pattern = "uuuu-MM-dd")
    LocalDate date
) {}
~~~

Cách này làm rõ hợp đồng riêng của request và response. Nếu dùng cùng một kiểu cho cả hai chiều và cần parser/serializer khác nhau, custom serializer và deserializer có thể cung cấp hành vi riêng:

~~~java
@JsonDeserialize(using = CustomDateDeserializer.class)
@JsonSerialize(using = CustomDateSerializer.class)
private LocalDate date;
~~~

Custom deserializer chịu trách nhiệm phân tích input; custom serializer chịu trách nhiệm ghi output. Khi dùng custom handler, không nên giả định mọi metadata @JsonFormat sẽ tự động được áp dụng giống serializer mặc định; handler cần đọc hoặc triển khai cấu hình mong muốn.

## 23. JsonFormat với enum có giá trị văn bản phụ thuộc locale

JsonFormat không chỉ dành cho ngày giờ. Nó còn có thể điều chỉnh cách một số kiểu khác được biểu diễn, tùy serializer. Với enum, shape có thể ảnh hưởng đến việc biểu diễn như chuỗi hoặc số trong những trường hợp được hỗ trợ.

Tuy nhiên, không nên dùng locale để dịch mã enum trao đổi một cách ngầm định. Mã enum trong API nên ổn định, ví dụ PENDING, PAID hoặc CANCELLED, hoặc một wire value rõ ràng được định nghĩa bằng @JsonValue/@JsonCreator.

Locale phù hợp với cách hiển thị cho người dùng. Wire value phù hợp với giao tiếp giữa các hệ thống. Trộn hai mục đích có thể làm cùng một trạng thái có nhiều cách viết theo ngôn ngữ và phá vỡ khả năng tương thích.

## 24. Những lỗi thường gặp khi cấu hình JsonFormat

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Parse ngày thất bại | Pattern không khớp chuỗi đầu vào | So sánh chính xác mẫu và JSON thực tế |
| Tháng và phút bị đảo | Dùng mm thay cho MM hoặc ngược lại | MM là tháng, mm là phút |
| Giờ bị lệch nhiều giờ | Timezone mặc định hoặc timezone annotation không đúng | Dùng timezone ID rõ ràng và kiểm tra kiểu Java |
| LocalDateTime bị hiểu như instant | Dùng kiểu không chứa timezone cho dữ liệu cần thời điểm tuyệt đối | Dùng Instant hoặc OffsetDateTime |
| Tên tháng không đúng ngôn ngữ | Locale mặc định khác mong đợi | Khai báo locale rõ ràng |
| Offset đầu vào bị thay đổi | Mapper điều chỉnh theo context timezone | Kiểm tra ADJUST_DATES_TO_CONTEXT_TIME_ZONE |
| Ngày được ghi thành số | Shape hoặc feature timestamp | Dùng Shape.STRING và cấu hình module phù hợp |
| Pattern hoạt động với Date nhưng lỗi với LocalDate | Khác biệt giữa SimpleDateFormat và DateTimeFormatter | Chọn pattern đúng API định dạng |
| Môi trường CI ghi tên tháng khác máy cá nhân | Locale data/JDK khác nhau | Cố định locale và kiểm tra trên runtime triển khai |
| Thời điểm bị hiểu khác nhau giữa hai hệ thống | Chuỗi thiếu offset/timezone | Đưa UTC/offset hoặc ZoneId vào hợp đồng |

## 25. Ví dụ tổng hợp với nhiều kiểu ngày giờ

Một DTO có thể chứa nhiều loại ngày giờ với ý nghĩa khác nhau:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;

public record ScheduleResponse(

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/uuuu"
    )
    LocalDate serviceDate,

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "HH:mm"
    )
    LocalTime localStartTime,

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/uuuu HH:mm:ss"
    )
    LocalDateTime localScheduledAt,

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime confirmedAt,

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX",
        timezone = "UTC"
    )
    Instant createdAt
) {}
~~~

Cấu hình mapper:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
    .build();
~~~

JSON minh họa:

~~~json
{
  "serviceDate": "12/11/2026",
  "localStartTime": "08:30",
  "localScheduledAt": "12/11/2026 08:30:00",
  "confirmedAt": "2026-11-12T08:30:00+07:00",
  "createdAt": "2026-11-12T01:30:00Z"
}
~~~

Ý nghĩa:

- serviceDate là ngày lịch, không có timezone.
- localStartTime là giờ địa phương, không có ngày hoặc timezone.
- localScheduledAt là ngày giờ địa phương; nếu cần xác định instant, hợp đồng phải cung cấp thêm vùng thời gian.
- confirmedAt là thời điểm kèm offset +07:00.
- createdAt là instant được biểu diễn theo UTC.

Đặt tên thuộc tính và chọn kiểu Java đúng ngữ nghĩa quan trọng hơn việc chỉ chọn pattern. Pattern giúp biểu diễn giá trị; kiểu Java cho biết dữ liệu đó là ngày lịch, giờ địa phương hay một thời điểm tuyệt đối.

## 26. Kiểm tra serialize và deserialize

Khi thêm @JsonFormat, nên kiểm tra cả hai chiều. Ví dụ:

~~~java
class DateFormatTest {

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

    @Test
    void readsAndWritesLocalDateWithExpectedPattern() throws Exception {
        DateRequest request = mapper.readValue(
            "{\"date\":\"17/06/2026\"}",
            DateRequest.class
        );

        assertEquals(
            LocalDate.of(2026, 6, 17),
            request.date()
        );

        String json = mapper.writeValueAsString(request);
        JsonNode node = mapper.readTree(json);
        assertEquals("17/06/2026", node.get("date").asText());
    }
}
~~~

Với timezone, nên kiểm tra giá trị instant thay vì chỉ so sánh chuỗi:

~~~java
Instant expected = Instant.parse("2026-11-12T09:00:00Z");
Date value = new Date(expected.toEpochMilli());

String json = mapper.writeValueAsString(new LegacyEvent(value));
LegacyEvent restored = mapper.readValue(json, LegacyEvent.class);

assertEquals(value.toInstant(), restored.getHappenedAt().toInstant());
~~~

Ví dụ kiểm tra này giả định LegacyEvent dùng Date và @JsonFormat pattern/timezone như các phần trước. Nếu pattern chỉ có giờ địa phương và không có offset, timezone trong annotation là thành phần quan trọng để đọc lại cùng instant.

Nên có các test cho:

- Ngày hợp lệ và ngày không tồn tại như 31/02.
- Năm nhuận.
- Chuỗi có tên tháng theo locale.
- Giờ có offset khác UTC.
- Offset bị giữ nguyên hoặc được chuẩn hóa theo chính sách đã chọn.
- Giá trị thiếu, null và chuỗi rỗng.
- Thời điểm nằm gần ranh giới DST ở vùng có DST.
- JSON được ghi ra và đọc lại trên phiên bản JDK/Jackson dùng khi triển khai.

## 27. Nguyên tắc thiết kế hợp đồng ngày giờ

Khi thiết kế trường ngày giờ cho API, nên quyết định theo thứ tự:

1. Xác định ý nghĩa: ngày lịch, giờ địa phương, ngày giờ địa phương hay thời điểm tuyệt đối.
2. Chọn kiểu Java phản ánh ý nghĩa: LocalDate, LocalTime, LocalDateTime, OffsetDateTime, ZonedDateTime hoặc Instant.
3. Chọn biểu diễn JSON: chuỗi ISO, mẫu riêng, offset hoặc timezone ID.
4. Chọn pattern phù hợp với formatter mà kiểu Java sử dụng.
5. Khai báo locale nếu pattern chứa tên tháng/ngày hoặc ký hiệu phụ thuộc ngôn ngữ.
6. Khai báo timezone nếu dữ liệu biểu diễn một thời điểm cần diễn giải/hiển thị theo vùng cụ thể.
7. Cấu hình JavaTimeModule và các feature toàn cục cần thiết.
8. Kiểm tra cả hai chiều và dùng dữ liệu mẫu từ hợp đồng thực tế.

Một số quy tắc thực hành:

- Ưu tiên ISO-8601 cho API giữa các hệ thống.
- Dùng UTC hoặc offset tường minh cho thời điểm tuyệt đối.
- Dùng LocalDate cho ngày lịch như sinh nhật, ngày hiệu lực hoặc ngày thanh toán.
- Không gắn timezone giả tạo cho LocalDateTime.
- Dùng locale cố định nếu bắt buộc truyền tên tháng/ngày bằng chữ.
- Dùng timezone ID IANA thay cho chữ viết tắt mơ hồ.
- Không thay đổi cấu hình timezone/locale của ObjectMapper dùng chung theo từng request.
- Đừng giả định pattern của SimpleDateFormat và DateTimeFormatter giống nhau.

## 28. Tổng kết

@JsonFormat giúp mô tả cách một giá trị Java được đọc và ghi thành JSON. Pattern định hình chuỗi, locale điều khiển các thành phần văn bản theo ngôn ngữ, timezone điều khiển việc diễn giải hoặc hiển thị thời điểm, còn shape xác định dạng JSON ở cấp cấu trúc.

Để cấu hình đúng, cần hiểu kiểu Java đang dùng. LocalDate và LocalTime không có timezone; LocalDateTime là giờ địa phương chưa xác định instant; OffsetDateTime có offset; Instant là thời điểm tuyệt đối. Cùng một pattern không thể thay thế sự khác biệt về ngữ nghĩa này.

Khi hợp đồng ngày giờ được xác định rõ và Jackson được cấu hình phù hợp, dữ liệu có thể được trao đổi nhất quán giữa các hệ thống, bất kể locale hoặc timezone mặc định của môi trường chạy.
