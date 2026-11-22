# Kiểm thử tính năng giao dịch theo khả năng của từng hệ lưu trữ

Trong hệ thống Spring Boot dùng **dữ liệu ngoài SQL**, không thể gắn `@Transactional` rồi mặc định mong mọi hệ lưu trữ có hành vi **commit, rollback, isolation và durability** giống một relational database. MongoDB có multi-document transactions khi topology đáp ứng điều kiện. Redis hỗ trợ `MULTI/EXEC`, `WATCH` và Lua script với tính nguyên tử/thứ tự thực thi nhất định nhưng **không có rollback theo kiểu cơ sở dữ liệu quan hệ**. Neo4j có ACID transactions cho graph. DynamoDB có API transaction giới hạn phạm vi. Couchbase có distributed transactions khi dùng SDK/API thích hợp. Elasticsearch không cung cấp giao dịch nhiều document kiểu ACID; Cassandra có các cơ chế LWT/batch và, ở một số phiên bản/bản triển khai mới, **Accord transactions** với điều kiện kích hoạt riêng.

Vì vậy câu hỏi đúng trước khi viết test không phải “có annotation transaction chưa?” mà là:

1. **Hệ lưu trữ, phiên bản, topology và client cụ thể hỗ trợ tính năng nào?**
2. **Phạm vi nguyên tử là một lệnh, một document, một partition, nhiều documents, nhiều tables hay toàn hệ thống?**
3. **Lỗi giữa chuỗi thao tác có hoàn tác được những phần đã thực thi không?**
4. **Khi concurrent writes hoặc mạng/primary node lỗi, client có quan sát trạng thái commit mơ hồ không?**
5. **Test cần chứng minh bằng chứng gì, bằng công cụ và instance nào gần production?**

Bài Knowledge này cung cấp **ma trận khả năng giao dịch theo từng hệ lưu trữ**, quy trình thiết kế test commit/rollback/conflict/visibility, lỗi phổ biến khi dùng Spring Data, và dự án **Java 17 + Spring Boot 3.5 + MongoDB Testcontainers** có thể chạy để đối chiếu giao dịch nhiều collection với thao tác **không** có transaction.

## 1. Hiểu đúng “giao dịch” trước khi kiểm thử

Các hệ thống gọi “transaction” cho nhiều cơ chế khác nhau:

| Thuộc tính | Câu hỏi cần kiểm | Ví dụ phản ví dụ |
|---|---|---|
| **Atomicity** | Nếu bước thứ hai fail, bước thứ nhất có bị hoàn tác không? | Redis `MULTI/EXEC` không rollback các command đã thực thi nếu command sau gặp lỗi runtime |
| **Consistency** | Invariant nghiệp vụ và ràng buộc của store có luôn được giữ ở boundary được cam kết không? | Một lệnh `SET` Redis riêng lẻ không tự bảo vệ tổng tiền ở nhiều key |
| **Isolation** | Client B có thể thấy trạng thái trung gian, lost update hoặc write skew của Client A không? | `read committed` không tự đồng nghĩa serializable |
| **Durability** | Sau khi báo thành công, dữ liệu có tồn tại sau failover/crash theo write concern và replication policy không? | `EXEC` thành công không tự có nghĩa AOF fsync đã bền vững trên disk |
| **Scope** | Tính chất được bảo đảm trên một key, document, partition, transaction request hay nhiều tài nguyên? | Một document atomic không suy ra atomic trên hai collections |
| **Visibility** | Khi ghi thành công, lúc nào query/search/subscriber khác nhìn thấy kết quả? | Elasticsearch đã index nhưng chưa `refresh` nên search chưa thấy |
| **Idempotency** | Retry request sau timeout có tạo hiệu ứng lặp không? | Ghi order hai lần nếu không có business key/conditional check |

**Atomicity không đồng nghĩa rollback.** Một lệnh Redis script hoặc atomic compare-and-set có thể được xử lý không bị interleave với lệnh client khác, nhưng vẫn **không khôi phục mọi write trước đó** nếu script/transaction gặp lỗi runtime. Ngược lại, một hệ thống có ACID transaction có thể cho phép rollback, nhưng chỉ trong đúng **phạm vi transaction** đã bắt đầu.

**Consistency không phải luôn strong consistency.** Eventual consistency là mô hình mà bản sao có thể thấy trạng thái khác trong một khoảng thời gian; việc một write được server chấp nhận chưa chắc mọi reader hoặc search index quan sát ngay. Test phải nói rõ đọc từ primary/replica, consistency/read concern, refresh hoặc convergence deadline.

## 2. Ma trận khả năng giao dịch theo hệ lưu trữ

| Hệ lưu trữ / API | Đơn vị được bảo đảm | Multi-object transaction / rollback? | Điểm cần chứng minh khi test |
|---|---|---|---|
| **MongoDB** | Một document atomic; transaction có thể trải nhiều documents/collections trên replica set/sharded cluster phù hợp | **Có** với session + transaction manager/API và topology hỗ trợ | Ghi hai collection cùng commit hoặc cùng rollback; lỗi giữa bước; conflict/commit outcome |
| **Redis** `SET`/`INCR` | Một command atomic trong mô hình Redis server | Không tự tạo transaction bao nhiều lệnh | Cùng key không lost update khi dùng atomic increment; TTL và idempotency |
| **Redis** `MULTI/EXEC`, `WATCH` | Commands trong `EXEC` không bị lệnh client khác interleave; WATCH cho optimistic CAS | **Không** rollback các write đã chạy nếu command trong EXEC lỗi runtime | WATCH conflict không thực thi queue; runtime command error có thể để lại partial effects |
| **Redis** Lua/Functions | Script thực thi atomic tương đối với lệnh client khác theo server rules | Không phải rollback transaction SQL | Chặn oversell trong một script; nếu script lỗi sau write, không kết luận auto-rollback |
| **Neo4j** | Transactions đối với node, relationship và Cypher operations | **Có ACID**, nhưng isolation mặc định có giới hạn | Tạo node + relationship, fail và rollback; unique constraint; concurrent updates |
| **DynamoDB** | Write đơn item + conditional writes; `TransactWriteItems` nhóm nhiều item | **Có** qua transaction API với giới hạn request/Region | Condition failure làm toàn transaction không áp dụng; optimistic conflicts; idempotency token |
| **Couchbase** | Atomic operations trên document; multi-document transactions qua SDK/transaction service | **Có** nếu dùng distributed transaction API phù hợp | Hai documents cùng commit/rollback, retried transaction lambda, conflict và query visibility |
| **Cassandra** truyền thống | Atomicity/consistency theo partition/statement và các bảo đảm của batch; LWT conditional CAS | **Không suy ra RDBMS-style rollback từ `LOGGED BATCH`** | `[applied]` từ LWT, conflict, consistency levels; logged batch không đồng nhất multi-row isolation |
| **Cassandra Accord** (nếu version/config hỗ trợ) | Có thể bao nhiều partitions/tables qua transactional mode/API được bật | **Có thể** cung cấp ACID multi-operation | Xác nhận engine/transactional mode, test multi-partition atomicity, conflicts/recovery |
| **Elasticsearch** | Index/update của từng document có concurrency controls; Bulk trả kết quả theo từng item | **Không có multi-document ACID rollback mặc định** | Bulk partial failures, optimistic concurrency `seq_no`/`primary_term`, refresh/search visibility |

