# Phân trang theo khóa với khóa ghép và thứ tự ổn định trong MongoDB

Khi một collection có hàng trăm nghìn hoặc hàng triệu document, ứng dụng thường không trả tất cả bản ghi trong một lần. Danh sách đơn hàng, nhật ký hoạt động, lịch sử giao dịch hay dòng tin cần **phân trang** để trả từng nhóm dữ liệu nhỏ. Cách quen thuộc là `skip() + limit()`, nhưng khi vị trí trang ngày càng sâu, MongoDB có thể phải đi qua nhiều kết quả trước khi đến trang cần đọc. Dữ liệu được chèn hoặc xóa trong lúc người dùng xem các trang cũng có thể khiến kết quả bị lặp hoặc bỏ sót.

**Phân trang theo khóa (keyset pagination, còn gọi là seek pagination)** sử dụng **giá trị khóa sắp xếp của bản ghi cuối trang trước** làm mốc để lấy trang tiếp theo. Để kết quả có thứ tự xác định khi nhiều document có cùng thời gian hoặc cùng điểm số, ta dùng **khóa ghép** gồm trường sắp xếp chính và một **trường phân biệt duy nhất**, thường là `_id`.

Bài học này trình bày cách tạo thứ tự ổn định, thiết kế filter theo thứ tự từ điển (lexicographic order), phân trang tiến/lùi, tạo cursor token cho API, thiết kế compound index và hiểu giới hạn khi dữ liệu thay đổi giữa các request.

## 1. Vì sao phân trang cần thứ tự ổn định?

Giả sử collection `orders` được sắp xếp theo `createdAt` giảm dần:

~~~javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1 })
  .limit(3);
~~~

Khi hai đơn hàng có **cùng `createdAt`**, điều kiện sort chỉ theo thời gian **không xác định** đơn nào phải đứng trước. MongoDB không đảm bảo thứ tự cố định giữa các document có cùng giá trị sort. Tùy kế hoạch thực thi, vị trí các bản ghi đồng hạng có thể khác nhau giữa các lần truy vấn.

Ví dụ, cùng một giây có ba đơn:

| orderCode | createdAt |
| --- | --- |
| O-105 | 2026-05-03T10:00:00Z |
| O-106 | 2026-05-03T10:00:00Z |
| O-107 | 2026-05-03T10:00:00Z |

Với `sort({ createdAt: -1 })`, cả ba bằng nhau theo khóa sort. Nếu ranh giới trang đi qua nhóm này, một phần tử có thể xuất hiện ở hai trang hoặc bị bỏ sót khi ứng dụng chạy hai truy vấn riêng biệt.

Cách chuẩn hóa thứ tự:

~~~javascript
db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3);
~~~

Tổ hợp **`(createdAt, _id)`** tạo thứ tự xác định khi `_id` là duy nhất trong tập kết quả cần phân trang:

1. So sánh `createdAt` trước, thời gian **mới hơn** đứng trước.
2. Nếu hai document có cùng `createdAt`, so sánh `_id`, giá trị **lớn hơn** đứng trước.
3. Khi không có hai document nào cùng cả hai khóa, mỗi document có một vị trí rõ ràng trong thứ tự.

**Thứ tự ổn định không đồng nghĩa dữ liệu bất biến.** Nếu có chèn/xóa hoặc cập nhật trường sort giữa hai lần đọc, vị trí logic của document vẫn có thể thay đổi. Khóa ghép giải quyết việc *đồng hạng theo sort*; phần về dữ liệu thay đổi sẽ giải thích giới hạn tiếp theo.

## 2. Phân trang offset và phân trang theo khóa

### 2.1. Offset: skip + limit

~~~javascript
const pageSize = 20;
const pageNumber = 100;

db.orders.find({ status: "paid" })
  .sort({ createdAt: -1, _id: -1 })
  .skip((pageNumber - 1) * pageSize)
  .limit(pageSize);
~~~

Với trang thứ 100, MongoDB phải bỏ qua **1.980 kết quả** theo thứ tự sắp xếp rồi mới trả tối đa 20 document. Index có thể giúp việc sắp xếp và duyệt, nhưng `skip()` ở offset sâu vẫn cần đi qua các phần tử bị bỏ qua.

Offset có lợi khi giao diện cần chọn ngay “trang 5”, “trang 100” và tập kết quả tương đối nhỏ, ít biến động. Hạn chế là chi phí đọc sâu và nguy cơ lệch vị trí khi dữ liệu mới được thêm hoặc dữ liệu cũ bị xóa.

### 2.2. Keyset: bắt đầu từ khóa của phần tử cuối

Thay vì “bỏ qua 1.980 bản ghi”, ứng dụng gửi mốc:

~~~text
Sau bản ghi có:
  createdAt = 2026-05-03T10:00:00Z
  _id       = ObjectId("000000000000000000000006")
~~~

MongoDB tìm các bản ghi **nằm sau mốc** theo cùng thứ tự sort. Với sort **giảm dần** ở cả hai khóa, điều kiện trang kế tiếp là:

~~~text
createdAt < last.createdAt
OR
(createdAt = last.createdAt AND _id < last._id)
~~~

Chính điều kiện này giúp không bỏ sót các bản ghi **trùng thời gian** nhưng có `_id` nhỏ hơn.

### 2.3. So sánh nhanh

| Tiêu chí | Offset (`skip/limit`) | Keyset (seek/cursor token) |
| --- | --- | --- |
| Cách xác định trang | Số thứ tự trang và số bản ghi bỏ qua | Khóa sắp xếp của bản ghi biên |
| Truy cập trang rất sâu | Có thể tốn chi phí duyệt nhiều kết quả | Có thể đi từ mốc bằng index phù hợp |
| Chèn/xóa dữ liệu trước trang hiện tại | Dễ làm lệch offset | Ít bị ảnh hưởng bởi các thay đổi nằm trước mốc |
| Bắt buộc có sort ổn định | Rất nên có | **Bắt buộc** nếu muốn phân trang đúng |
| Đi đến trang thứ N bất kỳ | Dễ dùng page number | Không trực tiếp; thường đi tuần tự theo token |
| API phù hợp | Bảng nhỏ, ít biến động | Infinite scroll, activity feed, đơn hàng, log |
| Khi khóa sort bị sửa giữa trang | Vẫn có thể lệch | Vẫn có thể lặp/bỏ sót, cần chính sách dữ liệu |

