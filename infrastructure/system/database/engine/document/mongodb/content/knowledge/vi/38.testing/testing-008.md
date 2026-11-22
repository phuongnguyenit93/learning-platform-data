# Kiểm thử mất kết nối, chuyển primary và tiếp tục change stream trong MongoDB

## 1. Bối cảnh: change stream bị ngắt có làm mất sự kiện không?

Giả sử một dịch vụ đồng bộ đơn hàng sử dụng MongoDB Change Streams để cập nhật search index:

~~~text
Orders API -> MongoDB orders
                     |
                     | Change Stream
                     v
              Search Indexer
                     |
                     v
                 Search Index
~~~

Ở 10:00:00, indexer xử lý event `E100` và lưu resume token. Đến 10:00:02, primary MongoDB mất kết nối; một secondary được bầu làm primary mới. Trong thời gian ấy, API tiếp tục ghi `E101`, `E102` và `E103` sau khi election thành công.

Những câu hỏi cần kiểm thử không chỉ là **“ứng dụng có tự reconnect?”**:

1. Consumer có phát hiện cursor bị đóng hoặc lỗi `getMore`?
2. Sau chuyển primary, nó có mở stream trên topology mới?
3. Nó tiếp tục từ **đúng vị trí đã xác nhận xử lý**, hay bỏ qua một số events?
4. Nếu event `E101` được xử lý nhưng token chưa được lưu trước khi process chết, hệ thống có xử lý trùng `E101` sau restart?
5. Nếu outage dài hơn oplog history, có thông báo rõ **không thể resume** và cách khôi phục bằng snapshot/reconciliation?
6. Bên nhận có giữ trạng thái đúng sau những lỗi tạm thời?

Bài thuộc module **Database Engine Document MongoDB**, chương **Kiểm thử**, với đề bài **Kiểm thử mất kết nối, chuyển primary và tiếp tục change stream**.

**Thông điệp:** Kết nối lại được không đồng nghĩa dữ liệu đầu ra chính xác. Kiểm thử phải đo **tính liên tục của luồng, checkpoint, idempotency và khả năng phục hồi sau sự cố**.

## 2. Mục tiêu bài học

Sau bài học, bạn có thể:

- Hiểu Change Streams và mối liên hệ với replica set oplog.
- Phân biệt cursor tạm thời, session/driver, event resume token và durable checkpoint.
- Biết khi nào dùng `resumeAfter`, `startAfter` hoặc `startAtOperationTime`.
- Hiểu lỗi resumable và lỗi không thể phục hồi do oplog history.
- Phân biệt thay primary với consumer process chết, partition network và DNS/TLS failure.
- Xây môi trường test replica set có primary failover thật.
- Dùng `mongosh` để tạo event, lưu token, đóng stream, resume và kiểm tra kết quả.
- Dùng MongoDB Java Sync Driver xây consumer có checkpoint.
- Xử lý đặc điểm Spring Data MongoDB synchronous/reactive change streams.
- Thiết kế checkpoint không tạo lỗ hổng mất sự kiện.
- Chứng minh idempotent processing khi event được đọc lại.
- Kiểm chứng chính xác state sau failover bằng assertions tự động.
- Theo dõi lag, resume attempts, errors, duplicate rate và oplog headroom.
- Xây runbook và checklist production cho change stream consumers.

## 3. Kiến trúc Change Streams

MongoDB Change Streams cho phép theo dõi thay đổi trên:

- **Collection:** `db.orders.watch()` hoặc `collection.watch()`.
- **Database:** `db.watch()`.
- **Deployment:** `MongoClient.watch()` hoặc `Mongo.watch()`, tùy driver và quyền.

Nó hoạt động trên **replica set hoặc sharded cluster**, dựa trên oplog, không có trên standalone MongoDB thuần.

~~~text
Application writes
       |
       v
Replica set PRIMARY
       |
       +----> Replicated oplog
       |             |
       v             v
 SECONDARIES    $changeStream aggregation
                      |
                      v
               Change Stream Cursor
                      |
                      v
                 Java Consumer
                      |
                 process event
                      |
                 persist token
~~~

### 3.1. Change stream không phải queue vô hạn

MongoDB Change Streams là cách đọc thông báo thay đổi từ lịch sử oplog, không thay thế vô điều kiện cho hệ thống message queue có retention độc lập.

Một consumer ngừng quá lâu có thể mất khả năng tiếp tục nếu oplog đã ghi đè phần chứa vị trí resume.

### 3.2. Sự kiện được công bố khi majority-committed

Change Streams phát hiện các thay đổi đã majority-committed. Một write dùng `w:1` bị rollback trước majority commit có thể không xuất hiện dưới dạng change event đã được commit.

Không dùng Change Stream để chứng minh mọi lệnh client từng gửi đều đã được lưu bền vững.

### 3.3. Consumer cần connection dài hạn

Change stream cursor thường giữ một `getMore` chờ events. Khi không có thay đổi, call có thể đợi rồi trả batch rỗng. **Batch rỗng không phải lỗi kết nối**.

### 3.4. Khả năng đọc trên secondary

MongoDB driver có thể mở change stream theo read preference phù hợp. Tuy nhiên một election có thể khiến node phục vụ cursor không còn đáp ứng read preference; cần dựa vào driver topology discovery và resumable semantics thay vì giả định cursor cũ sống mãi.

## 4. Điều kiện để kiểm thử có ý nghĩa

| Hạng mục | Yêu cầu |
|---|---|
| Topology | Replica set hoặc sharded cluster, không chỉ standalone |
| Write workload | Có operations tạo events và ID dễ đối chiếu |
| Consumer | Có logic đọc event và checkpoint |
| Checkpoint store | Bền vững qua consumer process restart |
| Failure control | Có quyền mô phỏng mạng/primary trong lab |
| Recovery checks | Có assertions về events bị thiếu, xử lý trùng và cuối cùng state đúng |
| Observability | Logs/metrics timestamps UTC, election và resume attempts |
| Isolation | Không chạy fault injection nguy hiểm trên production |

### 4.1. Vì sao một MongoDBContainer đơn node chưa đủ?

Testcontainers có thể chạy một **single-node replica set**, đủ thử basic change stream và resume token. Nhưng nó **không** mô phỏng bầu chọn primary mới từ một node dữ liệu khác nếu chỉ có một member.

Muốn kiểm thử failover thật, cần ít nhất một secondary đủ điều kiện được bầu, và thông thường cấu hình **ba voting data-bearing members** để giữ majority khi một node mất.

### 4.2. Tránh nhầm Docker restart với election

Restart consumer container kiểm thử consumer lifecycle, không kiểm thử MongoDB election. Restart một mongod container trong một replica set không khỏe có thể làm mất quorum, và kết quả không tương đương planned stepdown.

### 4.3. Atlas và self-managed

Trong Atlas, không tự chạy các thao tác OS/network của self-managed lên managed nodes. Dùng môi trường staging/test có quyền hỗ trợ, maintenance/test workflows được cho phép hoặc phối hợp Support. Bài lab dùng self-managed replica set cô lập.

## 5. Cấu trúc change event

Một event minh họa:

~~~javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "update",
  clusterTime: Timestamp({ t: 1794650400, i: 1 }),
  ns: { db: "change_stream_lab", coll: "orders" },
  documentKey: { _id: "order-101" },
  updateDescription: {
    updatedFields: { status: "CONFIRMED" },
    removedFields: []
  }
}
~~~

Nội dung token trong ví dụ là placeholder. Không tự tạo giá trị `_data` để dùng làm resume token.

| Trường | Vai trò |
|---|---|
| `_id` | Resume token của event, là BSON document |
| `operationType` | insert, update, replace, delete, invalidate... |
| `clusterTime` | Thời gian logic của cluster/event |
| `ns` | Namespace database/collection |
| `documentKey` | Nhận diện document, có thể gồm shard key |
| `fullDocument` | Document đầy đủ theo cấu hình/event type |
| `updateDescription` | Delta của update |
| `lsid`/`txnNumber` | Metadata transaction trong trường hợp có |

### 5.1. _id của change event không phải _id của business document

- `event._id`: token để resume luồng.
- `event.documentKey._id`: khóa document nghiệp vụ.
- `event.fullDocument._id`: khóa của full document nếu được trả.

Không dùng `documentKey._id` thay cho resume token. Một document có thể phát nhiều events ở các thời điểm khác nhau.

### 5.2. Token là BSON opaque

Không coi resume token là số thứ tự đơn giản, timestamp string hoặc UUID tự tạo. Lưu **nguyên BSON document** được driver/server trả về, cùng thông tin phạm vi stream và cấu hình pipeline.

### 5.3. clusterTime không phải unique event ID

Nhiều change events có thể chia sẻ `clusterTime`, đặc biệt với transactions/sharding; một số tình huống từ MongoDB 8.0 cũng có behavior tương tự trên deployments khác. Vì thế chỉ dùng timestamp để deduplicate có thể bỏ sót events.

## 6. Resume token: điểm neo của recovery

Các nguồn token:

1. `event._id` cho event đã nhận.
2. `postBatchResumeToken` từ `aggregate`/`getMore`, khi server đưa ra high-watermark token.
3. Driver cursor có thể theo dõi resume token nội bộ cho automatic resume.

### 6.1. Event token và high-watermark token

**Event token** gắn với một event cụ thể.

**High-watermark token** có thể đại diện tiến trình cursor ngay cả khi không nhận event nào. Điều này có ích cho watermark/lag, nhưng cách checkpoint phải đảm bảo tất cả events trước watermark đã được xử lý.

### 6.2. Checkpoint phải phản ánh xử lý hoàn tất

Nếu mới nhận `E100` nhưng chưa cập nhật search index, lưu token của `E100` rồi crash sẽ khiến lần resume bỏ qua `E100`.

