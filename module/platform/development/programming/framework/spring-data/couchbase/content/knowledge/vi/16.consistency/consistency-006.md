# MutationState và nhất quán theo thay đổi tại lớp Java SDK

## 1. Vấn đề: đã ghi document nhưng query theo field chưa nhìn thấy

Trong ứng dụng **Spring Data Couchbase**, một luồng nghiệp vụ rất phổ biến là:

1. Ghi một Order document qua Key–Value (KV).
2. Ngay sau đó truy vấn SQL++ để tìm Order theo `customerId`.
3. Trả về danh sách mới nhất cho người dùng.

Lệnh KV có thể được xác nhận thành công trong khi **Global Secondary Index (GSI)** phục vụ SQL++ vẫn đang xử lý thay đổi. Nếu query chạy với scan consistency mặc định không buộc index bắt kịp, danh sách có thể tạm thời thiếu Order vừa tạo.

Couchbase Java SDK cung cấp **`MutationState`** để diễn đạt yêu cầu cụ thể hơn: *“Trước khi quét index, hãy bảo đảm index đã xử lý ít nhất các mutation mà tôi cung cấp dấu mốc.”* Thay vì yêu cầu đợi toàn bộ những thay đổi có trước query như `REQUEST_PLUS`, ứng dụng có thể yêu cầu query nhất quán với **các kết quả ghi đã biết**.

Bài học thuộc chương **Tính nhất quán** trong module **SPRING_DATA_COUCHBASE**. Sau bài, bạn cần:

- Phân biệt một **mutation**, **mutation token**, **MutationState** và **scan consistency**.
- Hiểu ý nghĩa cơ chế `AT_PLUS`/`consistentWith` khi truy vấn SQL++ qua index.
- Viết luồng SDK KV mutation → `MutationResult` → `MutationState` → query `consistentWith(state)`.
- Ghép dấu mốc của nhiều thao tác ghi theo đúng phạm vi và xử lý trường hợp không có token.
- So sánh `NOT_BOUNDED`, `REQUEST_PLUS` và consistency theo mutation với các trường hợp thực tế.
- Phối hợp Java SDK cùng Repository, `CouchbaseTemplate` và API reactive mà không nhầm các hợp đồng mapping.
- Thiết kế kiểm thử tích hợp, quan sát độ trễ, timeout và cơ chế fallback.
- Phân biệt vấn đề độ mới index với CAS, durability, TTL, transaction, Search consistency và idempotency.

**Ý chính:** `MutationState` là tập dấu mốc *độ tiến của những mutation được quan sát*, không phải snapshot lịch sử, không phải một transaction và cũng không phải cơ chế khóa document.

## 2. Khung ví dụ xuyên suốt: tạo hai đơn rồi mở lịch sử

Giả sử ứng dụng có:

~~~text
Bucket: shop
Scope: sales
Collection: orders

Order A:
  document ID = order::o-1001
  customerId  = c-1001
  status      = CREATED

Order B:
  document ID = order::o-1002
  customerId  = c-1001
  status      = CREATED
~~~

Body JSON của mỗi Order:

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T08:00:00Z",
  "totalVnd": 250000
}
~~~

Màn hình lịch sử truy vấn theo `customerId`:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Vì không biết toàn bộ Order ID từ trước, query cần tìm theo field và thường phụ thuộc secondary index. Một index khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Nếu ứng dụng vừa ghi **A và B**, nó không nhất thiết cần index bắt kịp mọi mutation của các request khác trên cluster. Nó cần biết index đã đi qua **đúng các mutation của A và B** trước khi query, miễn hai document vẫn phù hợp `WHERE` và `LIMIT`.

~~~mermaid
flowchart TD
    A["SDK KV insert Order A"] --> TA["MutationResult A"]
    B["SDK KV insert Order B"] --> TB["MutationResult B"]
    TA --> MS["MutationState chứa mốc A và B"]
    TB --> MS
    MS --> QUERY["SQL++ query với consistentWith(state)"]
    QUERY --> INDEX[("Index Service bắt kịp các mốc yêu cầu")]
    INDEX --> ROWS["Kết quả lịch sử theo dữ liệu đủ mới"]
~~~

Sơ đồ biểu diễn **mục tiêu nhất quán theo mutation**, không cam kết thứ tự row hay việc kết quả phải chứa mọi document: query vẫn có điều kiện lọc, giới hạn, quyền và các mutation đồng thời khác.

## 3. Phân biệt dữ liệu nguồn, index và dấu mốc mutation

### 3.1. Dữ liệu nguồn trong Data Service

Document nằm ở bucket/scope/collection với một metadata key. Ví dụ:

~~~text
shop.sales.orders
  key: order::o-1001
  body:
    customerId: c-1001
    status: CREATED
~~~

Thao tác `collection.insert`, `upsert`, `replace` hoặc `remove` thay đổi dữ liệu nguồn theo các semantics tương ứng. Sau khi SDK nhận xác nhận mutation, việc KV đọc theo ID trên active path của cùng keyspace không cần secondary index để định vị document.

### 3.2. Secondary index trong Index Service

Một index theo `customerId` duy trì cấu trúc tra cứu những document phù hợp. Dịch vụ index xử lý thay đổi được truyền từ dữ liệu nguồn; tại một thời điểm, index có thể **chưa theo kịp mutation mới nhất**.

### 3.3. Mutation token là dấu mốc

Couchbase có cơ chế chia dữ liệu thành các partition/vBucket. Một mutation token do SDK nhận được mô tả vị trí tiến của thay đổi đối với partition liên quan, với thông tin như bucket, partition/vBucket ID, định danh thế hệ partition và sequence number.

Nó **không** biểu diễn một bản sao JSON, không mang đầy đủ nội dung document, không phải timestamp của laptop và không phải CAS dùng để kiểm tra optimistic locking.

### 3.4. MutationState gom dấu mốc cần đợi

`MutationState` là cấu trúc SDK dùng để mang các token tương ứng những mutation mà query cần xem là đã được index phản ánh. Query `consistentWith(state)` chuyển ý định này thành yêu cầu scan consistency theo mutation (thường được mô tả là `AT_PLUS`).

**Quan trọng:** không hiểu việc mang nhiều token là “đợi index quét tất cả partition tới cùng một số thứ tự toàn cục”. Mốc mutation phụ thuộc partition; mỗi token cần được hiểu trong ngữ cảnh partition/đời vBucket và keyspace mà SDK/Server hỗ trợ.

## 4. Ba sự kiện xảy ra tại những thời điểm khác nhau

Một timeline minh họa:

