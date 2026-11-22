# Nguyên tắc equality, sort, range và đánh đổi theo truy vấn trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Index cơ bản

## 1. Vì sao thứ tự các field trong index quan trọng?

MongoDB hỗ trợ **index** để tìm, lọc và sắp xếp document hiệu quả hơn việc duyệt toàn bộ collection. Nhưng việc thêm đúng các field vào một **compound index** (index ghép) chưa đủ: **thứ tự các field** có thể quyết định liệu truy vấn tìm được vùng key nhỏ, đọc dữ liệu theo thứ tự sẵn có hay phải lọc/sắp xếp nhiều document sau đó.

Giả sử API cần lấy 20 đơn hàng đã thanh toán của một cửa hàng, tổng tiền từ 100 trở lên, ưu tiên đơn mới nhất:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Điều kiện truy vấn có ba loại thao tác:

- **Equality (E):** `tenantId = "shop-a"` và `status = "PAID"`.
- **Sort (S):** sắp xếp `createdAt DESC`, rồi `_id DESC` để ổn định thứ tự khi trùng thời gian.
- **Range (R):** `total >= 100`.

Với truy vấn này, index theo định hướng **ESR** có thể là:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1, total: 1 },
  { name: "idx_orders_tenant_status_created_id_total" }
);
```

Index trên ưu tiên tìm đúng tenant/status, sau đó quét theo thứ tự thời gian để trả trang mới nhất và kiểm tra điều kiện `total`. Tuy nhiên, nếu `total >= 100` chỉ khớp một phần cực nhỏ dữ liệu, đặt range sớm hơn có thể tìm được ít key hơn, dù phải trả giá cho việc sắp xếp. Đó là lý do **ESR là nguyên tắc lựa chọn index theo truy vấn, không phải một công thức luôn thắng**.

Sau bài học, bạn có thể:

1. Nhận diện equality, sort và range trong bộ lọc MongoDB.
2. Phân biệt single-field index, compound index và **index prefix**.
3. Giải thích nguyên tắc ESR: Equality → Sort → Range.
4. Nhận biết ngoại lệ nên cân nhắc **ERS**: Equality → Range → Sort.
5. Đọc kế hoạch `explain("executionStats")` để đánh giá `IXSCAN`, `FETCH`, `SORT`, số key/document được kiểm tra.
6. Cân nhắc hiệu năng đọc cùng chi phí ghi, lưu trữ, RAM và bảo trì index.
7. Thiết kế, thử nghiệm, chọn index cho các truy vấn khác nhau thay vì tạo index theo từng field một cách máy móc.

## 2. Mô hình tư duy: index ghép được sắp xếp theo thứ tự khóa

Với compound index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

MongoDB lưu các entry của index theo thứ tự khóa tương ứng: trước theo `tenantId` tăng dần, bên trong một tenant theo `status` tăng dần, rồi bên trong cùng tenant/status theo `createdAt` giảm dần. Có thể hình dung:

```text
tenantId = shop-a
    status = CANCELLED
        createdAt mới → cũ
    status = NEW
        createdAt mới → cũ
    status = PAID
        createdAt mới → cũ
tenantId = shop-b
    status = CANCELLED
        createdAt mới → cũ
    status = NEW
        createdAt mới → cũ
    status = PAID
        createdAt mới → cũ
...
```

Đây là **hình minh họa thứ tự key**, không phải mô tả đầy đủ layout vật lý của storage engine. Index B-tree/B-tree-like giúp MongoDB tìm vị trí và duyệt vùng khóa phù hợp mà không phải đọc toàn bộ document trong collection.

Khi điều kiện cố định `tenantId` và `status`, các key trong vùng đó đã xếp theo `createdAt DESC`. Server có thể trả kết quả theo thứ tự mong muốn bằng cách quét index mà không cần một bước **blocking sort** riêng.

Nếu chỉ có index:

```javascript
{ tenantId: 1, total: 1, createdAt: -1 }
```

thì bên trong mỗi tenant, entry được nhóm theo `total` trước; toàn bộ các entry thuộc vùng `total >= 100` **không tự được sắp chung theo `createdAt`**. Phần sort phía sau có thể phải dùng một bước riêng.

### 2.1. Ý nghĩa của số 1 và -1

- `1`: thứ tự tăng dần trong key index.
- `-1`: thứ tự giảm dần.
- Với một field đơn, index có thể được quét theo chiều thuận/ngược cho sort tương ứng.
- Với compound index nhiều field cần sort, **tương quan hướng giữa các field** là quan trọng.

Ví dụ index:

```javascript
{ createdAt: -1, _id: -1 }
```

có thể phục vụ sort `{ createdAt: -1, _id: -1 }` hoặc sort ngược hoàn toàn `{ createdAt: 1, _id: 1 }`. Nhưng sort hỗn hợp `{ createdAt: -1, _id: 1 }` không cùng mẫu hướng và không mặc nhiên được index này đáp ứng.

### 2.2. Thứ tự field trong filter không quyết định thứ tự index

Hai filter sau biểu đạt cùng điều kiện:

```javascript
{ tenantId: "shop-a", status: "PAID" }

{ status: "PAID", tenantId: "shop-a" }
```

Việc đổi thứ tự field trong object filter không tự làm MongoDB xây hoặc sử dụng index khác. Điều quan trọng là **trình tối ưu truy vấn, tập điều kiện và thứ tự key của index hiện có**.

## 3. Equality (E): điều kiện bằng

Equality thường gặp với `$eq` hoặc cách viết rút gọn:

```javascript
{ tenantId: "shop-a" }
{ status: { $eq: "PAID" } }
{ _id: ObjectId("507f1f77bcf86cd799439011") }
```

Khi equality nằm đầu compound index, nó giúp thu hẹp vùng key cần duyệt. Ví dụ:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Truy vấn:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
}).sort({ createdAt: -1 });
```

có thể đi tới vùng key của một tenant và trạng thái cụ thể rồi duyệt theo thời gian, thay vì kiểm tra tất cả tenant.

### 3.1. Một hay nhiều equality field?

