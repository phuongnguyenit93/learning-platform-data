# fullDocument, updateLookup và pre image, post image

MongoDB **change streams** cho phép ứng dụng theo dõi các thay đổi xảy ra đối với document trong collection, database hoặc deployment được hỗ trợ. Một **change event** có thể được dùng để đồng bộ Redis cache, search index, data warehouse, projection, phát thông báo hoặc ghi nhận lịch sử thay đổi.

Tuy nhiên, đối với thao tác **update**, event thường chỉ chứa **những field được thay đổi**. Nếu consumer cần toàn bộ document, phải lựa chọn cách lấy nội dung. Đặc biệt, có sự khác biệt rất quan trọng giữa **lấy document hiện hành** và **lấy ảnh của document ở đúng thời điểm thay đổi**.

Trong MongoDB, các công cụ liên quan là:

- **`updateDescription`**: cho biết những field được thay đổi hoặc bị xóa trong một `update` event; không phải ảnh đầy đủ của document.
- **`fullDocument: "updateLookup"`**: lấy trạng thái **majority-committed hiện hành tại thời điểm lookup**. Trạng thái này có thể đã chịu tác động của nhiều update xảy ra **sau** event đang xử lý.
- **`fullDocument: "whenAvailable"` / `"required"`**: yêu cầu **post-image**, tức toàn bộ document **ngay sau event** nếu ảnh được capture và còn tồn tại.
- **`fullDocumentBeforeChange: "whenAvailable"` / `"required"`**: yêu cầu **pre-image**, tức toàn bộ document **ngay trước event** nếu ảnh được capture và còn tồn tại.
- **`changeStreamPreAndPostImages.enabled`**: cấu hình collection để bắt đầu lưu pre/post images cho những thay đổi xảy ra **sau khi bật tính năng**.

Điểm mấu chốt:

> **`updateLookup` là tra cứu trạng thái hiện tại, không phải exact post-image của sự kiện.** Nếu muốn ghi nhận chính xác document trước và sau **từng lần update**, phải dùng pre/post images theo cơ chế được MongoDB hỗ trợ và bảo đảm ảnh chưa hết hạn.

Bài học đi từ cấu trúc sự kiện, các mode của `fullDocument`, cách bật pre/post images, vòng đời ảnh, xử lý insert/update/replace/delete, resume token, hiệu năng, bảo mật đến ví dụ thực hành và thiết kế consumer production.

## 1. Change streams trong MongoDB

Change streams được hỗ trợ trên những triển khai MongoDB có cơ chế replication phù hợp, như **replica set** và **sharded cluster**. Một standalone `mongod` thông thường không cung cấp change stream theo cùng cơ chế.

Dòng xử lý khái quát:

```text
Ứng dụng ghi document
          │
          ▼
MongoDB primary
          │
          ├── replication / oplog
          │
          ▼
Thay đổi đủ điều kiện majority commit
          │
          ▼
Change stream event
          │
          ▼
Consumer
   ├── Redis invalidation
   ├── Search indexing
   ├── Analytics projection
   ├── CDC
   └── Audit pipeline
```

Change streams phát các sự kiện theo cơ chế **majority-committed changes** được server hỗ trợ; không phải mọi ghi chỉ mới xuất hiện thoáng qua ở primary với `w: 1` đều trở thành một event bền vững.

Trong `mongosh` có thể mở stream:

```javascript
const stream = db.orders.watch();

while (stream.hasNext()) {
  const event = stream.next();
  printjson(event);
}
```

Vòng lặp có thể chờ lâu để nhận event. Khi thực hành nên mở **hai terminal**: terminal A chờ change stream, terminal B ghi dữ liệu.

### 1.1. Các operation types cần xử lý

| `operationType` | Ý nghĩa | Dữ liệu thường cần |
|---|---|---|
| `"insert"` | Thêm document | Document vừa insert |
| `"update"` | Thay đổi một phần document | `updateDescription`, pre/post nếu cần |
| `"replace"` | Thay thế nội dung document | Document mới và có thể pre-image |
| `"delete"` | Xóa document | `documentKey`, pre-image nếu cần |
| `"drop"` | Drop collection | Metadata sự kiện |
| `"rename"` | Đổi tên collection | Metadata sự kiện |
| `"invalidate"` | Luồng hiện hành bị vô hiệu trong ngữ cảnh hỗ trợ | Xử lý đóng/resume lại phù hợp |

Một số sự kiện mở rộng và cấu trúc metadata khác phụ thuộc phiên bản MongoDB và các tùy chọn như `showExpandedEvents`. Không được giả định mọi event đều là `update`.

### 1.2. Cấu trúc change event

Một sự kiện update có dạng minh họa:

