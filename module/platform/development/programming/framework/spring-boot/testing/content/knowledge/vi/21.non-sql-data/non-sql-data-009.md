# Phiên bản dịch vụ, mapping và giới hạn của bản giả lập khi kiểm thử dữ liệu ngoài SQL

> **Module:** Spring Boot – testing  
> **Nhóm:** Dữ liệu ngoài SQL  
> **Đề bài:** Phiên bản dịch vụ, mapping và giới hạn của bản giả lập  
> **Mục tiêu:** Phân biệt mock, fake, emulator/embedded server và dịch vụ thật; hiểu tại sao phiên bản server, Spring Data mapping, serializer, index, query và transaction semantics quyết định giá trị của test; lựa chọn MongoDB/Redis/Elasticsearch Testcontainers đúng trường hợp. Ví dụ chính dùng Java 17, Spring Boot 3.5 và MongoDB 7 với một unit test service dùng Mockito và integration test chạy engine thật.

## 1. Vấn đề: test giả lập xanh nhưng service production vẫn lỗi

Các dịch vụ lưu trữ ngoài SQL không chỉ là một `Map<String,Object>`. Tùy công nghệ, hệ thống phải tuân theo một giao thức, version, kiểu dữ liệu và hành vi server cụ thể. Một bản giả lập có thể trả các giá trị mà ta kỳ vọng, nhưng lại bỏ qua ràng buộc quan trọng của database thật.

Ví dụ điển hình:

- Mock `MongoRepository` được stub để trả danh sách đơn hàng; test xanh dù field `tenantId` bị ghi thành key `tenant_id` khác với truy vấn thực tế.
- In-memory fake lưu tiền như `BigDecimal`, trong khi MongoDB BSON ở production yêu cầu `Decimal128`; test không thấy lỗi serialization/converter.
- Fake không xây unique index, nên tạo hai order trùng external reference vẫn thành công.
- Một server mô phỏng không có optimistic locking/transaction isolation, nên concurrent update không phát hiện lost update.
- Redis fake dùng `HashMap` không mô phỏng TTL, eviction, atomic Lua, key type và race conditions của Redis thực.
- Elasticsearch mock trả documents theo list cố định; test không bảo vệ analyzer, tokenization, mappings, refresh và relevance scoring của cluster thật.
- Integration test chạy phiên bản MongoDB/Redis/Elasticsearch khác production nên một operator, index option hoặc protocol behavior không khớp.
- Spring Data/Jackson converters đã được cấu hình khác trong test và production; dữ liệu đọc từ server thật bị đổi kiểu, precision hoặc timezone.

**Nguyên tắc trung tâm:** Test chỉ chứng minh hành vi của những thành phần **thực sự được thực thi**. Mock service không chứng minh persistence mapping; fake database không chứng minh server semantics; một container chạy đúng server engine có thể chứng minh nhiều hành vi thật, nhưng vẫn chưa chứng minh cấu hình cluster, bảo mật, hiệu năng và phiên bản production nếu chúng khác nhau.

## 2. Từ mock đến môi trường production-like: bốn mức khác nhau

| Mức | Ví dụ | Có kiểm tra mapping/server thực? | Điểm mạnh | Giới hạn lớn |
| --- | --- | --- | --- | --- |
| **Mock/stub** | Mockito `when(repository.find...)` | Không, trừ khi có thành phần thực được gọi | Rất nhanh, kiểm tra interaction/service logic | Kết quả lập trình sẵn, không chạy query hay serializer |
| **In-memory fake** | `Map<String, Order>` tự viết, fake Redis cache | Thường không | Test nghiệp vụ, kiểm soát lỗi và thời gian | Bỏ qua dialect/protocol/index/collation/TTL/locking |
| **Embedded/emulator** | Embedded Mongo alternative, Redis emulator, local API emulator | Một phần, tùy implementation/version | Thuận tiện offline, mô phỏng một số API | Không chắc tương đương full server, có behavior không được hỗ trợ |
| **Dịch vụ thật dùng cho test** | MongoDB/Redis/Elasticsearch qua Testcontainers | Có, trong version/config container | Thực thi driver, wire protocol, mapper, index/query/locking thật | Không tự tái tạo cluster, managed features, IAM, tải lớn |
| **Staging/production-like** | Cluster riêng có policy/data tương ứng | Cao hơn nếu cấu hình đồng nhất | TLS, networking, multi-node, upgrade, operational behavior | Chậm/tốn kém, cần cô lập dữ liệu và quyền |

Một bản fake có thể là lựa chọn **đúng** cho unit test. Sai lầm là gắn nhãn “đã test MongoDB 7” cho một test mà MongoDB server chưa từng khởi động.

### 2.1. Mock không phải fake, fake không phải emulator

- **Mock** tập trung vào tương tác, ví dụ ghi nhận `verify(repository).findBy...` và trả về dữ liệu định trước.
- **Stub** cung cấp response định trước, không nhất thiết kiểm tra interaction; Mockito thường hỗ trợ cả mock lẫn stubbing.
- **Fake** là implementation thay thế có hành vi thực nhưng giản lược, ví dụ lưu record trong `Map`.
- **Emulator** tái hiện một phần giao thức/API/hành vi dịch vụ, có thể chạy process độc lập; mức tương thích phải được chứng minh.
- **Testcontainers** không phải “mock Docker”. Container chạy **dịch vụ thật** trong môi trường test, với limitations do topology/config/data.
- **Contract test** đối chiếu yêu cầu client–provider ở ranh giới; contract test không tự thay thế integration test đặc tính persistence.

### 2.2. Test nào trả lời câu hỏi nào?

```text
OrderLookupService
     |
     +-- Mockito OrderRepository
     |      → Service truyền tenant/status đúng?
     |      → OrderSummary mapping logic đúng?
     |
     +-- MongoDB Testcontainers (MongoDB 7)
     |      → Query dùng đúng BSON field names?
     |      → Decimal128/Instant mapping đúng?
     |      → Unique index, @Version có hiệu lực?
     |      → Driver/server đang ở version nào?
     |
     +-- Staging MongoDB cluster
            → Auth/TLS/replica set/production indexes đúng?
            → Upgrade, network failover và load behavior đúng?
```

Sự khác biệt giữa các câu trả lời này phải được thể hiện rõ trong tên test, báo cáo QA và pipeline CI.

## 3. Phiên bản nào thực sự quan trọng?

Một ứng dụng Spring Boot tương tác với NoSQL thường có **nhiều phiên bản cùng lúc**, không chỉ một dependency trong `pom.xml`:

1. **Spring Boot version:** điều khiển auto-configuration và một bộ dependency versions được quản lý.
2. **Spring Data module version:** ví dụ Spring Data MongoDB, Redis, Elasticsearch; điều khiển query derivation, mapping, repositories và converters.
3. **Java client/driver version:** MongoDB Java Driver, Lettuce/Jedis, Elasticsearch Java API Client; điều khiển wire protocol, authentication, serialization, retry và error translation.
4. **Server version:** MongoDB major/minor, Redis 6/7/8, Elasticsearch cluster 7/8/9 tùy product; điều khiển API, storage behavior và query syntax.
5. **Server configuration/topology:** standalone/replica set/sharded MongoDB, Redis standalone/cluster/sentinel, Elasticsearch multi-node, TLS/auth/ACL, collation, timezones.
6. **Data/index/schema version:** collection validators, indexes, aliases, analyzers, serializer schema, key naming và migration scripts.
7. **External hosted service version:** managed providers có feature flags, API compatibility layers, access policies hoặc engine forks khác vanilla OSS.

**Một cặp version không xác định toàn bộ hành vi.** MongoDB 7 single-node trong container và MongoDB 7 sharded production cluster có thể giống ở lệnh CRUD nhưng khác ở routing, shard keys, transactions, latency và failover.

### 3.1. Ma trận version kiểm thử nên ghi lại

