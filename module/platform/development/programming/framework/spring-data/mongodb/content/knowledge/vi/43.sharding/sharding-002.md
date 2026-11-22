# Chọn shard key theo phân bố dữ liệu và mẫu truy vấn

## 1. Vì sao shard key quyết định hiệu quả của sharding?

Trong MongoDB, **shard key** là một trường hoặc tập hợp trường dùng để phân chia document của một sharded collection thành các khoảng dữ liệu (chunk) và phân phối chúng tới các shard. Khi ứng dụng gửi truy vấn qua `mongos`, hệ thống dựa vào shard key trong điều kiện lọc để xác định shard cần truy cập.

Một shard key tốt phải phục vụ đồng thời hai mục tiêu:

1. **Phân bố dữ liệu và lưu lượng hợp lý:** tránh một shard giữ phần lớn dung lượng, số lần ghi hoặc các truy vấn tốn tài nguyên.
2. **Định tuyến hiệu quả:** các truy vấn thường gặp có thể được chuyển tới ít shard nhất có thể, giảm truyền dữ liệu và công việc hợp nhất kết quả.

Hai mục tiêu này có thể xung đột. Ví dụ, phân phối ngẫu nhiên từng đơn hàng có thể giúp ghi đều hơn, nhưng màn hình liệt kê đơn hàng theo khách thuê (tenant) lại phải tìm ở nhiều shard. Vì vậy không thể chọn shard key chỉ bằng cách đếm số giá trị khác nhau của một trường.

Trong **Spring Data MongoDB**, `MongoTemplate` và repository vẫn gửi truy vấn MongoDB bình thường; việc định tuyến do cụm MongoDB xử lý. Tuy nhiên, cách thiết kế bộ lọc trong ứng dụng quyết định máy chủ có dùng được shard key để định tuyến hay không. Đây là phần thiết kế dữ liệu và truy vấn thuộc phạm vi Spring Data MongoDB, bên cạnh các chủ đề repository, index, aggregation và chẩn đoán hiệu năng.

### Mô hình ví dụ xuyên suốt

Giả sử hệ thống SaaS lưu đơn hàng của nhiều doanh nghiệp trong collection `shop.orders`:

~~~javascript
{
  _id: ObjectId("66aa00000000000000000001"),
  tenantId: "tenant-17",
  orderId: "ORD-2026-000081",
  createdAt: ISODate("2026-11-12T09:30:00Z"),
  status: "PAID",
  total: NumberDecimal("1290000")
}
~~~

Các màn hình và tác vụ có đặc điểm minh họa sau:

| Nghiệp vụ | Điều kiện truy vấn thường gặp | Tỷ lệ tham khảo |
| --- | --- | ---: |
| Liệt kê đơn hàng của một tenant theo thời gian | `tenantId = ?`, `createdAt` trong khoảng, sắp xếp mới nhất | 60% |
| Xem chi tiết một đơn hàng | `tenantId = ?`, `orderId = ?` | 25% |
| Báo cáo toàn hệ thống | Thống kê trên nhiều tenant, nhiều tháng | 10% |
| Tác vụ vận hành khác | Tra cứu hoặc cập nhật theo trạng thái | 5% |

Các tỷ lệ chỉ là **giả định để luyện cách ra quyết định**. Khi áp dụng thực tế, phải lấy số liệu từ log, tracing và workload production. Cũng cần đo lưu lượng ghi, kích thước document và số tenant hoạt động; chỉ nhìn tỷ lệ truy vấn đọc là chưa đủ.

## 2. Hiểu những đặc tính quan trọng của shard key

### 2.1. Cardinality: số lượng giá trị phân biệt

**Cardinality** là số giá trị khác nhau của một trường hoặc tổ hợp trường.

- `status` chỉ có vài giá trị như `NEW`, `PAID`, `CANCELLED`: cardinality thấp, thường không thích hợp làm shard key độc lập.
- `tenantId` có thể có hàng chục nghìn giá trị: cardinality tốt hơn, nhưng số đơn hàng giữa các tenant có thể chênh lệch rất lớn.
- `orderId` thường gần như duy nhất: cardinality cao, nhưng chưa chắc phù hợp cho các truy vấn lọc theo tenant.

