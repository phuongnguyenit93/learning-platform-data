# Kiểm thử CAS bằng hai cập nhật cạnh tranh trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả chính xác **Compare-And-Swap (CAS)** của Couchbase: giá trị CAS nằm trong metadata, làm token điều kiện ghi, không phải số thứ tự nghiệp vụ.
2. Hiểu vai trò của `@Version` trong Spring Data Couchbase và phân biệt lỗi `OptimisticLockingFailureException` với lỗi domain hoặc kết nối.
3. Viết một test **tuần tự nhưng tái hiện được stale snapshot** bằng cách đọc hai bản của cùng document trước khi ghi.
4. Viết test **hai luồng ghi cạnh tranh thực sự**, sử dụng `ExecutorService` và `CountDownLatch` để bảo đảm cả hai đọc **cùng phiên bản trước khi bắt đầu save**.
5. Kiểm tra bất biến **chính xác một write thành công, một write bị từ chối** và dữ liệu cuối không bị cập nhật thất lạc.
6. Xác minh hành vi CAS độc lập qua Couchbase Java SDK `GetResult.cas()` và `ReplaceOptions.cas(...)`.
7. Thiết kế **retry có giới hạn**: đọc lại trạng thái, tính lại thao tác nghiệp vụ, xử lý hết hàng và idempotency; không lặp mãi một entity stale.
8. Phân biệt CAS với transaction đa document, durability, TTL, sub-document mutation và reactive I/O.
9. Tổ chức Testcontainers, fixture, cleanup và CI để test concurrency đáng tin, không phụ thuộc thứ tự scheduler hay tốc độ máy.

Bài thuộc chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và SQL++; đồng thời học bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn reactive API. Ở đây, đối tượng kiểm chứng trung tâm là **điều kiện ghi bằng CAS trên Couchbase Server thật**, không phải một mock được lập trình để ném lỗi.

> **Hợp đồng cần chứng minh:** Khi hai writers đọc cùng phiên bản V0 của một document, rồi cùng muốn thay nó, **không thể cả hai đều ghi thành công dựa trên CAS V0**. Có một write thắng và một write bị từ chối do stale CAS, trừ khi mã thực thi retry bằng cách **đọc lại** và thử trên phiên bản mới.

## 1. Bài toán lost update khi hai request cùng sửa một document

Giả sử kho hàng có:

~~~json
{
  "sku": "coffee-250g",
  "available_units": 10,
  "last_writer": "seed"
}
~~~

Hai request đặt hàng A và B cùng đọc số lượng còn 10, cùng muốn trừ 1:

~~~text
T0: Document available_units = 10, CAS = C0

Writer A: read -> 10, CAS C0
Writer B: read -> 10, CAS C0

Writer A: tính 10 - 1 = 9
Writer B: tính 10 - 1 = 9

Writer A: replace toàn document -> 9
Writer B: replace toàn document -> 9

Kết quả sai: 9, mặc dù đã chấp nhận hai đơn.
Kết quả đúng nếu chấp nhận cả hai đơn: 8.
~~~

Nếu dùng `upsert`/replace **không có điều kiện CAS**, request B có thể ghi đè công việc của request A. Đây là **lost update**.

### 1.1. CAS thay đổi điều gì?

Couchbase gắn cho mỗi phiên bản document một token CAS. Client đọc cả body và CAS; khi `replace`, client có thể gửi `expectedCas`:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant B as Writer B
    participant CB as Couchbase Server
    A->>CB: GET sku (body 10, CAS C0)
    B->>CB: GET sku (body 10, CAS C0)
    A->>CB: REPLACE body 9 IF CAS == C0
    CB-->>A: Success, new CAS C1
    B->>CB: REPLACE body 9 IF CAS == C0
    CB-->>B: CAS mismatch (current C1)
~~~

Đây là ví dụ thứ tự A thắng. Nếu B đến trước, B thắng và A bị từ chối. **Test đúng không giả định writer A luôn thắng**, vì lịch chạy của thread và network không xác định.

### 1.2. Phạm vi bất biến

CAS bảo vệ **một lần mutation trên một document** khỏi ghi đè dựa trên bản đọc cũ. Nó không tự:

- Biến hai update liên tiếp thành transaction đa document.
- Bảo đảm business operation B đã thành công khi B nhận CAS conflict.
- Tự xử lý retry, idempotency hoặc hoàn tiền.
- Bảo đảm document không bị xóa/expire giữa read và write.
- Bảo đảm toàn bộ workflow qua Kafka, HTTP hay service khác là atomic.
- Bảo đảm durability tới replica/quorum chỉ vì CAS đã khớp.

**Kiểm thử CAS** khác **kiểm thử transaction** hoặc **kiểm thử hệ thống chấp nhận đồng thời hai đơn**.

## 2. CAS là metadata, không phải @Field trong body

Spring Data Couchbase có thể ánh xạ CAS qua `@Version`:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long cas;
~~~

| Thành phần | Vai trò | Nằm ở đâu? |
| --- | --- | --- |
| Document key `@Id` | Xác định document trong collection | KV key metadata |
| CAS `@Version` | Token phiên bản dùng kiểm tra ghi | Metadata do Server cấp |
| `available_units` | Số lượng tồn kho nghiệp vụ | JSON body |
| `last_writer` | Dữ liệu quan sát writer cuối | JSON body |
| Schema version `schema_version` | Định dạng JSON/migration | JSON body nếu ứng dụng khai báo |
| TTL/expiry | Chính sách hết hạn | Metadata expiry |

**Không đồng nhất CAS với version số nguyên tăng liên tục.** CAS có thể được SDK biểu diễn bằng `long` nhưng là token opaque. Assert “khác CAS cũ” hoặc dùng token làm điều kiện ghi; không assert `newCas == oldCas + 1`, không tự tạo CAS.

### 2.1. Ảnh hưởng của @Version

Trong Spring Data Couchbase, `@Version` kích hoạt optimistic locking khi ghi entity có CAS phiên bản đã đọc. Khi một writer giữ CAS cũ và writer khác đã thay document, thao tác dựa trên bản cũ sẽ thất bại. Exception tại tầng Spring có thể được diễn đạt là:

~~~java
org.springframework.dao.OptimisticLockingFailureException
~~~

Cần kiểm chứng trên phiên bản Spring Data thực tế vì một số exception có subclass hoặc được translation qua repository/template API. Test nên bắt **loại đủ cụ thể** và kiểm tra server state cuối; không coi mọi `RuntimeException` là chứng minh CAS.

### 2.2. @Version không làm tăng số nguyên thủ công

Không viết:

~~~java
@Version
private Long cas;

// Sai: tự điều chỉnh CAS như application counter.
this.cas = this.cas + 1;
~~~

CAS do Couchbase Server sinh khi mutation thành công. Entity giữ token được mapper materialize; application không được biến nó thành business field có thể tăng hoặc ép giá trị bất kỳ.

### 2.3. Null CAS, entity mới và insert

Với Spring Data, trạng thái entity mới/đã tồn tại có thể ảnh hưởng đường `save` (insert/replace). Khi test CAS:

1. Tạo entity mới với ID riêng và `cas == null`.
2. Ghi entity lần đầu vào Couchbase.
3. **Đọc lại entity từ repository** để nhận CAS hiện hành.
4. Từ đây mới tạo hai snapshots cạnh tranh.

Đừng tự gán CAS cố định cho fixture; làm như vậy dễ biến test thành kiểm thử một trường hợp không đại diện cho normal persistence path. Những khác biệt newness detection giữa phiên bản `@Version` và custom `Persistable` phải được kiểm tra riêng khi dự án có cấu hình ấy.

## 3. Môi trường kiểm thử phù hợp với CAS

Để tái hiện CAS trên **một key trong một collection**, về nguyên tắc chỉ cần Couchbase KV Service và document thật. Không cần tạo secondary index chỉ cho `findById` hoặc `replace`.

