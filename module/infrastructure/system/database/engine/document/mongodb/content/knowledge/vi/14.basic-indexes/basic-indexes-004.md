# Thứ tự trường, tiền tố index và khả năng dùng lại index trong MongoDB

## 1. Vì sao thứ tự trường trong index lại quan trọng?

Trong MongoDB, index giúp database tìm những document thỏa điều kiện mà không nhất thiết phải duyệt lần lượt toàn bộ collection. Đối với **compound index** (index ghép từ nhiều trường), **thứ tự trường** là một phần của thiết kế index, không chỉ là cách viết.

Giả sử ứng dụng quản lý đơn hàng theo khách hàng doanh nghiệp (tenant) thường nhận các truy vấn:

1. Tìm mọi đơn thuộc một tenant.
2. Tìm các đơn thuộc một tenant ở trạng thái `PAID`.
3. Trong một tenant và một trạng thái, lấy đơn mới nhất trước.
4. Tìm các đơn của một trạng thái trên **mọi tenant**.
5. Lọc đơn trong một khoảng thời gian mà không có tenant.

Một index như:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

thường phục vụ tốt nhóm truy vấn 1–3, nhưng không mặc định tối ưu cho 4–5. Nguyên nhân là các khóa index được sắp xếp **theo thứ tự từ trái sang phải**: `tenantId` trước, `status` tiếp theo, rồi `createdAt` trong từng nhóm giá trị đã xác định.

Đây là chủ đề của bài học: **thứ tự trường, tiền tố index và khả năng dùng lại index**. Sau khi học, bạn sẽ:

- Hiểu cách compound index sắp xếp khóa và vì sao thứ tự trường ảnh hưởng đến truy vấn.
- Nhận diện **prefix** (tiền tố) của một index ghép.
- Biết khi nào một index ghép có thể phục vụ nhiều query pattern khác nhau.
- Hiểu điều kiện để index hỗ trợ `sort()`, cả hướng thuận và hướng đảo.
- Áp dụng nguyên tắc **Equality – Sort – Range (ESR)** như một điểm xuất phát khi thiết kế.
- Biết đọc `explain("executionStats")` để quan sát index được chọn và chi phí thực thi.
- Tránh tạo index trùng lặp hoặc dựa vào một index không phù hợp với mẫu truy vấn quan trọng.

## 2. Index đơn và index ghép

### 2.1. Single-field index

Một index đơn chỉ chứa một trường khóa:

```javascript
db.orders.createIndex({ tenantId: 1 });
```

Giá trị `1` biểu thị thứ tự tăng dần. `-1` biểu thị thứ tự giảm dần. Với index đơn trên trường scalar, MongoDB thường có thể duyệt index theo chiều thuận hoặc ngược để phục vụ sắp xếp tăng/giảm, nên việc chọn `1` hay `-1` thường ít quan trọng hơn so với index ghép có nhiều hướng hỗn hợp.

Các trường hợp đặc biệt như multikey, collation, text, hashed, wildcard hoặc geospatial index có quy tắc riêng. Trong bài này, trước tiên xét **B-tree index thông thường trên các trường scalar**.

### 2.2. Compound index

Một compound index lưu nhiều trường theo thứ tự đã khai báo:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Thứ tự khóa về mặt khái niệm:

```text
(tenantId ASC, status ASC, createdAt DESC)

tenant A
 ├── status CANCELLED
 │     ├── createdAt mới nhất
 │     └── createdAt cũ hơn
 ├── status NEW
 │     ├── createdAt mới nhất
 │     └── createdAt cũ hơn
 └── status PAID
       ├── createdAt mới nhất
       └── createdAt cũ hơn

tenant B
 ├── status NEW
 │     └── ...
 └── status PAID
       └── ...
```

Đây là sơ đồ minh họa thứ tự khóa, không phải hình ảnh vật lý chính xác của từng trang B-tree. Ý nghĩa cần nhớ:

1. Những khóa có cùng `tenantId` thường ở cùng một vùng logic.
2. Trong vùng của một tenant, những khóa có cùng `status` tiếp tục được nhóm.
3. Trong nhóm tenant + status, `createdAt` được sắp theo hướng đã chọn.

Vì vậy, nếu đã biết `tenantId` và `status`, database có thể đi đến một khoảng khóa hẹp và đọc các đơn theo thứ tự ngày mà không cần sắp xếp lại toàn bộ tập dữ liệu.

### 2.3. Index không phải “ba index đơn gộp lại”

Index ghép `{ tenantId: 1, status: 1, createdAt: -1 }` không tương đương với ba index đơn:

```javascript
{ tenantId: 1 }
{ status: 1 }
{ createdAt: -1 }
```

Ba index đơn có thể hỗ trợ từng điều kiện riêng và MongoDB có thể cân nhắc một số cách kết hợp index trong những tình huống thích hợp. Tuy nhiên, không nên mặc định index intersection sẽ cung cấp cùng hiệu quả lọc và cùng thứ tự sort như một compound index đúng với query pattern.

Compound index có lợi thế ở chỗ **các trường nằm chung trong một khóa có thứ tự xác định**. Đây là lý do không thể bỏ qua thứ tự trường khi tối ưu các điều kiện kết hợp.

## 3. Tiền tố index (index prefix)

### 3.1. Định nghĩa

Với index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

các **prefix liên tiếp tính từ trường đầu tiên** là:

```javascript
{ tenantId: 1 }

{ tenantId: 1, status: 1 }

{ tenantId: 1, status: 1, createdAt: -1 }
```

Các tập sau **không phải prefix** của index trên:

```javascript
{ status: 1 }
{ createdAt: -1 }
{ status: 1, createdAt: -1 }
{ tenantId: 1, createdAt: -1 } // Bỏ qua status ở giữa
```

