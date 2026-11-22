# Thông báo thay đổi: Change Streams, xử lý lặp và khôi phục người tiêu thụ trong MongoDB

## 1. Bài toán thiết kế ứng dụng

Một hệ thống đặt hàng lưu tài liệu trong collection `orders`. Khi đơn hàng được tạo hoặc cập nhật, ứng dụng cần:

- Cập nhật collection `orderReadModels` để phục vụ truy vấn nhanh.
- Gửi thông báo trạng thái đến người dùng.
- Đồng bộ dữ liệu sang công cụ tìm kiếm.
- Cập nhật cache hoặc dữ liệu phân tích.
- Tiếp tục xử lý chính xác về mặt nghiệp vụ khi consumer mất kết nối, server đổi primary hoặc process khởi động lại.

Cách đơn giản nhưng thiếu an toàn là ghi MongoDB rồi tự gọi một API khác:

```java
orders.insertOne(order);
notificationApi.send(order);
```

Nếu `insertOne` thành công nhưng process crash trước `send`, sự kiện không được gửi. Nếu `send` thành công rồi response timeout, request có thể bị retry và gửi trùng.

MongoDB **Change Streams** cho phép ứng dụng theo dõi những thay đổi được ghi nhận trong database và xử lý chúng theo cơ chế consumer dài hạn.

```text
                       MongoDB Replica Set
                                |
              Primary writes --> oplog
                                |
                                v
                     Change Stream cursor
                                |
                                v
                     Consumer Java Worker
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
       Read model           Search index        Notification
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                    Durable checkpoint
                     (resume token)
```

**Tuy nhiên:** Change Stream không tự cung cấp đúng một lần xử lý business side effect. Consumer có thể thấy lại sự kiện sau lỗi hoặc restart. Cần chủ động thiết kế **idempotency, checkpoint, retry, recovery và observability**.

> **Nguyên tắc xuyên suốt:** xử lý xong thay đổi rồi mới ghi checkpoint; chấp nhận có thể đọc lại thay đổi và thiết kế để việc đọc lại không gây tác dụng phụ nguy hiểm.

---

## 2. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích Change Streams và vai trò của oplog trong kiến trúc notification.
2. Tạo consumer bằng MongoDB Java Sync Driver.
3. Phân biệt sự kiện thay đổi database với sự kiện nghiệp vụ.
4. Xử lý insert, update, replace, delete và các tình huống invalidate.
5. Dùng `resumeAfter`, `startAfter`, `startAtOperationTime` đúng ngữ cảnh.
6. Lưu resume token bền vững mà không làm mất thông tin BSON.
7. Nhận diện at-least-once delivery, duplicate events và ambiguous outcomes.
8. Thiết kế consumer có idempotency ở target MongoDB hoặc external service.
9. Gắn checkpoint với xác nhận side effect, cân nhắc transaction khi thích hợp.
10. Khởi động lại consumer sau sự cố network/election, nhận diện oplog history lost.
11. Bootstrap read model từ dữ liệu cũ mà không tạo khoảng trống giữa snapshot và stream.
12. Thiết kế hàng đợi, worker ownership, thứ tự xử lý, retries và metrics.
13. Kiểm thử lỗi trước/sau checkpoint và điều kiện khôi phục.

---

## 3. Change Streams là gì?

**Change Stream** là API MongoDB cho phép ứng dụng theo dõi những thay đổi đã được commit và có thể quan sát theo các đảm bảo của deployment, thay vì liên tục chạy query xem có document nào mới.

Ví dụ:

```javascript
use sales;

const stream = db.orders.watch();

while (stream.hasNext()) {
  printjson(stream.next());
}
```

Ứng dụng có thể nhận các thay đổi như:

- `insert` khi một document mới được tạo.
- `update` khi một số fields được cập nhật.
- `replace` khi document bị thay thế.
- `delete` khi document bị xóa.
- Các loại event khác, trong đó có drop/rename/invalidate tùy phạm vi stream, phiên bản và cấu hình.

### 3.1. Điều kiện triển khai

Change Streams sử dụng cơ chế replication history và cần triển khai MongoDB hỗ trợ tính năng này, thông thường là:

- **Replica set**.
- **Sharded cluster**.

Một standalone `mongod` thông thường không phải môi trường phù hợp để mở Change Stream. Khi test cục bộ, dùng single-node replica set hoặc Testcontainers cấu hình replica set.

### 3.2. Change Stream không phải queue bền vững vô hạn

Consumer resume dựa trên lịch sử còn giữ trong oplog hoặc các điều kiện change history được server hỗ trợ. Khi history quá cũ bị loại, một resume token có thể không còn sử dụng được.

### 3.3. Change Stream không thay thế hoàn toàn domain event

Một thay đổi:

```javascript
{ $set: { status: "PAID" } }
```

cho biết **dữ liệu được cập nhật**, chưa chắc mô tả đầy đủ nghiệp vụ:

- Thanh toán đã được ngân hàng xác nhận?
- Có phải cập nhật lại để sửa lỗi?
- Có nên gửi email lần nữa?
- Ai thực hiện và có cần audit?
- Có phải dữ liệu được backfill?

Nếu cần sự kiện nghiệp vụ bất biến, thứ tự chính xác và replay lâu dài, cân nhắc **transactional outbox** hoặc event log được thiết kế riêng.

---

## 4. Kiến trúc consumer cơ bản

```text
Client/API
    |
    v
MongoDB orders collection
    |
    v
Change Stream
    |
    v
Single reader / dispatcher
    |
    +--> Validate event schema
    |
    +--> Deduplicate / check processing state
    |
    +--> Apply side effect
    |
    +--> Persist durable checkpoint
    |
    v
Read next event
```

Một consumer cần có những thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| Stream definition | Xác định collection/database/deployment và pipeline |
| Reader | Đọc event qua cursor |
| Event decoder | Phân biệt operation types, document key, full document |
| Handler | Xử lý thay đổi theo nghiệp vụ |
| Idempotency store | Ngăn tác dụng phụ lặp nguy hiểm |
| Checkpoint store | Lưu resume token đã xử lý |
| Retry policy | Phân loại lỗi tạm thời và lỗi không thể tiếp tục |
| Owner/lease | Tránh hai instances cùng xử lý một logical stream ngoài ý muốn |
| Metrics/alerting | Theo dõi lag, errors, checkpoint age, backlog |
| Recovery procedure | Khôi phục cursor, resnapshot hoặc replay khi mất history |

Không nên chỉ viết một `while (cursor.hasNext())` rồi xem như đã giải quyết toàn bộ bài toán reliable notification.

---

## 5. Phạm vi theo dõi: collection, database, deployment

MongoDB cho phép watch ở các scope khác nhau.

### 5.1. Collection scope

```javascript
db.orders.watch();
```

Phù hợp khi chỉ cần events của `orders`.

### 5.2. Database scope

```javascript
db.watch();
```

Theo dõi các collections được hỗ trợ trong database, subject to quyền và options.

### 5.3. Deployment scope

Ở `mongosh`, có thể theo dõi ở mức deployment thông qua API `Mongo` phù hợp; Java Driver có `MongoClient.watch()`.

```java
MongoClient client = MongoClients.create(uri);

var deploymentStream = client.watch();
```

Scope rộng hơn làm số events, quyền truy cập, tài nguyên và logic lọc phức tạp hơn.

### 5.4. Chọn scope theo consumer ownership

Nếu chỉ xây `orderReadModels`, ưu tiên watch `orders` thay vì nghe mọi database rồi lọc trong Java. Tuy nhiên nếu một workflow cần quan sát thay đổi ở nhiều collections, database/deployment scope có thể phù hợp hơn.

---

## 6. Cấu trúc event

Một Change Stream event có thể trông như sau:

```javascript
{
  _id: {
    _data: "82691A..."
  },
  operationType: "update",
  clusterTime: Timestamp({ t: 1794662400, i: 1 }),
  ns: {
    db: "sales",
    coll: "orders"
  },
  documentKey: {
    _id: ObjectId("691800000000000000000001")
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

Các fields quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| `_id` ở cấp event | **Resume token**, không phải document ID |
| `operationType` | Kiểu thay đổi |
| `clusterTime` | BSON Timestamp liên quan vị trí thay đổi, không phải wall clock thông thường |
| `ns` | Database/collection |
| `documentKey` | Khóa xác định document bị thay đổi |
| `fullDocument` | Có thể có document sau thay đổi theo option, nhưng không luôn tồn tại |
| `updateDescription` | Thông tin fields được cập nhật/xóa trong update |
| `lsid`, `txnNumber` | Một số metadata liên quan session/transaction |
| `wallTime` | Thời gian theo đồng hồ thực khi server cung cấp |

### 6.1. Phân biệt hai `_id`

```javascript
event._id              // opaque resume token
event.documentKey._id  // business document key
```

Không dùng `documentKey._id` làm vị trí resume của Change Stream; nó không chứa thông tin thứ tự của tất cả changes.

### 6.2. Không phân tích token bằng cách tách chuỗi `_data`

Token là BSON opaque. Format có thể thay đổi theo server version và topology. Ứng dụng chỉ lưu nguyên giá trị và gửi lại qua API resume.

### 6.3. Không chỉ dựa vào `clusterTime`

Nhiều events, đặc biệt trong transaction, có thể chia sẻ timestamp. Dùng `clusterTime` đơn lẻ để checkpoint có thể bỏ sót các events khác cùng timestamp. Resume token là lựa chọn chính khi đã có.

---

## 7. Event được phát hành sau thay đổi có majority visibility

MongoDB Change Streams theo dõi những thay đổi được commit theo semantics replication và có thể quan sát trong majority-committed history. Đây là ưu điểm so với tự tail một collection theo read preference không kiểm soát.

Nhưng đừng suy ra:

- Event được gửi tới consumer **đúng một lần**.
- Downstream đã nhận event ngay khi database write thành công.
- Không có network delay.
- Notification external sẽ thành công.
- Có một thời gian cố định giữa write và callback.
- Dữ liệu ở mọi secondary đều đã bắt kịp cùng thời điểm.

**Majority persistence của source và end-to-end side-effect delivery là hai bảo đảm khác nhau.**

---

## 8. Java Sync Driver: chuẩn bị kết nối

Giả sử project đã có dependency `org.mongodb:mongodb-driver-sync` tương thích Java runtime/server.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class AppBootstrap {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("sales");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            // Open a Change Stream in a managed worker.
        }
    }
}
```

Connection string nên liệt kê replica set seeds hoặc dùng cơ chế SRV được cấu hình đúng, kèm TLS/auth/replicaSet khi cần.

`MongoClient` thường sống theo vòng đời process; **mỗi consumer cursor có vòng đời riêng**. Không mở/đóng một MongoClient sau mỗi event.

---

## 9. Consumer tối thiểu bằng MongoChangeStreamCursor

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

public final class SimpleOrderConsumer {

    public static void consume(
            MongoCollection<Document> orders
    ) {
        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 orders.watch()
                     .fullDocument(FullDocument.UPDATE_LOOKUP)
                     .cursor()) {

            while (cursor.hasNext()) {
                ChangeStreamDocument<Document> event =
                    cursor.next();

                System.out.println(
                    event.getOperationType()
                );
                System.out.println(
                    event.getDocumentKey()
                );
            }
        }
    }
}
```

### 9.1. Mẫu này chỉ để học API

Chưa có durable checkpoint, idempotency, shutdown, retry, history-loss detection và downstream error handling.

### 9.2. `hasNext()` có thể block

Change Stream là một stream đang chờ sự kiện mới. Khi chưa có changes, gọi `hasNext()` có thể block để đợi dữ liệu.

### 9.3. Đóng cursor chủ động

`try-with-resources` bảo đảm `close()` khi worker kết thúc hoặc throw exception. Một service dài hạn cần thêm stop signal/cancellation để không phải chờ vô hạn khi shutdown.

---

## 10. `tryNext()` và `maxAwaitTime` cho worker có thể dừng

Một vòng lặp service thường cần kiểm tra cờ shutdown định kỳ:

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.Document;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class PollingConsumer {

    private final AtomicBoolean running =
        new AtomicBoolean(true);

    public void stop() {
        running.set(false);
    }

    public void run(MongoCollection<Document> orders) {
        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 orders.watch()
                     .maxAwaitTime(
                         2, TimeUnit.SECONDS
                     )
                     .cursor()) {

            while (running.get()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    // Chưa có event ở lần poll này.
                    continue;
                }

                process(event);
            }
        }
    }

    private void process(
            ChangeStreamDocument<Document> event
    ) {
        // Business handler.
    }
}
```