Nếu filter có nhiều điều kiện equality, những field đó thường được ưu tiên trước phần sort/range:

```javascript
{ tenantId: 1, status: 1, channel: 1, createdAt: -1 }
```

MongoDB có thể tận dụng equality prefix `tenantId + status + channel`. Thứ tự giữa **các equality field** không có một quy luật “luôn đặt field có độ chọn lọc cao nhất trước” áp dụng cho mọi workload. Hãy ưu tiên khả năng dùng index prefix cho các truy vấn quan trọng, rồi kiểm tra hiệu năng thực tế.

Ví dụ các truy vấn của API:

| Truy vấn | Filter |
|---|---|
| Trang đơn hàng theo cửa hàng | `tenantId = ?` |
| Trang đơn hàng theo cửa hàng và trạng thái | `tenantId = ? AND status = ?` |
| Trang đơn hàng theo cửa hàng, trạng thái và kênh | `tenantId = ? AND status = ? AND channel = ?` |

Đối với ba truy vấn này, việc bắt đầu bằng `tenantId` thường giúp một index ghép phục vụ nhiều pattern. Nếu phần lớn truy vấn lại bắt đầu bằng `status` mà không có `tenantId`, lựa chọn thứ tự khác hoặc thêm index riêng có thể cần thiết.

### 3.2. Equality không phải luôn là giá trị có độ chọn lọc cao

`status = "PAID"` có thể khớp 70% collection; `tenantId = "shop-a"` có thể chỉ khớp 1%. Cả hai đều là equality, nhưng không có hiệu quả lọc như nhau.

**Selectivity** mô tả mức độ điều kiện thu hẹp tập document. Điều kiện rất chọn lọc giữ lại ít document; điều kiện ít chọn lọc giữ lại nhiều document. Ưu tiên equality trong ESR giúp định vị key tốt và giữ sort, nhưng vẫn phải cân nhắc phân bố dữ liệu và query pattern.

## 4. Sort (S): tận dụng thứ tự có sẵn trong index

Sort xảy ra khi truy vấn yêu cầu thứ tự đầu ra:

```javascript
db.orders.find({ tenantId: "shop-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Một index phù hợp:

```javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
```

Khi `tenantId` được cố định bằng equality, đoạn còn lại của index đã theo thứ tự `createdAt DESC, _id DESC`. MongoDB có thể duyệt index để trả 20 phần tử theo đúng thứ tự mà không phải thu thập toàn bộ kết quả rồi sort.

### 4.1. Vì sao sort trước range thường hữu ích?

Giả sử filter có điều kiện `total >= 100`:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Nếu index đặt sort fields trước range:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1, total: 1 }
```

thì sau khi cố định tenant/status, cursor có thể đọc đơn theo thời gian giảm dần và kiểm tra `total >= 100`. Khi có đủ 20 đơn phù hợp, truy vấn có cơ hội dừng sớm theo `limit(20)`.

Nhưng nếu chỉ 1 trong 10000 đơn thỏa range, việc quét theo thứ tự thời gian có thể phải bỏ qua nhiều index entry. Đó là trường hợp cần so sánh với ERS ở mục sau.

### 4.2. Sort không được index hỗ trợ là gì?

Khi MongoDB không thể dùng thứ tự index để đáp ứng yêu cầu sort, nó có thể sử dụng một bước **SORT** trong kế hoạch thực thi. Một sort dạng blocking cần thu thập đủ dữ liệu liên quan trước khi trả kết quả theo thứ tự, dù các tối ưu như **sort + limit** có thể giới hạn số phần tử cần giữ trong bộ nhớ.

Index phù hợp thường giúp tránh chi phí sort này; tuy nhiên, không phải mọi truy vấn có stage `SORT` đều kém. Nếu range rất chọn lọc và chỉ còn vài document, một sort nhỏ có thể rẻ hơn quét lượng lớn key để giữ thứ tự.

### 4.3. Thứ tự sort cần ổn định khi phân trang

Nếu nhiều đơn có cùng `createdAt`, sort:

```javascript
.sort({ createdAt: -1 })
```

không quy định thứ tự giữa những document trùng thời gian. Thêm `_id` làm khóa phụ:

```javascript
.sort({ createdAt: -1, _id: -1 })
```

giúp có thứ tự xác định, đặc biệt quan trọng cho cursor pagination theo keyset. Index cũng nên được thiết kế theo thứ tự thực tế của sort, ví dụ `{ tenantId: 1, createdAt: -1, _id: -1 }`.

## 5. Range (R): điều kiện bất đẳng thức và khoảng giá trị

Range thường gặp dưới các dạng:

```javascript
{ total: { $gte: 100 } }
{ total: { $gt: 100, $lt: 500 } }
{ createdAt: { $gte: ISODate("2026-01-01T00:00:00Z") } }
{ score: { $lte: 90 } }
```

Các điều kiện này xác định một **vùng giá trị**, không phải một key bằng cố định. Index trên field range có thể giúp server chỉ duyệt một đoạn key:

```javascript
db.orders.createIndex({ total: 1 });
db.orders.find({ total: { $gte: 100, $lt: 500 } });
```

Range cũng bao gồm những loại operator như `$ne` hoặc `$nin` trong nhiều tình huống nhưng tính chọn lọc của chúng thường thấp; việc có operator bất đẳng thức **không đảm bảo** index sẽ hiệu quả.

### 5.1. Vì sao range trước sort có thể làm mất khả năng sort bằng index?

Xem index:

```javascript
{ tenantId: 1, status: 1, total: 1, createdAt: -1 }
```

Sau equality `tenantId` và `status`, index sắp theo **total** tăng dần. Trong vùng total từ 100 đến 500, document được nhóm theo total; thứ tự `createdAt` chỉ đúng bên trong các giá trị total tương ứng. Do đó, toàn bộ kết quả **không tự được sắp chung theo createdAt DESC** và có thể cần SORT riêng.

Đặt range sau sort trong ESR là cách giữ thứ tự của kết quả theo field sort khi range có thể chấp nhận quét đủ index key.