Điểm cuối dễ nhầm: `{tenantId, createdAt}` vẫn có trường đầu là `tenantId`, nhưng **không phải prefix liên tiếp** vì bỏ qua `status`. Nó có thể tận dụng một phần index để lọc theo tenant và đôi khi dùng thêm trường sau ở mức kiểm tra khóa, nhưng không có đủ lợi thế của việc thu hẹp liên tiếp theo `tenantId → status → createdAt`.

### 3.2. Index ghép có thể dùng lại cho truy vấn prefix

Với index trên, các truy vấn sau thường có khả năng tận dụng index:

```javascript
// Prefix một trường.
db.orders.find({ tenantId: "TENANT-A" });

// Prefix hai trường.
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
});

// Prefix đầy đủ, trường cuối là khoảng.
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

Đây là ý nghĩa chính của **khả năng dùng lại index**: một compound index được thiết kế hợp lý có thể phục vụ nhiều truy vấn có điều kiện trên các prefix khác nhau.

Nhưng “có thể sử dụng” và “sẽ được query planner chọn” không giống nhau. Với collection nhỏ, độ chọn lọc thấp hoặc khi việc đọc index rồi fetch document tốn hơn collection scan, optimizer vẫn có thể chọn `COLLSCAN`. Cần kiểm tra bằng `explain()` trên dữ liệu đại diện.

### 3.3. Query không có trường đầu tiên

Các truy vấn:

```javascript
db.orders.find({ status: "PAID" });

db.orders.find({
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
});
```

không có điều kiện trên `tenantId`, tức bỏ qua trường dẫn đầu của index. Index ghép nêu trên thường **không hiệu quả** để thu hẹp vùng tìm kiếm cho chúng. Một số kế hoạch vẫn có thể quét index và lọc, nhưng điều đó không tương đương một lần tra cứu hẹp theo khóa `status` hoặc `createdAt`.

Nếu truy vấn mọi tenant theo `status` hoặc ngày là một use case có tần suất cao, cần cân nhắc index khác với trường dẫn đầu phù hợp, ví dụ:

```javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
```

Không nên đặt thêm index chỉ vì một query có tồn tại; hãy xem tần suất sử dụng, số lượng document trả về, độ chọn lọc và chi phí index.

### 3.4. Không cần viết filter theo cùng thứ tự như index

Trong JavaScript, hai filter dưới đây có cùng điều kiện:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
});

db.orders.find({
  status: "PAID",
  tenantId: "TENANT-A"
});
```

**Thứ tự viết field trong filter không quyết định thứ tự khóa index.** MongoDB query planner xem điều kiện và index có sẵn. Thứ tự **khai báo khi tạo compound index** mới là điều có ảnh hưởng lớn đến cách các khóa được sắp xếp.

## 4. Thiết lập dữ liệu thử nghiệm bằng `mongosh`

Để quan sát các nguyên tắc trên, ta tạo database riêng và một vài đơn hàng mẫu. Chỉ chạy trên MongoDB mà bạn được phép ghi dữ liệu, không thực hiện trên collection production.

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Thay URI theo cấu hình MongoDB local của bạn. Trong shell:

```javascript
const lab = db.getSiblingDB("mongo_index_row150_lab");
const orders = lab.getCollection("orders_demo");

// Mỗi lượt có một tenant riêng để không đè dữ liệu bài thử khác.
const tenantId = "row150-" + new ObjectId().toHexString();
const runId = tenantId;

const samples = [
  { status: "NEW",       day: "2026-11-01T03:00:00Z", amountCents: 100000 },
  { status: "NEW",       day: "2026-11-03T03:00:00Z", amountCents: 150000 },
  { status: "NEW",       day: "2026-11-09T03:00:00Z", amountCents: 180000 },
  { status: "PAID",      day: "2026-11-02T04:00:00Z", amountCents: 200000 },
  { status: "PAID",      day: "2026-11-05T04:00:00Z", amountCents: 250000 },
  { status: "PAID",      day: "2026-11-10T04:00:00Z", amountCents: 300000 },
  { status: "PAID",      day: "2026-11-12T04:00:00Z", amountCents: 220000 },
  { status: "SHIPPED",   day: "2026-11-04T05:00:00Z", amountCents: 350000 },
  { status: "SHIPPED",   day: "2026-11-08T05:00:00Z", amountCents: 190000 },
  { status: "CANCELLED", day: "2026-11-06T06:00:00Z", amountCents: 50000 }
];

orders.insertMany(samples.map((item, index) => ({
  _id: new ObjectId(),
  runId,
  tenantId,
  externalOrderId: "DEMO-" + String(index + 1).padStart(3, "0"),
  status: item.status,
  createdAt: ISODate(item.day),
  amountCents: item.amountCents
})));

orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "tenant_status_createdAt" }
);

printjson(orders.getIndexes());
```

Mọi truy vấn theo một tenant trong bài dùng `tenantId` đã sinh, không cần giả lập nhiều tenant. Trong triển khai thực, môi trường thường có nhiều tenant với số lượng đơn khác nhau; **độ phân bố dữ liệu** là yếu tố cần đánh giá khi tối ưu index.

> Các ví dụ `explain()` với chỉ 10 document phục vụ học cách đọc kết quả, không nhằm chứng minh hiệu năng. Khi dữ liệu nhỏ, optimizer có thể chọn collection scan; index hiệu quả trong hệ thống thật phải được đo trên số lượng document và phân bố tương đương production.

## 5. Ba truy vấn tận dụng các prefix khác nhau

### 5.1. Tìm mọi đơn của tenant

```javascript
orders.find(
  { tenantId },
  { _id: 0, externalOrderId: 1, status: 1, createdAt: 1 }
);
```

Điều kiện `tenantId` trùng với prefix một trường. Index có thể định vị vùng khóa thuộc tenant đó thay vì xét toàn bộ tenant trên collection.

