# Lập bảng đánh đổi giữa mô hình, tính nhất quán, hiệu năng và vận hành trong thiết kế ứng dụng MongoDB

Một thiết kế MongoDB không nên được đánh giá chỉ bằng câu hỏi “query này có nhanh không?”. Một document nhúng toàn bộ dữ liệu có thể đọc nhanh nhưng tăng kích thước, gây tranh chấp khi cập nhật và khó lưu lịch sử. Một mô hình tham chiếu dễ thay đổi độc lập nhưng cần nhiều lượt đọc hoặc aggregation `$lookup`. Một collection được sharding có thể phân tán dung lượng nhưng lại tạo cross-shard query và độ phức tạp vận hành. Một read preference giảm tải primary có thể phục vụ dữ liệu cũ hơn, không phù hợp với màn hình xác nhận giao dịch.

Do đó, khi **thiết kế ứng dụng MongoDB**, người kỹ sư cần lập một bảng đánh đổi để quyết định **mô hình dữ liệu**, **mức nhất quán/độ bền**, **hiệu năng đọc–ghi** và **chi phí vận hành** cùng lúc. Bảng không phải bảng xếp hạng công nghệ chung chung. Nó là **hồ sơ quyết định theo workload và bất biến nghiệp vụ cụ thể**, có giả định, dữ liệu đo, tiêu chí loại trừ, lựa chọn tạm thời, rủi ro còn lại và điều kiện xem xét lại.

Bài này hướng dẫn phương pháp từ việc thu thập yêu cầu, phân loại ràng buộc tới xây trade-off matrix, chấm điểm có trọng số, thiết kế thử nghiệm và viết Architecture Decision Record (ADR). Các ví dụ dùng hệ thống thương mại điện tử đa tenant với `orders`, `products`, `inventory`, `payments` và một bảng hoạt động gần thời gian thực. Nêu rõ đâu là giả định minh họa, đâu là thuộc tính MongoDB, để tránh áp một phương án cho mọi ứng dụng.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Xác định decision scope, workload và bất biến nghiệp vụ trước khi chọn schema.
2. Phân biệt tiêu chí **bắt buộc** với tiêu chí **có thể đánh đổi**.
3. Lập bảng truy cập dữ liệu (access-pattern matrix) theo query, filter, sort, payload và tần suất.
4. So sánh embedded documents, references, hybrid denormalization và materialized views.
5. Chọn aggregate boundary dựa trên tính nguyên tử một document và tốc độ thay đổi.
6. Phân tích consistency, durability, read/write concerns và read preference theo use case.
7. Đánh đổi indexes, query plans, write amplification, RAM/IO và thời gian tăng trưởng.
8. Đánh giá hiệu năng `$lookup`, aggregation, pagination, cache và hot documents.
9. Nhận diện giới hạn 16 MiB/document, mảng tăng không giới hạn và fan-out.
10. Đánh giá replica sets, transactions, sharding, shard key và multi-tenant isolation.
11. Ước tính storage, RAM, capacity headroom, backup và chi phí vận hành.
12. Dùng ma trận điểm có trọng số nhưng không dùng điểm để hợp thức hóa vi phạm invariant.
13. Thiết kế benchmark, load tests và kế hoạch đo p95/p99, keys examined, conflict rates.
14. Xây ADR có phương án thay thế, giả định, điều kiện đảo ngược và monitoring.
15. Áp dụng cách ra quyết định vào ba bài toán: checkout, catalog và activity feed.

## 2. Vì sao không có “schema MongoDB tốt nhất”?

MongoDB lưu dữ liệu dạng BSON document, cho phép mô hình linh hoạt và đưa dữ liệu thường đọc cùng nhau vào cùng một document. Nhưng “đưa mọi thứ vào một document” cũng có giới hạn:

- Mỗi BSON document có kích thước tối đa **16 MiB**.
- Một document chứa mảng tăng mãi dễ phải cập nhật liên tục, tạo hot spot và chi phí tăng trưởng.
- Những phần dữ liệu cần đổi độc lập hoặc chia sẻ bởi nhiều aggregates có thể phù hợp với references.
- Tham chiếu giữa collections không tự cung cấp foreign-key constraint theo kiểu RDBMS; ứng dụng cần thiết kế integrity.
- Giao dịch nhiều documents có thể được dùng khi MongoDB deployment hỗ trợ, nhưng tăng độ phức tạp, contention và chi phí so với một atomic document update.
- Sharding mở rộng dung lượng/throughput theo cách phân vùng, nhưng một query không target được shard có thể phải scatter-gather.

**Tối ưu theo một chiều có thể làm chiều khác xấu đi.** Tăng denormalization thường giảm số lần đọc nhưng tăng số bản sao phải cập nhật. Thêm index giúp query đọc nhưng làm tăng disk/cache consumption và write maintenance. Tăng consistency bằng cách đọc từ primary và dùng write concern mạnh hơn có thể thay đổi latency/availability profile.

## 3. Bốn trục quyết định chính

| Trục | Câu hỏi cần trả lời | Ví dụ tiêu chí |
|---|---|---|
| **Mô hình** | Documents, references và aggregates biểu diễn nghiệp vụ đúng không? | Boundaries, cardinality, lifecycle, update ownership |
| **Nhất quán** | Những kết quả nào phải thấy ngay, ghi nào không được mất? | Atomicity, stale-read budget, uniqueness, write concern |
| **Hiệu năng** | Workload đạt SLO ở tải thực tế và khi tăng trưởng không? | p95/p99, throughput, index use, read/write amplification |
| **Vận hành** | Có thể backup, theo dõi, migration, restore và chạy an toàn không? | Complexity, DR, costs, deployment, on-call, rollback |

Một thiết kế có thể đạt điểm cao ở hai trục và thấp ở hai trục còn lại. Mục tiêu là **đạt mọi điều kiện bắt buộc** và chọn phương án có tổng đánh đổi phù hợp nhất, chứ không tối đa hóa mọi trục một cách giả định.

### 3.1. Trục bổ sung: bảo mật và tuân thủ

Trong sản phẩm thực, security, tenant isolation, retention và compliance có thể là ràng buộc không thể đánh đổi. Ví dụ không được phép đọc dữ liệu tenant khác dù làm query nhanh hơn. Có thể đưa chúng vào “hard constraints” riêng, thay vì chấm điểm như tính năng tùy chọn.

### 3.2. “Đơn giản” cũng là một kết quả kỹ thuật

Một thiết kế dùng một collection, hai indexes và một atomic update có thể tốt hơn phương án năm collections, nhiều transactions và CDC nếu cả hai đáp ứng yêu cầu. Chi phí nhận thức, vận hành và độ khó sửa lỗi đều là một phần của quyết định.

## 4. Quy trình lập bảng đánh đổi

~~~mermaid
flowchart TD
    Scope["1. Xác định use case và ranh giới"] --> Invariants["2. Ghi hard invariants/SLO"]
    Invariants --> Workload["3. Thu thập access patterns và growth"]
    Workload --> Candidates["4. Tạo phương án khả thi"]
    Candidates --> Gate{"5. Có vi phạm hard constraints?"}
    Gate -->|"Có"| Reject["Loại hoặc chỉnh phương án"]
    Reject --> Candidates
    Gate -->|"Không"| Matrix["6. Lập ma trận định tính"]
    Matrix --> Score["7. Chấm điểm/độ tin cậy"]
    Score --> Measure["8. Prototype + benchmark"]
    Measure --> ADR["9. Quyết định + ADR + monitoring"]
    ADR --> Review["10. Xem lại khi workload thay đổi"]
~~~

Quy trình nên bắt đầu từ **access pattern và business invariant**, không bắt đầu từ một danh sách tính năng cơ sở dữ liệu rồi tìm bài toán để áp dụng.

### 4.1. Đầu ra cần có

Tối thiểu một cuộc đánh giá cần:

1. Problem statement cùng scope và out-of-scope.
2. Hard constraints và SLO/SLI.
3. Bảng access patterns và cardinalities.
4. Tối thiểu hai phương án khả thi.
5. Bảng đánh đổi có chứng cứ, không chỉ từ khóa “nhanh/chậm”.
6. Rủi ro, giải pháp giảm thiểu, kết quả thử nghiệm và ADR.

## 5. Phân biệt ràng buộc bắt buộc và ràng buộc có thể đánh đổi

Ví dụ một hệ thống thanh toán:

| Yêu cầu | Loại | Cách chứng minh |
|---|---|---|
| Không trừ tiền hai lần với cùng request ID | Bắt buộc | Unique ledger + integration/idempotency tests |
| Số dư không âm khi rút | Bắt buộc | Atomic conditional update + concurrent tests |
| Không lộ orders của tenant khác | Bắt buộc | Security scope + permission tests |
| API checkout p95 dưới 250 ms | SLO, có ngưỡng | Load test workload representative |
| Trang catalog mở trong 100 ms | Mục tiêu hiệu năng | p95/p99 API + query stats |
| Chi phí thấp hơn 20% | Mục tiêu có thể đánh đổi | Capacity/cost estimation |
| Dễ rollback migration | Mục tiêu vận hành | Rollback rehearsal và compatibility test |

Không cộng điểm để bù cho việc vi phạm “không double charge”. Nếu một phương án có xác suất sai nghiệp vụ không chấp nhận được, nó **không phải ứng viên hợp lệ** cho business flow đó.

### 5.1. Giá trị ước lượng phải được đánh dấu

Con số 250 ms, 20% và kích thước dữ liệu trong bài chỉ là **assumptions để học phương pháp**. Với dự án thật cần lấy từ product SLO, dữ liệu production, load forecast và risk policy.

### 5.2. Không dùng “eventual consistency” làm giấy phép phá invariant

Một catalog price display có thể chấp nhận stale trong vài giây. Nhưng checkout phải chốt giá/thanh toán theo business policy và ghi một kết quả authoritative. Phân biệt **dữ liệu hiển thị có thể trễ** với **quyết định tài chính phải nguyên tử/đối soát được**.

## 6. Bài toán mẫu: cửa hàng đa tenant

Giả sử hệ thống có các collections:

~~~text
products       thông tin catalog, tên, ảnh, giá hiển thị
inventory      số lượng có thể bán và giữ chỗ theo SKU/warehouse
orders         đơn hàng, dòng sản phẩm, lịch sử trạng thái
payments       các giao dịch và ledger cho idempotency/audit
customers      hồ sơ khách hàng
activityEvents sự kiện hoạt động lớn, append-only
~~~

Tải giả định:

- 2 triệu products, 30 triệu orders, 300 triệu activity events.
- 90% catalog requests là đọc, phần lớn filter theo tenant/category, sort theo mức độ phổ biến hoặc thời điểm.
- Checkout tăng mạnh theo campaign, nhiều khách tranh một SKU.
- Một order thường có 1–20 dòng hàng, một số B2B orders có hàng trăm dòng.
- Mỗi user cần xem 20 orders gần nhất hoặc “Load more”.
- Audit dữ liệu tài chính giữ nhiều năm và có yêu cầu đối soát.

Những con số minh họa để thiết kế workload; không phải dự báo hiệu năng thực tế của MongoDB.

## 7. Lập access-pattern matrix

