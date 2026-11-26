# CassandraBatchOperations và batchOps của Template

Trong **Spring Data Cassandra**, API `CassandraBatchOperations` và phương thức `batchOps()` của `CassandraTemplate` cho phép **gom nhiều mutation** (`INSERT`, `UPDATE`, `DELETE`) thành **một CQL batch**. API này giúp diễn đạt những thay đổi có liên quan và tái sử dụng entity mapping của Spring Data, nhưng **không nên được hiểu như JDBC batch để tăng tốc mọi thao tác ghi**, cũng **không phải transaction SQL đa bảng có rollback và isolation**.

Để sử dụng batch đúng, cần hiểu ba tầng:

1. **CQL BATCH**: Cassandra xử lý một tập mutation cùng request, với ngữ nghĩa khác nhau giữa **LOGGED**, **UNLOGGED** và **COUNTER** batch.
2. **Spring Data `CassandraBatchOperations`**: một đối tượng tích lũy các thao tác trên entity; `batchOps()` tạo phiên gom thao tác, `execute()` gửi batch.
3. **Mô hình dữ liệu phân tán**: partition key, replica, consistency level, timestamp, tombstone, timeout và retry vẫn quyết định kết quả thực tế.

Bài thuộc chương **Batch** của module **SPRING_DATA_CASSANDRA**, nơi ứng dụng làm việc với Cassandra qua entity mapping, repository, `CassandraTemplate` và truy vấn CQL. Các ví dụ hướng đến Spring Boot 3.x / Spring Data Cassandra 4.x và Java Driver 4.x; **chữ ký overload, tùy chọn batch và API reactive cần đối chiếu với phiên bản chính xác của dự án**.

## 1. BATCH của Cassandra dùng để giải quyết điều gì?

Giả sử nghiệp vụ ghi **hai sự kiện liên quan của cùng một tenant trong một ngày**. Ta muốn gửi chúng thành một nhóm thao tác thay vì gọi riêng từng câu lệnh:

~~~text
Không dùng batch:
  template.insert(eventA) ------> request 1
  template.insert(eventB) ------> request 2

Dùng batchOps:
  batch = template.batchOps()
  batch.insert(eventA)
  batch.insert(eventB)
  batch.execute() --------------> một CQL batch request
~~~

Đó là **nhóm thao tác ghi**, không phải một cơ chế tự gộp mọi lời gọi database thành transaction dài. Khi tạo batch, ứng dụng vẫn cần xác định:

- Hai mutation có thuộc **cùng partition** không?
- Có yêu cầu chúng được ghi chung theo ngữ nghĩa nghiệp vụ không?
- Nếu request timeout, hệ thống sẽ kiểm tra và thử lại như thế nào?
- Mỗi mutation có cần TTL, write timestamp hay điều kiện `IF` riêng không?
- Tổng kích thước batch có đủ nhỏ để tránh gây tải cho coordinator và replica không?

**Không dùng batch để sửa truy vấn thiếu partition key hoặc giải quyết một partition quá lớn.** Cassandra vẫn định tuyến từng mutation theo khóa và replication của bảng.

## 2. Cú pháp CQL: BEGIN BATCH ... APPLY BATCH

CQL hỗ trợ nhiều câu lệnh sửa dữ liệu trong một batch:

~~~sql
BEGIN BATCH
    INSERT INTO telemetry_ks.events_by_tenant_day (
        tenant_id, event_day, event_time, event_id,
        event_type, payload
    ) VALUES (?, ?, ?, ?, ?, ?);

    INSERT INTO telemetry_ks.events_by_tenant_day (
        tenant_id, event_day, event_time, event_id,
        event_type, payload
    ) VALUES (?, ?, ?, ?, ?, ?);
APPLY BATCH;
~~~

Đây là **CQL minh họa câu lệnh có bind markers** dành cho prepared/bound statements; để chạy trực tiếp trong `cqlsh` phải dùng các giá trị literal hợp lệ thay cho `?`. Các bảng/kiểu dữ liệu sẽ được khai báo ở mục tiếp theo.

Điểm đáng chú ý:

- `BEGIN BATCH` mặc định là **LOGGED BATCH** trong CQL.
- `APPLY BATCH` thực thi tập mutation đã đưa vào.
- Batch dành cho câu lệnh ghi, **không chứa SELECT** như một giao dịch đọc/ghi SQL bất kỳ.
- Mỗi `INSERT`, `UPDATE`, `DELETE` vẫn phải đúng kiểu dữ liệu và đầy đủ khóa theo yêu cầu Cassandra.
- Một batch lớn có thể kém hơn nhiều request nhỏ, đặc biệt khi các mutation rải nhiều partition.

Không kỳ vọng Cassandra thực thi các câu lệnh trong batch theo một **thứ tự nghiệp vụ tuần tự được bảo đảm**. Nếu hai statement ghi **cùng cell với hai giá trị khác nhau**, kết quả còn phụ thuộc write timestamp và quy tắc xung đột; không dùng thứ tự dòng CQL trong batch để xây state machine.

## 3. LOGGED, UNLOGGED và COUNTER batch

| Loại batch | Cú pháp CQL | Ý nghĩa chính | Cần tránh |
| --- | --- | --- | --- |
| **LOGGED** | `BEGIN BATCH` hoặc `BEGIN LOGGED BATCH` | Có **batch log** hỗ trợ các mutation trong batch được hoàn tất sau sự cố theo cơ chế batch | Không coi là tối ưu mặc định cho bulk insert đa partition |
| **UNLOGGED** | `BEGIN UNLOGGED BATCH` | Không dùng batch log cho bảo đảm nguyên tử đa partition; thường phù hợp hơn với mutation cùng partition khi có lý do gom | Không xem là atomic giữa nhiều partition |
| **COUNTER** | `BEGIN COUNTER BATCH` | Dành riêng cho mutation của **counter** | Không trộn counter với mutation thường; retry tăng counter có thể đếm đôi |

