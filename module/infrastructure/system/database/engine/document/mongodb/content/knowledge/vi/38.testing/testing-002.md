# Dựng MongoDB bằng Testcontainers với topology phù hợp tính năng

## 1. Vì sao một MongoDB container không đủ cho mọi bài kiểm thử?

Một dự án Java có bốn nhóm bài test:

- Test `insertOne()`, `find()`, index và aggregation.
- Test chuyển tiền giữa hai tài khoản bằng **multi-document transaction**.
- Test **change streams** để phát event khi có document mới.
- Test ứng dụng có tìm được **primary mới** khi primary cũ bị dừng, và có đọc được từ **secondary** hay không.

Nếu mọi bài đều dùng một MongoDB chạy standalone, transaction và change streams có thể bị từ chối. Nếu chuyển tất cả sang **single-node replica set**, transaction và change streams có thể chạy, nhưng **không có secondary để kiểm tra read preference và không có thành viên khác để bầu primary khi node duy nhất dừng**.

Vấn đề của bài không chỉ là “khởi động MongoDB bằng Docker”. Mục tiêu là **chọn topology đơn giản nhất nhưng đủ điều kiện cho tính năng đang kiểm thử**, rồi cấu hình Java Driver, Spring Boot và môi trường CI tương ứng.

### 1.1. Kết quả mong đợi

Sau bài học, bạn có thể:

1. Chọn giữa **standalone**, **single-node replica set**, **multi-node replica set**, **sharded cluster** và **MongoDB Atlas Local** theo tính năng cần test.
2. Dùng Testcontainers Java, JUnit 5 và Java Sync Driver để chạy MongoDB cô lập trong integration tests.
3. Khai báo dependency đúng **Testcontainers 2.x**, biết khác biệt với ví dụ cũ 1.x.
4. Dùng `MongoDBContainer.withReplicaSet()` và `getReplicaSetUrl()` cho transaction/change stream tests.
5. Kết nối Spring Boot qua `@DynamicPropertySource` hoặc `@ServiceConnection` mà không hardcode Docker mapped port.
6. Hiểu việc cấu hình replica set nhiều node, tên host nội bộ, seed list và Docker network.
7. Tổ chức dữ liệu test, reset state, container lifecycle, parallel tests và cleanup để tránh flaky tests.
8. Thiết kế các kiểm thử tính năng: transaction rollback, resume change stream, read preference, election, retryable writes, sharding, search.
9. Chuẩn hóa Docker/CI, version pinning, diagnostics, timeout và giới hạn phạm vi mô phỏng production.

### 1.2. Phạm vi ví dụ

Ví dụ dùng **Java 17+**, **JUnit Jupiter** và **MongoDB Java Sync Driver**. Dependency minh họa theo **Testcontainers Java 2.0.x** và MongoDB image 7.0.x. Trong dự án thực cần chốt phiên bản cụ thể đã được xác minh tương thích.

**Quan trọng:** Testcontainers 2.0 chuyển MongoDB module sang tọa độ Maven `org.testcontainers:testcontainers-mongodb` và class `org.testcontainers.mongodb.MongoDBContainer`. Nhiều bài viết 1.x còn sử dụng `org.testcontainers:mongodb` và `org.testcontainers.containers.MongoDBContainer`. Không trộn hai cách khi sao chép code.

## 2. Testcontainers làm gì, không làm gì?

Testcontainers là thư viện Java điều khiển container runtime tương thích Docker để cấp những dịch vụ phụ thuộc cho tests.

```text
JUnit 5 / Spring Boot Test
          |
          v
    Testcontainers Java
          |
          +-- create isolated container
          +-- start / inspect / wait
          +-- expose dynamically mapped ports
          +-- report host + connection URI
          +-- capture logs / stop / clean up
          |
          v
     MongoDB container(s)
          |
          v
       Java MongoClient
          |
          v
     Assertions / teardown
```

### 2.1. Điểm mạnh

- Không cần cài MongoDB trực tiếp lên máy developer.
- Cùng một MongoDB image được chọn trong local và CI.
- Test có thể tự dựng hạ tầng cần thiết, thay vì trông cậy một database chia sẻ.
- Port trên host được cấp động nên giảm va chạm khi chạy nhiều test suites.
- Có thể mô phỏng phần lớn behavior của **MongoDB server thật** thay vì chỉ mock repository.
- Dễ kiểm soát version, startup, cleanup và tích hợp vào test lifecycle.

### 2.2. Giới hạn

- Testcontainers **không tự quyết định topology phù hợp** theo business requirement.
- `MongoDBContainer` thông thường **không tự cung cấp ba voting members hay một sharded cluster**.
- Single-node replica set không kiểm thử được majority propagation, election hoặc read preference từ secondary thật.
- Container cục bộ không mô phỏng đầy đủ latency multi-region, IAM, private endpoints hay mọi Atlas-managed features.
- Cần container runtime hoạt động và đủ CPU/RAM/disk trên local/CI.

### 2.3. Đây là integration test, không thay unit test

Unit test cho domain logic có thể không cần Docker. Testcontainers hữu ích khi cần xác nhận:

- Driver encoding/decoding BSON.
- Query filters, aggregation, indexes, unique constraints.
- Transaction semantics.
- Database validation, error codes và behavior thực.
- Change streams và cấu hình replica set.
- Tương tác Spring Data MongoDB với một server MongoDB thật.

Không tạo MongoDB container chỉ để test một hàm `calculateTotal()` không truy cập database.

## 3. Ma trận topology theo tính năng

| Điều cần kiểm thử | Standalone | Single-node replica set | Multi-node replica set | Sharded cluster | Atlas Local |
|---|---|---|---|---|---|
| CRUD, filters, aggregation cơ bản | Có | Có | Có | Có | Có, trong phạm vi hỗ trợ |
| Index unique/TTL/schema validation | Có | Có | Có | Có, với sharding constraints | Có |
| Multi-document transactions | Không trên standalone | **Có** | **Có** | Có, với sharded transactions | Phụ thuộc local deployment/features |
| Change streams | Không trên standalone | **Có** | **Có** | Có | Theo hỗ trợ của image |
| Retryable writes trong replica-set protocol | Không đủ điều kiện RS | Có | Có | Có | Theo topology |
| Read preference secondary có data | Không | **Không** | **Có** | Có nếu shard replicas phù hợp | Không thay multi-member tự động |
| Failover và election thực | Không | **Không** | **Có** | Có trên shard/config RS phù hợp | Không mặc định |
| Replication lag giữa nodes | Không | Không có secondary | Có | Có | Không mặc định |
| Majority acknowledgment trên nhiều node | Không | Majority chỉ một member | **Có** | Có theo replica sets | Tùy topology |
| Shard key, targeted/scatter query | Không | Không | Chưa đủ | **Có** | Không thay sharded cluster |
| `mongos` routing/balancer | Không | Không | Không | **Có** | Không |
| Atlas Search/Vector Search local | Không mặc định | Không mặc định | Không mặc định | Không tự có | **Mục đích chính** |
| Internal X.509/TLS/member auth | Phải cấu hình | Phải cấu hình | Phải cấu hình | Phải cấu hình | Tùy chế độ |

**Cách đọc bảng:** “Có” nói topology đủ nền tảng để thiết kế test, không phải một test bất kỳ đã tự động cover mọi trường hợp. Một single-node replica set vẫn cần wire version, MongoDB version và driver phù hợp cho feature đang thử.

### 3.1. Quy tắc chọn nhanh

```text
Test chỉ CRUD/index/aggregation?
  -> Standalone hoặc MongoDBContainer mặc định.

Test transactions/change streams?
  -> Single-node replica set là lựa chọn bắt đầu.

Test secondary reads, voting, failover, replication lag?
  -> Replica set có nhiều data-bearing members.

Test shard key, mongos routing, distributed transactions?
  -> Sharded cluster với config server + mongos + shards.

Test Atlas Search / Vector Search tích hợp tại local?
  -> MongoDBAtlasLocalContainer (đúng version và phạm vi hỗ trợ).
```

### 3.2. Chọn ít node nhất **đủ để chứng minh điều cần test**

Không cần cluster 9 containers cho một filter test. Nhưng nếu yêu cầu là “ứng dụng tiếp tục ghi sau khi primary chết”, một single-node replica set **không có ý nghĩa làm test failover** dù transaction trên nó vẫn chạy.

## 4. Chuẩn bị môi trường Java, Docker và JUnit

### 4.1. Những thành phần cần thiết

- JDK tương thích với Testcontainers/driver/Spring Boot đang dùng.
- Maven hoặc Gradle.
- Container runtime được Testcontainers hỗ trợ, có thể kéo MongoDB images.
- JUnit Jupiter.
- Java MongoDB Sync Driver hoặc Spring Data MongoDB starter.
- CI có Docker-compatible runtime và chính sách image pull/network phù hợp.

### 4.2. Kiểm tra container runtime ở local

Ví dụ từ terminal developer:

```bash
docker version
docker info
docker pull mongo:7.0
```

Đây là thao tác **tham khảo khi thiết lập**, không phải lệnh cần chạy trong quá trình viết tài liệu. Không bắt buộc user có Docker Desktop nếu đã có runtime khác được Testcontainers hỗ trợ.

### 4.3. Không sử dụng database production

Testcontainers phải kết nối đến **container được test khởi tạo**, không lấy URI từ `MONGODB_PROD_URI` hoặc env secret production. Một lỗi cấu hình URI trỏ sai có thể làm bộ test phá dữ liệu thật.

### 4.4. Kiểm tra version trước khi sao chép code

Với Testcontainers **1.x**, ví dụ cũ thường dùng:

```java
import org.testcontainers.containers.MongoDBContainer;
```

Với Testcontainers **2.x**:

```java
import org.testcontainers.mongodb.MongoDBContainer;
```

Không cố compile mẫu 2.x bằng JAR 1.x hoặc ngược lại.

## 5. Dependencies Gradle: Testcontainers 2.x

Ví dụ `build.gradle` cho một ứng dụng Java thông thường:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:5.6.0'

    testImplementation platform(
        'org.testcontainers:testcontainers-bom:2.0.5'
    )
    testImplementation 'org.testcontainers:testcontainers-mongodb'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Phiên bản trên là mốc minh họa** cho cách khai báo coordinates/BOM; cần đồng bộ với Spring Boot BOM và phiên bản thực tế đã chọn. Thực tế có thể để Spring Boot dependency management quản lý Testcontainers/JUnit/driver và chỉ override khi có lý do rõ.

### 5.1. Vì sao có BOM?

`testcontainers-bom` giúp các modules như MongoDB, JUnit Jupiter và core dùng phiên bản tương thích, tránh:

```text
testcontainers-mongodb 2.0.x
testcontainers-junit-jupiter 1.20.x
core transitive khác nhau
```

Đây là kiểu trộn version dễ tạo lỗi classpath.

### 5.2. Driver là dependency riêng

`testcontainers-mongodb` quản lý container, **không tự bổ sung MongoDB Java Driver cho ứng dụng**. Với Spring Boot Data MongoDB starter, driver thường được kéo theo starter; Java thuần cần `mongodb-driver-sync` riêng.

### 5.3. Phân biệt scope

Testcontainers dependencies nên nằm trong `testImplementation`; không đóng gói Testcontainers core/điều khiển Docker vào runtime production chỉ để application kết nối database.

## 6. Dependencies Maven tương ứng

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>testcontainers-bom</artifactId>
      <version>2.0.5</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-mongodb</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>5.6.0</version>
  </dependency>