| ID | Thao tác | Filter/sort | Dữ liệu cần | Tần suất/độ sâu | Độ nhất quán |
|---|---|---|---|---|---|
| Q1 | Tìm catalog | tenant/category, sort popular | summary product | Rất cao, trang nông | Stale ngắn có thể chấp nhận |
| Q2 | Xem product detail | tenant + productId | thông tin + media metadata | Cao | Giá hiển thị cần policy |
| Q3 | Checkout | tenant + SKU, qty | available, price snapshot | Burst write | Không oversell theo policy |
| Q4 | Xem đơn hàng | tenant + orderId | items, totals, status | Trung bình | Đã xác nhận phải đọc lại được |
| Q5 | Danh sách orders | tenant/customer/status, createdAt desc | summary | Cao, có phân trang | Feed consistency định nghĩa |
| Q6 | Ghi payment | tenant + requestId | ledger + outcome | Write critical | Idempotent và audit |
| Q7 | Report doanh thu | tenant + date/status | aggregate sums | Theo lịch | Snapshot/cutoff policy |
| Q8 | Activity feed | tenant + actor, eventTime desc | vài fields | Rất lớn, deep scroll | Cho phép eventual |

### 7.1. Không thiết kế từ collections trước khi biết query

Một collection với schema “đẹp” nhưng không đáp ứng Q1–Q8 có thể tốn network và $lookup. MongoDB schema design thường gắn chặt với các **truy vấn quan trọng và cách dữ liệu được cập nhật**.

### 7.2. Viết query shape cụ thể

“Tìm orders nhanh” quá chung. Hãy ghi:

~~~javascript
db.orders.find(
  { tenantId: "t-01", customerId: "C-9", status: "PAID" },
  { orderNo: 1, totalMinor: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20)
~~~

Từ shape này mới đánh giá compound index, payload, sort stability, deep pagination và tenant routing.

## 8. Cardinality, growth và ownership

Cho mỗi quan hệ:

| Quan hệ | Cardinality | Số lượng có giới hạn? | Thay đổi bởi ai? |
|---|---|---|---|
| Order → line items | 1:N nhỏ/trung bình | Thường có giới hạn business | Checkout service |
| Product → comments | 1:N lớn, tăng mãi | Không | Nhiều users |
| Customer → orders | 1:N lớn | Không | Checkout service |
| Order → shipping address snapshot | 1:1 tại thời điểm đặt | Có | Order aggregate |
| Product → category | N:1 | Có thể shared | Catalog admin |
| Tenant → activity events | 1:N rất lớn | Không | Nhiều services |

### 8.1. Không chỉ đo số lượng trung bình

Nếu 99% orders có 5 lines nhưng 1% B2B orders có 50.000 lines, “array không lớn” là giả định nguy hiểm. Phải đo p50/p95/p99 kích thước và xác định trường hợp cực trị.

### 8.2. Ownership thay đổi

Nếu một child luôn được tạo/sửa/xóa cùng parent, embedding có thể hợp lý. Nếu nhiều services cập nhật child độc lập hoặc child được tham chiếu bởi nhiều parents, reference/hybrid thường dễ quản lý hơn.

## 9. Ba ứng viên mô hình hóa cơ bản

**Phương án A — embedding:** nhúng children/snapshot vào parent, thường đọc một document đủ.

**Phương án B — references:** lưu child collection riêng với parentId/productId, application query hoặc aggregation join.

**Phương án C — hybrid:** lưu snapshot các fields cần thiết trong parent nhưng giữ reference tới entity nguồn cho các thao tác độc lập.

~~~mermaid
flowchart LR
    A["A: Order { items: [...] }"] --> ARead["Đọc một document"]
    B["B: orders + orderItems"] --> BRead["Query children hoặc lookup"]
    C["C: Order có item snapshots + productId"] --> CRead["Read snapshot, cập nhật catalog riêng"]
~~~

Không chấm điểm trước khi xác định các hard constraints như size, integrity và read-after-write.

## 10. Bảng đánh đổi embedding và references

| Tiêu chí | Embedding | References | Hybrid |
|---|---|---|---|
| Đọc parent + children | Thường một document | Cần nhiều queries/$lookup | Đọc snapshot nhanh |
| Ghi parent + embedded fields | Atomic trong một document | Có thể nhiều writes/transaction | Cần phân định source của từng field |
| Child update độc lập | Có thể tăng contention | Tự nhiên | Một phần phải sync |
| Child tăng không giới hạn | Rủi ro 16 MiB/hot array | Phù hợp hơn | Chỉ embed subset có giới hạn |
| Shared child giữa parents | Lặp dữ liệu | Reference reuse | Reference + selected snapshot |
| Dữ liệu lịch sử bất biến | Snapshot phù hợp | Phải quản lý version/history | Thường phù hợp |
| Truy vấn children độc lập | Có thể khó hoặc index phức tạp | Dễ hơn theo child index | Theo nhu cầu |
| Consistency giữa bản sao | Không có bản sao nếu chỉ embed | Reference tới authority | Có nguy cơ snapshot stale |
| Chi phí reads | Ít round trips, BSON có thể lớn | Tăng round trips/$lookup | Cân bằng |
| Chi phí writes | Document growth, multikey index | Nhiều collections/indexes | Write amplification |
| Vận hành/migration | Parent schema lớn | Referential cleanup | Reconciliation bản sao |

### 10.1. Bảng không có cột “tốt nhất”

Nếu child có lifetime phụ thuộc parent, đọc cùng parent và có kích thước có giới hạn, embedding thường nổi bật. Nếu child là history/event tăng mãi, reference thường phù hợp hơn. Hybrid đặc biệt hữu ích khi **snapshot lịch sử** khác với **trạng thái nguồn hiện tại**.

### 10.2. Dữ liệu lặp có thể là chủ ý

Một order nên giữ `productNameAtPurchase` và `unitPriceAtPurchase` để hóa đơn lịch sử không đổi khi catalog được chỉnh sửa. Đây không nhất thiết là “data duplication bug”; nó là một snapshot có semantics khác giá hiện tại.

## 11. Ví dụ schema embedded order

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  customerId: "C-9",
  createdAt: ISODate("2026-11-01T10:00:00Z"),
  status: "PAID",
  totalMinor: NumberLong(245000),
  items: [
    {
      productId: "SKU-A",
      nameAtPurchase: "Bình giữ nhiệt",
      unitPriceMinor: NumberLong(125000),
      quantity: 1
    },
    {
      productId: "SKU-B",
      nameAtPurchase: "Ống hút thép",
      unitPriceMinor: NumberLong(60000),
      quantity: 2
    }
  ],
  shippingAddressSnapshot: {
    country: "VN", city: "Ho Chi Minh City"
  }
}
~~~

Các item snapshots được dùng trong lịch sử đơn. Product catalog vẫn có collection riêng; việc chỉnh tên/giá catalog **không phải** sửa nội dung hóa đơn đã chốt.

### 11.1. Atomic boundary

Một update đối với các fields của **cùng order document** là atomic. Nếu checkout còn trừ stock trong `inventory` và ghi `payment ledger` ở documents khác, tính nguyên tử của order document không tự bao trùm chúng.

### 11.2. Giới hạn document

BSON document tối đa 16 MiB. Không nhúng vô hạn auditEvents, comments, click stream hay attachments lớn. Đặt upper bound cho `items`/notes và theo dõi p95/p99 document size.

### 11.3. Hot aggregate

Nếu nhiều workers liên tục cập nhật cùng order để append trạng thái và metrics, document có thể trở thành contention point. Có thể tách append-only events, giữ summary/index của trạng thái hiện tại trong order.

## 12. Ví dụ schema referenced và hybrid

Referenced:

~~~javascript
// orders
{ _id: "O-1001", tenantId: "t-01", totalMinor: NumberLong(245000) }

// orderItems
{ _id: "OI-1", tenantId: "t-01", orderId: "O-1001", productId: "SKU-A",
  unitPriceMinor: NumberLong(125000), quantity: 1 }
~~~

Hybrid:

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  totalMinor: NumberLong(245000),
  itemSummaries: [
    { productId: "SKU-A", nameAtPurchase: "Bình giữ nhiệt",
      quantity: 1, unitPriceMinor: NumberLong(125000) }
  ]
}
~~~

### 12.1. Reference integrity

MongoDB không mặc định enforce foreign key từ `orderItems.orderId` tới `orders._id`. Application/transaction/reconciliation phải kiểm tra orphaned children, tenant ownership, delete policy và dữ liệu chuyển đổi.

### 12.2. Hybrid cần ownership rõ

`product.name` là authority của tên hiện tại, nhưng `order.itemSummaries.nameAtPurchase` là snapshot lịch sử. Nếu hai fields được dùng với semantics khác nhau, không cần “sync về một giá trị”; ngược lại nếu chỉ là cache của cùng business value, phải có invalidation/update consistency policy.

## 13. Mảng tăng không giới hạn

Anti-pattern:

~~~javascript
{
  _id: "P-1",
  productName: "Sản phẩm A",
  allComments: [
    /* 5 triệu comments tiếp tục tăng */
  ]
}
~~~

Vấn đề:

- Chạm giới hạn 16 MiB.
- Document growth và update contention.
- Đọc product metadata có thể vô tình tải quá nhiều comments.
- Multikey indexes và array updates có chi phí.
- Khó phân trang comments theo thời gian/author.

Mô hình tốt hơn:

~~~javascript
// products
{ _id: "P-1", name: "Sản phẩm A", commentCount: 5000000 }

// comments
{ _id: ObjectId(), productId: "P-1", authorId: "C-3",
  createdAt: new Date(), body: "Hữu ích" }
~~~

Index comments theo `productId + createdAt + _id` cho phân trang, giữ `commentCount` là derived value với update/reconciliation policy rõ.

## 14. Atomic document update và consistency

Nếu invariant nằm gọn trong một document, ưu tiên đưa điều kiện vào **cùng atomic write**:

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "SKU-A",
    tenantId: "t-01",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1, reserved: 1 }
  }
);
~~~

Nếu 2 requests tranh sản phẩm cuối, tối đa một thao tác có thể match khi `available=1`. Cần kiểm tra `matchedCount` và acknowledgement; không đọc `available` ở client rồi trừ trong lệnh không có điều kiện.

### 14.1. Đây chưa phải toàn bộ checkout

Nếu reservation còn cần tạo order và ledger khác collection, **nhiều documents** phải nhất quán theo business rule. Có thể dùng transaction trên topology MongoDB hỗ trợ hoặc mô hình/protocol reservation có reconciliation, chứ không kỳ vọng atomic inventory update bao trùm tất cả.

### 14.2. Atomicity khác idempotency

Hai requests khác nhau tranh stock cần atomic conditional update. Một request **gửi lại** sau timeout cần stable request ID/unique ledger để không trừ hai lần. Hai vấn đề khác nhau và có thể xảy ra cùng lúc.

## 15. Mô hình hóa business invariants

Ví dụ:

~~~text
INV-1: inventory.available >= 0
INV-2: một (tenantId, requestId) tạo tối đa một payment outcome
INV-3: orders.PAID phải đối soát được payment ledger tương ứng
INV-4: một seatId của một event có tối đa một ACTIVE booking
INV-5: tenantId của mọi dependent record phải khớp parent
INV-6: order snapshot không bị sửa theo catalog hiện tại
~~~

### 15.1. Bản đồ invariant → cơ chế

