# CqlTemplate và session factory trong Spring Data Cassandra

## 1. Vì sao phải hiểu CqlTemplate trước khi cấu hình Cassandra adapter?

Một dịch vụ nhận sự kiện `OrderPaid` qua JMS, chuyển đổi thành đối tượng Java và ghi vào Apache Cassandra. Khi phát sinh lỗi, bạn cần biết sự cố nằm ở đâu: message contract, connection đến cluster, keyspace, câu CQL, mapping Java hay cách một endpoint chờ kết quả.

Spring Data for Apache Cassandra cung cấp hai tầng đáng phân biệt:

- **`CqlTemplate`**: API mức thấp để chạy CQL, bind tham số, lấy kết quả, dịch exception và quản lý những công việc lặp lại của Cassandra driver.
- **`SessionFactory`**: abstraction cung cấp `CqlSession` cho các thao tác CQL; thường được xây từ một session driver dùng chung, sống lâu.

Ở phía dưới là **`CqlSession`** của DataStax Java Driver. Phía trên có **`CassandraTemplate`**, **`ReactiveCassandraTemplate`** và các Spring Integration endpoints sử dụng object mapping/Reactive APIs.

Trong module **SPRING_INTEGRATION_ADAPTERS**, các inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; mỗi kết nối cần hợp đồng message, đường lỗi và lifecycle rõ ràng. Chương **Adapter Cassandra** dùng kiến thức về `CqlTemplate` và session factory để giải thích nền tảng của những thao tác Cassandra được kích hoạt từ IntegrationFlow.

**Mục tiêu học tập:**

1. Phân biệt `CqlSession`, `CqlSessionFactoryBean`, `SessionFactory`, `DefaultSessionFactory` và `SessionFactoryFactoryBean`.
2. Tạo, inject và dùng `CqlTemplate` để chạy SELECT/INSERT/UPDATE/DELETE với giá trị được bind an toàn.
3. Hiểu `RowMapper`, `ResultSetExtractor`, `PreparedStatementCreator` và exception translation.
4. Phân biệt `CqlTemplate` đồng bộ với `ReactiveCqlTemplate` và các template có entity mapping.
5. Biết khi nào một `@ServiceActivator` có thể dùng `CqlTemplate`, và vì sao `CassandraMessageHandler` không nhận `CqlTemplate` làm dependency.
6. Thiết kế pooling/session lifecycle, keyspace, consistency, timeout, idempotency, observability và integration test.

## 2. Sơ đồ các tầng và trách nhiệm

~~~mermaid
flowchart TB
    A["JMS / HTTP / Kafka / File"] --> B["Spring Integration: Transformer + MessageChannel"]
    B --> C["Service Activator tùy chỉnh"]
    B --> D["CassandraMessageHandler"]
    C --> E["CqlTemplate hoặc ReactiveCqlTemplate"]
    D --> F["ReactiveCassandraOperations / ReactiveCassandraTemplate"]
    E --> G["SessionFactory / ReactiveSession"]
    F --> G
    G --> H["CqlSession — DataStax Java Driver"]
    H --> I[("Apache Cassandra cluster")]
~~~

Đây là sơ đồ **khái niệm**: ở nhánh reactive, `ReactiveSession` cầu nối driver `CqlSession` với publisher APIs; `SessionFactory` cơ bản của CQL imperative không đồng nhất với `ReactiveSession`. Đừng nhầm các mũi tên là một class inheritance chain duy nhất.

| Thành phần | Package/loại | Chịu trách nhiệm |
|---|---|---|
| `CqlSession` | `com.datastax.oss.driver.api.core` | Driver session, quản lý các kết nối tới nodes, routing, CQL requests |
| `CqlSessionFactoryBean` | `org.springframework.data.cassandra.config` | Spring `FactoryBean<CqlSession>` tạo/quản lý session driver |
| `SessionFactory` | Spring Data Cassandra | Interface cung cấp một `CqlSession` cho tầng CQL |
| `DefaultSessionFactory` | `org.springframework.data.cassandra.core.cql.session` | SessionFactory mặc định, trả về một session singleton |
| `SessionFactoryFactoryBean` | `org.springframework.data.cassandra.config` | Tạo SessionFactory có hỗ trợ mapping/schema lifecycle |
| `CqlTemplate` | `org.springframework.data.cassandra.core.cql` | Thực thi CQL kiểu blocking; callback, result mapping, exception translation |
| `ReactiveCqlTemplate` | `org.springframework.data.cassandra.core.cql` | Thực thi CQL qua `Mono`/`Flux` |
| `CassandraTemplate` / `ReactiveCassandraTemplate` | `org.springframework.data.cassandra.core` | Entity mapping dựa vào `@Table`, converter và query abstractions |
| `CassandraMessageHandler` | Spring Integration Cassandra | Endpoint nhận Spring Message, gọi `ReactiveCassandraOperations` |

### Ba thứ dễ nhầm nhất

**`CqlSessionFactoryBean` không phải `SessionFactory`.** Cái đầu là *Spring FactoryBean tạo driver session*, còn cái sau là interface *Spring Data dùng để lấy driver session*.

**`CqlTemplate` không phải `CassandraTemplate`.** CqlTemplate để lập trình CQL và map từng hàng qua callback; CassandraTemplate dùng object mapping của Spring Data.

**`CqlTemplate` không phải dependency trực tiếp của `CassandraMessageHandler`.** Spring Integration Cassandra handler nhận `ReactiveCassandraOperations`. Nếu muốn xây flow trực tiếp với CqlTemplate, hãy tạo service activator tùy chỉnh; nếu muốn outbound adapter/gateway Cassandra có sẵn, cung cấp reactive operations.

## 3. CqlSession: tài nguyên driver sống lâu, không tạo theo message

Driver `CqlSession` là session **thread-safe**, quản lý kết nối tới nhiều Cassandra nodes và intended to be **long-lived**. Một ứng dụng thông thường tái sử dụng một session cho cùng keyspace/cluster thay vì mở/đóng session trên mỗi message.

~~~mermaid
flowchart LR
    S["Một CqlSession singleton"] --> N1["Connection pool tới node A"]
    S --> N2["Connection pool tới node B"]
    S --> N3["Connection pool tới node C"]
    T1["Worker 1"] --> S
    T2["Worker 2"] --> S
    T3["Worker 3"] --> S
~~~

Sơ đồ không có nghĩa cứ có ba nodes là driver mở đúng ba TCP connections; số connection và routing tùy driver/version/configuration. Điều quan trọng là session là **tài nguyên dùng chung**, được lifecycle của Spring/container quản lý.

### 3.1. Dùng driver trực tiếp để tạo session

~~~java
import java.net.InetSocketAddress;
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DirectCqlSessionConfiguration {

    @Bean(destroyMethod = "close")
    public CqlSession cqlSession() {
        return CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .withKeyspace("shop_integration")
                .build();
    }
}
~~~

Đây là **một lựa chọn cho lab** khi keyspace `shop_integration` đã tồn tại. Datacenter `datacenter1` phải đúng metadata của Cassandra cluster. Spring gọi `close()` khi hủy bean; **không gọi `close()` sau mỗi lần SELECT/INSERT**.

Với Spring Boot, nên ưu tiên auto-configuration khi có sẵn. Không khai báo trùng `CqlSession` do driver builder tự tạo và session do Boot tạo nếu không chủ ý quản lý nhiều clusters. Nếu ứng dụng cần xác thực/TLS, đặt chúng trong secrets/driver configuration thay vì hard-code credentials trong bài.

### 3.2. Tạo driver session bằng CqlSessionFactoryBean

Spring Data cung cấp `CqlSessionFactoryBean`; đây là một Spring `FactoryBean<CqlSession>`, xử lý quá trình khởi tạo/đóng session.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.CqlSessionFactoryBean;

@Configuration
public class FactoryBeanSessionConfiguration {

    @Bean
    public CqlSessionFactoryBean cqlSession() {
        CqlSessionFactoryBean factory = new CqlSessionFactoryBean();
        factory.setContactPoints("127.0.0.1");
        factory.setPort(9042);
        factory.setLocalDatacenter("datacenter1");
        factory.setKeyspaceName("shop_integration");
        return factory;
    }
}
~~~

**Đây là phương án thay thế mục 3.1**, không đăng ký cả hai với cùng tên bean. `CqlSessionFactoryBean` được Spring dùng để tạo bean `CqlSession`; consumer inject theo type `CqlSession`, không cần gọi `factory.getObject()` thủ công.