Cardinality cao tạo điều kiện chia nhỏ dữ liệu, nhưng không tự bảo đảm tải đều. Một số ít giá trị có thể chiếm phần lớn dữ liệu hoặc lưu lượng. Với một shard key chỉ gồm `tenantId`, **mọi document mang cùng tenantId có cùng giá trị shard key**; không thể chia tập document đó thành nhiều khoảng shard key khác nhau chỉ nhờ balancer.

### 2.2. Frequency: phân bố số lần xuất hiện và truy cập

Ngoài số giá trị, cần quan sát:

- **Phân bố số document/dung lượng theo giá trị**: tenant nào chứa nhiều dữ liệu nhất?
- **Phân bố ghi theo giá trị**: tenant nào tạo đơn hàng liên tục?
- **Phân bố đọc theo giá trị**: có tenant nào nhận phần lớn yêu cầu truy vấn không?
- **Thay đổi theo thời gian**: giờ cao điểm, cuối tháng, chiến dịch khuyến mãi có làm tải dồn vào một nhóm khóa không?

Một key giúp dữ liệu cân đối tại thời điểm triển khai vẫn có thể tạo shard nóng khi một tenant phát sinh phần lớn số yêu cầu. Cần đo cả dung lượng **và** QPS/CPU/IO/độ trễ của từng shard.

### 2.3. Monotonicity: giá trị tăng hoặc giảm theo thời gian

Trường `createdAt`, mã tự tăng và một số dạng ID có tính **đơn điệu**. Nếu dùng shard key dạng range với giá trị liên tục tăng, bản ghi mới có thể tập trung vào khoảng cuối, khiến một shard tiếp nhận phần lớn ghi tại một thời điểm. Các shard khác vẫn có dữ liệu nhưng nhàn rỗi.

Hash một trường có giá trị phân biệt cao thường làm các bản ghi phân tán hơn. Đổi lại, các truy vấn **theo khoảng** trên trường đã hash không còn được định tuyến theo trật tự thời gian như range key.

### 2.4. Query locality: truy vấn có chứa shard key hay không?

Khi truy vấn cung cấp đủ thông tin để `mongos` khoanh vùng các chunk, nó có thể **target** một shard hoặc một tập con shard. Nếu thiếu điều kiện phù hợp, `mongos` có thể phải **scatter-gather**: gửi truy vấn tới nhiều hoặc tất cả shard rồi tổng hợp kết quả.

Không nên đồng nhất ba khái niệm:

- **Targeted query**: định tuyến tới các shard chứa các khoảng khóa liên quan; có thể vẫn hơn một shard nếu khoảng rộng.
- **Single-shard query**: trường hợp cụ thể chỉ cần một shard.
- **Scatter-gather query**: phải phát truy vấn rộng vì không thể xác định đủ vùng dữ liệu qua shard key.

Sự khác biệt rất quan trọng với shard key ghép. Một truy vấn có tiền tố của khóa có thể khoanh vùng dữ liệu nhưng không bảo đảm chỉ chạm một shard.

### 2.5. Tính ổn định và ràng buộc dữ liệu

Shard key nên dựa trên thuộc tính ít thay đổi trong vòng đời document. Việc cập nhật giá trị shard key hoặc đổi chiến lược sharding phức tạp hơn cập nhật một trường thông thường và có thể gây di chuyển dữ liệu.

Cần đánh giá trước các ràng buộc về index và uniqueness:

- Các unique index trên sharded collection chịu ràng buộc theo shard key; với kiểu range, yêu cầu tiền tố shard key là một phần quan trọng của thiết kế unique index.
- **Hashed index không hỗ trợ unique**. Không nên mặc định tính duy nhất toàn cụm được bảo đảm chỉ vì đã hash `orderId`.
- Nếu `_id` không phải shard key, cần hiểu giới hạn thực thi uniqueness của `_id` trong môi trường sharded và có chiến lược sinh ID phù hợp.
- Không thể chọn tùy ý trường array làm shard key. Shard key và index hỗ trợ phải đáp ứng giới hạn của phiên bản MongoDB đang vận hành.

