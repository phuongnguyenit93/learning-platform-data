# Tích hợp Spring Data, mapping khóa và kiểm thử truy vấn

## 1. Mục tiêu và bài toán thực hành

Bài thực hành tổng hợp này sử dụng **Apache Cassandra** như một cơ sở dữ liệu wide-column phân tán, kết hợp **Spring Boot, Spring Data Cassandra và Testcontainers** để xây dựng, truy vấn và kiểm thử một chức năng Java hoàn chỉnh. Điểm trọng tâm là: **thiết kế bảng theo truy vấn trước, ánh xạ chính xác partition key/clustering key, rồi xác nhận bằng kiểm thử tích hợp trên Cassandra thật**.

Sau khi hoàn thành, bạn cần làm được các việc sau:

1. Từ một yêu cầu đọc cụ thể, chọn khóa phân vùng và khóa phân cụm phù hợp, giải thích vì sao truy vấn không cần quét toàn bảng.
2. Viết CQL để tạo keyspace, bảng và truy vấn theo đúng primary key; hiểu thứ tự sắp xếp và giới hạn của Cassandra.
3. Ánh xạ composite primary key bằng `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@PrimaryKey` và `@Table` của Spring Data Cassandra.
4. Tạo repository có truy vấn CQL tường minh, gọi repository từ service Java và kiểm tra các điều kiện đầu vào.
5. Dùng Testcontainers chạy kiểm thử tạo/đọc/xóa bản ghi, đúng thứ tự clustering, đúng tenant và đúng giới hạn thời gian.
6. Phân biệt điều được test một nút chứng minh với các vấn đề vận hành phân tán như replication, consistency level, compaction, repair và lỗi mạng.

**Tình huống:** Một ứng dụng quản lý đơn hàng ghi các sự kiện của đơn, chẳng hạn `CREATED`, `PAID`, `SHIPPED`, để màn hình chi tiết đơn hiển thị **20 sự kiện mới nhất**. Nhiều tenant dùng chung cụm Cassandra; mọi truy vấn phải giữ ranh giới tenant.

Hai truy vấn quan trọng nhất:

- **Q1:** “Cho tenant T và đơn O, lấy N sự kiện mới nhất theo thời gian giảm dần.”
- **Q2:** “Cho tenant T và đơn O, lấy N sự kiện xảy ra từ mốc thời gian S trở đi.”

Không có yêu cầu tìm mọi sự kiện theo trạng thái `PAID` trên toàn bộ tenant. Một truy vấn như vậy sẽ cần **bảng khác thiết kế theo truy vấn**, hoặc hệ tìm kiếm/phân tích chuyên dụng.

### Kiến trúc nhỏ cho bài lab

~~~mermaid
flowchart LR
    Client["Client / API"] --> Service["EventTimelineService"]
    Service --> Repo["OrderEventRepository"]
    Repo --> Mapping["Spring Data Cassandra mapping"]
    Mapping --> DB[("Apache Cassandra")]
    Test["JUnit + Testcontainers"] --> Service
    Test --> Repo
    Test --> DB
~~~

Lưu ý: Spring Data Cassandra là lớp mapping/repository trên **CQL và Java Driver**, không thay đổi quy tắc phân vùng hay biến Cassandra thành một cơ sở dữ liệu quan hệ có join tùy ý.

## 2. Chọn mô hình dữ liệu từ truy vấn

Đối với Q1 và Q2, partition của một dòng sự kiện được xác định bởi **cặp (tenant_id, order_id)**; các dòng trong cùng partition được sắp xếp theo `occurred_at` giảm dần. Thêm `event_id` vào clustering key để phân biệt hai sự kiện có cùng timestamp.

| Thành phần | Cột | Ý nghĩa |
| --- | --- | --- |
| Partition key | `(tenant_id, order_id)` | Đưa tất cả sự kiện của một đơn, thuộc đúng tenant, vào cùng phân vùng logic |
| Clustering column 1 | `occurred_at DESC` | Hỗ trợ đọc các sự kiện mới nhất và lọc theo ngưỡng thời gian |
| Clustering column 2 | `event_id ASC` | Phân biệt sự kiện trùng thời điểm, tạo thứ tự ổn định trong cùng timestamp |
| Cột thường | `event_type`, `amount` | Dữ liệu hiển thị, không thể dùng tùy ý làm điều kiện lọc hiệu quả |

Mô hình chính:

~~~sql
CREATE KEYSPACE IF NOT EXISTS workshop
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS workshop.events_by_order (
    tenant_id uuid,
    order_id uuid,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**Vì sao có hai cặp ngoặc quanh partition key?** Trong `PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)`, cặp ngoặc **bên trong** biểu diễn partition key **gồm hai cột**. Cặp ngoặc ngoài bao toàn bộ primary key. Nếu viết `PRIMARY KEY (tenant_id, order_id, occurred_at, event_id)`, Cassandra hiểu chỉ `tenant_id` là partition key, các cột còn lại là clustering key: đây là thiết kế khác hoàn toàn và dễ tạo partition quá lớn cho một tenant.

Ví dụ truy vấn hợp lệ:

~~~sql
-- Q1: Đọc đúng một partition, theo thứ tự clustering đã khai báo.
SELECT tenant_id, order_id, occurred_at, event_id, event_type, amount
FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND order_id = 00000000-0000-0000-0000-000000000002
LIMIT 20;

-- Q2: Đầy đủ partition key, tiếp theo là điều kiện range trên
-- clustering column đầu tiên.
SELECT *
FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND order_id = 00000000-0000-0000-0000-000000000002
  AND occurred_at >= '2026-11-01T00:00:00Z'
LIMIT 20;
~~~

Các truy vấn này không dùng `ALLOW FILTERING` vì Cassandra có thể định vị partition rồi đọc theo thứ tự clustering. Ngược lại, `SELECT * FROM events_by_order WHERE event_type = 'PAID'` không có partition key và không được thiết kế để chạy bằng bảng này.

**Giới hạn quan trọng:** partition key gắn với một đơn giúp đọc lịch sử đơn hiệu quả, nhưng một đơn có thể tích lũy quá nhiều sự kiện. Nếu cần giữ hàng triệu sự kiện cho cùng đơn, cân nhắc **time bucket** (ví dụ `event_month` trong partition key), TTL theo yêu cầu lưu giữ và cơ chế đọc nhiều bucket. Không đưa time bucket vào bài lab khi chưa có nhu cầu, vì nó làm phức tạp đường truy vấn.

## 3. Tạo project Java và chạy Cassandra cục bộ

Ví dụ dùng **Java 17, Spring Boot 3.3.4, Spring Data Cassandra do Spring Boot quản lý phiên bản, Testcontainers 1.20.1 và Cassandra 4.1** như một bộ phiên bản minh họa nhất quán. Khi sử dụng phiên bản khác, kiểm tra tương thích của Java Driver, Spring Data, Testcontainers và tên property tương ứng. Máy cần có JDK 17+, Maven và Docker Engine đang hoạt động để chạy kiểm thử tích hợp.

Cấu trúc gợi ý:

~~~text
cassandra-practice/
├── pom.xml
├── src/main/java/com/example/cassandraworkshop/
│   ├── CassandraPracticeApplication.java
│   ├── domain/OrderEventKey.java
│   ├── domain/OrderEvent.java
│   ├── repository/OrderEventRepository.java
│   └── service/EventTimelineService.java
├── src/main/resources/application.yml
├── src/test/java/com/example/cassandraworkshop/
│   └── OrderEventRepositoryIntegrationTest.java
└── src/test/resources/schema.cql
~~~

### 3.1. Maven dependencies

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>cassandra-practice</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <testcontainers.version>1.20.1</testcontainers.version>
    </properties>

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
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${testcontainers.version}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>cassandra</artifactId>
            <version>${testcontainers.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot starter cung cấp Spring Data Cassandra, driver CQL và auto-configuration. Không cần thêm một thư viện ORM kiểu JPA cho bảng Cassandra.

### 3.2. Chuẩn bị cluster một nút để chạy ứng dụng

Chạy bằng terminal đã cài Docker:

~~~bash
docker run --name cassandra-lab \
  -e CASSANDRA_DC=datacenter1 \
  -p 9042:9042 \
  -d cassandra:4.1

docker exec -it cassandra-lab cqlsh
~~~

Đợi Cassandra sẵn sàng nhận kết nối trước khi mở `cqlsh`; nếu lệnh kết nối thất bại vì máy chủ đang khởi động, chạy lại lệnh `docker exec` sau khi container khỏe. Dán đoạn `CREATE KEYSPACE` và `CREATE TABLE` ở mục 2 vào `cqlsh`.

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: cassandra-practice
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: workshop
    schema-action: NONE
~~~

`schema-action: NONE` thể hiện chủ đích **quản lý schema bằng CQL/migration**, không để ứng dụng tự ý tạo/xóa bảng khi khởi động. Keyspace cần tồn tại trước khi kết nối. Đối với môi trường production, không giữ `SimpleStrategy`/replication factor 1; hãy chọn `NetworkTopologyStrategy`, replication factor theo datacenter và consistency level theo yêu cầu.

`CassandraPracticeApplication.java`:

~~~java
package com.example.cassandraworkshop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CassandraPracticeApplication {
    public static void main(String[] args) {
        SpringApplication.run(CassandraPracticeApplication.class, args);
    }
}
~~~

## 4. Ánh xạ composite primary key trong Spring Data Cassandra

Đây là phần quan trọng nhất của lab. Khóa Java phải phản ánh **cả thứ tự lẫn vai trò** của từng cột ở CQL. Không thể dùng một `UUID id` thay cho khóa bốn cột rồi mong repository tự tra đúng partition.

`domain/OrderEventKey.java`:

~~~java
package com.example.cassandraworkshop.domain;

import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderEventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    @PrimaryKeyColumn(
        name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public OrderEventKey() {
    }

    public OrderEventKey(
            UUID tenantId, UUID orderId, Instant occurredAt, UUID eventId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID tenantId) { this.tenantId = tenantId; }

    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID orderId) { this.orderId = orderId; }

    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant occurredAt) { this.occurredAt = occurredAt; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID eventId) { this.eventId = eventId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderEventKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(orderId, that.orderId)
            && Objects.equals(occurredAt, that.occurredAt)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId, occurredAt, eventId);
    }
}
~~~