Trong bài này, “cursor” của keyset có nghĩa là **token mang vị trí khóa sắp xếp**. Nó **khác** với **server-side cursor** của MongoDB driver, đối tượng nội bộ dùng để đọc kết quả theo batch. API keyset có thể dùng một truy vấn `find()` mới cho mỗi trang mà không cần giữ một server-side cursor mở qua nhiều HTTP request.

## 3. Bộ dữ liệu thực hành có khóa trùng nhau

Mở `mongosh` kết nối MongoDB và chạy trong database riêng:

~~~javascript
const lab = db.getSiblingDB("keyset_pagination_lab");

lab.orders.drop();

function order(idSuffix, code, date, status = "paid") {
  return {
    _id: ObjectId("0000000000000000000000" + idSuffix),
    tenantId: "T1",
    orderCode: code,
    createdAt: ISODate(date),
    status,
    amount: NumberInt(100 + parseInt(idSuffix, 16) * 10)
  };
}

lab.orders.insertMany([
  order("01", "O-101", "2026-05-01T10:00:00Z"),
  order("02", "O-102", "2026-05-02T10:00:00Z"),
  order("03", "O-103", "2026-05-02T10:00:00Z"),
  order("04", "O-104", "2026-05-03T10:00:00Z"),
  order("05", "O-105", "2026-05-03T10:00:00Z"),
  order("06", "O-106", "2026-05-03T10:00:00Z"),
  order("07", "O-107", "2026-05-04T10:00:00Z"),
  order("08", "O-108", "2026-05-05T10:00:00Z"),
  order("09", "O-109", "2026-05-05T10:00:00Z"),
  order("0a", "O-110", "2026-05-06T10:00:00Z", "pending"),
  order("0b", "O-111", "2026-05-06T10:00:00Z"),
  order("0c", "O-112", "2026-05-07T10:00:00Z")
]);
~~~

Các `_id` trên được tạo có chủ đích để thứ tự có thể đọc bằng phần đuôi. Đây là **dữ liệu minh họa**, không phải mẫu tạo ObjectId trong hệ thống thực. Trong ứng dụng, driver thường tạo ObjectId tự động hoặc sử dụng định danh duy nhất theo hợp đồng dữ liệu.

Đọc toàn bộ đơn `paid`:

~~~javascript
lab.orders.find(
  { tenantId: "T1", status: "paid" },
  { _id: 1, orderCode: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 });
~~~

Thứ tự dự kiến:

| Vị trí | orderCode | createdAt | Đuôi `_id` |
| ---: | --- | --- | --- |
| 1 | O-112 | 07/05 10:00 | 0c |
| 2 | O-111 | 06/05 10:00 | 0b |
| 3 | O-109 | 05/05 10:00 | 09 |
| 4 | O-108 | 05/05 10:00 | 08 |
| 5 | O-107 | 04/05 10:00 | 07 |
| 6 | O-106 | 03/05 10:00 | 06 |
| 7 | O-105 | 03/05 10:00 | 05 |
| 8 | O-104 | 03/05 10:00 | 04 |
| 9 | O-103 | 02/05 10:00 | 03 |
| 10 | O-102 | 02/05 10:00 | 02 |
| 11 | O-101 | 01/05 10:00 | 01 |

`O-110` không nằm trong kết quả vì có `status: "pending"`. Các ngày trong bảng dùng tháng 05 năm 2026, múi giờ UTC như chuỗi `ISODate`.

## 4. Trang đầu tiên: lấy và lưu mốc

Để đọc ba đơn đầu tiên, dùng:

~~~javascript
const pageSize = 3;

const firstPage = lab.orders.find(
  { tenantId: "T1", status: "paid" }
).sort({ createdAt: -1, _id: -1 })
 .limit(pageSize)
 .toArray();

firstPage.map(d => d.orderCode);
// ["O-112", "O-111", "O-109"]
~~~

Phần tử **cuối** của trang có:

~~~javascript
const last = firstPage[firstPage.length - 1];

printjson({
  orderCode: last.orderCode,
  createdAt: last.createdAt,
  _id: last._id
});
~~~

Mốc của trang kế tiếp là **`(createdAt của O-109, _id của O-109)`**. Không lấy `createdAt` của phần tử đầu; cũng không chỉ gửi ngày nếu nhiều bản ghi có cùng thời gian.

Lưu ý: trang đầu không cần cursor đầu vào, nhưng vẫn **phải dùng cùng sort** như các trang sau.

## 5. Trang kế tiếp với khóa ghép: điều kiện từ điển

### 5.1. Suy ra điều kiện đúng

Giả sử thứ tự sort là:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

Để lấy một document **nằm sau** `last`, có đúng hai trường hợp:

1. `createdAt` **nhỏ hơn** thời gian của `last`.
2. `createdAt` **bằng** thời gian của `last`, nhưng `_id` **nhỏ hơn** `last._id`.

Viết thành MongoDB filter:

~~~javascript
const after = {
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
};
~~~

Ghép với filter nghiệp vụ:

~~~javascript
const secondPage = lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
}).sort({ createdAt: -1, _id: -1 })
  .limit(pageSize)
  .toArray();

secondPage.map(d => d.orderCode);
// ["O-108", "O-107", "O-106"]
~~~

`O-108` có cùng `createdAt` với `O-109`, nhưng `_id` nhỏ hơn, nên phải xuất hiện ngay đầu trang tiếp theo. Nếu chỉ lọc `createdAt < last.createdAt`, **O-108 sẽ bị bỏ sót**.

### 5.2. Tại sao phải dùng so sánh nghiêm ngặt?

Để phân trang sau mốc, dùng `$lt` trong sort giảm dần, **không dùng `$lte`** cho cả hai khóa:

~~~javascript
// Không đúng cho trang sau: tài liệu mốc có thể xuất hiện lại.
{
  $or: [
    { createdAt: { $lte: last.createdAt } },
    { createdAt: last.createdAt, _id: { $lte: last._id } }
  ]
}
~~~

Với cách viết trên, bản ghi làm mốc có thể khớp và bị trả lại ở trang sau. Phải dùng **so sánh nghiêm ngặt** `<` hoặc `>` tùy chiều sort.

### 5.3. Không được dùng OR đơn giản cho hai điều kiện khóa

Ví dụ sai:

~~~javascript
// SAI: _id nhỏ hơn mốc không đủ, vì thời gian có thể mới hơn.
{
  $or: [
    { createdAt: { $lt: last.createdAt } },
    { _id: { $lt: last._id } }
  ]
}
~~~

