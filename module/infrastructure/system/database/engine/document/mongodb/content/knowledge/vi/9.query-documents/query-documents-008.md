# Sắp xếp nhiều trường và tạo thứ tự ổn định khi giá trị trùng trong MongoDB

## Mục tiêu bài học

Trong MongoDB, một truy vấn có thể sắp xếp document theo nhiều trường, mỗi trường có chiều tăng hoặc giảm riêng. Khi nhiều document có cùng giá trị tại trường sắp xếp, **thứ tự giữa chúng không tự động được đảm bảo** nếu chưa có trường phân xử (tie-breaker) đủ để xác định duy nhất từng document.

Ví dụ, khi hiển thị các đơn hàng mới nhất, hai đơn có thể có cùng `createdAt` đến mức mili giây. Truy vấn chỉ dùng `sort({ createdAt: -1 })` có thể trả hai đơn theo thứ tự khác nhau giữa những lần chạy. Vấn đề trở nên rõ rệt khi phân trang: người dùng có thể thấy một đơn xuất hiện ở hai trang, hoặc không xuất hiện ở trang nào trong một điều kiện dữ liệu nhất định.

Bài học này giải thích cách thiết kế **thứ tự toàn phần ổn định** trong phạm vi tập kết quả, cách chọn **compound index** tương ứng và cách đưa thứ tự đó vào phân trang.

Sau bài học, người học có thể:

- Dùng `sort()` với nhiều trường và các chiều `1` (tăng), `-1` (giảm).
- Giải thích MongoDB so sánh từng trường theo thứ tự ưu tiên trong sort specification.
- Nhận diện trường hợp nhiều document trùng khóa sắp xếp và dùng `_id` hoặc khóa duy nhất để phân xử.
- Kết hợp `find()`, `sort()`, `limit()`, `skip()` và aggregation `$sort`.
- Thiết kế compound index phục vụ cả filter và sort; đọc kế hoạch bằng `explain("executionStats")`.
- Xây dựng **keyset/cursor pagination** với thứ tự ổn định, kể cả khi có chiều tăng và giảm.
- Phân biệt **thứ tự xác định** với **tính nhất quán của dữ liệu giữa nhiều lần truy vấn** khi có insert/update/delete.
- Xử lý các trường hợp đặc biệt như null, field thiếu, kiểu BSON khác nhau, chuỗi có collation và mảng.

> **Quy tắc chính:** Nếu một danh sách có thể phân trang, cần có thứ tự hoàn chỉnh. Ví dụ: `sort({ createdAt: -1, _id: -1 })`. `createdAt` thể hiện ý nghĩa nghiệp vụ; `_id` là khóa cuối cùng giúp phân xử khi timestamp trùng.

---

## 1. Vì sao sắp xếp một trường có thể chưa đủ?

Giả sử collection `orders` có các đơn:

| `_id` | `customerId` | `priority` | `createdAt` | `status` |
|---|---|---:|---|---|
| `O-001` | `C-01` | 2 | 2026-11-10 09:00:00Z | PAID |
| `O-002` | `C-01` | 2 | 2026-11-10 09:00:00Z | PAID |
| `O-003` | `C-01` | 3 | 2026-11-11 08:00:00Z | NEW |
| `O-004` | `C-01` | 3 | 2026-11-11 08:00:00Z | NEW |
| `O-005` | `C-01` | 1 | 2026-11-12 09:00:00Z | PAID |
| `O-006` | `C-01` | 2 | 2026-11-12 11:00:00Z | NEW |
| `O-007` | `C-01` | 1 | 2026-11-09 14:00:00Z | CANCELED |
| `O-008` | `C-01` | 2 | 2026-11-13 10:00:00Z | PAID |

Nếu truy vấn:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1
});
~~~

thì MongoDB nhóm các document có `priority` cao hơn lên trước, nhưng các document `O-003` và `O-004` có cùng mức ưu tiên 3. Không có điều kiện bổ sung nào xác định đơn nào đứng trước.

Ngay cả khi thêm timestamp:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1
});
~~~

thì `O-003` và `O-004` vẫn bằng nhau ở cả hai trường. Thêm một khóa duy nhất:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

Lúc này `O-003` đứng trước `O-004` vì cùng `priority`, cùng `createdAt` nhưng `"O-003" < "O-004"`.

**Lưu ý:** MongoDB có thể tình cờ trả các document trùng khóa theo thứ tự giống nhau trong nhiều lần chạy, nhưng thứ tự đó **không được đảm bảo** khi các trường sort không phân biệt được chúng. Đổi index, kế hoạch truy vấn, topology hoặc tập dữ liệu có thể làm kết quả đổi thứ tự.

### 1.1. “Ổn định” nghĩa là gì trong bài này?

Cần phân biệt hai khái niệm:

1. **Thứ tự xác định (deterministic order):** với cùng tập document và giá trị khóa sắp xếp, mỗi document có vị trí được xác định bởi danh sách khóa, không phụ thuộc thứ tự nội bộ của storage engine.
2. **Ảnh chụp dữ liệu nhất quán (consistent snapshot):** nhiều truy vấn ở những thời điểm khác nhau có thấy cùng trạng thái dữ liệu hay không.

Thêm `_id` vào sort giải quyết vấn đề thứ nhất. Nó **không tự khóa snapshot dữ liệu**: nếu có đơn mới được thêm, hoặc một đơn đổi `priority` giữa hai trang, tập kết quả và vị trí các document có thể thay đổi.

---

## 2. Cú pháp sắp xếp nhiều trường

Trong **mongosh**:

~~~javascript
db.orders.find(filter).sort({
  firstField: 1,
  secondField: -1,
  thirdField: 1
});
~~~

Ý nghĩa:

- Giá trị `1`: sắp xếp **tăng dần**.
- Giá trị `-1`: sắp xếp **giảm dần**.
- **Thứ tự khai báo các field trong đối tượng sort có ý nghĩa**: MongoDB xét trường đầu tiên trước, rồi đến trường thứ hai khi các giá trị ở trường đầu bằng nhau, và tiếp tục tương tự.

Ví dụ:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  status: 1,
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

MongoDB thực hiện theo thứ tự ưu tiên:

1. `status` theo chiều tăng.
2. Trong nhóm có cùng `status`, `priority` giảm.
3. Trong nhóm cùng `status` và `priority`, `createdAt` giảm.
4. Nếu cả ba trường đầu giống nhau, `_id` tăng để phân xử.

Thứ tự này là kiểu so sánh **từ điển (lexicographic ordering)** trên bộ giá trị. Không phải MongoDB tính điểm tổng hay luân phiên các trường.

### 2.1. Khóa đầu tiên có ưu tiên cao nhất

So sánh:

~~~javascript
// A: Ưu tiên trạng thái trước, thời gian sau
db.orders.find().sort({
  status: 1,
  createdAt: -1,
  _id: -1
});

// B: Ưu tiên thời gian trước, trạng thái sau
db.orders.find().sort({
  createdAt: -1,
  status: 1,
  _id: -1
});
~~~

