# Kiểm tra lược đồ thực tế so với mô hình ứng dụng

> **Chương: Quản lý lược đồ.** Trong Spring Data Cassandra, annotation trên entity, bản CQL migration và cấu trúc bảng thật trên Apache Cassandra phải mô tả cùng một mô hình dữ liệu. Bài này hướng dẫn đối chiếu chúng trước khi triển khai và khi xử lý lỗi, với ví dụ bảng lưu sự kiện thiết bị theo thời gian.

## 1. Mục tiêu và bối cảnh

Giả sử hệ thống IoT lưu sự kiện từ thiết bị. API chính cần xem **50 sự kiện mới nhất của một thiết bị trong một ngày UTC**, sau đó tiếp tục bằng paging state. Ứng dụng viết bằng Spring Boot, sử dụng Spring Data Cassandra để ánh xạ entity, `CassandraRepository`, `CassandraTemplate` và CQL.

Một thay đổi tưởng đơn giản như đổi tên field `eventTime`, thêm `eventType` hoặc thay bucket từ ngày sang giờ có thể khiến mô hình Java **không còn khớp** với bảng Cassandra đang tồn tại. Trong môi trường phân tán, điều này không chỉ gây lỗi ánh xạ: đổi partition key hay clustering key có thể làm toàn bộ chiến lược truy vấn trở nên sai.

Sau bài học, bạn có thể:

- Phân biệt **mong đợi của ứng dụng** và **schema thực tế** trên Cassandra.
- Kiểm tra keyspace, bảng, cột, kiểu CQL, partition key, clustering columns, thứ tự sắp xếp, tùy chọn bảng và index có liên quan.
- Dùng `cqlsh`, `system_schema` và metadata API của Java driver để xác nhận trạng thái.
- Nhận diện lệch schema có thể triển khai tương thích và thay đổi cần tạo bảng mới.
- Thiết kế bước kiểm tra trước rollout, trong integration test và sau migration, kể cả khi cluster chưa hoàn tất schema agreement.

Đây là bài về **kiểm tra và quản lý schema**. Không có thiết lập annotation hay Java driver nào có thể biến một bảng thiết kế sai access pattern thành bảng chạy nhanh chỉ nhờ tăng timeout hoặc thêm `ALLOW FILTERING`.

## 2. Ba lớp cần khớp: hợp đồng truy vấn, CQL, entity

Một schema được xem là “đúng” khi các thành phần trả lời cùng một câu hỏi:

| Thành phần | Mô tả | Điều cần đối chiếu |
| --- | --- | --- |
| Hợp đồng nghiệp vụ | Đọc sự kiện theo thiết bị, bucket ngày UTC, mới nhất trước | Các cột khóa phù hợp filter, sort và trang kết quả |
| Bản migration CQL | `CREATE KEYSPACE`, `CREATE TABLE`, `ALTER TABLE` được quản lý có phiên bản | Cấu trúc ứng dụng dự kiến sau mỗi lần rollout |
| Schema đang chạy | Keyspace, tables, columns, types, clustering order, options trên cluster | Thực tế đã áp dụng đủ migration và đã hội tụ trên các node chưa |
| Spring Data mapping | `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@Column`, Java types | Cột, kiểu và khóa mà entity/repository thực sự sử dụng |
| Truy vấn | CQL trong `@Query`, `CassandraTemplate`, `CqlSession` | Có đủ partition key và điều kiện hợp lệ với clustering columns không |

Ví dụ thực tế:

~~~text
Yêu cầu:
  Xem sự kiện theo deviceId và một ngày, eventTime DESC.

CQL được mong đợi:
  PRIMARY KEY ((device_id, event_day), event_time, event_id)

Mô hình Java:
  deviceId + eventDay = PARTITIONED
  eventTime DESC + eventId ASC = CLUSTERED

Cluster thực tế:
  Đã có cột event_day?
  Partition key có đúng hai thành phần?
  Clustering có đúng thứ tự và hướng?
  Kiểu event_time thực sự là timestamp?
~~~

Chỉ kiểm tra ứng dụng biên dịch thành công là chưa đủ. Annotation là mô tả phía Java; nó **không bảo đảm Cassandra đã nhận schema tương ứng**.

## 3. Ví dụ schema đích của ứng dụng

Để giới hạn phạm vi, ta giả định keyspace và bảng được tạo bằng migration riêng, trước khi ứng dụng khởi động. Ví dụ sau phù hợp **môi trường phát triển một node**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    received_at timestamp,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Trong môi trường nhiều node/đa datacenter, hệ thống thường sử dụng `NetworkTopologyStrategy` với replication factor theo topology thực tế. Không sao chép `SimpleStrategy` và RF=1 sang production.

### Tại sao thứ tự khóa quan trọng?

- `(device_id, event_day)` là **composite partition key**. Thiết bị và bucket ngày cùng quyết định partition; truy vấn lịch sử phải cung cấp **cả hai**.
- `event_time DESC` là clustering column đầu: các event mới xuất hiện trước **trong cùng một partition**.
- `event_id ASC` là clustering column tiếp theo: phân biệt nhiều sự kiện cùng millisecond và giữ thứ tự xác định.
- `event_type`, `payload` và `received_at` là **regular columns**. Chúng không tự trở thành khóa để truy vấn toàn hệ thống theo loại sự kiện.
- Timestamp Cassandra có độ phân giải millisecond: nếu dùng `Instant` chính xác đến nanosecond trong Java, phải thống nhất quy tắc chuẩn hóa trước khi đưa vào khóa.

Truy vấn phù hợp:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry.events_by_device_day
WHERE device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Truy vấn này có thể đọc trong một partition, theo thứ tự clustering đã khai báo. Truy vấn chỉ theo `event_type` sẽ không có khả năng định tuyến tương đương.

## 4. Mô hình Spring Data Cassandra cần đem đi đối chiếu