#### FactoryBean và bean thực tế

Nếu tên bean factory là `cqlSession`:

- Inject `CqlSession` hoặc lấy bean tên `"cqlSession"` thì Spring trả về **đối tượng do FactoryBean tạo**.
- Lấy `"&cqlSession"` (dùng tiền tố `&` trong BeanFactory) mới là **bản thân FactoryBean**, chủ yếu cho mục đích cấu hình/chẩn đoán.
- `CqlSessionFactoryBean` **không** thay thế `DefaultSessionFactory` hoặc `SessionFactoryFactoryBean` trong tầng Spring Data.

Một số tài liệu/đoạn code cũ còn dùng `CassandraCqlSessionFactoryBean`; lớp đó đã bị deprecate và được khuyến nghị thay bằng `CqlSessionFactoryBean`. Tránh tiếp tục sao chép cấu hình dùng API cũ khi triển khai mới.

### 3.3. Spring Boot auto-configuration

Với một ứng dụng Spring Boot quản lý BOM, ví dụ local:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Đây là **application.yml của ứng dụng** (không phải YAML metadata của bài học). Khi dùng `spring-boot-starter-data-cassandra` hoặc reactive starter phù hợp, Spring Boot có thể tạo `CqlSession` và các template cần thiết; các bean có điều kiện tùy version/điều kiện auto-config.

Chọn **một** cách quản lý session trong ứng dụng:

1. Spring Boot auto-configuration (phổ biến).
2. Driver `CqlSession.builder()` với bean được quản lý lifecycle.
3. Spring Data `CqlSessionFactoryBean` hoặc `AbstractCassandraConfiguration` khi cần tùy chỉnh chuyên sâu.

Đừng kết luận “Cassandra chưa kết nối” chỉ vì không thấy bean tên đúng `cqlSession`: tên và điều kiện auto-configuration có thể khác. Hãy xem loại bean thực tế và dependency tree.

## 4. SessionFactory: abstraction cấp CqlSession cho CqlTemplate

Spring Data Cassandra định nghĩa `SessionFactory` riêng. Với các use case đơn giản, `DefaultSessionFactory` chứa **một `CqlSession`** và luôn trả về cùng session đó.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.SessionFactory;
import org.springframework.data.cassandra.core.cql.CqlTemplate;
import org.springframework.data.cassandra.core.cql.session.DefaultSessionFactory;

@Configuration
public class LowLevelCqlConfiguration {

    @Bean
    public SessionFactory sessionFactory(CqlSession cqlSession) {
        return new DefaultSessionFactory(cqlSession);
    }

    @Bean
    public CqlTemplate cqlTemplate(SessionFactory sessionFactory) {
        return new CqlTemplate(sessionFactory);
    }
}
~~~

Ví dụ dùng một bean `CqlSession` đã được cấu hình **theo một trong các cách ở mục 3**. CqlTemplate cũng có constructor nhận `CqlSession` trực tiếp:

~~~java
// Hợp lệ, nhưng dùng SessionFactory tiện hơn nếu cần abstraction.
CqlTemplate template = new CqlTemplate(cqlSession);
~~~

**Vòng đời:** gọi `CqlTemplate.query(...)` không đóng session driver sau một lần query. Khi Spring app shutdown, bean sở hữu `CqlSession` chịu trách nhiệm đóng kết nối. `DefaultSessionFactory` không phải một connection pool mới; nó chủ yếu bọc session dùng chung.

### 4.1. SessionFactoryFactoryBean dùng trong mapping/schema infrastructure

Nếu cần Spring Data entity mapping và schema actions, cấu hình `SessionFactoryFactoryBean` là lựa chọn bổ sung:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.SessionFactory;
import org.springframework.data.cassandra.config.SchemaAction;
import org.springframework.data.cassandra.config.SessionFactoryFactoryBean;
import org.springframework.data.cassandra.core.convert.CassandraConverter;

@Bean
public SessionFactoryFactoryBean mappedSessionFactory(
        CqlSession cqlSession,
        CassandraConverter converter) {

    SessionFactoryFactoryBean factory = new SessionFactoryFactoryBean();
    factory.setSession(cqlSession);
    factory.setConverter(converter);
    factory.setSchemaAction(SchemaAction.NONE);
    return factory;
}
~~~

`CassandraConverter` cần được cấu hình cùng mapping context/UDT resolver khi làm thủ công; `AbstractCassandraConfiguration` hoặc Boot thường giúp wire các thành phần này. `SchemaAction.NONE` thể hiện **không tự thay schema database trên startup** trong ví dụ.

**Quan trọng:** chọn **DefaultSessionFactory** *hoặc* **SessionFactoryFactoryBean** cho bean `SessionFactory` mà `CqlTemplate` inject, tránh tạo hai bean cùng type không có `@Qualifier` hoặc `@Primary`. `CqlSessionFactoryBean` vẫn tạo session ở tầng dưới; `SessionFactoryFactoryBean` tạo **SessionFactory** ở tầng trên.

### 4.2. Tại sao không đổi keyspace bằng CQL `USE` trong mỗi request?

Session gắn với keyspace và driver connection infrastructure. Đổi keyspace bằng `USE other_keyspace` trên cùng session dùng chung có thể tạo kết quả khó dự đoán giữa các thread/queries và khiến mapping mất nhất quán.

Nếu hệ thống cần nhiều keyspaces/tenants, nên chọn:

- Một `SessionFactory`/`CqlTemplate` riêng với keyspace xác định.
- Một routing session factory được cấu hình và kiểm thử đúng với context truyền xuyên thread.
- Fully qualified table name khi phù hợp với quyền truy cập và query được allowlist, không thay session keyspace tùy ý.

Quyết định multi-tenant còn liên quan ACL, replication, quotas và isolation; không dựa vào header `tenantId` do client tự gửi để cho phép truy cập keyspace khác.

## 5. Chuẩn bị schema và dependencies để thực hành CQL

Với Spring Boot quản lý BOM, các dependencies thông dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
<!-- Chỉ cần khi thực hành reactive hoặc Cassandra adapter/gateway có sẵn. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
~~~

Không buộc mọi ứng dụng phải thêm cả **imperative starter** và **reactive starter**: chọn theo API đang dùng. `CqlTemplate` thuộc Spring Data Cassandra core; `CassandraMessageHandler` trong `spring-integration-cassandra` sử dụng `ReactiveCassandraOperations`. Không chỉ thêm Spring Integration dependency mà mong tự sinh keyspace/table.

Trên Cassandra **test**, tạo:

~~~sql
-- Chỉ dùng mô hình replication này trong lab một node.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text,
    processed_at timestamp
);
~~~

Table được thiết kế để **truy vấn theo `event_id`**. Một truy vấn thường xuyên kiểu `WHERE order_id = ?` sẽ **không tối ưu** với schema này vì `order_id` không phải partition key. Thiết kế Cassandra phải dựa vào query pattern; không lạm dụng `ALLOW FILTERING` để “giải quyết” mô hình sai.

### Dữ liệu ví dụ

~~~json
{
  "eventId": "evt-3001",
  "orderId": "ORD-3001",
  "eventType": "OrderPaid",
  "schemaVersion": 1
}
~~~

`eventId` là business ID ổn định qua retry. `schemaVersion` nằm trong contract payload nhưng table lab chưa có cột tương ứng; muốn lưu riêng cần sửa schema/mapping có chủ đích, không giả định Cassandra tự tách JSON.

## 6. CqlTemplate: chạy INSERT bằng prepared bind values

`CqlTemplate` thực thi CQL **đồng bộ (blocking)**. Với một câu lệnh có giá trị do người dùng hoặc message cung cấp, dùng `?` placeholders và arguments để tránh nối chuỗi CQL từ dữ liệu:

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public class OrderEventCqlWriter {

    private final CqlOperations cql;

    public OrderEventCqlWriter(CqlOperations cql) {
        this.cql = cql;
    }

    public void save(String eventId, String orderId,
                     String eventType, String json) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, payload_json, processed_at) "
                + "VALUES (?, ?, ?, ?, ?)",
                eventId, orderId, eventType, json, Instant.now());
    }
}
~~~

Khi `CqlTemplate` đã được cấu hình (mục 4), nó implement `CqlOperations` nên có thể inject qua interface. Overload `execute(String cql, Object... args)` tạo một **prepared statement với bind values**. Driver và Cassandra hỗ trợ cache prepared statements, giúp tối ưu query lặp lại mà ứng dụng không cần tự giữ một cache vô hạn.

