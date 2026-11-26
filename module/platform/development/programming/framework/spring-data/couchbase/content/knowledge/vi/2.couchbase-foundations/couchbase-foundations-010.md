# Ranh giới giữa kiến thức cần cho ứng dụng và quản trị cụm chuyên sâu

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để đạt hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định **kiến thức Couchbase mà lập trình viên Spring Data phải nắm** để ứng dụng hoạt động chính xác.
2. Phân biệt **thiết kế truy cập dữ liệu** với **cấu hình và điều hành cluster production**.
3. Hiểu đủ về Data/Query/Index Service, vBucket, replica, failover và rebalance để đánh giá tác động lên request.
4. Làm rõ những quyết định **phải phối hợp**: index, quyền, quota, durability, capacity, backup và RPO/RTO.
5. Phân loại sự cố theo đường **KV**, **SQL++**, **mạng/TLS**, **cạnh tranh dữ liệu** hoặc **hạ tầng** trước khi chuyển cho đúng người xử lý.
6. Đề xuất index/schema migration, đo đạc và cung cấp bằng chứng kỹ thuật có ích cho DBA/SRE.
7. Chọn API đồng bộ, template hoặc reactive theo workload mà không nhầm kỹ thuật lập trình với việc tăng sức chứa cluster.

## 2. Ranh giới không phải là “developer không cần hiểu hạ tầng”

Một ứng dụng sử dụng Couchbase không thể hoàn toàn bỏ qua cách dữ liệu được lưu trữ và truy vấn. Tuy nhiên, **biết cơ chế** khác với **chịu trách nhiệm cấu hình cơ chế**.

Ví dụ:

- Developer cần biết `findById(id)` thường dùng KV đến Data Service, còn `findByStatus(...)` thường dùng SQL++ và Global Secondary Index (GSI).
- Developer cần biết failover có thể gây timeout và khiến kết quả mutation không rõ (*ambiguous outcome*).
- Nhưng developer không nhất thiết được giao chỉnh số node, memory quota, replica placement hoặc hard failover trong production.

Một nguyên tắc hữu ích:

> **Nhóm ứng dụng sở hữu tính đúng đắn và SLO của API; nhóm DBA/SRE/platform sở hữu sức khỏe, sức chứa và lifecycle của hệ thống database.** Những thay đổi ở ranh giới hai nhóm phải được phối hợp.

Ở một đội nhỏ, một người có thể kiêm cả phát triển và quản trị. Khi đó vẫn cần tách **quyền hạn, quy trình phê duyệt, backup, thử nghiệm và kế hoạch rollback**, thay vì bỏ kiểm soát vì “cùng một người làm”.

## 3. Ba tầng trách nhiệm

~~~mermaid
flowchart TD
    A["Application layer<br/>Spring Data + business logic"]
    B["Shared contract<br/>SLO, schema, index, RBAC, durability"]
    C["Cluster operations<br/>Topology, resources, failover, backup"]
    A --> B --> C
~~~

| Tầng | Quyết định điển hình | Người chủ trì |
|---|---|---|
| **Ứng dụng** | Document ID, JSON schema, repository, query, CAS, TTL, idempotency | Nhóm phát triển |
| **Giao thoa** | Index migration, RBAC, consistency, durability, capacity planning, DR objectives | Cùng thống nhất |
| **Cluster chuyên sâu** | Node/service placement, vBucket, failover/recovery, nâng cấp, backup/restore, tuning tài nguyên | DBA/SRE/platform hoặc dịch vụ managed |

Ranh giới này không cho phép developer đẩy mọi vấn đề hiệu năng sang DBA. Một query quét quá nhiều document hoặc một API ghi trùng vì thiếu idempotency vẫn cần sửa ở **ứng dụng**, dù cluster đã được quản lý tốt.

## 4. Bản đồ năng lực cần học

| Chủ đề | Developer cần thành thạo | Cần hiểu để chẩn đoán | DBA/SRE thường sở hữu |
|---|---|---|---|
| **Document ID/JSON** | Định danh, schema, mapping, validation | Hot key, document size | Quota và storage |
| **Bucket/scope/collection** | Chọn đúng keyspace | Quyền và ranh giới tài nguyên | Cấp/tổ chức tài nguyên |
| **KV/SQL++** | Chọn đúng API, dùng parameterized query | Data/Query/Index Service | Bố trí service và sizing |
| **GSI** | Thiết kế index theo query, đọc `EXPLAIN` | Index lag, IndexScan/Fetch/Sort | Index placement, replica, build |
| **CAS** | Optimistic locking và xử lý conflict | Contention, hot key | Điều tra resource nếu quá tải |
| **TTL** | Absolute/sliding expiry | MaxTTL và thay đổi khi update | Chính sách tài nguyên/retention |
| **Consistency** | KV vs SQL++, request_plus, mutation state | Index backlog | Tuning Index Service |
| **Durability** | Chọn yêu cầu và xử lý timeout mơ hồ | Replica, failover | HA topology và recovery |
| **Transaction** | Boundary, idempotency, external side effects | Isolation/retry/chi phí | Hỗ trợ phiên bản, tài nguyên |
| **Reactive** | Backpressure, concurrency, retry safety | Retry storm | Database capacity |
| **Security** | SDK TLS, secrets, least privilege | Network/DNS/RBAC | PKI, firewall, rotation |
| **Backup/DR** | Nêu RPO/RTO và kiểm thử ứng dụng sau restore | Khả năng mất dữ liệu | Backup/restore, XDCR, DR runbook |

