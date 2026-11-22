# Targeted query, scatter-gather và ảnh hưởng đến độ trễ

## 1. Tại sao cùng một truy vấn có thể nhanh trên cụm này nhưng chậm trên cụm khác?

Khi MongoDB dùng **sharding**, document của một collection được phân bố trên nhiều shard dựa theo **shard key**. Ứng dụng kết nối qua `mongos`; bộ định tuyến quyết định shard nào cần nhận truy vấn bằng cách đối chiếu điều kiện lọc với thông tin phân bố chunk.

Hai truy vấn trả về cùng một document có thể tạo tải rất khác nhau:

~~~javascript
// Biết tenant chứa đơn hàng.
db.orders.findOne({ tenantId: "tenant-17", orderId: "ORD-081" })

// Chỉ biết mã đơn hàng.
db.orders.findOne({ orderId: "ORD-081" })
~~~

Giả sử collection được shard theo `{ tenantId: "hashed" }`. Truy vấn đầu có thể được chuyển tới một shard vì `mongos` biết giá trị shard key. Truy vấn thứ hai thiếu shard key nên có thể phải gửi tới tất cả shard, dù kết quả thực tế chỉ có một document.

Đó là khác biệt giữa **targeted query** và **scatter-gather**. Cách định tuyến tác động đến số yêu cầu mạng, công việc trên từng shard, khâu gộp kết quả và độ trễ cuối cùng mà người dùng nhìn thấy.

Trong **Spring Data MongoDB**, cả `MongoTemplate` lẫn repository đều tạo truy vấn gửi đến MongoDB. Framework không tự bổ sung shard key bị thiếu: bộ lọc mà ứng dụng xây dựng sẽ quyết định mức độ hiệu quả của định tuyến. Bài học này kết nối việc thiết kế query với phân bố dữ liệu, index và chẩn đoán hiệu năng.

## 2. Đường đi của truy vấn trong một sharded cluster

Một cụm MongoDB sharded thường có:

- **Shard:** nơi lưu trữ một phần dữ liệu; thông thường mỗi shard là một replica set.
- **Config servers:** lưu metadata cấu hình và phân bố chunk.
- **`mongos`:** cổng định tuyến truy vấn, sử dụng metadata của cụm để xác định shard cần liên hệ.
- **Ứng dụng:** gửi lệnh tìm kiếm, cập nhật và aggregation tới `mongos` thông qua MongoDB driver, chẳng hạn Spring Data MongoDB.

~~~mermaid
flowchart TD
    A["Spring Data MongoDB / MongoDB Driver"] --> B["mongos: phân tích bộ lọc và shard key"]
    B --> C{"Xác định được vùng dữ liệu?"}
    C -->|Có| D["Target một shard hoặc một tập con shard"]
    C -->|Không| E["Gửi tới toàn bộ shard liên quan"]
    D --> F["Thực thi tại shard được chọn"]
    E --> G["Thực thi song song tại nhiều shard"]
    F --> H["mongos trả kết quả"]
    G --> I["Gộp kết quả, có thể sort/limit"]
    I --> H
~~~

`mongos` không cần quét từng document để biết vị trí của khóa. Nó dùng thông tin các khoảng shard key gắn với chunk; đối với **hashed shard key**, giá trị khóa được hash trước khi xác định vị trí tương ứng. Metadata và cách tổ chức chunk có thể thay đổi khi balancer dịch chuyển dữ liệu, nhưng ứng dụng vẫn gửi truy vấn theo cùng giao diện.

**Phân biệt hai tầng tối ưu:**

1. **Query routing:** `mongos` chọn bao nhiêu shard để gửi lệnh.
2. **Query execution:** bên trong mỗi shard, query planner dùng index nào, quét bao nhiêu key/document, có phải sort trong bộ nhớ không.

Một truy vấn **target đúng một shard** vẫn có thể chậm nếu thiếu index hoặc phải quét hàng triệu document. Ngược lại, một scatter-gather trên tập dữ liệu nhỏ có thể hoàn thành nhanh, nhưng chi phí và độ trễ đuôi thường khó kiểm soát hơn khi số shard và tải tăng.

## 3. Targeted query, single-shard query và scatter-gather

