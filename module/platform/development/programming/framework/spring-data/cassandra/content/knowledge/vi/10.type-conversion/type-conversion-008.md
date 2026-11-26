# Ảnh hưởng của chuyển đổi đến điều kiện truy vấn

Khi làm việc với **Apache Cassandra** qua **Spring Data Cassandra**, ứng dụng thường không dùng trực tiếp các kiểu CQL trong mọi lớp Java. Chẳng hạn, nghiệp vụ biểu diễn trạng thái bằng enum, mã khách hàng bằng value object, hoặc thời điểm bằng `Instant`; trong bảng Cassandra chúng được lưu dưới dạng `text`, `uuid`, `timestamp` hay `date`. **Chuyển đổi kiểu (type conversion)** nối hai thế giới này với nhau.

Một lỗi khó phát hiện xuất hiện khi **giá trị được chuyển đổi lúc ghi khác cách giá trị được chuyển đổi lúc truy vấn**. Entity có thể được lưu thành công nhưng `WHERE` không tìm thấy hàng; hoặc truy vấn thất bại do tham số có kiểu CQL không phù hợp. Bài thuộc chương **Chuyển đổi kiểu** của module **SPRING_DATA_CASSANDRA**, tập trung vào ảnh hưởng của converter đối với equality, range, partition key, clustering key, repository, `CassandraTemplate`, prepared statement và hiệu năng.

## 1. Hai hướng chuyển đổi, một hợp đồng dữ liệu

Hãy phân biệt **giá trị miền nghiệp vụ** và **giá trị được lưu trong Cassandra**:

~~~text
                         ĐƯỜNG GHI
Java EventType.PAID --------------------> CQL text 'paid'
                    writing converter

                         ĐƯỜNG ĐỌC
CQL text 'paid' ------------------------> Java EventType.PAID
                    reading converter

                         ĐƯỜNG TRUY VẤN
Java EventType.PAID --> CQL bind value 'paid' --> WHERE event_type = ?
~~~

Khi xây dựng `WHERE`, giá trị bound phải có **kiểu CQL và biểu diễn lưu trữ phù hợp**. Nếu writing converter lưu `'paid'` nhưng đường truy vấn lại gửi `'PAID'` vào cột `text`, truy vấn đẳng thức có thể trả về **không hàng nào** dù dữ liệu vẫn tồn tại.

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| Java domain type | Giá trị xuất hiện trong code là `EventType`, `UUID`, `Instant` hay value object nào? |
| CQL column type | Schema khai báo `text`, `uuid`, `date`, `timestamp`, `decimal`…? |
| Writing conversion | Java được biến thành giá trị CQL nào khi lưu? |
| Reading conversion | Giá trị CQL được biến lại thành kiểu Java nào khi đọc? |
| Query parameter conversion | Ai chuyển tham số `WHERE` trước khi bind: Spring Data, driver hay code của ứng dụng? |
| Query semantics | Cassandra so sánh **giá trị đã lưu** theo quy tắc của kiểu CQL nào? |

**Lưu ý quan trọng:** converter không phải hàm tự động được Cassandra thực thi bên trong `WHERE`. Cassandra so sánh các giá trị CQL; việc đổi kiểu diễn ra ở phía ứng dụng/driver trước khi truy vấn được gửi hoặc khi kết quả được ánh xạ trở lại Java.

## 2. Ví dụ xuyên suốt: truy vấn sự kiện theo tenant, ngày và loại

