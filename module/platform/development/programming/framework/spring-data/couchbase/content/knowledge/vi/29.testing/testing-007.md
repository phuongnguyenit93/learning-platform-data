# Kiểm thử CRUD, truy vấn dẫn xuất và @Query trên dữ liệu thực trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây dựng **integration test với Couchbase Server thật** cho `save`, `findById`, `existsById`, `deleteById` và cập nhật entity qua Spring Data Couchbase.
2. Phân biệt rõ **Key-Value (KV) operations theo document key** và **SQL++ queries theo JSON field**; chuẩn bị secondary index cho từng truy vấn tương ứng.
3. Kiểm tra phương thức truy vấn dẫn xuất như `findByCustomerIdAndStatusOrderByCreatedAtAsc` trên **tập dữ liệu có kiểm soát**.
4. Viết và test `@Query` dùng `#{#n1ql.selectEntity}`, `#{#n1ql.filter}`, tham số positional `$1`/`$2` hoặc named `@Param` một cách an toàn.
5. Chứng minh ánh xạ `@Id`, `@Field`, `@Scope`, `@Collection` và `@Version` bằng cách đối chiếu với JSON body và CAS từ Couchbase Java SDK.
6. Điều khiển query consistency qua `@ScanConsistency` hoặc SDK `QueryOptions` để tránh test flaky ngay sau khi seed.
7. Viết test âm tính, biên, sắp xếp, pagination, dữ liệu thiếu/null, optimistic locking, reactive và cleanup an toàn.
8. Tổ chức bộ test trong CI sao cho kết quả không phụ thuộc Docker host port, dữ liệu sót, thứ tự JUnit hoặc index chưa sẵn sàng.

Chủ đề nằm trong chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate` và SQL++, cùng mô hình bucket/scope/collection, chỉ mục, TTL, CAS, transaction và API reactive. Mục tiêu không phải test một mock repository trả dữ liệu theo kịch bản dựng sẵn, mà là **xác minh hợp đồng giữa Java code và Couchbase đang thực thi**.

> **Trục kiểm thử:** CRUD theo ID chủ yếu dùng KV; truy vấn theo field/`@Query` dùng SQL++ và index; test viết–đọc entity cần thêm raw JSON check để phát hiện hai chiều mapping cùng sai.

## 1. Bốn câu hỏi mà một bộ test dữ liệu phải trả lời

Khi một Order được tạo, cập nhật, tìm kiếm rồi xóa, bộ test cần trả lời những câu hỏi độc lập:

| Câu hỏi | Đường code cần chạy | Lỗi mà mock thường bỏ sót |
| --- | --- | --- |
| Có lưu được document vào key đúng? | Repository → Converter → SDK KV → Server | Sai keyspace, sai ID, dữ liệu không được lưu |
| Có đọc JSON về entity đúng? | SDK KV → Converter → Repository | Sai tên `@Field`, type hint, constructor |
| Query theo customer/status chạy đúng? | Spring Data query creator → SQL++ → Index → Converter | Query sai cú pháp/index, type filter, projection |
| Có bảo vệ update/delete khi cạnh tranh không? | Spring Data CAS/Version → SDK KV → Server | Lost update, CAS cũ bị ghi đè |

~~~mermaid
flowchart TD
    A["JUnit 5 integration test"] --> B["Spring Data repository"]
    B --> C{"Loại thao tác?"}
    C -->|"save/findById/deleteById"| D["KV theo document key"]
    C -->|"findBy... / @Query"| E["SQL++ Query Service"]
    E --> F["Secondary index"]
    D --> G["Couchbase Server"]
    F --> G
    H["Raw SDK JSON + CAS assertion"] --> G
~~~

**Không gọi một test chỉ `when(repository.findById(...)).thenReturn(...)` là test CRUD Couchbase.** Nó hữu ích cho tầng service nhưng không chạm server, không kiểm chứng JSON hay index.

### 1.1. Ma trận phạm vi

| Kiểm thử | Unit/mock | Couchbase thật |
| --- | --- | --- |
| Business rule không chấp nhận amount âm | Tốt | Không bắt buộc |
| Service chuyển not-found thành HTTP 404 | Tốt | Không bắt buộc |
| `save` ghi field `amount_vnd` | Không | Có |
| `findById` đúng `sales.orders` | Không | Có |
| `findByCustomerId` có dữ liệu mới ghi | Không | Có + scan consistency |
| `@Query` phân giải SpEL/param đúng | Không | Có + Query Service/index |
| `@Version` phát hiện CAS conflict | Chỉ stub được nhánh xử lý | Có |
| TTL/multi-document transaction | Chỉ test policy | Có + setup chuyên biệt |

## 2. Môi trường kiểm thử: pin version và tạo tài nguyên riêng

Ví dụ trong bài dùng **Java 17+, Spring Boot 3.5.x, Testcontainers 1.x và Couchbase Java SDK 3.x**. Với Spring Boot 4.x/Testcontainers 2.x, đổi artifact/package theo bảng, không trộn hai major versions.

| Thành phần | Boot 3.x / Testcontainers 1.x | Boot 4.x / Testcontainers 2.x |
| --- | --- | --- |
| Data starter | `spring-boot-starter-data-couchbase` | Starter tương ứng |
| Test slice | `org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest` | `org.springframework.boot.data.couchbase.test.autoconfigure.DataCouchbaseTest` |
| Boot test dependencies | `spring-boot-starter-test` | `spring-boot-starter-data-couchbase-test` hoặc module test tương ứng |
| Testcontainers Couchbase | `org.testcontainers:couchbase` | `org.testcontainers:testcontainers-couchbase` |
| Testcontainers JUnit | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| Boot Testcontainers support | `spring-boot-testcontainers` | `spring-boot-testcontainers` |

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:couchbase'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Image Couchbase được pin **theo dự án**, ví dụ:

~~~java
DockerImageName image =
    DockerImageName.parse("couchbase/server:community-7.2.5");
~~~

Tag này chỉ để minh họa và cần được thay bằng phiên bản Server nằm trong ma trận tương thích SDK/production. Không dùng `latest` trong integration regression suite.

### 2.1. Tài nguyên trong bài

~~~text
Bucket:       shop_it
Scope:        sales
Collection:   orders
Index:        ix_orders_customer_status_created
Document key: it::<runId>::order::draft-a
              it::<runId>::order::draft-b
              it::<runId>::order::confirmed-c
              it::<runId>::order::other-d
~~~

Tài nguyên này **không nằm trong database production**. Mỗi test tạo `runId` hoặc namespace riêng để tránh trùng keys khi chạy song song.

~~~mermaid
flowchart TB
    A["CouchbaseContainer(shop_it)"] --> B["Create sales.orders"]
    B --> C["CREATE INDEX + watch ONLINE"]
    C --> D["Seed Order fixtures"]
    D --> E["CRUD/KV tests"]
    D --> F["Derived queries"]
    D --> G["@Query tests"]
    E --> H["Cleanup owned keys"]
    F --> H
    G --> H
~~~

## 3. Entity mẫu: OrderDocument với key, mapping và CAS

Ta lưu Order của khách hàng. Các field có tên vật lý dạng snake_case, còn Java property dùng camelCase.

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

    public void changeAmount(long newAmount) {
        if (!"DRAFT".equals(status) || newAmount < 0) {
            throw new IllegalStateException("Không thể đổi tiền");
        }
        amountVnd = newAmount;
    }
}
~~~

**Lưu ý mapping:**

- `@Id` dùng **document key** tại `shop_it.sales.orders`, không mặc định lưu một JSON field `id`.
- `@Version Long cas` liên kết với **CAS metadata** do Couchbase Server cấp; nó không phải JSON `version`.
- `@Field("customer_id")` đổi tên Java property `customerId` thành JSON key `customer_id`.
- `@Scope` và `@Collection` trỏ tới resource được fixture tạo; tên key `order::...` không tự chọn collection.
- `createdAt` được lưu chuỗi UTC ISO-8601 chỉ để fixture sort dễ dự đoán; với production nên chọn `Instant`/converter và test riêng.

Body JSON kỳ vọng sau khi lưu:

~~~json
{
  "_class": "com.example.shop.sales.OrderDocument",
  "customer_id": "customer::u100",
  "status": "DRAFT",
  "amount_vnd": 150000,
  "created_at": "2026-01-15T08:00:00Z"
}
~~~

`_class` có thể khác nếu dùng `@TypeAlias` hoặc custom type mapper. Không hardcode class name này vào tất cả test nếu việc đổi alias là một phần cấu hình có chủ đích.

## 4. Repository: CRUD, derived query và @Query

Spring Data repository bao gồm các method CRUD theo key; ta khai báo thêm phương thức truy vấn dựa trên tên và custom SQL++.

~~~java
package com.example.shop.sales;

import java.util.List;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.ScanConsistency;
import org.springframework.data.repository.query.Param;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    // Derived query: Java property names, mapper đổi sang JSON field names.
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument>
    findByCustomerIdAndStatusOrderByCreatedAtAsc(
        String customerId, String status);

    // Inline SQL++: JSON field names là customer_id, amount_vnd.
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND customer_id = $1 AND status = $2 " +
           "AND amount_vnd >= $3 ORDER BY created_at ASC")
    List<OrderDocument> findAtLeastAmount(
        String customerId, String status, long minimumAmount);

    // Named parameters là một phương án THAY THẾ positional parameters.
    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND customer_id = $customer AND status = $state " +
           "ORDER BY created_at ASC")
    List<OrderDocument> findByNamedParameters(
        @Param("customer") String customerId,
        @Param("state") String status);
}
~~~

**Ba nhóm method khác nhau:**

| Method | Spring Data thực thi chủ yếu qua | Tài nguyên cần |
| --- | --- | --- |
| `save`, `findById`, `existsById`, `deleteById` | KV theo ID | KV service, collection |
| `findByCustomerIdAndStatusOrderByCreatedAtAsc` | SQL++ do Spring Data tạo | Query/Index Services và index |
| `findAtLeastAmount`, `findByNamedParameters` | SQL++ từ `@Query` | Query/Index Services, correct projection/type filter |

### 4.1. Tại sao @Query dùng hai SpEL macro?

`#{#n1ql.selectEntity}` tạo phần SELECT/FROM phù hợp để Spring Data **dựng lại entity đầy đủ**, bao gồm metadata cần thiết như document ID và CAS. `#{#n1ql.filter}` thêm điều kiện phân biệt entity type theo type metadata.