| Hình thức | `mongos` làm gì? | Ví dụ khi shard key là `{ tenantId: "hashed" }` |
| --- | --- | --- |
| **Single-shard targeted query** | Gửi tới đúng một shard chứa giá trị shard key cần tìm | `{ tenantId: "tenant-17" }` |
| **Multi-shard targeted query** | Gửi tới một tập con shard được xác định từ shard key | `{ tenantId: { $in: ["tenant-17", "tenant-24"] } }` nếu hai giá trị nằm trên những shard khác nhau |
| **Scatter-gather** | Phát truy vấn tới tất cả shard cần tìm kiếm khi bộ lọc không giới hạn được shard key | `{ orderId: "ORD-081" }` hoặc `{ status: "PAID" }` |

Trong một cụm có tám shard, targeted query có thể cần một, hai hoặc một số shard. **Targeted không đồng nghĩa với single-shard.** Ngược lại, scatter-gather nghĩa là `mongos` phải tìm kiếm rộng khắp, dù chỉ một shard thật sự có document phù hợp.

Độ chính xác của định tuyến phụ thuộc đồng thời vào **kiểu shard key**, **thứ tự trường của shard key ghép**, **toán tử trong bộ lọc**, và **vị trí các chunk** ở thời điểm thực thi.

### 3.1. Khi shard key là một trường hashed

Giả sử collection được sharding theo:

~~~javascript
{ tenantId: "hashed" }
~~~

Các trường hợp thường gặp:

~~~javascript
// A. Equality trên toàn bộ shard key: thường tới một shard.
db.orders.find({ tenantId: "tenant-17" })

// B. Equality trên shard key và thêm điều kiện khác:
// vẫn có khả năng định tuyến tới một shard.
db.orders.find({ tenantId: "tenant-17", status: "PAID" })

// C. Nhiều giá trị shard key: có thể tới nhiều shard, nhưng
// không nhất thiết tất cả shard.
db.orders.find({ tenantId: { $in: ["tenant-17", "tenant-24"] } })

// D. Thiếu shard key: có nguy cơ scatter-gather.
db.orders.find({ orderId: "ORD-081" })

// E. Truy vấn khoảng trên giá trị gốc của hashed key:
// không được hưởng cách định tuyến theo khoảng của ranged key.
db.orders.find({ tenantId: { $gte: "tenant-10", $lt: "tenant-20" } })
~~~

Hashed shard key giúp phân bố các **giá trị khóa khác nhau**. Nó không tự chia nhỏ tập dữ liệu có **cùng một giá trị khóa**, ví dụ một tenant rất lớn; đây là một đánh đổi cần xem xét khi thiết kế hệ thống nhiều tenant.

### 3.2. Khi shard key là một tổ hợp ranged

Giả sử một collection khác dùng shard key:

~~~javascript
{ tenantId: 1, createdAt: 1 }
~~~

Lúc này `tenantId` là **tiền tố** của shard key; `createdAt` đứng sau. Hình dạng bộ lọc ảnh hưởng đến phạm vi chunk phải truy cập:

| Bộ lọc | Khả năng định tuyến | Giải thích |
| --- | --- | --- |
| `tenantId = t AND createdAt = d` | Có thể xác định vị trí một điểm trong không gian khóa | Bộ lọc cung cấp đầy đủ một giá trị khóa ghép |
| `tenantId = t AND createdAt >= d1 AND createdAt < d2` | Target các chunk của tenant trong khoảng ngày | Khoảng rộng có thể nằm trên nhiều shard |
| `tenantId = t` | Target các chunk thuộc tenant đó | Có thể tới nhiều shard nếu dữ liệu tenant trải trên nhiều chunk |
| `createdAt >= d1 AND createdAt < d2` | Thường phải quét nhiều hoặc toàn bộ shard | Thiếu tiền tố `tenantId` |
| `status = "PAID"` | Thường scatter-gather | Không liên hệ với shard key |

Không có quy tắc “có một trường của shard key là đủ”. Với shard key ghép, điều kiện trên **tiền tố phù hợp** thường giúp `mongos` khoanh vùng tốt hơn điều kiện chỉ nằm trên trường phía sau. Khoảng khóa lớn có thể chạm nhiều chunk và nhiều shard ngay cả khi bộ lọc chứa shard key.