Giả sử API cần trả về **20 sự kiện mới nhất của một tenant trong một ngày, thuộc một loại sự kiện đã chọn**. Bảng được thiết kế theo đúng truy vấn:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS commerce_ks.events_by_tenant_day_type (
    tenant_id   uuid,
    event_day   date,
    event_type  text,
    occurred_at timestamp,
    event_id    uuid,
    details     text,
    PRIMARY KEY ((tenant_id, event_day), event_type, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    event_type ASC,
    occurred_at DESC,
    event_id DESC
);
~~~

Ở đây:

- **Partition key:** `(tenant_id, event_day)`. Cần biết đầy đủ cả hai giá trị để đọc một partition cụ thể.
- **Clustering columns:** `event_type`, `occurred_at`, `event_id`. Trong cùng partition, hàng được nhóm theo loại sự kiện rồi sắp xếp theo thời gian giảm dần trong từng loại.
- **Giá trị cột `event_type`:** lưu bằng `text` chữ thường, ví dụ `'created'`, `'paid'`, `'cancelled'`.

Truy vấn hợp lệ theo khóa:

~~~sql
SELECT event_type, occurred_at, event_id, details
FROM commerce_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type = ?
LIMIT 20;
~~~

Nếu muốn lọc thêm thời điểm, có thể dùng range trên clustering column `occurred_at` sau điều kiện bằng trên `event_type`:

~~~sql
SELECT event_type, occurred_at, event_id
FROM commerce_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 20;
~~~

**Đánh đổi của bảng:** truy vấn “20 sự kiện mới nhất **không phân biệt loại**” không nhận được thứ tự thời gian toàn cục chỉ bằng cách đọc bảng này, vì `event_type` đứng trước `occurred_at` trong clustering key. Đó là vấn đề thiết kế truy vấn, không phải lỗi có thể sửa bằng converter.

Tên datacenter `dc1` và RF = 3 ở đây chỉ minh họa; triển khai thực tế phải sử dụng topology, cấu hình replication và keyspace phù hợp.

## 3. Chuyển enum Java thành text CQL: một ví dụ dễ sai

Ở tầng Java, ta muốn dùng enum thay vì gửi chuỗi tùy ý:

~~~java
public enum EventType {
    CREATED,
    PAID,
    CANCELLED
}
~~~

Hợp đồng lưu trữ quyết định **text chữ thường**. Ta viết một hàm dùng chung để chuyển đổi; không để các tầng tự chọn viết hoa hay viết thường:

~~~java
import java.util.Locale;

public final class EventTypeStorage {
    private EventTypeStorage() {}

    public static String toCql(EventType value) {
        return value.name().toLowerCase(Locale.ROOT);
    }

    public static EventType fromCql(String value) {
        return EventType.valueOf(
                value.toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Hai hàm này chỉ minh họa bộ mã hóa **cho các giá trị hợp lệ**. Trong hệ thống thực, cần xác định rõ cách xử lý `null`, mã chưa được hỗ trợ hoặc giá trị không hợp lệ, thay vì âm thầm đổi giá trị lạ thành một giá trị nghiệp vụ khác.

Sử dụng Spring Data `@WritingConverter` và `@ReadingConverter` để ánh xạ vào/ra CQL:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EventTypeWriteConverter
        implements Converter<EventType, String> {
    @Override
    public String convert(EventType source) {
        return EventTypeStorage.toCql(source);
    }
}

@ReadingConverter
public class EventTypeReadConverter
        implements Converter<String, EventType> {
    @Override
    public EventType convert(String source) {
        return EventTypeStorage.fromCql(source);
    }
}
~~~

Đăng ký converter vào cấu hình Spring Data Cassandra, theo API tương thích với phiên bản dự án:

~~~java
@Configuration
public class CassandraConversionConfig {

    @Bean
    CassandraCustomConversions cassandraCustomConversions() {
        return new CassandraCustomConversions(
            List.of(
                new EventTypeWriteConverter(),
                new EventTypeReadConverter()
            )
        );
    }
}
~~~

Trong ví dụ trên, các import của `Configuration`, `Bean`, `List` và `CassandraCustomConversions` được lược bỏ cho ngắn gọn. Mục đích của `CassandraCustomConversions` là để **Spring Data mapping** biết cặp chuyển đổi. Đối với dự án thật, cần đối chiếu constructor/configuration extension point theo phiên bản Spring Data/Boot, tránh tạo hai bean cạnh tranh hoặc làm mất các custom converter đã có.

**Vì sao hai chiều phải đồng bộ?** Nếu ghi `'paid'` mà reading converter chỉ chấp nhận `'PAID'`, đọc entity có thể lỗi chuyển đổi. Ngược lại, nếu chỉ custom đọc mà quên custom ghi, enum có thể được ghi với biểu diễn mặc định khác mong muốn. Hãy kiểm thử round-trip thay vì dựa vào giả định về enum mặc định của thư viện.

## 4. Entity mapping: kiểu Java không đổi schema CQL

Để Spring Data mapping vào bảng trên, một primary key class rút gọn có thể là:

~~~java
@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "event_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @CassandraType(type = CassandraType.Name.TEXT)
    @PrimaryKeyColumn(
        name = "event_type", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING)
    private EventType eventType;

    @PrimaryKeyColumn(
        name = "occurred_at", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 4,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor, getter/setter, equals/hashCode phù hợp.
}

@Table("events_by_tenant_day_type")
public class EventRow {
    @PrimaryKey
    private EventKey key;

    @Column("details")
    private String details;
}
~~~

Các import và thành phần Java cơ bản được lược bỏ. `@CassandraType(type = CassandraType.Name.TEXT)` giúp diễn đạt kiểu CQL mong muốn cho thuộc tính Java không phải `String`; custom converter quyết định **giá trị** chữ thường khi Spring Data thực hiện chuyển đổi. Phải xác minh mapping này hoạt động với phiên bản Spring Data Cassandra cụ thể, nhất là khi domain type nằm trong primary key tổng hợp.

**Không thể chỉ đổi kiểu Java để đổi schema đã có.** Nếu bảng khai báo `event_type text`, Cassandra vẫn yêu cầu giá trị kiểu CQL `text`. Chuyển field Java sang enum không khiến column trên cluster đổi thành kiểu CQL mới. Nếu thay đổi cách mã hóa giá trị của **clustering/partition key**, có thể phải di chuyển hoặc ghi lại dữ liệu và cập nhật mọi đường truy vấn.

## 5. Converter ảnh hưởng tới tham số `WHERE` như thế nào?

Giả sử một hàng được lưu với `event_type = 'paid'`. Hai truy vấn này **không tương đương**:

~~~sql
-- Tìm đúng theo hợp đồng lưu trữ:
SELECT *
FROM commerce_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type = 'paid'
LIMIT 20;

-- Có thể không khớp dữ liệu vì CQL text phân biệt chữ hoa/thường:
SELECT *
FROM commerce_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type = 'PAID'
LIMIT 20;
~~~

Đừng nhầm **tên enum Java** với **giá trị text CQL**. Cột kiểu `text` được so sánh theo giá trị lưu trữ; Cassandra không tự gọi converter Java trên literal `'PAID'`.

**Các đường thực thi có hành vi chuyển đổi khác nhau:**

| Đường truy cập | Ai chuẩn bị giá trị so sánh? | Lưu ý |
| --- | --- | --- |
| Repository thao tác với mapped entity/key | Spring Data mapping/conversion theo API | Thử nghiệm với converter và khóa thực tế |
| Repository method với `@Query` và tham số đơn giản | Cơ chế binding của Spring Data, tùy parameter mapping và version | Tránh giả định mọi enum/raw value luôn được custom convert |
| `CassandraTemplate` với query object | Tầng mapping có thể chuyển giá trị theo field metadata | Kiểm tra CQL/bind thực tế và cách chỉ định tên cột/property |
| Java Driver `CqlSession`/prepared statement trực tiếp | Driver codec và **ứng dụng** | Không tự dùng Spring Data custom converters |
| Literal viết thẳng trong CQL | Developer | Không có chuyển đổi kiểu Java |

Do đó, khi cần bảo đảm giá trị đúng, có thể **chủ động chuyển sang kiểu lưu trữ** ở ranh giới của một query viết tay. Đặc biệt với những query dùng driver trực tiếp, không nên truyền enum vào parameter kiểu `text` rồi kỳ vọng driver biết converter của Spring Data.

## 6. Repository: bind giá trị đã chuẩn hóa theo hợp đồng CQL

Ví dụ repository trả về các sự kiện của một tenant/ngày/loại:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("""
        SELECT * FROM events_by_tenant_day_type
        WHERE tenant_id = ?0
          AND event_day = ?1
          AND event_type = ?2
        LIMIT 20
        """)
    List<EventRow> recentByType(
        UUID tenantId,
        LocalDate eventDay,
        String storedEventType
    );
}
~~~

Service chịu trách nhiệm đưa `EventType` thành `String` theo đúng hợp đồng:

~~~java
@Service
public class EventQueryService {
    private final EventRepository repository;

    public EventQueryService(EventRepository repository) {
        this.repository = repository;
    }

    public List<EventRow> recent(
            UUID tenantId,
            LocalDate day,
            EventType eventType) {
        return repository.recentByType(
            tenantId, day, EventTypeStorage.toCql(eventType)
        );
    }
}
~~~

Ở đây, method repository nhận `String` vì cột Cassandra là `text`. Ta **tái sử dụng duy nhất** hàm mã hóa mà writing converter gọi, nên đường ghi và đường truy vấn không lệch cách viết hoa/thường. Đây là lựa chọn rõ ràng đối với truy vấn CQL được viết tay; nếu method nhận enum trực tiếp, cần kiểm tra cách version Spring Data bind enum với custom converter trong tình huống cụ thể.

Code dùng Java text block (Java 15+), cần import/constructor phù hợp; trên Java cũ, thay bằng chuỗi nối thông thường. Ví dụ giả định keyspace mặc định là `commerce_ks`; nếu không, dùng tên bảng đầy đủ hoặc cấu hình keyspace tương ứng.

**Lưu ý về ý nghĩa truy vấn:** parameter được chuyển đổi chính xác **không khắc phục** việc thiếu `tenant_id` hoặc `event_day`. Cassandra vẫn đòi điều kiện phù hợp partition key, rồi mới xét clustering key và giá trị so sánh.

## 7. CassandraTemplate và CqlSession: kiểm tra tầng nào thực hiện conversion

Với `CassandraTemplate`, ứng dụng có thể xây query object sử dụng `Criteria` và entity mapping. Ví dụ minh họa:

~~~java
Query query = Query.query(
    Criteria.where("tenant_id").is(tenantId),
    Criteria.where("event_day").is(day),
    Criteria.where("event_type")
            .is(EventTypeStorage.toCql(eventType))
).limit(20);

List<EventRow> rows = cassandraTemplate.select(query, EventRow.class);
~~~

Tên lớp và import của `Query`, `Criteria`, `CassandraTemplate` phụ thuộc API Spring Data tương ứng. Trong ví dụ này ta **chủ động cung cấp giá trị `text` đã chuẩn hóa**, giúp mục đích truy vấn rõ ràng; vẫn cần kiểm thử việc Spring Data map tên field/tên cột và bound type với phiên bản thực tế.

Đối với Java Driver, không có chuyện driver tự gọi `EventTypeWriteConverter` được đăng ký trong Spring Data. Cần chuyển đổi trước:

~~~java
PreparedStatement prepared = session.prepare("""
    SELECT event_type, occurred_at, event_id, details
    FROM commerce_ks.events_by_tenant_day_type
    WHERE tenant_id = ? AND event_day = ? AND event_type = ?
    LIMIT 20
    """);

BoundStatement bound = prepared.bind(
    tenantId,
    day,
    EventTypeStorage.toCql(eventType)
);

ResultSet result = session.execute(bound);
~~~

Trong đoạn trên, `session` là `CqlSession`; `tenantId` là `UUID`, `day` là `LocalDate`, và tham số cuối là `String`. Driver bind chúng theo các codec tương thích với `uuid`, `date`, `text`. Nếu cột CQL là `uuid` mà ứng dụng gửi đối tượng tùy biến không có codec phù hợp, việc bind có thể thất bại **trước khi truy vấn chạy**.

**Phân biệt hai lớp:** Spring Data **converter** ánh xạ giá trị miền nghiệp vụ; Java Driver **codec** mã hóa/giải mã kiểu Java được driver hỗ trợ sang kiểu CQL. Một custom converter của Spring Data không tự trở thành driver codec, và đăng ký driver codec cũng không tự sửa mọi mapping Spring Data.

## 8. Chuyển đổi ảnh hưởng cả equality và range

Điều kiện `WHERE col = ?` và `WHERE col >= ?` có yêu cầu khác nhau. Với equality, cần **biểu diễn chuẩn hóa ổn định**; với range, phép chuyển đổi còn cần **bảo toàn thứ tự** nếu muốn ý nghĩa so sánh ở CQL khớp ý nghĩa ở Java.

Ví dụ một hệ thống muốn lưu số lượng:

| Giá trị logic | Lưu dạng số CQL | Lưu dạng text không chuẩn hóa |
| --- | --- | --- |
| 2 | `2` | `'2'` |
| 10 | `10` | `'10'` |
| 100 | `100` | `'100'` |

So sánh theo kiểu số có thứ tự `2 < 10 < 100`. So sánh từ điển của chuỗi không thể mặc định đồng nhất với thứ tự số: chẳng hạn `'10'` đứng trước `'2'` theo thứ tự chuỗi. Vì vậy, nếu có nhu cầu range query số, **ưu tiên cột CQL kiểu số thích hợp**. Không chỉ thêm converter `Integer -> String` và mong phép `>` sẽ có cùng ý nghĩa.

Tương tự:

- Lưu thời điểm dưới dạng `timestamp` phù hợp hơn chuỗi ngày giờ không nhất quán nếu cần so sánh khoảng thời gian.
- Mã phiên bản như `v2`, `v10` nếu được lưu `text` không mặc nhiên có thứ tự semantic version.
- Chuỗi ngày kiểu `'dd/MM/yyyy'` không phù hợp để so sánh khoảng theo thứ tự từ điển; dùng `date` hoặc cách mã hóa có quy tắc, được kiểm thử.
- Nếu biến đổi dữ liệu trước khi lưu là **không đơn điệu** (hash, mã hóa tùy ý, rút gọn), một range query trên giá trị biến đổi có thể mất ý nghĩa.

**CQL vẫn giới hạn cấu trúc WHERE.** Kể cả khi converter bảo toàn thứ tự, Cassandra chỉ hỗ trợ range trong những trường hợp phù hợp partition/clustering key hoặc index và loại truy vấn được phiên bản cluster hỗ trợ. Converter không mở khóa các truy vấn lọc tùy ý như hệ quan hệ.

## 9. Timestamps, timezone và bucket ngày

Một lỗi phổ biến khác là convert thời điểm nhưng **đánh mất múi giờ hoặc độ chính xác**. Ví dụ CQL khai báo:

~~~sql
occurred_at timestamp,
event_day   date
~~~

Trong Java, chọn `Instant` cho thời điểm tuyệt đối và `LocalDate` cho bucket ngày:

~~~java
Instant occurredAt = incomingEvent.occurredAt();
LocalDate eventDay = occurredAt
        .atZone(ZoneOffset.UTC)
        .toLocalDate();
~~~

Khi ghi, writer sử dụng `eventDay` tính theo **UTC**. Khi truy vấn, reader cũng phải tính bucket bằng **cùng quy tắc**. Nếu writer dùng ngày UTC nhưng reader lấy ngày theo múi giờ địa phương, một sự kiện gần 00:00 có thể nằm trong partition khác so với nơi reader tìm.

**Thời điểm truy vấn range:** chuyển thời gian đầu/cuối khoảng thành cùng một cơ sở, thường dùng `Instant` UTC:

~~~java
Instant from = requestStart.atZone(zone).toInstant();
Instant to   = requestEnd.atZone(zone).toInstant();
// Xử lý khoảng [from, to) và xác định các event_day giao nhau.
~~~

Với CQL `timestamp`, hãy chú ý độ chính xác lưu trữ của Cassandra/driver có thể ở mức **mili giây**, trong khi Java `Instant` chứa nano giây. Hai giá trị Java trông rất gần nhau không nhất thiết còn chính xác từng nano giây sau round-trip. Equality chính xác theo timestamp phải được kiểm chứng; khi hợp lý, dùng khoảng `>= from AND < to` và chuẩn hóa độ chính xác theo hợp đồng dữ liệu.

**Đừng nhầm lỗi conversion với lỗi partition:** dù bind timestamp đúng, truy vấn thiếu thành phần partition key vẫn có thể bị Cassandra từ chối hoặc phải quét dữ liệu.

## 10. Chuyển đổi khóa: yêu cầu tính tất định cao hơn

Đối với **partition key** hoặc **clustering key**, tính nhất quán của converter đặc biệt quan trọng. Khóa tham gia xác định partition, vị trí dữ liệu và hàng duy nhất.

Một converter dùng để tạo khóa nên đáp ứng:

1. **Tất định:** cùng một giá trị miền nghiệp vụ luôn tạo cùng giá trị CQL, không phụ thuộc thời gian, locale hệ điều hành hay state ngẫu nhiên.
2. **Ổn định giữa các phiên bản:** việc thay đổi format lưu trữ phải có kế hoạch migration và tương thích đọc/ghi.
3. **Không gây collision ngoài chủ đích:** hai giá trị miền khác nhau không nên vô tình biến thành cùng một khóa CQL.
4. **Đúng kiểu CQL:** một khóa `uuid` phải được bind đúng dạng mà driver/Cassandra chấp nhận, không lẫn sang `text`.
5. **Giữ quy tắc chuẩn hóa:** nếu ID được quy định không phân biệt chữ hoa/thường, cả đường ghi và đường truy vấn phải cùng quy tắc; nếu ID phân biệt chữ hoa/thường, không được tự ý lowercase.

Ví dụ nguy hiểm: trước đây converter lưu `ORDER_PAID` thành `'paid'`; bản mới đổi thành `'payment_completed'` nhưng chỉ triển khai converter mới. Các hàng cũ vẫn mang clustering value `'paid'`, còn query mới chỉ tìm `'payment_completed'`. Một số dữ liệu bỗng “biến mất” khỏi kết quả mà không hề bị xóa.

Với trạng thái **có thể thay đổi theo thời gian**, nếu nó nằm trong primary key thì thay đổi trạng thái cũng đồng nghĩa **thay đổi khóa hàng**. Cassandra không tự “di chuyển hàng” giữa clustering key/partition key chỉ nhờ set property Java; thiết kế nghiệp vụ có thể cần ghi hàng mới, loại bỏ hàng cũ và xử lý nhất quán liên quan. Cân nhắc bảng đọc riêng hoặc event có loại bất biến nếu yêu cầu nghiệp vụ khác.

## 11. Null, invalid values và conversion một chiều

Không nên để converter tự động “chữa” dữ liệu không hợp lệ theo cách âm thầm thay đổi ý nghĩa truy vấn.

| Tình huống | Hậu quả có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Writing converter trả `null` cho khóa | Không thể tạo/bind primary key hợp lệ | Validate sớm; không coi null là một key bình thường |
| Reading converter không hiểu giá trị cũ | Query chạy nhưng materialize entity thất bại | Có chiến lược tương thích dữ liệu V1/V2 hoặc migration |
| Chuẩn hóa mất thông tin | Hai khóa khác nhau trùng cùng text | Chỉ chuẩn hóa khi phù hợp định nghĩa domain identity |
| Enum mới nhưng service cũ chưa biết | Service cũ đọc data mới rồi lỗi | Thiết kế rollout tương thích và kiểm thử cả hai phiên bản |
| Query viết CQL literal khác writing converter | Kết quả rỗng dù hàng còn trong bảng | Dùng chung codec/chuẩn hóa khi tạo query |
| Chỉ đăng ký reading converter | Ghi và truy vấn có thể dùng format khác | Xác minh cả ghi, đọc, bind và round-trip |

Đối với giá trị `null`, Spring Data hoặc driver có thể xử lý trước khi gọi converter tùy API; đừng đặt nghiệp vụ quan trọng vào giả định “converter luôn được gọi cả khi null”. Với cột khóa, hãy xác thực giá trị **trước khi xây query hoặc entity**.

## 12. Hiệu năng: converter không thay đổi data model

Type conversion có chi phí CPU ở tầng Java và ảnh hưởng đến số byte truyền qua driver, nhưng phần lớn chi phí Cassandra vẫn gắn với **partition key, phạm vi hàng đọc, tombstone, consistency, paging và tải replica**.

Ví dụ:

~~~sql
-- Phù hợp với khóa: tenant/day, rồi event_type.
SELECT event_id, occurred_at
FROM commerce_ks.events_by_tenant_day_type
WHERE tenant_id = ? AND event_day = ? AND event_type = ?
LIMIT 20;

-- Không có tenant/day, không phù hợp với bảng theo partition này.
SELECT event_id
FROM commerce_ks.events_by_tenant_day_type
WHERE event_type = 'paid';
~~~

Chuyển `EventType.PAID -> 'paid'` thành công không làm truy vấn thứ hai trở nên định tuyến chính xác. Dùng `ALLOW FILTERING` cũng không phải cách sửa data model khi workload lớn.

Một số điểm đo hiệu năng:

- **Đúng partition trước:** bảo đảm điều kiện `WHERE` sử dụng đủ partition key; chọn clustering columns theo mẫu range/order.
- **Giới hạn số hàng:** `LIMIT` và paging theo driver; không coi page size là cơ chế sửa partition quá lớn.
- **Đo kích thước và phân bố:** khi converter mã hóa một object thành text lớn, kích thước lưu trữ và truyền tải có thể tăng.
- **Chọn tính nhất quán:** RF và consistency level ảnh hưởng replica cần phản hồi, không làm giá trị converter tự động chuẩn hóa.
- **Tránh converter nặng trong hot path:** mã hóa/parse lặp lại với kích thước lớn cần được benchmark; tránh lookup mạng hoặc thao tác blocking trong converter.
- **Theo dõi lỗi parsing:** lỗi mapping ở một phần tử của kết quả có thể khiến cả pipeline repository/reactive thất bại.

Khi dùng `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate`, converter vẫn chạy trong quá trình đọc/ghi. Trả `Mono`/`Flux` không làm một converter CPU-heavy tự động trở nên rẻ, cũng không làm CQL hỗ trợ thêm điều kiện truy vấn.

## 13. Kiểm thử đầu cuối cho một custom converter

Việc test riêng hai hàm `toCql` và `fromCql` là cần thiết nhưng chưa đủ. Hãy kiểm tra từ **ghi thật đến truy vấn thật** trên môi trường test có schema giống production:

1. **Schema:** xác nhận `event_type` là `text` và nằm trong clustering key đúng thứ tự; entity mapping phù hợp.
2. **Round-trip:** ghi một entity có `EventType.PAID`, đọc theo đầy đủ primary key; giá trị Java trả về vẫn là `PAID`.
3. **Query predicate:** gọi repository query với `EventTypeStorage.toCql(PAID)`; xác minh tìm thấy hàng đã ghi.
4. **Negative case:** thử literal `'PAID'` trong CQL và xác minh kỳ vọng không khớp `'paid'` (trong dataset kiểm soát).
5. **Driver bind:** chuẩn bị CQL với `?`, kiểm tra bind lần lượt `UUID`, `LocalDate`, `String` đúng kiểu.
6. **Range:** dùng `Instant` và khoảng `[from, to)`; kiểm tra mốc đúng đầu/cuối và ranh giới ngày UTC.
7. **Phiên bản:** đọc dữ liệu từ converter cũ bằng code mới; xử lý giá trị không còn nằm trong enum.
8. **Paging:** kiểm tra trang tiếp theo với cùng câu CQL và parameter; paging state phải gắn với cùng truy vấn, không đổi cách convert giữa các trang.

Test nên xác nhận **giá trị CQL thực được lưu**, không chỉ so sánh hai object Java đã qua cùng một converter. Ví dụ đọc trực tiếp bằng driver từ bảng để kiểm tra `event_type = 'paid'` thật sự được ghi.

### Ma trận kiểm tra nhanh

| Test | Input Java | Dạng CQL mong đợi | Kết quả |
| --- | --- | --- | --- |
| Ghi loại sự kiện | `EventType.PAID` | `'paid'` | Ghi thành công |
| Đọc entity | `'paid'` | `EventType.PAID` | Round-trip đúng |
| Query theo type | `PAID` qua hàm encode | `WHERE event_type = 'paid'` | Tìm thấy hàng |
| Query không encode | Literal `'PAID'` | Không khớp `'paid'` | Không tìm thấy hàng phù hợp |
| Query thiếu partition key | Chỉ event type | Không thể định tuyến một partition | Phải thiết kế lại đường truy cập |
| Query timestamp | `Instant` UTC | Bind `timestamp` đúng độ chính xác | Lọc đúng khoảng |

## 14. Các sai lầm thường gặp

| Sai lầm | Điều cần hiểu đúng |
| --- | --- |
| “Converter được áp dụng tự động cho mọi dấu `?`.” | Chỉ khi **đường thực thi** có tích hợp mapping/conversion tương ứng; driver trực tiếp không dùng Spring Data converter. |
| “Enum `PAID` và text `'paid'` luôn bằng nhau.” | CQL so sánh giá trị text đã lưu; chữ hoa/thường có thể làm khác kết quả. |
| “Converter có thể đổi partition key mà không ảnh hưởng dữ liệu cũ.” | Giá trị key sau conversion quyết định vị trí logic; đổi encoding cần migration hoặc chiến lược tương thích. |
| “Lưu số thành text vẫn range-query như số.” | Thứ tự text khác thứ tự số; cần chọn CQL type phù hợp. |
| “`@Query` là CQL nên converter luôn được áp dụng lên literal.” | Literal nằm trong CQL không đi qua converter Java. |
| “Converter giúp truy vấn `WHERE` theo mọi field.” | Cassandra vẫn có các quy tắc partition/clustering/index. |
| “Reactive repository sẽ tự sửa lỗi convert.” | Reactive thay mô hình I/O, không sửa dữ liệu/key/schema. |
| “Chỉ cần test converter class là đủ.” | Cần kiểm tra path ghi, path đọc và **bound parameter** thực tế. |

## 15. Tự kiểm tra

**Câu 1.** Converter ghi `OrderStatus.PAID` thành `'paid'`. Một câu `@Query` hard-code `WHERE status = 'PAID'` có chắc tìm ra hàng không?

**Đáp án:** Không. Text value có phân biệt hoa/thường; literal không tự qua converter Java. Query phải dùng đúng representation đã lưu, ví dụ `'paid'`.

**Câu 2.** Vì sao writing converter cho partition key phải tất định và ổn định khi deploy phiên bản mới?

**Đáp án:** Vì kết quả conversion tham gia xác định khóa/partition và cách truy vấn tìm hàng. Thay encoding mà không migration khiến reader mới tìm theo key khác với dữ liệu cũ.

**Câu 3.** Một ứng dụng lưu giá tiền dưới dạng text `'2'` và `'10'`. Có thể dùng so sánh từ điển để bảo đảm `2 < 10` không?

**Đáp án:** Không. Thứ tự chuỗi không mặc nhiên giống thứ tự số; nên lưu kiểu số CQL phù hợp với truy vấn range.

**Câu 4.** Dùng `CqlSession` trực tiếp và bind một Java enum vào cột `text`. Driver có tự tìm `@WritingConverter` đã đăng ký với Spring Data không?

**Đáp án:** Không. Phải bind dạng Java được driver codec hỗ trợ (ví dụ `String` đã chuẩn hóa) hoặc có cơ chế codec/chuẩn bị tham số riêng phù hợp.

**Câu 5.** Converter đã đổi giá trị đúng, nhưng CQL chỉ có `WHERE event_type = ?` trên bảng `events_by_tenant_day_type`. Vì sao query vẫn sai?

**Đáp án:** Bảng có partition key `(tenant_id, event_day)`; chỉ điều kiện theo clustering column không chỉ ra partition, nên query không phù hợp access pattern. Conversion không thay đổi quy tắc phân vùng của Cassandra.

---

**Ghi nhớ:** chuyển đổi kiểu làm thay đổi **biểu diễn giá trị** mà Cassandra nhận khi lưu và so sánh. Với `WHERE`, cần dùng đúng kiểu CQL, cùng quy tắc encode như khi ghi; với **range** còn phải bảo toàn ngữ nghĩa thứ tự, với **partition/clustering key** còn phải bảo đảm tính tất định và tương thích phiên bản. Spring Data Cassandra giúp mapping nhưng không thay thế thiết kế bảng theo truy vấn, chuẩn hóa tham số, paging và kiểm thử CQL thực tế.
