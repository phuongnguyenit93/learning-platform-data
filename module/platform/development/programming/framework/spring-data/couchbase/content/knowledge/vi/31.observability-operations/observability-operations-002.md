# Phân biệt health check với độ sẵn sàng của từng dịch vụ Couchbase

## 1. Câu hỏi nền tảng: “Couchbase UP” nghĩa là gì?

Một ứng dụng Spring Boot trả `{"status":"UP"}` ở `/actuator/health`. Lệnh `orderRepository.findById("order::1001")` chạy bình thường, nhưng `orderRepository.findByCustomerId("c-1001")` lỗi vì Query Service hoặc secondary index chưa sẵn sàng. Ở một ứng dụng khác, SQL++ trả kết quả nhưng chức năng tìm kiếm toàn văn thất bại. Đây không nhất thiết là những kết quả mâu thuẫn.

**Health check** là một phép kiểm tra với **phạm vi cụ thể**. **Readiness** là quyết định một instance hoặc một dịch vụ **có thể tiếp nhận và phục vụ loại công việc nào tại thời điểm đó**. Một phép kiểm tra thành công không chứng minh các đường truy cập khác đều hoạt động.

Bài học thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**, nơi xây tầng truy cập bằng document mapping, Repository, `CouchbaseTemplate`, SQL++, chọn API reactive, bucket/scope/collection, chỉ mục, TTL, CAS, transaction và các biện pháp vận hành.

**Mục tiêu học tập:**

1. Phân biệt process liveness, application readiness, SDK connectivity, readiness của từng Couchbase service và functional readiness của use case.
2. Biết các phụ thuộc Data/KV, Query, Index, Search, Analytics, Eventing, replication/XDCR xuất hiện trong từng API.
3. Giải thích những điều `ping`, `diagnostics`, `waitUntilReady`, KV `exists`, `SELECT RAW 1` và query trên named index thực sự chứng minh.
4. Xây health indicators và health groups của Spring Boot phù hợp khả năng phục vụ, không làm liveness phụ thuộc database.
5. Quyết định cách xử lý partial failure, shared-dependency outage và Kubernetes routing.
6. Đo service availability, latency, index freshness và Eventing/Analytics backlog như các đại lượng riêng.
7. Viết kiểm thử/kịch bản vận hành có thể chẩn đoán sự cố mà không tạo tải không cần thiết.

> Quy tắc: Với mỗi đèn xanh `UP`, hãy trả lời: “UP **cho thao tác nào**, qua **dịch vụ và keyspace nào**, trong **ngân sách thời gian nào**?”

## 2. Một Couchbase cluster có nhiều chức năng

~~~mermaid
flowchart TD
    APP["Orders API / Spring Data Couchbase"] --> SDK["Couchbase Java SDK"]
    SDK --> KV[("Data Service: KV")]
    SDK --> Q[("Query Service: SQL++")]
    Q --> IDX[("Index Service: GSI")]
    SDK --> S[("Search Service: full-text")]
    SDK --> ANA[("Analytics Service nếu triển khai")]
    KV --> EVT[("Eventing Service nếu triển khai")]
    KV --> REPL["XDCR/cross-cluster replication"]
~~~

Sơ đồ biểu diễn **phụ thuộc nghiệp vụ ở mức khái niệm**; không khẳng định mọi mũi tên là một kết nối mạng trực tiếp hoặc mọi cluster đều có đủ dịch vụ.

- **Data/KV:** `get`, `insert`, `upsert`, `replace`, `remove` theo metadata document key.
- **Query:** thực thi SQL++, có thể chạy câu lệnh không liên quan đến collection.
- **Index:** duy trì và phục vụ GSI để query SQL++ theo field tìm document; từng index có lifecycle riêng.
- **Search (FTS):** full-text queries và Search indexes, khác GSI.
- **Analytics:** query phân tích/dataset và tiến độ ingest nếu ứng dụng dùng dịch vụ này.
- **Eventing:** thực thi function khi có mutation; có deployment state, errors và backlog.
- **XDCR/replication:** đồng bộ dữ liệu giữa clusters với độ trễ riêng; health ở source không chứng minh target đã bắt kịp.

Một Java SDK `Cluster` có thể tiếp cận được một số service endpoints trong khi những service khác không sẵn sàng. **Không mô hình hóa tất cả thành một biến `databaseReady` duy nhất.**

## 3. Phân biệt liveness, readiness, service health và functional health

| Tín hiệu | Câu hỏi trả lời | Ví dụ | Không chứng minh |
| --- | --- | --- | --- |
| **Process liveness** | JVM/HTTP process còn hoạt động đúng không? | `/actuator/health/liveness` | Couchbase đang phục vụ được |
| **Application readiness** | Pod có nên nhận traffic mới? | `/actuator/health/readiness` | Mọi feature đều hoạt động |
| **SDK connectivity** | Client có giao tiếp được với service endpoint? | `ping`, `diagnostics` | RBAC/keyspace/index cụ thể |
| **Service readiness** | KV/Query/Search/... có xử lý một lớp operation? | KV `exists`, SQL++ `SELECT RAW 1` | Tất cả business queries đều đúng |
| **Functional readiness** | Một capability trên keyspace/index thật có chạy đúng? | `findByCustomerId` với GSI hợp lệ | Các capability khác cũng hoạt động |
| **Data freshness** | Index/read model đã phản ánh mutation mới đến mốc nào? | Consistent-with mutation, lag metrics | Transaction/CAS correctness |

### 3.1. Độ sâu kiểm tra càng lớn, chi phí thường càng cao

Một `HealthIndicator` gọi một KV read-only nhẹ có thể thích hợp cho readiness. Một synthetic test tạo Order, chạy query `REQUEST_PLUS`, kiểm tra Search index, chờ Eventing rồi xóa fixture phải chạy riêng với tần suất thấp và cleanup.

### 3.2. Một health check luôn mang giới hạn thời gian

Health `UP` tại 09:00:00 không chứng minh request 09:00:01 sẽ thành công. Một Query Service có thể sẵn sàng nhận `SELECT RAW 1` nhưng không đáp ứng latency SLO cho query sort hàng triệu rows.

## 4. Case study: Order detail, Order list và các tính năng mở rộng

Giả sử ứng dụng dùng bucket `shop`, scope `sales`, collection `orders`:

~~~text
Keyspace:     shop.sales.orders
Document ID:  order::o-1001
~~~

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 245000
}
~~~

Một số endpoint:

| Endpoint/chức năng | Đường Couchbase cần | Khi đường đó lỗi |
| --- | --- | --- |
| `GET /orders/{id}` | Data KV đọc theo ID | Không đọc được document nếu không có fallback |
| `POST /orders` | Data KV write; CAS/idempotency tùy domain | Không được báo tạo thành công khi write chưa xác nhận |
| `GET /customers/{id}/orders` | Query + GSI Index, có thể fetch Data | Danh sách theo field lỗi/delay |
| `GET /products/search?q=...` | Search Service + Search index | Tìm toàn văn lỗi dù KV còn hoạt động |
| `GET /reports/sales` | SQL++/Analytics/read model | Báo cáo degrade theo SLO riêng |
| Xử lý Order event | Eventing function hoặc worker | Projection/notification có thể chậm |
| Đọc dữ liệu ở region khác | Cluster đích + replication | Dữ liệu vùng đích có thể trễ |

