# Bảng lựa chọn nhúng, tham chiếu, cập nhật nguyên tử và giao dịch trong MongoDB

MongoDB cho phép tổ chức dữ liệu theo **document** thay vì bắt buộc chia mọi thực thể thành các bảng quan hệ độc lập. Ưu điểm lớn là những dữ liệu thường được đọc và cập nhật cùng nhau có thể nằm trong một document và hưởng **tính nguyên tử của thao tác ghi trên một document**. Tuy nhiên, không phải cứ nhúng được là nên nhúng, và không phải cứ có hai collection là luôn phải dùng transaction.

Bài học thuộc chương **Tổng kết và tra cứu**, module **Database Engine Document MongoDB**, là một **sổ tay ra quyết định** cho bốn nhóm lựa chọn:

1. **Nhúng (embedding):** đặt dữ liệu con trực tiếp trong parent document.
2. **Tham chiếu (referencing):** giữ các documents riêng, kết nối bằng ID hoặc business key.
3. **Cập nhật nguyên tử:** sử dụng update operators, conditional updates hoặc find-and-modify trên **một document**.
4. **Giao dịch (transactions):** phối hợp nhiều thao tác hoặc nhiều documents cần commit/abort cùng nhau, trên deployment hỗ trợ.

Đây **không phải bốn lựa chọn loại trừ nhau**. Một thiết kế có thể vừa nhúng vài item trong đơn hàng, vừa tham chiếu sản phẩm, vừa dùng $inc để cập nhật tồn kho và vẫn dùng transaction cho bước tạo đơn + trừ kho nếu nghiệp vụ yêu cầu.

Tài liệu ưu tiên các **bảng tra cứu, cây quyết định, ví dụ hành vi và checklist**. Các lệnh MongoDB có tác động ghi chỉ nên chạy trong database thử nghiệm được cấp quyền; không chạy trên production nếu chưa có đánh giá tác động, kế hoạch thay đổi và sao lưu phù hợp.

## 1. Bảng chọn nhanh trong 30 giây

| Tình huống | Lựa chọn ưu tiên cân nhắc | Vì sao | Cần kiểm tra thêm |
| --- | --- | --- | --- |
| Một đơn hàng có tối đa 20 dòng hàng; luôn xem cùng đơn | **Nhúng** items | Đọc và ghi cùng vòng đời | Giới hạn kích thước, thay đổi item |
| Một khách hàng có hàng triệu đơn hàng | **Tham chiếu** | Lịch sử tăng không giới hạn | Index customerId + date, phân trang |
| Giá sản phẩm cần giữ tại thời điểm mua | **Nhúng snapshot** vào order | Bảo toàn lịch sử hợp đồng | Tách khỏi giá hiện hành |
| Hồ sơ sản phẩm đổi thường xuyên, được nhiều orders sử dụng | **Tham chiếu** master | Tránh cập nhật fan-out | Có cần thêm snapshot không? |
| Tăng số lượt xem một bài viết | **$inc một document** | Atomic counter update | Hot document contention |
| Chỉ trừ tồn kho nếu còn đủ | **Conditional update + $inc** | Check và update trong một write | Một kho hay nhiều kho? |
| Hai người cùng sửa một bản ghi theo version | **Optimistic locking trên một document** | Tránh lost update | MatchedCount và retry |
| Xóa phần tử khỏi mảng của một đơn | **$pull trên document** | Một document atomic | Mảng có tăng không giới hạn? |
| Chuyển tiền giữa hai tài khoản cần cùng commit | **Transaction** | Nhiều documents phải nhất quán | Số dư, idempotency, ledger |
| Tạo booking + giữ chỗ xe với invariant xuyên documents | **Transaction kết hợp cơ chế contention** | Commit hai writes phối hợp | Chống double-book đúng cách |
| Gửi email sau khi tạo đơn | **Outbox + async worker** | Email ngoài phạm vi DB transaction | Idempotency, retry, dedup |
| Dashboard tổng doanh thu được cập nhật theo sự kiện | **Derived read model** | Giảm chi phí tính lại | Lag và reconciliation |
| Audit/payment events tăng vô hạn | **Collection riêng** | Vòng đời và phân trang độc lập | Retention, bất biến sự kiện |
| Cần đọc hồ sơ người dùng hiện tại khi xem booking | **Reference hoặc $lookup** | Không dùng snapshot lịch sử thay current profile | Authorization/tenant scope |
| Cần thay nhiều documents nhưng eventual consistency được chấp nhận | **Events/saga hoặc batch có kiểm chứng** | Không nhất thiết giữ transaction dài | SLA, retry, compensation |

**Điểm cốt lõi:** quyết định đúng phụ thuộc vào **access pattern + cardinality + lifecycle + consistency invariant**, không chỉ vào kiểu quan hệ 1:N hay số lượng collections.

## 2. Hai trục quyết định cần tách riêng

Nhiều thiết kế sai vì trộn lẫn hai câu hỏi:

- **Câu hỏi mô hình dữ liệu:** dữ liệu nên ở cùng hay ở các documents khác nhau?
- **Câu hỏi tính nhất quán:** những thay đổi nào phải được quan sát như một đơn vị atomic?

Ví dụ một booking có addons được nhúng trong booking, nhưng giữ chỗ một chiếc xe là thao tác liên quan tài nguyên riêng. Phần addons có thể cập nhật nguyên tử trong booking; còn việc khẳng định xe chưa bị đặt trùng cần giao thức concurrency khác.

| Mô hình lưu trữ | Một document | Nhiều documents |
| --- | --- | --- |
| Một business operation | Update operators hoặc findOneAndUpdate | Có thể dùng transaction hoặc workflow eventual |
| Nhiều business operations | State machine/version trên document | Transaction, outbox, saga, reconciliation tùy invariant |
| Đọc dữ liệu | Một find/projection | Nhiều queries, $lookup, read model |
| Rủi ro thường gặp | Document quá lớn, hotspot | Referential drift, partial writes |

### 2.1. Nhúng là quyết định lưu trữ, không phải phép tối ưu tuyệt đối

Nhúng giảm joins/round trips, nhưng làm document lớn hơn, tăng contention và có thể tạo dữ liệu trùng lặp khó duy trì.

### 2.2. Transaction là quyết định phối hợp commit, không phải phép thay thế schema design

Transaction có thể bảo vệ một tập writes xuyên documents nhưng có overhead và không tự làm truy vấn hoặc thiết kế vòng đời trở nên tốt.

### 2.3. Atomic update không đồng nghĩa consistency của mọi hệ thống

UpdateOne là atomic ở cấp một document, không bao trùm cache Redis, broker, email, thanh toán hoặc những documents khác.

## 3. Cây quyết định tổng quát

~~~text
Dữ liệu A và B có thường được đọc cùng nhau?
  |
  +-- Không --> Ưu tiên tham chiếu / tải khi cần
  |
  +-- Có
       |
       v
     Số phần tử và kích thước có bounded chặt không?
       |
       +-- Không --> Tách collection / reference / bucket
       |
       +-- Có
            |
            v
          Có cùng vòng đời, owner và nhu cầu atomicity?
            |
            +-- Có --> Nhúng là ứng viên mạnh
            |
            +-- Không --> Reference hoặc snapshot chọn lọc
                            |
                            v
                          Nếu cần read nhanh,
                          cân nhắc derived view
~~~

Tiếp tục câu hỏi ghi:

~~~text
Business invariant phải thay đổi những gì?
  |
  +-- Một document
  |      |
  |      v
  |   Atomic update + predicate điều kiện
  |   + version nếu chống lost update
  |
  +-- Nhiều documents
         |
         v
       Phải commit/abort tất cả cùng lúc?
         |
         +-- Không --> Event/outbox/saga + reconciliation
         |
         +-- Có
              |
              v
           Transaction trên topology hỗ trợ
           + bảo vệ conflict/uniqueness
           + idempotency cho retry
~~~

**Cây quyết định là heuristic**. Phải kiểm tra data size, throughput, indexability, security và failure model thực tế.

## 4. Bảng tiêu chí chọn nhúng hay tham chiếu

| Tiêu chí | Nghiêng về nhúng | Nghiêng về tham chiếu |
| --- | --- | --- |
| Truy cập | Luôn đọc cùng parent | Hay truy cập riêng |
| Cardinality | Một hoặc một ít, có hard bound | Rất nhiều hoặc không giới hạn |
| Vòng đời | Tạo/xóa cùng parent | Có lifecycle riêng |
| Ghi | Cập nhật cùng parent | Ghi độc lập, thường xuyên |
| Chủ sở hữu | Một aggregate owner | Nhiều owners/services |
| Thay đổi master | Snapshot bất biến hoặc ít đổi | Dữ liệu hiện hành đổi thường xuyên |
| Bảo mật | Cùng mức phân quyền | Quyền truy cập khác |
| Retention | Cùng chính sách lưu | Khác retention/audit |
| Kích thước | Dưới giới hạn có headroom | Dễ tăng lớn theo thời gian |
| Truy vấn ngược | Ít hoặc được index tốt | Thường tìm child xuyên parents |
| Khả năng phân trang | Không cần phân trang child | Child có feed/page riêng |
| Concurrency | Ít writers cạnh tranh | Một parent dễ trở thành hotspot |

### 4.1. Trường hợp đặc biệt: vừa reference vừa snapshot

Một order có productId tham chiếu product master, đồng thời có itemSnapshot.name và itemSnapshot.priceMinor. Khi product đổi tên hoặc giá, đơn cũ vẫn cần hiển thị điều đã thỏa thuận.

### 4.2. Một document vẫn có giới hạn

Một BSON document thông thường có giới hạn **16 MiB**. Đừng dùng 16 MiB như kích thước mục tiêu; cần headroom cho các updates sau, index entries và traffic.

