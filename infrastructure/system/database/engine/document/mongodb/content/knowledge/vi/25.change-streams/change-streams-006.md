# `resumeAfter`, `startAfter`, `startAtOperationTime` và các tình huống khôi phục trong MongoDB Change Streams

## 1. Vấn đề cốt lõi: consumer phải tiếp tục từ đâu?

MongoDB **Change Streams** cho phép ứng dụng theo dõi sự kiện thay đổi dữ liệu mà không phải tự tail oplog. Một consumer có thể dùng chúng để cập nhật search index, gửi sự kiện tới message broker, làm mới cache, tạo read model hoặc thực hiện những nghiệp vụ phản ứng với insert/update/delete.

Giả sử service `order-indexer` nghe `commerce.orders`:

```text
MongoDB                         Change stream consumer                    Search index
   |                                     |                                    |
   | -- E1: insert O100 ----------------> | -- index O100 ------------------> |
   | -- E2: update O100 ----------------> | -- update O100 -----------------> |
   |                                     X  service crash                     |
   | -- E3: insert O101                 |                                    |
   | -- E4: delete O100                 |                                    |
   |                                     |  restart                           |
   |                                     ?  tiếp tục từ event nào?            |
```

Nếu consumer mở `watch()` mới mà không có checkpoint, các sự kiện E3/E4 diễn ra khi service tắt có thể bị bỏ qua. Nếu mở lại quá sớm, E2 có thể được xử lý lại; nếu handler không idempotent, điều đó có thể gây tác dụng phụ lặp.

MongoDB cung cấp ba lựa chọn điểm bắt đầu khi **mở** stream:

- **`resumeAfter`**: tiếp tục sau **resume token** của một vị trí đã biết, thường dùng sau restart hoặc lỗi kết nối.
- **`startAfter`**: bắt đầu **stream mới** sau token, đặc biệt có thể dùng khi token cuối thuộc một event **`invalidate`**.
- **`startAtOperationTime`**: bắt đầu tại hoặc sau **BSON Timestamp**, khi chưa có resume token nhưng có operation time đáng tin cậy, hoặc có chủ đích backfill từ một thời điểm.

Ba lựa chọn này **loại trừ lẫn nhau**. Chúng không thay thế việc persist checkpoint, bảo đảm thứ tự xử lý và thiết kế idempotency ở hệ thống đích.

> **Nguyên tắc:** MongoDB quản lý vị trí đọc; ứng dụng chịu trách nhiệm chứng minh event đã được áp dụng tới sink trước khi checkpoint có thể tiến qua event đó.

---

## 2. Điều kiện để Change Streams hoạt động

| Điều kiện | Giải thích |
| --- | --- |
| Deployment là **replica set** hoặc **sharded cluster** | `mongod` standalone không hỗ trợ change streams vì thiếu oplog replica set cần thiết. |
| Storage engine và replication phù hợp | MongoDB tài liệu hóa WiredTiger và replication protocol version 1 (`pv1`) cho change streams. |
| Sharded cluster dùng **`mongos`** | Router tạo/ghép các luồng từ shards, không yêu cầu ứng dụng tự merge oplog. |
| Quyền truy cập đúng scope | Tài khoản cần quyền phù hợp để watch collection/database/deployment. |
| Oplog còn lịch sử | Muốn resume từ token/timestamp quá khứ phải còn những oplog entries cần thiết. |
| Driver đủ khả năng | Java Sync Driver cung cấp `watch()`, `ChangeStreamIterable`, resume options và cursor token. |
| Namespace được hỗ trợ | Các system collection, `admin`, `config`, `local`, time-series có hạn chế tương ứng. |

Change streams phát ra sự kiện của những thay đổi được majority-committed theo semantics của MongoDB. Không xem chúng là cơ chế nhận mọi thao tác vừa xảy ra trên primary nhưng có thể rollback.

### 2.1. Chọn scope

Trong `mongosh`:

```javascript
// Collection-level:
db.getSiblingDB("commerce").orders.watch();

// Database-level:
db.getSiblingDB("commerce").watch();

// Deployment-level, nhận từ các database được hỗ trợ:
db.getMongo().watch();
```

Trong Java:

```java
collection.watch();
database.watch();
mongoClient.watch();
```

Token gắn với ngữ cảnh change stream, vì vậy khi resume cần giữ **cùng scope, pipeline và options**. Không nên lấy token của collection watch để tự ý đổi sang deployment watch và nghĩ rằng vẫn cùng vị trí/semantics.

### 2.2. Kiến trúc sharded

```text
              Java Consumer
                    |
                    v
                 mongos
              /     |     \
             v      v      v
         Shard A Shard B Shard C
             \      |      /
              \     |     /
              merged change stream
```

`mongos` tạo các change streams tương ứng trên shards rồi sort/filter/merge. Shard removal có thể khiến stream đóng và không phải mọi trường hợp đều khôi phục hoàn toàn. Cần có runbook riêng cho thay đổi topology lớn.

---

## 3. Change event, `clusterTime` và resume token

Một event minh họa:

```javascript
{
  _id: { _data: "SERVER_GENERATED_OPAQUE_TOKEN" },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1794632400, i: 1 }),
  ns: { db: "commerce", coll: "orders" },
  documentKey: { _id: "O100" },
  fullDocument: {
    _id: "O100",
    status: "CREATED"
  }
}
```

Đây là **ví dụ cấu trúc**, không phải token có thể sử dụng thực tế.

- **`event._id`** là toàn bộ **resume token BSON document**.
- `operationType`: insert, update, replace, delete, drop, rename, invalidate và các loại khác theo version/options.
- `clusterTime`: **BSON Timestamp**, đại diện mốc logic của operation; không phải một `Date` tùy ý.
- `ns`: database/collection của event.
- `documentKey`: khóa định danh document nguồn.
- `fullDocument`: nội dung document theo event/options; với update mặc định không nhất thiết được cấp.

**Không nhầm `event._id` với `documentKey._id`.** Resume token là định danh vị trí sự kiện, không phải khóa bản ghi `orders`.

### 3.1. Token là opaque: giữ nguyên BSON

Không làm:

```javascript
// Sai: tự dựng token từ khóa nghiệp vụ hoặc đồng hồ.
const token = {
  _data: orderId + ":" + Date.now()
};
```

Không cắt chuỗi hex `_data`, sửa thứ tự field, biến token thành ID business hay tự thay `clusterTime` cho token.

Nên lưu:

```javascript
{
  _id: "orders-cdc-v1",
  token: event._id,
  lastOperationType: event.operationType,
  scope: "commerce.orders"
}
```

Cách này giữ nguyên token BSON do server cung cấp.

### 3.2. Event token và high-watermark token

MongoDB có hai loại token ở cấp khái niệm:

1. **Event token**: tương ứng một change event cụ thể.
2. **High-watermark token**: đại diện một điểm tiến triển trong stream, không cần gắn với event được trả về.

Ngoài `_id` của mỗi event, phản hồi `aggregate`/`getMore` có thể mang `cursor.postBatchResumeToken` (PBRT), kể cả khi batch **rỗng**. Java driver có thể cache vị trí này trong cursor.

Không phải stream yên lặng là không có token tiến triển. Tuy nhiên ở sharded cluster, high-watermark có thể tiến chậm vì một số shard ít phát sinh ghi.

---

## 4. Bảng so sánh ba phương thức

| Tiêu chí | `resumeAfter` | `startAfter` | `startAtOperationTime` |
| --- | --- | --- | --- |
| Nhận tham số | Resume token BSON | Resume token BSON | BSON Timestamp |
| Vị trí bắt đầu | **Sau** token đã cho | **Sau** token đã cho, mở stream mới | **Tại hoặc sau** logical timestamp |
| Trường hợp phổ biến | Restart khi đã có token | Tiếp tục sau `invalidate` | Bootstrap/backfill không có token |
| Sau `invalidate` | **Không hỗ trợ** | **Có thể** | Không thay thế chính xác invalidate token |
| Phân biệt events cùng timestamp | Có | Có | Không định vị riêng một event |
| Phụ thuộc oplog history | Có | Có | Có nếu thời điểm ở quá khứ |
| Có thể dùng cùng option khác? | Không | Không | Không |

