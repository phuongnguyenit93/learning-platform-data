# Ảnh hưởng của sharding đến aggregation, giao dịch và vận hành MongoDB

Một collection MongoDB có thể phát triển từ vài triệu đến hàng tỷ document, khiến một replica set đơn lẻ khó đáp ứng đồng thời dung lượng dữ liệu, tốc độ đọc/ghi và các báo cáo phức tạp. **Sharding** phân phối document của một collection qua nhiều shard để mở rộng theo chiều ngang. Nhưng khi dữ liệu đã nằm trên nhiều shard, một aggregation không nhất thiết còn xử lý trên một node; một transaction có thể cần điều phối nhiều replica set; và các công việc như cân bằng dữ liệu, tạo index hay sao lưu trở thành hoạt động toàn cụm.

Ví dụ, cùng một pipeline `$group` theo tenant:

- Nếu dữ liệu cần đọc nằm trên một shard, có thể được xử lý gần như một pipeline thông thường trên shard đó.
- Nếu document của nhiều tenant hoặc một tenant nằm trên nhiều shard, MongoDB phải thu thập **kết quả cục bộ** và có thể **hợp nhất** chúng để tính ra tổng đúng toàn cụm.
- Nếu tiếp tục `$sort` và `$limit`, thứ tự/top N phải được xác định **trên dữ liệu toàn cục**, không chỉ lấy top N của một shard.
- Nếu pipeline ghi kết quả ra một sharded collection hoặc dùng `$lookup` tới collection đã shard, quy tắc routing và các ràng buộc của stage trở nên quan trọng.

Tương tự, thao tác chuyển tồn kho giữa hai kho trên **hai shard khác nhau** vẫn có thể được bao trong distributed transaction ở các phiên bản hỗ trợ, nhưng chi phí commit, rủi ro abort và độ trễ thường cao hơn một atomic update trên một document.

Bài thuộc chương **Sharding** của module *Database Engine Document MongoDB*, tập trung vào ba trục **aggregation – giao dịch – vận hành**. Ví dụ minh họa bằng **mongosh** và **Node.js Driver**; các thao tác sharding/configuration chỉ dành cho **sharded cluster lab**. MongoDB phát triển qua nhiều phiên bản, vì vậy một số hỗ trợ như `$lookup` tới sharded collection, distributed transactions, online resharding, DDL và định dạng `explain` cần được kiểm tra theo phiên bản server/driver và môi trường managed đang dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả luồng truy vấn từ driver qua `mongos`, config servers và những shard chứa dữ liệu.
2. Giải thích **targeted operation** với shard key và **scatter-gather** khi không định tuyến hẹp được.
3. Dự đoán lúc nào aggregation cần xử lý trên nhiều shard và có bước **merge kết quả**.
4. Hiểu cách `$match`, `$group`, `$sort`, `$skip` và `$limit` chịu ảnh hưởng của sharding.
5. Nhận biết chi phí fan-out và điều kiện chọn shard trong `$lookup`, cùng hạn chế của `$out` và `$merge`.
6. Phân biệt aggregation đọc thuần túy với pipeline ghi kết quả ra collection.
7. Phân biệt atomic update một document, transaction trong một shard và **cross-shard transaction**.
8. Xây transaction có session, shard-key-aware filters, idempotency, read/write concern và xử lý retry đúng.
9. Nhận diện giới hạn transaction theo thời gian, cache, DDL, chunk migration và phối hợp commit.
10. Giải thích balancer, chunks/ranges, data skew, hot shard, thay đổi shard key và resharding.
11. Đo hiệu năng từ `explain()`, các thống kê theo shard, index và network/merge overhead.
12. Thiết kế công việc batch, báo cáo, backup và rollout schema phù hợp với sharded cluster.

## 2. Kiến trúc ảnh hưởng đến toàn bộ đường đọc/ghi

Một sharded cluster gồm các thành phần chính:

- **`mongos`:** query router nhận lệnh từ ứng dụng, dựa vào metadata để quyết định shard nào cần tham gia. Đây không phải nơi lưu đầy đủ dữ liệu ứng dụng.
- **Config server replica set (CSRS):** lưu metadata về collections, chunks/ranges, phân phối dữ liệu và thông tin cấu hình của cụm.
- **Shards:** mỗi shard thường là một **replica set** giữ một phần dữ liệu của các sharded collections. Một unsharded collection vẫn nằm trên một shard sở hữu nó theo metadata.
- **Balancer/metadata services:** điều phối phân phối ranges/chunks để cân bằng theo chính sách và topology; cơ chế cụ thể có thể thay đổi theo phiên bản.

~~~mermaid
flowchart TD
    Client["Driver / API"] --> Router["mongos query router"]
    Router <-->|"Metadata/routing"| Config["Config Server Replica Set"]
    Router --> S1["Shard A (Replica Set)"]
    Router --> S2["Shard B (Replica Set)"]
    Router --> S3["Shard C (Replica Set)"]
    S1 --> P1["Range dữ liệu 1"]
    S2 --> P2["Range dữ liệu 2"]
    S3 --> P3["Range dữ liệu 3"]
~~~

### 2.1. Sharding khác replication

| Khía cạnh | Replication | Sharding |
|---|---|---|
| Mục tiêu chính | Dự phòng, HA, phục hồi qua failover | Phân phối dữ liệu và tải theo chiều ngang |
| Dữ liệu trên member | Secondary sao chép dữ liệu của replica set | Mỗi shard giữ **một phần** collection đã shard |
| Thành phần quyết định ghi | Primary của replica set | `mongos` định tuyến tới shard, rồi primary của shard nhận ghi |
| Đọc phân tán | Read preference chọn member trong replica set | Query có thể phải đọc **nhiều shards**, mỗi shard lại có replica set members |
| Sự cố cần chú ý | Lag/election/majority | Routing, chunk placement, balancer, scatter-gather, sự cố nhiều shards |

Thêm shard **không tương đương** thêm secondary. Thêm secondary vào shard tăng khả năng dự phòng/phân tải đọc của shard đó; thêm shard có thể chia dữ liệu nhưng khiến cross-shard query và transaction phải điều phối nhiều nơi hơn.

### 2.2. Metadata định tuyến không phải dữ liệu phân quyền

`mongos` dùng shard key để xác định nơi lưu document. Điều đó **không thay thế** kiểm tra `tenantId` và quyền truy cập. Một truy vấn tìm đúng shard nhưng thiếu filter tenant vẫn có thể trả dữ liệu sai quyền nếu tầng ứng dụng không kiểm soát.

## 3. Shard key quyết định aggregation phải chạm những shard nào

Giả sử collection `orders` shard theo:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Đây là compound **ranged shard key**. MongoDB phân phối dữ liệu theo các range của khóa đã chọn. Việc query có được định tuyến hẹp hay không phụ thuộc **filter trên shard key**, vị trí các range hiện tại và cách metadata chia/phân phối chunks.

### 3.1. Point query đủ shard key

~~~javascript
db.orders.findOne({
  tenantId: "t-01",
  orderId: "o-001"
})
~~~

Với equality trên toàn bộ shard key và metadata hợp lệ, `mongos` thường có thể định tuyến tới shard chứa khóa đó. Điều này đặc biệt có ích cho API đọc/sửa một order.

### 3.2. Chỉ có tiền tố shard key

~~~javascript
db.orders.find({ tenantId: "t-01" })
~~~

Filter trên tiền tố `tenantId` có thể giúp `mongos` xác định **những ranges liên quan** và loại bớt shard không chứa chúng. Tuy nhiên, **không bảo đảm chỉ một shard**: nhiều chunks của cùng tenant có thể nằm trên nhiều shards. Không khẳng định “có tenantId là luôn targeted tới một shard”.

### 3.3. Thiếu shard key

~~~javascript
db.orders.find({ status: "PAID" })
~~~

`status` không thuộc shard key. Khi không có cơ chế routing khác chứng minh shard chứa dữ liệu, query có thể bị gửi tới **mọi shard liên quan** — thường gọi là **scatter-gather**.

### 3.4. Bảng routing tư duy

| Query predicate | Với shard key `{tenantId:1,orderId:1}` | Khả năng routing |
|---|---|---|
| `tenantId=t-01, orderId=o-001` | Full equality | Thường target shard chứa key |
| `tenantId=t-01` | Equality theo tiền tố | Có thể chỉ một hoặc nhiều shards tùy chunk placement |
| `tenantId=t-01, orderId>{$gt:o-050}` | Range có tiền tố | Những shards chứa ranges liên quan |
| `orderId=o-001` | Bỏ field đầu | Có thể scatter tới nhiều shards |
| `status=PAID` | Không có shard key | Thường scatter-gather |
| Không có `$match` | Không giới hạn dữ liệu | Thường đọc toàn collection phân tán |

**Nguyên tắc:** xác định có **bao nhiêu shard được chạm** trước khi hỏi query dùng index nào. Một query mỗi shard đều có IXSCAN nhanh vẫn có thể tốn tổng network/merge nếu gửi tới rất nhiều shards.

## 4. Shard key ranged và hashed: đánh đổi với analytics

MongoDB hỗ trợ shard key dạng range và hashed (cùng những biến thể/khả năng theo phiên bản).

### 4.1. Ranged shard key

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

Ưu điểm có thể gồm:

- Filter theo tiền tố tenant và khoảng orderId có cơ hội định tuyến ranges.
- Một số truy vấn sort/range trên shard key thuận lợi.
- Dễ lý giải theo thứ tự khóa.

Nhược điểm:

- Nếu `orderId` tăng liên tục hoặc một tenant có lưu lượng cực lớn, vùng khóa đang nhận ghi có thể thành **hot range**.
- Tenant lớn có thể trải nhiều chunks/shards; chỉ lọc tenant không bảo đảm một shard.
- Quy mô và độ chọn lọc phụ thuộc cardinality/phân phối tenant, không chỉ số lượng field.

### 4.2. Hashed shard key

~~~javascript
{ orderId: "hashed" }
~~~

Hash giúp phân tán những giá trị key có thứ tự tăng đều bằng cách ánh xạ chúng sang miền hash. Equality theo hashed key vẫn có thể route hiệu quả. Nhưng các range theo giá trị **orderId gốc** không còn tương ứng trực tiếp với thứ tự hash, nên range query có thể phải đọc nhiều shard.

### 4.3. Hash mỗi tenant chưa chắc chia tải tốt

~~~javascript
{ tenantId: "hashed" }
~~~

Nếu chỉ có vài tenant lớn và mọi đơn của một tenant mang cùng giá trị `tenantId`, hash của tenant đó vẫn **không đổi**. Một tenant rất nóng có thể tập trung vào một vùng khóa/shard, bất kể số shard toàn cụm tăng. Cần phân tích cardinality và độ lệch workload.

### 4.4. Chọn shard key dựa trên workload

Các câu hỏi cần trả lời:

1. API thường truy vấn theo tenant + orderId, theo date, hay phân tích toàn bộ tenants?
2. Lưu lượng ghi có tập trung vào range cuối của key tăng dần không?
3. Tenant lớn có cần trải nhiều shards không?
4. Query phải join theo customerId hoặc productId nhiều không?
5. Có yêu cầu uniqueness toàn cluster cho business key không?
6. Shard key có ổn định hay bị sửa thường xuyên?
7. Có kế hoạch resharding khi workload thay đổi không?

Không có một shard key tối ưu đồng thời cho **mọi** point lookup, range query, join, analytics và phân phối ghi.

## 5. Chuẩn bị lab có sharded collection

**Điều kiện:** kết nối mongosh tới `mongos` của **sharded cluster lab**, có quyền quản trị để shard collection và tạo index. Các câu lệnh trong mục này **không chạy trên production**, vì thay đổi sharding/index có tác động lâu dài. Không cần dùng số liệu lab để đánh giá tốc độ thực tế: dữ liệu ít có thể nằm toàn bộ trên một shard và chưa thể hiện chi phí phân tán.

### 5.1. Tạo database và orders

~~~javascript
use sharding_analytics_lab

db.createCollection("orders")