### 4.3. Bounded phải có giới hạn thật

“Trung bình chỉ ba comments” không phải một bound nếu một bài viết có thể nhận 100.000 comments. Cần hard business cap hoặc chọn collection riêng.

## 5. Ví dụ 1:N: order và orderItems

Relational model:

~~~text
orders
  id, customer_id, status, total

order_items
  order_id, product_id, qty, unit_price
~~~

Nếu mỗi đơn có số dòng hàng nhỏ, vòng đời giống nhau, mô hình nhúng:

~~~javascript
{
  _id: "order-101",
  tenantId: "tenant-a",
  customerId: "customer-15",
  status: "DRAFT",
  items: [
    {
      lineId: "line-1",
      productId: "product-8",
      productNameSnapshot: "Sổ tay",
      qty: 2,
      unitPriceMinor: NumberLong(50000)
    },
    {
      lineId: "line-2",
      productId: "product-12",
      productNameSnapshot: "Bút",
      qty: 1,
      unitPriceMinor: NumberLong(10000)
    }
  ],
  totalMinor: NumberLong(110000),
  version: 1,
  schemaVersion: 1
}
~~~

### 5.1. Lợi ích

Một lần đọc order chứa các dòng hàng cần cho màn chi tiết; đơn giá lịch sử không bị đổi khi product master thay đổi.

### 5.2. Giới hạn

Nếu orderItems là feed khổng lồ, có lifecycle riêng hoặc truy vấn ngược theo line items chiếm phần lớn workload, cần đánh giá collection tách.

### 5.3. Invariant totalMinor

Nếu thay items và total, việc update cùng document có thể atomic. Nhưng **atomic không tự bảo đảm phép tính đúng**: application vẫn phải kiểm tra total = sum(qty × unitPriceMinor), overflow và currency.

### 5.4. Không dùng $push vô hạn

Một shopping cart/aggregated log có thể tăng mãi nếu không giới hạn. Dùng bounded history, tách collection, hoặc bucket pattern khi phù hợp.

## 6. Ví dụ nhúng document con nhỏ

Một địa chỉ giao hàng tại thời điểm đặt:

~~~javascript
{
  _id: "order-102",
  shippingAddressSnapshot: {
    recipient: "Khách hàng Mẫu",
    city: "Hà Nội",
    postalCode: "100000"
  }
}
~~~

### 6.1. Snapshot và master address khác nhau

Khách đổi địa chỉ hồ sơ không nên vô tình đổi thông tin giao hàng của đơn đang xử lý nếu nghiệp vụ cần giữ lịch sử.

### 6.2. PII

Chỉ snapshot fields cần thiết và có chính sách retention/redaction. Không lấy toàn bộ hồ sơ khách hàng để nhúng vào hàng nghìn orders.

### 6.3. Security

Một API quản trị cần status nhưng không có quyền xem địa chỉ không nên nhận raw document; dùng DTO/projection và authorization.

## 7. Khi tham chiếu là lựa chọn tốt hơn

Ví dụ khách hàng có nhiều orders trong nhiều năm:

~~~javascript
// customers
{
  _id: "customer-15",
  tenantId: "tenant-a",
  displayName: "Khách hàng Mẫu",
  updatedAt: ISODate("2026-01-15T00:00:00Z")
}

// orders
{
  _id: "order-101",
  tenantId: "tenant-a",
  customerId: "customer-15",
  createdAt: ISODate("2026-01-16T00:00:00Z"),
  totalMinor: NumberLong(110000)
}
~~~

Truy vấn lịch sử:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  customerId: "customer-15"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 7.1. Index candidate

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

### 7.2. Vì sao không nhúng orders vào customer?

Lịch sử không có giới hạn và cần phân trang. Customer document sẽ tăng liên tục và trở thành contention point cho mọi đơn mới.

### 7.3. Referential integrity

MongoDB không tự cung cấp foreign-key constraints giữa những collections theo cách RDBMS điển hình. Application, workflows và reconciliation phải giữ các references hợp lệ theo contract.

## 8. Bảng cardinality

| Quan hệ | Mô hình gợi ý | Cần lưu ý |
| --- | --- | --- |
| 1:1 profile settings, cùng lifecycle | Nhúng | Phân quyền/độc lập ghi |
| 1:few phones, bounded | Nhúng hoặc reference | Dữ liệu nhạy cảm |
| 1:few order items | Nhúng | Item cap và snapshot giá |
| 1:many bookings/customer | Reference | Pagination/index |
| 1:huge logs/device | Collection riêng/bucket | Growth/TTL/time-series |
| Many:many user-role | Bounded IDs hoặc mapping collection | Role ownership/expiry |
| Many:many courses-students | Association collection nếu quan hệ có fields | Truy vấn hai chiều |
| 1:huge comments/post | Reference + comment collection | Hot post |
| 1:few addresses | Có thể nhúng | Search và quyền chỉnh sửa |
| Events/audit history | Append-only collection | Retention, immutable semantics |

### 8.1. Một mối quan hệ có thể có nhiều representations

Một product có canonical catalog record; order item chứa snapshot; search index chứa derived description. Không coi đó là ba nguồn sự thật.

### 8.2. Nên dokument hóa lựa chọn

Với mỗi quan hệ, ghi cardinality max, access frequency, update frequency, data owner, source of truth và policy khi reference bị xóa.

## 9. Nhúng quá nhiều và các mẫu thay thế

### 9.1. Unbounded array anti-pattern

~~~javascript
{
  _id: "user-1",
  allOrdersEver: [
    // potentially millions
  ]
}
~~~

Rủi ro: 16 MiB, write contention, oversized document, khó phân trang, khó lưu trữ/archive.

### 9.2. Subset pattern

Nhúng chỉ vài items gần đây:

~~~javascript
{
  _id: "user-1",
  recentOrderSummaries: [
    { orderId: "o-100", createdAt: ISODate("2026-01-15T00:00:00Z") },
    { orderId: "o-099", createdAt: ISODate("2026-01-14T00:00:00Z") }
  ]
}
~~~

Toàn bộ orders ở collection riêng. recentOrderSummaries là derived data, phải có cơ chế cập nhật và giới hạn kích thước.

### 9.3. Bucket pattern

Với measurements/events đều đặn, có thể gom một số records vào buckets theo thời gian/thiết bị. Cần quản lý kích thước bucket và phân biệt khi dùng MongoDB time-series collections.

### 9.4. Outlier pattern

Nếu phần lớn accounts có vài child nhưng một số account có cực nhiều, không ép tất cả vào một layout không bounded. Có thể giữ common subset nhúng và tách phần lịch sử vượt giới hạn, với reader hiểu cả hai nguồn.

## 10. $lookup và application composition

Reference không nhất thiết tạo N+1 requests nếu dùng aggregation phù hợp hoặc batched lookups.

Ví dụ join orders với customer hiện tại:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      _id: "order-101"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId",
        tenantKey: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$customerKey"] },
                { $eq: ["$tenantId", "$$tenantKey"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 0,
            displayName: 1
          }
        }
      ],
      as: "currentCustomer"
    }
  }
]);
~~~

### 10.1. Khi nào dùng?

Khi API cần thông tin customer hiện tại và query frequency/size cho phép. Trường hợp chỉ cần display name lúc đặt, snapshot trong order có thể tốt hơn.

### 10.2. $lookup không tự bảo đảm authorization

Phải tenant-aware, đặc biệt khi business IDs trùng giữa tenants. Không tin client tự truyền tenantId mà không có xác thực.

### 10.3. Tối ưu theo phép đo

Dùng indexes ở collection được join, explain và p95 API. $lookup có thể hợp lý cho query hiếm nhưng không tối ưu cho feed nhiều documents.

## 11. Bảng chọn thao tác ghi trên một document

| Yêu cầu | Operator/API | Thuộc tính |
| --- | --- | --- |
| Đặt hoặc đổi một field | $set | Atomic trong một document |
| Xóa một field | $unset | Atomic trong một document |
| Tăng/giảm số lượng | $inc | Không cần đọc rồi ghi |
| Chỉ giữ giá trị lớn/nhỏ theo điều kiện | $max / $min | Cập nhật có điều kiện theo giá trị |
| Cập nhật thời điểm server | $currentDate | Dùng server clock |
| Thêm một phần tử vào array | $push | Cần kiểm soát growth |
| Thêm phần tử nếu chưa bằng giá trị đã có | $addToSet | Không thay unique business keys |
| Xóa phần tử array | $pull | Một document atomic |
| Đặt fields khi insert trong upsert | $setOnInsert | Không sửa fields đó khi match existing |
| Nhiều thay đổi trên cùng document | $set + $inc + $currentDate | Một updateOne atomic |
| Tìm và cập nhật rồi lấy bản ghi | findOneAndUpdate | Có thể chọn BEFORE/AFTER |
| Ghi theo version | filter version + $inc version | Optimistic concurrency |

### 11.1. Atomicity scope

Một lệnh updateOne trên một document là atomic. Một lệnh updateMany thay nhiều documents **không atomic như một khối thống nhất**: từng document update atomic nhưng giữa các documents có thể quan sát trạng thái từng phần.

### 11.2. Không phải operator nào cũng bảo vệ business invariant

$push thêm item atomic, nhưng nếu không giới hạn mảng thì vẫn gây unbounded growth. $inc trừ tồn kho atomic, nhưng nếu không có filter số lượng thì có thể tạo stock âm.

## 12. Lost update: đọc rồi ghi là nguy hiểm

Hai requests cùng đọc quantity = 10:

~~~text
Request A reads quantity=10
Request B reads quantity=10

A computes 10+1 and writes 11
B computes 10+1 and writes 11

Expected after two increments: 12
Observed with naive read-modify-write: 11
~~~