### 3.3. Những trường hợp cần thận trọng

- **`_id`:** tìm theo `_id` không mặc nhiên target một shard nếu `_id` không phải shard key hoặc không giúp xác định shard key.
- **`$or`:** nếu một nhánh không thể khoanh vùng bằng shard key, khả năng định tuyến của toàn bộ truy vấn có thể trở nên rộng hơn; luôn xác minh bằng `explain`.
- **Aggregation:** một `$match` có điều kiện shard key, đặt sớm và được optimizer đẩy xuống phù hợp, có thể giảm shard tham gia. Các stage khác như `$group`, `$sort` hoặc `$lookup` vẫn có thể phát sinh công việc phân tán và khâu gộp.
- **Index thứ cấp:** index trên `orderId` giúp mỗi shard tìm nhanh hơn nhưng không làm `mongos` biết document nằm ở shard nào nếu query không chứa shard key.

## 4. Thực hành: tạo collection và quan sát định tuyến

Ví dụ sau giả định đã có một **sharded cluster**, kết nối tới `mongos` và cơ sở dữ liệu `shop`. Với môi trường production, việc bật sharding hoặc đổi shard key cần quy trình vận hành riêng; hãy chạy thực hành trên cụm thử nghiệm.

### 4.1. Chuẩn bị dữ liệu và index

Một document mẫu:

~~~javascript
{
  _id: ObjectId("66aa00000000000000000001"),
  tenantId: "tenant-17",
  orderId: "ORD-081",
  createdAt: ISODate("2026-11-12T09:30:00Z"),
  status: "PAID",
  total: NumberDecimal("1290000")
}
~~~

Ví dụ cấu hình shard key:

~~~javascript
use shop

// Hashed index để hỗ trợ hashed shard key.
db.orders.createIndex({ tenantId: "hashed" })

// Thực thi thông qua mongos, với collection đáp ứng yêu cầu
// về sharding/index của phiên bản MongoDB đang dùng.
sh.shardCollection("shop.orders", { tenantId: "hashed" })

// Index thứ cấp phục vụ lọc tenant, khoảng ngày và sort.
db.orders.createIndex({ tenantId: 1, createdAt: -1 })
~~~

Index `{ tenantId: 1, createdAt: -1 }` hỗ trợ cách tìm kiếm/sắp xếp thường gặp **bên trong shard đã được chọn**. Index này không thay đổi shard key của collection. Các ràng buộc về unique index, đặc biệt khi dùng hashed key, cần được đánh giá trước khi áp dụng trên dữ liệu thật.

### 4.2. So sánh các truy vấn

~~~javascript
// Truy vấn 1: có equality trên hashed shard key.
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50)

// Truy vấn 2: có orderId, không có tenantId.
db.orders.find({ orderId: "ORD-081" })

// Truy vấn 3: lọc đơn đã thanh toán trên toàn hệ thống.
db.orders.find({ status: "PAID" }).limit(50)
~~~

Trong cấu hình trên, truy vấn 1 thường target một shard; truy vấn 2 và 3 thiếu shard key nên thường scatter-gather. `limit(50)` hạn chế số kết quả trả về nhưng **không chứng minh** chỉ một shard được truy cập.

### 4.3. Dùng `explain` để kiểm chứng

~~~javascript
// Đo truy vấn có shard key.
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50)
  .explain("executionStats")

// Đo truy vấn thiếu shard key.
db.orders.find({
  orderId: "ORD-081"
}).explain("executionStats")
~~~

Khi đọc `explain` từ `mongos`, kiểm tra:

1. **Danh sách shard thực thi:** nhìn phần giải thích kế hoạch liên quan đến shard, xác định một shard, một nhóm shard hay tất cả shard.
2. **Index và plan:** xem truy vấn sử dụng `IXSCAN` hay `COLLSCAN`; chú ý bước sort và merge nếu xuất hiện.
3. **Khối lượng quét:** xem `totalKeysExamined`, `totalDocsExamined` và số kết quả trả về; các con số tổng có thể bao gồm nhiều shard.
4. **Thời gian:** đối chiếu `executionTimeMillis` và số liệu đo end-to-end bên ứng dụng; thời gian của `explain` không thay thế benchmark độ trễ production.