</dependencies>
```

Đây là **đoạn dependency fragment**, không phải toàn bộ `pom.xml`. Dự án cần JUnit/JDK/test plugin phù hợp; phiên bản có thể do BOM khác quản lý.

## 7. JUnit 5 và `@Testcontainers` / `@Container`

Một test class mẫu dùng lifecycle của Jupiter:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class MongoStarts412Test {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void mongoIsRunning() {
        assertTrue(mongo.isRunning());
    }
}
```

### 7.1. Static container

`static @Container` thường được khởi động **một lần cho test class** rồi dừng sau các test methods của class. Phù hợp nếu các test cùng sử dụng một database có quy tắc cách ly dữ liệu rõ.

### 7.2. Instance container

`@Container` ở instance field được quản lý theo từng test method. Tăng tính cô lập nhưng startup cost cao hơn.

### 7.3. Testcontainers JUnit 5 extension và parallel

Tài liệu Testcontainers lưu ý JUnit Jupiter extension chủ yếu được thử nghiệm với **sequential test execution**; parallel tests cần thiết kế rõ cơ chế sharing/ownership, không mặc định các container fields và mutable data an toàn khi chạy đồng thời.

### 7.4. Test “đang chạy” chưa đủ

`mongo.isRunning()` chỉ chứng minh Docker container state, **chưa xác nhận feature được kiểm thử**. Những test hữu ích hơn cần gọi MongoDB và assert kết quả, transaction hoặc change stream behavior.

## 8. MongoDB standalone: khi nào dùng `GenericContainer`?

Nếu muốn kiểm tra hành vi **standalone thật sự**, đừng mặc định `MongoDBContainer` tạo standalone; MongoDB module có logic replica set riêng theo version.

Ví dụ generic container:

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> standalone =
    new GenericContainer<>(DockerImageName.parse("mongo:7.0"))
        .withExposedPorts(27017)
        .withCommand("mongod", "--bind_ip_all");

standalone.start();

String uri = String.format(
    "mongodb://%s:%d/?directConnection=true",
    standalone.getHost(),
    standalone.getMappedPort(27017)
);
```

### 8.1. Standalone giúp test gì?

- CRUD, BSON codec, filters, projection.
- Aggregation cơ bản, update operators.
- Index unique, TTL mechanics, collation.
- Schema validation.
- Xử lý exception từ server.

### 8.2. Standalone không đủ cho multi-document transaction

Một lệnh transaction thực trên standalone có thể bị từ chối, vì multi-document transactions yêu cầu một deployment được hỗ trợ (replica set/sharded cluster).

### 8.3. URI dùng mapped port

Không viết:

```text
mongodb://localhost:27017
```

trừ khi bạn **cố ý** publish đúng port cố định. Testcontainers thường cấp một host port động nên dùng `getHost()` và `getMappedPort(27017)`.

### 8.4. Không dùng standalone làm đại diện cho production replica set

Nếu production dùng majority write concern, session transaction hoặc change streams, test hoàn toàn standalone có thể bỏ sót những lỗi quan trọng.

## 9. Single-node replica set: topology đủ cho transaction

Sơ đồ:

```text
JUnit 5 / Java Driver
        |
        v
Testcontainers mapped endpoint
        |
        v
MongoDBContainer
  mongod --replSet ...
  rs.initiate()
  single member becomes PRIMARY
        |
        v
    local.oplog.rs
```

### 9.1. Các tính năng được hỗ trợ

Single-node replica set cho phép:

- Multi-document transactions trong một deployment được hỗ trợ.
- Change streams và oplog-based behavior.
- Sessions, retryable write protocol.
- Một số write/read concern semantics.
- Kiểm thử nhiều lệnh trong một transaction với MongoDB thật.

### 9.2. Những thứ **không được** mô phỏng

- Không có secondary để đọc.
- Không có lag giữa primary và secondary.
- Không có election sang node khác khi primary chết.
- Majority chỉ gồm **một member**; không chứng minh sự bền vững qua nhiều bản sao.
- Không kiểm tra được phản ứng với network partition giữa voting members.

### 9.3. Kết nối đúng

`MongoDBContainer.withReplicaSet()` giúp khởi tạo chế độ replica set theo API Testcontainers 2.x. Sau khi container start, lấy URI bằng `getReplicaSetUrl()`.

**Không tự gắn `replicaSet=rs0` hay tự thay hostname/port trong URI nếu helper đã cung cấp URI.** Tên replica set và cách container quảng bá địa chỉ do module quản lý.

## 10. Java integration test hoàn chỉnh: đọc/ghi trên replica set một node

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class ProductRepository412IT {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    static MongoClient client;
    static MongoCollection<Document> products;

    @BeforeAll
    static void setup() {
        client = MongoClients.create(mongo.getReplicaSetUrl());
        products = client.getDatabase("it_products_412")
            .getCollection("products");
    }

    @AfterAll
    static void cleanup() {
        if (client != null) {
            client.close();
        }
    }

    @Test
    void shouldInsertAndFindProduct() {
        products.insertOne(
            new Document("_id", "P412-1")
                .append("name", "Demo keyboard")
                .append("price", 350000));

        Document found = products.find(
            new Document("_id", "P412-1")).first();

        assertNotNull(found);
        assertEquals("Demo keyboard", found.getString("name"));
        assertEquals(350000, found.getInteger("price"));
    }
}
```

### 10.1. Điểm đáng chú ý

1. `@Container static` quản lý lifecycle cho test class.
2. `withReplicaSet()` chọn topology thích hợp.
3. `getReplicaSetUrl()` cung cấp endpoint và port động sau khi start.
4. Database name `it_products_412` tách test namespace.
5. `MongoClient` được đóng sau test class.

### 10.2. Đừng dùng test data chung không có cleanup

Test này giả định container fresh cho class. Nếu bật reusable container hoặc dùng singleton lâu dài giữa classes, `_id = "P412-1"` có thể va chạm ở lần chạy sau. Khi chia sẻ container cần data isolation khác.

### 10.3. Kiểm thử API thay vì chỉ container status

Assertion kiểm tra document thực sự được ghi/đọc và Java Driver hoạt động trên MongoDB thật.

## 11. Test transaction: thành công và rollback

### 11.1. Vì sao transaction đòi replica set?

MongoDB hỗ trợ multi-document transaction trong replica set/sharded topology phù hợp; standalone không thực hiện loại transaction này.

Single-node replica set là lựa chọn nhẹ nhất để xác nhận **atomic commit/abort trên nhiều documents**. Nó không mô phỏng network failures hay majority behavior nhiều nodes.

### 11.2. Java test rollback có chủ đích

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

@Test
void shouldAbortTwoDocumentTransaction() {
    MongoCollection<Document> accounts = client
        .getDatabase("it_accounts_412")
        .getCollection("accounts");

    accounts.insertMany(java.util.List.of(
        new Document("_id", "A").append("balance", 100),
        new Document("_id", "B").append("balance", 50)
    ));

    try (ClientSession session = client.startSession()) {
        session.startTransaction();

        accounts.updateOne(
            session,
            new Document("_id", "A"),
            new Document("$inc", new Document("balance", -20)));

        accounts.updateOne(
            session,
            new Document("_id", "B"),
            new Document("$inc", new Document("balance", 20)));

        // Cố ý hủy để kiểm tra atomic rollback.
        session.abortTransaction();
    }

    assertEquals(100, accounts.find(
        new Document("_id", "A")).first().getInteger("balance"));

    assertEquals(50, accounts.find(
        new Document("_id", "B")).first().getInteger("balance"));
}
```

**Lưu ý:** test method trên giả định đang nằm trong test class có `client` đã được khởi tạo ở mục 10; namespace `it_accounts_412` phải fresh hoặc seed/cleanup có kiểm soát.

### 11.3. Test commit

Một test khác nên gọi `session.commitTransaction()` rồi assert cả hai số dư đã thay đổi, tổng bảo toàn, không có partial state.

### 11.4. Không suy từ rollback test rằng failover đã an toàn

Để kiểm tra `UnknownTransactionCommitResult`/`TransientTransactionError` trong election, cần **multi-node topology** hoặc một fault-injection strategy khác đủ sát thực tế; single-node mất node duy nhất không bầu primary mới.

## 12. Test change streams: nguồn sự kiện cần oplog

Change streams dùng oplog của replica set/sharded cluster để theo dõi thay đổi. Test trên standalone sẽ không có đúng điều kiện.

### 12.1. Luồng test

```text
Create single-node replica set
      |
      v
Open change stream on collection
      |
      v
Insert document into collection
      |
      v
Read event from stream
      |
      v
Assert operationType=INSERT and document key
```

### 12.2. Java Sync Driver minh họa

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;

@Test
void shouldReceiveInsertChangeEvent() {
    MongoCollection<Document> events = client
        .getDatabase("it_changes_412")
        .getCollection("events");

    try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
             events.watch()
                 .maxAwaitTime(1, TimeUnit.SECONDS)
                 .cursor()) {

        events.insertOne(
            new Document("_id", "E412-1").append("kind", "CREATED"));

        ChangeStreamDocument<Document> change = null;
        long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(10);

        while (System.nanoTime() < deadline && change == null) {
            change = cursor.tryNext();
        }

        assertNotNull(change, "No change stream event received");
        assertEquals(OperationType.INSERT, change.getOperationType());
        assertNotNull(change.getDocumentKey());
    }
}
```

### 12.3. Tránh race “mở watcher quá muộn”

Trên driver, `watch().cursor()` thực hiện subscription/aggregation, nhưng việc mở stream và thao tác ghi cần được thiết kế **đúng thứ tự**. Nếu test mở stream sau khi insert và không dùng `resumeAfter/startAtOperationTime` phù hợp, event có thể không còn nằm trong khoảng theo dõi mong muốn.

### 12.4. Timeout có hạn

Không dùng `cursor.next()` chờ vô hạn trong test. `tryNext()` với `maxAwaitTime` và deadline giúp test kết thúc rõ ràng nếu không có event.

### 12.5. Một event không chứng minh resume sau failover

Kiểm tra resume token, reconnect, oplog window và duplicate event handling cần những test riêng; single-node vẫn hữu ích để kiểm tra consumer logic cơ bản.

## 13. Spring Boot integration test bằng `@DynamicPropertySource`

### 13.1. Vì sao cần dynamic URI?

Host port thay đổi mỗi khi Testcontainers tạo container. Hardcode `spring.data.mongodb.uri=mongodb://localhost:27017` là không đúng.

Spring Framework cung cấp `@DynamicPropertySource` để đăng ký property từ container **sau khi endpoint được cấp**.

### 13.2. Ví dụ Spring Data MongoDB

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import org.bson.Document;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class SpringMongo412IT {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @DynamicPropertySource
    static void mongoProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
        registry.add("spring.data.mongodb.database",
            () -> "spring_it_412");
    }

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void shouldQueryWithSpringMongoTemplate() {
        Document value = new Document("_id", "SP412")
            .append("status", "READY");
        mongoTemplate.insert(value, "snapshots");

        Document result = mongoTemplate.findById(
            "SP412", Document.class, "snapshots");

        assertNotNull(result);
        assertEquals("READY", result.getString("status"));
    }
}
```

### 13.3. Điều cần kiểm tra

- Test có dependency `spring-boot-starter-data-mongodb`.
- Spring Boot version dùng `spring.data.mongodb.uri` theo cơ chế tương ứng.
- Container hoạt động trước khi Spring khởi tạo client thật.
- Không có property/bean khác override sai connection.
- Không chứa tài khoản production trong test properties.

### 13.4. Spring context caching và container lifecycle

Spring có thể cache application context giữa test classes. Nếu context giữ MongoClient trỏ đến container class trước đã dừng, test class tiếp theo có thể nhận **stale connection string**.

Các giải pháp: dùng container singleton có lifecycle được quản lý xuyên classes, giới hạn context reuse, hoặc chủ động cấu hình test context isolation phù hợp. Không bật `@DirtiesContext` cho mọi test nếu không cần, vì chi phí startup context lớn.

## 14. Spring Boot `@ServiceConnection`

Với Spring Boot hỗ trợ **Testcontainers service connections** (Spring Boot 3.1+ với setup phù hợp), có thể:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class SpringMongoServiceConnection412IT {

    @Container
    @ServiceConnection
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void contextStarts() {
        // Spring MongoDB auto-configuration uses connection details
        // derived from the running MongoDB Testcontainer.
    }
}
```

