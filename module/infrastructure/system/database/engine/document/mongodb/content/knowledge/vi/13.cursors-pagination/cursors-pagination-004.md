# Phân trang bằng `skip`, `limit` và chi phí ở trang sâu trong MongoDB

Một collection MongoDB có thể chứa hàng triệu document, trong khi màn hình danh sách chỉ hiển thị vài chục bản ghi mỗi lần. **Phân trang** giúp ứng dụng chia kết quả truy vấn thành nhiều phần nhỏ để người dùng xem lần lượt. Cách phổ biến và dễ hiểu nhất là **offset pagination**, kết hợp `skip` để bỏ qua những document đứng trước trang cần xem và `limit` để giới hạn số document trả về.

Ví dụ, mỗi trang có 20 bài viết: trang 1 bắt đầu ở vị trí 0, trang 2 bắt đầu ở vị trí 20, còn trang 500 bắt đầu ở vị trí 9.980. Phương pháp này rất tiện cho giao diện có số trang và nút “đến trang N”. Tuy nhiên, **trang càng sâu thì số phần tử MongoDB phải đi qua trước khi trả kết quả càng nhiều**. `limit(20)` không làm mất chi phí bỏ qua 9.980 phần tử trước đó.

Bài học thuộc chương **Cursor và phân trang**. Chúng ta sẽ thực hành với `mongosh`, đọc hành vi cursor, dùng `sort` để ổn định thứ tự, quan sát chi phí qua `explain("executionStats")`, áp dụng index phù hợp và nhận biết khi nào nên chuyển sang phân trang theo khóa (keyset/seek pagination).

## 1. `skip` và `limit` hoạt động như thế nào?

Hình dung một tập kết quả đã được lọc và sắp xếp:

```text
Danh sách kết quả theo thứ tự:

Vị trí:    0    1    2    3    4    5    6    7    8    9   ...
Document: A0   A1   A2   A3   A4   A5   A6   A7   A8   A9  ...

Trang 1: skip(0)  + limit(3)  -> A0, A1, A2
Trang 2: skip(3)  + limit(3)  -> A3, A4, A5
Trang 3: skip(6)  + limit(3)  -> A6, A7, A8
```

Trong MongoDB:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

Truy vấn trên được hiểu như sau:

1. Chọn các document có `status: "published"`.
2. Sắp xếp mới nhất trước theo `createdAt`; nếu trùng thời điểm, sắp xếp theo `_id` giảm dần.
3. Bỏ qua 3 document đầu trong **tập kết quả đã lọc và sắp xếp**.
4. Trả về tối đa 3 document tiếp theo.

| Thành phần | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `find(filter)` | Xác định document nào thuộc tập kết quả | `skip` đếm trên tập khớp bộ lọc, không đếm toàn collection |
| `sort(specification)` | Xác định thứ tự các document | Phân trang đáng tin cậy cần một thứ tự rõ ràng |
| `skip(n)` | Bỏ qua `n` kết quả đứng trước | `n = 0` nghĩa là không bỏ qua |
| `limit(k)` | Trả tối đa `k` kết quả | Nếu cuối danh sách còn ít hơn `k`, trang trả ít hơn |

`skip()` và `limit()` là các phương thức của **cursor** trả về từ `find()`. Cursor đại diện cho quá trình đọc kết quả; viết `find()` trong `mongosh` chưa đồng nghĩa tất cả document đã được tải sẵn vào bộ nhớ client. Chỉ đọc các batch cần thiết là một lợi ích của cursor, nhưng nó **không tự loại bỏ chi phí của offset lớn trên server**.

## 2. Tạo dữ liệu mẫu có thứ tự kiểm chứng được

Mở `mongosh` và chọn database thực hành:

```javascript
use mongo_pagination_lab
```

Chèn mười bài viết vào collection `posts` mới hoặc trống:

```javascript
db.posts.insertMany([
  {
    _id: 101, title: "Bài 101", status: "published",
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: 102, title: "Bài 102", status: "published",
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: 103, title: "Bài 103", status: "published",
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: 104, title: "Bài 104", status: "published",
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: 105, title: "Bài 105", status: "published",
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: 106, title: "Bài 106", status: "published",
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: 107, title: "Bài 107", status: "published",
    createdAt: ISODate("2026-11-09T08:00:00Z")
  },
  {
    _id: 108, title: "Bài 108", status: "published",
    createdAt: ISODate("2026-11-09T08:00:00Z")
  },
  {
    _id: 109, title: "Bài 109", status: "published",
    createdAt: ISODate("2026-11-08T08:00:00Z")
  },
  {
    _id: 110, title: "Bài 110", status: "published",
    createdAt: ISODate("2026-11-08T08:00:00Z")
  }
])
```

Các giá trị `_id` cố định được dùng để làm rõ thứ tự khi nhiều bài viết có cùng `createdAt`. `_id` không nhất thiết là số trong ứng dụng thực tế; có thể là ObjectId hoặc một khóa duy nhất khác.

Nếu chèn lại vào collection có các `_id` này, MongoDB sẽ báo lỗi trùng khóa. Hãy tạo bộ dữ liệu trên ở một môi trường lab riêng và tránh xóa collection có dữ liệu cần giữ.

