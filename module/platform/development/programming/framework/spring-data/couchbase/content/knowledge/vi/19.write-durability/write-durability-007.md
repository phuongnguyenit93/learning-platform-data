# Phân biệt độ bền ghi với độ mới của chỉ mục truy vấn trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để bảo đảm hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **một mutation KV thành công với durability mạnh vẫn có thể chưa được nhìn thấy bởi SQL++** khi truy vấn dựa trên Global Secondary Index (GSI).
2. Phân biệt **độ bền ghi**, **độ mới của chỉ mục**, **tính nhất quán của truy vấn**, **CAS/optimistic locking** và **atomicity transaction**.
3. Mô tả các vai trò của **Data Service**, **Database Change Protocol (DCP)**, **Index Service** và **Query Service** trong đường ghi–đọc.
4. Sử dụng `NOT_BOUNDED`, `REQUEST_PLUS` và `consistentWith(MutationState)` đúng nhu cầu; hiểu quan hệ của `at_plus` với mutation token.
5. Chọn **KV get theo document ID** thay vì SQL++ khi yêu cầu là đọc lại đúng một record vừa ghi.
6. Đặt durability trên entity hoặc từng mutation, và đặt scan consistency trên repository/query trong Spring Data Couchbase mà không đánh đồng hai cấu hình.
7. Đánh giá tác động lên p95/p99 latency, throughput, index backlog, timeout và availability.
8. Xử lý trường hợp **ghi timeout chưa rõ đã commit hay chưa** mà không dùng SQL++ stale như bằng chứng “chưa ghi”.
9. Xây dựng integration test, failure test và runbook để phân biệt lỗi durability, index lag, query sai, thiếu chỉ mục và dữ liệu hết TTL.

## 2. Tình huống mở đầu: ghi thành công nhưng trang danh sách không thấy đơn

Ứng dụng tạo đơn trong keyspace:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Document ID: tenant::42::order::1001
~~~

Nội dung document:

~~~json
{
  "docType": "ORDER",
  "tenantId": "42",
  "status": "PAID",
  "total": 1490000,
  "createdAt": "2026-11-25T09:00:00Z"
}
~~~

Đường ghi Java SDK:

~~~java
orders.insert(
    "tenant::42::order::1001",
    body,
    insertOptions()
        .durability(DurabilityLevel.PERSIST_TO_MAJORITY)
);
~~~

Ứng dụng nhận `MutationResult` thành công, nhưng ngay sau đó trang “Đơn đã thanh toán” chạy:

~~~sql
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "ORDER"
  AND o.tenantId = "42"
  AND o.status = "PAID";
~~~

và **chưa trả về đơn mới**.

Một phản xạ sai phổ biến là:

> “Chắc `PERSIST_TO_MAJORITY` chưa đủ mạnh; hãy tăng replica hoặc sleep trước khi query.”

Trong trường hợp này, nguyên nhân có thể nằm ở **độ mới của Global Secondary Index**, không phải độ bền ghi. Mutation KV hoàn tất theo contract của Data Service, còn Index Service cập nhật GSI **bất đồng bộ**.

Nếu đã biết document ID, `orders.get(id)` qua KV có thể nhìn thấy document đã commit trong khi truy vấn theo `status` chưa thấy. Đó là hai đường truy cập với hai mốc nhất quán khác nhau.

## 3. Hai đồng hồ độc lập: commit ghi và chỉ mục bắt kịp

Hãy tưởng tượng hai đồng hồ:

- **Đồng hồ A — Mutation/Durability:** mutation đến Data Service, được commit và trả thành công khi đáp ứng mức replication/persistence yêu cầu.
- **Đồng hồ B — Index Freshness:** Index Service nhận mutation qua DCP, cập nhật chỉ mục, tạo trạng thái index đủ mới để truy vấn có thể dựa vào đó.

~~~mermaid
sequenceDiagram
    participant App as Spring Data / Java SDK
    participant Data as Data Service
    participant Rep as Data Replica
    participant Index as Index Service / GSI
    participant Query as Query Service
    App->>Data: INSERT order, PERSIST_TO_MAJORITY
    Data->>Rep: Replication/persistence theo level
    Rep-->>Data: Điều kiện durability được đáp ứng
    Data-->>App: MutationResult SUCCESS
    Note over App,Data: Ghi đã được xác nhận đủ durability
    Data-->>Index: DCP stream cập nhật bất đồng bộ
    App->>Query: SQL++ WHERE status = PAID (NOT_BOUNDED)
    Query->>Index: Scan trạng thái index hiện có
    Index-->>Query: Chưa có entry mới
    Query-->>App: Danh sách chưa gồm order
    Note over Data,Index: Sau đó Index Service bắt kịp mutation
~~~

**Các đường ở sơ đồ là tiến trình logic**, không khẳng định DCP chỉ bắt đầu sau khi client nhận success. Replication, persistence và DCP indexing có thể tiến triển đồng thời. Quan trọng là **success của durability không buộc GSI đã bắt kịp trước thời điểm response**.

### 3.1. Các mốc thời gian minh họa

| Mốc | Sự kiện | Điều biết chắc |
|---|---|---|
| T0 | Client gửi `insert` với `MAJORITY` | Đang thực hiện |
| T1 | Data Service commit, SDK nhận success | Mutation đáp ứng durability **hiệu lực** |
| T2 | KV `get(id)` thấy document mới | Document đã commit và có thể đọc theo ID |
| T3 | SQL++ `NOT_BOUNDED` lọc `status=PAID` chưa thấy | Chỉ mục có thể chưa theo kịp |
| T4 | DCP update được Index Service áp dụng | GSI có trạng thái mới hơn |
| T5 | SQL++ cùng predicate thấy document | Truy vấn được phục vụ từ index đủ mới |

T2 và T3 **có thể cùng đúng**. Không có mâu thuẫn giữa “document đã commit” và “chỉ mục truy vấn chưa thấy”.

### 3.2. “Đã bền” và “đã thấy” không kéo theo nhau

- Mutation đạt `PERSIST_TO_MAJORITY` **không** có nghĩa mọi GSI đã cập nhật.
- Query `REQUEST_PLUS` thấy document **không** chứng minh mutation trước được persist trên majority nếu nó vốn chỉ yêu cầu `NONE`.
- GSI đã cập nhật trên Index node **không phải** Data replica có thể dùng để chứng minh quorum.
- Một request SQL++ trả kết quả mới **không** thay thế backup, transaction hoặc CAS.

## 4. Data Service, DCP, Index Service và Query Service làm gì?

### 4.1. Data Service — nơi KV mutation được xử lý

Document ID được ánh xạ vào vBucket. Data node giữ **active vBucket** tiếp nhận mutation; các Data nodes khác có thể giữ replica tùy bucket.

Các lệnh `insert`, `get`, `replace` và `remove` theo ID dùng Data Service. Chúng không cần SQL++ secondary index để tìm document.

### 4.2. DCP — luồng thay đổi dữ liệu

**Database Change Protocol (DCP)** chuyển các sự kiện thay đổi tài liệu từ Data Service sang những thành phần cần theo dõi như Index Service. Indexer/projector tiêu thụ luồng thay đổi và cập nhật các entry GSI có liên quan.

DCP là cơ chế **lan truyền cập nhật**, không phải mức durability per-operation. Một mutation được Data Service xác nhận không bắt buộc đợi tất cả consumers DCP xử lý hết.

### 4.3. Index Service — trạng thái của Global Secondary Index

GSI lưu cấu trúc tìm kiếm theo field, ví dụ `tenantId`, `status`, `createdAt`. Index Service bảo trì GSI **bất đồng bộ** để tránh buộc từng KV mutation phải cập nhật mọi index đồng bộ trên đường ghi.

Đổi lại, truy vấn dùng trạng thái index hiện có có thể bỏ sót một document mới hoặc chưa phản ánh field vừa đổi.

### 4.4. Query Service — lập kế hoạch và thực thi SQL++

SQL++ Query Service dùng index làm đường truy cập theo predicate; sau đó có thể fetch document hoặc dùng index covering tùy query plan.

Nếu index chưa có entry cho một document mới, Query Service không thể luôn tìm ra document đó chỉ nhờ việc mutation KV đã commit. Tùy query plan, sự chậm cập nhật index có thể làm thiếu row hoặc dùng dữ liệu tìm kiếm cũ.

~~~mermaid
flowchart LR
    Client["Ứng dụng Spring Boot"]
    KV["Data Service<br/>active/replica vBucket"]
    DCP["DCP / projector"]
    IDX["Index Service<br/>GSI"]
    Q["Query Service<br/>SQL++"]
    Client -->|"KV get / insert / replace"| KV
    KV -->|"Sự kiện mutation bất đồng bộ"| DCP
    DCP --> IDX
    Client -->|"SELECT WHERE status..."| Q
    Q -->|"Index scan"| IDX
    Q -.->|"Fetch document khi query plan cần"| KV
~~~

### 4.5. Index replica không phải Data replica

Index Service có thể bố trí **replica của GSI** để tăng availability truy vấn. Data Service có **replica vBucket** để hỗ trợ availability và durability ghi.

