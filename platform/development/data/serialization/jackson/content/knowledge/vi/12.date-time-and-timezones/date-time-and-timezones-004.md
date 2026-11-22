# Lựa chọn chuỗi ngày giờ hoặc dấu thời gian dạng số

## 1. Hai cách biểu diễn thời điểm trong JSON

Khi tuần tự hóa ngày giờ bằng Jackson, ứng dụng thường phải chọn giữa hai dạng JSON:

- **Chuỗi ngày giờ:** thường theo ISO-8601, ví dụ `"2025-03-08T10:15:30Z"` hoặc `"2025-03-08T17:15:30+07:00"`.
- **Dấu thời gian dạng số (numeric timestamp):** một số biểu diễn thời gian theo quy ước của API, ví dụ số giây hoặc mili giây tính từ Unix epoch.

Hai dạng này đều có thể biểu diễn thời gian, nhưng mang thông tin và yêu cầu khác nhau. Chuỗi có thể thể hiện offset, ký hiệu UTC và đôi khi cả múi giờ theo vùng. Timestamp dạng số gọn và thuận tiện cho tính toán, nhưng bên gửi và bên nhận phải thống nhất đơn vị, độ chính xác và cách hiểu giá trị.

JSON không định nghĩa một kiểu ngày giờ riêng. Theo cú pháp JSON, ngày giờ dạng chuỗi chỉ là string và timestamp chỉ là number. Việc số đó là giây, mili giây hay nano giây là quy ước của ứng dụng hoặc hợp đồng API. Vì vậy, không nên chỉ nhìn một con số rồi tự đoán đơn vị.

## 2. Chọn kiểu Java trước khi chọn định dạng JSON

Không phải mọi kiểu ngày giờ Java đều mang cùng ý nghĩa. Jackson có thể ghi chúng thành chuỗi hoặc số, nhưng kiểu Java quyết định thông tin thời gian nào tồn tại trong dữ liệu.

| Kiểu Java | Ý nghĩa | Ví dụ dạng chuỗi |
|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên dòng thời gian, chuẩn hóa theo UTC | `2025-03-08T10:15:30Z` |
| `OffsetDateTime` | Ngày giờ địa phương kèm offset UTC cụ thể | `2025-03-08T17:15:30+07:00` |
| `ZonedDateTime` | Ngày giờ gắn với một múi giờ theo vùng và quy tắc của vùng đó | `2025-03-08T17:15:30+07:00[Asia/Ho_Chi_Minh]` |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương, không có offset hoặc múi giờ | `2025-03-08T17:15:30` |
| `LocalDate` | Ngày lịch, không có giờ và múi giờ | `2025-03-08` |
| `LocalTime` | Giờ trong ngày, không có ngày và múi giờ | `17:15:30` |

Một timestamp dạng epoch biểu diễn một thời điểm tuyệt đối. Vì vậy, nó phù hợp tự nhiên với `Instant`. Nếu chuyển `LocalDateTime` sang số bằng cách tự gắn một múi giờ, ứng dụng đã thêm một quy tắc không có trong giá trị ban đầu. Nếu không biết múi giờ, không thể xác định duy nhất một instant từ `LocalDateTime`.

Tương tự, khi chuyển `ZonedDateTime` thành epoch number, con số chỉ giữ thời điểm trên timeline; thông tin tên vùng như `Asia/Ho_Chi_Minh` không còn nằm trong con số đó. Nếu nghiệp vụ cần giữ vùng múi giờ để áp dụng quy tắc lịch trong tương lai, cần truyền thêm zone ID hoặc dùng dạng chuỗi phù hợp.

## 3. Cấu hình Jackson Java Time

Các kiểu `java.time` được hỗ trợ bởi module `jackson-datatype-jsr310`. Cần có module này trên classpath và đăng ký với mapper. Không nên nhầm việc Jackson nhận diện record hoặc POJO với việc nó tự hỗ trợ mọi kiểu thời gian.

Ví dụ Maven dùng Jackson BOM để căn chỉnh phiên bản:

```xml
<properties>
    <jackson.version>2.17.2</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
</dependencies>
```

