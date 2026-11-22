# Sự kiện lặp, invalidate, retention và xử lý idempotent

## 1. Bài toán: một change stream chạy lại có thể gửi cùng hiệu ứng nghiệp vụ

Giả sử hệ thống đặt hàng có collection **orders** trong MongoDB. Khi một đơn chuyển sang trạng thái **PAID**, dịch vụ dùng Spring Data MongoDB change stream để cập nhật một read model **order_summaries** và gửi thông báo xác nhận.

~~~text
Orders (MongoDB)
      |
      | Change stream
      v
OrderEventConsumer
      |
      +-- cập nhật order_summaries
      |
      +-- tạo notification/outbox
      |
      +-- lưu resume token
~~~

Consumer nhận một sự kiện chuyển trạng thái PAID và đã cập nhật read model. Ngay sau đó, ứng dụng mất kết nối hoặc process dừng trước khi lưu checkpoint. Khi khởi động lại, consumer đọc tiếp từ resume token cũ và có thể **nhận lại chính sự kiện đã xử lý**. Nếu handler cộng thêm doanh thu hoặc gửi email mỗi lần nhận, dữ liệu có thể bị cộng/gửi hai lần.

Một trường hợp khác: quản trị viên xóa hoặc đổi tên collection đang được theo dõi. MongoDB phát **invalidate** và đóng cursor. Một vòng lặp retry chỉ gọi **resumeAfter** token cũ sẽ không tự làm luồng hợp lệ trở lại.

Trường hợp thứ ba: worker ngừng nhiều giờ trong khi oplog quay vòng. Resume token được lưu vẫn còn trong database checkpoint, nhưng **lịch sử mà token trỏ đến đã bị loại khỏi oplog**. Resume thất bại; retry vô hạn với token ấy chỉ kéo dài sự cố.

Bài học **Sự kiện lặp, invalidate, retention và xử lý idempotent** thuộc chương **Change stream** trong module **SPRING_DATA_MONGODB**. Module hướng tới việc kết nối, ánh xạ document, thao tác MongoDB qua MongoTemplate hoặc repository, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

### 1.1. Mục tiêu

Sau bài, bạn có thể:

1. Phân biệt **sự kiện lặp** do replay/reconnect với hai business changes hợp lệ trên cùng entity.
2. Hiểu resume token, **resumeAfter**, **startAfter**, **startAtOperationTime**.
3. Xác định invalidate khi drop/rename/dropDatabase và xử lý theo scope theo dõi.
4. Hiểu **oplog retention**, recovery window và trường hợp token không còn sử dụng được.
5. Thiết kế **checkpoint sau khi xử lý thành công**, không checkpoint trước.
6. Áp dụng **idempotent inbox**, unique key, business version và MongoDB transaction.
7. Tách **side effect bên ngoài MongoDB** thành outbox/notification worker có idempotency.
8. Dùng Spring Data **ReactiveMongoTemplate** và **ChangeStreamOptions** với token bền vững.
9. Xử lý lỗi, retry có backoff, poison events và không làm mất thứ tự sự kiện.
10. Viết integration/failure-injection tests và theo dõi lag so với oplog retention.

## 2. Change stream là gì và đòi hỏi hạ tầng nào?

MongoDB change streams cho phép theo dõi những thay đổi đã được ghi trong deployment MongoDB mà không phải tự tail trực tiếp **oplog.rs**.

Một watch có thể áp dụng ở nhiều phạm vi:

| Phạm vi | Điểm mở stream | Ví dụ |
| --- | --- | --- |
| Collection | db.orders.watch | Chỉ theo dõi một collection |
| Database | db.watch | Theo dõi thay đổi trong nhiều collections của một database |
| Deployment | Mongo.watch | Theo dõi nhiều database/collections trong deployment theo quyền được cấp |

**Change streams yêu cầu replica set hoặc sharded cluster**, không phải một MongoDB standalone thông thường. Ứng dụng cần quyền phù hợp để mở change stream và theo dõi namespace.

### 2.1. Change stream không phải message queue có retention độc lập

Một broker có thể giữ messages theo chính sách topic retention riêng. MongoDB change streams dựa trên **lịch sử oplog** để phát lại events. Không thể lưu token trong một collection khác rồi mặc định event history sẽ còn mãi.

### 2.2. Cursor không phải job bất biến

Change stream là một cursor dài hạn. Nó có thể đóng vì:

- Ứng dụng chủ động dừng.
- Kết nối mất, timeout hoặc mongod/mongos chuyển trạng thái.
- Trường hợp **invalidate**.
- Lịch sử không còn đủ để resume.
- Những lỗi pipeline/permission/server khác.

Đóng cursor và đóng namespace vì invalidate là hai loại biến cố khác nhau. Một số lỗi tạm thời có thể resume được; invalidate và history loss đòi quyết định khác.

### 2.3. Watch scope ảnh hưởng việc xử lý DDL

Collection watch có thể bị invalidate bởi **drop**, **rename** hoặc **dropDatabase** ảnh hưởng collection đó. Database watch bị invalidate khi **dropDatabase** ảnh hưởng database được theo dõi. Không mặc định mọi drop collection đều làm database-level watch bị invalidate.

## 3. Một change event chứa những gì?

Một sự kiện insert từ mongosh có hình dạng giản lược:

~~~javascript
{
  _id: { _data: "8265...opaque-resume-token..." },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1730462400, i: 1 }),
  ns: { db: "commerce", coll: "orders" },
  documentKey: {
    _id: ObjectId("507f1f77bcf86cd799439011")
  },
  fullDocument: {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    tenantId: "shop-a",
    orderNo: "ORD-101",
    status: "CREATED"
  }
}
~~~

Ví dụ trên minh họa cấu trúc, không phải resume token thật có thể dùng để resume.

| Trường | Ý nghĩa |
| --- | --- |
| _id ở cấp **event** | **Resume token**, đại diện vị trí trong change stream |
| operationType | insert, update, replace, delete, invalidate và các loại khác |
| clusterTime | BSON Timestamp liên quan thao tác trên cluster |
| ns | Database/collection của event |
| documentKey | Key của document được thay đổi, thường gồm _id |
| fullDocument | Document liên quan, tùy operation type và cấu hình lookup |
| updateDescription | Những field được update/remove/truncate ở update event |

### 3.1. Hai _id khác nhau

~~~text
event._id                  -> resume token của sự kiện
event.documentKey._id      -> ID document nghiệp vụ
event.fullDocument._id     -> ID document trong snapshot (nếu có)
~~~

Không dùng documentKey._id thay cho resume token. Một Order có thể sinh **hàng chục events** với cùng documentKey._id.

### 3.2. Không phải event nào cũng có fullDocument

Với delete, phần body document đã bị xóa thường không còn. Với update, event mặc định có **updateDescription**; muốn lookup document hiện tại có thể yêu cầu **fullDocument: updateLookup**, nhưng kết quả lookup có thể khác snapshot đúng tại thời điểm update hoặc là null.

Với invalidate, đừng kỳ vọng fullDocument chứa một Order. Handler phải phân nhánh theo **operationType** trước khi lấy body.

### 3.3. Không sửa _id của event trong pipeline

MongoDB coi event._id là resume token. Pipeline change stream không nên project bỏ hay sửa event._id; từ MongoDB 4.2, việc sửa _id qua pipeline sẽ gây lỗi. Nếu muốn thêm fields cho DTO, transform **sau khi nhận** mà vẫn giữ token.

## 4. “Sự kiện lặp” xuất hiện khi nào?

Change stream không cung cấp cam kết rằng business side effect được thực thi exactly-once. Ở tầng consumer, cần **thiết kế an toàn với replay/at-least-once processing**.

Những nguyên nhân phổ biến:

1. Worker hoàn thành xử lý nhưng crash trước khi persist checkpoint.
2. Connection lỗi và driver/app mở lại cursor bằng token đã checkpoint trước event.
3. Supervisor khởi động lại container, consumer đọc lại một vùng sự kiện.
4. Một token checkpoint được roll back do storage chưa bền vững.
5. Hai consumer cùng xử lý một logical subscription khi không có lease/fencing.
6. Retry một message từ outbox hoặc notification queue sau timeout.

### 4.1. Lặp ở mức event khác lặp ở mức business command

Nếu một Order đổi:

~~~text
CREATED -> PAID -> REFUNDED -> PAID
~~~

thì có thể tồn tại **hai event PAID hợp lệ khác nhau**, với resume tokens khác nhau. Không được mặc định “Order ID đã thấy rồi thì bỏ mọi event sau”.

Một business command gửi lại cũng có thể tạo **một event mới** với resume token mới, dù client nghĩ đó là cùng một request. Vì vậy cần hai tầng idempotency:

- **Event idempotency:** xử lý một change event token tối đa một lần về mặt hiệu ứng mong muốn.
- **Business idempotency:** cùng một paymentId/commandId không được ghi nhận doanh thu hoặc thanh toán hai lần.

### 4.2. Duplicate không chỉ do MongoDB

Nếu consumer publish một email request rồi service email timeout nhưng đã gửi thành công, retry từ notification worker có thể gửi lại. Dedupe change-stream events ở consumer chưa bảo đảm email chỉ gửi một lần khi downstream không có idempotency.

## 5. Các mức bảo đảm thực tế

| Mục tiêu | Cách tiếp cận | Điều không tự được bảo đảm |
| --- | --- | --- |
| Không bỏ sót events trong cửa sổ lịch sử | Checkpoint token bền vững, resume đúng | Không bảo vệ khi oplog history đã mất |
| Không áp cùng event hai lần | Unique inbox key/event token | Không chặn hai events khác token nhưng cùng business operation |
| Không cập nhật projection trùng | Idempotent $set/upsert/version guard | Không tự giữ đúng thứ tự nếu xử lý song song |
| Atomic giữa inbox + projection + checkpoint | MongoDB transaction dùng cùng session | Không atomic với email/HTTP/Kafka ngoài MongoDB |
| Tránh gửi email trùng | Outbox + downstream idempotency key | Email provider không hỗ trợ idempotency có thể vẫn trùng |
| Tiếp tục sau drop/rename | Nhận diện invalidate + startAfter theo policy | Không khôi phục document cũ tự động |
| Hồi phục sau history loss | Rebuild/reconcile với mốc cắt nhất quán | Không thể phục hồi event đã bị xóa nếu không có nguồn khác |

**Exactly-once** chỉ có ý nghĩa khi chỉ rõ **đối tượng nào được xử lý đúng một lần**, trong phạm vi những hệ thống và transaction nào.

## 6. Resume token: checkpoint logic của change stream

Mỗi change event chứa token tại **event._id**. Token thường là một BSON document có các trường opaque, không phải số thứ tự tự đặt.

~~~javascript
const stream = db.orders.watch();
const event = stream.next();
const token = event._id;
~~~

Lưu **nguyên vẹn token** để resume, không tự cắt lấy timestamp hoặc một phần _data.

### 6.1. Event token và highwatermark token

MongoDB có cả:

- **Event token:** gắn với một event cụ thể.
- **Highwatermark token:** đại diện một điểm tiến của cluster time khi chưa có event mới; có thể được server trả dưới dạng **postBatchResumeToken** trong phản hồi cursor.

Spring Data ChangeStreamEvent.getResumeToken() chủ yếu giúp xử lý token của các events mà abstraction phát ra. Nếu cần checkpoint cả highwatermark ở thời điểm idle, phải dùng API driver/cursor cung cấp postBatchResumeToken và tuân thủ quy tắc chỉ checkpoint sau khi mọi event trước mốc đó đã được xử lý.

