# Kiểm thử TTL, độ bền và độ trễ cập nhật chỉ mục trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **TTL/expiry của document**, **durability của mutation** và **độ trễ đồng bộ secondary index**: đây là ba thuộc tính độc lập, không thể kiểm chứng bằng cùng một assertion.
2. Viết integration test TTL bằng Couchbase Java SDK với `InsertOptions.expiry(Duration)`, kiểm tra metadata expiry và **poll đến khi document thực sự không còn truy cập được bằng KV**.
3. Kiểm tra chính sách TTL khi `replace`, `touch`, `getAndTouch`, `preserveExpiry` và khi bucket/collection có maxTTL; tránh nhầm “đọc document” với “gia hạn tuổi thọ”.
4. Biết cách áp dụng `@Document(expiry = ...)` hoặc `expiryExpression` trong Spring Data Couchbase và phân biệt test mapping với test TTL server.
5. Phân biệt regular writes với synchronous durable writes ở các mức `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY`, gắn yêu cầu vào replica topology và bucket type.
6. Thiết kế test xác minh **durable write đã được server acknowledge**, không ngộ nhận một container một node chứng minh failover hoặc bảo vệ dữ liệu nhiều replica.
7. Đo **KV-to-index visibility lag** và kiểm thử SQL++ với `NOT_BOUNDED`, `REQUEST_PLUS`, và `consistentWith(MutationState)` khi có mutation token.
8. Thiết kế assertion đúng cho cập nhật, xóa, expiry, index ONLINE, query scan consistency và test timeout/ambiguous outcomes.
9. Quản lý Testcontainers, scope/collection/index, dữ liệu riêng cho từng test, cleanup, CI metrics, SLO và bài tập thực hành.

Bài nằm trong chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**, tập trung xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++; đồng thời thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive bảo đảm hiệu năng, nhất quán, khả năng vận hành.

> **Hợp đồng cốt lõi:** `KV get` nhìn thấy mutation ngay sau khi được ghi **không chứng minh** secondary index đã cập nhật; `REQUEST_PLUS` chờ index **không biến một ghi thường thành durable write**; và một durable write thành công **không làm document miễn nhiễm với TTL**.

## 1. Ba trục không được đánh đồng

Giả sử ứng dụng bán hàng lưu document giỏ hàng trong Couchbase:

~~~json
{
  "cart_id": "cart::u100",
  "customer_id": "u100",
  "state": "ACTIVE",
  "amount_vnd": 250000
}
~~~

Document được đặt TTL, mutation có yêu cầu durability và có secondary index theo `customer_id`, `state` để tìm giỏ hàng đang hoạt động.

| Cơ chế | Câu hỏi nó trả lời | Nó **không** bảo đảm |
| --- | --- | --- |
| **TTL/expiry** | Document còn hợp lệ trong bao lâu theo đồng hồ Server? | Dữ liệu được ghi tới replica hoặc query index đồng bộ |
| **Durability** | Server phải xác nhận mức sao chép/lưu bền nào trước khi báo ghi thành công? | Document tồn tại vĩnh viễn hay query index đã bắt kịp |
| **Index freshness** | SQL++/Index Service đã phản ánh mutation KV nào? | Durability của ghi, deadline TTL hoặc giao dịch đa document |
| **CAS** | Mutation có được ghi dựa trên đúng version document không? | Replica durability, query scan consistency |
| **Transaction** | Nhiều mutation có cùng commit/abort đúng protocol không? | HTTP/Kafka side effects hay TTL vô hạn |

Một request ghi giỏ hàng có thể được acknowledge bền vững, sau đó document vẫn **hết hạn đúng TTL**; `findById` có thể thấy update mới trong khi `findByState` (SQL++) với consistency mặc định vẫn dùng index state cũ.

~~~mermaid
flowchart LR
    A["Application / Spring Data"] --> B["KV write with expiry + durability"]
    B --> C["Couchbase active/replica copies"]
    C --> D["KV get / exists"]
    C --> E["Index Service ingestion"]
    E --> F["SQL++ query"]
    C --> G["Server expiry / logical removal"]
    G --> E
~~~

**Couchbase physical cleanup có thể bất đồng bộ**: một document hết hạn có thể không đọc được bằng KV trước khi công việc dọn vật lý/đồng bộ index hoàn tất. Đừng viết test dựa vào thời điểm compaction dọn bytes khỏi disk.

## 2. Dựng môi trường tích hợp có thể tái lập

Các ví dụ Java chính dùng **Java 17+, Spring Boot 3.5.x, Testcontainers 1.x và Couchbase Java SDK 3.x**. Khi dự án nâng lên Spring Boot 4.x/Testcontainers 2.x, cần chọn đúng artifacts/imports theo release và dùng BOM thống nhất.

| Thành phần | Spring Boot 3.x / Testcontainers 1.x | Boot 4.x / Testcontainers 2.x |
| --- | --- | --- |
| Data starter | `spring-boot-starter-data-couchbase` | Starter data Couchbase tương ứng |
| Boot test | `spring-boot-starter-test` | `spring-boot-starter-data-couchbase-test` hoặc module test tương ứng |
| Boot Testcontainers | `spring-boot-testcontainers` | `spring-boot-testcontainers` |
| Testcontainers Couchbase | `org.testcontainers:couchbase` | `org.testcontainers:testcontainers-couchbase` |
| Testcontainers JUnit | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| `@DataCouchbaseTest` import | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Hãy pin Server image theo compatibility matrix của dự án. Ví dụ:

~~~java
DockerImageName image =
    DockerImageName.parse("couchbase/server:community-7.2.5");
~~~

Tag này chỉ là **minh họa phiên bản cố định**, không phải phiên bản bắt buộc hoặc mới nhất. Không dùng `latest` cho regression suite cần tái lập.

### 2.1. Resource model của ví dụ

~~~text
Bucket:       shop_it
Scope:        commerce
Collection:   carts
Index:        ix_carts_run_state
Index fields: test_run_id, state, customer_id
Document key: it::<runId>::cart::active-a
              it::<runId>::cart::active-b
              it::<runId>::cart::expired-c
              it::<runId>::cart::durable-d
~~~

Dùng bucket riêng `shop_it`; các keys và `test_run_id` mang `runId` của mỗi testcase, tránh query đếm lẫn dữ liệu của test khác chạy song song.

### 2.2. Container có KV, Query và Index Services

~~~java
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.utility.DockerImageName;

static final CouchbaseContainer COUCHBASE =
    new CouchbaseContainer(
        DockerImageName.parse("couchbase/server:community-7.2.5"))
        .withEnabledServices(
            CouchbaseService.KV,
            CouchbaseService.QUERY,
            CouchbaseService.INDEX)
        .withBucket(new BucketDefinition("shop_it"));
~~~

| Test | KV | QUERY | INDEX |
| --- | :---: | :---: | :---: |
| TTL bằng `get/exists` | Có | Không bắt buộc | Không bắt buộc |
| Durability trên `insert/replace` | Có | Không bắt buộc | Không bắt buộc |
| SQL++ theo JSON field | Có | Có | Có |
| Index build/wait | Có thể cần | Có | Có |
| Derived repository query | Có | Có | Có |

`withBucket` không tự tạo `commerce.carts` hoặc secondary index. Không bật Query/Index nếu suite chỉ cần KV, nhưng cũng không bỏ chúng trong test query latency.

### 2.3. Spring Boot test slice cấp connection details

~~~java
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
class CartLifetimeIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer COUCHBASE =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_it"));

    @Autowired com.couchbase.client.java.Cluster cluster;

    // @Autowired CartRepository / CouchbaseTemplate...
    // Resource fixture cần tạo commerce.carts trước test I/O.
}
~~~

`@ServiceConnection` cấu hình endpoint và credentials từ container; **bucket name vẫn cần được khai báo**. Với `@DynamicPropertySource` thay thế, đăng ký `spring.couchbase.connection-string`, `username`, `password`, `spring.data.couchbase.bucket-name` qua suppliers từ **chính container này**; không cần khai báo trùng cả hai cơ chế.

`@DataCouchbaseTest` không tự chạy Server hay provision index. Nếu application có startup bean truy cập collection trong lúc load context, setup ở `@BeforeAll` có thể quá muộn; chọn fixture/initializer thực thi trước khi bean đó cần I/O.

## 3. Provision scope, collection và index đúng keyspace

Ví dụ dùng Couchbase Java SDK 3.x:

~~~java
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;
import com.couchbase.client.java.manager.collection.CollectionSpec;

cluster.waitUntilReady(Duration.ofSeconds(60));
var bucket = cluster.bucket("shop_it");
bucket.waitUntilReady(Duration.ofSeconds(60));

var collections = bucket.collections();

try {
    collections.createScope("commerce");
} catch (ScopeExistsException alreadyExists) {
    // Setup idempotent.
}

try {
    collections.createCollection(
        CollectionSpec.create("carts", "commerce"));
} catch (CollectionExistsException alreadyExists) {
    // Collection đã tồn tại.
}
~~~

Sau `createCollection`, SDK có thể chưa nhận được collection manifest mới ngay. Dùng KV probe có deadline (ví dụ `collection.exists("it::readiness::probe")`) để biết collection usable. **Không nuốt mọi RuntimeException**; permission/quota/sai bucket phải fail fast, chỉ lỗi propagation tạm thời mới có thể retry.

### 3.1. Chỉ tạo index khi test SQL++ cần

SQL++ query dự kiến:

~~~sql
SELECT META(c).id AS documentKey,
       c.test_run_id, c.state, c.customer_id
FROM `shop_it`.`commerce`.`carts` AS c
WHERE c.test_run_id = $runId
  AND c.state = $state;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_carts_run_state
ON `shop_it`.`commerce`.`carts`(
    test_run_id, state, customer_id
);
~~~

Java SDK:

~~~java
import java.util.List;
import static com.couchbase.client.java.manager.query.CreateQueryIndexOptions.createQueryIndexOptions;
import static com.couchbase.client.java.manager.query.WatchQueryIndexesOptions.watchQueryIndexesOptions;

var indexes = cluster.queryIndexes();

indexes.createIndex(
    "shop_it",
    "ix_carts_run_state",
    List.of("test_run_id", "state", "customer_id"),
    createQueryIndexOptions()
        .scopeName("commerce")
        .collectionName("carts")
        .ignoreIfExists(true)
);

indexes.watchIndexes(
    "shop_it",
    List.of("ix_carts_run_state"),
    Duration.ofSeconds(90),
    watchQueryIndexesOptions()
        .scopeName("commerce")
        .collectionName("carts")
);
~~~

`watchIndexes` chỉ đợi index đã tạo đạt ONLINE, không tạo index. `ignoreIfExists(true)` chỉ bỏ qua tên trùng, **không xác minh index hiện hữu có đúng fields và order**. Với environment dùng chung, đối chiếu metadata qua `getAllIndexes` / `system:indexes` và `EXPLAIN` khi cần. Tránh tạo primary index để che lỗi thiếu secondary index.

### 3.2. Không nhầm index ONLINE với dữ liệu đã bắt kịp

~~~text
T0: CREATE INDEX hoàn thành
T1: watchIndexes ONLINE
T2: KV insert document
T3: Query NOT_BOUNDED ngay sau insert

Tại T3:
  Index có thể ONLINE nhưng chưa phản ánh mutation T2.
~~~

Index readiness là điều kiện **infrastructure**. Index freshness là điều kiện **data-consistency cho một request**. Cần test riêng cho cả hai.

## 4. TTL là expiry metadata của document

TTL (time to live) nói khi nào một document bị coi là hết hạn. Couchbase có thể đặt expiry:

- Theo từng `insert`, `upsert`, `replace` hoặc mutation hỗ trợ expiry options.
- Theo bucket/collection maxTTL, nếu resource được cấu hình.
- Qua Spring Data Couchbase `@Document(expiry=...)` hoặc `expiryExpression`.
- Qua các thao tác đổi expiry như `touch`, `getAndTouch`.

TTL thuộc **toàn document**, không tự biến một phần tử trong một array thành document riêng có expiry độc lập.

### 4.1. Thời điểm hết hạn và độ chính xác

Khi SDK nhận `Duration.ofSeconds(6)`, nó truyền chính sách expiry cho Server. **Không** giả định document biến mất chính xác sau 6.000 ms trên đồng hồ máy test:

- Phải tính network/clock skew và thời điểm Server nhận mutation.
- Couchbase có thể làm tròn theo đơn vị/độ phân giải của expiry.
- Khi hết hạn, đường KV có thể báo not-found trong khi dọn vật lý/secondary index diễn ra sau.
- Batch cleanup và compaction không phải điều kiện test cần đồng bộ.
- Clock giả của Java/Reactor **không tua nhanh đồng hồ Couchbase Server**.

Sử dụng `System.nanoTime()` để đo khoảng trễ từ lúc SDK trả về (monotonic clock) và poll có deadline; không dùng `LocalDateTime.now()` để chứng minh millisecond precision.

### 4.2. TTL khác CAS và độ bền

Document có TTL 6 giây và durable write MAJORITY có thể:

1. Được ghi bền vững theo cấu hình quorum.
2. Đọc lại bằng KV ngay sau khi ghi.
3. Hết hạn hợp lệ khi TTL tới.
4. Biến mất khỏi kết quả SQL++ sau khi Index Service tiếp nhận expiry.


## 5. Kiểm thử TTL thực bằng Couchbase Java SDK

Couchbase Java SDK cho phép khai báo expiry trên `insert`/`upsert` và các mutations hỗ trợ expiry.

### 5.1. Tạo document có TTL và đọc expiry metadata

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import static com.couchbase.client.java.kv.GetOptions.getOptions;
import static org.junit.jupiter.api.Assertions.*;

import com.couchbase.client.java.json.JsonObject;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

var collection = cluster.bucket("shop_it")
    .scope("commerce").collection("carts");

String key = "it::" + UUID.randomUUID() + "::cart::ttl";

collection.insert(
    key,
    JsonObject.create()
        .put("state", "ACTIVE")
        .put("amount_vnd", 250000L),
    insertOptions().expiry(Duration.ofSeconds(8))
);

var result = collection.get(key, getOptions().withExpiry(true));

assertEquals("ACTIVE",
    result.contentAsObject().getString("state"));
assertTrue(result.expiryTime().isPresent());

Instant serverExpiry = result.expiryTime().orElseThrow();

// Kiểm tra khoảng hợp lý, không suy ra expiry chính xác
// bằng thời gian hiện tại của máy test + đúng 8 giây.
assertTrue(serverExpiry.isAfter(Instant.now().minusSeconds(2)));
~~~

`GetOptions.withExpiry(true)` mới yêu cầu lấy expiry metadata; GET bình thường không cần kèm expiry. `GetResult.expiryTime()` là `Optional<Instant>`. Một JSON field như `expires_at` của ứng dụng **không phải** expiry metadata do Server áp dụng.

### 5.2. Đợi hết hạn bằng điều kiện thật, không sleep cố định

~~~java
import static org.awaitility.Awaitility.await;

await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(200))
    .until(() -> !collection.exists(key).exists());

assertFalse(collection.exists(key).exists());
~~~

Một test tốt dùng TTL đủ dài để document còn tồn tại ngay sau create, rồi dùng deadline dài hơn TTL cho việc quan sát. `Thread.sleep(8000)` rồi assert một lần có thể flaky khi CI bị chậm; `Clock.fixed`/Reactor virtual time không tua nhanh server clock.

### 5.3. Test hoàn chỉnh với cleanup

~~~java
@Test
void expiresDocumentAccordingToServerTtl() {
    String key = "it::" + UUID.randomUUID() + "::cart::ttl";

    try {
        collection.insert(key,
            JsonObject.create().put("state", "ACTIVE"),
            insertOptions().expiry(Duration.ofSeconds(8)));

        assertTrue(collection.exists(key).exists());

        var current = collection.get(
            key, getOptions().withExpiry(true));
        assertTrue(current.expiryTime().isPresent());

        await().atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .until(() -> !collection.exists(key).exists());

        assertFalse(collection.exists(key).exists());
    } finally {
        if (collection.exists(key).exists()) {
            collection.remove(key);
        }
    }
}
~~~

Nếu document hết hạn giữa `exists` và `remove`, `DocumentNotFoundException` có thể xảy ra. Cleanup fixture nên xử lý trường hợp not-found dự kiến và vẫn báo các lỗi thực (authorization/network). Không gọi `deleteAll()` trong collection được nhiều tests chia sẻ.

### 5.4. Không chờ physical compaction

