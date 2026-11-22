# Đếm chính xác, đếm ước lượng và lấy giá trị distinct trong MongoDB

Khi làm việc với collection MongoDB, ứng dụng thường cần biết **có bao nhiêu document**, **bao nhiêu document thỏa điều kiện** hoặc **một field đang có những giá trị khác nhau nào**. Ba nhu cầu nghe có vẻ giống nhau nhưng dẫn đến những thao tác khác nhau:

- **`countDocuments(filter)`** đếm chính xác số document thỏa điều kiện truy vấn.
- **`estimatedDocumentCount()`** ước lượng tổng số document của collection bằng thông tin thống kê/metadata, thường nhanh khi collection lớn.
- **`distinct(field, filter)`** trả về tập các **giá trị không trùng lặp** của một field trong các document thỏa điều kiện, không trả về số document.

MongoDB còn có các công cụ aggregation như **`$count`**, **`$group`**, **`$sortByCount`** và **`$unwind`** để tính thống kê phức tạp hơn. Hiểu rõ phạm vi, độ chính xác và kiểu kết quả của từng thao tác giúp tránh những sai sót trong phân trang, dashboard và thống kê nghiệp vụ.

## 1. Cùng một collection nhưng có ba câu hỏi khác nhau

Giả sử ứng dụng bán hàng lưu đơn hàng trong collection **`shop.orders`**.

| Câu hỏi nghiệp vụ | Thao tác phù hợp | Kết quả kỳ vọng |
| --- | --- | --- |
| Có bao nhiêu đơn hàng trạng thái PAID? | `countDocuments({ status: "PAID" })` | Một số nguyên chính xác theo phạm vi truy vấn |
| Collection orders có khoảng bao nhiêu document? | `estimatedDocumentCount()` | Một số đếm dựa trên metadata, có thể không tuyệt đối chính xác |
| Những trạng thái đơn hàng nào đang tồn tại? | `distinct("status")` | Danh sách các giá trị trạng thái khác nhau |
| Có bao nhiêu trạng thái khác nhau? | `distinct("status").length` hoặc aggregation | Số lượng giá trị phân biệt, không phải tổng document |
| Mỗi trạng thái có bao nhiêu đơn? | `$group` hoặc `$sortByCount` | Nhiều cặp trạng thái–số lượng |

Ví dụ sơ đồ:

~~~text
Collection orders (10 documents)
│
├── countDocuments({ status: "PAID" })
│     └── 5 document
│
├── estimatedDocumentCount()
│     └── xấp xỉ 10 document theo metadata
│
└── distinct("status")
      └── ["PAID", "PENDING", "CANCELLED"]
           (thứ tự không được bảo đảm)
~~~

**Đếm document** khác với **đếm số giá trị phân biệt**. Một trạng thái có thể xuất hiện trong hàng triệu document nhưng chỉ đóng góp một phần tử vào kết quả distinct.

## 2. Chuẩn bị dữ liệu thử nghiệm trong mongosh

Dùng database thử nghiệm riêng **`mongo_query_count_lab`**. Các ví dụ trong bài giả định collection ban đầu chưa chứa dữ liệu; `drop()` xóa toàn bộ collection, vì vậy chỉ chạy lệnh này trong môi trường thử nghiệm.

~~~javascript
use mongo_query_count_lab

db.orders.drop();

db.orders.insertMany([
  {
    _id: "O-1001",
    customerId: "C-01",
    status: "PAID",
    channel: "WEB",
    shipping: { city: "HCM" },
    tags: ["new", "priority"],
    amount: 250000
  },
  {
    _id: "O-1002",
    customerId: "C-02",
    status: "PAID",
    channel: "APP",
    shipping: { city: "HCM" },
    tags: ["new"],
    amount: 120000
  },
  {
    _id: "O-1003",
    customerId: "C-03",
    status: "PENDING",
    channel: "WEB",
    shipping: { city: "HN" },
    tags: ["gift", "priority"],
    amount: 500000
  },
  {
    _id: "O-1004",
    customerId: "C-04",
    status: "CANCELLED",
    channel: "APP",
    shipping: { city: "DN" },
    tags: [],
    amount: 200000
  },
  {
    _id: "O-1005",
    customerId: "C-01",
    status: "PAID",
    channel: "WEB",
    shipping: { city: "HN" },
    tags: ["gift"],
    amount: 800000
  },
  {
    _id: "O-1006",
    customerId: "C-05",
    status: "PENDING",
    channel: "APP",
    shipping: { city: "HCM" },
    tags: ["new", "gift"],
    amount: 650000
  },
  {
    _id: "O-1007",
    customerId: "C-06",
    status: "PAID",
    channel: "WEB",
    shipping: { city: "DN" },
    tags: ["priority"],
    amount: 300000
  },
  {
    _id: "O-1008",
    customerId: "C-07",
    status: "CANCELLED",
    channel: "WEB",
    shipping: { city: "HCM" },
    tags: [],
    amount: 100000
  },
  {
    _id: "O-1009",
    customerId: "C-02",
    status: "PAID",
    channel: "APP",
    shipping: { city: "HCM" },
    tags: ["new"],
    amount: 380000
  },
  {
    _id: "O-1010",
    customerId: "C-08",
    status: "PENDING",
    channel: "WEB",
    shipping: { city: "HN" },
    tags: ["gift"],
    amount: 220000
  }
]);
~~~

Dữ liệu có phân bố như sau:

| Trạng thái | Số đơn |
| --- | ---: |
| PAID | 5 |
| PENDING | 3 |
| CANCELLED | 2 |
| **Tổng** | **10** |

Có 6 đơn từ kênh **WEB**, 4 đơn từ **APP**; ba giá trị thành phố là **HCM**, **HN** và **DN**. Các giá trị tag phân biệt là **new**, **priority** và **gift**.

Tất cả ví dụ kết quả số học sau đây giả định **không có write đồng thời** và tập dữ liệu không bị thay đổi giữa các lệnh.

