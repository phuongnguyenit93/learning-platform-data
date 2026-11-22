# @DataCassandraTest, @DataCouchbaseTest hoặc @DataLdapTest khi ứng dụng có tích hợp

## 1. Bài toán và mục tiêu

Trong một ứng dụng Spring Boot, dữ liệu không chỉ nằm ở cơ sở dữ liệu quan hệ. Một hệ thống có thể dùng Apache Cassandra để lưu sự kiện/telemetry theo partition, Couchbase để lưu document JSON và LDAP để truy vấn danh bạ tổ chức. Mỗi hệ thống có mô hình dữ liệu, cách tạo kết nối, consistency, indexing, security và lifecycle khác nhau.

Dùng `@SpringBootTest` cho mọi test repository thường nạp nhiều bean không liên quan: REST controller, message consumer, scheduling, cloud clients. Ngược lại, dùng Mockito mock hoàn toàn repository thì không biết mapping có đúng hay query có chạy trên engine thực không. Spring Boot cung cấp ba **test slice** cho các tích hợp này:

- `@DataCassandraTest`: tập trung Spring Data Cassandra, mapping `@Table`, Cassandra templates và repositories.
- `@DataCouchbaseTest`: tập trung Spring Data Couchbase, mapping `@Document`, Couchbase templates và repositories.
- `@DataLdapTest`: tập trung Spring LDAP / Spring Data LDAP, mapping `@Entry`, `LdapTemplate` và repositories, với tùy chọn LDAP nhúng khi có UnboundID.

Trong bài, bạn sẽ:

1. Hiểu **test slice** khác với full application context và pure unit test ra sao.
2. Xác định **dependency**, **annotation import** và **auto-configuration** theo Spring Boot 3.5, Java 17.
3. Biết vì sao Cassandra/Couchbase cần một engine thực hoặc container, trong khi LDAP có thể dùng UnboundID nhúng.
4. Viết test kiểm mapping, repository CRUD, entity/document/entry, search/query, connection và cleanup.
5. Dùng `Testcontainers`, `@ServiceConnection` và `@Testcontainers` khi test Cassandra/Couchbase.
6. Dùng `spring.ldap.embedded.base-dn` và LDIF fixture để test LDAP offline, không cần tài khoản enterprise directory thật.
7. Tránh giả định **rollback** cho NoSQL slice như `@DataJpaTest`; thiết kế dữ liệu test cách ly.
8. Phân biệt Cassandra partition/query semantics, Couchbase KV/index/query consistency và LDAP DN/base/LDAP filter.
9. Biết khi nào chuyển sang `@SpringBootTest` hoặc contract/integration test môi trường thật.
10. Xử lý lỗi phổ biến: `NoSuchBeanDefinitionException`, không kết nối được service, keyspace/bucket/DN sai, permission, schema/index và version mismatch.

**Phiên bản áp dụng:** Java 17+, Spring Boot **3.5.x** (ví dụ Maven dùng **3.5.16**), JUnit Jupiter, Spring Data, Testcontainers tương thích BOM của Boot 3.5. Trong Spring Boot 4, nhiều test annotations được chuyển sang các module/package mới; phải đối chiếu tài liệu đúng major version.

**Nguyên tắc:** Chọn slice khi ứng dụng thật sự dùng công nghệ đó và muốn kiểm **repository/mapping/connection với engine phù hợp**. Không thêm starter Cassandra/Couchbase/LDAP chỉ để học ba annotation trong một ứng dụng không dùng chúng.

## 2. Test slice là gì và không phải gì?

### 2.1. Ba ranh giới kiểm thử

```text
Pure unit test:
  JUnit -> domain/service -> Mockito fake repository
  (không mapping, không database, không Spring context)

NoSQL/LDAP test slice:
  JUnit -> Spring Data repository/template thật
                |
                v
          Cassandra/Couchbase/LDAP test instance
  (có mapping/query/connection, không cần cả ứng dụng)

Full integration test:
  HTTP/controller -> service -> repository -> data store
  + security, properties, transactions, messaging, external adapters
```

`@DataCassandraTest`, `@DataCouchbaseTest` và `@DataLdapTest` **không phải annotations giả lập dữ liệu tự động**. Chúng quyết định Spring context nào được load và cấu hình những client/templates/repositories liên quan. Dữ liệu và dịch vụ thực tế được cung cấp bởi Testcontainers, embedded LDAP hoặc test environment riêng.

### 2.2. Nguyên tắc auto-configuration trong Boot 3.5

Các slice dùng chiến lược chỉ bật những auto-configurations cần thiết; Spring Boot thường áp dụng `@OverrideAutoConfiguration(enabled=false)`, type exclude filters và `@ImportAutoConfiguration`. Trong danh mục test slices của Boot 3.5:

| Slice | Template/repository quan trọng | Các auto-configurations tiêu biểu |
| --- | --- | --- |
| `@DataCassandraTest` | `CassandraTemplate`, có thể có reactive templates/repos khi có dependency | `CassandraAutoConfiguration`, `CassandraDataAutoConfiguration`, Cassandra reactive & repository configs, SSL/cache |
| `@DataCouchbaseTest` | `CouchbaseTemplate` / `ReactiveCouchbaseTemplate`, repositories | `CouchbaseAutoConfiguration`, Couchbase data/reactive/repository configs, SSL/cache |
| `@DataLdapTest` | `LdapTemplate`, LDAP repositories/entities | `LdapAutoConfiguration`, `LdapRepositoriesAutoConfiguration`, `EmbeddedLdapAutoConfiguration` khi điều kiện phù hợp |

Khi `spring-boot-testcontainers` hiện diện, mỗi slice còn có **optional `ServiceConnectionAutoConfiguration`** để nhận connection details từ các container đã được khai báo. Optional không đồng nghĩa tự khởi động Docker hay tạo container nếu bạn không cấu hình.

### 2.3. Component scanning bị giới hạn

Tài liệu Boot 3.5 nói rõ các slice này thường **không scan regular `@Component` và `@ConfigurationProperties` beans** như full app. Tùy slice, chúng ưu tiên các domain mapping types và repositories.

```java
@DataCassandraTest
class TelemetryRepositoryTest {
    @Autowired TelemetryRepository repository;

    // @Autowired MyBusinessService service;
    // Thường KHÔNG tự được scan vào slice.
}
```

Đoạn này chỉ là minh họa dependency graph. Nếu muốn kiểm mapping/repository, không cần business service. Nếu thực sự cần một collaborator nhỏ, dùng `@Import(MyService.class)` hoặc `@MockitoBean` theo ranh giới; với `@ConfigurationProperties` sử dụng `@EnableConfigurationProperties(MyStoreProperties.class)`.

**Không** thêm `@ComponentScan("com.example")` để sửa mọi lỗi thiếu bean: cách đó phá ý nghĩa slice và có thể kéo cả các thành phần sản xuất vào test.

### 2.4. Không phối hợp ba slice annotations trên cùng class

Spring Boot không hỗ trợ tạo một test bằng cách gắn `@DataCassandraTest`, `@DataCouchbaseTest` và `@DataLdapTest` đồng thời. Mỗi slice có bootstrap/override auto-configuration riêng; nếu ứng dụng cần kiểm phối hợp Cassandra + Couchbase + LDAP trong một workflow, dùng `@SpringBootTest` và test infrastructure thực tế, hoặc chọn một slice rồi import có chủ đích vài auto-configurations của phần khác theo tài liệu.

Dùng **một test class/một boundary**, có dữ liệu riêng và cleanup rõ.

## 3. Bảng quyết định công nghệ