// Index chứa shard key; có thể thêm index khác theo workload.
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_tenant_order" }
)

// Chạy qua mongos trong lab, khi collection/database đủ điều kiện.
sh.shardCollection(
  "sharding_analytics_lab.orders",
  { tenantId: 1, orderId: 1 }
)
~~~

Đây là minh họa shard key. Tùy phiên bản, trạng thái collection, các index/unique constraint đã có và quyền, lệnh `sh.shardCollection` có thể yêu cầu chuẩn bị khác. Không ép sharding bằng cách bỏ qua lỗi metadata hoặc thay đổi unique index của dữ liệu production.

### 5.2. Dữ liệu orders

~~~javascript
db.orders.insertMany([
  {
    _id: "t01-o001", tenantId: "t-01", orderId: "o-001",
    customerId: "c-01", status: "PAID", region: "HCM",
    amount: NumberDecimal("120"),
    createdAt: ISODate("2026-06-01T08:00:00Z")
  },
  {
    _id: "t01-o002", tenantId: "t-01", orderId: "o-002",
    customerId: "c-02", status: "PAID", region: "HN",
    amount: NumberDecimal("80"),
    createdAt: ISODate("2026-06-02T08:00:00Z")
  },
  {
    _id: "t01-o003", tenantId: "t-01", orderId: "o-003",
    customerId: "c-01", status: "CREATED", region: "HCM",
    amount: NumberDecimal("60"),
    createdAt: ISODate("2026-06-03T08:00:00Z")
  },
  {
    _id: "t01-o004", tenantId: "t-01", orderId: "o-004",
    customerId: "c-03", status: "PAID", region: "DN",
    amount: NumberDecimal("150"),
    createdAt: ISODate("2026-06-04T08:00:00Z")
  },
  {
    _id: "t02-o005", tenantId: "t-02", orderId: "o-005",
    customerId: "c-01", status: "PAID", region: "HCM",
    amount: NumberDecimal("200"),
    createdAt: ISODate("2026-06-01T09:00:00Z")
  },
  {
    _id: "t02-o006", tenantId: "t-02", orderId: "o-006",
    customerId: "c-04", status: "REFUNDED", region: "HN",
    amount: NumberDecimal("75"),
    createdAt: ISODate("2026-06-02T09:00:00Z")
  },
  {
    _id: "t02-o007", tenantId: "t-02", orderId: "o-007",
    customerId: "c-04", status: "PAID", region: "DN",
    amount: NumberDecimal("175"),
    createdAt: ISODate("2026-06-03T09:00:00Z")
  },
  {
    _id: "t02-o008", tenantId: "t-02", orderId: "o-008",
    customerId: "c-05", status: "PAID", region: "HCM",
    amount: NumberDecimal("50"),
    createdAt: ISODate("2026-06-04T09:00:00Z")
  },
  {
    _id: "t03-o009", tenantId: "t-03", orderId: "o-009",
    customerId: "c-11", status: "PAID", region: "HN",
    amount: NumberDecimal("300"),
    createdAt: ISODate("2026-06-01T10:00:00Z")
  },
  {
    _id: "t03-o010", tenantId: "t-03", orderId: "o-010",
    customerId: "c-11", status: "CREATED", region: "DN",
    amount: NumberDecimal("90"),
    createdAt: ISODate("2026-06-02T10:00:00Z")
  },
  {
    _id: "t03-o011", tenantId: "t-03", orderId: "o-011",
    customerId: "c-12", status: "PAID", region: "HCM",
    amount: NumberDecimal("40"),
    createdAt: ISODate("2026-06-03T10:00:00Z")
  },
  {
    _id: "t03-o012", tenantId: "t-03", orderId: "o-012",
    customerId: "c-13", status: "PAID", region: "DN",
    amount: NumberDecimal("110"),
    createdAt: ISODate("2026-06-04T10:00:00Z")
  }
])
~~~

Chỉ insert một lần vào database lab rỗng. Chạy lại cùng `_id` sẽ lỗi duplicate key. Kiểm tra:

~~~javascript
db.orders.countDocuments({})                // 12
db.orders.countDocuments({ status: "PAID" }) // 9
~~~

Tổng doanh thu **PAID** (không cộng CREATED/REFUNDED) của dữ liệu lab:

| Tenant | Số đơn PAID | Tổng `amount` |
|---|---:|---:|
| `t-01` | 3 | 350 |
| `t-02` | 3 | 425 |
| `t-03` | 3 | 450 |
| **Tổng** | **9** | **1.225** |

Đây là mốc để kiểm tra aggregation **đúng kết quả logic** dù dữ liệu thực tế nằm trên một hay nhiều shard.

### 5.3. Chuẩn bị dữ liệu nhỏ cho join

~~~javascript
db.createCollection("orderLines")
db.orderLines.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "idx_lines_tenant_order" }
)

// Khi đang làm lab có thể shard orderLines.
sh.shardCollection(
  "sharding_analytics_lab.orderLines",
  { tenantId: 1, orderId: 1 }
)

db.orderLines.insertMany([
  { _id: "l-01", tenantId: "t-01", orderId: "o-001", sku: "A", qty: 2 },
  { _id: "l-02", tenantId: "t-01", orderId: "o-001", sku: "B", qty: 1 },
  { _id: "l-03", tenantId: "t-01", orderId: "o-002", sku: "A", qty: 1 },
  { _id: "l-04", tenantId: "t-02", orderId: "o-005", sku: "C", qty: 4 },
  { _id: "l-05", tenantId: "t-02", orderId: "o-005", sku: "D", qty: 1 },
  { _id: "l-06", tenantId: "t-03", orderId: "o-009", sku: "A", qty: 3 }
])
~~~

Không có ý nghĩa chắc chắn rằng collection `orders` và `orderLines` với cùng shard-key pattern sẽ có **cùng chunk placement trên cùng shard**; chúng có metadata/phân phối riêng. Tránh giả định rằng chỉ cần giống shard key thì join luôn là xử lý nội bộ một shard.

## 6. Aggregation có thể chạy theo hai phần: shard và merger

Trên một collection không shard, pipeline thường được giải thích như chuỗi stage đọc và biến đổi dữ liệu trên một nơi. Với sharded collection, `mongos` có thể **split pipeline** thành:

- **Phần chạy trên các shard** (*shards part*): đọc dữ liệu local, áp các stage có thể thực hiện phân tán.
- **Phần merge** (*merger part*): gom/hoàn tất kết quả trên dữ liệu từ các shard.

~~~mermaid
flowchart TD
    Query["aggregate trên orders"] --> Router["mongos"]
    Router --> A["Shard A: match + partial group"]
    Router --> B["Shard B: match + partial group"]
    Router --> C["Shard C: match + partial group"]
    A --> Merge["Merger: hoàn tất group / sort"]
    B --> Merge
    C --> Merge
    Merge --> Result["Kết quả toàn cluster"]
~~~

**Không phải mọi pipeline đều có cùng điểm split.** Optimizer quyết định theo stage, index, shard key, phiên bản và yêu cầu của các stage. Merger có thể ở `mongos` hoặc trên một shard/địa điểm thực thi phù hợp; không mặc định toàn bộ dữ liệu luôn được chuyển về router để thực thi mọi stage.

### 6.1. Vì sao có bước merge?

Một phép tổng doanh thu:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$amount" }
    }
  }
])
~~~

Nếu `t-01` có 100 đơn PAID trên Shard A và 80 đơn PAID trên Shard B, một nhóm local `t-01` ở Shard A **chưa phải** tổng doanh thu của tenant trên toàn cluster. Cần hợp nhất giá trị tương ứng từ mọi shard chứa document matching.

### 6.2. Streaming vs blocking stages

Một số stage có thể chạy từng document, nhưng những stage như global `$sort` hoặc `$group` thường cần trao đổi/gom kết quả. Trên sharded cluster, chi phí có thể gồm:

~~~text
T_total ≈ work ở các shard
        + network transfer
        + merge/finalize
        + coordination/queueing
~~~

Đây chỉ là **mô hình tư duy**, không phải công thức đo latency. Query có thể chạy shard phases song song, nên không cộng cơ học thời gian từng shard như chạy tuần tự.

## 7. `$match` sớm giúp giảm số shard và byte chuyển qua mạng

So hai pipeline:

~~~javascript
// A: phân tích tất cả đơn PAID.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$tenantId", total: { $sum: "$amount" } } }
])

// B: phân tích một order cụ thể của một tenant.
db.orders.aggregate([
  { $match: { tenantId: "t-01", orderId: "o-001" } },
  { $project: { _id: 0, orderId: 1, amount: 1 } }
])
~~~

Với shard key `{tenantId:1,orderId:1}`:

- A không có predicate shard key → thường phải xem xét tất cả shards.
- B có equality toàn bộ shard key → có thể định tuyến hẹp tới shard chứa order.

### 7.1. Vừa cần shard targeting, vừa cần index

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
)
~~~

Index này hỗ trợ lọc/sort theo tenant/status/date trên những shard liên quan. Nhưng nó không thay đổi fact rằng một truy vấn có `tenantId` thôi vẫn có thể cần nhiều shards nếu tenant có nhiều chunks phân tán.

### 7.2. Filter local vs filter sau aggregation

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$tenantId", total: { $sum: "$amount" } } },
  { $match: { _id: "t-01" } }
])
~~~

Ý nghĩa logic khác với một số filter trên document gốc nếu pipeline có biến đổi phức tạp; optimizer có thể đẩy những điều kiện tương đương về sớm, nhưng không được dựa vào khả năng đó cho mọi trường hợp.

Cách rõ ràng khi muốn chỉ phân tích tenant:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $group: { _id: "$status", n: { $sum: 1 } } }
])
~~~

Nếu filter phụ thuộc field được tính từ `$group`, không thể đẩy filter về collection gốc một cách tùy tiện.

### 7.3. Bảo mật tenant là điều kiện riêng

`$match: {tenantId:"t-01"}` giúp thu hẹp truy vấn **chỉ khi tenantId đúng với quyền đã xác thực**. Không tin tenantId từ payload do client tự cung cấp như một biện pháp phân quyền. Query targeting và authorization là hai lớp khác nhau.

## 8. `$group` trên sharded collection: tính cục bộ và toàn cục

Pipeline lab:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      paidOrders: { $sum: 1 },
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả đúng:

~~~text
t-01 -> paidOrders=3, revenue=350
t-02 -> paidOrders=3, revenue=425
t-03 -> paidOrders=3, revenue=450
~~~

### 8.1. Tối ưu partial aggregation

Khi stage/accumulator cho phép, MongoDB có thể thực hiện **partial aggregation trên từng shard**, rồi merge kết quả trung gian. Ví dụ:

~~~text
Shard A: t-01 revenue 200, t-02 revenue 150
Shard B: t-01 revenue 150, t-02 revenue 275
Merger:  t-01 revenue 350, t-02 revenue 425
~~~

Điều này có thể giảm dữ liệu truyền về merger: thay vì mọi order, shard gửi một số summary. Nhưng **đây là tối ưu phụ thuộc plan**; một pipeline có những stage không thể phân tán tương tự, hoặc cần dữ liệu chi tiết về merger.

### 8.2. Group theo shard key không đồng nghĩa luôn chạy ở một shard

Với compound shard key `{tenantId:1,orderId:1}`, một tenant có thể trải nhiều shard. Group theo `tenantId` cần gộp phần của tenant nếu có mặt trên nhiều shards. Không suy luận “group theo tenant là local group” chỉ vì tenant là tiền tố shard key.

Ngược lại, group theo **toàn bộ shard key** có thể có những khả năng tối ưu riêng vì tất cả document cùng giá trị shard key thuộc cùng vùng định tuyến; vẫn cần `explain()` để hiểu pipeline thực tế.

### 8.3. Accumulator có ảnh hưởng đến khả năng phân tán

Các phép cộng/count/min/max có thể thường được tính từng phần rồi tổng hợp. Những phép tính cần thứ tự toàn cục hoặc ngữ nghĩa trên toàn bộ tập như một số window calculations, distinct distributions và pipelines có stage blocking có thể đòi hỏi thêm bộ nhớ, truyền dữ liệu hoặc bước finalize. Không mặc định mọi `$group` đều trở thành một `$group` cục bộ + một `$group` merge đơn giản.

