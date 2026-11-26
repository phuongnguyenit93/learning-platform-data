# Độ mới của dữ liệu khi đọc theo khóa và khi truy vấn qua chỉ mục

## 1. Vấn đề cốt lõi: vừa ghi thành công nhưng truy vấn chưa thấy

Trong **Spring Data Couchbase**, hai cách đọc tưởng như tương đương có thể trả kết quả khác nhau ngay sau một thao tác ghi:

1. `repository.findById("order::o-1001")` đọc **một document theo khóa chính xác**.
2. `repository.findByCustomerId("c-1001")` tìm **các document có một giá trị field JSON**.

Đường thứ nhất thường dùng **Key–Value (KV)** trên Data Service. Đường thứ hai thường được thực thi qua **SQL++ và secondary index**. Index được cập nhật từ những thay đổi dữ liệu và có thể chưa bắt kịp mutation vừa hoàn tất; bởi vậy **query theo field có thể tạm thời trả kết quả cũ**, dù đọc theo key đã thấy document mới.

Bài học thuộc chương **Tính nhất quán** của module **SPRING_DATA_COUCHBASE**. Bạn sẽ học:

- Phân biệt *write acknowledged*, *KV read-after-write*, *index freshness*, *query consistency* và *durability*.
- Giải thích nguyên nhân SQL++ đôi khi chưa thấy document vừa tạo, còn thấy document vừa xóa hoặc trả giá trị field trước khi sửa.
- Chọn giữa chính sách index scan `not_bounded`, `request_plus` và đọc nhất quán theo **mutation token** (`at_plus`) khi API hỗ trợ.
- Sử dụng Spring Data Repository cùng Couchbase Java SDK để minh họa các đường đọc và cấu hình query consistency.
- Thiết kế UX và các thao tác nghiệp vụ không phụ thuộc sai vào độ mới của index.
- Kiểm tra tác động của CAS, TTL, transaction, replica reads và Search Service, đồng thời đo đánh đổi độ trễ/hiệu năng.

**Điều quan trọng nhất:** “Đã ghi thành công” và “mọi loại truy vấn đều lập tức nhìn thấy bản ghi ấy” **không phải một phát biểu tương đương**.

## 2. Tình huống xuyên suốt: tạo đơn hàng rồi mở lịch sử

Ứng dụng thương mại điện tử lưu đơn trong bucket `shop`, scope `sales`, collection `orders`. Một document có:

~~~text
Địa chỉ:
  bucket: shop
  scope: sales
  collection: orders
  document ID (metadata): order::o-1001
~~~

~~~json
{
  "customerId": "c-1001",
  "status": "CREATED",
  "createdAt": "2026-11-25T03:00:00Z",
  "currency": "VND",
  "totalVnd": 350000
}
~~~

Người dùng đặt đơn, backend lưu thành công rồi mở trang “Đơn hàng của tôi”. Hãy so sánh hai lời gọi:

~~~java
// Đọc theo document ID đã biết:
Optional<OrderDocument> detail =
        orders.findById("order::o-1001");

// Tìm theo field customerId trong JSON:
List<OrderDocument> history =
        orders.findByCustomerId("c-1001");
~~~

Cả hai method nằm trong Spring Data Repository, nhưng có thể đi tới **hai dịch vụ và hai cơ chế dữ liệu**:

~~~mermaid
flowchart TD
    W["OrderRepository.save(order)"] --> D[("Couchbase Data Service")]
    D --> K["KV get theo ID"]
    D --> S["Luồng thay đổi dữ liệu"]
    S --> I["Secondary index / Index Service"]
    I --> Q["SQL++ / Query Service"]
    K --> A["findById: có thể thấy đơn mới"]
    Q --> B["findByCustomerId: có thể tạm chưa thấy"]
~~~

Sơ đồ tập trung vào nguyên lý, không mô tả toàn bộ topology hoặc tiến trình nội bộ của cluster. Độ mới của index còn tùy trạng thái dịch vụ, tải, partition, chính sách consistency và thời điểm query bắt đầu.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi nó trả lời | Không nên hiểu lầm |
| --- | --- | --- |
| **Mutation** | Dữ liệu đã được insert/upsert/replace/remove như thế nào? | Không đồng nghĩa mọi index đã cập nhật |
| **Write acknowledged** | Thao tác ghi đã được hệ thống xác nhận theo option hiện hành chưa? | Không tự suy ra truy vấn SQL++ thấy ngay |
| **KV read-after-write** | Khi biết đúng ID, đọc từ đường KV có thấy mutation vừa ghi không? | Không bảo đảm cho đường replica hoặc hệ thống khác |
| **Secondary index freshness** | Chỉ mục SQL++ đã theo kịp thay đổi dữ liệu tới mức nào? | Không chính là CAS hoặc durability |
| **Query scan consistency** | Query phải chờ index đến trạng thái nào trước khi scan? | Không phải một lệnh khóa cả cluster |
| **CAS / optimistic locking** | Document có bị người khác sửa kể từ lần đọc trước không? | Không làm index cập nhật nhanh hơn |
| **Durability** | Mutation đã đạt mức ghi bền/nhân bản được yêu cầu chưa? | Không bằng index query consistency |
| **Transaction** | Một nhóm mutation có ranh giới commit/rollback theo API tương ứng không? | Không có nghĩa mọi Search index cập nhật đồng thời |

Trong phạm vi bài này, **“độ mới”** (freshness) chủ yếu mô tả *thời điểm những thay đổi của dữ liệu nguồn đã được phản ánh vào kết quả truy vấn dựa trên index*. Đây là một chiều của tính nhất quán, không phải định nghĩa đầy đủ về mọi bảo đảm isolation, durability hay replication.

### 3.1. “Đã thấy” không đồng nghĩa “thấy đúng phiên bản tôi muốn”

