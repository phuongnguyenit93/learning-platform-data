# Tích hợp change stream, resume token và dừng ứng dụng có kiểm soát với MongoDB Java Driver

> **Module:** Database Engine Document MongoDB  
> **Chương:** Java Driver  
> **Bài học:** Tích hợp change stream, resume token và dừng ứng dụng có kiểm soát

## 1. Bài toán mở đầu: một sự kiện được xử lý hai lần hoặc bị bỏ sót

Một dịch vụ Java nhận đơn hàng trong collection `orders`. Mỗi khi trạng thái đơn chuyển sang `PAID`, hệ thống cần:

- cập nhật một bảng đọc `order_read_model`;
- gửi tác vụ đồng bộ sang công cụ báo cáo;
- giữ tiến độ đã đọc để sau khi deploy/restart có thể tiếp tục;
- dừng gọn khi Kubernetes gửi tín hiệu kết thúc pod.

Nhóm phát triển viết:

```java
collection.watch().forEach(change -> {
    publishToAnotherSystem(change);
});
```

Đoạn code có thể nhận thay đổi khi ứng dụng chạy, nhưng chưa trả lời được bốn câu hỏi vận hành:

1. Nếu xử lý xong thay đổi nhưng ứng dụng **chết trước khi lưu tiến độ**, sự kiện có bị xử lý lại không?
2. Nếu lưu tiến độ **trước khi** gọi hệ thống ngoài rồi bị crash, sự kiện có thể bị bỏ qua vĩnh viễn không?
3. Nếu ứng dụng được SIGTERM trong lúc `next()` đang chờ sự kiện, làm sao thoát và đóng MongoDB cursor mà không mất những công việc đang xử lý?
4. Nếu pod ngừng vài ngày và oplog đã cuốn qua điểm resume, có thể tự mở stream “từ bây giờ” mà không tạo lỗ hổng dữ liệu không?

Công cụ giải quyết những câu hỏi này là **MongoDB Change Streams + Java Driver + durable checkpoint + idempotent processing + graceful shutdown**. Một hệ thống chạy tốt cần cả năm, không chỉ lệnh `watch()`.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích change stream dựa trên oplog và phạm vi theo collection/database/deployment.
2. Mở change stream qua Java Sync Driver và sử dụng `MongoChangeStreamCursor`.
3. Phân biệt `tryNext()`, `next()`, `hasNext()`, timeout chờ và tài nguyên cursor.
4. Đọc event `insert/update/replace/delete/invalidate`, `documentKey`, `updateDescription` và `fullDocument`.
5. Hiểu resume token `_id` và `postBatchResumeToken`, không tự chế hoặc thay đổi token.
6. Phân biệt `resumeAfter()`, `startAfter()` và `startAtOperationTime()`.
7. Thiết kế checkpoint lưu **sau khi xử lý** để hướng tới **at-least-once**, kết hợp idempotency để chịu được xử lý lặp.
8. Phân biệt sự cố có thể resume với token đã hết lịch sử, collection bị invalidate hoặc pipeline thay đổi.
9. Xây vòng lặp Java có cờ dừng, bounded polling, `try-with-resources` và shutdown hook.
10. Tổ chức consumer một hoặc nhiều instance với lease/fencing/partitioning.
11. Thiết lập metrics/alerting, runbook và bài lab an toàn trên replica set test.

## 2. Change stream trong kiến trúc ứng dụng

Change stream cho phép ứng dụng theo dõi các thay đổi được MongoDB công bố qua một API dựa trên aggregation. So với việc tự tail collection `local.oplog.rs`, change stream có API event, resume token và cơ chế driver tự tiếp tục khi lỗi tạm thời.

```text
            Application writes
                  |
                  v
            MongoDB replica set
                  |
       Majority-committed changes
                  |
                  v
              Oplog history
                  |
            $changeStream
                  |
                  v
        Java Driver / watch()
                  |
          +-------+---------+
          |                 |
          v                 v
    Business handler    Durable checkpoint
    / idempotent sink    / resume token
          |                 |
          +-------+---------+
                  |
                  v
      External/read-model consumers
```

Change stream là **event feed trên các database changes**, không phải một message queue bảo đảm giữ mọi sự kiện vô thời hạn. Khả năng tiếp tục phụ thuộc lịch sử oplog còn sẵn, pipeline/options đúng và trạng thái namespace.

### 2.1. Điều kiện triển khai

Theo tài liệu MongoDB, change streams cần:

- **Replica set hoặc sharded cluster**, không hỗ trợ standalone `mongod`.
- Storage engine/topology tương thích; triển khai phổ biến sử dụng WiredTiger.
- Quyền database phù hợp để mở change stream và đọc dữ liệu liên quan.
- Java MongoDB Driver tương thích với server version.
- Kết nối qua `mongos` đối với sharded cluster, hoặc URI replica set phù hợp.
- Oplog history đủ để consumer dừng/restart mà vẫn tìm được điểm resume.

Trên development machine chỉ có standalone MongoDB, bạn có thể chạy **single-node replica set** ở môi trường test theo tài liệu chính thức. Không tự chạy `rs.initiate()` trên deployment người khác đang sử dụng.

### 2.2. Phạm vi của `watch()`

Java Sync Driver cung cấp:

```java
// Một collection:
MongoCollection<Document> orders =
        database.getCollection("orders");
orders.watch();

// Mọi collection phù hợp trong một database:
database.watch();

// Các namespace thuộc một deployment theo quyền:
mongoClient.watch();
```

| API | Phạm vi | Lưu ý |
| --- | --- | --- |
| `MongoCollection.watch()` | Một collection | Dễ giới hạn nghiệp vụ, tránh nhận nhiều event không liên quan |
| `MongoDatabase.watch()` | Nhiều collection trong database | Dễ sinh fan-out; xử lý namespace, type riêng |
| `MongoClient.watch()` | Deployment | Cần quyền/phạm vi cao, nhiều event và chi phí |
| Thêm aggregation pipeline | Lọc/biến đổi event | Không được làm mất/thay `_id` là resume token |

Với worker chỉ theo dõi đơn hàng, thường bắt đầu từ `collection.watch()` thay vì `client.watch()` chỉ để đỡ viết filter.

### 2.3. Tại sao không thay hoàn toàn message broker?

| Tiêu chí | MongoDB change stream | Broker/queue chuyên dụng |
| --- | --- | --- |
| Nguồn sự kiện | Thay đổi database | Message do producer publish |
| Lưu vết | Oplog có cửa sổ lịch sử hữu hạn | Theo retention/partition cấu hình broker |
| Cursor/offset | Resume token | Offset/ack/cursor tùy broker |
| Replay dài hạn | Phụ thuộc oplog, recovery riêng | Phụ thuộc retention và mô hình queue |
| Business intent | Cần suy ra từ database change | Có thể là domain event rõ ràng |
| Fan-out nhiều consumers | Mỗi stream có chi phí | Thiết kế consumer groups tùy broker |
| Exactly-once external side effects | Không tự bảo đảm | Cũng cần xét transaction/idempotency |
| Độ phức tạp hạ tầng | Dùng sẵn MongoDB | Thêm thành phần nhưng có khả năng queue chuyên biệt |

Change stream phù hợp để **đồng bộ projections, cache invalidation, audit pipelines, CDC và outbox relay**, nhưng không được xem là hàng đợi vĩnh viễn cho các tác vụ không thể mất nếu chưa có recovery plan.

## 3. Java Driver: các API quan trọng

### 3.1. Dependency

Với Java Sync Driver, dependency chính:

```xml
<!-- pom.xml: thay VERSION_DA_KIEM_TRA bằng bản tương thích -->
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>VERSION_DA_KIEM_TRA</version>
</dependency>
```

Hoặc trong Gradle:

```kotlin
dependencies {
    implementation("org.mongodb:mongodb-driver-sync:VERSION_DA_KIEM_TRA")
}
```

Không chép một số version ngẫu nhiên vào production. Cần đối chiếu Java runtime, Spring Boot/BOM, MongoDB Server/FCV và Java Driver compatibility matrix.

Ví dụ ở bài dùng **Java 17** và API phổ biến trong dòng MongoDB Java Sync Driver 5.x; với driver khác, kiểm Javadocs của đúng bản.

### 3.2. Import mẫu

```java
import com.mongodb.MongoException;
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;

import org.bson.BsonDocument;
import org.bson.Document;

import java.util.List;
import java.util.concurrent.TimeUnit;
```

Driver có Sync, Reactive Streams và có thể được Spring Data MongoDB bọc thành abstraction khác. Ví dụ `MongoChangeStreamCursor` là **Sync Driver**, không phải API Reactive `Publisher`; đừng trộn hai cách quản lý lifecycle.

### 3.3. Mở stream đơn giản

```java
String uri = System.getenv("MONGODB_URI");

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database =
            client.getDatabase("mongo_change_row395_lab");

    MongoCollection<Document> source =
            database.getCollection("events");

    try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                 cursor = source.watch()
                     .maxAwaitTime(1, TimeUnit.SECONDS)
                     .cursor()) {

        while (true) {
            ChangeStreamDocument<Document> event =
                    cursor.tryNext();

            if (event != null) {
                System.out.println(event.getOperationType());
            }
        }
    }
}
```

Đây chỉ là đoạn minh họa API: vòng lặp `while(true)` **không có điều kiện dừng** và không đủ cho production. Một worker thật cần cờ stop, checkpoint và xử lý lỗi như các phần sau.

## 4. `next()`, `hasNext()`, `tryNext()` và thread bị chặn

### 4.1. Khác biệt chính

| Phương thức | Hành vi ở change stream |
| --- | --- |
| `next()` | Chờ và trả một event mới, có thể block trong thời gian dài |
| `hasNext()` | Thường chờ tới khi có event/stream kết thúc, không phù hợp poll shutdown nhanh |
| `tryNext()` | Trả event đang sẵn có hoặc `null` khi hiện tại chưa có event sau lượt lấy batch |
| `cursor.close()` | Giải phóng tài nguyên cursor/server cursor theo API |
| `watch().maxAwaitTime(...)` | Giới hạn thời gian server chờ event trong một `getMore` trước khi trả batch rỗng |

**`tryNext()` không có nghĩa mọi trường hợp đều non-blocking ở mức socket.** Nó có thể cần network round-trip và chờ server trong giới hạn `maxAwaitTime`, cộng thời gian mạng, server selection và driver timeouts.

### 4.2. Vì sao không dùng `forEach` trực tiếp trên main thread?

```java
database.watch().forEach(event -> {
    // Chạy vô thời hạn nếu stream còn mở.
    // Main thread sẽ không tự đi tới đoạn shutdown.
});
```

Trong ứng dụng HTTP, nên chạy consumer ở một **worker thread** hoặc managed service component. Đừng block startup thread hay request thread bằng vòng `forEach` vô hạn.

### 4.3. Bounded polling cho graceful shutdown

```java
AtomicBoolean stopping = new AtomicBoolean(false);

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
         cursor = collection.watch()
                 .maxAwaitTime(1, TimeUnit.SECONDS)
                 .cursor()) {

    while (!stopping.get()) {
        ChangeStreamDocument<Document> event =
                cursor.tryNext();

        if (event == null) {
            continue;  // quay lại kiểm tra stop flag
        }

        handleAndCheckpoint(event);
    }
}
```

`maxAwaitTime(1, SECONDS)` giúp kiểm tra stop định kỳ trong điều kiện bình thường. Nhưng nó **không bảo đảm** toàn bộ lần gọi Java kết thúc sau đúng 1 giây nếu network/server có sự cố. Dùng driver timeouts và shutdown deadline riêng.