`2.17.2` là phiên bản minh họa được ghim cố định để ví dụ có môi trường xác định, không phải tuyên bố đó là phiên bản mới nhất. Trong dự án thực tế, hãy dùng phiên bản đã được dự án lựa chọn và giữ các artifact Jackson đồng bộ qua BOM.

Đăng ký module tường minh:

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

Ở cấu hình trên, `JavaTimeModule` cung cấp serializer/deserializer cho các kiểu Java Time. `WRITE_DATES_AS_TIMESTAMPS` được tắt để chọn dạng chuỗi cho những kiểu thời gian mà module hỗ trợ định dạng chuỗi.

Nếu bật `WRITE_DATES_AS_TIMESTAMPS`, cách biểu diễn phụ thuộc kiểu Java. Các kiểu đại diện một thời điểm như `Instant` thường được ghi thành số; các kiểu local như `LocalDate`, `LocalTime` và `LocalDateTime` không tự xác định được một epoch instant nên thường được ghi thành mảng thành phần ngày giờ khi chế độ timestamp bật.

## 4. Ghi ngày giờ thành chuỗi ISO-8601

Chuỗi ISO-8601 thường dễ đọc, dễ kiểm tra trong log và có thể mang thông tin UTC hoặc offset. Với `Instant`, dạng chuỗi tiêu biểu kết thúc bằng `Z` để biểu thị UTC.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DateStringExample {
    public record Event(
            String name,
            Instant occurredAt,
            OffsetDateTime receivedAt,
            ZonedDateTime scheduledAt
    ) {
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .build();

        Event event = new Event(
                "payment-created",
                Instant.parse("2025-03-08T10:15:30Z"),
                OffsetDateTime.parse("2025-03-08T17:15:30+07:00"),
                ZonedDateTime.of(
                        2025, 3, 8, 17, 15, 30, 0,
                        ZoneId.of("Asia/Ho_Chi_Minh")
                )
        );

        String json = mapper.writerWithDefaultPrettyPrinter()
                .writeValueAsString(event);
        System.out.println(json);
    }
}
```

Với các kiểu Java Time tương ứng, đầu ra có dạng chuỗi ngày giờ. `Instant` được biểu diễn theo UTC; `OffsetDateTime` mang offset; `ZonedDateTime` có thể biểu diễn thêm zone ID theo formatter và serializer được dùng. Hãy kiểm tra chính xác định dạng của kiểu đang sử dụng bằng một ví dụ thực tế của phiên bản Jackson trong dự án.

Chuỗi thường là lựa chọn tốt cho API công khai vì con người có thể đọc được và thông tin offset hiển thị ngay. Nó cũng giúp tránh sự mơ hồ giữa epoch seconds và epoch milliseconds. Tuy nhiên, bên nhận vẫn cần parse đúng kiểu và đúng định dạng đã thống nhất.

## 5. Ghi ngày giờ thành timestamp dạng số

Để ghi các kiểu thời gian theo dạng số, bật `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS`:

```java
ObjectMapper numericMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