Lấy danh sách theo thứ tự:

```javascript
db.posts.find(
  { status: "published" },
  { _id: 1, title: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
```

Thứ tự các ID kỳ vọng là:

```text
102, 101, 104, 103, 106, 105, 108, 107, 110, 109
```

Trong dữ liệu mẫu, `102` đứng trước `101` dù hai document có cùng timestamp, vì ta dùng `_id: -1` làm tiêu chí phụ.

## 3. Tính offset theo số trang

Nhiều API sử dụng **số trang bắt đầu từ 1**. Nếu `page` là số trang và `pageSize` là số document mỗi trang, ta có:

\[
\text{skip} = (\text{page} - 1) \times \text{pageSize}
\]

Ví dụ với `pageSize = 3`:

| Trang | Phép tính | `skip` | Kết quả ID trên dữ liệu mẫu |
| --- | --- | --- | --- |
| 1 | `(1 - 1) * 3` | 0 | `102, 101, 104` |
| 2 | `(2 - 1) * 3` | 3 | `103, 106, 105` |
| 3 | `(3 - 1) * 3` | 6 | `108, 107, 110` |
| 4 | `(4 - 1) * 3` | 9 | `109` |
| 5 | `(5 - 1) * 3` | 12 | Không có document |

Truy vấn từng trang trong `mongosh`:

```javascript
// Trang 1
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(3)

// Trang 2
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)

// Trang 3
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(6)
  .limit(3)
```

Một đoạn dùng biến:

```javascript
const page = 2;      // Đếm từ 1
const pageSize = 3;  // Số document/trang

if (!Number.isSafeInteger(page) || page < 1) {
  throw new Error("page phải là số nguyên >= 1");
}
if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100) {
  throw new Error("pageSize phải trong khoảng 1..100");
}

const offset = (page - 1) * pageSize;
if (!Number.isSafeInteger(offset)) {
  throw new Error("Offset vượt phạm vi số nguyên an toàn");
}

db.posts.find(
  { status: "published" },
  { title: 1, createdAt: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .skip(offset)
  .limit(pageSize)
```

Đây là cấu trúc phù hợp cho API kiểu `GET /posts?page=2&pageSize=3`. Phía server cần **tự kiểm tra** `page`, `pageSize` và `offset`; không chuyển trực tiếp tham số chưa được xác thực từ người dùng vào truy vấn.

Nếu giao diện dùng chỉ số trang bắt đầu từ 0, công thức là `skip = pageIndex * pageSize`. Hãy chọn một quy ước rõ ràng và áp dụng nhất quán ở cả frontend lẫn backend.

## 4. Vì sao phải dùng `sort` ổn định?

Không có `sort`, MongoDB **không bảo đảm thứ tự kết quả**. Thứ tự quan sát được có thể phụ thuộc vào access path, index, query planner hoặc thay đổi dữ liệu. Vì vậy:

```javascript
// Không nên dùng cho phân trang ổn định
db.posts.find({ status: "published" })
  .skip(3)
  .limit(3)
```

không có một ý nghĩa ổn định về “trang 2” nếu ứng dụng muốn một thứ tự cụ thể.

Thêm `sort({ createdAt: -1 })` đã định nghĩa hướng thời gian, nhưng các document có **cùng timestamp** vẫn có thể đổi vị trí tương đối. Trong bộ dữ liệu mẫu, cứ hai document lại có cùng `createdAt`, nên cần một khóa duy nhất để phân định thứ tự:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

Ở đây `_id` là duy nhất trong collection, nên cặp `(createdAt, _id)` tạo thứ tự xác định giữa các document. Khi hai phần tử có timestamp bằng nhau, MongoDB dùng `_id` để phân biệt.

**Thứ tự xác định không đồng nghĩa với ảnh chụp dữ liệu bất biến.** Dù có `sort` đầy đủ, kết quả các trang được yêu cầu ở những thời điểm khác nhau vẫn có thể thay đổi nếu dữ liệu được thêm, xóa hoặc các field sắp xếp được cập nhật. Mục 9 giải thích rõ giới hạn này.

### Lọc trước, rồi mới xác định vị trí

Nếu chỉ phân trang các bài viết đã xuất bản:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

thì offset 3 được tính trên **các bài viết có status published**, không phải trên toàn bộ collection rồi mới bỏ những bài viết draft. Vì vậy mỗi trang của cùng một danh sách phải dùng **cùng filter và sort**, trừ khi người dùng chủ động thay điều kiện tìm kiếm.

## 5. Tương tác giữa `skip`, `limit`, cursor và projection

`skip(n)` điều khiển vị trí bắt đầu trả kết quả; `limit(k)` điều khiển số lượng tối đa. Chúng không làm thay đổi document được lưu.

```javascript
db.posts.find(
  { status: "published" },
  { title: 1, createdAt: 1, _id: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
```

`projection` nằm trong đối số thứ hai của `find()`. Nó chỉ quyết định **field nào được trả về**, chẳng hạn `title`, `createdAt` và `_id`; nó không biến một trang sâu thành trang nông hay tránh được chi phí bỏ qua các kết quả đứng trước.