Giả sử bản ghi được cập nhật hai lần rất nhanh: trạng thái chuyển từ `CREATED` sang `CONFIRMED`, rồi sang `CANCELLED`. Một query yêu cầu index bắt kịp mutation đầu tiên **không bắt buộc** phải trả đúng phiên bản `CONFIRMED`: nó có thể thấy phiên bản mới hơn, hoặc không trả document nếu document đã bị xóa và index bắt kịp xóa. Consistency theo mutation token là ràng buộc về **độ tiến của index**, không phải yêu cầu truy xuất một bản snapshot lịch sử có phiên bản cố định.

## 4. Đọc theo khóa: đường KV và những điều kiện của kết luận

### 4.1. Vì sao `findById` khác SQL++?

Với `CouchbaseRepository<OrderDocument, String>`, thao tác tìm theo ID chính xác thường được thực hiện bằng KV trên document key. Data Service có thể định vị document trực tiếp qua keyspace mà **không cần secondary index**.

~~~text
Write order::o-1001 thành công
       |
       v
KV get("order::o-1001")
       |
       +--> đọc trực tiếp trạng thái document qua đường KV
       |
       +--> không phải chờ index (customerId, createdAt) cập nhật
~~~

Đối với một mutation đã được xác nhận thành công, đọc KV bình thường theo cùng key từ **active data path của cùng cluster** là lựa chọn tự nhiên để có read-your-writes cho document đó. Dù vậy, khi hệ thống có timeout, failover, replication hoặc đọc từ nguồn khác, phải kiểm tra semantics thực tế chứ không diễn giải “KV luôn mới nhất” như một lời hứa không điều kiện.

### 4.2. Ba ngoại lệ dễ bị bỏ qua

1. **Đọc từ replica:** một số API SDK có khả năng đọc từ replica vì mục tiêu sẵn sàng hoặc tối ưu đường truy cập. Replica có thể chưa theo kịp active; không áp một bảo đảm độ mới giống hệt lên mọi chế độ replica read.
2. **Đọc từ cluster/bản sao dữ liệu khác:** nếu đọc ở vùng hoặc cluster khác qua cơ chế đồng bộ dữ liệu riêng, phải xét độ trễ replication của cơ chế đó.
3. **Kết quả ghi không rõ do timeout:** timeout **không luôn có nghĩa ghi chắc chắn thất bại**. Nếu server có thể đã nhận mutation nhưng client chưa nhận phản hồi, cần idempotency key, kiểm tra trạng thái và chiến lược retry đúng cho nghiệp vụ.

Ngoài ra, một application cache đứng trước Repository có thể trả giá trị cũ nếu cache invalidation không đúng; vấn đề đó tách biệt với GSI index freshness ở Couchbase.

### 4.3. Đọc KV không cần secondary index

Giả sử Java service biết `orderId = o-1001`:

~~~java
import java.util.Optional;

public Optional<OrderDocument> getDetail(String orderId) {
    return orderRepository.findById("order::" + orderId);
}
~~~

Không cần tạo index theo `customerId` hay `status` để lời gọi này hoạt động. Ngược lại, nếu service chỉ biết `customerId` mà không biết Order ID, một KV get đơn lẻ không thể trả toàn bộ lịch sử đơn. Phải có query/index hoặc một cấu trúc ánh xạ bổ trợ được duy trì theo nghiệp vụ.

## 5. Truy vấn SQL++ qua secondary index: vì sao có độ trễ?

Couchbase cho phép truy vấn các trường trong JSON bằng **SQL++**, ví dụ:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.status, o.createdAt
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Một secondary index khởi đầu:

~~~sql
CREATE INDEX ix_orders_customer_date
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Khi client ghi document, thao tác KV và việc cập nhật **Global Secondary Index (GSI)** không nhất thiết hoàn tất cùng một thời điểm. Hệ thống chuyển các thay đổi dữ liệu tới Index Service để index phản ánh trạng thái mới. Query Service sử dụng index phù hợp theo query plan.

### 5.1. Ví dụ timeline

~~~text
T0   SDK/Repository ghi Order mới, nhận kết quả thành công
T1   KV get(order::o-1001) thấy Order
T2   Index ix_orders_customer_date chưa xử lý mutation mới
T3   SQL++ WHERE customerId = "c-1001" có thể chưa thấy Order
T4   Index bắt kịp mutation
T5   Cùng SQL++ đó thấy Order (nếu trạng thái dữ liệu không đổi)
~~~

Khoảng giữa T0 và T4 là **index lag**; không có con số cố định áp dụng cho mọi cluster. Dưới tải hoặc lúc index đang xây dựng/phục hồi, độ trễ có thể biến động. Số liệu ổn trong môi trường dev không bảo đảm production luôn giống như vậy.

### 5.2. Ba loại sai khác thường gặp

| Mutation vừa xảy ra | KV theo đúng key | Query qua index có thể tạm thời |
| --- | --- | --- |
| **Insert** document mới | Thấy document sau ghi thành công | **Thiếu** document mới |
| **Update** `status=CREATED` → `CONFIRMED` | Thấy giá trị mới qua đường active KV | Vẫn match điều kiện cũ, hoặc chưa match điều kiện mới |
| **Remove** document | Trả not-found khi xóa đã có hiệu lực | Có thể còn ID/hit cũ cho tới khi index phản ánh xóa |

Nếu index đã trả một ID của document bị xóa nhưng engine cần fetch document gốc, hành vi row thực tế phụ thuộc query plan: có thể row không xuất hiện thay vì hiển thị “bản cũ”. Vì thế hãy mô tả vấn đề là **độ mới của kết quả và quá trình quét index**, không mặc định mọi câu SQL++ sẽ trả lại nguyên JSON cũ.

### 5.3. Index không phải nơi bảo đảm bất biến nghiệp vụ

Không dùng một query với index có thể trễ để quyết định duy nhất rằng “email chưa ai đăng ký” hoặc “đơn này chưa tồn tại” rồi tạo record mới với ID khác. Hai request đồng thời cũng có thể vượt qua kiểm tra trước khi ghi. Nếu cần uniqueness, chọn một chiến lược **tạo có điều kiện theo key, giao dịch hoặc dữ liệu ánh xạ có kiểm soát** phù hợp với nghiệp vụ.

## 6. Ba mức SQL++ index scan consistency quan trọng

