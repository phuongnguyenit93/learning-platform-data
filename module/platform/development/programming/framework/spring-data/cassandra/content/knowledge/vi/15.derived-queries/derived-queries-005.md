# IN, CONTAINS và phạm vi từ khóa được hỗ trợ

Trong **Spring Data Cassandra**, ta có thể khai báo các method như `findByKeyTenantIdAndKeyEventDay(...)` trên interface repository, sau đó để Spring Data **phân tích tên method** và xây câu truy vấn CQL tương ứng. Cơ chế này gọi là **derived queries** (truy vấn dẫn xuất). Những từ khóa như **`In`**, **`Contains`** và **`ContainsKey`** rất tiện, nhưng có một ranh giới quan trọng: **việc Spring Data nhận ra từ khóa không có nghĩa Apache Cassandra sẽ thực thi được hoặc thực thi hiệu quả câu CQL đó**.

Bài học thuộc chương **Truy vấn dẫn xuất** của module **SPRING_DATA_CASSANDRA**. Ta sẽ phân biệt cú pháp method với toán tử CQL, minh họa `IN` trên clustering column, `CONTAINS` trên set/list/map, `CONTAINS KEY` trên map, các giới hạn về partition key và index, rồi xác định khi nào nên chuyển sang `@Query`, `CassandraTemplate` hoặc thiết kế bảng khác. Ví dụ dùng Spring Data Cassandra và Java Driver tương thích với Spring Boot 3.x; danh sách từ khóa và cách ánh xạ chính xác cần được đối chiếu với phiên bản thư viện đang dùng.

## 1. Derived query hoạt động như thế nào?

Ví dụ:

~~~java
List<EventRow> findByKeyTenantIdAndKeyEventDay(
        UUID tenantId, LocalDate eventDay);
~~~

Tên method được phân tích thành:

~~~text
findBy | TenantId | And | EventDay
  |        |                |
  |        +--- property ---+----> điều kiện lọc theo property
  |
  +--> yêu cầu truy vấn tìm bản ghi
~~~

Với entity mapping phù hợp, ý định CQL là:

~~~sql
SELECT *
FROM events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?;
~~~

Lợi ích: giảm việc viết CQL lặp lại, giữ method ngắn và dễ đọc với các truy vấn đơn giản. Tuy nhiên có **hai lớp kiểm tra khác nhau**:

1. **Spring Data parsing/mapping:** tên method có dùng keyword và property hợp lệ không; các tham số có phù hợp với cơ chế chuyển đổi và binding của phiên bản hiện tại không?
2. **Cassandra query validation/execution:** câu CQL được tạo có hợp lệ theo partition key, clustering key, index, dữ liệu và các giới hạn của cluster không?

Một method có thể compile và repository khởi tạo được nhưng **chỉ lỗi khi query chạy**; hoặc query chạy được trên dữ liệu ít nhưng rất chậm khi cluster có nhiều partition. Derived query không phải trình tối ưu hóa thay thế thiết kế bảng.

## 2. Schema dùng xuyên suốt bài học

Giả sử ứng dụng quản lý sự kiện của từng tenant theo ngày. Người dùng thường xem sự kiện trong một ngày và có thể lọc theo loại; một số màn hình thử nghiệm còn muốn lọc nhãn trong collection.

