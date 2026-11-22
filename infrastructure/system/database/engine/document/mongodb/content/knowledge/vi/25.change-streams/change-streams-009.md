# Điều tiết tốc độ tiêu thụ, độ trễ và khôi phục sau gián đoạn với MongoDB Change Streams

## Mục tiêu bài học

MongoDB **change streams** cho phép ứng dụng nhận biết những thay đổi đã được commit trên collection, database hoặc deployment tương ứng. Nhưng triển khai change stream trong production không chỉ là gọi `watch()` và đọc cursor liên tục. Nếu nguồn sinh sự kiện nhanh hơn khả năng xử lý, consumer có thể hết bộ nhớ hoặc tụt quá xa lịch sử oplog. Nếu tiến trình bị crash, network đứt hoặc MongoDB bầu primary mới, hệ thống phải biết **tiếp tục từ đâu**, **event nào đã xử lý**, và **khi nào cần tái đồng bộ**.

Bài thuộc **Database Engine Document MongoDB → Change stream → Điều tiết tốc độ tiêu thụ, độ trễ và khôi phục sau gián đoạn**. Các mục tiêu cụ thể:

1. Hiểu đường đi từ MongoDB oplog đến change stream cursor và ứng dụng tiêu thụ.
2. Phân biệt arrival rate, successful processing rate, backlog, queue depth, processing latency và checkpoint lag.
3. Dùng `batchSize`, `maxAwaitTimeMS`, `next()` và `tryNext()` đúng mục đích.
4. Xây backpressure bằng bounded queue, semaphore, rate limiting và concurrency control.
5. Lưu resume token **nguyên dạng BSON** sau khi side effect thành công.
6. Dùng `resumeAfter`, `startAfter` và `startAtOperationTime` đúng tình huống.
7. Phát hiện oplog history không còn và khôi phục bằng snapshot/reconciliation thay vì âm thầm mất event.
8. Thiết kế handler idempotent và checkpoint không vượt các event chưa xử lý khi dùng nhiều workers.
9. Xử lý MongoDB primary election, reconnect, invalidate, schema errors, downstream timeout và graceful shutdown.
10. Hiểu tác động của `fullDocument:"updateLookup"`, filters và sharded change streams tới hiệu năng.
11. Xây ví dụ mongosh/Java Sync Driver và hệ thống metrics, runbook, fault-injection tests.

> **Thông điệp chính:** Đọc được event không đồng nghĩa **đã xử lý**. Resume token phải biểu diễn **tiến độ đã xử lý an toàn**, không chỉ vị trí cuối cùng driver đã fetch.

---

## 1. Change stream hoạt động như thế nào?

### 1.1. Luồng thay đổi

Một ứng dụng ghi:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);
~~~

Change stream có thể phát ra change event tương ứng:

