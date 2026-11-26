# Đánh giá chi phí của REQUEST_PLUS, độ bền và giao dịch

## 1. Ba cơ chế giải quyết ba câu hỏi khác nhau

Trong ứng dụng Spring Data Couchbase, một thao tác ghi order thành công nhưng SQL++ truy vấn ngay theo `customerId` có thể chưa thấy order đó. Nhóm phát triển bật `REQUEST_PLUS` và kết quả trở nên đúng hơn theo yêu cầu độ mới, nhưng p99 tăng. Nhóm khác tăng mức durability để tránh mất cập nhật khi node gặp sự cố. Luồng checkout lại cần cùng lúc thay order và inventory, nên dùng transaction.

Cả ba quyết định đều có thể tăng chi phí, nhưng không thể đánh đồng:

- **Query scan consistency `REQUEST_PLUS`:** Query service cần mức độ mới của **chỉ mục** phù hợp với truy vấn tại thời điểm request.
- **Durability của KV write:** Couchbase phải thỏa điều kiện xác nhận bản ghi trên các bản sao/thiết bị lưu trữ trước khi coi mutation thành công ở mức được yêu cầu.
- **Transaction nhiều document:** một đơn vị nghiệp vụ gồm nhiều đọc/ghi được thực hiện theo bảo đảm giao dịch, có kiểm soát xung đột và commit/rollback.

Bài **“Đánh giá chi phí của REQUEST_PLUS, độ bền và giao dịch”** thuộc chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Module tập trung vào document mapping, repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để giữ hiệu năng, nhất quán và khả năng vận hành.

Sau bài này, bạn có thể:

1. Giải thích vì sao một KV GET theo key và một SQL++ query theo secondary index có thể nhìn thấy kết quả ở thời điểm khác nhau.
2. Phân biệt `NOT_BOUNDED`, `REQUEST_PLUS` và cơ chế ràng buộc query với mutation token.
3. Lựa chọn các mức durability SDK theo rủi ro mất dữ liệu và khả năng cluster.
4. Hiểu chi phí phát sinh của transaction: đọc/ghi bổ sung, metadata, xung đột, retry và commit.
5. Chứng minh durability, query freshness và transaction atomicity **không thay thế nhau**.
6. Lập benchmark latency, goodput, errors, index lag và tài nguyên cho từng lựa chọn.
7. Giữ đúng hợp đồng nghiệp vụ khi tối ưu; không đánh đổi tính đúng đắn để lấy số p99 đẹp.

Các ví dụ định hướng Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x và Couchbase Server hỗ trợ synchronous durability và transactions. Cú pháp API, giới hạn, tên exception và hành vi theo phiên bản cần được kiểm tra bằng dependency và cluster đang sử dụng; đây không phải cam kết về mọi bản server.

## 2. Tình huống xuyên suốt: thanh toán và lịch sử đơn hàng

Giả sử hệ thống sử dụng:

~~~text
Bucket: commerce
Scope: sales
  Collection: orders
  Collection: inventory
Scope: checkout
  Collection: carts
Scope: finance
  Collection: payments
~~~

Một document order:

~~~json
{
  "docType": "order",
  "tenantId": "tenant-a",
  "customerId": "u-42",
  "status": "PAID",
  "createdAtEpochMs": 1795582800000,
  "total": 150000,
  "inventoryReserved": false
}
~~~

Các câu hỏi:

- “Tôi vừa ghi một order. Truy vấn danh sách order của customer có thấy nó ngay không?”
- “Server báo ghi thành công. Nếu node active hỏng ngay sau đó thì bản ghi có được giữ không?”
- “Order chuyển sang CONFIRMED nhưng inventory giảm thất bại, có thể để hệ thống ở trạng thái nửa vời không?”

Ba câu hỏi yêu cầu ba cơ chế khác nhau. Hãy định nghĩa **đầu ra cần bảo đảm** trước khi tối ưu thời gian xử lý.

## 3. Bản đồ ra quyết định ban đầu

~~~mermaid
flowchart TD
    A["Use case Couchbase"] --> B{"Đọc bằng exact document ID?"}
    B -- "Có" --> C["KV GET: không đợi GSI"]
    B -- "Không, truy vấn SQL++" --> D{"Cần thấy mutation mới ngay?"}
    D -- "Không" --> E["NOT_BOUNDED hoặc chính sách độ mới yếu hơn"]
    D -- "Có" --> F{"Có mutation token của chính writes?"}
    F -- "Có" --> G["Đánh giá consistentWith(MutationState)"]
    F -- "Không" --> H["Đánh giá REQUEST_PLUS"]
    A --> I{"Ghi phải chịu lỗi node theo mức nào?"}
    I --> J["Chọn durability phù hợp"]
    A --> K{"Nhiều document cần atomic commit?"}
    K -- "Có" --> L["Transaction hoặc kiến trúc nghiệp vụ tương đương"]
    K -- "Không" --> M["KV mutation + CAS khi cần"]
~~~

Sơ đồ là hướng dẫn phân loại, không phải thuật toán tự động áp dụng trong mọi service. Một checkout vừa cần transaction **vừa** cần durability; một API đọc danh sách sau commit vẫn có thể cần query consistency phù hợp.

## 4. Ba chiều bảo đảm: freshness, durability, atomicity

| Câu hỏi | Cơ chế chính | Không bảo đảm điều gì |
| --- | --- | --- |
| SQL++ thấy dữ liệu mới trong GSI chưa? | `REQUEST_PLUS` hoặc mutation-state consistency | Không tự làm write bền hơn |
| Mutation sống sót lỗi node theo mức yêu cầu? | Durability level | Không tự làm GSI cập nhật tức thì |
| Nhiều document thay đổi cùng nhau? | Transaction | Không miễn mọi chi phí query consistency bên ngoài |
| Một mutation dựa trên phiên bản đã đọc còn hợp lệ? | CAS / `@Version` | Không tạo transaction nhiều document |
| Document tự hết hạn đúng policy? | TTL/expiry, `maxTTL` | Không phải consistency hoặc durability |
| Một request có quyền tác động document? | Authentication/authorization | Không được giải quyết bằng những cơ chế trên |

**Nguyên tắc:** một thay đổi cấu hình hiệu năng có thể tác động tới ranh giới đảm bảo, nên benchmark phải so các phương án có cùng correctness contract.

## 5. Vì sao KV GET và SQL++ có thể cho kết quả khác nhau?

SDK KV thao tác theo document key trong Data service. SQL++ query trên field như `customerId` thường dựa vào **secondary index (GSI)** được cập nhật bất đồng bộ từ mutations.

~~~mermaid
sequenceDiagram
    participant App as Spring Service
    participant Data as Data Service
    participant Index as Index Service
    participant Query as Query Service
    App->>Data: Upsert order::O-1
    Data-->>App: Mutation acknowledged
    Data-->>Index: Index update stream (async)
    App->>Data: KV GET order::O-1
    Data-->>App: Order found
    App->>Query: SELECT WHERE customerId = u-42
    Query->>Index: Scan index
    Note over Query,Index: Nếu index chưa bắt kịp, row có thể chưa xuất hiện
    Index-->>Query: Current indexed rows
    Query-->>App: Query result
~~~

Một SQL++ query không thấy order ngay sau upsert **không tự chứng minh write thất bại**. Có thể chỉ là độ trễ cập nhật index. Khi chẩn đoán phải kiểm tra đúng keyspace, index, query plan và scan consistency.