~~~text
Sai:
  receive E100
     |
  save token E100
     |
  process E100 -> crash
     |
  restart resumeAfter(E100) -> E100 bị bỏ qua
~~~

### 6.3. Ghi token sau side effect vẫn có thể tạo duplicate

~~~text
receive E100
   |
process E100 -> success
   |
crash BEFORE save token
   |
restart từ token E99
   |
E100 có thể được xử lý lại
~~~

Vì thế consumer cần **idempotency** hoặc cơ chế lưu kết quả + checkpoint một cách atomic khi có thể.

### 6.4. Không đồng nhất auto-resume với durable checkpoint

Driver có thể tự resume sau **một số lỗi resumable** trong khi process còn sống. Nhưng nếu process bị kill/redeploy, chỉ checkpoint trong RAM không đủ. Ứng dụng phải đọc durable token từ storage lúc khởi động lại.

## 7. resumeAfter, startAfter, startAtOperationTime

| Lựa chọn | Đầu vào | Dùng khi nào |
|---|---|---|
| `resumeAfter` | Resume token | Mở tiếp sau event/watermark đã xử lý |
| `startAfter` | Resume token | Tạo stream mới sau token, kể cả trường hợp `invalidate` |
| `startAtOperationTime` | BSON timestamp | Bắt đầu tại mốc thời gian khi không có token phù hợp |

Ba options này **loại trừ lẫn nhau** trong một lần mở stream. MongoDB không cho đặt đồng thời cả ba.

### 7.1. resumeAfter là lựa chọn thường dùng

Nếu đã commit xong xử lý `E100` và token của `E100` được lưu bền vững, lần restart dùng `resumeAfter(tokenE100)` để tiếp tục.

### 7.2. startAfter cho invalidate

Sau một `invalidate` do drop/rename collection hoặc drop database theo scope, không dùng `resumeAfter` từ token invalidate. `startAfter` cho phép tạo change stream mới sau token đó trong những điều kiện được hỗ trợ.

**Nhưng** “startAfter thành công” không đảm bảo namespace đã bị drop/rename còn tồn tại hoặc dữ liệu đã được phục hồi. Business recovery cần xử lý lifecycle của namespace.

### 7.3. startAtOperationTime không phải thay thế hoàn hảo cho token

`BsonTimestamp` gồm seconds và increment, chính xác hơn `Instant` trong một số tình huống. Mốc cũ phải còn trong oplog, và chọn mốc không chính xác có thể đọc thừa hoặc bỏ sót events.

Không lấy giờ đồng hồ ứng dụng vừa restart để “tiếp tục” nếu cần những events xảy ra lúc consumer ngừng.

### 7.4. Giữ nguyên pipeline và options

MongoDB khuyến cáo khi resume bằng token, dùng **cùng pipeline/options** như khi token được tạo. Đổi filters/fullDocument/options trong lúc recovery có thể dẫn đến behavior không dự đoán hoặc resume fail.

Nên version hóa stream definition gắn với checkpoint.

## 8. Invalidate khác lỗi kết nối

Một change stream cursor có thể kết thúc vì:

- Mạng ngắt hoặc server election.
- Client stop/cancel/close.
- Collection rename/drop.
- Database drop.
- Stream bị invalidated.
- Lỗi access/auth/TLS.
- History loss vì oplog.
- Điều kiện topology đặc biệt như shard removal.

### 8.1. Đừng coi mọi cursor đóng là resumable

Một network timeout có thể resumable. Một `invalidate` là semantic event báo nguồn stream thay đổi. History loss là dấu hiệu **không còn đủ lịch sử**. Cần các nhánh xử lý khác nhau.

### 8.2. Quy tắc theo scope

| Scope | Ví dụ invalidate |
|---|---|
| Collection-level watch | Rename/drop watched collection, drop database |
| Database-level watch | Drop watched database |
| Deployment-level watch | Không suy luận từ collection-level; xem docs/event semantics |

### 8.3. Trường hợp đổi tên collection

Nếu collection `orders` đổi tên thành `orders_archive`, watcher collection-level cũ có thể nhận invalidate và dừng. Muốn tiếp tục theo dõi collection mới phải đổi watch scope/namespace và có kế hoạch re-bootstrap theo semantic nghiệp vụ.

### 8.4. Sharded cluster có thêm góc cạnh

MongoDB docs cảnh báo shard removal có thể khiến change stream cursor đóng và không phải lúc nào cũng resumable đầy đủ. Test sharded lifecycle khác replica set failover.

## 9. Oplog retention: điều kiện để resume được

Change stream resume dựa vào oplog có đủ history đến vị trí token. Không thể bảo đảm resume từ token đã quá cũ chỉ vì token còn lưu trong database checkpoint.

~~~text
Oplog:
 [E100 E101 E102 ... E400 E401] -> thời gian
   ^                ^
   |                |
 token E100      oldest available
   |
   +--> token cũ đã ngoài oplog => history lost
~~~

### 9.1. Oplog window thay đổi theo write volume

Cùng cấu hình oplog capacity, nếu write throughput tăng đột biến, khoảng thời gian lịch sử thực tế có thể bị rút ngắn.

Ví dụ:

~~~text
Trước batch:
  Oplog window ~36 giờ

Sau batch:
  Oplog window ~4 giờ

Consumer outage:
  6 giờ

=> Resume có nguy cơ thất bại.
~~~

### 9.2. Giám sát oplog window bằng mongosh

Trên replica set member phù hợp:

~~~javascript
rs.printReplicationInfo();
~~~

Một số scripts dùng:

~~~javascript
db.getReplicationInfo();
~~~

Không đồng nhất con số oplog window tại một thời điểm với bảo đảm giữ mọi event đến ngày mai; nó phụ thuộc write rate và cấu hình.

### 9.3. PIT backup không thay change stream history

Backup/PIT có thể giúp khôi phục dữ liệu, nhưng không tự biến token cũ ngoài oplog thành resumable. Nếu history đã mất, cần quy trình **re-bootstrap projection/snapshot + lấy mốc mới + reconciliation**, được thiết kế để không có gap giữa snapshot và stream.

### 9.4. Recovery khi history lost

Không bắt exception rồi mở `watch()` không token và coi đã phục hồi hoàn toàn. Luồng mới chỉ thấy events từ thời điểm mới, dữ liệu trong khoảng bị mất chưa được xử lý.

Nên chuyển consumer sang trạng thái `RECONCILIATION_REQUIRED`, cảnh báo, dừng tuyên bố “caught up”, dựng lại projection hoặc đối soát có kiểm chứng.

## 10. Test oracle: tiêu chí nào quyết định PASS?

Đừng chỉ assert “không có exception”. Xây nguồn sự thật:

~~~text
Writer tạo: E001 E002 E003 ... E100
           |                    |
           v                    v
      Durable order log    Consumer output
           |                    |
           +--------- compare --+
                     |
          Không thiếu business events
          Không tạo side effects trùng
          State projection chính xác
~~~

Một **test oracle** có thể là collection riêng ghi `eventId` của các writes thành công với write concern phù hợp, hoặc một tập identifiers được writer ghi và xác minh sau test.

### 10.1. So event IDs, không chỉ đếm

Consumer output có 100 records chưa chắc là 100 events khác nhau; nó có thể gồm 99 đúng + 1 trùng + 1 bị thiếu.

Kiểm tra:

- Expected event ID set.
- Actually processed IDs.
- Duplicates.
- Missing IDs.
- Bản cuối của projection/index.
- Recovery latency.
- Checkpoint position và consumer healthy state.

### 10.2. Event ordering và sharding

Đừng suy luận các events từ nhiều shards có một sequence number ứng dụng toàn cục đơn giản. Khi cần order theo aggregate, thiết kế version/sequence ở cấp domain, và kiểm tra invariant cần thiết.

### 10.3. Không dựa hoàn toàn vào wall clock

Clock skew giữa containers/VMs có thể làm các timestamps không so được tuyệt đối. Ưu tiên business IDs, DB events và monotonic measurements để chứng minh continuity. `clusterTime` là logical timestamp, không thay ID.

## 11. Ma trận fault injection cần có

| Kịch bản | Failure được tạo | Kỳ vọng |
|---|---|---|
| Consumer process restart | Đóng/redeploy worker | Resume từ checkpoint, không bỏ sót |
| Consumer crash sau xử lý trước checkpoint | Kill giữa hai bước | Event có thể được đọc lại, output idempotent |
| Network drop ngắn | Chặn TCP trong thời gian ngắn | Bounded reconnect, không mất dữ liệu |
| DNS/SRV unavailable | Chặn DNS có kiểm soát | Không xóa checkpoint, phục hồi khi DNS về |
| Primary stepdown | `rs.stepDown` trong lab | Driver tìm primary mới và resume |
| Primary node hard stop | Stop mongod primary lab | Election, eventual continuation |
| Secondary outage | Stop một secondary | Primary vẫn chạy; consumer không ngắt vô lý |
| Loss of majority | Isolate đủ voting members | Writes không thể tiến hành; báo sự cố rõ |
| Lag vượt oplog window | Chờ/đẩy write volume trong lab | History lost, yêu cầu rebootstrap |
| Collection drop/rename | DDL có kiểm soát | Invalidate, policy startAfter/recreate |
| Permission revoked | Thay role lab | Auth/authorization error rõ, không retry vô hạn |
| TLS/CA rotation lỗi | Đổi trust path lab | New connections fail, recovery sau fix |
| Multiple consumers | Hai workers chung checkpoint | Có fencing/lease hoặc idempotency |
| High event throughput | Batch writes lớn | Lag và resource trong ngưỡng |
| Slow downstream | Giảm tốc projector | Backpressure và checkpoint đúng |
| Shard event | Shard migration/removal lab | Không hứa resume vô điều kiện |