### 10.1. `null` không có nghĩa “stream đã hết vĩnh viễn”

`tryNext()` có thể trả `null` khi batch tạm thời không có event. Đừng coi đó là điều kiện `COMPLETED`.

### 10.2. `maxAwaitTime` không phải timeout tổng của job

Nó ảnh hưởng thời gian server chờ trong những lời gọi await/getMore phù hợp. Application vẫn cần:

- Timeout kết nối/operation được cấu hình.
- Deadline cho downstream calls.
- Shutdown signal.
- Retry/backoff.
- Kiểm tra consumer health.

### 10.3. Tránh busy-spin

Nếu `tryNext()` trả `null` quá nhanh theo cấu hình hoặc sự cố, vòng lặp có thể tốn CPU. Có thể dùng backoff ngắn/điều chỉnh maxAwaitTime phù hợp, nhưng không biến poll thành retry vô hạn sau lỗi nghiêm trọng.

---

## 11. ChangeStreamIterable và pipeline lọc event

Ví dụ chỉ nhận các thay đổi đơn hàng:

```javascript
[
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]
```

Java Sync Driver:

```java
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;

import java.util.List;

List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.in(
            "operationType",
            "insert",
            "update",
            "replace",
            "delete"
        )
    )
);

try (var cursor =
         orders.watch(pipeline).cursor()) {
    while (cursor.hasNext()) {
        handle(cursor.next());
    }
}
```

### 11.1. Lọc trên server giúp giảm traffic

Nếu bạn chỉ quan tâm đến `status`, có thể lọc các event fields được hỗ trợ bằng pipeline hợp lệ, nhưng cần xem behavior của updateDescription và fullDocument.

### 11.2. Không tùy ý loại `_id` của event

`_id` cấp event chứa **resume token**. Một pipeline thay đổi/loại token có thể khiến stream không thể resume hoặc bị server từ chối. Không `$project: {_id: 0}` trong Change Stream chỉ để giảm payload.

### 11.3. Pipeline là một phần của checkpoint contract

Nếu đổi filter từ “chỉ inserts” sang “inserts + updates”, resume từ token cũ có thể **không tạo lại những updates đã bị lọc bỏ trước đó**. Lưu `pipelineVersion`, `consumerName`, scope và options bên cạnh token; khi thay logic có thể cần rebootstrap.

---

## 12. Phân biệt các operationType

| Type | Ý nghĩa | Cách xử lý thông thường |
| --- | --- | --- |
| `insert` | Document được tạo | Tạo projection hoặc gửi event tương ứng |
| `update` | Một phần document thay đổi | Dùng updateDescription hoặc lookup theo yêu cầu |
| `replace` | Document bị thay hoàn toàn | Thay projection theo dữ liệu mới |
| `delete` | Document bị xóa | Xóa/đánh dấu tombstone tại target |
| `drop` | Collection bị drop | Dừng, kiểm tra namespace ownership |
| `rename` | Collection đổi tên | Xử lý mapping/scope |
| `invalidate` | Stream không còn hiệu lực theo scope | Dừng/resubscribe theo policy |
| Event types mới | Phụ thuộc MongoDB release | Phân loại rõ, không im lặng bỏ qua |

Không phải mọi event type xuất hiện ở mọi scope/version. Với production consumer, có chính sách rõ cho loại event không được hỗ trợ thay vì chỉ `default: return;`.

---

## 13. Xử lý `insert`

Với insert event, `fullDocument` thường chứa document được insert.

```java
if (event.getOperationType()
        == OperationType.INSERT) {

    Document document = event.getFullDocument();

    if (document == null) {
        throw new IllegalStateException(
            "Missing insert fullDocument"
        );
    }

    indexOrder(document);
}
```

### 13.1. Một insert không nhất thiết là “business order created” duy nhất

Migration hoặc data repair scripts cũng có thể insert documents. Nếu nghiệp vụ cần thông báo đơn hàng mới, event handler phải kiểm tra domain state/intent và idempotency, hoặc nhận sự kiện nghiệp vụ từ transactional outbox.

### 13.2. Không gửi email trực tiếp trước khi có chính sách retry

Nếu consumer gọi email rồi crash trước checkpoint, insert event có thể được đọc lại. Phải dùng email idempotency key, delivery ledger hoặc outbox trước khi triển khai.

---

## 14. Xử lý `update`: patch hay full document?

Một update:

```javascript
db.orders.updateOne(
  { _id: "O100" },
  { $set: { status: "PAID" } }
);
```

có thể tạo event:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O100" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

### 14.1. Khi dùng updateDescription

Phù hợp khi bạn thực sự muốn xử lý patch và hiểu nested paths, array changes, removed fields, truncated arrays và event schema của MongoDB version đang sử dụng.

### 14.2. Đừng xử lý patch bằng phép cộng không idempotent

Nếu patch tương đương “tăng counter thêm 1” mà event bị replay, cộng lại một lần nữa gây sai số.

### 14.3. Khi dùng fullDocument

Nếu consumer xây read model hiện trạng của order, có thể lấy document đầy đủ theo option phù hợp rồi `replaceOne` bằng ID. Nhưng cần xem rủi ro race và ordering ở phần sau.

---

## 15. `fullDocument: UPDATE_LOOKUP` không phải exact historical after-image

Java:

```java
orders.watch()
    .fullDocument(FullDocument.UPDATE_LOOKUP)
    .cursor();
```

Server có thể lookup **trạng thái hiện tại** của document khi xử lý update, thay vì một immutable after-image đúng thời điểm event xảy ra.

Ví dụ:

```text
T1: order.status = NEW
T2: update status = PAID
T3: update status = REFUNDED
T4: consumer xử lý event ở T2
```

`fullDocument` của event T2 với `UPDATE_LOOKUP` có thể chứa `REFUNDED` nếu lookup diễn ra sau T3.

### 15.1. `fullDocument` có thể null

Nếu document bị xóa trước khi lookup, field có thể không có. Không hiểu `null` là một `delete` event; phải nhìn `operationType` và business policy.

### 15.2. Phân biệt state replication và event sourcing

- **State replication:** chỉ cần target cuối cùng phản ánh trạng thái mới nhất. Lookup hiện tại có thể hữu ích nếu bảo vệ ordering.
- **Event sourcing/business audit:** cần các transitions được ghi lại chính xác tại từng sự kiện. `UPDATE_LOOKUP` có thể không đáp ứng điều này; nên dùng domain events/outbox hoặc pre/post image theo yêu cầu.

---

## 16. Pre-images và post-images

MongoDB các phiên bản hỗ trợ tính năng **Change Stream pre- and post-images** khi collection bật cấu hình thích hợp.

Ý tưởng:

- **Pre-image:** document trước khi thay đổi.
- **Post-image:** document sau khi thay đổi.
- Consumer có thể yêu cầu images khi chúng tồn tại.
- Availability phụ thuộc MongoDB Server version, collection config và image retention.
- Không mặc định mọi event đều có images.
- Khi cấu hình yêu cầu image bắt buộc nhưng không có, stream có thể báo lỗi theo semantics API.

### 16.1. Lợi ích

- So sánh old/new state.
- Phát hiện chuyển từ `PENDING` sang `PAID`.
- Xây projection có semantics rõ hơn `UPDATE_LOOKUP`.
- Audit một số loại thay đổi, khi retention đáp ứng.

### 16.2. Chi phí và giới hạn

- Additional storage/write amplification.
- Image retention và oplog dependency.
- Cấu hình cần quản lý.
- Kích thước tài liệu và event-size restrictions.
- Một số event/types có thể không cung cấp images.

### 16.3. Không thay thế audit log vĩnh viễn

Pre/post images có chính sách lưu giữ; không dùng nó như kho audit nhiều năm nếu chưa có export/retention architecture riêng.

---

## 17. Xử lý `delete`

Delete event thường không có fullDocument là document đã xóa.

```java
if (event.getOperationType()
        == OperationType.DELETE) {

    BsonDocument key = event.getDocumentKey();

    if (key == null) {
        throw new IllegalStateException(
            "DELETE without documentKey"
        );
    }

    target.deleteOne(key);
}
```

Ví dụ này chỉ phù hợp nếu `documentKey` là filter hợp lệ cho target với cùng key mapping. Trong sharded collection, `documentKey` có thể chứa shard key fields; nếu target khác schema, phải transform.

### 17.1. Đừng bỏ delete

Một consumer chỉ thực hiện upsert cho insert/update sẽ để lại dữ liệu cũ sau khi source xóa.

### 17.2. Tombstone ngăn sự kiện cũ làm document sống lại

Nếu handlers xử lý song song và nhận:

```text
E40: update order status=PAID
E41: delete order
```

mà E41 áp trước E40, một stale update có thể tạo lại order trên target.

Có thể lưu tombstone:

```javascript
{
  _id: "O100",
  appliedVersion: NumberLong("41"),
  deleted: true
}
```

và chỉ chấp nhận event có version mới hơn. Cần retention đủ để ngăn late replay; version phải được sinh theo protocol đáng tin, không tự lấy ObjectId hoặc client timestamps làm thứ tự tuyệt đối.

---

## 18. `drop`, `rename` và `invalidate`

Change Stream có thể bị **invalidate** khi collection/database thay đổi theo cách làm stream cũ không còn hợp lệ.

### 18.1. Không coi invalidate là một thay đổi dữ liệu bình thường

Nếu collection `orders` bị drop rồi tạo lại, một consumer cũ có thể đang theo dõi namespace hoặc collection identity không còn phù hợp. Việc tiếp tục xử lý cần quyết định:

- Collection được tạo lại có phải cùng nghiệp vụ?
- Có cần rebuild read model không?
- Có được mất events trong thời gian drop/recreate không?
- Có cần namespace mới?
- Có áp dụng lại pipeline và permissions?

### 18.2. ResumeAfter và StartAfter khác nhau

Sau `invalidate`, `resumeAfter` không được dùng để resume theo cách thông thường. `startAfter` có semantics được thiết kế để mở stream sau một invalidate token khi điều kiện server hỗ trợ.

`startAfter` **không** tự đảm bảo dữ liệu mới giống collection cũ hoặc consumer không cần bootstrap.

### 18.3. DDL cần runbook

Một production consumer cần policy cho:

- Drop/rename collection.
- Resharding/configuration changes.
- Thay đổi schema/indexes.
- Stream pipeline version.
- Chuyển database/tenant scope.
- Xóa rồi tạo lại namespace.

Không im lặng catch mọi event lạ và tiếp tục checkpoint.

---

# PHẦN II — XỬ LÝ LẶP VÀ IDEMPOTENCY

## 19. Tại sao consumer có thể nhận lại sự kiện?

Xét một event E100:

```text
Read E100 from Change Stream
           |
           v
Apply to target successfully
           |
           v
Process crashes BEFORE checkpoint E100
           |
           v
Restart from token E99
           |
           v
E100 is delivered again
```

Đây là hành vi có thể xảy ra trong cơ chế **at-least-once processing**.

Các nguyên nhân khác:

- Network response bị mất.
- Primary election làm cursor được mở lại.
- Driver/application retry.
- Worker lease hết hạn khi worker cũ còn chạy.
- Consumer chạy trùng nhiều instances.
- Checkpoint store ghi thất bại.
- Event được replay có chủ đích để rebuild.
- Target ghi thành công nhưng acknowledgment bị timeout.

**Không cố khử duplicate bằng một biến `lastEventId` trong RAM**, vì process restart làm mất state đó và không xử lý concurrency.

---

## 20. Ba khái niệm dễ nhầm

| Khái niệm | Ý nghĩa |
| --- | --- |
| At-most-once | Có thể mất event; tránh một số duplicates |
| At-least-once | Không bỏ qua event đã có thể replay theo điều kiện retention, nhưng có thể xử lý lặp |
| Exactly-once business effect | Side effect nghiệp vụ xảy ra đúng một lần, cần protocol/transaction/idempotency phù hợp |

Change Streams có resume capability, nhưng **không tự cam kết exactly-once external side effects**.

### 20.1. Exactly-once không phải một checkbox

