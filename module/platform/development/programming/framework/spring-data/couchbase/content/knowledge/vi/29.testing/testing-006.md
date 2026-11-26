# Tạo scope, collection, chỉ mục và dữ liệu thử có thể tái lập trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **môi trường kiểm thử tái lập**, **schema tài nguyên tái lập** và **dữ liệu thử tái lập**.
2. Khởi tạo Couchbase Server cô lập bằng Testcontainers, sau đó tạo đúng bucket, scope, collection và secondary index.
3. Dùng `Bucket.collections()`, `CollectionSpec` và `QueryIndexManager` của Couchbase Java SDK để provision tài nguyên.
4. Thiết kế **setup idempotent** mà không che lỗi quyền, lỗi kết nối hay sai định nghĩa index.
5. Seed dữ liệu theo logical ID cố định và physical document key có namespace riêng; dùng `insert`, `upsert` hoặc repository `save` đúng mục đích.
6. Chờ cluster, collection và index thực sự sẵn sàng, đồng thời giải quyết SQL++ scan consistency khi test read-after-write.
7. Kiểm thử JSON mapping, CAS, TTL, dữ liệu legacy, cleanup và thực thi song song trong CI.

Bài nằm trong chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**. Module hướng dẫn xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++; thiết kế bucket/scope/collection, index, TTL, CAS, giao dịch và lựa chọn reactive API. Trong môi trường ấy, **tạo được một container chưa đủ để chứng minh tầng dữ liệu đã được chuẩn bị đúng**.

> **Nguyên tắc:** Bộ kiểm thử tái lập không phụ thuộc dữ liệu còn sót lại, không phụ thuộc thứ tự chạy JUnit, không truy cập cluster production và không giả định index sẵn sàng chỉ vì câu lệnh CREATE INDEX hoàn thành.

## 1. Ba mức tái lập cần quản lý độc lập

Một test có thể chạy PASS trên máy cá nhân nhưng FAIL ở CI vì:

- Máy cá nhân đã có scope/collection/index từ lần chạy trước.
- CI dùng bucket mới nhưng script chưa tạo named collection.
- Docker ánh xạ port khác, test hardcode `localhost`.
- Secondary index đang build nên SQL++ chưa thấy document mới.
- Một test khác đã sửa document fixture có key dùng chung.
- Dữ liệu seed dùng `Instant.now()` khiến khoảng thời gian, phân trang hoặc thứ tự khác nhau.

Ba loại đầu vào phải được mô tả rõ:

| Lớp | Cần tái lập điều gì? | Ví dụ |
| --- | --- | --- |
| **Runtime** | Version Couchbase Server, KV/Query/Index Services, connection details, tài nguyên CI | `CouchbaseContainer` với image cố định |
| **Schema** | Bucket, scope, collection, index keys, index condition, TTL settings nếu có | `shop_it.sales.orders` và `ix_orders_customer_status` |
| **Dataset** | Document keys, JSON body, timestamps, status, expected result, cleanup | `draft-a`, `draft-b`, `confirmed-c` |

~~~mermaid
flowchart TB
    A["CouchbaseContainer + bucket"] --> B["SDK bootstrap"]
    B --> C["Tạo scope và collection"]
    C --> D["Tạo secondary index"]
    D --> E["Chờ collection/index ready"]
    E --> F["Seed dữ liệu theo fixture"]
    F --> G["Repository / Template / SQL++ / CAS tests"]
    G --> H["Cleanup theo key có chủ sở hữu"]
~~~

Thứ tự ở đây thể hiện **các điều kiện trước khi chạy assertion**. SDK bootstrap, Query Service và Index Service có thể khởi động bất đồng bộ; vì vậy phải đợi *điều kiện thực*, không chỉ ngủ một thời gian cố định.

### 1.1. Tái lập khác với tạo cùng một ID vật lý

Nếu hai CI jobs cùng chạy và đều seed document key `order::1` vào collection chung, chúng có thể ghi đè nhau. Vì thế:

- **Logical fixture ID** như `draft-a` được giữ ổn định để dễ hiểu testcase.
- **Physical document key** được ghép một `runId` duy nhất, ví dụ `it::<runId>::order::draft-a`.
- Expected status/amount/timestamp vẫn cố định.
- Cleanup chỉ xóa key của test/run đó.

UUID **dùng làm namespace** không làm kết quả nghiệp vụ ngẫu nhiên. Ngược lại, ngẫu nhiên hóa status/price/date mà không lưu seed có thể khiến testcase khó tái hiện.

## 2. Mô hình tài nguyên xuyên suốt bài

Ta dùng môi trường kiểm thử đơn hàng:

~~~text
Bucket:        shop_it
Scope:         sales
Collection:    orders
Index:         ix_orders_customer_status
Index fields:  customer_id, status, created_at
Document key:  it::<runId>::order::draft-a
               it::<runId>::order::draft-b
               it::<runId>::order::confirmed-c
               it::<runId>::order::other-d
~~~

Dữ liệu body của Order ví dụ:

~~~json
{
  "customer_id": "customer::u100",
  "status": "DRAFT",
  "amount_vnd": 150000,
  "created_at": "2026-01-15T08:00:00Z"
}
~~~

Một Spring Data document còn có thể lưu type hint `_class`. **Couchbase document key và CAS nằm ở metadata**, không mặc định thành body field `id` hoặc `version`.

### 2.1. Bộ fixture nghiệp vụ cố định

| Logical ID | customer_id | status | amount_vnd | created_at |
| --- | --- | --- | ---: | --- |
| `draft-a` | `customer::u100` | DRAFT | 150000 | 2026-01-15T08:00:00Z |
| `draft-b` | `customer::u100` | DRAFT | 250000 | 2026-01-15T09:00:00Z |
| `confirmed-c` | `customer::u100` | CONFIRMED | 400000 | 2026-01-15T10:00:00Z |
| `other-d` | `customer::u200` | DRAFT | 100000 | 2026-01-15T11:00:00Z |

Nhờ đó, khi **chỉ xét đúng dataset thuộc test hiện tại**:

- customer u100/status DRAFT có đúng hai Order.
- customer u100/status CONFIRMED có một Order.
- customer u200/status DRAFT có một Order.
- `created_at` tăng từ `draft-a` tới `other-d`.

Không assert `COUNT(*) = 4` cho toàn collection nếu nhiều suite cùng sử dụng tài nguyên. Phải lọc theo namespace, tạo collection riêng hoặc so sánh chính tập key đã seed.

## 3. Phiên bản dependency và Testcontainers

Ví dụ Java dưới đây chủ yếu dành cho **Java 17+, Spring Boot 3.5.x, Testcontainers 1.x, Couchbase Java SDK 3.x**. Khi dùng phiên bản mới hơn, đối chiếu đúng tọa độ dependency và API.

