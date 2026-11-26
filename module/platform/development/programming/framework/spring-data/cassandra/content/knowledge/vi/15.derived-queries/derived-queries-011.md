# @AllowFiltering và chi phí cần đánh giá trước khi sử dụng

> **Chương:** Truy vấn dẫn xuất  
> **Công nghệ:** Spring Data Cassandra, CassandraRepository, CassandraTemplate, CQL và Apache Cassandra.  
> **Mục tiêu:** hiểu chính xác `@AllowFiltering` tác động đến truy vấn dẫn xuất ra sao, vì sao nó có thể làm độ trễ không dự đoán được và cách thay thế bằng mô hình dữ liệu phù hợp với partition key, paging và yêu cầu nghiệp vụ.

## 1. Tình huống: một phương thức repository trông rất hợp lý

Hệ thống IoT dùng Spring Data Cassandra để lưu sự kiện từ nhiều thiết bị. Người dùng đã có màn hình xem 50 sự kiện mới nhất của **một thiết bị trong một ngày UTC**. Sau đó sản phẩm yêu cầu thêm:

> “Hiển thị các sự kiện `BATTERY_LOW` mới nhất của mọi thiết bị thuộc một chi nhánh.”

Một developer thử thêm phương thức:

~~~java
List<DeviceEvent> findByEventType(String eventType);
~~~

Tên phương thức hợp lệ với quy tắc tạo **derived query** của Spring Data. Nhưng với bảng Cassandra có primary key dựa trên thiết bị và ngày, câu truy vấn theo `eventType` có thể bị server từ chối. Developer bổ sung:

~~~java
@AllowFiltering
List<DeviceEvent> findByEventType(String eventType);
~~~

Lúc này câu truy vấn có thể chạy được trên dữ liệu demo, khiến nhóm tưởng bài toán đã giải quyết. Tuy nhiên, khi cluster chứa hàng trăm triệu sự kiện, lời gọi ấy có thể phải đọc lượng dữ liệu lớn để tìm rất ít kết quả.

**Bài học chính:** `@AllowFiltering` không phải chỉ thị tối ưu hóa. Nó cho phép Cassandra thực hiện thao tác lọc mà hệ thống vốn từ chối hoặc cảnh báo vì chi phí có thể khó dự đoán.

## 2. Truy vấn dẫn xuất trong Spring Data Cassandra làm gì?

Spring Data tạo câu truy vấn từ tên phương thức repository, ví dụ:

~~~java
findByEventType("BATTERY_LOW")
~~~

Tên `findByEventType` có thể được diễn giải thành điều kiện `event_type = ?` dựa trên property và mapping của entity. Các từ khóa như `And`, `Between`, `GreaterThan` hay `LessThan` giúp diễn đạt điều kiện, nhưng vẫn phải phù hợp với CQL và cấu trúc khóa trên Cassandra.

Quá trình có hai tầng khác nhau:

~~~mermaid
flowchart LR
    A["Repository method<br/>findByEventType"] --> B["Spring Data<br/>phân tích tên, tạo CQL"]
    B --> C["Java driver<br/>gửi câu truy vấn"]
    C --> D["Cassandra<br/>kiểm tra khóa, index, filtering"]
    D --> E["Đọc dữ liệu và trả kết quả"]
~~~

Spring Data **không tự tạo secondary index**, **không thay partition key** và **không di chuyển điều kiện WHERE thành bảng đọc khác**. Mọi derived query cuối cùng vẫn phải được Apache Cassandra thực thi theo schema đã có.

Một tên phương thức “đúng ngữ pháp Spring Data” không đồng nghĩa với một access pattern hiệu quả. Khi review derived queries, luôn đối chiếu điều kiện lọc với partition key, clustering columns và index của bảng thật.

## 3. Schema minh họa: dữ liệu phân vùng theo thiết bị/ngày

Ta dùng bảng `events_by_device_day` được thiết kế cho truy vấn timeline. CQL demo:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id   uuid,
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    site_id     uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id ASC
);
~~~

`SimpleStrategy` và replication factor 1 chỉ dùng cho môi trường học tập một node. Production nhiều node/datacenter cần `NetworkTopologyStrategy`, replication factor và consistency phù hợp topology thật.

| Cột | Vai trò | Hệ quả |
| --- | --- | --- |
| `tenant_id` | Thành phần partition key | Phân tách dữ liệu tenant theo thiết kế |
| `device_id` | Thành phần partition key | Định vị thiết bị |
| `event_day` | Thành phần partition key | Bucket thời gian, hạn chế partition tăng không giới hạn |
| `event_time` | Clustering column đầu, DESC | Sắp xếp mới nhất trước **trong một partition** |
| `event_id` | Clustering column tiếp theo | Phân biệt sự kiện cùng thời điểm |
| `site_id`, `event_type`, `payload` | Regular columns | Không tự cung cấp đường tìm kiếm toàn cluster |

Đọc đúng access pattern:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Cassandra có đủ composite partition key, do đó có thể định tuyến tới một partition. Ngược lại, chỉ lọc `event_type` nghĩa là bỏ qua toàn bộ partition key và có thể đụng lượng dữ liệu rất rộng.

**Điểm cần nhớ:** cùng một bảng không nhất thiết đáp ứng mọi bộ lọc mà sản phẩm nghĩ ra. Cassandra ưu tiên **thiết kế bảng theo truy vấn** hơn là cho phép WHERE tùy ý.

## 4. Entity mapping và ví dụ repository

