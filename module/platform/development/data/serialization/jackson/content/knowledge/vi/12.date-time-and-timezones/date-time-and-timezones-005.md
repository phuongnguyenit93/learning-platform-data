# Phân biệt đơn vị giây, mili giây và độ chính xác phần giây

Khi trao đổi thời điểm qua JSON, một con số có thể biểu diễn thời gian tính từ Unix Epoch theo **giây**, **mili giây** hoặc một dạng có phần thập phân để giữ độ chính xác nhỏ hơn một giây. Các biểu diễn này trông khá giống nhau nhưng khác đơn vị. Nếu hệ thống gửi mili giây mà phía nhận hiểu là giây, thời điểm sẽ lệch hàng nghìn lần; nếu gửi giây nhưng đọc thành mili giây, kết quả sẽ rơi về một thời điểm rất gần năm 1970.

Trong Java và Jackson, cần phân biệt ba khái niệm:

- **Đơn vị epoch:** số đo khoảng thời gian từ mốc 1970-01-01T00:00:00Z, thường là seconds hoặc milliseconds.
- **Độ chính xác phần giây:** số chữ số được giữ sau dấu thập phân của giây, ví dụ millisecond có 3 chữ số, microsecond có 6 và nanosecond có 9.
- **Kiểu thời gian:** `Instant`, `Date`, `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime` mang ý nghĩa khác nhau; không phải kiểu nào cũng có thể chuyển trực tiếp thành epoch timestamp nếu thiếu múi giờ.

Bài này giải thích cách chuyển đổi chính xác, cách Jackson biểu diễn timestamp số, các feature của Java Time module và cách thiết kế hợp đồng JSON để tránh sai đơn vị.

## 1. Unix Epoch và đơn vị thời gian

Unix Epoch là mốc:

```text
1970-01-01T00:00:00Z
```

Ký hiệu `Z` nghĩa là UTC offset bằng 0. Một epoch timestamp biểu diễn khoảng cách từ mốc này đến thời điểm cần lưu.

### 1.1. Epoch seconds

Epoch seconds là số giây kể từ Unix Epoch:

```text
1735689600
```

Giá trị này tương ứng với thời điểm:

```text
2025-01-01T00:00:00Z
```

Nếu chỉ dùng số nguyên giây, phần thời gian nhỏ hơn một giây không được biểu diễn. Ví dụ hai thời điểm cách nhau 250 mili giây có thể cùng rơi vào một epoch-second integer nếu phần thập phân bị bỏ.

### 1.2. Epoch milliseconds

Epoch milliseconds là số mili giây kể từ Unix Epoch. Một giây bằng 1.000 mili giây:

```text
1 second = 1,000 milliseconds
```

Cùng thời điểm ở trên được biểu diễn:

```text
1735689600000
```

JavaScript thường dùng epoch milliseconds cho `Date.now()`, còn Java `System.currentTimeMillis()` cũng trả về số mili giây từ epoch.

### 1.3. Phần thập phân của giây

Để giữ độ chính xác nhỏ hơn một giây, timestamp có thể được biểu diễn bằng số thập phân tính theo giây:

```text
1735689600.123
```

Giá trị này có nghĩa là:

- 1.735.689.600 giây nguyên kể từ epoch.
- 0,123 giây = 123 mili giây.

Nếu có 9 chữ số sau dấu thập phân:

```text
1735689600.123456789
```

phần lẻ là 123.456.789 nanosecond, tương đương 123 mili giây, 456 microsecond và 789 nanosecond.

Một giây được chia như sau:

| Đơn vị | Số phần trong một giây | Số chữ số thập phân |
|---|---:|---:|
| Second (s) | 1 | 0 |
| Millisecond (ms) | 1.000 | 3 |
| Microsecond (µs) | 1.000.000 | 6 |
| Nanosecond (ns) | 1.000.000.000 | 9 |

Lưu ý: số chữ số sau dấu thập phân mô tả độ chính xác/độ phân giải của biểu diễn, không tự bảo đảm đồng hồ nguồn đo thời gian chính xác đến mức đó.

## 2. Các kiểu thời gian Java không có cùng ý nghĩa

Jackson không chỉ xử lý một kiểu “date”. Java cung cấp nhiều kiểu thời gian, mỗi kiểu mang một ngữ nghĩa khác nhau.