**Không dùng bảng này như một cam kết cho mọi version.** Các tính năng thay đổi theo edition, cluster topology, SDK và server release. Ví dụ Cassandra có **LWT/batch** từ lâu, trong khi các cơ chế **Accord** mới chỉ áp dụng khi hệ thống/version hỗ trợ và được cấu hình; không nên khẳng định “Cassandra luôn không có transactions” hoặc “mọi Cassandra hiện tại đều có ACID multi-partition”.

### Cách chọn test theo mục tiêu

- “Một document insert hợp lệ có lưu đúng không?” → repository test một operation.
- “Ghi order và outbox cùng thành công hoặc cùng thất bại?” → **multi-document transaction test trên MongoDB/Neo4j/DynamoDB/Couchbase** với API tương ứng; Redis/Elasticsearch cần thiết kế khác.
- “Chặn hai request mua cùng một item khi stock còn 1?” → **concurrency/conditional write test**, không chỉ rollback test.
- “Ghi thành công nhưng search chưa thấy?” → **visibility/refresh/convergence test**, không đồng nhất với rollback.
- “Đã gửi email rồi database rollback?” → **cross-resource workflow test**; không có phép màu từ một store transaction.

## 3. Phân tầng kiểm thử transaction trong Spring Boot

| Tầng test | Ví dụ | Chứng minh được | Không chứng minh được |
|---|---|---|---|
| **Unit test** với mock repository | `when(repo.save(...))`, throw ở bước hai | Service gọi dependency đúng thứ tự hoặc chuyển lỗi đúng | Server có rollback/ACID thật hay không |
| **Data slice** | `@DataMongoTest`, `@DataNeo4jTest`, `@DataRedisTest` | Repository mapping/query hoặc API store đã nạp trong slice | Transaction trên service proxy nếu service không được import; topology production |
| **Integration test với container** | MongoDB replica set, Redis, Neo4j, Couchbase, Cassandra | Hành vi thực theo server/version và config của test | Độ bền toàn production cluster hoặc failover nếu container đơn |
| **Full Spring Boot context** | `@SpringBootTest` + store container | `@Transactional` service proxy, transaction manager, repository wiring | Những external systems không có trong test |
| **Failure/concurrency test** | 2 clients, network interruption, duplicate request, commit unknown | Isolation/conflicts/retry/recovery theo kịch bản | Mọi lịch thực thi/đường failover nếu chỉ thử một lần |
| **System/deployment test** | Cluster production-like với auth, replication và rolling failover | Durability/visibility và cấu hình thực gần production | Không chứng minh tuyệt đối mọi failure có thể xảy ra |

Một bài `@DataMongoTest` có thể nạp `MongoTemplate` nhưng **không tự tạo `MongoTransactionManager`** theo mong muốn của bạn. Nếu test muốn kiểm `@Transactional` ở service, phải bảo đảm transaction manager bean và Spring proxy thực sự tồn tại trong context, thường qua `@SpringBootTest` hoặc `@Import` có chủ đích. Tương tự, `@DataRedisTest` không biến lệnh Redis thành giao dịch SQL.

**Không dùng H2 để mô phỏng MongoDB transaction**. H2 là relational engine: test rollback trên H2 chỉ chứng minh behavior của H2/JDBC hoặc ORM, không chứng minh MongoDB session, Redis WATCH hay Elasticsearch Bulk. Dùng **server/driver thật hoặc simulator chính thức** đúng đặc tính đang kiểm.

## 4. MongoDB: nhiều documents có thể commit/rollback cùng nhau

MongoDB từ lâu hỗ trợ atomic operations trong phạm vi **một document**; multi-document transactions yêu cầu **client session, server topology và transaction API** phù hợp. Với Spring Data MongoDB imperative, cấu hình `MongoTransactionManager` rồi gọi public service method `@Transactional` qua **Spring proxy**; `MongoTemplate` phát hiện session được ràng buộc với transaction và tham gia.

```text
Spring @Transactional service (proxy)
             |
             v
       MongoTransactionManager
             |
             v
     ClientSession + transaction
             |
         +---+---+
         |       |
         v       v
    orders.insert outbox.insert
         |       |
         +---+---+
             |
       commit / abort
             |
     both visible / neither
```

**Điều kiện cần:**

1. MongoDB server hỗ trợ transaction; trong test dùng **replica set** do `MongoDBContainer` thiết lập, không một standalone mongod không bật replica set.
2. Đăng ký `MongoTransactionManager` cho **imperative `MongoTemplate`**, hoặc `ReactiveMongoTransactionManager` cho **reactive template**. Không tráo hai transaction model.
3. Chạy service qua Spring bean proxy, không gọi `this.placeAtomically(...)` từ một method nội bộ rồi cho rằng proxy luôn bắt được self-invocation.
4. Dùng các MongoTemplate/repository operations tham gia **cùng MongoDatabaseFactory/session**; native driver calls tự tạo session khác có thể ở ngoài transaction.
5. Nên **tạo sẵn collection và index** ngoài transaction để tránh khác biệt/hạn chế khi implicit collection creation xuất hiện trong transaction. Tránh DDL ở giữa kịch bản.
6. Test **commit thành công**, **throw sau write đầu tiên**, **DB lỗi sau write thứ nhất** và **mẫu không có transaction** để phân biệt tác dụng.