Khi KV `exists(key)` trả `false` sau expiry, test đã xác minh document **không còn truy cập được theo KV contract**. Không cần kiểm tra file trên disk hoặc tombstone/metadata đã bị dọn tức thì. Nếu cần kiểm tra kết quả SQL++ không chứa expired document, đó là **test index visibility riêng**.

## 6. Kiểm thử TTL khi cập nhật hoặc gia hạn document

Lỗi phổ biến là một application dùng `replace` để sửa trạng thái session, vô tình thay đổi expiry deadline. Hoặc handler gọi `getAndTouch` dù nghiệp vụ cần fixed deadline.

### 6.1. Giữ expiry gốc bằng preserveExpiry

~~~java
import static com.couchbase.client.java.kv.GetOptions.getOptions;
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

String key = "it::" + UUID.randomUUID() + "::cart::preserve";
var collection = cluster.bucket("shop_it")
    .scope("commerce").collection("carts");

try {
    collection.insert(key,
        JsonObject.create().put("state", "ACTIVE"),
        insertOptions().expiry(Duration.ofSeconds(20)));

    Instant before = collection.get(
        key, getOptions().withExpiry(true))
        .expiryTime().orElseThrow();

    collection.replace(key,
        JsonObject.create().put("state", "CHECKED"),
        replaceOptions().preserveExpiry(true));

    Instant after = collection.get(
        key, getOptions().withExpiry(true))
        .expiryTime().orElseThrow();

    assertTrue(Math.abs(
        Duration.between(before, after).toMillis()) <= 2000);
} finally {
    if (collection.exists(key).exists()) {
        collection.remove(key);
    }
}
~~~

`preserveExpiry(true)` yêu cầu Server **giữ expiry hiện tại**, không gia hạn deadline. So thời điểm trước/sau trong một khoảng sai số phù hợp, không lấy `get` của SDK rồi giả định đọc sẽ tự gia hạn thời gian sống.

### 6.2. Sliding expiration cần getAndTouch hoặc touch

~~~java
var touched = collection.getAndTouch(
    key, Duration.ofSeconds(30));
~~~

`getAndTouch` đồng thời lấy body và thay đổi thời hạn sống. Với session có **sliding expiration**, đây có thể là hành vi đúng. Với OTP hoặc đường link mời có **fixed deadline**, đây có thể là lỗi security/domain vì mỗi lần kiểm tra lại kéo dài hiệu lực.

### 6.3. Ma trận thay đổi TTL

| Thao tác | Mục tiêu | Điều test cần kiểm chứng |
| --- | --- | --- |
| Insert với `expiry` | Đặt deadline lần đầu | Metadata có expiry; KV cuối cùng not-found |
| GET thường | Chỉ đọc | Không tự kéo dài deadline |
| Replace + `preserveExpiry(true)` | Sửa body, giữ deadline | Expiry trước/sau tương đương |
| Replace không preserve | Theo policy/options, có thể reset expiry | Test chính đường code production |
| `getAndTouch` / `touch` | Gia hạn TTL | Deadline mới muộn hơn |
| Remove | Xóa chủ động | Key không còn |
| maxTTL của resource | Ràng buộc TTL hiệu lực | Deadline tuân resource policy |

**Một TTL test chỉ kiểm tra expiration sau insert chưa bắt được bug update làm reset TTL.** Hãy có test riêng cho mỗi đường ghi quan trọng.

## 7. Bucket/collection maxTTL và thời gian tương đối/tuyệt đối

Bucket và collection có thể có **maxTTL**. Nếu Server có giới hạn này, expiry SDK truyền vào **không được tự coi là effective TTL**. Ví dụ ứng dụng muốn 30 phút nhưng collection giới hạn 10 phút, test phải đối chiếu **metadata thực** với policy của resource.

### 7.1. Kiểm tra policy thực thay vì đoán

1. Provision bucket/collection với TTL settings dự kiến.
2. Kiểm tra cấu hình tài nguyên nếu test dựa vào maxTTL.
3. Insert document với expiry.
4. Dùng `withExpiry(true)` đọc expiry metadata.
5. Assert deadline hiệu lực theo resource policy.
6. Poll KV tới lúc document không còn tồn tại.

Tránh dùng cluster staging/production sẵn có với maxTTL khác nhau để tạo “fixture chuẩn”. Một test PASS trên machine A có thể FAIL trên CI nếu resource settings không đồng nhất.

### 7.2. Duration và Instant

~~~java
// Relative expiry:
insertOptions().expiry(Duration.ofMinutes(10));

// Absolute expiry:
insertOptions().expiry(Instant.now().plusSeconds(600));
~~~

SDK hiện đại hỗ trợ `Duration` trong giới hạn được tài liệu hóa (thường dưới 50 năm) và `Instant` cho một thời điểm tuyệt đối. Không tự dùng quy tắc legacy “trên 30 ngày là Unix timestamp” để chuyển đổi số nguyên nếu SDK đang nhận `Duration` và `Instant`.

### 7.3. Server clock và độ chính xác

Đoạn `Duration.ofSeconds(8)` mô tả thời hạn do Server quản lý. Thời điểm quan sát thay đổi vì network, scheduler, độ phân giải expiry và thời gian gọi test. `System.nanoTime()` phù hợp đo elapsed time trong JVM; không dùng `LocalDateTime.now()` làm mốc chính xác millisecond cho Server TTL.


## 8. TTL với Spring Data Couchbase entity

Spring Data Couchbase hỗ trợ expiry thông qua mapping metadata của `@Document`. Đây là **tầng cấu hình application**, khác với trực tiếp truyền `InsertOptions.expiry` trong Java SDK.

### 8.1. @Document(expiry = N)

~~~java
package com.example.shop.commerce;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Field;

@Document(expiry = 10)
@Scope("commerce")
@Collection("carts")
public class TemporaryCart {
    @Id
    private String id;

    @Version
    private Long cas;

    @Field("customer_id")
    private String customerId;

    @Field
    private String state;

    protected TemporaryCart() {}

    public TemporaryCart(String id, String customerId) {
        this.id = id;
        this.customerId = customerId;
        this.state = "ACTIVE";
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getCustomerId() { return customerId; }
    public String getState() { return state; }
}
~~~

`@Document(expiry = 10)` khai báo thời hạn sống 10 giây theo Spring Data mapping. `@Version Long` thể hiện CAS metadata; không đồng nhất CAS với TTL hay `schema_version`.

### 8.2. Repository test: ghi qua Spring Data, đọc expiry bằng SDK

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

interface TemporaryCartRepository
        extends CouchbaseRepository<TemporaryCart, String> {}

@Test
void springDataDocumentExpiryReachesTheServer() {
    String key = "it::" + UUID.randomUUID() + "::cart::spring-ttl";

    var collection = cluster.bucket("shop_it")
        .scope("commerce").collection("carts");

    try {
        temporaryCarts.save(
            new TemporaryCart(key, "customer::u100"));

        var result = collection.get(
            key, getOptions().withExpiry(true));

        assertEquals("ACTIVE",
            result.contentAsObject().getString("state"));
        assertEquals("customer::u100",
            result.contentAsObject().getString("customer_id"));
        assertTrue(result.expiryTime().isPresent());

        await().atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(250))
            .until(() -> temporaryCarts.findById(key).isEmpty());
    } finally {
        if (temporaryCarts.existsById(key)) {
            temporaryCarts.deleteById(key);
        }
    }
}
~~~

Đây là integration test **mapping Spring Data → Couchbase Server**. Nó không tự chứng minh `Repository.findByCustomerId` SQL++ đã xóa index entry sau expiry; cần test query index riêng.

### 8.3. expiryExpression đến từ Spring properties

~~~java
@Document(expiryExpression = "${shop.cart.expiry-seconds}")
@Scope("commerce")
@Collection("carts")
public class ConfiguredCart {
    @Id String id;
    // ...
}
~~~

Ví dụ property cấu hình test:

~~~properties
shop.cart.expiry-seconds=10
~~~

`expiryExpression` dùng placeholder property sources; cần đọc theo Spring Data version mà dự án đang dùng. Nếu thay giá trị test giữa hai contexts, không tự giả định một `ApplicationContext` đang cache sẽ hot-reload mọi mapping metadata. Hãy dùng context riêng hoặc cách inject TTL runtime minh bạch.

### 8.4. Expiry lúc save/update cần test theo đường thực