| Kiểu | Ý nghĩa | Có xác định một instant tuyệt đối không? |
|---|---|---|
| `java.util.Date` | Một thời điểm trên timeline, độ phân giải millisecond | Có |
| `Instant` | Một thời điểm trên timeline UTC, độ phân giải nanosecond | Có |
| `LocalDate` | Ngày lịch, không có giờ và timezone | Không |
| `LocalTime` | Giờ trong ngày, không có ngày và timezone | Không |
| `LocalDateTime` | Ngày và giờ địa phương, không có timezone/offset | Không |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | Có |
| `ZonedDateTime` | Ngày giờ gắn với một vùng timezone | Có, khi kết hợp với zone rules |

### 2.1. Instant là lựa chọn tự nhiên cho một thời điểm tuyệt đối

`Instant` lưu thời điểm trên timeline bằng hai thành phần:

- Số giây epoch.
- Phần nanosecond trong giây.

Ví dụ:

```java
Instant instant = Instant.parse("2025-01-01T00:00:00.123456789Z");

long seconds = instant.getEpochSecond();
int nanos = instant.getNano();
```

Kết quả:

```text
seconds = 1735689600
nanos   = 123456789
```

`getNano()` là phần nanosecond trong giây, không phải tổng số nanosecond kể từ epoch. Giá trị này nằm trong khoảng 0 đến 999.999.999.

### 2.2. Date chỉ giữ độ phân giải millisecond

`java.util.Date` biểu diễn thời điểm bằng epoch milliseconds:

```java
Date date = new Date(1735689600123L);
long epochMillis = date.getTime();
```

Khi chuyển từ `Instant` sang `Date`, phần nhỏ hơn millisecond không thể được giữ nguyên:

```java
Instant precise = Instant.parse("2025-01-01T00:00:00.123456789Z");
Date legacy = Date.from(precise);

Instant restored = legacy.toInstant();
```

`restored` chỉ có thể giữ độ chính xác millisecond của `Date`; phần 456.789 nanosecond nhỏ hơn millisecond đã mất.

Nếu ứng dụng cần độ chính xác cao hơn millisecond, hãy giữ `Instant` xuyên suốt các lớp xử lý thay vì chuyển sớm sang `Date`.

### 2.3. LocalDateTime không tự có epoch timestamp

`LocalDateTime` chỉ chứa ngày và giờ trên đồng hồ địa phương. Ví dụ:

```java
LocalDateTime local = LocalDateTime.of(2025, 1, 1, 7, 0);
```

Giá trị này có thể là 07:00 ở Ho Chi Minh City, Tokyo hoặc London. Nếu chưa biết timezone/offset, không thể xác định nó tương ứng với instant nào.

Để đổi thành `Instant`, cần cung cấp zone:

```java
Instant instant = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
```

Không nên gọi một giá trị `LocalDateTime` là “UTC” chỉ vì nó được lưu trong database. Nếu đó là thời điểm tuyệt đối, dùng `Instant` hoặc kiểu có offset/zone để biểu diễn ý nghĩa rõ ràng.

## 3. Chuyển đổi seconds và milliseconds trong Java

Các phương thức chuyển đổi của Java có tên thể hiện rõ đơn vị. Dùng đúng phương thức giúp tránh nhầm lẫn khi parse hoặc tạo timestamp.

### 3.1. Tạo Instant từ epoch seconds

```java
long epochSeconds = 1735689600L;
Instant instant = Instant.ofEpochSecond(epochSeconds);
```

Nếu cần giữ phần nanosecond:

```java
Instant precise = Instant.ofEpochSecond(
        1735689600L,
        123456789L
);
```

Tham số thứ hai là nano adjustment. Java chuẩn hóa giá trị này, vì vậy nó có thể vượt quá một giây hoặc âm; tuy nhiên, thông thường nên truyền phần nanosecond trong khoảng 0..999.999.999 để code dễ đọc.

### 3.2. Tạo Instant từ epoch milliseconds

```java
long epochMillis = 1735689600123L;
Instant instant = Instant.ofEpochMilli(epochMillis);
```

Không thay `ofEpochMilli` bằng `ofEpochSecond` chỉ vì đầu vào là một số nguyên. Đơn vị phải khớp hợp đồng của dữ liệu.

### 3.3. Lấy seconds và milliseconds từ Instant