| Nhu cầu | Tài nguyên tối thiểu |
| --- | --- |
| Hai `get` cùng key + `replace` với CAS | KV service |
| Spring Data `findById/save` cùng entity | KV service, converter, repository, named collection nếu có |
| Query theo `sku` hoặc `last_writer` | Query + Index Services, secondary index |
| Reactive `findById/save` | Reactive repository/client + server thực |
| Transaction hai document | Couchbase Transactions đúng cấu hình, có thể cần services khác tùy thao tác |
| Durability/failover nhiều replica | Multi-node topology với replicas/quorum, không chỉ một container |

### 3.1. Version được sử dụng trong ví dụ

Các đoạn Java chính minh họa **Java 17+, Spring Boot 3.5.x, Testcontainers 1.x, Couchbase Java SDK 3.x**. Với Boot 4.x/Testcontainers 2.x, kiểm tra tương thích và thay imports/artifacts.

| Thành phần | Spring Boot 3.x / Testcontainers 1.x | Spring Boot 4.x / Testcontainers 2.x |
| --- | --- | --- |
| Boot data starter | `spring-boot-starter-data-couchbase` | Starter tương ứng |
| Boot test slice | `spring-boot-starter-test` | `spring-boot-starter-data-couchbase-test` hoặc module tương ứng |
| `@DataCouchbaseTest` | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |
| Boot Testcontainers | `spring-boot-testcontainers` | `spring-boot-testcontainers` |
| Couchbase Testcontainers | `org.testcontainers:couchbase` | `org.testcontainers:testcontainers-couchbase` |
| JUnit Testcontainers | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |

~~~groovy
// Gradle, Spring Boot 3.x / Testcontainers 1.x:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Dùng BOM theo dự án, không trộn modules Testcontainers 1.x và 2.x. Image minh họa:

~~~java
DockerImageName image =
    DockerImageName.parse("couchbase/server:community-7.2.5");
~~~

Đây là **tag cố định làm ví dụ**, không phải đề xuất bắt buộc. Dự án cần pin image nằm trong compatibility matrix Couchbase Server / Java SDK / Spring Data đã được kiểm chứng.

## 4. Entity StockDocument có @Version và ranh giới nghiệp vụ

Ví dụ quản lý một SKU trong bucket `shop_it`, scope `warehouse`, collection `stocks`.

~~~text
Bucket:       shop_it
Scope:        warehouse
Collection:   stocks
Document key: it::<UUID>::stock::coffee-250g
Body:         sku, available_units, last_writer
Metadata:     CAS token
~~~

### 4.1. Java entity

~~~java
package com.example.shop.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("warehouse")
@Collection("stocks")
public class StockDocument {

    @Id
    private String id;

    @Version
    private Long cas;

    @Field
    private String sku;

    @Field("available_units")
    private int availableUnits;

    @Field("last_writer")
    private String lastWriter;

    protected StockDocument() {}

    public StockDocument(String id, String sku, int availableUnits) {
        if (id == null || id.isBlank()
                || sku == null || sku.isBlank()
                || availableUnits < 0) {
            throw new IllegalArgumentException("Stock không hợp lệ");
        }
        this.id = id;
        this.sku = sku;
        this.availableUnits = availableUnits;
        this.lastWriter = "seed";
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getSku() { return sku; }
    public int getAvailableUnits() { return availableUnits; }
    public String getLastWriter() { return lastWriter; }

    public void reserveOne(String writer) {
        if (writer == null || writer.isBlank()) {
            throw new IllegalArgumentException("Thiếu writer ID");
        }
        if (availableUnits <= 0) {
            throw new IllegalStateException("Hết hàng");
        }
        availableUnits--;
        lastWriter = writer;
    }
}
~~~

Một document được mong đợi có dạng:

~~~json
{
  "_class": "com.example.shop.inventory.StockDocument",
  "sku": "coffee-250g",
  "available_units": 10,
  "last_writer": "seed"
}
~~~

`_class` có thể khác nếu dự án dùng type alias, nhưng trường JSON `cas` **không bắt buộc nằm trong body**. Để kiểm tra, đọc raw JSON qua SDK; đừng chỉ dùng repository save–read, vì hai chiều mapping có thể cùng sai.

### 4.2. Repository

~~~java
package com.example.shop.inventory;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface StockRepository
        extends CouchbaseRepository<StockDocument, String> {
}
~~~

Test CAS cần `save`, `findById` và `deleteById`; đây chủ yếu là **KV operations**. Method tìm theo `sku` sẽ cần Query Service/index nếu được bổ sung, nhưng **không cần cho bài kiểm thử CAS cơ bản**.

## 5. Testcontainers và @DataCouchbaseTest cho kho hàng

~~~java
package com.example.shop.inventory;

import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;
import com.couchbase.client.java.manager.collection.CollectionSpec;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class StockCasIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    @Autowired StockRepository stocks;
    @Autowired Cluster cluster;

    @BeforeAll
    void prepareKeyspace() {
        cluster.waitUntilReady(Duration.ofSeconds(60));
        var bucket = cluster.bucket("shop_it");
        bucket.waitUntilReady(Duration.ofSeconds(60));
        var manager = bucket.collections();

        try {
            manager.createScope("warehouse");
        } catch (ScopeExistsException alreadyExists) {
            // Fixture idempotent.
        }

        try {
            manager.createCollection(
                CollectionSpec.create("stocks", "warehouse"));
        } catch (CollectionExistsException alreadyExists) {
            // Không xóa collection hiện hữu.
        }

        // Chờ đường KV của warehouse.stocks usable theo mục 5.1.
    }

    // Các @Test ở mục 6-9.
}
~~~

`@ServiceConnection` cấp thông tin kết nối từ `CouchbaseContainer`, **không tự tạo scope/collection**. `spring.data.couchbase.bucket-name=shop_it` phải trùng tên bucket đã khai báo. `@DataCouchbaseTest` không tự spawn server và không mặc định tải mọi `@Service` trong ứng dụng.

Nếu sử dụng `@DynamicPropertySource` thay `@ServiceConnection`:

~~~java
@DynamicPropertySource
static void couchbaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.couchbase.connection-string",
        COUCHBASE::getConnectionString);
    registry.add("spring.couchbase.username",
        COUCHBASE::getUsername);
    registry.add("spring.couchbase.password",
        COUCHBASE::getPassword);
    registry.add("spring.data.couchbase.bucket-name",
        () -> "shop_it");
}
~~~

Cách này cần imports `DynamicPropertySource` và `DynamicPropertyRegistry` từ Spring Test; không dùng **cả hai phương thức cấp endpoint** mà không hiểu precedence. Không hardcode `localhost:8091` vì Docker port mapping thay đổi.

### 5.1. Chờ named collection sẵn sàng trước khi test

Cluster và bucket ready không có nghĩa collection vừa tạo đã được toàn bộ đường request nhận diện. Có thể dùng một **KV probe** và deadline:

~~~java
import java.time.Duration;
import java.time.Instant;
import com.couchbase.client.core.error.CollectionNotFoundException;

var collection = cluster.bucket("shop_it")
    .scope("warehouse").collection("stocks");

Instant deadline = Instant.now().plus(Duration.ofSeconds(30));

while (true) {
    try {
        collection.exists("it::readiness::never-created");
        break; // Request được collection chấp nhận.
    } catch (CollectionNotFoundException transientFailure) {
        if (Instant.now().isAfter(deadline)) {
            throw new IllegalStateException(
                "Collection stocks chưa usable", transientFailure);
        }
        try {
            Thread.sleep(200);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Bị ngắt", interrupted);
        }
    }
}
~~~

Đây là polling có **điều kiện thực và timeout**, không phải ngủ 5 giây rồi hy vọng resource sẵn sàng. Nếu gặp authentication failure, sai bucket hoặc thiếu quyền, phải fail fast, không retry vô hạn.

### 5.2. Vòng đời test và isolation