Instant instant = Instant.parse("2025-03-08T10:15:30Z");
String json = numericMapper.writeValueAsString(instant);
System.out.println(json);
```

Khi dùng JavaTimeModule, số timestamp cho các kiểu instant-based được tính từ Unix epoch (`1970-01-01T00:00:00Z`). Cần xác định thêm cách biểu diễn độ chính xác bằng `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS`:

| Thiết lập | Dạng số thường dùng cho `Instant` |
|---|---|
| `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS` bật | Số giây từ epoch, có thể có phần thập phân biểu diễn nano giây |
| `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS` tắt | Số nguyên mili giây từ epoch |

Ví dụ cấu hình timestamp theo giây với độ chính xác nano:

```java
ObjectMapper secondsMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .enable(SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();
```

Ví dụ cấu hình timestamp theo mili giây:

```java
ObjectMapper millisMapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();
```

Không nên chỉ bật `WRITE_DATES_AS_TIMESTAMPS` rồi giả định mọi số đều là milliseconds. Đơn vị số phụ thuộc thêm feature về nano giây và kiểu Java được serialize.

### Local date/time khi timestamp được bật

`LocalDate`, `LocalTime` và `LocalDateTime` không đại diện cho một instant tuyệt đối. Khi `WRITE_DATES_AS_TIMESTAMPS` bật, JavaTimeModule thường ghi chúng thành mảng thành phần, ví dụ:

```json
[2025, 3, 8]
```

cho một `LocalDate`, hoặc dạng tương tự:

```json
[2025, 3, 8, 17, 15, 30]
```

cho một `LocalDateTime` không có phần nano giây. Vì vậy, “bật timestamp” không đồng nghĩa mọi kiểu ngày giờ đều thành một con số epoch. Nếu API yêu cầu số epoch, hãy dùng một kiểu biểu diễn thời điểm tuyệt đối như `Instant` hoặc chuyển đổi rõ ràng bằng một zone đã thống nhất.

## 6. Đọc timestamp: thống nhất giây hay mili giây

Chiều deserialization cũng cần quy ước đơn vị. `DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS` điều khiển cách Jackson diễn giải timestamp dạng số nguyên cho các kiểu Java Time:

- Bật: số nguyên được hiểu là số giây từ epoch.
- Tắt: số nguyên được hiểu là số mili giây từ epoch.
- Giá trị số có phần thập phân được hiểu là giây có phần lẻ biểu diễn độ chính xác nhỏ hơn một giây.

Để đọc số nguyên milliseconds, có thể cấu hình:

```java
ObjectMapper millisReader = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();

Instant instant = millisReader.readValue(
        "1741428930000",
        Instant.class
);
```

Để đọc số nguyên seconds:

```java
ObjectMapper secondsReader = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS)
        .build();

Instant instant = secondsReader.readValue(
        "1741428930",
        Instant.class
);
```

Hai ví dụ dùng hai con số khác nhau về đơn vị nhưng cùng biểu diễn thời điểm tương ứng. Nếu producer gửi milliseconds còn consumer hiểu seconds, thời điểm sẽ lệch rất lớn. Đây là lỗi hợp đồng dữ liệu, không phải lỗi cú pháp JSON.

## 7. Độ chính xác: mili giây và nano giây

Các lớp Java Time như `Instant` lưu độ chính xác đến nano giây. Hệ thống khác có thể chỉ hỗ trợ mili giây hoặc thậm chí chỉ hỗ trợ giây. Khi chuyển định dạng, phần độ chính xác vượt quá khả năng của bên nhận có thể bị mất.

Ví dụ, một instant có thể chứa:

```java
Instant instant = Instant.parse("2025-03-08T10:15:30.123456789Z");

System.out.println(instant.getEpochSecond()); // Số giây nguyên từ epoch
System.out.println(instant.getNano());       // 123456789
System.out.println(instant.toEpochMilli());  // Mili giây; phần dưới mili giây bị bỏ
```

Nếu dùng timestamp mili giây, phần `456789` nano giây còn lại sau mili giây không thể được giữ trong một số nguyên milliseconds. Nếu nghiệp vụ cần độ chính xác nano, hãy dùng dạng số giây có phần thập phân hoặc chuỗi ISO-8601 có phần lẻ đủ chữ số, và kiểm tra bên nhận có giữ được độ chính xác đó không.

Một lưu ý khi trao đổi với JavaScript: kiểu `Number` thường dùng số dấu phẩy động IEEE-754 double. Epoch milliseconds hiện tại nằm trong vùng có thể biểu diễn số nguyên chính xác, nhưng epoch nanoseconds là số rất lớn và có thể vượt giới hạn số nguyên chính xác của JavaScript. Đừng truyền epoch nanoseconds dưới dạng JSON number cho consumer dùng JavaScript nếu cần bảo toàn chính xác từng nano giây; cân nhắc chuỗi hoặc ISO-8601.

## 8. Múi giờ, offset và ý nghĩa của dữ liệu

Chuỗi và timestamp có cách thể hiện thông tin múi giờ khác nhau:

### `Instant`: thời điểm tuyệt đối

`Instant` không lưu múi giờ địa phương. Nó đại diện một điểm trên timeline và thường được ghi ra chuỗi UTC có hậu tố `Z`. Nếu muốn hiển thị theo giờ Việt Nam, chuyển đổi khi trình bày:

```java
Instant instant = Instant.parse("2025-03-08T10:15:30Z");
ZonedDateTime vietnamTime = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
System.out.println(vietnamTime);
```

### `OffsetDateTime`: giữ offset

`OffsetDateTime` lưu ngày giờ cùng offset, ví dụ `+07:00`. Offset xác định quan hệ với UTC tại thời điểm đó nhưng không chứa toàn bộ quy tắc lịch sử hoặc tương lai của một vùng địa lý.

### `ZonedDateTime`: giữ zone ID

`ZonedDateTime` có thể giữ zone ID như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`, cùng quy tắc của vùng. Điều này quan trọng khi tính lịch trong vùng có thay đổi giờ mùa hè (DST). Nếu chỉ lưu epoch timestamp, zone ID sẽ mất; nếu cần tái hiện lịch địa phương trong tương lai, lưu thêm zone ID.