~~~sql
CREATE KEYSPACE IF NOT EXISTS app_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS app_ks.events_by_tenant_day_type (
    tenant_id   uuid,
    event_day   date,
    event_type  text,
    occurred_at timestamp,
    event_id    uuid,
    tags        set<text>,
    attributes  map<text, text>,
    description text,
    PRIMARY KEY (
        (tenant_id, event_day),
        event_type, occurred_at, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_type ASC,
    occurred_at DESC,
    event_id DESC
);
~~~

| Thành phần | Vai trò trong bảng |
| --- | --- |
| `(tenant_id, event_day)` | **Composite partition key**, xác định partition của một tenant/ngày |
| `event_type` | Clustering column đầu tiên, nhóm sự kiện theo loại trong partition |
| `occurred_at` | Clustering column thứ hai, sắp xếp mới nhất trước trong từng loại |
| `event_id` | Clustering column thứ ba, giúp phân biệt sự kiện có cùng thời điểm |
| `tags set<text>` | Tập nhãn non-frozen, có thể dùng toán tử CQL `CONTAINS` trong điều kiện được Cassandra cho phép |
| `attributes map<text, text>` | Thuộc tính mở rộng; có thể kiểm tra key hoặc value theo các toán tử collection thích hợp |
| `description text` | Thuộc tính thường, không hỗ trợ tìm substring bằng `CONTAINS` collection |

Ví dụ này chọn `event_type` làm clustering column **có chủ đích** để minh họa `IN`. Điều đó cũng có hệ quả: truy vấn “sự kiện mới nhất, không phân biệt loại” không tự có thứ tự thời gian tổng thể trong partition, vì `event_type` được sắp trước `occurred_at`.

Tên datacenter `dc1` và RF = 3 chỉ là giả định minh họa; cluster thực tế phải có topology và replication phù hợp. Trong production, schema cần được quản lý bằng migration CQL có kiểm soát, không mặc định tạo/sửa bảng mỗi lần khởi động.

## 3. Entity và lớp khóa tổng hợp

Với bảng có nhiều cột tạo primary key, ví dụ sử dụng một lớp khóa `EventKey` để khớp rõ ràng giữa ID của repository và cấu trúc CQL:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.Table;

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

    @PrimaryKeyColumn(
        name = "event_type", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING)
    private String eventType;

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

    // Constructor, getters/setters, equals/hashCode cho kiểu khóa.
}

@Table("events_by_tenant_day_type")
public class EventRow {

    @PrimaryKey
    private EventKey key;

    @Column("tags")
    private Set<String> tags;

    @Column("attributes")
    private Map<String, String> attributes;

    @Column("description")
    private String description;

    // Constructor, getters/setters và các thành phần mapping cần thiết.
}
~~~

Mã Java được rút gọn để tập trung vào mapping; khi triển khai cần tách class vào các file phù hợp và bổ sung constructor/accessor. Do entity có thuộc tính `key` kiểu `EventKey`, derived method phải biểu diễn **đường dẫn property lồng nhau** (ví dụ `findByKeyTenantIdAndKeyEventDay(...)`) theo cơ chế phân tích property path của Spring Data. Nếu parser phiên bản dự án gặp tên nhập nhằng, có thể dùng dấu `_` để chỉ ranh giới đường dẫn theo quy tắc query derivation, hoặc dùng `@Query` với CQL tường minh.

Trong Java, `key.tenantId` ánh xạ tới cột CQL `tenant_id`; `key.eventDay` ánh xạ `event_day`. **Tên method dựa trên property Java**, còn CQL sử dụng tên cột sau mapping. Vì thế đừng đặt method theo thói quen dùng nguyên tên cột CQL.

## 4. Từ khóa In: nhiều giá trị cho cùng một điều kiện

Ví dụ repository:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    List<EventRow> findByKeyTenantIdAndKeyEventDayAndKeyEventTypeIn(
        UUID tenantId,
        LocalDate eventDay,
        Collection<String> eventTypes
    );
}
~~~

Ở đây `EventKey` chính là kiểu ID đã khai báo bằng `@PrimaryKeyClass`, được sử dụng nhất quán trong `CassandraRepository<EventRow, EventKey>`. Tên method có các đoạn `KeyTenantId`, `KeyEventDay`, `KeyEventType` vì chúng đi qua property `key` của entity.

Tên method được hiểu là:

~~~text
findBy
  TenantId = ?
  AND EventDay = ?
  AND EventType IN (...)
~~~

Ý định CQL:

~~~sql
SELECT *
FROM app_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type IN ?;
~~~

Các phiên bản driver/CQL hỗ trợ bind một collection vào marker `IN ?` ở những trường hợp thích hợp. Cũng có thể gặp CQL biểu diễn dạng `IN (?, ?, ...)`, tùy API và cách query được xây dựng. **Điều quan trọng** là danh sách giá trị được bind, không phải nối thủ công thành CQL string.

Vì `tenant_id` và `event_day` đã xác định **một partition**, còn `event_type` là clustering column đầu tiên, `IN` có ý nghĩa truy cập nhiều nhóm loại sự kiện **trong partition đó**.

### Khác biệt giữa In và Equals