Ví dụ cú pháp hợp lệ:

```javascript
orders.watch([], {
  resumeAfter: savedToken
});

orders.watch([], {
  startAfter: invalidateToken
});

orders.watch([], {
  startAtOperationTime: savedBsonTimestamp
});
```

Sai:

```javascript
// Ba lựa chọn mutually exclusive:
orders.watch([], {
  resumeAfter: savedToken,
  startAfter: invalidateToken
});
```

Dùng hai trong ba option cùng lúc khiến server báo lỗi, không phải một fallback tự động.

---

## 5. `resumeAfter` — đường khôi phục thông thường

`resumeAfter` nhận token của vị trí stream đã được consumer xử lý an toàn. MongoDB trả events **sau** vị trí đó.

```text
E1 ---- E2 ---- E3 ---- E4 ---- E5
         ^
         |
      token T2 đã checkpoint

watch({ resumeAfter: T2 })
=> E3, E4, E5, ...
```

Đây là lựa chọn ưu tiên khi consumer đã có token hợp lệ từ cùng subscription và cần tiếp tục từ checkpoint.

### 5.1. Ví dụ `mongosh`

```javascript
const orders = db.getSiblingDB("commerce").orders;
const cursor = orders.watch();

let savedToken;

// Ở terminal khác, hãy insert/update để tạo một event.
if (cursor.hasNext()) {
  const event = cursor.next();

  // Consumer thực tế phải xử lý event thành công trước.
  printjson(event);

  savedToken = event._id;
}

cursor.close();

if (savedToken) {
  const resumedCursor = orders.watch([], {
    resumeAfter: savedToken
  });

  // resumedCursor chờ các event sau vị trí savedToken.
}
```

Ví dụ lưu token trong biến chỉ minh họa method. Process restart sẽ mất biến này. Cần checkpoint vào storage bền vững.

### 5.2. Điều kiện quan trọng

- Token phải là token **được server cung cấp**, không tự tạo.
- Oplog phải còn đủ history.
- Stream mở lại cần dùng **cùng pipeline/options/scope** như lúc sinh token.
- **Không dùng `resumeAfter` sau `invalidate`**.

Nếu token đã hết hạn và history bị dọn, retry cùng lệnh nhiều lần không làm event cũ xuất hiện lại.

### 5.3. “Sau token” không chứng minh sink đã nhận event

MongoDB chỉ biết vị trí stream. Nếu ứng dụng persist T2 trước khi gửi E2 sang search index, rồi crash, restart sẽ bắt đầu ở E3 và sink **mất E2**. Đây là lỗi trong checkpoint protocol, không phải lỗi của `resumeAfter`.

---

## 6. `startAfter` — khôi phục luồng sau `invalidate`

Một **`invalidate` event** cho biết stream không còn hợp lệ ở scope đang theo dõi. Với collection-level stream, nó có thể xuất hiện sau drop, rename hoặc dropDatabase ảnh hưởng collection, làm cursor đóng.

Timeline:

```text
Collection commerce.orders:
E1 insert
E2 update
E3 drop collection
E4 invalidate         <-- stream đóng
      |
      +-- resumeAfter(T4) => không hợp lệ
      |
      +-- startAfter(T4)  => có thể mở stream mới
```

Sử dụng:

```javascript
const lastInvalidateToken = invalidateEvent._id;

const restarted = db.getSiblingDB("commerce")
  .orders.watch([], {
    startAfter: lastInvalidateToken
  });
```

`invalidateEvent` là event thật đã nhận từ stream. Không lấy token tự tạo hoặc token giả trong ví dụ để sử dụng.

### 6.1. `startAfter` không phục hồi collection

Nếu collection bị drop, `startAfter` chỉ định vị một stream **mới** sau invalidate. Nó không:

- Phục hồi dữ liệu đã xóa.
- Tái tạo index hoặc validation rules.
- Đảm bảo collection tái tạo cùng tên có cùng UUID/generation.
- Khôi phục search index/read model đã mất.
- Thay thế backup/PITR.

Do đó, sau một invalidate cần quyết định:

1. **Migration được chủ động phê duyệt?** Có thể mở lại stream, đánh dấu generation mới và rebuild nếu cần.
2. **Drop/rename ngoài dự kiến?** Kích hoạt incident response, không lặng lẽ tiếp tục.
3. **Database-level hay collection-level watch?** Xác định chính xác phạm vi invalidate.
4. **Oplog còn history?** Nếu token hết hạn, `startAfter` cũng không cứu được.

### 6.2. Token của drop khác token của invalidate

Trong một luồng có thể có event `drop` rồi `invalidate`. Dùng **token của `invalidate`** để mở sau invalidate và lưu `operationType` cùng checkpoint để phân biệt với event trước đó.

```javascript
{
  _id: "orders-indexer",
  token: { _data: "..." },
  lastOperationType: "invalidate",
  generation: 2
}
```

### 6.3. Scope quyết định lifecycle

| Scope | Tình huống gây kết thúc luồng |
| --- | --- |
| Collection | Drop/rename collection, dropDatabase liên quan. |
| Database | DropDatabase của database đang được theo dõi. |
| Deployment | Có behavior riêng; không tự suy từ collection-level stream. |

Không phải cứ drop một collection là mọi database/deployment-level change stream cũng đóng theo cùng cách. Cần hiểu scope ban đầu.

---

## 7. `startAtOperationTime` — mở từ mốc logic

Khác với hai phương thức nhận token, `startAtOperationTime` nhận **BSON Timestamp**:

```javascript
Timestamp({ t: 1794632400, i: 1 })
```

Trong đó `t` biểu diễn phần thời gian của timestamp, `i` là increment logic trong cùng đơn vị thời gian.

**BSON Timestamp không phải BSON Date.**

```javascript
// BSON Date: dùng nhiều trong document dữ liệu:
ISODate("2026-11-14T09:00:00Z")

// BSON Timestamp: dùng làm mốc change stream:
Timestamp({ t: 1794632400, i: 1 })
```

Cách sử dụng:

```javascript
// savedBsonTimestamp phải được lấy/lưu từ MongoDB,
// còn trong oplog nếu thuộc quá khứ.
const cursor = db.getSiblingDB("commerce")
  .orders.watch([], {
    startAtOperationTime: savedBsonTimestamp
  });
```

Sai:

```javascript
orders.watch([], {
  startAtOperationTime: new Date()
});
```

BSON Date từ `new Date()` không phải kiểu mà option này chấp nhận.

### 7.1. `startAtOperationTime` có thể đọc lại events cùng timestamp

Giả sử một transaction tạo:

```text
E1 update A      clusterTime=T, token=T1
E2 update B      clusterTime=T, token=T2
E3 insert audit  clusterTime=T, token=T3
```

Nếu consumer đã áp dụng E2 rồi restart bằng `startAtOperationTime: T`, có thể nhận lại E1/E2. Nếu có token T2, `resumeAfter: T2` phù hợp hơn vì định vị **sau đúng event**.

Theo MongoDB Change Streams Driver Specification, `startAtOperationTime` bắt đầu trả những thay đổi xảy ra **tại hoặc sau** Timestamp đã chỉ định. Không tự xem timestamp như event identity duy nhất.

### 7.2. Khi nào nên dùng?

- Lần đầu bootstrap khi chưa có resume token nhưng có operation time hợp lệ.
- Replay/backfill có chủ đích từ một mốc logic được ghi lại.
- Chuyển tiếp từ hệ CDC cũ chỉ lưu Timestamp, với dedup/reconciliation.
- Tạo điểm nối giữa snapshot và stream theo một giao thức đúng đắn.

### 7.3. Khi nào không nên dùng?

- Đã có resume token hợp lệ từ event: dùng `resumeAfter` chính xác hơn.
- Không biết time lấy từ đâu, chỉ có đồng hồ client: không bảo đảm no-gap.
- Timestamp đã quá xa, ngoài oplog window: không thể tái tạo events đã mất.
- Muốn bỏ qua một `invalidate` bằng cách đoán timestamp mới: cần xử lý lifecycle của collection trước.

---

## 8. Quy trình chọn phương thức khôi phục