| Câu hỏi | Cassandra | Couchbase | LDAP |
| --- | --- | --- | --- |
| Mục tiêu thường gặp | Wide-column, partitioned records, write-heavy | JSON documents, key-value và N1QL/SQL++ query | Directory entries, DN, attributes, người dùng/nhóm |
| Mapping annotation | `@Table` (Spring Data Cassandra) | `@Document` (Spring Data Couchbase) | `@Entry` (Spring Data LDAP) |
| Template | `CassandraTemplate` | `CouchbaseTemplate` / reactive variant | `LdapTemplate` |
| Repository | `CassandraRepository`/reactive | `CouchbaseRepository`/reactive | `LdapRepository` |
| Slice | `@DataCassandraTest` | `@DataCouchbaseTest` | `@DataLdapTest` |
| Test service | Cassandra container/cluster thật | Couchbase container/cluster thật | UnboundID embedded hoặc LDAP test server |
| Default embedded in-memory do slice cấp? | **Không** | **Không** | **Có thể**, nếu UnboundID và base DN được cấu hình |
| Data cleanup | Delete partition key rows / isolate keyspace | Delete document IDs / bucket, collection | LDAP unbind DN / clean LDIF fixture |
| SQL/JPA rollback mặc định? | Không | Không | Không |
| Chính yếu khi fail | Contact point/keyspace/schema/consistency | Bucket/index/query scope/KV consistency | Base DN/schema/filter/bind credentials/TLS |

### 3.1. Khác @DataJpaTest và H2

`@DataJpaTest` thường bật test-managed transaction rồi rollback sau test; H2 có thể tự tạo embedded database. Không áp tư duy đó lên `@DataCassandraTest`, `@DataCouchbaseTest` và `@DataLdapTest`:

- Cassandra không sử dụng JPA `EntityManager` hoặc JDBC local rollback như JPA.
- Couchbase KV write có durability/consistency và transaction APIs riêng; không có TestContext rollback miễn phí cho mỗi test.
- LDAP add/modify/delete entry không tự rollback như một JPA test transaction.
- `@Transactional` không biến tất cả NoSQL operations thành một JDBC transaction có rollback tự động.

Vì vậy, khi test `save` rồi thấy record, bạn phải **xóa** record hoặc chạy trên môi trường ephemeral thay vì mặc định chờ TestContext rollback.

### 3.2. Chỉ dùng khi ứng dụng thực sự có tích hợp

Nếu ứng dụng chỉ có MySQL, không cần thêm cả ba starter vào test classpath. Chúng làm dependency graph phức tạp, tăng startup time và có thể kích hoạt connection attempts không cần. Chỉ thêm đúng Spring Data module của backend thực dùng, kiểm ở tầng repository, rồi kết hợp unit/integration tests theo rủi ro.

## 4. Packages và phiên bản: Spring Boot 3.5 khác Boot 4

Ba import đúng cho **Spring Boot 3.5**:

```java
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
```

Những packages này nằm trong Spring Boot test auto-configuration của major 3.x. Trong Boot 4, module splits và namespace của test annotations thay đổi, ví dụ các package tương ứng có tiền tố `org.springframework.boot.data.cassandra.test.autoconfigure`. Không copy code từ tài liệu Boot 4 sang Boot 3.5 mà không cập nhật imports/dependencies.

Các Maven dependencies thường dùng:

| Mục đích | Maven groupId:artifactId |
| --- | --- |
| Cassandra data access | `org.springframework.boot:spring-boot-starter-data-cassandra` |
| Cassandra reactive | `org.springframework.boot:spring-boot-starter-data-cassandra-reactive` |
| Couchbase data access | `org.springframework.boot:spring-boot-starter-data-couchbase` |
| Couchbase reactive | `org.springframework.boot:spring-boot-starter-data-couchbase-reactive` |
| LDAP data access | `org.springframework.boot:spring-boot-starter-data-ldap` |
| JUnit + AssertJ + Spring Boot Test | `org.springframework.boot:spring-boot-starter-test` (test scope) |
| Testcontainers auto service connections | `org.springframework.boot:spring-boot-testcontainers` (test scope) |
| Testcontainers JUnit Jupiter | `org.testcontainers:junit-jupiter` (test scope) |
| Cassandra Testcontainers module (1.x) | `org.testcontainers:cassandra` (test scope) |
| Couchbase Testcontainers module (1.x) | `org.testcontainers:couchbase` (test scope) |
| Embedded LDAP UnboundID | `com.unboundid:unboundid-ldapsdk` (test scope) |

**Chú ý:** Danh sách module Testcontainers nêu cho BOM 3.5/Testcontainers 1.x. Các phiên bản Testcontainers 2.x thay đổi tọa độ một số modules; luôn kiểm `mvn dependency:tree` và module coordinates ứng với dependency management đang dùng, không trộn major vô tình.

## 5. @DataCassandraTest — mô hình và phạm vi

### 5.1. Cassandra khác một RDBMS

Apache Cassandra dựa trên partition keys, clustering keys và replicated distributed storage. Muốn kiểm một Cassandra repository, test cần xác nhận:

- Mapping `@Table`, `@PrimaryKey`/`@PrimaryKeyColumn` đúng.
- Keyspace và table thực sự tồn tại.
- Fields được serialize thành CQL types đúng.
- Query phù hợp partition/clustering keys hoặc index đã có.
- TTL, timestamp, consistency/replication và query patterns được thiết kế đúng.
- Không dùng những giả định SQL như `JOIN`, arbitrary `ORDER BY` hoặc full table scan bằng `ALLOW FILTERING` để “sửa” lỗi query.

`@DataCassandraTest` giúp load `CassandraTemplate` và repositories nhưng **không tự tạo một Cassandra embedded H2-like engine**. Test cần Cassandra đang chạy: Testcontainers, container CI hoặc service test chuyên dụng.

### 5.2. @Table và primary key

```java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("catalog_item")
public class CassandraItem {

    @PrimaryKey
    private String id;

    private String title;

    protected CassandraItem() {}

    public CassandraItem(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
}
```

Đây là fragment thể hiện mapping Spring Data Cassandra, không phải Jakarta Persistence `@Entity`. Với composite partition/clustering key, dùng `@PrimaryKeyClass` và `@PrimaryKeyColumn` với key type/order được thiết kế rõ, không coi `@PrimaryKey String id` đủ cho mọi bảng production.

### 5.3. CassandraRepository, CassandraTemplate

`CassandraRepository<CassandraItem, String>` hỗ trợ CRUD theo primary key; `CassandraTemplate` cho phép thao tác/query CQL qua Spring abstraction. Một phép `repository.save`/`findById` kiểm được mapping và key-value read. Nhưng một test chỉ đọc theo primary key **không chứng minh** mọi `@Query`, paging hoặc consistency semantics đã đúng.

Khi cần kiểm query tùy biến, viết test riêng trên schema production-like với partition keys, clustering order và index/denormalized tables thực tế.

## 6. Project Cassandra hoàn chỉnh với Testcontainers

Đây là **project độc lập**, không ghép vào project LDAP/Couchbase ở những phần sau. Nó cần Docker/Podman environment tương thích Testcontainers, tài nguyên RAM đủ cho Cassandra và network để tải image lần đầu. Test tự tạo keyspace/table bằng CQL init script.

### 6.1. Cây file

```text
cassandra-slice-lab/
├── pom.xml
├── src/main/java/com/example/casslab/
│   ├── CassandraLabApplication.java
│   ├── CassandraItem.java
│   └── CassandraItemRepository.java
└── src/test/
    ├── resources/cassandra/schema.cql
    └── java/com/example/casslab/CassandraItemRepositoryTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>cassandra-slice-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>cassandra</artifactId>
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

Boot parent quản lý driver/Testcontainers versions. Không pin driver DataStax độc lập vào một version không khớp Spring Data Cassandra. Testcontainers cần container runtime; `@Testcontainers(disabledWithoutDocker = true)` trong ví dụ được dùng để **skip** khi không có Docker, nhưng CI phải báo skip rõ; không nhận “0 tests run” như bằng chứng tích hợp Cassandra PASS.

### 6.3. CassandraLabApplication.java

`src/main/java/com/example/casslab/CassandraLabApplication.java`:

```java
package com.example.casslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CassandraLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CassandraLabApplication.class, args);
    }
}
```

### 6.4. CassandraItem.java

`src/main/java/com/example/casslab/CassandraItem.java`:

```java
package com.example.casslab;

import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("catalog_item")
public class CassandraItem {
    @PrimaryKey
    private String id;
    private String title;

    protected CassandraItem() {
    }