### LOGGED batch: tính nguyên tử không giống SQL isolation

Với **logged batch**, Cassandra ghi nhận thông tin batch để có thể phục hồi các mutation nếu coordinator gặp lỗi sau những bước phù hợp của quy trình. Mục tiêu là **all-or-eventually-applied** đối với các mutation của batch dưới những giả định vận hành hợp lệ.

Nhưng **không có transaction isolation tổng quát xuyên nhiều partition**. Trong lúc batch đang được áp dụng hoặc khi replica chưa đồng bộ, client khác có thể thấy một phần thay đổi trước phần còn lại. Nếu client nhận timeout, không thể khẳng định rằng cả batch đã bị rollback; cần xử lý **kết quả chưa chắc chắn**.

### UNLOGGED batch: không phải “logged nhưng nhanh hơn vô điều kiện”

Không tạo batch log thường giảm một phần chi phí điều phối, **nhưng cũng bỏ bảo đảm phục hồi nguyên tử đa partition**. Với những mutation **cùng một partition**, Cassandra có thể áp dụng cơ chế gom mutation theo partition; điều này khác hoàn toàn việc dùng unlogged batch trải nhiều partition.

Khi các mutation không liên quan và nằm ở nhiều partition, nhiều request độc lập có giới hạn concurrency thường là mô hình hợp lý hơn so với một unlogged batch cực lớn.

### COUNTER batch: loại thao tác riêng

Counter có ngữ nghĩa cộng/trừ, không phải gán scalar thông thường. Một mutation counter bị thực thi lại có thể làm số đếm tăng thêm lần nữa, nên **không được tự gán nhãn idempotent** hoặc bật retry mù quáng.

## 4. Schema ví dụ: nhiều sự kiện trong một partition ngày

Thiết kế bảng theo truy vấn “lấy sự kiện gần nhất của một tenant trong một ngày”:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id DESC
);
~~~

| Thành phần | Vai trò |
| --- | --- |
| `(tenant_id, event_day)` | **Composite partition key**, dùng để định tuyến nhóm replica |
| `event_time` | Clustering column để đọc sự kiện mới trước trong partition |
| `event_id` | Clustering column để phân biệt các hàng trùng timestamp |
| `event_type`, `payload` | Cột thường được ghi/đọc theo yêu cầu nghiệp vụ |

Truy vấn đọc:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT 50;
~~~

**Mẫu truy vấn và schema quyết định hiệu năng trước khi xét batch.** Ví dụ `dc1` với RF=3 yêu cầu cluster có topology/replica phù hợp; không chạy lệnh tạo keyspace/table bừa bãi trên production. Ở môi trường thực, quản lý schema qua migration độc lập.

Hai hàng cùng `tenant_id`, cùng `event_day`, khác `event_time/event_id` sẽ thuộc **cùng partition**. Nếu `event_day` khác nhau, hai mutation thuộc **hai partition** dù `tenant_id` giống nhau.

## 5. Entity mapping và composite primary key

Để dùng `CassandraBatchOperations` thao tác entity, Spring Data cần biết khóa và cột tương ứng CQL.

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.Column;
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
        name = "event_time", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor, getter/setter và equals/hashCode cho khóa.
}

@Table("events_by_tenant_day")
public class EventRow {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    // Constructor/getter/setter phù hợp với Spring Data.
}
~~~

Đoạn mã tập trung vào metadata và lược bỏ boilerplate; hai public class cần được đặt vào **hai tệp Java riêng** nếu sử dụng nguyên khai báo. Với `@PrimaryKeyClass`, định nghĩa `equals`/`hashCode` và accessor nhất quán với mapping. Mọi phần của primary key phải có giá trị không null trước khi ghi.

Trong cấu hình Spring Boot, đặt keyspace mặc định tương ứng hoặc dùng tên bảng đủ điều kiện ở CQL:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: telemetry_ks
    schema-action: none
~~~

Giá trị cấu hình chỉ minh họa môi trường test. Với production, cần TLS, authentication, contact points, local datacenter và monitoring theo hạ tầng thực tế.

## 6. `CassandraBatchOperations` là gì?

Spring Data Cassandra cung cấp interface **`CassandraBatchOperations`** để tập hợp thao tác mapped entity trước khi thực thi. Thông thường ta lấy đối tượng này từ **`CassandraTemplate.batchOps()`**.

~~~java
import org.springframework.data.cassandra.core.CassandraBatchOperations;
import org.springframework.data.cassandra.core.CassandraTemplate;

CassandraBatchOperations batch = cassandraTemplate.batchOps();

batch.insert(firstEvent);
batch.insert(secondEvent);
batch.execute();
~~~

Trong ví dụ, `firstEvent` và `secondEvent` là hai entity `EventRow` đã được tạo với khóa đầy đủ; `cassandraTemplate` là bean `CassandraTemplate` đã cấu hình.

Luồng:

~~~text
CassandraTemplate (dùng chung trong service)
     |
     +-- batchOps() ---> CassandraBatchOperations (phiên gom mới)
                            |
                            +-- insert(eventA)
                            +-- insert(eventB)
                            +-- execute()
                                  |
                                  v
                             CQL BATCH
                                  |
                                  v
                          Coordinator / replicas
~~~

**Ý nghĩa quan trọng:** các lời gọi `insert(...)` trước `execute()` là bước **đăng ký mutation vào batch**. Việc ghi xuống Cassandra diễn ra khi batch được thực thi, không phải sau mỗi lần thêm entity vào batch.