```text
Consumer khởi động / mở lại stream
                 |
                 v
Có checkpoint token?
       |                     |
      Có                    Không
       |                     |
       v                     v
Token của invalidate?    Có BSON Timestamp đáng tin?
    |          |               |         |
   Không       Có             Có       Không
    |          |               |         |
    v          v               v         v
resumeAfter  startAfter  startAtOperationTime  Bootstrap có
    |          |               |             chính sách rõ
    +----------+---------------+
                  |
                  v
        Oplog còn đủ lịch sử?
             |         |
            Có        Không
             |         |
             v         v
        Xử lý tiếp   Rebuild/backfill/
        và checkpoint reconciliation
```

Trong production, thêm lớp kiểm tra `scope`, `pipelineVersion`, `optionsVersion`, ownership của worker và tính hợp lệ của checkpoint trước khi đi vào một nhánh.

---

## 9. Thực hành với `mongosh`: tạo event và resume

Bộ dữ liệu thử nghiệm trên replica set/sharded cluster:

```javascript
const lab = db.getSiblingDB("cdc_lab");

lab.orders.insertOne({
  _id: "O100",
  status: "CREATED",
  createdAt: new Date()
});
```

Ở terminal A:

```javascript
const orders = db.getSiblingDB("cdc_lab").orders;

const cursor = orders.watch([], {
  maxAwaitTimeMS: 1000
});

print("Change stream ready");
```

Ở terminal B:

```javascript
const orders = db.getSiblingDB("cdc_lab").orders;

orders.insertOne({
  _id: "O101",
  status: "CREATED"
});

orders.updateOne(
  { _id: "O101" },
  { $set: { status: "PAID" } }
);
```

Quay lại terminal A:

```javascript
const firstEvent = cursor.next();
printjson(firstEvent);

const savedToken = firstEvent._id;
printjson(savedToken);

cursor.close();

const resumed = orders.watch([], {
  resumeAfter: savedToken
});

// Event ngay sau firstEvent sẽ có thể được trả.
// resumed.next() có thể block nếu không có event mới.
```

**Lưu ý:** ví dụ yêu cầu MongoDB có change streams, không dùng standalone; collection và ID chỉ dành cho môi trường thử nghiệm. `next()` chờ event, do đó không nên chạy vô hạn trong script kiểm thử không có dữ liệu phát sinh.

---

## 10. Thiết kế checkpoint bền vững

Checkpoint nên được lưu bên ngoài memory của process:

```javascript
{
  _id: "commerce-orders-search-v3",
  resumeToken: { _data: "<opaque token từ server>" },
  resumeMode: "resumeAfter",
  scope: {
    type: "collection",
    database: "commerce",
    collection: "orders"
  },
  pipelineVersion: 3,
  optionsVersion: 2,
  lastOperationType: "update",
  lastClusterTime: Timestamp({ t: 1794632400, i: 2 }),
  checkpointedAt: ISODate("2026-11-14T10:00:00Z")
}
```

Đây chỉ là sơ đồ document checkpoint, chưa có token thật.

### 10.1. Vì sao cần version và scope?

- Nếu đổi từ `collection.watch()` sang `database.watch()`, token cũ không tự chứng minh tương thích.
- Nếu thêm/bớt `$match`, `fullDocument`, pre/post-images hoặc `showExpandedEvents`, semantics stream có thể thay đổi.
- Nếu cùng một checkpoint `_id` bị hai workers khác phiên bản sử dụng, worker cũ có thể ghi token không còn đúng với pipeline mới.
- Nếu collection đã drop/recreate, cần phân biệt thế hệ dữ liệu để không dùng checkpoint sai.

### 10.2. Chỉ lưu BSON nguyên vẹn

```javascript
const checkpoint = {
  _id: "orders-indexer",
  resumeToken: firstEvent._id,
  updatedAt: new Date()
};

db.getSiblingDB("cdc_state")
  .checkpoints.replaceOne(
    { _id: checkpoint._id },
    checkpoint,
    { upsert: true }
  );
```

Nếu checkpoint nằm ngoài MongoDB, serialize/deserialize bằng **BSON Extended JSON hoặc BSON codec** phù hợp, không tự chuyển nó thành một chuỗi `_data` không đủ thông tin kiểu.

### 10.3. Bảo vệ checkpoint

- Ghi bền vững với write concern phù hợp.
- Không cho ứng dụng khác tùy tiện sửa checkpoint.
- Theo dõi sự kiện xóa/reset checkpoint.
- Có ownership/lease/fencing khi chạy nhiều consumers cùng subscription.
- Không ghi đè checkpoint hợp lệ bằng null lúc cursor chưa có token.
- Không đánh đồng `updatedAt` mới với nguồn đã được catch up.

---

## 11. Lưu checkpoint trước/sau xử lý và tính đúng đắn

### 11.1. Nguy hiểm: checkpoint trước khi áp dụng event

```text
Receive E2
   |
   v
Persist T2
   |
   X crash trước khi apply E2
   |
   v
Restart resumeAfter(T2) => E3 trở đi
=> Sink mất E2
```

Đây là cách thiết kế có nguy cơ **bỏ sót event**.

### 11.2. An toàn hơn: xử lý xong rồi checkpoint

```text
Receive E2
   |
   v
Apply E2 thành công
   |
   X crash trước Persist T2
   |
   v
Restart resumeAfter(T1)
=> có thể apply E2 thêm lần nữa
```

Đường này hướng tới **at-least-once** ở tầng consumer, nhưng cần **idempotent sink**.

### 11.3. Không tự có exactly-once

Change stream resume token **không** tự bảo đảm exactly-once cho:

- Email.
- HTTP webhook.
- Search index.
- Kafka hoặc message broker khác.
- Counter thống kê cập nhật bằng `$inc` không có dedup.

Một event có thể được xử lý hai lần nếu consumer crash sau khi sink đã commit nhưng trước khi checkpoint được lưu.

### 11.4. Idempotent operation

Dùng `$set` một field sang cùng giá trị có thể idempotent:

```javascript
db.orderReadModels.updateOne(
  { _id: "O100" },
  { $set: { status: "PAID" } },
  { upsert: true }
);
```

Nhưng đây không phải lúc nào cũng đủ. Nếu event cũ được áp dụng sau event mới, nó có thể **ghi đè state mới**. Cần ordering/sequence/version fence.

Không idempotent:

```javascript
db.dashboard.updateOne(
  { _id: "paid-orders" },
  { $inc: { count: 1 } },
  { upsert: true }
);
```

Nếu event `PAID` chạy lại, counter tăng lần hai.

### 11.5. Cách thiết kế

- Dùng event identity hoặc business key ổn định.
- Ghi processed-event marker có unique constraint phù hợp.
- Apply state và marker **atomic** khi chúng ở cùng MongoDB transaction.
- Hoặc sử dụng sink-side idempotency, inbox/outbox và reconciliation.
- Không skip event đang lỗi rồi vẫn tiến checkpoint trừ khi policy ghi nhận đầy đủ về việc discard.

---

## 12. `postBatchResumeToken` và batch rỗng

Một change stream không cần liên tục có event. Phản hồi `getMore` có thể trả empty batch và `postBatchResumeToken`.

```text
10:00: event E1; token T1
10:01: empty batch; PBRT T_10:01
10:02: empty batch; PBRT T_10:02
```

High-watermark token đại diện một vị trí đã tiến qua, không cần gắn với event cụ thể.

### 12.1. Java driver giúp lấy token cache

```java
MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
    collection.watch().cursor();

ChangeStreamDocument<Document> event = cursor.tryNext();
BsonDocument token = cursor.getResumeToken();
```

`token` **có thể null ở giai đoạn ban đầu**. Sau khi consume events hoặc empty batches với PBRT, driver có thể cung cấp token phù hợp. Không chỉ nhớ token của event cuối và cho rằng stream không hề tiến khi dữ liệu đang yên lặng.

### 12.2. Không checkpoint vượt event chưa xử lý

```text
Batch: E1, E2, E3

Xử lý E1 thành công.
Xử lý E2 lỗi.
E3 chưa xử lý.

=> Không được checkpoint vị trí sau E3.
```

Nếu xử lý batch song song, phải theo dõi **contiguous completed offset**, không checkpoint dựa vào event hoàn thành nhanh nhất. Mẫu đơn luồng tuần tự giúp tránh một lớp phức tạp này.