| Derived method | Ý định CQL | Phạm vi dữ liệu |
| --- | --- | --- |
| `findByKeyTenantIdAndKeyEventDayAndKeyEventType(...)` | `event_type = ?` | Một loại trong một partition |
| `findByKeyTenantIdAndKeyEventDayAndKeyEventTypeIn(...)` | `event_type IN ?` | Một số loại trong một partition |
| `findByKeyEventTypeIn(...)` | `event_type IN ?`, thiếu partition key | Không phù hợp bảng đã thiết kế; có thể bị từ chối |

**Không mặc định `IN` luôn “rẻ hơn nhiều lần SELECT”.** Nếu danh sách có hàng trăm hoặc hàng nghìn giá trị, coordinator vẫn phải xử lý nhiều nhánh và nhiều kết quả; độ trễ, heap, kích thước response và paging có thể tăng. Giới hạn số phần tử đầu vào, kiểm tra empty collection và xác định khi nào nên chia nhỏ request.

### IN trên partition key có đánh đổi khác

Ví dụ nếu một bảng khác chỉ có `customer_id uuid PRIMARY KEY` thì điều kiện `customer_id IN (...)` có thể tìm nhiều partition. Đây là dạng **fan-out**: Cassandra phải tiếp xúc với các token/replica tương ứng, không phải một phép truy cập duy nhất đến tất cả giá trị. Với composite partition key, các quy tắc `IN` cũng bị giới hạn bởi cấu trúc khóa và phiên bản CQL.

Không coi mọi danh sách ID đưa vào `findByIdIn(...)` là một query hiệu quả. Khi muốn truy cập hàng loạt hàng thuộc nhiều partition, cần đặt giới hạn rõ ràng hoặc tổ chức các request theo partition/độ đồng thời phù hợp.

## 5. Từ khóa Contains: phần tử trong collection, không phải substring

Trong CQL, `CONTAINS` dùng cho **membership trong collection**:

~~~sql
-- Một giá trị có thuộc set tags không?
SELECT *
FROM app_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND tags CONTAINS 'important';
~~~

Về ý định, derived method có thể được biểu diễn:

~~~java
List<EventRow> findByKeyTenantIdAndKeyEventDayAndTagsContains(
    UUID tenantId,
    LocalDate eventDay,
    String tag
);
~~~

Nó khác hoàn toàn với ý định “chuỗi `description` chứa một từ nào đó”. Cassandra không tự hiểu `Contains` trên `String` như truy vấn SQL `LIKE '%term%'`. Nếu cần tìm kiếm văn bản theo substring/full-text, thường phải chọn index/search engine hoặc data model phù hợp, không dùng `findByDescriptionContains(...)` rồi giả định sẽ có chức năng như trong JPA.

### Cassandra có chấp nhận câu CONTAINS không?

**Nhận diện keyword khác với khả năng thực thi.** `tags` là một cột set thông thường, không nằm trong primary key. Trong nhiều cấu hình Cassandra, truy vấn `tags CONTAINS ?` cần index phù hợp hoặc một cách lọc được phép; có đủ partition key **chưa tự bảo đảm** predicate trên collection được chấp nhận hay tối ưu.

Cassandra có các cơ chế index cho collection, nhưng cú pháp và năng lực phụ thuộc phiên bản (ví dụ secondary index, SAI). Hãy kiểm tra khả năng hỗ trợ của cluster, kích thước tập dữ liệu, độ chọn lọc của tag và tác động tới write path trước khi thêm index.

**Không nên tự gắn `ALLOW FILTERING` vào mọi derived query** để vượt lỗi. Nếu cho phép lọc với tập dữ liệu lớn, Cassandra có thể phải đọc nhiều hàng rồi loại bỏ kết quả không khớp, dẫn đến độ trễ/tombstone/IO cao. Đối với đường đọc nóng theo tag, phần tiếp theo trình bày cách tạo bảng theo truy vấn thay vì bắt Cassandra lọc cột tùy ý.

### Contains có thể dùng với collection nào?

| Kiểu CQL | Mệnh đề CQL | Ý nghĩa |
| --- | --- | --- |
| `set<text>` | `tags CONTAINS 'vip'` | Set có phần tử `'vip'` |
| `list<text>` | `labels CONTAINS 'vip'` | List có phần tử `'vip'` |
| `map<text, text>` | `attributes CONTAINS 'mobile'` | Map có ít nhất một **value** bằng `'mobile'` |
| `text` | Không dùng `CONTAINS` collection để tìm substring | Không phải SQL `LIKE`/full-text search |

