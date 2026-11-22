# Điểm nóng ghi, dữ liệu lệch và truy vấn thiếu shard key

**Sharding** chia dữ liệu một collection MongoDB thành nhiều phần, lưu trên nhiều **shard** để tăng khả năng lưu trữ và phân tán tải. Tuy nhiên, có nhiều shard không đồng nghĩa workload sẽ được chia đều. Một **shard key** chọn sai có thể khiến phần lớn writes tập trung vào một shard, một số shard sở hữu nhiều dữ liệu hơn phần còn lại, hoặc mọi request phải đi qua tất cả shard dù chỉ trả về một document.

Ba triệu chứng tiêu biểu:

1. **Điểm nóng ghi (write hotspot):** nhiều insert/update đồng thời đều tới cùng một vùng shard key, chunk hoặc shard. Một shard bận trong khi shards khác nhàn.
2. **Dữ liệu lệch (data skew):** dung lượng, số document, số range/chunk, hoặc số lượng giá trị shard key không phân bố hợp lý. Một số vùng chứa quá nhiều dữ liệu hoặc không thể tách hiệu quả.
3. **Truy vấn thiếu shard key:** `mongos` không xác định được shard chứa document cần tìm, nên phải **broadcast/scatter-gather** tới nhiều hoặc tất cả shards; độ trễ, kết nối, CPU và network có thể tăng theo số shard.

Đặc biệt, ba vấn đề **không đồng nhất**: dữ liệu 50/50 trên hai shard vẫn có thể mang tải 95/5 nếu 95% requests đổ vào một khách hàng; ngược lại số chunk không bằng nhau không nhất thiết chứng minh mất cân bằng dung lượng hay QPS. Cách xử lý phải bắt đầu bằng **phân biệt dạng lệch**, đọc **query patterns** và kiểm chứng bằng metrics/`explain`.

Bài thuộc chương **Sharding** của module *Database Engine Document MongoDB*. Trọng tâm là cách đánh giá shard key, nhận diện nguyên nhân, sửa query để targeted, kiểm tra balancer và hoạch định thay đổi shard key an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vai trò của `mongos`, config servers, shards, shard key và chunks/ranges.
- Phân biệt **range sharding** với **hashed sharding**, biết đánh đổi giữa write spread và range-query locality.
- Giải thích vì sao shard key có giá trị **tăng/giảm đơn điệu** có thể tạo điểm nóng ghi.
- Nhận diện **low cardinality**, **high frequency**, **hot tenant** và rủi ro indivisible/jumbo chunks.
- Đánh giá khác biệt giữa **data skew**, **chunk skew**, **working-set skew**, **read skew** và **write skew**.
- Viết và kiểm chứng **targeted queries** bằng đủ shard key hoặc prefix của compound shard key khi thích hợp.
- Phát hiện `scatter-gather` bằng `explain` và hiểu khi nào broadcast là chấp nhận được.
- Dùng `sh.status()`, `getShardDistribution()`, `getShardedDataDistribution()`, balancer status và `analyzeShardKey` để hỗ trợ chẩn đoán.
- Lập kế hoạch cải tiến index, shard key, routing, data model, zone placement hoặc resharding có kiểm soát.
- Nhận biết các tác động đến `updateOne`, `updateMany`, `deleteMany`, upsert, unique index và Java Driver.

> **Phiên bản và phạm vi:** Cú pháp minh họa dùng MongoDB hiện đại và `mongosh` qua một **sharded cluster** có quyền quản trị phù hợp. Thao tác `sh.shardCollection()`, `reshardCollection`, zone balancing hoặc thay đổi index không dành cho môi trường production nếu chưa có kế hoạch. Các khả năng như `analyzeShardKey` (MongoDB 7.0+), `sh.getShardedDataDistribution()` (MongoDB 6.0.3+) hay cách phân phối chunk ban đầu thay đổi theo bản server. Đối chiếu tài liệu đúng phiên bản, FCV và Atlas/self-managed topology.

## 1. Kiến trúc định tuyến shard cơ bản

Một MongoDB sharded cluster gồm ba nhóm thành phần chính:

~~~text
Java service / mongosh / application
                |
                v
         mongos (query router)
                |
        +-------+-------+
        |       |       |
        v       v       v
      Shard 0 Shard 1 Shard 2
      replica replica replica
       set     set     set
        ^       ^       ^
        |       |       |
       Config servers: metadata / chunk ranges
~~~

Ứng dụng thông thường kết nối **`mongos`**, không tự chọn shard bằng phép modulo ID rồi mở connection trực tiếp tới các `mongod` shard. Query router dùng **cluster metadata và shard key** để xác định shard nào cần tham gia.

### 1.1. Các khái niệm quan trọng

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Shard** | Một đơn vị lưu phần dữ liệu, thường là replica set. |
| **`mongos`** | Query router nhận request, định tuyến tới shard cần thiết, tổng hợp kết quả nếu nhiều shard tham gia. |
| **Config Server Replica Set** | Lưu metadata về phân vùng, shard membership, zone/range mapping. |
| **Shard key** | Một hoặc nhiều fields dùng để quyết định phân bố dữ liệu và routing; có thể ranged, hashed hoặc compound. |
| **Chunk / range** | Một khoảng liên tiếp theo không gian shard key; shard sở hữu range đó. |
| **Balancer** | Theo dõi lượng dữ liệu theo shard/collection và di chuyển ranges để cân bằng khi cần, có xét zone constraints. |
| **Targeted operation** | Router xác định một shard hoặc một tập shard nhỏ từ predicate và metadata. |
| **Broadcast/scatter-gather** | Router gửi query tới nhiều/tất cả shard, nhận results rồi merge. |
| **Resharding** | Thay đổi shard key và/hoặc tái phân bố collection theo cơ chế hỗ trợ. |

### 1.2. Cách một request được định tuyến

Với shard key giả định `{tenantId:1, orderId:1}`:

~~~javascript
// Có đủ hai thành phần -> cơ hội định tuyến tới một shard.
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-107"
})
~~~

`mongos` tìm range sở hữu cặp shard key tương ứng. Nếu query chỉ có `orderId` mà bỏ thành phần dẫn đầu `tenantId`, router có thể không xác định được range cần tìm:

~~~javascript
db.orders.findOne({ orderId: "ORD-107" })
// Có thể phải dò nhiều shard để tìm document.
~~~

Lưu ý: **index** và **shard targeting** là hai việc khác nhau. Một index `{orderId:1}` trên từng shard có thể khiến phép tìm **trong mỗi shard** nhanh, nhưng không tự báo cho `mongos` shard nào sở hữu orderId. Query vẫn có thể phát tới tất cả shards.

### 1.3. Vì sao thêm shard không chắc chữa được chậm?

Giả sử hệ thống có bốn shard, nhưng mọi insert mới đều mang giá trị `createdAt` tăng liên tục và chỉ đổ vào range cuối. Việc thêm shard thứ năm không làm năm shard cùng nhận insert mới trong cùng thời điểm. Hoặc nếu API tìm email bằng `email` trong khi shard key là `tenantId`, mỗi request có thể phải gửi đến cả năm shards. Càng nhiều shards, fan-out overhead có thể càng rõ.

**Sharding mở rộng năng lực phân tán khi shard key và truy vấn có thể tận dụng việc phân tán đó.**

## 2. Ba loại mất cân bằng và cách nhận dạng

Không nên dùng duy nhất nhãn “shard lệch” cho mọi biểu hiện.

| Dạng lệch | Ví dụ đo | Nguyên nhân thường gặp | Biện pháp có thể xem xét |
|---|---|---|---|
| **Data size skew** | Shard A 900 GB, B 250 GB, C 280 GB cùng collection | Ranges lớn, balancer chậm, zones, indivisible chunk | Balancer/zone/range investigation, reshard nếu key kém. |
| **Chunk-count skew** | A 100 chunks, B 50, C 52 | Kích thước chunks khác nhau, chính sách distribution, migration | Không kết luận chỉ bằng chunk count; kiểm tra owned bytes. |
| **Read/load skew** | A 12k reads/s, B 1k, C 900 | Hot tenant/key/range, missing cache, query tập trung | Query/index/data placement/tenant partition. |
| **Write skew** | A 9k writes/s, B/C rất ít | Monotonic key, hot key, app behavior | Hashed/compound key, bucketed writes, repartition. |
| **Working-set skew** | A có 20 GB data hot với RAM 8 GB, B có 100 GB data cold | Access pattern, index size, tenant hotspots | Memory/index/workload isolation, shard key/zone. |
| **Scatter-gather overhead** | Mỗi read API chạm 8/8 shards | Predicate thiếu shard key, query đi theo secondary key | API bổ sung shard key, key choice/lookup strategy. |
| **Migration imbalance** | Balancer migrations thất bại/chậm | Jumbo/indivisible chunks, disk/network/DDL, zones | Kiểm tra status/logs/range distribution. |

### 2.1. Dung lượng đều không có nghĩa tải đều

Ví dụ đo:

| Shard | Owned data | Reads/s | Writes/s |
|---|---:|---:|---:|
| `shardA` | 310 GB | 9.500 | 8.200 |
| `shardB` | 305 GB | 600 | 500 |
| `shardC` | 315 GB | 750 | 520 |

Đây là **số liệu minh họa**, không phải benchmark MongoDB. Data size gần như bằng nhau nhưng **shardA là hot shard**. Balancer dựa vào phân bố dữ liệu có thể thấy cluster đã cân bằng, trong khi CPU/IOPS của A vẫn gần bão hòa.

### 2.2. Số chunk đều không có nghĩa data đều

Hai shard đều 100 chunks không chứng minh dung lượng bằng nhau: một số ranges có thể chứa documents lớn hơn hoặc số lượng document khác nhau. Cần xem **ownedSizeBytes**, `numOwnedDocuments` và metrics workload thực tế, đặc biệt khi chunk size và cơ chế phân vùng thay đổi theo phiên bản.

### 2.3. Tính chọn lọc của shard key

Shard key có ba đặc điểm quan trọng:

- **Cardinality:** số lượng giá trị khác nhau, ảnh hưởng khả năng chia range/chunk.
- **Frequency distribution:** một giá trị có lặp lại quá nhiều không (ví dụ một `tenantId` chiếm 85% orders).
- **Monotonicity:** các giá trị mới có luôn tăng/giảm như timestamp hoặc sequential ID không?

Một key có cardinality cao nhưng tăng đơn điệu vẫn có thể tạo **insert hotspot**. Một key phân tán hash đều nhưng application chỉ truy vấn một tenant vẫn có thể có **hot tenant**. Không chọn shard key chỉ dựa vào một thuộc tính.

## 3. Mô hình dữ liệu minh họa và lab sharding an toàn

Bài dùng **orders** của một nền tảng bán hàng đa tenant:

~~~javascript
{
  _id: "O-1001",
  orderId: "O-1001",
  tenantId: "T-A",
  customerId: "C-10",
  status: "PAID",
  createdAt: ISODate("2026-06-01T09:00:00Z"),
  totalMinor: NumberLong(125000)
}
~~~

Một ngày sản phẩm có thể nhận hàng chục triệu đơn, nhưng 80% khách hàng thuộc một vài tenants lớn. Những API thường gặp:

- `GET /tenants/T-A/orders/O-1001` → lấy order bằng **tenant + order ID**.
- `GET /orders/O-1001` → lấy order chỉ bằng **order ID**.
- `GET /tenants/T-A/orders?from=...&to=...` → danh sách theo **tenant và ngày**.
- `GET /tenants/T-A/orders?status=PAID` → lọc theo **tenant và status**.
- Admin dashboard → tổng số PAID và doanh thu **mọi tenant** theo kỳ.
- Dịch vụ import → insert khối lượng lớn với `createdAt` tăng liên tục.

Các access patterns này **xung đột**: key `{createdAt:1}` tiện cho báo cáo khoảng thời gian nhưng có nguy cơ nóng ghi, `{orderId:"hashed"}` phân tán inserts nhưng truy vấn theo thời gian có thể fan out, còn `{tenantId:1,orderId:1}` hữu ích cho tenant-scoped lookup nhưng có nguy cơ một tenant rất lớn chi phối ranges.

### 3.1. Chỉ tạo dữ liệu trên database lab

Script sau là **ví dụ độc lập trong `mongosh`**. Nó tạo dữ liệu mẫu trong một database mới, không xóa gì và không thực hiện thay đổi shard topology.

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

const docs = [
  {
    _id: "O-1001", orderId: "O-1001", tenantId: "T-A",
    customerId: "C-10", status: "PAID",
    createdAt: ISODate("2026-06-01T09:00:00Z"),
    totalMinor: NumberLong(125000)
  },
  {
    _id: "O-1002", orderId: "O-1002", tenantId: "T-A",
    customerId: "C-10", status: "CREATED",
    createdAt: ISODate("2026-06-02T09:00:00Z"),
    totalMinor: NumberLong(70000)
  },
  {
    _id: "O-1003", orderId: "O-1003", tenantId: "T-B",
    customerId: "C-20", status: "PAID",
    createdAt: ISODate("2026-06-03T09:00:00Z"),
    totalMinor: NumberLong(95000)
  },
  {
    _id: "O-1004", orderId: "O-1004", tenantId: "T-C",
    customerId: "C-30", status: "SHIPPED",
    createdAt: ISODate("2026-06-04T09:00:00Z"),
    totalMinor: NumberLong(150000)
  },
  {
    _id: "O-1005", orderId: "O-1005", tenantId: "T-A",
    customerId: "C-11", status: "PAID",
    createdAt: ISODate("2026-06-05T09:00:00Z"),
    totalMinor: NumberLong(190000)
  },
  {
    _id: "O-1006", orderId: "O-1006", tenantId: "T-B",
    customerId: "C-22", status: "CANCELLED",
    createdAt: ISODate("2026-06-06T09:00:00Z"),
    totalMinor: NumberLong(35000)
  }
]

lab.orders_local.insertMany(docs)

lab.orders_local.find(
  {},
  { _id: 0, orderId: 1, tenantId: 1, status: 1, createdAt: 1 }
).sort({ orderId: 1 })
~~~

Chạy lại script với `_id` đã tồn tại sẽ báo duplicate key, không phải sự cố sharding. Nếu muốn học riêng từng thiết kế, tạo những collections lab mới và copy fixture **chỉ trong database thử nghiệm**.

### 3.2. Demo ba cách shard khác nhau

Để so sánh, một **cluster lab đã có ít nhất hai shards và kết nối qua `mongos`** có thể tạo ba collections tách biệt. **Các lệnh sau là mẫu cấu hình quản trị; chỉ chạy sau khi hiểu ảnh hưởng, đã xác minh môi trường lab và có quyền thích hợp.** Không áp dụng lên collection đang phục vụ production.

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