### 12.3. Sharded cluster có thể làm high-watermark tiến chậm

Một shard idle ít ghi có thể khiến high-watermark cập nhật chậm. Không kết luận stream hỏng chỉ từ số giây token không đổi; kiểm tra thêm lượng dữ liệu nguồn, `getMore`, trạng thái shard, pool connections và lag của consumer.

---

## 13. Java Sync Driver: mở stream theo checkpoint

Các kiểu cần dùng:

```java
org.bson.BsonDocument;   // Resume token
org.bson.BsonTimestamp;  // Logical operation time
```

Ví dụ factory:

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoCollection;
import org.bson.BsonDocument;
import org.bson.BsonTimestamp;
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

public final class ChangeStreamFactory {

    public static ChangeStreamIterable<Document> open(
            MongoCollection<Document> collection,
            List<Bson> pipeline,
            BsonDocument token,
            boolean tokenIsInvalidate,
            BsonTimestamp operationTime
    ) {
        if (token != null && operationTime != null) {
            throw new IllegalArgumentException(
                "Choose token or operationTime, not both"
            );
        }

        ChangeStreamIterable<Document> stream =
            collection.watch(pipeline);

        if (token != null) {
            return tokenIsInvalidate
                ? stream.startAfter(token)
                : stream.resumeAfter(token);
        }

        if (operationTime != null) {
            return stream.startAtOperationTime(operationTime);
        }

        // Chỉ cho phép nếu đây là subscription mới và
        // khởi tạo từ hiện tại được nghiệp vụ chấp nhận.
        return stream;
    }
}
```

`tokenIsInvalidate` chỉ nên lấy từ metadata checkpoint thực sự đã ghi cùng event. Không suy ra từ tên collection hoặc lỗi connection.

### 13.1. Java BSON Timestamp

```java
import org.bson.BsonTimestamp;

// savedSeconds và savedIncrement phải là dữ liệu hợp lệ
// lấy từ MongoDB operation time đã được ghi bền vững.
BsonTimestamp at = new BsonTimestamp(
    savedSeconds,
    savedIncrement
);

ChangeStreamIterable<Document> stream =
    collection.watch().startAtOperationTime(at);
```

Không ép `java.util.Date` thành `BsonTimestamp` rồi tự giả định logical increment chuẩn. Nếu có token, resume theo token tốt hơn.

---

## 14. Java Sync Driver: vòng đọc, xử lý và checkpoint

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDocument;
import org.bson.Document;

public final class ChangeStreamWorker {

    public interface EventSink {
        // Bảo đảm xử lý lại không nhân đôi tác dụng phụ.
        void applyIdempotently(ChangeStreamDocument<Document> event);
    }

    public interface CheckpointStore {
        // Persist bền vững, không chỉ lưu trong RAM.
        void save(BsonDocument token);
    }

    public static void run(
            ChangeStreamIterable<Document> source,
            EventSink sink,
            CheckpointStore checkpoints
    ) {
        try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
                 source.cursor()) {

            while (!Thread.currentThread().isInterrupted()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event != null) {
                    // Không checkpoint nếu handler throw.
                    sink.applyIdempotently(event);

                    BsonDocument token = cursor.getResumeToken();
                    if (token == null) {
                        token = event.getResumeToken();
                    }

                    if (token != null) {
                        checkpoints.save(token);
                    }
                } else {
                    // Có thể đã nhận PBRT trong empty batch.
                    BsonDocument token = cursor.getResumeToken();

                    if (token != null) {
                        checkpoints.save(token);
                    }
                }
            }
        }
    }
}
```

Đây là **khung xử lý đơn luồng**, không phải consumer production hoàn chỉnh. Còn phải triển khai `EventSink`/`CheckpointStore`, retries có backoff, xử lý invalidate, signal shutdown, ownership fencing và telemetry.

**Điểm tích cực:** khi sink báo lỗi, code không tiến checkpoint qua event đó.

**Giới hạn:** nếu sink và checkpoint khác hệ thống, chúng không tự commit atomic. Crash đúng khoảng giữa hai lần ghi có thể gây replay; vì vậy sink phải idempotent.

### 14.1. `tryNext()` và `next()`

| Method | Đặc điểm |
| --- | --- |
| `cursor.next()` | Chờ change event; có thể block rất lâu. |
| `cursor.hasNext()` | Cũng có thể block trong lúc đợi events. |
| `cursor.tryNext()` | Chờ theo cơ chế getMore/timeout rồi trả event hoặc `null`. |
| `cursor.getResumeToken()` | Vị trí driver đã cache từ event hoặc PBRT nếu có. |
| `cursor.close()` | Giải phóng cursor/connection được dùng. |

Không tạo một cursor cho mỗi HTTP request nếu ứng dụng chỉ cần một subscriber. Change stream cursor giữ connection khi chờ `getMore`; số stream lớn so với connection pool có thể tạo latency.

### 14.2. Lưu BSON token từ Java

Khi lưu token vào MongoDB:

```java
BsonDocument token = cursor.getResumeToken();

if (token != null) {
    Document checkpoint = new Document(
        "_id", "orders-indexer"
    ).append(
        "resumeToken", token
    ).append(
        "checkpointedAt", new java.util.Date()
    );

    checkpointsCollection.replaceOne(
        new Document("_id", "orders-indexer"),
        checkpoint,
        new com.mongodb.client.model.ReplaceOptions()
            .upsert(true)
    );
}
```

Đoạn lưu phải nằm đúng vị trí sau handler, hoặc ở transaction cùng sink. Nếu `token == null` không được ghi checkpoint null làm mất vị trí hợp lệ cũ.

---

## 15. Recovery scenario A: service restart bình thường

```text
10:00  E1 processed -> checkpoint T1
10:01  E2 processed -> checkpoint T2
10:02  service crashes
10:03  E3, E4 arrive
10:04  service restarts
```

Các bước:

1. Load checkpoint `T2` từ storage bền vững.
2. Validate scope, pipeline/options version và quyền ownership.
3. Mở stream với `resumeAfter(T2)`.
4. Consumer xử lý E3, E4 và các event tiếp theo.
5. Persist token mới sau khi xử lý thành công.

Nếu crash sau khi xử lý E2 nhưng **trước khi** checkpoint T2, E2 có thể bị replay. Đây là tình huống bình thường của mô hình at-least-once; handler phải chịu được duplicate.

**Không dùng đồng hồ lúc restart để thay T2.** Có thể bỏ qua E3/E4.

---

## 16. Recovery scenario B: network lỗi hoặc primary election

Những sự cố tạm thời gồm:

- Network hiccup giữa consumer và MongoDB.
- `mongod`/`mongos` restart.
- Primary election hoặc node phục vụ cursor đổi role.
- Driver mất connection rồi chọn server khác theo read preference.
- Một số lỗi `getMore` được đánh dấu resumable.

MongoDB drivers tuân chuẩn có thể **tự thử resume sau lỗi resumable** bằng token đang cache trong memory. Theo đặc tả, một resumable error dẫn đến một lần thử resume; sau khi resume thành công, các lỗi tương tự xảy ra sau này vẫn có thể được xử lý theo quy tắc đó.

**Không phải mọi lỗi đều resumable.** Authentication/authorization, token không hợp lệ, thiếu oplog history, pipeline sai cú pháp hoặc lỗi handler ở sink cần xử lý riêng.

### 16.1. Driver resume không thay durable checkpoint

```text
Cùng process:
  driver có token trong memory -> có thể tự resume khi lỗi.

Process chết:
  memory mất -> ứng dụng cần checkpoint trên disk/DB.
```

### 16.2. Thay đổi read preference từ MongoDB 9.0

Tài liệu MongoDB ghi nhận từ **9.0**, nếu change stream mở với read preference `primary` hoặc `secondary`, election làm role của node đang phục vụ không còn đáp ứng preference, `getMore` có thể trả resumable error `InterruptedDueToReplStateChange` (code `11602`). Driver chuẩn có thể tự resume qua node thỏa preference.

Nếu dùng raw `getMore` hoặc tự implement protocol, phải xử lý theo tài liệu version cụ thể, không dựa vào danh sách lỗi tự đoán.