Mẫu:

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
       "AND customer_id = $1")
List<OrderDocument> findOneCustomer(String customerId);
~~~

Tài liệu Spring Data Couchbase khuyến nghị dùng hai SpEL macro này cho inline query trả **full entity**. Nếu viết raw `SELECT customer_id, amount_vnd FROM ...` rồi trả `OrderDocument`, có thể thiếu ID/CAS/`_class` và gây lỗi materialization hoặc hành vi update không đúng.

Trong Spring Data Couchbase hiện đại còn có `#{#n1ql.bucket}`, `#{#n1ql.scope}`, `#{#n1ql.collection}` khi cần xây dựng query động theo metadata; đừng hardcode keyspace production vào annotation rồi dùng nó để truy cập test bucket.

### 4.2. Positional và named parameters

**Positional**:

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
       "AND customer_id = $1 AND status = $2")
List<OrderDocument> findPositional(String customerId, String status);
~~~

**Named**:

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
       "AND customer_id = $customer AND status = $state")
List<OrderDocument> findNamed(
    @Param("customer") String customerId,
    @Param("state") String status);
~~~

**Không trộn `$1` và `$state` trong cùng một inline query.** Hai cách đều được Spring Data hỗ trợ, nhưng việc phối hợp có thể gây `IllegalArgumentException`. Giá trị được binding thành parameter; không nối trực tiếp input của user thành SQL++ string.

### 4.3. @ScanConsistency giải quyết read-after-write thế nào?

Repository SQL++ thường mặc định mức `NOT_BOUNDED`: index có thể chưa phản ánh mutation vừa ghi. `@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)` yêu cầu Query Service chờ index đủ mới theo request, đổi lại có thể tăng latency.

Tại sao test có annotation này? Bởi bài kiểm thử cần assert **sau khi seed vừa ghi**, SQL++ phải đọc được dữ liệu. Không phải mọi production query cũng nên dùng `REQUEST_PLUS`: hãy chọn theo yêu cầu consistency/latency của workload, và test cả chế độ production khi cần.

## 5. Chuẩn bị container, named collection và index

Ví dụ một Spring Boot 3.x slice test:

~~~java
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.BeforeAll;
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
class OrderRepositoryIT {

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
    @Autowired OrderRepository orders;

    @BeforeAll
    void provisionKeyspace() {
        // Implement ensureScope/ensureCollection/createIndex/wait như mục 6.
    }
}
~~~

`@ServiceConnection` cấp endpoint/credentials, nhưng **không tạo scope, collection hoặc index**. Nếu dùng `@DynamicPropertySource` thay thế, phải đăng ký `spring.couchbase.connection-string`, `username`, `password` và `spring.data.couchbase.bucket-name` từ cùng container.

`@DataCouchbaseTest` cũng **không tự khởi chạy Couchbase Server** hoặc scan mọi service/controller. Với test service + repository + HTTP, cân nhắc `@SpringBootTest`; với repository mapping/query, slice thường là phù hợp.

### 5.1. Chuỗi thiết lập tài nguyên

~~~mermaid
flowchart TD
    A["JUnit starts CouchbaseContainer"] --> B["Spring connection details"]
    B --> C["Cluster/Bucket.waitUntilReady"]
    C --> D["ensureScope sales"]
    D --> E["ensureCollection orders"]
    E --> F["Create secondary index"]
    F --> G["watchIndexes ONLINE"]
    G --> H["Seed isolated Order documents"]
    H --> I["CRUD / derived / @Query assertions"]
    I --> J["Cleanup owned keys"]
~~~


## 6. Provision scope, collection và secondary index

Dùng Couchbase Java SDK để tạo resource test trong **đúng bucket**.

~~~java
import java.time.Duration;
import java.util.List;

import com.couchbase.client.core.error.ScopeExistsException;
import com.couchbase.client.core.error.CollectionExistsException;
import com.couchbase.client.java.manager.collection.CollectionSpec;
import static com.couchbase.client.java.manager.query.CreateQueryIndexOptions.createQueryIndexOptions;
import static com.couchbase.client.java.manager.query.WatchQueryIndexesOptions.watchQueryIndexesOptions;

cluster.waitUntilReady(Duration.ofSeconds(60));
cluster.bucket("shop_it").waitUntilReady(Duration.ofSeconds(60));

var manager = cluster.bucket("shop_it").collections();

try {
    manager.createScope("sales");
} catch (ScopeExistsException alreadyExists) {
    // Setup idempotent: đúng scope đã có.
}

try {
    manager.createCollection(CollectionSpec.create("orders", "sales"));
} catch (CollectionExistsException alreadyExists) {
    // Collection đã có.
}

var indexes = cluster.queryIndexes();
indexes.createIndex(
    "shop_it",
    "ix_orders_customer_status_created",
    List.of("customer_id", "status", "created_at"),
    createQueryIndexOptions()
        .scopeName("sales")
        .collectionName("orders")
        .ignoreIfExists(true)
);

indexes.watchIndexes(
    "shop_it",
    List.of("ix_orders_customer_status_created"),
    Duration.ofSeconds(90),
    watchQueryIndexesOptions()
        .scopeName("sales")
        .collectionName("orders")
);
~~~

Đây là code minh họa API cluster-level QueryIndexManager trong Couchbase Java SDK 3.x. Những phiên bản SDK mới hơn có thể ưu tiên API `collection.queryIndexes()`; cần đồng nhất với dependency của dự án. `ignoreIfExists(true)` chỉ cho phép setup gọi lại khi index **cùng tên** đã tồn tại; nó **không xác minh index hiện hữu có cùng fields/condition**. Với test migration/index schema, cần kiểm tra metadata qua `getAllIndexes`/`system:indexes` hoặc `EXPLAIN`.

### 6.1. Index được tạo để phục vụ query nào?

SQL++ tương đương của derived method:

~~~sql
SELECT META(o).id AS documentKey,
       o.customer_id, o.status, o.amount_vnd, o.created_at
FROM `shop_it`.`sales`.`orders` AS o
WHERE o.customer_id = $customer
  AND o.status = $state
ORDER BY o.created_at ASC;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_customer_status_created
ON `shop_it`.`sales`.`orders`(
  customer_id,
  status,
  created_at
);
~~~