~~~javascript
{
  _id: {
    _data: "opaque-resume-token"
  },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-101"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
~~~

Đây là hình dạng **minh họa**; trường và giá trị cụ thể phụ thuộc MongoDB version, loại event và tùy chọn stream.

### 1.2. Sơ đồ kiến trúc

~~~text
Ứng dụng ghi
     |
     v
MongoDB replica set / sharded cluster
     |
     v
Oplog và change stream infrastructure
     |
     v
Change stream cursor
     |
     v
Driver nhận batches bằng getMore
     |
     v
Consumer / bounded queue / workers
     |
     v
Downstream side effect được ACK
     |
     v
Lưu checkpoint resume token bền vững
~~~

MongoDB server biết event đã được trả từ cursor, nhưng **không biết** liệu hệ thống search, cache, analytics hay API bên ngoài đã xử lý thành công chưa. Ứng dụng phải quản lý phần đó.

### 1.3. Change streams cần loại deployment nào?

Change streams hoạt động trên replica sets và sharded clusters hỗ trợ tính năng, với server/driver version và quyền truy cập phù hợp. Standalone `mongod` thông thường không cung cấp change streams như replica set. Để học một máy, có thể dùng **single-node replica set**; nó không có high availability trước lỗi máy.

### 1.4. Phạm vi quan sát

| Cách mở | Phạm vi |
|---|---|
| `db.orders.watch()` | Collection orders |
| `db.watch()` | Database hiện tại |
| `MongoClient.watch()` trong driver | Deployment-wide theo quyền/khả năng |
| `collection.watch(pipeline)` | Collection với pipeline lọc/biến đổi hợp lệ |

Đừng mở một stream toàn cluster cho workload chỉ cần một collection nếu điều đó tạo chi phí không cần thiết.

---

## 2. Change streams không tự thay thế message broker

Kafka hoặc RabbitMQ có consumer groups, message acknowledgment, routing và retention theo semantics riêng. MongoDB change stream dùng **cursor** và **resume token**; event từ cursor chưa tự có trạng thái “consumer nghiệp vụ đã ACK”.

Ví dụ:

~~~text
MongoDB đưa event E101 cho consumer
       |
       v
Consumer gọi cursor.next()
       |
       v
Ứng dụng crash
       |
       v
Chưa cập nhật search index
~~~

Nếu consumer lưu token E101 **ngay khi nhận**, khi restart với `resumeAfter(E101)` nó có thể bỏ sót E101. Nếu consumer chưa checkpoint, E101 được đọc lại và cần xử lý idempotent.

### 2.1. Ba mốc phải phân biệt

1. **Fetched:** driver nhận event.
2. **Processed:** handler hoàn thành side effect và được xác nhận.
3. **Checkpointed:** token được persist bền vững.

Không được coi ba mốc là một.

### 2.2. Tại sao oplog retention quan trọng?

Thay đổi chỉ có thể resume nếu lịch sử cần thiết còn khả dụng. Khác một event log được thiết kế giữ nhiều tháng/năm, oplog có thời gian lưu phụ thuộc dung lượng, write rate và cấu hình. Consumer quá chậm hoặc offline quá lâu có thể mất khả năng resume từ token cũ.

---

## 3. Arrival rate, processing rate và backlog

### 3.1. Định nghĩa

- `λ`: tốc độ phát sinh change events, events/second.
- `μ`: tốc độ **xử lý thành công**, events/second.
- `B`: backlog events chưa xử lý xong.
- `L`: độ trễ, seconds/milliseconds.

Trong điều kiện gần đúng với tốc độ ổn định:

\[
\frac{dB}{dt}\approx\lambda-\mu
\]

### 3.2. Ví dụ nguồn nhanh hơn consumer

Giả sử:

~~~text
Arrival rate   : 250 events/s
Processing rate: 180 events/s
Backlog growth :  70 events/s
~~~

Sau hai giờ:

\[
B \approx 70 \times 7200 = 504\,000\ \text{events}
\]

Đây là **ước lượng** theo mô hình đơn giản. Events có thể nằm trong oplog, driver buffer, application queue hoặc đã xử lý nhưng chưa checkpoint. MongoDB không tự giữ một con số business backlog chính xác cho ứng dụng.

### 3.3. Tốc độ bắt kịp

Nếu tăng processing capacity lên 500 events/s trong khi nguồn tiếp tục tạo 250 events/s:

~~~text
Catch-up net rate = 500 - 250 = 250 events/s
~~~

Với backlog 504.000:

\[
504000/250=2016\text{ giây}\approx33{,}6\text{ phút}
\]

Không biến kết quả toán học thành cam kết SLA: còn retry, network, disk, out-of-order, throttling và sự cố.

### 3.4. Khi `μ <= λ` kéo dài

Backlog tăng hoặc không giảm. Nếu consumer checkpoint quá cũ so với oplog window, lần resume sau crash có thể gặp `ChangeStreamHistoryLost` hoặc lỗi tương tự.

### 3.5. Không nhầm throughput với khả năng đọc

Một fetch thread có thể nhận 1.000 events/s, nhưng downstream chỉ hoàn tất 100/s. Báo cáo “throughput 1.000/s” là sai nếu mục tiêu là business processing. Đo **processed/s**, failed/s, retry/s, queue depth và checkpoint progress riêng biệt.

---

## 4. Độ trễ gồm nhiều lớp

### 4.1. Timeline

~~~text
T0  MongoDB commit
T1  Change được stream quan sát
T2  Driver nhận event
T3  Event vào handler
T4  Downstream xác nhận success
T5  Checkpoint được persist
~~~

### 4.2. Metrics

| Metric | Định nghĩa |
|---|---|
| Source-to-receive | T2 - T0 |
| Queue wait | T3 - T2 |
| Handler latency | T4 - T3 |
| End-to-end processing | T4 - T0 |
| Checkpoint latency | T5 - T0 |
| Oldest unprocessed age | Thời gian event lâu nhất chưa hoàn tất chờ đợi |
| Checkpoint staleness | Khoảng cách tiến độ nguồn so với token đã lưu |

Một hệ thống có average latency rất thấp vẫn có thể có một event bị kẹt hàng giờ. Theo dõi p95/p99 và **oldest unprocessed age**.

### 4.3. `clusterTime` không phải wall-clock Date

`clusterTime` thường là BSON Timestamp logic; không tự coi nó là JavaScript Date để làm phép trừ chính xác millisecond. Một số MongoDB version có `wallTime` trên change event với semantics riêng.

Muốn đo latency chặt chẽ, dùng nguồn thời gian đã định nghĩa (business event time, server wallTime phù hợp, consumer received time) và chú ý clock skew. Nên ghi rõ phương pháp tính trong dashboard.

### 4.4. Những nguyên nhân làm lag tăng

- MongoDB có write burst.
- Event handler CPU-bound.
- Downstream 429 hoặc 5xx.
- Cache/search index cập nhật chậm.
- Consumer queue quá dài.
- Nhiều sự kiện dùng `fullDocument:"updateLookup"` gây thêm workload.
- Cursor reconnect liên tục.
- Một poison event chặn thứ tự.
- Chạy song song nhưng vẫn phải serialize theo cùng aggregate.
- Sharded stream điều phối nhiều shards và network.

---

## 5. Backpressure: bảo vệ bộ nhớ và downstream

### 5.1. Anti-pattern unbounded queue

~~~text
MongoDB: 500 events/s
       |
       v
Fetch: 500 events/s
       |
       v
Queue không giới hạn
       |
       v
Handler: 100 events/s
~~~

Queue tăng 400 events/s và có thể gây out-of-memory. Đọc nhanh không có nghĩa xử lý tốt.

### 5.2. Bounded queue

~~~text
Change stream
      |
      v
Bounded queue, ví dụ 128 events
      |
      v
8 workers, tối đa 16 concurrent calls
      |
      v
Downstream API + ACK
      |
      v
Checkpoint tiến độ liên tục đã hoàn thành
~~~

Khi queue đầy, fetch thread **tạm chờ**. RAM được giới hạn dù nguồn vẫn tạo changes.

### 5.3. Bounded queue không giữ oplog mãi mãi

Khi consumer ngừng fetch, MongoDB vẫn ghi. Nếu kéo dài quá retention, resume history có thể mất. Bounded queue chống OOM; để chống gap cần capacity, retention, durable intermediary và recovery strategy.

### 5.4. Rate limiting

- **Semaphore:** tối đa N requests đồng thời.
- **Token bucket:** tối đa X requests/second.
- **Per-key serial lane:** xử lý tuần tự cho cùng aggregate.
- **Backoff/jitter:** giảm retries khi downstream lỗi.
- **Circuit breaker:** ngừng gọi hệ thống đang lỗi liên tiếp trong một khoảng.

Ví dụ search service cho tối đa 200 updates/s, tăng workers lên 200 không giúp nếu nó vẫn bị 429. Phải giới hạn tốc độ dựa trên capacity thực của destination.

### 5.5. Không drop event nếu SLA không cho phép

Nếu nguồn là log telemetry không quan trọng, sampling/drop có thể được đồng ý rõ trong hợp đồng dữ liệu. Nhưng với orders/payments/financial projection, **không drop rồi checkpoint vượt event**. Nếu không theo kịp, cần alert và chiến lược durable staging hoặc scale phù hợp.

---

## 6. `batchSize` điều chỉnh kích thước batch

Change streams dùng aggregation cursor và `getMore`. `batchSize` định nghĩa số documents mong muốn cho mỗi batch, trong giới hạn tương ứng.

~~~javascript
const stream = db.orders.watch(
  [],
  {
    batchSize: 50
  }
);
~~~

### 6.1. Batch nhỏ

Ưu điểm:

- Có thể giảm dữ liệu/peak memory mỗi lần nhận.
- Phù hợp khi handler chậm và queue nhỏ.

Nhược điểm:

- Nhiều getMore/network round trips.
- Tăng overhead nếu handler rất nhanh.

### 6.2. Batch lớn

Ưu điểm:

- Giảm số round trips khi throughput lớn.

Nhược điểm:

- Tăng memory in-flight.
- Có thể tạo batch mà nhiều events chưa xử lý.
- Không làm downstream chạy nhanh hơn nếu bottleneck ở API ngoài.

### 6.3. Batch size không phải rate limiter

`batchSize:50` **không** đồng nghĩa tối đa 50 events/giây. Nếu source và consumer nhanh, driver có thể nhận nhiều batch mỗi giây. Rate limit thật phải ở logic ứng dụng.

### 6.4. Cách benchmark

Thử batchSize 10, 50, 200 và đo events processed/s, getMore latency, queue depth, heap/RSS, downstream errors và p99 completion latency.

Không có giá trị tối ưu chung mọi hệ thống.

---

## 7. `maxAwaitTimeMS` là thời gian chờ getMore

Khi stream chưa có event mới, server có thể chờ trong một getMore request.

~~~javascript
const stream = db.orders.watch(
  [],
  {
    batchSize: 50,
    maxAwaitTimeMS: 1000
  }
);
~~~

### 7.1. Điều tham số này làm

Nó định hướng thời gian chờ một lượt getMore khi chưa có dữ liệu. Nó ảnh hưởng responsiveness/round trips trong các điều kiện thực tế.

### 7.2. Điều nó không làm

- Không bắt server chỉ gửi tối đa một batch/giây.
- Không giới hạn events processed/second.
- Không cam kết end-to-end latency dưới 1000 ms.
- Không tự ghi resume checkpoint.
- Không xác định handler deadline.

### 7.3. Các timeout khác

| Timeout | Nội dung |
|---|---|
| `maxAwaitTimeMS` | Chờ event ở getMore |
| Server selection timeout | Chọn MongoDB server thích hợp |
| Socket timeout | Network I/O |
| Handler timeout | Downstream effect |
| Backoff delay | Chờ trước retry |
| Shutdown grace period | Đợi events in-flight hoàn tất |

Không gộp mọi timeout thành một config rồi cho rằng chúng cùng ngữ nghĩa.

---

## 8. `next()`, `hasNext()` và `tryNext()`

### 8.1. Blocking loop trong mongosh

~~~javascript
const stream = db.orders.watch();

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
~~~

Ví dụ phù hợp để học. Nhưng xử lý production còn cần shutdown, checkpoint, retry và observability.

### 8.2. Java `tryNext()`

Với MongoDB Java Sync Driver, cursor có thể trả `null` khi hiện chưa có event:

~~~java
ChangeStreamDocument<Document> event = cursor.tryNext();

if (event == null) {
    // Hiện không có change phù hợp ở lần thử này.
    // Không có nghĩa stream đã vĩnh viễn kết thúc.
}
~~~

Không tự coi null là lỗi. Tránh busy spin nếu API trả nhanh liên tục; dùng `maxAwaitTime` và scheduling phù hợp.

### 8.3. Empty batches

Driver/server có thể công bố **post-batch resume token** ngay cả khi batch không chứa event trả về. Token đó phản ánh vị trí stream theo API, nhưng **không** chứng minh những events đã giao cho worker đều xử lý xong.

Không checkpoint token mới hơn các events vẫn đang in-flight.

---

## 9. Resume token là vị trí đọc, không phải business ACK

Một change event thường có field `_id` chứa resume token:

~~~javascript
{
  _id: {
    _data: "opaque-bson-token"
  },
  operationType: "insert",
  documentKey: {
    _id: "ORD-101"
  }
}
~~~

### 9.1. Token phải được coi là opaque

Đừng cố parse chuỗi `_data` để lấy thời gian, document ID hoặc shard rồi tự sắp xếp. Token do server tạo; phải dùng với change stream API và giữ nguyên kiểu BSON.

### 9.2. Lưu checkpoint bền vững

Ví dụ checkpoint document:

~~~javascript
{
  _id: "orders-indexer-v1",
  resumeToken: {
    _data: "token-do-MongoDB-cap"
  },
  updatedAt: ISODate("2026-11-14T04:00:00Z"),
  checkpointVersion: 1
}
~~~

Token trong ví dụ chỉ minh họa hình dạng, không dùng token giả để gọi `resumeAfter`.

### 9.3. Không chỉ lưu timestamp

`documentKey._id` và `clusterTime` không thay thế resume token chính xác. Nhiều changes có thể xuất hiện cùng timestamp; sharded topology và resume semantics phức tạp hơn.

### 9.4. Nên lưu token ở đâu?

Trong production, thường dùng durable checkpoint store như MongoDB collection với write concern phù hợp. Nếu container restart, memory hoặc filesystem ephemeral có thể biến mất. Với nhiều instances, checkpoint store còn cần ownership/fencing.

---

## 10. Checkpoint trước hay sau xử lý?

### 10.1. Sai: lưu token trước handler

~~~text
Read E101
   |
Save token E101
   |
Crash
   |
Handler chưa tạo side effect
   |
Restart resumeAfter(E101)
   |
E101 có thể mất khỏi consumer state
~~~

### 10.2. Đúng: xử lý thành công rồi lưu token

~~~text
Read E101
   |
Handle E101
   |
Downstream ACK / local commit
   |
Persist token E101
~~~

Nếu crash giữa handler và checkpoint, E101 được phát lại. Handler phải **idempotent**.

### 10.3. Ma trận crash

| Thời điểm crash | Effect | Checkpoint | Sau restart |
|---|---|---|---|
| Trước khi fetch | Chưa | E100 | Đọc E101 |
| Sau fetch, trước handler | Chưa | E100 | Đọc lại E101 |
| Đang xử lý | Chưa chắc | E100 | Replay E101 |
| Sau effect success, trước checkpoint | Đã | E100 | Replay E101, cần dedupe |
| Sau checkpoint success | Đã | E101 | Tiếp tục sau E101 |
| Checkpoint trước effect (sai) | Chưa | E101 | Bỏ qua E101 |

### 10.4. Chỉ ACK side effect khi thật sự hoàn tất

Gọi API async và đặt job vào executor không phải completed. Nếu downstream là broker, chờ broker acknowledgment theo policy. Nếu là MongoDB read model, đợi transaction/write concern success. Nếu là HTTP, xử lý timeout và idempotency key.

### 10.5. Checkpoint write timeout

Nếu save checkpoint bị timeout, nó có thể đã ghi hoặc chưa. Restart phải đọc lại checkpoint thực tế, không dựa vào giả định. Nếu token chưa được ghi, event replay; handler cần idempotent.

---

## 11. `resumeAfter`, `startAfter` và `startAtOperationTime`

### 11.1. `resumeAfter`

Với token của event đã xử lý:

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    resumeAfter: savedToken
  }
);
~~~