Nếu Query Service lỗi nhưng KV vẫn phục vụ Order detail, việc cho **mọi** pod Orders NotReady có thể chặn luôn chức năng vẫn còn hoạt động. Quyết định này phải do **hợp đồng của deployment và các route** quyết định.

## 5. Partial failure: “có dịch vụ tốt, có dịch vụ lỗi”

~~~text
Spring Boot process  : LIVENESS UP
Data/KV              : có thể get/insert
Query Engine         : unavailable hoặc timeout
Một named GSI        : offline/đang build
Các GSI khác         : online
Search               : chưa có Search index cần thiết
Analytics            : không được triển khai
Eventing             : function backlog tăng
XDCR                 : cluster đích đang lag
~~~

Tình huống trên có thể xảy ra ở một cluster hoặc qua nhiều hệ thống liên quan. Cần mô tả riêng:

1. **Service không được sử dụng/không triển khai** — không phải một outage của ứng dụng.
2. **Service có tồn tại nhưng unavailable** — dependency failure.
3. **Service available nhưng feature/query cụ thể lỗi** — sai index/keyspace/RBAC hoặc query plan.
4. **Service available nhưng chậm** — latency/capacity degradation.
5. **Service available nhưng data chưa mới** — backlog/freshness, không mặc định là connectivity failure.

### 5.1. Đặc biệt với Index Service

Index Service có thể chạy nhưng chỉ một index chưa online. Query khác dùng index khác vẫn thành công. Không suy từ “Index node UP” rằng `ix_orders_customer_created` đã dùng được.

### 5.2. Đặc biệt với Eventing

Eventing function có thể deployed nhưng đang chậm xử lý mutation hoặc thất bại khi gọi downstream. State triển khai chỉ chứng minh một phần khả năng phục vụ.

## 6. Mô hình readiness theo capability thay vì một cờ tổng

Khai báo các capability cụ thể:

~~~text
orders.kv.read          = Data + shop.sales.orders + RBAC read
orders.kv.write         = Data + RBAC write + write policy
orders.list.sqlpp       = Query + GSI + keyspace + Query RBAC
products.search         = Search + named Search index
reports.analytics       = Analytics dataset/link + Query
orders.event.projection = Eventing function + downstream sink
regional.read           = target cluster + replication freshness
~~~

Một capability có thể cần nhiều dịch vụ. Query theo field thường dùng Query + Index, đôi khi fetch Data; do đó check `SELECT RAW 1` chưa đủ để chứng minh nó hoạt động.

| Capability | Lightweight evidence | Deep functional evidence |
| --- | --- | --- |
| Orders KV read | KV `exists` đúng collection | KV get một fixture được quản lý |
| Orders KV write | Không có read-only check chứng minh toàn bộ write | Synthetic conditional insert, cleanup, idempotency |
| Orders list SQL++ | SQL++ read-only đúng keyspace/index | Derived Spring Data query + `EXPLAIN` + assertion |
| Products full-text | Search request/index path | Search fixture hit với SLO freshness |
| Reports analytics | Query nhẹ nếu Analytics có mặt | Dataset query + ingestion lag |
| Event projection | Function state/backlog | Mutation synthetic → quan sát side effect |
| Cross-region read | Target-cluster connectivity | Replication lag + target KV test |

Phải ghi **khả năng nào bắt buộc trước khi pod nhận traffic** và khả năng nào chỉ cần alert/degrade.

## 7. Ma trận bằng chứng: check thành công có nghĩa gì?

| Phép check | Kết luận hợp lệ | Không được kết luận |
| --- | --- | --- |
| Liveness HTTP 200 | Health handler/process phản hồi | Database khỏe |
| Khởi tạo `Cluster` bean | SDK object được tạo | Network/RBAC đã đúng |
| SDK ping KV thành công | Một số KV endpoints phản hồi | Quyền write/collection/index đầy đủ |
| KV `exists` trên Orders thành công | Collection phục vụ được KV operation | Query/Index/Search hoạt động |
| SQL++ `SELECT RAW 1` thành công | Query engine có thể thực thi query nhỏ | GSI theo customerId online |
| SQL++ theo `customerId` thành công | Query/index path đã thực thi | Mọi index và data freshness đạt SLO |
| Search query trả response | Search endpoint/index path phản hồi | Term bất kỳ phải có hit |
| Analytics query thành công | Analytics path của query đó hoạt động | Dataset ingestion luôn mới |
| Eventing function deployed | Deployment state đạt mức nhất định | Mọi event đã xử lý xong |
| Replication stream active | Cơ chế replication đang hoạt động ở mức báo cáo | Target đã có mọi mutation nguồn |

### 7.1. Một request không thành công vì permission khác vì outage

Nếu SDK KV read được nhưng Query trả permission denied, không nên ghi log duy nhất “database down”. Đây có thể là RBAC sai hoặc security policy chưa cập nhật. Tăng timeout không sửa được quyền thiếu.

## 8. SDK ping và diagnostics: công cụ quan sát endpoint

Couchbase Java SDK có API `ping` và `diagnostics` để xem trạng thái các endpoint/dịch vụ client biết theo version và options.

~~~java
import com.couchbase.client.java.Cluster;

public class CouchbaseClientStatus {
    private final Cluster cluster;

    public CouchbaseClientStatus(Cluster cluster) {
        this.cluster = cluster;
    }

    public void sample() {
        var pingReport = cluster.ping();
        var diagnosticSnapshot = cluster.diagnostics();

        // Chuyển các trạng thái theo từng endpoint/service
        // thành metrics/log có kiểm soát. Không chỉ lấy 1 boolean.
    }
}
~~~

**Ý nghĩa:**

- `ping` có thể thử liên lạc với các service types/endpoints được hỗ trợ theo cấu hình.
- `diagnostics` cung cấp snapshot trạng thái endpoints/client ở thời điểm gọi, không nhất thiết giống một live functional query.
- Phạm vi services được probe, cấu trúc report và cách chọn ServiceType cần kiểm tra đúng SDK version.
- Một endpoint ping thành công không chứng minh mọi node/service khác đều responsive.
- Ping/diagnostics không tự kiểm tra generated SQL++, index state hay dữ liệu customerId.

### 8.1. Không mở kết nối mới cho mỗi probe

Dùng `Cluster` do Spring quản lý. Tạo `Cluster.connect(...)` liên tục trong health endpoint gây DNS/TLS/bootstrap/connection churn và có thể khuếch đại sự cố.

### 8.2. Không phơi nguyên report ra Internet

Report có thể chứa host/port/topology. Ghi metric hoặc trạng thái khái quát; diagnostics chi tiết dùng kênh quản trị có phân quyền.

## 9. waitUntilReady: khi khởi động không thay runtime check

Ví dụ SDK 3.x có thể đợi bucket sẵn sàng:

~~~java
import java.time.Duration;

var bucket = cluster.bucket("shop");
bucket.waitUntilReady(Duration.ofSeconds(10));
~~~

