# Kiểm thử giao dịch thành công, rollback và thử lại trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế ba nhóm integration test độc lập cho **commit thành công**, **rollback khi lỗi** và **thử lại khi xung đột tạm thời** trên Couchbase Server thật.
2. Hiểu cơ chế distributed ACID transactions của Couchbase: **transaction attempt**, staged mutations, Active Transaction Record (ATR), atomic commit point, unstaging và asynchronous cleanup.
3. Sử dụng Java SDK `cluster.transactions().run(ctx -> {...})` để đọc, thay thế, tạo hoặc xóa **nhiều document trong cùng một transaction**.
4. Phân biệt `TransactionFailedException`, `TransactionExpiredException` và **`TransactionCommitAmbiguousException`**; không đồng nhất “không nhận success” với “đã rollback”.
5. Viết phép thử rollback có **điểm lỗi được điều khiển** sau khi đã staged một mutation, rồi kiểm tra **mọi document liên quan** vẫn giữ trạng thái trước giao dịch.
6. Kiểm thử automatic retry mà không tạo side effect ngoài transaction, không dùng barrier sai cách gây deadlock khi SDK thực thi lại lambda.
7. Kiểm chứng tương tác của `@Transactional`, `CouchbaseTransactionManager`, repository, `CouchbaseTemplate` và `CouchbaseTransactionalOperator` trong Spring Data Couchbase theo cấu hình thực của dự án.
8. Tổ chức Testcontainers, bucket durability, fixture cô lập, cleanup, reactive testing, CI và quan sát hiệu năng để kết quả không bị flaky.

Bài thuộc chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**, xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive. Chủ đề này chỉ tập trung vào **hợp đồng giao dịch và bằng chứng kiểm thử**: không xem một lệnh repository `save` thành công là bằng chứng của atomicity nhiều document.

> **Nguyên tắc cốt lõi:** Một phép thử transaction đúng phải kiểm tra **cả tập document**, đúng **ranh giới transaction**, và phân biệt **commit**, **rollback chắc chắn** với **commit chưa xác định**. Một phép kiểm tra chỉ thấy exception, hoặc chỉ thấy một document được cập nhật, là chưa đủ.

## 1. Bối cảnh: chuyển tiền giữa hai ví bằng hai document

Giả sử ví A có 1.000 đơn vị và ví B có 200 đơn vị, thực hiện chuyển 250 từ A sang B.

~~~text
Trước giao dịch:
  wallet::A  balance = 1000
  wallet::B  balance = 200
  Tổng = 1200

Sau khi commit thành công:
  wallet::A  balance = 750
  wallet::B  balance = 450
  Tổng = 1200

Sau khi rollback:
  wallet::A  balance = 1000
  wallet::B  balance = 200
  Tổng = 1200
~~~

Nếu dùng hai lệnh `upsert`/`save` độc lập:

~~~java
// KHÔNG phải một transaction chỉ vì nằm trong cùng Java method.
wallets.upsert(fromKey, debitBody);
wallets.upsert(toKey, creditBody);
~~~

thì sau lệnh thứ nhất có thể xảy ra timeout, crash, lỗi validation hoặc mất kết nối. Lệnh thứ hai chưa chạy, số tiền bị trừ nhưng chưa cộng; **không có rollback tự động** chỉ nhờ code nằm trong cùng một phương thức Java.

Trong Couchbase transaction, cả hai thay đổi được thực hiện qua **transaction attempt context** và có atomic commit point:

~~~mermaid
flowchart TD
    A["Begin transaction"] --> B["ctx.get ví A và B"]
    B --> C{"A đủ tiền?"}
    C -->|Không| D["Business exception → rollback"]
    C -->|Có| E["ctx.replace A: trừ 250"]
    E --> F["ctx.replace B: cộng 250"]
    F --> G{"Commit attempt"}
    G -->|Committed| H["Transaction success"]
    G -->|Lỗi tạm thời có thể thử lại| I["Rollback attempt và retry lambda"]
    I --> B
    G -->|Thất bại không thể phục hồi| J["TransactionFailed/Expired"]
    G -->|Không xác định tại điểm commit| K["CommitAmbiguous: cần reconcile"]
~~~

### 1.1. Định nghĩa “đúng” phải gồm nhiều bất biến

| Test case | Ví A | Ví B | Tổng | Điều cần chứng minh |
| --- | ---: | ---: | ---: | --- |
| Setup | 1000 | 200 | 1200 | Fixture đúng và độc lập |
| Commit 250 | 750 | 450 | 1200 | Cả hai mutation được commit |
| Business reject | 1000 | 200 | 1200 | Không có mutation nào xuất hiện |
| Lỗi sau khi staged A | 1000 | 200 | 1200 | Rollback toàn transaction |
| Hai giao dịch hợp lệ cạnh tranh | Tùy hai khoản chuyển | Tùy hai khoản chuyển | Bất biến | Không mất cập nhật, không double-apply |
| Commit ambiguous | Chưa thể kết luận ngay | Chưa thể kết luận ngay | Reconcile | Không retry mù vì kết quả có thể đã commit |

Điều cần tránh: chỉ assert ví A giảm 250 mà không assert ví B tăng 250. Có thể cả hai thay đổi sai theo cùng một hướng và tổng không đổi; vì vậy cần kiểm tra **giá trị từng ví**, tổng và **request/operation ID** nếu ứng dụng có idempotency.

## 2. Couchbase transaction vận hành như thế nào?

Couchbase distributed transactions dùng cơ chế **staging** và **metadata commit** để phối hợp những document thuộc nhiều collections.

### 2.1. Transaction, attempt và transaction lambda

~~~java
cluster.transactions().run(ctx -> {
    // Đọc và mutation thông qua ctx.
    // SDK có thể chạy lại toàn bộ lambda nếu gặp lỗi transient.
});
~~~

Một lời gọi `run` đại diện cho **một transaction logic**. SDK có thể thực hiện **nhiều attempts**. Nếu gặp write-write conflict hay lỗi transient có khả năng phục hồi, SDK có thể rollback attempt rồi chạy lại lambda; không phải mọi lỗi đều được retry.

Vì thế:

- Mỗi attempt phải **đọc lại state hiện tại**.
- Lambda không được gửi email, gọi thanh toán ngoài, publish Kafka hoặc ghi file như side effect không kiểm soát.
- Không tăng số lần thực thi một tác vụ ngoài transaction rồi suy rằng có đúng một commit.
- Không gắn transaction attempt ID vào business request ID; cùng request có thể có nhiều attempts.

### 2.2. Staged mutations và ATR

Couchbase có **Active Transaction Records (ATRs)** chứa trạng thái attempt, đồng thời lưu staged document mutations qua metadata/XATTR trước khi commit. Đây là cơ chế nội bộ của protocol; ứng dụng không được tự sửa ATR hoặc các XATTR dành riêng cho transactions.

~~~mermaid
sequenceDiagram
    participant App as Test / Application
    participant Txn as Transactions SDK
    participant DB as Couchbase
    App->>Txn: run(ctx -> ...)
    Txn->>DB: ctx.get(A), ctx.get(B)
    Txn->>DB: stage replace(A), replace(B)
    Txn->>DB: update ATR to committed
    DB-->>Txn: Commit point reached
    Txn->>DB: Unstage document A/B
    Txn-->>App: TransactionResult (success)
~~~

**Commit point** được xác định bởi transaction metadata. Việc bỏ staging từ từng document (**unstaging**) có thể kết thúc sau thời điểm transaction đã commit. Transaction-aware actors đọc kết quả theo trạng thái commit, trong khi **đọc KV thông thường không tham gia transaction** có thể cần thời gian tới khi mọi document được unstaged.

### 2.3. Đừng trộn transaction-aware và thao tác thường bên trong lambda

Sai:

~~~java
cluster.transactions().run(ctx -> {
    // Sai: thao tác này KHÔNG tự tham gia transaction.
    walletCollection.upsert(walletAKey, newBodyA);
    ctx.replace(ctx.get(walletCollection, walletBKey), newBodyB);
});
~~~