Trong Spring Data Cassandra, một composite key có thể được ánh xạ bằng `@PrimaryKeyClass`:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class DeviceEventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "device_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "event_time", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() { }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID v) { tenantId = v; }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID v) { deviceId = v; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate v) { eventDay = v; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant v) { eventTime = v; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID v) { eventId = v; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof DeviceEventKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, deviceId, eventDay, eventTime, eventId);
    }
}
~~~

Entity tương ứng:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class DeviceEvent {
    @PrimaryKey
    private DeviceEventKey key;

    @Column("site_id")
    private UUID siteId;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public DeviceEvent() { }

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey v) { key = v; }

    public UUID getSiteId() { return siteId; }
    public void setSiteId(UUID v) { siteId = v; }

    public String getEventType() { return eventType; }
    public void setEventType(String v) { eventType = v; }

    public String getPayload() { return payload; }
    public void setPayload(String v) { payload = v; }
}
~~~

Repository với một phương thức cần **tránh dùng cho production** trên bảng lớn:

~~~java
import java.util.List;

import org.springframework.data.cassandra.repository.AllowFiltering;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    // Minh họa cú pháp, KHÔNG gọi trên bảng lớn:
    @AllowFiltering
    List<DeviceEvent> findByEventType(String eventType);
}
~~~

`@Column("event_type")` giúp Spring Data biết property `eventType` ánh xạ tới cột CQL `event_type`. Tuy nhiên regular column đó không thuộc primary key: annotation cho phép filtering, **không làm đường đọc theo eventType trở nên rẻ**.

Một số phiên bản Spring Data dùng API và cơ chế tạo query khác nhau. Ví dụ dựa trên dòng Spring Data Cassandra hiện đại; cần giữ version do Spring Boot quản lý và xác minh kết quả CQL ở integration test của dự án.

## 5. @AllowFiltering thực sự là annotation nào?

Tên đầy đủ:

~~~java
import org.springframework.data.cassandra.repository.AllowFiltering;
~~~

`@AllowFiltering` được đặt trên **phương thức repository truy vấn dẫn xuất**. Trong API Spring Data Cassandra, annotation này tương đương một meta-annotation cấu hình `@Query(allowFiltering = true)` cho quá trình **query derivation**.

Ví dụ hai cách biểu diễn mục đích giống nhau đối với query dẫn xuất:

~~~java
@AllowFiltering
List<DeviceEvent> findByEventType(String eventType);
~~~

~~~java
@org.springframework.data.cassandra.repository.Query(
    allowFiltering = true)
List<DeviceEvent> findByEventType(String eventType);
~~~

Không cần sử dụng cả hai trên cùng một method.

**Phạm vi rất quan trọng:**

- Annotation báo cho Spring Data rằng derived query có thể sử dụng tùy chọn `ALLOW FILTERING`.
- Cassandra vẫn quyết định truy vấn có được thực thi và mất bao nhiêu tài nguyên.
- Annotation **không tự thêm index** hay đánh dấu regular column là clustering key.
- Annotation không tự áp lên tất cả phương thức của repository.
- Với `@Query("SELECT ...")` có **CQL tường minh**, đừng mặc định `@AllowFiltering` sẽ sửa câu CQL viết tay. Nếu cố ý cần filtering, câu CQL phải được viết và kiểm thử theo đúng ngữ nghĩa của API/version; đừng che giấu quyết định này.

`@AllowFiltering` chỉ là công cụ cho trường hợp có chủ đích, không phải cấu hình “bật để mọi method chạy”.

## 6. Spring Data tạo CQL nào và Cassandra xử lý ra sao?

Về bản chất, method:

~~~java
@AllowFiltering
List<DeviceEvent> findByEventType(String eventType);
~~~

có thể tạo câu CQL tương đương:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE event_type = 'BATTERY_LOW'
ALLOW FILTERING;
~~~

Đoạn SQL trên minh họa hình dạng kết quả; Java driver thực tế dùng các tham số/binding và cơ chế tạo statement của Spring Data. Hãy kiểm tra câu lệnh thực ở môi trường tích hợp nếu việc tối ưu hóa dựa vào hành vi cụ thể.

Cassandra có thể phải xem rất nhiều partition vì `event_type` không xuất hiện trong partition key, và bảng không có index chuyên biệt theo điều kiện này. Khi `ALLOW FILTERING` được cho phép, server có thể lọc dữ liệu sau khi đọc, thay vì từ chối query chỉ vì nó không thể dự đoán chi phí tốt.

Không nên hiểu:

~~~text
@AllowFiltering
    = bật index
    = chỉ đọc row khớp eventType
    = Cassandra tự biết cách JOIN/scan nhanh
    = bảo đảm LIMIT 50 chỉ đọc 50 row
~~~

Cách hiểu đúng:

~~~text
@AllowFiltering
    = cho phép server thực hiện filtering nếu query cần
    = phạm vi dữ liệu đọc vẫn do partition key, index
      và câu CQL cụ thể quyết định
    = phải đánh giá chi phí trước khi dùng thường xuyên
~~~

## 7. Lọc trong một partition khác hoàn toàn lọc toàn bảng

`ALLOW FILTERING` **không đồng nghĩa mọi query đều chắc chắn full-scan toàn cluster**. Một query đã cung cấp đầy đủ partition key nhưng lọc thêm regular column có thể chỉ phải kiểm tra row **trong partition ấy**.

Ví dụ trong một partition biết trước:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
  AND event_type = 'BATTERY_LOW'
ALLOW FILTERING;
~~~