Để bảo đảm “chỉ gửi một email” cần idempotency ở email provider hoặc một hệ thống delivery ledger có cách kiểm soát ambiguity. Chỉ việc lưu resume token đúng lúc chưa giải quyết tình huống response bị mất sau email đã gửi.

### 20.2. Chọn mục tiêu theo side effect

- Xây read model bằng idempotent replace: at-least-once thường hợp lý.
- Tính tổng doanh thu bằng `$inc`: phải có dedup/version/increment event protocol.
- Gửi tiền/thanh toán: cần business idempotency key và reconciliation.
- Gửi notification: tùy policy “may deliver duplicate” hay “at-most-once per user”.

---

## 21. Idempotent operation là gì?

Một hàm `f` idempotent khi:

```text
f(f(x)) = f(x)
```

Ví dụ replace với cùng document:

```java
target.replaceOne(
    Filters.eq("_id", orderId),
    transformedOrder,
    new ReplaceOptions().upsert(true)
);
```

Áp lại cùng *state* có thể giữ kết quả không đổi, nếu transformation deterministic và không bị event cũ ghi đè state mới.

Không idempotent:

```java
target.updateOne(
    Filters.eq("_id", orderId),
    Updates.inc("notificationsSent", 1)
);
```

Áp event hai lần làm counter tăng hai lần.

### 21.1. Idempotency không đồng nghĩa xử lý đúng thứ tự

Nếu áp trạng thái mới `REFUNDED` rồi áp lại event cũ `PAID`, `replaceOne` vẫn có thể làm final state sai.

### 21.2. Transformation phải deterministic

Không nên mỗi lần replay cùng event lại:

- Sinh `_id` ngẫu nhiên.
- Ghi `updatedAt = now()` nếu nó ảnh hưởng nghiệp vụ.
- Sinh số tiền dựa trên double/logic thay đổi.
- Gọi API external mà không có idempotency key.

Có thể chấp nhận metadata về `lastAttemptAt`, nhưng tách nó khỏi kết quả nghiệp vụ mong muốn.

---

## 22. Chọn idempotency key

Những lựa chọn phổ biến:

1. **Event identity:** resume token được giữ nguyên ở dạng BSON, kèm stream/consumer identity.
2. **Business operation ID:** ví dụ `paymentAttemptId`, `orderEventId`.
3. **Document ID + monotonic version:** phù hợp state projection per aggregate.
4. **Outbox event ID:** ID bất biến do application sinh và commit cùng business write.

### 22.1. Đừng dùng chỉ mỗi `documentKey._id`

Một order có thể phát sinh 100 events. Nếu dedup theo order ID, event đầu tiên được xử lý rồi tất cả updates sau đó bị coi là duplicate.

### 22.2. Token và scope

Một token thuộc change stream history và scope. Khi lưu trong processed-events collection, nên namespace khóa bởi:

```text
consumerName
streamScope
streamGeneration / pipelineVersion
event resume token
```

Tránh vô tình chia sẻ idempotency key giữa hai consumers có side effects khác nhau.

### 22.3. Business key thường tốt hơn cho external side effects

Nếu event database bị replay hoặc consumer tái bootstrap và sinh token khác cho cùng nghiệp vụ, một stable `notificationId`/`paymentId` có thể thích hợp hơn resume token.

---

## 23. Inbox/receipt collection để xử lý một lần trong MongoDB

Một consumer cập nhật projection trong **cùng MongoDB deployment** có thể dùng collection `processedChangeEvents` làm inbox.

Ví dụ document:

```javascript
{
  _id: {
    consumer: "orders-read-model-v1",
    eventKey: "stable-encoded-token-or-event-id"
  },
  processedAt: ISODate("2026-11-14T10:00:00Z"),
  operationType: "update",
  documentId: "O100"
}
```

Tạo unique constraint:

```javascript
db.processedChangeEvents.createIndex(
  { "consumer": 1, "eventKey": 1 },
  { unique: true }
);
```

Trong schema này nên chọn **một cấu trúc khóa thống nhất** (ví dụ `_id` ghép hoặc compound fields). Nếu đã dùng `_id` duy nhất có đủ consumer+event identity, index bổ sung có thể không cần.

### 23.1. Check-then-write không an toàn nếu có concurrency

Sai:

```text
if inbox record absent:
    send notification
    insert inbox record
```

Hai workers có thể cùng thấy absent rồi cùng gửi.

### 23.2. Unique receipt chỉ đủ khi gắn với effect đúng cách

Nếu ghi receipt trước external API, crash sau receipt nhưng trước API sẽ làm **mất effect** khi replay bỏ qua event.

Nếu gọi external API trước receipt, crash giữa hai bước có thể **lặp effect**.

Đó là bài toán atomicity xuyên hệ thống; dùng provider idempotency key, outbox/delivery workflow hoặc reconciliation, không chỉ unique index.

---

## 24. Atomic inbox và projection trong cùng MongoDB deployment

Nếu processed receipt và read model **ở cùng MongoDB replica set/sharded deployment** hỗ trợ multi-document transactions, có thể ghi hai tài liệu trong một transaction.

Pseudocode:

```text
BEGIN TRANSACTION
    insert receipt(eventId) with unique constraint
    upsert projection(orderId, newState)
COMMIT

On duplicate receipt:
    event already processed; do not reapply

After commit:
    checkpoint resume token
```

### 24.1. Vì sao điều này hữu ích?

Nếu transaction commit thành công mà checkpoint thất bại, event sẽ replay. Lúc replay, receipt trùng khiến handler không áp projection lại.

Nếu transaction abort, cả receipt lẫn projection bị rollback trong cùng transaction boundary.

### 24.2. Không đồng nghĩa cross-cluster atomicity

Nếu consumer đọc nguồn MongoDB A và ghi projection vào MongoDB B, transaction trên B có thể bao trùm **receipt và projection ở B**, nhưng không bao trùm việc nhận Change Stream từ A.

Đó không nhất thiết là vấn đề: checkpoint sau target commit và idempotent replay vẫn cung cấp workflow có thể khôi phục.

### 24.3. Không gọi external API trong transaction callback

Các API như `withTransaction()` có thể retry callback. Side effects ngoài MongoDB có thể bị gọi lại. Chỉ đặt operations thuộc transaction scope và chịu được retry vào callback.

---

## 25. Java minh họa transaction receipt + projection

Đoạn dưới là ví dụ về ranh giới transaction. `eventId` cần được sinh/lưu từ một stable event identity theo protocol consumer; `order` là state đã transform.

```java
import com.mongodb.MongoException;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;

public final class ProjectionWriter {

    private final MongoClient targetClient;
    private final MongoCollection<Document> receipts;
    private final MongoCollection<Document> projections;

    public ProjectionWriter(
            MongoClient targetClient,
            MongoCollection<Document> receipts,
            MongoCollection<Document> projections
    ) {
        this.targetClient = targetClient;
        this.receipts = receipts;
        this.projections = projections;
    }

    public void applyOnce(
            String consumerId,
            String eventId,
            Document order
    ) {
        String receiptId = consumerId + ":" + eventId;

        try (ClientSession session =
                 targetClient.startSession()) {

            try {
                session.withTransaction(() -> {
                    receipts.insertOne(
                        session,
                        new Document("_id", receiptId)
                    );

                    projections.replaceOne(
                        session,
                        Filters.eq("_id", order.get("_id")),
                        order,
                        new ReplaceOptions().upsert(true)
                    );

                    return null;
                });
            } catch (MongoException error) {
                if (error.getCode() == 11000) {
                    // Chỉ coi là duplicate đã xử lý nếu
                    // receiptId đúng consumer/event contract.
                    return;
                }
                throw error;
            }
        }
    }
}
```

### 25.1. Ví dụ còn những điều kiện cần thiết

- Đảm bảo `receipts` có unique `_id`.
- `eventId` phải stable, không phải UUID mới ở mỗi retry.
- Nếu replace có thể ghi đè state mới hơn, cần thêm version/order handling.
- `withTransaction` retries và commit uncertainty cần xử lý theo driver docs.
- Error 11000 có thể đến từ **index khác**, không phải receipt; production code phải phân biệt index/key thực tế và không nuốt unique conflicts của projection như “đã xử lý”.
- Cần đảm bảo `targetClient`, `receipts` và `projections` thuộc **cùng deployment** hỗ trợ transactions.
- Transaction không bao gồm external email/payment calls.

**Quan trọng:** đây là minh họa cơ chế, không phải implementation đầy đủ cho mọi driver version và topology.

---

## 26. Side effect ngoài MongoDB: notification/email/payment

Ví dụ:

```text
Change event E100
    |
    v
Call email provider
    |
    v
Provider sends email
    |
    v
Response lost / consumer crash
    |
    v
Consumer reprocesses E100
    |
    v
Email may be sent again
```

Không có cách chỉ dùng MongoDB checkpoint để biến một external API không hỗ trợ idempotency thành exactly-once.

### 26.1. Các chiến lược khả thi

- Dùng **idempotency key** ở downstream provider.
- Tạo notification record với unique business key.
- Ghi intent vào **outbox/delivery queue** rồi worker gửi theo policy.
- Lưu delivery state/attempts/correlation ID.
- Theo dõi trạng thái unknown và reconciliation.
- Đặt policy chấp nhận duplicates nếu business cho phép (ví dụ thông báo ít quan trọng).

### 26.2. Payment là trường hợp đặc biệt

Không dùng raw Change Stream event ID làm payment idempotency key nếu một giao dịch có thể phát nhiều DB events. Dùng business paymentAttemptId được sinh và quản lý từ trước.

### 26.3. “Gửi đúng một lần” thường là end-to-end protocol

Nguồn, consumer, queue, provider và trạng thái nghiệp vụ đều phải tham gia. Khi provider không cung cấp xác nhận có thể tra cứu, một kết quả unknown có thể phải được xử lý thủ công.

---

## 27. Transactional outbox khi cần event nghiệp vụ ổn định

Một mô hình khác:

```text
Application transaction
      |
      +--> Write business order
      |
      +--> Insert outbox event
      |
      v
Commit
      |
      v
Change Stream watches OUTBOX
      |
      v
Delivery worker
      |
      v
Notification provider / Kafka
```

Outbox event:

```javascript
{
  _id: "evt-order-O100-paid-v4",
  aggregateId: "O100",
  type: "OrderPaid",
  version: NumberLong("4"),
  payload: {
    orderId: "O100",
    customerId: "C7",
    amountMinor: NumberLong("199000")
  },
  createdAt: ISODate("2026-11-14T10:00:00Z"),
  deliveryState: "PENDING"
}
```

### 27.1. Tại sao tốt hơn watch mọi update?

- Event mang **business intent**, không phụ thuộc diff của documents.
- Có stable ID và version.
- Cho phép lọc những thay đổi đáng gửi notification.
- Khi business write và outbox insert cùng transaction, không bỏ mất intent giữa hai thao tác.
- Có thể replay/retention dài hơn oplog nếu lưu outbox đủ lâu.

### 27.2. Vẫn có duplicate delivery

Worker có thể gửi rồi crash trước khi đánh dấu delivered. Cần provider idempotency và retry/reconciliation.

### 27.3. Watch outbox thay vì polling?

Cả hai có thể cùng tồn tại:

- Change Stream để đánh thức worker nhanh.
- Polling outbox durable để đảm bảo có thể quét các pending events khi Change Stream history bị mất.

Một số kiến trúc dùng Change Stream như **notification of work**, còn outbox collection là nguồn dữ liệu bền vững cần xử lý.

---

# PHẦN III — RESUME TOKEN VÀ CHECKPOINT

## 28. Resume token cần lưu gì?

Resume token là một `BsonDocument` opaque, không phải một số thứ tự do ứng dụng tự định nghĩa.

Lưu cùng:

```javascript
{
  _id: "orders-projection-v1",
  streamScope: "sales.orders",
  pipelineVersion: 1,
  checkpointType: "resumeAfter",
  resumeToken: {
    _data: "opaque-bson-value"
  },
  updatedAt: ISODate("2026-11-14T10:00:00Z"),
  workerGeneration: NumberLong("12")
}
```

Đây là schema minh họa. Nếu lưu trong `MongoCollection<BsonDocument>`, có thể bảo toàn BSON token tự nhiên hơn so với chuyển sang string.

### 28.1. Không chỉ lưu một chuỗi token không kèm scope