    public CassandraItem(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Entity dùng id do test cung cấp; không dùng JPA `GenerationType.IDENTITY`. Cassandra không tự cấp identity value như relational auto-increment. Trên production, định nghĩa id/partition key theo access patterns.

### 6.5. CassandraItemRepository.java

`src/main/java/com/example/casslab/CassandraItemRepository.java`:

```java
package com.example.casslab;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CassandraItemRepository
        extends CassandraRepository<CassandraItem, String> {
}
```

Không cần `@Repository` trên interface để Spring Data tạo bean khi Cassandra repositories được auto-configure. Nếu repository ở ngoài package được auto scan, dùng cấu hình packages phù hợp thay vì sửa project bằng cách nạp toàn bộ application.

### 6.6. schema.cql

`src/test/resources/cassandra/schema.cql`:

```sql
CREATE KEYSPACE IF NOT EXISTS training
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS training.catalog_item (
    id text PRIMARY KEY,
    title text
);
```

CQL script tạo keyspace và table **trước** khi Spring Data chạy query. Trong container single-node, `SimpleStrategy` replication factor 1 phù hợp cho demo; không copy đó thành cấu hình production multi-datacenter.

### 6.7. CassandraItemRepositoryTest.java

`src/test/java/com/example/casslab/CassandraItemRepositoryTest.java`:

```java
package com.example.casslab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataCassandraTest(properties = {
        "spring.cassandra.keyspace-name=training",
        "spring.cassandra.local-datacenter=datacenter1"
})
@Testcontainers(disabledWithoutDocker = true)
class CassandraItemRepositoryTest {

    @Container
    @ServiceConnection
    static final CassandraContainer<?> cassandra =
            new CassandraContainer<>("cassandra:4.1")
                    .withInitScript("cassandra/schema.cql");

    @Autowired
    CassandraItemRepository repository;

    @Autowired
    CassandraTemplate template;

    @Test
    void savesAndLoadsByPartitionKey() {
        String id = "lesson-259-cassandra-1";

        try {
            repository.save(new CassandraItem(id, "Cassandra slice"));
            assertThat(repository.findById(id))
                    .isPresent()
                    .get()
                    .extracting(CassandraItem::getTitle)
                    .isEqualTo("Cassandra slice");

            assertThat(template).isNotNull();
        }
        finally {
            repository.deleteById(id);
        }
    }

    @Test
    void missingPrimaryKeyReturnsEmpty() {
        assertThat(repository.findById("missing-259-cassandra"))
                .isEmpty();
    }
}
```

**Giải thích kỹ:**
- `@DataCassandraTest` chọn đúng Cassandra slice và mapping/repository.
- `@Container` khai báo container do JUnit/Testcontainers quản lý.
- `@ServiceConnection` cung cấp `CassandraConnectionDetails` cho Spring Boot, thay vì tự hard-code port đã được Docker map.
- `CassandraContainer.withInitScript(...)` nạp CQL trong classpath trước phần test; schema có thể cần thời gian cluster khởi động.
- `spring.cassandra.keyspace-name=training` cho template/repository biết keyspace đang làm việc; container initialization tạo keyspace đó.
- `repository.save(...)` và `findById(...)` kiểm mapping entity với Cassandra thật.
- `finally` xóa row để tránh database state bám giữa methods. Cassandra không rollback tự động theo TestContext.
- Test thứ hai kiểm read miss, không mặc định dựa vào dữ liệu còn tồn tại từ test trước.

Nếu container implementation/version đã thay package trong Testcontainers 2.x, điều chỉnh import/tọa độ module theo BOM, không copy `org.testcontainers.containers.CassandraContainer` v1 vào classpath v2 mà không kiểm.

### 6.8. Chạy Cassandra lab

```bash
mvn -q clean test
mvn -q -Dtest=CassandraItemRepositoryTest test
```

Nếu Docker có sẵn và tests chạy thành công, Maven trả exit code 0. **Nếu Docker không có**, annotation có thể bỏ qua tests; xem Surefire summary (`tests` / `skipped`) trước khi kết luận. Lần đầu kéo Cassandra image và bootstrap cluster thường lâu hơn unit tests; timeout phải phản ánh startup thực tế.

Project không cố tình đưa ra stdout cố định vì Testcontainers/docker logs/driver versions khác nhau. Kết quả ở `target/surefire-reports`. Đây là tài liệu code mẫu đã được phân tích; kết quả Maven phải xác nhận trong môi trường có Docker.

## 7. Những điểm nâng cao khi kiểm Cassandra

### 7.1. Primary key và query hợp lệ

Cassandra tổ chức dữ liệu theo **partition key** và clustering columns; primary key test đọc theo id chỉ chứng minh một đường truy cập. Với method `findByStatus(...)` hoặc search theo field không phải partition/index, query có thể bị từ chối hoặc quét dữ liệu kém hiệu quả. Đừng thêm `ALLOW FILTERING` để làm test xanh nếu production sẽ không chịu tải nổi.

### 7.2. Cassandra không cần “commit” như JDBC

Một write operation trong Cassandra có consistency/durability semantics riêng và replication/acknowledgment, không có cùng mô hình một local JDBC transaction bao quanh cả test. Test `save` không bị Spring TestContext rollback mặc định.

Nếu application dùng lightweight transactions (`IF NOT EXISTS`/compare-and-set) hoặc logged batch, cần viết test riêng kiểm semantics đó trên cluster thật. Một Testcontainers node không đủ để chứng minh cross-datacenter consistency hay network partition behavior.

### 7.3. TTL/tombstones

Cassandra có `TTL` và tombstones; test cần kiểm TTL với thời gian phù hợp nếu đây là business contract. Không chọn `Thread.sleep(1000)` rồi kỳ vọng dữ liệu xóa chính xác millisecond; TTL granularity và background compaction khác nhau. Dùng TTL đủ lớn, bounded polling/clock hợp lý và xác định đó là integration test có thời gian chạy tương đối lâu.

### 7.4. Consistency level

Một single-node test không kiểm được quorum/all/write failure scenarios của cluster multi-node. Nếu mức consistency là requirement, cần cluster test/environment phù hợp. `@DataCassandraTest` chỉ quyết định Spring context, không tự tạo cluster đa nút với replication giống production.

### 7.5. Schema migrations

Schema `schema.cql` trong test phải phản ánh một phiên bản hợp đồng schema. Production Cassandra schema changes có thể cần `ALTER TABLE`, migration coordination và rollout, không do `@DataCassandraTest` tự chạy. Sử dụng tool/schema initialization nhất quán giữa test và production.

## 8. @DataCouchbaseTest — document/KV/query

### 8.1. Couchbase là JSON document store + KV + query

Couchbase lưu JSON documents theo key trong bucket/scope/collection. Spring Data Couchbase cung cấp `@Document`, `@Id`, `@Field`, `CouchbaseTemplate` và repositories.

`@DataCouchbaseTest` load Couchbase template/repository infrastructure, nhưng **không tự cung cấp Couchbase server nhúng**. Test cần container/test cluster. Có thể dùng Testcontainers `CouchbaseContainer` với `@ServiceConnection` và tạo một bucket riêng.

### 8.2. KV lookup khác N1QL query

Một test `repository.findById(id)` thường sử dụng đường **key-value lookup**, không nhất thiết cần secondary index. Nhưng derived query như `findByTitle`/`findByCategory` có thể dùng query service và yêu cầu index, scope/collection mapping, consistency chính xác. KV test PASS không chứng minh toàn bộ SQL++/N1QL queries PASS.

Couchbase có **query consistency** và index update timing: tài liệu backend có thể chưa hiện trong secondary index ngay sau KV write nếu query dùng `NOT_BOUNDED` mặc định. Nếu test gọi save rồi query ngay, cần hiểu `REQUEST_PLUS`/`AT_PLUS`/scan consistency hoặc sử dụng bounded eventually-assert khi semantics yêu cầu. Không thêm `Thread.sleep(200)` ngẫu nhiên để che race.

### 8.3. Bucket/scope/collection cần khớp

Couchbase connection properties (host/credentials) không đồng nghĩa Spring Data Couchbase đã biết bucket đúng. Trong Spring Boot 3.5, `spring.data.couchbase.bucket-name` là cấu hình thường dùng cho Spring Data Couchbase.

Nếu dùng scopes/collections không mặc định, repository/template và bucket provisioning phải dùng đúng scope/collection. Test với `_default` nhưng production ở scope khác có thể che mapping bug; thêm integration test đúng cấu trúc production khi cần.

## 9. Project Couchbase hoàn chỉnh với Testcontainers

Project này **độc lập** với Cassandra và LDAP. Nó cần Docker, Couchbase image, RAM/CPU phù hợp và thời gian startup đủ dài. Test tập trung KV mapping, không tự claim N1QL/secondary-index correctness.

### 9.1. Cây file

```text
couchbase-slice-lab/
├── pom.xml
├── src/main/java/com/example/cbslab/
│   ├── CouchbaseLabApplication.java
│   ├── CatalogDocument.java
│   └── CatalogRepository.java
└── src/test/java/com/example/cbslab/
    └── CatalogRepositoryTest.java
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>couchbase-slice-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-couchbase</artifactId>
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
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>couchbase</artifactId>
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

### 9.3. CouchbaseLabApplication.java

`src/main/java/com/example/cbslab/CouchbaseLabApplication.java`:

```java
package com.example.cbslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CouchbaseLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CouchbaseLabApplication.class, args);
    }
}
```

### 9.4. CatalogDocument.java

`src/main/java/com/example/cbslab/CatalogDocument.java`:

```java
package com.example.cbslab;