| Mục | Ví dụ minh họa | Kiểm chứng bằng gì? |
| --- | --- | --- |
| Spring Boot | `3.5.0` | `pom.xml`/dependency tree |
| Java runtime | `17` | `java -version` |
| MongoDB server | `7.0.x` | Container image và `db.runCommand({buildInfo:1})` |
| MongoDB driver | Version do Boot BOM quản lý | `mvn dependency:tree` |
| MongoDB topology | Test single node; production replica set | Integration environment metadata |
| Index policy | Compound unique tenant + externalRef | Server index catalog/duplicate-write test |
| BSON currency | `Decimal128` | Inspect raw `org.bson.Document` |
| Schema rollout | Versioned migrations/initialization | Migration/rollout job và catalog assertions |
| Security | Test-only connection | Auth/TLS staging test riêng |

Ví dụ image `mongo:7.0` là một **dòng version minh họa**, không có nghĩa mọi production MongoDB đều nên dùng MongoDB 7. Khi team nâng server version, cập nhật ma trận và test các chức năng được sử dụng, không nâng image tùy tiện chỉ vì có tag mới.

### 3.2. Không dùng image tag trôi nổi

`mongo:latest`, `redis:latest` hoặc `elasticsearch:latest` dễ khiến CI hôm nay chạy engine khác hôm qua. Với integration tests, pin major/minor hoặc digest theo chính sách tổ chức. Khi nâng version, chạy version matrix trong một khoảng chuyển tiếp:

```text
Target production now: MongoDB version A
Next planned target:   MongoDB version B

CI:
  1) Fast unit tests với mocks/fakes
  2) Container integration tests trên A
  3) Compatibility/upgrade tests trên B
  4) Staging rollout và telemetry checks
```

**Không suy luận mọi API cũ đều hoạt động như cũ trên server mới**. Có thể có deprecation, thay mặc định, removed server command, index/aggregation behavior khác hoặc driver compatibility rule mới.

### 3.3. Đọc thông tin version ngay từ server

Ví dụ MongoDB shell:

```javascript
db.runCommand({ buildInfo: 1 })
```

Lệnh trả metadata có `version`, `gitVersion`…; muốn test đặc tính cụ thể, assert phiên bản server thực chứ không chỉ nhìn POM. MongoDB driver version không đồng nghĩa MongoDB server version.

Với Redis, có thể đọc `INFO server` (phụ thuộc quyền ACL). Với Elasticsearch, gọi root/cluster information endpoint hoặc Java client tương ứng; thông tin cần được kiểm tra từ **service thật trong test**, không lấy từ chuỗi giả lập tự gán.

## 4. Mapping: Java object không phải là BSON/Redis bytes/Elasticsearch document

Trong ứng dụng Spring Data, thông thường có nhiều bước chuyển đổi:

```text
Java entity / DTO
   │
   ▼
Spring Data MappingContext + MongoConverter / RedisSerializer / ES mapping
   │
   ▼
Wire type: BSON document / Redis bytes / JSON request
   │
   ▼
Real server storage/index/query
   │
   ▼
Driver deserialize + Spring Data mapping
   │
   ▼
Java object returned to service
```

Một fake lưu trực tiếp Java object vào `Map` có thể bỏ qua **cả hai chiều chuyển đổi**. Vì vậy fake không phát hiện được việc đổi tên field, precision overflow, missing/null, enum converter, TTL expiry hoặc index mismatch.

### 4.1. MongoDB: Spring property name khác BSON field

Ví dụ:

```java
@Field("tenant_id")
private String tenantId;
```

Java property là `tenantId` nhưng MongoDB field là `tenant_id`. Khi dùng Spring Data derived query `findByTenantId(...)`, mapping infrastructure chuyển property thành field name phù hợp. Khi dùng raw BSON `Document` hoặc native JSON query, phải biết key thật.

Một test mock repository trả thẳng `OrderDocument` không chạy mapper. Integration test nên kiểm tra **raw server BSON** để xác nhận `tenant_id` tồn tại và `tenantId` không xuất hiện ngoài ý muốn.

### 4.2. MongoDB: BigDecimal không tự biến thành Decimal128 trong fake

Spring Data MongoDB có type conversion. Với money/amount, muốn lưu số `BigDecimal` dưới BSON `Decimal128`, chỉ định tường minh:

```java
@Field(value = "total_amount", targetType = FieldType.DECIMAL128)
private BigDecimal totalAmount;
```

Sau khi `MongoTemplate` ghi vào MongoDB thật, kiểm tra raw type:

```java
Document raw = mongoTemplate.getCollection("orders")
        .find(new Document("_id", "ord-1"))
        .first();

assertThat(raw.get("total_amount"))
        .isInstanceOf(Decimal128.class);
```

Đây là **snippet trong test có `mongoTemplate` đã inject**, cần imports `org.bson.Document`, `org.bson.types.Decimal128` và AssertJ. Project đầy đủ ở phần 8 có case này. Một fake Java `Map<String,BigDecimal>` không chứng minh kiểu BSON thật.

### 4.3. MongoDB: `@Id String`, ObjectId và identifier conversions

MongoDB mặc định lưu primary key tại `_id`, không nhất thiết có field `id`. Spring Data Mongo có quy tắc cho `String` identifiers: nếu String biểu diễn được ObjectId hợp lệ, mapper có thể convert sang BSON `ObjectId`; các chuỗi khác có thể giữ dạng string tùy mapping/cấu hình.

Vì vậy không nên assert rằng mọi `@Id String` luôn được lưu BSON String. Nếu consumer có requirement lưu đúng raw string ID, cân nhắc `@MongoId` hoặc mapping rõ ràng và test với cả identifier nhìn giống 24 ký tự hex. Ví dụ dùng IDs `"ord-1"`, không giống ObjectId, để các raw BSON assertions có cách hiểu nhất quán.

### 4.4. MongoDB: Instant, Date, precision

Java `Instant` chứa precision cao hơn nhiều representation BSON Date vốn có độ phân giải milliseconds. Khi ghi/đọc, nanoseconds có thể bị cắt/chuyển đổi theo driver/converter. Test nên chọn một mốc cố định:

```java
Instant.parse("2026-06-17T10:00:00Z")
```

Nếu API yêu cầu microsecond/nanosecond fidelity, cần storage design khác hoặc field phụ; không để fake `Map` lừa rằng nanoseconds đã được bảo toàn trong BSON Date. Đừng dùng `Instant.now()` rồi assert equality chính xác qua DB nếu clock precision không được kiểm soát.

### 4.5. Null và missing field không giống nhau

MongoDB document có thể:

```json
{"_id":"ord-1","note":null}
```

hoặc:

```json
{"_id":"ord-1"}
```

Trong raw storage, một field vắng mặt và field hiện diện `null` có thể khác nhau về query matching, indexes và migration. Một converter có thể bỏ null fields khi ghi, nhưng fake Java object không thể hiện sự khác biệt. Cần test `raw.containsKey("note")` khi missing-vs-null là phần của contract.

### 4.6. Redis: bytes + serializer mới là storage contract

Redis không lưu Java object. Một `RedisTemplate<String, Order>` có thể dùng JDK serialization, JSON, String hoặc custom serializer. Cùng object nhưng bytes khác có thể khiến dữ liệu cũ không đọc được sau deploy:

```text
Java Order
   ├── JDK serializer  → binary encoding
   ├── Jackson JSON    → JSON bytes / optional type metadata
   └── String format   → UTF-8 fields

Redis stores bytes; fake Map stores Java Order directly.
```

Vì vậy test thật phải xác nhận key prefix, serialization format, TTL và backward compatibility khi đổi serializers. Không dùng dữ liệu production trong test để “thử parser”. Với polymorphic JSON type metadata, cân nhắc security của deserialization và versioning.

### 4.7. Elasticsearch: mapping + analyzer + refresh

Elasticsearch `keyword` và `text` không tương đương; chúng khác về tokenization, filtering và aggregation. Một mock search response có thể trả đúng id nhưng bỏ qua toàn bộ:

- Index mapping, dynamic fields, keyword subfields.
- Analyzer/tokenizer, lowercase, stemming, accent folding.
- Query DSL semantics, relevance scoring và tie-breaking.
- Refresh policy: newly indexed document không nhất thiết searchable lập tức.
- Alias/rollover và index templates.
- Version/cluster compatibility.