Giải pháp atomic:

~~~javascript
db.counters.updateOne(
  { _id: "views:article-1" },
  { $inc: { value: 1 } }
);
~~~

### 12.1. $inc tránh lost increments

Khi mỗi request dùng atomic $inc, hai successful increments sẽ tăng tổng cộng 2 theo server semantics.

### 12.2. Retry vẫn cần xem semantics

Nếu client timeout không biết write đã chạy hay chưa, tự retry business operation theo cách không idempotent có thể tăng thêm lần nữa. Driver retryable write/operation IDs giúp ở phạm vi hỗ trợ, nhưng ứng dụng cần hiểu result ambiguity và idempotency.

### 12.3. Hot counter

Một document bị update liên tục bởi quá nhiều workers có thể tạo contention. Có thể dùng sharded counters hoặc event aggregation khi business chấp nhận eventual counts, với trade-off về reads.

## 13. Giảm tồn kho có điều kiện trong một document

Giả sử product có available = 10 và cần đặt 3 sản phẩm:

~~~javascript
db.inventory.updateOne(
  {
    _id: "tenant-a:product-1",
    tenantId: "tenant-a",
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: -3,
      reserved: 3
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

### 13.1. Vì sao predicate nằm trong update?

Nếu chỉ đọc available >= 3 trước rồi thực hiện update không điều kiện, hai requests có thể đồng thời thấy đủ rồi trừ khiến stock âm.

### 13.2. matchedCount là tín hiệu nghiệp vụ

- matchedCount = 1: một document thỏa điều kiện và được đưa vào update.
- matchedCount = 0: document không tồn tại, sai tenant hoặc không đủ stock.

Cần phân biệt lỗi cho người dùng bằng truy vấn bổ sung nếu nghiệp vụ cần, nhưng không để truy vấn bổ sung thay atomic predicate.

### 13.3. Một document vẫn chưa phải một order hoàn chỉnh

Thao tác stock có thể thành công nhưng insert order thất bại nếu hai bước không cùng transaction/workflow. Cần xem invariant giữa inventory và orders ở các mục tiếp theo.

## 14. Atomic update nhiều fields với $inc và $set

Ví dụ chuyển trạng thái đơn từ DRAFT sang SUBMITTED:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "tenant-a",
    status: "DRAFT"
  },
  {
    $set: {
      status: "SUBMITTED"
    },
    $inc: {
      version: 1
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

### 14.1. Conditional state transition

Nếu request khác đã CANCEL order, update có filter status DRAFT sẽ không match. Điều kiện giúp bảo vệ state machine.

### 14.2. Nếu không có precondition?

Một update status vô điều kiện có thể cho phép chuyển trạng thái trái luật, dù bản thân write atomic.

### 14.3. Không cần multi-document transaction cho một write duy nhất

Nếu toàn bộ invariant nằm trong document order, updateOne là đủ. Bọc thêm transaction thường không đem lại atomicity quan trọng mới cho thao tác đơn này.

## 15. Optimistic locking bằng version

Document:

~~~javascript
{
  _id: "profile-1",
  tenantId: "tenant-a",
  displayName: "A",
  version: 7
}
~~~

Client/service đọc version=7 rồi muốn đổi displayName:

~~~javascript
db.profiles.updateOne(
  {
    _id: "profile-1",
    tenantId: "tenant-a",
    version: 7
  },
  {
    $set: {
      displayName: "B"
    },
    $inc: {
      version: 1
    }
  }
);
~~~

### 15.1. Kết quả

Nếu matchedCount=1, update thành công và version thành 8. Nếu matchedCount=0, có thể record đã bị sửa, xóa hoặc sai scope; cần báo conflict/not found theo nghiệp vụ.

### 15.2. Version không thay thế validation

Dù không có lost update, giá trị displayName vẫn phải được kiểm tra đúng schema/quyền.

### 15.3. Retry an toàn

Khi conflict, application có thể load lại và cho người dùng quyết định merge, không tự ghi đè tất cả fields từ snapshot cũ.

## 16. findOneAndUpdate để lấy document đúng thời điểm

Một số luồng cần đồng thời claim một task và lấy task được claim:

~~~javascript
db.jobs.findOneAndUpdate(
  {
    status: "PENDING",
    availableAt: {
      $lte: ISODate("2026-01-15T12:00:00Z")
    }
  },
  {
    $set: {
      status: "RUNNING",
      workerId: "worker-1"
    },
    $currentDate: {
      claimedAt: true
    }
  },
  {
    sort: {
      availableAt: 1,
      _id: 1
    },
    returnDocument: "after"
  }
);
~~~

### 16.1. Atomic claim

Một worker claim một document; các workers khác không thể cùng match status=PENDING trên document đó sau khi nó được chuyển RUNNING, nếu filter và write được áp dụng đúng.

### 16.2. Lease và recovery

Nếu worker chết, job có thể kẹt RUNNING. Trong thiết kế thực tế cần leaseExpiresAt, heartbeat/renewal hoặc recovery policy; không chỉ có một status flag.

### 16.3. Không dùng query rồi update riêng để claim

Đọc một pending job sau đó mới update không điều kiện dễ bị hai workers chọn cùng job.

## 17. Cập nhật mảng: $push, $addToSet, $pull

~~~javascript
// Append an item:
db.orders.updateOne(
  { _id: "order-101", status: "DRAFT" },
  {
    $push: {
      notes: {
        by: "staff-1",
        text: "Cần xác nhận"
      }
    }
  }
);

// Add a unique primitive tag:
db.orders.updateOne(
  { _id: "order-101" },
  {
    $addToSet: {
      tags: "priority"
    }
  }
);

// Remove a matching embedded item:
db.orders.updateOne(
  { _id: "order-101", status: "DRAFT" },
  {
    $pull: {
      items: { lineId: "line-2" }
    }
  }
);
~~~

### 17.1. $addToSet không thay unique index

Nó tránh thêm phần tử trùng theo giá trị so sánh BSON của array trong cùng document, không kiểm soát business uniqueness xuyên nhiều documents hoặc biến thể normalization của field.

### 17.2. Atomic không đồng nghĩa tổng tiền tự khớp

Xóa một line item bằng $pull mà không cập nhật totalMinor theo đúng business rule có thể để lại dữ liệu sai. Nên tính tổng trong cùng atomic update khi có thể hoặc dùng workflow giữ invariant rõ.

### 17.3. Mảng tăng vô hạn

$push liên tục vào auditTrail/comments/history mà không có giới hạn sẽ làm document phình. Chọn collection riêng hoặc giới hạn subset.

## 18. Sửa phần tử mảng theo điều kiện

Ví dụ cập nhật một line item có lineId cụ thể bằng arrayFilters:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "tenant-a",
    status: "DRAFT"
  },
  {
    $set: {
      "items.$[line].qty": 3
    }
  },
  {
    arrayFilters: [
      { "line.lineId": "line-1" }
    ]
  }
);
~~~

### 18.1. Quy tắc một document

Một updateOne vẫn atomic trong order document; phần tử nào bị sửa được điều khiển bởi arrayFilters.

### 18.2. Định nghĩa lineId ổn định

Không dựa vào array position nếu users có thể xóa/sắp xếp items. Dùng stable line IDs giúp tránh sửa nhầm.

### 18.3. Invariant total

Nếu qty thay đổi, totalMinor phải phản ánh thay đổi trong cùng business operation. Không nên cho một update qty và một update total rời rạc có thể lỗi nửa chừng.

## 19. Update pipeline khi field mới phụ thuộc field cũ

MongoDB hỗ trợ update bằng aggregation pipeline trong những phiên bản và operators tương thích.

Ví dụ làm mới updatedAt và computed field dựa trên giá trị hiện có:

~~~javascript
db.inventory.updateOne(
  {
    _id: "tenant-a:product-1",
    tenantId: "tenant-a",
    available: { $gte: 3 }
  },
  [
    {
      $set: {
        available: {
          $subtract: ["$available", 3]
        },
        reserved: {
          $add: [
            { $ifNull: ["$reserved", 0] },
            3
          ]
        },
        updatedAt: "$$NOW"
      }
    }
  ]
);
~~~

### 19.1. Pipeline và operator update khác cú pháp

Update pipeline dùng các aggregation expressions; không thể tự động dùng mọi update operator trong pipeline như một modifier document.

### 19.2. Atomicity vẫn ở cấp một document

Pipeline updateOne là atomic với một document. Nếu updateMany, từng document atomic nhưng toàn lệnh không thành một giao dịch all-or-nothing.

### 19.3. Kiểu số

Nếu dữ liệu bị trộn string/number hoặc reserved missing, expression phải có policy rõ. Dữ liệu mẫu dùng Int32 và NumberLong tùy schema; phép toán tiền có thể cần Decimal128.

## 20. Upsert: tính nguyên tử và uniqueness

Một upsert có thể update record hiện tại hoặc tạo record mới:

~~~javascript
db.productSettings.updateOne(
  {
    tenantId: "tenant-a",
    productId: "product-1"
  },
  {
    $set: {
      reorderThreshold: 5
    },
    $setOnInsert: {
      createdBy: "system"
    }
  },
  {
    upsert: true
  }
);
~~~

### 20.1. Unique index cho business key

~~~javascript
db.productSettings.createIndex(
  {
    tenantId: 1,
    productId: 1
  },
  { unique: true }
);
~~~

Nếu không có unique constraint phù hợp, concurrent upserts có thể tạo duplicate business records trong một số tình huống.

### 20.2. Không assume upsertedId luôn có

Khi match existing record, upsertedId có thể null. Kiểm tra matchedCount/modifiedCount/upsertedId theo semantics API.

### 20.3. Upsert không thay giao dịch nhiều documents

Nó không bảo vệ write vào collection khác, không tự ngăn orphan references.

## 21. Khi nào cần multi-document transaction?

Một transaction hữu ích khi **một business invariant yêu cầu nhiều writes được commit/abort cùng nhau**.

Ví dụ tạo một reservation:

~~~text
Read inventory for product-1
Decrement available stock
Create one order
Persist related reservation state

Expected:
  Either all required MongoDB writes commit
  Or none of them commit
~~~

Nếu stock và order ở hai documents, conditional update riêng lẻ không bảo đảm commit của cả hai nếu lệnh thứ hai thất bại.

### 21.1. Bảng ngưỡng cần transaction

| Câu hỏi | Nếu trả lời Có | Hướng |
| --- | --- | --- |
| Các field cùng một document? | Có | UpdateOne/conditional update |
| Ghi xuyên nhiều documents? | Có | Xem yêu cầu consistency |
| Có thể chấp nhận trạng thái tạm lệch? | Có | Outbox/events/saga có thể phù hợp |
| Không thể chấp nhận partial commit? | Có | Transaction hoặc redesign boundary |
| Có external API/email? | Có | Transaction DB không bao trùm |
| Giao dịch dài nhiều phút? | Có | Tránh long-running DB transaction; state machine |
| Có hot contention? | Có | Kiểm soát conflict, retries và throughput |
| Deployment là standalone? | Có | Multi-document transactions không hỗ trợ như replica set/sharded |

### 21.2. Giao dịch không phải biện pháp phân phối tải

Nhiều transactions kéo dài có thể tạo conflicts, tăng tài nguyên và replication overhead.

### 21.3. Giao dịch không sửa được mô hình bất hợp lý

Một customer chứa hàng triệu bookings vẫn không tốt chỉ vì writes được bọc transaction.

## 22. Ba mức consistency cần phân biệt

1. **Single-document atomicity:** một write cập nhật một document là all-or-nothing trên document đó.
2. **Multi-document transaction atomicity:** một tập thao tác trong transaction commit/abort cùng nhau.
3. **End-to-end business consistency:** cả DB, queue, external payment, email, cache và các process khác đạt invariant theo hợp đồng.

Không được lấy mức 1 hoặc 2 để mặc nhiên suy ra mức 3.

### 22.1. Read concern và write concern cũng quan trọng

Transaction có thể có readConcern/writeConcern phù hợp để đáp ứng consistency/durability cần thiết. Không trộn lẫn khái niệm transaction atomicity với độ bền của commit sau failover.

### 22.2. Eventual consistency có thể chấp nhận

Với email thông báo, dashboard hoặc search index, trạng thái cập nhật sau vài giây có thể hợp lệ. Thay vì transaction dài, dùng durable outbox và reconcile.

### 22.3. Business invariant không chấp nhận tạm lệch

Số dư kế toán, giới hạn tồn kho và đặt thuê không trùng cần thiết kế quyết định rõ. Tùy implementation có thể dùng một document contention point, unique slot keys, transaction và idempotency.

## 23. MongoDB transaction lifecycle

~~~text
Start client session
         |
         v
Start transaction
         |
         v
Read / write operations using SAME session
         |
         v
Business preconditions hold?
   |                 |
  Yes               No
   |                 |
   v                 v
Commit           Abort
   |
   v
Commit acknowledged under chosen concerns
   |
   v
Return result / publish downstream events
~~~

### 23.1. Session là bắt buộc cho transaction operations

Các operations phải truyền **cùng ClientSession** tương ứng. Một write bị quên session có thể chạy ngoài transaction, phá tính all-or-nothing mong đợi.

### 23.2. Trạng thái unknown commit result

Timeout hoặc network error trong quá trình commit có thể khiến client chưa biết transaction đã commit hay chưa. Không tự suy từ timeout rằng chưa có thay đổi.

### 23.3. Recovery

Dùng transaction retry patterns/driver support đúng version và kiểm tra idempotency ở tầng business; retry toàn bộ operation có external side effects không an toàn.

## 24. Ví dụ multi-document transaction bằng mongosh

**Chỉ chạy trong replica set/sharded MongoDB test deployment hỗ trợ transactions, với dữ liệu lab thích hợp.** Ví dụ minh họa transaction hai documents và conditional stock decrement.

~~~javascript
const session = db.getMongo().startSession();

const lab = session.getDatabase("mongo_decision_lab");
const inventory = lab.getCollection("inventory");
const orders = lab.getCollection("orders");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const qty = 2;
  const result = inventory.updateOne(
    {
      _id: "tenant-a:product-1",
      tenantId: "tenant-a",
      available: { $gte: qty }
    },
    {
      $inc: {
        available: -qty,
        reserved: qty
      }
    }
  );

  if (result.matchedCount !== 1) {
    throw new Error("Insufficient stock or missing item");
  }

  orders.insertOne({
    _id: "tenant-a:order:reservation-001",
    tenantId: "tenant-a",
    productId: "tenant-a:product-1",
    quantity: qty,
    status: "RESERVED"
  });

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (_) {
    // Commit may already have completed or session ended.
    // Resolve ambiguous outcomes via durable business ID.
  }

  throw error;
} finally {
  session.endSession();
}
~~~