Đây là **mức độ trách nhiệm**, không phải lệnh cấm học sâu. Khi developer được giao on-call hay vận hành cluster, phạm vi cần học và quyền thao tác cũng tăng theo.

## 5. Kiến thức bắt buộc: keyspace, document mapping và ID

Mô hình logic:

~~~text
Bucket: commerce
├── Scope: sales
│   ├── Collection: orders
│   └── Collection: payments
└── Scope: catalog
    └── Collection: products
~~~

Trong Spring Data Couchbase:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String status;
    private Long total;

    // Constructor, getter/setter được lược bỏ.
}
~~~

Developer phải hiểu:

- `@Id` xác định document trong collection tương ứng; cùng ID ở collection khác có thể là document khác.
- `@Scope` và `@Collection` xác định keyspace theo phiên bản Spring Data hỗ trợ.
- `@Version` thường được gắn với cơ chế CAS, khác với `schemaVersion` trong JSON.
- Quy tắc nghiệp vụ như `status = "PAID"` hay `total >= 0` là trách nhiệm của ứng dụng.
- ID phải ổn định trong retry nếu muốn idempotency. Ví dụ `tenant::42::order::1001` không ép các document cùng tenant lên một Data node.

### Đâu là phần của quản trị?

DBA/SRE có thể tạo bucket/collection, cấu hình quota, retention/maxTTL và RBAC. Nhưng họ không thể quyết định thay ứng dụng rằng một order được hủy sau thanh toán có hợp lệ hay không, hoặc cấu trúc một aggregate nên gồm những trường nào.

## 6. Kiến thức bắt buộc: KV và SQL++ là hai đường truy cập khác nhau

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId,
            String status);
}
~~~

~~~java
// Theo ID: thông thường là đường KV trên Data Service.
OrderDocument order = orderRepository
        .findById("tenant::42::order::1001")
        .orElseThrow();

// Theo thuộc tính: thông thường là SQL++ qua Query/Index Service.
List<OrderDocument> paidOrders =
        orderRepository.findByTenantIdAndStatus("42", "PAID");
~~~

Developer cần biết lựa chọn API quyết định thành phần chịu tải:

| Truy cập | Đường xử lý | Cần quan tâm |
|---|---|---|
| `findById`, `deleteById`, mutation theo ID | KV / Data Service | ID, latency KV, CAS, TTL, retry |
| Derived query theo trường | SQL++ / Query Service và thường là GSI | Query plan, Index Service, scan consistency |
| `CouchbaseTemplate` theo ID | Thường KV | Mapping và semantics mutation |
| Template/SDK chạy SQL++ | Query/Index Service | SQL++, index, query timeout |
| Reactive repository | Tùy operation là KV hay SQL++ | Concurrency, backpressure, retry |

**Tăng Data node không tự sửa SQL++ thiếu index.** Chuyển sang reactive cũng không làm một câu query thiếu predicate hoặc scan quá rộng trở nên tối ưu.

## 7. Kiến thức cần thành thạo về GSI, chưa cần vận hành Index Service

Developer nên viết được query SQL++:

~~~sql
SELECT META(o).id AS id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Và đề xuất chỉ mục phù hợp:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId, status, createdAt DESC
);
~~~

Sau đó kiểm tra:

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Ở mức ứng dụng, cần nhận diện IndexScan, Fetch, Filter và Sort/Order. Không nhất thiết tự thiết kế index replica/partitioning của Index node hoặc điều chỉnh tài nguyên memory/storage.

### Ranh giới thao tác trên production

| Công việc | App team | DBA/SRE |
|---|---|---|
| Mô tả query và đề xuất index | Chủ trì | Review |
| Kiểm tra câu SQL++ do Spring Data tạo | Chủ trì | Hỗ trợ nếu cần |
| Benchmark, đọc `EXPLAIN` | Chủ trì | Hỗ trợ tối ưu chuyên sâu |
| Tạo index dev/test | Theo quyền môi trường | Quản lý tài nguyên |
| Tạo/drop/build index production | Cung cấp migration và rollback | Chủ trì/phê duyệt theo quy trình |
| Phân bổ Index Service, replica/placement | Cung cấp SLO, tải | Chủ trì |

Không cấp đặc quyền tạo/drop index cho database user runtime của API chỉ vì muốn thao tác thuận tiện.