Các annotation thực hiện đúng vai trò sau:

| Annotation/thuộc tính | Tác dụng | Lỗi thường gặp |
| --- | --- | --- |
| `@PrimaryKeyClass` | Đánh dấu object chứa composite key | Chỉ để `@PrimaryKey` lên UUID đơn lẻ trong entity |
| `type = PARTITIONED` | Cột thuộc partition key | Đánh dấu `order_id` là `CLUSTERED` dù CQL dùng partition key ghép |
| `type = CLUSTERED` | Cột sắp xếp trong cùng partition | Nhầm thứ tự clustering giữa `occurred_at` và `event_id` |
| `ordinal` | Xác định thứ tự các cột trong key | Đảo ordinal khiến mapping khác thiết kế CQL |
| `ordering` | Phản ánh hướng thứ tự clustering | Để tăng dần trong mapping khi bảng dùng `DESC` |
| `equals/hashCode` | So sánh khóa Java ổn định | Chỉ so `orderId`, gây nhầm tenant/sự kiện |

`domain/OrderEvent.java`:

~~~java
package com.example.cassandraworkshop.domain;

import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_order")
public class OrderEvent {

    @PrimaryKey
    private OrderEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("amount")
    private BigDecimal amount;

    public OrderEvent() {
    }

    public OrderEvent(OrderEventKey key, String eventType, BigDecimal amount) {
        this.key = key;
        this.eventType = eventType;
        this.amount = amount;
    }

    public OrderEventKey getKey() { return key; }
    public void setKey(OrderEventKey key) { this.key = key; }

    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
}
~~~

Giá trị `@PrimaryKey` là **toàn bộ `OrderEventKey`**. Trong Cassandra, `INSERT` với **cùng primary key** sẽ cập nhật/upsert cùng một hàng; nếu muốn hai sự kiện có cùng `occurredAt` cùng tồn tại thì `eventId` phải khác nhau. Đồng thời, timestamp của CQL có độ chính xác mili giây; tránh dựa vào phần nano của `Instant` làm định danh duy nhất.

Thời điểm sự kiện phải là `occurredAt` theo nghiệp vụ; không dùng `UUID.randomUUID()` làm vật thay thế cho thứ tự thời gian. `eventId` là thành phần phân biệt, chỉ tạo trật tự ổn định **khi thời điểm trùng nhau**, không có nghĩa sắp xếp theo thời gian thực của các sự kiện cùng timestamp.

## 5. Repository: viết truy vấn minh bạch với CQL

`repository/OrderEventRepository.java`:

~~~java
package com.example.cassandraworkshop.repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.example.cassandraworkshop.domain.OrderEvent;
import com.example.cassandraworkshop.domain.OrderEventKey;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.stereotype.Repository;

@Repository
public interface OrderEventRepository
        extends CassandraRepository<OrderEvent, OrderEventKey> {

    @Query("SELECT * FROM events_by_order " +
           "WHERE tenant_id = ?0 AND order_id = ?1 LIMIT ?2")
    List<OrderEvent> findRecent(UUID tenantId, UUID orderId, int limit);

    @Query("SELECT * FROM events_by_order " +
           "WHERE tenant_id = ?0 AND order_id = ?1 " +
           "AND occurred_at >= ?2 LIMIT ?3")
    List<OrderEvent> findSince(
            UUID tenantId, UUID orderId, Instant since, int limit);
}
~~~