```javascript
{
  _id: { token: "opaque-resume-token-placeholder" },
  operationType: "update",
  clusterTime: Timestamp(1772340000, 1),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: "ORDER-274"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

Đây **chỉ là ví dụ giản lược để đọc cấu trúc**, không phải resume token thật. Trong thực tế:

- **`event._id`** là một **opaque resume token**, không phải `_id` của document đơn hàng.
- **`documentKey`** giúp xác định document; trên sharded collection có thể chứa thêm các thành phần shard key.
- **`clusterTime`** là logical timestamp do MongoDB cung cấp, không phải thời điểm consumer nhận event.
- **`updateDescription`** mô tả delta của update.
- **`fullDocument`** và **`fullDocumentBeforeChange`** có hoặc không tùy loại operation, mode và khả năng cung cấp ảnh.

Không tự parse resume token để suy ra version nghiệp vụ hoặc timestamp chi tiết.

## 2. Vì sao update event mặc định không chứa toàn bộ document?

Giả sử document:

```javascript
{
  _id: "ORDER-274",
  customerId: "C-10",
  status: "NEW",
  total: NumberDecimal("125000.00"),
  shipping: {
    city: "Hà Nội",
    method: "STANDARD"
  }
}
```

Ứng dụng chạy:

```javascript
db.orders.updateOne(
  { _id: "ORDER-274" },
  {
    $set: {
      status: "PAID",
      "shipping.method": "EXPRESS"
    }
  }
);
```

Một update event có thể cho:

```javascript
{
  operationType: "update",
  documentKey: { _id: "ORDER-274" },
  updateDescription: {
    updatedFields: {
      status: "PAID",
      "shipping.method": "EXPRESS"
    },
    removedFields: []
  }
}
```

Sự kiện không cần gửi lại `customerId`, `total` và mọi field khác vì chúng không phải là phần thay đổi. Điều này giúp giảm kích thước thông báo trong trường hợp update chỉ sửa một vài field.

### 2.1. `updatedFields`, `removedFields` và array

Các trường thông dụng:

- `updatedFields`: map đường dẫn field → giá trị sau thay đổi;
- `removedFields`: danh sách field bị xóa;
- `truncatedArrays`: thông tin khi một số thao tác làm ngắn array, tùy event;
- Các biểu diễn đường dẫn bổ sung như `disambiguatedPaths` ở những phiên bản hỗ trợ.

Ví dụ:

```javascript
db.orders.updateOne(
  { _id: "ORDER-274" },
  {
    $set: { status: "SHIPPED" },
    $unset: { legacyCode: "" }
  }
);
```

Delta có thể tương đương:

```javascript
{
  updatedFields: { status: "SHIPPED" },
  removedFields: ["legacyCode"]
}
```

**Không coi `updateDescription` là JSON Patch chuẩn trong mọi trường hợp.** Array, field chứa dấu chấm, embedded document và các kiểu BSON đặc biệt có quy tắc biểu diễn riêng. Consumer tự áp delta lên một snapshot sai thời điểm có thể tạo ra document khác state thật của MongoDB.

### 2.2. Khi nào chỉ dùng delta là đủ?

- Xóa cache theo `_id`;
- Đếm số lần field đổi;
- Chuyển một vài thay đổi đơn giản sang hệ thống downstream;
- Consumer đã có state đúng và có logic áp delta phù hợp.

Khi cần **toàn bộ document**, **giá trị cũ** hoặc **cặp ảnh trước/sau của một sự kiện**, cần xem các option tiếp theo.

## 3. `fullDocument`: các chế độ quan trọng

Option `fullDocument` được truyền khi mở stream:

```javascript
db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
```

Các chế độ chính:

| Mode | Ý nghĩa đối với update | Điều cần hiểu |
|---|---|---|
| `"default"` | Không yêu cầu lấy full document cho update; thường có delta | Insert/replace thường đã có `fullDocument` |
| `"updateLookup"` | Tra cứu document majority-committed **hiện hành** | Có thể mới hơn trạng thái đúng sau event |
| `"whenAvailable"` | Trả exact **post-image** nếu có | Cần capture được bật trước và ảnh chưa bị dọn |
| `"required"` | Đòi exact post-image; thiếu ảnh khi cần thì lỗi | Không tự tạo hoặc giữ ảnh vô hạn |

Các chế độ dùng pre/post images cần MongoDB 6.0+ theo tính năng, deployment/FCV/driver hỗ trợ.

### 3.1. `fullDocument: "default"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "default" }
);
```

Đối với update, event mặc định tập trung vào `updateDescription`. Đối với insert/replace, `fullDocument` thường biểu diễn document được tạo/thay thế.

Không được hiểu `"default"` nghĩa là tất cả events đều không có `fullDocument`.

### 3.2. `fullDocument: "updateLookup"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
```

Ở update event, MongoDB lookup document theo khóa phù hợp để bổ sung một **bản document hiện hành đã majority committed**.

Lợi ích:

- Consumer có thể lấy full document mà **không cần bật capture pre/post**.
- Phù hợp khi chỉ muốn projection/search index cuối cùng phản ánh state hiện tại.
- Không cần tự áp hàng loạt delta phức tạp.

Hạn chế:

- Không phải ảnh post-state tại chính event.
- Có thêm thao tác đọc và chi phí truyền document đầy đủ.
- Nếu document đã bị xóa trước lookup, `fullDocument` có thể là `null`.
- Khi có nhiều update nhanh, event delta và `fullDocument` có thể mô tả **hai mốc trạng thái khác nhau**.

### 3.3. `fullDocument: "whenAvailable"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "whenAvailable" }
);
```

Với update cần post-image, server trả **ảnh document sau chính update event đó** nếu collection đã bật pre/post images và ảnh còn tồn tại.

Nếu ảnh không có, consumer có thể nhận `null`/không có ảnh tương ứng, thay vì tự động báo lỗi chỉ vì điều đó.

### 3.4. `fullDocument: "required"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "required" }
);
```

Nếu không có post-image cho sự kiện cần ảnh, server báo lỗi để consumer biết **hợp đồng thông tin bắt buộc đã không được đáp ứng**.

Mode required không làm ảnh bị thiếu xuất hiện lại. Nó cũng không buộc delete event có một document tồn tại “sau khi xóa”: post-state của delete không phải một document.

## 4. `updateLookup` không đồng nghĩa exact post-image

Đây là điểm quan trọng nhất khi thiết kế audit/CDC.

Giả sử một document thay đổi liên tiếp:

```text
T0:
  { _id: "O1", status: "NEW",     version: 1 }

T1: Update A
  { _id: "O1", status: "PAID",    version: 2 }
  Event A được phát sinh.

T2: Update B
  { _id: "O1", status: "SHIPPED", version: 3 }
  Event B được phát sinh.

T3: Consumer xử lý event A và MongoDB thực hiện updateLookup.
```

Khi update B đã majority committed ở T3, `fullDocument` bổ sung cho **event A** có thể chứa:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O1" },
  updateDescription: {
    updatedFields: {
      status: "PAID",
      version: 2
    }
  },
  fullDocument: {
    _id: "O1",
    status: "SHIPPED",
    version: 3
  }
}
```

Không có mâu thuẫn:

- **Delta** nói về thay đổi **A**: NEW → PAID.
- **Full document do lookup** nói về trạng thái hiện hành: SHIPPED.

### 4.1. Sai lầm khi xây audit

Nếu một consumer lấy:

```javascript
event.fullDocument.status
```

và ghi rằng đó là “giá trị ngay sau update A”, audit có thể ghi SHIPPED thay vì PAID.

Giải pháp:

- Nếu chỉ cần các field được update: dùng `updateDescription`.
- Nếu cần **document đầy đủ ngay sau update A**: dùng exact post-image.
- Nếu cần **trước và sau A**: dùng cặp pre/post images.
- Nếu cần latest state cho cache/index: updateLookup có thể phù hợp, nhưng không gắn nhãn nó là post-image lịch sử.

### 4.2. `updateLookup` có thể null sau delete

Timeline:

```text
T1: Update O1.
T2: Delete O1.
T3: Consumer tra cứu fullDocument cho event update ở T1.
```

Đến T3, document không còn tồn tại. Lookup có thể không trả được document.

**Không suy rằng một update event có `fullDocument: null` chính là delete event.** Hãy kiểm tra `operationType` và xử lý delete event riêng.

### 4.3. Không bảo đảm demo nào cũng tạo ra race

Trong một bài tập thủ công, updateLookup có thể hoàn thành trước update B nên trả PAID. Nhưng trong workload production có nhiều update và consumer lag, nó **có thể** trả SHIPPED.

Đây là **ngữ nghĩa được thiết kế**, không phải một lỗi xác suất thấp có thể bỏ qua.

## 5. Pre-image và post-image: trạng thái đúng thời điểm event

Xét một update:

```text
                     UPDATE status = "PAID"
                       │
          ┌────────────┴────────────┐
          │                         │
    PRE-IMAGE                 POST-IMAGE
    status = NEW              status = PAID
    version = 1               version = 2
```

- **Pre-image**: document tồn tại **ngay trước** thay đổi.
- **Post-image**: document tồn tại **ngay sau** thay đổi.
- Cặp ảnh mô tả **chính event đang quan sát**, không phải một lần query document ở thời điểm sau đó.

Nếu document sau update A lập tức chịu update B, post-image A vẫn là state **sau A**, còn pre-image B là state **trước B** khi ảnh được capture.

### 5.1. Bảng theo loại sự kiện

| Sự kiện | Pre-image | Post-image / full document |
|---|---|---|
| Insert | Không có document trước insert | Document vừa tạo |
| Update | Document trước update nếu có ảnh | Document sau đúng update nếu có ảnh |
| Replace | Document trước replace nếu có ảnh | Document thay thế |
| Delete | Document trước delete nếu có ảnh | Không còn document sau delete |
| Drop/rename/invalidate | Không phải document pre-image tương ứng | Event metadata, không phải document post-image |

**Delete event là trường hợp pre-image đặc biệt hữu ích:** document đã xóa không thể được tra cứu lại từ collection hiện hành để biết các field cũ.

### 5.2. Pre-image của delete

Delete event bình thường có:

```javascript
{
  operationType: "delete",
  documentKey: { _id: "O1" }
}
```

Nếu muốn cập nhật một số liệu theo `customerId` hoặc ghi audit giá trị tiền của document vừa xóa, `documentKey` có thể không đủ.

Với pre-image có sẵn:

```javascript
{
  operationType: "delete",
  documentKey: { _id: "O1" },
  fullDocumentBeforeChange: {
    _id: "O1",
    customerId: "C-10",
    status: "SHIPPED",
    total: NumberDecimal("125000.00")
  }
}
```