## 8. CAS: kiến thức nghiệp vụ chứ không chỉ kỹ thuật server

Hai request cùng đọc order:

~~~text
T0: status=NEW, CAS V1
T1: Request A đọc V1
T2: Request B đọc V1
T3: A ghi PAID → CAS V2
T4: B ghi CANCELLED dựa trên V1
~~~

Nếu B ghi đè không điều kiện, thay đổi của A có thể bị mất. **CAS** giúp phát hiện phiên bản đã thay đổi.

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.java.kv.GetResult;

GetResult current = orders.get("tenant::42::order::1001");

orders.replace(
    "tenant::42::order::1001",
    current.contentAsObject().put("status", "PAID"),
    replaceOptions().cas(current.cas())
);
~~~

Ứng dụng phải:

1. Kiểm tra phép chuyển trạng thái hợp lệ.
2. Bắt CAS mismatch/optimistic locking conflict.
3. Đọc lại và đánh giá business rule khi thử lại.
4. Có giới hạn retry; không bỏ CAS để “ghi cho được”.
5. Viết test cho hai request đồng thời.

DBA/SRE không cần tham gia mỗi CAS conflict bình thường. Họ có thể cần điều tra nếu một hot key gây contention, độ trễ server hoặc retry storm vượt khả năng hệ thống.

## 9. TTL/expiry: business lifecycle và chính sách cluster

Developer quyết định session tồn tại bao lâu, giỏ hàng hết hạn khi nào và dữ liệu thanh toán phải được lưu bao lâu. TTL/expiry là metadata Couchbase, khác với field `expiresAt` mà ứng dụng tự lưu trong JSON.

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

sessions.upsert(
    "session::abc123",
    sessionBody,
    upsertOptions().expiry(Duration.ofMinutes(30))
);
~~~

Developer cần hiểu:

- **Absolute expiry:** không vượt mốc cố định.
- **Sliding expiry:** có thể gia hạn theo hoạt động hợp lệ.
- `touch`, `getAndTouch` hoặc `preserveExpiry` theo SDK/version và policy.
- Một thao tác update có thể thay đổi hạn; phải test rõ.
- Document hết hạn không được xem là còn tồn tại trên KV; quá trình dọn vật lý/index có thể khác thời điểm hết hạn.
- TTL không phải scheduler bảo đảm gửi notification đúng một thời điểm.

DBA/SRE đặt giới hạn cấu hình như bucket/collection maxTTL theo phiên bản, quản trị dung lượng và chính sách retention. **Hai đội phải thống nhất** để maxTTL ở hạ tầng không vô tình xóa order trước hạn cần thiết.

## 10. Scan consistency: quyết định của ứng dụng, tài nguyên của cluster

GSI được Index Service cập nhật **bất đồng bộ** sau mutation ở Data Service. Vì vậy, lệnh KV ghi xong không chứng minh một query SQL++ theo field thấy thay đổi ngay.

| Trường hợp | API/cơ chế phù hợp | Ghi chú |
|---|---|---|
| Biết ID, cần đọc document vừa lưu | KV `get(id)` | Không cần scan GSI |
| Danh sách cho phép cập nhật trễ | SQL++ `not_bounded` | Có thể chưa thấy mutation mới |
| Danh sách phải theo kịp trước thời điểm query | `request_plus` | Có thể chờ index/backlog |
| Query phải nhìn thấy mutation đã biết | `MutationState` và `consistentWith` | Cần token/result theo SDK |
| Đọc replica | API replica read có chủ đích | Có thể đọc dữ liệu cũ |

Ví dụ SDK:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var rows = cluster.query(
    "SELECT META(o).id AS id, o.status " +
    "FROM `commerce`.`sales`.`orders` AS o " +
    "WHERE o.tenantId='42' AND o.status='PAID'",
    queryOptions().scanConsistency(QueryScanConsistency.REQUEST_PLUS)
).rowsAsObject();
~~~

Developer cần chọn mức consistency theo SLA của endpoint; DBA/SRE cần xử lý khi Index Service backlog khiến `request_plus` chờ quá lâu.

CAS không ép GSI cập nhật nhanh hơn. Thêm node không thay thế việc dùng index đúng.

## 11. Durability, replica và failover: hiểu hệ quả, phân vai rõ ràng

Developer cần phân biệt:

- **Atomicity:** thao tác trên một document là một đơn vị mutation, transaction phục vụ nhiều document khi phù hợp.
- **Durability:** mức đảm bảo mutation đã được xác nhận tồn tại trước những lỗi được định nghĩa.
- **Availability:** khả năng tiếp tục phục vụ khi node/service không khả dụng.
- **Query freshness:** GSI đã theo kịp thay đổi nào.

Các mức synchronous durability hỗ trợ theo phiên bản/loại bucket có thể gồm:

| Mức | Ý nghĩa khái quát |
|---|---|
| Không yêu cầu durability đồng bộ bổ sung | Ack theo semantics mutation mặc định |
| `MAJORITY` | Yêu cầu xác nhận theo đa số bản dữ liệu liên quan |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Đa số xác nhận và active persist |
| `PERSIST_TO_MAJORITY` | Persist tới đa số theo cơ chế hỗ trợ |

Không mức nào thay thế backup/restore hoặc tránh lỗi logic như xóa nhầm. Replica cũng không đảm bảo mọi mutation không yêu cầu durability đã có mặt trên bản sao trước response.

### Developer sở hữu phần nào?

- Nêu RPO/RTO của nghiệp vụ; cùng đội vận hành chọn durability thích hợp.
- Xử lý timeout mơ hồ (**ambiguous outcome**) thay vì luôn mặc định ghi thất bại.
- Dùng ID/idempotency key ổn định khi client retry.
- Đo độ trễ mutation và tỷ lệ durability failure.
- Viết test cạnh tranh, retry và failover được kiểm soát.

### DBA/SRE sở hữu phần nào?

- Số node, data replica, index replica, failure domain và capacity N-1.
- Failover, recovery, rebalance, maintenance/upgrades.
- Kiểm tra topology và đường mạng để SDK có thể nhận cluster map.
- Backup/restore, DR và monitoring replica/cluster health.

## 12. Transaction nhiều document: boundary xuất phát từ invariant

Nếu một workflow phải đồng thời tạo order và giữ tồn kho trong Couchbase, nhiều mutation KV riêng lẻ không tự nguyên tử với nhau. Developer có thể cần **Couchbase Transactions**.

~~~java
cluster.transactions().run(ctx -> {
    var stock = ctx.get(inventory, "inventory::sku-A1");
    var current = stock.contentAsObject();
    long available = current.getLong("availableStock");

    if (available < 1) {
        throw new IllegalStateException("Hết hàng");
    }

    ctx.replace(
        stock,
        current.put("availableStock", available - 1)
    );

    ctx.insert(
        orders,
        "tenant::42::order::1001",
        com.couchbase.client.java.json.JsonObject.create()
            .put("status", "RESERVED")
            .put("sku", "A1")
            .put("quantity", 1)
    );
});
~~~

Ví dụ minh họa API transaction Java SDK; code production cần validation, exception handling, idempotency và xác minh hỗ trợ của phiên bản server/SDK.

Đặc biệt: **transaction callback có thể được SDK thực hiện lại** trong một số tình huống xung đột. Không gọi payment gateway, gửi email hoặc publish message không idempotent trực tiếp trong callback. Các hệ thống ngoài Couchbase cần saga/outbox/idempotency theo kiến trúc phù hợp.

Developer quyết định invariant, boundary và xử lý lỗi. DBA/SRE xác minh capacity, compatibility và sức khỏe cluster khi workload transaction lớn. Không mặc định `@Transactional` của Spring tự cấu hình multi-document Couchbase transaction nếu chưa kiểm chứng transaction manager thực tế.

## 13. Reactive: khác cách viết, không khác sức chứa vật lý

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId,
        String status);
}
~~~

API reactive dùng `Mono`/`Flux`, hỗ trợ tổ chức pipeline I/O bất đồng bộ. Nhưng:

- Một document hot vẫn gây tranh chấp trên active vBucket.
- Query SQL++ vẫn có GSI index lag và chi phí Index Service.
- `retryWhen` có thể **resubscribe** và thực hiện lại mutation có side effect.
- Backpressure không cung cấp durability, consistency hay transaction.
- Concurrency lớn có thể đẩy Data/Query/Index Service vào quá tải.

Developer cần quản lý concurrency, deadline và retry. DBA/SRE cần được cung cấp các số liệu tải thực tế nếu bottleneck ở cluster. Chuyển từ repository đồng bộ sang reactive **không** là biện pháp tự động sửa một query quá tốn tài nguyên.

## 14. Network, TLS, secrets và RBAC là trách nhiệm chung

Một cluster hoàn toàn khỏe mạnh có thể không thể truy cập từ ứng dụng do DNS, firewall, certificate, authentication hoặc quyền database.

Ví dụ cấu hình Spring Boot dùng placeholder:

~~~yaml
spring:
  couchbase:
    connection-string: "<COUCHBASE_CONNECTION_STRING>"
    username: "<COUCHBASE_USERNAME>"
    password: "<COUCHBASE_PASSWORD>"
  data:
    couchbase:
      bucket-name: "commerce"
~~~

Placeholder phải được thay bằng cấu hình và secrets từ môi trường triển khai. Tên property cần xác minh theo Spring Boot/Spring Data version. Với TLS, connection scheme thường là `couchbases://` khi endpoint hỗ trợ và yêu cầu kết nối bảo mật.