| Thành phần | Boot 3.x / Testcontainers 1.x | Boot 4.x / Testcontainers 2.x |
| --- | --- | --- |
| Data starter | `spring-boot-starter-data-couchbase` | Starter tương ứng |
| Boot test | `spring-boot-starter-test` | `spring-boot-starter-data-couchbase-test` hoặc module test tương ứng |
| Boot Testcontainers | `spring-boot-testcontainers` | `spring-boot-testcontainers` |
| Couchbase container | `org.testcontainers:couchbase` | `org.testcontainers:testcontainers-couchbase` |
| JUnit integration | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| `@DataCouchbaseTest` import | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |

~~~groovy
// Gradle cho Boot 3.x / Testcontainers 1.x.
// Sử dụng BOM và các phiên bản được dự án kiểm chứng.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

**Không trộn modules Testcontainers 1.x/2.x.** Đừng dùng image `latest` cho bộ kiểm thử hồi quy quan trọng: image có thể đổi phiên bản giữa hai lần chạy.

### 3.1. Cấu hình một CouchbaseContainer có đủ KV/Query/Index

~~~java
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.utility.DockerImageName;

CouchbaseContainer couchbase = new CouchbaseContainer(
    DockerImageName.parse("couchbase/server:community-7.2.5"))
    .withEnabledServices(
        CouchbaseService.KV,
        CouchbaseService.QUERY,
        CouchbaseService.INDEX)
    .withBucket(new BucketDefinition("shop_it"));
~~~

Tag Server `community-7.2.5` chỉ là **phiên bản minh họa được pin**; môi trường thực cần chọn image nằm trong ma trận hỗ trợ SDK/Server.

| Service | Nhiệm vụ |
| --- | --- |
| **KV** | `get`, `insert`, `replace`, repository `findById` / `save` |
| **QUERY** | SQL++ và các derived queries |
| **INDEX** | Secondary index cho query theo field |

`withBucket` tạo bucket `shop_it`. Nó **không** tạo scope `sales`, collection `orders`, index hay dữ liệu thử. Một container đơn node đủ cho nhiều phép kiểm tra KV/CAS/index, nhưng không phải bằng chứng failover hoặc quorum durability của cluster nhiều node.

## 4. Tách vòng đời hạ tầng, schema và dữ liệu

Gợi ý cấu trúc logic:

~~~text
CouchbaseContainerFixture
   |  container lifecycle + endpoint + bucket
   v
CouchbaseResourceFixture
   |  ensureScope / ensureCollection / ensureIndex
   v
OrderDataFixture
   |  per-test logical IDs, seed, owned keys
   v
OrderRepositoryIT / OrderQueryIT / OrderCasIT
~~~

| Công việc | Thời điểm thích hợp | Chủ sở hữu |
| --- | --- | --- |
| Start container | Một lần/class hoặc suite | Testcontainers/JUnit |
| Create bucket | Một lần/container | `BucketDefinition` |
| Create scope/collection | Một lần/keyspace | Resource fixture |
| Create index / wait ONLINE | Một lần/index definition | Resource fixture |
| Seed document | Theo từng test hoặc suite cô lập | Data fixture |
| Cleanup document | Sau test sở hữu | Data fixture |
| Drop scope/index | Sau cùng, chỉ với tài nguyên độc quyền | Resource fixture |

Không dùng `CREATE INDEX` ở mọi `@BeforeEach` nếu index không thay đổi. Ngược lại, đừng seed một Order dùng chung rồi để nhiều test đồng thời chỉnh sửa trạng thái của nó.

### 4.1. Spring Boot connection details không tạo schema

~~~java
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
class OrderRepositoryIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

    // @Autowired Cluster, OrderRepository, CouchbaseTemplate...
}
~~~

`@DataCouchbaseTest` là test slice; **nó không tự chạy Couchbase Server**. `@ServiceConnection` cấp endpoint/credentials từ container cho auto-configuration, không tự tạo schema/index. Bucket name phải được chọn tường minh.

Nếu ứng dụng dùng kết nối tự quản lý, thay `@ServiceConnection` bằng `@DynamicPropertySource`:

~~~java
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.DynamicPropertyRegistry;