## 5. Đọc một change event đúng cách

### 5.1. Hình dạng change event

Một change event khái quát:

```javascript
{
  _id: { _data: "826..." },      // Resume token
  operationType: "update",
  clusterTime: Timestamp({t: 1794630000, i: 1}),
  ns: {
    db: "mongo_change_row395_lab",
    coll: "orders"
  },
  documentKey: { _id: ObjectId("...") },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Thông tin thực phụ thuộc version và operation:

- `_id` ở cấp **change event** chính là resume token, **không phải document `_id`**.
- `documentKey` xác định document được tác động; trong sharded collection có thể chứa shard key.
- `operationType` cho biết loại thay đổi.
- `clusterTime` gắn với thời điểm logic của operation; không dùng nó thay resume token.
- `fullDocument` có thể có hoặc không tùy loại event và lựa chọn driver.
- `updateDescription` mô tả delta của update.
- Các field `lsid`/`txnNumber` có thể hữu ích khi phân tích transaction, không phải event identity đơn giản.

### 5.2. Đọc event bằng Java

```java
ChangeStreamDocument<Document> change = cursor.tryNext();

if (change != null) {
    BsonDocument resumeToken = change.getResumeToken();
    BsonDocument documentKey = change.getDocumentKey();

    System.out.println("op=" + change.getOperationType());
    System.out.println("ns=" + change.getNamespace());

    // Không ghi toàn bộ token hoặc fullDocument nhạy cảm
    // ra logs production.
}
```

### 5.3. Insert, replace, update và delete

| Operation | Dữ liệu thường có | Điều cần chú ý |
| --- | --- | --- |
| `insert` | `fullDocument` chứa document mới | Có thể dùng cho projection, vẫn xét idempotency |
| `replace` | `fullDocument` thay thế | Có thể thay nhiều fields |
| `update` | `updateDescription` delta; `fullDocument` tùy option | `updateLookup` không phải snapshot bất biến tại thời điểm event |
| `delete` | `documentKey`, không còn document để lookup | Không trông chờ `fullDocument` |
| `invalidate` | Token sự kiện invalidate | Cursor đóng; có semantics resume khác |

Các event như `drop`, `rename` và những event mở rộng theo version/scope có thể xuất hiện. Worker không nên giả định mọi event đều có `fullDocument`.

### 5.4. `FullDocument.UPDATE_LOOKUP`

```java
ChangeStreamIterable<Document> stream =
        collection.watch()
            .fullDocument(FullDocument.UPDATE_LOOKUP);
```

Với update, driver yêu cầu server lookup **document hiện tại** khi event được xử lý. Nếu document đã bị update tiếp hoặc xóa trước thời điểm lookup, `fullDocument` có thể khác state **ngay khi update event phát sinh**, hoặc không còn.

Ví dụ:

```text
T1: update status -> PAID
T2: update status -> CANCELLED
T3: change stream xử lý event T1, updateLookup
    -> fullDocument có thể đã là CANCELLED
```

Nếu business logic cần chính xác delta của event, hãy dùng `updateDescription` hoặc một domain event/outbox có version/snapshot trong transaction.

### 5.5. Pre-image/post-image

MongoDB 6.0+ hỗ trợ pre/post-images khi collection được cấu hình phù hợp và retention còn dữ liệu.

Java API có thể dùng:

```java
collection.watch()
    .fullDocumentBeforeChange(
        FullDocumentBeforeChange.WHEN_AVAILABLE
    );
```

Không bật `REQUIRED` rồi coi như chắc chắn mọi old event đều có pre-image. Images có retention policy riêng; nếu đã hết hoặc chưa được bật lúc ghi, lookup có thể fail.

Đây là khả năng tùy version; trên high-throughput collection, pre-images tăng storage và nên được đánh giá bảo mật/chi phí.

## 6. Resume token: đơn vị checkpoint thực sự

### 6.1. Resume token không phải document ID hay timestamp đơn giản

MongoDB tạo một BSON document trong `event._id`:

```javascript
{
  "_data": "826..."
}
```

Một token có thể có cấu trúc/format khác theo server version; **coi nó là opaque BSON document**.

Không tự:

- tách chuỗi `_data` rồi đoán thứ tự;
- đổi token thành timestamp;
- tạo token từ `documentKey._id`;
- chỉnh sửa các field bên trong token;
- thay `_id` của event bằng `$project`/`$replaceRoot` trong pipeline;
- so token lexicographically để tự xác định event mới hơn.

Java:

```java
BsonDocument token = change.getResumeToken();
```

Token này đánh dấu **vị trí event** để sau restart xin các event **sau** event đó.

### 6.2. Vì sao phải giữ nguyên BSON?

Ví dụ checkpoint trong MongoDB:

```javascript
{
  _id: "orders-consumer-v1",
  token: {
    _data: "826..."
  },
  pipelineVersion: "orders-v1",
  updatedAt: ISODate("2026-11-14T04:25:00Z")
}
```

Ưu tiên lưu token dưới dạng BSON ở collection checkpoint. Khi đưa qua JSON/file/config, phải dùng **Extended JSON** và kiểm tra round-trip, không chuyển BSON thành string không thể đọc lại.

Resume token có thể chứa dữ liệu giao thức/metadata, không nên phơi trong logs công khai.

### 6.3. `postBatchResumeToken` và highwatermark

Ngoài event token, MongoDB có thể trả `postBatchResumeToken` trong `aggregate`/`getMore` response. Đây có thể là **highwatermark token**, đại diện tiến độ thời gian của stream dù batch không chứa event.

Java Sync Driver cung cấp:

```java
BsonDocument lastKnownToken = cursor.getResumeToken();
```

Theo Javadocs, `getResumeToken()` có thể trả:

- token của event gần nhất đã được cursor trả;
- hoặc `postBatchResumeToken` sau khi client đã duyệt hết batch;
- hoặc `null` trước khi có token/stream đã đóng.

**Cảnh báo quan trọng:** token của cursor là **vị trí đọc từ MongoDB**, không nhất thiết là **vị trí side effect đã hoàn tất**. Nếu xử lý events bất đồng bộ/hàng đợi chưa drain, đừng lưu `cursor.getResumeToken()` làm checkpoint khi chưa biết tất cả events trước token đã được xử lý.

### 6.4. Checkpoint trên batch rỗng

Một consumer sync xử lý từng event và không có work còn pending có thể tối ưu tiến độ bằng highwatermark token từ `getResumeToken()` sau batch rỗng. Tuy nhiên trước khi persist phải đảm bảo:

1. Không có event đã deliver nhưng chưa xử lý.
2. Không có side effect đang thực hiện hoặc queued.
3. Không có retry/replay đang chờ.
4. Token tương thích pipeline/options hiện hành.
5. Cùng một consumer có quyền độc quyền ghi checkpoint.

Trong ví dụ nền tảng của bài, dùng **event.getResumeToken() sau khi xử lý thành công** cho đơn giản và an toàn. Khi stream idle kéo dài, không có event mới thì checkpoint không tiến, nhưng đây không phải lỗi dữ liệu.

## 7. Ba cách bắt đầu hoặc tiếp tục change stream

### 7.1. `resumeAfter(token)`

Dùng khi đã có token từ event trước, muốn tiếp tục **sau event đó**:

```java
ChangeStreamIterable<Document> stream =
        collection.watch();

if (savedToken != null) {
    stream.resumeAfter(savedToken);
}
```

Các điều kiện:

- Oplog còn đủ history chứa vị trí token.
- Pipeline và options tương thích như khi token được tạo.
- Namespace/topology còn phù hợp.
- Không dùng `resumeAfter` với token của **invalidate event**.

Nếu checkpoint ghi token sau side effect, restart với `resumeAfter` sẽ không phát lại event đó, nhưng có thể phát lại một event **chưa checkpoint**.

### 7.2. `startAfter(token)`

Dùng khi khởi động stream **sau một token**; đặc biệt khác `resumeAfter` ở chỗ nó có thể tạo stream mới **sau invalidate event**:

```java
ChangeStreamIterable<Document> stream =
        collection.watch()
            .startAfter(invalidateToken);
```

Ví dụ collection bị drop/rename/recreated và application muốn theo dõi namespace mới. Nhưng **đừng tự dùng `startAfter` để che giấu mất data**:

- Collection mới có thể khác schema/owner.
- Token vẫn phụ thuộc oplog history.
- Business semantics khi drop/rename có thể cần re-bootstrap.
- Cần quyết định rõ whether to resume/migrate or stop processing.

### 7.3. `startAtOperationTime(timestamp)`

Có thể mở stream từ một MongoDB **BSON timestamp**:

```java
BsonTimestamp operationTime = new BsonTimestamp(
    secondsSinceEpoch,
    increment
);

ChangeStreamIterable<Document> stream =
        collection.watch()
            .startAtOperationTime(operationTime);
```

Đây **không phải** timestamp `java.util.Date`/milliseconds đơn giản. Cần dùng một timestamp logic hợp lệ đã được ghi nhận từ server/operation, và nó phải còn trong oplog history nếu là mốc quá khứ.

`startAtOperationTime` có thể hữu ích trong bootstrap/backfill protocol khi chưa có token event, nhưng không nên chế timestamp từ đồng hồ client rồi khẳng định không có gap.

### 7.4. Ba tùy chọn loại trừ nhau

| Tùy chọn | Dùng khi | Cảnh báo |
| --- | --- | --- |
| Không truyền điểm bắt đầu | Theo dõi thay đổi mới từ lúc stream được thiết lập | Không tự backfill toàn bộ dữ liệu quá khứ |
| `resumeAfter` | Tiếp tục sau token thông thường | Không dùng sau invalidate |
| `startAfter` | Khởi động sau token, gồm invalidate | Phải xét lifecycle namespace |
| `startAtOperationTime` | Khởi động ở MongoDB operation time | Timestamp trong oplog, không kết hợp token |

Không đặt `resumeAfter`, `startAfter` và `startAtOperationTime` đồng thời.

## 8. Tính đúng đắn: vì sao thứ tự checkpoint quyết định mất dữ liệu?

### 8.1. Sai: checkpoint trước business side effect

```text
Receive event E42
       |
Persist token T42  <-- đã đánh dấu xử lý xong
       |
Call external API
       |
CRASH before external API succeeds
       |
Restart with resumeAfter(T42)
       |
E42 không được phát lại
```

Đây là lỗi **at-most-once/lost work**. Nếu side effect thất bại nhưng token đã được lưu, hệ thống có thể im lặng bỏ qua event.

### 8.2. Đúng hơn: side effect trước checkpoint

```text
Receive event E42
       |
Apply side effect successfully
       |
Persist token T42
       |