## 9. `$sort`, `$limit` và `$skip` cần thứ tự toàn cục

Pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { amount: -1, tenantId: 1, orderId: 1 } },
  { $limit: 3 },
  { $project: { _id: 0, tenantId: 1, orderId: 1, amount: 1 } }
])
~~~

Top 3 đúng theo lab:

~~~text
t-03 / o-009 -> 300
t-02 / o-005 -> 200
t-02 / o-007 -> 175
~~~

### 9.1. Sai: lấy top 3 từ một shard rồi coi là top 3 toàn cụm

Giả sử:

~~~text
Shard A: 100, 90, 80
Shard B: 300, 200, 175
~~~

Top 3 toàn cục là 300, 200, 175, không phải kết quả riêng của Shard A. Trong aggregation sharded, optimizer có thể đẩy **local top-k** xuống từng shard khi an toàn, nhưng vẫn cần **merge sort/top-k** để chọn kết quả toàn cục.

### 9.2. Tối ưu sort + limit

MongoDB có thể coalesce `$sort + $limit` thành top-k, hoặc đẩy một giới hạn đủ lớn tới các shard trong trường hợp phù hợp. Điều này giảm lượng dữ liệu phải giữ/truyền, nhưng không có nghĩa mỗi shard chỉ đọc đúng K documents nếu không có index thích hợp.

### 9.3. Skip sâu không miễn phí

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, tenantId: 1, orderId: 1 } },
  { $skip: 100000 },
  { $limit: 20 }
])
~~~

`$skip` cần loại **100.000 kết quả đầu trong thứ tự toàn cục**. Trong một số kế hoạch, optimizer có thể phối hợp sort với giới hạn khoảng `skip + limit` ở các shard, nhưng lượng dữ liệu cần xem và merge vẫn có thể lớn. Một shard không thể độc lập bỏ 100.000 records của mình rồi trả kết quả chính xác cho trang toàn cụm.

Với feed sâu, cân nhắc **keyset pagination** dùng bộ khóa sort và điều kiện cursor; cần bảo đảm filter/shard key/index phù hợp.

### 9.4. Tie-breaker quan trọng hơn khi phân tán

Nếu sort chỉ theo `createdAt:-1`, nhiều order có thể cùng timestamp ở các shard khác nhau. MongoDB **không bảo đảm thứ tự của những document có cùng toàn bộ sort key**, nên phân trang có thể đảo thứ tự. Dùng tie-breaker thực sự duy nhất trong scope, ví dụ `tenantId + orderId` theo định nghĩa nghiệp vụ:

~~~javascript
{ $sort: { createdAt: -1, tenantId: 1, orderId: 1 } }
~~~

Điều kiện cursor cho keyset phải khớp chính xác mọi chiều sort. Nếu `orderId` chỉ unique **trong tenant**, không được dùng đơn lẻ làm tie-breaker toàn cluster.

## 10. `$facet`, `$setWindowFields` và phân tích nâng cao

Các stage này hữu ích cho dashboard nhưng có thể tạo điểm nghẽn khi dữ liệu từ nhiều shards phải hợp nhất.

### 10.1. `$facet`: nhiều nhánh từ cùng tập đầu vào

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $facet: {
      byTenant: [
        { $group: { _id: "$tenantId", revenue: { $sum: "$amount" } } },
        { $sort: { revenue: -1, _id: 1 } }
      ],
      topOrders: [
        { $sort: { amount: -1, tenantId: 1, orderId: 1 } },
        { $limit: 3 },
        { $project: { _id: 0, tenantId: 1, orderId: 1, amount: 1 } }
      ]
    }
  }
])
~~~

`$facet` tạo **một document kết quả chứa các mảng**. Nó có giới hạn bộ nhớ riêng (thông thường **100 MiB đối với document xử lý trong facet**) và kết quả BSON cuối vẫn phải tuân thủ **16 MiB/document**. `allowDiskUse` không làm `$facet` tự spill vượt giới hạn của nó. Đừng gom mọi item/report vào một facet khổng lồ.

Khi sharding, cần hiểu phần dữ liệu nào được tập hợp trước facet và tại đâu; đây không phải kỹ thuật đảm bảo mọi nhánh chạy phân tán tối ưu. Đặt `$match` sớm và giới hạn output khi đúng nghiệp vụ.

### 10.2. Window functions

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: { createdAt: 1, orderId: 1 },
      output: {
        runningRevenue: {
          $sum: "$amount",
          window: { documents: ["unbounded", "current"] }
        }
      }
    }
  }
])
~~~

Tính tổng chạy theo tenant cần **thứ tự và phân hoạch đầy đủ**. Nếu một tenant có dữ liệu trải nhiều shard, không thể tự tính một running total riêng ở mỗi shard rồi gọi đó là kết quả toàn tenant. Query planner phải xử lý/điều phối theo khả năng của stage và phiên bản, có thể tốn sort/memory và network.

### 10.3. Group nhiều chiều

Một báo cáo nhóm theo `tenantId, region, ngày` có thể tạo rất nhiều nhóm, đặc biệt nếu thời gian chia đến phút/giây. Dù đã chia dữ liệu, cuối pipeline vẫn có thể bị nghẽn ở bước merge hoặc chuyển kết quả qua mạng. Giảm cardinality nhóm, dùng pre-aggregation cho dashboard quan trọng và đo footprint.

## 11. `$lookup` khi collection được join cũng là sharded

MongoDB hỗ trợ `$lookup` với foreign `from` là sharded collection trên các phiên bản hiện đại (ví dụ từ **MongoDB 5.1**). Trước khi sử dụng trên cluster legacy, kiểm tra giới hạn theo phiên bản.

Giả sử `orders` và `orderLines` đều sharded. Một join đơn giản chỉ theo orderId:

~~~javascript
{
  $lookup: {
    from: "orderLines",
    localField: "orderId",
    foreignField: "orderId",
    as: "lines"
  }
}
~~~

có thể **không đủ điều kiện định tuyến tối ưu** khi shard key foreign là `{tenantId,orderId}`, đồng thời sai về tenant nếu orderId được tái sử dụng giữa tenants.

### 11.1. Join đủ tenant + orderId

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", orderId: "o-001" } },
  {
    $lookup: {
      from: "orderLines",
      let: {
        t: "$tenantId",
        o: "$orderId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$orderId", "$$o"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 0,
            sku: 1,
            qty: 1
          }
        }
      ],
      as: "lines"
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: 1,
      orderId: 1,
      lines: 1
    }
  }
])
~~~

Với lab, order `t-01/o-001` có hai dòng hàng: SKU A qty 2 và SKU B qty 1.

### 11.2. Không tự bảo đảm targeted foreign lookup

Việc foreign pipeline có `$expr` so sánh với `let` **không mặc định** khiến mọi lookup trở thành một lần truy cập đúng một shard hay dùng compound index. Điều này phụ thuộc:

- Khả năng optimizer suy ra shard key equality và route phù hợp.
- Index ở foreign collection, nhất là `tenantId + orderId`.
- Biến `let` có giá trị xác định, không missing/null.
- Pipeline stages/expressions, collation và khả năng dùng index.
- Topology/shard key/phiên bản.

Kiểm tra `explain("executionStats")` và thống kê **shards touched, foreign documents/keys examined, output size**. Khi không thể route hiệu quả, một lookup có thể fan-out qua nhiều shards, nhân lên theo số local inputs.

### 11.3. Fan-out và kích thước output

`$lookup` gắn mảng vào **mỗi local document**. Nếu một order có 100.000 lines, output có nguy cơ vượt giới hạn 16 MiB dù các lines nằm phân tán trên shards. Dùng foreign `$match`, `$project`, `$sort`, `$limit` khi phù hợp, hoặc truy vấn/paginate lines riêng.

### 11.4. Collocation không tự phát sinh từ shard key giống nhau

Hai collections cùng shard key pattern có thể được chunk và balance **độc lập**. Không suy ra order document và orderLines document có cùng tenant/order sẽ ở chung một shard. Nếu workload đòi hỏi data locality, cần mô hình dữ liệu, zone/placement strategy hoặc cách tổ chức phù hợp và kiểm tra cluster thực tế.

## 12. `$merge` và `$out`: ghi kết quả aggregation trong cụm sharded

Aggregation đọc thuần có thể chỉ trả cursor, nhưng báo cáo ETL thường cần **ghi kết quả** vào collection đích.

### 12.1. `$merge`: upsert/update materialized result

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$amount" },
      paidOrders: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      tenantId: "$_id",
      reportType: { $literal: "paid_revenue" },
      revenue: 1,
      paidOrders: 1
    }
  },
  {
    $merge: {
      into: "tenantReports",
      on: ["tenantId", "reportType"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
~~~

Để ví dụ chạy được, cần **chuẩn bị trước** collection `tenantReports` cùng một **unique index phù hợp với `on`**, kiểm tra điều kiện hiện có và phiên bản. Ví dụ collection đích **unsharded**:

~~~javascript
db.createCollection("tenantReports")
db.tenantReports.createIndex(
  { tenantId: 1, reportType: 1 },
  { unique: true, name: "uq_tenant_report_type" }
)
~~~

Trong thực hành, hãy **tạo collection/index trước khi chạy `$merge`** để không phụ thuộc hành vi tự tạo đích. `whenMatched:"replace"` cần giữ các key phù hợp và tính đến `_id`; bảo đảm dữ liệu output match đúng unique index đã chọn.

### 12.2. Ghi vào sharded collection

`$merge` có thể ghi vào sharded output collection trong điều kiện được hỗ trợ, nhưng `on` fields và unique index phải tuân thủ ràng buộc **shard key** (thường cần chứa **toàn bộ các field shard key** và các quy tắc tương ứng). Không shard `tenantReports` theo `{tenantId, reportType}` rồi dùng tùy ý `on:["reportType"]` — nó không đủ thông tin/ràng buộc uniqueness cho đích sharded.

### 12.3. `$out` không phải bản sao của `$merge`

`$out` ghi lại kết quả pipeline vào collection đích theo semantics thay collection và có các giới hạn DDL/đích riêng. Đặc biệt, **`$out` không thể xuất trực tiếp vào một sharded collection như một replacement tùy ý** theo quy tắc hỗ trợ của MongoDB. Nó cũng có thể tác động đến index/metadata workflow và concurrency ở collection đích.

Không chọn `$out` chỉ vì “đỡ viết `on`” nếu đích là sharded collection hoặc có readers cần ổn định.

### 12.4. Cả `$merge` và `$out` đều không dùng trong transaction

Hai output stages này không được phép trong multi-document transaction. Nếu cần báo cáo nhất quán:

- Dùng dữ liệu đầu vào có cutoff/version/snapshot phù hợp.
- Materialize kết quả ngoài transaction.
- Kiểm tra hoàn tất và chuyển `activeReportVersion` bằng một atomic update nhỏ.
- Thiết kế retry/idempotency vì pipeline có thể thất bại giữa quá trình ETL.

### 12.5. Ghi kết quả aggregation không tự bảo đảm snapshot toàn job

Một job aggregate kéo dài trong khi writers vẫn đang ghi có thể quan sát dữ liệu theo semantics read concern đang dùng. Nếu yêu cầu “doanh thu đúng lúc 00:00 UTC”, cần xác định cutoff, trạng thái thanh toán và cách đọc nhất quán; không chỉ thêm `$merge` ở cuối.

## 13. Index trên sharded collection: routing và tìm kiếm là hai việc khác nhau

Một query thường có hai pha tư duy:

1. **Router tìm shard liên quan** theo shard-key metadata.
2. **Tại mỗi shard**, query planner chọn index scan/collection scan và các stage tiếp theo.

Ví dụ:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    orderId: 1
  },
  { name: "idx_tenant_status_date_order" }
)
~~~

Index có thể hữu ích cho danh sách PAID của tenant theo ngày. Nhưng:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, orderId: 1 } },
  { $limit: 20 }
])
~~~