Những điều kiện này có thể loại bỏ một phương án tưởng như tối ưu về hiệu năng.

## 3. So sánh các chiến lược shard key

| Kiểu shard key | Điểm mạnh | Đánh đổi / nguy cơ | Thường phù hợp khi |
| --- | --- | --- | --- |
| **Ranged**, ví dụ `{ tenantId: 1, createdAt: 1 }` | Có thể định tuyến theo tenant và khoảng thời gian; hỗ trợ locality | Tenant nóng; các ghi có thứ tự thời gian trong một vùng khóa có thể gây hotspot | Phần lớn truy vấn lọc tenant kèm khoảng ngày |
| **Hashed**, ví dụ `{ orderId: "hashed" }` | Phân tán các khóa có cardinality cao, giảm xu hướng ghi dồn vào một đầu dải | Truy vấn theo tenant hoặc khoảng ngày thường phải fan-out | Đọc/ghi chủ yếu theo ID đơn hàng |
| **Hashed theo tenant**, ví dụ `{ tenantId: "hashed" }` | Trải các tenant khác nhau lên các shard; tìm theo một tenant có thể nhắm đích | Tenant lớn vẫn có thể tập trung vào một shard; range theo tenant không còn lợi thế | Nhiều tenant tương đối đồng đều, truy vấn thường luôn biết tenant |
| **Compound hashed**, ví dụ `{ tenantId: 1, orderId: "hashed" }` | Có thể phân chia dữ liệu của một tenant lớn theo orderId; truy vấn có cả tenant và orderId định tuyến chính xác | Chỉ có tenant có thể chạm nhiều shard; truy vấn theo ngày cần index riêng | Tenant có quy mô lệch nhau, nhiều ghi, nhiều truy vấn theo định danh |

Không có một kiểu tốt nhất cho mọi hệ thống. Thứ tự trường trong shard key ghép cũng là lựa chọn thiết kế, vì `mongos` dùng các thành phần khóa theo cấu trúc index để xác định khoảng liên quan.

### Ví dụ định tuyến khi dùng `{ tenantId: 1, createdAt: 1 }`

| Bộ lọc | Đặc điểm định tuyến | Nhận xét |
| --- | --- | --- |
| `tenantId = "tenant-17" AND createdAt >= d1 AND createdAt < d2` | Khoanh vùng tốt theo tiền tố và khoảng thời gian | Phù hợp nghiệp vụ liệt kê đơn |
| `tenantId = "tenant-17"` | Khoanh vùng các chunk của tenant | Có thể liên quan nhiều chunk/shard nếu tenant lớn |
| `orderId = "ORD-..."` | Không có tiền tố shard key | Dễ thành scatter-gather dù có index phụ trên từng shard |
| `createdAt >= d1 AND createdAt < d2` | Thiếu tiền tố `tenantId` | Dễ phải tìm ở nhiều shard |
| `status = "PAID"` | Không chứa shard key | Thường fan-out trên toàn cụm |

**Lưu ý:** index phụ có thể làm thao tác tìm kiếm *bên trong từng shard* nhanh hơn, nhưng không tự biến truy vấn thiếu shard key thành truy vấn chỉ đến một shard.

### Khi nào thêm hashed suffix?

Giả sử một tenant chiếm 45% tổng đơn hàng và tạo 60% lượng ghi. Nếu chỉ chọn `tenantId`, phần dữ liệu mang cùng khóa rất khó phân tán. Có thể cân nhắc `{ tenantId: 1, orderId: "hashed" }` nếu `orderId` có đủ giá trị phân biệt và không thay đổi.

Điều này tạo khả năng chia dữ liệu của một tenant theo nhiều giá trị orderId; **không có nghĩa** MongoDB luôn cân bằng toàn bộ tenant ngay lập tức. Phân bố thực tế còn phụ thuộc kích thước chunk, vị trí split, balancer, phân bố tenant và lưu lượng theo khóa. Đồng thời, màn hình chỉ lọc `tenantId` sẽ có thể chạm nhiều shard hơn trước.

## 4. Quy trình chọn shard key từ số liệu thực tế