**`@Transactional` không có nghĩa Redis, Kafka, HTTP client hay một MongoDB cluster khác tự được gộp cùng transaction.** Transaction manager Mongo quản lý đúng MongoDB resource của nó, không phải distributed XA transaction tự động.

### Imperative vs reactive Mongo

| Code | Transaction manager | Context |
|---|---|---|
| `MongoTemplate`, `MongoRepository`, sync driver | `MongoTransactionManager` | Thread-bound client session của Spring |
| `ReactiveMongoTemplate`, `ReactiveMongoRepository`, reactive driver | `ReactiveMongoTransactionManager` | Reactor Context gắn với Publisher subscription |

Với reactive methods trả `Mono`/`Flux`, phải subscribe trong transactional boundary; **không** gọi `block()` rồi tách lệnh thành nhiều subscriptions ngoài transaction. Spring Data hỗ trợ `TransactionalOperator` để bao một Publisher, tương tự ví dụ R2DBC transaction nhưng dùng **ReactiveMongoTransactionManager**.

**Durability/isolation:** việc transaction commit thành công phải được diễn giải cùng `writeConcern`, `readConcern`, read preference và replication/failover policy. Một test replica set một node **chứng minh atomicity trong môi trường ấy**, không tự kiểm đa node failover hay majority durability thực tế.

## 5. Ví dụ Java 17 đầy đủ: MongoDB Testcontainers commit và rollback

Ta xây một quy trình ghi đơn hàng đơn giản: lưu một `OrderDoc` trong collection `orders` và một `OutboxDoc` trong collection `outbox`. **Outbox record là dữ liệu MongoDB**, không phải message đã gửi qua Kafka/email.

Nếu mọi thao tác thành công, hai document cùng commit. Nếu service throw sau khi ghi order, transaction phải abort và **không còn order hoặc outbox**. Nếu không dùng transaction, cùng lỗi đó để lại **order mồ côi**. Nếu ghi outbox lỗi do trùng `_id`, order mới cũng phải rollback.

Ví dụ dùng **Spring Boot 3.5.0**, **Java 17**, **MongoDB 7**, **Testcontainers 1.x (do BOM Spring Boot 3.5 quản lý)** và JUnit Jupiter. **Cần Docker đang chạy**. Không dùng embedded MongoDB fake hoặc H2; không cần HTTP server.

### 5.1. Cấu trúc dự án

```text
nosql-transaction-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/nosql/
    │   ├── NoSqlTransactionApplication.java
    │   ├── OrderDoc.java
    │   ├── OutboxDoc.java
    │   └── OrderWorkflow.java
    └── test/java/com/example/nosql/
        └── MongoTransactionTest.java
```

### 5.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>nosql-transaction-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>mongodb</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-data-mongodb` sử dụng **imperative MongoTemplate** trong ví dụ; `org.testcontainers:mongodb` của dòng Testcontainers 1.x hỗ trợ `org.testcontainers.containers.MongoDBContainer`; `junit-jupiter` kích hoạt container lifecycle. **Spring Boot 4/Testcontainers 2.x có thể thay module/package**, cần tra tài liệu đúng dòng khi nâng cấp chứ không copy import tùy ý.

### 5.3. Spring Boot application

File **`src/main/java/com/example/nosql/NoSqlTransactionApplication.java`**:

```java
package com.example.nosql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoSqlTransactionApplication {
    public static void main(String[] args) {
        SpringApplication.run(NoSqlTransactionApplication.class, args);
    }
}
```

Application gốc giúp Spring Boot scan `OrderWorkflow` và Mongo mapping types cùng package. Ta không khởi động web server trong test; chỉ cần MongoDB resource và Spring transaction proxy.

### 5.4. MongoDB documents

File **`src/main/java/com/example/nosql/OrderDoc.java`**:

```java
package com.example.nosql;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDoc(@Id String id, String sku) {
}
```

File **`src/main/java/com/example/nosql/OutboxDoc.java`**:

```java
package com.example.nosql;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "outbox")
public record OutboxDoc(
        @Id String id,
        String orderId,
        String eventType) {
}
```

Java `record` hỗ trợ equality/immutable state. `@Id` được Spring Data Mongo map sang `_id`; MongoDB có unique index cho `_id` của mỗi collection. Hai collections khác nhau **không được tự gộp** vào một transaction chỉ vì dùng cùng `MongoTemplate`; giao dịch được tạo bởi transaction manager/session và boundary của service.

### 5.5. Service có và không có transaction

File **`src/main/java/com/example/nosql/OrderWorkflow.java`**:

```java
package com.example.nosql;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflow {

    private final MongoTemplate mongo;

    public OrderWorkflow(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional
    public void placeAtomically(
            String orderId, String sku, boolean failAfterOrder) {
        writeBoth(orderId, sku, failAfterOrder);
    }

    public void placeWithoutTransaction(
            String orderId, String sku, boolean failAfterOrder) {
        writeBoth(orderId, sku, failAfterOrder);
    }

    private void writeBoth(
            String orderId, String sku, boolean failAfterOrder) {
        mongo.insert(new OrderDoc(orderId, sku));

        if (failAfterOrder) {
            throw new IllegalStateException("after-first-write");
        }

        mongo.insert(new OutboxDoc(
                "event-" + orderId,
                orderId,
                "ORDER_PLACED"));
    }
}
```

**Điểm cần hiểu:**

