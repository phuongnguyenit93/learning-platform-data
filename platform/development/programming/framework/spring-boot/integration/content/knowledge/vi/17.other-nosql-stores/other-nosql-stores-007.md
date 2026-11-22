# CassandraTemplate, repository và lựa chọn API phù hợp

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, Apache Cassandra là một lựa chọn lưu trữ NoSQL khi hệ thống cần phục vụ lưu lượng ghi/đọc lớn trên nhiều nút và dữ liệu được truy cập theo những khóa, mẫu truy vấn tương đối xác định. Spring Boot cung cấp tích hợp với Cassandra qua **Spring Data Cassandra**, gồm các lớp truy cập mức cao như **CassandraTemplate**, **CassandraRepository** và các API mức thấp như **CqlTemplate**, **CqlSession**.

Chủ đề này nằm trong chương **Các kho NoSQL khác**. Nó bổ sung cho những luồng tích hợp qua HTTP client, cơ sở dữ liệu, cache, message broker và adapter Spring Integration. Việc lựa chọn API Cassandra phải xét đồng thời cấu hình kết nối, hợp đồng dữ liệu, giao dịch/nhất quán, lỗi, xử lý trùng lặp, kiểm thử và khả năng quan sát. Chọn đúng API Java chỉ là một phần; **mô hình partition key và mẫu truy vấn mới quyết định Cassandra có phù hợp với nghiệp vụ hay không**.

Sau bài học, bạn sẽ có thể:

1. Giải thích vai trò của **CqlSession**, **CqlTemplate**, **CassandraTemplate**, **CassandraRepository** và biến thể reactive.
2. Cấu hình Spring Boot kết nối Cassandra, ánh xạ entity và dùng repository với một bảng có partition key rõ ràng.
3. Chuyển sang CassandraTemplate khi cần Query/Criteria, tùy chọn ghi hoặc quyền kiểm soát cao hơn CRUD thông thường.
4. Dùng CqlTemplate hoặc driver cho CQL đặc thù, truy vấn có bind parameter và kiểm tra kết quả ghi có điều kiện.
5. Hiểu ảnh hưởng của consistency level, TTL, LWT, pagination, timeout và retry đối với tính đúng đắn của tích hợp.
6. Kiểm thử chọn API và mô hình dữ liệu trên Cassandra thật trong môi trường test.

## 2. Các lớp API và trách nhiệm

Spring Data Cassandra có hai trục lựa chọn: **mức trừu tượng** và **mô hình thực thi**.

| API | Mức trừu tượng | Điểm mạnh | Khi nào phù hợp |
| --- | --- | --- | --- |
| **CassandraRepository<T, ID>** | Repository trên entity | CRUD phổ biến, tìm theo khóa, query method, code service gọn | Aggregate ổn định, ít truy vấn phức tạp |
| **CassandraTemplate / CassandraOperations** | Entity mapping + thao tác có kiểm soát | Query/Criteria, select, insert, update, delete; tùy chọn mỗi truy vấn | Repository không đủ linh hoạt, cần tùy chọn ghi/đọc riêng |
| **CqlTemplate / CqlOperations** | CQL, callback và RowMapper | Chủ động viết CQL, sử dụng bind parameter; ít phụ thuộc entity mapping | CQL đặc thù, counter, câu lệnh chưa được entity API thể hiện thuận tiện |
| **CqlSession** (Java driver) | Driver trực tiếp | Prepared/BoundStatement, paging state, execution profile, driver-specific options | Cần khả năng driver hoặc chính sách truy vấn đặc biệt |
| **ReactiveCassandraRepository / ReactiveCassandraTemplate** | Repository/template reactive | Mono, Flux, composition, khả năng không chặn thread gọi | Hệ thống reactive có nhiều request I/O đồng thời |
| **ReactiveCqlTemplate** | CQL reactive | CQL trực tiếp với Mono/Flux | CQL đặc thù trong pipeline reactive |

Sơ đồ:

~~~mermaid
flowchart TD
    A["Application service"] --> B{"Nhu cầu truy cập"}
    B -->|"CRUD theo entity"| C["CassandraRepository"]
    B -->|"Entity + Query/Criteria"| D["CassandraTemplate"]
    B -->|"CQL tùy chỉnh"| E["CqlTemplate"]
    B -->|"Driver-specific"| F["CqlSession"]
    C --> G["Spring Data mapping và chuyển đổi lỗi"]
    D --> G
    E --> H["CQL execution và chuyển đổi lỗi"]
    G --> I["Cassandra Java Driver"]
    H --> I
    F --> I
    I --> J["Cassandra cluster"]
~~~

**CassandraTemplate** triển khai interface **CassandraOperations**; **ReactiveCassandraTemplate** triển khai **ReactiveCassandraOperations**. Trong code nghiệp vụ, có thể inject các interface Operations để giảm phụ thuộc vào implementation cụ thể. Template được Spring quản lý có thể tái sử dụng giữa các request.

**Lưu ý:** repository cũng sử dụng Spring Data template/mapping ở bên dưới. “Repository hay template” là quyết định về cách tổ chức truy vấn, không phải hai hệ thống lưu trữ riêng biệt. Không nên đổi API chỉ để xử lý vấn đề mà nguyên nhân là bảng được thiết kế sai partition key.