## 3. `countDocuments()`: đếm chính xác những document phù hợp

Cú pháp mongosh:

~~~javascript
db.collection.countDocuments(query, options)
~~~

Trong đó:

- **query** là document điều kiện lọc, tương tự điều kiện của `find()`.
- **options** có thể chỉ định các tùy chọn như `limit`, `skip`, `hint`, `maxTimeMS`.
- Kết quả là **một số** biểu thị số document được đếm theo điều kiện và các tùy chọn.

### 3.1. Đếm toàn bộ collection

~~~javascript
db.orders.countDocuments({});
// 10
~~~

Điều kiện rỗng **`{}`** nghĩa là không lọc theo field nghiệp vụ nào. Với dữ liệu đang có 10 document, kết quả là **10**.

Đây là thao tác đếm chính xác dựa trên nội dung tập document được truy vấn, không dựa riêng vào thống kê số lượng của collection.

### 3.2. Đếm theo một điều kiện

~~~javascript
db.orders.countDocuments({ status: "PAID" });
// 5

db.orders.countDocuments({ status: "PENDING" });
// 3

db.orders.countDocuments({ channel: "WEB" });
// 6
~~~

Điều kiện được đánh giá theo cú pháp truy vấn MongoDB thông thường.

### 3.3. Kết hợp nhiều điều kiện

~~~javascript
// Đơn PAID từ kênh WEB.
db.orders.countDocuments({
  status: "PAID",
  channel: "WEB"
});
// 3
~~~

Hai field cùng xuất hiện trong một filter ở cấp cao nhất được kết hợp như điều kiện **AND**.

Có thể sử dụng toán tử:

~~~javascript
// Số đơn có giá trị amount từ 300000 trở lên.
db.orders.countDocuments({
  amount: { $gte: 300000 }
});
// 5

// Các đơn thuộc hai trạng thái PAID hoặc PENDING.
db.orders.countDocuments({
  status: { $in: ["PAID", "PENDING"] }
});
// 8

// Đơn giao đến HCM.
db.orders.countDocuments({
  "shipping.city": "HCM"
});
// 5
~~~

**`shipping.city`** sử dụng **dot notation** để truy cập field bên trong embedded document. Nó không phải tên collection hay namespace.

### 3.4. Đếm trên field dạng array

~~~javascript
// Document có ít nhất một phần tử tags bằng "priority".
db.orders.countDocuments({
  tags: "priority"
});
// 3
~~~

Ba document phù hợp là **O-1001**, **O-1003** và **O-1007**. Mỗi document chỉ được tính **một lần**, ngay cả khi một field array có nhiều phần tử liên quan đến điều kiện. `countDocuments()` đếm **document**, không đếm số lần giá trị xuất hiện trong array.

### 3.5. Đếm theo khoảng thời gian

Giả sử ứng dụng có field **createdAt** kiểu BSON Date:

~~~javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end = ISODate("2026-12-01T00:00:00Z");

db.orders.countDocuments({
  createdAt: {
    $gte: start,
    $lt: end
  }
});
~~~

Khoảng **`[start, end)`** bao gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc. Đây là cách hữu ích để tính thống kê theo ngày/tháng mà tránh đếm trùng ở ranh giới. Ví dụ này minh họa cú pháp; bộ dữ liệu thử nghiệm bên trên **chưa có field createdAt**, nên kết quả của chính dữ liệu mẫu sẽ là 0.

Nếu thống kê theo múi giờ địa phương, cần quy đổi ranh giới ngày sang UTC đúng cách trước khi lọc.

## 4. `countDocuments()` hoạt động ra sao?

MongoDB không đơn thuần lấy số đếm trong metadata để trả lời `countDocuments()`. Về mặt logic, thao tác tương đương với một aggregation lọc document rồi cộng số lượng:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: null,
      n: { $sum: 1 }
    }
  }
]);
// [ { _id: null, n: 5 } ]
~~~

Trong đó:

1. **`$match`** chọn document phù hợp filter.
2. **`$group`** gom toàn bộ document đã chọn vào một nhóm chung.
3. **`$sum: 1`** tăng số đếm một đơn vị cho mỗi document.

Bản thân `countDocuments()` trả về **số 5**, thay vì một document có field `n`.

### 4.1. Ý nghĩa của từ “chính xác”

Chính xác ở đây nghĩa là số đếm được tính từ tập document thực tế thỏa filter, với read concern, thời điểm đọc và điều kiện triển khai đang áp dụng. Nó không phải một lời hứa rằng số này **không bao giờ thay đổi**.

Ví dụ:

~~~javascript
const total = db.orders.countDocuments({ status: "PAID" });

// Một client khác có thể insert/delete/update đơn PAID ngay sau dòng trên.

const page = db.orders.find({ status: "PAID" })
                      .sort({ _id: 1 })
                      .limit(20)
                      .toArray();
~~~

Nếu có write giữa hai lệnh, số `total` và tập dữ liệu `page` có thể phản ánh **hai thời điểm khác nhau**. Việc cần một ảnh chụp nhất quán qua nhiều thao tác đọc là bài toán riêng liên quan tới read concern, snapshot và transaction phù hợp.

Ngoài ra, nếu đọc từ secondary và có replication lag, số đếm có thể chưa phản ánh những write vừa được ghi trên primary. Phải diễn giải kết quả theo cách hệ thống đang đọc dữ liệu.

### 4.2. Chính xác trong sharded cluster

Trong sharded cluster, có thể còn tồn tại **orphaned document** phát sinh từ quá trình dịch chuyển dữ liệu. `countDocuments()` được thiết kế để cho số đếm chính xác, kể cả khi có các document dạng này; vì vậy nó phù hợp hơn với các phép đếm nghiệp vụ yêu cầu độ chính xác so với cách đếm chỉ dựa trên metadata.

Khả năng chính xác không loại bỏ chi phí phải truy vấn các shard liên quan. Nếu filter thiếu shard key hoặc không đủ để xác định shard đích, yêu cầu có thể cần nhiều shard tham gia.