`10s` chỉ minh họa timeout. Điều quan trọng:

- `waitUntilReady` chỉ đợi điều kiện của API trong thời điểm đó.
- Không chứng minh mọi collection/index/Search/Analytics/Eventing đã sẵn sàng.
- Không thay RBAC check cho thao tác nghiệp vụ.
- Không nên lặp lại mỗi HTTP request hoặc mỗi Kubernetes probe.
- Sau khi startup thành công, dependency vẫn có thể lỗi trong runtime.

Tùy yêu cầu, một startup failure do cấu hình bucket sai có thể cần fail-fast; một mất kết nối tạm thời có thể phù hợp trạng thái NotReady cho tới khi phục hồi. Hãy chọn chính sách rõ ràng.

## 10. Data Service: health theo KV operation đúng collection

Đọc-only `Collection.exists` trên key giả là một cách kiểm tra KV đến đúng collection.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;

public class OrdersKvProbe {
    private final Collection orders;

    public OrdersKvProbe(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public void check() {
        var result = orders.exists(
                "__orders_health_probe__",
                ExistsOptions.existsOptions()
                        .timeout(Duration.ofSeconds(1)));

        // result.exists() == false vẫn có thể là thành công:
        // phép thử chỉ cần operation hoàn tất không lỗi.
    }
}
~~~

**Phép thử này chứng minh:** một KV operation theo collection và account hiện tại đã được xử lý trong timeout. Nếu key không tồn tại, false là kết quả hợp lệ.

**Phép thử này không chứng minh:** quyền ghi, CAS/transaction, durability cao, Query Service, Index, Search hay replica/region khác.

### 10.1. Vì sao không insert rồi delete trong readiness?

Khi nhiều pods cùng chạy, synthetic mutation tại mỗi readiness poll:

- Tạo write load và chi phí index maintenance.
- Có thể kích hoạt Eventing và downstream side effects.
- Tạo dữ liệu rác khi write/delete timeout hoặc ambiguous.
- Làm outage nặng thêm khi hệ thống vốn đang quá tải.

Đưa write test sang smoke/integration check ở namespace cô lập, frequency thấp, có cleanup và quyền riêng.

## 11. Query Service: SELECT RAW 1 chứng minh điều gì?

Một SQL++ statement tối thiểu:

~~~sql
SELECT RAW 1;
~~~

Nó có thể được thực thi mà không cần truy vấn Orders collection/GSI.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.QueryOptions;

public class QueryEngineProbe {
    private final Cluster cluster;

    public QueryEngineProbe(Cluster cluster) {
        this.cluster = cluster;
    }