Tên stage và cấu trúc JSON của `explain` có thể khác nhau theo phiên bản MongoDB và loại truy vấn. Đừng viết công cụ giám sát phụ thuộc cứng vào một đường dẫn JSON chưa được xác nhận trên cluster thực tế.

Có thể quan sát trạng thái phân bố bằng:

~~~javascript
sh.status()
db.orders.getShardDistribution()
~~~

Phân bố dung lượng cân bằng **không bảo đảm** số request hay độ trễ cân bằng. Cần thêm metric từ từng shard và `mongos`.

## 5. Scatter-gather làm độ trễ tăng bằng cách nào?

Khi scatter-gather, `mongos` phát một truy vấn tới nhiều shard, chờ các phản hồi cần thiết, rồi hợp nhất kết quả. Với truy vấn phải chờ tất cả shard, có thể hình dung gần đúng:

\[
T_{\text{request}}
\approx T_{\text{routing}} +
\max_i(T_{\text{network},i} + T_{\text{execution},i}) +
T_{\text{merge}} + T_{\text{return}}
\]

Đây là **mô hình tư duy**, không phải công thức đo thời gian chính xác cho mọi lệnh. Một số truy vấn có thể trả kết quả sớm, giới hạn kết quả hoặc xử lý từng batch; thời gian thực tế còn phụ thuộc hàng đợi, sort, fetch, kích thước kết quả và cấu trúc pipeline.

Tuy nhiên, công thức cho thấy bốn nguồn chi phí chính.

### 5.1. Fan-out tăng số yêu cầu và tranh chấp tài nguyên

Với N shard, một targeted query chỉ gửi lệnh tới một shard có thể tạo một luồng xử lý chính. Scatter-gather có thể gửi tới N shard, tiêu tốn nhiều socket, CPU, IO và công việc quản lý cursor hơn. Nếu số yêu cầu đồng thời cao, fan-out còn khuếch đại tải toàn cụm.

Ví dụ minh họa: hệ thống có 12 shard và nhận 800 truy vấn/giây thiếu shard key. Một truy vấn có thể phát tới 12 shard, tạo ra tối đa khoảng **9.600 lượt xử lý shard/giây** cho riêng nhóm truy vấn này, trước khi tính các lệnh/batch phụ. Đây là phép ước lượng về **mức khuếch đại công việc**, không phải số đo thực tế hay khẳng định mỗi shard đều quét toàn bộ dữ liệu.

### 5.2. Độ trễ đuôi phụ thuộc shard chậm nhất

Nếu truy vấn phải thu thập kết quả từ tất cả shard, một shard chậm do disk IO, CPU, hàng đợi hoặc sự cố mạng có thể kéo dài toàn bộ thời gian phản hồi. Khi số shard tham gia tăng, xác suất gặp ít nhất một shard bị chậm cũng có thể tăng.

Trong một mô hình lý tưởng hóa, nếu xác suất mỗi shard bị chậm là `p`, các shard độc lập và truy vấn phải đợi tất cả, xác suất gặp **ít nhất một shard chậm** trong `N` shard là:

\[
P(\text{ít nhất một shard chậm}) = 1 - (1-p)^N
\]

Ví dụ `p = 1%` và `N = 8` cho xác suất xấp xỉ 7,7%. Đây chỉ là minh họa định tính cho *tail latency*: các shard thực tế có thể bị ảnh hưởng bởi nguyên nhân chung, phụ thuộc nhau, và không phải truy vấn nào cũng chờ mọi shard. Không dùng công thức này làm dự báo SLA.

### 5.3. Merge, sort và phân trang tốn thêm tài nguyên

Với truy vấn tìm kiếm phân tán, `mongos` có thể cần merge các cursor và kết quả từ nhiều shard. Khi có sort hoặc aggregation, khả năng thực thi phân tán phụ thuộc query plan:

- Một số bước lọc/sort có thể được đẩy xuống các shard.
- Phần gộp có thể chạy tại `mongos` hoặc một vị trí merge được chọn tùy pipeline và phiên bản.
- Các phép gộp theo nhóm, sort quy mô lớn hoặc pipeline mang tính blocking có thể tiêu tốn nhiều bộ nhớ, IO hoặc thời gian trước khi có kết quả cuối.