Hai truy vấn có **cùng tập trường** nhưng cho **thứ tự khác nhau**, vì thứ tự trường trong sort specification khác nhau.

Truy vấn A nhóm các document theo trạng thái trước. Truy vấn B hiển thị tất cả đơn mới hơn lên trước, và chỉ dùng trạng thái để phân xử khi timestamp bằng nhau.

### 2.2. Chiều tăng/giảm có thể trộn

Ví dụ “ưu tiên cao trước; cùng mức ưu tiên thì đơn cũ trước; cùng cả hai thì mã tăng dần”:

~~~javascript
db.orders.find().sort({
  priority: -1,
  createdAt: 1,
  _id: 1
});
~~~

Không có quy tắc bắt buộc mọi field phải cùng chiều. Tuy nhiên, **hướng sort của compound index** cũng cần tương thích nếu muốn tránh bước sắp xếp bổ sung.

### 2.3. `sort()` không thay đổi thứ tự lưu vật lý

`sort()` là yêu cầu về **thứ tự trả kết quả**. Nó không xếp lại các document trong collection theo thứ tự đã chọn.

Không dựa vào “thứ tự tự nhiên” (natural order), thứ tự insert, thứ tự lưu trên disk hoặc thứ tự `_id` ngầm định khi không có `sort()`. Những thứ tự đó không phải hợp đồng trả dữ liệu cho API.

---

## 3. Tạo dữ liệu thực hành

Các ví dụ sau dùng mongosh trong database **`sort_lab`**. Chúng tạo dữ liệu thử nghiệm; không chạy trên collection production.

~~~javascript
use sort_lab

db.orders.insertMany([
  {
    _id: "O-001",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-002",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-003",
    customerId: "C-01",
    priority: 3,
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    status: "NEW"
  },
  {
    _id: "O-004",
    customerId: "C-01",
    priority: 3,
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    status: "NEW"
  },
  {
    _id: "O-005",
    customerId: "C-01",
    priority: 1,
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-006",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-12T11:00:00Z"),
    status: "NEW"
  },
  {
    _id: "O-007",
    customerId: "C-01",
    priority: 1,
    createdAt: ISODate("2026-11-09T14:00:00Z"),
    status: "CANCELED"
  },
  {
    _id: "O-008",
    customerId: "C-01",
    priority: 2,
    createdAt: ISODate("2026-11-13T10:00:00Z"),
    status: "PAID"
  },
  {
    _id: "O-009",
    customerId: "C-02",
    priority: 2,
    createdAt: ISODate("2026-11-13T10:00:00Z"),
    status: "NEW"
  }
]);
~~~

Kiểm tra:

~~~javascript
db.orders.countDocuments({});
~~~

Kết quả dự kiến cho tập dữ liệu vừa tạo là 9 document. Các ví dụ truy vấn theo khách `C-01` dùng 8 document.

### 3.1. Sort chỉ theo `priority`

~~~javascript
db.orders.find(
  { customerId: "C-01" },
  { _id: 1, priority: 1, createdAt: 1 }
).sort({
  priority: -1
});
~~~

Các document có priority 3 đứng trước priority 2, sau đó priority 1. Thứ tự **bên trong mỗi nhóm** không được đảm bảo do `priority` trùng.

### 3.2. Sort ba trường tạo thứ tự toàn phần

~~~javascript
db.orders.find(
  { customerId: "C-01" },
  { _id: 1, priority: 1, createdAt: 1 }
).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

Với dữ liệu trên, kết quả `_id` theo thứ tự:

~~~text
O-003
O-004
O-008
O-006
O-001
O-002
O-005
O-007
~~~

Diễn giải:

- `O-003` và `O-004` cùng priority 3 và cùng timestamp; `_id` tăng nên O-003 đứng trước.
- Các đơn priority 2 xếp theo thời gian mới nhất: O-008, O-006, rồi hai đơn cùng timestamp O-001/O-002.
- Nhóm priority 1 xếp O-005 trước O-007 vì mới hơn.

Đây là **thứ tự xác định** miễn là các giá trị khóa sort và tập document không thay đổi.

### 3.3. Đảo chiều khóa cuối

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1,
  _id: -1
});
~~~

Khi priority và timestamp trùng, `_id` giảm: O-004 đứng trước O-003; O-002 đứng trước O-001. Các nhóm khác giữ nguyên quan hệ theo hai khóa đầu.

---

## 4. Tại sao `_id` thường là tie-breaker tốt?

Mỗi document trong một collection thông thường có trường `_id`; MongoDB áp đặt tính duy nhất của `_id` theo các điều kiện áp dụng của deployment. Trong tập truy vấn thuộc một collection có `_id` duy nhất, thêm nó làm khóa cuối thường đủ để phân xử các trường hợp bằng nhau ở những field trước.

Ví dụ chuẩn để hiển thị mới nhất trước:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  createdAt: -1,
  _id: -1
});
~~~

Điểm mạnh:

- Không cần một sequence bổ sung chỉ để tạo thứ tự.
- Khóa tie-breaker có sẵn trong phần lớn các collection.
- Có thể đưa vào compound index.
- Có thể dùng làm thành phần cursor của keyset pagination.

Nhưng cần hiểu các giới hạn:

1. **`_id` là khóa định danh, không phải đồng hồ nghiệp vụ.** ObjectId có thành phần thời gian, nhưng không nên thay `createdAt` bằng suy luận “ObjectId tăng tuyệt đối theo thời gian tạo” trong hệ thống phân tán.
2. **Kiểu `_id` cần nhất quán.** Nếu trộn string, number và ObjectId, MongoDB có quy tắc so sánh BSON theo type. Thứ tự vẫn có thể xác định nhưng khó hiểu về nghiệp vụ.
3. **Khóa tie-breaker phải phân biệt được kết quả.** Trong một aggregation hoặc join, nếu output đã nhân bản một `_id` qua nhiều hàng kết quả, chỉ `_id` có thể chưa đủ; cần khóa duy nhất cho từng result row.
4. **Phạm vi tính duy nhất cần đúng với topology.** Với sharded collection, quy tắc bảo đảm unique `_id` và việc sử dụng shard key có những chi tiết riêng; hệ thống cần thiết kế tính duy nhất phù hợp với toàn bộ dữ liệu truy vấn.
5. **Không dùng `_id` như cam kết sequence tăng liên tục.** Với UUID hoặc chuỗi bất kỳ, hướng sắp xếp theo `_id` chỉ là hướng trên giá trị khóa.

Nếu nghiệp vụ đã có một khóa duy nhất khác, chẳng hạn `orderNo` với unique index đáng tin cậy, có thể dùng khóa đó làm tie-breaker thay `_id`. Nhưng hãy chứng minh tính duy nhất và kiểu dữ liệu ổn định.

### 4.1. Tie-breaker chỉ có ích sau những trường nghiệp vụ

Ví dụ:

~~~javascript
db.orders.find().sort({
  _id: -1
});
~~~

Truy vấn này xác định thứ tự theo `_id`, nhưng **không nhất thiết phản ánh thời điểm tạo đơn**. Nếu yêu cầu là “đơn mới nhất”, chọn:

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
});
~~~