Hai loại replica có thể đều được gọi là “replica” trong dashboard, nhưng GSI replica **không tính vào majority Data durability**. Ngược lại, một Data replica thêm vào bucket không tự làm query có index tốt hơn.

## 5. DurabilityLevel bảo đảm cái gì?

Couchbase Java SDK 3.x sử dụng:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
~~~

| Durability level | Khi mutation được trả success | Không tự bảo đảm |
|---|---|---|
| **`NONE`** | Không có yêu cầu synchronous durability bổ sung từ mutation, trừ bucket minimum | Data replica đã xác nhận, GSI đã bắt kịp |
| **`MAJORITY`** | Đạt yêu cầu xác nhận majority theo SyncWrite protocol | GSI cập nhật, active persisted nếu level không yêu cầu |
| **`MAJORITY_AND_PERSIST_TO_ACTIVE`** | Majority cùng persistence trên active | GSI cập nhật, mọi replica đã persist |
| **`PERSIST_TO_MAJORITY`** | Mutation persist theo majority theo semantics mức này | GSI cập nhật, backup/DR hay tính đúng của business logic |

Mức durability ở server có thể bị **minimum durability của bucket** ràng buộc. Để yêu cầu thành công, môi trường phải hỗ trợ synchronous durability: loại bucket/storage engine, replica count, node health và version phù hợp.

### 5.1. Một câu dễ nhớ

**Durability trả lời:** “Mutation đã được xác nhận ở những bản dữ liệu nào trước success?”

**Index freshness trả lời:** “Chỉ mục được SQL++ sử dụng đã phản ánh mutation nào tại thời điểm query?”

Hai câu hỏi khác nhau ngay cả khi chúng cùng ảnh hưởng thứ người dùng nhìn thấy.

### 5.2. Mức bền mạnh không khiến Query Service đồng bộ hơn

Dù chọn `PERSIST_TO_MAJORITY`, một SQL++ query `NOT_BOUNDED` vẫn có thể được thực thi dựa trên index chưa theo kịp. Muốn index bắt kịp một mốc cần **scan consistency**, không phải thay mức durability.

### 5.3. Chọn level theo RPO, không theo UI freshness

Chọn `MAJORITY` hay `PERSIST_TO_MAJORITY` dựa trên nhu cầu chịu lỗi Data node, disk/persistence, RPO và chi phí latency. Nếu UI cần vừa tạo đơn xong thấy đơn trong danh sách, hãy thiết kế **read-after-write/query scan consistency** riêng.

## 6. Truy vấn SQL++ nhanh hay đủ mới: các chế độ scan consistency

Couchbase SQL++ có những chế độ kiểm soát mốc cập nhật của index scan.

| Chế độ ở SQL++ | Ý nghĩa | Hệ quả thường gặp |
|---|---|---|
| **`not_bounded`** / SDK `NOT_BOUNDED` | Scan trạng thái index hiện có, không yêu cầu chờ cập nhật tới một mốc cụ thể | Latency thấp hơn, có thể trả dữ liệu chưa mới |
| **`request_plus`** / SDK `REQUEST_PLUS` | Đợi các index liên quan bắt kịp tới mốc mutation tại thời điểm query request theo semantics Query Service | Thấy các mutation đã commit trước mốc yêu cầu, nhưng có thể đợi lâu hoặc timeout |
| **`at_plus`** | Đợi index đạt **mutation vector/token** cụ thể được caller cung cấp | Phù hợp read-your-own-writes, chỉ chờ phạm vi mutation đã biết |
| **`statement_plus`** | Chế độ mạnh hơn theo từng SQL++ statement ở server/API hỗ trợ | Không phải mọi Java SDK enum/abstraction đều cung cấp cùng option |

Mặc định SQL++/Java SDK thường là **`not_bounded`**. Các Spring Data repository query cũng có mặc định/query-level setting; cần kiểm tra annotation/configuration hiện hành chứ không kết luận tất cả query trong mọi project dùng một level duy nhất.

### 6.1. `NOT_BOUNDED` — ưu tiên độ trễ

`NOT_BOUNDED` không bắt index chờ cập nhật. Dùng cho trang danh sách, analytics gần thời gian thực hoặc màn hình chấp nhận trễ ngắn.

~~~java
QueryResult result = cluster.query(sql,
    queryOptions()
        .scanConsistency(QueryScanConsistency.NOT_BOUNDED));
~~~

Một query trả row thiếu dữ liệu mới có thể là **hành vi hợp lệ theo contract này**. Nếu sản phẩm yêu cầu vừa ghi xong là thấy, đây có thể là cấu hình chưa phù hợp, không phải Couchbase đánh mất mutation.

### 6.2. `REQUEST_PLUS` — chờ mốc index của request

`REQUEST_PLUS` yêu cầu Query Service chờ index liên quan bắt kịp một vector timestamp tại thời điểm request. Nó không tự đặt durability cho mutation; nó chỉ **chờ độ mới của index**.

~~~java
QueryResult result = cluster.query(sql,
    queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS));
~~~

Nếu Index Service trì trệ, query này có thể chậm hơn `NOT_BOUNDED` hoặc gặp timeout. Khi cần “toàn bộ những mutation đã commit trước query được phản ánh”, cân nhắc nó cùng SLA và khả năng Index Service.

### 6.3. `AT_PLUS` — mốc cụ thể từ mutation đã biết

Ở cấp SQL++ wire protocol, `at_plus` dùng mutation scan vector do caller cung cấp. Ở Java SDK, lựa chọn tiện lợi là `queryOptions().consistentWith(MutationState)`.

Ý tưởng: ứng dụng vừa ghi một order, có mutation token; hãy chờ index bao gồm **ít nhất mutation đó** thay vì chờ toàn bộ mutation mới của cluster.

**Lưu ý:** `consistentWith` và `scanConsistency(REQUEST_PLUS)` là **hai tùy chọn loại trừ nhau** trong Java SDK QueryOptions. Không chain cả hai trên cùng query rồi kỳ vọng chúng hợp nhất.

### 6.4. “Chờ đúng mốc” không có nghĩa “không bao giờ stale”

Cả `REQUEST_PLUS` và `AT_PLUS` đều liên quan **một mốc**. Chúng không thể hứa nhìn thấy mutation **xảy ra sau mốc query** hoặc tạo snapshot giao dịch xuyên nhiều hệ thống ngoài Couchbase.

Để đọc document ID vừa ghi, KV get thường đơn giản và trực tiếp hơn; khi cần SQL++ theo field mới phải cân nhắc consistency của index scan.

## 7. Ma trận 2 × 2: durability và query consistency độc lập

Giả sử chỉ xét hai lựa chọn ghi và hai lựa chọn query:

| Ghi | Query SQL++ | Có thể xảy ra | Ý nghĩa |
|---|---|---|---|
| `NONE` | `NOT_BOUNDED` | Query thiếu row mới | Ghi không đợi majority, index cũng không bắt buộc mới |
| `NONE` | `REQUEST_PLUS` | Query thấy row nhưng sau đó active mất và mutation có thể không được bảo vệ theo kỳ vọng | Index freshness **không nâng** durability của ghi |
| `PERSIST_TO_MAJORITY` | `NOT_BOUNDED` | Ghi đủ bền nhưng query tạm thiếu row | Trường hợp mở đầu bài học |
| `PERSIST_TO_MAJORITY` | `REQUEST_PLUS` | Ghi được xác nhận mạnh và query chờ index bắt kịp | Đáp ứng **hai mục tiêu khác nhau**, đổi lại write và query latency |

Bảng là mô hình lý luận; tình huống lỗi thật phụ thuộc topology, policy, query plan và thời điểm failure. Không suy ra `NONE` chắc chắn mất dữ liệu hoặc `REQUEST_PLUS` chắc chắn không thể timeout.

### 7.1. Tại sao hai trục phải được review riêng?

Một Product Owner có thể cần:

- Không mất order đã xác nhận trong kịch bản một Data node lỗi.
- Sau checkout, UI hiển thị đúng order ngay.
- Trang báo cáo 30 ngày không cần chờ mỗi thay đổi cuối giây.
- Giao dịch thanh toán không charge trùng.

Lúc đó có ít nhất **bốn biện pháp**, không phải một enum: durability, KV/scan consistency, idempotency và business transaction/workflow.

## 8. KV get theo ID: phương án đơn giản cho read-after-write

Nếu đã biết `documentId`:

~~~java
var saved = orders.insert(
    orderId,
    body,
    insertOptions().durability(DurabilityLevel.MAJORITY)
);

var readBack = orders.get(orderId);
~~~

`get` theo ID truy cập Data Service, **không cần GSI** để tìm record. Khi mutation đã được server commit và SDK trả success, đọc KV từ active owner là con đường phù hợp để xem body mới.

Điều kiện/giới hạn:

- Đảm bảo cùng bucket/scope/collection và đúng ID.
- Nếu dùng **replica read** riêng, semantics độ mới có thể khác với KV get từ active.
- Nếu mutation trước **ambiguous**, KV get thấy hoặc không thấy tại một thời điểm chưa thay thế toàn bộ reconciliation.
- Nếu document có TTL rất ngắn hoặc writer khác sửa/xóa, kết quả có thể đổi hợp lệ.
- `get` không tự xác minh business transition hoặc payload fingerprint.

### 8.1. Ví dụ UX tối ưu

Sau tạo order thành công:

1. API trả `201 Created` kèm `orderId` và dữ liệu order đã ghi.
2. Trang chi tiết hiển thị dữ liệu trả về hoặc gọi `GET /orders/{id}` (KV).
3. Danh sách theo `status` có thể dùng SQL++ `NOT_BOUNDED` theo SLA cập nhật trễ, hoặc dùng `REQUEST_PLUS` khi yêu cầu nhất quán mạnh ngay.
4. UI nên phân biệt “chi tiết đơn đã tạo” với “danh sách đã lập chỉ mục”.

Không buộc trang danh sách dùng `REQUEST_PLUS` vô điều kiện nếu người dùng chỉ cần thấy order mới bằng một màn hình chi tiết.

## 9. Ví dụ SQL++: index cho danh sách đơn hàng

Giả sử truy vấn phổ biến:

~~~sql
SELECT META(o).id AS id, o.status, o.total, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "ORDER"
  AND o.tenantId = "42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một index ứng viên:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`
   (tenantId, status, createdAt DESC)
WHERE docType = "ORDER";
~~~

Điều kiện `docType = "ORDER"` trong query giúp phù hợp partial index. Tùy kế hoạch, index có thể cần thêm field để tránh fetch hoặc đáp ứng tối ưu sort; cần kiểm tra `EXPLAIN` và workload thực tế.

**Trước khi kết luận index lag, kiểm tra có index phù hợp và ở trạng thái online.** `REQUEST_PLUS` không thể tạo một index còn thiếu. Index về mặt logic chỉ hữu ích nếu query planner sử dụng nó.

### 9.1. SQL++ query với độ trễ chấp nhận được

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

String sql = """
    SELECT META(o).id AS id, o.status, o.total
    FROM `commerce`.`sales`.`orders` AS o
    WHERE o.docType = "ORDER"
      AND o.tenantId = $tenantId
      AND o.status = $status
    """;

var opts = queryOptions()
        .parameters(
            JsonObject.create()
                .put("tenantId", "42")
                .put("status", "PAID")
        )
        .scanConsistency(QueryScanConsistency.NOT_BOUNDED);

var rows = cluster.query(sql, opts).rowsAsObject();
~~~

Ví dụ dùng Java text block (Java 15+), giả định `cluster` và `JsonObject` được import/cấu hình phù hợp. Named parameters tránh nối trực tiếp dữ liệu người dùng vào SQL++.

### 9.2. Query cần thấy các write đã commit trước yêu cầu

~~~java
var opts = queryOptions()
        .parameters(
            JsonObject.create()
                .put("tenantId", "42")
                .put("status", "PAID")
        )
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);

var rows = cluster.query(sql, opts).rowsAsObject();
~~~

Chỉ thay **query option**. Durability của mutation trước đó không bị thay đổi và không cần thực hiện lại mutation.

### 9.3. Query timeout có thể xuất hiện khi đợi index

Nếu Query Service cần chờ index bắt kịp nhưng Index Service chậm, query `REQUEST_PLUS` có thể hết `queryTimeout` hoặc `scanWait` tùy cấu hình. Trường hợp đó cần chẩn đoán **Index/Query Service**, không chỉ tăng `kvDurableTimeout` vốn thuộc đường ghi KV.

## 10. Java SDK: MutationResult, MutationToken và MutationState

Khi ghi qua Couchbase Java SDK, `MutationResult` có thể chứa `MutationToken`. Token cho biết vị trí mutation trong luồng thay đổi theo vBucket; Java SDK sử dụng nó để tạo `MutationState` cho query consistency.

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.kv.MutationState;
import com.couchbase.client.java.json.JsonObject;

MutationResult mutation = orders.insert(
    orderId,
    body,
    insertOptions().durability(DurabilityLevel.MAJORITY)
);

var token = mutation.mutationToken()
        .orElseThrow(() ->
            new IllegalStateException(
                "Mutation token không khả dụng; cần chọn chiến lược query khác"
            )
        );

MutationState state = MutationState.from(token);

var queryResult = cluster.query(
    sql,
    queryOptions()
        .parameters(JsonObject.create()
            .put("tenantId", "42")
            .put("status", "PAID"))
        .consistentWith(state)
);
~~~

**Import chính xác:** trong Java SDK 3.x, `MutationState` thuộc `com.couchbase.client.java.kv`, không phải package `query`.

### 10.1. Ý nghĩa của `consistentWith`

Query Service phải chờ trạng thái index liên quan bắt kịp **các mutation token trong state**. Nó phù hợp khi bạn chỉ cần chính những ghi đã biết của mình được phản ánh.

### 10.2. Token có thể không tồn tại

`MutationResult.mutationToken()` trả về một `Optional`. Ứng dụng phải xử lý trường hợp token thiếu do đặc điểm API/phiên bản/cấu hình. Không gọi `.get()` mù quáng rồi chuyển lỗi đó thành “database mất dữ liệu”.

Những lựa chọn khi không có token:

- Nếu biết ID, dùng KV get.
- Nếu cần SQL++ theo field và chấp nhận chờ toàn bộ mốc query, dùng `REQUEST_PLUS`.
- Đánh giá SDK/server version và khả năng mutation tokens theo môi trường.
- Nếu ghi trước đó ambiguous nên **không có MutationResult rõ ràng**, dùng luồng reconciliation thay vì bịa token.

### 10.3. Không chain `REQUEST_PLUS` và `consistentWith`

~~~java
// Sai về cách dùng API: hai chế độ này loại trừ nhau.
queryOptions()
    .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
    .consistentWith(state);
~~~

Chọn **một**:

- `REQUEST_PLUS` nếu cần mốc chung của query.
- `consistentWith(state)` nếu chỉ cần mốc của một hoặc vài mutation đã biết.

### 10.4. Nhiều mutation và cùng một truy vấn

Nếu workflow thực hiện vài KV mutations có tokens, ứng dụng có thể tích lũy các token vào một `MutationState` để query chờ các mutation đó.

~~~java
MutationState state = MutationState.from(tokenOrder);
state.add(tokenOther);

var rows = cluster.query(
    sql,
    queryOptions().consistentWith(state)
).rowsAsObject();
~~~

Cần bảo đảm tokens tương ứng keyspaces/partition và query hỗ trợ, đồng thời nhớ rằng một nhóm mutation độc lập **không tự trở thành transaction** chỉ vì cùng MutationState.

## 11. Hình dung chênh lệch độ trễ giữa các chiến lược đọc

~~~mermaid
flowchart TD
    A["Mutation KV đã được ack theo durability level"]
    B{"Đọc cần gì?"}
    KV["Đọc đúng ID<br/>KV get"]
    Q1["SQL++ NOT_BOUNDED<br/>Không chờ mốc mới"]
    Q2["SQL++ REQUEST_PLUS<br/>Chờ index tại mốc query"]
    Q3["SQL++ consistentWith(state)<br/>Chờ token đã biết"]
    A --> B
    B -->|"Chi tiết theo ID"| KV
    B -->|"Danh sách chấp nhận trễ"| Q1
    B -->|"Danh sách phải cập nhật theo request"| Q2
    B -->|"Danh sách phải chứa ghi đã biết"| Q3
~~~

| Phương án | Mục tiêu chính | Latency/chi phí thường gặp |
|---|---|---|
| **KV get** | Đọc một document theo ID | Không cần GSI, thường thấp nếu Data Service khỏe |
| **SQL++ `NOT_BOUNDED`** | Truy vấn nhanh trên index hiện có | Có thể thiếu mutation mới |
| **SQL++ `REQUEST_PLUS`** | Mốc mới của index theo query | Có thể chờ DCP/index, tăng p95/p99 |
| **SQL++ `consistentWith`** | Chờ mutation đã biết | Có thể bớt chờ hơn `REQUEST_PLUS` khi toàn cluster ghi nhiều |
| **SQL++ không có index đúng** | Không đáp ứng bằng option consistency | Phải sửa query/index, không chỉ chờ |

Độ trễ thực tế phụ thuộc cluster load, number of indexes, vBucket changes, indexer backlog và query plan. Đừng khẳng định `consistentWith` luôn nhanh hơn `REQUEST_PLUS` mà không benchmark.

## 12. Spring Data Couchbase: mapping và durability trên entity

Ví dụ entity có mặc định ghi `MAJORITY`:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String docType;
    private String tenantId;
    private String status;
    private Long total;
    private String createdAt;

    // Constructor và accessors được lược bỏ.
}
~~~

`@Document(durabilityLevel = ...)` đặt **mức durability mặc định cho mutation qua mapping Spring Data** ở những phiên bản hỗ trợ. Nó **không** đặt query scan consistency.

`@Version` là CAS/optimistic locking, không phải durability. `@Scope` và `@Collection` xác định keyspace, không xác định độ mới chỉ mục.