### 24.1. Đây là ví dụ control flow cơ bản

Trong production, nên dùng driver-recommended transaction callback/retry guidance phù hợp phiên bản. Không coi catch rồi abort sau một commit error là luôn xác định được kết quả.

### 24.2. Dữ liệu phải tồn tại và đúng scope

Document inventory cần sẵn các fields available/reserved đúng numeric type; collection orders và indexes cần có preconditions.

### 24.3. Idempotency là bắt buộc khi có retry ở tầng business

Stable order ID và unique key giúp tìm kết quả đã commit. Không sinh order ID mới mỗi lần khi chưa chắc transaction trước thành công.

### 24.4. Ứng dụng không cần mọi read cùng transaction

Read-only dashboard hoặc một lookup có thể dùng readConcern phù hợp mà không mở transaction nhiều documents.

## 25. Java Sync Driver: conditional atomic update

Ví dụ Java:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class InventoryOps {
    private InventoryOps() {}

    public static boolean reserve(
        MongoCollection<Document> inventory,
        String tenantId,
        String productId,
        int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        UpdateResult result = inventory.updateOne(
            Filters.and(
                Filters.eq("_id", productId),
                Filters.eq("tenantId", tenantId),
                Filters.gte("available", quantity)
            ),
            Updates.combine(
                Updates.inc("available", -quantity),
                Updates.inc("reserved", quantity),
                Updates.currentDate("updatedAt")
            )
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

### 25.1. Tại sao không dùng find rồi update?

Một write với filter available>=quantity kiểm tra precondition khi thực hiện update, không dựa vào snapshot cũ từ application.

### 25.2. Tại sao kiểm tra quantity>0?

Nếu quantity âm, phép trừ tồn kho có thể thành cộng. Atomicity không thay business input validation.

### 25.3. Điều gì còn thiếu?

Hàm chỉ update một inventory document. Nếu còn tạo order ở collection khác, cần transaction hoặc workflow xử lý partial state.

## 26. Java Sync Driver: multi-document transaction

Ví dụ tối giản, giả định MongoClient của ứng dụng được tái sử dụng, topology test hỗ trợ transactions và có indexes/fixture hợp lệ:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class CheckoutService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;

    public CheckoutService(
        MongoClient client,
        MongoCollection<Document> inventory,
        MongoCollection<Document> orders
    ) {
        this.client = client;
        this.inventory = inventory;
        this.orders = orders;
    }

    public void reserveAndCreateOrder(
        String tenantId,
        String productId,
        String orderId,
        int qty
    ) {
        if (qty <= 0) {
            throw new IllegalArgumentException(
                "qty must be > 0"
            );
        }

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                UpdateResult stockResult =
                    inventory.updateOne(
                        session,
                        Filters.and(
                            Filters.eq("_id", productId),
                            Filters.eq("tenantId", tenantId),
                            Filters.gte("available", qty)
                        ),
                        Updates.combine(
                            Updates.inc("available", -qty),
                            Updates.inc("reserved", qty)
                        )
                    );

                if (stockResult.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Stock not available"
                    );
                }

                orders.insertOne(
                    session,
                    new Document("_id", orderId)
                        .append("tenantId", tenantId)
                        .append("productId", productId)
                        .append("qty", qty)
                        .append("status", "RESERVED")
                );

                return null;
            });
        }
    }
}
~~~

### 26.1. Cả hai write đều nhận session

Thiếu session ở một trong hai operations sẽ khiến write đó chạy ngoài transaction.

### 26.2. Transaction callback có thể được thực thi lại

Driver có thể retry theo chính sách hỗ trợ, vì vậy không đặt các side effects không-idempotent như charge card, send email hoặc increment một counter ngoài DB trong transaction callback.

### 26.3. Stable orderId

Khi client chưa biết kết quả commit, cần truy vấn theo orderId/idempotency key để xác định outcome; không tạo orderId mới mỗi retry.

### 26.4. Không đảm bảo business uniqueness tự động

Nếu application cho phép orderId khác nhau cho cùng một thao tác thanh toán, transaction không ngăn double-charge. Unique business keys và idempotency vẫn cần.

## 27. Transaction retry, errors và ambiguous outcomes

Các tình huống cần phân biệt:

| Tình huống | Có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Write conflict | Transaction bị abort/retry | Retry theo driver guidance và giới hạn |
| Transient transaction error | Lỗi tạm thời | Retry cả transaction khi an toàn |
| UnknownTransactionCommitResult | Client không chắc commit outcome | Retry commit/resolve theo guidance |
| Duplicate key | Unique index bị vi phạm | Check business key và conflict policy |
| Network timeout | Write/commit có thể đã chạy | Idempotent reconciliation |
| Business validation failed | Không đủ stock, sai trạng thái | Abort và trả lỗi nghiệp vụ |
| Process died after commit | DB có thể đã commit | Reconcile theo stable ID |