không có shard-key filter, nên có thể scatter tới nhiều shards, dù mỗi shard đều có index tốt cho `status/createdAt` nếu index được thiết kế đúng. Ngược lại, một query targeted tới một shard vẫn có thể là COLLSCAN nếu index không hỗ trợ predicate.

### 13.1. Một index không có hiệu quả giống nhau cho mọi pipeline

| Pipeline | Yếu tố cần xét |
|---|---|
| `$match` full shard key | Định tuyến hẹp; index trên shard key có ích |
| `$match` chỉ tenant | Có thể chạm nhiều ranges/shards, cần secondary index cho status/date nếu dùng |
| `$match` chỉ status | Có thể scatter; index trên status có thể giảm đọc local nhưng không giảm số shard |
| `$group` theo tenant | Có thể partial group rồi merge; shard key không mặc định loại global merge |
| `$sort` theo field tính toán | Index trên document gốc có thể không hỗ trợ |
| `$lookup` tới foreign sharded | Cần xem shard key foreign, foreign index, số shard touched |

### 13.2. Index unique trong sharded collection

MongoDB có giới hạn về **unique indexes trên sharded collections**: thông thường unique constraint được hỗ trợ trên index mà **shard key là tiền tố** của index, với ngoại lệ/quy tắc cụ thể theo phiên bản. `_id` index vẫn tồn tại, nhưng nếu `_id` không phải shard key, cơ chế uniqueness toàn cluster cần được hiểu cẩn thận; không mặc định mọi `_id` được enforce toàn cục trong mọi cấu hình sharded.

Ví dụ business key duy nhất theo tenant/order:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

là ứng viên phù hợp nếu nó cũng là shard key/unique index theo quy tắc của collection. Không chỉ dùng `orderId` khi mã chỉ duy nhất trong tenant.

### 13.3. Index build có tác động vận hành

Tạo index trên sharded collection liên quan đến các shard/replica set chứa dữ liệu; có thể làm tăng CPU, I/O, disk và replication load. Cần rollout/migration kế hoạch, kiểm tra tính nhất quán index giữa shards và đo tác động đến cả transaction, balancer.

## 14. `explain()` cho aggregation trên sharded cluster

Truy vấn:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

Hãy đọc `explain` theo **kế hoạch toàn cluster**, không chỉ một `winningPlan` duy nhất.

### 14.1. Các thành phần có thể thấy

Tùy phiên bản/classic engine/SBE/optimizer, output có thể chứa:

- Các phần `shards`, `splitPipeline`, `shardsPart` và `mergerPart` hoặc một biểu diễn khác cho cấu trúc phân tán.
- `SHARDING_FILTER`/routing-related stages trong một số kế hoạch.
- `IXSCAN`, `COLLSCAN` và `FETCH` ở các shard.
- `$mergeCursors`, merge sort/group hoặc các stages tương đương.
- Số document/index keys examined, number returned và execution stats riêng từng shard.
- Thông tin spill khi stage blocking vượt ngưỡng và được hỗ trợ.

Không coi một chuỗi stage cụ thể là bắt buộc trong mọi phiên bản. Một số optimizer đổi thứ tự/gộp stages; phải dựa vào **số liệu và kết quả**.

### 14.2. Câu hỏi đọc explain

1. Có bao nhiêu shards tham gia?
2. Những shards nào có `docsExamined` lớn nhất?
3. Có shard nào trả rất nhiều dữ liệu về merger không?
4. `$match` có thật sự được áp dụng trước bước trao đổi dữ liệu không?
5. `$group` đã tính partial aggregation ở shard hay đang gom full documents?
6. `$sort` có dùng index/top-k tối ưu hay blocking sort?
7. `totalKeysExamined`/`totalDocsExamined` có cao so với số document trả về?
8. Có spill ra disk hoặc merge bottleneck không?
9. Độ trễ cuối cùng bị chi phối bởi shard chậm nhất, mạng hay merger?
10. Nếu có `$lookup`, foreign side có phải chạm nhiều shards trên mỗi local row?

### 14.3. Compare targeted với scatter

~~~javascript
// Full shard key: thường target một shard.
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01", orderId: "o-001" } },
  { $project: { _id: 0, orderId: 1, amount: 1 } }
])

// Không có shard key: thường scatter.
db.orders.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$region", n: { $sum: 1 } } }
])
~~~

Trên dataset lab nhỏ, tất cả documents có thể vô tình nằm trên một shard/chunk nên chênh lệch không thể dùng làm benchmark. Kết luận về performance phải dựa trên cluster có phân phối và workload đại diện.

## 15. Bộ nhớ, network và spill khi aggregation phân tán

Sharding giúp chạy một số phần truy vấn song song, nhưng nhiều pipeline vẫn có **điểm tập trung tài nguyên**:

- Global `$sort` phải hợp nhất thứ tự từ nhiều shards.
- Một `$group` có số nhóm cực lớn có thể cần nhiều RAM hoặc disk.
- `$lookup` có fan-out lớn có thể tạo mảng/result lớn.
- `$facet` có giới hạn per-stage/per-document riêng.
- `$merge` phải phân phối writes tới collection đích.
- Mỗi document kết quả cuối vẫn chịu **16 MiB BSON limit**.

### 15.1. `allowDiskUse`

~~~javascript
db.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $group: { _id: "$customerId", total: { $sum: "$amount" } } },
    { $sort: { total: -1 } }
  ],
  { allowDiskUse: true }
)
~~~

`allowDiskUse` cho phép những stages hỗ trợ ghi tạm ra disk khi cần theo quy tắc phiên bản (các mặc định từ MongoDB 6.0 chịu ảnh hưởng `allowDiskUseByDefault`). Nó **không miễn phí**, không buộc index scan, không nâng giới hạn document 16 MiB, và không làm mọi stage như `$facet` có thể spill vô hạn.

### 15.2. Network bytes cũng là một tài nguyên

Một query trả 20.000 nhóm từ mỗi trong 10 shards có thể tạo lượng kết quả trung gian lớn chuyển về merger, ngay cả khi mỗi shard xử lý CPU rất nhanh. Theo dõi bytes transferred/network throughput, không chỉ query CPU.

### 15.3. Shard chậm nhất ảnh hưởng toàn pipeline

Nếu merger phải chờ kết quả từ tất cả shard, một shard bị thiếu index hoặc chịu disk saturation có thể kéo p95/p99 latency của aggregation toàn cluster lên. Một cluster “9 shards khỏe, 1 shard quá tải” vẫn có thể làm báo cáo scatter-gather chậm.

## 16. Transaction trên sharded cluster: một shard so với nhiều shards

MongoDB hỗ trợ multi-document transactions trên replica sets từ MongoDB 4.0 và **distributed transactions trên sharded clusters từ MongoDB 4.2** theo điều kiện triển khai. Một transaction trên sharded cluster có thể:

1. Chỉ chạm các document trên một shard.
2. Chạm các document trên nhiều shards.

Hai trường hợp cùng có ý nghĩa atomicity nhưng **chi phí điều phối khác nhau**.

### 16.1. Transaction một shard

~~~text
Business request:
  update order + ghi ledger
Các document ở cùng shard
=> Commit trong phạm vi một shard replica set
~~~

Không phải cứ một tenant là chắc chắn một shard. Cùng tenant có thể trải nhiều chunks; khác collection cũng không mặc định cùng placement.

### 16.2. Distributed transaction nhiều shards

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Router as mongos
    participant S1 as Shard A
    participant S2 as Shard B
    App->>Router: Bắt đầu transaction (session)
    Router->>S1: Ghi order
    Router->>S2: Ghi inventory
    Router->>S1: Ghi ledger nếu được route tới A
    App->>Router: commitTransaction
    Router->>S1: Phối hợp quyết định commit
    Router->>S2: Phối hợp quyết định commit
    S1-->>Router: Kết quả participant
    S2-->>Router: Kết quả participant
    Router-->>App: Outcome commit (có thể timeout/không rõ)
~~~

Sơ đồ lược giản quá trình commit phân tán: hệ thống có cơ chế điều phối theo protocol/tài nguyên phù hợp, không phải mọi participant trả lời theo trình tự cứng như biểu đồ. Khi transaction chạm nhiều shards, có thêm network, metadata routing, commit coordination, khả năng lỗi ở từng participant và chi phí giữ snapshot/locks.

### 16.3. Không có “cross-shard = không atomic”

Nếu distributed transaction được hỗ trợ và commit thành công theo điều kiện áp dụng, những ghi MongoDB của transaction vẫn có ngữ nghĩa **all-or-nothing**. Đánh đổi là chi phí, latency, rủi ro abort và độ phức tạp phục hồi, **không phải** phải chấp nhận partial commit như bình thường.

### 16.4. Không phải mọi workflow cần distributed transaction

Nếu cần cập nhật một order chứa tổng số tiền và trạng thái trong cùng document, atomic single-document update vẫn là giải pháp đơn giản. Nếu workflow chạy qua MongoDB + payment gateway + email, distributed MongoDB transaction **không** bao được các hệ thống ngoài MongoDB. Cần outbox/idempotency/saga.

## 17. Thiết kế data model để giảm cross-shard transactions

Ví dụ một nghiệp vụ giữ hàng:

~~~text
1. Tạo order
2. Giảm inventory
3. Ghi request ledger
4. Phát event OrderCreated
~~~

Nếu orders, inventory, request ledger ở ba sharded collections khác nhau, các document có thể nằm trên **ba shards khác nhau**. Chỉ dùng một `tenantId` trong các shard keys không bảo đảm chúng nằm chung shard.

### 17.1. Co-location là mục tiêu thiết kế, không phải mặc định

Muốn giảm cross-shard transactions:

- Xem xét những document nào thường phải cập nhật nguyên tử cùng nhau.
- Nếu invariant thực sự nằm trong một document, nhúng đúng phạm vi có giới hạn.
- Nếu cần nhiều documents, chọn shard key và placement strategy dựa trên **khả năng định tuyến/cùng phạm vi** thực tế, không dựa vào tên key giống nhau.
- Đo số shards touched của transaction, không chỉ tổng số documents.
- Tránh một global counter document bị tất cả tenants cùng cập nhật.

### 17.2. Trade-off giữa locality và hot shard

Dồn mọi order của một tenant lớn vào một shard có thể giảm một số cross-shard operations nhưng tạo **hot tenant/hot shard**. Phân tán order của tenant đó ra nhiều shards tăng throughput nhưng khiến các báo cáo/transaction theo toàn tenant cần merge/coordination.

Không có thiết kế tuyệt đối tốt: hãy chọn theo access patterns và khả năng mở rộng, rồi đo thực tế.

### 17.3. Dùng request ledger để bảo vệ retry

Ngay cả khi transaction atomic, HTTP request có thể bị gửi lại sau khi commit thành công nhưng phản hồi bị mất. Ledger có unique constraint trên **scope nghiệp vụ** như `{tenantId,requestId}` giúp nhận diện một intent và replay kết quả. Trên sharded collection, unique index cần tương thích shard key.

## 18. Chuẩn bị collection cho transaction lab

Trên `mongos` của cluster lab:

~~~javascript
use sharding_analytics_lab

db.createCollection("inventory")
db.inventory.createIndex(
  { tenantId: 1, sku: 1 },
  { name: "idx_inventory_tenant_sku" }
)
sh.shardCollection(
  "sharding_analytics_lab.inventory",
  { tenantId: 1, sku: 1 }
)

db.createCollection("requestLog")
db.requestLog.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)
sh.shardCollection(
  "sharding_analytics_lab.requestLog",
  { tenantId: 1, requestId: 1 }
)

db.inventory.insertMany([
  { _id: "inv-t01-A", tenantId: "t-01", sku: "A", available: 10, reserved: 0 },
  { _id: "inv-t02-A", tenantId: "t-02", sku: "A", available: 7, reserved: 0 },
  { _id: "inv-t03-B", tenantId: "t-03", sku: "B", available: 20, reserved: 0 }
])
~~~