Điều kiện thứ hai không bị ràng buộc bởi **createdAt bằng mốc**, vì vậy nó có thể lấy nhầm document có thời gian mới hơn nhưng `_id` nhỏ hơn. Thứ tự từ điển yêu cầu điều kiện so sánh khóa phụ **chỉ kích hoạt khi khóa chính bằng nhau**.

### 5.4. Trang tiếp theo sau trang thứ hai

Lấy phần tử cuối của trang 2:

~~~javascript
const lastPage2 = secondPage[secondPage.length - 1];

const thirdPage = lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $lt: lastPage2.createdAt } },
    {
      createdAt: lastPage2.createdAt,
      _id: { $lt: lastPage2._id }
    }
  ]
}).sort({ createdAt: -1, _id: -1 })
  .limit(pageSize)
  .toArray();

thirdPage.map(d => d.orderCode);
// ["O-105", "O-104", "O-103"]
~~~

Trang thứ ba vẫn bao gồm hai đơn cùng ngày 03/05 đứng sau mốc `O-106`. Đây là bằng chứng trực tiếp rằng **tie-breaker `_id`** giúp đi hết nhóm khóa trùng thay vì nhảy qua chúng.

## 6. Hàm phân trang tiến có thể tái sử dụng

Thay vì viết lại filter ở mỗi trang, có thể gói truy vấn thành một hàm chạy trong `mongosh`:

~~~javascript
const SORT_DESC = { createdAt: -1, _id: -1 };
const BASE_FILTER = { tenantId: "T1", status: "paid" };

function fetchNextPage(after = null, pageSize = 3) {
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw new Error("pageSize phải là số nguyên từ 1 đến 100");
  }

  const filter = { ...BASE_FILTER };

  if (after) {
    filter.$or = [
      { createdAt: { $lt: after.createdAt } },
      {
        createdAt: after.createdAt,
        _id: { $lt: after._id }
      }
    ];
  }

  // Đọc thêm 1 document để biết còn trang tiếp theo hay không.
  const fetched = lab.orders.find(filter)
    .sort(SORT_DESC)
    .limit(pageSize + 1)
    .toArray();

  const hasNextPage = fetched.length > pageSize;
  const items = fetched.slice(0, pageSize);
  const lastItem = items[items.length - 1];

  return {
    items,
    hasNextPage,
    nextCursor: hasNextPage && lastItem
      ? { createdAt: lastItem.createdAt, _id: lastItem._id }
      : null
  };
}
~~~

Chạy thử từng trang:

~~~javascript
const p1 = fetchNextPage(null, 3);
printjson(p1.items.map(o => o.orderCode));
// ["O-112", "O-111", "O-109"]

const p2 = fetchNextPage(p1.nextCursor, 3);
printjson(p2.items.map(o => o.orderCode));
// ["O-108", "O-107", "O-106"]

const p3 = fetchNextPage(p2.nextCursor, 3);
printjson(p3.items.map(o => o.orderCode));
// ["O-105", "O-104", "O-103"]

const p4 = fetchNextPage(p3.nextCursor, 3);
printjson(p4.items.map(o => o.orderCode));
// ["O-102", "O-101"]
~~~

Với dữ liệu ban đầu, trang 1–3 đều có `hasNextPage: true` và trang 4 có `hasNextPage: false`. Hàm chỉ tạo `nextCursor` khi còn trang tiếp theo, giúp client không tiếp tục yêu cầu vô ích.

### Vì sao lấy `pageSize + 1` bản ghi?

Nếu chỉ đọc đúng ba document, một trang có đúng ba phần tử **không cho biết** còn phần tử thứ tư hay không. Đọc thêm một:

~~~text
limit(4) -> [A, B, C, D]
trả cho client -> [A, B, C]
hasNextPage -> true
nextCursor -> khóa của C, không phải D
~~~

**Không lấy khóa của phần tử nhìn trước D làm cursor**. Vì D chưa được trả cho client, làm mốc D sẽ khiến client bỏ qua chính D.

Nếu kết quả chỉ có 0–3 phần tử thì `hasNextPage` là false tại thời điểm truy vấn. Khi dữ liệu thay đổi liên tục, đây chỉ là trạng thái quan sát được của lần đọc đó.

## 7. Phân trang lùi: đổi chiều điều kiện và đảo kết quả

Một API thường cần cả “Next” lẫn “Previous”. Với thứ tự hiển thị chuẩn:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Để tìm các bản ghi **đứng trước** phần tử đầu tiên của trang hiện tại, điều kiện ngược lại là:

~~~text
createdAt > first.createdAt
OR
(createdAt = first.createdAt AND _id > first._id)
~~~

Nhưng nếu muốn lấy **trang liền trước**, nên đọc theo **chiều tăng dần** để nhận những bản ghi gần mốc nhất trước, sau đó **đảo mảng kết quả** để hiển thị lại theo thứ tự giảm dần.

Ví dụ quay về trang trước từ trang 2:

~~~javascript
const firstPage2 = p2.items[0]; // O-108

const earlier = lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $gt: firstPage2.createdAt } },
    {
      createdAt: firstPage2.createdAt,
      _id: { $gt: firstPage2._id }
    }
  ]
}).sort({ createdAt: 1, _id: 1 })
  .limit(3)
  .toArray();

const previousPage = earlier.reverse();

previousPage.map(o => o.orderCode);
// ["O-112", "O-111", "O-109"]
~~~

Tại sao không giữ nguyên sort giảm dần khi tìm previous? Nếu có hàng nghìn bản ghi đứng trước mốc, `limit(3)` theo chiều giảm dần sẽ lấy **ba bản ghi đầu tiên của toàn bộ tập cũ**, chứ không phải **ba bản ghi gần trang hiện tại nhất**. Đổi sort sang tăng dần giúp chọn các bản ghi sát ranh giới trước, rồi đảo để trả đúng chiều UI.

### Hàm phân trang lùi có lookahead

~~~javascript
function fetchPreviousPage(before, pageSize = 3) {
  if (!before || !(before.createdAt instanceof Date)) {
    throw new Error("Thiếu cursor hợp lệ của phần tử đầu trang");
  }
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw new Error("pageSize phải nằm trong khoảng 1..100");
  }

  const filter = {
    ...BASE_FILTER,
    $or: [
      { createdAt: { $gt: before.createdAt } },
      {
        createdAt: before.createdAt,
        _id: { $gt: before._id }
      }
    ]
  };

  const fetched = lab.orders.find(filter)
    .sort({ createdAt: 1, _id: 1 })
    .limit(pageSize + 1)
    .toArray();

  const hasEarlierPage = fetched.length > pageSize;
  const items = fetched.slice(0, pageSize).reverse();
  const firstItem = items[0];

  return {
    items,
    hasEarlierPage,
    previousCursor: hasEarlierPage && firstItem
      ? { createdAt: firstItem.createdAt, _id: firstItem._id }
      : null
  };
}