### 27.1. Không “retry vô hạn”

Đặt timeout/deadline và backoff phù hợp. Mất kết nối dài hoặc contention cao không nên tạo retry storm.

### 27.2. Không suy from timeout = rollback

Có thể commit đã thành công nhưng phản hồi bị mất. Điều tra bằng durable business identifier.

### 27.3. Lưu error labels và metrics

Retry policies nên dựa vào error class/labels theo API, không so raw error message dài chứa host/time.

## 28. Transaction costs và phạm vi phù hợp

Một transaction nhiều documents có thể làm tăng:

- Network round trips.
- Lock/conflict pressure.
- Resource/time sử dụng cho snapshot.
- Memory/storage pressure ở transaction lớn hoặc kéo dài.
- Độ phức tạp retry/commit uncertainty.
- Latency với cross-shard coordination.
- Tải trên replica set và nghiệp vụ cạnh tranh cao.

### 28.1. Transaction càng ngắn càng tốt

Không giữ transaction mở trong lúc chờ user input, gọi payment provider hoặc xử lý tác vụ dài nhiều phút.

### 28.2. Giới hạn cụ thể phụ thuộc version/config

MongoDB có quy định về lifetime, operations, memory và các trường hợp DDL trong transaction khác nhau theo phiên bản/topology. Kiểm tra tài liệu đúng deployment đang dùng.

### 28.3. Không quy định "mọi thao tác nhiều collections đều cần transaction"

Một append-only audit event có thể được phát sau qua outbox với eventual consistency nếu business cho phép.

## 29. Chọn transaction hay eventual consistency

| Tình huống | Nên cân nhắc | Điều kiện để an toàn |
| --- | --- | --- |
| Order + inventory phải commit cùng nhau | Transaction | Conditional stock update, unique order ID |
| Gửi email sau order | Outbox worker | At-least-once + idempotency |
| Dashboard cập nhật sau order | Derived projection | Lag SLO, replay/reconcile |
| Search index đồng bộ product | Events/read model | Version, ordering, retry |
| Trừ/ghi hai số dư tài khoản | Transaction và ledger invariant | Double-entry, uniqueness, auditing |
| Đồng bộ product name snapshot trong orders cũ | Thường không làm nếu lịch sử bất biến | Data ownership policy |
| Gộp nhiều writes cùng một document | Atomic update | Conditional predicates |
| Batch migrate nhiều documents không cần snapshot all-or-nothing | Idempotent bulk + checkpoints | Resume và reconciliation |
| Hard consistency trong nhiều documents | Transaction hoặc redesign | Scope/timing/constraints |
| Long distributed workflow | Saga/state machine | Compensation và idempotency |

### 29.1. Eventual consistency không phải “không quan tâm dữ liệu”

Nó đòi sự kiện bền vững, retry, dedup, max lag, failure handling và reconciliation.

### 29.2. Transaction không đưa external service vào cùng atomic boundary

Không có MongoDB transaction nào tự hoàn tác một payment capture ở bên thứ ba hoặc email đã gửi.

## 30. Outbox pattern khi có side effects ngoài DB

~~~text
MongoDB transaction or atomic document write
       |
       +-- Update business state
       |
       +-- Insert outbox event (same transaction if separate doc)
       |
       v
Commit
       |
       v
Outbox worker reads pending events
       |
       v
Publish to broker / send message
       |
       v
Mark delivery progress with idempotency
~~~

### 30.1. Vì sao không publish trước commit?

Nếu publish thành công nhưng transaction abort, downstream service có thể hành động trên một order chưa tồn tại.

### 30.2. Vì sao không publish sau commit bằng một call không durable?

Nếu process chết ngay sau commit nhưng trước publish, event có thể bị mất. Outbox lưu ý định gửi trong DB.

### 30.3. Delivery có thể lặp

Worker có thể publish rồi chết trước khi mark sent. Consumer cần idempotency key để xử lý duplicate event.

### 30.4. Transaction chỉ cho hai DB writes nếu outbox là collection riêng

Nếu có thể giữ outbox metadata nhỏ cùng aggregate trong một document, atomic boundary có thể khác; phải xem growth và behavior.

## 31. Saga và quy trình kéo dài

Một workflow đặt thuê xe có thể:

~~~text
Create booking PENDING
      |
      v
Hold vehicle slot
      |
      v
Authorize payment provider
      |
      +-- Success --> Confirm booking
      |
      +-- Failure --> Release hold, mark failed
~~~

### 31.1. Không giữ DB transaction xuyên toàn bộ workflow

Payment provider có thể mất vài giây hoặc nhiều phút, dễ timeout. Dùng state machine và compensation có thể là lựa chọn phù hợp.

### 31.2. Compensation không phải rollback DB thật

Nếu payment đã charge, có thể phải refund, không thể xóa vết để coi như chưa xảy ra. Giữ audit và trạng thái tường minh.

### 31.3. Idempotency ở từng bước

Mỗi action cần stable operation ID và check trạng thái để retries không tạo double reservation hoặc double charge.

## 32. Booking overlap là tình huống đặc biệt

Nếu mỗi booking ở một document, ứng dụng có thể kiểm tra:

~~~text
Existing startAt < requested endAt
AND
Existing endAt > requested startAt
~~~

Ví dụ:

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  vehicleId: "vehicle-1",
  status: {
    $in: ["HELD", "CONFIRMED"]
  },
  startAt: {
    $lt: ISODate("2026-02-15T12:00:00Z")
  },
  endAt: {
    $gt: ISODate("2026-02-14T12:00:00Z")
  }
});
~~~

### 32.1. Query-then-insert không bảo vệ concurrency

Hai requests đồng thời có thể cùng thấy không có booking overlap rồi insert hai documents khác nhau.

### 32.2. Transaction đơn thuần không chắc loại bỏ write skew

Nếu cả hai transactions chỉ đọc sự vắng mặt rồi ghi vào hai docs khác nhau, phải có cơ chế đảm bảo conflict/uniqueness; transaction không tự tạo uniqueness trên các khoảng thời gian bất kỳ.

### 32.3. Các phương án

- Materialize discrete slot keys với unique index theo vehicle+slot.
- Dùng một availability/lock/sequence document chung được cập nhật có điều kiện để tạo write contention.
- Reservation holds với TTL/recovery nhưng phải có uniqueness và time contract đúng.
- Thiết kế slot granularity theo nghiệp vụ: theo ngày không đủ nếu xe có giờ nhận/trả bất kỳ.

### 32.4. Đo business invariant

Không được có hai active bookings overlap cho cùng vehicle theo quy định. Kiểm tra bằng concurrent integration test, không chỉ một test tuần tự.

## 33. Transaction cho transfer tiền: cần thêm ledger

Một ví dụ chuyển 100 từ A sang B:

~~~text
account A balance = 1000
account B balance = 500

Operation:
  Debit A by 100 if balance>=100
  Credit B by 100
  Insert ledger entry with transferId

Invariant:
  A+B balance unchanged by this transfer
  One logical transfer per transferId
~~~

### 33.1. Transaction bảo vệ commit của các changes

Debit, credit và ledger entry cần all-or-nothing nếu business yêu cầu.

### 33.2. Double-entry ledger

Trong hệ thống tài chính thực, nên thiết kế ledger/entries và auditing chuyên nghiệp, không coi hai số dư mutable là nguồn đủ cho accounting.

### 33.3. Stable transferId

Retry sau unknown commit outcome phải tìm transferId đã được xử lý, không phát sinh transfer mới.

### 33.4. Authorization và currency

Không chuyển giữa accounts sai tenant/quyền; cùng loại currency hoặc conversion rules rõ, tránh overflow và floating-point.

## 34. Quan hệ nhiều-một và master data

Với một product thuộc hàng nghìn orders:

~~~text
Product master
  productId, currentName, currentPrice

Orders
  orderId
  productId
  itemSnapshot(nameAtPurchase, unitPriceAtPurchase)
~~~

### 34.1. Master sửa một nơi

Giá hiện tại đổi trong product collection, không fan-out update mọi orders cũ.

### 34.2. History snapshot

Tên/giá lịch sử ở order có thể bất biến. Khi user nhìn đơn cũ, họ thấy thông tin đã thỏa thuận.

### 34.3. Không biến snapshot thành nguồn chính cho catalog

Product search current name cần product master hoặc derived search collection, không quét historical orders.

## 35. Many-to-many và association documents

Ví dụ students và courses hoặc users và roles:

| Bối cảnh | Thiết kế |
| --- | --- |
| User có tối đa 5 role IDs, đọc cùng user | Có thể nhúng roles |
| Enrollment có enrolledAt, grade, status | Association collection |
| Course có hàng trăm nghìn students | Không nhúng tất cả vào course |
| Role metadata thay thường xuyên | Role master + refs |
| Cần tìm mọi users của một role | Index array hoặc association collection theo scale |

### 35.1. Dữ liệu liên kết có thuộc tính riêng

Nếu association có lịch sử/trạng thái/owner riêng, một document liên kết có thể là aggregate thích hợp.

### 35.2. Không bỏ qua query đảo chiều

Nhúng IDs vào user rất thuận khi đọc user roles; nhưng tìm mọi user có role X cần multikey index hoặc mô hình riêng.

## 36. Đặt index theo mô hình dữ liệu

### 36.1. Embedded fields

Có thể index nested path:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  "shippingAddressSnapshot.city": 1
});
~~~

Chỉ tạo khi query thường xuyên lọc theo city; index này cũng có chi phí lưu trữ.

### 36.2. Referenced child collection

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Phục vụ lịch sử khách hàng theo tenant và thời gian.