- `placeAtomically` là **public Spring bean method** có `@Transactional`; khi **test gọi qua bean được inject**, proxy mở transaction. Private helper `writeBoth` chạy *bên trong* boundary của method public, nên hai lệnh MongoTemplate tham gia cùng session.
- `placeWithoutTransaction` dùng cùng helper nhưng **không có transaction**. MongoTemplate thực hiện từng insert độc lập; nếu throw sau insert đầu thì order có thể đã tồn tại mà outbox chưa được ghi.
- Nếu lỗi được ném trong method transactional, Spring rollback theo mặc định cho **unchecked exception** như `IllegalStateException`.
- Nếu service chỉ bắt `RuntimeException` và **nuốt lỗi** rồi trả bình thường, Spring có thể commit trừ khi chủ động đánh dấu rollback-only; test phải phản ánh policy này.
- Đây là transaction **MongoDB**, không phải transaction cho gửi email, Kafka hoặc Redis.

### 5.6. Test cấu hình MongoDB replica set và transaction manager

File **`src/test/java/com/example/nosql/MongoTransactionTest.java`**:

```java
package com.example.nosql;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(MongoTransactionTest.TxConfig.class)
class MongoTransactionTest {

    @Container
    static final MongoDBContainer MONGO =
            new MongoDBContainer(
                    DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class TxConfig {
        @Bean
        MongoTransactionManager transactionManager(
                MongoDatabaseFactory factory) {
            return new MongoTransactionManager(factory);
        }
    }

    @Autowired
    private MongoTemplate mongo;

    @Autowired
    private OrderWorkflow workflow;

    @BeforeEach
    void resetCollectionsOutsideTransaction() {
        // Tao collection truoc de khong phai DDL trong transaction.
        if (!mongo.collectionExists(OrderDoc.class)) {
            mongo.createCollection(OrderDoc.class);
        }
        if (!mongo.collectionExists(OutboxDoc.class)) {
            mongo.createCollection(OutboxDoc.class);
        }

        mongo.remove(new Query(), OrderDoc.class);
        mongo.remove(new Query(), OutboxDoc.class);
    }

    @Test
    void successCommitsOrderAndOutboxTogether() {
        workflow.placeAtomically("O-1", "BOOK-1", false);

        assertNotNull(mongo.findById("O-1", OrderDoc.class));
        assertNotNull(mongo.findById("event-O-1", OutboxDoc.class));
        assertEquals(1L, mongo.count(new Query(), OrderDoc.class));
        assertEquals(1L, mongo.count(new Query(), OutboxDoc.class));
    }

    @Test
    void exceptionAfterFirstInsertRollsBackBothCollections() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> workflow.placeAtomically(
                        "O-2", "BOOK-2", true));

        assertEquals("after-first-write", failure.getMessage());
        assertNull(mongo.findById("O-2", OrderDoc.class));
        assertNull(mongo.findById("event-O-2", OutboxDoc.class));
    }

    @Test
    void sameFailureWithoutTransactionLeavesPartialOrder() {
        assertThrows(
                IllegalStateException.class,
                () -> workflow.placeWithoutTransaction(
                        "O-3", "BOOK-3", true));

        assertNotNull(mongo.findById("O-3", OrderDoc.class));
        assertNull(mongo.findById("event-O-3", OutboxDoc.class));
    }

    @Test
    void duplicateOutboxIdAbortsNewOrderButKeepsExistingEvent() {
        mongo.insert(new OutboxDoc(
                "event-O-4", "OLD", "EARLIER_EVENT"));

        assertThrows(
                DuplicateKeyException.class,
                () -> workflow.placeAtomically(
                        "O-4", "BOOK-4", false));

        assertNull(mongo.findById("O-4", OrderDoc.class));
        OutboxDoc existing =
                mongo.findById("event-O-4", OutboxDoc.class);

        assertNotNull(existing);
        assertEquals("OLD", existing.orderId());
        assertEquals(0L, mongo.count(new Query(), OrderDoc.class));
        assertEquals(1L, mongo.count(new Query(), OutboxDoc.class));
    }
}
```

**Các lựa chọn cố ý trong code:**

- `@Testcontainers` và `@Container` tạo MongoDB 7 trong Docker. `getReplicaSetUrl` cho URI phù hợp replica set, cần cho transaction. **Không thay bằng URI của standalone MongoDB**.
- `@DynamicPropertySource` gắn URI container vào `spring.data.mongodb.uri` trước khi Spring Boot tạo `MongoClient`.
- `@TestConfiguration` và `@Import` nạp **`MongoTransactionManager`**; `@EnableTransactionManagement` cho Spring tạo proxy xử lý `@Transactional`.
- `@BeforeEach` tạo trước collections rồi dọn dữ liệu **ngoài** transaction. Việc tạo collection trong transaction có những hạn chế tùy phiên bản/topology, nên precreate là cách rõ ràng hơn.
- **Test 1:** gọi method transactional qua proxy, sau đó kiểm **cả hai collections** cùng có document.
- **Test 2:** ném lỗi sau insert order nhưng trước insert outbox; transaction rollback nên không còn document nào.
- **Test 3:** cùng lỗi nhưng không có annotation/boundary; order **vẫn tồn tại**. Đây là test đối chứng quan trọng, tránh “xanh” chỉ vì code không thực sự ghi.
- **Test 4:** outbox đã có `_id` trùng. MongoDB báo duplicate key ở insert thứ hai; transaction rollback cả order mới, **không xóa** outbox cũ được tạo trước transaction.

Không đặt `@Transactional` lên test methods: việc đó có thể làm sai ranh giới muốn chứng minh (test-managed transaction ảnh hưởng tới đọc kết quả). Assertions đọc dữ liệu **sau khi method proxy kết thúc**, nghĩa là sau khi commit/rollback được xử lý.

**Kết quả dự kiến:** khi Docker chạy được, Mongo container khởi tạo replica set và dependencies tương thích, có **4 phương thức `@Test` PASS**. Bài này **không được chạy thực tế trong tài liệu**; khi áp dụng, phải dùng Maven/IDE test runner để xác nhận trong môi trường của bạn. Một node replica set test chưa chứng minh chịu lỗi majority/failover của cluster production.

### 5.7. Chạy bằng Maven

Ở thư mục có `pom.xml`, cần Java 17+, Maven, Docker Engine chạy và có quyền khởi tạo container:

```bash
mvn test
```

Chạy riêng:

```bash
mvn -Dtest=MongoTransactionTest test
```