### 11.1. Tách loại lỗi

- **Transient:** mạng, election, server selection.
- **Semantic:** invalidate, schema change, collection rename.
- **Permanent/configuration:** credential sai, thiếu privilege, TLS trust sai.
- **Data history gap:** oplog không còn token.

Một retry loop chung cho bốn loại thường gây thông báo “healthy” sai hoặc log spam.

## 12. Chuẩn bị môi trường lab

Một topology thực hành:

~~~text
                    MongoDB replica set rsLab
                 +------------------------------+
                 |                              |
                 |  m1 PRIMARY                  |
                 |  m2 SECONDARY                |
                 |  m3 SECONDARY                |
                 +------------------------------+
                     |                   |
                    Writer             Consumer
                                         |
                                    Checkpoint store
                                         |
                                   Projection output
~~~

### 12.1. Điều kiện mạng

- Tất cả nodes có hostname mà **cả nodes lẫn clients** resolve được.
- Ports nội bộ mở đúng và không expose ngoài phạm vi lab.
- Replica set member addresses khớp với địa chỉ được quảng bá trong `rs.conf()`.
- Java Driver URI có ít nhất đủ seed hosts, `replicaSet=rsLab` và TLS/auth nếu lab có thiết lập.

### 12.2. Dữ liệu test riêng

Dùng một database `change_stream_lab` và các collections:

~~~text
orders
consumer_checkpoints
order_projection
test_writer_log
~~~

Không inject lỗi vào production hoặc tài khoản có dữ liệu thật.

### 12.3. Role tối thiểu

Change stream consumer cần privileges read/changeStream phù hợp với scope (collection/database/deployment) và quyền ghi checkpoint/projection nếu cùng principal. Không dùng root cho worker production. Nếu source và projection tách DB, phân quyền rõ cả hai.

### 12.4. Healthy replica set trước fault

Trước khi bắt đầu test bầu chọn primary:

~~~javascript
rs.status();
rs.conf();
db.hello();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Không tiến hành stepdown nếu thiếu member/quorum hoặc secondary chưa bắt kịp.

## 13. Khởi tạo dữ liệu lab

**Chỉ chạy các lệnh dưới đây trong database thử nghiệm**.

~~~javascript
use change_stream_lab

db.createCollection("orders");
db.createCollection("consumer_checkpoints");
db.createCollection("order_projection");
db.createCollection("test_writer_log");

db.orders.createIndex(
  { testRunId: 1, seq: 1 },
  { unique: true, name: "unique_test_seq" }
);

db.order_projection.createIndex(
  { eventId: 1 },
  { unique: true, name: "unique_event" }
);
~~~

### 13.1. Vì sao tạo index trước test?

Tạo indexes/collections lần đầu trong lúc ghi events có thể thêm DDL events, chi phí metadata và thay đổi kết quả so với mục đích kiểm thử. Pre-create giúp nguồn sự thật dễ đối chiếu hơn.

### 13.2. Chọn testRunId cố định cho mỗi lượt

Ví dụ:

~~~javascript
const runId = "failover-lab-2026-11-14-A";
~~~

Không dùng lại cùng ID cho hai lượt mà không cleanup/reinitialize vì unique constraint sẽ gây duplicate key.

### 13.3. Test data không chứa PII

~~~javascript
db.orders.insertOne({
  _id: "order-001",
  testRunId: "failover-lab-2026-11-14-A",
  seq: 1,
  status: "CREATED",
  updatedAt: new Date()
});
~~~

Giữ payload nhỏ, deterministic và có business ID để assertion.

## 14. Bước lab A: mở một change stream trong mongosh

Mở **Shell A** kết nối replica set:

~~~javascript
use change_stream_lab

const cursor = db.orders.watch(
  [],
  { fullDocument: "updateLookup", maxAwaitTimeMS: 1000 }
);

print("Waiting for events...");
~~~

Mở **Shell B** (cũng kết nối rsLab) và ghi:

~~~javascript
use change_stream_lab

db.orders.insertOne({
  _id: "order-002",
  testRunId: "failover-lab-2026-11-14-A",
  seq: 2,
  status: "CREATED",
  updatedAt: new Date()
});
~~~

Trở lại Shell A:

~~~javascript
const firstEvent = cursor.next();

printjson({
  op: firstEvent.operationType,
  documentKey: firstEvent.documentKey,
  token: firstEvent._id
});
~~~

`cursor.next()` chờ đến khi nhận event; không chạy trên một thread phục vụ HTTP request.

### 14.1. Vì sao phải mở watcher trước khi write?

Nếu mở stream **sau** khi insert và không có starting point trong lịch sử, event có thể đã xảy ra trước thời điểm stream bắt đầu và không xuất hiện. Với test xác định, mở watcher/checkpoint trước writer hoặc dùng starting point có kiểm soát.

### 14.2. Full document và updateLookup

`fullDocument:"updateLookup"` yêu cầu lấy document hiện tại khi có update. Đây có thể là **phiên bản majority-committed mới nhất tại thời điểm lookup**, khác với nội dung ngay tại thời điểm operation nếu sau đó có update khác. Không dùng fullDocument thay event delta nếu cần giá trị chính xác theo từng update.

## 15. Bước lab B: lưu token và resume thủ công

Trong Shell A, sau khi xử lý thành công `firstEvent`:

~~~javascript
const token = firstEvent._id;

db.consumer_checkpoints.updateOne(
  { _id: "consumer-lab" },
  {
    $set: {
      token: token,
      savedAt: new Date()
    }
  },
  { upsert: true }
);

cursor.close();
~~~

Tiếp theo, Shell B tạo thêm event:

~~~javascript
db.orders.updateOne(
  { _id: "order-002" },
  { $set: { status: "CONFIRMED", updatedAt: new Date() } }
);
~~~

Mở lại cursor ở Shell A:

~~~javascript
const saved = db.consumer_checkpoints.findOne({
  _id: "consumer-lab"
});

const resumed = db.orders.watch(
  [],
  { resumeAfter: saved.token, fullDocument: "updateLookup" }
);

const eventAfterRestart = resumed.next();

printjson({
  operationType: eventAfterRestart.operationType,
  documentKey: eventAfterRestart.documentKey,
  token: eventAfterRestart._id
});
~~~

### 15.1. Assertions cơ bản

- Event nhận sau restart là sự kiện xảy ra sau token đã checkpoint.
- Không đọc lặp event đã checkpoint trong điều kiện không có lỗi khác.
- Token được lưu dưới dạng BSON document, không biến thành string tự chế.
- Không đổi pipeline/namespace/options trong lúc resume.

### 15.2. Caveat về log dữ liệu

Trong lab có thể `printjson` token. Production nên lưu token trong checkpoint store được bảo vệ; không log full payload/change event có PII hoặc secrets.

## 16. Bước lab C: consumer crash giữa process và checkpoint

Tạo tình huống:

~~~text
Checkpoint = token E002

Receive E003
Process E003 successfully
*** KILL consumer BEFORE save token E003 ***

Restart consumer
resumeAfter(token E002)
Read E003 again
~~~

### 16.1. Kết quả mong đợi

Chấp nhận việc **đọc lại E003**, nhưng projection/search index hoặc downstream side effect phải không bị nhân đôi.

Một cách đơn giản là xử lý theo một idempotent business event key:

~~~javascript
db.order_projection.updateOne(
  { eventId: "E003" },
  {
    $set: {
      orderId: "order-003",
      status: "CONFIRMED",
      lastAppliedAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Dùng `eventId` cố định/unique theo domain để tránh tạo hai projection entries. Nếu cần xử lý tuần tự các updates, phải có version/ordering controls; `$set` đơn giản chưa đủ cho mọi workflow.

### 16.2. Vì sao không checkpoint trước?

Checkpoint trước khi side effect thành công có thể gây **at-most-once delivery** với sự kiện bị bỏ qua. Với đồng bộ dữ liệu quan trọng, thường cần ít nhất at-least-once + idempotency hoặc atomic checkpoint.

## 17. Bước lab D: planned primary stepdown

**Chỉ trên self-managed replica set lab**, với quyền quản trị và secondary healthy.

Kết nối **trực tiếp** vào primary hiện tại bằng mongosh cho lệnh admin, xác nhận:

~~~javascript
db.hello().isWritablePrimary;
rs.status();
~~~

Kích hoạt stepdown có kiểm soát:

~~~javascript
rs.stepDown(60, 15);
~~~

Ý nghĩa:

- Primary cũ đề nghị nhường vai trò trong khoảng 60 giây.
- Có tối đa khoảng 15 giây để electable secondary bắt kịp theo tham số.
- Lệnh có thể khiến chính shell admin bị lỗi kết nối hoặc trả lỗi do node đã đổi role.

Không chạy `force:true` để ép mất majority. Nếu không có secondary đủ điều kiện, MongoDB có thể từ chối stepdown.

### 17.1. Quan sát song song

Trong khi stepdown:

1. Writer gửi events có IDs tăng dần, retry có giới hạn.
2. Consumer tiếp tục đọc change stream.
3. Thu driver logs về server selection và resumable errors.
4. Ghi mốc thời gian primary thay đổi.
5. Kiểm tra event IDs được writer **xác nhận thành công**.
6. So projection/checkpoint sau khi cluster ổn định.

### 17.2. Lỗi thoáng qua là kỳ vọng hợp lý

Trong election có khoảng không có primary nên writes có thể thất bại, request timeout hoặc retry. Test không nên đòi “không một network error nào”, mà đòi **khôi phục trong SLO và không mất sự kiện đã commit**.

### 17.3. Read preference và thay đổi vai trò

Từ MongoDB 9.0, với cursor mở theo read preference `primary`/`secondary`, election có thể khiến node cũ không còn thỏa read preference; `getMore` trả resumable `InterruptedDueToReplStateChange` (code 11602). Driver tương thích sẽ xử lý auto-resume; code tự viết `getMore` phải phản ứng tương ứng.

Không áp đặc điểm này máy móc cho mọi phiên bản MongoDB cũ hơn.

### 17.4. Điều cần chứng minh

Không chỉ thấy “new primary elected”; consumer phải tiếp tục phát các sự kiện sau election và checkpoint của nó tiến lên theo expected IDs.

## 18. Bước lab E: hard-stop primary

Kịch bản này khác `rs.stepDown`:

~~~text
Primary m1
   |
   +--> OS process killed/stopped
   |
Secondaries m2 + m3 elect a new primary
   |
   +--> Driver rediscovers topology
   |
   +--> Change stream resumes from checkpoint/driver token
~~~

### 18.1. Chỉ thao tác một node trong lab

Không kill nhiều members; cần majority để failover. Ghi rõ identity của node hiện tại trước khi stop, vì primary có thể thay đổi giữa lúc chuẩn bị và lúc injection.

### 18.2. Rủi ro khác planned stepdown

- In-flight writes/transactions có thể bị gián đoạn.
- Driver connection tới node chết có thể mất ngay.
- Election có thể mất thời gian khác.
- Nếu write chưa majority-committed, nó có thể rollback và **không** phải expected change stream event.

### 18.3. Oracle chỉ gồm committed writes

Khi tính missing events, chỉ tính các writes có confirmed outcome theo write concern và chiến lược đối soát; đừng đếm mọi lệnh writer đã thử gửi nếu một số bị timeout/unknown result.

## 19. Bước lab F: network partition và consumer mất kết nối

Có ít nhất ba failure modes khác nhau:

1. **Consumer ↔ MongoDB bị chặn**, các members vẫn liên lạc.
2. **Primary ↔ secondaries bị chặn**, có thể phát sinh election/quorum change.
3. **Một member ↔ nhiều clients bị chặn**, topology discovery/cursor routing có thể thay.

### 19.1. Mô hình test

~~~text
Time A: Consumer đang đọc E020
Time B: Chặn network consumer -> MongoDB
Time C: Writer khác tiếp tục ghi E021..E030 vào cluster khỏe
Time D: Mở lại network
Time E: Consumer resume
Time F: Compare expected IDs E021..E030
~~~

### 19.2. Bản chất timeout

Phân biệt:

- TCP connect timeout.
- Socket/read timeout.
- Server selection timeout.
- Cursor `maxAwaitTime` kết thúc mà không có event.
- Application deadline/batch processing timeout.

`tryNext()` trả `null` vì batch không có event không được phân loại là network failure.

### 19.3. Không yêu cầu mạng tự trở lại tức thì

Xác minh bounded retry/backoff, không tạo connection storm khi database unreachable. Consumer cần lưu token cũ an toàn trong thời gian đợi.

### 19.4. Tái nối phải giữ đúng identity và TLS

Nếu dùng MongoDB Atlas, URI SRV/private endpoint/TLS/SCRAM có thể tạo lỗi riêng. Không tắt TLS validation hoặc mở IP allowlist rộng để “thử cho qua”.

## 20. Consumer Java Sync Driver: đọc change stream

Ví dụ tối giản bằng MongoDB Java Sync Driver với dependency do Spring Boot BOM quản lý, hoặc driver library tương thích.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.ChangeStreamIterable;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class SimpleChangeStreamWatcher {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                client.getDatabase("change_stream_lab")
                      .getCollection("orders");

            ChangeStreamIterable<Document> stream =
                orders.watch().maxAwaitTime(1, TimeUnit.SECONDS);

            try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
                     stream.cursor()) {
                while (!Thread.currentThread().isInterrupted()) {
                    ChangeStreamDocument<Document> event = cursor.tryNext();

                    if (event == null) {
                        // Không có event lúc này, KHÔNG phải lỗi.
                        continue;
                    }

                    System.out.println("type=" + event.getOperationType());
                    System.out.println("token=" + event.getResumeToken());
                }
            }
        }
    }
}
~~~

### 20.1. Điểm cần nhớ

- `watch()` mở change stream trên collection.
- `cursor.tryNext()` trả event hoặc `null` khi không có event ở thời điểm đọc.
- `cursor.next()` chờ event, có thể block.
- `maxAwaitTime` điều chỉnh thời gian chờ server trên một `getMore`; không phải tổng transaction deadline.
- `try-with-resources` giúp đóng cursor/client.

### 20.2. Không chạy cursor blocking trên request thread

Nếu dùng Spring MVC, consumer đồng bộ thường có dedicated worker/managed executor. Nếu dùng WebFlux, cân nhắc reactive change stream để tránh chặn event loop.

### 20.3. Output và bản quyền dữ liệu

Không log full `event.getFullDocument()` hoặc token nếu payload có thông tin nhạy cảm; ví dụ in token phục vụ lab, không phải thiết kế logging production.

## 21. Java: lưu checkpoint BSON bền vững

Một checkpoint tối thiểu có thể lưu trong collection `consumer_checkpoints`.

Ví dụ repository raw driver với `MongoCollection<BsonDocument>`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.Filters;
import org.bson.BsonDocument;
import org.bson.BsonString;

public final class TokenCheckpointStore {
    private final MongoCollection<BsonDocument> checkpoints;
    private final String consumerId;

    public TokenCheckpointStore(MongoCollection<BsonDocument> checkpoints,
                                String consumerId) {
        this.checkpoints = checkpoints;
        this.consumerId = consumerId;
    }

    public BsonDocument load() {
        BsonDocument state = checkpoints
            .find(Filters.eq("_id", consumerId))
            .first();

        return state == null ? null : state.getDocument("token");
    }

    public void save(BsonDocument token) {
        if (token == null) {
            throw new IllegalArgumentException("missing resume token");
        }

        BsonDocument state = new BsonDocument("_id",
            new BsonString(consumerId))
            .append("token", token);

        checkpoints.replaceOne(
            Filters.eq("_id", consumerId),
            state,
            new ReplaceOptions().upsert(true)
        );
    }
}
~~~

### 21.1. Sử dụng trong watcher

~~~java
MongoCollection<BsonDocument> checkpointCollection =
    client.getDatabase("change_stream_lab")
          .getCollection("consumer_checkpoints", BsonDocument.class);

TokenCheckpointStore store =
    new TokenCheckpointStore(checkpointCollection, "orders-indexer-v1");

BsonDocument last = store.load();

ChangeStreamIterable<Document> stream = orders.watch();
if (last != null) {
    stream = stream.resumeAfter(last);
}

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         stream.maxAwaitTime(1, TimeUnit.SECONDS).cursor()) {
    // Đọc, xử lý, rồi save token.
}
~~~

Cần import `org.bson.BsonDocument` và MongoDB driver types phù hợp.

### 21.2. Lưu chính xác token, không chuyển sang UUID/string tự chế

`BsonDocument` giữ loại BSON cần thiết. Nếu lưu dưới JSON để chuyển hệ thống, phải đảm bảo Extended JSON được decode về đúng BSON types; một phép chuyển đổi mất type có thể làm token không dùng được.

### 21.3. Checkpoint metadata quan trọng

Trong production checkpoint nên có:

~~~json
{
  "_id": "orders-indexer-v1",
  "token": { "_data": "OPAQUE_BSON_FROM_MONGODB" },
  "streamScope": "change_stream_lab.orders",
  "pipelineVersion": "v3",
  "processorVersion": "search-indexer-2.1",
  "lastProcessedEventId": "E101",
  "updatedAt": "2026-11-14T10:25:00Z"
}
~~~

JSON này chỉ mô tả ý tưởng. `token` thật cần giữ BSON nguyên bản. Metadata có thể bảo vệ khỏi việc resume token của stream definition khác bị dùng nhầm.

## 22. Java: mở stream sau restart từ checkpoint

Một vòng đọc với recovery boundaries rõ:

~~~java
BsonDocument savedToken = store.load();

ChangeStreamIterable<Document> stream = orders.watch();

if (savedToken != null) {
    stream = stream.resumeAfter(savedToken);
}

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         stream.maxAwaitTime(2, TimeUnit.SECONDS).cursor()) {

    while (running) {
        ChangeStreamDocument<Document> event = cursor.tryNext();

        if (event == null) {
            continue;
        }

        // Hàm nghiệp vụ này PHẢI idempotent nếu có thể đọc lại event.
        processIdempotently(event);

        // Chỉ đánh dấu done sau khi process hoàn tất.
        store.save(event.getResumeToken());
    }
}
~~~

Các tên `running` và `processIdempotently` là các hooks nghiệp vụ mà ứng dụng phải hiện thực; ví dụ minh họa **thứ tự**, không phải class độc lập compile ngay.

### 22.1. Khi có exception giữa process và save

Nếu `processIdempotently` thành công nhưng `store.save` thất bại, sau restart event có thể lặp lại. Đây là lý do business idempotency cần thiết ngay cả khi driver auto-resume tốt.

### 22.2. Không catch-all và mở watch mới từ hiện tại

Nếu `cursor.tryNext()` ném lỗi, không bỏ token và lập tức gọi `orders.watch()` không `resumeAfter`. Hành vi đó có thể bỏ qua events trong khoảng downtime.

### 22.3. Driver auto-resume và vòng reconnect của app

MongoDB driver có cơ chế tự resume một số resumable errors. Ứng dụng vẫn cần:

- Reload durable checkpoint sau process restart.
- Tự thử lại có giới hạn nếu cursor chết sau khi driver đã thử.
- Phân biệt non-resumable errors.
- Hạn chế log spam/backoff.
- Đưa consumer sang trạng thái degraded khi quá thời gian được chấp nhận.

## 23. Checkpoint và downstream side effect: ba lựa chọn

### 23.1. Checkpoint trước process — có nguy cơ mất

~~~text
save token -> process -> crash
                |
          event có thể mất
~~~

Không phù hợp nếu mục tiêu không bỏ sót sự kiện.

### 23.2. Process trước checkpoint — at-least-once

~~~text
process -> save token
    |
    +--> crash => có thể process trùng
~~~

Đây là chiến lược phổ biến khi side effects được thiết kế idempotent.

### 23.3. Process + checkpoint cùng transaction MongoDB

Nếu **projection và checkpoint cùng MongoDB deployment** và cùng transaction/session, có thể commit atomically:

~~~text
Change Stream Event E101
       |
       v
Start MongoDB transaction
       |
       +--> Update projection
       +--> Save checkpoint token E101
       |
       v
Commit transaction
~~~

Đây là cơ chế tốt cho **MongoDB-local materialization**, nhưng không biến Kafka/HTTP/search engine ngoài MongoDB thành transactional resource.

## 24. Ví dụ Java: checkpoint atomic với projection

Sử dụng MongoDB Java Sync Driver, chạy trong replica set lab:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDocument;
import org.bson.BsonString;

public final class MongoAtomicProjector {

    private final MongoClient client;
    private final MongoCollection<BsonDocument> projections;
    private final MongoCollection<BsonDocument> checkpoints;

    public MongoAtomicProjector(
            MongoClient client,
            MongoCollection<BsonDocument> projections,
            MongoCollection<BsonDocument> checkpoints) {
        this.client = client;
        this.projections = projections;
        this.checkpoints = checkpoints;
    }

    public void apply(String consumerId, String businessKey,
                      ChangeStreamDocument<?> event) {

        BsonDocument token = event.getResumeToken();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                BsonDocument projection = new BsonDocument(
                    "_id", new BsonString(businessKey))
                    .append("lastEventToken", token);

                projections.replaceOne(
                    session,
                    Filters.eq("_id", businessKey),
                    projection,
                    new ReplaceOptions().upsert(true)
                );

                BsonDocument checkpoint = new BsonDocument(
                    "_id", new BsonString(consumerId))
                    .append("token", token);

                checkpoints.replaceOne(
                    session,
                    Filters.eq("_id", consumerId),
                    checkpoint,
                    new ReplaceOptions().upsert(true)
                );

                return null;
            });
        }
    }
}
~~~

### 24.1. Phạm vi đảm bảo

Đây là **ví dụ cơ chế transaction**, projection chỉ lưu token để giữ code ngắn. Production phải mapping payload, xử lý version/order và idempotency phù hợp. Callback `withTransaction` có thể được gọi lại khi retry nên **không** thực hiện side effects ngoài MongoDB trong callback.

### 24.2. Không đọc change stream bên trong transaction này

Consumer nhận event qua cursor độc lập, sau đó dùng transaction riêng để ghi projection/checkpoint. Không cố gọi `watch()` như một operation transactional ghi dữ liệu.

### 24.3. Same cluster không đủ nếu khác session

Mọi MongoDB writes trong transaction phải dùng overload có `ClientSession` tương ứng. Nếu `projections.replaceOne(...)` không nhận session, nó có thể chạy ngoài transaction.

### 24.4. Still not exactly-once toàn hệ thống

Một HTTP call hoặc Kafka publish ngoài MongoDB không được rollback với MongoDB transaction. “Exactly-once projection” là mục tiêu có phạm vi hẹp khi dùng atomic checkpoint và idempotent writes; không tuyên bố exactly-once external delivery.

## 25. Mô hình idempotency bằng business event ID

Resume token phù hợp làm checkpoint, nhưng duplicate suppression với downstream thường nên dùng business ID có nghĩa:

~~~text
eventId = order-123:status-confirmed:v7
~~~

Ví dụ materialized event table:

~~~javascript
db.processed_events.createIndex(
  { eventId: 1 },
  { unique: true, name: "unique_business_event" }
);
~~~

### 25.1. Không chỉ dựa vào _id của document

Một order có thể cập nhật nhiều lần: created, paid, refunded. Dùng mỗi `documentKey._id` làm dedup key sẽ loại bỏ các events hợp lệ đến sau.

### 25.2. Unique insert và idempotent upsert

- Khi lần đầu thấy event ID: insert/update projection.
- Khi đọc lại cùng event ID: nhận biết đã xử lý và không phát side effect lặp.
- Khi event version mới: áp dụng nếu đúng thứ tự/causal logic.

### 25.3. Cần tính đến commit ambiguity

Nếu MongoDB transaction commit timeout và client không biết outcome, không gửi lại HTTP payment bừa bãi. Dùng cùng business ID để reconcile state và áp dụng retry an toàn.

## 26. Spring Data MongoDB: synchronous Change Streams

Spring Data hỗ trợ sử dụng `MessageListenerContainer` với sync driver. Nó quản các tasks blocking ở worker threads.

Một skeleton theo tài liệu Spring Data:

~~~java
MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);

container.start();

MessageListener<ChangeStreamDocument<Document>, Document> listener =
    message -> {
        // Đọc metadata/event và gọi idempotent processor.
        // Lưu token sau khi xử lý bền vững.
    };

ChangeStreamRequestOptions options =
    new ChangeStreamRequestOptions(
        "change_stream_lab",
        "orders",
        ChangeStreamOptions.empty()
    );

Subscription subscription = container.register(
    new ChangeStreamRequest<>(listener, options),
    Document.class
);
~~~

Ví dụ là **skeleton** và cần imports Spring Data theo phiên bản, error handler, lifecycle bean management và checkpoint integration.

### 26.1. ChangeStreamRequest cần error handler

Theo tài liệu Spring Data, error trong listener được chuyển tới `ErrorHandler`; mặc định có handler log. **Chỉ log error là chưa đủ** để đảm bảo consumer tự phục hồi đúng checkpoint. Thiết kế error handler giám sát, restart subscription và escalate non-resumable errors.

### 26.2. Chặn stream đúng lifecycle

Khi app shutdown, dừng container/subscription có kiểm soát và đợi in-flight processing/checkpoint hoàn tất trong deadline. Không abrupt cancel rồi xác nhận event đã xử lý nếu side effect chưa commit.

### 26.3. Với database-level watch, dùng Document khi schema khác nhau

Watch toàn database có events từ nhiều collections với document structures khác nhau; typed conversion sang một entity class có thể sai. Dùng raw `Document` hoặc phân loại theo namespace.

## 27. Spring Data reactive Change Streams

Spring Data hỗ trợ reactive:

~~~java
Flux<ChangeStreamEvent<Document>> changes =
    reactiveTemplate.changeStream(Document.class)
        .watchCollection("orders")
        .listen();
~~~

Trong một reactive service, nên compose processor và checkpoint tuần tự:

~~~java
changes
    .concatMap(event ->
        processEvent(event)
            .then(saveCheckpoint(event.getResumeToken()))
    );
~~~

Các hàm `processEvent` và `saveCheckpoint` là pseudo application methods trả `Mono<Void>`. Cần có subscribe ở application lifecycle đúng cách và error/retry strategy.

### 27.1. Vì sao concatMap?

`concatMap` giữ thứ tự xử lý các events trong một subscription tốt hơn `flatMap` đồng thời khi checkpoint phải tiến tuần tự. Nếu dùng concurrency cao, một event mới có thể checkpoint trước event cũ xử lý xong → gây mất khi restart.

### 27.2. Reactor retry không tự giải quyết mọi lỗi

`retryWhen` có thể tái subscribe stream, nhưng:

- Nó phải reload token đã commit, không chỉ dùng token lúc app startup.
- Nó phải phân loại resumable vs history loss/authorization.
- Nó cần bounded backoff/jitter.
- Phải tránh tạo nhiều subscriptions song song cùng consumer checkpoint.

### 27.3. Resume bằng timestamp là fallback có điều kiện

Spring Data docs cho phép `resumeAt(Instant)`; tuy nhiên không dùng `Instant.now()` sau restart để khẳng định không mất events. Ưu tiên chính xác resume token khi có; timestamp start cần oplog còn giữ lịch sử và có logic dedup.

### 27.4. Reactive subscription có thể xử lý bất đồng bộ

Một `subscribe()` tách bên trong `doOnNext` không được đợi hoàn tất trước khi checkpoint. Nên compose publisher trong `concatMap`/`flatMapSequential` phù hợp, và kiểm thử crash giữa process/checkpoint.

## 28. Failover test Java: orchestration thay vì sleep cố định

Test đáng tin cậy nên chờ **điều kiện** thay vì `Thread.sleep(5000)` rồi giả định election đã xong.

~~~text
1. Bootstrap three-node replica set
2. Wait until exactly one PRIMARY and secondaries caught up
3. Start consumer with checkpoint store
4. Generate first N committed events
5. Wait until consumer checkpoint at N
6. Initiate stepdown through dedicated admin connection
7. Wait until new PRIMARY elected
8. Generate next M committed events
9. Wait until consumer projection contains expected IDs
10. Assert missing=0, duplicate side effects=0, lag<SLO
11. Close resources, save timeline/metrics
~~~

### 28.1. Test timeout

Không để test chạy vô hạn khi không có primary. Chờ đến deadline có thể cấu hình; khi hết, xuất status evidence và fail.

### 28.2. Không trộn infra setup với assertions

Một test fail vì replica set không bootstrap xong là **infrastructure/setup failure**, không chứng minh change stream recovery fail. Ghi loại failure rõ.