`CassandraTemplate` có thể được dùng lại giữa nhiều request theo cách quản lý bean thông thường. Ngược lại, đối tượng `CassandraBatchOperations` là **bộ tích lũy có trạng thái** cho một lần thực thi; không chia sẻ cùng một batch object giữa các HTTP request hoặc thread không liên quan. Tạo một batch mới cho mỗi nhóm mutation logic.

## 7. Ví dụ service: insert hai event cùng partition

Một service có thể kiểm tra rằng hai sự kiện thực sự cùng partition trước khi gom batch:

~~~java
import java.util.Objects;
import org.springframework.data.cassandra.core.CassandraBatchOperations;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class EventBatchWriter {
    private final CassandraTemplate template;

    public EventBatchWriter(CassandraTemplate template) {
        this.template = template;
    }

    public void writePair(EventRow first, EventRow second) {
        EventKey a = first.getKey();
        EventKey b = second.getKey();

        if (!Objects.equals(a.getTenantId(), b.getTenantId())
                || !Objects.equals(a.getEventDay(), b.getEventDay())) {
            throw new IllegalArgumentException(
                "Batch mẫu chỉ cho phép một partition");
        }

        CassandraBatchOperations batch = template.batchOps();
        batch.insert(first);
        batch.insert(second);
        batch.execute();
    }
}
~~~

Đoạn mã giả định `EventRow` có `getKey()` và `EventKey` có `getTenantId()/getEventDay()` như mapping ở trên. Trong ứng dụng thực tế, kiểm tra thêm null, kích thước payload, số mutation và quyền tenant.

Ví dụ chỉ **giới hạn ở một partition theo quy ước nghiệp vụ**; Cassandra không tự cấm logged batch đa partition. Kiểm tra này giúp tránh việc một helper dành cho ghi cặp sự kiện nhỏ bị dùng sai để gom hàng nghìn tenant hoặc ngày không liên quan.

### Vì sao không gọi insert ngay trong vòng lặp lớn?

~~~java
// KHÔNG NÊN: gom toàn bộ dữ liệu lịch sử vào một batch khổng lồ.
CassandraBatchOperations batch = template.batchOps();
for (EventRow event : allEventsForManyTenants) {
    batch.insert(event);
}
batch.execute();
~~~

Vòng lặp không bảo đảm các event cùng partition, kích thước tổng batch có thể rất lớn và coordinator trở thành điểm điều phối tải. Nếu cần nhập hàng triệu sự kiện, dùng pipeline/driver async có giới hạn concurrency, backpressure, partition-aware scheduling và quan sát throughput, thay vì coi `batchOps()` là bulk loader.

## 8. Kết hợp insert, update, delete trong một batch

`CassandraBatchOperations` biểu diễn các thao tác cơ bản trên entity. Một ví dụ quy trình bảo trì **ba hàng khác nhau cùng partition**:

~~~java
public void applyChanges(
        EventRow newEvent,
        EventRow revisedEvent,
        EventRow obsoleteEvent) {

    CassandraBatchOperations batch = template.batchOps();
    batch.insert(newEvent);
    batch.update(revisedEvent);
    batch.delete(obsoleteEvent);
    batch.execute();
}
~~~

Trong đó `template` là `CassandraTemplate` của service. Các thao tác này chỉ nên được gom khi đã xác nhận:

- Từng entity có primary key hợp lệ.
- Các hàng được sửa/xóa là **khác nhau** nếu yêu cầu thứ tự tác động cụ thể.
- Ba mutation có liên quan, kích thước nhỏ và cùng phạm vi truy cập mong muốn.
- Cơ chế retry không gây tác dụng phụ ngoài ý muốn.
- Không nhầm `delete(entity)` với xóa đối tượng Java khỏi bộ nhớ: Cassandra cần mutation/tombstone được áp dụng.

Điều cần nhớ về ngữ nghĩa mapped write:

| Method | Ý định | Cảnh báo |
| --- | --- | --- |
| `batch.insert(entity)` | Đăng ký INSERT theo mapping entity | INSERT thông thường có ngữ nghĩa **upsert** theo primary key |
| `batch.update(entity)` | Đăng ký UPDATE theo mapping entity | Có thể ghi nhiều property; không tự động như JPA dirty checking |
| `batch.delete(entity)` | Đăng ký DELETE dựa trên entity/khóa | Tạo tombstone; không nhất thiết chứng minh hàng từng tồn tại |
| `batch.execute()` | Gửi batch chứa các mutation đã gom | Timeout có thể để lại kết quả chưa chắc chắn |

Không giả định rằng một thao tác `update(entity)` chỉ ghi đúng field Java vừa đổi. Nếu cần **partial update** với TTL/timestamp riêng cho một cột, có thể dùng CQL hoặc template query/update thích hợp thay vì đưa toàn entity cũ vào batch.

## 9. Một partition hay nhiều partition: khác biệt nền tảng

So sánh:

~~~text
Trường hợp A: cùng partition
  eventA: (tenant=T1, day=D1, time=10:00, id=E1)
  eventB: (tenant=T1, day=D1, time=10:01, id=E2)

Trường hợp B: khác partition
  eventA: (tenant=T1, day=D1, time=10:00, id=E1)
  eventB: (tenant=T2, day=D1, time=10:01, id=E2)

Trường hợp C: khác partition dù tenant giống nhau
  eventA: (tenant=T1, day=D1, time=10:00, id=E1)
  eventB: (tenant=T1, day=D2, time=10:01, id=E2)
~~~

**A** phù hợp hơn khi ứng dụng muốn gom một nhóm mutation nhỏ. **B/C** có thể khiến coordinator phải liên hệ với các replica của nhiều token/partition khác nhau và tăng độ phức tạp lỗi/khả năng quan sát.

