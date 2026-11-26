# Quản lý nhiều bucket hoặc nhiều cluster mà không trộn cấu hình trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **nhiều scope/collection trong một bucket**, **nhiều bucket trong một cluster** và **nhiều cluster độc lập**; chọn mô hình đúng với ranh giới nghiệp vụ, dữ liệu, quyền truy cập và vận hành.
2. Thiết kế bảng định tuyến tài nguyên có kiểu: business capability → cluster → bucket → scope → collection → repository/template/SDK adapter.
3. Tách connection string, credentials, TLS, timeouts, tên bucket và keyspace theo từng cluster trong Spring Boot configuration; không dựa vào biến global hoặc bean tiêm mơ hồ.
4. Đăng ký nhiều bean `Cluster` và SDK `Collection` với `@Qualifier` cụ thể; quản lý vòng đời đóng kết nối đúng một lần.
5. Ánh xạ repository Spring Data tới các buckets khác nhau với `RepositoryOperationsMapping` / `ReactiveRepositoryOperationsMapping`, và hiểu rằng mapping này **chỉ chi phối repository**.
6. Thiết kế `CouchbaseTemplate`/`ReactiveCouchbaseTemplate`, `CouchbaseClientFactory` và adapter SDK khi có nhiều cluster thật; không giả định `@Collection` hay `@Primary` tự đổi cluster.
7. Giữ ranh giới cho SQL++, chỉ mục, TTL, CAS, durability, giao dịch và reactive data access.
8. Viết integration tests ngăn ghi nhầm bucket/cluster, sai credentials, lỗi query keyspace hoặc lẫn tenant và kiểm chứng hành vi rollout/failover.
9. Áp dụng checklist RBAC, secret rotation, metrics, health, capacity, backup, migration và rollback.

Bài thuộc chương **Thiết kế ứng dụng** của module **SPRING_DATA_COUCHBASE**, chuyên xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, index, TTL, CAS, transaction và reactive API. Trong môi trường này, **việc kết nối được không có nghĩa kết nối đúng nơi**.

> **Nguyên tắc:** Mỗi repository và data adapter phải có **đích dữ liệu rõ ràng, kiểm chứng được**. Không sử dụng global mutable bucket/cluster, không im lặng dùng default khi cấu hình một đích bị thiếu, và không tự chuyển thao tác ghi sang cluster khác vì một request timeout.

## 1. Ba cấp phân tách bị nhầm lẫn nhiều nhất

Couchbase có cấu trúc:

~~~text
Cluster
  ├─ Bucket
  │    ├─ Scope
  │    │    ├─ Collection
  │    │    └─ Collection
  │    └─ Scope
  │         └─ Collection
  └─ Bucket
       └─ Scope
            └─ Collection
~~~

`Cluster` của Java SDK kết nối tới **một Couchbase cluster**. Từ cluster ta lấy `Bucket` → `Scope` → `Collection`. Trong Spring Data, `CouchbaseClientFactory` và template gắn tới connection/bucket/scope cụ thể, còn `@Scope`/`@Collection` trên entity chủ yếu xác định các tầng con trong bucket đang chọn.

| Mô hình | Connection SDK | Ranh giới | Khi nào chọn? |
| --- | --- | --- | --- |
| Nhiều collections, một bucket | Một `Cluster` | `bucket.scope.collection` | Domain types khác nhau, policy chung |
| Nhiều buckets, một cluster | Một `Cluster` | `bucket-a`/`bucket-b` | Quota, retention, bucket policy, RBAC khác |
| Nhiều clusters | **Nhiều `Cluster` objects** | Endpoints và identity riêng | Region, compliance, ownership, topology, DR |
| Nhiều tenants | Theo threat model | Scope/collection/bucket/cluster | Ranh giới tenant được kiểm chứng |
| Replication giữa clusters | Nhiều SDK connections hoặc XDCR | Thường bất đồng bộ | DR/analytics, không có transaction xuyên clusters tự động |

**Tên giống nhau không biểu thị cùng dữ liệu.** Ví dụ hai clusters khác nhau đều có `shop_live.commerce.orders` và document key `order::123`; đó vẫn là **hai documents khác nhau**. Một SDK `Cluster` không tự tìm kiếm bucket ở cluster khác.

~~~mermaid
flowchart LR
    S["Order service"] --> R["OrderStore"]
    S --> A["AuditStore"]
    R --> P["Primary Cluster"]
    A --> Q["Audit Cluster"]
    P --> O["shop_live.commerce.orders"]
    Q --> E["audit_history.events.order_events"]
~~~

### 1.1. So sánh lựa chọn kiến trúc

| Tiêu chí | Collections | Buckets cùng cluster | Clusters độc lập |
| --- | --- | --- | --- |
| Schema/keyspace | Phân tách collection | Phân tách bucket | Phân tách hoàn toàn |
| Index | Theo collection | Theo bucket/collection | Index riêng từng cluster |
| Bucket quota/retention | Chung bucket | Có thể tách | Hoàn toàn tách |
| RBAC | Theo bucket/scope/collection nếu roles hỗ trợ | Theo bucket | Theo identity/cluster |
| Failure domain | Chung cluster | Chung cluster | Có thể độc lập nếu hạ tầng tách |
| Số pool/health endpoints | Ít | Ít hơn multi-cluster | Nhiều |
| Transaction đa document | Theo cluster transaction semantics | Trong phạm vi Server/SDK hỗ trợ | **Không có một Couchbase transaction xuyên hai clusters** |
| Query SQL++ | Cùng cluster | Có thể truy vấn nhiều keyspaces cùng cluster nếu hỗ trợ/quyền | Không tự động join bằng một `cluster.query` |
| Vận hành | Dễ nhất | Trung bình | Phức tạp nhất |

Chọn **ít cấp nhất đáp ứng business policy**. Không tạo cluster riêng chỉ vì một entity được đặt tên “Audit” nếu bucket/scope riêng đã đủ để đáp ứng isolation.

### 1.2. Tại sao cần nhiều bucket?

- Khác chính sách lưu trữ, tuổi thọ dữ liệu, backup và quota.
- Một phần dữ liệu có nhiều Query/Index workload ảnh hưởng capacity.
- Giảm quyền truy cập theo bucket hoặc nhóm vận hành.
- Triển khai migration/retention độc lập hơn so với dữ liệu chung bucket.

### 1.3. Tại sao cần nhiều cluster?

- Data residency hoặc region khác nhau.
- Khác trust boundary, secret/identity và lịch bảo trì.
- Cần tách failure/capacity domain và nâng cấp phiên bản theo lịch riêng.
- Audit/reporting/DR có quy trình sao chép/khôi phục khác production.
- Quyền quản trị hoặc ownership bởi tổ chức khác nhau.

**Cluster mới cũng là một hệ thống phân tán mới:** tăng chi phí giám sát, kết nối, TLS, credential rotation, migration và kiểm thử vận hành.

## 2. Routing contract: một capability, một nơi ghi có chủ đích

Ví dụ shop có các data capabilities:

| Capability | Logical cluster | Bucket | Scope | Collection | Operation |
| --- | --- | --- | --- | --- | --- |
| Orders | `primary` | `shop_live` | `commerce` | `orders` | KV/SQL++ read-write |
| Inventory | `primary` | `shop_live` | `warehouse` | `stocks` | KV + CAS |
| Audit events | `audit` | `audit_history` | `events` | `order_events` | Insert/query |
| Reporting | `reporting` | `shop_snapshot` | `reports` | `daily_sales` | Mostly read |
| Integration test | `test-primary` | `shop_it` | `commerce` | `orders` | Test fixtures |

Một logical alias `primary` hoặc `audit` là **deployment configuration**, không phải giá trị user được phép tự do gửi trong HTTP request. Không cho client truyền một connection string hay bucket name để ghi tới bất kỳ keyspace nào.

### 2.1. Bất biến nên test được

> Thay đổi cấu hình audit cluster/bucket không được làm thay đổi nơi `OrderStore` ghi dữ liệu. Ngược lại, lỗi kết nối primary không tự biến thành quyền ghi Order vào audit cluster.

Để giữ bất biến:

1. Mỗi data adapter nhận **client/collection đã được chọn đúng lúc khởi tạo**.
2. Không có biến mutable `currentBucket`/`currentCluster` dùng chung nhiều requests.
3. Thiếu một route bắt buộc phải **fail startup**; không silent fallback sang default.
4. Write adapter không tự động retry sang secondary/fallback cluster trừ khi có protocol đã định nghĩa.
5. Test ghi vào A rồi xác minh B **không chứa key**.
6. RBAC làm hàng rào thứ hai: credentials audit không được ghi order nếu không có chủ đích.

### 2.2. Anti-pattern: static global cluster

~~~java
// Không dùng trong ứng dụng đa luồng.
static Cluster currentCluster;
static String currentBucket;

void process(String requestType) {
    if ("AUDIT".equals(requestType)) {
        currentCluster = auditCluster;
        currentBucket = "audit_history";
    } else {
        currentCluster = primaryCluster;
        currentBucket = "shop_live";
    }

    // Hai requests song song có thể thay currentCluster của nhau.
}
~~~

Tương tự, không thay property `spring.data.couchbase.bucket-name` sau khi Spring đã tạo repositories rồi chờ các beans tự chuyển bucket.

## 3. Cấu hình Spring Boot nhiều clusters rõ ràng

Spring Boot có `spring.couchbase.*` cho một kết nối mặc định và `spring.data.couchbase.bucket-name` cho default bucket. Những properties đó **không tạo sẵn hai SDK Cluster beans độc lập**.

Tạo namespace ứng dụng:

~~~yaml
app:
  couchbase:
    primary:
      connection-string: ${APP_COUCHBASE_PRIMARY_URL}
      username: ${APP_COUCHBASE_PRIMARY_USER}
      password: ${APP_COUCHBASE_PRIMARY_PASSWORD}
      bucket: shop_live
      scope: commerce
      collection: orders
    audit:
      connection-string: ${APP_COUCHBASE_AUDIT_URL}
      username: ${APP_COUCHBASE_AUDIT_USER}
      password: ${APP_COUCHBASE_AUDIT_PASSWORD}
      bucket: audit_history
      scope: events
      collection: order_events
~~~

Đây là **ví dụ biến môi trường**, không có mật khẩu thật. Không log toàn bộ configuration bean hoặc dùng `@ToString` trên object chứa password. Dùng Secret Manager/Kubernetes Secrets/identity provider theo chính sách triển khai.

### 3.1. Các trường cấu hình có phạm vi khác nhau

| Field | Gắn với | Lưu ý |
| --- | --- | --- |
| `connection-string` | Cluster | `couchbase://` hoặc `couchbases://`, bootstrap hosts, TLS |
| `username/password` | Identity của cluster | Credentials chỉ được quyền tối thiểu |
| `bucket` | Bucket trên cluster đó | Không suy ra từ Java entity type |
| `scope/collection` | Keyspace trong bucket | Không giả định cùng tên ở cluster khác là cùng dữ liệu |
| `timeouts` | ClusterEnvironment hoặc request | Theo workload và SLO từng route |
| `durability` | Mutation/bucket policy | Replica topology và bucket type |
| `index scan consistency` | Query policy | NOT_BOUNDED, REQUEST_PLUS, AT_PLUS |
| `health/metrics tags` | Vận hành | Tag logical alias, không đưa username/host chứa PII |

Không gộp hết vào một chuỗi parse thủ công kiểu `cluster/bucket/scope/collection` để truyền khắp tầng application; đó là nguồn lỗi cấu hình và SQL++ identifier injection.

### 3.2. Typed @ConfigurationProperties

~~~java
package com.example.shop.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.couchbase.primary")
public record PrimaryCouchbaseProperties(
    @NotBlank String connectionString,
    @NotBlank String username,
    @NotBlank String password,
    @NotBlank String bucket,
    @NotBlank String scope,
    @NotBlank String collection
) {}

@Validated
@ConfigurationProperties(prefix = "app.couchbase.audit")
public record AuditCouchbaseProperties(
    @NotBlank String connectionString,
    @NotBlank String username,
    @NotBlank String password,
    @NotBlank String bucket,
    @NotBlank String scope,
    @NotBlank String collection
) {}
~~~

Đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
    PrimaryCouchbaseProperties.class,
    AuditCouchbaseProperties.class
})
class CouchbasePropertiesConfiguration {}
~~~

Ví dụ yêu cầu Spring Boot 3.x/Java 17+ cùng `spring-boot-starter-validation` cho Jakarta Validation. Hai record khác type giúp compiler giảm khả năng tiêm nhầm properties, nhưng YAML vẫn có thể copy sai URL — phải có validation ở startup/integration tests.

### 3.3. Startup guards

- Khi yêu cầu hai clusters độc lập, kiểm tra route identity/topology/permissions thực tế; **hai connection strings giống nhau** cần được review.
- Có thể chủ đích dùng cùng cluster cho primary/audit; đừng tự báo lỗi nếu architecture cho phép.
- Không dùng `@Primary` che missing `@Qualifier`; bean injection mơ hồ nên fail.
- Không tự động fallback từ `app.couchbase.audit.*` sang `spring.couchbase.*` nếu audit route thiếu.
- Không dump environment variables hoặc secrets trong startup logs.

## 4. Quản lý nhiều Cluster beans bằng @Qualifier

Với **hai clusters thực sự**, hãy khởi tạo hai SDK `Cluster` beans độc lập. Không dùng cùng một mutable variable rồi chuyển endpoint theo request.

### 4.1. Java configuration định tuyến rõ ràng

~~~java
package com.example.shop.config;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
    PrimaryCouchbaseProperties.class,
    AuditCouchbaseProperties.class
})
public class MultiClusterCouchbaseConfiguration {

    @Bean(name = "primaryCluster", destroyMethod = "disconnect")
    Cluster primaryCluster(PrimaryCouchbaseProperties p) {
        return Cluster.connect(
            p.connectionString(), p.username(), p.password());
    }

    @Bean(name = "auditCluster", destroyMethod = "disconnect")
    Cluster auditCluster(AuditCouchbaseProperties p) {
        return Cluster.connect(
            p.connectionString(), p.username(), p.password());
    }

    @Bean(name = "ordersCollection")
    Collection ordersCollection(
            @Qualifier("primaryCluster") Cluster primary,
            PrimaryCouchbaseProperties p) {

        return primary.bucket(p.bucket())
            .scope(p.scope())
            .collection(p.collection());
    }

    @Bean(name = "auditEventsCollection")
    Collection auditEventsCollection(
            @Qualifier("auditCluster") Cluster audit,
            AuditCouchbaseProperties p) {

        return audit.bucket(p.bucket())
            .scope(p.scope())
            .collection(p.collection());
    }
}
~~~

Đây là một cách **dùng SDK adapters có đích rõ ràng** khi multi-cluster. Cấu hình mặc định của Spring Boot có thể có các điều kiện auto-configuration cho **một Cluster candidate**; nếu tự đăng ký hai `Cluster` beans, **không tự suy** Boot sẽ biết dùng cluster nào để tạo `CouchbaseClientFactory`/`CouchbaseTemplate`/repositories. Phải thiết lập Spring Data routing tường minh nếu muốn dùng repository trên cả hai clusters.

### 4.2. @Qualifier ở ngay constructor của adapter

~~~java
package com.example.shop.storage;

import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Repository;

@Repository
public final class AuditEventStore {

    private final Collection auditEvents;

    public AuditEventStore(
        @Qualifier("auditEventsCollection")
        Collection auditEvents) {
        this.auditEvents = auditEvents;
    }

    public void append(String eventId, String aggregateId,
                       String eventType) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId required");
        }

        auditEvents.insert(
            "event::" + eventId,
            JsonObject.create()
                .put("aggregate_id", aggregateId)
                .put("event_type", eventType));
    }
}
~~~

Một adapter khác nhận `@Qualifier("ordersCollection")`. Việc ghi nhầm sẽ phải đi qua **sửa code wiring** hoặc sửa cấu hình deployment, thay vì xảy ra vì shared mutable state ở runtime.

### 4.3. Đừng gắn @Primary tùy tiện để cho injection hết lỗi

~~~java
@Autowired Cluster cluster; // Mơ hồ khi có primaryCluster + auditCluster.
@Autowired Collection collection; // Mơ hồ khi có hai Collections.
~~~

Nếu thêm `@Primary` trên một Cluster, câu lệnh trên có thể **âm thầm chọn primary** ngay cả trong service audit bị thiếu qualifier. Một số ứng dụng có nhu cầu default thật; khi đó dùng `@Primary` có chủ đích **cộng với quy ước bắt buộc @Qualifier tại biên adapter**, integration tests kiểm chứng.

### 4.4. Quản lý lifecycle và connection pools

SDK khuyến nghị **reuse** `Cluster`, `Bucket`, `Scope`, `Collection` cho toàn vòng đời ứng dụng; chúng được thiết kế dùng chung giữa threads. Không gọi `Cluster.connect` bên trong mỗi request.

~~~java
// Anti-pattern: mỗi API call tạo kết nối SDK mới.
public JsonObject load(String key) {
    Cluster cluster = Cluster.connect(url, user, pass);
    try {
        return cluster.bucket(bucket).defaultCollection()
            .get(key).contentAsObject();
    } finally {
        cluster.disconnect();
    }
}
~~~

Tạo một `Cluster`/đích lúc startup rồi tái sử dụng. Spring `@Bean(destroyMethod = "disconnect")` giúp disconnect khi context đóng. **Collection handles không sở hữu Cluster**, vì vậy không gọi `disconnect` ngay sau khi tạo collection bean.

### 4.5. Shared ClusterEnvironment: dùng có chủ đích

Nếu các clusters dùng **cùng chính sách** timeout/security/network, Java SDK cho phép share một `ClusterEnvironment` để giảm thread/timer resource:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.env.ClusterEnvironment;

ClusterEnvironment shared = ClusterEnvironment.builder()
    .timeoutConfig(t -> t.kvTimeout(Duration.ofSeconds(5)))
    .build();

Cluster a = Cluster.connect(
    primaryUrl,
    ClusterOptions.clusterOptions(primaryUser, primaryPassword)
        .environment(shared));

Cluster b = Cluster.connect(
    auditUrl,
    ClusterOptions.clusterOptions(auditUser, auditPassword)
        .environment(shared));

// Shutdown đúng thứ tự khi app dừng:
// a.disconnect();
// b.disconnect();
// shared.shutdown();
~~~

**Cảnh báo:** environment dựng thủ công và share **không được SDK tự shutdown** khi chỉ `Cluster.disconnect()`. Đóng cả hai clusters xong mới `shared.shutdown()`, ví dụ Spring bean `destroyMethod="shutdown"` với dependency order đã được thiết lập/kiểm chứng. Nếu hai clusters cần TLS trust store, timeout hoặc network settings khác nhau, **đừng share environment mù quáng**; dùng per-cluster config.

### 4.6. TLS/certificates và bí mật

- Dùng `couchbases://`/TLS với CA trust phù hợp khi deployment yêu cầu; xác minh hostname.
- Không bỏ certificate verification để “kết nối được nhanh”.
- Primary/audit có thể dùng các CA khác nhau; mỗi environment cần policy tương ứng.
- Secrets từ vault/K8s và không được xuất hiện trong `toString`, exception payload, health response hoặc logs.
- RBAC theo bucket/scope/collection để credential audit không tự có quyền ghi order.
- Secret rotation cần quy trình thay client/credentials mà không làm gián đoạn request đang xử lý.
- Endpoint list nhiều bootstrap nodes có thể giúp resilience khi một node không sẵn sàng; connection string không phải cluster ID tin cậy tuyệt đối.

