# Đọc tập dữ liệu lớn khi dữ liệu có thể thay đổi giữa các lượt

Trong MongoDB, một ứng dụng có thể phải đọc hàng triệu document trong khi các tiến trình khác liên tục thêm, sửa hoặc xóa dữ liệu. Người dùng đọc trang đầu của danh sách đơn hàng, sau đó nhấn “Trang tiếp”. Giữa hai request, một đơn hàng mới được tạo hoặc một đơn hàng cũ đổi trạng thái. Nếu không định nghĩa rõ cách phân trang, kết quả có thể **lặp document, bỏ sót document hoặc không phản ánh đúng thời điểm nghiệp vụ mong muốn**.

Vấn đề này xuất hiện ở nhiều hệ thống:

- Giao diện hiển thị 20 đơn hàng mới nhất khi các đơn mới liên tục được tạo.
- API trả danh sách khách hàng theo nhiều trang; tài khoản có thể bị xóa mềm giữa các lượt.
- Job xuất dữ liệu lớn cần chạy hàng giờ và có khả năng tiếp tục sau khi process bị dừng.
- Worker cần xử lý mỗi giao dịch theo thứ tự ID, nhưng các document liên tục được cập nhật.
- Dịch vụ search cần tải dữ liệu ban đầu rồi theo dõi các thay đổi tiếp theo mà không bỏ mất sự kiện.

MongoDB cung cấp **cursor**, `batchSize()`, `skip()/limit()`, truy vấn theo **khóa tiếp nối (keyset/seek pagination)**, read concern, transaction và change streams. Không có một lựa chọn duy nhất phù hợp với mọi yêu cầu. Trước khi chọn kỹ thuật, phải xác định **muốn xem dữ liệu đang sống hay muốn cố định một ảnh chụp dữ liệu tại một mốc**.

## 1. Phân biệt ba loại mục tiêu đọc

Ba nhu cầu trông giống nhau ở tầng API nhưng đòi hỏi mức đảm bảo khác nhau.

### 1.1. Xem danh sách sống (live browsing)

Người dùng cuộn danh sách bài viết hoặc hóa đơn. Khi cuộn đến cuối trang 1, họ muốn nhận các bản ghi nằm sau bản ghi cuối đã xem. Nếu có bản ghi mới xuất hiện ở đầu danh sách, họ có thể bấm “Làm mới” để nhìn thấy nó.

Mục tiêu chính:

- Trả nhanh các trang liên tiếp.
- Giảm hiện tượng trùng record do trang bị dịch vị trí.
- Giữ trải nghiệm mượt và không tải toàn bộ collection.
- Chấp nhận dữ liệu có thể thay đổi giữa hai request.

Với tình huống này, **keyset pagination với sort ổn định** thường thích hợp.

### 1.2. Quét theo lô và có khả năng tiếp tục (resumable scan)

Worker cần đọc hai triệu document để chuyển đổi dữ liệu. Process có thể crash ở document thứ 700.000, nên phải lưu checkpoint để khởi động lại.

Mục tiêu chính:

- Không phải đọc lại tất cả từ đầu sau crash.
- Biết document nào đã xử lý an toàn.
- Có cơ chế retry không nhân đôi tác dụng nghiệp vụ.
- Xác định record phát sinh trong khi quét có thuộc phạm vi công việc không.

Với tình huống này, thường dùng **keyset theo khóa bất biến + checkpoint + idempotency**, đôi khi kèm **upper watermark** giới hạn miền khóa.

### 1.3. Đọc nhất quán tại một thời điểm (snapshot export)

Báo cáo yêu cầu “mọi đơn hàng đã thanh toán đúng tại 00:00 ngày cuối tháng”. Document bị sửa sau thời điểm này không được làm thay đổi số liệu của báo cáo.

Mục tiêu chính:

- Các lần đọc phải quan sát **cùng một trạng thái logic**.
- Không trộn bản ghi cũ với phiên bản mới từ những thời điểm khác nhau.
- Có khả năng giải thích chính xác mốc dữ liệu được chốt.

Tình huống này cần **snapshot read/transaction phù hợp hoặc một dataset đã được materialize cố định**. Chỉ thêm `sort()` và `limit()` không đủ.

| Mục tiêu | Kỹ thuật chính | Điều không tự đảm bảo |
|---|---|---|
| Live browsing | Seek pagination | Snapshot cố định |
| Resumable scan | Seek + checkpoint | Exactly-once nghiệp vụ nếu không có idempotency |
| Bounded scan | Seek + watermark | Không bị update/delete trong miền khóa |
| Snapshot export | Snapshot hoặc dataset bất biến | Giữ snapshot vô hạn mà không có chi phí |
| Đồng bộ liên tục | Initial scan + change streams | Xử lý event exactly-once mà không có cơ chế riêng |

## 2. MongoDB cursor khác một trang API như thế nào?

Khi thực hiện `find()`, MongoDB có thể trả một **batch kết quả ban đầu**, sau đó client lấy thêm batch bằng cơ chế `getMore`. Driver thường quản lý các lượt trao đổi đó qua một đối tượng cursor.

Ví dụ trong `mongosh`:

```javascript
const cursor = db.orders.find(
  { tenantId: "T-A", status: "PAID" },
  { _id: 1, createdAt: 1, total: 1 }
)
.sort({ createdAt: 1, _id: 1 })
.batchSize(200);

try {
  while (cursor.hasNext()) {
    const order = cursor.next();
    print(order._id);
  }
} finally {
  cursor.close();
}
```

Điểm cần hiểu:

- `batchSize(200)` yêu cầu kích thước batch mong muốn; batch thực tế còn chịu giới hạn kích thước message và hành vi server/driver.
- `hasNext()` có thể khiến driver lấy thêm batch nếu đã tiêu thụ batch hiện tại.
- Ứng dụng chỉ giữ một phần kết quả trong bộ nhớ, thay vì đưa tất cả vào mảng.
- `cursor.close()` giúp giải phóng tài nguyên server/client khi không cần nữa.

**Batch của MongoDB không đồng nghĩa với page của API.** API trả 20 record có thể dùng một hoặc nhiều batch nội bộ. Ngược lại, một batch có thể chứa nhiều record hơn page mà ứng dụng muốn trả.

### 2.1. Vì sao không nên dùng `toArray()` cho tất cả dữ liệu?

```javascript
// Rủi ro trên collection rất lớn:
const allOrders = db.orders.find({ tenantId: "T-A" }).toArray();
```

Lệnh trên yêu cầu thu tất cả kết quả vào bộ nhớ phía client. Với hàng triệu record có document lớn, ứng dụng có thể dùng quá nhiều RAM hoặc tăng độ trễ đáng kể. Với job lớn, nên lặp theo cursor hoặc đọc các chunk có checkpoint.

### 2.2. Cursor thông thường không tự đóng băng dữ liệu

Một hiểu lầm là: “Khi gọi `find()` thì server đã chốt tất cả document tại thời điểm đó, vì vậy mọi batch sau đều thuộc snapshot ban đầu.”

Đây **không phải đảm bảo chung của cursor thông thường**. Khi các writer đồng thời sửa những trường ảnh hưởng đến query hoặc index scan, một lần duyệt dài có thể chịu tác động của dữ liệu biến đổi. Các page được thực hiện bằng nhiều request `find()` riêng càng rõ ràng là nhiều lần đọc khác nhau.

Cursor còn có giới hạn vòng đời, timeout và session. Một kết nối mạng bị ngắt hoặc server failover có thể khiến cursor không còn dùng được. Đối với API web qua nhiều request, thường nên dùng **continuation token logic** thay vì cố giữ một server cursor mở trong thời gian dài.

## 3. Sort ổn định là điều kiện đầu tiên

MongoDB không cam kết thứ tự kết quả khi truy vấn thiếu `sort()`. Ngay cả khi có `sort({ createdAt: -1 })`, nhiều document có cùng `createdAt` vẫn có thể bằng khóa sort.

Ví dụ:

```javascript
db.orders.find(
  { tenantId: "T-A" }
)
.sort({ createdAt: -1 })
.limit(20);
```

Nếu hai order có cùng timestamp, MongoDB không bắt buộc duy trì cùng thứ tự tương đối giữa chúng qua mọi lần truy vấn. Khi lấy trang tiếp theo bằng khóa createdAt đơn lẻ, có thể bỏ sót hoặc lặp những record cùng thời điểm.

Giải pháp phổ biến:

```javascript
db.orders.find(
  { tenantId: "T-A" }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Bây giờ cặp `(createdAt, _id)` tạo một thứ tự đầy đủ **nếu _id là duy nhất trong tập kết quả**. MongoDB bảo đảm field `_id` là khóa định danh của document theo quy tắc collection; khi sharding, cần chú ý điều kiện uniqueness trên phạm vi toàn cluster nếu shard key không chứa _id.

### 3.1. Khóa sort phải đủ ổn định

Hai yêu cầu khác nhau:

- **Có tie-breaker duy nhất:** mọi document có một vị trí rõ trong sort.
- **Khóa không bị thay đổi:** vị trí document không dịch chuyển khi scan.

`_id` bất biến trong vòng đời một document, nhưng `updatedAt` thay đổi khi cập nhật. Vì vậy `sort({ updatedAt: -1, _id: -1 })` có thứ tự xác định tại mỗi thời điểm, **nhưng document vẫn có thể đổi vị trí giữa các trang**.

Nếu cần quét ổn định, ưu tiên `_id` hoặc `createdAt` được thiết kế bất biến, kết hợp _id làm khóa phụ. Nếu dữ liệu cho phép sửa createdAt, phải xét snapshot hoặc xử lý duplicate/missing.

### 3.2. Kiểu BSON nhất quán là điều kiện nền tảng

Đừng để cùng một trường sort lúc là BSON Date, lúc là String:

```javascript
{ _id: "A", createdAt: ISODate("2026-05-01T10:00:00Z") }
{ _id: "B", createdAt: "2026-05-01T10:00:00Z" }
```

MongoDB so sánh theo quy tắc BSON; nó không tự xem chuỗi ISO là Date. Range predicate và seek cursor có thể hoạt động khác kỳ vọng. Hãy dùng schema validation/migration để thống nhất Date, Number, String và null/missing ở các khóa sắp xếp.

## 4. Skip/limit: đơn giản nhưng có thể trùng hoặc bỏ sót

Offset pagination thường viết:

```javascript
const page = 2;
const size = 3;

db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip((page - 1) * size)
  .limit(size);
```

Giả sử tại T1 thứ tự là:

```text
[A, B, C, D, E, F, G, H]
```

Trang 1, size 3:

```text
[A, B, C]
```

Trước trang 2, một order mới `X` được insert lên đầu:

```text
[X, A, B, C, D, E, F, G, H]
```

Trang 2 gọi `skip(3).limit(3)` và nhận:

```text
[C, D, E]
```

**C bị lặp** vì vị trí offset đã dịch chuyển. Nếu thay vào đó `A` bị xóa:

```text
T2 sau xóa A:
[B, C, D, E, F, G, H]