| Invariant | Ranh giới | Cơ chế ứng viên |
|---|---|---|
| Không âm stock | Một inventory document | Atomic conditional update |
| Không double request | Namespace business key | Unique index + idempotency ledger |
| Order + ledger cùng commit | Nhiều documents | Transaction hoặc protocol/resolution |
| Unique active seat | Nhiều booking documents | Unique/partial unique index theo semantics |
| Order snapshot lịch sử | Order document | Immutable snapshot fields |
| Tenant isolation | Mọi query/write | Auth-scoped filter, indexes, permissions |

### 15.2. Đừng chấm điểm thay invariant

Nếu một phương án “eventual sync order/payment” khiến người dùng có thể được báo PAID không có ledger trong trạng thái được phép là vĩnh viễn, phương án chưa đạt correctness. Hãy sửa protocol hoặc loại ứng viên trước bảng điểm.

## 16. Đánh đổi tính nhất quán theo tác vụ

| Tác vụ | Stale data chấp nhận? | Ghi phải bảo vệ điều gì? | Hướng thiết kế |
|---|---|---|---|
| Catalog browse | Có thể vài giây theo policy | Product updates/version | Cached/materialized read model |
| View own checkout | Thường không sau success | Order/payment kết quả authoritative | Primary/session consistency phù hợp |
| Product stock display | Có thể chấp nhận sai lệch UI | Không oversell tại lúc reserve | Conditional write trên authority |
| Payment ledger | Không được nhân đôi effect | Idempotency + durable commit | Unique request ID, reconcile |
| Activity feed | Có thể eventual | Không mất required events | Append-only + checkpoint |
| Financial report | Theo cutoff/snapshot rõ | Tổng tiền đúng tại boundary | Snapshot/aggregation/export policy |

### 16.1. Stale read không luôn gây oversell

UI có thể hiển thị stock=1 từ cache trong khi stock thật đã 0. Nếu quyết định reserve dựa trên atomic predicate của write authority, yêu cầu thứ hai bị từ chối. Điều cần tránh là để UI cache làm quyết định cuối cùng.

### 16.2. “Consistency mạnh” cần mô tả cụ thể

Không dùng các nhãn “strong”/“eventual” đơn lẻ. Hãy nói **read-your-writes**, **monotonic reads**, **majority-acknowledged writes**, **atomic multi-document commit**, **snapshot tại mốc T**, hoặc **staleness tối đa N giây** theo use case.

## 17. Read concern, write concern và read preference

MongoDB có các cơ chế cấu hình riêng:

| Cấu hình | Câu hỏi | Đánh đổi |
|---|---|---|
| Write concern `w:1` | Primary thừa nhận write? | Latency thường thấp hơn, độ bền qua failover cần hiểu |
| Write concern `majority` | Đủ majority members thừa nhận theo policy? | Có thể tăng latency/độ phụ thuộc replicas |
| Read concern `local` | Đọc data mà node đang có | Có thể thấy dữ liệu chưa majority committed |
| Read concern `majority` | Đọc dữ liệu majority-committed theo semantics | Không tạo snapshot xuyên nhiều HTTP requests |
| Read concern `snapshot` | Snapshot semantics trong ngữ cảnh được hỗ trợ | Thêm yêu cầu tài nguyên/topology |
| Read preference `primary` | Ưu tiên đường đọc authoritative | Primary read load |
| Read preference `secondaryPreferred` | Phân tải một số reads | Có thể stale/lag/failover behavior |

### 17.1. Không đánh đồng durability với freshness

Một write majority-acknowledged nói về acknowledgement/durability theo replication semantics; không bảo đảm một secondary bất kỳ lập tức trả giá trị mới. Read preference và session causal consistency/read concern vẫn cần xét.

### 17.2. Không hứa linearizable toàn hệ thống

Read concern majority không tương đương linearizability cho mọi thao tác nhiều documents. Nếu business yêu cầu một property rất mạnh, phải chỉ rõ linearization/transaction/snapshot scope và kiểm thử theo deployment.

### 17.3. Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    Q["Read request"] --> CR{"Yêu cầu nhìn ngay kết quả write của chính user?"}
    CR -->|"Có"| Primary["Primary/session semantics phù hợp"]
    CR -->|"Không"| Stale{"Cho phép dữ liệu trễ?"}
    Stale -->|"Có"| Secondary["Secondary/cache/materialized view có lag budget"]
    Stale -->|"Không"| Primary
    Primary --> Verify["Kiểm chứng concern/SLO thực tế"]
    Secondary --> Verify
~~~

## 18. Optimistic locking và write contention

Hai editors cùng sửa order từ revision 4:

~~~javascript
db.orders.updateOne(
  { _id: "O-1001", tenantId: "t-01", revision: NumberLong(4) },
  {
    $set: { status: "APPROVED" },
    $inc: { revision: NumberLong(1) }
  }
);
~~~

Một writer thắng thì revision tăng; writer sau dùng revision cũ sẽ không match. Đây là **compare-and-swap**. Spring Data MongoDB hỗ trợ optimistic locking theo `@Version` đối với những version-aware operations, nhưng raw driver/bulk scripts phải tuân thủ cùng protocol nếu muốn tránh stale overwrite.

### 18.1. Chi phí tính nhất quán

CAS giảm silent lost updates nhưng tăng conflict handling/retry khi nhiều writers cùng một document. Không biến conflict thành retry vô hạn; đôi khi cần báo HTTP conflict để người dùng reload/merge.

### 18.2. Ưu tiên atomic predicate khi business condition đơn giản

Nếu chỉ cần trừ stock đủ số lượng, một `updateOne` có điều kiện thường đơn giản hơn read–modify–write với CAS loop ở application. Nếu phải chỉnh một form dựa trên snapshot nhiều fields, version CAS thích hợp hơn.

## 19. Transactions nhiều documents: đánh đổi

Khi một checkout phải cùng:

1. Trừ stock.
2. Tạo order.
3. Tạo reservation ledger.

Một transaction trên deployment hỗ trợ có thể đặt writes trong cùng atomic commit. Đánh đổi:

| Điểm mạnh | Đổi lại |
|---|---|
| Atomic commit/abort các writes được bao trong transaction | Transaction lifetime/resource limits |
| Có thể đọc snapshot trong phạm vi transaction | Retry/abort/write conflict logic phức tạp |
| Giữ nhất quán đa document trong MongoDB | Contention và latency khi ghi nhiều records |
| Dễ lý luận all-or-nothing | Không rollback external payment gateway/Kafka/email |

### 19.1. Snapshot isolation không thay mọi business guard

Một invariant đếm trên nhiều documents có thể gặp **write skew** nếu các transactions đọc cùng snapshot rồi ghi các documents khác nhau mà không có guard chung. Đặt invariant vào document/unique index/guard bị mọi writers tranh chấp, hoặc protocol serialization phù hợp.

### 19.2. Callback và retry

Driver transaction helpers có thể retry transaction body/commit theo error labels như `TransientTransactionError` hay `UnknownTransactionCommitResult`. Callback không nên gọi external side effects không idempotent vì có thể chạy lại; dùng outbox, stable IDs và reconciliation.

### 19.3. Khi nào không cần transaction?

Một atomic update document đủ bảo vệ invariant mà không liên quan documents khác. Không dùng transaction cho mọi CRUD như một mặc định để “an toàn” nếu nó tăng latency/contension mà không thêm correctness.

## 20. Bảng quyết định consistency

| Phương án | Atomic phạm vi | Read freshness | Độ phức tạp | Thích hợp |
|---|---|---|---|---|
| Một document + conditional update | Một document | Theo read strategy | Thấp | Stock/counter/aggregate gọn |
| Versioned CAS | Một document | Phát hiện stale writes | Vừa | Người dùng chỉnh entity |
| Multi-document transaction | Nhiều documents trong deployment | Snapshot theo semantics | Cao hơn | Order + ledger cùng commit |
| Async denormalized projection | Mỗi target write riêng | Eventual | Vừa–cao | Search/catalog/report read |
| Outbox/inbox + dedupe | Across async processes theo protocol | Eventual có audit | Cao hơn | Cross-service events/external effects |

Các cơ chế thường **kết hợp**, không loại trừ nhau: ví dụ transaction chứa conditional stock update và idempotency ledger, sau đó outbox phát sự kiện cho cache.

## 21. Index là một đánh đổi đọc–ghi–lưu trữ

Index hỗ trợ truy vấn, sort và covered query trong điều kiện phù hợp. Đổi lại, mỗi index tiêu thụ dung lượng/cache, tạo thêm việc khi insert/update/delete và tăng chi phí bảo trì, backup, migration.

| Thiết kế index | Lợi ích | Đổi lại |
|---|---|---|
| Không có index phù hợp | Ít storage/index maintenance | `COLLSCAN` hoặc sort rộng |
| Compound index theo query shape | Đọc/sort hiệu quả hơn | Chỉ tối ưu một số patterns |
| Nhiều indexes đa mục đích | Hỗ trợ nhiều filters | Write amplification, cache pressure |
| Partial index | Index subset có ích | Query phải tương thích partial filter |
| Multikey index | Truy vấn nested arrays | Nhiều index entries và constraints |
| Unique index | Bảo vệ business identity | Có thể trả duplicate-key error |
| TTL index | Tự xóa theo expiration policy | Không tức thời, không thay archival |

### 21.1. Compound index theo access pattern

Với Q5: tenant, customer, status, sort newest:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_customer_status_created" }
);
~~~

Equality prefix rồi sort fields là ứng viên hợp lý cho query này, **không phải** index tốt cho mọi filter khác. Khi query không có `customerId` hoặc `status`, index có thể không phục vụ sort như kỳ vọng; đo `explain`.

### 21.2. Index không tự là bảo mật

Index có `tenantId` giúp targeting/filter, nhưng không thay việc service lấy tenant từ authentication context. Unique index trên `(tenantId,requestId)` có thể là hard correctness constraint cho idempotency ledger.

### 21.3. Index nào không đáng giữ?

Index ít được dùng nhưng làm tăng insert latency/IO/storage phải được đánh giá lại. Xem statistics và kế hoạch rollout/rollback khi drop; không xóa chỉ từ một lần quan sát thấp traffic.

## 22. Dùng `explain("executionStats")` để đo sự thật