Một mapping có chủ đích nên đặt rõ tên CQL thay vì phụ thuộc hoàn toàn vào naming strategy ngầm định. Ở đây sử dụng composite primary key.

**`DeviceEventKey.java`**:

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

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "event_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() { }

    public DeviceEventKey(UUID deviceId, LocalDate eventDay,
                          Instant eventTime, UUID eventId) {
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }
    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }
    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }
    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof DeviceEventKey that)) return false;
        return Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime, eventId);
    }
}
~~~

**`DeviceEvent.java`**:

~~~java
import java.time.Instant;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class DeviceEvent {
    @PrimaryKey
    private DeviceEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    @Column("received_at")
    private Instant receivedAt;

    public DeviceEvent() { }

    public DeviceEvent(DeviceEventKey key, String eventType,
                       String payload, Instant receivedAt) {
        this.key = key;
        this.eventType = eventType;
        this.payload = payload;
        this.receivedAt = receivedAt;
    }

    public DeviceEventKey getKey() { return key; }
    public void setKey(DeviceEventKey value) { key = value; }
    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }
    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
    public Instant getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Instant value) { receivedAt = value; }
}
~~~

Trong ví dụ:

| Annotation/kiểu Java | Mong đợi bên Cassandra |
| --- | --- |
| `@Table("events_by_device_day")` | Tên bảng chính xác trong keyspace cấu hình |
| `UUID deviceId` + `@PrimaryKeyColumn(PARTITIONED)` | `device_id uuid`, thành phần thứ nhất của partition key |
| `LocalDate eventDay` + `@PrimaryKeyColumn(PARTITIONED)` | `event_day date`, thành phần thứ hai của partition key |
| `Instant eventTime` + `CLUSTERED DESCENDING` | `event_time timestamp`, clustering column đầu `DESC` |
| `UUID eventId` + `CLUSTERED ASCENDING` | `event_id uuid`, clustering column thứ hai `ASC` |
| `String eventType` + `@Column("event_type")` | `event_type text` |
| `Instant receivedAt` | `received_at timestamp` |

**Kiểu Java không phải kiểu CQL.** Mapping/converter của Spring Data Cassandra và driver mới quyết định chuyển đổi. Với trường đặc biệt như collection, tuple, UDT hoặc custom converter, đối chiếu phải mở rộng đến element type, `frozen` và converter thực tế. Chỉ so tên cột sẽ bỏ sót những lỗi này.

## 5. Quy tắc đối chiếu tối thiểu trước khi chạy ứng dụng

Trước khi kiểm tra “khớp schema”, hãy phân loại mức độ quan trọng:

| Đối tượng | Điều phải khớp | Rủi ro khi lệch |
| --- | --- | --- |
| Keyspace | Tên, replication, cấu hình datacenter theo môi trường | Không kết nối được; consistency không đạt như dự kiến |
| Table | Tên và keyspace | Driver/repository báo bảng không tồn tại |
| Partition key | Danh sách, thứ tự, kiểu dữ liệu | Không thể định tuyến câu CQL mong đợi; phải đổi mô hình hoặc migration |
| Clustering key | Danh sách, thứ tự, kiểu, `ASC/DESC` | Phân trang/thứ tự timeline không như kỳ vọng |
| Regular columns | Tên, loại dữ liệu, khả năng ánh xạ | Đọc null, mapping lỗi hoặc ghi thất bại |
| Index/view | Loại, target, trạng thái và nhu cầu truy vấn tương ứng | Sai hiệu năng hoặc query không được hỗ trợ |
| Table options | TTL mặc định, compaction, gc grace và các policy khác | Dữ liệu hết hạn khác dự tính; tombstone/hiệu năng thay đổi |
| Quyền truy cập | Role có quyền truy vấn keyspace/table | Build đúng nhưng runtime bị từ chối |
| Schema agreement | Node đã hội tụ cùng schema sau thay đổi | Node khác nhau nhìn thấy schema khác nhau trong thời gian chuyển tiếp |

Có thể sử dụng checklist như một **schema contract** cho mỗi bảng. Với Cassandra, partition/clustering key quan trọng hơn việc so sánh mọi thuộc tính theo một diff văn bản đơn thuần.

Không nhầm giữa **schema parity** và **data parity**: hai bảng có DDL giống nhau vẫn có thể thiếu row do backfill lỗi; cần quy trình đối soát dữ liệu độc lập.

## 6. Kiểm tra bằng cqlsh: nhìn trực tiếp bảng đã triển khai

Đầu tiên, kết nối tới một node Cassandra thuộc môi trường cần kiểm tra bằng `cqlsh` (điểm kết nối, TLS và xác thực tùy hạ tầng). Trong phiên `cqlsh`, chạy:

~~~text
DESCRIBE KEYSPACE telemetry;
DESCRIBE TABLE telemetry.events_by_device_day;
~~~

`DESCRIBE` là **lệnh của cqlsh**, không phải câu CQL chuẩn để gửi qua `CqlSession.execute(...)`. Nó giúp hiển thị DDL gần với cấu trúc cluster đang báo, gồm khóa, kiểu cột và một số table options. Khi đọc output, so với migration dự kiến:

- `PRIMARY KEY ((device_id, event_day), event_time, event_id)` đúng chưa?
- `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` đúng chưa?
- `event_day` thực sự là `date`, `event_time` là `timestamp`?
- `event_type` là `text`, có bị ghi nhầm thành `int` không?
- Keyspace có đúng replication strategy và RF của môi trường không?

Đừng kết luận một môi trường đã đúng chỉ vì `DESCRIBE` ở **một node** trông hợp lệ: cluster có thể chưa đạt schema agreement. Mục 11 giải thích bước kiểm tra hội tụ.

### CQL kiểm tra catalog: system_schema