## 5. Nhiều bucket trong cùng một cluster bằng SDK

Khi cùng một `Cluster`:

~~~java
Cluster cluster = Cluster.connect(
    connectionString, username, password);

var orderCollection = cluster.bucket("shop_live")
    .scope("commerce").collection("orders");

var eventCollection = cluster.bucket("shop_audit")
    .scope("events").collection("order_events");
~~~

**Không cần mở hai Cluster connections** chỉ vì hai buckets cùng cluster. `Bucket` là resource handle dưới một connection và có keyspaces/quota/permissions khác nhau.

### 5.1. Truy cập bằng explicit Collection ổn định hơn string runtime

~~~java
public record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("orderId required");
        }
    }
}

public final class OrderKvStore {
    private final Collection orderCollection;

    public OrderKvStore(Collection orderCollection) {
        this.orderCollection = orderCollection;
    }

    public JsonObject findBody(OrderId orderId) {
        return orderCollection
            .get("order::" + orderId.value())
            .contentAsObject();
    }
}
~~~

`OrderKvStore` không cần biết connection string hoặc bucket name; nó **chỉ nhận đúng Collection handle** từ configuration. Một routing layer chuyên biệt có thể được test mà không truyền raw endpoint/credentials ra domain service.

### 5.2. Không để collection name từ request chọn mọi dữ liệu

Sai:

~~~java
Collection target = cluster.bucket(request.getBucket())
    .scope(request.getScope())
    .collection(request.getCollection());
target.upsert(request.getKey(), body);
~~~

Nếu request client điều khiển keyspace, nó có thể thử ghi vào dữ liệu không được phép. RBAC vẫn quan trọng nhưng authorization domain cần chặn **trước** khi gọi SDK.

Đúng hơn:

~~~java
enum Capability {
    ORDERS, AUDIT_EVENTS
}

// Routing static và allowlist theo role/business use case.
Collection resolve(Capability capability) {
    return switch (capability) {
        case ORDERS -> orderCollection;
        case AUDIT_EVENTS -> auditEventsCollection;
    };
}
~~~

Với tenancy rất lớn buộc tạo keyspace động, sử dụng **registry có owner, tenant authorization, schema version và quota**, không cho client truyền bất kỳ bucket/scope không kiểm tra.

## 6. Spring Data repository nhiều bucket: RepositoryOperationsMapping

Spring Data Couchbase có API:

~~~java
protected void configureRepositoryOperationsMapping(
    RepositoryOperationsMapping mapping)
~~~

và bản reactive:

~~~java
protected void configureReactiveRepositoryOperationsMapping(
    ReactiveRepositoryOperationsMapping mapping)
~~~

Các callback này nằm trong cấu hình kế thừa `AbstractCouchbaseConfiguration`. Chúng ánh xạ **repository interface hoặc entity type** tới một `CouchbaseOperations`/`ReactiveCouchbaseOperations` do template tương ứng đại diện.

### 6.1. Thứ tự ưu tiên của mapping

| API | Mục đích | Ưu tiên |
| --- | --- | --- |
| `mapping.map(OrderRepository.class, template)` | Chỉ định đích theo repository interface | Cao nhất |
| `mapping.mapEntity(OrderDocument.class, template)` | Các repositories chưa được map theo interface, cùng entity | Trung bình |
| `mapping.setDefault(defaultTemplate)` | Mặc định cho repositories chưa map | Fallback |

**Đây không phải hệ thống route theo từng tenant/request.** Repository bean được cấu hình vào template khi khởi tạo; nó không tự đổi cluster khi một request xuất hiện.

### 6.2. Ví dụ mapping theo repo, không theo tên bucket string trong method

Giả sử đã provision hai `CouchbaseTemplate` có factory/bucket khác nhau:

~~~java
// Đoạn override trong lớp extends AbstractCouchbaseConfiguration.
// ordersTemplate dùng bucket shop_live.
// auditTemplate dùng bucket shop_audit.

@Override
protected void configureRepositoryOperationsMapping(
        RepositoryOperationsMapping mapping) {

    mapping.map(OrderRepository.class, ordersTemplate);
    mapping.map(AuditEventRepository.class, auditTemplate);

    // Có thể dùng mapEntity khi nhiều repos dùng chung entity:
    // mapping.mapEntity(AuditEvent.class, auditTemplate);

    // Nếu muốn policy fail closed, kiểm tra toàn bộ repository
    // đã được map; không dựa vào default âm thầm.
}
~~~

**Vấn đề quan trọng:** `ordersTemplate` và `auditTemplate` phải được tạo **trước** khi method này chạy, với `CouchbaseClientFactory` và converter đúng. Trong một `AbstractCouchbaseConfiguration` subclass, tránh đặt tên helper trùng với tên method `@Bean couchbaseTemplate`, `couchbaseClientFactory` ... vì Spring có thể gọi/resolve bean mặc định thay vì factory bạn định chọn. Hãy đặt tên rõ như `auditTemplateForRepositoryMapping`.

### 6.3. Lắp ráp template và client factory

Spring Data Couchbase các release 5.x/6.x cung cấp `SimpleCouchbaseClientFactory` với các overload, gồm:

~~~java
// Constructor dạng dùng Cluster có sẵn (scopeName tường minh):
new SimpleCouchbaseClientFactory(
    cluster, "shop_audit", "_default");
~~~

và các overload dùng connection string + authenticator + bucket name. `CouchbaseTemplate` có constructor nhận `CouchbaseClientFactory` và `MappingCouchbaseConverter`:

~~~java
CouchbaseClientFactory auditFactory =
    new SimpleCouchbaseClientFactory(
        cluster, "shop_audit", "_default");

MappingCouchbaseConverter converter =
    new MappingCouchbaseConverter();

// Lược đồ: khởi tạo converter/mapping context/custom conversions
// nhất quán với cấu hình Spring Data của dự án trước khi sử dụng.
CouchbaseTemplate auditTemplate =
    new CouchbaseTemplate(auditFactory, converter);
~~~

**Không copy lược đồ này vào production nếu đang dùng custom converters, type aliases, entity callbacks, scope mapping hoặc Spring Data version khác.** Dùng chung đúng `MappingCouchbaseConverter`/mapping context được ứng dụng cấu hình hoặc tạo một bean converter tương đương, rồi test round-trip JSON thật.

### 6.4. Mapping chỉ chi phối calls qua repository

Điểm thường bị hiểu nhầm từ tài liệu Spring Data:

> `configureRepositoryOperationsMapping` áp dụng khi framework tạo/retrieve **repositories**. Nó **không tự chuyển hướng** mọi code gọi trực tiếp bean `couchbaseTemplate` hoặc `cluster.bucket(...)`.

Ví dụ:

~~~java
auditRepository.save(event);   // Route theo operations mapping.
couchbaseTemplate.upsertById(AuditEvent.class).one(event);
                              // Route theo CHÍNH bean template này!
auditCluster.bucket("shop_live").defaultCollection();
                              // SDK route theo cluster/bucket gọi trực tiếp.
~~~

Nếu bean `couchbaseTemplate` vẫn là default `shop_live`, lời gọi thứ hai **không tự dùng auditTemplate** chỉ vì entity được map tới auditRepository. Vì vậy cần adapter dành riêng cho template:

~~~java
public final class AuditTemplateStore {
    private final CouchbaseTemplate auditTemplate;

    public AuditTemplateStore(CouchbaseTemplate auditTemplate) {
        this.auditTemplate = auditTemplate;
    }

    public void save(AuditEvent event) {
        auditTemplate.upsertById(AuditEvent.class).one(event);
    }
}
~~~


## 7. Nhiều cluster với Spring Data repositories: phải cấu hình tường minh hơn

`RepositoryOperationsMapping` giải bài toán **chọn CouchbaseOperations** cho repository. Nhưng `AbstractCouchbaseConfiguration` thông thường định nghĩa **một tập beans mặc định** từ một connection string/bucket. Khi ứng dụng có hai clusters khác nhau, không nên nghĩ chỉ thêm `@EnableCouchbaseRepositories` sẽ tự sinh hai connection contexts hoàn chỉnh.

### 7.1. Hai cách tổ chức có thể review

| Phương án | Thiết kế | Khi nên chọn |
| --- | --- | --- |
| **SDK adapters tách biệt** | `@Qualifier Cluster/Collection`, mỗi capability có wrapper type | Ít data stores, cần kiểm soát cluster tuyệt đối |
| **Nhiều Spring Data templates/factories** | Mỗi target có `CouchbaseClientFactory`, converter, repository operations mapping hoặc repository factory riêng | Cần derived query/entity mapping trên nhiều destinations |
| **Tách Spring application/process** | Mỗi service kết nối một cluster, trao đổi qua event/API | Trust boundary, compliance, vận hành độc lập |
| **Cấu hình dynamic per request** | Route registry nhiều destinations | Chỉ dùng khi có tenancy design/authorization mạnh, không phải mặc định |

Một ứng dụng có thể dùng **Spring Data cho primary cluster** và **SDK adapter riêng cho audit cluster**. Cách này hợp lý nếu audit chỉ insert event và không cần repository query. Đừng bắt buộc dùng cùng abstraction cho mọi cluster khi nó làm routing trở nên mơ hồ.

### 7.2. Những gì một Spring Data multi-cluster setup phải gắn rõ

~~~text
primaryCluster
  ├─ primaryClientFactory (bucket shop_live)
  ├─ primaryMappingConverter
  ├─ primaryCouchbaseTemplate
  ├─ primaryReactiveTemplate (nếu cần)
  └─ OrderRepository -> primary operations

auditCluster
  ├─ auditClientFactory (bucket audit_history)
  ├─ auditMappingConverter
  ├─ auditCouchbaseTemplate
  ├─ auditReactiveTemplate (nếu cần)
  └─ AuditEventRepository -> audit operations
