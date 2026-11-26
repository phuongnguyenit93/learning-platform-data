# @DataCouchbaseTest và cấu hình tài nguyên kiểm thử cho Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác **`@DataCouchbaseTest` tải những bean nào, không tải những bean nào**, và vì sao annotation này không tự cung cấp Couchbase Server.
2. Cấu hình **Couchbase test resource** bằng Testcontainers hoặc cluster kiểm thử cô lập, tách connection details khỏi tên bucket và tài nguyên nghiệp vụ.
3. Chọn `@ServiceConnection` hoặc `@DynamicPropertySource` theo phiên bản Spring Boot và mức kiểm soát cần thiết.
4. Provision bucket, scope, collection, secondary index và kiểm tra readiness trước khi chạy repository/query.
5. Viết kiểm thử **Spring Data entity mapping, repository, `CouchbaseTemplate` và SDK JSON** với dữ liệu thật, không chỉ dùng mock.
6. Kiểm tra riêng **KV, SQL++/index consistency, CAS/`@Version`, TTL, transaction và reactive**.
7. Thiết kế isolation, cleanup và CI để test ổn định, không xóa lẫn fixture hoặc vô tình kết nối production.

Đây là bài trong chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**. Module xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive là những thành phần phải được **xác minh bằng hạ tầng thật** khi ngữ nghĩa lưu trữ là trọng tâm.

> **Nguyên tắc quan trọng:** `@DataCouchbaseTest` là **test slice của Spring Boot**, không phải “Couchbase embedded”. Nó giúp cấu hình phần data trong Spring context; Couchbase Server vẫn phải được cung cấp riêng.

## 1. @DataCouchbaseTest giải quyết vấn đề nào?

Một `@SpringBootTest` thường khởi tạo rất nhiều thành phần ứng dụng: web layer, service, message adapter, scheduler, cấu hình tích hợp bên ngoài và persistence. Nếu chỉ cần kiểm tra entity–JSON và repository, toàn bộ context này có thể thừa, khiến test chậm và phụ thuộc những dịch vụ không liên quan.

`@DataCouchbaseTest` giới hạn phạm vi để tập trung vào **Spring Data Couchbase**:

- Cấu hình liên quan Couchbase, chẳng hạn `CouchbaseTemplate` hoặc `ReactiveCouchbaseTemplate` khi dependency phù hợp.
- Quét entity có `@Document` và Spring Data Couchbase repositories trong phạm vi cấu hình quét.
- Sử dụng mapping context/converter và auto-configuration của tầng dữ liệu.
- Không mặc định quét toàn bộ `@Service`, `@Component` hoặc `@ConfigurationProperties` của ứng dụng.

Hành vi trên được mô tả trong tài liệu chính thức của Spring Boot; chi tiết auto-configuration tùy phiên bản.

~~~mermaid
flowchart TB
    T["@DataCouchbaseTest"] --> A["Spring test context gọn"]
    A --> B["Repository / Template / Converter"]
    B --> C["Couchbase Java SDK"]
    C --> D["Couchbase Server kiểm thử"]
    X["Testcontainers / cluster riêng"] --> D
    Y["Bucket / scope / collection / index"] --> D
    Z["Application Service / Web / Scheduler"] -.->|"Không tự động có đầy đủ"| A
~~~

Đây là **test tích hợp tầng dữ liệu** nếu nó thực sự kết nối Couchbase. Nó không biến repository thành object giả, cũng không tạo một server in-memory.

### 1.1. Những gì slice xác minh và chưa xác minh

| Nhu cầu | `@DataCouchbaseTest` phù hợp? | Cần chuẩn bị thêm |
| --- | --- | --- |
| Ghi và đọc entity qua `CouchbaseRepository` | Có | Server, bucket, fixture, cleanup |
| Đọc body JSON bằng SDK để đối chiếu `@Field` | Có | Server + SDK `Cluster` |
| Kiểm tra `CouchbaseTemplate` | Có | Template thực và keyspace đúng |
| Kiểm tra derived query dùng SQL++ | Có | Query/Index Services, index, consistency |
| Kiểm tra reactive repository | Có, khi dependency và cấu hình reactive phù hợp | Reactor test + subscription |
| Kiểm tra behavior của service thuần | Không nhất thiết | JUnit unit test nhanh hơn |
| Tiêm `@Service` tùy ý | Không mặc định | `@Import`/filters hoặc `@SpringBootTest` |
| Kiểm thử HTTP/security/filter end-to-end | Không đủ | `@SpringBootTest` và HTTP test |
| Kiểm thử transaction multi-document thật | Có thể là một phần | Đúng transaction configuration, server, nhiều document |
| Kiểm thử failover/durability nhiều node | Không đủ nếu chỉ một container | Topology đa node gần production |

**Không coi việc Spring context khởi động thành công là bằng chứng rằng bucket, collection hay index đã tồn tại.** Những lỗi đó có thể chỉ lộ ra ở thao tác KV/SQL++ đầu tiên.

## 2. Chuẩn bị trước khi viết test

Một bộ kiểm thử có thể lập lại cần ghi rõ:

1. **Spring Boot và Spring Data Couchbase version** đã được pin hoặc quản lý bằng BOM.
2. **Testcontainers version và Couchbase Server image** hỗ trợ nhau.
3. **Tên bucket** dành riêng cho test; nếu có scope/collection thì tạo chúng tường minh.
4. Các Couchbase Services cần: **KV** cho đọc theo key, **Query** và **Index** cho SQL++.
5. Quyền tạo bucket/scope/index và quyền đọc–ghi của test principal.
6. Tài nguyên CPU/RAM và container runtime có sẵn trong CI.
7. Chính sách cleanup, timeouts, index readiness và thứ tự chạy.

### 2.1. Ma trận version rất quan trọng