skip(3).limit(3) -> [E, F, G]
```

**D bị bỏ sót**. Cả hai ví dụ đều có sort xác định, nhưng thứ tự các phần tử đã bị **đổi vị trí do tập kết quả thay đổi**.

### 4.1. Offset lớn còn gây chi phí đọc

```javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(1000000)
  .limit(20);
```

Để bỏ qua một triệu kết quả, server thường phải tiến qua một lượng lớn index key/document tương ứng. Có index không đồng nghĩa `skip(1000000)` thành thao tác chi phí hằng số.

Offset vẫn phù hợp với danh sách nhỏ, dữ liệu ít biến động hoặc UI cần nhảy đến một số trang cụ thể, nếu ứng dụng chấp nhận giới hạn về độ sâu và sự thiếu nhất quán giữa các lượt.

## 5. Keyset pagination: tiếp tục sau khóa cuối đã nhận

Thay vì bỏ qua N record của tập kết quả **hiện tại**, keyset hỏi:

> Trả những record nằm **sau bản ghi cuối của trang trước** theo cùng thứ tự.

Ví dụ scan tăng dần theo _id:

```javascript
// Trang đầu.
db.events.find({ tenantId: "T-A" })
  .sort({ _id: 1 })
  .limit(20);
```

Giả sử document cuối có `_id = lastId`. Trang sau:

```javascript
db.events.find({
  tenantId: "T-A",
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(20);
```

Nếu sort giảm dần `{ _id: -1 }` thì đổi thành `_id: { $lt: lastId }`.

Ưu điểm:

- Insert ở đầu danh sách không làm dịch vị trí seek cursor như offset.
- Có thể dùng index để tìm vùng khóa cần đọc tiếp.
- Không cần bỏ qua hàng triệu document cho một trang sâu.
- Có thể lưu lastId làm checkpoint cho batch job.

Nhưng **keyset không tạo snapshot**: record mới có khóa nằm sau lastId vẫn có thể xuất hiện; record chưa đọc bị xóa sẽ biến mất; nếu trường sort có thể cập nhật, record có thể di chuyển qua ranh giới cursor.

### 5.1. ObjectId không phải timestamp nghiệp vụ tuyệt đối

ObjectId thường có thành phần thời gian, nhưng nó không bảo đảm **thứ tự commit hay thứ tự sự kiện toàn cục**:

- ID có thể được tạo ở client từ trước khi gửi insert.
- Nhiều ID trong cùng giây có thể không đại diện thứ tự nghiệp vụ mong muốn.
- Dữ liệu backfill có thể có ID cũ hoặc do hệ thống khác cấp.
- `_id` còn có thể là String, UUID, Number theo schema.

Dùng _id để quét theo thứ tự ID là hợp lý. Muốn sort theo thời gian nghiệp vụ, dùng trường Date ổn định và thêm _id làm tie-breaker.

## 6. Keyset với nhiều trường: createdAt và _id

Danh sách đơn hàng mới nhất thường dùng:

```javascript
.sort({ createdAt: -1, _id: -1 })
```

Giả sử document cuối trang trước có:

```javascript
{
  _id: ObjectId("65a12f010000000000000041"),
  createdAt: ISODate("2026-03-01T12:30:00Z")
}
```

Điều kiện “nằm sau document này” theo sort giảm dần là:

```text
createdAt < lastCreatedAt
HOẶC
createdAt == lastCreatedAt và _id < lastId
```

Ví dụ:

```javascript
const lastCreatedAt = ISODate("2026-03-01T12:30:00Z");
const lastId = ObjectId("65a12f010000000000000041");

db.orders.find({
  tenantId: "T-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Nếu chỉ dùng `createdAt: { $lt: lastCreatedAt }`, những record khác có **cùng createdAt nhưng ID nhỏ hơn** bị bỏ qua. Nếu dùng `$lte` mà không có tie-breaker, record cuối trang trước có thể bị lặp.

### 6.1. Index phục vụ keyset

Ví dụ:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Ở query phổ biến trên, `tenantId` và `status` là equality conditions; `createdAt` và `_id` làm các sort keys. Tùy filter khác và phân phối dữ liệu thực tế, có thể cần index khác; không nên tạo index chỉ vì một ví dụ mà bỏ qua workload tổng thể.

### 6.2. Sort tăng dần

Nếu sort bằng `{ createdAt: 1, _id: 1 }`, điều kiện đi tiếp đổi chiều:

```javascript
{
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
}
```

Điều kiện seek và sort **phải tương thích về chiều trên từng trường**. Nếu sort kết hợp chiều tăng/giảm, so sánh trên từng thành phần cần được xây theo thứ tự từ điển thực tế; không đơn giản thay cùng một toán tử cho mọi field.

## 7. Hàm đọc trang có next cursor trong mongosh

Ví dụ triển khai một trang đơn hàng với size tùy chọn:

```javascript
function fetchOrdersPage(tenantId, after, pageSize) {
  const filter = {
    tenantId: tenantId,
    status: "PAID"
  };

  if (after) {
    filter.$or = [
      { createdAt: { $lt: after.createdAt } },
      {
        createdAt: after.createdAt,
        _id: { $lt: after.id }
      }
    ];
  }

  const docs = db.orders.find(
    filter,
    {
      _id: 1,
      createdAt: 1,
      status: 1,
      total: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(pageSize + 1)
  .toArray();

  const hasMore = docs.length > pageSize;
  const items = docs.slice(0, pageSize);
  const tail = items.length
    ? items[items.length - 1]
    : null;

  return {
    items: items,
    hasMore: hasMore,
    next: hasMore && tail
      ? { createdAt: tail.createdAt, id: tail._id }
      : null
  };
}
```

Hàm minh họa kỹ thuật **đọc pageSize + 1 document** để xem còn dữ liệu phía sau hay không. Trả tối đa `pageSize` document; dùng khóa của **document cuối thực sự trả về** để tạo token.

Không lấy khóa của document thừa (thứ `pageSize + 1`), nếu không sẽ bỏ sót document đó ở trang kế tiếp.

Với production:

- Giới hạn `pageSize`, tránh số lớn tùy ý.
- Xác thực tenant từ identity/authorization context, không chỉ tin parameter user gửi.
- Ký hoặc xác thực continuation token; không chấp nhận điều kiện MongoDB tùy ý từ client.
- Chuyển kiểu timestamp thành BSON Date, _id thành ObjectId hay kiểu gốc đúng schema.
- Có quy tắc rõ với field `createdAt` thiếu, null hoặc sai kiểu.
- Có thể thêm watermark và version của filter nếu phiên phân trang cần giới hạn.

## 8. Dữ liệu thay đổi giữa hai lượt: bốn kịch bản

### 8.1. Insert mới đứng trước cursor

T1:

```text
[A, B, C, D, E]
Trang 1: A, B, C
Cursor: C
```

T2 có insert `X` mới nhất:

```text
[X, A, B, C, D, E]
```

Trang sau C bằng keyset trả `D, E`. Nó **không lặp C** như skip/limit có thể làm. Nhưng `X` không xuất hiện trong phần cuộn tiếp. Đây có thể là hành vi mong muốn của live feed: người dùng cần refresh từ đầu để xem item mới nhất.

### 8.2. Insert mới có khóa nằm sau cursor

Một tác vụ backfill insert `Y` với `createdAt` rất cũ, nằm sau cursor. Trang tiếp theo có thể thấy `Y` dù record không tồn tại khi trang 1 được lấy.

Như vậy, keyset không bảo đảm “mọi kết quả đều có từ thời điểm T1”. Nó chỉ xác định vị trí truy vấn theo một khóa.

### 8.3. Delete hoặc soft delete trước khi đọc

Nếu `D` chưa đọc và bị xóa vật lý, page tiếp theo không thể trả `D`. Nếu API lọc `isDeleted: false` và `D` được xóa mềm, nó cũng rời khỏi tập kết quả active.

Điều này có thể chấp nhận cho danh sách đang hoạt động. Nếu job cần xuất “mọi document từng tồn tại tại T1”, phải dùng snapshot/nguồn lịch sử phù hợp.

### 8.4. Update khóa sort hoặc trường lọc

Giả sử sort giảm dần theo `updatedAt`:

```text
T1: [A, B, C, D, E]
Trang 1: [A, B, C]
Cursor = C
```

Nếu `D.updatedAt` được cập nhật thành thời điểm mới hơn cả C, `D` chuyển **lên trước cursor**. Query trang sau chỉ lấy các khóa nhỏ hơn cursor có thể **bỏ sót D**.

Nếu `B` đã được đọc sau đó bị đổi sort key thành thời điểm cũ hơn C, nó có thể chuyển **xuống sau cursor** và xuất hiện lại ở trang sau.

Tương tự, nếu `status` đổi từ `PAID` sang `CANCELLED`, document có thể rời khỏi filter; nếu đổi ngược lại thì có thể gia nhập tập kết quả. **Tie-breaker _id chỉ xử lý nhiều record có khóa sort giống nhau, không ngăn việc trường sort bị sửa.**

## 9. Snapshot, majority và một mốc đọc cố định

Nhiều người tưởng rằng `readConcern: "majority"` bảo đảm các trang liên tiếp đọc cùng một ảnh chụp. Điều này **không đúng**.

Ví dụ:

```text
T1: page 1 đọc các bản ghi đã majority committed.
T2: một batch insert được majority committed.
T3: page 2 đọc majority.
```

Cả hai query đều đọc dữ liệu đủ điều kiện majority, nhưng page 2 có thể quan sát trạng thái mới hơn page 1. Majority không tự kết nối chúng thành một snapshot duy nhất.

### 9.1. Các khái niệm cần phân biệt

| Cơ chế | Tác dụng chính | Không mặc nhiên có |
|---|---|---|
| `readConcern: "local"` | Đọc theo trạng thái local phù hợp quy tắc triển khai | Snapshot xuyên mọi request |
| `readConcern: "majority"` | Đọc dữ liệu theo các bảo đảm majority commit | Cùng timepoint cho nhiều trang |
| `readConcern: "snapshot"` | Cho phép đọc một snapshot nhất quán trong phạm vi được hỗ trợ | Snapshot vô thời hạn |
| Causally consistent session | Quan hệ causal cho chuỗi thao tác khi đáp ứng điều kiện | Snapshot cố định cho toàn bộ scan |
| `readPreference` | Chọn node đọc, ví dụ primary/secondary | Quyết định snapshot consistency |

Read preference tới secondary có thể chịu replication lag. Nếu các request đọc từ nhiều secondary khác nhau mà không có cơ chế phù hợp, kết quả còn có thể khác nhau do trạng thái áp dụng dữ liệu.

### 9.2. Snapshot transaction

Trong môi trường MongoDB hỗ trợ transaction snapshot, một luồng đơn giản:

```javascript
const session = db.getMongo().startSession();

try {
  const sessionDb = session.getDatabase(db.getName());
  const orders = sessionDb.getCollection("orders");

  session.startTransaction({
    readConcern: { level: "snapshot" }
  });

  const cursor = orders.find({
    tenantId: "T-A",
    status: "PAID"
  })
  .sort({ createdAt: 1, _id: 1 })
  .batchSize(200);

  while (cursor.hasNext()) {
    const order = cursor.next();
    // Xử lý nhanh trong ranh giới transaction.
  }

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (ignored) {
    // Có thể transaction đã kết thúc theo trạng thái lỗi thực tế.
  }
  throw error;
} finally {
  session.endSession();
}
```

Ví dụ trên **không phải khuyến nghị giữ transaction nhiều giờ để export hàng triệu document**. Transaction dài có chi phí tài nguyên, giới hạn lifetime và rủi ro lỗi do lịch sử snapshot/áp lực ghi. Trên các phiên bản/topology phù hợp, MongoDB còn có cơ chế snapshot read ngoài transaction với điều kiện riêng; cần xem tài liệu đúng phiên bản.

Nếu cần báo cáo lớn cố định tại T1, có thể phù hợp hơn với:

- Snapshot backup hoặc bản xuất logic được chốt tại thời điểm xác định.
- Collection/dataset bất biến được materialize cho phiên export.
- Cơ chế snapshot read tại thời điểm hỗ trợ, với thời gian chạy và lưu giữ lịch sử được kiểm soát.
- Kiến trúc snapshot + change capture khi cần cả ảnh chụp ban đầu và dòng thay đổi.

## 10. Upper watermark: chốt miền khóa, không phải snapshot

Khi job chỉ cần quét những ID nằm trong miền hiện có tại lúc bắt đầu, có thể chốt khóa lớn nhất `H`:

```javascript
const newest = db.events.find(
  { tenantId: "T-A" },
  { _id: 1 }
)
.sort({ _id: -1 })
.limit(1)
.toArray();

const upperId = newest.length ? newest[0]._id : null;
```

Nếu có `upperId`, các lần đọc dùng:

```javascript
db.events.find({
  tenantId: "T-A",
  _id: {
    $gt: lastId,
    $lte: upperId
  }
})
.sort({ _id: 1 })
.limit(500);
```

Ý nghĩa: job chỉ quét ID **lớn hơn lastId nhưng không vượt quá upperId**.

Điều này chặn một phần các document mới có ID cao hơn mốc H. Nhưng:

1. Writer vẫn có thể insert ID **thấp hơn H**.
2. Những document có ID trong miền có thể bị update/delete.
3. Trường lọc khác như `status` vẫn có thể thay đổi.
4. Tính upperId và quét dữ liệu không phải một thao tác snapshot nguyên tử.

Do đó, upper watermark là **giới hạn miền quét**, không phải lời hứa rằng mọi document thuộc tập T1 đều giữ nguyên.

Nếu nghiệp vụ cấm backfill và có khóa tăng đơn điệu bất biến, watermark có thể rất hữu ích. Nếu không, cần thiết kế mạnh hơn.

## 11. Batch job có checkpoint sau khi xử lý an toàn

Một job quét dài cần lưu tiến độ bền vững; server cursor không phải checkpoint lâu dài.

Ví dụ:

```javascript
// lastId lấy từ checkpoint đã lưu.
const filter = { tenantId: "T-A" };

if (lastId !== null) {
  filter._id = { $gt: lastId };
}

const batch = db.customers.find(
  filter,
  { _id: 1, tenantId: 1, emailNormalized: 1 }
)
.sort({ _id: 1 })
.limit(500)
.toArray();
```

Khi kết hợp upper watermark, điều kiện _id phải gồm cả `$gt` và `$lte` như phần trước.

### 11.1. Trình tự checkpoint an toàn

```text
1. Đọc checkpoint lastProcessedKey.
2. Đọc batch sau lastProcessedKey.
3. Xử lý từng document.
4. Sau khi effect của document/batch đã an toàn:
     lưu checkpoint tương ứng.
5. Lặp lại.
```

Nếu lưu checkpoint **trước effect** rồi worker crash, có thể bỏ sót document mà checkpoint đã vượt qua. Nếu effect đã thành công nhưng checkpoint chưa lưu, khi retry có thể xử lý lại document. Vì vậy, một thiết kế thực tế thường là **at-least-once + idempotent processing**.

### 11.2. Ví dụ idempotency

Giả sử job tính lại thông tin tìm kiếm cho mỗi user. Thay vì append một bản ghi mới mỗi lần:

```javascript
db.searchCards.insertOne({
  userId: user._id,
  title: user.displayName
});
```

có thể dùng một khóa ổn định:

```javascript
db.searchCards.updateOne(
  { _id: user._id },
  {
    $set: {
      title: user.displayName,
      sourceVersion: user.version
    }
  },
  { upsert: true }
);
```

Việc update cùng ID thường giúp tránh tạo nhiều record kết quả; nhưng nếu event cũ tới sau event mới, còn cần kiểm soát `sourceVersion`/điều kiện cập nhật để không ghi đè trạng thái mới bằng giá trị cũ. Định danh ổn định chỉ là một phần của idempotency.

Nếu effect và checkpoint nằm ở hai collection, có thể cần transaction phù hợp hoặc quy trình xử lý lặp/đối soát. Không có nguyên tắc rằng một cursor tự bảo đảm exactly-once cho downstream.

### 11.3. Checkpoint theo batch hay từng document?

| Cách checkpoint | Lợi ích | Đánh đổi |
|---|---|---|
| Sau mỗi document | Ít phải replay khi crash | Nhiều lần ghi trạng thái |
| Sau mỗi batch | Giảm overhead checkpoint | Có thể replay cả batch |
| Mỗi N document/thời gian | Cân bằng hai mục tiêu | Cần mô tả rõ phạm vi replay |

Checkpoint nên chứa filter/sort version và các khóa cần thiết để tránh tiếp tục theo thuật toán đã đổi giữa hai lần deploy.

Ví dụ metadata:

```javascript
{
  _id: "reindex-users-T-A",
  tenantId: "T-A",
  filterVersion: 2,
  sort: { _id: 1 },
  lastProcessedId: ObjectId("65a12f010000000000000041"),
  upperId: ObjectId("65a12f010000000000000099"),
  status: "RUNNING",
  processedCount: NumberLong("150000"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
```

Đây là schema do ứng dụng định nghĩa, không phải document checkpoint mặc định của MongoDB.

## 12. Khi khóa sort thay đổi: không thể chỉ dựa vào seek

Nếu buộc phải quét theo `updatedAt` đang được các writer sửa, một document có thể chuyển qua ranh giới cursor và tạo duplicate/missing.

Các giải pháp tùy mục tiêu:

- **Khóa bất biến:** quét theo _id hoặc createdAt không được thay đổi.
- **Snapshot:** giữ cùng phiên bản dữ liệu tại mốc T.
- **Versioned records:** mỗi lần thay đổi tạo một phiên bản bất biến có ID riêng.
- **Change streams:** theo dõi từng sự kiện insert/update/delete thay vì scan live để dò mọi thay đổi.
- **Replay/dedup:** chấp nhận đọc lại và lưu version/ID để không nhân đôi effect.
- **Đối soát định kỳ:** hữu ích khi chỉ cần eventual consistency nhưng phải phát hiện chênh lệch.

Không nên giải quyết bằng cách tăng page size hoặc thêm `_id` rồi khẳng định đã loại hết rủi ro. Thứ tự ổn định tại một thời điểm vẫn khác thứ tự **bất biến theo thời gian**.

## 13. Change streams cho đồng bộ liên tục

Khi cần nhận những thay đổi phát sinh sau khi đọc dữ liệu ban đầu, MongoDB hỗ trợ **change streams** trên deployment phù hợp. Change stream quan sát luồng thay đổi và cung cấp resume token.

Ví dụ:

```javascript
const changeStream = db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    }
  ],
  { fullDocument: "updateLookup" }
);

while (changeStream.hasNext()) {
  const event = changeStream.next();

  printjson({
    type: event.operationType,
    key: event.documentKey,
    token: event._id
  });

  // Xử lý event trước khi đánh dấu resume token đã commit.
}
```

Những lưu ý quan trọng:

- Cần replica set hoặc sharded cluster/triển khai hỗ trợ change streams.
- `fullDocument: "updateLookup"` có thể lấy phiên bản hiện tại vào thời điểm lookup, không mặc nhiên là hình ảnh chính xác tại đúng thời điểm event xảy ra.
- Sự kiện delete thường có `documentKey`, không có đầy đủ document đã bị xóa.
- Resume token phụ thuộc lịch sử thay đổi/oplog còn sẵn và phiên bản cấu hình; không thể resume vô hạn sau khi history đã bị dọn.
- Event có thể được đọc lại khi consumer retry/reconnect; cần xử lý idempotent.
- Nếu lưu resume token trước khi effect của event được xử lý an toàn, có thể mất hiệu ứng sau crash.

### 13.1. Initial scan kết hợp stream phải xử lý khoảng giao nhau

Một pipeline đồng bộ thường:

```text
MongoDB source
   |
   +--> Initial snapshot/scan ------> data đích ban đầu
   |
   +--> Change stream -------------> áp dụng insert/update/delete
                                     phát sinh sau mốc phù hợp
```

Nếu **quét trước, mở stream sau**, có thể mất thay đổi phát sinh giữa hai bước. Nếu **mở stream trước, quét sau**, có thể phải buffer hoặc xử lý duplicate, đồng thời bảo vệ thứ tự áp dụng giữa snapshot và event.

Một hệ thống CDC đúng cần xác định điểm bắt đầu, mốc snapshot tương ứng, cách lưu token, dedup/version và khả năng resync. Không phải cứ chạy `find()` rồi chạy `watch()` là tự bảo đảm không mất sự kiện.

## 14. Count và trang cuối khi dữ liệu thay đổi

API phân trang truyền thống có thể trả:

```json
{
  "items": [],
  "page": 3,
  "size": 20,
  "total": 1742,
  "totalPages": 88
}
```

Nhưng `total` được tính bởi một phép đọc khác:

```javascript
db.orders.countDocuments({
  tenantId: "T-A",
  status: "PAID"
});
```

Nếu có insert/update/delete giữa lúc đếm và lấy page, tổng có thể không mô tả chính xác tập các record đã trả. Qua nhiều request, tổng còn tiếp tục thay đổi.

Với live scrolling, hợp đồng có thể chỉ cần:

```json
{
  "items": [],
  "nextCursor": "opaque-token",
  "hasMore": true
}
```

Nếu product vẫn cần `total`, nên xác định nó là tổng tại **thời điểm đếm**, gần đúng hay thuộc snapshot đã chốt, không ngầm hứa rằng số trang sẽ cố định.

Khi `hasMore: false` tại T1, không có nghĩa collection sẽ không bao giờ có thêm document. Để thấy record mới ở đầu, client nên refresh hoặc dùng luồng sự kiện riêng.

## 15. Continuation token: không tin dữ liệu do client tự gửi

Một token hợp lý cần mô tả vị trí trong thứ tự logic:

```json
{
  "version": 1,
  "tenantId": "T-A",
  "status": "PAID",
  "sort": ["createdAt:desc", "_id:desc"],
  "after": {
    "createdAt": "2026-03-01T12:30:00.000Z",
    "id": "65a12f010000000000000041"
  },
  "expiresAt": "2026-11-15T00:00:00.000Z"
}
```

Đây là **nội dung trước khi đóng gói**, không phải khuyến nghị gửi JSON thô ra client. Production thường dùng token opaque có chữ ký hoặc cơ chế xác thực tương đương.

Quy trình xử lý:

1. Xác thực người dùng và quyền truy cập vào tenant.
2. Xác thực chữ ký, phiên bản và thời hạn của token.
3. Kiểm tra filter/sort của token phù hợp endpoint và request.
4. Parse lại Date theo UTC và ID theo đúng BSON type.
5. Dựng seek predicate trên những trường đã được allowlist.
6. Giới hạn số record mỗi trang, không cho token vượt quyền tenant.

**Base64 chỉ là mã hóa biểu diễn, không phải chữ ký bảo mật.** Client có thể tự sửa payload Base64 nếu không có cơ chế xác thực. Không chứa dữ liệu bí mật không cần thiết trong token.

Token của API mô tả **khóa tiếp tục**, không phải server cursor ID với lifetime không giới hạn.

## 16. Chọn index theo filter, sort và workload

Với trang đơn hàng:

```javascript
db.orders.find({
  tenantId: "T-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Một index ứng viên:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Xác nhận bằng:

```javascript
db.orders.find({
  tenantId: "T-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
```

Cần quan sát:

| Trường trong explain | Câu hỏi |
|---|---|
| `winningPlan` | Kế hoạch được chọn là gì? |
| `IXSCAN` | Có dùng index thích hợp không? |
| `FETCH` | Có cần đọc document ngoài index? |
| `COLLSCAN` | Có quét collection không? |
| `SORT` | Có sort bổ sung tốn bộ nhớ không? |
| `totalKeysExamined` | Bao nhiêu khóa index đã xem xét? |
| `totalDocsExamined` | Bao nhiêu document đã xem xét? |
| `nReturned` | Có trả đúng số lượng cần thiết không? |

Seek theo hai field thường dùng `$or`. Query planner có thể triển khai các nhánh theo nhiều kế hoạch; hiệu quả phụ thuộc phiên bản, phân bố dữ liệu và index. Không nên chỉ nhìn thấy một `IXSCAN` rồi kết luận toàn bộ query tối ưu nếu có FETCH/SORT lớn.

### 16.1. Projection giảm payload nhưng không mặc nhiên giảm mọi I/O

```javascript
db.orders.find(
  { tenantId: "T-A" },
  { _id: 1, createdAt: 1, total: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Projection giúp client không tải các mảng hoặc object lớn không cần thiết. Nếu index cover filter/sort/projection, một số query có thể không cần FETCH. Nhưng projection không đồng nghĩa storage engine chỉ đọc vài byte của BSON record; phải xem plan thực tế.

### 16.2. Sharded cluster còn thêm chi phí merge

Ở sharded cluster, query có thể phải đọc từ nhiều shard rồi merge các luồng theo sort. Shard key quyết định mức độ route/scatter-gather, và index ở mỗi shard không tự loại bỏ toàn bộ chi phí phối hợp.

Nếu phần lớn query có `tenantId`, một shard key thích hợp có thể giúp route, nhưng lựa chọn này phải cân bằng tải ghi và tránh hot shard. Keyset không tự cung cấp snapshot phân tán khi các shard đang thay đổi dữ liệu.

## 17. Vòng đời cursor và timeout trong job dài

Server cursor có thể hết hạn do timeout, session hoặc sự kiện vận hành. Một số option như `noCursorTimeout()` không loại bỏ mọi giới hạn của session và kết nối.

Khi viết job dài:

- Đóng cursor khi hoàn tất hoặc gặp lỗi.
- Không giữ cursor nhàn rỗi quá lâu trong khi gọi API bên ngoài.
- Chọn batch size dựa trên số byte, không chỉ số document.
- Tránh `toArray()` toàn bộ collection.
- Có cách tái tạo query từ checkpoint nếu mất cursor.
- Đo round trip, bộ nhớ và độ trễ khi thay đổi batch size.
- Giới hạn thời gian snapshot/transaction nếu đang dùng cơ chế đó.

Ví dụ:

```javascript
const cursor = db.events.find({
  tenantId: "T-A"
})
.sort({ _id: 1 })
.batchSize(500);

try {
  while (cursor.hasNext()) {
    const event = cursor.next();
    // Xử lý event, ghi checkpoint theo hợp đồng job.
  }
} finally {
  cursor.close();
}
```

Đối với ứng dụng Java, nên dùng cơ chế đóng cursor như `try-with-resources` khi phù hợp với loại MongoCursor đang dùng. Khi lỗi giữa chừng, phục hồi bằng **khóa đã checkpoint**, không phụ thuộc ID của server cursor cũ.

## 18. Chọn giải pháp theo tình huống

| Tình huống | Cách tiếp cận | Giới hạn cần công bố |
|---|---|---|
| Danh sách bài viết đang có thêm mới | Keyset theo createdAt + _id | Refresh để thấy bài mới đứng trước cursor |
| Danh sách sản phẩm có thể bị xóa mềm | Keyset + active filter | Document chưa đọc có thể rời tập |
| Tập nhỏ cần chọn trang số 1–10 | Skip/limit | Có thể lệch khi insert/delete |
| Worker chuyển đổi hàng triệu tài khoản | Keyset theo ID bất biến + checkpoint | Cần replay/idempotency |
| Chỉ quét những khóa trong miền lúc bắt đầu | Upper watermark | Không phải snapshot khi có backfill/update |
| Báo cáo tài chính chốt tại một thời điểm | Snapshot/dataset bất biến | Chi phí và giới hạn snapshot |
| Đồng bộ toàn bộ thay đổi sang search index | Initial scan + change streams | Phải quản lý giao điểm và resume token |
| Đếm tổng bản ghi hiển thị | Count với ngữ nghĩa mốc rõ ràng | Total live có thể đổi |
| Collection sharded lớn | Seek, index, shard key phù hợp | Cần đo merge/routing và concurrency |

## 19. Bài tập thực hành

### Bài 1 — Chứng minh offset drift

Tạo collection `pageLab` gồm các document có sequence từ 1 đến 10. Lấy trang đầu theo `sort({ sequence: 1 }).limit(3)`. Trước trang thứ hai, insert document có sequence nhỏ hơn 1 hoặc xóa record đứng đầu. Gọi `skip(3).limit(3)` và giải thích document nào có thể bị lặp hoặc bị bỏ sót.

### Bài 2 — Keyset theo _id

Tạo 100 document với _id từ 1 đến 100. Viết vòng lặp lấy 10 document mỗi lần bằng `_id: { $gt: lastId }`. Thêm ID 105 trong khi đang quét và thử xóa ID 30 trước khi đọc đến nó. Phân biệt kết quả thực tế với tập dữ liệu tại lúc bắt đầu.

### Bài 3 — Seek theo createdAt và _id

Tạo nhiều đơn hàng có cùng `createdAt`. Viết hai truy vấn lấy trang đầu và trang sau theo `{ createdAt: -1, _id: -1 }`. Giải thích vì sao chỉ dùng `createdAt: { $lt: lastCreatedAt }` gây mất record cùng timestamp.

### Bài 4 — Update sort key

Quét collection theo `updatedAt DESC`. Sau trang đầu, cập nhật một document chưa đọc để `updatedAt` nhảy lên trước cursor và cập nhật một document đã đọc để nó chuyển xuống sau cursor. Dự đoán missing và duplicate. Đề xuất sửa bằng khóa bất biến hoặc snapshot.

### Bài 5 — Worker có checkpoint

Một job xử lý 500 document mỗi batch, đã xử lý xong 387 document thì crash trước khi lưu checkpoint. Giải thích vì sao phải hỗ trợ replay và cách thiết kế effect idempotent. Đề xuất vị trí lưu checkpoint và version filter.

### Bài 6 — Snapshot hay live?

Dashboard đơn hàng chỉ cần dữ liệu PAID mới nhất. Báo cáo kế toán yêu cầu trạng thái đúng 00:00 ngày cuối tháng. Chọn chiến lược đọc cho từng trường hợp và giải thích vì sao keyset live không đủ cho báo cáo chốt.

### Bài 7 — Initial scan kết hợp change streams

Thiết kế pipeline đưa dữ liệu MongoDB sang search index: quét 1 triệu record ban đầu, tiếp tục cập nhật insert/update/delete. Mô tả cách tránh mất event giữa hai giai đoạn, lưu resume token và xử lý event lặp.

### Bài 8 — Thiết kế continuation token

Thiết kế token cho API đa tenant với filter `status: "PAID"` và sort `createdAt DESC, _id DESC`. Nêu các field bắt buộc, cách xác thực token và rủi ro khi token chỉ được encode Base64 mà không ký.

## 20. Tài liệu MongoDB tham khảo

- [db.collection.find()](https://www.mongodb.com/docs/manual/reference/method/db.collection.find/)
- [Cursor Methods](https://www.mongodb.com/docs/manual/reference/method/js-cursor/)
- [cursor.batchSize()](https://www.mongodb.com/docs/manual/reference/method/cursor.batchSize/)
- [cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/)
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Snapshot Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Indexes and Query Optimization](https://www.mongodb.com/docs/manual/indexes/)

## Kết luận

Khi dữ liệu MongoDB có thể thay đổi trong lúc đọc, không thể chỉ dùng `sort()`, `skip()` và `limit()` mà mặc nhiên kỳ vọng các trang nối tiếp nhau như một tập bất biến. **Offset pagination** dễ bị dịch vị trí khi insert/delete; **keyset pagination** tiếp tục theo khóa cuối đã nhận và thường phù hợp hơn với tập lớn, nhưng vẫn chịu tác động của update/delete và không phải snapshot.

Với UI live, hãy dùng thứ tự đầy đủ, index phù hợp và continuation token có kiểm tra quyền. Với worker quét dữ liệu, dùng khóa đủ bất biến, checkpoint sau effect và xử lý lặp an toàn; watermark giúp giới hạn miền khóa nhưng không chặn thay đổi bên trong miền. Với báo cáo chốt thời điểm, dùng snapshot hoặc dataset bất biến; với đồng bộ liên tục, kết hợp initial scan và change streams đúng ranh giới. Định nghĩa chính xác **khả năng nhìn thấy dữ liệu mới, mức chấp nhận duplicate/missing và thời điểm đọc** ngay từ đầu là nền tảng để đọc dữ liệu lớn an toàn.