Lưu ý: khi lấy toàn bộ đơn của một tenant, kết quả từ index ghép được nhóm theo `status` rồi mới theo `createdAt`. Nếu ứng dụng cần **mọi đơn của tenant, sắp xếp mới nhất trên toàn bộ trạng thái**, index hiện tại không nhất thiết cung cấp đúng thứ tự sort.

### 5.2. Tìm đơn theo tenant và trạng thái

```javascript
orders.find(
  { tenantId, status: "PAID" },
  { _id: 0, externalOrderId: 1, createdAt: 1 }
);
```

Điều kiện có hai trường đầu của compound index. Database có thể thu hẹp vùng khóa theo cả tenant và status.

### 5.3. Tìm đơn đã thanh toán trong khoảng ngày

```javascript
orders.find(
  {
    tenantId,
    status: "PAID",
    createdAt: {
      $gte: ISODate("2026-11-05T00:00:00Z"),
      $lt: ISODate("2026-11-13T00:00:00Z")
    }
  },
  { _id: 0, externalOrderId: 1, createdAt: 1, amountCents: 1 }
).sort({ createdAt: -1 });
```

Ở đây:

- `tenantId` được lọc bằng equality.
- `status` cũng được lọc bằng equality.
- `createdAt` là một khoảng trên trường thứ ba, đồng thời là khóa sort.

Các document cùng tenant và status nằm trong một vùng khóa. Bên trong vùng đó, `createdAt` có thứ tự giảm dần, vì vậy index thường giúp lọc khoảng và trả dữ liệu theo thứ tự ngày như yêu cầu.

## 6. Thứ tự trường quyết định hiệu quả khi lọc kết hợp

Xét ba index có cùng ba field nhưng thứ tự khác:

```javascript
// Index A
{ tenantId: 1, status: 1, createdAt: -1 }

// Index B
{ status: 1, tenantId: 1, createdAt: -1 }

// Index C
{ tenantId: 1, createdAt: -1, status: 1 }
```

Với filter:

```javascript
{
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}
```

cả A và B đều đặt **hai điều kiện equality** trước điều kiện range `createdAt`. Khi cả `tenantId` và `status` luôn được chỉ định, cả hai có thể là ứng viên hợp lý. Nhưng khả năng dùng lại khác nhau:

- Index A có prefix `tenantId`, phục vụ truy vấn theo tenant không cần status.
- Index B có prefix `status`, phục vụ truy vấn theo trạng thái trên mọi tenant.
- Index C có prefix `tenantId` rồi `createdAt`, hữu ích cho lịch sử tất cả đơn của một tenant theo thời gian, nhưng `status` đứng sau trường range `createdAt` nên khả năng thu hẹp vùng theo status có thể kém hơn so với A khi lọc status và ngày.

Không thể xếp hạng A, B, C tuyệt đối mà không biết **tập truy vấn nào quan trọng nhất** và phân bố giá trị trong dữ liệu.

### 6.1. Bảng lựa chọn theo query pattern

| Query pattern | Index thường đáng cân nhắc | Giải thích |
| --- | --- | --- |
| `{tenantId}` | `{tenantId:1, status:1, createdAt:-1}` | Có prefix tenant |
| `{tenantId, status}` | `{tenantId:1, status:1, createdAt:-1}` | Dùng hai field đầu |
| `{tenantId, status}` + sort `createdAt:-1` | `{tenantId:1, status:1, createdAt:-1}` | Equality trước khóa sort |
| `{tenantId}` + sort `createdAt:-1` | `{tenantId:1, createdAt:-1}` | Không bị `status` chen giữa |
| `{status}` trên tất cả tenant | `{status:1, createdAt:-1}` | Status đứng đầu |
| Chỉ có khoảng `createdAt` | `{createdAt:-1}` | Ngày đứng đầu |
| `{tenantId, createdAt range}`, không lọc status | `{tenantId:1, createdAt:-1}` | Prefix phù hợp bộ lọc và sort |

Bảng thể hiện nguyên tắc lựa chọn, **không phải yêu cầu tạo toàn bộ các index**. Mỗi index tốn dung lượng và làm tăng công việc khi insert/update/delete. Cần chọn một tập nhỏ phục vụ truy vấn phổ biến và có độ chọn lọc tốt.

### 6.2. “Trường có cardinality cao nhất phải đặt đầu” có luôn đúng?

Không. Độ phân biệt (selectivity/cardinality) là một yếu tố, nhưng không thay thế hiểu biết về **prefix reuse và sort**. Khi truy vấn luôn có equality trên cả `tenantId` và `status`, cả hai thứ tự có thể giúp định vị bộ khóa đủ hẹp. Nhưng nếu phần lớn API luôn ràng buộc tenant và nhiều API không có status, đặt `tenantId` đầu có thể tạo khả năng dùng lại đáng giá.

Với dữ liệu nhiều tenant, còn phải cân nhắc quyền truy cập, thiết kế shard key, phân vùng khối lượng và tần suất các truy vấn quản trị xuyên tenant. Không nên áp dụng một “quy tắc cardinality” duy nhất mà bỏ qua các query pattern.

## 7. Index có hỗ trợ `sort()` hay không?

### 7.1. Sắp xếp trong một nhóm có điều kiện equality

Index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

trong nhóm mà `tenantId` và `status` đã cố định, khóa `createdAt` có thứ tự giảm dần.

```javascript
orders.find({
  tenantId,
  status: "PAID"
}).sort({ createdAt: -1 });
```

Đây là mẫu lý tưởng: các trường **đứng trước trường sort** đã có điều kiện equality, nên index có thể cấp dữ liệu đúng thứ tự ngày mà không cần một bước sắp xếp chặn (*blocking sort*) riêng.

### 7.2. Nếu thiếu equality ở một trường đứng trước khóa sort

```javascript
orders.find({
  tenantId
}).sort({ createdAt: -1 });
```

Trong index A, các document của tenant được nhóm theo `status` trước khi xét `createdAt`. Do đó thứ tự toàn bộ document không phải “mới nhất trước” trên mọi status.