### 12.1. Repository `save` và `findById`

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument stored = orderRepository.save(order);

OrderDocument again = orderRepository.findById(stored.getId())
        .orElseThrow();
~~~

`findById` đi theo đường KV theo document ID; không cần GSI để tìm record. Nếu chỉ cần chi tiết order vừa lưu, đây là cơ chế tránh phụ thuộc index freshness.

**Điều kiện:** class `OrderDocument` phải có getters/constructors thích hợp; ví dụ lược bỏ boilerplate. Và trong production cần đúng bucket, scope, collection và các cấu hình conversion.

### 12.2. Derived repository query theo field khác đường KV

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status
    );
}
~~~

Query derived theo `tenantId` và `status` thường dùng SQL++/GSI và có thể chịu index lag. Đừng thấy `findById` nhanh, mới rồi suy ra `findByTenantIdAndStatus` cũng nhìn thấy write ngay.

### 12.3. Document metadata tách hai lựa chọn

Trong Spring Data Couchbase phiên bản hỗ trợ, `@Document` còn có `queryScanConsistency`:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(
    durabilityLevel = DurabilityLevel.MAJORITY,
    queryScanConsistency = QueryScanConsistency.NOT_BOUNDED
)
public class OrderDocument {
    // @Id và các field khác...
}
~~~

Cùng annotation chứa **hai thuộc tính độc lập**:

- `durabilityLevel`: ghi có đợi majority/persistence không?
- `queryScanConsistency`: SQL++ query được sinh qua Spring Data dùng mức scan consistency nào?

Không nhầm `@Document.queryScanConsistency` với SQL++ index consistency của toàn bucket; đây là metadata của đường framework.

## 13. Spring Data Couchbase: `@ScanConsistency` trên repository query

Khi một derived query cần chờ index bắt kịp, Spring Data Couchbase cung cấp annotation:

~~~java
import java.util.List;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status
    );
}
~~~

Ở method này, query được yêu cầu `REQUEST_PLUS` theo API Spring Data version hỗ trợ. Các method khác có thể dùng default cấu hình từ entity/framework.

**Không đặt `@ScanConsistency` lên mutation rồi coi là tăng durability**: nó là cấu hình đường truy vấn theo GSI, không thay `@Document.durabilityLevel`.

### 13.1. Khi nào đặt consistency trên method?

Đặt mức mạnh hơn ở một endpoint “ngay sau khi ghi phải nhìn thấy” thường hợp lý hơn việc buộc **mọi báo cáo/danh sách** trong ứng dụng chờ index mới.

Ví dụ:

- `GET /orders?status=PAID` trên màn hình xác nhận vừa checkout: có thể yêu cầu `REQUEST_PLUS`.
- Trang quản trị liệt kê hàng nghìn order lịch sử: `NOT_BOUNDED` thường phù hợp nếu SLA cho phép cập nhật trễ.
- `GET /orders/{id}`: KV theo ID không cần GSI scan consistency.

### 13.2. Khác biệt với custom SQL++ query

Nếu repository dùng `@Query` với SQL++ tùy biến, cần kiểm tra logic framework sinh keyspace/type filter, mapping projection và option scan consistency theo phiên bản. Một query sai scope hoặc thiếu predicate không được sửa chỉ bằng `REQUEST_PLUS`.

### 13.3. Template/query fluent API

Với Spring Data Couchbase phiên bản hỗ trợ, fluent `findByQuery` có `withConsistency(QueryScanConsistency.REQUEST_PLUS)`. Cần kiểm tra method chain theo dependency thực tế; ví dụ định hướng:

~~~java
var found = template.findByQuery(OrderDocument.class)
    .withConsistency(QueryScanConsistency.REQUEST_PLUS)
    .matching(query(where("status").is("PAID")))
    .all();
~~~

Đây là code định hướng về **chỗ chọn scan consistency**, giả định đã import `Query.query`, `Criteria.where` và template đúng phiên bản. Khi đưa vào codebase, kiểm tra generated SQL++/mapping và có index phù hợp.

## 14. `@ScanConsistency` không ép KV get chờ Index Service

Nếu Spring Data entity hoặc repository được đánh dấu `REQUEST_PLUS`:

- Method **KV `findById`** vẫn tìm document theo ID qua Data Service.
- Method **SQL++/GSI** áp dụng query scan consistency trên đường truy vấn tương ứng.
- Method **`save`** vẫn cần durability riêng nếu nghiệp vụ cần majority/persistence.

Một annotation query không thể biến cả repository thành cơ chế giao dịch bền và nhất quán ở mọi kiểu API.

## 15. Spring Data `CouchbaseTemplate.withDurability` khác `withConsistency`

Đặt cạnh nhau để thấy ý nghĩa:

~~~java
// MUTATION: điều kiện xác nhận ghi.
OrderDocument saved = template
    .upsertById(OrderDocument.class)
    .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
    .one(order);
~~~

~~~java
// QUERY: mức mới của secondary index được dùng để scan.
var list = template.findByQuery(OrderDocument.class)
    .withConsistency(QueryScanConsistency.REQUEST_PLUS)
    .matching(query(where("status").is("PAID")))
    .all();
~~~

Tóm tắt:

| Method | Tác động đến | Không giải quyết |
|---|---|---|
| `upsertById(...).withDurability(...)` | Mutation KV đi tới Data Service | GSI freshness, lost update nếu dùng upsert mù quáng |
| `findByQuery(...).withConsistency(...)` | SQL++ query và GSI scan | Persistence của mutation trước đó, duplicate request |
| `repository.findById(id)` | KV read theo ID | Full-text/secondary-index search |
| `repository.findByStatus(status)` | SQL++/index path | Không tự chờ index nếu policy là `NOT_BOUNDED` |

## 16. Query consistency và performance: chi phí nằm ở đâu?

~~~mermaid
flowchart TD
    R["SQL++ SELECT"]
    Mode{"Scan consistency?"}
    Fast["NOT_BOUNDED<br/>Dùng index hiện có"]
    Wait["REQUEST_PLUS / AT_PLUS<br/>Đợi mốc DCP/index"]
    Index["Index scan + fetch/aggregate"]
    Reply["Trả result hoặc timeout/error"]
    R --> Mode
    Mode --> Fast
    Mode --> Wait
    Fast --> Index
    Wait --> Index
    Index --> Reply
~~~

Với `NOT_BOUNDED`, Query Service có thể dùng index snapshot hiện có và không phải chờ DCP bắt kịp một mốc mới.

Với `REQUEST_PLUS`, query có thêm chi phí lấy vector timestamp và đợi index cần thiết theo kịp. Nếu có Index Service node chậm, index build/rebalance hoặc ghi burst, phần chờ có thể lớn và gây tail latency.

Với `consistentWith(MutationState)`, query chỉ cần mốc token được đưa vào (theo semantics hỗ trợ), nên đôi khi giảm chờ không cần thiết so với `REQUEST_PLUS`. Nhưng vẫn phải có index phù hợp và service đủ khỏe.

### 16.1. Tăng write durability không thay query latency theo một quy luật cố định

Nếu mutation `PERSIST_TO_MAJORITY` đã chờ storage lâu, Index Service **có thể** đã bắt kịp vào lúc app query, nhưng điều đó chỉ là tình cờ do thời gian trôi qua. Không thể dựa trên tương quan đó để bỏ `REQUEST_PLUS` khi sản phẩm yêu cầu query luôn theo kịp.

### 16.2. Chọn SLA theo endpoint

- KV write p99: đo thời gian mutation và durability level.
- SQL++ `NOT_BOUNDED` p99: đo execution hiện tại, có thể chấp nhận stale.
- SQL++ `REQUEST_PLUS` p99: đo cả **thời gian chờ index catch-up**.
- HTTP p99: đo cả service + DB + network.

Không chỉ theo dõi một “Couchbase latency” rồi quy mọi nghẽn cho Data node.

## 17. Update và delete: index lag không chỉ làm thiếu record mới

Ví dụ một document đang ở trạng thái `NEW`:

~~~json
{
  "docType": "ORDER",
  "tenantId": "42",
  "status": "NEW",
  "total": 1490000
}
~~~

API thay `status` thành `PAID` bằng KV `replace` thành công. Vì chỉ mục `(tenantId, status, createdAt)` cập nhật bất đồng bộ, trong khoảng chênh lệch:

- Query `WHERE status = "PAID"` ở `NOT_BOUNDED` **có thể chưa tìm được** order.
- Query `WHERE status = "NEW"` có thể vẫn dùng trạng thái index cũ làm ứng viên, nhưng nội dung kết quả thực tế còn phụ thuộc query plan/fetch/filter.
- `get(orderId)` từ Data Service đã thấy body đã commit, nếu không có writer khác thay đổi.

Không nên hứa rằng stale GSI luôn hiển thị toàn bộ body cũ, vì một query có thể fetch body mới và lọc lại. Điều chắc chắn là **đường truy vấn theo index có thể không phản ánh ngay trạng thái mutation mới**.