### 5.1. Từ một key đến một predicate

Nếu đã biết key `order::O-1`, dùng `repository.findById` hoặc `collection.get` khi phù hợp; chúng không cần chờ secondary index.

Nếu yêu cầu “đơn hàng của khách A, trạng thái PAID, mới nhất trước”, caller không có sẵn danh sách keys: SQL++/Index service vẫn là đường truy cập cần thiết.

Không bật `REQUEST_PLUS` để “sửa” độ trễ của một KV GET theo key; đó là hai đường khác nhau.

## 6. `NOT_BOUNDED`: ưu tiên throughput khi chấp nhận độ trễ chỉ mục

Một SQL++ query có thể không yêu cầu đợi index bắt kịp mutations mới nhất:

~~~java
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var opts = QueryOptions.queryOptions()
        .scanConsistency(QueryScanConsistency.NOT_BOUNDED);
~~~

`NOT_BOUNDED` là một lựa chọn phù hợp cho màn hình, báo cáo hoặc tìm kiếm mà **độ trễ hiển thị rất ngắn** có thể được chấp nhận theo hợp đồng.

Nó không có nghĩa query trả dữ liệu tùy tiện hoặc luôn cũ; kết quả phụ thuộc trạng thái index thực tế khi scan. Nhưng ứng dụng **không yêu cầu** Query đợi tới độ mới mà `REQUEST_PLUS` đòi hỏi.

### 6.1. Ví dụ áp dụng

- Danh sách sản phẩm cập nhật gần đây, cho phép trễ vài giây theo SLO.
- Dashboard thống kê không yêu cầu phản ánh tức thời mọi mutation.
- Các truy vấn browse/search không dùng làm quyết định thanh toán.

Không dùng `NOT_BOUNDED` mặc định cho một luồng phải xác nhận order vừa ghi nếu business contract đòi read-your-writes qua SQL++.

## 7. `REQUEST_PLUS` giải quyết yêu cầu nào?

Trong Couchbase Java SDK 3.x, Query API cho phép:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;

var options = QueryOptions.queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
~~~

Ý tưởng: Query service đợi các index tham gia truy vấn đạt mức cập nhật tương ứng với mutations đã tồn tại ở đầu yêu cầu (theo server/query contract), thay vì quét ngay một trạng thái index có thể chưa bắt kịp.

**Đây là yêu cầu về index scan freshness.** Nó không biến mọi SQL++ query thành một giao dịch snapshot xuyên nhiều document và không tự khiến ghi đã bền tới mọi replica.

### 7.1. Chi phí nằm ở đâu?

Nếu Index service đang chậm, backlog lớn hoặc đang chịu tải mutation cao, query có thể **đợi** index bắt kịp, làm tăng latency. Mức tăng phụ thuộc lag, query plan, số index/keyspace liên quan, topology và tải thực; không có con số “REQUEST_PLUS luôn cộng 20 ms”.

Một query có index đã cập nhật đầy đủ có thể có chênh lệch rất nhỏ giữa `NOT_BOUNDED` và `REQUEST_PLUS` ở một thời điểm. Khi có burst writes, p99 có thể chênh lệch đáng kể.

### 7.2. Timeout và stale result không phải một lựa chọn nhị phân đơn giản

Nếu yêu cầu không đạt trong thời gian cho phép, query có thể timeout hoặc báo lỗi. Không catch timeout rồi âm thầm chạy lại `NOT_BOUNDED` nếu luồng cần dữ liệu mới để quyết định nghiệp vụ.

## 8. SQL++ query hoàn chỉnh dùng `REQUEST_PLUS`

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

public final class RecentOrdersReader {

    private final Cluster cluster;

    public RecentOrdersReader(Cluster cluster) {
        this.cluster = cluster;
    }

    public java.util.List<JsonObject> find(
            String authorizedTenantId,
            String customerId) {

        String sql = """
                SELECT META(o).id AS id,
                       o.status,
                       o.createdAtEpochMs,
                       o.total
                FROM `commerce`.`sales`.`orders` AS o
                WHERE o.tenantId = $tenant
                  AND o.customerId = $customer
                ORDER BY o.createdAtEpochMs DESC
                LIMIT 20
                """;

        return cluster.query(
                sql,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("tenant", authorizedTenantId)
                                .put("customer", customerId))
                        .scanConsistency(
                                QueryScanConsistency.REQUEST_PLUS)
        ).rowsAsObject();
    }
}
~~~

`authorizedTenantId` phải lấy từ context đã xác thực, không chỉ tin giá trị trong URL. Truy vấn được parameterized, trả giới hạn 20 row và có index phù hợp, nhưng **REQUEST_PLUS không thay thế quyền truy cập hoặc tối ưu index**.

### 8.1. Chỉ chọn consistency sau khi chốt yêu cầu

Nếu màn hình danh sách cho phép eventual consistency, dùng `REQUEST_PLUS` trên mọi request có thể tăng chi phí không cần. Nếu vừa xác nhận chuyển trạng thái rồi cần hiển thị ngay bằng SQL++, đây là ứng viên đáng thử.

## 9. Query consistency theo mutation token: giới hạn mục tiêu phải đợi

SDK Java có kiểu `MutationState` để ràng buộc query với các mutation mà client đã biết, khi mutation token có sẵn:

~~~java
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.kv.MutationResult;

MutationResult write = orders.upsert(
        "order::O-2026-001",
        orderJson
);

MutationState state = MutationState.from(write);

var rows = cluster.query(
        LIST_ORDERS_SQL,
        QueryOptions.queryOptions()
                .parameters(parameters)
                .consistentWith(state)
).rowsAsObject();
~~~

Các biến `orders`, `orderJson`, `LIST_ORDERS_SQL` và `parameters` do service khởi tạo. Đây là ví dụ cơ chế `AT_PLUS`/mutation-state consistency qua SDK; kiểm tra availability của token và chữ ký API theo version đang dùng.

Khác biệt quan trọng:

- `REQUEST_PLUS` yêu cầu độ mới rộng hơn tại thời điểm request theo Query service contract.
- `consistentWith(state)` yêu cầu index ít nhất phản ánh **những mutation tokens đã chỉ định**, phù hợp khi application cần read-your-own-writes mà đã có token.
- Truy vấn có thể ít phải đợi hơn so với `REQUEST_PLUS` trong workload ghi mạnh, **nhưng không được giả định luôn nhanh hơn**.

### 9.1. Không dùng CAS thay mutation token

CAS được dùng cho optimistic concurrency trên document. `MutationToken`/`MutationState` dùng cho query/index consistency. Chúng không phải cùng loại định danh, không thể gán trực tiếp CAS vào `consistentWith`.

### 9.2. Token lifecycle và nhiều writes

Nếu cần đọc kết quả của **nhiều mutation** qua SQL++, phải tích lũy những mutation states/tokens cần thiết theo SDK contract. Không lấy token của order A rồi mặc định query phải thấy mutation độc lập trên inventory B.

## 10. Khi không cần REQUEST_PLUS: chọn KV theo key

Sau khi tạo order thành công:

~~~java
orders.upsert("order::O-2026-001", orderJson);

var current = orders.get(
        "order::O-2026-001"
).contentAsObject();
~~~

Đây là một key-based lookup phù hợp nếu chỉ cần kiểm tra order đó. Không cần query:

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE META(o).id = "order::O-2026-001";
~~~