### 4.3. Tùy chọn `skip` và `limit`

~~~javascript
db.orders.countDocuments(
  { status: "PAID" },
  { skip: 2, limit: 2 }
);
// 2
~~~

Có 5 đơn PAID. Bỏ qua 2 document và giới hạn số document đếm còn 2 thì kết quả trả về là **2**. Kết quả đó **không còn là tổng số document PAID**.

Trong một API phân trang, để lấy tổng số bản ghi của filter, thường gọi:

~~~javascript
const filter = { status: "PAID" };

const total = db.orders.countDocuments(filter);

const page = db.orders.find(filter)
                      .sort({ _id: 1 })
                      .skip(0)
                      .limit(2)
                      .toArray();
~~~

Ở đây **total = 5**, còn **page.length = 2**. Không nên truyền `skip` và `limit` của trang vào phép đếm tổng nếu mục tiêu là tổng số bản ghi phù hợp.

## 5. `estimatedDocumentCount()`: ước lượng tổng số document

Cú pháp:

~~~javascript
db.collection.estimatedDocumentCount(options)
~~~

Ví dụ:

~~~javascript
db.orders.estimatedDocumentCount();
// Thường xấp xỉ 10 trên dữ liệu mẫu; giá trị dựa trên metadata.
~~~

Khác biệt quan trọng: **`estimatedDocumentCount()` không nhận query filter**. Nó trả về số lượng ước lượng cho **toàn bộ collection**.

Không dùng:

~~~javascript
// SAI MỤC ĐÍCH: estimatedDocumentCount không có tham số filter.
db.orders.estimatedDocumentCount({ status: "PAID" });
~~~

Đối số này không có ý nghĩa là điều kiện lọc. Muốn đếm riêng đơn PAID, phải dùng `countDocuments({ status: "PAID" })`.

### 5.1. Vì sao thường nhanh?

`estimatedDocumentCount()` dựa vào **collection metadata**, nên trong trường hợp collection thông thường không phải quét các document chỉ để tính tổng.

Điều này hữu ích cho:

- Dashboard tổng quan không yêu cầu tuyệt đối chính xác ở mọi thời điểm.
- Hiển thị quy mô dữ liệu, chẳng hạn “khoảng vài triệu bản ghi”.
- Thống kê vận hành hoặc quản trị cần ước lượng nhanh.
- Các phép kiểm tra sơ bộ khi collection lớn, nếu độ lệch có thể chấp nhận được.

Không nên hiểu tên “estimated” là một thuật toán lấy mẫu ngẫu nhiên theo tỷ lệ, cũng không có nghĩa giá trị luôn lệch. Trên collection nhỏ và trạng thái metadata bình thường, nó có thể trả số đúng; khác biệt nằm ở **cơ chế tạo số đếm và mức bảo đảm**.

### 5.2. Khi nào kết quả có thể không chính xác?

Các tình huống cần lưu ý:

- **Sharded cluster:** metadata count có thể bao gồm **orphaned document** và không loại bỏ chính xác những document này.
- **Unclean shutdown:** sau khi một `mongod` dừng không sạch, thống kê số lượng collection có thể không được cập nhật đầy đủ so với dữ liệu thực.
- **View:** view không có sẵn số đếm metadata giống collection. Đối với view, MongoDB phải xử lý pipeline định nghĩa view; không có lợi thế “đếm nhanh từ metadata” tương tự.

Ví dụ, khi tổng số đơn hàng tác động trực tiếp đến đối soát tài chính, thanh toán hoặc một giới hạn nghiệp vụ, **không nên dùng số ước lượng như số liệu quyết định**.

### 5.3. Các tùy chọn

Có thể giới hạn thời gian xử lý:

~~~javascript
db.orders.estimatedDocumentCount({
  maxTimeMS: 2000
});
~~~

`maxTimeMS` là giới hạn thời gian yêu cầu thực thi phía server, **không phải số lượng document tối đa**. Tùy chọn này không biến thao tác ước lượng thành đếm chính xác.

## 6. So sánh trực diện hai cách đếm

| Tiêu chí | `countDocuments()` | `estimatedDocumentCount()` |
| --- | --- | --- |
| Mục đích | Đếm chính xác số document phù hợp | Ước lượng tổng document collection |
| Filter theo field | **Có** | **Không** |
| Dùng collection metadata làm số đếm | Không | Có, với collection thông thường |
| Chi phí trên tập lớn | Tùy filter, index và lượng dữ liệu cần xử lý | Thường nhỏ hơn do dùng metadata |
| Phù hợp thống kê nghiệp vụ chính xác | Có | Không nên dùng khi bắt buộc chính xác |
| Sharded orphaned documents | Có cơ chế tính đếm chính xác | Có thể bị tính dư |
| Sau unclean shutdown | Không dựa vào thống kê đếm có thể lệch | Có khả năng lệch |
| Đếm document trong view | Có | Có thể, nhưng không có lợi ích đếm nhanh từ metadata |
| Kết quả | Một số | Một số |

Quy tắc lựa chọn:

~~~text
Cần đếm theo điều kiện?
    ├── CÓ  ──> countDocuments(filter)
    └── KHÔNG
         ├── Cần số chính xác? ──> countDocuments({})
         └── Chấp nhận ước lượng nhanh? ──> estimatedDocumentCount()
~~~

Nếu hệ thống hiển thị một con số có ảnh hưởng lớn đến người dùng, chẳng hạn số đơn có thể hoàn tiền, hãy xác định rõ độ chính xác cần thiết trước khi chọn phương thức.

## 7. `distinct()`: lấy những giá trị không trùng lặp

Cú pháp mongosh:

~~~javascript
db.collection.distinct(field, query, options)
~~~

Trong đó:

- **field**: tên field hoặc dot path cần lấy giá trị phân biệt, viết dưới dạng string.
- **query**: điều kiện lọc document tùy chọn.
- **options**: một số tùy chọn truy vấn, chẳng hạn `collation`.
- Kết quả: một **array các giá trị BSON phân biệt**, không phải cursor document như `find()`.

