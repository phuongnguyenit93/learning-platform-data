# Phân biệt tính nguyên tử, tính nhất quán và độ bền ghi trong Couchbase

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập dữ liệu bằng document mapping, repository, `CouchbaseTemplate` và SQL++; vận dụng thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, transaction và API reactive để kiểm soát tính đúng đắn, hiệu năng và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **atomicity (tính nguyên tử)**, **consistency (tính nhất quán)** và **durability (độ bền ghi)** qua những câu hỏi và sự cố thực tế.
2. Nêu ranh giới tính nguyên tử của một thao tác trên **một document** và thời điểm cần **transaction nhiều document**.
3. Phân biệt tính nhất quán **của trạng thái nghiệp vụ**, **kiểm soát cạnh tranh bằng CAS**, **độ mới của truy vấn SQL++ qua GSI**, và **đọc từ replica**.
4. Giải thích các lựa chọn **synchronous durability** và tác động của replication, persistence, failover, timeout.
5. Thiết kế retry/idempotency khi kết quả ghi **không chắc chắn** (*ambiguous outcome*).
6. Chọn đúng đường truy cập bằng Spring Data Couchbase: repository, `CouchbaseTemplate`, SDK transactions, SQL++ và reactive API.
7. Thiết kế thử nghiệm để không nhầm một hệ thống “ghi đã thành công” với “mọi nơi đã thấy dữ liệu” hoặc “không thể mất dữ liệu”.

## 2. Ba thuộc tính có mục đích khác nhau

Khi thiết kế hệ thống bán hàng, ta thường nghe yêu cầu: “Ghi dữ liệu phải an toàn và nhất quán”. Yêu cầu này cần được tách thành những câu hỏi cụ thể.

| Thuộc tính | Câu hỏi chính | Ví dụ với đơn hàng | Cơ chế liên quan |
|---|---|---|---|
| **Atomicity — nguyên tử** | Một nhóm thay đổi phải **cùng thành công hoặc không có thay đổi nào được chấp nhận**? | Tạo đơn và trừ tồn kho phải được xử lý như một đơn vị | Mutation một document, Couchbase Transactions cho nhiều document |
| **Consistency — nhất quán** | Kết quả đọc và trạng thái nghiệp vụ có đáp ứng invariant/độ mới yêu cầu không? | Không giao hàng hai lần; sau ghi đơn PAID, màn hình nào phải thấy đơn? | CAS, kiểm tra quy tắc nghiệp vụ, transaction isolation, KV read, SQL++ scan consistency |
| **Durability — bền ghi** | Một thay đổi đã được xác nhận sẽ sống sót qua những loại lỗi nào? | Node đang ghi đơn hỏng ngay sau phản hồi thành công | Data replica, persistence, synchronous durability |
| **Isolation — cô lập** (liên quan) | Các thao tác đồng thời nhìn và ảnh hưởng lẫn nhau thế nào? | Hai yêu cầu cùng cập nhật số lượng hàng tồn | CAS và ngữ nghĩa isolation của transaction |

**Không có một tùy chọn duy nhất** biến tất cả các mục trên thành “an toàn tuyệt đối”. Ví dụ:

- Một thao tác `replace` có thể **nguyên tử trên một document**, nhưng không tự bảo vệ workflow gồm ba document.
- CAS có thể chặn **lost update** nhưng không buộc GSI mới ngay sau ghi.
- `request_plus` có thể làm SQL++ chờ GSI theo kịp, nhưng không tự biến hai lệnh `upsert` thành một transaction.
- `MAJORITY` tăng yêu cầu độ bền mutation, nhưng không xác minh đơn hàng đã tuân thủ quy tắc “không trừ kho âm”.
- Backup có thể giúp khôi phục sau xóa nhầm; nó **khác** data replica và synchronous durability.

### 2.1. “Consistency” có nhiều nghĩa

Cần xác định rõ ngữ cảnh mỗi lần dùng từ *consistency*:

1. **Business consistency:** dữ liệu thỏa ràng buộc nghiệp vụ, ví dụ `availableStock >= 0`.
2. **Concurrency consistency:** các cập nhật đồng thời không ghi đè nhau tùy yêu cầu, ví dụ CAS.
3. **Query freshness:** kết quả SQL++ nhìn thấy mutation gần đây đến mức nào.
4. **Replica freshness:** bản sao đọc được đã bắt kịp active chưa.
5. **Transaction isolation:** các bước trong giao dịch và thao tác đồng thời quan sát nhau thế nào.

Các vấn đề này có liên quan nhưng không thay thế nhau. Bài học sẽ dùng thuật ngữ cụ thể thay vì chỉ nói “đọc nhất quán” chung chung.

## 3. Mô hình Couchbase liên quan đến ba thuộc tính

Dữ liệu Couchbase được tổ chức theo **bucket → scope → collection → document**. Trong mỗi bucket, Couchbase phân phối document qua những **vBucket** trên các Data node.

~~~text
Bucket: commerce
├── Scope: sales
│   ├── Collection: orders
│   │   └── ID: order::1001
│   └── Collection: payments
│       └── ID: payment::1001
└── Scope: catalog
    └── Collection: inventory
        └── ID: inventory::sku-A1
~~~

- Thao tác **KV theo ID** được SDK định tuyến tới Data Service đang giữ active vBucket.
- Một bucket có thể có **replica vBucket** trên node khác để tăng khả năng chịu lỗi.
- **SQL++** thường dùng Query Service và Global Secondary Index (GSI) của Index Service khi truy vấn theo trường JSON.
- Chỉ mục được cập nhật từ luồng mutation **bất đồng bộ** so với thao tác KV, nên kết quả SQL++ có thể chưa thấy ghi mới nếu chọn chế độ không chờ index.

~~~mermaid
flowchart LR
    App["Spring Data / Couchbase SDK"]
    Data["Data Service<br/>Active vBucket"]
    Replica["Data Service<br/>Replica vBucket"]
    Stream["Mutation stream"]
    Index["Index Service<br/>GSI"]
    Query["Query Service<br/>SQL++"]
    App -->|"KV write/read theo ID"| Data
    Data -->|"Replication"| Replica
    Data -->|"Change feed"| Stream
    Stream -->|"Async index update"| Index
    App -->|"Query theo thuộc tính"| Query
    Query -->|"Index scan"| Index
    Query -->|"Fetch nếu cần"| Data
