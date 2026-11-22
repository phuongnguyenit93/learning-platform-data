# Object mapper/DAO và chi phí trừu tượng hóa

## 1. Bài toán: code Java ngắn hơn nhưng truy vấn có nhanh hơn không?

Một dịch vụ **Java** dùng **Apache Cassandra** để lưu sự kiện thiết bị. Ban đầu, lập trình viên viết trực tiếp `PreparedStatement`, `BoundStatement` và lấy từng trường từ `Row`. Khi dự án có hàng chục bảng theo truy vấn và hàng trăm call site, nhóm muốn chuyển sang **object mapper** và **DAO (Data Access Object)** để tránh lặp mã chuyển đổi cột, gom logic truy cập và giảm sai sót khi bảo trì.

Phương án mới nhìn rất gọn:

~~~java
EventRecord event = dao.findById(
    "device-7",
    LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:00:00Z"),
    UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));
~~~

Nhưng sau khi thay, nhóm nhận thấy p99 của một số API tăng, heap allocation lớn hơn và có các query âm thầm trả nhiều cột hơn mức giao diện cần. Một người kết luận: “Mapper vốn chậm, bỏ hết mapper là xong.” Người khác cho rằng: “DAO đã tự tối ưu CQL, không cần xem query plan.” **Cả hai kết luận đều thiếu cơ sở.**

Trong Apache Cassandra Java Driver 4.x, mapper thường là **mã Java được sinh tại compile time từ annotations**; bản thân nó không nhất thiết dùng reflection ở mỗi hàng như một ORM động. Chi phí thực cần tách thành **chuẩn bị statement, network/replica, số cột/byte đọc, paging, decode CQL, khởi tạo object, chuyển đổi kiểu và phân bổ bộ nhớ**. Một `SELECT *` hoặc partition key sai có thể tốn hơn mọi khác biệt giữa mapper và `Row` nhiều bậc độ lớn.

**Mục tiêu của bài thuộc chương “Truy vấn từ Java”:**

1. Hiểu vai trò của `@Entity`, `@Dao`, `@Mapper` và annotation processor trong Java Driver 4.x.
2. Tạo bảng CQL theo truy vấn, ánh xạ primary key đúng và dùng DAO để đọc/ghi.
3. So sánh mapper với **Core API** (`CqlSession`, prepared/bound statements, `Row`) trên cùng CQL.
4. Định lượng chi phí trừu tượng hóa: object allocation, GC, column projection, custom codec, paging, `N+1`, prepared statement và routing.
5. Phân biệt DAO của Cassandra với ORM kiểu JPA/Hibernate: **không tự có join, transaction, lazy loading hoặc dirty checking**.
6. Thiết kế phép đo p95/p99, throughput, memory và tài nguyên replica trước khi chọn cách triển khai.
7. Áp dụng giới hạn concurrency, consistency, timeout, security và migration để giữ DAO đúng và an toàn.

**Phạm vi:** dùng API `com.datastax.oss.driver.api.*` của Java Driver **4.x**. Dependency, package annotation, code generation, khả năng ánh xạ kiểu, execution profile và tên tùy chọn có thể khác giữa các bản minor/bản phân phối. Code là **lab minh họa**, cần đối chiếu phiên bản và schema thật. Bài không thay thế bước QA học thuật/benchmark trên cluster mục tiêu.

## 2. Đặt mapper đúng vị trí trong kiến trúc Cassandra

~~~mermaid
flowchart TD
    A["HTTP / use case Java"] --> B["Service: validation, deadline, rate limit"]
    B --> C["DAO interface"]
    C --> D["Mapper implementation sinh ở compile time"]
    D --> E["Java Driver Core: CqlSession, prepared/bound statement"]
    E --> F["Routing đến coordinator"]
    F --> G["Natural replicas theo token, RF, CL"]
    G --> H["Memtable, SSTable, cache, commit log"]
    H --> G
    G --> F
    F --> E
    E --> I["Decode Row / mapping Entity / DTO"]
    I --> B
~~~

**Không có đường đi tắt từ `@Dao` tới SSTable.** Dù gọi `dao.findById()` hay `session.execute()`, cuối cùng vẫn là một **CQL statement** gửi qua native protocol tới Cassandra. Driver không bỏ qua coordinator, consistency level, tombstone hoặc disk I/O nhờ có mapper.

| Thành phần | Trách nhiệm chính | Không làm thay |
| --- | --- | --- |
| **CQL schema** | Định tuyến bằng partition key, sắp hàng bằng clustering columns, định nghĩa kiểu dữ liệu. | Mapper không đổi được primary key của bảng. |
| **Core Driver** | Kết nối/routing, prepare/bind/execute, paging, timeout, retry, decode giá trị. | Không tự đảm bảo query shape phù hợp workload. |
| **Object mapper** | Sinh mã chuyển cột CQL thành thuộc tính Java, sinh DAO và câu lệnh thường dùng. | Không tạo join, secondary index, snapshot transaction hay projection tối ưu tự động. |
| **DAO interface** | Đóng gói hợp đồng truy cập dữ liệu và phương thức phục vụ use case. | Không tự đảm bảo mọi `SELECT` là một partition lookup. |
| **Service layer** | Validation, authorization nghiệp vụ, fan-out qua bucket, deadline, backpressure và caching khi thích hợp. | Không nên để DAO quyết định nghiệp vụ hay retry vô hạn. |

### 2.1. Data Access Object khác object mapper ở đâu?

- **DAO** là **ranh giới API**: `findById`, `findWindow`, `insertEvent`, `markProcessed`. Nó có thể được viết thủ công bằng Core Driver hoặc được sinh.
- **Object mapper** là công cụ chuyển đổi **hàng/kiểu CQL ↔ Java object** và thường hỗ trợ tạo implementation DAO từ annotations.
- **Entity** mô tả cách Java bean tương ứng với bảng Cassandra, không nhất thiết là domain object đầy đủ hay aggregate root nghiệp vụ.
- **DTO/projection** chỉ chứa dữ liệu mà API cần; có thể không có một entity ánh xạ đầy đủ nếu đọc vài cột bằng `Row` hiệu quả hơn.

**Một DAO tốt có thể dùng cả mapper và Core API.** Ví dụ `findById` dùng mapper vì tính bảo trì, còn dashboard cần đọc ba cột trong hàng triệu records dùng Core API để tránh tạo object `payload` không cần thiết.

## 3. Mapper 4.x không phải ORM quan hệ kiểu JPA

| Kỳ vọng khi quen JPA/Hibernate | Cassandra Java Driver mapper làm gì? | Hệ quả |
| --- | --- | --- |
| `@Entity` có identity map và dirty checking | Ánh xạ property/column, sinh statement/DAO; **không có persistence context JPA** theo mặc định. | Sửa một field Java object không có nghĩa Cassandra tự `UPDATE`. |
| `@ManyToOne`, `JOIN FETCH` | Cassandra không có join đa bảng theo mô hình CQL thông thường. | Tạo bảng theo query hoặc ghép kết quả ở service khi cần. |
| Lazy load quan hệ | Không tự có lazy proxy và prefetch graph object kiểu ORM quan hệ. | Phải tự giới hạn số query, tránh `N+1`. |
| `@Transactional` cho nhiều bảng | Cassandra có semantics mutation/batch/LWT riêng, **không có transaction cách ly đa partition kiểu SQL**. | Dual-write hai bảng cần idempotency/reconciliation. |
| Đổi khóa chính bằng `entity.setId()` | Partition/clustering key định danh hàng và token placement. | Cần ghi key mới và xử lý key cũ theo quy trình, không update khóa tại chỗ. |
| ORM tự tạo query tối ưu | Mapper xây CQL dựa trên annotations hoặc `@Query`; nó không đo cluster hay rewrite truy vấn tùy ý. | Cần thiết kế partition key, clustering range và benchmark. |
| Tự quản lý schema migration | Mapper không tự thay đổi cấu trúc bảng production. | Dùng migration process/schema governance riêng. |

**Vì sao điều này quan trọng?** Nếu `EventRecord` có thuộc tính `eventDay`, việc ánh xạ `@PartitionKey(1)` giúp mapper bind đúng cấu trúc đã có; **không** khiến Cassandra tự chia partition theo ngày khi schema thực không chứa thành phần ấy.

## 4. Chuẩn bị một bảng theo truy vấn, không theo hình dạng object

### 4.1. CQL lab

