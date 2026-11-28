# Ngày giờ dạng chuỗi hoặc số và tương thích dữ liệu từ hệ thống cũ

Ứng dụng Spring Data Neo4j (SDN) thường phải đọc graph được tạo bởi nhiều phiên bản phần mềm. Một hệ thống cũ có thể lưu thời điểm dưới dạng chuỗi ISO-8601, chuỗi ngày giờ theo định dạng riêng, số epoch milliseconds hoặc số epoch seconds. Ứng dụng mới lại muốn làm việc với Instant, ZonedDateTime, LocalDate hoặc các kiểu temporal native của Neo4j.

Để chuyển đổi an toàn, trước hết phải xác định ý nghĩa của dữ liệu cũ: đó là ngày lịch, giờ địa phương hay một thời điểm tuyệt đối; chuỗi có offset hay không; số nguyên biểu diễn giây hay mili giây. Sau đó chọn converter phù hợp, triển khai khả năng đọc tương thích và chuyển dần dữ liệu sang định dạng chuẩn.

## 1. Vì sao dữ liệu ngày giờ từ hệ thống cũ khó tương thích?

Hai giá trị nhìn giống ngày giờ có thể biểu diễn những ý nghĩa khác nhau:

| Giá trị cũ | Kiểu lưu | Ý nghĩa cần xác định |
|---|---|---|
| 2025-03-15T09:30:00Z | Chuỗi ISO-8601 có Z | Thời điểm UTC |
| 2025-03-15T16:30:00+07:00 | Chuỗi ISO-8601 có offset | Cùng thời điểm với ví dụ UTC phía trên |
| 2025-03-15T16:30:00 | Chuỗi không có offset | Giờ địa phương; cần biết múi giờ nguồn |
| 15/03/2025 16:30:00 | Chuỗi định dạng riêng | Cần biết pattern và múi giờ |
| 1742031000000 | Số epoch milliseconds | Số mili giây kể từ Unix epoch |
| 1742031000 | Số epoch seconds | Số giây kể từ Unix epoch |
| 2025-03-15 | Chuỗi ngày | Ngày lịch, không phải thời điểm |

Nếu coi tất cả các giá trị trên là cùng một kiểu String hoặc Long, ứng dụng có thể đọc sai thời điểm, lệch múi giờ hoặc sai hệ số một nghìn lần. Một lỗi phổ biến là truyền epoch seconds vào converter đang mong đợi epoch milliseconds. Giá trị số vẫn hợp lệ nhưng thời điểm kết quả nằm sai xa trên trục thời gian.

Hệ thống cũ cũng có thể lưu cùng một property bằng nhiều kiểu khác nhau trong graph: một số node có chuỗi, node khác có số nguyên, node mới lại có temporal value native. Khi đó, cần một chiến lược tương thích có kiểm soát thay vì giả định toàn bộ dữ liệu đã được chuẩn hóa.

## 2. Chọn kiểu Java theo ý nghĩa thời gian

Trước khi viết converter, hãy chọn kiểu Java diễn đạt đúng nghiệp vụ:

| Kiểu Java | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| LocalDate | Ngày lịch, không có giờ và múi giờ | Ngày sinh, ngày phát hành |
| LocalTime | Giờ trong ngày, không có ngày và múi giờ | Giờ mở cửa |
| LocalDateTime | Ngày giờ địa phương, không có múi giờ | Giờ hẹn theo lịch tại một địa điểm |
| OffsetDateTime | Ngày giờ kèm offset UTC | Thời điểm có offset như +07:00 |
| ZonedDateTime | Ngày giờ gắn với múi giờ hoặc offset | Lịch cần giữ vùng Asia/Ho_Chi_Minh |
| Instant | Một thời điểm tuyệt đối trên UTC timeline | createdAt, updatedAt, thời điểm sự kiện |
| java.util.Date | Một thời điểm có độ chính xác mili giây | Tương thích API Java cũ |

Không chuyển một chuỗi ngày lịch như 2025-03-15 thành Instant nếu nghiệp vụ chỉ cần ngày. Ngược lại, không dùng LocalDateTime cho thời điểm toàn cầu nếu hệ thống cần so sánh chính xác giữa nhiều múi giờ.

Ví dụ:

```java
public class Event {

    private LocalDate businessDate;

    private LocalDateTime scheduledAtLocal;

    private Instant occurredAt;

    private ZonedDateTime venueTime;
}
```

occurredAt phù hợp với một sự kiện đã xảy ra tại một thời điểm xác định. scheduledAtLocal chỉ có ý nghĩa khi kết hợp với quy tắc múi giờ của địa điểm hoặc người dùng. Nếu cần bảo toàn cả thời điểm lẫn tên vùng múi giờ, dùng ZonedDateTime hoặc lưu vùng múi giờ thành property riêng.

## 3. Ưu tiên temporal type native của Neo4j

Neo4j hỗ trợ các kiểu temporal như DATE, LOCAL TIME, TIME, LOCAL DATETIME và ZONED DATETIME. SDN ánh xạ các kiểu Java thời gian phổ biến sang các kiểu Cypher tương ứng:

| Kiểu Java | Kiểu temporal Neo4j thường dùng |
|---|---|
| LocalDate | DATE |
| LocalTime | LOCAL TIME |
| OffsetTime | TIME |
| LocalDateTime | LOCAL DATETIME |
| ZonedDateTime | ZONED DATETIME |
| Instant, OffsetDateTime | Được SDN chuyển đổi sang kiểu DATETIME phù hợp |

Trong mapping mặc định hiện hành, java.util.Date được lưu dưới dạng chuỗi ISO-8601 theo UTC; @DateLong thay đổi cách lưu thành epoch milliseconds, còn @DateString cho phép khai báo pattern chuỗi tường minh. Hãy kiểm tra bảng chuyển đổi của đúng phiên bản SDN trong dự án vì các quy tắc mặc định và annotation tương thích có thể khác giữa các thế hệ.

Kiểu native có lợi thế vì Neo4j hiểu ngữ nghĩa thời gian. Ứng dụng có thể so sánh, sắp xếp, lọc khoảng và trích xuất thành phần ngày giờ mà không phải parse chuỗi ở mỗi truy vấn.

Ví dụ một entity mới:

```java
@Node("Event")
public class Event {

    @Id
    private String id;

    private Instant occurredAt;

    private LocalDate businessDate;
}
```

Với Instant, ứng dụng có thể ghi và đọc một thời điểm tuyệt đối. Với LocalDate, database lưu một ngày lịch không bị diễn giải thành nửa đêm ở một múi giờ tùy ý.

Không nên tiếp tục lưu ngày giờ dưới dạng chuỗi chỉ vì hệ thống cũ từng làm như vậy. Chuỗi vẫn có thể cần thiết cho một hợp đồng tương thích cụ thể, nhưng temporal native thường là lựa chọn tốt hơn cho dữ liệu mới cần truy vấn theo thời gian.

## 4. Hỗ trợ sẵn cho chuỗi và epoch trong SDN

SDN có các annotation tương thích với cách lưu ngày giờ cũ:

- @DateString: lưu java.util.Date hoặc Instant thành chuỗi theo pattern. Pattern mặc định là dạng ISO-8601 có offset; có thể cấu hình format và zoneId.
- @DateLong: lưu java.util.Date hoặc Instant dưới dạng số epoch milliseconds.

Ví dụ dùng chuỗi ISO-8601:

```java
@Node("LegacyEvent")
public class LegacyEvent {

    @Id
    private String id;

    @DateString
    private Instant occurredAt;
}
```

Ví dụ dùng format riêng của hệ thống cũ:

```java
@Node("ImportedEvent")
public class ImportedEvent {

    @Id
    private String id;

    @DateString(
            format = "dd/MM/yyyy HH:mm:ss",
            zoneId = "Asia/Ho_Chi_Minh")
    private Instant importedAt;
}
```

Ví dụ dùng số epoch milliseconds:

```java
@Node("LegacyEvent")
public class LegacyEvent {

    @Id
    private String id;

    @DateLong
    private Instant occurredAt;
}
```

@DateLong biểu diễn mili giây, không phải giây. Nếu nguồn cũ lưu epoch seconds, không gắn @DateLong rồi kỳ vọng SDN tự nhân một nghìn. Cần converter riêng hoặc chuyển dữ liệu về milliseconds trước khi dùng annotation.