| Khía cạnh | Cùng partition | Nhiều partition |
| --- | --- | --- |
| Định tuyến | Một nhóm replica của partition | Nhiều nhóm replica có thể khác nhau |
| Chi phí điều phối | Thường dễ kiểm soát hơn | Có thể tăng theo số partition/size |
| Tính cô lập | Có ngữ nghĩa mutation theo partition; cần xét batch/phiên bản | **Không có isolation xuyên nhiều partition** |
| Logged batch | Có thể dùng, nhưng cần đo overhead | Hỗ trợ phục hồi batch nhưng chi phí phối hợp lớn hơn |
| Unlogged batch | Có thể phù hợp nếu đúng nhu cầu và phiên bản | Không bảo đảm atomic delivery đa partition |
| Mục tiêu throughput | Không nhất thiết nhanh hơn ghi đơn | Thường nên dùng independent async writes nếu không cần gom |

**Cùng tenant không đồng nghĩa cùng partition** nếu partition key còn chứa ngày, bucket, shard hoặc một trường khác. Đánh giá theo **giá trị khóa partition đầy đủ**, không theo tên service hay business aggregate.

## 10. BatchOps và batch type: API phiên bản cần kiểm tra

`CassandraTemplate.batchOps()` cung cấp một cách thuận tiện để bắt đầu batch. Một số phiên bản Spring Data Cassandra hỗ trợ lựa chọn **batch type** qua overload/cấu hình tương ứng, nhưng **không nên áp một chữ ký method của một version bất kỳ cho mọi dự án**.

Khi phải chỉ định tường minh `LOGGED`, `UNLOGGED` hoặc `COUNTER`, có thể dùng **Java Driver 4.x** với `BatchStatement` và `DefaultBatchType`. Đây cũng là cách dễ thấy các lựa chọn request-level như consistency level:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

BoundStatement first = preparedInsert.bind(
    tenantId, eventDay, firstTime, firstId,
    "ORDER_PAID", firstPayload
);
BoundStatement second = preparedInsert.bind(
    tenantId, eventDay, secondTime, secondId,
    "ORDER_SHIPPED", secondPayload
);

BatchStatement batch = BatchStatement.builder(DefaultBatchType.LOGGED)
    .addStatement(first)
    .addStatement(second)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .build();

session.execute(batch);
~~~

Giả định `preparedInsert` là `PreparedStatement` đã được prepare với câu `INSERT` sáu marker phù hợp schema và `session` là bean `CqlSession`. Các biến UUID/LocalDate/Instant/String được tạo và validate trước khi bind.

Nếu thao tác **chỉ** gồm các mutation cùng partition, có thể cân nhắc:

~~~java
BatchStatement unlogged =
    BatchStatement.builder(DefaultBatchType.UNLOGGED)
        .addStatement(first)
        .addStatement(second)
        .build();

session.execute(unlogged);
~~~

Không suy ra rằng UNLOGGED luôn nhanh hơn LOGGED trong mọi kích thước/tải. **Benchmark trên dữ liệu/cluster thực** và hiểu ngữ nghĩa phục hồi trước khi chọn. Đoạn mã dùng API driver mức thấp; nó **không tự dùng mọi converter** được cấu hình riêng cho Spring Data mapping.

## 11. `batchOps()` khác các lời gọi riêng và repository.saveAll

Các cách viết sau có **mục đích và ngữ nghĩa không mặc định tương đương**:

~~~java
// Hai request logic riêng.
template.insert(firstEvent);
template.insert(secondEvent);

// Một phiên gom các mutation thành CQL batch.
CassandraBatchOperations batch = template.batchOps();
batch.insert(firstEvent);
batch.insert(secondEvent);
batch.execute();

// API lưu nhiều entity trên repository.
repository.saveAll(events);
~~~

Không mặc định `repository.saveAll(events)` có cùng loại batch, cùng sự kiện xác nhận hay cùng chính sách timeout như `batchOps()`. Tùy phiên bản Spring Data, repository có thể triển khai thao tác lưu tập entity theo đường khác; cần kiểm tra API và đo request thực tế nếu semantics/performance quan trọng.

Tương tự, `@Transactional` trong một service Spring Data Cassandra **không tự biến nhiều mutation CQL và gọi hệ thống ngoài thành một transaction SQL có rollback**. Trước khi áp dụng một pattern từ JPA/JDBC, hãy hỏi Cassandra sẽ thực hiện mutation theo partition, batch log và consistency nào.

## 12. Atomicity, isolation và durability: không đánh đồng

Trong hệ SQL quan hệ, nhiều người mong đợi một transaction có thể rollback hoàn toàn và các reader không thấy trạng thái trung gian. Với Cassandra BATCH, cần tách ba câu hỏi:

| Câu hỏi | Cassandra batch trả lời thế nào? |
| --- | --- |
| Mutation có thể bị gửi lại sau sự cố? | **LOGGED** batch có batch log để phục hồi theo cơ chế Cassandra |
| Người đọc có thấy tất cả partition cùng lúc? | **Không bảo đảm isolation xuyên partition** như SQL transaction |
| Nếu client timeout, tất cả mutation đã thất bại? | **Không được kết luận**; có thể đã áp dụng một phần/toàn bộ |
| Nếu một thao tác trả exception, có rollback SQL? | **Không** có cơ chế rollback đa bảng tổng quát tương đương |
| Nếu cả hai ghi cùng một cell, dòng nào “chạy sau” thắng? | Phân giải theo write timestamp, không mặc định theo thứ tự lệnh batch |
| RF/CL có thay đổi data model? | Không; chỉ ảnh hưởng replica và yêu cầu phản hồi |

**Logged batch** có bảo đảm về **việc hoàn tất mutation của batch** dưới các điều kiện phù hợp, nhưng không đồng nghĩa một **transaction đa partition tuyến tính** hoặc một giao dịch đọc-sửa-ghi nguyên tử.