~~~

Các thành phần cần xét:

- **Cluster SDK instance**: connection string, credentials, TLS, environment.
- **Client factory**: bucket/scope trên **đúng cluster**.
- **Mapping converter**: mapping context, custom converters, type aliases, encryption.
- **Template**: uses factory/converter; default scope/collection theo entity/operation.
- **Repository mapping/factory**: repository interface nào dùng template nào.
- **Query/index**: query phát ra trên cluster đang chứa entity.
- **Transaction manager**: chọn đúng cluster/context, không tự xuyên clusters.
- **Metrics/health**: tag source logical name, không lẫn thành một `couchbase` generic.

### 7.3. Nếu dùng nhiều @EnableCouchbaseRepositories

Có thể chia repository packages theo capability, nhưng **chỉ định basePackages chưa đủ** nếu cả hai vẫn trỏ cùng một default CouchbaseTemplate:

~~~java
// Minh họa cấu trúc package, KHÔNG phải cấu hình hoàn chỉnh.
@EnableCouchbaseRepositories(
    basePackages = "com.example.shop.orders.repository")
class PrimaryRepositoriesConfiguration {}

@EnableCouchbaseRepositories(
    basePackages = "com.example.shop.audit.repository")
class AuditRepositoriesConfiguration {}
~~~

Nếu không cấu hình factory/reference/template cho từng repository infrastructure theo đúng Spring Data release, hai tập scan có thể vẫn dùng cùng default operations hoặc tạo bean conflict. Hãy chọn **operations mapping đã test**, hoặc repository infrastructure tùy biến với template references phù hợp API/version; không copy giả định từ JPA `entityManagerFactoryRef` vì Couchbase dùng cơ chế riêng.

Để tránh drift, thêm test đọc resolved mapping:

~~~java
// Ý tưởng assertion khi setup có RepositoryOperationsMapping:
assertSame(
    expectedAuditOperations,
    mapping.resolve(AuditEventRepository.class, AuditEvent.class)
);
~~~

`resolve` và `map` nằm trong `RepositoryOperationsMapping`; không dựa vào bean name string không được xác minh.

### 7.4. Cẩn trọng converter dùng chung

Nếu audit entity có custom JSON encryption/type alias khác order entity, share một `MappingCouchbaseConverter` chưa chắc đúng. Ngược lại, tạo `new MappingCouchbaseConverter()` ad-hoc mà bỏ qua ứng dụng đang cấu hình có thể làm mất custom conversions, event callbacks, auditing và mapping context.

| Thành phần | Khi có thể share | Khi cần tách |
| --- | --- | --- |
| Domain model class | Schema, lifecycle và ownership thực sự giống | Không cho cùng class bị route nhầm |
| Mapping converter | Cùng type policies/conversions | Khác encryption/type alias/field names |
| Cluster environment | Cùng timeout/TLS/network policy | Khác trust store/timeouts |
| Credentials | Có RBAC đúng và security policy cho phép | Trust boundary độc lập |
| Spring template | Khi cùng factory/cluster/bucket policy | Khác cluster hoặc bucket |
| Transaction manager | Phù hợp cùng transaction domain/context | Không share mù xuyên clusters |

**Không nhầm “cùng Java entity” với “cùng physical storage target”.** Một entity type cũng có thể được dùng cho read replica, nhưng code phải phân biệt rõ read model và command model, đặc biệt với CAS/TTL.

## 8. SQL++: tên keyspace, index và quyền phải khớp route

Trên một cluster có nhiều buckets, SQL++ dùng fully qualified keyspace:

~~~sql
SELECT META(o).id AS orderKey,
       o.customer_id, o.status
FROM `shop_live`.`commerce`.`orders` AS o
WHERE o.customer_id = $customerId
  AND o.status = $status
ORDER BY META(o).id;
~~~

Trên audit cluster, query dùng keyspace **thực tồn tại ở audit cluster**:

~~~sql
SELECT META(e).id AS eventKey, e.aggregate_id, e.event_type
FROM `audit_history`.`events`.`order_events` AS e
WHERE e.aggregate_id = $aggregateId;
~~~

### 8.1. Một query được gửi tới cluster nào?

~~~java
var primaryRows = primaryCluster.query(
    primaryQuery, queryOptions().parameters(primaryParams));

var auditRows = auditCluster.query(
    auditQuery, queryOptions().parameters(auditParams));
~~~

`primaryCluster.query` không thể tự lấy records từ audit cluster chỉ vì trong SQL++ string ghi tên bucket `audit_history`. Nếu audit cluster không có bucket đó, query thất bại hoặc tệ hơn, có bucket cùng tên nhưng dữ liệu khác.

### 8.2. Đừng nối identifier từ HTTP request

SQL++ parameter binding cho **giá trị** như `$customerId`, không phải thường dùng để thay thế bất kỳ identifier bucket/scope/collection nào trong `FROM`.

Sai:

~~~java
String statement = "SELECT * FROM " + request.getBucket()
    + "." + request.getScope()
    + "." + request.getCollection();
~~~

Đúng về nguyên tắc:

~~~java
enum QueryRoute { ORDER_SEARCH, AUDIT_SEARCH }

String sqlFor(QueryRoute route) {
    return switch (route) {
        case ORDER_SEARCH -> """
            SELECT META(o).id, o.status
            FROM `shop_live`.`commerce`.`orders` AS o
            WHERE o.customer_id = $customerId
            """;
        case AUDIT_SEARCH -> """
            SELECT META(e).id, e.event_type
            FROM `audit_history`.`events`.`order_events` AS e
            WHERE e.aggregate_id = $aggregateId
            """;
    };
}
~~~

Route enum là **allowlist do ứng dụng định nghĩa**; user chỉ được chọn capability mà policy cho phép, không truyền raw bucket names. Values luôn bind bằng `QueryOptions.parameters`.

### 8.3. Index phải tồn tại tại đúng cluster/bucket/collection

~~~sql
CREATE INDEX ix_orders_customer_status
ON `shop_live`.`commerce`.`orders`(
    customer_id, status
);
~~~

Chạy DDL trên `primaryCluster`. Nếu chạy DDL cùng tên trên audit cluster, bạn **không tự sửa lỗi query trên primary**. Một index có tên giống nhau ở hai clusters có thể có definitions khác nhau; test phải kiểm tra cả keys và keyspace.

| Kiểm tra | Primary | Audit |
| --- | --- | --- |
| Bucket/scope/collection | `shop_live.commerce.orders` | `audit_history.events.order_events` |
| Query Service/Index Service | Theo workload | Theo workload |
| Index definitions | Theo Order query | Theo Audit query |
| `watchIndexes` ONLINE | Trên primary | Trên audit |
| `EXPLAIN` | Đúng query primary | Đúng query audit |
| `QueryScanConsistency` | Theo order read semantics | Theo audit read semantics |

**Một index ONLINE không đảm bảo nó bắt kịp mọi KV mutation mới.** `REQUEST_PLUS`/mutation token policies là quyết định query consistency từng route; không lấy default của primary để áp cho audit một cách ngầm.

### 8.4. Query nhiều buckets trong cùng cluster không giống query nhiều clusters

Couchbase SQL++ có thể truy cập nhiều keyspaces cùng cluster khi Server/role/index hỗ trợ, nhưng:

- Cross-keyspace query có thể tốn tài nguyên và quyền rộng.
- Không tự giải quyết transaction boundary của application workflow.
- Không nên dùng để che storage model quá phân mảnh.
- Không hoạt động tự động giữa hai independent `Cluster` objects; cần API-level aggregation, replication, analytics service/links phù hợp hoặc batch pipeline.

**XDCR giữa clusters thường bất đồng bộ**. Truy vấn reporting cluster sau khi ghi primary có thể đọc trạng thái cũ; không suy từ read-after-write trên primary rằng reporting đã bắt kịp.

## 9. CAS, TTL và durability: metadata cũng phải route đúng

Couchbase `@Id` xác định document key **trong collection**. `@Version` dùng CAS metadata **của document tại đích đó**.

~~~text
Primary: shop_live.commerce.orders / order::123 CAS = C1
Audit:   audit_history.events.order_events / event::order123 CAS = C2
~~~

CAS C1 và C2 **không cùng không gian phiên bản**. Không sao chép `@Version Long` của entity primary sang audit rồi dùng để `replace` audit như thể chúng cùng document.

### 9.1. TTL khác nhau giữa buckets

- Bucket `shop_live` có thể giữ Orders không hết hạn hoặc theo retention riêng.
- Bucket `shop_audit` có thể có policy giữ sự kiện trong nhiều năm.
- Reporting snapshot có thể TTL ngắn.
- Collection maxTTL/bucket settings có thể ảnh hưởng expiry thực tế.

Không gắn `@Document(expiry = 3600)` vào entity dùng chung rồi giả định mọi storage targets nên hết hạn trong một giờ. Khi cùng Java class được ghi vào hai buckets, cần kiểm tra **effective expiry** ở từng bucket, không chỉ annotation ở source code.

### 9.2. Durability yêu cầu topology của cluster đích

SDK mutation options:

~~~java
primaryCollection.insert(
    orderId, orderJson,
    insertOptions().durability(DurabilityLevel.MAJORITY));

auditCollection.insert(
    eventId, auditJson,
    insertOptions().durability(DurabilityLevel.MAJORITY));
~~~

Hai operations có cùng durability level nhưng **khác replica topology**. Nếu audit cluster không đủ quorum, write audit có thể thất bại trong khi primary thành công. Đừng định nghĩa một global flag `durability=MAJORITY` mà không xác minh mỗi cluster/bucket hỗ trợ đúng policy.

### 9.3. CAS không ngăn update nhầm cluster