| Công việc | Ứng dụng | DBA/SRE/Security |
|---|---|---|
| Connection string, credentials ở runtime | Cấu hình/tích hợp secret manager | Cung cấp endpoint/database user |
| RBAC | Liệt kê quyền đọc/ghi/query cần thiết | Cấp quyền least privilege |
| TLS | Xác minh trust/hostname, không bypass cert | PKI, chứng chỉ, network policies |
| DNS/firewall | Kiểm tra từ đúng runtime, cung cấp lỗi | Route, DNS, firewall, private connectivity |
| Secret rotation | Hỗ trợ reload/reconnect, không log secret | Chính sách và kế hoạch rotation |
| Đa tenant | Kiểm tra tenant trong business code | Isolation/RBAC theo thiết kế hệ thống |

Không dùng database admin credential cho runtime API, không tắt certificate verification để chữa lỗi kết nối, và không ghi secrets vào issue/tracing.

## 15. vBucket, rebalance và failover: hiểu đủ để phản ứng đúng

Developer cần biết:

- vBucket là phân vùng logic; SDK dựa vào document ID và cluster map để tìm active Data node.
- Replica là bản sao phục vụ HA, không phải backup và không mặc nhiên luôn mới nhất.
- Rebalance di chuyển phân vùng khi topology thay đổi, có thể làm tăng tải hoặc latency.
- Failover đưa bản replica phù hợp lên làm active theo điều kiện cluster, có thể phát sinh timeout/mutation ambiguous.
- SDK tự quản lý topology/routing; ứng dụng không tự viết hàm hash chọn node.
- `NOT_MY_VBUCKET` có thể liên quan map cũ, không phải bằng chứng document bị xóa.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant SDK as Couchbase Java SDK
    participant Old as Old active Data node
    participant New as New active Data node
    App->>SDK: get(documentId)
    SDK->>Old: KV request theo map cũ
    Old-->>SDK: Routing error/timeout có thể xảy ra
    Note over SDK: Refresh cluster map
    SDK->>New: Retry theo chính sách và deadline
    New-->>SDK: Document nếu sẵn sàng
    SDK-->>App: Kết quả hoặc lỗi cuối
~~~

Không suy ra SDK sẽ luôn retry thành công trong mọi trường hợp. Mutation có thể không an toàn khi retry do kết quả ghi trước đó chưa rõ.

**Những việc developer không tự ý làm ở production:** hard failover, xóa node, đổi replica count, chạy rebalance, drop index, chỉnh quota hệ thống hoặc disable TLS. Những thao tác này có thể ảnh hưởng **nhiều ứng dụng cùng cluster**.

## 16. Danh mục quản trị chuyên sâu cần biết tên, chưa cần thao tác

| Chuyên môn | Công việc điển hình | App team cung cấp gì |
|---|---|---|
| **Topology** | Số node, Data/Query/Index Service placement | Workload và SLO |
| **Capacity** | RAM, CPU, disk/IOPS, network, quotas | Dung lượng, tốc độ tăng, peak traffic |
| **HA** | Data/index replicas, failover, recovery | RTO/RPO, endpoints quan trọng |
| **Data movement** | Rebalance, node replacement, upgrades | Cửa sổ bảo trì, compatibility test |
| **Index administration** | Index replica, partition/build/rebuild | Query, explain/profile, index proposal |
| **Storage maintenance** | Persistence, compaction, engine settings theo version | Retention, churn, write rate |
| **Security infrastructure** | TLS PKI, firewall, network segmentation, audit | Runtime identities và least privilege |
| **Backup/DR** | Backup policy, restore drills, XDCR/DR | Dữ liệu thiết yếu, yêu cầu khôi phục |
| **Monitoring** | Service health, capacity và alert thresholds | Traces, request metrics và business impact |

Trong Couchbase Capella, nhà cung cấp quản lý nhiều tác vụ hạ tầng. Nhóm ứng dụng vẫn chịu trách nhiệm về schema, index, user/role, backup policy theo khả năng dịch vụ và logic truy cập. Các tùy chọn thực tế phụ thuộc tier/cloud/region, không thể coi mọi Capella deployment giống nhau.

## 17. RACI: ai quyết định và ai làm?

RACI dùng các vai trò: **R** = thực hiện, **A** = chịu trách nhiệm kết quả/quyết định, **C** = tham vấn, **I** = được thông báo.

| Công việc | App team | DBA/SRE | Security |
|---|---|---|---|
| Document ID và schema nghiệp vụ | **R/A** | C | I |
| SQL++ và index proposal | **R/A** | C | I |
| Tạo/rebuild index production | C | **R/A** | I |
| Quy tắc CAS, transaction, TTL và idempotency | **R/A** | C | C |
| Replica/failover/rebalance | C | **R/A** | I |
| RBAC runtime/rotation | R (yêu cầu) | R (cấp) | A theo policy |
| Backup/restore | C (test application) | **R/A** | C |
| SLO ứng dụng | **R/A** | C | I |
| Sizing/upgrade cluster | C | **R/A** | C |