### 17.1. Xóa document và GSI

Nếu `orders.remove(orderId)` trả success theo durability đã chọn, thay đổi xóa cũng phải được truyền qua DCP để index loại bỏ entry tương ứng.

Trong thời gian lag, index có thể còn entry ứng viên. Query có thể phải fetch Data Service và xử lý record đã mất; hành vi row cuối phụ thuộc covering index, query plan và server version. Không dùng “index còn entry” làm bằng chứng rằng việc xóa đã không commit.

### 17.2. TTL/expiry và index freshness

Khi TTL hết hạn, thay đổi lifecycle làm document không còn hợp lệ. Việc loại bỏ khỏi GSI có thể có độ trễ tương tự, nhưng expiry còn chịu semantics truy vấn/fetch của engine.

Ba điều khác nhau:

1. `expiry`: document tồn tại tới khi nào theo policy.
2. `DurabilityLevel`: mutation trước đó được xác nhận thế nào.
3. `scanConsistency`: GSI phải mới tới đâu khi query.

Không bật `PERSIST_TO_MAJORITY` để “ngăn order hết hạn” hoặc thay TTL bằng `REQUEST_PLUS`.

### 17.3. CAS không làm GSI mới

`@Version` của Spring Data Couchbase và `ReplaceOptions.cas(...)` dùng CAS để tránh cập nhật dựa trên document cũ.

Một `replace` đã thành công sau CAS check vẫn có thể chưa được truy vấn SQL++ theo field phản ánh ngay. CAS bảo vệ **concurrency**, không bảo vệ độ mới của GSI.

## 18. SQL++ scan consistency không phải transaction isolation

Giả sử workflow tạo order và giảm inventory:

~~~text
Mutation 1: insert order::1001
Mutation 2: replace inventory::sku-A1
~~~

Nếu hai mutation thực hiện riêng biệt, kể cả cả hai dùng `PERSIST_TO_MAJORITY` và query sau đó dùng `REQUEST_PLUS`, chúng **không tự thành một transaction nhiều document**. Một mutation có thể thành công, mutation còn lại có thể lỗi.

### 18.1. Atomicity nhiều document cần cơ chế khác

Couchbase Transactions cung cấp atomicity/commit semantics phù hợp cho một nhóm mutation theo version và API. Query scan consistency chỉ kiểm soát **mốc cập nhật của index** trước khi scan, không tự rollback một nhóm ghi nếu một bước thất bại.

### 18.2. Sau khi transaction commit

Sau khi transaction hoàn tất, một query index-based có thể cần cơ chế scan consistency để bảo đảm nhìn thấy những thay đổi đã commit tại mốc yêu cầu. Cần kiểm tra **transaction query API và consistency option** cụ thể khi truy vấn nằm bên trong transaction, thay vì lấy cùng một `QueryOptions` bên ngoài áp bừa.

### 18.3. Query với `REQUEST_PLUS` không tạo snapshot toàn hệ thống

Đối với nhiều hệ thống như Couchbase, Kafka và payment gateway, `REQUEST_PLUS` không bảo đảm trạng thái xuyên hệ thống đồng bộ, hoặc mọi HTTP caller đọc cùng snapshot nghiệp vụ. Cần thiết kế saga/outbox, idempotency và reconciliation khi workflow vượt ranh giới database.

## 19. Kết quả ghi ambiguous: SQL++ không phải công cụ kết luận chính

Một mutation có thể đã commit nhưng client mất response do mạng hoặc timeout:

~~~mermaid
sequenceDiagram
    participant App as Order API
    participant Data as Active Data node
    participant Rep as Replica
    participant IDX as Index Service
    App->>Data: INSERT order + MAJORITY
    Data->>Rep: Replicate/confirm
    Rep-->>Data: Đủ điều kiện
    Note over Data,Rep: Có thể đã commit
    Data--xApp: Response thất lạc
    App->>IDX: SQL++ NOT_BOUNDED tìm order
    IDX-->>App: Không có entry tại thời điểm scan
    Note over App: Không được kết luận chắc chắn mutation chưa xảy ra
~~~

Với outcome ambiguous:

- Không có `MutationResult` thành công rõ ràng thì có thể **không có mutation token** để dùng `consistentWith`.
- Query `NOT_BOUNDED` thiếu row **không chứng minh write chưa commit**.
- Ngay cả `REQUEST_PLUS` tại một thời điểm cũng không thay thế **quy trình kiểm tra pending/late commit, business idempotency và failure status**.
- Ưu tiên **KV get theo ID ổn định** và so sánh business fields/fingerprint; nếu vẫn không rõ, giữ request trong reconciliation.
- Không sinh document ID mới chỉ vì không thấy SQL++ row.

### 19.1. KV readback vẫn phải được hiểu đúng

Một lần `get(id)` không thấy record có thể xảy ra khi mutation chưa commit, đang pending, đã abort, hoặc document đã bị xóa/hết hạn trong một luồng khác. Kết hợp với timeout ambiguous, một lần not-found không cho phép suy ra “server chắc chắn chưa ghi và sẽ không ghi”.

### 19.2. ID/idempotency key ổn định

~~~text
Request: POST /checkout
Idempotency-Key: checkout-abc

Document ID:
tenant::42::checkout::checkout-abc

Tất cả HTTP retries vẫn dùng ID này.
~~~

Với `insert`, lần retry báo `DocumentExistsException` có thể do mutation đầu đã thành công. Cần đọc record và đối chiếu tenant, checkout ID, request fingerprint và trạng thái trước khi trả kết quả cũ.

### 19.3. Token không phải bằng chứng của nghiệp vụ ngoài database

Một mutation token cho phép query chờ index tại mốc của mutation đã biết. Nó **không chứng minh** payment gateway đã charge đúng một lần, email đã gửi hoặc nhiều document đã commit cùng transaction.

## 20. Request-plus có thể chậm, timeout hoặc trả lỗi

Với `REQUEST_PLUS`, Query Service chờ index bắt kịp. Vì vậy:

- Nếu DCP đã bắt kịp trước lúc query, độ trễ tăng có thể nhỏ.
- Nếu Index Service backlog, query có thể **đợi lâu**.
- Nếu index không online, query có thể **thất bại**; request-plus không tự tạo index.
- Nếu query có deadline ngắn, nó có thể **timeout trong khi chờ index**, dù mutation KV trước đó đã thành công.
- Sau failover, index có thể phải rollback/rebuild hoặc chờ snapshot nhất quán; độ trễ có thể thay đổi.

### 20.1. Query timeout khác KV durable timeout

| Timeout/cấu hình | Điều khiển gì? |
|---|---|
| `kvTimeout` | Thời gian chờ của operation KV thông thường |
| `kvDurableTimeout` | Thời gian chờ KV mutation có synchronous durability |
| `queryTimeout` | Deadline của SQL++ query |
| `scanWait` | Giới hạn thời gian đợi index scan nhất quán khi được hỗ trợ |
| HTTP/gateway timeout | Khi caller ngừng chờ response API |

**Tăng `kvDurableTimeout` sẽ không chữa DCP/GSI backlog**. Ngược lại, tăng `queryTimeout` không biến mutation trước đó thành `PERSIST_TO_MAJORITY`.

### 20.2. `scanWait` trong Java SDK

~~~java
import java.time.Duration;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

var result = cluster.query(
    sql,
    queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        .scanWait(Duration.ofSeconds(2))
        .timeout(Duration.ofSeconds(5))
);
~~~

Đây là ví dụ về **hai thời hạn liên quan đến query**. Các mức cụ thể chỉ minh họa; cấu hình phải được đo với SLA thực, phiên bản SDK/server và chi phí Index Service. `scanWait` không phải thao tác sleep cố định 2 giây trước khi query.

### 20.3. Không luôn bật `REQUEST_PLUS` cho mọi báo cáo

Các màn hình tổng hợp nhiều loại document có thể có nhiều query và chỉ mục. Nếu tất cả đều chờ index catch-up trên workload ghi liên tục, latency/throughput và khả năng phục vụ có thể suy giảm.

Một SLA thích hợp là **“dữ liệu danh sách có thể trễ vài giây”** kèm monitoring, thay vì yêu cầu mọi query mạnh nhất nhưng không có tài nguyên.

## 21. Kiểm tra query plan trước khi đổ lỗi cho index lag

Các nguyên nhân khiến query SQL++ không trả row mong đợi không chỉ có GSI stale:

| Nguyên nhân | Biểu hiện | Cách xác minh |
|---|---|---|
| Sai bucket/scope/collection | KV ID ở keyspace A, SQL++ quét B | So keyspace đầy đủ và SDK Collection |
| Sai predicate `tenantId`/`status` | Document tồn tại nhưng không match | Đọc body từ KV và so điều kiện |
| Sai field type | `"42"` khác `42`, date string khác timestamp | Kiểm tra schema/converter |
| Partial index không được dùng | Query thiếu điều kiện `docType` của index | `EXPLAIN`, chỉnh index/query |
| Index chưa được build/online | Query lỗi/no matching index | Kiểm tra Index Service và index state |
| GSI lag | KV mới nhưng query `NOT_BOUNDED` chưa phản ánh | So `REQUEST_PLUS`, query latency và DCP backlog |
| Spring Data type discriminator | Query sinh thêm điều kiện mapping `_class` | Kiểm tra generated SQL++/mapping |
| RBAC khác nhau | KV user có quyền, query user thiếu quyền | Kiểm tra quyền Query/Index và collection |
| TTL/delete | Document không còn khi đọc, index cleanup chậm | Kiểm tra expiry/tombstone và sự kiện xóa |
| Query timeout | `REQUEST_PLUS` đợi index nhưng hết deadline | Xem error context, query plan và Index health |