**Đừng dựa vào boolean của `execute(...)` để tự kết luận event mới được tạo.** Với CQL INSERT bình thường, Cassandra có *upsert semantics*, cùng khóa có thể được ghi lại; nếu cần “chưa tồn tại”, phải dùng conditional write `IF NOT EXISTS` và kiểm tra applied result.

### 6.1. INSERT không phải RDBMS unique insert

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, payload_json
) VALUES (
    'evt-3001', 'ORD-3001', 'OrderPaid',
    '{"eventId":"evt-3001"}'
);
~~~

Chạy lại cùng `event_id` thông thường **không ném lỗi duplicate key** giống constraint unique của một RDBMS. Cassandra dựa trên timestamps/conflict resolution để quyết định các giá trị được lưu. Nếu producer gửi lại **cùng event ID nhưng nội dung khác**, tác động nghiệp vụ có thể sai dù CQL thành công.

Với bảng event log, nên coi `eventId` là **immutable identity** và kiểm tra duplicate có payload xung đột. Với bảng state theo đơn hàng, cần xử lý thứ tự version/conditional updates để tránh event cũ ghi đè trạng thái mới.

### 6.2. UPDATE và DELETE bằng CqlTemplate

~~~java
public void changeEventType(String eventId, String eventType) {
    cql.execute(
            "UPDATE order_event SET event_type = ? WHERE event_id = ?",
            eventType, eventId);
}

public void delete(String eventId) {
    cql.execute(
            "DELETE FROM order_event WHERE event_id = ?",
            eventId);
}
~~~

Hai đoạn là methods trong repository đã có field `cql`. CQL UPDATE có thể **tạo cell/row mới nếu khóa chưa tồn tại** tùy operation; không mặc định update chỉ thành công khi row có sẵn. Cassandra DELETE tạo **tombstones**, có ảnh hưởng tới compaction và read performance. Không xóa hàng loạt theo wildcard hoặc xử lý user-provided WHERE clause tùy ý.

## 7. SELECT: RowMapper, queryForObject và queryForList

`CqlTemplate` cung cấp các method:

- `queryForObject(...)` cho kết quả mong đợi **một row/một giá trị** hoặc một object theo mapper.
- `query(...)` với `RowMapper<T>` cho nhiều rows.
- `queryForList(...)` cho kết quả dạng `List<Map<String,Object>>` hoặc danh sách giá trị theo overload.
- `queryForStream(...)` khi cần stream theo API phù hợp, cần đóng/tiêu thụ stream có kiểm soát.
- `query(...)` với `RowCallbackHandler` hoặc `ResultSetExtractor` khi cần callback mức thấp hơn.

### 7.1. Lấy một cột bằng queryForObject

~~~java
import org.springframework.data.cassandra.core.cql.CqlOperations;

public String findType(String eventId) {
    return cql.queryForObject(
            "SELECT event_type FROM order_event WHERE event_id = ?",
            String.class,
            eventId);
}
~~~

`findType` là method của repository có `CqlOperations cql`. `queryForObject` mong query có đúng số row/column phù hợp; **đừng dùng để lấy cả bảng**. Khi không có row hoặc có nhiều rows ngoài ý muốn, API có thể báo lỗi kích thước kết quả theo version/overload. Định nghĩa rõ cách xử lý “không tìm thấy” bằng kiểm thử, thay vì chỉ dựa vào `null`.

### 7.2. Map một hàng sang DTO

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.List;
import java.util.Optional;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.data.cassandra.core.cql.RowMapper;

public record OrderEventRow(
        String eventId, String orderId,
        String eventType, String payloadJson) {
}

public class OrderEventCqlReader {

    private final CqlOperations cql;

    public OrderEventCqlReader(CqlOperations cql) {
        this.cql = cql;
    }

    public Optional<OrderEventRow> findById(String eventId) {
        List<OrderEventRow> rows = cql.query(
                "SELECT event_id, order_id, event_type, payload_json "
                + "FROM order_event WHERE event_id = ?",
                (row, index) -> new OrderEventRow(
                        row.getString("event_id"),
                        row.getString("order_id"),
                        row.getString("event_type"),
                        row.getString("payload_json")),
                eventId);
        return rows.stream().findFirst();
    }
}
~~~

Ví dụ cho thấy `RowMapper` nhận một Cassandra driver `Row` rồi tạo Java DTO. Tham số `index` giúp xử lý số thứ tự row khi cần; nó **không phải Cassandra partition ID**. Import `Row`/`RowMapper` nằm trong ví dụ để người đọc biết nguồn API; lambda dùng trực tiếp type inference.

**Lợi ích của RowMapper:** bạn kiểm soát tên cột và cách convert mà không cần annotating toàn bộ DTO bằng `@Table`. **Đánh đổi:** mapper phải được cập nhật khi schema/cột hoặc type CQL thay đổi; nó không tự biết object mapping rules của `CassandraConverter`.

### 7.3. queryForList với kết quả dạng Map

~~~java
import java.util.List;
import java.util.Map;

List<Map<String, Object>> result = cql.queryForList(
        "SELECT event_id, event_type FROM order_event WHERE event_id = ?",
        "evt-3001");
~~~

Kết quả Map hữu ích cho ad-hoc diagnostics nhưng làm giảm type safety so với DTO. Không đưa toàn bộ Map từ database ra HTTP response mà không kiểm tra/loại bỏ cột bí mật; Spring Message payload cũng nên có schema rõ ràng.

## 8. Prepared statements và callback API

Với Cassandra, một câu CQL được thực thi nhiều lần có thể được driver **prepare** và bind values; driver hiện đại hỗ trợ caching prepared statements.

### 8.1. Dùng arguments là cách đơn giản nhất

~~~java
// CqlOperations tự chọn prepared-statement path cho overload có args.
String eventType = cql.queryForObject(
        "SELECT event_type FROM order_event WHERE event_id = ?",
        String.class,
        "evt-3001");
~~~

Đây là lựa chọn nên ưu tiên cho phần lớn queries đơn giản. Với các statement tĩnh không có arguments, `queryForObject(String cql, Class<T>)` có thể gửi một CQL statement trực tiếp, còn overload có args sử dụng prepared statements.

### 8.2. PreparedStatementCreator + binder cho logic phức tạp

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.cql.CqlOperations;

List<String> orderIds = cql.query(
        session -> session.prepare(
                "SELECT order_id FROM order_event WHERE event_id = ?"),
        ps -> ps.bind("evt-3001"),
        (row, rowNum) -> row.getString("order_id"));
~~~

Ba callbacks ở đây lần lượt là:

1. **PreparedStatementCreator:** tạo prepared statement với `CqlSession` đang được template quản lý.
2. **PreparedStatementBinder:** bind giá trị cụ thể vào statement đã prepare.
3. **RowMapper:** chuyển từng Cassandra row thành Java `String`.

Cấu hình này hữu ích khi cần tùy chỉnh các tùy chọn statement/binding hoặc kiểm thử từng callback. Đừng prepare lại CQL khác nhau cho mỗi event bằng cách chèn trực tiếp `eventId` vào CQL string; điều đó làm giảm cache hiệu quả và tăng nguy cơ injection.

### 8.3. ResultSetExtractor và RowCallbackHandler

| Callback | Cách dùng | Lợi ích | Giới hạn |
|---|---|---|---|
| `RowMapper<T>` | Mỗi row → một `T` | Dễ test, type-safe | Tạo danh sách khi dùng `query(...)` dạng list |
| `RowCallbackHandler` | Xử lý từng row bằng callback | Tránh phải tự viết vòng lặp thủ công | Side effect callback cần kiểm soát |
| `ResultSetExtractor<T>` | Nhận `ResultSet` để tự trích xuất kết quả | Linh hoạt với kết quả tổng hợp | Dễ tạo mã coupling với driver |
| `PreparedStatementCreator` | Tạo `PreparedStatement` qua session | Tùy biến cách prepare | Thêm complexity |
| `PreparedStatementBinder` | Bind params cho prepared statement | Không nối chuỗi dữ liệu | Phải khớp số/types placeholders |

Cassandra có **paging**: API trả list và thu thập quá nhiều dữ liệu có thể gây memory pressure. Query đúng partition và page size phù hợp, không tạo `SELECT * FROM huge_table` rồi ép hết vào `List` chỉ để tiện xử lý.