`createdAt` mang nghĩa “mới nhất”; `_id` chỉ giải quyết tình huống timestamp trùng.

### 4.2. Các phương án tie-break khác

| Khóa cuối | Khi phù hợp | Điều kiện |
|---|---|---|
| `_id` | Danh sách document thông thường | Unique trong tập kết quả cần phân trang |
| `orderNo` | Danh sách đơn hàng có mã nghiệp vụ | Unique index / bảo đảm nghiệp vụ |
| `eventSequence` | Luồng sự kiện có thứ tự nghiệp vụ | Có cơ chế cấp sequence đáng tin, phạm vi nhất quán rõ |
| Khóa ghép `tenantId` + `orderNo` | Hệ thống multi-tenant | Cần bảo đảm unique trên bộ giá trị, không chỉ orderNo riêng |
| Khóa kết quả aggregation | `$unwind`/`$group` tạo hàng dẫn xuất | Các field phân biệt được từng dòng kết quả |

Chỉ thêm nhiều field không tự bảo đảm tính duy nhất. Phải có khóa hoặc tổ hợp khóa **duy nhất trong tập kết quả**.

---

## 5. Sort trong aggregation pipeline

Với aggregation, sử dụng stage `$sort`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      customerId: "C-01"
    }
  },
  {
    $sort: {
      priority: -1,
      createdAt: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      priority: 1,
      createdAt: 1,
      status: 1
    }
  },
  {
    $limit: 5
  }
]);
~~~

Cũng cần tie-breaker trong `$sort` nếu nhiều document có cùng giá trị. Stage `$sort` **không phải stable sort** theo nghĩa tự duy trì thứ tự đầu vào giữa các giá trị trùng. Nếu một pipeline biến đổi tập document trước khi sort, hãy kiểm tra rằng khóa cuối vẫn phân biệt được mỗi kết quả.

### 5.1. `$match` nên đặt trước `$sort` khi phù hợp

~~~javascript
[
  { $match: { customerId: "C-01" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 20 }
]
~~~

Điều kiện lọc trước sort có thể giảm dữ liệu phải sắp xếp. Với index phù hợp, MongoDB còn có thể lấy dữ liệu theo đúng thứ tự index.

Tuy nhiên, tối ưu hóa aggregation phụ thuộc các stage khác; ví dụ một `$project` hoặc `$unwind` đặt trước sort có thể ảnh hưởng khả năng tận dụng index. Dùng explain thay vì giả định mọi pipeline đều tối ưu giống nhau.

### 5.2. `$limit` sau `$sort`

~~~javascript
db.orders.aggregate([
  { $match: { customerId: "C-01" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 20 }
]);
~~~

Phải **sắp xếp trước khi chọn 20 document đầu** để có 20 kết quả đúng theo yêu cầu. Nếu limit trước:

~~~javascript
// Đây là ý nghĩa khác: lấy 20 document trước rồi chỉ sắp xếp 20 document đó.
db.orders.aggregate([
  { $match: { customerId: "C-01" } },
  { $limit: 20 },
  { $sort: { createdAt: -1, _id: -1 } }
]);
~~~

thì không bảo đảm lấy được 20 đơn mới nhất toàn collection.

Một số dạng pipeline cho phép MongoDB tối ưu hóa `$sort` + `$limit`, nhưng không nên thay đổi thứ tự logic của các stage khi chưa hiểu ý nghĩa.

### 5.3. Sort kết quả sau `$group`

Ví dụ tổng số đơn theo trạng thái:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      totalOrders: { $sum: 1 }
    }
  },
  {
    $sort: {
      totalOrders: -1,
      _id: 1
    }
  }
]);
~~~

Nếu hai trạng thái có cùng `totalOrders`, khóa `_id` của nhóm (ở đây là trạng thái) làm tie-breaker. Không phải lúc nào `_id` sau `$group` cũng còn là `_id` document nguồn: nó chính là **grouping key**.

### 5.4. `$unwind` và hàng kết quả trùng `_id`

Ví dụ một đơn có nhiều items. Sau `$unwind`, mỗi line item có thể mang cùng `_id` của đơn:

~~~javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $sort: {
      createdAt: -1,
      _id: -1
    }
  }
]);
~~~

Với nhiều items cùng đơn, `createdAt` và `_id` vẫn trùng; thứ tự từng item chưa được phân xử. Nếu cần thứ tự ổn định theo vị trí mảng, hãy dùng `includeArrayIndex` và thêm chỉ số đó vào sort:

~~~javascript
db.orders.aggregate([
  {
    $unwind: {
      path: "$items",
      includeArrayIndex: "itemIndex"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: -1,
      itemIndex: 1
    }
  }
]);
~~~

Cách này phân biệt các phần tử của cùng một đơn theo vị trí tại thời điểm đọc. Nếu mảng có thể bị sửa giữa những lần phân trang, thứ tự vẫn chịu ảnh hưởng của thay đổi dữ liệu.

---

## 6. Compound index cho sắp xếp nhiều trường

### 6.1. Vì sao sort có thể chậm?

Không có index phù hợp, MongoDB có thể phải:

1. Đọc những document thỏa filter.
2. Tính khóa sắp xếp cho từng document.
3. Sắp xếp chúng trong bộ nhớ hoặc qua cơ chế hỗ trợ trên disk tùy phiên bản/cấu hình.
4. Trả phần kết quả theo limit.

Trên collection lớn, sort không tận dụng được index có thể tốn RAM/CPU/disk và tăng latency. Bước sắp xếp được phản ánh trong kế hoạch truy vấn.

### 6.2. Index phục vụ filter và sort

Truy vấn thường dùng:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Compound index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_created_id"
  }
);
~~~

Cấu trúc:

~~~text
customerId ASC  -> equality filter
createdAt DESC  -> yêu cầu sort chính
_id DESC        -> tie-breaker
~~~

Khi `customerId` được cố định bằng equality, các key trong index phù hợp có thể đã được sắp xếp theo `createdAt DESC, _id DESC`. MongoDB có thể lấy kết quả theo thứ tự index mà không cần sort riêng.

**Lưu ý:** Index mặc định trên `_id` không tự có nghĩa mọi compound index khác đã bao gồm `_id` theo hướng mong muốn. Nếu sort dùng `_id` làm trường phụ, hãy cân nhắc khai báo nó tường minh trong compound index phục vụ truy vấn.

### 6.3. Trật tự field và hướng sort rất quan trọng

Xét index:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

Index này phù hợp để thử cho:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

Nhưng truy vấn:

~~~javascript
db.orders.find(
  { customerId: "C-01" }
).sort({
  priority: -1,
  createdAt: 1,
  _id: 1
});
~~~

đã đổi riêng chiều `createdAt`. Một compound index không tự hỗ trợ mọi tổ hợp hướng tăng/giảm. Trong nhiều trường hợp, index có thể hỗ trợ thứ tự đã khai báo **hoặc đảo ngược toàn bộ chiều của những khóa sort tương ứng**, chứ không thể đảo tùy ý một field trong khi giữ các field khác.