    public void check() {
        cluster.query(
                "SELECT RAW 1",
                QueryOptions.queryOptions()
                        .timeout(Duration.ofSeconds(1)));
    }
}
~~~

**Kết quả thành công cho thấy** Query Service có thể thực thi một query nhỏ, nhưng không kiểm tra:

1. Query permission trên `shop.sales.orders`.
2. Index theo `customerId` đã online.
3. Query planner có index phù hợp.
4. Query fetch body trên Data Service.
5. Index đã phản ánh mutation mới.
6. Business query có đáp ứng latency SLO không.

Một cluster có Data Service tốt nhưng Query Service gặp lỗi vẫn có thể phục vụ `findById`. Đó là lý do cần các capability health riêng biệt.

## 12. Index Service: trạng thái process và named GSI khác nhau

Index Service duy trì Global Secondary Index. Một index có thể offline/đang build trong khi index khác online. Không chỉ hỏi “Index Service UP?” mà nên hỏi:

- Named index `ix_orders_customer_created` đã được triển khai trên `shop.sales.orders` chưa?
- Trạng thái index có đủ để query sử dụng theo Server version không?
- SQL++ planner đang dùng index nào, có fallback khác không?
- Query scan/fetch có hoàn tất dưới timeout không?
- Index có backlog mutation hoặc bị thiếu data freshness không?

Index minh họa:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Đường truy vấn:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Với test query plan:

~~~sql
EXPLAIN
SELECT META(o).id AS documentId,
       o.customerId, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = "c-probe"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

**Không chạy CREATE INDEX hoặc rebuild index trong health handler.** Schema/index provisioning thuộc migration/deployment. Metadata về index state có thể lấy qua management/system keyspaces với quyền phù hợp, nên dùng trong smoke test/monitor có phân quyền chứ không yêu cầu mọi application service account thành cluster admin.

### 12.1. Online chưa chắc fresh

GSI có thể online nhưng chưa xử lý tới mutation gần nhất. `REQUEST_PLUS` trên SQL++ có thể yêu cầu đợi index tới mốc request; nó có thể tăng latency/timeout. Freshness SLO cần metric/test riêng, không suy từ trạng thái index online.

## 13. SQL++ theo field thường cần nhiều dịch vụ cùng phục vụ

~~~mermaid
flowchart LR
    APP["OrderRepository.findByCustomerId()"] --> Q[("Query Service")]
    Q --> IDX[("Index Service")]
    IDX --> Q
    Q --> DATA[("Data Service nếu fetch body")]
    DATA --> Q
    Q --> MAP["Spring Data converter / entity mapping"]
~~~

Query `SELECT RAW 1` chứng minh Query Engine trả lời, nhưng `findByCustomerId` còn phụ thuộc:

- GSI có thể tra cứu field.
- Quyền `SELECT` đúng keyspace.
- Data Service phục vụ body fetch khi query plan cần.
- Type discriminator, mapping và entity converter của Spring Data.
- `WHERE`, `ORDER BY`, `LIMIT` và tenant filter.
- Năng lực server đáp ứng deadline dưới tải.

Nếu mục tiêu là readiness cho **capability Order list**, cần kiểm tra đúng path đó. Nếu chỉ mục tiêu connectivity của Query Engine, câu SQL++ tối giản đủ gần phạm vi đó.

## 14. Diagnostic read-only cho index path nghiệp vụ

Cách kiểm tra sâu hơn có thể dùng SQL++ read-only đúng collection và field:

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrderIndexPathDiagnostic {
    private final Cluster cluster;

    public OrderIndexPathDiagnostic(Cluster cluster) {
        this.cluster = cluster;
    }

    public void check(String customerId) {
        String sql = """
            SELECT RAW META(o).id
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            LIMIT 1
            """;

        cluster.query(sql,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", customerId))
                        .scanConsistency(
                                QueryScanConsistency.NOT_BOUNDED)
                        .timeout(Duration.ofSeconds(2)));
    }
}
~~~

**Không có row vẫn có thể là một query thành công**, nếu customerId test không tồn tại. Đặt assertion phải có row chỉ khi có fixture sentinel và yêu cầu đó là một bài functional test riêng.

Lưu ý:

- Cần kiểm tra `EXPLAIN` xác nhận query thực tế dùng index mong muốn.
- `NOT_BOUNDED` không buộc index mới; nó phù hợp kiểm tra *khả năng chạy query* không phải read-after-write.
- `REQUEST_PLUS` có thể đợi index; không đặt mặc định trong mỗi readiness check.
- Timeout `2s` chỉ minh họa, cần điều chỉnh theo SLO và ngân sách probe.
- SDK raw SQL++ có thể khác generated SQL++ của Repository về type discriminator/projection.

Đưa diagnostic này vào synthetic monitor ít tần suất hoặc startup/smoke check, trừ khi business contract đòi bắt buộc kiểm tra path này ở readiness.

## 15. Search Service: full-text readiness độc lập GSI

Search (FTS) phục vụ những query như tìm sản phẩm bằng từ khóa. Một KV `get(productId)` và SQL++ `SELECT RAW 1` có thể UP trong khi Search index `products_text` chưa online hoặc chưa ingest document mới.

Phân loại:

| Phép thử | Điều chứng minh |
| --- | --- |
| Search endpoint/connectivity check | Có đường giao tiếp tới Search service được kiểm tra |
| Search query read-only trên named index | Index path có thể thực hiện query |
| Query tìm fixture term kỳ vọng | Dữ liệu fixture đã được Search index phản ánh |
| Đo mutation→Search visibility | Search freshness trong workload cụ thể |
| Search latency/error/backlog | SLO hiệu năng và vận hành |

**Đừng áp `QueryScanConsistency.REQUEST_PLUS` của SQL++ GSI sang Search rồi mặc định nó có cùng semantics**. Search có consistency options riêng tùy SDK/Server version; cần xác minh API đúng khi viết synthetic freshness test.

### 15.1. Không có search hit không tự nghĩa là service down

Nếu query chạy thành công nhưng term không khớp bất kỳ document nào, kết quả rỗng là bình thường. Muốn kiểm tra dữ liệu sentinel phải có fixture được quản lý và kỳ vọng rõ.

### 15.2. Search không có mặt cũng có thể bình thường

Một Orders deployment không dùng full-text Search không nên coi việc cluster không triển khai Search là readiness failure.

## 16. Analytics Service: engine UP có thể ingestion lag

Analytics (nếu được triển khai và được ứng dụng sử dụng) thường phục vụ phân tích/đọc dữ liệu ở mô hình riêng. Phân biệt:

1. Analytics Service nhận và thực thi query không?
2. Dataset/link đã được cấu hình và có quyền thích hợp không?
3. Ingestion từ nguồn đã đến mốc kỳ vọng chưa?
4. Query aggregate có hoàn tất trong SLO latency không?

Một query đơn giản có thể thành công dù dataset còn thiếu mutation mới. Khi đó **availability** tốt nhưng **freshness** không đạt SLO.

| Tình huống | Kết luận đúng |
| --- | --- |
| Cluster không triển khai Analytics, ứng dụng không dùng | Không phải dependency failure |
| Analytics endpoint unavailable nhưng KV/Query đang dùng được | Analytics capability DOWN, các capability khác đánh giá riêng |
| Analytics query trả số liệu cũ | Kiểm tra ingestion lag/caching/logic, không mặc định engine DOWN |
| Report query timeout vì scan lớn | Kiểm tra workload/plan/capacity, không chỉ connection |

Không chạy báo cáo lớn liên tục trong Kubernetes readiness. Tách Analytics synthetic monitor và dashboard ingestion metrics.

## 17. Eventing Service: triển khai function chưa chứng minh đã xử lý event

Một luồng Eventing điển hình:

~~~text
KV mutation Order đã ACK
  -> Eventing nhận mutation theo pipeline
  -> Function xử lý/biến đổi
  -> Downstream projection/notification/read model được cập nhật
~~~

Cần quan sát độc lập:

- Function state: deployed, paused, stopped hoặc trạng thái tương ứng version.
- Event processing backlog/lag.
- Handler error/retry và khả năng gọi downstream.
- Tốc độ xử lý thành công, latency đến hiệu ứng đích.
- Khả năng phục hồi sau downtime.
- Idempotency nếu event bị retry/phát lại.

**Một health check KV UP không chứng minh Eventing đã xử lý mutation**, và một function deployed không đồng nghĩa projection đã cập nhật.

Synthetic Eventing test có thể tạo side effect (email, payment, event downstream). Không chạy loại test này trong liveness/readiness; nếu cần, dùng namespace test, guard logic, cleanup và tần suất thấp.

Các sự cố Eventing cần được báo cáo theo pipeline/function, không mặc định chặn mọi route KV đang hoạt động.

## 18. XDCR và nhiều cluster: khỏe ở nguồn không bảo đảm khỏe ở đích

Một writer ghi Order vào cluster A, còn reader ở vùng khác đọc từ cluster B qua XDCR/replication:

~~~mermaid
flowchart LR
    W["Writer region A"] --> A[("Cluster A")]
    A --> R["XDCR / replication"]
    R --> B[("Cluster B")]
    C["Reader region B"] --> B
~~~

Mutation được ACK tại A không có nghĩa B đã nhận bản ghi ngay. Cần theo dõi độc lập:

- Connectivity và trạng thái phục vụ KV tại cluster A.
- Availability và quyền đọc trên cluster B.
- Trạng thái replication stream, backlog, lag và conflict handling.
- Query/Index readiness **ở B** nếu reader dùng SQL++.
- SLO đọc sau ghi xuyên vùng; đây thường không phải hợp đồng giống active KV read.

`QueryScanConsistency.REQUEST_PLUS` của SQL++ tại A không tự đồng bộ dữ liệu sang B. Với topology không dùng XDCR, **không nên đặt replication health làm dependency bắt buộc** của ứng dụng.

## 19. Spring Boot Actuator: health tổng và health group có mục đích khác nhau

Spring Boot Actuator có thể cung cấp:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
GET /actuator/health/{custom-group}
~~~

Ví dụ cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

- **Global health:** tổng hợp các contributors đã đăng ký theo chính sách.
- **Liveness:** trạng thái process/application; thường không bao gồm Couchbase.
- **Readiness:** quyết định pod có nên nhận traffic mới theo hợp đồng phục vụ.
- **Custom groups:** nhóm metrics/health của KV, Query hoặc capability riêng để chẩn đoán.

### 19.1. Couchbase contributor được auto-configured cũng có phạm vi

Một số phiên bản Spring Boot có Couchbase health contributor khi điều kiện classpath/bean thỏa mãn. Trước khi include tên `couchbase` vào health group, hãy xác minh contributor thực sự tồn tại và đang thực hiện loại kiểm tra nào, timeout gì, có đi qua collection/SQL++ hay không.

**Không mặc định `couchbase: UP` có nghĩa toàn bộ KV, Query, GSI, Search, Analytics, Eventing đã sẵn sàng.**

### 19.2. Không lộ diagnostics qua HTTP health

Health response công khai nên chỉ đưa trạng thái cần thiết. Exception, hostnames, thông tin TLS/credential hoặc chi tiết topology phải nằm trong hệ thống logs/metrics có phân quyền.

## 20. Viết HealthIndicator KV đúng collection

Một check đọc-only trên `shop.sales.orders` có thể dùng `exists` theo key không cần tồn tại.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersKv")
public class OrdersKvHealthIndicator implements HealthIndicator {
    private final Collection orders;