- Tạo một key `it::<UUID>::stock::coffee-250g` **riêng cho từng test**.
- Chỉ xóa key do test tạo; không `deleteAll()` trong collection dùng chung.
- Không dùng `@Transactional` trong test rồi giả định mọi Couchbase mutation được rollback tự động giống JPA.
- Với nhiều test classes, quản lý Spring context cache cùng vòng đời container; tránh context giữ port của container đã dừng.

## 6. Test nền tảng: hai snapshots, hai lần save tuần tự

Trước khi thử concurrency thật bằng threads, hãy làm phép thử **cố tình stale** theo thứ tự cố định. Nó cho bằng chứng trực tiếp mà không phụ thuộc scheduler.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.dao.OptimisticLockingFailureException;

@Test
void staleSnapshotMustNotOverwriteNewerVersion() {
    String key = "it::" + UUID.randomUUID()
        + "::stock::coffee-250g";

    try {
        // 1. Seed dữ liệu thật.
        stocks.save(new StockDocument(key, "coffee-250g", 10));

        // 2. Đọc thành HAI object Java độc lập, cùng một CAS.
        StockDocument writerA =
            stocks.findById(key).orElseThrow();
        StockDocument writerB =
            stocks.findById(key).orElseThrow();

        assertNotSame(writerA, writerB);
        assertNotNull(writerA.getCas());
        assertEquals(writerA.getCas(), writerB.getCas());

        // 3. Writer A thành công, server cấp CAS mới.
        writerA.reserveOne("A");
        stocks.save(writerA);

        // 4. Writer B vẫn dùng CAS cũ.
        writerB.reserveOne("B");

        assertThrows(
            OptimisticLockingFailureException.class,
            () -> stocks.save(writerB));

        // 5. Xác minh chính STATE được server giữ lại.
        StockDocument stored =
            stocks.findById(key).orElseThrow();

        assertEquals(9, stored.getAvailableUnits());
        assertEquals("A", stored.getLastWriter());
        assertNotEquals(writerB.getCas(), stored.getCas());
    } finally {
        if (stocks.existsById(key)) {
            stocks.deleteById(key);
        }
    }
}
~~~

Đây là test **hai cập nhật cạnh tranh về phiên bản**, mặc dù các lệnh ghi được sắp thứ tự tuần tự trong test. Vì hai writers cùng đọc trước khi writer A ghi, writer B là stale snapshot chắc chắn. Cách này đặc biệt hữu ích khi cần test regression nhanh, ổn định.

### 6.1. Test đang chứng minh những gì?

- Thực sự có **hai object độc lập**, không chỉ hai biến trỏ cùng entity.
- Cả hai ban đầu có **cùng CAS token**.
- Sau khi writer A ghi, Server lưu body mới và CAS khác.
- Writer B dùng CAS cũ bị từ chối.
- Dữ liệu writer A được giữ; không bị writer B ghi đè.
- Test không giả định CAS là số tự tăng.

Test **không chứng minh** cùng một lúc hai thread có thể đến server; cho mục đích đó, xem mục 8.

### 6.2. Vì sao chỉ assert exception là chưa đủ?

Nếu code của test:

~~~java
assertThrows(Exception.class, () -> stocks.save(writerB));
~~~

thì exception do bucket sai, SDK timeout, database chưa chạy hoặc validation cũng khiến test PASS giả. Dùng exception loại rõ ràng và **kiểm tra state cuối**. Nếu Spring Data version đang chạy dịch exception sang subclass của `OptimisticLockingFailureException`, `assertThrows` với superclass vẫn chấp nhận subclass đó.

Một test mạnh còn nên kiểm tra:

~~~java
assertEquals(9, stored.getAvailableUnits());
assertEquals("A", stored.getLastWriter());
~~~

Nếu result cuối là 8 hoặc 9 với `last_writer="B"`, lỗi lost update đã xảy ra dù một nhánh code có vẻ báo conflict.

### 6.3. Cách test sai: đọc snapshot B sau khi A đã save

~~~java
StockDocument a = stocks.findById(key).orElseThrow();
a.reserveOne("A");
stocks.save(a);

StockDocument b = stocks.findById(key).orElseThrow();
b.reserveOne("B");
stocks.save(b); // Hoàn toàn có thể THÀNH CÔNG!
~~~

`b` đã có CAS **mới**, nên đây không phải stale update. Test cần **đọc cả A và B trước khi bất kỳ writer nào lưu**, hoặc dùng barrier trong concurrency test.

## 7. Đối chiếu CAS độc lập bằng Couchbase Java SDK

Spring Data giúp mapping entity và translation exception. Để kiểm chứng rằng **Couchbase Server thực sự áp dụng CAS**, hãy thử trực tiếp SDK với cùng key trong cùng collection.

### 7.1. Đọc CAS từ metadata

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.kv.GetResult;

var collection = cluster.bucket("shop_it")
    .scope("warehouse")
    .collection("stocks");

GetResult fromSdk = collection.get(key);

long serverCas = fromSdk.cas();
int units = fromSdk.contentAsObject().getInt("available_units");

assertEquals(10, units);
assertNotEquals(0L, serverCas);
assertFalse(fromSdk.contentAsObject().containsKey("cas"));
~~~

Không so CAS bằng phép cộng 1, không sử dụng JSON field tên `cas` thay `GetResult.cas()`. Nếu một custom converter chủ động lưu body field `cas` cho mục đích riêng, field đó **không thay thế** metadata CAS.

### 7.2. Hai SDK get trả hai snapshots cùng version

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

import com.couchbase.client.core.error.CasMismatchException;

var collection = cluster.bucket("shop_it")
    .scope("warehouse").collection("stocks");

var snapshotA = collection.get(key);
var snapshotB = collection.get(key);

assertEquals(snapshotA.cas(), snapshotB.cas());

var newBodyA = snapshotA.contentAsObject()
    .put("available_units", 9)
    .put("last_writer", "sdk-A");

collection.replace(
    key,
    newBodyA,
    replaceOptions().cas(snapshotA.cas())
);

var newBodyB = snapshotB.contentAsObject()
    .put("available_units", 9)
    .put("last_writer", "sdk-B");

assertThrows(
    CasMismatchException.class,
    () -> collection.replace(
        key, newBodyB,
        replaceOptions().cas(snapshotB.cas()))
);

var latest = collection.get(key);
assertEquals(9, latest.contentAsObject().getInt("available_units"));
assertEquals("sdk-A",
    latest.contentAsObject().getString("last_writer"));
~~~

Đoạn trên **giả định key đã được seed với 10 units** và phải cleanup sau test. Khi chạy độc lập:

~~~java
String key = "it::" + UUID.randomUUID()
    + "::stock::sdk-cas";
collection.insert(key, JsonObject.create()
    .put("sku", "coffee-250g")
    .put("available_units", 10)
    .put("last_writer", "seed"));

try {
    // Hai get + replace with cas như ví dụ phía trên.
} finally {
    if (collection.exists(key).exists()) {
        collection.remove(key);
    }
}
~~~

SDK ném `CasMismatchException` khi expected CAS không còn khớp. Spring Data repository có thể chuyển điều kiện này thành `OptimisticLockingFailureException`. **Không nên đòi exception hai tầng có cùng tên.**

### 7.3. SDK replace không có CAS sẽ chứng minh điều ngược lại

~~~java
// Không dùng cho cập nhật read-modify-write có yêu cầu tránh lost update:
collection.replace(key, snapshotB.contentAsObject());
~~~

Nếu `replace` không mang `ReplaceOptions.cas(...)`, Server không kiểm tra rằng phiên bản hiện tại còn là phiên bản B đã đọc. Test âm tính trên **collection độc quyền** có thể chứng minh sự khác biệt, nhưng đừng để một ví dụ race cố tình unsafe chạy trên dữ liệu quan trọng.

### 7.4. Đọc raw body để bắt lỗi mapping

Sau khi Spring Data writer A save, SDK raw JSON phải cho thấy:

~~~java
var json = collection.get(key).contentAsObject();

assertEquals(9, json.getInt("available_units"));
assertEquals("A", json.getString("last_writer"));
assertFalse(json.containsKey("id"));
~~~