import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class CatalogDocument {

    @Id
    private String id;

    @Field
    private String title;

    protected CatalogDocument() {
    }

    public CatalogDocument(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

`@Id` của Couchbase/Spring Data là `org.springframework.data.annotation.Id`; không phải `jakarta.persistence.Id`. `@Field` của Spring Data Couchbase mô tả persisted field. Đừng sử dụng JPA `@Entity`/`@Table` để tạo Couchbase document mapping.

### 9.5. CatalogRepository.java

`src/main/java/com/example/cbslab/CatalogRepository.java`:

```java
package com.example.cbslab;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CatalogRepository
        extends CouchbaseRepository<CatalogDocument, String> {
}
```

Test đọc theo ID; Couchbase không cần secondary index để KV get. Nếu mở rộng `findByTitle`, phải bảo đảm query service/index có mặt và xét index consistency; đừng suy từ test này rằng derived query chắc chắn hoạt động.

### 9.6. CatalogRepositoryTest.java

`src/test/java/com/example/cbslab/CatalogRepositoryTest.java`:

```java
package com.example.cbslab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@DataCouchbaseTest(properties = {
        "spring.data.couchbase.bucket-name=lesson_bucket",
        "spring.couchbase.env.timeouts.connect=2m",
        "spring.couchbase.env.timeouts.key-value=1m"
})
@Testcontainers(disabledWithoutDocker = true)
class CatalogRepositoryTest {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
            new CouchbaseContainer(
                    DockerImageName.parse("couchbase/server:7.6.2"))
                    .withEnabledServices(
                            CouchbaseService.KV,
                            CouchbaseService.INDEX,
                            CouchbaseService.QUERY)
                    .withBucket(new BucketDefinition("lesson_bucket"));

    @Autowired
    CatalogRepository repository;

    @Autowired
    CouchbaseTemplate template;

    @Test
    void storesAndFetchesDocumentById() {
        String id = "lesson-259-couchbase-1";
        try {
            repository.save(new CatalogDocument(id, "Couchbase slice"));

            assertThat(repository.findById(id))
                    .isPresent()
                    .get()
                    .extracting(CatalogDocument::getTitle)
                    .isEqualTo("Couchbase slice");

            assertThat(template.getBucketName())
                    .isEqualTo("lesson_bucket");
        }
        finally {
            repository.deleteById(id);
        }
    }

    @Test
    void missingDocumentIsAbsent() {
        assertThat(repository.findById("missing-259-couchbase"))
                .isEmpty();
    }
}
```

**Giải thích:**
- `@DataCouchbaseTest` cấu hình template/repositories, không controller/service toàn app.
- `CouchbaseContainer` provision Couchbase test server và bucket `lesson_bucket`.
- `@ServiceConnection` đưa connection details vào Spring Boot; bucket name vẫn phải khớp property `spring.data.couchbase.bucket-name`.
- `withEnabledServices` khai báo KV, index, query services phù hợp test. Các Testcontainers 2.x packages có thể khác version này.
- `findById` là đường KV, tránh nhu cầu tạo index/đợi index cập nhật ở demo đầu tiên.
- `finally` xóa đúng document ID; NoSQL test slice không tự rollback.
- Nếu test query secondary index, thêm index provisioning cùng assertions tương ứng.

**Lưu ý vận hành:** Couchbase container nặng hơn nhiều so với embedded LDAP. Với môi trường CI tải yếu hoặc image không sẵn, hãy cấu hình tài nguyên và timeout hợp lý thay vì biến timeout/chạy test thành một phép thử may rủi.

### 9.7. Chạy Couchbase lab

```bash
mvn -q clean test
mvn -q -Dtest=CatalogRepositoryTest test
```

Chỉ kết luận integration PASS khi Surefire ghi nhận tests **đã chạy**, không phải skipped vì thiếu Docker. `@ServiceConnection` giúp truyền connection details nhưng không tạo sẵn bucket/scope tùy ý ngoài những gì container setup cung cấp. Xem `target/surefire-reports` để kiểm kết quả.

## 10. Mở rộng Couchbase testing đúng ranh giới

### 10.1. Derived query và index

Một method:

```java
List<CatalogDocument> findByTitle(String title);
```

được khai báo trong `CatalogRepository` có thể khiến Spring Data thực hiện query service. Để test:
- Đảm bảo bucket/scope/collection/index phù hợp.
- Tạo index trước test hoặc dùng container provision schema.
- Biết consistency behavior sau KV write.
- Kiểm mapping đúng property name và field annotation.
- Dọn dữ liệu theo key/collection, không xóa cả bucket đang được test khác dùng.

Method trên là **mẫu mở rộng**, không có trong runnable `CatalogRepository.java` ở mục 9; muốn chạy phải thêm vào interface và tạo index.

### 10.2. Query consistency khác KV consistency

Nếu save xong, `findById` đọc thấy document nhưng `findByTitle` chưa thấy, có thể query index chưa được cập nhật. Không mặc định mapping sai. Với query consistency được yêu cầu, cấu hình scan consistency ở đúng API/template/query options, hoặc dùng bounded await/retry chỉ dành cho eventual consistency contract; tránh sleep vô hạn.

### 10.3. CAS và concurrent modifications

Couchbase cung cấp CAS (compare-and-swap) và các kiểu optimistic concurrency. Nếu business cần ngăn lost updates, test riêng CAS/version mapping trên container thật. `@DataCouchbaseTest` không tự giả lập race hoặc đảm bảo atomicity của nhiều documents.

### 10.4. Durability và cross-node guarantees

Một Couchbase container đơn thường phù hợp mapping/KV integration nhưng không chứng minh quorum durability/replica failover của cluster production. Tùy rủi ro, cần environment nhiều nodes và test được kiểm soát. Không kết luận một test `save` thành công nghĩa là tất cả durability policies production đúng.

### 10.5. Bucket, scope, collection trong multi-tenant apps

Nếu production tách tenant theo collection/bucket, test trong `_default` có thể không phát hiện lỗi routing. Dùng data container provision giống cấu trúc thực, kiểm repository mapping và security isolation. Không hard-code credentials của production vào `application-test.properties`.

## 11. @DataLdapTest — embedded LDAP và DN

### 11.1. LDAP không phải bảng SQL hoặc JSON document store

LDAP lưu directory entries được xác định bằng **Distinguished Name (DN)**, ví dụ:

```text
uid=alice,ou=people,dc=example,dc=org
```

Entry có attributes và object classes:

```ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
```

- `uid=alice` là một Relative Distinguished Name (RDN).
- `ou=people` là organizational unit chứa entry.
- `dc=example,dc=org` là base DN.
- `cn` là common name; `sn` là surname.
- `objectClass` quyết định thuộc tính bắt buộc và hợp lệ theo LDAP schema.

LDAP filter `(uid=alice)` **không phải SQL WHERE**. Các ký tự `*`, `(`, `)`, `\` và NUL có escaping rules riêng; không nối chuỗi filter với input từ người dùng một cách thô.

### 11.2. Boot 3.5 hỗ trợ LDAP nhúng khi có UnboundID

`@DataLdapTest` tự cấu hình `LdapTemplate`/LDAP repositories và **in-memory embedded LDAP nếu thư viện phù hợp và properties được cung cấp**.

Cần:
- `spring-boot-starter-data-ldap`.
- `com.unboundid:unboundid-ldapsdk` trong test classpath.
- `spring.ldap.embedded.base-dn=dc=example,dc=org`.
- LDIF fixture chứa base/organizational unit/entries nếu muốn dữ liệu sẵn.
- Có thể đặt `spring.ldap.base=dc=example,dc=org` để template thao tác bằng DN tương đối.

Một embedded LDAP thường chạy trên random local port. **Không cần** trỏ `spring.ldap.urls` về LDAP công ty trong slice test này. Nếu cố tình dùng server ngoài, exclude embedded auto-configuration và cấp URL/bind credentials của sandbox test (không production).

## 12. Project LDAP hoàn chỉnh, không cần Docker

Project LDAP dưới đây có fixtures LDIF và ba test: lookup/search entry cố định, kiểm missing entry, thêm và xóa entry với cleanup. Đây là bài lab nhẹ nhất trong ba ví dụ.

### 12.1. Cây thư mục

```text
ldap-slice-lab/
├── pom.xml
├── src/main/java/com/example/ldaplab/
│   └── LdapLabApplication.java
└── src/test/
    ├── resources/ldap-test.ldif
    └── java/com/example/ldaplab/LdapDirectoryTest.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>ldap-slice-lab</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>com.unboundid</groupId>
      <artifactId>unboundid-ldapsdk</artifactId>
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

Không có Spring Security starter. `@DataLdapTest` kiểm LDAP data access, **không tự kiểm** authentication manager/role mapping/security filter chain của ứng dụng. Với Spring Security LDAP, tạo test riêng ở ranh giới security.

### 12.3. LdapLabApplication.java

`src/main/java/com/example/ldaplab/LdapLabApplication.java`:

```java
package com.example.ldaplab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LdapLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LdapLabApplication.class, args);
    }
}
```

### 12.4. ldap-test.ldif

`src/test/resources/ldap-test.ldif`:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
```

Không chứa password hoặc tài khoản nhân viên thật; dữ liệu là fixture. Đặt đúng newline và một dòng trống giữa các entries. LDIF có các quy tắc encode non-ASCII/continuation lines; fixture dùng ASCII đơn giản để tránh phụ thuộc encoding. Nếu thêm tên tiếng Việt, dùng UTF-8 LDIF hợp lệ.

### 12.5. LdapDirectoryTest.java

`src/test/java/com/example/ldaplab/LdapDirectoryTest.java`:

```java
package com.example.ldaplab;

import java.util.List;
import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.assertj.core.api.Assertions.assertThat;

@DataLdapTest(properties = {
        "spring.ldap.base=dc=example,dc=org",
        "spring.ldap.embedded.base-dn=dc=example,dc=org",
        "spring.ldap.embedded.ldif=classpath:ldap-test.ldif"
})
class LdapDirectoryTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void findsSeededDirectoryEntry() {
        List<String> names = ldapTemplate.search(
                "ou=people",
                "(uid=alice)",
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString());

        assertThat(names).containsExactly("Alice Nguyen");
    }

    @Test
    void unknownUidReturnsEmptySearch() {
        List<String> names = ldapTemplate.search(
                "ou=people",
                "(uid=not-present)",
                (AttributesMapper<String>) attrs ->
                        attrs.get("cn").get().toString());

        assertThat(names).isEmpty();
    }

    @Test
    void createsAndDeletesOnlyItsOwnEntry() {
        Name dn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "bob")
                .build();

        DirContextAdapter entry = new DirContextAdapter(dn);
        entry.setAttributeValues("objectClass", new String[] {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        });
        entry.setAttributeValue("uid", "bob");
        entry.setAttributeValue("cn", "Bob Tran");
        entry.setAttributeValue("sn", "Tran");

        boolean bound = false;
        try {
            ldapTemplate.bind(entry);
            bound = true;

            String commonName = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs ->
                            attrs.get("cn").get().toString());

            assertThat(commonName).isEqualTo("Bob Tran");
        }
        finally {
            if (bound) {
                ldapTemplate.unbind(dn);
            }
        }
    }
}
```

**Giải thích chi tiết:**
- `@DataLdapTest` dựng LDAP slice, template và embedded UnboundID nếu điều kiện phù hợp.
- `spring.ldap.base` khiến template dùng relative DN: `ou=people`, `uid=bob,ou=people`. LDAP server vẫn lưu full DN dưới `dc=example,dc=org`.
- `LdapTemplate.search` dùng LDAP filter `(uid=alice)` trên organizational unit; mapper đọc attribute `cn`.
- Test unknown user chứng minh search trả list rỗng, không giả định repository có user mặc định nào khác.
- `DirContextAdapter` xây LDAP entry với object classes/attributes hợp lệ.
- `LdapTemplate.bind` thêm entry; `lookup` đọc lại DN và attribute.
- `finally` unbind đúng DN; LDAP slice không tự rollback record thêm vào.
- Tất cả dữ liệu cố định có thể tái chạy nếu cleanup hoàn tất và context/fixture không bị test khác sửa song song.

**Lưu ý về mapping repository:** Lab dùng `LdapTemplate` để giữ example ngắn và rõ DN. Spring Data LDAP còn cung cấp `@Entry`, `@DnAttribute`, `@Attribute` và `LdapRepository`; chúng hữu ích khi ứng dụng có model repository thật. `@DataLdapTest` hỗ trợ cả hai. Đừng tự suy rằng LDAP entry ánh xạ giống một JPA entity.

### 12.6. Chạy LDAP lab

```bash
mvn -q clean test
mvn -q -Dtest=LdapDirectoryTest test
```

Lab này không cần Docker hoặc LDAP thật. Nếu Maven/test PASS, exit code 0; nếu context fail vì LDIF/schema/base DN, xem `target/surefire-reports` và Spring Boot startup logs. Không dùng `spring.ldap.urls=ldap://ldap.company...` trong lab này.