### 16.3. Backoff và error classification

Một outer retry loop phải:

- Nhận biết lỗi resumable/transient.
- Dùng exponential backoff/jitter và retry budget.
- Không reset token khi reconnect chưa thành công.
- Dừng retry bình thường nếu history lost hoặc invalidation cần quyết định nghiệp vụ.
- Alert nếu stream không tiến hoặc oplog window gần hết.

---

## 17. Recovery scenario C: collection drop/rename, `invalidate`

Ví dụ:

```javascript
// Ở môi trường test:
db.getSiblingDB("commerce")
  .orders.renameCollection("orders_archive");
```

Nếu collection-level watch bị invalidate:

1. Consumer nhận/ghi event `invalidate` và token của event đó.
2. Cursor đóng.
3. `resumeAfter(tokenInvalidate)` **không được**.
4. Có thể dùng `startAfter(tokenInvalidate)` để mở stream mới theo chính sách.
5. Nếu namespace thay đổi, cần điều chỉnh subscription/khởi tạo lại dữ liệu theo hợp đồng.
6. Nếu drop ngoài dự kiến, xem là incident cần khôi phục dữ liệu, không chỉ là thao tác restart.

**Chú ý:** event `rename` hoặc `drop` và event `invalidate` có thể có token khác nhau. Phải checkpoint đúng event và giữ metadata `lastOperationType`.

### 17.1. Recreate collection không tự phục hồi dữ liệu cũ

Một collection mới có thể có cùng tên nhưng UUID khác. Việc startAfter không làm những document đã drop quay trở lại. Hệ thống downstream có thể cần clear/rebuild projection cho generation mới.

---

## 18. Recovery scenario D: token cũ hơn oplog window

Giả sử:

```text
Oplog chỉ còn 2 giờ.
Consumer checkpoint lúc 08:00.
Service restart lúc 13:00.
```

Nếu token và operation mà nó cần đã bị dọn khỏi oplog, MongoDB không thể resume. Lỗi có thể mang tên/ý nghĩa **`ChangeStreamHistoryLost`** hoặc không tìm được resume token tùy phiên bản.

**Không thực hiện fallback im lặng:**

```text
resumeAfter(oldToken) lỗi
        |
        v
watch() không options tại 13:00
        |
        v
Toàn bộ events khi service ngừng bị bỏ qua.
```

### 18.1. Recovery đúng phải phụ thuộc downstream

| Downstream | Khả năng rebuild | Điều cần làm |
| --- | --- | --- |
| Search index của dữ liệu hiện tại | Thường có | Snapshot/reindex và cutover theo generation. |
| Cache | Thường có | Invalidate và nạp lại theo source-of-truth. |
| Read model thống kê | Tùy dữ liệu nguồn | Backfill/recompute/reconcile. |
| Audit mọi thay đổi lịch sử | Không chắc | Cần nguồn event log hoặc backup có lịch sử; state hiện tại không tái tạo đầy đủ transitions. |
| Webhook đã gửi | Tùy bên nhận | Reconcile/idempotency, kiểm tra replay từ outbox. |

### 18.2. Runbook khi history lost

1. **Giữ nguyên checkpoint cũ để điều tra.**
2. Ghi nhận sự cố, last applied event, token, timestamp, scope/pipeline version.
3. Xác định oplog window và khoảng có thể bị mất.
4. Quyết định rebuild/snapshot/backfill hoặc khôi phục từ nguồn log khác.
5. Chỉ cutover sang checkpoint mới sau khi dữ liệu downstream đã được đối soát.
6. Không đánh dấu consumer healthy chỉ vì stream mới đã mở được.

Đổi từ `resumeAfter` sang `startAfter` trên **cùng token hết hạn** không khôi phục lịch sử. `startAtOperationTime` cũng không thể đọc ngoài oplog window.

---

## 19. Recovery scenario E: chỉ có operation time

Một consumer cũ lưu BSON Timestamp chứ không lưu event token:

```javascript
{
  _id: "orders-consumer-old",
  lastOperationTime: Timestamp({ t: 1794632400, i: 1 })
}
```

Nếu timestamp còn trong oplog:

```javascript
const checkpoint = db.getSiblingDB("cdc_state")
  .checkpoints.findOne({ _id: "orders-consumer-old" });

const cursor = db.getSiblingDB("commerce")
  .orders.watch([], {
    startAtOperationTime: checkpoint.lastOperationTime
  });
```

Vì timestamp có thể dùng chung cho nhiều events, consumer phải **chấp nhận khả năng replay events đã xử lý**, kiểm tra idempotency và chạy reconciliation nếu cần.

Nếu chỉ có `new Date()` từ client, đó **không phải** một logical operation time đáng tin cậy để bảo đảm không bỏ sót. Hãy dùng token hoặc operation time từ MongoDB khi thiết kế checkpoint.

---

## 20. Recovery scenario F: thay pipeline/options sau deploy

Stream ban đầu:

```javascript
orders.watch([
  { $match: { operationType: "insert" } }
], {
  fullDocument: "default"
});
```

Code mới:

```javascript
orders.watch([
  {
    $match: {
      operationType: { $in: ["insert", "update"] }
    }
  }
], {
  fullDocument: "updateLookup",
  resumeAfter: oldToken
});
```

MongoDB cảnh báo **khi resume từ token phải giữ cùng pipeline và options**, nếu không có thể không resume được hoặc gây behavior không dự đoán được.

### 20.1. Version hóa subscription

```javascript
{
  _id: "orders-indexer",
  token: { _data: "..." },
  scope: "commerce.orders",
  pipelineVersion: 4,
  optionsVersion: 2
}
```

Khi deploy version mới, consumer phải so metadata rồi:

- Tiếp tục nếu cùng contract;
- Hoặc chạy migration/backfill và tạo checkpoint generation mới;
- Không vô điều kiện dùng token cũ rồi bỏ qua các operation type vừa mới thêm.

### 20.2. Không sửa/xóa `_id` của event

Sai:

```javascript
orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      documentKey: 1
    }
  }
]);
```

`_id` chính là resume token. MongoDB từ 4.2 sẽ throw exception nếu change stream pipeline sửa `_id`.

Đúng:

```javascript
orders.watch([
  {
    $project: {
      _id: 1,
      operationType: 1,
      documentKey: 1,
      clusterTime: 1
    }
  }
]);
```

Không nhầm `_id` của change event với `_id` trong `documentKey` của bản ghi nguồn.

---

## 21. Recovery scenario G: sharded cluster

Khi đọc change stream qua `mongos`:

- Router quản lý stream trên nhiều shards.
- Kết quả được merge/sort theo semantics của MongoDB.
- Mỗi event có opaque token riêng; không tự ghép `(shardId, clusterTime)`.
- PBRT có thể tiến theo high-watermark giữa các shards.
- Chunk migrations/shard removal có thể ảnh hưởng stream.
- Shard removal có thể đóng cursor và **không bảo đảm hoàn toàn resumable**.

### 21.1. Không đọc trực tiếp từng shard để thay router

```text
Không nên tự làm cho CDC toàn cluster:
  Consumer -> shard A trực tiếp
  Consumer -> shard B trực tiếp
  Consumer -> shard C trực tiếp
  Consumer tự sort theo clusterTime
```

Đây không tương đương stream qua `mongos`; metadata, ordering và chunk migrations làm tình huống phức tạp hơn.

### 21.2. Multiple events cùng `clusterTime`

Trong sharded cluster, nhiều events có thể có cùng logical timestamp. Dùng resume token **nguyên vẹn** thay vì timestamp để checkpoint chính xác. Nếu topology thay đổi lớn, kiểm chứng việc resume và chuẩn bị phương án backfill.

---

## 22. Recovery scenario H: sự kiện từ transaction nhiều document

Ví dụ transaction tạo:

```text
Txn #42:
  E1 update account A
  E2 update account B
  E3 insert transfer log
```

Các events cùng transaction có thể chia sẻ `clusterTime`, và một transaction lớn còn có thể tạo nhiều oplog entries.

```text
E1 clusterTime=T, token=T1
E2 clusterTime=T, token=T2
E3 clusterTime=T, token=T3
```

Nếu E2 đã được xử lý:

- `resumeAfter(T2)` định vị sau E2.
- `startAtOperationTime(T)` có thể phát lại E1/E2.

Không xem `clusterTime` duy nhất là **event identity**. Khi cần nhận diện transaction, có thể dùng các field như `lsid` và `txnNumber` khi hiện diện, nhưng chúng cũng không thay token của từng event.

**Change stream không tự làm sink bên ngoài MongoDB trở nên transactional.** Nếu consumer áp dụng các event này vào nhiều hệ ngoài, cần thiết kế transactional sink, ordering hoặc outbox/reconciliation.

---

## 23. `fullDocument: "updateLookup"` và dữ liệu lịch sử

Một stream mặc định có thể chỉ trả delta của update:

```javascript
{
  operationType: "update",
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Có thể yêu cầu lookup:

```javascript
orders.watch([], {
  fullDocument: "updateLookup"
});
```

Nhưng `updateLookup` tìm **bản document majority-committed hiện hành tại thời điểm lookup**; nó không nhất thiết là state chính xác ngay sau update lịch sử đang được replay.

Ví dụ:

```text
10:00 E1 status = PAID
10:01 E2 status = REFUNDED
13:00 Consumer resume từ trước E1
```

Khi xử lý E1 lúc 13:00, `fullDocument` có thể hiển thị `REFUNDED` hoặc null nếu document đã bị xóa. Nếu cần trạng thái đúng thời điểm E1, phải thiết kế với pre/post-images hoặc event store phù hợp.

### 23.1. Pre/post-images

MongoDB 6.0+ hỗ trợ pre/post-images khi collection được cấu hình đúng.

- `whenAvailable`: image có thể thiếu/null nếu không còn.
- `required`: stream có thể báo lỗi nếu image bắt buộc không tồn tại.
- **Oplog retention và pre/post-image retention khác nhau**; resume được event không đồng nghĩa image lịch sử còn có.

Không đổi `fullDocument`/`fullDocumentBeforeChange` tùy ý giữa lúc lấy token và lúc resume mà không đánh giá compatibility.

---

## 24. Bootstrap từ snapshot: tránh khoảng hở CDC

Một quy trình thường gặp:

```text
10:00 bắt đầu copy documents làm snapshot.
10:05 snapshot xong.
10:06 mở watch() không token, từ hiện tại.
```

Update lúc 10:03 có thể xuất hiện bất nhất trong snapshot và không có event được theo dõi sau khi watch mở. Vì vậy xuất hiện **snapshot-to-stream gap**.

### 24.1. Quy trình có điểm nối rõ ràng

```text
A. Thiết lập điểm bắt đầu stream (token/operation time).
B. Bắt đầu snapshot dữ liệu nguồn.
C. Theo dõi/buffer thay đổi từ A trong lúc snapshot chạy.
D. Áp dụng snapshot + events với thứ tự/version fencing.
E. Reconcile kết quả.
F. Cutover sang streaming liên tục.
```

Chỉ “mở stream trước snapshot” **chưa đủ** nếu event mới được apply rồi snapshot cũ ghi đè:

```text
E1 update status=PAID
Snapshot đọc status=PAID
E2 update status=REFUNDED
Sink apply E2
Snapshot ghi chậm status=PAID lên sink
=> sink quay ngược trạng thái
```

Cần generation/version, snapshot boundary, buffering hoặc đối soát. Với snapshot kéo dài, oplog retention phải đủ để giữ lịch sử từ điểm A tới lúc consumer catch up.

### 24.2. Không dùng `Instant.now()` của Java làm offset

Giờ client không thể thay một resume token hoặc logical operation time được server cấp nếu yêu cầu no-gap. Đồng hồ có thể lệch và một timestamp không phân biệt từng event cùng thời điểm.

---

## 25. Oplog window — giới hạn recovery

Oplog có retention hữu hạn và cửa sổ thực tế thay đổi theo tốc độ ghi.

```text
Timeline: 08:00 --- 09:00 --- 10:00 --- 11:00
Oplog:              [ oldest ........ newest ]
Checkpoint: 08:15
              |
              +--> token có thể đã nằm ngoài history
```

### 25.1. Kiểm tra oplog

Trên replica set với quyền phù hợp:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

Trong sharded cluster, xem các shard replica sets liên quan; không giả định cả cluster có một oplog window duy nhất.

### 25.2. Ước lượng retention

Đặt:

```text
R = oplog window nhỏ nhất có liên quan
L = consumer lag tối đa
O = outage/restart/recovery budget
M = safety margin
```

Mục tiêu vận hành:

```text
R > L + O + M
```

Đây là hướng capacity planning, không phải cam kết toán học tuyệt đối. Một write burst có thể làm cửa sổ oplog co lại. Cần đo **peak load**, không chỉ giá trị lúc hệ thống rảnh.

### 25.3. Cảnh báo sớm

- Last processed event clusterTime.
- Last checkpoint/persist time.
- High-watermark/token progress.
- Consumer backlog và sink latency.
- Oplog retention window theo shard.
- Error count, resume attempts, history-lost incidents.
- Availability của node và connection pool.

Đừng coi checkpoint document có `updatedAt` mới là bằng chứng stream đã bắt kịp; có thể ứng dụng chỉ ghi lại cùng một token cũ.

---

## 26. Lưu sink và checkpoint atomic khi có thể

Nếu downstream là một MongoDB collection **trong cùng deployment**, có thể tổ chức transaction:

```text
Receive E2
    |
    v
Begin transaction
    |
    +--> Check/deduplicate event identity
    |
    +--> Update read model
    |
    +--> Persist resume token T2
    |
    v