Các annotation này hữu ích khi một property có định dạng cũ nhất quán. Nếu cùng một property chứa lẫn chuỗi ISO, chuỗi format riêng, số giây, số mili giây và temporal native, hãy dùng converter riêng có logic đọc rõ ràng hoặc chuẩn hóa dữ liệu trước.

## 5. Phân biệt epoch seconds và epoch milliseconds

Unix epoch đo thời gian từ 1970-01-01T00:00:00Z. Hai đơn vị phổ biến:

- Epoch seconds: số giây kể từ epoch.
- Epoch milliseconds: số mili giây kể từ epoch.

Ví dụ:

```java
Instant fromSeconds = Instant.ofEpochSecond(1_742_031_000L);

Instant fromMilliseconds = Instant.ofEpochMilli(1_742_031_000_000L);
```

Không thể thay ofEpochSecond bằng ofEpochMilli mà vẫn nhận cùng thời điểm. Giá trị mili giây thường có số chữ số lớn hơn giá trị giây khoảng ba chữ số, nhưng không nên chỉ đoán đơn vị từ độ dài số. Dữ liệu trước năm 1970 có thể âm; dữ liệu thử nghiệm hoặc timestamp ở phạm vi khác có thể phá vỡ quy tắc suy đoán.

Hãy lấy hợp đồng từ hệ thống nguồn hoặc tài liệu migration. Nếu không biết đơn vị, giữ nguyên giá trị, đánh dấu bản ghi cần điều tra và không tự chuyển đổi.

Đối với epoch seconds:

```java
Instant instant = Instant.ofEpochSecond(epochSeconds);
```

Đối với epoch milliseconds:

```java
Instant instant = Instant.ofEpochMilli(epochMillis);
```

Nếu dùng @DateLong, property phải mang giá trị milliseconds theo quy ước của annotation. Nếu hệ thống cũ lưu seconds, có thể dùng Instant.ofEpochSecond(...) trong converter để đổi đúng đơn vị rồi ghi ra temporal native.

## 6. Converter riêng cho một property bằng @ConvertWith

Khi một field cụ thể có định dạng cũ đặc biệt, @ConvertWith cho phép chỉ định Neo4jPersistentPropertyConverter cho đúng property đó. Cách này tránh làm thay đổi cách chuyển đổi của tất cả field Instant trong ứng dụng.

Giả sử createdAt của hệ thống cũ có thể là:

- Chuỗi ISO-8601 có offset.
- Chuỗi địa phương dạng dd/MM/yyyy HH:mm:ss, được xác định theo múi giờ Asia/Ho_Chi_Minh.
- Số epoch milliseconds.
- Temporal ZONED DATETIME của Neo4j sau khi dữ liệu đã được chuẩn hóa.

Converter có thể đọc các dạng cũ và ghi dạng chuẩn mới:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

import org.neo4j.driver.Value;
import org.neo4j.driver.Values;
import org.springframework.data.neo4j.core.convert.Neo4jPersistentPropertyConverter;

public final class LegacyInstantConverter
        implements Neo4jPersistentPropertyConverter<Instant> {

    private static final ZoneId LEGACY_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final DateTimeFormatter LEGACY_FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm:ss");

    @Override
    public Value write(Instant source) {
        if (source == null) {
            return Values.NULL;
        }

        return Values.value(source.atZone(ZoneOffset.UTC));
    }

    @Override
    public Instant read(Value source) {
        if (source == null || source.isNull()) {
            return null;
        }

        Object raw = source.asObject();

        if (raw instanceof String text) {
            try {
                return Instant.parse(text);
            } catch (DateTimeParseException ignored) {
                LocalDateTime local =
                        LocalDateTime.parse(text, LEGACY_FORMAT);
                return local.atZone(LEGACY_ZONE).toInstant();
            }
        }

        if (raw instanceof Number epochMillis) {
            // Chỉ đúng khi hợp đồng dữ liệu xác nhận đơn vị là milliseconds.
            return Instant.ofEpochMilli(epochMillis.longValue());
        }

        if (raw instanceof ZonedDateTime zonedDateTime) {
            return zonedDateTime.toInstant();
        }

        if (raw instanceof OffsetDateTime offsetDateTime) {
            return offsetDateTime.toInstant();
        }

        throw new IllegalArgumentException(
                "Unsupported legacy timestamp value: " + raw.getClass());
    }
}
```

Gắn converter vào property:

```java
@Node("Event")
public class Event {