### 7.1. Lấy các trạng thái đang tồn tại

~~~javascript
db.orders.distinct("status");
// Ví dụ: ["PAID", "PENDING", "CANCELLED"]
~~~

Collection có 10 document nhưng chỉ có **3 trạng thái** khác nhau. Thứ tự phần tử trả về **không được bảo đảm**; nếu cần trình bày theo alphabet hoặc thứ tự nghiệp vụ, ứng dụng phải sắp xếp rõ ràng.

### 7.2. Distinct có filter

~~~javascript
db.orders.distinct(
  "status",
  { channel: "WEB" }
);
// Các trạng thái thuộc đơn hàng từ WEB: PAID, PENDING, CANCELLED.
~~~

`query` được áp dụng để chọn **document đầu vào** trước khi lấy giá trị phân biệt.

Một ví dụ khác:

~~~javascript
db.orders.distinct(
  "channel",
  { status: "PAID" }
);
// ["WEB", "APP"], thứ tự bất kỳ.
~~~

Năm đơn PAID xuất hiện trên cả hai kênh, nhưng distinct chỉ trả về **một giá trị WEB và một giá trị APP**.

### 7.3. Distinct trên field lồng nhau

~~~javascript
db.orders.distinct("shipping.city");
// Có 3 giá trị: "HCM", "HN", "DN".
~~~

Đường dẫn **`shipping.city`** truy cập field `city` trong embedded document `shipping`.

Có thể kết hợp filter:

~~~javascript
db.orders.distinct(
  "shipping.city",
  { status: "PAID" }
);
// Các giá trị: "HCM", "HN", "DN".
~~~

### 7.4. Distinct trên array

~~~javascript
db.orders.distinct("tags");
// Các giá trị: "new", "priority", "gift".
~~~

Khi field chỉ định chứa **array**, `distinct()` xem **từng phần tử** của array là một giá trị cần xét. Nó không coi nguyên array `["new", "priority"]` là một nhãn duy nhất trong ví dụ này.

Vì vậy:

~~~javascript
db.orders.countDocuments({ tags: "priority" });
// 3 document

db.orders.distinct("tags").length;
// 3 giá trị tag phân biệt trong toàn collection
~~~

Hai kết quả tình cờ cùng là số **3**, nhưng chúng trả lời hai câu hỏi khác nhau. Trong dữ liệu khác, hai số không cần bằng nhau.

### 7.5. Không dùng distinct để lấy document đầy đủ

`distinct("status")` chỉ trả về các giá trị của field `status`, không trả về đơn hàng tương ứng với từng trạng thái. Nếu cần document đầy đủ, dùng `find()`; nếu cần nhóm document và thống kê theo giá trị field, dùng `aggregate()`.

## 8. Giá trị thiếu, null, kiểu dữ liệu và collation

### 8.1. Field thiếu khác field mang giá trị null

Xét collection thử nghiệm khác:

~~~javascript
use mongo_query_count_lab

db.profiles.drop();

db.profiles.insertMany([
  { _id: 1, displayName: "An", region: "NORTH" },
  { _id: 2, displayName: "Bình", region: null },
  { _id: 3, displayName: "Chi" },
  { _id: 4, displayName: "Dung", region: "SOUTH" }
]);
~~~

Có thể đếm:

~~~javascript
// Bao gồm cả document có region: null và không có field region.
db.profiles.countDocuments({ region: null });
// 2

// Field region tồn tại, kể cả khi giá trị là null.
db.profiles.countDocuments({
  region: { $exists: true }
});
// 3

// Field region không tồn tại.
db.profiles.countDocuments({
  region: { $exists: false }
});
// 1

// Chỉ field region có BSON type Null.
db.profiles.countDocuments({
  region: { $type: "null" }
});
// 1
~~~

Với `distinct("region")`, MongoDB thu thập **các giá trị của field tồn tại**; giá trị `null` được lưu rõ ràng là một giá trị, còn document thiếu field không tạo thêm một giá trị region.

~~~javascript
db.profiles.distinct("region");
// Có các giá trị: "NORTH", null, "SOUTH".
~~~

Nếu mục đích là đếm “các khu vực thực sự được khai báo” và không muốn tính `null`, có thể lọc:

~~~javascript
db.profiles.distinct(
  "region",
  { region: { $ne: null } }
);
// "NORTH", "SOUTH"
~~~

### 8.2. Chuỗi khác nhau do chữ hoa/chữ thường

Trong chế độ so sánh nhị phân mặc định thông thường, những string như **`"paid"`**, **`"PAID"`** và **`"Paid"`** có thể được xem là các giá trị khác nhau. Khi muốn distinct theo quy tắc ngôn ngữ hoặc bỏ phân biệt hoa thường, dùng **collation** phù hợp.

Ví dụ:

~~~javascript
db.profiles.distinct(
  "displayName",
  {},
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

`strength: 2` thường so sánh không phân biệt chữ hoa/chữ thường nhưng vẫn xét dấu/diacritics theo quy tắc collation. Giá trị `locale`, `strength` và collation của index có thể ảnh hưởng kết quả lẫn khả năng dùng index.

Không nên chỉ gọi `toLowerCase()` trên mọi thứ ở client rồi cho rằng đã tương đương với collation database. Trường hợp có ngôn ngữ, dấu và cách chuẩn hóa Unicode cần được xác định thành quy tắc nghiệp vụ.

### 8.3. Giá trị cùng nghĩa nhưng khác BSON type

Ví dụ field `customerCode` được lưu ở nơi là số, nơi là chuỗi:

~~~javascript
{ customerCode: 101 }
{ customerCode: "101" }
~~~

MongoDB có thể coi đây là **hai giá trị khác kiểu**, dù trên giao diện đều hiển thị gần giống nhau.

Tương tự, chuỗi UUID và BSON Binary UUID không tự hợp nhất thành một giá trị distinct. Để có thống kê đáng tin cậy, nên chuẩn hóa schema và BSON type ngay ở điểm ghi dữ liệu.

## 9. Khi distinct chưa đủ: dùng aggregation

`distinct()` phù hợp khi chỉ cần danh sách giá trị phân biệt có kích thước vừa phải. Nếu cần cả **số document trên mỗi giá trị**, **sắp xếp**, **phân trang giá trị nhóm** hoặc **thống kê kết hợp**, aggregation linh hoạt hơn.

### 9.1. Đếm document bằng `$count`

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "totalPaid" }
]);
// [ { totalPaid: 5 } ]
~~~

