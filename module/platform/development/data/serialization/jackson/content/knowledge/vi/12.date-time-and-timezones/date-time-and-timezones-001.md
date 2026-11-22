# Vai trò của module hỗ trợ java.time

Java cung cấp API ngày giờ hiện đại trong package `java.time`. Các kiểu như `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` và `ZonedDateTime` biểu diễn những khái niệm thời gian khác nhau. Khi ứng dụng dùng Jackson để đọc hoặc ghi JSON, cần có serializer và deserializer hiểu các kiểu này.

Trong Jackson 2.x, module đảm nhiệm việc đó là **`jackson-datatype-jsr310`**, với module class **`JavaTimeModule`**. Module bổ sung quy tắc ánh xạ giữa các kiểu `java.time` và JSON, giúp `ObjectMapper` xử lý ngày giờ theo định dạng có ý nghĩa thay vì coi chúng như những object Java thông thường.

Module này giải quyết phần chuyển đổi kỹ thuật. Nó không tự quyết định múi giờ nghiệp vụ, không xác định một `LocalDateTime` thuộc khu vực nào và không thay thế việc thiết kế hợp đồng ngày giờ của API. Muốn dữ liệu thời gian chính xác, trước hết cần chọn đúng kiểu Java, sau đó cấu hình và kiểm thử cách Jackson biểu diễn kiểu đó.

## 1. Vì sao cần module hỗ trợ java.time?

Các kiểu ngày giờ trong `java.time` không phải lúc nào cũng có thể được ánh xạ bằng quy tắc bean thông thường. Chúng có constructor, factory method và ngữ nghĩa riêng. Ví dụ, `Instant` biểu diễn một thời điểm trên dòng thời gian UTC; `LocalDate` chỉ biểu diễn ngày lịch, không chứa giờ hoặc múi giờ.

Jackson Databind cần biết:

- Cách đọc chuỗi hoặc giá trị JSON thành một kiểu ngày giờ cụ thể.
- Cách ghi giá trị Java thành JSON theo định dạng phù hợp.
- Cách xử lý offset, zone, phần giây và độ chính xác nano giây.
- Cách áp dụng định dạng mặc định hoặc định dạng được khai báo bằng annotation.
- Cách xử lý giá trị thiếu, null và các input không hợp lệ.

`JavaTimeModule` cung cấp serializer/deserializer cho nhiều kiểu trong `java.time`. Khi đăng ký module trên `ObjectMapper`, các kiểu này được xử lý theo ngữ nghĩa thời gian của chúng.

### 1.1. JSON không có kiểu ngày giờ riêng

JSON chỉ có các kiểu cơ bản: object, array, string, number, boolean và null. Không có kiểu riêng tên là date, time, timestamp hay timezone.

Vì vậy, ngày giờ trong JSON thường được biểu diễn bằng:

- **String theo ISO-8601/RFC 3339**, ví dụ `"2026-11-12T09:30:00+07:00"`.
- **Number timestamp**, thường là số giây hoặc mili giây tính từ epoch, tùy cấu hình.
- **Array số**, có thể xuất hiện với một số kiểu local date/time khi chế độ timestamp được bật.

Hình dạng JSON phải được thống nhất trong hợp đồng API. Hai hệ thống có thể cùng dùng Jackson nhưng vẫn không tương thích nếu một bên gửi chuỗi ISO-8601 còn bên kia mong đợi timestamp hoặc array.

### 1.2. Vai trò của module trong luồng chuyển đổi

```text
Java object có java.time
        │
        ▼
ObjectMapper + JavaTimeModule
        │
        ├── Serialize ──> JSON string / number / array
        │
        └── Deserialize <── JSON string / number / array
        │
        ▼
Kiểu java.time tương ứng
```

Module đăng ký các serializer và deserializer cần thiết với Jackson Databind. `ObjectMapper` tiếp tục sử dụng parser/generator của Jackson Core để đọc và ghi token JSON.

Nếu module chưa được đăng ký, ứng dụng có thể gặp lỗi không tìm được serializer/deserializer phù hợp hoặc hành vi không như mong đợi, tùy phiên bản và cách mapper được tạo.

## 2. Các kiểu java.time và ý nghĩa múi giờ

Chọn đúng kiểu thời gian quan trọng hơn việc chọn một pattern JSON. Một chuỗi trông giống ngày giờ chưa chắc xác định được một thời điểm duy nhất.