### 6.2. Token không phải đồng hồ

Không sắp xếp hay so sánh resume tokens bằng thứ tự chữ cái của chuỗi JSON. Token là BSON opaque và format có thể đổi theo server/version. Một checkpoint nên lưu token cùng metadata: stream identity, watch scope, pipeline version và thời điểm quan sát.

### 6.3. Một stream identity cần một checkpoint rõ ràng

~~~javascript
{
  _id: "orders-projection-v1",
  watchScope: "commerce.orders",
  pipelineVersion: 1,
  resumeTokenJson: "{ \"_data\": \"8265...\" }",
  lastOperation: "update",
  updatedAt: ISODate("2025-06-01T12:00:00Z")
}
~~~

Trường resumeTokenJson là **ví dụ serialization**, không phải hợp đồng bắt buộc. Có thể lưu BSON token dưới dạng native BSON/BsonDocument nếu codec và storage schema được kiểm chứng. Khi dùng JSON, phải **round-trip Extended JSON không mất type** và bảo vệ dữ liệu checkpoint.

## 7. Checkpoint đúng thứ tự: xử lý trước, lưu token sau

Timeline an toàn về replay:

~~~mermaid
sequenceDiagram
    participant M as MongoDB Change Stream
    participant C as Consumer
    participant P as Projection/Inbox
    participant K as Checkpoint
    M->>C: Event E1 + token T1
    C->>P: Apply idempotent effect E1
    P-->>C: Đã xử lý bền vững
    C->>K: Persist token T1
    K-->>C: Checkpoint thành công
    Note over C: Mới bắt đầu coi E1 đã commit về mặt consumption
~~~

### 7.1. Lưu token trước effect là nguy hiểm

~~~text
T0: nhận event E1
T1: checkpoint T1 thành công
T2: crash trước khi cập nhật read model
T3: resumeAfter(T1) => bỏ qua E1
~~~

Kết quả: projection bị thiếu dữ liệu, và token mới khiến E1 không còn trong luồng phát tiếp thông thường.

### 7.2. Lưu token sau effect có thể lặp — và đó là lý do cần idempotency

~~~text
T0: nhận E1
T1: cập nhật projection thành công
T2: crash trước checkpoint T1
T3: resumeAfter(T0) => nhận lại E1
T4: idempotent handler nhận ra E1 đã được áp dụng
T5: checkpoint T1
~~~

Thiết kế này có thể xử lý replay an toàn khi marker/effect là bền vững.

### 7.3. Transaction giúp loại bỏ khoảng hở

Nếu **inbox marker, projection update và checkpoint đều ở cùng MongoDB deployment** và tham gia một transaction MongoDB:

~~~text
BEGIN TRANSACTION
  insert inbox marker(event E1)
  update projection
  update checkpoint(T1)
COMMIT
~~~

Sau commit, ba thay đổi được ghi cùng nhau; nếu abort, không có thay đổi nào được commit. Điều này **không bao gồm** gửi HTTP/email ngoài MongoDB và phụ thuộc topology, session/transaction options.

## 8. Ma trận crash: dự đoán sự kiện bị lặp hay bị mất

| Điểm crash | Effect được lưu? | Checkpoint được lưu? | Khi restart |
| --- | --- | --- | --- |
| Trước khi xử lý E1 | Chưa | Chưa | E1 có thể được phát lại |
| Sau effect, trước token | Rồi | Chưa | E1 có thể phát lại; inbox phải dedupe |
| Sau token, trước effect | Chưa | Rồi | **Có nguy cơ mất E1** |
| Sau transaction commit effect+token | Rồi | Rồi | Resume sau E1 |
| Transaction abort | Không | Không | E1 được thử lại nếu còn oplog |
| Effect bên ngoài đã xảy ra, local transaction abort | Có thể rồi | Không | Downstream cần idempotency riêng |

### 8.1. Không “fix” bằng retry vô hạn

Retry giúp đối phó lỗi tạm thời nhưng **không giải quyết transaction gap** và không hồi sinh được oplog đã bị truncate. Retry phải đi kèm phân loại lỗi, giới hạn thời gian, metrics và recovery plan.

### 8.2. Tại sao không checkpoint khi nhận event?

Callback onNext chỉ chứng minh consumer **đã đọc được bytes/event**. Nó không chứng minh projection, outbox hay business operation đã được commit. Checkpoint cần đại diện **last durably processed position**, không chỉ last observed position.

## 9. Mở stream và resume trong mongosh

Thực hành trên **replica set test database**, không dùng collection production để tạo/sửa/xóa dữ liệu.

~~~javascript
use commerce;

const stream = db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);

const first = stream.next();
printjson(first);

const token = first._id;
stream.close();
~~~

Lời gọi **next()** có thể chờ cho tới khi có event. Đối với một ví dụ điều khiển được, mở watch trước, từ một session khác thực hiện insert/update trên collection. Trong script tự động nên dùng tryNext/timeout/cancellation thích hợp thay vì đợi vô thời hạn.

### 9.1. Resume sau event

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    resumeAfter: token,
    fullDocument: "updateLookup"
  }
);
~~~

**resumeAfter(T)** mở cursor bắt đầu **sau** sự kiện được token T xác định. Cần đảm bảo token vẫn nằm trong khả năng khôi phục của oplog và watch pipeline/options phù hợp với lần tạo token.

### 9.2. Không tự chế token từ clusterTime

~~~javascript
// Sai về bản chất:
const token = { _id: first.clusterTime };
~~~

Token có BSON shape do MongoDB tạo, không phải một object ứng dụng tùy ý. Nếu muốn khởi chạy theo timestamp, dùng **startAtOperationTime** với BSON Timestamp phù hợp, không giả mạo resume token.

### 9.3. Bắt đầu theo thời điểm

~~~javascript
const startTime = Timestamp({ t: 1730462400, i: 1 });

const byTime = db.orders.watch(
  [],
  { startAtOperationTime: startTime }
);
~~~

Điểm bắt đầu phải còn thuộc cửa sổ lịch sử oplog. Timestamp không xác định một event riêng biệt giống resume token và không luôn đủ độ chính xác khi nhiều events cùng thời gian.

### 9.4. Không dùng đồng thời ba lựa chọn

Các options **resumeAfter**, **startAfter** và **startAtOperationTime** là những cách chọn điểm bắt đầu thay thế nhau, không được kết hợp tùy tiện trong một watch.

### 9.5. Giữ pipeline/options đồng nhất

MongoDB khuyến nghị dùng **cùng pipeline và options** khi resume từ token. Nếu thay đổi aggregation filters, collation hoặc fullDocument options theo cách không tương thích, server có thể không resume đúng hoặc kết quả có thể không theo kỳ vọng. Ghi **pipelineVersion** trong checkpoint để triển khai/migration có kiểm soát.

## 10. Invalidate là gì?

**invalidate** là một change event đánh dấu stream đang theo dõi không còn hợp lệ theo phạm vi namespace hiện tại, ví dụ vì collection đã drop hoặc rename.

~~~javascript
{
  _id: { _data: "opaque-invalidate-token" },
  operationType: "invalidate",
  clusterTime: Timestamp({ t: 1730462401, i: 1 })
}
~~~

Cursor thường **đóng sau invalidate**. Không xử lý invalidate như một update có fullDocument.

### 10.1. Khi nào xuất hiện invalidate?

| Watch scope | Thao tác DDL liên quan | Kết quả thường gặp |
| --- | --- | --- |
| Collection orders | Drop chính collection orders | Drop event và invalidate; cursor đóng |
| Collection orders | Rename collection orders | Invalidate; cursor đóng |
| Collection orders | Drop database chứa orders | Invalidate; cursor đóng |
| Database commerce | Drop một collection con | Database watch có thể thấy drop event; không mặc định invalidate toàn database |
| Database commerce | Drop chính database commerce | Invalidate database watch; cursor đóng |
| Deployment watch | DDL của một collection/database | Scope khác, cần đọc loại event và API; không tự áp quy tắc collection watch |

Các phiên bản MongoDB có thể hỗ trợ thêm expanded DDL events khi cấu hình **showExpandedEvents**. Đừng đặt logic phụ thuộc chính xác một chuỗi DDL events mà chưa integration test trên server version mục tiêu.

### 10.2. Drop, rename khác update/delete

Một **delete** document bình thường không khiến collection watch bị invalidate. **Drop collection** là thay đổi namespace/collection lifecycle, có tác động rộng hơn.

### 10.3. Có cần phát sự kiện nghiệp vụ cho invalidate?

Thông thường consumer nên:

1. Lưu trạng thái stream bị invalidate.
2. Dừng nhận business updates cũ.
3. Báo động nếu việc drop/rename không nằm trong kế hoạch migration.
4. Quyết định có tạo stream mới, đổi namespace hay rebuild read model không.

Không chuyển invalidate thành “xóa một order” hoặc gửi notification cho khách hàng theo kiểu event business thông thường.

## 11. resumeAfter và startAfter khác nhau ở điểm nào?

| Tình huống | resumeAfter(token) | startAfter(token) |
| --- | --- | --- |
| Token của event thông thường, history còn | Thường là lựa chọn chuẩn | Có thể dùng theo contract mở luồng mới |
| Token của **invalidate event** | **Không được dùng** | **Có thể mở stream mới sau invalidate** |
| Token đã rơi khỏi oplog | Không thể resume | Không thể khôi phục lịch sử đã mất |
| Pipeline/options khác lúc tạo token | Rủi ro/không được bảo đảm | Cũng cần giữ tính tương thích |
| Namespace cũ đã drop | Không khôi phục collection | Chỉ mở luồng sau invalidate; không tái tạo dữ liệu đã mất |

### 11.1. Mongosh: startAfter invalidate

~~~javascript
// Giả sử đã nhận và lưu nguyên vẹn token của sự kiện invalidate:
const invalidateToken = {
  _data: "token-from-real-invalidate-event"
};

const freshCursor = db.orders.watch(
  [],
  { startAfter: invalidateToken }
);
~~~

Đoạn trên chỉ minh họa **hình thức option**, token giả không dùng được. Cần lưu token thực từ event invalidate. Trên một collection bị drop, có thể cần chờ collection được tạo lại, điều chỉnh watch scope hoặc áp chính sách triển khai khác.

### 11.2. Điều kiện startAfter thành công

**startAfter không vượt qua giới hạn retention.** Server vẫn phải còn đủ lịch sử nhận diện token. Namespace đã bị rename hoặc drop không tự được khôi phục; nếu ứng dụng cần đọc state mới, phải đánh giá collection mới/collection được tạo lại và migration.

### 11.3. Không đổi resumeAfter thành startAfter cho mọi exception

Lỗi network thoáng qua, permission denied, pipeline lỗi và invalidate không cùng ý nghĩa. Dùng startAfter bừa bãi có thể che giấu những thay đổi DDL không được phép hoặc khiến consumer tiếp tục trên một dataset khác với dataset trước đó.

### 11.4. Sau invalidate, có nên tự tạo lại collection?

Không mặc định. Việc tạo lại collection có thể thay đổi UUID, indexes, validators, sharding, quyền và ý nghĩa dữ liệu. Quy trình migration/deployment phải quyết định. Một consumer đọc change stream thường **không nên tự ý tạo schema** khi phát hiện drop.