### 28.3. Không sử dụng fixed election delay như guarantee

Election timeout, heartbeat và network khác nhau theo version/config. Dùng observed primary identity/hello và driver topology state.

## 29. JUnit integration test: ý tưởng cấu trúc

Ví dụ pseudo JUnit 5:

~~~java
@Test
void resumesAfterPrimaryFailover() {
    String runId = uniqueRunId();

    ensureHealthyThreeNodeReplicaSet();
    startConsumer(runId);

    writeCommittedEvents(runId, 1, 20);
    awaitProcessed(runId, 20);

    String oldPrimary = currentPrimaryId();
    stepDownCurrentPrimaryInLab();
    awaitPrimaryDifferentFrom(oldPrimary);

    writeCommittedEvents(runId, 21, 40);
    awaitProcessed(runId, 40);

    assertExpectedEventIds(runId, 1, 40);
    assertNoDuplicateSideEffects(runId);
    assertCheckpointAdvanced(runId);

    stopConsumer();
}
~~~

Các helpers là **phương thức của test harness**, chưa phải code Java đầy đủ chạy độc lập. Thực tế cần retry/backoff cho writes giữa election và deadline tổng.

### 29.1. Testcontainers có thể giúp gì?

- Single-node replica set: kiểm thử watch, cursor, resume, process crash.
- Multi-node replica set: cần thiết lập container/network/advertised hosts để test election thực.
- Toxiproxy hoặc network fault harness: test one-way/two-way connection failures.
- JUnit: assertions, deadlines, cleanup và báo cáo.

API Testcontainers và package của MongoDB module có thể khác giữa các phiên bản; xem javadocs tương ứng trước khi copy imports.

### 29.2. Tránh chạy failover tests trong mọi unit-test loop

Unit tests có thể fake consumer handler/checkpoint. Những bài failover thật nên chạy integration/chaos suite có infrastructure chuyên dụng và chạy trong CI/staging theo lịch thích hợp.

## 30. Bảng assertions cho từng fault

| Fault | Assertion chính | Assertion bổ sung |
|---|---|---|
| Consumer restart | Resume đúng token sau restart | Không mất IDs |
| Crash sau side effect | Event được replay | Side effect không nhân đôi |
| Network disconnect | Connected lại trong deadline | Checkpoint không nhảy trước |
| Primary stepdown | New primary và consumer tiếp tục | Không missing majority-committed events |
| Primary kill | Failover theo majority | Driver recovery, no data corruption |
| Majority loss | Không accept writes sai | Recovery sau quorum restored |
| Oplog expired | Clear history-lost state | Không báo caught-up |
| Invalidate | Cursor đóng theo semantic | startAfter/rebootstrap theo policy |
| Shard removal | Error được phát hiện | Không giả định resume luôn được |
| TLS failure | New connections bị từ chối | Không disable verification |
| Auth revoke | Lỗi authorization rõ | Không retry storm |
| Slow sink | Lag tăng có kiểm soát | Backpressure, checkpoint không vượt process |
| Duplicate worker | Có lease/fencing hoặc idempotency | Không mất tiến trình state |

### 30.1. Nên có negative tests

Một test tốt cũng xác nhận hệ thống **từ chối báo thành công** khi không thể resume do history lost, hoặc không tự nhảy sang current time khi mất token.

### 30.2. Không cần zero duplicate reads

Với at-least-once, duplicate **delivery** có thể xảy ra. Assertion hữu ích hơn là duplicate **business side effects** bằng 0 và final state đúng.

## 31. Kiểm tra consistency khi writer nhận timeout

Nếu writer gửi `insertOne` rồi network đứt trước ACK, outcome có thể chưa rõ. Không đếm một attempted write thất bại không chắc chắn như event bắt buộc.

Một cách thiết kế oracle:

1. Mọi event có `testRunId` và `seq` duy nhất.
2. Writer ghi với write concern/durability phù hợp.
3. Khi ACK không rõ, writer đọc lại theo unique key để reconcile.
4. Chỉ khi document đã được xác nhận tồn tại theo consistency mục tiêu mới đưa vào expected set.
5. Sau test, so expected set với consumer processed IDs.

### 31.1. Không dùng w:1 để suy ra majority-committed

Một write xác nhận `w:1` có thể rollback sau failover. Nếu test oracle đòi mọi `w:1` write phải có change event vĩnh viễn, test có thể sai về semantics.

### 31.2. Unique business IDs bảo vệ retries

Nếu writer retry `insertOne` sau unknown outcome, duplicate key có thể là dấu hiệu lần đầu đã thành công. Dùng idempotent writes hoặc đối soát để không nhân đôi data.

## 32. Drop/rename và invalidate test

Trên **lab riêng**, sau khi tạo cursor trên `orders`, thực hiện DDL:

~~~javascript
use change_stream_lab

db.orders.renameCollection("orders_archive");
~~~

Hoặc:

~~~javascript
db.orders.drop();
~~~

Đây là thao tác phá dữ liệu test; không chạy trên production.

### 32.1. Kỳ vọng

- Collection-level cursor nhận invalidate event theo behavior hỗ trợ.
- Cursor đóng.
- `resumeAfter` token invalidate **không hợp lệ** để tiếp tục sau invalidate.
- `startAfter` có thể mở stream mới sau invalidate, nhưng schema/namespace phải được đánh giá lại.

### 32.2. Ghi rõ chính sách ứng dụng

Nếu production collection bị rename ngoài ý muốn, consumer nên vào incident mode và chờ chủ sở hữu dữ liệu xử lý, không tự chuyển nguồn dữ liệu và tiếp tục âm thầm.

### 32.3. Database-level watch khác collection-level

Nếu chỉ một collection bị drop, database-level watch không nhất thiết invalidate như collection watcher. Test theo chính xác scope đã chọn.

## 33. Pipeline filter, _id và versioning

Có thể chỉ theo dõi insert/update:

~~~javascript
const pipeline = [
  {
    $match: {
      operationType: { $in: ["insert", "update"] }
    }
  }
];

const cursor = db.orders.watch(pipeline);
~~~

### 33.1. Không xóa/chỉnh _id của event

MongoDB docs yêu cầu giữ nguyên `_id` resume token; từ MongoDB 4.2, change stream pipeline sửa `_id` có thể ném lỗi.

### 33.2. Filter có thể che thao tác invalidate

Nếu pipeline lọc bỏ loại event mà ứng dụng cần để xử lý lifecycle namespace, consumer có thể không quan sát đủ tín hiệu semantic. Thiết kế filter và recovery theo scope; đảm bảo không thay đổi filter giữa checkpoint cũ và resume khi chưa có migration plan.

### 33.3. Version hóa pipeline

Checkpoint metadata:

~~~text
consumerId=orders-indexer
streamScope=change_stream_lab.orders
pipelineVersion=v2
fullDocumentMode=updateLookup
token=BSON...
~~~

Khi nâng từ v2 sang v3, có thể cần pause/rebootstrap/reconcile, thay vì dùng token v2 với pipeline v3 một cách mặc định.

## 34. fullDocument:updateLookup không phải immutable snapshot

Với update:

~~~javascript
db.orders.updateOne(
  { _id: "order-002" },
  { $set: { status: "PAID" } }
);

db.orders.updateOne(
  { _id: "order-002" },
  { $set: { status: "SHIPPED" } }
);
~~~

Nếu consumer đọc update đầu chậm và dùng `fullDocument:"updateLookup"`, giá trị `fullDocument.status` có thể đã là `SHIPPED`, không phải `PAID`. `updateDescription` mới mô tả field delta của update event, trong phạm vi cung cấp.

### 34.1. Pre/post images

MongoDB 6.0+ hỗ trợ pre/post images trong những điều kiện và cấu hình phù hợp. Nếu cần hình ảnh trước/sau chính xác theo change, hãy đánh giá feature này và retention riêng; không mặc định nó được bật.

### 34.2. Event size

Thêm fullDocument hoặc images có thể làm change event vượt BSON document limit và cursor lỗi. Cần test documents lớn, event split behavior nếu server version hỗ trợ và payload limit.

### 34.3. Data mapping có thể thay đổi

Nếu Spring Data entity mapping không hiểu một event của collection khác, dùng raw Document để không làm subscriber fail khi schema khác nhau.

## 35. Watch scope: collection, database hay deployment?

| Scope | Ưu điểm | Rủi ro |
|---|---|---|
| Collection | Dễ lọc, business context rõ | Drop/rename dễ invalidate |
| Database | Một watcher cho nhiều collections | Phải phân loại namespace/schema |
| Deployment | Bao nhiều databases | Quyền rộng, event volume lớn, routing phức tạp |

### 35.1. Không sử dụng deployment-wide watch khi chỉ cần một collection

Quyền `changeStream` và `find` tùy phạm vi, nhiều data nhiều tenants có thể chứa thông tin nhạy cảm. Giảm scope để giới hạn blast radius và throughput.

### 35.2. Hot namespaces

Một database-level watcher có thể bị event volume lớn của collection khác làm lag, ảnh hưởng tới collection quan trọng. Cần filter/partitioning/consumer isolation theo workload.

## 36. Cạnh tranh giữa nhiều consumers

Hai worker pods dùng cùng checkpoint ID:

~~~text
Worker A reads E100, processes slowly
Worker B reads E101, processes fast and saves token E101
Worker A then saves token E100
=> checkpoint moves backward
~~~

Hoặc ngược lại, checkpoint nhảy lên trước event chưa xử lý.

### 36.1. Một logical consumer = một owner

Nếu dùng active/standby:

- Chỉ một worker giữ lease/fencing token.
- Có leader election hoặc managed coordination.
- Checkpoint writes có compare-and-set/monotonic protections phù hợp.
- Worker mất lease ngừng ghi side effects/checkpoint.