### 36.3. Unique business keys

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    externalOrderId: 1
  },
  { unique: true }
);
~~~

Bảo vệ uniqueness của externalOrderId theo tenant.

### 36.4. Multikey arrays

Array được index tạo multikey behavior; số index entries có thể tăng theo số phần tử. Một mảng bounded vẫn cần đánh giá nếu có nhiều indexed subfields.

## 37. Index không tự là foreign key hay transaction

| Index | Có thể giúp | Không tự bảo đảm |
| --- | --- | --- |
| Unique index | Một business key không trùng trong phạm vi index | Tài liệu tham chiếu tồn tại |
| Compound index | Lọc và sort hiệu quả hơn | Tất cả updates atomic xuyên docs |
| Partial unique | Uniqueness trên subset theo filter | Uniqueness toàn collection |
| TTL index | Dọn dữ liệu hết hạn bất đồng bộ | Xóa chính xác tại thời điểm hết hạn |
| Multikey | Truy vấn array elements | Array bounded hoặc rules cùng phần tử |
| Shard key index | Routing và distribution theo thiết kế | Mọi query targeted nếu thiếu shard key |

### 37.1. TTL và reservation holds

TTL deletion là background asynchronous process, không phải một lock service xóa holds ngay tại timestamp. Business validity cần kiểm tra expiresAt theo server/application rules, không đợi TTL để quyết định slot có hợp lệ.

### 37.2. Unique index theo interval endpoints

Unique(vehicleId,startAt,endAt) không chặn mọi khoảng overlap. Bảo vệ tính duy nhất của tuple khác với bảo vệ non-overlap interval.

## 38. Read concern, write concern và durability

Khi cần quyết định transaction hoặc atomic update, phải xác định mức nhất quán/durability được yêu cầu.

| Cơ chế | Câu hỏi nó trả lời |
| --- | --- |
| Atomic single-document write | Một document có thể bị update nửa chừng không? |
| Transaction | Nhiều DB writes trong transaction có commit/abort chung không? |
| Write concern | Write được xác nhận bởi bao nhiêu/những loại members và durability mức nào? |
| Read concern | Read có thể nhìn loại snapshot/trạng thái nào? |
| Read preference | Read gửi đến primary hay secondary phù hợp nào? |
| Causal consistency | Các operations liên quan session có thứ tự quan sát thế nào? |

### 38.1. "majority" không phải từ thần kỳ

Write concern `"majority"` có ý nghĩa về acknowledgement, nhưng guarantees chính xác còn phụ thuộc topology, journaling/setting và MongoDB version. Không dùng nó để thay transaction khi operation yêu cầu nhiều documents atomic.

### 38.2. Secondary reads

Read từ secondary có thể stale; nếu cần read-your-writes, thiết kế read preference/session/concern phù hợp.

### 38.3. Atomicity không đồng nghĩa visibility tức thời cho mọi cache

Ngay cả DB đã commit, downstream search index và cache vẫn có thể chưa refresh. Định nghĩa latency contract và reconciliation.

## 39. Multi-tenant design trong các lựa chọn

Mọi read/write cần ràng buộc tenant:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "tenant-a",
    status: "DRAFT"
  },
  {
    $set: {
      status: "SUBMITTED"
    }
  }
);
~~~

### 39.1. TenantId đến từ backend

Không tin tenantId tùy ý trong request payload nếu chưa xác minh quyền.

### 39.2. Các references cũng phải cùng tenant

Order.customerId chỉ hợp lệ nếu customer thuộc tenant được phép; một $lookup chỉ theo customerId có thể lộ dữ liệu xuyên tenant nếu IDs trùng.

### 39.3. Transaction không tự thực thi authorization

Bọc writes trong transaction không ngăn application sửa document tenant khác nếu filter sai.

### 39.4. Snapshot và PII

Nhúng có chủ đích chỉ fields được phép, retention và redaction theo chính sách.

## 40. Hot documents và throughput

Khi nhiều requests cập nhật cùng một document:

~~~text
1000 concurrent viewers
   -> all increment same article.views document
~~~

MongoDB vẫn giữ atomicity theo từng update, nhưng contention, latency và tài nguyên có thể tăng.

### 40.1. Tối ưu không đồng nghĩa bỏ atomicity

Có thể sharded counters hoặc batching nhưng cần xác định accuracy/freshness contract.

### 40.2. Khi nào dùng event aggregation?

Nếu thống kê lượt xem không cần cập nhật ngay đến đơn vị cuối cùng, events/counters per partition và asynchronous sum có thể giảm hotspot.

### 40.3. Khi nào không nên?

Số dư kế toán hoặc số lượng tồn kho cần invariant nghiêm ngặt không nên chuyển sang eventual counter chỉ vì throughput.

## 41. Sharded cluster và transactions

MongoDB hỗ trợ transactions trên các topology/versions phù hợp, bao gồm các trường hợp sharded deployment, nhưng chi phí coordination và hạn chế vận hành khác replica set.

### 41.1. Shard key theo truy vấn

Đưa tenantId vào document không bảo đảm mọi query targeted. Query phải có shard-key predicates đúng để mongos route hiệu quả.

### 41.2. Cross-shard writes

Một transaction chạm nhiều shards có thể tăng latency/coordination overhead. Thiết kế boundaries và shard key cần xem xét workload.

### 41.3. Unique indexes

Sharded collections có quy tắc về unique indexes liên quan shard key theo MongoDB version. Không tự sao chép index từ non-sharded lab sang production sharded.

### 41.4. Không chọn embed để tránh mọi cross-shard transaction

Một document quá lớn/hot có thể còn tệ hơn. Cần đánh đổi locality, cardinality và concurrency.

## 42. Dữ liệu mới, dữ liệu cũ và schema evolution

Một phần dữ liệu được nhúng ban đầu có thể cần tách khi sản phẩm phát triển.

Ví dụ version 1:

~~~javascript
{
  _id: "customer-15",
  orderSummaries: [
    // bounded during early stage
  ],
  schemaVersion: 1
}
~~~

Version 2:

~~~javascript
// customers
{
  _id: "customer-15",
  schemaVersion: 2
}

// orders
{
  _id: "order-101",
  customerId: "customer-15",
  schemaVersion: 2
}
~~~

### 42.1. Expand–migrate–contract

1. Reader hiểu cả v1 và v2.
2. Writer ưu tiên v2.
3. Backfill các documents lịch sử.
4. Reconcile counts/IDs.
5. Loại bỏ legacy fields sau khi không còn clients cần.

### 42.2. Migration idempotent

Chạy lại transform không tạo duplicate orders. Dùng stable IDs, unique business keys và checkpoint.

### 42.3. Không xóa nguồn trước khi xác minh

Đặc biệt với thao tác tách embedded array sang collection, cần so counts/business invariants và có rollback plan.

## 43. Bảng chọn theo quan hệ thực tế

| Miền nghiệp vụ | Quan hệ | Lựa chọn thường tốt | Ghi chú |
| --- | --- | --- | --- |
| E-commerce | Order → orderItems bounded | Embed | Snapshot giá |
| E-commerce | Customer → orders unbounded | Reference | Lịch sử phân trang |
| Catalog | Product → reviews unbounded | Reference | Reviewer identity |
| CMS | Article → tags bounded | Embed | Index multikey nếu search |
| CMS | Article → comments unbounded | Reference | Moderation lifecycle |
| Messaging | Conversation → messages unbounded | Reference | Paging, retention |
| IoT | Device → measurements rất lớn | Separate time-series/buckets | TTL/retention |
| Social | User → followers rất lớn | Association collection | Query hai chiều |
| Booking | Booking → small addons | Embed | Same aggregate |
| Booking | Booking → vehicle current master | Reference + snapshot | Current vs contracted |
| Payments | Payment → event history | Separate append-only | Auditable |
| Finance | Account → ledger entries unbounded | Reference | Ledger source of truth |
| Inventory | Product → available/reserved counters | Atomic update | Conditional predicate |
| Reporting | Daily revenue | Derived read model | Replay/reconcile |
| Search | Full-text index | Search-specific model | Eventual update |
| Work queues | Job status/lease | Atomic claim | Lease recovery |

**Mọi dòng là gợi ý, không phải quy tắc cưỡng bức.** Hệ thống thực cần đo cardinality, transactions, retention và traffic.

## 44. Bảng chọn theo loại write

| Hành động | Cấp dữ liệu | Gợi ý | Lỗi cần tránh |
| --- | --- | --- | --- |
| Đổi một field profile | 1 document | $set | Ghi đè snapshot cũ |
| Đếm lượt xem | 1 document | $inc | Read-modify-write |
| Trừ tồn kho khi đủ | 1 document | Predicate + $inc | Race check-then-write |
| Sửa một item array | 1 document | arrayFilters | Chọn sai item |
| Chốt order và total từ items cùng doc | 1 document | Atomic update/pipeline | Total lệch items |
| Claim job | 1 document | findOneAndUpdate | Hai worker claim |
| Tăng version khi sửa | 1 document | Filter version + $inc | Lost update |
| Cập nhật 1000 profile docs độc lập | Nhiều docs | Bulk/write workflow | Giả định toàn bộ atomic |
| Tạo order và reserve inventory | Nhiều docs | Transaction/workflow | Partial commit |
| Chuyển tiền A → B | Nhiều docs | Transaction + ledger | Retry double charge |
| Ghi outbox sau commit | Nhiều docs | Cùng transaction khi cần | Lost event |
| Email sau commit | External | Outbox/worker | Email trong DB transaction |
| Phân phối read model | Async | Events/reconciliation | Stale view không được kiểm soát |

## 45. Bảng chọn theo consistency requirement