~~~text
T0: Client gửi upsert Order A
T1: Data Service xác nhận mutation A
T2: SDK nhận MutationResult A (+ token nếu được cung cấp)
T3: Client KV get Order A -> thấy document
T4: Index Service vẫn đang xử lý mutation trước A
T5: SQL++ với NOT_BOUNDED -> có thể chưa thấy A
T6: Client SQL++ consistentWith(MutationState(A))
T7: Query Service đợi index đạt ít nhất mốc A
T8: SQL++ scan và trả kết quả theo trạng thái/query plan hiện hành
~~~

Không coi T4–T8 là các khoảng thời gian cố định. Trên môi trường ít tải, index có thể đã theo kịp A ngay tại T2. Khi Index Service backlog, `consistentWith` có thể làm query **chờ lâu hoặc timeout**.

Một query không có Order A có thể do nhiều nguyên nhân ngoài index lag: document đã bị xóa, `WHERE` không khớp, `LIMIT` loại A, scope/collection sai, quyền tenant loại A hoặc query thực tế chọn index khác. Chờ index đủ mới **không sửa lỗi nghiệp vụ hay query plan**.

## 5. MutationResult và mutationToken() trong Couchbase Java SDK

Với Java SDK 3.x, nhiều KV mutation trả về một `MutationResult`. Kết quả có thể cung cấp một **optional mutation token**; vì optional nên ứng dụng không nên mặc định token luôn tồn tại trong mọi hoàn cảnh.

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.json.JsonObject;

public class OrderWriteGateway {
    private final Collection collection;

    public OrderWriteGateway(Collection collection) {
        this.collection = collection;
    }

    public MutationResult insertNew(
            String id, String customerId) {

        JsonObject body = JsonObject.create()
                .put("customerId", customerId)
                .put("status", "CREATED");

        return collection.insert(id, body);
    }
}
~~~

Khi dùng SDK trực tiếp, cần chuẩn bị Collection chính xác:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;

Collection orders = cluster.bucket("shop")
        .scope("sales")
        .collection("orders");
~~~

**Dùng lại `Cluster`/`Bucket`/`Collection` do ứng dụng quản lý**, không tạo kết nối mới cho từng request. Tài khoản phải có quyền KV mutation và SQL++ Query phù hợp.

### 5.1. Kiểm tra token có được cấp hay không

~~~java
MutationResult mutation = orders.insert(id, body);

if (mutation.mutationToken().isPresent()) {
    // SDK đã nhận metadata token; có thể dùng cho MutationState.
} else {
    // Không có token: chọn fallback có chủ đích.
}
~~~

Những nguyên nhân/token availability phụ thuộc SDK, Server, tùy chọn và dạng thao tác. Nếu không có token, **không tự chế** token từ ID, CAS, thời gian máy hay sequence do ứng dụng tự tăng.

### 5.2. Kết quả mutation không đồng nghĩa kết quả Query

`MutationResult` là kết quả của KV mutation. `QueryResult` là kết quả SQL++ query. Tách hai loại giúp tránh thiết kế method `save` vừa ghi, vừa lén query toàn bộ lịch sử chỉ để có dữ liệu trả về.

## 6. Luồng chuẩn: từ MutationResult đến MutationState rồi consistentWith

Cách sử dụng cốt lõi của Java SDK là tạo một `MutationState` từ mutation result và truyền state vào query options.

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryResult;

public class OrderReadYourWritesGateway {
    private final Cluster cluster;
    private final Collection orders;