Trong `@Query`, `?0`, `?1`, `?2`, `?3` là **tham số bind theo chỉ số từ 0** do Spring Data xử lý, tránh ghép chuỗi dữ liệu người dùng vào CQL. Cả Q1 và Q2 đều truyền đầy đủ **hai thành phần partition key**. Dữ liệu đọc theo `CLUSTERING ORDER BY` đã khai báo trong schema; `LIMIT` giới hạn số hàng trả về từ Cassandra.

Đối với các điều kiện lớn hơn một partition, không tự suy rằng phương thức repository có thể thực hiện join, group by đa partition hoặc lọc động giống JPA. Tạo bảng mới phục vụ truy vấn hoặc đưa dữ liệu sang hệ thống tìm kiếm/phân tích khi yêu cầu đòi hỏi.

### Tầng service

`service/EventTimelineService.java`:

~~~java
package com.example.cassandraworkshop.service;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import com.example.cassandraworkshop.domain.OrderEvent;
import com.example.cassandraworkshop.domain.OrderEventKey;
import com.example.cassandraworkshop.repository.OrderEventRepository;
import org.springframework.stereotype.Service;

@Service
public class EventTimelineService {
    private final OrderEventRepository repository;

    public EventTimelineService(OrderEventRepository repository) {
        this.repository = repository;
    }

    public OrderEvent record(
            UUID tenantId,
            UUID orderId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            BigDecimal amount) {

        var key = new OrderEventKey(
            Objects.requireNonNull(tenantId),
            Objects.requireNonNull(orderId),
            Objects.requireNonNull(occurredAt),
            Objects.requireNonNull(eventId));

        if (eventType == null || eventType.isBlank()) {
            throw new IllegalArgumentException("eventType is required");
        }
        return repository.save(new OrderEvent(key, eventType, amount));
    }