Điều này vẫn có rủi ro: Cassandra có thể cần đọc nhiều row trong partition rồi mới loại những event không khớp. Nếu partition chỉ có vài chục row được giới hạn rõ ràng, tần suất thấp và đã benchmark, chi phí có thể chấp nhận được. Nếu một thiết bị gửi hàng triệu row/ngày và chỉ 0,01% là pin yếu, filtering trong partition ấy vẫn có thể quá đắt.

So sánh:

| Query | Phạm vi có thể phải xem | Đánh giá sơ bộ |
| --- | --- | --- |
| Full partition key, không lọc regular column | Một partition, đọc theo clustering | Phù hợp nếu partition size được kiểm soát |
| Full partition key + regular column + filtering | Một partition nhưng có thể lọc nhiều row | Cân nhắc khi partition nhỏ và truy vấn ít |
| Chỉ `event_type` + filtering | Có thể đọc rất nhiều partition/table | Không phù hợp API thường xuyên trên bảng lớn |
| `site_id` + `event_type` + filtering | Vẫn thiếu partition key của bảng | Không thể coi là truy vấn theo site hiệu quả |
| Partition key của bảng read model mới | Một hoặc ít bucket đã biết | Phù hợp nếu thiết kế và tải được kiểm chứng |

**Câu hỏi đầu tiên khi review không phải “có annotation không?” mà là “server cần đọc bao nhiêu partition và row để tìm kết quả?”**

## 8. Vì sao LIMIT nhỏ không bảo đảm truy vấn rẻ?

Developer cố giảm tác động bằng phương thức:

~~~java
@AllowFiltering
List<DeviceEvent> findFirst20ByEventType(String eventType);
~~~

Ngay cả khi Spring Data tạo một câu truy vấn có giới hạn kết quả, nó vẫn phải tìm các row thỏa điều kiện. Nếu chỉ một trong 10.000 event có `eventType = BATTERY_LOW`, việc tìm đủ 20 row có thể yêu cầu xem lượng dữ liệu lớn hơn nhiều so với 20 row được trả về.

Tương tự:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE event_type = 'BATTERY_LOW'
LIMIT 20
ALLOW FILTERING;
~~~

`LIMIT` giới hạn **kết quả trả**, không phải ngân sách tuyệt đối của **row được đọc trước khi lọc**. Nó không biến truy vấn thiếu partition key thành truy vấn O(20).

### Phân biệt ba loại giới hạn

| Khái niệm | Điều nó kiểm soát | Điều nó không bảo đảm |
| --- | --- | --- |
| `LIMIT 20` | Tối đa 20 row CQL trả ra | Không bảo đảm chỉ scan 20 row |
| Fetch page size 20 | Kích thước mục tiêu mỗi lần driver fetch | Không giới hạn tổng dữ liệu khi client đọc tiếp |
| API request timeout | Thời gian client chờ | Không thay đổi cấu trúc truy cập, cũng không chắc hủy công việc server đã thực hiện |

Khi có filtering, thậm chí một trang kết quả nhỏ vẫn có thể đi kèm nhiều thao tác đọc phía Cassandra. **Không** dùng `LIMIT`, page size nhỏ hoặc timeout lớn làm lý do duy nhất để chấp nhận query rộng.

## 9. Slice và CassandraPageRequest không làm filtering biến mất

Spring Data Cassandra hỗ trợ phân trang dựa trên paging state. Một ví dụ có chủ ý **không khuyến nghị**:

~~~java
import org.springframework.data.cassandra.repository.AllowFiltering;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

@AllowFiltering
Slice<DeviceEvent> findByEventType(
    String eventType, Pageable pageable);
~~~

Gọi với:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;

var first = repository.findByEventType(
    "BATTERY_LOW", CassandraPageRequest.first(50));
~~~

Việc trả `Slice` có thể tránh giữ toàn bộ kết quả trong một `List` và dùng paging state để đọc tiếp. **Nhưng chi phí lọc trước khi có đủ row cho mỗi trang vẫn tồn tại.** Nếu truy vấn chạm rất nhiều partition, phân trang không tự giảm đáng kể công việc cần thực hiện ở phía server.

Cassandra không dùng SQL offset để nhảy trực tiếp tới trang thứ 1.000. Paging state phải gắn với đúng statement, điều kiện và quy tắc phân trang; không nên đưa nguyên state không được xác thực ra bên ngoài hệ thống.

Sử dụng `CassandraPageRequest` có ý nghĩa khi **truy vấn cơ sở đã tốt**: ví dụ đọc một partition theo thiết bị/ngày hoặc đọc một partition cảnh báo theo site/type/ngày. Nó không chữa truy vấn thiếu access pattern.

## 10. existsBy, countBy và findFirstBy cũng phải được đánh giá

Derived query có thể trả dữ liệu với nhiều hình dạng:

~~~java
boolean existsByEventType(String eventType);

long countByEventType(String eventType);

List<DeviceEvent> findFirst10ByEventType(String eventType);
~~~

Những method này trông nhẹ hơn `findByEventType` vì chỉ trả boolean, số hoặc 10 entity. Nhưng trên Cassandra, **lượng dữ liệu cần kiểm tra để tạo kết quả** mới là điều quan trọng.

- `existsBy...` không có nghĩa server có một global index/metadata miễn phí về điều kiện đó.
- `countBy...` có thể phải xử lý rất nhiều row. Cassandra không duy trì sẵn số đếm chính xác cho bộ lọc bất kỳ.
- `findFirst10By...` vẫn phải tìm row thỏa điều kiện; không có sắp xếp toàn cục theo thời gian chỉ nhờ chữ `First`.
- Khi derived method không đáp ứng khóa/index, nó có thể bị từ chối nếu chưa có cấu hình filtering, hoặc trở thành truy vấn rất đắt nếu bật filtering.