Nếu search behavior quan trọng, cần integration test với Elasticsearch container/cluster phù hợp và kiểm tra mapping + query thực. Không dùng `List.stream().filter(s -> s.contains(...))` làm bằng chứng analyzer behavior.

## 5. Những giới hạn thường không có trong một bản giả lập

| Khía cạnh | Fake/mock thường làm gì | Real service có thể làm gì |
| --- | --- | --- |
| Wire protocol | Không gửi request qua driver | Validate type, command, encoding, auth |
| Schema/BSON mapping | Lưu Java object nguyên vẹn | Convert sang BSON/JSON/bytes rồi đọc lại |
| Server version | Không có server | Hỗ trợ/loại bỏ features theo version |
| Index | Tìm bằng `Map`/`List` | Unique, compound, TTL, full-text indexes |
| Constraints | Không kiểm tra | Reject duplicate/invalid writes hoặc enforce validation |
| Ordering | Thường dùng insertion order | Order theo query/sort/collation, ties không ổn định |
| Concurrency | Một thread/synchronized fake | Concurrent writes, atomic ops, optimistic conflict |
| TTL | Không hết hạn hoặc xóa ngay bằng fake clock | Expiry có lịch thực, eventual cleanup |
| Transactions | Không có hoặc đơn giản | Support tùy topology/engine/config |
| Search relevance | Substring matching | Analyzer, scoring, refresh và shards |
| Serialization | Object equals | Network bytes/BSON types/converters |
| Retry/timeouts | Trả success ngay | Network timeout, connection exhaustion, failover |
| Security | Bỏ qua user/ACL | Authentication, TLS, roles, namespaces |
| Observability | Không có metadata | Latency, errors, metrics, logs, traces |
| Operational upgrades | Không đổi behavior | Migration/compatibility/rollover |

**Hành vi giả lập càng đơn giản, phạm vi kiểm thử càng cần ghi tên chính xác.** Unit test fake là một công cụ hợp lệ khi nó bảo vệ business logic; sự tương thích server phải được bảo vệ ở tầng khác.

## 6. Ví dụ sai và đúng ở ranh giới service

Giả sử service cần trả danh sách đơn hàng mới của một tenant. Một unit test Mockito:

```java
when(repository.findByTenantIdAndStatusOrderByCreatedAtDesc(
        "team-a", OrderStatus.NEW))
        .thenReturn(List.of(orderB, orderA));
```

Như vậy test có thể xác nhận service chuyển đúng tenant và enum, sắp xếp kết quả theo danh sách trả về, nhưng **không** kiểm tra Spring Data tạo query BSON đúng trường `tenant_id`, không xác nhận MongoDB sắp xếp `created_at` và không xác nhận driver mapping `Decimal128`.

Một integration test dùng MongoDB Testcontainers:

```text
1. Lưu ba BSON documents vào engine thật
2. Query qua repository thật
3. Kiểm tra filter tenant/status và descending createdAt
4. Inspect raw BSON types
5. Kiểm tra index duplicate write và optimistic update
6. Ghi lại server version thực qua buildInfo
```

Đó là những điều mock không thể chứng minh, dù stub có nhiều dữ liệu đến đâu.

## 7. Dự án mẫu Spring Boot 3.5 + MongoDB Testcontainers

Project chạy được với **Java 17, Maven, Spring Boot 3.5.0**, Spring Data MongoDB và Testcontainers MongoDB. Tất cả dữ liệu giả ở database test-only. Docker/container runtime phải hoạt động cho integration tests; unit test Mockito không cần Docker.

### 7.1. Cây thư mục

```text
non-sql-version-mapping-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/nosql/
    │       ├── NoSqlLabApplication.java
    │       ├── OrderStatus.java
    │       ├── OrderDocument.java
    │       ├── OrderRepository.java
    │       ├── OrderSummary.java
    │       └── OrderLookupService.java
    └── test/
        └── java/com/example/nosql/
            ├── OrderLookupServiceUnitTest.java
            └── OrderMongoIntegrationTest.java
```

Mỗi public class/record/enum nằm trong file riêng đúng tên, cùng package `com.example.nosql`. Project không khai báo HTTP controller vì mục tiêu là **storage mapping và service boundary**, không phải route/web contract. Không có production credentials hoặc external managed endpoint.

### 7.2. `pom.xml`

```xml
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
    <artifactId>non-sql-version-mapping-lab</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
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

`spring-boot-starter-data-mongodb` mang Spring Data MongoDB/driver; `spring-boot-starter-test` mang JUnit Jupiter/Mockito/AssertJ; `spring-boot-testcontainers` có Spring Boot service connection support; Testcontainers MongoDB + JUnit 5 khởi động server test.

**Không thêm MongoDB driver version thủ công** nếu đang dùng Spring Boot dependency management, trừ khi đã có version compatibility strategy. MongoDB server version là chuyện của container image, không phải POM.

### 7.3. `NoSqlLabApplication.java`

```java
// src/main/java/com/example/nosql/NoSqlLabApplication.java
package com.example.nosql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoSqlLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NoSqlLabApplication.class, args);
    }
}
```

### 7.4. `OrderStatus.java`

```java
// src/main/java/com/example/nosql/OrderStatus.java
package com.example.nosql;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 7.5. `OrderDocument.java`: tường minh BSON mapping

```java
// src/main/java/com/example/nosql/OrderDocument.java
package com.example.nosql;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "orders")
@CompoundIndex(
        name = "uq_tenant_external_ref",
        def = "{'tenant_id': 1, 'external_ref': 1}",
        unique = true)
public class OrderDocument {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("external_ref")
    private String externalRef;

    @Field(
            value = "total_amount",
            targetType = FieldType.DECIMAL128)
    private BigDecimal totalAmount;

    @Field("created_at")
    private Instant createdAt;

    @Field("status")
    private OrderStatus status;

    @Version
    private Long version;

    protected OrderDocument() {
    }

    public OrderDocument(
            String id,
            String tenantId,
            String externalRef,
            BigDecimal totalAmount,
            Instant createdAt,
            OrderStatus status) {
        this.id = id;
        this.tenantId = tenantId;
        this.externalRef = externalRef;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getExternalRef() { return externalRef; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }
    public Long getVersion() { return version; }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
```

**Mapping có chủ đích:**

- `@Document(collection="orders")` dùng collection `orders`.
- `@Id String id` đi vào `_id`. IDs trong tests dùng `ord-...` để không vô tình được chuyển thành ObjectId.
- `tenantId` ↔ BSON `tenant_id`; `externalRef` ↔ `external_ref`.
- `BigDecimal totalAmount` được lưu là BSON `Decimal128`, khác fake lưu trực tiếp Java object.
- `Instant createdAt` được lưu dạng date/time BSON phù hợp, với precision quan trọng khi test timestamp.
- `status` được map thành giá trị enum string trong BSON theo converter mặc định của ví dụ.
- `@Version Long version` cho optimistic locking khi save/update; không tự biến hệ thống thành có distributed transaction.
- `@CompoundIndex` yêu cầu uniqueness của **cặp** tenant + external reference, không cấm hai tenants khác nhau dùng cùng external ref.

**Cảnh báo quan trọng:** Spring Data MongoDB không tự tạo mọi indexes theo annotation một cách vô điều kiện. Auto index creation bị tắt mặc định ở nhiều phiên bản Spring Data; test sẽ bật `spring.data.mongodb.auto-index-creation=true` một cách **tường minh**. Production nên quản lý index rollout/creation theo quy trình schema migration riêng. Có annotation `@CompoundIndex` trong code chưa chứng minh database thật đã có index đó.

### 7.6. `OrderRepository.java`

```java
// src/main/java/com/example/nosql/OrderRepository.java
package com.example.nosql;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument>
    findByTenantIdAndStatusOrderByCreatedAtDesc(
            String tenantId, OrderStatus status);
}
```