const prev = fetchPreviousPage({
  createdAt: p2.items[0].createdAt,
  _id: p2.items[0]._id
}, 3);

printjson(prev.items.map(o => o.orderCode));
// ["O-112", "O-111", "O-109"]
~~~

Ở đây `hasEarlierPage: false` nếu trang trả về chính là trang đầu tiên của danh sách. Muốn UI quay lùi nhiều lần, token `before` phải được tạo từ **phần tử đầu của trang đang hiển thị**, không phải phần tử cuối. Với danh sách có nhiều trang, mỗi lần đọc lùi tiếp tục dùng phần tử đầu của nhóm kết quả vừa nhận.

### Phân biệt hai loại cursor của UI

| Nút | Mốc lấy từ trang hiện tại | Điều kiện với sort giảm dần | Sort dùng khi tìm |
| --- | --- | --- | --- |
| Next | Phần tử **cuối** | `(createdAt, _id) < mốc` | `{-1, -1}` |
| Previous | Phần tử **đầu** | `(createdAt, _id) > mốc` | `{1, 1}` rồi đảo |

Nên đặt tên rõ `after` và `before` hoặc `nextCursor` và `previousCursor`. Một cursor chỉ có cặp khóa nhưng thiếu ngữ nghĩa hướng rất dễ bị dùng sai ở API.

## 8. Tổng quát hóa: khóa ghép có hai hoặc nhiều trường

Tư duy then chốt của keyset là **so sánh từ điển**:

~~~text
sort theo (K1, K2, K3):
- so sánh K1
- nếu K1 bằng nhau, so sánh K2
- nếu K1 và K2 bằng nhau, so sánh K3
~~~

Khóa cuối phải bảo đảm phân biệt các tài liệu trong tập cần phân trang, chẳng hạn `_id` duy nhất. Nếu cả ba khóa vẫn trùng giữa hai document, thứ tự chưa được xác định hoàn toàn.

### 8.1. Hai trường đều giảm dần

Sort:

~~~javascript
{ score: -1, _id: -1 }
~~~

Trang sau mốc `(scoreLast, idLast)`:

~~~javascript
{
  $or: [
    { score: { $lt: scoreLast } },
    { score: scoreLast, _id: { $lt: idLast } }
  ]
}
~~~

### 8.2. Một trường giảm, một trường tăng

Sort:

~~~javascript
{ score: -1, _id: 1 }
~~~

Trang sau:

~~~javascript
{
  $or: [
    { score: { $lt: scoreLast } },
    { score: scoreLast, _id: { $gt: idLast } }
  ]
}
~~~

Vì `score` giảm dần nên score nhỏ hơn nằm sau. Nhưng `_id` tăng dần nên khi score bằng nhau, `_id` lớn hơn lại nằm sau. **Không chọn dấu `<`/`>` theo một công thức cứng cho tất cả trường**; phải dựa trên hướng sort thực tế của từng khóa.

### 8.3. Ba trường: biểu thức OR gồm ba nhánh

Sort:

~~~javascript
{ priority: -1, createdAt: -1, _id: -1 }
~~~

Mốc `(p, t, id)`. Điều kiện trang sau:

~~~javascript
{
  $or: [
    { priority: { $lt: p } },
    {
      priority: p,
      createdAt: { $lt: t }
    },
    {
      priority: p,
      createdAt: t,
      _id: { $lt: id }
    }
  ]
}
~~~

Đây là quy tắc mở rộng chung:

1. Nhánh 1: khóa chính đã nằm sau mốc.
2. Nhánh 2: khóa chính bằng mốc và khóa thứ hai nằm sau.
3. Nhánh 3: hai khóa đầu bằng mốc, khóa thứ ba nằm sau.
4. Tiếp tục như vậy nếu có nhiều khóa hơn.

Số nhánh tăng theo số trường sort; vì thế nên giữ tổ hợp khóa **đủ ổn định nhưng không dài quá cần thiết**.

### 8.4. Sắp xếp theo chuỗi và collation

Nếu sort theo `name` rồi `_id`:

~~~javascript
.find({})
.sort({ name: 1, _id: 1 })
~~~

thì điều kiện cursor phải so sánh `name` theo **cùng quy tắc collation** dùng khi sort. Với collation khác nhau, so sánh chữ hoa, dấu và các chuỗi có thể khác thứ tự dự kiến.

Ví dụ với collation:

~~~javascript
const collation = { locale: "en", strength: 2 };

lab.customers.find({
  $or: [
    { name: { $gt: lastName } },
    { name: lastName, _id: { $gt: lastId } }
  ]
}).collation(collation)
  .sort({ name: 1, _id: 1 })
  .limit(20);
~~~

Ví dụ này dùng collection `customers` giả định. Với triển khai thực tế, cần thiết kế index có **collation tương thích**, quyết định cách xử lý những tên được collation xem là tương đương và dùng khóa phụ độc lập để phá hòa. Khi cần thứ tự byte ổn định cho API hoặc khóa kinh doanh, có thể lưu **sortKey chuẩn hóa** và sử dụng quy tắc so sánh đã thống nhất.

## 9. Compound index hỗ trợ filter và sort

Keyset chỉ có lợi thế đáng kể nếu truy vấn sử dụng index phù hợp với **lọc nghiệp vụ và thứ tự**.

Với filter:

~~~javascript
{ tenantId: "T1", status: "paid" }
~~~

và sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

có thể tạo compound index:

~~~javascript
lab.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Ý tưởng thứ tự khóa index:

~~~text
tenantId  (equality)
  └── status  (equality)
        └── createdAt DESC  (thứ tự hiển thị)
              └── _id DESC  (tie-breaker)
~~~

Khi `tenantId` và `status` được giới hạn bằng điều kiện bằng, phần index tiếp theo có thứ tự thích hợp cho truy vấn theo `createdAt` và `_id`. MongoDB có thể dùng index để tìm vị trí gần mốc và đọc tiếp, thay vì bỏ qua số lượng lớn kết quả như offset sâu.

**Không phải index nào có đủ tên trường cũng tối ưu.** Thứ tự trường, điều kiện equality/range, hướng sort, collation, phân bố dữ liệu và cách optimizer xử lý `$or` đều ảnh hưởng execution plan.