Tạo stream bắt đầu **sau** token theo semantics MongoDB nếu token hợp lệ và lịch sử còn.

### 11.2. `startAfter`

Khi stream nhận **invalidate** vì thao tác namespace được hỗ trợ như collection drop/rename, `resumeAfter` không thể dùng để resume **sau invalidate** theo cách thông thường. `startAfter` được thiết kế để bắt đầu sau token invalidate khi điều kiện cho phép.

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    startAfter: invalidateToken
  }
);
~~~

Nhưng drop/recreate có thể làm downstream read model cũ không còn hợp lệ; cần quyết định rebuild/reconciliation.

### 11.3. `startAtOperationTime`

Nếu có một **BSON Timestamp** phù hợp:

~~~javascript
const stream = db.orders.watch(
  [],
  {
    startAtOperationTime: someTimestamp
  }
);
~~~

Đây không phải `new Date()` hoặc chuỗi ISO tùy ý. Cần lịch sử oplog tương ứng và khả năng version phù hợp.

### 11.4. Không có token

~~~javascript
db.orders.watch();
~~~

thường bắt đầu theo điểm hiện tại khi mở stream, **không tự đọc toàn bộ historical documents**. Khi xây search index lần đầu, phải thực hiện bootstrap snapshot + catch-up.

### 11.5. Bảng quyết định

| Trường hợp | Hướng |
|---|---|
| Restart bình thường có token | `resumeAfter` |
| Muốn mở sau invalidate token | `startAfter` |
| Có operation Timestamp hợp lệ | `startAtOperationTime` |
| Chỉ quan tâm thay đổi mới | Watch từ current point có chủ đích |
| Token history lost | Rebuild/reconcile, không tự reset |
| Chưa có checkpoint nhưng nguồn có dữ liệu | Snapshot/bootstrap + catch-up |

Không khai báo nhiều start-position options đồng thời trong một watch call.

---

## 12. Oplog history lost và nguy cơ mất dữ liệu

### 12.1. Oplog không giữ vô hạn

Oplog là lịch sử replication/change stream được MongoDB quản lý với giới hạn dung lượng/retention theo deployment. Khi write load tăng, thời gian lịch sử còn giữ có thể rút ngắn.

~~~text
Oplog có lịch sử:
  09:00 --------------------------- 10:00

Consumer checkpoint:
  08:30

Consumer restart lúc 10:00:
  token 08:30 có thể không còn resume được
~~~

### 12.2. Lỗi history lost

MongoDB có lỗi dạng `ChangeStreamHistoryLost` trong các tình huống không còn lịch sử cần resume. Không retry vô hạn cùng token cũ: nếu oplog đã bỏ lịch sử, ngủ thêm 10 giây không làm lịch sử quay lại.

### 12.3. Anti-pattern nguy hiểm

~~~javascript
try {
  consume();
} catch (error) {
  db.orders.watch(); // Mở mới từ hiện tại, bỏ gap.
}
~~~

Nếu ứng dụng yêu cầu cập nhật search/projection chính xác, mở từ now sau history lost có thể bỏ sót thay đổi mà hệ thống không phát hiện.

