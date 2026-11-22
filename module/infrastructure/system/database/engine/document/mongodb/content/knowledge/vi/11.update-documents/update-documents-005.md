# Upsert, $setOnInsert và kiểm soát trùng khóa khi nhiều yêu cầu đồng thời

## 1. Bài toán: nhận cùng một yêu cầu nhiều lần

Trong ứng dụng thực tế, một yêu cầu có thể đến MongoDB hơn một lần dù người dùng chỉ thao tác một lần. Ví dụ:

- Client gửi yêu cầu tạo đơn hàng, nhưng mất kết nối trước khi nhận phản hồi và tự gửi lại.
- Một hệ thống nhận sự kiện từ hàng đợi theo cơ chế *at least once delivery*; cùng một message có thể được xử lý lại.
- Hai worker cùng đọc một công việc chưa được đánh dấu hoàn thành và cùng ghi dữ liệu.
- Hai HTTP request của cùng khách hàng đến gần như đồng thời.

Giả sử ứng dụng nhận đơn hàng từ một hệ thống đối tác với khóa nghiệp vụ `{tenantId, externalOrderId}`. Mong muốn là **mỗi cặp khóa chỉ có một document**, kể cả khi nhiều worker ghi đồng thời. Nếu document chưa tồn tại thì tạo nó; nếu đã tồn tại thì tùy yêu cầu mà giữ nguyên hoặc cập nhật một số trường cho phép.

Đây là ngữ cảnh điển hình để hiểu ba công cụ của MongoDB:

1. **Upsert**: nếu bộ lọc khớp document hiện có thì cập nhật; nếu không khớp thì chèn một document mới.
2. **`$setOnInsert`**: đặt những field chỉ ở nhánh **insert** của upsert, chẳng hạn `createdAt`, `initialStatus` hoặc dữ liệu gốc cần giữ nguyên.
3. **Unique index**: thực thi ràng buộc không cho tồn tại hai document có cùng khóa nghiệp vụ, kể cả khi nhiều request chạy đồng thời.

Điểm mấu chốt là: **`upsert: true` không tự biến một bộ lọc bất kỳ thành ràng buộc duy nhất**. Khi có nhiều yêu cầu đồng thời, unique index và chiến lược xử lý lỗi mới là phần quyết định tính đúng đắn.

Sau bài học, người học có thể viết `updateOne(..., { upsert: true })`, phân biệt `$set` với `$setOnInsert`, chọn khóa duy nhất, xử lý cạnh tranh ghi, nhận diện lỗi trùng khóa `E11000` và thiết kế yêu cầu có thể lặp lại an toàn.

## 2. Upsert hoạt động như thế nào?

### 2.1. Từ `updateOne` thông thường đến upsert

Lệnh cập nhật một document:

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  { $set: { status: "RECEIVED" } }
);
```

Nếu không có document khớp bộ lọc, lệnh trên **không chèn mới**. Đặt thêm `upsert: true` để MongoDB tạo document khi không tìm thấy kết quả khớp:

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  { $set: { status: "RECEIVED" } },
  { upsert: true }
);
```

Luồng logic ở mức khái niệm:

```text
updateOne(filter, update, { upsert: true })
                    |
                    v
           Có document khớp?
              /          \
            Có            Không
            |               |
            v               v
      UPDATE document    INSERT document mới
            |               |
            +-------+-------+
                    |
                    v
             Trả kết quả ghi
```

Trong lệnh update dùng toán tử như `$set`, nếu cần insert, MongoDB xây dựng document mới từ những điều kiện bằng thích hợp trong filter và các toán tử cập nhật; nếu chưa có `_id`, server cấp một `_id`. Không nên dựa vào bộ lọc phức tạp để suy ra mọi field được đưa vào document insert: chỉ rõ dữ liệu cần lưu bằng cấu trúc update phù hợp.

`upsert` cũng có mặt ở một số phương thức khác như `replaceOne` và `findOneAndUpdate`. Bài này tập trung vào `updateOne` vì nó biểu đạt rõ việc thay đổi từng field và thường phù hợp cho khóa nghiệp vụ.

### 2.2. Cách đọc kết quả `updateOne`

Ví dụ một kết quả chèn mới:

```javascript
{
  acknowledged: true,
  matchedCount: 0,
  modifiedCount: 0,
  upsertedCount: 1,
  upsertedId: ObjectId("...")
}
```

Một kết quả tìm thấy document và cập nhật thành công thường có `matchedCount: 1`, `upsertedCount: 0`. Nếu update không làm thay đổi giá trị, `modifiedCount` có thể bằng `0` dù `matchedCount` là `1`.

| Trường kết quả | Ý nghĩa |
| --- | --- |
| `acknowledged` | Lệnh ghi có được xác nhận theo write concern hay không |
| `matchedCount` | Số document khớp filter ở nhánh update, tối đa 1 với `updateOne` |
| `modifiedCount` | Số document thực sự bị thay đổi, có thể là 0 nếu cập nhật không đổi giá trị |
| `upsertedCount` | Số document được chèn do upsert, thường 0 hoặc 1 ở `updateOne` |
| `upsertedId` | `_id` của document vừa được chèn, nếu có |

Không nên hiểu `modifiedCount: 0` đồng nghĩa với “thao tác thất bại”: nó có thể là trường hợp đã có document giống hệt dữ liệu cần ghi. Với môi trường ghi không được xác nhận, một số thông tin kết quả có thể không sẵn có; các ví dụ trong bài giả định thao tác ghi được xác nhận.

### 2.3. Khi nào nên và không nên dùng upsert?

**Phù hợp:** đồng bộ trạng thái hiện tại theo một khóa duy nhất, tạo cấu hình mặc định nếu chưa có, nhập dữ liệu từ nguồn bên ngoài, tạo bản ghi xử lý theo idempotency key.

**Cần cân nhắc:** nghiệp vụ chỉ cho phép “create” và phải báo lỗi nếu đã tồn tại; cập nhật bắt buộc kiểm tra trạng thái cũ; thao tác thay đổi tiền hoặc số lượng không được lặp; bộ lọc chỉ theo điều kiện thời gian/trạng thái không xác định một khóa duy nhất.