### 5.2. Range rất chọn lọc có thể đáng ưu tiên trước sort

Nếu 99,99% đơn hàng có total dưới 100000 và chỉ 0,01% có total cao hơn, truy vấn:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100000 }
})
.sort({ createdAt: -1 })
.limit(20);
```

có thể hiệu quả hơn với index:

```javascript
{ tenantId: 1, status: 1, total: 1, createdAt: -1 }
```

vì range trên `total` thu hẹp rất mạnh số key cần quét. Chi phí sort số document ít ỏi có thể nhỏ hơn chi phí duyệt một lượng lớn entry được sắp theo thời gian.

Đây là lựa chọn **ERS** có điều kiện, không tự động đúng với mọi range. Cần đo bằng dữ liệu đại diện.

## 6. Nguyên tắc ESR: Equality → Sort → Range

**ESR** là hướng dẫn sắp xếp field trong **compound index** phục vụ truy vấn có cả equality, sort và range:

```text
E (Equality) → S (Sort) → R (Range)
    cố định       giữ thứ tự    kiểm tra khoảng
    tiền tố       kết quả       giá trị
```

Ví dụ truy vấn:

```javascript
db.orders.find({
  tenantId: "shop-a",                // E
  status: "PAID",                    // E
  total: { $gte: 100, $lte: 500 }   // R
})
.sort({ createdAt: -1, _id: -1 })   // S
.limit(20);
```

Index ESR:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,        // E
    status: 1,          // E
    createdAt: -1,      // S
    _id: -1,            // S
    total: 1            // R
  },
  { name: "idx_esr_orders" }
);
```

Lợi ích tiềm năng:

1. `tenantId + status` giúp định vị vùng key.
2. Trong vùng đó, các key đã theo thứ tự `createdAt DESC, _id DESC`.
3. Điều kiện `total` có thể được đánh giá từ các entry/index hoặc sau khi lấy document tùy kế hoạch.
4. `limit(20)` có thể giúp dừng sau khi đủ 20 document hợp lệ.

**Đánh đổi:** range đặt cuối có thể không cắt giảm mạnh vùng index được quét, đặc biệt khi dữ liệu đủ điều kiện range rất hiếm. Đừng chỉ nhìn thấy index ESR rồi mặc định query chắc chắn nhanh.

### 6.1. ESR là định hướng, không phải cú pháp bắt buộc

MongoDB không yêu cầu tạo field theo ESR mới cho phép query chạy. Query có thể hoạt động bằng COLLSCAN hoặc index khác. ESR giúp dự đoán index có thể hỗ trợ filter và sort tốt tới đâu; planner vẫn chọn kế hoạch tùy thống kê và tình trạng dữ liệu.

Không phải lúc nào index gồm tất cả các field truy vấn cũng tốt hơn index gọn. Nhiều field làm index lớn hơn, tăng chi phí ghi và bộ nhớ. Hãy ưu tiên **truy vấn thực sự quan trọng**, dựa trên workload chứ không ghép mọi field của document vào một index.

### 6.2. Query không có sort

Với:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
});
```

index `{ tenantId: 1, status: 1, total: 1 }` là lựa chọn tự nhiên **E → E → R**. Không cần thêm field sort không được query sử dụng, trừ khi muốn index dùng chung cho nhiều pattern khác.

### 6.3. Query không có range

Với:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` là mẫu **E → E → S**. Đây là pattern rất thường gặp ở danh sách có lọc trạng thái và phân trang.

## 7. Khi nào cân nhắc ERS: Equality → Range → Sort?

Một index theo thứ tự **ERS** đặt field range trước các field sort:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    total: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_ers_orders" }
);
```

### 7.1. Lý do nên thử ERS

ERS có thể thắng khi:

- Điều kiện range **rất chọn lọc**, làm giảm cực mạnh số key/document cần xét.
- Tập sau khi lọc range nhỏ nên chi phí sort chấp nhận được.
- Có đủ RAM/tài nguyên cho phần sort hoặc query dùng chiến lược sort hợp lý.
- Truy vấn ưu tiên lọc đúng ít document hơn giữ thứ tự hoàn toàn từ index.

### 7.2. Lý do ESR có thể thắng

ESR có thể thắng khi:

- Kết quả sau equality vẫn lớn nhưng range không quá chọn lọc.
- Query có `sort + limit`, cần trả vài document đầu rất nhanh.
- Sort từ index tránh bước blocking SORT.
- Phân trang liên tục theo thời gian, index scan có thể dừng sớm khi đủ dữ liệu.

### 7.3. Bảng so sánh ESR và ERS

| Tiêu chí | ESR | ERS |
|---|---|---|
| Thứ tự index | Equality → Sort → Range | Equality → Range → Sort |
| Điểm mạnh | Giữ thứ tự sort từ index sau equality prefix | Giảm mạnh key scan khi range rất chọn lọc |
| Bước SORT riêng | Có thể tránh | Thường cần nếu range bao trùm nhiều giá trị |
| Khi kết hợp `limit(20)` | Có cơ hội lấy 20 kết quả đầu theo thứ tự nhanh | Có thể phải lọc range rồi sort trước khi chọn 20 |
| Khi range chỉ khớp rất ít | Có thể quét nhiều key không đạt range | Có thể ít key hơn |
| Chi phí lưu trữ | Phụ thuộc field/index thực tế | Tương tự nếu gồm cùng field |
| Cách chọn | Đo với workload và dữ liệu thật | Đo với workload và dữ liệu thật |

**Không có quy tắc “range luôn phải ở cuối” hoặc “field chọn lọc nhất luôn phải ở đầu” đúng cho tất cả truy vấn.** Điều quan trọng là phân tích tập điều kiện và thứ tự yêu cầu rồi dùng `explain` để có bằng chứng.

## 8. Compound index và quy tắc index prefix

Giả sử có index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Các **prefix** lần lượt là:

1. `{ tenantId: 1 }`
2. `{ tenantId: 1, status: 1 }`
3. `{ tenantId: 1, status: 1, createdAt: -1 }`
4. Toàn bộ index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }`

Index có thể phục vụ tốt nhiều truy vấn bắt đầu bằng prefix:

```javascript
// Có thể tận dụng tenantId prefix:
db.orders.find({ tenantId: "shop-a" });

// Có thể tận dụng tenantId + status prefix:
db.orders.find({ tenantId: "shop-a", status: "PAID" });

// Có thể tận dụng equality prefix + sort:
db.orders.find({ tenantId: "shop-a", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 });
```

Còn truy vấn:

```javascript
db.orders.find({ status: "PAID" });
```

**không dùng prefix `tenantId`**. MongoDB vẫn có thể lựa chọn một kế hoạch dùng compound index tùy tình huống, nhưng thường không khai thác được cùng lợi thế tìm một vùng key hẹp như truy vấn đã cố định prefix.

### 8.1. Sort trên field không nằm đầu index

Trong một số trường hợp, MongoDB dùng index để sort theo **non-prefix subset** nếu các field đứng trước subset trong index đều có điều kiện equality.

Ví dụ index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Truy vấn:

```javascript
db.orders.find({ tenantId: "shop-a", status: "PAID" })
  .sort({ createdAt: -1 });
```

có thể được index hỗ trợ sort vì hai field đứng trước `createdAt` đều được cố định bằng equality. Nếu bỏ điều kiện `status`:

```javascript
db.orders.find({ tenantId: "shop-a" })
  .sort({ createdAt: -1 });
```

thì các document của tenant nằm trong nhiều nhóm status; thứ tự createdAt **không xuyên suốt** tất cả nhóm status. Index trên không mặc nhiên hỗ trợ global sort theo createdAt cho truy vấn đó.

### 8.2. Có nên tạo thêm single-field index trùng prefix?

Nếu đã có compound index `{ tenantId: 1, status: 1 }`, một index riêng `{ tenantId: 1 }` có thể là dư trong nhiều workload vì compound index có prefix `tenantId`. Nhưng trước khi xóa index riêng, phải xem:

- Index có khác nhau về tính chất unique, sparse, partial, collation hay không.
- Có query chỉ cần index nhỏ hơn vì hiệu quả read/working set không?
- Có truy vấn cần hint, query plan đặc thù hoặc mục đích vận hành riêng?
- Tải ghi/lưu trữ và tần suất truy vấn có đủ dữ liệu để quyết định?

Không xóa index chỉ dựa trên prefix mà chưa kiểm tra workload.

## 9. Ví dụ thực hành: collection và truy vấn thật

Tạo database lab để có dữ liệu minh họa. Cài MongoDB Server và kết nối bằng `mongosh` có quyền ghi trong database thực hành.

```javascript
const lab = db.getSiblingDB("esr_index_lab");
const orders = lab.getCollection("orders");

orders.insertMany([
  {
    _id: "O-001", tenantId: "shop-a", status: "PAID",
    total: 120, createdAt: ISODate("2026-01-11T10:00:00Z")
  },
  {
    _id: "O-002", tenantId: "shop-a", status: "PAID",
    total: 500, createdAt: ISODate("2026-01-12T10:00:00Z")
  },
  {
    _id: "O-003", tenantId: "shop-a", status: "NEW",
    total: 80, createdAt: ISODate("2026-01-13T10:00:00Z")
  },
  {
    _id: "O-004", tenantId: "shop-a", status: "PAID",
    total: 25, createdAt: ISODate("2026-01-14T10:00:00Z")
  },
  {
    _id: "O-005", tenantId: "shop-a", status: "PAID",
    total: 230, createdAt: ISODate("2026-01-15T10:00:00Z")
  },
  {
    _id: "O-006", tenantId: "shop-a", status: "CANCELLED",
    total: 180, createdAt: ISODate("2026-01-16T10:00:00Z")
  },
  {
    _id: "O-007", tenantId: "shop-b", status: "PAID",
    total: 1000, createdAt: ISODate("2026-01-17T10:00:00Z")
  },
  {
    _id: "O-008", tenantId: "shop-b", status: "PAID",
    total: 35, createdAt: ISODate("2026-01-18T10:00:00Z")
  },
  {
    _id: "O-009", tenantId: "shop-a", status: "PAID",
    total: 700, createdAt: ISODate("2026-01-19T10:00:00Z")
  },
  {
    _id: "O-010", tenantId: "shop-a", status: "PAID",
    total: 150, createdAt: ISODate("2026-01-20T10:00:00Z")
  }
]);
```

Đây là dữ liệu học tập nhỏ; không có ý nghĩa để benchmark tốc độ index trên production. Nếu lệnh insert lỗi trùng `_id` do đã tạo trước, dùng một database lab khác hoặc xử lý dữ liệu thử nghiệm có kiểm soát. Không xóa collection thuộc ứng dụng thật.

Truy vấn cần phân tích:

```javascript
const filter = {
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
};

const sort = { createdAt: -1, _id: -1 };

printjson(
  orders.find(filter, { _id: 1, tenantId: 1, status: 1, total: 1, createdAt: 1 })
    .sort(sort)
    .limit(3)
    .toArray()
);
```

Với dữ liệu mẫu, ba đơn mới nhất khớp là `O-010` (150), `O-009` (700), `O-005` (230). Đơn `O-004` có total 25 nên bị loại dù nằm gần hơn trong thứ tự thời gian.

### 9.1. Tạo index theo ESR

```javascript
orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1,
    total: 1
  },
  { name: "idx_esr" }
);
```

### 9.2. Tạo index theo ERS để so sánh

```javascript
orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    total: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_ers" }
);
```

Hai index khác nhau về thứ tự field `total` và các field sort. Chúng sử dụng thêm dung lượng và chịu chi phí duy trì khi document được ghi/cập nhật, vì vậy trong ứng dụng thật không nên giữ cả hai mãi nếu workload chỉ cần một.

### 9.3. Quan sát danh sách index

```javascript
printjson(orders.getIndexes());
```

Ngoài hai index tự tạo, collection có index mặc định trên `_id`. Đây là cơ hội phân biệt **index được khai báo** với **index được query planner chọn**: việc có index không chứng minh mọi query sẽ dùng nó.