Khả năng tận dụng index để lọc theo tenant vẫn có, nhưng truy vấn có thể cần một bước `SORT` bổ sung hoặc một index khác:

```javascript
orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "tenant_createdAt" }
);
```

Index `tenant_createdAt` phù hợp hơn cho trang “tất cả đơn của tenant, mới nhất trước”. Tuy nhiên, index này không thay thế hoàn toàn lợi ích của `tenant_status_createdAt` cho trang có filter trạng thái; lựa chọn dựa trên tần suất của hai màn hình.

### 7.3. Sort theo prefix của index

Với index `{tenantId:1, status:1, createdAt:-1}`, có thể tận dụng thứ tự khóa cho `sort({tenantId:1, status:1})` hoặc `sort({tenantId:1, status:1, createdAt:-1})` trong điều kiện thích hợp.

Một **non-prefix subset** của sort key cũng có thể được hỗ trợ nếu các field index đứng trước nó đều được cố định bằng equality. Ví dụ:

```javascript
orders.find({
  tenantId,
  status: "PAID"
}).sort({ createdAt: -1 });
```

Ở đây sort chỉ nêu `createdAt`; nó không phải prefix của index. Nhưng hai khóa đứng trước đã là equality nên việc duyệt vùng index tương ứng có đúng thứ tự `createdAt`.

Nếu filter có điều kiện range trên một field đứng trước sort, khả năng tránh SORT có thể khác và thường bị hạn chế. Cần đọc kế hoạch thực tế thay vì chỉ nhìn tên các field.

### 7.4. Hướng thuận, hướng đảo và sort hỗn hợp

Index:

```javascript
{ a: 1, b: -1 }
```

thường hỗ trợ các kiểu sort theo cùng pattern hướng:

```javascript
{ a: 1,  b: -1 }  // Duyệt thuận.
{ a: -1, b: 1 }   // Duyệt ngược toàn index.
```

Nhưng khi cả hai field thay đổi hướng giống nhau:

```javascript
{ a: 1, b: 1 }
```

thì index `{a:1,b:-1}` không mặc nhiên cho đúng thứ tự đó khi cả `a` và `b` đều biến đổi trong tập kết quả. Muốn dùng index cho kiểu sort này có thể cần tạo pattern hướng phù hợp.

**Ngoại lệ do equality:** nếu `a` đã cố định bằng equality, chỉ còn thứ tự của `b` thay đổi. Duyệt thuận hoặc đảo ở vùng khóa đó thường có thể cho `b` tăng hoặc giảm mà không cần hai index riêng. Do đó khi phân tích hướng sort, phải xét đồng thời **filter equality**, không chỉ so hai object sort.

### 7.5. Sort ổn định và phân trang

Sắp xếp chỉ theo `createdAt` có thể có nhiều document cùng timestamp. Với phân trang, nên thêm tie-breaker xác định như `_id`:

```javascript
orders.find({
  tenantId,
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Nếu đây là query quan trọng, có thể cân nhắc index:

```javascript
orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "tenant_status_createdAt_id" }
);
```

Index này thêm `_id` làm khóa sort cuối. Đừng hiểu rằng một index trên `createdAt` tự động có cùng thứ tự `_id` khi giá trị timestamp trùng. Một số chi tiết lưu trữ có thể dùng RecordId nội bộ để phân biệt khóa, nhưng thứ tự đó không thay thế hợp đồng sắp xếp rõ ràng của ứng dụng.

## 8. Nguyên tắc Equality – Sort – Range (ESR)

Khi thiết kế compound index, quy tắc **ESR** là điểm xuất phát hữu ích:

1. **Equality:** đặt các trường được so sánh bằng `=`/`$eq` trước.
2. **Sort:** đặt các trường phục vụ thứ tự kết quả tiếp theo.
3. **Range:** đặt các trường dùng so sánh phạm vi như `$gt`/`$gte`/`$lt`/`$lte` sau cùng.

Ví dụ query:

```javascript
db.products.find({
  category: "book",
  price: { $gte: 100000, $lt: 500000 }
}).sort({ rating: -1 });
```

Ứng viên ESR:

```javascript
{ category: 1, rating: -1, price: 1 }
```

Trong đó:

- `category` là equality.
- `rating` là sort.
- `price` là range.

Đặt sort trước range có thể giúp truy vấn lấy dữ liệu theo thứ tự `rating` từ index mà không cần sắp xếp lại một lượng lớn document. Nhưng mức độ lọc bởi `price` có thể không tốt bằng index có range đứng trước.

### 8.1. Khi nào cân nhắc Equality – Range – Sort (ERS)?

Với cùng query, một index khác:

```javascript
{ category: 1, price: 1, rating: -1 }
```

có thể thu hẹp tốt hơn theo `price` nếu khoảng giá cực kỳ chọn lọc. Đổi lại, index không nhất thiết trả được kết quả theo thứ tự `rating` trên toàn khoảng giá mà không cần sắp xếp bổ sung.

Một lựa chọn nào nhanh hơn phụ thuộc:

- Tập giá trị `price` trong collection.
- Khoảng lọc trả về bao nhiêu document.
- Có `limit` hay không và giới hạn bao nhiêu.
- Tỷ lệ document phải đọc so với số document trả về.
- Mức chi phí của SORT so với đọc thêm khóa index.

**ESR là hướng dẫn, không phải quy luật tuyệt đối.** Khi range rất chọn lọc, ERS có thể tốt hơn. Khi ưu tiên tránh blocking sort và lấy một tập kết quả giới hạn, ESR có thể phù hợp. Dùng `explain("executionStats")` và thử với dữ liệu đại diện để quyết định.

### 8.2. Nhiều trường equality: thứ tự nào trước?

Ví dụ query luôn có:

```javascript
{
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}
```

Hai index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ status: 1, tenantId: 1, createdAt: -1 }
```