Continue reading
```

Nếu crash xảy ra sau side effect nhưng trước checkpoint, E42 sẽ được phát lại. Đây là **at-least-once** (không mất do cửa sổ crash này, nhưng có thể trùng).

Cần kết hợp xử lý **idempotent** để xử lý lại an toàn.

### 8.3. Ma trận crash window

| Thời điểm crash | Sink đã có kết quả? | Token đã được lưu? | Khi restart |
| --- | --- | --- | --- |
| Trước khi xử lý E42 | Chưa | Chưa | E42 có thể được phát lại |
| Trong lúc sink request | Không rõ | Chưa | Phải verify/retry idempotently |
| Sau sink success, trước checkpoint | Có | Chưa | E42 có thể được phát lại |
| Sau checkpoint success | Có | Có | Tiếp tục sau E42 |
| Lưu checkpoint trước sink | Chưa | Có | **Có thể mất E42** |

`ACK` của API ngoài có thể thất lạc sau khi side effect đã xảy ra; không thể chỉ dựa vào một exception để kết luận “chưa làm gì”.

### 8.4. Không tự hứa exactly once

**Change stream + resume token không tạo exactly-once side effect xuyên MongoDB và một hệ thống bên ngoài.**

Một xử lý có thể được giao lại sau restart/retry. Để có hiệu ứng nghiệp vụ không trùng:

- Dùng idempotency key của event ở sink.
- Upsert bằng deterministic key.
- Dùng unique constraint cho deduplication ledger.
- Lưu side effect và checkpoint **trong cùng transaction** nếu cả hai nằm trong một MongoDB deployment và topology hỗ trợ.
- Nếu đẩy qua queue, cân nhắc transactional outbox/inbox.
- Với external payment/email, dùng API có idempotency hoặc reconcile theo business ID.

Chỉ nói “exactly once” khi có thiết kế end-to-end và proof về tất cả failure windows.

## 9. Idempotent processing theo event token

### 9.1. Dùng event identity ổn định

`event.getResumeToken()` là identifier của một change event. Với sink không chấp nhận BSON làm ID, có thể tạo một **hash ổn định** từ token serialized theo quy tắc cố định và kèm consumer name.

Ví dụ Java 17:

```java
import org.bson.BsonDocument;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

static String eventKey(String consumerName, BsonDocument token) {
    try {
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(
                (consumerName + ":" + token.toJson())
                    .getBytes(StandardCharsets.UTF_8)
            );

        return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException("SHA-256 unavailable", e);
    }
}
```

Đây là ví dụ tạo dedup key, **không phải thuật toán giải mã token**. Trong production, quy định format serialization ổn định qua driver upgrades và test round-trip, hoặc lưu canonical BSON bytes; không suy luận timestamp/ordering từ hash.

### 9.2. Inbox/processed events collection

Một document sink có thể là:

```javascript
{
  _id: "sha256-of-consumer-and-resume-token",
  consumer: "order-projection-v1",
  source: "commerce.orders",
  op: "update",
  processedAt: ISODate("2026-11-14T04:15:00Z")
}
```

MongoDB tự có unique `_id` index. Chèn lần hai cùng ID sẽ gặp duplicate; dùng upsert với `$setOnInsert` để idempotent:

```java
String id = eventKey(consumerName, event.getResumeToken());

processedEvents.updateOne(
    Filters.eq("_id", id),
    Updates.combine(
        Updates.setOnInsert("consumer", consumerName),
        Updates.setOnInsert(
            "processedAt",
            new java.util.Date()
        )
    ),
    new UpdateOptions().upsert(true)
);
```

**Quan trọng:** việc lưu event ID vào ledger không làm một **HTTP side effect khác** tự trở nên idempotent. Nếu muốn gửi email hay gọi payment API, sink đó cũng phải nhận/reconcile idempotency key; cần transaction/outbox nếu phối hợp nhiều tài nguyên.

### 9.3. Cập nhật projection bằng deterministic key

Ví dụ đọc đơn hàng theo ID:

```java
Document fullDocument = event.getFullDocument();

if (fullDocument != null) {
    Object businessId = fullDocument.get("_id");

    orderReadModel.replaceOne(
        Filters.eq("_id", businessId),
        fullDocument,
        new ReplaceOptions().upsert(true)
    );
}
```

Đây là ví dụ **idempotent assignment** theo `_id` trong điều kiện **một consumer xử lý tuần tự**. Với concurrent consumers hoặc `updateLookup` có thể lấy state mới hơn, cần thêm `version`, compare-and-set hoặc projection logic riêng. Không dùng `replaceOne` nếu target có schema/fields độc lập mà source không biết.

### 9.4. Không ghi vào chính collection đang watch một cách vô hạn

Nếu watch toàn database/deployment rồi ghi checkpoint hoặc projection **cũng trong database đó**, các writes của consumer có thể tạo change events mới và dẫn đến vòng phản hồi.

Để tránh:

- Watch đúng source collection.
- Hoặc filter namespaces/operation types cẩn thận.
- Dùng checkpoint/projection collections riêng.
- Không transform event làm mất `_id`.
- Giám sát trường hợp self-triggering feedback loop.

## 10. Lưu checkpoint MongoDB bằng BSON nguyên vẹn

### 10.1. Một collection riêng cho mỗi consumer scope

Ví dụ:

```text
Database: mongo_change_row395_lab

events_row395_lab          -> source events
processed_events_row395   -> demo idempotent sink
change_stream_checkpoints -> durable resume state
```

Checkpoint key nên phân biệt:

- Deployment/cluster identity.
- Source namespace và watch scope.
- Consumer group/worker identity.
- Pipeline + options version.
- Schema version của side-effect logic.

Ví dụ:

```javascript
{
  _id: "lab:events_row395:report-worker:pipeline-v1",
  resumeToken: { _data: "826..." },
  pipelineVersion: "v1",
  updatedAt: ISODate("2026-11-14T04:30:00Z")
}
```

Không dùng cùng checkpoint `_id` cho hai consumers có logic khác nhau hoặc hai pipeline không tương thích.

### 10.2. Java đọc checkpoint

Dùng collection typed `BsonDocument` để giữ token đúng kiểu:

```java
MongoCollection<BsonDocument> checkpoints =
    database.getCollection(
        "change_stream_checkpoints",
        BsonDocument.class
    );

String streamKey = "lab:events:workerA:pipeline-v1";

BsonDocument record = checkpoints
    .find(Filters.eq("_id", streamKey))
    .first();

BsonDocument token = record == null
    ? null
    : record.getDocument("resumeToken");
```

Nếu lưu checkpoint trong JSON/string/Redis, phải kiểm tra deserialize trả đúng **BSON document**, không phải chuỗi `_data` hay field random được client tự dựng.

### 10.3. Java ghi checkpoint

```java
import com.mongodb.client.model.ReplaceOptions;
import org.bson.BsonDateTime;
import org.bson.BsonString;

static void saveCheckpoint(
        MongoCollection<BsonDocument> checkpoints,
        String streamKey,
        BsonDocument token) {

    BsonDocument checkpoint = new BsonDocument()
        .append("_id", new BsonString(streamKey))
        .append("resumeToken", token)
        .append(
            "updatedAt",
            new BsonDateTime(System.currentTimeMillis())
        );

    checkpoints.replaceOne(
        Filters.eq("_id", streamKey),
        checkpoint,
        new ReplaceOptions().upsert(true)
    );
}
```

Trong production, tăng durability checkpoint bằng write concern phù hợp (ví dụ `majority` khi có yêu cầu mạnh), quyền ghi giới hạn, audit, và fencing nếu nhiều instances cạnh tranh.

### 10.4. Checkpoint mới không phải số sequence của business

Không lấy `clusterTime` hoặc `documentKey` thay token. Các transaction/sharded events có thể chia sẻ clusterTime; token chứa thông tin vị trí cần cho resume.

`checkpoint.updatedAt` là thời gian **worker ghi tiến độ**, không phải timestamp sự kiện. Dùng nó để đo freshness tương đối, không để quyết định ordering tuyệt đối.

## 11. Ví dụ Java Sync Driver: vòng tiêu thụ có checkpoint và shutdown

Đây là một **mẫu ứng dụng hoàn chỉnh theo hướng instructional**. Nó:

- kết nối tới replica set **lab**;
- chỉ watch một source collection;
- khôi phục `resumeAfter` từ checkpoint;
- xử lý tuần tự, ghi vào một **idempotent inbox**;
- lưu token **sau** khi sink operation thành công;
- kiểm tra stop flag qua `tryNext()`;
- đóng cursor bằng `try-with-resources`;
- nhận SIGTERM qua shutdown hook và chờ worker hoàn tất trong thời gian có hạn;
- không tự xóa/drop dữ liệu test.

### 11.1. Cấu hình môi trường

```text
MONGODB_URI=mongodb://localhost:27017/?replicaSet=rs0
ROW395_SOURCE=events_row395_lab
ROW395_CONSUMER=demo-consumer-v1
```

Dùng URI riêng của replica set test (đường dẫn trên chỉ là ví dụ). **Không viết password hoặc URI thật vào source/README public**.

Dùng một `ROW395_SOURCE` ổn định giữa các lần khởi động thì consumer mới có thể tiếp tục cùng stream. Nếu mỗi lần startup sinh collection name mới, checkpoint cũ không còn tương ứng.

### 11.2. Java class

```java
import com.mongodb.MongoException;
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;