// Ba collections giả định có dữ liệu riêng và indexes phù hợp.
// Mỗi dòng sh.shardCollection minh họa một phương án shard key.

// A. Range theo timestamp: minh họa rủi ro hot newest-range.
sh.shardCollection(
  "shard262_lab.orders_ranged",
  { createdAt: 1 }
)

// B. Hashed theo orderId: rải IDs tăng đều hơn theo hash.
sh.shardCollection(
  "shard262_lab.orders_hashed",
  { orderId: "hashed" }
)

// C. Compound range theo tenantId + orderId.
sh.shardCollection(
  "shard262_lab.orders_tenant",
  { tenantId: 1, orderId: 1 }
)
~~~

Với collection có sẵn dữ liệu, việc chọn key, index tương thích, unique constraints, chunk initialization và quyền DDL phải đáp ứng yêu cầu server/cluster. Trong lab, cần tạo các collections `orders_ranged`, `orders_hashed`, `orders_tenant` và nạp dữ liệu khi học, không nhầm rằng việc chạy mẫu chỉ tạo shard topology sẽ tự sao chép dữ liệu từ `orders_local`. Khi collection chỉ có vài document, planner/balancer cũng có thể chưa phân bổ sang nhiều shards; **một fixture sáu orders không chứng minh khả năng phân tán tải thực tế**.

### 3.3. Một chỉ dẫn kiểm tra môi trường

Khi mở `mongosh`, có thể xác minh router:

~~~javascript
db.adminCommand({ hello: 1 })
// Với mongos, kết quả thông thường có:
//   msg: "isdbgrid"
~~~

Và xem sharding metadata:

~~~javascript
sh.status()
~~~

`sh.status()` có ý nghĩa khi kết nối **`mongos`**. Nếu đang nối thẳng đến standalone hoặc một shard `mongod`, một số lệnh sharding sẽ báo lỗi/không có thông tin như mong đợi. Không nên chạy DDL thử để “xem có hoạt động không” trên production.

## 4. Điểm nóng ghi do shard key tăng hoặc giảm đơn điệu

Một shard key như `{createdAt:1}` hoặc ID tuần tự có thể khiến các inserts gần đây liên tục vào **cùng vùng cuối** của không gian khóa.

### 4.1. Range sharding chia theo khoảng khóa

Giả sử các chunks hiện tại:

~~~text
createdAt ranges (min inclusive, max exclusive)

Shard A: (-∞, 2026-03-01)
Shard B: [2026-03-01, 2026-05-01)
Shard C: [2026-05-01, +∞)
                                 ^
                     tất cả đơn mới trong tháng 6
                     đều rơi vào range cuối ở Shard C
~~~

Đây là **sơ đồ minh họa**, không phải output từ cluster. Khi application luôn tạo `createdAt = new Date()`:

- Mỗi insert tăng dần theo thời gian.
- `mongos` định tuyến phần lớn inserts mới tới **chunk đầu/cuối** có bound `MinKey/MaxKey`.
- Shard sở hữu chunk “mới nhất” có thể phải gánh phần lớn write throughput.
- Một ngày sau, balancer có thể đã di chuyển một chunk mới; **hotspot có thể chuyển từ shard C sang shard khác**, nhưng tại một thời điểm writes vẫn tập trung.

MongoDB Manual nêu trường hợp shard key **monotonic** có thể tạo **hot chunk / hot shard**. Cân bằng **tổng dung lượng lịch sử** không đồng nghĩa cân bằng **dòng inserts mới**. Xem [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/).

### 4.2. Vì sao balancer không tự giải quyết tận gốc?

Balancer giúp phân phối **ranges theo lượng dữ liệu** theo chính sách, có thể chuyển chunk mới ra shard khác khi splits/migrations phù hợp. Nhưng với key tăng đơn điệu, các insert tiếp theo vẫn đổ vào **range đuôi** tại bất kỳ thời điểm nào. Di chuyển vị trí chunk chỉ **chuyển nơi bị nóng**, không biến một range duy nhất thành đồng thời nhiều đích nhận insert.

Không nên “chữa” workload này chỉ bằng cách thêm shard hoặc bật balancer, rồi giả định writes mới sẽ tự chia đều.

### 4.3. Một ví dụ ID tăng liên tục