```java
Instant instant = Instant.parse("2025-01-01T00:00:00.123456789Z");

long seconds = instant.getEpochSecond();
long millis = instant.toEpochMilli();
int nanosWithinSecond = instant.getNano();
```

Kết quả:

```text
seconds          = 1735689600
millis           = 1735689600123
nanosWithinSecond = 123456789
```

`toEpochMilli()` làm giảm độ chính xác xuống millisecond. Nếu cần giữ toàn bộ 9 chữ số phần lẻ, lưu `Instant` hoặc cặp seconds/nanos thay vì chỉ giữ một `long` millisecond.

### 3.4. Chuyển milliseconds sang seconds

Với giá trị epoch millisecond dương:

```java
long epochMillis = 1735689600123L;
long epochSeconds = epochMillis / 1000;
long remainingMillis = epochMillis % 1000;
```

Kết quả:

```text
epochSeconds = 1735689600
remainingMillis = 123
```

Nếu muốn giữ phần lẻ, không chỉ lấy phép chia nguyên. Có thể dùng:

```java
Instant instant = Instant.ofEpochMilli(epochMillis);
```

Cách này tránh tự ghép giây và phần lẻ, đồng thời xử lý đúng cả timestamp âm trước epoch.

Với thời điểm trước 1970, phép chia nguyên của Java làm tròn về 0, không phải luôn làm tròn xuống. Vì vậy, nếu tự tách giây và mili giây bằng `/` và `%`, cần xử lý số âm cẩn thận. `Instant.ofEpochMilli()` và `getEpochSecond()` là cách an toàn hơn khi làm việc với timeline.

## 4. Cấu hình Jackson Java Time module

Trong Jackson 2.x, hỗ trợ các kiểu thuộc `java.time` thường được cung cấp bởi artifact `jackson-datatype-jsr310` và `JavaTimeModule`.

Gradle:

```kotlin
dependencies {
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

Tạo mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();
```

Tắt `WRITE_DATES_AS_TIMESTAMPS` để các kiểu Java Time thường được ghi thành chuỗi ISO-8601 thay vì dạng số hoặc array. Đây thường là lựa chọn dễ đọc và ít gây hiểu nhầm đơn vị hơn cho API.

Ví dụ:

```java
Instant instant = Instant.parse("2025-01-01T00:00:00.123456789Z");
String json = mapper.writeValueAsString(instant);
```

Đầu ra dạng chuỗi:

```json
"2025-01-01T00:00:00.123456789Z"
```

Khi đọc lại:

```java
Instant restored = mapper.readValue(json, Instant.class);
```

ISO-8601 string thể hiện rõ ngày, giờ, offset và phần thập phân. Người đọc không cần đoán một con số là giây hay mili giây.

Jackson 3 có thay đổi về package và cách cấu hình mapper; hãy dùng dependency và API tương ứng với major version của dự án. Các ví dụ feature trong phần tiếp theo tập trung vào Jackson 2.x với `JavaTimeModule`.

## 5. Jackson biểu diễn timestamp số của java.time như thế nào?

Khi `WRITE_DATES_AS_TIMESTAMPS` bật, Java Time module có thể ghi các kiểu ngày giờ dưới dạng timestamp. Hai feature liên quan trực tiếp đến độ chính xác là:

- `SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS`
- `DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS`

Tên feature dễ gây nhầm: khi bật, timestamp số nguyên của các kiểu instant-based được hiểu theo **đơn vị giây**, với khả năng giữ phần thập phân đến nanosecond. Khi tắt, timestamp số nguyên được hiểu theo **đơn vị mili giây**.

### 5.1. Ghi timestamp với độ chính xác nanosecond