### 36.2. Worker group muốn scale horizontally?

Change Streams tự nó không giống một Kafka consumer group có partition assignments. Để scale, cần phân vùng theo business key/namespace, tách streams, hoặc dispatch có thứ tự và checkpoint thiết kế đúng.

### 36.3. Không dùng resume token như thứ tự numeric

Resume tokens là opaque BSON. Không so sánh `_data` bằng chuỗi tự chế để xác định token nào mới hơn. Nếu cần ordering cho checkpoint, dùng sequence/version ứng dụng hoặc fencing protocol được thiết kế riêng.

## 37. Backpressure và slow downstream

Consumer bị chậm có thể tạo:

- Cursor vẫn mở nhưng lag tăng.
- Oplog history window ngày càng ngắn so với consumer lag.
- Memory queue ứng dụng tăng.
- External sink quá tải.
- Token checkpoint tiến chậm.

### 37.1. Dùng bounded queue

Không đọc hàng triệu events vào unbounded Java queue rồi xử lý sau. Nếu process crash, những events chỉ ở RAM chưa checkpoint sẽ bị replay; queue quá lớn gây OOM.

### 37.2. Chọn processing concurrency có chủ đích

Nếu cần in-order per order, có thể phân vùng theo `orderId` và xử lý tuần tự trong partition. Checkpoint toàn stream vẫn phải bảo đảm không vượt qua event chưa hoàn tất ở partition khác.

### 37.3. Alert khi lag sắp vượt history

Ví dụ:

~~~text
Oplog window: 8 giờ
Consumer lag: 6 giờ
Headroom: 2 giờ
~~~

Một cảnh báo chỉ khi consumer bị disconnected là quá muộn; cần theo dõi backlog/lag và headroom so với oplog window, với đo lường có kiểm chứng.

## 38. Metrics và logs nên instrument

Các tên dưới đây là **custom application metrics minh họa**, không phải metrics MongoDB xuất sẵn:

~~~text
change_stream_events_received_total
change_stream_events_processed_total
change_stream_events_failed_total
change_stream_event_duplicate_total
change_stream_resume_attempts_total
change_stream_resume_failures_total
change_stream_history_lost_total
change_stream_checkpoint_age_seconds
change_stream_processing_duration_seconds
change_stream_reconnect_duration_seconds
change_stream_consumer_lag_seconds
change_stream_active_subscriptions
change_stream_read_idle_seconds
change_stream_current_primary_changes_total
~~~

### 38.1. Tách metrics healthy idle với stalled

Consumer có thể không có event vì database đang yên lặng. **Không có event mới** chưa đủ kết luận stalled. So:

- Source write traffic.
- Cursor/driver health.
- Last successful `getMore`.
- Checkpoint watermark/processed event.
- Oplog window.
- New event injection canary trong test.

### 38.2. Alert cơ bản

| Alert | Mục đích |
|---|---|
| Consumer not running | Không có watcher |
| Resume failures sustained | Kết nối lại liên tục thất bại |
| Checkpoint age vượt SLA | Dữ liệu không kịp cập nhật |
| Oplog headroom thấp | Nguy cơ không thể resume |
| History lost | Cần reconciliation ngay |
| Duplicate side effects | Idempotency hỏng |
| Primary election + resume errors | Correlation failover |
| Error handler logging-only | Consumer có thể chết âm thầm |

### 38.3. Tracing

Ghi logical event ID/trace ID, consumer ID, attempt count, operationType, namespace, error category, thời gian và checkpoint version. Tránh log raw payload/credentials/PII hoặc token tràn lan.

## 39. Runbook: consumer ngừng sau election

1. **Triage:** Có user impact không? Bao nhiêu events backlog? Projection stale bao lâu?
2. **Topology:** Kiểm tra current primary/replica health.
3. **Driver:** Xem server selection, socket, resumable error labels, reconnect attempts.
4. **Checkpoint:** Lấy token cuối đã commit, stream scope và pipeline version.
5. **History:** Kiểm tra oplog window, token có còn trong phạm vi?
6. **Recovery:** Nếu resumable, mở watch cùng pipeline/options với `resumeAfter`.
7. **Integrity:** So expected vs processed IDs, projection invariants.
8. **Observe:** Theo dõi lag giảm về baseline.
9. **Escalate:** Nếu history lost hoặc corrupt checkpoint, dừng tuyên bố đã phục hồi.
10. **Postmortem:** Cải thiện retry/monitoring/retention/fencing.

### 39.1. Tránh thao tác làm mất bằng chứng

Không xóa collection checkpoint hoặc thay pipeline version giữa incident khi chưa có snapshot/evidence. Một lần “reset stream” về hiện tại có thể khiến các events chưa xử lý bị mất dấu.

### 39.2. Runbook cho unknown errors

Các lỗi network có thể resumable; lỗi missing privilege/invalid pipeline/history loss thường cần remediation khác. Phân loại theo MongoDB error code/labels và documentation của driver/version thay vì catch-all.

## 40. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Khả năng | Hướng xử lý |
|---|---|---|
| Standalone watch fail | Không có oplog replica set | Dùng replica set |
| Watcher im lặng | Chưa có events hoặc cursor chưa open | Ghi test event, inspect cursor |
| Không nhận event trước lúc watch | Không có starting point | Mở watch sớm hoặc dùng token/time |
| Sau restart bị thiếu events | Checkpoint trước processing | Đổi thứ tự/idempotency |
| Sau restart bị trùng events | Crash trước checkpoint | Dedup business ID |
| Sau election stream chết | Driver hết auto-resume, app không restart | Durable checkpoint và reconnect loop |
| Không thấy primary mới | URI/directConnection/seed list sai | Multi-host URI/SDAM |
| Stepdown fail | Không có secondary electable/up-to-date | Health/quorum/catchup |
| Writes fail ngắn | Election đang diễn ra | Bounded retry và SLO |
| Token không resume được | Oplog history lost | Rebootstrap/reconcile |
| Resume after invalidate fail | Dùng sai option | `startAfter` theo policy |
| Filter làm lỗi token | Thay `_id` | Giữ nguyên event _id |
| Chuyển pipeline version lỗi | Token và options không tương thích | Version/migration |
| FullDocument khác mong đợi | updateLookup đọc latest majority | Dùng delta/pre-post images |
| Consumer lag tăng | Downstream chậm | Backpressure/capacity |
| Projection sai dù event đủ | Ordering/logic sai | Version/ordering tests |
| Hai consumers ghi checkpoint | Không có lease/fencing | One owner/conditional writes |
| Test chỉ một mongod node không elect được | Không có secondary | Dùng 3-member replica set |
| Lỗi DNS/TLS | Runtime network/trust sai | Fix DNS/CA, không tắt TLS |
| auth fail sau rotate | Cũ/new credentials không đồng bộ | Rotation rollout |
| Read preference fail sau election | Role không còn thỏa (version-specific) | Resumable handling |
| Shard removal đóng cursor | Sharded topology event | Reconcile theo docs |

## 41. Security và compliance khi kiểm thử

### 41.1. Không dùng dữ liệu thật cho chaos

Hãy tạo database/collection lab riêng với fake IDs. Dữ liệu test có thể xuất hiện trong logs, profiler, artifacts và downstream test sinks; không dùng PII thật.

### 41.2. Least privilege

Consumer cần quyền xem changes trong scope và quyền tối thiểu để cập nhật projection/checkpoint; chaos harness cần admin rights tách biệt. Không trao `clusterAdmin` cho consumer chỉ để nó có thể chạy `rs.stepDown` trong test.

### 41.3. Audit mọi fault injection

Ghi:

~~~yaml
testRunId: failover-lab-2026-11-14-A
scenario: planned-primary-stepdown
environment: isolated-test
faultInjectedAtUtc: 2026-11-14T10:25:00Z
faultOwner: test-runner
expected: resume-without-missing-committed-events
observed: pending
~~~

Đây là schema báo cáo thử nghiệm minh họa, không phải config MongoDB.

### 41.4. Tránh rò rỉ resume token/metadata

Resume token không phải password, nhưng nó tiết lộ trạng thái stream/cluster và có thể chứa metadata nhạy cảm. Giới hạn quyền đọc checkpoints, retention logs và không gửi raw tokens tới alert channels nếu không cần.

## 42. Kế hoạch CI/CD và chaos testing

Phân tầng test:

| Tầng | Chạy khi nào | Mục tiêu |
|---|---|---|
| Unit | Mỗi PR | Handler, dedup, checkpoint ordering |
| Integration single-node replica set | Mỗi PR/merge | watch/resume/rollback cơ bản |
| 3-node failover integration | Theo lịch/PR quan trọng | Election, network, driver SDAM |
| Stress/soak | Theo lịch | Throughput, lag, memory, throughput recovery |
| Staging chaos | Trước release lớn | End-to-end pipeline và runbook |
| Disaster recovery drill | Theo policy | History loss/rebootstrap/backup correctness |

### 42.1. CI cần deterministic failure injection

Dùng test harness điều khiển thời điểm crash:

~~~text
afterProcessBeforeCheckpointLatch
afterCheckpointBeforeNextPollLatch
whileGetMoreBlockedLatch
afterPrimaryStepdownLatch
~~~

Trong test harness có thể có hooks/latches nội bộ, nhưng không nên giữ các debug kill switches mở trong production API.

### 42.2. Bảo đảm cleanup

Mỗi test phải đóng cursor/MongoClient, khôi phục network rules, phục hồi members, dọn fake data theo policy và không để trạng thái replica set lỗi ảnh hưởng test khác.

### 42.3. Artifact của test

Lưu:

- Test run ID, server/driver versions.
- Fault timeline UTC.
- Node states/election markers.
- Event IDs expected/processed/duplicated.
- Resume attempts và checkpoint transitions.
- Latency, lag và duration.
- Exit status và những assertion failures.
- Evidence redacted.

## 43. Checklist trước khi chạy failover test

### Infrastructure

- [ ] Môi trường lab/staging được phép fault injection.
- [ ] Replica set có electable secondaries và majority khỏe.
- [ ] Java Driver/Spring Data versions được ghi nhận.
- [ ] Writer dùng writeConcern phù hợp để xác minh committed events.
- [ ] Oplog window đủ test duration.
- [ ] Network/TLS/auth hoạt động trước test.
- [ ] Có admin session riêng cho stepdown.
- [ ] Có rollback/restore/cleanup plan.

### Consumer

- [ ] Checkpoint store bền vững ngoài process memory.
- [ ] Token giữ nguyên BSON, không bị stringify mất type.
- [ ] Stream scope/pipeline/options được version hóa.
- [ ] Checkpoint sau processing, hoặc cùng transaction với projection.
- [ ] Xử lý idempotent duplicate deliveries.
- [ ] Có bounded retry và backoff.
- [ ] Phân biệt resumable, invalidate và history lost.
- [ ] Không có hai workers vô kiểm soát cùng consumer ID.
- [ ] Không chạy raw blocking cursor trên request/event loop thread.

### Acceptance

- [ ] Expected set từ majority-committed writes.
- [ ] Có test normal reconnect.
- [ ] Có test crash before/after checkpoint.
- [ ] Có test stepdown và hard-stop primary.
- [ ] Có test network partition.
- [ ] Có negative test history lost.
- [ ] Có invalidation/startAfter theo scope.
- [ ] Có verify projection state cuối.
- [ ] Không missing events hoặc duplicate side effects.
- [ ] RTO/consumer catch-up SLO đạt.
- [ ] Alert/runbook phản ứng đúng.
- [ ] Logs/artifacts không lộ dữ liệu nhạy cảm.

## 44. Bài tập tự luyện

Chỉ sử dụng MongoDB replica set **lab**, không chạy `rs.stepDown`, drop collection, chặn mạng hoặc kill process trên production.

### Bài 1 — Tại sao change stream cần replica set?

Giải thích vai trò oplog. Một standalone mongod đã bật authentication nhưng không có replica set có watch được không?

### Bài 2 — Phân biệt event và token

Trong event có `_id` và `documentKey._id`. Trường nào là resume token?

### Bài 3 — Majority-commit

Một `w:1` write rollback sau election. Có nên yêu cầu consumer phải xử lý vĩnh viễn write đó không?

### Bài 4 — Cursor và consumer

Nếu client app chết, MongoDB có tự lưu durable checkpoint thay ứng dụng không?

### Bài 5 — resumeAfter

Consumer xử lý E20 và lưu token. Sau restart cần dùng option nào để tiếp tục sau E20?

### Bài 6 — startAfter

Collection được drop, nhận invalidate. Vì sao không dùng `resumeAfter` token invalidate?

### Bài 7 — startAtOperationTime

Vì sao dùng `Instant.now()` sau 30 phút outage có nguy cơ bỏ mất events?

### Bài 8 — Same pipeline

Bạn đổi `$match` filter giữa hai lần mở stream. Có nên dùng token cũ không, và vì sao?

### Bài 9 — Event ID

Một document có ba lần update. Vì sao không thể dùng `documentKey._id` làm ID duy nhất của mỗi change event?

### Bài 10 — Checkpoint trước process

Viết timeline gây mất E101 nếu token được lưu trước side effect.

### Bài 11 — Checkpoint sau process

Viết timeline khiến E101 được replay nhưng không được tạo hai order notifications.

### Bài 12 — Atomic checkpoint

Nếu projection và checkpoint cùng MongoDB cluster, bạn có thể dùng transaction như thế nào? Nó có rollback được Kafka event không?

### Bài 13 — Mongosh basic lab

Tạo collection `orders`, mở `watch`, insert một document và đọc resume token.

### Bài 14 — Mongosh resume

Lưu token event đầu, đóng cursor, update document, mở watch với `resumeAfter` và xác nhận event mới.

### Bài 15 — Planned stepdown

Vì sao cần ít nhất một up-to-date electable secondary trước `rs.stepDown(60,15)`?

### Bài 16 — Primary kill

Điểm khác nhau giữa stepdown và hard-stop primary là gì? Có thể có in-flight writes ambiguous không?

### Bài 17 — Quorum

Nếu ba voting members và mất hai nodes, kỳ vọng writes/change streams thế nào?

### Bài 18 — Oplog window

Oplog window 4 giờ, consumer offline 6 giờ. Recovery strategy nào cần chuẩn bị?

### Bài 19 — Event set

Writer tạo IDs E001..E100. Output consumer có 100 bản ghi nhưng một ID trùng và một ID thiếu. Test có PASS không?

### Bài 20 — Java cursor

Phân biệt `next()`, `tryNext()`, `maxAwaitTime()` và `null` khi không có event.

### Bài 21 — BsonDocument

Tại sao lưu nguyên `BsonDocument` resume token tốt hơn chỉ lưu chuỗi do ứng dụng tự tạo?

### Bài 22 — Auto resume

Driver tự resume một lần sau resumable error có thay thế checkpoint sau process restart không?

### Bài 23 — Read preference

MongoDB 9.0 có thay đổi gì về `InterruptedDueToReplStateChange` sau election?

### Bài 24 — Spring Data sync

Vì sao `MessageListenerContainer` cần thread riêng và error handler? Mặc định chỉ log error có đủ không?

### Bài 25 — Spring Data reactive

Vì sao `concatMap` có thể phù hợp hơn `flatMap` đồng thời khi checkpoint một luồng duy nhất?

### Bài 26 — Reactor retry

Một `retryWhen` tạo stream mới từ current time sau lỗi. Có thể bỏ sót events không?

### Bài 27 — updateLookup

Nếu document vừa update sang PAID rồi sang SHIPPED rất nhanh, `fullDocument` của event đầu có thể là SHIPPED không?

### Bài 28 — pre/post images

Khi nào cần pre-image chính xác thay vì updateLookup? Các điều kiện server cần?

### Bài 29 — Multiple consumers

Hai workers cùng ghi một checkpoint. Nêu cách lease/fencing hoặc dedup để tránh checkpoint tiến sai.

### Bài 30 — Sharded cluster

Vì sao cần kiểm thử per-shard/hot shard và cảnh báo shard removal đóng cursor?

### Bài 31 — Network recovery

Mô phỏng consumer-to-cluster disconnect 20 giây. Assertions nào giúp chứng minh recoverability?

### Bài 32 — DNS/TLS

Sau rotation CA, new connection fail. Vì sao không bật `tlsInsecure` thay cho sửa truststore?

### Bài 33 — Alerting

Thiết kế metrics cho checkpoint age, history headroom, resume attempts và consumer catch-up time.

### Bài 34 — Runbook

Viết các bước khôi phục consumer sau election, có phân loại history-lost và invalidate.

### Bài 35 — Testcontainers

Single-node replica set đủ cho test resume token nhưng vì sao chưa đủ cho election từ secondary?

### Bài 36 — CI strategy

Phân biệt unit, integration, 3-node failover và staging chaos; mỗi tầng xác minh điều gì?

### Bài 37 — Incident data privacy

Một event có địa chỉ khách hàng. Có nên log toàn bộ `fullDocument` trong failed resume alert không?

### Bài 38 — Tình huống tổng hợp

Thiết kế một service Spring Boot + MongoDB Java Driver đồng bộ index với:

- Replica set ba nodes.
- Writer có IDs duy nhất và majority commit.
- Consumer dùng cursor/Change Streams.
- Durable BSON resume tokens.
- Same-scope pipeline version.
- Idempotent downstream processor.
- Crash injection giữa process/checkpoint.
- Planned stepdown và primary kill.
- Test history-lost/invalidate.
- Bounded retry và backpressure.
- Metrics, alert routing, runbook và acceptance assertions.

## 45. Tổng kết

Để kiểm thử **mất kết nối, chuyển primary và tiếp tục change stream** một cách đáng tin cậy, phải kết hợp ba lớp:

**Lớp 1 — MongoDB topology và lịch sử:** Replica set/sharded cluster khỏe, majority-committed writes, oplog history còn đủ, driver topology discovery và elections được kiểm thử trong lab.

**Lớp 2 — Consumer và checkpoint:** Change stream có resume token BSON opaque, pipeline/options cố định, `resumeAfter`/`startAfter` chọn theo semantic; checkpoint chỉ được ghi sau processing hoặc atomic với projection. Auto-resume của driver không thay durable restart recovery.

**Lớp 3 — Tính đúng đắn nghiệp vụ:** At-least-once có thể replay event; phải dùng idempotency/fencing/reconciliation. Test không chỉ yêu cầu reconnect mà cần **zero missing committed events, zero duplicate business side effects, final state đúng và recovery trong SLO**.

Quy tắc cuối cùng: **Không thể tiếp tục từ token đã mất lịch sử trong oplog bằng cách retry mãi. Khi đó hãy báo history gap và chạy quy trình re-bootstrap/đối soát có kiểm chứng thay vì âm thầm bắt đầu từ hiện tại.**

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/)
- [MongoDB Manual — db.collection.watch()](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [MongoDB Manual — $changeStream Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/)
- [MongoDB Manual — Change Stream Invalidate Events](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/)
- [MongoDB Manual — Change Stream Update Events](https://www.mongodb.com/docs/manual/reference/change-events/update/)
- [MongoDB Java Sync Driver — Open Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [MongoDB Java Sync Driver — Monitor Events](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [Spring Data MongoDB — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — rs.stepDown()](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)