Đúng:

~~~java
cluster.transactions().run(ctx -> {
    var a = ctx.get(walletCollection, walletAKey);
    var b = ctx.get(walletCollection, walletBKey);
    ctx.replace(a, modifiedA);
    ctx.replace(b, modifiedB);
});
~~~

Nếu code dùng **Spring Data repository/template** trong transaction, phải bảo đảm Spring transaction integration thực tế **gắn operations vào transaction context**, không kết luận dựa trên một `@Transactional` đặt sai vị trí.

### 2.4. Isolation và giới hạn phạm vi

| Khả năng | Couchbase transaction test có thể chứng minh |
| --- | --- |
| Atomicity hai document | Commit toàn bộ hoặc rollback toàn bộ theo protocol |
| Consistent snapshot/visibility | Theo transaction isolation semantics của SDK/framework |
| Conflict resolution | Lỗi transient có thể làm attempt/lambda retry |
| Durability | Phụ thuộc bucket replica/quorum, cluster topology, options |
| External HTTP/Kafka | **Không** tự thuộc Couchbase transaction |
| DDL `CREATE INDEX` trong lambda | **Không**: DDL phải provision trước |
| TTL và CAS | Metadata/expiry có tương tác riêng, cần test riêng |
| Read committed trên Spring Data | Xác minh semantics theo version/framework |

**Không đồng nhất một Couchbase container một node với production nhiều node.** Đó là môi trường tốt để xác minh functional transaction flows, không phải bằng chứng failover/quorum.

## 3. Lựa chọn phiên bản và tài nguyên kiểm thử

Ví dụ dùng **Java 17+, Spring Boot 3.5.x, Testcontainers 1.x và Couchbase Java SDK 3.x**. Dự án dùng Boot 4.x/Testcontainers 2.x phải đổi đúng dependency/import theo version.

| Thành phần | Boot 3.x / Testcontainers 1.x | Boot 4.x / Testcontainers 2.x |
| --- | --- | --- |
| Couchbase data starter | `spring-boot-starter-data-couchbase` | Starter tương ứng |
| Test dependency | `spring-boot-starter-test` | `spring-boot-starter-data-couchbase-test` hoặc module test tương ứng |
| Boot Testcontainers | `spring-boot-testcontainers` | `spring-boot-testcontainers` |
| Couchbase Testcontainers | `org.testcontainers:couchbase` | `org.testcontainers:testcontainers-couchbase` |
| JUnit 5 Testcontainers | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| `@DataCouchbaseTest` | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'

    // Có thể dùng Awaitility để chờ unstaging/readiness.
    testImplementation 'org.awaitility:awaitility'

    // Kiểm thử reactive publisher.
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Gắn version bằng BOM tương thích; không trộn Testcontainers 1.x với 2.x. SDK Java 3.3+ đã tích hợp transactions API vào SDK, vì vậy **không tự thêm thư viện couchbase-transactions thế hệ cũ** khi đang dùng SDK mới nếu BOM không yêu cầu.

### 3.1. Chọn image Server và services

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

Tag `community-7.2.5` là **minh họa phiên bản cố định**, không phải bản Server được khuyến nghị cho mọi dự án. Hãy chọn image nằm trong compatibility matrix SDK/Server và gần production target. Với transaction chỉ dùng KV `ctx.get/insert/replace/remove`, các Query/Index Services không nhất thiết cần; chúng được bật ở ví dụ để kiểm thử thêm SQL++.

### 3.2. Cảnh báo đặc biệt: replica count trên cluster một node

**Đây là điều kiện tiền đề quyết định test transaction có thể chạy.** Couchbase transactions sử dụng durable writes. Trong self-managed cluster chỉ có một Data node, nếu bucket cấu hình **1 replica** thì quorum durability có thể không đạt và nhận `DurabilityImpossibleException`.

| Topology test | Bucket replica count | Kết quả durable write |
| --- | ---: | --- |
| Một Data node | 1 | Có thể không đạt majority, transaction fail |
| Một Data node | 0 | Majority khả thi ở một node (không chứng minh replica durability) |
| Nhiều nodes đủ quorum | Theo topology | Có thể kiểm tra độ bền với replicas |

**Trước khi đánh giá transaction tests**, kiểm tra bucket `shop_it` đang có `numReplicas=0` nếu Testcontainers chạy một node và sử dụng durability mặc định phù hợp. Tạo bucket với replica count thích hợp ngay từ provisioning; nếu đã thay replica setting của bucket tồn tại, Server có thể yêu cầu rebalance để cấu hình có hiệu lực. API `BucketDefinition` thay đổi theo bản Testcontainers; đừng sao chép builder option của Testcontainers Go vào Java.

Đặt kiểm tra cấu hình vào fixture:

~~~java
int configuredReplicas =
    cluster.buckets().getBucket("shop_it").numReplicas();

org.junit.jupiter.api.Assertions.assertEquals(
    0, configuredReplicas,
    "Single-node transaction fixture cần bucket 0 replicas");
~~~

Đoạn check này làm **fail fast** khi hạ tầng không phù hợp, không âm thầm cho phép transaction test sai kết quả. Khi production dùng replica 1+, cần bộ multi-node tests riêng để đánh giá durability.

### 3.3. Tài nguyên và keyspace của bài

~~~text
Bucket:       shop_it
Scope:        billing
Collection:   wallets
Collection:   transfer_requests (cho idempotency case)
Wallet keys:  it::<runId>::wallet::A
              it::<runId>::wallet::B
Transfer key: it::<runId>::transfer::req-123
~~~

Resource setup tạo **scope và collections** trước test; `withBucket` chỉ tạo bucket. Không tạo collection/index bằng SQL++ DDL bên trong transaction lambda.

## 4. Chuẩn bị fixture Couchbase Testcontainers

Ví dụ test slice dùng `@ServiceConnection`, có thể thay bằng `@DynamicPropertySource` nếu dự án không dùng Boot testcontainers support.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.TestInstance;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Testcontainers
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class WalletTransactionIT {

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

    @Autowired Cluster cluster;

    @BeforeAll
    void prepare() {
        cluster.waitUntilReady(Duration.ofSeconds(60));
        cluster.bucket("shop_it")
            .waitUntilReady(Duration.ofSeconds(60));

        // Fixture phải bảo đảm billing.wallets tồn tại và KV usable.
        // Tạo billing.transfer_requests khi test idempotency.
        // Check configuredReplicas == 0 trên môi trường một node.
    }
}
~~~

Với Spring Boot 4.x, import `@DataCouchbaseTest` từ package mới. `@DataCouchbaseTest` chỉ load data-layer slice; không mặc định scan service/business components. Test chỉ dùng SDK cluster có thể dùng JUnit + Testcontainers thuần mà không cần Spring context, nhưng ở đây giữ slice để làm cầu nối tới Spring Data trong phần sau.

### 4.1. Provision scope và collection có tính idempotent

~~~java
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;
import com.couchbase.client.java.manager.collection.CollectionSpec;

var manager = cluster.bucket("shop_it").collections();

try {
    manager.createScope("billing");
} catch (ScopeExistsException alreadyExists) {
    // Expected nếu fixture được chạy lại.
}

for (String name : java.util.List.of(
        "wallets", "transfer_requests")) {
    try {
        manager.createCollection(
            CollectionSpec.create(name, "billing"));
    } catch (CollectionExistsException alreadyExists) {
        // Không drop dữ liệu của test khác.
    }
}
~~~

Sau create, collection manifest có thể cần thời gian lan truyền; dùng một KV probe có deadline/Awaitility để kiểm tra collection **usable**, không thay bằng `Thread.sleep(3000)`. **Chỉ catch AlreadyExists**, không nuốt permission, bucket-not-found hoặc network failures.

### 4.2. Tách tài nguyên khỏi dữ liệu của từng test

Resource setup chạy một lần cho class/container. **Mỗi `@Test` tạo một `runId` riêng** và tự seed/cleanup hai ví:

~~~java
String prefix = "it::" + java.util.UUID.randomUUID() + "::";
String walletAKey = prefix + "wallet::A";
String walletBKey = prefix + "wallet::B";

var walletCollection = cluster.bucket("shop_it")
    .scope("billing").collection("wallets");

walletCollection.insert(
    walletAKey,
    com.couchbase.client.java.json.JsonObject.create()
        .put("balance", 1000L)
        .put("currency", "VND")
        .put("label", "A"));

walletCollection.insert(
    walletBKey,
    com.couchbase.client.java.json.JsonObject.create()
        .put("balance", 200L)
        .put("currency", "VND")
        .put("label", "B"));
~~~

Các values **1000/200** cố định để assertion tái lập; physical keys có UUID để không va chạm với test khác. Dùng `insert` cho fixtures mới để phát hiện duplicate key; không `upsert` vào một key cố định rồi vô tình reset dữ liệu của test đồng thời.

### 4.3. Công cụ đọc và cleanup

~~~java
static long balance(
        com.couchbase.client.java.Collection c, String key) {
    return c.get(key).contentAsObject().getLong("balance");
}

static void deleteIfPresent(
        com.couchbase.client.java.Collection c, String key) {
    if (c.exists(key).exists()) {
        c.remove(key);
    }
}
~~~


## 5. Test commit thành công: cả hai document cùng thay đổi

Một bộ test tốt không chỉ kiểm tra ví A đã trừ tiền, mà còn xác minh ví B đã nhận tiền và tổng trước/sau được bảo toàn.

### 5.1. Transaction helper bằng Couchbase Java SDK

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.transactions.TransactionResult;

static final class InsufficientFunds extends RuntimeException {}

static TransactionResult transfer(
        Cluster cluster, Collection wallets,
        String fromKey, String toKey, long amount) {

    if (amount <= 0 || fromKey.equals(toKey)) {
        throw new IllegalArgumentException("Transfer không hợp lệ");
    }

    return cluster.transactions().run(ctx -> {
        // Đọc lại trong MỖI transaction attempt.
        var from = ctx.get(wallets, fromKey);
        var to = ctx.get(wallets, toKey);

        JsonObject debitBody = from.contentAs(JsonObject.class);
        JsonObject creditBody = to.contentAs(JsonObject.class);

        long beforeFrom = debitBody.getLong("balance");
        long beforeTo = creditBody.getLong("balance");

        if (beforeFrom < amount) {
            throw new InsufficientFunds();
        }

        debitBody.put("balance",
            Math.subtractExact(beforeFrom, amount));
        creditBody.put("balance",
            Math.addExact(beforeTo, amount));

        // Cả HAI mutation thuộc một ctx.
        ctx.replace(from, debitBody);
        ctx.replace(to, creditBody);
    });
}
~~~

`cluster.transactions().run` có thể chạy lại lambda nếu gặp conflict transient; vì vậy mỗi attempt phải đọc lại state. Không dùng một `JsonObject` chụp trước transaction rồi áp dụng nhiều lần. Số dư được mô tả bằng `long` nguyên đơn vị cho dễ hiểu; hệ thống tiền tệ thật cần quy tắc currency, rounding, audit và idempotency riêng.

### 5.2. Test commit với assertions độc lập

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

@Test
void commitsBothWalletMutations() {
    String prefix = "it::" + UUID.randomUUID() + "::";
    String a = prefix + "wallet::A";
    String b = prefix + "wallet::B";

    var wallets = cluster.bucket("shop_it")
        .scope("billing").collection("wallets");

    wallets.insert(a, JsonObject.create().put("balance", 1000L));
    wallets.insert(b, JsonObject.create().put("balance", 200L));

    try {
        TransactionResult result =
            transfer(cluster, wallets, a, b, 250L);

        assertNotNull(result.transactionId());

        // Sau commit, unstaging có thể tiếp tục trong nền.
        // Poll KV read khi cần quan sát state ngoài transaction.
        await().atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                assertEquals(750L, balance(wallets, a));
                assertEquals(450L, balance(wallets, b));
            });

        assertEquals(1200L,
            balance(wallets, a) + balance(wallets, b));
    } finally {
        deleteIfPresent(wallets, a);
        deleteIfPresent(wallets, b);
    }
}
~~~

`TransactionResult.unstagingComplete()` cho biết mọi document đã được unstaged tại thời điểm trả về hay chưa; `false` **không có nghĩa rollback**. Transaction-aware actors biết commit point, nhưng non-transactional KV readers có thể cần chờ asynchronous unstaging. Poll có deadline giúp test không flaky; nó không phải bằng chứng về atomic visibility đối với một ứng dụng cố ý dùng non-transactional reads trong cửa sổ đó.

### 5.3. Tại sao kiểm tra tổng tiền chưa đủ?

Có thể hai bug bù trừ nhau khiến tổng vẫn là 1.200 nhưng giao dịch gửi nhầm ví. Vì vậy assert cả:

~~~java
assertEquals(750L, balance(wallets, a));
assertEquals(450L, balance(wallets, b));
assertEquals(1200L, balance(wallets, a) + balance(wallets, b));
~~~

Nếu có transfer request document, còn phải đối chiếu `requestId`, amount, currency và trạng thái của operation, không chỉ biến động balances.

## 6. Test rollback do lỗi sau khi đã stage một thay đổi

Một test ném exception trước mutation chỉ chứng minh rule validation. Để chứng minh **rollback staged change**, gây lỗi **sau `ctx.replace(A)` nhưng trước khi credit B**.

### 6.1. Lỗi chủ động, không phải ngắt mạng

~~~java
static final class ForcedRollback extends RuntimeException {
    ForcedRollback() {
        super("Simulated error after debit was staged");
    }
}

static void transferThenFail(
        Cluster cluster, Collection wallets,
        String fromKey, String toKey, long amount) {

    cluster.transactions().run(ctx -> {
        var from = ctx.get(wallets, fromKey);
        var to = ctx.get(wallets, toKey);

        JsonObject body = from.contentAs(JsonObject.class);
        body.put("balance", body.getLong("balance") - amount);

        ctx.replace(from, body); // Staged, CHƯA commit.

        // Gây lỗi sau khi đã stage debit.
        throw new ForcedRollback();
    });
}
~~~

`to` được đọc để xác nhận đường truy cập cả hai ví nhưng chưa được mutate; lỗi được tạo có chủ đích ở vị trí giữa workflow. Việc ném exception khiến transaction attempt thất bại; **không tự catch trong lambda rồi tiếp tục** vì attempt đã lỗi có thể không còn được phép commit.

### 6.2. Assert exception và state của CẢ HAI ví

~~~java
import com.couchbase.client.java.transactions.error.TransactionFailedException;
import com.couchbase.client.java.transactions.error.TransactionCommitAmbiguousException;

@Test
void rollsBackStagedDebitWhenSecondStepFails() {
    String prefix = "it::" + UUID.randomUUID() + "::";
    String a = prefix + "wallet::A";
    String b = prefix + "wallet::B";

    var wallets = cluster.bucket("shop_it")
        .scope("billing").collection("wallets");

    wallets.insert(a, JsonObject.create().put("balance", 1000L));
    wallets.insert(b, JsonObject.create().put("balance", 200L));

    try {
        TransactionFailedException failure = assertThrows(
            TransactionFailedException.class,
            () -> transferThenFail(cluster, wallets, a, b, 250L));

        assertFalse(
            failure instanceof TransactionCommitAmbiguousException,
            "Commit ambiguous KHÔNG phải rollback chắc chắn");

        assertTrue(failure.getCause() instanceof ForcedRollback);

        assertEquals(1000L, balance(wallets, a));
        assertEquals(200L, balance(wallets, b));
        assertEquals(1200L, balance(wallets, a) + balance(wallets, b));
    } finally {
        deleteIfPresent(wallets, a);
        deleteIfPresent(wallets, b);
    }
}
~~~