Giả định một cluster lab có DC `dc1` và đủ ba full replicas:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_mapper
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_mapper.events_by_device_day (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Tại sao schema này hợp lý cho use case?**

1. `(device_id, event_day)` là **partition key kép**. Cùng một thiết bị nhưng khác ngày nằm ở những partition khác nhau, có thể được băm ra các token khác nhau.
2. `event_time` là clustering column đầu, cho phép đọc một **khoảng thời gian trong một partition**; `event_id` ngăn hai event cùng timestamp trở thành một primary key.
3. `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` ưu tiên sự kiện mới trong ngày. Nó không tạo thứ tự toàn cục xuyên các partition ngày.
4. `payload` là regular column. Nếu rất lớn hoặc API chỉ cần timeline summary, tách bảng summary/chi tiết có thể giảm bytes read tốt hơn thay object mapper.
5. RF = 3 trong `dc1` chỉ là thiết lập lab có điều kiện. Không khai RF lớn hơn số node thực có rồi giả định `LOCAL_QUORUM` luôn thành công.

### 4.2. Dữ liệu thử nghiệm có định danh ổn định

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_mapper.events_by_device_day
 (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
 ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
  123e4567-e89b-42d3-a456-426614174001, 'HEARTBEAT', 'ok');

INSERT INTO telemetry_mapper.events_by_device_day
 (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
 ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
  123e4567-e89b-42d3-a456-426614174002, 'TEMPERATURE', '21.6');

INSERT INTO telemetry_mapper.events_by_device_day
 (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
 ('device-7', '2026-11-20', '2026-11-20T23:59:59Z',
  123e4567-e89b-42d3-a456-426614174003, 'HEARTBEAT', 'late');
~~~

`CONSISTENCY` là lệnh **cqlsh**. Trong Java Driver, CL được đặt bằng statement/profile. `LOCAL_QUORUM` với RF = 3 yêu cầu hai phản hồi trong local DC, nhưng không bảo đảm mọi replica đều đã hội tụ.

### 4.3. Query có giới hạn vật lý hợp lý

~~~sql
SELECT device_id, event_day, event_time, event_id, event_type, payload
FROM telemetry_mapper.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

Đây là truy vấn có **đầy đủ partition key**, clustering range **nửa kín [start, end)** và `LIMIT`. CQL này không được tối ưu “tự động hơn” vì gọi qua mapper; phần lớn lợi ích đến từ **cách truy cập một partition có giới hạn**.

## 5. Tích hợp mapper: dependency runtime và annotation processor

Java Driver 4.x thường tách **Core Driver**, **mapper runtime** và **annotation processor**. Annotation processor chạy trong quá trình compile để tạo implementation; mapper runtime hỗ trợ mã được sinh khi chương trình chạy.

### 5.1. Ví dụ Maven

~~~xml
<!-- Giá trị phiên bản chỉ minh họa; chọn đúng bản driver 4.x có sẵn
     và được hỗ trợ trong dự án, thống nhất mọi artifact. -->
<properties>
    <cassandra.driver.version>4.17.0</cassandra.driver.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-core</artifactId>
        <version>${cassandra.driver.version}</version>
    </dependency>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-mapper-runtime</artifactId>
        <version>${cassandra.driver.version}</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.datastax.oss</groupId>
                        <artifactId>java-driver-mapper-processor</artifactId>
                        <version>${cassandra.driver.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**Các điểm cần kiểm tra:**

- Cố định **một phiên bản** phù hợp của `java-driver-core`, mapper runtime và processor; kiểm tra compatibility matrix của bản Cassandra/JDK/driver đang dùng.
- Annotation processing phải được **bật trong build**. Nếu tắt, class kiểu `TelemetryMapperBuilder` sẽ không được tạo và project có thể lỗi compile.
- Một IDE biên dịch được nhưng build CI không biên dịch được có thể do **processor paths khác nhau**, không phải Cassandra node lỗi.
- Code generation **không kết nối database ở compile time** để xác minh mọi cột/bảng tồn tại trên cluster thực. Schema thay đổi vẫn cần migration, integration test và hậu kiểm.
- Không lấy phiên bản trong ví dụ như “mới nhất”. Khi dùng version khác, kiểm tra **tên annotation, supported return types và API mapper** tương ứng.

### 5.2. Đừng gọi compile-time generation là “reflection ORM nặng”

Một số ORM ánh xạ qua reflection/proxy ở runtime. Mapper 4.x của driver Cassandra **sinh mã Java** cho DAO và entity mapping trước khi ứng dụng chạy; điều đó thường giảm reflection động trong hot path. Tuy nhiên:

1. Mã sinh vẫn cần **decode CQL, tạo entity, gán property và xử lý null/codec**.
2. Tạo nhiều entity tạo **object allocation và GC pressure**.
3. Một phương thức mặc định trả `SELECT *` vẫn mang **byte payload và cột không cần thiết**.
4. Một lời gọi DAO gây nhiều CQL statements thì network/replica cost vẫn cộng dồn.
5. Tốc độ cần đo dưới **cùng câu CQL, paging, RF/CL và workload**, không kết luận từ kiến trúc codegen.

## 6. `@Entity`: ánh xạ đầy đủ partition/clustering key

Trong ví dụ sau, tên field Java dùng camelCase nhưng cột Cassandra dùng snake_case. Việc ghi **`@CqlName` tường minh** tránh phụ thuộc quy tắc suy tên và giúp người đọc thấy primary key.

~~~java
// EventRecord.java
import com.datastax.oss.driver.api.mapper.annotations.CqlName;
import com.datastax.oss.driver.api.mapper.annotations.Entity;
import com.datastax.oss.driver.api.mapper.annotations.PartitionKey;
import com.datastax.oss.driver.api.mapper.annotations.ClusteringColumn;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Entity
@CqlName("events_by_device_day")
public class EventRecord {
    @PartitionKey(0)
    @CqlName("device_id")
    private String deviceId;

    @PartitionKey(1)
    @CqlName("event_day")
    private LocalDate eventDay;

    @ClusteringColumn(0)
    @CqlName("event_time")
    private Instant eventTime;

    @ClusteringColumn(1)
    @CqlName("event_id")
    private UUID eventId;

    @CqlName("event_type")
    private String eventType;

    @CqlName("payload")
    private String payload;

    public EventRecord() {}

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
~~~

**Đọc annotation đúng ý nghĩa:**

- `@PartitionKey(0)` và `@PartitionKey(1)` phản ánh **thứ tự các thành phần partition key**. Đổi nhầm thứ tự hoặc bỏ `eventDay` không phải tối ưu hóa; nó có thể gây binding sai hoặc query không còn định tuyến được.
- `@ClusteringColumn(0/1)` phản ánh thứ tự clustering columns của bảng; việc trường `eventTime` đứng trước `eventId` là một phần **hợp đồng schema**.
- `Instant` dùng cho CQL `timestamp`, `LocalDate` cho `date`, `UUID` cho `uuid` trong Java Driver 4.x.
- POJO có constructor mặc định và getters/setters để mapper tạo/điền dữ liệu. Entity này là **record đọc/ghi CQL**, không phải transaction aggregate hay class tự theo dõi thay đổi.
- `@CqlName("events_by_device_day")` chỉ định bảng; **keyspace** được xác định bởi session/config/default schema hoặc mapping setup phù hợp. Lab bên dưới thiết lập `withKeyspace("telemetry_mapper")` để tránh mơ hồ.

### 6.1. Lỗi mapping thường gặp

| Lỗi | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Nhầm `eventDay` là regular column | DAO không match key hoặc query thiếu phần partition. | So `PRIMARY KEY` của bảng với annotations. |
| Đổi `timestamp` thành `String` tùy ý | Mapping cần custom codec hoặc lỗi kiểu. | Dùng `Instant` và quy ước UTC rõ ràng. |
| Dùng `int` cho cột có thể `null` | Không biểu diễn được giá trị null. | Chọn kiểu nullable phù hợp; đánh giá semantics null/unset. |
| Đổi tên property nhưng không đổi annotation/CQL | Dữ liệu không map như mong đợi hoặc build/runtime lỗi. | Dùng tên cột tường minh, integration test với schema thật. |
| Tạo entity rất lớn cho endpoint chỉ cần 3 cột | Tăng network/decoding/allocation nếu query chọn tất cả. | Thiết kế projection, DTO hoặc Core `Row` mapping. |

## 7. `@Dao`: gom truy vấn vào API nhỏ và rõ ràng

~~~java
// EventDao.java
import com.datastax.oss.driver.api.core.PagingIterable;
import com.datastax.oss.driver.api.mapper.annotations.Dao;
import com.datastax.oss.driver.api.mapper.annotations.Insert;
import com.datastax.oss.driver.api.mapper.annotations.Query;
import com.datastax.oss.driver.api.mapper.annotations.Select;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Dao
public interface EventDao {
    // Sinh SELECT cho primary key cụ thể.
    @Select
    EventRecord findById(
        String deviceId,
        LocalDate eventDay,
        Instant eventTime,
        UUID eventId);

    // Sinh INSERT từ các property của entity.
    @Insert
    void insert(EventRecord event);

    // Đọc một clustering range trong đúng một partition.
    @Query(
        "SELECT device_id, event_day, event_time, event_id, " +
        "event_type, payload " +
        "FROM telemetry_mapper.events_by_device_day " +
        "WHERE device_id = :deviceId AND event_day = :eventDay " +
        "AND event_time >= :fromInclusive " +
        "AND event_time < :toExclusive LIMIT :maxRows")
    PagingIterable<EventRecord> findWindow(
        String deviceId,
        LocalDate eventDay,
        Instant fromInclusive,
        Instant toExclusive,
        int maxRows);
}
~~~

**Lưu ý thực hành:** `@Select` và `@Insert` sinh statement dựa trên metadata entity; `@Query` cho phép mô tả CQL cụ thể. Mọi phương thức phải được compile-time processor kiểm tra theo các return types/parameters mà phiên bản mapper hỗ trợ. Nên bật option compiler để giữ **parameter metadata** khi thư viện/processor yêu cầu và kiểm tra generated source khi dùng `@Query` phức tạp.

| Method | Dễ dùng khi | Cần chú ý |
| --- | --- | --- |
| `findById` với `@Select` | Read chính xác một hàng theo full primary key. | Không dùng thay cho range query hoặc query thiếu partition key. |
| `insert` với `@Insert` | Ghi entity có mapping đầy đủ. | Timestamp/TTL/null/unset và retry idempotency; không coi là transaction multi-table. |
| `findWindow` với `@Query` | Đọc khoảng clustering trong một partition. | Giới hạn time window, `maxRows`, paging, object mapping và server tombstones. |
| Custom methods trong DAO/service | Query nghiệp vụ không vừa pattern CRUD. | Kiểm soát CQL statement, projection, CL và instrumentation. |

**Một DAO không nên có hàm `getAllEvents()` vô hạn** chỉ vì phương thức kiểu Java dễ khai báo. Với Cassandra, interface cần thể hiện **ràng buộc truy cập partition** ở chữ ký: `deviceId`, `eventDay`, `from`, `to` và `limit`.

## 8. `@Mapper`, builder sinh và vòng đời `CqlSession`

~~~java
// TelemetryMapper.java
import com.datastax.oss.driver.api.mapper.annotations.DaoFactory;
import com.datastax.oss.driver.api.mapper.annotations.Mapper;

@Mapper
public interface TelemetryMapper {
    @DaoFactory
    EventDao eventDao();
}
~~~

Nếu annotation processing chạy đúng, build sinh implementation và builder tương ứng; ví dụ kiểu tên `TelemetryMapperBuilder`. Ứng dụng tạo một session sống lâu, rồi dùng DAO:

~~~java
// MapperDemo.java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class MapperDemo {
    public static void main(String[] args) {
        // Chỉ dùng lab; production cần TLS và auth thích hợp.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .withKeyspace("telemetry_mapper")
                .build()) {

            TelemetryMapper mapper =
                new TelemetryMapperBuilder(session).build();
            EventDao dao = mapper.eventDao();

            EventRecord event = dao.findById(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));

            if (event != null) {
                System.out.println(event.getEventType());
            }

            // Một partition ngày, một range nửa kín.
            for (EventRecord row : dao.findWindow(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                Instant.parse("2026-11-21T10:00:00Z"),
                100)) {
                System.out.println(
                    row.getEventTime() + " " + row.getEventId());
            }
        }
    }
}
~~~

### 8.1. Chú ý khi chạy example

1. Tạo `CqlSession` **một lần trong vòng đời service**, không tạo trong từng HTTP handler. Session thread-safe cho nhiều request và quản lý pool/routing/metadata.
2. `TelemetryMapperBuilder` là **mã build sinh**, nên nếu IDE không thấy class cần kiểm tra Maven/Gradle annotation processing và output generated sources.
3. Keyspace mặc định phải đúng. Một entity chỉ có `@CqlName("events_by_device_day")` không nên ngầm dựa vào “keyspace cuối đã dùng trong cqlsh”.
4. Cấu hình **consistency level** của truy vấn DAO đến từ driver config/profile hoặc statement attributes theo mapper version; đừng mặc định `@Select` đồng nghĩa `LOCAL_QUORUM`. Kiểm tra effective config, ví dụ `basic.request.consistency = LOCAL_QUORUM` khi policy cần.
5. `PagingIterable` được tiêu thụ qua iterator; **duyệt hết** có thể kéo thêm nhiều page. `dao.findWindow(...,100)` có `LIMIT` 100 nhưng không giới hạn số tombstone vật lý được quét.
6. Entity được tạo khi row được map. Nếu hàng trả về rất nhiều hoặc payload lớn, tránh giữ tất cả `EventRecord` trong `List` không giới hạn.
7. Đường `@Insert` **không tự chứng minh idempotency của toàn workflow**. Write timeout có thể xảy ra sau khi một số replica đã ghi.

## 9. Cùng một CQL, Core API đọc trực tiếp và map DTO

Để so sánh công bằng, dùng **cùng schema, partition key, clustering range, column projection, CL, page size và `LIMIT`**; chỉ thay cách chuyển hàng sang đối tượng Java. Ví dụ Core Driver:

~~~java
// CoreReadExample.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class CoreReadExample {
    public static final class EventSummary {
        public final Instant eventTime;
        public final UUID eventId;
        public final String eventType;

        public EventSummary(Instant time, UUID id, String type) {
            eventTime = time;
            eventId = id;
            eventType = type;
        }
    }

    public static List<EventSummary> findSummary(
            CqlSession session,
            PreparedStatement prepared,
            String deviceId,
            LocalDate day,
            Instant from,
            Instant until) {

        BoundStatement statement = prepared.bind(
                deviceId, day, from, until)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        List<EventSummary> output = new ArrayList<>();
        ResultSet result = session.execute(statement);
        for (Row row : result) {
            output.add(new EventSummary(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }
        return output;
    }

    public static PreparedStatement prepare(CqlSession session) {
        return session.prepare(
            "SELECT event_time, event_id, event_type " +
            "FROM telemetry_mapper.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");
    }
}
~~~

**Điểm khác biệt:** ví dụ Core này **chỉ đọc ba cột**, không đọc `payload` và không xây `EventRecord` đầy đủ. Nếu benchmark nó nhanh hơn DAO ở mục 8, **không thể quy toàn bộ chênh lệch cho mapper**, vì projection khác nhau. Muốn đo overhead thuần mapping, phải dùng **cùng số cột** ở cả hai bên; muốn đo giá trị kiến trúc cho endpoint summary, lại nên so các phiên bản thực tế với đúng yêu cầu dữ liệu.

### 9.1. So sánh hai cách bằng đúng tiêu chí

| Tiêu chí | Mapper/DAO | Core `Row`/prepared | Gợi ý quyết định |
| --- | --- | --- | --- |
| Mã boilerplate | Ít khi CRUD/lookup thường gặp. | Viết binding và getter rõ ràng cho từng query. | DAO tốt cho nhiều bảng và quy trình dài hạn. |
| Type safety/mapping | Gắn annotation và codegen, dễ đọc entity. | Gắn tên cột/kiểu ở call site, cần test. | Cả hai đều có thể lỗi khi schema khác. |
| Column projection | Có thể tối ưu bằng `@Query`, DTO/projection phù hợp. | Dễ chọn vài cột chính xác. | Chọn **ít cột cần thiết nhất** cho hot path. |
| Phân bổ object | Entity + property allocation. | Tùy implementation; có thể không tạo DTO hoặc tạo DTO nhỏ. | Benchmark allocation/GC thực tế. |
| Paging | Do driver core thực hiện; mapper bọc API kết quả. | Driver core trực tiếp. | Giới hạn page/rows ở cả hai. |
| CQL/routing | Phụ thuộc query mà DAO phát. | Phụ thuộc query developer viết. | Kiểm tra full partition key. |
| Migration schema | Entity/DAO phải cập nhật/compile. | Query/Row mapping cũng phải cập nhật. | Dùng integration test với phiên bản schema. |
| Instrumentation | Có thể cần interceptor/wrapper, profile, query name. | Dễ bọc statement/đo chi tiết. | Chọn nơi quan sát đủ minh bạch. |

**Không có quy tắc “Core luôn nhanh hơn” hoặc “mapper luôn miễn phí”.** Kiểu thực thi, số cột và số rows thường ảnh hưởng nhiều hơn trừu tượng hóa, nhưng với đường đọc cực nóng, object allocation mỗi row có thể đáng kể.

## 10. Chi phí trừu tượng hóa: sáu thành phần cần tách riêng

Một cách tư duy:

~~~text
Tổng thời gian lời gọi từ Java
  ≈ chờ admission/queue
  + chuẩn bị/bind statement
  + routing + network đến coordinator
  + xử lý đọc/ghi phía coordinator/replicas
  + truyền response và paging
  + decode CQL + chuyển Row -> Entity/DTO
  + công việc nghiệp vụ sau map

Với nhiều page/statement, có thể cộng nhiều vòng
network, paging, query và mapping.
~~~

Công thức là **sơ đồ định tính**, không khẳng định mọi bước hoàn toàn tuần tự hay có thể cộng chính xác trong mọi implementation. Với async concurrency, các pha có thể chồng lấp và cần tracing/profiling để phân tách.

### 10.1. Chi phí 1 — Prepared statement và initialization

Mapper có thể sinh đường chuẩn bị/bind statement; Core API cũng nên **prepare một lần, tái dùng nhiều lần**. Nếu một bên bị đo bao gồm prepare/initialization còn bên kia dùng prepared statement đã warm, benchmark sẽ lệch.

**Cách đo:** tách **cold-start/warm-up** và hot-path request; warm cả mapper DAO và Core prepared trước khi đo p99 steady state. Khi so latency startup, đo riêng thời gian tạo `CqlSession`, tạo mapper, metadata load và chuẩn bị query.

### 10.2. Chi phí 2 — Tạo object và allocation

Giả sử query trả **5.000 rows**, mapper tạo 5.000 `EventRecord`. Mỗi row còn có object/string/codec tùy kiểu:

~~~text
5.000 rows × 1 entity/row  = 5.000 entity objects
10.000 requests/min       = 50 triệu entity objects/min
                            (nếu mỗi request đều trả 5.000 rows)
~~~

Đây chỉ là phép nhân **minh họa cực đoan**, chưa tính các đối tượng cho `String`, `UUID`, `Instant` và buffers, cũng không có nghĩa tất cả objects sống đồng thời. Nếu ứng dụng chỉ cần đếm hoặc trích ba trường, mapper toàn hàng có thể tạo GC pressure không cần thiết.

### 10.3. Chi phí 3 — Column projection và payload

**`SELECT *`** khiến server phải trả nhiều cột hơn ứng dụng cần; mapper không có cách “không trả byte payload” sau khi server đã gửi. Nếu `payload` là text 100 KiB/hàng và API chỉ cần `event_time`, thì:

~~~text
100 rows × 100 KiB payload ≈ 9,8 MiB dữ liệu payload
Chọn chỉ 3 cột nhỏ ≪ 9,8 MiB (tùy kích thước thực)
~~~

**Đừng đổ lỗi mapper khi nguyên nhân là `SELECT *`.** Cân nhắc **`@Query` với danh sách cột**, DTO nhỏ hoặc bảng summary riêng theo truy vấn. Một entity mapping cột thiếu phải có semantics rõ; không ghi lại entity **chỉ được nạp một phần** như thể nó là hàng đầy đủ.

### 10.4. Chi phí 4 — Codec/chuyển đổi kiểu

`timestamp` ↔ `Instant`, `date` ↔ `LocalDate`, `uuid` ↔ `UUID` có hỗ trợ trong driver. Với UDT, nested collections, JSON, conversion sang enum/domain class hoặc custom codecs, CPU/allocation có thể lớn hơn phần gán field thuần.

- Không parse JSON lớn trong getter của entity cho mỗi lần serialize response.
- Không biến `blob` lớn thành hàng loạt bản copy byte array nếu chỉ cần metadata.
- Benchmark custom codecs với dữ liệu thật và độ sâu nested structures.
- Đặt codec theo đúng version/registration mechanism; một lỗi mapping type không phải lỗi consistency của Cassandra.

### 10.5. Chi phí 5 — Paging và giữ kết quả trong bộ nhớ

`PagingIterable<EventRecord>` không nhất thiết phải chứa tất cả kết quả trong RAM tại thời điểm tạo. Nhưng nếu service làm:

~~~java
List<EventRecord> all = new ArrayList<>();
for (EventRecord row : dao.findWindow(
        deviceId, day, from, until, maxRows)) {
    all.add(row);
}
~~~

thì chính **service đã giữ tất cả object** đến khi `all` được giải phóng. Với `LIMIT` lớn, nhiều request đồng thời và payload nặng, peak heap tăng nhanh. Page size chỉ chia dữ liệu nhận về, **không giới hạn tổng số hàng được service giữ**.

### 10.6. Chi phí 6 — Nhiều DAO calls (N+1) và fan-out

Ví dụ anti-pattern:

~~~java
for (Device device : devices) {
    // Một query cho mỗi thiết bị; 10.000 devices -> 10.000 queries.
    EventRecord event = dao.findById(
        device.getId(), day, timestamp, eventId);
    // ...
}
~~~

DAO dễ gọi có thể **che số round-trip**. Nếu cần timeline cho 10.000 devices, hãy thiết kế bảng/projection theo `site_id`/bucket hoặc precomputed rollup phù hợp; đừng chữa bằng `ALLOW FILTERING` hoặc unbounded `CompletableFuture`. Nếu bắt buộc fan-out, đặt trần **concurrency, số partition, deadline và bytes** và kiểm tra p99/replica pressure.

## 11. `@Query` không biến truy vấn sai thành truy vấn tốt

Một mapper có thể sinh Java type-safe code, nhưng **CQL do DAO gửi vẫn phải thỏa mô hình truy vấn Cassandra**.

### 11.1. Ví dụ phản mẫu: thiếu partition key

~~~java
// ĐÂY LÀ PHẢN MẪU, KHÔNG dùng trên bảng production lớn.
@Query(
    "SELECT device_id, event_day, event_time, event_id, " +
    "event_type, payload FROM telemetry_mapper.events_by_device_day " +
    "WHERE event_type = :type ALLOW FILTERING")
PagingIterable<EventRecord> findAllOfType(String type);
~~~

Nếu `event_type` không thuộc partition key/index/access path thích hợp, truy vấn có thể cần **scan phân tán qua nhiều partition**, rồi lọc phần nhỏ kết quả. Dù viết là `dao.findAllOfType("ALARM")` trông tự nhiên, chi phí ở coordinator/replicas có thể rất lớn.

**Đừng coi `ALLOW FILTERING` là một hint tối ưu hóa.** Nó cho phép một số dạng truy vấn mà Cassandra có thể từ chối vì có nguy cơ scan, không tạo sẵn index hay tự giảm fan-out. Nếu nghiệp vụ cần tìm alarm của mọi thiết bị theo site và giờ, nên thiết kế bảng/projection tương ứng, tính partition size, RF và độ nóng.

### 11.2. `@Select` đọc theo primary key, `@Query` giải quyết pattern cụ thể

| Use case | DAO/CQL phù hợp | Rủi ro nếu lạm dụng |
| --- | --- | --- |
| Lookup một event bằng full primary key | `@Select` với đủ `deviceId,eventDay,eventTime,eventId`. | Ít rủi ro fan-out, nhưng vẫn có network/CL/timeout. |
| Đọc 20 event mới nhất một ngày | `@Query` với đủ partition key + `LIMIT 20`. | Có thể quét tombstone trước khi tìm đủ 20 hàng sống. |
| Đọc một khoảng 2 giờ trong ngày | `@Query` với clustering range `>= start AND < end`. | Range rộng/hot partition vẫn cần đo. |
| Đọc 3 ngày liền | **Ba hoặc bốn bucket** tùy ranh giới và chiều dài khoảng. | Mapper không tự merge/sort giữa partition. |
| Đọc alarm theo site/giờ | Bảng/projection khác, key theo site và bucket. | Không nên lạm dụng `ALLOW FILTERING`. |
| Thống kê tổng theo tháng cho 1 triệu thiết bị | Rollup/analytics data model riêng. | Không quét raw events bằng `dao.findAll()`. |

### 11.3. Khoảng nửa kín và multi-bucket

Một endpoint hỏi các event trong **[2026-11-20T23:45:00Z, 2026-11-21T00:15:00Z)**. Query `findWindow` của DAO chỉ đọc **một** `eventDay` mỗi lần, vì `eventDay` nằm trong partition key.

~~~text
Partition (device-7, 2026-11-20)
  [23:45:00Z, 2026-11-21T00:00:00Z)

Partition (device-7, 2026-11-21)
  [00:00:00Z, 2026-11-21T00:15:00Z)

Sau đó service merge các hàng theo (event_time DESC, event_id tie-breaker).
~~~

Khi API chỉ cần **global top 50**, không thể chỉ đọc một bucket rồi gọi kết quả là top 50 của cả khoảng. Với dữ liệu được chia theo ngày UTC chuẩn, có thể đọc những bucket giao nhau, **giới hạn số bucket**, chọn ứng viên và merge. Thứ tự `event_id` làm tie-breaker phải thống nhất giữa cách sắp trên Cassandra và phía Java; với UUID, cần kiểm chứng comparator/serialization tương thích thay vì mặc định `UUID.compareTo` luôn tương đương thứ tự sắp CQL.

**Số bucket tối đa** cũng là một guardrail của API. Nếu người dùng vô tình gửi time window 5 năm với bucket 15 phút, mapper sẽ không tự ngăn một cuộc quét hàng chục nghìn partition.

### 11.4. Token-aware routing vẫn phụ thuộc câu lệnh

Driver có thể tận dụng thông tin **partition key được bind đầy đủ** để định tuyến token-aware, chọn coordinator gần natural replica thích hợp tùy policy/topology. Annotation `@Dao` tự nó **không** bảo đảm routing tốt:

- Query thiếu một phần composite partition key không thể là lookup cùng partition như trên.
- Dùng statement phức tạp hoặc custom CQL thiếu metadata/routing information có thể làm driver không xác định token tương ứng.
- `localDatacenter`, contact points, load balancing policy và khả năng replica vẫn ảnh hưởng coordinator được chọn.
- `LOCAL_QUORUM` có thể yêu cầu đọc từ nhiều replica local DC; nó không đồng nghĩa “driver gửi request trực tiếp tới đúng một replica”.

Nếu một phương thức DAO đột nhiên chậm, hãy lấy **CQL thực tế, bound key shape, coordinator, RF/CL và server metrics** trước khi quy lỗi cho annotation mapping.

## 12. Cập nhật, `null`, `UNSET`, TTL và tombstone: chi phí không chỉ là CPU

Đối với Cassandra, `INSERT` thường có semantics **upsert**, không giống `INSERT` SQL quan hệ kiểm tra trùng primary key mặc định. Update và delete được hòa giải theo timestamp của mutation. Khi dùng mapper, các semantics ấy **không biến mất**.

### 12.1. Cần phân biệt “không có giá trị”, “không cập nhật” và “xóa”

| Ý định nghiệp vụ | CQL/driver semantics cần hiểu | Nếu map nhầm |
| --- | --- | --- |
| Giữ nguyên cột hiện có | Bind marker ở trạng thái **UNSET** khi thao tác/phiên bản cho phép, hoặc không đưa cột vào câu UPDATE. | Ghi null có thể tạo tombstone ngoài ý muốn. |
| Xóa giá trị cột | Ghi `null` hoặc `DELETE` tương ứng. | Có thể làm mất dữ liệu trước đó. |
| Đặt giá trị mới | Bind value mới với mutation timestamp/TTL phù hợp. | Nếu timestamp thấp hơn bản cũ, cập nhật có thể không thắng. |
| Không biết giá trị khi đọc projection | Trường Java có thể `null` vì chưa SELECT cột ấy. | Lưu lại entity thiếu cột có thể xóa dữ liệu nếu null được ghi. |

Trong CQL, `null` viết vào cột có thể mang nghĩa **xóa cell**, dẫn tới tombstone; **UNSET** ở driver tương ứng “không ghi trường này” khi được hỗ trợ. Các annotation/tuỳ chọn **null-saving strategy** của mapper thay đổi theo method/phiên bản. **Không đoán default**; hãy kiểm tra generated statement, cấu hình annotation và làm integration test với các cột null.

### 12.2. Ví dụ update một cột an toàn về phạm vi

~~~sql
UPDATE telemetry_mapper.events_by_device_day
SET payload = '21.7'
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:01:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174002;
~~~

Một câu `UPDATE` đặt **đúng cột cần đổi** giúp không vô tình ghi những property Java khác đang null. Có thể gói nó vào DAO với `@Query` cụ thể khi use case yêu cầu:

~~~java
// Phương thức bổ sung trong EventDao:
@Query(
    "UPDATE telemetry_mapper.events_by_device_day SET payload = :payload " +
    "WHERE device_id = :deviceId AND event_day = :eventDay " +
    "AND event_time = :eventTime AND event_id = :eventId")
void updatePayload(
    String payload,
    String deviceId,
    LocalDate eventDay,
    Instant eventTime,
    UUID eventId);
~~~

**Không dùng `@Update` một entity chỉ nạp hai trường rồi giả định các trường null còn lại không bị động tới.** Hành vi phụ thuộc chiến lược null/unset, annotation và generated CQL. Việc cập nhật một phần cần hợp đồng rõ giữa service và DAO.

### 12.3. TTL không tự dựa trên `event_time`

~~~sql
-- Ví dụ ghi giá trị mới có thời gian sống 3600 giây.
UPDATE telemetry_mapper.events_by_device_day
USING TTL 3600
SET payload = 'temporary reading'
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:01:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174002;
~~~

TTL thường được tính **từ lúc mutation được ghi** theo semantics Cassandra, **không tự tính từ cột `event_time`**. Nếu DAO dùng `@Insert` lại một hàng cũ với TTL mới, thời gian sống có thể bị gia hạn. Nếu dữ liệu có delete/TTL và mapper không giữ nguyên mutation timestamp, backfill hoặc retry có thể làm dữ liệu cũ xuất hiện lại khi ghi đè tombstone.

### 12.4. LWT, counter và batch không phải transaction ORM

- `IF NOT EXISTS` hoặc `UPDATE ... IF ...` dùng **lightweight transaction/CAS** cho những điều kiện thích hợp, có latency/coordination riêng. Mapper không khiến CAS miễn phí.
- `counter` có semantics và retry rủi ro khác với upsert idempotent; không tăng counter lại khi chưa biết kết quả timeout.
- `BEGIN BATCH` có semantics atomicity nhất định của Cassandra, nhưng **không có isolation đa partition như transaction JPA** và batch lớn nhiều partition có thể tạo overload.
- Việc service gọi `dao.insertA()` và `dao.insertB()` không tạo atomic transaction; cần event log, idempotency hoặc reconciliation nếu hai bảng phải luôn đồng bộ.

**Tư duy đúng:** DAO ẩn cách phát statement, **không ẩn đi mô hình mutation và consistency** của Cassandra.

## 13. Mapping collections, UDT, enum và kiểu tùy chỉnh

Cassandra có kiểu `list`, `set`, `map`, tuple, UDT, blob và nhiều primitive. Các loại ấy hữu ích nhưng không phải một “object graph” tự do như ORM quan hệ.

### 13.1. Dự toán chi phí khi có collection

Giả sử entity có một `map<text,text>` chứa 20.000 phần tử. Query muốn lấy `eventType` nhưng entity/statement chọn luôn map lớn:

- Node có thể phải truyền nhiều byte hơn.
- Driver phải decode map và tạo object/collections Java tương ứng.
- GC pressure và thời gian serialize JSON/HTTP tăng.
- Update collection lớn hoặc xóa nhiều phần tử có chi phí storage/tombstone riêng.

**Đừng tạo collection không giới hạn** trong một Cassandra row để mô phỏng quan hệ một-nhiều. Thông thường, dùng **nhiều rows với clustering keys** sẽ dễ dự báo kích thước partition và range reads hơn, với giới hạn phù hợp.

### 13.2. UDT và custom codec

| Nhu cầu | Cách tiếp cận | Điều cần đo |
| --- | --- | --- |
| UDT ổn định, kích thước nhỏ | Khai báo mapping/codec phù hợp với driver. | CPU decode, null fields, schema evolution. |
| Enum ứng dụng | Mapping string/int hoặc codec có version rõ. | Tương thích khi enum thêm giá trị mới. |
| JSON payload nặng | Lưu text/blob, chỉ parse lúc thực sự cần. | Bytes/network, JSON parser allocation và GC. |
| Tiền tệ/số độ chính xác cao | Kiểu CQL/Java tương ứng, không chuyển tùy tiện sang float. | Correctness, rounding và schema compatibility. |
| Blob hàng MB | Cân nhắc object storage + metadata trong Cassandra. | Message size, row size, heap/direct memory và latency. |

**Cảnh báo:** custom codec có thể phát sinh lỗi runtime khi schema/cột thay đổi. Build sinh mapper kiểm tra cấu trúc Java/annotations, **không chứng minh mọi giá trị dữ liệu thật đều decode được**. Integration tests phải có mẫu `null`, collection rỗng/lớn, dữ liệu cũ và phiên bản UDT khác nhau.

## 14. Đồng bộ, bất đồng bộ và giới hạn concurrency

DAO phương thức đồng bộ có thể đơn giản và đủ tốt với lookup ngắn. Nhưng một API đọc hàng chục bucket hoặc producer ghi nhiều event cần hiểu **số statement đang chờ**. Mapper không tự giới hạn concurrency của service.

### 14.1. Giao diện bất đồng bộ của Core Driver

~~~java
// Cùng CqlSession và PreparedStatement, chỉ đổi đường execute.
CompletionStage<AsyncResultSet> future = session.executeAsync(boundStatement);
future.whenComplete((page, error) -> {
    if (error != null) {
        // Ghi error_type/correlation ID, không log credentials/payload.
        return;
    }
    // page là kết quả bất đồng bộ; với SELECT nhiều page,
    // cần fetchNextPage() theo API/phiên bản, không giả định đủ mọi row.
});
~~~

Đoạn này là **minh họa nằm trong method**, cần imports `CompletionStage`, `AsyncResultSet` và `boundStatement` đã tạo. DAO/mapping version cũng có thể cung cấp các kiểu trả về async phù hợp; dùng **return type được processor hỗ trợ** thay vì tự viết `CompletableFuture` rồi nghĩ rằng mapper sẽ nhận mọi kiểu.

### 14.2. Ghi với concurrency hữu hạn

Ví dụ dưới dùng Core Driver để minh họa **bounded in-flight** ngay cả khi ứng dụng dùng mapper cho phần lớn các read:

~~~java
// BoundedEventWriter.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedEventWriter {
    private static final int MAX_IN_FLIGHT = 8;

    public static void writeLabBatch(
            CqlSession session, List<EventRecord> events)
            throws InterruptedException {

        PreparedStatement insert = session.prepare(
            "INSERT INTO telemetry_mapper.events_by_device_day " +
            "(device_id, event_day, event_time, event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)");

        Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger uncertain = new AtomicInteger();
        List<CompletableFuture<Void>> completions = new ArrayList<>();

        for (EventRecord e : events) {
            // Chặn producer thông thường, KHÔNG block driver I/O callback.
            permits.acquire();
            BoundStatement write = insert.bind(
                    e.getDeviceId(), e.getEventDay(),
                    e.getEventTime(), e.getEventId(),
                    e.getEventType(), e.getPayload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            CompletableFuture<Void> done = new CompletableFuture<>();
            completions.add(done);
            try {
                session.executeAsync(write).whenComplete((result, error) -> {
                    try {
                        if (error == null) {
                            success.incrementAndGet();
                            done.complete(null);
                        } else {
                            uncertain.incrementAndGet();
                            done.completeExceptionally(error);
                        }
                    } finally {
                        permits.release();
                    }
                });
            } catch (RuntimeException dispatchError) {
                uncertain.incrementAndGet();
                done.completeExceptionally(dispatchError);
                permits.release();
            }
        }

        try {
            CompletableFuture.allOf(
                completions.toArray(new CompletableFuture[0])).join();
        } catch (CompletionException ex) {
            System.err.println("At least one write did not ACK");
        }
        System.out.println("acked=" + success.get()
            + " failed_or_unknown=" + uncertain.get());
    }
}
~~~

**Điều code làm được:** không vượt quá tám async calls trong vòng lặp này; callback nhẹ, không block I/O; `PreparedStatement` được tái sử dụng. **Điều code chưa làm được:** durable retry queue, per-tenant/global rate limit, API deadline, cancellation, TTL/timestamp semantics, idempotency và bảo vệ khi process chết. Không dùng nguyên xi làm ingestion pipeline cho dữ liệu nghiệp vụ không thể mất.

Một `WriteTimeout` là trạng thái **có thể đã ghi một phần**, không đồng nghĩa chưa ghi. Nếu retry với một `eventId` mới thì có thể tạo duplicate; mọi retry cần stable primary key và quy tắc mutation timestamp/TTL phù hợp.

### 14.3. Giới hạn tại nhiều lớp

~~~text
API admission capacity   : 100 requests/process (ví dụ)
API waiting queue        : tối đa 200 request (ví dụ)
DB in-flight per process : tối đa 32 statements (ví dụ)
Driver request throttler : budget riêng nếu bật
Global fleet             : tổng across N pods và mọi workload
~~~

Nếu dịch vụ có 30 pod và mỗi pod cho 32 DB statements đang chạy, trần theo model đơn giản là **30 × 32 = 960** in-flight toàn fleet, chưa tính retry, batch jobs, speculative execution hay service khác. Đây **không phải** số connections hoặc requests/second. Phải benchmark sức chịu tải của **coordinator và replica** trước khi tăng trần.

## 15. Benchmark công bằng: mapper overhead hay CQL overhead?

### 15.1. Định nghĩa ba thí nghiệm riêng

| Test | CQL/column projection | Java mapping | Câu hỏi trả lời |
| --- | --- | --- | --- |
| **A. Mapper full entity** | Đủ sáu cột, đúng partition/range, `LIMIT 100`. | `Row → EventRecord` qua generated mapper. | Chi phí endpoint hiện dùng mapper là bao nhiêu? |
| **B. Core full entity** | **Cùng sáu cột** như A, cùng CL/page/limit. | Tạo `EventRecord` bằng code Core thủ công. | Chênh lệch **mapping implementation** sau khi cố định CQL? |
| **C. Core narrow DTO** | Chỉ `event_time,event_id,event_type`. | `Row → EventSummary` nhỏ. | Thiết kế projection cho endpoint có tiết kiệm đáng kể không? |

Nếu C nhanh hơn A rất nhiều nhưng B gần bằng A, kết luận hợp lý có thể là **đọc thừa payload**, không phải “mapper chậm”. Ngược lại, nếu A chậm hơn B khi CQL/số rows/GC hoàn toàn giống nhau, mới có căn cứ phân tích generated mapper/codec/allocation.

### 15.2. Kiểm soát biến gây nhiễu

1. **Cùng phiên bản Cassandra/driver/JDK**, phần cứng, CL, RF, DC, TLS, request timeout, retry policy.
2. **Cùng dữ liệu và query shape**, cả hot/cold partitions, TTL/tombstones và kích thước payload.
3. **Prepare và warm-up cả hai đường**, không gộp cold-start mapper build vào latency steady state rồi so với prepared Core.
4. **Cùng page size**, giới hạn hàng và **tiêu thụ hết cùng số page**. Đừng so thời gian trả page đầu với thời gian duyệt toàn bộ.
5. **Tách warm cache/cold disk** hoặc ngẫu nhiên thứ tự test; truy vấn chạy sau có thể hưởng cache của truy vấn trước.
6. **Cố định concurrency**, số pod, request mix và burst, rate limiting, retry/sampling.
7. Đo **allocation/GC, CPU, bytes received, rows/sec, latency p50/p95/p99** và server metrics cùng lúc.
8. Kiểm tra **kết quả logic tương đương**; một cách nhanh hơn vì bỏ cột/bỏ row là phép so không hợp lệ.
9. Lặp lại đủ mẫu/cửa sổ và có độ ổn định; **100 request không đủ kết luận p99 chắc chắn**.
10. Coi benchmark **JMH ở cấp Java mapping** và **load test end-to-end** là hai loại đo khác nhau: JMH không thay network/replica behavior.

### 15.3. Bảng kết quả giả lập để luyện diễn giải

| Chỉ số | Mapper full A | Core full B | Core narrow C |
| --- | ---: | ---: | ---: |
| `LIMIT` | 100 | 100 | 100 |
| Byte/response (ước tính của test) | 900 KiB | 900 KiB | 45 KiB |
| Client p99 | 32 ms | 30 ms | 16 ms |
| CPU/row trên đường mapping | 1,2 đơn vị giả lập | 1,0 đơn vị | 0,6 đơn vị |
| Allocation/request | 450 KiB | 410 KiB | 110 KiB |
| Dữ liệu trả đúng? | Có | Có | Có, theo hợp đồng summary |

**Các số trên hoàn toàn giả lập**, không phải benchmark thật của Cassandra/Java Driver. Ví dụ cho thấy **giảm dữ liệu trả về** có thể đem lại khác biệt lớn hơn đổi mapper sang thủ công. Cũng có hệ thống mà object mapping đáng kể nếu hàng cực nhỏ, rất nhiều row/giây và phần lớn dữ liệu đã cache.

### 15.4. Ước lượng tác động ở quy mô lớn

~~~text
Giả sử:
  mỗi request tạo thêm 100 KiB allocation do mapping
  2.000 requests/s

Allocation tăng ≈ 200.000 KiB/s ≈ 195 MiB/s
  (không phải heap sống lâu; là tốc độ allocation).

Nếu GC và application heap đã sát ngưỡng, mức tăng này
có thể làm p99 xấu đi dù Cassandra server latency không đổi.
~~~

Tốc độ allocation khác **live heap size** và khác memory direct/off-heap của driver; theo dõi **JFR/allocation profiler/GC logs** để xác nhận thay vì suy từ công thức đơn giản.

## 16. Tracing, metrics và phân tích p99 theo tầng

### 16.1. Lệnh và quan sát phía Cassandra

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool proxyhistograms
nodetool tablestats telemetry_mapper.events_by_device_day
nodetool tablehistograms telemetry_mapper events_by_device_day
nodetool gcstats
~~~

Giải thích nhanh:

| Chỉ số/công cụ | Dấu hiệu cần xem |
| --- | --- |
| `tpstats` | Pending/blocked/dropped tasks; coordinator hay replica đang quá tải? |
| `compactionstats` | Pending compaction, disk pressure có trùng với p99 tăng? |
| `tablestats` | SSTable count, partition/tombstone/latency thống kê theo version. |
| `tablehistograms` | Phân phối latency và partition size/cell count phù hợp với bảng. |
| `proxyhistograms` | Latency ở coordinator, so với client p99. |
| `gcstats`/JVM logs | GC pauses có tương quan với query chậm không? |
| Client metrics | In-flight, request queue, retry, page fetch và mapping CPU. |

Tên lệnh, tham số và metrics thay đổi theo bản Cassandra. Không lấy một số liệu `nodetool` tích lũy từ lúc node khởi động so với p99 tính trên 5 phút mà không chuẩn hóa cửa sổ.

### 16.2. Tracing một truy vấn trong lab

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT device_id, event_day, event_time, event_id, event_type, payload
FROM telemetry_mapper.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

`TRACING` và `CONSISTENCY` là **lệnh cqlsh**; trong Java Driver, sử dụng tính năng tracing/statement options được phiên bản hỗ trợ. Tracing có thể cho thấy coordinator/replica và hoạt động xử lý của một statement, nhưng **không đo trực tiếp CPU dùng để tạo `EventRecord`** trong JVM ứng dụng.

**Muốn biết mapper mapping chậm**, cần đo từ client:

- Time to first page và time to consume toàn bộ results.
- Số rows/bytes đã nhận.
- CPU samples/allocation trong generated DAO và code mapping.
- Driver retries/speculative execution, queue wait và network latency.
- Số dao calls trên một API transaction (N+1).

### 16.3. Instrumentation theo query template, không theo partition key cá nhân

Gợi ý một event telemetry:

~~~text
timestamp_utc     = 2026-11-21T09:05:00Z
service           = telemetry-api
query_name        = events_find_window_mapper
path              = mapper | core
environment       = staging
local_dc          = dc1
consistency       = LOCAL_QUORUM
result_rows       = 50
result_bytes      = measured-or-estimated
pages_fetched     = 1
elapsed_ms        = 25
error_type        = none
~~~

Không dùng `device_id`, `event_id`, UUID request hay raw CQL có literal riêng tư làm metric labels: **cardinality và nguy cơ lộ dữ liệu** tăng. Logs được quyền truy cập hạn chế; metrics cần labels có tập giá trị nhỏ và ổn định. Correlation ID có thể ghi ở log/trace theo policy, không phải label của histogram p99.

## 17. Thử nghiệm đúng/sai và kiểm tra hồi quy schema

Một annotation processor compile thành công chỉ chứng minh một số ràng buộc Java/mapper đã hợp lệ theo **code và annotation**. Nó không chứng minh production schema, role, RF hay dữ liệu thật đúng như code.

### 17.1. Nhóm test nên có

| Test | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| **Mapper generation** | Build sạch, annotation processor bật. | `TelemetryMapperBuilder` được sinh, không lỗi processor. |
| **Column/key mapping** | Load `device-7`, ngày 21/11, full PK. | Tất cả field đúng kiểu, không đảo partition/clustering key. |
| **Composite key mismatch** | Truy vấn nhầm `eventDay` hoặc bỏ key. | Không được lặng lẽ đọc partition sai/hàng toàn cluster. |
| **Time boundary** | Range [23:59:59Z, 00:00:00Z) và ngày tiếp theo. | Không đếm trùng, không bỏ sót ranh giới UTC. |
| **Null/unset** | Update một field khi field khác null. | Không xóa ngoài ý muốn; chỉ thay cell được định nghĩa. |
| **TTL** | Backfill/insert dữ liệu có expiry. | Không kéo dài retention trái nghiệp vụ. |
| **Schema drift** | Staging thiếu/đổi tên một cột. | Integration test fail có thông tin rõ. |
| **RBAC** | Role readonly thử `SELECT`, rồi thử `INSERT/DELETE` trên lab. | Allow/deny đúng; không chạy bằng superuser. |
| **CL/replica failure** | RF=3, `LOCAL_QUORUM`, một replica chậm/down có kiểm soát. | Error handling và SLO phù hợp, không retry storm. |
| **Paging/memory** | 10.000 rows nhỏ và 100 rows payload lớn. | Bounded heap, thời gian consume có đo, không OOM. |
| **High concurrency** | Nhiều parallel DAO calls, pool/rate limit. | Không tăng queue vô hạn, p99 đạt SLO. |
| **Migration** | Đổi cột/UDT/driver version theo rollout. | Generated mapper tương thích, client old/new được kiểm thử. |

### 17.2. Test mapping có thể ở service boundary

~~~java
// Pseudo-test structure, không phụ thuộc một framework test cụ thể:
EventRecord actual = dao.findById(
    "device-7", LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:00:00Z"),
    UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));

if (actual == null
        || !"HEARTBEAT".equals(actual.getEventType())
        || !"ok".equals(actual.getPayload())) {
    throw new AssertionError("Cassandra mapper mapping mismatch");
}
~~~

Đây chỉ là một **smoke test một hàng**, không phải đối soát toàn bảng. Integration tests nên chạy trên Cassandra phiên bản/schema/tên DC được kiểm soát, với dữ liệu lab tách khỏi production.

### 17.3. Cần có phép thử đối với đường Core thay thế

Nếu một hot path được chuyển từ mapper sang Core `Row`, phải so **kết quả nghiệp vụ** ở những trường hợp:

- `null` và giá trị rỗng trong cột.
- Event có cùng `eventTime` nhưng `eventId` khác.
- Time window ở ranh giới ngày/bucket.
- Tombstone/TTL hết hạn, retry/write timeout.
- Cột/UDT mới xuất hiện trong schema.
- Phân trang nhiều page và page cuối không đủ hàng.

Nếu Core nhanh hơn nhưng làm sai thứ tự event hoặc bỏ trường có ý nghĩa, đó **không phải tối ưu hóa thành công**.

## 18. Bảo mật: DAO rõ ràng nhưng không thay authorization

Một DAO chỉ chứa các method `findById` và `insert` có thể giúp giảm đường gọi sai từ code. Nhưng **quyền Cassandra vẫn kiểm tra trên CQL resources**:

1. Java service có **identity riêng** và `SELECT`/`MODIFY` tối thiểu trên bảng cần thiết; không dùng shared superuser.
2. CQL native connection sử dụng TLS và xác thực server/certificate phù hợp; không tắt peer validation để né lỗi.
3. Authorization kiểm soát **bảng/keyspace**, không mặc nhiên kiểm tra tenant business ID trong partition key. Service vẫn phải xác thực tenant trước khi bind `deviceId`.
4. `@Query` dùng named/positional bind markers thay vì ghép input trực tiếp vào CQL text.
5. JMX/`nodetool`, OS/file access và backup có cơ chế phân quyền khác, không lấy quyền `SELECT` để suy quyền quản trị.
6. Không ghi password, access tokens, raw payload hoặc đầy đủ thông tin cá nhân vào exception/log/tracing.

### 18.1. Chống lẫn tenant ở service layer

~~~java
// Minh họa service boundary, không phải mapper tự cấp tenant security:
public EventRecord readAuthorizedEvent(
        Caller caller, String deviceId, LocalDate day,
        Instant time, UUID eventId) {
    if (!authorizationService.canReadDevice(caller, deviceId)) {
        throw new SecurityException("not authorized for this device");
    }
    return dao.findById(deviceId, day, time, eventId);
}
~~~

Đoạn minh họa dùng `Caller`, `authorizationService`, `dao` được cung cấp bởi ứng dụng. **Không** viết `dao.findById` trực tiếp trong một endpoint mà chỉ dựa vào RBAC cho toàn bảng để giả định Cassandra tự chặn đọc thiết bị của tenant khác.

## 19. Phân loại lỗi DAO: `null` là không tìm thấy, timeout không phải không tìm thấy

Khi mapper trả về một entity hoặc `null` cho lookup một hàng, service thường chuyển thành HTTP 200/404 theo hợp đồng API. Điều đó khác hoàn toàn khi **Cassandra không thể trả kết quả đúng hạn**.

| Tình huống | Ý nghĩa | Cách xử lý nghiệp vụ |
| --- | --- | --- |
| `@Select` trả `null` sau một read thành công | Không tìm thấy hàng còn sống theo truy vấn/CL tại thời điểm đọc. | Có thể trả 404 nếu đúng hợp đồng. |
| `ReadTimeout` từ server | Không thu đủ phản hồi/dữ liệu trước timeout. | Trả lỗi tạm thời/503 hoặc retry có budget khi an toàn; không biến thành 404. |
| Driver request timeout | Driver hết thời gian chờ request/attempt theo semantics. | Kiểm tra deadline, queue, network, retries; không giả định hàng không tồn tại. |
| `Unavailable` | Không đủ replica khả dụng cho CL. | Kiểm tra RF, DC và node health; tăng timeout không tạo replica. |
| `Unauthorized` | Identity không được phép truy cập bảng/tài nguyên. | Sửa RBAC/provisioning; không tự chuyển sang tài khoản superuser. |
| `CodecNotFound`/mapping error (tên lỗi theo version) | Không chuyển đổi được kiểu CQL/Java. | Kiểm tra schema, annotations, codec và dữ liệu. |
| `WriteTimeout` | Không nhận đủ ACK trong thời gian. | Trạng thái mutation có thể chưa rõ; cần idempotency và reconciliation. |

### 19.1. Không che ngoại lệ bằng đối tượng rỗng

~~~java
// PHẢN MẪU: che lỗi database thành dữ liệu nghiệp vụ không tồn tại.
try {
    return dao.findById(deviceId, day, time, eventId);
} catch (RuntimeException ignored) {
    return null;
}
~~~

Hàm trên có thể khiến hệ thống trả **404 sai** khi Cassandra timeout hoặc credentials bị thu hồi. Hướng tốt hơn:

1. Bắt/ghi nhận **loại ngoại lệ** tại service boundary hoặc exception mapper của API.
2. Gắn `query_name`, request correlation ID và UTC time mà không lộ partition key nhạy cảm.
3. Chọn policy retry theo **read/write, idempotency, CL và deadline còn lại**.
4. Không retry vô hạn auth/permission/schema validation failures.
5. Phân biệt **not found, temporary unavailable, permanent bad request và unknown write outcome** trong response contract.

**Mapper không thay đổi semantics của lỗi**, chỉ thay cách Java biểu diễn kết quả.

### 19.2. Query timeout qua mapper và tổng thời gian API

Nếu DAO thực hiện ba `findWindow` cho ba bucket, mỗi statement có timeout hai giây, điều đó **không có nghĩa toàn API sẽ hoàn tất trong hai giây**. Chạy tuần tự có thể kéo dài hơn, và mỗi statement có page fetch riêng. Service phải có:

- **Deadline tổng** tính từ khi nhận request, gồm chờ slot, gọi DAO và merge/sort.
- **Giới hạn số bucket/shard** được phép đọc.
- **Số request đồng thời hữu hạn**, không mở hàng trăm DAO calls cùng lúc.
- **Retry budget** không vượt thời gian còn lại.
- **Ngưỡng byte/row** để không trả payload lớn vô hạn.

Khi timeout, cancellation ở client **không bảo đảm replica đã ngừng mọi việc ngay lập tức**; vì vậy giảm traffic và backpressure vẫn quan trọng.

## 20. Sửa schema và đổi DAO: quy trình triển khai an toàn

Một mapper được sinh theo schema cũ có thể **compile thành công** dù Cassandra đã đổi cột/UDT/primary key trong môi trường đang chạy. Nếu release đổi schema và Java code không có thứ tự, lỗi thường chỉ xuất hiện lúc request thật.

### 20.1. Expand–migrate–contract

~~~mermaid
flowchart TD
    A["Bảng V1 + DAO V1 đang phục vụ"] --> B["EXPAND: thêm cột/bảng V2 phù hợp"]
    B --> C["Triển khai code đọc/ghi tương thích"]
    C --> D["Backfill + dual-write/CDC nếu đổi primary key"]
    D --> E["Reconcile key/value, TTL/delete và late events"]
    E --> F["Shadow read + canary DAO V2"]
    F --> G{"Correctness, p99, GC, RF/CL đạt?"}
    G -->|Không| H["Giữ V1, sửa mapping/pipeline và test lại"]
    H --> D
    G -->|Có| I["Chuyển read sang V2, giữ rollback path"]
    I --> J["Retire V1 sau backup/approval"]
~~~

| Thay đổi schema | Cần làm ở entity/DAO | Rủi ro |
| --- | --- | --- |
| Thêm regular column | Thêm property/annotation nếu cần đọc/ghi; test null ở dữ liệu cũ. | Dữ liệu cũ có `null` và statement full entity có thể đọc thêm byte. |
| Đổi tên cột | Phối hợp schema rename và `@CqlName`/query templates. | Mixed-version clients dùng tên cũ có thể lỗi. |
| Đổi kiểu `text` sang UDT/collection | Thường cần schema migration/bảng mới và codec. | Decode/correctness/performance, không tự cast an toàn. |
| Đổi partition hoặc clustering key | **Bảng mới + migration dữ liệu**, DAO mới. | Token/replica placement, backfill, update/delete/TTL và rollback. |
| Bổ sung projection theo query | DAO/query riêng và pipeline cập nhật projection. | Dual-write một nhánh lỗi có thể gây data drift. |

**Không dùng `ALTER TABLE` để mong đổi cấu trúc primary key hiện hữu.** Cassandra phân bố dữ liệu theo token của partition key, nên đổi khóa ảnh hưởng nơi lưu và hướng truy vấn. Với hệ thống đang ghi liên tục, cần durable mutation capture/catch-up; hai `dao.insert()` vào hai bảng **không tự có tính nguyên tử**.

### 20.2. Mapper version và driver version

Trong một phiên phát hành:

1. Ghi **driver core + mapper runtime + mapper processor** version chính xác, cùng JDK.
2. Xây generated code từ **clean build**, không dựa vào generated sources cũ trên máy developer.
3. Test với Cassandra version, CQL schema và feature set tương thích.
4. Giữ migration theo thứ tự: schema sẵn sàng trước, client code tương thích sau, rồi mới loại cột/bảng cũ.
5. Trên staging, chạy **allow/deny CQL RBAC tests**, prepared query tests, null/UDT/paging tests và load tests.
6. Canary một nhóm Java instances, ghi `mapper_version`/`driver_version` như metadata deployment/metrics có cardinality hữu hạn.
7. Chỉ xóa phương thức DAO cũ khi **mọi client/batch job** đã chuyển; kiểm tra cả luồng chạy theo ngày/tháng.

### 20.3. Dao interface là hợp đồng được version hóa

Một phương thức như `findWindow(deviceId, day, start, end, maxRows)` là một **query contract**. Khi đổi từ bucket ngày sang bucket giờ, đừng giữ nguyên chữ ký rồi âm thầm tính `eventHour` từ `day`; việc đó khiến API có thể bỏ sót dữ liệu. Hoặc:

- Tạo `EventDaoV2` và service read router với migration feature flag; hoặc
- Giữ interface nghiệp vụ `EventRepository` nhưng implement bằng DAO mới, có **integration tests cho toàn khoảng thời gian**.

Đừng coi đổi annotation trong Java là schema migration đã hoàn tất.

## 21. Case study: sau khi thêm mapper, API timeline chậm gấp đôi

Giả sử API lấy 20 sự kiện mới nhất của một thiết bị. Trước khi đổi, đường Core Driver chỉ chọn `event_time,event_id,event_type`, trả DTO ngắn. Sau khi đổi sang mapper, code dùng một phương thức `@Select`/query full entity đọc cả `payload`, rồi serialize đối tượng cho HTTP.

### 21.1. Bằng chứng giả lập

| Quan sát | Trước (Core narrow) | Sau (Mapper full) | Gợi ý |
| --- | ---: | ---: | --- |
| Cột chọn | 3 | 6 | **Thí nghiệm không cùng projection**. |
| Bytes/response | 20 KiB | 600 KiB | Payload có thể chi phối network và decode. |
| Read latency ở coordinator p99 | 14 ms | 16 ms | Server tăng ít, cần kiểm tra nguyên nhân khác. |
| Client full-consume p99 | 25 ms | 53 ms | Phía client/network/mapping có thêm chi phí. |
| Allocation/request | 120 KiB | 1,2 MiB | Có thể tăng GC khi concurrency lớn. |
| API response bytes | 5 KiB | 5 KiB | Payload đọc về nhưng cuối cùng không trả ra ngoài. |

**Số liệu chỉ là tình huống minh họa**. Không dùng nó làm benchmark thực tế hoặc kết luận mapper luôn chậm gấp đôi.

### 21.2. Quy trình điều tra

1. **Lấy CQL thật của hai đường**, so projection, partition key, clustering range, `LIMIT`, CL và page size.
2. Kiểm tra driver request count, retries/speculative attempts và time to first/full page.
3. Xem response bytes, rows, allocation/GC, JSON serialization CPU và payload size.
4. So server latency, tombstones, SSTable/compaction pressure; nếu server cũng tăng nhiều, **đừng chỉ tối ưu Java object**.
5. Thử `@Query` chỉ chọn trường cần thiết hoặc bảng summary/DTO; vẫn giữ mapper cho lookup và CRUD phù hợp.
6. Chạy **ba thí nghiệm A/B/C ở mục 15**, canary có kiểm soát, đánh giá p99 và correctness.
7. Đặt rollback feature flag/previous artifact, quan sát traffic peak thay vì chỉ chạy một `main()` với ba hàng.

**Giải pháp có thể là giữ DAO nhưng sửa projection**, không cần xóa toàn bộ abstraction layer. Trong một codebase lớn, mất maintainability và nhân bản CQL có chi phí lâu dài; cân bằng dựa trên đo lường.

### 21.3. Khi nào cân nhắc bỏ mapper ở đúng một hot path?

Ví dụ một luồng đọc vài triệu rows nhỏ/giây chỉ để tính một thống kê streaming. Nếu:

- `@Query` đã chọn đúng cột, server latency ổn và network không phải bottleneck;
- Profiling chứng minh việc dựng bean và codec của mapper chiếm CPU/GC đáng kể;
- Core API có thể xử lý `Row` theo streaming, tránh nhiều entity allocation;
- Đã có integration tests và benchmark cho kết quả tương đương;

thì dùng **Core API có chủ đích ở riêng hot path ấy** là hợp lý. **Không phải cứ DAO là chậm**; vấn đề là có bằng chứng một lớp mapping không mang lại giá trị tương xứng cho workload cụ thể.

## 22. Ma trận quyết định: mapper, Core API hay bảng projection?

| Tình huống | Phương án thường đáng cân nhắc | Lý do |
| --- | --- | --- |
| CRUD/lookup theo full primary key, team nhiều người | **Mapper/DAO** | Mã rõ, giảm boilerplate, dễ test mapping/schema. |
| Một vài query custom có partition/range rõ | **`@Query` trong DAO** | Giữ API domain-friendly mà kiểm soát CQL. |
| Streaming/aggregation hàng triệu rows rất nhỏ | **Core `Row` hoặc DTO nhẹ** | Giảm allocations khi profiler xác nhận cần thiết. |
| Endpoint chỉ cần 3/20 cột | **Narrow projection** bằng `@Query`, Core hoặc bảng summary | Tối ưu bytes trước khi tranh luận mapper overhead. |
| Truy vấn qua hàng trăm bucket | **Thay data model/rollup và bounded fan-out** | Mapper/Core đều không sửa chi phí quét nhiều partition. |
| Tìm theo cột không nằm trong partition key | **Bảng theo truy vấn/index được đánh giá** | `ALLOW FILTERING` không tạo đường truy cập rẻ. |
| Domain cần join, graph traversal, ACID nhiều partition | **Đánh giá kiến trúc lưu trữ và hệ khác** | Cassandra mapper không biến Cassandra thành RDBMS. |
| Tối ưu hóa khi chưa có đo lường | **Giữ phương án đơn giản và đo trước** | Tránh đổi code lớn nhưng không giải quyết bottleneck. |

### 22.1. Công thức chọn abstraction ở cấp nhóm phát triển

Có thể tự hỏi theo thứ tự:

1. **Truy vấn Cassandra có đúng partition/range, bounded rows và ít cột chưa?**
2. **Số CQL round-trips/API có hợp lý chưa?**
3. **Client có dùng session/prepared statement và paging đúng chưa?**
4. **Server p99/compaction/tombstone có phải bottleneck không?**
5. **Profiler có chứng minh mapping/GC là phần đáng kể không?**
6. **Độ phức tạp Core API sẽ tạo thêm bao nhiêu chi phí bảo trì/test?**

Chỉ khi câu 1–4 được giải quyết và câu 5 có bằng chứng, việc giảm abstraction layer mới nên trở thành ưu tiên.

## 23. Runbook khi DAO phát sinh lỗi hoặc p99 tăng

~~~mermaid
flowchart TD
    A["DAO error / p99 regression"] --> B{"Build mapping hay runtime?"}
    B -->|Build| C["Processor/dependencies/generated sources"]
    B -->|Runtime| D["Ghi query name, CQL shape, error class, DC/CL"]
    D --> E{"Auth/Unauthorized/Schema/Codec error?"}
    E -->|Có| F["Kiểm tra identity, schema, CQL types, mapper annotations"]
    E -->|Không| G["So latency app/driver/coordinator/replica"]
    G --> H{"Server scan/disk/replica chậm?"}
    H -->|Có| I["Sửa query/model dữ liệu, giảm fan-out, compaction/repair"]
    H -->|Không| J["Đo projection/bytes, mapping CPU, allocation và GC"]
    J --> K["So Mapper full / Core full / narrow DTO"]
    C --> L["Integration tests + load test + canary"]
    F --> L
    I --> L
    K --> L
    L --> M{"SLO + correctness + resource đạt?"}
    M -->|Không| N["Rollback thay đổi, giữ incident mở"]
    M -->|Có| O["Ghi bằng chứng, áp dụng có kiểm soát"]
~~~

### 23.1. Checklist chẩn đoán theo mức ưu tiên

1. **Xác nhận môi trường:** version Driver/Core/mapper processor, Cassandra, schema, JDK, keyspace, local DC và RF/CL.
2. **Phân loại lỗi:** mapping/build, codec, auth, unavailable, read/write timeout, overload, tombstones, application exception.
3. **Lấy statement thực:** `SELECT` có `*` không, `WHERE` đủ partition key không, `LIMIT`, clustering range, số partition/bucket và page size?
4. **Đo client:** request rate, in-flight, driver throttling/queue, retries, bytes/rows, time to first/all pages, allocation và GC.
5. **Đo server:** `tpstats`, `compactionstats`, tombstone/partition stats, disk latency, replica health và DC network.
6. **Test correctness:** mapping trường null, UUID/timestamp/UTC, TTL, delete, data shape, boundary.
7. **Thử sửa ít nhất:** giảm cột/bytes, tối ưu CQL, bounded fan-out hoặc dùng projection; chỉ viết Core custom khi profiler chỉ rõ mapping bottleneck.
8. **Thử staging + canary:** giữ traffic/data shape tương đương, đo p95/p99/throughput và error trong thời gian đủ dài.
9. **Dự phòng rollback:** artifact/version cũ, feature flag, chuẩn hóa dữ liệu và kế hoạch xử lý mutations nếu chuyển bảng.
10. **Ghi hậu kiểm:** độ trễ, memory/GC, server resource và correctness đều đạt; không chỉ `HTTP 200`.

## 24. Bài tập tự kiểm tra có đáp án

**Bài 1.** Mapper 4.x có nhất thiết dùng Java reflection cho từng trường của từng row giống một ORM động không?

**Đáp án:** **Không.** Mapper dựa trên annotation processing sinh mã ở compile time. Tuy vậy, mã sinh vẫn thực hiện decode, tạo object, gán field và có thể gây allocation/GC.

**Bài 2.** Entity có `@PartitionKey(0) deviceId` và `@PartitionKey(1) eventDay`. Nếu gọi `findWindow` thiếu `eventDay`, mapper có tự tìm mọi ngày không?

**Đáp án:** **Không.** Partition key kép cần đủ thành phần để định tuyến chính xác; việc tìm nhiều ngày phải thiết kế traversal qua bucket hoặc bảng/projection khác.

**Bài 3.** Nhóm chuyển Core query chọn ba cột sang mapper full entity chọn sáu cột và thấy latency tăng 80%. Có thể kết luận 80% là do object mapping?

**Đáp án:** **Không.** Thí nghiệm thay cả projection/bytes và mapping. Phải so **Core full và mapper full cùng CQL** rồi đo allocation; sau đó tách riêng tác động của narrow DTO.

**Bài 4.** `dao.findById(...)` trả `null` sau read thành công khác gì `ReadTimeout`?

**Đáp án:** `null` cho biết không có row sống khớp lookup theo kết quả đọc; `ReadTimeout` là không hoàn tất theo deadline, **không thể đổi thành kết quả rỗng/404**.

**Bài 5.** Cassandra có `PRIMARY KEY ((device_id,event_day),event_time,event_id)`. API hỏi khoảng 23:45 ngày 20/11 đến 00:15 ngày 21/11 UTC. Một `findWindow` của ngày 20/11 có đủ không?

**Đáp án:** **Không.** Event ngày 21/11 nằm partition khác. Đọc hai bucket với khoảng nửa kín phù hợp, sau đó merge/sort và áp global limit nếu cần.

**Bài 6.** Một service có 25 pod, mỗi pod được phép tối đa 40 CQL statements in-flight. Trần đồng thời theo mô hình đơn giản là bao nhiêu?

**Đáp án:** `25 × 40 = 1.000` statements in-flight trên fleet, chưa tính các service khác/retry/speculative requests. Đây không phải số kết nối TCP hay throughput requests/s.

**Bài 7.** Object mapper ánh xạ một `payload` 100 KiB; UI chỉ cần `event_time` và `event_type`. Giải pháp đầu tiên nên xem xét?

**Đáp án:** **Giảm column projection**, trả DTO nhỏ hoặc bảng summary thích hợp, vì tránh truyền/decode byte thừa thường giá trị hơn chỉ đổi cách dựng Java object.

**Bài 8.** Entity được đọc với query chỉ chọn hai cột, các thuộc tính khác là `null`. Có nên gọi `@Insert`/ `@Update` với object này để sửa đúng hai cột?

**Đáp án:** **Không nên giả định an toàn.** Null có thể mang semantics xóa/tombstone tùy generated statement/null-saving strategy. Dùng update đúng cột hoặc kiểm tra cấu hình UNSET và integration tests.

**Bài 9.** Mapper `@Query` có `WHERE event_type=:type ALLOW FILTERING` chạy chậm. Tăng pool và đổi sang Core API có tự sửa đường đọc không?

**Đáp án:** **Không.** Vẫn thiếu partition key/index phù hợp; có thể scan nhiều partition. Cần mô hình bảng phục vụ query hoặc đường analytics có giới hạn.

**Bài 10.** Một write bằng DAO trả `WriteTimeout`. Có thể retry ngay với `eventId` mới để “chắc chắn lần sau ghi thành công” không?

**Đáp án:** **Không.** Một số replica có thể đã ghi. Retry bằng ID mới có thể tạo duplicate; cần stable key, idempotency và reconciliation theo hợp đồng nghiệp vụ.

**Bài 11.** Khi so mapper và Core, tại sao phải warm-up cả hai, cùng page size và tiêu thụ hết cùng số page?

**Đáp án:** Nếu một bên chịu chi phí prepare/cold-start hoặc chỉ đo page đầu, kết quả không còn so **cùng công việc**; khác biệt latency không thể gán riêng cho mapping.

**Bài 12.** Một DAO được chú thích `@Select` và entity có đầy đủ primary key. Điều gì vẫn có thể làm lookup chậm?

**Đáp án:** Node/replica down hoặc GC, SSTable/disk, tombstone, network, CL, concurrency và overloaded queues. Partition lookup tốt **không miễn nhiễm tài nguyên**.

**Bài 13.** Java code dùng `@Dao`, `@Mapper`, nhưng build CI báo không tìm thấy `TelemetryMapperBuilder`. Hãy nêu một nguyên nhân.

**Đáp án:** Annotation processor chưa được cấu hình/chạy trong CI, dependency processor/runtime không khớp version hoặc generated sources không có trong build. Kiểm tra compile configuration trước khi điều tra Cassandra server.

**Bài 14.** Service được cấp `SELECT` trên cả bảng nhưng tenant A truyền `deviceId` của tenant B vào DAO. Mapper có tự chặn không?

**Đáp án:** **Không.** CQL RBAC thường kiểm tra quyền resource, không tự biết tenant ownership theo `deviceId`; service phải kiểm soát authorization nghiệp vụ trước khi bind.

**Bài 15.** Một mapper full entity p99 35 ms, Core full entity p99 33 ms, Core narrow DTO p99 15 ms trong cùng cluster. Có căn cứ kết luận mapper là bottleneck chính chưa?

**Đáp án:** **Chưa.** Mapper và Core full gần nhau, narrow DTO nhanh hơn nhiều; cần điều tra projection/bytes và server/network trước. Dữ liệu chỉ có ý nghĩa khi benchmark đủ mẫu, cùng CL/page, workload, warm-up và kết quả logic.

## 25. Checklist triển khai DAO cho production

~~~text
SCHEMA / QUERY
[ ] Entity/DAO khớp đúng partition key và clustering key trong CQL.
[ ] Mỗi method có query contract rõ: key, time window, LIMIT, ordering.
[ ] Không viết getAll()/ALLOW FILTERING không giới hạn cho hot path.
[ ] Cột được SELECT vừa đủ nhu cầu API, không mặc định SELECT *.
[ ] Với multi-bucket, service giới hạn fan-out, merge và pagination đúng.

MAPPER / JAVA
[ ] Core, mapper runtime, processor dùng bộ version tương thích.
[ ] Annotation processing chạy trong CI; generated sources được xác minh.
[ ] Keyspace, @CqlName và Java/CQL types có integration tests.
[ ] CqlSession dùng chung, prepared statements được reuse/warm phù hợp.
[ ] Null/UNSET/TTL/updates không xóa hoặc gia hạn dữ liệu ngoài ý muốn.
[ ] Codec/UDT/collections lớn được benchmark.
[ ] Mapper hot path được so với Core ở cùng CQL trước khi tối ưu.

RESOURCE / FAILURE
[ ] Có giới hạn rows, byte, page size, concurrency và API deadline.
[ ] Async code không gửi futures vô hạn hoặc block I/O callbacks.
[ ] Retry/idempotency rõ cho read, write, counter và LWT.
[ ] Timeout/unavailable/authorization được xử lý khác "not found".
[ ] Đo p50/p95/p99, full result consume, allocations/GC, driver queue.
[ ] Đo replica I/O, SSTable/tombstone, compaction, RF/CL và topology.

SECURITY / RELEASE
[ ] Service identity least-privilege; không dùng superuser hoặc shared secret.
[ ] TLS xác thực peer, secrets không đi vào logs/metrics.
[ ] Tenant authorization ở service, không phó mặc cho @Dao.
[ ] Staging tích hợp schema/version/TTL/delete/large payload tests.
[ ] Có canary, performance/correctness gates và rollback.
~~~

~~~mermaid
flowchart TD
    A["Cần đọc/ghi Cassandra từ Java"] --> B["Thiết kế CQL theo partition + clustering"]
    B --> C["Chọn API: mapper DAO hay Core"]
    C --> D{"Query thông thường, entity rõ, cần bảo trì dễ?"}
    D -->|Có| E["@Entity + @Dao + @Mapper codegen"]
    D -->|Không / streaming hot path| F["Core PreparedStatement + Row/DTO nhẹ"]
    E --> G["Giới hạn projection, paging, concurrency, deadline"]
    F --> G
    G --> H["Test null, TTL, errors, RF/CL, schema và security"]
    H --> I["Benchmark CQL giống nhau + allocation/GC + server latency"]
    I --> J{"SLO và data correctness đạt?"}
    J -->|Không| K["Sửa data model/bytes/overhead, thử lại"]
    K --> C
    J -->|Có| L["Canary và quan sát trước khi rollout toàn bộ"]
~~~

**Kết luận:** object mapper và DAO của Apache Cassandra Java Driver 4.x giúp **định nghĩa đường truy cập dữ liệu rõ ràng, giảm boilerplate và tạo mã mapping ngay lúc compile**. Nhưng chúng không phải ORM quan hệ có join/transaction/dirty checking, và **không tự tối ưu CQL hoặc tăng capacity Cassandra**. Chi phí thật cần nhìn đủ **partition/range, số statement, projection bytes, page fetch, network/replica latency, codec, object allocation và GC**. Hãy dùng mapper cho những truy vấn rõ ràng, bảo trì lâu dài; dùng Core API hoặc DTO/projection nhẹ ở hot path **chỉ khi phép đo công bằng chứng minh lợi ích**. Trước khi kết luận “mapper chậm”, luôn kiểm tra **CQL được gửi đi, khối lượng dữ liệu, RF/CL, timeout, backpressure và tính đúng của kết quả**.