Cấu hình:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .enable(SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();
```

Với `Instant`:

```java
Instant instant = Instant.parse("2025-01-01T00:00:00.123456789Z");
String json = mapper.writeValueAsString(instant);
```

Biểu diễn số thường có dạng epoch seconds với phần thập phân:

```json
1735689600.123456789
```

Phần `.123456789` giữ 123.456.789 nanosecond trong giây đó. Đây là số thập phân của giây, không phải epoch milliseconds.

### 5.2. Ghi timestamp ở độ phân giải millisecond

Nếu tắt feature nanoseconds:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();
```

`Instant` sẽ được ghi thành số nguyên epoch milliseconds, ví dụ:

```json
1735689600123
```

Độ chính xác dưới millisecond không còn được thể hiện. Nếu Instant ban đầu có 123.456.789 nanosecond trong giây, biểu diễn millisecond chỉ giữ 123 millisecond.

### 5.3. Đọc timestamp số nguyên: giây hay mili giây?

Khi đọc số nguyên thành kiểu Java Time, `READ_DATE_TIMESTAMPS_AS_NANOSECONDS` quyết định cách diễn giải:

```java
ObjectMapper secondsMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();

Instant fromSeconds = secondsMapper.readValue(
        "1735689600",
        Instant.class
);
```

Với feature bật, số nguyên được hiểu là epoch seconds.

Ngược lại:

```java
ObjectMapper millisMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();

Instant fromMillis = millisMapper.readValue(
        "1735689600000",
        Instant.class
);
```

Với feature tắt, số nguyên được hiểu là epoch milliseconds.

Đây là điểm đặc biệt dễ gây lỗi khi tích hợp API. Nếu producer gửi `1735689600000` theo milliseconds nhưng consumer đọc integer theo seconds, thời điểm sẽ nằm xa hàng chục nghìn năm trong tương lai và có thể vượt miền hỗ trợ. Nếu producer gửi `1735689600` theo seconds nhưng consumer hiểu là milliseconds, kết quả sẽ rơi vào vài tuần sau epoch năm 1970.

### 5.4. Số thập phân biểu diễn seconds

Với Java Time module, timestamp JSON có phần thập phân được hiểu là giây và phần lẻ của giây, ví dụ:

```json
1735689600.123456789
```

Phần thập phân có thể mang độ chính xác nanosecond. `READ_DATE_TIMESTAMPS_AS_NANOSECONDS` chủ yếu quyết định cách hiểu số nguyên; số thập phân đã thể hiện đơn vị giây thông qua phần lẻ.

Không nên gửi một số mili giây có phần thập phân, ví dụ `1735689600123.5`, rồi giả định Jackson tự biết đó là milliseconds. Hãy thống nhất rõ schema: integer milliseconds, integer seconds hoặc decimal seconds.

## 6. Phân biệt JavaTime timestamp với java.util.Date

Một nguồn nhầm lẫn là cho rằng mọi timestamp số trong Jackson đều dùng cùng một đơn vị.

Với `java.util.Date`, timestamp số truyền thống là epoch milliseconds. Các feature nanosecond của Java Time module không đổi ý nghĩa của `Date#getTime()`.

Ví dụ:

```java
Date date = new Date(1735689600123L);
String json = mapper.writeValueAsString(date);
```

Giá trị số của `Date` là millisecond timestamp.

Với `Instant` khi dùng `JavaTimeModule`, số nguyên có thể được đọc/ghi theo seconds hoặc milliseconds tùy feature đã nêu. Vì vậy, nếu DTO có cả `Date` và `Instant`, không nên mặc định một cấu hình numeric timestamp duy nhất sẽ tạo cùng đơn vị cho cả hai.

| Kiểu Java | Dạng timestamp số thường dùng | Feature nanoseconds của Java Time |
|---|---|---|
| `java.util.Date` | Epoch milliseconds | Không đổi đơn vị của Date |
| `Instant` qua JavaTimeModule | Epoch seconds có phần thập phân, hoặc epoch milliseconds | Có ảnh hưởng |
| `OffsetDateTime` qua JavaTimeModule | Timestamp theo instant hoặc chuỗi ISO tùy cấu hình | Có ảnh hưởng khi ghi/đọc numeric timestamp |
| `LocalDateTime` | Không có epoch độc lập; khi timestamp bật có thể dùng array component | Không nên xem như epoch timestamp |
| `LocalDate` | Ngày lịch; timestamp mode có dạng cấu trúc riêng | Không phải epoch milliseconds trực tiếp |

Để tránh nhầm, nên dùng ISO-8601 string cho các API ngày giờ thông thường, hoặc định nghĩa tên/contract rõ ràng như `createdAtEpochMillis` nếu bắt buộc dùng số.

## 7. LocalDateTime và timezone: không thể suy ra đơn vị epoch nếu thiếu zone

`LocalDateTime` không chứa offset hay timezone. Vì vậy, không có một epoch timestamp duy nhất tương ứng với nó.

Ví dụ:

```java
LocalDateTime local = LocalDateTime.of(2025, 1, 1, 9, 0);
```

Nếu gắn với hai zone khác nhau:

```java
Instant hcm = local.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
Instant tokyo = local.atZone(ZoneId.of("Asia/Tokyo")).toInstant();
```

hai Instant sẽ khác nhau vì cùng 09:00 trên hai múi giờ là hai thời điểm tuyệt đối khác nhau.

### 7.1. Chuyển LocalDateTime thành epoch milliseconds

Cần chỉ rõ ZoneId:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

long epochMillis = local
        .atZone(zone)
        .toInstant()
        .toEpochMilli();
```

Không dùng `ZoneId.systemDefault()` cho hợp đồng API nếu kết quả cần ổn định giữa các server. Timezone mặc định của JVM có thể khác theo môi trường triển khai.

### 7.2. DST có thể tạo thời điểm không tồn tại hoặc mơ hồ

Ở những vùng có Daylight Saving Time (DST), một giờ địa phương có thể:

- Không tồn tại khi đồng hồ nhảy tới trước.
- Xuất hiện hai lần khi đồng hồ lùi lại.

Khi chuyển `LocalDateTime` sang `Instant`, `ZoneRules` phải giải quyết gap hoặc overlap. Nếu nghiệp vụ cần kiểm soát chính xác, hãy dùng `ZonedDateTime`, `OffsetDateTime` hoặc kiểm tra các valid offsets trước khi chuyển đổi.

Việt Nam hiện sử dụng UTC+07:00 ổn định trong thực tế, nhưng ứng dụng đa quốc gia không nên hardcode một offset cho mọi địa điểm và mọi thời điểm lịch sử. Dùng ZoneId có tên như `Asia/Ho_Chi_Minh` để dựa vào timezone database.

## 8. Độ chính xác: millisecond, microsecond và nanosecond

Một timestamp có thể có nhiều chữ số sau dấu thập phân. Việc chọn độ chính xác phải dựa trên cả nguồn dữ liệu, kiểu Java, database và consumer.

### 8.1. Instant giữ nanosecond

`Instant` lưu nanosecond trong giây. Ví dụ:

```java
Instant instant = Instant.parse("2025-01-01T00:00:00.123456789Z");

System.out.println(instant.getNano()); // 123456789
```

Nếu chuyển thành epoch milliseconds:

```java
long millis = instant.toEpochMilli();
```

các chữ số dưới millisecond bị loại bỏ.

### 8.2. Độ chính xác nguồn không đồng nghĩa độ phân giải kiểu

Một hệ thống có thể tạo `Instant.now()` nhưng clock phần cứng hoặc runtime chỉ cung cấp độ chính xác thực tế đến millisecond hoặc microsecond. Việc `Instant` có khả năng lưu nanosecond không có nghĩa giá trị đo luôn chính xác đến nanosecond.

Cần phân biệt:

- **Precision (độ chính xác biểu diễn):** số chữ số có thể lưu.
- **Resolution (độ phân giải nguồn):** bước nhỏ nhất mà nguồn thời gian có thể quan sát.
- **Accuracy (độ đúng so với thời gian chuẩn):** đồng hồ gần thời gian thực đến mức nào.

Ví dụ, một timestamp có 9 chữ số phần thập phân có thể chỉ là giá trị được padding từ clock millisecond. Đừng dùng số chữ số để kết luận độ chính xác vật lý.

### 8.3. Database có thể giảm độ chính xác

Một số database column kiểu timestamp hỗ trợ microsecond hoặc nanosecond; số khác chỉ lưu millisecond. Khi ghi từ `Instant` vào database, driver và column type có thể làm tròn hoặc cắt phần nhỏ hơn độ phân giải hỗ trợ.

Hãy xác định độ chính xác end-to-end:

```text
Clock nguồn
   -> Java Instant
   -> Jackson JSON
   -> HTTP/message broker
   -> Database column/driver
   -> Consumer
```

Nếu một chặng chỉ giữ millisecond, dữ liệu cuối cùng không thể khôi phục nanosecond đã mất ở chặng đó.

## 9. Nên dùng ISO-8601 string hay numeric timestamp?

Cả hai dạng đều hợp lệ nếu hợp đồng rõ ràng.

### 9.1. ISO-8601 string

Ví dụ:

```json
{
  "createdAt": "2025-01-01T00:00:00.123456789Z"
}
```

Ưu điểm:

- Nhìn được ngày, giờ, offset và phần thập phân.
- Không phải đoán giây hay mili giây.
- Tương thích tốt với nhiều ngôn ngữ và công cụ.
- Có thể giữ offset/zone representation theo kiểu Java phù hợp.

Đây thường là lựa chọn tốt cho API công khai hoặc event schema cần dễ đọc.

### 9.2. Numeric epoch milliseconds

```json
{
  "createdAtEpochMillis": 1735689600123
}
```

Ưu điểm:

- Dễ xử lý với JavaScript `Date` và nhiều thư viện thời gian.
- Gọn, không cần parse chuỗi ISO.
- Đơn vị phổ biến trong nhiều API và hệ thống Java legacy.

Nhược điểm là độ chính xác chỉ ở millisecond và cần tên field hoặc schema nói rõ đơn vị. Tên `createdAt` đi kèm một số trần không cho biết nó là giây hay mili giây.

### 9.3. Numeric epoch seconds có phần thập phân

```json
{
  "createdAtEpochSeconds": 1735689600.123456789
}
```

Dạng này có thể giữ nanosecond và tương thích với các hệ thống dùng Unix timestamp dạng seconds. Tuy nhiên, một số runtime hoặc parser chuyển số JSON sang binary floating point, gây mất chữ số thập phân. Với consumer JavaScript, number cũng có giới hạn precision. Nếu cần giữ chính xác tuyệt đối, cân nhắc chuỗi ISO-8601 hoặc tách seconds/nanos thành hai trường nguyên.

### 9.4. Cặp seconds và nanos

Một hợp đồng khác là truyền rõ hai phần:

```json
{
  "epochSecond": 1735689600,
  "nano": 123456789
}
```

Cách này tránh phải biểu diễn một số thập phân lớn và giữ độ chính xác nanosecond nếu cả hai trường được xử lý bằng integer đủ miền. Tuy nhiên, consumer phải tuân theo quy tắc chuẩn hóa `nano` trong khoảng 0..999.999.999.

## 10. Đặt quy tắc định dạng bằng annotation

Có thể dùng `@JsonFormat` để chỉ định dạng chuỗi và timezone cho property.

```java
public class AuditEvent {
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    private Instant createdAt;
}
```

Với `Date` hoặc kiểu lịch giờ có hỗ trợ pattern, có thể chỉ rõ pattern và timezone:

```java
public class LegacyEvent {
    @JsonFormat(
            shape = JsonFormat.Shape.STRING,
            pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
            timezone = "UTC"
    )
    private Date createdAt;
}
```

Pattern `SSS` biểu diễn millisecond. Nếu format chỉ có 3 chữ số sau dấu thập phân, không thể giữ phần microsecond/nanosecond của một `Instant` khi chuyển qua chuỗi đó.

`@JsonFormat` không phải cách tổng quát để tự động đổi một numeric timestamp từ milliseconds sang seconds cho mọi kiểu. Nếu hợp đồng số có đơn vị riêng, cần cấu hình đúng Java Time feature hoặc viết serializer/deserializer tường minh. Đặt tên field rõ ràng cũng giúp tránh phụ thuộc vào cấu hình ngầm.

## 11. Xử lý dữ liệu numeric từ API có đơn vị không rõ

Giả sử một hệ thống gửi:

```json
{
  "eventTime": 1735689600000
}
```

Con số có 13 chữ số thường gợi ý epoch milliseconds trong giai đoạn hiện tại, còn 10 chữ số thường gợi ý epoch seconds. Tuy nhiên, không được dựa vào số chữ số như một quy tắc parse. Timestamp trước/sau các mốc lịch sử, timestamp âm hoặc dữ liệu giả lập có thể không tuân theo mẫu này.

Hãy xác nhận schema hoặc tài liệu API. Nếu producer không thể sửa ngay, tạo adapter ở ranh giới tích hợp:

```java
public Instant fromEpochMillis(long value) {
    return Instant.ofEpochMilli(value);
}
```

Nếu hợp đồng nói seconds:

```java
public Instant fromEpochSeconds(long value) {
    return Instant.ofEpochSecond(value);
}
```

Đặt tên method và biến kèm đơn vị giúp code review phát hiện nhầm lẫn. Tránh các biến chung chung như `timestamp`, `time` hoặc `value` nếu đơn vị không hiển nhiên.

## 12. Custom deserializer khi API có hợp đồng numeric riêng

Nếu một API bắt buộc nhận epoch milliseconds vào property `Instant`, có thể viết deserializer tường minh thay vì phụ thuộc cấu hình chung:

```java
public class EpochMillisInstantDeserializer
        extends JsonDeserializer<Instant> {

    @Override
    public Instant deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        if (!parser.hasToken(JsonToken.VALUE_NUMBER_INT)) {
            return (Instant) context.handleUnexpectedToken(
                    Instant.class,
                    parser
            );
        }

        long epochMillis = parser.getLongValue();
        return Instant.ofEpochMilli(epochMillis);
    }
}
```

Gắn vào property:

```java
public class EventRequest {
    @JsonDeserialize(using = EpochMillisInstantDeserializer.class)
    private Instant occurredAt;
}
```

Deserializer này yêu cầu token JSON integer và diễn giải rõ là milliseconds. Nó từ chối string, decimal hoặc các kiểu token khác. Nếu API cần chấp nhận cả số nguyên và chuỗi, hãy bổ sung quy tắc một cách có chủ đích, không tự đoán đơn vị.

Một adapter như vậy nên được đặt ở boundary của hệ thống ngoài. Trong domain, giữ kiểu `Instant` để phần còn lại của ứng dụng không phải liên tục chuyển đổi epoch units.

## 13. Kiểm thử đơn vị và độ chính xác

Các test nên xác nhận cả giá trị thời điểm lẫn đơn vị được dùng.

### 13.1. Kiểm thử seconds và milliseconds

```java
@Test
void shouldCreateInstantFromSeconds() {
    Instant instant = Instant.ofEpochSecond(1735689600L);

    assertEquals(
            Instant.parse("2025-01-01T00:00:00Z"),
            instant
    );
}