Test trên dùng API SDK transaction và đánh giá trạng thái sau một **failure trước commit**. Một `TransactionFailedException` thường chứa cause để phân biệt lỗi business được chủ động tạo với lỗi connectivity/index/durability. Khi nâng SDK, cần kiểm tra exception translation và cause chain đúng version.

### 6.3. Rollback do thiếu tiền là một test khác

~~~java
@Test
void rejectsInsufficientFundsWithoutPartialCommit() {
    String prefix = "it::" + UUID.randomUUID() + "::";
    String a = prefix + "wallet::A";
    String b = prefix + "wallet::B";
    var wallets = cluster.bucket("shop_it")
        .scope("billing").collection("wallets");

    wallets.insert(a, JsonObject.create().put("balance", 100L));
    wallets.insert(b, JsonObject.create().put("balance", 200L));

    try {
        TransactionFailedException failure = assertThrows(
            TransactionFailedException.class,
            () -> transfer(cluster, wallets, a, b, 250L));

        assertTrue(failure.getCause() instanceof InsufficientFunds);
        assertEquals(100L, balance(wallets, a));
        assertEquals(200L, balance(wallets, b));
    } finally {
        deleteIfPresent(wallets, a);
        deleteIfPresent(wallets, b);
    }
}
~~~

Khác biệt: test thiếu tiền kiểm tra **domain guard trước staged writes**. Test `ForcedRollback` kiểm chứng **đã staged nhưng không commit**. Cả hai cần thiết để tránh một test “rollback” chỉ tạo exception tại đầu hàm rồi tuyên bố atomicity.

### 6.4. Ma trận rollback chi tiết

| Tình huống | Giai đoạn | Kỳ vọng |
| --- | --- | --- |
| Amount không hợp lệ | Trước transaction | Validation error, không mutation |
| Thiếu tiền | Trong lambda trước stage | TransactionFailed + state cũ |
| Lỗi giữa debit/credit | Sau `ctx.replace(A)` | TransactionFailed + A/B vẫn cũ |
| `ctx.insert` duplicate key | Khi stage insert | Failed, không partial commit |
| `ctx.get` key không tồn tại | Khi đọc | Failed hoặc domain policy rõ |
| Xung đột temporary giữa hai transactions | Khi attempt chạy | SDK có thể thử lại |
| Timeout trước commit | Sau nhiều attempts | TransactionExpired, chưa tới commit |
| Không rõ kết quả tại commit | Commit point/network | **Không khẳng định rollback** |

### 6.5. Rollback không đồng nghĩa xóa sạch ATR/XATTR ngay

Couchbase có **asynchronous cleanup** cho staged transaction metadata. Với failure trước commit, các thay đổi không được hiển thị như committed, nhưng nội bộ metadata có thể còn trong thời gian cleanup. Không tự sửa/delete `_txn:atr-*` hoặc transaction XATTR để “làm sạch test”; hãy để protocol xử lý.

## 7. Phân biệt failure, expiration và ambiguous commit

Couchbase Java SDK có các exceptions:

~~~java
import com.couchbase.client.java.transactions.error.TransactionFailedException;
import com.couchbase.client.java.transactions.error.TransactionExpiredException;
import com.couchbase.client.java.transactions.error.TransactionCommitAmbiguousException;
~~~

| Loại | Điều SDK xác nhận | Test/ứng dụng phải làm |
| --- | --- | --- |
| `TransactionFailedException` | Không đạt commit point | Phân tích cause và logs, test rollback |
| `TransactionExpiredException` | Timeout trước khi đạt commit | Phân loại như non-commit, xem retry budget |
| `TransactionCommitAmbiguousException` | Không biết transaction có commit chưa | Reconcile theo operation ID, không retry mù |
| `DurabilityImpossibleException` (cause) | Không đạt durability quorum | Sửa replica/topology, không coi là business rollback |
| Domain exception | Nghiệp vụ chủ động từ chối | Test state cũ và đúng business error |
| Permission error | Principal không đủ quyền | Fail fast, không retry như transient conflict |

**Quan trọng:** `TransactionCommitAmbiguousException` có thể kế thừa `TransactionFailedException`. Vì vậy phải catch ambiguous **trước** failed:

~~~java
try {
    TransactionResult result =
        transfer(cluster, wallets, a, b, 250L);
    // Commit đã đạt; kiểm tra result.unstagingComplete().
} catch (TransactionCommitAmbiguousException ambiguous) {
    // Kết quả CHƯA rõ. Không kết luận rollback.
    // Dùng business requestId/operation document để reconcile.
    throw ambiguous;
} catch (TransactionFailedException failed) {
    // Chưa đạt commit point. Xem cause/logs.
    throw failed;
}
~~~

### 7.1. Retry mù sau commit ambiguous là anti-pattern

~~~java
catch (TransactionCommitAmbiguousException e) {
    // SAI: nếu lần trước đã commit, tiền có thể bị chuyển lần nữa.
    transfer(cluster, wallets, a, b, 250L);
}
~~~

Nếu response bị mất sau commit point, client không thể biết đã transfer chưa. **Không xử lý ambiguous như failed.** Thiết kế idempotency với key `transfer_request::<requestId>`, ghi operation marker cùng transaction và reconcile trước khi quyết định thử lại.

### 7.2. Phân biệt commit và unstaging

~~~java
TransactionResult result = cluster.transactions().run(ctx -> {
    // Các transactional operations...
});

if (!result.unstagingComplete()) {
    // Đã committed nhưng tài liệu KV có thể chưa unstaged đầy đủ.
    // Chờ điều kiện committed state nếu test đọc bằng KV thông thường.
}
~~~

`TransactionResult` có `transactionId()` và `logs()` phục vụ chẩn đoán; không dùng chúng như business request ID. Đọc non-transactional KV ngay lập tức trong trạng thái chưa unstaged có thể chưa thấy tất cả thay đổi; test cần polling hữu hạn hoặc transaction-aware read.

### 7.3. Fault injection ambiguous không phù hợp CI regression mặc định


## 8. Kiểm thử SDK tự thử lại khi hai transaction cạnh tranh

Bộ giao dịch Couchbase có thể **tự thử lại attempt hoặc một số thao tác** khi gặp xung đột transient. Một test đáng tin phải:

- Thực sự có hai transactions cùng xử lý **một nguồn dữ liệu**.
- Không dùng một `Thread.sleep` với hy vọng scheduler tự tạo race.
- Không giả định writer A/B sẽ thắng.
- Không assert chính xác số lần lambda chạy vì SDK có thể retry ở nhiều tầng.
- Assert **business state cuối cùng** khi cả hai transactions hoàn tất.

### 8.1. Hai giao dịch chuyển từ A sang B và C

~~~text
Trước:
  Wallet A = 1000
  Wallet B = 200
  Wallet C = 400
  Tổng = 1600

Transfer X: A -> B, amount 100
Transfer Y: A -> C, amount 100

Sau cả hai giao dịch được commit:
  Wallet A = 800
  Wallet B = 300
  Wallet C = 500
  Tổng = 1600
~~~

Nếu cả hai đọc số dư A=1000 nhưng không xử lý conflict/retry, có thể chỉ một giao dịch thành công hoặc có lost update. Transactions SDK phải bảo đảm protocol an toàn, nhưng **test chỉ được tuyên bố cả hai hoàn tất** nếu futures thật sự thành công.

### 8.2. Đồng bộ **lần đọc đầu**, không chặn mọi retry

Một barrier vô điều kiện đặt trong transaction lambda có thể làm deadlock khi SDK chạy lại lambda: attempt mới chờ một writer đã hoàn thành từ lâu. Dùng `AtomicInteger` để chỉ **lần attempt đầu tiên** chờ barrier.

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import static com.couchbase.client.java.transactions.config.TransactionOptions.transactionOptions;