Đặc biệt, không sử dụng `upsert: true` một cách tùy tiện cho lệnh “chỉ cập nhật khi đang `PENDING`”. Nếu document cùng khóa đã chuyển sang `ACTIVE`, filter kèm `status: "PENDING"` không khớp và upsert có thể cố **insert một document mới**, dẫn đến trùng khóa hoặc tạo bản ghi ngoài ý muốn.

## 3. `$set` và `$setOnInsert` khác nhau như thế nào?

### 3.1. `$set` áp dụng cho cả hai nhánh

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  {
    $set: {
      status: "RECEIVED",
      lastSeenAt: new Date()
    }
  },
  { upsert: true }
);
```

Nếu chưa có document, MongoDB tạo document với các field tương ứng. Nếu đã có, `status` và `lastSeenAt` bị đặt lại. Điều này hữu ích nếu nghiệp vụ thực sự cần đồng bộ giá trị hiện tại, nhưng **có thể nguy hiểm với dữ liệu chỉ được khởi tạo một lần**.

Ví dụ: đơn hàng đã chuyển `SHIPPED`, nhưng message “đơn hàng mới” được phát lại. Nếu worker dùng `$set: { status: "RECEIVED" }` cho mọi upsert, lần xử lý lại có thể kéo trạng thái từ `SHIPPED` về `RECEIVED`.

### 3.2. `$setOnInsert` chỉ áp dụng khi tạo mới

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  {
    $setOnInsert: {
      status: "RECEIVED",
      createdAt: new Date(),
      sourceSystem: "partner-api"
    }
  },
  { upsert: true }
);
```

Nếu chưa tồn tại, document mới nhận `status`, `createdAt` và `sourceSystem`. Nếu đã tồn tại, các giá trị này **không bị ghi lại**.

| Trường hợp | `$set` | `$setOnInsert` |
| --- | --- | --- |
| Upsert không tìm thấy và chèn document | Áp dụng | Áp dụng |
| Upsert tìm thấy và cập nhật document | Áp dụng | Không áp dụng |
| `updateOne` không có upsert, tìm thấy document | Áp dụng | Không có tác dụng |
| `updateOne` không có upsert, không tìm thấy | Không ghi | Không ghi |

Điều kiện để `$setOnInsert` có tác dụng là thao tác thực sự **đi đến nhánh insert của một upsert**. Nó không phải toán tử đặt giá trị mặc định cho field thiếu trên document đã tồn tại.

### 3.3. Kết hợp hai toán tử khi cần cập nhật có kiểm soát

Một cấu trúc thường gặp:

```javascript
db.productSnapshots.updateOne(
  { source: "ERP", sourceId: "SKU-1001" },
  {
    $set: {
      displayName: "Bàn phím",
      currentPriceCents: 125000,
      updatedAt: new Date()
    },
    $setOnInsert: {
      createdAt: new Date(),
      initialImportVersion: 1
    }
  },
  { upsert: true }
);
```

Ở đây `displayName` và `currentPriceCents` được phép cập nhật mỗi lần đồng bộ; `createdAt` và `initialImportVersion` chỉ có khi tạo mới. **Không đặt cùng một đường dẫn field trong cả `$set` và `$setOnInsert`**, vì có thể gây xung đột toán tử cập nhật.

### 3.4. `$setOnInsert` không đồng nghĩa “chỉ tạo nếu chưa có” cho mọi tình huống

Nếu mong muốn **create-if-absent**, toàn bộ thông tin chỉ được ghi lần đầu có thể đặt dưới `$setOnInsert`. Nếu mong muốn **đồng bộ dữ liệu hiện tại**, thêm `$set` cho những field có thể thay đổi. Nhưng việc xác định “tạo một lần” hay “luôn cập nhật” phải bắt đầu từ quy tắc nghiệp vụ:

- `createdAt`: thường chỉ ghi một lần.
- `updatedAt`: cập nhật khi dữ liệu thực sự được chỉnh sửa theo quy tắc.
- `status` của state machine: không nên tùy ý đặt lại bằng message có thể phát lại.
- `requestFingerprint` của một idempotency key: chỉ nên ghi lần đầu để đối chiếu các yêu cầu lặp.
- `lastSeenAt`: có thể được cập nhật trong mô hình đồng bộ, nhưng việc lặp thao tác sẽ làm thay đổi giá trị.

## 4. Khóa nghiệp vụ và unique index

### 4.1. `_id` là duy nhất, nhưng chưa đủ cho một khóa khác

MongoDB tạo unique index cho `_id`. Nếu mỗi lần request sinh một `ObjectId` mới làm `_id`, hai request xử lý cùng đơn hàng có thể tạo hai document khác nhau. `_id` duy nhất không tự ngăn việc đó.

Ví dụ hai document:

```javascript
{ _id: ObjectId("66a000000000000000000001"), tenantId: "A", externalOrderId: "ORD-1" }
{ _id: ObjectId("66a000000000000000000002"), tenantId: "A", externalOrderId: "ORD-1" }
```

Cả hai có `_id` khác nhau nên vẫn thỏa index mặc định. Nếu quy tắc nghiệp vụ nói một tenant không được có hai order cùng external ID, phải biểu diễn chính xác ràng buộc đó.