đều đặt các điều kiện equality trước range. Với query có cả hai equality, chúng có thể cùng là ứng viên hợp lý. Câu hỏi quan trọng là **các query khác dùng prefix nào**:

- API tenant luôn lọc `tenantId`, nhưng đôi khi không lọc `status` → thiên về `tenantId` trước.
- Dashboard quản trị thường xem mọi tenant theo `status` → có thể cần index bắt đầu bằng `status`.

Nên tối ưu **tập workload**, không chỉ một query riêng lẻ.

### 8.3. `$in`, `$ne` và nhiều điều kiện khác

Không phải mọi operator đều là equality hay range thuần túy trong mọi hoàn cảnh:

- `$eq` với một giá trị là equality rõ ràng.
- `$in` chứa nhiều giá trị có thể được tối ưu như nhiều equality hoặc theo chiến lược khác; tác động đến sort và index tùy số phần tử, phiên bản, kế hoạch thực thi.
- `$ne` và `$nin` thường khó chọn lọc và có thể đòi hỏi quét nhiều khóa.
- `$regex` chỉ có một số pattern, như regex tiền tố nhạy case, có thể được tận dụng hiệu quả bởi index B-tree trong điều kiện phù hợp.
- Collation có thể thay đổi cách so sánh string và khả năng dùng index.

Vì vậy không nên gán cứng nhãn ESR chỉ dựa trên tên toán tử mà không xem dạng biểu thức, số giá trị và query plan.

## 9. Các trường hợp “dùng lại index” thường bị hiểu sai

### 9.1. Một index dài có thể bao trùm index prefix ngắn hơn

Nếu collection đã có:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

thì nhiều truy vấn `{tenantId}` có thể dùng nó, không nhất thiết phải thêm:

```javascript
{ tenantId: 1 }
```

Nếu hai index đều thông thường, không khác nhau về unique/sparse/partial/collation hoặc những tùy chọn quan trọng khác, index prefix ngắn có thể trở nên **dư thừa** về mặt khả năng phục vụ truy vấn. Việc giữ index ngắn đôi khi vẫn có giá trị do nhỏ hơn và rẻ hơn cho một số workload; nhưng không nên tạo mặc định trước khi đo.

MongoDB không tự bảo đảm mọi index được tạo ra đều cần thiết hoặc tự loại toàn bộ index trùng lặp khi thiết kế schema. Trước khi thêm một index mới, hãy xem danh sách đã có và prefix của chúng.

### 9.2. Compound unique index không làm prefix cũng unique

```javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
);
```

Index này cho phép:

```text
(tenant A, user@example.test)
(tenant B, user@example.test)
```

vì hai cặp khóa khác nhau. Nó **không** bắt email duy nhất trên toàn bộ collection, cũng không bắt mỗi tenant chỉ có một document.

Thêm một unique index trên `{tenantId:1}` sẽ tạo ra **ràng buộc nghiệp vụ khác hẳn** (mỗi tenant tối đa một document), không thể coi là index prefix dư thừa.

Tính duy nhất luôn áp cho **toàn bộ key** trong phạm vi của index, cùng các quy tắc về collation, partial filter và dữ liệu null/thiếu field có liên quan.

### 9.3. Partial index không thay thế index đầy đủ cho mọi truy vấn