@Test
void shouldCreateInstantFromMilliseconds() {
    Instant instant = Instant.ofEpochMilli(1735689600123L);

    assertEquals(
            Instant.parse("2025-01-01T00:00:00.123Z"),
            instant
    );
}
```

Hai test dùng số có đơn vị rõ ràng và kiểm tra kết quả bằng Instant chuẩn.

### 13.2. Kiểm thử nanosecond

```java
@Test
void shouldPreserveNanosecondPrecision() {
    Instant instant = Instant.parse("2025-01-01T00:00:00.123456789Z");

    assertEquals(123456789, instant.getNano());
    assertEquals(
            Instant.parse("2025-01-01T00:00:00.123456789Z"),
            instant
    );
}
```

Nếu chuyển sang `Date`, hãy viết test thể hiện rõ mất phần dưới millisecond:

```java
@Test
void convertingToDateLosesSubMillisecondPrecision() {
    Instant original = Instant.parse("2025-01-01T00:00:00.123456789Z");

    Instant restored = Date.from(original).toInstant();

    assertEquals(
            Instant.parse("2025-01-01T00:00:00.123Z"),
            restored
    );
}
```

### 13.3. Kiểm thử Jackson numeric timestamp

Có thể kiểm tra cấu hình đọc integer seconds và milliseconds riêng biệt:

```java
@Test
void shouldReadIntegerAsEpochSecondsWhenConfigured() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .enable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
            .build();

    Instant value = mapper.readValue("1735689600", Instant.class);

    assertEquals(Instant.parse("2025-01-01T00:00:00Z"), value);
}