Commit
```

Khi cả sink state và checkpoint được commit cùng transaction, giảm nguy cơ “sink thành công nhưng checkpoint fail” hoặc ngược lại.

### 26.1. Pseudocode Java

```java
try (ClientSession session = client.startSession()) {
    session.withTransaction(() -> {

        // Implement có xử lý duplicate trong phạm vi transaction.
        applyEventToReadModel(session, event);

        checkpoints.updateOne(
            session,
            Filters.eq("_id", "orders-consumer"),
            Updates.set(
                "resumeToken",
                event.getResumeToken()
            ),
            new UpdateOptions().upsert(true)
        );

        return null;
    }, options);
}
```

Các tên `applyEventToReadModel`, `client`, `event`, `checkpoints`, `options` là thành phần của service thật, không phải sample độc lập có thể compile ngay. Code minh họa **vị trí atomic commit**; cần còn unique constraint, idempotency, retries, leadership fencing và validation.

### 26.2. Không đưa external side effect vào transaction callback

Callback `withTransaction` có thể chạy lại khi có transient errors. Không gửi email hoặc gọi HTTP API ở giữa callback rồi mặc định chỉ xảy ra một lần. Dùng transactional outbox hoặc sink-side idempotency.

### 26.3. Hai workers cùng subscription

Atomicity của một transaction không ngăn worker cũ ghi token T100 sau khi worker mới đã ghi T150. Cần lease/fencing epoch, version compare-and-set hoặc cơ chế đảm bảo chỉ một consumer nắm ownership.

---

## 27. Driver auto-resume không phải retry vĩnh viễn

Phân biệt trách nhiệm:

| Công việc | Chủ thể |
| --- | --- |
| Sinh event và resume token | MongoDB server. |
| Cache token và retry một số resumable errors | MongoDB driver theo spec. |
| Persist offset qua process restart | Ứng dụng. |
| Áp dụng event và deduplicate | Handler/sink. |
| Quản lý poison event | Consumer/DLQ theo policy. |
| Rebuild khi oplog hết lịch sử | Ứng dụng và vận hành. |
| Phục hồi collection bị drop | Backup/migration, không phải `startAfter`. |
| Kiểm tra pipeline/options changes | Quy trình deploy. |

Nếu một lỗi không phải resumable, reconnect vô hạn có thể làm vấn đề tệ hơn. Ví dụ:

- `Unauthorized`: sửa quyền.
- Pipeline `$project` làm mất `_id`: sửa pipeline.
- History lost: backfill/rebuild.
- Invalidate: xem lifecycle, có thể dùng `startAfter`.
- Sink error: không tiến checkpoint; retry event hoặc đưa DLQ có kiểm soát.
- Token từ server version mới đem sang server quá cũ: kiểm tra compatibility.

**Không reset checkpoint về null tự động** sau N lần retry chỉ để consumer “xanh lại”.

---

## 28. Token và compatibility khi upgrade/downgrade

Resume token có định dạng phụ thuộc MongoDB version và đôi khi FCV. Không viết parser business riêng cho token.

Trong upgrade plan:

1. Lưu checkpoint bền vững trước nâng cấp.
2. Kiểm tra driver tương thích với MongoDB server/FCV.
3. Giữ scope/pipeline/options khi resume.
4. Không mặc định server cũ hiểu token format mới nếu downgrade.
5. Kiểm thử trong staging với token sinh từ phiên bản nguồn và cursor mới.
6. Theo dõi thời gian restart, oplog window và catch-up.
7. Nếu đổi schema event/pipeline, chạy migration có checkpoint generation mới.

Token có thể được decode để chẩn đoán bằng công cụ chuyên dụng, nhưng **không dựa vào cấu trúc hex cố định** cho định tuyến hoặc dedup logic của ứng dụng.

---

## 29. Kiểm thử các tình huống khôi phục

Nên thực hiện trên staging/replica set thử nghiệm, không tự gây drop/failover production.

| Trường hợp | Thử như thế nào | Kết quả đúng |
| --- | --- | --- |
| Restart sau E2 | Persist T2, stop consumer, tạo E3/E4, restart | E3/E4 được xử lý nếu oplog còn history. |
| Crash sau sink, trước checkpoint | Ngắt process tại thời điểm đó | E2 có thể replay, sink không nhân đôi tác dụng. |
| Checkpoint trước sink | Mô phỏng một consumer code lỗi | Phát hiện mất event để sửa protocol. |
| Network disconnect | Ngắt kết nối trong môi trường test | Driver xử lý lỗi resumable nếu đủ điều kiện. |
| Primary election | Stepdown trong staging | Consumer có thể tiếp tục từ token. |
| Drop/rename | Gây invalidate hợp lệ trên collection test | Phân biệt `resumeAfter` và `startAfter`. |
| Oplog rollover | Consumer offline ngoài retention trên test | Báo lỗi, không tự reset từ now. |
| Empty batch | Không phát sinh writes | PBRT/cached token được quản lý an toàn. |
| Multi-document transaction | Commit nhiều updates trong một transaction | Cùng clusterTime không bị xem là một event. |
| Thay pipeline | Đổi filter/fullDocument | Version mismatch được nhận biết. |
| Change stream trên sharded cluster | Phát sinh writes ở nhiều shards | Dùng `mongos`, không tự merge oplog. |
| Sink timeout | Mô phỏng HTTP/indexing timeout | Không checkpoint trước khi biết xử lý hoàn tất. |
| Poison event | Event sai schema downstream | Có DLQ/retry policy, không skip lặng lẽ. |
| Duplicate worker | Hai instances cố cập nhật checkpoint | Có lease/fencing, token không ghi lùi. |
| Snapshot + CDC | Ghi liên tục trong snapshot | Không mất/gặp state reversal sau cutover. |
| Pre-image hết retention | Replay cũ với `required` | Lỗi được phát hiện và xử lý theo policy. |

### 29.1. Những bất biến cần kiểm tra

- Không bỏ sót event nằm trong lịch sử và nằm trong cam kết xử lý.
- Sink đạt đúng trạng thái sau replay/duplicates.
- Checkpoint không đi trước xử lý thành công.
- Không bỏ qua poison event một cách im lặng.
- Không coi `invalidate` tương đương lỗi network.
- Không reset token tự động khi history mất.
- Consumer không ghi lùi checkpoint vì tranh ownership.

---

## 30. Bài tập vận dụng

### Bài 1 — Consumer restart

Consumer xử lý E1, E2; checkpoint cuối là T2. Trong outage có E3 và E4.

**Hỏi:** Chọn option nào?

**Đáp án:** `resumeAfter: T2`, nếu scope/pipeline/options không đổi và oplog còn history.

### Bài 2 — Invalidate

Collection bị drop. Event cuối của collection-level stream là `invalidate` có token T_inv.

**Hỏi:** Có thể dùng `resumeAfter` không?

**Đáp án:** Không. Nếu nghiệp vụ cho phép bắt đầu stream mới, dùng `startAfter: T_inv`. Nó không phục hồi document đã drop.

### Bài 3 — Timestamp

Có một BSON Timestamp đã lưu từ MongoDB nhưng không có resume token.

**Hỏi:** Option nào và rủi ro gì?

**Đáp án:** `startAtOperationTime`, cần dedup vì nhiều events có thể cùng timestamp. History phải còn trong oplog.

### Bài 4 — Sai kiểu

```javascript
orders.watch([], {
  startAtOperationTime: ISODate("2026-11-14T09:00:00Z")
});
```

**Đáp án:** Sai, `startAtOperationTime` cần BSON Timestamp chứ không phải Date.

### Bài 5 — Crash sau checkpoint

Handler ghi token T2 trước khi update search index. Service crash.

**Hỏi:** Khi restart sẽ xảy ra gì?

**Đáp án:** `resumeAfter(T2)` bỏ qua E2, gây mất tác dụng của E2 ở sink. Sửa thứ tự xử lý.

### Bài 6 — Crash trước checkpoint

Sink đã cập nhật E2 nhưng chưa ghi T2 thì crash.

**Hỏi:** Cần tính chất gì?

**Đáp án:** Idempotency khi replay E2 từ checkpoint cũ.

### Bài 7 — History lost

Oplog retention 2 giờ, consumer tắt 6 giờ.

**Hỏi:** `startAfter(oldToken)` có cứu được không?

**Đáp án:** Không nếu token cần lịch sử đã hết. Phải backfill/rebuild/reconcile.

### Bài 8 — Transaction events

Ba event cùng `clusterTime` nhưng token khác.

**Hỏi:** Lưu `clusterTime` có tương đương lưu token của event thứ hai không?

**Đáp án:** Không; timestamp không định vị chính xác sau event thứ hai.

### Bài 9 — `$project` loại `_id`

```javascript
orders.watch([
  { $project: { _id: 0, operationType: 1 } }
]);
```

**Đáp án:** Không phù hợp; `_id` là resume token, server có thể từ chối pipeline thay đổi field này.

### Bài 10 — Đổi filter

Consumer cũ chỉ nhận insert, bản mới nhận cả update.

**Hỏi:** Có nên dùng token cũ luôn?

**Đáp án:** Không được giả định. Phải đánh giá pipeline mismatch, version hóa và migration/backfill nếu cần.

### Bài 11 — Idle stream

Không có event, nhưng `getMore` trả PBRT.

**Hỏi:** PBRT có ý nghĩa gì?

**Đáp án:** Là token high-watermark biểu diễn vị trí tiến triển; driver có thể cache để resume dù không có event mới.

### Bài 12 — `updateLookup`

Event E1 cập nhật status PAID, sau đó E2 cập nhật REFUNDED. Consumer replay E1 một giờ sau.

**Hỏi:** `fullDocument` của E1 chắc chắn là PAID không?

**Đáp án:** Không. `updateLookup` có thể đọc state mới hơn, hoặc null nếu document không còn.

### Bài 13 — Thay sharded router bằng manual merge

Team mở ba change streams trực tiếp tới ba shards rồi sort theo timestamp.

**Đáp án:** Không tương đương watch qua `mongos`, rủi ro routing/migration/ordering.

### Bài 14 — Gửi email

Consumer gửi email khi thấy order PAID, crash trước checkpoint.

**Hỏi:** Làm sao tránh gửi hai lần?

**Gợi ý:** Idempotency key, outbox/inbox hoặc durable delivery status; `resumeAfter` không giải quyết external side effect.

### Bài 15 — Bootstrap snapshot

Copy toàn bộ collection xong mới mở `watch()` từ hiện tại.

**Hỏi:** Rủi ro gì?

**Đáp án:** Có khoảng hở dữ liệu trong lúc snapshot. Cần điểm CDC trước/suốt snapshot và ordering/reconciliation.

### Bài 16 — Worker conflict

Worker A checkpoint T100, B checkpoint T150, A lại ghi T110.

**Hỏi:** Giải pháp?

**Đáp án:** Lease/fencing/compare-and-set hoặc phân vùng consumer rõ, ngăn checkpoint ghi lùi.

### Bài 17 — Pre-image

Token còn resume được nhưng pre-image đã hết retention.

**Hỏi:** `required` còn luôn hoạt động?

**Đáp án:** Không. Image retention là giới hạn riêng; stream có thể báo lỗi nếu image bắt buộc không còn.

### Bài 18 — Poison event

Một event hợp lệ nhưng payload không được sink chấp nhận.

**Hỏi:** Có nên ghi checkpoint rồi bỏ qua để stream tiếp tục?

**Gợi ý:** Không lặng lẽ bỏ qua. Cần chính sách retry/DLQ, quyết định an toàn về thời điểm checkpoint và dấu vết lỗi.

---

## 31. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Mở `watch()` sau restart tự nhận lại events cũ.” | Không; cần resume token hoặc operation time. |
| “`resumeAfter` dùng được sau `invalidate`.” | Không; dùng `startAfter` khi được phép. |
| “`startAfter` tự phục hồi collection.” | Không; chỉ định vị stream sau event. |
| “`startAfter` cứu được token đã rơi khỏi oplog.” | Không; vẫn cần lịch sử. |
| “`startAtOperationTime` nhận `Date`.” | Cần BSON Timestamp. |
| “Một `clusterTime` chỉ có một event.” | Nhiều events có thể cùng timestamp. |
| “Token là `_id` của document nguồn.” | Là `_id` của **change event**. |
| “Có thể tự ghép `_data` từ ID.” | Không; token do MongoDB sinh. |
| “Token dùng mãi mãi.” | Phải có oplog history tương ứng. |
| “Driver auto-resume nên không cần checkpoint.” | Driver memory không sống qua process restart. |
| “Driver retry tất cả lỗi vô hạn.” | Chỉ một số lỗi resumable, theo spec. |
| “Checkpoint càng sớm càng tốt.” | Ghi trước sink hoàn tất có thể mất event. |
| “Lưu sau sink là exactly-once.” | Có thể replay; cần idempotency/atomicity. |
| “Không có event thì token không bao giờ tiến.” | PBRT có thể tiến khi empty batches. |
| “Có thể xóa `_id` bằng `$project` cho nhẹ.” | Không; `_id` là resume token. |
| “Đổi pipeline và dùng token cũ luôn an toàn.” | MongoDB cảnh báo có thể sai hoặc không resume. |
| “`updateLookup` là post-image lịch sử chính xác.” | Có thể là state mới hơn hoặc null. |
| “Oplog còn thì pre-image chắc còn.” | Pre/post-image retention có giới hạn riêng. |
| “Sharded cluster có một oplog chung.” | Mỗi shard có lịch sử và tình trạng khác nhau. |
| “Sort `clusterTime` là đủ để merge CDC của shards.” | Nên dùng `mongos`/change stream contract. |
| “Lỗi history lost thì mở từ now là bình thường.” | Có thể mất dữ liệu, phải xử lý rõ. |
| “MongoDB transaction bao gồm email/HTTP.” | Không; external sink cần idempotency. |
| “Có hai workers thì checkpoint vẫn an toàn.” | Có thể ghi lùi nếu không fencing. |
| “Cursor có thể mở vô hạn không tốn tài nguyên.” | Mỗi stream/getMore chiếm connection và tài nguyên. |
| “`invalidate` luôn là sự cố máy chủ.” | Có thể do drop/rename hợp lệ; xét scope. |

---

## 32. Checklist production

1. Deployment hỗ trợ change streams, không phải standalone.
2. Đối với sharded cluster, kết nối qua `mongos`.
3. Chọn đúng scope collection/database/deployment.
4. Giữ `_id` change event nguyên vẹn trong pipeline.
5. Phiên bản hóa pipeline và options của subscription.
6. Lưu resume token BSON nguyên vẹn vào checkpoint bền vững.
7. Chỉ tiến checkpoint sau khi sink xử lý thành công.
8. Có idempotent handler hoặc atomic sink+checkpoint.
9. Có cơ chế lease/fencing nếu nhiều consumers chia sẻ checkpoint.
10. Biết token nào là của `invalidate`.
11. `resumeAfter` dùng cho event/token thông thường.
12. `startAfter` dùng sau invalidate theo chính sách.
13. `startAtOperationTime` chỉ nhận BSON Timestamp và có dedup.
14. Oplog window lớn hơn lag, outage budget và safety margin.
15. Không reset checkpoint âm thầm khi history lost.
16. Có quy trình rebuild/backfill và reconciliation.
17. Theo dõi PBRT/high-watermark trên stream idle.
18. Cấu hình retries/backoff, phân loại fatal và transient errors.
19. Giám sát sink failures, poison events và DLQ.
20. Hiểu `fullDocument` updateLookup và pre/post-image retention.
21. Thiết kế bootstrap tránh khoảng hở snapshot/CDC.
22. Có kiểm thử restart, crash, election, invalidate và oplog rollover.
23. Có kế hoạch migration khi đổi server/driver/FCV/pipeline.
24. Giám sát connection pool và số lượng active change streams.
25. Đảm bảo khôi phục tuân thủ yêu cầu bảo mật, audit và SLA.

Sơ đồ:

```text
MongoDB majority-committed changes
                 |
                 v
         Change stream cursor
          | event hoặc PBRT
          v
       Consumer handler
          |
          v
  Apply idempotently to sink
          |
          v
  Persist durable resume token
          |
          +-- restart ---> load token ---> resumeAfter
          |
          +-- invalidate ---> decide lifecycle ---> startAfter
          |
          +-- no token, known timestamp ---> startAtOperationTime
          |
          +-- history lost ---> rebuild/reconcile, not silent reset