### Bước 1: Lập bảng workload

Với mỗi truy vấn, ghi lại:

1. Bộ lọc thực tế, đặc biệt là trường xuất hiện trong điều kiện bằng (`=`), khoảng (`>=`, `<`) và `$in`.
2. Tần suất, tỉ lệ đọc/ghi, p95/p99 latency và số document phải quét.
3. Số kết quả thường trả về, sort, pagination, aggregation và khả năng truy vấn đi kèm tenant.
4. Khả năng sửa code ứng dụng để luôn truyền điều kiện shard key, ví dụ lấy chi tiết đơn hàng bằng cặp `tenantId + orderId`.

Đừng chỉ lấy một truy vấn phổ biến nhất. Một truy vấn báo cáo chạy ít lần nhưng quét hàng trăm triệu document vẫn có thể chi phối chi phí tài nguyên.

### Bước 2: Đo phân bố dữ liệu theo candidate key

Kiểm tra số lượng giá trị phân biệt, phân vị kích thước tenant, số document/byte và tốc độ ghi trên nhóm lớn nhất. Có thể phân tích sơ bộ bằng aggregation trên môi trường thử nghiệm hoặc dữ liệu có phép đo phù hợp:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1 } },
  { $limit: 10 }
])
~~~

Pipeline này tìm tenant nhiều document nhất, **không** đo dung lượng byte hay QPS. Với dữ liệu lớn, cần chú ý chi phí aggregation và nên sử dụng hệ thống đo đạc hoặc thống kê được chuẩn bị sẵn. Để biết key có gây hotspot không, cần thêm lưu lượng ghi/đọc theo tenant trong nhiều khung giờ.

### Bước 3: Đánh giá từng candidate trên cùng bộ tiêu chí

| Tiêu chí | Câu hỏi kiểm tra |
| --- | --- |
| Phân bố | Key có đủ giá trị để chia chunk? Có nhóm giá trị nào chứa quá nhiều dữ liệu? |
| Ghi | Inserts mới rơi vào nhiều shard hay dồn về một dải khóa? |
| Đọc | Bao nhiêu phần trăm truy vấn thường gặp có thể được target? |
| Truy vấn tốn kém | Aggregation, export, tra cứu đặc biệt cần truy cập bao nhiêu shard? |
| Index và sort | Index hỗ trợ shard key có tương thích với bộ lọc và thứ tự sắp xếp chính? |
| Tính ổn định | Shard key có thường được cập nhật? Có nguy cơ thay đổi quy tắc phân tenant? |
| Uniqueness | Có cần bảo đảm orderId, mã hóa đơn hoặc khóa nghiệp vụ là duy nhất trên toàn cụm? |
| Vận hành | Khi tăng số shard, chi phí phân phối dữ liệu và nhu cầu resharding có chấp nhận được không? |

Nên loại bỏ trước các candidate vi phạm yêu cầu cứng, sau đó so sánh hiệu năng trên dữ liệu mô phỏng sát production. Không dùng một điểm số tổng hợp tùy ý thay cho kiểm thử.

### Bước 4: Đưa ra lựa chọn theo workload, kèm điều kiện thay đổi

Với workload giả định ở phần đầu, có thể chọn `{ tenantId: 1, createdAt: 1 }` **nếu** dữ liệu của từng tenant đủ cân đối, truy vấn liệt kê theo khoảng ngày quan trọng nhất, và không có tenant gây tải ghi quá lớn.

Nếu vài tenant lớn chi phối phần lớn dữ liệu hoặc ghi, cần thử thêm `{ tenantId: 1, orderId: "hashed" }` hoặc một chiến lược dữ liệu khác. Chi phí phải đánh giá là fan-out của truy vấn liệt kê theo tenant/ngày và index bổ sung; thêm hashed suffix không phải giải pháp miễn phí.

Nếu phần lớn yêu cầu là đọc/ghi một đơn hàng độc lập theo `orderId`, shard key `{ orderId: "hashed" }` có thể thực dụng hơn. Tuy nhiên API tenant-aware vẫn phải thực hiện kiểm tra quyền truy cập ở tầng ứng dụng; việc một query target được shard không thay thế kiểm soát dữ liệu theo tenant.