`$count` là một **aggregation stage** và trả về document có field do bạn đặt tên. Khác với `countDocuments()`, kết quả là từ một aggregation cursor.

Một điểm cần nhớ: nếu pipeline không có document đầu vào, **`$count` không phát ra document kết quả**.

~~~javascript
db.orders.aggregate([
  { $match: { status: "UNKNOWN" } },
  { $count: "total" }
]);
// []
~~~

Trong khi đó:

~~~javascript
db.orders.countDocuments({ status: "UNKNOWN" });
// 0
~~~

Ứng dụng phải xử lý trường hợp cursor aggregation rỗng khi dùng `$count`.

### 9.2. `$group`: đếm theo từng trạng thái

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả sau khi sắp theo tên trạng thái:

~~~javascript
[
  { _id: "CANCELLED", total: 2 },
  { _id: "PAID", total: 5 },
  { _id: "PENDING", total: 3 }
]
~~~

Mỗi giá trị trạng thái khác nhau tạo ra một nhóm; `total` là số document trong nhóm.

Nếu chỉ cần đếm số **loại trạng thái** khác nhau:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status" } },
  { $count: "distinctStatusCount" }
]);
// [ { distinctStatusCount: 3 } ]
~~~

Phương án này thường hữu ích khi số lượng nhóm lớn và không muốn trả toàn bộ giá trị về client chỉ để gọi `.length`.

### 9.3. `$sortByCount`: bảng tần suất ngắn gọn

~~~javascript
db.orders.aggregate([
  { $sortByCount: "$status" }
]);
~~~

Stage `$sortByCount` nhóm theo giá trị biểu thức, tính số document trong từng nhóm và sắp theo số lượng giảm dần. Kết quả của bộ dữ liệu mẫu:

~~~javascript
[
  { _id: "PAID", count: 5 },
  { _id: "PENDING", count: 3 },
  { _id: "CANCELLED", count: 2 }
]
~~~

Khi tần suất bằng nhau, thứ tự giữa các nhóm bằng nhau không được bảo đảm nếu không có sort bổ sung.

### 9.4. `$unwind` cho field array

Để có số lần mỗi tag xuất hiện trong document, cần tách array thành các dòng đầu vào:

~~~javascript
db.orders.aggregate([
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tags",
      totalOccurrences: { $sum: 1 }
    }
  },
  { $sort: { totalOccurrences: -1, _id: 1 } }
]);
~~~

Trong tập dữ liệu mẫu:

- `new` xuất hiện trong 4 document.
- `gift` xuất hiện trong 4 document.
- `priority` xuất hiện trong 3 document.

`$unwind` loại bỏ document có array rỗng ở cấu hình mặc định. Nếu một document có hai phần tử **giống nhau** trong `tags`, pipeline trên tính hai lần vì nó đếm số **phần tử được unwind**, không mặc định là số **document phân biệt** chứa tag.

Nếu nghiệp vụ muốn “mỗi tag được tính tối đa một lần cho mỗi order”, cần chuẩn hóa array không trùng lặp hoặc thêm bước loại trùng theo cặp **order ID + tag** trước khi tính tần suất.

### 9.5. Khác biệt của `$group` trên array khi không unwind

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$tags" } }
]);
~~~

Pipeline này nhóm theo **giá trị của toàn array** (chẳng hạn `["new", "priority"]`), không hoạt động giống `distinct("tags")` trả những phần tử riêng lẻ. Muốn mô phỏng lấy các tag riêng lẻ bằng aggregation, dùng:

~~~javascript
db.orders.aggregate([
  { $unwind: "$tags" },
  { $group: { _id: "$tags" } },
  { $sort: { _id: 1 } }
]);
~~~

Các phép biến đổi này cho thấy cùng một field array có thể được xem là **một giá trị nguyên khối** hoặc **một tập các phần tử**, tùy thao tác.

## 10. Hiệu năng: index, scan và dữ liệu lớn

### 10.1. `countDocuments({})` trên collection lớn

Một `countDocuments({})` không có filter có thể cần **full collection scan**, làm chi phí tăng cùng quy mô collection.

MongoDB khuyến nghị có thể sử dụng index `_id_` để tránh quét toàn bộ document khi đếm toàn collection:

~~~javascript
db.orders.countDocuments(
  {},
  { hint: "_id_" }
);
~~~

Index `_id_` là index mặc định trên field `_id` của collection thông thường. `hint` buộc query planner xét index được chỉ định; nó chỉ phù hợp nếu index tồn tại và phục vụ phép đếm.

Đừng áp dụng `hint: "_id_"` mù quáng cho mọi filter. Khi đếm theo field khác, index đúng field điều kiện thường hữu ích hơn.

### 10.2. Index cho count có filter

Giả sử API thường đếm đơn theo **status** và **channel**:

~~~javascript
db.orders.createIndex({
  status: 1,
  channel: 1
});
~~~

Có thể đếm:

~~~javascript
db.orders.countDocuments({
  status: "PAID",
  channel: "WEB"
});
~~~

MongoDB có thể dùng index để khoanh vùng document cần xét. Hiệu quả thực tế phụ thuộc độ chọn lọc, thứ tự field trong index, cấu trúc filter, dung lượng dữ liệu và query plan.