@Test
void shouldReadIntegerAsEpochMillisWhenConfigured() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
            .build();

    Instant value = mapper.readValue("1735689600000", Instant.class);

    assertEquals(Instant.parse("2025-01-01T00:00:00Z"), value);
}
```

Các test này nên chạy với đúng phiên bản Jackson mà ứng dụng sử dụng vì cấu hình và module có thể thay đổi theo major version.

## 14. Lỗi thường gặp

**Đọc milliseconds như seconds.** Số epoch millisecond thường lớn hơn số epoch second khoảng 1.000 lần. Dùng nhầm `ofEpochSecond()` tạo thời điểm sai rất xa.

**Đọc seconds như milliseconds.** Dùng `ofEpochMilli()` cho số giây tạo thời điểm gần epoch 1970 thay vì thời điểm mong muốn.

**Bỏ phần lẻ khi chuyển seconds.** Chia số millisecond cho 1.000 bằng phép chia nguyên sẽ loại bỏ phần dưới giây. Dùng `Instant.ofEpochMilli()` nếu cần giữ phần millisecond.

**Nhầm nanosecond với epoch nanoseconds.** `Instant.getNano()` trả phần nanosecond trong giây, không phải tổng số nanosecond kể từ 1970. Không ghép nó với `getEpochSecond()` bằng phép nhân tùy tiện nếu chưa xét overflow.

**Cho rằng Date giữ nanosecond.** `Date` chỉ giữ epoch milliseconds. Chuyển `Instant` sang `Date` sẽ làm mất phần nhỏ hơn millisecond.

**Dùng LocalDateTime như một instant.** `LocalDateTime` thiếu timezone/offset; cần ZoneId để xác định một thời điểm tuyệt đối.

**Để consumer đoán đơn vị.** Một field tên `timestamp` không thể hiện rõ seconds hay milliseconds. Hãy dùng ISO-8601 hoặc tên field/schema nói rõ đơn vị.

**Cho rằng WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS áp dụng giống nhau cho mọi kiểu thời gian.** Feature này thuộc đường xử lý Java Time module; `java.util.Date` vẫn dùng epoch milliseconds.

**Chỉ kiểm tra số chữ số để đoán đơn vị.** Số chữ số chỉ là dấu hiệu, không phải hợp đồng. Hãy xác nhận schema hoặc tài liệu producer.

## 15. Quy trình chọn biểu diễn thời gian

Khi thiết kế một property thời gian cho JSON:

1. Xác định dữ liệu là ngày lịch, giờ địa phương hay một instant tuyệt đối.
2. Nếu là instant, ưu tiên `Instant`; nếu cần giữ offset/zone trong hợp đồng, chọn `OffsetDateTime` hoặc `ZonedDateTime` theo ngữ nghĩa.
3. Xác định consumer cần ISO-8601 string, epoch milliseconds, epoch seconds hay seconds+nanos.
4. Ghi rõ đơn vị trong tên field hoặc schema nếu dùng số.
5. Cấu hình `JavaTimeModule` và các feature đọc/ghi numeric timestamp phù hợp với Jackson 2.x.
6. Tránh chuyển qua `Date` nếu cần giữ precision nhỏ hơn millisecond.
7. Không chuyển `LocalDateTime` thành epoch nếu chưa chọn ZoneId và chính sách DST.
8. Kiểm tra độ chính xác xuyên suốt database, serializer, transport và consumer.
9. Viết test cho giá trị có phần lẻ, mốc epoch, timestamp âm nếu có và các trường hợp sai đơn vị.

## 16. Kết luận

Epoch seconds, epoch milliseconds và phần thập phân của giây là những biểu diễn khác nhau của thời gian. Một giây bằng 1.000 milliseconds và 1.000.000.000 nanoseconds; số chữ số phần lẻ quyết định độ phân giải biểu diễn. Trong Java, `Instant` có thể giữ nanosecond, còn `Date` chỉ giữ millisecond. `LocalDateTime` không thể chuyển thành epoch nếu thiếu timezone/offset.

Với Jackson 2.x, Java Time module có các feature điều khiển cách đọc/ghi timestamp số: khi chế độ nanosecond bật, integer timestamp của các kiểu instant-based được hiểu theo giây và có thể dùng phần thập phân để giữ nanosecond; khi tắt, integer timestamp dùng milliseconds. Hãy ưu tiên ISO-8601 cho hợp đồng dễ đọc, hoặc ghi rõ đơn vị nếu dùng số. Kết hợp kiểu Java phù hợp, cấu hình mapper nhất quán và test giá trị biên sẽ tránh phần lớn lỗi lệch thời gian và mất độ chính xác.

## Tài liệu tham khảo

- [Java Instant API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java Date API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html)
- [Jackson Java 8 Date/Time Module](https://github.com/FasterXML/jackson-modules-java8/tree/2.x/datetime)
- [Jackson SerializationFeature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/SerializationFeature.html)
- [Jackson DeserializationFeature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [RFC 3339 — Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339)