## 5. Thực hành trong MongoDB

Giả sử đã có một cụm sharded MongoDB và thao tác qua `mongos`. Phương án minh họa là shard collection `shop.orders` theo `tenantId` và `createdAt`.

### Tạo index và khai báo shard key

~~~javascript
use shop

// Index hỗ trợ shard key theo range.
db.orders.createIndex({ tenantId: 1, createdAt: 1 })

// Thực hiện qua mongos, sau khi kiểm tra cấu hình cluster,
// index hiện có và các ràng buộc của collection.
sh.shardCollection("shop.orders", { tenantId: 1, createdAt: 1 })
~~~

Đây là thao tác thay đổi cấu trúc phân bố dữ liệu, nên cần thực hiện trên môi trường thử nghiệm trước. Các collection có dữ liệu hoặc unique index hiện hữu phải được kiểm tra theo yêu cầu của phiên bản MongoDB đang dùng. Bản thân index tạo trong ví dụ chưa bảo đảm workload đã tối ưu.

### So sánh truy vấn có và không có shard key

~~~javascript
// Màn hình liệt kê đơn theo tenant và khoảng thời gian:
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50)

// Tra cứu theo orderId mà không biết tenant:
db.orders.find({ orderId: "ORD-2026-000081" })
~~~

Với shard key đã chọn, truy vấn đầu có đủ tiền tố và khoảng thời gian để `mongos` thu hẹp các chunk cần tìm. Truy vấn thứ hai thiếu shard key, vì vậy có nguy cơ đi tới tất cả shard.

Đo chứ không suy đoán số shard được truy cập:

~~~javascript
db.orders.find({
  tenantId: "tenant-17",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).explain("executionStats")

db.orders.find({
  orderId: "ORD-2026-000081"
}).explain("executionStats")

sh.status()
db.orders.getShardDistribution()
~~~

Trong kết quả `explain`, xem các shard thực sự tham gia, plan sử dụng index, `totalKeysExamined`, `totalDocsExamined` và thời gian thực thi. Cấu trúc trường trong output có thể thay đổi giữa phiên bản và kiểu query; cần xem trực tiếp các stage liên quan đến shard. `sh.status()` cùng `getShardDistribution()` giúp quan sát trạng thái phân bố, nhưng để kết luận cân bằng tải phải kết hợp metric CPU, IO, network và latency theo shard.

### Nếu thử phương án compound hashed

Phương án sau là **một thiết kế thay thế để kiểm nghiệm**, không chạy đè lên collection đã shard theo ví dụ trên:

~~~javascript
// Ví dụ chuẩn bị index cho một collection/thí nghiệm riêng.
db.orders_candidate.createIndex({ tenantId: 1, orderId: "hashed" })

// Chỉ chạy khi collection tương ứng chưa được shard
// và đã đáp ứng các điều kiện của cluster.
sh.shardCollection(
  "shop.orders_candidate",
  { tenantId: 1, orderId: "hashed" }
)
~~~

Khi đó truy vấn `{ tenantId: "tenant-17", orderId: "ORD-..." }` xác định một giá trị shard key đầy đủ; truy vấn chỉ có `tenantId` thường vẫn target được theo tiền tố nhưng có thể tìm trên nhiều shard. Truy vấn theo `createdAt` cần một index phù hợp để giảm số document phải quét tại các shard liên quan. Chú ý thiết kế khóa duy nhất nếu `orderId` phải unique; hashed index không phải unique index.

## 6. Thiết kế truy vấn với Spring Data MongoDB

Spring Data MongoDB không tự thêm `tenantId` hoặc khoảng ngày vào truy vấn chỉ vì collection được shard. Nhà phát triển phải truyền những trường đó theo đúng ngữ nghĩa nghiệp vụ.

Ví dụ domain đơn giản:

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

Truy vấn danh sách bằng `MongoTemplate`:

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

    public List<Order> findOrders(
            String tenantId,
            Instant fromInclusive,
            Instant toExclusive,
            int requestedLimit) {
        int limit = Math.min(Math.max(requestedLimit, 1), 100);

        Query query = new Query(
                Criteria.where("tenantId").is(tenantId)
                        .and("createdAt").gte(fromInclusive).lt(toExclusive)
        );

        query.with(Sort.by(Sort.Direction.DESC, "createdAt"));
        query.limit(limit);
        return mongoTemplate.find(query, Order.class);
    }
}
~~~