Để lấy thông tin theo truy vấn hoặc đưa vào công cụ audit, Cassandra có các bảng hệ thống `system_schema`. Ví dụ:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry';
~~~

~~~sql
SELECT keyspace_name, table_name, column_name,
       kind, position, type, clustering_order
FROM system_schema.columns
WHERE keyspace_name = 'telemetry'
  AND table_name = 'events_by_device_day';
~~~

Các trường của `system_schema.columns` cho phép nhận biết:

- `kind = 'partition_key'`: thành phần partition key, `position` thể hiện vị trí.
- `kind = 'clustering'`: clustering columns; `position` và `clustering_order` giúp kiểm tra thứ tự và chiều.
- `kind = 'regular'` hoặc `static`: cột dữ liệu, có tính chất truy cập riêng.
- `type`: chuỗi tên kiểu CQL được Cassandra ghi nhận.

Thứ tự row do câu `SELECT` trả về **không phải contract** để đối chiếu trực tiếp: khi lập báo cáo, cần nhóm theo `kind`, sắp theo `position` và so từng loại. Một bản diff đúng phải hiểu **vai trò** của cột; nếu chỉ so danh sách tên theo alphabet thì không phát hiện được việc đổi thứ tự clustering key.

Có thể xem tùy chọn của bảng:

~~~sql
SELECT keyspace_name, table_name, default_time_to_live,
       compaction, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'telemetry'
  AND table_name = 'events_by_device_day';
~~~

Với chỉ mục, các bảng hệ thống như `system_schema.indexes` hữu ích để xác định tên, target và options tùy phiên bản Cassandra. Nếu dùng Storage-Attached Index hoặc các tính năng mới, phải đối chiếu cách thể hiện index trong **phiên bản server thực tế**.

**Lưu ý về version:** cột và nội dung tùy chọn ở bảng hệ thống có thể thay đổi giữa các phiên bản Cassandra. Công cụ audit cần được kiểm thử trên đúng phiên bản đang vận hành, không nên viết parser cố định dựa vào `SELECT *` mà không có kiểm soát schema.

## 7. Kiểm tra bằng Java driver: metadata của cluster

Để tự động kiểm tra mà không cần phân tích output văn bản của `cqlsh`, Java driver 4.x cung cấp schema metadata:

- `CqlSession.getMetadata()`: metadata nhìn thấy từ session.
- `Metadata.getKeyspace(...)`: tìm keyspace bằng `CqlIdentifier`.
- `KeyspaceMetadata.getTable(...)`: tìm bảng.
- `TableMetadata.getPartitionKey()`: thứ tự cột partition key.
- `TableMetadata.getClusteringColumns()`: cột clustering và hướng sắp xếp.
- `TableMetadata.getColumn(...)`: tìm kiểu dữ liệu từng cột.

Ví dụ Spring component kiểm tra một **schema contract** bắt buộc. Đây là kiểm tra cấu trúc tại thời điểm gọi; bạn có thể dùng trong integration test hoặc một bước pre-deploy có quyền read schema.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.schema.ClusteringOrder;
import com.datastax.oss.driver.api.core.metadata.schema.ColumnMetadata;
import com.datastax.oss.driver.api.core.metadata.schema.KeyspaceMetadata;
import com.datastax.oss.driver.api.core.metadata.schema.TableMetadata;
import com.datastax.oss.driver.api.core.type.DataType;
import com.datastax.oss.driver.api.core.type.DataTypes;

public final class EventSchemaVerifier {
    private EventSchemaVerifier() { }

    public static void verify(CqlSession session) {
        KeyspaceMetadata keyspace = session.getMetadata()
            .getKeyspace(CqlIdentifier.fromCql("telemetry"))
            .orElseThrow(() -> new IllegalStateException(
                "Thiếu keyspace telemetry"));

        TableMetadata table = keyspace
            .getTable(CqlIdentifier.fromCql("events_by_device_day"))
            .orElseThrow(() -> new IllegalStateException(
                "Thiếu bảng events_by_device_day"));

        List<String> partitionKeys = table.getPartitionKey().stream()
            .map(col -> col.getName().asInternal())
            .collect(Collectors.toList());

        expect("partition keys", partitionKeys,
               List.of("device_id", "event_day"));

        Map<ColumnMetadata, ClusteringOrder> clustering =
            table.getClusteringColumns();

        List<String> clusteringNames = clustering.keySet().stream()
            .map(col -> col.getName().asInternal())
            .collect(Collectors.toList());

        expect("clustering keys", clusteringNames,
               List.of("event_time", "event_id"));

        expect("clustering order",
               List.copyOf(clustering.values()),
               List.of(ClusteringOrder.DESC, ClusteringOrder.ASC));

        expectType(table, "device_id", DataTypes.UUID);
        expectType(table, "event_day", DataTypes.DATE);
        expectType(table, "event_time", DataTypes.TIMESTAMP);
        expectType(table, "event_id", DataTypes.UUID);
        expectType(table, "event_type", DataTypes.TEXT);
        expectType(table, "payload", DataTypes.TEXT);
        expectType(table, "received_at", DataTypes.TIMESTAMP);
    }

    private static void expectType(
            TableMetadata table, String columnName, DataType expected) {
        ColumnMetadata column = table
            .getColumn(CqlIdentifier.fromCql(columnName))
            .orElseThrow(() -> new IllegalStateException(
                "Thiếu cột " + columnName));

        expect("type of " + columnName,
               column.getType(), expected);
    }

    private static void expect(String label,
                               Object actual, Object expected) {
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                label + ": expected=" + expected + ", actual=" + actual);
        }
    }
}
~~~

Đối với driver version mà dự án đang dùng, cần kiểm tra thứ tự do `TableMetadata.getClusteringColumns()` trả về và API enum `ClusteringOrder`. Mẫu này dựa vào driver 4.x và logic so thứ tự khai báo, không dành cho mọi thế hệ driver Cassandra.