    public OrdersKvHealthIndicator(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    @Override
    public Health health() {
        try {
            orders.exists(
                    "__orders_readiness_probe__",
                    ExistsOptions.existsOptions()
                            .timeout(Duration.ofSeconds(1)));

            return Health.up()
                    .withDetail("capability", "orders.kv.read")
                    .build();
        } catch (RuntimeException failure) {
            // Log an toàn: phân loại lỗi, không xuất credential.
            return Health.down()
                    .withDetail("capability", "orders.kv.read")
                    .build();
        }
    }
}
~~~

**`exists(false)` vẫn là UP** nếu SDK hoàn tất operation; key sentinel không cần tồn tại. Contributor tên `ordersKv` phục vụ cấu hình group.

Giới hạn:

- Không chứng minh quyền ghi, CAS, transaction, durability hoặc TTL workflow.
- Không kiểm tra Query/Index/Search/Analytics.
- Không tự bảo đảm request kế tiếp luôn thành công.
- Timeout `1s` chỉ là ví dụ, phải chọn theo budget thực.

Tránh retry vô hạn trong `health()` hoặc mở `Cluster.connect` mới cho mỗi probe.

## 21. Query Service HealthIndicator riêng biệt

Một contributor khác có thể chạy `SELECT RAW 1` để kiểm tra SQL++ engine mà **không cần GSI**.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.QueryOptions;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("queryEngine")
public class QueryEngineHealthIndicator implements HealthIndicator {
    private final Cluster cluster;

    public QueryEngineHealthIndicator(Cluster cluster) {
        this.cluster = cluster;
    }