@DynamicPropertySource
static void connection(DynamicPropertyRegistry registry) {
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

Đây là **hai cách thay thế**, không cần khai báo trùng cả hai cho cùng connection string. Không hardcode `localhost:8091` vì Testcontainers map cổng động và 8091 không phải cấu hình SDK tương đương `getConnectionString()`.

## 5. Tạo scope và collection bằng Couchbase Java SDK

Lấy manager từ đúng bucket:

~~~java
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;
import com.couchbase.client.java.manager.collection.CollectionSpec;

var bucket = cluster.bucket("shop_it");
var manager = bucket.collections();

try {
    manager.createScope("sales");
} catch (ScopeExistsException alreadyExists) {
    // Setup có thể gọi lại.
}

CollectionSpec spec = CollectionSpec.create("orders", "sales");

try {
    manager.createCollection(spec);
} catch (CollectionExistsException alreadyExists) {
    // Collection đã tồn tại.
}
~~~

`CollectionSpec.create(collectionName, scopeName)` là cách được tài liệu Java SDK 3.x mô tả; phiên bản SDK mới có thể hỗ trợ overload nhận tên trực tiếp. Hãy sử dụng API có trong dependency thực tế.

### 5.1. Vì sao chỉ bắt lỗi AlreadyExists?

Đây là anti-pattern:

~~~java
try {
    manager.createScope("sales");
    manager.createCollection(spec);
} catch (RuntimeException ignored) {
    // SAI: nuốt mất lỗi credentials, network, quota, wrong bucket.
}
~~~

Chỉ những lỗi `ScopeExistsException` và `CollectionExistsException` đã dự kiến mới được xử lý như “idempotent”. Nếu bucket sai, thiếu quyền `Manage Scopes` hoặc timeout, setup phải báo lỗi **đúng tầng**, không tiếp tục để test query báo `No index available` mơ hồ.

### 5.2. Idempotent chưa chứng minh cấu hình đúng

Scope cùng tên có thể chứa collection với retention/maxTTL khác dự kiến. Nếu test dựa vào expiry, phải kiểm tra **collection settings** chứ không chỉ sự tồn tại.

Tương tự, index `ix_orders_customer_status` cùng tên nhưng đã đổi field keys là **schema drift**. Không vì `ignoreIfExists(true)` mà bỏ qua định nghĩa hiện hữu.

### 5.3. Những tài nguyên không nên tạo lại mỗi test

| Tài nguyên | Có thể chia sẻ giữa methods? | Điều kiện |
| --- | --- | --- |
| Bucket/scope/collection | Có | Không drop khi test khác đang chạy |
| Secondary index | Có | Định nghĩa được xác nhận, không thay đổi khi test |
| Immutable seed dataset | Có điều kiện | Không có test nào sửa/xóa |
| Order mutable, TTL document | Không nên | Mỗi test một key riêng |
| Cluster context | Có | Container lifecycle tương thích Spring context cache |

Tránh tạo một scope cho mỗi method nếu chỉ cần vài document: DDL/index build rất tốn tài nguyên so với giá trị isolation đạt được.

## 6. Thời điểm provision so với @BeforeAll

Các bean Spring Data có thể được tạo khi test context load. `@BeforeAll` trong JUnit **không luôn diễn ra trước toàn bộ quá trình Spring bean initialization**.

Nếu context chỉ khởi tạo repository/template và không chạy query trong startup, thường có thể:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class OrderRepositoryIT {

    @Autowired Cluster cluster;

    @BeforeAll
    void provision() {
        cluster.waitUntilReady(Duration.ofSeconds(60));
        cluster.bucket("shop_it")
            .waitUntilReady(Duration.ofSeconds(60));

        // ensureScope, ensureCollection, ensureIndex...
    }
}
~~~

Nhưng nếu app có `@PostConstruct`, startup validator hoặc configuration bean dùng collection ngay khi khởi tạo, `@BeforeAll` là **quá muộn**. Khi đó cần fixture/initializer chạy **trước bean có I/O**, hoặc khởi động container, provision schema rồi mới tạo application context theo kiến trúc test thích hợp.

Không sửa test bằng cách thêm `Thread.sleep(10000)` vào `@BeforeAll` mà vẫn không provision tài nguyên đúng.

## 7. Chờ collection usable bằng KV probe có deadline

`cluster.waitUntilReady` và `bucket.waitUntilReady` bảo đảm mức bootstrap được SDK kiểm tra, **không bảo đảm named collection vừa tạo đã được mọi thành phần nhìn thấy**. Sau `createCollection`, hãy kiểm tra đường KV thực.

~~~java
import java.time.Duration;
import java.time.Instant;
import com.couchbase.client.core.error.CollectionNotFoundException;

var collection = cluster.bucket("shop_it")
    .scope("sales")
    .collection("orders");

Instant deadline = Instant.now().plus(Duration.ofSeconds(30));

while (true) {
    try {
        // Key probe không cần tồn tại: request tới collection phải hợp lệ.
        collection.exists("it::readiness::never-created");
        break;
    } catch (CollectionNotFoundException notReady) {
        if (Instant.now().isAfter(deadline)) {
            throw new IllegalStateException(
                "Collection sales.orders chưa usable", notReady);
        }
        try {
            Thread.sleep(200);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Bị ngắt trong khi đợi collection", interrupted);
        }
    }
}
~~~

`Thread.sleep(200)` ở đây chỉ là **khoảng cách giữa hai lần thử có điều kiện**, không phải một lần sleep cứng rồi coi tài nguyên đã sẵn sàng. Nếu nhận authentication failure, thiếu quyền, bucket không tồn tại hoặc network cấu hình sai, không retry vô hạn như với lỗi collection manifest chưa lan truyền.

### 7.1. Mỗi bước readiness có timeout riêng

| Bước | Ví dụ timeout | Điều kiện dừng |
| --- | --- | --- |
| Container start | Theo image/CI | Module startup hoàn thành |
| Cluster wait | 60 giây | SDK service readiness |
| Bucket wait | 60 giây | Bucket/KV sockets |
| Collection probe | 30 giây | Request KV tới named collection thành công |
| Index watch | 90 giây | Secondary index ONLINE |
| Query operation | Theo test SLO | SQL++ trả về theo consistency yêu cầu |

Các thời gian trên là **giá trị minh họa**, không phải SLA mặc định của Couchbase. Hãy log bước nào timeout và nguyên nhân thực, thay vì chỉ báo `Couchbase unavailable`.

## 8. Tạo secondary index theo truy vấn sẽ kiểm thử

Ví dụ truy vấn theo `customer_id` và `status`:

~~~sql
SELECT META(o).id AS orderKey,
       o.customer_id,
       o.status,
       o.created_at
FROM `shop_it`.`sales`.`orders` AS o
WHERE o.customer_id = $customerId
  AND o.status = $status
ORDER BY o.created_at, META(o).id;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_customer_status
ON `shop_it`.`sales`.`orders`(
    customer_id,
    status,
    created_at
);
~~~

Index composite này phù hợp phần filter, có thể giúp sort theo thời gian. **Hãy chạy `EXPLAIN`** để xác minh Query Service chọn index phù hợp, đặc biệt nếu query Spring Data có thêm predicate `_class` hoặc sort theo `META(o).id`.

### 8.1. Tạo secondary index bằng Java SDK

~~~java
import java.util.List;
import static com.couchbase.client.java.manager.query.CreateQueryIndexOptions.createQueryIndexOptions;

var indexes = cluster.queryIndexes();

indexes.createIndex(
    "shop_it",
    "ix_orders_customer_status",
    List.of("customer_id", "status", "created_at"),
    createQueryIndexOptions()
        .scopeName("sales")
        .collectionName("orders")
        .ignoreIfExists(true)
);
~~~

Tài liệu Java SDK 3.x mô tả API trên; trong SDK mới hơn, `scopeName` và `collectionName` thuộc cluster-level `QueryIndexManager` có thể được đánh dấu deprecated vì đã có `collection.queryIndexes()`. Hãy ưu tiên API theo collection khi dependency hiện tại hỗ trợ, không kết hợp tùy tiện hai API khác thế hệ.

**`ignoreIfExists(true)` chỉ xử lý trùng tên.** Nếu index cùng tên nhưng keys khác, lệnh vẫn có thể bỏ qua mà test query/optimizer sai. Với fixture trên cluster chia sẻ, cần kiểm tra metadata definition và fail nếu index drift.

### 8.2. Chờ index ONLINE

~~~java
import java.time.Duration;
import java.util.List;
import static com.couchbase.client.java.manager.query.WatchQueryIndexesOptions.watchQueryIndexesOptions;

indexes.watchIndexes(
    "shop_it",
    List.of("ix_orders_customer_status"),
    Duration.ofSeconds(90),
    watchQueryIndexesOptions()
        .scopeName("sales")
        .collectionName("orders")
);
~~~

`watchIndexes` **không tự tạo index**, nó đợi index đã được tạo ONLINE hoặc timeout. Nếu setup có `deferred(true)`, phải gọi `buildDeferredIndexes` đúng keyspace trước khi đợi.

### 8.3. Kiểm tra schema drift

| Điều kiện | `ignoreIfExists` có kiểm chứng? | Kiểm tra riêng cần có |
| --- | --- | --- |
| Index có tên đúng | Có thể | Tên và keyspace |
| Đúng index keys | Không | `getAllIndexes` hoặc `system:indexes` |
| Đúng thứ tự keys | Không | Compare normalized expressions |
| Đúng filter/condition | Không | Partial index condition |
| Đúng scope/collection | Không đầy đủ | Bucket/scope/keyspace metadata |
| Index ONLINE | Không | `watchIndexes` |
| Query dùng index | Không | `EXPLAIN` và test SQL++ thực |

SQL++ kiểm kê minh họa:

~~~sql
SELECT name, bucket_id, scope_id, keyspace_id,
       index_key, condition, state
FROM system:indexes
WHERE bucket_id = "shop_it"
  AND scope_id = "sales"
  AND keyspace_id = "orders";
~~~

Tên/trường metadata của `system:indexes` có thể thay đổi theo Server version. Nếu so sánh `index_key`, cần chuẩn hóa biểu thức; Server có thể đưa thêm dấu ngoặc hoặc backticks mà semantics không đổi.

Không tạo primary index `#primary` chỉ để cho query chạy: điều đó dễ che lỗi thiếu secondary index production, đồng thời có thể gây scan lớn.

## 9. Fixture dữ liệu: logical ID ổn định, physical key riêng

Bộ dữ liệu kỳ vọng:

| ID logic | Customer | Status | Amount | created_at |
| --- | --- | --- | ---: | --- |
| `draft-a` | u100 | DRAFT | 150000 | 2026-01-15T08:00:00Z |
| `draft-b` | u100 | DRAFT | 250000 | 2026-01-15T09:00:00Z |
| `confirmed-c` | u100 | CONFIRMED | 400000 | 2026-01-15T10:00:00Z |
| `other-d` | u200 | DRAFT | 100000 | 2026-01-15T11:00:00Z |

Các giá trị trên được **cố định**. Chỉ namespace ID dùng UUID để tránh va chạm:

~~~java
String runId = java.util.UUID.randomUUID().toString();
String prefix = "it::" + runId + "::order::";
String key = prefix + "draft-a";
~~~

Có thể thêm `created_at` cố định dưới dạng chuỗi ISO-8601 UTC để test sort không phụ thuộc timezone hệ điều hành. Khi production dùng `Instant`, kiểm thử riêng converter thời gian.

**Không dùng `Instant.now()` để tạo fixture nếu assertion giả định ranh giới thời gian cố định.** Clock giả hữu ích cho business-time unit tests nhưng không tua nhanh TTL trên Couchbase Server.

## 10. Entity mẫu: Spring Data mapping và named collection

~~~java
package com.example.shop.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long cas;

    @Field("customer_id")
    private String customerId;

    @Field
    private String status;

    @Field("amount_vnd")
    private long amountVnd;

    @Field("created_at")
    private String createdAt;

    protected OrderDocument() {}

    public OrderDocument(String id, String customerId, String status,
                         long amountVnd, String createdAt) {
        if (id == null || id.isBlank()
                || customerId == null || customerId.isBlank()
                || status == null || status.isBlank()
                || amountVnd < 0
                || createdAt == null || createdAt.isBlank()) {
            throw new IllegalArgumentException("Order không hợp lệ");
        }
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.amountVnd = amountVnd;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public long getAmountVnd() { return amountVnd; }
    public String getCreatedAt() { return createdAt; }

    public void confirm() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Chỉ xác nhận đơn DRAFT");
        }
        status = "CONFIRMED";
    }
}
~~~