Mục tiêu của *scan consistency* là xác định mức độ cập nhật của **index dùng cho query** trước khi thực hiện scan. Đây không phải một phiên bản khóa toàn bộ Couchbase hay một transaction isolation level.

| Chế độ | Ý nghĩa khái quát | Điểm mạnh | Đánh đổi |
| --- | --- | --- | --- |
| **`not_bounded`** | Không yêu cầu index đợi bắt kịp mutation mới nhất trước khi scan | Giảm thời gian chờ index; thường phù hợp các danh sách chấp nhận trễ | Có thể không thấy dữ liệu vừa thay đổi |
| **`request_plus`** | Đợi index tiến đến mức phản ánh các mutation trước thời điểm bắt đầu request/query theo semantics của server | Hữu ích khi query cần độ mới cao, không có token riêng | Có thể tăng độ trễ, timeout nếu index chậm |
| **`at_plus` / consistent-with** | Đợi index phản ánh ít nhất các mutation được chỉ ra bởi mutation state/token | Tập trung vào “đã thấy các ghi cụ thể của mình” | Phải có/giữ mutation token, quản lý scope và API thích hợp |

Cách gọi tên trong SDK/Server có thể khác nhau theo phiên bản và loại API. Đặc biệt, `consistentWith(MutationState)` ở SDK là một cách yêu cầu tính nhất quán theo mutation state; không nên sao chép cùng tên method sang Spring Data Repository nếu phiên bản hiện tại không hỗ trợ.

### 6.1. `not_bounded`: ưu tiên độ trễ truy vấn

Đây thường là lựa chọn mặc định của SQL++ query khi không yêu cầu scan consistency cao hơn.

Ví dụ phù hợp:
- Trang báo cáo tổng hợp không bắt buộc phản ánh từng mutation vừa xảy ra.
- Danh sách sản phẩm chấp nhận cập nhật sau một khoảng ngắn.
- Tác vụ đọc chỉ để gợi ý giao diện, còn thao tác quyết định cuối cùng sẽ xác minh lại trạng thái nguồn.

**Không phù hợp** nếu ngay sau khi tạo đơn, yêu cầu nghiệp vụ bắt buộc query lịch sử có đơn vừa tạo để xác nhận thành công. Trong trường hợp ấy, truy cập thẳng Order ID hoặc nâng query consistency sẽ phù hợp hơn.

### 6.2. `request_plus`: chờ index cập nhật trước khi quét

`request_plus` yêu cầu Query Service đợi các index liên quan theo kịp thay đổi tới mốc được xác định khi query bắt đầu, trước khi scan theo semantics của server.

~~~mermaid
sequenceDiagram
    participant A as App
    participant D as Data Service
    participant I as Index Service
    participant Q as Query Service
    A->>D: Ghi order::o-1001
    D-->>A: Ghi thành công
    A->>Q: SQL++ với request_plus
    Q->>I: Đợi index bắt kịp mốc consistency
    D-->>I: Mutation được phản ánh vào index
    I-->>Q: Index đủ mới để scan
    Q-->>A: Query result
~~~

Điểm cần nhớ:

- Đây là **chờ index**, không phải nâng cấp mọi read thành transaction serializable.
- Các mutation xảy ra **sau khi query bắt đầu** không mặc nhiên nằm trong ranh giới request ấy.
- Nếu index lag quá lớn, query có thể chậm hoặc timeout. Thời gian đợi không phải miễn phí.
- Query còn phụ thuộc index **được chọn trong plan** và phạm vi keyspace; cần `EXPLAIN` và kiểm tra index trạng thái sẵn sàng.

### 6.3. `at_plus`: đợi những mutation mình đã quan sát

Sau một lệnh KV mutation, SDK có thể cung cấp **mutation token** chứa thông tin để xác định một mốc tiến của dữ liệu/partition. Một **MutationState** có thể tổng hợp các token liên quan. Query dùng consistency theo state này đợi index cập nhật tới ít nhất các mốc cần thiết.

Tư duy luồng:

~~~text
KV upsert(Order A) --> mutation token A
KV upsert(Order B) --> mutation token B
                          |
                          v
                  MutationState(A, B)
                          |
                          v
             SQL++ consistentWith(state)
                          |
                          v
            Đợi index bắt kịp A và B
~~~

Đây là lựa chọn có ích khi application cần bảo đảm query sau ghi **nhìn thấy ít nhất các mutation vừa thực hiện**, nhưng không nhất thiết muốn đợi mọi mutation khác đang xảy ra trên cluster như `request_plus`.

**Lưu ý:** Token/state là dấu mốc consistency, không phải transaction ID và không cho phép đọc snapshot chính xác một phiên bản cũ. Nếu một document đã tiếp tục bị cập nhật hoặc xóa, query có thể phản ánh trạng thái mới hơn. Khi thao tác ghi đi qua `repository.save`, ứng dụng có thể không trực tiếp nhận mutation token ở abstraction đó; nếu muốn dùng token, cần tìm API/configuration phù hợp trong đúng phiên bản Spring Data/SDK, hoặc thiết kế một gateway SDK cho luồng cần tính năng này.

## 7. Mã Java SDK: so sánh KV và SQL++ request_plus

Ví dụ sau minh họa riêng đường SDK để thấy options rõ ràng. Giả sử `Cluster` đã được cấu hình trong Spring Boot, collection `shop.sales.orders` tồn tại và có secondary index hỗ trợ điều kiện `customerId`.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrderReadGateway {
    private final Cluster cluster;
    private final Collection orders;

    public OrderReadGateway(Cluster cluster) {
        this.cluster = cluster;
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public JsonObject findByExactKey(String orderId) {
        GetResult result = orders.get(orderId);
        return result.contentAsObject();
    }

    public QueryResult findByCustomerWithFreshIndex(
            String customerId) {

        String sql = """
                SELECT META(o).id AS documentId,
                       o.customerId, o.status, o.createdAt
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                ORDER BY o.createdAt DESC
                LIMIT 20
                """;

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS);

        return cluster.query(sql, options);
    }
}
~~~