Nếu developer đổi annotation nhầm thành `@Field("availble_units")`, repository save–read vẫn có thể cùng sai mà test PASS; SDK raw JSON assertion phát hiện.

## 8. Test hai cập nhật song song thật bằng CountDownLatch

Phép thử tuần tự ở mục 6 xác minh stale CAS một cách bền vững. Nhưng khi nghiệp vụ xử lý nhiều requests đồng thời, bạn cũng muốn kiểm chứng hai threads cùng đi qua **đường repository thực**.

Sai lầm thường gặp là chạy hai futures rồi hy vọng chúng vô tình đọc cùng CAS:

~~~java
pool.submit(() -> readModifySave("A"));
pool.submit(() -> readModifySave("B"));
~~~

Một task có thể chạy trọn trước khi task kia đọc; cả hai lần save đều hợp lệ và test không hề tạo conflict.

**Giải pháp:** dùng hai latches:

- `loaded`: cả hai writers đã đọc snapshot.
- `release`: chỉ khi đã có **hai snapshots cùng CAS**, mới cho cả hai đi tới thao tác lưu.

~~~mermaid
sequenceDiagram
    participant Test as JUnit thread
    participant A as Worker A
    participant B as Worker B
    participant CB as Couchbase
    Test->>A: submit A
    Test->>B: submit B
    A->>CB: findById -> body10, CAS C0
    B->>CB: findById -> body10, CAS C0
    A-->>Test: loaded.countDown()
    B-->>Test: loaded.countDown()
    Test-->>A: release.countDown()
    Test-->>B: release.countDown()
    A->>CB: save CAS C0
    B->>CB: save CAS C0
    CB-->>A: One success or conflict
    CB-->>B: Opposite outcome
    Test->>CB: findById final state
~~~

### 8.1. Outcome tách success và conflict

Trong test class `StockCasIT`, khai báo một record nhỏ:

~~~java
private record Outcome(
    String writer,
    Long readCas,
    boolean saved,
    boolean conflict
) {}
~~~

Không đưa exception tùy ý vào nhóm `conflict`; chỉ bắt `OptimisticLockingFailureException`. Lỗi mạng/authentication cần làm test fail.

### 8.2. Worker helper: đọc xong phải chờ barrier

~~~java
private Outcome reserveFromSameSnapshot(
        String key,
        String writer,
        CountDownLatch loaded,
        CountDownLatch release) throws Exception {

    StockDocument snapshot =
        stocks.findById(key).orElseThrow();

    Long originalCas = snapshot.getCas();
    loaded.countDown();

    if (!release.await(15, TimeUnit.SECONDS)) {
        throw new AssertionError(
            "Không nhận được tín hiệu bắt đầu save");
    }

    snapshot.reserveOne(writer);

    try {
        stocks.save(snapshot);
        return new Outcome(writer, originalCas, true, false);
    } catch (OptimisticLockingFailureException conflict) {
        return new Outcome(writer, originalCas, false, true);
    }
}
~~~

Các imports trong class:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.dao.OptimisticLockingFailureException;
~~~

**Tại sao `loaded.countDown()` nằm sau `findById`?** Nếu báo sẵn sàng trước khi đọc, test thread có thể cho writer A save xong rồi writer B mới đọc CAS mới — lúc ấy không còn conflict bắt buộc.

### 8.3. Test concurrent race hoàn chỉnh

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

@Test
void exactlyOneConcurrentWriterCanSaveTheOldCas()
        throws Exception {

    String key = "it::" + UUID.randomUUID()
        + "::stock::race";

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch loaded = new CountDownLatch(2);
    CountDownLatch release = new CountDownLatch(1);

    try {
        stocks.save(new StockDocument(key, "coffee-250g", 10));

        Future<Outcome> fa = pool.submit(() ->
            reserveFromSameSnapshot(
                key, "A", loaded, release));

        Future<Outcome> fb = pool.submit(() ->
            reserveFromSameSnapshot(
                key, "B", loaded, release));

        // Cả HAI đã đọc trước khi cho phép bất kỳ save nào.
        assertTrue(loaded.await(20, TimeUnit.SECONDS));
        release.countDown();

        Outcome a = fa.get(30, TimeUnit.SECONDS);
        Outcome b = fb.get(30, TimeUnit.SECONDS);

        assertNotNull(a.readCas());
        assertEquals(a.readCas(), b.readCas());

        // Không phụ thuộc A hay B thắng.
        assertEquals(1, java.util.stream.Stream.of(a, b)
            .filter(Outcome::saved).count());
        assertEquals(1, java.util.stream.Stream.of(a, b)
            .filter(Outcome::conflict).count());

        StockDocument stored =
            stocks.findById(key).orElseThrow();

        assertEquals(9, stored.getAvailableUnits());
        assertTrue(Set.of("A", "B")
            .contains(stored.getLastWriter()));

        Outcome winner = a.saved() ? a : b;
        assertEquals(winner.writer(), stored.getLastWriter());
    } finally {
        // Giải phóng thread nếu test bị timeout ở await/assertion.
        release.countDown();
        pool.shutdownNow();
        pool.awaitTermination(10, TimeUnit.SECONDS);

        if (stocks.existsById(key)) {
            stocks.deleteById(key);
        }
    }
}
~~~

**Hai asserts quan trọng nhất** là:

~~~java
assertEquals(1, successes);
assertEquals(1, conflicts);
~~~

và trạng thái cuối `availableUnits == 9`. Nếu cả hai writes đều thành công dựa trên snapshot cũ, đây là bug hoặc thiếu CAS guard. Nếu cả hai đều thất bại, có thể môi trường/setup/cơ chế mapping không đúng — không được coi đó là CAS PASS.

### 8.4. Điều gì vẫn có thể làm test này thất bại vì hạ tầng?

- Container chưa sẵn sàng, bucket/collection chưa provision.
- Một thread bị block lâu do CPU CI, `loaded.await` timeout.
- Spring Data converter gặp lỗi, không phải CAS conflict.
- Thiếu quyền runtime, network đứt hoặc container bị dừng.
- Test khác sửa **cùng key** do fixture dùng key cố định.
- Cleanup chạy trước khi futures kết thúc nếu test code quản lý lifecycle sai.

Vì vậy test dùng **UUID cho key**, hai futures cùng một class và timeout riêng cho barrier/get; không dùng `Thread.sleep(500)` để tạo race.

### 8.5. Tại sao không dùng Thread.sleep để ép race?


## 9. Hành vi khi có conflict: từ chối hay retry?

Phép thử mục 8 cố ý **không retry**. Một lần reserve thành công, một lần bị từ chối, tồn kho còn 9. Đó là kết quả đúng của **một vòng optimistic write không retry**, nhưng chưa phải kết quả cuối cùng của một nghiệp vụ muốn xử lý cả hai yêu cầu.

Có hai hợp đồng khác nhau:

| Hợp đồng | Xử lý writer thua CAS | Kỳ vọng tồn kho từ 10 khi có 2 yêu cầu |
| --- | --- | --- |
| **Fail fast** | Trả conflict/409, client quyết định thử lại | 9 và một request thất bại |
| **Retry có giới hạn** | Đọc trạng thái mới, kiểm tra lại invariant, lưu trên CAS mới | 8 nếu cả hai yêu cầu hợp lệ và retry thành công |
| **Hết hàng** | Đọc lại thấy không đủ hàng | Không âm, từ chối yêu cầu còn lại |
| **Lỗi hạ tầng** | Timeout, auth failure, ambiguous mutation | Không coi như CAS; phải phân loại |

**Đừng viết test “hai thread đều phải thành công” cho đoạn code chỉ có một lần `save`.** Mục tiêu đó thuộc service retry/idempotency, không thuộc cơ chế CAS tự thân.

### 9.1. Retry đúng: luôn đọc lại document trước khi ghi tiếp

Ví dụ service nghiệp vụ có một retry budget nhỏ:

~~~java
package com.example.shop.inventory;

import org.springframework.dao.OptimisticLockingFailureException;

public class StockReservationService {

    private static final int MAX_ATTEMPTS = 5;
    private final StockRepository stocks;

    public StockReservationService(StockRepository stocks) {
        this.stocks = stocks;
    }

    public StockDocument reserveOneWithRetry(
            String key, String writer) {

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            // Mỗi vòng phải đọc CAS mới và trạng thái mới nhất.
            StockDocument current =
                stocks.findById(key).orElseThrow();

            // Có thể ném lỗi domain nếu available_units == 0.
            // Lỗi này KHÔNG được retry như CAS conflict.
            current.reserveOne(writer);

            try {
                return stocks.save(current);
            } catch (OptimisticLockingFailureException conflict) {
                if (attempt == MAX_ATTEMPTS) {
                    throw conflict;
                }
                // Vòng sau đọc lại, không save current stale nữa.
            }
        }
        throw new IllegalStateException("Không thể tới đây");
    }
}
~~~

Đây là **thuật toán nền tảng**, chưa phải production implementation hoàn chỉnh. Ứng dụng thật thường bổ sung backoff + jitter, timeout, metrics, cancellation, idempotency và xử lý lỗi kết nối không rõ mutation đã áp dụng hay chưa.

Không retry một exception khác như `DocumentNotFoundException` hoặc authentication failure bằng cùng policy nếu chưa xác định rõ nguyên nhân và hành vi mong muốn.

### 9.2. Cách retry sai: lặp lại chính stale object

~~~java
StockDocument stale = stocks.findById(key).orElseThrow();

for (int attempt = 0; attempt < 5; attempt++) {
    try {
        stocks.save(stale); // Nếu CAS cũ thì lặp vẫn CAS cũ.
    } catch (OptimisticLockingFailureException ignored) {
        // SAI: không reload state hoặc recompute thay đổi.
    }
}
~~~

Một stale CAS sẽ không tự trở thành token mới chỉ vì thêm sleep hoặc retry `save`. Thao tác nghiệp vụ còn phải được **tính lại trên state mới**, tránh ghi đè số lượng đã bị request khác thay đổi.

### 9.3. Test retry theo thứ tự xác định

Nếu service retry ở trên chưa được inject vào test slice, ta vẫn có thể chứng minh **semantics đọc lại và ghi lần thứ hai**:

~~~java
@Test
void aRejectedReservationCanSucceedAfterReload() {
    String key = "it::" + UUID.randomUUID()
        + "::stock::retry";

    try {
        stocks.save(new StockDocument(key, "coffee-250g", 10));

        StockDocument first = stocks.findById(key).orElseThrow();
        StockDocument stale = stocks.findById(key).orElseThrow();

        first.reserveOne("A");
        stocks.save(first); // 10 -> 9

        stale.reserveOne("B");
        assertThrows(
            OptimisticLockingFailureException.class,
            () -> stocks.save(stale));

        // B phải reload rồi mới thử lại.
        StockDocument refreshed =
            stocks.findById(key).orElseThrow();

        assertEquals(9, refreshed.getAvailableUnits());

        refreshed.reserveOne("B");
        stocks.save(refreshed); // 9 -> 8

        StockDocument finalState =
            stocks.findById(key).orElseThrow();

        assertEquals(8, finalState.getAvailableUnits());
        assertEquals("B", finalState.getLastWriter());
    } finally {
        if (stocks.existsById(key)) {
            stocks.deleteById(key);
        }
    }
}
~~~

Test này phân biệt rõ **không retry thì một success**, **đọc lại và retry thì có thể có hai success**. Nó cũng chứng minh CAS không tự “khóa” document mãi mãi sau conflict.

### 9.4. Hết hàng: invariant quan trọng hơn số lần retry

Nếu `available_units = 1` và hai requests cùng reserve 1:

1. Cả hai ban đầu đọc 1/CAS C0.
2. Một writer save thành công, còn 0/CAS C1.
3. Writer thứ hai bị CAS mismatch.
4. Khi retry, writer thua đọc 0.
5. Domain `reserveOne` phải trả lỗi **hết hàng**, không lưu `-1`.

Test phải kiểm tra **final available_units == 0** và chỉ **một reservation được chấp nhận**. Nếu test chỉ assert có CAS exception nhưng không test business invariant, vẫn có thể cho phép âm hàng trong đường retry.

### 9.5. Timeout hoặc kết quả mutation không rõ khác CAS mismatch

Trong hệ phân tán, client có thể timeout sau khi Server đã áp dụng mutation nhưng trước khi client nhận response. Đây là tình huống **ambiguous outcome**, không giống CAS mismatch được Server xác nhận.

- Khi nhận CAS mismatch, xác nhận expected CAS không còn khớp.
- Khi nhận timeout/ambiguous mutation, **chưa chắc** thao tác đã thành công hay thất bại.
- Nếu tự retry một lệnh trừ hàng không có idempotency key, có nguy cơ **trừ hàng hai lần**.
- Cần query state/reconcile hoặc dùng một protocol idempotency được thiết kế rõ.

**Không bắt `Exception.class` rồi retry như CAS mismatch.** Đây là một lỗi vận hành có thể gây duplicate side effect.

## 10. Idempotency: một request được gửi lại không phải request mới

CAS phát hiện lost update giữa hai snapshot, nhưng không ngăn client retry cùng một **business command** dưới một key mới hoặc sau timeout.

Ví dụ:

~~~text
Order requestId = req-789
Client gửi reserveOne(req-789)
Response bị mất
Client gửi lại reserveOne(req-789)

Nếu chỉ lấy stock mới nhất rồi trừ 1:
  Có thể trừ hàng hai lần cho cùng một request.
~~~

Hãy phân biệt:

- **Concurrency control:** CAS kiểm tra một phiên bản document có bị thay đổi.
- **Idempotency:** một `requestId` đã xử lý rồi không được áp dụng lại.
- **Transactional consistency:** nhiều document/bản ghi side effect có được commit cùng nhau.

### 10.1. Những hướng thiết kế idempotency

1. Tạo operation document với key xác định, ví dụ `reservation::req-789`, được ghi bằng insert-only và có trạng thái xử lý.
2. Nếu cần atomically update stock + operation record, cân nhắc Couchbase Transactions/outbox hoặc workflow reconciliation phù hợp.
3. Có thể ghi token thao tác trong Stock document để đảm bảo điều kiện single-document, nhưng **không để danh sách request IDs tăng không giới hạn**.
4. Đặt expiry/retention của idempotency record theo thời hạn nghiệp vụ chấp nhận duplicate.
5. Test cả trường hợp request lặp lại **sau khi lần đầu thành công**, không chỉ hai requests ID khác nhau.

Chỉ lưu một field `last_writer` trong ví dụ Stock **không đủ** để chống replay request cũ; nó nhằm dễ quan sát winner trong CAS test.

### 10.2. Test cases bắt buộc cho idempotent reservation

| Kịch bản | Kỳ vọng |
| --- | --- |
| `req-1` lần đầu | Trừ 1 đúng một lần |
| `req-1` gửi lại sau response bị mất | Không trừ lần hai |
| `req-1` và `req-2` cạnh tranh, stock còn đủ | Cả hai được xử lý đúng theo retry/transaction policy |
| `req-1` và `req-2` cạnh tranh, stock chỉ còn 1 | Chỉ một được chấp nhận, stock không âm |
| Timeout giữa stock update và operation record | Reconcile có thể xác định trạng thái |
| Idempotency key trùng nhưng payload khác | Từ chối hoặc xử lý theo policy rõ, không im lặng |

Một bài test CAS thuần **không đủ** chứng minh tất cả kịch bản idempotency; nên có suite riêng khi đây là tính năng sản phẩm.

## 11. Các đường ghi có thể vô tình bỏ qua CAS guard

Một class entity có `@Version` không đảm bảo **mọi code trong ứng dụng** luôn sử dụng CAS. Hãy kiểm kê:

- Repository `save(entity)` có version mapping.
- `CouchbaseTemplate` thực thi save/replace theo API và metadata tương ứng.
- SDK `Collection.upsert(...)` được gọi trực tiếp mà không có điều kiện.
- SDK `Collection.replace(...)` **có/không có** `ReplaceOptions.cas(...)`.
- Sub-document `mutateIn(...)` có/không có `MutateInOptions.cas(...)`.
- SQL++ `UPDATE` theo predicate có/không có kiểm soát phiên bản.
- Transaction wrapper có conflict/rollback semantics riêng.

| Đường mutation | CAS tự động vì Java entity có @Version? | Hành động kiểm thử |
| --- | --- | --- |
| Spring Data repository save entity đã đọc | Theo mapping/version của repository | Test stale snapshot |
| Spring Data CouchbaseTemplate save entity | Theo API/configuration cụ thể | Test chính đường template |
| SDK `replace` với `cas(expected)` | Có điều kiện CAS SDK | Test `CasMismatchException` |
| SDK `replace` không truyền CAS | Không có expected CAS từ caller | Test lost-update risk nếu dùng |
| SDK `upsert` thông thường | Không dựa vào `@Version` của entity Java | Không dùng thay CAS-safe RMW |
| SDK sub-document mutateIn có CAS options | Có CAS nếu truyền expected CAS | Test path + metadata |
| SQL++ UPDATE theo field | Không tự hiểu `@Version` Java | Kiểm tra predicate/version/transaction semantics |

**Quy tắc:** kiểm thử chính đường ghi mà production sử dụng. Không test repository `save` rồi tuyên bố SDK `upsert` ở một adapter khác cũng an toàn.

### 11.1. Sub-document mutation và CAS

Sub-document `mutateIn` cho phép sửa một path mà không phải gửi cả JSON body, nhưng **cùng một document vẫn có CAS metadata**. Nếu nghiệp vụ cần điều kiện “chỉ update nếu document chưa thay đổi”, dùng CAS options của sub-document mutation:

~~~java
import static com.couchbase.client.java.kv.MutateInOptions.mutateInOptions;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

var before = collection.get(key);

collection.mutateIn(
    key,
    List.of(MutateInSpec.upsert("last_writer", "sdk-A")),
    mutateInOptions().cas(before.cas())
);
~~~

Code trên **không thực hiện reserve stock**; nó chỉ minh họa CAS guard trên sub-document path. Nếu muốn tăng/giảm số lượng atomically bằng counter subdoc, cần hiểu semantics của counter operation và domain invariant; một lệnh counter không tự kiểm tra `available_units >= 1`.

### 11.2. SQL++ UPDATE là một bài kiểm thử khác

Một câu SQL++ UPDATE không tự áp dụng optimistic locking của Spring Data Java entity chỉ vì class có `@Version`. Nếu dự án dùng SQL++ mutation, hãy kiểm tra predicate dựa trên `META().cas` hoặc cơ chế transaction/guard tương ứng **theo Server version**, đồng thời xác minh số document thực được sửa và state cuối.

Không dùng một `UPDATE ... WHERE id = ...` không có CAS condition rồi coi nó là tương đương repository `save` có version.

## 12. CAS và giao dịch đa document

Giả sử khi xác nhận đơn hàng phải:

1. Trừ tồn kho ở `warehouse.stocks`.
2. Cập nhật `sales.orders` thành CONFIRMED.
3. Ghi operation/outbox event.

CAS trên Stock bảo vệ **một document**, không tự bảo đảm ba mutation commit cùng lúc. Có thể Stock đã giảm nhưng Order update thất bại.

### 12.1. Phân biệt câu hỏi kiểm thử

| Câu hỏi | Cơ chế cần xác minh |
| --- | --- |
| Hai writers update cùng Stock có lost update không? | CAS per document |
| Stock và Order có cùng commit/abort không? | Couchbase Transactions hoặc workflow consistency |
| Side effect gửi Kafka có trùng không? | Outbox/idempotency |
| Mất node khi ghi có ảnh hưởng durability không? | Multi-node topology, replicas/quorum |
| Query SQL++ có thấy mutation ngay không? | Index consistency và query options |

Một container Couchbase đơn node có thể kiểm chứng **CAS behavior** và một số transaction flows cơ bản, nhưng không đủ cho kịch bản failover/quorum nhiều node.

### 12.2. @Transactional không đồng nghĩa rollback test kiểu JPA

Không mặc định thêm `@Transactional` vào JUnit test là mọi dữ liệu Couchbase sẽ tự rollback sau test. Spring Data Couchbase transaction configuration và Couchbase SDK Transactions có cơ chế riêng, cần xác minh theo phiên bản. Test nên **cleanup document keys đã tạo** một cách tường minh.

### 12.3. Conflict trong transaction không phải chỉ một exception CAS

Transactions có khả năng retry và conflict resolution bên trong tùy SDK/configuration. Nếu test yêu cầu atomicity, phải xác minh **cả hai documents** sau commit/abort, không chỉ assert một exception. Test CAS ở mục 6/8 tập trung **non-transactional KV write** để thấy rõ compare-and-swap behavior.

## 13. TTL, remove và recreate giữa hai snapshots

Một race không chỉ gồm hai lần replace. Ví dụ:

~~~text
Writer A: GET key -> CAS C0
Writer B: REMOVE key
Writer C: INSERT lại key -> CAS Cnew
Writer A: REPLACE key với C0
~~~

Expected CAS của writer A không còn hợp lệ. Tùy thời điểm và operation, Server có thể trả **not found** khi document đã bị xóa, hoặc **CAS mismatch** khi key được tạo lại. Đừng viết test cứng rằng mọi delete race đều ném đúng một exception không đổi.

### 13.1. TTL có thể làm document biến mất giữa read và write

Nếu Stock được cấu hình TTL ngắn và hết hạn trước khi writer ghi:

- Đây có thể là `DocumentNotFound`, không phải stale-CAS conflict thông thường.
- Không tự tạo lại document với `upsert` nếu business policy yêu cầu missing stock là lỗi.
- Xác định rõ expiry khi ghi lại: mutation có thể giữ, bỏ hoặc đặt lại TTL tùy SDK/options.
- Test TTL riêng bằng **server clock** và polling có deadline, không dùng Java `Clock.fixed` để tua thời gian server.

### 13.2. CAS token và ABA pattern

ABA theo nghĩa trạng thái body trở lại giá trị cũ:

~~~text
Body 10 (CAS C0) -> Body 9 (CAS C1) -> Body 10 (CAS C2)
~~~

Dù body lại bằng 10, writer giữ CAS C0 **không được giả định còn hợp lệ**. CAS bảo vệ **phiên bản mutation**, không so sánh nội dung JSON đơn thuần. Test này cho thấy vì sao “nếu body equals snapshot cũ thì cứ save” là cách chống lost update không đúng.

### 13.3. CAS không bảo đảm thứ tự nghiệp vụ


## 14. Reactive: giữ cùng bằng chứng nhưng phải subscribe

Với Spring Data Couchbase reactive, có thể định nghĩa:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveStockRepository
        extends ReactiveCouchbaseRepository<StockDocument, String> {
}
~~~

Một publisher `Mono` không được subscribe thì thường **chưa chạy I/O**. Vì vậy test reactive CAS cần `StepVerifier` hoặc một cơ chế subscribe rõ ràng, không chỉ khởi tạo hai `Mono` rồi assert dữ liệu giả.

### 14.1. Reactive stale CAS theo thứ tự cố định

Mẫu sử dụng `Mono.zip` để đọc cả hai snapshots rồi lưu A trước B:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.springframework.dao.OptimisticLockingFailureException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<Void> race = Mono.zip(
        reactiveStocks.findById(key),
        reactiveStocks.findById(key))
    .flatMap(pair -> {
        StockDocument a = pair.getT1();
        StockDocument b = pair.getT2();

        assertEquals(a.getCas(), b.getCas());

        a.reserveOne("A");
        b.reserveOne("B");

        // Lưu A xong mới lưu B, nhưng cả hai đọc V0.
        return reactiveStocks.save(a)
            .then(reactiveStocks.save(b))
            .then();
    });