Vì vậy phải đo đúng các mẫu sort mà API thực tế dùng. Không tạo hàng chục index chỉ để dự phòng các tổ hợp hướng không được dùng.

### 6.4. Equality trước, sort sau

Một nguyên tắc hữu ích khi thiết kế compound index là **Equality – Sort – Range (ESR)**: đặt các field equality filter trước, rồi những field giúp sắp xếp, tiếp đến range khi phù hợp. Đây là hướng dẫn thực hành, không phải công thức bất biến.

Ví dụ:

~~~javascript
db.orders.find({
  customerId: "C-01",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent"
  }
);
~~~

Nếu lọc `status` không có trong query, index này có thể không giúp sắp xếp hiệu quả như index bỏ qua `status`, vì `status` là một khóa nằm giữa `customerId` và các field sort. Hãy thiết kế index theo **các query shape phổ biến**, không chỉ index rộng nhất có thể.

### 6.5. Dùng `explain("executionStats")` để xác nhận

~~~javascript
const details = db.orders
  .find({ customerId: "C-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

printjson(details.queryPlanner.winningPlan);
printjson(details.executionStats);
~~~

Những trường hữu ích:

| Trường | Ý nghĩa |
|---|---|
| `winningPlan` | Kế hoạch MongoDB chọn |
| `IXSCAN` hoặc cấu trúc index scan tương đương | Duyệt index |
| `COLLSCAN` | Quét collection |
| `SORT` hoặc stage sắp xếp tương đương | Bước sắp xếp cần tài nguyên riêng |
| `nReturned` | Số document được trả |
| `totalKeysExamined` | Số index key đã xem |
| `totalDocsExamined` | Số document được kiểm tra/fetch |
| `executionTimeMillis` | Thời gian báo cáo trong explain |

Các trường/stage thực tế khác nhau theo phiên bản và query engine. Với dataset nhỏ, planner có thể chọn COLLSCAN vì rẻ hơn dùng index; đừng chỉ nhìn một ví dụ 9 document rồi kết luận index không cần thiết.

`explain` giúp hiểu kế hoạch, nhưng benchmark latency production còn cần network, driver, cache, concurrency và phân bố dữ liệu lớn.

### 6.6. Sort in memory và giới hạn tài nguyên

Nếu không thể lấy thứ tự từ index, MongoDB phải thực hiện sort. Với tập dữ liệu lớn, thao tác sort có thể vượt giới hạn bộ nhớ; việc ghi tạm ra disk phụ thuộc phiên bản và chính sách, ví dụ `allowDiskUse` hoặc `allowDiskUseByDefault`.

Trong aggregation có thể dùng:

~~~javascript
db.orders.aggregate(
  [
    { $match: { customerId: "C-01" } },
    { $sort: { createdAt: -1, _id: -1 } },
    { $limit: 20 }
  ],
  { allowDiskUse: true }
);
~~~

Đây **không phải cách thay thế index** cho đường đọc quan trọng. Sort trên disk có thể chậm và tiêu tốn tài nguyên; nên xem `winningPlan` và benchmark trên dữ liệu đủ lớn.

---

## 7. Phân trang với `skip()` và `limit()`

### 7.1. Offset pagination

Một cách phổ biến:

~~~javascript
const pageSize = 3;
const pageNumber = 2;

db.orders.find(
  { customerId: "C-01" }
).sort({
  createdAt: -1,
  _id: -1
}).skip(
  (pageNumber - 1) * pageSize
).limit(pageSize);
~~~

Với `pageSize = 3` và `pageNumber = 2`, truy vấn bỏ qua 3 document đầu rồi trả tối đa 3 document tiếp theo.

**Quan trọng:** Sử dụng cùng một sort specification trên mọi trang, bao gồm tie-breaker duy nhất. Nếu chỉ sort theo `createdAt`, những document trùng timestamp có thể thay đổi thứ tự tương đối và gây trùng hoặc sót trong việc chia trang, ngay cả khi dữ liệu không thay đổi.

### 7.2. Vì sao offset lớn tốn kém?

Để lấy trang số 10.000 với mỗi trang 20 kết quả, database thường phải bỏ qua một lượng lớn kết quả trước khi lấy 20 document mong muốn. Index có thể giúp duyệt có thứ tự nhưng không khiến chi phí `skip` lớn biến mất hoàn toàn.

Khi bảng dữ liệu lớn và người dùng cuộn liên tục, **keyset pagination** thường có lợi hơn offset sâu.

### 7.3. Có tie-breaker vẫn chưa giải quyết mọi thay đổi giữa hai trang

Giả sử người dùng lấy trang 1, sau đó có một order mới được chèn với timestamp mới hơn tất cả. Trước khi lấy trang 2 bằng `skip(3)`, order mới làm các vị trí dịch xuống. Một document từ trang 1 có thể xuất hiện lại ở trang 2.

Đây là **dịch chuyển tập kết quả do ghi đồng thời**, khác với **thứ tự không xác định khi khóa trùng nhau**.

Thêm `_id` giải quyết vấn đề khóa trùng. Nhưng offset pagination vẫn có thể trùng/sót khi dữ liệu thay đổi giữa những lần đọc. Nếu cần giảm hiện tượng đó, cân nhắc keyset pagination và chính sách nhất quán dữ liệu phù hợp.

---

## 8. Keyset/cursor pagination với thứ tự ổn định

### 8.1. Nguyên tắc

Với sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Trang đầu đọc 3 document:

~~~javascript
const pageSize = 3;

const firstPage = db.orders
  .find({ customerId: "C-01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(pageSize)
  .toArray();

printjson(firstPage);
~~~

Lấy document cuối trang:

~~~javascript
const last = firstPage[firstPage.length - 1];
~~~

Trang tiếp theo phải lấy những document **đứng sau** `last` trong cùng thứ tự, nghĩa là:

- `createdAt` **nhỏ hơn** timestamp cuối; hoặc
- `createdAt` **bằng** timestamp cuối và `_id` **nhỏ hơn** id cuối (vì cả hai chiều giảm).

~~~javascript
const nextPage = db.orders.find({
  customerId: "C-01",
  $or: [
    {
      createdAt: { $lt: last.createdAt }
    },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(pageSize).toArray();

printjson(nextPage);
~~~

Không cần `skip` theo độ sâu trang. Query giới hạn kết quả bằng điều kiện cursor dựa trên khóa sort.

### 8.2. Công thức cho hai trường cùng chiều giảm

Với thứ tự:

~~~text
sort(A DESC, B DESC)
~~~

và cursor cuối trang `(a, b)`, điều kiện “sau cursor” là:

~~~text
A < a
OR
(A = a AND B < b)
~~~

Với thứ tự cùng chiều tăng:

~~~text
sort(A ASC, B ASC)
~~~

điều kiện là:

~~~text
A > a
OR
(A = a AND B > b)
~~~

Với chiều trộn, điều kiện thay theo từng field.

Ví dụ:

~~~text
sort(priority DESC, _id ASC)

Sau cursor (priority = p, _id = id):
  priority < p
  OR
  (priority = p AND _id > id)
~~~

**Không dùng cùng toán tử `$lt` cho mọi trường khi sort có chiều trộn.**

### 8.3. Ví dụ cursor với ba trường

Sort:

~~~javascript
{
  priority: -1,
  createdAt: -1,
  _id: 1
}
~~~

Giả sử document cuối trang có:

~~~javascript
{
  priority: 2,
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-001"
}
~~~

Điều kiện đọc trang sau là:

~~~javascript
const cursor = {
  priority: 2,
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-001"
};

db.orders.find({
  customerId: "C-01",
  $or: [
    { priority: { $lt: cursor.priority } },
    {
      priority: cursor.priority,
      createdAt: { $lt: cursor.createdAt }
    },
    {
      priority: cursor.priority,
      createdAt: cursor.createdAt,
      _id: { $gt: cursor._id }
    }
  ]
}).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
}).limit(3);
~~~

Đây là điều kiện so sánh từ điển mở rộng: **field đầu tiên khác cursor quyết định vị trí; các field trước đó phải bằng cursor**.

### 8.4. Thiết kế cursor an toàn trong API

Một cursor phía ứng dụng thường cần chứa:

- Giá trị của **tất cả các khóa sort** tại document cuối trang.
- Filter cố định hoặc một dấu định danh filter/query shape để tránh dùng cursor của truy vấn khác.
- Thông tin về chiều sort và version nếu API có thể đổi.
- Cách biểu diễn kiểu dữ liệu chính xác, ví dụ BSON Date và ObjectId.

Không nên chỉ truyền một timestamp dạng string đã cắt mất mili giây rồi so sánh với BSON Date; làm vậy có thể bỏ sót hoặc lặp kết quả. Nếu API dùng opaque cursor, có thể encode các trường theo format có phiên bản và ký/kiểm tra integrity theo thiết kế ứng dụng.

Trong ví dụ sử dụng chuỗi `_id`, cursor cũng có thể dùng chuỗi. Với `_id` là ObjectId, khi giải mã cursor cần chuyển lại ObjectId đúng kiểu; không so chuỗi hex với ObjectId như hai giá trị BSON cùng kiểu.

### 8.5. Các giới hạn khi dữ liệu thay đổi

Keyset pagination giúp tránh chi phí offset sâu và thường giảm hiện tượng dịch vị trí khi có document mới ở đầu danh sách. Nhưng nó **không tự tạo snapshot toàn bộ nhiều request**:

- Nếu một document đã đọc đổi `createdAt` hoặc `priority`, nó có thể chuyển sang vùng chưa đọc và xuất hiện lại.
- Nếu một document chưa đọc đổi khóa và chuyển lên trước cursor, nó có thể không xuất hiện ở các trang tiếp.
- Document bị xóa sẽ biến mất.
- Document mới được thêm với khóa nằm sau cursor có thể xuất hiện ở trang sau.

Nếu yêu cầu nghiệp vụ là “xuất chính xác tập kết quả tại thời điểm T” qua nhiều trang và nhiều phút, cần đánh giá các cơ chế nhất quán/snapshot phù hợp, chiến lược đóng băng tập ID, hoặc quy trình export độc lập. Tie-breaker và keyset chỉ giải quyết **thứ tự**, không thay một snapshot consistency contract.

---

## 9. Các trường hợp khiến kết quả sort khó dự đoán

### 9.1. Field thiếu và giá trị `null`

Ví dụ:

~~~javascript
db.tasks.insertMany([
  { _id: "T-01", priority: 2, title: "Đọc tài liệu" },
  { _id: "T-02", priority: null, title: "Kiểm tra dữ liệu" },
  { _id: "T-03", title: "Viết báo cáo" },
  { _id: "T-04", priority: 1, title: "Đẩy bản phát hành" }
]);
~~~

Truy vấn:

~~~javascript
db.tasks.find().sort({
  priority: 1,
  _id: 1
});
~~~

MongoDB sử dụng **BSON comparison order**. Trong ngữ cảnh sort, field thiếu và `null` có thể được xếp tương đương ở mức khóa sort, do đó `_id` đóng vai trò phân xử. Điều này không có nghĩa ứng dụng tự biết cách phân biệt “chưa được ưu tiên” với “ưu tiên thấp nhất”.

Nếu nghiệp vụ yêu cầu “task không có priority phải luôn xuống cuối”, hãy **chuẩn hóa dữ liệu** thành một giá trị hoặc field sort rõ nghĩa, thay vì vô tình phụ thuộc thứ tự của `null`.

Một read model có thể có:

~~~javascript
{
  _id: "T-03",
  priority: null,
  priorityGroup: 1
}
~~~

và dùng:

~~~javascript
db.tasks.find().sort({
  priorityGroup: 1,
  priority: -1,
  _id: 1
});
~~~

Nếu dùng `priorityGroup`, phải tạo và duy trì field cho mọi document theo quy tắc ứng dụng.

### 9.2. Kiểu BSON không đồng nhất

Một field có lúc là string, có lúc là number:

~~~javascript
{ _id: "A", score: 10 }
{ _id: "B", score: "9" }
{ _id: "C", score: 8 }
~~~

MongoDB không nhất thiết chuyển tất cả sang số để so sánh; nó áp dụng quy tắc thứ tự kiểu BSON. Vì vậy, đừng kỳ vọng chuỗi `"9"` đứng giữa số 8 và 10.

Khuyến nghị:

- Lưu một kiểu BSON nhất quán cho field sort.
- Dùng schema validation khi thích hợp.
- Migrate dữ liệu cũ bị lệch kiểu.
- Nếu cần sort theo giá trị chuyển đổi, cân nhắc xử lý rõ ràng trong aggregation hoặc materialize một sort key.

### 9.3. Sort chuỗi và collation

Mặc định, so sánh chuỗi theo quy tắc binary/simple không giống trực giác ngôn ngữ của mọi người dùng.

Ví dụ collection `users`:

~~~javascript
db.users.insertMany([
  { _id: "U-01", fullName: "An", score: 8 },
  { _id: "U-02", fullName: "an", score: 8 },
  { _id: "U-03", fullName: "Ánh", score: 8 },
  { _id: "U-04", fullName: "Bình", score: 9 }
]);
~~~

Truy vấn với collation:

~~~javascript
db.users.find().collation({
  locale: "vi",
  strength: 2
}).sort({
  fullName: 1,
  _id: 1
});
~~~

`locale: "vi"` lựa chọn quy tắc locale tiếng Việt; `strength: 2` thông thường phân biệt dấu nhưng không phân biệt hoa/thường theo cấp so sánh tương ứng. Những chuỗi có thể coi bằng nhau dưới một collation nhất định vẫn cần khóa cuối `_id` để định vị thứ tự chính xác.

Đối với performance, index dùng để hỗ trợ sort chuỗi cần có **collation tương thích** với truy vấn:

~~~javascript
db.users.createIndex(
  { fullName: 1, _id: 1 },
  {
    name: "idx_fullName_vi",
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

Một index xây theo collation khác có thể không hỗ trợ phần so sánh string như mong muốn. Kiểm tra bằng explain.

### 9.4. Sort trên array

Nếu một field là array, MongoDB có quy tắc chọn phần tử đại diện để sort, phụ thuộc chiều tăng/giảm và ngữ cảnh. Ví dụ:

~~~javascript
db.students.insertMany([
  { _id: "S-01", scores: [6, 9] },
  { _id: "S-02", scores: [7, 8] }
]);
~~~

Sort trực tiếp trên `scores`:

~~~javascript
db.students.find().sort({
  scores: 1,
  _id: 1
});
~~~

không tương đương với “sắp xếp theo điểm trung bình” hoặc “theo phần tử đầu tiên” trong mọi tình huống. Nếu nghiệp vụ cần điểm trung bình hoặc điểm cao nhất, nên có field tính toán rõ nghĩa:

~~~javascript
db.students.aggregate([
  {
    $addFields: {
      averageScore: { $avg: "$scores" }
    }
  },
  {
    $sort: {
      averageScore: -1,
      _id: 1
    }
  }
]);
~~~

Truy vấn với computed sort key có thể cần sắp xếp sau tính toán và không dễ tận dụng index trực tiếp trên `scores`. Nếu đọc thường xuyên, cân nhắc lưu `averageScore` dưới dạng field dẫn xuất với cơ chế cập nhật đúng.

### 9.5. Sort bằng ObjectId không thay thế `createdAt`

ObjectId được thiết kế để định danh và có thành phần timestamp, nhưng giá trị ID không phải một đồng hồ nghiệp vụ chính xác tuyệt đối. Chúng có thể được tạo ở client, nhiều tiến trình hoặc thời điểm khác nhau, và độ phân giải timestamp không đủ để thay mọi yêu cầu thứ tự phát sinh.

Nếu yêu cầu là mới nhất theo thời điểm đặt hàng:

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
});
~~~

Không mặc định sử dụng:

~~~javascript
db.orders.find().sort({
  _id: -1
});
~~~

rồi tuyên bố đó là thứ tự thời gian chính xác của mọi bản ghi.

### 9.6. Thay đổi khóa sort trong lúc người dùng phân trang

Nếu một danh sách được sort theo `priority`, nhưng người dùng hoặc hệ thống có thể đổi priority theo thời gian thực, vị trí document cũng đổi. Cursor không cố định document theo vị trí cũ sau update.

Với bảng danh sách công việc liên tục cập nhật, nên xác định hành vi mong muốn:

- Cho phép danh sách biến động và hiển thị dữ liệu mới.
- Cố định một mốc lọc theo thời gian hoặc version.
- Hiển thị cảnh báo “danh sách có thay đổi” và cho người dùng refresh.
- Thực hiện export tại một snapshot có kiểm soát nếu tính chính xác tuyệt đối cần thiết.

---

## 10. Sắp xếp ổn định khi có nhiều filter và nhiều sort key

### 10.1. Filter không đồng nghĩa sort

Truy vấn:

~~~javascript
db.orders.find({
  customerId: "C-01",
  status: { $in: ["NEW", "PAID"] }
}).sort({
  priority: -1,
  createdAt: -1,
  _id: 1
});
~~~

MongoDB lọc document theo điều kiện trước khi xác định thứ tự trả về. Trường `status` trong filter không tự xuất hiện trong thứ tự nếu không được nêu trong `sort`.

Nếu nghiệp vụ muốn ưu tiên NEW trước PAID, không thể suy ra điều đó từ thứ tự phần tử trong `$in`. Phải bổ sung thứ tự nghiệp vụ rõ ràng (ví dụ field `statusRank`) hoặc một biểu thức tính toán tương ứng.

### 10.2. Sắp xếp theo thứ tự nghiệp vụ tự định nghĩa

Ví dụ thứ tự trạng thái mong muốn là:

~~~text
NEW -> PAID -> CANCELED
~~~

Sắp xếp alphabet theo `status` không cho thứ tự trên. Một giải pháp là lưu `statusRank`:

~~~javascript
{
  _id: "O-101",
  status: "NEW",
  statusRank: 1,
  createdAt: new Date()
}
~~~

Truy vấn:

~~~javascript
db.orders.find().sort({
  statusRank: 1,
  createdAt: -1,
  _id: -1
});
~~~

Khi thay đổi trạng thái, `statusRank` phải được cập nhật nhất quán. Nếu không muốn lưu field dẫn xuất, có thể tính nó bằng `$switch` trong aggregation:

~~~javascript
db.orders.aggregate([
  {
    $addFields: {
      statusRank: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "NEW"] },
              then: 1
            },
            {
              case: { $eq: ["$status", "PAID"] },
              then: 2
            },
            {
              case: { $eq: ["$status", "CANCELED"] },
              then: 3
            }
          ],
          default: 99
        }
      }
    }
  },
  {
    $sort: {
      statusRank: 1,
      createdAt: -1,
      _id: -1
    }
  }
]);
~~~