Nếu repository save lại entity `TemporaryCart`, Spring Data có thể áp dụng expiry mapping cho mutation mới. Với **fixed original deadline**, cần xác minh ứng dụng không làm reset TTL khi cập nhật giỏ hàng. Test `@Document(expiry=10)` và SDK `replaceOptions().preserveExpiry(true)` là hai hợp đồng khác nhau; không thay thế nhau.

### 8.5. @Document durabilityLevel là cấu hình khác

Trong Spring Data Couchbase release hỗ trợ, `@Document` còn có `durabilityLevel`/`durabilityExpression`. Ví dụ:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;

@Document(
    expiry = 10,
    durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("commerce")
@Collection("carts")
public class DurableTemporaryCart {
    @Id private String id;
    // ...
}
~~~

Nhưng test annotation này phải kiểm tra **effective durability và topology**, không chỉ đọc lại JSON qua repository. TTL vẫn khiến document hết hạn theo deadline ngay cả khi write yêu cầu mức durability mạnh.

## 9. Durable writes: điều gì phải được acknowledge trước khi báo success?

Một regular KV write thường được acknowledge khi active node nhận và giữ mutation trong memory; từ đó Couchbase tiếp tục replicate/persist không đồng bộ. Synchronous durable write yêu cầu Server đạt một **durability level** cụ thể trước khi acknowledge.

| Level | Điều kiện chính | Đánh đổi |
| --- | --- | --- |
| Regular / không yêu cầu durability | Active node đã nhận mutation | Latency thấp nhưng không có quorum guarantee |
| `MAJORITY` | Phần lớn copies theo bucket replica topology đã nhận vào memory | Thường tăng latency so với regular |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Majority memory + active node đã flush đồng bộ xuống disk | Latency disk của active |
| `PERSIST_TO_MAJORITY` | Majority đã persist/sync xuống disk | Điều kiện mạnh nhất trong ba mức |
 
`MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` yêu cầu bucket hỗ trợ disk persistence (không dùng cho Ephemeral bucket không có disk persistence). Nếu bucket-level min durability và SDK option khác nhau, Server áp dụng mức **mạnh hơn**, không nhất thiết mức caller truyền vào là effective requirement.

### 9.1. Replica count quyết định majority

| Bucket replicas | Number of copies | Majority cần |
| --- | ---: | ---: |
| 0 | 1 active | 1 Data node |
| 1 | 1 active + 1 replica | 2 Data nodes |
| 2 | 1 active + 2 replicas | 2 Data nodes |
| 3+ | Không hỗ trợ synchronous durability với cấu hình này | — |

Với Testcontainers **một Data node**, bucket `numReplicas=0` mới có thể đáp ứng Majority trên chính node đó. Nếu để 1 replica mà không có node thứ hai, durable writes có thể gặp `DurabilityImpossibleException`.

**Quan trọng:** Majority trên một node/zero replicas **không chứng minh** mutation được replicate sang node khác. Nó chỉ chứng minh Server đã acknowledge theo điều kiện mà topology đơn node cho phép.

### 9.2. Đọc lại bucket settings trước khi test

~~~java
int replicas = cluster.buckets()
    .getBucket("shop_it").numReplicas();

assertEquals(0, replicas,
    "Single-node test bucket phải có 0 replicas " +
    "để kiểm thử durable write khả thi");
~~~

Đây là một guard trong **single-node fixture**, không phải quy tắc cho production. Production có 1–2 replicas và đủ Data nodes để đạt quorum; muốn test failover/persistence thực cần mô hình nhiều nodes.

### 9.3. Durability không thay CAS hoặc multi-document transaction

Một mutation có `DurabilityLevel.MAJORITY` không tự so expected CAS. Nếu hai writers đọc cùng một document rồi `upsert` dựa trên stale data, durability chỉ xác nhận **mỗi write** đạt mức yêu cầu, không ngăn lost update.

Tương tự, hai durable writes trên hai keys được gọi lần lượt **không biến thành một transaction atomic**. Với workflow phải commit/abort nhiều document, dùng Couchbase Transactions hoặc cơ chế đồng nhất khác và test riêng.

## 10. Ghi durable bằng SDK và kiểm chứng kết quả

SDK Java hỗ trợ durability trên mutation options:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;

MutationResult inserted = collection.insert(
    "it::durable::example",
    JsonObject.create().put("state", "CONFIRMED"),
    insertOptions().durability(DurabilityLevel.MAJORITY)
);

assertNotEquals(0L, inserted.cas());
~~~

Thực tế nên dùng key `UUID` và cleanup, không hardcode key trên collection chia sẻ. `MutationResult.cas()` là CAS token phản ánh version mới, **không phải bằng chứng số copies đã được ghi**. Server acknowledge thành công theo durability requirements của mutation/bucket mới là bằng chứng một durable write request đã hoàn thành.

### 10.1. Integration test độc lập cho Majority

~~~java
@Test
void acknowledgesMajorityDurableWrite() {
    String key = "it::" + UUID.randomUUID() + "::cart::durable";

    var collection = cluster.bucket("shop_it")
        .scope("commerce").collection("carts");

    try {
        int replicas = cluster.buckets()
            .getBucket("shop_it").numReplicas();
        assertEquals(0, replicas);

        MutationResult result = collection.insert(
            key,
            JsonObject.create()
                .put("state", "CONFIRMED")
                .put("amount_vnd", 500000L),
            insertOptions()
                .durability(DurabilityLevel.MAJORITY)
        );

        assertNotEquals(0L, result.cas());

        // KV read xác minh body/mutation thực.
        var stored = collection.get(key).contentAsObject();
        assertEquals("CONFIRMED", stored.getString("state"));
        assertEquals(500000L, stored.getLong("amount_vnd"));
    } finally {
        if (collection.exists(key).exists()) {
            collection.remove(key);
        }
    }
}
~~~

Test này chứng minh **durable insert với Majority đã được Server của fixture chấp nhận**, và body được ghi đúng. Test **không** chứng minh sẽ sống sót nếu node này bị mất và cả disk không thể phục hồi.

### 10.2. Thử từng durability level theo bucket type

~~~java
var regular = collection.upsert(
    keyA, JsonObject.create().put("level", "regular"));

var majority = collection.upsert(
    keyB, JsonObject.create().put("level", "majority"),
    upsertOptions().durability(DurabilityLevel.MAJORITY));

var persistedActive = collection.upsert(
    keyC, JsonObject.create().put("level", "active-disk"),
    upsertOptions().durability(
        DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE));

var persistedMajority = collection.upsert(
    keyD, JsonObject.create().put("level", "majority-disk"),
    upsertOptions().durability(
        DurabilityLevel.PERSIST_TO_MAJORITY));
~~~

Đây là **minh họa**: test phải tự tạo 4 keys có namespace riêng, bảo đảm Couchbase (non-Ephemeral) bucket và topology đủ điều kiện, cleanup sau khi đã xác minh. Nếu resource là Ephemeral bucket, không chạy các mức đòi persistence to disk.

### 10.3. Không assert mọi lần ghi bền vững đều chậm hơn regular

Durable writes thường tốn thêm latency cho replication/persistence, nhưng một lần chạy riêng lẻ có thể bị nhiễu bởi network, disk/cache và scheduler. Không nên:

~~~java
assertTrue(durableLatencyNanos > regularLatencyNanos);
~~~

cho từng cặp mutations độc lập. Muốn đo throughput hoặc p95/p99, cần warmup, nhiều lần lặp, data isolation, cùng workload và cluster topology đại diện; xem phần đo ở cuối bài.

## 11. Failure và ambiguous outcome của durable mutation

Durable write có thể gặp:

- **Durability impossible**: cấu hình replica/topology không thể đạt quorum.
- **Sync write in progress**: document đang có pending synchronous write; mutation cạnh tranh phải được xử lý theo SDK retry/error policy.
- **Timeout/ambiguous outcome**: client không có đủ bằng chứng write đã commit hay chưa.
- **Authentication/RBAC hoặc bucket lỗi**: vấn đề cấu hình, không phải contention.
- **CAS mismatch**: khi mutation dùng CAS condition; đây là một loại lỗi khác durability.

### 11.1. Tại sao không retry mù khi ambiguous?

~~~text
Client gửi INSERT/UPSERT yêu cầu Majority.
Server có thể đã commit mutation.
Response bị mất hoặc timeout ở client.
Client không biết mutation đã commit hay chưa.
~~~

Nếu request mang nghiệp vụ như trừ tồn kho, tự phát lệnh lần nữa có thể tạo duplicate side effect. Dùng **idempotency key**, đọc/reconcile state và phân loại outcome theo SDK exception. Với `insert` có document key cố định theo operation ID, duplicate key có thể giúp nhận biết khả năng đã ghi; nhưng vẫn phải kiểm tra **payload và trạng thái** để không coi một key trùng ngẫu nhiên là success.

### 11.2. Test âm tính durability cần môi trường riêng

Nếu cố tình provision single-node bucket có một replica để test `DurabilityImpossible`, đó là một **negative topology test**, không dùng chung với các test cần durable writes thành công. Hãy chạy ở fixture riêng rồi assert đúng exception class/cause và kiểm tra state theo outcome được SDK xác nhận.

**Đừng chủ động stop container giữa mutation rồi assert “dữ liệu chắc chắn rollback”**: khi network đứt, kết quả có thể ambiguous; test sẽ không xác định được điều kiện đúng nếu không có fault-injection harness, operation marker và quá trình reconcile.

### 11.3. Không xem read-back là bằng chứng durability độc lập


## 12. Vì sao secondary index có thể chậm hơn KV?

Couchbase KV xác nhận mutation ở Data Service, còn secondary index cho SQL++ được cập nhật thông qua pipeline ingestion của Index Service. Khi KV ghi thành công, index **có thể chưa chứa phiên bản mới**.

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant KV as KV Service
    participant IX as Index Service
    participant Q as Query Service
    T->>KV: INSERT state=ACTIVE
    KV-->>T: success + CAS + mutation token (nếu có)
    Note over KV,IX: Index ingestion bất đồng bộ
    T->>Q: Query NOT_BOUNDED
    Q->>IX: Scan index hiện có
    IX-->>Q: Có thể chưa thấy mutation
    T->>Q: Query REQUEST_PLUS / consistentWith
    Q->>IX: Chờ index bắt kịp theo yêu cầu
    Q-->>T: Kết quả theo consistency đã chọn
~~~

Index lag không có hằng số cố định; nó chịu tác động từ load, nhiều partitions/vBuckets, kích thước dữ liệu, disk/network, Index Service CPU, index build và truy vấn đồng thời.

### 12.1. Ba cách đọc chỉ mục

| Cơ chế | Ngữ nghĩa | Khi nên kiểm thử |
| --- | --- | --- |
| `NOT_BOUNDED` (mặc định) | Dùng index state hiện có, không đợi mutation mới | Eventual visibility, benchmark lag |
| `REQUEST_PLUS` | Chờ index bắt kịp mức scan consistency của request | Read-after-write trên SQL++ |
| `consistentWith(MutationState)` | Chờ những mutation tokens cụ thể | Read-your-own-writes cho request vừa ghi |

`REQUEST_PLUS` và `consistentWith` có thể tăng query latency, nhưng **không** làm mutation durable hơn hay tăng TTL.

### 12.2. Index ONLINE khác index freshness

`watchIndexes` xác nhận index đã được build và ONLINE. Sau đó mỗi KV mutation mới vẫn có thể chưa kịp ingest. Test cần xác minh **hai điều kiện**: index sẵn sàng trước khi chạy và index theo kịp những mutation mà query đòi hỏi.

### 12.3. Query mẫu có parameters

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

String selectByRunAndState = """
    SELECT META(c).id AS documentKey
    FROM `shop_it`.`commerce`.`carts` AS c
    WHERE c.test_run_id = $runId
      AND c.state = $state
    ORDER BY META(c).id
    """;

var result = cluster.query(
    selectByRunAndState,
    queryOptions()
        .parameters(JsonObject.create()
            .put("runId", runId)
            .put("state", "ACTIVE"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

`test_run_id` chứa giá trị chỉ thuộc testcase này; không đếm toàn collection rồi nhận nhầm document còn sót từ test khác. Query dùng tên JSON fields thực, không dùng Java camelCase nếu đang viết SQL++ raw.

## 13. Test REQUEST_PLUS đọc mutation vừa tạo

~~~java
@Test
void requestPlusReturnsJustInsertedKey() {
    String runId = UUID.randomUUID().toString();
    String key = "it::" + runId + "::cart::active";

    var collection = cluster.bucket("shop_it")
        .scope("commerce").collection("carts");

    try {
        collection.insert(key,
            JsonObject.create()
                .put("test_run_id", runId)
                .put("state", "ACTIVE")
                .put("customer_id", "customer::u100"));

        var rows = cluster.query(
            selectByRunAndState,
            queryOptions()
                .parameters(JsonObject.create()
                    .put("runId", runId)
                    .put("state", "ACTIVE"))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        ).rowsAsObject();

        assertEquals(1, rows.size());
        assertEquals(key, rows.get(0).getString("documentKey"));
    } finally {
        if (collection.exists(key).exists()) {
            collection.remove(key);
        }
    }
}
~~~

Đây là test **SQL++ consistency**. Điều kiện cần có: Query/Index Services bật, index phù hợp được tạo và ONLINE. Nếu query báo `No index available`, sửa index/provisioning thay vì tăng thời gian sleep.

Nếu query được viết qua derived Spring Data repository, có thể dùng `@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)` trên method đó. Tuy nhiên entity query có thể thêm type filter `_class`; seed raw SDK JSON thiếu type metadata có thể không trả cùng kết quả như repository. Hãy seed bằng repository khi đang test chính derived method, và dùng SDK raw query khi đang đo index ingestion.

## 14. AT_PLUS: chỉ đợi mutations đã biết

Với read-your-own-writes theo một mutation cụ thể, SDK hỗ trợ `QueryOptions.consistentWith(MutationState)`.

~~~java
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.kv.MutationResult;

MutationResult write = collection.upsert(
    key, JsonObject.create()
        .put("test_run_id", runId)
        .put("state", "ACTIVE")
        .put("customer_id", "customer::u100"));

var token = write.mutationToken().orElseThrow(
    () -> new IllegalStateException(
        "Mutation token không khả dụng với fixture này"));

MutationState state = MutationState.from(token);

var rows = cluster.query(
    selectByRunAndState,
    queryOptions()
        .parameters(JsonObject.create()
            .put("runId", runId)
            .put("state", "ACTIVE"))
        .consistentWith(state)
).rowsAsObject();

assertEquals(1, rows.size());
assertEquals(key, rows.get(0).getString("documentKey"));
~~~

Mutation token là metadata SDK/Server trả về khi hỗ trợ. Không âm thầm dùng `NOT_BOUNDED` nếu token vắng mà testcase đang yêu cầu consistency cụ thể. Với nhiều mutations thuộc các vBuckets khác nhau, phải tổng hợp **tất cả tokens liên quan** bằng API `MutationState` đúng version.

**Không truyền mâu thuẫn cả `scanConsistency(REQUEST_PLUS)` và `consistentWith(state)` vào cùng một query.** Chọn một chiến lược cho từng testcase; chúng có phạm vi chờ khác nhau.

## 15. Đo index visibility lag không áp đặt rằng lần query đầu phải thiếu

Nếu muốn biết sau bao lâu NOT_BOUNDED query nhìn thấy mutation:

~~~text
tWriteAck = nanoTime ngay sau khi KV INSERT thành công
tVisible = nanoTime tại lần đầu NOT_BOUNDED query chứa key
Observed lag = tVisible - tWriteAck
~~~

Thời gian quan sát còn gồm chi phí query/network và khoảng cách polling, không phải chỉ thời gian xử lý nội bộ Index Service.

### 15.1. Poll tới khi NOT_BOUNDED nhìn thấy key

~~~java
@Test
void eventuallyIndexesWriteWithoutRequestPlus() {
    String runId = UUID.randomUUID().toString();
    String key = "it::" + runId + "::cart::index-lag";

    var collection = cluster.bucket("shop_it")
        .scope("commerce").collection("carts");

    try {
        collection.insert(key,
            JsonObject.create()
                .put("test_run_id", runId)
                .put("state", "ACTIVE")
                .put("customer_id", "customer::u100"));

        long writeAckNanos = System.nanoTime();

        await()
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .until(() -> cluster.query(
                selectByRunAndState,
                queryOptions()
                    .parameters(JsonObject.create()
                        .put("runId", runId)
                        .put("state", "ACTIVE"))
                    .scanConsistency(
                        QueryScanConsistency.NOT_BOUNDED)
            ).rowsAsObject().stream().anyMatch(row ->
                key.equals(row.getString("documentKey"))));

        long observedLagMs = Duration.ofNanos(
            System.nanoTime() - writeAckNanos).toMillis();

        System.out.println(
            "Observed index visibility lag (ms): " + observedLagMs);
    } finally {
        if (collection.exists(key).exists()) {
            collection.remove(key);
        }
    }
}
~~~

**Không assert query `NOT_BOUNDED` đầu tiên phải trả rỗng.** Khi Server ít tải, Index Service có thể bắt kịp trước lần query đầu. Cả hai kết quả “thấy ngay” và “thấy sau” đều phù hợp eventual consistency. Test nên dùng deadline hữu hạn, ghi measurement và phân tích lúc vượt SLO.

### 15.2. Vì sao số đo chỉ là xấp xỉ?

Nếu poll mỗi 200ms, latency quan sát có độ phân giải thô; query latency, JVM scheduler và network cũng cộng vào. Muốn đo phân vị:

- Warm up SDK/query path và tránh tính index creation vào lag.
- Seed hàng trăm mutations có keys/runIds riêng.
- Đo từng KV ack → first query visibility với monotonic clock.
- Ghi N, min/p50/p95/p99/max, interval và concurrency.
- Tránh test suite khác ghi vào cùng keyspace khi benchmark.
- Theo dõi CPU/RAM/disk/index backlog và DCP ingestion.
- Tách `request_plus_query_latency` khỏi `not_bounded_first_visibility`.
- Đừng áp một ngưỡng millisecond cứng cho laptop/CI có tài nguyên không ổn định.

`REQUEST_PLUS` có thể phản hồi chậm vì query phải chờ index và thực thi plan. Độ trễ của một REQUEST_PLUS query không bằng chính xác index lag.

## 16. Test UPDATE và DELETE phải kiểm tra cả entry cũ và entry mới

### 16.1. UPDATE ACTIVE → CHECKED_OUT

~~~java
@Test
void requestPlusReflectsIndexedFieldChange() {
    String runId = UUID.randomUUID().toString();
    String key = "it::" + runId + "::cart::updated";
    var collection = cluster.bucket("shop_it")
        .scope("commerce").collection("carts");

    try {
        collection.insert(key, JsonObject.create()
            .put("test_run_id", runId)
            .put("state", "ACTIVE")
            .put("customer_id", "customer::u100"));

        collection.upsert(key, JsonObject.create()
            .put("test_run_id", runId)
            .put("state", "CHECKED_OUT")
            .put("customer_id", "customer::u100"));

        var active = cluster.query(selectByRunAndState,
            queryOptions()
                .parameters(JsonObject.create()
                    .put("runId", runId)
                    .put("state", "ACTIVE"))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        ).rowsAsObject();

        var checkedOut = cluster.query(selectByRunAndState,
            queryOptions()
                .parameters(JsonObject.create()
                    .put("runId", runId)
                    .put("state", "CHECKED_OUT"))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        ).rowsAsObject();

        assertTrue(active.isEmpty());
        assertEquals(1, checkedOut.size());
        assertEquals(key,
            checkedOut.get(0).getString("documentKey"));
    } finally {
        if (collection.exists(key).exists()) collection.remove(key);
    }
}
~~~

**Kiểm tra cả status cũ không còn và status mới xuất hiện**. Không kết luận update-index correctness chỉ vì repository `findById` theo key trả body mới.

### 16.2. DELETE và index removal

~~~java
collection.remove(key);
assertFalse(collection.exists(key).exists());

await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(250))
    .until(() -> cluster.query(
        selectByRunAndState,
        queryOptions()
            .parameters(JsonObject.create()
                .put("runId", runId)
                .put("state", "ACTIVE"))
            .scanConsistency(QueryScanConsistency.NOT_BOUNDED)
    ).rowsAsObject().isEmpty());
~~~

Đây là test **secondary index removal latency** sau KV delete; query vẫn cần runId cô lập. Đừng nhầm kết quả rỗng trước khi đã seed/verify key có trong index với việc index thật sự xử lý delete; nên kiểm tra baseline index visibility **trước remove**.

### 16.3. TTL expiry và index removal có hai mốc riêng

~~~text
T0: Insert với TTL 8 giây
T1: KV exists(key) == true
T2: TTL đến hạn, KV exists(key) == false
T3: Index Service nhận xử lý expiry/removal
T4: NOT_BOUNDED query không trả key nữa
~~~


## 17. Ma trận kiểm thử kết hợp ba cơ chế

TTL, durability và index consistency nên có **test chuyên biệt** trước khi ghép thành end-to-end scenario.

| Case | Ghi KV | TTL | SQL++ | Điều assert |
| --- | --- | --- | --- | --- |
| A. TTL cơ bản | Insert thường | 8s | Không cần | Exists true ngay sau ghi, sau đó false trong deadline |
| B. Giữ expiry | Replace + preserveExpiry | 20s ban đầu | Không cần | Expiry deadline không bị reset |
| C. Sliding TTL | getAndTouch | Gia hạn | Không cần | Expiry mới sau thao tác |
| D. Majority | Insert durable | 0 hoặc theo policy | Không cần | Durable write acknowledged; body đúng |
| E. Index eventual | Insert thường | Không | NOT_BOUNDED | Cuối cùng trả đúng key trong deadline |
| F. Read-after-write | Insert thường | Không | REQUEST_PLUS | Trả đúng key ngay trong consistent query |
| G. AT_PLUS | Insert trả mutation token | Không | consistentWith | Query chứa mutation cụ thể |
| H. Field update | Upsert | Không | REQUEST_PLUS | Old filter vắng, new filter xuất hiện |
| I. Delete | KV remove | Không | NOT_BOUNDED polling | Cuối cùng không còn key trong kết quả |
| J. TTL + SQL++ | Insert có TTL | 8s | Query | KV hết hạn và query sau cùng không trả key |
| K. TTL + durable | Insert durable | 8s | Không cần | Acknowledged durable write vẫn có thể expire |

**Tách test case A–I thành các phép thử độc lập** để chẩn đoán rõ. Case J/K dùng integration scenario kết hợp nhưng không được thay thế A–I: nếu J FAIL, cần biết lỗi nằm ở clock/TTL, index hay durability.

### 17.1. Một kịch bản end-to-end có TTL và durability

~~~java
@Test
void durableCartStillExpiresAndIsQueryableBeforeExpiry() {
    String runId = UUID.randomUUID().toString();
    String key = "it::" + runId + "::cart::combined";

    var collection = cluster.bucket("shop_it")
        .scope("commerce").collection("carts");

    try {
        MutationResult mutation = collection.insert(
            key,
            JsonObject.create()
                .put("test_run_id", runId)
                .put("state", "ACTIVE")
                .put("customer_id", "customer::u100"),
            insertOptions()
                .durability(DurabilityLevel.MAJORITY)
                .expiry(Duration.ofSeconds(15))
        );

        assertNotEquals(0L, mutation.cas());

        var visible = cluster.query(
            selectByRunAndState,
            queryOptions()
                .parameters(JsonObject.create()
                    .put("runId", runId)
                    .put("state", "ACTIVE"))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        ).rowsAsObject();

        assertEquals(1, visible.size());
        assertEquals(key,
            visible.get(0).getString("documentKey"));

        await().atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(250))
            .until(() -> !collection.exists(key).exists());

        assertFalse(collection.exists(key).exists());
    } finally {
        if (collection.exists(key).exists()) {
            collection.remove(key);
        }
    }
}
~~~

**Điều test chứng minh:**

- SDK đã yêu cầu Majority durability; fixture topology phải hỗ trợ.
- Server acknowledge mutation và lưu document có TTL.
- SQL++ REQUEST_PLUS trả đúng document trước expiry (khi query kịp chạy).
- Document hết hạn và không còn được KV truy cập.

**Điều test chưa chứng minh:** replica failover; disk persistence trên hai nodes; độ trễ ingestion p99; physical deletion của index entry; outbox/transaction consistency. Nếu CI rất chậm, TTL 15s có thể hết trước query, vì vậy test kết hợp cần thời gian expiry đủ rộng hoặc tách khẳng định từng trục để tránh false failure.

### 17.2. Phân biệt contract “document không còn trong query”

Một query không trả expired document **không tự chứng minh index entry đã được dọn vật lý**: Query Service có thể fetch/filter dữ liệu và không trả body đã expire dù quá trình index cleanup còn pending. Cần metric/diagnostics Index Service nếu muốn đo **nội bộ index tombstone processing latency**.

Do đó:

- Test API: “KV expired và SQL++ cuối cùng không trả document” là một hợp đồng hữu ích.
- Đo `index ingestion/removal latency` thực sự: dùng công cụ Index Service/telemetry phù hợp, không chỉ quan sát rows rỗng.
- Không suy từ `REQUEST_PLUS` rằng expiration lifecycle/physical cleanup đã hoàn tất ở một mốc millisecond chính xác.

## 18. Các lỗi thường gặp và cách phân loại

| Triệu chứng | Lớp lỗi khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Document hết hạn ngay sau insert | TTL quá ngắn, maxTTL hoặc sai thời gian tuyệt đối | `withExpiry(true)` và policy |
| Document không hết hạn | TTL không được set, update reset expiry, maxTTL/config sai | SDK metadata và mutation path |
| TTL test lúc PASS lúc FAIL | Sleep cố định, timeout sát deadline | Poll có điều kiện và dư thời gian |
| GET success nhưng SQL++ thiếu document | Index lag, type filter, sai keyspace | REQUEST_PLUS, `EXPLAIN` |
| SQL++ luôn lỗi no index | Chưa tạo index/Index Service tắt | Provision/watchIndexes |
| Query NOT_BOUNDED luôn thấy ngay | Index Service bắt kịp nhanh | Đây là kết quả hợp lệ, không ép miss |
| Index name có nhưng query scan sai | Index definition drift | Metadata + `EXPLAIN` |
| Durable write trên one-node fail | Bucket replica count 1, quorum impossible | Kiểm tra numReplicas |
| MAJORITY success nhưng không có replica | Single-node, zero replica | Không coi là HA test |
| PersistToMajority fail với Ephemeral | Không có disk persistence | Dùng Couchbase bucket phù hợp |
| Durable operation timeout | Quorum, disk, network, ambiguous outcome | Phân loại SDK exception và reconcile |
| KV write mới đã đọc được nhưng query cũ | Index consistency | REQUEST_PLUS hoặc AT_PLUS |
| Update index query thấy cả old/new state | Index lag, scan consistency sai | Test REQUEST_PLUS, kiểm tra query |
| Count trong SQL++ lớn hơn dự kiến | Dữ liệu run khác | Filter test_run_id |
| Test class kế tiếp nối port đã dừng | Spring context cache/container lifecycle | Đồng bộ lifecycle |
| Reactive test không ghi document | Mono/Flux chưa subscribe | StepVerifier |
| Expired doc bị fetch thành NotFound | TTL đã áp dụng | Phân biệt với lỗi network |

### 18.1. Đừng gộp tất cả thành retryable error

- `DocumentNotFoundException` do TTL: có thể là hành vi nghiệp vụ hợp lệ.
- `CasMismatchException`: xử lý optimistic conflict, đọc lại state.
- `DurabilityImpossibleException`: sửa topology/quorum, không retry mù.
- `AmbiguousTimeoutException`/durability ambiguous: không biết mutation đã commit hay chưa, reconcile/idempotency.
- `No index available`: sai index setup hoặc query plan; không sửa bằng sleep.
- `AuthorizationFailureException`: sai quyền, fail fast.
- `TimeoutException` query: có thể do Index Service backlog/scan wait/SLO, cần chẩn đoán.

Khi test một nhánh lỗi, **assert đúng exception/cause và trạng thái server liên quan**, không dùng `assertThrows(Exception.class)` để cho một lỗi Docker cũng được tính PASS.

### 18.2. Đồng hồ và timeout nên được tách riêng

| Bước | Timeout minh họa | Điều kiện kết thúc |
| --- | --- | --- |
| Docker/container startup | Theo resources/image | Server initialization |
| SDK cluster/bucket ready | 60 giây | Service/data sockets usable |
| Scope/collection propagation | 30 giây | KV probe thành công |
| Index build/watch | 90 giây | Index ONLINE |
| TTL 8s | 30 giây | KV exists false |
| Eventual index visibility | 30 giây | NOT_BOUNDED query thấy key |
| Durable mutation | Theo SDK/service SLO | Write ack hoặc exception được phân loại |
| REQUEST_PLUS query | Theo request SLO/scanWait | Result phù hợp consistency |

Các số trên **không phải default SLA của Couchbase**. Chúng là gợi ý để một test không đợi vô hạn và báo được giai đoạn hỏng.

## 19. Reactive API: expiry/durability vẫn cần subscribe

Nếu hệ thống dùng reactive Spring Data hoặc reactive SDK, publisher `Mono`/`Flux` phải được subscribe mới có thể xác nhận I/O.

### 19.1. SDK reactive insert có durability và expiry

~~~java
import reactor.test.StepVerifier;

String key = "it::" + UUID.randomUUID() + "::cart::reactive";

StepVerifier.create(
    collection.reactive().insert(
        key,
        JsonObject.create().put("state", "ACTIVE"),
        insertOptions()
            .expiry(Duration.ofSeconds(10))
            .durability(DurabilityLevel.MAJORITY))
)
    .assertNext(result -> assertNotEquals(0L, result.cas()))
    .verifyComplete();
~~~

Sau subscription, dùng `StepVerifier` trên `get` hoặc SDK KV blocking trong teardown để xác minh body và expiry. Cleanup reactive cũng phải subscribe:

~~~java
StepVerifier.create(collection.reactive().remove(key))
    .assertNext(result -> assertNotEquals(0L, result.cas()))
    .verifyComplete();
~~~

Đoạn cleanup này chỉ áp dụng khi key **chưa hết hạn**. Nếu TTL đã hết, reactive remove có thể báo not-found; test nên xử lý đúng trường hợp đó mà không che lỗi khác.

### 19.2. Reactive queries cần cùng consistency policy

SDK reactive query vẫn có lựa chọn scan consistency tương ứng. Khi sử dụng Spring Data reactive repository, một derived query có thể dựa vào `@ScanConsistency`/template options theo phiên bản. Test:

1. Subscribe mutation publisher và đợi terminal success.
2. Subscribe query publisher với consistency mong muốn.
3. Assert đúng rows/keys/terminal signals.
4. Cleanup publisher và verify completion.

**Không dùng `StepVerifier.withVirtualTime` để tua nhanh Couchbase TTL hoặc index ingestion**. Virtual time chỉ chi phối các scheduler trong Reactor pipeline mà test kiểm soát, không đổi Server clock.

## 20. Quan sát vận hành và SLO

Ba nhóm metrics cần được theo dõi riêng:

| Nhóm | Metric gợi ý | Ý nghĩa |
| --- | --- | --- |
| TTL | `couchbase_document_expiry_observed_ms` | Chênh lệch thời gian quan sát expiry |
| TTL | `couchbase_ttl_update_reset_total` | Số lần update reset TTL ngoài chủ đích |
| Durability | `couchbase_durable_write_latency_ms` | Latency theo mức durability |
| Durability | `couchbase_durability_impossible_total` | Quorum configuration failures |
| Durability | `couchbase_ambiguous_write_total` | Kết quả mutation không rõ |
| Index | `couchbase_index_first_visibility_ms` | Thời gian từ KV ack tới first NOT_BOUNDED match |
| Index | `couchbase_request_plus_latency_ms` | Query latency khi chờ consistency |
| Index | `couchbase_index_watch_timeout_total` | Index build không ONLINE đúng hạn |
| Index | `couchbase_query_no_index_total` | Query thiếu index có thể dùng |
| Cross-cutting | `couchbase_test_resource_setup_failures_total` | Fixture setup failures |

Đây là **tên metrics gợi ý**, không phải metrics Couchbase/Spring Data chắc chắn xuất mặc định. Dùng OpenTelemetry/Micrometer/SDK diagnostics để bổ sung context phù hợp, tránh đưa key/customer PII vào metric labels vì cardinality và rò rỉ dữ liệu.

### 20.1. Đo độ trễ với monotonic clock và workload đại diện

- Dùng `System.nanoTime()` cho elapsed times, không dùng wall clock để so nanoseconds.
- Tách setup phase/index build khỏi measurement.
- Kiểm tra event-loop/network, CI host load và Server quotas.
- Báo median/p95/p99 trên N đủ lớn, không chỉ một lần.
- Ghi replica count, durability level, bucket type, index definition, scan consistency.
- Không so hai biến thể khi một bên có Query Service/index khác.
- Không giả định regular write luôn nhanh hơn durable trong **mỗi** sample.
- Đặt SLO theo use case và môi trường có tài nguyên đại diện.

### 20.2. Test nhanh và test hiệu năng cần tách

Một bộ regression CI có thể dùng TTL 8–15 giây, deadline 30–40 giây, vài mutations, ít queries. Benchmark index lag và durability under load cần dataset lớn, warmup, load-control và máy riêng. Đừng biến toàn bộ pull-request tests thành benchmark nặng có độ dao động lớn.

## 21. Bài thực hành: giỏ hàng giữ chỗ với TTL và chỉ mục

**Bối cảnh:** ứng dụng đặt hàng muốn giữ một reservation giỏ hàng trong 20 giây, ghi reservation theo Majority durability, và tìm `ACTIVE` reservations bằng SQL++.

~~~json
{
  "test_run_id": "run-123",
  "cart_id": "cart::u100",
  "state": "ACTIVE",
  "reserved_units": 2,
  "created_at": "2026-01-15T08:00:00Z"
}
~~~

Resource:

~~~text
shop_it.commerce.reservations
index ix_reservations_run_state(test_run_id, state, created_at)
key it::<runId>::reservation::<logicalId>
TTL 20s (ví dụ)
Durability MAJORITY (nếu topology cho phép)
~~~

### 21.1. Các yêu cầu kiểm thử

1. Khởi tạo CouchbaseContainer với KV/QUERY/INDEX và bucket test độc lập production.
2. Kiểm tra replica topology để Majority có thể đạt trên environment đó.
3. Provision `commerce.reservations` và secondary index, chờ ONLINE.
4. Seed reservation với key riêng và `test_run_id`.
5. Kiểm tra `InsertOptions.expiry(Duration.ofSeconds(20))` được Server lưu vào expiry metadata.
6. Kiểm tra `DurabilityLevel.MAJORITY` write được acknowledge và JSON body đúng.
7. Dùng `REQUEST_PLUS` query reservation ngay sau insert, xác minh đúng key.
8. Dùng `NOT_BOUNDED` polling để đo thời gian xuất hiện của document trên index.
9. Dùng `replaceOptions().preserveExpiry(true)` để sửa state mà vẫn giữ deadline cố định.
10. Dùng `getAndTouch` trên một document khác để kiểm tra sliding expiry, không trộn với fixed deadline.
11. Chờ document hết hạn bằng KV, sau đó kiểm tra query không còn trả key bằng polling.
12. Cleanup keys đã tạo; không `deleteAll` shared collection.

### 21.2. Sơ đồ kiểm thử

~~~mermaid
flowchart TD
    A["CouchbaseContainer + resource fixture"] --> B["Index ONLINE + proper replicas"]
    B --> C["Insert reservation TTL + MAJORITY"]
    C --> D["KV get + expiry metadata"]
    D --> E["SQL++ REQUEST_PLUS read"]
    E --> F["Optional: measure NOT_BOUNDED visibility"]
    F --> G["Replace + preserveExpiry"]
    G --> H["KV TTL expires"]
    H --> I["SQL++ eventual absence"]
    I --> J["Cleanup + report"]
~~~

### 21.3. Câu hỏi tự kiểm tra

1. **TTL có phải JSON field không?** Không; Couchbase document expiry là metadata Server.
2. **Java `Clock.fixed` có làm document Server hết hạn sớm không?** Không.
3. **`GetResult.expiryTime()` có mặc định luôn có dữ liệu không?** Cần `getOptions().withExpiry(true)` và document có expiry.
4. **`preserveExpiry(true)` làm gì?** Giữ expiry deadline khi replace.
5. **`getAndTouch` khác GET thường thế nào?** Gia hạn/thay expiry.
6. **Durability MAJORITY trên bucket replicas=0 có bảo vệ replica khác không?** Không, majority chỉ là một node.
7. **Có thể dùng PERSIST_TO_MAJORITY trên Ephemeral bucket không?** Không, vì cần disk persistence.
8. **CAS và durability có giống nhau không?** Không, một cái kiểm version, một cái yêu cầu ack/quorum.
9. **Index ONLINE có bảo đảm index thấy mutation mới ngay không?** Không.
10. **NOT_BOUNDED query đầu tiên phải thiếu document mới?** Không, có thể bắt kịp ngay.
11. **REQUEST_PLUS có tạo index không?** Không.
12. **consistentWith(MutationState) làm gì?** Chờ các mutation tokens đã cung cấp.
13. **Mutation token thiếu mà test AT_PLUS yêu cầu thì xử lý thế nào?** Fail rõ, không fallback âm thầm.
14. **Durable write ack có nghĩa document không bao giờ expire?** Không.
15. **Query không trả expired key có chứng minh index entry dọn vật lý chưa?** Không nhất thiết.
16. **Read-back KV có chứng minh disk/replica durability?** Không.
17. **Tại sao dùng runId trong document và query?** Cô lập dữ liệu giữa tests.
18. **Benchmark index lag có nên dùng một mutation làm p99 không?** Không.
19. **Thấy timeout durable write có nên retry ngay?** Không nếu outcome ambiguous; cần reconcile.
20. **CI thiếu Docker có thể báo integration PASS không?** Không.

## 22. Checklist triển khai

- [ ] Pin Server/SDK/Spring Boot/Testcontainers versions phù hợp.
- [ ] Cấp cluster/bucket test riêng; không dùng credentials production.
- [ ] KV, Query và Index Services được bật theo loại test.
- [ ] Scope/collection/index đúng keyspace và index ONLINE trước khi query.
- [ ] Tạo fixture keys/runIds độc lập, cleanup chỉ những keys thuộc sở hữu.
- [ ] TTL dùng Server expiry, không tin Java clock giả.
- [ ] `withExpiry(true)` được dùng để kiểm tra metadata, không suy từ body.
- [ ] TTL test polling có deadline và có khoảng dư.
- [ ] Test giữ expiry qua update với `preserveExpiry`.
- [ ] Test sliding TTL bằng `getAndTouch` riêng.
- [ ] Kiểm tra bucket/collection maxTTL/effective expiry policy.
- [ ] Test Spring Data `@Document(expiry)` qua SDK raw metadata.
- [ ] Durability test phân biệt regular, MAJORITY, persistence levels.
- [ ] Kiểm tra bucket replica count/topology và bucket type trước khi test.
- [ ] Không suy multi-node failover từ successful one-node MAJORITY.
- [ ] Xử lý durability/timeout ambiguous khác CAS conflict.
- [ ] Không coi `get(key)` thành công là bằng chứng replica persisted.
- [ ] SQL++ REQUEST_PLUS test đọc được key vừa ghi.
- [ ] AT_PLUS/consistentWith test giữ mutation token đúng.
- [ ] NOT_BOUNDED eventual test không ép lần query đầu phải thiếu.
- [ ] Index lag đo bằng monotonic clock và report sampling method.
- [ ] Update index test kiểm tra old value vắng + new value xuất hiện.
- [ ] Delete/expiry test hiểu khác biệt end-to-end query absence và physical index cleanup.
- [ ] Reactive publisher được subscribe và cleanup chạy thật.
- [ ] CI có timeout rõ cho từng tầng; không skip im lặng.
- [ ] SLO/metrics riêng cho TTL, durable write, index visibility và consistency latency.

## Tài liệu tham khảo chính thức

- [Couchbase Java SDK — KV Operations, Durability and Expiration](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `expiry(Duration/Instant)`, `withExpiry`, `preserveExpiry`, `getAndTouch`, `durability`.
- [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): quorum, levels, replica topology và ambiguous outcomes.
- [Couchbase Java SDK — Data Durability and Consistency](https://docs.couchbase.com/java-sdk/current/concept-docs/data-durability-acid-transactions.html): regular vs durable mutation và trade-offs.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `NOT_BOUNDED`, `REQUEST_PLUS`, `consistentWith`.
- [Couchbase Java SDK — MutationState API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/MutationState.html): mutation tokens và AT_PLUS.
- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): create scope/collection/index và `watchIndexes`.
- [Couchbase Server — CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): composite/secondary index.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document(expiry)`, `@Version` và mapping.
- [Spring Data Couchbase — Document API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/mapping/Document.html): expiry, expiryExpression và durabilityLevel.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD, derived SQL++ queries và scan consistency.
- [Spring Boot — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và auto-configuration.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer` và `BucketDefinition`.
- [Testcontainers Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`/`@Container` lifecycle.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): reactive test publisher assertions.