| Kiểu Java | Biểu diễn | Có offset/zone? | Trường hợp thường dùng |
| --- | --- | --- | --- |
| `LocalDate` | Ngày lịch, ví dụ `2026-11-12` | Không | Ngày sinh, ngày nghỉ, ngày hóa đơn |
| `LocalTime` | Giờ trong ngày, ví dụ `09:30:00` | Không | Giờ mở cửa, giờ bắt đầu theo lịch địa phương |
| `LocalDateTime` | Ngày và giờ địa phương | Không | Thời gian trên đồng hồ địa phương khi zone được lưu riêng |
| `OffsetTime` | Giờ trong ngày kèm offset | Có offset | Một số hợp đồng cần giờ và độ lệch UTC |
| `OffsetDateTime` | Ngày giờ kèm offset như `+07:00` | Có offset | Thời điểm gửi qua API cần giữ offset |
| `ZonedDateTime` | Ngày giờ cùng ZoneId như `Asia/Ho_Chi_Minh` | Có zone | Lịch hẹn gắn với quy tắc múi giờ khu vực |
| `Instant` | Một thời điểm trên UTC timeline | UTC | Timestamp tạo bản ghi, sự kiện, audit |
| `Duration` | Khoảng thời gian theo giây/nano giây | Không | Timeout, thời lượng xử lý |
| `Period` | Khoảng thời gian theo năm/tháng/ngày lịch | Không | Tuổi, thời hạn theo lịch |

### 2.1. LocalDate và LocalTime

`LocalDate` chỉ có ngày, không có giờ và không có timezone:

```java
LocalDate dueDate = LocalDate.of(2026, 11, 12);
```

JSON thường là:

```json
"2026-11-12"
```

`LocalTime` chỉ có giờ trong ngày:

```java
LocalTime openingTime = LocalTime.of(9, 30);
```

JSON thường là:

```json
"09:30:00"
```

Không nên tự gắn timezone vào các kiểu này nếu dữ liệu nghiệp vụ chỉ là ngày hoặc giờ trên lịch. Ví dụ, ngày sinh không cần chuyển đổi sang UTC; đổi timezone không làm thay đổi ngày sinh đã được lưu theo lịch.

### 2.2. LocalDateTime

`LocalDateTime` chứa ngày và giờ nhưng không có offset hay zone:

```java
LocalDateTime localStart =
    LocalDateTime.of(2026, 11, 12, 9, 30);
```

JSON thường có dạng:

```json
"2026-11-12T09:30:00"
```

Chuỗi này không xác định duy nhất một thời điểm trên toàn cầu. Không thể biết nó tương ứng với UTC nào nếu không có thêm timezone hoặc offset.

Ví dụ, `2026-11-12T09:30:00` có thể là 09:30 tại Thành phố Hồ Chí Minh, Tokyo hoặc Paris. Các thời điểm tuyệt đối tương ứng sẽ khác nhau.

Dùng `LocalDateTime` khi ứng dụng cần lưu giờ trên lịch địa phương và zone được xác định ở nơi khác. Nếu API cần truyền một thời điểm để các hệ thống ở nhiều múi giờ hiểu giống nhau, hãy cân nhắc `Instant` hoặc `OffsetDateTime`.

### 2.3. OffsetDateTime

`OffsetDateTime` có ngày, giờ và độ lệch so với UTC:

```java
OffsetDateTime meeting =
    OffsetDateTime.parse("2026-11-12T09:30:00+07:00");
```

JSON có thể giữ offset:

```json
"2026-11-12T09:30:00+07:00"
```

Offset `+07:00` đủ để tính ra một thời điểm UTC. Tuy nhiên, offset không chứa toàn bộ quy tắc múi giờ khu vực. Nó không cho biết tên vùng, lịch sử thay đổi giờ mùa hè hay quy tắc trong tương lai.

### 2.4. ZonedDateTime

`ZonedDateTime` chứa ngày giờ, offset tại thời điểm đó và `ZoneId`:

```java
ZonedDateTime localMeeting =
    ZonedDateTime.of(
        2026, 11, 12, 9, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh")
    );
```

Zone ID như `Asia/Ho_Chi_Minh` đại diện cho một bộ quy tắc múi giờ, không chỉ là độ lệch cố định. Điều này quan trọng với khu vực có thay đổi giờ mùa hè hoặc quy tắc lịch sử.

Một chuỗi chỉ có `+07:00` không tương đương hoàn toàn với `Asia/Ho_Chi_Minh`. Nếu nghiệp vụ cần giữ khu vực để tính lịch trong tương lai, hãy lưu ZoneId một cách tường minh.

### 2.5. Instant

`Instant` biểu diễn một thời điểm duy nhất trên UTC timeline:

```java
Instant createdAt = Instant.parse("2026-11-12T02:30:00Z");
```

JSON thường là:

```json
"2026-11-12T02:30:00Z"
```

`Instant` không lưu timezone của người dùng. Nó lưu thời điểm tuyệt đối; khi hiển thị cho người dùng, ứng dụng chuyển đổi sang zone thích hợp.

Đối với timestamp tạo bản ghi, thời điểm nhận sự kiện, log hoặc audit, `Instant` thường là lựa chọn rõ ràng. Việc hiển thị theo giờ địa phương có thể được thực hiện ở lớp giao diện hoặc dịch vụ trình bày.