~~~javascript
{
  orderSeq: NumberLong(1000000001),
  tenantId: "T-A",
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

Shard key `{orderSeq:1}` có cardinality cao nhưng **monotonic**. Chỉ cần toàn bộ orderSeq mới lớn hơn tất cả giá trị trước, chúng sẽ định tuyến tới upper range, tạo hot chunk. **High cardinality không đủ** để ngăn write hotspot.

### 4.4. Không phải mọi timestamp field đều gây nóng

Nếu timestamp chỉ là **field phụ**, còn shard key là `{orderId:"hashed"}`, việc createdAt tăng không tự khiến inserts cùng một shard. Điều gây hotspot ở ví dụ trên là **giá trị shard key dùng để phân vùng** tăng đơn điệu, không phải cứ collection có trường thời gian.

Ngoài ra, timestamp trong shard key **compound** có thể có hành vi khác tùy field dẫn đầu và phân bố của chúng. Ví dụ `{tenantId:1,createdAt:1}` có nhiều tenantIds, nhưng **một tenant rất nóng** vẫn có thể dồn tất cả writes mới của tenant đó vào một range nóng. Cần phân tích **toàn bộ shard key pattern**, không chỉ từng field.

### 4.5. Điểm nóng còn có thể xảy ra khi key không monotonic

Ví dụ ứng dụng có một bản ghi `counters`:

~~~javascript
db.counters.updateOne(
  { _id: "GLOBAL_ORDER_COUNT" },
  { $inc: { value: 1 } }
)
~~~

Dù shard key của `orders` được hash hoàn hảo, `counters.GLOBAL_ORDER_COUNT` vẫn là **một document nóng** nếu mọi request cập nhật nó. Dạng contention này là **hot document**, không thể giải quyết bằng cách đổi shard key của orders. Cần chia bộ đếm thành nhiều buckets, dùng asynchronous aggregation hoặc thay đổi quy tắc cập nhật nếu business cho phép.

### 4.6. Tín hiệu cho thấy monotonic hotspot

- Shard sở hữu **upper/lower edge range** có write QPS/CPU/IOPS cao.
- Các inserts mới gần như đều gắn shard key **tăng dần** hoặc **giảm dần**.
- Balancer thường xuyên chuyển range, nhưng shard nóng **thay đổi vị trí theo thời gian**.
- Indexing/replication lag trên shard nóng cao hơn shards khác.
- Dữ liệu lịch sử có thể đã tương đối đều nhưng ghi mới vẫn lệch rõ.

Khi điều tra, lấy mẫu nhiều khoảng thời gian đủ ngắn để thấy **đường đi của hotspot**, không chỉ số liệu trung bình cả ngày.

## 5. Hashed sharding: phân tán ghi nhưng đổi lại điều gì?

**Hashed sharding** dùng hash của giá trị shard key để quyết định range. Hai ID tăng liền nhau thường có hash không liền nhau, nên các inserts có thể rải ra nhiều chunks/shards.

### 5.1. Ví dụ shard theo orderId hashed

~~~javascript
// Chỉ minh họa trên cluster lab đã có collection/metadata phù hợp.
sh.shardCollection(
  "shard262_lab.orders_hashed",
  { orderId: "hashed" }
)
~~~

Đối với `orderId` là scalar có cardinality cao và độ trùng thấp, hashed key thường giúp phân tán writes tốt hơn shard key `{orderSeq:1}` tăng đơn điệu, khi collection đã có ranges/initial distribution phù hợp.

### 5.2. Lookup bằng equality thường targeted

~~~javascript
db.getSiblingDB("shard262_lab").orders_hashed.findOne({
  orderId: "O-1005"
})
~~~

Router có thể tính hash từ `orderId` cụ thể và xác định chunk/shard chứa khóa đó. **Equality trên hashed shard key** là access pattern thường phù hợp.

### 5.3. Range query thường mất locality

~~~javascript
db.getSiblingDB("shard262_lab").orders_hashed.find({
  orderId: {
    $gte: "O-1000",
    $lt: "O-2000"
  }
})
~~~

Những order IDs trong range `[O-1000,O-2000)` **không nằm kề nhau theo hash**, nên router khó giới hạn vào một dải chunk liên tiếp. Range query theo hashed field có thể thành **broadcast**, kể cả nếu index local vẫn hỗ trợ filter. Xem [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/).

### 5.4. Hashed key không giải quyết hotspot khi key thiếu phân biệt

Giả sử shard key là:

~~~javascript
{ tenantId: "hashed" }
~~~

Với 80% đơn đều có `tenantId:"T-BIG"`, hash("T-BIG") vẫn là **cùng một giá trị hash**; chúng vẫn có nguy cơ tập trung vào cùng chunk/shard. Hash **không tự rải một giá trị giống hệt** ra nhiều shards. Nếu một tenant cần trải trên nhiều shards, shard key có thể cần thêm thành phần có nhiều giá trị **trong cùng tenant**, chẳng hạn `orderId`, và cân nhắc tradeoff của query by tenant.

### 5.5. Key hash và index truyền thống

Hashed index không hỗ trợ mọi loại query/filter như B-tree ranged index, và hashed shard key có giới hạn với uniqueness. Một collection sharded theo hashed key vẫn có thể cần **indexes bổ sung trên từng shard** để hỗ trợ query theo createdAt, status hoặc customerId, nhưng index local **không tự làm query targeted**.

Không vì mục tiêu chia đều inserts mà tạo hashed shard key rồi bỏ qua những truy vấn quan trọng nhất của sản phẩm. Chọn shard key là cân bằng giữa:

| Mục tiêu | Range key | Hashed key |
|---|---|---|
| Truy vấn **range** theo chính shard key | Thường có locality tốt. | Có thể phải nhiều shards. |
| Equality theo full key | Thường targeted. | Thường targeted. |
| Inserts có key tăng đơn điệu | Dễ tạo hot edge chunk. | Thường phân tán tốt hơn khi values đủ đa dạng. |
| Tenant hot nhưng key chỉ là tenantId | Một tenant vẫn dồn cùng key. | Một tenant vẫn dồn cùng hash value. |
| Sắp xếp theo giá trị khóa | Có thể tận dụng order/range locality. | Hash làm mất thứ tự tự nhiên theo khóa gốc. |
| Unique constraints toàn cluster | Phụ thuộc shard key/index rules. | Hashed index không phải unique index; phải xét unique constraints. |

**Kết luận phần này:** Hashed sharding là một công cụ giảm **monotonic write hotspots**, không phải lựa chọn tối ưu phổ quát cho mọi workload. Xem [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/).

## 6. Compound shard key: cân bằng tenant isolation và phân bố tải

Trong ứng dụng multi-tenant, shard key có `tenantId` giúp router biết dữ liệu của tenant nằm ở đâu. Nhưng đây là một **lựa chọn có đánh đổi**: tenant có thể rất lớn, có thể cần nhiều shards, và một số API lại chỉ biết orderId.

### 6.1. `{tenantId:1}`: targeted theo tenant nhưng dễ hot tenant

~~~javascript
// Mẫu thiết kế, không chạy trên production.
sh.shardCollection(
  "shard262_lab.orders_tenant_only",
  { tenantId: 1 }
)
~~~

Ưu điểm: query `{tenantId:"T-A"}` có thể target range chứa tenant A; lọc theo tenant rất tự nhiên. Nhược điểm:

- **Cardinality hạn chế:** nếu chỉ có 5 tenants, có rất ít giá trị để phân vùng.
- **High frequency:** một tenant chiếm 80% orders có thể khiến nhiều writes đổ về cùng key.
- **Khả năng chia:** nhiều documents có **cùng shard key value** có thể không chia được một khoảng thành nhiều ranges hiệu quả qua giá trị đó, gây **indivisible chunk**.

Không nghĩ rằng một tenant lớn tự động được rải đều bằng cách thêm nhiều shards khi **toàn bộ khóa phân vùng chỉ là giá trị tenantId giống nhau**.

### 6.2. `{tenantId:1,orderId:1}`: tăng cardinality nhưng có nhiều tình huống

~~~javascript
sh.shardCollection(
  "shard262_lab.orders_tenant",
  { tenantId: 1, orderId: 1 }
)
~~~

Trong một tenant, các orderIds khác nhau tăng số giá trị shard key có thể tách ranges. Router có thể định tuyến:

~~~javascript
// Full equality trên compound shard key: thường đến một shard.
lab.orders_tenant.findOne({
  tenantId: "T-A",
  orderId: "O-1005"
})

// Prefix equality tenantId: có thể chỉ một hoặc nhiều shards
// vì các order của một tenant có thể đã phân bố nhiều ranges.
lab.orders_tenant.find({
  tenantId: "T-A"
})
~~~

**Có prefix shard key không luôn đồng nghĩa một shard.** Nếu tenant A sở hữu nhiều chunks trên các shards khác nhau, router có thể gửi query tới **tập shard liên quan**, nhưng vẫn tránh những shard không giữ ranges A.

### 6.3. Sequential orderId vẫn có thể tạo hot edge *trong tenant*

Nếu orderId tăng liên tục trong T-A, compound range key `{tenantId:1,orderSeq:1}` có thể khiến inserts mới **của T-A** tập trung vào range cuối cho T-A. Với nhiều tenants viết đồng thời, tải có thể phân tán theo tenants, nhưng một tenant cực lớn vẫn có thể nóng.

Một lựa chọn đáng đánh giá:

~~~javascript
// Compound hashed shard key: tiền tố tenantId, hậu tố orderId hashed.
// Yêu cầu server version hỗ trợ compound hashed shard key.
sh.shardCollection(
  "shard262_lab.orders_tenant_hashed",
  { tenantId: 1, orderId: "hashed" }
)
~~~

Khi đủ orderIds có nhiều giá trị, hash của orderId làm tăng khả năng phân tán writes của **một tenant** giữa nhiều ranges; hiệu quả thực tế phụ thuộc chunk initialization, zones, balancer và workload. Query full equality tenantId + orderId có cơ hội targeted; query chỉ tenantId có thể cần nhiều shards để lấy toàn tenant. **Không kết luận shard key mới đã chia hot tenant đều trước khi đo.**

### 6.4. Thêm bucket key khi workload cần nhiều điểm ghi

Một kỹ thuật khác là đưa **bucket phân tán** vào khóa:

~~~javascript
{
  tenantId: "T-A",
  bucket: 7,            // Từ một hash ổn định của orderId.
  orderId: "O-1005",
  createdAt: ISODate("2026-06-05T09:00:00Z")
}
~~~

Ứng dụng có thể chọn shard key dạng `{tenantId:1,bucket:1,orderId:1}` trong một thiết kế phù hợp. Bucket được tính **deterministically** từ orderId giúp:

- Phân tán writes của một tenant qua nhiều bucket ranges.
- Truy vấn theo orderId có thể tính lại bucket và đưa **đủ shard key fields** để targeted.
- Truy vấn chỉ tenantId không biết bucket vẫn có thể phải quét các buckets của tenant, nên fan-out cao hơn.

**Không dùng bucket random mới mỗi lần tra cứu** nếu ứng dụng không thể khôi phục bucket từ ID. Nếu key có bucket và orderId, phải có chiến lược tìm document/truyền đủ key ngay từ API.

### 6.5. Chọn thứ tự key dựa trên API thật

| Shard key ứng viên | Truy vấn thuận lợi | Rủi ro |
|---|---|---|
| `{tenantId:1}` | Lookup/list theo tenant. | Hot tenant, low cardinality. |
| `{tenantId:1,orderId:1}` | Full equality tenant+order; tenant prefix. | Sequential orderId có thể nóng trong tenant, order-only thiếu prefix. |
| `{tenantId:1,orderId:"hashed"}` | Full tenant+order equality; phân tán order IDs. | Tenant-wide list có thể nhiều shards; range theo orderId kém locality. |
| `{orderId:"hashed"}` | Equality theo orderId; rải order IDs. | Tenant-wide query/date range broadcast. |
| `{createdAt:1}` | Date range. | Writes mới monotonic hot. |
| `{tenantId:1,bucket:1,createdAt:1}` | Tenant+bucket+date khi biết bucket. | Tenant-date phải fan out nhiều buckets; application phức tạp hơn. |

Một key lý tưởng cho tất cả queries thường không tồn tại. Có thể cần thay đổi API để truyền thêm tenant/key, tạo **read models/secondary indexes**, hoặc phân biệt workload OLTP và analytics thay vì cố nhồi mọi yêu cầu vào một shard key.

## 7. Dữ liệu lệch do cardinality thấp và high-frequency values

**Low cardinality** và **high frequency** là hai nguyên nhân khác monotonicity.

### 7.1. Low cardinality

Ví dụ shard key `{region:1}`, dữ liệu chỉ có:

~~~javascript
{ region: "NORTH" }
{ region: "SOUTH" }
{ region: "CENTRAL" }
~~~

Nếu chỉ có 3 region values mà cluster có 12 shards, số vùng khóa khác nhau rất ít; thêm shards không khiến dữ liệu tự chia đều trong mỗi region. Giải pháp có thể là thêm thành phần shard key có nhiều giá trị hơn, ví dụ `{region:1,tenantId:1,orderId:1}` nếu query và write distribution cho phép.

Không thêm trường suffix chỉ để “làm key dài hơn”; phải đánh giá **cardinality, frequency, monotonicity, query prefixes** và unique index implications.

### 7.2. High-frequency value

Giả sử tần suất orders:

| Tenant | Phần trăm documents | Phần trăm writes |
|---|---:|---:|
| T-BIG | 72% | 91% |
| T-A | 12% | 3% |
| T-B | 9% | 4% |
| Các tenant khác | 7% | 2% |

Các số là **ví dụ giả định**. Khi shard theo `{tenantId:1}`, T-BIG có thể là điểm nóng lớn; hashed `tenantId` vẫn trả cùng hash cho toàn bộ T-BIG. Nếu mỗi tenant chỉ có **một giá trị shard key**, không thể kỳ vọng balancer chia những documents cùng giá trị đó sang nhiều chunks chỉ nhờ migration.

### 7.3. Indivisible chunk: một vùng không thể chia thêm

Một **chunk/range** có thể quá lớn nhưng không thể tách nếu các documents trong nó không có đủ giá trị shard key khác nhau để tạo split point hợp lệ. Hiện tượng thường được mô tả là **indivisible chunk**, có liên hệ với các tình huống **jumbo** tùy server version/diagnostics.

~~~text
Chunk A chứa mọi document có tenantId = "T-BIG"
         |
         v
Tất cả có cùng shard key value
         |
         v
Không có split point bên trong cùng giá trị
         |
         v
Thêm shard hoặc chạy balancer không biến nó
thành nhiều chunks chia đều một cách thần kỳ.
~~~

Điểm xử lý gốc là **đổi mô hình phân vùng / bổ sung thành phần shard key / reshard** khi dữ liệu và version cho phép, hoặc chia workload theo chiều khác. Đừng bắt đầu bằng manual moveChunk trước khi hiểu vì sao chunk không thể tách.

### 7.4. Jumbo không chỉ do một nguyên nhân

Vùng dữ liệu quá lớn, số lượng giá trị key thiếu, documents lớn, migration constraints, balancer thresholds hoặc index/topology issues có thể làm cluster báo warning/migration stuck. **Đừng chẩn đoán mọi lệch dung lượng là jumbo chunk**; cần đọc balancer state, chunk details, server logs và đặc trưng shard key.

### 7.5. Data size skew có thể là thiết kế có chủ đích

Nếu tổ chức dùng **zones** để giữ dữ liệu theo quốc gia hoặc tenant tier, shard A có thể chứa nhiều dữ liệu hơn B vì **chính sách data placement**. Balancer phải tôn trọng zone assignments và khả năng shard thuộc zone. “Số GB không bằng nhau” không tự chứng minh lỗi nếu deployment ưu tiên data residency hoặc workload isolation.

## 8. Balancer: cân bằng dữ liệu, không phải bộ điều phối QPS

Balancer quản lý chuyển ranges/chunks để đạt phân bố dữ liệu theo chính sách. Nó **không tự điều chỉnh shard key của từng document theo số CPU request hiện tại**.

### 8.1. Balancer có thể làm gì?

- Di chuyển ranges khi phát hiện chênh lệch đủ điều kiện.
- Tôn trọng **zone rules** và những hạn chế placement.
- Phân bố dữ liệu ban đầu/tích lũy tùy cơ chế shard, chunk sizing và phiên bản.
- Giúp giảm **data imbalance** khi chunks/ranges có thể di chuyển.

### 8.2. Balancer không tự giải quyết gì?

- Shard key **monotonic** vẫn đổ writes mới vào range cuối.
- Tenant có **một shard key value** không trải ra nhiều shards chỉ nhờ balancer.
- Query thiếu shard key vẫn fan out tới các shards được mongos xác định.
- **Hot document** vẫn là một document; migration có thể chuyển vị trí nóng, không chia write load của document thành nhiều nơi.
- Collection balanced theo bytes vẫn có thể lệch **QPS/CPU/working set**.

### 8.3. Cách kiểm tra trạng thái balancer

Trên `mongos` và với quyền đọc metadata:

~~~javascript
sh.getBalancerState()

db.adminCommand({ balancerStatus: 1 })

sh.status(true)
~~~

`sh.getBalancerState()` cho biết cấu hình bật/tắt balancer; nó **không đủ** để kết luận mọi migration đang thành công hay collection đã cân bằng. `balancerStatus` và logs giúp xem tình hình chi tiết tùy version; `sh.status(true)` trình bày thông tin chunks/placement. Khi điều tra production, dùng metrics từ monitoring/Atlas kèm commands chứ không chỉ tin một output shell.

### 8.4. Không tùy tiện tắt balancer hoặc move ranges bằng tay

Một cách khắc phục hấp tấp:

~~~text
Hot shard -> Tắt balancer -> Di chuyển vài chunks
~~~

có thể khiến dữ liệu không còn được balancing, hoặc chỉ **chuyển** hotspot sang shard khác. Manual migration/force migration còn có tác động network, disk và rủi ro với jumbo/indivisible chunks. Chỉ tiến hành sau khi xác định root cause, có rollout/rollback và theo đúng tài liệu server version.

### 8.5. Zone sharding có ích khi nào?

**Zones** cho phép ràng buộc những ranges của shard key với nhóm shards cụ thể, ví dụ dữ liệu EU ở region EU hoặc dữ liệu premium tenants ở phần cứng riêng. Nhưng nếu zone chỉ có **một shard** và toàn bộ hot tenant bị buộc vào zone đó, throughput vẫn có giới hạn.

Zone giúp **placement/data residency/workload isolation**, không tự tăng cardinality hay chữa monotonic keys. Khi thiết kế zones, phải đảm bảo đủ shards/capacity và hiểu balancer tôn trọng zone boundaries.

## 9. Truy vấn thiếu shard key: nguyên nhân của scatter-gather

Khi `mongos` không thể xác định shard chứa dữ liệu từ **query predicate và shard key metadata**, router có thể gửi truy vấn tới **tất cả shards** rồi tổng hợp kết quả. Đây gọi là **broadcast** hay **scatter-gather**.

### 9.1. Sơ đồ targeted và scatter-gather

~~~text
Truy vấn có full shard key hoặc prefix có thể định tuyến:

Application
    |
  mongos
    |
    +----------------> Shard B
    |                  (chứa range cần tìm)
    |
    +-- không gửi tới Shard A/C nếu metadata loại trừ được

Truy vấn thiếu shard key:

Application
    |
  mongos
    |
    +------------> Shard A ----+
    +------------> Shard B ----+--> merge results --> Client
    +------------> Shard C ----+
~~~

Scatter-gather có thể đắt vì:

- Nhiều shards phải parse/filter/query, kể cả khi **không có document khớp** tại shard đó.
- Có nhiều network round trips/connections và overhead merge ở `mongos` hoặc merge shard.
- Tail latency của request có thể bị kéo theo **shard chậm nhất**.
- Một API QPS cao sẽ nhân số operations: 1.000 requests/s × 8 shards ≈ tối đa 8.000 shard-level query participations/s, **chỉ là phép đếm minh họa**, không phải workload metric chuẩn.
- Với `sort`, `limit` và aggregation, merge có thể phải xử lý nhiều partial results.

### 9.2. Có index trên email nhưng thiếu shard key vẫn broadcast

Giả sử orders shard key là `{tenantId:1,orderId:1}` nhưng có index local:

~~~javascript
lab.orders_tenant.createIndex(
  { customerEmail: 1 },
  { name: "ix_customer_email" }
)
~~~

Request:

~~~javascript
lab.orders_tenant.find({
  customerEmail: "an@example.test"
})
~~~

Nếu không có tenantId/orderId, router thường không thể biết shard nào chứa email, dù mỗi shard có index customerEmail:

~~~text
mongos: hỏi nhiều shards
  Shard A: IXSCAN(customerEmail)
  Shard B: IXSCAN(customerEmail)
  Shard C: IXSCAN(customerEmail)
~~~

**Index scan nhanh trên mỗi shard không xóa được chi phí fan-out.** Cách sửa có thể là API truyền thêm tenantId, chọn shard key khác hoặc thiết kế một collection ánh xạ email → tenant/orderKey cho lookup đặc biệt, với ràng buộc consistency phù hợp.

### 9.3. Full key và prefix key

Với compound shard key:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

| Query | Định tuyến thường gặp |
|---|---|
| `{tenantId:"T-A",orderId:"O-1005"}` | Full equality, thường một shard chứa key tương ứng. |
| `{tenantId:"T-A"}` | Có prefix, thường tập shards chứa ranges của T-A; có thể một hoặc nhiều. |
| `{orderId:"O-1005"}` | Thiếu leading prefix, có nguy cơ broadcast. |
| `{status:"PAID"}` | Không có shard key, thường broadcast. |
| `{tenantId:"T-A",createdAt:{$gte:start,$lt:end}}` | Target theo tenant prefix, nhưng có thể nhiều shards nếu T-A phân tán. |
| `{tenantId:{$in:["T-A","T-B"]}}` | Có thể target union các ranges của hai tenants; số shards phụ thuộc placement. |
| `{tenantId:{$regex:/^T-/}}` | Router có thể có giới hạn targeting tùy predicate/collation; phải xem explain. |

Đây là **mô hình lý luận**, không phải bảo đảm trên mọi dữ liệu. Kể cả query có shard key, predicate quá rộng và chunk distribution có thể khiến nó chạm nhiều hoặc tất cả shards. MongoDB Manual mô tả targeting dựa trên **full key hoặc prefix compound key**, không phải mọi field nằm đâu đó trong index. Xem [Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/).

### 9.4. Vì sao query theo `_id` không luôn targeted?

MongoDB tự tạo index `_id`, nhưng nếu collection sharded theo `{tenantId:1,orderId:1}`, chỉ có:

~~~javascript
lab.orders_tenant.findOne({ _id: "O-1005" })
~~~

thì router không nhất thiết suy ra tenantId và chunk sở hữu `_id` đó. Nó có thể phải tìm trên nhiều shards, dù `_id` index giúp mỗi shard kiểm tra nhanh.

**`_id` không tự trở thành shard key** nếu bạn chọn shard key khác. Điều này còn liên quan đến uniqueness của `_id` và unique indexes trên sharded collections; không suy rằng mọi sharded collection bảo đảm global uniqueness của `_id` khi `_id` không phải shard key.

### 9.5. Có trường hợp broadcast là hợp lý

Không phải scatter-gather nào cũng sai. Analytics muốn tổng doanh thu **toàn cluster**:

~~~javascript
lab.orders_tenant.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$totalMinor" }
    }
  }
])
~~~

Nếu cần thống kê trên **mọi tenant**, việc các shards xử lý song song rồi merge có thể đúng và thậm chí hữu ích. Cần phân biệt:

- **OLTP point lookup:** người dùng chỉ cần một order; fan-out thường lãng phí.
- **Cluster-wide analytics:** kết quả cần toàn bộ dữ liệu; nhiều shards tham gia là tự nhiên.

Mục tiêu không phải tuyệt đối “mọi query chỉ một shard”, mà là **OLTP queries có tính chọn lọc nên targeted khi mô hình cho phép**, còn analytics được tối ưu theo chi phí tổng thể/parallel execution.

### 9.6. Truy vấn không có shard key ảnh hưởng paging/sort

~~~javascript
lab.orders_tenant.find(
  { status: "PAID" }
).sort({ createdAt: -1 }).limit(20)
~~~

Để tìm top 20 toàn cluster, từng shard có thể phải tạo partial results rồi router/merge stage phối hợp. Nếu mỗi shard thiếu index phù hợp, còn có chi phí sort trên từng shard. Một index local `{status:1,createdAt:-1}` có thể giúp **trong shard**, nhưng query vẫn fan out vì không có tenantId/orderId.