Điều quan trọng trong ví dụ:

1. `findByExactKey` dùng KV. Đầu vào phải là **metadata ID đầy đủ**, ví dụ `order::o-1001`, không phải `customerId`.
2. `findByCustomerWithFreshIndex` truy vấn theo field JSON bằng SQL++ và yêu cầu `request_plus`.
3. Đầu vào `customerId` được truyền qua **named parameter** thay vì ghép chuỗi SQL++; vừa rõ hợp đồng vừa tránh injection.
4. Cần cấp quyền Query/Index phù hợp và index hoạt động; `request_plus` không tự tạo index.
5. Java text block yêu cầu phiên bản Java hỗ trợ; phiên bản SDK và cấu hình Spring Boot thực tế phải tương thích. Nếu keyspace khác, chỉnh cả annotation mapping và query.
6. SDK trả `JsonObject`/`QueryResult`; nó **không tự thực thi toàn bộ converter/annotation Spring Data** như Repository hoặc Template.

### 7.1. Tự chọn khi nào cần request_plus

Không nên bật `request_plus` cho tất cả request một cách máy móc. Ví dụ:

- API `GET /orders/{id}`: có ID → dùng KV là đủ cho mục tiêu truy cập document đó.
- API `GET /customers/{id}/orders`: có nhiều ID cần lọc → SQL++/index; dùng `request_plus` nếu business/UX đòi hỏi dữ liệu vừa ghi phải xuất hiện ngay.
- Báo cáo doanh thu theo ngày: nếu chấp nhận trễ ngắn, có thể dùng consistency mặc định và tránh đợi index ở mọi lần.
- Xử lý thanh toán: **không** nên dựa vào query index cũ để quyết định trạng thái cuối cùng; cần đọc/ghi nguồn có thẩm quyền và đồng bộ nghiệp vụ phù hợp.

## 8. Mutation token trong SDK: mẫu thao tác theo luồng

Phần này diễn giải **ý tưởng code** để chọn độ mới theo một mutation đã biết. Tên API cụ thể của `MutationState` và cách lấy token phải đối chiếu tài liệu của Couchbase Java SDK phiên bản đang sử dụng.

~~~java
// Pseudocode: mô tả luồng, không phải đoạn mã biên dịch độc lập.

// 1. Ghi document qua SDK KV; lấy kết quả có mutation metadata.
var mutationResult = orders.upsert(documentId, jsonBody);

// 2. Tạo mutation state từ kết quả/token của ghi vừa xong.
var state = MutationState.from(mutationResult);

// 3. Query theo field; yêu cầu index bắt kịp state đã có.
var result = cluster.query(
    sql,
    queryOptions()
        .parameters(params)
        .consistentWith(state)
);
~~~

Để dùng mẫu này, cần import `MutationState`, `queryOptions`, khai báo `orders`, `sql` và `params` theo API thực tế. Đây không phải đoạn Java copy-paste hoàn chỉnh; mục tiêu là hiểu **mối quan hệ mutation → token/state → query**.

### 8.1. Vì sao không chỉ giữ thời gian máy client?

Không thể suy ra một token consistency an toàn đơn giản từ `Instant.now()` của client. Đồng hồ giữa client và cluster không phải metadata index sequence. Mutation token là dữ liệu do API/database cung cấp để biểu đạt mốc mutation được quan sát; nếu không có token phù hợp, hãy dùng cơ chế consistency khác như `request_plus` hoặc đổi UX sang đọc theo key.

### 8.2. Khi nào cần tổng hợp nhiều token?

Một workflow đã tạo vài document rồi cần query thấy các mutation đó. State có thể cần tổng hợp các token theo đúng phạm vi/partition để bảo đảm query đủ mới. Không lấy một token bất kỳ rồi mặc định nó đại diện cho toàn bộ các thay đổi ở mọi collection và transaction.

Đồng thời, cần xác định **tính tương thích giữa token, keyspace, Query Service và API**. Nếu một thao tác ghi không cấp được mutation metadata cần thiết, ứng dụng phải chọn fallback rõ ràng thay vì ngầm coi truy vấn đã có độ mới mong muốn.

## 9. Spring Data Repository và CouchbaseTemplate nhìn vấn đề này thế nào?

Spring Data Couchbase giúp lập trình viên làm việc trên entity:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);
}
~~~

Service minh họa:

~~~java
public OrderDocument placeAndOpenDetail(OrderDocument order) {
    OrderDocument saved = orders.save(order);
    return orders.findById(saved.getId())
            .orElseThrow();
}
~~~

Ở đây sau `save`, service đọc trực tiếp theo ID vừa biết. Nó **không** phụ thuộc vào secondary index để thấy document mới trong tình huống bình thường.

Nếu service thay bằng:

~~~java
public List<OrderDocument> placeAndListHistory(
        OrderDocument order) {

    OrderDocument saved = orders.save(order);
    return orders.findByCustomerId(saved.getCustomerId());
}
~~~

thì lời gọi thứ hai là query theo field; nếu mặc định scan consistency không yêu cầu index mới nhất, danh sách có thể chưa chứa Order vừa tạo.

**Không đồng nhất “Repository cho cùng entity” với “cùng tính nhất quán”.** Repository xử lý mapping và lựa chọn thao tác; Data Service và Query/Index Service vẫn tuân theo semantics của đường truy cập.

### 9.1. Muốn chỉnh query consistency ở tầng Spring Data

Có thể có các cơ chế cấu hình consistency qua `CouchbaseTemplate`/query options, repository configuration hoặc tích hợp với SDK tùy phiên bản. Tuy nhiên, không nên tự bịa annotation hay tên method cho `findByCustomerId`.

Một quy trình an toàn:

1. Xác định phiên bản Spring Boot, Spring Data Couchbase và SDK.
2. Xem API tương ứng để cấu hình scan consistency cho đúng query/operation.
3. Nếu abstraction không phơi bày đầy đủ option cần thiết, tạo gateway dùng SDK Query API ở tầng persistence để thực hiện truy vấn đặc thù.
4. Viết integration test cho read-after-write; không chỉ mock Repository.
5. Theo dõi latency và timeout sau khi bật consistency cao hơn.