~~~javascript
db.orders.find(
  {
    tenantId: "t-01",
    customerId: "C-9",
    status: "PAID"
  },
  {
    orderNo: 1,
    totalMinor: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Đọc:

- `nReturned`: số records được trả.
- `totalKeysExamined`: lượng index entries phải duyệt.
- `totalDocsExamined`: lượng documents phải đọc.
- `winningPlan`: `IXSCAN`, `COLLSCAN`, `SORT`, `FETCH` và các stages theo engine/version.
- Execution metrics: công việc/phần thời gian phía server.

### 22.1. Đừng chỉ benchmark trang đầu

Một query nhanh với 100 documents có thể chậm khi dataset 30 triệu orders, tenant lệch, cache cold và clients concurrent. Cần representative cardinality/selectivity, p95/p99 và peak load.

### 22.2. Covered projection

Khi filter/sort/projection phù hợp index, MongoDB có thể tránh FETCH nhiều documents; thêm một field không nằm trong index hoặc field lớn vào DTO có thể thay đổi hiệu năng.

### 22.3. Explain không bao trùm HTTP

Request duration còn gồm connection pool wait, network, mapping BSON, JSON serialization và upstream. Kết hợp application tracing với MongoDB metrics/slow logs trong quyền cho phép.

## 23. Pagination: offset hay keyset?

Danh sách orders newest-first:

~~~javascript
db.orders.find({ tenantId: "t-01" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000).limit(20);
~~~

Offset cho phép nhảy trực tiếp trang số N, nhưng deep `skip` thường phải duyệt nhiều entries. Keyset tiếp tục sau cặp sort keys cuối:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-01T10:00:00Z") } },
    {
      createdAt: ISODate("2026-11-01T10:00:00Z"),
      _id: { $lt: ObjectId("64b000000000000000000123") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Ví dụ dùng BSON ObjectId cho `_id`, sort giảm dần, cần index tương ứng và token validation.

| Tiêu chí | Offset | Keyset/seek |
|---|---|---|
| Nhảy tới trang N | Dễ | Khó nếu thiếu bookmark |
| Trang sâu | Chi phí có thể tăng | Có thể seek theo index |
| Inserts/deletes trước boundary | Dễ duplicate/missing | Ít dịch vị trí |
| API | Page number/size | Last sort keys/token |
| Tổng số trang | Count được nếu cần | Không trực tiếp |
| Dynamic sort | Đơn giản hơn | Cần comparator/token riêng |

### 23.1. Thứ tự phải xác định

`createdAt` có thể trùng, nên thêm `_id` unique làm tie-breaker. Keyset vẫn không tự tạo snapshot khi sort fields thay đổi giữa requests.

### 23.2. Chọn theo UI

Trang quản trị 300 records nhảy trang 7 có thể dùng offset. Activity feed 300 triệu events chỉ có “Load more” thường phù hợp keyset.

## 24. `$lookup` và aggregation: tránh định kiến

Mô hình references có thể phải join:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "orderItems",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]);
~~~

### 24.1. Join không mặc định chậm

Hiệu năng phụ thuộc source set, foreign index, cardinality, documents size, server version, sharding và resource budgets. `orderItems.orderId` có index và chỉ join 20 parents có thể đáp ứng SLO; không có index/fan-out lớn có thể rất tốn.

### 24.2. Đặt `$limit` đúng semantics

Nếu chỉ cần 20 orders mới nhất theo fields trong orders, giảm parent set trước lookup là hợp lý. Nếu filter/sort dựa vào joined fields, không tự dời `$limit` trước join vì sẽ thay đổi kết quả.

### 24.3. Mô hình sai không được “cứu” bằng pipeline dài

Nếu mỗi API phải làm nhiều `$lookup`/`$unwind` và tốn network, cân nhắc bounded embedding hoặc materialized read model — đồng thời tính chi phí đồng bộ các bản sao.

## 25. Materialized views và denormalization

~~~text
Orders / events authoritative
    → CDC/outbox/batch
        → productStats read collection
            → dashboard API
~~~

Một bản tổng hợp:

~~~javascript
{
  _id: "t-01:SKU-A",
  tenantId: "t-01",
  productId: "SKU-A",
  paidOrderCount: NumberLong(184200),
  refreshedAt: ISODate("2026-11-14T02:00:00Z")
}
~~~

### 25.1. Lợi ích

Tính sẵn thông tin để đọc nhanh, giảm aggregation lặp lại. Phù hợp dashboard, product popularity, search ranking hoặc read-heavy APIs.

### 25.2. Đánh đổi

Phải vận hành pipeline, checkpoint/replay, reconcile drift, handling deletes và lag SLA. Nếu view phục vụ analytics, stale ngắn có thể chấp nhận; không dùng số liệu derived bất đồng bộ làm payment ledger authoritative.

### 25.3. Write amplification

Một order update có thể cập nhật customerSummary, productStats, search index và notifications. Đánh giá tổng số downstream writes và failure recovery, không chỉ tốc độ đọc cuối.

## 26. Cache: giảm reads, tăng bề mặt consistency

| Cache | Lợi ích | Rủi ro |
|---|---|---|
| Product detail | Giảm hot reads | Giá/tên stale |
| Search results | Giảm aggregation | Invalidation khi filter đổi |
| User order summary | Giảm repeated queries | Read-your-writes có thể sai |
| Payment response | Retry response nhanh | Không thay durable ledger |

### 26.1. TTL theo business contract

Product description có thể stale một thời gian; stock hiển thị có thể trễ ngắn nếu checkout vẫn dùng atomic predicate. Không dùng cache làm quyết định cuối cùng của inventory/payment.

### 26.2. Cache invalidation là chi phí thật

Write MongoDB thành công nhưng Redis chưa invalidated có thể làm UI thấy bản cũ. Dùng event-based invalidation, versioned keys hoặc short TTL theo SLO; đo stale-read violations.

### 26.3. Tránh cache stampede

Hàng nghìn requests cùng gặp key hết hạn có thể dồn tải vào MongoDB. Dùng request coalescing, TTL jitter, bounded retries và circuit breaker.

## 27. Sharding: mở rộng hay thêm độ phức tạp?

Replica set chủ yếu là high availability/replication; **sharding** phân vùng dữ liệu và workload qua shards. Hai cơ chế không đồng nghĩa.

| Lợi ích sharding | Chi phí tương ứng |
|---|---|
| Chia dung lượng/throughput | Chọn shard key và theo dõi skew |
| Target query đến ít shards | Query thiếu key có thể scatter-gather |
| Phân tán writes | Hot shard nếu key phân phối xấu |
| Mở rộng theo số shards | Balancer/chunk migration/resharding operations |
| Dữ liệu lớn hơn giới hạn một node | Cross-shard aggregation/transaction cost |

### 27.1. Shard key phải theo access patterns

Nếu query chủ yếu có `tenantId`, shard key hỗ trợ targeting tenant có thể hữu ích. Nhưng một mega-tenant chiếm phần lớn writes có thể vẫn nóng nếu cùng một key value chỉ nhắm một phần cluster.

### 27.2. Ranged vs hashed

Ranged có lợi cho locality theo range nhưng dễ nóng ở cuối range với monotonic writes. Hashed có thể phân tán key values, nhưng thay đổi range query behavior. Kiểm tra query shapes, cardinality, shard distribution và hot-key risk.

### 27.3. Sharding không tự sửa deep offset

Deep `skip` qua mongos có thể còn work ở nhiều shards trước khi merge. Index, targeting và keyset vẫn cần được xem xét.

## 28. Bảng đánh giá shard key

| Tiêu chí | Câu hỏi |
|---|---|
| Cardinality | Có đủ unique values? |
| Skew | Có mega-tenants/hot keys? |
| Query targeting | Các API quan trọng có key predicate? |
| Time growth | Inserts có dồn một đầu range? |
| Mutable key | Business có thay đổi key thường xuyên? |
| Unique indexes | Constraints có tương thích sharding? |
| Joins/aggregations | Scatter-gather có thường xuyên? |
| Resharding | Có kế hoạch/chi phí nếu workload đổi? |

Ví dụ: shard chỉ theo tenant có thể dễ hiểu cho thousands small tenants, nhưng khi một tenant chiếm 70% traffic, cần đánh giá partitioning theo tenant+bucket hoặc zoning/tier khác. Không tự thêm random bucket mà quên thay đổi query routing và global tenant invariant.

## 29. Multi-tenant và noisy-neighbor

| Cách tổ chức | Điểm mạnh | Chi phí |
|---|---|---|
| Shared collection + tenantId | Ít namespaces, vận hành tập trung | Tenant scope bắt buộc mọi query |
| Collection per tenant | Dễ tách thao tác mức namespace | Nhiều indexes/migrations |
| Database per tenant | Phân tách quản lý/roles ở mức DB | Backup, lifecycle phức tạp |
| Cluster per tenant/tier | Isolation mạnh hơn ở capacity | Chi phí/provisioning cao |

### 29.1. Tenant scope là hard constraint

`tenantId` phải lấy từ authentication context. Không chỉ filter tenant trong application sau khi đã đọc collection rộng; việc đó lãng phí và có nguy cơ rò dữ liệu.

### 29.2. Noisy neighbor

Một tenant lớn có thể chiếm index cache, CPU hoặc pool connections, làm p99 của tenants khác xấu. Rate limits/quotas/dedicated tier là phần của bảng đánh đổi.

## 30. Hot documents và contention

Một `inventory:SKU-HOT` có thể nhận hàng nghìn updates đồng thời. Single-document atomicity bảo vệ invariant nhưng không làm contention biến mất.

- Atomic conditional stock update đúng về nghiệp vụ nhưng p99 có thể cao khi tranh cùng key.
- CAS cần xử lý optimistic conflicts, retry budgets và backoff.
- Một sharded counter có thể tăng throughput nhưng **không tự giữ global strict limit**.
- Queue/serialized reservation có thể giảm contention nếu SLA cho phép.
- Nếu invariant toàn cục phải giữ, thiết kế guard chung hoặc transactional protocol tương ứng.

### 30.1. Chọn correctness trước throughput

Không chia quota 100 thành 10 counters không có reconciliation/guard rồi tuyên bố chắc chắn không bán quá 100. Bất biến phải được chứng minh dưới concurrency.

### 30.2. Đo tail latency

Average 20 ms nhưng p99 2 s có thể không đạt checkout SLO. Thu metrics success/rejection, conflicts, retry attempts, aborts, CPU và pool wait theo hot key.

## 31. Kích thước BSON và write amplification

Khi embedding nhiều data:

- Document p50/p95/p99 bao nhiêu bytes?
- Có child array tăng mãi không?
- Read có thường chỉ lấy projection không?
- Child update độc lập có làm parent thành hot document?
- Multikey indexes có tăng entry count mạnh không?
- Có thể đưa audit/comments/events vào collection riêng?

### 31.1. Đo kích thước

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $project: { bytes: { $bsonSize: "$$ROOT" } } },
  {
    $group: {
      _id: null,
      count: { $sum: 1 },
      avgBytes: { $avg: "$bytes" },
      maxBytes: { $max: "$bytes" }
    }
  }
]);
~~~

Đây là truy vấn có thể tốn tài nguyên trên tập lớn; chạy lab/sample hoặc với capacity phù hợp. Giới hạn 16 MiB **không** phải mục tiêu thiết kế document ở sát 16 MiB.

## 32. Retention, TTL và archival

| Data type | Chính sách | Mô hình ứng viên |
|---|---|---|
| Active order | Latency thấp, giao dịch | Hot operational collection |
| Order history | Audit lâu dài, đọc ít | Cold/archive tier hoặc collection |
| Session | Expiration | TTL index theo policy |
| Activity event | Append-only, rất lớn | Time-based partition/archive |
| Payment ledger | Retention nghiêm ngặt | Durable immutable-ish records/audit |
| Derived stats | Rebuild được | Materialized views + rebuild plan |

### 32.1. TTL không phải archival

TTL index xóa documents theo background process và không bảo đảm đúng mili giây. Nó **không copy data sang kho lưu trữ** và không nên là cơ chế enforce deadline chính xác của giao dịch.

### 32.2. Legal hold và retention

Nếu compliance yêu cầu giữ một record lâu hơn, đừng dùng TTL đơn giản mà không xét legal hold. Cleanup/restore/backup phải bảo toàn các yêu cầu lưu giữ theo chính sách.

