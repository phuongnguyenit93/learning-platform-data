# Kết hợp change stream với CDC, outbox và hệ thống nhận sự kiện trong MongoDB

## 1. Bài toán: dữ liệu đã lưu nhưng hệ thống khác chưa biết

Một ứng dụng bán hàng lưu đơn hàng trong MongoDB. Khi trạng thái đơn chuyển từ `NEW` sang `PAID`, hệ thống cần:

- gửi sự kiện cho dịch vụ giao hàng;
- cập nhật chỉ mục tìm kiếm;
- cập nhật read model phục vụ báo cáo;
- gửi thông báo cho khách hàng;
- đồng bộ dữ liệu sang một kho phân tích.

Thiết kế đầu tiên thường là:

```javascript
await orders.updateOne(
  { _id: orderId },
  { $set: { status: "PAID" } }
);

await eventBus.publish("OrderPaid", { orderId });
```

Nhưng điều gì xảy ra nếu MongoDB cập nhật thành công, rồi ứng dụng bị dừng **trước khi publish**? Đơn hàng đã thanh toán nhưng hệ thống nhận sự kiện không được thông báo. Ngược lại, nếu publish trước rồi ghi database thất bại, bên nhận có thể xử lý một sự kiện không tương ứng với trạng thái đã commit.

Đây là **dual-write problem**: một nghiệp vụ muốn ghi vào **hai hệ thống độc lập** mà không có chung một transaction nguyên tử.

MongoDB cung cấp **change streams**, một cơ chế nhận biết thay đổi đã commit từ collection, database hoặc deployment. Kết hợp chúng với **CDC (Change Data Capture)** và **transactional outbox**, ta có thể xây dựng một pipeline phát sự kiện có khả năng phục hồi tốt hơn.

Mục tiêu của bài:

1. Hiểu change stream là nguồn CDC của MongoDB, khác gì với polling.
2. Phân biệt **database change** và **domain event**.
3. Hiểu khi nào đọc trực tiếp change stream của collection nghiệp vụ, khi nào cần **outbox**.
4. Thiết kế transaction ghi business data và outbox record cùng nhau.
5. Xây relay chuyển sự kiện tới Kafka, RabbitMQ hoặc hệ thống nhận tương đương.
6. Lưu **resume token/checkpoint** đúng thứ tự, xử lý mất kết nối và replay.
7. Thiết kế bên nhận **idempotent**, hiểu vì sao giao hàng *at least once* thường thực tế hơn tuyên bố *exactly once* end-to-end.
8. Giải quyết thứ tự sự kiện, schema evolution, dữ liệu nhạy cảm, backfill, retention và giới hạn oplog.
9. Thực hành `mongosh` và Node.js trên môi trường thử nghiệm được phép.

## 2. Bức tranh tổng thể: Change Stream, CDC, Outbox và Consumer

### 2.1. CDC là một mục tiêu tích hợp dữ liệu

**Change Data Capture** nghĩa là phát hiện và chuyển tiếp các thay đổi của nguồn dữ liệu sang các hệ thống khác. Một CDC pipeline điển hình:

```text
             MongoDB
        Collection / Database
                  |
              Change Stream
                  |
                 CDC
                  |
          Connector / Relay
                  |
         Kafka / Queue / Sink
                  |
        Search / Analytics / API
```

CDC có thể phục vụ:

- đồng bộ dữ liệu sang Elasticsearch hoặc một công cụ tìm kiếm;
- streaming ETL vào data warehouse;
- làm mới cache hoặc read model;
- tích hợp dữ liệu giữa dịch vụ cũ và mới;
- phát hiện thay đổi phục vụ phản ứng gần thời gian thực.

**CDC không mặc định đồng nghĩa event sourcing.** Trong event sourcing, event là nguồn sự thật được lưu bền vững cho lịch sử nghiệp vụ; trong CDC, stream thường phản ánh các **thay đổi đã xảy ra trong database**, phụ thuộc lịch sử và cơ chế retention của nguồn.

### 2.2. Change stream là cách MongoDB bộc lộ thay đổi

Change stream dùng hạ tầng replication/oplog và giao thức của MongoDB để cung cấp các sự kiện thay đổi. Nó khác cách ứng dụng tự truy vấn `updatedAt > lastSeen`:

- Không phải quét collection định kỳ để tìm document có timestamp mới.
- Có thể nhận thông tin insert/update/replace/delete và một số sự kiện quản trị theo phạm vi/tính năng.
- Có **resume token** giúp tiếp tục sau gián đoạn khi lịch sử cần thiết còn khả dụng.
- Tận dụng cơ chế của server/driver để theo dõi thay đổi đã được đa số xác nhận theo ngữ nghĩa của change streams.

Tuy nhiên, **change stream không tự cung cấp kho sự kiện vĩnh viễn**, không tự publish vào Kafka, và không tự bảo đảm mọi bên nhận xử lý đúng một lần.

### 2.3. Outbox là một mẫu bảo vệ dual-write

Trong **transactional outbox pattern**, nghiệp vụ ghi:

1. Document chính, ví dụ order.
2. Một **outbox record** mô tả domain event.

Hai thao tác được commit trong **cùng MongoDB transaction** nếu nằm ở những document/collection khác nhau.

```text
              Order Service
                   |
          BEGIN MongoDB TRANSACTION
                   |
         +---------+----------+
         |                    |
         v                    v
    update orders        insert outbox
         |                    |
         +---------+----------+
                   |
                 COMMIT
                   |
                   v
          Change stream outbox
                   |
             Relay / Publisher
                   |
                   v
              Kafka / Queue
                   |
                   v
              Consumer(s)
```

Nếu transaction abort, **không có business update lẫn outbox record đã commit**. Nếu commit thành công, outbox record tồn tại bền vững theo mức write concern yêu cầu, để relay chuyển tiếp sau đó.

**Điểm cốt lõi:** transaction bảo đảm sự gắn kết giữa business data và **ý định phát sự kiện** trong MongoDB; nó **không trực tiếp biến việc publish vào broker thành một phần của MongoDB transaction**.

### 2.4. Relay và consumer đảm nhận hai trách nhiệm khác nhau

**Relay** đọc outbox và đưa message sang hệ thống nhận. Nó quan tâm:

- change stream, resume token, backoff, acknowledgment;
- ánh xạ outbox record sang message;
- quan sát lag và xử lý broker unavailable.

**Consumer** đọc message rồi áp dụng tác dụng nghiệp vụ. Nó quan tâm:

- idempotency/deduplication;
- ordering và gap detection;
- validation, authorization theo hệ thống;
- retry, dead-letter và checkpoint/offset;
- khả năng phục hồi khi message đến lại.

Một relay hoạt động đúng không tự bảo đảm consumer hoạt động đúng.

## 3. Trước khi sử dụng change streams

### 3.1. Deployment hỗ trợ

Change streams được hỗ trợ trên **replica set** hoặc **sharded cluster** tương thích, không phải standalone `mongod` thông thường. Có thể chạy trên deployment tự quản lý hoặc dịch vụ managed tương thích, với giới hạn theo phiên bản và cấu hình.

Trước khi xây:

- Xác nhận MongoDB server version, Feature Compatibility Version và driver.
- Xác nhận collection/database được xem có nằm trên replica set hoặc sharded cluster.
- Dùng connection string và quyền truy cập hợp lệ.
- Kiểm tra read/write concern, failover, khả năng resume.
- Tính toán oplog window phù hợp với thời gian tối đa relay có thể ngắt.

Nếu local MongoDB đang chạy standalone, không giải quyết bằng cách tạo một collection tên `oplog` hoặc tự thêm trường `updatedAt` rồi gọi đó là change stream.

### 3.2. Phạm vi của `watch()`

MongoDB driver thường cung cấp ba mức theo dõi:

```javascript
// Theo dõi một collection.
db.collection("orders").watch();

// Theo dõi nhiều collection trong một database.
db.watch();

// Theo dõi nhiều database/collection trong deployment.
client.watch();
```

Các ví dụ trên minh họa **MongoDB Node.js driver** khi `db` là đối tượng `Db` và `client` là `MongoClient`; không phải cú pháp `mongosh` cho mọi phiên bản.

Chọn phạm vi nhỏ nhất đáp ứng mục tiêu:

- CDC cho `orders`: collection-level stream.
- Đồng bộ một số collection trong cùng database: database-level stream với filter rõ.
- Một collector thay đổi nhiều database: deployment-level stream khi quyền, topology và chi phí cho phép.

Stream rộng có thể nhận nhiều namespace và tăng chi phí lọc. Không mở một stream riêng cho mỗi người dùng cuối hay mỗi document nếu không có lý do kiến trúc và đánh giá tài nguyên.

### 3.3. Quyền truy cập tối thiểu

Thông thường cần quyền phù hợp với **`changeStream`** và **`find`** trên phạm vi theo dõi. Relay đọc outbox không cần mặc định có quyền sửa mọi collection nghiệp vụ.

Tách vai trò:

- Service tạo order: quyền ghi vào `orders`/`outbox`.
- Relay: quyền xem change stream, đọc outbox, ghi checkpoint được cấp riêng.
- Consumer: quyền xử lý đích mà nó sở hữu.

Không dùng tài khoản admin toàn cluster cho relay chỉ vì cấu hình tiện.

### 3.4. Change stream và majority commit

Change streams cung cấp các thông báo thay đổi **đã được majority-committed** theo cơ chế MongoDB. Sự kiện không nên được xem như thông báo của một ghi tạm thời chưa commit.

Hệ quả:

- Một write chỉ nhận `w:1` chưa chắc xuất hiện ngay trên change stream.
- Transaction nhiều document phát thay đổi khi transaction được commit phù hợp.
- Thời gian “client gọi write” khác với thời gian “relay nhận change event”.
- Không nên lấy đồng hồ của client làm vị trí chính xác trong lịch sử change stream.

Những chi tiết này phụ thuộc topology và khả năng server; khi triển khai cần đối chiếu tài liệu chính thức của version đang chạy.

## 4. Cấu trúc một change event

### 4.1. Ví dụ một insert event

Một document do `watch()` trả về có thể mang hình dạng tương tự:

```javascript
{
  _id: { /* opaque resume token */ },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1794631200, i: 1 }),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: ObjectId("66a000000000000000000001")
  },
  fullDocument: {
    _id: ObjectId("66a000000000000000000001"),
    status: "NEW",
    totalCents: NumberLong("120000")
  }
}
```

Đây là ví dụ giản lược; tập trường có thể thay đổi theo operation, server version và các tùy chọn của stream.

| Trường | Ý nghĩa |
| --- | --- |
| `_id` | **Resume token** của change event, không phải `_id` của business document |
| `operationType` | Loại thay đổi: `insert`, `update`, `replace`, `delete`, `invalidate`, v.v. |
| `clusterTime` | Mốc thời gian logic của sự kiện trong MongoDB |
| `ns` | Database và collection phát sinh thay đổi |
| `documentKey` | Khóa định danh document nguồn, có thể kèm shard key theo tình huống |
| `fullDocument` | Nội dung document trong các trường hợp/tùy chọn cho phép |
| `updateDescription` | Các thay đổi field/array của một update khi được cung cấp |

Điều rất dễ nhầm:

```text
change._id                 = resume token của STREAM
change.documentKey._id     = _id của DOCUMENT MongoDB thay đổi
change.fullDocument._id    = _id bên trong document nếu được trả
```

Chỉ **`change._id`** là token được lưu để resuming change stream. Không dùng `documentKey._id` thay thế token.

### 4.2. Insert, update, replace và delete khác nhau

Với insert, `fullDocument` thường được trả trong change event. Với update, event thường chứa `updateDescription` mô tả các field thay đổi:

```javascript
{
  operationType: "update",
  documentKey: { _id: orderId },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

Với delete, document đã bị xóa nên không mặc định có `fullDocument` của tài liệu trước khi xóa.

Vì thế consumer không thể mặc định mọi event có đầy đủ nội dung document. Nếu chỉ gửi `change.fullDocument` mà không xử lý các loại operation khác, thông điệp CDC có thể thiếu dữ liệu hoặc sai nghiệp vụ.

### 4.3. `fullDocument: "updateLookup"` và giới hạn

Khi xem update, có thể yêu cầu:

```javascript
const stream = orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
```

MongoDB thực hiện lookup để lấy document hiện tại ở thời điểm lookup theo semantics hỗ trợ. **Kết quả không nhất thiết là trạng thái của document ngay đúng thời điểm update event**, vì một update sau có thể đã xảy ra trước khi lookup hoàn tất. Document cũng có thể không còn tồn tại.

Ví dụ:

```text
T0: status NEW  -> PAID      (change event X)
T1: status PAID -> SHIPPED   (change event Y)
T2: lookup fullDocument cho X

fullDocument của X có thể phản ánh SHIPPED,
không phải đúng snapshot tại T0.
```

Với nghiệp vụ phải phát đúng payload của **event OrderPaid**, không nên coi `updateLookup` là cơ chế lấy snapshot domain event đáng tin cậy. Outbox lưu payload được xác định lúc transaction là lựa chọn rõ ràng hơn.

### 4.4. Pre-images và post-images

Các phiên bản MongoDB hỗ trợ **change stream pre-images/post-images** khi được cấu hình đúng cho collection và lựa chọn stream. Chúng giúp truy cập trạng thái trước hoặc sau thay đổi theo ngữ nghĩa server, hữu ích cho một số bài toán audit, diff hoặc CDC.

Nhưng:

- Chỉ bật tùy chọn watch chưa đủ nếu collection chưa cấu hình capture phù hợp.
- Có chi phí dung lượng/tài nguyên và chính sách retention.
- Tính năng, thao tác được hỗ trợ và thời gian giữ phụ thuộc MongoDB version.
- Không dùng pre-images làm kho audit vĩnh viễn.
- Việc dữ liệu bị xóa hoặc lịch sử hết hạn có thể làm ảnh hưởng khả năng lấy image.

Đừng tự suy luận rằng event update nào cũng có `fullDocumentBeforeChange`; phải kiểm tra option và phiên bản.

## 5. CDC trực tiếp từ collection nghiệp vụ

### 5.1. Mô hình đơn giản

```text
MongoDB orders collection
             |
      orders.watch()
             |
         CDC relay
             |
      Search index / Cache