### 12.7. Nếu cần server LDAP thật

Spring Boot reference hỗ trợ loại embedded LDAP khỏi slice:

```java
import org.springframework.boot.autoconfigure.ldap.embedded.EmbeddedLdapAutoConfiguration;
import org.springframework.boot.test.autoconfigure.data.ldap.DataLdapTest;

@DataLdapTest(
    excludeAutoConfiguration = EmbeddedLdapAutoConfiguration.class,
    properties = {
        "spring.ldap.urls=ldap://127.0.0.1:1389",
        "spring.ldap.base=dc=example,dc=org"
    })
class ExternalDirectoryTest {
    // Cần test-only LDAP server thật tại URI đó.
}
```

Đây là **mẫu minh họa**, không thuộc runnable lab; `127.0.0.1:1389` chỉ là địa chỉ của LDAP test server nếu bạn đã dựng riêng. Với LDAP thật, có thể cần bind principal/password, StartTLS/LDAPS, truststore, network access và permission. Không kết nối Directory production từ unit test.

## 13. LdapRepository/@Entry: lựa chọn khác LdapTemplate

### 13.1. Entity LDAP sử dụng @Entry

Ví dụ mô tả một LDAP directory object (đoạn code nâng cao, không thuộc lab đã tạo):

```java
@Entry(base = "ou=people",
       objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"})
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    // No-arg constructor, getters/setters
}
```

Các imports tương ứng là Spring Data LDAP annotations `org.springframework.ldap.odm.annotations.Entry`, `Id`, `Attribute`. Đoạn này **không phải file biên dịch độc lập** vì bỏ phần constructor/accessors; khi dùng trong project thực, cần mapping class hoàn chỉnh và DN generation/update strategy.

Một repository:

```java
public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
```

cần đúng `org.springframework.data.ldap.repository.LdapRepository` và entity được scan. Khi ID là DN đầy đủ/relative và base DN đã cấu hình, mapping cần nhất quán; đừng dùng một UID string như SQL primary key nếu repository đòi `Name`/DN.

### 13.2. Filter injection

Một filter từ input:

```java
String filter = "(uid=" + externalUserInput + ")";
```

có thể bị chèn `*`, `)`, `(` hoặc escape sequences. Đây là **anti-pattern**. Dùng APIs của Spring LDAP dựng filter hoặc escape value đúng chuẩn RFC 4515 (ví dụ `EqualsFilter`), rồi assert rằng input chứa ký tự đặc biệt không biến thành một điều kiện rộng hơn.

### 13.3. Embedded LDAP không mô phỏng mọi enterprise schema

UnboundID tốt cho DN/search/mapping cơ bản. Nhưng Active Directory/OpenLDAP và dịch vụ Directory khác có thể có:
- Schema extensions/custom attributes.
- Group membership/memberOf semantics.
- ACL và bind rules.
- Password policy, lockout, password hashing.
- StartTLS/LDAPS, certificate/truststore.
- Referral chasing, paging/sorting controls.
- Case/normalization behavior khác nhau.

Với requirement đặc thù, thêm sandbox integration tests trên directory engine thực, không coi embedded LDAP PASS là chứng cứ cho mọi security/policy behavior.

## 14. @ServiceConnection và @DynamicPropertySource

### 14.1. Service connection hoạt động như thế nào?

Với Boot 3.5 và `spring-boot-testcontainers`, `@ServiceConnection` trên container typed cho phép Boot cung cấp connection details tự động. Boot có built-in factories cho `CassandraConnectionDetails` từ `CassandraContainer` và `CouchbaseConnectionDetails` từ `CouchbaseContainer`. Những details này có thể có ưu tiên so với properties kết nối thông thường.

```java
@Testcontainers
@DataCassandraTest(properties = "spring.cassandra.keyspace-name=training")
class ContainerSliceTest {
    @Container
    @ServiceConnection
    static CassandraContainer<?> cassandra =
            new CassandraContainer<>("cassandra:4.1");
}
```

Snippet này **không chạy độc lập** nếu chưa có schema/keyspace như mục 6, và có thể còn thiếu import. Nó minh họa cách connection details được đăng ký, không phải cách tự động tạo keyspace.

### 14.2. Đừng coi @ServiceConnection tạo cả schema/bucket

- Cassandra: `@ServiceConnection` cung cấp endpoint/datacenter/credentials theo container factory; **không thay thế `CREATE KEYSPACE`/`CREATE TABLE`**.
- Couchbase: connection details cung cấp cluster endpoint/credentials; **bucket và scope/collection** vẫn phải được container provision/config đúng.
- LDAP: embedded auto-configuration có cơ chế riêng; không cần `@ServiceConnection` cho lab UnboundID trong mục 12.

Đây là một trong những nguyên nhân phổ biến của lỗi context startup: kết nối được server nhưng keyspace/bucket chưa tồn tại.

### 14.3. @DynamicPropertySource khi cần custom connection

Nếu không dùng được service connection typed, có thể đăng ký properties động:

```java
@DynamicPropertySource
static void cassandraProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cassandra.contact-points",
            () -> cassandra.getHost() + ":" + cassandra.getMappedPort(9042));
    registry.add("spring.cassandra.local-datacenter",
            cassandra::getLocalDatacenter);
    registry.add("spring.cassandra.keyspace-name", () -> "training");
}
```

Đây là snippet cho một class đã có `static CassandraContainer<?> cassandra`. Nó cần imports `DynamicPropertySource`/`DynamicPropertyRegistry` và schema trước startup. Nếu Boot 3.5 config property muốn danh sách contact points/port theo mẫu riêng, dùng cách Boot reference/Javadoc tương ứng; `@ServiceConnection` thường ít sai hơn.

Đừng thêm cả `@ServiceConnection` và manual contact-points overrides rồi giả định properties thủ công thắng: connection details có thể có ưu tiên hơn properties.

### 14.4. Container lifecycle trong Spring TestContext

Static `@Container` dưới JUnit Testcontainers extension thường khởi động/dừng theo class lifecycle. Spring TestContext **cache application context** qua nhiều test classes có config giống nhau; vì vậy có thể xảy ra rủi ro cached context giữ connection đến container đã dừng. Với suite lớn, cân nhắc container khai báo như Spring bean trong `@TestConfiguration` cùng `@ServiceConnection`, hoặc context isolation/caching strategy được Spring Boot 3.5 documentation khuyến nghị.

Dùng Docker image digest/tag cố định có chủ đích để CI có kết quả lặp lại; không sử dụng `latest` cho Cassandra/Couchbase mà không kiểm migration compatibility.

## 15. Test data isolation và cleanup

### 15.1. Vì sao không tự rollback?

Một phép `save` Cassandra hoặc Couchbase và `ldapTemplate.bind` đã thay đổi backend bên ngoài test method. Các `@Data...Test` này không mặc định mở JDBC/JPA transaction rồi rollback. Vì vậy:

- Test phải tạo **ID/DN riêng**.
- Delete/cleanup trong `finally`/`@AfterEach`.
- Sử dụng container/bucket/keyspace/base DN chuyên biệt cho test.
- Chấp nhận cleanup có thể không chạy nếu JVM bị kill; **ephemeral infrastructure** là safety net.
- Không trỏ tới production, kể cả “chỉ chạy một integration test”.
- Tránh chạy parallel tests cùng key/entry nếu chưa có namespace/cách ly.

### 15.2. Cassandra cleanup

Thường xóa row bằng primary key:

```java
try {
    repository.save(new CassandraItem("test-id", "data"));
    // assertions
}
finally {
    repository.deleteById("test-id");
}
```

Nếu test thực hiện nhiều writes/partitions, cần cleanup tất cả. Cassandra deletes tạo tombstones; với dataset lớn, đừng tạo hàng triệu tombstones chỉ để test. Ephemeral keyspace/container phù hợp hơn cho test workload nặng.

### 15.3. Couchbase cleanup

```java
try {
    repository.save(new CatalogDocument("test-id", "data"));
    // assertions
}
finally {
    repository.deleteById("test-id");
}
```

Nếu test query dựa vào secondary index, cleanup có thể chưa phản ánh tức thì trong query result do index consistency; test không nên assert zero counts ngay mà không hiểu semantics. Với các suites song song, dùng test ID prefix hoặc bucket/collection isolation.

### 15.4. LDAP cleanup

```java
Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "temporary")
        .build();

try {
    ldapTemplate.bind(context);
    // assertions
}
finally {
    ldapTemplate.unbind(dn);
}
```

Snippet cần `context` đã được tạo đúng DN/schema, và chỉ nên unbind nếu bind thành công; runnable lab sử dụng cờ `bound` để tránh masking original exception. Không unbind cả organizational unit hoặc base DN vì có thể làm mất fixture/test data dùng chung.

### 15.5. @DirtiesContext không xóa data store

`@DirtiesContext` chỉ thay đổi vòng đời cached Spring context, không bảo đảm xóa rows/documents/entries từ Cassandra/Couchbase/LDAP. Nó cũng có thể làm test chậm vì phải khởi động context mới. Cleanup cần diễn ra trên data store thực hoặc dựa vào sự huỷ ephemeral container khi suite kết thúc.

## 16. Mapping và query correctness: kiểm theo hợp đồng

### 16.1. Field types khác nhau giữa các backend

| Concept | Cassandra | Couchbase | LDAP |
| --- | --- | --- | --- |
| Identity | Partition/clustering primary key | Document key/ID | Distinguished Name (DN) |
| Schema | CQL schema/keyspace/table | JSON document schema linh hoạt, indexes | LDAP object classes/attribute schema |
| Query | CQL với key/index rules | KV + SQL++/N1QL | LDAP filter/search scope |
| Ordering | Clustering order theo partition | Chỉ theo ORDER BY nếu query cam kết | LDAP search không tự bảo đảm sort |
| Missing value | CQL null/unset semantics | JSON null/missing semantics | Attribute absent vs empty string |
| Consistency | Tunable consistency + replication | KV durability/query scan consistency | Server/replica/referral/replication theo directory |
| TTL | Native TTL | Expiry (document) | Không là thuộc tính chung của mọi LDAP |
| Transactions | Batches/LWT, không như JPA rollback test | Couchbase transactional APIs riêng nếu dùng | LDAP ops không JDBC test rollback |