## 12. State machine cho consumer khi gặp invalidate

Một handler production không chỉ có trạng thái “đang chạy” và “retry”.

~~~mermaid
flowchart TD
    A["STREAMING"] -->|event bình thường| B["PROCESSING"]
    B -->|commit effect + checkpoint| A
    A -->|temporary error| C["RETRY_WAIT"]
    C -->|token còn hợp lệ| A
    A -->|invalidate| D["INVALIDATED"]
    D -->|approved migration / new scope| E["START_AFTER"]
    E -->|watch mới hợp lệ| A
    D -->|chưa được duyệt| F["PAUSED + ALERT"]
    C -->|history lost| G["RECOVERY_REQUIRED"]
    G -->|rebuild / reconcile| H["NEW_BASELINE"]
    H --> A
~~~

### 12.1. Xử lý invalidate trước khi lọc business events

Nếu pipeline server-side chỉ match operationType=insert/update và bỏ toàn bộ invalidate/DDL signals, consumer có thể không quan sát được điểm kết thúc quan trọng. Một cách an toàn hơn là nhận **tất cả operation types liên quan đến lifecycle**, xử lý invalidate/control events trước, rồi chỉ đưa events nghiệp vụ tới handler tương ứng.

Nếu cần filter server-side để giảm lưu lượng, phải chứng minh filtering không phá khả năng nhận diện invalidate và resume; kiểm thử trên MongoDB Server thực.

### 12.2. Không checkpoint qua một control event chưa được xử lý

Nếu nhận invalidate token nhưng chưa quyết định scope mới, lưu token dưới dạng checkpoint bình thường rồi tự retry có thể khiến system khởi động bằng lựa chọn sai. Nên lưu **lastInvalidateToken + trạng thái INVALIDATED**, kèm thông tin DDL, để recovery logic quyết định dùng startAfter hay cần rebuild.

### 12.3. Lưu trữ trạng thái