## 10. Dùng explain("executionStats") để đưa ra quyết định

Một cách kiểm tra thực tế là chạy query với:

```javascript
const query = orders.find(filter)
  .sort(sort)
  .limit(3);

printjson(query.explain("executionStats"));
```

Output chứa thông tin về kế hoạch và quá trình thực thi. Tên stage/cấu trúc JSON có thể khác nhau theo version MongoDB và query engine. Hãy tìm các phần thể hiện:

| Trường/stage | Cần hiểu gì? |
|---|---|
| `IXSCAN` | Quét index theo các điều kiện/ranh giới khóa |
| `COLLSCAN` | Quét collection thay vì tìm theo index |
| `FETCH` | Lấy document thực từ collection theo thông tin index |
| `SORT` | Có bước sắp xếp riêng; cần hiểu chi phí và khả năng dùng index |
| `PROJECTION_COVERED` hoặc dạng projection tương ứng | Khả năng trả field từ index mà không phải đọc document |
| `nReturned` | Số kết quả thực sự trả từ phần thực thi được ghi nhận |
| `totalKeysExamined` | Số index keys được xem xét |
| `totalDocsExamined` | Số document được xem xét/lấy ra |
| `executionTimeMillis` | Thời gian thực thi đo theo cơ chế explain trong môi trường hiện tại |
| `indexBounds` | Khoảng key index mà truy vấn áp dụng |
| `indexName` | Tên index thuộc stage đang được thực thi |

Những trường này **không phải một phép đo duy nhất đủ để kết luận**. Đọc kết hợp số document trả về, số key/document đã kiểm tra, sort, kích thước dữ liệu, cache và độ trễ thực tế từ ứng dụng.

### 10.1. So sánh có kiểm soát bằng hint

Để yêu cầu MongoDB thử một index cụ thể, dùng `hint()` trong môi trường lab:

```javascript
const esrPlan = orders.find(filter)
  .sort(sort)
  .limit(3)
  .hint("idx_esr")
  .explain("executionStats");

const ersPlan = orders.find(filter)
  .sort(sort)
  .limit(3)
  .hint("idx_ers")
  .explain("executionStats");

printjson({
  esr: esrPlan.executionStats,
  ers: ersPlan.executionStats
});
```

Tùy phiên bản, cấu trúc kế hoạch nằm trong `queryPlanner` và chi tiết stage có thể khác. Với dữ liệu lab chỉ có 10 document, chênh lệch thời gian thường không có giá trị thống kê. Khi đánh giá workload thật, cần lượng dữ liệu đại diện, truy vấn tiêu biểu và môi trường đọc/ghi tương tự production.

**`hint()` có thể ép một kế hoạch kém** nếu phân bố dữ liệu thay đổi. Dùng nó để đo so sánh hoặc cho tình huống đã có bằng chứng; không đưa hint vào mọi truy vấn mặc định.

### 10.2. Nhận diện sort có được index phục vụ

Nếu index ESR được dùng phù hợp, planner có khả năng tận dụng thứ tự `createdAt DESC, _id DESC` và không cần một `SORT` blocking riêng.

Nếu dùng index ERS với `total >= 100`, các key đã nhóm theo `total`; truy vấn cần global sort theo thời gian thường xuất hiện bước SORT. Điều đó **không tự chứng minh ERS chậm hơn**: nếu range lọc đủ mạnh thì chi phí của sort nhỏ có thể chấp nhận được.

### 10.3. Vì sao số keysExamined quan trọng?

Giả sử một truy vấn trả 20 document:

- Plan A: `totalKeysExamined = 25`.
- Plan B: `totalKeysExamined = 200000`.

Nếu các chỉ số khác tương đương, plan A thường hiệu quả hơn vì phải duyệt ít key hơn. Nhưng nếu plan A phải sort document lớn, plan B tránh sort và trả trang đầu nhanh hơn, việc đánh giá cần thêm thời gian, bộ nhớ và lượng dữ liệu thực tế.

Các giá trị trên chỉ là **ví dụ giải thích chỉ số**, không phải kết quả đo của bộ dữ liệu lab.

### 10.4. Số document examined có thể bằng 0 không?

Có, trong một **covered query** phù hợp: các field để filter và projection đều có trong index, đồng thời đáp ứng các điều kiện khác để MongoDB không cần FETCH document. Ví dụ:

```javascript
orders.find(
  { tenantId: "shop-a", status: "PAID" },
  { _id: 0, tenantId: 1, status: 1, createdAt: 1 }
)
.sort({ createdAt: -1 });
```

Nếu index phù hợp chứa các field cần thiết và query được cover theo các quy tắc engine, server có thể trả dữ liệu chỉ từ index. Để xác nhận, xem plan và `totalDocsExamined`. Phải loại `_id` khỏi projection khi index không chứa `_id`; không mặc định một secondary index tự cover giá trị `_id` trong mọi trường hợp.

**Chú ý:** Index chứa field dạng array (multikey), collation, kiểu biểu thức và projection có thể ảnh hưởng khả năng cover; không suy luận chỉ từ tên index.

## 11. Equality, sort và range với các kiểu điều kiện đặc biệt

### 11.1. $in có phải equality không?

`$in` so sánh field với một tập giá trị:

```javascript
db.orders.find({
  status: { $in: ["PAID", "NEW"] }
}).sort({ createdAt: -1 });
```

`$in` không hoàn toàn giống một equality duy nhất khi phải hợp nhất kết quả của nhiều giá trị. MongoDB có thể dùng nhiều nhánh index scan rồi hợp nhất theo thứ tự trong một số điều kiện. Với danh sách rất lớn, hành vi có thể gần với một range operator.

Tài liệu MongoDB nêu một ngưỡng xử lý đặc biệt theo số phần tử `$in` trong một số trường hợp dùng `sort`; đây là chi tiết triển khai có thể thay đổi ở các phiên bản sau. Khi dùng `$in` kết hợp sort, hãy kiểm tra explain của phiên bản đang chạy, đừng tự áp một con số cố định làm chuẩn thiết kế.