StepVerifier.create(race)
    .expectError(OptimisticLockingFailureException.class)
    .verify();

// Read-back từ server để kiểm tra available_units = 9
// và last_writer = "A", rồi cleanup key do test sở hữu.
~~~

Đây là **test stale snapshot trong reactive chain**, không phải hai writes chạy đồng thời. `Mono.zip` đảm bảo hai reads hoàn tất trước khi bắt đầu lưu. Nếu muốn kiểm thử hai reactive saves cạnh tranh thực sự, cần tạo hai snapshots trước, chạy writes song song, thu lại **cả success và conflict**; đừng để một error kết thúc pipeline rồi bỏ mất outcome của writer còn lại.

### 14.2. Reactive cleanup phải thực sự chạy

~~~java
StepVerifier.create(reactiveStocks.deleteById(key))
    .verifyComplete();
~~~

Nếu chỉ viết `reactiveStocks.deleteById(key);` rồi bỏ publisher, không có bằng chứng cleanup đã được thực thi. `StepVerifier.withVirtualTime` không tua nhanh CAS, bootstrap, index build hoặc TTL trên server.

### 14.3. Không block event-loop

Trong test setup có thể dùng blocking SDK provision keyspace rồi kiểm tra reactive repository, nhưng **không** đưa `block()` vào production reactive pipeline để xử lý CAS. Với retry reactive, dùng `retryWhen` **chỉ cho lỗi được phân loại**, có retry budget và tái tạo thao tác **sau khi đọc state mới**. Nếu source publisher giữ sẵn stale entity, chỉ resubscribe nhiều lần không tự sửa CAS.

## 15. Giám sát và hiệu năng khi hot document nhận nhiều writes

CAS giúp ngăn lost update, nhưng một document bị ghi quá thường xuyên vẫn có thể trở thành hot key:

~~~text
100 requests cùng đọc Stock K / CAS C0
    |
    +--> Một writer được commit
    |
    +--> Nhiều writers thua CAS
                |
                +--> Reload + Retry gây I/O bổ sung
                |
                +--> Lại cạnh tranh phiên bản mới
~~~

### 15.1. Các chỉ số nên đo

| Metric | Ý nghĩa |
| --- | --- |
| `stock_cas_conflicts_total` | Mutation thất bại do optimistic lock |
| `stock_cas_retry_attempts_total` | Tổng số lượt retry sau conflict |
| `stock_cas_retry_exhausted_total` | Request hết retry budget |
| `stock_reservation_rejected_total` | Domain rejection như hết hàng |
| `stock_reservation_latency` | Latency và p95/p99 |
| `stock_hot_key_write_rate` | Tần suất writes theo key nóng, tổng hợp an toàn |
| `stock_ambiguous_mutations_total` | Timeout/kết quả mutation không rõ |
| `stock_negative_inventory_violations_total` | Vi phạm invariant, mục tiêu bằng 0 |

Không gộp CAS conflict với hết hàng. Conflict có thể retry thành công; hết hàng là kết luận nghiệp vụ. Khi theo dõi, ghi số retry cuối, % success after retry và tỉ lệ lỗi hạ tầng để phân biệt contention với outage.

### 15.2. Khi nào cần thay đổi thiết kế hot key?

Nếu retry storm làm latency cao:

- Hạn chế số writers cùng cập nhật một document.
- Dùng queue/serialized processor nếu nghiệp vụ chấp nhận điều phối có thứ tự.
- Phân vùng/shard dữ liệu khi consistency model cho phép.
- Xem xét atomic KV/sub-document operations nếu vẫn giữ đúng invariant.
- Thêm admission control, backoff + jitter, request deadline.
- Dùng event log/operation documents và reconciliation khi phù hợp.
- Đo hiệu quả theo workload thực thay vì suy từ một test concurrency có hai threads.

Các lựa chọn này **không thay thế CAS một cách mặc định**; đó là biện pháp quản lý contention và thiết kế hệ thống.

## 16. Phân loại lỗi CAS, mapping và hạ tầng

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán |
| --- | --- | --- |
| Cả hai writers ghi thành công dựa trên cùng snapshot | Không có CAS guard hoặc race không được tái hiện | Kiểm tra `@Version`, SDK options và barrier |
| Không có conflict khi test threads | Writer B đọc sau writer A save | So hai `readCas`, dùng latch sau read |
| Cả hai writers thất bại | Lỗi bucket, mapping, network, permission | Xem exception class thực |
| CAS token null sau read | Mapping `@Version`/newness sai | Đối chiếu SDK `get().cas()` |
| SDK báo `CasMismatchException` nhưng repo báo loại khác | Exception translation khác tầng | Kiểm tra Spring exception taxonomy |
| Retry liên tục không thành công | Lặp lại entity stale | Reload và recompute ở mỗi attempt |
| Stock giảm 2 nhưng chỉ một request được ghi nhận | Idempotency/ambiguous outcome bug | Operation IDs, events và reconciliation |
| App báo hai successes nhưng stock chỉ giảm 1 | Lost update hoặc báo success trước commit | So accepted commands với state thực |
| Lúc PASS lúc FAIL theo CPU | Sleep thay synchronization | Dùng latches và timeout hữu hạn |
| Test PASS riêng nhưng FAIL trong suite | Key trùng hoặc cleanup xóa lẫn | UUID/ownership, không `deleteAll` |
| Document not found thay CAS mismatch | Document bị remove hoặc TTL expiry | Kiểm tra delete/recreate race |
| Reactive test không có mutation | Mono/Flux chưa subscribe | StepVerifier và terminal signal |

**Chỉ bắt lỗi CAS để test CAS.** Một `assertThrows(Exception.class, ...)` có thể PASS vì Docker chưa sẵn sàng, không chứng minh optimistic locking.

### 16.1. API trả lỗi đúng hợp đồng

Một adapter có thể chuyển `OptimisticLockingFailureException` thành HTTP 409, domain hết hàng thành một business rejection, invalid quantity thành validation error, timeout thành tình trạng cần xác minh lại. **HTTP status là lựa chọn API**, không phải Couchbase tự cấp. Unit test adapter kiểm tra response; integration test này kiểm tra nguyên nhân persistence.

### 16.2. Log đủ để điều tra nhưng không lộ dữ liệu

Có thể log synthetic test key, operation ID giả lập, số lần retry và thời gian xử lý. Không log password, PII, full JSON production hoặc credentials. CAS token là metadata kỹ thuật, không cần đưa ra public API.

## 17. Thiết kế bộ test CAS theo nhiều lớp

| Test class | Trọng tâm | Couchbase thật? |
| --- | --- | --- |
| `StockPolicyTest` | Không cho tồn kho âm | Không cần |
| `StockCasStaleIT` | Hai snapshots, writer sau bị từ chối | Có |
| `StockCasConcurrentIT` | Hai threads cùng CAS, đúng một success | Có |
| `StockCasSdkIT` | CAS trực tiếp với `ReplaceOptions.cas` | Có |
| `StockReservationRetryIT` | Reload/recompute và state sau retry | Có |
| `StockReservationIdempotencyIT` | Replay request ID không trừ hai lần | Có, thêm resource nếu cần |
| `StockCasReactiveIT` | Publisher/exception signal | Có |
| `StockTtlRaceIT` | Expiry/remove giữa read và write | Có |
| `StockTransactionIT` | Atomicity Order + Stock | Có, config giao dịch riêng |
| `StockLoadIT` | Hot key p95/p99 và retry contention | Môi trường đại diện |

### 17.1. Checklist vận hành CI