### 14.1. Phụ thuộc bổ sung

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
}
```

Spring Boot tạo `MongoConnectionDetails` phù hợp từ `MongoDBContainer`. Khi service connection active, connection details **có thể được ưu tiên hơn properties**; cần hiểu cách framework phối hợp với custom MongoClient beans.

### 14.2. `@ServiceConnection` hay `@DynamicPropertySource`?

| Lựa chọn | Ưu điểm | Khi cân nhắc |
|---|---|---|
| `@DynamicPropertySource` | Tường minh từng property, linh hoạt | Phải đặt database/URI riêng |
| `@ServiceConnection` | Ít boilerplate, tích hợp Boot | Auto-config phù hợp với project |
| Custom `MongoClient` test bean | Điều khiển settings trực tiếp | Driver/test setup đặc thù |

Không đồng thời khai báo ba kiểu khác nhau để rồi không biết Bean/URI nào được dùng.

### 14.3. Test không chỉ cần contextLoads

`contextStarts()` là smoke test cấu hình, nhưng phải thêm assertions thực sự gọi repository/transaction/stream để chứng minh feature hoạt động.

## 15. Kiểm tra topology trước khi chạy tính năng

Đừng tin tuyệt đối tên class `MongoDBContainer`. Dùng MongoDB command để xác nhận:

```java
import org.bson.Document;

Document hello = client.getDatabase("admin")
    .runCommand(new Document("hello", 1));

System.out.println("hello.setName=" + hello.getString("setName"));
System.out.println("hello.isWritablePrimary=" +
    hello.getBoolean("isWritablePrimary"));
```

### 15.1. Assertion cho replica set

```java
assertNotNull(hello.getString("setName"));
assertEquals(Boolean.TRUE,
    hello.getBoolean("isWritablePrimary"));
```

`setName` xuất hiện khi server thuộc replica set. `isWritablePrimary` cho biết vai trò theo hello response; trong một cửa sổ election có thể chưa true, nên đợi readiness đúng thay vì `Thread.sleep` cố định.

### 15.2. `replSetGetStatus`

Khi có quyền:

```java
Document status = client.getDatabase("admin")
    .runCommand(new Document("replSetGetStatus", 1));
```

Một single-node replica set kỳ vọng một member trong `members` và role primary sau khởi tạo.

### 15.3. Điều gì không nên assert?

Không assert container's **mapped port** bằng một literal cụ thể. Không assert election diễn ra trong đúng 3 giây trên mọi CI host. Không dùng string output Mongosh không ổn định làm protocol nếu MongoDB driver có field JSON/BSON có cấu trúc.

## 16. Readiness: không chỉ đợi cổng 27017 mở

```text
Container started
    |
    v
Port 27017 listening
    |
    v
MongoDB process ready for commands
    |
    v
Replica set initiated
    |
    v
PRIMARY elected
    |
    v
Transactions/change streams can run
```

### 16.1. Socket open không phải feature ready

`Wait.forListeningPort()` chỉ chứng minh TCP port có thể chấp nhận kết nối, **không chứng minh rs.initiate() đã hoàn tất**.

### 16.2. Dùng helper module

`MongoDBContainer.withReplicaSet()` đảm nhận phần setup theo implementation của Testcontainers. Không tùy tiện ghi đè `withCommand()`/startup script/wait strategy nếu chưa hiểu logic khởi tạo nội bộ.

### 16.3. Với topology tự dựng

Phải:

1. Khởi động các `mongod` processes.
2. Gọi `rs.initiate()` đúng một lần trên member thích hợp.
3. Đợi primary election.
4. Đợi secondaries được nhận diện và có state đúng.
5. Kết nối driver qua URI mà **client thực sự resolve được**.

Không `Thread.sleep(5000)` rồi mặc định mọi CI node đủ nhanh.

## 17. Test data: seed, isolation và teardown

### 17.1. Kiểm thử cần độc lập và lặp lại được

Một test:

```java
products.insertOne(new Document("_id", "P1"));
```

có thể fail `E11000 duplicate key` nếu test khác để lại `P1` trong database.

### 17.2. Các chiến lược

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Fresh container mỗi class | Cô lập mạnh | Startup chậm hơn |
| Fresh DB mỗi class | Chia sẻ container, tách namespace | Cần cleanup và quản lý metadata |
| Fresh collection mỗi test | Dễ reset dữ liệu nhỏ | Dễ quên indexes/schema |
| Unique IDs mỗi test | Ít va chạm | Có thể vẫn lệch vì shared state |
| Transaction rollback ở cuối | Gọn cho một số patterns | Không cover mọi operation/side effects |
| Database cleanup sau test | Dễ hiểu | Failure giữa test/cleanup có thể để lại state |

### 17.3. Không drop nguyên database lạ

Chỉ `dropDatabase()` trên test database **được tạo riêng và biết chắc không chứa dữ liệu của test suite khác**. Với mọi cleanup nguy hiểm, xác định ownership trước.

### 17.4. Seed trước assertions

Ví dụ:

```java
MongoCollection<Document> products =
    client.getDatabase("it_seed_412").getCollection("products");

products.insertMany(java.util.List.of(
    new Document("_id", "P10")
        .append("category", "audio").append("price", 100000),
    new Document("_id", "P20")
        .append("category", "audio").append("price", 200000),
    new Document("_id", "P30")
        .append("category", "books").append("price", 150000)
));
```

Viết test filter category và sort price theo kết quả dự kiến. Không dùng những IDs này nếu chia sẻ dữ liệu qua classes mà chưa reset.

### 17.5. Seed bằng Java thay vì phụ thuộc shell version

MongoDB Docker images có thể khác nhau về `mongosh` availability/options. Với integration tests Java, seed bằng Java Driver sau khi container ready thường dễ kiểm soát hơn việc mount JS script chỉ chạy một lần vào `docker-entrypoint-initdb.d`.

## 18. Index, validation và TTL: topology phù hợp nhưng không overkill

### 18.1. Unique index

```java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

orders.createIndex(
    Indexes.ascending("tenantId", "requestId"),
    new IndexOptions().unique(true));
```

Test thêm hai orders có cùng `tenantId/requestId` và kỳ vọng MongoDB trả duplicate key.

### 18.2. Schema validation

```javascript
db.createCollection("inventories", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "available"],
      properties: {
        sku: { bsonType: "string" },
        available: {
          bsonType: ["int", "long"],
          minimum: 0
        }
      }
    }
  }
});
```

Test document thiếu `sku` hoặc `available < 0` bị từ chối. Một standalone container đã đủ cho case này.

### 18.3. TTL

TTL monitor chạy bất đồng bộ; test không nên assert “document biến mất sau đúng 100 ms”. Sử dụng deadline phù hợp và test TTL semantics riêng. **Đừng làm toàn suite chờ TTL monitor** nếu có thể dùng unit test cho policy và một integration test nhỏ cho behavior.

### 18.4. Tạo indexes trước workload

Seed và tạo indexes theo thứ tự phù hợp. Với unique index, dữ liệu trùng được seed trước khi create index có thể làm build thất bại vì duplicate, khác với assert insert duplicate sau khi index đã có.

## 19. Test aggregation với dữ liệu sát kiểu BSON

Một mock repository có thể không nhận ra những khác biệt:

- `Decimal128` so với `double`.
- `ObjectId` so với `String`.
- `Date` và timezone.
- `null` so với trường không tồn tại.
- Array operators và multikey semantics.
- Collation, case sensitivity.

### 19.1. Ví dụ aggregation

```javascript
db.sales412.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$productId",
      revenue: {
        $sum: { $multiply: ["$price", "$quantity"] }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1 } }
]);
```

### 19.2. Test output có thứ tự rõ

Aggregation `$group` không bảo đảm thứ tự results nếu không có `$sort`. Không assert theo thứ tự ngẫu nhiên chỉ vì máy local đang trả ổn định.

### 19.3. Version feature gates

Nếu pipeline dùng stage/operator chỉ có trên MongoDB mới, chọn image version tối thiểu phù hợp và test compatibility matrix. **MongoDB image version là một phần của test contract.**

## 20. Tách test logic transaction khỏi test failover

### 20.1. Hai mục tiêu khác nhau

Test transaction:

```text
Given two accounts
When one transaction updates both
Then commit changes both or abort changes none
```

Topology đủ: **single-node replica set**.

Test failover:

```text
Given A PRIMARY and B/C SECONDARY
When A becomes unavailable
Then B or C is elected PRIMARY
And Java Driver resumes eligible operations
```

Topology bắt buộc: **multi-node replica set có đủ majority**.

### 20.2. Tách suites

```text
src/test/java/
  repository/
    CrudIT.java
    TransactionIT.java
    ChangeStreamIT.java

src/failoverTest/java/ (hoặc source set/tag riêng)
    ElectionIT.java
    SecondaryReadIT.java
    RetryOnFailoverIT.java
```

Các paths là ví dụ tổ chức dự án, không có source set `failoverTest` sẵn nếu chưa cấu hình Gradle/Maven.

### 20.3. Vì sao không test failover trên CI nhanh mặc định?

Multi-node startup, network setup và election kéo dài hơn. Có thể chạy theo tag/nightly/merge gate chuyên biệt; giữ unit/integration tests nhanh cho feedback mỗi commit.

## 21. Multi-node replica set: kiến trúc tối thiểu

Sơ đồ ba data-bearing members:

```text
               Docker network: mongo-it-net

        +----------------+      +----------------+
        | mongo-a        |      | mongo-b        |
        | alias=mongo-a  |      | alias=mongo-b  |
        | mongod         |      | mongod         |
        | --replSet rsIT |      | --replSet rsIT |
        +----------------+      +----------------+
                 \                  /
                  \                /
                   \              /
                  +----------------+
                  | mongo-c        |
                  | alias=mongo-c  |
                  | mongod         |
                  | --replSet rsIT |
                  +----------------+
                           |
                           v
                 Containerized test runner
                 same network:
                 mongodb://mongo-a:27017,
                 mongo-b:27017,
                 mongo-c:27017/?replicaSet=rsIT