Với pagination sâu dùng `skip`, router có thể phải thu nhiều kết quả hơn số records cuối. Đối với API tenant-scoped, cân nhắc pagination theo shard key/`createdAt` và một tie-breaker ổn định như `orderId`, có index và filter tenant phù hợp.

### 9.7. Query theo tenant là vừa hiệu năng vừa phân quyền

Nếu API trả orders theo tenant, tenantId nên đến từ **ngữ cảnh authorization đáng tin**, không chỉ nhận từ query string tùy ý. Thêm `tenantId` vào filter có thể tăng targeting và bảo vệ dữ liệu, nhưng **index/shard key không thay thế authentication/authorization**. Phải nhất quán scope ở query, aggregation, lookup, updates và export jobs.

## 10. Xác minh targeted hay broadcast bằng `explain`

Đừng kết luận từ cú pháp SQL-like hay việc có index. **`explain()` trên sharded cluster** cho biết shards thực sự được query và query plan của mỗi shard trong phạm vi thông tin phiên bản hỗ trợ.

### 10.1. So sánh hai `find()` tương đương về mục tiêu nghiệp vụ

Với shard key giả định `{tenantId:1,orderId:1}`:

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

// A. API đã có tenant và order ID:
lab.orders_tenant.explain("executionStats").find({
  tenantId: "T-A",
  orderId: "O-1005"
})

// B. API chỉ biết order ID:
lab.orders_tenant.explain("executionStats").find({
  orderId: "O-1005"
})
~~~

Khi dữ liệu/metadata cho phép, **A có thể target một shard**, còn **B có thể broadcast**. Hai queries đều có thể trả **cùng một order** nếu `orderId` là duy nhất, nhưng chi phí routing khác nhau.

Điều kiện cần khi so sánh:

- Collection **thật sự được shard** theo key đã nêu.
- Kết nối qua **`mongos`**, không nối riêng một shard `mongod`.
- Dữ liệu đã phân bố đủ nhiều shards; fixture quá nhỏ thường chỉ nằm trên một shard nên không thấy rõ fan-out.
- Dùng cùng snapshot workload/điều kiện kết nối và quan sát plan thực tế.

### 10.2. Đọc `explain` của sharded queries

Tùy MongoDB Server/engine, bạn có thể thấy các thành phần:

| Thành phần/khái niệm | Cách đọc |
|---|---|
| `SINGLE_SHARD` | Router chọn một shard cho truy vấn trong plan phù hợp. |
| `SHARD_MERGE` | Có công đoạn merge kết quả giữa shards trong một số plans. |
| `SHARDING_FILTER` / `SHARD_FILTER` | Xử lý ownership/metadata trong execution plan khi áp dụng. |
| `shards` | Danh sách các shard tham gia và kế hoạch/thống kê từng shard. |
| `IXSCAN` | Index scan **bên trong shard**, không nhất thiết chỉ một shard tham gia. |
| `COLLSCAN` | Collection scan trong một shard; có thể do thiếu index hoặc planner chọn. |
| `FETCH` | Đọc document gốc sau index lookup khi cần field/kiểm tra khác. |
| `totalKeysExamined` | Số index keys xem; cần hiểu phạm vi thống kê. |
| `totalDocsExamined` | Số documents xem; có thể cộng từ shard-level stats. |
| `nReturned` | Document được trả ở cấp execution được báo cáo. |
| `splitPipeline` / `mergeType` | Phân đoạn aggregation giữa shard-side và merge-side khi hiện diện. |

Không viết bộ parser `explain` giả định mọi phiên bản luôn có một đường JSON cố định như `queryPlanner.winningPlan.shards`. Classic engine, SBE và aggregation có hình dạng khác; tập trung vào **shards tham gia + số keys/docs examined + sort/merge**.

### 10.3. Minh họa “mỗi shard có index nhưng vẫn fan out”

~~~text
Query A: full shard key
  mongos -> Shard B: IXSCAN + FETCH
  total shards targeted = 1

Query B: orderId only
  mongos -> Shard A: IXSCAN + FETCH
          -> Shard B: IXSCAN + FETCH
          -> Shard C: IXSCAN + FETCH
  total shards targeted = 3
~~~

Đây là **mô phỏng để giải thích**, không phải explain thật. Nếu mọi shard chỉ xem một key, query B vẫn có thể nhanh trên dataset nhỏ; vấn đề là khi tần suất và số shards tăng, fan-out trở thành chi phí lớn. Phải đo p95/p99 latency và per-shard QPS thay vì gán “broadcast luôn chậm hơn đúng N lần”.

### 10.4. Dùng `hint` có biến broadcast thành targeted không?

Không. `hint()` có thể điều khiển index **được dùng để xử lý query** theo API/phiên bản:

~~~javascript
lab.orders_tenant.find(
  { orderId: "O-1005" }
).hint({ orderId: 1 })
~~~

Nếu index này có tồn tại/phù hợp, từng shard có thể dùng nó, nhưng router vẫn thiếu `tenantId` để suy shard đích từ compound shard key. **Index tuning giải quyết local scan; shard key predicate giải quyết routing**.

### 10.5. So sánh `find()` và `aggregate()`

~~~javascript
lab.orders_tenant.explain("executionStats").aggregate([
  { $match: { tenantId: "T-A", orderId: "O-1005" } },
  { $project: { _id: 1, status: 1, totalMinor: 1 } }
])

lab.orders_tenant.explain("executionStats").aggregate([
  { $match: { orderId: "O-1005" } },
  { $project: { _id: 1, status: 1, totalMinor: 1 } }
])
~~~

`$match` trên shard key ở đầu aggregation có cơ hội giúp router xác định shard. Nhưng nếu pipeline có `$match` sau những stages đổi dữ liệu/điều kiện dependency, optimizer có thể không đẩy về cursor được. **Kiểm tra optimized aggregation plan**, không chỉ nhìn stage thứ mấy trong source.

### 10.6. Cách đếm số shards tham gia

Ở một số phiên bản, `winningPlan` có stage `SINGLE_SHARD` hoặc `SHARD_MERGE`; ở một số dạng khác có object/array `shards` với execution stats. Cách chắc chắn nhất là **đọc từng shard entry trong explain** và kiểm tra nó có thực sự tham gia query hay chỉ xuất hiện dưới dạng metadata. Khi tự động phân tích, xây parser theo phiên bản đã triển khai và test lại sau nâng cấp.

## 11. Đo phân bố dữ liệu và chunk/range

Để phân biệt **dữ liệu lệch** với **tải lệch**, cần ít nhất hai bộ đo: *owned data distribution* và *read/write activity*.

### 11.1. `sh.status()`: tổng quan topology, chunk counts, zones

~~~javascript
// Chạy trên mongos:
sh.status()

// Chi tiết hơn, có thể rất dài trên cluster lớn:
sh.status(true)
~~~

Theo MongoDB Manual, `sh.status(true)` hiển thị chi tiết chunk distribution và thông tin sharding configuration. `sh.status()` mặc định có thể rút gọn khi collection nhiều chunks. Nếu một chunk được đánh dấu jumbo/migration lỗi, thông tin này có thể giúp hướng điều tra tiếp.

**Không dùng số chunks là chỉ số duy nhất của data size**. Cần kết hợp owned data bytes và skew theo shard.

### 11.2. `getShardDistribution()`: phân bố một collection

~~~javascript
const lab = db.getSiblingDB("shard262_lab")
lab.orders_tenant.getShardDistribution()
~~~

Helper mongosh này in thống kê phân bố của **một sharded collection**. Nó không phải API Java Driver và không tự đo QPS của queries. Nếu collection chưa được shard hoặc đang nối sai endpoint, kết quả có thể không như mong đợi.

### 11.3. `sh.getShardedDataDistribution()`: thống kê toàn cluster

Từ MongoDB **6.0.3** có mongosh helper:

~~~javascript
sh.getShardedDataDistribution()
~~~

Kết quả minh họa có thể chứa:

~~~javascript
[
  {
    ns: "shard262_lab.orders_tenant",
    shards: [
      {
        shardName: "shardA",
        numOwnedDocuments: 1200000,
        ownedSizeBytes: 310000000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      },
      {
        shardName: "shardB",
        numOwnedDocuments: 1100000,
        ownedSizeBytes: 295000000000,
        numOrphanedDocs: 0,
        orphanedSizeBytes: 0
      }
    ]
  }
]
~~~

Đây là **data giả định**, không phải output từ fixture. Các trường `numOwnedDocuments`/`ownedSizeBytes` mô tả dữ liệu shard **sở hữu**; `numOrphanedDocs`/`orphanedSizeBytes` biểu diễn dữ liệu orphan khi áp dụng. So sánh **owned data** thay vì cộng nhầm orphaned documents thành lượng dữ liệu logical của collection. Xem [sh.getShardedDataDistribution](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/).

### 11.4. Balancer/migration status và nhật ký

~~~javascript
sh.getBalancerState()
db.adminCommand({ balancerStatus: 1 })
~~~

Kết hợp với **config server/balancer logs**, shard logs, disk/capacity và chunk/range information để tìm:

- Range migration bị retry/abort.
- Jumbo/indivisible chunk.
- Disk/network/replication lag trên donor/recipient.
- Zone constraints khiến balancer không có shard hợp lệ.
- Resharding/DDL hoặc hoạt động quản trị cạnh tranh.

Một balancer **được bật** không bảo đảm migrations thành công. Nếu distribution vẫn lệch, nguyên nhân có thể là giới hạn placement hoặc range không chia/migrate được, không chỉ “balancer chưa chạy”.

### 11.5. Cần đo runtime load theo từng shard

Danh sách nên thu từ Atlas Metrics, MongoDB monitoring hoặc observability hiện có:

| Metric | Dấu hiệu |
|---|---|
| CPU %/core utilization | Một shard bão hòa, shard khác nhàn. |
| Disk reads/writes và IOPS | Hot shard có I/O vượt capacity. |
| Memory/cache eviction | Working set nóng vượt RAM/cache. |
| Replication lag | Shard hot có secondary theo không kịp. |
| Operations/s theo read/write | Tải khác biệt rõ dù owned bytes bằng nhau. |
| P95/P99 latency | Tail latency tăng khi một shard chậm. |
| Network bytes/connection usage | Scatter-gather fan-out/merge overhead. |
| Query shape frequency | Những predicates nào không chứa shard key. |
| Chunk migration rate/failure | Balancer đang làm việc hay mắc kẹt. |
| Dung lượng owned bytes/documents | Data skew và tăng trưởng theo thời gian. |

Không nên so sánh chỉ **QPS** giữa shards: cùng một QPS nhưng một shard chạy queries phải scan/sort lớn còn shard kia point lookups, load vẫn khác. Theo dõi **cost per operation** và số keys/docs examined khi có thể.

### 11.6. Đọc kết quả theo cửa sổ thời gian

Ví dụ ngày bình thường nhìn thấy:

~~~text
Shard A: 30% writes, 34% reads, 31% owned bytes
Shard B: 35% writes, 33% reads, 34% owned bytes
Shard C: 35% writes, 33% reads, 35% owned bytes
~~~

Nhưng đợt flash sale 15 phút:

~~~text
Shard A: 92% writes, 75% reads, 31% owned bytes
Shard B:  4% writes, 12% reads, 34% owned bytes
Shard C:  4% writes, 13% reads, 35% owned bytes
~~~

Data phân bố bình thường, nhưng tenant/key đang được truy cập nhiều có thể nằm ở shard A. Bài toán là **workload skew theo thời gian**, không phải chỉ data balance.

## 12. `analyzeShardKey`: đo một key ứng viên trước khi reshard

Chọn shard key bằng suy đoán thường thất bại khi dữ liệu production có phân bố tenants và query shapes khác dữ liệu test. Từ **MongoDB 7.0**, lệnh **`analyzeShardKey`** hỗ trợ phân tích key đang dùng hoặc key ứng viên qua metrics về **key characteristics** và **read/write distribution** trên dữ liệu/query samples khi đáp ứng yêu cầu.

### 12.1. Hai nhóm metrics

| Nhóm | Nội dung |
|---|---|
| **`keyCharacteristics`** | Cardinality, frequency, monotonicity và đặc điểm của giá trị shard key. |
| **`readWriteDistribution`** | Tính chất định tuyến/độ phân tán của các queries ghi/đọc được lấy mẫu theo key ứng viên. |

Key có cardinality cao chưa chắc tốt nếu application **không bao giờ đưa field đó vào filters**. Tương tự key có read targeting tốt chưa chắc tốt nếu 99% writes mới đổ vào một monotonic range.

### 12.2. Gọi `analyzeShardKey` bằng mongosh

Theo tài liệu hiện hành, method có dạng:

~~~javascript
// Chỉ chạy khi cluster/version/permissions đáp ứng yêu cầu.
const lab = db.getSiblingDB("shard262_lab")

lab.orders_tenant.analyzeShardKey({
  tenantId: 1,
  orderId: 1
})

// Phân tích một ứng viên khác để so sánh.
lab.orders_tenant.analyzeShardKey({
  orderId: "hashed"
})
~~~

Lệnh phân tích **không tự reshard collection**. Nó cho biết metrics hữu ích để đánh giá. Để có **readWriteDistribution** đáng tin, cần query sampling đủ đại diện và cấu hình tương ứng theo docs. Một collection lab sáu documents gần như không có giá trị thống kê thực tế; không kết luận shard key production từ vài samples.

### 12.3. Query analyzer sampling

MongoDB có cơ chế **query analyzer** và helper/command như `configureQueryAnalyzer` để bật lấy mẫu các queries theo điều kiện phiên bản và quyền. Cần cấu hình sample rate phù hợp với QPS thực, hạn chế overhead, quan sát thời gian lấy mẫu, và phân loại:

- Point lookups theo tenant+order.
- Point lookups chỉ theo orderId.
- Range scans theo createdAt.
- `updateOne`/`upsert`/`deleteMany` không có shard key.
- Queries được scheduler chạy mỗi giờ hoặc workload flash sale.

Nếu sample window chỉ có OLTP giờ thấp điểm nhưng không chứa batch imports hoặc analytics cuối ngày, `readWriteDistribution` có thể thiên lệch. **Mọi metric sampling chỉ hữu ích khi đại diện workload cần tối ưu**.

### 12.4. Cách so sánh hai ứng viên

Giả sử:

| Khía cạnh | `{tenantId:1,orderId:1}` | `{orderId:"hashed"}` |
|---|---|---|
| Các lookups tenant+order | Tốt | OrderId equality thường tốt. |
| Query chỉ orderId | Có nguy cơ broadcast | Thường targeted. |
| Tenant-wide list/report | Có thể target ranges của tenant | Có nguy cơ broadcast. |
| Sequential IDs trong hot tenant | Có thể có hot range | Hash thường rải tốt hơn. |
| Unique indexes cho tenant+externalOrderNo | Cần xét shard key prefix/constraints | Cần xét lại uniqueness rules, hash không unique. |
| Mức độ thay đổi API | Có thể cần truyền tenant | Có thể giữ API order-only. |

Đây là **bảng đánh đổi lý thuyết**, không phải số đo trên workload cụ thể. Đưa vào quyết định cả data residency, index size, shard ownership và khả năng rollout.

### 12.5. Kết quả analyzer không phải cam kết hiệu năng

`analyzeShardKey` và `explain` hỗ trợ quyết định; không thay thế **load test thực**, đo p95/p99, thử failure mode và theo dõi thời gian sau rollout. Key tốt khi phân bố hiện tại có thể suy yếu khi khách hàng lớn tăng gấp 50 lần hoặc sản phẩm thêm query mới không mang tenantId.

## 13. Khi thiếu shard key trong **write operations**

Khác với `find()`, thao tác ghi trên sharded collection có những **quy tắc định tuyến và hạn chế cú pháp riêng**. Chúng thay đổi giữa server versions và theo loại write/upsert.

### 13.1. `insertOne` có đầy đủ shard key trong document

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

lab.orders_tenant.insertOne({
  _id: "O-2001",
  tenantId: "T-A",
  orderId: "O-2001",
  status: "CREATED",
  createdAt: new Date(),
  totalMinor: NumberLong(70000)
})
~~~

`mongos` dùng shard key values trong document để xác định shard đích. Nếu data model yêu cầu non-null tenantId/orderId, hãy enforce chuẩn dữ liệu ở application và schema validation phù hợp. Không mặc định missing/null shard key fields có thể xử lý an toàn chỉ vì command chấp nhận một số trường hợp.

### 13.2. `updateOne` với full shard key

~~~javascript
lab.orders_tenant.updateOne(
  {
    tenantId: "T-A",
    orderId: "O-2001",
    status: "CREATED"
  },
  {
    $set: {
      status: "PAID",
      paidAt: new Date()
    }
  }
)
~~~

Router có thể target shard tương ứng; filter `status:"CREATED"` còn bảo vệ transition khỏi hai concurrent requests cùng chạy. **Full shard key equality** thường là lựa chọn có hiệu năng và semantics rõ ràng nhất cho point writes.

### 13.3. `updateOne` chỉ theo `_id` có thể dùng đường ghi tốn hơn

~~~javascript
lab.orders_tenant.updateOne(
  { _id: "O-2001" },
  { $set: { status: "CANCELLED" } }
)
~~~

Khi `_id` không phải shard key và filter thiếu full shard key, MongoDB có **quy tắc two-phase write protocol** hoặc các giới hạn riêng tùy phiên bản/op/upsert; request có thể cần tìm document trên nhiều shards trước khi thực hiện write. Không giả định `_id` index tự nói cho router shard đích.

Ví dụ này để **minh họa rủi ro routing**, không khuyến nghị chạy sau lệnh đổi status thành PAID trong nghiệp vụ thật. Với cập nhật trạng thái, luôn thêm transition guard/authorization như ví dụ `updateOne` phía trên.

### 13.4. `updateMany` và `deleteMany`

~~~javascript
// Chỉ sửa một tenant được yêu cầu:
lab.orders_tenant.updateMany(
  {
    tenantId: "T-A",
    status: "CREATED"
  },
  {
    $set: { needsReview: true }
  }
)
~~~

Với compound shard key `{tenantId:1,orderId:1}`, điều kiện tenantId prefix có thể target **một tập shard** chứa ranges của tenant đó; không mặc định chỉ một shard.

Nếu filter chỉ có `status:"CREATED"`, router có thể cần broadcast. `updateMany` và `deleteMany` có routing rules phụ thuộc việc query có **full shard key** hay không; nếu bỏ key, workload có thể phải đi nhiều shards. Hơn nữa, `updateMany` **atomic theo từng document**, không atomic toàn bộ documents nếu không có transaction.

### 13.5. Upsert có nhiều điều kiện version-specific

~~~javascript
lab.orders_tenant.updateOne(
  { tenantId: "T-A", orderId: "O-3001" },
  {
    $setOnInsert: {
      createdAt: new Date(),
      status: "CREATED"
    }
  },
  { upsert: true }
)
~~~

**Full shard key trong filter** làm yêu cầu định tuyến rõ và thường dễ quản trị hơn. Tuy nhiên, các yêu cầu pháp lý/cú pháp “upsert phải có đầy đủ shard key” đã thay đổi giữa MongoDB versions (ví dụ thay đổi từ các dòng 7.x/8.x). Không viết rule tuyệt đối cho mọi deployment: hãy kiểm tra trang `updateOne()` đúng server và phiên bản driver, nhất là khi thay shard key field value, dùng null/missing key hoặc update không chứa `_id`.

### 13.6. Unique indexes trên sharded collection

Nếu cần uniqueness toàn cluster của `(tenantId,externalOrderNo)`, phải thiết kế shard key và unique index phù hợp với **unique index restrictions**. Với ranged shard keys, unique index trên sharded collection thường phải có **shard key là prefix** để bảo đảm uniqueness cluster-wide, ngoài các ngoại lệ/giới hạn được MongoDB nêu.

~~~javascript
// Ví dụ key design được chủ động chọn theo tính duy nhất:
// Shard key: { tenantId: 1, externalOrderNo: 1 }
// Unique constraint candidate theo prefix:
db.orders.createIndex(
  { tenantId: 1, externalOrderNo: 1 },
  { unique: true }
)
~~~

Với **hashed shard key**, hashed index không thể làm unique index đơn giản theo cùng kiểu. Và nếu `_id` không là shard key, MongoDB có giới hạn về **global uniqueness của `_id`**: index `_id` có thể chỉ thực thi uniqueness **theo từng shard**, nên ứng dụng phải có cơ chế bảo đảm global ID uniqueness khi cần. Đừng dùng giả định “`_id` luôn global unique bất kể shard key” để thiết kế payment/identity.

### 13.7. Đổi shard key field của document

MongoDB hỗ trợ cập nhật shard key trong những trường hợp/phiên bản phù hợp, nhưng thao tác làm document chuyển sang range thuộc shard khác có thể gây chi phí di chuyển và hạn chế về query/session/transaction. Tránh chọn shard key là field thay đổi thường xuyên như `status`, `currentAssignee` hay mutable `region` nếu các updates liên tục làm document chuyển shard.

Đây không chỉ là vấn đề atomicity mà còn là **performance và operational complexity**.

## 14. Aggregation trong sharded cluster: filter sớm và merge

Một aggregation có thể chia thành **shard-side partial pipeline** và **merge-side pipeline**. `mongos` hoặc một shard merge kết quả tùy stage và server version. Khi điều kiện lọc đủ shard key và có thể được đẩy sớm, server có thể target ít shards hơn.

### 14.1. Báo cáo trong một tenant

~~~javascript
const start = ISODate("2026-06-01T00:00:00Z")
const end = ISODate("2026-07-01T00:00:00Z")

lab.orders_tenant.aggregate([
  {
    $match: {
      tenantId: "T-A",
      status: "PAID",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalMinor: { $sum: "$totalMinor" },
      orders: { $sum: 1 }
    }
  },
  { $sort: { totalMinor: -1 } }
])
~~~

Filter `tenantId:"T-A"` là shard key prefix, giúp router xác định những ranges liên quan. Nhưng vì T-A có thể nằm trên **nhiều shards**, aggregation vẫn có thể chia một phần kết quả rồi merge. Bảng phân bố thực tế quyết định số shards, không phải chỉ tên `tenantId`.

### 14.2. Báo cáo toàn bộ tenants

~~~javascript
lab.orders_tenant.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: { $gte: start, $lt: end }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      totalMinor: { $sum: "$totalMinor" },
      orders: { $sum: 1 }
    }
  },
  { $sort: { totalMinor: -1 } }
])
~~~

Vì yêu cầu tổng thể cần mọi tenants, việc tất cả shards tham gia có thể là **đúng**. Phải tối ưu bằng indexes local, shard-side filters/grouping, tài nguyên sort/merge và giới hạn kết quả; không cố ép một shard làm tất cả.

### 14.3. Lọc sau projection có thể được optimizer đẩy nhưng đừng dựa vào nó mù quáng

~~~javascript
lab.orders_tenant.aggregate([
  { $project: { tenantId: 1, status: 1, totalMinor: 1 } },
  { $match: { tenantId: "T-A", status: "PAID" } }
])
~~~

Optimizer có thể đẩy một số predicate độc lập lên sớm. Nhưng nếu `$match` phụ thuộc field được tạo bởi `$project`, hoặc stage đã thay đổi ngữ nghĩa, việc chuyển vị trí có thể không hợp lệ. Viết **shard key filter sớm khi đúng ngữ nghĩa** và dùng `explain` để xác nhận targeting, thay vì hy vọng mọi pipeline tự tối ưu.

### 14.4. `$lookup` và sharding không tự giải quyết routing

Aggregation join sang collection khác có thể tạo nhiều subqueries hoặc phân chia stages theo sharding. Index và shard key của **foreign collection** có thể ảnh hưởng cách lookup được thực thi, tùy server version. Nếu mỗi order lookup customer theo customerId mà không có shard key của customer, có thể phát sinh chi phí fan-out/merge. Cần xem `explain` của toàn pipeline, đặc biệt khi `$lookup`, `$group` hoặc `$sort` tốn phần lớn thời gian.

### 14.5. Streaming analytics vs OLTP

Workload OLTP cần trả một order trong vài milliseconds nên targeted lookup quan trọng. Analytics quét hàng chục triệu documents để tổng hợp có thể có lợi từ xử lý song song mọi shards. Khi hai nhu cầu đối lập, cân nhắc **read model/denormalization** hoặc một storage phân tích riêng, thay vì chọn một shard key cực đoan chỉ để tối ưu một truy vấn.

## 15. Khi cần đổi shard key: refine hay reshard?

Nếu đã đo và kết luận shard key hiện tại **về bản chất không phù hợp**, có hai hướng thay đổi:

1. **Refine shard key:** thêm field suffix vào shard key hiện có (giữ prefix cũ).
2. **Reshard collection:** phân phối lại dữ liệu theo shard key khác; có thể đổi field hoặc chuyển ranged ↔ hashed theo khả năng server.

Đây là **thao tác DDL/cluster-level có rủi ro**, không phải tối ưu query thường nhật. Cần capacity, migration plan, kiểm tra unique constraints, query contract, zone policy và quy trình rollback/recovery.

### 15.1. Refine shard key: thêm thành phần suffix

Giả sử key cũ:

~~~javascript
{ tenantId: 1 }
~~~

Một tenant rất lớn có nhiều orders, key chỉ tenantId quá ít giá trị để chia ranges. Nếu muốn giữ tenantId làm prefix, có thể đánh giá:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Mẫu lệnh quản trị trên cluster lab hỗ trợ:

~~~javascript
// KHÔNG chạy trực tiếp trên production.
db.adminCommand({
  refineCollectionShardKey: "shard262_lab.orders_tenant_only",
  key: { tenantId: 1, orderId: 1 }
})
~~~

Refinement có yêu cầu về indexes/key fields và giới hạn phiên bản. Nó **không** cho phép bỏ `tenantId` hoặc đưa `orderId` lên trước; chỉ thêm suffix. Nếu queries phổ biến không có tenantId, refine **không tự chữa** fan-out theo orderId-only. Nếu orderId tăng đơn điệu, compound ranged key vẫn có thể hot trong tenant.

### 15.2. Reshard: đổi cấu trúc khóa

MongoDB hỗ trợ `reshardCollection` từ **5.0** theo các điều kiện triển khai. Ví dụ mong muốn từ:

~~~javascript
// Hiện tại:
{ tenantId: 1, orderId: 1 }

// Ứng viên mới:
{ orderId: "hashed" }
~~~

Lệnh dạng:

~~~javascript
// Chỉ minh họa DDL trong cluster lab đã chuẩn bị.
db.adminCommand({
  reshardCollection: "shard262_lab.orders_tenant",
  key: { orderId: "hashed" }
})
~~~

Reshard có thể giúp thay đổi write spread/query targeting. Nhưng nó cũng đổi **query contract**: API tenant-only giờ có nguy cơ broadcast, và unique indexes hiện có có thể không đáp ứng key mới. Trước khi chạy, phải rà queries, writes, indexes, uniqueness, zones và storage capacity.

### 15.3. Reshard với cùng shard key

Từ MongoDB **8.0**, có khả năng reshard với **cùng shard key hiện tại** bằng redistribution khi phù hợp, ví dụ option `forceRedistribution:true`:

~~~javascript
// Chỉ minh họa, không chạy trên production.
db.adminCommand({
  reshardCollection: "shard262_lab.orders_tenant",
  key: { tenantId: 1, orderId: 1 },
  forceRedistribution: true
})
~~~

Redistribution với cùng key có thể giúp một số placement imbalance, nhưng **không sửa đặc điểm xấu của key**, như monotonic write edge hoặc một giá trị tenantId lặp quá nhiều.

### 15.4. Chi phí cần dự trù

- Copy/clone dữ liệu và index tạo **I/O, network, CPU, storage pressure**.
- Có thể cần **không gian lưu trữ bổ sung đáng kể** trên recipient shards.
- Có thể có khoảng ngắn **block writes/cutover latency** theo giới hạn server version.
- Cần xem tác động tới **oplog, replication, change streams** và operations đang chạy.
- Một số DDL không được phép hoặc phải chờ khi resharding đang chạy.
- Unique index/shard key compatibility là điều kiện quan trọng.
- Thời gian thực tế phụ thuộc data size/cluster throughput/concurrent workload.

Thử trên staging với data/workload đại diện, có monitoring, xác minh queries sau cutover và chuẩn bị khôi phục. Xem [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/).

### 15.5. Khi không nên reshard ngay

Nếu vấn đề là API quên truyền tenantId dù đã biết, thiếu index local, batch import không được throttle, một hot counter document độc lập, hoặc balancer tạm thời đang migrate, thì **sửa query/index/throttling/model cụ thể** có thể ít rủi ro hơn reshard toàn collection. Đổi shard key là quyết định lớn sau khi có evidence key đang giới hạn hệ thống.