Trong các luồng cần chính xác “chỉ chuyển trạng thái khi đang NEW”, hãy nghĩ tới **LWT/conditional write** và thiết kế idempotency, không chỉ đổi từ nhiều `update` riêng sang `batchOps()`.

## 13. Consistency level của batch

RF thuộc keyspace; CL thuộc **request ghi**. Với RF=3 trong một DC và `LOCAL_QUORUM`, cần đa số replica cục bộ phản hồi theo ngữ nghĩa của thao tác.

Ví dụ điều chỉnh CL trên Java Driver batch:

~~~java
BatchStatement batch = BatchStatement.builder(DefaultBatchType.LOGGED)
    .addStatement(first)
    .addStatement(second)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .build();
~~~

Một batch có các statement tới nhiều partition có thể liên quan tới nhiều nhóm replica. Không được suy từ RF=3 rằng tất cả partition sẽ chỉ đi qua cùng ba node.

**CL cao không biến unlogged batch thành transaction nguyên tử đa partition.** CL chỉ mô tả yêu cầu phản hồi từ replica; kiểu batch và thuật toán phục hồi là câu chuyện khác. Đồng thời, CL cao hơn có thể làm request nhạy hơn với node chậm/lỗi.

Khi dùng `CassandraBatchOperations` thông qua Spring Data, CL thường đến từ cấu hình driver/execution profile hoặc options được phiên bản thư viện hỗ trợ. Nếu cần chọn CL và batch type một cách chính xác cho request đặc biệt, dùng API phù hợp của Spring Data hoặc driver trực tiếp và kiểm chứng execution options thực tế.

## 14. Timeout và retry: cả batch cũng có kết quả chưa chắc chắn

Một kịch bản thường gặp:

~~~text
T0  Client gửi LOGGED batch gồm hai mutation
T1  Coordinator ghi nhận batch theo cơ chế Cassandra
T2  Một số replica đã nhận mutation
T3  Client timeout hoặc mất kết nối
T4  Worker/driver dự định retry cùng batch
~~~

Ở T3, client chưa chắc đã biết liệu các thay đổi đã được áp dụng đầy đủ, đang được phục hồi hay chưa hoàn tất. Một lần retry có thể thực thi lại những mutation đã xảy ra.

### Thiết kế retry an toàn hơn

- Tạo **primary key và event ID ổn định** ở thời điểm tiếp nhận nghiệp vụ; không tự sinh ID khác trong mỗi lần retry.
- Chỉ xem batch idempotent nếu **tất cả mutation bên trong** an toàn khi lặp lại và không kích hoạt side effect ngoài ý muốn.
- Tránh đưa counter increment hoặc list append vào luồng retry thông thường.
- Xem xét **write timestamp** và TTL: retry một thao tác cũ với timestamp mới có thể ghi đè một cập nhật mới hơn; TTL có thể thay đổi deadline tồn tại.
- Giới hạn số attempt và concurrency, dùng backoff có jitter; không retry vô hạn khi Cassandra overload.
- Khi có ambiguity, đọc lại bằng **đúng primary key/CL phù hợp** hoặc chạy reconciliation theo business command ID.

Với Java Driver, cờ `setIdempotent(true)` là **tuyên bố về semantics của statement**, không phải cơ chế tự đạt exactly-once:

~~~java
// Chỉ đặt true khi mọi mutation trong batch thực sự
// an toàn khi thực thi lặp lại trong mô hình nghiệp vụ.
BatchStatement candidate = BatchStatement.builder(DefaultBatchType.LOGGED)
    .addStatement(first)
    .addStatement(second)
    .setIdempotent(true)
    .build();
~~~

Đừng bật cờ này chỉ để driver có cơ hội retry nhiều hơn. Kiểm tra retry policy, request timeout, loại lỗi và khả năng idempotent **ở toàn bộ tầng API/queue/DB**, không chỉ từng câu CQL.

## 15. Write timestamp, TTL và tombstone bên trong batch

### Write timestamp

Cassandra giải quyết các ghi cạnh tranh theo **write timestamp của cell**. CQL có thể chỉ định timestamp, nhưng không nên dùng timestamp tự sinh thiếu quy tắc để “xếp thứ tự” nhiều statement trong một batch.

~~~sql
BEGIN BATCH
    INSERT INTO telemetry_ks.events_by_tenant_day (
        tenant_id, event_day, event_time, event_id, event_type
    ) VALUES (?, ?, ?, ?, ?);

    UPDATE telemetry_ks.events_by_tenant_day
    SET payload = ?
    WHERE tenant_id = ?
      AND event_day = ?
      AND event_time = ?
      AND event_id = ?;
APPLY BATCH;
~~~

**Không** xây logic “statement thứ hai chắc chắn thắng statement thứ nhất” nếu chúng ghi cùng cell. Tránh ghi hai giá trị khác nhau vào cùng một cột/khóa trong một batch; nếu cần trạng thái sau cùng, hãy tính ra **một mutation đúng** ở tầng ứng dụng.

### TTL

Với CQL `INSERT` hoặc `UPDATE` có thể dùng `USING TTL` theo cú pháp của mỗi statement. Ví dụ một mutation có TTL:

~~~sql
INSERT INTO telemetry_ks.events_by_tenant_day (
    tenant_id, event_day, event_time, event_id, event_type
) VALUES (?, ?, ?, ?, ?)
USING TTL ?;
~~~

TTL tính bằng **giây**. Trong một batch, TTL của từng mutation/cell có thể có ý nghĩa khác nhau tùy giá trị được ghi. **Không mặc định `batchOps()` tự gán TTL nghiệp vụ** cho toàn bộ entity; khi cần kiểm soát TTL, dùng WriteOptions hoặc statement API phù hợp phiên bản.