Spring Data Mongo query derivation phải ánh xạ Java properties `tenantId`, `status` và `createdAt` qua mapping context để tạo MongoDB query/sort trên fields `tenant_id`, `status` và `created_at`. Mockito stub không có khả năng chứng minh chuyện này.

### 7.7. `OrderSummary.java`

```java
// src/main/java/com/example/nosql/OrderSummary.java
package com.example.nosql;

import java.math.BigDecimal;

public record OrderSummary(
        String id,
        String externalRef,
        BigDecimal totalAmount) {
}
```

Response domain DTO cố tình không lộ tenant, status, version hay persistence internal fields ngoài yêu cầu. Việc không có tenant trong summary **không phải** authorization; service phải bảo đảm tenant input đã được xác thực ở boundary thật.

### 7.8. `OrderLookupService.java`

```java
// src/main/java/com/example/nosql/OrderLookupService.java
package com.example.nosql;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {

    private final OrderRepository repository;

    public OrderLookupService(OrderRepository repository) {
        this.repository = repository;
    }

    public List<OrderSummary> latestNew(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Tenant is required");
        }

        return repository
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        tenantId, OrderStatus.NEW)
                .stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getExternalRef(),
                        order.getTotalAmount()))
                .toList();
    }
}
```

Service có một **hợp đồng unit-test được**: validate tenant không rỗng, truyền đúng tenant/status cho repository và map returned objects thành summary. Nó không tự làm database queries; trách nhiệm đó thuộc repository/driver/server.

**Không dùng raw `X-Tenant-Id` do client tự nhập làm quyền đọc dữ liệu thật.** Một ứng dụng production cần lấy tenant từ authenticated principal/verified token và enforce resource-level authorization. Ví dụ này chỉ tập trung vào mapping và test boundary.

## 8. Unit test với Mockito: nhanh nhưng giới hạn rõ ràng

### 8.1. `OrderLookupServiceUnitTest.java`

```java
// src/test/java/com/example/nosql/OrderLookupServiceUnitTest.java
package com.example.nosql;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class OrderLookupServiceUnitTest {

    private OrderDocument order(
            String id, String externalRef,
            String amount) {
        return new OrderDocument(
                id,
                "team-a",
                externalRef,
                new BigDecimal(amount),
                Instant.parse("2026-06-17T10:00:00Z"),
                OrderStatus.NEW);
    }

    @Test
    void passesTenantAndMapsRepositoryResults() {
        OrderRepository repository =
                mock(OrderRepository.class);
        OrderLookupService service =
                new OrderLookupService(repository);

        when(repository
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        "team-a", OrderStatus.NEW))
                .thenReturn(List.of(
                        order("ord-2", "ext-2", "20.00"),
                        order("ord-1", "ext-1", "10.00")));

        List<OrderSummary> result =
                service.latestNew("team-a");

        assertThat(result)
                .extracting(OrderSummary::id)
                .containsExactly("ord-2", "ord-1");

        assertThat(result.get(0).totalAmount())
                .isEqualByComparingTo("20.00");

        verify(repository)
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        "team-a", OrderStatus.NEW);
    }

    @Test
    void rejectsMissingTenantWithoutQueryingRepository() {
        OrderRepository repository =
                mock(OrderRepository.class);
        OrderLookupService service =
                new OrderLookupService(repository);

        assertThatThrownBy(() -> service.latestNew(" "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Tenant is required");

        verifyNoInteractions(repository);
    }
}
```

**Đã chứng minh:** service validation, argument passing, DTO mapping và returned list order **theo stub đã tạo**.

**Chưa chứng minh:** Query trong MongoDB sort đúng thật, Spring Data map BSON field đúng, unique index tồn tại, Decimal128 không mất precision, optimistic lock hoạt động hoặc server hỗ trợ feature.

Một test fake in-memory có thể tạo `List` rồi filter/sort bằng Java, nhưng vẫn không thực thi MongoDB BSON, index và query semantics. Không đổi một stub phức tạp thành “MongoDB emulator” chỉ vì nó có nhiều methods.

### 8.2. Khi nào nên dùng fake thay mock?

Fake có ích khi nhiều business services cùng truy cập một persistence port mà cần state qua nhiều calls, nhưng test không nhắm MongoDB behavior. Ví dụ một `InMemoryOrderStore` lưu bản sao `Order` trong `Map` để test workflow phát sự kiện hoặc tính toán giá trị.

Giới hạn giả lập phải được ghi rõ:

- Có xử lý duplicate key hoặc không?
- Có copy data khi save/find hay trả cùng reference mutable?
- Có cùng ordering/null/missing semantics không?
- Có thực thi optimistic version check không?
- Có mô phỏng TTL/collision/concurrency không?

Nếu câu trả lời là “không”, **đừng** dùng test fake để chứng minh các điều ấy. Thay bằng integration test thật ở phần tiếp theo.

## 9. Integration test trên MongoDB 7 thật bằng Testcontainers

### 9.1. `OrderMongoIntegrationTest.java`

```java
// src/test/java/com/example/nosql/OrderMongoIntegrationTest.java
package com.example.nosql;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest(properties = {
        "spring.data.mongodb.auto-index-creation=true",
        "spring.data.mongodb.database=orders_test"
})
@Import(OrderLookupService.class)
@Testcontainers
class OrderMongoIntegrationTest {

    @Container
    @ServiceConnection
    static final MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @Autowired
    OrderRepository repository;

    @Autowired
    OrderLookupService service;

    @Autowired
    MongoTemplate mongoTemplate;

    @BeforeEach
    void cleanDataWithoutDroppingIndexes() {
        repository.deleteAll();
    }

    private OrderDocument order(
            String id, String tenant, String externalRef,
            String amount, String instant, OrderStatus status) {
        return new OrderDocument(
                id,
                tenant,
                externalRef,
                new BigDecimal(amount),
                Instant.parse(instant),
                status);
    }

    @Test
    void storesExpectedBsonFieldNamesAndDecimal128() {
        OrderDocument created = repository.save(
                order("ord-1", "team-a", "ext-1",
                        "12.50", "2026-06-17T10:00:00Z",
                        OrderStatus.NEW));

        assertThat(created.getVersion()).isNotNull();

        Document raw = mongoTemplate.getCollection("orders")
                .find(new Document("_id", "ord-1"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("tenant_id"))
                .isEqualTo("team-a");
        assertThat(raw.getString("external_ref"))
                .isEqualTo("ext-1");
        assertThat(raw.containsKey("tenantId")).isFalse();
        assertThat(raw.get("total_amount"))
                .isInstanceOf(Decimal128.class);
        assertThat(((Decimal128) raw.get("total_amount"))
                .bigDecimalValue())
                .isEqualByComparingTo("12.50");
        assertThat(raw.getDate("created_at").toInstant())
                .isEqualTo(
                        Instant.parse("2026-06-17T10:00:00Z"));

        OrderDocument reloaded =
                repository.findById("ord-1").orElseThrow();

        assertThat(reloaded.getTotalAmount())
                .isEqualByComparingTo("12.50");
        assertThat(reloaded.getStatus())
                .isEqualTo(OrderStatus.NEW);
    }

    @Test
    void derivedQueryUsesMappedFieldsAndRealSorting() {
        repository.saveAll(List.of(
                order("ord-1", "team-a", "ext-1", "10.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW),
                order("ord-2", "team-a", "ext-2", "20.00",
                        "2026-06-17T12:00:00Z", OrderStatus.NEW),
                order("ord-3", "team-a", "ext-3", "30.00",
                        "2026-06-17T13:00:00Z", OrderStatus.PAID),
                order("ord-4", "team-b", "ext-4", "40.00",
                        "2026-06-17T14:00:00Z", OrderStatus.NEW)));

        assertThat(service.latestNew("team-a"))
                .extracting(OrderSummary::id)
                .containsExactly("ord-2", "ord-1");

        assertThat(service.latestNew("team-b"))
                .extracting(OrderSummary::id)
                .containsExactly("ord-4");
    }

    @Test
    void compoundUniqueIndexRejectsOnlySameTenantDuplicate() {
        repository.save(
                order("ord-1", "team-a", "same-ref", "10.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW));

        repository.save(
                order("ord-2", "team-b", "same-ref", "20.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW));

        assertThatThrownBy(() -> repository.save(
                order("ord-3", "team-a", "same-ref", "30.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void optimisticVersionRejectsStaleUpdate() {
        repository.save(
                order("ord-1", "team-a", "ext-1", "10.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW));

        OrderDocument first =
                repository.findById("ord-1").orElseThrow();
        OrderDocument stale =
                repository.findById("ord-1").orElseThrow();

        first.setStatus(OrderStatus.PAID);
        repository.save(first);

        stale.setStatus(OrderStatus.CANCELLED);
        assertThatThrownBy(() -> repository.save(stale))
                .isInstanceOf(
                        OptimisticLockingFailureException.class);

        assertThat(repository.findById("ord-1")
                .orElseThrow().getStatus())
                .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void verifiesActualMongoServerMajorVersion() {
        Document info = mongoTemplate.getDb()
                .runCommand(new Document("buildInfo", 1));

        assertThat(info.getString("version"))
                .startsWith("7.");
    }
}
```