Nếu project có Maven Wrapper (`mvnw` được tạo trước), có thể dùng `./mvnw test`; Windows dùng `mvnw.cmd`. Maven Surefire/JUnit có thể in log MongoDB/Testcontainers theo phiên bản. Với đúng ví dụ, kỳ vọng **Tests run: 4, Failures: 0, Errors: 0** sau khi tải image và khởi tạo replica set thành công. Không có stdout nghiệp vụ cố định.

Một failure ở test 2 hoặc 4 trong đó **order vẫn tồn tại** là tín hiệu phải điều tra transaction manager, proxy, Mongo topology/session hoặc một thao tác đã chạy ngoài session — không “chữa” bằng cách xóa row trước assertion.

## 6. Redis: `MULTI/EXEC` không đồng nghĩa rollback khi runtime error

Redis là ví dụ kinh điển về việc **có thuật ngữ transaction** nhưng không có cùng ngữ nghĩa với MongoDB/Neo4j.

### `MULTI`, `EXEC`, `DISCARD` và `WATCH`

```redis
SET quota 5
MULTI
DECR quota
DECR quota
EXEC
GET quota
```

Đây là chuỗi lệnh minh họa trong `redis-cli`. `MULTI` bắt đầu queue commands; `EXEC` chạy commands được queue **tuần tự, không bị command client khác chen giữa**. Với input đã nêu và không có client khác sửa `quota`, giá trị sau EXEC là `3`.

Nếu client gọi `DISCARD` **trước `EXEC`**, commands đang queue bị bỏ mà không chạy. Nhưng nếu một command **bị lỗi trong lúc EXEC thực thi**, Redis **không rollback các command khác đã thành công**; một test phải kiểm cả state cuối và từng reply, không chỉ thấy reply array có mặt rồi kết luận atomic rollback.

Ví dụ (chủ ý có một command lỗi type):

```redis
SET counter 0
SET text hello
MULTI
INCR counter
INCR text
EXEC
GET counter
GET text
```

Kết quả về mặt trạng thái: `counter` có thể thành `1` mặc dù `INCR text` trả lỗi vì `text` không phải số; `text` vẫn là `hello`. Đây là **negative test minh họa** để phản bác ngộ nhận “EXEC gặp một lỗi thì hoàn tác tất cả”.

`WATCH` tạo **optimistic check-and-set**: Client A `WATCH stock`, đọc giá trị, queue mutation; nếu Client B thay `stock` trước A `EXEC`, A sẽ **không thực thi** batch và phải nhận biết null/aborted reply rồi retry hoặc báo conflict. Test đúng cần **hai kết nối độc lập** và barrier đồng bộ để chắc chắn có conflict; không dùng một connection rồi giả định có concurrency.

### Lua/Redis Functions

Khi cần “chỉ giảm tồn kho nếu còn lớn hơn 0”, Lua script có thể đọc-kiểm-ghi không bị client khác interleave trên Redis server, ví dụ:

```lua
local n = tonumber(redis.call('GET', KEYS[1]) or '0')
if n <= 0 then return 0 end
return redis.call('DECR', KEYS[1])
```

Script là **snippet Lua**, cần gọi qua `EVAL/EVALSHA` với đúng `KEYS[1]`; trong cluster, key placement/hash slots phải tuân thủ quy tắc multi-key. Test nên chạy **hai clients cùng tranh chấp** tồn kho 1 và xác minh chỉ một client giành được stock. Tuy nhiên nếu script đã ghi rồi sau đó phát sinh một Redis runtime error, **đừng tuyên bố những write trước đó tự rollback**.

Đối với durability, phải xem cấu hình **AOF/RDB, fsync, replication acknowledgements và failover**. Việc `EXEC` trả thành công không thể thay thế một fault-injection test về dữ liệu còn lại sau crash.

### Spring Data Redis

`RedisTemplate` hỗ trợ transactional commands và `setEnableTransactionSupport(true)` trong các trường hợp tương ứng. Nhưng một `@Transactional` JDBC/Mongo không tự biến mọi Redis command thành một **multi-resource ACID transaction**. Nếu cần thực sự kiểm Redis WATCH/MULTI behavior, dùng **Redis container**, `RedisConnection` hoặc `SessionCallback` đúng connection và assert **EXEC result + final key state**. Đừng dùng `@MockBean RedisTemplate` rồi kết luận rollback thực.

## 7. Cassandra: LWT, logged batch và Accord phụ thuộc phiên bản

### Lightweight transactions (LWT)

Cassandra truyền thống hỗ trợ compare-and-set qua câu lệnh CQL có điều kiện:

```sql
INSERT INTO users (tenant_id, user_id, email)
VALUES ('shop-a', 'U-1', 'a@example.com')
IF NOT EXISTS;
```

Đây là **CQL minh họa**, không phải SQL/JPA code; cần schema Cassandra với primary key phù hợp. Query có thể trả thông tin **`[applied]`**; khi key đã tồn tại, một INSERT `IF NOT EXISTS` khác phải trả **not applied**, và row ban đầu không bị ghi đè. LWT dựa trên cơ chế đồng thuận (Paxos) để cung cấp compare-and-set/linearizability trong phạm vi hỗ trợ, nhưng có chi phí latency cao hơn write thường.

Test tối thiểu phải kiểm **cả lần thành công lẫn lần thất bại điều kiện**; nếu client API không ném exception mà trả result `[applied]=false`, test chỉ assert “không có exception” sẽ **xanh giả**.

### Logged batch khác rollback kiểu RDBMS

`BEGIN BATCH ... APPLY BATCH`/logged batch có mục tiêu đảm bảo các mutations được ghi nhận và cuối cùng được apply theo guarantees của Cassandra, đặc biệt khi coordinator lỗi. Đừng suy từ từ “BATCH” rằng các partition khác nhau có **isolation + rollback tức thời** như một SQL transaction; consumer có thể nhìn thấy quá trình cập nhật qua nhiều partitions tùy phiên bản/config. Test phải nêu rõ muốn kiểm **eventual completion**, **atomic visibility** hay **conditional application**, bởi mỗi yêu cầu cần API khác nhau.

### Accord transactions ở những bản triển khai hỗ trợ