### 12.4. Khôi phục đúng theo yêu cầu business

Nếu no-gap là yêu cầu:

1. Alert và dừng normal consumer.
2. Phân loại lỗi/token/source scope.
3. Xác định nguồn sự thật: current collection, event log, outbox, backup/PITR.
4. Rebuild read model hoặc reconcile entity/version.
5. Bảo vệ **khoảng thay đổi xảy ra trong lúc rebuild**.
6. Thiết lập checkpoint mới theo quy trình cutover an toàn.
7. Chạy kiểm thử consistency trước khi báo service khỏe.

Nếu chỉ xử lý telemetry được phép mất, có thể reset từ now **theo chính sách được chấp nhận và có log**, không âm thầm.

### 12.5. Monitor oplog window

Theo dõi:

- Kích thước oplog.
- Khoảng thời gian giữa oldest/latest oplog positions.
- Write burst rate.
- Consumer checkpoint staleness.
- Replication lag.
- Time-to-history-loss khi workload tăng.

Không giả định “oplog hôm qua giữ 12 giờ nên hôm nay chắc vẫn 12 giờ”.

---

## 13. Bootstrap snapshot + change stream không bị gap

### 13.1. Cách triển khai dễ sai

~~~text
1. Scan toàn bộ orders để xây search index.
2. Sau khi scan xong, mở watch từ hiện tại.
~~~

Một order thay đổi giữa bước 1 và bước 2 có thể không nằm trong snapshot chính xác và cũng không được stream nhận. Đây là **gap**.

### 13.2. Mô hình đúng ở mức kiến trúc

- Xác lập điểm bắt đầu nhận changes hoặc mở stream và lưu events an toàn.
- Snapshot dữ liệu nguồn theo consistency requirements.
- Xây read model trên dữ liệu snapshot.
- Áp dụng events xảy ra trong quá trình snapshot, theo event version/ID.
- Bắt kịp source rồi chuyển sang live processing.
- Ghi durable checkpoint sau khi effects hoàn tất.

### 13.3. Không giữ backlog bootstrap vô hạn trong RAM

Scan hàng triệu documents có thể kéo dài. Nếu ghi changes vào một memory list không giới hạn, ứng dụng vẫn có thể OOM. Cần durable staging hoặc chiến lược partition/batch có thể phục hồi.

### 13.4. Nếu chỉ cần trạng thái cuối

Một cache/search projection có thể được rebuild toàn bộ và đối soát định kỳ nếu business chấp nhận eventual convergence. Nhưng nếu cần **từng transition event để audit/finance**, change stream oplog hữu hạn không nên là nguồn lịch sử duy nhất. Cân nhắc transactional outbox/event log/broker có retention phù hợp.

---

## 14. Resumable errors, reconnect và retry

### 14.1. Các tình huống

- Network đứt.
- MongoDB primary election.
- Server selection timeout.
- Cursor bị đóng.
- Server restart.
- Token không hợp lệ.
- History lost.
- Invalidate event.
- Handler lỗi nghiệp vụ.
- Downstream 429/5xx.

### 14.2. Driver resume khác application recovery

Official MongoDB drivers có thể tự resume change stream khi gặp một số **resumable errors** theo change stream spec. Nhưng driver không biết downstream đã xử lý thành công đến đâu, và không lưu ứng dụng checkpoint qua process restart nếu bạn không triển khai.

**Driver auto-resume không thay application checkpoint.**

### 14.3. Retry loop

~~~text
while service is running:
    token = readDurableCheckpoint()
    try:
        stream = openWatch(resumeAfter=token)
        while running:
            change = cursor.tryNext()
            if change exists:
                handleIdempotently(change)
                persistCheckpoint(change.resumeToken)
    catch temporary/resumable:
        close cursor
        bounded backoff + jitter
        reopen using durable checkpoint
    catch history-lost / invalid token:
        alert
        stop normal consumption
        reconcile/bootstrap
    catch poison business event:
        do not checkpoint past it
        retry/quarantine with policy
~~~

### 14.4. Tránh retry storm

Một loop mở watch mới hàng trăm lần mỗi giây khi MongoDB đang outage có thể gây load và log noise. Dùng exponential backoff, jitter, retry budget và health signals.

### 14.5. Không reset checkpoint khi đọc checkpoint store bị lỗi

Lỗi truy cập checkpoint database **khác** với checkpoint chưa từng tồn tại. Nếu read checkpoint timeout, fail closed/đợi retry theo policy, không mở stream từ now.

---

## 15. Idempotent processing

### 15.1. Vì sao replay là bình thường?

Giả sử E101 đã được apply vào search index nhưng process crash trước save token. Restart từ E100 đọc E101 lại. Đó là hệ quả hợp lý khi ưu tiên không mất event.

### 15.2. Idempotent upsert

Nếu change event phản ánh trạng thái order version 2, handler có thể upsert projection dựa trên aggregate ID/version. Không dùng thao tác cộng/trừ mù khi replay.

~~~javascript
db.orderProjections.updateOne(
  {
    _id: "ORD-101",
    version: 1
  },
  {
    $set: {
      status: "PAID",
      version: 2
    }
  }
);
~~~

Ví dụ trên chỉ cập nhật khi projection tồn tại với version 1. Với trạng thái chưa tồn tại hoặc concurrent writes, cần thiết kế insert/upsert và conflict handling riêng.

### 15.3. Dùng inbox marker

~~~javascript
{
  _id: "search-indexer:EVT-ORD-101-PAID",
  eventId: "EVT-ORD-101-PAID",
  processedAt: ISODate("2026-11-14T12:00:00Z")
}
~~~

Đặt unique key theo consumer+eventId. Nếu marker và local business effect cùng nằm trong MongoDB deployment hỗ trợ transaction, có thể commit chúng **trong cùng transaction**.

### 15.4. External APIs

Gửi email, HTTP payment hoặc broker publication không tự được MongoDB transaction rollback. Cần idempotency key tại destination, outbox hoặc saga/compensation. Checkpoint không tự bảo vệ các side effects bên ngoài.

### 15.5. Cẩn thận `$inc`

~~~javascript
db.metrics.updateOne(
  { _id: "orderPaidCount" },
  { $inc: { count: 1 } },
  { upsert: true }
);
~~~

Nếu E101 replay, `$inc` tăng lần hai trừ khi có dedup/transaction. Chỉ xử lý lại bằng update idempotent hoặc business event marker.

---

## 16. Xử lý song song và contiguous checkpoint

### 16.1. Event fetch order khác completion order

~~~text
Fetch:      E101, E102, E103
Worker A:   E101 mất 10 giây
Worker B:   E102 mất 1 giây
Worker C:   E103 mất 1 giây

Completion: E102, E103, E101
~~~

Nếu lưu token E103 khi E103 hoàn tất, process crash có thể bỏ E101 dù E101 chưa xử lý.

### 16.2. Contiguous completion frontier

Chỉ checkpoint đến event cuối trong **đoạn liên tiếp đã xử lý xong từ checkpoint cũ**.

~~~text
Fetched     E101  E102  E103  E104
Completed    NO   YES   YES    NO
Checkpoint   E100
~~~

Sau E101 hoàn tất, E101–E103 liên tục đã xong → có thể checkpoint E103. E104 vẫn chưa xong nên không checkpoint vượt nó.

### 16.3. Không so sánh opaque tokens như số nguyên