    @Override
    public Health health() {
        try {
            cluster.query("SELECT RAW 1",
                    QueryOptions.queryOptions()
                            .timeout(Duration.ofSeconds(1)));

            return Health.up()
                    .withDetail("capability", "query.engine")
                    .build();
        } catch (RuntimeException failure) {
            return Health.down()
                    .withDetail("capability", "query.engine")
                    .build();
        }
    }
}
~~~

Bây giờ có thể có trạng thái:

~~~text
ordersKv      UP
queryEngine   DOWN
liveness      UP
~~~

Không có mâu thuẫn khi Query Service lỗi nhưng Data/KV còn hoạt động.

**Query engine UP vẫn không chứng minh named GSI Orders online**; đường SQL++ nghiệp vụ ở mục 14 là một capability khác. Đừng ép query sâu này chạy trong mỗi liveness probe.

## 22. Cấu hình health groups theo contract

Ví dụ giả sử Orders API coi KV là dependency thiết yếu, còn Query Service được giám sát riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ordersKv
        query-path:
          include: queryEngine
~~~

Các endpoint:

~~~text
/actuator/health/liveness
/actuator/health/readiness
/actuator/health/query-path
~~~

- `liveness`: process vẫn đáp ứng.
- `readiness`: availability state cộng với read-only KV check theo contract ví dụ.
- `query-path`: theo dõi Query Engine, không tự quyết định pod readiness.

Nếu mọi route trong deployment bắt buộc SQL++, có thể cân nhắc include `queryEngine` vào readiness. Nhưng nếu shared Query cluster lỗi, **tất cả pods có thể NotReady**, kể cả route KV còn phục vụ được; cần đánh giá chính sách này.

### 22.1. Health group ID phải khớp contributor thật

Nếu không có bean `ordersKv` hay `queryEngine`, Spring Boot có thể báo cấu hình include không hợp lệ tùy version. Đừng tắt validation để che sai chính tả; kiểm tra context và endpoints trong môi trường test.

### 22.2. Một boolean readiness có thể quá thô

Nếu Orders KV API và Search API có yêu cầu routing khác nhau, cân nhắc tách deployment/service hoặc ứng dụng có cơ chế degrade và metrics capability riêng.

## 23. Kubernetes: probe cho routing, synthetic monitor cho chức năng sâu

Một ví dụ Deployment với Actuator ở cùng main HTTP port 8080:

~~~yaml
containers:
  - name: orders-api
    image: registry.example.invalid/orders-api:TAG
    ports:
      - containerPort: 8080

    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 2
      timeoutSeconds: 2
      failureThreshold: 30

    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
~~~

Các giá trị là ví dụ, không phải chuẩn latency chung.

- `startupProbe` cho app thời gian hoàn tất khởi động.
- `livenessProbe` có thể dẫn tới restart khi process thật sự hỏng.
- `readinessProbe` loại/đưa pod vào Service endpoints.

### 23.1. Không đưa Couchbase vào liveness

Couchbase outage tạm thời không được mặc định coi như JVM hỏng. Restart đồng loạt có thể gây DNS/TLS/bootstrap/reconnect storm mà không phục hồi database.

### 23.2. Management port có thể không phản ánh main application port

Nếu Actuator chạy port riêng, management port có thể UP trong khi business port lỗi. Khi có thể, đặt health check trên main serving port hoặc dùng additional health path được hỗ trợ bởi Spring Boot version.

### 23.3. Readiness không thay runtime error handling

Giữa hai probe vẫn có thể xảy ra outage. Controller/service cần xử lý timeout, backoff/circuit breaker, idempotency và HTTP errors đúng nghĩa.

## 24. Hạ readiness hay chỉ cảnh báo?

| Tình huống | Lựa chọn có thể hợp lý | Tiêu chí |
| --- | --- | --- |
| JVM hỏng, không phục vụ HTTP | Liveness DOWN | Restart giúp phục hồi |
| App chưa hoàn tất initialization | Readiness DOWN | Chưa nhận traffic |
| KV credentials sai, toàn bộ API cần KV | Readiness DOWN + alert | Lỗi cấu hình |
| Shared Data Service outage | Readiness theo contract + alert | Có fallback/route không cần DB? |
| Query lỗi nhưng KV detail còn dùng | Query capability DOWN | Không nhất thiết hạ mọi pod |
| Một named GSI chưa online | Orders list DOWN, Query engine có thể UP | Có route khác còn hoạt động? |
| Search index lỗi | Search-specific alert/degradation | Search criticality |
| Analytics ingestion lag | Freshness alert | Query engine có thể UP |
| Eventing backlog | Processing-lag alert | Projection/notification criticality |
| XDCR lag ở B | Replication/target alert | Nguồn A còn khỏe |

**Không che lỗi thật bằng cách luôn báo UP.** Nếu chọn không đưa dependency vào readiness, vẫn cần error handling và alert cho chức năng thất bại.

### 24.1. Cân nhắc cascade khi mọi pod NotReady

Một dependency chung outage có thể khiến tất cả pod mất readiness cùng lúc. Đó là hành vi phải **được quyết định có chủ đích**, không phải tác dụng phụ của việc include mọi health contributor.

## 25. Security và RBAC cũng ảnh hưởng kết quả check

Một account có thể:

~~~text
SDK ping KV endpoint        SUCCESS
KV exists trên orders       SUCCESS
SQL++ SELECT trên orders    PERMISSION DENIED
Search query trên index     PERMISSION DENIED
~~~

Đây không phải bằng chứng Couchbase Data Service DOWN. Cần xác định:

- Quyền theo bucket/scope/collection và operation.
- Identity/secret của Spring Data Repository, Template và SDK.
- Query/index/Search RBAC theo phiên bản.
- Sự thay đổi của secret, TLS certificate hoặc network policy.

Không sửa bằng cách cấp full admin cho application. Synthetic monitor dùng quyền sâu nên tách identity và giới hạn.

Từng contributor trả lời một câu hỏi hẹp; chỉ gom chúng theo routing contract sau khi đo tác động.

## 26. Availability, latency, freshness và correctness là những hợp đồng khác nhau

Một dịch vụ có thể **available** nhưng vẫn **chậm**, **dữ liệu chưa mới** hoặc **sai bất biến nghiệp vụ**.

| Thuộc tính | Câu hỏi | Bằng chứng thích hợp |
| --- | --- | --- |
| **Availability** | Operation có được thực hiện thành công? | Scoped health check, success/error rate |
| **Latency** | Response trong bao lâu, p95/p99 có đạt SLO? | SDK/HTTP durations |
| **Capacity** | Khi concurrency/tốc độ ghi tăng, có backlog/timeout? | Load tests, CPU, memory, queue |
| **Freshness** | GSI/Search/Analytics/replica theo kịp mutation đến đâu? | Lag metrics, mutation-aware tests |
| **Correctness** | CAS, transaction, auth, idempotency có bảo vệ bất biến? | Integration/concurrency tests |

Ví dụ:

~~~text
query.engine         UP
orders.list.sqlpp    UP nhưng p99 = 2200ms, vượt SLO
orders.namedIndex    online nhưng backlog còn tăng
products.search     UP nhưng index còn thiếu sản phẩm mới
eventing.projection running nhưng xử lý sự kiện chậm
~~~

Bảng này không có nghĩa phải tự thêm các trạng thái đó thành một enum duy nhất. Nó cho thấy **mỗi kết luận cần metric riêng**.

### 26.1. Query readiness không phải consistency guarantee

SQL++ query `SELECT RAW 1` không sử dụng GSI. Một query trên GSI với `NOT_BOUNDED` có thể chưa thấy mutation mới. `REQUEST_PLUS` hoặc `consistentWith(MutationState)` dùng cho yêu cầu index freshness; lựa chọn ấy có thể tăng latency và không làm Query Service khỏe hơn.

### 26.2. Cache có thể che hoàn toàn database operation

Một `@Cacheable` hit có thể trả response dù không hề truy cập KV/Query. Khi đo service readiness hoặc query freshness, phải đi trực tiếp vào SDK/DAO không qua result cache. Ngược lại, cache có thể là fallback có chủ đích trong hợp đồng degraded mode.

## 27. Metrics và tracing theo tên dịch vụ/capability

| Nguồn | Chỉ số và sự kiện cần theo dõi |
| --- | --- |
| Spring Boot | Liveness/readiness transitions, HTTP 5xx, pod restarts |
| Couchbase SDK | KV/Query/Search timeout, retry, connection endpoint status |
| Data/KV | Read/write latency, mutation rate, ambiguous errors, CAS conflicts |
| Query | Request count, p50/p95/p99, timeout, scan/fetch/sort cost |
| Index | Index online state, mutation backlog/lag, update/scan utilization |
| Search | Query latency/errors, Search index state, indexing lag |
| Analytics | Query errors, dataset/link status, ingestion progress |
| Eventing | Function state, backlog, handler failure/retry, event processing latency |
| XDCR | Replication stream state, backlog/lag, target visibility |
| Synthetic monitors | Capability pass/fail, last success, duration, fixture errors |

Tên metric cụ thể thay đổi theo Couchbase Server, SDK, Micrometer hoặc monitoring stack. Không tự đặt ra một metric name rồi tuyên bố nó luôn tồn tại trong mọi triển khai.

### 27.1. Trace minh họa có giá trị chẩn đoán

~~~text
requestId=req-921
route=GET /customers/{id}/orders
capability=orders.list.sqlpp
keyspace=shop.sales.orders
kv.health=UP
query.engine.health=UP
index.path.health=DEGRADED
db.query.elapsed_ms=2510
db.error.category=timeout
http.status=503
~~~

Đây là format tự thiết kế để minh họa, không phải output mặc định SDK. Không ghi password, bearer token, payment details hoặc toàn bộ JSON khách hàng.

### 27.2. Log state transitions thay vì mọi lần probe

Nếu hàng trăm pod in toàn bộ SDK ping report mỗi 5 giây, log sẽ rất lớn và lộ thông tin topology. Ưu tiên metrics/histograms, log sự kiện chuyển trạng thái UP/DOWN, nhóm lỗi và một số sample chẩn đoán có giới hạn.

## 28. Reactive health: chỉ UP sau khi I/O thật hoàn thành

Một ứng dụng WebFlux có thể dùng `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate`. Trong reactive health indicator, **tạo Publisher không đồng nghĩa đã kiểm tra được dependency**.

~~~java
// Pseudocode: reactiveKvReadOnlyCheck() là I/O Publisher
// được inject theo API SDK/Spring Data version.
Mono<Health> health() {
    return reactiveKvReadOnlyCheck()
            .thenReturn(Health.up().build())
            .onErrorResume(error ->
                    Mono.just(Health.down().build()));
}
~~~

Các phản ví dụ:

~~~java
// Sai: blocking call chạy trước khi Mono được tạo.
Mono.just(blockingCollection.get(id));

// Sai: làm nghẽn event loop.
reactiveCollection.get(id).block();

// Sai: fire-and-forget rồi trả UP ngay.
reactiveCollection.get(id).subscribe();
return Mono.just(Health.up().build());
~~~

`ReactiveHealthIndicator` có thể giúp health pipeline non-blocking khi ứng dụng và SDK đều reactive. Nếu dùng một `HealthIndicator` đồng bộ trong WebFlux, cần kiểm tra threading/offload và timeout thay vì mặc định gọi blocking trong event loop.

Reactive giúp điều phối I/O, **không làm Data/Query/Index Service tự hồi phục** và không triệt tiêu thời gian chờ index khi query yêu cầu consistency cao.

## 29. Timeout budget và readiness flapping

Một readiness timeout 2 giây nhưng custom Query probe mất tối đa 5 giây có thể khiến kubelet đánh dấu probe thất bại trước khi Java SDK trả kết quả.

Ví dụ ngân sách, **không phải số cố định nên áp mọi nơi**:

~~~text
Kubernetes readiness timeout: 2s
  + HTTP/Actuator overhead
  + một KV exists với timeout 1s
  + margin cho scheduler/network
~~~

Các nguyên tắc:

1. Đặt SDK operation timeout tương thích deadline probe.
2. Readiness nhẹ, không retry vô hạn.
3. Chọn `periodSeconds`, `timeoutSeconds`, `failureThreshold` dựa trên startup/runtime và spike chấp nhận được.
4. Query/Index deep check quá lâu phải chuyển sang synthetic monitor.
5. Theo dõi readiness transitions, không chỉ trạng thái hiện tại.
6. Giới hạn tần suất/concurrency để probes không khuếch đại outage.
7. Khi dependency đang chậm, request-level circuit breaker, rate limit và backpressure vẫn cần thiết.

### 29.1. Shared dependency outage là tình huống đặc biệt

Nếu mọi pod cùng bị tác động bởi một Query cluster lỗi, readiness include Query có thể làm toàn bộ Kubernetes Service mất endpoints. Điều đó **có thể phù hợp** cho một dịch vụ chỉ phục vụ SQL++, nhưng không nên vô ý chặn KV routes còn dùng được.

### 29.2. Không tăng timeout để che cấu hình sai

Authentication denied, missing collection hoặc thiếu index không trở thành đúng nếu chờ 30 giây thay vì 2 giây. Phân loại lỗi trước khi điều chỉnh timeouts và retry.

## 30. Kiểm thử tách policy health với trạng thái Couchbase thực

Một bộ test đáng tin nên có hai tầng.

### 30.1. Contract/unit test có thể dùng fake operations

~~~text
Scenario A: KV succeeds, Query fails
  ordersKv = UP
  queryEngine = DOWN
  liveness = UP
  readiness = tùy group policy

Scenario B: KV fails, Query succeeds
  ordersKv = DOWN
  queryEngine = UP
  readiness include ordersKv = DOWN

Scenario C: KV exists returns false
  ordersKv = UP (operation thành công)

Scenario D: SELECT RAW 1 succeeds nhưng named GSI missing
  queryEngine = UP
  orders.list.sqlpp = DOWN / DEGRADED
~~~

Unit tests chỉ chứng minh health policy, không kiểm chứng SDK/Server connection thật.

### 30.2. Spring Boot integration test health endpoints

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CapabilityHealthIT {

    @Autowired
    private TestRestTemplate http;

    @Test
    void kvReadinessIsUpInPreparedTestCluster() {
        ResponseEntity<String> result = http.getForEntity(
                "/actuator/health/readiness", String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
    }

    @Test
    void queryGroupCanBeCheckedIndependently() {
        ResponseEntity<String> result = http.getForEntity(
                "/actuator/health/query-path", String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
    }
}
~~~

Điều kiện: Actuator/probes bật, contributor đúng ID, test Cluster bean đã cấu hình, collection Orders và Query Service sẵn sàng. Test này không đo GSI freshness và cũng không chứng minh Search/Analytics/Eventing.

### 30.3. Test partial outage trong cluster lab

| Kịch bản | KV | Query Engine | Order Index Path | Điều cần quan sát |
| --- | --- | --- | --- | --- |
| Baseline | UP | UP | UP | Health groups theo thiết kế |
| Query service unavailable | Có thể UP | DOWN | DOWN | Liveness không bị kéo DOWN |
| Named index offline | UP | UP | DOWN | Query engine khác index readiness |
| KV permission sai | DOWN | Có thể UP | Tùy | Phân biệt RBAC với outage |
| Search index mất | UP | UP | Không liên quan | Search capability DOWN riêng |
| Analytics ingestion lag | UP | Có thể UP | Không liên quan | Freshness alert |
| Eventing backlog | UP | Có thể UP | Không liên quan | Processing lag metrics |
| XDCR target lag | Source UP | Có thể UP | Không liên quan | Target freshness SLO |

Không fault inject trên production; node/network disruptions cần cluster cô lập, quyền vận hành và runbook rollback.

## 31. Runbook: health xanh nhưng nghiệp vụ thất bại

~~~mermaid
flowchart TD
    A["Business request lỗi"] --> B{"Capability dùng dịch vụ nào?"}
    B --> K["KV / Data"]
    B --> Q["SQL++ Query + Index"]
    B --> S["Search / Analytics / Eventing / XDCR"]
    K --> C["Read-only KV đúng collection và RBAC"]
    Q --> D["SELECT RAW 1; query thật; EXPLAIN"]
    S --> E["Index/function/dataset/replication status, lag"]
    C --> F{"Có lỗi network/auth/timeout?"}
    D --> F
    E --> F
    F -->|Có| G["Phân loại nguyên nhân, khôi phục, đo lại"]
    F -->|Không| H["Mapping, cache, data freshness, CAS/transaction"]
~~~

Trình tự đề xuất:

1. Xác định route và kiểu operation KV, Query, Index, Search, Analytics, Eventing hay replication.
2. Xem trạng thái process liveness và application readiness **theo group thực**.
3. Kiểm tra SDK endpoint diagnostics, network DNS/TLS, credential và RBAC.
4. Với KV: chạy một read-only operation trên đúng bucket/scope/collection.
5. Với Query: tách `SELECT RAW 1` (engine) với query theo field (GSI).
6. Với Index: xem named index online, `EXPLAIN`, backlog và consistency mode.
7. Với Search: xem Search index, query path và freshness/lag.
8. Với Analytics: tách query engine khỏi ingestion/dataset freshness.
9. Với Eventing: theo dõi function state, backlog, handler errors.
10. Với XDCR: so sánh source, target và replication lag.
11. Phân biệt lỗi cache/mapping với dữ liệu nguồn/index chưa mới.
12. Sau sửa, đo request error rate, p95/p99, readiness transitions và user impact.

**Không dùng restart mọi pod hoặc tăng mọi timeout làm phương án mặc định.** Các hành động đó không sửa named index chưa được tạo hoặc RBAC sai.

## 32. Health không bảo đảm CAS, durability, TTL và transaction

Ngay cả khi `ordersKv` UP, các câu hỏi sau vẫn cần kiểm chứng độc lập:

- **CAS/optimistic locking:** `@Version` có ngăn lost update trên Order không?
- **Durability:** mutation có đáp ứng mức bền/nhân bản mà nghiệp vụ chọn?
- **TTL/expiry:** session hết hạn đúng metadata, không chỉ có JSON field `expiresAt`?
- **Transaction:** tạo Order và trừ Inventory có commit/rollback cùng nhau khi cần?
- **Idempotency:** write timeout rồi retry có tạo Order/trừ tiền hai lần?
- **Scan consistency:** GSI đã thấy mutation theo `REQUEST_PLUS` hoặc `MutationState`?
- **Cache invalidation:** Redis/Caffeine/CDN có bị stale dù Couchbase mới?
- **Authorization:** tenant/user có được phép đọc row hay không?

Health routing không thay điều kiện ghi hoặc quyền truy cập. Một trạng thái `UP` chỉ có ý nghĩa trong **phạm vi check thực thi**.

## 33. Các lỗi thiết kế cần tránh

1. Gộp toàn bộ Couchbase thành một `databaseReady` và che partial failures.
2. Coi SDK ping UP là mọi service/keyspace/index đều hoạt động.
3. Coi `SELECT RAW 1` là test Global Secondary Index.
4. Không kiểm tra named index và `EXPLAIN` khi SQL++ business query lỗi.
5. Coi GSI online nghĩa index đã đủ mới tới mutation cuối.
6. Đưa full-text Search failure vào liveness của Orders KV API.
7. Coi không có Analytics nodes là outage khi ứng dụng không dùng Analytics.
8. Coi Eventing function deployed là đã xử lý hết events.
9. Coi source cluster ACK là target XDCR cũng có document.
10. Dùng KV `exists(false)` như bằng chứng Data Service DOWN.
11. Thêm mọi contributor vào readiness mà không xem route dependencies.
12. Gắn database connectivity vào liveness và gây restart storm.
13. Chạy insert/delete synthetic fixture ở mỗi readiness probe.
14. Chạy REQUEST_PLUS query nặng liên tục trong readiness.
15. Mở SDK Cluster connection mới cho mỗi health check.
16. Tăng timeout thay vì sửa RBAC, tên collection hoặc index thiếu.
17. Dùng error timeout thành danh sách rỗng rồi báo API vẫn UP.
18. Không theo dõi tail latency, error rate, index backlog và data freshness.
19. Công khai full diagnostics, certificate hoặc credential trong health response.
20. Dùng `Mono.just(blockingCall())` mà tưởng health đã non-blocking.
21. Chỉ probe management port trong khi main application port không phục vụ.
22. Không test partial outage và recovery trên môi trường lab.
23. Coi cache hit là bằng chứng một SQL++ query mới đã chạy.
24. Dùng liveness/readiness như cơ chế bảo vệ transaction/CAS/idempotency.

## 34. Bài tập thực hành

### Bài A — KV vẫn tốt, SQL++ lỗi

`findById` thành công nhưng `findByCustomerId` timeout.

**Hướng giải:** Data/KV có thể còn hoạt động. Kiểm tra Query Service, Index Service, index path, `EXPLAIN` và Query timeout. Không tự kết luận Data Service DOWN.

### Bài B — Query engine UP, named index mất

`SELECT RAW 1` chạy được, query theo customerId báo thiếu index.

**Hướng giải:** `queryEngine = UP`, nhưng `orders.list.sqlpp = DOWN`; sửa index provisioning/query plan, không tăng timeout.

### Bài C — Search không trả hit

Search request trên `products_text` hoàn tất nhưng từ khóa ngẫu nhiên không match.

**Hướng giải:** Empty hit không đồng nghĩa service down. Dùng fixture term nếu cần test data visibility.

### Bài D — Eventing backlog

Một mutation Order đã ACK nhưng projection cho dashboard chưa cập nhật.

**Hướng giải:** Theo dõi Eventing function processing lag và downstream; không tự kéo liveness của Orders API DOWN.

### Bài E — Không triển khai Analytics

Cluster/app không dùng Analytics nhưng readiness cố kiểm tra Analytics mỗi lần.

**Hướng giải:** Loại dependency không sử dụng khỏi readiness, giữ capability checks theo app thực.

### Bài F — KV có quyền, Query bị permission denied

Một account chạy được KV exists nhưng SQL++ SELECT bị từ chối.

**Hướng giải:** Phân biệt RBAC theo operation và keyspace; không giải bằng retry hoặc cấp admin bừa bãi.

### Bài G — Quá nhiều readiness query

Một deployment lớn chạy SQL++ REQUEST_PLUS sort hàng nghìn Order mỗi hai giây.

**Hướng giải:** Probe đắt, có thể gây index wait/timeout/flapping. Dùng lightweight check và tách synthetic Query/Index checks.

### Bài H — Replication target stale

Writer ở cluster A nhận ACK, reader ở B chưa thấy Order.

**Hướng giải:** XDCR và target freshness riêng; Query scan consistency ở A không đồng bộ B.

### Bài I — Liveness lúc shared outage

Couchbase unavailable nhưng JVM vẫn khỏe và có thể recover connection.

**Hướng giải:** Liveness thường vẫn UP. Readiness/degradation tùy traffic contract, đi kèm alert và error handling.

### Bài J — Reactive HealthIndicator

Lập trình viên dùng `Mono.just(blockingSdkPing())` rồi báo UP.

**Hướng giải:** Blocking đã chạy trước khi tạo Mono. Dùng SDK reactive hoặc offload blocking, chờ tín hiệu success/error thật.

## 35. Checklist review trước production

- [ ] Đã tách process liveness, app readiness, SDK connectivity và per-service capability?
- [ ] Đã xác định dịch vụ Couchbase nào thực sự được deploy và ứng dụng sử dụng?
- [ ] Mỗi route có dependency map Data/Query/Index/Search/Analytics/Eventing/XDCR?
- [ ] Readiness contract được viết rõ theo route và khả năng degrade?
- [ ] Liveness độc lập shared Couchbase outage?
- [ ] Đã cân nhắc all-pods-NotReady và cascading failure?
- [ ] KV probe dùng đúng bucket/scope/collection và read-only operation?
- [ ] `exists(false)` được hiểu là response hợp lệ?
- [ ] SQL++ Query Engine check khác named index path check?
- [ ] Index online, query plan/`EXPLAIN` được kiểm tra trong smoke/deploy workflow?
- [ ] Search index readiness/freshness được giám sát riêng với SQL++ GSI?
- [ ] Analytics không bị tính là DOWN nếu không dùng; ingestion lag tách khỏi engine?
- [ ] Eventing function state và processing backlog được đo riêng?
- [ ] XDCR source/target health và lag được theo dõi độc lập?
- [ ] SDK ping/diagnostics được diễn giải theo endpoint/service, không chỉ boolean?
- [ ] Không tạo `Cluster.connect` mới cho mỗi probe?
- [ ] Spring Boot contributor names/health groups được xác minh trên version thật?
- [ ] Kubernetes probe path/port/timeout khớp main serving path?
- [ ] Probe có timeout, tần suất và concurrency hợp lý?
- [ ] Không ghi/xóa document và tạo side effect trong readiness?
- [ ] Cảnh báo có p95/p99, errors, backlog, freshness ngoài trạng thái UP?
- [ ] Health response không lộ credential, PII, topology hoặc stack traces?
- [ ] Reactive health không block event loop hoặc tự subscribe fire-and-forget?
- [ ] Tests bao gồm partial failure và recovery trong môi trường cô lập?
- [ ] Có runbook theo từng service thay vì restart chung?
- [ ] CAS, TTL, durability, transaction, cache, idempotency và freshness có tests riêng?

## 36. Kết luận

**Health check của Spring Boot không đồng nghĩa mọi dịch vụ Couchbase đều sẵn sàng.** Một SDK ping, KV `exists`, SQL++ `SELECT RAW 1`, business query dùng GSI hay Search query là những phép kiểm tra có phạm vi **khác nhau**. Data Service có thể hoạt động khi Query lỗi; Query có thể hoạt động khi một named index chưa online; Search, Analytics, Eventing và replication có trạng thái/lag riêng.

Trong hệ thống **SPRING_DATA_COUCHBASE**, hãy tổ chức quan sát theo **capability** của từng use case, giữ liveness dành cho tiến trình, dùng readiness cho quyết định routing với dependency thiết yếu, còn checks sâu cho monitoring/smoke/integration tests có giới hạn. Đồng thời đo riêng availability, tail latency, capacity và data freshness; đừng biến health endpoint thành nguồn tải, restart storm hoặc lời bảo đảm giả về CAS/transaction.

Một trạng thái `UP` hữu ích khi mọi người biết **thao tác nào đã được kiểm tra, trên dịch vụ nào, với timeout nào**. Khi đó đội ngũ vận hành sẽ xác định đúng nơi cần xử lý — Data, Query, Index, Search, Analytics, Eventing hay XDCR — thay vì chỉ nhìn một đèn xanh tổng hợp.