## 3. Bắt đầu với Spring Boot

### 3.1. Dependency

Với Maven và phiên bản dependency do Spring Boot parent/BOM quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu toàn bộ ứng dụng dùng reactive, cân nhắc starter **spring-boot-starter-data-cassandra-reactive** và các API reactive đi kèm. Chọn dependency phù hợp thế hệ Spring Boot và kiểm tra module test/slice test mà phiên bản ấy cung cấp. Không cần tự thêm driver với version không tương thích khi starter đã quản lý phần phụ thuộc phù hợp.

### 3.2. Cấu hình kết nối

Ví dụ cấu hình local trong **application.yml**:

~~~yaml
spring:
  cassandra:
    contact-points: localhost:9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
    request:
      timeout: 3s
      consistency: LOCAL_QUORUM
    schema-action: none
~~~

Đây là cấu hình minh họa, **không phải các giá trị mặc định nên dùng cho mọi cluster**. Cần thay **datacenter1** bằng tên datacenter chính xác từ cluster, chọn consistency theo số bản sao, topology và yêu cầu nghiệp vụ. Nếu production cần xác thực/TLS, cấu hình credential và SSL/SSL bundle tương ứng; đưa bí mật vào secret manager hoặc biến môi trường, không commit mật khẩu vào repository.

Các điểm cần phân biệt:

- **spring.cassandra.contact-points** là những node khởi tạo khám phá cluster; driver không bị giới hạn vĩnh viễn vào các node này.
- **local-datacenter** ảnh hưởng đến chính sách định tuyến; điền sai có thể khiến client không chọn được node thích hợp.
- **keyspace-name** tương tự namespace quản lý bảng; keyspace phải tồn tại trước khi ứng dụng truy vấn.
- **request.timeout** giới hạn thời gian driver chờ một request hoàn thành, không bảo đảm toàn bộ workflow tích hợp hoàn thành trong 3 giây.
- **schema-action: none** tránh để ứng dụng tự thay đổi schema khi khởi động; nên quản lý schema qua quy trình migration/phát hành có kiểm soát.

Khi điều kiện auto-configuration thỏa mãn, Spring Boot tạo các bean hỗ trợ như **CqlSession**, **CqlTemplate**, **CassandraTemplate** và hạ tầng repository tương ứng. Nhờ đó service/repository có thể inject những bean này; thông thường không cần tạo một session mới mỗi lần request. Tùy chọn auto-configuration thay đổi theo version, custom bean và classpath: khi gặp lỗi bean hãy xem **Condition Evaluation Report** thay vì giả định mọi bean luôn được tạo.

## 4. Mô hình dữ liệu phải bắt đầu từ truy vấn

Cassandra không vận hành giống database quan hệ. Nó tổ chức dữ liệu quanh **partition key** để quyết định vị trí lưu bản ghi và **clustering columns** để sắp xếp dữ liệu bên trong partition. Trước khi viết Repository, phải biết ứng dụng sẽ truy vấn theo khóa nào, mỗi partition lớn đến đâu và thứ tự đọc cần thiết.

### 4.1. Ví dụ đơn giản: bản chụp tồn kho theo SKU

Giả sử một hệ thống tích hợp duy trì một **snapshot tham khảo** của lượng hàng do hệ thống khác cung cấp. Không dùng snapshot này để thực hiện quyết định tài chính hay trừ kho đòi hỏi transaction mạnh nếu chưa có kiến trúc nhất quán riêng.

~~~sql
CREATE TABLE shop_integration.inventory_snapshot (
    sku text PRIMARY KEY,
    available_qty int,
    source_version bigint,
    updated_at timestamp
);
~~~

Ở đây **sku** là partition key. Các truy vấn **WHERE sku = ?** rất tự nhiên; nhưng câu hỏi “đếm tất cả SKU có available_qty > 0” không còn là truy vấn theo partition key. Để phục vụ cách đọc đó với tải lớn, có thể cần bảng projection riêng, index phù hợp hoặc một công cụ tìm kiếm/analytics khác.

Entity Java (rút gọn import):

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("inventory_snapshot")
public class InventorySnapshot {
    @PrimaryKey("sku")
    private String sku;

    @Column("available_qty")
    private int availableQty;

    @Column("source_version")
    private long sourceVersion;

    @Column("updated_at")
    private Instant updatedAt;

    protected InventorySnapshot() {} // phục vụ mapping

    public InventorySnapshot(
            String sku, int availableQty, long sourceVersion, Instant updatedAt) {
        this.sku = sku;
        this.availableQty = availableQty;
        this.sourceVersion = sourceVersion;
        this.updatedAt = updatedAt;
    }