Trong cluster thật, shard collection tạo từ một collection đã có unique indexes phải đáp ứng quy tắc shard-key/uniqueness của MongoDB. Khi muốn unique `{tenantId,requestId}`, shard key `{tenantId,requestId}` là một lựa chọn tương thích về mặt tiền tố, nhưng phải kiểm tra version, trạng thái collection, dữ liệu đã tồn tại và sharding restrictions trước khi chạy.

### 18.1. Vì sao setup nên làm ngoài transaction?

Một transaction nghiệp vụ không phải nơi để tạo collections, index và shard metadata. Một số DDL được hỗ trợ trong transaction ở phiên bản nhất định nhưng có hạn chế nghiêm ngặt, nhất là khi transaction ghi nhiều shards. Pre-create schema qua migration giúp transaction runtime ngắn và giảm lock contention.

### 18.2. Không dùng lab để ép dữ liệu nằm trên nhiều shards

Ba dòng inventory và mười hai orders quá nhỏ để đảm bảo tạo chunks và phân phối thực qua nhiều shards. Ví dụ code giải thích **semantics transaction có thể cross-shard**, nhưng không chứng minh một lần chạy cụ thể đã trải nhiều shard. Dùng tools/metadata và dữ liệu đại diện mới xác nhận participant shards thật.

## 19. Node.js Driver: transaction có định tuyến theo shard key

Ví dụ một intent “tạo order mới và giữ một đơn vị SKU” với `tenantId` đã được xác thực. Lệnh phải có session và các filter có **shard key đầy đủ** khi phù hợp để hỗ trợ routing.

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI, {
  serverSelectionTimeoutMS: 5000
});

await client.connect();

const database = client.db("sharding_analytics_lab");
const orders = database.collection("orders");
const inventory = database.collection("inventory");
const requestLog = database.collection("requestLog");

async function createOrderAndReserve({
  tenantId, requestId, orderId, sku, qty
}) {
  // tenantId cần lấy từ auth context, không tin client tự khai báo.
  if (!tenantId || !requestId || !orderId || !sku ||
      !Number.isSafeInteger(qty) || qty <= 0 || qty > 100) {
    throw new Error("INVALID_INPUT");
  }

  // Với payload cố định, serialize theo thứ tự field chủ động;
  // production cần canonical fingerprint/hash nếu payload phức tạp.
  const fingerprint = JSON.stringify({ orderId, sku, qty });
  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      // Cùng requestId + tenant chỉ được thực hiện một intent.
      const previous = await requestLog.findOne(
        { tenantId, requestId },
        { session }
      );

      if (previous) {
        if (previous.fingerprint !== fingerprint) {
          throw new Error("IDEMPOTENCY_KEY_REUSED");
        }
        return previous.result;
      }

      // Unique compound index là rào cuối cho hai request đồng thời.
      await requestLog.insertOne({
        tenantId,
        requestId,
        fingerprint,
        state: "PROCESSING",
        createdAt: new Date()
      }, { session });

      // Tất cả fields shard key inventory đều có equality.
      const stock = await inventory.updateOne(
        {
          tenantId,
          sku,
          available: { $gte: qty }
        },
        {
          $inc: {
            available: -qty,
            reserved: qty
          }
        },
        { session }
      );

      if (stock.matchedCount !== 1) {
        // Rejection là kết quả terminal theo contract lab.
        const result = { ok: false, code: "OUT_OF_STOCK", orderId };
        await requestLog.updateOne(
          { tenantId, requestId },
          { $set: { state: "COMPLETED", result } },
          { session }
        );
        return result;
      }

      // Ghi đủ shard key orders.
      await orders.insertOne({
        tenantId,
        orderId,
        status: "CREATED",
        sku,
        qty,
        createdAt: new Date()
      }, { session });

      const result = { ok: true, code: "CREATED", orderId };
      await requestLog.updateOne(
        { tenantId, requestId },
        { $set: { state: "COMPLETED", result } },
        { session }
      );
      return result;
    }, {
      readPreference: "primary",
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      maxCommitTimeMS: 10000
    });
  } finally {
    await session.endSession();
  }
}

// Ví dụ:
// await createOrderAndReserve({
//   tenantId: "t-01",
//   requestId: "reserve-1001",
//   orderId: "o-1001",
//   sku: "A",
//   qty: 1
// });

// Đóng client khi ứng dụng shutdown: await client.close();
~~~

### 19.1. Điều quan trọng hơn số dòng code

- `requestLog`, `inventory` và `orders` có thể nằm trên những shard khác nhau; transaction vẫn điều phối nguyên tử trong những topology được hỗ trợ.
- Filter `inventory` dùng equality trên `tenantId + sku`, đúng shard key của collection đó.
- `orders.insertOne` chứa `tenantId + orderId` nên có đủ khóa để route.
- Unique index `requestLog.{tenantId,requestId}` giúp chặn hai insert đồng thời cùng intent.
- `withTransaction` có thể retry callback do lỗi transient; không gọi payment/email trong callback.
- Nếu không đủ stock, lưu `OUT_OF_STOCK` để các retry cùng intent replay theo contract.
- `writeConcern:"majority"` quan trọng với durability khi commit, nhưng còn phải theo dõi latency/health của các shard.

### 19.2. Giới hạn của ví dụ

Ví dụ là **khung học tập**, không phải API production hoàn chỉnh. Cần bổ sung:

- Fingerprint canonical thực sự, authorization và validation dữ liệu.
- Kiểm tra duplicate key có thể phát sinh ở `requestLog` **hoặc** business order key; không coi mọi E11000 là replay thành công.
- Bounded retry/reconciliation khi hai requests cùng key tranh chấp nhưng ledger chưa nhìn thấy committed record.
- Xử lý `UnknownTransactionCommitResult`; không suy luận mọi exception nghĩa là transaction chưa commit.
- Quy tắc uniqueness của `orderId` và `_id` trên sharded collection; dùng business key/unique index tương thích shard key, không tin `_id` tùy ý luôn unique toàn cluster.
- Kiểm tra request ledger đã hoàn tất nếu client retry sau mất phản hồi.
- Cách ghi tiền tệ chính xác, reservation expiry và chính sách release stock nếu có.

### 19.3. Không tự biến mọi lỗi thành retry

Nếu `available` không đủ, đó là **kết quả nghiệp vụ**. Nếu một transaction abort vì write conflict, có thể retry body. Nếu commit outcome chưa rõ, cần retry commit/reconcile. Nếu shard key thiếu hoặc index bị lỗi, phải **sửa query/schema**, không retry mù.

## 20. Distributed commit, retry và kết quả không chắc chắn

### 20.1. `TransientTransactionError`

Khi một participant shard gặp write conflict, failover hoặc lỗi transient, transaction có thể bị abort và trả error label `TransientTransactionError`. Hướng xử lý:

1. Abort hoặc để driver helper abort attempt hiện tại.
2. Bắt đầu attempt transaction mới.
3. Đọc lại dữ liệu và kiểm tra lại điều kiện.
4. Thực hiện lại các ghi có cùng business intent.
5. Giới hạn retries bằng deadline, backoff và jitter phù hợp.

Không chỉ retry lệnh trên shard cuối cùng bằng snapshot đã abort. Các quyết định như “còn stock” có thể thay đổi sau một retry.

### 20.2. `UnknownTransactionCommitResult`

Commit phân tán có thể đã thành công nhưng phản hồi thất lạc:

~~~text
Client gửi commit
Shard participants hoàn tất theo protocol
Router/driver mất phản hồi
Client chưa biết outcome
~~~

Lúc này, **không tạo requestId mới rồi chạy lại business operation**. Dùng helper/driver retry **commit** của cùng attempt khi còn ngữ cảnh phù hợp; nếu hết ngân sách hoặc connection mất, dùng ledger để reconcile. Một read không thấy ledger ngay trên secondary stale không đủ chứng minh chưa commit.

### 20.3. Idempotency xuyên request

Retryable writes của driver không tự biến hai HTTP requests thành cùng một logical operation. Cần giữ `requestId` ổn định qua:

- Retry của HTTP client.
- Queue redelivery.
- Service restart.
- Failover primary của shard.
- Retry transaction body.
- Retry/reconcile sau unknown commit.

### 20.4. Không quên side effects ngoài MongoDB

Một transaction MongoDB không rollback email, payment gateway, message broker. Dùng **transactional outbox**:

~~~text
Transaction MongoDB:
  update order
  update inventory
  write requestLog
  write outbox event
Commit

Outbox relay:
  publish event at-least-once
Consumer:
  dedupe theo eventId ổn định
~~~

Outbox vẫn có thể gửi trùng khi relay crash sau publish trước đánh dấu SENT; consumer cần idempotency.

## 21. Transaction lifetime, cache và network khi có nhiều shards

Multi-document transaction có thời gian sống giới hạn, mặc định thường khoảng **60 giây** qua `transactionLifetimeLimitSeconds`. Distributed transaction phải chịu thêm network/routing/coordination giữa các shard participants. Transaction lớn có thể gặp:

- Lifetime exceeded.
- Write conflict hoặc lock acquisition timeout.
- `TransactionTooLargeForCache` hoặc áp lực WiredTiger cache.
- Error do topology/metadata/chunk migration thay đổi.
- Commit timeout/unknown result.
- BSON document lớn hơn 16 MiB.
- Lệnh hoặc thao tác không hỗ trợ trong transaction.

### 21.1. 16 MiB document khác tổng transaction

Giới hạn 16 MiB áp dụng cho **mỗi BSON document**. Trong phiên bản MongoDB hiện đại, một transaction có thể sinh **nhiều oplog entries**; không đồng nhất “16 MiB cho một oplog entry” với “tổng transaction phải nhỏ hơn 16 MiB”. Nhưng cache, lifetime và tài nguyên thực vẫn giới hạn kích thước transaction hữu dụng.

### 21.2. Thời gian chờ lock và commit

`maxTransactionLockRequestTimeoutMillis` liên quan thời gian chờ lock; `maxCommitTimeMS` trong driver options liên quan bước commit. Chúng không thay thế `transactionLifetimeLimitSeconds` và không phải cách “mở rộng transaction thành job hàng giờ”.

### 21.3. Giảm phạm vi cross-shard trước khi tăng timeout

Nếu transaction cập nhật 100.000 orders trên 15 shards, tăng timeout có thể khiến transaction giữ snapshot/locks lâu hơn, và retry tốn hơn. Tốt hơn là:

- Dùng điều kiện/index để chạm đúng document cần thiết.
- Chỉ giữ invariant bắt buộc trong transaction.
- Chia batch có checkpoint khi không cần all-or-nothing toàn lô.
- Thiết kế versioned cutover khi cần cho readers thấy bản dữ liệu hoàn chỉnh.
- Giảm số collections/shards tham gia nếu phù hợp.

## 22. Các thao tác bị hạn chế trong sharded transactions

Một số lệnh có thể chạy bình thường ngoài transaction nhưng bị giới hạn trong transaction.

### 22.1. `$out` và `$merge`

Không được dùng hai aggregation output stages này **bên trong multi-document transaction**. Nếu transaction cần cập nhật một summary nhỏ, dùng các CRUD statements tường minh trên collection đã tồn tại; nếu cần materialize báo cáo lớn, chạy job ngoài transaction với version/idempotency.

### 22.2. DDL và implicit collection creation

MongoDB hỗ trợ một số trường hợp tạo collection/index trong transaction từ phiên bản nhất định, nhưng có **giới hạn nghiêm ngặt**. Một transaction đang ghi trên nhiều shards không được mặc định vừa **tạo collection mới ngầm định** vừa ghi các namespace ở shard khác. Chuẩn bị collections và indexes **trước runtime** qua migration là thiết kế ít bất ngờ hơn.

### 22.3. Chú ý cùng transaction dùng primary

Transactions phải tuân theo yêu cầu read preference primary. Không dùng `readPreference:"secondary"` với ý tưởng đọc báo cáo trong transaction phân tán rồi vẫn ghi được. Các operations cần dùng **cùng session** và driver transaction options đúng.

### 22.4. Không chạy đồng thời các lệnh trên cùng transaction một cách tùy tiện

Trong Node.js Driver, **parallel operations trong cùng transaction không được hỗ trợ**. Đừng làm:

~~~javascript
await session.withTransaction(async () => {
  await Promise.all([
    orders.updateOne(filterA, updateA, { session }),
    inventory.updateOne(filterB, updateB, { session })
  ]);
});
~~~

Chạy các thao tác tuần tự, có kiểm tra `matchedCount` và xử lý lỗi rõ ràng.

### 22.5. Các special namespaces, admin commands

Không giả định mọi namespace hệ thống và mọi lệnh quản trị như `shardCollection`, `moveChunk`, index/collection DDL, `replSetReconfig` hay `explain` đều hợp lệ trong transaction. Thao tác quản trị/sharding nên ở quy trình vận hành **ngoài transaction nghiệp vụ** và theo hỗ trợ của phiên bản.

## 23. Chunk migration/balancer ảnh hưởng workload thế nào?

Một sharded collection được chia thành các **ranges/chunks** theo shard key. Khi phân phối dữ liệu lệch hoặc topology thay đổi, balancer/placement services có thể điều phối migration giữa shards.

### 23.1. Migration không phải copy file đơn giản

Di chuyển một chunk/range liên quan đến:

- Sao chép dữ liệu thuộc range tới shard đích.
- Bắt kịp thay đổi phát sinh trong lúc migration.
- Cập nhật ownership/metadata routing.
- Dọn dữ liệu cũ/orphan theo quy trình.

Các bước và mức khóa/điều phối thay đổi theo phiên bản; không tự chạy manual migration trên production chỉ vì thấy shard đang quá tải.

### 23.2. Tác động tới aggregation

Khi routing metadata thay đổi, `mongos` phải cập nhật thông tin định tuyến. Các query lớn xuyên nhiều shards có thể chịu thêm network/metadata overhead hoặc được server xử lý theo quy tắc consistency/routing hiện hành. Không cộng lặp document chỉ vì một chunk đang chuyển: server có cơ chế ownership/sharding filtering; nếu nhận sai kết quả, cần điều tra nghiêm túc chứ không “tự dedupe” tùy tiện.

### 23.3. Tác động tới transactions

Migration và transaction chạm cùng vùng dữ liệu/metadata có thể gây contention, chờ lock hoặc một số lỗi transient liên quan placement/chunk, khiến transaction cần retry. **Giữ transaction ngắn** giúp giảm cơ hội va chạm và làm việc cân bằng dễ hơn.

### 23.4. Balancer không xử lý mọi loại skew

Một shard có thể đầy dữ liệu nhưng không nóng; shard khác có ít dữ liệu nhưng nhận 70% writes vì shard key tập trung. Cân bằng **dung lượng/chunks** không đồng nghĩa cân bằng **CPU/QPS**. Nếu một giá trị shard key cực nóng, chunk không thể chia hợp lý theo key hoặc hoạt động chỉ dồn một range, có thể cần **đổi data model/shard key**.

## 24. Hot shard, data skew và “thêm shard nhưng không nhanh”

Giả sử có 5 shards, nhưng 80% order writes có `tenantId="t-major"` và shard key là `{tenantId:"hashed"}`. Mọi document của tenant có một hash key giống nhau; không có bảo đảm hash tự chia 80% lưu lượng của tenant thành 5 phần.

### 24.1. Các dạng skew

| Dạng skew | Ví dụ | Hậu quả |
|---|---|---|
| Storage skew | Một shard giữ phần lớn bytes | Disk pressure, khó bảo trì |
| Read skew | API chủ yếu hỏi một tenant/range | Hot read shard |
| Write skew | Insert tăng dần dồn vào range cuối | Hot primary shard |
| Computation skew | Aggregation group có một key cực lớn | Shard hoặc merger tốn RAM/CPU |
| Join skew | Một customer có hàng triệu order lines | `$lookup`/`$unwind` phình dữ liệu |
| Network skew | Một shard có RTT/throughput thấp | Global query bị kéo p99 |

### 24.2. Chọn shard key theo truy vấn thực

Một shard key giúp phân tán ghi nhưng khiến một báo cáo thời gian phải scatter có thể vẫn là đánh đổi chấp nhận được nếu write throughput là yêu cầu hàng đầu. Ngược lại, chọn shard key để mọi report nhanh nhưng khiến mọi insert vào một shard có thể làm toàn hệ thống nghẽn.

### 24.3. Tách OLTP và analytics khi cần

Với báo cáo nặng, đôi khi **một sharded OLTP cluster không nên gánh toàn bộ BI**. Có thể cân nhắc:

- Materialized summary collections.
- Incremental aggregation theo change streams/outbox.
- ETL sang warehouse/OLAP engine phù hợp.
- Lịch chạy báo cáo, resource quotas và pre-aggregation.
- Đọc trên secondary theo read preference nếu consistency cho phép, nhưng chú ý lag/tài nguyên của từng shard replica set.

Không phải mọi dashboard cần kiến trúc mới; hãy đo trước và chọn giải pháp theo SLO.

## 25. Resharding và thay đổi shard key

Shard key được chọn ban đầu có thể không còn phù hợp khi số tenant, pattern truy vấn hoặc dòng ghi thay đổi. MongoDB hỗ trợ **resharding collection** trên những phiên bản hiện đại (ví dụ từ MongoDB 5.0 với những ràng buộc/cải tiến theo các phiên bản sau).

### 25.1. Vì sao cần reshard?

- Shard key cũ phân bố dữ liệu lệch.
- Tenant nóng chỉ nằm trong một range và không chia được tải.
- Query phổ biến thay đổi từ `tenantId + orderId` sang `tenantId + createdAt` hoặc kiểu access khác.
- Cần thêm shard/zone với chiến lược placement mới.

### 25.2. Resharding là thay đổi vận hành lớn

Resharding có thể yêu cầu copy/sắp xếp lại lượng dữ liệu rất lớn, duy trì thay đổi trong thời gian chuyển đổi và có giai đoạn cutover metadata. Tài nguyên/throughput có thể bị tác động; cần xem hạn chế phiên bản, disk headroom, balancer, backup và khả năng rollback.

### 25.3. Không đổi shard key chỉ để cứu một query

Thay shard key ảnh hưởng **mọi** query, writes, unique constraints và data distribution. Nếu chỉ một báo cáo cuối ngày cần group toàn collection, thêm materialized summary hoặc analytics store có thể ít rủi ro hơn reshard hàng TB dữ liệu.

### 25.4. Quy trình triển khai gợi ý

1. Thu baseline query routing, chunk distribution, hot keys và application SLO.
2. Mô phỏng shard-key candidate trên dữ liệu/phân phối đại diện.
3. Kiểm tra unique indexes và compatibility.
4. Ước lượng disk/network/migration/cutover cost.
5. Thử resharding trên staging tương đương.
6. Chuẩn bị metrics, rollback/recovery và lịch vận hành.
7. Triển khai theo runbook chính thức của phiên bản/managed provider.
8. Xác minh targeted queries, aggregation plans và transaction paths sau cutover.

## 26. Zone sharding, locality và chính sách dữ liệu

Zone sharding cho phép gắn **phạm vi shard key** với nhóm shard/zone phù hợp để định hướng placement theo chính sách. Nó không tương đương member tags của replica set.

### 26.1. Zone khác replica set read tags

- **Zone sharding:** điều khiển **data placement** của shard-key ranges giữa shards.
- **Replica set member tags/read preference:** chọn **member** trong replica set để phục vụ read theo mục đích/vùng.

Đưa tenant châu Á vào một zone có thể giúp data locality nếu chunk placement và workload phù hợp, nhưng aggregation toàn cầu vẫn phải tổng hợp dữ liệu từ nhiều zones. Không dùng read preference tag thay shard-key placement.

### 26.2. Compliance và residency

Zone placement có thể hỗ trợ mục tiêu đặt dữ liệu theo vùng, nhưng không tự bảo đảm mọi yêu cầu pháp lý: backups, logs, replication members, các bản sao, config metadata và đường truyền mạng cũng phải được thiết kế/kiểm soát. Không suy ra một tag `region` là bằng chứng đủ về data residency.

### 26.3. Cross-zone transactions

Nếu một transaction chạm shards ở nhiều zones/regions, network RTT/partition risk và latency commit có thể lớn. Một model giữ hầu hết transaction local-zone có thể tốt cho latency, nhưng khó hơn khi có giao dịch xuyên vùng. Cần đo thực tế.

## 27. Read preference và read concern trong sharded cluster

Mỗi shard thường là một replica set; query có thể dùng read preference để chọn member, nhưng **shard routing** và **replica set member selection** là hai lớp khác nhau.

Ví dụ:

~~~text
Query thiếu shard key:
  mongos gửi tới Shard A, B, C
  mỗi shard chọn member phục vụ read theo readPreference
~~~

Mode `secondary` không làm query scatter trở thành targeted. Nó chỉ có thể chuyển phần đọc từ primary sang secondary trong từng shard theo điều kiện hỗ trợ.

### 27.1. Read concern local/majority/snapshot

- `local` phản ánh trạng thái local node theo semantics cho phép; có thể stale/rollback trong tình huống nhất định.
- `majority` yêu cầu dữ liệu đủ điều kiện majority-committed, nhưng **không đồng nghĩa mới nhất** nếu đọc secondary.
- `snapshot` có khả năng cung cấp điểm nhìn nhất quán hơn trong phạm vi lệnh/transaction hỗ trợ; điều kiện và tính năng có thể khác theo version/topology.

Không ghép một report từ nhiều shards rồi tự khẳng định “đây chắc chắn là snapshot đúng 00:00 UTC” nếu chưa chọn read concern và cutoff phù hợp.

### 27.2. Causal consistency và read-your-writes

Một user vừa tạo order trên primary của shard A rồi đọc qua secondary có thể chưa thấy đơn do replication lag. Causal sessions với majority read/write concern phù hợp có thể cung cấp guarantee nhân quả trong điều kiện hỗ trợ, nhưng có thể phải **chờ** secondary bắt kịp. Đối với flow quan trọng đọc ngay sau ghi, đọc primary thường dễ kiểm soát hơn.

### 27.3. Distributed transaction thường đọc primary

Không đặt read preference secondary cho transaction muốn ghi xuyên shards. Transaction cần tuân thủ quy tắc driver/server với primary, snapshot và commit concern; read preference của các read-only reporting queries nên cấu hình riêng.

## 28. Vận hành: quan sát cluster, shards và phân phối dữ liệu

Trong `mongosh` kết nối tới `mongos` của lab, có thể kiểm tra:

~~~javascript
sh.status()
~~~

Lệnh này giúp xem tổng quan sharded databases/collections, shards và metadata tương ứng, tùy phiên bản mongosh/server. Để xem danh sách shards khi có quyền admin:

~~~javascript
db.adminCommand({ listShards: 1 })
~~~

Để kiểm tra collection và plan:

~~~javascript
db.orders.getIndexes()

db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, orderId: 1 } },
  { $limit: 20 }
])
~~~

### 28.1. Những số liệu phải đo

| Mảng vận hành | Metric/quan sát |
|---|---|
| Phân phối data | Bytes/documents/chunks mỗi shard, skew lớn nhất |
| Routing | Số shards touched trên query quan trọng |
| Query | p95/p99 latency, docs/keys examined trên mỗi shard |
| Merger | Bytes transferred, merge CPU/memory, spill |
| Hot keys | Tỷ lệ reads/writes theo shard-key ranges/tenant |
| Replication | Lag, majority commit latency, election events từng shard |
| Balancer | Migration duration, failures, backlog và resource overhead |
| Transactions | Duration, abort/retry by label, participants, commit latency |
| DDL | Index build status, lock waits, schema drift trên shard |
| Storage | Disk/cpu/cache/network của từng shard và config server |
| Availability | Router errors, shard unavailable, config metadata issues |

Không phải mọi metric có sẵn nguyên tên trong MongoDB; một số cần lấy từ profiler/diagnostic tools, monitoring của cloud provider, command monitoring của driver hoặc instrumentation ứng dụng.

### 28.2. Phân biệt “query nhanh trên shard” với “query nhanh end-to-end”