Đừng viết một helper test áp cùng giả định “save rồi query count, rollback sau test” lên ba backend.

### 16.2. Kiểm dữ liệu quan trọng

Khi domain phụ thuộc vào mapping:
- Cassandra: ID, column names/CQL types, partition key, custom converters, TTL/consistency.
- Couchbase: document ID, field names, JSON type, `@Version`/CAS, expiry, scope/collection, query index.
- LDAP: DN/base, RDN, objectClass, attributes, group membership/filter and escape.

Nên có test negative: missing key/unknown DN, invalid schema/type, query không khớp, access denied, expired document hoặc invalid credentials khi requirement yêu cầu. Nhưng đừng kéo các case có security/TLS vào embedded-only test rồi kết luận production secure.

## 17. Những lỗi phổ biến và cách xử lý

### 17.1. No qualifying bean for repository/template

**Nguyên nhân:** module starter thiếu, repository không ở auto-scan package, mapping annotation sai backend, hoặc slice filter không include bean. Kiểm `mvn dependency:tree`, packages và imports. Không sửa bằng `@SpringBootTest` vô điều kiện.

### 17.2. Không có @Service hoặc @ConfigurationProperties trong slice

**Nguyên nhân:** slice loại regular components. **Sửa:** chỉ `@Import(MyService.class)` hoặc `@EnableConfigurationProperties(MyProperties.class)` khi nó thực sự thuộc ranh giới test. Nếu test cần cả workflow và nhiều adapters, dùng full integration test.

### 17.3. Cassandra connection refused / no host available

**Nguyên nhân:** không có Cassandra server, Docker chưa chạy, startup chưa hoàn tất, sai host/port/datacenter. **Sửa:** kiểm Testcontainers runtime, `@ServiceConnection`, logs Cassandra, keyspace và local datacenter. Không trỏ vào Cassandra production để tiện debug.

### 17.4. Cassandra InvalidQueryException: unconfigured table

**Nguyên nhân:** `schema.cql` không chạy, test keyspace sai hoặc table name không trùng `@Table`. **Sửa:** kiểm resource path, CQL init script, keyspace `training` và table `catalog_item`. Không dựa vào JPA `ddl-auto=create-drop`; property đó không có nghĩa với Cassandra.

### 17.5. Cassandra query rejected vì thiếu key/index

**Nguyên nhân:** query không phù hợp primary key. **Sửa:** thiết kế access pattern, bảng/materialized view/index thích hợp; nếu dùng `ALLOW FILTERING` phải đánh giá hiệu năng và có justification, không dùng làm bản vá vội.

### 17.6. Couchbase authentication hoặc bucket not found

**Nguyên nhân:** connection details có nhưng `spring.data.couchbase.bucket-name` sai, bucket không provision, credential hoặc network sai. **Sửa:** bảo đảm bucket name trong `BucketDefinition` và Boot property khớp, xem container logs.

### 17.7. Couchbase findById PASS nhưng derived query FAIL

**Nguyên nhân:** KV get không cần index, nhưng query cần query service/index/scope hoặc consistency. **Sửa:** tạo index/schema phù hợp; test consistency theo contract, không thêm sleep để may rủi thấy data.

### 17.8. Couchbase timeout trên CI

**Nguyên nhân:** Couchbase container khởi động chậm/ít RAM, bucket warm-up, Query service không sẵn. **Sửa:** cấp tài nguyên/timeout hợp lý, pin image và theo dõi startup readiness; đừng làm test skip im lặng mà báo đã PASS.

### 17.9. LDAP NoSuchObjectException

**Nguyên nhân:** sai base DN, `ou=people` chưa có trong LDIF, relative/full DN trộn lẫn hoặc object hierarchy sai. **Sửa:** kiểm `spring.ldap.base`, `spring.ldap.embedded.base-dn` và LDIF tree; search với relative DN đúng.

### 17.10. LDAP invalid attribute/objectClass

**Nguyên nhân:** entry thiếu `cn`/`sn`, objectClass không hỗ trợ attribute hoặc LDIF sai schema. **Sửa:** thêm đúng object classes/required attributes; đừng tắt `spring.ldap.embedded.validation.enabled` chỉ để test xanh nếu schema validation là rủi ro chính.

### 17.11. LDAP filter injection

**Nguyên nhân:** nối chuỗi filter với dữ liệu người dùng chưa escape. **Sửa:** dùng Spring LDAP filter builders/escaping, kiểm malicious input và giới hạn search scope. Không lấy kết quả search rộng rồi coi là “user đã được xác thực”.

### 17.12. Embedded LDAP PASS nhưng LDAP enterprise FAIL

**Nguyên nhân:** khác schema, ACL, bind, groups, TLS/LDAPS/StartTLS, pagination hoặc referral. **Sửa:** thêm integration test với test directory engine thích hợp, fake users/groups, TLS certificate test và permissions đúng.

### 17.13. Test pass ở local nhưng fail khi chạy song song

**Nguyên nhân:** dùng cùng Cassandra key, Couchbase document ID hoặc LDAP DN; cùng container/bucket/context mutable state. **Sửa:** unique IDs, test namespace, cleanup, cô lập backend; không phụ thuộc thứ tự JUnit.

### 17.14. @DirtiesContext dùng để xóa NoSQL test data

**Sai:** chỉ thay Spring context cache. **Sửa:** delete/flush collection, ephemeral container hoặc teardown data store có chủ đích.

### 17.15. @Transactional không làm NoSQL tests tự rollback

**Nguyên nhân:** các repository operations của NoSQL/LDAP không mặc định nằm trong JDBC/JPA test transaction. **Sửa:** hiểu native transaction support, test đúng boundary và cleanup. Đừng dùng `TestTransaction` của JPA để suy luận rollback Cassandra/Couchbase/LDAP.

### 17.16. Testcontainers bị skip do Docker không có

**Nguyên nhân:** `@Testcontainers(disabledWithoutDocker = true)` được dùng để skip integration tests. **Sửa:** CI integration job phải có runtime hỗ trợ Docker và yêu cầu tests thực sự executed (skipped=0) trước khi coi build đủ điều kiện; unit/LDAP tests có thể chạy trong job khác không có Docker.

### 17.17. Trộn Spring Boot 3.5 với Boot 4 import

**Nguyên nhân:** Boot 4 chuyển các data slice annotations sang module riêng, có package khác. **Sửa:** dùng BOM và docs theo major; kiểm compiler actual errors, không pin spring-boot-test-autoconfigure 3.x vào Boot 4.

### 17.18. Test dùng production credentials

**Nguyên nhân:** test profile đọc app secrets hoặc env variables trùng production. **Sửa:** test containers, embedded LDAP, fake users, isolated credentials. CI không nên log tokens/passwords hay LDAP user data thật.

## 18. Kiến trúc test nhiều tầng

| Mục tiêu | Kiểu test | Công nghệ |
| --- | --- | --- |
| Domain validations hoặc tính toán không liên quan data store | JUnit/Mockito | Không Spring context |
| Mapping Cassandra @Table/primary key/repository CRUD | `@DataCassandraTest` | Cassandra container |
| Mapping Couchbase @Document/KV repository | `@DataCouchbaseTest` | Couchbase container |
| LDAP DN/search/attributes | `@DataLdapTest` | Embedded UnboundID |
| Cassandra CQL, TTL, LWT, multi-node consistency | Slice + integration environment thích hợp | Cassandra cluster/version phù hợp |
| Couchbase SQL++/index/consistency/CAS | Slice + provisioned indexes/cluster | Couchbase test server |
| LDAP auth/group/schema/ACL/TLS | Slice hoặc full-context integration | LDAP sandbox engine thật |
| Service phối hợp Cassandra + Couchbase + LDAP | `@SpringBootTest` | Test stores + fake external boundaries |
| REST controller trả JSON dựa trên store | `@WebMvcTest` hoặc `@SpringBootTest` | Mock service hay real storage theo mục tiêu |
| Observability/retry/circuit breaker integration | Full-context/integration | Có instrumentation, controlled failure |

Không cần test end-to-end cho mọi field: giữ nhiều **fast unit tests**, vài **data slice tests** đúng công nghệ và một số **cross-component integration tests** cho rủi ro liên kết.