    @Id
    private String id;

    @ConvertWith(converter = LegacyInstantConverter.class)
    private Instant createdAt;
}
```

Trong ví dụ, converter đọc nhiều dạng dữ liệu cũ nhưng luôn ghi ZONED DATETIME theo UTC. Sau khi một entity được lưu lại, property đó đã chuyển sang dạng chuẩn. Values.NULL được dùng khi ghi giá trị null; khi đọc, converter kiểm tra Value.isNull() trước khi chuyển kiểu.

Ví dụ trên giả định mọi giá trị số là epoch milliseconds. Nếu nguồn cũ dùng seconds, hãy thay nhánh số bằng Instant.ofEpochSecond(...) hoặc tạo converter riêng cho nguồn đó. Nếu cùng property trộn cả seconds và milliseconds mà không có metadata xác định đơn vị, không thể phân biệt chắc chắn chỉ từ kiểu INTEGER.

Converter này là ví dụ cho dữ liệu có hợp đồng đã biết. Khi chuỗi địa phương không có offset, múi giờ LEGACY_ZONE phải là múi giờ thật sự của hệ thống nguồn. Không lấy múi giờ mặc định của máy chạy ứng dụng để parse ngầm.

## 7. Converter toàn cục với Neo4jConversions

Nếu mọi thuộc tính thuộc một kiểu Java đều cần cùng quy tắc chuyển đổi, có thể đăng ký converter toàn cục qua bean Neo4jConversions. Một custom GenericConverter có thể khai báo cặp chuyển đổi giữa kiểu miền và org.neo4j.driver.Value.

Ví dụ cấu hình:

```java
@Configuration
public class Neo4jConversionConfiguration {

    @Bean
    Neo4jConversions neo4jConversions() {
        Set<GenericConverter> converters =
                Set.of(new DomainTimestampConverter());
        return new Neo4jConversions(converters);
    }
}
```

DomainTimestampConverter là converter do ứng dụng triển khai. Với entity property, converter toàn cục cần hỗ trợ cả chiều Java sang Driver Value và chiều Value sang Java. Nếu chỉ dùng để bind tham số cho một số custom query, có thể chỉ cần chiều ghi theo yêu cầu của query.

Hãy thận trọng khi đăng ký converter toàn cục cho String, Long, Date hoặc Instant: nó có thể ảnh hưởng đến nhiều property không liên quan. Với một field legacy cụ thể, @ConvertWith thường an toàn và dễ hiểu hơn. Không đăng ký converter toàn cục chỉ để sửa một cột ngày giờ của một loại node.

## 8. Xử lý múi giờ và dữ liệu không có offset

Chuỗi có offset như 2025-03-15T16:30:00+07:00 đã xác định được thời điểm. Chuỗi không có offset như 2025-03-15T16:30:00 chỉ cho biết giờ trên đồng hồ địa phương. Muốn chuyển thành Instant, phải biết múi giờ nguồn.

Ví dụ cùng một giờ địa phương nhưng hai vùng múi giờ khác nhau sẽ tạo ra hai thời điểm UTC khác nhau:

```java
LocalDateTime local =
        LocalDateTime.of(2025, 3, 15, 16, 30);

Instant vietnamTime = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();

Instant utcTime = local
        .atZone(ZoneOffset.UTC)
        .toInstant();
```

Không thể khôi phục tên vùng múi giờ như Asia/Ho_Chi_Minh từ một chuỗi chỉ có offset +07:00. Offset xác định độ lệch tại thời điểm đó; tên vùng còn mang quy tắc lịch sử và quy tắc thay đổi theo thời gian. Nếu nghiệp vụ cần vùng múi giờ, lưu ZoneId riêng hoặc dùng ZonedDateTime với zone ID.

Với dữ liệu ở vùng có quy tắc daylight saving time, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần khi đồng hồ chuyển đổi. Quy trình migration cần chính sách rõ ràng cho các trường hợp này; không để LocalDateTime.atZone(...) tự quyết định mà không hiểu hành vi mặc định.

## 9. Khảo sát dữ liệu cũ trước khi chuyển đổi

Trước khi cập nhật graph, cần thống kê kiểu và định dạng đang tồn tại. Nếu phiên bản Neo4j hỗ trợ hàm valueType(), có thể thống kê kiểu dữ liệu của property:

```cypher
MATCH (e:Event)
WHERE e.createdAt IS NOT NULL
RETURN valueType(e.createdAt) AS storedType,
       count(*) AS records
