# Chỉ mục cập nhật bất đồng bộ và độ mới của kết quả truy vấn trong Couchbase

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate` và SQL++; vận dụng kiến thức về bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để cân bằng hiệu năng với yêu cầu nhất quán.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Giải thích vì sao **ghi document thành công qua KV** không luôn đồng nghĩa với **SQL++ lập tức tìm thấy thay đổi qua Global Secondary Index (GSI)**.
2. Mô tả đường đi từ Data Service tới Index Service và vai trò của Query Service, vBucket, mutation stream và index scan.
3. Phân biệt ba cách đặt độ mới của truy vấn: **`not_bounded`**, **`request_plus`** và **`at_plus` / `consistentWith`**.
4. Dùng **MutationResult/MutationState** của Couchbase Java SDK để thiết kế read-your-own-writes khi truy vấn theo thuộc tính.
5. Chọn **KV read** thay vì SQL++ khi đã biết document ID, tránh chi phí và độ trễ index không cần thiết.
6. Phân tích mối quan hệ giữa độ mới, chi phí chờ index, thiết kế GSI, covering index, durability, CAS và transaction.
7. Áp dụng vào **Spring Data Couchbase** (repository/template hoặc reactive) và tổ chức kiểm thử, logging, giám sát nhất quán dữ liệu.

## 2. Tình huống mở đầu: ghi thành công nhưng trang danh sách chưa thấy

Một ứng dụng bán hàng dùng collection `commerce.sales.orders`. API ghi đơn mới:

~~~json
{
  "tenantId": "tenant-42",
  "status": "PAID",
  "createdAt": "2026-11-25T02:10:00Z",
  "total": 1490000
}
~~~

Document ID là `order::1001`. Sau khi lệnh `insert` hoặc `save` trả thành công, trang “Đơn đã thanh toán” gọi truy vấn:

~~~sql
SELECT META(o).id AS orderId, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-42"
  AND o.status = "PAID";
~~~

Đôi khi đơn vừa tạo **chưa xuất hiện trong kết quả truy vấn** ngay lập tức, nhưng `get("order::1001")` vẫn đọc được document. Đó có thể là hành vi bình thường của hệ thống dùng **chỉ mục cập nhật bất đồng bộ**.

Cần phân biệt:

- **KV write acknowledgement:** mutation tới Data Service được xác nhận theo semantics thao tác và mức durability được yêu cầu.
- **Index maintenance:** Index Service theo dõi luồng thay đổi và cập nhật GSI riêng.
- **SQL++ query:** Query Service có thể scan chỉ mục chưa bắt kịp mutation vừa ghi, tùy scan consistency.
- **Lỗi thực sự:** sai keyspace, quyền, điều kiện lọc, thiếu index hoặc lỗi mapping cũng có thể làm document không xuất hiện. Không quy mọi kết quả thiếu cho index lag.

Bài học này tập trung vào **độ mới của kết quả truy vấn SQL++ sử dụng GSI**; không đánh đồng nó với thời gian document tồn tại, mức bền vững của ghi hay tính nguyên tử của transaction.

## 3. Kiến trúc dữ liệu, truy vấn và chỉ mục

Couchbase phân tách chức năng qua các service:

| Service | Nhiệm vụ | Ảnh hưởng tới bài toán |
|---|---|---|
| **Data Service** | Quản lý document và thao tác KV theo ID | Nhận `get`, `insert`, `upsert`, `replace`, `remove` |
| **Query Service** | Phân tích và thực thi SQL++, chọn execution plan | Điều phối index scan, filter, fetch, sort, join |
| **Index Service** | Duy trì/phục vụ GSI | Cung cấp đường tìm document theo trường JSON, có thể cập nhật trễ so với KV |

Một đường đi tổng quát:

~~~mermaid
flowchart LR
    A["Spring Data / Couchbase Java SDK"]
    D["Data Service<br/>Document + active vBucket"]
    S["Luồng mutation / DCP"]
    I["Index Service<br/>GSI"]
    Q["Query Service<br/>SQL++"]
    A -->|"Insert/replace theo ID"| D
    D -->|"Ghi được chấp nhận"| A
    D -->|"Thay đổi dữ liệu"| S
    S -->|"Cập nhật index bất đồng bộ"| I
    A -->|"Truy vấn theo field"| Q
    Q -->|"IndexScan"| I
    I -->|"Khóa/index entries"| Q
    Q -->|"Fetch document khi cần"| D
    Q -->|"Kết quả truy vấn"| A
~~~

Couchbase phân phối document trong bucket bằng **vBucket**, sau đó Data Service quản lý active/replica vBucket trên nhiều node. Index Service nhận thông tin thay đổi qua cơ chế truyền mutation (thường nhắc đến **Database Change Protocol – DCP**) và cập nhật GSI. Query Service không cần chờ Index Service hoàn tất mọi mutation mới cho phép Data Service phản hồi thao tác KV.

Điều này có ưu điểm: ghi KV không bị buộc phải đồng bộ mọi chỉ mục thứ cấp trước khi trả kết quả, giúp tách việc cập nhật document khỏi tải truy vấn. Đổi lại, ứng dụng phải **chọn mức độ mới phù hợp** khi đọc qua SQL++.

**Ghi chú phạm vi:** Search Index, Analytics hoặc các dịch vụ tìm kiếm khác có các semantics và API riêng. Những khái niệm scan consistency cụ thể trong bài áp dụng cho đường **SQL++ + GSI**, không mặc định áp dụng nguyên xi sang Full Text Search.

## 4. GSI chứa gì và vì sao index có thể trễ?

**Global Secondary Index** giúp SQL++ tìm document dựa trên biểu thức/trường thay vì ID. Ví dụ:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId,
    status,
    createdAt DESC
);
~~~

Khi tạo đơn mới, Data Service lưu document tại phân vùng phù hợp. Index Service cần tiếp nhận thay đổi, xác định entry index liên quan và cập nhật cấu trúc chỉ mục. Công việc đó diễn ra **bất đồng bộ** so với xác nhận thao tác KV.

GSI có thể ở một trạng thái **chưa bắt kịp** do:

- Lượng mutation lớn trong thời gian ngắn.
- Index node bận CPU, RAM, đĩa hoặc network.
- Index đang build/rebuild, rebalance hoặc sau sự cố.
- Câu truy vấn dùng nhiều index, phân vùng hoặc index replica có tiến độ khác nhau.
- Một vấn đề vận hành gây backlog hoặc thiếu capacity.

Không có một hằng số độ trễ index áp dụng cho mọi workload. Có lúc index gần như bắt kịp ngay; lúc tải cao, thời gian chờ có thể đáng kể.

### 4.1. Chỉ mục có thể thiếu entry, hoặc phản ánh trạng thái cũ

Giả sử document được thay:

~~~text
T0: order::1001.status = NEW
T1: KV replace → status = PAID, trả thành công
T2: Index Service chưa xử lý thay đổi T1
T3: Index Service cập nhật entry NEW → PAID
~~~

Một câu SQL++ lọc `status = "PAID"` ở T2 có thể **chưa tìm được** đơn vì entry index tương ứng chưa cập nhật. Truy vấn dựa vào thông tin index cũ cũng có thể gặp sai khác giữa entry đã scan và body hiện tại; kết quả cụ thể phụ thuộc execution plan, việc Fetch/filter lại và cấu hình truy vấn.

**Không hứa chắc rằng SQL++ luôn trả về “bản JSON cũ”.** Stale index chủ yếu tạo rủi ro **độ mới của tập kết quả và lựa chọn document**; body có thể được Fetch từ Data Service tại thời điểm khác. Muốn biết hành vi của truy vấn cụ thể, phải xem `EXPLAIN` và thử với dữ liệu thực.

### 4.2. Covering index không tự bảo đảm dữ liệu mới

**Covering index** chứa đủ dữ liệu cần trả về để một query plan có thể không cần Fetch body từ Data Service. Nó có thể giúp tốc độ truy vấn, nhưng **không loại bỏ index lag**.

Một index bao phủ tốt chỉ giúp giảm chi phí đọc, không biến GSI thành cập nhật đồng bộ với mutation. Hai tiêu chí cần đánh giá độc lập:

- **Hiệu năng của plan:** số entry scan, Fetch, sort, network, CPU.
- **Độ mới của plan:** Query Service có đợi index đạt mốc cần thiết trước khi scan hay không.

## 5. Dòng thời gian read-after-write

Ví dụ ứng dụng cập nhật `order::1001` từ `NEW` sang `PAID`:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant D as Data Service
    participant I as Index Service
    participant Q as Query Service
    App->>D: KV replace(status=PAID)
    D-->>App: Mutation success + CAS + mutation token (nếu có)
    D-->>I: Luồng mutation bất đồng bộ
    App->>Q: SQL++ WHERE status=PAID
    Q->>I: IndexScan
    I-->>Q: Có thể chưa chứa thay đổi vừa ghi
    Q-->>App: Kết quả theo scan consistency
    Note over I: Index xử lý xong mutation
    App->>Q: SQL++ với yêu cầu consistency phù hợp
    Q->>I: Chờ index bắt kịp mốc cần thiết
    I-->>Q: Index ở trạng thái phù hợp
    Q-->>App: Kết quả đáp ứng yêu cầu độ mới
~~~

Chú ý: sơ đồ tách thời điểm một mutation **được xác nhận qua KV** và thời điểm **GSI theo kịp**. Cùng một ứng dụng có thể quan sát:

| Hành động | Kết quả dự kiến |
|---|---|
| `collection.get("order::1001")` sau ghi thành công | Đọc theo khóa qua Data Service, tránh scan GSI |
| SQL++ mặc định lọc `status = "PAID"` | Có thể chưa thấy thay đổi ngay |
| SQL++ với consistency chờ index phù hợp | Đợi GSI đạt mốc trước khi scan; có thể tăng latency |
| SQL++ sai keyspace hoặc sai điều kiện `tenantId` | Vẫn thiếu document dù index mới nhất |
| SQL++ không có index hợp lệ | Có thể lỗi lập kế hoạch hoặc phải dùng kế hoạch khác; consistency không tự tạo index |

Vì vậy **thấy not-found trong query không đủ để kết luận mutation đã thất bại**. Kiểm tra KV theo ID và thông tin lỗi sẽ giúp khoanh vùng.

## 6. Các lựa chọn scan consistency của SQL++

Scan consistency là yêu cầu về **độ mới của index ở thời điểm truy vấn**. Nó độc lập với transaction isolation và durability của KV mutation.

| Lựa chọn | Ý nghĩa | Khi dùng | Chi phí/rủi ro |
|---|---|---|---|
| **`not_bounded`** | Không yêu cầu GSI chờ một mốc cập nhật cụ thể trước khi scan | Danh sách/báo cáo chấp nhận thay đổi xuất hiện chậm | Kết quả có thể chưa phản ánh mutation vừa được xác nhận |
| **`request_plus`** | Chờ index theo kịp các mutation có trước mốc yêu cầu truy vấn theo semantics server | Cần trạng thái index mới ở thời điểm request, không có token riêng | Có thể tăng thời gian chờ và timeout khi backlog |
| **`at_plus` / `consistentWith`** | Chờ index đạt ít nhất các mutation token được cung cấp | Read-your-own-writes sau một hoặc nhiều mutation có token | Phải thu thập/chuyển mutation state hợp lệ |

Các mức trên nói về **mốc index phải đạt**, không tự tạo một snapshot giao dịch nhiều document hoặc một lịch sử tuyến tính cho mọi phép đọc.

### 6.1. `not_bounded`: phản hồi nhanh, chấp nhận độ mới chưa tuyệt đối

Trong các luồng phù hợp, query có thể dùng index sẵn có mà không chờ backlog mới nhất. Ví dụ dashboard doanh thu chấp nhận độ trễ cập nhật ngắn theo SLA riêng.

Ưu điểm: tránh chi phí chờ index cho những query không cần tức thời. Nhược điểm: người dùng có thể cần làm mới danh sách hoặc thấy dữ liệu chậm hơn một thao tác KV ngay trước đó.

**Không nên mô tả `not_bounded` là “truy vấn trả dữ liệu sai”.** Đây là đánh đổi nhất quán được cung cấp rõ ràng; lựa chọn phù hợp tùy kỳ vọng nghiệp vụ.

### 6.2. `request_plus`: chờ cập nhật đã có trước query

Khi chọn `request_plus`, Query Service yêu cầu index bắt kịp thay đổi đã xảy ra trước thời điểm bắt đầu truy vấn theo semantics của Couchbase. Điều này thường phù hợp cho query phải thấy mutation hoàn thành trước request.

Đổi lại, truy vấn có thể chờ lâu nếu Index Service có backlog hoặc node đang căng tải. Khi write rate cao, `request_plus` có thể chờ cả thay đổi **ngoài** thao tác nghiệp vụ hiện tại.

Không bật mức này trên mọi endpoint chỉ vì “an toàn hơn”. Cần cân nhắc **latency SLO, số query đồng thời và mức độ mới thực sự cần**.

### 6.3. `at_plus` / `consistentWith`: chờ thay đổi đã biết

Nếu sau mutation KV, SDK cung cấp **mutation token**, ta có thể chuyển token này vào một `MutationState` để yêu cầu index theo kịp chính các thay đổi cần quan sát.

Phạm vi sử dụng điển hình:

~~~text
Ghi đơn A → mutation token A
Ghi đơn B → mutation token B
Tạo MutationState từ các token hợp lệ
SQL++ consistentWith(MutationState)
→ Index phải đạt mốc A và B trước khi thực thi phần scan liên quan
~~~

Cơ chế này thường tối ưu mục tiêu **read-your-own-writes** hơn yêu cầu chờ tất cả mutation trước thời điểm query. Tuy nhiên, nó cần dữ liệu mutation được SDK hỗ trợ và không giải quyết tính nguyên tử nhiều document.

## 7. Mutation token và MutationState

**Mutation token** là thông tin theo phân vùng do SDK/server cung cấp cho một số thao tác mutation. Về mặt khái niệm, token liên quan đến:

- ID của partition/vBucket.
- UUID/generation nhận diện lịch sử của vBucket.
- Sequence number mô tả tiến trình của luồng thay đổi.

Token được thiết kế cho mục đích quan sát thứ tự/tiến độ mutation ở mức phân vùng. **Nó khác CAS**:

| Thuộc tính | CAS | Mutation token |
|---|---|---|
| Dùng để | Kiểm tra một document còn đúng phiên bản đã đọc | Xác định mốc mutation cần index đạt |
| Phạm vi | Phiên bản document | Luồng thay đổi của một vBucket |
| Kết quả phổ biến | `GetResult.cas()`, `MutationResult.cas()` | Mutation result/token từ API hỗ trợ |
| Có thể dùng làm ID nghiệp vụ? | Không | Không |
| Bảo đảm transaction nhiều document? | Không | Không |

Cũng không được so sánh số thứ tự token của hai vBucket khác nhau như một đồng hồ toàn cục hoặc tự ghép token bằng chuỗi rồi đưa vào SQL++.

### 7.1. Java SDK: ghi và dùng MutationState

Mẫu Java SDK 3.x minh họa:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.Collection;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryResult;

// cluster và orders là các đối tượng đã được cấu hình đúng bucket/scope.
MutationResult write = orders.upsert(
    "order::1001",
    JsonObject.create()
        .put("tenantId", "tenant-42")
        .put("status", "PAID")
        .put("createdAt", "2026-11-25T02:10:00Z")
        .put("total", 1490000)
);

QueryResult result = cluster.query(
    "SELECT META(o).id AS id, o.status, o.total " +
    "FROM `commerce`.`sales`.`orders` AS o " +
    "WHERE o.tenantId = $tenantId AND o.status = $status",
    queryOptions()
        .parameters(JsonObject.create()
            .put("tenantId", "tenant-42")
            .put("status", "PAID"))
        .consistentWith(MutationState.from(write))
);

System.out.println(result.rowsAsObject());
~~~

Đoạn trên giả định bucket/collection đã có, quyền truy cập phù hợp, index phục vụ query đã sẵn sàng và mutation result chứa thông tin cần thiết theo cấu hình SDK/server. **Đối chiếu phương thức và package theo phiên bản Couchbase Java SDK đang dùng.**

Một request chỉ ghi một document rồi trả đúng document đó cho client có thể **không cần SQL++ lần hai**: lấy dữ liệu từ kết quả nghiệp vụ hoặc dùng KV theo ID là đủ.

### 7.2. Gom nhiều mutation state

Nếu workflow ghi nhiều document ở các vBucket khác nhau, cần đưa các mốc mutation phù hợp vào `MutationState` theo API SDK. Đừng xem token của một document là đủ đại diện cho mọi document khác.

Không có gì trong `MutationState` khiến hai mutation trở thành một transaction. Nếu ghi A thành công còn ghi B thất bại, chờ index không tự rollback A.

### 7.3. Nếu không có token từ Spring Data repository?

`repository.save(entity)` thường trả về entity, không trực tiếp phơi bày `MutationResult` của SDK. Vì thế ứng dụng có thể không lấy được token từ API repository đang dùng.

Các lựa chọn:

1. Nếu đã biết ID và cần đọc đúng document, dùng `findById`/KV.
2. Nếu query cần thấy những mutation trước lúc query bắt đầu, cân nhắc `request_plus` qua API/cấu hình được phiên bản Spring Data hỗ trợ.
3. Khi cần truyền mốc mutation chính xác, dùng API SDK hoặc template hỗ trợ trả metadata/mutation result và xây dựng luồng dữ liệu rõ ràng.
4. Không tạo token giả từ CAS, timestamp hoặc document ID.

## 8. Java SDK: cấu hình request_plus và not_bounded

Khi cần Query Service chờ index, Java SDK cung cấp query option tương ứng.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.query.QueryScanConsistency;
import com.couchbase.client.java.json.JsonObject;

var rows = cluster.query(
    "SELECT META(o).id AS id, o.status " +
    "FROM `commerce`.`sales`.`orders` AS o " +
    "WHERE o.tenantId = $tenantId",
    queryOptions()
        .parameters(JsonObject.create().put("tenantId", "tenant-42"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
).rowsAsObject();
~~~

Nếu query không cần chờ mutation mới nhất, có thể sử dụng chế độ mặc định hoặc đặt rõ khi API hỗ trợ:

~~~java
var rows = cluster.query(
    "SELECT META(o).id AS id FROM `commerce`.`sales`.`orders` AS o",
    queryOptions()
        .scanConsistency(QueryScanConsistency.NOT_BOUNDED)
).rowsAsObject();
~~~

Không nên cộng `sleep(100)` vào logic nghiệp vụ rồi hy vọng “index chắc đã cập nhật”. Độ trễ index biến động theo tải và topology; việc chờ một khoảng cố định vừa không tạo bảo đảm vừa làm mất thời gian trên các lần query vốn đã sẵn sàng.

### 8.1. Query timeout cần tính cả thời gian chờ index

Khi bật `request_plus` hoặc `consistentWith`, tổng thời gian query bao gồm **thời gian chờ index bắt kịp** và chi phí thực thi. Một query trước đây nhanh có thể timeout nếu Index Service backlog lớn.

Nên:

- Chọn timeout/deadline theo SLO thực tế, không kéo dài vô hạn.
- Đo query execution latency và index lag; tách lỗi timeout do chờ consistency khỏi query scan nặng khi có telemetry.
- Giới hạn concurrency ở các API có nhiều request_plus khi tải ghi lớn.
- Cân nhắc đường KV hoặc trả ngay kết quả từ mutation cho những trường hợp chỉ cần xác nhận một document.

## 9. KV get, SQL++ USE KEYS và SQL++ lọc theo thuộc tính

### 9.1. Đã biết ID: ưu tiên KV

~~~java
var result = orders.get("order::1001");
var body = result.contentAsObject();
~~~

KV đi thẳng đến Data Service qua document ID và active vBucket. GSI không nằm trong đường đọc này, nên **index lag không khiến KV get theo ID bỏ sót document chỉ vì chưa cập nhật GSI**.

Tuy nhiên, KV get vẫn có thể chịu tác động từ lỗi mạng, timeout, expiry, failover, durability và việc chọn API đọc replica. Không gọi toàn bộ KV read là “mạnh hơn SQL++ trong mọi nghĩa”.

### 9.2. SQL++ USE KEYS

Nếu có lý do dùng SQL++ mà đã biết key, có thể dùng `USE KEYS`:

~~~sql
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
USE KEYS "order::1001";
~~~

Đây là đường truy cập khóa qua SQL++, thường tránh cần GSI cho việc xác định ID. Dù vậy nó vẫn có chi phí Query Service và không phải lựa chọn mặc định đơn giản hơn `collection.get(id)` cho một document.

### 9.3. Tìm nhiều document theo field: GSI

~~~sql
SELECT META(o).id AS id, o.tenantId, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID";
~~~

Truy vấn tìm theo trường thường cần GSI phù hợp, nên **scan consistency** trở thành một quyết định thiết kế. Với phương thức repository `findByTenantIdAndStatus`, cần kiểm tra câu SQL++ sinh ra và index được sử dụng.

## 10. Thiết kế chỉ mục để truy vấn đúng và nhanh

Index lag và index design là hai vấn đề độc lập nhưng ảnh hưởng nhau khi hệ thống chịu tải.

Giả sử yêu cầu nghiệp vụ: tìm 20 đơn PAID mới nhất của một tenant.

~~~sql
SELECT META(o).id AS id, o.status, o.createdAt, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một index bắt đầu để đánh giá:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId,
    status,
    createdAt DESC
);
~~~

Cách lựa chọn:

1. `tenantId` và `status` là điều kiện bằng, thu hẹp tập ứng viên.
2. `createdAt DESC` liên quan đến thứ tự trả về và có thể giúp tránh một bước sort tùy query plan.
3. `total` chưa được index bao phủ trong ví dụ, nên Query Service có thể cần `Fetch` từ Data Service.
4. Tạo nhiều GSI không cần thiết làm tăng tài nguyên và chi phí duy trì index sau mutation.

Kiểm tra kế hoạch thực thi:

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.createdAt, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Khi đọc `EXPLAIN`, tìm index được chọn, IndexScan, Fetch, Filter và Sort/Order. Đây là thông tin **kế hoạch**, không tự chứng minh index mới tới đâu hoặc query đạt latency SLO.

### 10.1. Primary index không giải quyết nhất quán

Tạo primary index để mọi query “có index” có thể khiến hệ thống chậm vì quét phạm vi rộng. Primary index cũng được Index Service duy trì; nó **không biến truy vấn thành luôn mới nhất**.

Khi thiếu index đúng, cần thiết kế GSI theo query thực tế, không bổ sung primary index như giải pháp cho hiện tượng ghi rồi đọc chưa thấy.

### 10.2. Partial index và điều kiện do Spring Data tạo

Nếu collection chứa nhiều loại entity và muốn index chỉ đơn hàng, có thể cân nhắc partial index:

~~~sql
CREATE INDEX ix_paid_orders_tenant_created
ON `commerce`.`sales`.`orders`(tenantId, createdAt DESC)
WHERE status = "PAID";
~~~

Đây chỉ là ví dụ, hiệu quả phụ thuộc workload và **truy vấn phải có điều kiện đủ để optimizer dùng partial index**. Nếu ứng dụng đọc nhiều trạng thái, index lọc chỉ `PAID` không phục vụ mọi query khác.

Spring Data Couchbase có thể thêm điều kiện phân biệt kiểu entity (ví dụ `_class`) vào SQL++ từ repository. Vì vậy, index từ SQL++ viết tay **không chắc** phù hợp với derived query thực tế. Cần log/tracing SQL++ được sinh và kiểm tra `EXPLAIN`.

### 10.3. Số index càng nhiều thì cập nhật càng tốn

Một mutation thay đổi `tenantId`, `status` hoặc `createdAt` có thể tác động đến nhiều chỉ mục. Index Service phải duy trì chúng khi nhận luồng mutation.

Do đó:

- Không tạo index dư chỉ vì thấy một query chậm.
- Xem workload đọc/ghi, mức cardinality, dung lượng index và tốc độ mutation.
- Theo dõi backlog trong giờ cao điểm và sau rebalance.
- Cân nhắc covering index khi giảm Fetch đáng giá chi phí cập nhật lớn hơn.
- Định kỳ đánh giá index ít được sử dụng theo cơ chế quan sát của môi trường.

Không kết luận có thêm index thì **chắc chắn** index lag tăng theo một tỷ lệ cố định; ảnh hưởng phụ thuộc thiết kế chỉ mục, tài nguyên và loại mutation.

## 11. Index lifecycle: BUILDING, ONLINE và các tình huống chưa sẵn sàng

Một index vừa được tạo có thể cần **build** trước khi đủ điều kiện được Query Service sử dụng. Trong môi trường có thao tác tạo index với chế độ trì hoãn build, cần chủ động khởi tạo và theo dõi trạng thái xây dựng theo API/version.

Cần phân biệt:

| Trạng thái/tình huống | Ý nghĩa đối với query |
|---|---|
| **Index đang build** | Chưa chắc sẵn sàng được dùng cho mọi plan; không chỉ là “độ trễ vài mili giây” |
| **Index ONLINE và có backlog** | Index có thể được scan nhưng chưa bắt kịp mutation; scan consistency quyết định mức chờ |
| **Index bị lỗi/không khả dụng** | Query có thể fail hoặc không tìm được plan phù hợp |
| **Index replica chưa có hoặc unavailable** | Đường SQL++ có rủi ro khi mất Index node; data replica không thay thế index replica |

Truy vấn ở `request_plus` không thể tự sửa một chỉ mục bị cấu hình sai, thiếu keyspace hoặc chưa hoạt động. Kiểm tra tình trạng index và khả năng truy cập trước khi tăng timeout.

### 11.1. Rebalance, failover và index replica

Index Service có thể được triển khai trên các node khác Data Service. Khi Index node lỗi hoặc cluster rebalance, tốc độ cập nhật/chỉ mục khả dụng có thể thay đổi. **Index replica** giúp tăng khả năng phục vụ nếu cấu hình đúng và còn tài nguyên.

Cần theo dõi riêng:

- Data replica/active vBucket để đánh giá khả năng chịu lỗi dữ liệu.
- Query node để bảo đảm có endpoint SQL++.
- Index node và bản sao GSI để truy vấn vẫn có đường scan.
- Backlog/tiến độ cập nhật GSI để biết request_plus có đang phải chờ lâu.

Không nhầm **index replica** với một công tắc làm kết quả tự động “mới hơn”; bản sao chỉ mục chủ yếu giúp HA và capacity theo cấu hình.

## 12. Spring Data Couchbase: repository và độ mới của query

### 12.1. Document mapping

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

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
    private String createdAt;
    private Long total;

    // Constructor/getter/setter được lược bớt.
}
~~~

- `@Id` ánh xạ document ID và dùng cho thao tác KV theo khóa.
- `@Scope`/`@Collection` xác định keyspace đúng phiên bản Spring Data hỗ trợ.
- `@Version` thường gắn CAS, giúp kiểm soát ghi đè cạnh tranh **trên một document**; không buộc GSI cập nhật ngay.

### 12.2. Repository method và đường thực thi

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Mẫu sử dụng:

~~~java
OrderDocument stored = orderRepository.save(order);

// Nếu có ID và chỉ cần kiểm chứng đơn đó:
OrderDocument justSaved = orderRepository.findById(stored.getId())
        .orElseThrow();

// Nếu cần danh sách lọc theo tenant và status:
List<OrderDocument> paidOrders =
        orderRepository.findByTenantIdAndStatus("tenant-42", "PAID");
~~~

**Điểm mấu chốt:** `findById` thường dùng KV, còn `findByTenantIdAndStatus` thường là SQL++ và GSI. `save` trả thành công không mặc nhiên chứng minh một derived query ngay sau đó sẽ thấy document ở chế độ scan consistency không chờ index.

### 12.3. Làm thế nào yêu cầu consistency trong Spring Data?

API/cách cấu hình scan consistency có thể thay đổi theo Spring Data Couchbase, Spring Boot và Couchbase Java SDK đang dùng. Cách tiếp cận cần giữ nguyên nguyên tắc:

1. Xác định query chạy qua repository, `CouchbaseTemplate` hay SDK.
2. Kiểm tra API version cụ thể có hỗ trợ đặt scan consistency theo query, annotation, template hoặc cấu hình chung hay không.
3. Chọn mức độ mới theo **use case**, tránh vô tình bật mức chờ cao trên mọi query.
4. Nếu cần `MutationState`, xem đường API nào thực sự cung cấp `MutationResult` để chuyển token.
5. Kiểm tra SQL++ và `EXPLAIN` được thực thi trong môi trường, bao gồm field `_class` nếu có.

Không nên đưa một annotation hoặc phương thức Spring Data chưa đối chiếu phiên bản vào mọi project. Ví dụ Java SDK phía trên cho thấy rõ cơ chế ở tầng Couchbase; ở tầng framework cần ánh xạ sang API tương ứng.

### 12.4. CouchbaseTemplate không xóa bài toán index lag

`CouchbaseTemplate` cung cấp thao tác entity ở mức thấp hơn và truy vấn tùy chỉnh. Nếu template dùng KV theo ID, nó không scan GSI. Nếu template chạy SQL++ theo field, nó vẫn chịu quy tắc cập nhật index và scan consistency như Query Service.

Chuyển từ repository sang template **không tự làm index cập nhật nhanh hơn**; chỉ có thể giúp kiểm soát query/options hoặc cách đọc/ghi rõ hơn.

## 13. SQL++ freshness và CAS, TTL, durability, transaction

### 13.1. CAS giải quyết vấn đề khác

**CAS** dùng để phát hiện phiên bản document đã đổi khi cập nhật dựa trên bản đọc trước. Nó bảo vệ khỏi lost update, không yêu cầu Index Service hoàn tất mutation.

Ví dụ hai request cập nhật cùng đơn:

~~~text
A đọc CAS V1
B đọc CAS V1
A replace với CAS V1 → thành công, CAS V2
B replace với CAS V1 → conflict
~~~

Đây là đúng semantics optimistic locking nhưng một query SQL++ ở `not_bounded` vẫn có thể chưa nhìn thấy thay đổi của A.

### 13.2. TTL/expiry tác động tới kết quả

Một document có expiry metadata sẽ bị xem là hết hạn sau thời gian hiệu lực. Khi document hết hạn, các thao tác KV thông thường không còn xem nó là đang tồn tại. Đường truy vấn SQL++ và GSI liên quan có thể chịu thời gian dọn/cập nhật dữ liệu.

Không dùng số lượng entry trong index như đồng hồ chính xác cho việc xóa vật lý. Nếu nghiệp vụ cần phát sự kiện vào một thời điểm chính xác, dùng cơ chế scheduler/event phù hợp; TTL riêng không tạo bảo đảm có một callback đúng giờ.

### 13.3. Durability nói về mức ghi được xác nhận

Synchronous durability khi được hỗ trợ có thể yêu cầu mutation đạt điều kiện xác nhận/replication/persistence như `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` hoặc `PERSIST_TO_MAJORITY`.

**Mutation đạt durability yêu cầu không tự đồng nghĩa GSI đã bắt kịp.** Durability bảo vệ trạng thái ghi theo cơ chế Data Service; scan consistency bảo vệ mốc index phục vụ truy vấn.

### 13.4. Transaction và truy vấn

Nếu cần atomicity nhiều document, dùng API **Couchbase Transactions** khi điều kiện triển khai phù hợp. Query trong transaction và thao tác bên ngoài transaction có semantics riêng; không dùng `request_plus` như một phương án thay thế transaction isolation.

MutationState có thể khiến SQL++ chờ các mutation đã biết, nhưng **không bảo đảm** hai mutation được ghi nguyên tử. Nếu ghi đơn thành công còn ghi thanh toán thất bại, chờ index không khôi phục tính đúng đắn nghiệp vụ.

## 14. Chọn consistency cho từng loại API

Một ứng dụng nên thiết kế từ **hợp đồng dữ liệu với người dùng**, không chọn một mức consistency chung cho mọi tính năng.

| Use case | Yêu cầu độ mới | Hướng triển khai |
|---|---|---|
| Trang xác nhận vừa tạo một đơn | Phải xác nhận đúng document vừa ghi | Trả kết quả từ write hoặc đọc KV theo ID |
| Danh sách đơn ngay sau thanh toán | Phải thấy đơn vừa sửa trong tập lọc | `consistentWith` khi có token; hoặc `request_plus` |
| Dashboard doanh thu cập nhật theo nhịp | Cho phép chậm vài giây theo SLA | `not_bounded` và UI thông báo độ trễ dữ liệu nếu cần |
| Kiểm tra tồn tại document theo ID | Cần đúng khóa, không cần query theo field | KV get |
| Báo cáo cần mốc cập nhật toàn cục tại thời điểm request | Cần index bắt kịp mutation trước request | `request_plus`; nếu đòi snapshot giao dịch phải thiết kế thêm |
| Batch đọc nhiều document đã ghi bởi chính workflow | Phải thấy các mutation cụ thể | Gom mutation state theo SDK khi có hỗ trợ |
| Tính toán tồn kho/quy trình nhiều entity cần atomicity | Không chấp nhận kết quả trung gian | Transaction/thiết kế nghiệp vụ, CAS, idempotency |

Quy tắc hữu ích: nếu API biết chính xác document cần kiểm chứng, **đọc theo ID** có thể đơn giản và rẻ hơn chờ GSI cho cả một truy vấn danh sách.

## 15. Reactive API và rủi ro retry

`ReactiveCouchbaseRepository` và reactive template dùng cùng Data/Query/Index Service. Đổi từ API đồng bộ sang reactive **không làm chỉ mục cập nhật đồng bộ**.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

~~~java
Mono<OrderDocument> justSaved =
    reactiveOrderRepository.findById("order::1001");
~~~

Trong luồng reactive:

- Thao tác KV có thể hoàn tất ở server trước khi subscriber nhận response.
- `retryWhen` có thể **resubscribe** và thực hiện lại một mutation có side effect.
- Request-plus làm query chờ index có thể giữ nhiều tác vụ đồng thời lâu hơn; cần concurrency limit/deadline.
- Nếu cần truyền mutation token, phải có **cách truyền context** từ kết quả write sang query; Reactor context riêng không tự biến CAS thành MutationState.
- Backpressure giúp quản lý luồng dữ liệu, **không** thay cho consistency, durability, CAS hoặc idempotency.

Với API ghi thanh toán, retry an toàn cần ID/idempotency key rõ ràng; timeout mơ hồ không có nghĩa mutation chưa xảy ra.

## 16. Quan sát độ trễ index và xử lý sự cố

Khi query không thấy dữ liệu mới, làm rõ **đúng keyspace**, **đúng dữ liệu** và **đúng consistency** trước khi tăng tài nguyên.

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán |
|---|---|---|
| KV get thấy document; query `not_bounded` chưa thấy | Index lag hoặc query filter khác kỳ vọng | Xác minh document, GSI, `EXPLAIN` và query filter |
| `request_plus` chậm/timeout khi ghi cao | Query đang đợi Index Service bắt kịp | Theo dõi index lag, CPU/disk, query latency |
| Query không chạy sau deploy index | Index còn build, chưa online hoặc thiếu quyền | Kiểm tra trạng thái GSI, keyspace, quyền |
| Query theo field chậm dù index ONLINE | Index scan rộng, Fetch/Sort nặng | Dùng `EXPLAIN`, query profile và đo tài nguyên |
| Chỉ một vài collection chậm | GSI/workload riêng của collection hoặc index node | So sánh index và write rate theo keyspace |
| Query thất bại khi Index node lỗi | Index replica/Query capacity không đủ | Kiểm tra index availability và topology |
| Sau failover query có kết quả bất ngờ | Index/topology đang phục hồi, consistency hoặc mutation lỗi | Đối chiếu KV state, mutation status và health |
| Spring Data query thiếu document khi JSON vẫn đúng | `_class`/type filter hoặc collection mapping | Log câu SQL++ được sinh, so sánh `META().id` và body |

### 16.1. Metrics hữu ích

Trong dashboard/telemetry khả dụng, nên theo dõi:

1. **KV mutation latency và success/error rate**, đặc biệt những mutation có yêu cầu durability.
2. **Query latency p50/p95/p99**, timeout và loại consistency sử dụng.
3. **Index mutation backlog/lag**, trạng thái index, tài nguyên CPU/RAM/đĩa/mạng của Index node.
4. **Index scan/Fetch/sort chi phí**, số entry scan và số document trả về.
5. **Node health**, rebalance, failover, index replica availability.
6. **Business read-after-write miss rate**, nếu ứng dụng có thể đo an toàn từ hành vi thực.

Tên metric cụ thể phụ thuộc Couchbase Server/Capella, SDK và hệ thống quan sát; xác định nghĩa của từng metric trước khi đặt ngưỡng. Một “index lag = 0” trong một đồ thị không đủ chứng minh mọi query đều có plan hoặc quyền đúng.

### 16.2. Thứ tự xử lý sự cố

1. Đọc bằng KV theo ID để xác nhận document có tồn tại và trường JSON đúng.
2. Đảm bảo SQL++ `FROM` trỏ đúng `bucket.scope.collection`, đủ quyền và điều kiện lọc không loại document.
3. Kiểm tra chỉ mục phục vụ query đã **ONLINE** chưa, có index phù hợp không.
4. Chạy `EXPLAIN` và quan sát query plan.
5. Thử query với `request_plus` trong môi trường phù hợp để phân biệt tình trạng độ mới với filter/index plan sai.
6. Quan sát độ trễ index, tài nguyên Index/Query node và sự kiện rebalance/failover.
7. Điều chỉnh kiến trúc consistency hoặc index/capacity, rồi đo lại dưới tải đại diện.

Không giải quyết bằng cách thêm `Thread.sleep(...)` cố định hoặc tăng timeout vô hạn; cách này che giấu bottleneck và không tạo bảo đảm độ mới.

## 17. Thiết kế kiểm thử cho tính bất đồng bộ

Không nên viết test kiểu “ghi xong đợi 200 ms rồi query, kết quả phải luôn có document”. Nếu GSI cập nhật nhanh, test có thể pass, nhưng khi CI chậm hoặc node bận sẽ trở nên thất thường.

### 17.1. Kiểm thử theo hợp đồng nhất quán

| Trường hợp | Cách kiểm thử | Kết quả cần xác nhận |
|---|---|---|
| **KV read-after-write** | `upsert` rồi `get` theo ID | Document đúng, khi không có lỗi concurrency/expiry |
| **Request-plus** | Ghi KV rồi query `REQUEST_PLUS` với index online | Query đạt mốc consistency hoặc báo timeout rõ ràng |
| **MutationState** | Ghi lấy mutation result rồi query `consistentWith` | Query có khả năng nhìn thấy mutation được chỉ định |
| **Not-bounded** | Ghi rồi query mặc định trong tải cao | Không viết assertion bắt buộc nhìn thấy ngay; đo độ trễ hội tụ |
| **Index build** | Tạo index và theo dõi trạng thái | Không chạy business query phụ thuộc trước khi index sẵn sàng |
| **Mất Index node** | Diễn tập trên môi trường có kế hoạch | Đánh giá index replica, query availability và timeout |
| **Spring Data mapping** | So sánh SQL++ sinh với schema và index | Đúng keyspace, điều kiện `_class`, filter và plan |
| **Reactive retry** | Giả lập response không rõ sau mutation | Không ghi trùng, deadline/retry có giới hạn |

### 17.2. Đo độ trễ hội tụ của index

Có thể xây một thử nghiệm tải nhỏ trên môi trường test:

1. Sinh document có ID duy nhất, `tenantId` và mốc thao tác trong payload.
2. Ghi KV và ghi nhận thời gian server/client trả thành công.
3. Định kỳ query `not_bounded` theo field với khoảng kiểm tra hợp lý và deadline.
4. Khi document xuất hiện, ghi nhận phân phối thời gian trễ quan sát được.
5. Lặp lại ở các mức write rate/index workload khác nhau để ước lượng p50/p95/p99.

Thử nghiệm này có thể giúp **đo** độ trễ hội tụ nhưng không định nghĩa một bảo đảm thời gian tối đa. Khi tính SLO đọc sau ghi, nên dùng consistency đúng API thay vì dựa vào độ trễ trung bình.

## 18. Bài tập tình huống

### Bài tập A — phân biệt ba kết quả

Ứng dụng `save(order)` thành công. Ngay sau đó:

1. `findById(orderId)` trả đúng đơn vừa ghi.
2. `findByTenantIdAndStatus(tenantId, "PAID")` không trả đơn.
3. Query `REQUEST_PLUS` với cùng điều kiện trả đơn.

Hãy giải thích vì sao đây là dấu hiệu phù hợp với index lag. Có kết luận được `save` đã thất bại hoặc cần thêm CAS không?

**Gợi ý:** KV và GSI là hai đường truy cập; CAS không ép GSI cập nhật ngay.

### Bài tập B — chọn cơ chế consistency

Một endpoint hiển thị xác nhận thanh toán theo `orderId`; endpoint khác liệt kê toàn bộ đơn PAID của tenant. Đề xuất đường đọc và consistency cho mỗi endpoint. Giải thích chi phí nếu bật `request_plus` ở cả hai nơi.

### Bài tập C — MutationState từ hai lần ghi

Workflow cập nhật hai đơn khác nhau, có thể thuộc hai vBucket. Sau đó cần SQL++ thấy trạng thái của cả hai. Hãy nêu cách thu thập mutation token, gom state theo API SDK và giải thích vì sao thao tác này **không tự bảo đảm atomicity**.

### Bài tập D — tối ưu chậm do Fetch/Sort

Truy vấn có index đúng `tenantId` nhưng phải scan hàng trăm nghìn document, Fetch body rồi sort. Có nên chỉ chuyển `not_bounded` thành `request_plus` để truy vấn nhanh hơn không? Dùng `EXPLAIN` đánh giá index phù hợp với `tenantId`, `status` và `createdAt`.

### Bài tập E — phân biệt lỗi mapping

Document vừa ghi đọc bằng KV được, nhưng ngay cả query `REQUEST_PLUS` cũng không tìm thấy. Hãy đề xuất các bước kiểm tra theo thứ tự: keyspace, `_class`/type, điều kiện lọc, GSI status, quyền và query plan.

### Bài tập F — reactive retry

Một pipeline reactive ghi đơn và query SQL++ ngay sau đó. Lập trình viên dùng `retryWhen` cho mọi lỗi, đồng thời `Thread.sleep(100)` sau save. Giải thích hai rủi ro và đề xuất một pipeline có idempotency, timeout và consistency rõ ràng.

## 19. Checklist thiết kế ứng dụng

- [ ] Phân biệt **xác nhận ghi KV** với **thời điểm GSI bắt kịp**.
- [ ] Có index SQL++ phù hợp trên đúng bucket/scope/collection, ở trạng thái sẵn sàng.
- [ ] Dùng KV theo ID khi đã biết document cần đọc.
- [ ] Xác định SLA độ mới của từng endpoint: có chấp nhận trễ không?
- [ ] Dùng `not_bounded` khi có thể chấp nhận độ trễ chỉ mục.
- [ ] Dùng `request_plus` khi cần GSI theo kịp mốc query và không có mutation token riêng.
- [ ] Dùng `consistentWith(MutationState)` khi cần chờ mutation xác định và API hỗ trợ.
- [ ] Không dùng CAS, TTL, durability hoặc transaction như cách thay thế trực tiếp scan consistency.
- [ ] Không giả định covering index bảo đảm index mới nhất.
- [ ] Đối chiếu SQL++ do Spring Data sinh, gồm keyspace và điều kiện phân biệt entity.
- [ ] Đo index lag, query p95/p99 và bottleneck Query/Index Service.
- [ ] Có timeout, retry/idempotency rõ ràng, nhất là với reactive mutation.
- [ ] Kiểm thử hành vi bất đồng bộ bằng hợp đồng consistency, tránh sleep cố định.
- [ ] Có phương án khôi phục Query/Index Service và index replica phù hợp với SLA.
- [ ] Kiểm tra phiên bản SDK/framework/server khi dùng QueryOptions, MutationState hoặc cách cấu hình Spring Data.

## 20. Tổng kết

**GSI của Couchbase được cập nhật bất đồng bộ từ các mutation ở Data Service.** Vì thế `save` hoặc `insert` trả thành công qua KV không mặc nhiên đảm bảo một truy vấn SQL++ theo trường JSON sẽ nhìn thấy document mới ngay lập tức. Query Service có thể dùng chỉ mục chưa bắt kịp thay đổi, tùy scan consistency.

Ba lựa chọn cốt lõi là **`not_bounded`** để tối ưu độ trễ khi chấp nhận dữ liệu cập nhật chậm; **`request_plus`** để chờ index bắt kịp các mutation trước request; và **`consistentWith(MutationState)`** để chờ những mutation đã biết. Với API chỉ cần đọc một document theo ID, **KV get** thường đơn giản hơn.

Trong **Spring Data Couchbase**, repository, `CouchbaseTemplate` và reactive API cùng chịu các nguyên tắc Data/Query/Index này. Thiết kế tốt cần kết hợp đúng **đường đọc, index, consistency, timeout, CAS, durability, transaction và idempotency** theo yêu cầu nghiệp vụ, đồng thời đo hiệu năng dưới tải thực tế.