    public List<OrderEvent> recent(UUID tenantId, UUID orderId, int limit) {
        if (tenantId == null || orderId == null) {
            throw new IllegalArgumentException("tenantId/orderId required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        return repository.findRecent(tenantId, orderId, limit);
    }

    public List<OrderEvent> since(
            UUID tenantId, UUID orderId, Instant since, int limit) {
        if (tenantId == null || orderId == null || since == null) {
            throw new IllegalArgumentException("key and since required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }
        return repository.findSince(tenantId, orderId, since, limit);
    }
}
~~~

Ở đây giới hạn 100 bản ghi mỗi lần đọc là chính sách API của ví dụ, không phải giới hạn cứng của Cassandra. Một ứng dụng thực có thể dùng **driver paging state** hoặc `Slice` phù hợp để đọc tuần tự trong cùng partition. Cassandra không cung cấp phân trang theo offset kiểu `OFFSET 1000` giống SQL quan hệ. Paging state là token tiếp diễn cần quản lý an toàn, gắn với query và cấu hình tương ứng.

Đây cũng chưa phải service xử lý **tranh chấp phiên bản**. Nếu nghiệp vụ yêu cầu chống hai writer cùng sửa một trạng thái, cần thiết kế điều kiện ghi (LWT/CAS khi phù hợp) hoặc versioning phía ứng dụng. Việc một event có composite key duy nhất không làm mọi nghiệp vụ trên Cassandra trở thành transaction ACID đa partition.

## 6. Testcontainers: kiểm thử trên Cassandra thực

Unit test dùng mock repository chỉ kiểm tra lời gọi Java; nó **không** chứng minh mapping key đúng, CQL hợp lệ hay kết quả được sắp theo clustering order. Vì vậy bài lab sử dụng **integration test** với container Cassandra 4.1 thật.

`src/test/resources/schema.cql` dùng cùng schema với môi trường chạy tay:

~~~sql
CREATE KEYSPACE IF NOT EXISTS workshop
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS workshop.events_by_order (
    tenant_id uuid,
    order_id uuid,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Testcontainers khởi động một instance Cassandra độc lập, thực thi `schema.cql`, và cấp **host/port thực** cho Spring Boot qua `@DynamicPropertySource`. Mỗi lần chạy không cần dùng keyspace của Cassandra `cassandra-lab` ở phần trước.

`src/test/java/com/example/cassandraworkshop/OrderEventRepositoryIntegrationTest.java`:

~~~java
package com.example.cassandraworkshop;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.example.cassandraworkshop.domain.OrderEvent;
import com.example.cassandraworkshop.domain.OrderEventKey;
import com.example.cassandraworkshop.repository.OrderEventRepository;
import com.example.cassandraworkshop.service.EventTimelineService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class OrderEventRepositoryIntegrationTest {

    @Container
    static final CassandraContainer<?> cassandra =
        new CassandraContainer<>(DockerImageName.parse("cassandra:4.1"))
            .withInitScript("schema.cql");

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points", cassandra::getHost);
        registry.add("spring.cassandra.port",
                     () -> cassandra.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter",
                     () -> "datacenter1");
        registry.add("spring.cassandra.keyspace-name", () -> "workshop");
        registry.add("spring.cassandra.schema-action", () -> "NONE");
    }

    @Autowired
    private OrderEventRepository repository;

    @Autowired
    private EventTimelineService timeline;

    @Test
    void savesAndFindsByFullCompositeKey() {
        var key = new OrderEventKey(
            UUID.randomUUID(),
            UUID.randomUUID(),
            Instant.parse("2026-11-01T08:00:00Z"),
            UUID.randomUUID());

        repository.save(new OrderEvent(
            key, "CREATED", new BigDecimal("120.50")));

        OrderEvent actual = repository.findById(key).orElseThrow();
        assertThat(actual.getKey()).isEqualTo(key);
        assertThat(actual.getEventType()).isEqualTo("CREATED");
        assertThat(actual.getAmount()).isEqualByComparingTo("120.50");
    }

    @Test
    void returnsLatestEventsInClusteringOrderAndRespectsLimit() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant base = Instant.parse("2026-11-01T09:00:00Z");

        timeline.record(tenant, order, base.minusSeconds(60),
                        UUID.randomUUID(), "CREATED", BigDecimal.TEN);
        timeline.record(tenant, order, base,
                        UUID.randomUUID(), "PAID", BigDecimal.TEN);
        timeline.record(tenant, order, base.plusSeconds(60),
                        UUID.randomUUID(), "SHIPPED", BigDecimal.TEN);

        List<OrderEvent> actual = timeline.recent(tenant, order, 2);
        assertThat(actual)
            .extracting(OrderEvent::getEventType)
            .containsExactly("SHIPPED", "PAID");
    }

    @Test
    void isolatesTenantsEvenWhenOrderIdMatches() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-01T10:00:00Z");

        timeline.record(tenantA, order, at,
                        UUID.randomUUID(), "FROM_A", BigDecimal.ONE);
        timeline.record(tenantB, order, at,
                        UUID.randomUUID(), "FROM_B", BigDecimal.ONE);

        assertThat(timeline.recent(tenantA, order, 10))
            .extracting(OrderEvent::getEventType)
            .containsExactly("FROM_A");
        assertThat(timeline.recent(tenantB, order, 10))
            .extracting(OrderEvent::getEventType)
            .containsExactly("FROM_B");
    }

    @Test
    void filtersWithinPartitionByClusteringTime() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant cutoff = Instant.parse("2026-11-01T10:00:00Z");

        timeline.record(tenant, order, cutoff.minusSeconds(1),
                        UUID.randomUUID(), "BEFORE", BigDecimal.ONE);
        timeline.record(tenant, order, cutoff,
                        UUID.randomUUID(), "AT_CUTOFF", BigDecimal.ONE);
        timeline.record(tenant, order, cutoff.plusSeconds(1),
                        UUID.randomUUID(), "AFTER", BigDecimal.ONE);

        assertThat(timeline.since(tenant, order, cutoff, 10))
            .extracting(OrderEvent::getEventType)
            .containsExactly("AFTER", "AT_CUTOFF");
    }

    @Test
    void deletingByFullKeyRemovesOnlyThatEvent() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-01T11:00:00Z");
        OrderEventKey key1 = new OrderEventKey(
            tenant, order, at, UUID.randomUUID());
        OrderEventKey key2 = new OrderEventKey(
            tenant, order, at, UUID.randomUUID());

        repository.save(new OrderEvent(key1, "ONE", BigDecimal.ONE));
        repository.save(new OrderEvent(key2, "TWO", BigDecimal.ONE));
        repository.deleteById(key1);

        assertThat(repository.findById(key1)).isEmpty();
        assertThat(repository.findById(key2)).isPresent();
    }
}
~~~

Chạy test tại thư mục Maven project:

~~~bash
mvn test
~~~

Trong bài này, tên lớp kết thúc bằng `Test`, để Maven Surefire tự nhận và chạy ở pha `test`. Testcontainers tải/chạy image theo môi trường Docker và tạo keyspace/table trước khi Spring kết nối. Nếu Docker không khả dụng, test sẽ không kiểm chứng được tương tác với Cassandra; đó là lỗi môi trường cần giải quyết, không phải lý do thay integration test bằng mock.

### 6.1. Ý nghĩa của từng kiểm thử