Một shard có thể hoàn tất trong 20 ms, nhưng query scatter tới mười shard và hợp nhất 100 MB dữ liệu có thể mất lâu hơn nhiều. Đo từ **API/driver ở đầu cuối**, đồng thời phân tích chi tiết từng shard để tìm bottleneck.

### 28.3. Không benchmark bằng dataset quá nhỏ

12 orders trong lab không buộc MongoDB tạo/chia/di chuyển chunks như production. Explain có thể cho kết quả chỉ một shard hoặc COLLSCAN hợp lý. Lab dành cho semantics; benchmark cần dataset, số clients, key distribution và topology đại diện.

## 29. Backup, khôi phục và nâng cấp trong sharded cluster

Khi dữ liệu nằm ở nhiều shard, việc sao lưu không còn đơn giản như copy một tập file từ một node:

- Các shards có thể đang ghi ở những thời điểm khác nhau.
- Metadata chunks/collection placement nằm ở config server.
- Distributed transactions có thể commit xuyên shards.
- Balancer/migrations có thể thay đổi placement trong quá trình backup.

### 29.1. Backup nhất quán

Một backup có tính nhất quán cho toàn sharded cluster cần chiến lược/phần mềm **nhận biết sharding**, bao gồm dữ liệu shards và metadata/commit state phù hợp. Không copy độc lập snapshot của các shards tại thời điểm bất kỳ rồi cho rằng restore chắc chắn tái tạo một cluster nhất quán.

### 29.2. Restore và tính toàn vẹn business

Sau restore cần xác nhận:

- Collections và indexes tồn tại đúng, gồm shard keys/unique constraints.
- Chunk/zone metadata và kết nối routers hoạt động.
- Các transaction business không bị quan sát ở trạng thái nửa vời.
- Read/write API dùng shard-key filters đúng.
- Reporting/materialized views có thể cần replay/reconcile.

### 29.3. Nâng cấp version/FCV

Các tính năng aggregation, transaction, resharding và DDL phụ thuộc phiên bản server và **Feature Compatibility Version**. Khi nâng cấp:

1. Kiểm tra compatibility của driver/mongos/config servers/shards.
2. Theo lộ trình rolling upgrade được hỗ trợ.
3. Xác nhận FCV đúng giai đoạn.
4. Kiểm tra behavior thay đổi của query planner và explain.
5. Chạy lại tests về transactions, retry labels, lookup và output stages.

Không nâng từng shard tùy hứng rồi sử dụng ngay tính năng mới khi phần còn lại của cluster chưa ở version/FCV được hỗ trợ.

## 30. Change streams, ETL và dữ liệu phân tán

Sharded cluster hỗ trợ change streams theo các điều kiện phiên bản/topology. Một consumer có thể theo dõi thay đổi của một sharded collection hoặc ở phạm vi database/cluster phù hợp.

### 30.1. Tại sao có lợi cho analytics?

Thay vì mỗi phút chạy aggregation quét hàng tỷ orders, có thể:

~~~text
Order CREATED / PAID / REFUNDED
  -> Change Stream hoặc outbox
  -> Consumer cập nhật summary theo tenant/ngày
  -> Dashboard đọc summary nhỏ
~~~

Đánh đổi:

- Cần resume token/checkpoint và quy trình phục hồi khi consumer dừng.
- Event có thể được quan sát lại trong một số tình huống retry/restart; consumer phải idempotent.
- Không tự suy ra ordering toàn cluster giống một queue đơn nhất cho mọi business event; thiết kế khóa/order theo entity và consistency cần thiết.
- Khi update trạng thái, phải tránh cộng doanh thu hai lần hoặc không trừ doanh thu đã refund.

### 30.2. Outbox giúp nhất quán business event

Nếu cần bảo đảm event tương ứng với database commit, ghi outbox cùng transaction với order/stock, sau commit relay phát đi. Change stream có thể quan sát outbox changes; consumer vẫn cần dedupe theo eventId.

### 30.3. Khi nào ETL batch vẫn tốt?

Báo cáo cuối ngày có thể dùng cutoff/version, chạy aggregate theo batch, ghi materialized collection và publish version sau khi thành công. Change streams không tự biến mọi phép phân tích lịch sử thành streaming computation dễ dàng.

## 31. Lựa chọn chiến lược theo nhu cầu

| Nhu cầu | Thiết kế gợi ý | Cảnh báo |
|---|---|---|
| Đọc một order theo tenant + orderId | Full shard-key predicate, indexed lookup | Đừng chỉ query `_id` nếu nó không đủ routing/uniqueness |
| Báo cáo tất cả tenant theo ngày | Distributed aggregation hoặc summary store | Scatter/merge/network có thể đắt |
| Top 20 orders toàn cluster | `$match → $sort → $limit` với tie-breaker | Global merge, cần index và kiểm tra plan |
| Top 20 orders của một tenant | Shard-key prefix filter + index date | Tenant có thể trải nhiều shards |
| Join order với lines | Join cả tenant + orderId, foreign index | Foreign lookup có thể scatter; output fan-out |
| Tổng doanh thu theo tenant | Partial group/final merge hoặc materialized summary | Không coi local group là global |
| Dùng `$merge` vào sharded summary | Shard-key-aware `on` + unique index hợp lệ | Không mặc định output stage tương thích mọi key |
| Tạo replacement report | `$out` với đích được hỗ trợ, versioned cutover | Không output tùy ý vào sharded collection |
| Giữ hàng một SKU | Conditional atomic update một document | Retry API vẫn cần idempotency |
| Order + inventory + ledger | Transaction ngắn qua shards nếu cần | Commit latency, retry/unknown outcome |
| Import vài triệu documents | Batch checkpoints, idempotent upserts | Không gom thành một transaction khổng lồ |
| Đổi shard key | Resharding có runbook | Tài nguyên, availability, unique constraints |
| Đọc phân tải khỏi primary | Secondary read preference theo shard | Không giảm số shards touched; có thể stale |
| Dashboard SLA thấp | Incremental/materialized analytics | Freshness và reconciliation cần thiết kế |

## 32. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ sharding luôn làm mọi aggregation nhanh hơn | Scatter/merge có thể tốn hơn | Đo query routing và plan |
| Chỉ dùng status/index mà thiếu shard key | Nhiều shards vẫn bị query | Thiết kế shard-key-aware filters khi phù hợp |
| Có tenantId là chắc chắn một shard | Tenant có thể nhiều chunks/shards | Xem metadata placement và explain |
| Dùng hashed tenantId để “chia nhỏ một tenant cực lớn” | Cùng tenant hash tới cùng giá trị key | Chọn shard key đủ phân tán within-tenant |
| Sum kết quả group ở một shard như toàn cụm | Tổng sai | Global merge/final aggregation |
| Limit ở từng shard rồi coi là global top | Top N sai | Để MongoDB merge sort/limit |
| Skip sâu như một phép nhảy tức thì | Tốn duyệt/merge nhiều rows | Keyset pagination theo sort key |
| Sort không có tie-breaker | Pagination bất ổn giữa shards | Thêm khóa duy nhất trong scope |
| `$lookup` chỉ theo orderId khi orderId chỉ unique theo tenant | Join sai tenant, fan-out lớn | Join đủ tenant + orderId |
| Giống shard-key pattern nghĩa là cùng shard | Chunk placement độc lập | Kiểm chứng placement |
| Dùng `$out` vào sharded target | Unsupported behavior | Dùng `$merge` đúng ràng buộc hoặc versioned report |
| `$merge` thiếu shard key trong `on` | Lỗi/không đảm bảo uniqueness | Thiết kế output key và unique index phù hợp |
| Cho rằng transaction cross-shard không atomic | Hiểu sai transaction | Dùng distributed transaction đúng phiên bản |
| Cho rằng transaction cross-shard miễn phí | Commit/network/abort tăng | Giảm shards touched và scope |
| Retry mọi timeout bằng requestId mới | Có thể double-apply | Reconcile/idempotency key |
| Gọi payment/email trong transaction callback | Side effect có thể bị lặp | Outbox/external idempotency |
| Giữ transaction mở khi chạy ETL lâu | Lifetime/cache/locks | Batch + checkpoint |
| Chạy DDL/sharding metadata trong business transaction | Lỗi tương thích, contention | Migration ngoài runtime |
| Balancer cân bytes là cân QPS | Hot shard vẫn nóng | Đo workload skew, xét reshard |
| Đọc secondary nghĩa là đã target một shard | Scatter vẫn scatter | Phân biệt read preference và routing |
| Backup mỗi shard độc lập tùy thời điểm | Restore không nhất quán toàn cụm | Sharding-aware consistent backup |
| Đánh giá hiệu năng bằng 12 documents | Không đại diện cluster thật | Benchmark dữ liệu phân bố thực |

## 33. Bài thực hành tổng hợp

Sử dụng collections lab `orders`, `orderLines`, `inventory` và `requestLog`. Dự đoán **kết quả logic**, sau đó giải thích **routing/chi phí có thể xảy ra**. Không thực hiện thay đổi sharding trên production.

### Bài 1 — Targeted hay scatter?

Với shard key `{tenantId:1,orderId:1}`, phân loại:

~~~javascript
// A
db.orders.find({ tenantId: "t-01", orderId: "o-001" })

// B
db.orders.find({ tenantId: "t-01" })

// C
db.orders.find({ status: "PAID" })

// D
db.orders.find({ orderId: "o-001" })
~~~

Trường hợp nào thường target một shard? Trường hợp nào có thể nhiều shards? Vì sao?

### Bài 2 — Tổng PAID toàn cluster

Viết `$match` + `$group` + `$sort` lấy count/revenue PAID theo tenant. Dự đoán ba dòng và giải thích partial group vs merge.

### Bài 3 — Top 3 toàn cluster

Lấy ba order PAID có amount lớn nhất, sắp tie bằng tenantId/orderId. Vì sao không thể lấy kết quả riêng của một shard?

### Bài 4 — Phân trang

Giả sử muốn trang 5, mỗi trang 20 orders theo createdAt. Tính `skip` và giải thích tại sao skip phải áp vào thứ tự **toàn cục**; đề xuất keyset.

### Bài 5 — Join sharded foreign

Join order `t-01/o-001` với lines. Dùng `let` và `$expr` so sánh đầy đủ tenantId/orderId. Vì sao chỉ join orderId có thể sai?

### Bài 6 — Group theo tenant

Một tenant có 500.000 orders ở hai shards. Nếu mỗi shard trả revenue local 200.000 và 300.000, tổng đúng là bao nhiêu? Vì sao kết quả của shard A không đủ?

### Bài 7 — `$merge` đích sharded

Thiết kế materialized report có shard key `{tenantId:1,reportType:1}`. `on` fields và unique index phải được cân nhắc thế nào? Vì sao `on:["reportType"]` không đủ?

### Bài 8 — `$out`

Có thể chạy `$out` trực tiếp tới `tenantReports` đã sharded không? Nếu không, đề xuất cách thay thế để tạo report có version.

### Bài 9 — Đọc explain

Chạy hai pipeline ở mục 14.3 qua `mongos`. Ghi shards touched, COLLSCAN/IXSCAN, docs examined và merge stages **nếu có**. Không tự bịa metric nếu plan output không chứa field đó.

### Bài 10 — Transaction tồn kho

Trong cùng transaction: giảm inventory `t-01/A` một đơn vị, insert order `t-01/o-1001` và ghi requestLog. Nếu inventory và order nằm trên hai shards khác nhau thì ý nghĩa atomicity có thay đổi không?

### Bài 11 — Retry commit không rõ

Transaction đã commit nhưng client mất phản hồi. Client gửi lại request với **requestId mới** có an toàn không? Thiết kế reconciliation.

### Bài 12 — Hot shard

80% writes của cluster thuộc tenant lớn nhất và shard key `{tenantId:"hashed"}`. Vì sao thêm shards chưa chắc tăng throughput? Đề xuất shard-key design có phân tán trong tenant.

### Bài 13 — Balancer và transaction

Một chunk migration diễn ra trong khi transaction lớn đang đọc/ghi cùng vùng dữ liệu. Kể tên các nguồn contention/abort và thiết kế retry.