Hai field đầu phù hợp equality filters; `created_at` có thể giúp sort theo timestamp. Custom `@Query` có thêm điều kiện `amount_vnd >= $3`, nên optimizer vẫn có thể phải fetch/filter sau index scan. **Tính đúng của kết quả không đồng nghĩa index tối ưu**; nếu hiệu năng quan trọng, dùng `EXPLAIN`, dữ liệu đại diện và phân tích query plan.

Không tạo primary index đại trà chỉ để test SQL++ “chạy được”. Điều đó che việc thiếu secondary index mà migration production thực sự cần.

### 6.2. Readiness của collection khác index

`Cluster.waitUntilReady`/`Bucket.waitUntilReady` không tự tạo scope hay index. Collection mới tạo còn có thể cần manifest propagation. Nếu SDK request gặp `CollectionNotFoundException` trong cửa sổ ngay sau khi create, hãy retry **đúng lỗi tạm thời** bằng KV probe có deadline:

~~~java
import java.time.Duration;
import java.time.Instant;
import com.couchbase.client.core.error.CollectionNotFoundException;

var collection = cluster.bucket("shop_it")
    .scope("sales").collection("orders");

Instant deadline = Instant.now().plusSeconds(30);

while (true) {
    try {
        collection.exists("it::readiness::probe");
        break;
    } catch (CollectionNotFoundException notReady) {
        if (Instant.now().isAfter(deadline)) {
            throw new IllegalStateException(
                "sales.orders chưa usable", notReady);
        }
        try {
            Thread.sleep(200);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Đã ngắt khi chờ", ex);
        }
    }
}
~~~

`Thread.sleep(200)` ở đây chỉ giãn cách **giữa các lần probe có điều kiện**, không phải một lệnh sleep cố định rồi coi hệ thống đã sẵn sàng. Với permission, authentication, sai bucket hoặc Query Service không bật, phải **fail fast**.

### 6.3. Vòng đời và isolation

- `static @Container` thường được JUnit extension quản lý một lần cho class.
- Index/scope/collection có thể được chia sẻ trong class, nhưng test methods cần keys riêng.
- Không `deleteAll()` trong collection dùng chung khi test song song.
- Spring TestContext cache có thể giữ Spring `Cluster` kết nối container đã dừng nếu nhiều test classes cấu hình lifecycle không phù hợp; cần quản lý context/container thống nhất.
- Dùng `@DirtiesContext` có chủ đích, không thêm vô điều kiện làm mọi test chậm.

## 7. Fixture tái lập: logical IDs ổn định, physical keys duy nhất

Một dataset ít nhưng rõ ràng có giá trị hơn hàng trăm document không kiểm soát.

| Logical ID | Customer | Status | amount_vnd | created_at |
| --- | --- | --- | ---: | --- |
| `draft-a` | u100 | DRAFT | 150000 | 2026-01-15T08:00:00Z |
| `draft-b` | u100 | DRAFT | 250000 | 2026-01-15T09:00:00Z |
| `confirmed-c` | u100 | CONFIRMED | 400000 | 2026-01-15T10:00:00Z |
| `other-d` | u200 | DRAFT | 100000 | 2026-01-15T11:00:00Z |

Để các test query theo customer không lẫn nhau, **cả customer ID của fixture cũng có runId riêng**, không chỉ document key.

~~~java
import java.util.List;
import java.util.UUID;

String runId = UUID.randomUUID().toString();
String prefix = "it::" + runId + "::order::";
String customerA = "customer::it::" + runId + "::u100";
String customerB = "customer::it::" + runId + "::u200";

List<OrderDocument> sample = List.of(
    new OrderDocument(prefix + "draft-a", customerA, "DRAFT",
        150000, "2026-01-15T08:00:00Z"),
    new OrderDocument(prefix + "draft-b", customerA, "DRAFT",
        250000, "2026-01-15T09:00:00Z"),
    new OrderDocument(prefix + "confirmed-c", customerA, "CONFIRMED",
        400000, "2026-01-15T10:00:00Z"),
    new OrderDocument(prefix + "other-d", customerB, "DRAFT",
        100000, "2026-01-15T11:00:00Z")
);
~~~

**Tái lập nghĩa là expected values ổn định**, còn namespace có thể thay đổi để bảo vệ isolation. Những test dùng `Instant.now()`, random status hoặc random amount mà không ghi seed dễ trở nên flaky.

### 7.1. Seed bằng repository hay SDK?

| Mục tiêu kiểm thử | Seed phù hợp |
| --- | --- |
| Derived query trên dữ liệu ứng dụng ghi | Repository `save`, bảo đảm type metadata phù hợp |
| JSON body mapping contract | Spring Data `save` rồi SDK đọc raw JSON |
| Reader tương thích dữ liệu legacy | SDK `insert` raw JSON rồi Spring Data `findById` |
| Duplicate key semantics | SDK `insert` và assert DocumentExists |
| CAS conflict | Ghi rồi đọc hai snapshots từ repository thật |
| TTL | SDK mutation với expiry hoặc entity TTL |
| SQL++ thuần không phụ thuộc entity type | SDK raw JSON và query có tham số |

**Đừng mặc định mọi document raw SDK thiếu `_class` sẽ xuất hiện trong derived query của Spring Data.** Framework có thể thêm type predicate để phân biệt entity, trong khi raw SQL++ chỉ lọc theo JSON field.

### 7.2. Fixture phải sở hữu những key nó tạo

Trong test thực tế có thể đăng ký key **trước khi save** để dọn được cả khi thao tác server thành công nhưng client bị timeout trước khi nhận response:

~~~java
List<String> ownedKeys = new ArrayList<>();

try {
    for (OrderDocument order : sample) {
        ownedKeys.add(order.getId());
        orders.save(order);
    }

    // ... assertions ...
} finally {
    for (String key : ownedKeys) {
        if (orders.existsById(key)) {
            orders.deleteById(key);
        }
    }
}
~~~

Code trên là mẫu đơn giản; trong hệ thống có khả năng network lỗi lúc cleanup, nên giữ primary test failure và báo cleanup failure riêng thay vì che kết quả. Khi reactive, publisher cleanup phải được subscribe. Không xóa toàn collection khi chỉ cần dọn vài keys.

## 8. Kiểm thử CREATE: save rồi xác minh KV và raw JSON

~~~java
@Test
void createsOrderWithCorrectKeyAndJson() {
    String key = "it::" + UUID.randomUUID() + "::order::create";

    try {
        OrderDocument created = orders.save(
            new OrderDocument(
                key, "customer::u100", "DRAFT",
                150000L, "2026-01-15T08:00:00Z"));

        assertEquals(key, created.getId());
        assertTrue(orders.existsById(key));

        OrderDocument loaded = orders.findById(key).orElseThrow();
        assertEquals("customer::u100", loaded.getCustomerId());
        assertEquals(150000L, loaded.getAmountVnd());

        var raw = cluster.bucket("shop_it")
            .scope("sales")
            .collection("orders")
            .get(key);

        assertEquals("customer::u100",
            raw.contentAsObject().getString("customer_id"));
        assertEquals(150000L,
            raw.contentAsObject().getLong("amount_vnd"));
        assertFalse(raw.contentAsObject().containsKey("id"));
        assertNotEquals(0L, raw.cas());
    } finally {
        if (orders.existsById(key)) orders.deleteById(key);
    }
}
~~~

Test này kiểm tra **hai đường đọc độc lập**: repository đọc thành Java object và SDK đọc body JSON. Nếu `@Field("amount_vnd")` bị gõ sai thành `@Field("amount_vd")`, một round-trip qua repository có thể vẫn PASS; raw JSON assertion sẽ phát hiện.

### 8.1. @Id không phải body.id

Couchbase định danh document bằng **key tại collection**, ví dụ:

~~~text
shop_it.sales.orders / it::<runId>::order::create
~~~

Không tự thêm `"id":key` vào fixture JSON chỉ vì Java entity có `@Id`. Nếu có custom converter chủ động ghi `id` vào body, điều chỉnh test theo hợp đồng riêng; đừng hiểu giá trị `@Id` mặc định là một JSON property.

### 8.2. @Version dùng CAS metadata

`@Version` trong Spring Data Couchbase thể hiện CAS token. Kiểm tra:

- Sau khi lưu/đọc, entity có CAS được mapping nếu cấu hình hỗ trợ đúng.
- SDK `GetResult.cas()` khác zero.
- Khi mutation xảy ra, CAS mới khác CAS cũ.
- **Không assert CAS tăng đúng 1**: CAS là opaque token, không phải bộ đếm liên tiếp.

## 9. Kiểm thử READ: tìm theo key có và không có

~~~java
@Test
void readsExistingAndMissingKeys() {
    String id = "it::" + UUID.randomUUID() + "::order::read";
    String missing = "it::" + UUID.randomUUID() + "::order::absent";

    try {
        orders.save(new OrderDocument(id, "customer::u100", "DRAFT",
            50000L, "2026-01-15T08:00:00Z"));

        assertTrue(orders.findById(id).isPresent());
        assertTrue(orders.findById(missing).isEmpty());

        assertTrue(orders.existsById(id));
        assertFalse(orders.existsById(missing));
    } finally {
        if (orders.existsById(id)) orders.deleteById(id);
    }
}
~~~

**Không đưa `null` vào `findById` rồi mong `Optional.empty()`.** Spring Data repository có thể từ chối null ID bằng argument validation; đó là một contract khác. Hãy test missing key bằng **chuỗi ID hợp lệ không tồn tại**.

### 9.1. Cùng key ở collection khác không được đọc lẫn

Nếu cùng `id` tồn tại tại `_default._default` và `sales.orders`, repository có `@Scope("sales")`/`@Collection("orders")` chỉ được làm việc với `sales.orders`.

Kiểm tra bằng SDK chèn hai JSON khác nhau vào hai collections và đọc qua repository. Điều này bắt lỗi mapping keyspace mà mock `findById` không thấy.

## 10. Kiểm thử UPDATE và optimistic locking

Khi entity có `@Version`:

~~~java
@Test
void updatesOneDocumentAndKeepsCasInvariant() {
    String key = "it::" + UUID.randomUUID() + "::order::update";

    try {
        orders.save(new OrderDocument(key, "customer::u100", "DRAFT",
            100000L, "2026-01-15T08:00:00Z"));

        OrderDocument first = orders.findById(key).orElseThrow();
        Long previousCas = first.getCas();

        first.changeAmount(130000L);
        orders.save(first);

        OrderDocument after = orders.findById(key).orElseThrow();
        assertEquals(130000L, after.getAmountVnd());
        assertNotEquals(previousCas, after.getCas());
    } finally {
        if (orders.existsById(key)) orders.deleteById(key);
    }
}
~~~

Test này chứng minh cập nhật có hiệu lực ở server và metadata thay đổi. Đừng dựa vào Java object cũ để kết luận state đã được persist.

### 10.1. Hai writers phải xuất phát từ hai snapshots

~~~java
@Test
void rejectsStaleWriterInsteadOfLosingUpdate() {
    String id = "it::" + UUID.randomUUID() + "::order::cas";

    try {
        orders.save(new OrderDocument(id, "customer::u100", "DRAFT",
            100000L, "2026-01-15T08:00:00Z"));

        OrderDocument writerA = orders.findById(id).orElseThrow();
        OrderDocument writerB = orders.findById(id).orElseThrow();

        writerA.changeAmount(120000L);
        orders.save(writerA);

        writerB.confirm();

        assertThrows(
            org.springframework.dao.OptimisticLockingFailureException.class,
            () -> orders.save(writerB));

        OrderDocument stored = orders.findById(id).orElseThrow();
        assertEquals(120000L, stored.getAmountVnd());
        assertEquals("DRAFT", stored.getStatus());
    } finally {
        if (orders.existsById(id)) orders.deleteById(id);
    }
}
~~~

Vì cả hai writers ban đầu có cùng CAS, writer B không được ghi đè thay đổi writer A. Nếu test chỉ mock `save` để ném `OptimisticLockingFailureException` thì mới chứng minh **service xử lý exception**, chưa chứng minh cơ chế CAS thật hoạt động.

### 10.2. Retry đúng khi gặp conflict

Sai:

~~~java
for (int retry = 0; retry < 3; retry++) {
    repository.save(staleOrder); // Vẫn dùng CAS cũ!
}
~~~

Đúng về nguyên tắc:

1. Bắt lỗi CAS/optimistic locking theo loại có thể retry.
2. Đọc lại Order mới nhất.
3. Kiểm tra lại trạng thái/invariant domain.
4. Tính lại cập nhật trên snapshot mới, không dùng stale object.
5. Ghi lại với retry budget/backoff/idempotency phù hợp.

Đây là policy nghiệp vụ có thể unit test bằng mock, còn **CAS detection** cần ít nhất một integration test trên Couchbase thực.

## 11. Kiểm thử DELETE: xóa đúng key và xác nhận không tồn tại

~~~java
@Test
void deletesByIdAndDoesNotTouchOtherOrders() {
    String idA = "it::" + UUID.randomUUID() + "::order::delete-a";
    String idB = "it::" + UUID.randomUUID() + "::order::keep-b";

    try {
        orders.save(new OrderDocument(idA, "customer::u100", "DRAFT",
            100000L, "2026-01-15T08:00:00Z"));
        orders.save(new OrderDocument(idB, "customer::u100", "DRAFT",
            200000L, "2026-01-15T09:00:00Z"));

        orders.deleteById(idA);

        assertFalse(orders.existsById(idA));
        assertTrue(orders.findById(idA).isEmpty());

        assertTrue(orders.existsById(idB));
        assertEquals(200000L,
            orders.findById(idB).orElseThrow().getAmountVnd());
    } finally {
        if (orders.existsById(idA)) orders.deleteById(idA);
        if (orders.existsById(idB)) orders.deleteById(idB);
    }
}
~~~

**Không gọi `deleteAll()` để làm cleanup trong collection dùng chung.** `deleteAll` có thể dùng SQL++/scan tùy implementation và xóa document của test khác, gây lỗi không tái lập. Cleanup phải giới hạn trong key do test sở hữu.

### 11.1. Delete với CAS và concurrent delete

Nếu ứng dụng cần xóa có điều kiện không được làm mất cập nhật mới nhất, kiểm tra đúng phương thức repository/SDK có dùng CAS:

- `deleteById` theo key và `delete(entity)` có thể có ngữ nghĩa concurrency khác; kiểm tra theo version Spring Data đang dùng.
- SDK `remove` với `RemoveOptions.cas(expectedCas)` cho phép test xóa có điều kiện.

## 12. Test derived query trên tập dữ liệu thật

Spring Data Couchbase có thể suy câu SQL++ từ method name:

~~~java
@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<OrderDocument> findByCustomerIdAndStatusOrderByCreatedAtAsc(
    String customerId, String status);
~~~

Tên property trong Java là `customerId`, `createdAt`, nhưng JSON body lưu `customer_id` và `created_at`. Test phải xác minh **Spring Data Query Creator hiểu đúng mapping `@Field`**.

### 12.1. Test đầy đủ: đúng bộ lọc, đúng thứ tự, không lẫn khách khác

~~~java
@Test
void derivedQueryFiltersCustomerStatusAndOrdersByTime() {
    String runId = UUID.randomUUID().toString();
    String prefix = "it::" + runId + "::order::";
    String customerA = "customer::it::" + runId + "::u100";
    String customerB = "customer::it::" + runId + "::u200";

    List<OrderDocument> docs = List.of(
        new OrderDocument(prefix + "draft-a", customerA, "DRAFT",
            150000, "2026-01-15T08:00:00Z"),
        new OrderDocument(prefix + "draft-b", customerA, "DRAFT",
            250000, "2026-01-15T09:00:00Z"),
        new OrderDocument(prefix + "confirmed-c", customerA, "CONFIRMED",
            400000, "2026-01-15T10:00:00Z"),
        new OrderDocument(prefix + "other-d", customerB, "DRAFT",
            100000, "2026-01-15T11:00:00Z")
    );

    try {
        docs.forEach(orders::save);

        List<OrderDocument> found =
            orders.findByCustomerIdAndStatusOrderByCreatedAtAsc(
                customerA, "DRAFT");

        assertEquals(
            List.of(prefix + "draft-a", prefix + "draft-b"),
            found.stream().map(OrderDocument::getId).toList());

        assertTrue(
            orders.findByCustomerIdAndStatusOrderByCreatedAtAsc(
                customerB, "CONFIRMED").isEmpty()
        );
    } finally {
        for (OrderDocument doc : docs) {
            if (orders.existsById(doc.getId())) {
                orders.deleteById(doc.getId());
            }
        }
    }
}
~~~