| Điều kiện bắt buộc | Lựa chọn | Điều kiện đi kèm |
| --- | --- | --- |
| Không để stock âm trong một record | Conditional atomic update | Filter available >= qty |
| Không để status chuyển trái luật | Filter current status | State machine |
| Không lost update vào một record | Version predicate | Conflict handling |
| Một document không update dở dang | Single-document write | Có sẵn MongoDB atomicity |
| Nhiều docs phải commit cùng nhau | Transaction | Same session, retry guidance |
| Không xuất hai events nghiệp vụ giống nhau | Unique event ID/idempotency | Consumer dedup |
| Không bỏ mất outbox event sau order commit | Durable outbox trong same DB atomic scope | Relay/retry |
| Read immediately after write | Read/session policy phù hợp | Concern/preference |
| Không duplicate booking theo slot | Unique slot/contended record | Time granularity |
| Dashboard cập nhật trong 5 giây | Eventual projection | Lag monitoring, replay |
| Phải rollback external payment | Compensation/refund workflow | Không phải MongoDB rollback |

### 45.1. Chọn consistency bằng câu hỏi nghiệp vụ

“Dữ liệu phải nhất quán” còn quá chung. Nên viết: “Trong một lần giữ chỗ, không tồn tại hai reservations ACTIVE trên cùng resource-slot”, hoặc “Sau khi write được acknowledge, user đọc lại trạng thái của chính mình phải thấy phiên bản mới”.

### 45.2. Mức mạnh hơn thường có chi phí

Giao dịch xuyên shards, write concern majority, readConcern snapshot và contention point có thể tăng latency/capacity needs. Đánh đổi cần được đo.

## 46. Quy trình 10 câu hỏi trước khi chốt schema

1. **Mẫu đọc chính là gì?** Fields được tải cùng nhau hay riêng?
2. **Mẫu ghi chính là gì?** Một hay nhiều documents?
3. **Cardinality tối đa?** Có unbounded arrays không?
4. **Data owner?** Ai được sửa, lifecycle ra sao?
5. **Historical snapshot hay current master?** Tránh đồng bộ nhầm.
6. **Consistency invariant?** Viết bằng câu có thể test.
7. **Unique/index requirements?** Những khóa nào phải duy nhất?
8. **Tenant/security scope?** Có cross-tenant references không?
9. **Growth/retention?** 16 MiB, write hotspot, history retention?
10. **Failure/retry policy?** Partial commit, ambiguous outcome, external effects?

Nếu chưa trả lời được câu 3, 6 hoặc 10, nên tạm chưa chốt mô hình cho luồng quan trọng.

## 47. Các anti-patterns thường gặp

| Anti-pattern | Vì sao sai | Cách cải thiện |
| --- | --- | --- |
| Mỗi SQL table thành một MongoDB collection y hệt | Vẫn nhiều joins và round trips | Access-pattern-driven boundaries |
| Nhúng tất cả comments vào article | Unbounded array | Separate comments |
| Nhúng cả lịch sử bookings vào customer | Document phình/hot | Reference + pagination |
| Sao chép giá hiện tại vào mọi order cũ rồi sync | Sai lịch sử | Immutable price snapshot |
| Quên cập nhật fields denormalized | Drift | Canonical owner + event/reconcile |
| Đọc stock rồi ghi số mới | Lost update | Predicate + $inc |
| Update stock không check available | Có thể âm | Atomic conditional filter |
| updateMany được tưởng all-or-nothing | Partial state có thể thấy | Transaction nếu cần |
| findOne rồi update claim job | Hai workers có thể claim | findOneAndUpdate |
| Dùng $addToSet thay unique index toàn tập | Không bảo vệ xuyên docs | Unique business index |
| $push logs mãi vào parent | 16 MiB/growth | Separate history |
| Dùng transaction cho mọi updateOne | Overhead | Atomic update |
| Transaction kéo dài chờ payment | Timeouts/contention | Saga/state machine |
| Gửi email trong transaction callback | Retry tạo trùng emails | Outbox |
| Unknown commit outcome được coi abort | Duplicate retry | Idempotent reconciliation |
| Dùng transaction để ngăn interval overlap nhưng không có contention | Write skew | Unique slots/shared write |
| Giảm write concern để bỏ timeout | Durability risk | Chẩn đoán lag và workload |
| Đọc secondary và luôn đòi current state | Stale reads | Read strategy phù hợp |
| Một index cho mọi quan hệ | Query plan kém | Workload-specific indexes |
| Quên tenant filter | Data leak | Trusted scope |
| Chuyển money sang Double | Precision loss | Minor units/Decimal128 |
| Transaction bảo đảm email rollback | Không đúng | Compensation |
| Schema migration tạo random IDs | Duplicate records | Stable IDs |
| Chỉ đo latency đọc | Bỏ write/index cost | Full workload metrics |

## 48. Ma trận đánh giá rủi ro trước khi đổi lựa chọn

| Thay đổi | Dữ liệu bị ảnh hưởng | Rủi ro chính | Điều cần đo/xác minh |
| --- | --- | --- | --- |
| Embed child collection vào parent | Schema shape | Oversized docs, data loss | Count/cardinality/size |
| Reference từ embedded array | Query path | N+1 reads, orphan refs | Indexes, integrity |
| Thêm snapshot field | Dữ liệu lặp | Staleness/PII | Ownership, retention |
| Chuyển read-modify-write thành $inc | Concurrency | Retry duplicates | Counter invariant |
| Thêm optimistic locking | API conflict behavior | More retries | Conflict rate |
| Thêm transaction | Write path | Latency/conflicts | p95/abort/lag |
| Chuyển transaction sang saga | Consistency model | Partial states | Compensation coverage |
| Thêm outbox | Event delivery | Duplicate processing | Dedup/replay/lag |
| Thêm unique index | Writes & data quality | Existing duplicates | Data cleanup/index build |
| Thêm TTL | Retention | Async deletion | Business expiry logic |
| Chuyển sang sharding | Routing, unique constraints | Scatter-gather, hotspot | Shard-key analysis |

### 48.1. Không đổi nhiều biến cùng lúc

Nếu vừa tách collection, đổi IDs, thay consistency và shard key, việc rollback/truy vết khó hơn. Chia migration thành phases có evidence.

### 48.2. Tính tới dữ liệu đã ghi

Sau khi application dùng schema mới và ghi thêm, rollback binary cũ có thể không đọc được. Reader compatibility, dual-schema và forward fix cần được chuẩn bị.

## 49. Các bài toán thực hành chọn đúng mô hình

### Bài 1 — Danh sách địa chỉ

Một customer có tối đa 3 địa chỉ, thường xem cùng profile, nhưng PII cần phân quyền. Chọn embed hay reference? Nêu trường hợp phải tách dù bounded.

### Bài 2 — Hàng triệu messages

Một conversation có hàng triệu messages và cần infinite scroll. Vì sao không nhúng tất cả trong conversation? Thiết kế index phân trang.

### Bài 3 — Order items

Một order có tối đa 10 items, giá cố định khi mua. Thiết kế document snapshot và invariant total.

### Bài 4 — Customer master

Tên khách đổi. Phân biệt dữ liệu current profile với name snapshot trong order cũ.

### Bài 5 — Follower graph

Một tài khoản có hàng triệu followers, query theo cả hai chiều. Chọn association collection hay embedded IDs?

### Bài 6 — Device telemetry

100 measurements/giây/device, retention 30 ngày. So một mảng trong device document với time-series/bucket collection.

### Bài 7 — Small tags

Một article có tối đa 8 tags, cần tìm articles theo tag. Có thể nhúng tags và index ra sao?

## 50. Bài tập về nguyên tử và concurrency

### Bài 8 — Lost update

Hai requests đọc counter=10 và cùng ghi 11. Viết cách dùng $inc để nhận 12.

### Bài 9 — Stock condition

Product available=4, hai requests muốn reserve qty=3. Thiết kế filter/update và expected number of successful reservations.

### Bài 10 — State transition

Order DRAFT có thể SUBMIT hoặc CANCEL, nhưng không thể SUBMIT sau CANCEL. Viết conditional update.

### Bài 11 — Optimistic lock

Một profile version=5, hai clients cùng sửa. Thiết kế conflict detection.

### Bài 12 — Array update

Chỉ sửa lineId=line-7 trong items, không dùng array index. Viết arrayFilters.

### Bài 13 — Job claiming

Hai workers cùng tìm PENDING job. Dùng findOneAndUpdate, lease và recovery policy thế nào?

### Bài 14 — Upsert

Concurrent requests cùng tạo tenantId+productId config. Tại sao cần unique index?

### Bài 15 — updateMany

Một bulk status update giữa 1.000 documents bị lỗi giữa chừng. Có được giả định toàn bộ rollback không? Khi nào cần transaction?

## 51. Bài tập transaction và eventual consistency

### Bài 16 — Order + stock

Tạo order và trừ stock ở hai collections. Viết transaction concept và mô tả retry idempotency.

### Bài 17 — Payment capture

DB transaction commit nhưng call payment provider thất bại. MongoDB có rollback payment provider không? Thiết kế saga/outbox.

### Bài 18 — Unknown commit result

Client timeout khi commit. Vì sao không tạo một orderId mới để thử lại? Cách reconcile với stable orderId?

### Bài 19 — Booking overlap

Hai requests cùng query không có overlap rồi insert. Vì sao transaction thông thường chưa chắc đủ? Đề xuất slot key hoặc contention document.

### Bài 20 — Ledger transfer

Chuyển tiền giữa hai accounts cần cập nhật số dư và ledger. Viết invariants và idempotency key.

### Bài 21 — Dashboard

Doanh thu dailyRevenue cập nhật trễ 2 giây. Khi nào eventual consistency được chấp nhận? Cần những metrics và replay safeguards nào?