## 16. Java Sync Driver: truyền shard key đúng trong truy vấn OLTP

Java Driver không yêu cầu ứng dụng tự chọn shard. Đơn vị cần kiểm soát là **BSON filter** gửi qua `mongos`. Nếu filter bỏ shard key, router vẫn có thể broadcast dù code dùng `Filters.eq` và có local index.

### 16.1. Lookup targeted theo tenant + orderId

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

// database: MongoDatabase kết nối tới cluster qua mongos.
MongoCollection<Document> orders =
    database.getCollection("orders_tenant");

String authorizedTenantId = "T-A"; // Từ auth context đã xác minh.
String orderId = "O-1005";

Bson filter = Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("orderId", orderId)
);

Document order = orders.find(filter).first();
System.out.println(order == null ? "Not found" : order.toJson());
~~~

Nếu key là `{tenantId:1,orderId:1}`, filter có đủ hai fields. Không dùng `Filters.eq("orderId",orderId)` đơn lẻ cho path OLTP quan trọng chỉ vì Driver trả kết quả đúng trên cluster nhỏ.

### 16.2. Conditional update có full shard key

~~~java
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Updates;

UpdateResult result = orders.updateOne(
    Filters.and(
        Filters.eq("tenantId", authorizedTenantId),
        Filters.eq("orderId", orderId),
        Filters.eq("status", "CREATED")
    ),
    Updates.combine(
        Updates.set("status", "PAID"),
        Updates.set("paidAt", new java.util.Date())
    )
);

if (result.getMatchedCount() == 0) {
    // Order thiếu, đã đổi trạng thái, hoặc scope tenant không hợp lệ.
    System.out.println("Update precondition not met");
}
~~~

Filter shard key giúp routing; filter status bảo vệ **business transition**. Không coi `matchedCount:0` là network error; nó thường chỉ có nghĩa không có document khớp.

### 16.3. Index phục vụ tenant + sort

~~~java
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.IndexOptions;

orders.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId"),
        Indexes.descending("createdAt")
    ),
    new IndexOptions().name("ix_tenant_createdAt_desc")
);
~~~

Index hỗ trợ **trong shard** với query tenant/date và sort, nhưng không thay đổi shard key. Với tenant trên nhiều shards, query còn cần merge. Tạo index production phải xem write overhead/disk/existing indexes.

### 16.4. `explain` trong Java

~~~java
import com.mongodb.ExplainVerbosity;

Document plan = orders.find(
    Filters.and(
        Filters.eq("tenantId", authorizedTenantId),
        Filters.eq("orderId", orderId)
    )
).explain(ExplainVerbosity.EXECUTION_STATS);

System.out.println(plan.toJson());
~~~

`FindIterable.explain()` giúp thấy query plan. Muốn đếm targeted shards, cần hiểu cấu trúc output theo server/version, không parse `IXSCAN` rồi kết luận chỉ một shard.

### 16.5. Aggregation tenant-scoped trong Java

~~~java
import java.util.Arrays;
import java.util.Date;
import java.time.Instant;
import org.bson.conversions.Bson;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Sorts;

Date start = Date.from(Instant.parse("2026-06-01T00:00:00Z"));
Date end = Date.from(Instant.parse("2026-07-01T00:00:00Z"));

Bson match = Aggregates.match(Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("status", "PAID"),
    Filters.gte("createdAt", start),
    Filters.lt("createdAt", end)
));

orders.aggregate(Arrays.asList(
    match,
    Aggregates.group(
        "$customerId",
        Accumulators.sum("paidOrders", 1),
        Accumulators.sum("revenueMinor", "$totalMinor")
    ),
    Aggregates.sort(Sorts.descending("revenueMinor"))
)).forEach(System.out::println);
~~~

Query này đặt tenantId filter trước grouping. Nếu tenantId prefix bao nhiều ranges trên các shards, aggregation vẫn có thể cần multi-shard execution/merge.

### 16.6. Lỗi API thường gặp: service chỉ nhận orderId

~~~java
// API quá nghèo ngữ cảnh:
public Document getOrder(String orderId) {
    return orders.find(Filters.eq("orderId", orderId)).first();
}
~~~

Trong collection sharded theo tenantId-leading key, service này có thể broadcast. Contract tốt hơn là truyền authorizedTenantId:

~~~java
public Document getOrder(String authorizedTenantId, String orderId) {
    return orders.find(Filters.and(
        Filters.eq("tenantId", authorizedTenantId),
        Filters.eq("orderId", orderId)
    )).first();
}
~~~

Nếu client không biết tenant, cần lookup mapping, key khác, hoặc flow tra cứu hai bước an toàn. Không thêm tenantId giả định hay dùng giá trị client không được phép chọn chỉ để query nhanh.

### 16.7. Driver không tự suy shard key

Java Driver serialize filter, quản lý topology/mongos discovery và retryable writes theo điều kiện, nhưng không tự suy `tenantId` từ `orderId` nếu không có mapping. Đổi connection string không biến query thiếu key thành targeted; phải sửa **query shape hoặc data model**.

## 17. Runbook điều tra shard bị nóng hoặc dữ liệu lệch

Khi production báo “MongoDB sharded cluster chậm dù đã thêm shard”, không chạy reshard ngay. Dùng quy trình **đo → phân loại → xác minh → sửa có kiểm soát**.

### Bước 1 — Xác định triệu chứng và thời gian

~~~text
Hot writes?         Hot reads?
Data size skew?     Chunk/zone imbalance?
Query latency?      Migration failures?
~~~

Chỉ ra **metric và thời điểm**: một shard 95% CPU? P99 tăng khi flash sale? Owned bytes lệch 70/15/15? Có nhiều broadcast point lookups? Liệu app ghi tăng đột ngột hay data đã lệch nhiều tuần?

### Bước 2 — Xác định shard key thật

~~~javascript
// Qua mongos và quyền metadata phù hợp.
sh.status()
~~~

Ghi lại **exact shard key pattern**, gồm thứ tự fields và hashed/ranged. Không dùng tên index trong tài liệu thiết kế cũ rồi giả định đó là shard key đang triển khai.

### Bước 3 — Thu data distribution

~~~javascript
const lab = db.getSiblingDB("shard262_lab")

lab.orders_tenant.getShardDistribution()
sh.getShardedDataDistribution()
~~~

Nhìn owned bytes/docs per shard và range ownership, không chỉ số chunks. Nếu balancer mắc kẹt, xem `balancerStatus` và logs.

### Bước 4 — Thu query shapes và `explain`

Chọn một số queries **QPS cao** và **p95/p99 chậm**, gồm reads/writes:

~~~javascript
// Có full key:
lab.orders_tenant.explain("executionStats").find({
  tenantId: "T-A",
  orderId: "O-1005"
})

// Thiếu leading shard key prefix:
lab.orders_tenant.explain("executionStats").find({
  orderId: "O-1005"
})
~~~

Đếm shards tham gia; đọc `IXSCAN`/`COLLSCAN` **của từng shard**. Xác định query có index tốt nhưng vẫn fan out không.

### Bước 5 — Phân loại nguyên nhân

| Nếu quan sát | Ưu tiên điều tra |
|---|---|
| Writes mới tập trung vào range cuối | Monotonic key, hot chunk, insert pattern. |
| Một tenant chiếm phần lớn traffic | Hot tenant, frequency, tenantID-only key. |
| Bytes lệch nhưng QPS đều | Range placement, balancer, zones, indivisible chunks. |
| Bytes đều nhưng QPS lệch | Hot keys, working set, query patterns. |
| Point lookups chạm mọi shard | Missing shard key/prefix, API contract. |
| Từng shard quét nhiều docs dù targeted | Local indexes/filter selectivity, sort. |
| Migration thất bại liên tục | Balancer logs, jumbo/indivisible chunks, capacity/zones. |

### Bước 6 — Chọn cách sửa nhỏ nhất có tác dụng

Các biện pháp theo thứ tự tăng rủi ro:

1. **Sửa API/query** để truyền đủ shard key hoặc prefix phù hợp.
2. **Tạo/chỉnh index local** cho filter/sort sau khi query targeted.
3. **Giảm hotspot do ứng dụng**, ví dụ throttle imports, bucket counters, batch writes hợp lý.
4. **Đổi data model**, hoặc thêm lookup mapping/read model.
5. **Đánh giá refine/reshard shard key** bằng analyzeShardKey, thử staging và kế hoạch migration.
6. **Điều chỉnh zones/balancer/capacity** theo root cause; không thao tác manual khi chưa hiểu placement.

### Bước 7 — Xác minh sau rollout

- Owned bytes/docs và range distribution có đáp ứng kỳ vọng không?
- QPS/CPU/IOPS per shard có cải thiện không?
- Tỷ lệ targeted/broadcast của OLTP queries có thay đổi không?
- Latency p95/p99 có giảm dưới workload tương đương?
- Có regression ở tenant-wide reports, range queries hoặc unique constraints không?
- Balancer/replication ổn định, có migration stuck/jumbo mới không?
- Error rate/retries của `updateOne`/upserts có tăng do key mới không?

### 17.1. Mẫu chẩn đoán bằng bằng chứng

~~~text
Triệu chứng:
  write latency p99 tăng từ 20ms lên 220ms trong flash sale.

Đo:
  Shard B dùng 95% CPU, A/C 30%.
  Owned bytes A/B/C = 33/34/33%.
  85% writes thuộc tenant T-BIG.
  Shard key {tenantId:1}, một tenant lặp rất nhiều.

Kết luận sơ bộ:
  Workload skew/hot tenant, không phải thiếu dữ liệu cân bằng.

Hành động:
  Đánh giá compound key có orderId/hash hoặc bucket.
  Đo query contract (tenant-only vs tenant+order).
  Thử workload/reshard trên staging.
~~~

Các số là **tình huống minh họa**; không dùng làm ngưỡng cố định cho mọi cluster.

### 17.2. Những thao tác không nên thực hiện ngay

- Tắt balancer vì thấy CPU cao mà không xác định migrations là nguyên nhân.
- Di chuyển ranges thủ công khi chưa đo hotspot và khả năng split.
- Đổi shard key chỉ vì một query bị broadcast, trong khi có thể thêm tenantId vào API.
- Thêm shards rồi cam kết write throughput sẽ tăng tuyến tính.
- Tạo hàng loạt local indexes để “chữa broadcast” mà không sửa routing.
- Ép tất cả tenant vào một zone/shard mà chưa tính peak QPS.
- Bỏ tenant filter để “tăng tốc” nhưng làm mất phân tách dữ liệu.
- Chạy `reshardCollection` trực tiếp trên production không thử capacity/cutover/rollback.

## 18. Các tình huống kiến trúc và lựa chọn

### 18.1. Feed bài viết theo thời gian

Ứng dụng lưu post mới với `createdAt` tăng liên tục, shard key `{createdAt:1}`; truy vấn “post mới nhất” cũng tập trung đầu dải dữ liệu.

**Vấn đề:** write hotspot ở tail range; read hotspot cũng tập trung vào dữ liệu mới.

**Hướng đánh giá:** Shard theo userId/authorId/hash hoặc compound key phù hợp, nhưng global feed “mới nhất” có thể phải merge nhiều shards; có thể cần materialized feed/caching. Đừng chỉ thay createdAt bằng hash mà không lập kế hoạch cho global chronological reads.

### 18.2. Tenant B chiếm 90% orders

Key `{tenantId:"hashed"}` có vẻ “đã hash nên đều”, nhưng mọi order của tenant B vẫn cùng hash.

**Vấn đề:** hot tenant trong một giá trị key; có thể xuất hiện indivisible chunk.

**Hướng đánh giá:** compound hashed key `{tenantId:1,orderId:"hashed"}` hoặc bucket theo orderId, với đầy đủ query targeting và data residency constraints. Nếu tenant B có yêu cầu isolation mạnh, cân nhắc phân bổ tài nguyên/tenant-specific shard strategy.

### 18.3. Số documents bằng nhau nhưng một shard CPU 100%

Một hot customer liên tục đọc/cập nhật cùng document, balancer báo data cân bằng.

**Vấn đề:** **hot document/workload skew**, không phải data size skew.

**Hướng đánh giá:** giảm contention bằng cách đổi data model, split/bucket counters, cache, asynchronous aggregation hoặc rate limit; balancer không chia được một document thành nhiều writes song song tới nhiều shard.

### 18.4. API tìm order bằng orderId sau khi shard theo tenantId

~~~javascript
// Query cũ:
db.orders.findOne({ orderId: "O-1005" })

// Query tốt hơn cho key {tenantId:1,orderId:1}:
db.orders.findOne({
  tenantId: "T-A",
  orderId: "O-1005"
})
~~~

**Vấn đề:** API contract thiếu leading shard key prefix, dẫn tới broadcast.

**Hướng đánh giá:** lấy tenantId từ auth context/URL đã xác minh, đưa vào filter; nếu consumer hợp lệ chỉ biết orderId, xây lookup mapping có consistency hoặc cân nhắc shard key khác. Không giả lập tenantId chỉ để target.

### 18.5. Email lookup dù có email index

Orders shard theo tenant; mỗi shard có index `customerEmail` nhưng email-only lookup vẫn broadcast.

**Vấn đề:** local index không thay shard metadata.

**Hướng đánh giá:** tenant-aware query, read model email→tenantIds/orderIds, hoặc global search service; bảo vệ PII và uniqueness theo tenant/global policy. Không chắc chắn email là khóa ổn định/duy nhất.

### 18.6. Region zone EU nhưng shard EU đầy

Zone constraints buộc dữ liệu EU vào nhóm shards cụ thể, trong đó một shard thiếu capacity.

**Vấn đề:** có thể là zone placement/capacity skew; balancer không được tùy tiện chuyển dữ liệu EU ra shard ngoài zone.

**Hướng đánh giá:** thêm shards phù hợp trong zone, chỉnh zone ranges sau khi đánh giá data residency, capacity planning, migration health. Không phá zone policy chỉ để bytes đều.

### 18.7. Range query theo ngày bị chậm sau chuyển sang hashed orderId

Hash làm inserts tốt hơn nhưng `createdAt` không phải shard key, báo cáo tháng 6 phải quét nhiều shards.

**Hướng đánh giá:** nếu report có tenant, thêm tenant filter khi key hỗ trợ; index local createdAt/status, materialized daily aggregates, analytical replica/warehouse. Chỉ reshard lại nếu workload range query quan trọng hơn write spread và đã đo đủ.

### 18.8. Import một ngày 20 triệu documents với sequential key

**Vấn đề:** đợt bulk insert dồn vào một hot range, lag và lock/I/O tăng.