~~~javascript
{
  _id: "orders-projection-v1",
  state: "INVALIDATED",
  watchScope: "commerce.orders",
  lastInvalidateTokenJson: "{ \"_data\": \"...\" }",
  reason: "collection_drop",
  detectedAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Trong một sistema nhiều instance, nên có **owner lease/fencing token** và hạn chế worker nào được thay đổi trạng thái, tránh hai consumer đồng thời quyết định các điểm resume khác nhau.

## 13. Oplog retention: resume token không giữ được lịch sử

MongoDB sử dụng oplog để ghi lại lịch sử các thao tác của replica set. Oplog hoạt động như một vùng lịch sử có giới hạn; khi ghi nhiều, các entry cũ có thể bị loại bỏ.

~~~text
Oplog window:
|---------- lịch sử còn lưu ----------|
T_old                              T_new

Consumer checkpoint ở T_old - 2h
Nếu T_old đã tiến vượt checkpoint, resume có thể thất bại.
~~~

### 13.1. Retention không bằng tuổi của checkpoint record

Một document checkpoint có thể được giữ 1 năm trong collection của ứng dụng. **Nó không buộc MongoDB giữ 1 năm oplog**. Server chỉ resume khi lịch sử cần thiết còn đủ để định vị token/thời điểm.

### 13.2. Không hứa “chắc chắn giữ 24 giờ” chỉ từ oplog size

Thời gian lịch sử phụ thuộc:

- Kích thước oplog.
- Tốc độ ghi trên deployment.
- Transaction/bulk behavior.
- Cấu hình retention của MongoDB.
- Dung lượng đĩa và chính sách vận hành.
- Tải theo thời điểm (peak writes khác daily average).

MongoDB có cấu hình minimum oplog retention ở các phiên bản hỗ trợ; nó có trade-off về disk và không nên coi như khả năng resume vô hạn. Luôn đo **thực tế earliest oplog entry** và consumer lag.

### 13.3. Công thức quan sát cửa sổ an toàn

Giả sử:

- Lịch sử thực tế còn **H phút**.
- Consumer chậm hơn sự kiện mới nhất **L phút**.
- Thời gian khắc phục sự cố và bắt kịp dự kiến **R phút**.

Một chỉ số cảnh báo thô:

\[
M=H-(L+R)
\]

Nếu M <= 0, consumer có nguy cơ vượt qua history window trong thời gian recovery. **Công thức chỉ để capacity planning**, không phải MongoDB guarantee; event timestamps, oplog age và sharded idle behavior có thể khiến phép đo thực phức tạp hơn.

### 13.4. Oplog window trên sharded cluster

Một change stream từ sharded cluster có thể đi qua nhiều shards. Cửa sổ history/resume phụ thuộc lịch sử các shard liên quan, thao tác di chuyển chunk/shard và hoạt động mongos. Không nhìn một oplog window của một shard rồi kết luận cả stream an toàn.

## 14. History lost: khi nào retry không còn ích?

Nếu resume token trỏ tới thao tác đã rời oplog, MongoDB không còn đủ thông tin để tiếp tục theo cách đã checkpoint. Lỗi có thể được thông báo như **ChangeStreamHistoryLost** (một số trường hợp mã lỗi 286), hoặc thông qua thông báo cụ thể của driver/server.

### 14.1. Không tự xóa checkpoint và bắt đầu từ hiện tại

~~~text
T0: checkpoint đã xử lý tới event E100
T1: ứng dụng offline quá lâu
T2: oplog đã loại E101..E900
T3: resume từ E100 thất bại
T4: consumer bỏ token, watch từ now
=> E101..E900 không bao giờ được áp dụng
~~~

Nếu read model, search index, metrics hoặc notifications phụ thuộc tất cả events, đây là một **data gap** nghiêm trọng. Bắt đầu từ now chỉ hợp lệ khi nghiệp vụ **chủ động chấp nhận bỏ lỡ** và ghi nhận sự mất mát.

### 14.2. Phân loại lỗi trước retry

| Lỗi | Hướng xử lý |
| --- | --- |
| Mất kết nối tạm thời | Retry có backoff/jitter, resume từ checkpoint |
| Election/repl state change có thể resume | Để driver xử lý theo contract; app có kế hoạch khởi động lại cursor |
| Poison event do code/validation | Không checkpoint qua; DLQ/quarantine theo policy và recovery |
| Invalidate | PAUSED/INVALIDATED; đánh giá startAfter/new scope |
| Change stream history lost | **REBUILD/RECONCILIATION** hoặc explicit data-loss acceptance |
| Authentication/authorization failure | Sửa credentials/policy, không retry vô hạn |
| Pipeline compatibility error | Sửa pipeline/deployment, không đổi token tùy tiện |

### 14.3. Recovery không được tạo một khoảng hở mới

Một quy trình rebuild projection cần kết hợp **snapshot hiện tại** với **events được giữ từ một mốc rõ ràng**. Nếu đơn giản đọc snapshot trong 20 phút rồi mở watch từ hiện tại, các updates trong 20 phút ấy có thể bị thiếu hoặc được áp dụng sai.

Một mô hình có thể là:

1. Dừng worker cũ và giữ ownership/lease.
2. Chọn một recovery baseline có thể gắn với **stream position** còn hợp lệ.
3. Mở/neo stream từ mốc đó trước khi quét snapshot, hoặc dùng một snapshot/read timestamp có hợp đồng nhất quán phù hợp.
4. Build lại read model từ dữ liệu nguồn.
5. Replay thay đổi diễn ra trong quá trình rebuild **đúng thứ tự**, có idempotency.
6. Switch sang read model mới khi đã bắt kịp.
7. Ghi checkpoint và trạng thái recovery cùng quy trình có kiểm chứng.

**Chi tiết thuật toán** phải được thiết kế theo topology, read concern và khối lượng dữ liệu. Nếu history window đã bị mất hoàn toàn và không có nguồn events khác, không thể khôi phục chính xác mọi intermediate event chỉ từ snapshot hiện tại.

## 15. Retention của pre-images và post-images là một vấn đề riêng

MongoDB 6.0 trở lên hỗ trợ **change stream pre- and post-images** với cấu hình collection thích hợp.

~~~javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

Các images là dữ liệu “trước/sau” một thao tác, khác **resume token** và khác tập events trong oplog.

### 15.1. Hai loại retention không được gộp làm một

| Thành phần | Vai trò | Giới hạn |
| --- | --- | --- |
| Oplog entries | Cơ sở lịch sử change stream và khả năng resume | Phụ thuộc oplog retention window |
| Pre-images | Document trước update/delete | Phụ thuộc tính năng và pre/post image retention |
| Post-images | Document sau insert/update/replace | Phụ thuộc cấu hình/version/retention |
| Checkpoint collection | Token/tiến độ ứng dụng đã xử lý | Không tự kéo dài lịch sử oplog |
| Read model | Trạng thái tổng hợp phục vụ query | Phải rebuild/reconcile khi có gap |

### 15.2. expireAfterSeconds

MongoDB có cluster parameter **changeStreamOptions.preAndPostImages.expireAfterSeconds** trên deployment hỗ trợ. Khi ở trạng thái **off** mặc định theo tài liệu, images được giữ tới khi các events tương ứng bị loại khỏi oplog; không có nghĩa “giữ vĩnh viễn”.

Nếu entry oplog tương ứng bị loại, images cũng bị xóa **bất kể** expireAfterSeconds đặt dài hơn. Không dùng cấu hình pre-image retention để suy rằng một resume token cũ sẽ vẫn hợp lệ.

### 15.3. fullDocument: updateLookup không phải historical snapshot

~~~javascript
db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
~~~

Khi cần lookup document cho update event, MongoDB có thể trả **version majority-committed hiện tại** tại thời điểm lookup. Một update mới có thể đã xảy ra trước lookup; fullDocument có thể khác nội dung ngay sau event đang xét hoặc null trong một số trường hợp.

Nếu nghiệp vụ đòi chính xác before/after của một thay đổi, phải đánh giá pre/post-images theo contract/version/retention và cấu hình **required/whenAvailable** thích hợp; không coi updateLookup là một before/after snapshot chính xác.

## 16. Không có oplog đủ dài: cần chiến lược resilience nhiều tầng

Một hệ thống bền vững nên có:

- **Oplog window lớn hơn** worst-case consumer outage + catch-up time, cộng safety margin.
- **Monitoring lag** và earliest available oplog history, không chỉ monitor service process uptime.
- **Checkpoint bền vững** và có backup.
- **Replay-safe effects** để reprocess không phá dữ liệu.
- **Rebuild/reconcile process** đã được diễn tập.
- **DLQ/quarantine** cho poison events không làm mất visibility.
- **Owner lease/fencing** khi nhiều replicas có thể cạnh tranh stream ownership.
- **Runbook invalidate** riêng với runbook network outage.

### 16.1. Đừng tăng retention vô hạn mà không đo disk

Larger oplog giữ lịch sử lâu hơn nhưng dùng dung lượng và có thể ảnh hưởng hạ tầng. MongoDB minimum retention settings có trade-off disk; cần quan sát disk usage, write throughput và cluster capacity.

### 16.2. Đừng để retry làm trôi thời gian recovery

Nếu error cho biết history đã mất, mỗi giờ chỉ retry lại cùng token khiến read model ngày càng lạc hậu. Chuyển trạng thái **RECOVERY_REQUIRED**, alert và thực hiện rebuild có kiểm soát.

## 17. Inbox: lưu dấu sự kiện đã được áp dụng

Một mẫu phổ biến là **idempotent consumer/inbox**. Mỗi event được gán một key duy nhất trong collection đánh dấu:

~~~javascript
{
  _id: "orders-projection-v1:sha256(eventResumeToken)",
  streamId: "orders-projection-v1",
  eventTokenJson: "{ \"_data\": \"...\" }",
  operationType: "update",
  appliedAt: ISODate("2025-06-01T12:00:01Z")
}
~~~

MongoDB có unique index trên **_id** trong collection. Hai attempts cố gắng insert cùng marker sẽ không thể cùng commit thành công như hai document độc lập.

### 17.1. Key của inbox

~~~text
inboxId = streamId + ":" + SHA256(serializeResumeToken(token))
~~~

**streamId** phân biệt hai projections có cùng source nhưng tác dụng khác nhau. **Resume token** phân biệt hai events trên cùng Order. Không dùng documentKey._id làm key duy nhất của inbox, vì một Order sẽ có nhiều updates hợp lệ.

### 17.2. ClusterTime không phải event identity

Nhiều events có thể cùng clusterTime, đặc biệt trong transaction/sharded cluster. Không tạo inbox key bằng clusterTime một mình. Nếu nghiệp vụ cần nhận diện transaction, lsid/txnNumber có semantics riêng theo MongoDB version, nhưng không thay resume token event.

### 17.3. Marker cần bền vững cùng effect

Nếu marker đã ghi nhưng projection update thất bại, lần retry thấy marker sẽ bỏ qua event và read model bị thiếu. Vì vậy marker và effect nên **atomic trong MongoDB transaction**, hoặc có protocol trạng thái có thể recover.

### 17.4. Dedupe trong RAM không đủ

Set lưu những token đã thấy trong bộ nhớ mất khi process restart và có thể tăng vô hạn. Dùng storage bền vững cùng unique constraint; có kế hoạch retention đủ dài so với replay horizon.

## 18. Phân biệt event idempotency và business idempotency

| Effect | Lặp có an toàn? | Chiến lược |
| --- | --- | --- |
| Set status=PAID | Có với cùng trạng thái, nhưng có thể đảo thứ tự | Upsert + business version |
| Inc doanh thu | **Không** | Payment ID duy nhất + atomic inbox/transaction |
| Push một item vào array | **Không** | Unique item ID hoặc set semantics phù hợp |
| Gửi email | Không được bảo đảm | Outbox + downstream idempotency |
| Đánh dấu event đã xử lý | Có khi marker unique | Unique inbox key theo stream/token |
| Xóa projection | Có thể, nếu delete đúng phiên bản | Version/order guard |

### 18.1. Hai events khác tokens có thể đại diện cùng business command

~~~text
E1: token=T1, orderId=O1, paymentId=P100
E2: token=T2, orderId=O1, paymentId=P100
~~~

Nếu một request thanh toán được ghi lại hai lần, cả E1 và E2 đều có identity riêng ở tầng stream, nhưng business payment **P100** phải được xử lý một lần theo yêu cầu nghiệp vụ. Unique index có thể là:

~~~javascript
db.payments.createIndex(
  { tenantId: 1, paymentId: 1 },
  { unique: true, name: "uniq_payment_per_tenant" }
);
~~~

**Inbox token** bảo vệ replay một event; **business paymentId** bảo vệ lặp command ở một tầng khác.

### 18.2. Set không bảo vệ thứ tự

~~~text
E1: status=PAID, version=5
E2: status=REFUNDED, version=6
~~~

Nếu consumer áp E2 trước rồi E1 sau, một update set(status=PAID) sẽ ghi đè dữ liệu mới hơn dù cả hai events đều chỉ được xử lý một lần. Cần tuần tự hóa theo key hoặc so sánh **version** của aggregate; không dùng so sánh chuỗi resume tokens làm version.

## 19. Atomic apply + checkpoint bằng MongoDB transaction

Mẫu kiến trúc:

~~~text
orders (nguồn)
processed_change_events (inbox)
order_summaries (projection)
change_checkpoints (checkpoint)
~~~

Ba thành phần inbox, projection và checkpoint có thể được ghi cùng MongoDB transaction nếu ở **cùng deployment**, qua đúng session/transaction manager. Transaction phải ngắn; không chờ cursor hoặc gửi HTTP trong transaction.

### 19.1. Cấu hình manager

~~~java
package com.example.changestream;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class ChangeStreamTxConfiguration {

    @Bean("mongoTransactionManager")
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

MongoDB phải hỗ trợ transactions (replica set hoặc sharded cluster thích hợp). Gọi @Transactional method qua Spring proxy, không self-invocation.

### 19.2. Một transactional handler dành riêng cho INSERT

~~~java
package com.example.changestream;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;
import org.bson.BsonValue;
import org.bson.Document;
import com.mongodb.client.model.changestream.OperationType;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderChangeApplier {

    private static final String STREAM = "orders-projection-v1";
    private final MongoTemplate template;

    public OrderChangeApplier(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void applyInsert(ChangeStreamEvent<Document> event) {
        if (event.getOperationType() != OperationType.INSERT) {
            throw new IllegalArgumentException(
                "INSERT events only");
        }

        BsonValue token = Objects.requireNonNull(
            event.getResumeToken(), "Missing resume token");
        String tokenJson = token.asDocument().toJson();
        String eventId = STREAM + ":" + sha256(tokenJson);
        Query eventKey = Query.query(
            Criteria.where("_id").is(eventId));

        boolean alreadyApplied = template.exists(
            eventKey, "processed_change_events");

        if (!alreadyApplied) {
            template.insert(
                new Document("_id", eventId)
                    .append("streamId", STREAM)
                    .append("tokenJson", tokenJson)
                    .append("appliedAt", java.util.Date.from(
                        Instant.now())),
                "processed_change_events");

            Document body = Objects.requireNonNull(
                event.getBody(), "Insert body required");
            Object orderId = Objects.requireNonNull(
                body.get("_id"), "Order ID required");

            template.upsert(
                Query.query(Criteria.where("_id").is(orderId)),
                new Update()
                    .set("tenantId", body.getString("tenantId"))
                    .set("status", body.getString("status"))
                    .set("orderNo", body.getString("orderNo")),
                "order_summaries");
        }

        template.upsert(
            Query.query(Criteria.where("_id").is(STREAM)),
            new Update()
                .set("resumeTokenJson", tokenJson)
                .set("streamState", "STREAMING")
                .set("checkpointAt", java.util.Date.from(
                    Instant.now())),
            "change_checkpoints");
    }

    private static String sha256(String raw) {
        try {
            MessageDigest md =
                MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(
                md.digest(raw.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }
}
~~~

### 19.3. Giới hạn cần hiểu trước khi copy code

- **Chỉ dùng cho INSERT events**. UPDATE, REPLACE, DELETE và INVALIDATE có logic riêng; không thể lấy getBody() vô điều kiện.
- **template.exists không khóa concurrency**. Hai workers có thể cùng thấy false; unique _id và MongoDB transaction quyết định xung đột. Retry **toàn transaction** khi phù hợp.
- **Checkpoint cùng transaction** chỉ an toàn nếu một active owner giữ thứ tự token; nhiều workers ghi token trái thứ tự có thể làm checkpoint lùi. Cần lease/fencing.
- Dùng SHA-256 để tạo inbox key gọn; serialization token phải ổn định qua lưu/đọc. Đừng cắt token opaque.
- Không giữ transaction mở khi change stream đang chờ event.
- Ví dụ là integration pattern, chưa chứa cấu hình retries, transaction options, lease, logging và migration.

### 19.4. Nếu token cũ được replay

Khi marker đã tồn tại, handler không áp projection lần nữa nhưng vẫn tiến checkpoint trong transaction. Trong mô hình **một owner xử lý events tuần tự**, đây là một đường recovery. Nếu có nhiều owners, bắt buộc dùng fencing/checkpoint compare-and-set, không chỉ làm upsert vô điều kiện.

## 20. Side effect ngoài MongoDB: outbox và downstream idempotency

Giả sử event PAID cần gửi email hoặc publish một message:

~~~text
Change event E1
     |
     v
MongoDB transaction:
  - insert inbox marker E1
  - update order_summaries
  - insert outbox record (business key cố định)
  - update checkpoint E1
     |
     v
Outbox worker -> Email provider / Broker
~~~

### 20.1. Vì sao không gửi email trong transaction?

~~~java
// Phản ví dụ: email không tự rollback khi MongoDB abort.
emailClient.sendConfirmation(order);
mongoTemplate.upsert(
    checkpointQuery, checkpointUpdate, "change_checkpoints");
~~~

Nếu email thành công nhưng MongoDB transaction rollback, retry event có thể gửi lần nữa. Transaction của MongoDB không kiểm soát email provider.

### 20.2. Outbox idempotency key

~~~javascript
{
  _id: "order-paid:shop-a:P100",
  type: "ORDER_PAID_EMAIL",
  tenantId: "shop-a",
  orderId: ObjectId("507f1f77bcf86cd799439011"),
  paymentId: "P100",
  state: "PENDING",
  attempts: 0
}
~~~

Unique _id giữ một outbox command cho cùng business payment. Outbox sender có thể retry khi timeout; nếu downstream hỗ trợ idempotency key thì truyền nguyên key qua mỗi lần thử.

### 20.3. Nếu nhà cung cấp email không hỗ trợ idempotency?

Không thể hứa “email exactly-once” chỉ bằng outbox local. Có thể giảm trùng qua provider message ID, suppression windows, inbox phía nhận hoặc trạng thái nghiệp vụ, nhưng vẫn có khoảng không biết request trước đã thành công hay chưa. Ghi nhận contract và xử lý retry phù hợp.

### 20.4. Dedupe retention

Không TTL-delete inbox markers sau 1 ngày nếu ứng dụng có thể replay/rebuild 7 ngày. Marker retention phải đủ cho độ dài replay/reconciliation mong muốn hoặc dùng business idempotency lâu dài hơn. TTL của marker **khác** retention của oplog.

## 21. Thứ tự xử lý, parallelism và checkpoint

Một change stream phát events theo thứ tự hợp đồng của stream, nhưng consumer có thể phá thứ tự nếu chạy nhiều handler song song.

~~~java
// Có thể khiến E2 hoàn thành trước E1:
return eventFlux.flatMap(this::processAsync, 32);
~~~

Ví dụ E1(status=PAID,version=5) xử lý 2 giây, E2(status=REFUNDED,version=6) xử lý 10 ms. E2 có thể ghi trước E1, khiến projection cuối cùng bị đảo ngược.

### 21.1. ConcatMap: lựa chọn dễ hiểu cho một checkpoint

~~~java
return eventFlux.concatMap(this::processAndCheckpoint);
~~~

concatMap chờ inner Publisher trước hoàn tất rồi mới xử lý tiếp event sau. Với một subscription và một checkpoint, nó giúp thứ tự **processing completion** khớp với thứ tự events.

### 21.2. Khi throughput đòi parallelism

Có thể phân vùng theo aggregateId và xử lý tuần tự trong từng key, song song giữa keys. Tuy nhiên checkpoint của **toàn stream** phải được nâng tới **highest contiguous processed position**: không checkpoint token E500 khi E499 vẫn chưa commit.

Đây là bài toán điều phối phức tạp hơn concatMap, đặc biệt trong sharded streams. Không chạy flatMap concurrency cao rồi cho mỗi handler upsert checkpoint không có guard.

### 21.3. Owner lease và fencing

Nếu có hai instance:

~~~text
Worker A: xử lý E101..E200
Worker B: còn đang xử lý E101..E150
~~~

Worker B có thể vô tình ghi checkpoint token T150 sau khi A đã ghi T200. Resume token là opaque nên không thể dùng so sánh chuỗi để nhận biết “T200 lớn hơn T150”.

Giải pháp: **một active owner cho stream**, lease có hạn, fencing generation tăng mỗi lần đổi owner, và conditional update checkpoint chỉ cho generation được phép. Với leader failover, retry phải dựa trên trạng thái bền vững, không tin trạng thái RAM của worker cũ.

### 21.4. Cùng clusterTime vẫn có nhiều events

Một transaction có thể sinh nhiều change events, nên không thể dedupe hoặc checkpoint từng event chỉ bằng clusterTime. Resume token event và thứ tự stream có thông tin cần cho consumption.

## 22. Spring Data MongoDB: reactive change stream cơ bản

Spring Data cung cấp **ReactiveMongoTemplate** để nghe change stream như một Flux:

~~~java
package com.example.changestream;

import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;

public class RawOrderWatcher {

    private final ReactiveMongoTemplate template;

    public RawOrderWatcher(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<Document>> events() {
        return template.changeStream(Document.class)
            .watchCollection("orders")
            .listen();
    }
}
~~~

**Document.class** cho phép đọc body ở dạng BSON-mapped Document thay vì ép vào một domain type có thể không phù hợp cho delete/invalidate/DDL.

### 22.1. Không phải mọi event đều có body

~~~java
Flux<ChangeStreamEvent<Document>> events = watcher.events();

return events.doOnNext(event -> {
    System.out.println(event.getOperationType());
    System.out.println(event.getResumeToken());
});
~~~

Đừng gọi event.getBody().getString("status") trước khi kiểm tra operationType và null. **DELETE** và **INVALIDATE** không có fullDocument như INSERT.

### 22.2. Subscription và cursor

Flux change stream là Publisher dài hạn. Không có subscriber thì không có lệnh listen thực sự. Khi ứng dụng dừng, phải dispose subscription/hủy cursor theo application lifecycle; không để nhiều subscriptions vô tình mở duplicate stream cùng một checkpoint.

### 22.3. Dùng filter có chủ đích

Nếu chỉ cần status=PAID, có thể filter business logic **sau khi xử lý control events**, hoặc dùng server-side pipeline được kiểm thử kỹ. Một filter server-side bỏ hết invalidate/DDL có thể khiến consumer không thấy dấu hiệu quan trọng để chuyển trạng thái.

### 22.4. Reactive không đồng nghĩa exactly-once

Flux, backpressure, retryWhen và concatMap là công cụ composition. Không operator nào tự lưu checkpoint nguyên tử với effect, kéo dài oplog hay cung cấp business idempotency.

## 23. Resume một reactive stream từ checkpoint

Spring Data MongoDB cung cấp **ChangeStreamOptions** có builder resumeAfter/startAfter. Với một token đã lưu dưới dạng Extended JSON:

~~~java
import org.bson.BsonDocument;
import org.bson.BsonValue;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;

public Flux<ChangeStreamEvent<Document>> openResumedStream(
        ReactiveMongoTemplate template,
        String tokenJson) {

    BsonValue token = BsonDocument.parse(tokenJson);
    ChangeStreamOptions options = ChangeStreamOptions
        .builder()
        .resumeAfter(token)
        .build();

    return template.changeStream(
        "orders", options, Document.class);
}
~~~

Đoạn này dùng overload ChangeStreamOptions của **ReactiveMongoOperations**. Spring Data versions hiện hành cũng cung cấp fluent API changeStream(...).watchCollection(...).resumeAfter(token).listen().

### 23.1. Khi chưa có checkpoint?

Nếu service khởi động lần đầu và không có token:

~~~java
ChangeStreamOptions options = ChangeStreamOptions.empty();
~~~

Điều này thường mở stream cho các thay đổi **từ thời điểm bắt đầu theo dõi**, không tự replay toàn bộ lịch sử document. Nếu read model cần cả dữ liệu cũ, phải có **initial snapshot/build + mốc event stream** với một kế hoạch tránh gap.

### 23.2. Sau invalidate không dùng resumeAfter

Nếu checkpoint store đang có **state=INVALIDATED** và token của invalidate event, phải dùng nhánh recovery đã được duyệt với:

~~~java
ChangeStreamOptions options = ChangeStreamOptions
    .builder()
    .startAfter(invalidateToken)
    .build();
~~~

Không tự áp nhánh đó cho mọi token; nhớ rằng token còn phải nằm trong oplog history.

### 23.3. Serialization phải giữ BSON types

BsonDocument.parse là lựa chọn minh họa với Extended JSON token được lưu nguyên vẹn. Không serialize token chỉ bằng cách cắt chuỗi _data hay gọi hash rồi cố xây lại token từ hash; **hash chỉ dùng cho inbox key**, không thể thay token thật khi resume.

### 23.4. Lưu pipeline version

Checkpoint nên chứa watch scope, pipeline version và option set được dùng khi token được tạo. Thay pipeline/filter và vẫn resume từ token cũ có thể gây hành vi khó dự đoán theo cảnh báo của MongoDB.

## 24. Nạp lại checkpoint mỗi lần retry reactive

Một lỗi thường gặp:

~~~java
// Phản ví dụ: options được tạo một lần từ token cũ.
Flux<ChangeStreamEvent<Document>> stream =
    openResumedStream(template, startupTokenJson);

return stream.retryWhen(retryPolicy);
~~~

Khi retry, publisher có thể được subscribe lại từ **startupTokenJson**, dù consumer đã xử lý và checkpoint tiến thêm hàng nghìn events trong lúc chạy.

### 24.1. Dùng Flux.defer và đọc checkpoint bền vững lại

~~~java
import java.util.Optional;
import org.bson.BsonDocument;
import org.bson.BsonValue;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<ChangeStreamEvent<Document>> freshOnSubscribe() {
    return Flux.defer(() ->
        reactiveCheckpointStore.loadTokenJson("orders-projection-v1")
            .map(json -> Optional.of(
                (BsonValue) BsonDocument.parse(json)))
            .defaultIfEmpty(Optional.empty())
            .flatMapMany(optional -> {
                ChangeStreamOptions options = optional
                    .map(token -> ChangeStreamOptions.builder()
                        .resumeAfter(token)
                        .build())
                    .orElseGet(ChangeStreamOptions::empty);

                return reactiveTemplate.changeStream(
                    "orders", options, Document.class);
            })
    );
}
~~~

Đoạn này thuộc một class có **reactiveTemplate** và **reactiveCheckpointStore** được inject; store giả định expose **Mono<String> loadTokenJson(String streamId)**. Đây là skeleton minh họa cách dựng options **mỗi subscription**.

### 24.2. Trường hợp INVALIDATED/RECOVERY_REQUIRED

Mẫu trên chỉ dành cho checkpoint stream ở trạng thái STREAMING bình thường. Production phải đọc **cả state**, không chỉ token:

- STREAMING: có token → resumeAfter.
- NEW: chưa có token → dùng initial-sync policy.
- INVALIDATED: không tự resumeAfter; pause/startAfter có duyệt.
- RECOVERY_REQUIRED: không retry; rebuild/reconcile.

### 24.3. Retry phải được áp sau processing chain

~~~java
return freshOnSubscribe()
    .concatMap(this::processAndCheckpoint)
    .retryWhen(retryPolicy);
~~~

Với một processing chain có thể phát lỗi, retryWhen resubscribe từ đầu **Flux.defer**, nhờ đó checkpoint được nạp lại. Nhưng policy phải **phân loại retryable và non-retryable errors**; không áp retry vô hạn với invalidate/history lost.

### 24.4. Không bỏ error rồi vẫn checkpoint

~~~java
// Phản ví dụ nếu lặng lẽ skip event chưa xử lý:
return process(event)
    .onErrorResume(ex -> Mono.empty())
    .then(saveCheckpoint(event.getResumeToken()));
~~~

Đoạn trên có thể đánh dấu event đã xử lý dù handler thất bại. Nếu dùng DLQ/quarantine, phải định nghĩa rõ khi nào một event được coi là **durably handed off** để an toàn nâng checkpoint.

## 25. Reactive transaction và MongoTemplate đồng bộ không dùng chung context

Ví dụ transactional service ở phần 19 dùng **MongoTemplate** đồng bộ và **MongoTransactionManager**. Không được tự gọi nó trong reactive stream và cho rằng nó nằm trong ReactiveMongoTransactionManager transaction.

~~~java
// Một dạng dễ gây hiểu nhầm:
return eventFlux.flatMap(event ->
    Mono.fromRunnable(() -> syncApplier.applyInsert(event))
);
~~~

Đoạn trên chạy logic đồng bộ trong subscription, có thể chặn thread reactive. Nếu thực sự phải bọc một legacy blocking API, dùng scheduler phù hợp như boundedElastic **chỉ là biện pháp chuyển tiếp**, và transaction đồng bộ vẫn có context riêng.

### 25.1. ReactiveMongoTransactionManager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
class ReactiveChangeTxConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager tx(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Một reactive transactional processing chain:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

TransactionalOperator operator =
    TransactionalOperator.create(
        reactiveMongoTransactionManager);

Mono<Void> effect = insertInbox(event)
    .then(updateProjection(event))
    .then(saveCheckpoint(event))
    .then();

return effect.as(operator::transactional);
~~~

Các hàm **insertInbox, updateProjection, saveCheckpoint** trong skeleton phải trả Publisher từ **cùng reactive MongoDB infrastructure** và dùng đúng session context. Mẫu này mới minh họa atomic chain cho đường event chưa được áp dụng; production cần thêm nhánh **already-applied marker** và duplicate-key retry.

### 25.2. ConcatMap kết hợp transaction

~~~java
return sourceEvents
    .concatMap(event ->
        applyIdempotentlyInReactiveTransaction(event))
    .then();
~~~

Không mở một transaction bao quanh toàn bộ **sourceEvents** vì change stream là một Publisher có thể chạy vô hạn. Transaction chỉ bao **một event hoặc một batch nhỏ**, sau đó commit và giải phóng resource.

### 25.3. Callback/transaction khác exactly-once

Reactor Context đảm bảo transaction propagation đúng trong reactive chain. Nhưng nó không tạo business idempotency, không cấp uniqueness cho outbox và không bảo đảm external HTTP side effects atomic.

## 26. Đồng bộ: MessageListenerContainer và ChangeStreamRequest

Spring Data MongoDB cũng hỗ trợ change streams qua **blocking driver** và messaging infrastructure:

~~~java
import org.bson.Document;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequest;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequest.ChangeStreamRequestOptions;
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListener;
import org.springframework.data.mongodb.core.messaging.MessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.Subscription;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);

MessageListener<ChangeStreamDocument<Document>, Document> listener =
    message -> {
        // Chỉ là chỗ nhận message. Production handler phải
        // phân loại operationType, transaction, checkpoint và errors.
        System.out.println(message.getRaw());
    };

ChangeStreamRequestOptions options =
    new ChangeStreamRequestOptions(
        "commerce", "orders", ChangeStreamOptions.empty());

container.start();
Subscription subscription = container.register(
    new ChangeStreamRequest<>(listener, options),
    Document.class
);

// Khi ứng dụng shutdown: hủy subscription và dừng container.
subscription.cancel();
container.stop();
~~~

Mẫu trên minh họa API, không phải một service chạy thực sự lâu vì nó cancel ngay sau register. Trong production, quản lý container theo **Spring lifecycle** và dừng khi application shutdown.

### 26.1. Vì sao không làm blocking listener trong WebFlux?

MessageListenerContainer sử dụng task dài hạn dựa trên sync driver. Nó phù hợp với một worker được quản lý, không phải một callback chạy trực tiếp trong HTTP event loop. Với workload stream lớn hoặc reactive app, Spring Data khuyến nghị ưu tiên **Reactive Change Streams** để giảm chi phí thread.

### 26.2. Error handler cần rõ ràng

Spring Data messaging layer có cơ chế **ErrorHandler**. Mặc định logging errors không đủ cho một workflow bắt buộc xử lý đủ events. Cần metrics, trạng thái checkpoint, retry/restart policy và alert khi listener dừng.

### 26.3. Listener cần commit trước khi báo tiến độ

Không lấy thời điểm listener callback bắt đầu như là last processed. Nếu callback async-handoff sang thread queue khác rồi return ngay, checkpoint phải theo lifecycle **thực sự hoàn thành/commit** của công việc đó.

### 26.4. Không để hai listener cùng làm một stream mà không coordination

Hai instances cùng đăng ký collection watch thường có thể thấy **cùng thay đổi**; change streams không tự biến thành một competing-consumers work queue để phân phát mỗi event cho một instance. Cần explicit leader/lease hoặc thiết kế fan-out và idempotency riêng.

## 27. Error handling, backoff và poison events

Một consumer nên phân loại lỗi:

| Loại lỗi | Ví dụ | Hành động đề xuất |
| --- | --- | --- |
| Resumable/transient | Connection reset, một số election errors | Backoff + reconnect từ durable checkpoint |
| Processing transient | Timeout của MongoDB projection write | Retry transaction/processing, không checkpoint trước |
| Processing permanent | Event schema không hợp lệ, required field thiếu | Quarantine/DLQ hoặc pause; không silently skip |
| Authorization | Quyền read change stream bị thu hồi | Alert + sửa quyền, không retry tight loop |
| Invalidate | Drop/rename/dropDatabase ảnh hưởng scope | State INVALIDATED, policy startAfter/new scope |
| Retention exhausted | Resume token ngoài oplog | RECOVERY_REQUIRED, rebuild/reconcile |
| Incompatible pipeline | Đổi filter/options khi resume | Fix/deploy migration, không đổi token tùy tiện |
| Duplicate marker conflict | Event đã được apply hoặc concurrent race | Kiểm tra marker/transaction, retry cả handler nếu cần |

### 27.1. RetryWhen có giới hạn

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Retry retryPolicy = Retry.backoff(
        8, Duration.ofSeconds(1))
    .maxBackoff(Duration.ofMinutes(1))
    .jitter(0.25)
    .filter(this::isRetryableTransientFailure);
~~~

isRetryableTransientFailure là **hàm phân loại lỗi của ứng dụng**, cần định nghĩa dựa trên MongoDB exception/error labels, Spring translated exceptions và các lỗi nghiệp vụ.

Không đặt một Predicate luôn trả true. Những lỗi invalidate, history lost và validation phải đổi state/alert, không retry cùng token mãi.

### 27.2. Sau khi hết retries?

Một số hệ thống cho phép supervisor restart worker, nhưng phải:

- Lưu nguyên checkpoint cuối cùng đã commit.
- Phân biệt trạng thái STOPPED/PAUSED/RECOVERY_REQUIRED.
- Ghi error code và lần thử cuối.
- Alert theo SLO.
- Khi restart, **nạp lại checkpoint từ storage**, không dùng biến local stale.

### 27.3. Poison event

Ví dụ event có status không thuộc enum mà converter không parse được. Nếu stream cứ retry nó, các events sau bị chặn; nhưng tự checkpoint bỏ qua có thể mất một thay đổi nghiệp vụ.

Chọn policy có thể audit:

1. **Pause + alert** để sửa schema/handler rồi replay.
2. **Quarantine/DLQ bền vững** chứa token và raw event (đã redacted nếu nhạy cảm), ghi nhận một quyết định skip có chủ đích.
3. **Rebuild projection** sau khi bug được sửa.

Nếu chuyển sang DLQ rồi checkpoint, phải xác định DLQ insertion/ack có đủ bền vững và quyền xử lý lại event sau này.

### 27.4. Lỗi từ fullDocument lookup

fullDocument=updateLookup có thể trả null hoặc document trạng thái mới hơn; handler không được coi đây là lỗi network để retry vô hạn. Xem operationType, updateDescription, source schema/version và yêu cầu consistency.

## 28. Observability: đo lag và nguy cơ hết retention

Một worker “vẫn chạy” nhưng chậm hàng giờ là một sự cố tiềm ẩn dù không có exception.

| Metric | Ý nghĩa |
| --- | --- |
| lastEventReceivedAt | Lần cuối consumer nhận một event |
| lastDurableCheckpointAt | Lần cuối checkpoint được commit |
| lastProcessedClusterTime | Cluster time của event cuối đã xử lý |
| eventProcessingLatency | Thời gian apply + checkpoint |
| consumerLag | Độ trễ so với tiến độ cluster/nguồn dữ liệu |
| oplogHistoryWindow | Lịch sử còn để resume, đo trên deployment |
| retentionSafetyMargin | Oplog window trừ lag và recovery buffer |
| duplicateDetectedCount | Số replay bị inbox ngăn |
| checkpointWriteErrors | Rủi ro token không được nâng |
| invalidationCount | Số lần đổi namespace/scope |
| historyLostCount | Sự cố mất khả năng resume |
| deadLetterCount | Events được quarantine |
| transactionAbortCount | Xung đột, retry, lỗi MongoDB |
| activeStreamOwners | Phát hiện có hơn một worker dùng một checkpoint |
| streamReconnects | Lỗi mạng, elections, unstable cursor |

### 28.1. ClusterTime khác wall clock

MongoDB event.clusterTime là **BSON Timestamp**, không phải một instant duy nhất với nanosecond wall-time semantics. Có thể dùng cluster time cho correlation/progress, nhưng không dùng timestamp ấy làm unique event ID.

### 28.2. Idle stream có thể không có event mới

Khi collection ít writes, lastEventReceivedAt cũ không tự chứng minh consumer chết. Kết hợp cursor health, highwatermark tokens, heartbeat của worker và thông tin oplog. Trên sharded deployment, idle shards có thể làm highwatermark tiến chậm.

### 28.3. Alert theo retention margin

Ví dụ một alert rule:

~~~text
WARN:  estimated history window - consumer lag < 2h
CRIT:  estimated history window - consumer lag < 30m
~~~

Ngưỡng là ví dụ, phải chọn theo worst-case incident repair + catch-up throughput và độ bất định của quan sát lịch sử.

### 28.4. Bảo vệ token và event payload

Token/metadata và raw change events có thể tiết lộ thông tin vận hành hoặc nội dung cá nhân. Giới hạn quyền đọc checkpoint, mã hóa/secrets policy phù hợp và tránh log toàn bộ fullDocument để debug.

## 29. Kiểm thử đơn vị: serialize token không mất BSON shape

Resume token phải được lưu và khôi phục nguyên vẹn. Một test đơn vị có thể chứng minh **Extended JSON round-trip** cho token giả lập:

~~~java
package com.example.changestream;

import static org.assertj.core.api.Assertions.assertThat;

import org.bson.BsonDocument;
import org.bson.BsonString;
import org.junit.jupiter.api.Test;

class ResumeTokenCodecTest {

    @Test
    void tokenCanRoundTripThroughExtendedJson() {
        BsonDocument token = new BsonDocument(
            "_data", new BsonString("opaque-example"));

        String serialized = token.toJson();
        BsonDocument restored =
            BsonDocument.parse(serialized);

        assertThat(restored).isEqualTo(token);
    }
}
~~~

**Chú ý:** token giả chỉ kiểm chứng cách encode/decode, không phải token thật hợp lệ để gọi MongoDB resumeAfter. Integration test cần lấy token thật từ MongoDB.

### 29.1. Hash không thay thế token

SHA-256 của token phù hợp làm inbox key, nhưng **không thể dựng lại resume token** từ hash để mở change stream. Lưu riêng serialized token đủ BSON type information.

### 29.2. Test marker dedupe

Một MongoDB integration test có thể:

1. Insert inbox marker với _id = streamId + ":" + sha256(token).
2. Thử insert cùng marker lần hai.
3. Assert duplicate-key exception và chỉ có một marker.
4. Gọi transactional handler hai lần với cùng event; assert read model, payment counter và outbox không bị lặp.
5. Kiểm tra checkpoint sau lần xử lý hoặc replay đã commit.

Test bước 4–5 mới chứng minh idempotency của **toàn handler**, không chỉ chứng minh unique index.

### 29.3. Failure injection

Trong MongoDB test database, inject exception sau marker insert nhưng trước projection update, và sau projection nhưng trước checkpoint. Assert transaction abort, marker/projection/checkpoint đều không commit, rồi retry event và kiểm tra kết quả cuối chỉ được áp dụng một lần.

## 30. Integration test: nhận token thật rồi resumeAfter

Ví dụ dùng MongoDB Testcontainers replica set và Java Sync Driver thông qua MongoTemplate:

~~~java
package com.example.changestream;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.BsonDocument;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class ChangeStreamResumeIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri",
            mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @Test
    void resumesAfterLastObservedEvent() {
        String collection = "watch_test_"
            + UUID.randomUUID().toString().replace("-", "");
        template.createCollection(collection);

        try {
            BsonDocument token;

            try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                    cursor = template.getCollection(collection)
                        .watch()
                        .maxAwaitTime(500, TimeUnit.MILLISECONDS)
                        .cursor()) {

                template.insert(
                    new Document("_id", new ObjectId())
                        .append("status", "CREATED"),
                    collection);

                ChangeStreamDocument<Document> first =
                    awaitNext(cursor, Duration.ofSeconds(10));

                assertThat(first.getOperationType())
                    .isEqualTo(OperationType.INSERT);
                token = first.getResumeToken();
                assertThat(token).isNotNull();
            }

            try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                    resumed = template.getCollection(collection)
                        .watch()
                        .resumeAfter(token)
                        .maxAwaitTime(500, TimeUnit.MILLISECONDS)
                        .cursor()) {

                template.insert(
                    new Document("_id", new ObjectId())
                        .append("status", "PAID"),
                    collection);

                ChangeStreamDocument<Document> second =
                    awaitNext(resumed, Duration.ofSeconds(10));

                assertThat(second.getOperationType())
                    .isEqualTo(OperationType.INSERT);
                assertThat(second.getFullDocument()
                    .getString("status")).isEqualTo("PAID");
                assertThat(second.getResumeToken())
                    .isNotEqualTo(token);
            }
        } finally {
            template.dropCollection(collection);
        }
    }

    private static ChangeStreamDocument<Document> awaitNext(
            MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor,
            Duration timeout) {

        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            ChangeStreamDocument<Document> event =
                cursor.tryNext();
            if (event != null) {
                return event;
            }
        }
        throw new AssertionError(
            "Timed out waiting for a change event");
    }
}
~~~

### 30.1. Cursor được mở trước khi insert

Change stream chỉ phát sự kiện từ vị trí bắt đầu theo dõi. Nếu insert xảy ra **trước khi watch thực sự được mở**, event có thể bị bỏ lỡ. Trong ví dụ, cursor() ở sync driver khởi tạo watch trước insert.

### 30.2. Cần MongoDB replica set

MongoDBContainer với getReplicaSetUrl cung cấp topology thử nghiệm phù hợp trên Testcontainers versions hỗ trợ. Test cần Docker, Spring Boot test, MongoDB driver. Không chạy trên standalone mongod hoặc production DB.

### 30.3. Đây chưa phải test idempotency

Test này chứng minh token do server tạo và resumeAfter có thể tiếp tục sau event trước. Test transactional inbox/replay ở phần 29 vẫn cần để chứng minh business effect không bị lặp.

### 30.4. Driver tự resume không thay checkpoint

MongoDB drivers có thể tự resume một số resumable errors, nhưng không thay durable checkpoint ứng dụng để khởi chạy lại sau process crash.

## 31. Thử nghiệm invalidate trong môi trường được kiểm soát

Không drop collection production để test. Sử dụng một collection disposable và **hai mongosh sessions** kết nối cùng replica set.

### 31.1. Terminal A: mở watch

~~~javascript
use test_change_streams;

db.watch_orders_test.insertOne({
  _id: "seed",
  status: "CREATED"
});

const stream = db.watch_orders_test.watch();

while (!stream.isClosed()) {
  const event = stream.tryNext();
  if (event !== null) {
    printjson(event);
    if (event.operationType === "invalidate") {
      print("Save the REAL event._id token");
      break;
    }
  }
}
~~~

### 31.2. Terminal B: drop collection test

~~~javascript
use test_change_streams;

// CHỈ thực hiện trên collection test:
db.watch_orders_test.drop();
~~~

Terminal A quan sát các control events có liên quan và một **invalidate** event; collection watch cursor đóng.

### 31.3. So sánh resumeAfter và startAfter

Lưu token thật từ invalidate vào biến invalidateToken. Nếu cố:

~~~javascript
db.watch_orders_test.watch(
  [],
  { resumeAfter: invalidateToken }
);
~~~

thì MongoDB không cho resumeAfter qua invalidate. Để tạo một stream mới sau invalidate:

~~~javascript
db.watch_orders_test.watch(
  [],
  { startAfter: invalidateToken }
);
~~~

startAfter vẫn phụ thuộc history window, namespace/watch scope và collection lifecycle; nó không tự tạo lại dữ liệu đã drop. Một hệ thống thực phải dừng/reconcile hoặc chờ collection được tạo lại theo migration.

### 31.4. State machine test

Sau invalidate, assert consumer:

1. Đổi trạng thái **INVALIDATED**.
2. Giữ token invalidate và nguyên nhân.
3. Dừng apply business events theo namespace cũ.
4. Không retry resumeAfter vô hạn.
5. Báo động nếu việc drop/rename không được phép.
6. Chỉ startAfter/rebuild theo một recovery policy được duyệt.

### 31.5. Scope database watch

Một test riêng dùng db.watch và drop một collection con để kiểm tra **không mặc định invalidate database watch**. Với database-level watch, dropDatabase mới là một trong những trường hợp khiến stream bị invalidate. Không chạy test này trên database được các test khác dùng chung.

## 32. Kiểm thử history loss và crash windows

Không chủ động làm oplog production tràn để tái hiện history loss. Có thể kiểm tra ở các tầng:

| Test | Cách thực hiện | Kết quả mong muốn |
| --- | --- | --- |
| Error classifier | Giả lập ChangeStreamHistoryLost | RECOVERY_REQUIRED |
| Không retry non-resumable | Inject lỗi history lost | RetryWhen từ chối |
| Replay cùng event | Handler nhận cùng token hai lần | Projection/outbox không bị lặp |
| Crash trước effect | Inject exception trước transaction | Checkpoint không tiến |
| Crash giữa effect và checkpoint | Inject exception trong transaction | Marker/effect/token đều rollback |
| Crash sau commit | Replay sau commit | Inbox ngăn effect |
| Two owners | Hai workers cạnh tranh | Unique marker/fencing bảo vệ trạng thái |
| Consumer lag | Làm worker chậm có kiểm soát | Alert trước khi quá oplog window |
| Poison event | Body thiếu field bắt buộc | Pause/quarantine, không silent skip |
| Invalidate | Drop/rename ở namespace test | PAUSED/INVALIDATED |
| Pipeline drift | Đổi pipelineVersion | Không resume bừa từ token cũ |

### 32.1. History loss thật ở dedicated environment

Nếu cần end-to-end test server thật, dùng replica set **disposable**, cấu hình oplog/history window ngắn theo MongoDB version hỗ trợ và tạo đủ writes để entry cũ bị loại. Không chạy trên cluster shared hay production. Số lượng writes cần thiết phụ thuộc sizing/throughput, không hardcode một con số rồi coi luôn đủ.

### 32.2. Kiểm tra retries

Test cần assert số attempts, backoff classification, checkpoint không đổi khi fail, và state chuyển chính xác. Chỉ assert rằng exception đã được catch không chứng minh worker không làm mất event.

### 32.3. Recovery drill

1. Dừng consumer trong môi trường test có writes liên tục.
2. Quan sát lag và retention safety margin.
3. Giả lập hoặc tạo điều kiện history loss ở test cluster.
4. Chuyển trạng thái RECOVERY_REQUIRED.
5. Rebuild projection, đối chiếu snapshot.
6. Xác minh không tạo gap giữa snapshot và stream mới.
7. Bật lại worker và quan sát lag, duplicate count và data parity.

### 32.4. Re-run phải an toàn

Một bài test quan trọng là **rebuild cùng snapshot nhiều lần**. Nếu rebuild lặp làm revenue tăng hoặc notifications gửi lại, workflow khôi phục vẫn chưa idempotent dù change stream handler bình thường đã có inbox.

## 33. Bài tập thực hành

### Bài tập 1: event ID và document ID

Event có:

~~~javascript
{
  _id: { _data: "opaque-token-T1" },
  documentKey: {
    _id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

**Câu hỏi:** Token nào dùng để resume?

**Đáp án:** Dùng **event._id** nguyên vẹn, không dùng documentKey._id.

### Bài tập 2: hai updates cùng Order

E1 chuyển Order O1 sang PAID; E2 chuyển O1 sang REFUNDED. Có được dedupe bằng mỗi orderId=O1 không?

**Đáp án:** Không. Đây là hai events hợp lệ, mỗi event cần marker khác; nếu dedupe ở business level phải dựa vào command/payment/version cụ thể.

### Bài tập 3: sự kiện bị lặp

Consumer đã cập nhật projection nhưng crash trước checkpoint. Sau restart có thể thấy gì?

**Đáp án:** Có thể thấy lại cùng event. Handler phải idempotent bằng unique marker/transaction hoặc thiết kế tương đương.

### Bài tập 4: checkpoint trước effect

Lưu token T200 thành công rồi crash trước khi xử lý E200. Kết quả resumeAfter(T200)?

**Đáp án:** Bắt đầu sau E200, có nguy cơ **mất hiệu ứng của E200**. Không checkpoint trước khi xử lý bền vững.

### Bài tập 5: checkpoint sau effect

Effect đã commit nhưng checkpoint cũ. Vì sao đây là trade-off thường chấp nhận được?

**Đáp án:** Replay có thể xảy ra nhưng xử lý idempotent có thể phát hiện và bỏ effect trùng; còn checkpoint trước có thể làm mất event không hồi phục theo stream bình thường.

### Bài tập 6: atomic inbox

Ba write operations nào nên nằm trong một MongoDB transaction nếu chúng cùng database deployment?

**Đáp án:** **Insert inbox marker, apply projection/outbox và update checkpoint**. Đây là cách đóng transaction gap trong phạm vi MongoDB.

### Bài tập 7: unique index

Hai workers cùng nhìn marker chưa tồn tại rồi cùng insert. Kiểm tra exists trước có ngăn race không?

**Đáp án:** Không. Chỉ unique constraint trên marker ID, transaction conflict handling và owner coordination mới bảo vệ đúng.

### Bài tập 8: business duplicate

E1 token T1, E2 token T2, nhưng cả hai có paymentId=P100. Inbox theo token có ngăn double charge không?

**Đáp án:** Không. Cần **unique business paymentId + idempotency policy** ở payment layer.

### Bài tập 9: không dùng $inc bừa bãi

Một handler nhận event PAYMENT_CAPTURED và gọi $inc(revenue,amount). Điều gì xảy ra nếu event replay?

**Đáp án:** Revenue bị cộng hai lần. Cần idempotent marker cùng transaction hoặc ledger/payment entry unique theo business key rồi tính tổng từ ledger.

### Bài tập 10: invalidate collection

Collection watch đang mở, collection bị drop. Sự kiện gì báo stream không còn hợp lệ?

**Đáp án:** **invalidate**. Cursor đóng; consumer phải chuyển trạng thái và thực hiện recovery policy.

### Bài tập 11: resumeAfter sau invalidate

Có thể gọi resumeAfter(invalidateToken) để tiếp tục như một lỗi network thông thường không?

**Đáp án:** Không. MongoDB không cho resumeAfter đi qua invalidate.

### Bài tập 12: startAfter

startAfter(invalidateToken) có tự khôi phục những documents đã drop không?

**Đáp án:** Không. Nó là lựa chọn mở stream mới sau invalidate nếu còn history; schema/data state phải được xử lý riêng.

### Bài tập 13: watch scope

Drop collection con có chắc làm một database-level watch bị invalidate không?

**Đáp án:** Không. Scope của database-level watch khác collection-level watch; dropDatabase mới là một tình huống invalidate database watch.

### Bài tập 14: retention

Checkpoint được giữ 365 ngày. Oplog chỉ còn 6 giờ lịch sử thực tế. Consumer dừng 48 giờ, resume có chắc thành công?

**Đáp án:** Không. Độ bền checkpoint không kéo dài oplog window; cần recovery khi lịch sử token đã mất.

### Bài tập 15: token đã mất lịch sử

Phản ứng nào nguy hiểm nhất khi nhận ChangeStreamHistoryLost?

**Đáp án:** Xóa token, bắt đầu stream từ hiện tại rồi âm thầm bỏ qua các events đã mất. Cần báo gap và rebuild/reconcile hoặc chấp nhận mất dữ liệu một cách tường minh.

### Bài tập 16: pre-image retention

Đặt expireAfterSeconds của pre/post-images rất lớn có làm oplog giữ event mãi không?

**Đáp án:** Không. Nếu oplog entry đã bị loại thì images tương ứng cũng bị xóa, bất kể retention image dài hơn.

### Bài tập 17: fullDocument updateLookup

E1 update Order status=PAID; E2 ngay sau update thành REFUNDED. fullDocument của E1 có chắc là PAID không?

**Đáp án:** Không. Update lookup có thể nhìn version majority-committed hiện tại, đã bị E2 thay đổi. Dùng updateDescription/business version hoặc pre/post images đúng contract khi cần lịch sử chính xác.

### Bài tập 18: transaction ngoài MongoDB

Handler gửi email trước commit MongoDB. Transaction abort sau email. Email có được rollback?

**Đáp án:** Không. Dùng outbox và downstream idempotency.

### Bài tập 19: flatMap

E1(version 5) chạy chậm, E2(version 6) chạy nhanh, cả hai được flatMap concurrency=32. Có rủi ro gì?

**Đáp án:** E2 có thể commit trước E1; E1 ghi đè state mới. Dùng concatMap hoặc partition/per-key ordering và checkpoint barrier.

### Bài tập 20: Reactive retry

Worker tạo options từ token lúc startup rồi chỉ gọi retryWhen trên cùng Flux. Vì sao có thể replay quá nhiều?

**Đáp án:** Retry có thể mở lại từ token cũ. Dùng **Flux.defer + load durable checkpoint** khi tái đăng ký stream.

### Bài tập 21: reactive transaction

Một Flux change stream chạy liên tục trong nhiều ngày. Có nên bao toàn bộ Flux trong một MongoDB transaction?

**Đáp án:** Không. Transaction phải ngắn cho từng event/batch nhỏ; không giữ session/snapshot lâu qua một stream vô hạn.

### Bài tập 22: poison event

Một event có schema không phù hợp khiến handler luôn ném IllegalArgumentException. Có nên onErrorResume rồi checkpoint qua event?

**Đáp án:** Không tự động. Cần policy pause/quarantine/recovery. Nếu đưa vào DLQ rồi skip, phải xác nhận DLQ đã nhận dữ liệu bền vững và có quy trình replay.

### Bài tập 23: highwatermark

Consumer không nhận change event mới trong vài giờ. Có thể mặc định stream chết không?

**Đáp án:** Không. Stream có thể idle. Quan sát cursor health, worker heartbeat và postBatchResumeToken/highwatermark nếu API dùng được.

### Bài tập 24: retention margin

Oplog window H=8 giờ, consumer lag L=5 giờ, dự kiến xử lý incident và catch-up R=4 giờ. Margin M?

**Đáp án:** M=8-(5+4)=-1 giờ. Có nguy cơ không kịp resume; cần tăng history window/throughput và xử lý ngay, không chỉ restart.

### Bài tập 25: multiple owners

Worker A checkpoint T200, worker B xử lý chậm checkpoint T150. Có thể so sánh JSON tokens theo chuỗi để biết cái nào mới hơn không?

**Đáp án:** Không. Token opaque; dùng lease/fencing, exclusive ownership và thứ tự commit được kiểm soát.

### Bài tập 26: integration test

Unit test encode/decode token giả thành công. Đã đủ chứng minh resumeAfter trên MongoDB thật hoạt động chưa?

**Đáp án:** Chưa. Cần replica set integration test, mở stream, ghi change thật, lấy token thật, đóng rồi mở lại với resumeAfter và xác minh event tiếp theo.

### Bài tập 27: outbox

Một notification đã gửi thành công nhưng worker timeout. Outbox có ngăn gửi lại tuyệt đối không?

**Đáp án:** Không nếu downstream không có idempotency contract. Outbox đảm bảo durable command, còn exactly-once side effect bên ngoài cần downstream dedupe/chấp nhận trade-off.

### Bài tập 28: rebuild

Read model được xây lại bằng snapshot mất 30 phút, rồi mở watch từ hiện tại. Vấn đề?

**Đáp án:** Có thể bỏ lỡ updates trong 30 phút. Recovery phải có stream position/snapshot cut và replay buffer hoặc chiến lược đồng bộ phù hợp.

## 34. Checklist trước khi triển khai production

- **Topology:** MongoDB deployment là replica set/sharded cluster hỗ trợ change streams chưa?
- **Permissions:** tài khoản watcher có đủ quyền đúng watch scope chưa?
- **Namespace:** collection/database/deployment scope đã được chọn và document rõ chưa?
- **Pipeline version:** options, filters và version pipeline được lưu cùng checkpoint chưa?
- **Control events:** handler không bỏ qua invalidate/DDL mà chưa có policy chưa?
- **Resume token:** lưu BSON token nguyên vẹn, không lưu mỗi documentKey hoặc clusterTime chưa?
- **Serialization:** token JSON/BSON có round-trip giữ nguyên types chưa?
- **Checkpoint semantics:** token là **last durably processed**, không phải last received chưa?
- **Ordering:** đã bảo đảm xử lý tuần tự hoặc có version + contiguous checkpoint barrier chưa?
- **Single owner:** có lease/fencing cho nhiều instances chung một checkpoint chưa?
- **Crash windows:** đã inject lỗi trước/sau effect/checkpoint để xác minh không mất dữ liệu chưa?
- **Inbox:** event identity unique theo stream + token chưa?
- **Business keys:** paymentId/operationId có unique index và policy rõ chưa?
- **Atomic effect:** marker, projection, outbox, checkpoint cùng MongoDB transaction khi cần chưa?
- **Outbox:** side effects ngoài MongoDB không chạy trực tiếp trước commit chưa?
- **Downstream dedupe:** có idempotency key hoặc document rõ nguy cơ duplicate chưa?
- **Marker retention:** dedupe state còn lâu hơn replay/rebuild horizon chưa?
- **Reprocessing:** cùng event được apply nhiều lần không làm sai read model/revenue chưa?
- **Version:** event cũ không ghi đè state mới khi concurrency thay đổi chưa?
- **Invalidate:** có trạng thái INVALIDATED và token invalidate riêng chưa?
- **startAfter:** chỉ dùng sau recovery quyết định và khi history còn phù hợp chưa?
- **resumeAfter:** không dùng trực tiếp qua invalidate chưa?
- **History loss:** có trạng thái RECOVERY_REQUIRED và runbook rebuild thay vì silent skip chưa?
- **Initial sync:** snapshot + change stream có kế hoạch tránh gap chưa?
- **Oplog:** đo history window thực tế và thiết kế downtime/catch-up margin chưa?
- **Pre/post-images:** không nhầm image retention với oplog retention chưa?
- **FullDocument:** không coi updateLookup là snapshot chính xác tại event chưa?
- **Retries:** phân loại resumable/non-resumable, có backoff/jitter và giới hạn chưa?
- **Poison event:** có quarantine/DLQ hoặc pause không mất dữ liệu chưa?
- **Reactive:** ứng dụng dùng concatMap, không block hoặc tự subscribe ngoài lifecycle chưa?
- **Reactive retry:** nạp lại checkpoint mỗi lần subscription/retry chưa?
- **Reactive transaction:** dùng ReactiveMongoTransactionManager và một Reactor chain chưa?
- **Sync listener:** MessageListenerContainer có error handler và shutdown đúng chưa?
- **Monitoring:** có lag, oplog window, checkpoint age, duplicate count, invalidation, history lost chưa?
- **Security:** không log fullDocument/PII và bảo vệ checkpoint/outbox chưa?
- **Testing:** có MongoDB replica set integration tests và Testcontainers phù hợp chưa?
- **Operations:** đã diễn tập shutdown, failover, invalidate và history loss chưa?

## 35. Tổng kết

1. **Change streams không tự bảo đảm exactly-once business effects**. Ứng dụng cần an toàn với replay/duplicate deliveries trong cơ chế processing của mình.
2. **Event._id là resume token**, khác với documentKey._id; không thay token bằng document ID hoặc clusterTime.
3. **Checkpoint sau khi effect bền vững** tránh nguy cơ bỏ qua event chưa xử lý; việc replay sau crash phải được idempotent handler hấp thụ.
4. **Inbox marker với unique key** theo streamId + event token là một công cụ chống replay, nhưng không thay business idempotency theo paymentId/operationId.
5. **MongoDB transaction** có thể commit atomic inbox + read model + outbox + checkpoint khi cùng deployment/session; không bao gồm side effects ngoài MongoDB.
6. **Outbox** tách việc phát email/broker ra khỏi transaction; downstream idempotency vẫn cần để hạn chế duplicate từ timeout/retry.
7. **$inc, append và external calls không idempotent** nếu xử lý lại thiếu unique guards.
8. **Đúng một lần không có nghĩa đúng thứ tự**; cần concatMap, partition ordering hoặc version guard và contiguous checkpoint.
9. **Invalidate** xuất hiện ở một số sự kiện DDL theo watch scope và đóng cursor. Nó khác lỗi mạng tạm thời.
10. **resumeAfter không được dùng sau invalidate**; **startAfter** có thể mở stream mới sau invalidate khi lịch sử vẫn còn và recovery policy cho phép.
11. **startAfter không tái tạo dữ liệu bị drop**, không khắc phục tự động pipeline drift và không vượt qua oplog retention.
12. **Checkpoint tồn tại lâu không có nghĩa oplog còn lâu**. Nếu history đã mất, phải rebuild/reconcile hoặc ghi nhận rõ quyết định chấp nhận data gap.
13. **Pre/post-image retention khác oplog retention**; khi oplog event tương ứng bị loại, image cũng không còn.
14. **fullDocument updateLookup** có thể trả trạng thái hiện tại đã đổi so với update event; cần chọn nguồn dữ liệu đúng semantics.
15. **Spring Data ReactiveMongoTemplate** cung cấp Flux<ChangeStreamEvent<T>> và ChangeStreamOptions resumeAfter/startAfter; durable checkpoint phải được load lại khi retry.
16. **Reactive transaction context** khác imperative thread-bound transaction, nên không trộn blocking MongoTemplate vào reactive chain rồi mặc định atomic.
17. **MessageListenerContainer** là lựa chọn sync nhưng cần lifecycle, error handler, ownership và processing semantics rõ ràng.
18. **Observability phải theo consumer lag và oplog safety margin**, không chỉ health status của process.
19. **Integration tests phải chạy với replica set**, token thật và fault injection để xác minh resume, invalidate, duplicate handling và recovery.
20. **Recovery phải tránh một khoảng hở mới giữa snapshot và stream**; đó là trách nhiệm thiết kế dữ liệu chứ không được một option resume đơn lẻ giải quyết.

Với chủ đề **Sự kiện lặp, invalidate, retention và xử lý idempotent**, dịch vụ **SPRING_DATA_MONGODB** chỉ đáng tin cậy khi kết hợp đúng semantics của MongoDB change streams, checkpoint bền vững, idempotency ở tầng sự kiện và nghiệp vụ, transaction có phạm vi rõ cùng một runbook phục hồi khi lịch sử không còn.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — scope, resume tokens, resumeAfter, startAfter, highwatermark, oplog history.
- [MongoDB Manual — Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/) — event._id, documentKey, operationType và event metadata.
- [MongoDB Manual — Invalidate Event](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/) — khi nào stream bị invalidate và tác động lên cursor.
- [MongoDB Manual — db.collection.watch](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/) — resume options, fullDocument lookup và cursor lifecycle.
- [MongoDB Manual — Change Streams Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — vận hành, stream size và history considerations.
- [MongoDB Manual — changeStreamOptions](https://www.mongodb.com/docs/manual/reference/cluster-parameters/changestreamoptions/) — retention của pre/post-images.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — lịch sử oplog và retention.
- [Spring Data MongoDB — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html) — ReactiveMongoTemplate, MessageListenerContainer, resume support.
- [Spring Data MongoDB — ChangeStreamOptions Builder API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.ChangeStreamOptionsBuilder.html) — resumeAfter/startAfter và fullDocument.
- [Spring Data MongoDB — ChangeStreamEvent API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamEvent.html) — getResumeToken, getBody, getRaw, getOperationType.
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager, ReactiveMongoTransactionManager và context.
- [MongoDB Java Sync Driver — Open Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — ChangeStreamIterable, MongoChangeStreamCursor và resume.