`@Id` sử dụng document key Couchbase; `@Version` dùng CAS metadata; `@Field` mô tả tên field JSON. **Không nhầm CAS với schema version** và không suy rằng body phải có `id` hay `cas`.

Repository:

~~~java
package com.example.shop.sales;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerIdAndStatus(
        String customerId, String status);
}
~~~

`findById` thường dùng KV, không cần secondary index. `findByCustomerIdAndStatus` thường phát SQL++ theo mapping metadata và cần index.

## 11. Seed bằng Spring Data repository

Một factory tạo dataset từ namespace của **test hiện tại**:

~~~java
import java.util.List;

public static List<OrderDocument> sampleOrders(String prefix) {
    return List.of(
        new OrderDocument(prefix + "draft-a",
            "customer::u100", "DRAFT", 150000L,
            "2026-01-15T08:00:00Z"),

        new OrderDocument(prefix + "draft-b",
            "customer::u100", "DRAFT", 250000L,
            "2026-01-15T09:00:00Z"),

        new OrderDocument(prefix + "confirmed-c",
            "customer::u100", "CONFIRMED", 400000L,
            "2026-01-15T10:00:00Z"),

        new OrderDocument(prefix + "other-d",
            "customer::u200", "DRAFT", 100000L,
            "2026-01-15T11:00:00Z")
    );
}
~~~

Seed có kiểm soát:

~~~java
String prefix = "it::" + UUID.randomUUID() + "::order::";

List<OrderDocument> fixtures = sampleOrders(prefix);

fixtures.forEach(repository::save);
~~~

Dùng repository ghi fixture có ưu điểm: type hints/converter do Spring Data cung cấp **giống đường ghi production**, nên derived query của repository có cơ sở đọc được. Tuy nhiên, nó **không phải bằng chứng độc lập** rằng JSON field name đúng. Nếu cả writer và reader đều ánh xạ `amount_vnd` sai thành `amount_vd`, round-trip có thể vẫn PASS; cần SDK đọc raw JSON.

### 11.1. Type hint khi seeding qua SDK

Spring Data Couchbase có thể ghi `_class` hoặc type alias. Một repository query generated có thể bổ sung predicate theo type metadata.

Nếu seed SDK raw JSON không có `_class`:

~~~json
{"customer_id":"customer::u100","status":"DRAFT","amount_vnd":150000}
~~~

thì **SQL++ query thuần theo body** có thể trả document, nhưng derived query của Spring Data có thể không trả, tùy mapping/type filter. Đó là lý do phải chọn fixture theo **đường code thực sự cần xác minh**:

- Repository query → seed bằng repository hoặc raw JSON có type metadata hợp lệ.
- Legacy reader → seed raw JSON theo schema cũ, kiểm tra mapping compatibility riêng.
- SQL++ đọc body → có thể seed raw JSON không có type hint, nếu đó là hợp đồng cần test.

### 11.2. Insert-only so với upsert

| Thao tác | Semantics | Khi dùng trong fixture |
| --- | --- | --- |
| SDK `insert` | Chỉ tạo mới; lỗi nếu key đã tồn tại | Test duplicate, seeding per-test key |
| SDK `upsert` | Tạo hoặc thay toàn body | Reset state trong collection sở hữu độc quyền |
| SDK `replace` | Thay document phải tồn tại, có thể dùng CAS | Kiểm thử update/conflict |
| Repository `save` | Theo semantics Spring Data entity/version | Test mapping/repository workflow |
| SDK `remove` | Xóa theo key, có thể có CAS | Cleanup key đã theo dõi |