ORDER BY records DESC;
```

Lấy mẫu để xác định format:

```cypher
MATCH (e:Event)
WHERE e.createdAt IS NOT NULL
RETURN e.id AS id,
       e.createdAt AS rawValue,
       valueType(e.createdAt) AS storedType
LIMIT 30;
```

Không chỉ thống kê STRING hay INTEGER. Cần xem giá trị mẫu để phân biệt ISO có offset, chuỗi địa phương, chuỗi ngày, epoch seconds và epoch milliseconds. Nếu một property có nhiều định dạng chuỗi, hãy phân nhóm theo nguồn hoặc quy tắc tạo dữ liệu.

Một bảng kiểm kê hữu ích:

| Nhóm dữ liệu | Số lượng | Định dạng | Múi giờ/đơn vị | Cách chuyển |
|---|---:|---|---|---|
| Chuỗi ISO có offset | Ghi nhận thực tế | ISO-8601 | Offset trong chuỗi | Parse sang temporal |
| Chuỗi local datetime | Ghi nhận thực tế | Pattern đã biết | Zone nguồn | Parse rồi gắn zone |
| Số nguyên milliseconds | Ghi nhận thực tế | Epoch milliseconds | UTC | datetime({epochMillis: ...}) |
| Số nguyên seconds | Ghi nhận thực tế | Epoch seconds | UTC | datetime({epochSeconds: ...}) |
| Ngày lịch | Ghi nhận thực tế | yyyy-MM-dd | Không có zone | Chuyển sang DATE |
| Giá trị không hợp lệ | Ghi nhận thực tế | Không xác định | Chưa rõ | Cách ly và xử lý riêng |

Nếu valueType() không có trong phiên bản Neo4j đang dùng, có thể kiểm tra dữ liệu bằng cách đọc mẫu qua ứng dụng hoặc dùng truy vấn phân loại theo nguồn và metadata đã có. Không dựa vào tên property để suy ra kiểu thực tế.

## 10. Chuyển chuỗi hoặc số sang temporal native bằng Cypher

Neo4j có các hàm temporal để tạo giá trị native từ chuỗi hoặc epoch. Cần chọn đúng hàm và đúng đơn vị.

**Chuỗi ISO-8601 có offset:**

```cypher
MATCH (e:Event {id: $id})
SET e.createdAt = datetime(e.createdAt)
RETURN e.createdAt;
```

datetime(string) parse chuỗi biểu diễn ngày giờ hợp lệ theo định dạng temporal mà Neo4j hỗ trợ. Chuỗi có Z hoặc offset giữ đúng ý nghĩa thời điểm.

**Epoch milliseconds:**

```cypher
MATCH (e:Event {id: $id})
SET e.createdAt = datetime({epochMillis: e.createdAt})
RETURN e.createdAt;
```

**Epoch seconds:**

```cypher
MATCH (e:Event {id: $id})
SET e.createdAt = datetime({epochSeconds: e.createdAt})
RETURN e.createdAt;
```

Không thay epochMillis bằng epochSeconds hoặc ngược lại. Cả hai đều nhận số nguyên nhưng kết quả cách nhau hệ số một nghìn.

**Chuỗi chỉ có ngày:**

```cypher
MATCH (e:Event {id: $id})
SET e.businessDate = date(e.businessDate)
RETURN e.businessDate;
```

**Chuỗi ngày giờ địa phương không có offset:**

Nếu dữ liệu nguồn xác nhận thuộc múi giờ Asia/Ho_Chi_Minh, có thể parse thành LOCAL DATETIME rồi gắn timezone:

```cypher
MATCH (e:Event {id: $id})
WITH e, localdatetime(e.createdAt) AS localValue
SET e.createdAt = datetime({
    datetime: localValue,
    timezone: 'Asia/Ho_Chi_Minh'
})
RETURN e.createdAt;
```

Với chuỗi có pattern riêng như dd/MM/yyyy HH:mm:ss, một số phiên bản Neo4j hỗ trợ đối số pattern cho datetime(input, pattern). Hãy kiểm tra tài liệu đúng phiên bản server trước khi dùng. Nếu server không hỗ trợ pattern đó hoặc quy tắc nguồn phức tạp, parse bằng Java converter rồi ghi temporal value đã chuẩn hóa.

## 11. Migration theo từng lô và có thể chạy lại

Với graph lớn, không nên cập nhật toàn bộ node trong một transaction quá lớn. Có thể chia thành các lô nhỏ, mỗi lần xử lý một số node:

```cypher
MATCH (e:Event)
WHERE e.createdAt IS NOT NULL
  AND valueType(e.createdAt) STARTS WITH 'STRING'