Một token thuộc stream và pipeline. Nếu deploy version mới với phạm vi event khác, cần biết token cũ có còn phù hợp hay không.

### 28.2. Tránh convert token thành timestamp

Không thay:

```javascript
resumeToken: event._id
```

bằng:

```javascript
lastSeenAt: event.clusterTime
```

rồi kỳ vọng giống nhau. `clusterTime` không là ID đầy đủ của event và có thể trùng giữa nhiều changes.

### 28.3. Token có thể đến từ empty batch

Java cursor có thể cung cấp resume token mới nhất/high-watermark kể cả khi chưa trả event mới, theo server/driver support. Cần xử lý cẩn thận với những events đang in-flight.

---

## 29. Checkpoint sau side effect, không phải sau khi đọc

Đúng:

```text
Read event E101
    |
    v
Validate event
    |
    v
Apply side effect idempotently
    |
    v
Receive/verify acknowledgment
    |
    v
Persist resume token of E101
    |
    v
Read event E102
```

Sai:

```text
Read event E101
    |
    v
Persist token E101
    |
    v
Apply side effect -> FAILURE
    |
    v
Restart from AFTER E101
    |
    v
E101 skipped
```

### 29.1. At-least-once và checkpoint

Khi checkpoint sau apply, crash giữa hai bước tạo duplicate replay; vì vậy cần idempotency. Đây là một đánh đổi có chủ đích để tránh mất event.

### 29.2. Khi nào checkpoint theo batch?

Nếu xử lý 100 events tuần tự rồi mới lưu checkpoint của event 100, crash có thể replay cả 100. Cần:

- Mọi effects idempotent.
- Batch size phù hợp.
- Quan sát progress/lag.
- Không checkpoint qua event chưa được ack.
- Giới hạn lượng replay theo SLO.

### 29.3. Với processing song song

Không lưu token **lớn nhất vừa hoàn thành** nếu các events trước đó còn pending. Chỉ có thể checkpoint tới **contiguous prefix** đã được xử lý/ack theo stream order hoặc theo per-partition protocol.

---

## 30. Lưu resume token giữ nguyên BSON trong Java

Một ví dụ dùng `MongoCollection<BsonDocument>`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.BsonDocument;
import org.bson.BsonString;

public final class ResumeTokenStore {

    private final MongoCollection<BsonDocument> checkpoints;
    private final BsonString consumerId;

    public ResumeTokenStore(
            MongoCollection<BsonDocument> checkpoints,
            String consumerId
    ) {
        this.checkpoints = checkpoints;
        this.consumerId = new BsonString(consumerId);
    }

    public BsonDocument load() {
        BsonDocument record = checkpoints.find(
            Filters.eq("_id", consumerId)
        ).first();

        return record == null
            ? null
            : record.getDocument("resumeToken");
    }

    public void save(BsonDocument token) {
        if (token == null) {
            return;
        }

        BsonDocument record = new BsonDocument(
            "_id", consumerId
        ).append(
            "resumeToken", token
        );

        checkpoints.replaceOne(
            Filters.eq("_id", consumerId),
            record,
            new ReplaceOptions().upsert(true)
        );
    }
}
```

### 30.1. Cần durable acknowledgment

Checkpoint store phải có durability policy phù hợp. Nếu checkpoint được lưu với write concern yếu rồi rollback sau failover, consumer có thể replay thêm events. Idempotency giúp xử lý trường hợp này.

### 30.2. Một consumer ID cho mỗi logical stream

Không cho hai pipelines khác nhau cùng ghi đè một checkpoint document. Dùng ID chứa tên consumer/stream version.

### 30.3. Không dùng checkpoint store làm memory cache

State phải tồn tại sau process restart. Có thể dùng MongoDB collection, nhưng cũng cần backup/retention và lease policy.

### 30.4. Nếu checkpoint ở cùng target với effects

Có thể transactionally lưu checkpoint và xử lý projection trong một transaction phù hợp, nhưng cần thiết kế ordering, duplicate handling và transaction error semantics. Khi external effect khác deployment, vẫn không có atomicity tự nhiên.

---

## 31. Consumer restart bằng `resumeAfter`

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ResumableConsumer {

    private final ResumeTokenStore checkpointStore;
    private final AtomicBoolean running =
        new AtomicBoolean(true);

    public ResumableConsumer(
            ResumeTokenStore checkpointStore
    ) {
        this.checkpointStore = checkpointStore;
    }

    public void stop() {
        running.set(false);
    }

    public void run(
            MongoCollection<Document> orders
    ) {
        BsonDocument saved = checkpointStore.load();

        ChangeStreamIterable<Document> stream =
            orders.watch()
                .fullDocument(FullDocument.UPDATE_LOOKUP)
                .maxAwaitTime(2, TimeUnit.SECONDS);

        if (saved != null) {
            stream = stream.resumeAfter(saved);
        }

        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 stream.cursor()) {

            while (running.get()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    continue;
                }

                // Must be idempotent!
                processEvent(event);

                // Save AFTER successful processing.
                checkpointStore.save(
                    event.getResumeToken()
                );
            }
        }
    }

    private void processEvent(
            ChangeStreamDocument<Document> event
    ) {
        // Business-specific idempotent handler.
    }
}
```

### 31.1. Ví dụ có giới hạn

- Không tự xử lý error labels và retries.
- Không có worker lease/fencing.
- Chưa xử lý missing event types/invalidations.
- Không có bootstrap snapshot.
- `processEvent` là placeholder.
- Chưa có monitoring/checkpoint metadata.
- Dòng `checkpointStore.save(...)` không atomic với external effect.

Đây là **khung kết nối đúng thứ tự thao tác**, không phải consumer production hoàn chỉnh.

### 31.2. Nếu không có token

`watch()` mặc định bắt đầu từ một vị trí mới theo semantics stream, **không tự phát lại toàn bộ documents đã tồn tại**. Cần bootstrap theo yêu cầu ứng dụng trước khi cho consumer phục vụ dữ liệu.

---

## 32. `resumeAfter`, `startAfter` và `startAtOperationTime`

| Tùy chọn | Dùng khi | Lưu ý |
| --- | --- | --- |
| `resumeAfter(token)` | Consumer restart bình thường sau checkpoint hợp lệ | Không dùng để resume sau invalidate theo cách thông thường |
| `startAfter(token)` | Mở stream sau một invalidate event khi được hỗ trợ | Không tự xây lại collection/read model |
| `startAtOperationTime(timestamp)` | Bắt đầu ở một BSON logical time có history phù hợp, thường khi chưa có token | Kém cụ thể hơn resume token; cần hiểu phạm vi/thời điểm |

### 32.1. Chỉ chọn một starting point

Không cấu hình đồng thời nhiều starting options trong cùng Change Stream.

### 32.2. `startAtOperationTime` là BSON Timestamp

Không phải Java `Date` và không phải epoch millis do client tự đoán.

```java
import org.bson.BsonTimestamp;

BsonTimestamp time =
    new BsonTimestamp(secondsSinceEpoch, increment);

orders.watch()
    .startAtOperationTime(time);
```

Cần lấy timestamp từ một nguồn/operation phù hợp và đảm bảo history còn lưu; không bịa `increment` rồi coi là exact event position.

### 32.3. Token từ invalidate

Nếu consumer xử lý sự kiện `invalidate` và có token phù hợp, `startAfter` có thể giúp mở stream mới theo semantics MongoDB. Nhưng nếu namespace đã bị xóa, business projection có thể cần rebuild.

---

## 33. Post-batch resume token và high-watermark

Khi server trả batch rỗng, response có thể mang `postBatchResumeToken`, biểu thị vị trí stream đã tiến tới dù không có user event nào.

Java MongoChangeStreamCursor có phương thức:

```java
BsonDocument token = cursor.getResumeToken();
```

Token này có thể phản ánh event gần nhất hoặc server-provided resume point được driver quản lý.

### 33.1. Tại sao hữu ích?

Nếu collection rất ít writes, consumer không nên để checkpoint quá cũ chỉ vì lâu không có event. High-watermark có thể giúp resume tại vị trí mới hơn khi không có outstanding work.

### 33.2. Không checkpoint vượt event chưa xong

```text
E100 read, handler still running
E101 read, handler still running
postBatch token = T105
```

Nếu lưu T105 khi E100/E101 chưa ack, restart có thể bỏ qua chúng.

### 33.3. Quy tắc an toàn

Chỉ cập nhật token high-watermark khi:

- Mọi events trước token đã được xử lý/ack theo protocol.
- Không còn in-flight work cũ hơn.
- Consumer ownership/lease hợp lệ.
- Token xuất phát từ chính stream/pipeline đang dùng.

Với **single-threaded synchronous** consumer đã xử lý hết trước khi tiếp tục poll, việc lưu high-watermark ở batch rỗng có thể khả thi khi đã xác nhận điều kiện.

### 33.4. Không bắt buộc phải lưu PBRT để có correctness

Có thể chỉ checkpoint event tokens sau khi xử lý xong. Việc đó đơn giản hơn nhưng token có thể cũ trong thời gian ít events. Chọn theo SLO history/idle duration.

---

## 34. Driver có tự resume không?

Java Driver hiện đại có cơ chế **automatic resume cho một số lỗi có thể resume được** trong Change Streams, tuân theo server/driver error labels và điều kiện API.

Nhưng không nên giả định:

- Mọi lỗi đều có thể resume.
- Driver sẽ retry vô hạn.
- History đã hết hạn vẫn có thể khôi phục.
- Callback side effect chưa ack sẽ được xử lý chính xác một lần.
- Invalidate event tự mở lại collection với cùng business semantics.
- Không cần application checkpoint.

### 34.1. Trách nhiệm tách biệt

**Driver:**

- Quản lý kết nối/topology.
- Fetch batches.
- Có thể tự resume theo contract và token hiện có trong một số trường hợp.

**Application:**

- Lưu durable checkpoint.
- Idempotency.
- Startup/restart policy.
- Business errors.
- Long outage handling.
- Rebootstrap/reconciliation.
- Worker ownership.

### 34.2. Sau process crash

Driver state trong RAM mất. Application phải đọc checkpoint store rồi mở stream mới với starting option phù hợp.

---

## 35. Oplog history window và mất resume point

Change Streams phụ thuộc lịch sử đủ dài. Nếu consumer ngừng nhiều giờ/ngày trong khi writes tiếp tục:

```text
00:00 consumer saves token T100
01:00 consumer crashes
...
20:00 oplog overwrites old history
21:00 consumer restarts from T100
       -> history no longer available
```

Khi token không còn có thể resume, không được âm thầm tạo stream mới ở thời điểm hiện tại và đánh dấu consumer `HEALTHY`. Làm như vậy có thể mất những changes trong khoảng gián đoạn.

### 35.1. Cần theo dõi

- Oplog window hiện tại của source/sync topology.
- Consumer lag và tuổi checkpoint.
- Tốc độ viết thay đổi ở giờ cao điểm.
- Thời gian offline/restart tối đa.
- Backlog của downstream.
- Độ trễ xử lý per event.
- Quá trình initial sync/resharding/maintenance ảnh hưởng history.

### 35.2. Khi token quá cũ

Có thể cần:

1. Dừng consumer/báo degraded.
2. Bảo vệ target hiện tại để không tiếp tục nhận state không nhất quán.
3. Đánh giá source of truth và data loss window.
4. Rebootstrap toàn bộ/những partitions bị ảnh hưởng.
5. Thiết lập lại stream starting point hợp lệ.
6. Reconcile dữ liệu và side effects.
7. Chỉ chuyển trạng thái HEALTHY khi dữ liệu/offset đã được xác minh.

### 35.3. Tăng oplog sau khi mất history không khôi phục past entries

Tăng retention có thể giúp tương lai, không tái tạo những changes đã bị cắt.

---

# PHẦN IV — KHÔI PHỤC SAU SỰ CỐ

## 36. Phân loại lỗi consumer