chỉ để ép `REQUEST_PLUS` xử lý tính nhất quán. Một KV GET không cần GSI; dùng SQL++ khi muốn lọc/sort/aggregate trên nhiều document.

**Lưu ý:** KV behavior vẫn phụ thuộc operation success, keyspace, failover và transaction visibility. Đây không phải cam kết về mọi kiểu đọc replica hoặc snapshot.

## 11. Truy vấn SQL++ có index kém vẫn chậm dù không đợi

Hai nguyên nhân độ trễ khác nhau:

1. **Index freshness wait** do `REQUEST_PLUS`.
2. **Execution cost** do index scan, Fetch, Sort/Join/Aggregation.

Nếu query phải scan hàng triệu entries, chuyển từ `REQUEST_PLUS` sang `NOT_BOUNDED` chỉ có thể giảm phần đợi index mà không sửa query plan. Hãy xem:

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-a"
  AND o.customerId = "u-42"
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Nên kiểm tra leading index keys, spans, Fetch, Order, Limit pushdown và cardinality. **Index phù hợp và projection nhỏ thường là tối ưu cấu trúc**, còn scan consistency là lựa chọn về độ mới.

## 12. Quan sát index lag thay vì gán mọi p99 cho REQUEST_PLUS

Nếu p99 tăng khi bật `REQUEST_PLUS`:

- Đo Query duration, queue time, timeout rate theo consistency level.
- Kiểm tra Index service CPU, memory, disk, scan latency và lag/backlog nếu telemetry version cung cấp.
- Xem lượng KV mutations/giây và index updates trong cùng cửa sổ.
- Ghi thứ tự build index, rebalance, failover hoặc rolling upgrade.
- Tách query plan/params cố định giữa hai phép đo.
- Theo dõi client network/GC để không nhầm bottleneck ở tầng khác.

Không tuyên bố có một metric tên cố định cho “index lag” trong mọi Couchbase release. Dùng metric thực tồn tại ở cluster đang triển khai và ghi rõ nguồn.

## 13. Durability: một chiều khác hẳn Query freshness

Khi SDK gọi `collection.upsert` hoặc `replace`, nó nhận acknowledgement theo semantics của mutation. Nếu không yêu cầu mức durability mạnh hơn, thành công không có nghĩa đã bảo đảm persistence/replication giống một write có synchronous durability.

**Durability** trả lời câu hỏi:

> “Nếu node hoặc một phần cluster gặp lỗi ngay sau acknowledgement, mức nào của dữ liệu đã được replica/persist theo cam kết?”

Nó **không trả lời** câu hỏi “Query index đã cập nhật để SELECT theo customerId chưa?”.

Một ứng dụng có thể đặt:

- Durability cao nhưng SQL++ `NOT_BOUNDED` vẫn chưa thấy mutation mới.
- Durability mặc định và `REQUEST_PLUS` giúp query nhìn thấy dữ liệu vừa ghi nhưng không nâng bảo đảm tồn tại sau failover.
- Durability + transaction để đáp ứng commit nhiều document, còn query consistency xử lý visibility ngoài giao dịch.

## 14. Synchronous durability và các mức trong SDK

Couchbase Java SDK 3.x có `DurabilityLevel`, thường bao gồm:

| Mức | Điều kiện khái niệm | Chi phí thường gặp |
| --- | --- | --- |
| `NONE` | Không yêu cầu synchronous durability bổ sung | Thường latency thấp hơn nhưng mức chịu lỗi yếu hơn |
| `MAJORITY` | Mutation đạt đa số bản sao liên quan | Đợi replicated acknowledgements |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Đạt majority và active persist | Thêm điều kiện persistence ở active |
| `PERSIST_TO_MAJORITY` | Đạt persistence trên majority theo cluster contract | Có thể đợi thêm I/O trên nhiều node |

Bảng mô tả **bản chất lựa chọn**, không phải thời gian thực tế cố định. Một mức durability cao có thể khiến p99 phụ thuộc replica lẫn disk tail latency. Cấu hình replicas, bucket type và server version ảnh hưởng mức nào được hỗ trợ.

### 14.1. Chọn mức dựa trên hậu quả, không theo khẩu hiệu

- Một event metric có thể chịu mất một lần cập nhật trong sự cố.
- Một order được công bố “đã thanh toán” thường cần đánh giá rủi ro mất mutation nghiêm túc.
- Một job checkpoint idempotent có thể tái lập; durability contract khác bản ghi tài chính.
- Một đơn đặt hàng có deadline không tự yêu cầu mức durability cao hơn chỉ vì TTL ngắn.

**Không tự biến ví dụ thành chính sách bắt buộc**. Phải đối chiếu RPO, RTO, khả năng khôi phục và yêu cầu tổ chức.

## 15. Java SDK: đặt durability cho KV mutation

Ví dụ với `upsert`:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.kv.UpsertOptions;

var result = orders.upsert(
        "order::O-2026-001",
        orderJson,
        UpsertOptions.upsertOptions()
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Nếu nghiệp vụ đòi thêm persistence active và server hỗ trợ:

~~~java
var result = orders.upsert(
        "order::O-2026-002",
        anotherOrder,
        UpsertOptions.upsertOptions()
                .durability(
                        DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);
~~~

Đây là ví dụ SDK; `orders` là Collection đúng keyspace, `orderJson`/`anotherOrder` là JSON được validate trước. Trong production, tránh `upsert` vô điều kiện nếu update phải có CAS hoặc create-only.

### 15.1. `replace` với CAS và durability

~~~java
import com.couchbase.client.java.kv.ReplaceOptions;

var existing = orders.get(id);

var newJson = existing.contentAsObject();
newJson.put("status", "PACKED");

orders.replace(
        id,
        newJson,
        ReplaceOptions.replaceOptions()
                .cas(existing.cas())
                .preserveExpiry(true)
                .durability(DurabilityLevel.MAJORITY)
);
~~~

CAS bảo vệ **concurrency**, `preserveExpiry` bảo vệ **TTL policy**, durability bảo vệ **ghi theo mức yêu cầu**. Ba option không hoán đổi cho nhau.

## 16. Sub-document mutation cũng có chi phí durability

Một update chỉ thay một path:

~~~java
import java.util.List;
import com.couchbase.client.java.kv.MutateInOptions;
import com.couchbase.client.java.kv.MutateInSpec;
import com.couchbase.client.java.kv.StoreSemantics;

orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "SHIPPED"),
                MutateInSpec.upsert("updatedAtEpochMs", now)
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
                .durability(DurabilityLevel.MAJORITY)
);
~~~

`mutateIn` có thể tiết kiệm bytes khi chỉ sửa vài path, nhưng **không bỏ qua** replication/persistence và index maintenance theo durability/collection. Không so full replace durability mạnh với mutateIn durability yếu rồi tuyên bố phần lớn lợi ích do subdocument.

## 17. Durability phụ thuộc cluster topology và loại bucket

Durable writes cần đủ bản sao/nodes và cơ chế lưu trữ tương ứng để thỏa yêu cầu. Khi replicas không đủ, node mất kết nối, disk chậm hoặc bucket không hỗ trợ persistence cấp được yêu cầu, operation có thể không thành công hoặc timeout.

Đánh giá trước khi bật ở quy mô lớn:

1. Number of replicas của bucket và phân bố node.
2. Failover/rebalance scenarios.
3. Data service disk IOPS, latency và capacity.
4. Bucket engine/type (persistent vs memory-oriented theo version).
5. SDK/server versions hỗ trợ synchronous durability.
6. Timeout budget và chuẩn xử lý ambiguous outcome.
7. Peak write throughput, không chỉ một request thử thành công.

**Không bật `PERSIST_TO_MAJORITY` một cách máy móc** nếu cluster không có cấu hình thỏa; lỗi durability là lỗi thật cần được surfaced.

## 18. Durability và latency: phần đợi thêm đến từ đâu?

Một KV mutation đơn giản có thể đợi acknowledgement của active Data service. Yêu cầu durability cao hơn thường đưa thêm điều kiện từ replica và/hoặc storage.

~~~mermaid
sequenceDiagram
    participant App as Java Service
    participant Active as Active Data Node
    participant Replica as Replica Data Node
    participant Disk as Persistence
    App->>Active: UPSERT with durability
    Active->>Replica: Replicate mutation
    Active->>Disk: Persist when level requires
    Replica-->>Active: Replication/durability progress
    Disk-->>Active: Persistence status
    Active-->>App: Acknowledge after requested conditions
~~~

Đây là sơ đồ **khái niệm**. Số replicas cần xác nhận và điều kiện disk chính xác phụ thuộc durability level và server contract; không phải mọi operation luôn phải đợi mọi mũi tên trong sơ đồ.

Chi phí quan sát có thể xuất hiện ở p95/p99, write goodput, Data service CPU/I/O, timeout và memory pressure. Mức chênh lệch có thể nhỏ dưới tải thấp nhưng tăng mạnh khi disk hoặc replica bị nghẽn.

## 19. Durability timeout và trạng thái mơ hồ

Nếu SDK báo timeout hoặc một dạng **ambiguous durability outcome**, client không được mặc nhiên kết luận “write chắc chắn chưa thành công”.

Trong một số tình huống server có thể đã áp dụng mutation, nhưng client chưa nhận được sự xác nhận đầy đủ. Với các thao tác không idempotent như increment hoặc array append, retry ngay có thể tạo thay đổi lần hai.

Quy trình:

1. Phân loại exception theo SDK/version và tính chất operation.
2. Nếu outcome mơ hồ, đối soát trạng thái document bằng key/idempotency marker phù hợp.
3. Không lặp vô hạn với cùng operation khi cluster đã quá tải.
4. Với nghiệp vụ thanh toán, dùng idempotency key hoặc ledger/outbox theo thiết kế.
5. Ghi metrics và trace để vận hành biết số ambiguous outcomes.

**Durability mạnh không có nghĩa network timeout trở thành impossible.** Error handling vẫn là một phần correctness.

## 20. CAS, durability và TTL phải được tách biệt

Giả sử hai writers cùng muốn sửa order:

~~~text
Writer A: GET order + CAS c1
Writer B: GET order + CAS c1
Writer A: REPLACE CAS c1 -> success, CAS thành c2
Writer B: REPLACE CAS c1 -> conflict
~~~

`@Version` trong Spring Data Couchbase có thể kết nối optimistic locking với CAS ở các API mapping tương ứng. Nhưng durability `MAJORITY` **không ngăn lost update nếu không dùng CAS đúng chỗ**.

Tương tự, `@Document(expiry)` hoặc SDK expiry options không tự chọn durability. Một write bền không làm document sống quá TTL, và một document sống lâu không mặc nhiên được lưu bền qua sự cố.

### 20.1. Không vô tình reset expiry khi nâng durability

Khi chuyển từ repository save sang SDK `replace`/`mutateIn` để điều khiển durability, phải kiểm tra có giữ expiry metadata không. `preserveExpiry(true)` chỉ phù hợp với server/options hỗ trợ và chính sách không renew deadline.

## 21. Transaction giải quyết điều gì?

Giả sử thanh toán đơn hàng đòi hai cập nhật Couchbase:

~~~text
orders/order::O-2026-001:
  status: PAID -> CONFIRMED

inventory/stock::SKU-A:
  available: 10 -> 8
~~~

Nếu thực hiện hai mutation độc lập:

~~~text
1) order confirmed -> thành công
2) stock giảm -> thất bại do conflict/timeout
~~~

thì trạng thái nghiệp vụ có thể bị lệch. **Couchbase Transactions** là công cụ để nhóm các thao tác trên nhiều document thành một đơn vị commit theo các bảo đảm mà server/SDK cung cấp.

Transaction là **lựa chọn correctness** trước khi là lựa chọn performance. Nó thường tạo thêm chi phí so với một KV mutation độc lập, nhưng bỏ transaction để giảm latency không hợp lệ nếu nghiệp vụ yêu cầu atomic commit.

## 22. Mô hình transaction và chi phí phát sinh

Một transaction thường có:

- Đọc các document và phiên bản liên quan.
- Stage mutations và metadata cần thiết.
- Kiểm tra xung đột/commit protocol.
- Commit hoặc rollback/cleanup.
- Retry transaction logic khi lỗi có thể thử lại.
- Durability để giữ trạng thái commit phù hợp contract.

Couchbase transactions sử dụng cơ chế nội bộ như metadata giao dịch và quản lý trạng thái mutation. Chi tiết triển khai (ví dụ ATR/xattrs ở những phiên bản) không nên được xem là API mà ứng dụng tự can thiệp.

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Đọc order + inventory"]
    B --> C{"Business invariants hợp lệ?"}
    C -- "Không" --> D["Abort / reject"]
    C -- "Có" --> E["Stage order + stock changes"]
    E --> F{"Conflict/commit thành công?"}
    F -- "Có" --> G["Committed"]
    F -- "Có thể retry" --> H["SDK retry transaction attempt"]
    H --> B
    F -- "Thất bại không retry" --> I["Báo lỗi / đối soát outcome"]
~~~

**Không dự đoán chi phí chỉ bằng số dòng Java trong lambda.** Một transaction có thể phát sinh thêm round trips, metadata writes và conflict retries.

## 23. Java SDK: ví dụ transaction nhiều document

Ví dụ SDK Java Transactions API ở phiên bản tương thích:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public final class CheckoutCommitter {

    private final Cluster cluster;
    private final Collection orders;
    private final Collection inventory;

    public CheckoutCommitter(
            Cluster cluster,
            Collection orders,
            Collection inventory) {
        this.cluster = cluster;
        this.orders = orders;
        this.inventory = inventory;
    }

    public void confirm(
            String orderId, String stockId, int reserved) {

        if (reserved <= 0) {
            throw new IllegalArgumentException(
                    "Reservation amount must be positive");
        }

        cluster.transactions().run(ctx -> {
            var orderRead = ctx.get(orders, orderId);
            var stockRead = ctx.get(inventory, stockId);

            JsonObject order = orderRead.contentAsObject();
            JsonObject stock = stockRead.contentAsObject();

            if (!"PAID".equals(order.getString("status"))) {
                throw new IllegalStateException(
                        "Invalid order transition");
            }

            int available = stock.getInt("available");
            if (available < reserved) {
                throw new IllegalStateException(
                        "Insufficient inventory");
            }

            order.put("status", "CONFIRMED");
            stock.put("available", available - reserved);

            ctx.replace(orderRead, order);
            ctx.replace(stockRead, stock);
        });
    }
}
~~~

Ví dụ cho thấy nhiều document được thao tác thông qua **transaction context**, không phải gọi `orders.replace` và `inventory.replace` bên ngoài rồi mong chúng tự commit cùng nhau.