Đây là gợi ý, không phải mô hình bắt buộc. Ở một tổ chức khác, security/platform hoặc nhà cung cấp dịch vụ có thể đảm nhiệm thêm vai trò. Điều quan trọng là mỗi công việc có owner và quy trình phê duyệt.

## 18. Quy trình đề xuất index an toàn

Một ticket “database chậm, tăng RAM” thiếu nhiều thông tin. Developer nên cung cấp:

~~~text
Service: order-api
Environment: staging, dự kiến production sau review
Keyspace: commerce.sales.orders
Endpoint: GET /orders?tenantId=...&status=...
SQL++: đã parameterize, không kèm dữ liệu nhạy cảm
SLO nội bộ (ví dụ): p95 < 200 ms ở 500 req/s
Hiện trạng (ví dụ): p95 850 ms, scan 80.000 entries/query
Bằng chứng: EXPLAIN/profile + khung thời gian đo
Đề xuất: ix_orders_tenant_status_created
Chi phí: storage/index maintenance, build time
Kế hoạch: test tải trước/sau + rollback
Owner: app team, DBA review
~~~

Các con số ở trên là **giả định giảng dạy**, không phải benchmark thật của Couchbase.

Ticket tốt chứa **triệu chứng, tác động, bằng chứng, phương án, chi phí, owner và validation**. Không cần developer biết cách tự phân bố Index replica trên các node để yêu cầu một index mới.

## 19. Triage sự cố: chọn đúng người xử lý

| Triệu chứng | Developer kiểm tra trước | Escalate khi |
|---|---|---|
| `findById` not-found | ID, keyspace, TTL, xóa thực sự, quyền | Nhiều ID biến mất hoặc có dấu hiệu sự cố cluster |
| KV theo ID chậm | Tracing, body size, retry, hot key | Data node quá tải, rebalance, lỗi network |
| Derived query chậm | SQL++, `EXPLAIN`, GSI, predicate, sort | Index/Query Service backlog hoặc thiếu capacity |
| KV có doc, SQL++ chưa thấy | Scan consistency, index lag, filter | `request_plus` chờ quá lâu, index offline |
| CAS conflict | Business rule, concurrent writers, retry | Conflict đột biến kèm hot key/server overload |
| Session hết hạn bất thường | TTL, preserveExpiry, touch, maxTTL | Cấu hình bucket/collection hoặc chính sách cluster |
| Durability timeout | SDK exception, deadline, replica requirement | Replica/node health hoặc failover |
| Kết nối lỗi sau scale | SDK version, DNS, TLS, credentials | Topology/address/network policy |
| Permission denied | User/role cần thiết, keyspace | Cấp RBAC theo quy trình |
| Duplicate sau retry | ID/idempotency, ambiguous result | Nếu có bằng chứng sự cố hạ tầng đồng thời |

### Năm bước triage

1. Xác định **KV hay SQL++**, đọc hay ghi, đồng bộ hay reactive.
2. Xác nhận **bucket/scope/collection/ID** và điều kiện tenant/TTL.
3. Thu thập **thời điểm, tần suất, exception, timeout, p95/p99, correlation ID**.
4. Tái hiện có kiểm soát, ưu tiên staging/dữ liệu giả lập; không thử ghi đè production.
5. Chuyển đến đúng owner với bằng chứng và tác động nghiệp vụ, không chỉ gửi ảnh chụp màn hình lỗi.

## 20. Observability: hai tầng cùng nhìn một sự cố

### Developer theo dõi

- p50/p95/p99 của KV get, mutation và SQL++ riêng biệt.
- Error rate: document-not-found, CAS conflict, duplicate, timeout, ambiguous outcomes.
- Query latency, scan consistency, truy vấn slow và số entry scan khi quan sát được.
- Retry count/concurrency, `retryWhen` và deadline trong reactive pipeline.
- Business metrics: order duplicate, payment double-charge, invalid state transition, unexpected expiry.
- Trace IDs và khung thời gian trước/sau deploy.

### DBA/SRE theo dõi

- Data/Query/Index Service health, throughput và saturation.
- CPU, memory, disk/IOPS, network, node/replica states.
- Active/replica vBucket placement, rebalance và failover.
- GSI availability/index lag, backup success và DR readiness.

~~~text
Application dashboard:
  - HTTP API latency/errors
  - KV latency/errors/ambiguous outcomes
  - SQL++ latency + query/index diagnostics
  - Business consistency/idempotency

Cluster dashboard:
  - Data Service capacity/replicas
  - Query + Index Service saturation/backlog
  - Topology events/rebalance/failover
  - Backup/restore/security events
~~~

Một đồ thị “cluster healthy” không tự chứng minh đơn hàng không bị tạo trùng. Ngược lại, một CAS conflict nghiệp vụ không tự chứng minh node database đang lỗi. Cần kết hợp dữ liệu qua timestamp/correlation ID và che/redact secrets, PII.