Một index không phải bảo đảm tốc độ trong mọi tình huống. Index cũng tiêu tốn dung lượng lưu trữ và chi phí cập nhật khi insert/update/delete.

### 10.3. Index cho distinct

Nếu thường xuyên lấy distinct của `status`:

~~~javascript
db.orders.createIndex({ status: 1 });

db.orders.distinct("status");
~~~

Trong một số trường hợp, MongoDB có thể dùng **DISTINCT_SCAN** hoặc index scan để tìm giá trị khác nhau hiệu quả hơn. Có thể kiểm tra kế hoạch thực thi bằng công cụ explain phù hợp.

Không phải mọi `distinct()` đều dùng index. Query có filter, collation khác index, field array hoặc kiểu collection đặc biệt có thể khiến query plan khác dự kiến.

### 10.4. Shard key và phân tán yêu cầu

Trong sharded cluster, một phép đếm có filter đủ cụ thể trên shard key có thể được định tuyến đến một hoặc một số shard; phép đếm tổng hoặc filter không xác định shard có thể cần tổng hợp kết quả từ nhiều shard.

Ví dụ giả sử `orders` được sharding theo `customerId`:

~~~javascript
// Có cơ hội định tuyến hẹp theo shard key.
db.orders.countDocuments({ customerId: "C-01" });

// Không có customerId: có thể cần hỏi nhiều shard.
db.orders.countDocuments({ status: "PAID" });
~~~

Điều này là hệ quả của thiết kế phân vùng dữ liệu, không phải dấu hiệu `countDocuments()` sai.

### 10.5. Dùng explain để hiểu chi phí

Có thể xem execution plan của truy vấn tương đương bằng aggregation:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
~~~

Cần quan sát các thành phần như **IXSCAN**, **COLLSCAN**, số key/document được đọc và thời gian thực thi trong hoàn cảnh có dữ liệu đủ lớn. Một collection chỉ có 10 document không đại diện cho hiệu năng production.

## 11. Giới hạn và điểm cần thận trọng với `distinct()`

### 11.1. Kết quả rất lớn

`distinct()` trả về một tập giá trị được gom trong phản hồi lệnh. Nếu field có số lượng giá trị phân biệt cực lớn, kết quả có thể chạm **giới hạn BSON document 16 MiB** và thao tác thất bại.

Ví dụ lấy distinct của field `eventId` nếu mỗi document có một eventId khác nhau, tức số lượng giá trị gần bằng số document. Lúc này `distinct()` không còn là cách thích hợp để hiển thị hàng triệu ID.

Có thể sử dụng aggregation trả **một document trên mỗi nhóm** và đọc bằng cursor:

~~~javascript
db.events.aggregate([
  { $match: { status: "ACTIVE" } },
  { $group: { _id: "$eventId" } },
  { $sort: { _id: 1 } }
]);
~~~

Cách này giúp tránh việc gói tất cả distinct values vào **một array kết quả duy nhất**. Tuy nhiên, `$group` vẫn có chi phí RAM, đĩa hoặc giới hạn tài nguyên riêng; không phải lựa chọn miễn phí với tập lớn.

Đặc biệt, dùng `$addToSet` để gom **tất cả ID vào một array trong một document** có thể vẫn đụng giới hạn kích thước. Nếu cần xuất danh sách giá trị lớn, hãy ưu tiên xử lý bằng cursor và từng nhóm thay vì một array khổng lồ.

### 11.2. `distinct` trong sharded cluster

Lệnh `distinct` trong một số bối cảnh sharded cluster có thể thu thập giá trị từ **orphaned documents**, dẫn đến kết quả chứa giá trị không còn đại diện cho dữ liệu đang được sở hữu hợp lệ theo phân vùng.

Nếu cần suy ra tập giá trị nghiệp vụ chính xác trong sharded cluster, phải cân nhắc đặc tính này, kế hoạch query và việc dùng aggregation `$group` khi phù hợp.

### 11.3. `distinct` trong transaction

Theo quy tắc transaction của MongoDB:

- Với **unsharded collection**, `distinct()` có thể được dùng trong transaction.
- Với **sharded collection**, không dùng `distinct()`/lệnh `distinct` trong transaction; MongoDB hướng dẫn dùng aggregation pipeline với `$group` thay thế.

Ví dụ dành cho field đơn giá trị:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$channel" } }
]);
~~~

Nếu field là array, cân nhắc `$unwind` trước `$group` để đạt semantics giống distinct trên phần tử array.

### 11.4. Thứ tự kết quả và hiển thị

Kết quả `distinct()` **không có hợp đồng sắp xếp**. API trả danh mục giá trị cần chủ động áp dụng thứ tự:

~~~javascript
const channels = db.orders.distinct("channel");
channels.sort();
~~~

Lệnh `.sort()` trên array JavaScript trong ví dụ sử dụng cách so sánh string mặc định. Khi có số, ngày, ký tự có dấu hoặc thứ tự nghiệp vụ, cần dùng comparator/collation phù hợp.

Không nên dùng thứ tự phần tử của distinct làm căn cứ tạo “trang 1”, “trang 2” mà không có chiến lược sắp xếp/phân trang ổn định.

## 12. Những lỗi thường gặp khi dùng count và distinct