**Ý nghĩa của phép kiểm tra:**

- Nếu thiếu keyspace/bảng, báo rõ đối tượng nào.
- Nếu đổi partition key hoặc thứ tự clustering, kiểm tra thất bại trước khi ứng dụng bắt đầu phục vụ traffic.
- Nếu cột có tên giống nhau nhưng kiểu dữ liệu khác, lỗi được báo ở đúng cột.
- Nếu schema chỉ có **thêm** regular column chưa sử dụng, kiểm tra cơ sở vẫn có thể cho qua; đây là chính sách tương thích có chủ đích, không phải phép so toàn bộ catalog.

Muốn kiểm tra `default_time_to_live`, compaction, index, replication hoặc UDT, mở rộng contract tương ứng hoặc truy vấn metadata/catalog phù hợp. Không nên kết luận “toàn schema khớp 100%” chỉ từ đoạn ví dụ trên, vì nó chỉ xác minh các thành phần đã liệt kê.

### Khi nào metadata có thể chưa phản ánh thay đổi mới?

Schema metadata của driver được cập nhật thông qua cơ chế theo dõi cluster và có thể có độ trễ sau DDL. Nếu vừa áp migration rồi đọc ngay, kết quả có thể chưa kịp cập nhật. Một bước deploy đúng cần **chờ schema agreement**, đợi metadata cập nhật hoặc tạo session mới ở bước kiểm tra độc lập, và chỉ sau đó chạy verifier. Không dùng một khoảng `sleep(1000)` cố định như bảo đảm schema đã sẵn sàng.

## 8. Đối chiếu với Spring Data mapping thay vì đoán theo tên field

Việc schema thực có `event_time timestamp` chưa bảo đảm entity đọc đúng nếu mapping Java trỏ nhầm sang `created_at`. Phải kiểm tra từ **hai hướng**:

1. **Spring Data → Cassandra:** mỗi `@Table`, `@PrimaryKeyColumn`, `@Column` có đích CQL tồn tại và kiểu phù hợp.
2. **Cassandra → Spring Data:** những khác biệt trên cluster đã được nhận diện, đặc biệt thay đổi khóa, type, TTL hoặc index có thể ảnh hưởng truy vấn.

Có thể lập bảng mapping từ source và review cùng bản migration:

| Spring Data | Vai trò | DDL mong đợi | Kết quả bắt buộc |
| --- | --- | --- | --- |
| `DeviceEventKey.deviceId` | PARTITIONED, thứ tự 0 | `device_id uuid` | Khớp |
| `DeviceEventKey.eventDay` | PARTITIONED, thứ tự 1 | `event_day date` | Khớp |
| `DeviceEventKey.eventTime` | CLUSTERED, DESC | `event_time timestamp` | Khớp |
| `DeviceEventKey.eventId` | CLUSTERED, ASC | `event_id uuid` | Khớp |
| `DeviceEvent.eventType` | Regular column | `event_type text` | Khớp |
| `DeviceEvent.receivedAt` | Regular column | `received_at timestamp` | Khớp |

Tránh chỉ kiểm tra `@Column`. Các trường nằm bên trong `@PrimaryKeyClass` cũng là cột của bảng và có ý nghĩa đặc biệt. Ngược lại, đừng giả định một property Java không có `@Column` chắc chắn không được mapping: Spring Data có naming strategy và cơ chế mapping mặc định. Muốn contract minh bạch, khai báo tên CQL tường minh cho những cột quan trọng.

**Tên và chữ hoa/chữ thường:** Cassandra thường chuẩn hóa CQL identifier không đặt trong dấu ngoặc kép thành chữ thường. Identifier được quote có thể phân biệt chữ hoa/chữ thường. Ví dụ `event_time` và `"eventTime"` là tên khác nhau. Khi đối chiếu metadata, dùng `CqlIdentifier` và quy tắc naming thực tế thay vì chỉ so chuỗi hiển thị.

## 9. Dùng repository và CassandraTemplate để chứng minh schema hoạt động

Schema metadata giúp phát hiện lệch **cấu trúc**. Một kiểm thử dữ liệu nhỏ sẽ xác minh Spring Data mapper thực sự ghi và đọc đúng bảng.

Ví dụ repository:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {
}
~~~

Ví dụ đọc theo partition bằng `CassandraTemplate`:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class EventLookup {
    private final CassandraTemplate template;

    public EventLookup(CassandraTemplate template) {
        this.template = template;
    }

    public List<DeviceEvent> readDay(UUID deviceId, LocalDate day) {
        Query query = Query
            .query(Criteria.where("device_id").is(deviceId))
            .and(Criteria.where("event_day").is(day))
            .limit(50);

        return template.select(query, DeviceEvent.class);
    }
}
~~~

Hàm trên chỉ nên chạy khi bucket ngày đã biết; nó không biến query thành tìm kiếm mọi `device_id` hoặc `event_type`. Schema kiểm tra **có đúng primary key** và test nghiệp vụ kiểm tra **truy vấn dùng đúng primary key** là hai bước bổ sung cho nhau.

### Bài smoke test có ý nghĩa

Ghi một sự kiện mẫu bằng repository và đọc lại bằng khóa đầy đủ:

~~~java
UUID device = UUID.fromString(
    "22222222-2222-4222-8222-222222222222");
UUID event = UUID.fromString(
    "44444444-4444-4444-8444-444444444444");

Instant occurredAt = Instant.parse("2026-11-25T09:30:00Z");
LocalDate day = LocalDate.of(2026, 11, 25);

DeviceEventKey key =
    new DeviceEventKey(device, day, occurredAt, event);

repository.save(new DeviceEvent(
    key, "TEMPERATURE", "{\"celsius\":25.4}", Instant.now()));