    public OrderReadYourWritesGateway(Cluster cluster) {
        this.cluster = cluster;
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public QueryResult createAndFind(
            String documentId, String customerId) {

        JsonObject payload = JsonObject.create()
                .put("customerId", customerId)
                .put("status", "CREATED");

        // Bước 1: mutation KV được xác nhận.
        MutationResult write = orders.insert(documentId, payload);

        // Bước 2: state mô tả mutation vừa ghi.
        MutationState state = MutationState.from(write);

        // Bước 3: SQL++ chỉ bắt đầu scan khi index đã đủ mới.
        String sql = """
            SELECT META(o).id AS documentId, o.customerId, o.status
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            """;

        return cluster.query(
                sql,
                queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", customerId))
                        .consistentWith(state));
    }
}
~~~

Đoạn mã minh họa **API Java SDK 3.x**, phải xác minh chữ ký `MutationState.from(MutationResult)`, cấu hình token availability, và phiên bản client/server đang dùng trước khi triển khai. Nếu token không sẵn có, một luồng production cần xử lý fallback rõ thay vì coi query đã có consistency theo mutation.

Để gọi với ID ví dụ:

~~~java
QueryResult result = gateway.createAndFind(
        "order::o-1001",
        "c-1001");
~~~

**Điểm quan trọng về semantics:**

- `insert` tạo document mới; nếu key đã tồn tại, cần xử lý conflict, không chuyển tự động sang `upsert` để “tránh lỗi” mà không xét idempotency.
- `MutationState.from(write)` diễn đạt dấu mốc của write đã biết.
- `consistentWith(state)` yêu cầu Query Service/Index Service đáp ứng mốc đó trước khi scan, không ép query trả trạng thái JSON y hệt lúc insert.
- Query parameter được binding qua `JsonObject`, không nối input trực tiếp thành chuỗi SQL++.
- Muốn kiểm tra Order cụ thể vừa tạo, **đọc theo ID hoặc trả saved result** có thể đơn giản hơn nhiều so với query qua index.

## 7. Phân biệt AT_PLUS, REQUEST_PLUS và NOT_BOUNDED

Ba cách đọc có mục tiêu khác nhau:

| Chính sách | Query cần chờ gì? | Cần token từ ứng dụng? | Đánh đổi |
| --- | --- | --- | --- |
| `NOT_BOUNDED` | Không đòi index bắt kịp mutation mới trước scan | Không | Thường giảm thời gian chờ, có thể đọc chưa mới |
| `REQUEST_PLUS` | Đợi index liên quan bắt kịp mốc của query/request theo semantics server | Không | Có thể chờ mutation từ nhiều nguồn, tăng latency |
| `AT_PLUS` / `consistentWith(state)` | Đợi index đạt mốc của **những mutation token đã biết** | Có | Kiểm soát read-your-writes tinh hơn, cần giữ state |

### 7.1. Đặt NOT_BOUNDED trong SDK

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

cluster.query(sql,
        queryOptions()
                .parameters(params)
                .scanConsistency(
                        QueryScanConsistency.NOT_BOUNDED));
~~~

### 7.2. Đặt REQUEST_PLUS trong SDK

~~~java
cluster.query(sql,
        queryOptions()
                .parameters(params)
                .scanConsistency(
                        QueryScanConsistency.REQUEST_PLUS));
~~~

### 7.3. Đặt AT_PLUS theo mutation state

~~~java
cluster.query(sql,
        queryOptions()
                .parameters(params)
                .consistentWith(state));
~~~

Biến `sql`, `params`, `state` trong các snippet trên là đầu vào đã được tạo từ ngữ cảnh thích hợp.

**Không kết hợp** `scanConsistency(REQUEST_PLUS)` và `consistentWith(state)` trên cùng query options rồi suy đoán cách ưu tiên. Hãy chọn **một policy minh bạch** ở ranh giới truy vấn. Nếu ứng dụng có code path fallback, chọn nhánh riêng, mỗi nhánh xây `QueryOptions` tương ứng.

### 7.4. Vì sao AT_PLUS có thể ít tốn chờ hơn REQUEST_PLUS?

Nếu cluster có nhiều luồng ghi không liên quan đến request hiện tại, `REQUEST_PLUS` yêu cầu index đạt mốc request rộng hơn. `consistentWith(state)` tập trung vào những partition/mutation đã được nêu trong state. Trong một số workload, nó **có thể** chờ ít hơn. Tuy nhiên, không cam kết AT_PLUS luôn nhanh hơn: nó còn phụ thuộc partition, index lag, trạng thái cluster, query plan và số token.

### 7.5. Không dùng các tên policy lẫn nhau

`AT_PLUS` là tên khái niệm/cấp query protocol cho tính nhất quán theo mutation vector. Java SDK thường phơi bày cách dễ dùng hơn là **`QueryOptions.consistentWith(MutationState)`**, không phải việc tự truyền một chuỗi `"AT_PLUS"` kèm token tự chế.

## 8. Gom nhiều mutation: hai Order trong cùng một luồng

Giả sử một request tạo Order A và Order B rồi query danh sách cả hai. Một token chỉ mô tả mutation A **không mặc nhiên** bảo đảm query đã thấy mutation B.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant S as Order Service
    participant KV as Data Service
    participant IDX as Index Service
    participant Q as Query Service
    S->>KV: insert Order A
    KV-->>S: MutationResult A
    S->>KV: insert Order B
    KV-->>S: MutationResult B
    Note over S: Gộp state từ A và B
    S->>Q: SQL++ consistentWith(state)
    Q->>IDX: Chờ các partition/mốc được chỉ định
    IDX-->>Q: Đã đạt mốc
    Q-->>S: Query result
~~~

Một ví dụ gộp state ở mức ý tưởng:

~~~java
// Minh họa logic; kiểm tra overload/API chính xác theo SDK version.
MutationResult a = orders.insert(idA, bodyA);
MutationResult b = orders.insert(idB, bodyB);

// State phải bao gồm CẢ HAI mutation.
MutationState state = MutationState.from(a, b);

QueryResult result = cluster.query(
        sql,
        queryOptions()
                .parameters(params)
                .consistentWith(state));
~~~

Dấu mốc của những mutation xảy ra trên **cùng partition** có thể được biểu diễn bằng tiến độ cao nhất liên quan partition đó trong mutation state. Ở các partition khác nhau, cần các mốc tương ứng. SDK chịu trách nhiệm cấu trúc, còn người dùng phải chắc chắn **đã đưa mọi mutation cần thiết vào state**.

### 8.1. Không cần gom token của mọi mutation trên cluster

Nếu bạn đang tạo hai Order, không có lý do mặc định để thu thập token của hàng nghìn request khác. Việc gom token phải theo đúng **tính nhất quán mong muốn của nghiệp vụ**. Đối với yêu cầu dữ liệu “mới nhất trên phạm vi rộng” mà không có state, `REQUEST_PLUS` có thể đơn giản hơn.

### 8.2. Query theo nhiều keyspace

Một SQL++ query có thể truy cập nhiều collection hoặc JOIN nhiều loại document. Nếu yêu cầu của business là “đọc sau các mutation trên nhiều collection”, cần xác nhận tính tương thích **MutationState, bucket/collection, query context và giới hạn SDK/Server**. Không giả định token của một bucket bất kỳ đủ để thiết lập consistency cho mọi index ở bucket khác.

Một cách an toàn là diễn đạt chính xác tập mutation nào cần quan sát, xây state qua các kết quả ghi được hỗ trợ, và kiểm thử query thực tế trên đúng keyspace.

## 9. Khi token không có: cần fallback rõ ràng

Một chương trình chạy tốt trên happy path chưa đủ để vận hành. Nếu `MutationResult.mutationToken()` trống hoặc SDK không tạo được state hợp lệ, có những lựa chọn:

| Mục tiêu | Fallback hợp lý | Điều cần tránh |
| --- | --- | --- |
| Xem đúng document vừa ghi | Trả giá trị đã ghi hoặc đọc KV theo ID | Query theo field rồi kết luận không có |
| SQL++ cần index mới đến mốc request | `REQUEST_PLUS` nếu API/Server hỗ trợ | Âm thầm hạ xuống NOT_BOUNDED |
| Danh sách chỉ cần gần đúng | `NOT_BOUNDED` với SLO chấp nhận lag | Giả vờ đã bảo đảm read-your-writes |
| Đòi hỏi nhất quán đặc thù không thể đáp ứng | Trả lỗi rõ hoặc đổi luồng nghiệp vụ | Tạo token giả từ thời gian máy |
| Ghi bị timeout, trạng thái chưa rõ | Kiểm tra trạng thái theo key/idempotency | Tạo ID mới rồi retry không kiểm soát |

Mẫu điều khiển chính sách có thể viết như sau:

~~~java
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

// Pseudocode logic: mutationResult, state và các biến được khởi tạo
// theo API đang sử dụng.

QueryOptions options;
if (mutationResult.mutationToken().isPresent()) {
    options = QueryOptions.queryOptions()
            .consistentWith(state);
} else {
    // Nếu SLO bắt buộc index đủ mới, dùng REQUEST_PLUS rõ ràng.
    options = QueryOptions.queryOptions()
            .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
}
~~~

Trên luồng thực, hãy xây `state` **chỉ khi kết quả có token theo điều kiện API**, không gọi factory rồi mới kiểm tra token. Mỗi nhánh cũng cần `parameters(...)`, timeout và các options khác giống nhau khi áp dụng vào cùng câu SQL++.

### 9.1. Đừng thay fallback thành sleep cố định

~~~java
Thread.sleep(200); // Không chứng minh index đã bắt kịp mutation.
~~~

Đợi 200 ms hoặc 1 giây có thể hoạt động ở dev nhưng thất bại khi tải tăng. Nếu nghiệp vụ cần bảo đảm mốc, hãy dùng consistency option của Couchbase thay vì đoán số mili giây cần sleep.

### 9.2. Không lấy CAS làm mutation token

`MutationResult.cas()` là giá trị dùng cho optimistic concurrency. Nó không thay thế `mutationToken()`; truyền CAS vào công cụ tự xây “token” sẽ không có semantics mà Index Service hiểu.

## 10. Metadata token: giới hạn vòng đời và hiểu lầm thường gặp

Thông thường một mutation token mang **định danh bucket, vBucket/partition, partition UUID và sequence number**. Những thành phần này giúp hệ thống phân biệt tiến độ của một partition với partition khác, bao gồm thế hệ khác nhau sau sự kiện topology.

Không nên:

- Chuyển một token thành số nguyên toàn cục rồi so sánh token của mọi partition.
- Dùng timestamp client để “tính lại” sequence.
- Coi token là khóa chính của document.
- Giả định token có thể lưu hàng năm rồi áp vào mọi topology/failover mà không kiểm chứng.
- Thay thế log nghiệp vụ/audit bằng token.
- Gắn một token của Order A vào mọi query khác mà không xác định mốc consistency thực sự cần.

### 10.1. Token thuộc ngữ cảnh mutation đã ghi

Một token phản ánh một mutation được SDK xác nhận; nó không chứa mã Java của service, request HTTP hoặc đối tượng domain. Nếu muốn gắn orderId/customerId để truy vết, ứng dụng phải lưu/correlate chúng ở tầng riêng với chính sách log an toàn.

### 10.2. State là ràng buộc độ tiến, không phải snapshot

Giả sử:

~~~text
T0: SDK upsert Order A với status=CREATED
T1: Nhận token A
T2: Một worker khác cập nhật Order A thành CONFIRMED
T3: Query consistentWith(token A)
~~~

Query ở T3 có thể thấy `CONFIRMED` nếu index đã xử lý mutation T2. `consistentWith` **không có nghĩa “đọc lại đúng JSON tại T0”**.

Tương tự, nếu Order A đã bị xóa trước query và index phản ánh xóa, query không phải trả Order A chỉ vì token của lần insert đã được cung cấp.

## 11. Khác biệt với CAS và @Version của Spring Data

Cả CAS và mutation token đều gắn với một hoạt động ghi, nhưng dùng cho hai mục tiêu hoàn toàn khác.

| Thuộc tính | CAS / `@Version` | Mutation token / `MutationState` |
| --- | --- | --- |
| Mục đích | Kiểm tra document đã thay đổi trước khi ghi không | Đợi index xử lý tới mốc mutation đã biết |
| Nơi dùng | KV replace/remove/conditional update | SQL++ query scan consistency |
| Quy mô | Điều kiện concurrency của document | Mốc tiến theo partition/mutation |
| Giúp ngăn lost update | Có, khi dùng đúng | Không |
| Giúp query theo field nhìn thấy mutation mới | Không trực tiếp | Có, trong phạm vi query/SDK hỗ trợ |
| Có phải transaction? | Không | Không |
| Tái tạo snapshot lịch sử | Không | Không |

Ví dụ cạnh tranh ghi:

~~~text
A KV get Order, CAS=C1
B KV get Order, CAS=C1
A replace với CAS=C1 -> thành công, CAS mới=C2
B replace với CAS=C1 -> conflict
~~~

Nếu B trước đó đã chạy một SQL++ query `consistentWith(state)`, điều đó **không tự bảo vệ** lệnh replace của B. Muốn an toàn khi nhiều request sửa một document, dùng CAS hoặc cơ chế ghi có điều kiện của database.

Với Spring Data Couchbase, `@Version` được ánh xạ vào CAS để hỗ trợ optimistic locking trên entity. Không cố dùng field `version` tự tăng trong JSON như bản sao của mutation sequence.

## 12. Durability và MutationState cũng khác nhau

**Durability** trả lời: mutation đã đạt yêu cầu về ghi bền/nhân bản như thế nào trước khi client nhận xác nhận?

**MutationState** trả lời: trước khi query quét secondary index, index đã theo kịp những mutation đã biết chưa?

Một write với durability cao hơn vẫn có thể được xác nhận khi secondary index chưa xử lý xong. Một query `consistentWith(state)` có thể chờ index đủ mới nhưng không tăng mức durability của write quá khứ.

~~~text
KV mutation
  |-- durability option: điều kiện xác nhận ghi
  |
  +--> MutationResult (+ optional mutation token)
         |
         v
      MutationState
         |
         v
  SQL++ query consistentWith
  |-- scan consistency: index đã đủ mới chưa?
~~~

Vì hai mục tiêu khác nhau, hệ thống quan trọng có thể cần **cả durability và scan consistency**. Không xem việc bật một thứ là đã giải quyết toàn bộ bảo đảm dữ liệu.

## 13. Transaction, nhiều document và tính nhất quán

Một nghiệp vụ đặt hàng có thể cần:

~~~text
1. Tạo Order document
2. Trừ Inventory document
3. Ghi PaymentIntent document
4. Query danh sách đơn của khách
~~~

Nếu 1–3 phải cùng thành công/thất bại, không thể chỉ gom ba token thành `MutationState` rồi cho rằng các thao tác ghi đã trở thành một transaction. State chỉ là thông tin **phục vụ độ mới của query**.

Couchbase có transaction đa document trong những phiên bản hỗ trợ. Khi dùng transaction:

- Phải dùng transaction context/API phù hợp cho mọi mutation có liên quan.
- Tìm hiểu read-your-writes **bên trong transaction** và visibility **sau commit** theo semantics riêng.
- Không giả định transaction trả mutation token cùng cách với các KV mutation thông thường.
- Bên ngoài transaction, query qua index vẫn phải áp dụng policy consistency phù hợp.
- External payment API nằm ngoài transaction database; cần idempotency/saga/outbox tùy nghiệp vụ.

**Quan trọng:** Một truy vấn `consistentWith` sau các mutation độc lập đã ghi thành công không làm “rollback” một mutation nếu mutation khác thất bại.

## 14. Spring Data Repository và CouchbaseTemplate: vì sao cần lớp Java SDK?

Spring Data Couchbase tiện cho mapping entity và CRUD:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);
}
~~~