Một `replace` có CAS đúng trong audit cluster vẫn có thể là **business error** nếu request lẽ ra ghi Order primary. CAS chỉ bảo vệ stale update tại đúng document; nó không chứng minh routing đúng.

### 9.4. Mutation token/AT_PLUS không thay cross-cluster replication guarantee

`QueryOptions.consistentWith(MutationState)` dựa vào mutation tokens của bucket/cluster nơi mutation xảy ra. Không gửi mutation token của primary sang audit cluster rồi kỳ vọng audit index đạt trạng thái tương đương; XDCR/replication lag và mutation histories khác nhau.

## 10. Transaction và cross-cluster workflow

Một `cluster.transactions().run(ctx -> {...})` thuộc **cluster/Transactions instance đó**. Không dùng:

~~~java
primaryCluster.transactions().run(ctx -> {
    // Những thao tác này chỉ thật sự thuộc transaction
    // khi dùng ctx trên cùng transaction domain.
    var order = ctx.get(primaryOrderCollection, orderId);

    // Sai: auditEventsCollection ở cluster khác
    // không được tham gia vào transaction primary bằng
    // auditEventsCollection.insert(...) thường.
    auditEventsCollection.insert(auditKey, auditBody);
});
~~~

Trong ví dụ, audit write là **ngoài transaction**; primary transaction rollback không xóa audit write. Nếu audit thất bại, primary transaction cũng không tự rollback theo giao dịch 2-phase giữa hai clusters.

### 10.1. Vì sao không có một transaction Couchbase thông thường xuyên clusters?

Transactions SDK dùng transaction metadata/ATR và KV/Query operations trong phạm vi một cluster. Hai clusters có độc lập:

- Availability, replication/quorum, config/version.
- Transaction logs/ATRs.
- Failure/timeout.
- Credentials và security boundary.

Một lambda Java chứa hai Cluster calls không phải distributed transaction giữa hai clusters.

### 10.2. Outbox, saga hoặc idempotent replication

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant Primary as Primary Cluster
    participant Relay as Outbox Relay
    participant Audit as Audit Cluster
    App->>Primary: Transaction Order + OutboxEvent
    Primary-->>App: Commit
    Relay->>Primary: Read pending OutboxEvent
    Relay->>Audit: Idempotent INSERT eventId
    Audit-->>Relay: Ack or duplicate
    Relay->>Primary: Mark delivered / checkpoint
~~~

Đây là **eventual consistency**, không phải một transaction ACID toàn hệ thống. Khi relay mất kết nối sau khi audit đã nhận event nhưng trước khi checkpoint, nó có thể gửi lại — audit consumer phải idempotent dựa trên `eventId`.

### 10.3. Điều không nên làm

- Không “dual write” Order và Audit liên tiếp rồi tuyên bố chúng atomic.
- Không retry cross-cluster write mù khi response timeout (outcome ambiguous).
- Không cho read fallback sang audit khi primary lỗi nếu audit không được định nghĩa là authoritative.
- Không tự promote reporting cluster thành command store khi chưa có quy trình failover/cutover và kiểm tra consistency.
- Không assume `@Transactional` Spring gói được hai clusters chỉ vì cả hai là Couchbase.

## 11. Reactive multi-cluster: publisher và resource ownership

Reactive SDK cũng cần route tường minh:

~~~java
ReactiveCollection primaryOrders = primaryCluster
    .bucket("shop_live")
    .scope("commerce")
    .collection("orders")
    .reactive();

ReactiveCollection auditEvents = auditCluster
    .bucket("audit_history")
    .scope("events")
    .collection("order_events")
    .reactive();
~~~

Hai `ReactiveCollection` handles có nguồn Cluster khác nhau. Khi compose:

~~~java
Mono<JsonObject> order = primaryOrders.get(orderId)
    .map(r -> r.contentAsObject());

Mono<JsonObject> audit = auditEvents.get(eventId)
    .map(r -> r.contentAsObject());

Mono<Tuple2<JsonObject, JsonObject>> both =
    Mono.zip(order, audit);
~~~

`Mono.zip` **không tạo transaction xuyên clusters**. Một publisher lỗi có thể làm zip lỗi; cancellation, timeout và retries có thể tác động riêng trên mỗi cluster. Test reactive cần subscribe bằng `StepVerifier` và xác minh completion/error của từng operation.

### 11.1. ReactiveRepositoryOperationsMapping cũng chỉ map repositories

Nếu dùng `ReactiveCouchbaseRepository` trên nhiều buckets, cấu hình callback tương ứng:

~~~java
@Override
protected void configureReactiveRepositoryOperationsMapping(
        ReactiveRepositoryOperationsMapping mapping) {
    mapping.map(AuditEventReactiveRepository.class,
        auditReactiveTemplate);
}
~~~

Và giống blocking mapping, cơ chế này **không tự reroute** một `ReactiveCouchbaseTemplate` được inject trực tiếp vào component khác. Luôn dùng typed route/`@Qualifier` hoặc repository mapping đã kiểm chứng.

### 11.2. Không block event-loop để đổi route

Sai:

~~~java
return auditMono.block(); // Block trong reactive request thread.
~~~

Nên giữ operations reactive end-to-end, inject đúng SDK client/ReactiveCouchbaseTemplate. Chỉ dùng blocking khi setup/teardown tests hoặc ở boundary đã được xác định, không dùng để che thiếu orchestration giữa clusters.


## 12. Multi-tenancy: không chọn cluster/bucket chỉ bằng tên tenant

Một hệ thống đa tenant có thể chọn:

| Mô hình | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Shared collection, field `tenant_id` + key prefix | Ít resource, dễ scale tenant count | Mỗi query/update cần tenant filter và authorization |
| Scope/collection per tenant | Isolation keyspace rõ hơn | Rất nhiều resources/indexes, quota và migration |
| Bucket per tenant | Có thể tách bucket policy/RBAC | Số bucket/index/resource lớn, vận hành phức tạp |
| Cluster per tenant | Tách trust/failure domain mạnh | Chi phí hạ tầng/SDK pools/ops tăng đáng kể |

**Tenant ID phải đến từ trusted auth context**, không lấy từ body tùy ý rồi sử dụng để chọn bucket.

### 12.1. TenantRoutingRegistry theo allowlist

~~~java
public enum TenantTier {
    SHARED, DEDICATED
}

public record TenantRoute(
    String tenantId,
    TenantTier tier,
    String logicalCluster,
    String bucket,
    String scope,
    String collection
) {
    public TenantRoute {
        if (tenantId == null || tenantId.isBlank()
                || logicalCluster == null || logicalCluster.isBlank()
                || bucket == null || bucket.isBlank()
                || scope == null || scope.isBlank()
                || collection == null || collection.isBlank()) {
            throw new IllegalArgumentException("Invalid route");
        }
    }
}

public interface TenantRoutingRegistry {
    TenantRoute authorizedRouteFor(
        String authenticatedTenantId);
}
~~~

Registry có thể đọc config/metadata tin cậy và cache theo policy; nhưng auth layer phải chứng minh user/session được phép truy cập tenant đó. `TenantRoute` chưa đủ nếu code chỉ kiểm tra route tồn tại rồi cho user ghi vào tenant bất kỳ.

### 12.2. Shared collection vẫn phải gắn tenant vào key và query

~~~text
Document key: tenant::<tenantId>::order::<orderId>
JSON: { "tenant_id": "...", "status": "..." }
Index: (tenant_id, status, created_at)
~~~

Query:

~~~sql
SELECT META(o).id, o.status
FROM `shop_live`.`commerce`.`orders` AS o
WHERE o.tenant_id = $authorizedTenantId
  AND o.status = $status;
~~~

`$authorizedTenantId` phải lấy từ authentication context; không dùng `request.tenantId` chưa xác minh. KV `findById` theo key vẫn cần tên key có tenant prefix và authorization check, vì KV không tự áp SQL++ WHERE tenant filter.

### 12.3. Không dùng ThreadLocal để đổi default bucket trong reactive pipeline

Trong request thread imperative, `ThreadLocal` dễ rò giữa thread pool khi không cleanup; trong Reactor, pipeline có thể chuyển thread. Đặt `TenantRoute` trong request-scoped context/Reactive Context theo framework đang dùng, nhưng adapter vẫn phải **validate route** và chọn resource từ registry không mutable.

Không đưa một mutable `currentTenantBucket` vào singleton `CouchbaseTemplate`. Với dedicated tenant database, cân nhắc pool/cache client handles theo tenant có giới hạn, expiry và cleanup; **không Cluster.connect mỗi HTTP request**.

### 12.4. Kiểm thử chống lộ dữ liệu cross-tenant

- Cùng logical `orderId=42` ở tenant A/B, physical keys phải khác hoặc nằm collection/bucket tách.
- Người dùng tenant A không được `findById`/SQL++ query thấy tài liệu B.
- Một query thiếu `tenant_id` phải bị bắt bởi contract tests/static policy.
- RBAC phải giảm thiệt hại nếu ứng dụng có bug routing.
- Khi một tenant chuyển từ shared sang dedicated bucket, không được trả dữ liệu của tenant khác do fallback.
- Cache key phải chứa tenant/route identity; không cache `order::42` toàn cục.

## 13. Security: giới hạn thiệt hại khi cấu hình sai

**Một câu SQL++ đúng cú pháp vẫn có thể truy cập nhầm dữ liệu** khi client có quyền quá rộng. Multi-bucket/multi-cluster cần security boundary nhiều lớp.

### 13.1. RBAC theo từng capability

| Identity | Quyền đề xuất | Không nên có |
| --- | --- | --- |
| `shop-primary-app` | KV/Query trên `shop_live.commerce.orders` và resources cần thiết | Quyền admin toàn cluster nếu không cần |
| `shop-audit-writer` | Insert/read theo policy vào `audit_history.events.order_events` | Update/delete Order production |
| `shop-report-reader` | Chỉ đọc các keyspaces reporting cho phép | Write production |
| `shop-migration` | Quyền tạm thời để provision/copy tài nguyên | Credentials lâu dài không rotation |
| `shop-it-runner` | Provision/read/write chỉ trên test cluster | Truy cập production |