**Tập test có chủ đích:**

1. `storesExpectedBsonFieldNamesAndDecimal128` chứng minh raw BSON names/type/date và Java readback.
2. `derivedQueryUsesMappedFieldsAndRealSorting` chứng minh derived repository query lọc theo tenant/status và sorting dựa trên server.
3. `compoundUniqueIndexRejectsOnlySameTenantDuplicate` bảo vệ **compound unique index** mà mock không biết đến; giá trị giống nhau ở hai tenants được chấp nhận, cùng tenant thì bị từ chối.
4. `optimisticVersionRejectsStaleUpdate` bảo vệ `@Version` và optimistic write failure với hai instances đọc từ cùng version cũ.
5. `verifiesActualMongoServerMajorVersion` xác nhận test đang kết nối MongoDB dòng 7.x, không tự tin chỉ vì một chuỗi image trong code.

### 9.2. Vì sao `@DataMongoTest` vẫn cần `@Import`?

`@DataMongoTest` nạp MongoDB mapper/template và repositories, nhưng **không quét mọi business `@Service`**. Ta thêm `@Import(OrderLookupService.class)` vì integration test muốn đi qua service thật → repository thật → MongoDB thật.

Khác với unit test, `OrderRepository` không bị mock. Nếu thay repository bằng `@MockitoBean` ở class này, các test không còn xác minh BSON/index/server đúng mục tiêu.

### 9.3. Tác dụng của `@ServiceConnection`

`@ServiceConnection` trên static `MongoDBContainer` cho Spring Boot biết MongoDB connection details từ container đã chạy; ứng dụng test không hard-code `localhost:27017` hoặc lấy URI production.

`spring.data.mongodb.database=orders_test` chỉ chọn database name test, không tự xác thực container. Container có database ephemeral theo lifecycle; URI/port do Testcontainers cấp. Tránh thêm `spring.data.mongodb.uri` production vào `src/test/resources`.

### 9.4. Vì sao cần `auto-index-creation=true`?

`@CompoundIndex` mô tả index mapping, nhưng tự tạo index bằng annotation **không mặc định bật** trong Spring Data MongoDB 3+.

Test đặt:

```properties
spring.data.mongodb.auto-index-creation=true
```

để đảm bảo unique index hiện diện trong ephemeral test database. Production nên có cách quản lý index có kiểm soát (migration/initialization), nhất là với collection có data sẵn và các thao tác rebuild index tốn thời gian.

**Rất quan trọng:** `repository.deleteAll()` trong `@BeforeEach` xóa documents, không drop collection/index. Nếu test dùng `mongoTemplate.dropCollection(...)` sau khi indexes đã tạo, các indexes có thể mất; đừng khẳng định unique test sẽ fail đúng khi index không còn.

### 9.5. Optimistic locking không phải transaction cross-document

`@Version` bổ sung version check vào update của một entity, ngăn một số stale writes. Nó không mặc nhiên đảm bảo atomicity của một workflow sửa hai collections, hoặc rollback side effect khi một remote call fail.

MongoDB multi-document transactions có requirements về deployment/topology, replica set/sharded cluster support và session configuration. Nếu production dùng transactions, cấu hình container replica set theo Testcontainers/Spring Data docs và test explicit transaction boundaries. Bài mẫu **không** tuyên bố có multi-document transactions chỉ vì test `@Version` pass.

### 9.6. Chạy tests và cách đọc kết quả

```bash
java -version
mvn -version

# Unit test không cần MongoDB/Docker:
mvn -Dtest=OrderLookupServiceUnitTest test

# Integration test cần Docker/container runtime:
docker info
mvn -Dtest=OrderMongoIntegrationTest test

# Cả hai nhóm:
mvn test
```

Project có **7 phương thức `@Test`**: 2 trong `OrderLookupServiceUnitTest` và 5 trong `OrderMongoIntegrationTest`. Đây là số method theo mã minh họa, **không phải log build đã chạy**. Maven có thể cần tải dependencies, Docker image có thể cần pull; output, port và thời gian chạy khác theo môi trường.

Nếu Docker unavailable, integration test có thể fail startup; không đổi nó sang mocked repository rồi ghi báo cáo “MongoDB integration PASS”. Báo cáo CI phải phân biệt unit-only, integration pass, integration skipped và integration failed.

## 10. Những giới hạn của MongoDB container so với production

Dù chạy MongoDB engine thật trong Docker, test một container vẫn chưa chứng minh mọi behavior:

| Điều cần kiểm tra | MongoDB container đơn lẻ | Khi nào cần kiểm thử khác |
| --- | --- | --- |
| Basic CRUD & BSON mapping | Tốt | Khi có production-specific converters |
| Query/aggregation operators | Tốt trong version được pin | Khi operator phụ thuộc Atlas/server flavor |
| Unique/compound indexes | Có thể kiểm tra | Khi dữ liệu cũ hoặc migration tạo index phức tạp |
| Optimistic locking | Có thể kiểm tra | Khi có nhiều services/concurrent workloads |
| Multi-document transactions | Cần topology/replica-set phù hợp | Test transactions trên replica set |
| Sharding/cluster routing | Không mặc định | Cluster integration test |
| TLS/IAM/ACL | Không mặc định | Staging/security tests |
| Failover/elections | Không với single node | Multi-node failure tests |
| Large datasets/performance | Không đại diện | Load/EXPLAIN/profiling tests |
| Managed extensions | Không nhất thiết | Provider-specific staging |

**Một test nhanh về đúng BSON không tương đương stress test**. Tách yêu cầu correctness khỏi performance, operability và security.

### 10.1. Version pin và upgrade test

Nếu production đang chạy MongoDB version A, container test phải ưu tiên version A. Khi lên B, CI chạy cả A/B cho các repository quan trọng. Thay đổi có thể ảnh hưởng default behavior, query planner, feature compatibility version (FCV), auth mode, indexes hoặc driver support.

Không chạy thử production upgrade bằng cách dùng credentials production từ laptop/CI test. Dùng isolated staging database hoặc container/cluster test-only.

### 10.2. Mapping converter thay đổi qua phiên bản

Một class Java không đổi vẫn có thể đổi BSON output nếu mapping/converter, Mongo driver hoặc default type representation thay đổi qua dependency update. Điều cần kiểm tra:

- Raw `_id` type: String/ObjectId.
- `BigDecimal`: String vs Decimal128.
- `Instant`: BSON Date precision/timezone.
- Collections/maps: nested fields và keys có dấu chấm/dollar.
- Null/missing semantics.
- Enum naming và custom converters.
- Version field và optimistic locking semantics.
- Index definitions và collection validators.

Test bằng *raw Document assertions* cộng round-trip Java object; chỉ round-trip có thể bỏ sót trường hợp hai chiều cùng sai.

## 11. Redis: giới hạn fake đối với TTL, atomicity và serialization