## 9. ReactiveCqlTemplate: cùng CQL, khác cách thực thi

`CqlTemplate` thuộc mô hình **blocking**. Spring Data Cassandra còn có `ReactiveCqlTemplate` để trả về các Project Reactor publishers:

- `execute(...)` trả `Mono<Boolean>` cho các CQL write/DDL tương ứng.
- `queryForObject(...)` trả `Mono<T>`.
- `query(...)` có thể trả `Flux<T>`.

**Reactive là hai giai đoạn:** *compose publisher* rồi *subscribe*. Gọi `reactiveCqlTemplate.execute(...)` tạo một `Mono` chưa chắc đã thực hiện I/O cho tới khi có subscriber.

### 9.1. Tạo ReactiveCqlTemplate từ cùng driver session

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.ReactiveCqlTemplate;
import org.springframework.data.cassandra.core.cql.session.DefaultBridgedReactiveSession;

@Configuration
public class ReactiveLowLevelCqlConfiguration {

    @Bean
    public ReactiveCqlTemplate reactiveCqlTemplate(CqlSession session) {
        return new ReactiveCqlTemplate(
                new DefaultBridgedReactiveSession(session));
    }
}
~~~

`DefaultBridgedReactiveSession` chuyển hoạt động bất đồng bộ của driver `CqlSession` sang reactive publisher. Nó không tạo một Cassandra cluster thứ hai. Do session có thể được dùng chung, **không đóng bridge/session tùy ý trong từng reactive subscription**; để bean owner/container quản lý lifecycle theo ứng dụng.

Nếu Spring Boot hoặc `AbstractReactiveCassandraConfiguration` đã tạo các reactive bean tương ứng, không đăng ký duplicate chỉ vì ví dụ trên cho thấy cách tạo thủ công. Kiểm tra cấu hình thực tế bằng bean definitions và qualifier.

### 9.2. Reactive DAO cho INSERT và SELECT

~~~java
import org.springframework.data.cassandra.core.cql.ReactiveCqlOperations;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class ReactiveOrderEventDao {

    private final ReactiveCqlOperations cql;

    public ReactiveOrderEventDao(ReactiveCqlOperations cql) {
        this.cql = cql;
    }

    public Mono<Boolean> save(String eventId, String orderId,
                              String eventType, String json) {
        return cql.execute(
                "INSERT INTO order_event "
                + "(event_id, order_id, event_type, payload_json) "
                + "VALUES (?, ?, ?, ?)",
                eventId, orderId, eventType, json);
    }

    public Mono<String> findType(String eventId) {
        return cql.queryForObject(
                "SELECT event_type FROM order_event WHERE event_id = ?",
                String.class, eventId);
    }
}
~~~

**Ví dụ caller đúng trong reactive pipeline:**

~~~java
public Mono<Void> recordPaid(String eventId, String orderId, String json) {
    return reactiveOrderEventDao
            .save(eventId, orderId, "OrderPaid", json)
            .doOnNext(applied -> {
                if (!applied) {
                    throw new IllegalStateException("Conditional write not applied");
                }
            })
            .then();
}
~~~

`reactiveOrderEventDao` là dependency đã inject. Không gọi `save(...)` rồi bỏ quên `Mono`. Trong WebFlux, returning `Mono<Void>` cho framework cho phép subscription trong request pipeline; trong một tác vụ background, phải chọn cơ chế subscribe/lifecycle/error handling có kiểm soát.

**Không tự động coi `Boolean applied` là đảm bảo business uniqueness.** CQL INSERT không có `IF NOT EXISTS` vẫn có semantics upsert, nên `true` không đồng nghĩa một event mới duy nhất được tạo. Khi dùng LWT, phải kiểm tra kết quả áp dụng đúng với câu lệnh cụ thể.

### 9.3. Mono/Flux và lỗi

Một kết nối Cassandra thất bại trong reactive DAO có thể phát ra **error signal sau khi method đã trả publisher**. `try/catch` chỉ quanh lời gọi `save()` sẽ không bắt được mọi lỗi:

~~~java
return reactiveOrderEventDao.save(eventId, orderId, "OrderPaid", json)
        .doOnError(error -> metrics.recordCassandraFailure(error))
        .retryWhen(
            reactor.util.retry.Retry.backoff(2, java.time.Duration.ofMillis(200))
                .filter(this::isTransientCassandraFailure));
~~~

Đây là fragment minh họa trong một service có `metrics` và predicate `isTransientCassandraFailure(...)` do ứng dụng tự triển khai. `retryWhen` là một **chính sách có giới hạn**, không phải gợi ý retry mọi exception. Với lệnh ghi không idempotent như tăng counter, retry mù quáng có thể gây tác động lặp.

### 9.4. Không dùng `block()` trên event-loop

~~~java
// Chỉ dùng trong code imperative nơi thread được phép chờ.
Boolean result = reactiveOrderEventDao
        .save(eventId, orderId, "OrderPaid", json)
        .block();
~~~

`block()` biến đường xử lý thành blocking; nó có thể gây lỗi hoặc giảm thông lượng trên WebFlux/Reactor event-loop. Nếu muốn một flow thực sự reactive, hãy trả `Mono`/`Flux` tới subscriber và kiểm soát concurrency/backpressure thay vì block trong một handler bất kỳ.

## 10. Phân biệt các template để chọn đúng API

| API | Mô hình | Có mapping entity `@Table`? | Tình huống nên dùng |
|---|---|---|---|
| `CqlTemplate` | Blocking | Không tự động như CassandraTemplate | CQL nhỏ, diagnostic, query tùy biến, callback |
| `ReactiveCqlTemplate` | Reactive `Mono`/`Flux` | Không tự động như ReactiveCassandraTemplate | CQL reactive, counter/ad-hoc operations |
| `CassandraTemplate` | Blocking | **Có**, dùng converter/mapping context | CRUD domain object, repositories |
| `ReactiveCassandraTemplate` | Reactive | **Có**, cùng Spring Data converter | Reactive CRUD, CassandraMessageHandler |
| `CqlSession` (driver) | Driver sync/async API | Không có Spring Data entity mapping | Trường hợp cần driver-specific operations |

Không dùng `CqlTemplate` để thay thế `ReactiveCassandraOperations` chỉ vì cả hai cùng chạy được CQL. Những Spring Integration Cassandra adapters/gateways có sẵn yêu cầu **ReactiveCassandraOperations**; khi cần API imperative, viết một service activator tùy chỉnh.

### 10.1. `CassandraTemplate` có thêm lớp object mapping

`CassandraTemplate` dựa trên `CqlTemplate`/CQL infrastructure nhưng kết hợp `CassandraConverter` và mapping context để biết:

- `@Table`: entity vào bảng nào.
- `@PrimaryKey`/`@PrimaryKeyClass`: primary key/partition-clustering keys.
- `@Column`: tên cột và cách mapping field.
- Type conversions và UDTs được cấu hình qua converter.

`CqlTemplate` chỉ biết CQL và Cassandra `Row`; việc tạo DTO/entity qua `RowMapper` do người dùng quyết định. Do đó hai template **bổ sung** nhau, không phải cùng một class có hai tên.

### 10.2. CassandraMessageHandler dùng cái nào?

~~~java
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;

// Đúng: dependency là reactive operations.
CassandraMessageHandler handler =
        new CassandraMessageHandler(reactiveCassandraOperations);
~~~

`reactiveCassandraOperations` là bean đã được inject từ Spring Data reactive. **Không** truyền một `CqlTemplate` vào constructor này; nếu không compile được, nguyên nhân không nằm ở cấu hình keyspace mà ở **API mismatch**.

Mặc định `CassandraMessageHandler` bất đồng bộ và có thể chạy `INSERT`, `UPDATE`, `DELETE` hoặc `STATEMENT`. Với `async(false)`, handler có thể chờ completion từ reactive operation, nhưng **không** biến Cassandra thành RDBMS transaction hoặc một nguồn reply mặc định.

## 11. Dùng CqlTemplate qua Spring Integration Service Activator

Bạn có thể gọi `CqlTemplate` trực tiếp từ một service activator nếu ứng dụng đã có xử lý imperative, cần CQL mức thấp hoặc chưa muốn dùng Cassandra outbound adapter có sẵn.