### 11.2. $ne và $nin

`$ne` và `$nin` thường ít chọn lọc, ví dụ:

```javascript
{ status: { $ne: "CANCELLED" } }
```

Nếu phần lớn đơn hàng đều khác CANCELLED, index trên `status` không giúp thu hẹp tập kết quả nhiều. Tùy workload, COLLSCAN có thể cạnh tranh hoặc tốt hơn index scan + FETCH.

### 11.3. Regex và tiền tố chuỗi

Một regex anchored theo tiền tố như:

```javascript
{ sku: /^ABC/ }
```

có thể tận dụng range trên index chuỗi trong điều kiện phù hợp. Regex chứa wildcard đầu chuỗi như `/.*ABC/` thường khó tận dụng prefix để định vị vùng key.

Regex phân biệt/không phân biệt hoa thường và collation có những giới hạn sử dụng index riêng; đừng mặc định một index với collation case-insensitive sẽ tăng tốc mọi regex `/i`.

### 11.4. Điều kiện trên array và multikey index

Nếu một field trong index chứa array, MongoDB có thể tạo **multikey index**. Quy tắc lọc/sort và khả năng cover với multikey phức tạp hơn scalar index, nhất là khi có nhiều field array và `$elemMatch`.

Ví dụ truy vấn theo `tags` cùng sort `createdAt` cần xem xét index thực tế, cấu trúc document và giới hạn multikey. **Không áp máy móc ESR của field scalar vào mọi query array.**

### 11.5. Collation và so sánh chuỗi

Index được tạo với một collation nhất định. Để index hỗ trợ so sánh hoặc sắp xếp string theo collation đó, query cần dùng collation tương thích:

```javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  { name: "idx_customer_name_ci", collation: { locale: "en", strength: 2 } }
);

db.customers.find({ tenantId: "shop-a" })
  .collation({ locale: "en", strength: 2 })
  .sort({ name: 1 });
```

Đây là ví dụ cách khai báo collation; không yêu cầu chạy nếu collection `customers` chưa có. Collation ảnh hưởng semantics của so sánh/đặt thứ tự, nên cũng là một phần hợp đồng truy vấn và index.

## 12. Index nhiều không phải lúc nào cũng tốt

Mỗi index cần dung lượng lưu trữ và được cập nhật khi document thay đổi theo field được index. Một collection có nhiều index thường tăng chi phí:

- **Insert:** thêm entry vào các index liên quan.
- **Update:** khi thay field nằm trong index, phải cập nhật cấu trúc index tương ứng.
- **Delete:** loại entry của document khỏi index.
- **Disk/storage:** index chiếm dung lượng và có thể làm bộ dữ liệu index lớn.
- **RAM/cache:** working set của index cạnh tranh tài nguyên với dữ liệu và các cấu trúc khác.
- **Build/maintenance:** xây index tiêu tốn I/O/CPU và cần chiến lược triển khai ở production.
- **Planner:** quá nhiều index gần giống nhau có thể tăng độ phức tạp lựa chọn/duy trì và khiến mục tiêu vận hành khó kiểm soát.

### 12.1. Ví dụ ba index gần giống nhau

```javascript
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Về prefix, index dài nhất có thể hỗ trợ nhiều query mà hai index ngắn hơn cũng hỗ trợ. Nhưng index dài sẽ lớn hơn và có thể không tối ưu cho query chỉ cần key hẹp. Chỉ nên quyết định giữ/xóa sau khi biết tần suất, latency, write load, đặc tính unique/partial/collation và sự phụ thuộc của workload.

### 12.2. “Một index cho mỗi endpoint” có ổn không?

Nếu API có 50 endpoint nhưng chỉ 5 mẫu truy vấn chủ đạo, tạo 50 index có thể dư thừa. Ngược lại, nếu có một truy vấn cực quan trọng với SLA rất thấp, một index chuyên dụng có thể đáng chi phí.

Tập trung vào **query patterns**, ví dụ:

| Query pattern | Field lọc/sort | Index ứng viên |
|---|---|---|
| Xem đơn theo tenant | E: tenantId; S: createdAt DESC | `{ tenantId: 1, createdAt: -1, _id: -1 }` |
| Xem đơn theo tenant + status | E: tenantId/status; S: createdAt DESC | `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` |
| Tìm đơn giá trị cao | E: tenantId/status; R: total | `{ tenantId: 1, status: 1, total: 1 }` |
| Tìm đơn giá trị cao và lấy mới nhất | E: tenantId/status; R: total; S: createdAt DESC | So sánh ESR và ERS |
| Tra cứu đơn theo ID | E: _id | Index `_id` mặc định |

Không nhất thiết tạo đủ tất cả index ứng viên. Một index phục vụ nhiều pattern có thể tốt hơn nhiều index chuyên biệt nếu yêu cầu hiệu năng cho phép.

## 13. Partial index, unique index và điều kiện chọn index

Một **partial index** chỉ chứa document đáp ứng filter quy định khi tạo index, giúp giảm kích thước index và chi phí ghi so với index toàn collection nếu truy vấn tập trung vào một nhóm dữ liệu.

Ví dụ phần lớn truy vấn chỉ lấy đơn đang ở trạng thái PAID:

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "idx_paid_orders",
    partialFilterExpression: { status: "PAID" }
  }
);
```

Để có thể tận dụng index partial mà không làm thiếu kết quả, query cần có điều kiện tương ứng hoặc điều kiện đủ hẹp để suy ra tập document thuộc index:

```javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID"
}).sort({ createdAt: -1, _id: -1 });
```

Query không có điều kiện `status: "PAID"` không thể mặc nhiên dùng index partial này để trả toàn bộ đơn hàng, vì index không chứa document ở trạng thái khác.

**Không lẫn partial index với ESR.** ESR nói về **thứ tự các field trong index**; partial nói về **document nào có entry trong index**. Có thể kết hợp hai nguyên tắc khi workload phù hợp.

Unique index lại nhằm đảm bảo **tính duy nhất** (ví dụ `orderId` không trùng), đồng thời có thể hỗ trợ lookup. Một index unique chuyên dụng là ràng buộc nghiệp vụ; không nên loại bỏ chỉ vì có compound index khác phục vụ sort/range.