WITH e
LIMIT $batchSize
SET e.createdAt = datetime(e.createdAt)
RETURN count(e) AS migrated;
```

Truy vấn trên chỉ phù hợp với nhóm chuỗi ISO mà Neo4j có thể parse trực tiếp. Sau mỗi lần chạy, các node đã đổi sang temporal type không còn thỏa điều kiện kiểu chuỗi, nên có thể chạy lại để xử lý lô tiếp theo. Lặp đến khi migrated bằng 0.

Với epoch milliseconds:

```cypher
MATCH (e:Event)
WHERE e.createdAt IS NOT NULL
  AND valueType(e.createdAt) STARTS WITH 'INTEGER'
WITH e
LIMIT $batchSize
SET e.createdAt = datetime({epochMillis: e.createdAt})
RETURN count(e) AS migrated;
```

Chỉ dùng truy vấn thứ hai nếu toàn bộ nhóm INTEGER đã được xác nhận là milliseconds. Nếu có cả seconds và milliseconds, hãy tách chúng theo nguồn hoặc metadata xác định được. Không chạy cùng một phép chuyển đổi cho cả hai nhóm.

Một migration an toàn nên có các bước:

1. Sao lưu hoặc xác nhận khả năng khôi phục dữ liệu.
2. Thống kê kiểu, format, đơn vị và timezone của dữ liệu hiện tại.
3. Triển khai ứng dụng có thể đọc định dạng cũ và định dạng mới.
4. Chuyển writer mới sang ghi temporal native.
5. Backfill dữ liệu cũ theo từng nhóm và từng lô.
6. Đếm lại kiểu dữ liệu, kiểm tra giá trị không hợp lệ và so sánh mẫu trước/sau.
7. Chỉ ngừng hỗ trợ định dạng cũ sau khi xác nhận không còn bản ghi cần đọc theo format đó.

Nếu cần giữ nguyên giá trị nguồn để đối chiếu, hãy ghi sang property mới như createdAtNative thay vì ghi đè ngay:

```cypher
MATCH (e:Event)
WHERE e.createdAtLegacy IS NOT NULL
  AND e.createdAtNative IS NULL
WITH e
LIMIT $batchSize
SET e.createdAtNative =
    datetime({epochMillis: e.createdAtLegacy})
RETURN count(e) AS migrated;
```

Sau khi ứng dụng mới đọc và ghi ổn định, có thể chuyển caller sang property chuẩn. Chỉ xóa property legacy khi đã qua thời gian kiểm chứng và chính sách lưu trữ cho phép.

## 12. Chiến lược đọc tương thích và ghi chuẩn

Khi nhiều phiên bản ứng dụng cùng hoạt động trong giai đoạn triển khai, có thể áp dụng chiến lược mở rộng rồi thu hẹp:

| Giai đoạn | Cách đọc | Cách ghi |
|---|---|---|
| Trước migration | Đọc định dạng cũ | Ghi định dạng cũ |
| Ứng dụng tương thích được triển khai | Đọc cả cũ và mới | Ghi định dạng chuẩn mới |
| Backfill đang chạy | Đọc cả cũ và mới | Ghi định dạng chuẩn mới |
| Đã xác minh dữ liệu | Chỉ đọc định dạng chuẩn | Ghi định dạng chuẩn |

Nếu dùng converter đọc nhiều kiểu, bảo đảm chiều ghi chỉ tạo một kiểu chuẩn. Đừng để converter tiếp tục ghi chuỗi hoặc số cũ sau khi migration bắt đầu, nếu không số lượng bản ghi legacy có thể tăng trở lại.

Nếu cần chạy song song phiên bản ứng dụng cũ không hiểu temporal native, hãy cân nhắc property mới hoặc dual-write trong một giai đoạn ngắn. Dual-write cần transaction bảo đảm hai property không lệch nhau; cũng cần có ngày kết thúc để tránh duy trì hai mô hình vĩnh viễn.

## 13. Truy vấn và sắp xếp sau khi chuẩn hóa

Khi property đã là temporal native, có thể so sánh trực tiếp theo thời gian:

```cypher
MATCH (e:Event)
WHERE e.createdAt >= datetime($from)
  AND e.createdAt < datetime($to)