Tên vai trò cụ thể phụ thuộc Couchbase Server edition/version, scope RBAC và chức năng Key-Value, Query/Index, collection management. Cần kiểm tra privileges theo **tác vụ thực tế**; không trao cluster admin chỉ để sửa lỗi access denied khi deploy.

### 13.2. Tách migration credential và runtime credential

Runtime app thường cần CRUD/query, không nên có `Manage Buckets`/`Manage Scopes`/`CREATE INDEX` nếu deployment pipeline đã provision. Chạy schema migrations bằng một identity CI riêng, audit, sau đó app khởi động với quyền tối thiểu.

**Tránh một anti-pattern:** application catch `CollectionNotFoundException` rồi tự tạo scope/index bằng quyền admin production. Lỗi thiếu resource phải được phát hiện qua migration/readiness checks, không mở quyền admin cho mọi runtime instance.

### 13.3. TLS, mTLS và certificate rotation

- `couchbases://` và verified CA/hostname cho kết nối TLS.
- Nếu cluster A và B có trust roots khác nhau, config TLS phải tách hoặc được share theo chính sách.
- Hỗ trợ certificate authentication nếu tổ chức dùng mTLS.
- Không ghi password/connection string chứa secret vào exception logs.
- Rotation certificate/credential cần test kết nối mới và drain client cũ; không mutate SDK Cluster đã khởi tạo theo cách không được hỗ trợ.
- Không giả định URL ở config giống nhau chứng minh cluster identity giống; bootstrap DNS/load balancer và cluster topology có thể thay đổi.

### 13.4. Audit trail của routing

Một log an toàn nên có:

~~~json
{
  "logical_store": "audit",
  "resource_alias": "audit-events",
  "operation": "insert",
  "operation_id": "evt-123",
  "result": "success"
}
~~~

Không cần đưa `password`, `username`, raw connection string, document body/PII hoặc hostname nội bộ nhạy cảm vào mọi log. Metrics thường gắn **logical alias** như `primary`, `audit`, không dùng document key hay tenant ID làm metric label cardinality rất cao.

## 14. Readiness và failure isolation theo từng cluster

Đừng gom mọi thứ vào một health check `couchbase: UP`. Một ứng dụng có Primary và Audit cần cho biết **đích nào không sẵn sàng**, và decision khi gặp lỗi phải dựa trên business policy.

### 14.1. Readiness theo route

~~~mermaid
flowchart TD
    START["App startup"] --> P["Connect primary"]
    START --> A["Connect audit"]
    P --> PK{"Primary keyspace usable?"}
    A --> AK{"Audit keyspace usable?"}
    PK -->|No| PF["Primary unavailable"]
    AK -->|No| AF["Audit unavailable"]
    PK -->|Yes| PR["Primary ready"]
    AK -->|Yes| AR["Audit ready"]
    PR --> DEC["Apply capability readiness policy"]
    AR --> DEC
    PF --> DEC
    AF --> DEC
~~~

| Capability | Khi primary down | Khi audit down |
| --- | --- | --- |
| Order create | Không tự ghi Order sang audit; fail/retry theo policy | Có thể tiếp tục **nếu** outbox durable và audit async |
| Order read | Không mặc định dùng audit copy stale | Có thể tiếp tục nếu order store ở primary |
| Synchronous compliance audit | Có thể block write theo policy | Có thể block nghiệp vụ hoặc queue đến khi audit sẵn sàng |
| Reporting dashboard | Có thể đọc snapshot theo freshness contract | Có thể degraded nếu reporting/audit down |
| Background reconciliation | Retry có backoff/deadline | Report lag và checkpoint |

**Không để fallback ghi sang cluster khác chỉ vì một cluster tạm thời timeout.** Nó có thể tạo split-brain dữ liệu, và khi cluster cũ hồi phục bạn không biết bản nào authoritative.

### 14.2. Bootstrap và health probes

~~~java
primaryCluster.waitUntilReady(Duration.ofSeconds(60));
auditCluster.waitUntilReady(Duration.ofSeconds(60));

primaryCluster.bucket(primaryBucket)
    .waitUntilReady(Duration.ofSeconds(60));
auditCluster.bucket(auditBucket)
    .waitUntilReady(Duration.ofSeconds(60));
~~~

Mức ready của cluster/bucket không chứng minh **named collection** đã tồn tại hoặc permission write/query đúng. Cần kiểm tra:

- Keyspace manifests và quyền phù hợp operation.
- Query/Index Services nếu route dùng derived repository/SQL++.
- Secondary index ONLINE nếu query cần.
- Chính sách “không có index” không được che bằng primary index scan.
- Durability/quorum nếu route yêu cầu synchronous durable mutation.

### 14.3. Timeout riêng và circuit breaking

Một cluster audit chậm không nên làm hết sạch thread pools phục vụ primary. Chọn:

- SDK operation timeouts theo route.
- Retry/backoff theo loại lỗi, không retry authorization hay missing keyspace.
- Concurrency quotas/circuit breakers cho audit event publisher.
- Backpressure/outbox queue limits.
- Separate SLOs `orders_write_latency`, `audit_event_delivery_lag`.
- Bulkhead khi chung JVM nhiều external dependencies.

Nếu dùng shared `ClusterEnvironment`, nhớ kiểm tra resource policy dùng chung có gây contention; khi có workload rất khác biệt, có thể cần environment riêng.

## 15. Observability: luôn ghi logical store thay vì một metric chung

| Metric gợi ý | Nhãn cơ bản | Ý nghĩa |
| --- | --- | --- |
| `couchbase_store_request_total` | `store=primary/audit`, operation, result | Traffic/errors theo route |
| `couchbase_store_latency_seconds` | store, operation | p50/p95/p99 |
| `couchbase_store_timeout_total` | store, exception category | Timeout theo cluster |
| `couchbase_store_connection_health` | store | Readiness |
| `couchbase_index_lag_seconds` | store, collection alias | Query freshness |
| `couchbase_durable_write_error_total` | store, level | Durability/quorum issues |
| `outbox_pending_events` | source, destination | Backlog cross-cluster |
| `outbox_oldest_pending_age_seconds` | route | RPO/lag |
| `routing_mismatch_failures_total` | operation, route | Phát hiện sai endpoint/resource |
| `tenant_access_denied_total` | capability | Unauthorized cross-tenant access |

Đây là **tên metric do ứng dụng có thể định nghĩa**, không phải mặc định chắc chắn có trong SDK. Không dùng raw tenant ID, document key hoặc kết nối có credentials làm Prometheus label.

### 15.1. Tracing qua nhiều clusters

Một trace chuyển đơn có thể gồm:

~~~text
POST /orders
  -> OrderStore(primary) write order + outbox
  -> OutboxPublisher(primary) read event
  -> AuditStore(audit) insert event idempotent
  -> Checkpoint(primary)
~~~

Ghi span attribute `db.system=couchbase` cùng `logical_store` và operation category. Không biến timeout audit thành một generic “database timeout” khiến đội vận hành nhầm sang primary.

### 15.2. Alerts theo business criticality

- Primary order writes error rate vượt SLO → cảnh báo cao.
- Audit lag vượt regulatory RPO/SLA → cảnh báo theo mức độ.
- Reporting snapshot chậm nhưng order path bình thường → degrade reporting riêng.
- Nhiều `DocumentNotFound` có thể là dữ liệu/TTL bình thường, không coi như mất kết nối.
- Quota, index failure, RBAC denied, X509 expiry nên có alerts riêng từng route.

## 16. Integration tests: tạo cùng document key ở hai đích để bắt nhầm

Unit tests của một `OrderStore` mock collection có thể kiểm tra logic, nhưng **không chứng minh SDK route đúng cluster/bucket**. Cần Testcontainers/cluster test thật.

### 16.1. Môi trường test tối thiểu

~~~text
Test Cluster PRIMARY:
  bucket shop_live_test
  scope commerce
  collection orders

Test Cluster AUDIT:
  bucket audit_history_test
  scope events
  collection order_events
~~~

Có hai lựa chọn:

1. **Một CouchbaseContainer, hai buckets:** kiểm chứng multi-bucket routing trong cùng cluster.
2. **Hai CouchbaseContainers tách biệt, có thể dùng cùng bucket name:** kiểm chứng multi-cluster routing và khác endpoints/credentials.

Hai containers độc lập giúp phát hiện lỗi mà một container/two-bucket test không tìm thấy: cluster bean chính xác hay không, SSL/credential config và khả năng ghi nhầm endpoint.

### 16.2. Testcontainers không tự tạo named collections/indexes

~~~java
CouchbaseContainer primary = new CouchbaseContainer(primaryImage)
    .withBucket(new BucketDefinition("shop_it"));

CouchbaseContainer audit = new CouchbaseContainer(auditImage)
    .withBucket(new BucketDefinition("audit_it"));
~~~

Tạo `scope/collection` bằng `CollectionManager`, index bằng `QueryIndexManager` trên **đúng container/cluster**, rồi đợi KV/Index readiness. Nếu chỉ test KV theo document key, Index Service không bắt buộc; với Spring Data derived/`@Query` cần Query/Index và secondary index phù hợp.

### 16.3. Test A/B có cùng logical ID để loại false positive

~~~java
@Test
void orderWriteCannotLeakIntoAuditCluster() {
    String logicalId = "order::shared-logical-id";
    String physicalId =
        "it::" + UUID.randomUUID() + "::" + logicalId;

    orderStore.insert(physicalId, orderJson);

    assertTrue(primaryOrders.exists(physicalId).exists());
    assertFalse(auditEvents.exists(physicalId).exists());
}
~~~