DeviceEvent readBack = repository.findById(key)
    .orElseThrow(() -> new AssertionError("Không đọc được sự kiện"));
~~~

Với môi trường test, phải có dữ liệu/cấu hình cô lập; dùng UUID khác nhau hoặc cleanup có kiểm soát để test lặp lại không tác động dữ liệu thật. Kiểm thử này chứng minh cơ bản rằng mapping ghi/đọc đúng. Nó chưa chứng minh thứ tự timeline, paging nhiều trang hay hiệu năng dưới tải; cần test tiếp theo hợp đồng truy vấn.

## 10. Phân loại thay đổi schema: tương thích hay cần đổi bảng?

Không phải thay đổi nào cũng có cùng rủi ro. Khi review một PR hoặc migration, hãy phân loại:

| Thay đổi | Khả năng thực hiện trực tiếp | Tác động cần kiểm tra |
| --- | --- | --- |
| Thêm regular column mới | Thường có thể dùng `ALTER TABLE ... ADD` nếu kiểu hợp lệ | Row cũ không có giá trị; application phải chấp nhận null/thiếu |
| Thêm index phù hợp | Cần đánh giá loại index và phiên bản Cassandra | Thời gian xây index, tải và độ trễ query |
| Đổi TTL mặc định | Có thể chỉnh table option khi phù hợp | Ảnh hưởng đến dữ liệu **ghi sau thay đổi**, tombstone và retention |
| Đổi compaction strategy | Thay đổi table option có thể hỗ trợ | Tải compaction, format/overlap, rolling performance |
| Đổi tên regular column | Phụ thuộc kiểu, phiên bản và cách migration | Phiên bản ứng dụng cũ có thể vẫn đọc tên cũ |
| Đổi type cột | Bị giới hạn mạnh; không được suy diễn tùy ý | Compatibility converter/driver, dữ liệu hiện hữu |
| Đổi partition key | **Không sửa trực tiếp như một ALTER thông thường** | Cần bảng mới, backfill, đổi đường ghi/đọc |
| Đổi clustering columns/thứ tự | **Không sửa trực tiếp như một ALTER thông thường** | Cần bảng mới, backfill và kiểm tra paging/sort |
| Đổi query từ device-day sang site-day | Không phải chỉ thêm field | Phải đánh giá access pattern và bảng đọc mới |

Ví dụ thêm cột đơn giản:

~~~sql
ALTER TABLE telemetry.events_by_device_day
ADD firmware_version text;
~~~

Sau đó mới triển khai entity có:

~~~java
@Column("firmware_version")
private String firmwareVersion;
~~~

Nếu ứng dụng mới được bật **trước** khi migration chạy, việc ghi/read field mới có thể thất bại vì cột chưa tồn tại. Cách triển khai tương thích thường là migration trước, rồi mới bật code sử dụng cột; nếu chạy song song hai phiên bản ứng dụng thì phải kiểm tra cả hai vẫn hoạt động.

Một số thay đổi CQL có cú pháp phụ thuộc phiên bản Cassandra; luôn đối chiếu tài liệu đúng phiên bản server và chạy trên staging. Không tự viết `ALTER TABLE ... ALTER PRIMARY KEY` vì Cassandra không hỗ trợ đổi khóa chính theo cách đó.

## 11. Schema agreement: cluster đã nhìn cùng một cấu trúc chưa?

Cassandra là hệ phân tán. Khi chạy DDL, thay đổi schema có thể cần thời gian lan truyền giữa các node. Nếu node A đã nhận bảng mới nhưng node B chưa nhận, ứng dụng có thể gặp lỗi không nhất quán theo đường kết nối.

**Schema agreement** là trạng thái các node liên quan đã hội tụ về cùng schema version. Trước khi mở traffic trên schema mới, cần:

1. Xác nhận cluster và các node dự kiến đang ở trạng thái hoạt động.
2. Áp migration theo quy trình có quyền điều khiển rõ ràng, tránh nhiều ứng dụng cùng sửa schema.
3. Chờ công cụ quản trị/driver xác nhận schema agreement trong giới hạn thời gian phù hợp.
4. Đọc lại schema bằng metadata sau khi đã hội tụ.
5. Chạy smoke test cho truy vấn chính trên keyspace/bảng đã migration.

Công cụ quản trị Cassandra có thể giúp kiểm tra:

~~~bash
nodetool status
nodetool describecluster
~~~

`nodetool status` cho thấy trạng thái node; `nodetool describecluster` có thể hiển thị thông tin schema versions của cluster. Kết quả cần được diễn giải theo phiên bản Cassandra, topology, node đang down và trạng thái có thể truy cập. Không chỉ dựa vào một lệnh để khẳng định toàn bộ hệ thống đã sẵn sàng.

**Phân biệt:** schema agreement không chứng minh đã backfill đủ dữ liệu. Một bảng mới có DDL đúng và mọi node cùng schema nhưng vẫn có thể rỗng hoặc thiếu hàng triệu row lịch sử.

### Không đồng nhất trạng thái “tạo thành công” và “có thể query ngay”

Tránh quy trình:

~~~text
1. App A chạy CREATE/ALTER TABLE
2. Không chờ agreement
3. App B ngay lập tức SELECT cột mới trên một node khác
4. Lỗi bất thường rồi tăng timeout để khắc phục
~~~

Thay vào đó, kiểm soát DDL theo migration và chặn bước deploy sử dụng schema mới cho đến khi cluster đã hội tụ và verifier xác nhận.

## 12. SchemaAction trong Spring Boot: dùng đúng môi trường

Spring Boot có thuộc tính cấu hình cho hành động schema của Spring Data Cassandra. Môi trường production thường chọn:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

`datacenter1` chỉ là ví dụ: phải khớp tên datacenter thực tế. Chạy migration tạo keyspace/bảng trước; `schema-action: none` tránh để ứng dụng tự tạo/sửa bảng khi khởi động.