Redis khác MongoDB về data model. Một fake Java Map thường mô phỏng `GET`/`SET`, nhưng Redis thật có TTL, eviction policy, server time, key types, transactions/pipelines, pub/sub, Lua scripts/Redis functions và cluster routing.

### 11.1. TTL là một contract thời gian

Giả sử code:

```java
redisTemplate.opsForValue()
        .set("reset-token:demo", "value",
                Duration.ofMinutes(5));
```

Đây là snippet minh họa, không nằm trong runnable MongoDB project; cần `RedisTemplate` và imports. Trong fake, bạn có thể thiết lập expiry dựa vào injected `Clock`, nhưng nó **không** chứng minh Redis server thật set expiration đúng, hoặc key biến mất đúng tại từng millisecond.

Redis TTL thường là **thời hạn** chứ không phải lời hứa xóa key trên disk đúng tuyệt đối tại timestamp: expiration có cơ chế lazy/active deletion và behavior khi truy cập key. Test nên xác minh `TTL/PTTL`/`GET` behavior theo contract, không assert một scheduler thread cụ thể đã xóa ngay khi clock qua deadline.

### 11.2. Atomicity của `SET NX EX` và Lua

Một fake:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

không bảo đảm atomicity nếu nhiều threads chạy đồng thời. Redis có các operations atomic theo lệnh server, ví dụ `SET key value NX EX seconds`. Với distributed lock/idempotency, một unit fake không chứng minh race-safety.

Test Redis thật cần hai clients/concurrent operations, key expiry, retry policy và cleanup. Không dựa vào fake đơn luồng để kết luận lock là đúng. Lưu ý một Redis lock đơn giản chưa chắc cung cấp đầy đủ failure semantics cho hệ thống phân tán.

### 11.3. Key serialization/prefix

`StringRedisSerializer`, Jackson JSON serializers và custom binary formats tạo các bytes khác nhau. Một cache có thể hoạt động trong Java fake nhưng production không đọc được key do prefix, charset hoặc serializer thay đổi.

Test thực phải kiểm tra:

- Keys thực sự được ghi theo prefix/namespace mong đợi.
- Serializer đọc lại được dữ liệu cũ/versioned.
- TTL được set đúng và không vô tình thành permanent.
- Null/value sentinel, key type và Unicode encoding đúng.
- Cache eviction/fallback không làm mất business invariant.

### 11.4. Testcontainers Redis

Spring Boot có thể lấy connection details từ Redis container; với Testcontainers `GenericContainer`, metadata image/name là yếu tố cần rõ khi dùng `@ServiceConnection(name = "redis")`. Đây là **kiến trúc mở rộng**, không tự khai báo Redis dependencies trong MongoDB project ở phần 7.

Test Redis integration nên dùng version phù hợp production và một `RedisTemplate` thật, không `Map`. Cluster/sentinel behavior, ACL, TLS và failover vẫn cần môi trường cao hơn.

## 12. Elasticsearch: mapping, analyzer và refresh không thể giả bằng list

Với search index, kết quả không đơn giản là “chuỗi chứa keyword”. Một fake có thể dùng Java `contains` và sắp xếp id, trong khi Elasticsearch thực sử dụng:

- `text` vs `keyword` mappings, multi-fields.
- Analyzer/normalizer, case folding, stop words, n-gram, stemming.
- Query DSL match/term/range/exists và semantics của arrays/null.
- Scoring `_score`, tie-breakers, pagination/search_after.
- Refresh: vừa index xong chưa chắc document đã searchable ngay.
- Index templates, aliases, shard settings, mappings evolution.
- Cluster version/API compatibility và authorization.

### 12.1. Một test sai lầm

```java
List<Product> matches = products.stream()
        .filter(p -> p.name().contains("cafe"))
        .toList();
```

Đây là snippet Java minh họa. Nó không chứng minh production Elasticsearch analyzer xử lý “café/Cafe/cafe” như mong muốn. Muốn kiểm tra search semantics, tạo test index với mapping/analyzer production-like, index fixtures, refresh theo contract, gửi query thật và assert ids/scores hoặc ordering theo điều kiện có kiểm soát.

### 12.2. Version mismatch và query DSL

Elasticsearch Java client version, server version và JSON DSL API có compatibility constraints. Một mock client trả `SearchResponse` có thể pass dù cluster không chấp nhận request hoặc index mapping thay đổi. Cần chạy engine/server version tương thích với production (ví dụ Elasticsearch Testcontainers), và test mapping creation, query, sorting, refresh.

**Không ép một fake search service bắt chước toàn bộ query DSL**. Điều đó tốn công và thường không sát engine thực. Fake cho business flow, container/cluster cho search contract.

### 12.3. Đừng coi container single-node là cluster test

Shards, replicas, node failure, rolling upgrades, role-based access và storage performance cần một staging/cluster scenario riêng. Single-node container đủ cho index mappings và nhiều DSL assertions, không đủ cho failover và sizing.

## 13. Version compatibility và mapping checklist theo dịch vụ

| Dịch vụ | Version cần đối chiếu | Mapping cần test | Behavior không nên giao cho fake |
| --- | --- | --- | --- |
| **MongoDB** | Server, driver, Spring Data Mongo | BSON fields, Decimal128, ID type, indexes, converters | Aggregations, unique indexes, optimistic locking, transactions |
| **Redis** | Server, Lettuce/Jedis, Spring Data Redis | Key prefixes, serializers, TTL units, hash fields | Atomic NX, Lua, expiration, eviction, pub/sub |
| **Elasticsearch** | Server/cluster, Java client, Spring Data ES | Index mappings, analyzers, aliases, nested fields | Query DSL, scoring, refresh, pagination |
| **Cassandra** | Cluster, driver, schema/CQL | Partition/clustering keys, codecs, TTL | Consistency levels, tombstones, paging |
| **Neo4j** | Server, Bolt driver, SDN mapping | Nodes/relationships, labels, Cypher | Transaction/constraint/Cypher planner |
| **DynamoDB** | Service API version/emulator capabilities, SDK | Attribute values, key/index schemas | Conditional writes, TTL eventual behavior, streams, IAM |
| **OpenSearch** | Server/client and managed distro | Index settings/DSL/analyzers | Scoring, refresh, permissions, extensions |

Bảng chỉ hướng dẫn **chọn tầng kiểm thử**; không giả định các sản phẩm trên chia sẻ một abstraction đủ thay thế lẫn nhau. Với database mục tiêu thực, hãy dùng đúng official docs và compatibility matrix của version hiện hành.

## 14. Lựa chọn giữa unit test, slice, integration và staging

| Mục tiêu | Công cụ khuyến nghị | Tín hiệu PASS có ý nghĩa |
| --- | --- | --- |
| Service validation, DTO mapping | JUnit + Mockito | Service logic và interactions |
| Workflow cần state nhẹ | In-memory fake qua persistence port | Domain flow dưới fake contract |
| MongoDB mapper/repository | `@DataMongoTest` + MongoDB container | BSON/query/unique/locking trên engine test |
| Redis key/TTL/atomicity | Redis container + Spring Data Redis | Key bytes/TTL/command behavior |
| Elasticsearch query/relevance | ES container + real client | Index mapping/DSL behavior |
| HTTP/controller + persistence | `@SpringBootTest` với container | Spring wiring và request flow |
| Auth/TLS/cluster failover | Isolated staging | Operational/security/topology behavior |
| Migration/upgrade | Old/new version matrix, staging | Backward compatibility và rollout |
| Performance | Representative dataset + metrics | Latency/throughput resource behavior |

**Không cần mọi unit test chạy Docker.** Điều quan trọng là mỗi claim “đã test” có môi trường phù hợp và không lấy một mock result để thay bằng chứng server.

### 14.1. `@DataMongoTest` không tự động rollback như JPA slice

Khác `@DataJpaTest` thường transactional rollback, MongoDB test slice **không tự bảo đảm** mọi writes được rollback sau từng test. Nếu tests chia sẻ container/database, cần cleanup dữ liệu rõ ràng và tránh phụ thuộc thứ tự.