## 21. Quy trình thay đổi schema/index trong release

Một PR thêm derived query mới không nên được deploy trước khi index cần thiết đã sẵn sàng.

1. **Thiết kế data contract:** JSON, ID, schemaVersion, TTL, business invariant.
2. **Liệt kê đường truy cập:** KV/SQL++, predicate, sort, pagination, consistency.
3. **Lập migration:** GSI mới, tài nguyên, thời gian build và rollback.
4. **Review với DBA/SRE:** tác động storage, Index Service và các ứng dụng khác.
5. **Thử staging:** dữ liệu/traffic đại diện, query plan và p95/p99.
6. **Triển khai đúng thứ tự:** index sẵn sàng trước khi bật code phụ thuộc nó.
7. **Quan sát sau release:** query errors, latency, index lag, CAS conflict.
8. **Có điều kiện rollback:** rollback code và data/index migration được thiết kế riêng.

Các thay đổi cần review đặc biệt: đổi ID format, bật TTL mặc định ở collection lưu dài hạn, `request_plus` toàn hệ thống, thêm nhiều index trùng chức năng, chuyển sang transaction nhiều document hoặc bật retry tự động trên mutation không idempotent.

## 22. Case study: tăng node hay tối ưu query?

Ứng dụng có endpoint:

~~~text
GET /orders?tenantId=42&status=PAID
p95: 900 ms
SLO ví dụ: p95 < 200 ms
GET /orders/{id} vẫn nhanh
~~~

Một developer yêu cầu tăng Data node vì “database chậm”. Cách phân tích hiệu quả hơn:

1. Endpoint bị chậm là SQL++ theo field, không phải KV theo ID.
2. Lấy SQL++ thực của Spring Data, kiểm tra điều kiện `tenantId`/`status` và `_class` nếu framework thêm.
3. Dùng `EXPLAIN`, xem GSI được chọn và số entry scan/Fetch/Sort.
4. Tạo index proposal, đo trên staging và so sánh trước/sau.
5. Nếu query đã tối ưu nhưng Index Service vẫn quá tải, cung cấp số liệu để DBA/SRE quyết định sizing và placement.

**App team** chịu trách nhiệm query/index proposal; **DBA/SRE** chịu trách nhiệm Index Service resource và rollout index production. Cả hai cùng chịu trách nhiệm SLO cuối cùng.

## 23. Case study: trùng đơn sau failover

API `POST /orders` gửi `insert`. Khi node failover, request nhận timeout và client gửi lại.

Nếu mỗi lần retry tạo một document ID mới, hệ thống có thể tạo **hai đơn cho một checkout** dù từng mutation KV là nguyên tử.

### Luồng idempotent

~~~mermaid
flowchart TD
    A["POST /orders + idempotency key"]
    B["Tính order ID ổn định"]
    C["insert theo ID"]
    D{"Kết quả?"}
    E["Success → trả order"]
    F["Duplicate → đọc/đối chiếu request"]
    G["Timeout ambiguous → kiểm tra ID"]
    H{"Trạng thái hợp lệ đã có?"}
    I["Trả kết quả đã lưu"]
    J["Retry có giới hạn hoặc báo cần xác minh"]
    A --> B --> C --> D
    D -->|"Success"| E
    D -->|"Duplicate"| F
    D -->|"Ambiguous"| G
    G --> H
    H -->|"Có"| I
    H -->|"Chưa rõ"| J
~~~

Phân vai:

- **Developer:** ID/idempotency ổn định, xử lý ambiguous outcome, không charge payment hai lần.
- **DBA/SRE:** kiểm tra failover, replica health, routing, RPO/RTO, vì sao timeout vượt SLO.
- **Cả hai:** chọn durability, diễn tập và đo độ sẵn sàng sau node failure.

Không thể kết luận chỉ từ một timeout rằng lỗi hoàn toàn ở ứng dụng hay hoàn toàn ở cluster.

## 24. Khi nào cần học quản trị cụm chuyên sâu?

Developer có thể cần mức học sâu hơn khi:

- Trở thành tech lead chịu trách nhiệm capacity hoặc dữ liệu phân tán.
- Được giao production on-call với quyền xử lý sự cố database.
- Đảm nhiệm vai trò SRE/DBA/platform.
- Xây dựng hệ thống có hot key, transaction contention, GSI khổng lồ hoặc write-heavy workloads.
- Tham gia migration cluster, backup/restore DR, failover, version upgrades.
- Cần tối ưu network/storage/CPU ở tầng hạ tầng.

Lộ trình:

| Mức | Kiến thức | Mục tiêu |
|---|---|---|
| **Foundation** | Document, KV, SQL++, GSI, CAS, TTL | Viết API đúng |
| **Production-aware** | SDK topology, replica, durability, scan consistency, metrics | Chẩn đoán và phối hợp |
| **Platform collaboration** | Index review, capacity planning, DR objectives, security | Đề xuất và review thay đổi |
| **Operator** | Failover/recovery/rebalance runbooks, upgrades, storage/network tuning | Vận hành production theo quyền được giao |