## 33. Backup và disaster recovery cũng thuộc thiết kế dữ liệu

Một model đạt p99 tốt nhưng không thể restore trong RTO có thể không phù hợp dữ liệu trọng yếu.

Những câu hỏi cần ghi trong bảng:

1. Có backup và Point-in-Time Recovery theo yêu cầu deployment không?
2. Đã thử restore thực tế chưa? Bao lâu để app hoạt động?
3. Có thể khôi phục index definitions, validators, roles và secrets cần thiết không?
4. Recovery của một tenant có cần ảnh hưởng cả cluster không?
5. Có các external effects ở payment/email/Kafka cần reconciliation sau restore không?
6. Retention, backup copies và cross-region egress tiêu tốn bao nhiêu?

### 33.1. RPO và RTO là requirements

RPO là lượng dữ liệu có thể mất theo mục tiêu phục hồi; RTO là thời gian phục hồi. RPO bằng 0 đối với acknowledged payments **không** đạt được chỉ bằng backup mỗi 15 phút.

### 33.2. Restore drill

Chạy restore trong môi trường cô lập, kiểm tra counts, keys, schema metadata, money totals và idempotency ledger. Dashboard “backup successful” không chứng minh restore đúng.

### 33.3. MongoDB và hệ thống bên ngoài

Restore database về trước thời điểm gateway charge thành công có thể làm payment state không khớp. Cần reconciliation, durable business IDs và protocol xử lý uncertain outcomes.

## 34. Schema evolution và khả năng quay lại

Một thay đổi lớn nên được phân thành:

~~~text
EXPAND readers and schema compatibility
  → BACKFILL old data, CDC/reconcile
  → SHADOW and CANARY reads
  → WRITE CUTOVER with fencing/watermark
  → STABILIZE with rollback window
  → CONTRACT old fields and collections
~~~

### 34.1. Vì sao migration ảnh hưởng bảng điểm?

Embedded one-document model có thể dễ update một lần nhưng khó chuyển nested structures khi document lớn; referenced model có thể cần nhiều collection migrations và integrity repair; hybrid cần reconcile snapshots/projections. Đánh giá **chi phí thay đổi sau này**, không chỉ thiết kế lúc tạo.

### 34.2. Big-bang đôi khi lại đúng

Một ứng dụng nội bộ nhỏ có maintenance window và dataset 10.000 records có thể hợp với offline migration được rehearsal. Dùng change streams/dual writes cho mọi thay đổi có thể tăng rủi ro mà không thêm giá trị.

### 34.3. Rollback có thể mất thông tin

Nếu schema mới thêm một trạng thái không biểu diễn được ở schema cũ, reverse mapping không lossless. Cần compatibility extension, freeze feature mới trong rollback window hoặc forward-fix policy.

## 35. Bảo mật và tuân thủ là hard constraints

Không chọn schema nhanh hơn nếu vi phạm:

- Tenant isolation/authorization cho read, write và aggregation.
- Retention, legal hold, regional residency hoặc encryption policy.
- Data minimization và PII redaction trong logs, backup, export, CDC.
- Auditability cho những thay đổi tài chính/identity.
- Separation of duties cho production writes và data migrations.

### 35.1. Encryption có thể đổi query capabilities

Mã hóa application/field-level có thể ảnh hưởng sort/filter/index theo kỹ thuật được chọn. Kiểm tra query compatibility trước khi quyết định encryption, không triển khai xong rồi mới khám phá critical query không còn hỗ trợ.

### 35.2. Query isolation khác infrastructure isolation

Shared collection + `tenantId` filter là logical isolation. Cluster riêng cho tenant quan trọng tăng capacity/operational isolation nhưng chi phí cao hơn. Chọn theo SLA/compliance/threat model, không đánh đồng hai mức.

## 36. Định lượng operational complexity

| Chỉ số | Cách đo/gợi ý |
|---|---|
| Số services ghi một aggregate | Ownership map và code inventory |
| Số collections/indexes | Index storage, migration scripts |
| Số background pipelines | CDC, outbox, cache invalidation, rebuild jobs |
| Retry/abort/conflict rates | APM metrics, transaction/optimistic counters |
| Restore duration | Recovery rehearsal |
| Incident frequency/MTTR | On-call runbooks và tickets |
| Deploy phases/rollback steps | Release plan, number of gates |
| Dữ liệu cần đối soát | Mismatch count, repair backlog |
| Chi phí con người | On-call và maintenance effort |

### 36.1. Read model nhanh nhưng có worker riêng

Một materialized view giúp GET nhanh có thể cần service tiêu thụ events, checkpoint store, dead-letter queue, replays, alerts và reconciliation. Đừng chấm vận hành bằng 5/5 chỉ vì GET đơn giản.

### 36.2. Ownership và cơ chế rebuild

Mỗi derived collection cần owner, freshness SLO, rebuild procedure và data provenance. Không có runbook rebuild là rủi ro vận hành dù query hiện rất nhanh.

## 37. Availability và failover

Replica set phục vụ high availability nhưng khi primary election, ứng dụng có thể gặp transient errors, server selection timeouts và commit outcomes chưa xác định.

### 37.1. Đường đọc có thể stale

Đọc secondary giúp phân tải những use cases chấp nhận lag, nhưng không mặc nhiên đáp ứng confirmation mới commit. Phải xét read preference/concern, session causal consistency và staleness contract.

### 37.2. Retryable write không thay idempotency

MongoDB driver có retryable writes trên những operations/topologies phù hợp, nhưng client retry **toàn HTTP request** có thể tạo logical operation mới. Dùng stable business request ID, unique ledger và reconciliation cho thanh toán/giữ chỗ.

### 37.3. Fault tests là đầu vào thiết kế

Test failover, network timeout, pool exhaustion, transaction conflicts, secondary lag và restore trên test topology tương thích. Quan sát p99 lẫn business invariants sau retry.

## 38. Capacity hiện tại và tăng trưởng

Một forecast giả định:

| Hạng mục | Hiện tại | Sau 12 tháng | Rủi ro cần theo dõi |
|---|---:|---:|---|
| Orders | 30 triệu | 80 triệu | Index/backup growth |
| Activity events | 300 triệu | 1,2 tỷ | Retention và working set |
| Peak checkout writes/s | 300 | 1.000 | Hot SKUs/transactions |
| Peak catalog reads/s | 6.000 | 20.000 | Cache misses/index CPU |
| Tenant lớn nhất | 15% traffic | 35% traffic | Hot shard/noisy neighbor |

Đây là minh họa, không phải kết quả đo. Growth không luôn tuyến tính theo node count; hot keys, index cache, retries và scatter-gather tạo bottlenecks không tuyến tính.

### 38.1. Headroom

Cần capacity dự phòng cho campaign spikes, failover, index builds, backups và migration. Nếu cả cluster đạt 95% CPU ở benchmark ngắn, khả năng chịu incident có thể quá thấp.

### 38.2. Workload mix

Đo tỉ lệ reads/writes, request size distribution, status filter selectivity và peak bursts. Synthetic benchmark chỉ đọc 100% không phản ánh contention lúc checkout burst.

## 39. Cost model tối giản

Chi phí tổng nên xét:

\[
\text{TotalCost}
= \text{Compute}+\text{Storage}+\text{Backup}
+\text{Network}+\text{Operations}
\]

| Thành phần | Ví dụ chi phí |
|---|---|
| Compute | Replica/shard nodes, CPU/RAM, peak scaling |
| Storage | Documents, indexes, oplog, replication, compression |
| Backup | Retention, PITR snapshots, restore storage |
| Network | Cross-region reads/CDC, `$lookup`, large BSON payloads |
| Operations | Alerting, migration, incidents, staff/on-call |

### 39.1. Write amplification

Hybrid snapshot và materialized views tạo nhiều copies/updates. Một business write có thể fan out tới orders, productStats, search và analytics. Ước lượng tổng bytes/writes, độ trễ và cost của pipelines.

### 39.2. Không rẻ bằng cách bỏ durability

Nếu thiếu backup/replication khiến RPO/RTO không đạt, phương án bị loại trước khi so giá. Giá thấp không bù dữ liệu tiền tệ bị mất.

## 40. Ma trận định tính ba phương án order model

Ba ứng viên:

- **A — All-in-one embedding:** parent order chứa items, shipping snapshot và **toàn bộ** audit history không có bound.
- **B — Fully referenced:** orders, orderItems, auditEvents và catalog references; ứng dụng join/query phù hợp.
- **C — Hybrid:** order chứa **bounded** item/shipping snapshots; audit events và catalog riêng, checkout có invariant protocol.

| Tiêu chí | A — Embedded all | B — References | C — Hybrid |
|---|---|---|---|
| Order detail read | Một document, có thể rất lớn | Multiple queries/join | Snapshot gọn, một read |
| Item update | Đơn giản trong parent | Independent children | Order snapshot immutable |
| Audit growth | Nguy cơ 16 MiB/hot array | Append riêng | Append riêng |
| Atomic order fields | Một document | Cần xác định boundary | Bounded order atomic |
| Reference integrity | Ít link nội order | Cần orphan checks | Cần kiểm tra catalog refs |
| Inventory/payment correctness | Vẫn cần cross-doc protocol | Vẫn cần | Vẫn cần |
| Index/query performance | Parent payload lớn khi history dài | Nhiều indexes/joins | Tối ưu UI read theo snapshot |
| Migration | Nested docs lớn | Multi-collection changes | Snapshot + derived data policy |
| Operations | Ít collections, tăng risk khi lớn | Integrity cleanup | Projection/CDC khi có copy |
| Scale growth | Khó với unbounded histories | Child growth độc lập | Bounded aggregate |

### 40.1. Hard gate trước khi tính điểm

A bị **loại trong ví dụ audit history tăng không giới hạn** vì chạm growth/16 MiB risk. Không cho A điểm cao ở read performance rồi dùng điểm đó bù việc vi phạm giới hạn. B/C còn phải chứng minh inventory/payment transaction/idempotency protocol, không tự nhận consistency cao chỉ vì cách nhúng/tham chiếu.

### 40.2. Kết quả phụ thuộc workload

Nếu orders luôn có tối đa 3 items và không có audit history, A (embedding bounded) có thể là phương án rất hợp lý. Bảng không kết luận “hybrid luôn tốt nhất”; nó kết luận **đối với giả định workload đã nêu**, A không còn hợp lệ.

## 41. Bảng điểm có trọng số

Sau khi loại những phương án vi phạm hard gates, nhóm có thể dùng thang điểm 1–5, trong đó **5 là đáp ứng tốt hơn**. Giả sử các trọng số:

| Tiêu chí | Trọng số |
|---|---:|
| Phù hợp mô hình/growth | 20% |
| Tính nhất quán/correctness khi triển khai đầy đủ | 30% |
| Read performance | 20% |
| Write performance | 15% |
| Vận hành/migration | 15% |
| **Tổng** | **100%** |

Các điểm dưới đây là **ước lượng thảo luận của nhóm**, chưa phải benchmark; cột consistency giả định mỗi phương án đã có protocol đúng để vượt hard invariants.