**CouchbaseTemplate** không thay thế ý nghĩa của `request_plus`, và một method `@Query` cũng không bảo đảm index đã mới nếu không cấu hình đúng. Hãy kiểm chứng bằng kết quả thực và options được truyền tới SDK.

## 10. Những giới hạn của request_plus và at_plus

### 10.1. Không biến query thành snapshot lịch sử cố định

Với các chế độ đợi index, điều được bảo đảm chủ yếu là **mốc dữ liệu index đã bắt kịp trước khi query quét**. Không nên yêu cầu query trả chính xác trạng thái document ở thời điểm ứng dụng đọc trước đó, vì mutation khác vẫn có thể diễn ra.

Ví dụ:

~~~text
T0: A save Order với status=CREATED
T1: A có mutation token
T2: B update Order thành CONFIRMED
T3: A query consistentWith(token T0)
~~~

Query T3 không bắt buộc trả `CREATED`. Nó có thể thấy `CONFIRMED` nếu index đã cập nhật mutation của B. Điều cần xác nhận của token là **không dùng một trạng thái index cũ hơn mốc đã yêu cầu**, trong phạm vi và điều kiện được API hỗ trợ.

### 10.2. Không bảo đảm thứ tự nghiệp vụ giữa hai request

Hai request độc lập có thể được thực hiện và ghi dữ liệu theo thứ tự khác nhau. Nếu một đơn chỉ được chuyển `CREATED → CONFIRMED` một lần, cần **CAS, điều kiện trạng thái hoặc transaction** để bảo vệ thao tác. Query consistency không biến kiểm tra trước rồi ghi sau thành atomic operation.

### 10.3. Không giải quyết vấn đề index không tồn tại hoặc sai

Nếu SQL++ cần query theo `customerId` nhưng collection chưa có index thích hợp, `request_plus` không tạo index. Query có thể lỗi hoặc chậm do kế hoạch quét không phù hợp. Cần chuẩn bị index, xem `EXPLAIN` và giám sát Index Service.

### 10.4. Không thay thế durability

Một ghi với durability mạnh hơn có thể đợi điều kiện ghi/nhân bản bền vững. Nó **không buộc GSI index lập tức phản ánh mutation** theo chính sách query mặc định. Ngược lại, `request_plus` đợi index cập nhật nhưng không tự thay đổi độ bền của mutation trước đó.

## 11. TTL, xóa, cập nhật và Search index

### 11.1. TTL ảnh hưởng độ mới thế nào?

Document session có expiry 30 phút. Ở thời điểm hết hạn, Couchbase có cơ chế để xem document là hết hạn khi đọc, dù quá trình dọn dữ liệu vật lý và index có thể diễn ra theo lịch xử lý riêng.

Điều cần phân biệt:

- **KV get cho một session hết hạn:** theo semantics expiry, không nên coi document hết hạn là còn hợp lệ chỉ vì có thể chưa được purge vật lý.
- **Query SQL++ trên index:** độ mới của index và việc phản ánh expiry cần được xem xét như một thay đổi dữ liệu; không dùng query index trễ để xác thực một token/session.
- **Field JSON `expiresAt`:** không phải TTL tự động; nếu chỉ thêm field này mà không đặt expiry metadata, document không tự hết hạn theo Couchbase.
- **Nghiệp vụ đăng nhập:** ngoài KV expiry, vẫn phải kiểm tra trạng thái token, revoke/logout và quyền truy cập theo thiết kế security.

Đơn hàng và dữ liệu khách hàng thường không nên có TTL ngắn chỉ vì hệ thống hỗ trợ tính năng expiry.

### 11.2. Search/FTS là đường index khác

Full-Text Search (FTS) có **Search index riêng** cho phân tích từ ngữ, relevance và ranking. Nó không dùng chính secondary index SQL++ đã tạo để lọc `customerId`.

Sau khi ghi, Search index cũng có thể chưa phản ánh mutation ngay. Nếu Search trả ID sản phẩm đã xóa hoặc trạng thái tồn kho cũ, cần lấy lại dữ liệu có thẩm quyền trước quyết định mua hàng.

**Không bê nguyên cách gọi `QueryScanConsistency.REQUEST_PLUS` của SQL++ sang Search API**. Search có các khả năng/semantics consistency khác tùy phiên bản SDK/Server. Phải xác nhận riêng.

### 11.3. Thao tác SQL++ không nhất thiết phải đi qua index secondary giống nhau

Couchbase có nhiều cách thực thi query và nhiều loại index; một query dùng key lookup đặc thù hoặc kế hoạch khác có thể có semantics hiệu năng khác. Bài này tập trung vào tình huống **SQL++ lọc field JSON dựa trên secondary index** — đường truy cập phổ biến của derived query Spring Data. Đừng suy ra “mọi câu SQL++ đều phải chờ GSI” mà không xem kế hoạch thực tế.

## 12. CAS, transaction và nhiều document: ba câu hỏi khác nhau

Giả sử nghiệp vụ tạo đơn và trừ tồn kho:

~~~text
A. Ghi Order document
B. Trừ Stock document
C. Truy vấn lịch sử Order theo customerId
~~~

Ta phải tách ba câu hỏi:

| Câu hỏi | Công cụ liên quan |
| --- | --- |
| Nếu hai nhân viên cùng sửa một Order, làm sao không mất cập nhật? | CAS / `@Version` / optimistic locking |
| Nếu A thành công mà B thất bại, làm sao giữ bất biến nghiệp vụ? | Transaction đa document hoặc workflow bù trừ, tùy yêu cầu |
| Sau khi A đã commit, tại sao C chưa thấy Order? | Secondary index freshness / SQL++ scan consistency |

Dù transaction đã commit, truy vấn ngoài transaction qua index vẫn phải tuân thủ semantics đọc/consistency của query tương ứng. Không nên suy rằng commit transaction bảo đảm mọi index khác nhau và mọi hệ thống tìm kiếm đều cập nhật tức thì.