Thực hành quyền operator ở lab được kiểm soát và quy trình tổ chức, **không chạy failover hoặc restore trên production chỉ để học**.

## 25. Bài tập tự đánh giá

### Bài tập A — ai chịu trách nhiệm?

Phân loại công việc theo nhóm ứng dụng, DBA/SRE hoặc phối hợp:

1. Đặt `@Id`, `@Version` cho `OrderDocument`.
2. Tạo GSI mới trong production.
3. Chọn RPO cho thanh toán.
4. Hard failover một Data node.
5. Chẩn đoán session hết hạn sớm do TTL.
6. Cấp database user quyền đọc/ghi collection.
7. Viết idempotent retry sau ambiguous mutation.
8. Diễn tập backup/restore và xác minh API sau phục hồi.

### Bài tập B — lỗi ở lớp nào?

`findById` nhanh nhưng `findByStatus` chậm. Nêu 5 bước điều tra trước khi xin tăng Data node và xác định số liệu nào cần lấy từ `EXPLAIN`.

### Bài tập C — CAS và nghiệp vụ

Hai request đồng thời đổi `NEW → PAID` và `NEW → CANCELLED`. Tại sao thêm `@Version` giúp phát hiện xung đột nhưng chưa quyết định chuyển trạng thái nào hợp lệ?

### Bài tập D — TTL và retention

Bucket có maxTTL làm order hết hạn sớm hơn chính sách lưu trữ. Ai phát hiện qua test? Ai quyết định retention nghiệp vụ? Ai thay setting và review tác động?

### Bài tập E — reactive và resource

Sau khi chuyển sang `ReactiveCouchbaseRepository`, ứng dụng mở concurrency lớn làm Query latency tăng. Hãy giải thích vì sao reactive không tự cấp thêm Index Service và đề xuất các metric phối hợp.

### Bài tập F — bảo mật kết nối

SDK bootstrap lỗi khi chuyển sang môi trường khác. Mô tả cách kiểm tra DNS, TLS/CA, firewall, database user và quyền **không tắt certificate verification** và không ghi password vào log.

### Bài tập G — đề xuất index

Viết một ticket migration index production gồm SQL++ parameterized, `EXPLAIN`, dự báo tải, rủi ro, người duyệt, cách benchmark và rollback.

## 26. Checklist trước production

### Phạm vi ứng dụng

- [ ] Định nghĩa bucket/scope/collection, document ID, schema và tenant boundary.
- [ ] Phân biệt KV theo ID với SQL++ theo field; query có GSI phù hợp.
- [ ] Có CAS/`@Version` cho read-modify-write cần chống lost update.
- [ ] Có chính sách TTL, expiry và retention có kiểm thử.
- [ ] Chọn consistency, durability và transaction theo business SLO/invariant.
- [ ] Có ID/idempotency và xử lý timeout/ambiguous write.
- [ ] Reactive concurrency/retry được giới hạn và có backpressure phù hợp.
- [ ] Có metric/tracing, bảo vệ secrets và PII.

### Phối hợp vận hành

- [ ] Index migration được DBA/SRE review, có plan rollback.
- [ ] Runtime user chỉ có quyền cần thiết, không dùng admin account.
- [ ] Kết nối DNS/TLS/network được kiểm thử từ đúng môi trường ứng dụng.
- [ ] Đã thỏa thuận replica, RPO/RTO, backup/restore, năng lực chịu lỗi.
- [ ] Có kênh escalation cho Data/Query/Index Service và failover.
- [ ] Đã thử tải với dữ liệu/traffic đại diện và đo p95/p99.
- [ ] Không thực hiện thay đổi cluster production ngoài change process.
- [ ] Có xác minh ứng dụng sau schema/index/cluster version change.

## 27. Tổng kết

Lập trình viên **Spring Data Couchbase** cần thành thạo **document mapping, ID, bucket/scope/collection, KV, SQL++, chỉ mục, CAS, TTL, scan consistency, transaction boundary, retry/idempotency và lựa chọn API reactive**. Họ cũng cần hiểu đủ về vBucket, replica, failover và Index Service để nhận diện tác động lên request và trao đổi chính xác với đội vận hành.

**Quản trị cụm chuyên sâu** tập trung vào topology, sizing, node/service placement, failover/recovery/rebalance, storage, index administration, TLS/network, backup và DR. Tại ranh giới hai tầng, cần thống nhất quyền, chỉ mục, durability, HA, SLO, kế hoạch triển khai và trách nhiệm xử lý sự cố.

**Năng lực quan trọng nhất không phải biết mọi lệnh quản trị, mà là viết ứng dụng đúng, nhận diện rủi ro đúng lớp và cung cấp bằng chứng để phối hợp với người vận hành đúng lúc.**