**Test chính xác phải dùng hai independent Cluster handles.** Nếu `primaryOrders` và `auditEvents` đều lấy từ primaryCluster do copy-paste nhầm, test “audit không thấy” có thể tình cờ PASS vì nằm hai collections của cùng cluster. Hãy test thêm **read/write markers tại các cụm khác nhau**.

### 16.4. Sentinel markers chứng minh cluster identity

~~~text
Primary cluster:
  it::<runId>::sentinel::cluster = {"origin":"PRIMARY"}

Audit cluster:
  it::<runId>::sentinel::cluster = {"origin":"AUDIT"}
~~~

Test đọc qua từng configured adapter và assert `origin` khớp. Không dùng document sentinel trong production nếu không có policy; fixture có thể dùng synthetic keys riêng và cleanup.

### 16.5. Các test bắt buộc theo tầng

| Test | Setup | Assertion |
| --- | --- | --- |
| Same cluster, two buckets | `shop_it` + `audit_it` | Order write không xuất hiện trong audit bucket |
| Two independent clusters | Hai containers | Audit adapter không ghi vào primary |
| Bean wiring | Hai Cluster/Collection beans | `@Qualifier` chọn đúng instance |
| Repository operations map | Repos/entitites có mapping | `resolve(repo,entity)` đúng template |
| Direct template | Inject template rõ bean name | Template upsert đúng keyspace |
| Wrong credentials | User audit thiếu quyền order | Access denied có chủ đích |
| Missing config | Audit endpoint/bucket trống | Startup fail, không fallback |
| Derived SQL++ | Index tại đúng cluster | Query thấy document đúng type/keyspace |
| Same key in both clusters | Seed body khác | Đọc mỗi route trả body riêng |
| Async audit replication | Outbox/replay | Đúng một event per eventId |
| Timeout audit | Fault injection | Primary behavior theo declared policy |
| Tenant A/B | Cùng logical ID | Cross-tenant read/write bị từ chối |

## 17. Migration từ một bucket sang nhiều buckets hoặc clusters

Thay đổi route dữ liệu không chỉ là sửa connection string. Ví dụ muốn chuyển audit events từ `shop_live.commerce.audit` sang `audit_history.events.order_events` ở cluster khác.

~~~mermaid
flowchart TD
    A["Inventory sources/routes/schema"] --> B["Provision destination + RBAC + indexes"]
    B --> C["Snapshot/backfill có checkpoint"]
    C --> D["CDC/XDCR/outbox bắt kịp changes"]
    D --> E["Shadow-read/compare"]
    E --> F{"Lag / data parity / permissions OK?"}
    F -->|No| G["Pause cutover + reconcile"]
    F -->|Yes| H["Switch read route theo release flag"]
    H --> I["Switch authoritative write theo protocol"]
    I --> J["Observe + rollback window"]
    J --> K["Retire old route sau retention"]
~~~

### 17.1. Sáu điều kiện bắt buộc trước khi cutover

1. Destination bucket/scope/collection đã có và đúng TTL/replica/quota policies.
2. Destination indexes được tạo, ONLINE và có plan phù hợp.
3. Credentials runtime có **quyền tối thiểu** tại destination.
4. Backfill có checkpoint/idempotency và đo record count/checksum/schema parity.
5. Update/delete/expiry trong lúc backfill được giải quyết, không chỉ copy snapshot lúc bắt đầu.
6. Có **rollback plan** nếu query/read/write sau cutover phát hiện sai route hoặc dữ liệu thiếu.

### 17.2. Đừng chỉ copy document JSON

Khi chuyển dữ liệu giữa buckets/clusters:

| Thuộc tính | Có tự giữ khi copy JSON? | Việc cần làm |
| --- | --- | --- |
| Document key | Nếu caller chọn đúng | Preserve/namespace theo contract |
| JSON fields | Có thể, qua converter hoặc SDK | Kiểm tra schema/type aliases |
| `_class` | Nếu body được copy nguyên | Mapping Spring Data cần xử lý |
| CAS | **Không** giữ semantics qua target write | Không mang `@Version` cũ sang dùng như CAS mới |
| Expiry/TTL | Không mặc định | Đọc deadline, tính chính sách còn lại hoặc reset có chủ đích |
| Bucket/scope/collection | Không tự suy từ body | Routing destination rõ ràng |
| Secondary indexes | Không | Provision và build riêng |
| RBAC | Không | Provision principal/roles |
| Durability | Không | Mutation options + destination topology |
| Transaction metadata | Không | Không copy/sửa ATR/XATTR transaction nội bộ |
| Tombstones/deletes | Snapshot đơn lẻ thường không đủ | CDC/XDCR/change log và reconcile |

**CAS là token của version tại target document**, không phải một field business có thể sao chép. Nếu entity cũ có `@Version`, cần dựng entity mới/clear metadata theo đúng mapper và migration protocol để insert/replace tại destination.

### 17.3. Không reset TTL ngoài ý muốn

Nếu Order/session còn hạn 15 phút ở nguồn, khi copy sang bucket mới cần quyết định:

- Preserve absolute expiry deadline theo policy.
- Đặt TTL còn lại tính tại thời điểm copy.
- Reset TTL theo chính sách đích (có rủi ro kéo dài/thu ngắn retention).
- Không copy tài liệu đã hết hạn.

Với audit immutable có retention pháp lý, TTL source/target có thể khác có chủ đích; cần record migration policy và test expiration sau cutover.

### 17.4. Giai đoạn dual write không tự an toàn

Đoạn sau có thể partial success:

~~~java
primaryOrders.upsert(key, orderBody);
auditEvents.upsert(eventKey, eventBody);
~~~

Nếu audit ghi fail sau primary success, dữ liệu không nhất quán. Nếu response timeout sau audit mutation, retry mù có thể duplicate side effects. Không gọi hai writes trên hai clusters là một atomic transaction.

Ưu tiên:

- Transaction order + outbox trong **một cluster authoritative**.
- Relay idempotent với stable event ID.
- Retry/backoff và dead-letter/reconciliation.
- Checkpoint/monitor replication lag.
- Read route cutover sau khi đạt parity/freshness policy.
- Cutback/rollback có nguồn authoritative xác định để tránh split-brain.

### 17.5. Switch authoritative write là quyết định lớn hơn switch read

**Read cutover** có thể tiến hành từng phần khi destination là bản sao đủ mới và không phát sinh mutation mới tại đó. **Write cutover** thay nguồn sự thật. Trước khi thực hiện phải kiểm tra:

- Writer nào còn ghi vào nguồn cũ?
- Có fencing/version/lease ngăn hai writers cùng authoritative không?
- Những request in-flight sẽ ghi đi đâu?
- Message queues/outbox có đang gửi chậm không?
- Nếu rollback, phải replay những writes phát sinh ở nguồn mới thế nào?

Không tự “failback” về cluster cũ khi cluster mới gặp timeout nếu không có chiến lược đồng bộ ngược và conflict handling.

## 18. Lỗi cấu hình thường gặp và cách phát hiện

| Triệu chứng | Nguyên nhân gốc có thể | Cách kiểm tra |
| --- | --- | --- |
| `OrderRepository` ghi vào audit bucket | Operations mapping sai hoặc default fallback | `resolve`, SDK raw reads theo keyspace |
| `AuditTemplateStore` ghi primary dù repo audit đúng | Mapping chỉ có hiệu lực cho repo, không cho template gọi trực tiếp | Inject đúng `@Qualifier`/template bean |
| Mọi bean Cluster trỏ cùng endpoint | Copy YAML/`@Primary`, property prefix sai | Two-container sentinel tests |
| Repository chạy `findById` nhưng derived query lỗi | KV đúng, Query/Index Services/keyspace sai | Index trên đúng cluster, `EXPLAIN` |
| `@Collection` đã đặt nhưng vẫn sai bucket | Annotation định collection, không tự đổi bucket | ClientFactory/default template |
| Chỉ khi chạy CI mới fail | Config vars thiếu, Testcontainers port mapping, secrets | Fail startup trên missing config |
| Cùng ID nhưng đọc nhầm bản khác | ID không namespace theo tenant/cluster | Định danh route + key |
| CAS conflict bất thường sau migrate | Dùng CAS từ source ở target | Dùng target CAS mới |
| TTL ở audit bị rút ngắn | Destination maxTTL khác source | Read expiry metadata |
| Primary down, app lại ghi reporting | Dangerous fallback routing | Cấm implicit write failover |
| Two clusters khác TLS trust CA | Share ClusterEnvironment không phù hợp | Tách env/trust policy |
| Audit không thấy event vừa phát | XDCR/outbox/Index lag eventual | Monitor checkpoint/replication lag |
| Duplicate audit events | Relay retry sau ambiguous ack | Stable eventId + insert-only/idempotency |
| `@Transactional` không rollback audit write | Cross-cluster write ngoài transaction | Outbox/saga, test state cả hai |
| Reactive app lẫn tenant | ThreadLocal không mang qua scheduler | Reactor Context + authorization |
| Metrics chỉ có `couchbase_errors` chung | Không tag logical route | Route-labelled observability |
| Test class sau dùng container đã dừng | Spring context cache vs Testcontainers lifecycle | Đồng bộ context/container |

### 18.1. Fail closed vs fail open

Khi một route bị thiếu hoặc invalid:

- **Fail closed** cho operation đòi chính xác nguồn dữ liệu và/hoặc compliance.
- **Degrade có kiểm soát** chỉ khi business contract cho phép, ví dụ reporting UI hiển thị “dữ liệu có thể chậm 10 phút”.
- **Không** giả một lỗi audit/primary bằng cách ghi vào default bucket khác.
- **Không** catch `RuntimeException` rồi tiếp tục với `Collections.emptyList()` nếu người dùng có thể hiểu là “không có dữ liệu”.
- **Không** cung cấp credentials rộng hơn chỉ để “sửa nhanh” permission denied.