```

### 21.1. Vì sao cần ba members?

Với ba voters, majority cần 2. Khi primary A mất, B và C vẫn có thể bầu primary mới nếu đủ điều kiện/đã đồng bộ. Với một node, dừng node duy nhất đồng nghĩa không còn thành viên để bầu.

### 21.2. Vì sao nên dùng data-bearing members?

Nếu mục tiêu là **secondary reads, replication lag và failover**, dùng ba data-bearing members cho signal rõ hơn thay vì một primary, một secondary, một arbiter. Arbiter có phiếu nhưng không lưu dữ liệu/oplog.

### 21.3. Không khẳng định “ba containers = replica set”

Ba tiến trình `mongod` chạy riêng rẽ vẫn chỉ là ba standalone processes nếu chưa:

1. Khởi động với cùng replica set name.
2. Thiết lập nội bộ có thể kết nối nhau.
3. Gọi `rs.initiate()` hoặc config phù hợp.
4. Chờ election/catch-up.

### 21.4. Multi-node phức tạp hơn module mặc định

Tài liệu Testcontainers MongoDB module cũng hướng dẫn cân nhắc một giải pháp helper chuyên cho multi-node replica set. Không dùng một `MongoDBContainer` và giả định nó có thể sinh ba voting members.

## 22. Docker networking và địa chỉ được MongoDB công bố

### 22.1. Hai không gian mạng

Trong Docker network:

```text
mongo-a:27017
mongo-b:27017
mongo-c:27017
```

Docker có thể resolve những **network aliases** này giữa containers cùng network.

Trên host chạy JUnit:

```text
localhost:<randomMappedPortA>
localhost:<randomMappedPortB>
localhost:<randomMappedPortC>
```

Host JVM **không mặc định** resolve được `mongo-a` như hostname của Docker network.

### 22.2. MongoDB Driver còn học hosts từ `hello`

MongoDB replica set config:

```javascript
{
  _id: "rsIT",
  members: [
    { _id: 0, host: "mongo-a:27017" },
    { _id: 1, host: "mongo-b:27017" },
    { _id: 2, host: "mongo-c:27017" }
  ]
}
```

Driver kết nối vào seed host rồi đọc member hostnames được replica set công bố. Nếu JVM host không thể resolve `mongo-b`, nó có thể chọn sai topology/không tìm được primary dù đã mở mapped ports.

### 22.3. Vì sao URI `localhost:mappedA,mappedB,mappedC` có thể sai?

```text
mongodb://localhost:49123,localhost:49124,localhost:49125
  ?replicaSet=rsIT
```

Driver có thể khám phá membership `mongo-a/b/c:27017` và cố kết nối tới các địa chỉ nội bộ đó. Nếu host JVM không resolve/reach, connection thất bại.

**Seed list không biến đổi các hostnames mà server công bố.**

### 22.4. Hai chiến lược đúng

1. **Chạy Java test/application runner trong cùng Docker network**, dùng URI theo aliases/ports container.
2. Nếu bắt buộc chạy JVM trên host, thiết kế **địa chỉ/proxy/mapping hai chiều** sao cho hostnames trong replica set config reachable từ tất cả members **và** JVM. Cần kiểm thử DNS/routing trên Linux, macOS, Windows và CI.

Đừng dùng `directConnection=true` rồi coi đó là test replica set failover: driver bị khóa vào một node và có thể né cơ chế discovery cần kiểm tra.

## 23. Dựng ba `mongod` bằng `GenericContainer`

Đoạn code **minh họa phần khởi tạo hạ tầng**. Nó tạo ba servers, một Docker network và khởi tạo replica set bằng `mongosh`; phần Java driver đa node phải chạy ở network có thể resolve `mongo-a/b/c`.

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;
import java.time.Duration;

public final class ThreeNodeMongoInfrastructure412
        implements AutoCloseable {

    private final Network network = Network.newNetwork();
    private final DockerImageName image =
        DockerImageName.parse("mongo:7.0");

    public final GenericContainer<?> a = node("mongo-a");
    public final GenericContainer<?> b = node("mongo-b");
    public final GenericContainer<?> c = node("mongo-c");

    private GenericContainer<?> node(String alias) {
        return new GenericContainer<>(image)
            .withNetwork(network)
            .withNetworkAliases(alias)
            .withExposedPorts(27017)
            .withCommand(
                "mongod", "--replSet", "rsIT", "--bind_ip_all")
            .waitingFor(Wait.forListeningPort())
            .withStartupTimeout(Duration.ofMinutes(2));
    }

    public void start() throws Exception {
        a.start();
        b.start();
        c.start();

        String init =
            "rs.initiate({_id:'rsIT',members:[" +
            "{_id:0,host:'mongo-a:27017'}," +
            "{_id:1,host:'mongo-b:27017'}," +
            "{_id:2,host:'mongo-c:27017'}" +
            "]})";

        var result = a.execInContainer(
            "mongosh", "--quiet", "--eval", init);

        if (result.getExitCode() != 0) {
            throw new IllegalStateException(
                "rs.initiate failed: " + result.getStderr());
        }

        // Cần đợi election + secondaries ready; xem mục kế tiếp.
    }

    @Override
    public void close() {
        c.stop();
        b.stop();
        a.stop();
        network.close();
    }
}
```

### 23.1. Vì sao dùng GenericContainer?

`MongoDBContainer` chuyên cho use case MongoDB đơn giản/single-node; nếu dùng ba instances của class này, chúng có thể tự khởi tạo các replica sets **độc lập** theo module implementation, không trở thành một replica set duy nhất.

Với custom multi-member setup, dùng `GenericContainer` hoặc helper multi-node được kiểm chứng để kiểm soát `--replSet`, `rs.initiate` và network.

### 23.2. Điều code này **chưa** làm

- Chưa đợi B/C trở thành `SECONDARY`.
- Chưa khởi tạo authentication/TLS/cluster internal auth.
- Chưa chạy Java test runner trong Docker network.
- Chưa xử lý retries nếu một node start chậm.
- Chưa tạo readiness gate đủ điều kiện cho failover assertions.

Đây là **building block**, không phải một reusable production-grade test harness hoàn chỉnh.

### 23.3. Không dùng `rs.initiate()` nhiều lần

Chỉ khởi tạo một replica set khi chưa có config. Với reusable containers/data volumes, cần kiểm tra trạng thái trước khi gọi lại, tránh lỗi “already initialized” hoặc cấu hình không đồng nhất.

## 24. Chờ primary và secondary bằng điều kiện, không `sleep`

### 24.1. Lệnh `replSetGetStatus` có cấu trúc

Từ shell trong member A:

```javascript
db.getSiblingDB("admin").runCommand({
  replSetGetStatus: 1
});
```

Kỳ vọng ba members:

```text
one PRIMARY
two SECONDARY
health=1 for all
```

### 24.2. Ví dụ Awaitility ở phía Java test harness

```java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

await()
    .atMost(Duration.ofMinutes(2))
    .pollInterval(Duration.ofSeconds(1))
    .until(() -> {
        var r = infrastructure.a.execInContainer(
            "mongosh", "--quiet", "--eval",
            "let s=rs.status();" +
            "if (s.members.length!==3 || " +
            "s.members.filter(m=>m.stateStr==='PRIMARY').length!==1 || " +
            "s.members.filter(m=>m.stateStr==='SECONDARY').length!==2 || " +
            "s.members.some(m=>m.health!==1)) quit(2);"
        );
        return r.getExitCode() == 0;
    });
```

### 24.3. Vì sao condition-based waits tốt hơn?

`Thread.sleep(5000)` có thể đủ trên laptop nhanh nhưng fail trên CI dưới tải cao. Với condition-based wait, test chạy ngay khi sẵn sàng và thất bại với thông điệp rõ khi timeout.

### 24.4. Không áp checklist đủ ba secondary cho các topology khác

Trong replica set ba node cần **1 primary + 2 secondary**, không phải 3 secondary. Nếu có arbiter/delayed/hide members, readiness condition phải theo **vai trò mong đợi** chứ không hardcode một công thức cho mọi cụm.

## 25. Kết nối runner ở cùng Docker network

Một chiến lược tránh lỗi hostnames:

```text
+--------------------------------------------+
| Testcontainers Docker network              |
|                                            |
| mongo-a:27017   mongo-b:27017 mongo-c:27017|
|        \            |            /         |
|         \           |           /          |
|          Java test runner container        |
|          can resolve all aliases           |
+--------------------------------------------+
```

Runner có thể là:

- Container build từ mã test Java của dự án.
- CI job chạy **bên trong cùng network** với MongoDB containers.
- Một test helper container để kiểm tra kết nối/driver khi có cấu hình runtime phù hợp.

URI được runner sử dụng:

```text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rsIT&retryWrites=true
```

Viết URI thực tế trên **một dòng**; xuống dòng ở trên chỉ để dễ đọc.

### 25.1. Kiểm tra alias bằng mongosh từ sidecar

Một helper container có `mongosh` ở cùng network có thể gọi:

```bash
mongosh "mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/?replicaSet=rsIT" --quiet --eval "db.hello().isWritablePrimary"
```

Không dùng thành công của `mongosh` trong sidecar như bằng chứng JVM **trên host** cũng có thể resolve alias; hai network namespaces khác nhau.

### 25.2. Nếu cần chạy JUnit trên host

Có thể xây test harness dùng reverse proxies/port forwarding/host mappings sao cho **mọi advertised hostnames** reachable từ host và member-to-member network. Đó là lựa chọn nâng cao, cần mô tả cụ thể resolution trên Docker Desktop, Linux và CI, không chỉ tạo các mapped ports.

### 25.3. Failover test phải dùng discovery

URI kết nối driver phải có đúng replica set name và nhiều reachable members. `directConnection=true` làm sai ý nghĩa của bài test automatic primary discovery.

## 26. Test read preference secondary

### 26.1. Đòi ít nhất một data-bearing secondary

Trên single-node replica set chỉ có primary; một `find` dùng `ReadPreference.secondary()` không thể tìm ra secondary.

### 26.2. Java test theo topology nhiều node

```java
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> secondaryCollection =
    client.getDatabase("rs_read_it_412")
        .getCollection("products")
        .withReadPreference(ReadPreference.secondary());

Document value = secondaryCollection
    .find(new Document("_id", "P412")).first();
```

Ở đây `client` phải được kết nối tới **multi-node replica set có secondary reachable**, không phải `MongoClient` singleton từ single-node example.

### 26.3. Read concern và replication

`secondary()` cho phép đọc dữ liệu có thể chậm so với primary. Test không nên assert “secondary lập tức thấy write vừa thực hiện” mà không chờ replication hoặc dùng causal consistency/session/read concerns phù hợp.

### 26.4. Không dùng `secondaryPreferred()` nếu muốn chứng minh secondary được dùng

`secondaryPreferred()` có fallback sang primary khi không có secondary phù hợp. Một test dùng preference này có thể pass dù không hề đọc từ secondary.

Để xác minh cụ thể host nhận lệnh, sử dụng command monitoring/tracing hoặc cách chọn server rõ ràng và assertions dựa trên topology.

## 27. Failover test: thao tác có chủ đích trong multi-node

### 27.1. Mục tiêu

```text
Given 3-voter replica set
And Java client configured for discovery
When primary becomes unavailable
Then another member becomes PRIMARY
And eligible operations eventually succeed
```

### 27.2. Test không được giả định ai sẽ là primary mới

Khi A mất, B hoặc C có thể được bầu tùy trạng thái, priority và tiến độ replication. Nếu bài test kỳ vọng **đúng B** mà không cấu hình ưu tiên và điều kiện, test có thể flaky.

### 27.3. Nên xác định primary theo trạng thái thật

Trước khi fault injection:

1. Đọc `rs.status()`/`hello` qua client phù hợp.
2. Xác định host hiện làm primary.
3. Xác nhận hai secondary bắt kịp, có quorum.
4. Đặt deadline test rõ và thu evidence.

Sau đó mới thực hiện planned stepdown hoặc stop đúng primary trong môi trường test.

### 27.4. Đừng gọi `a.stop()` chỉ vì a từng là primary

Sau initial election, a có thể đã trở thành secondary. Test phải xác định trạng thái thực tế rồi mới inject fault.

### 27.5. Hai cách thử

**Planned stepdown:** dùng `rs.stepDown()` có điều kiện và quan sát client recovery.

**Unexpected primary failure:** stop/kill container đang primary (trong lab) và quan sát election từ hai members còn lại. Đây là test gần với failure hơn nhưng cần đảm bảo teardown và capacity.

### 27.6. Các assertions cần đo

- Primary mới xuất hiện trong deadline.
- Ứng dụng gặp lỗi tạm thời trong phạm vi mong đợi, sau đó phục hồi.
- Driver không cần restart toàn bộ application.
- Retryable operations xử lý đúng.
- Không có double business writes.
- Majority write sau failover thành công.