| Loại lỗi | Ví dụ | Phản ứng |
| --- | --- | --- |
| Mạng tạm thời | Connection reset, temporary timeout | Backoff/reopen theo checkpoint |
| Primary election | Stepdown, topology change | Chờ cluster khỏe, resume theo policy |
| Server selection | Không tìm được node phù hợp | Alert outage, retry có giới hạn |
| History lost | Resume token không còn trong oplog | **Không skip**; rebootstrap/reconcile |
| Invalidate/DDL | Drop, rename | Scope-specific handling; thường cần quyết định nghiệp vụ |
| Authentication/authorization | Permission revoked | Dừng và sửa quyền, không retry vô hạn |
| Payload/schema | Unknown event type/field | Quarantine/poison event policy |
| Downstream unavailable | Search/email/Kafka lỗi | Retry durable, không advance checkpoint |
| Duplicate event | Replay sau crash | Idempotent no-op hoặc read/confirm state |
| Checkpoint store failure | Event đã apply nhưng token chưa lưu | Replay có kiểm soát |
| Worker lease lost | Worker không còn owner | Ngừng apply/checkpoint |
| Process shutdown | SIGTERM/deploy | Stop fetch, drain, checkpoint, close |

### 36.1. Không catch mọi Exception rồi `continue`

Ví dụ sai:

```java
try {
    handle(event);
} catch (Exception ignored) {
    // Continue and checkpoint next event.
}
```

Một event lỗi sẽ bị bỏ qua vĩnh viễn nếu checkpoint tiếp tục tiến lên.

### 36.2. Error policy phải chọn rõ

Đối với poison event:

- Block toàn stream đến khi sửa dữ liệu/code.
- Quarantine event vào durable DLQ rồi advance checkpoint **nếu nghiệp vụ cho phép bỏ qua** và có cơ chế replay/alert.
- Route sang manual workflow.
- Tách event streams theo partition khi cần giảm blast radius.

Không tuyên bố “không mất event” nếu DLQ có records chưa được giải quyết.

---

## 37. Retry với backoff và jitter

Một consumer không nên mở stream lại liên tục mỗi mili-giây khi source outage.

Ví dụ policy:

```text
retry 1: 200 ms + jitter
retry 2: 500 ms + jitter
retry 3: 1 s + jitter
retry 4: 2 s + jitter
...
cap: 30 s
```

### 37.1. Cần deadline/failure budget

Có thể retry lâu với background service, nhưng health phải báo `DEGRADED` khi liên tục không tiến triển và `FAILED/REBOOTSTRAP_REQUIRED` khi lỗi không recoverable.

### 37.2. Không retry poison data bằng tốc độ cao

Nếu transform event luôn throw do schema version chưa hỗ trợ, network retry không giúp. Alert và yêu cầu sửa handler/quarantine theo policy.

### 37.3. Jitter tránh thundering herd

Nếu 200 consumers cùng restart sau outage, deterministic retry delay có thể khiến tất cả kết nối và chạy getMore đồng thời.

---

## 38. Khôi phục sau mất kết nối ngắn

Runbook:

1. Ghi log exception, token cuối cùng đã lưu bền vững.
2. Đóng cursor hiện tại.
3. Kiểm tra network/topology hoặc đợi theo backoff.
4. Đọc lại token từ checkpoint store.
5. Mở Change Stream mới với `resumeAfter`.
6. Dùng idempotency để xử lý events có thể đã apply trước crash.
7. Theo dõi lag đến khi về ngưỡng cho phép.

### 38.1. Đừng resume theo token mới nhất chỉ ở RAM

Nếu event E200 đã đọc nhưng chưa apply, token `cursor.getResumeToken()` có thể đã vượt E200. Phải resume từ **durable acknowledged checkpoint**, không từ vị trí đọc cuối trong RAM.

### 38.2. Khi đang xử lý event và process crash

At-least-once replay có thể đưa event đó tới consumer mới. Đây là trường hợp bắt buộc phải test.

---

## 39. Khôi phục sau lỗi checkpoint

```text
Event E200
    |
    v
Projection update success
    |
    v
Checkpoint save fails
    |
    v
Process restart
    |
    v
Replay E200
```

Nếu projection được cập nhật bằng deterministic replace và có version/ordering phù hợp, replay có thể an toàn.

Nếu xử lý bằng `$inc`, `sendEmail()` hoặc `chargeCard()`, có thể tạo duplicate side effects.

### 39.1. Cơ chế bù

- Receipt/processed-events store.
- Stable business idempotency key.
- Atomic projection+receipt transaction nếu cùng deployment.
- Provider-level idempotency.
- Reconciliation để giải quyết kết quả unknown.

### 39.2. Checkpoint store writeConcern

Nếu token được lưu với `w:1` rồi rollback sau failover, consumer có thể đọc lại events. Không làm sai dữ liệu nếu handler idempotent; nếu SLA đòi hỏi durable progress, cân nhắc majority concern.

---

## 40. Khôi phục sau `invalidate`

Một stream trên collection bị drop hoặc rename có thể kết thúc bằng invalidate.

Không áp dụng:

```text
catch invalidate -> resumeAfter(invalidateToken) -> success
```

như quy tắc chung.

### 40.1. Sự khác nhau giữa các scope

- Collection-level stream thường gắn chặt với collection identity.
- Database/deployment-level streams có behavior khác trước drop/rename.
- Một số event types/DDL không invalidate cùng cách ở mọi scope.

### 40.2. Chọn recovery policy

1. Dừng và báo `NAMESPACE_CHANGED`.
2. Xác nhận collection mới có cùng business purpose hay không.
3. Nếu cần, dùng `startAfter` trên invalidate token theo semantics được hỗ trợ.
4. Rebuild projection khi dữ liệu cũ không còn tương thích.
5. Cập nhật stream generation/schema version.
6. Kiểm tra backlog/reconciliation trước phục vụ.

### 40.3. Không tự coi create lại collection là tiếp tục cùng lịch sử

Drop/recreate có thể tạo collection mới với cùng tên nhưng lifecycle, indexes và dữ liệu hoàn toàn khác. Consumer phải hiểu đó là migration hay thao tác không mong đợi.

---

## 41. Khôi phục sau oplog history lost

Nếu token quá cũ:

```text
Resume attempt with token T
        |
        v
History unavailable
        |
        v
STOP + mark REBOOTSTRAP_REQUIRED
        |
        v
Rebuild baseline from source of truth
        |
        v
Establish safe new change capture boundary
        |
        v
Apply catch-up events
        |
        v
Verify and resume service
```

### 41.1. Không phải cứ xóa token là xong

Nếu xóa token rồi mở stream từ “hiện tại”, hệ thống có thể vĩnh viễn bỏ qua hàng triệu updates trong khoảng mất kết nối.

### 41.2. Một số side effects không thể replay chỉ từ state hiện tại

Nếu cần gửi email cho **mỗi** lần chuyển trạng thái trong quá khứ, một snapshot hiện tại không cho biết đã có những lần chuyển trạng thái nào. Đây là lý do domain outbox/event log có retention bền vững có thể quan trọng hơn chỉ dựa vào Change Stream.

### 41.3. Recovery plan theo mục đích

- **Read model/search index:** có thể rebuild từ dữ liệu hiện tại, rồi catch up.
- **Cache invalidation:** có thể invalidate/rebuild cache.
- **Transactional notification:** có thể cần outbox/delivery ledger để tránh mất business events.
- **Audit:** cần audit log bất biến có retention phù hợp, không chỉ oplog.

---

## 42. Bootstrap dữ liệu lịch sử: Change Stream không tự backfill

Nếu collection đã có một triệu orders trước khi consumer được triển khai, việc `watch()` từ thời điểm hiện tại chỉ nhận changes sau mốc đó.

### 42.1. Mục tiêu

```text
Initial data:
  O1...O1,000,000

During bootstrap:
  O100 updated
  O500 deleted
  O1,000,001 inserted
```

Target cần chứa trạng thái cuối đúng sau khi copy và replay.

### 42.2. Quy trình khái niệm an toàn hơn

1. Thiết lập **CDC starting point** hợp lệ.
2. Bắt và persist changes từ điểm đó vào durable stream/log trong lúc copy.
3. Backfill source documents theo stable key.
4. Áp những events đã capture kể từ starting point theo thứ tự/phương pháp tránh stale overwrite.
5. Theo dõi catch-up lag.
6. Reconcile source và target ở cùng logical boundary.
7. Cho consumer hoạt động bình thường.

### 42.3. Bẫy: backfill ghi đè event mới

```text
T1 backfill reads O100 status=PENDING
T2 source updates O100 status=PAID
T3 CDC applies PAID to target
T4 backfill writes stale PENDING to target
```

Đây là lý do không để backfill và CDC apply tranh nhau mà không có ordering/version protocol.

### 42.4. Những cách giải quyết

- Capture trước, backfill hoàn tất rồi replay toàn bộ changes.
- Snapshot nhất quán + CDC starting point được xác lập theo cơ chế hỗ trợ.
- Version-aware conditional writes.
- Migration connector được thiết kế bảo đảm bootstrap/catch-up ordering.
- Dừng writes nếu downtime được chấp nhận.

### 42.5. Oplog window khi bootstrap

Backfill hàng giờ nhưng oplog window chỉ ngắn có thể làm mất events nếu không đọc và persist changes kịp. Tăng retention/giảm batch/có durable buffer hoặc công cụ migration chuyên dụng.

---

## 43. Đảm bảo ordering khi nhiều consumers

Một Change Stream cursor có ordering theo semantics MongoDB, nhưng khi đưa events sang worker pool:

```text
E1: O100 status=PAID
E2: O100 status=REFUNDED

Reader dispatches:
  E1 -> worker slow
  E2 -> worker fast

Target applies E2 then E1
```

Trạng thái cuối sai nếu E1 ghi đè E2.

### 43.1. Cách đơn giản nhất

Một consumer tuần tự xử lý events, checkpoint sau mỗi event/batch ack. Phù hợp khi throughput không quá cao.

### 43.2. Khi cần parallelism

- Partition theo stable aggregate ID.
- Bảo đảm per-key order.
- Một worker/partition hoặc ordered queue.
- Có monotonic version/tombstones ở target.
- Theo dõi completed contiguous offset, không checkpoint vượt pending.
- Có backpressure và giới hạn concurrency.

### 43.3. Không thread-share MongoCursor

`MongoCursor` không thread-safe. Một thread đọc rồi chuyển event payload sang workers; không cho nhiều threads cùng gọi `next()` trên một cursor.

### 43.4. Sharded cluster

Ordering, transaction events và cluster-wide streams có nuance. Không suy ra một trường timestamp đơn lẻ là total order để xử lý song song tùy ý.

---

## 44. Bounded queue và backpressure

Một pipeline:

```text
Change Stream reader
        |
        v
Bounded queue capacity=1000
        |
    +---+---+---+
    |       |   |
   W1      W2  W3
    |       |   |
    +-------+---+
        |
        v
Downstream
```

### 44.1. Nếu queue đầy

Reader phải backpressure/chặn lấy thêm events. Nếu reader tiếp tục đọc mà queue unbounded, heap tăng theo event rate.

### 44.2. Backpressure có giới hạn history

Khi reader chờ quá lâu và không tiến resume point, nguồn vẫn ghi và oplog window tiếp tục chạy. Cần:

- Scale downstream.
- Giảm xử lý event không cần thiết.
- Shard/partition hợp lý.
- Durable message broker nếu cần buffer dài.
- Alert theo consumer lag/oplog headroom.

### 44.3. Không lưu event chỉ trong RAM nếu mục tiêu chống crash

Bounded queue giúp memory safety nhưng **không bền vững**. Sau process crash, replay từ durable checkpoint phải tái tạo các events chưa xử lý.

---

## 45. Worker ownership, lease và fencing

Nếu deploy hai instances cùng consumer ID:

```text
Consumer A reads E100
Consumer B reads E100
Both send side effect
```

Checkpoint chung không ngăn hai workers cùng xử lý.

### 45.1. Single active consumer

Một thiết kế đơn giản:

- Mỗi logical stream chỉ có một active owner.
- Lease trong control collection.
- TTL hoặc expiry policy cho lease.
- Worker định kỳ renew.
- Khi mất lease, worker ngừng đọc/ghi checkpoint.

### 45.2. Fencing generation

Một **monotonic fencing token** giúp từ chối writes từ worker cũ sau khi lease chuyển sang worker mới.

```text
A owns generation=11
A becomes paused
Lease expires
B owns generation=12
A wakes up and tries to write
Storage rejects generation=11
```

Nếu chỉ dựa vào một boolean trong RAM, worker cũ có thể vẫn gửi side effect.

### 45.3. Lease không tự thay idempotency