Đừng dùng `@AllowFiltering` trên `countByEventType` rồi biến kết quả thành chỉ số dashboard được gọi mỗi giây. Nếu cần thống kê cảnh báo theo giờ, nên có **rollup table** hoặc pipeline tổng hợp riêng.

## 11. Mô hình chi phí: ít kết quả có thể cần rất nhiều phép đọc

Giả sử workload minh họa:

~~~text
10.000 thiết bị
30 ngày dữ liệu còn lưu
1.000 sự kiện / thiết bị / ngày

Tổng số event xấp xỉ:
10.000 × 30 × 1.000 = 300.000.000 row
~~~

API yêu cầu 50 sự kiện `BATTERY_LOW` mới nhất tại một chi nhánh. Nếu lọc trên bảng theo thiết bị/ngày mà không có đường định tuyến, lượng dữ liệu có khả năng phải kiểm tra lớn hơn rất nhiều so với 50 row trả về.

Các con số trên **chỉ là minh họa kích thước**, không phải benchmark hay số row Cassandra chắc chắn quét. Chi phí thực phụ thuộc phân bố dữ liệu, index, số node, lọc có phạm vi hẹp hay không, caching, cấu hình driver, compaction và tần suất query.

Có thể dùng các câu hỏi sau để dựng một “cost worksheet” trước khi chấp nhận annotation:

| Đại lượng | Câu hỏi | Ý nghĩa |
| --- | --- | --- |
| Partition fan-out | Query có đầy đủ partition key không, dự kiến chạm bao nhiêu partition? | Quyết định tính định tuyến |
| Rows examined | Cần kiểm tra bao nhiêu row trước khi lọc? | Read amplification |
| Selectivity | Bao nhiêu % row khớp điều kiện? | Ít khớp có thể phải tìm lâu |
| Partition size | Partition lớn nhất chứa bao nhiêu row/byte? | Rủi ro hot partition và tail latency |
| Query frequency | QPS bình thường và cao điểm là bao nhiêu? | Khả năng nhân tải khi lặp lại |
| Concurrency | Có bao nhiêu request chạy song song? | Coordinator/replica pressure |
| Data retention | 7 ngày, 30 ngày hay không giới hạn? | Phạm vi có thể quét tăng theo thời gian |
| Tombstones | Có TTL/xóa nhiều trên dữ liệu cũ không? | Đọc và hòa giải tốn thêm I/O |
| SLO | p95/p99 và error budget cho API? | Ngưỡng chấp nhận vận hành |

**Không chỉ đo thời gian chạy một lần trên local.** Cần workload mô phỏng cả số partition, row size, dữ liệu ít khớp và tải đồng thời.

## 12. Trường hợp nào có thể cân nhắc @AllowFiltering?

`@AllowFiltering` không phải lúc nào cũng tuyệt đối cấm. Một số trường hợp có thể xem xét khi đã đánh giá rõ giới hạn:

1. **Bảng thử nghiệm hoặc dữ liệu cực nhỏ** và không có kế hoạch tăng đáng kể.
2. **Một partition đã biết với số row nhỏ**, cần lọc thêm một regular column mà việc tạo bảng đọc riêng chưa có lợi.
3. **Tác vụ quản trị rất ít gọi**, phạm vi dữ liệu giới hạn và có người chịu trách nhiệm.
4. **Giai đoạn chuyển đổi tạm thời** với mốc loại bỏ cụ thể, kiểm soát QPS và có kế hoạch chuyển sang bảng read model.

Nhưng không nên chấp nhận chỉ vì “chạy dưới 50 ms ở môi trường development”. Cần có **ngưỡng dữ liệu tối đa**, **ngưỡng QPS**, **giám sát**, **owner** và **phương án thay thế** khi mở rộng.

Ví dụ một thiết bị gửi tối đa 100 event/ngày, việc lọc thêm `event_type` trong đúng partition `tenant+device+day` có thể chấp nhận sau benchmark và kiểm tra rõ. Khi một thiết bị có thể gửi 100.000 event/ngày hoặc query được gọi rất nhiều lần mỗi phút, nên xem lại mô hình.

Không coi annotation là hợp đồng bảo đảm tính chính xác/độ mới dữ liệu. Read consistency, replication factor, timeout, retry và dữ liệu projection vẫn phải được quản lý riêng.

## 13. Bảng đọc thay thế: cảnh báo theo site và loại

Nhu cầu nghiệp vụ cụ thể:

~~~text
Input: tenantId, siteId, eventType, time range, cursor
Output: 50 cảnh báo gần nhất cùng thông tin thiết bị
Sort: eventTime DESC, deviceId ASC, eventId ASC
Freshness: theo SLO sản phẩm
~~~