## 3. Artifact jackson-datatype-jsr310

Trong Jackson 2.x, module hỗ trợ `java.time` được đóng gói riêng.

| Thành phần | Giá trị |
| --- | --- |
| Artifact | `com.fasterxml.jackson.datatype:jackson-datatype-jsr310` |
| Module class | `com.fasterxml.jackson.datatype.jsr310.JavaTimeModule` |
| Vai trò | Serializer/deserializer cho các kiểu `java.time` |
| Nơi đăng ký | `ObjectMapper` hoặc builder do framework quản lý |

Module thuộc hệ sinh thái Jackson Datatype. Cần dùng phiên bản tương thích với các artifact Jackson còn lại, đặc biệt `jackson-databind`, `jackson-core` và `jackson-annotations`.

### 3.1. Khai báo dependency Gradle

Với Gradle:

```groovy
dependencies {
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

Nếu dự án dùng Spring Boot dependency management hoặc Jackson BOM, thông thường không cần tự khai báo version ở từng dependency. Hãy để BOM quản lý các module cùng release line.

Nếu dự án Java độc lập không dùng BOM, khai báo version rõ ràng và giữ các artifact Jackson đồng bộ. Không nên chỉ nâng riêng module JSR-310 lên phiên bản khác xa Databind đang dùng.

### 3.2. Khai báo dependency Maven

Với Maven:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

Nếu dùng parent/BOM quản lý dependency, version được kế thừa từ dependency management. Nếu không, hãy thêm version tương thích với Jackson Databind đang chạy.

### 3.3. Kiểm tra dependency thực tế

Dependency được khai báo trong file build chưa chắc là phiên bản cuối cùng trên runtime classpath. Với Gradle, có thể kiểm tra:

```bash
./gradlew dependencyInsight --dependency jackson-datatype-jsr310 --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.datatype:jackson-datatype-jsr310
```

Kiểm tra thêm phiên bản của `jackson-databind` và `jackson-core`. Nếu module không có trong runtime classpath hoặc bị resolve sang phiên bản không tương thích, mapper có thể không tìm thấy serializer/deserializer mong đợi.

## 4. Đăng ký JavaTimeModule với ObjectMapper

Trong ứng dụng Java độc lập, đăng ký module một cách tường minh:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Cấu hình trên có hai phần:

1. `addModule(new JavaTimeModule())` đăng ký hỗ trợ các kiểu `java.time`.
2. `disable(WRITE_DATES_AS_TIMESTAMPS)` yêu cầu ghi ngày giờ dưới dạng chuỗi thay vì timestamp/array theo chế độ timestamp.

Có thể dùng cách tương đương:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Hãy cấu hình mapper hoàn tất trước khi chia sẻ nó cho nhiều luồng. Sau đó tái sử dụng mapper thay vì tạo một mapper mới cho mỗi request.

### 4.1. Tự động phát hiện module

Jackson có cơ chế tìm module trên classpath:

```java
ObjectMapper mapper = new ObjectMapper()
    .findAndRegisterModules();
```

Cách này tiện khi ứng dụng có nhiều module Jackson. Tuy nhiên, trong ví dụ hoặc cấu hình cần tính xác định cao, đăng ký `JavaTimeModule` tường minh giúp người đọc thấy rõ mapper cần hỗ trợ kiểu nào.

Không nên cho rằng mọi mapper trong ứng dụng đều tự động có module chỉ vì dependency đã xuất hiện. Một mapper tự tạo trong service, mapper do framework quản lý và mapper dùng trong test có thể có cấu hình khác nhau.

## 5. Sử dụng trong Spring Boot

Spring Boot thường cung cấp `ObjectMapper` được cấu hình thông qua Jackson builder và HTTP message converter. Các module Jackson trên classpath thường được tích hợp vào mapper auto-configured, tùy phiên bản Spring Boot và cách ứng dụng tùy chỉnh cấu hình.

Vì vậy, khi dùng Spring Boot:

- Thêm dependency `jackson-datatype-jsr310`.
- Ưu tiên inject `ObjectMapper` do Spring quản lý.
- Kiểm tra cấu hình nếu dự án thay thế mapper hoặc tự tạo `MappingJackson2HttpMessageConverter`.
- Dùng integration test để xác nhận request/response HTTP thực tế có dạng ngày giờ mong muốn.

Ví dụ service nhận mapper được inject:

```java
@Service
public class EventJsonService {

    private final ObjectMapper mapper;

    public EventJsonService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String write(EventResponse response)
            throws JsonProcessingException {
        return mapper.writeValueAsString(response);
    }
}
```

Nếu cần cấu hình riêng thông qua builder, có thể đăng ký module ở cấu hình Spring:

```java
@Configuration
public class JacksonConfiguration {