Consumer có thể biết document **đã tồn tại thế nào ngay trước delete**.

### 5.3. Pre/post images không phải backup

Images:

- Không được tạo ngược cho quá khứ trước lúc bật;
- Có retention riêng và còn phụ thuộc oplog window;
- Phát sinh chi phí lưu trữ;
- Không thay thế backup, point-in-time restore hay audit store lâu dài.

Nếu nghiệp vụ cần lịch sử nhiều năm, hãy xây kho audit/event store có retention, access control và khả năng phục hồi độc lập.

## 6. Bật capture pre/post images ở collection

Change stream pre/post images được hỗ trợ từ **MongoDB 6.0** trong những deployment tương thích.

### 6.1. Tạo collection mới

Trên replica set thử nghiệm:

```javascript
use changeImageLab;

db.createCollection(
  "orders",
  {
    changeStreamPreAndPostImages: {
      enabled: true
    }
  }
);
```

### 6.2. Bật trên collection đã tồn tại

```javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
```

Các lệnh này thay đổi cấu hình collection. Không chạy vào production nếu chưa kiểm tra phiên bản, FCV, quyền quản trị, chi phí lưu ảnh và kế hoạch retention.

### 6.3. Bật capture không hồi tố

Giả sử:

```text
T1: Document O1 được update.
T2: Bật changeStreamPreAndPostImages.enabled = true.
T3: O1 được update lần nữa.
```

Ảnh của event T1 **không tự được tạo lại**. Capture có hiệu lực cho các thay đổi xảy ra **sau khi bật** theo quy tắc của server.

Không thể mở stream ở T3 rồi dùng `required` để lấy exact pre/post images của mọi sự kiện tháng trước nếu trước đó collection chưa capture ảnh.

### 6.4. Tắt capture

```javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: false
  }
});
```

Tắt capture cho các thay đổi kế tiếp **không có nghĩa lập tức xóa hết ảnh đã lưu**. Những ảnh trước đó chịu lifecycle/retention được cấu hình.

### 6.5. Bật ở collection và yêu cầu ở consumer là hai bước khác nhau

Khi collection đã bật capture:

```javascript
// Consumer nhẹ: chỉ delta.
db.orders.watch();

// Consumer muốn latest lookup.
db.orders.watch([], {
  fullDocument: "updateLookup"
});

// Consumer muốn exact before/after.
db.orders.watch([], {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
});
```

Mỗi stream quyết định nội dung **được trả cho consumer**, nhưng chi phí capture ở server do cấu hình collection quyết định. Không nên bật image capture cho mọi collection chỉ vì một consumer muốn xem thêm vài field.

## 7. `fullDocumentBeforeChange`: yêu cầu pre-image

Hai chế độ chính:

```javascript
{
  fullDocumentBeforeChange: "whenAvailable"
}
```

hoặc:

```javascript
{
  fullDocumentBeforeChange: "required"
}
```

### 7.1. `"whenAvailable"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocumentBeforeChange: "whenAvailable" }
);
```

Nếu pre-image được capture và còn tồn tại, event update/replace/delete có thể mang `fullDocumentBeforeChange`.

Nếu ảnh không có (chưa bật, bị xóa theo retention...), consumer nhận trường ảnh `null` hoặc không có ảnh hữu ích theo event shape, thay vì tự động ngừng chỉ vì thiếu ảnh.

Thích hợp khi pre-image **là thông tin bổ sung**, không bắt buộc mọi record.

### 7.2. `"required"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocumentBeforeChange: "required" }
);
```

Nếu server không thể cung cấp pre-image **cho một sự kiện cần pre-image**, stream sẽ lỗi. Đây là chọn lựa đúng hơn nếu **audit chính xác** là yêu cầu cứng.

Nhưng:

- Insert tự nhiên không có before-document.
- Delete tự nhiên không có after-document.
- Required không tạo ảnh cho event đã xảy ra trước khi bật.
- Required không kéo dài retention vô hạn.
- Khi ảnh hết hạn, consumer phải có **recovery policy**.

### 7.3. So sánh hai cách xử lý thiếu ảnh

| Tình huống | `whenAvailable` | `required` |
|---|---|---|
| Ảnh có sẵn | Trả ảnh | Trả ảnh |
| Ảnh cần thiết nhưng không có | Tiếp tục với ảnh null/thiếu | Báo lỗi |
| Pipeline cần chạy liên tục dù thiếu metadata | Thích hợp hơn | Có thể chặn |
| Audit không được thiếu giá trị cũ | Không đủ nếu chỉ dựa vào stream | Phù hợp hơn nhưng cần retention/recovery |
| Rủi ro che giấu thiếu thông tin | Cao hơn nếu code bỏ qua null | Thấp hơn, lỗi hiển lộ |
| Chi phí lưu ảnh ở collection | Vẫn tồn tại | Vẫn tồn tại |

**Required là chính sách phát hiện lỗi thiếu dữ liệu, không phải chính sách lưu dữ liệu vĩnh viễn.**

## 8. Kết hợp `fullDocument` và `fullDocumentBeforeChange`

Nếu muốn cặp trạng thái trước/sau:

```javascript
const stream = db.orders.watch(
  [],
  {
    fullDocument: "whenAvailable",
    fullDocumentBeforeChange: "whenAvailable"
  }
);
```

Nếu ảnh là bắt buộc:

```javascript
const stream = db.orders.watch(
  [],
  {
    fullDocument: "required",
    fullDocumentBeforeChange: "required"
  }
);
```

Một update event có cả ảnh:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O1" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  },
  fullDocumentBeforeChange: {
    _id: "O1",
    status: "NEW",
    version: 1
  },
  fullDocument: {
    _id: "O1",
    status: "PAID",
    version: 2
  }
}
```

Trong event thật, ảnh chứa **document đầy đủ**, còn ví dụ giản lược các field để nhấn mạnh state transition.

### 8.1. Kết hợp pre-image với updateLookup có được không?

Có thể:

```javascript
db.orders.watch([], {
  fullDocument: "updateLookup",
  fullDocumentBeforeChange: "whenAvailable"
});
```

Nhưng khi đó:

- `fullDocumentBeforeChange` mô tả state **trước event**;
- `fullDocument` mô tả state **hiện hành khi lookup**.

Chúng **không nhất thiết là cặp before/after của cùng một thay đổi**. Không tính diff nghiệp vụ lịch sử bằng cách so sánh hai object đó nếu document có thể tiếp tục được cập nhật.

## 9. Thực hành hai terminal: quan sát insert, update, replace và delete

Yêu cầu môi trường: MongoDB replica set/sharded cluster hỗ trợ change stream images, MongoDB 6.0+, `mongosh` và quyền phù hợp.

### 9.1. Terminal B: chuẩn bị collection

```javascript
use changeImageLab;

db.createCollection(
  "orders",
  {
    changeStreamPreAndPostImages: {
      enabled: true
    }
  }
);
```

Nếu collection đã có, dùng `collMod` thay vì tạo lại. Với bài tập lặp lại, chọn `_id` mới để tránh duplicate key, hoặc chỉ dọn record thử nghiệm một cách có kiểm soát:

```javascript
db.orders.deleteOne({ _id: "O-274" });
```

Tránh `drop()` collection trong lúc watch vì drop/invalidate có thể chấm dứt stream collection-level.

### 9.2. Terminal A: mở stream

```javascript
use changeImageLab;

const stream = db.orders.watch(
  [],
  {
    fullDocument: "whenAvailable",
    fullDocumentBeforeChange: "whenAvailable",
    maxAwaitTimeMS: 1000
  }
);

while (stream.hasNext()) {
  const e = stream.next();

  printjson({
    token: e._id,
    operationType: e.operationType,
    documentKey: e.documentKey,
    updateDescription: e.updateDescription,
    before: e.fullDocumentBeforeChange,
    after: e.fullDocument
  });
}
```