Tài liệu Cassandra mới có **Accord transactions** cho multi-partition/table ACID khi có version/config và transactional mode thích hợp. Vì vậy những khẳng định “Cassandra không có multi-partition transaction” phải gắn với **version/cơ chế cụ thể**. Trước khi dùng kịch bản transaction nhiều bảng, hãy kiểm release Cassandra, schema/table option, driver và cú pháp `BEGIN TRANSACTION ... COMMIT TRANSACTION` trong tài liệu tương ứng. Không copy API Accord vào cluster cũ chỉ có LWT/batch.

**Ma trận test Cassandra nên có:** `[applied]` true/false, hai clients tranh chấp cùng partition, logged batch giữa partitions trong network fault, read consistency QUORUM/LOCAL_QUORUM hoặc SERIAL/LOCAL_SERIAL khi dùng LWT, và Accord multi-partition **chỉ nếu được bật**.

## 8. DynamoDB: `TransactWriteItems` là transaction API có giới hạn rõ

DynamoDB có atomic single-item writes và conditional expressions. Khi cần nhiều items cùng all-or-nothing, dùng **`TransactWriteItems`** hoặc `TransactGetItems`, không phải hai `PutItem` tách riêng.

Ví dụ request transaction có thể gồm:

```text
TransactWriteItems:
  - Put Order(orderId=O-1), condition attribute_not_exists(orderId)
  - Update Stock(sku=BOOK-1), condition stock >= 1
  - Put Outbox(eventId=event-O-1), condition attribute_not_exists(eventId)
```

Đây là **pseudo-request**, không phải mã Java/AWS SDK runnable. Nếu `stock < 1` hoặc orderId đã tồn tại, transaction cần bị từ chối và **không áp dụng các thay đổi còn lại**. Test không chỉ assert exception `TransactionCanceledException`, mà phải đọc lại **order, stock, outbox** để thấy không có partial write.

Theo API DynamoDB hiện hành, một `TransactWriteItems` có giới hạn **tối đa 100 actions và 4 MiB** tổng dung lượng items, cùng AWS account/Region, và không đặt hai actions lên **cùng item**. Với global tables, giao dịch **không ACID xuyên các Regions** trong quá trình replication; test ở Region nhận replication không được suy ra atomic global visibility.

**Idempotency:** DynamoDB hỗ trợ `ClientRequestToken` để retry cùng transaction request mà không vô ý nhân đôi effect. Một test đáng giá là: gọi transaction, mô phỏng mất response/timeout, retry **cùng token**, rồi xác minh final state đúng một lần. Đừng test retry chỉ bằng `Mockito.verify(client, times(2))` vì không chứng minh trạng thái thực.

## 9. Neo4j và Couchbase: có ACID nhưng phải gọi đúng API

### Neo4j graph transactions

Neo4j hỗ trợ ACID transactions cho các thao tác node, relationship và Cypher. Ví dụ hợp đồng: “tạo hai nodes và relationship `OWNS` hoặc không tạo gì”. Với Spring Data Neo4j hoặc Neo4j Java Driver, đặt transaction boundary đúng rồi kiểm cả graph **sau commit/rollback**. Test container nên có:

- Happy path: cả hai nodes và relationship tồn tại.
- Throw sau tạo node thứ nhất: không còn graph fragment.
- Unique constraint conflict: transaction rollback đúng và không tạo relationship mồ côi.
- Concurrency: lock/isolation, lost updates, retry khi transient conflict.

Neo4j có ACID không đồng nghĩa **serializable isolation mặc định**; theo tài liệu, mặc định thường read-committed, nên nếu invariant yêu cầu serializability cần thiết kế locking/constraint/test phù hợp. Không test Neo4j bằng in-memory fake rồi tuyên bố đã đo locking thật.

### Couchbase distributed transactions

Couchbase cung cấp atomic operations cho một document và **distributed ACID transactions** cho nhiều documents/collections qua SDK transaction API. Ví dụ Java SDK concept:

```java
cluster.transactions().run(ctx -> {
    ctx.insert(collection, "order-O-1", orderContent);
    ctx.insert(collection, "outbox-O-1", outboxContent);
});
```

**Đây là snippet, không biên dịch độc lập** vì `cluster`, `collection`, `orderContent`, `outboxContent` chưa được khai báo. Khác với MongoTemplate imperative, việc có `@Transactional` trên một Spring service không tự chứng minh Couchbase SDK transaction lambda đã được dùng và toàn bộ operations tham gia transaction.

Test Couchbase phải kiểm **lambda commit/rollback**, conflict và transaction retries theo SDK/version; nếu transactions API tự retry lambda, mọi **side effect ngoài Couchbase trong lambda** (ví dụ gửi email) có nguy cơ chạy lại. Cần idempotency/outbox tách biệt. Với cluster configuration, durability và eventual search/index visibility có thể cần test khác ngoài KV transaction.

## 10. Elasticsearch: partial success và refresh không phải rollback

Elasticsearch hỗ trợ index/update mỗi document và **optimistic concurrency control** qua `if_seq_no` + `if_primary_term`. Nhưng **Bulk API không phải multi-document ACID transaction**: một request có thể có những items thành công và những items thất bại, không có rollback tự động cho những items thành công.

Ví dụ pseudo-bulk:

```text
Bulk:
  index product-1     -> 201 created
  update product-2    -> 409 version_conflict_engine_exception
  index product-3     -> 201 created

Response: errors=true, inspect items[0..2] separately
```

Đây là **kịch bản minh họa**, không phải response JSON thực được tạo từ một endpoint cụ thể. Một test chỉ thấy Bulk HTTP status 200 rồi kết luận “cả batch thành công” là **sai**; cần assert `errors` flag, từng item status/result và trạng thái search/index sau request.

**Refresh không phải commit:** index/update thành công thường cần `refresh` hoặc `refresh=wait_for` mới được nhìn thấy qua search ở thời điểm test mong đợi. Một test search ngay sau write có thể fail vì **near-real-time visibility**, không phải transaction rollback. Test nên tách:

1. Single-document optimistic version conflict.
2. Bulk partial success và xử lý từng item.
3. Search visibility sau refresh/refresh policy.
4. Retry/idempotency khi client không biết item nào đã được ghi.
5. Không giả định `@Transactional` Spring tự rollback Elastic indexes khi một request khác fail.