static TransactionResult competingTransfer(
        Cluster cluster,
        Collection wallets,
        String fromKey,
        String toKey,
        long amount,
        CountDownLatch bothRead,
        CountDownLatch release,
        AtomicInteger attempts) {

    return cluster.transactions().run(ctx -> {
        var from = ctx.get(wallets, fromKey);
        var to = ctx.get(wallets, toKey);

        JsonObject fromBody = from.contentAs(JsonObject.class);
        JsonObject toBody = to.contentAs(JsonObject.class);

        // Mỗi transaction chỉ chặn tại lần lambda được gọi đầu.
        if (attempts.incrementAndGet() == 1) {
            bothRead.countDown();

            try {
                if (!release.await(12, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Barrier timeout");
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Transaction attempt bị ngắt", interrupted);
            }
        }

        long available = fromBody.getLong("balance");
        if (available < amount) {
            throw new InsufficientFunds();
        }

        fromBody.put("balance", available - amount);
        toBody.put("balance",
            Math.addExact(toBody.getLong("balance"), amount));

        ctx.replace(from, fromBody);
        ctx.replace(to, toBody);
    }, transactionOptions().timeout(Duration.ofSeconds(30)));
}
~~~

`ctx.get` xảy ra trước `bothRead.countDown()`. Vì vậy barrier diễn đạt **hai attempts ban đầu đã đọc nguồn A trước khi được phép stage writes**. Nếu một attempt cần retry, nó **không chờ lại** cùng barrier.

Đếm `attempts` dùng cho diagnostics, không coi `attempts >= 2` là assertion bắt buộc của mọi SDK minor version. Mục tiêu chính là **final state và việc cả hai transactions kết thúc thành công**.

### 8.3. Hai futures với timeout

~~~java
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

@Test
void concurrentTransfersBothCommitWithoutLostUpdate()
        throws Exception {

    String prefix = "it::" + UUID.randomUUID() + "::";
    String a = prefix + "wallet::A";
    String b = prefix + "wallet::B";
    String c = prefix + "wallet::C";

    var wallets = cluster.bucket("shop_it")
        .scope("billing").collection("wallets");

    wallets.insert(a, JsonObject.create().put("balance", 1000L));
    wallets.insert(b, JsonObject.create().put("balance", 200L));
    wallets.insert(c, JsonObject.create().put("balance", 400L));

    CountDownLatch bothRead = new CountDownLatch(2);
    CountDownLatch release = new CountDownLatch(1);
    ExecutorService executor = Executors.newFixedThreadPool(2);

    AtomicInteger xAttempts = new AtomicInteger();
    AtomicInteger yAttempts = new AtomicInteger();

    try {
        Future<TransactionResult> x = executor.submit(() ->
            competingTransfer(cluster, wallets, a, b, 100L,
                bothRead, release, xAttempts));

        Future<TransactionResult> y = executor.submit(() ->
            competingTransfer(cluster, wallets, a, c, 100L,
                bothRead, release, yAttempts));

        assertTrue(bothRead.await(15, TimeUnit.SECONDS),
            "Cả hai transactions chưa đọc state ban đầu");
        release.countDown();

        TransactionResult rx = x.get(40, TimeUnit.SECONDS);
        TransactionResult ry = y.get(40, TimeUnit.SECONDS);

        assertNotNull(rx.transactionId());
        assertNotNull(ry.transactionId());

        await().atMost(Duration.ofSeconds(30))
            .untilAsserted(() -> {
                assertEquals(800L, balance(wallets, a));
                assertEquals(300L, balance(wallets, b));
                assertEquals(500L, balance(wallets, c));
            });

        assertEquals(1600L,
            balance(wallets, a)
            + balance(wallets, b)
            + balance(wallets, c));
    } finally {
        release.countDown();
        executor.shutdownNow();
        boolean stopped = executor.awaitTermination(
            15, TimeUnit.SECONDS);

        // Chỉ cleanup khi các workers đã kết thúc; nếu không,
        // báo lỗi fixture thay vì xóa key đang có transaction dùng.
        if (stopped) {
            deleteIfPresent(wallets, a);
            deleteIfPresent(wallets, b);
            deleteIfPresent(wallets, c);
        } else {
            throw new AssertionError(
                "Transaction workers chưa dừng; không cleanup giữa chừng");
        }
    }
}
~~~

Bộ test này **có thể cần timeout/resource tuning theo CI**, không được kết luận transaction bug chỉ từ việc máy hết CPU hoặc cluster thiếu replica quorum. Tuy nhiên, **đừng sửa mọi failure bằng cách tăng thời gian ngủ**; xác minh trước nguyên nhân và log của transactions SDK.

### 8.4. Không khẳng định SDK chắc chắn chạy lambda đúng hai lần

SDK có thể retry cả attempt hoặc các KV operations tùy loại lỗi. Do đó:

- Assert hai futures hoàn tất **thành công**.
- Assert cuối cùng A=800, B=300, C=500.
- Ghi `xAttempts/yAttempts` làm diagnostics.
- Không đặt `assertEquals(2, xAttempts.get())`.
- Không gọi side effect ngoài transaction trong lambda để “đếm commit”.
- Nếu timeout xảy ra, xem cụ thể conflict/expiration/infrastructure.

Với use case mong muốn chỉ **một transaction được chấp nhận**, test phải dùng chính business rule làm tiêu chí, không ép cả hai success.

## 9. Side effects và at-least-once execution của lambda

Nếu lambda có thể chạy nhiều attempts, mã sau không an toàn:

~~~java
cluster.transactions().run(ctx -> {
    // Sai: email/HTTP không rollback theo Couchbase transaction.
    paymentGateway.charge(customerId, amount);

    var wallet = ctx.get(wallets, walletKey);
    ctx.replace(wallet, adjustedBody);
});
~~~

Khi conflict làm lambda retry, payment gateway có thể bị gọi **nhiều lần**, hoặc gọi thành công dù transaction cuối cùng rollback. Tương tự, gửi email/publish Kafka/ghi log nghiệp vụ với side effect có thể lặp.

### 9.1. Những việc được phép trong transaction lambda

| Hành động | Khuyến nghị |
| --- | --- |
| `ctx.get` / `ctx.insert` / `ctx.replace` / `ctx.remove` | Đúng transactional API |
| Đọc JSON và tính toán pure, deterministic | Phù hợp |
| Validate business invariant | Phù hợp, throw domain error |
| Đọc source config immutable | Phù hợp nếu không thay giữa attempts |
| Phát HTTP charge | Không, side effect ngoài transaction |
| Gửi Kafka event trực tiếp | Không, dễ duplicate |
| Tạo UUID mới mỗi attempt cho business request | Không, dùng request ID ổn định |
| Ghi `AtomicInteger` cho test barrier | Chỉ là instrumentation của test, không production side effect |
| DDL `CREATE INDEX` | Không được thực hiện trong transaction |

### 9.2. Outbox/operation document thay side effect trực tiếp

Có thể stage một **outbox document** cùng mutation giao dịch, sau commit một worker khác phát event. Event delivery vẫn có thể được thử lại, vì vậy consumer cần idempotency theo event ID.

~~~java
cluster.transactions().run(ctx -> {
    var from = ctx.get(wallets, a);
    var to = ctx.get(wallets, b);

    // ctx.replace(from, newFromBody);
    // ctx.replace(to, newToBody);

    // Stage operation event: không phát Kafka trong lambda.
    ctx.insert(outboxCollection,
        "outbox::" + requestId,
        JsonObject.create()
            .put("type", "TransferCommitted")
            .put("request_id", requestId)
            .put("amount", amount));
});
~~~

`requestId` phải được sinh **bên ngoài transaction lambda** và gắn với một business operation, không phụ thuộc attempt nào thắng. Không biến outbox thành array không giới hạn trong ví.

## 10. Idempotency khi request bị gửi lại hoặc commit ambiguous

Couchbase transaction bảo đảm atomicity của các database mutations thuộc transaction; **nó không tự bảo đảm requestId chỉ được xử lý một lần**.

Ví dụ API nhận `POST /transfers`, client timeout rồi gửi lại cùng body:

~~~text
request_id = req-123
from A, to B, amount 250

Lần 1 có thể đã COMMIT nhưng response bị mất.
Lần 2 không được chuyển thêm 250.
~~~

### 10.1. Transactional request marker

Một phương án là dùng collection `billing.transfer_requests` và key:

~~~text
it::<tenantId>::transfer::<requestId>
~~~

Trong transaction:

~~~java
var transferRequests = cluster.bucket("shop_it")
    .scope("billing")
    .collection("transfer_requests");

cluster.transactions().run(ctx -> {
    // Thử tạo request marker cùng transaction.
    ctx.insert(transferRequests, requestKey,
        JsonObject.create()
            .put("from", fromKey)
            .put("to", toKey)
            .put("amount", amount)
            .put("state", "APPLIED"));

    var from = ctx.get(wallets, fromKey);
    var to = ctx.get(wallets, toKey);

    JsonObject f = from.contentAs(JsonObject.class);
    JsonObject t = to.contentAs(JsonObject.class);

    if (f.getLong("balance") < amount) {
        throw new InsufficientFunds();
    }

    f.put("balance", f.getLong("balance") - amount);
    t.put("balance", t.getLong("balance") + amount);

    ctx.replace(from, f);
    ctx.replace(to, t);
});
~~~

**Toàn bộ marker và hai balances thuộc cùng transaction.** Nếu attempt rollback, marker không được committed độc lập. Nếu requestId được sử dụng lại, transactional `insert` có thể thất bại do duplicate. Adapter cần phân biệt:

- Marker đã tồn tại và payload **giống hệt** → trả kết quả operation trước (theo policy).
- Marker đã tồn tại nhưng payload **khác** → từ chối reused request ID.
- Marker chưa tồn tại → thử operation mới.
- Commit ambiguous → reconcile theo marker, **không chuyển tiền lại mù**.

Đây là skeleton protocol; production cần xử lý **concurrent duplicate requests**, state transitions, timeout, cleanup và retry có ranh giới rõ.

### 10.2. Test replay cùng requestId

~~~text
Given: A=1000, B=200, transfer marker req-123 chưa có
When:  Chạy transfer(req-123, A, B, 250)
Then:  A=750, B=450, marker APPLIED
When:  Gọi lại transfer(req-123, cùng payload)
Then:  Không debit thêm; A=750, B=450
When:  Gọi req-123 với amount khác
Then:  Policy báo conflict, không thay balances
~~~

Không chỉ assert marker tồn tại; phải kiểm tra **số dư không đổi sau replay**. Nếu client đã nhận `TransactionCommitAmbiguousException`, cần để một reconciliation job/adapter xác minh marker committed và kết quả cuối, thay vì assert ngay rằng transaction rollback.

## 11. Spring Data Couchbase: test @Transactional đúng ranh giới

Spring Data Couchbase hỗ trợ transaction qua `@Transactional`, `CouchbaseTransactionManager` và `CouchbaseTransactionalOperator` khi đã cấu hình đúng. Các operations của repository/template có thể tham gia transaction context.

**Tuy nhiên:** một test chạy SDK `cluster.transactions().run` thành công **không chứng minh `@Transactional` service đang được Spring proxy**. Cần test riêng đường Spring Data thực tế.

### 11.1. Entity @Version Long và keyspace

Spring Data Couchbase transactions docs yêu cầu entity có `@Version Long` để giữ CAS.

~~~java
package com.example.shop.billing;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
@Scope("billing")
@Collection("wallets")
public class WalletDocument {
    @Id private String id;
    @Version private Long cas;

    @Field private String owner;
    @Field private long balance;

    protected WalletDocument() {}

    public WalletDocument(String id, String owner, long balance) {
        if (id == null || id.isBlank()
                || owner == null || owner.isBlank()
                || balance < 0) {
            throw new IllegalArgumentException("Invalid wallet");
        }
        this.id = id;
        this.owner = owner;
        this.balance = balance;
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getOwner() { return owner; }
    public long getBalance() { return balance; }

    public void debit(long amount) {
        if (amount <= 0 || balance < amount) {
            throw new InsufficientFunds();
        }
        balance -= amount;
    }

    public void credit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        balance = Math.addExact(balance, amount);
    }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface WalletRepository
        extends CouchbaseRepository<WalletDocument, String> {
}
~~~

Cùng `@Version Long`, test Spring Data entity mapping và CAS metadata cần chạy trên server thực. Không dùng field `version` trong JSON để mô phỏng CAS. Với SDK raw JSON fixtures, Spring Data có thể cần type metadata `_class` hoặc alias; thuận tiện nhất là seed bằng repository rồi **read back** trước test transaction.

### 11.2. Service thật có @Transactional

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletTransferService {
    private final WalletRepository wallets;

    public WalletTransferService(WalletRepository wallets) {
        this.wallets = wallets;
    }

    @Transactional
    public void move(String aKey, String bKey,
                     long amount, boolean failAfterDebit) {

        WalletDocument from =
            wallets.findById(aKey).orElseThrow();
        WalletDocument to =
            wallets.findById(bKey).orElseThrow();

        from.debit(amount);
        wallets.save(from);

        if (failAfterDebit) {
            throw new IllegalStateException(
                "Simulated business failure after debit");
        }

        to.credit(amount);
        wallets.save(to);
    }
}
~~~

Test phải xác minh **đúng `CouchbaseTransactionManager`** được sử dụng, đặc biệt nếu application còn có JPA/JDBC transaction manager. Dùng `@EnableTransactionManagement` trong configuration hỗ trợ transaction, service phải là Spring bean, và gọi method qua **Spring proxy từ một bean khác**.

### 11.3. Không gọi cùng class rồi mong AOP tự intercept

Sai:

~~~java
@Service
class Example {
    void outer() {
        move(...); // Self-invocation: bypass Spring proxy.
    }

    @Transactional
    void move(...) { ... }
}
~~~

Đúng là test lấy bean thông qua `@Autowired WalletTransferService` và gọi public transactional method từ bên ngoài. Nếu chỉ new `WalletTransferService(repository)` bằng Java constructor, `@Transactional` sẽ **không được Spring intercept**.

### 11.4. Test slice và transaction configuration

`@DataCouchbaseTest` thường chỉ load tầng dữ liệu; nó không tự động scan service nghiệp vụ. Với test service:

- Dùng `@SpringBootTest` khi cần cấu hình application/transaction manager đầy đủ.
- Hoặc `@DataCouchbaseTest` + `@Import(WalletTransferService.class)` và test configuration đủ transaction beans/proxy.
- Kiểm tra bean `CouchbaseTransactionManager` hiện diện và là manager được `@Transactional` chọn.
- Khi nhiều managers, chỉ định transaction manager theo tên/config được dự án xác thực.
- Giữ container/collection/schema provisioning trước khi gọi method.
- Không gọi method giao dịch qua `this` hoặc static helper làm bypass proxy.

### 11.5. Kiểm thử @Transactional commit và rollback

~~~java
@Autowired WalletTransferService service;
@Autowired WalletRepository walletRepository;

@Test
void springTransactionalServiceCommitsBoth() {
    // Seed hai WalletDocument vào billing.wallets với keys riêng.
    // Gọi service.move(a, b, 250, false) qua injected proxy.
    // Verify A=750, B=450 trên database thật.
}

@Test
void springTransactionalServiceRollsBackOnRuntimeError() {
    // Seed A=1000, B=200 bằng repository thật.
    assertThrows(IllegalStateException.class,
        () -> service.move(a, b, 250, true));
    // Verify A=1000, B=200; không chỉ assert exception.
}
~~~

Đây là **skeleton**; cách exception được translate/wrap có thể khác theo Spring Data release. Quan trọng nhất: nếu transaction manager/proxy bị cấu hình sai, service có thể ghi debit rồi ném exception mà **không rollback**. Test state cuối sẽ phát hiện ngay, còn test chỉ `assertThrows` sẽ cho PASS giả.

### 11.6. Đừng giả định rollbackFor/noRollbackFor giống JPA

Tài liệu Spring Data Couchbase cho biết ở các release được mô tả, một số attributes `@Transactional` như **rollback attributes** không được transaction integration hỗ trợ như JDBC/JPA; isolation được mô tả là **read-committed**. Vì vậy không lấy một test `@Transactional(rollbackFor=...)` từ JPA rồi khẳng định Couchbase cũng có đúng semantics đó.


## 12. Reactive transactions và CouchbaseTransactionalOperator

Spring Data Couchbase cung cấp `CouchbaseTransactionalOperator` để xây dựng transaction trong reactive pipeline; Java SDK cũng có `cluster.reactive().transactions().run(...)`. Cả hai cần được kiểm thử với publisher **được subscribe**, không chỉ tạo `Mono` rồi kết thúc test.

### 12.1. Reactive SDK transaction

~~~java
import com.couchbase.client.java.json.JsonObject;
import reactor.test.StepVerifier;

var walletsReactive = cluster.bucket("shop_it")
    .scope("billing")
    .collection("wallets")
    .reactive();

var result = cluster.reactive().transactions().run(ctx ->
    ctx.get(walletsReactive, fromKey)
        .flatMap(from -> ctx.get(walletsReactive, toKey)
            .flatMap(to -> {
                JsonObject f = from.contentAs(JsonObject.class);
                JsonObject t = to.contentAs(JsonObject.class);

                if (f.getLong("balance") < 250L) {
                    return reactor.core.publisher.Mono.error(
                        new InsufficientFunds());
                }

                f.put("balance", f.getLong("balance") - 250L);
                t.put("balance", t.getLong("balance") + 250L);

                return ctx.replace(from, f)
                    .then(ctx.replace(to, t));
            }))
);

StepVerifier.create(result)
    .assertNext(tx ->
        org.junit.jupiter.api.Assertions.assertNotNull(
            tx.transactionId()))
    .verifyComplete();
~~~

Sau đó phải xác minh trạng thái **cả hai ví trên server**, kể cả cửa sổ unstaging. Test rollback reactive có thể dùng `expectError` theo exception translation thực tế; không coi `Mono.error` bất kỳ là transaction rollback đúng nếu lỗi có thể phát sinh trước khi chạm database.

### 12.2. Lưu ý Spring reactive operator

Theo tài liệu Spring Data Couchbase, khi tạo operator thủ công, dùng factory `CouchbaseTransactionalOperator.create(manager)` của Spring Data Couchbase, không tự giả định `TransactionalOperator.create(manager)` của Spring generic có semantics giống nhau ở mọi release.

~~~java
// Skeleton: chỉ thực hiện khi cấu hình transaction manager
// và phiên bản Spring Data Couchbase hỗ trợ đúng API.
@Autowired CouchbaseTransactionalOperator operator;
@Autowired ReactiveCouchbaseTemplate reactiveTemplate;

// Dùng operator để bọc reactive Couchbase operations.
// Kết quả phải được subscribe bằng StepVerifier.
~~~

Không gọi `block()` trong production reactive event-loop. `StepVerifier.withVirtualTime` cũng không tua nhanh Couchbase server transaction cleanup, network timeout hay TTL.

## 13. SQL++ trong transaction và giới hạn DDL

Couchbase transactions có thể dùng KV và nhiều lệnh SQL++ DML như SELECT/INSERT/UPDATE/DELETE/MERGE. Nhưng **DDL CREATE INDEX không được thực hiện trong transaction lambda**.

~~~text
Đúng:
  Setup scope/collection/index ở fixture trước test
  Chờ index ONLINE
  Trong lambda dùng ctx.get/ctx.replace/ctx.query

Sai:
  Trong lambda tự CREATE INDEX rồi mới SELECT
~~~

Một phép chuyển tiền qua `ctx.get(collection, key)` theo document key không cần secondary index. Khi ứng dụng thực hiện `ctx.query` lọc theo JSON field, cần Query/Index Services và index phù hợp, đồng thời xác minh query consistency theo SDK và Spring Data version.

**Read-your-own-writes trong transaction** khác việc SQL++ query ngoài transaction thấy index vừa thay đổi tức thì. `REQUEST_PLUS` có thể giúp một query ngoài transaction cần read-after-write, nhưng nó không thay thế transaction commit hay index creation.

## 14. Chiến lược retry theo loại lỗi

| Tình huống | Cách xử lý |
| --- | --- |
| Write-write conflict transient | Cho SDK retry theo transaction budget |
| Rebalance hoặc lỗi transient phục hồi | Dựa vào SDK/configured timeout, theo dõi attempts |
| Thiếu tiền/hàng | Domain reject, không retry |
| Duplicate request ID | Reconcile marker/payload, không debit lần hai |
| Sai JSON/converter hoặc RBAC | Fail fast và sửa cấu hình |
| DurabilityImpossible trên single-node bucket | Sửa replica count/topology |
| TransactionExpired trước commit | Chưa commit; quyết định lại theo operation policy |
| TransactionCommitAmbiguous | Không biết đã commit, bắt buộc reconcile |
| HTTP/Kafka side effect trong lambda | Thiết kế lại, không coi retry là an toàn |

Timeout giao dịch có thể được cấu hình bằng `TransactionOptions.timeout`:

~~~java
import java.time.Duration;
import static com.couchbase.client.java.transactions.config.TransactionOptions.transactionOptions;

TransactionResult result = cluster.transactions().run(
    ctx -> {
        // Transactional operations.
    },
    transactionOptions().timeout(Duration.ofSeconds(30))
);
~~~

30 giây chỉ là **giá trị minh họa**, không phải SLO hay default bắt buộc. Tăng timeout quá lớn có thể kéo dài thời gian các staged mutations giữ conflict với transaction khác; chọn ngân sách theo workload và theo dõi latency.

## 15. Cleanup, test isolation và CI

### 15.1. Giữ quyền sở hữu dữ liệu

- Mỗi `@Test` dùng prefix `it::<runId>::` riêng cho wallet keys và transfer request key.
- Cleanup trong `finally` chỉ xóa owned keys, không `deleteAll` trên collection dùng chung.
- Không drop scope/collection đang được test khác sử dụng.
- Khi futures timeout, phải giải phóng latches và **đợi worker threads dừng trước cleanup**.
- Với commit ambiguous, không xóa marker/balances trước khi reconciliation biết trạng thái thực.
- Khi transaction đã commit nhưng unstaging chưa xong, chờ điều kiện KV committed state khi test dùng normal KV reads.

### 15.2. Context cache và lifecycle

Spring TestContext có thể cache `ApplicationContext`, trong khi JUnit Testcontainers extension dừng `static @Container` theo test class. Nếu context bị reuse với mapped ports của container đã dừng, class sau có thể lỗi kết nối. Quản lý cùng vòng đời context–container hoặc tách context theo đúng resource. Không bật Testcontainers reuse mặc định CI để che vấn đề đó.

### 15.3. Metrics và logs

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `cb_tx_commit_total` | Commit thành công |
| `cb_tx_rollback_total` | Failure trước commit |
| `cb_tx_attempt_total` | Số attempts, gồm retries |
| `cb_tx_conflict_retry_total` | Retry do contention |
| `cb_tx_expired_total` | Timeout trước commit |
| `cb_tx_ambiguous_total` | Kết quả commit chưa rõ |
| `cb_tx_unstaging_pending_total` | Commit rồi, unstaging còn pending |
| `cb_tx_latency_seconds` | Latency p50/p95/p99 |
| `transfer_duplicate_request_total` | Request ID được gửi lại |

Các tên trên là **metric ứng dụng có thể tự định nghĩa**, không phải metric chắc chắn được Couchbase tự xuất. `TransactionResult.logs()` / `TransactionFailedException.logs()` hỗ trợ debug; log transaction ID và exception taxonomy nhưng không log passwords/PII hoặc raw production JSON.

### 15.4. Ma trận lỗi môi trường

| Triệu chứng | Nguyên nhân khả dĩ |
| --- | --- |
| Docker không khởi động | Runtime/permission/CI setup |
| Container running nhưng transaction fail ngay | KV service, replica durability, RBAC |
| `DurabilityImpossibleException` | Một node nhưng bucket replicas không phù hợp |
| Collection not found | Fixture chưa provision hoặc manifest chưa usable |
| TransactionExpired | Retry contention/timeout hoặc tài nguyên thiếu |
| TransactionCommitAmbiguous | Không xác định commit point, phải reconcile |
| KV ngay sau success thấy một số document cũ | Unstaging chưa hoàn tất |
| Rollback test vẫn mất tiền | Mutation ở ngoài ctx hoặc Spring proxy/manager sai |
| Two-transaction test bị deadlock | Barrier chặn cả retry attempts |
| Test PASS riêng nhưng fail trong suite | Key collision/context cache/cleanup |
| Reactive test không chạy | Publisher chưa subscribe |

**CI skip integration do thiếu Docker không phải PASS.** Cần phân biệt build/unit test xanh với bằng chứng persistence transaction thực sự đã chạy.

## 16. Bài thực hành: đặt hàng và trừ tồn kho atomically

Ứng dụng có:

~~~text
Bucket: shop_it
Scope: commerce
Collection: stocks
Collection: orders
Collection: order_requests (idempotency)
Key Stock: it::<runId>::stock::coffee250
Key Order: it::<runId>::order::<orderId>
Key Request: it::<runId>::request::<requestId>
~~~

Stock ban đầu:

~~~json
{"sku": "coffee250", "available_units": 5}
~~~

Đơn hàng:

~~~json
{"sku": "coffee250", "quantity": 2, "status": "CONFIRMED"}
~~~

### 16.1. Các yêu cầu kiểm thử

1. Tạo cluster test một node với bucket durability phù hợp và collections đã provision.
2. **Commit success:** tạo Order quantity=2 và Stock từ 5 còn 3.
3. **Rollback:** stage trừ Stock rồi throw trước `ctx.insert(Order)`; Stock vẫn 5, Order không tồn tại.
4. **Business reject:** Order quantity=6 bị từ chối; Stock/Order giữ nguyên.
5. **Concurrent operations:** hai requests mỗi request quantity=2 với Stock=5; cả hai có thể commit sau retry, Stock còn 1.
6. **Insufficient after retry:** Stock=3, hai requests quantity=2; chỉ một accepted, Stock còn 1, không âm.
7. **Replay:** cùng requestId không tạo hai orders hoặc trừ tồn kho hai lần.
8. **Ambiguous:** adapter phải reconcile marker, không tự debit lại.
9. **Raw JSON/CAS:** kiểm tra fields và `@Version` nếu dùng Spring Data.
10. Cleanup theo runId sau khi transaction tasks thực sự đã dừng.

### 16.2. Skeleton giao dịch

~~~java
var stocks = cluster.bucket("shop_it")
    .scope("commerce").collection("stocks");
var orders = cluster.bucket("shop_it")
    .scope("commerce").collection("orders");

TransactionResult tx = cluster.transactions().run(ctx -> {
    var stock = ctx.get(stocks, stockKey);
    JsonObject body = stock.contentAs(JsonObject.class);

    int available = body.getInt("available_units");
    if (available < quantity) {
        throw new InsufficientStock();
    }

    body.put("available_units", available - quantity);
    ctx.replace(stock, body);
    ctx.insert(orders, orderKey,
        JsonObject.create()
            .put("sku", sku)
            .put("quantity", quantity)
            .put("status", "CONFIRMED"));
});
~~~

`stockKey`, `orderKey`, `sku` và `quantity` phải được xác định **trước lambda**. Không generate orderKey ngẫu nhiên trong mỗi retry attempt. Skeleton chưa có request marker, vì vậy muốn hỗ trợ replay an toàn phải bổ sung `order_requests` vào cùng transaction.

### 16.3. Tự kiểm tra

1. **Hai lệnh repository.save liên tiếp mặc định atomic?** Không.
2. **Transaction lambda có thể chạy lại?** Có, với các lỗi transient phù hợp.
3. **ATR lưu gì?** Metadata attempts/commit state.
4. **Staged mutation đã committed chưa?** Chưa.
5. **`unstagingComplete=false` có nghĩa rollback?** Không.
6. **TransactionFailed cho biết gì?** Không đạt commit point.
7. **Expired khác ambiguous thế nào?** Expired trước commit, ambiguous chưa biết.
8. **Vì sao single-node cần chú ý replicas?** Transaction dùng durable writes.
9. **Được direct `collection.upsert` bên trong transaction lambda không?** Không để thao tác tham gia transaction.
10. **Có thể CREATE INDEX trong lambda?** Không.
11. **HTTP charge trong lambda có an toàn với retry?** Không.
12. **Barrier nên chặn attempt nào?** Lần đầu, không chặn tất cả retries.
13. **Rollback chỉ assert exception đủ không?** Không, phải kiểm tra toàn bộ state.
14. **Success chỉ assert tổng tiền đủ không?** Không, từng ví/operation cũng phải đúng.
15. **@Transactional cần Spring proxy?** Có theo proxy-based Spring AOP.
16. **Self-invocation có đi qua proxy?** Không.
17. **Reactive transaction cần subscribe?** Có.
18. **Commit ambiguous có thể tự chuyển tiền lại?** Không, cần reconcile.
19. **CAS một document có thay multi-document transaction không?** Không.
20. **CI skip test khi thiếu Docker có phải integration PASS không?** Không.

## 17. Checklist trước khi hoàn tất

- [ ] Couchbase Server test thật, image/SDK/Testcontainers/Spring versions tương thích.
- [ ] Bucket durability/quorum phù hợp với số nodes.
- [ ] Scope/collection tồn tại và readiness có timeout.
- [ ] Không dùng tài nguyên hoặc secrets production.
- [ ] Mọi KV mutations trong SDK transaction dùng `ctx`.
- [ ] Không gửi HTTP/Kafka side effects trong lambda.
- [ ] Success test kiểm tra cả hai ví và tổng invariant.
- [ ] Rollback test gây lỗi sau một staged mutation rồi kiểm tra tất cả states.
- [ ] Không nhầm TransactionFailed/Expired với CommitAmbiguous.
- [ ] Phân biệt commit point và hoàn tất unstaging.
- [ ] Retry test tạo real conflict, không giả định attempts exact.
- [ ] Barrier không giữ các retry attempts chờ vô hạn.
- [ ] Idempotency/reconciliation dùng operation marker khi có request replay.
- [ ] Spring @Transactional test kiểm tra đúng proxy và transaction manager.
- [ ] Không mặc định rollbackFor như JPA khi chưa xác minh Spring Data version.
- [ ] Reactive test/cleanup được subscribe.
- [ ] Cleanup owned keys sau khi tất cả workers ngừng.
- [ ] CI phân loại hạ tầng, conflict, business failure và ambiguous.
- [ ] Không coi one-node test là phép chứng minh failover/quorum production.
- [ ] Không can thiệp ATR hoặc transaction XATTR nội bộ.

## Tài liệu tham khảo chính thức

- [Couchbase Java SDK — Using Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): ctx methods, retry và transactions API.
- [Couchbase Java SDK — Transaction Concepts](https://docs.couchbase.com/java-sdk/current/concept-docs/transactions.html): ATR, staging, commit/rollback, cleanup.
- [Couchbase Java SDK — Error Handling](https://docs.couchbase.com/java-sdk/current/concept-docs/transactions-error-handling.html): failed/expired/ambiguous và unstaging.
- [Couchbase Java SDK — Transactions API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/transactions/Transactions.html): run lambda/options.
- [Couchbase Server — Transactions](https://docs.couchbase.com/server/current/learn/data/transactions.html): topology và replica prerequisites.
- [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): durable writes, quorum/replicas.
- [Spring Data Couchbase — Transactions](https://docs.spring.io/spring-data/couchbase/reference/couchbase/transactions.html): @Transactional, managers/operators.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): @Version Long, mapping.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository operations.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): CouchbaseContainer và BucketDefinition.
- [Testcontainers Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): @Container lifecycle.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): @ServiceConnection.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): test reactive publishers.