RETURN e
ORDER BY e.createdAt;
```

Với tham số Java, truyền temporal value phù hợp từ Driver/SDN thay vì tự format thành chuỗi rồi nối vào Cypher. Khoảng nửa mở [from, to) hữu ích khi lọc theo tháng hoặc ngày: cận dưới được lấy, cận trên không được lấy.

Không nên dùng phép so sánh chuỗi để thay cho so sánh thời gian. Chuỗi có offset khác nhau có thể biểu diễn thứ tự thời gian khác với thứ tự ký tự; format không đồng nhất còn làm kết quả khó dự đoán. Temporal native giúp Neo4j so sánh theo ngữ nghĩa thời gian.

Trong giai đoạn property còn trộn STRING, INTEGER và DATETIME, tránh viết một truy vấn so sánh trực tiếp tất cả các kiểu đó như thể chúng đồng nhất. Hãy chuyển đổi dữ liệu trước hoặc tạo một property chuẩn riêng để truy vấn.

## 14. Kiểm thử converter và migration

Converter ngày giờ cần test cả chiều đọc và ghi. Những trường hợp quan trọng:

- Chuỗi ISO có Z.
- Chuỗi ISO có offset dương hoặc âm.
- Chuỗi local datetime với múi giờ nguồn đã biết.
- Epoch milliseconds và epoch seconds.
- Giá trị trước năm 1970 nếu hệ thống có dữ liệu lịch sử.
- null hoặc property không tồn tại.
- Ngày không hợp lệ hoặc chuỗi sai pattern.
- Giá trị temporal native sau khi backfill.
- Độ chính xác mili giây và nano giây theo yêu cầu.

Ví dụ unit test cho quy tắc epoch:

```java
@Test
void convertsEpochMillisecondsToInstant() {
    long epochMillis = 1_742_031_000_000L;

    Instant result = Instant.ofEpochMilli(epochMillis);

    assertThat(result.toEpochMilli()).isEqualTo(epochMillis);
}