```

---

## 33. Tài liệu MongoDB chính thức

- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changestreams/): availability, scopes, resume tokens, high-watermark, sharded considerations.
- [`$changeStream` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/): cấu trúc và các tùy chọn điểm bắt đầu.
- [`db.collection.watch()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/): watch collection, resume với token.
- [`db.watch()`](https://www.mongodb.com/docs/manual/reference/method/db.watch/): database-level change stream.
- [`Mongo.watch()`](https://www.mongodb.com/docs/manual/reference/method/mongo.watch/): deployment-level change stream.
- [Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/): định dạng change event.
- [`invalidate` change event](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/): drop/rename/dropDatabase và kết thúc stream.
- [Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/): `watch`, `ChangeStreamIterable`, cursor và fullDocument.
- [Change Streams Driver Specification](https://specifications.readthedocs.io/en/latest/change-streams/change-streams/): semantics BSON Timestamp, driver retry, PBRT.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): retention và oplog window.
- [Remove Shards from a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/remove-shards-from-cluster/): giới hạn khả năng resume khi thay đổi topology.

Khi triển khai, đối chiếu **MongoDB server version, FCV, Java Driver version và deployment topology**. Một số chi tiết về error codes, read preference, token format và expanded events có thể thay đổi theo phiên bản.

## 34. Kết luận

- **`resumeAfter`** là lựa chọn chính cho consumer restart sau event đã xử lý: sử dụng **token BSON bền vững** và đúng scope/pipeline/options.
- **`startAfter`** có điểm khác biệt quyết định: có thể mở **stream mới sau `invalidate`**, nhưng không khôi phục collection đã drop hoặc lịch sử đã mất.
- **`startAtOperationTime`** dùng **BSON Timestamp** để bắt đầu ở mốc logic khi chưa có token hoặc cần backfill; không định vị chính xác một event như resume token.

Cả ba cách đều bị giới hạn bởi **lịch sử oplog còn khả dụng**. Khi history lost, phải backfill/rebuild/reconcile, không được im lặng bắt đầu từ hiện tại.

Khả năng khôi phục end-to-end phụ thuộc **checkpoint sau xử lý, idempotency, ownership fencing, xử lý invalidate, giám sát oplog và một quy trình phục hồi đã được kiểm thử**, chứ không chỉ phương thức `watch()` được gọi.

**Resume token trả lời “đọc tiếp ở đâu”; thiết kế consumer quyết định “có áp dụng đủ và đúng từng thay đổi hay không”.**