### 9.1. Kiểm tra bằng explain

~~~javascript
const lastDoc = firstPage[firstPage.length - 1];

lab.orders.find({
  tenantId: "T1",
  status: "paid",
  $or: [
    { createdAt: { $lt: lastDoc.createdAt } },
    {
      createdAt: lastDoc.createdAt,
      _id: { $lt: lastDoc._id }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(4)
.explain("executionStats");
~~~

Các điểm nên quan sát trong output:

- `winningPlan` và các stage thực thi phù hợp phiên bản MongoDB.
- `IXSCAN` hoặc cấu trúc index scan có được sử dụng không.
- Có `SORT` ở bộ nhớ sau khi đọc hay không.
- `totalKeysExamined` so với `nReturned`.
- `totalDocsExamined` và số kết quả trả về.
- Độ chọn lọc của `tenantId`, `status` và phạm vi cursor.

Với bộ dữ liệu lab chỉ 12 document, MongoDB có thể chọn `COLLSCAN` vì quét toàn collection quá nhỏ còn rẻ. Điều đó không chứng minh index vô ích cho tập dữ liệu sản xuất.

### 9.2. Chọn index theo workload

Nếu có các màn hình khác nhau:

- Danh sách đơn của một tenant và trạng thái: `tenantId, status, createdAt, _id`.
- Danh sách mọi trạng thái của một tenant: `tenantId, createdAt, _id`.
- Danh sách đơn của một khách: `tenantId, customerId, createdAt, _id`.

Mỗi nhóm có thể cần index riêng hoặc một phương án dùng chung được cân nhắc. Không nên tạo mọi tổ hợp có thể có vì index tiêu tốn dung lượng, RAM và chi phí duy trì khi ghi.

### 9.3. Index không làm dữ liệu giữa các trang trở nên bất biến

Index giúp truy cập dữ liệu hiệu quả theo thứ tự, nhưng không khóa tập kết quả qua nhiều request. Nếu yêu cầu “xuất chính xác cùng một tập kết quả tại một thời điểm”, cần giải pháp nhất quán riêng, không chỉ dựa vào compound index.

## 10. Cursor token dành cho REST API

Trong `mongosh` ta có thể truyền trực tiếp object gồm `Date` và `ObjectId`. Nhưng một REST API thường nhận cursor từ URL:

~~~text
GET /orders?limit=20
GET /orders?limit=20&after=<opaque-token>
GET /orders?limit=20&before=<opaque-token>
~~~

Client không cần biết token chứa gì; nó chỉ gửi lại token do server trả.

Ví dụ response:

~~~json
{
  "items": [
    { "id": "00000000000000000000000c", "orderCode": "O-112" },
    { "id": "00000000000000000000000b", "orderCode": "O-111" },
    { "id": "000000000000000000000009", "orderCode": "O-109" }
  ],
  "pageInfo": {
    "hasNextPage": true,
    "nextCursor": "opaque-string-from-server"
  }
}
~~~

Đoạn token là mô tả giao diện API; giá trị thực phải được tạo theo hợp đồng của backend.

### 10.1. Payload của cursor nên chứa gì?

Một cấu trúc minh họa:

~~~json
{
  "version": 1,
  "direction": "after",
  "createdAt": "2026-05-05T10:00:00.000Z",
  "id": "000000000000000000000009",
  "sort": "createdAt_desc_id_desc",
  "filterKey": "tenant=T1;status=paid"
}
~~~

Ý nghĩa:

- `version`: phiên bản định dạng token để hỗ trợ thay đổi hợp đồng.
- `direction`: phân biệt next/previous nếu API dùng token theo hướng.
- `createdAt`: thời gian dưới dạng **ISO 8601 UTC**.
- `id`: ObjectId dạng **24 chữ số hexadecimal**.
- `sort`: nhận diện thứ tự, tránh dùng token của màn hình sort khác.
- `filterKey`: gắn cursor với bộ lọc mà server đang áp dụng.

Một số API còn có `expiresAt` hoặc giá trị ràng buộc user/tenant. Với filter lớn, có thể dùng fingerprint/hash của cấu hình lọc đã được canonicalize, nhưng phải kiểm tra lại quyền và filter thực tế ở server, không chỉ tin vào chuỗi do client gửi.

### 10.2. Mã hóa và giải mã trong Node.js

Ví dụ đơn giản bên dưới minh họa chuyển payload sang **base64url** (Node.js hỗ trợ `Buffer`). Base64url chỉ là **encoding**, không phải mã hóa bảo mật hay chữ ký.

~~~javascript
function encodeCursor(cursor) {
  const payload = {
    version: 1,
    direction: cursor.direction,
    createdAt: cursor.createdAt.toISOString(),
    id: cursor._id.toHexString(),
    sort: "createdAt_desc_id_desc"
  };

  return Buffer.from(JSON.stringify(payload), "utf8")
    .toString("base64url");
}

function decodeCursor(raw) {
  const payload = JSON.parse(
    Buffer.from(raw, "base64url").toString("utf8")
  );

  if (payload.version !== 1 ||
      payload.sort !== "createdAt_desc_id_desc" ||
      !["after", "before"].includes(payload.direction)) {
    throw new Error("Cursor không tương thích");
  }

  if (typeof payload.createdAt !== "string" ||
      !Number.isFinite(Date.parse(payload.createdAt)) ||
      !/^[a-f0-9]{24}$/i.test(payload.id)) {
    throw new Error("Cursor không hợp lệ");
  }

  return {
    direction: payload.direction,
    createdAt: new Date(payload.createdAt),
    _id: new ObjectId(payload.id)
  };
}
~~~

Để dùng với MongoDB Node.js Driver, cần import `ObjectId` từ package `mongodb`. Trong snippet, `ObjectId` được giả định đã có trong scope. Mã trên chỉ kiểm tra định dạng cơ bản, **chưa xác thực chữ ký, TTL, phạm vi tenant, giá trị filter và giới hạn kích thước token**.

Nếu cursor đi qua môi trường không tin cậy (trình duyệt, URL, client ngoài), backend cần cân nhắc **HMAC/chữ ký** để ngăn sửa mốc trái phép, giới hạn độ dài token, xử lý base64/JSON lỗi, và không đưa thông tin nhạy cảm vào token có thể giải mã. HMAC không thay thế **authentication/authorization**: mọi request vẫn phải áp dụng lại quyền xem tài liệu.

### 10.3. Không làm mất kiểu BSON khi tái tạo cursor

Đối với ví dụ sort theo `createdAt` và `_id`:

- `createdAt` phải được tái tạo thành **Date**, không truyền chuỗi ISO vào điều kiện so sánh với trường BSON Date.
- `_id` phải được tái tạo thành **ObjectId**, không truyền hex string khi collection lưu BSON ObjectId.
- Nếu dùng `Decimal128`, `Long` hoặc các kiểu khóa khác, token phải giữ giá trị chính xác và bộ giải mã phải khôi phục đúng BSON type.
- Không chuyển số nguyên 64 bit lớn qua JavaScript `Number` vì có thể mất độ chính xác trước khi tạo lại khóa.

Một cursor tưởng như đúng nhưng chứa **sai kiểu BSON** có thể làm điều kiện `$lt`/`$gt` không khớp như mong đợi.

## 11. Ứng dụng Java/Spring Data MongoDB

Trong Java, bạn có thể tạo filter theo thứ tự từ điển bằng `Criteria` và `Query` của Spring Data MongoDB. Ví dụ sau minh họa **trang sau** theo sort giảm dần.

Giả sử entity có:

~~~java
@Document("orders")
public class Order {
    @Id
    private ObjectId id;

    private String tenantId;
    private String status;
    private Date createdAt;

    // getters/setters...
}
~~~

Xây dựng `Query`:

~~~java
import java.util.Date;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Query buildNextPageQuery(
        String tenantId,
        String status,
        Date lastCreatedAt,
        ObjectId lastId,
        int pageSize
) {
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be 1..100");
    }

    Criteria base = Criteria.where("tenantId").is(tenantId)
        .and("status").is(status);

    Criteria after = new Criteria().orOperator(
        Criteria.where("createdAt").lt(lastCreatedAt),
        new Criteria().andOperator(
            Criteria.where("createdAt").is(lastCreatedAt),
            Criteria.where("_id").lt(lastId)
        )
    );

    return new Query(
        new Criteria().andOperator(base, after)
    )
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    ))
    .limit(pageSize + 1);
}
~~~

Gọi `mongoTemplate.find(query, Order.class)` để lấy `pageSize + 1` item, tách phần tử lookahead, và tạo cursor từ **phần tử cuối thực sự trả cho client**. Khi ứng dụng không truyền mốc (trang đầu), chỉ cần query `base` và sort tương tự, bỏ `after`.

Ví dụ này dùng Spring Data MongoDB làm lớp ánh xạ; cú pháp có thể được điều chỉnh theo phiên bản Spring Data và mô hình entity thực tế. Điều quan trọng nhất là **filter phải tương ứng chính xác với sort**.

**Với ứng dụng đa tenant**, `tenantId` phải được xác định từ ngữ cảnh đã xác thực và được ràng buộc trong mọi request, kể cả khi cursor token có chứa thông tin tenant. Không đọc tenant từ token rồi tự coi đó là bằng chứng cấp quyền.

## 12. Dữ liệu thay đổi giữa các trang: những giới hạn cần hiểu

### 12.1. Chèn document mới trước mốc

Người dùng đã nhận trang đầu:

~~~text
O-112, O-111, O-109
cursor = (05/05, id 09)
~~~

Sau đó hệ thống chèn một đơn mới ngày 08/05. Trang sau mốc cũ **không tự hiển thị** đơn mới ở đầu danh sách, bởi điều kiện keyset chỉ tìm bản ghi **sau** `(05/05, id 09)`.

Đây thường là hành vi mong muốn của **infinite scroll**: người dùng tiếp tục đi xuống các bản ghi cũ, không bị trang mới “đẩy” vị trí. Nếu muốn thấy đơn mới, UI có thể cung cấp nút **Làm mới** hoặc tải lại từ trang đầu.

### 12.2. Chèn document mới sau mốc

Nếu có một document mới với `createdAt` cũ hơn mốc hiện tại, nó có thể xuất hiện trong trang kế tiếp. Vì keyset **không phải snapshot cố định**, tập dữ liệu của phiên cuộn có thể thay đổi khi ứng dụng ghi dữ liệu lùi thời gian, import lịch sử hoặc sửa timestamp.

### 12.3. Xóa document trước mốc

Với offset, xóa một bản ghi trước vị trí skip có thể khiến các phần tử dịch lên, dẫn đến bỏ qua một bản ghi. Với keyset, điều kiện tiếp tục dựa trên **giá trị mốc cụ thể**, nên xóa những bản ghi đứng trước mốc thường không làm vị trí seek bị lệch theo cùng cách đó.

Nếu chính document mốc bị xóa, **cursor vẫn có thể dùng được** vì token đã mang cặp khóa; filter không cần phải tìm lại document mốc trong collection.

### 12.4. Cập nhật khóa sắp xếp làm document đổi vị trí

Đây là giới hạn quan trọng của keyset. Nếu sort theo `updatedAt`, mỗi lần cập nhật đơn hàng có thể làm nó chuyển lên đầu danh sách. Một document chưa được đọc có thể di chuyển **vượt qua mốc**, làm người dùng bỏ sót; document đã đọc cũng có thể di chuyển xuống sau mốc và xuất hiện lại.

Vì vậy, khi xây dựng keyset pagination, hãy ưu tiên khóa có tính **ổn định hoặc bất biến** trong vòng đời của document, ví dụ:

~~~text
createdAt + _id
sequence + _id
businessDate + uniqueId (nếu businessDate không đổi)
~~~

Trường `updatedAt` phù hợp cho màn hình muốn sắp xếp theo hoạt động mới nhất, nhưng phải chấp nhận hành vi danh sách chuyển động hoặc thiết kế thêm cơ chế snapshot/đồng bộ.

### 12.5. Thứ tự ổn định khác snapshot nhất quán

Một truy vấn từng trang bình thường không tự tạo một **snapshot nhất quán xuyên nhiều HTTP request**. Khi nghiệp vụ yêu cầu xuất chính xác toàn bộ dữ liệu “tại 10:00:00”, keyset một mình chưa đủ.

Các lựa chọn tùy yêu cầu:

- Lưu một **ngưỡng chặn trên** (high-water mark) trong token để không nhận những bản ghi có khóa sắp xếp mới hơn ngưỡng ban đầu.
- Thiết kế cột `createdAt` hoặc sequence **bất biến**, gắn một phiên export và cố định tập bản ghi được phép xuất.
- Tạo snapshot/materialized export riêng hoặc dùng cơ chế đọc có điểm thời gian nhất quán khi MongoDB deployment, session và read concern phù hợp.
- Với lịch sử có thao tác chỉnh sửa/xóa, thiết kế mô hình versioning hoặc lịch sử bất biến nếu nghiệp vụ đòi hỏi tái tạo trạng thái quá khứ.

High-water mark giúp hạn chế một loại biến động nhưng **không tự đóng băng dữ liệu**: document nằm trong ngưỡng vẫn có thể bị cập nhật/xóa và các bản ghi mới có timestamp cũ vẫn có thể xuất hiện. Đừng quảng bá nó như thay thế một snapshot thực thụ.

## 13. Kiểu dữ liệu, null, collation và uniqueness

### 13.1. Trường sort phải có giá trị và kiểu nhất quán

Nếu một số document thiếu `createdAt`, một số có `createdAt: null` và số khác là BSON Date, MongoDB sẽ sắp xếp theo quy tắc so sánh BSON types. Điều kiện seek sử dụng `$lt`/`$gt` có thể không thể hiện đúng mong muốn nghiệp vụ khi type bị trộn.

Với API cần thứ tự rõ ràng, nên:

1. Quy định `createdAt` là trường **bắt buộc** trong schema.
2. Quy định nó phải là **BSON Date**.
3. Backfill dữ liệu cũ trước khi bật phân trang ổn định.
4. Quyết định rõ có phân trang document thiếu khóa hay loại chúng bằng filter.

Có thể dùng collection validation với `$jsonSchema`:

~~~javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["createdAt", "status", "tenantId"],
      properties: {
        createdAt: { bsonType: "date" },
        status: { bsonType: "string" },
        tenantId: { bsonType: "string" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Khối `collMod` trên là **ví dụ về quy tắc thiết kế**, không cần chạy trên collection lab nếu muốn giữ validator hiện tại; nó giả định database đang chọn đúng collection `orders`. Trong môi trường thực, thay validator phải xem xét schema đang có và dữ liệu legacy trước khi triển khai.

### 13.2. Trường phụ phải thực sự phân biệt các bản ghi

`_id` thường là lựa chọn tie-breaker vì mặc định MongoDB yêu cầu mỗi document có một `_id`, và ứng dụng thường dùng định danh duy nhất. Tuy nhiên với thiết kế **sharded collection**, các điều kiện đảm bảo uniqueness toàn cục của `_id` phụ thuộc cấu hình shard key và ràng buộc unique index. Nếu không chắc một field là duy nhất trong tập kết quả, hãy thiết kế composite key có tính duy nhất theo phạm vi truy vấn hoặc dùng định danh được hệ thống bảo đảm.

### 13.3. ObjectId không tự chứng minh thứ tự thời gian tuyệt đối

MongoDB `ObjectId` có thành phần timestamp và có xu hướng tăng theo thời gian trong nhiều trường hợp, nhưng **không được coi là đồng hồ chính xác và duy nhất** cho toàn hệ thống. Các client có thể có đồng hồ khác nhau; ObjectId có độ phân giải timestamp theo giây và giá trị còn chứa phần ngẫu nhiên/bộ đếm.

Nếu cần sort theo **thời điểm tạo nghiệp vụ**, dùng `createdAt` được định nghĩa rõ; thêm `_id` để phá hòa. Không thay thế `createdAt` bằng `_id` nếu yêu cầu sản phẩm thực sự cần một timestamp chính xác theo quy ước riêng.

### 13.4. Collation phải nhất quán giữa index, sort và cursor

Khi sort chuỗi như `customerName`, API phải thống nhất locale, strength và cách chuẩn hóa. Filter “nằm sau” phải đánh giá theo **cùng thứ tự mà sort sử dụng**. Index có collation khác có thể không phục vụ được cùng sort hiệu quả. Nếu chuyển collation giữa hai request nhưng giữ cursor cũ, token có thể dẫn tới thứ tự sai.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| Một đơn bị lặp ở trang sau | Dùng `$lte`/`$gte`, gồm cả bản ghi mốc | Dùng so sánh nghiêm ngặt `$lt`/`$gt` |
| Đơn cùng timestamp bị bỏ sót | Chỉ lưu `createdAt` trong cursor | Lưu cả `createdAt` và `_id` |
| Trang sau trả sai thứ tự | Filter seek không khớp hướng `sort` | Viết lại điều kiện từ điển theo từng khóa |
| Trang trước nhảy về đầu danh sách | Tìm `before` nhưng vẫn dùng sort giảm dần rồi limit | Đổi chiều sort để lấy phần gần mốc, sau đó đảo mảng |
| Truy vấn vẫn chậm | Compound index chưa phù hợp filter/sort | Kiểm tra index và `explain("executionStats")` |
| Cursor chứa chuỗi ngày nhưng collection chứa Date | Sai BSON type khi tạo filter | Giải mã ISO thành Date |
| Cursor chứa hex string thay vì ObjectId | So sánh sai kiểu `_id` | Khôi phục ObjectId đúng kiểu |
| Client đổi status/tenant giữa trang | Cursor cũ thuộc tập kết quả khác | Gắn token với filter; áp lại quyền và filter hiện hành |
| Token bị sửa hoặc token quá lớn | Chưa xác thực dữ liệu đầu vào | Giới hạn độ dài, xác thực schema, ký HMAC khi cần |
| Document biến mất/lặp khi cuộn | Field sort bị sửa trong lúc phân trang | Ưu tiên khóa bất biến, thiết kế cơ chế snapshot nếu cần |
| Không thấy dữ liệu mới được chèn ở đầu | Keyset tiếp tục đọc sau mốc cũ | Cung cấp thao tác refresh từ đầu |
| `hasNextPage` sai | Dùng khóa của phần tử lookahead làm mốc hoặc chỉ đọc đúng pageSize | Đọc `pageSize + 1`, trả pageSize, mốc là phần tử cuối đã trả |
| Có thứ tự nhưng không ổn định | Khóa sort bị trùng và không có tie-breaker | Thêm trường cuối duy nhất vào sort và cursor |
| Dùng thứ tự tên với nhiều collation khác nhau | So sánh chuỗi không nhất quán | Giữ collation và index cùng hợp đồng |
| Muốn nhảy thẳng trang 500 | Keyset cần mốc của trang tương ứng | Cân nhắc offset, bookmark, anchor index hoặc thiết kế UX khác |

## 15. Bài thực hành

### Bài 1 — Chỉ có thời gian thì sai ở đâu?

Dùng dữ liệu mục 3, lấy trang đầu ba phần tử với sort `createdAt: -1`, sau đó viết điều kiện `createdAt < last.createdAt`. So sánh kết quả với truy vấn có `_id` làm tie-breaker.

Kết luận cần chỉ ra: khi trang đầu kết thúc ở `O-109` ngày 05/05, document `O-108` có **cùng timestamp** sẽ bị bỏ qua nếu filter chỉ dùng `createdAt < 05/05`.

### Bài 2 — Tự viết trang thứ hai

Với thứ tự:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

và mốc `O-109`, hãy viết `$or` theo hai nhánh để lấy ba đơn kế tiếp. Kết quả đúng:

~~~text
O-108, O-107, O-106
~~~

Giải thích vì sao cần phép so sánh `_id < last._id` ở nhánh thời gian bằng nhau.

### Bài 3 — Đọc liên tục đến hết danh sách

Dùng hàm `fetchNextPage()` ở mục 6 và lặp cho đến khi `nextCursor = null`. Với `pageSize = 3` và 11 đơn paid, số document ở từng trang lần lượt là:

~~~text
Trang 1: 3
Trang 2: 3
Trang 3: 3
Trang 4: 2
~~~

Hãy in tất cả `orderCode` theo thứ tự và đối chiếu với `find().sort({createdAt:-1,_id:-1})`.

### Bài 4 — Phân trang lùi

Từ trang thứ hai, dùng **phần tử đầu O-108** làm mốc `before`, điều kiện `$gt` theo thứ tự từ điển và sort tăng dần. Sau khi đảo mảng kết quả, trang trước phải là:

~~~text
O-112, O-111, O-109
~~~

Thử cố tình bỏ bước đảo mảng và giải thích vì sao thứ tự hiển thị sẽ ngược UI.

### Bài 5 — Khóa ghép hỗn hợp chiều

Giả sử một bảng xếp hạng dùng sort:

~~~javascript
{ score: -1, userId: 1 }
~~~

Hãy viết điều kiện trang sau mốc `(score, userId) = (90, "u07")`.

Lời giải:

~~~javascript
{
  $or: [
    { score: { $lt: 90 } },
    { score: 90, userId: { $gt: "u07" } }
  ]
}
~~~

Điểm bằng 90 nhưng `userId` lớn hơn `"u07"` phải nằm **sau** theo chiều tăng dần của khóa thứ hai. Chỉ đổi dấu comparator của `userId`, không đổi dấu của `score`.

### Bài 6 — Mở rộng ba khóa

Sắp xếp:

~~~javascript
{ priority: -1, createdAt: -1, _id: -1 }
~~~

Hãy viết điều kiện trang tiếp theo bằng ba nhánh `$or`. Mỗi nhánh cần giữ nguyên các khóa trước đó bằng mốc và so sánh nghiêm ngặt khóa hiện tại.

### Bài 7 — Compound index

Tạo index:

~~~javascript
lab.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Dùng `explain("executionStats")` với query trang sau. Quan sát loại scan, số keys/docs examined và sort stage; giải thích vì sao tập chỉ 12 document không đủ kết luận về lợi ích index trong môi trường sản xuất.

### Bài 8 — Dữ liệu thay đổi sau trang đầu

Giả lập một đơn mới có thời gian `2026-05-08T10:00:00Z` xuất hiện sau khi đã lấy trang đầu. Khi dùng `after` của `O-109`, bạn có nhìn thấy đơn mới không? Tại sao? Nếu UI muốn hiển thị đơn mới nhất, chức năng nào nên được cung cấp?

### Bài 9 — Thiết kế API cursor

Thiết kế schema token có `createdAt`, `id`, `direction`, `sort`, `version`. Mô tả cách:

1. Kiểm tra chữ ký và hạn dùng nếu dùng signed token.
2. Chuyển chuỗi ngày về Date, chuỗi ID về ObjectId.
3. Áp lại filter và quyền từ phiên đăng nhập.
4. Đọc thêm một phần tử để tính `hasNextPage`.
5. Tạo token mới từ **phần tử cuối được trả**.

Giải thích vì sao chỉ encode base64 không giúp bảo vệ token khỏi bị sửa.

## 16. Nguyên tắc thiết kế cần ghi nhớ

Phân trang theo khóa hiệu quả khi **thứ tự sắp xếp rõ ràng và có điểm bắt đầu chính xác**. Trong MongoDB, một mô hình rất phổ biến là:

~~~javascript
// Sort cố định
{ createdAt: -1, _id: -1 }

// Điều kiện "after" cho trang tiếp theo
{
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
}
~~~

Khi triển khai:

1. **Luôn có tie-breaker duy nhất** trong sort, thường là `_id`.
2. **Cursor chứa tất cả khóa sort**, giữ nguyên kiểu BSON và chiều sort.
3. **Filter seek dùng so sánh từ điển**: khóa trước bằng mốc mới được so sánh khóa sau.
4. **Dùng phép so sánh nghiêm ngặt** để không trả lại document mốc.
5. **Trang lùi đổi chiều sort và đảo lại kết quả** để lấy đúng các bản ghi gần mốc.
6. **Ghép compound index** theo filter equality và thứ tự sort.
7. **Ưu tiên trường sắp xếp bất biến** nếu muốn tránh chuyển vị trí khi dữ liệu cập nhật.
8. **Ràng buộc cursor với filter, sort và quyền truy cập**, kiểm tra input và token phía server.
9. **Không đồng nhất thứ tự ổn định với snapshot**: các lần đọc vẫn có thể nhìn thấy tập dữ liệu thay đổi.
10. **Giữ đúng kỳ vọng UX**: keyset phù hợp Next/Previous và infinite scroll; nhảy tới trang bất kỳ cần thiết kế bổ sung.

### Tài liệu tham khảo MongoDB chính thức

- [cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/) — chi phí skip ở offset sâu và lưu ý sort có khóa duy nhất.
- [cursor.sort()](https://www.mongodb.com/docs/manual/reference/method/cursor.sort/) — cú pháp sort và tính ổn định với các khóa trùng.
- [cursor.limit()](https://www.mongodb.com/docs/manual/reference/method/cursor.limit/) — giới hạn số document trả về.
- [Comparison Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-comparison/) — `$lt`, `$lte`, `$gt`, `$gte` và `$eq`.
- [`$or` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/or/) — kết hợp các nhánh điều kiện.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — nhiều khóa index và thứ tự truy cập.
- [Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/) — liên hệ index và sort.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — đọc execution plan và chi phí truy vấn.