Truy vấn membership của collection phải được Cassandra hỗ trợ về index/filtering như đã lưu ý; kiểu dữ liệu chỉ cho biết **ngữ nghĩa toán tử**, không bảo đảm hiệu năng.

## 6. ContainsKey: kiểm tra khóa trong map

Map phân biệt **key** và **value**. Ví dụ:

~~~text
attributes = {
  "channel": "mobile",
  "region": "apac"
}
~~~

Hai CQL có ý nghĩa khác nhau:

~~~sql
-- Kiểm tra có một KEY tên "channel".
SELECT *
FROM app_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND attributes CONTAINS KEY 'channel';

-- Kiểm tra có một VALUE là "mobile".
SELECT *
FROM app_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND attributes CONTAINS 'mobile';
~~~

Ví dụ tên method biểu đạt ý định tương ứng:

~~~java
List<EventRow> findByKeyTenantIdAndKeyEventDayAndAttributesContainsKey(
    UUID tenantId,
    LocalDate eventDay,
    String attributeKey
);

List<EventRow> findByKeyTenantIdAndKeyEventDayAndAttributesContains(
    UUID tenantId,
    LocalDate eventDay,
    String attributeValue
);
~~~

**Lưu ý phiên bản:** cơ chế phân tích `ContainsKey` và những phép toán collection đặc thù cần được kiểm tra trong **danh sách supported query keywords của Spring Data Cassandra version dự án**. Nếu phiên bản hiện tại không hỗ trợ sinh CQL đúng như mong muốn, dùng `@Query`/`CqlTemplate` với CQL tường minh; đừng đổi tên method một cách đoán mò.

Ngoài việc hiểu đúng toán tử, cả hai truy vấn vẫn đối diện bài toán **index hoặc filtering** nếu `attributes` chỉ là cột thường. Index key và index value cho map không đồng nghĩa và phải được cấu hình riêng theo khả năng của Cassandra version.

## 7. Phạm vi keyword: có phần chung với Spring Data, nhưng không phải JPA

Spring Data có cách phân tích query method khá thống nhất ở cấp framework, nhưng **từng datastore chỉ hỗ trợ một phần từ khóa và biểu thức**. Cassandra không hỗ trợ toàn bộ các phép lọc/sắp xếp giống SQL hoặc JPQL.

Nhóm keyword thường hữu ích khi mapping sang CQL, với điều kiện truy vấn hợp lệ theo khóa và phiên bản:

| Nhóm ý định | Ví dụ tên method | CQL dự kiến | Điều kiện quan trọng |
| --- | --- | --- | --- |
| Đẳng thức | `findByKeyTenantIdAndKeyEventDay` | `tenant_id = ? AND event_day = ?` | Cung cấp đầy đủ partition key |
| IN | `findByKeyTenantIdAndKeyEventDayAndKeyEventTypeIn` | `event_type IN ...` | `IN` phải đặt trên cột phù hợp và có danh sách được giới hạn |
| Lớn hơn | `findByKeyTenantIdAndKeyEventDayAndKeyEventTypeAndKeyOccurredAtGreaterThan` | `occurred_at > ?` | Range sau các phần khóa đứng trước đã được ràng buộc thích hợp |
| Lớn hơn/bằng | `...OccurredAtGreaterThanEqual` | `occurred_at >= ?` | Dùng cùng điều kiện khóa |
| Nhỏ hơn | `...OccurredAtLessThan` | `occurred_at < ?` | Dùng cùng điều kiện khóa |
| Nhỏ hơn/bằng | `...OccurredAtLessThanEqual` | `occurred_at <= ?` | Dùng cùng điều kiện khóa |
| Membership | `...TagsContains` | `tags CONTAINS ?` | Cột collection, index/filtering phù hợp |
| Map key | `...AttributesContainsKey` | `attributes CONTAINS KEY ?` | Hỗ trợ keyword/index phụ thuộc phiên bản |