Thiết kế bảng theo query:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alerts_by_site_type_day (
    tenant_id     uuid,
    site_id       uuid,
    event_type    text,
    event_day     date,
    event_time    timestamp,
    device_id     uuid,
    event_id      uuid,
    display_name  text,
    message       text,
    PRIMARY KEY (
        (tenant_id, site_id, event_type, event_day),
        event_time, device_id, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC, event_id ASC
);
~~~

| Khóa/cột | Vai trò | Vì sao |
| --- | --- | --- |
| `tenant_id` | Partition key | Cách ly truy vấn theo tenant |
| `site_id` | Partition key | Người dùng biết site lúc truy vấn |
| `event_type` | Partition key | Dashboard lọc theo một loại cảnh báo |
| `event_day` | Partition key | Bucket thời gian kiểm soát kích thước |
| `event_time` | Clustering DESC | Hiển thị cảnh báo mới nhất trước |
| `device_id, event_id` | Clustering tie-breakers | Phân biệt event cùng millisecond |
| `display_name, message` | Regular columns | Projection nhẹ, tránh JOIN khi hiển thị |

CQL truy vấn:

~~~sql
SELECT event_time, device_id, event_id, display_name, message
FROM telemetry.alerts_by_site_type_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND site_id = 33333333-3333-4333-8333-333333333333
  AND event_type = 'BATTERY_LOW'
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Đã cung cấp **đủ partition key**, không cần `ALLOW FILTERING`. Cassandra đọc được các row theo clustering order trong partition. Nếu user chọn khoảng thời gian cắt qua hai ngày UTC, ứng dụng đọc các bucket cần thiết và ghép kết quả có kiểm soát.

**Lưu ý:** site có lưu lượng cảnh báo lớn có thể tạo hot partition. Cần đo byte/partition và burst traffic; bucket theo giờ hoặc sharding có kiểm soát là phương án khi bucket ngày không đủ. Mô hình tốt luôn cần kiểm chứng, không chỉ thay một anti-pattern bằng schema chưa đo tải.

## 14. Đọc bảng mới bằng repository không cần @AllowFiltering

Trên bảng `alerts_by_site_type_day`, Spring Data Cassandra có thể ánh xạ entity/khóa tương ứng và dùng một phương thức query tường minh:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface SiteAlertRepository
        extends CassandraRepository<SiteAlert, SiteAlertKey> {

    @Query("SELECT * FROM alerts_by_site_type_day "
         + "WHERE tenant_id = ?0 AND site_id = ?1 "
         + "AND event_type = ?2 AND event_day = ?3")
    Slice<SiteAlert> findDayAlerts(
        UUID tenantId, UUID siteId, String eventType,
        LocalDate utcDay, Pageable pageable);
}
~~~

Ở ví dụ này, `SiteAlert` và `SiteAlertKey` phải được định nghĩa bằng `@Table`, `@PrimaryKeyClass` và `@PrimaryKeyColumn` khớp với DDL của bảng read model. Phần quan trọng là CQL truy vấn **đúng bốn thành phần partition key**, không cần annotation filtering.

Sử dụng:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;

var firstPage = repository.findDayAlerts(
    tenantId, siteId, "BATTERY_LOW", utcDay,
    CassandraPageRequest.first(50));

if (firstPage.hasNext()) {
    var nextPage = repository.findDayAlerts(
        tenantId, siteId, "BATTERY_LOW", utcDay,
        firstPage.nextPageable());
}
~~~

`Slice` và `CassandraPageRequest` hỗ trợ đọc tiếp bằng paging state. Chúng hữu ích **vì truy vấn gốc đã giới hạn được partition**. Nếu một API đọc nhiều bucket ngày, cần quản lý cursor riêng cho từng bucket và giữ cùng điều kiện filter/thời gian khi tiếp tục.

Mặc dù đề bài thuộc truy vấn dẫn xuất, minh họa `@Query` tường minh cho bảng có nhiều khóa giúp tránh tên derived method quá dài và dễ review CQL thực tế. Nếu dùng derived method cho khóa lồng nhau, cần kiểm tra tên property path và generated CQL qua integration test.

## 15. Một phương án khác: index phù hợp với phiên bản Cassandra

Ngoài denormalization, một số workload có thể dùng **secondary index** hoặc **Storage-Attached Index (SAI)** tùy phiên bản/nền tảng Cassandra. Tuy nhiên index không tự biến mọi truy vấn ad hoc thành đường đọc hiệu quả.

Trước khi tạo index để hỗ trợ `event_type`, phải hỏi:

- Cluster đang sử dụng Cassandra/SAI version nào? Cú pháp và tính năng có được hỗ trợ không?
- Giá trị `event_type` có cardinality/selectivity như thế nào? `BATTERY_LOW` có phổ biến không?
- Truy vấn có thêm filter `site_id`, thời gian, tenant và cần sort theo eventTime không?
- Index có cho phép tìm đúng dữ liệu với ít node/partition hay vẫn phải fan-out rồi merge?
- Chi phí ghi, storage, index build, compaction và rollback thế nào?
- p95/p99 và error rate có ổn khi site có cảnh báo đột biến không?

Ví dụ mục tiêu **“50 cảnh báo mới nhất của một site/type/day”** thường được phục vụ dễ dự đoán hơn bằng bảng đọc theo site/type/day, vì index trên `event_type` không tự cung cấp thứ tự toàn cục qua hàng nghìn device partitions.

Đừng thay `@AllowFiltering` bằng `CREATE INDEX` theo phản xạ. Cả hai phương án đều phải được benchmark với workload và kế hoạch vận hành thực tế.

## 16. Denormalization và chi phí ghi nhiều bảng

Một projection cần được cập nhật cùng luồng ingest, không tự đồng bộ chỉ vì có DDL mới:

~~~mermaid
flowchart LR
    A["Thiết bị gửi sự kiện"] --> B["Ingest / event log"]
    B --> C["events_by_device_day"]
    B --> D{"Là cảnh báo cần hiển thị?"}
    D -->|Có| E["alerts_by_site_type_day"]
    D -->|Không| F["Bỏ qua projection"]
    E --> G["Dashboard theo site"]
    C --> H["Timeline theo device"]
~~~

Rủi ro quan trọng:

- Ghi bảng nguồn thành công nhưng bảng projection lỗi hoặc worker xử lý chậm.
- Retry khiến một event được gửi lại. Nếu `eventId` thay đổi, bảng projection có thể chứa dữ liệu trùng.
- Tên thiết bị/site thay đổi: projection là snapshot tại thời điểm event hay phải cập nhật tên hiện tại?
- Thay đổi khóa bucket, TTL và retention có thể làm số liệu giữa hai bảng không khớp.
- Event đến muộn vẫn phải được ghi vào đúng `event_day` UTC, không mặc định ngày hệ thống đang nhận.

Một thiết kế bền vững dùng event ID ổn định, nguồn event có thể replay, projector idempotent, retry/backoff, checkpoint và reconciliation. Hai ghi vào hai bảng/partition **không tự là transaction ACID đa bảng**.

Consistency như `LOCAL_QUORUM` điều chỉnh xác nhận replica cho từng thao tác, nhưng không làm projection bất đồng bộ xuất hiện trước khi worker ghi.

## 17. Quy trình thay thế một @AllowFiltering đang chạy

Giả sử hệ thống đã có:

~~~java
@AllowFiltering
List<DeviceEvent> findByEventType(String eventType);
~~~

Một kế hoạch chuyển đổi giảm rủi ro:

1. **Lập danh mục query:** biết endpoint nào dùng method, QPS, p95/p99, số row/partition và độ trễ lỗi.
2. **Chốt hợp đồng nghiệp vụ:** tenant/site/type/day, sort, page, retention, SLO và lag chấp nhận.
3. **Tạo bảng mới:** schema `alerts_by_site_type_day` theo query, không đổi primary key bảng nguồn.
4. **Triển khai dual-write/projection:** ghi event mới vào bảng đọc, có retry theo event ID ổn định.
5. **Backfill lịch sử:** quét nguồn theo job offline có checkpoint, giới hạn concurrency và tác động cluster.
6. **Đối soát:** đếm/so ID theo bucket, phát hiện thiếu/trùng và event đến muộn.
7. **Canary read:** cho một phần traffic đọc bảng mới; so dữ liệu/latency với nguồn và giám sát lag.
8. **Chuyển hoàn toàn:** bỏ đường đọc filtering khỏi API production; giữ rollback rõ ràng.
9. **Dọn kỹ thuật:** xóa method/annotation cũ khi an toàn, bổ sung check ngăn tái xuất hiện.

Không xóa bảng nguồn hay tắt đường cũ trước khi chứng minh projection đầy đủ. Tạo schema và thay code trong cùng một bước không có backfill thường khiến dashboard thiếu dữ liệu lịch sử.

Đừng dùng batch Cassandra khổng lồ để chuyển hàng triệu row trong một lệnh. Cassandra batch không phải công cụ bulk import/transaction cross-partition hiệu quả; backfill nên đi theo pipeline phù hợp và giới hạn lưu lượng.

## 18. Đo chi phí trên staging và ở production

Một checklist thử tải có thể thực hiện trên cluster test dùng phiên bản Cassandra, RF, dữ liệu và topology tương tự production.

### Tạo tập dữ liệu đủ đại diện

- Thiết bị ít sự kiện và thiết bị rất “nóng”.
- Partition nhỏ, vừa và lớn; có cả tombstone/TTL.
- Phân bố `event_type`: loại hiếm, phổ biến, burst traffic.
- Dữ liệu nhiều tenant/site, nhiều bucket ngày.
- Truy vấn chạy ở concurrency/QPS tương tự giờ cao điểm.

### So sánh cùng hợp đồng truy vấn

| Chỉ số | Query filtering trên bảng nguồn | Query đọc bảng projection |
| --- | --- | --- |
| Số partition dự kiến | Có thể rất lớn | Thường 1–2 bucket cho cửa sổ 24h |
| Rows examined | Có thể nhiều hơn kết quả rất nhiều | Tương đối gần phạm vi trang nếu clustering phù hợp |
| p50/p95/p99 | Phải đo | Phải đo |
| Timeout/retry | Phải đo | Phải đo |
| CPU/I/O coordinator và replica | Phải đo | Phải đo |
| Độ mới dữ liệu | Theo nguồn và consistency | Thêm projection lag |
| Write/storage | Ít projection hơn | Thêm chi phí ghi bảng read model |

Không tự điền các con số p95/p99 tùy tiện vào báo cáo: chỉ sử dụng số đo có phương pháp, cùng mẫu dữ liệu và cùng mức tải.

### Công cụ hỗ trợ quan sát

- `cqlsh` có `TRACING ON` để khảo sát đường thực thi **trên môi trường thử nghiệm**. Tracing có overhead, không bật bừa bãi trên toàn bộ traffic production.
- Metrics Cassandra: read latency, timeout, unavailable, tombstone scanned, SSTable reads, compaction, CPU, disk I/O, dropped mutations.
- Metrics ứng dụng/driver: query ID, p95/p99, retry, request timeout, số page fetch và tổng row/bytes trả về.
- Thông tin về partition size/hot keys, replication factor, datacenter và trạng thái node.

Cassandra không cung cấp một `EXPLAIN` kiểu RDBMS đảm bảo dự đoán chi phí cho mọi truy vấn. Muốn biết query có gây fan-out hay không, phải kết hợp **schema, điều kiện CQL, tracing và đo đạc thực tế**.

## 19. Guardrails và chính sách review repository

Một số đội chọn chính sách **không chấp nhận `@AllowFiltering` mới trong luồng online** nếu thiếu phê duyệt hiệu năng. Mẫu review:

~~~text
Repository method: findByEventType
Annotation:        @AllowFiltering
Query category:    online / batch / admin
Primary key bound: tenantId? deviceId? day?
Maximum data:      partitions, rows, bytes
Query rate:        normal QPS / peak QPS
Latency budget:    p95 / p99 / timeout
Alternatives:      index / read table / analytics
Owner:             nhóm chịu trách nhiệm
Expiry/plan:       bỏ annotation khi nào?
Benchmark:         đường dẫn kết quả test/staging
~~~

Có thể đưa grep/kiểm tra tĩnh vào PR review để phát hiện `@AllowFiltering` mới, nhưng không cần tạo thêm script trong phạm vi bài học này. Review phải xét đúng **ngữ cảnh dữ liệu**: một method admin đọc partition nhỏ đã giới hạn khác hẳn một API public query toàn bảng.

Không nên để caller HTTP tùy ý chọn `ALLOW FILTERING`, thay đổi mọi filter hoặc đặt request timeout rất cao: đó là cách đưa quyết định vận hành quan trọng ra ngoài kiểm soát.

## 20. Consistency, timeout và retry không sửa được mô hình truy vấn

Một truy vấn filtering rộng có thể thất bại theo nhiều cách:

- Cassandra từ chối query nếu không cho phép server-side filtering.
- Query được chấp nhận nhưng đọc quá nhiều dữ liệu, gây p99 cao.
- Client request timeout trong khi công việc server có thể đã diễn ra.
- Retry tự động hoặc do service thực hiện khiến tải cluster tăng thêm.
- Các truy vấn online khác cũng chậm vì cùng cạnh tranh tài nguyên.

Tăng `basic.request.timeout` hoặc Spring Boot `spring.cassandra.request.timeout` có thể khiến client đợi lâu hơn, **không** làm số partition bị scan giảm. Tăng consistency từ `LOCAL_ONE` lên `LOCAL_QUORUM` là lựa chọn độ mới/availability theo replication, không phải tối ưu lọc regular column.

### Vòng lặp quá tải cần tránh

~~~text
Query không định tuyến tốt
    ↓
Đọc nhiều partition, latency tăng
    ↓
Timeout và retry nhiều hơn
    ↓
Coordinator/replica càng tải nặng
    ↓
Nhiều query khác cũng timeout
~~~

Ưu tiên sửa access pattern và giới hạn công việc. Nếu bắt buộc có query rộng tạm thời, giới hạn concurrency, QPS, dữ liệu, timeout và khả năng retry; đặt ngưỡng dừng khi ảnh hưởng cluster.

## 21. Lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Truy vấn dẫn xuất bị từ chối do filtering | WHERE không theo key/index phù hợp | Kiểm tra schema và thiết kế query khác |
| Thêm `@AllowFiltering` thì chạy nhưng p99 tăng | Cassandra phải lọc nhiều dữ liệu | Dùng partition-aware read model, benchmark |
| `findFirst10By...` vẫn chậm | LIMIT nhỏ nhưng phải tìm row khớp | Không dựa vào LIMIT để cứu scan |
| `countByEventType` gây tải cao | Đếm theo regular column trên dữ liệu rộng | Rollup/counter có chính sách hoặc analytics |
| `Slice` không giảm server CPU | Paging chỉ giới hạn kết quả fetch | Sửa access pattern, đo read amplification |
| Annotation đặt trên method `@Query` CQL viết tay nhưng không như mong đợi | Filtering của query derivation khác raw CQL | Kiểm tra JavaDoc/API và CQL thực tế |
| Lọc trong một partition lúc đầu nhanh rồi chậm dần | Partition theo ngày tăng quá lớn | Đo row/partition, đổi bucket hoặc projection |
| Endpoint chỉ có `eventId` nhưng query trên bảng theo device/day | Thiếu partition key | Bảng lookup theo ID hoặc sửa API |
| Index mới không đảm bảo ORDER BY mới nhất toàn site | Index không tạo clustering toàn cục | Bảng read model theo site/type/day |
| Dữ liệu projection thiếu sau migration | Backfill/retry/consumer chưa hoàn tất | Reconciliation, checkpoint và canary |
| GET sau ghi thấy dữ liệu cũ | Consistency, lag projection hoặc caching | Phân biệt nguồn lỗi và chốt freshness contract |
| Tăng timeout, retry làm cluster chậm hơn | Chưa sửa số partition/row cần đọc | Giới hạn tải, tối ưu schema |

## 22. Bài tập thực hành

### Bài A — Đọc câu truy vấn dẫn xuất

Bảng có primary key `((tenant_id, device_id, event_day), event_time, event_id)`. Developer viết:

~~~java
@AllowFiltering
List<DeviceEvent> findByEventType(String type);
~~~

Hãy chỉ ra điều kiện nào thiếu partition key, vì sao method vẫn có thể sinh CQL hợp lệ nhưng chi phí không đoán trước được, và cách nhận diện query được gửi thực tế.

**Gợi ý:** tên method dựa trên regular column; annotation cho phép lọc, không tạo index. Xem schema, tracing/metrics và chạy integration test có dữ liệu đại diện.

### Bài B — LIMIT có cứu được query không?

Truy vấn:

~~~sql
SELECT * FROM telemetry.events_by_device_day
WHERE event_type = 'BATTERY_LOW'
LIMIT 10 ALLOW FILTERING;
~~~

Nếu chỉ có 0,01% row khớp, Cassandra có chắc chỉ đọc 10 row không? Vì sao fetch page size 10 cũng không bảo đảm hiệu năng?

**Gợi ý:** LIMIT/page size chỉ giới hạn kết quả/fetch, không giới hạn tuyệt đối số row cần kiểm tra để tìm kết quả.

### Bài C — Lọc trong một partition nhỏ

Một device/day chắc chắn có không quá 100 event, API admin gọi một lần/ngày và muốn lọc `event_type`. Hãy liệt kê những thông tin cần đo trước khi chấp nhận filtering tạm thời. Nếu mỗi device/day tăng thành 100.000 event, bạn đổi thiết kế thế nào?

**Gợi ý:** chứng minh partition nhỏ, QPS thấp, SLO đạt, có owner và kế hoạch dừng; xem bảng đọc theo device/type/day hoặc mô hình phù hợp.

### Bài D — Chuyển sang bảng site/type/day

Product muốn 50 cảnh báo mới nhất tại một site trong một ngày. Hãy viết CQL `CREATE TABLE` với partition key có `tenantId`, `siteId`, `eventType`, `eventDay`; clustering keys gồm `eventTime`, `deviceId`, `eventId`. Viết `SELECT` không cần `ALLOW FILTERING`.

**Gợi ý:** dùng bảng `alerts_by_site_type_day` ở mục 13, nhớ quyền tenant và xử lý ngày UTC.

### Bài E — So sánh @Query với @AllowFiltering

Khi nào dùng:

~~~java
@AllowFiltering
List<DeviceEvent> findByEventType(String type);
~~~

và khi nào dùng `@Query("SELECT ... WHERE ...")` tường minh? Vì sao không được giả định `@AllowFiltering` tự sửa câu CQL viết tay?

**Gợi ý:** annotation dành cho query derivation; raw CQL phải chứa cú pháp cần thiết và được kiểm thử riêng. Với production, ưu tiên câu truy vấn có đủ partition key.

### Bài F — countBy và existsBy

Một dashboard mỗi giây gọi `countByEventType("BATTERY_LOW")` trên bảng 300 triệu row. Hãy ước lượng những yếu tố chi phí, nêu vì sao kiểu kết quả `long` không làm truy vấn rẻ và thiết kế rollup thay thế.

**Gợi ý:** số row cần xét quan trọng hơn byte trả về; lưu số liệu theo tenant/site/type/hour và kiểm soát replay/late events.

### Bài G — Kiểm thử hiệu năng

Lập kế hoạch benchmark query filtering so với read model: dữ liệu gồm site lớn nhất, eventType hiếm/phổ biến, nhiều ngày, tombstones, QPS bình thường và burst. Nêu ít nhất tám metrics cần thu và tiêu chí dừng thử.

**Gợi ý:** p95/p99, timeout, retries, partitions/rows scanned, bytes, CPU/I/O, compaction, tombstones và độ trễ projection.

### Bài H — Di chuyển an toàn

Một API filtering đã hoạt động nhiều tháng. Hãy lập kế hoạch schema mới, projection cho event mới, backfill, reconciliation, canary, rollback và thời điểm gỡ annotation. Vì sao không được bỏ ngay code cũ khi chưa backfill xong?

**Gợi ý:** schema đúng chưa chứng minh dữ liệu đầy đủ; cần so event IDs/bucket, checkpoint và kiểm tra lag.

**Tiêu chí đạt:** giải thích đúng tác dụng của `@AllowFiltering` với query derivation, phân biệt lọc trong một partition và quét rộng, không nhầm `LIMIT`/paging với scan budget, biết tính chi phí và đưa ra mô hình bảng đọc thay thế.

## 23. Checklist trước khi chấp nhận @AllowFiltering

- [ ] Có biết câu CQL cuối và cột nào thuộc partition/clustering key?
- [ ] Query có đủ partition key hay có nguy cơ scan rất nhiều partition?
- [ ] Nếu lọc trong một partition, đã chặn kích thước partition và QPS?
- [ ] Đã đo selectivity, rows examined, p95/p99, timeout và retry?
- [ ] `LIMIT` và paging có được hiểu đúng, không coi là giới hạn I/O?
- [ ] Method `existsBy`/`countBy` có thực sự cần đọc rộng không?
- [ ] Index/SAI hoặc read model có phù hợp hơn và đã benchmark chưa?
- [ ] Có quyền tenant, time bucket, retention và freshness contract?
- [ ] Đã thử trên dữ liệu/traffic đại diện và có guardrail khi tải tăng?
- [ ] Có owner, mục đích, thời hạn sử dụng và kế hoạch thay thế?
- [ ] Nếu tạo projection, đã có retry, idempotency, backfill và reconciliation?
- [ ] PR review nêu rõ vì sao chấp nhận filtering thay vì để annotation bị thêm theo thói quen?

## Tài liệu tham khảo

- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): derived queries và ví dụ `@AllowFiltering`.
- [Spring Data Cassandra — AllowFiltering Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/repository/AllowFiltering.html): annotation dùng cho query derivation.
- [Spring Data Cassandra — @Query Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/repository/Query.html): `allowFiltering` trong query derivation.
- [Apache Cassandra — CQL SELECT và ALLOW FILTERING](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): giới hạn filtering, `LIMIT` và điều kiện CQL.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): thiết kế theo access pattern và partition key.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): entity và khóa tổng hợp.
- [Spring Data Cassandra — Repositories](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): cách tổ chức repository.