## 28. Kiểm thử replication lag và majority write concern

### 28.1. Single-node là không đủ

Với một voting member, `w:"majority"` có thể được thỏa bởi chính member đó. Nó không chứng minh replication sang host khác.

### 28.2. Multi-node quan sát optime

```javascript
const s = rs.status();
printjson(s.members.map(m => ({
  name: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate,
  health: m.health
})));
```

Trong test multi-node, có thể quan sát progress sau write, kiểm tra secondary bắt kịp bằng polling condition-based.

### 28.3. Bài test majority loss

Nếu muốn xác minh behavior khi không còn majority:

- Cần multi-node với voting config đã hiểu rõ.
- Inject network fault có thể khiến write concern timeout hoặc mất primary.
- Phải phân biệt “write chưa áp dụng” và “write đã áp dụng nhưng chưa đạt write concern”.
- Không chạy trên shared/staging production cluster.

### 28.4. Test có thể xấu khi dùng sleep

```java
Thread.sleep(1000); // Không chứng minh replication đã tới B/C.
```

Polling `optime`, document state theo read preference và deadline là cách có ý nghĩa hơn.

## 29. Fault injection bằng Docker stop khác network partition

### 29.1. Stop một container

Trong môi trường lab:

```java
// Pseudocode có điều kiện: container 'primaryNode'
// phải được xác định từ topology thật trước khi gọi.
primaryNode.stop();
```

Mô phỏng **process/host không còn phục vụ**. Không nhất thiết giống một packet-loss scenario.

### 29.2. Network partition

```text
          A PRIMARY
          /       \
         /         \
        B  ----X---- C
```

Network partition có nhiều hình dạng:

- A bị cô lập khỏi B/C.
- A có thể liên lạc B nhưng không với C.
- Client kết nối được A nhưng A không còn majority.
- Một link có packet loss/latency, không chết hoàn toàn.

Để mô phỏng các tình huống này có thể cần **Toxiproxy** hoặc network-control facilities tương đương; không thể thay thế mọi failure mode bằng `container.stop()`.

### 29.3. Biết giới hạn của giả lập

Thử ngắt kết nối giữa hai containers có thể không đúng với outage thực của cloud region, disks hoặc Kubernetes services. Kịch bản cần mô tả fault model và điều gì **chưa** được kiểm thử.

### 29.4. Không làm chaos testing trên database thật

Các thao tác stop/kill/network partition chỉ thực hiện trên cluster mà test sở hữu hoàn toàn. Không nối fault injection tới shared staging hay production MongoDB.

## 30. Dùng Toxiproxy khi cần network faults có kiểm soát

Toxiproxy là công cụ cho phép đưa latency, bandwidth limits hoặc connection failures vào đường kết nối qua **proxy**.

```text
Java Client (runner)
       |
       v
Toxiproxy
       |
       v
MongoDB node
```

### 30.1. Những lỗi có thể mô phỏng

- Kết nối mất đột ngột.
- Latency tăng có kiểm soát.
- Giảm bandwidth.
- Network đứt trong khi command đang chạy.
- Một số kiểu half-open/stalled behavior theo toxic được hỗ trợ.

### 30.2. Cạm bẫy với replica set

Nếu chỉ proxy **seed URI** nhưng MongoDB quảng bá `mongo-a/mongo-b/mongo-c` trực tiếp, driver có thể **bỏ qua proxy** sau topology discovery và kết nối thẳng tới nodes. Khi đó bài test không thật sự inject lỗi vào đường driver sử dụng.

Để test failover qua proxy đáng tin:

1. Thiết kế advertised addresses đi qua proxy phù hợp.
2. Đảm bảo mọi địa chỉ/port reachable từ runner.
3. Xác minh CommandListener/SDAM events chứng minh client traffic đi qua proxies.
4. Chỉ sau đó kích hoạt toxic và assert.

### 30.3. Đừng chỉ assert exception xuất hiện

Một bài test lỗi mạng hữu ích hơn nên assert **recovery behavior**, không mất business idempotency, retry budget và time-to-success.

## 31. Sharded cluster: khi nào buộc phải dựng?

Một sharded cluster có các thành phần:

```text
                    Java Driver
                        |
                        v
                    mongos
                   /  |   \
                  /   |    \
                 v    v     v
        +----------+ +----------+
        | Shard A  | | Shard B  |
        | RS       | | RS       |
        +----------+ +----------+
                 \     /
                  \   /
                   v v
          Config Server Replica Set
```

### 31.1. Các tính năng cần sharded topology

- Kiểm tra shard key và write routing.
- Đánh giá targeted vs scatter/gather queries.
- Kiểm tra unique index constraints trên sharded collections.
- Thử transactions xuyên shards.
- Kiểm tra một số `$lookup`/`$merge` behaviors trong sharded collection.
- Change streams trên sharded deployment.
- Xử lý `mongos` routing/failure và topology changes.

### 31.2. Vì sao hai MongoDBContainers không tạo sharding?

Hai `MongoDBContainer` chỉ tạo hai MongoDB test instances theo implementation của module; chúng **không tự có config servers, shard registrations, `mongos` hay collection sharding metadata**.

### 31.3. Một sharded cluster có thể cần nhiều containers

Một bài test cô lập theo nhu cầu có thể cần:

```text
Config RS: config-1 (tối giản cho lab) hoặc 3 nodes
Shard A: 1-node RS hoặc nhiều data-bearing members
Shard B: 1-node RS hoặc nhiều data-bearing members
mongos: 1 router
runner: test process / container
```

Sharded deployment có những yêu cầu cấu hình/khởi tạo cụ thể; số nodes tối thiểu hợp lệ và cơ chế config servers phụ thuộc phiên bản. Không đưa cấu hình một config server đơn lẻ vào môi trường production.

### 31.4. Không dựng full sharded cluster cho mọi repository test

Một repository chỉ query theo `_id` có thể kiểm thử trên single-node replica set; test riêng sharding behaviors nên chạy ở suite phù hợp, dù startup nặng hơn.

## 32. Sharded setup bằng Testcontainers Compose

### 32.1. Vì sao cân nhắc Compose?

Một topology gồm config server replica set, hai shard replica sets, `mongos` và init scripts có thể dễ diễn đạt bằng **Docker Compose** hoặc image test fixture chuyên dụng hơn là hàng trăm dòng `GenericContainer`.

Testcontainers hỗ trợ tích hợp Compose để start các services theo lifecycle của test.

### 32.2. Các khối cần khởi tạo

```text
1. Start config server mongod nodes with --configsvr --replSet
2. Initiate config server replica set
3. Start shard mongod nodes with --shardsvr --replSet
4. Initiate shard replica sets
5. Start mongos with --configdb configRS/hosts
6. Wait for mongos readiness
7. Run sh.addShard(...)
8. Enable sharding / shard collections with correct indexes
9. Run test through mongos
```

### 32.3. Test phải đi qua `mongos`

Để kiểm tra routing, Java test kết nối tới **mongos**. Nối thẳng vào shard primary rồi query có thể bỏ qua layer cần test.

### 32.4. Endpoint vẫn cần giải quyết đúng

Nếu container chạy trong một Docker network, các shard/config names có thể resolve nội bộ. Runner/JVM phải có đường đến `mongos` reachable; nếu server discovery đưa thêm hostnames, vẫn phải kiểm tra network semantics.

### 32.5. Khác biệt 1.x/2.x

Testcontainers Java thay đổi một số tọa độ modules/classes giữa 1.x và 2.x; khi dùng `ComposeContainer`, đọc đúng tài liệu của **version đã pin**, không copy import/dependency cũ vào môi trường mới.

## 33. Sharding test: tạo collection và kiểm tra shard key

Một ví dụ chạy qua `mongos` sau khi sharded cluster đã sẵn sàng:

```javascript
sh.enableSharding("orders_it_412");

db.getSiblingDB("orders_it_412").orders.createIndex({
  tenantId: 1,
  orderId: 1
});

sh.shardCollection(
  "orders_it_412.orders",
  { tenantId: 1, orderId: 1 }
);
```

### 33.1. Các assertions

- `sh.status()` hoặc metadata tương ứng thể hiện namespace đã sharded.
- Query có shard key được route phù hợp.
- Query thiếu shard key không được tự kết luận là targeted.
- Unique index constraints được kiểm tra theo quy tắc shard key/version.
- Cross-shard transaction được thử chỉ khi có nhiều shards với dữ liệu phân bố thích hợp.

### 33.2. Chưa đủ nếu chỉ gọi `sh.shardCollection()`

Chạy thành công lệnh quản trị chứng minh namespace được cấu hình sharded, nhưng để kiểm tra **routing** cần phân phối dữ liệu/điều kiện query đủ đa dạng và quan sát explain/shard metrics.

### 33.3. Không chỉnh sharding để tạo test trên shared database

Chỉ dùng namespace và cluster mà test sở hữu; `sh.enableSharding` và `sh.shardCollection` là thao tác thay đổi metadata.

## 34. Atlas Search và Vector Search: topology khác nữa

MongoDB Atlas Search / Atlas Vector Search là những tính năng tìm kiếm có **search engine integration**; một container `mongo:7.0` bình thường không tự cung cấp đầy đủ.

Testcontainers Java có **`MongoDBAtlasLocalContainer`** dùng image `mongodb/mongodb-atlas-local` để tạo môi trường Atlas Search/Vector Search local được hỗ trợ.

### 34.1. Ví dụ

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBAtlasLocalContainer;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
class AtlasLocal412IT {
    @Container
    static MongoDBAtlasLocalContainer atlas =
        new MongoDBAtlasLocalContainer(
            DockerImageName.parse(
                "mongodb/mongodb-atlas-local:7.0.9"));

    @Test
    void shouldProvideConnectionString() {
        assertNotNull(atlas.getConnectionString());
    }
}
```

### 34.2. URI Atlas Local

`getConnectionString()` trả host/mapped port động và có thể chứa `directConnection=true`. Không tự đổi sang replica set URI nếu image/container không công bố topology đó.

### 34.3. Không coi Atlas Local giống Atlas Cloud

Môi trường local không mặc định tái hiện:

- Atlas control plane, organization/project RBAC.
- Private endpoints và networking/cloud IAM.
- Đủ mọi vector search features/version behaviors.
- Resource sizing và distributed scaling.
- Atlas backups/PITR/alerting managed.

### 34.4. Test thật cần search index

Chỉ `atlas.isRunning()` chưa kiểm tra search. Phải tạo index hợp lệ, đợi trạng thái index sẵn sàng, seed documents, chạy `$search` hoặc `$vectorSearch` rồi assert kết quả.

### 34.5. Phiên bản hình ảnh

Image Atlas Local có version/feature constraints; pin phiên bản phù hợp server/search integration thực tế và kiểm tra image compatibility trước khi triển khai suite.

## 35. Vì sao single-node test transaction có thể cho kết quả “quá dễ”?

### 35.1. Majority ở một node

```text
Single node RS:
  voters=1
  majority=1