| Cách hiểu sai | Vì sao sai hoặc chưa đủ |
| --- | --- |
| `estimatedDocumentCount({ status: "PAID" })` đếm số đơn PAID | `estimatedDocumentCount` không nhận filter |
| `countDocuments({})` và `estimatedDocumentCount()` luôn bằng nhau | Phương pháp và bảo đảm khác nhau; metadata có thể lệch |
| `distinct("status")` trả số lượng document theo status | Nó trả **các giá trị phân biệt**; muốn tần suất dùng `$group` |
| `distinct("tags")` trả nguyên từng array tags | Với field array, distinct xét các phần tử |
| `countDocuments({ tags: "gift" })` đếm số tag gift | Nó đếm document thỏa điều kiện, mỗi document một lần |
| Đếm tổng bằng `countDocuments(filter, { skip, limit })` trong phân trang | `skip`/`limit` làm thay đổi số được đếm |
| `$count` luôn trả document có số 0 | Input rỗng khiến pipeline có thể trả cursor rỗng |
| Đếm chính xác nghĩa là kết quả không đổi giữa hai lệnh | Write đồng thời hoặc replica lag có thể làm số đếm thay đổi |
| Thêm index bảo đảm mọi count chạy tức thì | Còn phụ thuộc filter, độ chọn lọc, kế hoạch thực thi và shard |
| MongoDB tự gộp các giá trị `"PAID"` và `"paid"` | Phụ thuộc collation và cách lưu dữ liệu |
| `distinct` không bao giờ gặp giới hạn kích thước | Kết quả phân biệt lớn có thể vượt giới hạn phản hồi BSON |
| `$group: { _id: "$tags" }` giống `distinct("tags")` | Với array, `$group` nhóm cả array nếu không `$unwind` |
| Dùng estimated count cho đối soát tài chính là đủ | Nghiệp vụ đòi hỏi số chính xác cần đếm/kiểm soát thích hợp |

Một lỗi tinh vi khác là dùng `find(filter).limit(20).toArray().length` làm tổng số kết quả tìm kiếm. Con số đó chỉ cho biết **bao nhiêu document được lấy trong trang đang tải**, tối đa bằng 20; nó không bằng tổng tài liệu thỏa filter khi có nhiều trang.

## 13. Ứng dụng thực tế: phân trang và dashboard

### 13.1. Phân trang kết quả tìm kiếm

Ví dụ API hiển thị trang danh sách đơn PAID, mỗi trang 3 đơn:

~~~javascript
const filter = { status: "PAID" };
const pageNumber = 1;
const pageSize = 3;

const totalItems = db.orders.countDocuments(filter);

const items = db.orders
  .find(filter)
  .sort({ _id: 1 })
  .skip((pageNumber - 1) * pageSize)
  .limit(pageSize)
  .toArray();

const totalPages = Math.ceil(totalItems / pageSize);

printjson({
  totalItems,
  pageNumber,
  pageSize,
  totalPages,
  items
});
~~~

Với dữ liệu mẫu cố định:

~~~text
totalItems = 5
pageSize   = 3
totalPages = 2
items      = 3 document ở trang đầu
~~~

Khi dữ liệu lớn, **skip sâu** có thể tốn chi phí; pagination dựa trên key/cursor thường phù hợp hơn để duyệt nhiều trang. Đồng thời, total count và items là hai lần đọc; nếu cần tính nhất quán mạnh giữa chúng, phải thiết kế cơ chế đọc tương ứng.

### 13.2. Dashboard tổng quan

Một dashboard có thể cần:

- Tổng số document trong collection để ước lượng quy mô.
- Tổng đơn PAID chính xác để theo dõi nghiệp vụ.
- Danh sách trạng thái dùng làm bộ lọc.
- Số lượng đơn theo từng trạng thái.

Ví dụ:

~~~javascript
const approximateAllOrders =
  db.orders.estimatedDocumentCount();

const exactPaidOrders =
  db.orders.countDocuments({ status: "PAID" });

const availableStatuses =
  db.orders.distinct("status");

const ordersByStatus =
  db.orders.aggregate([
    { $sortByCount: "$status" }
  ]).toArray();

printjson({
  approximateAllOrders,
  exactPaidOrders,
  availableStatuses,
  ordersByStatus
});
~~~

Với bộ dữ liệu nhỏ, các phép này có thể cho số như kỳ vọng. Trong hệ thống thật, chúng được thực hiện ở **những thời điểm khác nhau** và có thể phản ánh các trạng thái dữ liệu khác nhau nếu có ghi đồng thời.

Nếu màn hình rất nhiều người dùng cần cùng một số đếm phức tạp, có thể thiết kế cache hoặc bảng/counter thống kê được duy trì theo nghiệp vụ, thay vì mỗi lần hiển thị đều chạy truy vấn quét collection lớn. Khi đó cần nêu rõ **mức độ mới của số liệu** và cách cập nhật thống kê.

### 13.3. Danh mục filter động

Ví dụ trang đơn hàng cung cấp dropdown **Trạng thái**:

~~~javascript
const statusOptions =
  db.orders.distinct("status").sort();

printjson(statusOptions);
~~~

Điều này phù hợp nếu số trạng thái nhỏ. Nếu field là giá trị tự do có hàng triệu giá trị như `customerId`, tải toàn bộ distinct vào một dropdown là không hợp lý. Lúc đó nên dùng API tìm kiếm gợi ý theo prefix, phân trang và index phù hợp.

## 14. MongoDB Java Sync Driver: ba thao tác tương ứng

Với Java, đối tượng **`MongoCollection<Document>`** cung cấp API tương tự các helper mongosh:

| Mongosh | Java Sync Driver |
| --- | --- |
| `db.orders.countDocuments({})` | `collection.countDocuments()` |
| `db.orders.countDocuments({ status: "PAID" })` | `collection.countDocuments(Filters.eq("status", "PAID"))` |
| `db.orders.estimatedDocumentCount()` | `collection.estimatedDocumentCount()` |
| `db.orders.distinct("status")` | `collection.distinct("status", String.class)` |

Ví dụ:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CountOptions;
import com.mongodb.client.model.Filters;

import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class CountAndDistinctExample {

    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("mongo_query_count_lab");

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            // Đếm chính xác toàn bộ document.
            long totalExact = orders.countDocuments();

            // Đếm chính xác theo filter.
            long paidOrders = orders.countDocuments(
                    Filters.eq("status", "PAID")
            );

            // Đếm ước lượng toàn collection.
            long totalEstimated = orders.estimatedDocumentCount();

            // Lấy các giá trị trạng thái phân biệt.
            List<String> statuses = orders
                    .distinct("status", String.class)
                    .into(new ArrayList<>());

            // Đếm toàn collection với hint index _id.
            long totalWithHint = orders.countDocuments(
                    new Document(),
                    new CountOptions().hintString("_id_")
            );

            System.out.println("Exact total: " + totalExact);
            System.out.println("Paid orders: " + paidOrders);
            System.out.println("Estimated total: " + totalEstimated);
            System.out.println("Statuses: " + statuses);
            System.out.println("Exact with hint: " + totalWithHint);
        }
    }
}
~~~