Những tên method ở cột ví dụ rút gọn bằng dấu `...` chỉ để trình bày, **không phải cú pháp Java hợp lệ để chép nguyên**. Với các từ khóa như `Between`, `After`, `Before`, `IsNull`, `NotIn`, `Like`, `StartingWith`, `EndingWith`, `IgnoreCase`, `OrderBy` hoặc `Or`, **không được giả định** Spring Data Cassandra hỗ trợ y hệt một module Spring Data khác. Một số có thể được phân tích nhưng không ánh xạ thành truy vấn CQL hợp lệ; một số cần index/tính năng theo version; một số hoàn toàn không phù hợp mô hình bảng.

Khi nghi ngờ, thực hiện hai việc: **đối chiếu bảng supported query keywords của đúng version** và **kiểm tra câu CQL thực tế cùng kết quả trên cluster test**. Không dựa riêng vào việc tên method trông có vẻ giống tiếng Anh.

## 8. Vì sao And, Or, Not, Like không thể suy ra theo SQL?

Giả sử muốn tìm sự kiện:

~~~text
tenant = A
và (event_type = 'paid' hoặc description chứa 'refund')
~~~

Trong SQL quan hệ, developer thường dùng `OR`, `LIKE` và index/optimizer để đáp ứng. Với Cassandra, điều này liên quan nhiều đường truy cập:

- `tenant_id` và `event_day` chọn partition.
- `event_type` là clustering column, có thể được lọc bằng equality/IN trong phạm vi phù hợp.
- `description` là cột thường; substring search không phải chức năng mặc định của `CONTAINS` collection.
- `OR` giữa các cột thuộc đường truy cập khác nhau không được mặc định thực thi như một SQL expression tùy ý.

Không nên “dịch máy” `findByEventTypeOrDescriptionContaining(...)` từ ví dụ Spring Data JPA sang repository Cassandra. Nếu có hai access patterns thực sự khác nhau, có thể cần **hai bảng đọc**, **hai query có giới hạn và merge ở tầng ứng dụng**, hoặc hệ thống tìm kiếm riêng.

Tương tự, `Not` trên một cột thông thường thường không biến thành index lookup rẻ; nhiều truy vấn phủ định dễ dẫn tới việc đọc rất nhiều dữ liệu rồi lọc. Thiết kế theo truy vấn hữu ích hơn việc tìm một keyword trông gần với SQL.

## 9. Khi IN ảnh hưởng ORDER BY và phân trang

Với bảng ví dụ:

~~~sql
PRIMARY KEY ((tenant_id, event_day), event_type, occurred_at, event_id)
~~~

Khi ràng buộc một loại cụ thể:

~~~sql
SELECT occurred_at, event_id, event_type
FROM app_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type = 'paid'
LIMIT 50;
~~~

những hàng thuộc `'paid'` được sắp trong nhóm clustering theo `occurred_at DESC, event_id DESC`.

Khi thay equality bằng:

~~~sql
SELECT occurred_at, event_id, event_type
FROM app_ks.events_by_tenant_day_type
WHERE tenant_id = ?
  AND event_day = ?
  AND event_type IN ('paid', 'cancelled')
LIMIT 50;
~~~

**Đừng suy ra rằng kết quả là 50 sự kiện mới nhất trên cả hai loại khi xét theo thời gian.** Clustering key bắt đầu bằng `event_type`; các loại được nhóm theo thứ tự khóa, còn thời gian được sắp **trong mỗi nhóm**. Nếu API cần một **timeline toàn cục** của tenant/ngày, hãy dùng bảng khác với `occurred_at` là clustering column đầu tiên hoặc gộp/sắp xếp từ những nguồn có giới hạn.

Một `LIMIT 50` cũng không đảm bảo có 50 hàng **cho mỗi** giá trị trong `IN`. Giới hạn áp dụng cho kết quả câu query, không nhân lên theo số phần tử của collection.

Paging trong Cassandra dựa trên **paging state**, không có random-access offset giá rẻ. Query parameter, danh sách giá trị IN và thứ tự cần giữ ổn định khi dùng continuation token; đừng tái sử dụng paging state cho filter khác. Những cập nhật đồng thời không tạo snapshot bất biến xuyên nhiều trang.

## 10. Khi nào CONTAINS nên được thay bằng một bảng đọc?

Giả sử màn hình thường xuyên yêu cầu: **“Lấy các sự kiện có tag `urgent` của tenant A trong ngày D, sắp theo thời gian mới nhất.”**