`limit` giúp giảm kích thước kết quả, nhưng không tự triệt tiêu công việc trên tất cả shard. Với phân trang sử dụng `skip` lớn, mỗi shard có thể vẫn phải xử lý nhiều bản ghi trước khi mongos hợp nhất; hãy đánh giá keyset pagination khi thích hợp.

### 5.4. Targeted query cũng không luôn nhanh

Một targeted query có thể bị chậm khi một shard chứa tenant quá lớn hoặc đang là **hot shard**. Tăng số shard không tự chia nhỏ mọi giá trị shard key giống nhau. Index thiếu, quét dữ liệu quá nhiều, khóa và tranh chấp IO vẫn cần xử lý riêng.

Vì vậy, đánh giá hiệu năng phải đo **cả số shard được target lẫn hiệu quả thực thi trên từng shard**.

## 6. Viết query định tuyến tốt với Spring Data MongoDB

### 6.1. Domain và mẫu truy vấn

Giả sử collection `shop.orders` được shard theo `{ tenantId: "hashed" }`. Định nghĩa domain:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id String id,
    String tenantId,
    String orderId,
    Instant createdAt,
    String status,
    BigDecimal total
) {}
~~~

Truy vấn danh sách theo tenant và thời gian:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final MongoTemplate mongoTemplate;

    public OrderQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Order> listOrders(
            String tenantId,
            Instant fromInclusive,
            Instant toExclusive) {
        Query query = new Query(
            Criteria.where("tenantId").is(tenantId)
                .and("createdAt").gte(fromInclusive).lt(toExclusive)
        );

        query.with(Sort.by(Sort.Direction.DESC, "createdAt"));
        query.limit(50);
        return mongoTemplate.find(query, Order.class);
    }

    public List<Order> listByStatusAcrossTenants(String status) {
        // Thiếu tenantId: có thể scatter-gather.
        return mongoTemplate.find(
            Query.query(Criteria.where("status").is(status)),
            Order.class
        );
    }
}
~~~

Với hashed shard key `tenantId`, phương thức `listOrders` cung cấp giá trị equality nên có cơ sở target một shard. `listByStatusAcrossTenants` phù hợp với tác vụ tổng hợp toàn hệ thống nếu thật sự cần dữ liệu mọi tenant, nhưng nên dự trù chi phí fan-out và tránh gọi quá thường xuyên ở đường API nhạy cảm độ trễ.

### 6.2. Repository method cũng phải chứa shard key

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    // Có tenantId: hỗ trợ mongos định tuyến theo shard key giả định.
    List<Order> findByTenantIdAndOrderId(
        String tenantId, String orderId);

    // Chỉ orderId: có thể scatter-gather nếu không biết tenantId.
    List<Order> findByOrderId(String orderId);
}
~~~

Tên repository method không quyết định số shard. Điều kiện MongoDB do Spring Data tạo ra mới là căn cứ định tuyến. Khi thiết kế API, nên truyền `tenantId` được xác minh từ ngữ cảnh người dùng vào lớp truy vấn mỗi khi ngữ nghĩa nghiệp vụ cho phép, đồng thời thực hiện kiểm tra quyền truy cập độc lập với cơ chế sharding.

**Lưu ý về `findById`:** `MongoRepository.findById(id)` thường lọc trên `_id`. Nếu shard key là `tenantId`, thao tác này không mặc nhiên target đúng shard. Với các nghiệp vụ truy cập theo tenant, có thể dùng method theo cặp `tenantId + orderId` hoặc truy vấn có cả tenant và ID.

### 6.3. Lấy `explain` cho query do ứng dụng tạo

Trong lúc điều tra hiệu năng, có thể chạy command `explain` tương đương qua `MongoTemplate`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

Document find = new Document("find", "orders")
    .append("filter", new Document("tenantId", "tenant-17"));

Document explain = mongoTemplate.executeCommand(
    new Document("explain", find)
        .append("verbosity", "executionStats")
);
~~~