### Bài 22 — Outbox duplicate

Outbox worker publish xong thì crash trước khi mark sent. Vì sao consumer cần idempotency?

### Bài 23 — Retry storm

Một transaction gặp write conflicts nhiều lần. Đặt deadline/backoff và fallback/alert như thế nào?

## 52. Bài tập tổng hợp theo scenario

### Bài 24 — Booking aggregate

Thiết kế booking document có addons, customer/vehicle snapshots, references và một payment ledger riêng. Vẽ consistency boundary.

### Bài 25 — Điểm nóng

Một article có 20.000 updates/giây vào views counter. Khi nào cân nhắc sharded counter/event aggregation thay vì một document?

### Bài 26 — Retention

Lịch sử notifications cần giữ 90 ngày, user profile giữ lâu dài. Có nên nhúng notifications vào user document?

### Bài 27 — Quyền truy cập

Một order thuộc tenant-a nhưng customerId trùng business ID của tenant-b. Thiết kế lookup và validation chống leak.

### Bài 28 — Migration

Tách customer.orderSummaries sang orders collection, bảo đảm stable IDs, backfill idempotency và reader compatibility.

### Bài 29 — Sharding

TenantId được dùng làm shard-key component nhưng một tenant có 70% writes. Điều gì phải đánh giá trước khi chọn key?

### Bài 30 — Trade-off report

Một thiết kế mới giảm read p95 40% nhưng tăng write p95 25% và storage 30%. Dựa trên workload và SLO, đề xuất quyết định có điều kiện.

## 53. Gợi ý đáp án để tự đối chiếu

Đây là **hướng giải**, không phải các lời giải duy nhất:

| Bài | Gợi ý cốt lõi |
| --- | --- |
| 1 | Embed nếu cùng quyền/lifecycle; reference nếu PII/access riêng |
| 2 | Messages collection, index conversationId + createdAt + _id |
| 3 | Bounded items + unitPrice snapshot, total invariant |
| 4 | Current master reference khác historical snapshot |
| 5 | Association collection cho unbounded many-to-many |
| 6 | Time-series/partitions/buckets; không nhúng vô hạn |
| 7 | Bounded tags array + multikey index |
| 8 | $inc: {value:1} cho mỗi write thành công |
| 9 | Filter available>=3; chỉ một trong hai writes thành công khi available=4 |
| 10 | Filter status=DRAFT cùng $set status |
| 11 | Filter version=5 + $inc version, conflict nếu match=0 |
| 12 | $set items.$[line].field + arrayFilters |
| 13 | findOneAndUpdate + lease expiry/recovery |
| 14 | Unique(tenantId,productId), handle duplicate |
| 15 | updateMany per-document atomic, không all-or-nothing |
| 16 | Same session transaction và stable order ID |
| 17 | Outbox/saga/compensation, không dùng DB rollback cho API ngoài |
| 18 | Reconcile theo durable orderId khi commit ambiguous |
| 19 | Slot uniqueness hoặc shared contention write |
| 20 | Debit, credit, ledger atomic; unique transferId |
| 21 | Lag SLA, replay, dedup và reconciliation |
| 22 | At-least-once delivery có duplicate |
| 23 | Bounded retry/backoff, metrics/conflict response |
| 24 | Embed bounded addons, refs/snapshots, separate ledger |
| 25 | Hot document; sharded counters với freshness trade-off |
| 26 | Separate notifications với TTL/retention |
| 27 | Tenant-aware references/lookup và trusted tenant auth |
| 28 | Expand–migrate–contract, stable ID, reconciliation |
| 29 | Tenant skew/hotspot, shard targeting, uniqueness |
| 30 | SLO và read/write weighting quyết định trade-off |

## 54. Checklist review trước khi quyết định

### Mô hình dữ liệu

1. Access patterns quan trọng được ghi.
2. Cardinality có max và growth dự báo.
3. Không có unbounded arrays vô ý.
4. Embedded children có cùng lifecycle/owner.
5. Master references và historical snapshots được phân biệt.
6. Derived fields có canonical source và sync policy.
7. Document max size có headroom.
8. Retention/privacy được cân nhắc.
9. Reverse queries có index/plan phù hợp.
10. Tenant access và referential rules rõ.

### Thao tác nguyên tử

11. Không dùng đọc rồi ghi cho increment/decrement.
12. Conditional predicate nằm trong update.
13. Status transition được kiểm tra.
14. Optimistic version dùng khi cần.
15. matchedCount/modifiedCount/upsertedId được hiểu đúng.
16. Mảng nhúng có giới hạn.
17. Cập nhật nested fields không vô tình thay cả subdocument.
18. UpdateMany không bị nhầm all-or-nothing.
19. Retry ambiguity có business ID.
20. Invariant được test dưới concurrency.

### Giao dịch và workflow

21. Tập writes cần commit cùng nhau được nêu rõ.
22. Tất cả transaction ops dùng cùng session.
23. Deployment hỗ trợ transactions.
24. Read/write concerns phù hợp.
25. Transaction ngắn và có timeout/retry strategy.
26. External side effects ở ngoài transaction DB.
27. Outbox/saga có idempotency/compensation.
28. Không có double authoritative writers.
29. Interval uniqueness có conflict protection thực.
30. Reconciliation và audit có kế hoạch.

### Vận hành

31. Indexes phục vụ query workload đo được.
32. Chi phí writes/storage của indexes được đo.
33. SLO, peak traffic và hotspot đã đánh giá.
34. Sharding/unique index restrictions được xem xét.
35. Schema version/rollout/rollback rõ.
36. Changes chỉ triển khai theo môi trường/quyền phù hợp.
37. Có log error codes, metrics, tracing không lộ PII.
38. Có integration tests, negative cases và concurrent cases.

## 55. Mẫu ghi lại một quyết định kiến trúc

~~~yaml
decisionId: "ADR-MONGO-001"
title: "Embed order items and reference products"
businessRequirement:
  - "Read order detail in one request"
  - "Preserve price at purchase time"
  - "Support current product catalog changes"
readPatterns:
  - "GET order by tenant and orderId"
  - "LIST orders by customer and createdAt"
writePatterns:
  - "Create order with bounded items"
  - "Update status conditionally"
cardinality:
  orderItemsMax: 20
model:
  embed:
    - "order.items"
    - "item price/name snapshot"
  reference:
    - "order.customerId"
    - "item.productId"
consistency:
  singleDocument:
    - "status and version"
    - "items and agreed amount"
  multiDocument:
    - "reserve stock and persist order"
  external:
    - "payment authorization via saga/outbox"
indexes:
  - "tenantId,customerId,createdAt,_id"
  - "tenantId,externalOrderId unique"
risks:
  - "item cap enforcement"
  - "transaction retry contention"
  - "outbox duplicate events"
verification:
  - "exact order details"
  - "no negative stock"
  - "no duplicate external order"
  - "read/write p95 within SLO"
owner: "application architecture team"
status: "proposed"
~~~

### 55.1. Decision record cho phép review lại

Khi dữ liệu tăng hoặc business contract thay đổi, team có thể xem vì sao chọn embed/transaction ban đầu, thay vì chỉ nhìn schema và đoán.

### 55.2. Rủi ro có người sở hữu

Một thiết kế với outbox nhưng không ai theo dõi queue lag/reconciliation chưa thật sự hoàn chỉnh.

## 56. Runbook chọn mô hình và mức nguyên tử

~~~text
INPUT:
  API read/write patterns
  Data cardinality and lifecycle
  Business invariants
  Tenant/security rules
  Storage and latency SLO

MODEL:
  Embed small bounded co-owned data
  Reference large or independent data
  Snapshot historical contracts
  Materialize derived views only with sync policy

WRITE:
  One document?
    -> Atomic update with predicate/version
  Multiple documents?
    -> Is all-or-nothing required?
       YES -> transaction + same session + retry/idempotency
       NO  -> outbox/saga + eventual reconciliation
  External effect?
    -> Never assume DB transaction rolls it back

VERIFY:
  Correct result and reference integrity
  No negative stock or illegal transitions
  No duplicate business operation
  No cross-tenant data leak
  Read/write p95 and storage within SLO
  Retry/timeout/failover behavior

RECORD:
  Architecture decision
  Schema and index version
  Failure modes and owner
  Rollout/rollback plan
~~~

## 57. Tổng kết tra cứu

**Nhúng** khi dữ liệu nhỏ, bounded, gắn cùng vòng đời và thường được đọc/ghi cùng parent. **Tham chiếu** khi dữ liệu lớn, cập nhật độc lập, dùng chung hoặc có retention/quyền riêng. **Snapshot** là bản sao có chủ đích nhằm bảo toàn lịch sử; không nhầm với dữ liệu master hiện tại.

**Cập nhật nguyên tử** bằng $inc, $set, conditional filters, arrayFilters hoặc findOneAndUpdate là lựa chọn mặc định cho invariant nằm **trong một document**. **Giao dịch** được cân nhắc khi nhiều MongoDB documents cần commit/abort cùng nhau và deployment hỗ trợ; nó phải đi kèm retry/idempotency, concerns phù hợp và kiểm chứng trên failure cases. Với các tác vụ ngoài database hoặc quy trình kéo dài, **outbox, saga và reconciliation** thường cần thiết.

Điểm mạnh của MongoDB không nằm ở việc bỏ mọi JOIN hay dùng transaction cho mọi thao tác. Giá trị đến từ việc **đặt đúng ranh giới dữ liệu và consistency theo business invariant**, giữ query nhanh, dữ liệu không bị sai dưới concurrency và hệ thống có thể tiến hóa khi quy mô tăng.

## Tài liệu tham khảo

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedding Versus References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Schema Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/)
- [MongoDB Manual — Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/)
- [MongoDB Manual — Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