Ví dụ:

~~~java
OrderDocument saved = repository.save(order);
List<OrderDocument> history =
        repository.findByCustomerId(saved.getCustomerId());
~~~

Đường query thứ hai có thể đi SQL++/index, nhưng **Repository.save** thường trả entity được mapping, **không nhất thiết cung cấp MutationResult/token trực tiếp** cho caller. Vì vậy, để điều khiển nhất quán theo token một cách rõ ràng, có thể xây **SDK gateway** chuyên biệt cho luồng cần đặc tính này.

### 14.1. Lựa chọn tại tầng Spring Data

Nếu không có token, một derived query có thể dùng annotation scan consistency khi phiên bản hỗ trợ:

~~~java
import org.springframework.data.couchbase.repository.ScanConsistency;
import com.couchbase.client.java.query.QueryScanConsistency;

@ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
List<OrderDocument> findByCustomerId(String customerId);
~~~

Với `CouchbaseTemplate`, có thể dùng mức consistency phù hợp cho một SQL++ query:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;

// Query object đã được tạo theo criteria thực tế.
template.findByQuery(OrderDocument.class)
        .withConsistency(QueryScanConsistency.REQUEST_PLUS)
        .matching(query)
        .all();
~~~

Hai cách trên thường dùng **REQUEST_PLUS**, không tương đương việc truyền `MutationState`. Không tự gán một annotation tĩnh rồi khẳng định nó nắm được token động của request.