Production còn cần validate tenant/ownership, lock/counter policies, deadline, idempotency và kết hợp kết quả thanh toán từ hệ thống ngoài. Chữ ký API và các options giao dịch nên kiểm tra theo SDK version cụ thể.

### 23.1. Không thực hiện side effect không thể rollback trong transaction lambda

Cơ chế transaction có thể **retry lambda**. Không gửi email, gọi cổng thanh toán, phát sự kiện ngoài hệ thống hoặc ghi log audit một lần-duy-nhất theo cách không idempotent **bên trong lambda** rồi giả định nó chỉ chạy đúng một lần.

Một phương án phổ biến là ghi một outbox event **trong cùng đơn vị dữ liệu có bảo đảm** và phát side effect sau commit theo cơ chế idempotent. Đối với dịch vụ ngoài Couchbase, dùng saga/outbox phù hợp.

## 24. Transaction và durability: không tùy tiện hạ mức

Transaction có quy tắc durability/configuration riêng theo SDK/server. Không coi mỗi `ctx.replace` trong transaction là một KV replace thông thường để tự truyền mọi loại `ReplaceOptions` giống ngoài transaction.

Khi đánh giá:

- Xác định mức durability của transaction API theo version và cấu hình thực tế.
- Không giả định giá trị mặc định giống `Collection.upsert` không có options.
- Chọn mức đủ theo rủi ro mất dữ liệu của **toàn transaction**.
- Kiểm tra tính hỗ trợ của cluster/topology.
- Đo thời gian commit, retry và failure rate.

Một so sánh “transaction chậm hơn hai upsert” có thể đúng về latency nhưng vô nghĩa nếu hai upsert **không bảo đảm atomicity** mà transaction phải bảo đảm.

## 25. Isolation và visibility không đồng nghĩa Query REQUEST_PLUS

Một transaction cần có semantics về đọc/ghi trước/sau commit và cách xử lý conflicts. `REQUEST_PLUS` là một lựa chọn scan consistency của SQL++ **ngoài transaction**.

Không khẳng định:

- Bật `REQUEST_PLUS` biến hai UPSERT thành một transaction.
- Giao dịch đã commit thì mọi SQL++ query `NOT_BOUNDED` ngay sau đó lập tức thấy hết các thay đổi qua GSI.
- Chỉ dùng durability `MAJORITY` là đủ để nhìn thấy mọi row trong Query index.
- Một client đọc nhiều document bằng các GET riêng lẻ sẽ tự nhận snapshot nhất quán tại một thời điểm.

Khi đọc kết quả **bên trong transaction**, dùng transaction context/API hỗ trợ. Khi cần truy vấn SQL++ bên ngoài sau commit, đánh giá scan consistency riêng theo contract.

### 25.1. Nguồn gốc của những lời hứa quá mức

Từ “strong consistency” thường được dùng cho nhiều khía cạnh: read-your-writes, index freshness, atomic visibility, failure durability, CAS concurrency. Hãy đặt câu hỏi **mạnh ở chiều nào** trước khi bật một option.

## 26. Retry transaction: chi phí và tính đúng đắn

Transaction SDK có thể retry các attempt khi gặp xung đột hoặc lỗi có thể phục hồi theo API. Khi retry, code trong transaction function có thể chạy lại, làm tăng:

- Số KV reads và staged writes.
- Số lần kiểm tra business invariants.
- Thời gian elapsed end-to-end.
- Tải metadata/Data service.
- Áp lực lên hot keys và CAS contention.

Tuy nhiên, **không tự retry toàn bộ giao dịch bên ngoài** không giới hạn nếu SDK đã có retry semantics; bạn có thể tạo retry storm hoặc side effects trùng.

Đo hai mức:

1. **Business transaction attempts:** bao nhiêu request checkout được tiếp nhận, thành công/thất bại.
2. **Internal transaction attempts/operations:** bao nhiêu lần SDK phải làm lại công việc, theo telemetry được hỗ trợ.

Không đếm một transaction thành công sau ba attempts là ba checkout được phục vụ.

## 27. Hot document và transaction contention

Nếu nhiều checkout đồng thời sửa cùng document `stock::global`, concurrency conflicts có thể làm tỷ lệ retry tăng. Tăng HTTP threads hoặc reactive flatMap concurrency chưa chắc tăng goodput.

Cân nhắc:

- Partition/shard inventory theo SKU/warehouse nếu business cho phép.
- Giảm số writer cùng key.
- Dùng atomic counter/subdocument increment cho trường độc lập khi đủ semantics.
- Tách reservation records hoặc event/outbox theo thiết kế.
- Ghi nhận transaction conflict rate, retry attempts và p99.
- Thiết kế backoff/admission control khi cluster quá tải.

**Đừng đổi multi-document transaction thành mutation vô điều kiện chỉ để tránh conflict**, nếu làm mất yêu cầu nguyên tử.

## 28. So sánh chi phí: ba trục độc lập

Một bảng quyết định:

| Use case | Query freshness | Durability | Transaction |
| --- | --- | --- | --- |
| Xem danh sách catalog ít đổi | Có thể `NOT_BOUNDED` | Theo pipeline cập nhật catalog | Thường không cho read |
| Tạo cart tạm | KV GET theo ID, không cần GSI | Theo rủi ro mất cart | Một document có thể không cần |
| Tạo order cần bền | Query consistency tùy luồng đọc sau | Đánh giá `MAJORITY` hoặc mức cao hơn | Nếu ghi một doc có thể không cần |
| Xác nhận order + reserve inventory | SQL++ sau commit có thể cần freshness | Theo mức transaction/API | Có nếu cần atomic multi-doc |
| Ghi metric lượt xem | Có thể eventual | Có thể chấp nhận thấp | Thường không |
| Báo cáo batch cuối ngày | Theo SLA dữ liệu | Dữ liệu nguồn theo policy | Không nhất thiết |
| OTP/session deadline | KV key, tránh Query nếu có ID | Theo security/business | Không mặc định |
| Thanh toán qua hệ thống ngoài Couchbase | Tùy query UI | Cần durable audit/idempotency | Transaction Couchbase không bao trùm hệ thống ngoài |

Bảng mang tính **phân tích yêu cầu**, không phải chính sách bắt buộc cho mọi tổ chức. Mọi lựa chọn phải có owner, tiêu chí thất bại chấp nhận được và kiểm thử.

## 29. Nên tối ưu gì trước khi giảm consistency?

Nếu `REQUEST_PLUS` khiến p99 cao:

1. Kiểm tra use case có thật sự cần SQL++ ngay sau write không.
2. Nếu đã biết ID, thử KV GET cho **đúng** document đó.
3. Nếu có mutation token, đánh giá `consistentWith(MutationState)` để giảm phạm vi phải chờ.
4. Tối ưu chỉ mục theo `WHERE`/`ORDER BY` và projection.
5. Kiểm tra index backlog, Data/Index CPU, disk và topology.
6. Đánh giá batching/thời gian thực hiện ghi để giảm burst nếu business cho phép.
7. Cân nhắc cache/async view update chỉ khi không phá consistency/authorization.
8. Nếu vẫn cần `REQUEST_PLUS`, ghi nhận chi phí và đặt SLO khả thi.

**Không đổi sang `NOT_BOUNDED` chỉ để đạt SLO latency** khi yêu cầu sản phẩm phải phản ánh mutation mới.