    @Bean
    public Module javaTimeModule() {
        return new JavaTimeModule();
    }
}
```

Các `Module` bean thường được Spring Boot/Jackson builder đăng ký vào mapper auto-configured. Hãy kiểm tra cấu hình hiện tại để tránh tạo nhiều mapper với chính sách khác nhau hoặc đăng ký cùng một cấu hình ở nhiều nơi không cần thiết.

Không nên tạo một `new ObjectMapper()` trong service rồi dùng nó thay mapper của Spring nếu mục tiêu là giữ cùng định dạng với request/response HTTP.

## 6. Biểu diễn java.time thành JSON

Module có thể biểu diễn ngày giờ bằng chuỗi hoặc timestamp. Với API, chuỗi ISO-8601 thường dễ đọc và tương thích hơn.

### 6.1. Ghi chuỗi ISO-8601

Ví dụ DTO:

```java
public record MeetingResponse(
    LocalDate meetingDate,
    LocalTime startTime,
    LocalDateTime localStart,
    OffsetDateTime startWithOffset,
    Instant createdAt
) {}
```

Tạo giá trị:

```java
MeetingResponse response = new MeetingResponse(
    LocalDate.of(2026, 11, 12),
    LocalTime.of(9, 30),
    LocalDateTime.of(2026, 11, 12, 9, 30),
    OffsetDateTime.parse("2026-11-12T09:30:00+07:00"),
    Instant.parse("2026-11-12T02:30:00Z")
);
```

Dùng mapper đã đăng ký JavaTimeModule và tắt timestamp:

```java
String json = mapper.writeValueAsString(response);
```

JSON có hình dạng:

```json
{
  "meetingDate": "2026-11-12",
  "startTime": "09:30:00",
  "localStart": "2026-11-12T09:30:00",
  "startWithOffset": "2026-11-12T09:30:00+07:00",
  "createdAt": "2026-11-12T02:30:00Z"
}
```

Điểm cần chú ý:

- `meetingDate` không có giờ hoặc timezone.
- `startTime` không xác định ngày hoặc timezone.
- `localStart` không xác định offset.
- `startWithOffset` có offset `+07:00`.
- `createdAt` xác định thời điểm theo UTC với hậu tố `Z`.

### 6.2. Tắt WRITE_DATES_AS_TIMESTAMPS

`SerializationFeature.WRITE_DATES_AS_TIMESTAMPS` quyết định Jackson có ghi các kiểu ngày giờ theo dạng timestamp hay không.

```java
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Khi tắt, các kiểu ngày giờ được module hỗ trợ thường được ghi dưới dạng chuỗi ISO-8601 phù hợp với kiểu.

Khi bật, cách biểu diễn phụ thuộc kiểu:

- Một số kiểu có thể được ghi thành số timestamp.
- Các kiểu local như `LocalDate`, `LocalTime` và `LocalDateTime` không có một instant tuyệt đối để chuyển thành epoch timestamp; chúng có thể được ghi thành array thành phần số.
- Hình dạng chính xác còn phụ thuộc loại temporal và phiên bản/module.

Ví dụ array có thể có dạng:

```json
[2026, 11, 12]
```

đối với `LocalDate`, hoặc array chứa thành phần ngày/giờ đối với các kiểu local khác.

Đừng để API vô tình thay đổi từ chuỗi ISO sang array chỉ vì một mapper khác bật `WRITE_DATES_AS_TIMESTAMPS`. Hãy cấu hình tường minh và kiểm tra JSON output.

### 6.3. Timestamp và đơn vị thời gian

Khi dùng timestamp dạng số, cần xác định rõ đơn vị và quy ước:

- Epoch seconds: số giây từ mốc 1970-01-01T00:00:00Z, có thể có phần thập phân biểu diễn nano giây.
- Epoch milliseconds: số mili giây từ cùng mốc.
- Timestamp không mang timezone hiển thị; nó biểu diễn thời điểm tuyệt đối theo epoch.

Jackson có feature liên quan đến việc ghi timestamp với độ chính xác nano giây, như `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS`. Cấu hình đọc cũng có quy tắc tương ứng. Đừng tự giả định một số như `1730000000000` là giây; đó thường là mili giây theo quy ước phổ biến.

Nếu hợp đồng dùng timestamp số, tài liệu API cần ghi rõ đơn vị, độ chính xác, miền giá trị và cách xử lý phần thập phân. Nếu không có lý do đặc biệt, ISO-8601 string thường dễ kiểm tra bằng mắt và ít gây nhầm đơn vị hơn.

### 6.4. Ghi kèm ZoneId cho ZonedDateTime

`ZonedDateTime` có ZoneId. Nếu cần ghi cả tên zone thay vì chỉ offset, có thể bật:

```java
mapper.enable(SerializationFeature.WRITE_DATES_WITH_ZONE_ID);
```

Khi đó biểu diễn có thể bao gồm zone ID trong chuỗi theo định dạng zoned date-time, ví dụ:

```text
2026-11-12T09:30:00+07:00[Asia/Ho_Chi_Minh]
```

Không phải mọi client hoặc schema JSON đều chấp nhận hậu tố zone dạng ngoặc vuông này. Nếu hợp đồng yêu cầu RFC 3339 date-time string, hãy xác định rõ cách truyền ZoneId riêng, chẳng hạn thêm property `timeZone` thay vì giả định mọi client hiểu chuỗi ZonedDateTime đầy đủ.

## 7. Đọc JSON thành các kiểu java.time

Khi module được đăng ký, Jackson có thể đọc các chuỗi ISO-8601 phù hợp thành kiểu Java tương ứng.

Ví dụ:

```java
public record EventRequest(
    LocalDate eventDate,
    LocalTime startTime,
    OffsetDateTime startsAt,
    Instant createdAt
) {}
```

Payload:

```json
{
  "eventDate": "2026-11-12",
  "startTime": "09:30:00",
  "startsAt": "2026-11-12T09:30:00+07:00",
  "createdAt": "2026-11-12T02:30:00Z"
}
```

Đọc:

```java
EventRequest request = mapper.readValue(json, EventRequest.class);
```

Jackson chọn deserializer dựa trên kiểu component. Nếu string không phù hợp với định dạng kiểu đích, thao tác có thể ném lỗi mapping/parse ngày giờ.

### 7.1. Định dạng phù hợp với kiểu đích

| Kiểu | Ví dụ input |
| --- | --- |
| `LocalDate` | `"2026-11-12"` |
| `LocalTime` | `"09:30:00"` |
| `LocalDateTime` | `"2026-11-12T09:30:00"` |
| `OffsetDateTime` | `"2026-11-12T09:30:00+07:00"` |
| `Instant` | `"2026-11-12T02:30:00Z"` |
| `ZonedDateTime` | Chuỗi ISO zoned date-time hoặc định dạng phù hợp với cấu hình |

Không nên đọc chuỗi chỉ có ngày vào `Instant` vì nó không xác định giờ và offset. Tương tự, chuỗi `LocalDateTime` không có offset không thể tự xác định một instant nếu thiếu timezone.

### 7.2. Xử lý offset và context timezone

Một số cấu hình Databind có thể điều chỉnh giá trị ngày giờ có offset/zone theo timezone của mapper hoặc context khi deserialize. Feature liên quan là `DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE`.

Nếu hợp đồng yêu cầu giữ nguyên offset/zone do client gửi, hãy xem xét cấu hình feature này và kiểm thử với kiểu temporal cụ thể:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Tác động chính xác có thể khác nhau theo kiểu temporal và phiên bản Jackson. `LocalDate` và `LocalDateTime` vốn không có zone để điều chỉnh. Với `OffsetDateTime` hoặc `ZonedDateTime`, hãy viết test xác nhận giá trị offset/zone sau deserialize và sau serialize.

Đừng dùng timezone mặc định của máy chủ làm hợp đồng ngầm. Cấu hình server ở một môi trường khác có thể làm kết quả hiển thị khác đi.

## 8. Annotation @JsonFormat cho định dạng riêng

Nếu API yêu cầu định dạng khác mặc định, có thể dùng `@JsonFormat` trên property.

Ví dụ ngày theo pattern:

```java
public record EmployeeResponse(
    long id,
    @JsonFormat(pattern = "dd/MM/yyyy")
    LocalDate birthDate
) {}
```

JSON tương ứng:

```json
{
  "id": 10,
  "birthDate": "12/11/1995"
}
```

Với thời điểm có offset:

```java
public record AppointmentResponse(
    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
    OffsetDateTime startsAt
) {}
```

Pattern dùng ký hiệu của `DateTimeFormatter` trong Java, không phải mọi ký hiệu đều giống `SimpleDateFormat`.

Một số ký hiệu dễ nhầm:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `yyyy` | Năm theo year-of-era |
| `uuuu` | Proleptic year, thường phù hợp cho biểu diễn năm ISO |
| `MM` | Tháng |
| `dd` | Ngày trong tháng |
| `HH` | Giờ theo hệ 24 giờ |
| `mm` | Phút |
| `ss` | Giây |
| `XXX` | Offset dạng `+07:00` hoặc `Z` |

Tránh nhầm `MM` với `mm` (tháng và phút), `dd` với `DD` (ngày trong tháng và ngày trong năm), hoặc `yyyy` với `YYYY` (week-based year). Các lỗi pattern có thể chỉ xuất hiện ở một số ngày gần ranh giới năm.

Dùng pattern riêng khi hợp đồng thực sự yêu cầu. Với API mới, ISO-8601 mặc định thường dễ tương tác hơn định dạng ngày kiểu địa phương như `12/11/2026`, vốn có thể bị hiểu là ngày 12 tháng 11 hoặc ngày 11 tháng 12 tùy locale.