**Lưu ý:** Mã ví dụ yêu cầu MongoDB Java Sync Driver trong classpath, MongoDB đang chạy tại URI đã ghi và có dữ liệu mẫu. Kiểu `long` phù hợp để nhận số đếm trong Java Driver. Với field có nhiều BSON type khác nhau, việc yêu cầu `String.class` cho distinct có thể không phù hợp; cần thống nhất schema hoặc chọn kiểu giải mã thích hợp.

Trong một ứng dụng Spring Data MongoDB, có thể có các API tương đương ở tầng repository/template, nhưng vẫn cần phân biệt **đếm chính xác**, **đếm ước lượng** và **distinct** theo semantics thực của MongoDB.

## 15. Bài thực hành củng cố

Các bài tập dưới đây dùng collection **`mongo_query_count_lab.orders`** ở đầu bài. Có thể thử từng câu trong mongosh rồi đối chiếu với kết quả mong đợi.

### Bài 1: Đếm document

~~~javascript
db.orders.countDocuments({});
db.orders.countDocuments({ status: "PAID" });
db.orders.countDocuments({ channel: "APP" });
db.orders.countDocuments({ amount: { $lt: 300000 } });
~~~

Kết quả trên dữ liệu mẫu:

- Tổng: **10**.
- Trạng thái PAID: **5**.
- Kênh APP: **4**.
- Amount nhỏ hơn 300000: **5**.

Thử thay toán tử `$lt` bằng `$lte` rồi quan sát việc một document có `amount = 300000` được tính thêm.

### Bài 2: Phân biệt exact và estimated

~~~javascript
const exact = db.orders.countDocuments({});
const estimated = db.orders.estimatedDocumentCount();

printjson({ exact, estimated });
~~~

Giải thích vì sao hai số có thể trùng trên dữ liệu nhỏ nhưng không nên coi chúng là **hai cách đảm bảo độ chính xác như nhau**. Nếu triển khai sharded cluster, hãy suy nghĩ tại sao orphaned documents có thể ảnh hưởng tới thống kê metadata.

### Bài 3: Distinct theo field đơn và field lồng

~~~javascript
db.orders.distinct("status");
db.orders.distinct("channel");
db.orders.distinct("shipping.city");
db.orders.distinct("shipping.city", { status: "PENDING" });
~~~

Hãy xác định các loại giá trị được trả về và giải thích tại sao distinct không cho biết **mỗi city có bao nhiêu đơn**.

### Bài 4: Distinct trên array

~~~javascript
db.orders.distinct("tags");

db.orders.countDocuments({ tags: "new" });

db.orders.aggregate([
  { $unwind: "$tags" },
  { $sortByCount: "$tags" }
]);
~~~

So sánh ba câu hỏi:

1. Có những tag khác nhau nào?
2. Có bao nhiêu document chứa tag **new**?
3. Mỗi tag xuất hiện bao nhiêu lần ở các phần tử array?

Nếu một document có **`tags: ["new", "new"]`**, kết quả câu thứ ba có thể thay đổi ra sao, trong khi câu thứ hai vẫn đếm document đó một lần?

### Bài 5: Group, sort và count

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  { $sort: { n: -1 } }
]);

db.orders.aggregate([
  { $group: { _id: "$status" } },
  { $count: "numberOfStatuses" }
]);
~~~

Trả lời:

- Vì sao kết quả đầu tiên có **3 document nhóm** và tổng `n` bằng **10**?
- Vì sao kết quả thứ hai là **3**, không phải **10**?
- Nếu filter không khớp document nào và pipeline kết thúc bằng `$count`, vì sao kết quả có thể là array rỗng thay vì `[{ numberOfStatuses: 0 }]`?

### Bài 6: Chọn cách làm cho một yêu cầu mới

Một hệ thống có collection `events` hàng chục triệu document. Hãy chọn phương án cho từng yêu cầu:

| Yêu cầu | Hướng giải quyết |
| --- | --- |
| Số event thuộc khách hàng C-01 | `countDocuments({ customerId: "C-01" })` với index phù hợp |
| Quy mô collection xấp xỉ để hiển thị trên trang quản trị | `estimatedDocumentCount()` |
| Các loại `eventType` đang có, số lượng loại nhỏ | `distinct("eventType")` |
| Số event theo từng `eventType` | `$group` hoặc `$sortByCount` |
| Hàng triệu `eventId` phân biệt cần xuất file | Aggregation trả nhóm theo cursor hoặc thiết kế xuất dữ liệu chuyên dụng |
| Số event làm căn cứ đối soát chính xác | `countDocuments(filter)` với phạm vi/thời điểm/read concern đã xác định |

Bài tập kết thúc khi bạn có thể phân biệt rõ **đếm document theo điều kiện**, **đếm tổng ước lượng từ metadata** và **liệt kê giá trị không trùng lặp**, đồng thời hiểu lúc nào cần aggregation thay vì chỉ gọi một helper method.

## Tài liệu tham khảo

- [MongoDB Manual — db.collection.countDocuments()](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/)
- [MongoDB Manual — db.collection.estimatedDocumentCount()](https://www.mongodb.com/docs/manual/reference/method/db.collection.estimatedDocumentCount/)
- [MongoDB Manual — db.collection.distinct()](https://www.mongodb.com/docs/manual/reference/method/db.collection.distinct/)
- [MongoDB Manual — $count](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count/)
- [MongoDB Manual — $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB Manual — $sortByCount](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortByCount/)
- [MongoDB Java Sync Driver — Count Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/count/)