### Bài 14 — Báo cáo hằng ngày

Bạn cần báo cáo revenue theo tenant đến 00:00 UTC, dữ liệu 5 TB và có nhiều writes liên tục. Đề xuất cutoff, materialization, versioned cutover và cách kiểm tra accuracy; có cần một transaction trên toàn 5 TB không?

### Bài 15 — Backup

Vì sao snapshot data files từ Shard A lúc 10:00 và Shard B lúc 10:30 không mặc nhiên tạo backup toàn cluster nhất quán?

### Bài 16 — Đo hiệu năng

Lập bảng trước/sau khi shard collection:

| Metric | Trước | Sau | Diễn giải |
|---|---|---|---|
| API point lookup p95 | … | … | Có targeted không? |
| Aggregation global p95 | … | … | Merge/network tốn bao nhiêu? |
| Shards touched / query | … | … | Có scatter không? |
| Write QPS mỗi shard | … | … | Có hot shard không? |
| Disk bytes/chunks mỗi shard | … | … | Dung lượng có lệch không? |
| Transaction abort rate | … | … | Cross-shard contention? |
| Commit p99 | … | … | Điều phối có tăng độ trễ? |
| Balancer migration rate | … | … | Có ảnh hưởng giờ cao điểm? |

Chỉ điền số từ monitor/benchmark thật, không tự chọn số để “chứng minh sharding nhanh hơn”.

## 34. Gợi ý đáp án thực hành

**Bài 1:** A có full shard-key equality nên thường target một shard. B có tiền tố tenant, có thể một hoặc nhiều shards tùy phân phối chunks. C và D thiếu tiền tố shard key nên có thể scatter.

**Bài 2:** `t-01`: 3 PAID, 350; `t-02`: 3 PAID, 425; `t-03`: 3 PAID, 450. Shards có thể nhóm một phần rồi merger tính tổng toàn cụm.

**Bài 3:** `t-03/o-009` (300), `t-02/o-005` (200), `t-02/o-007` (175). Cần chọn global top 3 từ tất cả shards đủ điều kiện.

**Bài 4:** Page 5, size 20 đánh số từ 1 → `skip=(5-1)*20=80`. Global sort/skip/limit phải có thứ tự toàn cluster. Keyset dùng cursor theo bộ khóa sort đầy đủ.

**Bài 5:** So `tenantId` và `orderId` trong foreign pipeline. Chỉ orderId có thể trùng xuyên tenant và không đủ điều kiện route foreign collection đúng.

**Bài 6:** Tổng 500.000 theo cùng đơn vị đo. Revenue local chỉ là một phần, cần merger hoặc materialized summary toàn tenant.

**Bài 7:** `on` phải tương thích shard key và có unique index theo quy tắc của sharded output. Chỉ reportType không xác định tenant và không đủ shard-key identity.

**Bài 8:** `$out` không xuất trực tiếp vào sharded target tùy ý. Dùng `$merge` thỏa shard-key/unique-key constraints hoặc materialize report version mới ở collection hỗ trợ rồi atomic cutover.

**Bài 9:** Chỉ báo những field thực sự có trong explain. Query full shard key thường ít shards hơn query chỉ status; stage names phụ thuộc engine.

**Bài 10:** Một distributed transaction được hỗ trợ vẫn commit/abort atomically dù có nhiều shard participants; độ trễ/overhead/rủi ro abort cao hơn.

**Bài 11:** Không. Giữ requestId cũ, retry commit trong ngữ cảnh phù hợp hoặc reconcile ledger; không tạo intent mới.

**Bài 12:** Hash tenantId không phân tán những đơn của cùng một tenant ra nhiều key values. Cần shard key có độ phân tán **trong tenant** mà vẫn phù hợp query và uniqueness.

**Bài 13:** Migration có thể cạnh tranh metadata/lock và gây lỗi transient; transaction ngắn, shard-key-aware và retry có budget, không tăng timeout vô hạn.

**Bài 14:** Dùng cutoff và aggregation incremental/pre-aggregation, ghi summary theo reportVersion, kiểm tra rồi chuyển activeVersion atomically. Không cần mở transaction trên toàn 5 TB nếu semantic được thiết kế đúng.

**Bài 15:** Shards ở hai thời điểm có thể chứa nửa trước/nửa sau của distributed transaction và metadata placement có thể đổi. Cần backup solution nhất quán và sharding-aware.

**Bài 16:** Đánh giá cả routing, hot shard, merge/network, latency, transaction abort/commit và balancer; không chỉ đo tổng bytes hoặc throughput.

## 35. Câu hỏi ôn tập

**1. Vì sao sharding có thể khiến aggregation phức tạp hơn?**

Vì dữ liệu phân tán qua nhiều shards, các stage như group/sort/join có thể cần partial processing, network transfer và global merge.

**2. `mongos` có lưu toàn bộ dữ liệu collection không?**

Không. Nó là query router dùng metadata để định tuyến tới các shards; dữ liệu ứng dụng nằm ở shards.

**3. Filter có đủ shard key giúp gì?**

Giúp router target shard/range liên quan, thường giảm fan-out. Với full equality trên shard key có thể target một shard.

**4. Có tenantId trong shard key thì mọi query theo tenant chỉ chạm một shard?**

Không. Một tenant có thể được chia thành nhiều chunks ở nhiều shards tùy shard key và placement.

**5. Query chỉ có status có thể scatter-gather vì sao?**

Vì status không cung cấp thông tin shard-key routing; router có thể phải hỏi mọi shard để tìm document matching.

**6. `$group` trên từng shard có đủ cho tổng toàn cluster?**

Không khi một nhóm xuất hiện trên nhiều shards. Cần hợp nhất kết quả từ các shard.

**7. Global top N khác local top N thế nào?**

Global top N xét toàn bộ document matching trên mọi shard; local top N chỉ xét một shard. Optimizer có thể dùng local top-k như bước trung gian nhưng vẫn cần global merge.

**8. `$skip` sâu có tự trở thành rẻ hơn vì có nhiều shard?**

Không chắc. Phải xác định thứ tự toàn cục và bỏ prefix toàn cluster; offset lớn vẫn có thể tốn network/sort/merge.

**9. `$lookup` tới sharded collection có được hỗ trợ không?**

Có ở các phiên bản hiện đại như MongoDB 5.1 trở đi, nhưng hiệu năng/targeting phụ thuộc query shape, shard key/index và phiên bản.

**10. Hai collection có cùng shard key có tự nằm chung shard?**

Không. Chunk placement và balancer được quản lý riêng, nên join/transaction vẫn có thể cross-shard.

**11. `$merge` vào sharded output cần lưu ý gì?**

`on` fields và unique index phải thỏa quy tắc shard key và uniqueness; không dùng một key thiếu shard identity.

**12. `$out` có thay được một sharded output collection tùy ý?**

Không. Nó có các hạn chế trên sharded target; chọn `$merge` hoặc thiết kế materialization khác.

**13. Sharded transaction có atomicity không?**

Có, trên topology/phiên bản hỗ trợ. Cross-shard commit đắt hơn nhưng không mặc định partial commit là hợp lệ.

**14. Khi transaction commit timeout, có được retry bằng requestId mới?**

Không nên; transaction trước có thể đã commit. Cần retry commit/reconcile và dùng idempotency identity ổn định.

**15. Vì sao transaction trên nhiều shard dễ chậm?**

Có thêm routing, network, participant coordination, commit protocol và cơ hội lỗi/lock contention.

**16. `transactionLifetimeLimitSeconds` có tự tăng khi thêm shards không?**

Không. Transaction vẫn chịu lifetime/resource restrictions; thêm shards không biến nó thành workflow dài không giới hạn.

**17. Balancer có bảo đảm QPS chia đều không?**

Không. Cân bằng dữ liệu/chunks không đồng nghĩa cân bằng hot keys, CPU và write load.

**18. Hashed shard key có luôn giải quyết hot tenant không?**

Không, nếu chỉ hash tenantId thì cùng tenant luôn có cùng hash value và có thể vẫn tập trung tải.

**19. Read preference secondary có giảm số shards touched không?**

Không trực tiếp. Nó chọn replica set member cho read trong từng shard; shard-key routing vẫn quyết định bao nhiêu shard tham gia.

**20. Sao lưu sharded cluster cần chú ý gì?**

Phải nhất quán giữa dữ liệu shards, metadata placement và distributed transactions; không copy snapshots độc lập tùy thời điểm.

## 36. Checklist trước khi triển khai sharding cho hệ thống có analytics và transactions

- [ ] Đã phân tích access patterns chính: point lookup, range query, global aggregation, join và writes?
- [ ] Shard key candidate có cardinality, phân phối và locality phù hợp?
- [ ] Có tenant/hot key nào chiếm phần lớn QPS không?
- [ ] Query quan trọng có full shard key hoặc prefix đủ tốt để giảm shards touched?
- [ ] Đã đo targeted vs scatter-gather bằng `explain()` trên topology đại diện?
- [ ] Có index phù hợp **trên từng shard** cho filter/sort/join?
- [ ] `$group`/`$sort` có global merge và đủ memory/network capacity?
- [ ] Có tie-breaker duy nhất cho sort/pagination xuyên shards?
- [ ] `$lookup` tới foreign sharded collection có đủ tenant/shard key và kiểm soát fan-out?
- [ ] Không tạo một joined document vượt 16 MiB?
- [ ] `$facet` và các stage blocking có được kiểm soát memory/spill theo phiên bản?
- [ ] `$merge`/`$out` có phù hợp sharded output và unique index?
- [ ] Transactions có thật sự cần cross-shard atomicity?
- [ ] Business transaction chỉ chạm document/shard cần thiết, có deadline và retry budget?
- [ ] Đã pre-create collections/indexes, tránh DDL không hỗ trợ trong transaction?
- [ ] Có phân biệt `TransientTransactionError` với `UnknownTransactionCommitResult`?
- [ ] Có idempotency key/unique ledger cho các retry cấp API?
- [ ] Không gọi external payment/email trong transaction callback?
- [ ] Đã đánh giá chunk migration/balancer ảnh hưởng giờ cao điểm và transaction?
- [ ] Có kế hoạch zone placement, data residency và hot-shard mitigation nếu cần?
- [ ] Có runbook resharding/rollout/rollback và version/FCV compatibility?
- [ ] Backup/restore có sharding-aware consistency và được kiểm tra định kỳ?
- [ ] Đã đo p95/p99 latency, per-shard QPS/CPU/disk/cache, network merge và replication lag?
- [ ] Có khả năng tách analytics sang summary/ETL/warehouse nếu scatter-gather quá đắt?

## 37. Kết luận

**Sharding thay đổi vị trí và cách thực thi thao tác MongoDB, không thay đổi mục tiêu đúng đắn của truy vấn.** Một aggregation chỉ đúng khi các kết quả cục bộ được kết hợp thành kết quả toàn cluster theo ngữ nghĩa của pipeline; một global top N không thể được thay bằng top N của một shard; và một join tới foreign sharded collection vẫn cần khóa join đủ chính xác, index phù hợp và kiểm soát fan-out.

Với giao dịch, MongoDB hỗ trợ **distributed transactions** trên sharded cluster ở phiên bản tương thích, nên nhiều ghi ở nhiều shards vẫn có thể commit/abort nguyên tử. Đánh đổi là **latency điều phối, network, lock/cache pressure và nhiều tình huống retry/unknown commit**, khiến transaction ngắn, shard-key-aware, có idempotency trở thành thiết kế quan trọng.

Về vận hành, hãy nhìn đồng thời **chunk placement, hot shards, balancer, resharding, replication, index và backup nhất quán**. Thêm shard chỉ phát huy lợi ích khi workload được phân phối hiệu quả, truy vấn giảm scatter không cần thiết và các bước merge không trở thành điểm nghẽn mới. Kết quả tốt cần được chứng minh bằng **số shards touched, query plan, latency p95/p99, số liệu từng shard và tính đúng đắn nghiệp vụ** — không chỉ bằng số node của cluster.