| Test | Điều xác nhận | Lỗi mà test giúp phát hiện |
| --- | --- | --- |
| `savesAndFindsByFullCompositeKey` | Mapping đủ bốn cột, giá trị được chuyển đổi đúng | Thiếu khóa, mapping tên cột sai, mất precision/kiểu dữ liệu |
| `returnsLatestEventsInClusteringOrderAndRespectsLimit` | Q1 đọc đúng partition, DESC và LIMIT | Sai hướng clustering, query không sử dụng key |
| `isolatesTenantsEvenWhenOrderIdMatches` | Tenant là thành phần của partition key | Truy vấn chỉ theo order ID dẫn tới trộn dữ liệu tenant |
| `filtersWithinPartitionByClusteringTime` | Q2 áp điều kiện range đúng clustering key | Lọc sai cột/thứ tự, trả sự kiện trước cutoff |
| `deletingByFullKeyRemovesOnlyThatEvent` | DELETE đúng một primary key | Xóa nhầm toàn partition hoặc thiếu thành phần key |

Vì mỗi test sinh `tenantId/orderId` riêng, test không phụ thuộc thứ tự thực thi hoặc việc dọn toàn bảng. Trong một hệ thống kiểm thử lớn, vẫn nên quản lý vòng đời container, kết nối và dữ liệu seed nhất quán.

## 7. Kiểm thử truy vấn thủ công và các phản ví dụ

Sau khi bảng đã có, thử chèn dữ liệu qua `cqlsh`:

~~~sql
INSERT INTO workshop.events_by_order (
    tenant_id, order_id, occurred_at, event_id, event_type, amount
) VALUES (
    00000000-0000-0000-0000-000000000001,
    00000000-0000-0000-0000-000000000002,
    '2026-11-01T09:00:00Z',
    00000000-0000-0000-0000-000000000011,
    'CREATED',
    120.50
);

INSERT INTO workshop.events_by_order (
    tenant_id, order_id, occurred_at, event_id, event_type, amount
) VALUES (
    00000000-0000-0000-0000-000000000001,
    00000000-0000-0000-0000-000000000002,
    '2026-11-01T09:05:00Z',
    00000000-0000-0000-0000-000000000012,
    'PAID',
    120.50
);

SELECT occurred_at, event_type
FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND order_id = 00000000-0000-0000-0000-000000000002
LIMIT 2;
~~~

Kết quả dự kiến theo thứ tự:

~~~text
2026-11-01 09:05:00+0000 | PAID
2026-11-01 09:00:00+0000 | CREATED
~~~

Định dạng timestamp hiển thị phụ thuộc phiên bản `cqlsh`/timezone cấu hình; điều cần kiểm chứng là **sắp xếp PAID trước CREATED**.

### Các truy vấn cần biết vì sao không phù hợp

~~~sql
-- Thiếu một phần partition key ghép: không phục vụ bằng bảng này.
SELECT * FROM workshop.events_by_order
WHERE tenant_id = 00000000-0000-0000-0000-000000000001;

-- Không có partition key, lọc theo cột thường.
SELECT * FROM workshop.events_by_order
WHERE event_type = 'PAID';

-- Lọc trực tiếp theo clustering key mà thiếu partition key.
SELECT * FROM workshop.events_by_order
WHERE occurred_at >= '2026-11-01T00:00:00Z';
~~~

Cassandra sẽ từ chối những truy vấn thiếu điều kiện hỗ trợ, hoặc yêu cầu cơ chế lọc/phân tích khác tùy loại query và phiên bản. **Không thêm `ALLOW FILTERING` chỉ để “làm test xanh”**: kết quả đúng trên vài dòng dữ liệu lab không chứng minh hiệu năng khi có hàng trăm triệu dòng và nhiều partition.

Với một yêu cầu “tìm sự kiện theo customer_id trên toàn tenant”, có thể thiết kế thêm bảng `events_by_customer` với partition key `(tenant_id, customer_id)`, hoặc đưa dữ liệu sang search/analytics. Khi nhân bản dữ liệu sang nhiều bảng, phải xác định rõ luồng cập nhật, retry, idempotency và cách phát hiện lệch dữ liệu; hai lần ghi vào hai partition không mặc nhiên là một giao dịch phân tán nguyên tử.

## 8. Kết hợp consistency level, replication và Java Driver

Spring Data Cassandra thường gọi Java Driver để thực thi statement. Mỗi request hoạt động trong mô hình phân tán của Cassandra; hiểu replication và consistency quan trọng dù API repository chỉ có vài dòng.

### 8.1. Lab một nút và production nhiều replica

Keyspace trong lab dùng `SimpleStrategy`, `replication_factor = 1` để chạy gọn trên một container. Nó **không kiểm chứng** được hành vi replica mất kết nối hay cách quorum hoạt động trong datacenter thật.

Đối với hệ nhiều nút, một ví dụ keyspace theo datacenter:

~~~sql
-- Ví dụ minh họa: chỉ chạy khi cụm thật có DC tên dc1.
CREATE KEYSPACE IF NOT EXISTS app_prod
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Với RF = 3 trong một DC, `LOCAL_QUORUM` cần phản hồi từ đa số replica ở DC đó (2/3). Việc chọn consistency level phải cân bằng độ trễ, tính sẵn sàng và nhu cầu nhất quán; để lập luận về khả năng đọc giá trị ghi gần nhất, phải xét **mức nhất quán cả ghi lẫn đọc**, trạng thái mạng và semantics của Cassandra.

Khi cần đặt consistency level cho một câu CQL riêng biệt, Java Driver hỗ trợ cấu hình trên statement. Ví dụ minh họa dưới đây được đặt ở lớp truy cập hạ tầng sử dụng `CqlSession` trực tiếp:

~~~java
// Đoạn minh họa riêng, không thuộc các file bắt buộc của lab.
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
    "SELECT event_type FROM events_by_order " +
    "WHERE tenant_id = ? AND order_id = ? LIMIT ?");

BoundStatement bound = prepared.bind(tenantId, orderId, 20)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
session.execute(bound);
~~~

`session`, `tenantId`, `orderId` trong snippet là các biến đã được khởi tạo ở lớp gọi. Để cấu hình consistency cho các thao tác Spring Data repository, dùng cơ chế request/session configuration phù hợp với phiên bản Spring Data và driver đã chọn; đừng mặc định mọi lời gọi repository tự dùng `LOCAL_QUORUM`.

### 8.2. TTL, tombstone, compaction và repair

- **TTL:** nếu ứng dụng tự hết hạn lịch sử, có thể ghi với TTL, nhưng phải hiểu dữ liệu hết hạn tạo tombstone và ảnh hưởng truy vấn/compaction. Không dùng TTL khi yêu cầu kiểm toán đòi hỏi lưu lịch sử vĩnh viễn.
- **DELETE:** `repository.deleteById` tạo mutation xóa; không đồng nghĩa dữ liệu lập tức biến mất vật lý khỏi mọi SSTable. Đọc lại phải tuân theo consistency và cơ chế phân giải phiên bản của Cassandra.
- **Compaction:** hợp nhất SSTable, hỗ trợ loại bỏ dữ liệu cũ/tombstone khi điều kiện an toàn cho phép. Chọn chiến lược phù hợp với mô hình dữ liệu và vòng đời ghi; không xem compaction là thao tác sửa mất replica.
- **Repair:** đồng bộ khác biệt giữa replica sau thời gian lỗi/không đồng bộ; phải có lịch vận hành và quan sát tương thích với cấu hình `gc_grace_seconds` và chính sách xóa, tránh rủi ro dữ liệu cũ xuất hiện lại sau tombstone hết hạn.
- **Partition size:** một `orderId` có lịch sử không giới hạn có thể tạo partition lớn; theo dõi số dòng, kích thước thực và tail latency, điều chỉnh bucket/TTL theo yêu cầu.

Đây là các ràng buộc vận hành cần kiểm thử riêng trên cụm nhiều replica. **Không kết luận hệ thống chịu lỗi tốt chỉ vì năm test trên container một nút chạy thành công.**

## 9. Mở rộng kiểm thử cho môi trường thật

Sau phần lab cơ bản, xây dựng các bài test bổ sung:

| Kịch bản | Cách thực hiện | Điều cần quan sát |
| --- | --- | --- |
| Nhiều sự kiện cùng timestamp | Ghi hai event có `occurredAt` bằng nhau nhưng `eventId` khác | Không mất event; thứ tự trong timestamp theo `eventId ASC` |
| Upsert cùng khóa | Ghi lại đúng composite key với `eventType` mới | Chỉ còn một hàng cho key đó, hiểu semantics overwrite |
| Truy vấn giới hạn | Ghi 200 sự kiện cho một đơn, gọi service với limit 20 | Trả tối đa 20, không tải cả partition lên JVM |
| Input không hợp lệ | Gọi `recent(..., 0)`, `recent(..., 101)`, thiếu tenant | Service từ chối trước khi gọi Cassandra |
| Schema lệch | Đổi một tên cột trong mapping hoặc query | Integration test thất bại rõ ràng, phát hiện sớm drift |
| Mất kết nối/timeout | Ngắt mạng tạm thời hoặc dừng nút trong môi trường thử nghiệm phù hợp | Timeout, retry, thông báo lỗi và idempotency của client |
| RF = 3, lỗi một replica | Dựng cụm 3 nút trong cùng DC, kiểm thử các consistency level | Tính sẵn sàng/độ trễ theo quorum và fault scenario |
| Tombstone/repair | Thử DELETE, TTL, gián đoạn replica, phục hồi/repair có kiểm soát | Dữ liệu không hồi sinh; lag, tombstone và repair metrics đúng kỳ vọng |