Terminal A sẽ chờ event. `maxAwaitTimeMS` là tùy chọn liên quan việc chờ/batching của cursor theo API, **không đảm bảo sẽ có một event mới mỗi giây**.

### 9.3. Terminal B: insert

```javascript
db.orders.insertOne({
  _id: "O-274",
  customerId: "C-10",
  status: "NEW",
  version: 1,
  total: NumberDecimal("100.00"),
  shipping: { method: "STANDARD" }
});
```

Insert event có `fullDocument` của document mới. Pre-image không có vì trước insert document chưa tồn tại.

### 9.4. Terminal B: update lần thứ nhất

```javascript
db.orders.updateOne(
  { _id: "O-274" },
  {
    $set: {
      status: "PAID",
      "shipping.method": "EXPRESS"
    },
    $inc: { version: 1 }
  }
);
```

Event minh họa:

```javascript
{
  operationType: "update",
  updateDescription: {
    updatedFields: {
      status: "PAID",
      "shipping.method": "EXPRESS",
      version: 2
    },
    removedFields: []
  },
  before: {
    _id: "O-274",
    status: "NEW",
    version: 1,
    shipping: { method: "STANDARD" }
  },
  after: {
    _id: "O-274",
    status: "PAID",
    version: 2,
    shipping: { method: "EXPRESS" }
  }
}
```

Đây là ví dụ rút gọn; pre/post images thật còn có các field như `customerId`, `total`.

### 9.5. Terminal B: update lần thứ hai

```javascript
db.orders.updateOne(
  { _id: "O-274" },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  }
);
```

Event tiếp theo có **pre-image PAID** và **post-image SHIPPED**. Event trước đó vẫn có post-image **PAID**, không biến thành SHIPPED như một updateLookup có thể xảy ra sau.

### 9.6. Terminal B: replace

```javascript
db.orders.replaceOne(
  { _id: "O-274" },
  {
    _id: "O-274",
    customerId: "C-10",
    status: "DELIVERED",
    version: 4,
    total: NumberDecimal("100.00")
  }
);
```

Với replace, `fullDocument` thường chứa document thay thế; pre-image nếu có mô tả state trước replace.

MongoDB có thể phát `replace` event cho một số thao tác mà ứng dụng nghĩ là “update” trong những điều kiện nhất định, vì thế consumer không nên chỉ xử lý `operationType: "update"`.

### 9.7. Terminal B: delete

```javascript
db.orders.deleteOne({ _id: "O-274" });
```

Delete event cho `documentKey` và **pre-image**, nếu có. Không có post-document sau delete.

Consumer search index có thể chỉ cần `documentKey` để xóa record; consumer audit có thể cần toàn bộ pre-image.

## 10. So sánh ba streams trên cùng workload

Mở ba consumer độc lập:

```javascript
// Consumer 1: delta.
const s1 = db.orders.watch([], {
  fullDocument: "default"
});

// Consumer 2: lookup latest state.
const s2 = db.orders.watch([], {
  fullDocument: "updateLookup"
});

// Consumer 3: event-time images.
const s3 = db.orders.watch([], {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
});
```

Mỗi consumer cần vòng đọc/terminal riêng để tránh chặn các lệnh khác trong cùng phiên.

Tạo các update liên tiếp:

```javascript
db.orders.insertOne({
  _id: "FAST-1",
  status: "NEW",
  version: 1
});

db.orders.updateOne(
  { _id: "FAST-1" },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);

db.orders.updateOne(
  { _id: "FAST-1" },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  }
);
```

| Stream | Đối với event update thành PAID |
|---|---|
| Default | Có delta `status: PAID`, không chủ động tra full document |
| Update lookup | Có thể thấy PAID **hoặc SHIPPED** tùy thời điểm lookup |
| Pre/post images | Trước NEW, sau PAID nếu ảnh được lưu |

Một lần demo thủ công không đảm bảo tạo đủ race để updateLookup thấy SHIPPED. Hành vi phụ thuộc lịch update và thời gian consumer/lookup, không phải mỗi lần đều sai.

## 11. Lifecycle và retention của pre/post images

MongoDB quản lý dữ liệu ảnh trong vùng lưu trữ nội bộ, được mô tả qua cơ chế như `config.system.preimages` trong tài liệu. Ảnh không được giữ mãi theo mặc định trong mọi cấu hình.

Có **hai giới hạn** cần phân biệt:

1. **Oplog window**: thời gian sự kiện thay đổi còn đủ lịch sử cho resume.
2. **Pre/post image retention**: thời gian ảnh vẫn được lưu để có thể truy xuất.

Một consumer có thể có resume token nhưng **ảnh của một event** không còn được lưu; hoặc ảnh còn cấu hình TTL dài nhưng **event oplog** cần resume đã biến mất.

### 11.1. `expireAfterSeconds`

Trong các phiên bản/deployment hỗ trợ, có thể quản lý image TTL bằng cluster parameter:

```javascript
db.adminCommand({
  setClusterParameter: {
    changeStreamOptions: {
      preAndPostImages: {
        expireAfterSeconds: 3600
      }
    }
  }
});
```

Đây là ví dụ quyền quản trị cho môi trường thử nghiệm. 3600 giây chỉ là giá trị minh họa, không phải khuyến nghị chung.

Kiểm tra cấu hình khi được hỗ trợ:

```javascript
db.adminCommand({
  getClusterParameter: "changeStreamOptions"
});
```

Khả năng chỉnh qua command hoặc giao diện quản trị có thể khác giữa MongoDB self-managed và dịch vụ managed. Cần kiểm tra hướng dẫn của deployment đang dùng.

### 11.2. `off` không có nghĩa giữ vĩnh viễn

Nếu `expireAfterSeconds` là `"off"` trong cấu hình được hỗ trợ, ý nghĩa là không đặt TTL theo số giây riêng; **ảnh vẫn chịu vòng đời của oplog event tương ứng**.

Nếu oplog event đã bị loại, ảnh tương ứng cũng không phải một cơ chế lưu lịch sử không giới hạn. Không lập chính sách audit lâu năm dựa vào `"off"`.

### 11.3. Không sửa trực tiếp vùng ảnh nội bộ

Không tự xóa hoặc update dữ liệu trong collection nội bộ quản lý pre/post images. Dùng cơ chế retention và maintenance chính thức của MongoDB, theo dõi storage và capacity.

### 11.4. Capture ảnh có thể rất tốn dung lượng

Một collection có document trung bình 200 KB và bị cập nhật liên tục có thể phát sinh dung lượng ảnh lớn, dù mỗi update chỉ sửa một field nhỏ.

Cần tính:

- Kích thước document trung bình và p95/p99;
- Số update/replace/delete mỗi giây;
- Tỷ lệ update các document lớn;
- Retention muốn giữ;
- Disk/network/replication overhead;
- Nhu cầu của nhiều consumer.

Không bật ảnh trên mọi collection chỉ vì muốn “có thêm thông tin” khi không có use case rõ.

## 12. Giới hạn kích thước change event

Một event MongoDB phải tuân thủ giới hạn kích thước BSON document. Nếu trả cả pre-image và post-image đầy đủ, cộng với `updateDescription`, `documentKey` và metadata, tổng event có thể rất lớn.

Ví dụ:

```text
Pre-image:         document lớn
Post-image:        document lớn
Metadata/delta:    phần cộng thêm
          │
          ▼
Có thể vượt giới hạn BSON event
```

