# Index đơn và index ghép trong MongoDB

Khi collection mới có vài chục document, MongoDB có thể quét toàn bộ dữ liệu mà ứng dụng vẫn phản hồi nhanh. Nhưng khi collection tăng lên hàng triệu đơn hàng, việc đọc từng document để tìm những đơn của một khách hàng hoặc một tenant sẽ làm tăng CPU, I/O và độ trễ. **Index** giúp MongoDB tìm các document phù hợp mà không nhất thiết phải quét toàn bộ collection.

Hai kiểu index nền tảng cần nắm chắc:

- **Index đơn (single-field index):** tổ chức khóa theo một field, ví dụ `{customerId: 1}`.
- **Index ghép (compound index):** tổ chức khóa theo **một chuỗi nhiều field có thứ tự**, ví dụ `{tenantId: 1, status: 1, createdAt: -1}`.

Điểm khó không chỉ là cú pháp `createIndex()`. Bạn còn phải chọn đúng field, đúng thứ tự khóa, đúng chiều sắp xếp và biết lúc nào nên giữ hay bỏ một index. Ba index đơn không tự tương đương một index ghép ba field; đổi thứ tự các field của index ghép cũng có thể thay đổi hiệu quả truy vấn rất lớn.

Bài học thuộc chương **Index cơ bản** trong *Database Engine Document MongoDB*. Các ví dụ chạy bằng **mongosh** trên database lab `index_basics_lab`. Tên stage và hình dạng `explain()` có thể khác giữa các phiên bản MongoDB và execution engine. Những quyết định index cho production cần kiểm chứng trên phiên bản và workload thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích index giảm lượng dữ liệu phải đọc như thế nào và chi phí duy trì index.
2. Tạo, liệt kê, đo và xóa index đơn với `createIndex()`, `getIndexes()`, `stats()`, `dropIndex()`.
3. Tạo index ghép và vận dụng **quy tắc tiền tố (prefix)** để dự đoán query nào dùng index hiệu quả.
4. Thiết kế thứ tự key theo **Equality–Sort–Range (ESR)** và hiểu khi nào nên đo phương án range trước sort.
5. Phân tích `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, `totalKeysExamined`, `totalDocsExamined` trong `explain("executionStats")`.
6. Phân biệt filter, sort, projection, covered query, multikey index và các trường hợp giới hạn của mảng.
7. Dùng unique index đơn/ghép, hiểu ảnh hưởng của null/missing, partial index và collation.
8. Lựa chọn bộ index theo tải đọc/ghi, dung lượng, RAM/cache và SLO.

## 2. Index giúp tìm document như thế nào?

Hãy tưởng tượng một collection có 5 triệu đơn. API thường thực thi:

~~~javascript
db.orders.find({
  tenantId: "tenant-001",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(20)
~~~

Nếu không có index phù hợp, engine có thể phải xem rất nhiều document để xác định những đơn thỏa điều kiện và sắp xếp chúng. Với index thích hợp, MongoDB có thể đọc vùng index chứa một nhóm key của tenant/status rồi tận dụng thứ tự ngày tạo ngay từ index.

~~~mermaid
flowchart LR
    API["Query có filter + sort"] --> Planner["Query planner"]
    Planner --> Choice{"Đường truy cập phù hợp?"}
    Choice -->|"Index"| IDX["IXSCAN: đọc index key"]
    IDX --> FETCH["FETCH: lấy document khi cần"]
    FETCH --> Result["Trả kết quả"]
    Choice -->|"Không phù hợp"| SCAN["COLLSCAN: quét collection"]
    SCAN --> Result
~~~

Trong nhiều trường hợp, index thông thường dùng cấu trúc có tổ chức theo thứ tự khóa, thường được mô tả về nguyên lý như B-tree. Một index entry chứa khóa sắp xếp và tham chiếu cần thiết để truy xuất document. Dung lượng và cách mã hóa vật lý là trách nhiệm của storage engine; khi học thiết kế query, quan trọng nhất là **thứ tự khóa logic**.

### Index không miễn phí

| Lợi ích | Chi phí |
|---|---|
| Hạn chế số document phải kiểm tra | Index chiếm disk và một phần working set trong cache |
| Có thể phục vụ `sort` trực tiếp | Insert/update/delete phải duy trì index |
| Có thể tránh đọc document trong covered query | Index build/rebuild cần tài nguyên và có rủi ro vận hành |
| Có thể bảo đảm uniqueness | Ràng buộc unique có thể làm thao tác ghi thất bại |

**Index là công cụ chọn đường truy cập**, không phải lời hứa rằng mọi query đều dùng index hoặc dùng index luôn nhanh hơn quét collection.

## 3. Bộ dữ liệu thực hành

Chỉ chạy trên database lab. Không dùng lệnh xóa dữ liệu production để bắt đầu lại bài.

~~~javascript
use index_basics_lab

db.orders.insertMany([
  {
    _id: "ord-001", tenantId: "t-01", customerId: "c-101",
    status: "PAID", region: "HCM", amount: NumberDecimal("120000"),
    createdAt: ISODate("2026-01-05T08:00:00Z"),
    items: [{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]
  },
  {
    _id: "ord-002", tenantId: "t-01", customerId: "c-101",
    status: "CREATED", region: "HCM", amount: NumberDecimal("90000"),
    createdAt: ISODate("2026-01-06T09:00:00Z"),
    items: [{ sku: "A", qty: 1 }]
  },
  {
    _id: "ord-003", tenantId: "t-01", customerId: "c-102",
    status: "PAID", region: "HN", amount: NumberDecimal("350000"),
    createdAt: ISODate("2026-01-07T10:00:00Z"),
    items: [{ sku: "C", qty: 3 }]
  },
  {
    _id: "ord-004", tenantId: "t-01", customerId: "c-103",
    status: "CANCELLED", region: "DN", amount: NumberDecimal("75000"),
    createdAt: ISODate("2026-01-08T11:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: "ord-005", tenantId: "t-01", customerId: "c-101",
    status: "PAID", region: "HCM", amount: NumberDecimal("500000"),
    createdAt: ISODate("2026-01-09T12:00:00Z"),
    items: [{ sku: "A", qty: 4 }]
  },
  {
    _id: "ord-006", tenantId: "t-02", customerId: "c-201",
    status: "PAID", region: "HCM", amount: NumberDecimal("210000"),
    createdAt: ISODate("2026-01-05T13:00:00Z"),
    items: [{ sku: "A", qty: 2 }]
  },
  {
    _id: "ord-007", tenantId: "t-02", customerId: "c-202",
    status: "CREATED", region: "HN", amount: NumberDecimal("115000"),
    createdAt: ISODate("2026-01-06T14:00:00Z"),
    items: [{ sku: "D", qty: 1 }]
  },
  {
    _id: "ord-008", tenantId: "t-02", customerId: "c-201",
    status: "PAID", region: "HN", amount: NumberDecimal("280000"),
    createdAt: ISODate("2026-01-10T15:00:00Z"),
    items: [{ sku: "A", qty: 1 }, { sku: "C", qty: 2 }]
  },
  {
    _id: "ord-009", tenantId: "t-02", customerId: "c-203",
    status: "CANCELLED", region: "DN", amount: NumberDecimal("60000"),
    createdAt: ISODate("2026-01-11T16:00:00Z"),
    items: [{ sku: "B", qty: 1 }]
  },
  {
    _id: "ord-010", tenantId: "t-03", customerId: "c-301",
    status: "PAID", region: "HCM", amount: NumberDecimal("800000"),
    createdAt: ISODate("2026-01-12T17:00:00Z"),
    items: [{ sku: "C", qty: 5 }]
  },
  {
    _id: "ord-011", tenantId: "t-03", customerId: "c-302",
    status: "CREATED", region: "HN", amount: NumberDecimal("170000"),
    createdAt: ISODate("2026-01-13T18:00:00Z"),
    items: [{ sku: "D", qty: 2 }]
  },
  {
    _id: "ord-012", tenantId: "t-03", customerId: "c-301",
    status: "PAID", region: "HN", amount: NumberDecimal("450000"),
    createdAt: ISODate("2026-01-14T19:00:00Z"),
    items: [{ sku: "A", qty: 3 }]
  }
])
~~~

Lệnh đọc kiểm tra:

~~~javascript
db.orders.countDocuments({})

db.orders.find(
  {},
  { _id: 1, tenantId: 1, customerId: 1, status: 1, createdAt: 1 }
).sort({ _id: 1 })
~~~

Collection lab có 12 document. Nếu chạy lại `insertMany()` với cùng `_id` sẽ gặp duplicate key. Hãy dùng database lab mới nếu muốn lặp lại toàn bộ bài. **12 document đủ để minh họa query và ngữ nghĩa, nhưng không đủ để so sánh hiệu năng index một cách đáng tin cậy.**

## 4. Index mặc định trên `_id`

MongoDB thường tạo index duy nhất `_id_` trên collection thông thường:

~~~javascript
db.orders.getIndexes()
~~~

Bạn sẽ thấy key `{ _id: 1 }` và tên `_id_`. Vì vậy truy vấn:

~~~javascript
db.orders.findOne({ _id: "ord-005" })
~~~

đã có một đường truy cập hữu ích mà không cần tạo thêm index nghiệp vụ. Nhưng `_id_` không giúp một query chỉ lọc `status` hoặc `customerId` tìm chính xác vùng document mong muốn.

### Không đồng nhất document ID với khóa tìm kiếm nghiệp vụ

Nhiều hệ thống sử dụng `_id` kiểu ObjectId nhưng cho người dùng tra cứu theo `externalOrderNo`. Khi đó API `findOne({externalOrderNo:"PO-123"})` có thể cần index riêng. Quyết định ID là thiết kế dữ liệu, còn quyết định index phụ thuộc các query cần phục vụ.

## 5. Index đơn: tạo và truy vấn

### 5.1. Index tăng dần

~~~javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "idx_customer_id" }
)
~~~

`1` là hướng tăng dần, `-1` là hướng giảm dần. Tên index giúp đọc log, kết quả `getIndexes()` và kế hoạch `explain()`.

Truy vấn:

~~~javascript
db.orders.find(
  { customerId: "c-101" },
  { _id: 1, customerId: 1, status: 1 }
)
~~~

Document khớp: `ord-001`, `ord-002` và `ord-005`. Không khai báo `sort` thì **không có bảo đảm thứ tự kết quả**, dù engine đang dùng một index có thứ tự.

### 5.2. Index giảm dần

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_created_desc" }
)
~~~

Query lấy 5 đơn mới nhất:

~~~javascript
db.orders.find(
  {},
  { _id: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(5)
~~~

Với **index đơn trên một field**, MongoDB thường có thể quét index theo hướng ngược để phục vụ sort tăng dần hoặc giảm dần. Không nhất thiết tạo cả `{createdAt:1}` và `{createdAt:-1}` chỉ để hỗ trợ hai hướng trên một field. Với **index ghép**, chiều của từng field lại ảnh hưởng sort nhiều cột rõ rệt hơn.

### 5.3. Index trên field lồng nhau

~~~javascript
db.orders.createIndex(
  { "items.sku": 1 },
  { name: "idx_item_sku" }
)

db.orders.find({
  "items.sku": "A"
})
~~~

Vì `items` là mảng object, index trên `items.sku` là **multikey index**, một document có thể đóng góp nhiều khóa. Điều này hỗ trợ truy vấn mảng, nhưng khiến index và chi phí ghi tăng theo cấu trúc mảng.

### 5.4. Khi nào index đơn có giá trị?

| Truy vấn thường gặp | Index đơn ứng viên | Cân nhắc |
|---|---|---|
| Lấy các đơn của một khách | `{customerId:1}` | Tốt khi filter đủ chọn lọc |
| Lấy đơn mới nhất toàn hệ thống | `{createdAt:-1}` | Hỗ trợ sort/limit |
| Tìm document chứa SKU | `{"items.sku":1}` | Multikey, số item ảnh hưởng footprint |
| Tìm giao dịch theo mã ngoài | `{externalId:1}` | Có thể cần unique |
| Lọc mọi đơn có status PAID | `{status:1}` | Nếu PAID chiếm phần lớn dữ liệu, lợi ích có thể thấp |

Index đơn phù hợp với query **chủ yếu theo một field**. Khi filter và sort thường luôn dùng một nhóm field cố định, cân nhắc compound index.

## 6. Index ghép: thứ tự khóa thay đổi cách truy cập

Tạo index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  { name: "idx_tenant_status_created" }
)
~~~

Index key được tổ chức theo:

~~~text
tenantId tăng dần
  trong cùng tenantId: status tăng dần
    trong cùng tenantId + status: createdAt giảm dần
~~~

Ví dụ minh họa logic thứ tự khóa (không phải format byte thực tế):

~~~text
(t-01, CANCELLED, 2026-01-08)
(t-01, CREATED,   2026-01-06)
(t-01, PAID,      2026-01-09)
(t-01, PAID,      2026-01-07)
(t-01, PAID,      2026-01-05)
(t-02, CANCELLED, 2026-01-11)
(t-02, CREATED,   2026-01-06)
(t-02, PAID,      2026-01-10)
(t-02, PAID,      2026-01-05)
...
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(20)
~~~

có thể giới hạn hai field đầu bằng equality rồi đọc các key trong nhóm theo ngày mới nhất. Với dữ liệu mẫu, thứ tự kết quả là:

~~~text
ord-005
ord-003
ord-001
~~~

Đổi index thành `{createdAt:-1,tenantId:1,status:1}` sẽ đặt ngày lên đầu; cấu trúc mới có thể hợp lý cho feed mới nhất toàn hệ thống nhưng kém phù hợp hơn khi mọi query chỉ quan tâm tới một tenant/status.

**Index ghép không phải tập các field không có thứ tự.**

## 7. Quy tắc tiền tố (prefix) của compound index

Xét index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Các tiền tố từ trái sang phải:

~~~text
{ tenantId: 1 }
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Một query có điều kiện trên những field đầu thường có cơ hội giới hạn vùng key tốt:

| Query | Khả năng sử dụng index ghép |
|---|---|
| `{tenantId:"t-01"}` | Có tiền tố `tenantId` |
| `{tenantId:"t-01",status:"PAID"}` | Có tiền tố hai field |
| `{tenantId:"t-01",status:"PAID",createdAt:{$gte:t}}` | Có thể dùng các field trong toàn key |
| `{status:"PAID"}` | Thiếu field đầu `tenantId`; không có prefix phù hợp để lọc status hiệu quả |
| `{createdAt:{$gte:t}}` | Thiếu hai field đầu; không tương đương index riêng trên createdAt |
| `{tenantId:"t-01",createdAt:{$gte:t}}` | Có prefix tenantId; việc tận dụng createdAt sau khoảng trống status bị hạn chế |

Đây là quy tắc thiết kế hiệu quả, **không phải tuyên bố planner tuyệt đối không dùng index nếu thiếu tiền tố**. Trong một số hoàn cảnh MongoDB có thể scan index (thậm chí chọn nó để tránh đọc document), nhưng không nên kỳ vọng hiệu suất giống index có key đầu phù hợp.

### 7.1. Khi nào index tiền tố có thể dư thừa?

Nếu tồn tại cả:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

index đơn `tenantId` **có thể** trở nên dư vì index ghép đã có tiền tố này. Nhưng chưa nên xóa ngay:

- Index đơn nhỏ hơn, có thể phục vụ query thường gặp với I/O/cache thấp hơn.
- Index có option như unique, partial hoặc collation khác nhau không luôn tương đương.
- Index ghép có thể được giữ vì sort, còn index đơn vẫn có giá trị cho aggregation khác.
- Một vài query ít chạy nhưng quan trọng có thể phụ thuộc index đơn.

Đo `explain()`, tải ghi, footprint và theo dõi chu kỳ nghiệp vụ trước khi kết luận index dư.

### 7.2. Equality trên cả hai field không quyết định tuyệt đối thứ tự

So:

~~~javascript
{ tenantId: 1, status: 1 }
{ status: 1, tenantId: 1 }
~~~

Query có equality trên **cả hai field** có thể được index hỗ trợ với hai thứ tự. Nhưng query chỉ lọc `tenantId` thường phù hợp hơn index đầu; query chỉ lọc `status` thường phù hợp hơn index sau. Nếu còn sort/range thì thứ tự càng quan trọng.

## 8. Equality – Sort – Range (ESR)

Một quy tắc khởi đầu để thiết kế compound index là:

1. **Equality:** các field lọc bằng, như `tenantId = "t-01"` và `status = "PAID"`.
2. **Sort:** các field cần sắp xếp, như `createdAt: -1`.
3. **Range:** các field lọc khoảng, như `amount >= 100000`.

Nguyên tắc **ESR** là heuristic, không phải luật cứng. Nếu điều kiện range cực kỳ chọn lọc, có thể nên đặt range trước sort dù phải sắp xếp riêng một tập kết quả nhỏ. Cần đo hai phương án để quyết định.

### 8.1. Equality rồi sort

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({ createdAt: -1 })
~~~

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Hai equality được cố định, nên các key còn lại trong vùng đó có thứ tự theo `createdAt`; đây là một mẫu thường hiệu quả cho danh sách đơn mới nhất.

### 8.2. Equality → Sort → Range

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  amount: { $gte: NumberDecimal("100000") }
}).sort({ createdAt: -1 }).limit(20)
~~~

Index theo ESR:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, amount: 1 },
  { name: "idx_tenant_created_amount" }
)
~~~

Index tập trung vào vùng tenant và thứ tự ngày mới nhất. Điều kiện amount nằm sau sort, nên engine có thể phải xem nhiều key mới tìm đủ 20 đơn có amount cao, nhất là khi phần lớn đơn có amount thấp.

### 8.3. Equality → Range → Sort

Phương án khác:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, amount: 1, createdAt: -1 },
  { name: "idx_tenant_amount_created" }
)
~~~

Index này có cơ hội giới hạn khoảng `amount` tốt hơn. Tuy nhiên vì key được nhóm theo amount trước khi đến createdAt, nó **không mặc định** cung cấp thứ tự createdAt toàn tenant khi amount là range; query có thể phải sort riêng.

| Phương án | Lợi thế tiềm năng | Bất lợi tiềm năng |
|---|---|---|
| `{tenantId:1,createdAt:-1,amount:1}` | Phục vụ sort theo ngày sau tenant | Có thể duyệt nhiều key trước khi đủ kết quả lọc amount |
| `{tenantId:1,amount:1,createdAt:-1}` | Thu hẹp range amount sớm hơn | Có thể cần stage SORT theo createdAt |

### 8.4. So sánh có kiểm soát bằng `hint`

~~~javascript
const q = {
  tenantId: "t-01",
  amount: { $gte: NumberDecimal("100000") }
}

db.orders.find(q)
  .sort({ createdAt: -1 })
  .limit(20)
  .hint("idx_tenant_created_amount")
  .explain("executionStats")

db.orders.find(q)
  .sort({ createdAt: -1 })
  .limit(20)
  .hint("idx_tenant_amount_created")
  .explain("executionStats")
~~~

`hint()` được dùng **trong thí nghiệm** để so sánh các index đã tạo. Đừng cố định `hint` trong mọi query production chỉ vì một lần thử: khi phân bố dữ liệu, index hoặc query thay đổi, lựa chọn cũ có thể trở nên kém.

## 9. Chiều sort của index ghép

Xét index:

~~~javascript
{ tenantId: 1, createdAt: -1, amount: 1 }
~~~

Khi filter có equality trên `tenantId`, index có thể hỗ trợ sắp xếp hai field còn lại theo pattern:

~~~javascript
sort({ createdAt: -1, amount: 1 })
~~~

hoặc quét ngược toàn bộ pattern:

~~~javascript
sort({ createdAt: 1, amount: -1 })
~~~

Nhưng:

~~~javascript
sort({ createdAt: -1, amount: -1 })
~~~

không phải pattern hoặc phép đảo hướng của cả hai field, nên không mặc định được phục vụ trọn bởi index ấy. Query planner có thể cần thêm bước sort.

### 9.1. Khi cố định tiền tố bằng equality

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({ createdAt: 1 })
~~~

có thể quét ngược vùng key của tenant/status để lấy ngày tăng dần.

### 9.2. Khi thiếu field giữa

Query:

~~~javascript
db.orders.find({
  tenantId: "t-01"
}).sort({ createdAt: -1 })
~~~

trên index `{tenantId:1,status:1,createdAt:-1}` sẽ có các key được nhóm theo **status** trước createdAt. Vì status không được cố định, thứ tự trong toàn tenant không mặc định là thứ tự ngày toàn cục. Nếu API quan trọng, cân nhắc:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "idx_tenant_created" }
)
~~~

**Một compound index không thể phục vụ mọi kiểu sort chỉ vì nó chứa field sort ở vị trí nào đó.**

## 10. Selectivity và cardinality

`_id` thường có cardinality rất cao; field `status` thường có ít giá trị khác nhau. Nhưng điều quyết định lợi ích index là mức độ **chọn lọc của predicate trên dữ liệu thực**.

Ví dụ giả định:

~~~text
Collection: 1.000.000 đơn

status = PAID          -> 850.000 đơn   (lọc yếu)
tenantId = t-01       -> 80.000 đơn    (lọc trung bình)
customerId = c-101   -> 25 đơn        (lọc mạnh)
~~~

Nếu query trả gần hết collection, dùng index còn có thể phát sinh nhiều lần FETCH. Với một điều kiện trả rất ít document, index thường hấp dẫn hơn. Tuy nhiên, **không có quy tắc “field cardinality cao phải luôn đứng đầu compound index”** cho mọi workload:

- Thứ tự equality fields còn ảnh hưởng khả năng dùng prefix.
- Sort và range đòi hỏi key order.
- Một số giá trị status hiếm hơn nhiều giá trị khác.
- Dữ liệu có thể lệch mạnh giữa các tenant.

### 10.1. Đọc hiệu quả từ `explain`

Các con số:

~~~text
nReturned
totalKeysExamined
totalDocsExamined
executionTimeMillis
~~~

cho biết số kết quả và mức độ work của query. Nếu trả 20 document nhưng kiểm tra 200.000 index key, có thể index vẫn chưa phù hợp. Nếu trả 100.000 document, chi phí chuyển dữ liệu qua mạng và đọc document có thể rất lớn dù key scan hiệu quả.

Không lấy một tỉ lệ duy nhất làm chuẩn cho mọi query: aggregate, multikey, pagination và truy vấn trả 0 document cần phân tích theo tình huống.

## 11. Đọc `explain("executionStats")`

~~~javascript
db.orders.find({
  tenantId: "t-01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats")
~~~

| Stage/chỉ số | Ý nghĩa |
|---|---|
| `queryPlanner.winningPlan` | Kế hoạch được chọn |
| `IXSCAN` | Đọc index key |
| `COLLSCAN` | Quét document collection |
| `FETCH` | Lấy document từ storage/cache để kiểm tra hoặc trả field |
| `SORT` | Có bước sort riêng trong kế hoạch |
| `indexName` | Tên index ở stage tương ứng |
| `indexBounds` | Khoảng key index cần duyệt |
| `executionStats.nReturned` | Số kết quả trả về |
| `totalKeysExamined` | Tổng số index key được kiểm tra |
| `totalDocsExamined` | Số document được kiểm tra |

Hình dạng JSON có thể khác giữa classic execution engine và Slot-Based Execution. Không phụ thuộc vào một path JSON cố định cho mọi phiên bản.

### 11.1. Ba trường hợp thường gặp

**COLLSCAN:** có thể do thiếu index hoặc planner xác định quét collection rẻ hơn. Trên 12 document, COLLSCAN là điều không lạ.

**IXSCAN + FETCH:** index giúp tìm ứng viên, nhưng engine vẫn cần đọc document để lấy field chưa có trong index hoặc xác nhận predicate bổ sung. Đây là hành vi bình thường.

**IXSCAN + SORT:** index được dùng để lọc nhưng không cung cấp toàn bộ thứ tự yêu cầu; sort có thể tiêu tốn CPU/RAM khi dữ liệu lớn.

### 11.2. Một phương pháp đo

1. Xác định **query shape**: filter, sort, projection, limit.
2. Thu kế hoạch và `executionStats` trước khi thay index.
3. Tạo index ứng viên trong môi trường thử nghiệm.
4. Lặp lại đúng query cùng dữ liệu đại diện.
5. So nReturned, keys examined, docs examined, stage SORT và latency.
6. Đo thêm write throughput/latency và index footprint.
7. Kiểm tra khi dữ liệu lớn hơn cache hoặc khi selectivity thay đổi.

Chênh lệch 0–1 ms trên 12 document không thể chứng minh index thắng. Cần workload và số lần chạy đủ đại diện.

## 12. Covered query: khi index đủ để trả kết quả

Một **covered query** có thể được phục vụ từ index mà không cần truy xuất document gốc, nếu điều kiện lọc và các field cần trả đều có trong index và những quy tắc coverage khác được đáp ứng.

Với index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

thử:

~~~javascript
db.orders.find(
  {
    tenantId: "t-01",
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 }).explain("executionStats")
~~~

Đây là **ứng viên covered query** vì filter/sort/projection chỉ sử dụng field trong index. `_id:0` quan trọng: khi cần `_id` mà index không chứa `_id`, MongoDB có thể phải đọc document gốc. Dấu hiệu của coverage ở một kế hoạch phù hợp là không cần FETCH document và `totalDocsExamined = 0`.

### Projection không tự động làm query được cover

~~~javascript
db.orders.find(
  { tenantId: "t-01" },
  { _id: 0, customerId: 1 }
)
~~~

Projection làm response nhỏ hơn, nhưng nếu index dùng cho filter không chứa `customerId` thì engine có thể vẫn phải đọc document.

### Có nên thêm nhiều field vào index để cover?

Ví dụ index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, customerId: 1, amount: 1 }
~~~

cover được nhiều field hơn trong một số query nhưng đồng thời lớn hơn, tốn cache và tăng write amplification. Chỉ nên mở rộng index khi cải thiện đủ lớn cho query quan trọng.

## 13. Multikey: index trên mảng

Index:

~~~javascript
db.orders.createIndex(
  { "items.sku": 1 },
  { name: "idx_item_sku" }
)
~~~

hoạt động trên các object trong mảng `items`. Một document có nhiều item có thể tạo nhiều key; số phần tử ảnh hưởng chi phí lưu trữ và ghi.

### 13.1. Compound multikey trên cùng mảng object

~~~javascript
db.orders.createIndex(
  { "items.sku": 1, "items.qty": 1 },
  { name: "idx_item_sku_qty" }
)
~~~

Nếu nghiệp vụ tìm một item SKU A với qty ≥ 2, hãy dùng:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 2 }
    }
  }
})
~~~

`$elemMatch` buộc hai predicate thuộc **cùng phần tử**. Query:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 2 }
})
~~~

có thể khớp SKU từ một item và qty từ item khác. Index không tự sửa ngữ nghĩa sai. Trong điều kiện phù hợp, `$elemMatch` còn cho phép planner kết hợp index bounds đối với các field từ cùng mảng.

### 13.2. Mảng độc lập không giống field con trong cùng mảng

Với document:

~~~javascript
{
  tags: ["new", "vip"],
  couponCodes: ["SAVE10", "WELCOME"]
}
~~~

compound index:

~~~javascript
{ tags: 1, couponCodes: 1 }
~~~

có thể vi phạm hạn chế **parallel arrays** của compound multikey index. Không suy luận rằng index nào chứa hai field array độc lập cũng được phép chỉ vì index `items.sku + items.qty` từ cùng mảng object là hợp lệ.

### 13.3. Hạn chế covered query với array

Multikey index có các điều kiện coverage riêng; đặc biệt, truy vấn cần trả field mảng thường không thể cover theo cách đơn giản giống field scalar. Hãy kiểm tra `explain()` thay vì cho rằng cứ có field trong index thì không cần FETCH.

## 14. Unique index đơn và ghép

Index có thể vừa hỗ trợ truy vấn vừa **cưỡng chế uniqueness**.

### 14.1. Unique trên một field

~~~javascript
db.transactions.createIndex(
  { transactionId: 1 },
  { unique: true, name: "uq_transaction_id" }
)
~~~

MongoDB sẽ từ chối một document có cùng key `transactionId` với document khác, có thể báo duplicate key `E11000`.

`findOne()` kiểm tra trước insert **không thay thế unique index**: hai client có thể cùng đọc “chưa có” rồi cùng insert.

### 14.2. Unique compound theo tenant

Số đơn `orderNo` có thể trùng giữa hai tenant, nhưng phải duy nhất trong một tenant:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_order_no"
  }
)
~~~

Uniqueness áp dụng cho **tổ hợp** `tenantId + orderNo`. Ví dụ `(t-01,INV-100)` và `(t-02,INV-100)` là hai key khác nhau.

### 14.3. Null và field thiếu

Một unique index **không tự buộc field phải tồn tại**. Với unique single-field index thông thường, giá trị null/missing có những quy tắc uniqueness khiến nhiều document thiếu key có thể gây trùng. Với unique compound index, ràng buộc áp dụng cho **tổ hợp key**, bao gồm thành phần null/missing khi có.

Để bảo đảm `orderNo` luôn có kiểu string, cần schema validation hoặc kiểm soát ghi riêng. Để chỉ ràng buộc unique cho document thực sự có `orderNo` string, có thể dùng partial unique index theo phạm vi thích hợp.

### 14.4. Partial unique index

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uq_tenant_order_no_string",
    partialFilterExpression: {
      orderNo: { $type: "string" }
    }
  }
)
~~~

Index này chỉ cưỡng chế uniqueness trên những document thỏa filter. Những document ngoài filter không bị ràng buộc bởi index này. **Không tự tạo đồng thời hai unique index toàn phần và partial index cùng key** nếu chưa làm rõ mục tiêu; index toàn phần có thể khiến partial index không đạt ý nghĩa mong muốn.

Index unique build trên collection đã có dữ liệu có thể thất bại nếu phát hiện trùng. Cần xử lý dữ liệu cũ theo kế hoạch trước khi bật ràng buộc mới.

## 15. Partial, sparse và collation

Hai index có cùng key pattern chưa chắc cùng phạm vi hoặc ngữ nghĩa.

### 15.1. Sparse index

~~~javascript
db.customer_profiles.createIndex(
  { nickname: 1 },
  { sparse: true, name: "idx_existing_nickname" }
)
~~~

Sparse index có thể bỏ qua các document không có field được index theo quy tắc của loại index, nên query dùng index này khi thiếu điều kiện phù hợp có nguy cơ không trả đủ dữ liệu. Partial index thường biểu diễn được điều kiện chọn document rõ ràng hơn.

### 15.2. Partial index

Ví dụ chỉ index những đơn đang được xử lý:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "idx_created_orders",
    partialFilterExpression: {
      status: "CREATED"
    }
  }
)
~~~

Query `{tenantId:"t-01",status:"CREATED"}` có thể dùng index phù hợp. Query yêu cầu mọi status không thể dựa hoàn toàn vào một index chỉ chứa CREATED vì sẽ bỏ sót PAID/CANCELLED.

Trình tối ưu chỉ chọn partial index khi có thể xác định query không cần dữ liệu nằm ngoài phạm vi index.

### 15.3. Collation

~~~javascript
db.customers.createIndex(
  { displayName: 1 },
  {
    name: "idx_name_ci",
    collation: { locale: "en", strength: 2 }
  }
)

db.customers.find({
  displayName: "alice"
}).collation({
  locale: "en",
  strength: 2
})
~~~

Index với collation cho string có thể hỗ trợ query so sánh/sort theo cùng collation. Nếu query dùng collation khác, index có thể không hỗ trợ phần so sánh string theo kỳ vọng. Index không thay thế quy tắc chuẩn hóa và bảo mật của username/email.

## 16. Index đơn và index ghép có thể hỗ trợ query nào?

Giả sử có ba index:

~~~javascript
// I1
{ customerId: 1 }

// I2
{ tenantId: 1, status: 1, createdAt: -1 }

// I3
{ tenantId: 1, createdAt: -1 }
~~~

| Query | Index có khả năng phù hợp | Lý do |
|---|---|---|
| `customerId = c-101` | I1 | Lọc đúng field |
| `tenantId = t-01` | I2 hoặc I3 | Đều có tenantId làm tiền tố |
| `tenantId=t-01 AND status=PAID ORDER BY createdAt DESC` | I2 | Equality hai field đầu, sort field sau |
| `tenantId=t-01 ORDER BY createdAt DESC` | I3 | I2 có status chen giữa, không cung cấp global createdAt sort |
| `status=PAID` | Chưa index nào có tiền tố status | Cân nhắc theo workload thật |
| `createdAt từ ngày D, không filter tenant` | Chưa có index bắt đầu createdAt | Có thể cần index đơn createdAt |

Không có một index trả lời tối ưu cho mọi query. Chọn bộ index cần cân bằng các API đang được sử dụng với chi phí duy trì.

## 17. Index intersection: có thay compound index được không?

Nếu có:

~~~javascript
{ tenantId: 1 }
{ status: 1 }
{ createdAt: -1 }
~~~

MongoDB có thể chọn một index cho query, và trong một số trường hợp có thể kết hợp nhiều index bằng **index intersection**. Nhưng không nên mặc định planner sẽ kết hợp cả ba, hoặc tập hợp các index đơn sẽ hỗ trợ filter+sort tốt bằng index ghép được thiết kế riêng.

Compound index chứa thứ tự **tenant → status → createdAt** có thể phục vụ filter equality và sort trong cùng một cấu trúc. Index intersection có thể làm phát sinh công việc kết hợp key, FETCH hoặc SORT.

Vì vậy, khi một query được thực thi rất thường xuyên:

- Xem `winningPlan` thay vì đoán optimizer.
- So index ghép với phương án dùng nhiều index đơn.
- Tính tổng footprint và chi phí ghi của cả hai bộ index.
- Không thêm ba index đơn chỉ vì “mỗi filter cần một index”.

## 18. Quản lý index trong vòng đời hệ thống

### 18.1. Liệt kê index

~~~javascript
db.orders.getIndexes()
~~~

Kết quả bao gồm key pattern, tên và những option như unique/partial/collation khi có. Sau migration cần **đọc lại metadata** để xác nhận cấu hình thực tế.

### 18.2. Đo dung lượng

~~~javascript
const stats = db.orders.stats()

printjson({
  count: stats.count,
  size: stats.size,
  storageSize: stats.storageSize,
  totalIndexSize: stats.totalIndexSize,
  indexSizes: stats.indexSizes
})
~~~

`indexSizes` và `totalIndexSize` là thống kê footprint index theo storage engine, không phải lượng RAM một index đang chiếm trong cache.

### 18.3. Đo mức sử dụng

~~~javascript
db.orders.aggregate([
  { $indexStats: {} }
])
~~~

`$indexStats` giúp quan sát các lượt truy cập index trong khoảng thời gian mà hệ thống có metric. Index có số lượt thấp không tự động vô dụng: job tháng hoặc truy vấn điều tra hiếm vẫn có thể phụ thuộc nó. Đừng xóa index chỉ dựa vào vài giờ quan sát.

### 18.4. Ẩn index trước khi xóa

Trên phiên bản hỗ trợ hidden indexes:

~~~javascript
db.orders.hideIndex("idx_customer_id")

// Sau khi quan sát xong:
db.orders.unhideIndex("idx_customer_id")
~~~

Hidden index không được query planner chọn cho truy vấn thông thường, nhưng vẫn được duy trì khi ghi và ràng buộc như uniqueness không tự biến mất. Đây là công cụ thử tác động của việc bỏ index, không phải cách loại bỏ chi phí lưu trữ/ghi của index.

### 18.5. Xóa index

~~~javascript
db.orders.dropIndex("idx_customer_id")
~~~

**Chỉ dùng trong lab hoặc thay đổi production có kế hoạch.** Trước khi xóa:

1. Xác nhận index nào đang phục vụ query quan trọng và ở thời điểm nào.
2. Kiểm tra có đang cưỡng chế unique business key không.
3. Đánh giá query plan khi index vắng mặt.
4. Lập phương án rollback, chi phí tạo lại và thời gian index build.
5. Theo dõi latency, CPU/I/O, write throughput sau triển khai.

Không dùng `dropIndex("_id_")` để xóa index `_id` mặc định của collection thông thường.

### 18.6. Chi phí tạo index trên collection lớn

Index build có thể tiêu thụ CPU, I/O, RAM/dung lượng tạm và gây ảnh hưởng tải. Tác động cụ thể phụ thuộc phiên bản MongoDB/topology. Khi thêm index trên production, cần xem xét thời điểm triển khai, dung lượng trống, replication, thời gian build, monitoring và khả năng dừng/khôi phục. Không liên tục tạo/xóa index để “thử cho nhanh” trên primary đang phục vụ traffic thật.

## 19. Thiết kế index trong hệ thống multi-tenant

Đa số API SaaS có filter:

~~~javascript
{ tenantId: authenticatedTenantId }
~~~

Nếu API còn lọc status và sort theo ngày:

~~~javascript
db.orders.find({
  tenantId: authenticatedTenantId,
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: 1
}).limit(20)
~~~

Index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_tenant_status_date_id" }
)
~~~

Field `_id` là tie-breaker giúp thứ tự xác định khi nhiều document có cùng timestamp. Thứ tự sort của hai field `createdAt`/`_id` là hỗn hợp chiều, nên index phải được thiết kế khớp pattern tương ứng.

### 19.1. Index không thay thế authorization

Đặt `tenantId` ở đầu index chỉ giúp query hiệu quả, **không tự ngăn truy cập dữ liệu tenant khác**. API phải lấy tenant từ ngữ cảnh xác thực, kiểm tra quyền và đưa tenant filter vào truy vấn đúng cách.

### 19.2. Keyset pagination theo sort ổn định

Nếu sort theo `createdAt` giảm dần và `_id` tăng dần, cursor gồm cả hai field:

~~~javascript
const cursorDate = ISODate("2026-01-07T10:00:00Z")
const cursorId = "ord-003"

db.orders.find({
  tenantId: "t-01",
  status: "PAID",
  $or: [
    { createdAt: { $lt: cursorDate } },
    {
      createdAt: cursorDate,
      _id: { $gt: cursorId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: 1
}).limit(20)
~~~

Vì createdAt giảm dần, trang sau gồm thời điểm nhỏ hơn; khi ngày bằng nhau, `_id` tăng dần nên lấy ID lớn hơn. Index `{tenantId:1,status:1,createdAt:-1,_id:1}` là ứng viên. Query có `$or` cần được đo thực tế.

Thứ tự xác định **không đồng nghĩa có snapshot cố định qua nhiều HTTP request**: insert/update giữa hai trang vẫn có thể thay đổi tập dữ liệu.

## 20. Những lỗi thường gặp khi thiết kế index

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Tạo index cho mọi field | Tốn disk/cache/write, khó quản lý | Bắt đầu từ query shape và SLO |
| Coi compound index là ba index đơn | Hiểu sai prefix, filter, sort | Vẽ thứ tự khóa từ trái sang phải |
| Đặt field sort sau field không có equality | Query có thể phải SORT riêng | Điều chỉnh thứ tự field theo workload |
| Dùng ESR như quy tắc tuyệt đối | Bỏ qua range chọn lọc mạnh | So ESR với range trước sort bằng `explain` |
| Chỉ quan tâm `IXSCAN` | Có thể scan nhiều key/FETCH/SORT | Đo nReturned, key/doc examined và latency |
| Coi projection là covered query | Vẫn có thể FETCH document | Kiểm tra coverage và `totalDocsExamined` |
| Dùng hai dotted predicate với array | Có thể khớp hai phần tử khác nhau | Dùng `$elemMatch` cho same-element |
| Unique index nhưng không yêu cầu field | Null/missing có thể gây kết quả bất ngờ | Validator + ràng buộc unique phù hợp |
| Xóa index chỉ vì ít lượt sử dụng ngắn hạn | Hỏng query hiếm nhưng quan trọng | Quan sát đủ chu kỳ nghiệp vụ |
| Thêm `hint` cố định không có số liệu | Query kém khi dữ liệu/index thay đổi | Chỉ hint khi có lý do kiểm chứng |
| Benchmark 12 document | Noise che lấp chi phí | Dùng dữ liệu đủ lớn và workload đại diện |
| Thay index trên production không có kế hoạch | Tác động build/disk/replication/latency | Change management và rollback |

## 21. Bài thực hành tổng hợp

**Bối cảnh:** Một hệ thống bán hàng có 20 triệu đơn, nhiều tenant, lượng ghi lớn. Ba API quan trọng nhất: danh sách đơn PAID mới nhất theo tenant, lịch sử đơn của khách, và tra đơn theo SKU trong item. Hãy thử trên lab và đề xuất bộ index tối thiểu để hỗ trợ các API đó.

### Bài 1 — Index đơn

Tạo `{customerId:1}` rồi truy vấn đơn của `c-101`. Dự đoán ID kết quả, thử `explain("executionStats")`. Tại sao kết quả có thể là `COLLSCAN` trên dataset nhỏ dù index tồn tại?

### Bài 2 — Index thời gian

Tạo `{createdAt:-1}` rồi lấy 5 đơn mới nhất toàn hệ thống. Viết query sort tăng dần và giải thích vì sao không mặc định cần index thứ hai với hướng `1`.

### Bài 3 — Quy tắc prefix

Với index `{tenantId:1,status:1,createdAt:-1}`:

1. Liệt kê ba prefix.
2. Giải thích vì sao query chỉ theo `status` không có prefix thích hợp.
3. Giải thích vì sao query theo tenant và sort createdAt có thể cần index riêng `{tenantId:1,createdAt:-1}`.

### Bài 4 — ESR

Cho query:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  amount: { $gte: NumberDecimal("100000") }
}).sort({ createdAt: -1 }).limit(20)
~~~

So hai index:

~~~javascript
{ tenantId: 1, createdAt: -1, amount: 1 }
{ tenantId: 1, amount: 1, createdAt: -1 }
~~~

Index nào ưu tiên sort? Index nào có cơ hội lọc range sớm hơn? Khi range chỉ khớp 0,1% document, đánh đổi có thể thay đổi ra sao?

### Bài 5 — Sort direction

Với index `{tenantId:1,createdAt:-1,amount:1}` và equality tenant, hãy giải thích:

- Sort `{createdAt:-1,amount:1}`.
- Sort `{createdAt:1,amount:-1}`.
- Sort `{createdAt:-1,amount:-1}`.

Trường hợp nào khớp index pattern hoặc đảo chiều toàn bộ?

### Bài 6 — Covered query

Với index `{tenantId:1,status:1,createdAt:-1}`, viết query chỉ trả ba field đó và loại `_id`. Sau đó thêm `amount` vào projection và quan sát `explain`. Phân biệt **ít field trả về** với **không đọc document**.

### Bài 7 — Multikey

Tạo `{"items.sku":1}` và `{"items.sku":1,"items.qty":1}`. Viết truy vấn tìm một item vừa `sku = "A"` vừa `qty >= 2`; giải thích vai trò của `$elemMatch`.

### Bài 8 — Unique business key

Thiết kế index unique cho `tenantId + orderNo`. Trước khi tạo trên collection cũ, cần kiểm tra những document có orderNo thiếu, null hoặc trùng ra sao? Nêu cách kết hợp validator với partial unique index nếu nghiệp vụ chỉ áp dụng uniqueness cho đơn có mã.

### Bài 9 — Đo và cắt giảm index

Giả sử đã có 8 index khác nhau. Ghi lại `getIndexes()`, `$indexStats` và `indexSizes`. Đề xuất những index có thể trùng tiền tố hoặc ít giá trị, nhưng **không xóa** nếu chưa xác nhận các query hiếm, unique constraint và kế hoạch rollback.

### Bài 10 — Chọn bộ index cuối

Điền bảng dựa trên workload thật:

| Query | Tần suất | SLO | Index ứng viên | Kết quả `explain` | Chi phí ghi/index |
|---|---|---|---|---|---|
| Đơn PAID mới nhất theo tenant | … | … | … | … | … |
| Lịch sử đơn theo customer | … | … | … | … | … |
| Đơn chứa SKU A | … | … | … | … | … |
| Báo cáo amount range | … | … | … | … | … |

Không tự điền số “đã đo” nếu chưa có phép đo; có thể ghi giả định và kế hoạch thử nghiệm.

## 22. Câu hỏi ôn tập và đáp án

**1. Index đơn khác index ghép ở điểm nào?**

Index đơn tổ chức theo một field; index ghép tổ chức theo nhiều field với **thứ tự khóa xác định**. Index ghép không tương đương tập index đơn.

**2. Ba tiền tố của `{tenantId:1,status:1,createdAt:-1}` là gì?**

`{tenantId:1}`, `{tenantId:1,status:1}` và toàn bộ `{tenantId:1,status:1,createdAt:-1}`.

**3. Index đó có thay thế index `{status:1}` cho query chỉ theo status không?**

Không mặc định; status đứng sau tenant nên index không có tiền tố bắt đầu từ status.

**4. Vì sao thiếu equality ở field giữa có thể làm sort kém hiệu quả?**

Key được nhóm theo field giữa, nên thứ tự field sau chỉ đúng trong từng nhóm chứ không nhất thiết là thứ tự toàn bộ kết quả.

**5. Có cần hai index đơn `{createdAt:1}` và `{createdAt:-1}` không?**

Không mặc định. Một index trên một field có thể được quét theo hai hướng; với compound sort nhiều field, pattern chiều phức tạp hơn.

**6. ESR nghĩa là gì?**

Equality–Sort–Range: đặt field equality, rồi sort, rồi range là một heuristic phổ biến. Với range rất chọn lọc, đặt range trước sort đôi khi tốt hơn.

**7. Query có `IXSCAN` là đủ chứng minh nhanh chưa?**

Chưa. Có thể scan rất nhiều key, FETCH nhiều document hoặc SORT. Cần xem số liệu thực thi.

**8. Khi nào query có thể được cover?**

Khi index đủ phục vụ điều kiện và field kết quả trong những điều kiện hỗ trợ, không cần đọc document. Kiểm tra kế hoạch và `totalDocsExamined`.

**9. Unique index có làm field bắt buộc tồn tại không?**

Không. Unique chống trùng key; validation cần quản lý required/type. Null/missing có ngữ nghĩa uniqueness riêng.

**10. Unique compound `{tenantId:1,orderNo:1}` cho phép hai tenant dùng cùng orderNo không?**

Có, vì uniqueness áp dụng cho tổ hợp hai field.

**11. Vì sao `$elemMatch` quan trọng với compound multikey index trên items?**

Nó đảm bảo các predicate trên item cùng thuộc **một phần tử mảng**, đồng thời có thể giúp planner kết hợp index bounds.

**12. Vì sao không nên tạo index ghép chứa tất cả field?**

Index lớn làm tăng chi phí ghi/dung lượng, và thứ tự khóa có thể không phù hợp các query/sort thực tế.

**13. `hint()` nên dùng khi nào?**

Để so sánh hoặc điều tra một index theo cách có kiểm soát, không mặc định buộc production query dùng một index vĩnh viễn.

**14. Có nên xóa index khi `$indexStats` cho thấy ít truy cập trong một giờ không?**

Chưa đủ bằng chứng. Query theo ngày/tháng hoặc thao tác vận hành hiếm có thể vẫn cần nó.

## 23. Bảng lệnh ghi nhớ

| Mục đích | Lệnh |
|---|---|
| Tạo index đơn | `db.orders.createIndex({customerId:1})` |
| Tạo index giảm dần | `db.orders.createIndex({createdAt:-1})` |
| Tạo index ghép | `db.orders.createIndex({tenantId:1,status:1,createdAt:-1})` |
| Tạo unique compound | `db.orders.createIndex({tenantId:1,orderNo:1},{unique:true})` |
| Liệt kê index | `db.orders.getIndexes()` |
| Giải thích truy vấn | `db.orders.find(filter).explain("executionStats")` |
| Giải thích truy vấn có sort | `db.orders.find(filter).sort(sort).explain("executionStats")` |
| Thử một index cụ thể | `db.orders.find(filter).hint("index_name").explain("executionStats")` |
| Xem kích thước index | `db.orders.stats().indexSizes` |
| Xem mức sử dụng | `db.orders.aggregate([{$indexStats:{}}])` |
| Ẩn index nếu được hỗ trợ | `db.orders.hideIndex("index_name")` |
| Hiện lại index | `db.orders.unhideIndex("index_name")` |
| Xóa index | `db.orders.dropIndex("index_name")` |

## 24. Kết luận

**Index đơn** phù hợp khi truy vấn chủ yếu dựa vào một field. **Index ghép** có thể phục vụ hiệu quả một access pattern gồm filter, sort và thậm chí projection, nhưng thứ tự key là yếu tố quyết định: MongoDB tổ chức khóa từ trái sang phải, tận dụng các tiền tố để thu hẹp phạm vi và chỉ phục vụ thứ tự sort khi các điều kiện đứng trước phù hợp.

Hãy bắt đầu từ **filter + sort + projection** của truy vấn thật, dựa vào prefix và ESR để tạo vài index ứng viên, rồi kiểm chứng bằng `explain("executionStats")` cùng workload đại diện. Cuối cùng cân bằng lợi ích đọc với chi phí ghi, disk, cache và vận hành. **Một bộ index đúng cho workload thường có giá trị hơn rất nhiều index không khớp cách ứng dụng truy cập dữ liệu.**