@Test
void convertsEpochSecondsToInstant() {
    long epochSeconds = 1_742_031_000L;

    Instant result = Instant.ofEpochSecond(epochSeconds);

    assertThat(result.getEpochSecond()).isEqualTo(epochSeconds);
}
```

Unit test xác nhận quy tắc Java, nhưng chưa xác minh SDN/Driver mapping. Cần integration test với Neo4j thật hoặc Testcontainers để:

1. Ghi entity có converter.
2. Đọc lại entity và xác nhận thời điểm bằng nhau.
3. Kiểm tra kiểu property trong Neo4j là temporal native khi đó là định dạng ghi chuẩn.
4. Đọc node legacy có chuỗi hoặc số và xác nhận converter tạo đúng Instant.
5. Chạy migration hai lần để bảo đảm truy vấn không chuyển đổi lại bản ghi đã chuẩn hóa.
6. Kiểm tra bản ghi sai format được báo lỗi hoặc đưa vào luồng xử lý riêng, không bị âm thầm thay bằng thời điểm hiện tại.

Đừng chỉ kiểm tra chuỗi hiển thị. Hãy so sánh Instant, epoch value hoặc temporal value sau khi đọc lại để xác nhận đúng thời điểm.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng epoch seconds với @DateLong | Thời điểm sai hệ số một nghìn | Dùng converter seconds hoặc đổi đúng sang milliseconds |
| Coi chuỗi không có offset là UTC | Thời điểm có thể lệch so với hệ thống nguồn | Xác định timezone nguồn trước khi chuyển |
| Dùng LocalDateTime cho một thời điểm toàn cầu | Không thể xác định một instant duy nhất | Dùng Instant, OffsetDateTime hoặc ZonedDateTime |
| Dùng Instant cho ngày lịch | Ngày có thể đổi khi áp dụng timezone | Dùng LocalDate |
| Dùng một DateTimeFormatter cho nhiều format khác nhau | Một số bản ghi parse lỗi hoặc sai ngày | Phân nhóm dữ liệu theo format và converter |
| Đoán seconds/milliseconds theo số chữ số | Có thể phân loại sai dữ liệu lịch sử | Xác nhận hợp đồng nguồn hoặc metadata |
| Converter toàn cục cho một property riêng lẻ | Ảnh hưởng các field khác cùng kiểu Java | Dùng @ConvertWith cho property cụ thể |
| Chuyển đổi toàn bộ graph trong một transaction lớn | Tốn bộ nhớ và thời gian, khó rollback | Chia batch và theo dõi tiến độ |
| Ghi dữ liệu mới theo format cũ trong lúc backfill | Số lượng legacy record tăng lại | Chuyển writer sang format chuẩn trước hoặc đồng bộ dual-write có kiểm soát |
| Xóa giá trị gốc trước khi xác minh | Khó điều tra và khôi phục dữ liệu sai | Giữ raw value hoặc backup đến khi hoàn tất kiểm chứng |

## 16. Checklist tương thích ngày giờ

1. Property biểu diễn ngày lịch, giờ địa phương hay thời điểm tuyệt đối?
2. Dữ liệu nguồn là chuỗi ISO, chuỗi format riêng, epoch seconds hay epoch milliseconds?
3. Chuỗi có offset hoặc zone ID không? Nếu không, timezone nguồn là gì?
4. Có nhiều kiểu dữ liệu hoặc nhiều format trong cùng property không?
5. Có thể dùng LocalDate, Instant hoặc ZonedDateTime native thay cho chuỗi không?
6. @DateLong hoặc @DateString có khớp chính xác định dạng nguồn không?
7. Nếu dùng @ConvertWith, converter có đọc đầy đủ các dạng được hỗ trợ và ghi một dạng chuẩn duy nhất không?
8. Migration có thể chạy lại, chia batch và thống kê số bản ghi đã chuyển không?
9. Có giữ lại giá trị nguồn và xử lý riêng các bản ghi không hợp lệ không?
10. Integration test đã kiểm tra round-trip, timezone, đơn vị epoch và kiểu temporal trong Neo4j chưa?

## 17. Tự kiểm tra

1. Khác biệt giữa LocalDateTime, OffsetDateTime, ZonedDateTime và Instant là gì?
2. @DateLong lưu số epoch theo đơn vị nào?
3. Khi nào nên dùng @DateString thay vì temporal native?
4. Vì sao một chuỗi không có offset không thể tự xác định thành Instant?
5. @ConvertWith khác gì converter đăng ký toàn cục qua Neo4jConversions?
6. Vì sao không thể tự động phân biệt epoch seconds và milliseconds chỉ bằng kiểu Long?
7. Cypher chuyển ISO string sang ZONED DATETIME bằng hàm nào?
8. Khác biệt giữa datetime({epochSeconds: value}) và datetime({epochMillis: value}) là gì?
9. Vì sao nên chuyển dữ liệu theo batch và giữ raw value trong giai đoạn kiểm chứng?
10. Chiến lược đọc tương thích nhưng ghi theo định dạng chuẩn mới giúp migration an toàn như thế nào?

Khi hiểu ý nghĩa của từng kiểu thời gian và đơn vị lưu trữ, người học có thể cấu hình converter cho dữ liệu legacy, đọc được các định dạng cũ trong giai đoạn chuyển tiếp và chuẩn hóa graph sang temporal type native để truy vấn, sắp xếp và quản lý thời gian chính xác hơn trong Spring Data Neo4j.

## Tài liệu tham khảo

- [Spring Data Neo4j — Conversions](https://docs.spring.io/spring-data/neo4j/reference/appendix/conversions.html)
- [Spring Data Neo4j API — DateLong](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/support/DateLong.html)
- [Spring Data Neo4j API — DateString](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/support/DateString.html)
- [Spring Data Neo4j API — Neo4jPersistentPropertyConverter](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/convert/Neo4jPersistentPropertyConverter.html)
- [Neo4j Cypher Manual — Temporal functions](https://neo4j.com/docs/cypher-manual/current/functions/temporal/)
- [Neo4j Cypher Manual — Temporal values](https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/)