**Hướng đánh giá:** pre-partition/suitable hashed key/bucketed insert strategy, điều tiết throughput, phù hợp index và chunk distribution; không nghĩ unordered `bulkWrite` có thể tự rải writes qua shards nếu **shard key vẫn monotonic**.

### 18.9. Collection có nhiều orphaned documents

Migrations/chunk ownership thay đổi có thể dẫn tới orphaned records trong một giai đoạn. Nếu chỉ lấy raw storage bytes và cộng orphan data, dễ kết luận sai về owned logical distribution.

**Hướng đánh giá:** dùng `getShardedDataDistribution` để phân biệt `ownedSizeBytes` và `orphanedSizeBytes`, kiểm tra range deletion/migration logs theo version. Không tự xóa orphan bằng lệnh delete vào shard trực tiếp.

### 18.10. Query theo userId nhanh trên ba shards nhưng chậm trên 20 shards

Nếu key là tenantId và userId không có tenant, request có thể broadcast đến mọi shard. Cùng một index userId trên từng shard vẫn phải tốn nhiều shard-level operations và merge.

**Hướng đánh giá:** truy vấn có tenantId; nếu không thể, cải tiến global identifier/lookup routing, read model hoặc reshard khi pattern thực sự thường xuyên. **Scale-out dữ liệu** có thể làm rõ điểm yếu của **fan-out query pattern**.

## 19. Các nhầm lẫn thường gặp và cách sửa

| Nhầm lẫn | Tại sao sai | Cách hiểu đúng |
|---|---|---|
| “Có 8 shards thì mọi insert chia đều 1/8.” | Routing dựa trên shard key/chunk placement, không round-robin mỗi insert. | Chọn shard key có cardinality và distribution thích hợp. |
| “Shard key tăng tuần tự có cardinality cao nên luôn tốt.” | Inserts mới đều vào upper range. | Kiểm tra monotonicity và write hotspot. |
| “Balancer bật là các writes sẽ được chia đều.” | Balancer chuyển ranges theo data distribution, không chia một hot range thành nhiều đích viết đồng thời. | Cần chỉnh key/write pattern nếu monotonic/hot value. |
| “Hash tenantId tự chia tải của một tenant lớn.” | Mọi document cùng tenantId có cùng hash. | Dùng thành phần phân biệt trong tenant khi workload cần. |
| “Hash createdAt vẫn hỗ trợ range theo thời gian như ranged key.” | Hash phá tính liên tiếp của giá trị gốc. | Hashed giúp write spread nhưng range queries có thể broadcast. |
| “Mọi query có một field trong compound key đều targeted.” | Router cần full key hoặc **leading prefix** phù hợp. | Xem thứ tự key và explain. |
| “Prefix tenantId đảm bảo query chỉ một shard.” | Tenant lớn có thể chiếm ranges ở nhiều shards. | Prefix chỉ có thể giới hạn **tập shards**. |
| “Có index `orderId` thì tìm orderId chắc chắn chỉ một shard.” | Index xử lý **bên trong shard**, không cho router biết placement nếu key khác. | Truyền shard key hoặc đổi routing strategy. |
| “`_id` luôn tương đương shard key.” | Shard key do DDL chọn; `_id` có thể là field khác. | Không dựa vào `_id` để suy targeted/global uniqueness khi key khác. |
| “`IXSCAN` ở explain nghĩa là không broadcast.” | Mọi shard tham gia đều có thể dùng `IXSCAN`. | Kiểm tra **shards** tham gia, rồi local plan. |
| “`COLLSCAN` chắc chắn là gốc của latency.” | Có thể collection nhỏ hoặc scan toàn bộ là hợp lý cho analytics. | Đọc docsExamined/selectivity/QPS. |
| “Chunks bằng nhau nghĩa là data bằng nhau.” | Ranges có số lượng/size documents khác nhau. | Dùng ownedSizeBytes/numOwnedDocuments. |
| “Data bằng nhau nghĩa là workload bằng nhau.” | Hot tenant/key có thể tập trung read/write QPS. | So sánh metrics per shard theo thời gian. |
| “Một jumbo chunk chỉ cần moveChunk bằng tay.” | Nếu indivisible, range không có split point hợp lệ. | Điều tra key frequency/cardinality, constraints và version. |
| “Tắt balancer thì chấm dứt điểm nóng.” | Có thể làm data distribution xấu hơn, không chữa hot key. | Xác định gốc hotspot trước. |
| “Thêm shard luôn giúp hot document.” | Một document không được split thành nhiều shard writes. | Thay data model/counter bucketing/aggregation. |
| “Chỉ chọn shard key theo storage GB.” | API thiếu shard key có thể broadcast, write skew có thể cao. | Cân bằng read/write patterns và placement. |
| “Chọn key theo một ngày sample là đủ.” | Flash sale/imports/analytics có thể không xuất hiện. | AnalyzeShardKey và samples đại diện nhiều chu kỳ. |
| “Hashed key lúc nào cũng nhanh hơn ranged key.” | Range/sort locality suy giảm, unique constraints phức tạp. | Chọn theo tỷ trọng OLTP vs range scans. |
| “Refine thay được field đầu của key.” | Refine chỉ **thêm suffix**. | Muốn đổi leading prefix cần reshard khi hỗ trợ. |
| “Reshard với cùng key chữa monotonicity.” | Key vẫn monotonic, chỉ redistribution thay đổi placement. | Muốn thay write distribution phải đổi key/write pattern. |
| “Mọi upsert thiếu shard key đều hoạt động giống nhau ở mọi version.” | Routing/required predicates đã thay đổi qua phiên bản. | Xem docs `updateOne()` đúng server version. |
| “`updateMany` nguyên tử toàn cluster.” | Atomic trên từng document, trừ khi transaction bao nhiều writes. | Phân biệt atomicity và routing. |
| “`bulkWrite({ordered:false})` tự cân bằng shard writes.” | Unordered chỉ thay order constraints; shard key vẫn quyết định routing. | Cần key phân tán và observe actual distribution. |
| “Một zone có một shard cũng đáp ứng scaling không giới hạn.” | Zone ràng buộc placement và capacity. | Quy hoạch đủ shards theo zone. |
| “Query theo tenantId luôn bảo vệ dữ liệu tenant.” | TenantId do client giả mạo vẫn có thể đọc tenant khác. | Lấy tenant từ authorization context đáng tin. |
| “Chỉ cần reshard xong là mọi API tiếp tục tối ưu.” | Query contract/unique indexes/shard targeting thay đổi. | Regression tests với các query shapes trước cutover. |

### 19.1. Phân biệt ba câu trả lời cho ba triệu chứng

~~~text
Thấy write hotspot:
  Hỏi key nào, giá trị nào, chunk nào nhận writes?

Thấy data skew:
  Hỏi owned bytes/documents/ranges ra sao, balancer/zones có ràng buộc gì?

Thấy query chậm:
  Hỏi mongos đã target mấy shards,
  và mỗi shard dùng index hay scan/sort gì?
~~~

**Không dùng một biện pháp duy nhất “thêm shards” để trả lời cả ba câu hỏi.**

## 20. Bài tập thực hành và đáp án gợi ý

Các bài tập giả định một sharded cluster có ba shards hoặc tình huống nêu trong đề. Những con số QPS/GB là **minh họa**, không phải kết quả đo từ fixture `shard262_lab`. Các đoạn commands có thể chạy trên **cluster lab được phép**, không dùng DDL/migration trên production.

### Bài 1 — Tại sao key thời gian tạo hotspot?

**Đề:** `orders` sharded theo `{createdAt:1}`. Mọi order mới có thời gian tăng theo đồng hồ; 90% inserts tới shard C, mặc dù A/B/C có data size gần bằng nhau. Giải thích.

**Đáp án:** Range sharding có chunk chứa upper bound `MaxKey`. Khi createdAt tăng liên tục, các giá trị mới rơi vào **range cuối**, hiện thuộc shard C. Balancer có thể di chuyển hot range về shard khác theo thời gian, nhưng không tự khiến inserts mới được phân tán đều đồng thời. Cân nhắc hashed key/key có nhiều giá trị, nhưng phải xét range queries theo thời gian.

### Bài 2 — Hashed tenantId có chữa hot tenant?

**Đề:** 85% orders có `tenantId:"T-MEGA"`. Shard key `{tenantId:"hashed"}`. Vì sao shard vẫn nóng?

**Đáp án:** Hash một giá trị lặp lại tạo **cùng hash**. Tất cả T-MEGA documents vẫn có cùng key value, dễ tập trung range/shard. Cần thêm chiều phân biệt **trong tenant**, ví dụ orderId hashed/bucket, cùng kế hoạch cho queries tenant-wide.

### Bài 3 — Full key vs thiếu leading prefix

**Đề:** Shard key `{tenantId:1,orderId:1}`. Hai queries:

~~~javascript
db.orders.findOne({ tenantId: "T-A", orderId: "O-1" })
db.orders.findOne({ orderId: "O-1" })
~~~

Query nào dễ targeted hơn?

**Đáp án:** Query thứ nhất có full key, router có thể xác định range/shard. Query thứ hai thiếu tenantId nên có nguy cơ broadcast tới nhiều/tất cả shards. Có local index orderId không tự sửa routing.

### Bài 4 — Query chỉ theo tenantId

**Đề:** Shard key `{tenantId:1,orderId:1}`. Vì sao `{tenantId:"T-A"}` có thể target **nhiều shards**?

**Đáp án:** Tenant T-A có thể chứa nhiều orderId ranges nằm trên các shards khác nhau; prefix giúp router loại trừ shards không giữ T-A nhưng không đảm bảo chỉ một shard. Xem chunk placement/explain.

### Bài 5 — `_id` và shard key

**Đề:** Shard key là `{tenantId:1,orderId:1}`. Collection có index `_id`. Query `{_id:"O-1001"}` có chắc targeted không?

**Đáp án:** Không. Router không nhất thiết biết shard từ `_id` nếu `_id` không thuộc shard key. Có thể phải tìm trên nhiều shards, mỗi shard dùng `_id` index local. Nếu yêu cầu global uniqueness cho ID, cần thiết kế theo giới hạn unique index của sharded collection.

### Bài 6 — Local index và routing

**Đề:** Mỗi shard có index `{customerEmail:1}`; tìm `{customerEmail:"an@example.test"}` vẫn chạm 6 shards. Có phải index chưa được dùng?

**Đáp án:** Không nhất thiết. `IXSCAN` có thể xảy ra ở cả sáu shards. Index chỉ giúp local filtering, không cho router biết shard đích. Kiểm tra shard-level explain và cân nhắc tenant-aware API/read model.

### Bài 7 — Balanced data nhưng CPU lệch

**Đề:** Owned bytes là A=100 GB, B=100 GB, C=100 GB; CPU A=95%, B/C=15%. Có nên chạy balancer để “cân bằng CPU”?

**Đáp án:** Chưa có căn cứ. Data đã đều; có thể workload skew, hot tenant/key, query khác nhau, working-set khác hoặc một hot document. Thu QPS/IOPS/query shapes trước. Balancer chủ yếu quản lý data ranges và không tự là bộ phân phối CPU.

### Bài 8 — 100 chunks có chắc nhiều dữ liệu hơn 50 chunks?

**Đáp án:** Không. Chunks khác kích thước/data density. Dùng `ownedSizeBytes`, `numOwnedDocuments`, xét orphan data, chunks/ranges và version-specific balancing.

### Bài 9 — Low-cardinality key

**Đề:** Cluster có 10 shards, shard key `{countryGroup:1}` chỉ có ba values. Vì sao scaling bị giới hạn?

**Đáp án:** Key ít giá trị, nhiều documents trùng key và range khó chia thành đủ nhiều partitions. Có thể bổ sung suffix high-cardinality qua refine nếu phù hợp hoặc reshard với key khác, đồng thời kiểm tra query prefixes và residency.

### Bài 10 — Indivisible chunk

**Đề:** Một chunk chứa toàn bộ documents với `tenantId:"T-BIG"`, không có split point khả dụng vì key chỉ tenantId. Có thể giải quyết bằng cách thêm shard mà không đổi key không?

**Đáp án:** Không bảo đảm. Cùng key value không chia hiệu quả thành nhiều chunks; thêm shards không tự tách value đó. Cần đổi/refine shard key hoặc thiết kế khác khi dữ liệu thật sự cần chia trong tenant. Manual migration một chunk có thể chỉ chuyển hotspot.

### Bài 11 — Khi nào hashed key kém hơn ranged key?

**Đề:** 90% requests cần lấy orders trong một khoảng orderSeq/createdAt liên tục. Chuyển sang hashed orderSeq để phân tán writes có tác động gì?

**Đáp án:** Hash làm mất range locality, queries theo khoảng key có nguy cơ broadcast; có thể tăng chi phí OLTP/report. Phải đo tỷ trọng range queries và đánh giá compound/alternative read models; hashed không phải ưu thế tuyệt đối.

### Bài 12 — Từ explain có `IXSCAN` ở 4 shards

**Đề:** Query plan cho bốn shards đều có `IXSCAN`. Bạn có thể kết luận đã target một shard không?

**Đáp án:** Không, vì chính explain đã chỉ ra bốn shards tham gia. Index sử dụng ở từng shard không đồng nghĩa targeted routing. Phải đếm shards và xem local keys/docs examined.

### Bài 13 — Analytics broadcast

**Đề:** Báo cáo tổng doanh thu toàn bộ tenants cần đọc dữ liệu trên mọi shard. Có nên coi việc broadcast là lỗi?

**Đáp án:** Không. Với analytics toàn cluster, parallel shard processing rồi merge có thể là hành vi tự nhiên. Tối ưu filter, shard-local indexes, `$group` partial, sort/merge và lựa chọn read model.

### Bài 14 — Full key trong `updateOne`

**Đề:** Shard key `{tenantId:1,orderId:1}`. Viết update chuyển một order từ CREATED sang PAID với routing và business condition rõ:

**Đáp án:**

~~~javascript
db.orders.updateOne(
  {
    tenantId: "T-A",
    orderId: "O-1001",
    status: "CREATED"
  },
  {
    $set: {
      status: "PAID",
      paidAt: new Date()
    }
  }
)
~~~

Full key hỗ trợ targeted routing; status filter bảo vệ state transition. Nếu `matchedCount:0` thì có thể order missing/đã đổi status.

### Bài 15 — `updateMany` thiếu shard key

**Đề:** `updateMany({status:"EXPIRED"},{$set:{archived:true}})` trên collection sharded theo tenantId/orderId. Rủi ro?