### 14.2. SDK gateway và mapping không tự đồng bộ

Nếu SDK `orders.upsert(id, json)` ghi một JSON body thô, nó **không tự thực thi** mọi annotation/converter của Spring Data. Ví dụ Spring Data có thể ghi type discriminator hoặc field naming convention khác. Nếu code path SDK và Repository trỏ cùng collection nhưng lưu JSON khác format, một derived query có thể loại document vì type filter.

Cần thống nhất:

- Bucket, scope, collection và tiền tố document ID.
- Tên/kiểu dữ liệu field JSON và type discriminator nếu có.
- TTL/expiry khi ghi lại document.
- CAS/version handling khi cập nhật từ hai API.
- Durability, timeout, quyền, tenant filter và error mapping.
- Cách áp dụng schema evolution/custom converter.

**Đừng dùng SDK raw upsert trên entity có `@Version`** mà không xem xét làm mất dữ liệu hoặc vô hiệu hóa optimistic locking của code path Repository.

## 15. Reactive Java SDK: nối mutation và query đúng thứ tự

Couchbase Java SDK có reactive API. Trong hệ thống Spring WebFlux, nên giữ pipeline non-blocking nếu workload đòi hỏi.

Ý tưởng cơ bản:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryOptions;
import reactor.core.publisher.Flux;

public class ReactiveOrderGateway {
    private final Cluster cluster;
    private final Collection orders;