| Nền tảng | Import `@DataCouchbaseTest` | Ghi chú |
| --- | --- | --- |
| Spring Boot **3.x** | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | Thường đi cùng `spring-boot-starter-test` |
| Spring Boot **4.x** | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` | Từ module `spring-boot-data-couchbase-test`; kiểm tra starter test theo Boot 4 |
| Testcontainers **1.x** | Các module ví dụ `org.testcontainers:couchbase`, `org.testcontainers:junit-jupiter` | Dùng BOM 1.x phù hợp |
| Testcontainers **2.x** | Các module ví dụ `org.testcontainers:testcontainers-couchbase`, `org.testcontainers:testcontainers-junit-jupiter` | Tên artifact đổi; không chép dependency 1.x nguyên xi |

`@ServiceConnection` là annotation do Spring Boot cung cấp, không phải của Couchbase SDK. Testcontainers có `CouchbaseContainer` và `BucketDefinition`; package/import/chữ ký cụ thể phải theo đúng major version.

**Các mã mẫu chính trong bài giả định Java 17+, Spring Boot 3.5.x và Testcontainers 1.x**, trừ nơi ghi khác. Với Boot 4.x/Testcontainers 2.x, thay import/artifact theo BOM đang dùng, không nâng riêng một library rồi mong code mẫu cũ luôn compile.

### 2.2. Phụ thuộc test mẫu (Gradle, dùng BOM của Spring Boot)

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'

    // Chỉ cần khi test reactive bằng StepVerifier.
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Đây là ví dụ cho Testcontainers **1.x**. Với 2.x, dùng artifact mới theo Testcontainers BOM. Nếu chỉ kiểm thử domain logic không liên quan Couchbase, không cần thêm Testcontainers vào tất cả test class.

**Không hardcode credential production** trong file test hoặc property public; container có thể cung cấp credential riêng, còn cluster kiểm thử bên ngoài nên nhận secret từ môi trường CI.

## 3. Bốn lớp tài nguyên phải tách biệt

Trong một bài test Couchbase, “đã kết nối” có thể nghĩa rất nhiều thứ.

~~~mermaid
flowchart TB
    A["Container/cluster đang chạy"] --> B["Couchbase Services đã sẵn sàng"]
    B --> C["Bucket + scope + collection tồn tại"]
    C --> D["Index đã ONLINE, có quyền dùng"]
    D --> E["Repository/SQL++ test thật"]
~~~

| Tài nguyên | Được tạo/cấu hình ở đâu? | Khi thiếu sẽ có lỗi kiểu nào? |
| --- | --- | --- |
| Server/cluster | Testcontainers hoặc cluster CI | Connection refused, bootstrap timeout |
| Connection string + credential | `@ServiceConnection` hoặc config properties | Authentication/TLS failure |
| Bucket | `BucketDefinition`/management setup | Bucket not found, template không gắn được bucket |
| Scope/collection | SDK management/DDL/setup | Scope/collection not found |
| Query/Index Services | Container setup/topology | Query service unavailable, index operation lỗi |
| Secondary index | DDL hoặc QueryIndexManager | No index available, query chậm/không chạy |
| Index readiness | Poll trạng thái hoặc `watchIndexes` | Query ngay sau CREATE INDEX bị flaky |
| Test document | `@BeforeEach`/fixture | Đọc nhầm dữ liệu cũ, test thiếu điều kiện |
| TTL, CAS, durability | Configuration và thao tác server | Semantics khác với mock hoặc giả định |

**Cần phân biệt hai việc:** `@ServiceConnection` cấp **thông tin kết nối đến server**, còn `spring.data.couchbase.bucket-name` xác định bucket cho Spring Data. Annotation này **không tự đặt đúng bucket nếu ứng dụng chưa cấu hình bucket**.

## 4. Entity và repository mẫu cho cả bài

Ví dụ quản lý Order theo document key. Trước tiên dùng default scope/collection trong bucket `shop_it`, sau đó mở rộng sang `sales.orders`.

### 4.1. Order.java

~~~java
package com.example.shop.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Order {
    @Id
    private String id;

    @Version
    private Long cas;

    @Field("customer_id")
    private String customerId;

    @Field("total_amount_vnd")
    private long totalAmountVnd;

    @Field
    private String status;

    protected Order() {}

    public Order(String id, String customerId, long totalAmountVnd) {
        if (id == null || id.isBlank()
                || customerId == null || customerId.isBlank()
                || totalAmountVnd < 0) {
            throw new IllegalArgumentException("Order không hợp lệ");
        }
        this.id = id;
        this.customerId = customerId;
        this.totalAmountVnd = totalAmountVnd;
        this.status = "DRAFT";
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getCustomerId() { return customerId; }
    public long getTotalAmountVnd() { return totalAmountVnd; }
    public String getStatus() { return status; }

    public void addAmount(long amountVnd) {
        if (!"DRAFT".equals(status) || amountVnd <= 0) {
            throw new IllegalStateException("Không thể cập nhật Order");
        }
        totalAmountVnd = Math.addExact(totalAmountVnd, amountVnd);
    }
}
~~~

Ở đây:

- `@Id` dùng **document key**, không tự tạo field JSON `id`.
- `@Version` phản ánh **CAS metadata**, phục vụ optimistic locking.
- `@Field("customer_id")` và `@Field("total_amount_vnd")` xác định tên JSON vật lý.
- `status` và giá trị tiền là **dữ liệu body**.
- Constructor dành cho Spring Data không nên phát sinh lại ID hoặc timestamp khi đọc.

### 4.2. OrderRepository.java

~~~java
package com.example.shop.sales;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<Order, String> {

    List<Order> findByCustomerId(String customerId);
}
~~~

`findById` thường dùng KV theo key; `findByCustomerId` cần query theo field body, thường được hiện thực bằng SQL++ và secondary index. Chúng phải được kiểm thử khác nhau.

## 5. Cách A: @DataCouchbaseTest + Testcontainers + @ServiceConnection

Đây là ví dụ **có thể học và điều chỉnh trực tiếp** cho Spring Boot 3.5.x và Testcontainers 1.x. Container tạo bucket `shop_it`; entity ở mục trước dùng default collection.

~~~java
package com.example.shop.sales;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import com.couchbase.client.java.Cluster;
import org.junit.jupiter.api.Test;
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
class OrderRepositorySliceIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    @Autowired
    OrderRepository orders;

    @Autowired
    Cluster cluster;

    @Test
    void saveReadsRealJsonAndMetadata() {
        String key = "it::order::" + UUID.randomUUID();

        try {
            Order saved = orders.save(
                new Order(key, "customer::u100", 350000));

            Order read = orders.findById(key).orElseThrow();
            assertEquals("customer::u100", read.getCustomerId());
            assertEquals(350000L, read.getTotalAmountVnd());

            var result = cluster.bucket("shop_it")
                .defaultCollection().get(key);

            assertEquals("customer::u100",
                result.contentAsObject().getString("customer_id"));
            assertEquals(350000L,
                result.contentAsObject()
                    .getLong("total_amount_vnd"));
            assertNotEquals(0L, result.cas());
        } finally {
            orders.deleteById(key);
        }
    }
}
~~~

**Điều test này thực sự xác minh:** slice cấu hình repository/template, container khởi động Couchbase, repository lưu/đọc, JSON body có tên field đúng, SDK đọc cùng document key và lấy được CAS.

**Điều test này chưa xác minh:** repository trỏ đúng `sales.orders`, index có hiệu quả, Query Service/Index Service đã sẵn sàng, transaction đa document, TTL hay quyền user production. Những mục đó cần fixture và test riêng.

### 5.1. Vì sao không chỉ @DataCouchbaseTest?

Nếu bỏ Testcontainers và không có cluster kiểm thử:

~~~java
@DataCouchbaseTest
class OrderRepositorySliceIT {
    @Autowired OrderRepository orders;
}
~~~

Spring Data sẽ tìm connection/bucket theo cấu hình hiện có. Nếu không có server, thao tác thật thất bại. Nếu máy vô tình có Couchbase ở URL mặc định, test có thể dùng **sai cluster**, tạo ra kết quả không tái hiện được và nguy cơ dữ liệu thật.

**Không được coi `@DataCouchbaseTest` như H2/embedded database.** Couchbase không được auto-spawn như một in-memory datasource chỉ vì annotation xuất hiện.

### 5.2. @ServiceConnection làm gì?

Trong test Spring Boot hỗ trợ service connections:

- Nhận diện `CouchbaseContainer`.
- Cung cấp `CouchbaseConnectionDetails` với connection string/credential cho auto-configuration.
- Thông tin connection details này có thể ưu tiên hơn properties kết nối thông thường.

Nó **không tự tạo collection, tạo index, seed dữ liệu hoặc chọn tên bucket**. Vì vậy annotation trên class vẫn ghi tường minh `spring.data.couchbase.bucket-name=shop_it`.

**Không trộn nhiều nguồn kết nối mà không biết nguồn nào có hiệu lực.** Nếu một `@DynamicPropertySource` khác cũng đặt connection string hoặc credential, hãy xác định cụ thể config nào đang được dùng và bỏ nguồn dư thừa.

## 6. Cách B: @DynamicPropertySource khi cần tự quản lý connection details

Nếu không dùng `@ServiceConnection` (ví dụ Spring Boot cũ, auto-configuration tùy biến hoặc muốn truyền property tường minh), dùng `@DynamicPropertySource`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest
@Testcontainers
class ExplicitConnectionSliceIT {

    @Container
    static final CouchbaseContainer container =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    @DynamicPropertySource
    static void couchbaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.couchbase.connection-string",
            container::getConnectionString);
        registry.add("spring.couchbase.username",
            container::getUsername);
        registry.add("spring.couchbase.password",
            container::getPassword);
        registry.add("spring.data.couchbase.bucket-name",
            () -> "shop_it");
    }

    @Test
    void contextLoadsWithConfiguredBucket() {
        // Bổ sung repository và round-trip assertion thực tế.
    }
}
~~~

**Đây là một lựa chọn thay thế cho cách A**, không phải bước buộc chạy sau cách A. Sự khác biệt:

| Tiêu chí | `@ServiceConnection` | `@DynamicPropertySource` |
| --- | --- | --- |
| Ai cung cấp connection details? | Spring Boot từ container type | Test tự đăng ký properties |
| Tên bucket `shop_it` | Vẫn cần đặt riêng | Đặt trong registry |
| Tự provision scope/collection? | Không | Không |
| Khi nào tiện? | Boot hỗ trợ service connection chuẩn | Cấu hình đặc thù/cần kiểm soát tường minh |
| Rủi ro | Tin rằng mọi property đã được cấp | Gõ sai property name, quên credential/bucket |

Các property ví dụ tương ứng Spring Boot 3.x: `spring.couchbase.connection-string`, `spring.couchbase.username`, `spring.couchbase.password`, `spring.data.couchbase.bucket-name`. Khi nâng major version, kiểm tra property metadata của Spring Boot đang dùng.

## 7. Provision tài nguyên đúng nơi: bucket khác scope/collection

Trong ứng dụng thật, Order có thể được lưu ở:

~~~text
Bucket:       shop
Scope:        sales
Collection:   orders
Document key: order::125
~~~

Khi chạy Testcontainers, ví dụ kiểm thử có thể dùng:

~~~text
Bucket:       shop_it
Scope:        sales
Collection:   orders
Document key: it::order::<UUID>
~~~

Cùng một chuỗi document key ở `_default._default` và `sales.orders` là **hai document khác nhau**.

### 7.1. Khai báo entity named collection

~~~java
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
@Scope("sales")
@Collection("orders")
public class Order {
    // Các property @Id, @Version, @Field như ví dụ trước.
}
~~~

Nếu bạn đổi entity sang named collection, **test mục 5 cũng phải đổi** đường đọc raw JSON thành:

~~~java
var result = cluster.bucket("shop_it")
    .scope("sales")
    .collection("orders")
    .get(key);
~~~

Không thể dùng test default collection để kết luận cấu hình annotation named collection đã đúng.

### 7.2. Tạo scope và collection bằng SDK management

Ví dụ với Java SDK hiện đại:

~~~java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;

// Chạy trong một fixture setup sở hữu quyền quản trị.
Bucket bucket = cluster.bucket("shop_it");
var manager = bucket.collections();

try {
    manager.createScope("sales");
} catch (ScopeExistsException alreadyExists) {
    // Setup idempotent: scope đã có.
}

try {
    manager.createCollection("sales", "orders");
} catch (CollectionExistsException alreadyExists) {
    // Setup idempotent: collection đã có.
}
~~~

Một số Java SDK đời cũ dùng `CollectionSpec.create("orders", "sales")`; API mới có overload nhận scope/collection theo tên. Chọn theo SDK BOM đang dùng, không phối hợp overload cũ/mới tùy tiện.

**Sau lời gọi create collection thành công, có thể còn độ trễ lan truyền manifest và resource readiness.** Test nên chờ đến khi collection thực sự truy cập được, với timeout có giới hạn, thay vì gọi `Thread.sleep(1000)`.

### 7.3. Thứ tự thiết lập tài nguyên

1. Khởi động container và các service cần thiết.
2. Tạo bucket (ví dụ `BucketDefinition`) và xác nhận đã có thể kết nối.
3. Chờ cluster/bucket ready.
4. Tạo scope, rồi collection.
5. Chờ manifest/collection usable qua SDK.
6. Tạo secondary index cần cho SQL++.
7. Chờ index online.
8. Seed fixture theo key riêng.
9. Chạy test.
10. Cleanup document đã tạo.

Với quyền production, việc tạo scope/collection/index thường do migration/infra quản lý, không do ứng dụng đọc–ghi bình thường tự làm. **Test setup có quyền admin không chứng minh runtime principal production có quyền hợp lệ**. Nên có một suite quyền/SSL riêng khi RBAC/TLS là yêu cầu triển khai.

## 8. Readiness: KV sẵn sàng khác Query/Index sẵn sàng

Một lỗi phổ biến khi viết test:

~~~text
Container started
  -> immediately CREATE INDEX
  -> immediately run repository.findByCustomerId(...)
  -> test sometimes fails
~~~

`Container started` chỉ nói cơ chế Testcontainers xác định container đã đạt điều kiện khởi động của nó. Điều này **không bảo đảm** mọi dịch vụ, collection manifest và index đều sẵn sàng cho mọi thao tác ngay lập tức.

### 8.1. Chờ cluster/bucket

Java SDK cung cấp `waitUntilReady`:

~~~java
import java.time.Duration;

cluster.waitUntilReady(Duration.ofSeconds(60));

cluster.bucket("shop_it")
    .waitUntilReady(Duration.ofSeconds(60));
~~~

Chờ cluster/bucket giúp giảm lỗi bootstrap sớm. Tuy vậy, nó **không thay thế** việc kiểm tra trạng thái index; một index vừa tạo có thể vẫn đang build.

### 8.2. Provision secondary index theo query thực tế

Giả sử method `findByCustomerId` cần query field JSON `customer_id` trong `shop_it.sales.orders`:

~~~sql
CREATE INDEX ix_orders_customer
ON `shop_it`.`sales`.`orders`(customer_id);
~~~

**Index phục vụ truy vấn theo field**, không cần cho `findById(key)` vốn thường dùng KV. Có thể kiểm tra độ phù hợp bằng `EXPLAIN`:

~~~sql
EXPLAIN
SELECT META(o).id AS documentKey, o.customer_id
FROM `shop_it`.`sales`.`orders` AS o
WHERE o.customer_id = "customer::u100";
~~~

Một index chỉ phù hợp nếu query filter/sort thực tế có thể sử dụng nó. Spring Data repository query có thể thêm type predicate, nên **đừng thiết kế index chỉ dựa trên query SDK viết tay mà bỏ qua query của repository**.

### 8.3. Chờ index ONLINE bằng QueryIndexManager

Ví dụ SDK với named scope/collection:

~~~java
import java.time.Duration;
import java.util.List;

import static com.couchbase.client.java.manager.query.WatchQueryIndexesOptions.watchQueryIndexesOptions;

// Sau khi tạo ix_orders_customer qua DDL/setup:
cluster.queryIndexes().watchIndexes(
    "shop_it",
    List.of("ix_orders_customer"),
    Duration.ofSeconds(90),
    watchQueryIndexesOptions()
        .scopeName("sales")
        .collectionName("orders")
);
~~~

Nếu đang dùng API/query index manager phiên bản khác, kiểm tra chính xác overload và location scope/collection. Quan trọng là **poll trạng thái ONLINE có timeout và failure rõ ràng**, không thay bằng một sleep cố định hoặc bỏ qua lỗi index build.

### 8.4. Query visibility sau write

Couchbase KV có thể đọc document mới ngay trước khi secondary index phục vụ SQL++ nhìn thấy mutation. Query từ SDK có thể chọn scan consistency:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
    """
    SELECT META(o).id AS documentKey
    FROM `shop_it`.`sales`.`orders` AS o
    WHERE o.customer_id = $customer
    """,
    queryOptions()
        .parameters(JsonObject.create()
            .put("customer", "customer::u100"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

`REQUEST_PLUS` yêu cầu query đợi index bắt kịp ở mức nhất quán được yêu cầu. Nó giúp kiểm thử read-after-write ổn định hơn, nhưng **có chi phí latency**, và không tự tạo index còn thiếu.

Không dùng `Thread.sleep(3000)` để “chữa” test query bị flaky do index consistency. Xác định đúng cơ chế đang test: `NOT_BOUNDED` hay `REQUEST_PLUS`, index readiness, query service, hoặc lỗi mapping.

## 9. Tổ chức test class để tài nguyên được chia sẻ đúng cách

Testcontainers có thể khởi động container cho từng class hoặc chia sẻ một container cho nhiều class theo một chiến lược xác định. Chia sẻ giúp giảm chi phí bootstrap, nhưng làm tăng rủi ro **test ảnh hưởng lẫn nhau**.

### 9.1. Static @Container trong một class

~~~java
@Testcontainers
@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
class SmallRepositorySliceIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(DockerImageName.parse(
            "couchbase/server:community-7.2.5"))
            .withBucket(new BucketDefinition("shop_it"));

    // Các @Test được chạy cùng container trong class.
}
~~~

Static container thường chạy một lần cho class. Nếu muốn nhiều class cùng dùng một instance, phải quản lý vòng đời và Spring context cache **một cách tường minh**; đừng để container đã dừng nhưng Spring context cache vẫn giữ connection details của container cũ.

### 9.2. Không dùng dataset chung không có namespace

Các test này có thể đụng nhau:

~~~java
repository.save(new Order("order::125", "customer::u100", 100000));
repository.save(new Order("order::125", "customer::u200", 200000));
~~~

Khi chạy song song, một test có thể ghi đè dữ liệu của test khác hoặc gặp CAS conflict. Nên dùng:

~~~java
String key = "it::order::" + UUID.randomUUID();
~~~

Tách thêm keyspace nếu cần nhiều test suite chạy song song với dữ liệu lớn hoặc index khác nhau. Không nên dùng `deleteAll()` trên một collection dùng chung vì có thể xóa fixture của test khác.

### 9.3. Cleanup theo key ở cuối test

~~~java
String key = "it::order::" + UUID.randomUUID();

try {
    // setup, execute, assertions...
} finally {
    repository.deleteById(key);
}
~~~

Nếu test có thể thất bại **trước khi insert**, cleanup cần xử lý trường hợp key chưa tồn tại theo API đang dùng; có thể kiểm tra `existsById` hoặc dùng cơ chế xóa chấp nhận not-found. Không che một lỗi kiểm thử thực bằng một exception từ cleanup.

Một số dự án chọn tạo **bucket/collection riêng mỗi test suite** rồi drop sau suite; việc này đắt hơn và cần quyền quản trị, nhưng tăng isolation. Phải chọn chiến lược có thể chạy được trong CI với tài nguyên thực tế.

## 10. Kiểm chứng mapping bằng SDK độc lập với Spring Data

Một round-trip repository đơn thuần có thể bỏ sót lỗi nếu cả writer và reader đều áp cùng một mapping sai.

Ví dụ developer viết nhầm:

~~~java
@Field("total_amout_vnd") // Sai chính tả.
private long totalAmountVnd;
~~~

`repository.save` rồi `repository.findById` có thể trả lại đúng `350000`, vì hai chiều cùng dùng tên JSON sai. Một mock càng không phát hiện lỗi này.

Để test hợp đồng JSON, sau khi save phải đọc body bằng SDK:

~~~java
String key = "it::order::" + UUID.randomUUID();

try {
    orders.save(new Order(key, "customer::u100", 350000));

    var json = cluster.bucket("shop_it")
        .scope("sales").collection("orders")
        .get(key).contentAsObject();

    assertEquals(350000L, json.getLong("total_amount_vnd"));
    assertFalse(json.containsKey("total_amout_vnd"));
    assertFalse(json.containsKey("id"));
} finally {
    orders.deleteById(key);
}
~~~

Ví dụ trên **giả định đã dùng named collection** và chưa cấu hình ghi ID vào body. Nếu custom converter chủ động lưu `id`, hãy chỉnh expectation theo hợp đồng thực; `@Id` theo mặc định là Couchbase key, không đồng nghĩa field JSON `id`.

### 10.1. Kiểm thử chiều ngược: SDK chèn JSON, repository đọc

~~~java
var collection = cluster.bucket("shop_it")
    .scope("sales").collection("orders");

String key = "it::legacy::" + UUID.randomUUID();

try {
    collection.insert(key, JsonObject.create()
        .put("customer_id", "customer::u100")
        .put("total_amount_vnd", 0L)
        .put("status", "DRAFT"));

    Order reloaded = orders.findById(key).orElseThrow();
    assertEquals("customer::u100", reloaded.getCustomerId());
    assertEquals(0L, reloaded.getTotalAmountVnd());
} finally {
    orders.deleteById(key);
}
~~~

Đây là phép kiểm chứng dữ liệu do SDK/import/ứng dụng cũ tạo ra. Nếu mapping phụ thuộc `_class`, nested polymorphism hoặc converter đặc thù, fixture phải thêm thông tin cần thiết hoặc test phải xác nhận **lỗi có chủ đích** khi thiếu.

## 11. Các trường hợp mock không thể thay thế test với server

| Ngữ nghĩa | Dùng mock có thể kiểm tra | Bằng chứng phải lấy ở Testcontainers/cluster |
| --- | --- | --- |
| **KV insert** | Service xử lý “duplicate” exception như thế nào | `insert` thật từ chối key đã tồn tại |
| **KV replace/upsert** | Service chọn thao tác và xử lý lỗi | Ghi đúng document, CAS/overwrite semantics |
| **`@Id`** | Code truyền đúng key | Key nằm ở metadata, không lấy body.`id` |
| **`@Field`** | Chỉ kiểm tra annotations bằng reflection | JSON thật có đúng field names |
| **Repository query** | Service xử lý list kết quả | SQL++ đúng, index có, mapper đọc kết quả |
| **CAS `@Version`** | Service retry/HTTP 409 khi được stub conflict | Hai snapshot cũ ghi cạnh tranh thực sự conflict |
| **TTL** | Service truyền policy expiry | Document thật hết hạn theo thời gian server |
| **Transaction** | Nhánh xử lý khi dependency báo lỗi | Nhiều document commit/abort theo semantics thực |
| **Sub-document** | Tạo đúng API arguments | Atomicity theo document, JSON path/array behaviors |
| **Durability** | Chính sách chọn durability level | Server topology/quorum nhận và thực thi request |
| **Reactive** | Xử lý publisher được stub | Publisher kết nối, query, error, cancellation thật |

`@DataCouchbaseTest` **chỉ hỗ trợ tầng tích hợp**, không tự thay thế nhu cầu viết các test chuyên biệt cho từng ngữ nghĩa. Một test round-trip `findById` không phải test transaction hay index.

## 12. Test CAS: cùng key, hai snapshot độc lập

Nếu entity có `@Version Long cas`, Spring Data Couchbase thường dùng CAS để kiểm soát optimistic locking.

~~~java
@Test
void rejectsSecondWriterWithStaleCas() {
    String key = "it::cas::" + UUID.randomUUID();

    try {
        orders.save(new Order(key, "customer::u100", 100000));

        Order first = orders.findById(key).orElseThrow();
        Order second = orders.findById(key).orElseThrow();

        first.addAmount(50000);
        orders.save(first);

        second.addAmount(20000);

        assertThrows(
            org.springframework.dao.OptimisticLockingFailureException.class,
            () -> orders.save(second)
        );

        Order stored = orders.findById(key).orElseThrow();
        assertEquals(150000L, stored.getTotalAmountVnd());
    } finally {
        orders.deleteById(key);
    }
}
~~~

Test này cần hai entity được materialize **riêng biệt** trước lần ghi đầu tiên. Nếu dùng một reference Java hoặc test stub `save()`, bạn có thể không tạo được stale snapshot.

Không viết assertion “CAS tăng đúng 1”; CAS là metadata opaque token do Couchbase cấp.

### 12.1. Tại sao môi trường một container đủ cho CAS nhưng chưa đủ cho failover?

CAS per-document và các thao tác KV/SQL++ cơ bản có thể test bằng một Couchbase Server đơn node. Nhưng để kiểm tra:

- Replica count và failover;
- Durability levels yêu cầu quorum;
- Rebalance và mất một node;
- Topology/latency vùng mạng;

bạn cần môi trường **nhiều node có cấu hình tương ứng**. Một Testcontainers đơn node không tái hiện đầy đủ môi trường production có replicas.

## 13. Test TTL: thời gian server không phải đồng hồ unit test

Ví dụ Cart có expiry ngắn:

~~~java
@Document(expiry = 5)
public class EphemeralCart {
    @Id
    private String id;
    // Field và constructor phù hợp với mapping.
}
~~~

Khi kiểm thử thật:

1. Tạo document có expiry theo annotation hoặc SDK options.
2. Kiểm tra đọc ngay thấy document.
3. Poll cho tới khi KV không còn tìm thấy document trong timeout hợp lý.
4. Test riêng hành vi **touch on read** và mutation giữ/xóa expiry nếu ứng dụng cần.
5. Kiểm tra bucket/collection maxTTL có ảnh hưởng chính sách hay không.

Ví dụ dùng SDK + Awaitility (dependency test riêng):

~~~java
import java.time.Duration;

String key = "it::ttl::" + UUID.randomUUID();

collection.insert(
    key,
    JsonObject.create().put("type", "temporary"),
    com.couchbase.client.java.kv.InsertOptions.insertOptions()
        .expiry(Duration.ofSeconds(3))
);

assertTrue(collection.exists(key).exists());

await().atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(250))
    .until(() -> !collection.exists(key).exists());
~~~

`Clock.fixed` có thể test logic ngày giờ của business, nhưng **không tua nhanh đồng hồ Couchbase Server**. Không giả định expiry chính xác đến mili-giây.

**Đừng dùng `@Transactional` với kỳ vọng Spring sẽ tự rollback tất cả document sau test như một số test JPA.** Đối với Couchbase, cleanup và transaction cần kiểm chứng theo API/configuration thật.

## 14. Test reactive repository và ReactiveCouchbaseTemplate

Với starter/reactive dependencies phù hợp, `@DataCouchbaseTest` có thể cấu hình reactive template/repositories. Cần xác nhận bean đã được tạo trên version thực tế; không mặc định tất cả app đều có cả blocking và reactive API.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<Order, String> {
}
~~~

Kiểm thử với Reactor `StepVerifier`:

~~~java
String key = "it::rx::" + UUID.randomUUID();

StepVerifier.create(
    reactiveOrders.save(
        new Order(key, "customer::u100", 100000))
        .flatMap(saved -> reactiveOrders.findById(saved.getId()))
)
    .assertNext(order ->
        assertEquals(100000L, order.getTotalAmountVnd()))
    .verifyComplete();

StepVerifier.create(reactiveOrders.deleteById(key))
    .verifyComplete();
~~~

**Mấu chốt:** chỉ tạo `Mono` không có nghĩa I/O đã chạy; phải subscribe hoặc verify. Cleanup reactive cũng cần subscribe, nếu không fixture có thể còn lại.

Bên cạnh happy path, nên test exception từ store, cancellation, retry budget và CAS conflict khi ứng dụng dùng reactive thực tế. `StepVerifier.withVirtualTime` không làm TTL Couchbase hoặc index build chạy nhanh hơn.

## 15. Cấu hình test slice khi project có custom converter và domain service

Một số ứng dụng cấu hình:

- `CouchbaseCustomConversions` và custom reading/writing converter;
- Field naming strategy;
- Type aliases;
- Repository base class riêng;
- Bean `@ConfigurationProperties` dành cho keyspace;
- `@Service` hoặc mapper adapter quản lý logic lưu trữ.

Vì `@DataCouchbaseTest` **không quét mọi bean ứng dụng**, test có thể vô tình chạy với mapper mặc định khác production.

### 15.1. Import cấu hình tối thiểu nhưng đủ

~~~java
@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_it")
@Import(CouchbaseMappingConfiguration.class)
class CustomMappingSliceIT {
    @Autowired OrderRepository orders;
}
~~~

`CouchbaseMappingConfiguration` ở đây là cấu hình **do dự án định nghĩa**, không phải một class mặc định của Spring. Nếu custom converter là thành phần quan trọng, phải chủ động đưa nó vào test slice và dùng fixture JSON độc lập để xác nhận.

Đừng dùng `@Import` bừa bãi toàn bộ cấu hình ứng dụng. Các bean phụ thuộc SMTP/broker/API ngoài có thể biến data slice thành test gần full context, làm tăng độ chậm và flaky.

### 15.2. Khi nào chuyển sang @SpringBootTest?

| Cần xác minh | Đề xuất |
| --- | --- |
| `@Document`, converter, repository, template | `@DataCouchbaseTest` |
| Domain pure function | JUnit thuần, không Spring |
| Service đơn lẻ phụ thuộc repo | Unit test với mock/port |
| Service + Couchbase + custom transaction configuration | Có thể dùng `@SpringBootTest` |
| Controller, security, serialization HTTP, event | `@SpringBootTest`/web integration |
| Full workflow qua messaging + database | Integration suite phù hợp từng dependency |

Không có mục tiêu “mọi test đều phải là slice”. Mục tiêu là **mỗi test có phạm vi nhỏ nhất nhưng vẫn thực thi được ngữ nghĩa nó muốn chứng minh**.

## 16. Tài nguyên kiểm thử khi dùng cluster dùng chung thay Testcontainers

Không phải môi trường CI nào cũng cho phép Docker. Có thể dùng một cluster Couchbase test được vận hành riêng, nhưng phải:

- Tách khỏi production ở cấp network, credential và dữ liệu.
- Tạo bucket/scope/collection dành riêng cho test hoặc mỗi pipeline.
- Gắn index và migration theo đúng phiên bản schema đang kiểm thử.
- Có resource quota, timeout, lịch cleanup, và khả năng chạy nhiều job song song.
- Quản lý secret bằng CI secret store; không commit mật khẩu.
- Có quá trình kiểm tra readiness tương đương Testcontainers.
- Không tạo/destroy bucket của pipeline khác.
- Pin phiên bản Server hoặc kiểm thử một ma trận phiên bản có chủ đích.

### 16.1. Tách tên kết nối và bucket theo profile

Ví dụ `application-test.yml` chỉ để minh họa cách **tham số hóa**, không dùng credential thật:

~~~yaml
spring:
  couchbase:
    connection-string: ${TEST_COUCHBASE_CONNECTION_STRING}
    username: ${TEST_COUCHBASE_USERNAME}
    password: ${TEST_COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: ${TEST_COUCHBASE_BUCKET}
~~~

Khi dùng `@ServiceConnection`, connection details của container có thể override các connection properties trên; vẫn cần biết bucket nào được chọn. Tránh có một file test để mặc định sang cluster production nếu biến môi trường vắng mặt; nên **fail fast** hoặc chỉ chạy integration profile khi tài nguyên test được cấp đầy đủ.

### 16.2. Quyền hạn khác nhau giữa setup và runtime

Test fixture provisioning có thể cần quyền quản trị để tạo scope/index. Runtime app production chỉ nên có quyền đọc–ghi phù hợp. Nếu mục tiêu kiểm thử là RBAC, cần một test sử dụng **runtime principal có quyền hẹp** sau khi admin provisioning hoàn tất, không dùng tài khoản admin của Testcontainers để kết luận security đúng.

## 17. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán/khắc phục |
| --- | --- | --- |
| `@DataCouchbaseTest` load context nhưng query lỗi | Không có index/Query Service | Kiểm tra services, DDL và index ONLINE |
| Repo không được inject | Package scan không bao trùm repository | Đặt test gần application package hoặc cấu hình scanning |
| `@Service` không được inject | Slice không quét service thông thường | `@Import` bean mục tiêu hoặc dùng `@SpringBootTest` |
| `CouchbaseTemplate` dùng sai bucket | Quên `spring.data.couchbase.bucket-name` | Kiểm tra property và bucket thực trong test |
| Authentication fails | Container credential không được đưa vào context | Kiểm tra `@ServiceConnection` hoặc `@DynamicPropertySource` |
| App test kết nối cluster ngoài ý muốn | Cấu hình default/local profile rò rỉ | Fail-fast và cô lập test properties |
| KV có document nhưng repository không thấy | Sai scope/collection hoặc entity mapping | So raw SDK và annotation `@Scope`/`@Collection` |
| Chỉ test mặc định pass, production named collection lỗi | Fixture không tạo đúng keyspace | Tạo named resources và sửa đường SDK read |
| Index DDL xong nhưng query vẫn lỗi | Index build chưa ONLINE | Chờ `watchIndexes` hoặc readiness có timeout |
| Query ngay sau save trả rỗng | Index lag/scan consistency | Test `REQUEST_PLUS` khi cần read-after-write |
| Test CAS không conflict | Hai snapshot không độc lập, thiếu `@Version` | Đọc hai lần, kiểm tra CAS metadata |
| TTL test flaky | So thời gian quá chính xác, maxTTL/touch | Poll có timeout và kiểm tra policy expiry |
| Reactive test dường như không chạy | Chưa subscribe publisher | Dùng StepVerifier cho I/O và cleanup |
| Context bị cache dùng container đã stop | Container lifecycle và Spring cache lệch | Quản lý container/context scope rõ |
| Integration tests quá chậm | Mỗi test khởi tạo server/index mới | Chia sẻ theo class/suite có kiểm soát, seed gọn |
| Test song song ảnh hưởng lẫn nhau | Key trùng, `deleteAll`, DDL chồng nhau | Prefix/UUID, namespace/collection riêng, setup idempotent |
| CI xanh dù Docker thiếu | Test integration bị skip | Tạo gate bắt buộc và báo rõ môi trường không chạy |

Đừng chữa mọi lỗi bằng cách tăng timeout. Một lỗi **Index Not Found** hoặc **wrong bucket** không biến thành “đúng” chỉ vì đợi lâu hơn.

## 18. Thiết kế bộ fixture tái sử dụng và mức độ test phù hợp

Một fixture tốt nên có:

1. **Container lifecycle** có chủ sở hữu rõ.
2. **Một nơi tạo bucket/scope/collection/index** với logic idempotent.
3. **Hàm cấp document key riêng** cho mỗi test.
4. **Factory data** tạo JSON V1/V2, null/missing, nested object, document có TTL.
5. **Cleanup** theo key cụ thể; không xóa collection dùng chung.
6. **Readiness** và retry giới hạn có kiểm soát.
7. **Metric/log** cho startup/index, nhưng không in secret hoặc body chứa PII.

Có thể nhóm kiểm thử thành:

| Suite | Tài nguyên cần | Nội dung |
| --- | --- | --- |
| `DomainUnitTest` | Không Couchbase | Validation, tổng tiền, state machine |
| `OrderMappingIT` | KV + converter | `@Field`, `@Id`, `@Version`, raw JSON |
| `OrderRepositoryIT` | KV + Query/Index | findById, query theo customer |
| `OrderCasIT` | KV | Hai snapshot, conflict và bảo toàn dữ liệu |
| `OrderTtlIT` | KV + expiry policy | Đặt TTL và poll hết hạn |
| `OrderReactiveIT` | Reactive repo + KV | Subscription, result/error, cleanup |
| `OrderTransactionIT` | Transactions đúng config | Atomic commit/abort nhiều document |
| `OrderPerformanceIT` | Môi trường gần production | p95/p99, index, hot key, resource limits |

Không cần bật Query/Index Service nếu một suite **chỉ** kiểm tra KV, nhưng khi đã dùng derived repository methods/query cần chúng. Bố trí dịch vụ theo suite có thể giảm chi phí nếu CI đủ phức tạp; không tự tối ưu hạ tầng trước khi đo test startup và số lượng suite.

## 19. Bài thực hành: tạo slice test đúng cho giỏ hàng

**Đề bài:** một ứng dụng thương mại điện tử có entity `Cart`:

~~~text
Bucket:     shop_it
Scope:      sales
Collection: carts
Key:        cart::u100
Fields:     customer_id, lines[], status
TTL:        3600 giây
CAS:        @Version
~~~

Repository:

~~~java
public interface CartRepository
        extends CouchbaseRepository<Cart, String> {

    List<Cart> findByCustomerId(String customerId);
}
~~~

Yêu cầu:

1. Chọn cách cung cấp Couchbase Server và connection details cho slice.
2. Tạo scope `sales`, collection `carts` và index `customer_id`.
3. Viết một test KV + raw JSON mapping.
4. Viết một test SQL++ visibility sau khi ghi.
5. Viết một test CAS hai snapshot và một test TTL.
6. Thiết kế cleanup và chiến lược chạy song song.

### 19.1. Lời giải gợi ý theo thứ tự tài nguyên

~~~mermaid
flowchart TB
    A["CouchbaseContainer + Bucket shop_it"] --> B["@ServiceConnection"]
    B --> C["@DataCouchbaseTest + bucket property"]
    C --> D["createScope sales / createCollection carts"]
    D --> E["CREATE INDEX ix_carts_customer"]
    E --> F["watchIndexes ONLINE"]
    F --> G["Seed test Cart với key UUID"]
    G --> H["KV/SDK/Query/CAS/TTL tests"]
    H --> I["Cleanup theo key"]
~~~

**Mapping:** tạo Cart có key riêng, save bằng repository, đọc lại bằng `findById`, SDK truy vấn JSON tại `shop_it.sales.carts` để kiểm tra `customer_id` và `lines`. Đối chiếu CAS do SDK trả với `@Version` sau khi load.

**SQL++:** tạo index `customer_id` và đợi ONLINE; query sau save với `REQUEST_PLUS` nếu test muốn read-after-write, không sleep cố định.

**CAS:** đọc hai Cart từ cùng CAS, writer A thay đổi số lượng và save, writer B dựa trên bản cũ lưu thì cần bị từ chối; kiểm tra state cuối.

**TTL:** dùng fixture expiry ngắn (không bắt test chờ 3600 giây), theo dõi document biến mất bằng polling. Đừng thay TTL production trong mọi test bằng cấu hình nguy hiểm; dùng entity/tài nguyên chuyên biệt cho expiry test.

**Isolation:** mỗi test tạo `it::cart::<UUID>`, cleanup theo key; collection/index được tạo trong setup chung có quyền admin, không drop resource khi test khác đang chạy.

### 19.2. Bài tập mở rộng — phát hiện cấu hình nhầm collection

Cùng một key `it::cart::a1` được ghi vào:

~~~text
shop_it.sales.carts
shop_it._default._default
~~~

Hãy xác nhận:

- CartRepository được gắn `@Scope("sales")`, `@Collection("carts")` chỉ đọc bản tại `sales.carts`.
- SDK đọc bản default collection nhận nội dung khác.
- Không có test nào “PASS” chỉ vì mock `findById` trả Cart bất kể collection.

### 19.3. Câu hỏi tự kiểm tra

1. **`@DataCouchbaseTest` có tự khởi động Couchbase Server không?** Không.
2. **`@ServiceConnection` có tự tạo bucket/scope/collection/index không?** Không; nó chủ yếu cấp connection details.
3. **Spring Data Couchbase cần property bucket nào trong Boot 3.x?** `spring.data.couchbase.bucket-name`.
4. **Vì sao import `@DataCouchbaseTest` khác giữa Boot 3.x và 4.x?** Cấu trúc module/package của Boot 4 thay đổi.
5. **Dùng `@DataCouchbaseTest` có tự scan mọi `@Service` không?** Không.
6. **`findById` cần secondary index không?** Không, thường là KV theo document key.
7. **Query theo `customer_id` cần gì thêm?** Query/Index Services và index phù hợp.
8. **Sau CREATE INDEX, sleep 1 giây có bảo đảm ONLINE không?** Không; phải chờ/readiness có timeout.
9. **Vì sao query sau save có thể chưa thấy dữ liệu?** Secondary index có thể chưa cập nhật; chọn scan consistency phù hợp.
10. **Test mapping chỉ save rồi findById có đủ không?** Không hẳn; có thể cả hai chiều cùng dùng tên JSON sai. Cần SDK đọc raw body.
11. **Kiểm thử CAS cần mấy snapshot?** Ít nhất hai snapshot độc lập đọc trước mutation.
12. **Dùng `Clock.fixed` có tua nhanh TTL Couchbase không?** Không.
13. **Vì sao không dùng `deleteAll()` trong collection chung?** Có thể xóa fixture của test khác.
14. **Khi nào nên dùng `@SpringBootTest`?** Khi cần nhiều phần của ứng dụng ngoài data slice như controller/service/transaction configuration.
15. **Reactive cleanup có chạy nếu chỉ tạo `Mono<Void>` mà không subscribe không?** Không nên giả định; phải subscribe/verify.
16. **Một container đơn node có chứng minh durability failover nhiều replica không?** Không.

## 20. Checklist triển khai

- [ ] Xác định mục tiêu test: unit, mapping, repository, SQL++, CAS, TTL, transaction hay API.
- [ ] Dùng `@DataCouchbaseTest` cho tầng dữ liệu, không kỳ vọng web/service beans tự hiện diện.
- [ ] Pin Spring Boot/Testcontainers/SDK/Server versions; dùng package/artifacts đúng major.
- [ ] Cung cấp Couchbase Server test cô lập qua Testcontainers hoặc cluster riêng.
- [ ] Chọn một cách cấp connection details: `@ServiceConnection` **hoặc** `@DynamicPropertySource`.
- [ ] Đặt `spring.data.couchbase.bucket-name` tường minh, tránh kết nối nhầm production.
- [ ] Provision đúng bucket, scope, collection và runtime permissions.
- [ ] Chờ cluster, bucket, collection và index sẵn sàng với timeout; không sleep tùy ý.
- [ ] Tạo secondary index chỉ cho workload/query cần, kiểm tra `EXPLAIN` khi quan trọng.
- [ ] So sánh Spring Data save → SDK raw JSON và SDK insert → repository read.
- [ ] Test `@Id` là key, `@Version` là CAS, `@Field` là tên JSON đúng.
- [ ] Dùng `REQUEST_PLUS` hoặc mức consistency phù hợp cho read-after-write SQL++.
- [ ] Test CAS với hai snapshots và trạng thái cuối, không chỉ exception.
- [ ] TTL test bằng polling server time; lưu ý maxTTL/touch/preserve expiry.
- [ ] Đăng ký custom converter/bean có ảnh hưởng đến mapping nếu slice không tự quét.
- [ ] Reactive tests phải subscribe I/O và cleanup.
- [ ] Dùng UUID/namespace riêng, cleanup theo key, tránh `deleteAll()` trong dataset chung.
- [ ] Chỉ dùng `@SpringBootTest` khi phạm vi test cần nhiều bean/tích hợp rộng hơn.
- [ ] CI bảo đảm container runtime, tài nguyên, timeouts và báo rõ test bị skip.
- [ ] Không coi container đơn node là bằng chứng cho multi-node resilience/failover.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test slice `@DataCouchbaseTest` trên Boot 3.x và scope bean được auto-configure.
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): module `spring-boot-data-couchbase-test` và package annotation mới.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và `CouchbaseConnectionDetails`.
- [Spring Boot — Couchbase Configuration](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html): `spring.couchbase.*` và `spring.data.couchbase.bucket-name`.
- [Testcontainers for Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer`, `BucketDefinition`, modules và phiên bản.
- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): quản lý scope/collection/query index và `watchIndexes`.
- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): `waitUntilReady` cho cluster/bucket.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Field`, `@Id`, `@Version`, constructor/converter.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD, query và repository mapping.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryOptions`, parameters và scan consistency.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): xác minh reactive publishers.