~~~

Từ sơ đồ trên, có ba mốc khác nhau:

~~~text
T0: Active Data Service chấp nhận mutation
T1: Replica/persistence đạt mức durability yêu cầu (nếu được đặt)
T2: GSI của Index Service cập nhật để phục vụ query theo trường
~~~

**Không giả định T0, T1 và T2 trùng nhau.** Cách phản hồi mutation phụ thuộc durability level, nhưng độ mới GSI vẫn là một cơ chế riêng.

## 4. Atomicity: một document được cập nhật như một đơn vị

Đơn vị cơ bản thuận tiện để thiết kế trong Couchbase là **document**. Một mutation KV thành công như `insert`, `replace`, `upsert` hoặc `remove` tác động nguyên tử đến một document theo semantics của thao tác đó.

Giả sử document `order::1001`:

~~~json
{
  "status": "NEW",
  "total": 1490000,
  "currency": "VND",
  "items": [
    {"sku": "A1", "quantity": 2, "unitPrice": 745000}
  ]
}
~~~

Nếu dùng một lệnh `replace` để thay đổi cả `status` và `total`, thao tác này là một mutation trên document. Người đọc không nên thấy một nửa body đã thay đổi trong khi nửa còn lại vẫn thuộc body cũ do chính mutation đơn đó.

### 4.1. Insert, replace và upsert có semantics khác nhau

| KV operation | Ý nghĩa | Điều có thể gây hiểu nhầm |
|---|---|---|
| `insert(id, body)` | Tạo nếu ID chưa tồn tại | ID trùng thì lỗi, không “ghi đè cho chắc” |
| `replace(id, body)` | Thay document đang tồn tại | Không tự biết business rule bị thay đổi bởi người khác |
| `upsert(id, body)` | Tạo hoặc thay toàn bộ document | Có thể ghi đè dữ liệu mới hơn nếu thiếu điều kiện |
| `remove(id)` | Xóa một document | Không tự xóa các document tham chiếu ở collection khác |
| `mutateIn` (sub-document) | Thao tác trên đường dẫn trong một document | Các bước của một lệnh phục vụ document, không tạo transaction nhiều document |

Dù mutation một document nguyên tử, ứng dụng vẫn phải xử lý lỗi không tìm thấy, trùng ID, quyền truy cập, TTL/expiry và kết quả ambiguous khi mạng gián đoạn.

### 4.2. Sub-document mutation cũng có ranh giới document

Ví dụ cần sửa trạng thái và ghi thời điểm cập nhật trên **cùng một order document**. Có thể cân nhắc một thao tác sub-document nhiều specification khi API hỗ trợ, thay vì thực hiện hai mutation KV tách rời.

~~~java
import static com.couchbase.client.java.kv.MutateInSpec.upsert;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

// orders: Collection đã trỏ đến commerce.sales.orders.
orders.mutateIn(
    "order::1001",
    List.of(
        upsert("status", "PAID"),
        upsert("updatedAt", "2026-11-25T03:00:00Z")
    )
);
~~~

Ví dụ trên nhấn mạnh hai trường thuộc **một document**. Trong bài toán cần kiểm tra trạng thái trước khi sửa, vẫn phải kết hợp CAS hoặc một điều kiện nghiệp vụ phù hợp để tránh race condition. Một mutation sub-document không bảo đảm toàn bộ quy trình liên quan đến document tồn kho và thanh toán cùng nguyên tử.

## 5. Atomicity không tự giải quyết cập nhật cạnh tranh: vai trò CAS

Xét hai request đồng thời:

~~~text
T0: order::1001.status=NEW, CAS=V1
T1: A đọc NEW, CAS V1
T2: B đọc NEW, CAS V1
T3: A ghi status=PAID, CAS mới V2
T4: B ghi status=CANCELLED bằng bản đã đọc ở T2
~~~

Nếu B dùng `upsert`/`replace` mà **không** kiểm tra phiên bản, thay đổi của A có thể bị ghi đè (**lost update**). Mỗi thao tác vẫn nguyên tử riêng lẻ, nhưng trạng thái cuối không đúng kỳ vọng của hệ thống.

**CAS (Compare-And-Swap)** là token opaque của document để thực hiện cập nhật có điều kiện.

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

GetResult before = orders.get("order::1001");

JsonObject next = before.contentAsObject()
        .put("status", "PAID");

orders.replace(
    "order::1001",
    next,
    replaceOptions().cas(before.cas())
);
~~~

Nếu document đã thay đổi kể từ lần đọc, server có thể trả lỗi CAS mismatch. Khi đó cần:

1. Đọc lại trạng thái mới nhất.
2. Kiểm tra phép chuyển trạng thái còn hợp lệ về nghiệp vụ không.
3. Từ chối hoặc thử lại có giới hạn theo rule; không xóa điều kiện CAS để ép ghi.
4. Đảm bảo các HTTP request lặp lại không tạo side effect ngoài dự kiến.

**CAS không phải transaction nhiều document.** CAS cũng không phải timestamp hoặc số thứ tự toàn cục; không tự cộng CAS và không dùng nó làm mốc độ mới của GSI.

## 6. Khi nào cần transaction nhiều document?

Một đơn hàng hoàn chỉnh có thể gồm:

1. Tạo `orders/order::1001`.
2. Trừ `inventory/inventory::sku-A1`.
3. Tạo `payments/payment::1001` hoặc trạng thái xử lý thanh toán.

Nếu thực hiện ba lệnh KV riêng lẻ:

~~~text
1. insert order::1001       → thành công
2. replace inventory::sku-A1 → thành công
3. insert payment::1001     → thất bại
~~~

Kết quả là dữ liệu đã thay đổi một phần. **Tính nguyên tử riêng của từng document không bảo đảm cả ba bước cùng thành công.**

~~~mermaid
flowchart TD
    A["Bắt đầu tạo đơn"]
    B["Ghi order document"]
    C["Cập nhật inventory document"]
    D["Ghi payment document"]
    E["Hoàn tất"]
    X["Nếu một bước lỗi: trạng thái một phần có thể tồn tại"]
    A --> B --> C --> D --> E
    B -.-> X
    C -.-> X
    D -.-> X
~~~