    public ReactiveOrderGateway(Cluster cluster) {
        this.cluster = cluster;
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public Flux<JsonObject> insertThenFind(
            String id, String customerId) {

        JsonObject body = JsonObject.create()
                .put("customerId", customerId)
                .put("status", "CREATED");

        String sql = """
            SELECT META(o).id AS documentId, o.customerId, o.status
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            """;

        return orders.reactive()
                .insert(id, body)
                .flatMap(write -> {
                    MutationState state = MutationState.from(write);
                    return cluster.reactive().query(
                            sql,
                            QueryOptions.queryOptions()
                                    .parameters(JsonObject.create()
                                            .put("customerId", customerId))
                                    .consistentWith(state));
                })
                .flatMapMany(result -> result.rowsAsObject());
    }
}
~~~

Đây là ví dụ mô hình SDK reactive cần đối chiếu API/phiên bản và token availability trước khi dùng production. `flatMap` bảo đảm query được tạo/chạy sau khi Publisher insert đã phát kết quả ghi; `flatMapMany` mở dòng rows.

### 15.1. Những lỗi dễ gặp

~~~java
// Sai: gọi blocking SDK trước rồi mới bọc kết quả.
Mono.just(orders.insert(id, body));

// Sai: chặn event loop khi đã dùng SDK reactive.
orders.reactive().get(id).block();

// Không nên fire-and-forget trong service rồi trả HTTP thành công ngay.
orders.reactive().insert(id, body).subscribe();
~~~

Với WebFlux, hãy **trả Publisher** cho tầng framework hoặc compose tiếp, không tự subscribe rồi bỏ qua lifecycle/error. Nếu token không có, phải quyết định fallback/cách phản hồi thay vì làm rơi consistency requirement.

### 15.2. Reactive không thay đổi tính đúng đắn index

Reactive `Mono`/`Flux` giúp điều phối I/O và concurrency, nhưng không khiến secondary index được cập nhật ngay. `consistentWith(state)` vẫn có thể phải chờ Index Service. Quản lý timeout, cancellation và backpressure riêng với yêu cầu scan consistency.

## 16. Đọc sau ghi trong hai HTTP request độc lập

Giả sử:

~~~text
POST /orders
  -> SDK insert Order
  -> trả 201 + Order ID

GET /customers/c-1001/orders
  -> SQL++ query lịch sử
~~~

`GET` là một request HTTP mới. Nó không tự biết mutation token của `POST`, trừ khi ứng dụng có cách truyền hoặc lưu giữ dấu mốc đúng.

Có vài thiết kế:

1. **Hiển thị kết quả vừa tạo từ POST:** trang xác nhận nhận Order ID và biểu diễn đã lưu; không cần query index.
2. **GET detail theo ID:** dùng KV để đọc chính Order vừa ghi.
3. **GET history yêu cầu index đủ mới:** có thể dùng `REQUEST_PLUS` tại query, không cần token từ POST.
4. **Truyền mutation state qua ranh giới request:** chỉ cân nhắc nếu có thiết kế truyền/ủy quyền/bảo vệ token và compatibility rõ; không tự serialize nội bộ state thành một query parameter không xác thực.

### 16.1. Vì sao không nên gửi mutation token tùy tiện lên frontend?

Token/state là metadata nội bộ về tiến độ mutation. Dù không phải mật khẩu, việc công khai token có thể làm tăng coupling với SDK/cluster topology và tạo nguy cơ client yêu cầu các mốc không phù hợp, gây timeout/tải. Nếu cần thiết kế “session read-your-writes” qua nhiều request, nên dùng **opaque consistency handle** do server kiểm soát, TTL, validation, authorization và giới hạn tài nguyên. Không coi việc giữ state trong web browser là yêu cầu mặc định.

### 16.2. Yêu cầu phía UI đôi khi giải quyết được mà không cần token

Một UI có thể cập nhật danh sách cục bộ từ response POST và đồng thời refresh query nền. Khi làm vậy, cần tránh hiển thị status cuối cùng sai nếu thanh toán chưa được xác nhận; trả về trạng thái domain đã commit, không bịa kết quả từ client.

## 17. Hiệu năng: chi phí đợi index và lựa chọn policy

Dù `AT_PLUS`/`consistentWith` có thể hạn chế phạm vi mutation cần đợi, nó vẫn có thể tăng độ trễ so với query `NOT_BOUNDED`.

~~~text
SQL++ query total latency
  = SDK/network
  + Query Service planning
  + chờ index đạt consistency yêu cầu
  + index scan/fetch/filter/sort/project
  + truyền và decode rows
~~~

Nếu Index Service đang backlog hoặc index đang phục hồi/rebalance, phần chờ có thể lớn và chạm timeout. Một token mới trên partition có lag nhiều có thể khiến query phải đợi lâu, ngay cả khi những partition khác đã bắt kịp.

### 17.1. Ma trận lựa chọn dựa trên SLA

| Nhu cầu | Cách thường phù hợp | Rủi ro phải đo |
| --- | --- | --- |
| Một document vừa lưu, đã biết key | Trả saved entity/KV get | KV latency, read path |
| Báo cáo cho phép độ trễ nhỏ | SQL++ NOT_BOUNDED | Freshness lag |
| Danh sách ngay sau ghi, không giữ token | SQL++ REQUEST_PLUS | Wait latency, timeout |
| Query phải thấy các mutation mà application đã ghi | MutationState/consistentWith | Token availability, index lag |
| Dữ liệu nhiều cluster hoặc Search/FTS | Consistency riêng từng hệ thống | Replication/Search index delay |
| Ghi cạnh tranh có bất biến nghiêm ngặt | CAS/transaction/idempotency | Conflict, retry, correctness |

### 17.2. Đừng bỏ qua query plan

`consistentWith` không chữa được một index thiếu, một `WHERE` sai hay sorting tốn kém. Hãy kiểm tra `EXPLAIN` và đo query plan trước khi thay policy. Một query với `LIMIT 20` vẫn có thể có chi phí cao nếu cần sort/scan nhiều document.

### 17.3. Mỗi lần query nên chọn một cơ chế có chủ đích

Nếu code có một boolean tên `fresh` mà lúc thì bật `REQUEST_PLUS`, lúc thì truyền mutation token, rất khó phân biệt semantics. Nên đặt policy có ý nghĩa:

~~~java
public enum ReadFreshness {
    ACCEPT_INDEX_LAG,
    WAIT_FOR_REQUEST_BOUNDARY,
    CONSISTENT_WITH_MY_MUTATIONS
}
~~~

Tại persistence boundary, định nghĩa rõ nhánh nào cần `MutationState`, nhánh nào dùng `REQUEST_PLUS` và nhánh nào không đợi index. Khi không có token, fallback phải được quyết định bởi **SLO/contract**, không âm thầm hạ cấp.

## 18. Timeout, retry và kết quả ghi chưa rõ

Một lỗi quan trọng nằm ở lệnh **ghi**, không phải ở query.

~~~text
T0: SDK insert Order A gửi tới Couchbase
T1: Server có thể đã ghi thành công
T2: Network timeout trước khi client nhận MutationResult
T3: Application không biết mutation đã commit hay chưa
T4: Nếu retry với ID mới -> có thể tạo trùng Order
~~~

Không có `MutationResult` có nghĩa application cũng không có mutation token tin cậy từ lần ghi ấy. Nhưng **không được suy luận rằng document chưa tồn tại**.

Các phương án:

- Dùng **idempotency key** ổn định cho một yêu cầu đặt hàng.
- Tra cứu trạng thái theo key có thẩm quyền trước khi retry.
- Nếu create có thể chạy lại an toàn, sử dụng conditional insert và xử lý duplicate key theo domain.
- Không tự nhân đôi payment API/email/side effect khi retry.
- Với một query consistent-with bị timeout, phân biệt query chưa hoàn tất với KV mutation đã hoàn tất; đừng gửi lại mutation chỉ vì query không trả kết quả kịp.

### 18.1. Retry ở query không phải thay thế một consistency option

Lặp một query `NOT_BOUNDED` cho đến khi thấy row là **polling**. Nếu có giới hạn timeout và chấp nhận eventual consistency, polling có thể là một phương án UI hợp lệ; nhưng nó không mang cùng bảo đảm/semantics như một query `consistentWith(state)`. Không dùng polling không giới hạn trên đường nghiệp vụ quan trọng.

### 18.2. Không bịa thời gian chờ bằng sleep

~~~java
Thread.sleep(500); // Không có chứng cứ index đã xử lý mutation.
~~~

Độ trễ index biến thiên theo tải và trạng thái cluster. Một hằng số được chọn ở môi trường dev không phải hợp đồng consistency.

## 19. TTL, delete và Search: các trường hợp dễ nhầm

### 19.1. Delete có thể tạo token phục vụ đọc sau xóa

Một KV remove có thể trả mutation result/token theo API. Về mặt khái niệm, query consistent-with token xóa có thể đợi index phản ánh removal, từ đó giảm nguy cơ quét một entry stale. Nhưng kết quả SQL++ thực tế còn phụ thuộc query plan, việc fetch document nguồn và các mutation sau đó.

Không coi một query SQL++ không có row là bằng chứng duy nhất của việc xóa đã thành công khi `remove` bị timeout; phải xác minh ở đường ghi/KV.

### 19.2. TTL không tương đương mutation state

Session document có expiry. Việc đến hạn không phải một timestamp do application tự ghi vào JSON để `MutationState` tự tính. TTL là metadata/database behavior; query index có thể có độ trễ phản ánh expiry theo cơ chế riêng. Khi xác thực session, dùng key/expiry/revocation thay vì query Search hoặc index liệt kê session.

### 19.3. Search/FTS có consistency khác SQL++

Search index có pipeline cập nhật riêng và query semantics riêng. `QueryOptions.consistentWith(state)` trong bài này là **cho SQL++**; không bê nguyên option đó sang Search API rồi cho rằng Search Service sẽ xử lý giống hệt. Nếu sử dụng Search, xác minh API consistency của Search phiên bản đang chạy.

### 19.4. Replica và cross-region

MutationState để điều phối một SQL++ query/index ở cluster phù hợp **không** tự bảo đảm dữ liệu ở một cluster/region khác đã được đồng bộ qua XDCR hay cơ chế replication riêng. Cần thiết kế freshness và failover semantics theo topology thực tế.

## 20. Integration test: chứng minh read-your-writes theo token

Test này cần Couchbase Server hoặc môi trường tương đương, đúng bucket/scope/collection, index đã online và phiên bản SDK hỗ trợ mutation token. Mock Repository không thể chứng minh index bắt kịp.

### 20.1. Ý tưởng test

1. Tạo một `customerId` duy nhất và một Order ID ngẫu nhiên.
2. Ghi Order qua SDK KV và nhận `MutationResult`.
3. Xác minh có mutation token hoặc áp dụng nhánh fallback minh bạch.
4. Tạo `MutationState` từ kết quả ghi.
5. Query theo `customerId` với `consistentWith(state)`.
6. Nếu query thành công, không có mutation cạnh tranh và query không giới hạn loại row, phải tìm thấy Order ID đã ghi.
7. Cleanup fixture; đo độ trễ query và ghi lại consistency mode.
8. Không buộc query `NOT_BOUNDED` phải stale: index có thể cập nhật rất nhanh.

### 20.2. Ví dụ JUnit/Spring Boot với Couchbase Java SDK

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import java.util.UUID;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MutationStateConsistencyIT {
    @Autowired
    private Cluster cluster;

    @Test
    void querySeesItsOwnAcknowledgedInsert() {
        Collection orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");

        String id = "order::it-" + UUID.randomUUID();
        String customerId = "it-customer-" + UUID.randomUUID();
        boolean acknowledged = false;

        try {
            MutationResult result = orders.insert(
                    id,
                    JsonObject.create()
                            .put("customerId", customerId)
                            .put("status", "CREATED"));
            acknowledged = true;

            if (result.mutationToken().isEmpty()) {
                fail("Test requires a mutation token; " +
                        "check SDK/cluster support");
            }

            MutationState state = MutationState.from(result);

            String sql = """
                SELECT META(o).id AS documentId
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                """;

            QueryResult queried = cluster.query(
                    sql,
                    queryOptions()
                            .parameters(JsonObject.create()
                                    .put("customerId", customerId))
                            .consistentWith(state));

            assertTrue(queried.rowsAsObject().stream()
                    .anyMatch(row ->
                            id.equals(row.getString("documentId"))));
        } finally {
            if (acknowledged) {
                orders.remove(id);
            }
        }
    }
}
~~~

Đây là **test phụ thuộc môi trường**:

- Cần bean `Cluster`, bucket `shop`, scope `sales`, collection `orders`, quyền phù hợp và secondary index online.
- `result.mutationToken()` được kiểm tra trước khi tạo state để không che lỗi hỗ trợ token.
- Nếu insert đã thực hiện nhưng client không nhận ACK, cờ `acknowledged` có thể chưa bật. Suite production-grade cần cleanup fixture độc lập để loại bỏ tài liệu test bị bỏ lại.
- Query không có `LIMIT` để tránh loại document thử nghiệm, còn `customerId` ngẫu nhiên giảm va chạm.
- Một truy vấn `NOT_BOUNDED` cũng **có thể** thấy document ngay; không thể dùng sự có mặt của row một lần để chứng minh đã chọn đúng policy nếu không kiểm tra options/log/tracing.
- Không chạy thử nghiệm tạo/xóa dữ liệu trên cluster production.

### 20.3. Test nhiều mutation

Tạo A và B, gom state bao gồm cả hai kết quả, query theo customerId và assert tập ID chứa A và B. Khi viết test, bảo đảm dữ liệu không bị transaction/worker khác đổi hoặc xóa giữa các bước. Nếu hai token cùng partition, vẫn phải dùng API state phù hợp; đừng tự so sánh sequence số học giữa partition không liên quan.

### 20.4. Không viết test “index phải luôn trễ”

~~~text
upsert(Order)
query NOT_BOUNDED ngay
assert result KHÔNG chứa Order  // Sai: timing phụ thuộc hệ thống.
~~~

Một index có thể bắt kịp ngay trên môi trường ít tải. `NOT_BOUNDED` không ép query trả stale data.

## 21. Chẩn đoán khi consistentWith không đem lại kết quả mong đợi

~~~mermaid
flowchart TD
    A["Query consistentWith không có Order"] --> B{"Write đã ACK thành công?"}
    B -->|Không hoặc ambiguous| C["Kiểm tra state/idempotency theo key"]
    B -->|Có| D{"Có mutation token hợp lệ?"}
    D -->|Không| E["Fallback REQUEST_PLUS hoặc KV theo SLO"]
    D -->|Có| F{"Query đúng keyspace / filter / index?"}
    F -->|Không| G["Sửa mapping, SQL++, EXPLAIN, permission"]
    F -->|Có| H{"Query lỗi hoặc timeout?"}
    H -->|Có| I["Đo index lag, timeout và Index Service"]
    H -->|Không| J["Xem LIMIT, sort, mutation sau ghi và tenant filter"]
~~~

Một số triệu chứng:

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| `mutationToken()` rỗng | SDK/Server/operation không cung cấp token | Kiểm tra khả năng, fallback rõ |
| `consistentWith` query timeout | Index chưa đạt token hoặc query chậm | Đo Index Service, query plan, timeout |
| KV thấy Order nhưng SQL++ không thấy | Index lag, filter/collection sai | Kiểm tra keyspace, query consistency |
| Query thành công nhưng thiếu Order | `WHERE`/`LIMIT`/type filter/concurrent delete | Xem dữ liệu nguồn và generated SQL++ |
| Token từ mutation ở keyspace khác | State/query không tương thích ngữ cảnh | Xác minh bucket/index và SDK restrictions |
| SDK raw document không match Repository query | Type discriminator/schema mapping khác | Chuẩn hóa JSON/converter |
| Lỗi CAS khi ghi | Concurrent update, không phải index lag | Xử lý optimistic locking |
| Tạo Order trùng sau timeout | Retry không idempotent | Key ổn định và conditional insert |
| Request WebFlux block | SDK blocking được gọi trong event loop | Dùng SDK reactive end-to-end |

### 21.1. Dùng trace và metric thay vì chỉ xem kết quả row

Việc query trả đúng row **không tự chứng minh** SDK đã truyền mutation state, vì index có thể cập nhật kịp cả khi query NOT_BOUNDED. Nếu muốn test phần cấu hình, cần quan sát request options/tracing hoặc kiểm tra có tạo đúng state và truyền vào đúng `QueryOptions`.

Metric cần có: KV write latency, SQL++ p50/p95/p99, query timeout rate, Index Service mutation backlog, query plan/index usage, CAS conflict, retry count và tỷ lệ request chọn từng policy.

## 22. Thiết kế API có SLO về độ mới

Đối với một hệ thống nghiệp vụ, nên mô tả yêu cầu dữ liệu bằng ngôn ngữ rõ ràng.

| API | Độ mới mong muốn | Cách triển khai đề xuất |
| --- | --- | --- |
| `POST /orders` trả ID và trạng thái vừa lưu | Dữ liệu từ mutation đã xác nhận | Trả saved representation, không query danh sách |
| `GET /orders/{id}` | Document hiện tại theo key | KV read trên active path |
| `GET /customers/{id}/orders` sau POST trong cùng service | Nhìn thấy các Order vừa tạo | `consistentWith(state)` nếu có token; `REQUEST_PLUS` nếu không |
| `GET /customers/{id}/orders` xem lịch sử thông thường | Có thể chấp nhận trễ index | NOT_BOUNDED, pagination, refresh |
| `PATCH /orders/{id}/status` | Không lost update | CAS/`@Version`/conditional write |
| Đặt hàng đồng thời trừ tồn kho | Nhiều mutation phải cùng thành công | Transaction/compensation và idempotency |
| Kiểm tra session hợp lệ | Không chấp nhận session hết hạn | KV key + TTL/revocation, không dùng index lag |
| Tìm mô tả sản phẩm | Search theo từ khóa | Search index và consistency riêng |

**Không để client tự ý chọn tùy tiện mọi option consistency** ở API công khai. Application service nên quyết định policy theo SLO và resource budget, có giới hạn timeout/concurrency.

## 23. Bài tập tự luyện

### Bài A — Chọn đường đọc

Service vừa ghi Order, có `orderId`. Nó chỉ cần trả đúng Order đó.

**Hỏi:** Có cần `MutationState` rồi query `WHERE customerId = ...`?

**Hướng giải:** Thường không. Dùng saved entity hoặc KV `get(orderId)`. Token hữu ích khi thật sự cần **truy vấn qua index**.

### Bài B — Nhiều mutation

Service ghi hai Order A và B ở các key khác nhau, sau đó query lịch sử với state chỉ chứa token A.

**Hỏi:** Có bảo đảm thấy B chưa?

**Hướng giải:** Không. Phải đưa dấu mốc phù hợp của B vào state nếu yêu cầu nhìn thấy cả hai. Không tự suy diễn token A đại diện cho mọi mutation.

### Bài C — So sánh REQUEST_PLUS và consistentWith

Cluster có nhiều request ghi không liên quan. Service chỉ cần query thấy hai mutation mới của chính nó.

**Hỏi:** Cơ chế nào có thể giảm lượng chờ?

**Hướng giải:** `consistentWith(MutationState)` có thể tập trung vào những token cần thiết, nhưng cần token availability và phải đo thực tế; không cam kết luôn nhanh hơn REQUEST_PLUS.

### Bài D — CAS không phải token

Một lập trình viên dùng `MutationResult.cas()` làm “mutation state” để chống query thiếu dữ liệu.

**Hỏi:** Sai ở đâu?

**Hướng giải:** CAS là điều kiện concurrency của document, không phải token tiến độ index. Cần token/state do SDK hỗ trợ.

### Bài E — Token không có

KV insert được ACK nhưng `mutationToken()` trả empty. Query lịch sử vẫn bắt buộc mới ở mốc request.

**Hỏi:** Làm gì?

**Hướng giải:** Dùng `REQUEST_PLUS` nếu API hỗ trợ và SLO cho phép, hoặc đổi workflow đọc theo ID; không âm thầm dùng NOT_BOUNDED hoặc sleep tùy ý.

### Bài F — Timeout khi tạo Order

Client timeout ở KV insert rồi tạo ID mới và retry. Hai document xuất hiện.

**Hỏi:** `consistentWith` có sửa được lỗi này không?

**Hướng giải:** Không. Cần idempotency key/conditional insert và kiểm tra trạng thái ghi; scan consistency không thay bảo vệ tạo trùng.

### Bài G — Transaction

Service tạo Order và trừ Inventory; sau mỗi write, gom token vào MutationState rồi query.

**Hỏi:** Có bảo đảm Order và Inventory cùng commit không?

**Hướng giải:** Không. MutationState không tạo atomicity. Cần transaction hoặc workflow bù trừ và xử lý external side effects.

### Bài H — Test thiếu row

Một integration test query consistentWith(state) thành công nhưng không trả Order. Index đã đạt state.

**Hỏi:** Có thể do đâu?

**Hướng giải:** Kiểm tra `WHERE`, scope/collection, type discriminator, tenant filter, `LIMIT`, concurrent update/delete và query projection; không quy mọi thiếu row thành index lag.

## 24. Checklist trước khi đưa vào production

- [ ] Luồng query có thật sự cần **SQL++ theo index**, hay đã có ID để đọc KV?
- [ ] Mutation được xác nhận và SDK có cung cấp token phù hợp không?
- [ ] State bao gồm **mọi mutation cần quan sát** và đúng keyspace/partition?
- [ ] Không trộn `consistentWith` với scan consistency option khác trên cùng query?
- [ ] Nếu token thiếu, fallback đã được chọn theo SLO và được test?
- [ ] SQL++ dùng parameter binding, query plan và secondary index được kiểm tra?
- [ ] `WHERE`, `ORDER BY`, `LIMIT`, projection, type discriminator và authorization đúng?
- [ ] SDK raw JSON đồng nhất với mapping của Spring Data Repository/Template?
- [ ] CAS, TTL, durability, transaction và idempotency được xử lý riêng?
- [ ] Query timeout có tính phần chờ Index Service? Có giới hạn concurrency/retry?
- [ ] Reactive pipeline nối write rồi query theo thứ tự subscription, không `block()` trên event loop?
- [ ] Không dùng MutationState làm snapshot lịch sử hoặc token chứng minh quyền?
- [ ] Có integration test với cluster/index thật, không ép NOT_BOUNDED phải stale?
- [ ] Có cleanup fixture ngay cả khi write ambiguous, test không đụng production?
- [ ] Có p95/p99 SQL++ latency, index lag, timeout metrics và tracing phù hợp?
- [ ] Các ranh giới cross-request, cross-region và Search consistency đã được thiết kế riêng?

## 25. Kết luận

**`MutationState` của Couchbase Java SDK là công cụ diễn đạt read-your-writes cho truy vấn SQL++ dựa trên secondary index.** Khi SDK trả mutation metadata từ một thao tác KV, ứng dụng có thể gom các mốc cần quan sát rồi gọi `QueryOptions.consistentWith(state)` để yêu cầu Index Service bắt kịp các mutation ấy trước khi scan.

Cách này khác `NOT_BOUNDED` (không yêu cầu đợi index mới) và `REQUEST_PLUS` (đợi mốc phù hợp của request), đồng thời **không thay CAS, durability, TTL hoặc transaction**. Trong tầng truy cập Spring Data Couchbase, hãy dùng Repository/Template cho những thao tác thông thường và Java SDK gateway khi cần giữ mutation token một cách có chủ đích, bảo đảm mapping/keyspace thống nhất. Việc đo index lag, timeout và xây integration test không flaky là điều kiện để biến consistency policy thành một bảo đảm có thể vận hành trong hệ thống thực tế.