**Những bằng chứng test trên cung cấp:**

- Query Service thực thi query theo tên method.
- Mapping `customerId` → `customer_id` đúng.
- Mapping `createdAt` → `created_at` đúng cho sắp xếp.
- Filter `status` không lấy nhầm Order CONFIRMED.
- Không vô tình trả document của `customerB`.
- `@ScanConsistency(REQUEST_PLUS)` giúp test ổn định khi query ngay sau seed.

**Không thể kết luận index được sử dụng tối ưu chỉ vì kết quả đúng.** Cần `EXPLAIN`, index metadata và dataset đủ đại diện nếu muốn đánh giá kế hoạch thực thi.

### 12.2. Những trường hợp biên nên có

| Tình huống | Fixture | Kỳ vọng |
| --- | --- | --- |
| Customer không có Order | ID hợp lệ chưa seed | Trả list rỗng |
| Status không hợp lệ | `"ARCHIVED_UNKNOWN"` | Không trả bản ghi không khớp |
| Hai Order cùng timestamp | `created_at` trùng | Không suy thứ tự giữa chúng nếu không có tie-breaker |
| Field amount bằng 0 | `amount_vnd:0` | Không loại nhầm vì falsy |
| Field JSON thiếu | Raw document thiếu `customer_id` | Không khớp điều kiện equality |
| JSON null | `customer_id:null` | Khác với MISSING nếu nghiệp vụ phân biệt |
| Sai kiểu | `amount_vnd:"150000"` | Converter/query phải được kiểm tra theo chính sách xử lý sai kiểu |
| Type hint khác | Raw JSON có `_class` khác | Query repository có thể loại theo entity filter |
| Key khác collection | Same ID nằm ở default collection | Repository named collection không đọc lẫn |

Không cần mọi test chạy trong một method lớn; có thể dùng `@Nested` và fixture factories, nhưng giữ từng assertion bám một hợp đồng rõ ràng.

## 13. Test @Query positional parameters trên server thật

Custom query:

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
       "AND customer_id = $1 AND status = $2 " +
       "AND amount_vnd >= $3 ORDER BY created_at ASC")
List<OrderDocument> findAtLeastAmount(
    String customerId, String status, long minimumAmount);
~~~

Các parameter `$1`, `$2`, `$3` được bind **theo thứ tự method parameters**. SQL++ phải dùng **tên field JSON**, không viết `customerId`/`amountVnd` trong query nếu body không có những tên đó.

~~~java
@Test
void inlineQueryBindsAllPositionalParameters() {
    String runId = UUID.randomUUID().toString();
    String prefix = "it::" + runId + "::order::";
    String customerA = "customer::it::" + runId + "::a";

    List<OrderDocument> docs = List.of(
        new OrderDocument(prefix + "low", customerA, "DRAFT",
            150000, "2026-01-15T08:00:00Z"),
        new OrderDocument(prefix + "high", customerA, "DRAFT",
            250000, "2026-01-15T09:00:00Z"),
        new OrderDocument(prefix + "confirmed", customerA, "CONFIRMED",
            300000, "2026-01-15T10:00:00Z")
    );

    try {
        docs.forEach(orders::save);

        var matches = orders.findAtLeastAmount(
            customerA, "DRAFT", 200000L);

        assertEquals(1, matches.size());
        assertEquals(prefix + "high", matches.get(0).getId());
        assertEquals(250000L, matches.get(0).getAmountVnd());
    } finally {
        for (var doc : docs) {
            if (orders.existsById(doc.getId())) {
                orders.deleteById(doc.getId());
            }
        }
    }
}
~~~

Test này kiểm chứng:

- Tham số customer/status/amount được bind đúng vị trí.
- Query dùng `>=` và không loại nhầm giá trị bằng ngưỡng.
- SpEL `selectEntity/filter` trả full entity có document key.
- Query trả một kết quả duy nhất trong dataset thuộc test.

### 13.1. Test ngưỡng đúng bằng giá trị

Một test khác dùng `minimumAmount=150000` và dữ liệu có Order đúng `150000` để xác minh phép so sánh **lớn hơn hoặc bằng** thay vì lớn hơn:

~~~java
var matches = orders.findAtLeastAmount(customerA, "DRAFT", 150000L);
assertEquals(2, matches.size());
~~~

Đừng chỉ test ngưỡng lớn hơn mọi amount và nhận list rỗng; query sai field cũng có thể trả rỗng, khiến test không phân biệt được lỗi.

### 13.2. SQL injection và query parameters

Không nối input user vào câu SQL++:

~~~java
// Không làm: giá trị user có thể phá cú pháp hoặc gây injection.
String sql = "SELECT ... WHERE customer_id = '" + userInput + "'";
~~~

Dùng positional/named binding trong `@Query` hoặc SDK `QueryOptions.parameters`. Khi test một customer ID chứa ký tự `'`, `"` hoặc khoảng trắng, query có parameter **vẫn phải chạy đúng**, không đổi cú pháp. Query builder chỉ nên interpolating **identifier từ whitelist cố định** nếu buộc phải tạo keyspace/field động.

## 14. Test @Query named parameters và @Param

Custom method thứ hai:

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
       "AND customer_id = $customer AND status = $state " +
       "ORDER BY created_at ASC")
List<OrderDocument> findByNamedParameters(
    @Param("customer") String customerId,
    @Param("state") String status);
~~~

Dùng `@Param` để không phụ thuộc cờ compile lưu Java parameter names. Test cần xác minh:

~~~java
var fromPositional =
    orders.findAtLeastAmount(customerA, "DRAFT", 0L);

var fromNamed =
    orders.findByNamedParameters(customerA, "DRAFT");

assertEquals(
    fromPositional.stream().map(OrderDocument::getId).toList(),
    fromNamed.stream().map(OrderDocument::getId).toList()
);
~~~

Kỳ vọng trên chỉ hợp lệ nếu dữ liệu fixture không có amount âm (entity đã từ chối âm) và cả hai query đều sort theo `created_at`. Với timestamp trùng, cần tie-breaker hoặc so `Set` của keys thay vì thứ tự danh sách.

**Không trộn named `$customer` với positional `$2` trong một inline query.** Spring Data Couchbase tài liệu hóa hai phương án riêng và không hỗ trợ trộn chúng trong cùng query.

## 15. Query trả full entity khác query projection

Một lỗi phổ biến:

~~~java
// Thiếu ID/CAS/type metadata để tạo full entity đúng.
@Query("SELECT customer_id, amount_vnd " +
       "FROM `shop_it`.`sales`.`orders` WHERE status = $1")
List<OrderDocument> findBrokenProjection(String status);
~~~

Query này chọn vài field JSON nhưng không cung cấp đầy đủ metadata mà Spring Data dùng để dựng entity. Kết quả có thể khác kỳ vọng, thậm chí lỗi khi materialize/ghi tiếp.

### 15.1. Cách phù hợp khi trả OrderDocument

~~~java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
       "AND status = $1")
List<OrderDocument> findByStatusCustom(String status);
~~~

Macro `selectEntity`/`filter` được Spring Data cung cấp để giữ metadata/entity type. Khi app dùng named scope/collection, tránh hardcode production bucket vào `@Query` vì như vậy test `shop_it` và production `shop` sẽ khác keyspace.

### 15.2. Khi nào dùng projection riêng?

Nếu API chỉ cần vài field, có thể dùng **interface/DTO projection** với mapping đúng theo tính năng/version Spring Data đang dùng, hoặc query SDK và map kết quả sang DTO rõ ràng. Không trả `OrderDocument` từ SQL++ chỉ chứa `amount_vnd` rồi kỳ vọng Spring tự đoán ID/CAS.

Các phép test khác cần có:

- Projection trả đúng field names và type.
- Trường thiếu/null được xử lý đúng.
- Projection không được mang giả định “có CAS của entity” nếu query không lấy metadata.
- Không dùng entity projection thiếu metadata để update toàn document.

## 16. So sánh query Repository với SDK SQL++ độc lập