| Phương án | Mô hình 20% | Consistency 30% | Read 20% | Write 15% | Ops 15% | Tổng / 5 |
|---|---:|---:|---:|---:|---:|---:|
| A (all embedded, đã bị hard-gate loại) | 3 | 4 | 5 | 2 | 3 | 3,55 |
| B (references) | 5 | 4 | 2 | 4 | 4 | 3,80 |
| C (hybrid) | 4 | 5 | 4 | 3 | 2 | 3,85 |

Ví dụ cách tính B:

\[
S_B = 0.20(5)+0.30(4)+0.20(2)+0.15(4)+0.15(4)=3.80
\]

Ví dụ cách tính C:

\[
S_C = 0.20(4)+0.30(5)+0.20(4)+0.15(3)+0.15(2)=3.85
\]

### 41.1. Chênh 0,05 không chứng minh C thắng

Sai số do chủ quan chấm điểm có thể lớn hơn 0,05. Trong quyết định thật, B và C cần prototype/benchmark và sensitivity analysis, không tuyên bố C “hơn 1,3%” như một bằng chứng chắc chắn.

### 41.2. Không nhân đôi ý nghĩa consistency

Nếu một ứng viên vi phạm business invariant thì bị loại. Điểm consistency trong bảng chỉ đánh giá **độ khó và độ chắc chắn của cơ chế đạt invariant**, không cho phép đánh đổi invariant bằng các điểm read/ops.

### 41.3. Trọng số phải do người có trách nhiệm phê duyệt

Với feed đọc rất nhiều, trọng số read performance có thể cao. Với payment ledger, correctness/audit và durability là ưu tiên tuyệt đối. Không dùng một bộ trọng số cho mọi endpoints.

## 42. Sensitivity analysis: đổi trọng số thì sao?

Giả sử nhóm lo ngại việc vận hành hybrid pipelines và tăng trọng số Ops. Thay vì chỉ đổi một trọng số rồi tổng vượt 100%, hãy **chuẩn hóa lại tất cả trọng số** và tính lại. Nếu B vượt C khi operations weight tăng, kết luận phụ thuộc vào độ ưu tiên vận hành.

### 42.1. Điểm là mô hình quyết định, không phải benchmark

Điểm 4/5 ở write performance phải có căn cứ như QPS, p99, write amplification, conflict/retry rates. Nếu chưa đo, gắn nhãn **estimate/low confidence**, không ghi là sự thật.

### 42.2. Áp dụng robustness

Hỏi: nếu mỗi điểm ước lượng sai ±1, phương án được chọn còn thắng không? Nếu không, bổ sung measurements hoặc chọn phương án đơn giản/reversible hơn thay vì chấp nhận kết quả mong manh.

### 42.3. Rủi ro không có tần suất chắc chắn

Đánh giá impact và likelihood là hữu ích, nhưng số điểm rủi ro không tự biến thành xác suất thật. Dùng failure modes, historical incidents, tests và runbooks để hỗ trợ.

## 43. Một bảng đánh đổi hoàn chỉnh phải có bằng chứng

| Tiêu chí | Bằng chứng cần đưa vào quyết định |
|---|---|
| Order detail latency | p95/p99 với payload/traffic representative |
| Checkout throughput | Accepted writes/s, stock invariants, retries |
| Query efficiency | Explain `totalKeysExamined`/`totalDocsExamined` |
| Storage growth | BSON size p95/p99, index bytes, archive plan |
| Consistency | Concurrency/transaction/fault injection results |
| Migration | Expand/backfill/cutover rollback rehearsal |
| Availability | Failover and recovery tests |
| Ops | Number of pipelines, alert coverage, MTTR |
| Cost | Forecast nodes/storage/network/on-call |

### 43.1. Gắn độ tin cậy cho từng ô

Ví dụ:

~~~text
Read latency C: 90 ms p95 — MEASURED, 10 million orders, warm cache
Write latency B: 75 ms p95 — ESTIMATED, not benchmarked
Rollback complexity C: HIGH — VERIFIED in staging drill
~~~

Không so một số measured với số ước lượng như thể cả hai ngang nhau; thêm cột confidence và kế hoạch thu dữ liệu thiếu.

### 43.2. Dữ liệu production có phân bố lệch

Một benchmark đều 10.000 tenants có thể không đại diện khi 30% traffic thuộc một tenant. Chạy skew/hot-key workloads theo quan sát thực tế.

## 44. Case study A: checkout và inventory

**Hard invariants:**

~~~text
stock.available >= 0
one (tenantId,requestId) => at most one business effect
confirmed order must have consistent reservation/ledger
no double charge for a retry of the same payment request
~~~

**Ứng viên:**

- A: một collection orders, đọc stock rồi ghi order không có conditional update → **loại**, oversell.
- B: conditional stock update, tạo order riêng không có transaction/reconciliation → có nguy cơ partial success, cần sửa.
- C: conditional stock update và order/ledger trong MongoDB transaction, dùng idempotency key; external payment qua provider idempotency/outbox → ứng viên khả thi nếu topology và business process hỗ trợ.

### 44.1. Atomic predicate

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "SKU-A",
    tenantId: "t-01",
    available: { $gte: 1 }
  },
  { $inc: { available: -1, reserved: 1 } }
);
~~~

Điều kiện nằm trong write, tránh check-then-act race. Nếu còn cần order/ledger atomic, đặt trong transaction/protocol phù hợp; xử lý transient conflicts và unknown outcomes.

### 44.2. Idempotency

~~~javascript
db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uniq_tenant_request" }
);
~~~

Client retry cùng request ID không được tạo effect mới. External payment gateway không tự rollback cùng MongoDB transaction; dùng idempotent provider key/reconciliation và domain workflow.

### 44.3. Metrics để xác minh

Checkout p95/p99, accepted/rejected requests, stock negative count, duplicate ledger count, transaction abort/retry rate, payment reconciliation backlog. Một test chỉ đo p95 mà không kiểm tra stock invariants là chưa đủ.

## 45. Case study B: catalog đọc nhiều

**Yêu cầu:** 90%+ operations là đọc, sản phẩm có ảnh/tên/category, giá thay đổi theo campaign, UI cần tìm theo category/brand, sort/popularity. Có thể chấp nhận độ trễ search result theo policy.

**Phương án:**

1. Embed toàn bộ comments và inventory vào product → document lớn, nhiều writers/hot fields; loại phần unbounded.
2. Product document cho core metadata; comments riêng, inventory riêng, search/read model riêng.
3. Cache product summary với TTL/invalidation; checkout vẫn đọc authoritative price/stock snapshot theo policy.

### 45.1. Bảng mini

| Trục | Core product + references/cache |
|---|---|
| Model | Bounded document, comments ngoài |
| Consistency | UI eventual; checkout authoritative |
| Read performance | Compound indexes/cache/search projection |
| Write performance | Price/inventory update paths độc lập |
| Ops | Cache invalidation, projection rebuild, index management |

### 45.2. Kiểm thử quan trọng

Đổi giá campaign, GET có thể cache stale, nhưng checkout phải áp đúng price policy (snapshot trước xác nhận, version/validation). Đừng cho cache price quyết định charge mà không có chính sách rõ.

## 46. Case study C: activity feed và audit

**Yêu cầu:** sự kiện append-only hàng trăm triệu records, xem theo tenant/actor/thời gian, phân trang sâu, có chính sách retention; một phần audit bắt buộc không được xóa sớm.

**Phương án phù hợp thường gặp:**

- Event collection riêng, không nhúng toàn bộ vào user/order.
- Stable event ID, eventTime và tenant ID.
- Index theo access pattern, cân nhắc partitioning/sharding khi cần.
- Keyset pagination, archival/cold tier theo retention.
- Outbox/idempotent consumer nếu events phát từ business transaction.

### 46.1. Bảng mini

| Trục | Event collection + keyset |
|---|---|
| Model | Append-only, child growth độc lập |
| Consistency | Eventual read nếu contract cho phép |
| Read performance | Keyset và targeted index |
| Write performance | Avoid hot parent array |
| Ops | Retention, archive, replay, backup |

### 46.2. Audit khác feed giải trí

Audit bắt buộc giữ integrity/retention; feed UI có thể cache/archival mạnh hơn. Không dùng TTL chung cho cả hai nếu một bên phải bảo toàn nhiều năm.

## 47. Architecture Decision Record (ADR)

Một ADR có thể viết:

~~~markdown
# ADR-012: Chọn mô hình order bounded hybrid

Status: Accepted (sau benchmark và review)

Context:
- 30M orders, burst checkout, orders thường có <= 20 items
- Audit history có thể tăng vô hạn
- No double charge, stock nonnegative là hard constraints

Options:
- A: embed mọi thứ (rejected: unbounded audit)
- B: full references
- C: bounded order snapshot + separate audit (selected)

Decision:
- Embed purchase-time snapshots trong order
- Audit events ở collection riêng
- Inventory conditional update + transaction/ledger khi cần
- Maintain indexes theo Q1-Q8, monitor hot keys

Evidence:
- Link tới benchmark/result artifacts nội bộ
- Concurrent correctness tests, query explain, restore drill

Risks:
- Extra operational cost cho audit and outbox
- Need reconciliation, schema migration/backfill

Review triggers:
- p99 latency vượt SLO
- p99 order document size tăng mạnh
- Item cardinality thay đổi
- Cost hoặc traffic mix thay đổi
~~~

Đây là mẫu nội dung ADR để nhóm điền **dữ liệu đo thật**. Không ghi “Accepted” dựa trên bảng điểm minh họa mà chưa chứng minh hard gates và measurements.

## 48. Validation plan phải khớp từng trục

| Trục | Test |
|---|---|
| Model | Max cardinality/size, schema variations, migration |
| Consistency | Race tests, idempotency, failover, snapshot boundary |
| Read performance | Query plans, projections, p95/p99 under load |
| Write performance | Burst QPS, hot key contention, retries/aborts |
| Operational | Backup/restore, old/new deployment, rollback drill |
| Security | Tenant isolation, privileges, redaction/encryption |

### 48.1. Không test bằng mocks rồi kết luận MongoDB semantics

Mock repository có thể kiểm tra service branches nhưng không chứng minh unique index/transaction/atomic update của server. Integration tests dùng MongoDB test deployment thực phù hợp topology.

### 48.2. Fault injection

Network timeout sau commit, replica election, connection pool pressure và CDC worker crash có thể ảnh hưởng data/latency. Cần test uncertain outcomes và business reconciliation, không chỉ requests thành công.

## 49. Benchmark design

Một benchmark có ý nghĩa phải giữ:

1. **Cùng workload/định nghĩa kết quả** giữa phương án B và C.
2. Dataset đủ lớn, cardinality skew và size distribution representative.
3. Warm/cold cache runs được phân biệt.
4. Concurrency và request mix có burst như production.
5. Index definitions được ghi và explain cho critical queries.
6. Đo p50/p95/p99, throughput, errors, conflicts, retries, CPU/IO/RAM/network.
7. So total cost/write amplification, không chỉ một API GET.
8. Kiểm tra final business invariants sau load.

### 49.1. Benchmark không tự quyết mô hình

B có thể nhanh hơn trong một query detail với dataset nhỏ, nhưng C ổn hơn khi có customer-specific traffic/big orders. Một benchmark ngắn không dự báo restore time, migration risk hay on-call cost.

### 49.2. Không so lệch projection

Nếu B chỉ trả order header còn C trả cả 20 items, so latency trực tiếp không công bằng. Cả hai phải trả **cùng logical response** với cùng consistency policy.