Nếu business cần “MongoDB order + Elasticsearch index” đồng bộ logic, cân nhắc **outbox/CDC/eventual projection**, không coi Elastic bulk như một phần của Mongo transaction.

## 11. Các case test tối thiểu cho mọi hệ lưu trữ

Trước khi viết test, hãy xác định **capability contract** của hệ đích; không đưa expected rollback vào một hệ không hỗ trợ. Một ma trận hữu ích:

| Case | Dữ liệu khởi đầu | Tác động | Assertion cuối |
|---|---|---|---|
| **Happy commit** | Hai collections/keys rỗng | Ghi A rồi B trong đúng transaction API | Sau completion, A và B cùng tồn tại |
| **Fail ở bước giữa** | Trạng thái sạch | Ghi A, ném exception trước B | **Nếu store có rollback:** A/B đều vắng; nếu không: assert partial effect đúng cơ chế |
| **DB-level conflict** | B đã có unique key | Ghi A rồi ghi B trùng key | **Nếu store có rollback:** A không tồn tại, B cũ không đổi |
| **Concurrent writers** | Một slot hoặc stock=1 | Hai clients cùng cố claim | Chỉ một được áp dụng khi dùng CAS/unique/locking đúng |
| **Timeout/unknown commit** | Có operation ID cố định | Gửi transaction, mất response rồi retry | Không double charge, không duplicate record |
| **Visibility** | Chưa có data | Ghi xong, đọc qua replica/search | Kết quả theo read concern/refresh deadline, không đoán immediate |
| **Crash/failover** | Replicated cluster | Kill leader trong lúc commit/replicate | Quan sát recovery theo durability guarantee đã cấu hình |
| **Cross-store failure** | DB + broker/index | DB ghi thành công, broker/index lỗi | Recovery/outbox/compensation bảo đảm eventual convergence, không giả rollback chéo |

Với tests concurrency, đừng dùng `Thread.sleep` rồi hy vọng hai request đụng nhau. Dùng `CountDownLatch`/`CyclicBarrier`, hai kết nối/clients riêng và `ExecutorService`; ghi nhận **kết quả cả hai thao tác** và đọc trạng thái server cuối. Một test chạy một lần vẫn có thể không bao phủ hết interleavings; hãy chạy lặp có giới hạn/cùng testcontainers cluster phù hợp, đồng thời tránh flaky timings.

### Cách đưa lỗi vào đúng vị trí

- **Business exception sau write thứ nhất:** kiểm proxy transaction có rollback thật.
- **Constraint/conditional conflict ở write thứ hai:** kiểm server abort theo actual database error path.
- **Network disconnect ở COMMIT:** kiểm ứng dụng xử lý **unknown commit outcome**, không tự kết luận không commit.
- **Process crash trước/ sau ACK:** kiểm durability với write concern/failover configuration.
- **Retry request từ client:** kiểm idempotency key/số lần side effects.
- **Outside resource failure:** kiểm outbox/compensation, không đưa nó vào cùng atomic claim nếu store không quản lý.

Tất cả injection phải **có thể tái lập và quan sát**, tốt nhất dùng test-specific services/containers. Không gây crash trên production hoặc shared database để “thử transaction”.

## 12. Một transaction của Spring không bao cả MongoDB, Redis và Kafka

Coi `@Transactional` như một “chiếc ô toàn cục” là sai:

```text
@Transactional
  write MongoDB order   --> MongoTransactionManager
  write Redis cache     --> Redis command/Redis transaction riêng
  publish Kafka event   --> Kafka producer transaction riêng
  call external HTTP    --> Server độc lập

Không mặc định có distributed atomic rollback giữa các bên!
```

Ví dụ **DB transaction + transactional outbox** thường phù hợp khi cần reliable publish:

1. Trong **một transaction MongoDB**, ghi order và `OutboxDoc`.
2. Commit xong, **worker riêng** đọc outbox và gửi event tới Kafka/Redis/search.
3. Consumer dùng **idempotency key** để bỏ duplicate; publisher có thể retry.
4. Đánh dấu outbox đã phát và dùng reconciler/monitoring cho record bị kẹt.
5. Test eventual consistency với bounded retry/poll, không đòi bước ngoài DB rollback cùng order.

**Outbox giúp không mất ý định gửi sự kiện**, nhưng nó **không tự cho exactly-once side effect**. Đường gửi có thể lặp khi mất ACK; consumer phải idempotent. Với workflow nhiều hệ và bước bù, có thể dùng Saga/compensating action; compensation **không phải rollback ACID**, có thể fail và cần retry/audit.

### Tách ba loại bảo đảm

- **Atomicity trong một store:** transaction API/manager thật và scope đúng.
- **Reliable delivery giữa stores:** outbox/CDC/event stream + idempotency.
- **Business correctness toàn workflow:** Saga/validation/reconciliation và end-to-end tests.

Khi viết tài liệu/test suite, ghi rõ cấp độ nào được chứng minh. Ví dụ `MongoTransactionTest` chỉ chứng minh Mongo collections cùng commit/abort; nó chưa chứng minh outbox publisher đã gửi event một lần hay Redis/Elasticsearch projection đã hội tụ.

## 13. Những lỗi thường gặp