Ngược lại, bật `request_plus` cho C **không làm A và B thành một giao dịch nguyên tử**.

### 12.1. Bảo vệ bất biến “chỉ một đơn cho một idempotency key”

Nếu request tạo Order bị timeout, client có thể thử lại. Đọc danh sách Order qua SQL++ để xem đơn “đã tồn tại chưa” có thể bị trễ và không phải cách duy nhất bảo vệ khỏi tạo trùng. Nên dùng **idempotency key** có tính duy nhất, tạo có điều kiện theo key/record và lưu kết quả xử lý theo quy tắc nghiệp vụ. Sau timeout, kiểm tra trạng thái theo key có thể xác định thay đổi đã xảy ra mà không dựa trên index lag.

### 12.2. Vừa cập nhật trạng thái vừa xem chi tiết

Một route sửa trạng thái Order bằng `@Version`, nhận kết quả `save` rồi trả ngay entity đã lưu hoặc đọc KV lại theo ID nếu cần. Không cần query theo `status` chỉ để chứng minh thay đổi của một Order đã xảy ra. Cách này giảm phụ thuộc index freshness và dễ hiểu hơn.

## 13. Chọn độ mới theo yêu cầu API

| API/use case | Câu hỏi thực sự | Chiến lược thường phù hợp |
| --- | --- | --- |
| `GET /orders/{id}` | Order ID đã biết | KV `findById`; kiểm soát quyền |
| Trang xác nhận ngay sau `POST /orders` | Đơn vừa tạo có ID cụ thể | Trả saved entity/ID hoặc đọc KV |
| `GET /customers/{id}/orders` | Lịch sử nhiều Order | SQL++ + index; chọn consistency theo UX |
| Báo cáo nội bộ cho ngày hôm trước | Có thể chấp nhận trễ ngắn | SQL++ mặc định nếu SLA cho phép, hoặc dữ liệu tổng hợp riêng |
| Liệt kê Order vừa tạo cần hiển thị ngay | Query danh sách phải cập nhật | `request_plus` hoặc mutation-based consistency nếu hỗ trợ; cân nhắc chi phí |
| Xác nhận đơn chỉ nếu status hiện tại hợp lệ | Quyết định ghi trên một Order | KV + CAS/điều kiện ghi; không dựa vào index trễ |
| Tìm sản phẩm bằng từ khóa tự nhiên | Truy vấn Search index/FTS | Thiết kế Search freshness riêng; xác minh trạng thái nguồn |
| Xác thực session ID | Session còn hợp lệ tại thời điểm truy cập? | KV theo token key + chính sách expiry/revocation |
| Kiểm tra email chưa bị đăng ký | Uniqueness dưới cạnh tranh | Ghi có điều kiện/giao dịch phù hợp; query chỉ để hỗ trợ UX |

**Một quy tắc thiết kế có giá trị:** Nếu request đã biết **document key**, đừng ép nó chuyển qua một truy vấn secondary index chỉ để “đọc lại”. Nếu request thật sự cần tìm nhiều document theo field, hãy xác định **SLA về độ mới** thay vì bật request_plus vô điều kiện.

## 14. Đánh đổi hiệu năng khi yêu cầu index mới hơn

### 14.1. Độ trễ gồm những phần gì?

Với SQL++ query:

~~~text
Tổng thời gian phản hồi
  = chờ mạng
  + thời gian chờ index đạt consistency yêu cầu
  + lập kế hoạch/thực thi query
  + fetch/projection/sort
  + truyền kết quả về ứng dụng
~~~

Khi dùng `not_bounded`, query không có bước chủ động đợi index bắt kịp mốc cao như `request_plus`. Khi bật `request_plus`, độ trễ truy vấn có thể bị kéo dài nếu mutation rate cao hoặc Index Service đang bận. Nếu timeout bị đặt quá ngắn, hệ thống có thể tăng số lỗi và retry, khuếch đại tải.

**Không kết luận** tăng latency là do Spring Data chậm mà không đo Query/Index Service. Cần tách thời gian chờ index với thời gian quét/sort của query plan.

### 14.2. Bảng lựa chọn mức đánh đổi

| Ưu tiên | Lựa chọn đáng thử | Điều cần đo |
| --- | --- | --- |
| Độ trễ thấp, dữ liệu có thể hơi trễ | `not_bounded` | Tỷ lệ query bỏ sót mutation mới, p95/p99 |
| Cần query “mới đến lúc yêu cầu bắt đầu” | `request_plus` | Thời gian đợi index, timeout, throughput |
| Cần query thấy các mutation do luồng ứng dụng vừa thực hiện | `consistentWith(MutationState)` khi có token phù hợp | Chi phí quản lý token, độ trễ, fallback |
| Cần xem đúng một document vừa ghi | KV theo ID | KV latency, lỗi document/connection |
| Cần bảo vệ quyết định cập nhật dưới concurrency | CAS hoặc transaction | Conflict rate, idempotency, retry |

Cũng nên cân nhắc **cơ chế UX**: sau khi đặt hàng, hiển thị ngay đơn vừa lưu từ response, trong khi danh sách lịch sử có thể refresh sau. Điều này đáp ứng trải nghiệm mà không buộc mọi query phải chờ index.

## 15. Kiểm thử tích hợp: chứng minh các mức độ mới

Không nên chỉ mock Repository rồi kết luận consistency đúng. Cần môi trường Couchbase thực/tương đương với bucket/scope/collection và secondary index được dựng đúng.

### 15.1. Bộ test đề xuất

1. Tạo Order mới, nhận thành công từ KV write, đọc lại bằng key và xác minh body.
2. Query `WHERE customerId = ...` ở mức mặc định. Ghi nhận kết quả, **không khẳng định chắc chắn phải thất bại hoặc phải bị trễ**: index trên cluster nhàn có thể bắt kịp rất nhanh.
3. Query tương tự với `request_plus`. Xác minh document vừa tạo xuất hiện khi index, quyền và cấu hình phù hợp.
4. Sửa field `status`, kiểm tra KV sau ghi và query theo `status` ở các consistency được chọn.
5. Xóa document và xác nhận KV trả not-found; quan sát query/index theo policy.
6. Tăng tải mutation có kiểm soát để đo p95/p99 và timeout của query `request_plus` so với `not_bounded`.
7. Nếu dùng mutation token, tạo state từ write và query `consistentWith`; ghi nhận kết quả và độ trễ.
8. Test CAS conflict độc lập, tránh lẫn với index lag.
9. Nếu session dùng TTL, kiểm tra hành vi sau expiry và phân biệt với query qua index.