Nếu nghiệp vụ đòi hỏi nhóm thao tác Couchbase phải **cùng commit hoặc rollback**, dùng **Couchbase Transactions** theo API/điều kiện hỗ trợ. Transaction giúp một đơn vị công việc trải trên nhiều document và có thể qua nhiều collection/vBucket, nhưng còn những giới hạn quan trọng về hiệu năng, service, loại bucket, version và lỗi.

### 6.1. Java SDK: ví dụ transaction nhiều document

Ví dụ dưới đây minh họa việc chuyển trạng thái đơn và ghi một document ghi nhận thanh toán **đều trong Couchbase**. Nó không thực hiện charge tiền thật ở cổng thanh toán ngoài.

~~~java
import com.couchbase.client.java.json.JsonObject;

// orders và payments là hai Collection đã được cấu hình.
// Giả định order::1001 đã tồn tại và payment::1001 chưa tồn tại.
cluster.transactions().run(ctx -> {
    var currentOrder = ctx.get(orders, "order::1001");
    JsonObject nextOrder = currentOrder.contentAsObject()
            .put("status", "PAID");

    ctx.replace(currentOrder, nextOrder);

    JsonObject payment = JsonObject.create()
            .put("orderId", "order::1001")
            .put("status", "RECORDED")
            .put("amount", 1490000);

    ctx.insert(payments, "payment::1001", payment);
});
~~~

Đây là ví dụ Couchbase Java SDK Transactions hiện đại. Kiểm tra phiên bản SDK và cấu hình dịch vụ trước khi dùng trong dự án. Trong thực tế, cần **đọc/kiểm tra business rule trong transaction**, đảm bảo ID thanh toán không gây trùng và xử lý transaction exception.

### 6.2. Callback có thể được chạy lại

Một đặc điểm quan trọng của transaction SDK là cơ chế retry **có thể gọi lại phần mã bên trong transaction lambda** khi gặp xung đột hoặc lỗi có thể phục hồi. Do đó:

- Không gửi email, gọi cổng thanh toán, ghi log audit bên ngoài hoặc phát sự kiện không idempotent trực tiếp trong callback.
- Không tạo ID ngẫu nhiên mới mỗi lần callback được retry nếu ID phải ổn định trong một operation.
- Đặt **side effect bên ngoài** sau khi transaction commit hoặc dùng outbox/saga và idempotency theo thiết kế.

Transaction đảm bảo nguyên tử cho các mutation thuộc phạm vi transaction Couchbase được hỗ trợ; **không tự bao gồm REST API, Kafka, hệ thống thanh toán hay database khác**.

### 6.3. Transaction không phải công tắc miễn phí

Mỗi transaction nhiều document thường tốn thêm round trip, metadata/coordination và có thể gặp conflict/timeout. Với workflow có thể lưu toàn bộ thông tin nhỏ trong **một document duy nhất**, sử dụng một mutation document có thể đơn giản hơn.

Không tự động chuyển mọi `save` thành transaction: cần làm rõ phạm vi, invariant, contention, độ trễ và nhu cầu rollback trước.

## 7. Consistency của nghiệp vụ: invariant phải do thiết kế bảo vệ

Trong ACID, “C” thường được hiểu là trạng thái chuyển từ **một tập dữ liệu hợp lệ** sang tập dữ liệu hợp lệ khác dựa trên invariant. Không nên đồng nhất nó với “mọi truy vấn đều đọc phiên bản mới nhất”.

Ví dụ tồn kho:

~~~json
{
  "sku": "A1",
  "availableStock": 1
}
~~~

Có hai yêu cầu mua hàng, mỗi yêu cầu mua một sản phẩm. Nếu hai request cùng đọc `availableStock=1` rồi cùng ghi về 0, hệ thống có thể chấp nhận hai đơn dù chỉ có một sản phẩm.

Các phương án cần đánh giá:

- Dùng **CAS** và kiểm tra `availableStock >= quantity` trước khi ghi, retry có điều kiện.
- Dùng **một lệnh mutation có điều kiện** nếu thao tác và API hỗ trợ invariant cần thực thi.
- Dùng **transaction** khi việc giữ tồn kho và tạo đơn phải cùng nguyên tử trên nhiều document.
- Dùng mô hình đặt giữ hàng, idempotency, queue hoặc saga cho quy trình liên hệ hệ thống ngoài.

Ngay cả khi transaction commit thành công, **business logic sai vẫn tạo dữ liệu sai**. Couchbase không tự áp đặt foreign key/cascade hoặc mọi invariant quan hệ chỉ vì có SQL++.

### 7.1. Schema và constraint

Collection Couchbase chứa document JSON với schema linh hoạt. Trường `status` có thể bị ghi thành giá trị không hợp lệ nếu ứng dụng không validate.

~~~json
{"status": "PAID", "total": -1000}
~~~

Mutation này có thể hợp lệ ở tầng lưu trữ mà vẫn **vô nghĩa ở tầng nghiệp vụ**. Do đó business consistency cần:

1. Xác thực dữ liệu đầu vào.
2. Định nghĩa các phép chuyển trạng thái hợp lệ.
3. Bảo vệ các invariant trong vùng atomicity phù hợp.
4. Giữ schema version/migration có kiểm soát.
5. Thử nghiệm cạnh tranh và tình huống lỗi từng bước.

## 8. Consistency khi đọc KV theo ID

Đối với document có ID biết trước, ứng dụng có thể dùng Couchbase KV API:

~~~java
var read = orders.get("order::1001");
JsonObject body = read.contentAsObject();
~~~

Đây là đường đọc từ **Data Service** dựa trên key và active vBucket; nó không cần GSI. Trong luồng bình thường, sau khi một mutation được xác nhận thành công và không có update/delete/failover khác chen vào, đọc KV theo active owner là cách trực tiếp để quan sát document vừa ghi.

Cần hiểu giới hạn:

- Nếu **document khác bị sửa đồng thời**, lần đọc mới có thể nhận trạng thái mới hơn.
- Nếu document **hết TTL**, đã bị xóa hoặc truy cập sai keyspace, `get` có thể not-found.
- Nếu đọc qua API **replica read**, kết quả có thể cũ hơn active.
- Khi failover hoặc network lỗi, request có thể timeout, cần retry/deadline; durability của mutation quyết định một phần hành vi khi mất node.

### 8.1. Replica read và độ mới