Điểm đánh đổi: sort theo field tính toán trong pipeline thường không tận dụng một index trên field `statusRank` chưa được lưu. Nếu API dùng nhiều và collection lớn, materialize rank kèm index phù hợp có thể đáng cân nhắc.

### 10.3. Top N theo từng nhóm không giống sort toàn bộ

Một câu hỏi khác là “mỗi khách lấy 3 đơn mới nhất”. Chỉ chạy:

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
}).limit(3);
~~~

sẽ trả **3 đơn mới nhất toàn collection**, không phải 3 đơn cho từng khách.

Muốn lấy Top N theo nhóm cần pipeline hoặc kỹ thuật khác (chẳng hạn window functions, group cùng các toán tử phù hợp theo phiên bản). Trong mỗi nhóm vẫn nên có tie-breaker nếu những giá trị thứ tự nghiệp vụ trùng nhau.

---

## 11. Java và Spring Data MongoDB: giữ sort order nhất quán

### 11.1. Java Sync Driver

MongoDB Java Driver có các helper trong `com.mongodb.client.model.Sorts`:

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;
import static com.mongodb.client.model.Sorts.orderBy;

import org.bson.Document;
import com.mongodb.client.MongoCollection;

MongoCollection<Document> orders = database.getCollection("orders");

orders.find(eq("customerId", "C-01"))
      .sort(orderBy(
          descending("createdAt"),
          descending("_id")
      ))
      .limit(20)
      .forEach(System.out::println);