import org.bson.BsonDateTime;
import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Date;
import java.util.HexFormat;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ChangeStreamWorker395 {
    private final MongoCollection<Document> source;
    private final MongoCollection<Document> processedEvents;
    private final MongoCollection<BsonDocument> checkpoints;

    private final String streamKey;
    private final AtomicBoolean stopping = new AtomicBoolean(false);
    private final CountDownLatch finished = new CountDownLatch(1);

    public ChangeStreamWorker395(
            MongoDatabase db,
            String sourceName,
            String consumerName) {

        this.source = db.getCollection(sourceName);
        this.processedEvents =
                db.getCollection("row395_processed_events");
        this.checkpoints = db.getCollection(
                "row395_change_checkpoints",
                BsonDocument.class
        );

        this.streamKey = db.getName()
                + ":" + sourceName
                + ":" + consumerName
                + ":pipeline-v1";
    }

    public void requestStop() {
        stopping.set(true);
    }

    public boolean awaitStop(long seconds)
            throws InterruptedException {
        return finished.await(seconds, TimeUnit.SECONDS);
    }

    private BsonDocument loadToken() {
        BsonDocument row = checkpoints
                .find(Filters.eq("_id", streamKey))
                .first();

        return row == null
                ? null
                : row.getDocument("resumeToken");
    }

    private void storeToken(BsonDocument token) {
        BsonDocument row = new BsonDocument()
                .append("_id", new BsonString(streamKey))
                .append("resumeToken", token)
                .append("updatedAt",
                        new BsonDateTime(System.currentTimeMillis()));

        checkpoints.replaceOne(
                Filters.eq("_id", streamKey),
                row,
                new ReplaceOptions().upsert(true)
        );
    }

    private static String sha256(String data) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(data.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private void applyIdempotently(
            ChangeStreamDocument<Document> event) {

        BsonDocument token = event.getResumeToken();
        String eventId = sha256(streamKey + ":" + token.toJson());

        // Demo: ghi idempotent inbox, KHÔNG gọi HTTP side effect.
        processedEvents.updateOne(
                Filters.eq("_id", eventId),
                Updates.combine(
                        Updates.setOnInsert(
                                "streamKey", streamKey
                        ),
                        Updates.setOnInsert(
                                "operation",
                                String.valueOf(event.getOperationType())
                        ),
                        Updates.setOnInsert(
                                "processedAt", new Date()
                        )
                ),
                new UpdateOptions().upsert(true)
        );
    }

    public void consume() {
        try {
            while (!stopping.get()) {
                BsonDocument persisted = loadToken();

                ChangeStreamIterable<Document> iterable = source.watch()
                        .maxAwaitTime(1, TimeUnit.SECONDS);

                if (persisted != null) {
                    iterable = iterable.resumeAfter(persisted);
                }

                try (MongoChangeStreamCursor<
                        ChangeStreamDocument<Document>> cursor =
                             iterable.cursor()) {

                    System.out.println("Change stream active: " + streamKey);

                    while (!stopping.get()) {
                        ChangeStreamDocument<Document> event =
                                cursor.tryNext();

                        if (event == null) {
                            continue;
                        }

                        if (event.getOperationType()
                                == OperationType.INVALIDATE) {
                            // Drop/rename: không tiếp tục như bình thường.
                            throw new IllegalStateException(
                                    "Source invalidated; manual re-bootstrap required"
                            );
                        }

                        // 1) Hoàn thành side effect idempotent.
                        applyIdempotently(event);

                        // 2) Checkpoint CHỈ SAU khi side effect thành công.
                        storeToken(event.getResumeToken());
                    }
                }
            }
        } finally {
            finished.countDown();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        String uri = System.getenv("MONGODB_URI");
        String sourceName = System.getenv("ROW395_SOURCE");
        String consumerName = System.getenv("ROW395_CONSUMER");

        if (uri == null || sourceName == null ||
                consumerName == null) {
            throw new IllegalArgumentException(
                    "Need MONGODB_URI, ROW395_SOURCE, ROW395_CONSUMER"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase(
                    "mongo_change_row395_lab"
            );

            ChangeStreamWorker395 worker = new ChangeStreamWorker395(
                    db, sourceName, consumerName
            );

            Runtime.getRuntime().addShutdownHook(
                    new Thread(() -> {
                        worker.requestStop();

                        try {
                            if (!worker.awaitStop(20)) {
                                System.err.println(
                                        "Shutdown deadline reached; " +
                                        "uncheckpointed events may replay."
                                );
                            }
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    }, "row395-shutdown")
            );

            // Vòng này chạy trên main thread. SIGTERM kích hoạt
            // shutdown hook ở thread khác, đặt stopping=true.
            worker.consume();
        }
    }
}
```

### 11.3. Hành vi và giới hạn của mẫu code

- Worker xử lý **tuần tự**, không có hàng đợi event nội bộ. Do đó checkpoint được lưu sau một sink operation thành công.
- `processedEvents` là inbox dùng `$setOnInsert` và unique `_id`; xử lý lại cùng token không tạo bản ghi mới.
- `checkpoint` là hai writes MongoDB **khác nhau** so với side effect. Nếu crash giữa hai bước, event được phát lại và inbox hấp thụ duplicate.
- Code không gọi một hệ thống ngoài. Khi tích hợp email/payment/Kafka, phải thêm idempotency/outbox/ack semantics tương ứng.
- Code **không tự bắt mọi `MongoException` rồi resume vô hạn**. Khi stream gặp lỗi, process thoát để supervisor thực hiện backoff và vận hành điều tra. Đây là một lựa chọn **fail closed** cho bài học. Có thể thêm retry policy được phân loại ở phần sau.
- `getResumeToken()` của cursor không được dùng làm checkpoint vì có thể tiến tới highwatermark trong lúc công việc chưa được xác nhận.
- Demo không có distributed leader election/lease; **chạy một active instance cho mỗi streamKey**. Nếu chạy nhiều pods cùng streamKey, dễ có race ghi checkpoint.
- Với stop deadline, `tryNext()` có thể chờ quá 1 giây nếu network gặp sự cố. Không hứa shutdown luôn xong đúng 20 giây. Cấu hình timeout/socket và thời gian grace của orchestrator phải được thiết kế.
- Nếu tiến trình chết khi cập nhật inbox/checkpoint và write concern chưa đủ mạnh, phải xét rollback theo replica set failover. Với production, cân nhắc `WriteConcern.MAJORITY` cho những collections quan trọng.

### 11.4. Thêm write concern khi phù hợp

```java
MongoCollection<Document> durableSink =
        db.getCollection("row395_processed_events")
          .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<BsonDocument> durableCheckpoints =
        db.getCollection(
            "row395_change_checkpoints",
            BsonDocument.class
        ).withWriteConcern(WriteConcern.MAJORITY);
```

Nhớ import `com.mongodb.WriteConcern`. Chọn durability theo nghiệp vụ và replica set; `majority` có thể làm latency tăng khi secondaries chậm. **Write concern timeout không có nghĩa thao tác chắc chắn chưa thực hiện**; hãy đối soát trước khi retry side effect.

## 12. Graceful shutdown: nhận SIGTERM đến lúc đóng client

### 12.1. Trình tự mong muốn

```text
Kubernetes / systemd / application stop
                  |
                 SIGTERM
                  |
                  v
             Stop flag = true
                  |
       Stop receiving new work
                  |
                  v
         Wait for current event
           side effect to finish
                  |
                  v
       Persist processed event token
                  |
                  v
           Close change cursor
                  |
                  v
        Close MongoClient/resources
                  |
                  v
             Process exit
```

Nếu deadline đến trước khi side effect hoàn tất, **không checkpoint trước để ép thoát**. Hãy để lần chạy sau replay event nhờ idempotency.

### 12.2. Vì sao không đóng MongoClient ngay khi nhận SIGTERM?

Nếu shutdown hook gọi:

```java
client.close();
```

ngay trong lúc worker còn đang:

- đọc change stream;
- ghi projection/inbox;
- lưu checkpoint;

worker có thể nhận connection closed. Side effect có thể đã được server áp dụng nhưng ứng dụng chưa ghi nhận kết quả, tạo trạng thái không rõ.

Thứ tự tốt hơn: **yêu cầu dừng → chờ worker drain/ack → đóng cursor → đóng client**.

### 12.3. Cần thời hạn dừng hữu hạn

Một shutdown hook chờ mãi có thể khiến pod không được thay thế. Ngược lại thời gian quá ngắn khiến nhiều event phải replay.

Các thời hạn cần phối hợp:

- Server `maxAwaitTime`/`getMore`.
- Driver socket timeout/server selection timeout.
- Deadline xử lý một event.
- Timeout/độ tin cậy của external sink.
- Tổng `terminationGracePeriodSeconds` của Kubernetes.
- Lifecycle grace period của Spring Boot.
- Thời gian để flush metrics/logs sau consumer ngừng.

Giá trị **20 giây** trong mã ví dụ chỉ minh họa. Không có ngưỡng chung cho mọi workload.

### 12.4. `tryNext()` không bảo đảm dừng tức thời

Ngay cả với `maxAwaitTime(1, SECONDS)`, network hoặc driver server selection có thể kéo dài.

Không giải quyết bằng cách để hai thread dùng/đóng cùng `MongoChangeStreamCursor` tùy ý: Javadocs đánh dấu cursor **not thread-safe**. Hãy để worker **sở hữu cursor** và đóng nó ở `finally`/try-with-resources.

Nếu cần force shutdown sau deadline, quy trình phải chấp nhận **event chưa checkpoint có thể replay**. Một socket/client bị đóng cưỡng bức không được xem là “side effect chắc chắn chưa chạy”.

### 12.5. Phân biệt dừng có kiểm soát và crash cứng

| Tình huống | Hook/finally chạy? | Kỳ vọng |
| --- | --- | --- |
| SIGTERM xử lý được | Có thể chạy | Stop, drain, checkpoint, close |
| Spring context close bình thường | Có thể chạy callback | Dừng consumer theo lifecycle |
| SIGKILL/OOMKill | **Không bảo đảm** | Event chưa checkpoint replay |
| Mất điện/node crash | Không | Khởi động lại từ durable checkpoint |
| Network partition | Process còn sống nhưng operation lỗi | Retry có backoff hoặc fail closed |
| DB election | Driver có thể auto-resume lỗi phù hợp | Có thể nhận lại event; checkpoint vẫn đúng |
| Code bug/exception | `finally` có thể chạy | Không checkpoint event thất bại |

Graceful shutdown làm giảm reprocessing nhưng **không loại bỏ yêu cầu idempotency**.

## 13. Tích hợp với Spring Boot và lifecycle container

### 13.1. Không khởi động consumer trong HTTP request

Không đặt:

```java
@GetMapping("/listen")
public void listen() {
    collection.watch().forEach(...);
}
```

vì request thread bị giữ, khó quản lý phiên chạy và có nguy cơ mở hàng nghìn change streams khi client gọi endpoint.

Nên tạo một service chuyên trách:

- `@Service` + managed executor;
- `SmartLifecycle` khi cần kiểm soát start/stop phase;
- hoặc một worker deployment riêng không đi chung web server.

### 13.2. Mẫu lifecycle khái niệm

```java
@Component
public class ChangeStreamLifecycle implements SmartLifecycle {
    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    private final AtomicBoolean running =
            new AtomicBoolean(false);

    private Future<?> future;

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            future = executor.submit(() -> consumeLoop(running));
        }
    }

    @Override
    public void stop() {
        running.set(false);
        executor.shutdown();

        try {
            if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
                // Không checkpoint event chưa xử lý.
                // Report deadline; supervisor/replay handles it.
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
```

Đây là **skeleton**, chưa có imports, `consumeLoop` và các thành phần dependency injection. Với code thực:

1. Đóng cursor trong worker.
2. Không tạo thread mới mỗi khi `start()` được gọi.
3. Đảm bảo Spring container stop phase và MongoClient bean shutdown order đúng.
4. Theo dõi `Future`/lỗi worker; `running=true` không đồng nghĩa worker còn khỏe nếu thread chết.
5. Đừng coi `executor.shutdownNow()` là bảo đảm ngắt lập tức I/O; cần safe replay.
6. Cấu hình graceful shutdown budget của Spring Boot/Kubernetes tương ứng.

### 13.3. Readiness và liveness

Một watcher bị mất token hoặc rơi vào lỗi `ChangeStreamHistoryLost` không nên vẫn báo tất cả health checks “xanh”.

Tách:

- **Liveness:** process còn hoạt động và có thể phục hồi lỗi.
- **Readiness:** component có thể xử lý công việc đúng/SLO.
- **Consumer health:** last checkpoint age, lag, stream connected, processing errors, ownership lease.

Không buộc cả HTTP API fail readiness chỉ vì consumer phụ gặp lỗi nếu kiến trúc cho phép API phục vụ độc lập; định nghĩa theo yêu cầu nghiệp vụ.

## 14. Reactive Streams Driver: khác Java Sync

### 14.1. Cùng semantics, khác lifecycle

Với MongoDB Java Reactive Streams Driver, change stream được tiêu thụ qua **Publisher/Subscriber** (và có thể tích hợp Reactor), không dùng `MongoChangeStreamCursor` như sync API.

Điểm quan trọng:

- `Subscription.cancel()` dừng nhu cầu nhận thêm dữ liệu.
- Backpressure xác định số lượng events yêu cầu.
- Không subscribe một Publisher rồi bỏ reference quản lý lifecycle.
- Không checkpoint trong `doOnNext` nếu downstream async chưa hoàn thành.
- Dùng `concatMap`/serial processing hoặc explicit ordering khi checkpoint có thứ tự.
- Dọn subscription khi Spring Reactor context đóng, và chờ công việc side effect đạt điểm ổn định.

### 14.2. Lỗi khi xử lý song song

Ví dụ giả định:

```text
Event E10 -> xử lý chậm
Event E11 -> xử lý nhanh
Event E12 -> xử lý nhanh
```

Nếu E12 checkpoint trước E10, crash sẽ làm E10 bị bỏ qua khi restart với token sau E12.

Với parallel processing cần:

- **ordered commit frontier:** chỉ checkpoint token lớn nhất mà **mọi sự kiện trước đó** đã hoàn tất;
- hoặc partitioning bảo đảm ordering theo key và checkpoint riêng từng partition/consumer scope;
- không chia sẻ một token toàn stream cho các workers xử lý out-of-order mà không có coordinator.

Trong học liệu này, Java Sync loop xử lý tuần tự là baseline dễ chứng minh correctness.

## 15. Errors: transient, resumable và fatal không giống nhau

### 15.1. Driver tự resume một số lỗi

Java Driver tuân thủ change stream specifications: với **resumable errors** phù hợp, driver có cơ chế **thử resume** lại stream theo cached token/operation time. Đây là trợ giúp quan trọng khi election/network lỗi tạm.

Nhưng:

- Không phải mọi lỗi đều resumable.
- Driver không cam kết retry vô hạn.
- Event vẫn có thể được ứng dụng xử lý rồi chưa checkpoint.
- Nếu ứng dụng khởi động lại, phải dùng **durable checkpoint** của chính ứng dụng, không chỉ token trong RAM driver.

### 15.2. Phân loại lỗi

| Nhóm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Mạng/election tạm | Timeout, NotPrimary, interrupted repl state | Driver auto-resume nếu hợp lệ; application bounded backoff/reopen |
| Sink tạm thời | HTTP 503, queue unavailable | Không checkpoint; retry với idempotency/backoff |
| Sink permanent/poison | Payload không hợp lệ, business invariant | DLQ/quarantine/manual fix; không bỏ qua âm thầm |
| Auth/KMS/permissions | Không đủ quyền watch/read | Fail closed, alert, sửa credential/policy |
| `ChangeStreamHistoryLost` | Token quá cũ so với oplog | **Không** resume-from-now; re-bootstrap/reconcile |
| `invalidate` | Collection drop/rename | Phân tích lifecycle, có thể startAfter theo policy |
| Pipeline/options changed | Token cũ không tương thích | Lập migration checkpoint/pipeline |
| Resource pressure | Quá nhiều cursors/connections, memory/disk | Giảm watchers, sizing và alert |

### 15.3. Không retry liên tục không giới hạn

Một lỗi invalid token hoặc thiếu quyền không thể sửa bằng cách retry mỗi 10 ms.

Dùng:

- retry budget;
- exponential backoff có jitter;
- phân loại resumable/non-resumable;
- alert đến owner;
- circuit breaker cho sink;
- metrics số lần reopen/resume;
- giám sát oplog window và backlog.

### 15.4. `ChangeStreamHistoryLost`: token đã rơi khỏi oplog

Giả sử:

```text
Oplog history window: ~12 hours
Consumer stopped:      36 hours
Latest checkpoint:     older than available history
Restart:               resumeAfter fails
```

Trong một số phiên bản lỗi có mã `286` (`ChangeStreamHistoryLost`), nhưng không chỉ dựa vào hardcoded message/code; đọc error labels/server version.

Không được:

```java
// Anti-pattern: mất lịch sử thì bỏ token, mở stream từ hiện tại.
if (resumeFailed) {
    collection.watch().forEach(this::process);
}
```

Làm vậy có thể **mất 24 giờ thay đổi** mà không tạo alarm. Hệ thống phải có:

- source of truth để đối soát;
- snapshot/backfill;
- event source khác có retention dài hơn;
- hoặc quy trình manual recovery chấp nhận và ghi lại gap theo business decision.

## 16. Oplog window và khả năng resume

### 16.1. Oplog là cửa sổ lịch sử, không phải queue vô hạn

Change streams được xây dựng từ oplog. Oplog có giới hạn kích thước/retention tùy cấu hình và write volume. Khi workload ghi tăng, **thời gian lịch sử thực tế** có thể ngắn lại.

Ví dụ:

```text
Normal write volume:
   oplog covers 40 hours

Sales campaign / bulk import:
   oplog covers only 6 hours

Worker paused 10 hours:
   restart token may be too old
```

Đừng chỉ tính “oplog size = 30 GiB nên worker có thể dừng 2 ngày”. Cần quan sát **oplog window thực tế và tốc độ ghi**.

### 16.2. So sánh thời gian consumer dừng với oplog window

Các thông tin hữu ích:

- Current oplog earliest/latest timestamp, ước lượng window.
- Last successful checkpoint timestamp/clusterTime.
- Time since last processed event.
- Event processing latency.
- Retry backlog.
- Replication lag và primary election events.

Mức an toàn thường dựa trên **oplog window còn lại lớn hơn thời gian recovery dự kiến** có headroom; không dựa vào một ngưỡng cố định.

### 16.3. Query tham khảo trong `mongosh`

Trên replica set test/self-managed có quyền phù hợp:

```javascript
rs.printReplicationInfo();
```

Output có thể mô tả oplog window trên server. Một số managed tiers không cho đọc trực tiếp `local.oplog.rs`; dùng Atlas monitoring/metrics tương đương.

Không tự `replSetResizeOplog` hoặc đổi config oplog trên production chỉ vì tutorial; điều đó có ảnh hưởng replication/disk/retention và phải theo runbook.

## 17. Pipeline change stream và hợp đồng tương thích

### 17.1. Lọc các operation types

```java
List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.in(
            "operationType",
            List.of("insert", "update", "replace", "delete")
        )
    )
);

ChangeStreamIterable<Document> stream =
        collection.watch(pipeline);
```

Lợi ích: giảm số sự kiện truyền về application khi workload không liên quan. Nhưng cần cân nhắc event `invalidate` và các lifecycle events. Nếu filter bỏ các events đó, consumer có thể mất khả năng quan sát nguyên nhân stream đóng.

### 17.2. Không thay event `_id`

Không làm:

```javascript
// KHÔNG làm trên change stream:
{ $project: { _id: 0, operationType: 1 } }
```

MongoDB 4.2+ có thể báo lỗi nếu pipeline thay/loại `_id` của change event, vì mất resume token.

Nếu muốn giảm payload, project các field khác nhưng **giữ nguyên `_id`**, và kiểm tra pipeline theo support matrix.

### 17.3. Giữ nguyên pipeline/options khi resume

MongoDB cảnh báo resume với pipeline/options khác có thể cho kết quả không như mong đợi hoặc không thể resume.

Ví dụ:

```text
checkpoint generated under:
   source = orders
   filter = operationType in [insert, update]
   fullDocument = updateLookup
   collation = simple

restart under:
   source = orders
   filter = status = PAID
   fullDocument = default

=> không coi token cũ tương thích tự nhiên
```

Trong checkpoint, gắn `pipelineVersion`/cấu hình triển khai. Khi thay pipeline:

1. Xác định thay đổi tập sự kiện.
2. Dừng consumer cũ ở checkpoint an toàn.
3. Nếu tương thích theo tài liệu, di chuyển theo strategy rõ.
4. Nếu không, tạo stream consumer/version mới và re-bootstrap/reconcile.
5. Đổi routing sau khi đánh giá lag và output.
6. Không âm thầm reuse token cũ.

### 17.4. Repeated events trong transaction

Một transaction có thể phát nhiều change events liên quan. Events có thể chia sẻ `clusterTime`; chỉ dùng timestamp làm dedup sẽ bỏ sót thay đổi hợp lệ.

Dùng **resume token đầy đủ** cho vị trí, kết hợp `lsid`/`txnNumber` khi phân tích transaction nếu cần. Không tự suy ra “cùng clusterTime = cùng event”.

## 18. Full snapshot và change stream bootstrap không có gap

### 18.1. Change stream không tự xuất toàn bộ dữ liệu hiện hữu

Khi ứng dụng mới khởi tạo:

```java
collection.watch();
```

nó chủ yếu nhận những thay đổi **sau khi stream được mở theo điểm bắt đầu**, không tự gửi một lần toàn bộ collection giống `find()`.

Nếu cần tạo search index/read model từ 10 triệu documents hiện có, phải làm **backfill + CDC** nhất quán.

### 18.2. Lỗi bootstrap thường gặp

```text
T0: scan toàn bộ documents
T1: ghi projection từ scan
T2: bắt đầu watch()

Document thay đổi giữa T0 và T2
  -> có thể không được phản ánh vào projection
```

Đây là **gap**. Không có resume token từ trước T0 để phát lại thay đổi trong khoảng trống đó.

### 18.3. Một giao thức an toàn hơn

Tùy yêu cầu:

1. Xác lập **điểm bắt đầu CDC** (stream/token/operationTime) theo protocol.
2. Bắt đầu thu nhận/buffer changes **trước hoặc cùng lúc** với snapshot.
3. Backfill dữ liệu hiện có vào projection có version/idempotency.
4. Replay events trong thời gian backfill, xử lý race/order theo document version.
5. Chỉ cutover khi projection đã catch up và checksums/count hợp lệ.
6. Persist token và tiếp tục streaming.
7. Có checkpoint đủ dài, oplog window đủ lớn cho toàn bộ backfill.

Không đơn giản “mở stream trước rồi quét” nếu không có khả năng giữ/đệm event backlog, vì oplog có thể cuốn qua khi backfill lâu. Với dữ liệu quan trọng, dùng công cụ CDC/connector hoặc quy trình snapshot-consistent đã được kiểm chứng.

### 18.4. Nếu mất history thì phải re-bootstrap

Không có thiết kế nào giúp một resume token đọc lại oplog event đã bị xóa khỏi lịch sử và không có bản sao ở nơi khác. Khi token hết hạn:

- Dừng đưa output không nhất quán vào downstream.
- Phát alarm rõ ràng.
- Xác định source of truth và phạm vi thay đổi bị mất.
- Chạy backfill/reconcile.
- Lập checkpoint mới theo giao thức bảo đảm không gap.
- Lưu audit decision; không âm thầm nhảy tới hiện tại.

## 19. Tính đúng đắn khi có nhiều pod

### 19.1. Hai instance cùng watch một stream

```text
Pod A watches orders
Pod B watches orders
          |
Both receive E42
          |
Both write shared checkpoint
```

MongoDB Change Stream **không tự cung cấp consumer group/partition ownership giống Kafka**. Nếu hai pods cùng watch scope, mỗi pod có thể nhận cùng events; dùng chung checkpoint càng dễ race và nhảy qua việc chưa xử lý.

### 19.2. Một active owner cho mỗi checkpoint

Một cách:

- Leader election/distributed lease.
- `streamKey` cố định cho một logical consumer.
- Mỗi pod có `ownerId`/`leaseUntil`.
- Chỉ owner còn lease mới tiêu thụ/ghi checkpoint.
- Khi chuyển owner, dùng `fencingEpoch` để chặn writer cũ ghi checkpoint.
- Checkpoint update kèm condition về epoch/owner và monotonic progress logic.

Ví dụ lease record:

```javascript
{
  _id: "orders-projection-v1",
  ownerId: "pod-3",
  leaseUntil: ISODate("2026-11-14T04:32:00Z"),
  fencingEpoch: NumberLong("12"),
  resumeToken: { _data: "..." }
}
```

Đây là thiết kế ứng dụng, **MongoDB driver không tự tạo lease cho mỗi change stream**.

### 19.3. Lease hết hạn chưa chắc writer cũ dừng

Pod A có thể bị network partition, lease hết hạn nhưng tiếp tục xử lý event từ một cursor còn mở. Pod B chiếm lease mới. Nếu không có fencing, cả A và B có thể ghi side effects.

Fencing phải được thực thi ở **checkpoint writes và sink writes**. Một check owner trong RAM không đủ. Nếu sink ngoài không hỗ trợ fencing, cần idempotency mạnh và protocol chuyển owner cẩn thận.

### 19.4. Scale-out bằng phân vùng

Các lựa chọn:

1. **Một watcher**, chia work ra queues/partitions theo document key, commit token chỉ sau khi mọi event trước nó hoàn tất.
2. **Nhiều watchers với pipelines khác nhau** trên tập tenant/shard key không giao nhau và checkpoint độc lập.
3. **Outbox + message broker** nếu cần fan-out lớn, ordering per key và retention.

Không chỉ tạo 20 pods cùng một `collection.watch()` rồi hy vọng MongoDB tự phân phối 1/20 sự kiện cho mỗi pod. Mỗi stream có chi phí oplog scan/getMore/connections.

## 20. Transactional checkpoint khi side effect nằm trong MongoDB

### 20.1. Một cách giảm cửa sổ crash

Nếu projection và checkpoint cùng ở MongoDB replica set/sharded cluster tương thích, có thể:

- lấy change event **ngoài transaction**;
- mở **transaction mới ngắn**;
- cập nhật projection/idempotent sink;
- lưu checkpoint;
- commit transaction;
- chỉ sau commit thành công mới đọc event tiếp.

```text
watch().tryNext() -> event E42
          |
          v
begin MongoDB transaction
          |
update projection / inbox
          |
save token T42
          |
commit transaction
          |
          v
next event
```

Nếu transaction abort, cả projection và checkpoint của E42 rollback, nên E42 có thể phát lại. Nhưng vẫn có trường hợp **commit result unknown** do network: phải xử lý theo MongoDB transaction retry semantics và idempotency.

### 20.2. Vì sao không đưa watch() vào transaction?

Change stream là một long-lived aggregation cursor; **không tạo transaction kéo dài vô thời hạn để bọc cursor**. Chỉ business writes/projection/checkpoint có thể vào transaction ngắn nếu phù hợp.

### 20.3. Pseudocode giao dịch

```java
// Pseudocode: phần retry labels và document version
// phải bổ sung theo driver/version và business semantics.
ChangeStreamDocument<Document> event = cursor.tryNext();

if (event != null) {
    try (ClientSession session = client.startSession()) {
        session.withTransaction(() -> {
            applyProjection(session, event);
            persistCheckpoint(session, event.getResumeToken());
            return null;
        });
    }
}
```

Ứng dụng phải truyền `session` vào **mọi** MongoDB writes cùng transaction, cấu hình write/read concerns theo yêu cầu, xử lý `TransientTransactionError` và `UnknownTransactionCommitResult` theo driver docs.

Không gọi external API/email/payment **bên trong transaction retry callback**: callback có thể được thực thi lại, sinh side effects trùng mà MongoDB không rollback được.

### 20.4. Tính nhất quán không giải quyết mọi bài toán

Transaction chỉ đảm bảo atomicity của các writes **nằm trong cùng transaction**. Nó không biến:

- HTTP side effect,
- Kafka publish,
- email,
- payment,
- filesystem write,

thành thành phần của MongoDB transaction. Với các hệ đó, cân nhắc transactional outbox và idempotent delivery.

## 21. Quản trị tài nguyên change stream

### 21.1. Cursor giữ kết nối/tài nguyên

Mỗi active change stream sử dụng server-side cursor và các tài nguyên liên quan. Khi nhiều stream mở:

- Connection pool có thể bị chiếm.
- `getMore`/oplog processing tạo CPU/IOPS/aggregation cost.
- Mongos cần merge/coordinate streams trong sharded cluster.
- Kết nối bỏ quên có thể tăng cursor count và memory.
- Những consumers xử lý chậm tăng risk token hết history.

Không tạo một change stream per HTTP request hoặc per browser session.

### 21.2. `maxAwaitTime` và `batchSize`

```java
collection.watch()
    .maxAwaitTime(1, TimeUnit.SECONDS)
    .batchSize(100);
```

- `maxAwaitTime` là thời gian server chờ một lượt `getMore` để có batch.
- `batchSize` đặt gợi ý số documents trong batch, không bảo đảm mọi batch luôn đúng kích thước.
- Batch lớn có thể giảm round trips nhưng tăng peak memory và thời gian xử lý backlog.
- Batch nhỏ giúp phản ứng shutdown/metrics dễ hơn nhưng tăng overhead trong một số workload.

Không dùng `maxAwaitTime` làm timeout cho **business handler**; cần deadline riêng cho sink.

### 21.3. `fullDocument.UPDATE_LOOKUP` có chi phí

Lookup document hiện tại thêm I/O/cpu/cache và có thể tăng latency, nhất là dữ liệu lớn và updates dày. Nếu chỉ cần biết trường nào đổi, `updateDescription` có thể đủ.

Pre/post-images tăng storage/retention considerations. Không bật tất cả chỉ để có log đẹp.

### 21.4. Sharded cluster

Trong sharded cluster:

- Mở change stream qua `mongos`.
- Có chi phí merge kết quả và phối hợp các shards.
- Query pipeline, fullDocument lookup, topology changes ảnh hưởng latency.
- Events có thể đến từ nhiều shards và transactions; không suy luận thứ tự toàn cục chỉ từ client wall clock.
- History/removed shard ảnh hưởng resumability trong một số trường hợp.

Nếu cần strict ordering theo một business aggregate, thiết kế một partition/key/version và giới hạn writes/consumer tương ứng.

## 22. Quan sát hệ thống: metrics và alerts cho Java consumer

### 22.1. Một dashboard tối thiểu

```text
+------------------------------+--------------------------------+
| Consumer running / ownership | MongoDB change stream errors   |
+------------------------------+--------------------------------+
| Events received per second   | Events processed per second    |
+------------------------------+--------------------------------+
| Processing p95/p99 latency   | Checkpoint write latency      |
+------------------------------+--------------------------------+
| Checkpoint age / lag         | Oplog history window          |
+------------------------------+--------------------------------+
| Sink errors / DLQ backlog    | Reopened cursors / retries    |
+------------------------------+--------------------------------+
| Network/pool utilization     | CPU/RAM/disks of cluster       |
+------------------------------+--------------------------------+
| Source event volume          | Last successful shutdown      |
+------------------------------+--------------------------------+
```

### 22.2. Tên metric ví dụ do ứng dụng tự đặt

```text
mongo_change_stream_open
mongo_change_stream_events_received_total
mongo_change_stream_events_processed_total
mongo_change_stream_event_processing_seconds
mongo_change_stream_checkpoint_success_total
mongo_change_stream_checkpoint_failure_total
mongo_change_stream_checkpoint_age_seconds
mongo_change_stream_resume_attempts_total
mongo_change_stream_errors_total
mongo_change_stream_history_lost_total
mongo_change_stream_sink_errors_total
mongo_change_stream_shutdown_graceful_total
mongo_change_stream_shutdown_deadline_total
mongo_change_stream_consumer_leader
```

Đây là tên gợi ý cho Micrometer/Prometheus, **không phải các field MongoDB tự xuất đúng tên như vậy**.

### 22.3. Server metrics theo version

MongoDB 9.0 bổ sung một số metrics tại `serverStatus.metrics.changeStreams`, như:

- cursor đang mở;
- tổng cursors đã mở;
- lỗi resumable/non-resumable;
- `ChangeStreamHistoryLost` counts.

Trên các server cũ, những trường này có thể không tồn tại. Hãy kiểm tra version/tier, không coi `undefined` là 0.

```javascript
const s = db.serverStatus();
printjson(s.metrics?.changeStreams);
```

Thực hiện khi có quyền thích hợp. Đừng thu thập/log toàn bộ `serverStatus` mỗi giây; chọn metrics thật sự cần.

### 22.4. Lag không chỉ là thời gian giữa hai lần nhận event

Một stream có thể không có event suốt 5 giờ nhưng vẫn khỏe. `lastEventAt` cũ không tự đồng nghĩa consumer lag.

Phân biệt:

- **Stream liveness:** cursor còn active và có thể poll.
- **Checkpoint age:** thời gian từ lần xử lý/ghi token gần nhất.
- **Event processing lag:** now − event wallTime/clusterTime (đánh giá có giới hạn).
- **Backlog:** số event chờ hoặc tiến độ so với oplog tip.
- **Oplog retention headroom:** thời gian có thể dừng trước khi mất history.

Khi idle, có thể dùng highwatermark hợp lệ để thể hiện stream đã tiến thời gian, nhưng không checkpoint trước công việc còn pending.

### 22.5. Logging an toàn

Log nên có:

```json
{
  "consumer": "orders-projection-v1",
  "streamScope": "commerce.orders",
  "pipelineVersion": "v1",
  "operationType": "update",
  "eventKeyPrefix": "e4f87b8c",
  "attempt": 1,
  "handlerDurationMs": 54,
  "checkpointPersisted": true
}
```

Không log toàn bộ `fullDocument` có PII, access tokens, payment details hoặc raw resume tokens. Resume token là opaque metadata liên quan tiến độ; hạn chế truy cập và không đưa lên ticket công khai.

## 23. Runbook: consumer chậm và oplog window thu hẹp

### 23.1. Triệu chứng

```text
Source writes:        20,000 events/s
Consumer processed:     2,000 events/s
Checkpoint lag:          increasing
Oplog window:            4 hours -> 1 hour
```

Rủi ro: consumer không bắt kịp trước khi checkpoint cũ rơi khỏi oplog.

### 23.2. Các bước điều tra

1. Xác định streamKey, source namespace, pipeline version.
2. Kiểm tra last processed token/checkpoint, event rate, sink latency.
3. Kiểm tra application CPU/threads/pool/network.
4. Kiểm tra MongoDB cluster IOPS, replication lag, oplog window.
5. Đo tỉ lệ events bị filter và payload size.
6. Nếu bottleneck ở sink, throttle hoặc scale sink, tăng khả năng idempotent.
7. Nếu cần scale consumers, thiết kế partitioning/ordered checkpoint trước.
8. Nếu không thể bắt kịp, kích hoạt backfill/reconciliation plan.
9. Không tự bỏ token và “bắt đầu lại từ giờ hiện tại”.

### 23.3. Khắc phục theo nguyên nhân

| Root cause | Hướng xử lý |
| --- | --- |
| CPU Java handler | Tối ưu parse/business logic, batching có kiểm soát |
| HTTP sink slow | Idempotent async/outbox, retry budget, circuit breaker |
| MongoDB writes chậm | Query/index, replica/disk health, write concerns |
| Quá nhiều watcher scopes | Consolidate scopes hoặc hợp nhất filtering |
| Oplog window ngắn | Đánh giá cấu hình/disk capacity với DBA và giảm backlog |
| Đang chạy song song out-of-order | Ordered checkpoint frontier/fencing |
| Lỗi token invalid | Fail closed, snapshot/re-bootstrap |

## 24. Runbook: deploy gây xử lý lại sự kiện

### 24.1. Một ví dụ thời điểm crash

```text
T0: Worker nhận event A
T1: Sink ghi thành công
T2: SIGTERM
T3: Worker bị SIGKILL trước khi lưu token A
T4: New pod starts from token before A
T5: Event A được phát lại
```

Đây là hành vi dự kiến của **at-least-once**. Nếu sink upsert/dedup đúng, không tạo hiệu ứng nghiệp vụ trùng.

### 24.2. Khi nào đây là bug?

- Hai emails/charges được gửi vì sink không có idempotency.
- Token được checkpoint **trước** khi sink success, làm mất tác vụ.
- Old pod và new pod cùng cập nhật shared checkpoint không có fencing.
- Worker báo ready dù processing loop đã lỗi/đứng.
- Shutdown không chờ handler hoặc đóng MongoClient quá sớm.

### 24.3. Hướng xử lý

1. Kiểm checkpoint và logs theo event key.
2. Xác định sink có duplicate hay chỉ event được giao lại.
3. Nếu side effect bị lặp, bổ sung idempotency/business compensation.
4. Tăng deadline shutdown nếu handler thường lâu.
5. Nếu concurrency, đưa leader lease/fencing vào trước khi scale.
6. Thử SIGTERM, primary election, network error trong môi trường staging.

## 25. Runbook: invalidate khi collection drop/rename

### 25.1. Invalidate là điều kiện lifecycle

Collection change stream có thể nhận `invalidate` khi collection bị drop hoặc rename; database stream có thể nhận invalidate nếu database bị drop.

`invalidate` làm cursor kết thúc. Không nên coi đó là batch rỗng hoặc một insert/update bình thường.

### 25.2. Quyết định của ứng dụng

Khi nhận invalidate:

- Ghi nhận rõ namespace/event type.
- Dừng việc apply normal events.
- Đánh giá đây là maintenance/migration đã lên kế hoạch hay thao tác bất thường.
- Xem collection mới có cùng meaning/schema không.
- Nếu re-bootstrap/new source, theo protocol được phê duyệt.
- Nếu dùng `startAfter(invalidateToken)`, phải giữ token và đủ oplog history, cũng như scope phù hợp.
- Không tự retry `resumeAfter(invalidateToken)` vô hạn vì MongoDB không cho.

### 25.3. Khi đổi tên collection trong release

Một release blue/green có thể rename source collection. Dù application vẫn dùng tên cũ sau deploy, old collection stream có thể bị invalidate. Đừng ghép token từ old namespace với new namespace tùy tiện.

Nên version hóa streamKey và phối hợp cutover/backfill hoặc database-level watch theo thiết kế.

## 26. Runbook: lỗi không rõ kết quả khi ghi checkpoint

### 26.1. Case

Worker xử lý E42 thành công, gửi `replaceOne` checkpoint nhưng network timeout trước khi client nhận phản hồi.

Có thể:

- Checkpoint thực sự đã được server ghi, phản hồi bị mất.
- Checkpoint chưa được ghi.
- Ghi được primary nhưng write concern timeout chưa đạt điều kiện độ bền mong muốn.

### 26.2. Cách ứng xử

- Không xử lý ngay E43 nếu không biết checkpoint E42 đã bền theo contract.
- Read-back checkpoint bằng đường có consistency phù hợp.
- Nếu checkpoint đúng token E42 và side effect đã thành công, tiếp tục.
- Nếu checkpoint cũ, retry persist với **same token/streamKey** khi owner còn lease.
- Nếu trạng thái không rõ, fail closed để restart/replay idempotently.
- Không tự lưu token E43 để che lấp lỗi E42.

Với multi-instance, checkpoint writes phải có owner/fencing condition, tránh pod cũ ghi token cũ sau khi pod mới đã tiến xa hơn.

## 27. Lab có kiểm soát: tạo collection, chạy Java watcher, restart

### 27.1. Điều kiện

- MongoDB replica set/sharded test, không standalone.
- Java 17 và MongoDB Java Sync Driver version được xác minh.
- URI có quyền watch source collection và CRUD trong namespace lab.
- Không chạy change stream trên production chỉ để thử.
- Không drop database/test cluster.
- Không sửa oplog size hoặc cấu hình MongoDB.
- Chỉ dùng một active consumer instance cho cùng streamKey.

### 27.2. Tạo dữ liệu trong `mongosh`

Dùng database riêng:

```javascript
const lab = db.getSiblingDB("mongo_change_row395_lab");

const runId = "row395-" + new ObjectId().toHexString();
const sourceName =
  "events_" + runId.replace(/-/g, "_");

if (lab.getCollectionNames().includes(sourceName)) {
  throw new Error("Collection name đã tồn tại");
}

lab.createCollection(sourceName);

printjson({
  database: lab.getName(),
  sourceName,
  runId
});
```

Lưu `sourceName` và đặt:

```text
ROW395_SOURCE=<sourceName vừa tạo>
ROW395_CONSUMER=demo-v1
```

**Không thay `ROW395_SOURCE` sau khi restart** nếu muốn thấy resume token của cùng source. Chỉ một consumer active trên checkpoint `streamKey` đó.

### 27.3. Mở Java worker trước khi insert

Khởi động Java class trong một terminal sử dụng URI test và env variables. Đợi log báo `Change stream active`.

Terminal `mongosh` thứ hai:

```javascript
const lab = db.getSiblingDB("mongo_change_row395_lab");

// Điền chính xác sourceName/runId của lượt thử:
const coll = lab.getCollection(sourceName);

const docId = new ObjectId();

coll.insertOne({
  _id: docId,
  runId,
  kind: "order",
  status: "CREATED",
  version: 1
});

coll.updateOne(
  { _id: docId, runId, version: 1 },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);

coll.deleteOne({ _id: docId, runId });
```

Các writes phát sinh events với `insert`, `update` và `delete`. Java worker ghi inbox idempotent và checkpoint sau mỗi event.

**Lưu ý:** ví dụ Java chỉ ghi audit event vào `row395_processed_events`, không tạo real order projection; mục tiêu là minh họa đúng ordering checkpoint.

### 27.4. Dừng bằng SIGTERM hoặc CTRL+C

Dừng ứng dụng bằng cách kích hoạt shutdown bình thường của JVM/container. Quan sát:

```text
shutdown signal
    -> stopping=true
    -> tryNext poll returns
    -> cursor close
    -> client close
```

Với CTRL+C, JVM thường chạy shutdown hooks, nhưng thời điểm và tính chất phụ thuộc OS/container. **Không dùng SIGKILL làm cách dừng thông thường**.

### 27.5. Restart và xác minh checkpoint

Khởi động lại cùng:

- `MONGODB_URI`;
- `ROW395_SOURCE`;
- `ROW395_CONSUMER`;
- `pipeline-v1` không thay đổi.

Worker đọc checkpoint và gọi `resumeAfter(token)`. Nó không tự phát lại những events đã checkpoint; nếu crash trước checkpoint, sự kiện có thể được gửi lại và được dedup bằng event key.

Xem checkpoint (read-only):

```javascript
const ck = lab.getCollection("row395_change_checkpoints");

ck.find(
  {
    _id: {
      $regex: "^mongo_change_row395_lab:"
    }
  },
  {
    _id: 1,
    updatedAt: 1,
    resumeToken: 0
  }
).limit(20).toArray();
```

Không in raw token lên logs/ticket. Lọc bằng exact streamKey trong hệ thống nhiều consumers nếu có thể.

### 27.6. Test failure windows có chủ đích, nhưng không phá cluster

Trên staging:

1. Giả lập sink failure trước khi `storeToken` (mẫu code có thể inject exception).
2. Xác minh token chưa tiến.
3. Restart worker cùng key.
4. Xác minh event được giao lại.
5. Xác minh `processedEvents` không tạo trùng nếu đã được ghi trước crash.
6. Thử stop khi stream idle.
7. Thử stop trong lúc handler chậm bằng fake sink có timeout.
8. Thử lỗi mạng với điều kiện được đội hạ tầng cho phép, không kill production primary.

Đừng cố chờ oplog mất lịch sử trên dữ liệu thật để test `ChangeStreamHistoryLost`; có thể dùng test fixture hoặc môi trường cô lập.

### 27.7. Cleanup có kiểm soát

Kết thúc bài, **dừng Java worker trước**, tránh nó nhận thêm delete events do cleanup.

Trong `mongosh`:

```javascript
// Chỉ trên sourceName/runId của lượt thử:
const owned = coll.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

for (const item of owned) {
  coll.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + coll.countDocuments({ runId }));
```

Checkpoint và processed-events ledger được giữ để minh họa restart/resume. Người quản lý lab có thể dọn các documents **thuộc streamKey của lượt thử** theo chính sách, nhưng không drop database hoặc xóa toàn bộ checkpoint của consumers khác.

Nếu muốn xóa source collection ngẫu nhiên sau lab, cần xác minh nó là **namespace riêng hoàn toàn**, worker đã dừng, không còn consumer tham chiếu. Drop sẽ phát invalidate nếu còn watchers; không thực hiện drop như một “bước cleanup tự động” thiếu điều kiện.

## 28. Security và vận hành

### 28.1. Tối thiểu hóa quyền

Một change stream worker nên có:

- quyền watch/read source scope cần thiết;
- quyền ghi chỉ vào sink/registry/checkpoint phù hợp;
- không có quyền drop collection/đổi role;
- nếu cần pre-images/fullDocument, đánh giá quyền bổ sung;
- credential riêng, rotation và audit;
- network/TLS bảo vệ đường truyền.

Không dùng tài khoản admin toàn cluster cho một service chỉ cần theo dõi một collection.

### 28.2. Dữ liệu nhạy cảm trong events

Change events có thể chứa field values trong `fullDocument`/`updateDescription`. Pipeline, logs, metrics và sink đều phải áp dụng PII masking và authorization.

Resume token không nên được sửa hoặc lộ trong URL public. Dù nó không phải mật khẩu KMS, nó có giá trị về vị trí/metadata và cần quyền truy cập phù hợp.

### 28.3. Backups cho checkpoint

Nếu mất checkpoint nhưng source vẫn còn dữ liệu, bạn **không tự biết** đã xử lý tới event nào, trừ khi có durable inbox/projection logs hoặc một protocol khôi phục.

Nên backup:

- checkpoint collection;
- sink/inbox ledger;
- source data/backfill artifacts;
- config pipeline version và stream scope;
- audit logs/ownership leases.

Khi restore, đảm bảo checkpoint và sink không lệch thời điểm theo cách làm mất events. Một checkpoint “mới hơn” sink đã restore là nguy hiểm: resumeAfter có thể bỏ qua những side effects chưa nằm trong sink được phục hồi. Cần recovery protocol và kiểm tra consistency.

### 28.4. Multi-region / failover

Sau primary election, client có thể phải resume trên member mới. MongoDB 9.0 có thay đổi về read preference enforcement khi node đổi vai trò, trả resumable error trong một số trường hợp; driver hiện đại xử lý theo specification.

Không hardcode “cứ pin connection tới primary IP X” khi replica set có thể elect member khác. Sử dụng connection string replica set/seedlist hoặc SRV do môi trường cung cấp.

## 29. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`watch()` chạy trên standalone MongoDB” | Cần replica set/sharded cluster tương thích |
| “Stream mới tự gửi toàn bộ documents cũ” | Chỉ có changes từ điểm bắt đầu; cần backfill |
| “`documentKey._id` chính là resume token” | Resume token là `changeEvent._id` |
| “`clusterTime` đủ để checkpoint mọi event” | Token đầy đủ mới là resume cursor position |
| “Có thể tự sửa nội dung `_data` token” | Token opaque; giữ nguyên BSON |
| “Pipeline bỏ `_id` để giảm payload cũng được” | Có thể gây lỗi và phá resumability |
| “`resumeAfter` dùng được sau invalidate” | Dùng `startAfter` theo policy nếu muốn theo dõi tiếp |
| “`startAfter` luôn sửa được token hết hạn” | Vẫn cần oplog history |
| “Token đã lưu tồn tại vĩnh viễn” | Oplog history hữu hạn |
| “`tryNext()` chắc chắn không block” | Có thể chờ getMore/network |
| “`maxAwaitTime` là deadline cho HTTP sink” | Chỉ liên quan server await getMore |
| “`cursor.getResumeToken()` luôn tương đương công việc đã xử lý” | Có thể chứa postBatch/highwatermark/đi trước side effects |
| “Cứ checkpoint khi nhận event là xong” | Có thể bỏ mất side effect nếu crash |
| “Checkpoint sau xử lý có nghĩa exactly-once” | Có cửa sổ replay; sink cần idempotency |
| “Driver auto-resume nghĩa không cần durable checkpoint” | Token trong RAM không sống qua process restart |
| “Driver tự retry mãi” | Chỉ các errors hợp lệ và theo retry rules |
| “Mất oplog có thể mở stream từ hiện tại mà không mất gì” | Có gap; phải re-bootstrap/reconcile |
| “`updateLookup` là chính xác state ngay lúc update event” | Có thể là document hiện tại về sau |
| “Delete event luôn có `fullDocument`” | Thường chỉ có `documentKey`, pre-image cần config |
| “Nhiều pods tự chia events thành consumer group” | Mỗi watcher có thể nhận cùng events |
| “Checkpoint của pods ghi đồng thời vẫn an toàn” | Có race; cần leader/fencing/ordered commit |
| “Xử lý E12 xong có thể checkpoint dù E10 chưa xong” | Có thể bỏ qua E10 khi resume |
| “Close MongoClient ngay khi SIGTERM là graceful” | Có thể ngắt handler/checkpoint giữa chừng |
| “SIGTERM hook luôn chạy khi OOM/SIGKILL” | Không bảo đảm |
| “Stop flag bảo đảm socket call kết thúc đúng 1 giây” | Network timeouts còn ảnh hưởng |
| “Có thể đổi pipeline mà reuse token vô điều kiện” | Pipeline/options phải tương thích |
| “Event được ghi từ sink cùng database không ảnh hưởng watch” | Nếu watch toàn database, có thể tạo feedback loop |
| “Checkpoint timestamp là thời gian source event” | Là thời điểm consumer persist |
| “No events 5 giờ nghĩa watcher lag” | Có thể stream idle bình thường |
| “Mất checkpoint chỉ cần lấy token mới nhất từ server” | Có nguy cơ bỏ qua events cần xử lý |
| “Change stream thay thế authorization và retention” | Cần RBAC, backfill và governance riêng |

## 30. Bài tập thực hành

### Bài A — Xác định resume token

Event:

```javascript
{
  _id: { _data: "826..." },
  operationType: "update",
  documentKey: { _id: ObjectId("66a000000000000000000395") },
  clusterTime: Timestamp({ t: 1794630000, i: 1 })
}
```

1. Field nào là resume token?
2. Tại sao không lấy `documentKey._id`?
3. Tại sao `clusterTime` không đủ?
4. Có nên in nguyên token vào HTTP response không?

### Bài B — Thứ tự lưu checkpoint

```text
Event E7 -> gửi email -> lưu token T7
```

Nếu crash sau khi email gửi thành công, trước khi lưu token, điều gì xảy ra? Cần idempotency key và phương án dedup ở đâu?

### Bài C — Lỗi mất sự kiện

```text
Event E8 -> lưu token T8 -> call payment API -> crash
```

1. Tại sao E8 có thể bị bỏ qua?
2. Sắp xếp lại thứ tự xử lý.
3. Nếu payment API timeout sau khi đã charge, cách retry nào an toàn?
4. Change stream có tự rollback charge không?

### Bài D — `tryNext()` và shutdown

Viết pseudocode Java:

- AtomicBoolean stop.
- Loop `cursor.tryNext()`.
- `maxAwaitTime(2, SECONDS)`.
- Xử lý từng event đồng bộ.
- Lưu token sau sink.
- `try-with-resources`.
- Shutdown hook đợi có timeout.

Giải thích vì sao `client.close()` không nên là lệnh đầu tiên trong hook.

### Bài E — Resume sau invalidate

Một collection bị rename, watcher nhận invalidate.

1. Có dùng `resumeAfter(invalidateToken)` không?
2. Có thể dùng `startAfter` trong trường hợp nào?
3. Có cần verify collection mới/schema/business ownership không?
4. Nếu token đã rơi khỏi oplog, xử lý ra sao?

### Bài F — Oplog history

```text
Oplog window lúc bình thường: 24 giờ
Oplog window lúc peak:        4 giờ
Consumer down:                7 giờ
```

1. Rủi ro gì khi restart?
2. Có thể tự bỏ token để tiếp tục từ hiện tại không?
3. Cần alert/capacity nào?
4. Re-bootstrap thế nào để không tạo gap mới?

### Bài G — Nhiều pods

Hai pods `A` và `B` dùng cùng `streamKey`. B xử lý E10, E11 nhanh; A xử lý E10 chậm rồi ghi checkpoint cũ.

1. Điều gì có thể xảy ra với token?
2. Lease chỉ có `leaseUntil` có đủ không?
3. Fencing token nên kiểm ở đâu?
4. Cần architecture khác nếu muốn scale throughput?

### Bài H — Pipeline change

Consumer v1 lọc `insert/update`, v2 chỉ muốn `status:"PAID"`.

1. Vì sao không nên reuse resume token v1 vô điều kiện?
2. Pipeline có được bỏ `_id` không?
3. Version checkpoint cần chứa gì?
4. Migration backfill/shadow consumer ra sao?

### Bài I — Update lookup

```text
T1: status = PAID
T2: status = REFUNDED
T3: handle T1 event with UPDATE_LOOKUP
```

1. `fullDocument.status` có thể là gì?
2. `updateDescription` có thể giúp gì?
3. Nếu cần exact business event, thiết kế outbox thế nào?

### Bài J — At-least-once với sink MongoDB

Thiết kế collection `processed_events`:

- Unique `_id` theo event token hash + consumer.
- Upsert `$setOnInsert`.
- Checkpoint sau sink.
- Recovery khi crash bất kỳ bước nào.

Giải thích tại sao vẫn phải xử lý write concern timeout và token race.

### Bài K — Bootstrap snapshot

Source có 5 triệu documents, projection mới đang trống.

1. Vì sao `find()` xong rồi `watch()` có gap?
2. Tạo start point/stream trước snapshot giúp gì?
3. Oplog window phải bao phủ khoảng nào?
4. Làm sao xác minh projection đã catch up?

### Bài L — Spring Boot lifecycle

Một bean dùng `@PostConstruct` để chạy `watch().forEach()` trên main thread.

1. Vì sao app có thể treo startup?
2. Dùng executor/`SmartLifecycle` như thế nào?
3. Đặt readiness theo consumer health ra sao?
4. Khi context close, thứ tự dừng consumer và đóng client nên thế nào?

### Bài M — Metrics

Thiết kế dashboard có ít nhất 6 metric. Phân biệt:

- stream is idle;
- handler backlog;
- sink lỗi;
- token hết history;
- cursor bị reopen liên tục;
- shutdown không kịp grace period.

### Bài N — Transactional checkpoint

Nếu projection và checkpoint cùng ở MongoDB:

1. Transaction sẽ bao gồm những writes nào?
2. Có đưa `watch()` vào transaction không?
3. Nếu callback transaction retry, có được gửi email trong đó không?
4. Với external sink, giải pháp outbox/idempotency nào phù hợp?

## 31. Tài liệu tham khảo chính thức

Khi dùng trong production, đối chiếu **đúng server version, topology, FCV, Java Driver version, Java runtime và framework**:

- [Open Change Streams — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — `watch()`, filters, `MongoChangeStreamCursor`, pre/post-images, synchronous cursor behavior.
- [MongoDB Change Streams — Server Manual](https://www.mongodb.com/docs/manual/changestreams/) — availability, oplog history, resume token, resume/start semantics, sharded clusters.
- [`$changeStream` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changestream/) — options `resumeAfter`, `startAfter`, `startAtOperationTime`, `fullDocument` và expanded events.
- [Java Sync Driver `ChangeStreamIterable` API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/driver-sync/com/mongodb/client/ChangeStreamIterable.html) — overloads, `maxAwaitTime`, `batchSize`, resume options.
- [Java Sync Driver `MongoChangeStreamCursor` API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/driver-sync/com/mongodb/client/MongoChangeStreamCursor.html) — `tryNext()`, `getResumeToken()`, lifecycle, thread-safety.
- [Java Driver Change Stream Examples](https://github.com/mongodb/mongo-java-driver/blob/main/driver-sync/src/examples/documentation/ChangeStreamSamples.java) — official examples of resume token and watch behavior.
- [Change Streams Specification](https://github.com/mongodb/specifications/blob/master/source/change-streams/change-streams.md) — driver resumable error rules và cập nhật cached/postBatch token.
- [`invalidate` event](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/) — drop/rename/dropDatabase và `startAfter`.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — cách suy nghĩ về oplog size/window.
- [`rs.printReplicationInfo()`](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/) — thông tin replication history.
- [Transactions in Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — transaction retry/callback và atomic checkpoint khi phù hợp.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — lựa chọn độ bền cho checkpoint và sink.
- [MongoDB `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — số liệu server; change stream metrics ở các version mới.
- [MongoDB Drivers Compatibility](https://www.mongodb.com/docs/drivers/) — lựa chọn phiên bản driver/client tương thích.

**Ghi chú phiên bản:** ví dụ Java dùng API của dòng Java Sync Driver 5.x. Tính năng `showExpandedEvents`, pre/post-images, một số change stream/serverStatus metrics và điều kiện resume trong election có thể thay đổi theo phiên bản MongoDB; không coi mọi feature là có trên mọi cluster. Những code skeleton Spring/retry/outbox phải được hoàn thiện theo deployment và error handling thực tế trước khi dùng production.

## 32. Kết luận

Một consumer Java dùng MongoDB change streams chỉ đáng tin khi quản lý đồng thời **event semantics, tiến độ và lifecycle**:

1. **`watch()`** cho phép theo dõi thay đổi trên collection/database/deployment tương thích, nhưng không tự gửi snapshot của dữ liệu cũ.
2. **Resume token** là BSON opaque trong `changeEvent._id`; lưu nguyên vẹn, dùng `resumeAfter()` để tiếp tục sau event đã checkpoint. `startAfter()` phục vụ tình huống đặc biệt như sau invalidate; `startAtOperationTime()` cần timestamp hợp lệ còn trong oplog.
3. **Side effect trước, checkpoint sau** để tránh đánh dấu thành công trước khi nghiệp vụ hoàn tất. Crash giữa hai bước có thể phát lại event — hãy dùng idempotency.
4. **`tryNext()` + stop flag + try-with-resources** tạo nền tảng dừng có kiểm soát, nhưng phải cộng thời gian cho network, handler và orchestrator deadline.
5. **Driver auto-resume** chỉ xử lý những lỗi được hỗ trợ, không thay durable checkpoint hoặc recovery khi token rơi khỏi oplog.
6. **Một streamKey cần ownership rõ**, nhất là khi chạy nhiều pods. Không cho consumer xử lý out-of-order ghi checkpoint vượt qua events chưa hoàn tất.
7. **Giám sát oplog window, event lag, sink errors, checkpoint age và shutdown** để phát hiện dữ liệu có nguy cơ bị bỏ sót trước khi quá muộn.
8. **Mất history hoặc thay pipeline** đòi hỏi re-bootstrap/reconciliation, không âm thầm “watch từ hiện tại”.

**Nguyên tắc cốt lõi:** hãy coi resume token là **cam kết về những thay đổi mà hệ thống đã xử lý bền vững**, không chỉ là vị trí MongoDB đã trả qua network. Dừng ứng dụng đúng cách giúp giảm replay; còn idempotency, checkpoint và recovery plan mới bảo đảm thay đổi dữ liệu được xử lý đáng tin cậy khi có crash, deploy, failover hoặc gián đoạn kéo dài.