Trong project, `@BeforeEach repository.deleteAll()` xóa records trước mỗi test nhưng không drop indexes. Với nhiều collections, cần database/collection isolation strategy và xóa data test-only; đừng dùng `dropDatabase()` trên kết nối chưa xác minh là ephemeral.

### 14.2. Testcontainers cũng có giới hạn tài nguyên

Docker runtime, image pull, CPU/memory, network và platform security có thể làm tests chậm hoặc fail khi environment thiếu. Phân biệt:
- **Test code fail** vì mapping/index/query sai.
- **Environment fail** vì Docker unavailable/registry access denied.
- **Skipped tests** vì integration profile chưa bật.

Không tự diễn giải “tests skipped” thành integration PASS. Đặt tên/tag jobs rõ ràng và đưa logs có ích nhưng không tiết lộ secrets.

### 14.3. Test với embedded/emulated services

Nếu tổ chức bắt buộc dùng emulator do CI hạn chế Docker, nên:

1. Ghi tên emulator, version và capabilities hỗ trợ.
2. Liệt kê chỗ không tương thích hoặc chưa test.
3. Giữ một số smoke contract tests chạy real service ở pipeline khác.
4. Không viết workaround emulator làm thay đổi behavior production khi không cần thiết.
5. Khi nâng driver/server, cập nhật compatibility tests.

Đối với MongoDB, một embedded alternative không phải MongoDB production engine trừ khi nó thực sự chạy server version tương ứng. Một “compatible API” chỉ bảo đảm subset được document.

## 15. Negative tests cần thiết vì fake thường bỏ sót chúng

### 15.1. Duplicate key và unique index

Trong MongoDB sample, unique index là **cặp `(tenant_id,external_ref)`**. Test positive cho hai tenants khác nhau cùng externalRef và negative cho cùng tenant. Fake `HashMap` dùng key chỉ `externalRef` có thể **cấm sai** cross-tenant duplication; fake dùng key `id` lại có thể **cho phép sai** duplicate business key.

### 15.2. Stale optimistic update

Một fake object reference nếu hai reads trả **cùng instance**, thay đổi lần 1 sẽ làm thay đổi cả “stale” instance, khiến không thể phát hiện conflict. Test Mongo thật tạo hai instances đọc riêng với cùng version, update một, rồi save instance cũ để mong `OptimisticLockingFailureException`.

### 15.3. Mapping mismatch khi đổi field name

Khi chuyển `@Field("tenant_id")` thành `@Field("tenantId")`, một mock có thể vẫn trả expected. Test Mongo raw BSON và derived query phải nhận ra schema contract đã đổi. Để test backward compatibility, có thể seed các documents phiên bản cũ bằng raw driver, rồi đọc bằng mapper mới.

### 15.4. Time precision và null

Với `Instant`, test nanosecond boundary nếu contract yêu cầu; nếu lưu BSON Date milliseconds, phải định nghĩa cách truncate/round. Với missing/null, assert raw fields chứ không chỉ Java object fields.

### 15.5. TTL và expiry

Với Redis/Mongo TTL index, đừng assert “dữ liệu biến mất đúng millisecond” khi engine có background deletion behavior. Test store contract, TTL configuration và eventual expiry trong một bounded window; dùng fake clock riêng cho business deadline logic.

### 15.6. Network failures và cancellation

Mock throws một exception không chứng minh driver có cùng exception class trong real timeout/connection loss. Có thể dùng fault injection hoặc Testcontainers `Toxiproxy`/network proxy ở integration tier. Đừng dùng `Thread.sleep` để tạo race conditions không kiểm soát hoặc hard-code network timeout phi thực tế.

## 16. Thử tình huống phiên bản trước/sau khi nâng service

Giả sử team chuẩn bị nâng MongoDB major version. Một upgrade-readiness checklist:

1. Liệt kê server versions cũ/mới và dependency versions của Boot/Spring Data/driver.
2. Đọc release notes của server và driver, tập trung các command/features ứng dụng dùng.
3. Pin container version A và B trong jobs tách biệt.
4. Seed datasets có BSON types/old documents thật sự đại diện schema.
5. Chạy raw BSON mapping, derived repository queries, aggregations, indexes, sorting và optimistic locking.
6. Chạy authorization/transaction tests nếu application phụ thuộc replica set/ACL.
7. Chạy migration/index build rehearsal với dữ liệu test-only.
8. Test rollback/downgrade **nếu** được vendor hỗ trợ; không giả định downgrade luôn an toàn.
9. Đo latency, query plans, key/index size trên staging.
10. Rollout canary với metrics/rollback runbook.

**Không dùng tag `latest` để đại diện future server.** Version target phải là version team thực sự dự định triển khai, có pin và ngày review.

### 16.1. Spring Boot upgrade cũng là mapping upgrade

Một thay đổi Spring Data minor/major có thể đổi converter behavior, query derivation, warnings hoặc default serializers. Vì vậy upgrade Spring Boot không đơn thuần là cập nhật dependencies và rerun pure unit tests; integration tests trên engine thật có giá trị lớn trong việc phát hiện regression.

### 16.2. Backward-compatible documents

Ứng dụng rolling deployment có thể có instance cũ và mới cùng đọc/ghi dữ liệu. Hãy có fixtures cho:

- Documents version cũ thiếu field mới.
- Unknown fields do version mới thêm.
- Old enum values không còn trong code mới.
- Decimal128 vs String legacy.
- Changed key naming conventions.
- Optional/null semantics và timestamp precision.
- Index migration khi data cũ đã vi phạm uniqueness.

Một fake tạo object theo class hiện tại thường không tạo được những trường hợp cũ này. Test bằng raw BSON fixtures trong test container, xác định rõ fallback/migration policy.

## 17. Triệu chứng thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra hoặc sửa |
| --- | --- | --- |
| Mockito test xanh, Mongo query trả rỗng | Property ↔ BSON field mapping sai | Inspect raw BSON + real repository query |
| BigDecimal ra String thay Decimal128 | Chưa cấu hình converter/target type | `@Field(targetType=DECIMAL128)` + raw BSON test |
| Tạo duplicate vẫn thành công | Index chưa được tạo, index khác contract | Index management test + duplicate write |
| Test dùng Mongo nhưng nhận “connection refused” | Container chưa chạy/URI sai | `@ServiceConnection` và runtime logs |
| Service test thiếu bean | `@DataMongoTest` không scan ordinary service | `@Import` đúng service, không nạp toàn bộ app |
| Unit fake giữ object reference, optimistic test không fail | Không có copy/version semantics | Real Mongo `@Version` test |
| Mongo test suite ảnh hưởng lẫn nhau | Không rollback mặc định/cleanup sai | Delete test data, không drop indexes |
| Driver mới không đọc document cũ | BSON/serializer schema đổi | Legacy fixtures + version matrix |
| Mongo transaction fail trong test | Test container topology chưa phải replica set | Configure appropriate replica-set test environment |
| Redis TTL fake pass nhưng production key không hết hạn | Chưa set TTL, serializer hoặc expiry semantics sai | Redis container PTTL/GET test |
| Redis lock bị double-acquired | In-memory check-then-put không atomic | Real Redis atomic command/concurrency test |
| Elasticsearch “cafe” tìm sai “café” | Analyzer/mapping khác fake | Real index/analyzer/query test |
| Elasticsearch document vừa ghi chưa searchable | Refresh timing khác fake | Refresh policy hoặc bounded await |
| Cluster staging khác container behavior | TLS, roles, shards/replicas, cloud features khác | Staging-specific tests |
| CI báo xanh nhưng integration không chạy | Docker unavailable, tags skipped | Phân biệt PASS/FAIL/SKIPPED trong report |
| Test quá chậm vì Docker mỗi method | Container lifecycle bất hợp lý | Static container per test class, reuse policy an toàn |
| Version upgrade phá query | Server/driver/mapper compatibility | Pin A/B matrix, release notes, contract tests |

## 18. Bài tập thực hành

### Bài 1: Phát hiện field mapping sai

Trong nhánh học thử, đổi `@Field("tenant_id")` thành một tên khác. Chạy `OrderLookupServiceUnitTest` và `OrderMongoIntegrationTest`.