| Lỗi/ngộ nhận | Hậu quả | Hướng sửa |
|---|---|---|
| Gắn `@Transactional` lên mọi repository NoSQL | Ảo tưởng tất cả stores rollback giống SQL | Kiểm transaction manager/SDK, scope và topology |
| MongoDB standalone dùng `@Transactional` multi-doc | Server không hỗ trợ transaction topology cần thiết | Dùng replica set/sharded cluster và session URI đúng |
| Thiếu `MongoTransactionManager` | MongoTemplate không tham gia Spring transaction mong đợi | Tạo bean manager; test service qua Spring proxy |
| Test gọi trực tiếp `new OrderWorkflow(mongo)` | Không có Spring AOP proxy | Inject bean từ context; kiểm rollback trong server |
| `this.placeAtomically()` self-invocation | Method call bypass proxy | Thiết kế boundary bean khác hoặc gọi đúng proxy |
| Không tạo collection trước Mongo transaction | Lỗi DDL/implicit collection creation tùy version/topology | Precreate collections/indexes ngoài transaction |
| Test method có transaction ngoài ý muốn | Chỉ thấy state trong test transaction hoặc rollback sai boundary | Đọc sau khi service proxy kết thúc, setup sạch |
| Redis `EXEC` gặp command error nhưng test mong rollback | Redis không rollback runtime writes đã thực hiện | Assert từng reply và final keys; thiết kế atomic script/compensation đúng |
| WATCH abort bị hiểu là exception DB rollback | Không có commands queued nào đã chạy sau failed EXEC | Assert null/aborted EXEC và key state, retry CAS |
| Cassandra `[applied]=false` không được assert | Điều kiện thất bại nhưng test vẫn xanh | Kiểm result LWT, concurrency hai clients |
| Nhầm logged batch là SQL transaction nhiều partitions | Tưởng có isolation/rollback đồng bộ | Test guarantees theo version; xem Accord khi có |
| DynamoDB gọi hai `PutItem` riêng thay `TransactWriteItems` | Có thể partial write | Dùng transaction API, assert all-or-nothing khi conflict |
| DynamoDB transaction dùng hai actions trên một item | Request vi phạm giới hạn API | Thiết kế conditional update/transaction đúng |
| Neo4j ACID nhưng test không có lỗi sau write đầu | Chưa chứng minh rollback | Inject fault và kiểm graph không có fragment |
| Couchbase transaction lambda gửi email | SDK retry lambda có thể gửi email lặp | Đưa side effect ra ngoài transaction, outbox/idempotency |
| Elasticsearch Bulk HTTP 200 được hiểu là mọi item thành công | Bỏ qua partial failures | Kiểm `errors` + item-level status |
| Elasticsearch query không thấy data nên nghĩ rollback | Chưa refresh search index | Phân biệt index ACK và refresh visibility |
| Dùng mock repository làm bằng chứng ACID | Mock không phải database | Integration test với server/container thật |
| Dùng một container Mongo để kết luận majority failover | Topology không đại diện production cluster | Cluster/failover integration tests riêng |
| Test retry vô hạn khi lỗi commit chưa rõ | Có thể double side effects hoặc treo CI | Idempotency keys, bounded retry, quan sát commit outcome |
| Không dọn dữ liệu giữa tests | Test order-dependent hoặc duplicate key ngẫu nhiên | DB/container cách ly và deterministic fixture cleanup |

## 14. Checklist thiết kế test theo capability thực tế

- [ ] Đã xác định **store + version + edition + topology + driver/SDK** được kiểm.
- [ ] Đã xác định guarantee là **single item**, **transaction multi-item**, **CAS** hay **batch eventual completion**.
- [ ] Tôi phân biệt atomicity, isolation, durability, visibility và idempotency.
- [ ] Nếu cần nhiều writes cùng rollback, backend thực sự hỗ trợ và API transaction được gọi đúng.
- [ ] Transaction manager Spring bean hoặc SDK transaction session được cấu hình và sử dụng.
- [ ] Tôi không dựa vào annotation `@Transactional` để bảo đảm transaction giữa nhiều hệ lưu trữ.
- [ ] Test positive case assert **mọi** records được commit.
- [ ] Test negative case throw **sau write thứ nhất** và assert đúng state của store.
- [ ] Test database-level error khi bước sau fail, không chỉ lỗi Java tự ném.
- [ ] Kiểm cả **existing data không đổi** sau transaction abort.
- [ ] Có test đối chứng **không có transaction** khi cần chứng minh hiệu quả.
- [ ] Nếu store không rollback, tôi kiểm **partial success** và cơ chế recovery/compensation.
- [ ] Với optimistic locking/conditional writes, test hai clients tranh chấp và cả kết quả fail.
- [ ] Với search/index, phân biệt acknowledgment và **visibility sau refresh**.
- [ ] Với timeout/failover, tôi có chính sách xử lý **unknown commit state** và idempotent retries.
- [ ] Test dùng container/schema/index/capabilities gần môi trường production khi rủi ro cao.
- [ ] Không sử dụng fake in-memory khác engine để suy ra bảo đảm của database thật.
- [ ] Cleanup/test isolation không xóa dữ liệu của test khác khi CI chạy song song.
- [ ] Với event/outbox, tôi kiểm eventual delivery và dedup riêng, không suy từ DB commit.
- [ ] Tôi chạy test bằng build tool và biết assertions nào chứng minh **store capability**, assertions nào chỉ kiểm service logic.

**Kết luận:** **Không có một ngữ nghĩa transaction chung cho mọi hệ lưu trữ ngoài SQL.** MongoDB, Neo4j, DynamoDB và Couchbase có cơ chế multi-object transaction trong phạm vi/điều kiện cụ thể; Redis có atomic commands/`MULTI/EXEC`/`WATCH` nhưng không rollback như SQL; Cassandra có LWT/batch và khả năng Accord tùy version; Elasticsearch có per-document concurrency và Bulk partial success, không phải multi-document rollback. Test tốt phải chọn **đúng server, đúng API, đúng failure boundary và đúng assertion về trạng thái sau lỗi**.

### Tài liệu chính thức đối chiếu

- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [MongoDB Java Driver — Integration Testing with Testcontainers](https://www.mongodb.com/docs/drivers/java/sync/current/integrations/testcontainers/)
- [Redis — Transactions, MULTI/EXEC/WATCH, rollback behavior](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Apache Cassandra — Guarantees, Lightweight Transactions](https://cassandra.apache.org/doc/latest/cassandra/architecture/guarantees.html)
- [Apache Cassandra — Accord Transaction concepts](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/transactions.html)
- [AWS DynamoDB — TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)
- [AWS DynamoDB — Transaction limits and global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html)
- [Neo4j — Transactional behavior](https://neo4j.com/docs/operations-manual/current/database-internals/)
- [Couchbase — Distributed ACID Transactions](https://docs.couchbase.com/java-sdk/current/concept-docs/transactions.html)
- [Elasticsearch — Document update and optimistic concurrency](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