Không dùng lexical comparison của token `_data` để tìm “max token”. Ứng dụng nên gán **local sequence index** theo thứ tự fetch, giữ trạng thái completion và ánh xạ index → BSON token. Checkpoint theo frontier.

### 16.4. Bounded concurrency

Giả sử:

~~~text
MAX_IN_FLIGHT = 64
QUEUE_CAPACITY = 128
WORKERS = 8
~~~

Khi đạt giới hạn, chậm fetch; không tạo hàng nghìn Futures không kiểm soát.

### 16.5. Per-aggregate ordering

Các events cùng order có thể yêu cầu xử lý tuần tự:

~~~text
OrderPlaced  v1
OrderPaid    v2
OrderShipped v3
~~~

Dùng per-key lanes theo `aggregateId` hoặc version gating/gap detection. Parallelism cho các aggregates khác nhau không nhất thiết vi phạm thứ tự của cùng một aggregate.

### 16.6. Checkpoint khi process crash

Completed flags trong memory biến mất. Những events đã xử lý sau checkpoint cũ có thể replay. Consumer idempotency vẫn bắt buộc.

---

## 17. Multi-instance consumers và checkpoint ownership

### 17.1. Hai identical watchers không tự chia work

Nếu instance A và B đều mở:

~~~javascript
db.orders.watch();
~~~

cả hai có thể nhận cùng changes, không tự phân chia như Kafka consumer group.

### 17.2. Active-passive

~~~text
Instance A: owner, mở stream, xử lý và checkpoint
Instance B: standby, theo dõi lease owner
~~~

Khi A lỗi, B tiếp quản từ durable checkpoint.

### 17.3. Active-active

Có thể dùng một dispatcher đọc stream rồi gửi vào broker/durable queue có partition, hoặc thiết kế các consumers theo phân vùng nghiệp vụ rõ ràng.

### 17.4. Fencing và lease

Nếu owner cũ A bị pause rồi lease hết, B tiếp quản. Sau đó A tỉnh lại, không được ghi đè checkpoint của B.

Cần owner token/fencing epoch và conditional checkpoint update. Không dùng “last writer wins” trên một document checkpoint chung.

### 17.5. Không tự tạo offset chung cho nhiều shards

Khi watch sharded cluster, không tự ghép vài token của từng shard thành một position bằng string sort. Dùng API MongoDB hỗ trợ và chọn một ownership/stream model rõ ràng.

---

## 18. `fullDocument:"updateLookup"` và chi phí

### 18.1. Bật lookup

~~~javascript
const stream = db.orders.watch(
  [],
  {
    fullDocument: "updateLookup"
  }
);
~~~

Với update events, MongoDB có thể lấy full document tương ứng; tiện cho consumer cần projection hiện tại.

### 18.2. Giới hạn quan trọng

Full document trong lookup có thể phản ánh trạng thái document **ở thời điểm lookup**, không nhất thiết snapshot đúng ngay tại commit của update event. Nếu document lại bị update/delete trước lookup, kết quả có thể khác hoặc null theo điều kiện.

### 18.3. Chi phí

- Extra reads.
- Larger event payload.
- Network bandwidth.
- Serialization.
- Memory.
- Handler work.

Nếu cần chỉ một field thay đổi, `updateDescription.updatedFields` có thể phù hợp hơn. Nhưng phải xử lý insert/replace/delete và nested/array updates đúng semantics.

### 18.4. Pre/post images

MongoDB có hỗ trợ change stream pre/post images trong một số phiên bản khi cấu hình cho phép. Chúng có lưu trữ/retention/chi phí riêng, không tạo lịch sử vô hạn. Kiểm tra server version, collection options và durability/retention.

---

## 19. Lọc change streams mà không phá resume token

### 19.1. Chỉ nhận những operation types liên quan

~~~javascript
const stream = db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

### 19.2. Không loại `_id` của change event

`_id` là resume token. Pipeline thay hoặc xóa field đó có thể bị server từ chối hoặc làm mất resume semantics.

Không viết:

~~~javascript
{
  $project: {
    _id: 0,
    operationType: 1
  }
}
~~~

trong change stream pipeline nếu nó làm mất event token.

### 19.3. Chuyển đổi payload ở tầng handler

Nếu downstream chỉ cần `documentKey` và `operationType`, trích chúng **sau khi nhận event**; vẫn giữ token đầy đủ cho checkpoint.

### 19.4. Thay đổi filter có thể cần migration

Nếu v1 chỉ watch inserts, v2 thêm updates, không tự coi checkpoint cũ đã bao phủ lịch sử của các updates trước đó. Quyết định cần backfill/reconciliation, thay checkpoint namespace hoặc rollout có chủ đích.

---

## 20. Invalidate event và `startAfter`

### 20.1. Các tình huống

Drop hoặc rename collection có thể gây `invalidate` theo phạm vi stream. Cursor có thể đóng.

### 20.2. Không retry mù

Một invalidate không giống network timeout. Nếu collection đã bị drop, downstream projection có thể cần xóa/rebuild trước khi watch tiếp.

### 20.3. Token sau invalidate

`startAfter` cho phép mở stream sau invalidate token trong trường hợp được hỗ trợ. `resumeAfter` không phải API dùng để resume sau invalidate theo cách thông thường.

### 20.4. Tính đúng của downstream

Nếu collection bị drop/recreate, đơn thuần startAfter không tự xây lại dữ liệu của collection mới hoặc xóa projection cũ. Cần kế hoạch state reset/reconciliation.

---

## 21. Mongosh lab: quan sát và checkpoint

### 21.1. Tạo dữ liệu thử nghiệm

Chạy trên replica set lab:

~~~javascript
use change_stream_lab

db.orders.insertOne({
  _id: "ORD-101",
  status: "NEW",
  amount: 100000,
  updatedAt: new Date()
});
~~~

Không chạy các lệnh xóa rộng trên production để làm lab.

### 21.2. Mở stream

~~~javascript
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
    batchSize: 10,
    maxAwaitTimeMS: 1000,
    fullDocument: "updateLookup"
  }
);

while (stream.hasNext()) {
  const event = stream.next();

  printjson({
    operationType: event.operationType,
    documentKey: event.documentKey,
    resumeToken: event._id
  });
}
~~~

Vòng lặp sẽ chờ events; dừng cursor khi hoàn tất lab. Đây chỉ là demo quan sát.

### 21.3. Phát sinh thay đổi ở phiên thứ hai

~~~javascript
use change_stream_lab

db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);

db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      status: "SHIPPED",
      updatedAt: new Date()
    }
  }
);
~~~

### 21.4. Lưu token sau một handler thành công

Trong một demo **khác** dùng một event đã được nhận:

~~~javascript
const event = stream.next();

// Thay bằng xử lý nghiệp vụ bền vững.
printjson(event);

db.getSiblingDB("change_stream_lab")
  .streamCheckpoints.updateOne(
    { _id: "orders-indexer-v1" },
    {
      $set: {
        resumeToken: event._id,
        updatedAt: new Date()
      }
    },
    { upsert: true }
  );
~~~

Code này giả định handler chỉ in thành công. Với real consumer, đợi downstream ACK trước khi ghi checkpoint.

### 21.5. Restart

~~~javascript
const saved = db.getSiblingDB("change_stream_lab")
  .streamCheckpoints.findOne({
    _id: "orders-indexer-v1"
  });

if (saved && saved.resumeToken) {
  const resumed = db.getSiblingDB("change_stream_lab")
    .orders.watch(
      [],
      {
        resumeAfter: saved.resumeToken
      }
    );

  // Tiếp tục đọc từ sau checkpoint.
}
~~~