```

Write concern `majority` có semantics theo replica set, nhưng ở đây không đòi dữ liệu được sao chép sang một node vật lý khác.

### 35.2. Không có lag thật

Một ứng dụng dùng `ReadPreference.secondary()` trong production có thể gặp dữ liệu cũ. Test transaction trên one-node primary không cover tình huống này.

### 35.3. Không có election

Nếu dừng node duy nhất, driver không thể khám phá một primary mới cho tới khi node quay lại; không kiểm thử recovery qua server khác.

### 35.4. Test logic vẫn có giá trị

Đừng phủ nhận one-node tests: chúng rất hữu ích cho transaction atomicity, BSON types, validation, aggregation. **Chỉ không gán cho chúng những bảo đảm mà topology không thể tạo ra.**

## 36. Authentication và authorization trong Testcontainers

### 36.1. Container đơn giản thường không có auth

Nhiều MongoDB Testcontainers examples khởi động local MongoDB **không bật authentication** để tập trung vào query/transaction behavior.

Điều này **không** có nghĩa application production không cần auth.

### 36.2. Test authentication cần cấu hình có chủ đích

Với official MongoDB Docker image trong lab:

```java
GenericContainer<?> securedMongo =
    new GenericContainer<>(DockerImageName.parse("mongo:7.0"))
        .withExposedPorts(27017)
        .withEnv("MONGO_INITDB_ROOT_USERNAME", "testroot")
        .withEnv("MONGO_INITDB_ROOT_PASSWORD", "local-test-only-secret");
```

Official image có cơ chế init user qua các environment variables đó trong điều kiện startup phù hợp. Dùng **test-only credentials**, không commit production secrets.

### 36.3. Auth cho replica set phức tạp hơn

Khi bật auth trên nhiều members, phải xử lý **internal member authentication**, keyfile/X.509, permissions và thứ tự `rs.initiate()`. Không thêm các env username/password vào `MongoDBContainer.withReplicaSet()` rồi giả định helper tự xử lý mọi bước.

### 36.4. Test RBAC

Một test bảo mật hữu ích:

1. Tạo user có quyền read trên database A.
2. Xác nhận `find` trong A thành công.
3. Xác nhận write bị từ chối theo role.
4. Xác nhận truy cập database B bị từ chối.
5. Không dùng root user làm identity cho service đang được test.

### 36.5. Không chạy secured MongoDB sample trên production

Credentials cố định của ví dụ chỉ hợp lệ cho môi trường test disposable. Trong hệ thống thật phải dùng secrets management và phân quyền tối thiểu.

## 37. TLS, certificate và hostname trong topology test

### 37.1. Khi nào cần test TLS?

- Application bắt buộc kết nối `tls=true`.
- Certificate rotation.
- Client certificate authentication.
- Hostname verification.
- Multi-node với certificate SAN theo member hostnames.

### 37.2. Chỉ thêm `tls=true` chưa đủ

MongoDB server cũng phải được cấu hình TLS và có chứng chỉ hợp lệ. Test container phải mount certificate/key với permissions đúng, cấu hình CA/truststore cho client và hostname khớp SAN.

### 37.3. Multi-node cần cả internal auth

Khi dùng X.509 hoặc keyfiles để xác thực giữa members, những requirements đó là một phần của topology; không chỉ cấu hình Java client.

### 37.4. Không bỏ hostname verification

Không sửa lỗi SAN bằng cách bật `tlsAllowInvalidHostnames` hoặc bypass truststore để test pass. Thay vào đó cấp test certificates có SAN chính xác cho những hostnames dùng trong test network.

### 37.5. Test bảo mật nên thành suite riêng

Phần lớn CRUD tests không cần dựng CA/PKI trong mỗi test class. Có thể có suite riêng kiểm tra TLS/auth protocol, và những suite khác dùng MongoDBContainer đơn giản hơn.

## 38. Container lifecycle: đúng cách với JUnit

### 38.1. Per-method

```java
@Container
MongoDBContainer mongo = new MongoDBContainer("mongo:7.0")
    .withReplicaSet();
```

Container được tạo lại theo mỗi test method trong setup Jupiter tương ứng. Cách này cô lập tốt nhưng startup nhiều.

### 38.2. Per-class

```java
@Container
static MongoDBContainer mongo = new MongoDBContainer("mongo:7.0")
    .withReplicaSet();
```

Một container phục vụ nhiều test methods trong class; cần seed/cleanup.

### 38.3. Singleton suite-wide

Một số dự án dùng singleton container chạy xuyên nhiều classes để giảm startup. Khi đó:

- Không lẫn `@Container` lifecycle với singleton được quản lý thủ công.
- Không đóng container khi Spring context khác còn dùng MongoClient.
- Đặt database names riêng và cleaning ownership.
- Cần stop/cleanup phù hợp khi JVM kết thúc.

### 38.4. Test parallelism

Nếu chạy song song:

- Unique test IDs/databases.
- Không cùng drop một collection đang được test khác dùng.
- Không để một test stepdown/stop cluster trong khi test khác đang CRUD.
- Pool/shared container capacity phải đủ.
- JUnit Testcontainers extension parallel support/semantics cần được kiểm chứng theo version.

## 39. Reusable containers: lợi ích và nguy cơ

Testcontainers có khả năng **reusable containers** ở một số versions, nhưng được xem là experimental trong tài liệu.

### 39.1. Lợi ích

Trên máy developer, không phải startup MongoDB mới sau mỗi test run.

### 39.2. Rủi ro

- State lưu lại giữa runs.
- Index/collection cũ ảnh hưởng assertions.
- Test version mới dùng lại database từ version trước.
- Cleanup không xảy ra như container disposable.
- Khó phân tích flaky failures.

### 39.3. Không tự bật trên CI

CI nên ưu tiên **ephemeral, repeatable tests**. Chỉ dùng reuse khi có quy ước rõ và biết cách reset state. Không mặc định `withReuse(true)` + config host là tối ưu cho mọi nhóm.

### 39.4. Không dùng reuse để che startup problems

Nếu MongoDB container không khởi tạo replica set ổn định khi cold start, dùng container đã chạy từ trước có thể che bug readiness. Phải kiểm thử cold-start path riêng.

## 40. CI/CD: Docker runtime và tài nguyên

### 40.1. CI job cần gì?

- Docker-compatible daemon/runtime Testcontainers truy cập được.
- Quyền create/start/stop containers và networks.
- Đủ disk cho MongoDB images/temporary data.
- Đủ RAM/CPU cho mongod, đặc biệt nhiều nodes.
- Có network tới image registry/mirror.
- Cleanup runner/container lifecycle.

### 40.2. GitHub Actions, GitLab CI, Jenkins...

Mỗi nền tảng có cách cấp Docker socket/daemon khác. Không tự giả định `/var/run/docker.sock` luôn tồn tại trong runner.

### 40.3. Docker-in-Docker

Nếu test process chạy trong một container dùng Docker-in-Docker hoặc bind socket host, cần hiểu:

- `DOCKER_HOST` và cách Testcontainers discover daemon.
- Hostname/mapped-port mà JVM nhìn thấy.
- Docker network isolation.
- Resource/security của privileged mode.
- Cleanup khi runner bị kill.

**Không bật Docker socket đặc quyền cho workload không tin cậy** chỉ để chạy integration tests.

### 40.4. Image pull

Pin MongoDB image tag phù hợp và dùng registry mirror/cache nếu CI có rate limit. Tránh `mongo:latest` vì MongoDB server upgrade có thể làm test behavior đổi qua một đêm.

### 40.5. Image digests

Pin digest giúp tuyệt đối lặp lại image bytes, nhưng cần quy trình cập nhật bảo mật và rebuild theo chu kỳ. Pin tag version cụ thể cũng cần nhận thức tag có thể được republish.

## 41. Testcontainers Ryuk và cleanup

Testcontainers thường có resource reaper/cleanup mechanism giúp dọn containers/networks sau khi test kết thúc.

### 41.1. Vì sao quan trọng?

Không cleanup:

- Container còn chạy và giữ RAM/disk.
- Networks orphaned.
- Mapped ports/connections tồn tại ngoài ý muốn.
- CI runner đầy disk.

### 41.2. Không tùy tiện tắt cleanup

Trong một số CI có policy chặn sidecar cleanup, cần cấu hình theo tài liệu Testcontainers và cơ chế dọn tài nguyên thay thế đáng tin. Không mặc định tắt Ryuk/resource reaper để “hết lỗi” mà bỏ rủi ro rò tài nguyên.

### 41.3. Teardown phải xử lý cả khi test fail

Với manual `GenericContainer.start()`, sử dụng try-with-resources/`finally` hoặc JUnit lifecycle để stop/close. Nếu một node không start thành công, các nodes đã start trước đó vẫn phải được cleanup.

### 41.4. Không xóa Docker resources ngoài phạm vi test

Không chạy `docker system prune -a` trên shared CI host chỉ vì một suite MongoDB fail. Cleanup đúng containers/networks do Testcontainers sở hữu.

## 42. Startup failure: tìm đúng lớp lỗi

| Dấu hiệu | Nguyên nhân thường gặp | Đối chiếu |
|---|---|---|
| Cannot connect to Docker daemon | Runtime/socket/permission | Docker info, CI runtime |
| Image pull failed | Network/registry/rate limit | Registry credentials/cache |
| Mongo container exited | Command/image/volume/permission | Container logs |
| Port opened nhưng RS chưa ready | Election/init chưa hoàn tất | `hello`/`rs.status` |
| `rs.initiate` hostnames unreachable | Network aliases/DNS | Internal connectivity |
| JVM không chọn được primary | Advertised hosts không resolve | `hello.hosts`/URI |
| Transaction not supported | Standalone hoặc sai topology | `hello.setName` |
| Change streams unavailable | Không có replica set/sharded | Oplog/topology |
| Atlas Search stage unavailable | Sai image/search engine | Atlas Local config/index |
| Test pass local, fail CI | CPU/RAM/startup timeout/path | Timing/resource metrics |
| Unexpected duplicate key | Data leak giữa tests | Seed/cleanup/unique keys |

### 42.1. Xem logs container

```java
String logs = mongo.getLogs();
System.out.println(logs);
```

Chỉ dùng logs trong môi trường test với dữ liệu giả; output MongoDB có thể chứa thông tin kết nối, usernames hoặc query metadata.

### 42.2. Không chỉ in stack trace

Khi failure, chụp:

- Image name/tag.
- Testcontainers module version.
- Docker runtime version.
- Container exit code/log tail.
- MongoDB `hello`/`rs.status` nếu có thể kết nối.
- Network aliases, advertised hosts và URI đã redact.
- Startup/ready timestamps.

### 42.3. Không dùng sleep dài như biện pháp duy nhất

Tăng `Thread.sleep(30000)` có thể che race nhưng làm suite chậm mà vẫn thất bại trên CI chậm hơn. Dùng readiness condition với deadline có căn cứ.

## 43. Docker networking: những nhầm lẫn thường gặp

### 43.1. Host port khác container port

```text
Inside container:
  MongoDB listens 27017

On test host:
  MongoDB mapped to 49123 (example)