Ngay cả với owner duy nhất, crash sau effect trước checkpoint vẫn tạo replay. Cần cả lease/fencing và idempotency.

---

## 46. Graceful shutdown

Khi nhận SIGTERM/deploy/cancel:

1. Ngăn nhận work mới.
2. Nếu reader đang block, đóng cursor theo contract để hủy.
3. Chờ hoặc hủy tasks đang xử lý theo deadline.
4. Chỉ checkpoint prefix đã ack.
5. Lưu state/metrics và release lease.
6. Đóng cursor/session/driver resources theo đúng ownership.
7. Process thoát.

### 46.1. `close()` từ cancellation thread

MongoCursor API cho phép `close()` đồng thời với phương thức đọc theo contract, nhưng những phương thức còn lại **không thread-safe**. Không sử dụng cùng cursor để `next()` từ hai threads.

### 46.2. Không đánh dấu completed khi chỉ nhận stop signal

Một long-lived Change Stream không phải job hữu hạn; trạng thái `STOPPED`/`DRAINED` khác `COMPLETED`.

### 46.3. Kubernetes terminationGracePeriod

Nếu consumer chạy dưới orchestrator, deadline shutdown phải đủ để xử lý/ack một event hoặc đủ ngắn để dừng và replay sau restart theo idempotency.

---

# PHẦN V — THIẾT KẾ CHỨC NĂNG THÔNG BÁO

## 47. Domain events và database events

Giả sử order chuyển trạng thái:

```text
PENDING -> PAID -> FULFILLED -> REFUNDED
```

Nếu chỉ watch `orders`, mỗi update có thể đến từ:

- API nghiệp vụ.
- Migration script.
- Admin correction.
- Background job.
- Retry transaction.
- Reconciliation.

Một database change event chỉ phản ánh thao tác lưu, không luôn mang intent. Nếu notification chỉ gửi khi **thanh toán được xác nhận lần đầu**, tốt hơn có event nghiệp vụ:

```javascript
{
  _id: "order-O100-paid-evt-4",
  type: "OrderPaid",
  orderId: "O100",
  version: 4,
  customerId: "C7",
  occurredAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 47.1. Khi watch `orders` vẫn phù hợp

- Đồng bộ search index theo state cuối.
- Invalidating cache.
- Cập nhật read model.
- Analytics eventual consistency.
- Đánh thức pipeline để quét pending tasks.

### 47.2. Khi outbox thích hợp hơn

- Trả tiền và hóa đơn.
- Gửi email/sms theo business transition.
- Integrations đòi hỏi event payload bất biến.
- Audit có retention dài.
- Replay được toàn bộ business history.

---

## 48. Mô hình notification với idempotency key

Một schema tham khảo:

```javascript
{
  _id: "notification-O100-paid-C7",
  eventId: "order-O100-paid-evt-4",
  recipientId: "C7",
  channel: "EMAIL",
  template: "ORDER_PAID",
  status: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

Tạo unique key trên notification ID hoặc compound business fields.

### 48.1. Tách tạo intent khỏi gửi

Consumer xử lý Change Stream hoặc outbox event bằng cách **upsert notification intent** theo stable key. Worker delivery riêng gửi email và cập nhật status.

```text
Change Stream event
       |
       v
Upsert notification intent
       |
       v
Checkpoint event token
       |
       v
Delivery worker sends with idempotency key
```

### 48.2. Lợi ích

- Nếu consumer đọc lại event, upsert theo same ID không tạo intent thứ hai.
- Nếu email provider lỗi, delivery worker retry từ database record.
- Có metrics per notification.
- Có thể tách lag source CDC khỏi delivery backlog.

### 48.3. Không khẳng định tuyệt đối không gửi trùng

Nếu provider không hỗ trợ idempotency và response bị mất, delivery worker vẫn có ambiguous outcome. Cần policy “không gửi lại nếu unknown” hoặc “retry có nguy cơ duplicate” theo business, cùng reconciliation.

---

## 49. Version và delete/tombstone ở read model

Một projection:

```javascript
{
  _id: "O100",
  status: "PAID",
  appliedVersion: NumberLong("42"),
  deleted: false
}
```

Khi nhận version 43, update chỉ nên có hiệu lực nếu target chưa ở version 43 hoặc mới hơn.

### 49.1. Conditional update

Ví dụ về logic:

```javascript
db.orderReadModels.updateOne(
  {
    _id: "O100",
    appliedVersion: { $lt: NumberLong("43") }
  },
  {
    $set: {
      status: "REFUNDED",
      appliedVersion: NumberLong("43")
    }
  }
);
```

**Lưu ý:** nếu record chưa tồn tại, phải có logic insert/upsert an toàn riêng. Upsert với điều kiện version trên cùng `_id` có thể gặp duplicate key khi target đã có record version mới hơn.

### 49.2. Không dùng timestamp máy client như total order

`updatedAt` của hai máy có thể bị clock skew. Version cần sinh từ một source of truth có quy tắc monotonic rõ ràng.

### 49.3. Tombstone sau delete

Nếu xóa vật lý ngay và stale event đến sau, projection có thể bị tạo lại. Giữ tombstone version hoặc đảm bảo strict per-key ordering trước khi cleanup.

---

## 50. Read-after-write và eventual consistency

Khi API ghi order thành công, Change Stream consumer cần thời gian để cập nhật read model.

```text
T0: write order
T0+20 ms: API responds success
T0+100 ms: consumer processes event
T0+150 ms: projection becomes visible
```

### 50.1. Không tự hứa synchronous consistency

Nếu user mở trang ngay sau POST và đọc từ projection, có thể chưa thấy thay đổi.

Các lựa chọn:

- API đọc trực tiếp source cho read-your-writes.
- Client optimistic UI.
- Wait-for-projection version với deadline thích hợp.
- Session/causal consistency ở cùng deployment khi semantics phù hợp.
- Trả `202 Accepted` cho workflow bất đồng bộ khi nghiệp vụ cho phép.

### 50.2. Consumer lag là một phần của SLA

Một hệ thống thông báo “trong vòng 5 giây” cần monitoring và capacity planning. Change Stream tự nó không cam kết deadline 5 giây.

---

# PHẦN VI — MONITORING VÀ KIỂM THỬ

## 51. Metrics consumer quan trọng

| Metric | Vì sao cần |
| --- | --- |
| `consumer_up` / last successful poll | Phát hiện worker chết |
| Last event processed time | Phát hiện stream stuck |
| Last durable checkpoint time | Xác nhận progress đã lưu |
| Resume attempts | Đo mức độ lỗi kết nối |
| Resume history lost count | Cảnh báo cần rebootstrap |
| Event processing duration | Tốc độ handlers |
| Downstream ack latency | Bottleneck |
| Events processed/sec | Throughput |
| Duplicate events skipped/sec | Hiểu replay behavior |
| Dead-letter count/age | Lỗi chưa xử lý |
| In-flight events | Checkpoint/order safety |
| Queue depth | Backpressure |
| Source oplog window | Recovery headroom |
| Consumer lag | Nguy cơ mất history và chậm notify |
| Fencing/lease owner | Ngăn xử lý trùng |
| Notifications delivered/unknown/failed | End-to-end business outcome |

### 51.1. Consumer ít event không nhất thiết bị treo

Một collection có thể không có writes trong nhiều giờ. Phân biệt:

- Không có events mới.
- Cursor vẫn poll/heartbeat bình thường.
- Consumer không có progress vì network bị hỏng.

Có thể dùng poll health, error state và token/high-watermark thay vì chỉ metric `events/sec`.

### 51.2. Lag dựa trên clusterTime có giới hạn

`clusterTime` không phải wall-clock SLA tuyệt đối; workload idle hoặc clock skew có thể ảnh hưởng. Đo event creation-to-processing latency và checkpoint age bằng dữ liệu phù hợp.

---

## 52. Alerting theo SLO

Ví dụ policy:

```text
WARNING:
  consumer lag > 15s sustained for 5m
  or queue depth > 80% capacity

CRITICAL:
  no durable checkpoint progress during active source writes
  or resume history lost
  or DLQ contains unresolved high-severity events
  or consumer lease owner missing
```

Đây là ví dụ; hệ payment/notification chính thức cần thresholds theo business SLA.

### 52.1. Oplog window vs consumer lag

Nếu oplog window chỉ 2 giờ và consumer lag đã 90 phút, cần hành động sớm. Không chờ đến khi resume thất bại.

### 52.2. Low lag không chứng minh không mất dữ liệu

Một worker có thể checkpoint rồi **skip poison events**. Dashboard lag gần 0 vẫn có thể sai business state. Theo dõi DLQ, duplicates và reconciliation.

---

## 53. Kiểm thử cần MongoDB thật

Để test Change Streams, cần:

- Replica set/sharded cluster hỗ trợ.
- Đủ permissions để mở stream.
- Consumer start và ready trước trigger test event.
- Namespace riêng để tránh nhiễu từ tests khác.
- Durable checkpoint store/consumer ID riêng.
- Cleanup cursors và workers khi test kết thúc.

Một in-memory mock `MongoCollection` không chứng minh khả năng resume, oplog history, invalidate hay real event delivery.

### 53.1. Dùng Testcontainers

Testcontainers MongoDB module cung cấp các cách chạy MongoDB trong môi trường test; API/package có thể thay đổi theo release. Một số version hỗ trợ `MongoDBContainer` với `getReplicaSetUrl()`.

### 53.2. Readiness barrier

Sai:

```text
startConsumerAsync()
insertDocument()
assertReceived()
```

`startConsumerAsync()` có thể trả trước khi stream thực sự được khởi tạo.

Tốt hơn:

```text
start consumer
wait until cursor/subscription is READY
perform test insert with unique correlationId
await matching output event
close resources
```

### 53.3. Tránh `Thread.sleep(500)` thay event condition

CI scheduling, networking và server load thay đổi. Dùng polling với deadline, JUnit timeout và logs có correlation ID.

---

## 54. Test duplicate sau crash trước checkpoint

Fixture:

```text
Checkpoint = E99
Consumer reads E100
Apply target E100 successfully
Simulate crash BEFORE checkpoint save
Restart consumer at E99
Consumer receives E100 again
```

Assertion:

- Read model state vẫn đúng.
- Không có duplicate notification intent.
- Không tăng counter business hai lần.
- Checkpoint cuối cùng tiến đến E100.
- Có metric duplicate/retry nếu đó là kỳ vọng.

### 54.1. Đây là bài test bắt buộc

Nếu architecture không chịu được kịch bản này thì chưa có at-least-once recovery an toàn.

---

## 55. Test lỗi ngay sau checkpoint

Fixture:

```text
Consumer processes E100
Save checkpoint E100
Process crashes
Restart from resumeAfter(E100)
```

Kỳ vọng:

- Không bắt buộc xử lý lại E100.
- E101 vẫn được nhận khi source có history.
- Dữ liệu/side effects E100 đã hoàn tất trước checkpoint.
- Không có gap ở source events.

### 55.1. Không cố test exact sleep timing

Dùng hooks/test doubles cho checkpoint store hoặc failure injection ngay tại ranh giới, không cần đoán thời điểm ngắt process.

---

## 56. Test lịch sử quá cũ

Trong môi trường test có thể tạo oplog window ngắn hoặc mô phỏng lỗi resume history lost ở abstraction layer. Không nên làm nhỏ oplog production chỉ để kiểm thử.

Kỳ vọng:

- Consumer đánh dấu `REBOOTSTRAP_REQUIRED`.
- Không tự xóa token rồi chạy tiếp từ hiện tại một cách im lặng.
- Alert được phát.
- Có runbook phục hồi read model hoặc replay từ durable outbox.
- Không báo consumer healthy trước reconciliation.

### 56.1. Lưu ý lab thực tế

Oplog rollover phụ thuộc tải, kích thước và server version; integration test ép oplog history lost bằng cách tạo hàng triệu writes có thể chậm và không ổn định. Một test suite có thể dùng unit fault injection cho policy, cộng một integration rehearsal có kiểm soát.

---

## 57. Test `invalidate` và rename/drop

Chạy trên collection test riêng:

1. Bắt đầu Change Stream.
2. Chứng minh consumer nhận event bình thường.
3. Drop/rename namespace trong môi trường thử nghiệm.
4. Quan sát invalidate/DDL handling.
5. Xác minh consumer chuyển state phù hợp.
6. Thử recovery policy với `startAfter` khi điều kiện server hỗ trợ.
7. Nếu cần, rebuild read model từ collection mới.

Không `drop()` collection sản xuất để thử consumer.

---

## 58. Test event ordering và concurrency

Tạo các events:

```text
O100 version 1 -> NEW
O100 version 2 -> PAID
O100 version 3 -> REFUNDED
```

Cố tình làm handler version 2 chậm hơn version 3 khi dùng worker pool.

Kỳ vọng:

- Final projection version 3.
- Không bị v2 ghi đè.
- Checkpoint không vượt v2 khi v2 chưa ack.
- Shutdown/restart không mất event.
- Tombstone của delete không bị stale update tạo lại.

### 58.1. Test updateLookup race

Tạo các updates liên tiếp rồi trì hoãn event processing, quan sát semantics của `fullDocument`. Không assert `UPDATE_LOOKUP` luôn bằng exact state ở thời điểm update event.

### 58.2. Test cùng business ID và nhiều events

Không dùng `documentKey._id` làm dedup event key vì sẽ bỏ mất các updates hợp lệ về sau.

---

## 59. Test failure matrix

| Case | Fault | Expected |
| --- | --- | --- |
| Network reset | Cursor mất kết nối | Resume từ durable token |
| Primary election | Stream interrupted | Driver/app recovery theo policy |
| Crash after apply | Effect đã thành công, token chưa lưu | Replay, no duplicate harmful effect |
| Crash after token | Token đã lưu sau ack | Continue subsequent events |
| Token too old | Oplog history lost | Stop + rebootstrap |
| Invalid token | Wrong/corrupt token | Stop, không skip |
| Collection drop | Invalidate | DDL recovery policy |
| Unknown event type | Handler không hỗ trợ | Quarantine/block theo business |
| Downstream 503 | Target unavailable | Backoff, không advance checkpoint |
| Provider response lost | Unknown external outcome | Idempotency/reconciliation |
| Two workers | Duplicate active owner | Lease/fencing + idempotency |
| Out-of-order apply | Older update finishes last | Version/per-key ordering |
| Queue full | Reader faster than sink | Backpressure, no OOM |
| Shutdown mid-event | Stop while processing | Replay unacked event |
| No events for hours | Quiet collection | Consumer stays healthy |
| Bootstrap race | Backfill writes stale state | CDC replay/version corrects |
| Restart with new pipeline | Filter changed | Contract/version/rebootstrap |
| Missing pre-image | Image not retained | Explicit policy, no silent skip |

---

## 60. Security và quyền truy cập

Một consumer Change Stream thường cần quyền phù hợp để theo dõi namespace; ở MongoDB self-managed, roles/privileges liên quan `find` và `changeStream` tùy scope. Quản trị trên Atlas cũng cần role tương ứng.

Các nguyên tắc:

- Least privilege cho source reader.
- Separate credentials cho target writer.
- TLS và secrets manager.
- Không log raw resume token nếu log có nguy cơ lộ thông tin nội bộ; token là metadata nhạy cảm vận hành.
- Không log fullDocument chứa PII theo mặc định.
- Mã hóa checkpoint store và backup thích hợp.
- Phân tách consumer theo tenant/authorization boundary khi cần.
- Dùng correlation ID, not raw personal data.
- Kiểm soát retention của DLQ/processed-events/outbox.
- Bảo vệ API manual replay/rebootstrap khỏi thao tác trái phép.

### 60.1. Resume token không phải khóa xác thực

Không biến token thành public API pagination token hoặc secret authentication credential. Nó chỉ là vị trí stream; quyền truy cập database vẫn cần authorization.

### 60.2. Pre/post-images chứa dữ liệu cũ

Pre-image có thể giữ PII ngay cả sau khi document đã cập nhật/xóa. Data governance/retention phải tính cả image store, DLQ và logs.

---

## 61. Tối ưu hiệu năng và capacity

Các yếu tố:

- Source write/event rate.
- Event payload size.
- Filter pipeline.
- Consumer network/decoding CPU.
- Downstream throughput.
- Checkpoint write frequency.
- Batch size/maxAwaitTime.
- Worker concurrency và ordering.
- Queue depth và oplog retention.
- Pre/post-images overhead.

### 61.1. Đừng mở một stream trên mỗi user

Nếu ứng dụng có một triệu users, mở một triệu Change Streams chỉ để cập nhật một dashboard có thể làm connection/cursor/server resources quá tải.

Thường hợp lý hơn:

```text
A few shared consumers
       |
       v
Filter/route by tenant/user
       |
       v
Message broker / WebSocket gateway
       |
       v
End users
```

### 61.2. Multi-tenant routing

Nếu event chứa `tenantId`, phải bảo đảm consumer/projection không đẩy dữ liệu giữa tenants. Với `delete`, fullDocument có thể không có, vì vậy cần identity/tenant mapping từ documentKey hoặc schema khác.

### 61.3. Avoid polling source unnecessarily

Change Streams có thể giảm nhu cầu query source liên tục, nhưng consumer health, checkpoint và business delivery vẫn cần monitoring.

---

## 62. Sharded cluster: điều cần hiểu

Với sharded MongoDB:

- Có thể watch ở mức collection/database/deployment phù hợp.
- Server/mongos điều phối events từ nhiều shards.
- Resume token và `documentKey` chứa thông tin theo server/sharding semantics.
- Đọc theo một stream có thể có ordering và event metadata khác với single replica set.
- Cross-shard transactions có change events theo commit semantics.
- Consumer phải được cấu hình với MongoDB URI/topology đúng, không tự tail một shard rồi nghĩ có toàn bộ cluster changes.
- Resharding/DDL có thể ảnh hưởng stream và cần tested recovery.

### 62.1. Không phân vùng theo clusterTime một cách tùy tiện

`clusterTime` không thay hoàn toàn resume token hay global per-key ordering protocol. Nếu nhiều worker, phải định nghĩa quyền sở hữu và version.

### 62.2. Database/deployment-wide streams có nhiều noise

Lọc events theo namespace và event type được hỗ trợ; theo dõi số open streams và permission scope.

---

## 63. Change Streams so với polling collection

| Tiêu chí | Change Stream | Polling theo `updatedAt` |
| --- | --- | --- |
| Phát hiện thay đổi | Gần thời gian thực theo oplog | Theo chu kỳ query |
| Deletes | Có delete event phù hợp | Hard delete khó thấy nếu không tombstone |
| Tải query liên tục | Thường ít repeated scans | Có thể nhiều queries/index pressure |
| Resume | Resume token, phụ thuộc history | Marker/time-window do app quản lý |
| Bootstrap | Cần snapshot/backfill riêng | Cũng cần initial state |
| Data type | Database changes | Current document state |
| Reliability | Idempotency/checkpoint/recovery | Idempotency/checkpoint/recovery |
| Topology | Replica set/sharded hỗ trợ | Có thể query cả standalone |
| Long outage | History lost risk | Có thể quét lại current state, nhưng mất transitions |
| Business intent | Không tự cung cấp | Không tự cung cấp |

### 63.1. Khi polling vẫn phù hợp

- Dataset nhỏ, yêu cầu latency thấp không quan trọng.
- Chỉ cần final state, không cần mỗi transition.
- Có indexed immutable/versioned marker.
- Không cần delete events hoặc có tombstone.
- Production topology không hỗ trợ Change Streams.
- Muốn periodic reconciliation đi kèm stream.

### 63.2. Không bỏ reconciliation khi dùng stream

Một repair scan định kỳ có thể phát hiện sai lệch do bug/poison events/incorrect transforms mà lag metric không thấy.

---

## 64. Change Streams so với transactional outbox

| Tiêu chí | Watch business collection | Watch outbox collection |
| --- | --- | --- |
| Event source | Mọi thay đổi DB được quan sát | Business events được ghi có chủ đích |
| Payload | Update diff/fullDocument lookup | Versioned immutable payload |
| Trạng thái lịch sử | Oplog retention | Outbox retention do app thiết kế |
| Domain semantics | Suy luận từ document change | Trực tiếp theo event type |
| Backfill | Phải làm riêng | Có thể replay retained outbox |
| Notification exactly-once | Không tự có | Vẫn cần idempotency |
| Migration scripts | Có thể kích hoạt event | Có thể không tạo domain event nếu không viết outbox |
| Chi phí | Ít thay đổi code ghi source | Thêm outbox collection/transaction |
| Best fit | Cache, projections, search sync | External integrations, business notifications |

Một hệ thống trưởng thành có thể **kết hợp cả hai**: ghi transactional outbox, dùng Change Stream để phát hiện outbox records nhanh, và polling outbox để phục hồi nếu Change Stream bị mất history.

---

# PHẦN VII — RUNBOOK, CHECKLIST VÀ BÀI TẬP

## 65. Runbook khởi động một consumer mới

1. Xác định purpose, source collection và target.
2. Kiểm tra replica set/sharded topology và quyền `changeStream`.
3. Chọn pipeline, event types, schema version.
4. Xác định downstream idempotency key và delivery policy.
5. Thiết kế processed-events/receipt khi cần.
6. Thiết lập checkpoint store bền vững.
7. Xác định có cần historical backfill không.
8. Nếu cần, thiết lập safe capture boundary và bootstrap plan.
9. Triển khai consumer một instance active với ownership.
10. Monitor first event, checkpoint, lag và DLQ.
11. Test restart/cancellation.
12. Triển khai replicas/worker scale theo ordering plan.
13. Reconcile source/target.
14. Chỉ bật business notifications khi SLO và duplicate behavior được chấp nhận.

---

## 66. Runbook khi consumer báo lỗi liên tục

```text
Alert: consumer has no progress
                |
                v
       Is source accessible?
         /              \
       No                Yes
       |                  |
  Check topology       Check cursor error
  auth/network             |
       |           +-------+--------+
       |           |                |
       v        Resumeable?      History lost?
   Backoff          |               |
  and retry         v               v
               Resume from       STOP, mark
               durable token     REBOOTSTRAP
                    |
                    v
               Check target
               idempotency
                    |
                    v
               Check lag/DLQ
                    |
                    v
                 HEALTHY
```

### 66.1. Không xóa checkpoint trong incident nếu chưa đánh giá tác động

Checkpoint là bằng chứng vị trí xử lý đã được xác nhận. Xóa có thể làm mất khả năng xác định chính xác khoảng thay đổi cần replay.

### 66.2. Không công bố phục hồi khi lag thấp nhưng DLQ còn sự kiện quan trọng

Cần reconcile và giải quyết các records lỗi.

---

## 67. Checklist code review

- [ ] Change Stream được mở trên deployment hỗ trợ?
- [ ] Có scope và pipeline đủ hẹp?
- [ ] Không project bỏ event `_id`?
- [ ] Có xử lý event types rõ?
- [ ] Có phân biệt event `_id` và `documentKey._id`?
- [ ] Có hiểu `UPDATE_LOOKUP` và null fullDocument?
- [ ] Delete/replace/invalidate có policy?
- [ ] Có dùng `try-with-resources` và shutdown/cancellation?
- [ ] Không dùng cursor chung cho nhiều threads?
- [ ] Có durable checkpoint store lưu BSON token nguyên vẹn?
- [ ] Checkpoint sau side effect ack?
- [ ] Không checkpoint qua events còn pending?
- [ ] High-watermark/empty batch xử lý an toàn?
- [ ] Có pipeline version/scope metadata?
- [ ] ResumeAfter/StartAfter/startAtOperationTime dùng đúng?
- [ ] Có idempotency cho replay sau crash?
- [ ] Có business idempotency key cho external effects?
- [ ] Có provider/reconciliation strategy khi response unknown?
- [ ] Có worker lease/fencing nếu nhiều instances?
- [ ] Có bounded queue và backpressure?
- [ ] Có per-key ordering hoặc monotonic version?
- [ ] Có tombstone nếu deletes có thể out-of-order?
- [ ] Có strategy khi oplog history lost?
- [ ] Có bootstrap dữ liệu lịch sử?
- [ ] Backfill không ghi đè CDC state mới?
- [ ] Có DLQ/quarantine, retries/backoff và alerts?
- [ ] Có metrics lag/oplog window/checkpoint progress?
- [ ] Không nhầm Change Stream với domain event?
- [ ] Có privacy/tenant authorization và logging an toàn?
- [ ] Có test crash trước và sau checkpoint?
- [ ] Có diễn tập failover, invalidate và rebootstrap?

---

## 68. Bài tập 1 — Gửi thông báo lặp

Consumer nhận event E100, gửi email thành công rồi crash trước khi save checkpoint.

**Hỏi:** Sau restart có thể xảy ra điều gì?

**Đáp án:** E100 có thể được replay và email gửi lại. Cần stable notification ID/idempotency ở provider hoặc delivery ledger, không chỉ resume token.

---

## 69. Bài tập 2 — Checkpoint quá sớm

Consumer lưu token E200 trước rồi mới xử lý E200; target viết thất bại.

**Đáp án:** Restart `resumeAfter(E200)` có thể bỏ qua E200. Phải lưu token sau xử lý thành công.

---

## 70. Bài tập 3 — Lấy key sai

Handler dùng `documentKey._id` làm unique event identity.

**Đáp án:** Các updates khác nhau của cùng document sẽ bị dedup sai. Cần resume token hoặc business event ID/version.

---

## 71. Bài tập 4 — UpdateLookup

Source cập nhật `PAID`, ngay sau đó `REFUNDED`; consumer xử lý event PAID chậm.

**Đáp án:** `fullDocument: UPDATE_LOOKUP` có thể trả trạng thái `REFUNDED`, không phải exact PAID after-image. Nếu cần transition chính xác, dùng domain outbox/pre-post-images phù hợp.

---

## 72. Bài tập 5 — Delete bị bỏ qua

Consumer chỉ xử lý insert và update; source xóa document.

**Đáp án:** Target còn stale data. Cần delete handler hoặc tombstone semantics.

---

## 73. Bài tập 6 — Hai workers

Hai instances cùng đọc stream theo một checkpoint và cùng gọi notification API.

**Đáp án:** Có thể gửi trùng. Cần single active owner/lease/fencing và idempotency.

---

## 74. Bài tập 7 — Ordered per key

Event version 5 và 6 cho cùng order được xử lý song song; version 6 ghi trước, version 5 ghi sau.

**Đáp án:** Final state có thể sai. Cần ordered partition hoặc version-aware conditional writes.

---

## 75. Bài tập 8 — Trống event trong 1 giờ

`tryNext()` nhiều lần trả null.

**Đáp án:** Không có nghĩa consumer đã hoàn tất hoặc stream hỏng; cần health metric/heartbeat và xác định có source writes hay không.

---

## 76. Bài tập 9 — ResumeAfter invalidate

Stream bị invalidate do collection drop, consumer gọi resumeAfter trên invalidate token.

**Đáp án:** Không đúng theo semantics thông thường; xem startAfter cho trường hợp được hỗ trợ và xác định có cần rebuild/read model mới không.

---

## 77. Bài tập 10 — Token quá cũ

Consumer offline 2 ngày nhưng oplog giữ 6 giờ.

**Đáp án:** Resume có thể thất bại do history lost. Không tự start từ hiện tại rồi tuyên bố healthy; cần rebootstrap/reconcile hoặc replay từ event log bền vững.

---

## 78. Bài tập 11 — Initial data

Collection có 10 triệu orders trước khi consumer được deploy; developer chỉ gọi `watch()`.

**Đáp án:** Không tự nhận 10 triệu documents cũ; cần bootstrap/backfill.

---

## 79. Bài tập 12 — Backfill race

CDC áp `PAID`, backfill sau đó ghi `PENDING`.

**Đáp án:** Sai thứ tự/hội tụ. Capture trước và replay sau baseline, hoặc version-aware writes.

---

## 80. Bài tập 13 — `clusterTime` làm checkpoint

Hai events cùng clusterTime, consumer lưu timestamp sau event đầu.

**Đáp án:** Timestamp không định danh duy nhất event; dùng opaque resume token.

---

## 81. Bài tập 14 — Hàng đợi không giới hạn

Reader 10.000 events/s, sink xử lý 100 events/s, queue không bound.

**Đáp án:** Heap tăng vô hạn. Dùng bounded queue/backpressure, scale sink và xem oplog history headroom.

---

## 82. Bài tập 15 — External API không có idempotency

Provider trả timeout, không rõ đã gửi notification chưa.

**Đáp án:** Không thể suy ra chưa gửi. Cần provider status query, reconciliation, hoặc policy chấp nhận/reject duplicate risk; token checkpoint không giải quyết ambiguity.

---

## 83. Bài tập 16 — Pipeline đổi

Consumer v1 chỉ nghe insert; v2 bắt đầu nghe update nhưng dùng lại checkpoint v1.

**Đáp án:** Các updates trước vị trí v1 token đã bị lọc bỏ sẽ không tự tái xuất. Cần pipelineVersion/contract migration, có thể rebootstrap.

---

## 84. Bài tập 17 — Snapshot hiện tại và notification lịch sử

Consumer mất 5 ngày events, chỉ còn current order state.

**Đáp án:** Có thể rebuild read model cuối nhưng không tái tạo chính xác mọi transition/notification lịch sử. Cần domain event log/outbox được giữ đủ lâu.

---

## 85. Bài tập 18 — Multi-tenant

Một delete event chỉ có documentKey `_id`, handler không biết `tenantId` cần xóa ở search index.

**Đáp án:** Thiết kế stable key/mapping có tenant info, hoặc giữ identity lookup/tombstone phù hợp. Không giả định fullDocument hiện diện trên delete.

---

## 86. Bài tập 19 — Consumer restarted khi worker cũ còn sống

Lease chuyển sang B, A trở lại và tiếp tục lưu checkpoint.

**Đáp án:** Cần fencing generation trong target/checkpoint path và worker cũ phải ngừng; lease logic không chỉ kiểm tra một lần khi startup.

---

## 87. Bài tập 20 — Kiểm tra end-to-end

Consumer lag=0 nhưng DLQ còn event thanh toán lỗi.

**Đáp án:** Chưa có chứng cứ hệ thống đúng. Phải xử lý/quarantine có kiểm soát, reconcile business state và chỉ báo healthy theo các điều kiện rõ ràng.

---

## 88. Những ngộ nhận phổ biến

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Change Stream tự gửi notification đúng một lần.” | Delivery có thể lặp sau retry/restart; external effect cần idempotency. |
| “Consumer đã đọc là đã xử lý.” | Chỉ sau downstream ack mới được checkpoint. |
| “Có resume token là không bao giờ mất event.” | Token phụ thuộc history/oplog và stream validity. |
| “Có thể dùng document ID thay resume token.” | Document ID không định danh từng change. |
| “Timestamp đủ để resume mọi event.” | Nhiều events có thể chia sẻ clusterTime. |
| “Change Stream đọc toàn bộ documents cũ.” | Cần bootstrap/backfill. |
| “UPDATE_LOOKUP luôn là state ngay sau event.” | Có thể lookup state mới hơn và có thể null. |
| “Delete có fullDocument như insert.” | Thường chỉ có documentKey; pre-image cần cấu hình riêng. |
| “Không có event nghĩa cursor đã kết thúc.” | tryNext null có thể chỉ là stream idle. |
| “Driver tự resume mọi lỗi mãi mãi.” | Chỉ một số lỗi có thể resume, không thay application recovery. |
| “ResumeAfter dùng được sau invalidate.” | StartAfter có semantics riêng cho một số trường hợp. |
| “StartAfter tự rebuild data.” | Không. |
| “Chỉ lưu token trong RAM đủ cho restart.” | Cần durable checkpoint. |
| “Checkpoint trước apply tránh duplicate nên an toàn.” | Có thể làm mất event. |
| “Ghi retry vào target luôn idempotent.” | `$inc`/append/send external có thể không idempotent. |
| “ReplaceOne idempotent nghĩa ordering không quan trọng.” | Event cũ có thể ghi đè state mới. |
| “Transaction MongoDB bao trùm external email.” | Không. |
| “Unique inbox trước email là exactly-once.” | Crash sau receipt trước email có thể làm mất gửi. |
| “Consumer lag nhỏ là dữ liệu chắc đúng.” | Transform bug, dropped events, DLQ vẫn có thể tồn tại. |
| “Bật queue unbounded sẽ không bao giờ block.” | Có nguy cơ OOM. |
| “Chạy thêm consumer giống nhau tự chia đều công việc.” | Có thể xử lý trùng nếu không có partition ownership. |
| “Oplog window là không giới hạn.” | Có retention và sizing phụ thuộc write rate. |
| “Xóa token rồi watch lại là recovery.” | Có thể bỏ qua toàn bộ khoảng thay đổi cũ. |
| “Snapshot mới khôi phục mọi notification lịch sử.” | Snapshot chỉ chứa state hiện tại. |
| “Collection cùng tên sau drop là cùng stream identity.” | Lifecycle/semantics có thể khác. |
| “Primary failover nghĩa tất cả events mất.” | Có thể resume theo token/history và driver policy. |
| “Một event có một API side effect chắc chắn.” | Business intent có thể cần outbox mapping. |
| “Security không ảnh hưởng CDC.” | Event/fullDocument/pre-image có thể chứa dữ liệu nhạy cảm. |

---

## 89. Tài liệu tham khảo chính thức

1. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — nguyên lý, phạm vi, event schema và resume.
2. [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — event types, metadata, documentKey, updateDescription.
3. [MongoDB Manual — Change Stream Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — vận hành, oplog history, performance và limitations.
4. [MongoDB Manual — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream) — resumeAfter, startAfter và startAtOperationTime.
5. [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — image availability và retention.
6. [MongoDB Manual — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — replication history và window.
7. [MongoDB Java Sync Driver — Monitor Data with Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — Java consumer, resume và options.
8. [MongoDB Java Driver — ChangeStreamIterable Javadocs](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/ChangeStreamIterable.html) — watch configuration.
9. [MongoDB Java Driver — MongoChangeStreamCursor Javadocs](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/MongoChangeStreamCursor.html) — tryNext, getResumeToken và close.
10. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transactions và atomic write boundaries.
11. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — ClientSession và retry semantics.
12. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability và acknowledgment.
13. [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — retention và bất đồng bộ cleanup.
14. [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — các luồng tích hợp streaming qua connector.
15. [MongoDB Java Sync Driver — Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/) — Java/server/driver version support.
16. [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — replica set integration testing.
17. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — khi nào retry được hỗ trợ và ý nghĩa.
18. [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — failover và khả năng availability.

**Lưu ý về phiên bản:** tên event type, pre/post-image options, cursor APIs, timeout behavior, sharded cluster semantics, error labels và Change Stream permissions có thể khác nhau theo MongoDB Server, FCV, Java Driver và topology. Đối chiếu tài liệu ứng với chính phiên bản hệ thống trước khi đưa vào production.

---

## 90. Kết luận

**Change Streams** là công cụ quan trọng để thiết kế hệ thống thông báo thay đổi và đồng bộ dữ liệu gần thời gian thực trên MongoDB. Nhưng Change Stream chỉ là **nguồn change events**, không thay trọn vẹn một hệ thống reliable event processing.

Để consumer đáng tin cậy:

1. Xác định rõ stream scope, event schema và domain semantics.
2. Dùng Java `MongoChangeStreamCursor` và quản lý vòng đời bằng `try-with-resources`.
3. Nhận diện những event types khác nhau, đặc biệt `update`, `delete`, `invalidate`.
4. Hiểu giới hạn của `fullDocument: UPDATE_LOOKUP` và pre/post images.
5. Lưu **resume token opaque BSON** bền vững sau khi xử lý thành công.
6. Thiết kế at-least-once replay bằng idempotency, stable business keys và receipts/outbox khi cần.
7. Bảo đảm ordering, version hoặc tombstones để event cũ không ghi đè state mới.
8. Khi mất kết nối, resume từ checkpoint; khi history lost, dừng và **rebootstrap/reconcile**, không tự bỏ qua.
9. Bootstrap dữ liệu lịch sử đúng cách, tránh gap hoặc backfill ghi đè CDC.
10. Có worker lease/fencing, bounded queue, retry/backoff, metrics và failure-injection tests.

**Nguyên tắc cuối cùng:** đừng xem “đã thấy event” là “đã hoàn tất nghiệp vụ”. Chỉ khi side effect được xác nhận theo một giao thức có thể replay an toàn, checkpoint đúng thứ tự và recovery path được kiểm thử, consumer mới đủ tin cậy để đưa vào vận hành.