## 50. Bảng kết quả thử nghiệm cần ghi nhận

Một mẫu khi team điền số thực:

| Workload | B p95 | C p95 | SLO | Kết quả |
|---|---:|---:|---:|---|
| Q4 order detail | TBD | TBD | Theo API | Chưa đo |
| Q5 list 20 orders | TBD | TBD | Theo API | Chưa đo |
| Checkout burst | TBD | TBD | Theo API | Chưa đo |
| Audit append | TBD | TBD | Theo pipeline | Chưa đo |
| Restore 80M orders | TBD | TBD | Theo RTO | Chưa diễn tập |

Không điền số tưởng tượng vào cột measured. Khi thiếu bằng chứng, bảng nên thể hiện `TBD`/confidence thấp để có một **việc cần làm cụ thể** thay vì tạo cảm giác quyết định đã có cơ sở.

## 51. Decision tree cho mô hình dữ liệu

~~~mermaid
flowchart TD
    Relationship["Dữ liệu parent/child"] --> Bounded{"Child cardinality có bound và lifecycle cùng parent?"}
    Bounded -->|"Có"| ReadTogether{"Đọc parent+child thường cùng nhau?"}
    Bounded -->|"Không"| Reference["Reference hoặc collection riêng"]
    ReadTogether -->|"Có"| Embed["Bounded embedding candidate"]
    ReadTogether -->|"Không"| Reference
    Embed --> Shared{"Child được chia sẻ/cập nhật độc lập nhiều nơi?"}
    Shared -->|"Có"| Hybrid["Hybrid snapshot + reference"]
    Shared -->|"Không"| Guard["Kiểm tra BSON size/hot writes/invariant"]
    Guard --> Decision["Đo query/consistency/operations"]
    Hybrid --> Decision
    Reference --> Decision
~~~

### 51.1. Không chọn bằng sơ đồ mà bỏ workload

Decision tree tạo **ứng viên**, không phải quyết định cuối. Một child có bound vẫn có thể rất lớn; một reference join vẫn có thể nhanh nếu có index và số parent nhỏ.

### 51.2. Đưa tính nguyên tử lên sớm

Nếu parent và child phải được sửa cùng lúc để bảo vệ invariant, embedding có lợi khi hợp lý về size/lifecycle. Nếu không thể embed, xem transaction hoặc redesign protocol; không bỏ invariant để tiết kiệm một query.

## 52. Decision tree cho consistency

~~~mermaid
flowchart TD
    I["Business write"] --> One{"Invariant trong một document?"}
    One -->|"Có"| Atomic["Atomic update + predicate / CAS"]
    One -->|"Không"| Multi{"Trong cùng MongoDB deployment có transaction hỗ trợ?"}
    Multi -->|"Có"| Tx["Transaction + constraints + retries"]
    Multi -->|"Không"| Saga["Idempotency / outbox / reconciliation"]
    Atomic --> External{"Có external side effects?"}
    Tx --> External
    Saga --> External
    External -->|"Có"| Idem["Stable business ID + provider idempotency + recovery"]
    External -->|"Không"| Verify["Verify business invariants"]
    Idem --> Verify
~~~

### 52.1. Không chọn transaction chỉ vì relation nhiều

Một order tham chiếu product nhưng không phải cập nhật product khi sửa đơn; không nhất thiết cần transaction chỉ để đọc hai collections. Giao dịch được chọn khi **business operation cần atomic multi-document changes**.

### 52.2. Write skew

Nếu hai transactions đọc count của nhiều documents rồi ghi vào hai docs khác nhau, snapshot isolation không luôn bảo vệ một global invariant. Cần unique index, guard document hoặc mô hình serialize chung theo use case.

## 53. Tổng hợp các hard gates cho quyết định

Một ứng viên phải đi qua các kiểm tra:

| Gate | Câu hỏi |
|---|---|
| Business correctness | Không thể oversell/double charge/lost confirmed order? |
| Security | Tenant ownership và PII policies được enforce? |
| Data bound | Không có array/document tăng vô hạn tới giới hạn? |
| Durability | Đạt write acknowledgement, RPO/restore requirements? |
| Compatibility | Reader/writer versions có migration path? |
| Operability | Có backups, monitoring, runbook và owner? |
| SLO | Có đường hợp lý để đạt p95/p99 và throughput? |

Nếu một gate fail, **sửa phương án hoặc loại**, không cho điểm khác bù. Một số gates cần benchmark/proof trước khi có kết luận; trạng thái “chưa xác minh” không đồng nghĩa PASS.

## 54. Kỹ thuật tránh chấm điểm thiên lệch

Các sai lệch thường gặp trong review:

- **Confirmation bias:** đã thích embedding nên chỉ benchmark query một document.
- **Metric cherry-picking:** chỉ dùng p50 và bỏ p99/conflicts.
- **Survivorship bias:** không ghi các requests timeout hay bị retry.
- **Unknowns treated as zero risk:** không có evidence được xem là “vận hành đơn giản”.
- **Double-counting:** một lợi ích được cộng ở cả model và performance nhiều lần.
- **Sunk cost:** giữ design cũ chỉ vì đã đầu tư một tháng dù hard gate fail.

### 54.1. Review độc lập

Để owner tính nhất quán, DBA/operations và application team đánh giá riêng trước khi thảo luận. Dùng cùng workload/spec/weight definitions và ghi lại sự khác biệt điểm.

### 54.2. Theo dõi confidence

Mỗi đánh giá có trạng thái `MEASURED`, `PROTOTYPED`, `ESTIMATED` hoặc `UNKNOWN`. Các ô có confidence thấp là backlog cần thử nghiệm, không nên che bằng con số 4/5.

## 55. Khi nào nên xem lại quyết định?

Một schema phù hợp hôm nay có thể thành vấn đề sau 18 tháng. Trigger xem lại:

1. p99 API vượt SLO trong nhiều giai đoạn đại diện.
2. Size p95/p99 của document tăng mạnh.
3. Number of items/comments/events đổi khác assumptions.
4. Tenant skew hoặc hot key contention mới.
5. Thêm product feature mới cần query/transaction khác.
6. Chi phí index/backup/restore vượt budget.
7. RPO/RTO/compliance yêu cầu thay đổi.
8. CDC lag/reconciliation incidents tăng.
9. Migrations kéo dài hoặc rollout thường xuyên phải rollback.

### 55.1. Thiết kế có thể thay đổi

Ưu tiên stable IDs, versioned schema, bounded arrays, clear ownership và khả năng backfill/reconcile khi cần. Đây là năng lực giảm rủi ro cho tương lai, không chỉ là “clean architecture”.

## 56. Bài thực hành A — lập access-pattern matrix

Một app đặt lịch phòng khám có `patients`, `doctors`, `appointments` và `auditEvents`. Hãy viết ít nhất 5 query shapes, gồm:

- Tìm lịch hẹn của một bệnh nhân trong 30 ngày.
- Xem doctor schedule theo ngày.
- Đặt một slot chưa có booking active.
- Xem lịch sử thay đổi của appointment.
- Thống kê số lịch hẹn mỗi bác sĩ.

Với từng query, ghi filter, sort, projection, tần suất, data size và consistency requirement. Sau đó đề xuất indexes (chưa cần khẳng định chúng tối ưu).

## 57. Bài thực hành B — embedding hay reference?

Một product có 5 thuộc tính tĩnh, tối đa 10 ảnh và 2 triệu comments theo thời gian. Hãy chọn chỗ lưu images và comments, giải thích theo cardinality, read patterns, size bound, ownership và query pagination. Điều gì sẽ thay đổi nếu ảnh là binary files lớn?

## 58. Bài thực hành C — immutable order snapshot

Khách đặt hàng với giá 125.000 đồng. Ngày hôm sau catalog đổi giá thành 130.000 đồng và tên sản phẩm cũng đổi. Hãy thiết kế fields trong `orders.items` và `products` sao cho lịch sử hóa đơn không bị sửa, đồng thời catalog vẫn đọc tên/giá hiện tại.

## 59. Bài thực hành D — hai requests tranh stock

Initial stock=1. Hai requests qty=1 chạy đồng thời. Viết MongoDB atomic update có điều kiện và expected outcomes. Nếu còn phải tạo order và ledger ở collections khác, mô tả ranh giới transaction/reconciliation.

## 60. Bài thực hành E — consistency table

Cho ba paths:

1. User vừa trả tiền và muốn xem xác nhận.
2. Trang home xem 20 sản phẩm nổi bật.
3. BI report tổng doanh thu tháng trước.

Hãy chọn stale-read budget, read preference/concern hoặc snapshot/cutoff strategy phù hợp, và giải thích vì sao **không** sử dụng một policy đồng nhất cho cả ba.

## 61. Bài thực hành F — index tradeoff

Với query:

~~~javascript
db.orders.find(
  { tenantId: "t-01", customerId: "C-9", status: "PAID" }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Hãy đề xuất compound index, sau đó viết cách đọc explain results. Nếu application còn filter chỉ theo tenant nhưng cùng sort, vì sao index ứng viên ban đầu có thể chưa đủ?

## 62. Bài thực hành G — bounded array và hot document

Một `customer` chứa mảng toàn bộ 1 triệu giao dịch và được 300 workers append đồng thời. Chỉ ra ít nhất bốn vấn đề. Chọn một design khác và xác định query list transactions với keyset pagination.

## 63. Bài thực hành H — sharding đa tenant

Một cluster có 2.000 tenants; tenant lớn nhất có 40% writes. Hãy đánh giá shard key `tenantId`, phương án shard key compound/partition và tác động của việc query tenant-scoped. Không mặc định hashed tenant key làm hot tenant biến mất.

## 64. Bài thực hành I — materialized view

Dashboard cần top-10 products theo 7 ngày, refresh trễ tối đa 60 giây. Tạo design cho source events, derived collection, update worker, checkpoint/idempotency và cách rebuild nếu dữ liệu bị lệch. Đặt monitoring cho lag và mismatch.

## 65. Bài thực hành J — tính weighted score

Dùng trọng số `20% model, 30% consistency, 20% read, 15% write, 15% ops` và bảng điểm của B/C. Tính tổng. Sau đó thảo luận: chênh 0,05 có đủ để chọn C chưa? Những measurements nào thiếu?

## 66. Bài thực hành K — hard gate đánh bại điểm số

Một thiết kế được chấm 4,9/5 về hiệu năng nhưng cho phép một request payment timeout bị xử lý hai lần. Có được chọn không? Thiết kế idempotency ledger, unique key và recovery path rồi chấm lại.

## 67. Bài thực hành L — backup/restore

Payment database có RPO=0 cho các writes đã được acknowledge và RTO=30 phút. Hiện chỉ có backup snapshot mỗi 1 giờ, chưa test restore. Hãy ghi những hard gaps, kế hoạch thử nghiệm và khả năng cần đổi kiến trúc/SLAs.

## 68. Bài thực hành M — tạo ADR

Chọn giữa B (references) và C (hybrid) cho order detail. Viết ADR có context, hard constraints, alternatives, evidence, selected option, risks, mitigations, owners, review triggers và rollback/migration plan.

## 69. Bài thực hành N — sensitivity analysis

Nhóm tăng trọng số operations từ 15% lên 30% và giảm trọng số read để tổng vẫn 100%. Hãy tính điểm lại B/C, giải thích ý nghĩa nếu thứ tự đổi và tại sao phải chạy prototype trước quyết định khó đảo ngược.

## 70. Gợi ý đáp án thực hành

**A:** Query lịch bệnh nhân: filter patientId/time, sort startAt; doctor schedule: doctorId/time; booking: unique business key cho active slot; audit: appointmentId/time; aggregate statistics: doctorId/time/status, có thể materialized. Hard gate không double booking; index cần đánh giá với query plans.

**B:** Bounded image metadata có thể embed nếu nhỏ và luôn đọc cùng product; binary ảnh lớn thường lưu ở object storage với references. 2 triệu comments phải ở collection riêng với productId/time index và pagination; không nhúng mảng không giới hạn.

**C:** `orders.items` giữ productId, nameAtPurchase, unitPriceMinor và quantity, coi là snapshot. `products` giữ currentName/currentPrice; cập nhật catalog không sửa hóa đơn.

**D:** `updateOne({_id:sku,available:{$gte:1}},{$inc:{available:-1}})`, tối đa một matched; stock≥0. Order/ledger ở records khác cần transaction/protocol với reconciliation và idempotency key.

**E:** Payment confirmation dùng path authoritative/session semantics phù hợp; homepage có thể dùng cache/secondary với bounded staleness; BI dùng cutoff/snapshot/reconciliation để tổng tính được tại một boundary.

**F:** Index ứng viên `{tenantId:1,customerId:1,status:1,createdAt:-1,_id:-1}`. Đọc keys/docs examined, plan, nReturned; query không có customerId/status có thể cần index khác cho sort.

**G:** Rủi ro 16 MiB, document growth, hot contention, payload lớn, mảng khó phân trang; tách transactions thành collection với customerId + createdAt + _id index, dùng keyset.

**H:** Tenant-only shard key có thể khiến một mega-tenant nóng; cần đo skew, targeting, shard key cardinality, compound/partition strategy và consistency constraints trước khi thay.

**I:** Event source authoritative, derived top-10 theo window, worker idempotent có checkpoint, rebuild từ event history khi mismatch; theo dõi p99 lag ≤60s theo requirement và late events/deletes.

**J:** B = 3,80; C = 3,85. Không nên chọn chỉ vì 0,05; cần benchmark read/write, restore, operational effort và confidence intervals.

**K:** Loại ứng viên vi phạm non-double-charge. Sửa bằng stable requestId, unique ledger key, payload hash và reconcile unknown outcome; sau đó benchmark lại.

**L:** Snapshot hourly không tự đạt RPO=0. Cần bảo vệ acknowledged writes/replication/PITR và recovery procedure tương ứng, diễn tập restore dưới 30 phút hoặc thay đổi SLO có phê duyệt.

**M:** ADR phải nêu hard gates, evidence, selected option và conditions xem xét lại; không chỉ viết “hybrid tốt hơn”.

**N:** Trọng số phải được chuẩn hóa; thay đổi ranking cho thấy quyết định phụ thuộc business priorities, không phải chân lý cố định. Đo thêm những tiêu chí có confidence thấp.

## 71. Những sai lầm trong trade-off review

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chọn schema chỉ từ hình ERD | Query patterns bị bỏ qua | Access-pattern matrix trước |
| “Embed tất cả vì MongoDB document” | Unbounded arrays, hot parents | Bound cardinality/lifecycle |
| “Reference tất cả để normalized” | Excessive lookups/round trips | Embed snapshots/owned children khi phù hợp |
| “Transaction giải quyết mọi consistency” | Write skew, external effects | Invariant modeling + idempotency |
| “ReadConcern majority là snapshot xuyên HTTP” | Consistency hiểu sai | Scope read session/snapshot rõ |
| “Index càng nhiều càng nhanh” | Write/storage overhead | Chọn theo workload/explain |
| “Sharding tự cải thiện mọi query” | Scatter-gather/hot shards | Shard key evaluation |
| “Cache không ảnh hưởng business logic” | Read-your-writes sai | Freshness policy/invalidation |
| “TTL chính là archival” | Mất data chưa lưu trữ | Retention/archival pipeline |
| “Có backup tức là restore được” | RTO vượt mục tiêu | Restore drill |
| “Count bằng nhau nghĩa data parity đúng” | Thiếu/khác IDs/fields | Key/canonical parity |
| “Số điểm cao thay hard constraint” | Sai dữ liệu/tenant leakage | Exclusion gates |
| “p50 nhanh nghĩa production tốt” | Tail latency, retries | p95/p99 + failover/load |
| “Unknown đo thành 5/5” | Chọn theo giả định | Confidence labels + benchmark |
| “Không cần ADR vì team đã đồng ý” | Không biết vì sao chọn, khó đổi | ADR + review triggers |

## 72. Câu hỏi ôn tập

**1. Vì sao không có MongoDB schema tốt nhất cho mọi app?** — Workload, cardinality, consistency và vận hành khác nhau.

**2. Bốn trục quyết định là gì?** — Mô hình, tính nhất quán, hiệu năng, vận hành.

**3. Hard constraint khác weighted score thế nào?** — Vi phạm hard constraint phải loại/sửa, không cộng điểm bù.

**4. Khi nào embedding phù hợp?** — Child bounded, lifecycle cùng parent, thường đọc/ghi cùng nhau.

**5. Khi nào references phù hợp?** — Child tăng lớn hoặc cập nhật/truy vấn độc lập, được chia sẻ.

**6. Hybrid có lợi gì?** — Snapshot/summary đọc nhanh và giữ entity authority riêng.

**7. Hybrid đổi lại điều gì?** — Đồng bộ bản sao, write amplification, reconciliation/ops.

**8. MongoDB BSON document size tối đa là bao nhiêu?** — 16 MiB.

**9. Single-document atomicity có bao trùm ledger khác collection?** — Không.

**10. Atomic update khác idempotency ra sao?** — Atomic bảo vệ một write; idempotency ngăn same business request áp nhiều lần.

**11. Unique index giúp gì?** — Enforce uniqueness của indexed business key trong semantics hỗ trợ.

**12. Có cần transaction cho mọi reference?** — Không; chỉ khi business operation cần atomic nhiều documents.

**13. Snapshot isolation ngăn mọi write skew?** — Không mặc nhiên; cần guard/invariant design.

**14. Write concern majority giống read preference primary không?** — Không, chúng giải quyết những khía cạnh khác nhau.

**15. Đọc secondary có thể stale không?** — Có, tùy lag/concern/session.

**16. Index có chi phí gì?** — Disk/cache và index maintenance của writes.

**17. `explain` giúp xem gì?** — Query plan, keys/docs examined, nReturned, execution details.

**18. Deep skip có thể chậm dù có index?** — Có.

**19. Keyset có tạo snapshot giữa nhiều HTTP requests?** — Không.

**20. `$lookup` luôn chậm?** — Không; phụ thuộc index/fan-out/query plan.

**21. Materialized view có mặc định synchronous consistent không?** — Không; cần pipeline/freshness contract.

**22. Sharding và replica set khác nhau?** — Sharding phân vùng workload/data; replica set phục vụ replication/HA.

**23. Hashed shard key chữa một hot key duy nhất không?** — Không tự động.

**24. Multi-tenant shared collection có tự bảo mật không?** — Không; phải scope theo auth.

**25. TTL có archive records không?** — Không, TTL xóa theo policy.

**26. Vì sao cần restore drill?** — Backup thành công không chứng minh khôi phục đạt RTO/RPO.

**27. Trọng số trong ma trận lấy từ đâu?** — Business/SLO/risk priorities được phê duyệt.

**28. Chênh 0,05 điểm có đủ kết luận?** — Không khi scoring chủ quan và chưa đo.

**29. Cần thử nghiệm những gì?** — Model bound, correctness, query plans, load, failover, rollback/restore.

**30. ADR có ích gì?** — Ghi lý do, phương án khác, evidence, rủi ro, owner và review triggers.

## 73. Checklist trước khi phê duyệt thiết kế

- [ ] Use case, scope và out-of-scope được viết rõ?
- [ ] Hard business invariants và tenant/security gates được nêu?
- [ ] Access patterns có filter/sort/projection/cardinality/traffic?
- [ ] Đã đo hoặc ước lượng p50/p95/p99 document sizes?
- [ ] Child arrays đều có bound hoặc growth plan?
- [ ] Đã so embedding, references và hybrid dựa trên lifecycle?
- [ ] Có source of truth rõ cho denormalized fields?
- [ ] Atomic boundaries/transactions/idempotency được thiết kế?
- [ ] Read concern/write concern/read preference khớp consistency policy?
- [ ] Unique indexes và business constraints thực sự enforce?
- [ ] Compound indexes được chọn theo real query shapes?
- [ ] Đã phân tích `explain` và p95/p99 critical queries?
- [ ] Đã xét deep pagination, sort tie-breaker và keyset?
- [ ] Đã tính cost của lookup/aggregation/materialized projections?
- [ ] Có freshness/cache invalidation policy?
- [ ] Đã đánh giá hot keys, write contention và skew?
- [ ] Nếu sharded, đã kiểm chứng key selection/routing/uniqueness?
- [ ] Tenant isolation, auth scope và PII controls đạt yêu cầu?
- [ ] Storage/index growth/retention/TTL được dự báo?
- [ ] Có backup/PITR, restore drill và RPO/RTO?
- [ ] Có schema migration/expand-contract và rollback window?
- [ ] Có phương án thay thế, hard gates và weighted score?
- [ ] Bảng điểm có measured/estimated/unknown confidence labels?
- [ ] Đã chạy sensitivity analysis cho trọng số?
- [ ] Benchmark B/C dùng cùng logical responses và consistency?
- [ ] Đã thử concurrency, fault injection và restore?
- [ ] Có ADR, ownership, monitoring và review triggers?

## 74. Kết luận

Trong thiết kế ứng dụng MongoDB, **mô hình dữ liệu, tính nhất quán, hiệu năng và vận hành là bốn mặt của cùng một quyết định**. Embedding có thể giảm round trips và tận dụng atomicity một document, nhưng dễ gặp giới hạn size và hot-document contention nếu child tăng không giới hạn. References hỗ trợ lifecycle độc lập, nhưng cần queries/indexes và integrity/transaction protocol thích hợp. Hybrid tăng tốc đường đọc có snapshot rõ, đồng thời tăng chi phí đồng bộ và vận hành.

**Bảng đánh đổi tốt không bắt đầu bằng điểm số.** Nó bắt đầu từ business invariants và hard constraints, rồi mô tả access patterns, đưa ra nhiều ứng viên, lập ma trận định tính, loại phương án không hợp lệ, đánh trọng số theo ưu tiên thật, đo bằng benchmark và ghi ADR. Kết quả 3,80 so với 3,85 không tự là sự thật kỹ thuật nếu các điểm chưa được kiểm chứng.

Cuối cùng, hãy đánh giá phương án xuyên suốt vòng đời: dữ liệu tăng trưởng, failover, contention, backup/restore, schema migration, security và on-call. Một thiết kế thành công không chỉ chạy nhanh ở hôm nay mà còn **giữ đúng bất biến nghiệp vụ, đáp ứng SLO và có khả năng vận hành, phục hồi, tiến hóa trong những năm tiếp theo**.