Không tự tạo token giả. Không nhầm checkpoint không tồn tại với lỗi kết nối checkpoint store.

---

## 22. Java Sync Driver: consumer tuần tự với durable checkpoint

### 22.1. Mục đích

Ví dụ Java dưới đây minh họa:

- Mở stream trên orders.
- Load BSON resume token từ checkpoint collection.
- Dùng `batchSize` và `maxAwaitTime`.
- Đọc bằng `tryNext()`.
- Chạy handler đồng bộ.
- Lưu token **sau** handler success.

Đây là skeleton cho môi trường lab; production cần external retry supervisor, idempotency, bảo mật, checkpoint durability và bootstrap strategy.

### 22.2. Code Java

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.changestream.ChangeStreamDocument;

import org.bson.BsonDateTime;
import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class OrdersStreamWorker {

    private final MongoCollection<Document> orders;
    private final MongoCollection<BsonDocument> checkpoints;

    public OrdersStreamWorker(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("change_stream_lab");

        orders = db.getCollection("orders");

        checkpoints = db.getCollection(
            "streamCheckpoints",
            BsonDocument.class
        );
    }

    private BsonDocument loadCheckpoint() {
        BsonDocument doc = checkpoints.find(
            Filters.eq("_id", "orders-worker-v1")
        ).first();

        return doc == null
            ? null
            : doc.getDocument("resumeToken");
    }

    private void saveCheckpoint(BsonDocument token) {
        BsonDocument checkpoint =
            new BsonDocument()
                .append(
                    "_id",
                    new BsonString("orders-worker-v1")
                )
                .append("resumeToken", token)
                .append(
                    "updatedAt",
                    new BsonDateTime(
                        System.currentTimeMillis()
                    )
                );

        checkpoints.replaceOne(
            Filters.eq("_id", "orders-worker-v1"),
            checkpoint,
            new ReplaceOptions().upsert(true)
        );
    }

    private void handleIdempotently(
            ChangeStreamDocument<Document> change) {

        // DEMO: phải thay bằng handler thật.
        // Đợi xác nhận bền vững trước khi return.
        System.out.println(
            change.getOperationType()
        );
    }

    public void run() {
        BsonDocument token = loadCheckpoint();

        ChangeStreamIterable<Document> changeStream =
            orders.watch()
                .batchSize(50)
                .maxAwaitTime(
                    1000,
                    TimeUnit.MILLISECONDS
                );

        if (token != null) {
            changeStream =
                changeStream.resumeAfter(token);
        } else {
            // Lần đầu: stream không tự backfill history.
            // Cần explicit bootstrap hoặc "from now".
        }

        try (MongoChangeStreamCursor<
                ChangeStreamDocument<Document>> cursor =
                    changeStream.cursor()) {

            while (!Thread.currentThread().isInterrupted()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    continue;
                }

                handleIdempotently(event);

                // Sau khi effect đã thành công.
                saveCheckpoint(event.getResumeToken());
            }
        }
    }
}
~~~

### 22.3. Giải thích

- `getResumeToken()` trả resume token của change event.
- `resumeAfter(token)` cần token hợp lệ và history còn.
- `tryNext()==null` chỉ thể hiện chưa nhận event trong lần kiểm tra.
- `handleIdempotently` ở đây chỉ là placeholder; production phải bảo đảm side effect bền.
- `saveCheckpoint` chạy sau handler.
- Vì handler và checkpoint tách nhau, crash giữa chúng có thể replay.
- Nếu chưa có checkpoint, đoạn code không backfill documents cũ.

### 22.4. Cần bổ sung cho production

- MongoDB authentication/TLS.
- Write concern phù hợp cho checkpoint.
- Handler idempotency/inbox.
- Bounded error retry.
- History lost differentiation.
- Snapshot bootstrap.
- Monitoring.
- Shutdown lifecycle.
- Checkpoint owner fencing nếu có nhiều instances.
- Alert nếu checkpoint không tiến trong khi source vẫn ghi.

---

## 23. Java: retry supervisor có phân loại lỗi

Pseudocode:

~~~java
int attempt = 0;

while (serviceIsRunning()) {
    try {
        worker.run();
        attempt = 0;

    } catch (RuntimeException error) {

        if (isHistoryLostOrInvalidToken(error)) {
            alertOperator(error);
            stopConsumption();
            break;
        }

        if (!isTemporarilyRecoverable(error)) {
            alertOperator(error);
            stopConsumption();
            break;
        }

        attempt++;
        long delayMillis =
            boundedBackoffWithJitter(attempt);

        sleepSafely(delayMillis);
    }
}
~~~

Đây **không phải code độc lập compile được**: những helper methods là các điểm tích hợp với policy thực tế.

### 23.1. Không bắt mọi lỗi rồi mở stream từ hiện tại

Lỗi mạng có thể resume, nhưng history lost cần reconciliation. Lỗi handler không thể xử lý do schemaVersion sai không tự hết sau 100 retries.

### 23.2. Driver có thể tự resume một số errors

Một số MongoDB driver có auto-resume behavior. Application supervisor không nên mở hàng chục cursors trong cùng thời điểm; phải đóng cursor lỗi và dùng durable checkpoint có kiểm soát.

### 23.3. Khi save checkpoint timeout

Dừng/đọc lại checkpoint bền vững và replay an toàn. Không tự giả định token đã được lưu hay chưa.

---

## 24. Consumer side effect và checkpoint trong cùng transaction

Nếu handler cập nhật **một projection cũng nằm trong cùng MongoDB deployment**, có thể dùng transaction:

~~~text
Read change event
       |
       v
MongoDB transaction:
  insert processed event marker
  update read model
  save checkpoint
       |
       v
commit
~~~

Cách này có thể giảm khoảng crash giữa local effect và checkpoint, nhưng không bao phủ external HTTP/broker.

### 24.1. Inbox marker