Nếu `upsert` một key dùng chung mỗi test, việc ghi đè có thể **che dữ liệu sót**, thay CAS và TTL. Với namespace riêng, `insert` thường giúp phát hiện key collision rõ hơn. Nếu test yêu cầu seed lại **cùng physical key**, quy tắc reset phải được công bố và dataset phải độc quyền.

## 12. Seed SDK raw JSON để kiểm tra reader legacy

~~~java
import com.couchbase.client.java.json.JsonObject;

var collection = cluster.bucket("shop_it")
    .scope("sales")
    .collection("orders");

String key = "it::" + UUID.randomUUID()
    + "::order::legacy-v1";

collection.insert(key,
    JsonObject.create()
        .put("customer_id", "customer::u100")
        .put("status", "DRAFT")
        .put("amount_vnd", 50000L)
        .put("created_at", "2026-01-15T07:00:00Z"));
~~~

Sau đó:

~~~java
OrderDocument loaded = repository.findById(key).orElseThrow();

assertEquals("customer::u100", loaded.getCustomerId());
assertEquals(50000L, loaded.getAmountVnd());
~~~

Ví dụ này chỉ áp dụng khi mapping config thực tế chấp nhận raw JSON không có type hint. Với polymorphic entity hoặc resolver phụ thuộc `_class`, phải chuẩn bị fixture theo hợp đồng (hoặc assert lỗi có chủ đích).

### 12.1. Kiểm thử MISSING, NULL và giá trị zero

Ba body dưới đây không tương đương trong SQL++:

~~~json
{}
~~~

~~~json
{"discount": null}
~~~

~~~json
{"discount": 0}
~~~

| SQL++ predicate | MISSING | NULL | 0 |
| --- | :---: | :---: | :---: |
| `discount IS MISSING` | TRUE | FALSE | FALSE |
| `discount IS NULL` | FALSE | TRUE | FALSE |
| `discount IS VALUED` | FALSE | FALSE | TRUE |

Nếu domain phân biệt “chưa có” với “có nhưng null”, cần seed cả hai dạng và kiểm chứng qua SDK raw JSON hoặc mapper/converter giữ field presence. Java `Long discount` nullable thường **không giữ đủ** thông tin khác nhau giữa hai trạng thái ấy.

## 13. Đối chiếu Spring Data với SDK raw JSON

Sau khi repository lưu entity:

~~~java
OrderDocument saved = repository.save(
    new OrderDocument(key, "customer::u100", "DRAFT",
        150000L, "2026-01-15T08:00:00Z")
);

var result = cluster.bucket("shop_it")
    .scope("sales").collection("orders")
    .get(saved.getId());

var body = result.contentAsObject();

assertEquals("customer::u100", body.getString("customer_id"));
assertEquals("DRAFT", body.getString("status"));
assertEquals(150000L, body.getLong("amount_vnd"));
assertEquals("2026-01-15T08:00:00Z",
    body.getString("created_at"));

assertFalse(body.containsKey("id"));
assertNotEquals(0L, result.cas());
~~~

Kiểm tra này bắt lỗi `@Field` dù cả writer và reader Spring Data đều dùng cùng một tên sai. `id` và CAS đến từ metadata, **không phải JSON body**. Nếu dự án có custom converter chủ động ghi ID vào body, điều kiện `containsKey("id")` phải đổi theo hợp đồng thật.

### 13.1. Test CouchbaseTemplate đúng đường production

Nếu production code dùng `CouchbaseTemplate`, test repository không thay thế được:

~~~java
@Autowired CouchbaseTemplate template;

OrderDocument loaded =
    template.findById(OrderDocument.class).one(key);

assertEquals("customer::u100", loaded.getCustomerId());
~~~

Tùy phiên bản Spring Data, fluent API có thể thay đổi. Nếu code sản phẩm override `scope/collection` trên template, test cần dùng chính override đó; không dùng default collection rồi kết luận đã kiểm tra `sales.orders`.

## 14. Query test phải xác minh đúng dataset và consistency

SQL++ truy vấn theo field thường dùng secondary index, có thể chưa thấy ngay mutation vừa ghi ở chế độ scan consistency mặc định. **Index ONLINE khác với index đã bắt kịp dữ liệu của request hiện tại.**