    public String getSku() { return sku; }
    public int getAvailableQty() { return availableQty; }
    public long getSourceVersion() { return sourceVersion; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

Spring Data sử dụng mapping metadata từ **@Table**, **@PrimaryKey**, **@Column** và converter để ánh xạ đối tượng sang Cassandra row. Kiểu timestamp/Instant cần được xác minh với driver và version Java; ví dụ này không tạo field ID tự tăng, vì Cassandra không cấp sequence giống RDBMS.

### 4.2. Ví dụ khóa tổng hợp: sự kiện theo tenant và ngày

Nếu hệ thống cần đọc “50 sự kiện gần nhất của tenant A trong ngày D”, bảng thích hợp hơn có thể là:

~~~sql
CREATE TABLE shop_integration.events_by_tenant_day (
    tenant_id text,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**(tenant_id, event_day)** là composite partition key; **(occurred_at, event_id)** là clustering key. Bucket theo ngày giúp tránh dồn dữ liệu của cả một tenant vào một partition vô hạn, nhưng cần ước lượng kích thước partition thực tế; tenant có lưu lượng quá lớn có thể cần bucket theo giờ hoặc sharding bổ sung.

Spring Data Cassandra có thể ánh xạ khóa dạng này bằng **@PrimaryKeyClass** và **@PrimaryKeyColumn**:

~~~java
@PrimaryKeyClass
public class TenantEventKey implements Serializable {
    @PrimaryKeyColumn(
            name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(
            name = "event_day", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
            name = "occurred_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
            name = "event_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;

    // Constructor, getters/setters, equals() và hashCode()
    // phải được hiện thực nhất quán với identity của key.
}

@Table("events_by_tenant_day")
public class TenantEvent {
    @PrimaryKey
    private TenantEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    // Constructor và getters/setters theo converter đang dùng.
}
~~~

Các import cho **PrimaryKeyClass**, **PrimaryKeyColumn**, **PrimaryKeyType**, **Ordering**, **Serializable**, **LocalDate**, **Instant**, **UUID** được lược bỏ. Đoạn mã mô tả mapping; để dùng trực tiếp phải hiện thực đầy đủ constructor/accessor và **equals/hashCode** cho key. Mỗi truy vấn chọn partition phải cung cấp **đủ thành phần partition key**. Điều kiện range trên clustering column cũng phải theo các quy tắc CQL; không thể tự do filter mọi cột như SQL quan hệ.

## 5. Khi nào Repository là lựa chọn tốt nhất?

Với bảng snapshot theo khóa SKU, dùng Spring Data repository rất gọn:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface InventorySnapshotRepository
        extends CassandraRepository<InventorySnapshot, String> {
    // Có sẵn findById, save, deleteById, existsById, ...
}
~~~

Service:

~~~java
@Service
public class InventorySnapshotQueryService {
    private final InventorySnapshotRepository snapshots;

    public InventorySnapshotQueryService(
            InventorySnapshotRepository snapshots) {
        this.snapshots = snapshots;
    }

    public Optional<InventorySnapshot> findBySku(String sku) {
        return snapshots.findById(sku);
    }
}
~~~

**findById** rõ ý định, đúng partition key, không cần viết CQL. Repository hỗ trợ khai báo phương thức truy vấn bổ sung, bằng tên phương thức hoặc **@Query** khi truy vấn đó được Cassandra hỗ trợ.

Ví dụ một query method với bảng **events_by_tenant_day**:

~~~java
public interface TenantEventRepository
        extends CassandraRepository<TenantEvent, TenantEventKey> {

    @Query("""
        SELECT * FROM events_by_tenant_day
        WHERE tenant_id = ?0 AND event_day = ?1
        """)
    List<TenantEvent> findEventsForDay(
            String tenantId, LocalDate eventDay);
}
~~~

Truy vấn này hợp lệ về **partition key**, nhưng có thể trả số lượng bản ghi lớn trong ngày. Trong hệ thống thực cần thêm giới hạn, paging state hoặc phân trang theo clustering key. Repository dễ đọc chỉ khi truy vấn phản ánh đúng khả năng của CQL.

**Không hiểu nhầm save() là “chỉ insert khi chưa có”.** Ghi theo khóa trong Cassandra thường mang ngữ nghĩa **upsert**; lưu cùng khóa có thể ghi đè các giá trị cột thay vì phát lỗi duplicate key như insert trên RDBMS. Nếu cần bảo đảm “chỉ tiếp nhận request một lần”, dùng thao tác ghi có điều kiện **IF NOT EXISTS** và kiểm tra kết quả; cân nhắc chi phí LWT.

Repository thích hợp nhất khi domain ổn định, thao tác phần lớn là CRUD theo primary key và không cần điều khiển statement phức tạp cho từng lần gọi. Nếu service phải thêm nhiều if/else chỉ để điều khiển consistency, TTL, conditional write hoặc mapping query đặc thù, hãy chuyển phần đó sang custom repository với Template/CQL.

## 6. CassandraTemplate: điều khiển truy vấn trên entity

**CassandraTemplate** dành cho ứng dụng vẫn muốn mapping POJO nhưng cần chủ động hơn phương thức CRUD mặc định. Interface tương ứng là **CassandraOperations**:

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

@Repository
public class SnapshotTemplateDao {
    private final CassandraOperations cassandra;

    public SnapshotTemplateDao(CassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    public Optional<InventorySnapshot> find(String sku) {
        InventorySnapshot value = cassandra.selectOne(
                query(where("sku").is(sku)),
                InventorySnapshot.class
        );
        return Optional.ofNullable(value);
    }

    public InventorySnapshot insertSnapshot(InventorySnapshot value) {
        return cassandra.insert(value);
    }
}
~~~

**query(where("sku").is(sku))** được ánh xạ sang truy vấn chọn partition theo khóa. **selectOne** có thể trả null khi không tìm thấy bản ghi. **insert** giúp thực thi thao tác ghi entity nhưng không tự mang bảo đảm chống trùng; cần hiểu tính chất upsert và các tùy chọn cụ thể.

### 6.1. TTL và ghi có điều kiện

Đôi khi snapshot chỉ hữu ích trong một khoảng thời gian và cần tránh nhận lại cùng một key. Spring Data hỗ trợ **InsertOptions**:

~~~java
public boolean insertIfAbsent(InventorySnapshot value) {
    InsertOptions options = InsertOptions.builder()
            .ttl(Duration.ofHours(6))
            .withIfNotExists()
            .build();

    WriteResult result = cassandra.insert(value, options);
    return result.wasApplied();
}
~~~

Trong đoạn mã:

- **ttl(6 giờ)** yêu cầu bản ghi được ghi với TTL; dữ liệu có thể hết hạn theo cơ chế TTL của Cassandra. Đối với cập nhật từng cột hoặc xóa TTL, phải hiểu ngữ nghĩa của từng lệnh cụ thể.
- **withIfNotExists()** phát sinh conditional insert có **lightweight transaction (LWT)**.
- **wasApplied()** cho biết điều kiện đã được chấp nhận hay chưa.

**Quan trọng:** LWT đắt hơn write thường và không nên bật mặc định cho mọi snapshot. Nếu mục tiêu là giữ bản cập nhật mới nhất theo **source_version**, một thao tác **IF NOT EXISTS** không đủ để ngăn sự kiện cũ ghi đè sự kiện mới. Cần thiết kế cập nhật có điều kiện theo version hoặc một cơ chế xác định thứ tự riêng, rồi kiểm thử với nhiều request đến đảo thứ tự.

### 6.2. Khi cần query linh hoạt hơn

Template hỗ trợ **Query**, **Criteria**, update/delete operations và tùy chọn trên từng statement. Tuy nhiên, **Query/Criteria không biến Cassandra thành SQL cho phép lọc mọi thuộc tính**. Truy vấn vào non-key column có thể cần index hoặc thiết kế bảng khác; việc thêm **ALLOW FILTERING** nhằm né lỗi CQL có thể gây đọc rất nhiều partition, latency không ổn định và quá tải cluster.

Nếu phải tìm “tất cả snapshot có source_version nhỏ hơn X”, nên cân nhắc bảng projection theo access pattern hoặc một quy trình quét nền được phân đoạn, thay vì mặc định thêm điều kiện non-key vào Query.

## 7. CqlTemplate và CqlSession: khi cần CQL trực tiếp

**CqlTemplate** bỏ phần object mapping ở mức cao để service tự viết CQL và ánh xạ kết quả. Nó quản lý luồng thực thi cơ bản, chuyển lỗi truy cập dữ liệu và hỗ trợ parameter binding:

~~~java
@Repository
public class SnapshotCqlDao {
    private final CqlOperations cql;

    public SnapshotCqlDao(CqlOperations cql) {
        this.cql = cql;
    }

    public Optional<Integer> quantity(String sku) {
        List<Integer> quantities = cql.query(
                "SELECT available_qty FROM inventory_snapshot WHERE sku = ?",
                (row, rowNum) -> row.getInt("available_qty"),
                sku
        );
        return quantities.stream().findFirst();
    }

    public void upsertQuantity(String sku, int quantity) {
        cql.execute(
                "UPDATE inventory_snapshot SET available_qty = ? WHERE sku = ?",
                quantity, sku
        );
    }
}
~~~

Các import **CqlOperations**, **List** và **@Repository** được lược bỏ. Sử dụng **query** trả danh sách để thể hiện rõ trường hợp không có dòng; **queryForObject** có thể ném **IncorrectResultSizeDataAccessException** nếu số dòng không đúng một. Với câu lệnh có tham số, **CqlTemplate** sử dụng prepared statement; việc bind giúp tránh ghép trực tiếp chuỗi nhận từ người dùng vào CQL.

Chỉ dùng **CqlSession** trực tiếp nếu cần kiểm soát API driver rõ ràng: **PreparedStatement**, **BoundStatement**, **ConsistencyLevel**, paging state, execution profile, tracing cụ thể hoặc thông tin **ResultSet**. Ví dụ conditional insert và xác nhận kết quả:

~~~java
@Repository
public class ProcessedEventDao {
    private final CqlSession session;
    private final PreparedStatement markProcessed;

    public ProcessedEventDao(CqlSession session) {
        this.session = session;
        this.markProcessed = session.prepare("""
            INSERT INTO processed_event (consumer_name, event_id, processed_at)
            VALUES (?, ?, ?) IF NOT EXISTS
            """);
    }

    public boolean markFirstTime(
            String consumerName, UUID eventId, Instant processedAt) {
        BoundStatement statement = markProcessed.bind(
                consumerName, eventId, processedAt);
        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}
~~~

Giả định bảng **processed_event** có primary key chứa **consumer_name** và **event_id** phù hợp, và driver hỗ trợ mapping kiểu Instant theo cấu hình đang dùng. Ví dụ này tập trung vào cú pháp API; trong ứng dụng thật nên tạo bảng qua migration và chọn partition key tránh dồn quá nhiều khóa vào một partition. **CqlSession** do Spring quản lý được dùng chung; không **close()** session sau mỗi request.

**Đừng coi markFirstTime() là bằng chứng một tác vụ bên ngoài đã hoàn tất.** Nếu đánh dấu event trước khi gọi HTTP hoặc publish message rồi tiến trình chết, trạng thái “đã xử lý” có thể tồn tại dù side effect chưa diễn ra. Cần quyết định trạng thái xử lý, checkpoint, outbox hoặc cơ chế xác nhận theo đúng ranh giới nhất quán của toàn workflow.

## 8. Chọn imperative hay reactive

Cassandra có API đồng bộ, bất đồng bộ và reactive. Đừng chỉ nhìn chữ “Cassandra” trong tên lớp:

| Nhu cầu | Lựa chọn thường dùng | Giá trị trả về |
| --- | --- | --- |
| Spring MVC/service đồng bộ | CassandraRepository hoặc CassandraTemplate | Optional, List, entity |
| Truy vấn CQL thuần đồng bộ | CqlTemplate, đôi khi CqlSession | Scalar, List, ResultSet |
| WebFlux hoặc pipeline reactive | ReactiveCassandraRepository/ReactiveCassandraTemplate | Mono, Flux |
| CQL riêng trong reactive flow | ReactiveCqlTemplate | Mono, Flux |
| Cần CompletableFuture | AsyncCassandraTemplate hoặc driver async | CompletableFuture |

Ví dụ repository reactive:

~~~java
public interface ReactiveInventorySnapshotRepository
        extends ReactiveCassandraRepository<InventorySnapshot, String> {
}

@Service
public class ReactiveInventoryLookup {
    private final ReactiveInventorySnapshotRepository snapshots;

    public ReactiveInventoryLookup(
            ReactiveInventorySnapshotRepository snapshots) {
        this.snapshots = snapshots;
    }

    public Mono<InventorySnapshot> find(String sku) {
        return snapshots.findById(sku);
    }
}
~~~

Ví dụ Template reactive:

~~~java
@Repository
public class ReactiveSnapshotDao {
    private final ReactiveCassandraOperations cassandra;

    public ReactiveSnapshotDao(ReactiveCassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    public Mono<InventorySnapshot> find(String sku) {
        return cassandra.selectOneById(sku, InventorySnapshot.class);
    }
}
~~~

Trong reactive flow, **Mono.empty()** có thể biểu diễn “không tìm thấy”. Query thường chỉ bắt đầu thực thi khi có subscriber; **không tự gọi block()** trên event-loop của WebFlux. Reactor **timeout** có thể giới hạn thời gian chờ downstream, nhưng cancellation phía client không chứng minh thao tác ghi đã bị hủy ở database.

API reactive của Spring Data Cassandra tận dụng khả năng bất đồng bộ của Java driver; đó không phải JDBC hay R2DBC, và semantics CQL/consistency vẫn là Cassandra. Không tự cho rằng dùng Flux có nghĩa là toàn bộ bộ dữ liệu sẽ được đọc không giới hạn mà không ảnh hưởng tới memory hoặc connection.

## 9. Quy tắc lựa chọn API theo tình huống

| Tình huống tích hợp | Lựa chọn ban đầu | Lý do | Điểm cần xác minh |
| --- | --- | --- | --- |
| Đọc snapshot theo SKU | CassandraRepository | findById rõ ràng, ít boilerplate | Có đúng partition key, có cần stale-read tolerance không |
| Lưu entity có TTL và IF NOT EXISTS | CassandraTemplate | InsertOptions, WriteResult | LWT latency, wasApplied, TTL |
| Đọc sự kiện theo tenant/ngày, có paging | CassandraTemplate hoặc custom repository | Query có giới hạn, paging state | Tránh partition lớn; sort theo clustering key |
| Counter và CQL đặc thù | CqlTemplate | Kiểm soát cú pháp CQL và bind | Counter semantics, retry an toàn |
| Driver execution profile, tracing, bound statement chi tiết | CqlSession | Khai thác trực tiếp driver | Consistency, timeout, tài nguyên |
| WebFlux phục vụ nhiều request I/O | ReactiveRepository/ReactiveTemplate | Không chặn thread chờ I/O | Backpressure, timeout, lỗi |
| Đọc/ghi liên quan nhiều hệ thống (DB + broker + HTTP) | API phù hợp từng kho + orchestration | Quản lý nhất quán ở tầng ứng dụng | Outbox, idempotency, bù trừ và observability |

**Quy tắc thực hành:** bắt đầu với Repository nếu đa số truy vấn là CRUD theo khóa; đưa truy vấn có option/điều kiện vào Template; dùng CQL/driver khi thật sự cần các đặc tính bên dưới. Mỗi bước hạ tầng có thể tăng quyền điều khiển nhưng cũng tăng trách nhiệm bảo trì CQL, mapping, paging và lỗi.

## 10. Consistency, LWT và giao dịch có giới hạn

Nhiều hệ thống quan hệ dựa vào **@Transactional** để phối hợp nhiều bảng và tự động rollback toàn bộ khi có lỗi. Cassandra có mô hình giao dịch, mức nhất quán và giới hạn khác; **không giả định @Transactional của Spring Data Cassandra sẽ cho ACID transaction nhiều hàng/bảng giống JDBC/JPA**.

Những khái niệm quan trọng:

- **Consistency level** (ví dụ LOCAL_ONE, LOCAL_QUORUM) quyết định số replica phải phản hồi theo cấu hình replication và yêu cầu từng operation. Đọc mới nhất không được bảo đảm chỉ bằng việc chọn API Template hay Repository.
- **LWT** với **IF NOT EXISTS**, **IF column = value** sử dụng cơ chế đồng thuận cho cập nhật điều kiện; cần kiểm tra **wasApplied()** và tính chi phí latency/throughput.
- **Batch CQL** chủ yếu được thiết kế để nhóm những mutation liên quan; batch không phải công cụ tăng tốc ghi hàng loạt tùy ý hay bảo đảm transaction đa partition theo nghĩa RDBMS.
- **TTL** làm dữ liệu hết hạn tự động; cần cân nhắc tombstone, retention, sửa đổi TTL và tác động tới truy vấn.
- **Timestamp/LWW** và các update đến không đúng thứ tự có thể khiến kết quả khác thứ tự xử lý của ứng dụng; thiết kế xử lý version và late event phải rõ ràng.

### Bài toán xử lý trùng lặp

Một consumer nhận thông điệp **inventory.snapshot.changed** ít nhất một lần. Nếu một event được chuyển tới hai lần, gọi Repository.save() hai lần có thể cho cùng trạng thái khi dữ liệu và timestamp tương đương, nhưng **không tự chứng minh xử lý đúng** khi event đến đảo thứ tự hoặc có side effect ở dịch vụ khác.

Một mô hình có thể cân nhắc:

~~~text
Broker đưa event (eventId, sku, version, quantity)
      |
      v
Đối chiếu version / trạng thái nghiệp vụ
      |
      v
Ghi snapshot có điều kiện hoặc idempotency marker
      |
      v
Thực hiện/ghi nhận các side effect còn lại
      |
      v
ACK broker khi chính sách xử lý cho phép
~~~

Cần lựa chọn rõ khi nào ghi dấu đã xử lý, khi nào ACK, và cách phục hồi sau crash giữa các bước. **LWT trên một marker không biến nhiều write Cassandra, HTTP call và message publish thành một transaction phân tán**. Với yêu cầu nhất quán rất mạnh giữa nhiều hệ thống, có thể phải chọn kho giao dịch khác cho nguồn dữ liệu chính và chỉ dùng Cassandra làm projection.

## 11. Phân trang, lọc và giới hạn truy vấn

Thiết kế kiểu:

~~~sql
SELECT * FROM events_by_tenant_day
WHERE tenant_id = 't-01' AND event_day = '2026-11-21';
~~~

có thể hợp lệ nhưng vẫn trả hàng nghìn bản ghi. Đừng gọi phương thức repository trả **List** toàn bộ trong request HTTP nếu kích thước không bị chặn.

Cassandra hỗ trợ **driver paging state**. Spring Data có API **Slice**, **CassandraScrollPosition**, Query **pageRequest**/**pagingState** phù hợp từng phiên bản. Các đặc điểm:

- **Slice** thường phù hợp để biết còn trang tiếp hay không; tránh mặc định yêu cầu tổng số trang/count trên tập dữ liệu lớn.
- Paging state phải đi kèm đúng câu truy vấn và tham số. Nếu phát ra API cursor, cần ràng buộc với tenant/query, bảo vệ token và quy định thời gian sống; không xem nó là số trang offset tùy ý.
- **Sort** chỉ hợp lệ theo cách sắp xếp mà Cassandra hỗ trợ, thường dựa vào clustering columns trong partition đã chọn.
- Fetch size giới hạn số hàng mỗi lượt tải của driver; **không** thay thế giới hạn tổng số hàng ứng dụng phục vụ.
- **ALLOW FILTERING** không phải lối tắt đảm bảo performance. Cần đánh giá dựa trên mô hình dữ liệu và query plan.

Đối với dữ liệu lịch sử nhiều ngày, service có thể truy vấn các bucket ngày liên tiếp theo chính sách rõ ràng. Cần chặn số bucket một request được phép đọc; việc gộp/sắp xếp dữ liệu từ nhiều partition là trách nhiệm tầng ứng dụng hoặc dữ liệu projection riêng.

## 12. Timeout, retry, lỗi và quan sát

### 12.1. Các loại lỗi thường gặp

| Nhóm | Tình huống | Phản ứng nên thiết kế |
| --- | --- | --- |
| Kết nối hoặc khám phá cluster | Contact point sai, local DC sai, TLS/auth thất bại | Kiểm tra topology, credential, cấu hình driver; không retry vô hạn |
| Timeout | Coordinator hoặc replica chậm, quá tải, mất mạng | Phân biệt timeout đọc/ghi; giữ deadline và trạng thái chưa biết |
| Unavailable | Không đủ replica đáp ứng consistency | Có thể retry giới hạn hoặc chuyển chế độ degraded theo nghiệp vụ |
| Mapping lỗi | Entity, column, codec không khớp schema | Sửa mapping/migration; không che thành “không có dữ liệu” |
| CQL không hợp lệ | Query thiếu partition key, index hoặc dùng ALLOW FILTERING bừa bãi | Sửa mô hình bảng/truy vấn, không tự retry |
| LWT không applied | Có row hoặc điều kiện ghi không thỏa | Xử lý như kết quả nghiệp vụ, không mặc định là lỗi transport |

Exception từ driver có thể được Spring Data chuyển sang hệ **DataAccessException**; nhưng vẫn cần ghi nhận nguyên nhân gốc có cấu trúc. Đặc biệt, timeout ghi không chứng minh Cassandra đã không áp dụng mutation.

### 12.2. Retry có giới hạn và idempotency

Trong hệ thống message broker, delivery có thể lặp lại. Những thao tác như **counter increment** không nên được retry bừa bãi: hai lần thực thi có thể tăng giá trị hai lần. Các thao tác cập nhật thông thường cũng cần xem xét timestamp, version và điều kiện để biết có an toàn khi gửi lại không.

Nguyên tắc:

1. Đặt **deadline ở tầng workflow** bên cạnh timeout driver; không cộng dồn retry vượt ngân sách.
2. Chỉ retry lỗi tạm thời có thể được retry an toàn, theo chính sách driver/application được xác minh.
3. Dùng backoff có giới hạn và jitter ở tầng orchestration; tránh nhiều tầng cùng retry không kiểm soát.
4. Với conditional write, kiểm tra applied flag để phân biệt **điều kiện không thỏa** với **I/O thất bại**.
5. Với side effect ngoài Cassandra, có cơ chế xác nhận, idempotency key và phục hồi sau crash.

### 12.3. Metric, log và tracing

Nên theo dõi:

- Latency p95/p99 theo tên operation/table/driver node, số timeout và request failure.
- Request count, in-flight requests, throttling, pool/connection và queue pressure theo metric driver có sẵn.
- Số LWT applied/not applied, xung đột version, duplicate event; đặc biệt theo luồng tích hợp.
- Paging rows/pages, kích thước response, tỷ lệ truy vấn quét nhiều partition và tombstone warning.
- Trace/correlation ID từ API hoặc broker tới truy vấn Cassandra và bước ACK/publish.

Không log credential, token, toàn bộ payload hoặc binding chứa thông tin nhạy cảm. Không dùng giá trị SKU/tenantId/eventId làm nhãn metric có cardinality cao. Nếu bật query tracing hoặc logging bind values, chỉ bật có kiểm soát ở môi trường phù hợp.

## 13. Kiểm thử đúng tính chất Cassandra

Kiểm thử unit có thể mock **CassandraOperations** hoặc repository để xác minh service chọn nhánh đúng. Nhưng mock không chứng minh query hợp lệ, consistency, LWT hoặc paging. Với phần này nên dùng **Cassandra thật trong test**, chẳng hạn Testcontainers Cassandra, và tạo schema trước khi chạy.

Những test cần thiết:

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Boot context kết nối thành công | CqlSession, template và repository inject được; keyspace/dialect đúng |
| findById theo SKU có/không tồn tại | Có đúng entity hoặc Optional.empty; không quét cluster |
| Query theo tenant + day | Chỉ đọc partition được chọn; thứ tự theo clustering key |
| InsertOptions IF NOT EXISTS hai lần | Lần đầu applied, lần sau not applied |
| TTL nhỏ trong test | Bản ghi hết hạn theo TTL dự kiến, xét thời gian và biến động môi trường |
| Schema đổi tên cột | Mapping hoặc test thất bại có tín hiệu rõ ràng |
| Timeout / node mất kết nối | Không coi timeout như “bản ghi không tồn tại”; retry theo budget |
| Hai event cùng SKU đến đảo thứ tự | Không làm snapshot lùi về version cũ |
| API phân trang | Cursor đúng query, không mất/nhân đôi không chủ đích khi dữ liệu thay đổi |
| Tác vụ crash giữa ghi marker và side effect | Cơ chế phục hồi/đối soát theo thiết kế |

**@DataCassandraTest** là slice test do Spring Boot cung cấp để cấu hình thành phần dữ liệu Cassandra trong bối cảnh kiểm thử. Tuy nhiên, annotation và dependency test starter có thể khác giữa Boot 3.x và 4.x; lớp service không thuộc slice có thể cần **@Import** hoặc test **@SpringBootTest**. Boot 4.x có test starter chuyên biệt cho Cassandra; kiểm tra dependency thực tế. Test cần cluster/keyspace/schema đúng; annotation tự nó không khởi tạo một Cassandra cluster.

Một ví dụ kiểm tra business outcome tại tầng template (giả sử schema và dữ liệu test đã có):

~~~java
@DataCassandraTest
class CassandraSnapshotTest {

    @Autowired
    CassandraOperations cassandra;

    @Test
    void insertIfNotExistsDoesNotOverwriteExistingSku() {
        InventorySnapshot data = new InventorySnapshot(
                "SKU-01", 5, 1L, Instant.now());
        InsertOptions opts = InsertOptions.builder()
                .withIfNotExists()
                .build();

        assertTrue(cassandra.insert(data, opts).wasApplied());
        assertFalse(cassandra.insert(data, opts).wasApplied());
    }
}
~~~

Test cần xóa dữ liệu/bộ test riêng trước khi chạy để bảo đảm **SKU-01** chưa tồn tại. Để kiểm tra lỗi network và concurrency, chạy integration test có container/cluster cấu hình phù hợp, thay vì chỉ mock exception.

## 14. Các sai lầm phổ biến

**“Repository sẽ tự tối ưu mọi phương thức findBy...”** Repository tạo câu truy vấn theo tên phương thức, nhưng query vẫn phải tuân thủ khả năng truy cập của Cassandra. Không thể tùy ý filter/sort non-key columns trên bảng lớn.

**“CassandraTemplate giải quyết truy vấn chậm tốt hơn Repository.”** Hai API dùng chung cơ chế database; query sai partition key vẫn chậm. Hãy chỉnh data model và access pattern.

**“save() phát lỗi nếu ID đã tồn tại.”** Phần lớn lệnh ghi Cassandra có ngữ nghĩa upsert. Cần **IF NOT EXISTS** hoặc quy trình versioning khi phải kiểm soát ghi trùng.

**“@Transactional cho Cassandra giống giao dịch JDBC đa bảng.”** Không nên giả định điều đó. Xác định rõ tính nguyên tử/nhất quán Cassandra cung cấp và ranh giới side effect.

**“LWT có thể bật cho mọi ghi mà không đổi hiệu năng.”** LWT cần đồng thuận và có chi phí lớn hơn; chỉ dùng khi yêu cầu nghiệp vụ thực sự cần conditional write.

**“Reactive Flux nghĩa là không cần phân trang.”** Reactive giúp composition và non-blocking, nhưng không loại bỏ vấn đề partition quá lớn, memory, mạng và request deadline.

**“Timeout là thao tác chắc chắn thất bại.”** Có thể database đã áp dụng mutation nhưng caller không nhận phản hồi. Phải thiết kế retry/idempotency phù hợp.

**“ALLOW FILTERING biến Cassandra thành database phân tích.”** Nó có thể gây quét nhiều dữ liệu. Tối ưu bảng, index phù hợp hoặc dùng hệ thống khác cho truy vấn ad-hoc.

## 15. Checklist trước khi triển khai

1. Liệt kê những query có thật: khóa nào, phạm vi thời gian, thứ tự và giới hạn kết quả.
2. Kiểm tra partition key, clustering key, kích thước partition dự kiến và chính sách retention.
3. Chọn **Repository** cho CRUD theo khóa; **Template** cho entity có option; **CqlTemplate/CqlSession** cho CQL/driver đặc thù.
4. Thống nhất **imperative hay reactive** với thread model của ứng dụng; tránh block event-loop.
5. Xác minh contact points, local DC, keyspace, TLS, consistency và driver timeout theo môi trường.
6. Xác định ngữ nghĩa **upsert, IF NOT EXISTS, TTL, version và retry**; tách duplicate event khỏi kết quả không thể xác định do timeout.
7. Đặt giới hạn page size, số bucket, concurrency và kích thước response; không để query vô hạn trong HTTP handler.
8. Kiểm thử trên Cassandra thật các query, LWT, paging, lỗi mạng và event đến đảo thứ tự.
9. Theo dõi latency, số retry, timeout, throttling, kết quả conditional write và tracing; bảo vệ dữ liệu nhạy cảm.
10. Với workflow qua HTTP/database/broker, ghi rõ điểm ACK, side effect, trạng thái phục hồi và cơ chế chống trùng.

**Kết luận:** lựa chọn CassandraRepository hay CassandraTemplate nên xuất phát từ nhu cầu điều khiển truy vấn và mức trừu tượng mong muốn. Cả hai đều cần **mô hình dữ liệu theo access pattern**, chiến lược nhất quán và kiểm thử vận hành. Khi cần CQL hoặc driver đặc thù, CqlTemplate/CqlSession là lớp thấp hơn phù hợp; trong ứng dụng reactive, dùng các biến thể tương ứng thay vì chặn event-loop.

## Tài liệu tham khảo

- [Spring Boot — Working with NoSQL Technologies (Cassandra)](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter, cấu hình và các bean được auto-configure.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): khóa cấu hình Cassandra, timeout, consistency và schema action.
- [Spring Data Cassandra — Persisting Entities / CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): CassandraOperations, Query/Criteria và options.
- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): bind parameter, CQL query và mapping hàng.
- [Spring Data Cassandra — Cassandra-specific Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): repository, query derivation, consistency và paging.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): primary key, clustering column và mapping.
- [Spring Data Cassandra — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): reactive template/repository và execution model.