**Đáp án:** Có thể broadcast đến nhiều/tất cả shards vì filter không có shard key. Mỗi document update atomic riêng, toàn operation không atomic cùng lúc. Nếu business chỉ cần một tenant, thêm tenantId từ authorization; nếu cần toàn cluster, xử lý batch/rate limit/monitoring phù hợp.

### Bài 16 — Upsert thiếu shard key

**Đề:** Backend upsert một order chỉ theo `orderId` trên collection sharded theo `{tenantId:1,orderId:1}`. Có thể chắc chắn định tuyến nhanh và đúng trên mọi MongoDB version không?

**Đáp án:** Không. Các điều kiện/routing của upsert và write thiếu full shard key khác nhau giữa phiên bản, có thể liên quan two-phase write protocol hoặc lỗi điều kiện. API nên mang **full shard key** và unique business identity. Kiểm tra `updateOne()` documentation đúng server version trước khi triển khai.

### Bài 17 — Refine shard key và reshard khác nhau gì?

**Đề:** Collection có shard key `{tenantId:1}`, muốn thành `{tenantId:1,orderId:1}` hoặc `{orderId:"hashed"}`. Chọn loại nào?

**Đáp án:** Thêm suffix nhưng giữ prefix có thể dùng **refine** khi đáp ứng điều kiện. Muốn bỏ tenantId/đổi field dẫn đầu hoặc chuyển cấu trúc key cần **reshard** khi được hỗ trợ. Đánh giá index/unique constraints, query contract, zones và chi phí migration.

### Bài 18 — Có nên reshard ngay khi thấy một API chậm?

**Đề:** Key là `{tenantId:1,orderId:1}`; API `GET /orders/{orderId}` bị broadcast nhưng auth layer biết tenantId. Làm gì trước?

**Đáp án:** Truyền tenantId từ auth context vào BSON filter, đo lại targeted shards và p95 latency. Đây có thể là **sửa query contract** ít rủi ro hơn reshard toàn collection.

### Bài 19 — Bucket key

**Đề:** Chọn key `{tenantId:1,bucket:1,orderId:1}`, bucket = hash(orderId) mod 16. Query tìm một order cần gì?

**Đáp án:** Cần **tenantId, bucket và orderId** (với bucket tính deterministically từ orderId) để full-key targeting. Query chỉ tenantId có thể phải truy vấn nhiều bucket ranges, tradeoff giữa write spread và tenant-wide reads.

### Bài 20 — Balancer đang bật nhưng shard vẫn lệch

**Đề:** `sh.getBalancerState()` trả true, owned bytes vẫn 70/15/15 sau nhiều giờ. Có thể kết luận balancer bị lỗi code không?

**Đáp án:** Chưa. Cần `balancerStatus`, `sh.status(true)`, logs migration, zone constraints, indivisible/jumbo ranges, disk/network/replication health. Balancer enabled không bảo đảm mọi range có thể split/migrate ngay.

### Bài 21 — Chunk count vs owned bytes

**Đề:** A có 200 chunks, B có 180 chunks nhưng owned bytes A=100 GB, B=140 GB. Shard nào “lớn hơn” về dữ liệu?

**Đáp án:** Theo **owned bytes**, B chứa nhiều dữ liệu hơn, dù ít chunks hơn. Số chunks không phải đại diện tuyệt đối cho data size. Cần xem thêm orphan/zone và workload trước khi cân bằng.

### Bài 22 — Orphaned documents

**Đề:** Sau migration, shard A có 20 GB orphaned bytes. Bạn có nên tính chúng vào logical owned data của collection khi quyết định data balance không?

**Đáp án:** Không nên cộng như dữ liệu logical thuộc quyền sở hữu. Dùng `numOwnedDocuments`/`ownedSizeBytes` để hiểu phân bố logical; orphaned metrics phục vụ chẩn đoán range deletion/migration. Không tự xóa thủ công trên shard `mongod`.

### Bài 23 — Zone constraints

**Đề:** Zone EU chỉ có một shard, tất cả EU writes nóng. Thêm shard vào cluster ngoài zone EU có tự chia EU workload không?

**Đáp án:** Không nhất thiết. Balancer phải tôn trọng placement rules; nếu shard mới không thuộc zone hợp lệ, EU data không được tự chuyển sang đó. Phải xét thêm capacity trong zone và policy residency.

### Bài 24 — Analyze shard key trước reshard

**Đề:** Bạn định đổi key từ `{tenantId:1,orderId:1}` sang `{orderId:"hashed"}`. Cần đo gì trước?

**Đáp án:** Cardinality/frequency/monotonicity, query read/write distribution và targeting của key ứng viên, hot tenant distribution, queries chỉ tenantId, range report workload, unique index constraints, migration cost và capacity. Có thể dùng `analyzeShardKey` (7.0+) với query samples đại diện và load test staging.

### Bài 25 — Update hot counter dù orders đã hashed

**Đề:** Orders shard theo hashed orderId, inserts phân tán tốt, nhưng hệ thống vẫn chậm khi mọi request chạy `$inc` trên `counters._id:"GLOBAL"`. Đổi shard key orders có giúp không?

**Đáp án:** Không, nút thắt là **hot document counter**. Cân nhắc bucket counters và asynchronous aggregation, rate limits hoặc thay đổi yêu cầu strictness. Nếu bắt buộc một số đếm chính xác tức thì qua mọi requests, cần chấp nhận/confront giới hạn contention của một điểm ghi.

### Bài 26 — Thời điểm flash sale

**Đề:** Data size theo shards là 33/33/34%, còn writes ban ngày 30/34/36%. Trong 15 phút flash sale, writes thành 90/5/5%. Kiểm tra gì?

**Đáp án:** Lấy write distribution theo tenant/key/value ở **cửa sổ 15 phút**, xác định hot range/shard key, targeted queries và cache/IOPS; tránh chỉ xem average cả ngày. Có thể workload skew do một tenant hoặc batch import chứ không phải balancer.

### Bài 27 — Java Driver có tự target bằng orderId không?

**Đề:** Một hàm Java `orders.find(eq("orderId",id)).first()` chạy trên sharded key `{tenantId:1,orderId:1}`. Driver có tự suy tenantId từ document cũ không?

**Đáp án:** Không. Nó gửi BSON filter từ application; router không biết tenantId nếu filter thiếu. Sửa API truyền authorizedTenantId hoặc thiết kế mapping/key khác; không mong driver tự nhớ shard dựa trên những queries trước.

### Bài 28 — Range key nhưng analytics chỉ cần hàng gần đây

**Đề:** Dữ liệu được shard theo createdAt range, queries báo cáo tháng gần nhất rất nhanh targeted, nhưng peak inserts nóng. Có nên đổi ngay sang hash createdAt?

**Đáp án:** Chưa đủ căn cứ. Phải đo write load và tỷ trọng range reads; hash createdAt làm mất range locality, có thể khiến báo cáo chậm hơn. Xem compound key, bucket, materialized aggregates, batch scheduling/throttling và reshard chỉ khi lợi ích thực lớn hơn regression.

### Bài 29 — Unique `_id` trên sharded collection

**Đề:** Collection sharded theo `{tenantId:1,orderId:1}`, ứng dụng dùng `_id` là khóa toàn cầu. Có thể mặc định MongoDB bắt mọi shard đều thống nhất không cho duplicate `_id` không?

**Đáp án:** Không mặc định. Khi `_id` không là shard key, uniqueness có thể chỉ được index enforce **trong mỗi shard**. Để có global ID uniqueness phải chọn key/unique index phù hợp hoặc có cơ chế bảo đảm ID toàn cục ở ứng dụng. Kiểm tra quy định unique index theo version.

### Bài 30 — Một thiết kế “đúng cả ba”

**Đề:** Bạn phải lựa chọn shard key cho SaaS: 70% reads theo tenant+order, 15% reads theo order-only, 10% reports tenant-by-date, 5% global analytics. Peak writes chủ yếu từ một tenant. Đề xuất quy trình thay vì kết luận ngay một key.

**Đáp án gợi ý:**

1. Lấy query samples theo giờ/tenant, đo cardinality, frequency, monotonicity của candidates.
2. So sánh `{tenantId:1,orderId:1}`, `{tenantId:1,orderId:"hashed"}`, `{orderId:"hashed"}` và bucketed models.
3. Kiểm tra có thể sửa 15% API order-only để truyền tenantId từ auth hay không.
4. Đánh giá chi phí tenant-by-date reports khi tenant data trải nhiều shards, local indexes và read model.
5. Test với hot tenant, số shards thực, concurrency, size/zone constraints.
6. Chọn key dựa trên tổng chi phí **writes + OLTP targeted reads + analytics**, không chỉ phần trăm data size.
7. Nếu đổi key production, làm staging runbook/unique constraints/capacity/cutover, đo latency sau triển khai.

Một đáp án hợp lý có thể khác theo SLA và user journeys; điều quan trọng là giải thích được **đánh đổi** và có bằng chứng đo.

## 21. Checklist vận hành theo từng triệu chứng

### 21.1. Khi write QPS chỉ tập trung một shard

- Shard key có **monotonic values** hay quá ít distinct values?
- Hot shard có sở hữu range `MaxKey/MinKey`?
- Dữ liệu có hot tenant/hot document không?
- Data bytes giữa shards có cân bằng nhưng writes lệch không?
- Có đủ chunks/ranges để phân phối, hay một range không thể split?
- Có bulk inserts/import schedule gây spike không?
- Query/writes có đặc điểm hashed key giúp phân tán được hay tất cả cùng một value?
- Có cần compound hashed/buckets/thay invariant trước khi reshard?

### 21.2. Khi dữ liệu lệch giữa shards

- Owned docs/bytes phân bố thế nào? Orphaned data có làm số liệu sai không?
- Có chính sách zones hoặc capacity khác nhau không?
- Balancer có bật, có migration attempts và failures không?
- Có jumbo/indivisible chunks hoặc key có nhiều trùng lặp không?
- Data size lệch từ khi sharding, sau thêm shard, hay mới xuất hiện?
- Có cần refine/reshard hay chỉ chờ/sửa migration problem?

### 21.3. Khi truy vấn càng thêm shard càng chậm

- API point lookup có đưa **full shard key/prefix** vào filter không?
- Explain cho thấy một hay nhiều shards tham gia?
- Từng shard có `IXSCAN`/`FETCH`/`COLLSCAN` và docsExamined ra sao?
- `sort`/`limit`/`skip`/`$group`/`$lookup` có cần merge lớn không?
- Có thể đưa shard key từ auth context hoặc lookup mapping vào query không?
- Key hashed có làm range predicates broadcast không?
- Chỉ một query shape gây vấn đề hay toàn bộ workload?
- Query có thật sự cần toàn cluster analytics không?

## 22. Tài liệu MongoDB chính thức

Các liên kết dưới đây dùng để tra cú pháp/giới hạn chính xác theo **MongoDB Server version**, đặc biệt là sharding DDL, targeting của write operations và resharding:

- [Sharding Introduction and Architecture](https://www.mongodb.com/docs/manual/sharding/) — shard key, shard, chunk/range, query router và kiến trúc tổng quan.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency, monotonicity và query patterns.
- [Troubleshoot Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-troubleshooting-shard-keys/) — data skew, uneven load distribution và scatter-gather.
- [Ranged Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/) — phân vùng liên tiếp theo khoảng khóa.
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/) — hash key, write distribution và range-query tradeoff.
- [Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/) — targeted vs broadcast, query modifiers, single/multi-writes.
- [Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — range migrations và balancing theo data distribution/zones.
- [Troubleshoot Stuck Chunk Migrations](https://www.mongodb.com/docs/manual/troubleshooting/chunk-migrations-stuck/) — balancer logs, jumbo/indivisible ranges và xử lý migration failure.
- [`sh.status()`](https://www.mongodb.com/docs/manual/reference/method/sh.status/) — xem chunk/zone/topology information bằng mongosh.
- [`db.collection.getShardDistribution()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsharddistribution/) — phân bố dữ liệu của một collection.
- [`sh.getShardedDataDistribution()`](https://www.mongodb.com/docs/manual/reference/method/sh.getshardeddatadistribution/) — owned/orphaned document size phân theo shard (6.0.3+).
- [`db.collection.analyzeShardKey()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.analyzeshardkey/) — đánh giá key candidate và read/write distribution.
- [`configureQueryAnalyzer`](https://www.mongodb.com/docs/manual/reference/command/configureQueryAnalyzer/) — bật query sampling dùng cho shard key analysis.
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/) — thêm suffix vào shard key hiện có.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — thay shard key, redistribution và production prerequisites.
- [Sharding Zone-Based Architecture](https://www.mongodb.com/docs/manual/core/zone-sharding/) — data residency và placement theo zones.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — unique constraints trên sharded collection.
- [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — routing/upsert/shard-key update restrictions theo version.
- [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — multi-update routing và atomicity từng document.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — đọc plan khi một hoặc nhiều shards tham gia.
- [Aggregation Pipeline on Sharded Collections](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-sharded-collections/) — split/merge pipeline và tối ưu aggregation.
- [Java Sync Driver — Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/) — tạo filter phù hợp với shard key.
- [MongoDB 8.0 Sharding Docs](https://www.mongodb.com/docs/v8.0/sharding/) — tham khảo dòng 8.0 khi deployment chưa dùng manual hiện hành.

## 23. Kết luận

**Sharding không tự bảo đảm hệ thống được chia đều.** Việc phân phối dữ liệu và định tuyến requests phụ thuộc trực tiếp vào **shard key pattern, giá trị shard key trong thực tế, query predicates và placement metadata**.

Khi gặp **điểm nóng ghi**, hãy tìm key tăng đơn điệu, hot tenant/hot key hoặc hot document, thay vì chỉ thêm shard. Khi thấy **dữ liệu lệch**, phân biệt owned bytes/chunks/orphans, balancer và zone constraints với workload QPS. Khi một **point query thiếu shard key**, hãy dùng `explain` kiểm tra nó có đang scatter-gather; index trên từng shard không thay thế shard targeting.

Biện pháp thường ít rủi ro nhất là **sửa query để có đủ shard key**, dùng index local phù hợp, giảm tác nhân gây hot workload và làm rõ access patterns. Nếu key hiện tại đã là nút thắt kiến trúc, mới đánh giá **refine hoặc reshard** với `analyzeShardKey`, dữ liệu đại diện, unique constraints và kế hoạch cutover. Một shard key tốt không phải key giúp tất cả truy vấn chạy trên một shard, mà là key **cân bằng được write distribution, data placement và đường truy cập quan trọng nhất của ứng dụng** trong thực tế.