```

`getMappedPort(27017)` trả host port. Không nhầm `27017` nội bộ với port cho Java trên host.

### 43.2. `localhost` trong container không phải localhost của host

Nếu Java application chạy **trong container riêng**, `localhost` trỏ chính container Java, không trỏ MongoDB container.

### 43.3. Docker network aliases chỉ trong network

`mongo-a` có thể resolve trong custom Docker network nhưng không nhất thiết từ JVM host hoặc một network khác.

### 43.4. Replica set advertises hosts

Ngay cả khi seed URI kết nối được, driver khám phá hosts từ MongoDB và có thể bỏ seed endpoint ban đầu. Kết nối nhiều-node phải giải quyết **mọi advertised addresses**.

### 43.5. Không dùng `directConnection=true` để chứng minh failover

Chế độ direct giúp nhắm một member, phù hợp chẩn đoán, nhưng tránh cơ chế topology discovery của bài failover.

## 44. Database version matrix trong integration test

### 44.1. Vì sao cần nhiều server versions?

Ứng dụng có thể hỗ trợ MongoDB 7.0 và 8.0, sử dụng operators/index behaviors khác nhau; driver mới có thể hoạt động với server cũ ở mức được hỗ trợ.

### 44.2. Ma trận gợi ý

| Suite | MongoDB image | Topology | Tính năng |
|---|---|---|---|
| Basic CRUD IT | Server version thấp nhất hỗ trợ | Single-node RS | Query/index |
| Transaction IT | Các versions được hỗ trợ | Single-node RS | Commit/abort |
| Change Stream IT | Version mục tiêu | Single-node RS | Watch/resume |
| Failover IT | Version production | Three-node RS | Election/retry |
| Sharding IT | Version production | Sharded cluster | Routing/transactions |
| Search IT | Atlas Local image tương thích | Atlas Local | `$search`/`$vectorSearch` |

### 44.3. Pin image và test feature compatibility

Không chỉ thay image string nếu feature còn phụ thuộc `featureCompatibilityVersion` (FCV), storage engine, image support, Java driver version, TLS/auth config.

### 44.4. Không cần chạy mọi tổ hợp trên mỗi commit

Một lựa chọn:

- Mỗi PR: CRUD + transaction + change stream trên một version chính.
- Nightly: version matrix mở rộng và test multi-node/sharding.
- Trước nâng cấp production: compatibility/failover/rollback drills chuyên biệt.

### 44.5. Testcontainers pinning cũng quan trọng

Testcontainers 1.x và 2.x thay module names/packages. Việc nâng MongoDB image riêng và nâng Testcontainers Java riêng giúp phân loại regression rõ hơn.

## 45. Dataset đặc thù theo topology

### 45.1. Standalone

Seed documents đủ để kiểm tra indexes, filters, type handling, collation, TTL.

### 45.2. Single-node RS

Seed nhiều collections để kiểm tra transaction commit/abort; seed stream events có identity và timestamps.

### 45.3. Multi-node RS

Seed data đủ để kiểm tra secondary reads và read-after-write với lag; dùng unique business request IDs để phát hiện retry duplicates.

### 45.4. Sharded cluster

Seed keys được phân bố có chủ đích. Nếu mọi document tình cờ nằm trên một shard, “cross-shard transaction test” có thể thực tế chỉ chạm một shard.

### 45.5. Atlas Search

Seed documents có text/vector fields đúng index definition và đợi index ready. Không assert thứ tự scoring nếu thuật toán có tie hoặc behavior không ổn định mà thiếu điều kiện.

## 46. Chống flaky tests: readiness, timeouts và trạng thái

### 46.1. Flakiness từ startup

```text
Laptop: mongod ready in 2 sec
CI:     mongod ready in 15 sec
```

Nếu test hardcode sleep 3 giây, sẽ fail trên CI.

### 46.2. Flakiness từ election

Election có thể mất thời gian không cố định; assert phải theo deadline và trạng thái thay vì đo đúng một giá trị thời gian.

### 46.3. Flakiness từ change streams

Stream consumer cần subscribe đúng thời điểm, đọc event có timeout, filter identity và xử lý duplicate/resume semantics.

### 46.4. Flakiness từ TTL

TTL monitor bất đồng bộ; assert eventual deletion với timeout thích hợp hoặc tránh test mỗi class.

### 46.5. Flakiness từ data sharing

Hai tests cùng tạo `_id = "P1"` trên một collection shared có thể va chạm. Use unique IDs/DB names và cleanup controlled.

### 46.6. Flakiness từ parallel JUnit

Parallel test cùng dừng primary hoặc cùng drop collection là không an toàn. Gắn topology mutation tests vào một exclusive suite hoặc sở hữu clusters riêng.

## 47. Đo thời gian chạy test và tối ưu chi phí

### 47.1. Phân rã

```text
T_total =
  Docker environment detection
  + image pull
  + container start
  + MongoDB readiness / election
  + seed/index setup
  + assertions
  + teardown