### 4.2. Tạo unique compound index theo đúng phạm vi

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  {
    unique: true,
    name: "uniq_tenant_external_order"
  }
);
```

Index này nói rằng một cặp `(tenantId, externalOrderId)` chỉ được xuất hiện một lần. Hai tenant khác nhau vẫn có thể dùng cùng `externalOrderId`.

Nếu tên khóa chỉ duy nhất trong một hệ thống nguồn, có thể cần `{ sourceSystem, tenantId, externalOrderId }`. Nếu đơn hàng được xác định theo từng đợt/lần mở, có thể cần thêm `batchId`. **Định nghĩa khóa phải khớp chính xác ý nghĩa “trùng” trong nghiệp vụ.**

### 4.3. Field thiếu, `null` và chuẩn hóa khóa

Unique index không thay thế kiểm tra kiểu hoặc field bắt buộc. Với unique index ghép, việc thiếu hoặc có `null` ở một thành phần vẫn tham gia vào các khóa index theo quy tắc của MongoDB; nếu ứng dụng không kiểm soát, các document thiếu trường có thể tạo xung đột khó hiểu.

Nên có hai lớp:

1. **Ứng dụng** kiểm tra `tenantId` và `externalOrderId`, loại bỏ input không hợp lệ, chuẩn hóa theo chính sách.
2. **Schema validation** yêu cầu các field có mặt và đúng kiểu BSON; unique index bảo vệ tính duy nhất khi ghi đồng thời.

Nếu một email được dùng làm khóa nghiệp vụ, cần quyết định liệu `"User@Example.com"` và `"user@example.com"` có cùng định danh không. Có thể dùng một field `normalizedEmail` được chuẩn hóa theo chính sách và index unique, hoặc collation phù hợp. Quy tắc collation của unique index ảnh hưởng trực tiếp tới định nghĩa trùng; không tự ý đổi nó khi đã có dữ liệu.

### 4.4. Tạo unique index khi collection đã có dữ liệu

Nếu có document trùng khóa từ trước, lệnh tạo unique index có thể thất bại. Quy trình hợp lý là:

- Xác định khóa nghiệp vụ chuẩn.
- Kiểm tra các bản ghi trùng theo đúng key, kiểu và collation dự kiến.
- Giải quyết bản ghi cũ theo chính sách, giữ lại lịch sử hoặc hợp nhất có kiểm soát.
- Tạo index và chỉ cho các writer tương thích tiếp tục ghi.

Không “sửa” lỗi tạo index bằng cách tắt unique nếu hệ thống thực sự cần ràng buộc không trùng.

## 5. Thực hành: upsert không ghi đè đơn hàng đã tạo

### 5.1. Tạo môi trường thử nghiệm tách biệt

Các ví dụ sau chỉ dùng database `mongo_upsert_row121_lab` và collection `orders_demo` do người học sở hữu. Nếu làm việc trên MongoDB chung, cần xác nhận quyền quản lý collection/index trước khi chạy. Trong `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_upsert_row121_lab");
const orders = lab.getCollection("orders_demo");

// Nhận diện riêng từng lượt thực hành.
const runId = "row121-" + new ObjectId().toHexString();
const tenantId = runId;

print("database=" + lab.getName());
print("runId=" + runId);

orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uniq_tenant_external_order" }
);
```

Dùng `tenantId = runId` trong demo để các lượt thực hành khác nhau không giẫm lên cùng khóa nghiệp vụ. Trong hệ thống thật, `tenantId` phải lấy từ ngữ cảnh xác thực của server, không phải giá trị tùy ý do client cung cấp.

### 5.2. Chèn nếu chưa tồn tại

```javascript
const key = {
  tenantId: tenantId,
  externalOrderId: "EXT-1001"
};