~~~

Đây là ví dụ phần query; biến `database` cần được tạo từ một `MongoClient` đã kết nối. Nếu API đọc danh sách đơn theo thứ tự cũ nhất trước, đổi chiều tương ứng:

~~~java
import static com.mongodb.client.model.Sorts.ascending;

orders.find(eq("customerId", "C-01"))
      .sort(orderBy(
          ascending("createdAt"),
          ascending("_id")
      ))
      .limit(20);
~~~

**Giữ một quy tắc thống nhất:** Sort trong driver phải có đúng cùng field và chiều như cursor pagination. Không tạo cursor dựa trên một thứ tự nhưng truy vấn trang sau bằng thứ tự khác.

### 11.2. Spring Data MongoDB

Có thể tạo `Sort`:

~~~java
import org.springframework.data.domain.Sort;

Sort stableSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("_id")
);
~~~

Với `MongoTemplate`:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("customerId").is("C-01")
);

query.with(stableSort);
query.limit(20);

var orders = mongoTemplate.find(
    query,
    OrderDocument.class,
    "orders"
);
~~~

Trong dự án có mapping giữa Java property và MongoDB field, cần xác định chính xác field lưu trữ. `_id` có thể được ánh xạ từ property Java được đánh dấu `@Id`; hãy kiểm tra mapping thay vì giả định mọi property có cùng tên ở BSON.