```

Ví dụ Node.js:

```javascript
const changeStream = orders.watch(
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

for await (const change of changeStream) {
  console.log(change.operationType, change.documentKey);
}
```

Đoạn code trên chưa có checkpoint, retry và cleanup; chỉ minh họa cơ chế nhận change event. Trong production phải có vòng đời stream, resume token, error handling và lối thoát khi process shutdown.

### 5.2. Khi nào CDC trực tiếp là hợp lý?

Ví dụ **đồng bộ chỉ mục tìm kiếm**:

- Một insert order → thêm document vào read model.
- Một update → fetch/áp dụng trạng thái mới cần thiết.
- Một delete → xóa document khỏi index đích.

Ở đây consumer muốn **phản chiếu trạng thái lưu trữ**. Bản ghi thay đổi database gần với nhu cầu đích, nên CDC trực tiếp có thể gọn hơn outbox.

### 5.3. Vì sao CDC trực tiếp không phải domain event?

Giả sử service cập nhật:

```javascript
await orders.updateOne(
  { _id: orderId },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);
```

Một CDC consumer thấy `updatedFields.status = "PAID"`. Nó có thể đoán event nghiệp vụ là `OrderPaid`, nhưng:

- Field `status` có thể bị admin sửa thủ công để sửa lỗi.
- Cùng một trạng thái có thể đến từ các workflow khác nhau.
- Một update khác có thể set `status: "PAID"` dù trước đó đã PAID.
- Một migration có thể sửa hàng nghìn record mà không muốn kích hoạt giao hàng.
- Event cần metadata như paymentId, operator, business effective time mà updateDescription không chứa.

**Database change mô tả “dữ liệu đã đổi thế nào”; domain event mô tả “điều gì trong nghiệp vụ đã xảy ra”.** Hai thứ đôi khi trùng nhau nhưng không đồng nghĩa.

### 5.4. Chọn mô hình theo ý nghĩa

| Mục tiêu | Hướng thường phù hợp |
| --- | --- |
| Phản chiếu collection sang search index | CDC trực tiếp |
| Làm mới cache/read model theo thay đổi lưu trữ | CDC trực tiếp hoặc outbox nếu cần semantics nghiệp vụ |
| Báo “OrderPaid” cho dịch vụ giao hàng | Domain event qua transactional outbox |
| Phát chính xác paymentId, invoiceId, rule version tại lúc commit | Outbox với payload ổn định |
| Ghi audit dài hạn không được mất vì oplog xoay vòng | Event/audit store bền vững, có retention riêng |
| Chỉ muốn API khác biết một field vừa được sửa | CDC trực tiếp có thể đủ nếu contract rõ |

## 6. Transactional outbox: thiết kế cấu trúc dữ liệu

### 6.1. Một bản ghi outbox đề xuất

```javascript
{
  _id: "evt-7c82d",
  eventType: "OrderPaid",
  schemaVersion: 1,
  aggregateType: "Order",
  aggregateId: "ORDER-1001",
  aggregateVersion: 5,
  tenantId: "TENANT-A",
  occurredAt: ISODate("2026-11-14T03:30:00Z"),
  requestId: "req-4e91",
  correlationId: "trace-27e8",
  payload: {
    orderNo: "ORDER-1001",
    paymentId: "PAY-812",
    amountCents: NumberLong("120000"),
    currency: "VND"
  }
}
```

Các field nên được thiết kế có chủ đích:

| Field | Vai trò |
| --- | --- |
| `_id` / `eventId` | Định danh sự kiện ổn định để deduplicate |
| `eventType` | Tên sự kiện nghiệp vụ |
| `schemaVersion` | Phiên bản hợp đồng payload |
| `aggregateType` và `aggregateId` | Thực thể nghiệp vụ phát sự kiện |
| `aggregateVersion` | Số thứ tự/phiên bản **nghiệp vụ** khi được quản lý nhất quán |
| `tenantId` | Phân vùng/ủy quyền dữ liệu trong hệ đa tenant |
| `occurredAt` | Thời điểm nghiệp vụ ghi nhận, phục vụ quan sát |
| `requestId` | Liên kết ý định của một request |
| `correlationId` | Tracing xuyên dịch vụ |
| `payload` | Dữ liệu cần chuyển đến consumer |

Không dùng `occurredAt` làm định danh duy nhất hoặc bảo đảm thứ tự tuyệt đối: đồng hồ có thể lệch và nhiều sự kiện có thể cùng timestamp. Nếu cần strict ordering cho cùng aggregate, sử dụng **sequence/version có quy tắc sinh nguyên tử**.

### 6.2. Tại sao `eventId` không phải resume token?

Ví dụ:

```text
Outbox document:
    _id = "evt-7c82d"            -> business event ID

Change event trên outbox:
    _id = <opaque resume token>   -> vị trí change stream
    documentKey._id = "evt-7c82d"
    fullDocument._id = "evt-7c82d"
```

**Business event ID** đi cùng message tới Kafka/consumer để chống xử lý lặp. **Resume token** lưu riêng trong trạng thái của relay để mở lại MongoDB stream.

Nếu trộn hai ID, relay có thể không resume được, còn consumer không có khóa dedup bền vững.

### 6.3. Payload tối thiểu nhưng đủ để xử lý

Tránh phát cả MongoDB document với mọi trường nếu consumer chỉ cần `orderId`, `paymentId` và amount:

- Giảm băng thông và kích thước message.
- Giảm phụ thuộc vào schema nội bộ.
- Tránh lộ PII hoặc field nội bộ.
- Cho phép chuẩn hóa kiểu tiền, ngày, enum và field optional.

Tuy nhiên, payload quá ít có thể buộc consumer gọi ngược service để lấy dữ liệu; nếu dữ liệu đã thay đổi, consumer có thể xử lý sai thời điểm. Hãy chọn **hợp đồng sự kiện** theo nhu cầu downstream và chính sách bảo mật.

### 6.4. Giới hạn kích thước

MongoDB document vẫn chịu giới hạn BSON document, thường tối đa **16 MiB**. Outbox record và change event còn có giới hạn/bộ nhớ/băng thông theo công cụ streaming và broker.

Không nhúng tệp lớn, toàn bộ giỏ hàng hàng nghìn dòng hoặc binary vào `payload` một cách tùy tiện. Với dữ liệu lớn, có thể dùng ID/đường dẫn tới storage được quản lý, kèm version/hash và quyền truy cập phù hợp.

### 6.5. Immutable event và trạng thái publish

Nên coi phần **event payload** là bất biến sau commit. Nếu cần ghi `publishedAt`, `attempts` hay trạng thái relay, cân nhắc đặt metadata này ở một collection riêng:

```text
outbox_events: immutable event payload
relay_checkpoints: consumer/relay progress
delivery_attempts: optional diagnostics
```

Việc update `published:true` trên chính outbox document không sai trong mọi thiết kế, nhưng:

- Nó tạo thêm change events nếu đang watch cả update.
- Một cờ publish chung không đủ biểu diễn nhiều consumer độc lập.
- Nếu set cờ **trước broker acknowledgment** có thể làm mất sự kiện.
- Nếu có nhiều relay, cần ownership/lease/fencing và xử lý race.

Đừng nhầm một cờ `published` với một bằng chứng end-to-end rằng tất cả hệ thống đã xử lý message.

## 7. Ghi business data và outbox trong một transaction

### 7.1. Vì sao phải cùng transaction?

Nếu service làm:

```javascript
await orders.insertOne(order);
await outbox.insertOne(event);
```

thì dù cả hai thao tác cùng MongoDB, đây vẫn là **hai ghi riêng biệt**. Nếu process chết giữa chúng, order tồn tại mà event không tồn tại.

Muốn all-or-nothing giữa **hai document** hoặc hai collection, dùng MongoDB multi-document transaction trong deployment hỗ trợ:

```text
BEGIN
   insert order
   insert outbox event
COMMIT
```

Khi chỉ cần thay đổi một document, MongoDB đã hỗ trợ single-document atomicity; một mô hình lưu event cùng document có thể tận dụng điều này nếu thiết kế phù hợp. Nhưng nhúng outbox vô hạn vào mảng của business document có nguy cơ tăng kích thước document, contention và khó cleanup. Với nhiều dịch vụ, **outbox collection + transaction ngắn** thường dễ vận hành hơn.

### 7.2. Chuẩn bị môi trường thực hành

Ví dụ dùng database thử nghiệm:

```text
mongo_change_stream_row279_lab
```

Yêu cầu:

- Replica set hoặc sharded cluster thử nghiệm có hỗ trợ transaction/change streams.
- Node.js driver được cài ở ứng dụng mẫu hoặc môi trường học tập riêng.
- Quyền tạo document trong database test.
- Không trùng namespace với dữ liệu của người khác.

Không cần ngắt secondary hoặc đổ hàng triệu write để mô phỏng change stream. Các ví dụ không được chạy trên collection thanh toán/đơn hàng production.

### 7.3. Ví dụ Node.js tạo order và outbox nguyên tử

Giả định đã có `MongoClient` kết nối tới replica set và collection names riêng của lab:

```javascript
import { ObjectId } from "mongodb";

async function createOrderWithOutbox({
  client,
  db,
  tenantId,
  requestId,
  orderNo,
  amountCents
}) {
  // Các ID ổn định trong suốt các lần callback có thể được retry.
  const orderId = new ObjectId();
  const eventId = new ObjectId();
  const occurredAt = new Date();

  const orders = db.collection("orders_demo");
  const outbox = db.collection("outbox_demo");
  const session = client.startSession();

  try {
    await session.withTransaction(
      async () => {
        await orders.insertOne(
          {
            _id: orderId,
            tenantId,
            requestId,
            orderNo,
            status: "NEW",
            amountCents,
            version: 1,
            createdAt: occurredAt
          },
          { session }
        );

        await outbox.insertOne(
          {
            _id: eventId,
            tenantId,
            eventType: "OrderCreated",
            schemaVersion: 1,
            aggregateType: "Order",
            aggregateId: orderId.toHexString(),
            aggregateVersion: 1,
            requestId,
            occurredAt,
            payload: {
              orderNo,
              amountCents,
              status: "NEW"
            }
          },
          { session }
        );
      },
      {
        readPreference: "primary",
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );

    return { orderId, eventId };
  } finally {
    await session.endSession();
  }
}
```

Giải thích:

1. `orders_demo` và `outbox_demo` nằm trong **cùng MongoDB deployment** có transaction hỗ trợ.
2. `withTransaction` quản lý transaction lifecycle và xử lý một số lỗi retryable theo driver.
3. Hai insert dùng **cùng session**.
4. `orderId`/`eventId` được tạo **trước callback**, tránh đổi ID mỗi khi callback bị gọi lại.
5. `writeConcern: { w: "majority" }` dùng cho mức xác nhận commit phù hợp.
6. Không publish Kafka, gửi email hoặc gọi payment service **bên trong callback**.

Đây là mẫu về **atomicity MongoDB**, chưa phải API production hoàn chỉnh. Cần validate `tenantId`, `orderNo`, amount, quyền truy cập, giới hạn schema và kiểu tiền. Với số tiền chính xác, cân nhắc kiểu nguyên phù hợp (`Long`) hoặc `Decimal128`, tránh float khi nghiệp vụ không cho phép sai số.

### 7.4. Idempotency của API vẫn cần thiết

Nếu request HTTP được gửi lại sau khi transaction đã commit nhưng phản hồi bị mất, hàm có thể sinh **orderId và eventId mới** nếu gọi lại từ đầu. Hai giao dịch đều hợp lệ về mặt MongoDB, nhưng có thể tạo hai đơn cho **một ý định của người dùng**.

Với production, hãy:

- Dùng `requestId` hoặc `idempotencyKey` do API xác thực/chuẩn hóa.
- Tạo **unique constraint** trên khóa nghiệp vụ thích hợp, ví dụ `(tenantId,requestId)` trong collection orders khi kiến trúc sharding cho phép.
- Khi nhận duplicate key, **đọc bản ghi cùng requestId và so sánh payload/fingerprint** trước khi trả kết quả cũ.
- Giữ quy tắc idempotency trong khoảng thời gian đủ cho việc retry và reconciliation.

Trong sharded collections, **unique index có giới hạn shard-key-prefix**, nên phải thiết kế khóa và unique constraint trước khi triển khai. Không mặc định `_id` của một sharded collection không có `_id` trong shard key bảo đảm unique toàn cluster theo mọi mô hình.

### 7.5. Không phát sự kiện khi transaction abort

Giả sử sau khi insert order, validation nghiệp vụ thất bại:

```javascript
await session.withTransaction(async () => {
  await orders.insertOne(order, { session });

  if (!inventoryAvailable) {
    throw new Error("OUT_OF_STOCK");
  }

  await outbox.insertOne(event, { session });
});
```

Khi callback ném lỗi và transaction bị abort, order chưa commit không trở thành dữ liệu bền vững; outbox record cũng không commit. Nếu logic nghiệp vụ yêu cầu kiểm tồn kho chính xác, điều kiện đó cần được cưỡng chế tại **bước ghi nguyên tử trong transaction** chứ không chỉ dựa vào một biến `inventoryAvailable` đọc từ cache cũ.

### 7.6. Transaction không nên kéo dài

Giữ transaction ngắn:

```text
Ngoài transaction:
   validate input, chuẩn bị event, auth, tính dữ liệu dự kiến

Trong transaction:
   kiểm/cập nhật state cần nhất quán
   insert outbox record
   commit

Sau commit:
   relay gửi broker
   consumer xử lý
```

Không đợi HTTP webhook, Kafka acknowledgment hoặc response người dùng **trong MongoDB transaction**, vì chúng kéo dài snapshot, tăng contention và tạo side effect không rollback được.

## 8. Relay: đọc outbox bằng change stream

### 8.1. Luồng tổng quát

```text
outbox_demo (MongoDB, persistent)
           |
           | change stream insert events
           v
        Relay
           |
           | validate/map
           v
      publisher.publish()
           |
           | broker acknowledgment
           v
       save checkpoint
```

Thứ tự **publish thành công → lưu checkpoint** là nền tảng của mô hình *at least once*. Nếu checkpoint được lưu trước khi broker nhận sự kiện, crash có thể khiến relay **bỏ qua một event chưa được publish**.

### 8.2. Xử lý một outbox insert

Node.js driver:

```javascript
const stream = outbox.watch(
  [
    {
      $match: {
        operationType: "insert"
      }
    }
  ],
  {
    fullDocument: "default",
    maxAwaitTimeMS: 1000
  }
);

for await (const change of stream) {
  const event = change.fullDocument;

  await publisher.publish({
    topic: "orders.events",
    key: String(event.aggregateId),
    value: JSON.stringify({
      eventId: String(event._id),
      eventType: event.eventType,
      schemaVersion: event.schemaVersion,
      aggregateId: event.aggregateId,
      aggregateVersion: event.aggregateVersion,
      tenantId: event.tenantId,
      payload: event.payload
    })
  });

  // Đến đây mới được xác nhận tiến độ của stream.
  await checkpoints.updateOne(
    { _id: "relay-orders-events" },
    {
      $set: {
        resumeToken: change._id,
        updatedAt: new Date()
      }
    },
    { upsert: true }
  );
}
```

Trong code trên, `publisher.publish()` là **giao diện giả định** của một adapter Kafka/queue. Nó phải chỉ resolve khi có **acknowledgment tương ứng với mức đảm bảo publish cần thiết**, không chỉ khi message được đưa vào buffer trong process.

Đoạn trên cũng giả định một relay xử lý stream theo thứ tự, một checkpoint và một đích nhận. Production cần startup/reconnect/error handling và leadership khi có nhiều relay.

### 8.3. Mẫu relay có resume token

Một cách cấu trúc:

```javascript
async function runOutboxRelay({
  outbox,
  checkpoints,
  publisher,
  relayName = "orders-to-broker"
}) {
  const saved = await checkpoints.findOne({
    _id: relayName
  });

  const options = {
    fullDocument: "default",
    maxAwaitTimeMS: 1000
  };

  if (saved?.resumeToken) {
    options.resumeAfter = saved.resumeToken;
  }

  const stream = outbox.watch(
    [{ $match: { operationType: "insert" } }],
    options
  );

  try {
    for await (const change of stream) {
      const event = change.fullDocument;
      if (!event) {
        throw new Error("OUTBOX_DOCUMENT_MISSING");
      }

      // Đường xử lý ví dụ này cần mọi event là payload hợp lệ.
      if (!event.eventType || !event.aggregateId) {
        throw new Error("INVALID_OUTBOX_EVENT");
      }

      await publisher.publish({
        topic: "orders.events",
        key: String(event.aggregateId),
        value: JSON.stringify({
          eventId: String(event._id),
          type: event.eventType,
          schemaVersion: event.schemaVersion,
          aggregateId: event.aggregateId,
          aggregateVersion: event.aggregateVersion,
          tenantId: event.tenantId,
          payload: event.payload
        })
      });

      await checkpoints.updateOne(
        { _id: relayName },
        {
          $set: {
            resumeToken: change._id,
            updatedAt: new Date()
          }
        },
        { upsert: true }
      );
    }
  } finally {
    await stream.close();
  }
}
```

Ở đây:

- `saved.resumeToken` phải được lưu dưới dạng BSON/Extended JSON hỗ trợ bởi driver và **được phục hồi nguyên vẹn**; không tự cắt hoặc biến đổi cấu trúc opaque token.
- `resumeAfter` tiếp tục từ **sau** vị trí đã checkpoint.
- `change._id` là token stream. `event._id` là event ID outbox.
- Nếu publish chưa xác nhận, **không cập nhật checkpoint**.
- Nếu publish xác nhận rồi process crash trước checkpoint, event có thể được phát lại; consumer phải idempotent.

### 8.4. Một relay có thể dừng mà không “mất” sự kiện không?

Nếu oplog vẫn còn lịch sử cần thiết và checkpoint được lưu đúng, relay có thể resume sau gián đoạn. Nhưng **không có bảo đảm vô hạn**:

- Oplog có **retention window** hữu hạn.
- Stream có thể bị `invalidate` khi collection bị drop/rename theo điều kiện hỗ trợ.
- Checkpoint có thể hỏng, bị ghi đè hoặc lưu không đúng kiểu BSON.
- Namespace có thể đã thay đổi.
- Broker có thể không nhận được publish vì relay chết trước acknowledgment.

Transactional outbox giúp **event record tồn tại trong MongoDB** để có thể quét/đối soát khi lịch sử oplog mất; tuy nhiên, nếu outbox record đã bị TTL/deletion trước khi được backfill thì không thể tự phục hồi event chỉ từ collection đó.

### 8.5. Không xóa resume token một cách mù quáng

Nếu `resumeAfter` lỗi vì lịch sử đã mất, cách xử lý **không phải** bỏ token và mở stream mới tại “hiện tại” rồi coi như xong. Làm vậy có thể **bỏ qua toàn bộ sự kiện trong khoảng gián đoạn**.

Cần một **recovery policy**:

1. Dừng relay hoặc chuyển sang trạng thái cần reconciliation.
2. Xác định khoảng dữ liệu/event ID có thể chưa được publish.
3. Quét outbox records còn lưu bền vững theo checkpoint nghiệp vụ.
4. Dùng event ID để deduplicate ở broker/consumer.
5. Thiết lập lại luồng streaming bằng một giao thức handoff tránh gap.
6. Kiểm tra số lượng/đối chiếu trạng thái trước khi tuyên bố phục hồi.

Không có một `resumeAfter` token giả được tạo từ timestamp hoặc ObjectId để thay cho token server đã cấp.

## 9. Checkpoint và ngữ nghĩa giao hàng *at least once*

### 9.1. Crash matrix

| Thời điểm relay crash | Sự kiện đã có trong broker? | Checkpoint đã tiến? | Hệ quả |
| --- | --- | --- | --- |
| Trước publish | Chưa | Chưa | Resume sẽ thử lại; không bỏ mất do checkpoint |
| Publish đang chạy, không có response | Không rõ | Chưa | Retry có thể tạo duplicate; cần idempotency |
| Broker ack xong, trước checkpoint | Có | Chưa | Sau restart sẽ publish lại |
| Sau checkpoint đã lưu bền vững | Có, theo mức ack đã yêu cầu | Có | Resume từ vị trí tiếp theo |
| Checkpoint lưu **trước** publish | Có thể chưa | Có | **Nguy cơ mất event** |

Điều này minh họa một kết luận quan trọng:

> Không thể chỉ đặt hai lệnh `publish()` và `saveCheckpoint()` theo đúng thứ tự để có exactly once end-to-end. Khi chúng thuộc hai hệ thống không chung transaction, một khoảng crash giữa chúng vẫn tồn tại.

### 9.2. Chọn checkpoint durability

Checkpoint cần được lưu **bền vững** theo mức write concern phù hợp. Nếu chỉ ghi checkpoint vào RAM của relay, restart có thể phát lại nhiều event không cần thiết. Nếu ghi checkpoint vào MongoDB với write concern yếu rồi bị rollback, relay có thể lùi về token cũ và publish lại.

Phát lại thường có thể xử lý bằng dedup; bỏ qua event chưa publish nguy hiểm hơn. Vì vậy thông thường ưu tiên **at-least-once + idempotent consumer**, rồi tối ưu duplicate rate sau.

### 9.3. Một checkpoint dùng cho một tiến trình logic

Nếu có hai instance relay cùng đọc một change stream mà cùng dùng checkpoint:

```text
Relay A: publish event #10, checkpoint #10
Relay B: publish event #11, checkpoint #11
Relay A: ghi checkpoint #10 trễ hơn
```

Checkpoint có thể **thụt lùi** nếu không quản lý ownership và thứ tự. Với production, cần một chiến lược:

- **Một active owner** cho từng logical stream/checkpoint;
- leader election/lease kèm **fencing token** để chủ cũ không ghi checkpoint sau khi mất quyền;
- hoặc phân vùng nguồn một cách có chủ đích, mỗi partition có checkpoint riêng.

Không giải quyết bằng cách chạy hai process giống nhau với cùng `resumeAfter` và hy vọng broker sẽ tự dedup mọi message.

### 9.4. Checkpoint khác broker offset

Có ít nhất hai vị trí cần phân biệt:

```text
MongoDB change stream -> relay -> Kafka -> consumer
           |                       |
           v                       v
      resume token             Kafka offset
```

- MongoDB **resume token**: relay đã đọc đến đâu trong change stream.
- Kafka **consumer offset**: consumer đã xử lý/ack đến đâu trong topic partition.
- Business **eventId**: định danh sự kiện để consumer kiểm tra trùng.

Ba thứ không thay thế nhau. Broker có thể nhận message nhưng consumer chưa xử lý; checkpoint relay lúc đó vẫn có thể đã tiến đúng nếu broker đã xác nhận lưu message.

## 10. Consumer idempotent: chống xử lý lặp ở đích

### 10.1. Vì sao consumer phải chịu được duplicate?

Một outbox event `OrderPaid` có `eventId = evt-1001`. Relay publish thành công nhưng crash trước checkpoint. Khi restart, relay resume và publish lại.

Consumer có thể nhận:

```text
evt-1001  (lần thứ nhất)
evt-1001  (lần thứ hai)
```

Nếu consumer gửi email mỗi lần nhận mà không dedup, khách hàng có thể nhận hai email. Nếu consumer tăng số dư hoặc trừ kho mỗi lần, hậu quả còn nghiêm trọng hơn.

### 10.2. Inbox/deduplication table

Một mẫu thông dụng là **inbox**:

```javascript
{
  _id: "shipping-service:evt-1001",
  consumerId: "shipping-service",
  eventId: "evt-1001",
  processedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Kết hợp **consumerId + eventId** làm khóa duy nhất. Nếu consumer phải cập nhật một MongoDB collection, có thể đặt:

1. Insert inbox record.
2. Update business/read model.
3. Commit.

trong **cùng transaction** tại MongoDB của consumer, để dedup record và side effect trong database cùng nguyên tử.

### 10.3. Ví dụ Node.js xử lý event trong một transaction

Giả định `inbox` và `readModels` cùng MongoDB deployment hỗ trợ transaction:

```javascript
async function consumeOrderCreated({
  client,
  db,
  event
}) {
  const session = client.startSession();
  const inbox = db.collection("consumer_inbox");
  const readModels = db.collection("order_read_models");

  const consumerId = "search-projection-v1";
  const inboxId = consumerId + ":" + event.eventId;

  try {
    await session.withTransaction(
      async () => {
        // Insert trước để buộc mỗi event/consumer có một khóa duy nhất.
        await inbox.insertOne(
          {
            _id: inboxId,
            consumerId,
            eventId: event.eventId,
            processedAt: new Date()
          },
          { session }
        );

        // Minh họa event OrderCreated (version 1).
        await readModels.updateOne(
          {
            tenantId: event.tenantId,
            orderId: event.aggregateId
          },
          {
            $setOnInsert: {
              tenantId: event.tenantId,
              orderId: event.aggregateId,
              status: event.payload.status,
              version: event.aggregateVersion
            }
          },
          { upsert: true, session }
        );
      },
      {
        readPreference: "primary",
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );

    return { outcome: "PROCESSED" };
  } catch (error) {
    if (error.code !== 11000) {
      throw error;
    }

    // Đối soát xem khóa trùng có thực sự là event đã xử lý.
    const seen = await inbox.findOne({ _id: inboxId });
    if (seen && seen.eventId === event.eventId) {
      return { outcome: "DUPLICATE_ALREADY_PROCESSED" };
    }
    throw error;
  } finally {
    await session.endSession();
  }
}
```

Lưu ý thiết kế:

- `inbox._id` cần unique trong phạm vi phù hợp. Nếu sharded, phải xét giới hạn uniqueness của shard key.
- `readModels` cũng cần unique key phù hợp cho `(tenantId,orderId)`, để hai event khác nhau không tự tạo hai document đích cho cùng order.
- Code chỉ minh họa `OrderCreated`. Với `OrderPaid`, `OrderCancelled`, logic có thể cần kiểm tra sequence và chuyển trạng thái riêng.
- Nếu consumer thực hiện **HTTP call hoặc gửi email bên ngoài**, transaction MongoDB không tự làm side effect đó nguyên tử; phải dùng thêm outbox hoặc idempotency của hệ đích.
- Nếu nhận `DuplicateKey` do **unique index khác**, không được tự coi mọi mã 11000 là đã xử lý. Trong production cần xác định lỗi thuộc khóa inbox dự kiến, rồi kiểm tra nội dung event/fingerprint.

### 10.4. Broker acknowledgment/offset đặt sau side effect

Với Kafka hoặc queue:

```text
receive event
     |
validate/schema
     |
check dedup/sequence
     |
apply business update (commit)
     |
ack message / commit offset
```

Nếu ack broker **trước** side effect, consumer crash có thể bỏ qua event chưa xử lý. Nếu side effect commit rồi crash trước ack, message được đưa lại — inbox/idempotency bảo vệ khỏi xử lý lặp.

### 10.5. Exactly once end-to-end có nghĩa gì?

Một số broker/stream processor hỗ trợ **exactly-once processing semantics** trong phạm vi nhất định, như transaction giữa các topic/offset của cùng hệ thống. Nhưng MongoDB transaction, broker transaction và một API bên ngoài thường **không nằm trong một atomic transaction duy nhất**.

Vì vậy:

- Có thể đạt **effectively once về tác động nghiệp vụ** khi mọi bước có khóa idempotency và trạng thái được lưu bền vững.
- Có thể vẫn **nhận/publish cùng message nhiều lần**.
- Exactly once trên một broker **không tự bảo đảm** một email hoặc charge thẻ chỉ xảy ra đúng một lần.
- Với webhook, dùng idempotency key của nhà cung cấp và đối soát khi timeout.

Tránh quảng cáo “MongoDB change stream bảo đảm exactly once delivery tới mọi consumer”. Đó không phải contract mặc định.

## 11. Thứ tự sự kiện và phân vùng broker

### 11.1. Thứ tự trong database không tự là thứ tự nghiệp vụ đa nguồn

Change stream cung cấp thứ tự của các event theo cơ chế MongoDB và phạm vi stream, có resume token/clusterTime. Tuy nhiên, khi chuyển sang broker với nhiều partition, worker song song hoặc nhiều service, thứ tự xử lý end-to-end có thể thay đổi.

Ví dụ:

```text
OrderCreated   (version 1)
OrderPaid      (version 2)
OrderShipped   (version 3)

Broker/consumer có nhiều worker:
   Worker B xử lý v3 trước khi worker A xử lý v2
```

Nếu handler đơn thuần `$set: {status: event.status}`, event cũ có thể ghi đè trạng thái mới hơn.

### 11.2. Phân vùng theo aggregate ID

Với Kafka, có thể dùng:

```javascript
publisher.publish({
  topic: "orders.events",
  key: event.aggregateId,
  value: serialize(event)
});
```

Chọn **aggregateId** làm message key giúp các event cùng order có cơ hội vào cùng partition khi topology/partitioning ổn định, thuận lợi cho ordering. Nhưng vẫn phải xét:

- Producer retry và cách broker bảo đảm thứ tự theo cấu hình.
- Thay đổi số partition.
- Nhiều producer độc lập ghi cùng aggregate.
- Consumer retry, rebalance và xử lý song song.
- Sự kiện đến từ nhiều service/source không có shared order.

Kafka partition ordering không phải thay thế đầy đủ cho **aggregateVersion** và quy tắc bảo vệ trạng thái.

### 11.3. Aggregate version/sequence

Một domain event có thể mang:

```javascript
{
  aggregateId: "ORDER-1001",
  aggregateVersion: 3,
  eventType: "OrderShipped"
}
```

Consumer lưu version đã áp dụng. Một chính sách:

- Nếu event version bằng **currentVersion + 1**: áp dụng.
- Nếu event version **≤ currentVersion**: đã xử lý hoặc event quá cũ, đối chiếu eventId.
- Nếu event version **> currentVersion + 1**: có **gap**, chờ/retry/đối soát.

Đây là chính sách khi mọi thay đổi quan trọng đều tạo một event với sequence liên tục. Nếu chỉ một số trạng thái phát sự kiện, không được tự dùng MongoDB document `version` làm sequence liên tục của event mà chưa thiết kế mapping.

### 11.4. Gắn sequence nguyên tử với business update

Một cách:

```javascript
// Trong cùng transaction:
const updated = await orders.findOneAndUpdate(
  {
    _id: orderId,
    status: "NEW"
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  },
  {
    session,
    returnDocument: "after",
    includeResultMetadata: false
  }
);

if (!updated) {
  throw new Error("INVALID_STATE_OR_NOT_FOUND");
}

await outbox.insertOne(
  {
    _id: eventId,
    eventType: "OrderPaid",
    aggregateId: String(orderId),
    aggregateVersion: updated.version,
    payload: { status: "PAID" }
  },
  { session }
);
```

MongoDB Node.js driver có khác biệt API trả về của `findOneAndUpdate()` theo version; cần dùng đúng contract `includeResultMetadata` và driver. Không chạy hai thao tác của cùng transaction song song bằng `Promise.all()`.

Nếu chỉ có một event cho một phần thay đổi của order, sequence cho event nên là **giao thức riêng được xác định**, không suy luận rằng mọi version đều có tương ứng đúng một event.

## 12. Khởi động lần đầu, backfill và xử lý khoảng trống

### 12.1. Vấn đề khi bắt đầu watch ở “hiện tại”

Giả sử outbox đã có 100.000 event trước khi relay mới được triển khai. Nếu relay chỉ gọi:

```javascript
const stream = outbox.watch();
```

thì nó không tự phát lại **toàn bộ lịch sử document outbox** từ lúc collection được tạo. Change stream theo dõi thay đổi từ một vị trí thích hợp trong lịch sử oplog, không phải lệnh “đọc mọi document đang có rồi stream những cái mới”.

Muốn xử lý backlog lịch sử, cần **backfill/snapshot scan** kết hợp streaming.

### 12.2. Race giữa scan và watch

Phương án ngây thơ:

```text
1. Scan outbox từ đầu tới cuối
2. Sau khi scan xong mới mở change stream
```

Giữa bước 1 và 2, service có thể ghi một outbox record mới. Nó không nằm trong snapshot scan đã hoàn tất và cũng có thể xảy ra **trước khi stream bắt đầu**, tạo **khoảng trống mất sự kiện**.

Phương án ngược:

```text
1. Mở stream
2. Scan outbox
3. Bắt đầu tiêu thụ stream
```

có thể đưa cùng event qua cả scan và stream. **Trùng có thể xử lý bằng eventId**, nhưng vẫn phải đảm bảo stream thực sự đã được đăng ký/định vị trên server trước thời điểm bắt đầu scan; một số API driver khởi tạo cursor lazily.

### 12.3. Chiến lược handoff có kiểm soát

Một kiến trúc thường dùng:

1. Định nghĩa **consistent watermark/cluster time** hoặc cơ chế bắt đầu stream đúng theo server/driver.
2. Bắt đầu change stream ở mốc có khả năng bao phủ tất cả write trong giai đoạn scan.
3. Scan những outbox records chưa xử lý theo khóa/watermark ổn định.
4. Publish các event scan và stream bằng cùng **eventId**; consumer dedup.
5. Sau khi hoàn tất backfill, tiếp tục live stream và lưu resume token.
6. Đối soát **số lượng, khoảng sequence và bản ghi còn chưa publish**.

Chi tiết thuật toán phải xét snapshot, read concern, token, oplog window, startup semantics và write race. **Không coi hai bước “watch rồi find” là bằng chứng đủ cho gap-free handoff** nếu chưa xác nhận stream đã mở ở mốc thích hợp.

### 12.4. Outbox retention phải dài hơn thời gian recovery

Giả sử:

```text
Oplog window:                12 giờ
Relay outage:                18 giờ
Outbox document retention:    7 ngày
```

Relay có thể không resume change stream vì oplog history đã mất. Nhưng nếu outbox records vẫn còn, hệ thống có cơ hội scan/reconcile các sự kiện chưa publish.

Ngược lại, nếu TTL của outbox chỉ 6 giờ, cả oplog lẫn outbox có thể mất những records cần thiết, không còn nguồn đầy đủ để tự khôi phục.

Chọn retention dựa vào **SLO phục hồi, thời gian outage tối đa, khả năng backfill và nghĩa vụ audit**, không chỉ dung lượng.

### 12.5. Không đặt TTL lên outbox một cách thiếu điều kiện

Ví dụ:

```javascript
// Cẩn thận: TTL tự xóa theo thời gian,
// không cần biết consumer nào đã xử lý hay chưa.
outbox.createIndex(
  { occurredAt: 1 },
  { expireAfterSeconds: 86400 }
);
```

TTL index có thể xóa một event chưa được broker/consumer nhận. Đây là mẫu **không phù hợp** nếu cần đảm bảo dữ liệu không bị mất qua outage dài hơn 24 giờ.

Trong production, cân nhắc:

- cleanup chỉ sau khi đã có trạng thái delivery/checkpoint đủ chứng cứ;
- retention lớn hơn recovery SLO với margin;
- archive sang storage bền vững nếu cần audit;
- chính sách cho nhiều consumer/subscriber;
- đối soát trước khi xóa các event cũ.

## 13. Resume token, invalidate và các lỗi khó

### 13.1. `resumeAfter` là gì?

MongoDB change event có `_id` opaque resume token. Khi restart:

```javascript
const saved = await checkpoints.findOne({
  _id: "orders-to-broker"
});

const options = saved?.resumeToken
  ? { resumeAfter: saved.resumeToken }
  : {};

const stream = outbox.watch([], options);
```

`resumeAfter` yêu cầu tiếp tục **sau** event được token đại diện, trong điều kiện lịch sử còn sẵn. Không tự thay token bằng document `_id` hoặc timestamp.

### 13.2. `startAfter`, `startAtOperationTime` và giới hạn

Cần phân biệt:

| Tùy chọn | Ý nghĩa khái quát |
| --- | --- |
| `resumeAfter` | Resume từ sau một resume token được chấp nhận |
| `startAfter` | Bắt đầu sau một resume token, có những trường hợp dùng được sau invalidate theo quy tắc hỗ trợ |
| `startAtOperationTime` | Bắt đầu từ một operation time phù hợp, khi lịch sử và phiên bản hỗ trợ |

Không kết hợp những tùy chọn loại trừ nhau tùy tiện. Không tự tạo `startAtOperationTime` từ `Date.now()` rồi coi đó là cluster time hợp lệ; nó dùng BSON Timestamp của server với semantics riêng.

### 13.3. Invalidate event

Một số thay đổi namespace như drop collection, rename hoặc drop database có thể khiến stream bị **invalidate** tùy phạm vi và loại operation. Sau invalidate:

- `resumeAfter` không thể được dùng như một cách resume xuyên invalidate trong các trường hợp bị giới hạn.
- `startAfter` có những trường hợp được dùng để bắt đầu stream mới sau invalidate, theo tài liệu MongoDB.
- Ứng dụng phải quyết định việc namespace cũ biến mất có còn phù hợp với nguồn outbox không.

Không tự “bỏ qua invalidate” rồi chuyển sang collection mới cùng tên mà không kiểm tra event ID, schema, dữ liệu đã publish và nguồn quyền sở hữu.

### 13.4. Tình huống oplog history lost

Một relay dừng 48 giờ trong khi cửa sổ oplog còn 6 giờ. Resume token cũ có thể không còn có thể sử dụng, dẫn đến lỗi liên quan lịch sử change stream.

Hướng xử lý:

1. Không xóa checkpoint và silently start “now”.
2. Kích hoạt reconciliation/backfill trên outbox retained.
3. Kiểm tra đã xử lý đủ event và thiết lập live stream không tạo gap.
4. Điều chỉnh retention hoặc capacity để giảm khả năng lặp lại.

Tăng oplog size **sau khi lịch sử đã bị loại** không khôi phục những mục oplog cũ.

### 13.5. Không làm biến dạng resume token trong aggregation pipeline

Change stream yêu cầu trường `_id` của change event chứa resume token nguyên vẹn. Không viết pipeline:

```javascript
// Không làm như vậy khi watch: xóa _id resume token.
[
  { $project: { _id: 0, operationType: 1 } }
]
```

Làm mất hoặc sửa token có thể khiến stream không hoạt động/resume được theo giới hạn MongoDB.

Hãy chỉ lọc theo các field phù hợp, giữ nguyên `_id` của change event. Nếu cần map payload sang schema broker, thực hiện ở **application relay**, không thay `_id` hệ thống trong server-side change stream pipeline.

### 13.6. Không dùng một token cho một stream khác tùy ý

Một token thuộc vị trí và phạm vi stream được server cung cấp. Không coi token collection A là checkpoint chung có thể mở collection B bất kỳ, hoặc tự hoán đổi giữa database/deployment khác nhau. Khi đổi topology, namespace, watch pipeline hoặc cấu hình, cần đánh giá tính tương thích/resume theo tài liệu.

## 14. Hệ thống nhận sự kiện: Kafka, queue và webhook

### 14.1. Kafka

Một pipeline:

```text
MongoDB outbox
      |
      v
 Change Stream Relay
      |
      v
 Kafka topic "orders.events"
      |
      +----> Shipping consumer group
      |
      +----> Analytics consumer group
      |
      +----> Notification consumer group
```

Kafka phù hợp với:

- một sự kiện có nhiều consumer group;
- lưu message theo retention của Kafka;
- replay theo offset;
- partition ordering theo key.

Lưu ý:

- Kafka có offset riêng, không phải Mongo resume token.
- Topic retention cũng hữu hạn, cần thiết kế theo SLO.
- Producer ack, idempotent producer và transactions Kafka có semantics riêng.
- Relay từ MongoDB sang Kafka vẫn cần idempotency nếu không có cơ chế transactional bridge phù hợp.

### 14.2. RabbitMQ hoặc message queue

Một queue/broker với acknowledgment có thể phù hợp cho phân phối công việc và retry. Kiểm tra:

- persistent messages và durability;
- publisher confirmations;
- consumer acknowledgments;
- redelivery/dead-letter;
- routing keys/exchanges;
- ordering khi có nhiều consumer.

Không xem `publish()` trả success chỉ vì API gọi xong; adapter phải đợi **broker acknowledgment theo contract cần thiết**.

### 14.3. Webhook hoặc dịch vụ HTTP

Relay có thể gọi HTTP trực tiếp:

```text
outbox -> relay -> POST /shipping/events
```

Nhưng:

- HTTP timeout không rõ server bên nhận đã xử lý chưa.
- Có thể gửi lại cùng eventId.
- Cần authentication, signature/mTLS nếu áp dụng.
- Bên nhận phải idempotent.
- Khi đích lỗi dài ngày, cần retry/backoff, DLQ hoặc một durable queue trung gian.

Đối với nhiều đích nhận, queue/broker thường tách dependency tốt hơn gọi HTTP trực tiếp trong đường commit nghiệp vụ.

### 14.4. Tại sao không publish riêng cho từng consumer từ một cờ?

Một event có ba subscriber. Nếu relay lưu:

```javascript
{ published: true }
```

sau khi giao cho subscriber A, nó không biết B và C đã nhận chưa.

Cần:

- một broker có fan-out/consumer groups với offset riêng; hoặc
- bảng trạng thái per-destination/per-consumer; hoặc
- mỗi đích có checkpoint và replay riêng.

**Delivery đến broker** và **processing bởi từng consumer** là các mốc khác nhau.

## 15. Schema evolution và tương thích contract

### 15.1. Vì sao event cần `schemaVersion`?

Hôm nay sự kiện:

```javascript
{
  eventType: "OrderPaid",
  schemaVersion: 1,
  payload: {
    orderNo: "O-100",
    amountCents: 120000
  }
}
```

Phiên bản sau bổ sung:

```javascript
{
  eventType: "OrderPaid",
  schemaVersion: 2,
  payload: {
    orderNo: "O-100",
    amountCents: 120000,
    currency: "VND",
    paymentMethod: "BANK_TRANSFER"
  }
}
```

Nếu consumer còn chạy schema v1, trường mới có thể được bỏ qua nếu hợp đồng cho phép. Nhưng đổi `amountCents` từ số nguyên sang string hoặc thay nghĩa của `status` là **breaking change** nếu không có kế hoạch migration.

### 15.2. Quy tắc tiến hóa

- Thêm field optional có default hợp lý thường dễ tương thích hơn đổi tên field bắt buộc.
- Không tái sử dụng một eventType cho hai ý nghĩa nghiệp vụ khác hẳn.
- Gắn `schemaVersion` hoặc quản lý schema registry theo hệ thống.
- Version hóa cả schema và trạng thái business khi cần, tránh nhầm hai loại version.
- Có consumer contract test ở ranh giới tích hợp.
- Lưu đủ event payload trong outbox để replay theo schema đã phát.

Một event đã publish nên được xem là **lịch sử bất biến**. Không thay đổi toàn bộ payload cũ trong outbox chỉ để phù hợp consumer mới nếu điều đó phá tính truy vết.

### 15.3. Bảo vệ dữ liệu nhạy cảm

Change stream trực tiếp có thể bộc lộ **toàn bộ document** nếu bật fullDocument. Trước khi đưa vào broker đa người dùng:

- Whitelist field được phép xuất.
- Giảm tối đa PII, access token, thông tin thanh toán.
- Mã hóa khi truyền/lưu ở nơi phù hợp.
- Dùng ACL cho topic/queue và RBAC cho MongoDB.
- Áp dụng tenant isolation ở producer và consumer.
- Xác định retention/deletion policy phù hợp.

Không cho phép consumer truy cập toàn bộ bản ghi database chỉ vì nó cần biết event `OrderPaid`.

### 15.4. Tracing

Nên đưa `correlationId` và `eventId` vào message để theo dõi:

```text
HTTP request req-42
    |
    v
MongoDB transaction
    |
    +-- order update
    +-- outbox event evt-77
                 |
                 v
             Kafka publish
                 |
                 v
       shipping consumer evt-77
                 |
                 v
             shipment created
```

Từ đó SRE có thể trả lời “event này có được commit, publish và xử lý hay chưa?” dựa trên log/metric, không phụ thuộc vào một cờ mơ hồ.

## 16. Quản lý lỗi và replay

### 16.1. Lỗi ở từng chặng

| Chặng | Lỗi có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| MongoDB business transaction | Validation, write conflict, timeout | Abort/retry theo error label, idempotency request |
| Outbox insert | Duplicate event ID, schema invalid | Đối soát operationId, không retry mù quáng |
| Change stream | Network, failover, invalidate, history lost | Resume token khi hợp lệ, recovery/backfill nếu cần |
| Relay mapping | Payload sai schema | Quarantine/alert; không bỏ qua âm thầm |
| Broker publish | Timeout, unavailable, không có ack | Retry có backoff, không advance checkpoint |
| Checkpoint write | DB lỗi sau broker ack | Có thể replay; consumer dedup |
| Consumer update | DB conflict, validation, duplicate | Retry theo loại lỗi, inbox/idempotency |
| External side effect | HTTP timeout, email/charge không rõ | Idempotency key và đối soát nhà cung cấp |
| Broker offset ack | Consumer crash sau xử lý | Redelivery + inbox bảo vệ |

### 16.2. Retryable và non-retryable

**Retryable** có thể gồm network glitch ngắn, broker tạm unavailable, một số transient MongoDB errors hoặc consumer contention.

**Không nên retry y nguyên vô hạn**:

- Event thiếu field bắt buộc.
- Schema version không được hỗ trợ.
- Vi phạm business invariant.
- Credential/authorization sai.
- Duplicate event đã xử lý.
- Resume token đã mất lịch sử.

Đặt retry budget, backoff/jitter, dead-letter/quarantine và cảnh báo. Với poison message, phải có runbook sửa/replay **sau khi nguyên nhân được giải quyết**.

### 16.3. Đừng bỏ poison event rồi advance checkpoint tùy tiện

Nếu relay gặp một outbox event invalid:

```text
event #100: ok
event #101: invalid payload
event #102: ok
```

Việc “log #101 rồi checkpoint tới #102” có thể làm #101 không được xử lý bao giờ. Nếu policy cho phép chuyển event invalid sang **durable quarantine/DLQ**, phải xác nhận việc ghi quarantine thành công và lưu bằng chứng/replay plan trước khi tiến checkpoint.

Chính sách bắt buộc tùy nghiệp vụ:

- Dừng pipeline để không mất sự kiện quan trọng.
- Hoặc chuyển sang quarantine được xác nhận bền vững, rồi tiếp tục.
- Không silently discard.

### 16.4. Khả năng replay không bằng khả năng tái tạo business state

Replay một event `OrderPaid` có thể hợp lý để xây lại read model. Nhưng nếu consumer có side effect “gửi email thanh toán” hoặc “trừ số dư”, replay **không được thực hiện side effect lần nữa** nếu không có ý định nghiệp vụ mới.

Một hệ thống nên phân biệt:

- **Projection rebuild**: tính lại read model từ dữ liệu lịch sử.
- **Side-effect replay**: có thể cần vô hiệu hóa hành động ngoài đời hoặc dùng idempotency.
- **Reconciliation**: so trạng thái cuối giữa nguồn và đích rồi sửa sai lệch.

Không có một nút “replay all” an toàn cho mọi consumer.

## 17. Quan sát hệ thống từ commit tới consumer

### 17.1. Chỉ số cốt lõi

| Metric | Ý nghĩa |
| --- | --- |
| `outbox_events_created_total` | Số event đã commit vào outbox |
| `outbox_to_broker_publish_latency` | Độ trễ từ event commit tới broker ack |
| `relay_checkpoint_age_seconds` | Độ cũ của tiến độ relay |
| `relay_publish_failures_total` | Lỗi publish |
| `relay_resume_attempts_total` | Số lần resume/reconnect |
| `resume_token_history_lost_total` | Lỗi không thể resume do lịch sử |
| `outbox_unpublished_backlog` | Backlog theo chính sách đối soát |
| `broker_consumer_lag` | Message chờ consumer trong broker |
| `consumer_duplicate_events_total` | Số event được dedup |
| `consumer_processing_failures_total` | Lỗi xử lý nghiệp vụ |
| `dlq_or_quarantine_size` | Event cần can thiệp |
| `mongodb_oplog_window_seconds` | Khoảng lịch sử nguồn còn giữ |

Tên metric là **gợi ý tự định nghĩa**, không phải tên mặc định MongoDB/Prometheus cung cấp sẵn.

### 17.2. Cách đo độ trễ đúng

Có nhiều độ trễ:

```text
T1: MongoDB commit
T2: relay quan sát change event
T3: broker ack
T4: consumer nhận event
T5: consumer commit side effect

T2 - T1 = change stream/relay observation latency
T3 - T1 = end-to-end publish latency
T5 - T1 = business propagation latency
```

Không gọi tất cả là “MongoDB replication lag”. Change stream latency, broker lag và consumer processing latency là các thành phần khác nhau.

Nếu timestamp lấy từ nhiều máy, độ lệch đồng hồ có thể ảnh hưởng phép đo; cần đồng bộ thời gian hoặc dùng số đo có cùng nguồn/trace, ghi rõ định nghĩa metric.

### 17.3. Oplog window là chỉ số sống còn

Ví dụ:

```text
Oplog window:              12 giờ
Relay đang chậm:           10 giờ
Headroom ước lượng:         2 giờ
```

Nếu write load tăng làm window co, relay có thể mất khả năng resume. Nên cảnh báo **trước khi headroom về 0**, đồng thời giữ outbox retention đủ cho backfill.

Một phép trừ time window – checkpoint age chỉ là **ước lượng**; cần xét vị trí resume token và tình trạng thực tế của sync source.

### 17.4. Runbook khi broker ngắt dài

1. Xác nhận MongoDB và outbox vẫn ghi bình thường.
2. Quan sát broker producer errors và backpressure.
3. Giữ relay ở trạng thái retry có giới hạn, **không advance checkpoint** nếu publish chưa ack.
4. Theo dõi oplog window, thời gian outage và outbox retention.
5. Khi broker phục hồi, theo dõi backlog drain và duplicate rate.
6. Nếu history lost, chuyển sang reconciliation/backfill.
7. Đối soát business events/consumer state, không chỉ kiểm “relay connected”.

## 18. Thực hành `mongosh` và Node.js an toàn

### 18.1. Chuẩn bị collection test

Trong `mongosh` kết nối **replica set test**:

```bash
mongosh "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/?replicaSet=rs0"
```

Địa chỉ chỉ minh họa. Thay host, TLS và authentication theo môi trường được phép.

```javascript
const lab = db.getSiblingDB("mongo_change_stream_row279_lab");
const orders = lab.getCollection("orders_demo");
const outbox = lab.getCollection("outbox_demo");

const runId = "row279-" + new ObjectId().toHexString();
const orderId = new ObjectId();
const eventId = new ObjectId();

print("database=" + lab.getName());
print("runId=" + runId);
print("orderId=" + orderId);
print("eventId=" + eventId);
```

Ví dụ tạo một transaction nhỏ; chỉ chạy khi đã xác nhận database test không được chia sẻ cho người khác và đã có quyền:

```javascript
const session = db.getMongo().startSession();
const txLab = session.getDatabase(lab.getName());

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  txLab.getCollection("orders_demo").insertOne({
    _id: orderId,
    runId,
    orderNo: "ORDER-279",
    status: "NEW",
    version: 1
  });

  txLab.getCollection("outbox_demo").insertOne({
    _id: eventId,
    runId,
    eventType: "OrderCreated",
    schemaVersion: 1,
    aggregateId: orderId.toHexString(),
    aggregateVersion: 1,
    occurredAt: new Date(),
    payload: {
      orderNo: "ORDER-279",
      status: "NEW"
    }
  });

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (_ignored) {}
  throw error;
} finally {
  session.endSession();
}

printjson(orders.findOne({ _id: orderId, runId }));
printjson(outbox.findOne({ _id: eventId, runId }));
```

Ghi chú: trên một số phiên bản, transaction tạo collection mới có điều kiện/giới hạn riêng. Nếu `orders_demo` và `outbox_demo` chưa tồn tại, hãy **tạo hai collection trước transaction** bằng lệnh `createCollection()` trong database lab khi được phép, rồi chạy lại transaction trên namespace đã chuẩn bị. Không tạo/drop collection hệ thống hay collection production để vượt qua lỗi. Với sharded cluster, transaction DDL và namespace có thêm giới hạn theo phiên bản.

### 18.2. Quan sát change stream trong một phiên riêng

Để quan sát **event mới**, mở `mongosh` thứ hai, cùng replica set và database test. Vì watch thường chờ cho đến khi có event, chạy producer **sau khi watcher đã bắt đầu quan sát**:

```javascript
const lab = db.getSiblingDB("mongo_change_stream_row279_lab");
const outbox = lab.getCollection("outbox_demo");

const stream = outbox.watch(
  [{ $match: { operationType: "insert" } }],
  { fullDocument: "default" }
);

// Vòng lặp có thể chờ sự kiện; dừng có chủ đích sau khi quan sát.
for (const change of stream) {
  print("Resume token:");
  printjson(change._id);
  print("Business event ID:");
  printjson(change.documentKey._id);
  printjson(change.fullDocument);
  break;
}

stream.close();
```

Thực hiện một outbox insert **mới** từ phiên producer khi watcher đã đang chờ; nếu chỉ chèn trước khi mở watch, stream không phải là câu lệnh scan lịch sử. Không dùng ví dụ watcher làm relay production vì nó không lưu checkpoint/ack và không xử lý lỗi.

Nếu môi trường chỉ cho một phiên shell, có thể dùng đoạn Node.js relay và script producer ở hai process riêng, hoặc quan sát bằng công cụ monitoring; không cần cố tình làm chậm/đứt replication.

### 18.3. Xem resume token mà không biến đổi

Trong output watcher:

```javascript
printjson(change._id);
```

Không:

```javascript
// Sai: documentKey không phải token.
const wrongToken = change.documentKey._id;
```

Trong ứng dụng, hãy persist `change._id` bằng BSON serializer tương thích hoặc một dạng Extended JSON cho phép khôi phục đủ cấu trúc. Không chuyển thành chuỗi tự chế rồi cắt/bỏ field.

### 18.4. Dọn đúng dữ liệu thử nghiệm

Trong phiên có `runId`, `orderId`, `eventId` của chính lượt test:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
printjson(orders.findOne({ _id: orderId, runId }));
printjson(outbox.findOne({ _id: eventId, runId }));
```

Chỉ khi xác nhận đúng hai document sở hữu:

```javascript
const removedOrder = orders.deleteOne({
  _id: orderId,
  runId
});

const removedOutbox = outbox.deleteOne({
  _id: eventId,
  runId
});

printjson({
  orderDeleted: removedOrder.deletedCount,
  outboxDeleted: removedOutbox.deletedCount
});
```

**Chú ý:** xóa outbox test cũng tạo change event loại delete. Trong hệ thống thật, không xóa outbox chưa publish hoặc chưa đủ retention. Không chạy `deleteMany({})`, `dropDatabase()`, thao tác trực tiếp `local.oplog.rs` hoặc xóa checkpoint của relay đang chạy.

## 19. So sánh kiến trúc và các trade-off

| Thuộc tính | CDC trực tiếp từ business collection | Transactional outbox + change stream |
| --- | --- | --- |
| Sự kiện biểu đạt | Database change | Domain event do service quyết định |
| Cần thêm collection outbox | Không | Thường có |
| Chống dual-write business DB + broker | Không tự giải quyết side effect ngoài DB | Ghi business state + event intent nguyên tử trong MongoDB |
| Nội dung event ở thời điểm nghiệp vụ | Có thể cần tái tạo từ update hoặc lookup | Payload lưu trong transaction |
| Schema coupling | Consumer có thể phụ thuộc schema database | Có thể có contract độc lập |
| Chi phí ghi | Ít document bổ sung hơn | Thêm outbox insert/transaction |
| Khả năng backfill sau mất oplog | Cần nguồn khác/snapshot state, có thể không tái tạo đủ event | Có thể quét event outbox còn giữ |
| Retention và cleanup | Theo nguồn oplog/snapshot | Phải quản lý outbox lifecycle |
| Multi-consumer fanout | Qua broker/connector | Qua broker/connector |
| Exactly once end-to-end mặc định | Không | Không |
| Use case điển hình | Search index, cache sync, analytics CDC | OrderPaid, PaymentCaptured, nghiệp vụ liên dịch vụ |

Kết luận thiết kế:

- **Dùng change stream trực tiếp** khi consumer thật sự cần phản chiếu trạng thái database và hiểu schema nguồn.
- **Dùng transactional outbox** khi service cần phát **ý nghĩa nghiệp vụ rõ ràng** và không được mất event do khoảng hở giữa ghi database và publish.
- **Dùng inbox/idempotency ở consumer** vì outbox relay vẫn có thể giao cùng event hơn một lần.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cập nhật MongoDB rồi publish Kafka như hai bước độc lập | Crash giữa hai bước làm mất domain event | Transactional outbox |
| Publish broker bên trong transaction callback | Side effect không rollback, callback retry có thể publish lặp | Chỉ ghi outbox trong transaction; relay publish sau commit |
| Đọc `updateDescription` rồi suy ra mọi domain event | Migration/admin update có thể phát nhầm event | Event nghiệp vụ tường minh |
| Coi `change._id` là ID document nghiệp vụ | Nhầm resume token với document ID | Dùng `documentKey._id` / `fullDocument._id` cho record |
| Coi `fullDocument:"updateLookup"` là snapshot đúng thời điểm update | Payload có thể phản ánh update sau | Outbox payload hoặc pre/post images theo semantics phù hợp |
| Checkpoint trước broker acknowledgment | Có thể bỏ mất event | Ack broker rồi mới checkpoint |
| Crash sau publish thì chắc chắn không lặp | Resume sẽ phát lại nếu checkpoint chưa lưu | Consumer idempotent |
| Thấy resume token hết hạn rồi xóa checkpoint và start now | Mất những event trong khoảng outage | Reconciliation/backfill |
| Lưu resume token qua serialize làm mất kiểu BSON | Không resume được | Lưu/khôi phục nguyên vẹn |
| Đổi `_id` change event trong pipeline `watch()` | Phá resume semantics | Giữ `_id` token của change event |
| Chỉ dùng timestamp để nhận diện event | Có thể trùng, sai ordering | Event ID ổn định và aggregate sequence |
| Cho hai relay dùng cùng checkpoint không có leader | Publish trùng, checkpoint lùi | Single owner/lease/fencing hoặc partition |
| Coi Kafka offset là MongoDB resume token | Không thể đối soát hai chặng | Quản lý checkpoint riêng |
| Consumer ack trước khi commit side effect | Crash gây mất tác dụng nghiệp vụ | Commit side effect rồi ack |
| Consumer update trạng thái mà không kiểm event version | Event cũ có thể ghi đè state mới | Per-aggregate ordering/version và gap detection |
| TTL outbox quá ngắn | Không còn dữ liệu backfill sau outage | Retention theo recovery SLO |
| Một cờ `published:true` cho nhiều subscriber | Không phản ánh từng subscriber | Broker consumer groups hoặc per-destination state |
| “Exactly once” dựa trên một lệnh publish thành công | Crash/retry vẫn gây duplicate | At-least-once + idempotency/đối soát |
| Replay event thanh toán như event projection bình thường | Có thể trừ tiền/gửi email lại | Idempotency/compensation |
| Mở change stream cho mỗi user cuối | Tăng số cursor và chi phí server | Một relay/connector theo nguồn/partition |
| Dùng change stream trên standalone `mongod` | Không hỗ trợ topology | Replica set/sharded cluster |

## 21. Câu hỏi ôn tập và bài tập thiết kế

### Bài A. Dual-write và transactional outbox

Một API tạo đơn hàng rồi gọi `publisher.publish()`. MongoDB commit thành công, process chết trước publish.

1. Vì sao có thể xảy ra việc hệ thống giao hàng không biết đơn đã tạo?
2. Thay hai thao tác độc lập bằng transaction ghi `orders` + `outbox` có tác dụng gì?
3. Vì sao vẫn phải có relay riêng?
4. Tại sao relay publish đúng một lần không được bảo đảm chỉ vì MongoDB transaction thành công?

### Bài B. Token và event ID

Watcher nhận:

```javascript
{
  _id: { _data: "opaque-token" },
  documentKey: { _id: "evt-12" },
  fullDocument: {
    _id: "evt-12",
    eventType: "OrderPaid"
  }
}
```

Hãy xác định:

- Field nào lưu để `resumeAfter`?
- Field nào gửi cho consumer làm idempotency key?
- Nếu hai lần publish khác nhau cùng eventId, consumer nên làm gì?

### Bài C. Crash matrix

Relay publish `evt-12`, broker ack, nhưng mất điện trước khi lưu checkpoint.

1. Sau restart, event có thể được phát lại không?
2. Tại sao không nên checkpoint trước publish để tránh duplicate?
3. Consumer inbox giúp gì?
4. Nếu side effect là gọi payment gateway, cần điều kiện gì ngoài inbox?

### Bài D. Sự kiện đến sai thứ tự

Consumer nhận:

```text
OrderShipped v3
OrderPaid v2
```

nhưng read model đang ở `v1`.

- Có nên đặt ngay status SHIPPED rồi tiếp tục nhận v2 không?
- Nếu consumer yêu cầu sequence liên tục, phải xử lý gap như thế nào?
- Kafka partition key chọn theo field nào để hỗ trợ ordering?
- Khi nào cần reconciliation thay vì chờ mãi?

### Bài E. Lịch sử oplog mất

Relay ngắt 30 giờ. Oplog window còn 8 giờ, outbox retention 7 ngày.

1. Vì sao `resumeAfter` có thể thất bại?
2. Outbox còn giữ sự kiện có giúp phục hồi không?
3. Làm sao scan backlog và mở live stream mà không có khoảng gap?
4. Vì sao eventId dedup là thiết yếu trong quá trình backfill?

### Bài F. Full document không phải domain snapshot

Order đổi `NEW → PAID` rồi rất nhanh `PAID → SHIPPED`. Relay nhận update event `NEW → PAID` với `fullDocument:"updateLookup"`.

1. Vì sao `fullDocument.status` có thể là `SHIPPED`?
2. Nếu cần thông báo `OrderPaid` với paymentId đúng tại thời điểm thanh toán, nên lấy dữ liệu từ đâu?
3. Những trường hợp nào CDC trực tiếp vẫn phù hợp?

### Bài G. Nhiều consumer

Một event `OrderCreated` được dùng cho Shipping, Search và Analytics.

1. Vì sao một cờ `published` không cho biết từng consumer đã xử lý?
2. Broker với consumer group hỗ trợ gì?
3. Mỗi consumer cần checkpoint/dedup ra sao?
4. Nếu Analytics cần rebuild, có nên gửi lại email thông báo không?

### Bài H. Xử lý poison event

Relay gặp event thiếu `aggregateId` nhưng phía sau còn hàng trăm sự kiện hợp lệ.

1. Vì sao không nên log rồi bỏ qua mà vẫn checkpoint qua event lỗi?
2. Durable quarantine/DLQ có vai trò gì?
3. Cần metric/alert nào?
4. Điều kiện nào cho phép replay sau khi sửa schema?

## 22. Tài liệu tham khảo

Khi triển khai, phải đối chiếu **MongoDB server/driver version** và broker đang dùng:

- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — cơ chế, điều kiện và giới hạn của change streams.
- [Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — các field của change event.
- [Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream) — resume tokens và continuation.
- [Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — ảnh trước/sau ở phiên bản hỗ trợ.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity đa document và session.
- [Node.js Driver Change Streams](https://www.mongodb.com/docs/drivers/node/current/monitoring-and-logging/change-streams/) — API `watch()` và cursor.
- [Node.js Driver Transactions](https://www.mongodb.com/docs/drivers/node/current/crud/transactions/) — `withTransaction()` và transaction lifecycle.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — retention và cửa sổ lịch sử.
- [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — tích hợp source/sink connector với Kafka.

Các nguồn trên là điểm bắt đầu để kiểm tra phiên bản, quyền, read/write concern, resume behavior, connector mappings và giới hạn. Khi dùng Kafka Connect/Debezium hoặc một connector bên thứ ba, cần đọc thêm tài liệu riêng của connector để hiểu semantics snapshot, offset, retry và triển khai.

## 23. Kết luận

**Change streams** cung cấp cách quan sát thay đổi MongoDB để xây CDC gần thời gian thực, nhưng **database change không tự là domain event**, và oplog không phải kho sự kiện vĩnh viễn. Khi consumer chỉ cần phản chiếu trạng thái dữ liệu, CDC trực tiếp có thể đủ; khi service cần phát ý nghĩa nghiệp vụ và tránh khoảng hở giữa ghi dữ liệu với phát sự kiện, **transactional outbox** là một kiến trúc phù hợp.

Mẫu đáng tin cậy là: **business update + outbox insert cùng MongoDB transaction → relay đọc change stream → broker xác nhận publish → relay lưu resume token → consumer xử lý idempotent rồi mới ack**. Nếu crash sau publish trước checkpoint, có thể phát lại; đó là hệ quả có thể kiểm soát bằng eventId/inbox và là lý do không tuyên bố exactly once end-to-end một cách dễ dãi.

Thiết kế production cần thêm **outbox retention đủ dài, backfill không có gap, per-aggregate ordering, schema versioning, quyền truy cập, chống rò rỉ dữ liệu, quan sát lag và runbook khi mất oplog history**. Mục tiêu không phải chỉ là “nhận được một change event”, mà là **chuyển được ý định nghiệp vụ đã commit đến những hệ thống nhận một cách có thể kiểm chứng, phục hồi và không gây tác dụng lặp sai**.