### 18.1. Chi phí và tốc độ

- LDAP embedded thường khởi động nhanh và không cần Docker.
- Cassandra container cần chuẩn bị cluster, thường tốn thời gian/tài nguyên.
- Couchbase container nặng, có nhiều service và bucket initialization.
- Full application context có thể tốn hơn slice nếu kéo hạ tầng unrelated.

Có thể phân luồng Maven test targets/unit tests và integration tests, nhưng đừng đánh đồng tests đã skipped với tests PASS. Với một CI pipeline thực tế, nhóm có thể yêu cầu chỉ chạy Cassandra/Couchbase integration job khi có Docker runtime và đủ RAM; luôn công bố rõ coverage.

## 19. Checklist bảo mật và tính ổn định

### 19.1. Secrets và dữ liệu cá nhân

- Không dùng credentials Cassandra/Couchbase/LDAP production trong test.
- Không lưu thật password, email/employee IDs, access tokens trong LDIF fixtures.
- Dùng test-only service accounts với ít quyền nhất.
- Không ghi plain-text LDAP bind credentials hoặc Couchbase admin password ra CI logs.
- Khi test TLS, sử dụng self-signed/test certificates được quản lý đúng cách, không disable certificate verification trong production config.

### 19.2. Resource isolation

- Mỗi test dùng key/ID/DN khác nhau; tránh collision.
- Cleanup trong `finally`/test teardown và ephemeral infrastructure.
- Không dựa vào `@DirtiesContext` hoặc implicit rollback để xóa NoSQL rows.
- Với cache Spring TestContext và static containers, kiểm container lifecycle.
- Có memory/CPU/readiness timeout hợp lý cho Cassandra/Couchbase.
- Thống nhất version backend/test image với production compatibility goals.

### 19.3. Business assertions có ý nghĩa

Một test `repository.count() > 0` rất yếu nếu fixture đã seed data hoặc các tests dùng chung store. Nên assert đúng identity, fields, query result và negative path. Với LDAP DN, kiểm đường dẫn/base và attributes; với Cassandra/Couchbase, kiểm mapping/query theo access patterns.

## 20. Bài tập thực hành

1. Tạo một project chỉ có Spring Data Cassandra và `@DataCassandraTest`; giải thích vì sao test không tự có embedded Cassandra.
2. Dùng `CassandraContainer` và `@ServiceConnection`; cố ý bỏ `schema.cql` để quan sát lỗi keyspace/table. Sau đó khôi phục schema.
3. Với Cassandra composite key, bổ sung `@PrimaryKeyColumn` cho partition và clustering; kiểm query đúng partition key.
4. Thêm TTL vào Cassandra write, thiết kế test có polling bounded thay vì sleep tùy tiện.
5. Tạo Couchbase `@Document`, repository `findById` và kiểm round trip trên bucket test.
6. Thêm derived query `findByTitle` cho Couchbase; provision index và so sánh KV lookup với query consistency.
7. Thử đổi `spring.data.couchbase.bucket-name` sai và giải thích lỗi.
8. Tạo một LDIF entry có `uid=alice` và `@DataLdapTest`; search theo OU và attribute.
9. Thêm một LDAP entry tạm bằng `DirContextAdapter`, lookup và unbind trong `finally`.
10. Tạo một filter dùng external input chứa `*`/`)`; chứng minh filter builder escape input không làm search rộng bất ngờ.
11. Dùng `@EnableConfigurationProperties` đưa một custom properties bean vào một slice; phân biệt với quét toàn `@Component`.
12. Vì sao `@Transactional` và `@DirtiesContext` không tự cleanup các NoSQL writes? Đề xuất giải pháp.
13. Chạy ba labs riêng, ghi rõ lab nào không cần Docker, lab nào cần Docker; phân biệt PASS và SKIPPED.
14. Nêu cách bổ sung full integration test cho service đồng thời dùng Cassandra và LDAP.
15. Nếu Boot nâng từ 3.5 lên 4.x, bạn sẽ kiểm package annotation, Maven starter names, Testcontainers versions và service connection changes ở đâu?

Tiêu chí đạt: người học xác định **đúng backend**, **đúng slice**, **đúng test infrastructure**, **đúng schema/identity/index**, **đúng phạm vi được kiểm** và **đúng cleanup**.

## 21. Checklist trước khi merge

- [ ] Ứng dụng thật sự dùng Cassandra/Couchbase/LDAP; không thêm starter không cần?
- [ ] Spring Boot/Java versions và import annotation đúng major 3.5?
- [ ] Đã chọn đúng một test slice cho một class, không stack nhiều slices?
- [ ] Các `@Component`/`@ConfigurationProperties` không cần thiết bị loại khỏi context?
- [ ] Nếu cần properties custom, dùng `@EnableConfigurationProperties` có chọn lọc?
- [ ] Cassandra test có engine, keyspace, table schema và local datacenter đúng?
- [ ] Cassandra mapping `@Table`/primary key và CQL access pattern được kiểm?
- [ ] Cassandra cleanup theo primary key/ephemeral keyspace, không dựa rollback?
- [ ] Couchbase test có container, bucket, credentials và services cần thiết?
- [ ] Couchbase `@Document`/`@Id`/`@Field` đúng và repository mapping được assert?
- [ ] Test KV và query/index/consistency của Couchbase được phân biệt?
- [ ] LDAP test có UnboundID và base DN/LDIF đúng?
- [ ] LDAP filter escaping, DN, objectClass/attribute schema được kiểm?
- [ ] LDAP bind/unbind không đụng tới người dùng/directory thật?
- [ ] `@ServiceConnection`/`spring-boot-testcontainers`/Testcontainers module đúng version?
- [ ] Nếu Docker thiếu, CI không coi tests skipped là integration PASS?
- [ ] Mọi dữ liệu tạo ra đều có cleanup hoặc ephemeral service lifecycle?
- [ ] Parallel tests có unique IDs/DNs và isolation?
- [ ] Backend images/schema/test setup tương thích production critical behaviors?
- [ ] Security/TLS/ACL không bị suy diễn từ test mapping đơn giản?
- [ ] Có test negative paths, không chỉ happy path?
- [ ] Maven tests được thực thi trong CI phù hợp và Surefire report được review?

**Kết luận:** `@DataCassandraTest`, `@DataCouchbaseTest` và `@DataLdapTest` là những công cụ cô lập **tầng truy cập dữ liệu ngoài SQL**, không phải database giả tự tạo. Cassandra/Couchbase thường cần Testcontainers hoặc test cluster thật, trong khi LDAP có thể dùng embedded UnboundID. Mỗi slice giữ mapping/repository/template thật nhưng loại phần lớn application components không liên quan. Vì không có rollback mặc định kiểu JPA, cần thiết kế fixtures, identities, cleanup và infrastructure isolation. Khi test cần query semantics, authentication hoặc multi-store workflow, mở rộng boundary bằng integration test phù hợp thay vì yêu cầu slice chứng minh điều nó không bao phủ.

## 22. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Test Slices auto-configuration appendix: https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- Spring Boot 3.5 — Working with NoSQL Technologies: https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html
- Spring Boot 3.5 — Testcontainers / Service Connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — `@DataCassandraTest` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/cassandra/DataCassandraTest.html
- Spring Boot 3.5 — `@DataCouchbaseTest` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/couchbase/DataCouchbaseTest.html
- Spring Boot 3.5 — `@DataLdapTest` Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/ldap/DataLdapTest.html
- Spring Data Apache Cassandra — Reference: https://docs.spring.io/spring-data/cassandra/reference/
- Spring Data Couchbase — Reference: https://docs.spring.io/spring-data/couchbase/reference/
- Spring Data LDAP — Reference: https://docs.spring.io/spring-data/ldap/reference/
- Spring LDAP — Directory Context Adapter: https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html
- Spring LDAP — Testing: https://docs.spring.io/spring-ldap/reference/testing.html
- Testcontainers Java — Cassandra Module: https://java.testcontainers.org/modules/databases/cassandra/
- Testcontainers Java — Couchbase Module: https://java.testcontainers.org/modules/databases/couchbase/
- Spring Boot 4 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