### 11.3. API nên mô tả sort như một phần hợp đồng

Ví dụ endpoint:

~~~text
GET /customers/C-01/orders?limit=20&sort=recent
~~~

Có thể định nghĩa:

~~~text
sort=recent:
  createdAt DESC, _id DESC

sort=oldest:
  createdAt ASC, _id ASC

sort=priority:
  priority DESC, createdAt DESC, _id ASC
~~~

Không nên cho client tự truyền mọi tổ hợp field và direction vào database nếu không có kiểm soát. Số lượng sort shape không giới hạn làm khó tối ưu index, có thể gây sort tốn tài nguyên và khiến cursor encoding phức tạp.

API có thể cung cấp một tập sort mode có ý nghĩa nghiệp vụ, kiểm thử và index tương ứng.

---

## 12. Những lỗi thường gặp

### Lỗi 1 — Chỉ sort theo timestamp

~~~javascript
db.orders.find().sort({ createdAt: -1 });
~~~

**Vấn đề:** Nhiều đơn có cùng timestamp nên thứ tự giữa chúng không được đảm bảo.

**Giải pháp:**

~~~javascript
db.orders.find().sort({
  createdAt: -1,
  _id: -1
});
~~~

### Lỗi 2 — Tin rằng sort đã ổn định vì kết quả test luôn giống nhau

Trong một database nhỏ và một kế hoạch truy vấn cố định, kết quả có thể tình cờ giống nhau qua nhiều lần. Điều đó không trở thành bảo đảm của MongoDB khi có khóa sort trùng.

**Giải pháp:** Thêm khóa duy nhất và xây test có dữ liệu cố ý trùng timestamp, priority.

### Lỗi 3 — Dùng `skip` mà không có sort

~~~javascript
db.orders.find().skip(20).limit(20);
~~~

**Vấn đề:** Không có thứ tự được chỉ định, nên các trang không có quy tắc ổn định.

**Giải pháp:** Luôn chỉ định sort đầy đủ cho API phân trang.

### Lỗi 4 — Dùng `skip` rất sâu và cho rằng index giải quyết hết

Dù có index, bỏ qua hàng trăm nghìn kết quả vẫn có chi phí.

**Giải pháp:** Dùng keyset/cursor pagination cho luồng xem trang kế tiếp theo thứ tự.

### Lỗi 5 — Dùng cursor chỉ gồm timestamp

~~~javascript
// Chưa đủ nếu có nhiều document cùng createdAt
db.orders.find({
  createdAt: { $lt: lastCreatedAt }
}).sort({
  createdAt: -1
});
~~~

**Vấn đề:** Các document còn lại cùng timestamp với document cuối trang có thể bị bỏ sót.

**Giải pháp:** Cursor gồm cả `createdAt` và tie-breaker `_id`; thêm nhánh equality.

### Lỗi 6 — Dùng sai dấu so sánh với chiều sort

Với sort `{ priority: -1, _id: 1 }`, điều kiện tiếp theo không phải `priority < p OR _id < id`. Ở mức priority bằng nhau, `_id` cần **lớn hơn** cursor vì đang sort tăng.

**Giải pháp:** Viết điều kiện “sau cursor” theo phép so sánh từ điển và từng chiều.

### Lỗi 7 — Cho rằng `_id` luôn có thứ tự thời gian chính xác

**Vấn đề:** Giá trị `_id` có thể là string/UUID, và cả ObjectId cũng không phải đồng hồ nghiệp vụ tuyệt đối.

**Giải pháp:** Dùng timestamp nghiệp vụ chính và `_id` làm khóa phụ.

### Lỗi 8 — Thiết kế compound index sai thứ tự field

Truy vấn lọc `customerId` nhưng index đặt khóa sort trước hoặc đặt một field không được equality filter nằm giữa các sort key, khiến khả năng tận dụng index thay đổi.

**Giải pháp:** Phân tích query shape và đo explain, theo hướng Equality–Sort–Range khi phù hợp.

### Lỗi 9 — Dùng collation không tương thích index

Index trên chuỗi với simple collation có thể không phục vụ hiệu quả một sort theo locale khác.

**Giải pháp:** Xác minh collation của query và index; đọc plan.

### Lỗi 10 — Nghĩ thứ tự ổn định là snapshot bất biến

**Vấn đề:** Có `_id` làm tie-breaker nhưng document vẫn được thêm/xóa/sửa giữa hai request.

**Giải pháp:** Phân biệt consistency requirement của sản phẩm với yêu cầu sort. Với export có tính chính xác cao, chọn cơ chế snapshot/đóng băng kết quả phù hợp.

---

## 13. Quy trình thiết kế cho một API danh sách

### Bước 1 — Xác định ý nghĩa của thứ tự

Ví dụ: “Đơn gần đây nhất” nghĩa là `createdAt DESC`; nếu trùng thì `_id DESC`.

### Bước 2 — Xác định tập filter

Ví dụ chỉ xem đơn của một khách và trạng thái cụ thể:

~~~javascript
{
  customerId: "C-01",
  status: "PAID"
}
~~~

### Bước 3 — Chọn tie-breaker

Chọn `_id` nếu duy nhất trong tập kết quả. Với aggregation tạo nhiều hàng mỗi document, chọn bộ khóa khác nếu cần.

### Bước 4 — Thiết kế index theo truy vấn thường dùng

Ví dụ:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent"
  }
);
~~~

### Bước 5 — Chọn cách phân trang

- Danh sách nhỏ, số trang hạn chế, dữ liệu ít biến động: `skip/limit` có thể đủ.
- Danh sách lớn, người dùng cuộn liên tục: keyset/cursor pagination.
- Cần tập dữ liệu chính xác tại thời điểm cố định: thiết kế consistency và export riêng, không chỉ dùng cursor.

### Bước 6 — Kiểm chứng

~~~javascript
db.orders
  .find({
    customerId: "C-01",
    status: "PAID"
  })
  .sort({
    createdAt: -1,
    _id: -1
  })
  .limit(20)
  .explain("executionStats");
~~~

Đánh giá cả plan, số key/document được duyệt, latency và tốc độ query khi dữ liệu tăng.

### Bước 7 — Kiểm thử các tình huống phá giả định