Mã trên là ví dụ minh họa cách gọi command; ở ứng dụng thật nên chỉ bật `executionStats` trong luồng chẩn đoán có kiểm soát, với đúng database, filter và quyền thích hợp. Tránh đưa toàn bộ kết quả explain và dữ liệu nhạy cảm vào log công khai. Có thể dùng `mongosh` để kiểm chứng nhanh cùng query.

## 7. Phương pháp đo và xử lý khi scatter-gather làm chậm hệ thống

Không thể kết luận nguyên nhân chỉ từ một giá trị `executionTimeMillis`. Cần đo theo cùng workload và quan sát toàn tuyến.

### Bước 1: Ghi lại query shape từ ứng dụng

Với mỗi truy vấn chậm, xác định:

- Collection, bộ lọc, projection, sort, limit, aggregation và index hint (nếu có).
- Tần suất, số request đồng thời, tỷ lệ read/write và p50/p95/p99 latency.
- Có đủ shard key hay thiếu trường nào? Truy vấn lọc equality, range hay `$in`?
- Kích thước kết quả, số document/keys được quét, tỷ lệ dữ liệu của tenant lớn.

### Bước 2: Kiểm tra routing bằng `explain`

Chạy với dữ liệu và giá trị filter đại diện:

~~~javascript
// Query có giá trị shard key.
db.orders.find({
  tenantId: "tenant-17",
  orderId: "ORD-081"
}).explain("executionStats")

// Query thiếu shard key.
db.orders.find({
  orderId: "ORD-081"
}).explain("executionStats")
~~~

Hai truy vấn có điều kiện nghiệp vụ khác nhau; ở đây dùng để **so sánh cách định tuyến**, không phải benchmark tốc độ thuần túy. Muốn đo lợi ích thực tế, cần đánh giá tính đúng đắn và cùng tập dữ liệu mong đợi, đồng thời kiểm soát ảnh hưởng cache, tải nền và index.

### Bước 3: Xác định nút cổ chai

| Quan sát | Nguyên nhân có thể | Việc nên thử |
| --- | --- | --- |
| Hầu hết shard đều nhận query, mỗi shard xử lý ít dữ liệu | Thiếu shard key dẫn đến fan-out | Bổ sung điều kiện shard key khi nghiệp vụ cho phép |
| Chỉ một shard nhận query nhưng p99 vẫn cao | Hot shard, thiếu index, tài nguyên quá tải | Xem index, phân bố tenant, CPU/IO và contention |
| Mỗi shard quét nhiều document, `docsExamined` lớn | Bộ lọc/index không phù hợp | Thiết kế index hỗ trợ filter, sort và projection |
| `mongos` hoặc giai đoạn merge tốn thời gian | Gộp/sort/aggregation phân tán | Đẩy lọc sớm, giảm dữ liệu trả về, tối ưu pipeline |
| Độ trễ tăng khi tăng shard dù lượng dữ liệu mỗi shard giảm | Overhead fan-out, tail latency, mạng | Giảm shard tham gia; đo network và phân vị độ trễ |
| Dữ liệu phân bố đều nhưng một shard luôn nóng | Phân bố QPS lệch theo khóa | Đánh giá lại shard key và cách phân tán workload |

### Bước 4: Kiểm tra giải pháp trong môi trường đại diện

Đánh giá các thay đổi theo mức độ phù hợp với nghiệp vụ:

1. **Sửa API/query:** truyền thêm shard key đã biết; đưa `$match` phù hợp vào aggregation; tránh gọi tìm theo ID thiếu tenant nếu thiết kế cho phép.
2. **Tối ưu index:** bổ sung index cho truy vấn thường gặp ở shard đích; đo lại `keysExamined/docsExamined` thay vì chỉ kiểm tra có `IXSCAN`.
3. **Giảm công việc gộp:** hạn chế tập dữ liệu sớm, chọn projection cần thiết, tối ưu sort và phân trang; với báo cáo toàn hệ thống có thể cân nhắc dữ liệu tổng hợp riêng.
4. **Đánh giá thiết kế shard key:** nếu đa số truy vấn quan trọng không thể chứa shard key, cần cân nhắc chiến lược key phù hợp hơn hoặc resharding theo quy trình vận hành.
5. **Theo dõi kết quả:** so sánh số shard tham gia, throughput, p50/p95/p99 và mức sử dụng tài nguyên trước/sau thay đổi trong nhiều khung giờ.