Ví dụ chỉ index các đơn đang hoạt động:

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    partialFilterExpression: { active: true },
    name: "active_tenant_createdAt"
  }
);
```

Index này chỉ chứa các document thỏa `active: true`. Truy vấn chỉ lọc `tenantId` nhưng không hạn chế `active` không thể tùy ý dùng index đó để lấy đủ mọi order. Để planner dùng partial index mà không bỏ sót kết quả, predicate truy vấn phải phù hợp với điều kiện partial index.

Hai index có cùng trường khóa nhưng khác partial filter **không tương đương** về tập document được index.

### 9.4. Sparse index có phạm vi khác index thông thường

Sparse index chỉ index các document có field được đánh index theo quy tắc của loại index. Với compound sparse index, hành vi phụ thuộc các trường và kiểu index. Vì vậy không thể kết luận index sparse thay thế index thường chỉ vì cùng thứ tự key. Một query yêu cầu cả document thiếu field cũng phải được trả đủ; sử dụng sparse index không đúng có thể làm thiếu kết quả nên planner cần cân nhắc tính đầy đủ.

### 9.5. Collation phải khớp nhu cầu so sánh chuỗi

Giả sử đã tạo:

```javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  {
    collation: { locale: "vi", strength: 2 },
    name: "tenant_name_vi"
  }
);
```

Query equality trên `name` dùng simple collation mặc định có thể không tận dụng index `tenant_name_vi` cho so sánh chuỗi như kỳ vọng. Cần dùng operation collation phù hợp:

```javascript
db.customers.find({
  tenantId: "TENANT-A",
  name: "Nguyễn An"
}).collation({
  locale: "vi",
  strength: 2
});
```

Khi index có prefix trường không phải string như `tenantId`, một số kế hoạch vẫn có thể dùng phần index đó dù collation không khớp để phục vụ trường `name`; đừng suy luận cả index hoàn toàn vô dụng. Tuy nhiên, **khả năng dùng lại cho string equality/sort phụ thuộc vào collation tương thích**.

Đặc biệt, `$regex` không collation-aware theo cách equality. Một index có collation không phân biệt case không đồng nghĩa regex `/abc/i` được tối ưu nhờ quy tắc collation ấy.

### 9.6. Các loại index đặc thù không tuân theo mọi ví dụ B-tree thông thường

Text, wildcard, hashed, 2dsphere, multikey, TTL và những loại index khác có quy tắc và giới hạn riêng. Ví dụ hashed index phục vụ tra cứu hash equality, không hỗ trợ range và sort theo trường gốc giống index tăng/giảm thông thường.

Không dùng bảng prefix cho B-tree scalar trong bài này để suy ra mọi tổ hợp khóa của index đặc thù đều có hành vi tương tự.

## 10. Multikey index và trường mảng

### 10.1. Khi một field trong compound index là mảng

Giả sử document sản phẩm có nhiều tag:

```javascript
{
  tenantId: "TENANT-A",
  tags: ["mongo", "database"],
  price: 250000
}
```

Index:

```javascript
db.products.createIndex({
  tenantId: 1,
  tags: 1,
  price: 1
});
```

khi index trường mảng sẽ trở thành **multikey index**. Một document có thể đóng góp nhiều khóa index, tùy giá trị mảng. Truy vấn:

```javascript
db.products.find({
  tenantId: "TENANT-A",
  tags: "mongo"
});
```

có thể tận dụng index này. Nhưng khi xét covered query và sort trên trường mảng, cần hiểu các hạn chế của multikey. Không mặc định mọi truy vấn theo prefix trên mảng có cùng chi phí với field scalar.

### 10.2. Không phải mọi tổ hợp hai mảng đều index ghép được

Compound multikey index có giới hạn đối với việc một document chứa các trường mảng ở nhiều thành phần của cùng index. Trong trường hợp MongoDB xem đây là các mảng song song không hợp lệ, tạo index hoặc ghi document có thể bị từ chối.

Ví dụ khái niệm:

```javascript
{
  labels: ["A", "B"],
  categories: ["X", "Y"]
}
```

Không nên tùy tiện tạo compound index `{labels:1, categories:1}` cho các document có cả hai trường là mảng độc lập rồi kỳ vọng MongoDB nhân mọi tổ hợp. Cần xem cấu trúc tài liệu và những hạn chế multikey, hoặc mô hình lại dữ liệu cho truy vấn mong muốn.

## 11. Covered queries: dùng index mà không phải đọc document

### 11.1. Khái niệm

Một **covered query** có thể được trả lời bằng dữ liệu có trong index mà không cần fetch document, khi thỏa các điều kiện phù hợp về field được lọc, projection, index type, collation và các giới hạn khác.

Giả sử index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Một truy vấn chỉ cần hai trường đã có trong index:

```javascript
orders.find(
  {
    tenantId,
    status: "PAID"
  },
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
);
```

Với dữ liệu scalar và điều kiện phù hợp, đây là ứng viên cho index-covered query: các trường trong filter/projection đều có trong index. Việc đặt `_id: 0` quan trọng vì MongoDB trả `_id` theo mặc định; nếu index không chứa `_id` mà projection vẫn yêu cầu `_id`, engine có thể phải đọc document.

Không phải cứ projection ít field là covered. Nếu projection có `amountCents` mà index không chứa trường này, query phải lấy thêm từ document, trừ khi dùng index khác có trường phù hợp.

### 11.2. Đánh giá covered query bằng explain

```javascript
const plan = orders.find(
  { tenantId, status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
).explain("executionStats");

printjson(plan);
```

Khi thực sự được cover, execution stats thường cho thấy `totalDocsExamined` bằng 0 và index scan đáp ứng kết quả. Tuy nhiên, cấu trúc stage có thể khác giữa phiên bản/engine (ví dụ plan không luôn biểu diễn bằng một đường `IXSCAN → PROJECTION_COVERED` y hệt). Hãy dựa trên **số liệu và trường hợp cụ thể**, không chỉ tìm một chuỗi stage.

### 11.3. Có nên thêm mọi field hiển thị vào index?

Không. Mỗi field bổ sung làm index lớn hơn, tốn RAM/cache/disk hơn và tăng chi phí cập nhật. Với một truy vấn quan trọng, thêm một số field để đạt covered query có thể đáng giá; với API lấy document đầy đủ, việc mở rộng index để bao trùm mọi field thường không có lợi.

Hãy phân tích query hot path, số document đọc, tỷ lệ cache hit và write overhead trước khi mở rộng index.

## 12. Đọc `explain("executionStats")` để xác minh khả năng dùng lại

### 12.1. Quan sát query planner

Trong `mongosh`:

```javascript
const explanation = orders.find({
  tenantId,
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).explain("executionStats");

printjson(explanation);
```

Tùy MongoDB version, plan có thể là cây stage cổ điển hoặc cấu trúc của engine khác. Các thông tin thường cần tìm:

| Dấu hiệu | Diễn giải |
| --- | --- |
| `COLLSCAN` | Duyệt collection |
| `IXSCAN` | Quét index |
| `FETCH` | Đọc document từ collection sau khi xác định khóa |
| `SORT` | Có bước sắp xếp riêng, có thể ảnh hưởng chi phí |
| `indexName` | Tên index đã dùng |
| `indexBounds` | Khoảng khóa index được duyệt, nếu hiển thị ở plan |
| `nReturned` | Số document trả về |
| `totalKeysExamined` | Số khóa index đã quét |
| `totalDocsExamined` | Số document được kiểm tra |
| `executionTimeMillis` | Thời gian thực thi được báo cáo; có thể biến động theo cache và điều kiện chạy |

### 12.2. Phân biệt index được chọn và index có khả năng dùng

Một index **có thể** phục vụ điều kiện không có nghĩa optimizer **bắt buộc** chọn nó. MongoDB planner so sánh các kế hoạch khả thi, xem tính chọn lọc và chi phí dự kiến. Một index có thể được dùng cho một số điều kiện nhưng không hỗ trợ sort; query có thể vẫn cần `FETCH` hoặc `SORT`.

Để khảo sát index ứng viên, `hint()` có thể ép planner thử một index:

```javascript
printjson(
  orders.find(
    { tenantId, status: "PAID" }
  ).hint("tenant_status_createdAt").explain("executionStats")
);
```

`hint()` hữu ích trong thử nghiệm, nhưng không nên đưa vào mọi truy vấn production chỉ để buộc dùng index. Ép một index không phù hợp có thể làm chậm truy vấn khi dữ liệu và workload thay đổi.

### 12.3. Hai query có cùng filter nhưng khác sort

So sánh:

```javascript
// Q1: có equality trên tenantId + status.
orders.find({
  tenantId,
  status: "PAID"
}).sort({ createdAt: -1 });

// Q2: chỉ có equality trên tenantId, sort trên createdAt.
orders.find({
  tenantId
}).sort({ createdAt: -1 });
```

Với index `tenant_status_createdAt`, Q1 thường phù hợp hơn vì mọi trường đứng trước `createdAt` đã được cố định. Q2 có thể phải sắp xếp các document giữa nhiều nhóm status. Khi thực hành với dữ liệu đủ lớn, dùng `explain` để quan sát sự khác nhau giữa các kế hoạch.

## 13. Tránh index trùng và chi phí ghi quá lớn

### 13.1. Mỗi index đều có chi phí

Một collection có nhiều index phải cập nhật các cấu trúc index khi insert, delete và khi update làm thay đổi field được index. Index cũng dùng dung lượng disk, RAM/cache và thời gian cho thao tác quản trị. Vì vậy:

```javascript
{ tenantId: 1 }
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

không nhất thiết là bốn index phải cùng tồn tại. Chúng có các quan hệ prefix; index dài hơn có thể phục vụ nhiều truy vấn của index ngắn hơn. Nhưng vẫn cần xét sự khác biệt về **kích thước và tốc độ**, unique/partial/collation và vai trò của từng index trong workload.

### 13.2. Đặt câu hỏi trước khi thêm index mới

1. Query nào đang chậm hoặc có tần suất cao?
2. Filter thường cố định những field nào bằng equality?
3. Có sort/range không? Thứ tự và hướng sort là gì?
4. Các truy vấn khác có dùng chung prefix không?
5. Index sẵn có nào có cùng prefix, cùng collation, cùng phạm vi partial/sparse?
6. Có ràng buộc unique nào không được thay đổi?
7. Số lượng khóa index dự kiến và chi phí ghi bổ sung là bao nhiêu?
8. `explain("executionStats")` cho thấy cải thiện thực sự không?

Đặt mục tiêu phục vụ **một nhóm query pattern quan trọng bằng tập index tối thiểu hợp lý**, chứ không phải tạo một index khác cho từng biến thể câu lệnh.

### 13.3. Index nào phù hợp với workload ví dụ?

Ứng dụng có hai API rất thường dùng:

- **API A:** `GET /orders?tenantId=T&status=PAID`, sắp theo `createdAt` mới nhất.
- **API B:** `GET /orders?tenantId=T`, sắp theo `createdAt` mới nhất trên mọi trạng thái.

Có thể cân nhắc giữ:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, createdAt: -1 }
```

Index đầu phục vụ API A. Index thứ hai phục vụ API B. Dù cả hai đều bắt đầu bằng `tenantId`, không index nào là prefix đầy đủ của index còn lại vì thứ tự trường thứ hai khác nhau; mỗi index giải quyết một kiểu sắp xếp cụ thể.

Nếu API A hiếm và chỉ trả rất ít document, có thể không cần index riêng cho nó; query planner có thể dùng index khác rồi lọc thêm với chi phí chấp nhận được. Quyết định cuối dựa trên dữ liệu thực tế.

## 14. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| “Index ghép chứa field nào cũng tìm field đó nhanh như index đơn” | Vị trí trường và prefix quyết định khả năng thu hẹp vùng khóa |
| “Filter phải viết field theo đúng thứ tự index” | Thứ tự field trong object filter thường không quyết định; thứ tự key của index mới quan trọng |
| “`{a:1,b:1,c:1}` phục vụ tốt `{b,c}` như `{a,b}`” | `{b,c}` bỏ qua field đầu; thường mất lợi thế prefix |
| “Có index thì truy vấn chắc chắn dùng nó” | Query planner có thể chọn COLLSCAN hoặc index khác |
| “Một index ghép là ba index đơn” | Nó là một cấu trúc khóa có thứ tự từ trái sang phải |
| “Index `{a:1,b:-1}` dùng cho mọi hướng sort trên a và b” | Có thể duyệt thuận/đảo pattern, nhưng không tùy ý đảo riêng một field khi cả hai biến đổi |
| “Cứ equality, sort, range đúng thứ tự là tối ưu” | ESR chỉ là điểm xuất phát; độ chọn lọc và workload có thể ưu tiên phương án khác |
| “Chỉ cần index prefix dài nhất, mọi index ngắn hơn luôn vô dụng” | Index ngắn có thể nhỏ/rẻ hơn; unique, partial, collation khác có nghĩa khác |
| “Unique compound index làm từng trường prefix unique” | Unique áp dụng cho toàn bộ tổ hợp key |
| “Index có collation bất kỳ dùng cho mọi equality string” | Operation và index cần có collation tương thích cho phần so sánh string |
| “Index với field mảng giống hệt field scalar” | Multikey có giới hạn về khóa, sort và covered query |
| “`explain` trên 10 document chứng minh hiệu năng production” | Cần dữ liệu đại diện, xem tổng khóa/document được kiểm tra và chi phí thực tế |

## 15. Bài thực hành: thiết kế index từ yêu cầu

### Bài A. Xác định prefix

Cho index:

```javascript
{ companyId: 1, departmentId: 1, hiredAt: -1, _id: -1 }
```

Hãy xác định những prefix liên tiếp trong các bộ sau:

1. `{companyId}`
2. `{companyId, departmentId}`
3. `{departmentId, hiredAt}`
4. `{companyId, hiredAt}`
5. `{companyId, departmentId, hiredAt}`
6. `{companyId, departmentId, hiredAt, _id}`

Gợi ý: một prefix luôn phải bắt đầu từ **trường đầu** và không được bỏ qua trường ở giữa.

### Bài B. Chọn thứ tự field theo workload

Một collection `tickets` có các truy vấn:

```javascript
// Q1: ticket đang mở của một project, mới nhất trước.
db.tickets.find({
  projectId: "P1",
  status: "OPEN"
}).sort({ createdAt: -1 });

// Q2: mọi ticket của một project, mới nhất trước.
db.tickets.find({
  projectId: "P1"
}).sort({ createdAt: -1 });

// Q3: mọi ticket OPEN của toàn bộ project.
db.tickets.find({
  status: "OPEN"
});
```

Hãy so sánh các ứng viên:

```javascript
{ projectId: 1, status: 1, createdAt: -1 }
{ projectId: 1, createdAt: -1 }
{ status: 1, projectId: 1 }
```

Câu hỏi: index nào thường phù hợp cho Q1, Q2, Q3? Nếu Q3 chỉ chạy mỗi tháng một lần và Q1/Q2 chạy liên tục, nên ưu tiên index nào? Không có một tập index tốt nhất nếu chưa biết tần suất và lượng dữ liệu.

### Bài C. So sánh ESR và ERS

Xét query:

```javascript
db.products.find({
  brand: "A",
  price: { $gte: 100000, $lt: 200000 }
}).sort({ popularity: -1 }).limit(20);
```

Đánh giá hai index:

```javascript
{ brand: 1, popularity: -1, price: 1 }
{ brand: 1, price: 1, popularity: -1 }
```

Nếu khoảng `price` rất rộng, index nào có thể có lợi để phục vụ sort? Nếu khoảng giá chỉ chứa 0,1% sản phẩm của brand, index nào có thể đáng thử? Hãy dùng `explain` thay vì khẳng định theo cảm tính.

### Bài D. Thực hành xem plan

Với collection `orders_demo` từ phần 4, thử so sánh:

```javascript
// Có equality tenant + status.
printjson(
  orders.find(
    { tenantId, status: "PAID" }
  ).sort({ createdAt: -1 }).explain("executionStats")
);

// Chỉ equality tenant.
printjson(
  orders.find(
    { tenantId }
  ).sort({ createdAt: -1 }).explain("executionStats")
);
```

Quan sát indexName, IXSCAN/COLLSCAN, SORT nếu có, `totalDocsExamined` và `totalKeysExamined`. Kết quả có thể khác giữa các phiên bản/engine và do dữ liệu demo nhỏ.

## 16. Dọn dữ liệu thực hành an toàn

Trước khi dọn, xác nhận database, collection, `runId` và danh sách ID thuộc lượt thực hành:

```javascript
print("database=" + lab.getName());
print("collection=" + orders.getName());
print("runId=" + runId);

const ownedDocs = orders.find(
  { runId, tenantId },
  { _id: 1, externalOrderId: 1, runId: 1 }
).toArray();

printjson(ownedDocs);
print("ownedCount=" + ownedDocs.length);
```

Chỉ khi các ID trong danh sách chính xác là document bạn vừa tạo, xóa từng document bằng filter gắn với cả `_id` và dấu nhận diện:

```javascript
for (const doc of ownedDocs) {
  const result = orders.deleteOne({
    _id: doc._id,
    runId,
    tenantId
  });
  print(doc.externalOrderId + ": deleted=" + result.deletedCount);
}

print("remaining=" + orders.countDocuments({ runId, tenantId }));
```

Các lệnh này không xóa document có `runId` khác. **Index đã tạo vẫn tồn tại** trong collection; chỉ nên dọn index hoặc collection thử nghiệm theo quyền sở hữu và quy trình môi trường. Không sử dụng `deleteMany({})` hoặc `dropDatabase()` trên database dùng chung để dọn bài học.

## 17. Câu hỏi ôn tập

1. Compound index khác ba single-field index ở điểm nào?
2. Với `{a:1,b:1,c:-1}`, các prefix liên tiếp là gì? `{a,c}` có phải prefix không?
3. Vì sao một truy vấn chỉ lọc `b` thường không tận dụng tốt index bắt đầu bằng `a`?
4. Vì sao index `{tenantId:1,status:1,createdAt:-1}` có thể lọc tốt theo tenant nhưng không luôn hỗ trợ sort toàn bộ đơn của tenant theo `createdAt`?
5. Một index `{a:1,b:-1}` hỗ trợ kiểu sort ngược hoàn toàn như thế nào?
6. Khi có nhiều điều kiện equality, cần cân nhắc điều gì để chọn trường nào đứng đầu?
7. ESR có ý nghĩa gì? Trường hợp nào range có thể đáng đặt trước sort?
8. Khi nào một compound index dài có thể thay index prefix ngắn? Những khác biệt nào khiến việc thay thế không tương đương?
9. Unique index ghép có bảo đảm từng trường thành phần unique không?
10. Vì sao collation và partial filter ảnh hưởng đến khả năng dùng lại index?
11. Covered query là gì và vì sao projection mặc định chứa `_id` có thể khiến truy vấn không còn covered?
12. Dùng `explain("executionStats")` như thế nào để phân biệt index được chọn, số khóa quét và số document phải đọc?

## 18. Kết luận

**Compound index là một dãy khóa có thứ tự**, nên thứ tự các trường quyết định vùng dữ liệu có thể truy cập hiệu quả, cách index hỗ trợ `sort()` và những query pattern có thể dùng chung. Tiền tố index bắt đầu từ field đầu tiên và mở rộng liên tiếp sang phải. Một index dài có thể phục vụ các truy vấn theo prefix, nhưng việc bỏ qua field đầu hoặc một field ở giữa sẽ làm giảm hoặc thay đổi lợi ích của index.

Khi chọn index, hãy xuất phát từ **workload thực tế**, các equality, sort, range và nhu cầu phân trang; dùng ESR như hướng dẫn ban đầu, rồi xác minh bằng `explain()` và số liệu trên dữ liệu đại diện. Mục tiêu không phải có thật nhiều index, mà là một **tập index vừa đủ**, dùng lại được cho các truy vấn quan trọng với chi phí đọc và ghi cân bằng.