Khi cần xác định bug nằm ở SQL++ hay Spring Data mapping, chạy một query SDK độc lập, **trên cùng keyspace và dataset**:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
    """
    SELECT META(o).id AS docKey,
           o.customer_id AS customerId,
           o.status AS status,
           o.amount_vnd AS amountVnd
    FROM `shop_it`.`sales`.`orders` AS o
    WHERE o.customer_id = $customer
      AND o.status = $state
    ORDER BY o.created_at ASC, META(o).id ASC
    """,
    queryOptions()
        .parameters(JsonObject.create()
            .put("customer", customerA)
            .put("state", "DRAFT"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);

List<JsonObject> sdkRows = result.rowsAsObject();
~~~

Nếu SDK query thấy document mà repository derived query không thấy, kiểm tra:

1. `_class`/type alias và `#{#n1ql.filter}`.
2. `@Field` mapping và property name của derived method.
3. Repository `@Scope`/`@Collection` so với SDK path.
4. Scan consistency của hai query có giống nhau không.
5. Projection/ID/CAS metadata có đầy đủ không.
6. Index/cú pháp/Query Service có sẵn sàng không.

**Đừng vội kết luận repository bị lỗi** khi dữ liệu được seed bằng SDK thuần không có type hint; query Spring Data có thể chủ động loại document không đúng entity type.

### 16.1. EXPLAIN kiểm tra access path, không chỉ output

~~~sql
EXPLAIN
SELECT META(o).id, o.status
FROM `shop_it`.`sales`.`orders` AS o
WHERE o.customer_id = "customer::u100"
  AND o.status = "DRAFT";
~~~

Plan nên được xem xét để bảo đảm query có thể tận dụng `ix_orders_customer_status_created` hoặc index đúng nhu cầu. Nếu optimizer chọn index khác do thống kê hoặc dữ liệu nhỏ, test nên kiểm tra **khả năng và SLO hợp lý**, không hardcode toàn bộ JSON plan của một Couchbase Server version.

## 17. Tính nhất quán và nguồn flaky thường gặp

### 17.1. KV vừa ghi không đồng nghĩa secondary index đã phản ánh mutation

Luồng:

~~~text
T0: repository.save(order)  -> KV write thành công
T1: repository.findById(id) -> KV thấy document
T2: repository.findByCustomerId(...) -> SQL++ index có thể chưa bắt kịp
~~~

`QueryScanConsistency.NOT_BOUNDED` có thể trả index state gần nhất, còn `REQUEST_PLUS` chờ index đủ cập nhật tại thời điểm request. Spring Data repository có `@ScanConsistency`; SDK có:

~~~java
queryOptions()
    .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
~~~

**Không dùng `Thread.sleep(2000)` làm tiêu chí sẵn sàng**. Nếu muốn test read-after-write, chỉ rõ consistency. Nếu muốn test production chấp nhận eventual consistency, thiết kế assertion theo hợp đồng đó, không ép mỗi query phải thấy ghi tức thì.

### 17.2. Query không có index và index chưa ONLINE

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `findById` PASS, `findByCustomerId` FAIL | Thiếu Query/Index hoặc secondary index | Bật services/tạo index |
| `No index available` | Không có index sử dụng được | Tạo index đúng WHERE và type filters |
| DDL vừa xong nhưng query lỗi | Index đang build | `watchIndexes` ONLINE có timeout |
| Query thiếu document mới | Scan consistency | `@ScanConsistency(REQUEST_PLUS)` nếu cần |
| Query trả quá nhiều document | Fixture không cô lập customer/status | Dùng runId cho keys và customer |
| Lỗi chỉ ở CI | Docker resources, Index Service startup | Log service state, cấp RAM/CPU |
| Query đọc sai fields | `@Field` hoặc SQL++ field name sai | SDK raw JSON, `EXPLAIN` |
| Query thiếu ID/CAS | Projection full entity sai | `#{#n1ql.selectEntity}` |

### 17.3. MISSING, NULL, zero và type mismatch

Couchbase phân biệt:

~~~json
{}
~~~

~~~json
{"amount_vnd": null}
~~~

~~~json
{"amount_vnd": 0}
~~~

`amount_vnd IS MISSING`, `IS NULL` và `IS VALUED` có kết quả khác nhau. Một Java primitive `long` có thể làm mất thông tin về NULL/MISSING trong domain materialization hoặc gây exception tùy converter.

Với test repository query, seed các fixture **đúng kiểu và không đúng kiểu** rồi kiểm tra hành vi dự kiến. Nếu mục tiêu là SQL++ semantics, chạy query SDK trực tiếp trên raw JSON và phân biệt lỗi dữ liệu với lỗi mapping. Không dùng `IS NOT NULL` như thể nó luôn loại cả MISSING; hãy xem xét `IS VALUED` khi cần không thiếu và không null.

## 18. Pagination, sort và total count cần test riêng

Khi dataset lớn, một repository có thể hỗ trợ:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<OrderDocument> findByCustomerId(
    String customerId, Pageable pageable);
~~~

Test có thể dùng:

~~~java
PageRequest page0 = PageRequest.of(
    0, 2, Sort.by("createdAt").ascending());

Page<OrderDocument> firstPage =
    orders.findByCustomerId(customerA, page0);
~~~

Phải import `PageRequest` và `Sort` theo Spring Data Commons. Đối với `Page<T>`, framework có thể thực thi **count query** bổ sung; đây là một phần cần test trên Server thật và index phù hợp.

### 18.1. Test pagination không chỉ kiểm tra size

Cần kiểm tra:

- Page 0 và page 1 không có key trùng.
- Kết quả lọc đúng customer.
- Sort theo `createdAt` mapping sang `created_at`.
- Total elements và total pages phản ánh dataset cô lập.
- Không có document lọt giữa pages do test khác thay đổi dataset.
- Nếu timestamp trùng, sort phải có **tie-breaker ổn định** (ví dụ document key qua SQL++ custom query/SDK) khi dùng offset pagination.

**Không tự thêm `ORDER BY`/`LIMIT`/`OFFSET` vào một inline `@Query` đang được Spring Data áp dụng `Pageable` nếu phiên bản framework cũng thêm các mệnh đề ấy.** Query có thể trở thành SQL++ malformed; chọn một nơi chịu trách nhiệm paging/sort và kiểm thử rõ.

### 18.2. Đặt dữ liệu trùng timestamp để bắt pagination không ổn định

Nếu hai Order có cùng `created_at`, thứ tự chỉ `ORDER BY created_at` không xác định được giữa chúng. Kiểm thử phân trang thực sự nên có trường hợp đồng timestamp và dùng tie-breaker như `META(o).id` nếu giải pháp yêu cầu stable order.


## 19. Test lỗi, dữ liệu biên và khả năng tương thích

Không nên chỉ tạo “happy path” với Order hợp lệ. Tầng persistence cần được kiểm tra khi dữ liệu không đúng hợp đồng.

### 19.1. Ma trận kiểm thử âm tính

| Case | Setup | Hành vi cần kiểm tra |
| --- | --- | --- |
| Missing key | `findById` với ID hợp lệ không tồn tại | `Optional.empty`, không bị exception giả |
| Duplicate key | SDK `insert` hai lần cùng key | `DocumentExistsException` |
| Null ID | `findById(null)` | Validation theo contract Spring Data đang dùng |
| Amount âm | Constructor/Service tạo Order âm | Domain validation, không gọi persistence |
| Sai JSON field name | Spring Data writer sai `@Field` | SDK raw JSON test phát hiện |
| Sai JSON type | SDK chèn `amount_vnd:"150000"` | Mapper fail/convert theo chính sách dự án |
| Missing field | SDK chèn body thiếu `amount_vnd` | Không làm sai nghiệp vụ khi đọc legacy |
| JSON null | SDK chèn `amount_vnd:null` | Phân biệt với missing khi domain yêu cầu |
| Enum/status mới | `status:"REFUNDED_V9"` | Reader xử lý hoặc báo lỗi có chủ đích |
| Entity type khác | `_class` không phù hợp | Query filter không trả sai subtype |
| SQL++ không có index | Cố tình loại index trong môi trường riêng | Test setup fail với lỗi rõ, không ném nhầm business exception |
| CAS stale | Hai snapshots cùng version | Optimistic locking, state cuối được giữ |
| Query thiếu metadata | Raw SELECT chỉ vài field nhưng trả entity | Test phát hiện projection không tương thích |
| Timeout/connection loss | Fault-injection trong suite chuyên biệt | Phân loại retryable vs ambiguous mutation result |

**Không dùng `assertThrows(Exception.class, ...)` cho mọi lỗi.** Một test âm tính có thể PASS vì cluster chưa khởi động, không phải vì chính sách validation hoạt động. Xác nhận đúng exception type, message/cause khi cần, và **state cuối**.

### 19.2. Duplicate bằng SDK và ranh giới insert/upsert

~~~java
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.java.json.JsonObject;

var collection = cluster.bucket("shop_it")
    .scope("sales").collection("orders");

String key = "it::" + UUID.randomUUID() + "::order::duplicate";

try {
    collection.insert(key,
        JsonObject.create().put("status", "DRAFT"));

    assertThrows(DocumentExistsException.class,
        () -> collection.insert(key,
            JsonObject.create().put("status", "CONFIRMED")));

    assertEquals("DRAFT",
        collection.get(key).contentAsObject().getString("status"));
} finally {
    if (collection.exists(key).exists()) {
        collection.remove(key);
    }
}
~~~

`insert` khác `upsert`: `insert` chỉ tạo mới, còn `upsert` có thể thay document đã có. **Không suy repository `save` tương đương insert-only**, nhất là khi entity có ID/CAS. Test này chứng minh Couchbase Server thật xử lý collision.

### 19.3. Legacy raw JSON phải được test theo hai chiều

Hai chiều kiểm thử độc lập:

1. Spring Data `save` → SDK `get(contentAsObject)`: xác minh JSON field names, key và CAS.
2. SDK `insert` legacy JSON → Spring Data `findById`: xác minh reader tương thích dữ liệu không do framework ghi.

Nếu chỉ test chiều 1 rồi dùng Spring Data đọc lại, writer và reader có thể cùng dùng `@Field` sai khiến lỗi bị che. Nếu chỉ test chiều 2, chưa chứng minh Spring Data writer phát ra JSON phù hợp với các hệ thống khác.

Khi có subtype/`@TypeAlias`, fixture legacy có thể cần `_class`/alias đúng hoặc kỳ vọng lỗi rõ khi type metadata thiếu. Tài liệu schema migration cần chỉ rõ trạng thái MISSING, NULL, zero và giá trị mặc định.

## 20. Reactive repository: publisher phải được subscribe

Nếu ứng dụng dùng Spring Data Couchbase reactive:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByCustomerIdAndStatus(
        String customerId, String status);
}
~~~