## 30. Chi phí của durability có thể giảm bằng thiết kế

Nếu write p99 tăng khi bật `PERSIST_TO_MAJORITY`:

- Xác minh workload có thật sự đòi persistence trên majority.
- Kiểm tra replica count, disk IOPS/latency và network giữa nodes.
- Xác minh bottleneck có nằm ở durability wait thay vì JSON serialization/mapper.
- Giảm document size hoặc số thao tác không cần thiết.
- Gộp các path changes của **một document** bằng `mutateIn` khi đúng semantics.
- Tránh cập nhật cùng hot document quá thường xuyên.
- Tuning timeout/cluster resources theo số liệu, không giấu lỗi bằng timeout vô hạn.

Không hạ durability của audit tài chính chỉ vì một benchmark staging báo tăng p95. Hãy quay lại failure model/RPO và đánh giá chi phí vận hành.

## 31. Chi phí của transaction có thể giảm bằng data modeling

Nếu một nghiệp vụ chỉ phải thay hai field trên **cùng một document**, một `mutateIn` nhiều specs có thể atomic mà không cần transaction nhiều document.

Ngược lại, nếu cần thay order và inventory **ở hai keys khác nhau**, `mutateIn` trên mỗi key không tạo atomicity chung.

Ví dụ:

~~~java
// Một document: nhiều specs atomically trong một KV mutation.
orders.mutateIn(
        orderId,
        java.util.List.of(
                MutateInSpec.replace("status", "CONFIRMED"),
                MutateInSpec.upsert(
                        "inventoryReserved", true)
        )
);
~~~

Đoạn trên chỉ đúng nếu business invariant **thực sự nằm hết trong document order**. Nó không cập nhật document inventory thật.

Câu hỏi kiến trúc: có thể thiết kế aggregate/document boundary sao cho một business invariant thuộc một document mà không tạo hot key/giant document? Nếu có, có thể giảm chi phí giao dịch. Nếu không, ưu tiên correctness.

## 32. Spring Data repositories và durability: xác minh API thật

Một `CouchbaseRepository<OrderDocument, String>` có thể cung cấp `save`, `findById` và optimistic locking `@Version` theo mapper. Nhưng đừng mặc định mỗi repository method đều expose các options của SDK như:

~~~java
UpsertOptions.upsertOptions()
        .durability(DurabilityLevel.MAJORITY);
~~~

Hoặc tùy chọn consistency:

~~~java
QueryOptions.queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
~~~

Các abstraction của Spring Data và chữ ký API thay đổi theo release. Nếu một use case cần điều khiển durability/scan consistency chính xác mà public repository/template API chưa hỗ trợ trực tiếp:

1. Dùng cấu hình công khai phù hợp ở version hiện tại nếu có.
2. Nếu vẫn cần, tạo custom SDK gateway cho hot path.
3. Giữ converter/type metadata, `@Version`, TTL, validation và authorization.
4. Integration test đường repository và SDK sau refactor.
5. Không sử dụng reflection/hack giả định method không tồn tại.

### 32.1. `save` và sự khác biệt của transaction

Không gọi `repository.save` bên trong SDK transaction lambda rồi mặc định nó trở thành một staged write của transaction context. Khi cần giao dịch, dùng API được transaction framework hỗ trợ cho các document đó.

## 33. Reactive/async làm thay đổi concurrency chứ không xóa chi phí

Một reactive query có consistency:

~~~java
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var result =
        cluster.reactive().query(
                LIST_ORDERS_SQL,
                QueryOptions.queryOptions()
                        .parameters(params)
                        .scanConsistency(
                                QueryScanConsistency.REQUEST_PLUS)
        );
~~~

`cluster.reactive().query` trả publisher kết quả reactive theo SDK version; dùng `var` ở đây để không nhầm kiểu `QueryResult` của SDK blocking với kết quả reactive. Operation được thực thi khi subscribe theo ngữ nghĩa Reactor.

Reactive không khiến Index service cập nhật nhanh hơn hoặc durability acknowledgements ít hơn. Nó có thể giúp quản lý I/O không blocking và concurrency. Nhưng nếu `flatMap` mở quá nhiều query `REQUEST_PLUS` cùng lúc, Query/Index service vẫn có thể nghẽn.

### 33.1. Không block event loop

Đừng `block()` một query reactive trong WebFlux handler. Dùng `map`, `flatMap`, `onErrorResume` theo hợp đồng, phân loại timeout/invalid states, giới hạn in-flight và không nuốt lỗi.

## 34. Mô hình đo: ba biến kiểm thử không được trộn

Để đánh giá riêng từng cơ chế, tạo ba nhóm thí nghiệm:

**Nhóm Q — Query freshness:**

~~~text
Q1: SQL++ query with NOT_BOUNDED
Q2: SQL++ query with REQUEST_PLUS
Q3: SQL++ consistentWith(MutationState) khi có tokens

Giữ cùng statement/parameters/index/dataset/traffic.
Ghi thêm index lag, read-after-write assertion và query errors.
~~~

**Nhóm D — Write durability:**

~~~text
D1: KV UPSERT/REPLACE with NONE/default
D2: KV write with MAJORITY
D3: KV write with MAJORITY_AND_PERSIST_TO_ACTIVE
D4: KV write with PERSIST_TO_MAJORITY

Giữ payload, key distribution, CAS/expiry và offered load.
Ghi replicas/disk/topology, ambiguous errors, write p99.
~~~

**Nhóm T — Atomicity/transaction cost:**

~~~text
T1: Một KV mutation trên một document
T2: Một transaction trên hai documents
T3: Một transaction dưới contention cao

Không coi T1 tương đương T2 về chức năng.
Mục tiêu là phân tích overhead theo yêu cầu nguyên tử.
~~~

Khi cần xem tổ hợp Q+D+T, chạy thêm ma trận hỗn hợp có kiểm soát; đừng đổi cả ba biến trong một lượt rồi quy chi phí cho một yếu tố.

## 35. Latency, throughput, errors và bytes: định nghĩa baseline

Một report cần tối thiểu:

| Metric | Q: Query | D: Durable write | T: Transaction |
| --- | --- | --- | --- |
| p50/p95/p99 elapsed | Có | Có | Có |
| Completed business goodput/s | Có | Có | Có |
| Timeout/ambiguous errors | Có | Có | Có |
| Retry attempts | Có | Có | Có |
| Server CPU/IO/queue | Query/Index/Data | Data/replica/disk | Data/transaction metadata |
| Network request/response bytes | Có | Có | Có |
| Index lag/scan cost | Quan trọng | Đo ảnh hưởng downstream | Quan trọng nếu query sau commit |
| CAS/transaction conflicts | Nếu liên quan | CAS write | Đặc biệt quan trọng |
| Document correctness | Query freshness | Durable result | Atomic result |
| TTL/expiry behavior | Đọc đúng deadline | Ghi không reset TTL | Transaction không làm sai expiry |

**Goodput** là số business requests được xử lý hữu ích mỗi giây, khác số SDK operations, nhất là khi retry transaction.

### 35.1. Latency phải có ranh giới

Đo HTTP end-to-end và repository/SDK riêng. Query service metric không bao gồm toàn bộ thời gian Java deserialize/serialize hoặc network tới browser. Với durable write, elapsed từ client invocation đến acknowledgement bao gồm phần đợi durability; với transaction, tính từ transaction call đến kết quả commit/throw.

## 36. Kịch bản load test có khả năng tái lập