- Hai document trùng timestamp.
- Nhiều document trùng cả status, priority và timestamp.
- Mỗi trang kết thúc ngay giữa nhóm trùng timestamp.
- Field sort bị thiếu/null.
- `_id` có nhiều kiểu BSON (nếu schema hiện tại cho phép).
- Có insert/update/delete giữa hai request.
- Trang kế tiếp sau cursor của sort tăng, sort giảm và sort trộn.
- Filter/collation thay đổi giữa hai request.

Những trường hợp này kiểm tra hợp đồng API thực tế tốt hơn một dataset chỉ có timestamp khác nhau.

---

## 14. Bài tập thực hành

### Bài tập 1 — Sắp xếp theo ba trường

Dùng collection `orders` đã tạo ở phần 3. Hãy viết query:

1. Sort `priority` giảm.
2. Nếu priority trùng, sort `createdAt` giảm.
3. Nếu cả hai trùng, sort `_id` tăng.
4. Chỉ lấy đơn của `C-01` và trả `_id`, `priority`, `createdAt`.

Đối chiếu thứ tự `O-003`, `O-004`, `O-001`, `O-002` và giải thích tại sao khóa cuối quyết định vị trí của chúng.

### Bài tập 2 — Thay đổi thứ tự trường

So sánh:

~~~javascript
db.orders.find().sort({
  status: 1,
  createdAt: -1,
  _id: -1
});

db.orders.find().sort({
  createdAt: -1,
  status: 1,
  _id: -1
});
~~~

Giải thích cách mỗi truy vấn ưu tiên trường đầu tiên; đưa ví dụ hai document đổi vị trí giữa hai kết quả.

### Bài tập 3 — Tạo index phù hợp

Cho truy vấn:

~~~javascript
db.orders.find({
  customerId: "C-01",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(10);
~~~

Hãy:

1. Đề xuất compound index.
2. Giải thích vai trò equality của `customerId`, `status`.
3. Chạy explain trước và sau khi tạo index trên một bộ dữ liệu đủ lớn.
4. Kiểm tra có còn stage sort cần tài nguyên riêng hay không.
5. Thảo luận vì sao index phục vụ query này không mặc nhiên tối ưu cho query không lọc `status`.

### Bài tập 4 — Cursor trùng timestamp

Giả sử sort `{ createdAt: -1, _id: -1 }` và trang 1 kết thúc tại:

~~~javascript
{
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-002"
}
~~~

Viết filter cho trang sau để không bỏ sót document khác có cùng timestamp nhưng `_id` nhỏ hơn `"O-002"`.

### Bài tập 5 — Cursor chiều trộn

Sort:

~~~javascript
{ priority: -1, createdAt: 1, _id: 1 }
~~~

Cursor là:

~~~javascript
{
  priority: 2,
  createdAt: ISODate("2026-11-10T09:00:00Z"),
  _id: "O-001"
}
~~~

Viết điều kiện `$or` cho trang tiếp theo theo thứ tự từ điển, giải thích vì sao `priority` dùng `$lt` nhưng `createdAt` và `_id` dùng `$gt` ở nhánh tương ứng.

### Bài tập 6 — Dữ liệu thiếu và collation

Tạo collection `students` có một số document thiếu `lastName`, một số có `lastName: null`, và những chuỗi chỉ khác chữ hoa/thường. Thử sort theo `lastName ASC, _id ASC` với simple collation và `locale: "vi", strength: 2`. Ghi lại kết quả, giải thích vì sao nên chuẩn hóa field và khai báo đúng collation.

### Bài tập 7 — Dữ liệu thay đổi khi phân trang

Mô phỏng:

1. Lấy trang 1 theo `createdAt DESC, _id DESC`, page size 3.
2. Chèn một document mới đứng đầu danh sách.
3. Lấy trang 2 bằng `skip(3)`.
4. Lấy trang 2 bằng keyset cursor của trang 1.
5. So sánh các tình huống có thể gây lặp/sót.
6. Thử tiếp một update làm thay đổi `createdAt` của document đã đọc, thảo luận giới hạn của keyset.

Chỉ thực hiện trên database lab vì bài tập có thao tác ghi.

---

## 15. Câu hỏi ôn tập

1. Trong `sort({ a: 1, b: -1 })`, MongoDB ưu tiên trường nào?
2. Khi nào trường `b` ảnh hưởng đến vị trí kết quả?
3. Vì sao `sort({ createdAt: -1 })` chưa đủ để phân trang ổn định?
4. Một khóa tie-breaker cần tính chất gì?
5. Vì sao `_id` thường được chọn, và khi nào `_id` có thể chưa đủ?
6. Sort theo `_id` có luôn là sort theo thời gian tạo không?
7. Compound index cần tương thích với filter và sort ra sao?
8. Vì sao đổi riêng chiều một trường có thể khiến index không còn hỗ trợ sort hiệu quả?
9. Chỉ số `totalKeysExamined` và `totalDocsExamined` có ý nghĩa gì?
10. Vì sao `$sort` sau `$limit` khác với `$sort` trước `$limit`?
11. Offset pagination có giới hạn gì khi dữ liệu thay đổi?
12. Keyset pagination dùng điều kiện nào cho sort hai trường cùng chiều giảm?
13. Với một sort chiều trộn, dấu so sánh cursor thay đổi thế nào?
14. Null, field thiếu và kiểu BSON không đồng nhất ảnh hưởng sort ra sao?
15. Collation của index liên quan thế nào đến sort theo tiếng Việt?
16. Vì sao `$unwind` có thể khiến `_id` của document nguồn không còn là khóa duy nhất của các hàng kết quả?
17. Thứ tự xác định và snapshot consistency khác nhau ở điểm nào?

## 16. Tổng kết

Sắp xếp nhiều trường trong MongoDB là thao tác **so sánh lần lượt các khóa theo thứ tự được khai báo**. Trường đầu có ưu tiên cao nhất, các trường sau chỉ được xét khi những trường trước bằng nhau. Khi tập kết quả có thể chứa nhiều document trùng các khóa nghiệp vụ, thêm một **tie-breaker duy nhất** — thường là `_id` — để tạo thứ tự xác định.

Trong ứng dụng thực tế:

- **Xây sort có ý nghĩa nghiệp vụ:** ví dụ `createdAt DESC`.
- **Hoàn thiện bằng khóa phân xử:** ví dụ `_id DESC`.
- **Thiết kế index tương ứng:** xét cả equality filter, thứ tự và chiều sort.
- **Phân trang theo đúng thứ tự:** offset cho nhu cầu đơn giản, keyset/cursor khi dữ liệu lớn.
- **Phân biệt thứ tự với consistency:** khóa duy nhất không tự giữ nguyên tập dữ liệu khi có ghi đồng thời.
- **Kiểm chứng với dữ liệu có khóa trùng:** xem kế hoạch query, latency và hành vi phân trang.

Một thiết kế tốt phải để người dùng thấy kết quả đúng thứ tự, để API phân trang nhất quán về quy tắc và để database thực thi truy vấn hiệu quả trên dữ liệu đủ lớn.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — cursor.sort()](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/)
- [MongoDB Manual — $sort Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB Manual — Sort Results with Indexes](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — BSON Type Comparison Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Java Sync Driver — Sort Results](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/sort/)
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