### Số lượng trả về là giới hạn trên

Nếu trang cuối chỉ còn một document, `limit(3)` vẫn chỉ trả một document. Khi offset đã vượt số document thỏa bộ lọc, cursor không trả document nào. Đây là trạng thái bình thường, không nhất thiết là lỗi truy vấn.

```javascript
// Có 10 document trong bộ dữ liệu mẫu:
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(9)
  .limit(3) // Chỉ còn 1 document
```

### `batchSize` khác với `limit`

Driver và máy chủ trao đổi dữ liệu cursor theo các **batch**. `batchSize()` điều chỉnh số document mong muốn trong mỗi batch, còn `limit()` giới hạn **tổng số document của truy vấn**.

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(3)
  .limit(3)
  .batchSize(2)
```

Với cấu hình này, tổng số kết quả vẫn không vượt 3, dù driver có thể cần nhiều lần lấy batch. `batchSize(2)` không có nghĩa truy vấn chỉ được trả tối đa hai document.

Đối với phân trang giao diện, hãy dùng `limit` để giới hạn số phần tử mỗi trang; điều chỉnh `batchSize` chỉ khi có yêu cầu cụ thể về truyền dữ liệu hoặc luồng đọc cursor.

### Khi dùng aggregation pipeline

Nếu truy vấn cần `aggregate()`, thứ tự các stage là yếu tố mang tính ngữ nghĩa:

```javascript
db.posts.aggregate([
  { $match: { status: "published" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $skip: 3 },
  { $limit: 3 },
  { $project: { title: 1, createdAt: 1 } }
])
```

Mục tiêu là **match → sort → skip → limit**. Nếu viết pipeline `$limit: 3` rồi mới `$skip: 3`, ta đã giới hạn dòng dữ liệu xuống ba phần tử trước khi bỏ qua ba phần tử đó; kết quả không phải trang 2 như mong muốn. Bộ tối ưu MongoDB có thể sắp xếp lại một số thao tác để tối ưu thực thi, nhưng người viết pipeline vẫn phải diễn đạt đúng thứ tự logic.

## 6. Chi phí ở trang sâu: vì sao `skip` lớn trở nên đắt?

Giả sử một collection có 2 triệu bài viết thỏa bộ lọc; mỗi trang hiển thị 20 bài:

| Trang | `skip` | `limit` | Số phần tử đứng trước trang cần đọc |
| --- | ---: | ---: | ---: |
| 1 | 0 | 20 | 0 |
| 10 | 180 | 20 | 180 |
| 100 | 1.980 | 20 | 1.980 |
| 1.000 | 19.980 | 20 | 19.980 |
| 10.000 | 199.980 | 20 | 199.980 |

Để tìm đến các phần tử ở vị trí sâu, MongoDB thường phải **duyệt qua các phần tử đứng trước trong thứ tự kết quả**, rồi bỏ chúng đi. `skip(199980).limit(20)` chỉ trả tối đa 20 document cho client, nhưng không có nghĩa máy chủ chỉ xử lý 20 mục.

Trong điều kiện truy vấn đã có index hỗ trợ lọc và thứ tự, một mô hình chi phí trực quan là:

\[
\text{Số mục cần đi qua} \approx \text{skip} + \text{limit}
\]

Đây là **cách hình dung về lượng công việc phải đi qua**, không phải công thức cố định cho thời gian chạy hay số document được giải mã: kế hoạch thực thi, selectivity, index, cache và filter vẫn ảnh hưởng kết quả. MongoDB không thể tự nhảy thẳng đến “bản ghi thứ 200.000” chỉ từ thứ tự B-tree như thể đã có bảng ánh xạ chính xác từ số trang đến offset.

### Trang 1 và trang 10.000 khác nhau ra sao?

```text
Trang 1:
[20 mục cần đọc] --> Trả 20 mục

Trang 10.000:
[199.980 mục đi qua/bỏ qua] [20 mục cần đọc] --> Trả 20 mục
                                   ^
                            Lượng dữ liệu trả về ít
                            không xóa chi phí bỏ qua
```

Vì thế, API có `limit: 20` chưa đủ để bảo đảm phản hồi nhanh ở mọi trang. Các yêu cầu với offset rất lớn có thể gây tăng độ trễ và tải hệ thống, đặc biệt khi nhiều người dùng cùng nhảy đến trang sâu.

### Chi phí khi không có index hỗ trợ `sort`

Khi MongoDB không có index phù hợp, máy chủ có thể phải đọc nhiều document để lọc, sắp xếp hoặc duy trì vùng dữ liệu cho thao tác sort và offset. Một số kế hoạch sử dụng thao tác sort có giới hạn theo `skip + limit` để giảm bộ nhớ trung gian, nhưng **offset càng lớn thì vùng đầu ra cần xử lý vẫn có thể lớn**.

Các khoản chi phí có thể gồm:

- Đọc nhiều index entries hoặc document để tìm đủ các bản ghi khớp filter.
- Sắp xếp tập kết quả hoặc duy trì dữ liệu trung gian nếu index không phục vụ thứ tự.
- CPU, bộ nhớ, I/O và thời gian giữ tài nguyên truy vấn.
- Độ trễ tích lũy khi nhiều yêu cầu đồng thời thực hiện phân trang sâu.

Không nên đoán trước rằng truy vấn có index luôn nhanh hoặc truy vấn không có index luôn chậm; hãy kiểm tra kế hoạch thực tế của **đúng filter, sort, skip, limit**.

## 7. Dùng index để giảm công việc lọc và sắp xếp

Với truy vấn thường xuyên:

```javascript
db.posts.find({ status: "published" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(1000)
  .limit(20)
```

có thể tạo compound index:

```javascript
db.posts.createIndex(
  { status: 1, createdAt: -1, _id: -1 },
  { name: "status_createdAt_id_desc" }
)
```

Index này được thiết kế cho bộ lọc equality trên `status` và thứ tự giảm dần của `createdAt`, `_id`. Nếu query planner chọn index phù hợp, MongoDB có thể tránh phải sắp xếp toàn bộ kết quả trong bộ nhớ chỉ để đáp ứng `sort`.

Tuy nhiên, **index không loại bỏ yêu cầu duyệt qua offset**. Muốn trả trang bắt đầu ở vị trí 1.000, máy chủ vẫn cần xử lý các mục đứng trước trang theo thứ tự được dùng, dù việc đi qua các mục trong index thường hiệu quả hơn phải quét collection và sort.

### Chọn index theo filter và sort thực tế

| Query shape | Index có thể cân nhắc | Ghi chú |
| --- | --- | --- |
| `find({status:"published"}).sort({createdAt:-1,_id:-1})` | `{status:1,createdAt:-1,_id:-1}` | Equality trên `status`, sau đó sort |
| `find({authorId:"u1"}).sort({createdAt:-1,_id:-1})` | `{authorId:1,createdAt:-1,_id:-1}` | Dành cho danh sách theo tác giả |
| `find({}).sort({_id:1})` | Index mặc định trên `_id` | Có thể đọc theo thứ tự `_id` |
| `find({category:"tech",status:"published"}).sort({createdAt:-1,_id:-1})` | `{category:1,status:1,createdAt:-1,_id:-1}` | Cần đánh giá tính chọn lọc và mẫu truy vấn chính |

Không tạo hàng loạt index chỉ vì có nhiều màn hình. Index chiếm dung lượng và làm tăng công việc khi insert/update/delete. Hãy chọn theo truy vấn quan trọng, đo hiệu quả và quản lý index trong kế hoạch vận hành.

### Index cũng không sửa được thứ tự không ổn định

```javascript
db.posts.find({ status: "published" }).skip(100).limit(20)
```

vẫn không có thứ tự được bảo đảm dù collection đã có index. Ứng dụng phải **chỉ rõ `sort`**, và khi khóa sort có giá trị trùng, nên thêm một khóa duy nhất để phân định thứ tự.

## 8. Đo chi phí bằng `explain("executionStats")`

MongoDB cung cấp `explain()` để xem cách query planner dự kiến và thực thi truy vấn. Với dữ liệu lab nhỏ, không nên kết luận về hiệu năng production; mục đích là học cách đọc các trường thống kê. Có thể dùng collection lớn hơn trong môi trường thử nghiệm nếu được phép.

```javascript
const filter = { status: "published" };
const order = { createdAt: -1, _id: -1 };

db.posts.find(filter)
  .sort(order)
  .skip(0)
  .limit(3)
  .explain("executionStats")
```

So sánh với offset lớn hơn:

```javascript
db.posts.find(filter)
  .sort(order)
  .skip(6)
  .limit(3)
  .explain("executionStats")
```

Khi đọc kết quả, tập trung vào:

| Trường thống kê / dấu hiệu | Điều cần quan sát |
| --- | --- |
| `nReturned` | Số document kết quả của truy vấn giải thích |
| `totalKeysExamined` | Số index entries được xem xét trong quá trình thực thi |
| `totalDocsExamined` | Số document được xem xét ở các bước cần đọc document |
| `executionTimeMillis` | Thời gian thực thi được báo cáo, chịu ảnh hưởng môi trường đo |
| Các stage như `IXSCAN`, `COLLSCAN`, `SORT`, `SKIP`, `LIMIT` | Gợi ý kế hoạch sử dụng index, quét collection, sort, bỏ qua và giới hạn |

Với index tốt, `totalKeysExamined` có thể tăng đáng kể khi `skip` tăng, dù `nReturned` vẫn gần với `limit`. `totalDocsExamined` có thể tăng ít hơn nếu truy vấn được index hỗ trợ tốt hoặc covered; không nên suy ra rằng số document đọc **luôn** đúng bằng `skip + limit`.

Kế hoạch và cấu trúc `explain` có thể khác theo phiên bản MongoDB và bộ máy thực thi. Thời gian chạy có thể thay đổi vì cache, tài nguyên máy, tải cạnh tranh và độ lớn tập dữ liệu. Do đó, hãy so sánh **một nhóm phép đo cùng điều kiện**, không dựa vào duy nhất một con số thời gian từ một lần chạy.

### Thử thay đổi index

Sau khi đã tạo index:

```javascript
db.posts.getIndexes()
```

Chạy lại hai truy vấn `explain` với offset khác nhau. Quan sát xem query planner có dùng index đúng với filter/sort không, có xuất hiện `SORT` cần xử lý thêm không và các trường `totalKeysExamined` biến thiên thế nào.

Thử nghiệm `explain` là quan sát kỹ thuật; nó không làm cho offset pagination tự trở thành giải pháp phù hợp khi người dùng thường xuyên duyệt hàng trăm nghìn vị trí.

## 9. Dữ liệu thay đổi giữa các trang: lặp và bỏ sót document

**`sort` ổn định là cần thiết nhưng chưa đủ** nếu mỗi trang được tải trong một request riêng ở thời điểm khác nhau. Bản chất của offset pagination là “bỏ qua N phần tử đứng đầu **tại lúc chạy truy vấn hiện tại**”. Khi tập kết quả thay đổi, vị trí của các document cũng thay đổi.

### 9.1. Thêm document mới có thể gây lặp

Ban đầu, với `pageSize = 3` và sort `{createdAt:-1,_id:-1}`:

```text
Trang 1 đã đọc:          [102, 101, 104]
Phần chưa đọc:            103, 106, 105, 108, ...
```

Sau khi người dùng đọc trang 1, có một bài mới `111` với `createdAt` mới hơn tất cả bài cũ:

```text
Danh sách mới:            111, 102, 101, 104, 103, 106, 105, ...
Trang 2 dùng skip(3):                [104, 103, 106]
```

Document `104` đã xuất hiện ở cuối trang 1 nhưng nay lại ở đầu trang 2. Đây là lỗi **lặp giữa các trang** do vị trí bị dịch chuyển; thêm `_id` vào sort không ngăn được vì tập dữ liệu đã đổi.

### 9.2. Xóa document có thể gây bỏ sót

Nếu `102` bị xóa sau khi trang 1 trả về:

```text
Danh sách ban đầu:         102, 101, 104, 103, 106, 105, ...
Trang 1 đã đọc:          [102, 101, 104]

Danh sách sau khi xóa:     101, 104, 103, 106, 105, 108, ...
Trang 2 dùng skip(3):                 [106, 105, 108]
```

Document `103` bị **bỏ sót** đối với người đang đi từ trang 1 đến trang 2 vì phần tử trước nó đã bị xóa. Cập nhật `status` làm document không còn khớp filter, hoặc thay đổi field `createdAt` dùng để sort, cũng có thể gây hiện tượng tương tự.

### 9.3. Khi nào vấn đề này quan trọng?

- Danh sách quản trị ít thay đổi và người dùng muốn nhảy trang tùy ý: offset pagination có thể là lựa chọn hợp lý.
- News feed hoặc danh sách công việc đang thay đổi liên tục: offset pagination dễ khiến người dùng thấy lặp hoặc bỏ sót.
- Luồng xuất dữ liệu cần tập kết quả nhất quán: phải có chiến lược riêng về snapshot/phiên đọc, checkpoint hoặc khóa sắp xếp; nhiều request phân trang thông thường không tự tạo ảnh chụp bất biến.

**Không nên hứa rằng chỉ thêm `sort` sẽ bảo đảm người dùng thấy mỗi document đúng một lần trên nhiều request.** Sort chỉ xác định thứ tự tại từng thời điểm.

## 10. Phân trang theo khóa (keyset/seek) khi thường xuyên đi sâu

Khi giao diện chủ yếu dùng nút **“Xem thêm”**, **“Trang tiếp theo”** hoặc cuộn vô hạn, có thể tránh offset lớn bằng cách nhớ **khóa sắp xếp của document cuối trang trước**.

Với sort:

```javascript
{ createdAt: -1, _id: -1 }
```

trang kế tiếp cần các document có cặp khóa **nhỏ hơn** cặp của document cuối trang trước theo thứ tự giảm dần:

- `createdAt` cũ hơn `last.createdAt`, hoặc
- `createdAt` bằng `last.createdAt` nhưng `_id` nhỏ hơn `last._id`.

### 10.1. Lấy trang đầu

```javascript
const pageSize = 3;
const order = { createdAt: -1, _id: -1 };

const firstPage = db.posts.find(
  { status: "published" },
  { _id: 1, title: 1, createdAt: 1 }
)
  .sort(order)
  .limit(pageSize)
  .toArray();

printjson(firstPage);
```

Với dữ liệu mẫu, trang đầu chứa `102, 101, 104`. Document cuối có `_id = 104` và `createdAt = 2026-11-11T08:00:00Z`.

### 10.2. Truy vấn trang tiếp theo bằng khóa

```javascript
if (firstPage.length > 0) {
  const last = firstPage[firstPage.length - 1];

  const secondPage = db.posts.find(
    {
      status: "published",
      $or: [
        { createdAt: { $lt: last.createdAt } },
        {
          createdAt: last.createdAt,
          _id: { $lt: last._id }
        }
      ]
    },
    { _id: 1, title: 1, createdAt: 1 }
  )
    .sort({ createdAt: -1, _id: -1 })
    .limit(pageSize)
    .toArray();

  printjson(secondPage);
}
```

Trang hai chứa `103, 106, 105` khi dữ liệu chưa đổi. Không cần `skip(3)`: bộ lọc đã đặt **vị trí bắt đầu theo giá trị khóa**. Với index phù hợp, truy vấn có thể tìm đoạn khóa cần đọc hiệu quả hơn khi đã đi rất sâu.

### 10.3. So sánh offset và keyset

| Tiêu chí | Offset: `skip + limit` | Keyset: khóa cuối + `limit` |
| --- | --- | --- |
| Truy cập trang số 500 trực tiếp | Dễ biểu diễn bằng offset | Thường phải có token của vị trí tương ứng |
| Nút “Xem thêm” | Có thể dùng, nhưng offset tăng dần | Phù hợp tự nhiên |
| Chi phí trang sâu | Thường tăng theo số mục phải bỏ qua | Có thể tìm theo khoảng khóa nếu index hỗ trợ |
| Khi thêm bản mới trước vị trí đang đọc | Dễ thấy lặp hoặc bỏ sót | Thường tránh được sự dịch chuyển do insert ở đầu danh sách |
| Cần thứ tự xác định | Có | Có, và khóa sort phải được giữ trong token |
| Đếm tổng số trang | Có thể kết hợp `countDocuments` | Không bắt buộc; thường dùng `hasNext` |
| Thay đổi khóa sort của document đã có | Có thể ảnh hưởng | Cũng có thể ảnh hưởng; không phải snapshot |

Keyset không hoàn toàn thay thế offset trong mọi UI: nếu yêu cầu nhảy đến một trang bất kỳ theo số, offset vẫn tiện hơn. Ngược lại, với luồng cuộn vô hạn có thể đi rất sâu, keyset thường phù hợp hơn.

**Token phân trang thực tế** nên mang thông tin cần thiết để dựng lại điều kiện: `createdAt`, `_id`, cùng ngữ cảnh filter/sort nếu API cần bảo đảm token không bị dùng sai. Có thể đóng gói và ký token ở tầng ứng dụng; khi đổi filter hoặc thứ tự, phải bắt đầu lại từ trang đầu. Không bao giờ tin một token do client gửi mà không kiểm tra cấu trúc và quyền truy cập.

## 11. Đếm tổng số phần tử và tính `hasNext`

Một giao diện có số trang thường cần thêm tổng số bản ghi. MongoDB có:

```javascript
const total = db.posts.countDocuments({
  status: "published"
});

const pageSize = 3;
const totalPages = Math.ceil(total / pageSize);

print("Tổng bản ghi: " + total);
print("Tổng số trang: " + totalPages);
```

Với bộ dữ liệu mẫu, `total = 10`, `totalPages = 4`. `countDocuments(filter)` sử dụng **cùng bộ lọc** với danh sách; nếu đổi `status` hoặc điều kiện tìm kiếm, tổng số phải tương ứng với filter mới.

Tuy nhiên, phép đếm chính xác có thể tốn tài nguyên khi tập dữ liệu lớn hoặc filter phức tạp. Đừng tự động chạy một phép đếm nặng sau **mọi** request trang nếu giao diện chỉ cần biết liệu có trang tiếp theo hay không.

### Xác định `hasNext` bằng một phần tử bổ sung

Có thể lấy tối đa `pageSize + 1` document ở vị trí trang hiện tại:

```javascript
const page = 2;
const pageSize = 3;
const offset = (page - 1) * pageSize;

const fetched = db.posts.find(
  { status: "published" },
  { _id: 1, title: 1, createdAt: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .skip(offset)
  .limit(pageSize + 1)
  .toArray();

const hasNext = fetched.length > pageSize;
const items = fetched.slice(0, pageSize);

printjson({ page, pageSize, hasNext, items });
```

`hasNext` cho biết có **ít nhất một phần tử kế tiếp tại thời điểm truy vấn**. Không cần đếm toàn bộ collection, nhưng offset sâu vẫn phải chịu chi phí `skip`. Nếu dữ liệu được thay đổi giữa các request, `hasNext` và tổng trang có thể thay đổi.

`estimatedDocumentCount()` là phép ước lượng nhanh dựa trên metadata ở cấp collection, không nhận cùng `filter` như `countDocuments()`; do đó không thể dùng nó để thay thế chính xác tổng số document `status: "published"`.

## 12. Cài đặt phân trang offset bằng MongoDB Java Sync Driver

Trong Java, phương thức `find()` trả về `FindIterable<Document>`; có thể gọi `.sort()`, `.skip()` và `.limit()`. Đoạn dưới đây minh họa một hàm lấy trang, xác thực tham số, dùng thứ tự ổn định và trả cả cờ `hasNext`.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class PostsPaginationExample {
    record Page(List<Document> items, boolean hasNext) {}

    static Page getPage(
            MongoCollection<Document> posts,
            int pageNumber,
            int pageSize) {

        if (pageNumber < 1) {
            throw new IllegalArgumentException("pageNumber phải >= 1");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize phải trong 1..100");
        }

        long offset = ((long) pageNumber - 1L) * pageSize;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Offset vượt phạm vi skip của Java Driver"
            );
        }

        List<Document> fetched = posts.find(
                Filters.eq("status", "published"))
            .sort(Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
            ))
            .projection(Projections.include("_id", "title", "createdAt"))
            .skip((int) offset)
            .limit(pageSize + 1)
            .into(new ArrayList<>());

        boolean hasNext = fetched.size() > pageSize;
        if (hasNext) {
            fetched.remove(pageSize); // Bỏ phần tử chỉ dùng để kiểm tra
        }
        return new Page(fetched, hasNext);
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_pagination_lab");
            MongoCollection<Document> posts =
                database.getCollection("posts");

            Page page2 = getPage(posts, 2, 3);
            for (Document post : page2.items()) {
                System.out.println(post.toJson());
            }
            System.out.println("hasNext = " + page2.hasNext());
        }
    }
}
```

Đoạn mã dùng Java `record` (Java 16+) và MongoDB Java Sync Driver phù hợp. Nó giả định đã tạo dữ liệu mẫu và có biến môi trường `MONGODB_URI`. Với dữ liệu ban đầu, trang 2 chứa các ID `103, 106, 105`; `hasNext` là `true` vì còn các bài sau trang 2.

**Vì sao ép `offset` qua `long` trước?** Nếu nhân hai số nguyên `int` lớn, phép tính có thể overflow trước khi được truyền vào driver. Trong ví dụ, `skip(int)` của Java Sync Driver nhận một giá trị `int`, nên ta kiểm tra phạm vi rồi mới ép kiểu. Việc giới hạn `pageSize` ngăn client yêu cầu một trang quá lớn, nhưng một `pageNumber` rất lớn dù hợp lệ về kiểu vẫn có thể khiến truy vấn offset tốn kém; API production nên bổ sung chính sách giới hạn độ sâu hoặc dùng cách phân trang khác.

### Trả kết quả qua REST API

Một phản hồi có thể có cấu trúc:

```json
{
  "page": 2,
  "pageSize": 3,
  "hasNext": true,
  "items": [
    { "_id": 103, "title": "Bài 103" },
    { "_id": 106, "title": "Bài 106" },
    { "_id": 105, "title": "Bài 105" }
  ]
}
```

Đây là ví dụ hình thức API; trường `createdAt` có thể được trả thêm theo nhu cầu. Backend nên giữ cùng filter, sort và giới hạn tham số ở mọi trang. Nếu UI cần “tổng số trang”, có thể thêm `totalCount` lấy từ một phép đếm có cân nhắc chi phí.

## 13. Những sai lầm thường gặp

| Tình huống | Vì sao sai hoặc kém hiệu quả? | Hướng xử lý |
| --- | --- | --- |
| Dùng `skip`/`limit` mà không có `sort` | Không có thứ tự kết quả được bảo đảm | Chỉ định sort rõ ràng |
| Chỉ sort theo `createdAt` khi nhiều document trùng timestamp | Các document cùng thời điểm không có vị trí ổn định | Bổ sung `_id` hoặc khóa duy nhất vào sort |
| Trang 1 bị tính `skip = page * size` | Nhảy qua trang đầu nếu page đếm từ 1 | Dùng `(page - 1) * pageSize` |
| `page = 0`, `pageSize = -10` hoặc `pageSize` quá lớn | Tham số không hợp lệ hoặc gây tải không cần thiết | Xác thực và đặt giới hạn trước truy vấn |
| Tin rằng `limit(20)` bảo đảm truy vấn trang 50.000 nhanh | Server còn phải xử lý offset trước khi trả 20 kết quả | Đánh giá chi phí và dùng keyset khi phù hợp |
| Có index là có thể nhảy ngay đến kết quả thứ N | Index hỗ trợ thứ tự/tìm kiếm nhưng không ánh xạ trực tiếp đến ordinal N | Dùng điều kiện theo khóa sắp xếp nếu cần đi sâu |
| Đổi filter giữa các request nhưng giữ nguyên page/offset | Trang không còn tương ứng cùng tập kết quả | Reset trang về 1 khi thay bộ lọc |
| Thêm bài mới làm document lặp giữa các trang | Offset đếm lại từ đầu danh sách đã thay đổi | Cân nhắc keyset/seek hoặc cơ chế snapshot |
| Dùng `estimatedDocumentCount()` để tính tổng của một filter | Ước lượng ở cấp collection, không đếm chính xác theo filter | Dùng `countDocuments(filter)` khi thật sự cần tổng chính xác |
| Chạy `countDocuments()` cho mọi lượt cuộn vô hạn | Phép đếm có thể tăng tải nhưng UI chỉ cần biết còn mục kế tiếp không | Lấy `pageSize + 1` để tính `hasNext` |
| Trong aggregation, đặt `$limit` trước `$skip` | Giới hạn dữ liệu trước rồi mới bỏ qua, sai trang | Sắp xếp stage thành `$sort` → `$skip` → `$limit` |
| Phán đoán độ nhanh chỉ từ một lần chạy | Cache, tải máy và query planner tác động đến thời gian | Xem execution stats và đo cùng điều kiện nhiều lần |

## 14. Bài tập thực hành

### Bài 1. Tính offset

Một giao diện hiển thị 25 document mỗi trang, đánh số từ 1. Tính offset cho trang 1, 4, 20 và 200.

**Đáp án:**

| Trang | Công thức | Offset |
| --- | --- | ---: |
| 1 | `(1 - 1) * 25` | 0 |
| 4 | `(4 - 1) * 25` | 75 |
| 20 | `(20 - 1) * 25` | 475 |
| 200 | `(200 - 1) * 25` | 4.975 |

### Bài 2. Viết truy vấn trang 3

Collection `orders` có field `state`, `createdAt`, `_id`. Yêu cầu: tìm đơn hàng có `state: "paid"`, mới nhất trước, phân trang 15 đơn/trang; lấy trang số 3.

**Đáp án:**

```javascript
db.orders.find({ state: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(30)
  .limit(15)
```

Offset là `(3 - 1) * 15 = 30`. Việc thêm `_id` tránh thứ tự mơ hồ khi các đơn có cùng thời điểm tạo.

### Bài 3. So sánh trang đầu và trang sâu

Một danh sách có 1 triệu document phù hợp và có index hỗ trợ filter/sort. Một request dùng `skip(0).limit(20)`, request khác dùng `skip(200000).limit(20)`. Cả hai chỉ trả 20 document. Vì sao request thứ hai có thể chậm hơn nhiều?

**Đáp án:** Offset 200.000 khiến MongoDB phải đi qua nhiều mục trước phần kết quả cần trả. Index có thể giảm chi phí lọc/sort, nhưng không tự nhảy tới kết quả ordinal 200.001 chỉ nhờ offset. Kiểm tra `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis` và winning plan bằng `explain("executionStats")`.

### Bài 4. Phát hiện lỗi lặp giữa các trang

Trang 1 đã trả `[102, 101, 104]`. Sau đó có một document mới `111` đứng đầu danh sách. Trang 2 vẫn gọi `skip(3).limit(3)`. Kết quả có thể bị vấn đề gì?

**Đáp án:** Trong danh sách mới `[111, 102, 101, 104, 103, 106, ...]`, trang 2 bắt đầu từ `104`, nên `104` bị lặp. Đây là thay đổi vị trí do insert giữa hai request, không phải lỗi thiếu `sort`.

### Bài 5. Xây dựng bộ lọc keyset cho sort giảm dần

Giả sử trang trước kết thúc bằng document:

```javascript
{
  _id: 104,
  createdAt: ISODate("2026-11-11T08:00:00Z")
}
```

Hãy lấy tối đa ba document tiếp theo theo thứ tự `createdAt` giảm dần, `_id` giảm dần.

**Đáp án:**

```javascript
db.posts.find({
  status: "published",
  $or: [
    {
      createdAt: {
        $lt: ISODate("2026-11-11T08:00:00Z")
      }
    },
    {
      createdAt: ISODate("2026-11-11T08:00:00Z"),
      _id: { $lt: 104 }
    }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
```

Kết quả trên dữ liệu mẫu là `103, 106, 105`. Bộ lọc dùng **giá trị khóa cuối trang trước**, không dùng offset.

### Bài 6. Chọn giữa offset và keyset

Hai màn hình có yêu cầu khác nhau:

- **Màn A:** quản trị viên muốn nhảy ngay tới trang 75 của một danh sách gần như không đổi.
- **Màn B:** bảng tin cập nhật thường xuyên, người dùng cuộn liên tục bằng nút “Xem thêm”.

**Đáp án gợi ý:** Màn A phù hợp với offset pagination nếu độ sâu truy cập nằm trong giới hạn hiệu năng chấp nhận được và có filter/sort/index hợp lý. Màn B thường phù hợp với keyset vì chỉ cần tiến từ vị trí hiện tại, giảm chi phí bỏ qua nhiều mục và hạn chế lặp do bài mới xuất hiện ở đầu danh sách.

## 15. Quy tắc thực hành cần nhớ

Trước khi phát hành một API phân trang MongoDB, cần xác định: **filter** nào tạo tập kết quả, **sort** nào tạo thứ tự đầy đủ, **pageSize** tối đa là bao nhiêu, có cần **tổng số trang** hay chỉ cần `hasNext`, và người dùng có thực sự cần nhảy trực tiếp đến **trang sâu** hay không.

Với danh sách nhỏ hoặc vừa, `find().sort().skip().limit()` là phương pháp rõ ràng, dễ tích hợp với số trang. Khi offset tăng lớn, **lượng dữ liệu server phải đi qua tăng dù số kết quả trả về không đổi**; compound index giúp giảm chi phí lọc và sắp xếp nhưng không loại bỏ hoàn toàn bản chất của offset. Với luồng đọc tuần tự rất sâu, hãy cân nhắc lưu khóa cuối trang và dùng **keyset pagination**. Dù chọn cách nào, yêu cầu sắp xếp ổn định và hiểu rõ tác động của dữ liệu thay đổi giữa các request vẫn là nền tảng của một API phân trang đáng tin cậy.