Java SDK cung cấp API đọc replica như `getAnyReplica` hoặc `getAllReplicas` trong các phiên bản hỗ trợ. Những API này có thể trả dữ liệu từ các bản sao chưa theo kịp active.

**Có data replica không đồng nghĩa `get(id)` mặc định đọc ngẫu nhiên từ replica.** Đọc replica là quyết định API; chỉ sử dụng khi chấp nhận trade-off về độ mới dữ liệu và có xử lý tình trạng bản sao.

Ví dụ: trang thông tin sản phẩm có thể chấp nhận stale data ngắn; kiểm tra trạng thái thanh toán cuối cùng thường không nên mặc định dùng stale replica read.

## 9. Consistency khi đọc SQL++ theo trường JSON

Để tìm các đơn đã thanh toán của một tenant:

~~~sql
SELECT META(o).id AS orderId, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-42"
  AND o.status = "PAID";
~~~

Truy vấn này thường dựa trên **GSI**:

~~~sql
CREATE INDEX ix_orders_tenant_status
ON `commerce`.`sales`.`orders`(tenantId, status);
~~~

GSI được Index Service cập nhật **bất đồng bộ** từ mutation ở Data Service. Vì vậy, ngay sau khi `orders.upsert(...)` thành công, SQL++ ở chế độ mặc định có thể chưa tìm thấy bản ghi nếu index chưa bắt kịp.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Data as Data Service
    participant Idx as Index Service
    participant Query as Query Service
    App->>Data: KV insert(status=PAID)
    Data-->>App: Mutation thành công
    Data-->>Idx: Mutation feed bất đồng bộ
    App->>Query: SQL++ WHERE status=PAID
    Query->>Idx: IndexScan
    Idx-->>Query: Index có thể chưa bắt kịp
    Query-->>App: Kết quả theo scan consistency
    Note over Idx: Cập nhật index được xử lý
~~~

Hiện tượng này thường được gọi là **index lag** hoặc **eventual index consistency**. Nó **không chứng minh thao tác KV thất bại**, và việc thêm CAS vào `save` không buộc index cập nhật tức thời.

### 9.1. Các chế độ scan consistency

| Chế độ | Ý nghĩa khái quát | Phù hợp khi |
|---|---|---|
| **`not_bounded`** | Query không yêu cầu index phải bắt kịp một mốc mutation mới cụ thể trước khi scan | Danh sách chấp nhận độ trễ cập nhật |
| **`request_plus`** | Chờ index đạt trạng thái phản ánh các mutation trước mốc yêu cầu query theo semantics server | Cần đọc dữ liệu mới ở thời điểm bắt đầu truy vấn |
| **`at_plus` / `consistentWith`** | Chờ index đạt ít nhất các mutation token được đưa vào | Read-your-own-writes từ một/một số mutation đã biết |

Mức scan consistency **không tự tạo snapshot transaction xuyên toàn cluster** và không thay thế durability, CAS hoặc invariant nghiệp vụ.

### 9.2. Java SDK: yêu cầu REQUEST_PLUS

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
    "SELECT META(o).id AS id, o.status " +
    "FROM `commerce`.`sales`.`orders` AS o " +
    "WHERE o.tenantId = 'tenant-42' AND o.status = 'PAID'",
    queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

`REQUEST_PLUS` có thể tăng latency nếu Index Service đang backlog. Dùng theo yêu cầu cụ thể, tránh bật cho mọi truy vấn mà không đo SLO.

### 9.3. Java SDK: dùng MutationState từ ghi đã biết

Sau một KV mutation, SDK có thể cung cấp **mutation token** trong `MutationResult`. Token mô tả vị trí mutation trong luồng vBucket, không phải CAS.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;

MutationResult write = orders.upsert(
    "order::1001",
    JsonObject.create()
        .put("tenantId", "tenant-42")
        .put("status", "PAID")
        .put("total", 1490000)
);

var queryResult = cluster.query(
    "SELECT META(o).id AS id, o.status " +
    "FROM `commerce`.`sales`.`orders` AS o " +
    "WHERE o.tenantId = 'tenant-42' AND o.status = 'PAID'",
    queryOptions().consistentWith(MutationState.from(write))
);
~~~

Ví dụ dùng kiểu API Couchbase Java SDK 3.x; chi tiết package/method và khả năng cung cấp token cần kiểm tra theo SDK/server trong dự án. Query chờ index đạt mốc mutation **đã biết**, nhưng không làm nguyên tử các mutation đa document.

Nếu đã có document ID và chỉ cần xác nhận đúng đơn vừa tạo, `collection.get(id)` hoặc trả kết quả từ mutation thường đơn giản hơn mở một query theo trường JSON.

## 10. Isolation: hành vi khi có nhiều thao tác đồng thời

**Isolation** trả lời “một thao tác/giao dịch nhìn thấy trạng thái nào khi thao tác khác đang thực hiện?”. Không nên suy ra isolation level của một database quan hệ khác rồi áp dụng nguyên xi cho Couchbase.

### 10.1. CAS kiểm soát xung đột khi update một document

CAS là giải pháp phù hợp cho đọc → tính toán → ghi một document, nếu nghiệp vụ cần ngăn lost update. Nó không định nghĩa isolation cho một nhóm thao tác SQL++ qua nhiều collection.

### 10.2. Transaction nhiều document có semantics riêng

Khi dùng Couchbase Transactions, SDK điều phối các thao tác thuộc một transaction theo semantics hỗ trợ. Những gì truy vấn bên trong transaction và các thao tác ngoài transaction có thể nhìn thấy phụ thuộc API, isolation và giai đoạn commit.

Không mặc định rằng mọi query không thuộc transaction sẽ thấy đầy đủ một workflow **đang xử lý** hoặc rằng `request_plus` thay thế transaction isolation.

### 10.3. Kiểm tra invariant khi có tranh chấp

Với hai người cùng mua món hàng cuối cùng, một transaction hoặc CAS có thể phát hiện conflict, nhưng code phải **kiểm tra lại tồn kho** trong lần retry. Nếu chỉ retry với giá trị “stock=0” đã tính từ bản đọc cũ, nguyên tắc atomicity không tự sửa lỗi nghiệp vụ.

### 10.4. Quy tắc thực hành