## 9. Múi giờ, offset và quy tắc nghiệp vụ

Module giúp Jackson chuyển đổi kiểu, nhưng không thể tự suy ra múi giờ mà nghiệp vụ muốn dùng.

### 9.1. Không chuyển LocalDateTime thành thời điểm tuyệt đối nếu thiếu zone

Ví dụ:

```java
LocalDateTime local = LocalDateTime.parse("2026-11-12T09:30:00");
```

Giá trị này chỉ có nghĩa 09:30 theo một lịch địa phương. Để chuyển thành Instant, cần cung cấp ZoneId:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant = local
    .atZone(zone)
    .toInstant();
```

Không dùng `ZoneId.systemDefault()` như một giải pháp ngầm cho dữ liệu đến từ client nếu hệ thống cần kết quả ổn định. Múi giờ máy chủ có thể khác múi giờ người dùng hoặc thay đổi giữa môi trường triển khai.

### 9.2. Offset không thay thế ZoneId

Offset là độ lệch cố định so với UTC tại một thời điểm. ZoneId là tên vùng có quy tắc lịch sử và có thể thay đổi theo thời gian.

Ví dụ:

- `+07:00` là offset.
- `Asia/Ho_Chi_Minh` là ZoneId.
- `Europe/Paris` có thể có offset khác nhau tùy ngày do quy tắc giờ mùa hè.

Nếu cần tính một cuộc hẹn tương lai theo giờ địa phương của một thành phố, hãy lưu cả LocalDateTime và ZoneId hoặc dùng ZonedDateTime theo thiết kế domain. Nếu chỉ cần ghi lại thời điểm sự kiện đã xảy ra, Instant thường đủ.

### 9.3. DST và thời điểm mơ hồ

Ở khu vực có daylight saving time, một LocalDateTime có thể:

- Không tồn tại khi đồng hồ nhảy tới phía trước.
- Xuất hiện hai lần khi đồng hồ quay lùi.

Vì vậy, chuyển một LocalDateTime sang ZonedDateTime có thể cần chính sách giải quyết gap/overlap. Java Time API có quy tắc mặc định, nhưng nghiệp vụ đặt lịch có thể cần hỏi người dùng hoặc chọn offset cụ thể.

Jackson chỉ deserialize giá trị được gửi. Nó không biết ứng dụng muốn xử lý cuộc hẹn trong khoảng DST bị bỏ qua như thế nào.

## 10. Chọn kiểu thời gian cho DTO và API

Một số quy tắc thực tế:

| Nhu cầu | Kiểu nên cân nhắc | Lý do |
| --- | --- | --- |
| Ngày sinh, ngày lễ, ngày trên hóa đơn | `LocalDate` | Chỉ là ngày lịch |
| Giờ mở cửa hằng ngày | `LocalTime` | Không gắn với một ngày cụ thể |
| Thời điểm tạo bản ghi/audit | `Instant` | Một thời điểm tuyệt đối, dễ chuẩn hóa UTC |
| API cần giữ offset người gửi | `OffsetDateTime` | Offset hiện diện trong dữ liệu |
| Cuộc hẹn theo múi giờ khu vực | `ZonedDateTime` hoặc LocalDateTime + ZoneId | Giữ quy tắc vùng |
| Thời lượng xử lý | `Duration` | Khoảng thời gian theo thời lượng |
| Hạn theo tháng/ngày lịch | `Period` | Ngữ nghĩa lịch, không phải số giây cố định |

Không nên dùng `LocalDateTime` cho mọi field chỉ vì nó có cả ngày và giờ. Nó thiếu thông tin để xác định một thời điểm toàn cầu.

Đối với hệ thống phân tán, một quy ước phổ biến là lưu timestamp sự kiện dưới dạng Instant/UTC, rồi chuyển sang timezone hiển thị ở lớp presentation. Đối với lịch hẹn tương lai theo địa phương, giữ ZoneId là quan trọng vì quy tắc timezone có thể thay đổi.

## 11. Các kiểu java.time khác

Ngoài các kiểu phổ biến, JavaTimeModule còn hỗ trợ nhiều kiểu ngày giờ khác trong `java.time`.

### 11.1. Duration

`Duration` biểu diễn độ dài thời gian theo giây và nano giây:

```java
Duration timeout = Duration.ofSeconds(30);
```

Dùng cho timeout, thời gian xử lý hoặc khoảng cách giữa hai Instant. Nó không có khái niệm tháng lịch; một tháng không phải số giây cố định.

### 11.2. Period

`Period` biểu diễn khoảng thời gian theo năm, tháng và ngày lịch:

```java
Period warranty = Period.ofMonths(18);
```

Dùng cho tuổi, thời hạn theo tháng hoặc quy tắc lịch. Không nên đổi Period thành số giây nếu nghiệp vụ phụ thuộc độ dài tháng/năm.

### 11.3. Year, YearMonth và MonthDay

Các kiểu này biểu diễn thành phần lịch mà không cần một ngày đầy đủ:

```java
Year fiscalYear = Year.of(2026);
YearMonth billingMonth = YearMonth.of(2026, 11);
MonthDay anniversary = MonthDay.of(11, 12);
```

Chúng hữu ích cho năm tài chính, kỳ thanh toán hoặc ngày kỷ niệm lặp hằng năm. Hãy xác định rõ định dạng JSON trong hợp đồng thay vì ép mọi kiểu thành LocalDate.

## 12. Lỗi thường gặp khi dùng JavaTimeModule

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Jackson không tìm thấy serializer cho LocalDate/Instant | Thiếu module hoặc mapper chưa đăng ký module | Thêm jsr310 dependency và đăng ký JavaTimeModule trên mapper thực tế |
| JSON xuất hiện array thay vì chuỗi ISO | WRITE_DATES_AS_TIMESTAMPS đang bật | Tắt feature nếu hợp đồng yêu cầu ISO string |
| LocalDateTime không có Z hoặc offset | Bản thân kiểu không chứa timezone | Dùng Instant/OffsetDateTime hoặc truyền ZoneId riêng nếu cần |
| Instant bị lệch khi hiển thị | Chuyển đổi sang timezone ở lớp trình bày | Kiểm tra instant gốc và timezone hiển thị |
| OffsetDateTime sau deserialize không giữ offset mong muốn | Context timezone adjustment hoặc cấu hình khác | Kiểm tra ADJUST_DATES_TO_CONTEXT_TIME_ZONE và test mapper |
| Parse ngày sai format | Pattern không khớp hoặc input không phải ISO mặc định | Dùng @JsonFormat hoặc custom formatter theo hợp đồng |
| Ngày gần cuối năm bị lệch năm | Dùng YYYY thay vì yyyy/uuuu | Kiểm tra pattern DateTimeFormatter |
| Giờ bị sai do dùng MM/mm | Nhầm tháng với phút | Dùng pattern đúng: MM cho tháng, mm cho phút |
| Máy local chạy được nhưng môi trường khác lỗi | Mapper/dependency hoặc timezone default khác nhau | Kiểm tra runtime classpath và cấu hình thực tế |
| Ngày hẹn tương lai lệch khi quy tắc DST thay đổi | Chỉ lưu offset cố định | Lưu ZoneId và xác định chính sách lịch |

Khi debug, hãy kiểm tra theo thứ tự: kiểu Java đích, JSON thực tế, module đã đăng ký, serialization feature, timezone/offset và pattern. Đừng chỉnh timezone toàn cục để chữa một lỗi pattern hoặc chọn sai kiểu dữ liệu.

## 13. Kiểm thử serialization và deserialization ngày giờ

Nên kiểm thử cả hai chiều và xác nhận kiểu temporal sau khi đọc lại.

### 13.1. Test round-trip với nhiều kiểu

```java
class JavaTimeMappingTest {

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