### `LocalDateTime`: không tự có múi giờ

`LocalDateTime` chỉ nói “ngày X lúc giờ Y” mà không nói đó là giờ ở đâu. Không nên tự coi nó là UTC hoặc giờ máy chủ. Khi cần chuyển thành `Instant`, phải chỉ định `ZoneId` và xử lý các thời điểm mơ hồ hoặc không tồn tại do quy tắc DST:

```java
LocalDateTime local = LocalDateTime.of(2025, 3, 8, 17, 15);
ZonedDateTime zoned = local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
Instant instant = zoned.toInstant();
```

Việc chuyển đổi trên là một quyết định nghiệp vụ. Cùng một `LocalDateTime` có thể ánh xạ sang instant khác nhau ở các zone khác nhau.

## 9. Định dạng riêng bằng `@JsonFormat`

Nếu API yêu cầu chuỗi có định dạng riêng, có thể dùng `@JsonFormat` trên property thay vì thay đổi toàn bộ mapper:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDateTime;

public record Appointment(
        String title,
        @JsonFormat(
                shape = JsonFormat.Shape.STRING,
                pattern = "yyyy-MM-dd HH:mm:ss"
        )
        LocalDateTime startsAt
) {
}
```

Định dạng này tạo chuỗi như `"2025-03-08 17:15:30"`. Vì `LocalDateTime` không có zone, pattern không thể tự xác định múi giờ. Nếu cần offset, hãy dùng kiểu như `OffsetDateTime` và một pattern có trường offset, hoặc dùng định dạng ISO mặc định.

`@JsonFormat` hữu ích khi một property có hợp đồng riêng. Nếu mọi ngày giờ trong API cần cùng định dạng, cấu hình thống nhất ở mapper hoặc serializer phù hợp sẽ dễ duy trì hơn. Tránh đặt pattern tùy ý ở nhiều property mà không ghi rõ quy ước timezone và độ chính xác.

## 10. So sánh chuỗi và timestamp

| Tiêu chí | Chuỗi ISO-8601 | Timestamp dạng số |
|---|---|---|
| Dễ đọc trong log | Cao | Thấp hơn |
| Đơn vị | Thể hiện qua ký hiệu/định dạng | Phải quy định giây, mili giây hoặc quy ước khác |
| Offset UTC | Có thể thể hiện trực tiếp | Không thể hiện trong một số epoch đơn lẻ |
| Zone ID | Có thể thể hiện với định dạng phù hợp | Không được giữ trong số epoch |
| Tính toán thời gian | Cần parse thành kiểu thời gian | Thuận tiện sau khi thống nhất đơn vị |
| Độ chính xác | Có thể biểu diễn phần lẻ đến nano giây | Phụ thuộc cách mã hóa và kiểu số của consumer |
| Tương thích API | Phổ biến với API web | Phổ biến trong hệ thống đo thời gian và sự kiện |

Không có dạng nào luôn tốt hơn. Chuỗi phù hợp khi API cần tính rõ ràng, khả năng đọc và thông tin offset. Timestamp phù hợp khi hai bên đã thống nhất đơn vị và muốn biểu diễn thời điểm dưới dạng số dễ tính toán.

## 11. Những lỗi thường gặp

### Nhầm epoch seconds với epoch milliseconds

`1741428930` và `1741428930000` có độ lớn khác nhau vì một số là giây, số còn lại là mili giây. Hãy ghi rõ đơn vị trong tài liệu API và cấu hình reader tương ứng.

### Bật timestamp rồi mong mọi kiểu thành một số

Các kiểu local như `LocalDate` và `LocalDateTime` thường được ghi thành mảng thành phần khi `WRITE_DATES_AS_TIMESTAMPS` bật. Muốn một epoch number, cần kiểu biểu diễn thời điểm tuyệt đối như `Instant` hoặc phép chuyển đổi có zone rõ ràng.

### Dùng `LocalDateTime` cho thời điểm tuyệt đối

`LocalDateTime` không chứa offset hay zone. Nếu dữ liệu là thời điểm một giao dịch thực sự xảy ra, `Instant` thường phù hợp hơn. Nếu dữ liệu là giờ hẹn tại một địa điểm, cần xác định zone của địa điểm.

### Mất thông tin vùng múi giờ khi ghi số

Epoch timestamp không giữ tên vùng như `Asia/Ho_Chi_Minh`. Nếu cần tính lịch tương lai theo quy tắc của vùng, hãy lưu zone ID riêng.

### Mất độ chính xác khi chuyển sang milliseconds

`Instant.toEpochMilli()` chỉ giữ độ chính xác mili giây. Nếu cần nano giây, phải chọn cách biểu diễn và consumer có thể giữ được phần lẻ đó.

### Chỉ cấu hình chiều ghi mà quên chiều đọc

`WRITE_DATES_AS_TIMESTAMPS` và `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS` điều khiển serialization; `READ_DATE_TIMESTAMPS_AS_NANOSECONDS` điều khiển cách đọc số nguyên timestamp. Hãy thử nghiệm hai chiều bằng payload thực tế.

## 12. Thiết kế hợp đồng API rõ ràng

Trước khi chọn chuỗi hay số, hãy trả lời các câu hỏi sau trong hợp đồng dữ liệu:

1. Trường biểu diễn ngày lịch, giờ địa phương hay một thời điểm tuyệt đối?
2. Nếu là timestamp số, đơn vị là giây hay mili giây? Có phần lẻ không?
3. Độ chính xác cần đến giây, mili giây hay nano giây?
4. Nếu là chuỗi, định dạng có phải ISO-8601 không? Offset có bắt buộc không?
5. Có cần giữ zone ID như `Asia/Ho_Chi_Minh` để tái hiện quy tắc lịch không?
6. Bên nhận dùng Jackson, JavaScript hay một nền tảng khác? Kiểu số của consumer có giữ được độ chính xác cần thiết không?
7. Cả chiều serialize và deserialize đã dùng cùng quy ước chưa?

Một hợp đồng ví dụ cho sự kiện có thể ghi:

```json
{
  "occurredAt": "2025-03-08T10:15:30.123456789Z"
}
```

với quy ước `occurredAt` là instant UTC theo ISO-8601, tối đa chín chữ số phần lẻ. Một hợp đồng dùng milliseconds có thể ghi:

```json
{
  "occurredAt": 1741428930123
}
```

nhưng phải ghi rõ con số là epoch milliseconds. Tên field hoặc tài liệu schema nên làm rõ ý nghĩa, ví dụ `occurredAtEpochMillis`, nếu điều đó giúp tránh nhầm lẫn.

## 13. Kết luận

Jackson có thể ghi ngày giờ thành chuỗi ISO-8601 hoặc timestamp dạng số thông qua cấu hình của JavaTimeModule. Chuỗi thường dễ đọc và có thể giữ offset hoặc zone theo kiểu dữ liệu và formatter; timestamp gọn và thuận tiện tính toán nhưng cần thống nhất đơn vị, độ chính xác và ý nghĩa timezone. `WRITE_DATES_AS_TIMESTAMPS` chọn dạng số, `WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS` quyết định độ chính xác/đơn vị của số khi ghi, còn `READ_DATE_TIMESTAMPS_AS_NANOSECONDS` ảnh hưởng cách diễn giải timestamp số nguyên khi đọc. Hãy chọn kiểu Java đúng với ý nghĩa dữ liệu (`Instant`, `OffsetDateTime`, `ZonedDateTime` hoặc `LocalDateTime`), cấu hình rõ cả hai chiều và mô tả quy ước trong hợp đồng API.