- Nếu invariant nằm **trong một document**, cân nhắc dùng một mutation có điều kiện/CAS.
- Nếu invariant liên quan **nhiều document Couchbase**, cân nhắc transaction.
- Nếu invariant liên quan **hệ thống ngoài**, xác định giới hạn transaction và chọn saga/outbox/idempotency.
- Nếu chỉ cần **đọc phiên bản mới của một document có ID**, ưu tiên KV thay vì query GSI.

## 11. Durability: dữ liệu đã được xác nhận sống sót đến đâu?

Khi một mutation KV trả thành công, mức bảo đảm về dữ liệu được sao chép hoặc persist còn phụ thuộc **durability option**, replica, bucket type và phiên bản Couchbase.

Các mức **synchronous durability** thông dụng trong Couchbase:

| Mức | Yêu cầu khái quát trước khi xem mutation durable | Đánh đổi |
|---|---|---|
| Không yêu cầu synchronous durability bổ sung | Ack theo semantics mặc định của thao tác KV | Thường ít phối hợp hơn; một số thay đổi gần thời điểm lỗi có thể chưa đáp ứng mục tiêu replica/persistence |
| **`MAJORITY`** | Xác nhận mutation theo đa số bản dữ liệu liên quan | Có thể chờ replication, tăng latency |
| **`MAJORITY_AND_PERSIST_TO_ACTIVE`** | Đa số xác nhận và active persist theo yêu cầu | Thêm ràng buộc I/O trên active |
| **`PERSIST_TO_MAJORITY`** | Mutation được persist ở đa số bản theo cơ chế hỗ trợ | Yêu cầu bền hơn trong một số kịch bản, có thể tốn thời gian hơn |

**Cần xem chính xác semantics của phiên bản Couchbase Server, loại bucket và cấu hình replica.** Không có mức nào là lời hứa “không bao giờ mất dữ liệu” trước mọi lỗi thảm họa, sai thao tác hoặc hỏng logic ứng dụng.

### 11.1. Java SDK: mutation có durability

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;

orders.insert(
    "order::1001",
    JsonObject.create()
        .put("status", "NEW")
        .put("tenantId", "tenant-42")
        .put("total", 1490000),
    insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Đoạn mã giả định `orders` là một `Collection` đã kết nối. Trong production, chọn mức durability dựa trên RPO, latency và khả năng chịu lỗi của cluster; không bật mức mạnh nhất mọi nơi mà không đo throughput.

### 11.2. Replica không tự đồng nghĩa durability

Một bucket có cấu hình một data replica không nhất thiết chứng minh **mutation vừa được active xác nhận đã có mặt trên replica** tại cùng thời điểm khi không yêu cầu durability phù hợp.

Replica hỗ trợ high availability; durability option mô tả điều kiện ghi phải đạt trước khi xác nhận ở mức đã yêu cầu. Hai khái niệm bổ sung cho nhau.

### 11.3. Persistence khác backup

- **Persistence:** dữ liệu ghi xuống thiết bị lưu trữ theo semantics của server/bucket.
- **Data replica:** bản sao phân vùng có thể được promote khi node lỗi.
- **Backup/restore:** bản lưu độc lập để khôi phục sau xóa nhầm hoặc mất dữ liệu nghiêm trọng.

Một mutation `PERSIST_TO_MAJORITY` vẫn có thể bị xóa nhầm bởi lệnh hợp lệ; backup/restore là lớp phục hồi khác. Với bucket/triển khai không dùng persistence như thông thường, cần kiểm tra mức durability thực sự được hỗ trợ.

## 12. Failover, rebalance và kết quả ghi chưa chắc chắn

Giả sử active vBucket của `order::1001` nằm trên Data node B, một replica trên A. B lỗi ngay sau khi API gửi mutation.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant SDK as Couchbase SDK
    participant B as Data node B (active)
    participant A as Data node A (replica)
    participant M as Cluster management
    App->>SDK: insert order::1001
    SDK->>B: KV mutation
    Note over B: Server có thể ghi trước khi response được nhận
    B--xSDK: Mất kết nối / timeout
    M->>A: Promote replica nếu đủ điều kiện
    M-->>SDK: VBucket map mới
    SDK-->>App: Có thể báo lỗi ambiguous
~~~

Thực tế có nhiều khả năng:

1. Request **chưa tới server**: chưa có mutation.
2. Server **đã thực hiện**, nhưng response bị mất: mutation có thể đang tồn tại.
3. Mutation bị gián đoạn trong thay đổi active owner: trạng thái phải được xác minh theo outcome/durability.

**Timeout không chứng minh “ghi thất bại”.** Đây là một trong những nguyên nhân quan trọng nhất của duplicate record trong ứng dụng phân tán.

### 12.1. Đọc lại trước khi retry nghiệp vụ

Khi client retry thao tác tạo đơn:

- Dùng **document ID ổn định** hoặc idempotency key liên kết với request.
- Ưu tiên `insert` khi chỉ cho phép tạo một lần; nếu gặp duplicate, xác minh document đã có tương ứng với request nào.
- Nếu kết quả ghi ambiguous, kiểm tra trạng thái bằng ID và business invariant trước khi thử lại.
- Không sinh ID ngẫu nhiên mới cho mỗi lần retry cùng một request nếu sẽ tạo bản ghi trùng.
- Với thanh toán, bảo vệ cả việc gọi cổng thanh toán bên ngoài bằng idempotency và trạng thái xử lý.

### 12.2. Failover khác rebalance

**Failover** xử lý sự cố node/owner; **rebalance** phân phối lại vBucket và tài nguyên sau thay đổi topology. Cả hai có thể gây timeout/retry tạm thời. SDK chính thức làm mới vBucket map; ứng dụng không tự thay hàm băm document ID hoặc chọn Data node.

Sau failover, cần kiểm tra mức replica còn lại, capacity N-1, hoạt động của Query/Index Service và khả năng recovery/rebalance. Durability chỉ là một trong nhiều phần của chiến lược khả dụng.

## 13. Atomicity, consistency và durability trong cùng workflow

Xét một API `POST /checkout` xử lý order, inventory và thanh toán. Thiết kế có thể chia thành các pha:

~~~text
A. Nhận request + idempotency key
B. Kiểm tra quyền tenant và hợp đồng dữ liệu
C. Thực hiện giao dịch Couchbase cho order/inventory trạng thái nội bộ
D. Gọi/nhận kết quả từ cổng thanh toán ngoài bằng operation ID ổn định
E. Cập nhật trạng thái cuối, phát sự kiện/notification có kiểm soát
F. Trả kết quả hoặc trạng thái xử lý để client tra cứu
~~~

Không nhất thiết mọi pha nằm trong một transaction Couchbase. Đặc biệt, **Couchbase Transactions không tự bao trùm cổng thanh toán hoặc Kafka**.

| Rủi ro | Ví dụ | Hướng giải quyết |
|---|---|---|
| **Partial writes** | Order được tạo, tồn kho không giảm | Transaction khi invariant trải nhiều document Couchbase |
| **Lost update** | Hai request cùng sửa order | CAS/optimistic locking và kiểm tra chuyển trạng thái |
| **Stale query** | Danh sách chưa thấy đơn PAID vừa ghi | KV theo ID hoặc SQL++ scan consistency phù hợp |
| **Data loss khi node lỗi** | Mutation vừa ghi chưa có bản đủ bền | Replica và synchronous durability theo RPO |
| **Ambiguous timeout** | Client không biết ghi xong chưa | ID ổn định, idempotency, kiểm tra trạng thái |
| **External side effect** | Gửi yêu cầu charge hai lần | Idempotency ở payment gateway, saga/outbox hoặc workflow bù trừ |
| **Xóa nhầm hàng loạt** | Lệnh xóa đúng API nhưng sai phạm vi | Backup/restore, kiểm soát quyền, bảo vệ vận hành |

### 13.1. Ranh giới transaction với hệ thống ngoài

Nếu ghi dữ liệu Couchbase và gọi cổng thanh toán, không thể giả định hai hệ thống chia sẻ một transaction nguyên tử. Một cách thiết kế là **saga**: mỗi bước có trạng thái, idempotency, khả năng retry và hành động bù trừ nếu thích hợp.

Một mô hình khác là **transactional outbox trong cùng hệ dữ liệu**: transaction Couchbase ghi bản ghi nghiệp vụ và outbox event, sau commit có worker chuyển event ra message broker. Consumer phải xử lý idempotent vì phát event có thể lặp.

Điều này tránh gọi cổng thanh toán trực tiếp từ transaction callback, nơi framework có thể retry code. Outbox không đảm bảo hệ thống ngoài xử lý đúng một lần nếu không có idempotency thích hợp.

### 13.2. Không mọi nghiệp vụ cần ACID transaction nhiều document

Nếu mỗi đơn là một aggregate có thể lưu trọn trong **một document nhỏ**, một KV mutation có CAS/durability phù hợp có thể đơn giản và hiệu quả hơn.

Chỉ dùng transaction nhiều document khi yêu cầu invariant/atomicity thực sự trải ra nhiều document và tác động hiệu năng có thể chấp nhận được.

## 14. Spring Data Couchbase: mapping và repository

Spring Data Couchbase hỗ trợ lưu entity như document và thao tác qua repository/`CouchbaseTemplate`. Cần hiểu abstraction đang thực hiện **KV hay SQL++**, và semantics transaction có được kích hoạt rõ ràng hay không.

### 14.1. Entity có CAS optimistic locking

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
    private Long total;

    // Constructor, getter/setter được lược bỏ.
}
~~~