Vì sao không tự động “sync schema” bằng entity trong production?

- Thay đổi khóa chính là quyết định về phân phối dữ liệu và access pattern, không thể sửa bằng một thao tác đồng bộ đơn giản.
- Nhiều instance ứng dụng khởi động cùng lúc có thể cạnh tranh DDL hoặc nhìn thấy schema chưa hội tụ.
- DDL không chuyển đổi dữ liệu cũ sang partition key mới.
- Cấu hình tạo lại/xóa bảng, nếu bị bật nhầm trong môi trường có dữ liệu, có thể gây mất dữ liệu hoặc downtime.

Tùy Spring Boot/Spring Data Cassandra version, các giá trị `schema-action` có thể bao gồm chế độ tạo và tạo lại bảng. **Không dùng các chế độ tạo lại mang tính phá hủy với dữ liệu thật**. Bài học này cố ý không dùng cơ chế tự tạo bảng để tránh che giấu khác biệt giữa migration mong đợi và schema thực tế.

Điểm cần nhớ: `schema-action: none` **không tự kiểm tra đúng/sai schema**. Muốn phát hiện lệch khi deploy, cần bước verifier, test hoặc quy trình đối chiếu riêng.

## 13. Thay khóa phân vùng: bắt buộc lập kế hoạch chuyển bảng

Giả sử yêu cầu nghiệp vụ mới là “50 cảnh báo mới nhất của **một chi nhánh** trong ngày”, thay vì “lịch sử của **một thiết bị** trong ngày”. Không thể chỉ thêm `site_id` vào entity rồi truy vấn:

~~~sql
-- Không phù hợp với primary key của bảng cũ:
SELECT * FROM telemetry.events_by_device_day
WHERE site_id = 33333333-3333-4333-8333-333333333333;
~~~

Bảng hiện tại không có `site_id` trong partition key. Tăng timeout, dùng `CassandraTemplate` hoặc thêm `ALLOW FILTERING` không làm phép đọc trở thành truy vấn có chi phí dự đoán được.