Không nên đổi shard key chỉ vì một truy vấn bất thường đang fan-out. Cần so sánh chi phí tổng thể của read, write, dữ liệu lớn theo tenant, uniqueness và những truy vấn nền chạy định kỳ.

## 8. Những ngộ nhận dễ dẫn đến tối ưu sai

| Ngộ nhận | Thực tế |
| --- | --- |
| “Có index thì `mongos` biết chính xác shard chứa document.” | Index ở shard giúp thực thi trong shard; routing vẫn chủ yếu dựa vào shard key và metadata phân bố. |
| “Truy vấn trả về một document nên chỉ chạy trên một shard.” | Kết quả ít không đồng nghĩa truy vấn target một shard. |
| “`findById` luôn nhanh nhất trên sharded collection.” | Nếu `_id` không phải shard key, lookup theo `_id` có thể fan-out. |
| “Chỉ cần thêm `limit(1)` là hết scatter-gather.” | `limit` có thể giảm kết quả/công việc nhưng không làm xuất hiện shard key bị thiếu. |
| “Query có `tenantId` chắc chắn target một shard.” | Chỉ đúng tùy shard key; với shard key ghép ranged, một tenant có thể trải trên nhiều shard. |
| “Scatter-gather luôn chậm hơn mọi targeted query.” | Độ trễ phụ thuộc kích thước dữ liệu, cache, index, phân bố tải và cách merge; fan-out chủ yếu tăng chi phí và rủi ro độ trễ đuôi. |
| “Càng nhiều shard thì một truy vấn càng nhanh.” | Thêm shard có thể tăng số đích cần truy vấn và chi phí merge nếu query không có routing phù hợp. |
| “Thêm `shardKey` vào Java entity là đủ.” | Query filter phải thực sự mang điều kiện shard key; annotation mapping không tự sửa các truy vấn thiếu khóa. |

## 9. Bài tập phân tích

Một collection `payments` được shard theo `{ merchantId: 1, createdAt: 1 }`. API có ba loại truy vấn:

~~~javascript
// A. Báo cáo giao dịch của một merchant theo tuần.
db.payments.find({
  merchantId: "m-007",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-11-08T00:00:00Z")
  }
})

// B. Tra cứu một giao dịch chỉ bằng mã giao dịch.
db.payments.find({ paymentId: "P-88015" })

// C. Liệt kê mọi giao dịch trong tuần trên toàn hệ thống.
db.payments.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-11-08T00:00:00Z")
  }
})
~~~

**Hãy xác định:** truy vấn nào có cơ sở target tốt, truy vấn nào dễ scatter-gather? Việc thêm index `{ paymentId: 1 }` cho B có làm B target một shard không? Nếu merchant `m-007` có dữ liệu lớn, A có chắc chỉ tới một shard không?

**Hướng giải:**

- **A** dùng tiền tố `merchantId` và khoảng `createdAt`, vì vậy `mongos` có thể khoanh vùng các chunk cần truy cập. Nếu khoảng khóa nằm trên nhiều shard, A vẫn phải liên hệ với nhiều shard.
- **B** không có shard key nên có nguy cơ scatter-gather. Index `paymentId` giúp tìm nhanh ở *mỗi shard được hỏi*, không giúp `mongos` biết chính xác shard đích.
- **C** thiếu tiền tố `merchantId`; các chunk của nhiều merchant có thể chứa giao dịch cùng thời gian, nên truy vấn thường phải tìm rộng trên cụm.
- Với merchant rất lớn, dữ liệu của cùng merchant và các khoảng thời gian khác nhau có thể nằm ở nhiều chunk/shard. **Targeted A không bảo đảm single-shard.**

Khi đưa kết quả vào dự án thật, hãy chạy `explain("executionStats")` qua `mongos`, sau đó đo p95/p99 tại ứng dụng dưới tải gần production. Chỉ số quan trọng nhất là **truy vấn nào truy cập bao nhiêu shard, mỗi shard làm bao nhiêu việc và thời gian phản hồi của toàn bộ yêu cầu thay đổi ra sao**.