~~~mermaid
flowchart LR
    A["JMS inbound adapter"] --> B["DirectChannel"]
    B --> C["@ServiceActivator"]
    C --> D["OrderEventCqlWriter"]
    D --> E["CqlTemplate"]
    E --> F["SessionFactory -> CqlSession"]
    F --> G[("Cassandra")]
~~~

### 11.1. Service activator một chiều

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class SavePaidOrderService {

    private final OrderEventCqlWriter writer;

    public SavePaidOrderService(OrderEventCqlWriter writer) {
        this.writer = writer;
    }

    @ServiceActivator(inputChannel = "paidEventsForCassandra")
    public void save(PaidOrderEvent event) {
        writer.save(
                event.eventId(),
                event.orderId(),
                "OrderPaid",
                event.payloadJson());
    }
}

public record PaidOrderEvent(
        String eventId, String orderId, String payloadJson) {
}
~~~

`PaidOrderEvent` là DTO đã được transformer/validator tạo **trước** service activator. `OrderEventCqlWriter` dùng blocking CQL API ở mục 6.

Nếu input channel là `DirectChannel` và method xử lý đồng bộ, exception từ CqlTemplate **có thể đi ngược** đến caller/inbound listener. Nếu JMS listener sử dụng session transacted và error flow không nuốt exception, broker có thể redeliver message sau rollback.

### 11.2. Java DSL tương đương

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow savePaidOrdersFlow(
        OrderEventCqlWriter writer) {

    return IntegrationFlow.from("paidEventsForCassandra")
            .handle(PaidOrderEvent.class, (event, headers) -> {
                writer.save(
                        event.eventId(),
                        event.orderId(),
                        "OrderPaid",
                        event.payloadJson());
                return null;
            })
            .get();
}
~~~

Đây là **cách thay thế** `@ServiceActivator` ở mục 11.1 cho cùng input channel. Không đăng ký cả hai chỉ để lưu một sự kiện: khi có hai consumers, semantics dispatch có thể khác mong đợi.

### 11.3. Chuyển đổi JSON từ JMS

Nếu JMS inbound adapter nhận `TextMessage` và payload Spring là JSON `String`, phải biến đổi trước:

~~~java
// Fragment Java DSL, objectMapper đã được inject.
.transform(String.class, json -> {
    try {
        return objectMapper.readValue(json, PaidOrderEvent.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalArgumentException("Invalid PaidOrderEvent JSON", ex);
    }
})
.channel("paidEventsForCassandra")
~~~

Không để CqlTemplate tự parse JSON theo tên cột; nó là CQL execution template. Ngoài JSON syntax, phải validate business fields, `schemaVersion`, `eventId` và authorization trước khi ghi database.

### 11.4. Khi không nên dùng blocking CqlTemplate trong flow

Nếu upstream là WebFlux event-loop, `FluxMessageChannel` hoặc reactive pipeline end-to-end, blocking `CqlTemplate` có thể chiếm event-loop và làm giảm throughput. Khi đó nên dùng `ReactiveCqlTemplate` hoặc `ReactiveCassandraOperations` và đảm bảo publisher được subscribe đúng cách.

Tách blocking work sang scheduler được chỉ định là một lựa chọn nhưng **không tự bảo đảm** source JMS/Kafka chỉ ack sau khi Cassandra hoàn tất. Cần thiết kế acknowledgment boundary, error path và durable handoff rõ ràng.

## 12. Exception translation và cách phân loại lỗi

Một lý do chọn Spring Data `CqlTemplate` thay vì gọi driver ở mọi nơi là **exception translation**: các lỗi ở Cassandra driver được chuyển vào hệ phân cấp `org.springframework.dao.DataAccessException` khi có thể. Điều này giúp service viết chính sách retry/alert theo loại lỗi mà không gắn mọi handler với lớp exception driver cụ thể.

~~~mermaid
flowchart TD
    A["CqlTemplate.execute/query"] --> B["Cassandra driver request"]
    B --> C{"Kết quả?"}
    C -->|"Thành công"| D["ResultSet / mapped row / applied"]
    C -->|"Thất bại"| E["DriverException hoặc runtime exception"]
    E --> F["PersistenceExceptionTranslator"]
    F --> G["Spring DataAccessException"]
    G --> H{"Transient hay permanent?"}
    H -->|"Có thể phục hồi"| I["Retry có giới hạn + backoff"]
    H -->|"Sai cấu hình/contract"| J["Fail fast + alert/quarantine"]
~~~

Trong các phiên bản Spring Data khác nhau, chi tiết `PersistenceExceptionTranslator` có thể được cung cấp qua template, factory/configuration hoặc converter infrastructure. **Không nên viết logic phụ thuộc một subclass exception cụ thể mà chưa kiểm tra version**. Nên phân biệt:

| Nhóm lỗi | Ví dụ | Chiến lược |
|---|---|---|
| Connection/network transient | Node tạm mất kết nối, connection reset | Thử lại có giới hạn khi operation idempotent |
| Unavailable/overload | Không đủ replica cho CL, request backlog | Backoff, giảm concurrency, alert |
| Timeout với outcome không chắc | Client không nhận reply trong hạn | Retry **có idempotency**, không suy ra Cassandra chưa ghi |
| Invalid CQL/schema | Table/keyspace sai tên, syntax không hợp lệ | Sửa migration/config; retry nguyên dạng thường vô ích |
| Codec/type mismatch | Bind `String` vào cột CQL không phù hợp | Sửa contract/mapper |
| Authentication/authorization | Credentials lỗi hoặc thiếu quyền | Sửa secrets/ACL, không retry nóng |
| Too many results | Query sai partition, page size lớn | Sửa data model/query, tránh quét bừa |

### 12.1. Imperative try/catch

~~~java
import org.springframework.dao.DataAccessException;

public void persistSafely(PaidOrderEvent event) {
    try {
        writer.save(
                event.eventId(), event.orderId(),
                "OrderPaid", event.payloadJson());
    } catch (DataAccessException ex) {
        // Log exception class + eventId đã kiểm soát;
        // KHÔNG log toàn bộ payload nhạy cảm.
        throw ex; // Giữ exception propagation nếu nguồn cần rollback.
    }
}
~~~

Fragment minh họa một service có field `writer` đã inject. Không bắt mọi `DataAccessException` rồi nuốt lỗi: với listener transacted, điều đó có thể làm message nguồn **được ack/commit dù Cassandra chưa lưu**. Chỉ kết thúc bình thường khi nghiệp vụ đã quyết định và ghi nhận kết quả từ chối/quarantine một cách an toàn.

### 12.2. Reactive exception signal

Với `ReactiveCqlTemplate`, lỗi CQL có thể chỉ xuất hiện **khi publisher được subscribe**:

~~~java
return reactiveCqlTemplate
        .execute(
            "INSERT INTO order_event "
            + "(event_id, order_id, event_type, payload_json) "
            + "VALUES (?, ?, ?, ?)",
            eventId, orderId, eventType, json)
        .doOnError(ex -> log.warn(
                "Cassandra operation failed for eventId={}", eventId, ex));
~~~

Đây là fragment service đã có `reactiveCqlTemplate` và `log`, không phải method hoàn chỉnh. Logging trong `doOnError` **không tự làm publisher hoàn thành thành công**; error vẫn được truyền trừ khi downstream chọn `onErrorResume(...)` hoặc cơ chế tương tự. Với source JMS/Kafka, đảm bảo người chịu trách nhiệm acknowledge được thông báo về completion/error thật sự.

### 12.3. Exception không thay thế giám sát cluster

Một tỉ lệ nhỏ timeout có thể bị che bởi retries, trong khi p99 latency, pending requests và cluster load tiếp tục tăng. Hãy theo dõi cả application metrics và Cassandra/driver metrics; không chờ đến khi xuất hiện lỗi toàn hệ thống mới phát hiện hot partition.

## 13. Consistency, timeout, pagination và CqlSession configuration

`CqlSession` chịu trách nhiệm đưa query đến cluster; Spring Data template có thể áp đặt một số statement defaults. Cassandra dùng replication/consistency chứ không tự cung cấp một transaction SQL tổng quát cho mọi thao tác.

### 13.1. Consistency level

| Consistency | Ví dụ ý nghĩa | Hạn chế |
|---|---|---|
| `ONE` | Một replica phản hồi đủ theo CL | Không bảo đảm mọi replica đã thấy write tại thời điểm đó |
| `LOCAL_QUORUM` | Đủ quorum trong local DC | Phụ thuộc replication factor/placement thực tế |
| `ALL` | Yêu cầu tất cả replicas liên quan | Khả năng sẵn sàng có thể giảm khi replica lỗi |
| `LOCAL_ONE` | Một replica local | Phù hợp một số workload latency-focused, phải xét read/write CL |

Với replication factor 3 ở một datacenter, local quorum thường là 2. Với multi-DC và replication khác, không thể dùng con số đó cho mọi trường hợp. Consistency level không giải quyết việc **event v2 đến trước v1** hoặc **hai thao tác cùng khóa có timestamp khác nhau**; cần version/conditional write nếu nghiệp vụ yêu cầu.

### 13.2. Cấu hình statement thay vì thay đổi CqlTemplate lúc chạy

`CqlTemplate` có các cấu hình mặc định như consistency và page size thông qua `CassandraAccessor`. Driver cũng có **execution profile**, request timeout, retry policy và connection settings. Chúng phải được cấu hình cố định theo application/operation class, không đổi liên tục trên một singleton template từ header của từng message.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.SessionFactory;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

@Bean("readCqlTemplate")
public CqlTemplate readCqlTemplate(SessionFactory factory) {
    CqlTemplate template = new CqlTemplate(factory);
    template.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
    template.setPageSize(100);
    return template;
}
~~~

Các method `setConsistencyLevel`/`setPageSize` thuộc API Spring Data Cassandra, nhưng nên kiểm tra signatures của version thư viện đang dùng. Ví dụ `LOCAL_QUORUM` chỉ phù hợp khi replication topology cho phép; nếu lab một node/RF=1, kiểm tra sự phù hợp trước khi dùng production setting.

**Không trộn thay đổi global template config theo request:** singleton template có thể được nhiều threads dùng chung; muốn per-operation consistency/timeout, dùng statement/driver execution profile hoặc template/DAO riêng có cấu hình ổn định.

### 13.3. Timeout không chứng minh chưa ghi

~~~text
Client gửi INSERT evt-3001
  -> Coordinator nhận request
  -> Replicas ghi dữ liệu
  -> Response bị mất trên mạng
  -> Client thấy timeout
  -> Caller retry cùng eventId
~~~

Nếu event upsert là bất biến và cùng primary key, retry có thể an toàn hơn so với một thao tác tăng counter. Với conditional write `IF NOT EXISTS`, cần kiểm tra kết quả applied/row đang có. Không tự động retry vô hạn mọi operation từ CqlTemplate mà không phân biệt idempotency.

### 13.4. Pagination và Cassandra data modeling

Khi truy vấn nhiều rows trong một partition:

- Thiết kế partition/clustering keys theo câu hỏi nghiệp vụ sẽ truy vấn.
- Dùng page size và continuation/paging state khi API hỗ trợ thay vì load hết result vào bộ nhớ.
- Giới hạn kích thước partitions; tránh `SELECT *` không có key predicate trên bảng lớn.
- Đo p95/p99, số rows read, tombstones và coordinator pressure.
- Với reactive `Flux<T>`, quản lý subscription/backpressure và số query in-flight, không mặc định `collectList()` là an toàn.

`CqlSession` chia sẻ connections không có nghĩa rằng Cassandra cluster đáp ứng vô hạn queries song song; session reuse và backpressure là hai trách nhiệm khác nhau.

## 14. Transaction boundary với JMS, HTTP và Kafka

Khi Service Activator gọi blocking CqlTemplate trong một luồng JMS, sẽ có ít nhất hai tài nguyên tách biệt: **JMS session** và **Cassandra operation**.

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant Listener as JMS inbound adapter
    participant CQL as Service Activator + CqlTemplate
    participant DB as Cassandra
    Broker->>Listener: Deliver evt-3001
    Listener->>CQL: Spring Message via DirectChannel
    CQL->>DB: INSERT evt-3001
    DB-->>CQL: Write complete theo CL
    CQL-->>Listener: Handler hoàn thành
    Listener-->>Broker: JMS commit
    Note over Broker,DB: Cassandra write và JMS commit không atomic
~~~

Nếu Cassandra ghi thành công nhưng JVM crash **trước khi JMS commit**, broker có thể giao lại message. Nếu có lỗi Cassandra và exception truyền ngược qua `DirectChannel` tới listener transacted, JMS có thể rollback/redeliver; tuy nhiên Cassandra có thể đã ghi một phần/đã hoàn thành trước khi exception xảy ra.

| Trình tự | Rủi ro | Cách phòng vệ |
|---|---|---|
| Cassandra write thành công → JVM crash → JMS chưa commit | Duplicate redelivery | Primary key `eventId` ổn định, idempotent write |
| JMS commit trước Cassandra async completion | Cassandra lỗi nhưng broker không phát lại | Không ack quá sớm, durable handoff/retry độc lập |
| Kafka offset commit trước write Cassandra | Event không được phát lại sau DB lỗi | Chọn offset/ack boundary phù hợp |
| HTTP response báo success trước DB completion | Caller tin dữ liệu đã lưu | Chờ completion hoặc trả trạng thái accepted + job tracking |
| Cassandra timeout nhưng server đã ghi | Retry dẫn đến tác động lặp | Upsert immutable event hoặc conditional write |

### 14.1. DirectChannel vs ExecutorChannel

~~~text
DirectChannel + blocking CqlTemplate:
  JMS receive -> service activator -> Cassandra write -> return/throw
  -> listener có thể commit/rollback dựa vào exception

ExecutorChannel hoặc reactive async:
  JMS receive -> enqueue/dispatch -> listener có thể commit
                                  -> DB write sau đó fail ở thread khác
                                  -> không rollback được JMS gốc
~~~

Một `ExecutorChannel` hoặc `QueueChannel` in-memory có thể tách thread nhưng **không phải durable queue**. Nếu yêu cầu không mất event, cần lưu công việc vào nguồn bền vững, inbox/outbox hoặc chọn end-to-end ack control đã được integration-test.

### 14.2. Retry, idempotency và applied result

`CqlTemplate.execute(...)` không làm request idempotent theo nghĩa nghiệp vụ. Ví dụ:

- `INSERT` cùng `eventId`, cùng nội dung immutable: thường phù hợp với redelivery.
- `UPDATE counter = counter + 1` hoặc câu lệnh cộng dồn: **không an toàn khi retry mù quáng**.
- `INSERT ... IF NOT EXISTS`: một lightweight transaction giúp phân biệt row đã tồn tại, nhưng phải kiểm tra applied result và chấp nhận chi phí điều phối.

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, payload_json
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Trong code dùng `CqlTemplate`, thực thi câu lệnh có arguments và kiểm tra boolean kết quả của *conditional* operation:

~~~java
boolean applied = cql.execute(
        "INSERT INTO order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?) IF NOT EXISTS",
        eventId, orderId, eventType, json);

if (!applied) {
    // Row cùng eventId đã tồn tại; kiểm tra nội dung nếu cần.
}
~~~

Với CQL LWT, `applied=false` cho biết điều kiện không được đáp ứng; **không tự khẳng định đó là duplicate hợp lệ**. Nếu row đã tồn tại nhưng có payload khác, cần ghi conflict/quarantine để điều tra.

## 15. Session lifecycle, security và vận hành cluster

### 15.1. Session sống lâu nhưng connection có thể phục hồi

`CqlSession` quản lý nhiều kết nối/nodes. Khi một node tạm lỗi, driver có thể đổi routing/coordinator hoặc khôi phục connections theo policy. Điều này **không đồng nghĩa** mọi request đang chờ được tiếp tục thành công hoặc caller không cần retry.

**Quy tắc triển khai:**

1. Mở session khi khởi động hoặc khi Spring container tạo bean; tái sử dụng cho các operations.
2. Không gọi `session.close()` trong DAO, RowMapper hoặc service activator sau mỗi message.
3. Đảm bảo owner đóng session khi ứng dụng shutdown, có cách drain in-flight work nếu cần.
4. Không dùng `USE keyspace` thay đổi context của shared session theo yêu cầu mỗi request.
5. Không tạo pool `CqlSession` thủ công bằng hàng trăm bean để “tăng tốc” mà chưa đo driver/cluster metrics.
6. Không đóng một `DefaultBridgedReactiveSession` tùy ý nếu nó đang dùng cùng driver session với các beans khác.

### 15.2. Secrets và quyền truy cập

Trong production, `CqlSession` cần authentication/TLS theo yêu cầu cluster. Các thông tin này phải đến từ hệ thống secrets/environment configuration được quản lý, không hard-code trong Java hoặc log.

Sử dụng Cassandra role có quyền tối thiểu trên keyspace/table mà ứng dụng cần. Một read-only diagnostics service không nên có quyền `DROP TABLE`, `TRUNCATE` hoặc modify schema.

Không dùng tên keyspace/table lấy trực tiếp từ header `tenantId` mà không kiểm tra; prepared statements bind **giá trị**, không tự bảo vệ các CQL identifiers nếu bạn nối tên bảng/cột từ input. Với multi-tenancy, dùng allowlist và authorization theo service identity.

### 15.3. Observability theo từng lớp

| Lớp | Metric/log cần theo dõi | Ý nghĩa |
|---|---|---|
| Spring Integration | Message rate, handler duration, error channel | Flow có nhận đúng lượng công việc không? |
| CqlTemplate/DAO | Operation type, latency, exception type | Query nào đang gây lỗi hoặc chậm? |
| Driver `CqlSession` | In-flight requests, timeouts, connections, retry count | Có saturation/reconnect không? |
| Cassandra cluster | Read/write latency, compaction, tombstones, pending tasks | Backend có quá tải/hot partition không? |
| Source JMS/Kafka | Queue depth, oldest message age, offset lag | Lỗi Cassandra có gây backlog không? |
| Nghiệp vụ | Duplicate `eventId`, conflicting payload, applied=false | Replay có giữ tính đúng đắn không? |

`CqlTemplate` có thể log CQL ở mức DEBUG theo logger của nó. **Không bật verbose CQL logging trên production mà không kiểm soát dữ liệu nhạy cảm**: statement và bind values có thể liên quan PII, token hoặc thông tin tài chính. Dùng tracing/metrics với labels giới hạn cardinality, không dùng `eventId` làm metric label cho từng sự kiện nếu hệ đo có nguy cơ bùng nổ series.

### 15.4. Vận hành schema

Tạo keyspace và table có chủ đích qua migration/provisioning, không để mọi instance khởi động tự DROP/CREATE. Với Spring Data manual config, chọn `SchemaAction.NONE` khi schema do hệ migration quản lý. Khi thay bảng/mapping, triển khai theo thứ tự tương thích giữa producer, consumer và database; không đổi CQL column names trên một nửa các service rồi kỳ vọng `RowMapper` tự biết.

## 16. Bảng xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/khắc phục |
|---|---|---|
| `No bean of type CqlSession` | Chưa cấu hình driver/Boot auto-config không chạy | Dependency, properties, bean definitions |
| `No bean of type SessionFactory` | Có CqlSession nhưng thiếu wrapper cho CqlTemplate | Tạo `DefaultSessionFactory` hoặc cấu hình `SessionFactoryFactoryBean` |
| Trùng bean SessionFactory | Tạo cả default và mapping factory không qualifier | Chọn một hoặc dùng `@Qualifier` |
| Kết nối thất bại vì local DC | `datacenter1` khác metadata thực | Kiểm tra local-datacenter, contact-points, port |
| Keyspace không tồn tại | Tạo bean trước khi provision schema | Migration/provisioning trước khi start |
| Query báo invalid table | Sai keyspace hoặc table naming | Kiểm tra `SELECT` có qualified table name đúng |
| `CqlTemplate` compile lỗi khi truyền vào CassandraMessageHandler | Handler cần `ReactiveCassandraOperations` | Dùng reactive template/operations hoặc viết Service Activator |
| CQL INSERT thành công nhưng dữ liệu bị thay sau retry | Cassandra upsert cùng primary key | Giữ payload bất biến, version/LWT nếu cần |
| `queryForObject` lỗi về kích thước | Query trả không đúng một row/column | Dùng query + RowMapper hoặc điều chỉnh query/key |
| Codec error | Java value không khớp type CQL | Kiểm tra schema và driver codecs |
| Blocking trong WebFlux | CqlTemplate chạy trên event-loop | Dùng ReactiveCqlTemplate, reactive flow |
| Reactive Mono tạo nhưng không có dữ liệu | Không có subscription | Trả publisher cho framework hoặc có subscriber được quản lý |
| Timeout nhưng row đã có | Outcome không chắc sau mạng lỗi | Retry idempotent, kiểm tra state |
| JMS không redeliver khi Cassandra lỗi | Listener đã ack hoặc async boundary | Kiểm tra DirectChannel/transaction/error flow |
| DLQ tăng dù Cassandra đã phục hồi | Poison message hoặc contract không hợp lệ | Phân loại và replay có kiểm soát |
| Throughput giảm sau tăng concurrency | Quá nhiều queries in-flight, hot partition | Giảm tải, đo p95, partition design |
| Khởi động chậm hoặc nhiều connection | Tạo session trên mỗi call/bean | Tái sử dụng session singleton |
| CQL log lộ dữ liệu | DEBUG enabled quá rộng | Giới hạn logs, masking và quyền truy cập |

### Checklist trước khi đưa vào production

1. Xác định ứng dụng dùng Spring Boot auto-config hay Java-created session, không có bean trùng vô ý.
2. Xác định keyspace, contact points, local DC, replication, auth/TLS và quyền Cassandra role.
3. Chọn `CqlTemplate` imperative hay `ReactiveCqlTemplate`/`ReactiveCassandraTemplate` phù hợp luồng thực thi.
4. Dùng bind parameters cho mọi giá trị lấy từ payload/header; không tự ghép user CQL.
5. Kiểm tra query theo partition key, page size, consistency và retry/timeout policy.
6. Phân biệt lỗi transient với invalid schema/permission/codec error.
7. Có business `eventId`, cơ chế tránh duplicate/conflicting payload và ordering nếu cần.
8. Xác định đường exception/ack từ Spring Integration tới nguồn JMS/Kafka/HTTP.
9. Có metrics in-flight, p99, cluster load, source backlog và audit replay.
10. Thử restart, broker failure, Cassandra outage và shutdown khi còn work đang chạy.

## 17. Bài thực hành: dựng CqlTemplate và session factory

**Môi trường:** một Cassandra cluster/test container dành riêng cho lab, Java 17+, Spring Data Cassandra và Spring Integration 6+ (hoặc phiên bản tương thích). Dùng keyspace `shop_integration` và table `order_event` trong mục 5. Không thực hiện các thao tác phá dữ liệu trên production.

### Bài A — Một CqlSession, một DefaultSessionFactory

1. Tạo driver `CqlSession` bằng Spring Boot auto-config hoặc Java bean ở mục 3.
2. Tạo `DefaultSessionFactory(cqlSession)` và `CqlTemplate(sessionFactory)` theo mục 4.
3. Log **identity** của session được inject ở hai services trong lab, xác nhận cùng instance được tái sử dụng.
4. Thực hiện một SELECT và một INSERT; xác minh session vẫn usable sau hai thao tác.
5. Stop Spring context, kiểm tra driver session được đóng/clean up đúng lifecycle.

**PASS:** Không tạo/đóng session trên mỗi message; không có nhiều bean SessionFactory gây ambiguity.

### Bài B — CqlSessionFactoryBean thay cho driver @Bean

1. Dừng cấu hình driver trực tiếp, thay bằng `CqlSessionFactoryBean`.
2. Inject bean type `CqlSession` vào `CqlTemplate`/`DefaultSessionFactory`, **không gọi `getObject()` thủ công**.
3. Kiểm tra tên bean factory và cơ chế `&beanName` ở môi trường Spring context.
4. Cố ý đặt sai `local-datacenter` trong môi trường test, quan sát driver startup/connect failure.
5. Sửa lại và xác minh keyspace tồn tại, session có quyền SELECT/INSERT.

**PASS:** Hiểu rõ `FactoryBean<CqlSession>` khác `SessionFactory`.

### Bài C — Prepared statements và RowMapper

1. Gọi `writer.save("evt-3001", "ORD-3001", "OrderPaid", json)`.
2. Query bằng `CqlTemplate.queryForObject(...)` cho cột `event_type` theo `eventId`.
3. Query bằng `OrderEventCqlReader.findById(...)` trả DTO hoặc `Optional.empty()` nếu không có row.
4. Dùng chuỗi test chứa dấu nháy trong giá trị payload, xác minh giá trị được bind chứ không thành CQL syntax.
5. Thử sai kiểu `eventId`/`processed_at` để quan sát exception translation/codec errors.

~~~sql
SELECT event_id, order_id, event_type, payload_json
FROM shop_integration.order_event
WHERE event_id = 'evt-3001';
~~~

**PASS:** SELECT trả đúng dữ liệu; mapping field rõ; query không nối dữ liệu client thành CQL.

### Bài D — ReactiveCqlTemplate và subscription

1. Tạo bean `ReactiveCqlTemplate(new DefaultBridgedReactiveSession(cqlSession))`.
2. Gọi `reactiveDao.save(...)` nhưng **chưa subscribe**; xác nhận hiểu lazy execution, không dựa vào giá trị method return.
3. Cho một subscriber/framework consume `Mono<Boolean>`, kiểm tra dữ liệu được ghi.
4. Thử một SELECT trả `Mono<String>`; xử lý empty/result/error đúng.
5. Ngắt Cassandra trong lúc operation đang chạy, quan sát error signal và retry budget.

**PASS:** Không có operation bị bỏ quên vì thiếu subscription; lỗi async không bị nuốt.

### Bài E — Tích hợp Spring Integration

1. Tạo `OrderEventCqlWriter` và `SavePaidOrderService` với `@ServiceActivator(inputChannel="paidEventsForCassandra")`.
2. Phát Spring Message chứa `PaidOrderEvent` vào `DirectChannel`; kiểm tra row Cassandra.
3. Thay bằng Java DSL ở mục 11.2, **không chạy song song cả hai endpoint** trên cùng channel.
4. Ngắt Cassandra, quan sát exception trên đường DirectChannel.
5. Đưa `ExecutorChannel` vào trước handler và đối chiếu khác biệt về thời điểm exception xuất hiện.
6. Đối chiếu với `CassandraMessageHandler` sử dụng `ReactiveCassandraOperations`; không truyền CqlTemplate vào constructor của handler có sẵn.

**PASS:** Hiểu luồng imperative service activator khác endpoint Cassandra reactive có sẵn và nơi lỗi đi tới.

### Bài F — Redelivery, timeout và idempotency

1. Gửi sự kiện `evt-3001` từ JMS transacted tới handler dùng blocking CqlTemplate.
2. Sau Cassandra write, mô phỏng lỗi trước JMS commit; cho broker redeliver cùng event.
3. Xác nhận cùng key `eventId` không sinh thêm một event độc lập; phát hiện payload thay đổi nếu cùng ID nhưng nội dung xung đột.
4. Thử conditional CQL `IF NOT EXISTS`, so sánh `applied=true`/`false` với row tồn tại.
5. Đặt timeout và backoff hợp lý; mô phỏng Cassandra unavailable rồi khôi phục, đo số attempts.
6. Quan sát rằng chuyển sang async channel làm lỗi Cassandra không còn tự rollback JMS gốc sau khi source đã commit.

**PASS:** Định nghĩa được chính xác ranh giới ack/commit và không dùng timeout làm bằng chứng “chưa ghi”.

### Ma trận kiểm chứng cuối cùng

| Trường hợp | Kết quả yêu cầu |
|---|---|
| `CqlSession` singleton | Một session được tái sử dụng, đóng đúng lúc shutdown |
| `SessionFactory` | `DefaultSessionFactory` trả về đúng driver session |
| `CqlSessionFactoryBean` | FactoryBean tạo `CqlSession`, không bị nhầm là SessionFactory |
| `CqlTemplate` | Chạy CQL blocking và bind values |
| `RowMapper` | Map row đúng kiểu/cột |
| `ReactiveCqlTemplate` | Mono/Flux được subscribe và lỗi được quan sát |
| `CassandraMessageHandler` | Nhận `ReactiveCassandraOperations`, không nhận CqlTemplate |
| Exception translation | Lỗi CQL trở thành đường lỗi ứng dụng rõ ràng |
| Consistency và timeout | Không suy ra exactly-once từ một reply thành công hoặc timeout |
| Idempotency | Cùng event ID qua replay không gây tác động nghiệp vụ sai |
| Security và lifecycle | Không lộ credentials, không đóng session theo request |

**Không thể kiểm chứng session lifecycle, Cassandra consistency, timeout, prepared statement behavior hay reconnect chỉ bằng mock `CqlTemplate`.** Dùng Cassandra thật hoặc test container tương ứng; riêng JMS acknowledgment cần thêm broker JMS test để thấy redelivery/rollback.

## 18. Câu hỏi tự đánh giá

1. Vì sao `CqlTemplate` không phải một Spring Integration outbound adapter?
2. `CqlSession` khác `SessionFactory` như thế nào?
3. `CqlSessionFactoryBean` trả về object loại gì, và `&beanName` dùng để làm gì?
4. `DefaultSessionFactory` có tự tạo một pool Cassandra connections riêng không?
5. Khi nào `SessionFactoryFactoryBean` hữu ích hơn `DefaultSessionFactory`?
6. Vì sao không nên gọi `CqlSession.close()` sau mỗi INSERT?
7. Sự khác nhau giữa `CqlTemplate` và `CassandraTemplate` về object mapping là gì?
8. `CqlTemplate.execute(String, Object...)` bảo vệ các bind values bằng cách nào?
9. Tại sao nối `eventId` vào chuỗi CQL không được khuyến nghị?
10. `RowMapper` và `ResultSetExtractor` phục vụ hai cách xử lý kết quả khác nhau thế nào?
11. Vì sao `queryForObject` không phù hợp để lấy cả một partition lớn?
12. ReactiveCqlTemplate cần điều kiện gì để một `Mono` thực sự chạy I/O?
13. Khi nào nên tránh `Mono.block()`?
14. `ReactiveCqlTemplate` khác `ReactiveCassandraTemplate` về object mapping ở đâu?
15. Tại sao `CassandraMessageHandler` yêu cầu `ReactiveCassandraOperations` thay vì CqlTemplate?
16. Một Cassandra timeout có chứng minh INSERT đã thất bại hoàn toàn không?
17. Cassandra upsert cùng `event_id` khác unique insert RDBMS như thế nào?
18. `IF NOT EXISTS` giải quyết được điều gì và có chi phí gì?
19. Vì sao `DirectChannel` và `ExecutorChannel` tạo ra sự khác nhau về đường lỗi JMS→Cassandra?
20. Khi có nhiều keyspaces/tenants, tại sao đổi session keyspace bằng `USE` theo từng request không an toàn?

## 19. Tài liệu tham khảo chính thức

- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlTemplate`, callbacks, SessionFactory và exception translation.
- [Spring Data Cassandra — Connecting to Cassandra with Spring](https://docs.spring.io/spring-data/cassandra/reference/cassandra/configuration.html): Java/XML configuration, `CqlSessionFactoryBean`, `SessionFactoryFactoryBean` và `AbstractCassandraConfiguration`.
- [Spring Data Cassandra — Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html): binder, caching và `PreparedStatementCreator`.
- [Spring Data Cassandra — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCqlTemplate`, `ReactiveCassandraTemplate`, subscription và error signals.
- [Spring Data Cassandra API — CqlTemplate](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/CqlTemplate.html): constructor, `execute`, `queryForObject`, `query` và callbacks.
- [Spring Data Cassandra API — DefaultSessionFactory](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/session/DefaultSessionFactory.html): wrapper dùng chung `CqlSession`.
- [Spring Data Cassandra API — CqlSessionFactoryBean](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/config/CqlSessionFactoryBean.html): lifecycle Spring FactoryBean tạo driver session.
- [Spring Data Cassandra API — ReactiveCqlTemplate](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/ReactiveCqlTemplate.html): Mono/Flux và reactive operations.
- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, outbound adapter/gateway và yêu cầu `ReactiveCassandraOperations`.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL, replication, consistency, data modeling, LWT và vận hành cluster.

**Ghi nhớ:** `CqlSessionFactoryBean` tạo driver `CqlSession`; `SessionFactory` cung cấp session đó cho Spring Data; `CqlTemplate` dùng session để chạy **CQL blocking** với callback, prepared statements và exception translation. Khi cần reactive, dùng `ReactiveCqlTemplate` hoặc object-mapped `ReactiveCassandraTemplate`; còn Spring Integration `CassandraMessageHandler` nhận **ReactiveCassandraOperations**, không nhận CqlTemplate. Luồng đáng tin cậy cần session lifecycle đúng, query theo partition key, bind values, kiểm soát timeout/retry/idempotency và ranh giới acknowledgment với hệ thống nguồn.