Điều kiện `tenantId` kèm `createdAt` giúp server định tuyến theo shard key dạng range đã chọn. Lệnh sort giảm dần có thể tận dụng việc quét ngược một index tương thích tùy plan thực tế; vẫn cần xác minh bằng `explain`. Giới hạn số kết quả giúp giảm dữ liệu truyền đi, nhưng không khắc phục được fan-out nếu bộ lọc thiếu shard key.

Cách khai báo tương đương bằng repository có thể là:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndCreatedAtGreaterThanEqualAndCreatedAtLessThan(
            String tenantId, Instant fromInclusive, Instant toExclusive);
}
~~~

Repository biểu diễn điều kiện nghiệp vụ; quyền định tuyến vẫn ở MongoDB. Với API trả về tập lớn, nên dùng phân trang hoặc cơ chế duyệt phù hợp và kiểm tra index/sort của query thực tế.

Khi cập nhật hoặc xóa một đơn hàng, nên đưa các giá trị shard key đã biết vào bộ lọc để máy chủ có khả năng xác định đích chính xác. Không nên giả định thao tác tìm theo `_id` luôn được route hiệu quả nếu `_id` không thuộc shard key.

## 7. Kiểm chứng lựa chọn trước khi vận hành

Một shard key chỉ đạt yêu cầu khi được kiểm chứng bằng workload có phân bố sát thực tế. Chuẩn bị bộ dữ liệu với tenant nhỏ, vừa và rất lớn, thời gian tạo đơn thực tế và tỷ lệ đọc/ghi cao điểm.

**Kiểm tra định tuyến và độ trễ:**

- Chạy `explain("executionStats")` cho các truy vấn đại diện: theo tenant/ngày, theo orderId, các truy vấn báo cáo và cập nhật.
- Ghi nhận số shard tham gia, `totalKeysExamined`, `totalDocsExamined`, độ trễ p50/p95/p99 và tỷ lệ yêu cầu target được.
- Đối chiếu query plan với tập index đang có; tránh tạo nhiều index không cần thiết vì index làm tăng chi phí ghi và dung lượng.

**Kiểm tra phân bố và khả năng mở rộng:**

- So sánh số document, kích thước dữ liệu, dung lượng index và tốc độ tăng trưởng giữa các shard.
- Quan sát ghi/đọc theo shard trong giờ cao điểm; không suy ra cân bằng tải chỉ từ số document.
- Bổ sung shard trong môi trường thử nghiệm để xem chunk phân phối lại ra sao, có khoảng khóa/tenant nào không thể chia đủ nhỏ hay không.
- Kiểm tra tác động của di chuyển chunk, balancer và các truy vấn dài tới độ trễ của ứng dụng.

**Kiểm tra các ràng buộc nghiệp vụ:**

- Thử trường hợp tenant lớn nhất, giá trị thiếu/null, dữ liệu cũ và quy tắc sinh `orderId`.
- Xác nhận thiết kế unique index, phạm vi duy nhất của mã nghiệp vụ và cách sinh `_id`.
- Kiểm tra đường đi của query từ controller/service/repository để không vô tình bỏ `tenantId` trong thao tác truy cập dữ liệu tenant.

Nếu một candidate cân bằng dung lượng nhưng vẫn tạo p99 latency cao khi ghi, cần điều chỉnh thiết kế shard key hoặc hình dạng truy vấn. Thay đổi shard key sau khi dữ liệu đã lớn có thể cần resharding với chi phí vận hành đáng kể, nên phải dự trù sớm.