`Mono`/`Flux` thường không thực hiện I/O trước khi được subscribe. Dùng Reactor `StepVerifier`:

~~~java
import reactor.test.StepVerifier;

String key = "it::" + UUID.randomUUID() + "::order::rx";

StepVerifier.create(
    reactiveOrders.save(new OrderDocument(
        key, "customer::u100", "DRAFT",
        200000L, "2026-01-15T08:00:00Z"))
        .flatMap(saved ->
            reactiveOrders.findById(saved.getId()))
)
    .assertNext(actual -> {
        assertEquals(key, actual.getId());
        assertEquals(200000L, actual.getAmountVnd());
    })
    .verifyComplete();

StepVerifier.create(reactiveOrders.deleteById(key))
    .verifyComplete();
~~~

**Những điểm cần kiểm tra thêm:**

- `StepVerifier` xác nhận số phần tử, giá trị, terminal signal và lỗi mong đợi.
- Khi test derived query reactive, cần đảm bảo Query/Index Services và consistency phù hợp; không mặc định query Flux thấy mutation mới ngay.
- Cleanup reactive phải được subscribe; bỏ publisher delete sẽ có nguy cơ rò rỉ fixture.
- `StepVerifier.withVirtualTime` không tua nhanh TTL server hoặc tiến độ xây dựng index.
- Nếu cần CAS conflict reactive, đọc hai snapshots độc lập và assert `onError` từ operation thực; không dùng `onErrorResume` để nuốt lỗi.

### 20.1. Không gọi block trong production reactive pipeline

Trong test có thể dùng `StepVerifier` hoặc một bước blocking có timeout phù hợp để setup/cleanup, nhưng không đưa `block()` vào application code chạy trên event-loop. Test cần phản ánh đường reactive thật, không biến mọi thao tác thành blocking rồi kết luận backpressure/cancellation đã đúng.

## 21. Test transaction, TTL và sub-document không được suy từ CRUD

Một bộ test CRUD PASS không tự động bảo đảm các yêu cầu khác trong module.

| Khả năng | Vì sao cần test riêng? |
| --- | --- |
| **TTL** | Expiry thuộc metadata server, không chỉ một JSON field |
| **Sub-document** | `mutateIn` có JSON path và atomicity theo document |
| **Durability** | Phụ thuộc topology/replicas/quorum, không suy từ single-node |
| **Transaction** | Multi-document commit/abort khác save nhiều lần |
| **Reactive** | Publisher/cancellation/error signal có ngữ nghĩa riêng |
| **Optimistic locking** | Cần CAS thật, không chỉ gọi `save` tuần tự |
| **SQL++ index** | Read-after-write và execution plan khác KV |

Ví dụ TTL test bằng SDK:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import java.time.Duration;

String key = "it::" + UUID.randomUUID() + "::temporary";

collection.insert(key,
    JsonObject.create().put("kind", "ttl-test"),
    insertOptions().expiry(Duration.ofSeconds(4))
);
~~~

Sau đó dùng polling có deadline (hoặc Awaitility) cho đến khi `collection.exists(key).exists()` thành false. **Không dùng `Clock.fixed` để thay server time**, cũng không kỳ vọng hết hạn chính xác đến mili-giây.

Multi-document transaction cần **transaction API/configuration thật** và lỗi được chủ động kích hoạt; không mặc định `@Transactional` trên test tự rollback mọi Couchbase mutation giống JPA.

## 22. Tổ chức lớp test và CI để có phản hồi nhanh

Đề xuất các lớp:

| Suite | Tài nguyên | Kết quả cần chứng minh |
| --- | --- | --- |
| `OrderPolicyTest` | JUnit thuần | Validation, state machine |
| `OrderCrudIT` | KV + converter | Create/read/update/delete đúng |
| `OrderMappingIT` | KV + SDK raw JSON | `@Field`, `@Id`, metadata CAS, legacy |
| `OrderDerivedQueryIT` | KV/Query/Index | Filter/sort/empty results |
| `OrderAnnotatedQueryIT` | KV/Query/Index | `@Query` SpEL + positional/named binding |
| `OrderCasIT` | KV | Stale writer bị từ chối |
| `OrderPaginationIT` | Query/Index + dataset riêng | Pages, counts, deterministic order |
| `OrderReactiveIT` | Reactive repository | Subscription, terminal signals, cleanup |
| `OrderTtlIT` | KV + expiry | Server TTL có polling |
| `OrderPerformanceIT` | Môi trường đại diện | Index plans, p95/p99, hot keys |

### 22.1. Nguyên tắc CI

- Container runtime phải hoạt động; thiếu Docker thì test integration **chưa được chạy**, không báo PASS.
- Pin image/version SDK/Spring Boot/Testcontainers để kết quả hồi quy ổn định.
- Bật Query/Index Services khi có derived/`@Query`.
- Tạo resource qua fixture với quyền phù hợp, chờ index ONLINE bằng `watchIndexes`.
- Không dùng bucket hoặc credentials production.
- Seed key và customer namespaced theo runId để không lẫn dữ liệu khi chạy song song.
- Cleanup theo owned keys, không dùng `deleteAll()` trên collection chia sẻ.
- Có timeout hữu hạn cho container startup, cluster/bucket readiness, index build và từng query.
- Log tên keyspace, index state, loại exception; **không log secrets hoặc raw customer PII**.
- Khi nâng SDK/Server, chạy lại contract tests với JSON legacy và generated query.
- Đừng dùng một Couchbase container đơn node làm bằng chứng về failover/quorum durability nhiều node.

### 22.2. Chẩn đoán test flaky trước khi tăng timeout