Nếu nghiệp vụ cần truy vấn thường xuyên, thiết kế bảng theo truy vấn mới, ví dụ:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alerts_by_site_day (
    site_id    uuid,
    event_day  date,
    event_time timestamp,
    device_id  uuid,
    event_id   uuid,
    event_type text,
    message    text,
    PRIMARY KEY ((site_id, event_day), event_time, device_id, event_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC, event_id ASC
);
~~~

Schema này minh họa khóa theo `(site_id, event_day)`. Trong hệ thống đa tenant, nên đưa `tenant_id` vào partition key và cơ chế phân quyền để tách dữ liệu. Với tải cảnh báo lớn, bucket ngày có thể nóng, cần đo row/partition và cân nhắc bucket theo giờ hoặc shard có kiểm soát.

### Kế hoạch chuyển đổi dạng expand–migrate–contract

~~~mermaid
flowchart LR
    A["Bảng cũ và API Q1"] --> B["Tạo bảng đọc Q2"]
    B --> C["Ghi projection Q2 cho sự kiện mới"]
    C --> D["Backfill lịch sử"]
    D --> E["Đối soát nguồn và projection"]
    E --> F["Canary API Q2"]
    F --> G["Mở traffic"]
    G --> H["Duy trì và dọn đường cũ khi an toàn"]
~~~

Không bỏ qua bước backfill nếu màn hình mới phải đọc dữ liệu lịch sử. Hai bảng thường ở **những partition khác nhau**; thao tác Java gọi hai lệnh `save` không tạo transaction ACID nhiều bảng. Nếu ghi Q1 thành công còn Q2 lỗi, cần retry/replay và reconciliation theo event ID ổn định.

Khi làm schema diff, “bảng Q1 khác Q2” là **sự thay đổi thiết kế đã được chấp nhận**, không nên “sửa cho giống” bằng cách ép annotation cũ. Contract của mỗi bảng phải gắn với query cụ thể mà bảng đó phục vụ.

## 14. Kiểm tra index, UDT và table options khi hệ thống phức tạp hơn

Ví dụ trên chỉ sử dụng các cột scalar. Dự án thật có thể có:

- **Index**: secondary index, SAI hoặc giải pháp index phụ thuộc phiên bản Cassandra.
- **UDT (user-defined type)**: các field lồng nhau và cách dùng `frozen`.
- **Collections**: `list`, `set`, `map`, có thể có ràng buộc về cập nhật và truy vấn.
- **Static columns**: giá trị dùng chung cho các row trong partition.
- **Counter tables**: quy tắc cập nhật khác với bảng dữ liệu thường.
- **Table options**: default TTL, compaction strategy, tombstone-related options, caching, compression và gc grace.

Ví dụ schema:

~~~sql
CREATE TYPE IF NOT EXISTS telemetry.sensor_location (
    latitude double,
    longitude double
);

-- Ví dụ minh họa UDT, không tự động thêm vào bảng hiện có:
-- ALTER TABLE telemetry.events_by_device_day
-- ADD location frozen<sensor_location>;
~~~

Khi so UDT, cần đối chiếu **tên field, thứ tự/kiểu field và cách lưu frozen**; khi so collection, cần đối chiếu kiểu phần tử. Với một số thay đổi UDT, quy định tương thích và cách cập nhật khác nhau theo version server, vì vậy phải dùng migration kiểm chứng thay vì tự giả định đổi type sẽ an toàn.

Với TTL mặc định:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH default_time_to_live = 2592000;
~~~

Thay đổi này tác động chính sách hết hạn cho các lần ghi theo quy tắc TTL của Cassandra, nhưng **không nên suy ra toàn bộ dữ liệu cũ lập tức có TTL mới**. Hãy kiểm tra cách ghi có đặt TTL riêng hay không, retention thực tế, tombstones và compaction. Việc một schema diff “khớp `default_time_to_live`” chưa chứng minh dữ liệu đã được xóa theo đúng chính sách.

## 15. Báo cáo schema drift nên thể hiện những gì?

Schema drift là chênh lệch giữa **contract đã chốt** và **cấu trúc thực tế**. Một báo cáo hữu ích cần chỉ ra mức độ tác động để quyết định có chặn deploy không.

Ví dụ kết quả giả định:

| Kiểm tra | Mong đợi | Thực tế | Xử lý |
| --- | --- | --- | --- |
| Bảng | `events_by_device_day` tồn tại | Có | PASS |
| Partition key | `device_id, event_day` | `device_id` | **BLOCK**: phân phối khác thiết kế |
| Clustering key | `event_time DESC, event_id ASC` | `event_time ASC, event_id ASC` | **BLOCK**: thứ tự timeline khác |
| `event_time` | `timestamp` | `text` | **BLOCK**: sai kiểu và mapping |
| `received_at` | `timestamp` | Chưa có | **BLOCK** nếu version ứng dụng sử dụng |
| `firmware_version` | Không bắt buộc ở version hiện tại | Có thêm | Có thể chấp nhận, cần ghi nhận |
| Default TTL | 30 ngày (nếu contract quy định) | 0 | Cảnh báo/block tùy chính sách retention |

Phân loại đề xuất:

- **BLOCK:** thiếu keyspace/table bắt buộc, sai partition key/clustering key, kiểu không tương thích, thiếu cột code đang sử dụng, schema agreement chưa đạt.
- **REVIEW:** khác table options ảnh hưởng retention/performance, index khác contract, có column/index lạ hoặc migration không nằm trong danh mục.
- **ALLOW:** khác biệt đã được ghi nhận và bảo đảm tương thích trong giai đoạn rollout song song.

Nên lưu trong log/CI tên môi trường, keyspace, table, thời điểm kiểm tra, migration version áp dụng và phiên bản ứng dụng **không chứa bí mật kết nối**. Đừng chỉ log “schema mismatch” mà không nêu tên cột và giá trị expected/actual.

## 16. Tích hợp kiểm tra vào CI và quy trình phát hành

Một quy trình kỹ thuật có thể triển khai như sau:

1. **Review migration và mapping trong cùng PR.** Người review đối chiếu cột, primary key, clustering order, index và truy vấn.
2. **Khởi tạo Cassandra kiểm thử** với phiên bản server tương đương môi trường vận hành, ví dụ qua Testcontainers hoặc cluster test chuyên dụng.
3. **Áp toàn bộ migration theo thứ tự** trên keyspace sạch. Không cho entity tự tạo schema để che giấu thiếu migration.
4. **Đợi schema agreement** rồi lấy metadata.
5. **Chạy schema verifier** như mục 7.
6. **Chạy integration test ghi/đọc** bằng repository và `CassandraTemplate`, kèm phân trang và CQL trên partition mẫu.
7. **Kiểm tra migration trên dữ liệu hiện hữu** ở môi trường staging: chạy lại theo trình tự upgrade có hỗ trợ, quan sát tốc độ và khả năng rollback.
8. **Phát hành có kiểm soát**: migrate trước, xác minh, rồi rollout ứng dụng; theo dõi query errors, timeout và schema-related metrics.

Các lệnh tham khảo cho người học khi dự án có Gradle Wrapper và test đã cấu hình:

~~~bash
./gradlew test
./gradlew integrationTest
~~~

`integrationTest` **không phải task mặc định** của mọi dự án Gradle; nó chỉ hoạt động khi build đã định nghĩa task/source set/plugin phù hợp. Nếu không có, chạy integration test bằng task hiện có. Bài này không yêu cầu người học tự sửa cấu trúc build ngoài phạm vi bài học.

**Không cần chạy lại mọi test chỉ vì schema có thêm một regular column không sử dụng**, nhưng cần có ít nhất một kiểm thử tương thích và metadata verifier cho contract quan trọng. Với thay đổi khóa hoặc migration nhiều bảng, phải mở rộng kiểm thử và chạy kịch bản dữ liệu thực tế.

### Kiểm tra trước và sau deploy

~~~text
Trước deploy:
  Migration dự kiến?
  Cluster có đúng phiên bản Cassandra?
  Metadata và cột/khóa có khớp?
  Schema agreement đạt?
  App version hiện tại có tương thích thay đổi?

Sau deploy:
  Repository/CassandraTemplate đọc ghi được?
  CQL có lỗi Unknown column/InvalidQuery?
  Query latency và timeout có tăng?
  Dữ liệu có đúng bucket/partition?
  Job backfill và projection có lag hoặc thiếu row?
~~~

Một quy trình tốt cũng xác định **người chịu trách nhiệm** khi drift xảy ra: chủ migration, chủ ứng dụng, DBA/SRE hoặc đội platform. Không để nhiều service tự tranh nhau “sửa schema” lúc startup.

## 17. Khi schema lệch trên production, xử lý theo triệu chứng

| Hiện tượng | Khả năng cao | Điều tra trước khi sửa |
| --- | --- | --- |
| `unconfigured table` hoặc `unconfigured keyspace` | Chưa áp migration, sai keyspace hoặc metadata chưa cập nhật | Xem keyspace/table trên node, schema agreement, connection config |
| `Undefined column name` | App dùng cột mới trước migration hoặc mapping nhầm tên | So `@Column`/`@PrimaryKeyColumn` với `system_schema.columns` |
| `InvalidQueryException` về partition key | CQL không khớp khóa chính thật | So `PRIMARY KEY` và truy vấn, thiết kế lại access pattern nếu cần |
| Lỗi decode/mapping kiểu | CQL type khác converter Java | So `type` thật, converter và dependency version |
| API trả kết quả theo thứ tự lạ | Clustering order khác hoặc ứng dụng ghép nhiều partition sai | So `CLUSTERING ORDER BY` và logic paging |
| Chỉ một phần node báo thiếu bảng | Schema propagation hoặc topology có vấn đề | Kiểm tra schema agreement, trạng thái node và logs |
| Truy vấn chậm sau migration | Index, compaction, TTL, hot partition thay đổi | So table options và quan sát p95/p99/tombstone |
| Row mới có nhưng row cũ không đủ | Backfill/replay chưa hoàn tất | Đối soát dữ liệu, không chỉ đối chiếu DDL |

Đừng chữa lỗi thiếu column bằng cách đặt `schema-action: recreate` trên production. Điều này có thể dẫn đến mất dữ liệu và bỏ qua nguyên nhân migration. Trước hết phân loại lỗi theo **cấu trúc**, **hội tụ schema**, **mô hình truy vấn** hoặc **dữ liệu**.

## 18. Bộ tiêu chí nghiệm thu một schema migration

Một thay đổi được xem là sẵn sàng khi có bằng chứng:

| Tiêu chí | Bằng chứng tối thiểu |
| --- | --- |
| Khóa đúng | Schema verifier so được partition key/clustering key/thứ tự |
| Kiểu dữ liệu đúng | Kiểm tra tất cả cột mà entity/truy vấn sử dụng |
| Truy vấn phù hợp | CQL có đầy đủ partition key, test limit/paging/thứ tự |
| Migration tái lập | Staging/test tạo lại cùng schema từ scripts |
| Schema hội tụ | Kiểm tra agreement và metadata sau DDL |
| App cũ/mới tương thích | Kiểm thử giai đoạn deploy song song nếu có |
| Dữ liệu được bảo toàn | Có kết quả backfill/reconciliation khi đổi bảng |
| Quyền/retention đúng | Kiểm tra role, TTL và các tùy chọn cần quản lý |
| Quan sát vận hành | Có log lỗi schema, query latency, timeout, các cảnh báo liên quan |
| Kế hoạch rollback | Đã mô tả bước xử lý nếu đổi mã ứng dụng hoặc projection bị lỗi |

Với schema mới hoàn toàn, kiểm thử chỉ vài row chứng minh khả năng ánh xạ, không chứng minh được partition size và throughput. Với thay đổi lớn, cần thử trên dữ liệu và phân bố traffic đại diện cho thiết bị có tần suất cao nhất, không chỉ trung bình.

## 19. Bài tập thực hành

### Bài A — Phát hiện sai partition key

Một migration trên môi trường test tạo:

~~~sql
PRIMARY KEY ((device_id), event_day, event_time, event_id)
~~~

Nhưng mapping yêu cầu:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

Hãy chỉ ra ít nhất ba hệ quả về phân phối dữ liệu, truy vấn `WHERE device_id = ? AND event_day = ?` và partition size. Viết checklist để phát hiện sai khác bằng `system_schema.columns` hoặc `TableMetadata`. Có thể dùng `ALTER TABLE` để đổi trực tiếp không?

### Bài B — Sai kiểu dữ liệu và tên cột

Ứng dụng dùng `@Column("received_at") Instant`, nhưng schema thật có `received_time text`. Hãy xác định vì sao một integration test ghi/read sẽ thất bại, những bằng chứng cần thu thập và trình tự migration tương thích để thêm `received_at timestamp` mà không phá vỡ phiên bản ứng dụng cũ.

### Bài C — Tranh chấp lúc rollout

Cluster có ba node; migration vừa thêm `firmware_version`, hai node đã nhận schema mới, một node còn hiển thị version cũ. Hãy mô tả tại sao không nên mở ngay traffic mới, cách kiểm tra schema agreement và vì sao chỉ kiểm tra `DESCRIBE TABLE` trên một node không đủ.

### Bài D — Đổi mẫu truy vấn

Product muốn xem 100 cảnh báo gần nhất theo `siteId`. Đề xuất bảng mới với partition key phù hợp, giải thích nguồn dữ liệu để backfill, cách tránh event trùng khi retry, và danh sách kiểm tra schema/data parity trước khi bật API.

### Bài E — Tạo schema contract có thể chạy tự động

Dựa trên `EventSchemaVerifier`, bổ sung kiểm tra loại `received_at timestamp`, sự tồn tại của `event_type text` và một quy tắc phát hiện bất kỳ khóa clustering khác contract. Nêu trường hợp phép kiểm tra nên **chặn deploy**, và trường hợp có thêm regular column nhưng vẫn được phép triển khai.

### Bài F — Tách schema check khỏi data check

Một bảng có `PRIMARY KEY`, column types và options đều khớp; tuy nhiên dữ liệu từ hai ngày trước chưa được backfill. Hãy lập hai bộ kiểm tra riêng: một bộ cho **schema agreement/mapping**, một bộ cho **completeness và consistency của dữ liệu**. Giải thích tại sao hai kết quả có thể trái ngược.

**Hoàn thành bài khi:** bạn đọc được schema thật, đối chiếu chính xác khóa/kiểu/ordering với Spring Data mapping, biết chờ schema agreement, phân biệt thêm cột với đổi khóa, và có kế hoạch migration–test–rollout kiểm chứng được.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): `CREATE TABLE`, `ALTER TABLE`, primary key và table options.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): thiết kế schema theo access pattern.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `DESCRIBE` và thao tác trên schema.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn` và converter.
- [Spring Data Cassandra — Schema Management](https://docs.spring.io/spring-data/cassandra/reference/cassandra/schema-management.html): cách Spring Data quản lý schema.
- [Spring Boot — Data / NoSQL](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình `spring.cassandra.*`.
- [Java Driver 4 — Schema Metadata](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metadata/schema/): `TableMetadata`, `KeyspaceMetadata` và thông tin schema.