**Không dùng `REQUEST_PLUS` như một cách sửa lỗi schema hoặc missing index.** Nó chỉ yêu cầu index đủ mới trước scan.

### 21.1. `EXPLAIN` giúp xác định query đang dùng index gì

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "ORDER"
  AND o.tenantId = "42"
  AND o.status = "PAID";
~~~

Đọc plan để biết đang dùng index nào, có fetch hay covering scan, có sort/filter đắt hay không. Nếu query không có kế hoạch thực thi hợp lệ, query consistency không giúp nó tìm dữ liệu.

### 21.2. Index key design ảnh hưởng chi phí chờ

Nếu một collection có nhiều index update trên cùng workload ghi, Index Service phải xử lý nhiều thay đổi. Chỉ tạo index phục vụ truy vấn thực, tránh index mọi field “cho chắc”.

Tuy nhiên, xóa index bừa có thể làm query không chạy hoặc chuyển sang index khác chậm hơn. Dùng `EXPLAIN` và benchmark để chọn.

## 22. DCP backlog và failover: khi nào độ mới bị ảnh hưởng mạnh?

Index Service phụ thuộc luồng thay đổi từ Data Service. Một số tình huống có thể làm khoảng cách giữa mutation và index bắt kịp tăng:

1. **Burst write:** đột ngột tạo nhiều document hoặc cập nhật field được index.
2. **Index Service thiếu RAM/CPU/disk:** tốc độ cập nhật index không theo kịp Data Service.
3. **Network giữa Data và Index nodes chậm:** DCP/projector bị ảnh hưởng.
4. **Index build/rebalance:** di chuyển hoặc xây lại chỉ mục có thể làm thời gian phục vụ query thay đổi.
5. **Node failover/rollback:** Index Service có thể cần rollback về snapshot nhất quán hoặc rebuild, phụ thuộc engine/version.
6. **Query workload lớn:** Index Service còn phải phục vụ scans, dễ tranh chấp tài nguyên.
7. **Quá nhiều hoặc index quá rộng:** tăng write amplification ở Index Service.

### 22.1. Chú ý index rollback sau Data node failover

Nếu Data node lỗi và replica được promote, một GSI có thể cần khôi phục trạng thái tương thích với Data Service owner mới. Couchbase có các cơ chế index snapshot/rollback.

Trong một số trạng thái sau failover:

- `NOT_BOUNDED` có thể đọc snapshot index cũ trong thời gian ngắn theo semantics được mô tả.
- `REQUEST_PLUS` đợi một snapshot nhất quán trước khi scan, đổi lại query có thể chậm/hết deadline.

Đó là lý do **độ bền dữ liệu sau failover** và **khả năng truy vấn SQL++ đủ mới ngay sau failover** phải được kiểm thử riêng.

### 22.2. Đừng tăng Data replicas để giải quyết Index node bị nghẽn

Thêm Data replicas có thể giúp bảo vệ mutation trong cluster, nhưng nếu Index Service thiếu capacity, GSI vẫn có thể lag. Cần xử lý Index Service resource/index design/query workload theo đúng bottleneck.

## 23. Thiết kế API tránh phụ thuộc GSI ngay sau ghi

Một ví dụ REST:

~~~text
POST /orders
  - Ghi KV insert với mức durability phù hợp RPO.
  - Trả 201 Created với order ID và thông tin cơ bản.

GET /orders/{id}
  - KV read theo ID (phù hợp trang xác nhận).

GET /orders?status=PAID
  - SQL++ dựa trên GSI.
  - Scan consistency theo SLA của trang danh sách.
~~~

### 23.1. Phản hồi ngay dữ liệu vừa ghi

Ngay sau `POST /orders`, API có thể trả body đã được validate/ghi thành công cùng `orderId`. UI dùng dữ liệu này để hiển thị receipt, không cần đợi một query toàn bộ đơn hàng.

Ưu điểm:

- Tránh round-trip SQL++ chỉ để chứng minh lại cùng record.
- Không ép một trang danh sách lớn chờ Index Service.
- Phân biệt được **đã ghi** và **đã có trong chỉ mục tìm kiếm**.

### 23.2. Khi list phải nhất quán mạnh hơn

Một hệ thống quản trị vừa thay `status` và phải thấy dòng đúng ngay trên danh sách có thể dùng `REQUEST_PLUS` cho query tiếp theo. Chỉ áp dụng ở operation cần thiết; đo latency, timeout và tải Index Service.

### 23.3. CQRS hoặc materialized view không miễn nhất quán

Nếu thiết kế thêm read model/queue riêng cho danh sách, độ mới của read model đó cũng là **bất đồng bộ** trừ khi có protocol mạnh khác. Đừng dùng một kiến trúc CQRS rồi tự hứa rằng read model luôn đồng bộ không có bằng chứng.

## 24. Reactive API: hai loại waiting vẫn khác nhau

Java SDK reactive có các publisher cho KV mutation và SQL++ query.

Ví dụ định hướng:

~~~java
import reactor.core.publisher.Mono;

Mono<?> workflow = orders.reactive()
    .insert(
        orderId,
        orderBody,
        insertOptions().durability(DurabilityLevel.MAJORITY)
    )
    .flatMap(mutation -> cluster.reactive().query(
        sql,
        queryOptions().scanConsistency(
            QueryScanConsistency.REQUEST_PLUS
        )
    ));
~~~

Giả định `orders`, `cluster`, `sql` và query options đã cấu hình. Publisher không đồng nghĩa mutation tự động thực thi nếu không có subscription. Code minh họa sự khác nhau giữa **chờ durable write** và **chờ GSI catch-up**.

### 24.1. Reactive backpressure không làm index tự bắt kịp

Reactive giúp giảm blocking threads và kiểm soát concurrency, nhưng:

- Server vẫn cần thời gian để đáp ứng durability level của một mutation.
- Index Service vẫn cần xử lý DCP để đạt mốc query.
- `Mono.timeout` có thể làm caller ngừng chờ dù DB operation đã commit hoặc query vẫn đang xử lý.
- `retryWhen` trên publisher mutation có thể gửi lại side effect nếu không kiểm soát.

### 24.2. Retry query khác retry mutation

Một `SELECT` read-only timeout có thể được retry theo policy an toàn hơn về side effect, nhưng vẫn có chi phí cluster và tình huống kết quả khác do dữ liệu thay đổi. Một `insert/replace` timeout ambiguous **không** nên retry mù quáng.

Nếu cần retry SQL++ `REQUEST_PLUS` do index chưa sẵn sàng, dùng backoff/jitter và deadline tổng, không tạo bão query chờ Index Service.

## 25. Đo hai SLO khác nhau: write durability và query freshness

Một service có thể đạt p99 ghi rất tốt nhưng người dùng vẫn thấy danh sách cập nhật chậm. Cần ít nhất hai nhóm SLI:

| SLI | Tầng đo | Giải thích |
|---|---|---|
| **KV write p95/p99** | Java SDK/Data Service | Độ trễ tới khi mutation hoàn tất theo durability |
| **Durability error/ambiguous rate** | SDK/application | Tình trạng replica, timeout, kết quả chưa rõ |
| **Query p95/p99 theo scan consistency** | Query Service/application | Chi phí SQL++ scan và chờ index |
| **Index freshness lag** | Index Service/telemetry | Khoảng chậm giữa Data mutation và index catch-up |
| **DCP/indexer backlog** | Data→Index pipeline | Khả năng theo kịp tốc độ ghi |
| **Query timeout/request_plus wait** | Application/Query metrics | Có bị chờ index quá SLA không? |
| **Business read-after-write success** | End-to-end API test | Sau ghi thành công, đúng màn hình có nhìn thấy dữ liệu theo contract không? |

### 25.1. Định nghĩa mốc bắt đầu/kết thúc rõ ràng

Ví dụ:

- `writeLatencyMs`: từ lúc bắt đầu SDK mutation tới khi SDK trả success/exception.
- `indexVisibleLatencyMs`: từ lúc KV mutation được ack tới khi một query theo field phản ánh mutation; đo trong môi trường test với protocol rõ.
- `queryLatencyMs`: thời gian cho SQL++ query theo mode.
- `businessConfirmationLatencyMs`: thời gian người dùng nhận được thông tin đơn hàng đúng.

Không lấy `indexVisibleLatencyMs` từ một `sleep(500 ms)` duy nhất rồi suy ra SLA luôn đạt.

### 25.2. Phân tách dashboard