Việc một document riêng lẻ hợp lệ **không bảo đảm** event chứa cả hai ảnh lớn sẽ hợp lệ.

Những collection có document/array gần kích thước tối đa cần thử nghiệm worst-case khi dùng cả hai ảnh. Một projection phía consumer không nhất thiết loại bỏ mọi chi phí capture trên server.

## 13. Chi phí của updateLookup so với image capture

### 13.1. Update lookup

Ưu điểm:

- Không phải bật lưu ảnh từ trước.
- Có thể lấy trạng thái mới nhất để tạo projection.
- Không chịu image retention cho state lookup (nhưng vẫn chịu oplog/resume).

Chi phí:

- Có thêm lookup trên source collection;
- Thêm network/serialization cho full document;
- Có thể chậm khi document lớn hoặc shard bận;
- Không chính xác cho event-time state;
- Có thể null nếu document đã bị delete.

### 13.2. Pre/post images

Ưu điểm:

- Exact event-time before/after khi ảnh còn.
- Thích hợp audit, rollback analysis và CDC cần lịch sử.
- Không phải query document hiện hành để tái dựng thời điểm cũ.

Chi phí:

- Write/storage amplification vì server lưu ảnh;
- Quản trị retention;
- Payload lớn;
- Bảo mật PII nhạy cảm hơn;
- `required` có thể làm consumer dừng khi ảnh không sẵn.

Không có câu trả lời “pre/post images luôn nhanh hơn updateLookup”. Cần đo trên document size, update rate, số consumer, replication/storage và SLO thực tế.

## 14. Thiếu ảnh: nguyên nhân và cách phản ứng

Những lý do thường gặp:

1. Collection chưa bật capture khi sự kiện xảy ra.
2. Capture được bật quá muộn.
3. Capture bị tắt trước sự kiện.
4. Ảnh hết TTL.
5. Oplog event/ảnh tương ứng đã bị loại.
6. Event không có pre/post document theo bản chất.
7. Pipeline consumer lọc/project mất những trường cần đọc.

### 14.1. `whenAvailable`: xử lý fallback

```javascript
function handleEvent(event) {
  if (event.operationType !== "update") {
    return;
  }

  const after = event.fullDocument;

  if (after == null) {
    // Thiếu exact post-image.
    // Tùy nghiệp vụ: đánh dấu cần đối soát,
    // lấy latest state, hoặc bỏ phần làm giàu.
    print("Post-image unavailable");
    printjson(event.documentKey);
    return;
  }

  // Xử lý exact post-state của event.
}
```

Fallback bằng lookup state hiện hành chỉ phù hợp khi consumer chấp nhận latest state. Không biến một state lookup muộn thành “post-image lịch sử” trong audit.

### 14.2. `required`: lỗi là vi phạm hợp đồng

Nếu audit yêu cầu ảnh trước/sau của mọi thay đổi, thiếu ảnh không nên bị bỏ qua.

Runbook có thể là:

```text
Missing required image
     │
     ▼
Change stream error
     │
     ├── Alert và đánh dấu pipeline DEGRADED
     ├── Không advance checkpoint qua event chưa xử lý
     ├── Đối soát nguồn/backup/audit khác
     ├── Xác định khoảng lịch sử ảnh bị mất
     └── Rebuild hoặc công bố giới hạn phục hồi
```

Không thể bắt server tự tạo lại exact pre-image của event đã hết retention nếu không có nguồn lịch sử khác.

## 15. Resume token và checkpoint

Một change stream có thể hoạt động nhiều ngày, nhưng ứng dụng phải xử lý restart, deploy, network errors và primary stepdown.

Mỗi event có `_id` là **resume token opaque**:

```javascript
const event = stream.next();
const token = event._id;
```

Consumer cần lưu token sau khi đã xử lý side effect thành công theo contract.

### 15.1. Resume sau restart

Ví dụ minh họa:

```javascript
const tokenFromCheckpointStore = null; // Thay bằng BSON token đã lưu.

const options = {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
};

if (tokenFromCheckpointStore != null) {
  options.resumeAfter = tokenFromCheckpointStore;
}

const stream = db.orders.watch([], options);
```

Phải serialize/deserialize token theo BSON API hỗ trợ, không tự chuyển token thành một chuỗi tùy ý rồi đoán cách parse.

### 15.2. Thứ tự xử lý checkpoint

Sai:

```text
Nhận event E
    ↓
Lưu token(E)
    ↓
Xử lý E thất bại
```

Khi restart, stream resume **sau E** nên E có thể bị bỏ qua.

Hợp lý hơn:

```text
Nhận event E
    ↓
Xử lý side effect idempotently
    ↓
Xác nhận side effect đã commit
    ↓
Lưu token(E)
```

Nếu process crash **sau khi side effect commit nhưng trước khi lưu checkpoint**, E có thể được phát lại. Vì vậy, consumer cần idempotency/at-least-once semantics, hoặc commit cả checkpoint và side effect chung transaction nếu hệ thống đích cho phép.

### 15.3. Resume token không phải business version

Không lấy event `_id` làm:

- Số lần document đã được cập nhật;
- Timestamp UTC;
- Thứ tự nghiệp vụ của mọi client;
- ID người dùng.

Nếu cần ordering per document, có thể bổ sung `version` tăng hoặc ứng dụng đảm bảo xử lý theo từng key.

### 15.4. `resumeAfter` và `startAfter`

Cần phân biệt resume bình thường và mở stream **sau invalidate event** theo API hỗ trợ. Trong ngữ cảnh invalidate, `startAfter` có quy tắc riêng; không được giả định `resumeAfter` dùng được với mọi event/token.

### 15.5. Token cũ vượt oplog window

Nếu consumer ngừng quá lâu, oplog event cần để resume không còn. Không thể chỉ bỏ token, mở stream mới và gọi projection là “đồng bộ” nếu còn một khoảng thay đổi bị bỏ lỡ.

Phải thiết kế **full resync**: snapshot dữ liệu hiện tại, khớp mốc khởi động CDC, replay phần chênh và đối soát trước khi công bố projection đã đầy đủ.

## 16. Event ordering và consumer race

Dù server cung cấp change event theo cơ chế của nó, **consumer application** vẫn có thể làm sai thứ tự khi xử lý song song.

```text
Event A: O1, version=2, status=PAID
Event B: O1, version=3, status=SHIPPED

Worker 1 nhận A nhưng chạy chậm.
Worker 2 nhận B và ghi projection version 3.
Worker 1 ghi projection version 2 sau cùng.
```

Projection cuối bị **lùi về version 2**.

Giải pháp:

- Phân vùng công việc theo document key để các event cùng key xử lý tuần tự.
- Hoặc dùng version/conditional update mang tính atomic ở đích.
- Dùng idempotency để event replay không tạo side effects trùng.
- Với `updateLookup`, nhớ một event cũ có thể trả state mới hơn do lookup, không gán version từ delta rồi xử lý như thể full document cùng version.

Ví dụ ý tưởng:

```javascript
if (eventVersion > projectionVersion) {
  // Atomic conditional upsert by document key.
  applyNewerProjection();
} else {
  ignoreOlderEvent();
}
```

Version trên document nguồn là **trường do ứng dụng quản lý**, không phải tính năng MongoDB tự tăng cho mọi document.

## 17. Dùng `operationType` đúng cách

### 17.1. Insert

```javascript
db.orders.insertOne({
  _id: "O-1",
  status: "NEW"
});
```

Insert event có `fullDocument` của document mới; không có pre-image.

### 17.2. Update

```javascript
db.orders.updateOne(
  { _id: "O-1" },
  { $set: { status: "PAID" } }
);
```

Update event có `updateDescription`. Muốn whole document, dùng updateLookup hoặc post-image. Muốn before/after, dùng pre/post.