Không nên viết một test chỉ “assert bằng số lượng cột khai báo” để thay thế kiểm chứng. Các trường hợp hữu ích nhất là những trường hợp **hệ thống thực sự có thể làm sai**: nhầm cột của khóa, nhầm tenant, thay đổi thứ tự clustering, chạy truy vấn tốn kém, hoặc mất an toàn khi retry.

### Kiểm tra tính năng theo thao tác nghiệp vụ

Ví dụ chuỗi thao tác cần xác minh:

1. Tạo đơn `O1` thuộc `T1`, ghi sự kiện `CREATED`.
2. Ghi `PAID` và `SHIPPED` cho `T1/O1` với timestamp tăng dần.
3. Gọi `recent(T1, O1, 2)` → nhận `SHIPPED`, `PAID`.
4. Ghi một sự kiện cho `T2/O1` → truy vấn `T1/O1` không đổi.
5. Gọi `since(T1, O1, timeOfPaid, 10)` → nhận `SHIPPED`, `PAID`, không có `CREATED`.
6. Xóa đúng khóa của `PAID` → chỉ sự kiện đó bị xóa, các sự kiện khác còn nguyên.

**Điều kiện chấp nhận:** kết quả theo đúng partition key và clustering key, không dùng `ALLOW FILTERING`, không trộn tenant, các test tích hợp qua Cassandra thực và schema được quản lý rõ ràng.

## 10. Khi nào cần đổi thiết kế?

| Yêu cầu mới | Tác động thiết kế |
| --- | --- |
| Liệt kê đơn hàng của khách hàng | Cần bảng riêng theo customer hoặc một projection/search index |
| Lọc toàn bộ đơn theo `status` trong nhiều tenant | Bảng riêng theo truy vấn hoặc search engine; không scan `events_by_order` |
| Lịch sử đơn tăng rất lớn | Thêm bucket theo thời gian/giới hạn lưu giữ, cập nhật query và test phân trang |
| Phân tích số đơn theo tháng | Dùng mô hình tổng hợp theo truy vấn hoặc hệ phân tích; dữ liệu event chưa phải báo cáo có thể query ad hoc hiệu quả |
| Ghi sự kiện và trạng thái hiện tại với bảo đảm mạnh | Thiết kế rõ atomicity, sequence/version, idempotency; xem xét giới hạn batch/LWT theo partition |
| Nhiều datacenter, yêu cầu đọc nhất quán | Xác định keyspace replication, local/remote DC, CL, retry và đường khôi phục |

Một thay đổi ở partition key là thay đổi **cách phân phối dữ liệu**, thường không thể sửa bằng cách đổi mỗi annotation Java. Cần tạo bảng mới, backfill, chuyển đường ghi/đọc rồi kiểm chứng và dọn bảng cũ.

## 11. Checklist tự đánh giá

- [ ] Tôi giải thích được vì sao `PRIMARY KEY ((tenant_id, order_id), occurred_at, event_id)` có partition key gồm **hai** cột.
- [ ] Tôi biết vì sao `ordinal = 0,1` ứng với partition và `ordinal = 2,3` ứng với clustering.
- [ ] Tôi đã dùng `@PrimaryKeyClass` và `@PrimaryKey` đúng vị trí; khóa Java có `equals/hashCode`.
- [ ] Repository có truy vấn chỉ định đầy đủ partition key, dùng bind parameter và `LIMIT`.
- [ ] Testcontainers thực thi schema, Spring Boot kết nối được và các test đọc/ghi/sắp xếp/tenant/delete đều chạy.
- [ ] Tôi không dùng `ALLOW FILTERING` để bù cho thiết kế bảng sai truy vấn.
- [ ] Tôi biết test một nút chưa chứng minh tính sẵn sàng khi replica lỗi, và biết vai trò của consistency, repair, compaction, TTL/tombstone.
- [ ] Tôi có thể mô tả thay đổi schema/thiết kế cần làm nếu xuất hiện truy vấn theo customer hoặc báo cáo phân tích.

**Bài học cốt lõi:** Với Spring Data Cassandra, repository và annotation giúp giảm mã kết nối, nhưng **partition key và clustering key trong CQL vẫn quyết định truy vấn có chạy hiệu quả hay không**. Hãy kiểm chứng thiết kế bằng integration test trên Cassandra thật, sau đó kiểm thử phân tán và vận hành bằng môi trường phù hợp với topology production.