Ví dụ Java SDK dùng `REQUEST_PLUS`:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
    """
    SELECT META(o).id AS orderKey,
           o.customer_id, o.status, o.created_at
    FROM `shop_it`.`sales`.`orders` AS o
    WHERE o.customer_id = $customerId
      AND o.status = $status
    ORDER BY o.created_at, META(o).id
    """,
    queryOptions()
        .parameters(JsonObject.create()
            .put("customerId", "customer::u100")
            .put("status", "DRAFT"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);

var rows = result.rowsAsObject();
~~~

`REQUEST_PLUS` giúp query chờ index theo consistency yêu cầu và có thể tăng latency. Nó **không tự tạo index**, không sửa JSON field bị gõ sai và không thay trách nhiệm setup Query/Index Services.

### 14.1. Không assert COUNT trên tập dữ liệu dùng chung

Đoạn sau chỉ đúng khi collection chứa đúng dataset của test:

~~~java
assertEquals(2, rows.size());
~~~

Nếu test A và test B cùng seed `customer::u100` trong collection chung, query có thể trả về dữ liệu của cả hai, dù mọi document đều đúng.

Ba lựa chọn an toàn hơn:

1. **Collection riêng cho suite** với quyền sở hữu rõ và không chạy test khác chung keyspace.
2. **Customer ID riêng cho mỗi test**, ví dụ `customer::it::<runId>::u100`; query theo customer ID ấy.
3. **Test-run field** như `test_run_id` trong JSON nếu hợp đồng dữ liệu cho phép, rồi lọc query theo field này và index phù hợp.

Trong khi đó, chỉ kiểm tra `rows` chứa các keys cần tìm không chứng minh **không có kết quả dư**. Muốn assert số lượng chính xác, phải có dữ liệu đầu vào được cô lập.

### 14.2. Ví dụ fixture dùng customer riêng theo runId

~~~java
String runId = UUID.randomUUID().toString();
String prefix = "it::" + runId + "::order::";
String customerU100 = "customer::it::" + runId + "::u100";
String customerU200 = "customer::it::" + runId + "::u200";

List<OrderDocument> fixtures = List.of(
    new OrderDocument(prefix + "draft-a",
        customerU100, "DRAFT", 150000,
        "2026-01-15T08:00:00Z"),
    new OrderDocument(prefix + "draft-b",
        customerU100, "DRAFT", 250000,
        "2026-01-15T09:00:00Z"),
    new OrderDocument(prefix + "confirmed-c",
        customerU100, "CONFIRMED", 400000,
        "2026-01-15T10:00:00Z"),
    new OrderDocument(prefix + "other-d",
        customerU200, "DRAFT", 100000,
        "2026-01-15T11:00:00Z")
);

fixtures.forEach(repository::save);
~~~

Query theo `customerU100` và `status = "DRAFT"` có hai kết quả thuộc dataset riêng; query theo `customerU200` có một kết quả. Tên logical fixtures và thứ tự timestamp vẫn bất biến; chỉ **identity của môi trường test** thay đổi.

Với test index/query, cần gọi **chính method repository** nếu muốn chứng minh derived query hoạt động, không chỉ chạy SQL++ SDK. Spring Data có thể thêm `_class`/projection metadata, nên query SDK thuần và repository query không tương đương hoàn toàn.

### 14.3. Pagination và ORDER BY

Không dựa vào thứ tự mặc định của kết quả Couchbase:

~~~sql
ORDER BY o.created_at, META(o).id
~~~

`META(o).id` làm tie-break khi hai document có `created_at` giống nhau. Test nên có ít nhất một cặp timestamp trùng nếu muốn xác minh phân trang ổn định.

### 14.4. Kiểm tra EXPLAIN theo đường truy cập

Khi hiệu năng quan trọng:

~~~sql
EXPLAIN
SELECT META(o).id
FROM `shop_it`.`sales`.`orders` AS o
WHERE o.customer_id = "customer::u100"
  AND o.status = "DRAFT";
~~~

Mục tiêu là kiểm chứng index dự kiến phù hợp với predicate thực. **Không** suy từ tên index rằng optimizer bắt buộc dùng index ấy; `EXPLAIN`, thống kê/index definition và Server version mới quyết định.

## 15. Idempotent resource setup không đồng nghĩa upsert dữ liệu tùy tiện

Giả sử gọi fixture setup hai lần vào cùng container.

| Thành phần | Lần đầu | Lần thứ hai | Khi cấu hình drift |
| --- | --- | --- | --- |
| Bucket | `withBucket` tạo | Giữ resource | Fail nếu bucket khác kỳ vọng |
| Scope `sales` | Create | Bắt ScopeExists | Không tự drop dữ liệu |
| Collection `orders` | Create | Bắt CollectionExists | So retention/TTL nếu test dùng |
| Secondary index | Create + wait | Đối chiếu definition + wait | Fail, không ignore |
| Seed per-test | Tạo key có runId riêng | Tạo runId khác | Không chồng lên fixture cũ |
| Seed shared immutable | Tạo một lần | Verify state giống contract | Không âm thầm overwrite |
| Cleanup | Xóa owned keys | Not-found được xử lý có chủ đích | Không xóa resource của suite khác |

Resource setup idempotent có nghĩa là **gọi lại không phá state**, không có nghĩa “nuốt mọi RuntimeException”. Với index, `ignoreIfExists(true)` chỉ tránh lỗi trùng tên; cần metadata/`EXPLAIN` để phát hiện drift.

### 15.1. Kiểm tra độ bao phủ của seed

Sau khi seed, hãy kiểm tra **trước assertion nghiệp vụ**:

- Tất cả keys dự kiến tồn tại bằng KV.
- Body JSON có các field bắt buộc, đúng kiểu và giá trị.
- Các keys đều thuộc đúng scope/collection.
- Type hint `_class`/alias phù hợp nếu Spring Data query cần.
- CAS/expiry metadata có trạng thái mong muốn.
- Không có key trùng hoặc document bị upsert từ lần chạy trước.

Một kiểm tra seed quá đơn giản (chỉ `repository.count() > 0`) có thể PASS nhờ dữ liệu sót của suite khác. Khi collection chia sẻ, đếm theo ownership/physical keys đã seed.

### 15.2. Khi seed hỏng giữa chừng

Nếu seed được ba trong bốn Order rồi thất bại, **không bỏ lại ba document**:

~~~java
List<String> createdKeys = new ArrayList<>();

try {
    for (OrderDocument order : fixtures) {
        repository.save(order);
        createdKeys.add(order.getId());
    }
    // Run tests/assertions...
} finally {
    for (String key : createdKeys) {
        repository.deleteById(key);
    }
}
~~~

Đoạn trên minh họa quản lý ownership, nhưng có khoảng trống nếu mutation **đã thành công ở server** rồi client nhận timeout **trước khi thêm key vào createdKeys**. Với fixture, có thể **đăng ký key dự kiến trước khi gọi insert/save** và cleanup xử lý not-found. Để không tạo lỗi giả từ cleanup, hãy phân biệt DocumentNotFound với lỗi quyền/kết nối.

### 15.3. Không reset một collection dùng chung bằng deleteAll

`repository.deleteAll()` trong `@AfterEach` có thể xóa fixture của test song song. Tương tự, `dropScope("sales")` hoặc `dropCollection("orders")` chỉ được thực hiện khi fixture **sở hữu độc quyền** resource và chắc chắn không còn suite nào sử dụng.

Nếu mỗi test sở hữu keys, cleanup theo key là lựa chọn an toàn hơn; với shared CI cluster, tài nguyên cần namespace và thời hạn cleanup phù hợp.

## 16. Kiểm thử CAS, TTL và dữ liệu lỗi trên cùng fixture

### 16.1. CAS cần hai snapshot độc lập

~~~java
String key = "it::" + UUID.randomUUID() + "::order::cas";

try {
    repository.save(new OrderDocument(
        key, "customer::u100", "DRAFT", 100000,
        "2026-01-15T08:00:00Z"));

    OrderDocument first = repository.findById(key).orElseThrow();
    OrderDocument stale = repository.findById(key).orElseThrow();

    first.confirm();
    repository.save(first);

    stale.confirm();
    assertThrows(
        org.springframework.dao.OptimisticLockingFailureException.class,
        () -> repository.save(stale));

    assertEquals("CONFIRMED",
        repository.findById(key).orElseThrow().getStatus());
} finally {
    repository.deleteById(key);
}
~~~

`@Version` là CAS của **cùng một document**, không phải JSON body field hay version schema. CAS là token opaque: không assert nó tăng đúng 1. Để kiểm tra lost update, phải đọc lại state cuối.

### 16.2. TTL thuộc server, không thuộc đồng hồ giả

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

String key = "it::" + UUID.randomUUID() + "::cart::ttl";

collection.insert(key,
    JsonObject.create().put("purpose", "ttl-test"),
    insertOptions().expiry(Duration.ofSeconds(4)));
~~~

Dùng Awaitility hoặc polling có deadline để chờ `collection.exists(key).exists()` thành false. Đừng chờ chính xác 4.000 ms bằng sleep cứng; bucket/collection maxTTL, server clock và touch/update options có thể ảnh hưởng expiry.

**Không dùng `Clock.fixed` hoặc Reactor virtual time để tua nhanh Couchbase TTL.** Đồng hồ giả chỉ hữu ích cho business time và reactive scheduler do ứng dụng kiểm soát.

### 16.3. Dữ liệu âm tính cần độc lập

Một số JSON fixtures nên seed bằng SDK:

~~~json
{"customer_id":"customer::u100","status":null,"amount_vnd":100000}
~~~

~~~json
{"customer_id":"customer::u100","status":"DRAFT","amount_vnd":"100000"}
~~~

~~~json
{"customer_id":"customer::u100","amount_vnd":100000}
~~~

Test cần phát hiện NULL, sai kiểu string và MISSING theo **chính sách reader**. Đừng bắt chung `RuntimeException` rồi coi PASS: exception do index không tồn tại có thể làm test âm tính giả xanh.

### 16.4. Reactive fixture phải được subscribe

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(reactiveRepository.save(order))
    .assertNext(saved -> assertNotNull(saved.getId()))
    .verifyComplete();

StepVerifier.create(reactiveRepository.deleteById(order.getId()))
    .verifyComplete();
~~~

Chỉ tạo `Mono` hoặc `Flux` không bảo đảm I/O đã diễn ra. Cleanup reactive phải subscribe, và test transaction đa document cần kiểm tra atomic commit/rollback trên Couchbase thật — không suy ra từ việc server/container đã ready.

## 17. Cleanup đáng tin và quyền sở hữu tài nguyên

Một cleanup SDK theo key có thể xử lý trường hợp document đã tự hết hạn:

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;

for (String key : ownedKeys) {
    try {
        collection.remove(key);
    } catch (DocumentNotFoundException alreadyGone) {
        // TTL hoặc cleanup trước đó đã xóa đúng key.
    }
}
~~~

**Đừng nuốt mọi exception** khi cleanup: permission failure, timeout và bucket sai đều cần được ghi nhận. Nếu test dùng repository `deleteById` thì cần hiểu ngữ nghĩa khi key không tồn tại ở phiên bản Spring Data đang chạy.

| Mô hình môi trường | Cách cleanup hợp lý |
| --- | --- |
| Container riêng một test class | Xóa owned keys; container teardown dọn toàn bộ về sau |
| Bucket chung cho nhiều test classes | Chỉ xóa keys thuộc từng test |
| Named collection riêng một suite | Có thể drop collection sau khi không còn test dùng |
| Shared CI cluster | Namespace per pipeline, cleanup có owner và quyền |
| Test TTL | Cho expiry tự làm việc, cleanup còn lại và chấp nhận not-found |
| Migration test | Giữ fixtures đến khi reconciliation/rollback assertions hoàn tất |

Khi test có thông tin cá nhân giả lập, không log toàn bộ raw JSON trong CI; chỉ log synthetic key, schema/version và lỗi đã được làm sạch.

## 18. Chạy song song và Spring context cache

JUnit có thể chạy test methods/classes song song. Tránh:

~~~text
Test A seed order::1 = DRAFT
Test B update order::1 = CONFIRMED
Test C vẫn kỳ vọng order::1 = DRAFT
~~~

Thay bằng:

~~~text
Test A: it::runA::order::draft-a
Test B: it::runB::order::draft-a
Test C: it::runC::order::draft-a
~~~

**Logical ID `draft-a` giống nhau**, physical keys khác nhau. Nếu test query đếm theo customer ID, cũng cần cô lập customer hoặc collection như mục 14.

Một rủi ro khác: Spring TestContext cache `ApplicationContext`, trong khi JUnit Testcontainers extension có thể stop `static @Container` sau mỗi class. Nếu context được reuse với connection details của container đã dừng, test class kế tiếp sẽ dùng **stale port/credentials**.

Giải pháp là giữ vòng đời context và container tương thích, hoặc tách contexts khi container là resource riêng. Dùng `@DirtiesContext` có chủ đích nếu cần; không bật reusable containers trên CI mặc định rồi để dữ liệu cũ tồn tại không kiểm soát.

## 19. CI và phân loại lỗi provisioning

Một pipeline đáng tin:

~~~mermaid
flowchart LR
    A["Unit tests"] --> B["Start CouchbaseContainer"]
    B --> C["Provision scope/collection/index"]
    C --> D["Wait readiness/index ONLINE"]
    D --> E["Seed per-test data"]
    E --> F["KV/SQL++/CAS assertions"]
    F --> G["Cleanup + report"]
~~~

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Docker unavailable | Container runtime/permission | Fail integration job rõ ràng |
| Cluster timeout | Service bootstrap, RAM/CPU | Kiểm tra log/image/resource quota |
| Bucket not found | `BucketDefinition`/Spring property mismatch | Đồng nhất tên bucket |
| Scope/collection not found | Chưa provision hoặc manifest chưa usable | Create và KV probe có deadline |
| `No index available` | Thiếu index hoặc keys không phù hợp | Create index đúng, `EXPLAIN` |
| `watchIndexes` timeout | Index build/Index Service lỗi | Xem state/quota, không sleep vô hạn |
| KV thấy document, SQL++ không thấy | Index lag/scan consistency | `REQUEST_PLUS` hoặc policy phù hợp |
| COUNT khác khi chạy toàn suite | Fixture dùng chung, không cô lập query | Namespace customer/keyspace |
| CAS conflict không xuất hiện | Hai snapshots không độc lập, thiếu `@Version` | Đọc hai lần và kiểm tra state |
| Test TTL flaky | Sleep cứng hoặc expiry bị touch | Poll tới trạng thái mong đợi |
| Lỗi chỉ ở test class thứ hai | Context cache giữ container cũ | Đồng bộ lifecycle |
| Cleanup xóa lẫn nhau | `deleteAll`/trùng keys | Track owned keys |

Không xem một job integration **bị skip vì thiếu Docker** là PASS. CI phải phân biệt setup failure, test failure và skipped/no evidence.

## 20. Bài thực hành: Product và Review trong hai collections

**Bối cảnh:** ứng dụng dùng bucket `shop_it`, scope `catalog`, collections `products` và `reviews`. Product lưu thông tin danh mục; Review lưu `product_key` tham chiếu document key của Product.

~~~json
{
  "display_name": "Cà phê hạt 250 g",
  "category": "COFFEE",
  "price_vnd": 150000,
  "active": true
}
~~~

~~~json
{
  "product_key": "it::run::product::coffee250",
  "rating": 5,
  "status": "PUBLISHED",
  "created_at": "2026-01-15T09:00:00Z"
}
~~~

### 20.1. Yêu cầu

1. Tạo `catalog.products` và `catalog.reviews` có thể gọi lại an toàn.
2. Tạo `ix_reviews_product_status_time` trên `(product_key, status, created_at)` và đợi ONLINE.
3. Seed hai Product cùng bốn Review có logical IDs cố định và physical keys theo runId.
4. Dùng SDK raw JSON kiểm tra tên field do Spring Data repository ghi.
5. Query Review theo Product và status PUBLISHED; dùng consistency thích hợp và ORDER BY tường minh.
6. Test Review thiếu `status` như một fixture legacy, không coi đây là dữ liệu chuẩn.
7. Test CAS của một Product và TTL của một Review nháp trong các cases riêng.
8. Dọn keys đã tạo, không dùng `deleteAll()`/`dropCollection` trên tài nguyên dùng chung.

### 20.2. Dataset đề xuất

| Fixture | Loại | Thuộc Product | status | rating | Thời gian |
| --- | --- | --- | --- | ---: | --- |
| `coffee250` | Product | — | — | — | — |
| `tea100` | Product | — | — | — | — |
| `r1` | Review | coffee250 | PUBLISHED | 5 | 08:00 |
| `r2` | Review | coffee250 | PUBLISHED | 4 | 09:00 |
| `r3` | Review | coffee250 | HIDDEN | 2 | 10:00 |
| `r4` | Review | tea100 | PUBLISHED | 5 | 11:00 |

Query `coffee250 + PUBLISHED` trả đúng **hai Review** theo namespace của test: `r1`, rồi `r2`. Không assert tổng Review toàn collection nếu có suite khác.

~~~mermaid
flowchart TB
    A["CouchbaseContainer / shop_it"] --> B["Scope catalog"]
    B --> C["Collections products + reviews"]
    C --> D["Index reviews(product_key,status,created_at)"]
    D --> E["watchIndexes ONLINE"]
    E --> F["Seed Product + Review theo runId"]
    F --> G["SDK raw JSON + SQL++ REQUEST_PLUS"]
    G --> H["CAS / legacy / TTL cases"]
    H --> I["Cleanup owned keys"]
~~~

Couchbase không tự tạo ràng buộc foreign key giữa Review và Product. Nếu Product bị xóa, application phải có chính sách cho Review mồ côi, và test riêng cho chính sách đó.

### 20.3. Câu hỏi tự kiểm tra

1. **`withBucket` có tự tạo named scope/collection không?** Không.
2. **Khi scope đã tồn tại, có thể xử lý exception nào?** `ScopeExistsException`.
3. **Có được bắt mọi RuntimeException ở resource setup không?** Không.
4. **`ignoreIfExists` có xác minh đúng index keys không?** Không.
5. **`watchIndexes` có tạo index không?** Không, nó chờ index đã tạo.
6. **Vì sao logical IDs cố định nhưng physical keys có runId?** Để giữ expected result mà tránh collision.
7. **Vì sao seed bằng repository hữu ích?** Đi qua mapping/type metadata thật.
8. **Vì sao vẫn cần SDK raw JSON assertion?** Hai chiều Spring Data có thể cùng sai tên field.
9. **Vì sao raw SDK document thiếu `_class` có thể vắng ở derived query?** Spring Data có thể dùng type predicate.
10. **`upsert` có thể che dữ liệu cũ không?** Có, nếu ghi đè physical key không cô lập.
11. **`findById` có cần secondary index không?** Thường không, đó là KV.
12. **Query sau save không thấy data ngay nghĩa là save lỗi?** Không nhất thiết; có thể do index consistency.
13. **Vì sao phải ORDER BY có tie-breaker?** SQL++ không bảo đảm thứ tự mặc định.
14. **TTL có thể tua nhanh bằng `Clock.fixed` không?** Không.
15. **Có nên drop scope khi suite khác còn chạy?** Không.
16. **Một container đơn node có chứng minh multi-node durability không?** Không.

## 21. Checklist triển khai

- [ ] Bucket/test cluster độc lập production và image Server được pin.
- [ ] Testcontainers bật KV/QUERY/INDEX theo workload.
- [ ] Connection details đến từ container, bucket name được khai báo tường minh.
- [ ] Resource fixture tạo đúng scope và collection.
- [ ] Chỉ xử lý expected AlreadyExists; không nuốt quyền/network error.
- [ ] Khi tài nguyên tồn tại, kiểm tra cấu hình quan trọng và index definition.
- [ ] Đợi cluster/bucket, collection manifest và index ONLINE với deadline.
- [ ] Không dùng primary index để che secondary index thiếu.
- [ ] Có dataset với logical IDs/expected outputs cố định.
- [ ] Key và customer identity được namespace khi cần query isolation.
- [ ] Timestamp, status, amount cố định; random business data có seed/replay.
- [ ] `insert`, `upsert`, `save` được chọn theo semantics cần kiểm tra.
- [ ] Test Spring Data ghi → SDK raw JSON và SDK ghi → Spring Data đọc.
- [ ] Có fixture MISSING, NULL, sai kiểu, legacy/type alias khi cần.
- [ ] SQL++ query dùng consistency rõ và ORDER BY ổn định.
- [ ] Assertion COUNT chỉ trên dataset thuộc test.
- [ ] CAS test dùng hai snapshots độc lập và kiểm tra state cuối.
- [ ] TTL test dùng server expiry và polling, không ngủ cố định.
- [ ] Cleanup tracked keys ngay cả khi seed lỗi giữa chừng.
- [ ] Không xóa collection/bucket thuộc quyền dùng chung.
- [ ] Test parallel và Spring context cache không dùng stale container.
- [ ] CI báo rõ provisioning/index/timeout hoặc test bị skip.
- [ ] Không log secrets hoặc dữ liệu khách hàng thật.

## Tài liệu tham khảo chính thức

- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): CollectionManager, CollectionSpec và QueryIndexManager.
- [Couchbase Java SDK — QueryIndexManager API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/manager/query/QueryIndexManager.html): tạo, liệt kê và chờ index.
- [Couchbase Java SDK — CreateQueryIndexOptions API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/manager/query/CreateQueryIndexOptions.html): scope/collection, ignoreIfExists, deferred.
- [Couchbase Server — SQL++ CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): secondary index và key expressions.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): insert/upsert/replace/remove và CAS.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query parameters và scan consistency.
- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): Cluster/Bucket.waitUntilReady.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): CouchbaseContainer, BucketDefinition.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): container lifecycle.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): ServiceConnection và connection details.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): DataCouchbaseTest slice.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): Id, Field, Version và type metadata.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD và derived query methods.