## 14. Áp dụng trong MongoDB Java Sync Driver

Các nguyên tắc E/S/R không phụ thuộc ngôn ngữ. Java driver cung cấp API builder cho filter, sort và index.

Ví dụ dưới đây dùng `org.mongodb:mongodb-driver-sync` và giả định MongoDB Server đã hoạt động, database lab đã có dữ liệu.

### 14.1. Tạo compound index trong Java

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Indexes.ascending;
import static com.mongodb.client.model.Indexes.compoundIndex;
import static com.mongodb.client.model.Indexes.descending;

public final class CreateEsrIndex {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            uri = "mongodb://127.0.0.1:27017";
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("esr_index_lab")
                    .getCollection("orders");

            String indexName = orders.createIndex(
                    compoundIndex(
                            ascending("tenantId", "status"),
                            descending("createdAt", "_id"),
                            ascending("total")
                    )
            );

            System.out.println("Created/existing index: " + indexName);
        }
    }
}
```

Thư viện Java có thể trả tên index đã tạo hoặc tên index phù hợp đang tồn tại theo các quy tắc của server. Trong ứng dụng thật, index thường được quản lý qua migration/deployment script hoặc cơ chế quản trị có kiểm soát, thay vì xây lại mỗi lần ứng dụng khởi động.

### 14.2. Viết query E/S/R từ Java

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Sorts.descending;

// Giả định orders là MongoCollection<Document> đã khởi tạo:
try (MongoCursor<Document> cursor = orders.find(
        and(
                eq("tenantId", "shop-a"),
                eq("status", "PAID"),
                gte("total", 100)
        )
    )
    .sort(descending("createdAt", "_id"))
    .limit(20)
    .batchSize(20)
    .iterator()) {

    while (cursor.hasNext()) {
        System.out.println(cursor.next().toJson());
    }
}
```

Giải thích:

- `eq` trên `tenantId` và `status` tạo equality filters.
- `gte("total", 100)` là điều kiện range.
- `sort(descending("createdAt", "_id"))` là sort theo hai field.
- `limit(20)` giới hạn tổng document trả về.
- `batchSize(20)` điều chỉnh số document đề nghị lấy mỗi batch, **không thay index strategy**.
- `MongoCursor` được đóng bằng `try-with-resources`.

### 14.3. Kiểm tra index không đồng nghĩa kiểm tra dữ liệu trả về

Ứng dụng Java có thể vẫn nhận đúng kết quả bằng COLLSCAN, nên việc “chương trình chạy được” **không chứng minh index tốt**. Khi cần điều tra hiệu năng, dùng `explain` từ MongoDB Shell hoặc API giải thích tương ứng, giữ query/filter/sort giống hệt ứng dụng.

Cần lưu ý thêm **kiểu BSON**. Nếu `total` trong collection lưu dưới dạng Decimal128 nhưng Java filter dùng integer `100`, semantics so sánh số và hành vi index cần được hiểu theo kiểu dữ liệu thực tế. Với nghiệp vụ tiền tệ, hãy dùng kiểu số thống nhất trong schema/driver và index.

## 15. Quy trình chọn index theo workload

Một quy trình thực hành dễ áp dụng:

### Bước 1 — Ghi rõ các query thật

Đừng bắt đầu bằng danh sách field của collection. Hãy thống kê:

- Filter equality/range thực tế.
- Sort và hướng sort.
- Limit/page size.
- Tần suất truy vấn, SLA, đặc điểm tenant.
- Projection (field nào được trả về).
- Tần suất insert/update/delete và field hay thay đổi.

Ví dụ:

```javascript
find({ tenantId: ?, status: ?, total: { $gte: ? } })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

### Bước 2 — Phân loại E, S, R

| Vai trò | Field |
|---|---|
| E | `tenantId`, `status` |
| S | `createdAt`, `_id` |
| R | `total` |

Xác định thêm điều kiện có thực sự là equality đơn hay tập `$in`, có cần collation, liệu field là array hay không.

### Bước 3 — Đề xuất index tối thiểu

Bắt đầu với ESR:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1, total: 1 }
```

Nếu range rất chọn lọc, đề xuất ERS để so sánh:

```javascript
{ tenantId: 1, status: 1, total: 1, createdAt: -1, _id: -1 }
```

Đồng thời xem một index ngắn hơn có đủ không, chẳng hạn `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` nếu lọc total sau đó mà vẫn đáp ứng SLA.

### Bước 4 — Đọc explain, đo trong điều kiện đại diện

So sánh:

- Index có thực sự được chọn?
- Có `SORT` riêng hay không?
- `totalKeysExamined` và `totalDocsExamined` là bao nhiêu?
- Có nhiều FETCH và lọc bỏ document không?
- Thời gian trả trang đầu/tổng thời gian từ ứng dụng thế nào?
- Bộ nhớ/query sort và network có trở thành nút cổ chai?
- Index mới có ảnh hưởng đáng kể đến throughput ghi không?

### Bước 5 — Cân nhắc chi phí index

Nếu một index mới giúp endpoint hiếm dùng giảm từ 20 ms còn 15 ms nhưng làm tăng đáng kể dung lượng và chi phí ghi cho hàng triệu insert, có thể không đáng giữ. Nếu một endpoint truy cập hàng nghìn lần/giây giảm từ 300 ms còn 30 ms, index chuyên dụng có thể rất có giá trị.

Các con số ở đây chỉ minh họa cách cân nhắc; cần dữ liệu đo thực tế trước khi quyết định.

### Bước 6 — Theo dõi và xem xét lại

Phân bố status/tenant/total có thể thay đổi theo thời gian. Index từng hiệu quả có thể kém hơn khi một tenant tăng trưởng lớn hoặc nghiệp vụ thay đổi filter. Theo dõi slow query, latency, index usage, ghi và dung lượng; điều chỉnh bằng quy trình deployment/rollback có kiểm soát.

## 16. Bẫy thường gặp