- `@Id` ánh xạ document ID để truy cập KV.
- `@Version` thường sử dụng CAS cho optimistic locking.
- `@Scope`/`@Collection` xác định keyspace khi version Spring Data hỗ trợ.
- `@Version` **không tự biến toàn bộ method service thành transaction**.

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Phân biệt đường truy cập:

~~~java
// Đọc theo ID: thường KV qua Data Service.
var order = orderRepository.findById("order::1001")
        .orElseThrow();

// Truy vấn theo field: thường SQL++ và GSI.
var paid = orderRepository.findByTenantIdAndStatus(
        "tenant-42", "PAID"
);
~~~

Câu query do Spring Data sinh có thể có điều kiện phân biệt loại entity như `_class`; vì vậy index SQL++ nên thiết kế theo query thực tế, không chỉ theo tên method.

### 14.2. `save` không tự tạo transaction nhiều document

Giả sử service gọi:

~~~java
orderRepository.save(order);
inventoryRepository.save(inventory);
paymentRepository.save(payment);
~~~

**Ba lời gọi riêng không tự tạo tính nguyên tử xuyên ba document**, ngay cả khi từng call thành công độc lập.

Tùy framework version, cấu hình và transaction manager, một số hình thức tích hợp transaction có thể tồn tại. Nhưng **không mặc định** `@Transactional` của Spring sẽ điều phối Couchbase multi-document transaction chỉ vì bạn thêm annotation. Hãy xác minh transaction manager, API, boundary, rollback/retry semantics và support matrix của chính phiên bản đang dùng.

Khi cần nêu rõ ví dụ transaction ở mức cơ chế, Couchbase Java SDK `cluster.transactions().run(...)` là một cách minh họa trực tiếp.

### 14.3. `CouchbaseTemplate`

`CouchbaseTemplate` cho phép thao tác entity với mức kiểm soát cao hơn repository ở các phiên bản hỗ trợ. Nhưng chọn template thay repository không làm:

- Một mutation đơn thành transaction nhiều document.
- SQL++ không cần GSI.
- Replica mới tức thì.
- Mutation tự đạt durability mạnh.
- CAS conflict tự trở thành business success.

Khi cần durability hoặc scan consistency cụ thể, chọn API/template/SDK có tùy chọn rõ ràng và kiểm chứng hành vi thực tế.

## 15. Lựa chọn API reactive và rủi ro retry/resubscribe

`ReactiveCouchbaseRepository` hoặc reactive template chuyển cách lập trình sang `Mono`/`Flux` và xử lý bất đồng bộ. Chúng **không thay đổi** ý nghĩa atomicity, consistency hay durability trên Couchbase Server.

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

~~~java
Mono<OrderDocument> result =
        reactiveOrderRepository.findById("order::1001");
~~~

### 15.1. Retry không tự an toàn

Một pipeline ghi:

~~~java
Mono<OrderDocument> write =
        reactiveOrderRepository.save(order);
~~~

Khi dùng toán tử retry với publisher có side effect, **resubscribe có thể thực thi lại mutation**. Nếu request đầu được server xử lý nhưng response bị mất, lần retry có thể gặp duplicate, CAS conflict hoặc tạo side effect mới.

Biện pháp:

1. Phân loại lỗi: CAS conflict, duplicate, timeout ambiguous, lỗi kết nối, lỗi dữ liệu.
2. Xác định thao tác có **idempotent** theo ID và business key không.
3. Giới hạn số lần retry, backoff và deadline để tránh retry storm.
4. Khi kết quả ambiguous, xác minh trạng thái trước khi thực hiện lại nghiệp vụ.
5. Với reactive transaction, đọc đúng tài liệu SDK/framework và không dùng retry chung mù quáng trên callback có external side effect.

Backpressure giúp kiểm soát luồng tải, không đảm bảo atomicity hoặc dữ liệu bền hơn.

### 15.2. Lợi ích và giới hạn của reactive

Reactive phù hợp pipeline I/O với số lượng request đồng thời lớn khi ứng dụng điều chỉnh tốt concurrency, timeouts và resource usage. Tuy nhiên:

- Một hot key vẫn gây contention/CAS conflict.
- GSI vẫn có độ trễ cập nhật.
- Cluster vẫn có failover/rebalance và ambiguous outcomes.
- Business invariant vẫn cần transaction/CAS hoặc workflow điều phối.

Không dùng “chuyển sang reactive” làm phương án sửa lỗi nhất quán nghiệp vụ.

## 16. Bảng quyết định nhanh

| Nếu yêu cầu là... | Công cụ nên xem xét đầu tiên | Điều không nên kỳ vọng |
|---|---|---|
| Cập nhật nhiều trường trong **một document** cùng lúc | Một KV mutation hoặc sub-document mutation | Cùng lúc sửa document khác |
| Không ghi đè phiên bản đã thay đổi | CAS/`@Version` | CAS bảo đảm GSI mới ngay |
| Nhiều document phải cùng commit | Couchbase Transactions | Tự bao gồm dịch vụ thanh toán ngoài |
| SQL++ thấy ghi vừa hoàn thành | `request_plus` hoặc `consistentWith(MutationState)` | Query trở thành transaction đa document |
| Đọc đúng document vừa ghi khi có ID | KV `get(id)` | Query theo field không còn cần index |
| Chịu được mất một Data node | Data replica và failover đúng điều kiện | Không cần backup hoặc durability |
| Ghi phải được xác nhận bền theo mục tiêu RPO | Durability level phù hợp | Miễn nhiễm lỗi logic/xóa nhầm |
| Retry POST tạo đơn không tạo trùng | ID/idempotency key, `insert` và kiểm tra trạng thái | Timeout luôn đồng nghĩa chưa ghi |
| Phục hồi sau xóa nhầm | Backup/restore, quyền và runbook | Replica tự trở về phiên bản cũ |
| Tăng throughput I/O | Reactive, connection pooling, tối ưu query, đo tải | Reactive tự sửa race condition |

## 17. Chẩn đoán các hiểu nhầm thường gặp

### 17.1. “Mutation đã atomic, sao bị hai đơn trùng?”

Một mutation document nguyên tử nhưng hai request có thể tạo **hai document ID khác nhau**. Kiểm tra thiết kế idempotency trước khi quy lỗi atomicity.

### 17.2. “Có CAS rồi sao màn hình danh sách chưa thấy đơn?”

CAS chỉ kiểm tra phiên bản khi cập nhật một document. Màn hình danh sách có thể dùng SQL++/GSI chưa bắt kịp; kiểm tra scan consistency và index lag.

### 17.3. “Có replica rồi sao mutation gần nhất biến mất sau node failure?”

Cần xác minh yêu cầu synchronous durability đã được đặt và thành công chưa, replica đủ điều kiện không, failover xảy ra thế nào và API có trả ambiguous outcome không. Data replica đơn thuần không chứng minh mọi ghi đã được xác nhận bền trước phản hồi.

### 17.4. “Đã bật request_plus, sao trạng thái kho vẫn sai?”

`request_plus` giúp query đọc chỉ mục mới theo mốc yêu cầu; nó không sửa **business logic hoặc race condition** ở khâu cập nhật tồn kho. Xem lại invariant, CAS hoặc transaction.

### 17.5. “Có transaction mà gateway thanh toán vẫn bị gọi hai lần?”

Transaction callback có thể retry; external side effect không thuộc transaction Couchbase. Cần idempotency ở gateway và workflow sau commit/outbox/saga.

### 17.6. “Có backup, vậy có thể bỏ replica?”

Backup/restore không thay thế khả năng phục vụ online khi Data node lỗi. Xác định RTO/RPO và availability trước khi thay đổi cấu hình replica.

## 18. Kiểm thử đúng từng thuộc tính

Nên có các thử nghiệm độc lập, thay vì chỉ một bài test end-to-end “save rồi find”.

| Tình huống test | Cách thực hiện | Kết quả cần xác minh |
|---|---|---|
| **Atomicity một document** | Mutation hai trường trong một thao tác, mô phỏng lỗi | Không xuất hiện trạng thái nửa thành công của mutation đơn |
| **CAS conflict** | Hai request cùng đọc CAS rồi thay đổi trạng thái | Một lần cập nhật dựa trên CAS cũ bị từ chối |
| **Multi-document transaction** | Thực hiện transaction có lỗi giữa chừng | Không xuất hiện commit một phần theo semantics transaction |
| **Business invariant** | Hai request cùng mua sản phẩm tồn kho=1 | Không chấp nhận hai lần cấp hàng trái invariant |
| **KV read-after-write** | Ghi rồi đọc đúng ID | Trạng thái phù hợp với write đã được xác nhận và không bị sửa khác |
| **SQL++ freshness** | Ghi KV rồi query ở các scan consistency | Quan sát khác biệt, không dùng sleep cố định để giả định index đã xong |
| **Data replica failure** | Diễn tập failover trong môi trường phù hợp | Đo availability, outcome, RTO/RPO |
| **Durability** | Chọn durability và giả lập lỗi theo kế hoạch | Xác minh ack/error và trạng thái sau recovery |
| **Ambiguous timeout** | Làm mất response sau mutation được server xử lý | Retry không tạo trùng nghiệp vụ |
| **External side effect** | Retry transaction callback/payment operation | Không gọi double charge thiếu idempotency |
| **Reactive resubscribe** | Tái subscribe pipeline mutation | Side effect được quản lý theo quy tắc |
| **Backup restore** | Khôi phục dữ liệu trong môi trường tách biệt | Đúng dữ liệu/quyền/index, đo RTO |