### 17.3. Replace

```javascript
db.orders.replaceOne(
  { _id: "O-1" },
  {
    _id: "O-1",
    status: "SHIPPED"
  }
);
```

Replace event thường có full document mới; pre-image mô tả document trước replace nếu ảnh có. Consumer phải xử lý replace riêng với update vì replace không có cùng cơ chế delta.

### 17.4. Delete

```javascript
db.orders.deleteOne({ _id: "O-1" });
```

Delete event có `documentKey`. Nếu consumer cần dữ liệu bị xóa, dùng pre-image; `updateLookup` không biến document đã xóa thành dữ liệu có thể tra lại.

### 17.5. Invalidate và DDL

Một `drop`/`rename` có thể tạo những event điều khiển luồng. `invalidate` có thể đóng stream theo phạm vi watch. Consumer không nên bỏ qua rồi chờ `hasNext()` mãi như thể stream còn hoạt động bình thường.

Xử lý DDL/invalidate và `startAfter` cần theo ngữ nghĩa phiên bản cụ thể.

## 18. Change streams trên sharded cluster

Trong sharded cluster:

- `mongos` có thể tổng hợp event từ nhiều shard.
- `documentKey` có thể gồm `_id` và field shard key phù hợp.
- Việc update shard-key value có quy tắc riêng theo phiên bản và cách thao tác.
- Event ordering phải dựa trên cơ chế change stream, không tự suy từ đồng hồ wall time của từng node.
- Một document pre/post image không phải snapshot nhất quán **toàn cluster**.
- Resume token được quản lý bởi server, không tự dựng từ business ID.

Ví dụ khi shard key là `{tenantId: 1, orderId: 1}`:

```javascript
{
  documentKey: {
    tenantId: "TENANT-A",
    orderId: "O-9",
    _id: ObjectId("65a12f010000000000000001")
  }
}
```

Consumer không nên giả định `documentKey` lúc nào cũng chỉ có `_id`.

### 18.1. Một transaction không phải một change event duy nhất

Một transaction cập nhật `orders` và `payments` có thể tạo những sự kiện liên quan tới các document/collection tương ứng. Pre/post image của một order **không tự mang toàn bộ snapshot payment**.

Nếu downstream cần invariant nhiều document, phải thiết kế transaction/outbox, grouping hoặc reconciliation phù hợp. Không gọi cặp ảnh before/after của một document là “transaction snapshot toàn cluster”.

## 19. Dữ liệu nhạy cảm trong pre-image

Pre-image có thể chứa dữ liệu người dùng **đã sửa hoặc xóa**:

```javascript
{
  _id: "USER-1",
  email: "old@example.com",
  phone: "0123456789",
  homeAddress: "Địa chỉ cũ"
}
```

Nếu ứng dụng xóa địa chỉ khỏi document, pre-image trong retention window vẫn có thể còn giá trị cũ. Hệ quả:

- Chỉ cấp quyền đọc change stream cho service cần thiết.
- Không `printjson(event)` với PII vào production logs.
- Xác định retention và privacy policy rõ ràng.
- Kiểm soát mã hóa, quyền truy cập, audit đối với checkpoint và downstream storage.
- Khi đáp ứng yêu cầu xóa dữ liệu, cần biết thông tin có thể còn trong images/backup/audit không.
- Không coi event có dữ liệu là bằng chứng mọi downstream được phép lưu trữ dữ liệu đó.

### 19.1. Dùng watch pipeline cẩn thận

Có thể lọc operation types:

```javascript
const stream = db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    }
  ],
  {
    fullDocument: "whenAvailable",
    fullDocumentBeforeChange: "whenAvailable"
  }
);
```

Không dùng `$project` tùy tiện để loại/sửa **event `_id`** (resume token); thay đổi token có thể gây lỗi stream hoặc làm mất khả năng resume.

Watch pipeline có thể giảm nội dung downstream nhận, nhưng **không xóa chi phí capture images** đã bật ở source collection.

### 19.2. Change stream không tự cung cấp actor nghiệp vụ

Một event có thể cho biết document bị update, nhưng không tự chứa `userId` của người đã nhấn nút, request ID hoặc lý do nghiệp vụ nếu ứng dụng không tạo metadata liên quan.

Nếu audit cần “ai thay đổi, khi nào, vì sao”, phải thiết kế domain audit record với actor/correlation ID, không chỉ dựa vào change stream.

## 20. Java MongoDB Driver: updateLookup

Java Sync Driver có API `ChangeStreamIterable` và `ChangeStreamDocument<T>`.

Ví dụ skeleton:

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

MongoCollection<Document> orders =
    database.getCollection("orders");

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         orders.watch()
             .fullDocument(FullDocument.UPDATE_LOOKUP)
             .cursor()) {

    while (cursor.hasNext()) {
        ChangeStreamDocument<Document> event = cursor.next();

        System.out.println("operation=" + event.getOperationType());
        System.out.println("key=" + event.getDocumentKey());
        System.out.println("delta=" + event.getUpdateDescription());
        System.out.println("full=" + event.getFullDocument());
    }
}
```

`getFullDocument()` của update event ở chế độ này là **lookup hiện hành**, không phải exact post-image lịch sử.

### 20.1. Java Driver: event-time images

Trên phiên bản Java Driver hỗ trợ:

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;
import org.bson.Document;

MongoCollection<Document> orders =
    database.getCollection("orders");

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         orders.watch()
             .fullDocument(FullDocument.WHEN_AVAILABLE)
             .fullDocumentBeforeChange(FullDocumentBeforeChange.WHEN_AVAILABLE)
             .cursor()) {

    while (cursor.hasNext()) {
        ChangeStreamDocument<Document> event = cursor.next();

        Document before = event.getFullDocumentBeforeChange();
        Document after = event.getFullDocument();

        System.out.println("key=" + event.getDocumentKey());
        System.out.println("before=" + before);
        System.out.println("after=" + after);
    }
}
```

Đây không phải consumer production hoàn chỉnh. Cần thêm:

- Restart/resume loop;
- Error classification;
- Persist token đúng thời điểm;
- Idempotency;
- Kiểm soát thứ tự theo document key;
- Timeout/health metrics;
- Shutdown và connection lifecycle;
- Redaction dữ liệu nhạy cảm;
- Fallback khi ảnh null;
- Kiểm soát bộ nhớ và batching.

### 20.2. Resume token trong Java

Trong xử lý event:

```java
var token = event.getResumeToken();
```

Token phải được lưu đúng kiểu BSON hoặc representation được driver hỗ trợ, không giả định có thể tự parse string tùy ý.

Khi restart, dùng API resume tương ứng và bảo đảm oplog còn lịch sử cần thiết.

### 20.3. Spring Data MongoDB

Spring Data MongoDB có các API change streams và tùy chọn ánh xạ tài liệu. Nhưng API builder cho `fullDocumentBeforeChange`, mode `whenAvailable`/`required`, cùng DTO mapping phụ thuộc phiên bản Spring Data/Java Driver.

Khi triển khai cần kiểm tra:

1. Server version và FCV;
2. Driver/framework version;
3. Cấu hình watch options có được truyền đúng tới MongoDB;
4. BSON types như Decimal128/Date/ObjectId;
5. Resume token handling;
6. Lifecycle của subscription;
7. Consumer lag và error handling.

Không mặc định `updateLookup` trong một builder cũ có cùng tính năng với exact post-image ở MongoDB 6.0+.

## 21. Thiết kế theo use case

### 21.1. Cache invalidation