### DELETE và tombstone

Gom nhiều `DELETE` vào batch **không làm tombstone biến mất**. Những thao tác xóa tạo metadata để replica hòa giải dữ liệu đã xóa; hàng loạt partition delete hoặc TTL hết hạn có thể khiến compaction/read bị quá tải.

Tránh job “xóa toàn bộ dữ liệu hết hạn bằng batch hàng trăm nghìn hàng” nếu chưa sizing về tombstone. Với retention định kỳ, thiết kế TTL, time bucket và compaction phù hợp thường bền vững hơn.

## 16. LWT / IF NOT EXISTS và batch có điều kiện

Một yêu cầu như **“chỉ ghi sự kiện nếu nó chưa tồn tại”** không được giải quyết bằng `LOGGED BATCH` thông thường:

~~~sql
INSERT INTO telemetry_ks.events_by_tenant_day (
    tenant_id, event_day, event_time, event_id, event_type
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

`IF NOT EXISTS` sử dụng **lightweight transaction (LWT)** với ngữ nghĩa điều kiện. Cassandra có hỗ trợ một số dạng conditional batch, nhưng các điều kiện/phạm vi partition và việc trộn statement chịu **ràng buộc riêng theo phiên bản**; không được suy rằng có thể kết hợp tùy ý LWT đa partition bằng cách gọi `batchOps()`.

Nếu cần một chuỗi chuyển trạng thái như:

~~~text
NEW -> PAID -> SHIPPED
~~~

hãy dùng **state machine** và conditional update khi cần kiểm tra trạng thái cũ. **LOGGED batch không tự cung cấp compare-and-set**, cũng không tạo giao dịch nguyên tử với payment gateway hoặc message broker.

Với LWT, code phải kiểm tra **applied** và xử lý trường hợp response bị mất: retry có thể nhận `applied=false` dù lần đầu đã thành công. Chỉ đánh dấu batch là “đã hoàn tất nghiệp vụ” khi có bằng chứng phù hợp hoặc cơ chế reconciliation.

## 17. Vì sao batch không phải bulk loader?

Cassandra được thiết kế cho việc ghi phân tán tới đúng replica của partition. Nếu một job ingest 1 triệu sự kiện rải nhiều tenant/ngày:

~~~text
1 triệu event trên nhiều partition
          |
          +-- 1 batch khổng lồ  ---> coordinator chịu tải lớn,
          |                          batch log/timeout/memory
          |
          +-- nhiều request nhỏ, đồng thời có giới hạn
                                     ---> phân phối qua coordinator/
                                          replica theo token và backpressure
~~~

**Chọn batch vì semantics cần gom mutation, không vì “càng nhiều row trong một batch càng nhanh”.**

Một số rủi ro của batch lớn:

| Hiện tượng | Nguyên nhân/rủi ro |
| --- | --- |
| Cảnh báo batch quá lớn | Mutation vượt ngưỡng cảnh báo theo cấu hình Cassandra |
| Batch bị từ chối | Vượt giới hạn kích thước theo cấu hình/phiên bản |
| Coordinator CPU/heap tăng | Phải điều phối nhiều mutation/partition trong một request |
| p95/p99 latency tăng | Nhiều replica chậm, batch log và công việc phối hợp |
| Timeout khó kiểm tra | Kết quả có thể chưa chắc chắn, nhiều khóa cần reconcile |
| Cross-DC phụ thuộc mạng xa | CL/replica và các mutation trải nhiều datacenter |
| Tombstone hoặc repair tăng | Quá nhiều delete/TTL trên nhiều partition |

Cassandra có những ngưỡng như `batch_size_warn_threshold_in_kb` và `batch_size_fail_threshold_in_kb` ở một số phiên bản/cấu hình; **không dựa vào một con số mặc định chung**, vì nó có thể được thay đổi theo cluster/version.

### Hướng nhập dữ liệu lớn

Tùy yêu cầu, có thể dùng:

1. Java Driver asynchronous statements hoặc pipeline nhập liệu với **bounded concurrency**.
2. Gom theo **partition key** ở mức vừa phải nếu có lý do nghiệp vụ, không theo số hàng ngẫu nhiên.
3. Backpressure, retry có giới hạn, idempotency key và các chỉ số latency/timeout.
4. Công cụ bulk loading phù hợp môi trường nếu lượng dữ liệu rất lớn.

Không tạo batch cực lớn chỉ để “giảm số lần gọi hàm Java”. Độ trễ network của một request không phải thước đo duy nhất của tổng throughput hay an toàn dữ liệu.

## 18. Đánh giá batch khác partition bằng một ví dụ nghiệp vụ

Một cửa hàng lưu hai bảng đọc theo hai access patterns:

~~~text
orders_by_customer_day
  -> tra đơn theo customer/day

orders_by_status_day
  -> tra đơn theo status/day
~~~

Một thay đổi trạng thái `NEW` thành `PAID` có thể cần sửa cả hai bảng. Một **logged batch nhỏ** có thể được cân nhắc để hỗ trợ **việc cuối cùng áp dụng đủ các mutation liên quan** trong mô hình denormalized.

Nhưng:

- Hai bảng có **partition key khác nhau**, có thể nằm trên nhóm replica khác nhau.
- Một reader đang truy vấn bảng theo status có thể thấy dữ liệu mới trước/hoặc sau reader ở bảng theo customer; **không có snapshot đa bảng**.
- Nếu chuyển status, cần xử lý cả việc **xóa dòng thuộc status cũ** và **thêm dòng thuộc status mới**, không chỉ ghi thêm.
- Batch không tự đồng bộ những side effect ở cache, search engine, queue hoặc thanh toán.
- Khi ghi timeout, phải có cách **reconcile hai đường đọc** theo business ID.

Vì vậy logged batch là **một công cụ** trong thiết kế denormalization, không phải thay thế của transactional outbox, workflow engine hoặc cơ chế kiểm chứng tính nhất quán nghiệp vụ.

## 19. Chọn đúng công cụ trong Spring Data Cassandra

| Tình huống | Công cụ nên xem xét | Lý do |
| --- | --- | --- |
| CRUD một entity | `CassandraRepository` / `CassandraTemplate` | Mapped write đơn giản, không cần batch |
| Gom vài INSERT/UPDATE/DELETE có liên quan | **`CassandraTemplate.batchOps()`** | API typed entity, tạo batch và execute rõ ràng |
| Ghi partial update một cột | `CassandraTemplate` với Query/Update hoặc `CqlTemplate` | Tránh gửi toàn entity cũ |
| Chọn LOGGED/UNLOGGED cụ thể và set CL | Driver `BatchStatement` hoặc API batch options được version hỗ trợ | Điều khiển execution options tường minh |
| Ghi counter | CQL counter đúng kiểu, chỉ cân nhắc counter batch khi phù hợp | Counter không idempotent; không trộn mutation thường |
| Cần conditional transition | LWT/`IF` | Có kiểm tra giá trị trước khi áp dụng |
| Ingest liên tục rất lớn | Bounded async pipeline | Phân phối request và backpressure tốt hơn batch khổng lồ |
| Dùng WebFlux/reactive | API reactive tương ứng của version hoặc driver async | I/O không blocking không tự thay đổi semantics CQL |

Spring Data Cassandra cung cấp các API theo phiên bản; **không nên sao chép một method reactive hoặc overload batch type không tồn tại** mà chưa kiểm tra dependency. Với code đồng bộ ở bài này, `CassandraTemplate.batchOps()` là API trọng tâm.

## 20. Những sai lầm phổ biến khi dùng batchOps

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `batchOps()` giống SQL transaction | Không có rollback/isolation đa partition tương đương | Phân biệt logged-batch recovery và transaction isolation |
| Gom hàng nghìn tenant vào một batch | Coordinator/batch log nóng, timeout | Giới hạn kích thước, nhóm theo partition hoặc dùng async writes |
| Dùng UNLOGGED đa partition rồi mong all-or-nothing | Có thể nhìn thấy ghi một phần | Chọn mô hình phù hợp và có reconciliation |
| Dùng LOGGED chỉ để tăng throughput | Thường thêm overhead không cần thiết | Benchmark; sử dụng batch khi cần semantics |
| Gọi `insert` rồi quên `execute` | Mutation chưa được gửi theo phiên batch | Chỉ xem thành công sau khi execute và xử lý kết quả |
| Chia sẻ một `CassandraBatchOperations` giữa request | Trộn mutation, rò trạng thái, nguy cơ concurrency | Tạo batch object mới cho mỗi workflow |
| Coi `update(entity)` là dirty checking | Có thể ghi đè cột với dữ liệu cũ | Partial update CQL hoặc điều kiện phù hợp |
| Cho hai statement ghi khác giá trị cùng cell | Kết quả bị chi phối timestamp/tie-break | Tính một giá trị cuối ở service |
| Retry counter/list như INSERT thường | Đếm/lặp nhiều lần | Không đánh dấu idempotent bừa bãi |
| Nghĩ timeout nghĩa rollback | Có thể đã apply một phần/toàn bộ | Xác minh theo key và reconcile |
| Gom xóa hàng loạt vào batch | Tombstone và read/compaction pressure | Time bucket/TTL, giới hạn xóa |
| Nghĩ LOGGED batch thay cho LWT | Không bảo đảm compare-and-set | Dùng conditional write nếu cần |

## 21. Kế hoạch kiểm thử thực hành

Thực hiện trên cluster test có schema tương ứng với Cassandra/driver/Spring Data version thực tế; không gây lỗi node trên production để thử batch.

### Bài thực hành A: hai sự kiện cùng partition

1. Tạo `firstEvent` và `secondEvent` có cùng `tenantId`, `eventDay` nhưng khác `eventTime`/`eventId`.
2. Gọi `template.batchOps()`, `insert(firstEvent)`, `insert(secondEvent)`, `execute()`.
3. Query partition theo tenant/day và xác minh hai hàng được lưu.
4. Lặp lại batch với **cùng khóa và giá trị** ở môi trường test, quan sát ngữ nghĩa upsert.

### Bài thực hành B: sửa và xóa

1. Ghi ba hàng khác nhau trong một partition.
2. Dùng batch chứa `update(second)` và `delete(third)`, tránh hai mutation chồng lên cùng một cell.
3. Đọc lại để xác minh cột được cập nhật và hàng bị xóa.
4. Kiểm tra tombstone/latency nếu thực hiện nhiều lượt ở môi trường test.

### Bài thực hành C: logged so với unlogged

1. Chuẩn bị vài mutation trong **cùng partition**, xác nhận query hoạt động độc lập.
2. Thực hiện lần lượt bằng driver `DefaultBatchType.LOGGED` và `DefaultBatchType.UNLOGGED` trên dữ liệu test tách biệt.
3. Đo latency/p95/p99, request count, errors và coordinator load.
4. Thử mutation ở **hai partition** với dữ liệu test; quan sát logging, timeout và sự khác nhau về bảo đảm, không giả định isolation.

### Bài thực hành D: tình huống timeout

1. Ghi một batch nhỏ với primary key và business ID cố định.
2. Mô phỏng lỗi mạng/timeout **trong môi trường test được kiểm soát**.
3. Không tạo ID mới rồi retry mù quáng; đọc kiểm tra bằng đúng key.
4. Kiểm tra retry của các mutation gán giá trị và so sánh với increment counter/list append.

### Ma trận kiểm thử

| Kịch bản | Kỳ vọng cần xác minh |
| --- | --- |
| Batch chưa gọi `execute()` | Không có mutation batch nào được gửi bởi phiên tích lũy đó |
| Hai hàng cùng partition | Được ghi và đọc lại theo key chính xác |
| Nhiều partition | Hành vi phù hợp batch type/CL, không giả định isolation |
| LOGGED batch bị timeout | Kết quả chưa chắc chắn, cần kiểm tra/reconcile |
| UNLOGGED batch đa partition bị lỗi | Không giả định tất cả mutation đều được áp dụng |
| Counter batch bị retry | Có nguy cơ tăng nhiều lần |
| `update(entity)` với entity cũ | Có nguy cơ ghi đè cell khác, cần kiểm tra generated CQL |
| Batch có DELETE/TTL | Quan sát tombstone và TTL của cell theo CQL |
| Batch vượt ngưỡng size | Warning/error theo cấu hình cluster |
| LWT với điều kiện | Kiểm tra `applied`, không suy từ execute success |

Đối với một partition cụ thể, có thể kiểm tra bằng CQL:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT 100;
~~~

Ở quy trình test thật, dùng prepared statement/parameter binding, không ghép trực tiếp input không tin cậy vào CQL.

## 22. Checklist trước khi dùng CassandraBatchOperations ở production

- [ ] Batch có **mục đích nghiệp vụ** rõ, không được dùng chỉ vì nghĩ “bulk luôn nhanh hơn”.
- [ ] Biết chính xác **partition key** của từng entity/mutation.
- [ ] Ưu tiên batch nhỏ, cùng partition khi phù hợp; giới hạn số mutation và byte.
- [ ] Chọn LOGGED/UNLOGGED/COUNTER theo ngữ nghĩa và phiên bản API.
- [ ] Không trộn counter mutation với mutation thường.
- [ ] Không giả định isolation/rollback đa partition như SQL.
- [ ] Phân biệt mapped entity update với partial update và LWT.
- [ ] Không có hai statement cạnh tranh ghi cùng cell với giá trị mâu thuẫn mà dựa vào thứ tự CQL.
- [ ] Có idempotency key/primary key ổn định, chính sách retry và xử lý ambiguous outcome.
- [ ] TTL, write timestamp, DELETE/tombstone được kiểm soát riêng.
- [ ] CL/local datacenter và RF phù hợp với mục tiêu availability/latency.
- [ ] Có metrics batch size, warnings, p95/p99, timeout/unavailable, tombstone, retry.
- [ ] Đã kiểm thử logged/unlogged và multi-partition trên cluster test tương đương.
- [ ] Không chia sẻ một đối tượng `CassandraBatchOperations` tích lũy giữa nhiều request.

## 23. Tự kiểm tra

**Câu 1.** `CassandraTemplate.batchOps()` khác `template.insert(entity)` như thế nào?

**Đáp án:** `batchOps()` trả một đối tượng tích lũy nhiều mutation trước khi `execute()` gửi thành một batch. `template.insert(entity)` là thao tác ghi riêng theo API template.

**Câu 2.** Tại sao không nên gom 10.000 sự kiện từ nhiều tenant/ngày vào một logged batch?

**Đáp án:** Các mutation trải nhiều partition/replica, tăng chi phí coordinator/batch log, memory và timeout. Batch không phải công cụ tối ưu bulk throughput; dùng request nhỏ và bounded concurrency khi không cần semantics gom.

**Câu 3.** Logged batch có cho phép reader ở hai bảng khác nhau thấy cả hai thay đổi đồng thời như SQL transaction không?

**Đáp án:** Không. Batch log hỗ trợ phục hồi việc áp dụng mutation, nhưng không cung cấp transaction isolation xuyên partition/bảng.

**Câu 4.** Nếu hai event có cùng tenant nhưng khác ngày, chúng có cùng partition không?

**Đáp án:** Không với bảng ví dụ, vì partition key là cặp `(tenant_id, event_day)`.

**Câu 5.** `batch.update(entity)` có bảo đảm chỉ ghi field vừa sửa trong Java không?

**Đáp án:** Không mặc định. Mapped update có thể ghi nhiều property của entity; muốn partial update cần API Query/Update/CQL phù hợp.

**Câu 6.** Client timeout khi gọi `batch.execute()` thì nên kết luận đã rollback?

**Đáp án:** Không. Cần coi kết quả chưa chắc chắn, kiểm tra theo primary key, xử lý idempotency/retry và reconciliation.

**Câu 7.** Bật `setIdempotent(true)` có làm thao tác tăng counter an toàn khi retry không?

**Đáp án:** Không. Cờ chỉ là khai báo cho driver; increment counter vẫn có thể bị thực thi nhiều lần.

**Câu 8.** Khi cần “chỉ cập nhật nếu status hiện tại là NEW”, dùng LOGGED batch có đủ không?

**Đáp án:** Không. Cần conditional write/LWT với `IF` phù hợp và kiểm tra kết quả `applied`.

---

**Ghi nhớ:** **`CassandraBatchOperations`** kết hợp với **`CassandraTemplate.batchOps()`** là cách thuận tiện để gom `insert/update/delete` theo entity rồi gọi **`execute()`**. Nhưng batch trong Cassandra có ý nghĩa **ghi phân tán theo partition**, không phải JDBC bulk batch hay transaction SQL đầy đủ. Hãy phân biệt **LOGGED/UNLOGGED/COUNTER**, ưu tiên nhóm mutation nhỏ có liên quan, hiểu cross-partition isolation, kiểm soát timeout/retry/idempotency và đo tải thật. Khi cần conditional update dùng LWT; khi cần nhập dữ liệu lớn dùng pipeline có backpressure thay vì một batch khổng lồ.