~~~javascript
{
  _id: "orders-worker:EVT-101",
  eventId: "EVT-101",
  processedAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

Marker unique giúp nhận diện replay, nếu nằm cùng transaction với effect.

### 24.2. Nếu xử lý nhiều workers

Checkpoint phải là contiguous frontier, không được để worker hoàn thành E103 ghi token khi E101 đang chưa xong. Transaction local không tự giải quyết thứ tự hoàn thành song song.

### 24.3. External side effects

Nếu handler gọi payment API, cần idempotency key và reconciliation. Không cho rằng MongoDB transaction tự rollback external payment.

---

## 25. Post-batch resume token và empty batches

Các response của change stream có thể chứa thông tin resume tiến độ dù batch trống, tùy server/driver API. Trong trường hợp sequential consumer không có in-flight, lưu post-batch resume token hợp lệ theo hướng dẫn có thể giảm khoảng cách token cũ khi ít sự kiện.

**Nhưng nếu còn event trong queue chưa xử lý**, không checkpoint qua nó chỉ vì driver biết vị trí mới hơn.

Quy tắc tổng quát:

~~~text
Durable checkpoint <= vị trí liên tục đã hoàn tất effect.
~~~

Đừng tự diễn giải token theo lexical order để so sánh.

---

## 26. Sharded change streams và chi phí

Khi stream theo dõi sharded collection hoặc deployment, MongoDB có thể phải tổng hợp thay đổi từ nhiều shards và điều phối thứ tự. Điều này có chi phí về network/CPU/latency.

### 26.1. Không tự nối token shards

Sử dụng change stream API, không ghép tokens từng shard thành một offset string thủ công.

### 26.2. Chọn phạm vi stream đúng

Một stream trên collection thường đơn giản hơn theo dõi toàn cluster rồi bỏ 99% events. Chỉ dùng phạm vi lớn khi có yêu cầu.

### 26.3. Theo dõi tài nguyên

Số stream cursors, MongoDB load, getMore latency, memory, network và shard lag. Nhiều idle streams cũng có chi phí.

### 26.4. Namespace changes

Drop/rename/sharding/DDL có thể ảnh hưởng change stream behavior và cần test migrate/rebuild. Đừng tự xem mọi exception là resumable.

---

## 27. Runbook khi consumer bị chậm

### Bước 1: Xác định bottleneck

Kiểm tra event arrival, successful processing throughput, queue depth, handler latency, downstream 429/5xx, MongoDB getMore latency.

### Bước 2: Tính backlog growth

Nếu `λ > μ`, xác định net backlog growth và thời gian cần để catch up sau khi tăng capacity.

### Bước 3: Điều chỉnh backpressure

Bound queue, giới hạn inflight requests, rate limit downstream, tránh OOM.

### Bước 4: Tối ưu payload

Giảm fullDocument lookups nếu không cần, lọc events hợp lệ, tránh convert/serialize dữ liệu lớn.

### Bước 5: Scale đúng hướng

Tăng workers cho các aggregates độc lập; giữ ordering per aggregate hoặc version gating. Không tăng concurrency vượt quota downstream.

### Bước 6: So với oplog window

Nếu checkpoint staleness gần retention window, cảnh báo nguy cơ history lost. Đề xuất tăng retention/capacity hoặc durable intermediary theo workload.

### Bước 7: Quan sát sau thay đổi

Queue depth có giảm không? Checkpoint lag có thu hẹp không? p99 handler latency có tăng? Downstream có bị overload?

---

## 28. Runbook khi consumer mất kết nối

### Bước 1: Phân loại

Network transient, election, cursor killed, invalidate, invalid token, history lost, handler failure hay checkpoint store unavailable?

### Bước 2: Đọc durable checkpoint

Nếu đọc checkpoint lỗi, đừng coi đó là “không có checkpoint”.

### Bước 3: Resume

Với lỗi recoverable, đóng cursor và reopen từ saved token với bounded backoff. Driver cũng có thể auto-resume một số lỗi.

### Bước 4: Không nhảy đến hiện tại

Nếu resume token history lost, **không** tự watch từ now nếu hệ thống yêu cầu no-gap.

### Bước 5: Reconcile

Xác định source of truth; rebuild projection, apply changes trong thời gian rebuild, kiểm tra consistency rồi cutover.

### Bước 6: Kiểm thử idempotency

Các events đã xử lý trước checkpoint có thể replay. Phải bảo đảm không double-charge, double-count hay duplicate notification.

### Bước 7: Ghi incident

Lưu thời điểm mất kết nối, checkpoint trước/sau, history window, events recovered và điểm cần cải thiện.

---

## 29. Monitoring và SLO

| Metric | Mục đích |
|---|---|
| `change_events_received_total` | Tốc độ fetch |
| `change_events_processed_total` | Tốc độ hoàn tất |
| `change_events_failed_total` | Lỗi handler |
| `change_events_replayed_total` | Số lần replay |
| `change_stream_reconnect_total` | Tần suất reconnect |
| `change_stream_history_lost_total` | Số lỗi không resume được |
| `queue_depth` | Mức tải hàng đợi |
| `in_flight_events` | Công việc đang xử lý |
| `oldest_unprocessed_age_seconds` | Sự kiện lâu nhất chưa hoàn tất |
| `handler_latency_ms` | p50/p95/p99 handler |
| `checkpoint_staleness_seconds` | Độ cũ checkpoint |
| `checkpoint_write_errors_total` | Lỗi persist token |
| `oplog_window_seconds` | Lịch sử oplog hiện có |
| `downstream_rate_limit_errors_total` | Lỗi 429/quota |

### 29.1. Đừng chỉ nhìn average

Nếu phần lớn events rất nhanh nhưng một event bị kẹt 1 giờ, average có thể che vấn đề. Đo oldest unprocessed age và tiến độ checkpoint.

### 29.2. SLO mẫu

~~~text
99% event effects hoàn thành trong 5 giây
và không mất event do restart với lịch sử còn khả dụng.
~~~

SLO phải nêu mốc bắt đầu/kết thúc và điều kiện retention, không chỉ nói “real-time”.

### 29.3. Cảnh báo

- Checkpoint không tiến trong khi nguồn vẫn ghi.
- Queue gần đầy.
- `processing rate < arrival rate` kéo dài.
- Oldest unprocessed vượt ngưỡng.
- Oplog window gần bằng checkpoint lag.
- Resume errors tăng liên tục.
- History lost bất kỳ lần nào với no-gap consumer.
- Downstream 429/5xx tăng.
- Handler exceptions bất thường.

---

## 30. Kiểm thử lỗi và khả năng phục hồi

### Test 1 — Consumer chậm hơn producer

Tạo 200 events/s, handler hoàn tất 50/s. Quan sát backlog, queue depth và checkpoint lag. Bounded queue phải ngăn OOM nhưng không tự ngăn oplog history loss.

### Test 2 — Tăng workers

Tăng workers có kiểm soát; đo successful throughput, downstream error rate và per-aggregate ordering.

### Test 3 — Crash sau fetch

Nhận E101, crash trước handler. Restart từ E100, E101 phải được xử lý lại.

### Test 4 — Crash sau handler trước checkpoint

E101 effect thành công, crash trước lưu token. E101 replay; handler phải idempotent.

### Test 5 — Checkpoint store timeout

Save checkpoint mất kết nối. Restart đọc state bền; không bỏ qua event nếu token chưa lưu.

### Test 6 — Primary failover

Trong replica set lab, mô phỏng election và quan sát driver auto-resume/application recovery.

### Test 7 — Oplog history lost

Cho token cũ hơn lịch sử hiện còn trong lab. Consumer phải cảnh báo và chuyển sang reconciliation, không watch từ now một cách ngầm định.

### Test 8 — Invalidate

Drop/rename collection trong lab cô lập, quan sát invalidate và cân nhắc `startAfter` cùng rebuild projection.

### Test 9 — Out-of-order completion

E101 chậm hơn E102/E103. Checkpoint không vượt E101 đến khi E101 hoàn tất.

### Test 10 — Poison event

Schema event không được handler hiểu. Không checkpoint qua lỗi nếu chưa có quyết định quarantine/replay có audit.

### Test 11 — Downstream 429

Rate limit API; consumer phải backoff, giới hạn concurrency, không mất event.

### Test 12 — fullDocument updateLookup

Cập nhật cùng document liên tiếp và xác minh không giả định fullDocument luôn là snapshot của từng transition cũ.

### Test 13 — Lần đầu không token

Consumer mới phải bootstrap nguồn có dữ liệu cũ nếu cần index đầy đủ, không chỉ mở watch.

### Test 14 — BSON token roundtrip

Lưu và đọc lại token từ checkpoint collection, dùng lại trong `resumeAfter`.

### Test 15 — Hai instances cùng checkpoint

Mô phỏng owner A lease hết hạn, B nhận ownership. Kiểm tra A không overwrite checkpoint mới do thiếu fencing.

### Test 16 — Empty batch

Không có event mới nhưng driver nhận post-batch resume info. Đảm bảo không checkpoint vượt những events in-flight.

---

## 31. Bài tập thực hành

### Bài 1: Tính backlog

Arrival 600 events/s, processing 450 events/s trong 30 phút. Tính backlog tích lũy theo giả định tốc độ không đổi.

### Bài 2: Thời gian catch up

Có 240.000 events chưa xử lý; nguồn tiếp tục tạo 200/s, consumer nâng lên 500/s. Tính thời gian dọn backlog và nêu điều kiện của ước lượng.

### Bài 3: batchSize và rate limiter

Dùng `batchSize:20` và giải thích vì sao không phải 20 events/s. Đề xuất token bucket 100 events/s.

### Bài 4: maxAwaitTimeMS

Chọn 1000 ms rồi đo getMore behavior khi stream idle và busy. Nêu các lớp latency khác.

### Bài 5: Bounded queue

Đặt queue 128, max 16 in-flight, 8 workers. Mô tả lúc queue đầy, lúc downstream 429 và lúc shutdown.

### Bài 6: Checkpoint đúng thứ tự

Lấy resume token từ event thật, lưu sau handler, restart với `resumeAfter`. Nêu hậu quả nếu lưu trước handler.

### Bài 7: Idempotency

Xử lý E1 rồi crash trước checkpoint. Thiết kế inbox marker hoặc version-gated projection để E1 replay không tạo effect trùng.

### Bài 8: Contiguous frontier

E1,E2,E3,E4 hoàn thành theo thứ tự E2,E4,E3,E1. Viết checkpoint hợp lệ sau mỗi lần hoàn thành.

### Bài 9: History lost

Một consumer offline lâu hơn oplog window. Viết runbook no-gap gồm alert, rebuild snapshot, catch-up và cutover.

### Bài 10: Bootstrap gap

Tại sao quét documents xong mới mở watch có thể bỏ sót một update? Thiết kế quy trình không gap.

### Bài 11: Java Sync Driver

Viết consumer với `ChangeStreamIterable`, `MongoChangeStreamCursor`, `tryNext`, `resumeAfter` và durable checkpoint. Thêm bounded retry.

### Bài 12: Full document

So sánh `updateDescription` và `fullDocument:"updateLookup"` khi có hai updates liên tiếp trên một document.

### Bài 13: Multi-instance

Hai workers cùng mở watch và dùng một checkpoint ID. Thiết kế lease/fencing hoặc dispatcher-broker để không ghi token sai.

### Bài 14: Per-key ordering

Gắn aggregateId/version cho OrderPlaced, OrderPaid, OrderShipped. Đảm bảo version 2 không overwrite version 3.

### Bài 15: Monitoring

Xây dashboard arrival/success rates, queue depth, checkpoint age, oldest unprocessed event, oplog window, reconnect/error rate và p99 handler latency.

### Bài 16: Recovery testing

Lập kế hoạch fault injection cho network cut, primary election, handler exception, checkpoint error, poison event, history lost, invalidate và shutdown khi có in-flight events.

---

## 32. Câu hỏi ôn tập

1. Change stream lấy thông tin từ cơ chế lịch sử nào của MongoDB?
2. Vì sao MongoDB không tự biết business consumer đã xử lý xong?
3. Arrival rate khác processing rate ra sao?
4. Backlog tăng khi nào?
5. Bounded queue giải quyết vấn đề gì?
6. Bounded queue có tự ngăn mất oplog history không?
7. `batchSize` có phải giới hạn events/s không?
8. `maxAwaitTimeMS` điều khiển việc gì?
9. `tryNext()==null` có phải EOF vĩnh viễn không?
10. Resume token nằm ở đâu trong change event?
11. Tại sao phải coi token là opaque BSON value?
12. Vì sao chỉ checkpoint sau handler ACK?
13. Crash sau handler trước checkpoint gây điều gì?
14. Crash sau checkpoint trước handler nguy hiểm thế nào?
15. `resumeAfter` dùng khi nào?
16. `startAfter` liên quan invalidate như thế nào?
17. `startAtOperationTime` yêu cầu giá trị kiểu gì?
18. Không có token thì watch có replay documents cũ không?
19. History lost xảy ra khi nào?
20. Vì sao không reset từ now một cách ngầm định?
21. Snapshot bootstrap có gap nào?
22. Vì sao cần durable staging khi snapshot lâu?
23. Driver auto-resume khác app recovery ở đâu?
24. Idempotency giúp gì khi replay?
25. Tại sao `$inc` thường không idempotent?
26. Contiguous checkpoint frontier là gì?
27. Vì sao không checkpoint E103 nếu E101 chưa xử lý?
28. Hai identical watchers có tự chia work như consumer group không?
29. Khi dùng shared checkpoint cần fencing vì sao?
30. `fullDocument:"updateLookup"` có những rủi ro nào?
31. Vì sao không được remove event `_id` trong pipeline?
32. Sharded stream có chi phí gì?
33. Metrics nào cho thấy consumer tụt lại?
34. Vì sao oldest unprocessed quan trọng hơn average?
35. Khi downstream trả 429, cần điều tiết thế nào?
36. Khi oplog history mất, cần khôi phục ra sao?
37. Thao tác drop/rename collection ảnh hưởng stream thế nào?
38. Post-batch resume token có thể dùng khi nào an toàn?
39. Tại sao change streams không phải long-term audit log vô hạn?
40. SLO change stream nên định nghĩa mốc nào?

---

## 33. Tổng kết

MongoDB change stream cung cấp thay đổi từ cơ chế oplog/stream server, nhưng một consumer production phải chủ động quản lý **tốc độ**, **độ trễ** và **khả năng phục hồi**.

**Điều tiết tốc độ:** đo nguồn và năng lực hoàn tất thực tế; dùng bounded queue, concurrency limit, rate limiter và backoff. Hiểu `batchSize` là batch tuning, `maxAwaitTimeMS` là getMore waiting, **không** phải rate limit.

**Độ trễ:** đo commit-to-receive, queue wait, handler duration, checkpoint lag và oldest unprocessed age. Khi processing chậm hơn arrival, backlog tăng; nếu checkpoint tụt khỏi oplog retention, khả năng resume có thể mất.

**Khôi phục:** lưu resume token nguyên BSON **sau khi effect thành công**. Sử dụng `resumeAfter` cho restart thông thường, `startAfter` khi mở sau invalidate phù hợp, và `startAtOperationTime` khi có BSON Timestamp hợp lệ. Phân biệt transient errors với history lost; không âm thầm bỏ gap. Với parallelism, checkpoint theo **contiguous completion frontier**, không phải token mới nhất đã fetch.

**Tính đúng của nghiệp vụ:** handler phải idempotent để replay không tạo side effects trùng. Change streams không tự cung cấp consumer groups, exactly-once processing hay infinite replay history. Khi yêu cầu no-gap dài hạn, bổ sung outbox, broker, backup/reconciliation và testing.

Một consumer đáng tin không chỉ giữ cursor mở. Nó phải chứng minh được **đã xử lý đến đâu**, **đang tụt lại bao nhiêu**, **có thể còn lịch sử để catch up hay không**, và **sẽ làm gì khi checkpoint không thể resume**.

## Tài liệu tham khảo

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [MongoDB Manual — db.collection.watch()](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [MongoDB Manual — $changeStream](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/)
- [MongoDB Manual — Change Stream Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/)
- [MongoDB Manual — Replication Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images)
- [MongoDB Manual — Change Streams in Sharded Clusters](https://www.mongodb.com/docs/manual/changeStreams/#sharded-cluster-considerations)
- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [MongoDB Java Sync Driver — Cursors](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/cursor/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