Nếu mục tiêu chỉ là xóa Redis key khi một order thay đổi:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O1" }
}
```

thường là đủ. Không nhất thiết bật capture images hoặc updateLookup.

Ngoại lệ: cache key dựa vào field **cũ** (ví dụ customerId trước khi đổi) có thể cần pre-image hoặc một mapping riêng.

### 21.2. Search index latest-state

Consumer có thể:

- Insert/replace: upsert từ `fullDocument`.
- Update: dùng `updateLookup` nếu chấp nhận current state, hoặc exact post-image nếu cần event-time.
- Delete: xóa từ `documentKey`.
- Dùng version/idempotency để ngăn xử lý trễ ghi đè trạng thái mới.

Nếu updateLookup của update event trả null vì document đã bị xóa, cần phân biệt với chính delete event và bảo đảm kết quả search index cuối đúng.

### 21.3. Audit lịch sử trước/sau

Nếu cần chính xác mỗi bước thay đổi:

```javascript
db.orders.watch([], {
  fullDocument: "required",
  fullDocumentBeforeChange: "required"
});
```

Cần collection bật capture từ trước, retention đủ dài, monitoring và recovery.

Không phải mọi operation có cả before/after: insert không có before, delete không có after. Audit schema phải biểu diễn rõ các trường hợp tự nhiên này.

### 21.4. CDC sang data warehouse

Một pipeline CDC đầy đủ phải:

1. Bootstrap snapshot của document đã tồn tại trước khi stream mở.
2. Thiết lập mốc change stream để không mất thay đổi giữa snapshot và CDC.
3. Xử lý insert/update/replace/delete.
4. Chọn latest lookup hay exact images theo yêu cầu.
5. Chuẩn hóa BSON types/schema evolution.
6. Persist checkpoint sau khi downstream commit.
7. Rebuild nếu token cũ không resume được hoặc ảnh bắt buộc mất.

Chỉ mở `watch()` hôm nay **không tự xuất toàn bộ collection cũ** vào warehouse.

### 21.5. Event sourcing và audit khác CDC

Change stream không tự là event store vô hạn:

- Oplog có retention;
- Images có retention;
- Update kỹ thuật không nhất thiết là business event;
- Actor/reason có thể thiếu;
- Một lần thay đổi schema có thể làm việc replay delta phức tạp.

Nếu cần event sourcing, phải thiết kế domain events versioned, bền vững và có hợp đồng rõ, có thể dùng change stream làm cầu nối nhưng không coi oplog là sổ cái lâu dài.

## 22. Planning retention theo tốc độ và consumer lag

Giả sử:

```text
Producer rate:       10.000 events/giây
Consumer rate:        8.000 events/giây
Backlog tăng:         2.000 events/giây
```

Sau một giờ:

\[
2.000 \times 3.600 = 7.200.000\ \text{events}
\]

Dù hệ thống không bị crash, consumer vẫn có thể mất khả năng bắt kịp. Nếu event/ảnh hết retention trước khi được xử lý, CDC không còn đầy đủ.

### 22.1. Theo dõi tuổi backlog

Backlog depth 1 triệu event có thể tương ứng:

- 10 giây ở 100.000 events/giây;
- 1.000 giây ở 1.000 events/giây.

Vì thế cần metric:

- Event timestamp/clusterTime tới processing time;
- Tuổi event cũ nhất chưa xử lý;
- Oplog window;
- Pre/post image TTL;
- Retry rate;
- Required-image failures;
- Resume failures;
- Consumer throughput;
- Storage tăng theo thời gian.

### 22.2. Retention cần margin

Nếu SLA chấp nhận downtime 24 giờ, retention đúng 24 giờ có thể không đủ vì còn:

- Thời gian phát hiện lỗi;
- Thời gian sửa/triển khai lại;
- Khối lượng backlog phải replay;
- Những đợt peak updates;
- Giới hạn disk khi số ảnh tăng nhanh.

Không có một TTL phổ quát cho mọi workload. Phải tính bằng số liệu thật và mức chi phí có thể chấp nhận.

## 23. Decision matrix

| Nhu cầu | Chỉ `updateDescription` | `updateLookup` | Event-time pre/post |
|---|---|---|---|
| Invalidate cache theo `_id` | **Đủ trong nhiều trường hợp** | Thừa | Thừa |
| Biết field nào đổi | **Tốt** | Không thay delta | Không thay delta |
| Lấy latest state để index | Có thể nếu có state | **Phù hợp** | Phù hợp nếu xử lý ordering |
| Audit exact before/after | Thiếu before | **Không đủ** | **Ưu tiên** |
| Biết nội dung document đã xóa | Chỉ documentKey | Không lấy lại document đã xóa | **Pre-image có ích** |
| Giảm network payload | **Tốt** | Gửi full document | Gửi ảnh đầy đủ |
| Không tăng image storage | **Tốt** | Không cần capture | Cần capture |
| Consumer dừng dài ngày | Phụ thuộc oplog | Phụ thuộc oplog | Phụ thuộc oplog **và** image retention |
| Rủi ro PII | Ít hơn | Có full latest document | Có cả dữ liệu cũ đã sửa/xóa |

**Không chọn một mode cho mọi consumer.** Một collection có thể có nhiều luồng downstream với hợp đồng khác nhau; cấu hình capture ảnh ở server phải dựa trên những use case thực sự cần nó.

## 24. Những lỗi thường gặp

| Nhầm lẫn | Tác động | Cách xử lý |
|---|---|---|
| `updateLookup` là exact post-image | Audit sai khi document thay đổi tiếp | Dùng pre/post images |
| `whenAvailable` tự lưu ảnh | Nhận null do chưa bật capture | Bật `changeStreamPreAndPostImages` ở collection |
| Bật capture là có ảnh cho quá khứ | Thiếu ảnh lịch sử | Bật trước thay đổi hoặc có audit khác |
| Required giữ ảnh vĩnh viễn | Stream lỗi khi ảnh thiếu | Kế hoạch retention/recovery |
| Insert có pre-image | Consumer xử lý nhầm | Không có before-document khi insert |
| Delete có full post-document | Consumer cố lookup document đã xóa | Dùng pre-image |
| `fullDocument` null của update là delete event | Ghi sai event type | Luôn xem `operationType` |
| Default update luôn có full document | Thiếu field khi đồng bộ | Dùng lookup/image mode |
| Oplog window = image TTL | Resume/ảnh thiếu khác nhau | Giám sát cả hai |
| TTL `"off"` nghĩa giữ vĩnh viễn | Mất ảnh khi oplog event hết hạn | Đừng coi image store là audit archive |
| Resume token là business version | Sai ordering | Token opaque; version nghiệp vụ riêng |
| Lưu token trước side effect | Bỏ sót event sau crash | Lưu sau commit, xử lý idempotently |
| Change stream đảm bảo exactly-once external side effects | Duplicate khi retry | Idempotency/transaction phù hợp |
| Apply delta lên state cũ tùy ý | Sai nested/array state | Exact post-image hoặc state/replay chuẩn |
| Chỉ xử lý `update` | Bỏ insert/replace/delete | Xử lý operation types riêng |
| Ghi log toàn bộ pre-image | Lộ dữ liệu đã được xóa/sửa | Redaction, quyền, retention |
| Capture ảnh không tốn tài nguyên | Storage/write amplification | Benchmark và capacity planning |
| Cặp ảnh một document là transaction snapshot toàn cluster | Sai invariant đa document | Transaction/outbox/reconciliation |
| `$project` xóa event `_id` | Lỗi resume/change stream | Giữ resume token |

## 25. Bài tập thực hành

### Bài 1 — Phân biệt exact post-image và lookup

Document:

```javascript
{ _id: 1, status: "NEW", version: 1 }
```

Sau đó:

```text
Update A: NEW → PAID, version 2
Update B: PAID → SHIPPED, version 3
```

1. `updateDescription` của A nói gì?
2. `updateLookup` của A có thể trả version mấy?
3. Exact post-image của A phải có state nào?
4. Pre-image của B phải là gì?
5. Vì sao lookup không phù hợp để lập audit mỗi lần thay đổi?

### Bài 2 — Bật ảnh và thử insert/update/replace/delete

Trên replica set MongoDB 6.0+:

1. Tạo collection có `changeStreamPreAndPostImages.enabled: true`.
2. Mở stream với `fullDocument` và `fullDocumentBeforeChange` là `"whenAvailable"`.
3. Insert một document.
4. Update hai field.
5. Replace document.
6. Delete document.
7. Ghi lại trước/sau từng event và `operationType`.

### Bài 3 — Capture không hồi tố

Giả sử update T1 xảy ra trước khi bật capture T2, rồi update T3 sau khi bật.

1. Có thể lấy pre-image của T1 bằng tính năng bật ở T2 không?
2. UpdateLookup tại T3 có phải post-image của T1 không?
3. Nếu audit T1 là bắt buộc, cần nguồn lịch sử nào khác?

### Bài 4 — Required và whenAvailable

Một delete event cần pre-image nhưng ảnh đã hết TTL.

1. `whenAvailable` cho consumer xử lý ra sao?
2. `required` khác thế nào?
3. Có được phép tự tái dựng một pre-image không có bằng trạng thái hiện hành không?
4. Nếu oplog event cũng mất, có thể resume bằng token cũ không?

### Bài 5 — Redis cache invalidation

Một service chỉ cần xóa cache `order:{_id}` khi order thay đổi.

1. Có cần updateLookup không?
2. Có cần pre/post images không?
3. Nếu cache key dựa vào customerId cũ, lựa chọn nào thay đổi?
4. Làm thế nào để không log PII?

### Bài 6 — Search index race

Consumer xử lý song song event version 2 và version 3. Version 3 được ghi vào index trước version 2.

1. Điều gì xảy ra nếu version 2 ghi sau cùng?
2. Dùng version/idempotency/partition-by-key để chống lỗi.
3. Nếu lookup cho update trả null vì document đã bị xóa, phải xử lý gì?
4. Delete event khác update event như thế nào?

### Bài 7 — Checkpoint và replay

Consumer:

```text
Nhận event E
Lưu token(E)
Xử lý E
```

Nếu crash sau bước 2:

1. E có được xử lý sau resume không?
2. Đổi thứ tự xử lý/lưu token có loại hoàn toàn duplicate không?
3. Vì sao cần idempotency?
4. Khi nào checkpoint và side effect có thể commit chung?

### Bài 8 — Oplog và image TTL

Giả sử:

```text
Oplog window:       4 giờ
Image TTL:         12 giờ
Consumer downtime:  6 giờ
```

1. Resume sau sáu giờ có chắc chắn không?
2. Vì sao image TTL dài hơn không cứu oplog event đã mất?
3. Nếu oplog 24 giờ, image TTL hai giờ, `required` bị ảnh hưởng ra sao?
4. Thiết kế alert cho backlog age.

### Bài 9 — Chi phí images

Một collection có 5.000 update/giây, document trung bình 50 KB, giữ ảnh 12 giờ.

1. Ước lượng khối lượng dữ liệu thô theo giả định minh họa.
2. Giải thích overhead/compression/replication có thể làm khác ước tính.
3. So sánh với updateLookup nếu có 5 consumers.
4. Cần đo metric nào trước khi bật production?

### Bài 10 — Audit và privacy

Một user xóa địa chỉ nhà, nhưng pre-image của event vẫn giữ địa chỉ cũ.

1. Ai được phép xem?
2. Retention ảnh và audit log có thể khác nhau không?
3. Tại sao không log raw event?
4. Làm thế nào giới hạn downstream dùng ảnh?

### Bài 11 — Array update

Document:

```javascript
{
  _id: 5,
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 2 }
  ]
}
```

1. Cập nhật `items.0.qty`, xem `updateDescription`.
2. Thay cấu trúc array, xem biểu diễn delta.
3. Vì sao áp delta lên snapshot cũ có thể sai?
4. Khi nào exact post-image hữu ích hơn?

### Bài 12 — Multi-document transaction

Transaction cập nhật `orders` và `payments`.

1. Pre/post image của order có chứa payment không?
2. Làm thế nào consumer giữ invariant giữa hai collection?
3. Có cần outbox/reconciliation không?
4. Vì sao không thể dùng cặp ảnh một document thay snapshot toàn transaction?

## 26. Checklist production

Trước khi đưa change stream consumer vào production, xác nhận:

1. Server/FCV/driver hỗ trợ mode image cần dùng.
2. Deployment là replica set/sharded cluster hỗ trợ.
3. Collection bật capture **trước** những thay đổi cần ảnh.
4. Event contract phân biệt lookup hiện hành và exact post-image.
5. Mọi loại insert/update/replace/delete/invalidate được xử lý đúng.
6. Retention ảnh và oplog window đủ dài với margin.
7. `required` vs `whenAvailable` được chọn theo mức cho phép thiếu ảnh.
8. Checkpoint chỉ advance sau khi side effect commit.
9. Idempotency xử lý event replay.
10. Ordering/version tránh projection đi lùi.
11. PII/privacy/access control được thiết kế.
12. Event size không vượt giới hạn BSON.
13. Có metrics về event lag/backlog/ảnh thiếu/resume failures.
14. Có chiến lược snapshot bootstrap cho dữ liệu cũ.
15. Có kế hoạch full resync khi không thể resume.
16. Đã thử rapid updates, delete-after-update, crash/restart và failover trên staging.
17. Không coi image store là audit archive vô hạn.

## 27. Tài liệu MongoDB tham khảo

- [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Document Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images)
- [Change Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [Change Stream Update Event](https://www.mongodb.com/docs/manual/reference/change-events/update/)
- [Change Stream Replace Event](https://www.mongodb.com/docs/manual/reference/change-events/replace/)
- [Change Stream Delete Event](https://www.mongodb.com/docs/manual/reference/change-events/delete/)
- [Collection Watch](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream)
- [collMod Command](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [setClusterParameter Command](https://www.mongodb.com/docs/manual/reference/command/setClusterParameter/)
- [Java Driver Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/usage-examples/watch/)

## Kết luận

**`updateDescription`**, **`fullDocument: "updateLookup"`** và **pre/post images** giải quyết những nhu cầu khác nhau.

- **`updateDescription`** cung cấp delta của update event, phù hợp khi chỉ cần biết field nào đổi hoặc invalidate cache.
- **`updateLookup`** lấy **trạng thái majority-committed hiện hành tại lúc tra cứu**, hữu ích cho latest-state projection nhưng **không bảo đảm là trạng thái ngay sau event đang xử lý**.
- **Pre-image và post-image** cung cấp hai trạng thái **trước và sau chính event đó**, quan trọng cho audit/CDC chính xác. Chúng yêu cầu collection bật `changeStreamPreAndPostImages.enabled` trước thao tác, và consumer yêu cầu bằng `fullDocumentBeforeChange`/`fullDocument` với mode `"whenAvailable"` hoặc `"required"` phù hợp.

Không kém phần quan trọng là vòng đời ảnh: pre/post images và oplog có retention hữu hạn, consumer dừng quá lâu có thể mất khả năng resume hoặc thiếu ảnh cần thiết. Consumer production phải quản lý checkpoint, opaque resume token, idempotency, ordering, privacy, event size và full resync.

**Khi cần trạng thái mới nhất, lookup có thể đủ. Khi cần lịch sử trước/sau đúng từng thay đổi, không dùng lookup hiện hành để thay thế exact event-time images.**