1. Pin Spring Boot/Spring Data/SDK/Testcontainers/Server version tương thích.
2. Bảo đảm Docker runtime và quota RAM/CPU; thiếu Docker nghĩa là **chưa chạy integration test**.
3. Cung cấp bucket/scope/collection đúng, chờ KV readiness.
4. Không dùng URL/credential production.
5. Seed từng test với key UUID và ownership rõ.
6. Dùng barrier có timeout cho concurrency, không sleep đoán race.
7. Cleanup **sau khi tasks đã hoàn tất**.
8. Phân loại lỗi hạ tầng, conflict và domain.
9. Không chạy tải hot-key nặng trong cùng CI job với tests hồi quy nhỏ nếu thiếu tài nguyên.
10. Readback state từ Server, không chỉ kiểm tra Java object local.

### 17.2. Assertions không phụ thuộc lịch thread

Không retry:

~~~text
successes == 1
CAS conflicts == 1
final available_units == 9
last_writer thuộc {A, B}
last_writer == winner.writer
~~~

Không nên assert:

~~~text
Writer A luôn thắng
CAS mới == CAS cũ + 1
Writer B luôn hoàn tất sau writer A theo thời gian wall-clock
~~~

Có retry, stock đủ hai units:

~~~text
Cả hai business operations khác ID đều hoàn tất
available_units giảm đúng 2
Không có stock âm
Không có duplicate operation IDs
~~~

**Một test không ném exception chưa chứng minh CAS an toàn nếu nó chưa ép hai snapshots cùng phiên bản.**

## 18. Bài thực hành: hai người cùng giữ chỗ cuối cùng

**Bối cảnh:** ứng dụng vé dùng document `SeatInventory`:

~~~json
{
  "event_id": "evt-demo",
  "available_seats": 1,
  "last_reservation_id": null
}
~~~

Document key dạng `it::<runId>::seat::evt-demo`.

### 18.1. Yêu cầu

1. Tạo Testcontainers Couchbase và collection `events.seat_inventory`.
2. Định nghĩa `SeatInventory` với `@Id`, `@Version` và `@Field("available_seats")`.
3. Test tuần tự: đọc snapshots A/B trước; A giữ chỗ, B save CAS cũ.
4. Assert optimistic conflict, Server có `available_seats=0` và `last_reservation_id="A"`.
5. Test concurrent dùng `CountDownLatch` để chặn cả hai ở sau `findById`.
6. Cho A hoặc B thắng, nhưng phải **một success + một conflict** nếu không retry.
7. Thêm retry có giới hạn; writer thua reload thấy zero phải nhận domain hết ghế.
8. Test một `requestId` gửi lại hai lần và thiết kế idempotency riêng.
9. Đối chiếu CAS với SDK `get().cas()` và `replace(..., cas)`.
10. Cleanup key riêng; không `deleteAll`.

### 18.2. Sơ đồ kết quả

~~~mermaid
flowchart TD
    A["A và B đọc seats=1, CAS C0"] --> B{"Ai save trước?"}
    B --> C["Winner: seats=0, CAS C1"]
    C --> D["Loser CAS C0 -> conflict"]
    D --> E{"Loser retry?"}
    E -->|"Không"| F["Trả conflict, seats vẫn 0"]
    E -->|"Có"| G["Reload seats=0"]
    G --> H["Domain reject: hết ghế, không âm"]
~~~

### 18.3. Biến thể từ 2 ghế

Nếu ban đầu có `available_seats=2`:

- Không retry: một success, một CAS conflict, cuối cùng còn 1 ghế.
- Có retry đọc lại: hai reservations khác ID có thể cùng thành công, cuối cùng còn 0 ghế.
- Không có CAS guard: nguy cơ báo cả hai thành công nhưng cuối cùng còn 1 ghế.

Nếu ban đầu chỉ 1 ghế, retry đúng **không thể làm cả hai thành công**, vì domain invariant quan trọng hơn retry.

### 18.4. Tự kiểm tra kiến thức

1. **CAS nằm ở đâu?** Metadata Couchbase document.
2. **`@Version` ánh xạ gì?** CAS token.
3. **CAS là bộ đếm +1?** Không, token opaque.
4. **Hai biến Java trỏ cùng object có là hai snapshots?** Không.
5. **Vì sao A/B phải đọc trước khi có write?** Để cùng expected CAS.
6. **`loaded.countDown` nên ở trước hay sau `findById`?** Sau khi đọc xong.
7. **Hai CAS writes dựa cùng phiên bản có thể cùng thành công?** Không.
8. **Test có được giả định writer A thắng?** Không.
9. **Không retry, từ 10 units có hai yêu cầu, cuối cùng còn?** 9 nếu một success.
10. **Có retry hợp lệ cho hai yêu cầu, cuối cùng còn?** 8.
11. **Từ 1 unit, loser retry thì sao?** Domain hết hàng/ghế.
12. **Retry cùng stale entity có sửa CAS không?** Không.
13. **SDK option nào cho conditional replace?** `ReplaceOptions.cas(expectedCas)`.
14. **SDK CAS exception thường là gì?** `CasMismatchException`.
15. **Spring exception là gì?** `OptimisticLockingFailureException` hoặc subclass phù hợp.
16. **CAS có commit cùng lúc hai documents không?** Không.
17. **TTL làm key biến mất có luôn ném CAS mismatch không?** Không.
18. **SDK upsert không có CAS có được `@Version` tự bảo vệ không?** Không.
19. **Reactive publisher không subscribe có chạy KV I/O không?** Không nên giả định.
20. **CAS có tự giải quyết duplicate request IDs không?** Không.

## 19. Checklist trước khi kết luận CAS đã được kiểm thử

- [ ] Test dùng Couchbase Server thật, không chỉ Mockito.
- [ ] Bucket/scope/collection đúng entity và KV ready.
- [ ] Entity có `@Id` và `@Version` mapping chính xác.
- [ ] Không tự gán/tăng CAS; để Server cấp token.
- [ ] Seed bằng key UUID riêng, read lại để nhận CAS thật.
- [ ] Đọc hai snapshots độc lập **trước khi write**.
- [ ] Assert hai snapshots có cùng CAS ban đầu.
- [ ] Test stale writer ném optimistic locking exception.
- [ ] Kiểm tra state cuối để phát hiện lost update.
- [ ] SDK test có `ReplaceOptions.cas` và `CasMismatchException`.
- [ ] Concurrency test dùng CountDownLatch sau read/trước save.
- [ ] Futures và barrier có timeout; cleanup sau khi workers kết thúc.
- [ ] Không giả định A/B thắng cố định.
- [ ] Assert đúng một save thành công và một CAS conflict khi không retry.
- [ ] Retry phải reload state và recompute action, có giới hạn attempts.
- [ ] Test domain invariant khi hàng/ghế cạn.
- [ ] Có idempotency policy riêng khi một requestId gửi lại.
- [ ] Phân biệt optimistic conflict với ambiguous mutation timeout.
- [ ] Kiểm tra đường SDK/template/SQL++/sub-document không bypass CAS guard.
- [ ] Không suy multi-document transaction hay failover từ CAS test.
- [ ] Reactive test và cleanup phải subscribe.
- [ ] Không dùng sleep cố định để tạo race.
- [ ] CI phải báo rõ hạ tầng thiếu, không biến skipped test thành PASS.
- [ ] Có metrics conflict/retry/exhaustion và log an toàn.
- [ ] Content QA học thuật được thực hiện ở bước riêng, không đồng nhất với ghi file.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Version`, CAS metadata.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD và optimistic locking.
- [Spring Data Couchbase — CouchbaseTemplate](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): template API và mapping.
- [Couchbase Java SDK — Concurrent Document Mutations](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-document-mutations.html): CAS và conditional replace.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): read, replace/upsert và CAS errors.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): mutateIn và CAS options.
- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): multi-document transaction và retry.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): CouchbaseContainer và BucketDefinition.
- [Testcontainers Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): container lifecycle.
- [Spring Boot — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): ServiceConnection, CouchbaseConnectionDetails.
- [Spring Boot — Data Couchbase Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): DataCouchbaseTest.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): reactive assertions và error signals.