## 8. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chọn `status` vì rất hay lọc | Cardinality thấp; nhiều document cùng giá trị khó phân chia | Dùng trường/khóa ghép phân biệt tốt hơn; giữ index theo status nếu cần |
| Chọn `createdAt` dạng range vì dữ liệu luôn có thời gian | Ghi mới dồn vào cuối khoảng shard key | Đánh giá hashed key hoặc khóa ghép dựa trên pattern truy cập |
| Hash `tenantId` và cho rằng tenant lớn sẽ tự chia đều | Cùng giá trị tenant vẫn ánh xạ về cùng vị trí khóa hash | Thử key ghép cho phép chia nhỏ bên trong tenant |
| Chỉ nhìn dung lượng cân đối | Một shard có thể nóng do QPS cao dù dữ liệu không nhiều | Đo thêm write/read throughput, CPU/IO, latency |
| Thêm index cho `orderId` rồi kỳ vọng truy vấn chỉ tới một shard | Index riêng giúp tìm trong shard, không thay thế shard key khi route | Bổ sung shard key vào API khi có thể; hoặc đánh giá lại chiến lược |
| Dùng khóa ghép nhưng query bỏ trường tiền tố | Truy vấn dễ mở rộng sang nhiều shard | Thiết kế query theo đúng shard key prefix và kiểm tra `explain` |
| Chọn shard key mà chưa xét unique constraint | Có thể không tạo được unique index mong muốn | Xác định yêu cầu uniqueness trước khi chốt key |
| Đưa hashed suffix vào mọi collection | Phá locality của một số truy vấn theo khoảng; tăng fan-out | Chỉ dùng khi phân bố và write hotspot biện minh được đánh đổi |

## 9. Tình huống tự đánh giá

Hệ thống có 20.000 tenant. Phần lớn tenant chỉ có vài nghìn đơn, nhưng 5 tenant lớn nhất chiếm 55% tổng số đơn và 70% số lượt ghi. Truy vấn đọc chủ yếu là:

~~~javascript
db.orders.find({
  tenantId: "tenant-big-1",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
})
~~~

**Câu hỏi:** Nên chọn `{ tenantId: "hashed" }` hay `{ tenantId: 1, orderId: "hashed" }`?

**Gợi ý phân tích:**

1. Với `{ tenantId: "hashed" }`, phần dữ liệu của một tenant vẫn có một giá trị shard key. Năm tenant lớn có thể tiếp tục tạo chênh lệch dung lượng và write load.
2. Với `{ tenantId: 1, orderId: "hashed" }`, khóa của tenant lớn có thể được chia theo orderId, nhờ đó có cơ hội phân tán ghi và dung lượng tốt hơn.
3. Tuy nhiên, truy vấn tenant + khoảng ngày không có giá trị orderId, nên có thể phải đọc ở nhiều shard. Index theo `{ tenantId: 1, createdAt: 1 }` vẫn hữu ích *bên trong* các shard nhưng không loại bỏ fan-out.
4. Kết luận chỉ nên đưa ra sau khi chạy benchmark với dữ liệu và QPS đại diện, so sánh p95/p99 của truy vấn liệt kê, write hotspot, độ phân bố và chi phí vận hành.

Nếu truy vấn theo khoảng ngày là nghiệp vụ cực kỳ nhạy cảm với độ trễ, có thể cần xem xét lại partitioning ở mức nghiệp vụ, tối ưu API hoặc giải pháp lưu báo cáo riêng. Không nên hứa rằng một shard key đơn lẻ sẽ đồng thời tối ưu mọi loại truy vấn.

## 10. Ghi nhớ khi thiết kế

Việc chọn shard key bắt đầu từ **phân bố giá trị và lưu lượng**, tiếp tục bằng **mẫu truy vấn thực tế**, rồi mới đến quyết định dùng ranged, hashed hay compound hashed. Một khóa có cardinality cao vẫn có thể tệ nếu query không chứa khóa; một khóa định tuyến tốt vẫn có thể tệ nếu dồn ghi vào một shard.

Với Spring Data MongoDB, cần thiết kế filter ở service/repository sao cho truyền đủ shard key khi nghiệp vụ cho phép, kiểm tra plan trên `mongos` và theo dõi hiệu năng sau khi tăng dữ liệu hoặc shard. Quyết định tốt là quyết định có thể giải thích bằng workload, metric và kết quả kiểm chứng.