~~~text
Dataset:
  1 triệu orders, 100 nghìn inventory documents
  Payload sizes 2 KiB, 20 KiB, 100 KiB
  Hot/cold key distribution theo production

Workload:
  Read list by customer/status
  KV update order status
  Transaction confirm order + reserve stock

Load steps:
  100, 300, 600 requests/s
  Warm-up rồi steady-state measurement
  Same cluster, TLS, SDK, retries, timeouts

Record:
  p50/p95/p99 latency
  offered/completed/goodput
  unexpected errors/timeout/retries
  index visibility lag / wait indicators
  Data/Query/Index CPU, disk, network
  correctness and TTL metadata
~~~

Số lượng document và offered rates là **gợi ý xây dựng kịch bản**, không phải baseline đã đo. Tránh chạy load test phá vỡ dữ liệu/khả năng phục vụ production. Sử dụng môi trường test gần topology production và dữ liệu tổng hợp.

### 36.1. Phân bố dữ liệu quan trọng

Nếu 1% inventory keys nhận 70% writes, transaction conflicts có thể cao hơn nhiều so với dataset uniform. Tương tự, một batch tạo index lag có thể làm `REQUEST_PLUS` p99 tăng đột biến. Benchmark phải phản ánh những tình huống có thật, không chỉ requests phân đều trên mọi key.

## 37. Bảng kết quả minh họa — không phải dữ liệu đo thật

| Workload | p50 | p95 | p99 | Goodput/s | Unexpected errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| SQL++ `NOT_BOUNDED` | 18 ms | 55 ms | 120 ms | 300 | 0,1% |
| SQL++ `REQUEST_PLUS` | 23 ms | 95 ms | 230 ms | 291 | 0,3% |
| KV write `NONE` | 5 ms | 17 ms | 44 ms | 650 | 0,1% |
| KV write `MAJORITY` | 8 ms | 30 ms | 78 ms | 610 | 0,2% |
| Transaction 2 docs | 38 ms | 140 ms | 310 ms | 210 | 0,6% |

**Tất cả số liệu là giả lập để hướng dẫn đọc bảng**, không phải benchmark Couchbase. Không dùng nó làm lời hứa sản phẩm hoặc SLO.

Không so transaction 2 docs với KV write 1 doc rồi tuyên bố transaction “chậm hơn X lần” cho cùng công việc; workload, số document và correctness contract khác nhau.

### 37.1. Cách diễn giải đúng

- Query `REQUEST_PLUS` có thể có p99 cao hơn khi Index service đang bắt kịp writes. Cần đo lag và độ mới thực sự đạt được.
- Durability `MAJORITY` có thể tăng latency do đợi xác nhận replica. Cần đo reliability/failure requirements.
- Transaction có thể tăng round trips, metadata và retries. Chi phí này mua **atomicity** cho nhiều documents.
- Error rate phải được so cùng phân loại, timeout và tải; p99 chỉ trên thành công có thể che nhóm request lỗi chậm nhất.

## 38. Correctness test cho Query freshness

Kiểm thử theo trình tự không dựa vào `Thread.sleep` tùy tiện:

1. Tạo key test duy nhất và chèn document qua KV.
2. Xác nhận SDK write đã trả kết quả hoặc exception rõ.
3. Gọi KV GET theo key: xác minh document tồn tại.
4. Chạy query `REQUEST_PLUS` theo field/index đã online.
5. Assert query trả ID vừa ghi trong timeout budget hợp lệ.
6. Lặp lại với mutation-state consistency nếu API token hỗ trợ.
7. Test `NOT_BOUNDED` về **độ đúng theo contract eventual**, không assert nó buộc phải cũ.
8. Cleanup key test và kiểm tra index/collection đúng namespace.

Không tạo test kỳ vọng `NOT_BOUNDED` **luôn không thấy** write; thực tế index có thể bắt kịp rất nhanh.

### 38.1. Khi index build chưa hoàn tất

Một query fail do index chưa online là lỗi môi trường test, không phải chỉ dấu `REQUEST_PLUS` sai. Provision index và chờ online trước đo steady-state; ghi rõ tình trạng build nếu chính mục tiêu là test during index build.

## 39. Test durability và lỗi phải kiểm soát môi trường

Tối thiểu:

- Write với từng durability level được cluster hỗ trợ.
- Read-back nội dung, CAS và expiry metadata theo policy.
- Phân loại errors như impossible/unavailable, timeout và ambiguous.
- Test thiếu replica/cấu hình không thỏa trong môi trường riêng.
- Khi có thể, thực hiện fault injection node/failover trên test cluster theo quy trình vận hành.

**Đọc lại document ngay sau write không đủ chứng minh khả năng tồn tại qua lỗi node.** Muốn xác minh durability thực sự, phải kiểm thử failure scenario phù hợp, có thống kê và không làm gián đoạn production.

Không dùng `Thread.sleep(1000)` để suy bản ghi chắc chắn bền; thời gian chờ không thay cho durability acknowledgement.

## 40. Test transaction atomicity và retry

Một test giao dịch nhiều document:

~~~text
Arrange:
  order status = PAID
  stock available = 5

Transaction case A:
  Reserve 2 units
  Expect commit: order CONFIRMED, stock = 3

Transaction case B:
  Reserve 7 units
  Expect reject: order vẫn PAID, stock vẫn = 5

Concurrent case:
  Hai request cố reserve trên cùng stock
  Expect: không oversell, có conflict/retry thích hợp

Failure case:
  Một attempt lỗi có thể retry
  Expect: không phát email/payment side effect hai lần
~~~

Đừng chỉ assert exception từ transaction rồi không kiểm tra trạng thái hai documents. Không test “atomicity” bằng hai `collection.upsert` độc lập vì đó là chức năng khác.

### 40.1. Transaction result ambiguous

Khi client không chắc trạng thái commit, application cần phương pháp đối soát bằng business ID/idempotency record. Không tự báo checkout thành công hoặc thất bại chỉ vì client connection bị ngắt.

## 41. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Dùng SQL++ để GET một key đã biết | Query/index overhead không cần | KV GET |
| Bật `REQUEST_PLUS` cho mọi browse query | Latency/Index wait cao không cần | Chọn theo freshness SLA |
| Hạ consistency khi query timeout | Trả stale data ngoài contract | Sửa index/capacity, giữ semantics |
| Tin durability làm Query nhìn thấy write tức thì | Nhầm durability với index freshness | Query consistency riêng |
| Tin REQUEST_PLUS làm write chống mất dữ liệu | Nhầm freshness với durability | Chọn durability level |
| Đặt `PERSIST_TO_MAJORITY` khi topology không hỗ trợ | Durability errors/timeout | Kiểm tra replica/bucket |
| Retry increment mơ hồ vô điều kiện | Duplicated side effects | Idempotency + đối soát |
| Xóa CAS để giảm p99 | Lost update | CAS/`@Version` phù hợp |
| Hai KV writes được gọi “transaction” | Partial state | SDK transaction/saga |
| Side effect ngoài hệ thống trong transaction lambda | Bị lặp khi retry | Outbox/idempotency |
| Một hot inventory key cho mọi checkout | Transaction conflict | Data modeling |
| Dùng repository.save trong SDK transaction không đúng API | Không staged write | Dùng transaction context |
| So benchmark khác mức durability | Kết luận hiệu năng sai | Khóa correctness contract |
| Chỉ báo p99 success, ẩn timeout | Đánh giá sai | Báo lỗi và ambiguous outcomes |
| Đổ mọi Query latency cho REQUEST_PLUS | Có thể do index scan/Fetch | EXPLAIN và metrics |
| Thử failover trên production để đo | Rủi ro cao | Fault injection ở cluster riêng |
| Bỏ tenant filter để query nhanh | Rò dữ liệu | Giữ auth/index theo tenant |
| Bỏ qua TTL khi chuyển SDK options | Reset/renew expiry | Preserve/deadline validation |