| Triệu chứng | Kiểm tra |
| --- | --- |
| `@DataCouchbaseTest` load nhưng repository query lỗi | Có index và Query Service chưa? |
| `findById` PASS, `findBy...` FAIL | SQL++ index/type mapping/consistency |
| Query bị thiếu dữ liệu vừa save | `@ScanConsistency`/`REQUEST_PLUS` |
| Một test PASS riêng, FAIL khi chạy chung | ID/customer collision hoặc cleanup |
| Test class thứ hai lỗi sau class đầu | Spring context cache vs container đã stop |
| CAS test không fail | Hai snapshots độc lập? `@Version` đúng chưa? |
| Count sai | Query đếm lẫn dữ liệu ngoài namespace |
| Sorting khác nhau | Thiếu ORDER BY hoặc tie-breaker |
| `@Query` trả entity không có ID/CAS | Thiếu `selectEntity` hoặc metadata projection |
| Query named params lỗi | `@Param`/placeholder không khớp hoặc trộn kiểu |
| `@Query` khác derived query | Field name, type filter, keyspace, scan consistency |
| Raw SDK thấy document nhưng repository không | `_class`/type alias hoặc `@Scope/@Collection` |

## 23. Bài thực hành tổng hợp: ProductRepository trong catalog

**Bối cảnh:** dự án lưu Product trong `shop_it.catalog.products`.

~~~json
{
  "display_name": "Cà phê hạt 250 g",
  "category": "COFFEE",
  "price_vnd": 150000,
  "active": true,
  "created_at": "2026-01-15T08:00:00Z"
}
~~~

Entity:

- `@Document`, `@Scope("catalog")`, `@Collection("products")`.
- `@Id String id`, `@Version Long cas`.
- `@Field("display_name") String displayName`.
- `@Field String category`, `@Field("price_vnd") long priceVnd`, `@Field boolean active`.
- Timestamp được lưu/ánh xạ theo policy của ứng dụng.

### 23.1. Yêu cầu

1. Khởi tạo CouchbaseContainer với `shop_it`, KV/Query/Index Services.
2. Tạo `catalog.products` và secondary index phù hợp với `category, active, price_vnd`.
3. Viết CRUD integration test, đối chiếu `display_name` bằng SDK raw JSON.
4. Định nghĩa derived query `findByCategoryAndActiveOrderByPriceVndAsc`, seed dataset riêng và assert thứ tự.
5. Viết `@Query` dùng `selectEntity/filter` cùng parameter binding để lọc `price_vnd >= $1`.
6. Chọn `@ScanConsistency(REQUEST_PLUS)` hoặc một chiến lược tương đương cho read-after-write.
7. Test Product không tồn tại, duplicate key, giá bằng zero và JSON `price_vnd:null`.
8. Test hai writers update cùng Product dựa trên CAS cũ.
9. Thử pagination với hai Product cùng giá và thiết kế tie-breaker.
10. Cleanup chỉ các keys của test; không `deleteAll`.

### 23.2. Bộ dữ liệu tham khảo

| Logical ID | category | active | price_vnd | created_at |
| --- | --- | :---: | ---: | --- |
| `coffee-a` | COFFEE | true | 150000 | 08:00 |
| `coffee-b` | COFFEE | true | 200000 | 09:00 |
| `coffee-c` | COFFEE | false | 250000 | 10:00 |
| `tea-d` | TEA | true | 100000 | 11:00 |

Expected result:

- Derived query `COFFEE + true`: `coffee-a` rồi `coffee-b`.
- Custom query `COFFEE + true + price>=180000`: chỉ `coffee-b`.
- `TEA + true`: một Product; `COFFEE + false`: `coffee-c`.
- Khi update Product `coffee-a` từ hai snapshots cũ, writer thứ hai phải conflict và không ghi đè writer trước.

### 23.3. Skeleton repository gợi ý

~~~java
public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<Product> findByCategoryAndActiveOrderByPriceVndAsc(
        String category, boolean active);

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND category = $1 AND active = $2 " +
           "AND price_vnd >= $3 ORDER BY price_vnd ASC")
    List<Product> findAvailableAbovePrice(
        String category, boolean active, long minimumPrice);
}
~~~

Lưu ý khi so `findAvailableAbovePrice` với derived query: cả hai dùng **same category/active params**, test phải seed đúng type hint/field names. Nếu query bị lỗi cú pháp, đừng đổi assertion thành “trả list rỗng” để cho qua.

### 23.4. Tự kiểm tra

1. **Vì sao CRUD theo key có thể PASS khi derived query FAIL?** Vì KV không cần secondary index như SQL++.
2. **Test Mockito repository có chứng minh `@Query` chạy đúng không?** Không.
3. **`@Field("display_name")` cần kiểm tra bằng gì ngoài round-trip?** SDK raw JSON.
4. **`@Version` dùng metadata nào?** CAS, không phải JSON schema version.
5. **`#{#n1ql.selectEntity}` giúp gì?** Chọn đủ fields/metadata để dựng entity.
6. **`#{#n1ql.filter}` nhằm mục đích gì?** Giới hạn entity type theo mapping.
7. **Có thể trộn `$1` và `$name` trong một `@Query` không?** Không.
8. **`@Param` giúp gì trong named query?** Gắn parameter name một cách tường minh.
9. **`@ScanConsistency(REQUEST_PLUS)` có thay index creation không?** Không.
10. **Query không có ORDER BY có bảo đảm thứ tự không?** Không.
11. **Pagination có timestamp/price trùng cần gì?** Tie-breaker ổn định.
12. **Vì sao cần namespace cả customer ID nếu query đếm theo customer?** Tránh lẫn dữ liệu test khác.
13. **`deleteAll` có phù hợp cleanup shared collection không?** Không.
14. **Reactive publisher không được subscribe có ghi data không?** Không nên giả định.
15. **TTL có được tua nhanh bằng `Clock.fixed` không?** Không.
16. **Kết quả query đúng có chứng minh index hiệu quả không?** Không; cần `EXPLAIN`/performance test.

## 24. Checklist trước khi đánh dấu “CRUD và @Query đã được kiểm thử”

- [ ] Dùng Couchbase Server test thực (Testcontainers hoặc test cluster cô lập).
- [ ] Cấu hình đúng bucket, scope và collection được entity chỉ định.
- [ ] Query/Index Services được bật và secondary index tồn tại, ONLINE.
- [ ] CRUD `save/findById/existsById/deleteById` chạy qua repository thật.
- [ ] Create test đối chiếu JSON body bằng SDK thay vì chỉ repository round-trip.
- [ ] `@Id`, `@Field`, `@Version`/CAS được xác minh trên document thật.
- [ ] Update test đọc lại sau save, CAS conflict test dùng hai snapshots độc lập.
- [ ] Delete test chứng minh xóa đúng key và không xóa document khác.
- [ ] Derived query test xác minh filter, sort, empty result và mapping snake_case.
- [ ] `@Query` test dùng `selectEntity` và `filter` khi trả full entity.
- [ ] Positional `$1/$2` và named `@Param` được test riêng; không trộn kiểu.
- [ ] Không nối input không tin cậy thành SQL++; dùng parameter binding.
- [ ] SQL++ read-after-write có consistency phù hợp, không sửa flaky bằng sleep cứng.
- [ ] Test index definition/`EXPLAIN` nếu access path là yêu cầu.
- [ ] Data fixture có logical IDs rõ, physical keys/customer namespaced.
- [ ] SQL++ query không đếm dữ liệu ngoài namespace.
- [ ] Dữ liệu MISSING, NULL, 0, sai kiểu và legacy được test theo reader policy.
- [ ] Pagination có sort/tie-breaker ổn định, count query không lẫn fixture khác.
- [ ] Reactive test và cleanup subscribe bằng StepVerifier.
- [ ] Cleanup chỉ các keys thuộc quyền sở hữu, kể cả khi assertion thất bại.
- [ ] CI có Docker/resources/timeouts đủ và báo rõ integration test chưa chạy.
- [ ] Không coi mock, one-node failover hoặc test context load là bằng chứng persistence đầy đủ.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD, derived queries, `@Query`, SpEL macros, `@ScanConsistency`, pagination và projection.
- [Spring Data Couchbase — @Query API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/repository/Query.html): inline SQL++ và các biến SpEL hỗ trợ.
- [Spring Data Couchbase — @ScanConsistency API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/repository/ScanConsistency.html): `QueryScanConsistency` cho repository method.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Field`, `@Version` và converter.
- [Spring Boot — Data Couchbase Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataCouchbaseTest` và phạm vi test slice.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và connection details.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer`, `BucketDefinition`, services.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers` và `@Container` lifecycle.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): insert/upsert/replace/get/remove/CAS.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): parameters, query consistency, `REQUEST_PLUS`.
- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): scope/collection/index provisioning và `watchIndexes`.
- [Couchbase Server — SQL++ CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): composite index và query planner.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm thử publisher reactive.