Để tránh chẩn đoán sai, dashboard nên chia:

1. **Mutation/Data:** durability level, failover, KV errors, CAS conflict, latency.
2. **Index/DCP:** queue/backlog, build/rebalance, CPU/disk, index availability.
3. **Query:** SQL++ p95/p99, mode, timeout, query plans.
4. **Business/API:** HTTP latency, đơn thiếu trên danh sách sau write, reconciliation và duplicate.

Tên metric cụ thể phụ thuộc Couchbase Server/Capella và SDK version. Không tự sáng tạo một metric “index lag” nếu deployment chưa có telemetry đó; cần xác định phương pháp đo và nguồn dữ liệu.

## 26. Runbook khi “ghi thành công nhưng SQL++ không thấy”

Một quy trình thực dụng:

1. **Thu thập bằng chứng ghi:** keyspace, document ID, operation, timestamp, requested durability và response/exception.
2. **Đọc KV theo ID:** xác minh document đã commit và body/`status`/tenant; nếu outcome ambiguous, coi readback chỉ là một bước reconciliation.
3. **So predicate SQL++:** bucket/scope/collection, field type, dấu hoa/thường, `docType`, tenant filter, TTL.
4. **Kiểm tra index:** index nào có thể phục vụ query, trạng thái online, `EXPLAIN` có dùng nó không?
5. **Đối chiếu scan consistency:** query hiện là `NOT_BOUNDED` hay `REQUEST_PLUS`? Nếu thử `REQUEST_PLUS` thì thời gian chờ/thất bại ra sao?
6. **Quan sát Data→Index pipeline:** backlog, health, failover/rebalance, index build, CPU/disk/network.
7. **Phân loại sự cố:** index freshness, query logic/index missing, KV mutation failure, TTL, permission hay bug mapping.
8. **Sửa ở đúng tầng:** chọn KV/get, cải thiện query/index, đặt consistency phù hợp hoặc tăng Index capacity; không tùy tiện đổi write durability.
9. **Thêm test/alert:** ghi nhận scenario và tránh tái phát.

### 26.1. Một bảng quyết định nhanh

| Kết quả KV get | Kết quả SQL++ `NOT_BOUNDED` | Kết quả `REQUEST_PLUS` | Hướng ưu tiên |
|---|---|---|---|
| Thấy body đúng | Chưa thấy row | Thấy row | GSI lag với scan consistency hiện tại |
| Thấy body đúng | Chưa thấy row | Query lỗi thiếu index | Thiết kế/query index, không phải write durability |
| Thấy body đúng | Chưa thấy row | Vẫn chưa thấy nhưng query thành công | Kiểm tra predicate, keyspace, mapping, TTL, query plan |
| Không thấy | Chưa thấy | Chưa thấy | Kiểm tra mutation response, keyspace, pending/expiry, reconciliation |
| Thấy body mới | Row cũ/thiếu | Query chậm hoặc timeout | Index backlog, query timeout, cluster health |

Đây là gợi ý triage chứ không phải thuật toán chứng minh mọi nguyên nhân. Các thay đổi diễn ra đồng thời có thể làm kết quả khác giữa các lần đo.

## 27. Bài lab: quan sát độ mới GSI có kiểm soát

Bài thực hành nên chạy trên **cluster thử nghiệm được phép**, không làm quá tải hoặc chỉnh DCP/failover trên production.

### 27.1. Chuẩn bị

1. Tạo bucket/scope/collection hoặc dùng keyspace thử nghiệm sẵn có.
2. Cấu hình số replica và durability phù hợp, không dùng level persist trên bucket không hỗ trợ.
3. Tạo index cần cho câu SQL++.
4. Đảm bảo Index Service đã build index và ở trạng thái online.
5. Đo thời gian KV insert và SQL++ query riêng.

Ví dụ index:

~~~sql
CREATE INDEX ix_orders_status_test
ON `commerce`.`sales`.`orders`
   (tenantId, status, createdAt)
WHERE docType = "ORDER";
~~~

### 27.2. Thực hiện một chu kỳ ghi–đọc

~~~text
T0: orders.insert(id, body, durability=MAJORITY)
T1: nhận MutationResult thành công, lưu mutation token nếu có
T2: KV get(id)
T3: SQL++ NOT_BOUNDED WHERE tenantId/status
T4: SQL++ REQUEST_PLUS cùng predicate
T5: SQL++ consistentWith(MutationState) nếu có token
T6: ghi latency riêng của T2/T3/T4/T5
~~~

Kết quả có thể là `NOT_BOUNDED` **đã thấy ngay document** nếu Index Service bắt kịp kịp thời. Không coi test “không tái hiện được lag” là bằng chứng GSI cập nhật đồng bộ. Muốn kiểm tra failure mode, cần tạo tải/điều kiện Index backlog trên test cluster có runbook, không thêm sleep giả làm index lag.

### 27.3. Quan sát trạng thái cập nhật

Thử lần lượt:

- `insert` document mới, đọc theo ID và theo index.
- `replace` status từ `NEW` sang `PAID`, so hai danh sách.
- `remove` một document, quan sát phản ánh của index.
- Đặt TTL ngắn trên document test và đánh giá lifecycle.
- Thử Query/Index Service dưới load kiểm soát, đo `REQUEST_PLUS` p99 và timeout.

### 27.4. Điều cần kết luận

- Mutation level cao hơn **không bảo đảm** index freshness.
- `REQUEST_PLUS`/`consistentWith` kiểm soát mốc index, không thay durability.
- KV get phù hợp nhất khi có ID.
- Query latency tăng khi Index Service cần catch-up.
- Khi không đủ replica, lỗi durability là vấn đề đường ghi khác với chậm Index Service.

## 28. Case study A — “Đơn mới biến mất khỏi danh sách”

**Bối cảnh:** `POST /orders` trả `201` sau KV insert `MAJORITY`. `GET /orders/{id}` thấy bản đúng. `GET /orders?status=NEW` qua SQL++ không thấy row ngay.

**Suy luận sai:** dữ liệu vừa ghi đã bị mất vì replica chưa bền.

**Điều tra đúng:**

1. KV theo ID thấy body mới, đó là bằng chứng Data Service đang có document đã commit.
2. Query SQL++ dùng `NOT_BOUNDED` theo GSI có thể chưa bắt kịp.
3. Nếu trang bắt buộc hiển thị row ngay, dùng `REQUEST_PLUS` hoặc `consistentWith` nếu có mutation token và API hỗ trợ.
4. Nếu UI chỉ cần xác nhận vừa tạo đơn, hiển thị receipt từ kết quả `POST` hoặc KV detail.

**Bài học:** UX read-your-own-writes không nên được thiết kế bằng cách tăng độ bền ghi.

## 29. Case study B — bật REQUEST_PLUS làm danh sách chậm

**Bối cảnh:** để chữa missing-row hiếm gặp, nhóm ứng dụng đặt `REQUEST_PLUS` cho **toàn bộ** màn hình lịch sử đơn hàng. Trong giờ cao điểm, Index Service phải cập nhật lượng mutation lớn; query p99 và timeout tăng.

**Cách khắc phục:**

1. Xác định endpoint nào thực sự đòi mốc mới.
2. Giữ `REQUEST_PLUS` cho đường read-after-write quan trọng; dùng `NOT_BOUNDED` ở những báo cáo chấp nhận trễ.
3. Khi chỉ cần thấy mutation của request hiện tại, dùng `consistentWith(MutationState)` nếu giữ được token.
4. Tối ưu Index Service/index design và truy vấn bằng `EXPLAIN`.
5. Đo query wait và độ trễ quan sát thay vì đặt mọi query ở mức mạnh nhất.

**Bài học:** query freshness cũng có đánh đổi giữa latency và tính sẵn sàng phục vụ query.

## 30. Case study C — ghi bền mạnh nhưng SQL++ vẫn sai do predicate

**Bối cảnh:** backend dùng `PERSIST_TO_MAJORITY` cho order và `REQUEST_PLUS` khi liệt kê, nhưng SQL++ vẫn không trả bản ghi.

**Nguyên nhân:** entity được lưu với `tenantId = "42"` (string), query dùng số `42`, hoặc query nhầm collection, hoặc partial index predicate không trùng, hoặc Spring Data generated query có điều kiện discriminator khác.

**Hướng xử lý:**

1. Đọc KV để kiểm tra giá trị chính xác và field types.
2. In/capture generated SQL++ an toàn, không log PII.
3. Chạy `EXPLAIN` kiểm tra keyspace và index plan.
4. Sửa mapping/schema/predicate/index thay vì tăng durability hoặc scan wait.

**Bài học:** scan consistency không thể biến một predicate sai thành đúng.

## 31. Case study D — timeout ambiguous và SQL++ chưa thấy row

**Bối cảnh:** một `insert` `MAJORITY` nhận `AmbiguousTimeoutException`. Developer dùng SQL++ `NOT_BOUNDED` kiểm tra, thấy danh sách trống rồi insert bằng ID khác.

**Rủi ro:** write đầu có thể đã commit, nhưng index chưa thấy; lần hai tạo duplicate. Nếu liên quan payment, có thể dẫn đến double charge.