```

### 47.2. Tối ưu có mục tiêu

- Pin/cache images trong CI.
- Chia suites theo topology.
- Dùng static container cho nhiều tests khi data isolation tốt.
- Tránh drop/recreate quá nhiều indexes trên từng method.
- Dùng Awaitility/condition-based waits thay fixed sleeps.
- Chạy sharding/failover tests theo lịch phù hợp.

### 47.3. Không tối ưu bằng cách bỏ database thật

Đổi transaction integration test thành mock hoàn toàn có thể chạy nhanh hơn nhưng mất đúng semantics cần chứng minh. Phân lớp tests thay vì xóa critical integration coverage.

### 47.4. Không biến test thành performance benchmark

Laptop/CI host có performance biến động. `assert duration < 25ms` dễ flaky. Performance tests cần hạ tầng/benchmark design riêng; integration tests chủ yếu assert correctness, availability trong window hợp lý.

## 48. Checklist chọn topology trước khi viết test

### 48.1. Về tính năng

1. Test có multi-document transaction không?
2. Test có change streams/resume token không?
3. Test có read preference secondary thật không?
4. Test có election/failover/network partition không?
5. Test có majority write concern nhiều nodes không?
6. Test có sharding/mongos/shard key không?
7. Test có Atlas Search/Vector Search không?
8. Test có auth/TLS/X.509 behaviors không?

### 48.2. Về hạ tầng

1. Container runtime sẵn sàng?
2. Testcontainers/Driver/MongoDB versions tương thích?
3. MongoDB image pinned?
4. RAM/disk/network CI đủ không?
5. Startup readiness theo đúng feature?
6. Mọi advertised hosts reachable từ test runner?
7. Data isolation giữa classes/runs?
8. Cleanup cả khi test fail?

### 48.3. Về bằng chứng

1. Test khẳng định behavior thay vì chỉ container.isRunning()?
2. Assertions tránh timing/order không xác định?
3. Có logs/traces nếu startup fail?
4. Có test cases cho failure modes quan trọng?
5. Có kế hoạch separate heavy tests?

## 49. Kịch bản ví dụ: giao dịch chuyển tiền

### 49.1. Bài toán

Chuyển 30 đơn vị từ tài khoản A sang B. Yêu cầu: hoặc cả hai số dư đổi hoặc không đổi.

### 49.2. Topology

**Single-node replica set** đủ để test atomic transaction commit/abort.

### 49.3. Test cases

- Commit thành công, A giảm 30, B tăng 30.
- Exception trong transaction body khiến abort.
- Constraint failure khiến transaction không commit.
- Không để state trung gian xuất hiện sau abort.

### 49.4. Những gì chưa được test

- Primary election giữa commit.
- Unknown commit result do network.
- Replication và majority acknowledgment giữa data-bearing nodes.

Những trường hợp đó cần multi-node/fault test riêng.

## 50. Kịch bản ví dụ: event-driven order service

### 50.1. Bài toán

Khi order chuyển `CREATED` → `PAID`, một change-stream worker cập nhật read model.

### 50.2. Topology

**Single-node replica set** cho kiểm thử emit/consume cơ bản; **multi-node replica set** nếu yêu cầu chứng minh resume sau failover.

### 50.3. Test cases

1. Open watcher.
2. Update order.
3. Assert update event.
4. Check resume token được ghi nhận.
5. Restart consumer, resume đúng vị trí.
6. Assert handler idempotent khi event bị xử lý lại.

### 50.4. Những lỗi dễ bỏ sót

- Watcher subscribe sau khi sự kiện xảy ra.
- Polling không deadline.
- Resume token không được lưu.
- Event handler non-idempotent.
- Oplog bị truncate trước khi consumer resume.

## 51. Kịch bản ví dụ: API vẫn hoạt động sau primary failure

### 51.1. Bài toán

Java driver cần phát hiện primary mới khi node đang primary bị dừng.

### 51.2. Topology

**Three-data-bearing-member replica set**, voting majority 2/3, driver URI có thể resolve mọi advertised host.

### 51.3. Test cases

1. Đợi một primary, hai secondary và replication ổn.
2. Gửi baseline writes với request IDs.
3. Xác định actual primary.
4. Stop primary hoặc planned stepdown trong lab.
5. Poll new primary dưới deadline.
6. Gửi/retry eligible writes sau failover.
7. Verify IDs không trùng.
8. Verify former primary rejoin khi restarts và secondary catch-up.

### 51.4. Không hardcode “A là primary”

Election ban đầu có thể chọn A/B/C. Nếu test luôn stop A, có thể bạn chỉ đang test “mất một secondary”.

### 51.5. Ứng dụng có thể thấy unknown outcome

Nếu write đã gửi trước lỗi mạng, response lost có thể làm trạng thái chưa chắc chắn. Driver retryable writes có semantics riêng; HTTP API vẫn cần business idempotency.

## 52. Kịch bản ví dụ: kiểm thử shard key và cross-shard transaction

### 52.1. Bài toán

Đơn hàng của nhiều tenants được phân bố trên shards; cần kiểm tra routing và transaction xuyên collections/shards.

### 52.2. Topology

**Sharded cluster** với ít nhất hai shards và mongos. Một single-node replica set không đủ.

### 52.3. Test cases

- Collection đã shard theo key phù hợp.
- Inserts vào nhiều shard ranges/chunks theo test setup.
- Query chứa full shard key được route đúng.
- Query thiếu shard key được đo/hiểu scatter semantics.
- Cross-shard transaction commit/abort bảo đảm atomicity theo MongoDB.
- Unique indexes tuân thủ shard key constraints.

### 52.4. Khó khăn

Khởi tạo đầy đủ config server/shards/mongos, data distribution và container networking. Nên dùng fixture được duy trì/test riêng, không tự rải admin commands vào mỗi repository test.

## 53. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách thay |
|---|---|---|
| Dùng standalone cho transaction | Không đúng topology | Single-node RS |
| Dùng standalone cho change streams | Không có oplog stream phù hợp | Replica set/sharded |
| Single-node RS cho failover | Không có secondary bầu primary mới | Three-node RS |
| Single-node RS cho secondary read | Không có data-bearing secondary | Multi-node RS |
| Coi `w:majority` one-node như replication nhiều copies | Kết luận sai durability test | Multi-voter test |
| Dùng `MongoDBContainer` tạo ba instances độc lập rồi gọi là một RS | Không cùng replica set | GenericContainer + init/fixture |
| Hardcode `localhost:27017` | Mapped port động | getReplicaSetUrl/getMappedPort |
| Dùng Docker alias trong host JVM | Host không resolve | Containerized runner/proxy |
| Dùng `directConnection=true` cho failover | Không SDAM replica-set behavior | Full replica set URI |
| Dùng `Wait.forListeningPort()` như proof primary ready | Race | Condition-based topology wait |
| Hardcode `Thread.sleep(3000)` | Flaky CI | Poll with deadline |
| Test chỉ assert container.isRunning | Không test database feature | Real DB operation |
| Bật MongoDB auth env cùng helper mà không kiểm tra RS init | Startup fail | Dedicated secured fixture |
| Tắt TLS validation trong test | Che certificate bug | Correct test CA/SAN |
| Bật reusable containers không cleanup | Data leak | Isolation/disposable CI |
| Tạo MongoClient mới mỗi query | Connection storm/chậm | Long-lived client |
| Quên close MongoClient/cursor | Resource leak | Lifecycle/try-with-resources |
| Gọi `dropDatabase()` với URI sai | Mất dữ liệu | Test-owned namespace guard |
| Sử dụng production credentials | Rủi ro bảo mật | Disposable test secrets |
| Replay test data thiếu IDs độc lập | Duplicate key/flaky | Stable fixture + reset |
| Test TTL đúng từng giây | Flaky do TTL monitor | Eventually assertion |
| Test change stream subscribe quá muộn | Bỏ lỡ event | Subscribe before write |
| Test failover không xác định actual primary | Stop nhầm secondary | Inspect topology first |
| Cho parallel tests cùng điều khiển topology | Cross-test interference | Exclusive fixture |
| Chỉ kiểm tra MongoDB image version, bỏ FCV | Feature mismatch | Version/FCV matrix |
| Chạy sharded suite cho tất cả CRUD tests | Slow CI không cần | Split topology suites |
| Coi Atlas Local là Atlas Cloud đầy đủ | Bỏ sót control-plane differences | Scope Atlas tests |
| Bật logs full command/PII | Lộ dữ liệu | Redact/sanitize |
| Tắt Ryuk/cleanup vô điều kiện | Orphaned resources | Reliable cleanup |
| Dùng Docker privileged socket không hạn chế | Security risk | Scoped runner/runtime |

## 54. Bài tập thực hành

### Bài 1 — Lựa chọn topology

Cho bảy tính năng: CRUD, unique index, transaction, change streams, secondary read, failover và `$vectorSearch`. Hãy chọn topology tối thiểu phù hợp, giải thích từng lựa chọn.

### Bài 2 — Dependencies 2.x

Viết Gradle test dependencies cho `testcontainers-mongodb` và `testcontainers-junit-jupiter` bằng BOM. Giải thích vì sao cần MongoDB Java Driver riêng.

### Bài 3 — Migration 1.x → 2.x

Một test dùng `org.testcontainers.containers.MongoDBContainer` và `org.testcontainers:mongodb`. Hãy cập nhật sang API/module 2.x tương ứng.

### Bài 4 — Port động

Container MongoDB nội bộ nghe 27017 nhưng host mapped port là 49211. Viết Java lấy connection string đúng bằng helper, giải thích vì sao không hardcode 27017 trên host.

### Bài 5 — Standalone

Viết `GenericContainer` cho `mongod --bind_ip_all` không có `--replSet`. Kiểm tra CRUD thành công và transaction bị từ chối theo version.

### Bài 6 — Single-node replica set

Tạo `MongoDBContainer.withReplicaSet()`, dùng `getReplicaSetUrl()`, gọi `hello` và xác nhận `setName` khác null.

### Bài 7 — Transaction commit

Tạo hai accounts, cập nhật cả hai trong một transaction, commit và assert tổng số dư không đổi.

### Bài 8 — Transaction abort

Từ cùng fixture, gọi `abortTransaction()`; assert hai documents không đổi. Giải thích vì sao chưa chứng minh failover recovery.

### Bài 9 — Change streams

Mở stream trước khi insert event; chờ bounded time và assert operation type. Những race conditions nào khiến test flaky?

### Bài 10 — Spring DynamicPropertySource

Viết Spring Boot integration test dùng `@DynamicPropertySource` để truyền MongoDB Testcontainers URI vào `spring.data.mongodb.uri`.

### Bài 11 — ServiceConnection

Chuyển test Spring Boot sang `@ServiceConnection`. Nêu dependency cần thêm và khi nào custom MongoClient bean có thể làm autoconfiguration khác mong đợi.

### Bài 12 — Container lifecycle

So sánh `static @Container` với instance `@Container` và singleton suite-wide về startup time, isolation và cleanup.

### Bài 13 — Docker network aliases

Giải thích vì sao `mongo-a:27017` resolve trong Docker network nhưng không mặc định resolve từ JVM host.

### Bài 14 — Replica set advertised hosts

Một replica set cấu hình `mongo-a/b/c:27017`, JVM host seed bằng localhost mapped ports. Vì sao driver vẫn lỗi server selection sau khi đọc `hello`?

### Bài 15 — Manual replica set

Tạo ba `GenericContainer` với cùng `--replSet rsIT`, gọi `rs.initiate` và dùng condition wait xác nhận một primary, hai secondaries.

### Bài 16 — Read preference

Viết test `ReadPreference.secondary()` trên multi-node RS. Tại sao dùng `secondaryPreferred()` có thể khiến test pass mà không đọc secondary?

### Bài 17 — Election

Trong ba voters, dừng actual primary, chờ election rồi verify writes. Giải thích vì sao không hardcode “container A luôn là primary”.

### Bài 18 — Majority semantics

Vì sao `w:"majority"` trong một single-node RS không chứng minh dữ liệu đã được nhân bản qua network?

### Bài 19 — Toxiproxy

Thiết kế một network partition test sử dụng proxies. Làm sao kiểm tra Java Driver traffic không bypass proxy qua advertised hosts?

### Bài 20 — Sharded cluster

Vẽ topology gồm config server RS, shard A RS, shard B RS và mongos. Ghi thứ tự khởi tạo và Java Driver nên kết nối ở đâu.

### Bài 21 — Shard key

Cho collection orders theo tenantId/orderId; tạo shard key và thiết kế test targeted query, scatter query, unique constraints theo sharded topology.

### Bài 22 — Atlas Local

Tạo `MongoDBAtlasLocalContainer`, mô tả bước tạo Atlas Search index rồi chạy pipeline `$search`. Tại sao `mongo:7.0` thông thường chưa đủ?

### Bài 23 — Authentication

Thiết lập user chỉ đọc trong test database, kiểm tra read thành công, write bị từ chối. Vì sao không cấp root cho application identity?

### Bài 24 — TLS

Tạo test CA và server cert có SAN đúng hostname. Khi JVM kết nối theo alias khác SAN, điều gì xảy ra? Vì sao không bật allowInvalidHostnames?

### Bài 25 — TTL và eventual assertions

Test TTL xóa document nhưng không assert ngay sau đúng 1 giây. Hãy mô tả polling deadline/timeout phù hợp.

### Bài 26 — CI runtime

Một GitLab job báo không tìm thấy Docker runtime. Lập checklist Docker socket/daemon, permissions, image pull, network và cleanup.

### Bài 27 — Data isolation

Hai test classes dùng cùng singleton MongoDB container, đều insert `_id=P1`. Đề xuất ít nhất ba cách tránh xung đột và nêu trade-off.

### Bài 28 — Version matrix

Dự án hỗ trợ MongoDB 7 và 8. Thiết kế smoke/transaction/change-stream/sharding suites trên version matrix, ghi phần phụ thuộc FCV.

### Bài 29 — Failure diagnosis

Container running, port mở, nhưng Java báo `MongoTimeoutException: no primary`. Hãy lập runbook phân biệt init RS chưa xong với hostname không resolve.

### Bài 30 — Capstone

Thiết kế chiến lược integration test cho service Java có:

1. CRUD và schema validation.
2. Transaction đặt hàng.
3. Change streams cập nhật read model.
4. Failover/primary switchover.
5. Read preference secondary.
6. Search/vector search.
7. Sharded routing cho multi-tenant.

Hãy chọn topology cho từng suite, dependencies, readiness criteria, data isolation, CI schedule, timeouts, observability và stop conditions.

## 55. Quy trình thiết kế test dựa trên tính năng

### Bước 1 — Liệt kê behavior cần chứng minh

```text
CRUD đúng?
Transaction atomic?
Stream nhận event?
Replica set failover?
Secondary read stale?
Sharded routing?
Atlas Search?
```

### Bước 2 — Chọn topology nhỏ nhất đủ đúng

Standalone cho behavior đơn giản khi không cần RS; single-node RS cho transactions/streams; multi-node RS cho election/lag; sharded cluster cho mongos/shard key; Atlas Local cho search integration.

### Bước 3 — Pin runtime và versions

Testcontainers BOM, JUnit, MongoDB Driver, MongoDB image, Spring Boot version và FCV nếu liên quan.

### Bước 4 — Dựng bằng API đúng

`MongoDBContainer` cho MongoDB module, `GenericContainer` khi muốn standalone/custom members, `MongoDBAtlasLocalContainer` cho search local, Compose/helper khi topology nhiều services.

### Bước 5 — Giải quyết network trước assertion

Xác nhận advertised hostnames reachable từ Java test runner và member-to-member network. Đừng sửa bằng cách ép `directConnection=true` cho test failover.

### Bước 6 — Chờ readiness theo đúng feature

TCP open → database ready → replica set primary/secondaries → indexes/streams/search ready. Không mặc định một bước đủ cho tất cả.

### Bước 7 — Seed, test, reset

Test-owned namespaces/IDs, data isolation, seed deterministic, assertions rõ và teardown an toàn.

### Bước 8 — Inject fault có kiểm soát

Chỉ khi topology đủ đúng; xác định actual primary, có timeout, telemetry và cleanup.

### Bước 9 — Đọc chứng cứ khi test fail

Container logs, `hello`, `rs.status`, Docker runtime, URI đã redact, server selection errors, stack trace và timeline.

### Bước 10 — Tách CI lanes

Nhanh cho PR; heavy multi-node/sharding/search/failover theo policy để giữ độ tin cậy và thời gian phản hồi hợp lý.

## 56. Tổng kết

**Một MongoDB container không thể đại diện cho mọi topology MongoDB.** Testcontainers cung cấp hạ tầng lặp lại được, nhưng người viết test phải chọn cấu hình dựa trên feature:

- **Standalone:** đủ cho CRUD/index/aggregation thông thường, không đủ cho replica-set-only features.
- **Single-node replica set:** phù hợp transaction, change streams, session và retryable-write protocol, nhưng không có secondary hay failover thật.
- **Multi-node replica set:** cần cho election, secondary reads, lag, majority acknowledgment giữa nhiều data-bearing nodes và client recovery.
- **Sharded cluster:** bắt buộc khi cần kiểm thử shard key, mongos routing và sharded transactions.
- **MongoDB Atlas Local:** dùng cho Atlas Search/Vector Search local trong phạm vi image hỗ trợ, không thay thế toàn bộ managed Atlas Cloud.

**Điểm khó của multi-node test thường không phải tạo ba container mà là networking.** Replica set quảng bá member hostnames qua `hello`; Docker aliases và host mapped ports thuộc hai không gian khác nhau. Muốn test failover thật, runner phải resolve/reach tất cả advertised hosts và dùng full replica set discovery.

**Một test tốt kiểm tra behavior, không chỉ startup.** Đợi readiness bằng điều kiện; assert transaction commit/abort, stream events, server selection, secondary reads và routing phù hợp; tách data giữa tests; dùng deadline và logs khi failure.

**Tối ưu suite bằng phân tầng, không làm sai topology.** Tests đơn giản chạy nhanh trên MongoDBContainer; các bài multi-node/sharding/search chạy riêng khi cần. Kết quả là integration tests vừa gần MongoDB thật vừa ít flaky và có khả năng triển khai trên CI.

## 57. Tài liệu tham khảo

- [Testcontainers Java — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer`, `MongoDBAtlasLocalContainer` và dependency 2.x.
- [Testcontainers Java — JUnit 5 Integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, static/instance lifecycle.
- [Testcontainers Java — Networking and Communicating with Containers](https://java.testcontainers.org/features/networking/): mapped ports, networks, aliases và host access.
- [Testcontainers Java — Wait Strategies](https://java.testcontainers.org/features/startup_and_waits/): readiness và startup timeout.
- [Testcontainers Java — Docker Compose Module](https://java.testcontainers.org/modules/docker_compose/): orchestration nhiều services.
- [Testcontainers Java — Reusable Containers](https://java.testcontainers.org/features/reuse/): rủi ro và chế độ reuse.
- [MongoDB Java Sync Driver — Integration Testing Using Testcontainers](https://www.mongodb.com/docs/drivers/java/sync/current/integrations/testcontainers/): các ví dụ Java và Spring Boot.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và `@DynamicPropertySource`.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): cấu hình properties động.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): điều kiện topology và transaction semantics.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): oplog, resume tokens và deployment support.
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): voting, majority và failover.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary semantics.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): mongos, shards, config servers và shard keys.
- [MongoDB Atlas — Atlas Search](https://www.mongodb.com/docs/atlas/atlas-search/): kiến trúc tìm kiếm và index.
- [MongoDB Atlas — Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/): index và query vector search.