## 42. Bài tập tình huống: checkout nhiều lớp dữ liệu

Ứng dụng có những API:

~~~text
POST /orders
GET /orders/{id}
GET /customers/{customerId}/orders
POST /orders/{id}/confirm
POST /orders/{id}/reserve-stock
GET /reports/daily-revenue
~~~

Cho biết:

- Order được lưu ở `commerce.sales.orders`.
- Inventory ở `commerce.sales.inventory`.
- Một số request cần read-your-writes theo `customerId`.
- Có 10% keys rất nóng trong giờ cao điểm.
- Query/Index service và Data service chạy trên topology đã đo.

**Nhiệm vụ:**

1. Với `GET /orders/{id}`, vì sao KV GET thường không cần `REQUEST_PLUS`?
2. Với danh sách order sau POST, khi nào dùng `REQUEST_PLUS`?
3. Nếu POST có `MutationResult`/mutation token, hãy đánh giá `consistentWith(MutationState)`.
4. Phân biệt một query đang chờ Index service với một query scan index kém.
5. Khi nào `NOT_BOUNDED` phù hợp với báo cáo?
6. Vì sao durability `MAJORITY` không khiến SQL++ mặc định thấy order ngay?
7. Lập bảng rủi ro mất dữ liệu cho các durability levels.
8. Vì sao không thể yêu cầu `PERSIST_TO_MAJORITY` khi cluster không thỏa điều kiện?
9. Nếu mutation timeout mơ hồ, vì sao không blind retry increment?
10. Vì sao xác nhận order và trừ stock ở hai documents có thể cần transaction?
11. Transaction lambda tự retry thì email/notification nên đặt ở đâu?
12. Nếu hot stock key làm transaction p99 tăng, chọn biện pháp thiết kế nào?
13. Vì sao CAS không thay transaction nhiều document?
14. Khi tăng durability, phải giữ TTL/`preserveExpiry` thế nào?
15. Hãy thiết kế ma trận Q/D/T giữ cùng workload, consistency và durability.
16. Những metric nào đo goodput thay vì chỉ SDK operation count?
17. Vì sao p99 thành công thấp hơn khi errors tăng chưa chứng minh cải thiện?
18. Sau khi commit transaction, query `NOT_BOUNDED` có thể chưa thấy mọi mutation không?
19. Kế hoạch test lỗi node cần ở môi trường nào?
20. Nếu ứng dụng dùng Spring Data repository, làm sao điều khiển API options khi abstraction không expose?

**Gợi ý:** tách rõ **freshness**, **failure durability** và **atomicity**; chọn KV cho key, Query consistency cho predicate, durability theo RPO/rủi ro và transaction khi có multi-document invariant. Sau đó mới tối ưu bằng index, data modeling, metrics và benchmark.

## 43. Checklist trước khi đưa lên production

- [ ] Use case đã định nghĩa rõ yêu cầu độ mới của query.
- [ ] Phân biệt KV theo ID với SQL++ dựa trên secondary index.
- [ ] Chỉ bật `REQUEST_PLUS` khi freshness contract cần thiết.
- [ ] Có đánh giá `MutationState` khi ứng dụng có mutation tokens.
- [ ] Không nhầm CAS token với mutation token.
- [ ] Query statement/index/selectivity được kiểm tra bằng `EXPLAIN`.
- [ ] Có monitoring Query/Index lag, backlog hoặc chỉ số tương đương theo version.
- [ ] Timeout vì freshness không được âm thầm fallback stale khi contract cấm.
- [ ] Durability level được chọn theo RPO, failure model và dữ liệu.
- [ ] Replica count, bucket type và server version hỗ trợ durability.
- [ ] Đã đo Data/replica/disk/network bottlenecks khi tăng durability.
- [ ] Có error handling cho unavailable/impossible/ambiguous writes.
- [ ] Không retry mutation non-idempotent vô điều kiện.
- [ ] CAS hoặc `@Version` được giữ khi business cần optimistic locking.
- [ ] TTL/`maxTTL`/`preserveExpiry` không bị thay sai khi đổi SDK options.
- [ ] Multi-document invariant dùng transaction/saga/outbox phù hợp.
- [ ] Không coi multi-spec mutateIn là transaction nhiều documents.
- [ ] Transaction code dùng context API, không trộn writes ngoài transaction.
- [ ] Transaction lambda không chứa external side effects không idempotent.
- [ ] Có giới hạn retry/timeout và monitoring transaction conflicts.
- [ ] Hot keys và skew được phản ánh trong load test.
- [ ] Scan consistency bên ngoài transaction được xử lý riêng khi cần.
- [ ] Spring Data repository/template và SDK config được xác minh theo version.
- [ ] Không gỡ tenant filters, validation hoặc authorization để giảm latency.
- [ ] Benchmark Q/D/T tách riêng trước khi thử tổ hợp.
- [ ] Dataset, node topology, TLS, indexes, load generator được giữ tương đương.
- [ ] p50/p95/p99 ở HTTP, Query/KV, Transaction đều được ghi.
- [ ] Goodput, offered/completed rates, retries, errors và ambiguous outcomes được tách.
- [ ] Đã đo logical/network bytes, Query/Index/Data CPU và disk latency.
- [ ] Query freshness test không dựa vào `Thread.sleep`.
- [ ] Durability failure test diễn ra trên test cluster, không production.
- [ ] Transaction test assert cả commit lẫn reject/rollback và concurrent race.
- [ ] Kết quả được lưu với run ID, version, options và correctness assertions.
- [ ] Kết luận không dựa vào một lần chạy local hoặc benchmark số giả định.

## 44. Tổng kết

`REQUEST_PLUS`, **durability** và **transaction** trong Spring Data Couchbase giải quyết ba khía cạnh khác nhau: **độ mới của kết quả SQL++ theo chỉ mục**, **mức bảo đảm tồn tại của mutation khi có sự cố** và **tính nguyên tử của nhóm thao tác nhiều document**. Chúng có thể phối hợp trong cùng một nghiệp vụ, nhưng không cơ chế nào là cách thay thế chung cho hai cơ chế còn lại.

Chi phí `REQUEST_PLUS` thường thể hiện ở việc đợi Index service bắt kịp và ở p95/p99 query; chi phí durability ở xác nhận replica/persistence cùng disk/network tail; chi phí transaction ở staging/commit/metadata, conflicts và retry. Mức chi phí thực tế phụ thuộc index, data model, consistency/durability levels, topology, tải và phân bố hot keys.

Cách tối ưu đúng là chốt **correctness contract**, chọn đường KV hay SQL++ hợp lý, thiết kế index và transactions theo business invariant, rồi **đo tách từng trục** bằng latency, goodput, errors, retries, network/disk và kết quả kiểm thử. Một số p99 thấp hơn không phải thành công nếu đánh đổi việc đọc dữ liệu mới, lưu bền hoặc commit nguyên tử mà hệ thống thực sự cần.