**Thiết kế lại:**

1. Dùng một ID ổn định cho cùng checkout.
2. Khi ambiguous, đọc KV theo ID và kiểm tra fingerprint.
3. Nếu chưa rõ, retry có điều kiện với ID cũ hoặc chuyển reconciliation.
4. Không phát side effect ngoài khi trạng thái chưa xác minh.
5. Khi cần query SQL++ sau commit có token, chọn consistency đúng nhưng không thay reconciliation.

**Bài học:** độ mới GSI thấp có thể khuếch đại hậu quả retry sai khi kết quả ghi đã ambiguous.

## 32. Bài tập thực hành

### Bài A — hai mốc thời gian

Mô tả đường `Data Service → DCP → Index Service → Query Service`. Vì sao `insert(..., PERSIST_TO_MAJORITY)` success chưa chứng minh `WHERE status='PAID'` thấy row?

### Bài B — ma trận hai trục

Điền bảng 2 × 2 cho mutation `NONE`/`MAJORITY` với query `NOT_BOUNDED`/`REQUEST_PLUS`. Nêu từng cơ chế bảo đảm điều gì và không bảo đảm điều gì.

### Bài C — chọn KV hay SQL++

Sau `POST /orders`, frontend muốn xem chi tiết theo ID. Nên gọi `repository.findById` hay derived query `findByStatus`? Vì sao?

### Bài D — Java SDK options

Viết lệnh `cluster.query(...)` với `QueryScanConsistency.REQUEST_PLUS` và giải thích tác động của `queryTimeout`/`scanWait` khác `kvDurableTimeout`.

### Bài E — MutationState

Sau `MutationResult result = orders.insert(...)`, lấy `mutationToken()`, tạo `MutationState` và truyền `consistentWith`. Cần xử lý thế nào khi token không có?

### Bài F — option loại trừ nhau

Vì sao không nên set đồng thời `scanConsistency(REQUEST_PLUS)` và `consistentWith(state)` trong một Java SDK `QueryOptions`?

### Bài G — Spring Data entity

Khai báo `@Document(durabilityLevel=MAJORITY, queryScanConsistency=NOT_BOUNDED)`. Giải thích hai field này kiểm soát hai đường nào.

### Bài H — repository

Thêm `@ScanConsistency(query=REQUEST_PLUS)` cho method liệt kê order vừa thanh toán. Nêu tại sao annotation không làm `repository.save` ghi bền hơn.

### Bài I — update và delete

Sau `replace(status=PAID)` thành công, `get(id)` thấy PAID nhưng query SQL++ theo status chưa thấy. Sau `remove`, Index Service có thể còn entry tạm. Phân biệt mutation commit và index cleanup.

### Bài J — lỗi index

`REQUEST_PLUS` trả lỗi hoặc timeout liên tục. Nêu kế hoạch kiểm tra: index online, `EXPLAIN`, DCP lag, Index node CPU/disk, query deadline.

### Bài K — ambiguous retry

Một insert có timeout ambiguous, query `NOT_BOUNDED` không thấy order. Có được dùng ID mới để insert không? Hãy viết state machine reconciliation.

### Bài L — performance

Trong workload ghi cao, `REQUEST_PLUS` p99 tăng nhưng KV write p99 ổn. Tại sao tăng Data replicas có thể không giải quyết được? Những metric Index Service nào cần kiểm tra?

### Bài M — transaction

Hai mutation riêng cùng `PERSIST_TO_MAJORITY`, sau đó query `REQUEST_PLUS`. Có đảm bảo atomicity giữa hai record không? Khi nào cần Couchbase Transactions?

### Bài N — designing UX

Thiết kế API receipt sau checkout và API list status với consistency khác nhau sao cho trải nghiệm đúng mà không làm tất cả query phải chờ GSI.

## 33. Checklist triển khai

- [ ] Phân biệt **durability của KV mutation** và **độ mới GSI của SQL++**.
- [ ] Hiểu đường Data Service → DCP → Index Service → Query Service.
- [ ] Không suy ra `PERSIST_TO_MAJORITY` sẽ làm SQL++ `NOT_BOUNDED` thấy row ngay.
- [ ] Không dùng `REQUEST_PLUS` để thay durability hoặc backup/DR.
- [ ] Khi đã biết document ID, ưu tiên KV `get`/`findById` cho read-after-write.
- [ ] Khi query theo field, có GSI phù hợp, online và `EXPLAIN` hợp lý.
- [ ] Chọn `NOT_BOUNDED` cho các trang chấp nhận trễ, `REQUEST_PLUS` cho trang cần mốc query.
- [ ] Khi có token phù hợp, dùng `consistentWith(MutationState)` cho read-your-own-writes.
- [ ] Không chain `consistentWith` với `scanConsistency(REQUEST_PLUS)` trên cùng QueryOptions.
- [ ] Xử lý `mutationToken()` thiếu mà không bịa token.
- [ ] Với Spring Data, tách `@Document.durabilityLevel` và `@Document.queryScanConsistency`.
- [ ] Dùng `@ScanConsistency`/template query option đúng phạm vi, không làm mọi query mạnh lên vô điều kiện.
- [ ] Phân biệt `kvDurableTimeout` với `queryTimeout` và `scanWait`.
- [ ] Khi ambiguous mutation, không dùng SQL++ stale để chứng minh write thất bại.
- [ ] Dùng ID ổn định, fingerprint, CAS/idempotency và reconciliation cho critical writes.
- [ ] Đừng nhầm GSI replica với Data replica.
- [ ] Đo KV write p95/p99 và SQL++ query p95/p99 theo consistency riêng.
- [ ] Theo dõi Index Service backlog, DCP, index build/rebalance, failover/rollback.
- [ ] Kiểm tra TTL, schema, RBAC, keyspace và query predicate trước khi đổ lỗi lag.
- [ ] Có integration/failure tests trên môi trường được phép, không hard-failover production để học.
- [ ] Có backup/DR và business workflow ngoài phạm vi độ mới chỉ mục.

## 34. Tổng kết

**Ghi bền và chỉ mục đủ mới là hai bảo đảm khác nhau.** Couchbase Data Service xử lý KV mutation và trả success theo `DurabilityLevel` khi các điều kiện active/replica/persistence hiệu lực đạt được. Index Service tiếp nhận thay đổi qua DCP để cập nhật GSI bất đồng bộ; vì vậy một SQL++ query `NOT_BOUNDED` có thể chưa phản ánh mutation đã commit, kể cả khi mutation dùng `PERSIST_TO_MAJORITY`.

Khi đã biết ID, dùng **KV get/repository `findById`** cho read-after-write. Khi cần SQL++ theo field, chọn `REQUEST_PLUS` để chờ index theo mốc query hoặc `consistentWith(MutationState)` để chờ những mutation tokens đã biết. Chúng giúp **độ mới của query**, không nâng mức replication/persistence của ghi.

Trong **Spring Data Couchbase**, `@Document(durabilityLevel = ...)` và `@ScanConsistency` hoặc `queryScanConsistency` giải quyết **hai đường code khác nhau**. Thiết kế đúng cần xem cả durability, GSI index design, query SLO, timeout, CAS, idempotency, transaction và khả năng phục hồi. Nếu mutation timeout ambiguous, không dùng sự vắng mặt tạm thời của SQL++ row để tạo đơn mới; phải dùng ID ổn định và đối soát.

## Tài liệu tham khảo chính thức

1. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): Sync Writes, majority/persistence và kết quả ghi.
2. [Couchbase Server — Index Lifecycle](https://docs.couchbase.com/server/current/indexes/index-lifecycle.html): DCP/projector, cập nhật GSI bất đồng bộ và index scans.
3. [Couchbase Server — Index Availability and Performance](https://docs.couchbase.com/server/current/indexes/index-replication.html): `not_bounded`, `request_plus`, `at_plus` và index rollback sau failover.
4. [Couchbase Java SDK — SQL++ Query](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryOptions`, scan consistency, `consistentWith` và `scanWait`.
5. [Couchbase Java SDK — QueryOptions API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryOptions.html): loại trừ nhau giữa `scanConsistency` và `consistentWith`.
6. [Couchbase Java SDK — MutationState API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/MutationState.html): tập hợp `MutationToken`.
7. [Spring Data Couchbase — @Document API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/mapping/Document.html): `durabilityLevel` và `queryScanConsistency`.
8. [Spring Data Couchbase — @ScanConsistency API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/repository/ScanConsistency.html): query scan consistency của repository.
9. [Spring Data Couchbase — Fluent FindByQueryWithConsistency API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/ExecutableFindByQueryOperation.FindByQueryWithConsistency.html): `withConsistency` cho query template.

Các ví dụ dựa trên API/tài liệu hiện hành; trước khi áp dụng cần đối chiếu phiên bản **Spring Data Couchbase, Couchbase Java SDK, Couchbase Server/Capella và bucket/index topology** của dự án. Bài học là kiến thức để triển khai và kiểm thử; không thay thế Content QA chuyên môn hoặc performance testing.