| Nhận định hoặc triệu chứng | Vấn đề | Cách xử lý |
|---|---|---|
| “Cứ index mọi field dùng trong filter” | Nhiều index tăng write/storage cost | Thiết kế theo mẫu truy vấn |
| “Thứ tự field trong compound index không quan trọng” | Bỏ lỡ prefix và sort từ index | Phân tích E/S/R và thứ tự key |
| “Equality phải xếp theo selectivity giảm dần trong mọi trường hợp” | Bỏ qua query prefix khác và sort | Đánh giá workload tổng thể |
| “Range luôn phải cuối index” | Range rất chọn lọc có thể cần ERS | So sánh ESR/ERS bằng explain |
| “Index có tất cả field thì luôn tránh SORT” | Range đặt trước sort có thể phá thứ tự toàn cục | Kiểm tra sort theo compound key và explain |
| “createIndex thành công chứng minh query nhanh” | Planner có thể chọn index khác/COLLSCAN | Dùng explain và benchmark |
| “SORT stage lúc nào cũng xấu” | Sort tập nhỏ sau range có thể rẻ | Xem số key/document và thời gian |
| “limit(20) chỉ cần đọc 20 document” | Sort/filter có thể đọc rất nhiều key/document | Dùng index thích hợp, kiểm tra executionStats |
| “Càng nhiều compound index càng tốt” | Lưu trữ, RAM và ghi tăng | Gộp query patterns, loại index thừa có kiểm chứng |
| “Index có _id mặc định nên query nào cũng được cover” | Secondary index không mặc nhiên chứa mọi field cần projection | Xác minh covered query và `totalDocsExamined` |
| “Compound index phục vụ tốt mọi subset field” | Prefix không giống suffix/middle subset | Kiểm tra điều kiện equality trước sort |
| “Có index sẽ tối ưu mọi regex” | Regex không có anchored prefix hoặc không tương thích collation | Dùng query/index phù hợp |
| “Dùng hint để ép index tốt mãi mãi” | Dữ liệu và workload thay đổi | Dùng hint có căn cứ và theo dõi |

## 17. Bài thực hành tổng hợp

Bài tập sử dụng collection `esr_index_lab.orders` ở mục 9. Không cần sửa dữ liệu ngoài database thực hành.

### Bài A — Nhận diện E/S/R

Cho truy vấn:

```javascript
orders.find({
  tenantId: "shop-a",
  status: "PAID",
  total: { $lt: 300 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(5);
```

Hãy xác định:

1. Field nào là equality?
2. Field nào là sort?
3. Field nào là range?
4. Đề xuất một index ESR và một index ERS.
5. Vì sao hai index có thể cho cùng kết quả nhưng khác chi phí thực thi?

### Bài B — Sử dụng index prefix

Giả sử index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

Đánh giá khả năng tận dụng prefix hoặc thứ tự sort của từng query:

```javascript
// Q1
orders.find({ tenantId: "shop-a" });

// Q2
orders.find({ tenantId: "shop-a", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 });

// Q3
orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 });

// Q4
orders.find({ tenantId: "shop-a" })
  .sort({ createdAt: -1, _id: -1 });
```

Gợi ý: Q2 cố định cả hai field trước sort; Q4 còn nhiều nhóm status nên không có global order `createdAt` chỉ từ index này.

### Bài C — So sánh ESR và ERS bằng explain

Chạy:

```javascript
const queryFilter = {
  tenantId: "shop-a",
  status: "PAID",
  total: { $gte: 100 }
};

const querySort = { createdAt: -1, _id: -1 };

const planESR = orders.find(queryFilter)
  .sort(querySort)
  .limit(3)
  .hint("idx_esr")
  .explain("executionStats");

const planERS = orders.find(queryFilter)
  .sort(querySort)
  .limit(3)
  .hint("idx_ers")
  .explain("executionStats");

printjson(planESR);
printjson(planERS);
```

So sánh indexName, indexBounds, sự có mặt của SORT, keys examined, docs examined và nReturned. Trên bộ dữ liệu nhỏ, **không kết luận hiệu năng production chỉ từ thời gian vài mili giây**.

### Bài D — Đổi điều kiện range và dự đoán ảnh hưởng

So sánh hai filter:

```javascript
{ tenantId: "shop-a", status: "PAID", total: { $gte: 50 } }

{ tenantId: "shop-a", status: "PAID", total: { $gte: 600 } }
```

Filter thứ hai chọn ít document hơn trong bộ dữ liệu lab. Dự đoán tại sao index ERS có thể có lợi hơn khi một range trở nên rất chọn lọc, nhưng kết luận phải dựa trên explain và query thật.

### Bài E — Tính chi phí index cho ứng dụng

Một hệ thống giả định ghi 10000 order mỗi phút và có 6 compound index. Hãy thảo luận:

- Các thao tác insert/update phải duy trì những index nào?
- Nếu thêm index thứ bảy chỉ phục vụ report chạy một lần/ngày, chi phí có đáng không?
- Nếu index mới làm một API quan trọng giảm thời gian phản hồi đáng kể thì quyết định có đổi không?
- Làm thế nào để đo index usage, storage và write throughput trước khi giữ/xóa index?

Bài tập yêu cầu **lý luận đánh đổi**, không thể suy ra một con số CPU/RAM chính xác chỉ từ lượng document và số index.

## 18. Tài liệu chính thức

- [MongoDB Manual – The ESR (Equality, Sort, Range) Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual – Compound Index Prefixes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/index-prefix/)
- [MongoDB Manual – Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB Manual – Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual – Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual – Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual – Indexes and Query Performance](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Java Sync Driver – Work with Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)

**Điểm cốt lõi:** Equality giúp thu hẹp vùng index, Sort giúp trả kết quả theo thứ tự sẵn có, còn Range có thể giới hạn tập key. **ESR thường là điểm xuất phát tốt khi truy vấn vừa lọc vừa sort; ERS đáng thử khi range rất chọn lọc.** Quyết định cuối cùng phải dựa trên `explain`, dữ liệu và khối lượng truy vấn thực tế cùng chi phí duy trì index.