**Điều cần giải thích:** Unit mock có thể vẫn pass vì không dùng converter/real DB. Integration test raw BSON phải bắt được key mismatch hoặc query không trả đúng dữ liệu nếu schema/fixture được dựng độc lập.

### Bài 2: Đổi Decimal128 sang storage kiểu khác

Thử bỏ `targetType=FieldType.DECIMAL128` khỏi entity. Kiểm tra raw `total_amount` type và round-trip. Ghi nhận behavior thực theo Spring Data version; không suy đoán BigDecimal bắt buộc trở thành BSON String ở mọi release.

### Bài 3: Tắt auto index creation

Bỏ test property `spring.data.mongodb.auto-index-creation=true`. Trong một database sạch không có index, duplicate write có thể thành công. Giải thích vì sao `@CompoundIndex` annotation tự nó chưa đảm bảo một index thật đã tồn tại.

**Lưu ý:** Khi thực hành, dùng container/database test-only mới, không reuse một collection có index đã tạo ở lượt trước; nếu không, test có thể vẫn fail duplicate và tạo kết luận nhầm.

### Bài 4: Optimistic locking và hai copies

Đọc hai `OrderDocument` copies, sửa/save copy thứ nhất rồi sửa/save copy thứ hai. Dự đoán exception và phiên bản cuối cùng. Viết test không dựa vào việc fake trả cùng object reference.

### Bài 5: Phiên bản server

Chạy query `buildInfo` từ MongoDB test container, so sánh server version với image tag. Nếu đổi image A→B, hãy ghi kết quả rõ, không dùng một string constant trong test thay server query.

### Bài 6: Redis TTL

Thiết kế một `CachePort` cho business code. Test deadline logic với fake clock; test serializer + TTL + key name bằng Redis container. Xác định rõ điều nào mỗi tầng đã chứng minh.

### Bài 7: Elasticsearch search

Tạo index test-only có mapping `text` với analyzer đã chọn. Index ba documents, refresh theo contract, query bằng client thật và assert IDs. So sánh với fake Java `contains` để thấy sự khác biệt.

### Bài 8: Backward compatibility

Dùng raw `Document` insert một order với schema cũ (`total_amount` String), rồi đọc bằng converter mới. Xác định policy: chấp nhận và convert, migration một lần, hay reject có error rõ. Viết test theo policy thật của ứng dụng.

## 19. Câu hỏi tự kiểm tra

**1.** Tại sao Mockito `OrderRepository` pass không chứng minh mapping MongoDB đúng?

**Đáp án:** Mockito không tạo BSON, không gửi query qua driver/server và không xây indexes; nó chỉ trả stubbed objects.

**2.** Testcontainers có phải là một mock MongoDB không?

**Đáp án:** Không. Nó chạy MongoDB server thật trong container, nhưng thường có ít node/config/data hơn production.

**3.** `@DataMongoTest` có tự scan `@Service` thường không?

**Đáp án:** Không như full application context. Nếu cần service thật trong Mongo slice, `@Import` service phù hợp.

**4.** `@Field(targetType=FieldType.DECIMAL128)` bảo vệ điều gì?

**Đáp án:** Chỉ dẫn Spring Data converter lưu `BigDecimal` dưới BSON Decimal128. Test raw Document xác nhận server đã nhận đúng loại dữ liệu.

**5.** Có `@CompoundIndex(unique=true)` trong code đã chắc MongoDB có index chưa?

**Đáp án:** Chưa. Index creation phải được cấu hình/khởi tạo thực; auto index creation không luôn bật mặc định.

**6.** Vì sao một fake Redis Map không chứng minh distributed lock đúng?

**Đáp án:** Check-then-put của Map không tương đương atomic command Redis dưới concurrency, và fake thường không mô phỏng TTL/failure.

**7.** Vì sao test Elasticsearch bằng `String.contains` không đủ?

**Đáp án:** Nó bỏ qua index mappings, analyzer, query DSL, scoring và refresh semantics của engine.

**8.** Container MongoDB 7 có chứng minh production multi-node failover không?

**Đáp án:** Không. Single-container tests có giá trị cho CRUD/mapping/index/query, không tự kiểm chứng cluster elections, sharding và operational failures.

**9.** Tại sao test cần version matrix khi nâng Spring Boot hoặc MongoDB?

**Đáp án:** Mapper/driver/server changes có thể thay BSON, command support, indexes hoặc defaults; chạy trên cả version cũ và target mới giúp phát hiện regression.

**10.** Khi nào fake vẫn tốt hơn container?

**Đáp án:** Khi mục tiêu là logic thuần, workflow state hoặc xử lý exception được kiểm soát, không cần chứng minh storage semantics. Giữ container cho các hợp đồng của dịch vụ thật.

## 20. Checklist code review và CI

- [ ] Test name/report nói rõ đang dùng mock, fake, emulator hay real service.
- [ ] Server version/container image pin theo target compatibility matrix.
- [ ] Driver và Spring Data versions lấy từ BOM/dependency tree rõ ràng.
- [ ] BSON/Redis bytes/ES index mappings được test trên engine thật khi là contract.
- [ ] Có test cả serialize và deserialize/round-trip với expected độc lập.
- [ ] Null/missing, UUID/ObjectId, Decimal128, date precision, enum converters được xem xét.
- [ ] Unique/index/TTL features được khởi tạo và kiểm tra, không chỉ khai annotation.
- [ ] Mongo integration test giữ DataLoader/repository/mapper thật, không mock persistence boundary.
- [ ] Có negative tests duplicate, stale update, wrong type và missing context khi phù hợp.
- [ ] Không trông chờ `@DataMongoTest` rollback giống `@DataJpaTest`.
- [ ] Không dùng shared mutable fake references để kết luận concurrency correctness.
- [ ] Redis TTL/atomicity và Elasticsearch analyzer/refresh được test bằng dịch vụ thật khi cần.
- [ ] Test data thuộc database/index/namespace riêng, không kết nối production.
- [ ] Docker unavailable ≠ integration PASS; CI phân biệt FAIL/SKIPPED rõ.
- [ ] Cluster/auth/TLS/failover/performance được test riêng ở staging khi liên quan.
- [ ] Upgrade server/driver/mapper có version matrix và legacy fixtures.
- [ ] Không lưu token/password/PII thật trong test fixtures hoặc logs.

## 21. Tài liệu tham khảo

- [Spring Boot 3.5 – Auto-configured Data MongoDB Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataMongoTest`, MongoTemplate và Mongo repositories.
- [Spring Boot 3.5 – Testcontainers and Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` và `MongoConnectionDetails`.
- [Spring Data MongoDB – Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): BSON, `@Field`, `@Id` và conversions.
- [Spring Data MongoDB – Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): `BigDecimal`/`Decimal128`, custom conversion rules.
- [Spring Data MongoDB – Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): default auto-index behavior, index lifecycle.
- [Spring Data MongoDB – Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `@Version`, version checks và write acknowledgement.
- [Testcontainers for Java – MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer` và replica-set notes.
- [MongoDB Manual – BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): BSON Date, ObjectId, Decimal128.
- [MongoDB Manual – Indexes](https://www.mongodb.com/docs/manual/indexes/): compound/unique/TTL index behavior.
- [Redis Documentation – EXPIRE and TTL](https://redis.io/docs/latest/commands/expire/): expiry semantics và key lifetime.
- [Elasticsearch Reference – Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html): mappings, text/keyword và analyzer behavior.

**Kết luận:** **Một bản giả lập là đúng khi nó phục vụ mục tiêu unit test, nhưng không được dùng làm bằng chứng rằng dịch vụ NoSQL thật tương thích về version, mapping và server behavior.** Dùng mock/fake cho business logic, MongoDB/Redis/Elasticsearch thật trong Testcontainers cho những hợp đồng của driver, mapper, query, indexes và TTL, và dùng staging cluster cho auth, failover, nâng version và hiệu năng. Ghi rõ mức độ bằng chứng của mỗi test để tránh “xanh giả”.