### 18.1. Metrics cần quan sát

- Tỷ lệ CAS conflict, duplicate insert và optimistic locking exception.
- KV mutation latency, timeout, ambiguous outcomes và durability failures.
- Query p95/p99 latency, index lag và thời gian chờ `request_plus`.
- Transaction commit/rollback/retry, thời gian transaction và conflict.
- Data replica health, failover/rebalance events và sức chứa N-1.
- Business metrics như đơn trùng, tồn kho âm, thanh toán lặp — kết quả cuối cùng quan trọng hơn một metric server riêng lẻ.

Tên metric/hành vi lỗi cụ thể có thể khác theo Couchbase Server, Capella, Java SDK và Spring Data version. Khi đo, phân biệt rõ **sự cố ở Data Service**, **SQL++/Index Service** và **logic nghiệp vụ**.

## 19. Bài tập thực hành

### Bài tập A — gọi tên ba thuộc tính

Một service cần:

1. Sửa `status` và `total` trong một document.
2. Khi Data node lỗi, giảm nguy cơ mất lần ghi đã xác nhận.
3. Sau khi lưu đơn, trang SQL++ thấy ngay đơn mới.

Hãy xác định lần lượt các yêu cầu về **atomicity**, **durability** và **query freshness**. Giải thích vì sao một tùy chọn CAS không giải quyết cả ba.

### Bài tập B — lost update không vi phạm atomicity đơn document

Hai request cùng đọc tồn kho=1, rồi cùng ghi 0 mà không dùng CAS. Hai mutation riêng đều nguyên tử, nhưng nghiệp vụ chấp nhận hai đơn. Vì sao? Hãy đề xuất CAS và quy tắc kiểm tra lại trạng thái.

### Bài tập C — nhiều document

Ứng dụng tạo đơn hàng, giảm tồn kho và ghi trạng thái thanh toán vào ba document Couchbase. Lệnh thứ ba lỗi sau khi hai lệnh đầu thành công. Đề xuất cách tổ chức transaction cho những mutation thuộc Couchbase, và nêu giới hạn khi cổng thanh toán nằm ngoài Couchbase.

### Bài tập D — durability level

So sánh `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` theo yêu cầu replicate/persist, latency và failure scenario. Vì sao vẫn cần backup?

### Bài tập E — KV vs SQL++

Sau `save(order)`, `findById(id)` thấy document nhưng `findByTenantIdAndStatus` chưa thấy. Giải thích cơ chế, đề xuất `request_plus`/MutationState hoặc đọc KV theo ID. Tại sao `@Version` không tự sửa vấn đề?

### Bài tập F — timeout ambiguous

Client gửi `insert(order::1001)`, nhận timeout, tạo ID `order::1002` rồi retry thành công. Phân tích rủi ro duplicate, thiết kế lại bằng idempotency key và cách xác minh trạng thái sau lỗi.

### Bài tập G — reactive callback

Một pipeline dùng `retryWhen` cho toàn bộ thao tác tạo đơn và gọi HTTP gateway. Những side effect nào có thể chạy hai lần? Hãy thiết kế lại sao cho mutation Couchbase, external payment và event publishing có semantics retry rõ ràng.

## 20. Checklist áp dụng vào dự án

- [ ] Định nghĩa **invariant nghiệp vụ** trước khi chọn CAS hay transaction.
- [ ] Phân biệt atomicity một document và nhiều document.
- [ ] Dùng `insert`/ID ổn định khi thao tác tạo mới phải idempotent.
- [ ] Dùng CAS/`@Version` cho read-modify-write có tranh chấp.
- [ ] Chỉ dùng transaction nhiều document khi thật sự cần; tránh side effect ngoài trong callback.
- [ ] Không giả định Spring `@Transactional` tự bao trùm Couchbase nếu chưa kiểm chứng transaction integration.
- [ ] Phân biệt KV theo ID với SQL++/GSI theo thuộc tính.
- [ ] Chọn scan consistency theo SLA độ mới: `not_bounded`, `request_plus` hoặc `consistentWith`.
- [ ] Xác định durability theo mục tiêu RPO, replica và loại bucket hỗ trợ.
- [ ] Có kế hoạch failover, N-1 capacity và backup/restore độc lập.
- [ ] Xử lý timeout ambiguous bằng kiểm tra trạng thái và idempotency.
- [ ] Với reactive, phân loại lỗi, giới hạn retry và tránh resubscribe side effect ngoài ý muốn.
- [ ] Đo CAS conflicts, transaction retries, query lag, durability failures và business duplicate.
- [ ] Đối chiếu hành vi Spring Data/Couchbase SDK/Couchbase Server theo phiên bản thực tế.

## 21. Tổng kết

**Atomicity** trả lời nhóm thay đổi nào phải cùng commit hoặc không commit; **consistency** trả lời dữ liệu đọc/ghi có thỏa invariant và độ mới yêu cầu không; **durability** trả lời một mutation đã được xác nhận phải tồn tại qua những loại lỗi nào. Trong Couchbase, một mutation trên **một document** có ranh giới nguyên tử riêng, CAS xử lý cập nhật cạnh tranh, còn **Couchbase Transactions** phục vụ yêu cầu nhiều document cùng một đơn vị giao dịch.

Đối với truy vấn, đọc KV theo ID và SQL++ qua GSI có đặc tính độ mới khác nhau: `not_bounded`, `request_plus` và `consistentWith(MutationState)` giải quyết yêu cầu chờ chỉ mục, **không** thay thế transaction hay durability. Replica và synchronous durability giúp xử lý các tình huống node lỗi, trong khi **idempotency** xử lý kết quả ghi không chắc chắn và **backup** phục vụ khôi phục ngoài phạm vi HA.

Khi lập trình **Spring Data Couchbase**, hãy xác định rõ boundary của từng repository/template operation, dùng `@Version` đúng mục đích, không suy diễn `@Transactional`/reactive thành bảo đảm mới nếu chưa cấu hình, và kiểm thử riêng atomicity, query consistency, durability lẫn retry. Một thiết kế đúng là thiết kế nói rõ **mất điều gì, chờ điều gì và khôi phục bằng cơ chế nào** trước khi hứa hẹn “ghi an toàn” với người dùng.