### 18.2. Phân biệt connectivity, authorization và routing

Ba lỗi không tương đương:

1. `primaryCluster` không kết nối được → network/bootstrap/availability.
2. Kết nối được nhưng `shop_live.commerce.orders` access denied → RBAC.
3. Access thành công nhưng ở `audit_history.events.order_events` → **routing bug**.

Health check kiểu `cluster.waitUntilReady` không phát hiện trường hợp (3); cần contract tests theo route identity và permissions.

## 19. Bài thực hành tổng hợp: Orders và Audit trên hai clusters

**Yêu cầu:** một ứng dụng Spring Boot phải ghi Order vào cluster primary, audit event vào cluster audit. Không được có cách nào để một request Order ghi nhầm sang audit bucket.

### 19.1. Bối cảnh

~~~text
Primary Cluster:
  URI      couchbases://primary.example.invalid
  Bucket   shop_live
  Scope    commerce
  Col      orders

Audit Cluster:
  URI      couchbases://audit.example.invalid
  Bucket   audit_history
  Scope    events
  Col      order_events
~~~

Các host `example.invalid` chỉ để minh họa **không truy cập được**, không phải endpoints thực.

Order mẫu:

~~~json
{
  "order_id": "order-123",
  "customer_id": "customer-100",
  "status": "CREATED",
  "amount_vnd": 150000
}
~~~

Audit event:

~~~json
{
  "event_id": "evt-order-123-created",
  "aggregate_id": "order-123",
  "event_type": "ORDER_CREATED",
  "schema_version": 1
}
~~~

### 19.2. Các bước triển khai

1. Viết `PrimaryCouchbaseProperties` và `AuditCouchbaseProperties`, lấy secrets qua environment.
2. Khởi tạo hai `Cluster` beans đặt tên `primaryCluster`/`auditCluster`.
3. Khởi tạo `ordersCollection` và `auditEventsCollection` từ **đúng cluster**.
4. Tạo `OrderStore` và `AuditEventStore` nhận Collection qua `@Qualifier`, không đọc properties trực tiếp trong domain service.
5. Viết `OrderRepository`/`AuditEventRepository` nếu cần Spring Data; map mỗi repository tới đúng template/factory hoặc chọn SDK adapter để giữ route rõ hơn.
6. Provision keyspaces/indexes trên chính cluster có tài nguyên tương ứng, không chạy migration nhầm trên default connection.
7. Viết outbox event trên primary trong cùng order transaction hoặc workflow phù hợp, relay sang audit theo `eventId`.
8. Viết Testcontainers test với hai clusters chứa **cùng logical key**, nhưng marker khác nhau.
9. Assert Order write chỉ có ở primary; Audit write chỉ có ở audit.
10. Test Audit down: primary order behavior theo contract, không ngầm chuyển route.
11. Test read/sync lag: reporting/audit không bị coi là authoritative nếu chưa kịp bắt primary.
12. Test cleanup, RBAC denied, secrets missing và rollback/cutover logic.

### 19.3. Câu hỏi thiết kế

- Nếu dùng một `Cluster` và hai buckets thì đã là multi-cluster chưa? **Chưa**.
- `@Scope`/`@Collection` có tự chọn bucket khác không? **Không**.
- `configureRepositoryOperationsMapping` ảnh hưởng `CouchbaseTemplate` gọi trực tiếp không? **Không**.
- Có thể dùng `mapping.map` theo interface không? **Có**.
- Có thể dùng `mapping.mapEntity` cho mọi repo cùng entity không? **Có**, trừ mapping theo interface ưu tiên cao hơn.
- Khi mapping không tìm thấy repo/entity, điều gì xảy ra? **Fallback default operations**, nên phải kiểm tra fail-closed policy.
- Hai clusters có thể có cùng tên bucket và key không? **Có**, nhưng không phải cùng document.
- Một query trên primary có tự tìm dữ liệu audit không? **Không**.
- CAS của primary có dùng để replace audit document không? **Không**.
- Một `@Transactional` có bao bọc writes trên hai clusters không? **Không mặc định**.
- XDCR/outbox có thể chậm không? **Có**, phải đo lag và reconcile.
- Có thể tự failover write vào reporting cluster vì primary timeout không? **Không**, trừ một protocol failover đã được thiết kế/kiểm chứng.
- `Mono.zip` hai cluster calls có tạo transaction không? **Không**.
- Vì sao không dùng `ThreadLocal currentTenant` làm routing source duy nhất? Vì thread reuse/reactive scheduling và thiếu authorization.
- Đổi connection string trong ConfigMap có làm SDK Cluster object hiện tại tự chuyển đích? Không nên giả định; cần quy trình reload/recreate bean/cutover.
- Tại sao integration test cần hai containers? Để xác minh khác cluster thực sự, không chỉ khác bucket.

## 20. Checklist ứng dụng production

### A. Thiết kế ranh giới

- [ ] Có bảng capability → logical cluster → bucket/scope/collection.
- [ ] Phân biệt nhu cầu collection/bucket/cluster; không over-split vô cớ.
- [ ] Không dùng mutable global cluster/bucket để route request.
- [ ] Không lấy raw bucket/collection name trực tiếp từ HTTP input.
- [ ] Có nguồn authoritative rõ khi replication/XDCR hoặc read replica.
- [ ] Không giả định cross-cluster transaction atomic.

### B. Wiring và Spring Data

- [ ] Typed properties tách `primary`/`audit`, missing config fail startup.
- [ ] Mỗi `Cluster` bean được đặt tên và lifecycle `disconnect` đúng.
- [ ] Mỗi adapter dùng `@Qualifier` rõ; không che lỗi bằng `@Primary` ngầm.
- [ ] Một Cluster dùng nhiều buckets khi cùng cluster, không tạo pools thừa.
- [ ] Dùng đúng `CouchbaseClientFactory`/`CouchbaseTemplate` với bucket/cluster đích.
- [ ] Có tests cho `RepositoryOperationsMapping.map/mapEntity/resolve`.
- [ ] Hiểu mapping repositories không tự chuyển template/SDK calls.
- [ ] Reactive mapping cũng có tests và publishers được subscribe.
- [ ] Custom converters/type alias/encryption nhất quán đúng nơi dùng.

### C. Data access và bảo mật

- [ ] SQL++ query chạy trên đúng cluster và fully qualified keyspace.
- [ ] Indexes đúng scope/collection của từng cluster, được provision và ONLINE.
- [ ] `@Id`/`@Version`/CAS theo document ở đúng đích, không copy metadata CAS qua cluster.
- [ ] TTL/bucket maxTTL và durability policy được test trên từng destination.
- [ ] Cluster topology/replicas hỗ trợ durability được yêu cầu.
- [ ] RBAC tối thiểu, runtime không dùng migration/admin creds.
- [ ] TLS/trust store/hostname verification và secret rotation có quy trình.
- [ ] Không log credentials/PII/large dynamic tenant labels.
- [ ] Tenant authorization được kiểm tra với KV và SQL++, không chỉ một trong hai.

### D. Test, vận hành và thay đổi

- [ ] Có integration test 1 cluster/2 buckets và 2 clusters riêng.
- [ ] Có sentinel markers, same logical IDs và negative cross-target assertions.
- [ ] Không để test dùng credentials production.
- [ ] Có per-route health, latency, errors, index lag, outbox backlog metrics.
- [ ] Timeout/failure audit không làm Order ghi sang cluster khác.
- [ ] Outbox/idempotency/reconciliation cho cross-cluster data flow.
- [ ] Migration/cutover có backfill, checksum/parity và kế hoạch rollback.
- [ ] Có quy trình ngăn split-brain khi chuyển authoritative writer.
- [ ] Spring context cache/Testcontainers lifecycle được đồng bộ.
- [ ] Không xem test bằng Mockito hoặc chỉ bootstrap SDK là đủ chứng minh routing.
- [ ] Content QA chuyên môn thực hiện ở bước riêng, không đồng nhất với hoàn thành ghi Markdown.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Installation & Configuration](https://docs.spring.io/spring-data/couchbase/reference/couchbase/configuration.html): multi-bucket, `configureRepositoryOperationsMapping`/`configureReactiveRepositoryOperationsMapping`.
- [Spring Data Couchbase — AbstractCouchbaseConfiguration API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/config/AbstractCouchbaseConfiguration.html): client factory, template, mapping callbacks.
- [Spring Data Couchbase — RepositoryOperationsMapping API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/repository/config/RepositoryOperationsMapping.html): `map`, `mapEntity`, `setDefault`, `resolve`.
- [Spring Data Couchbase — SimpleCouchbaseClientFactory API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/SimpleCouchbaseClientFactory.html): tạo factory theo bucket/scope/cluster.
- [Spring Data Couchbase — Template and Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): `CouchbaseTemplate` và `ReactiveCouchbaseTemplate`.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): mapping, query/index.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`/`@Collection` và keyspace.
- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): multiple clusters, shared ClusterEnvironment, lifecycle.
- [Couchbase Java SDK — SDK Authentication](https://docs.couchbase.com/java-sdk/current/howtos/sdk-authentication.html): RBAC, authenticator, TLS.
- [Couchbase Java SDK — Provisioning Cluster Resources](https://docs.couchbase.com/java-sdk/current/howtos/provisioning-cluster-resources.html): bucket/scope/collection/index.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query parameters/scan consistency.
- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): cluster-bound transaction context.
- [Couchbase Server — XDCR](https://docs.couchbase.com/server/current/learn/clusters-and-availability/xdcr-overview.html): cross-cluster asynchronous replication.
- [Couchbase Server — Roles](https://docs.couchbase.com/server/current/learn/security/roles.html): role-based access control.
- [Spring Boot — Couchbase Auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): default `spring.couchbase`/`spring.data.couchbase.bucket-name`.
- [Spring Boot — Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html): typed properties/validation/secrets.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): isolated integration tests.