const first = orders.updateOne(
  key,
  {
    $setOnInsert: {
      runId: runId,
      sourceSystem: "partner-api",
      customerId: "C-001",
      amountCents: NumberLong("125000"),
      status: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(first);
printjson(orders.findOne(key));
```

Ở nhánh insert, MongoDB tạo document với các điều kiện equality trong `key` và những field do `$setOnInsert` cung cấp. Ví dụ dữ liệu lưu:

```javascript
{
  _id: ObjectId("..."),
  tenantId: "row121-...",
  externalOrderId: "EXT-1001",
  runId: "row121-...",
  sourceSystem: "partner-api",
  customerId: "C-001",
  amountCents: NumberLong("125000"),
  status: "RECEIVED",
  createdAt: ISODate("...")
}
```

`NumberLong("125000")` chỉ rõ kiểu số nguyên 64 bit trong shell; với tiền tệ, hệ thống thường lựa chọn số nguyên theo đơn vị nhỏ nhất hoặc `Decimal128` tùy yêu cầu.

### 5.3. Gọi lại cùng yêu cầu

Chạy lần nữa với cùng `key`:

```javascript
const second = orders.updateOne(
  key,
  {
    $setOnInsert: {
      runId: runId,
      sourceSystem: "partner-api",
      customerId: "C-001",
      amountCents: NumberLong("125000"),
      status: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(second);
print("matchingDocuments=" + orders.countDocuments(key));
printjson(orders.findOne(key));
```

Lần đầu thường có `upsertedCount: 1`; lần thứ hai thường có `matchedCount: 1`, `upsertedCount: 0` và `modifiedCount: 0`. Chỉ có **một document** theo cặp khóa. Giá trị `createdAt` đã ghi lần đầu không bị thay đổi chỉ vì gọi lại.

Lưu ý: trong ví dụ, `new Date()` vẫn được client tính ở lần gọi thứ hai, nhưng do MongoDB đi vào nhánh đã khớp nên giá trị đó **không được ghi** bằng `$setOnInsert`.

### 5.4. Chứng minh `$setOnInsert` không đặt lại trạng thái

Giả sử workflow chuyển đơn hàng từ `RECEIVED` sang `APPROVED`:

```javascript
const approved = orders.updateOne(
  { ...key, status: "RECEIVED" },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    }
  }
);

printjson(approved);
```

Sau đó replay message tạo đơn hàng:

```javascript
orders.updateOne(
  key,
  {
    $setOnInsert: {
      runId: runId,
      status: "RECEIVED",
      amountCents: NumberLong("125000"),
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(orders.findOne(key, {
  _id: 0,
  status: 1,
  approvedAt: 1,
  createdAt: 1
}));
```

`status` vẫn là `APPROVED` vì upsert đã tìm thấy document và `$setOnInsert` không áp dụng. Đây là mô hình **khởi tạo một lần, cho phép sự kiện tạo đến lặp lại**.

## 6. Race condition: hai upsert cùng nhìn thấy “chưa tồn tại”

### 6.1. Vấn đề khi không có unique index

Hãy hình dung hai worker W1 và W2 đồng thời xử lý cùng external order:

```text
Thời gian       Worker W1                     Worker W2
    |       updateOne(key, upsert)        updateOne(key, upsert)
    |       chưa thấy document           chưa thấy document
    |                |                           |
    |           thử INSERT                  thử INSERT
    |                |                           |
    v          INSERT thành công           INSERT thành công

Kết quả nếu không có ràng buộc duy nhất thích hợp:
hai document cùng khóa nghiệp vụ có thể cùng tồn tại.
```

Đừng suy luận rằng MongoDB khóa toàn bộ collection giữa bước tìm và bước insert cho mọi upsert. Một thao tác ghi lên **một document** có tính nguyên tử, nhưng điều đó không tự tạo ra ràng buộc duy nhất cho một predicate khi document chưa tồn tại.

`upsert` là chức năng “cập nhật nếu có, chèn nếu chưa có”. **Unique index** là cơ chế “không chấp nhận hai document cùng khóa”.

### 6.2. Có unique index thì chuyện gì xảy ra?

Nếu cả hai worker cùng upsert khóa `{tenantId, externalOrderId}` và có unique index phù hợp, database không thể lưu hai document mang cùng khóa.

Một trong các kết quả có thể xảy ra:

- Một worker chèn thành công; worker còn lại nhận ra document đã có và thực hiện nhánh update.
- Một worker chèn thành công; worker kia gặp lỗi **duplicate key** khi cố insert cùng khóa.

MongoDB có một số điều kiện để upsert đang tranh chấp một unique key có thể chuyển sang nhánh update, ví dụ bộ lọc equality phù hợp với khóa unique và cập nhật không thay đổi các field khóa; không nên giả định **mọi** upsert cạnh tranh đều âm thầm trở thành update. Một đường đi an toàn ở ứng dụng phải xử lý cả thành công, no-op và lỗi trùng khóa.

### 6.3. Mã lỗi `E11000`

Khi một thao tác vi phạm unique index, MongoDB thường trả lỗi có mã **`11000`**, thường hiển thị dưới dạng `E11000 duplicate key error`.

Điều quan trọng là phải xác định **unique constraint nào** bị vi phạm. Một collection có thể có nhiều unique index, chẳng hạn một index theo external order và một index khác theo mã giao dịch. Không nên bắt mọi lỗi `11000` rồi coi là “đơn hàng này đã tồn tại” mà bỏ qua dữ liệu mới.

Khi gặp lỗi, ứng dụng có thể tra cứu document theo **khóa nghiệp vụ mong đợi**, xác minh nội dung tương thích với request, rồi trả kết quả thích hợp. Nếu không tìm thấy document cùng khóa hoặc dữ liệu khác nhau, cần giữ lỗi để điều tra hoặc trả thông báo xung đột.

## 7. Không làm upsert bằng “find trước, insert sau”

Mẫu code sau dễ gặp race:

```javascript
// Pseudocode dễ gặp race condition:
const existing = await orders.findOne(key);
if (!existing) {
  await orders.insertOne(newOrder);
}
```

Hai request có thể cùng đọc kết quả `null` rồi cùng gọi `insertOne`. Nếu thiếu unique index, kết quả có thể có hai bản ghi trùng. Nếu có unique index, một lần insert sẽ bị từ chối và ứng dụng vẫn cần xử lý xung đột.

Phù hợp hơn cho bài toán khởi tạo một lần là:

```javascript
await orders.updateOne(
  key,
  { $setOnInsert: insertOnlyFields },
  { upsert: true }
);
```

Tuy nhiên, **unique index vẫn cần thiết** để bảo vệ trường hợp các request chạy đồng thời. Một lời gọi `updateOne` không thay thế index.

Đối với nghiệp vụ bắt buộc “chỉ insert, nếu tồn tại phải trả conflict”, có thể dùng `insertOne` kết hợp unique index thay vì dùng upsert. Lựa chọn giữa `insertOne` và upsert phụ thuộc vào semantics của API: “create một lần” và “ensure exists” không hoàn toàn giống nhau.

## 8. Idempotency: lặp yêu cầu mà không lặp tác dụng

### 8.1. Định nghĩa theo nghiệp vụ

Một thao tác **idempotent** có nghĩa là thực hiện nhiều lần với cùng đầu vào dẫn tới cùng kết quả nghiệp vụ quan trọng như thực hiện một lần. Với lệnh “đảm bảo đơn hàng tồn tại”, `$setOnInsert` cộng unique index có thể giúp tránh tạo nhiều đơn hàng.

Nhưng “không tạo document thứ hai” **chưa có nghĩa mọi side effect đều an toàn**. Ví dụ sau không idempotent nếu retry:

```javascript
db.accounts.updateOne(
  { _id: "ACCOUNT-1" },
  { $inc: { balanceCents: -50000 } }
);
```

Mỗi lần chạy thành công sẽ trừ thêm tiền. Nếu request bị phát lại, việc trừ tiền có thể diễn ra nhiều lần. Dùng `upsert: true` không giải quyết vấn đề này.

### 8.2. Khóa idempotency và nội dung request

Một mô hình phổ biến là client hoặc hệ thống nguồn gửi `idempotencyKey` để định danh **một thao tác nghiệp vụ**. Server lưu khóa này cùng **fingerprint nội dung được chuẩn hóa**.

Ví dụ:

```javascript
{
  tenantId: "TENANT-A",
  idempotencyKey: "PAYMENT-REQUEST-8db7",
  requestFingerprint: "sha256-of-canonical-fields",
  status: "PENDING",
  createdAt: ISODate("2026-11-14T03:00:00Z")
}
```

Hai request có cùng `tenantId` và `idempotencyKey`:

- Nếu nội dung nghiệp vụ tương đương, trả lại kết quả đã tạo/xử lý.
- Nếu nội dung nghiệp vụ khác, trả **conflict** để tránh sử dụng cùng một khóa cho hai thao tác khác nhau.

Fingerprint cần được **tính phía server từ dữ liệu đã chuẩn hóa**, với quy tắc canonicalization nhất quán; không tin một chuỗi hash tùy ý do client tự khai báo. Cũng không nên đưa các trường thay đổi ngẫu nhiên như `receivedAt` vào fingerprint nếu chúng không thuộc ý nghĩa nghiệp vụ.

### 8.3. Không ghi đè dữ liệu quan trọng khi replay

Với cùng idempotency key, một request phát lại không nên:

- đặt trạng thái workflow đã tiến xa trở về trạng thái ban đầu;
- cập nhật lại số tiền theo một payload khác;
- tạo thêm giao dịch thanh toán;
- gửi lặp email/notification có tác động;
- phát lại event mà downstream không có bảo vệ trùng.

`$setOnInsert` là một công cụ hữu ích để tạo bản ghi gốc **một lần**. Các side effect bên ngoài MongoDB cần cơ chế phối hợp riêng như idempotent consumer, transactional outbox hoặc quy trình lưu trạng thái xử lý có kiểm soát.

## 9. Ví dụ Node.js: ensure một đơn hàng tồn tại trong cạnh tranh ghi

Đoạn code sau minh họa một hàm dịch vụ dùng MongoDB Node.js driver. Giả định collection đã có **unique index** trên `{tenantId: 1, externalOrderId: 1}` và input đã được server kiểm tra, chuẩn hóa.

```javascript
// orderService.js - MongoDB Node.js driver
async function ensureOrder(orders, input) {
  const key = {
    tenantId: input.tenantId,
    externalOrderId: input.externalOrderId
  };

  // Fingerprint được tầng ứng dụng tính từ payload đã chuẩn hóa.
  const requestFingerprint = input.requestFingerprint;
  const insertOnly = {
    requestFingerprint,
    amountCents: input.amountCents,
    customerId: input.customerId,
    status: "RECEIVED",
    createdAt: new Date()
  };

  async function verifyExisting() {
    const existing = await orders.findOne(key);
    if (!existing) {
      return null;
    }
    if (existing.requestFingerprint !== requestFingerprint) {
      const conflict = new Error("ORDER_PAYLOAD_CONFLICT");
      conflict.code = "ORDER_PAYLOAD_CONFLICT";
      throw conflict;
    }
    return existing;
  }

  try {
    const result = await orders.updateOne(
      key,
      { $setOnInsert: insertOnly },
      { upsert: true }
    );

    // Lấy document hiện có (vừa chèn hoặc đã tồn tại).
    const order = await verifyExisting();
    if (!order) {
      throw new Error("ORDER_NOT_VISIBLE_AFTER_UPSERT");
    }

    return {
      order,
      inserted: result.upsertedCount === 1
    };
  } catch (err) {
    // Một unique upsert cạnh tranh có thể tạo E11000.
    if (err?.code !== 11000) {
      throw err;
    }

    // Chỉ coi là retry an toàn nếu tìm được đúng khóa và payload.
    const existing = await verifyExisting();
    if (!existing) {
      // Có thể là một unique index khác; giữ nguyên lỗi để xử lý.
      throw err;
    }

    return { order: existing, inserted: false };
  }
}
```

Ví dụ trên có một số giả định cần ghi rõ:

1. `tenantId`, `externalOrderId` phải có kiểu và cách chuẩn hóa nhất quán, và collection thực sự có unique index khớp hai field.
2. `requestFingerprint` được tính từ những field tạo nên **ý nghĩa đơn hàng**. Nếu request lại cùng khóa mà fingerprint khác, không ghi đè; báo conflict.
3. `amountCents` phải được chuyển sang kiểu BSON số phù hợp với schema của dự án (ví dụ `Long` hoặc `Int32` trong driver), tránh trộn kiểu không chủ đích.
4. Hàm trả lại document sau khi ghi; trong hệ thống replica set có chính sách đọc/ghi đặc thù, cần cấu hình read preference, read concern, write concern phù hợp với mức nhất quán mong muốn.
5. Trong trường hợp MongoDB trả lỗi mạng hoặc không rõ lệnh ghi đã được áp dụng chưa, ứng dụng cần chính sách retry có giới hạn và tra cứu lại theo khóa idempotency. Không mặc định tất cả lỗi có thể retry vô hạn.
6. Hàm chưa bao gồm thanh toán, gửi email hay phát event; những side effect đó đòi hỏi thiết kế idempotency riêng.

Vì `verifyExisting()` chỉ trả thành công khi tìm được document **đúng khóa và đúng fingerprint**, một lỗi unique phát sinh từ index khác sẽ không được che giấu thành kết quả thành công nếu document mong đợi chưa có.

### 9.1. Nếu muốn trả về ngay document sau upsert

Một lựa chọn khác là `findOneAndUpdate()` với `upsert: true` và `returnDocument: "after"`:

```javascript
const order = await orders.findOneAndUpdate(
  { tenantId, externalOrderId },
  {
    $setOnInsert: {
      status: "RECEIVED",
      createdAt: new Date(),
      requestFingerprint
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
);
```

Tùy phiên bản Node.js driver và tùy chọn `includeResultMetadata`, hàm có thể trả trực tiếp document hoặc một object chứa metadata/result. Chọn kiểu trả về theo phiên bản driver đang dùng. **Việc dùng `findOneAndUpdate` không loại bỏ yêu cầu unique index và xử lý cạnh tranh ghi**.

### 9.2. HTTP/API nên trả trạng thái thế nào?

Một API “đảm bảo tồn tại” có thể quy định:

| Tình huống | Phản hồi thường gặp |
| --- | --- |
| Tạo lần đầu | `201 Created`, trả ID hoặc resource |
| Yêu cầu lặp lại cùng khóa, cùng payload | `200 OK` hoặc trả lại kết quả trước đó theo API contract |
| Cùng idempotency key nhưng payload khác | `409 Conflict` |
| Input sai định dạng/thiếu field | `400 Bad Request` |
| Không có quyền đối với tenant | `403 Forbidden` hoặc trạng thái phù hợp với chính sách bảo mật |
| MongoDB tạm thời không khả dụng | Lỗi hệ thống thích hợp, có cơ chế retry/quan sát |

Không trả nguyên thông tin unique index, stack trace hoặc connection string ra client. Dữ liệu lỗi dành cho log có thể bao gồm operation ID, tên index và mã lỗi, nhưng cần tránh lộ thông tin nhạy cảm.

## 10. Bẫy nguy hiểm: upsert với filter không khớp đúng khóa unique

### 10.1. Thêm trạng thái vào filter một cách vô tình

Giả sử unique index là `{ tenantId: 1, externalOrderId: 1 }` và đã có document:

```javascript
{
  tenantId: "TENANT-A",
  externalOrderId: "EXT-001",
  status: "APPROVED"
}
```

Một worker thử:

```javascript
db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    externalOrderId: "EXT-001",
    status: "RECEIVED"
  },
  { $set: { status: "APPROVED" } },
  { upsert: true }
);
```

Document hiện có **không khớp** vì `status` đã là `APPROVED`. Với `upsert: true`, server có thể cố chèn document mới có cùng `tenantId` và `externalOrderId`; unique index từ chối với `E11000`. Nếu thiếu unique index, có nguy cơ tạo bản ghi trùng.

Nếu mục tiêu thực sự là “chỉ chuyển `RECEIVED` sang `APPROVED`”, hãy dùng **update có điều kiện nhưng không upsert**:

```javascript
const result = db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    externalOrderId: "EXT-001",
    status: "RECEIVED"
  },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    }
  }
);

printjson(result);
```

Nếu `matchedCount: 0`, ứng dụng xử lý trường hợp đã chuyển trạng thái, không tồn tại hoặc không còn hợp lệ. Không tự chuyển sang upsert để “chữa” việc không tìm thấy.

### 10.2. Filter chỉ có điều kiện khoảng không biểu diễn một key

```javascript
// Không phù hợp cho nghiệp vụ "mỗi external ID chỉ có một order".
db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    createdAt: { $gte: ISODate("2026-11-14T00:00:00Z") }
  },
  { $set: { status: "RECEIVED" } },
  { upsert: true }
);
```

Filter này không xác định một external order cụ thể; có thể cập nhật một document không mong muốn hoặc chèn document thiếu khóa nghiệp vụ. Để tránh trùng, filter upsert nên dựa trên equality của **bộ khóa duy nhất đầy đủ**. Các điều kiện nghiệp vụ như status, version và thời gian thường nên được áp dụng ở bước ghi có điều kiện khác.

### 10.3. `updateMany` với upsert không phải lời giải cho trùng khóa

`updateMany` có thể cập nhật nhiều document đang khớp; khi đặt `upsert: true` và không có document nào khớp, nó có thể chèn một document. Nó không phù hợp để biến mỗi bản ghi nguồn thành một document đích riêng chỉ qua một lời gọi filter rộng. Nếu xử lý batch, hãy xây dựng một upsert cho **mỗi khóa nghiệp vụ** và có unique index bảo vệ.

## 11. Cạnh tranh ghi, retry và transaction

### 11.1. Retry phải dựa trên tính chất thao tác

Một request có thể không nhận được phản hồi dù server đã ghi thành công. Khi retry:

- `$setOnInsert` trên khóa duy nhất cùng fingerprint thường có thể được dùng để **ensure một document**.
- `$set` đặt lại cùng giá trị có thể an toàn về giá trị cuối cùng, nhưng có thể vẫn làm thay đổi `updatedAt` hoặc kích hoạt quy trình khác nếu ứng dụng thiết kế như vậy.
- `$inc`, `$push`, cộng điểm hoặc trừ tiền có thể gây **thay đổi thêm mỗi lần chạy thành công**.
- Các side effect ngoài MongoDB như gửi email hoặc gọi cổng thanh toán phải được bảo vệ bằng cơ chế riêng.

MongoDB driver có cơ chế *retryable writes* trong những điều kiện và topology phù hợp. Tuy nhiên, cơ chế retry của driver không thay thế **idempotency ở cấp nghiệp vụ**, đặc biệt khi client/API phát lại cùng một yêu cầu thành request mới.

### 11.2. Transaction có thay unique index không?

**Không.** Transaction giúp phối hợp thay đổi trên nhiều document/collection theo một đơn vị commit, nhưng không tự tạo ràng buộc “mỗi `externalOrderId` chỉ có một order” nếu thiếu unique index.

Ví dụ quy trình “tạo đơn hàng và ghi một outbox event” có thể cần transaction để hai document cùng tồn tại hoặc cùng rollback. Unique index trên khóa đơn hàng vẫn bảo vệ trường hợp hai request đồng thời; ứng dụng phải xử lý lỗi duplicate/write conflict và retry phù hợp.

Luồng có thể là:

```text
Nhận request có idempotency key
              |
              v
      Chuẩn hóa + xác thực
              |
              v
  Upsert theo khóa + unique index
        /           |            \
   inserted       matched       E11000
       |             |             |
       v             v             v
  Xử lý mới     Đối chiếu     Tra cứu đúng key,
                fingerprint  đối chiếu fingerprint
       \             |             /
        \------------+------------/
                     |
                     v
           Trả kết quả nhất quán
```

Khi side effect cần ghi ở collection khác hoặc phát ra ngoài, cần mở rộng thiết kế transaction/outbox và quản lý trạng thái “đã xử lý” một cách rõ ràng.

### 11.3. Giao dịch không giải quyết khóa nghiệp vụ sai

Nếu một service chọn khóa `externalOrderId` toàn cục trong khi thực tế mã chỉ duy nhất theo `tenantId`, unique index toàn cục sẽ từ chối các đơn hợp lệ từ tenant khác. Nếu một service không chuẩn hóa mã nguồn, `"ORD-1"` và `"ord-1"` có thể bị coi là hai khóa khác nhau khi nghiệp vụ muốn chúng là một. Transaction không sửa được các lỗi mô hình hóa này; cần xác định bộ khóa và collation/normalization trước.

## 12. Các mô hình phổ biến cần cân nhắc

### 12.1. Tạo cấu hình mặc định khi chưa tồn tại

```javascript
db.userSettings.updateOne(
  { userId: ObjectId("66a000000000000000000001") },
  {
    $setOnInsert: {
      theme: "light",
      language: "vi",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

Cần unique index trên `userId` để không tạo hai setting khi nhiều request cùng khởi tạo. Một request sau đó đổi `theme` thành `dark`; upsert lặp lại không được đặt về `light`.

### 12.2. Đồng bộ dữ liệu bên ngoài

```javascript
db.products.updateOne(
  { sourceSystem: "ERP", sourceId: "SKU-1001" },
  {
    $set: {
      displayName: "Bàn phím",
      priceCents: 125000,
      sourceVersion: 12,
      syncedAt: new Date()
    },
    $setOnInsert: {
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

Index unique bảo vệ `{sourceSystem, sourceId}`. Nhưng nếu message đến **sai thứ tự**, bản cập nhật phiên bản 11 có thể ghi đè phiên bản 12 nếu chỉ dùng `$set` như trên. Bảo vệ thứ tự còn cần so sánh version và thiết kế cập nhật có điều kiện phù hợp; không nhầm “không trùng document” với “không ghi dữ liệu cũ”.

### 12.3. Khóa mềm (soft delete) và yêu cầu tạo lại

Giả sử document có `deletedAt`. Câu hỏi nghiệp vụ: cùng một `externalOrderId` sau khi soft delete có được tạo bản ghi mới không?

- Nếu **không**, dùng unique index toàn cục cho khóa nghiệp vụ và phục hồi/cập nhật document cũ theo quy trình.
- Nếu **có**, có thể cần một khóa chứa phiên bản/lần tạo, hoặc partial unique index chỉ áp dụng cho bản ghi active.

Ví dụ khái niệm partial index:

```javascript
db.contacts.createIndex(
  { tenantId: 1, normalizedEmail: 1 },
  {
    unique: true,
    partialFilterExpression: { active: true },
    name: "uniq_active_email_per_tenant"
  }
);
```

Index trên chỉ bảo vệ tính duy nhất của những document thuộc phạm vi filter `active: true`. Bản ghi không thuộc phạm vi đó có thể trùng khóa; khi chuyển từ inactive sang active vẫn phải chịu unique constraint. Upsert cần được thiết kế cùng điều kiện active và quy tắc vòng đời để không tạo dữ liệu bất ngờ. Ví dụ chỉ để giải thích chiến lược index; không áp dụng lên collection thật mà chưa đánh giá dữ liệu hiện có.

### 12.4. Unique index trong môi trường sharding

Khi collection được shard, khả năng thực thi unique index có thêm yêu cầu về cấu trúc index và shard key tùy phiên bản/topology MongoDB. Trước khi chọn khóa unique cho hệ thống phân tán, cần xác nhận ràng buộc mà triển khai hiện tại hỗ trợ. Không giả định index hoạt động y hệt trong mọi cấu hình chỉ vì nó chạy được trên một MongoDB local.

## 13. Những lỗi thiết kế dễ gặp

| Cách làm | Vấn đề | Hướng giải quyết |
| --- | --- | --- |
| Upsert theo external ID mà không có unique index | Hai request đồng thời có thể tạo hai document | Unique index theo khóa nghiệp vụ đầy đủ |
| Chỉ dựa vào `_id` tự sinh | Mỗi lần retry có `_id` mới | Dùng khóa idempotency/khóa nghiệp vụ ổn định |
| Dùng `$set` cho `createdAt` | Mỗi replay làm thay đổi thời điểm tạo | `$setOnInsert` cho các field chỉ khởi tạo |
| Dùng `$set` để đặt lại trạng thái ban đầu | Đơn hàng đã tiến trình có thể bị kéo lùi | `$setOnInsert`, chuyển trạng thái bằng update có điều kiện |
| Gắn `status` vào filter upsert | Không khớp sau khi đổi trạng thái, có thể cố insert và gặp E11000 | Tách “ensure exists” khỏi “update-if-status” |
| Bắt mọi `E11000` và trả thành công | Có thể che xung đột của unique index khác | Tra cứu đúng key, kiểm fingerprint, phân loại lỗi |
| Retry vô hạn khi gặp lỗi mạng/duplicate | Tăng tải, có thể lặp side effect | Retry có giới hạn, backoff và idempotency |
| Dùng `$inc` trong request có thể phát lại | Giá trị bị tăng/giảm nhiều lần | Mô hình thao tác có ID duy nhất, kiểm soát xử lý một lần |
| Unique index trên sai phạm vi | Chặn đơn hợp lệ hoặc để trùng | Thiết kế khóa theo tenant, source, kỳ hoặc phiên bản đúng nghiệp vụ |
| Không thống nhất kiểu và chuẩn hóa khóa | Chuỗi/ObjectId khác kiểu; case khác nhau dẫn tới nhiều khóa | Chuẩn hóa ở ứng dụng, schema validation, collation có chủ đích |
| Tạo index unique khi có dữ liệu trùng | Tạo index thất bại | Kiểm tra và xử lý dữ liệu cũ trước migration |
| Kỳ vọng transaction tự chống trùng | Hai thao tác vẫn có thể cạnh tranh khóa nghiệp vụ | Unique index vẫn bắt buộc cho bất biến duy nhất |

## 14. Bài thực hành kiểm soát cạnh tranh ghi

### 14.1. Tạo hai lời gọi cùng khóa ở mức khái niệm

Nếu môi trường của bạn có Node.js và MongoDB Node.js driver, có thể dùng hai promise để khởi tạo cùng khóa trong database thử nghiệm. Ví dụ sau giả định đã có biến `orders` là MongoDB collection từ Node.js driver và unique index tồn tại:

```javascript
async function attemptCreate(label) {
  try {
    const result = await orders.updateOne(
      { tenantId: "RACE-TEST-121", externalOrderId: "EXT-RACE" },
      {
        $setOnInsert: {
          status: "RECEIVED",
          createdBy: label,
          createdAt: new Date()
        }
      },
      { upsert: true }
    );
    return { label, kind: "success", result };
  } catch (error) {
    return { label, kind: "error", code: error.code };
  }
}

const outcomes = await Promise.all([
  attemptCreate("worker-A"),
  attemptCreate("worker-B")
]);

console.log(outcomes);
```

Kết quả phụ thuộc lịch thực thi: một lần có thể chèn, lần kia cập nhật/no-op hoặc nhận `11000`. Unique index bảo đảm **không có hai document trùng cặp khóa** được lưu. Chỉ dùng mã khóa được thiết kế riêng cho lượt test và kiểm tra dữ liệu trước khi dọn; ví dụ `"RACE-TEST-121"` cần được thay bằng tenant thử nghiệm duy nhất nếu nhiều người dùng cùng database.

Một lần chạy không tái hiện race không chứng minh hệ thống miễn nhiễm cạnh tranh. Điều bảo vệ tính duy nhất là **cấu hình database và cách ứng dụng xử lý các kết quả hợp lệ**, không phải khả năng tái hiện lỗi ở một máy.

### 14.2. Bài tập: dự đoán kết quả

Giả sử collection có unique index `{tenantId: 1, externalOrderId: 1}` và document:

```javascript
{
  tenantId: "T1",
  externalOrderId: "O1",
  status: "SHIPPED",
  createdAt: ISODate("2026-11-01T01:00:00Z")
}
```

Hãy suy nghĩ về ba câu lệnh:

**A.**

```javascript
db.orders.updateOne(
  { tenantId: "T1", externalOrderId: "O1" },
  { $setOnInsert: { status: "RECEIVED", createdAt: new Date() } },
  { upsert: true }
);
```

**B.**

```javascript
db.orders.updateOne(
  { tenantId: "T1", externalOrderId: "O1" },
  { $set: { status: "RECEIVED" } },
  { upsert: true }
);
```

**C.**

```javascript
db.orders.updateOne(
  { tenantId: "T1", externalOrderId: "O1", status: "RECEIVED" },
  { $set: { status: "SHIPPED" } },
  { upsert: true }
);
```

Điểm cần giải thích: A không đặt lại `SHIPPED`; B có thể ghi đè trạng thái về `RECEIVED`; C không khớp vì trạng thái hiện tại khác `RECEIVED` và có thể cố insert rồi vấp unique index. Với nghiệp vụ chuyển trạng thái, chọn update có điều kiện **không upsert**.

### 14.3. Quan sát index và số document theo khóa

Trong phiên `mongosh` ở mục 5:

```javascript
printjson(orders.getIndexes());
print("matched=" + orders.countDocuments(key));
printjson(orders.findOne(key));
```

`getIndexes()` cho biết thông tin index mà collection có. Với dữ liệu mẫu và khóa `key` chưa bị xóa, `matched` dự kiến bằng `1`. Số lượng là quan sát tại thời điểm truy vấn; dữ liệu có thể thay đổi nếu một writer khác đang chạy.

## 15. Dọn dữ liệu thực hành an toàn

Để tránh xóa nhầm, chỉ dọn các document thuộc `runId` của lượt thực hành. Kiểm tra trước:

```javascript
print("database=" + lab.getName());
print("collection=" + orders.getName());
print("runId=" + runId);

const preview = orders.find(
  { runId: runId },
  { _id: 1, tenantId: 1, externalOrderId: 1, runId: 1 }
).toArray();

printjson(preview);
print("matchedByRunId=" + orders.countDocuments({ runId: runId }));
```

Nếu đúng là **một** document có `externalOrderId: "EXT-1001"` do bạn tạo ở mục 5, xóa bằng bộ khóa đầy đủ và `runId`:

```javascript
const cleanupFilter = {
  tenantId: tenantId,
  externalOrderId: "EXT-1001",
  runId: runId
};

printjson(orders.findOne(cleanupFilter));
const deletion = orders.deleteOne(cleanupFilter);
printjson(deletion);
print("remaining=" + orders.countDocuments(cleanupFilter));
```

Trường hợp bình thường `deletedCount: 1` và `remaining: 0`. Nếu không còn document hoặc kết quả xem trước không đúng, **dừng lại để xác định môi trường**, không mở rộng bộ lọc tùy tiện. Unique index vẫn nằm trong collection sau khi xóa document; trên môi trường dùng chung, không tự `drop()` hoặc `dropDatabase()` để dọn một bài thực hành.

Nếu đã thực hiện bài test cạnh tranh trong Node.js ở mục 14 trên một database thật sự tách biệt, hãy kiểm tra đúng tenant thử nghiệm và bản ghi của bài test đó trước khi xóa. Không xóa theo một khóa chung như `RACE-TEST-121` nếu nó có thể trùng với dữ liệu của người khác.

## 16. Câu hỏi tự kiểm tra

1. `upsert: true` có nghĩa gì khi filter đã khớp một document? Khi không khớp thì sao?
2. `$setOnInsert` có đặt giá trị cho một field đang thiếu trên document đã tồn tại hay không?
3. Vì sao `_id` unique mặc định không ngăn hai bản ghi có cùng `externalOrderId` nhưng khác `_id`?
4. Unique index ghép `{tenantId: 1, externalOrderId: 1}` định nghĩa trùng khác index chỉ có `externalOrderId` như thế nào?
5. Khi hai upsert chạy đồng thời, vì sao cần sẵn sàng nhận `E11000` ngay cả khi đã tạo unique index?
6. Vì sao bộ lọc upsert có thêm `status: "PENDING"` dễ gây duplicate key khi document đã chuyển trạng thái?
7. Sự khác biệt giữa “không tạo thêm document” và “idempotent về mọi side effect” là gì?
8. Tại sao không nên dùng `$inc` cho một thao tác có thể bị client phát lại nếu chưa có cơ chế chống xử lý lặp?
9. Khi bắt được `11000`, cần kiểm tra gì trước khi trả về một kết quả thành công cho request lặp?
10. Nếu muốn tạo lại thực thể sau soft delete, cần định nghĩa lại khóa unique hoặc phạm vi index như thế nào?

**Điểm cốt lõi:** `upsert` quyết định **cập nhật hay chèn**, `$setOnInsert` giữ các field **chỉ được tạo lần đầu**, còn **unique index** bảo đảm không lưu hai document trùng khóa nghiệp vụ. Với nhiều yêu cầu đồng thời, ứng dụng vẫn phải xử lý kết quả cạnh tranh, lỗi `11000` và idempotency của toàn bộ quy trình; chỉ kết hợp đúng các lớp này mới tránh được dữ liệu trùng và trạng thái bị ghi đè ngoài ý muốn.