    @Test
    void roundTripsDateAndTimeTypes() throws Exception {
        EventRequest original = new EventRequest(
            LocalDate.of(2026, 11, 12),
            LocalTime.of(9, 30),
            OffsetDateTime.parse("2026-11-12T09:30:00+07:00"),
            Instant.parse("2026-11-12T02:30:00Z")
        );

        String json = mapper.writeValueAsString(original);
        EventRequest restored = mapper.readValue(json, EventRequest.class);

        assertEquals(original, restored);
    }
}
```

Test này kiểm tra mapper có ghi và đọc các kiểu temporal theo cấu hình đã chọn. Với `ZonedDateTime`, nên có test riêng nếu hợp đồng cần giữ ZoneId.

### 13.2. Test JSON string có offset

```java
@Test
void readsOffsetDateTime() throws Exception {
    OffsetDateTime value = mapper.readValue(
        "\"2026-11-12T09:30:00+07:00\"",
        OffsetDateTime.class
    );

    assertEquals(ZoneOffset.ofHours(7), value.getOffset());
}
```

Nếu hệ thống cần chuẩn hóa sang UTC, có thể chuyển đổi tường minh:

```java
Instant instant = value.toInstant();
```

Không nên thay offset chỉ để làm chuỗi output trông đồng nhất nếu hợp đồng cần giữ offset nguồn.

### 13.3. Test LocalDateTime không có timezone

```java
@Test
void readsLocalDateTimeWithoutZone() throws Exception {
    LocalDateTime value = mapper.readValue(
        "\"2026-11-12T09:30:00\"",
        LocalDateTime.class
    );

    assertEquals(LocalDateTime.of(2026, 11, 12, 9, 30), value);
}
```

Test này giúp tránh việc code sau đó giả định LocalDateTime đã là UTC hoặc đã thuộc timezone của máy chủ.

### 13.4. Test định dạng riêng

Với property dùng `@JsonFormat`, hãy kiểm thử:

- JSON đúng pattern được đọc.
- JSON sai pattern bị từ chối.
- Serialize tạo đúng pattern hợp đồng.
- Ngày ở ranh giới tháng/năm không bị hiểu nhầm.
- Offset được giữ hoặc chuẩn hóa theo chính sách đã định.

## 14. Quy trình cấu hình module cho dự án

Khi thêm hỗ trợ `java.time` vào một dự án:

1. Xác định các kiểu ngày giờ đang được dùng trong DTO, entity và API.
2. Chọn kiểu phù hợp với ngữ nghĩa: ngày lịch, giờ địa phương, thời điểm tuyệt đối hay lịch theo zone.
3. Thêm `jackson-datatype-jsr310` với version do BOM hoặc dependency management quản lý.
4. Đăng ký `JavaTimeModule` trên mapper dùng thực tế; với Spring Boot, xác minh mapper auto-configured.
5. Chọn định dạng JSON, thường là ISO-8601 string cho API.
6. Tắt `WRITE_DATES_AS_TIMESTAMPS` nếu hợp đồng không dùng timestamp/array.
7. Xác định có cần giữ offset/ZoneId hay chuẩn hóa về Instant/UTC.
8. Dùng `@JsonFormat` chỉ khi cần pattern riêng.
9. Viết round-trip test và integration test qua HTTP.
10. Kiểm tra timezone mặc định ở local, CI và production để tránh phụ thuộc môi trường.

## 15. Bài thực hành tổng hợp

Xây dựng API quản lý cuộc hẹn có các field:

```java
public record AppointmentRequest(
    String title,
    LocalDate appointmentDate,
    LocalTime localStartTime,
    ZoneId timeZone,
    OffsetDateTime startsAt,
    Instant createdAt
) {}
```

Thực hiện:

1. Thêm dependency `jackson-datatype-jsr310`.
2. Đăng ký `JavaTimeModule` vào mapper Java độc lập.
3. Tắt `WRITE_DATES_AS_TIMESTAMPS` và ghi object thành JSON.
4. Đọc JSON trở lại thành `AppointmentRequest`.
5. So sánh JSON của LocalDate, LocalTime, OffsetDateTime và Instant.
6. Thử đổi mapper sang timestamp mode và quan sát hình dạng output.
7. Thử `WRITE_DATES_WITH_ZONE_ID` với ZonedDateTime.
8. Dùng `@JsonFormat` để ghi một LocalDate theo pattern riêng.
9. Chuyển LocalDateTime thành Instant bằng ZoneId tường minh.
10. Viết test xác nhận offset được giữ hoặc chuẩn hóa theo hợp đồng.
11. Thử một lịch hẹn ở khu vực có DST và xác định cách xử lý thời điểm mơ hồ.
12. Nếu dùng Spring Boot, kiểm thử request/response HTTP bằng mapper được framework quản lý.

Bài thực hành hoàn thành khi có thể giải thích mỗi field biểu diễn ngày lịch, giờ địa phương hay một thời điểm tuyệt đối; chỉ ra module chịu trách nhiệm mapping; và chứng minh JSON giữ đúng offset/zone theo hợp đồng.

## 16. Nguyên tắc ghi nhớ

- Jackson 2.x dùng artifact `jackson-datatype-jsr310` và module class `JavaTimeModule` để hỗ trợ `java.time`.
- Module bổ sung serializer/deserializer; nó không tự quyết định timezone nghiệp vụ.
- `LocalDate`, `LocalTime` và `LocalDateTime` không chứa timezone.
- `OffsetDateTime` chứa offset; `ZonedDateTime` chứa ZoneId; `Instant` biểu diễn một thời điểm UTC.
- ISO-8601 string thường là định dạng dễ tương tác cho API.
- `WRITE_DATES_AS_TIMESTAMPS` ảnh hưởng hình dạng JSON; với kiểu local, timestamp mode có thể tạo array thành phần.
- Offset và ZoneId không tương đương; chỉ lưu offset có thể không đủ cho lịch hẹn tương lai theo khu vực.
- `@JsonFormat` hỗ trợ pattern riêng; cần dùng đúng ký hiệu của DateTimeFormatter.
- Spring Boot có thể tự đăng ký module trên mapper auto-configured, nhưng phải xác minh mapper thực tế.
- Kiểm thử round-trip, offset, zone, pattern và timezone context trước khi phát hành hợp đồng API.

Khi dùng ngày giờ với Jackson, hãy bắt đầu từ ý nghĩa thời gian của dữ liệu, chọn đúng kiểu `java.time`, đăng ký `JavaTimeModule` và định nghĩa rõ JSON representation. Cấu hình đúng module giúp Jackson chuyển đổi nhất quán; hợp đồng timezone rõ ràng giúp các hệ thống hiểu cùng một thời điểm hoặc cùng một giờ địa phương.