Với bảng hiện tại, `tags` là cột collection, không nằm trong primary key. Nếu truy vấn này rất nóng, phải cân nhắc chi phí index và filtering. Một cách thiết kế theo truy vấn là bảng riêng:

~~~sql
CREATE TABLE app_ks.events_by_tenant_day_tag (
    tenant_id   uuid,
    event_day   date,
    tag         text,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    description text,
    PRIMARY KEY ((tenant_id, event_day, tag), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Giờ câu CQL là một truy vấn dựa trên partition key:

~~~sql
SELECT occurred_at, event_id, event_type, description
FROM app_ks.events_by_tenant_day_tag
WHERE tenant_id = ?
  AND event_day = ?
  AND tag = ?
LIMIT 50;
~~~

Không cần `CONTAINS` cho đường đọc này. Đổi lại, mỗi sự kiện có nhiều tag có thể cần được ghi vào **nhiều partition** của bảng theo tag. Writer phải đảm bảo quy tắc tạo hàng, retry/idempotency, xóa/TTL và cập nhật khi tập tag thay đổi.

**Không có lựa chọn “miễn phí”:** index làm tăng chi phí duy trì và phụ thuộc tính năng Cassandra; bảng đọc riêng tăng write amplification và yêu cầu đồng bộ; `ALLOW FILTERING` có thể làm tăng I/O. Hãy chọn bằng access pattern, cardinality, phân bố tag và số lượng truy vấn thực tế.

## 11. IN nhiều partition, hot partition và kích thước dữ liệu

Một method chứa `In` không nói cho ta biết truy vấn thực sự đọc bao nhiêu dữ liệu. Có ba tình huống rất khác:

1. **IN trên clustering column trong một partition:** có khả năng đọc một số nhóm hàng trong partition xác định, nhưng còn tùy số giá trị và thứ tự khóa.
2. **IN trên partition key:** có thể đọc nhiều partition ở các replica/token khác nhau; số giá trị tăng thì fan-out/latency tăng.
3. **IN trên cột không thuộc khóa:** có thể bị từ chối nếu không có index hoặc phép lọc phù hợp; không thể biến nó thành đường truy cập tốt chỉ bằng đặt tên method.

Nếu partition chứa hàng triệu sự kiện, derived query `findByKeyTenantIdAndKeyEventDay(...)` cũng có thể làm service sử dụng rất nhiều bộ nhớ khi trả về một `List` lớn. Giới hạn result size, dùng paging và theo dõi kích thước partition; nếu cần chia bucket giờ hoặc shard, key và repository method phải thay đổi theo.

Một danh sách `IN` quá dài cũng có thể dẫn tới số lượng công việc lớn trên coordinator và khó kiểm soát timeout. Validation nên giới hạn số giá trị trước khi gọi repository. Đối với danh sách rỗng, xử lý ở service như trả kết quả rỗng hoặc báo input không hợp lệ; không gửi query mơ hồ rồi phụ thuộc hành vi đặc thù của version.

## 12. Derived query hay @Query, CassandraTemplate, CqlTemplate?

| Nhu cầu | Công cụ thường phù hợp | Nguyên tắc |
| --- | --- | --- |
| Đọc theo partition key rõ ràng, điều kiện đơn giản | Derived query trong `CassandraRepository` | Tên method ngắn, mapping rõ ràng |
| `IN` trên clustering column với điều kiện khóa phù hợp | Derived query nếu keyword được version hỗ trợ | Giới hạn số phần tử, kiểm tra CQL và paging |
| `CONTAINS`/`CONTAINS KEY` cần kiểm soát index/lọc | `@Query` hoặc query/template rõ ràng | Không giả định keyword tự làm index |
| CQL phức tạp hoặc phương án index theo phiên bản | `@Query`, `CqlTemplate` hoặc Java Driver | Kiểm tra cú pháp, bind, execution options |
| Nhiều điều kiện xây dựng động | `CassandraTemplate` với `Query`/`Criteria` | Từng tổ hợp điều kiện vẫn phải hợp lệ theo schema |
| API WebFlux | `ReactiveCassandraRepository` / `ReactiveCassandraTemplate` | Dùng `Mono`/`Flux`, nhưng cùng giới hạn CQL |
| Cần tìm full-text hay analytics diện rộng | Bảng đọc/index/engine phù hợp | Tránh ép một bảng Cassandra phục vụ mọi truy vấn |

Ví dụ chuyển method `In` sang CQL tường minh khi cần kiểm soát cấu trúc:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("""
        SELECT * FROM events_by_tenant_day_type
        WHERE tenant_id = ?0
          AND event_day = ?1
          AND event_type IN ?2
        LIMIT 50
        """)
    List<EventRow> recentByTypes(
        UUID tenantId,
        LocalDate eventDay,
        Collection<String> types
    );
}
~~~

Mã minh họa dùng **Java text block** (Java 15+) và giả định keyspace mặc định là `app_ks`. Khi thực thi, binding của collection với `IN ?` cần được xác minh trên phiên bản Spring Data/driver đang dùng. Nếu API không hỗ trợ binding đó theo cách mong muốn, dùng prepared statement/driver với binding phù hợp; **không nối trực tiếp danh sách do client nhập** vào câu CQL.

Nếu `@Query` cần `ALLOW FILTERING` để chạy, hãy xem đó là dấu hiệu phải **đo chi phí/đánh giá lại data model**. `@Query` chỉ cho phép viết CQL rõ hơn, không làm Cassandra có thêm index hoặc JOIN.

## 13. Từ tên method đến CQL: kiểm thử thế nào?

Đừng chỉ kiểm thử method parser. Một kế hoạch kiểm thử nên có cả **schema, dữ liệu, query và hiệu năng**:

1. Tạo keyspace/bảng trên Cassandra test có phiên bản tương đương môi trường đích.
2. Ghi các sự kiện có cùng tenant/ngày và khác `event_type`, tag, attributes.
3. Gọi `findByKeyTenantIdAndKeyEventDayAndKeyEventTypeIn(...)` với 1, 2 và nhiều loại; xác minh hàng được trả đúng, giới hạn input và hành vi khi danh sách rỗng.
4. Gọi truy vấn `tags CONTAINS` và `attributes CONTAINS KEY` **trong môi trường đã chuẩn bị index/cấu hình phù hợp**; nếu không, ghi nhận rõ lỗi CQL hoặc rủi ro filtering, không coi đó là lỗi cú pháp Java đơn thuần.
5. Đối chiếu câu CQL/bound values do repository phát ra với thiết kế partition key và clustering key.
6. Kiểm tra paging, nhất là khi có `IN` nhiều loại và dữ liệu được ghi trong lúc đọc.
7. Thử tải với partition lớn, tag phổ biến và danh sách IN dài để đo p95/p99 latency, CPU, tombstone, số hàng trả về và số request đến replica.
8. Với reactive repository, kiểm tra end-to-end không có blocking không cần thiết; reactive I/O không sửa CQL sai khóa.

### Ma trận test ngắn

| Trường hợp | Điều mong đợi |
| --- | --- |
| Equality đủ tenant/ngày | Truy vấn theo một partition |
| IN loại sự kiện trong tenant/ngày | Truy vấn đúng các nhóm loại, không tự đảm bảo timeline toàn cục |
| IN chỉ có loại, thiếu tenant/ngày | CQL bị từ chối hoặc không phù hợp access pattern |
| CONTAINS trên set có hỗ trợ index/filtering | Membership đúng phần tử trong tập |
| CONTAINS KEY trên map | Kiểm tra **key**, không nhầm với value |
| Contains trên text description | Không mặc định là tìm substring |
| Query với quá nhiều giá trị IN | Service kiểm tra/giới hạn, tránh fan-out không kiểm soát |
| Truy vấn nhiều ngày hoặc nhiều shard | Có kế hoạch đọc nhiều partition và merge/paging phù hợp |

## 14. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Tên method compile được nghĩa là CQL hợp lệ.” | Query derivation và thực thi Cassandra là hai tầng khác nhau. | Kiểm thử trên cluster thật/đúng version. |
| “`In` chỉ như phép so sánh đơn giá trị.” | Danh sách IN có thể tăng số nhánh và số partition được đọc. | Giới hạn danh sách và đo fan-out. |
| “`Contains` tìm một substring trong text.” | CQL `CONTAINS` là membership cho collection. | Dùng search/index thích hợp cho text. |
| “Map CONTAINS và CONTAINS KEY giống nhau.” | Một phép kiểm tra **value**, phép kia kiểm tra **key**. | Chọn keyword/toán tử theo dữ liệu cần tìm. |
| “Đủ partition key là mọi điều kiện trên cột thường đều hợp lệ.” | Điều kiện non-key có thể đòi index hoặc lọc được cho phép. | Kiểm tra CQL/index và thiết kế bảng. |
| “`ALLOW FILTERING` giải quyết tốt các lỗi query.” | Có thể phát sinh đọc/lọc nhiều dữ liệu rất tốn tài nguyên. | Ưu tiên access pattern và index được kiểm chứng. |
| “`event_type IN (...)` trả timeline mới nhất giữa các loại.” | Clustering sắp theo event_type trước thời gian. | Thiết kế bảng khác hoặc merge có giới hạn. |
| “Mọi keyword Spring Data JPA đều có trong Cassandra.” | Module Cassandra có tập supported keywords và CQL riêng. | Đối chiếu reference của đúng phiên bản. |
| “`PageRequest` cho phép nhảy ngay tới trang số 1.000.” | Cassandra không có offset ngẫu nhiên rẻ. | Dùng paging state/cursor. |
| “Reactive query sẽ sửa lỗi hiệu năng của CONTAINS.” | Reactive thay cách chờ I/O, không thay đổi đường truy cập Cassandra. | Kiểm tra partition/index/khối lượng đọc. |

## 15. Tự kiểm tra

**Câu 1.** Method `findByKeyTenantIdAndKeyEventDayAndKeyEventTypeIn(...)` dự kiến sinh toán tử nào và tại sao nó cần tenant/ngày?

**Đáp án:** Toán tử `IN` trên `event_type`. `tenant_id` và `event_day` xác định partition, trong khi `event_type` là clustering column đầu tiên.

**Câu 2.** `findByDescriptionContains("refund")` có tự động tương đương SQL `LIKE '%refund%'` không?

**Đáp án:** Không. `CONTAINS` trong CQL chủ yếu là membership của collection, không phải toán tử substring trên cột text.

**Câu 3.** Với `attributes = {'channel': 'mobile'}`, `CONTAINS KEY 'channel'` và `CONTAINS 'mobile'` khác gì?

**Đáp án:** Câu đầu kiểm tra **khóa** `'channel'`; câu sau kiểm tra **giá trị** `'mobile'`.

**Câu 4.** Nếu Spring Data phân tích đúng `TagsContains` nhưng Cassandra từ chối query, nguyên nhân có thể là gì?

**Đáp án:** Điều kiện trên cột collection thường có thể cần index/filtering phù hợp với phiên bản và schema. Cú pháp Java đúng không đồng nghĩa CQL được phép hoặc có hiệu năng tốt.

**Câu 5.** Nếu cần 100 sự kiện mới nhất trên mọi loại trong một tenant/ngày, có nên lấy trực tiếp kết quả `event_type IN (...)` và giả định đã sắp theo thời gian không?

**Đáp án:** Không. Vì `event_type` là clustering column trước `occurred_at` nên dữ liệu được nhóm theo loại trước; cần bảng timeline khác hoặc có kế hoạch merge/sort có giới hạn.

**Câu 6.** Khi gặp một keyword ở ví dụ Spring Data JPA nhưng không chắc có trong Cassandra, nên làm gì?

**Đáp án:** Đối chiếu tài liệu supported keywords của **đúng phiên bản Spring Data Cassandra**, kiểm tra câu CQL thực tế và chạy integration test trên cluster tương thích. Nếu không được hỗ trợ, dùng `@Query`/template hoặc thiết kế lại đường truy vấn.

---

**Ghi nhớ:** `In`, `Contains` và `ContainsKey` giúp diễn đạt truy vấn dẫn xuất trong Spring Data Cassandra, nhưng **tên method không vượt qua được giới hạn CQL**. Hãy phân biệt membership của collection với substring của text, cung cấp đủ partition key, hiểu thứ tự clustering, giới hạn số giá trị IN và kiểm tra yêu cầu index/filtering của CONTAINS. Khi truy vấn phức tạp hoặc không phù hợp data model, dùng CQL tường minh hoặc thiết kế bảng đọc theo access pattern thay vì cố nhồi thêm keyword vào tên method.