### 15.2. Ví dụ Java integration test cho request_plus

Đoạn kiểm thử sau minh họa trực tiếp SDK, giả sử đã inject `Cluster`, tạo collection và index hợp lệ trước khi test chạy:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.junit.jupiter.api.Test;

public class IndexFreshnessIT {
    private final Cluster cluster;
    private final Collection orders;

    public IndexFreshnessIT(Cluster cluster) {
        this.cluster = cluster;
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    @Test
    void queryWithRequestPlusSeesAcknowledgedOrder() {
        String id = "order::test-" + UUID.randomUUID();
        String customerId = "customer-test-" + UUID.randomUUID();

        orders.upsert(id, JsonObject.create()
                .put("customerId", customerId)
                .put("status", "CREATED"));

        String sql = """
            SELECT META(o).id AS documentId
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            """;

        QueryResult result = cluster.query(
                sql,
                queryOptions()
                        .parameters(JsonObject.create()
                                .put("customerId", customerId))
                        .scanConsistency(
                                QueryScanConsistency.REQUEST_PLUS));

        assertTrue(result.rowsAsObject().stream()
                .anyMatch(row ->
                        id.equals(row.getString("documentId"))));

        // Cleanup theo cơ chế fixture/teardown thực tế.
    }
}
~~~

Đây là **minh họa cấu trúc test**, chưa phải fixture JUnit hoàn chỉnh: để dùng trực tiếp, tích hợp tạo `Cluster` qua Spring Test hoặc Testcontainers, cấu hình injection/lifecycle, chuẩn bị index và cleanup document. Việc query trả kết quả không chứng minh mọi ngữ nghĩa của transaction hoặc FTS; nó kiểm tra đúng một hợp đồng read-after-write của SQL++ với `request_plus`.

### 15.3. Tránh một test sai kiểu “phải có index lag”

Không nên viết:

~~~text
Ghi Order
Ngay lập tức query mặc định
assert kết quả KHÔNG chứa Order
~~~

Test đó có thể **flaky**, vì index có thể đã cập nhật kịp. Thay vì đòi hỏi độ trễ luôn xuất hiện, dùng trace/measurement để quan sát và kiểm chứng chế độ consistency cao khi yêu cầu SLA thực sự.

## 16. Quan sát production và xử lý sự cố

| Triệu chứng | Kiểm tra trước | Hành động gợi ý |
| --- | --- | --- |
| API chi tiết thấy Order, lịch sử không thấy | Đường KV so với SQL++, scan consistency và trạng thái index | Xác định SLA độ mới; query request_plus hoặc UX hiện ngay saved order |
| Query request_plus chậm sau đợt ghi lớn | Index lag, Index Service CPU/memory, mutation rate, timeout | Đo indexer và query wait, điều chỉnh capacity/consistency |
| SQL++ báo thiếu index | Keyspace, quyền, index existence và query plan | Tạo/điều chỉnh index phù hợp, chạy `EXPLAIN` |
| Query theo status trả kết quả khác ngay sau update | Index chưa bắt kịp mutation hoặc query plan | KV xác nhận source, xem scan consistency |
| Đã xóa session nhưng một màn hình search vẫn hiện | Search/secondary index freshness | Không xác thực session bằng search; kiểm tra KV và security state |
| Tạo trùng Order sau timeout | Retry không idempotent, suy luận từ query index trễ | Định danh thao tác/idempotency key, kiểm tra trạng thái theo key |
| Một bản cập nhật bị mất | Thiếu CAS/conditional write | Dùng `@Version`/CAS, xem conflict handling |
| KV get ở vùng khác thấy giá trị cũ | Replica/cross-region replication semantics | Xác định đường read active/replica/cluster |

Metric nên có: **KV read/write latency**, **SQL++ query latency**, **index update lag**, **scan consistency mode**, **query timeout/error rate**, **mutation throughput**, **CAS conflict rate** và **CPU/memory của Data/Query/Index Service**. Kết hợp tracing có correlation ID để biết request nào ghi và query nào chạy sau đó.

Khi debug, không log credential, session token hay toàn bộ thông tin cá nhân của khách hàng. Nếu cần ghi ID để nối log, cân nhắc che hoặc băm một phần theo chính sách dữ liệu của ứng dụng.

## 17. Ngộ nhận thường gặp

| Ngộ nhận | Phân biệt đúng |
| --- | --- |
| “`save` thành công thì mọi query thấy ngay” | KV theo key và SQL++ qua index có đường cập nhật khác nhau |
| “Cả hai đều ở Repository nên consistency như nhau” | API Java giống nhau không thay semantics của Data và Query/Index Service |
| “Không thấy trong SQL++ nghĩa là insert thất bại” | Có thể chỉ là index lag; xác minh qua key và trạng thái ghi |
| “`request_plus` bảo đảm mọi request song song được tuần tự hóa” | Chỉ đặt yêu cầu mốc index scan; không là transaction isolation thay thế |
| “`at_plus` trả bản document đúng lúc tôi ghi” | Index có thể thấy mutation sau; token không chỉ định snapshot lịch sử |
| “Bật request_plus làm index query nhanh hơn” | Có thể tăng thời gian chờ, không cải thiện query plan |
| “Durability mạnh thì không cần request_plus” | Durability và query freshness là hai thuộc tính độc lập |
| “CAS làm secondary index cập nhật ngay” | CAS chỉ liên quan điều kiện cạnh tranh ở mutation |
| “TTL là field `expiresAt` trong JSON” | Expiry là metadata document, không phải tự suy ra từ field |
| “Search FTS dùng luôn request_plus của SQL++” | Search API có mô hình consistency riêng, phải xác nhận theo phiên bản |
| “Timeout có nghĩa thao tác chắc chắn chưa chạy” | Có thể kết quả ambiguous; retry cần idempotency và kiểm tra |

## 18. Bài tập và câu hỏi tự kiểm tra

### Bài tập A — Trang xác nhận đơn

Một người dùng vừa tạo Order và backend trả về `orderId`. Trang tiếp theo chỉ cần hiển thị số đơn, trạng thái và tổng tiền của **đúng Order đó**.

**Hỏi:** Nên dùng `findById` hay query `WHERE customerId = ...`?

**Đáp án định hướng:** Dùng saved entity hoặc `findById(orderId)` theo KV. Không cần phụ thuộc secondary index để hiển thị một document có ID đã biết.

### Bài tập B — Lịch sử đơn vừa tạo

Ngay sau khi tạo đơn, màn hình lịch sử bắt buộc chứa đơn mới trong danh sách 20 đơn gần nhất.

**Hỏi:** Có những lựa chọn gì?

**Đáp án định hướng:** SQL++ với consistency phù hợp như `request_plus` hoặc mutation state/token nếu API cung cấp; hoặc cập nhật giao diện dựa vào Order vừa tạo trong khi danh sách được refresh. Cần cân nhắc p95 latency và trường hợp có mutation đồng thời.

### Bài tập C — Hai request cùng đổi trạng thái

A và B cùng đọc Order `CREATED`. A xác nhận thành công, B gửi lại bản cũ. B bật `request_plus` khi query lịch sử.

**Hỏi:** Bật consistency cao có ngăn B ghi đè không?

**Đáp án:** Không. Cần CAS/`@Version` hoặc thao tác ghi có điều kiện. `request_plus` chỉ liên quan độ mới index khi query.

### Bài tập D — Email duy nhất

Hai khách cùng đăng ký email giống nhau. Cả hai gọi SQL++ `WHERE email = ...`, không thấy kết quả rồi tạo Customer với hai UUID khác nhau.

**Hỏi:** `request_plus` có phải giải pháp duy nhất đủ bảo đảm không trùng?

**Đáp án:** Không. Dù query rất mới tại thời điểm scan, hai request vẫn có thể cạnh tranh giữa kiểm tra và insert. Cần bất biến ghi có điều kiện/transaction hoặc thiết kế ID/ánh xạ email phù hợp.

### Bài tập E — Session hết hạn

Session có TTL 15 phút, ứng dụng tìm session bằng truy vấn `WHERE customerId = ...` để quyết định còn đăng nhập.

**Hỏi:** Đây có phải thiết kế an toàn?

**Đáp án định hướng:** Không nên dùng kết quả index có thể trễ làm nguồn quyết định xác thực. Dùng đường session key/expiry và cơ chế revoke/quyền theo thiết kế security.

### Câu hỏi nhanh

1. **KV theo key có cần secondary index không?** Không, khi key chính xác và đường KV bình thường.
2. **`not_bounded` có thể không thấy mutation vừa hoàn tất không?** Có.
3. **`request_plus` đợi điều gì?** Index liên quan theo kịp mốc yêu cầu trước khi scan.
4. **`consistentWith(MutationState)` nhắm tới điều gì?** Query thấy index đã tiến ít nhất qua các mutation được mô tả bởi state khi API hỗ trợ.
5. **`request_plus` có làm một loạt lệnh save thành transaction không?** Không.
6. **Đọc KV từ replica có nhất thiết mới như active không?** Không nên giả định.
7. **Một integration test mặc định có bắt buộc nhìn thấy index lag mới được tính là đúng không?** Không; index có thể cập nhật rất nhanh.
8. **Khi nào nên đo index lag và p95/p99 query latency?** Khi thiết kế SLA/UX độ mới, thay policy consistency hoặc thấy triệu chứng under load.

## 19. Checklist thiết kế độ mới dữ liệu

- [ ] API nào biết exact document ID và có thể đọc KV thay vì query theo field?
- [ ] Những query SQL++ nào dựa vào secondary index, với query plan/index nào?
- [ ] Yêu cầu độ mới là *chấp nhận trễ*, *mới đến thời điểm query*, hay *phải thấy mutation cụ thể*?
- [ ] Có lựa chọn rõ giữa `not_bounded`, `request_plus` và mutation-based consistency theo phiên bản không?
- [ ] Những mutation nào cần token; luồng Spring Data có lấy/chuyển token được không?
- [ ] Timeout cho query có tính đến thời gian chờ index? Có retry có giới hạn và idempotency?
- [ ] Quyết định nghiệp vụ có dựa sai vào query index trễ không?
- [ ] CAS/`@Version` bảo vệ concurrent write; transaction bảo vệ workflow nhiều document khi cần?
- [ ] Session/TTL và Search index được xử lý theo semantics riêng?
- [ ] Đã có integration test, query plan và metric index lag ở tải đại diện?

## 20. Kết luận

**Đọc theo khóa và truy vấn qua chỉ mục khác nhau về đường truy cập lẫn độ mới dữ liệu.** `findById` thường đọc KV trực tiếp theo document ID, không cần chờ secondary index. Còn truy vấn SQL++ theo field JSON thường sử dụng index được cập nhật từ mutation, vì vậy với consistency mặc định có thể tạm thời chưa thấy dữ liệu mới nhất.

Trong tầng truy cập **Spring Data Couchbase**, hãy chọn đường đọc theo yêu cầu thật: **biết ID thì ưu tiên KV; tìm tập document theo điều kiện thì dùng SQL++ với index và scan consistency phù hợp**. Dùng `request_plus` khi phải đợi index bắt kịp mốc truy vấn, mutation state/token khi cần nhìn thấy những ghi đã quan sát và API hỗ trợ; cân bằng độ mới với latency. Đồng thời tách biệt index freshness khỏi **CAS, TTL, durability, transaction, replica read và Search consistency** để hệ thống vừa đúng nghiệp vụ, vừa có hiệu năng và khả năng vận hành ổn định.
