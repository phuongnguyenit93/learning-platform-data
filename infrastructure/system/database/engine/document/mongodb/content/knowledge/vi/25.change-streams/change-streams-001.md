# Mục tiêu theo dõi thay đổi và điều kiện triển khai Change Streams trong MongoDB

## 1. Vì sao ứng dụng cần biết dữ liệu vừa thay đổi?

Trong nhiều ứng dụng, một thao tác ghi MongoDB không phải điểm kết thúc của nghiệp vụ. Khi đơn hàng được cập nhật, các thành phần khác có thể cần biết để thực hiện công việc tiếp theo:

- Gửi thông báo khi trạng thái đơn hàng đổi thành **SHIPPED**.
- Làm mới cache khi thông tin sản phẩm thay đổi.
- Đồng bộ một phần dữ liệu sang hệ thống tìm kiếm.
- Cập nhật bảng tổng hợp hoặc materialized view.
- Đẩy thay đổi sang dịch vụ báo cáo, giám sát hoặc ETL.
- Hiển thị danh sách thay đổi gần thời gian thực cho ứng dụng cộng tác.

Ví dụ trong collection **orders**:

~~~javascript
{
  _id: "ORD-100",
  tenantId: "SHOP-A",
  customerId: "CUS-01",
  status: "PENDING",
  totalCents: NumberLong(350000)
}
~~~

Khi ứng dụng chạy:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-100", tenantId: "SHOP-A" },
  { $set: { status: "PAID" } }
);
~~~

một dịch vụ khác muốn nhận tín hiệu:

~~~text
Đơn ORD-100 đã được cập nhật
Field status: "PAID"
Collection: orders
Operation: update
~~~

Nếu không có cơ chế theo dõi thay đổi, dịch vụ tiêu thụ phải liên tục truy vấn database:

~~~text
Mỗi vài giây:
  QUERY orders WHERE updatedAt > lastCheck
  -> xử lý kết quả
  -> ngủ
  -> lặp lại
~~~

Cách **polling** này vừa tạo tải truy vấn định kỳ vừa dễ xử lý sai nếu timestamp trùng, thiếu index, thay đổi diễn ra giữa các lần đọc hoặc document bị xóa.

**MongoDB Change Streams** cho phép ứng dụng **đăng ký nhận sự kiện thay đổi dữ liệu** trên collection, database hoặc toàn deployment, mà không phải tự đọc trực tiếp và giải mã oplog. Đây là một cơ chế **change data capture (CDC)** tích hợp trong MongoDB.

Mục tiêu của bài này là hiểu **để làm gì, yêu cầu hạ tầng nào, cách kiểm tra khả năng sử dụng và các giới hạn cần chuẩn bị trước khi triển khai**.

## 2. Mục tiêu của Change Streams

Change Streams giải quyết bài toán **phát hiện thay đổi đã diễn ra trong MongoDB và chuyển thông tin đó đến consumer** gần thời gian thực.

Các khả năng chính:

1. **Theo dõi sự kiện ghi** như insert, update, replace và delete.
2. **Giới hạn phạm vi theo dõi** từ một collection đến database hoặc deployment.
3. **Lọc sự kiện** bằng các stages tương ứng của aggregation pipeline.
4. **Nhận metadata**: loại thao tác, định danh document, namespace, thời điểm logic, mô tả các field thay đổi.
5. **Tiếp tục sau khi kết nối gián đoạn** thông qua resume token khi lịch sử oplog vẫn còn phù hợp.
6. **Kết hợp với kiến trúc event-driven** để kích hoạt đồng bộ, lập chỉ mục, thông báo và báo cáo.

Change Streams là luồng sự kiện về **những thao tác đã ghi vào MongoDB**, không phải lời gọi tự động cho mọi sự kiện nghiệp vụ.

~~~text
User xác nhận thanh toán
          |
          v
Backend xác minh payment provider
          |
          v
MongoDB cập nhật order.status = PAID
          |
          v
Change Stream phát event update
          |
          v
Consumer nhận event và cập nhật cache/báo cáo
~~~

Consumer biết có sự kiện cập nhật field status, nhưng chỉ nhìn từ database change **không tự chứng minh provider đã thực sự thu tiền**. Business service vẫn phải bảo đảm quy tắc thanh toán, bảo mật và idempotency.

### 2.1. Những mục tiêu phù hợp

| Nhu cầu | Cách Change Streams hỗ trợ |
|---|---|
| Đồng bộ tìm kiếm | Khi sản phẩm thay đổi, consumer cập nhật index ngoài MongoDB. |
| Cache invalidation | Khi một field liên quan đổi, xóa hoặc cập nhật key cache. |
| Realtime UI | Backend đẩy event qua WebSocket/SSE cho user được phép. |
| Audit hỗ trợ vận hành | Ghi nhận metadata thay đổi cho hệ thống quan sát. |
| Materialized view | Cập nhật dữ liệu tổng hợp dựa trên writes nguồn. |
| ETL/CDC | Chuyển delta sang data pipeline khác. |
| Tích hợp microservices | Phản ứng với thay đổi bền vững trong database. |

### 2.2. Những điều Change Streams không tự bảo đảm

Change Streams **không phải**:

- Một message broker đa nguồn thay thế Kafka/RabbitMQ trong mọi trường hợp.
- Lịch sử audit vĩnh viễn với khả năng replay vô hạn.
- Cơ chế exactly-once end-to-end cho email, cache, Elasticsearch hay HTTP APIs.
- Bản snapshot đầy đủ của mọi document từ trước thời điểm mở stream.
- Một transaction xuyên MongoDB và hệ thống bên ngoài.
- Một thay thế cho authorization, schema validation hoặc business rules.
- Một công cụ dự đoán thay đổi **trước khi write được commit**.

Kiến trúc đúng thường kết hợp Change Streams với **idempotent consumers, checkpoint, monitoring, reconciliation** và đôi khi **transactional outbox**.

## 3. Change Streams khác polling và tự đọc oplog như thế nào?

### 3.1. Polling theo updatedAt

~~~javascript
db.orders.find({
  updatedAt: { $gt: lastCheckedAt }
});
~~~

Ưu điểm: đơn giản khi collection có index phù hợp; hoạt động trên standalone MongoDB; ứng dụng kiểm soát chu kỳ. Hạn chế: query lặp ngay cả lúc không có writes; độ trễ theo interval; delete không còn document để đọc; mọi write path phải cập nhật timestamp; cần phân trang và xử lý timestamp trùng.

### 3.2. Tự tail oplog

Oplog là nhật ký thao tác của replica set. Việc tự đọc trực tiếp oplog đòi hỏi hiểu format nội bộ, topology, transaction semantics và xử lý resume/failover; các chi tiết có thể thay đổi giữa các phiên bản.

Change Streams cung cấp API ở mức cao hơn:

~~~javascript
const stream = db.orders.watch();
~~~

Thay vì consumer phải giải mã raw oplog entries, MongoDB trả **change event documents** theo schema Change Streams.

### 3.3. So sánh

| Tiêu chí | Polling | Tự tail oplog | Change Streams |
|---|---|---|---|
| Cần replica set/sharded cluster | Không nhất thiết. | Có oplog mới dùng được. | **Có**, không hỗ trợ standalone. |
| Phát hiện delete | Cần soft delete/tombstone. | Có thể, nhưng phức tạp. | Có sự kiện delete. |
| Gần thời gian thực | Theo interval. | Có. | Có, sau khi đủ điều kiện phát event. |
| API chuyên dụng | Query thông thường. | Phụ thuộc oplog. | **watch() / ChangeStream**. |
| Resume sau ngắt kết nối | Tự quản lý checkpoint. | Tự quản lý nhiều logic. | Resume token được cung cấp. |
| Lưu lịch sử | Tùy thiết kế. | Oplog window. | **Oplog window**. |
| Exactly-once downstream | Tự thiết kế. | Tự thiết kế. | **Vẫn phải tự thiết kế**. |

**Change Streams phù hợp** khi nguồn thay đổi là MongoDB, cần xử lý theo delta, deployment là replica set hoặc sharded cluster và thời gian downtime nằm trong khoảng có thể resume.

**Polling** có thể phù hợp nếu chỉ cần batch đơn giản hoặc standalone.

**Message broker/outbox** thường phù hợp khi cần contract domain events rõ ràng, retention dài, nhiều consumer groups hoặc phát sinh sự kiện từ nhiều hệ thống.

## 4. Change Streams hoạt động ở mức khái niệm

Luồng đơn giản với replica set:

~~~text
                  MongoDB Replica Set
  +----------------------------------------------+
  |  Primary                                     |
  |    |                                         |
  |    +-- ghi vào data                          |
  |    +-- replication log (oplog)              |
  |                |                             |
  |                +----> Secondary A            |
  |                +----> Secondary B            |
  |                                              |
  |      majority-committed change              |
  |                |                             |
  +----------------|-----------------------------+
                   |
                   v
        Change Stream watch() cursor
                   |
                   v
         Change event {operationType,...}
                   |
                   v
            Application consumer
~~~

MongoDB phát notification khi thay đổi đã **được majority commit trên data-bearing members**. Nó không phát ngay mọi thao tác mới áp dụng cục bộ trên primary nhưng chưa majority committed.

### 4.1. Majority committed không có nghĩa mọi consumer nhận tức thì

Sự kiện phải đi qua replication, cursor/getMore, network và consumer. Có **độ trễ đầu-cuối**:

~~~text
Write
  -> majority commit
  -> server tạo change event
  -> cursor/getMore
  -> application xử lý
  -> downstream xác nhận
~~~

Change Streams là **near-real-time**, không phải real-time cứng có deadline cố định.

### 4.2. Phân biệt write acknowledgement và lúc event đến

Ghi với **w:1** có thể nhận response trước majority commit. Change Stream chưa nhất thiết phát event ở thời điểm đó.

Ghi với **w:"majority"** được xác nhận sau khi đạt majority write concern, nhưng event vẫn phải được cursor truyền tới consumer. Không dùng lúc event đến để suy ra chính xác thời điểm client ghi nhận kết quả write.

### 4.3. Change Stream không tự đồng bộ dữ liệu bên ngoài

~~~text
MongoDB change event
        |
        v
Consumer processEvent()
        |
        +-- update cache
        +-- index search
        +-- publish message
~~~

Đây là hành vi ứng dụng do lập trình viên viết. Nếu consumer lỗi, Change Stream không tự rollback document nguồn.

## 5. Ba phạm vi theo dõi thay đổi

### 5.1. Collection-level: db.collection.watch()

~~~javascript
const stream = db.orders.watch();
~~~

Chỉ nhận những sự kiện liên quan collection orders. Phù hợp khi một service chỉ quan tâm đơn hàng, cần giới hạn quyền và giảm complexity.

### 5.2. Database-level: db.watch()

~~~javascript
const stream = db.watch();
~~~

Nhận sự kiện từ **các non-system collections trong database hiện tại**. Trường **ns.db** và **ns.coll** cho phép định tuyến sự kiện theo nguồn.

### 5.3. Deployment-level: Mongo.watch()

Trong mongosh:

~~~javascript
const stream = db.getMongo().watch();
~~~

Theo dõi **các non-system collections trên deployment** theo các giới hạn của MongoDB. Scope này cần quyền rộng và có thể tạo tải nhiều hơn.

### 5.4. Bảng chọn scope

| Scope | Lệnh mongosh | Điểm cần cân nhắc |
|---|---|---|
| Collection | **db.orders.watch()** | Ít sự kiện hơn, cấp quyền hẹp. |
| Database | **db.watch()** | Có nhiều schema, cần quyền toàn database. |
| Deployment | **db.getMongo().watch()** | Quyền lớn, cần governance và router. |

**Nên chọn phạm vi nhỏ nhất thỏa yêu cầu**, không watch toàn deployment mặc định cho một service chỉ cần orders.

### 5.5. Giới hạn namespace

Tài liệu MongoDB loại trừ **system collections** và collections thuộc database hệ thống như **admin, local, config** khỏi các scope thông thường của Change Streams. Không xem database watch là công cụ nhận mọi thay đổi nội bộ của MongoDB.

## 6. Điều kiện tiên quyết về topology

### 6.1. Bắt buộc replica set hoặc sharded cluster

**MongoDB standalone không hỗ trợ Change Streams** vì tính năng dựa trên **replica set oplog** để tạo và resume sự kiện.

~~~text
✅ Single-node replica set cho local development
✅ Replica set nhiều thành viên
✅ Sharded cluster có shards theo replica set
✅ Managed MongoDB deployment hỗ trợ change streams

❌ MongoDB standalone thuần túy
❌ Một process mongod không cấu hình replica set
~~~

Single-node replica set **đủ thử cú pháp và consumer local**, nhưng **không mô phỏng đầy đủ** majority durability, failover hoặc secondary lag.

### 6.2. WiredTiger và replica set protocol

MongoDB yêu cầu replica sets/sharded clusters sử dụng **WiredTiger storage engine** và **replica set protocol version 1 (pv1)** cho Change Streams.

Trong MongoDB hiện đại, WiredTiger và pv1 thường thông dụng, nhưng vẫn cần kiểm tra server/topology thực tế trước triển khai.

### 6.3. Có cần bật read concern majority riêng không?

Theo tài liệu MongoDB, **Change Streams khả dụng dù hỗ trợ read concern majority ở cấp deployment được bật hoặc tắt**, nhưng event vẫn chỉ được thông báo khi thay đổi đã majority committed.

Do đó, không nên sử dụng điều kiện lỗi thời kiểu “phải bật cấu hình readConcern majority thì Change Streams mới chạy” như một quy tắc tổng quát trên mọi phiên bản.

### 6.4. Sharded cluster phải kết nối qua mongos

Với replica set, mở Change Stream từ **data-bearing member** theo read preference/driver.

Với sharded cluster, mở stream thông qua **mongos** để MongoDB xử lý events từ các shards.

~~~text
Client/Consumer
      |
      v
    mongos
     / \
    v   v
 Shard A  Shard B
    |       |
    +-- MongoDB sắp xếp/lọc event --+
                                     |
                                     v
                                  Consumer
~~~

Đừng tự tail từng shard rồi tự ghép theo một timestamp đơn giản nếu cần semantics của một sharded Change Stream.

### 6.5. Kiểm tra topology

Trong mongosh:

~~~javascript
db.hello();
~~~

Gợi ý:

- Trường **setName** thường cho biết tên replica set.
- Trường **msg:"isdbgrid"** là dấu hiệu mongos.
- Standalone không có replica set name và không phải mongos.

Không suy topology chỉ từ hostname hay số lượng kết nối của URI.

### 6.6. Local development: single-node replica set

Ví dụ **chỉ trên máy thử nghiệm không chứa dữ liệu thật**:

~~~bash
# Đường dẫn dbpath phải trỏ tới folder dữ liệu có thật.
mongod --dbpath ./mongo-data --replSet rs0 --bind_ip 127.0.0.1 --port 27017
~~~

Mở mongosh ở terminal khác:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "127.0.0.1:27017" }
  ]
});

rs.status();
~~~

Đợi node trở thành PRIMARY rồi kết nối bằng URI local tương ứng:

~~~text
mongodb://127.0.0.1:27017/?replicaSet=rs0
~~~

**Không chạy các lệnh chuyển topology này trực tiếp trên MongoDB production đang hoạt động.** Việc cấu hình replica set thật cần backup, bảo mật/authentication, hostname/network, triển khai rolling phù hợp và driver URI.

### 6.7. MongoDB Atlas và managed deployments

Khi dùng managed cluster, xác nhận loại deployment/tier hỗ trợ Change Streams, URI, TLS, network allowlist, RBAC, oplog retention và connection pool. Không mặc định mọi managed tier/serverless option có cùng hành vi; cần đối chiếu tài liệu provider và phiên bản đang dùng.

## 7. Điều kiện về phiên bản MongoDB và driver

Change Streams xuất hiện từ **MongoDB 3.6** trên replica sets và được mở rộng cho sharded deployments. Một số tính năng bổ sung yêu cầu phiên bản server mới hơn:

| Khả năng | Mốc phiên bản | Ghi chú |
|---|---|---|
| Change Streams trên replica set | **MongoDB 3.6** | API theo dõi thay đổi ban đầu. |
| Hỗ trợ sharded/deployment scope | **MongoDB 4.0** | Cần kết nối qua mongos. |
| Từ chối pipeline làm thay đổi event _id | **MongoDB 4.2+** | Event _id là resume token. |
| Cải tiến hiệu năng một số stages | **MongoDB 5.1+** | Không loại bỏ chi phí cursor/getMore. |
| Document pre- và post-images | **MongoDB 6.0+** | Cần bật tính năng ở collection khi dùng. |
| Split large change stream events | **MongoDB 7.0+** | Dành cho sự kiện lớn đặc biệt. |

Các mốc trên giúp định hướng; **đừng copy API từ tài liệu phiên bản mới vào một server cũ mà không kiểm tra compatibility**. Java Driver, Spring Data MongoDB, MongoDB server và Stable API settings đều cần được phối hợp đúng phiên bản.

### 7.1. Time series collections

Theo tài liệu MongoDB Change Streams hiện tại, **time series collections không hỗ trợ Change Streams** vì định dạng lưu trữ đặc thù không theo dõi thay đổi trực tiếp ở cấp document như collection bình thường.

Nếu cần phát event cho phép ghi dữ liệu time-series, có thể dùng domain event/outbox trên collection thường hoặc thiết kế pipeline ingest riêng.

### 7.2. Views và collections hệ thống

Views không có oplog các writes độc lập như một collection vật lý. Không giả định watch trên view hoạt động như watch trên collection nguồn. System collections và các database admin/local/config có giới hạn theo API.

### 7.3. Stable API

Change Streams thuộc MongoDB **Stable API V1**; một số tùy chọn mở rộng như **showExpandedEvents** không thuộc Stable API V1. Khi dùng **apiStrict**, cần kiểm tra tính năng cụ thể trong API version được chọn.

## 8. Quyền truy cập và bảo mật

Trong deployment bật authorization, MongoDB yêu cầu hai actions:

- **find**
- **changeStream**

Phạm vi của chúng phải tương ứng với scope đang watch.

### 8.1. Collection-level privilege

Để watch **appdb.orders**:

~~~javascript
{
  resource: {
    db: "appdb",
    collection: "orders"
  },
  actions: [
    "find",
    "changeStream"
  ]
}
~~~

Ví dụ tạo custom role nếu có quyền quản trị:

~~~javascript
use appdb

db.createRole({
  role: "ordersChangeReader",
  privileges: [
    {
      resource: {
        db: "appdb",
        collection: "orders"
      },
      actions: ["find", "changeStream"]
    }
  ],
  roles: []
});
~~~

Sau đó quản trị viên có thể gán role này cho service account thích hợp. Không nhúng password trong mã nguồn.

### 8.2. Database-level privilege

Watch database yêu cầu **find + changeStream** trên các non-system collections của database:

~~~javascript
{
  resource: {
    db: "appdb",
    collection: ""
  },
  actions: ["find", "changeStream"]
}
~~~

### 8.3. Deployment-level privilege

Watch toàn deployment yêu cầu quyền tương ứng với các non-system collections của mọi database:

~~~javascript
{
  resource: {
    db: "",
    collection: ""
  },
  actions: ["find", "changeStream"]
}
~~~

Đây là quyền rất rộng; chỉ cấp cho hạ tầng CDC cần thiết và có governance phù hợp.

### 8.4. Bảo vệ dữ liệu sau khi nhận event

Change events có thể chứa customer identifiers, địa chỉ, payload nghiệp vụ, hoặc toàn bộ document khi bật fullDocument/pre-images. Cần:

1. Xác thực service identity và chỉ cấp namespace tối thiểu.
2. Dùng TLS, secret manager và rotate credentials.
3. Không log toàn bộ document chứa dữ liệu nhạy cảm.
4. Kiểm tra tenant/authorization **trước khi đẩy event ra WebSocket/SSE cho user cuối**.
5. Áp dụng chính sách retention cho checkpoints, logs, pre-images và downstream stores.
6. Giám sát lỗi authorization rõ ràng thay vì retry vô hạn.

**Change Streams không tự thực thi quyền truy cập của từng người dùng cuối khi backend chuyển tiếp dữ liệu.**

## 9. Thực hành Change Stream đầu tiên trong mongosh

Điều kiện: đã kết nối **replica set hoặc sharded cluster hỗ trợ Change Streams**, có quyền cần thiết. Dùng database thử nghiệm:

~~~javascript
use change_stream_lab
db.createCollection("orders");
~~~

Chỉ chạy **db.createCollection** một lần; nếu đã có collection, bỏ qua bước tạo.

### 9.1. Terminal A: mở stream trước

~~~javascript
use change_stream_lab

const stream = db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: [
            "insert",
            "update",
            "replace",
            "delete"
          ]
        }
      }
    }
  ],
  {
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  }
);

while (stream.hasNext()) {
  const event = stream.next();
  printjson(event);
}
~~~

**Lệnh hasNext/next chờ sự kiện**, nên terminal A có thể nhìn như đang đứng yên. Đây là hành vi bình thường của cursor dài hạn. Dừng bằng cách ngắt vòng xử lý/cursor phù hợp; với ứng dụng cần dùng **close()** khi shutdown.

### 9.2. Terminal B: tạo thay đổi để thử

Mở một mongosh **kết nối tới cùng MongoDB deployment/database**:

~~~javascript
use change_stream_lab

db.orders.insertOne({
  _id: "ORD-001",
  tenantId: "SHOP-A",
  status: "PENDING",
  totalCents: NumberLong(250000)
});

db.orders.updateOne(
  { _id: "ORD-001" },
  {
    $set: {
      status: "PAID"
    }
  }
);

db.orders.replaceOne(
  { _id: "ORD-001" },
  {
    _id: "ORD-001",
    tenantId: "SHOP-A",
    status: "PACKING",
    totalCents: NumberLong(250000)
  }
);

db.orders.deleteOne({ _id: "ORD-001" });
~~~

Terminal A sẽ nhận các events tương ứng nếu stream đang chạy và kết nối/replication bình thường.

**Lưu ý về thử nghiệm:** nếu chạy đoạn này lần nữa trên dữ liệu khác trạng thái, kết quả có thể khác. Phải mở stream **trước khi thực hiện writes** nếu muốn thấy các writes mới qua cách theo dõi mặc định.

### 9.3. Không có terminal B thì terminal A làm gì?

Change Stream cursor có thể chờ và gửi getMore để lấy events. **Không có document mới** không phải tình huống lỗi. Một client production nên có cơ chế shutdown, timeout, heartbeat/monitoring thích hợp.

### 9.4. Không tự tạo change stream từ một thao tác đọc

~~~javascript
db.orders.find({ status: "PAID" });
~~~

Một query **find** không tạo insert/update/delete event tương ứng. Change Streams theo dõi **thay đổi dữ liệu**, không phải mọi hoạt động đọc của người dùng.

### 9.5. Watch không phải query snapshot hiện có

Nếu trước khi mở stream collection đã có 100.000 orders, gọi **watch()** không tự gửi 100.000 insert events tương ứng. Muốn có **initial state + subsequent changes**, phải thiết kế quy trình bootstrap và đồng bộ delta có checkpoint để tránh thiếu/trùng.

## 10. Cấu trúc của một Change Stream event

Một ví dụ **insert event** rút gọn (giá trị token/timestamp minh họa):

~~~javascript
{
  _id: {
    _data: "<opaque-resume-token>"
  },
  operationType: "insert",
  clusterTime: Timestamp(1, 1),
  ns: {
    db: "change_stream_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-001"
  },
  fullDocument: {
    _id: "ORD-001",
    tenantId: "SHOP-A",
    status: "PENDING",
    totalCents: NumberLong(250000)
  }
}
~~~

**Đây không phải token thật để resume**; token được MongoDB sinh và có định dạng nội bộ. Không tự chế token bằng cách ghép timestamp hoặc _id của document.

### 10.1. Trường quan trọng

| Field | Ý nghĩa |
|---|---|
| **_id** | **Resume token của change event**, không phải _id của order. |
| **operationType** | Loại thao tác: insert, update, replace, delete... |
| **ns.db / ns.coll** | Database và collection của sự kiện. |
| **documentKey** | Định danh document bị thay đổi; trong sharded collection có thể gồm thông tin shard key. |
| **clusterTime** | Timestamp logic của thay đổi; không đồng nghĩa wall-clock timestamp chính xác cho business SLA. |
| **fullDocument** | Document đầy đủ ở một số event/option. |
| **updateDescription** | Mô tả các field được cập nhật/xóa trong update event. |
| **lsid / txnNumber** | Có thể xuất hiện với các operations liên quan transaction. |

### 10.2. Update event

Ví dụ:

~~~javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "update",
  ns: {
    db: "change_stream_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-001"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
~~~

**Mặc định update event thiên về delta**, không phải lúc nào cũng mang nguyên document sau update. Nếu consumer cần nhiều field còn lại, phải chọn chiến lược fullDocument hoặc tự truy vấn.

### 10.3. Replace event

~~~javascript
{
  operationType: "replace",
  documentKey: { _id: "ORD-001" },
  fullDocument: {
    _id: "ORD-001",
    tenantId: "SHOP-A",
    status: "PACKING",
    totalCents: NumberLong(250000)
  }
}
~~~

Một **replace** khác **update**: nó thay thế document được match (ngoại trừ quy tắc _id), nên thông tin event có thể là fullDocument thay vì một delta theo từng field.

### 10.4. Delete event

~~~javascript
{
  operationType: "delete",
  documentKey: {
    _id: "ORD-001"
  }
}
~~~

Sau delete, document không còn ở collection. **fullDocument sau delete không có để lookup**. Nếu cần nội dung trước xóa, xem pre-images hoặc thiết kế soft-delete/audit tương ứng.

### 10.5. Không nhầm hai _id

~~~text
changeEvent._id
  -> Resume token
  -> Dùng để tiếp tục stream

changeEvent.documentKey._id
  -> Định danh document nguồn
  -> Dùng để cập nhật cache/search projection
~~~

Lỗi rất hay gặp là lưu documentKey._id rồi dùng làm resumeAfter. Điều đó **không hợp lệ** vì resumeAfter cần **token được server sinh**.

## 11. Các operation types và sự kiện lifecycle

Thông thường consumer quan tâm:

| Operation | Ý nghĩa |
|---|---|
| **insert** | Document được thêm. |
| **update** | Các field của document thay đổi. |
| **replace** | Document được thay thế. |
| **delete** | Document bị xóa. |
| **invalidate** | Stream bị invalidated trong những tình huống lifecycle như collection drop/rename. |
| **drop / rename / dropDatabase** | Một số thay đổi DDL/lifecycle tùy scope. |

Các event types khác có thể xuất hiện ở server version/tùy chọn nhất định, đặc biệt khi bật **showExpandedEvents**. Không hardcode một enum duy nhất rồi giả định database không bao giờ phát event mới.

### 11.1. Invalidate cần cách phục hồi riêng

Nếu collection bị drop hoặc rename, stream có thể nhận **invalidate** và đóng. Nó không đơn giản giống một lần network mất kết nối.

**resumeAfter** không dùng được để tiếp tục **sau invalidate event**. MongoDB cung cấp **startAfter** để mở stream mới sau invalidate khi điều kiện hỗ trợ được đáp ứng.

Nếu consumer vẫn cần watch collection được tạo lại, có thể phải tái khởi tạo state/namespace và kiểm tra schema. Không “nuốt” invalidate rồi chạy mãi với cursor cũ.

### 11.2. No-op writes và sự kiện

Không giả định mọi request updateOne từ ứng dụng đều tạo một event riêng nếu thực chất không thay đổi dữ liệu. Change Streams tập trung vào những thay đổi được MongoDB ghi nhận; một update không tạo thay đổi thực tế có thể không tạo event mong đợi.

Nếu yêu cầu có một event **cho mỗi command nghiệp vụ**, cần domain event/outbox, không chỉ dựa vào change event của document.

## 12. fullDocument, updateLookup và pre-/post-images

### 12.1. updateLookup

Với update event, có thể yêu cầu:

~~~javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
~~~

MongoDB có thể lookup và trả **bản majority-committed hiện tại của document khi lookup được thực hiện**.

**Điểm dễ nhầm:** updateLookup không phải snapshot nguyên vẹn tại thời điểm event được tạo. Nếu một update khác xảy ra giữa thao tác đầu và thời điểm lookup, fullDocument có thể phản ánh state mới hơn.

Ví dụ:

~~~text
T1: status -> PAID      (Event E1)
T2: status -> PACKING   (Event E2)
T3: Consumer xử lý E1 với updateLookup

E1.updateDescription.status = "PAID"
E1.fullDocument có thể phản ánh "PACKING"
~~~

Nếu cần biết chính xác trạng thái document **ngay trước/sau event**, phải hiểu pre/post-image semantics và điều kiện phiên bản tương ứng.

### 12.2. Pre- và post-images (MongoDB 6.0+)

Từ MongoDB 6.0, có thể bật collection-level option:

~~~javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

Sau đó có thể yêu cầu:

~~~javascript
const stream = db.orders.watch([], {
  fullDocumentBeforeChange: "whenAvailable",
  fullDocument: "whenAvailable"
});
~~~

Một số modes:

- **whenAvailable:** trả image nếu có, không mặc định lỗi nếu image thiếu.
- **required:** đòi image; nếu không có theo điều kiện server, có thể báo lỗi.
- **updateLookup:** lookup document hiện tại cho update, không đồng nghĩa post-image đúng tại thời điểm change.

**Pre-image** là document trước update/replace/delete. **Post-image** là document sau insert/update/replace trong ngữ cảnh hỗ trợ; delete không có post-image.

### 12.3. Chi phí của pre/post-images

Việc bật pre/post-images:

- Tăng chi phí lưu trữ và xử lý.
- Có retention và quá trình cleanup.
- Không cung cấp lịch sử vô hạn.
- Có thể khiến event lớn vượt giới hạn BSON.

Chỉ bật khi thật sự cần và có phương án sizing/retention phù hợp.

### 12.4. Giới hạn 16 MiB và large events

MongoDB có giới hạn kích thước BSON document thông thường **16 MiB**. Nếu event bao gồm fullDocument, pre-image, updateDescription lớn, event cũng có thể vượt giới hạn.

Từ MongoDB 7.0, **$changeStreamSplitLargeEvent** có thể được dùng trong tình huống đặc biệt để chia large events, nhưng cần hỗ trợ version/driver và consumer phải hiểu fragments. Không bật mặc định khi dữ liệu không cần.

## 13. Lọc sự kiện ngay tại Change Stream

Change Streams dựa trên aggregation framework. Khi gọi **watch(pipeline, options)**, ứng dụng có thể cung cấp pipeline phù hợp để chỉ nhận những events cần thiết.

### 13.1. Chỉ theo dõi insert và update

~~~javascript
const stream = db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update"]
      }
    }
  }
]);
~~~

Đây là **filter trên event envelope**, không phải query trực tiếp vào document gốc.

### 13.2. Chỉ quan tâm thay đổi status

~~~javascript
const stream = db.orders.watch([
  {
    $match: {
      operationType: "update",
      "updateDescription.updatedFields.status": {
        $exists: true
      }
    }
  }
]);
~~~

Pipeline trên chọn các **update events** có field status nằm trong updatedFields.

**Giới hạn:** không bắt được mọi trường hợp thay đổi trạng thái ở dạng **replace** hoặc một event shape khác. Nếu mục tiêu là “mọi lần trạng thái hiệu lực thay đổi”, cần quyết định rõ cách xử lý **replace**, pre/post-images và dữ liệu nguồn.

### 13.3. Lọc namespace trong database watch

~~~javascript
const stream = db.watch([
  {
    $match: {
      "ns.coll": {
        $in: ["orders", "products"]
      }
    }
  }
]);
~~~

Không phải mọi event lifecycle đều có chính xác cùng fields; pipeline filter cần xem schema của loại event được chọn.

### 13.4. Tránh phép biến đổi làm mất resume token

Event **_id** là resume token. Không dùng pipeline xóa, thay thế hoặc tính lại **event._id**:

~~~javascript
// Không làm:
db.orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      documentKey: 1
    }
  }
]);
~~~

Từ MongoDB 4.2, Change Streams có thể báo lỗi nếu pipeline thay đổi event **_id**. Nếu muốn tạo object DTO nhỏ cho downstream, nên làm **trong consumer sau khi đã lấy/lưu resume token**.

### 13.5. Không đưa mọi aggregation stage vào stream

Change Stream pipeline không phải một aggregation report bình thường có thể dùng bất kỳ stage nào. Ví dụ các write stages **$out** hoặc **$merge** không phù hợp trong change stream pipeline, và **$changeStream** do watch() tạo phải theo đúng vị trí/semantics.

Chỉ chọn stages được MongoDB hỗ trợ cho Change Streams ở phiên bản đang chạy; kiểm tra giới hạn của stages khi chúng biến đổi event envelope.

### 13.6. Lọc sự kiện không tự bảo mật dữ liệu

Một backend watch cả database rồi filter theo tenantId chỉ là cách tối ưu/định tuyến events, **không thay thế quyền truy cập** ở MongoDB và ở API/WebSocket. Một số delete events không có fullDocument, nên cần documentKey hoặc một mapping an toàn để biết tenant đúng.

## 14. Resume token: điều kiện để consumer có thể tiếp tục

### 14.1. Token không phải timestamp thông thường

Mỗi change event có field **_id** chứa một **opaque resume token**:

~~~javascript
{
  _id: {
    _data: "..."
  },
  operationType: "update",
  documentKey: { _id: "ORD-001" }
}
~~~

Token được server tạo để xác định vị trí trong change stream. **Không tự chuyển token sang chuỗi timestamp, không tạo lại bằng document ID và không thay đổi nội dung BSON của token**.

### 14.2. resumeAfter

Một consumer đã xử lý xong event E1 và lưu token:

~~~javascript
const savedToken = event._id;
~~~

Sau khi khởi động lại:

~~~javascript
const stream = db.orders.watch(
  [],
  {
    resumeAfter: savedToken
  }
);
~~~

**resumeAfter** yêu cầu server tiếp tục **sau sự kiện được token chỉ định**.

Lưu ý: **savedToken** ở ví dụ phải là object BSON thật đã được lưu/khôi phục chính xác, không phải chuỗi literal "..." hoặc một ID của order.

### 14.3. startAfter

Nếu một change stream bị **invalidate** do collection drop/rename, không dùng resumeAfter để tiếp tục sau invalidate token. **startAfter** cho phép mở stream mới sau invalidate event theo semantics MongoDB hỗ trợ:

~~~javascript
const stream = db.orders.watch(
  [],
  {
    startAfter: invalidateToken
  }
);
~~~

Consumer có thể còn phải tái khởi tạo schema/projection sau khi collection được tạo lại.

### 14.4. startAtOperationTime

Có thể bắt đầu từ một **BSON Timestamp** của server trong phạm vi oplog còn giữ:

~~~javascript
db.orders.watch(
  [],
  {
    startAtOperationTime: savedBsonTimestamp
  }
);
~~~

Nhưng logical operation time không thay thế tiện lợi cho resume token khi token đã có. Nếu dùng timestamps, phải giữ type BSON chính xác và hiểu semantics của mốc thời gian/possible duplicates.

### 14.5. Chỉ một cơ chế bắt đầu phù hợp

Các options **resumeAfter**, **startAfter** và **startAtOperationTime** không phải ba tham số đặt tùy ý cùng lúc. Chọn cơ chế phù hợp với trạng thái khôi phục; đừng nhét mọi option vào cùng một watch request.

### 14.6. Oplog retention là điều kiện bắt buộc để resume

Resume token chỉ hữu ích khi server **còn đủ lịch sử oplog** để định vị sự kiện tương ứng.

~~~text
Oplog history window
|-------------------------------------------|
T0                                          Tnow

Consumer checkpoint ở Tc:

Nếu Tc nằm trong window -> có thể resume

Nếu Tc đã rơi khỏi window -> resume có thể fail
                            -> cần khởi tạo lại
                               state và bootstrap
~~~

Đây là một rủi ro vận hành lớn của Change Streams. **Không bảo đảm có thể resume sau downtime bất kỳ dài bao nhiêu**, kể cả đã lưu token chính xác.

### 14.7. Post-batch resume token / highwatermark

Server còn có thể trả **postBatchResumeToken** khi lấy batch; đó có thể là **highwatermark token** đánh dấu tiến độ dù không có event business mới. Các driver quản lý token thông qua cursor APIs phù hợp.

Consumer production cần phân biệt:

- **Event token** của một thay đổi đã được xử lý.
- **Highwatermark/post-batch token** biểu thị tiến độ stream.
- **Checkpoint đã được lưu bền vững** của ứng dụng.

Không tự lưu một token mới hơn trước khi các events trước đó đã được xử lý thành công; làm vậy có nguy cơ bỏ qua công việc chưa hoàn tất.

### 14.8. Resume với cùng pipeline/options

MongoDB khuyến nghị khi resume phải dùng **pipeline và options giống với lúc token được tạo**. Thay pipeline có thể làm thay đổi sự kiện được nhìn thấy hoặc thậm chí khiến resume không thể thực hiện.

Nếu nâng cấp version consumer và thay schema/filter, cần kế hoạch migration checkpoint/bootstrap, thay vì chỉ tiếp tục token cũ với pipeline hoàn toàn mới.

## 15. Checkpoint: lưu ở đâu và khi nào?

### 15.1. Quy tắc đơn giản

Một consumer nhận event, xử lý side effect, rồi checkpoint token:

~~~text
Read event E1
      |
      v
Process E1
      |
      v
Persist E1 resume token
      |
      v
Read E2
~~~

Nếu ghi token **trước khi xử lý E1**, rồi process crash:

~~~text
Checkpoint E1
     |
     X crash trước Process E1

ResumeAfter(E1) -> E1 bị bỏ qua!
~~~

Nếu xử lý **trước khi checkpoint**, rồi process crash:

~~~text
Process E1 thành công
     |
     X crash trước Checkpoint E1

Resume từ token cũ -> E1 có thể được xử lý lại
~~~

Trường hợp thứ hai thường được chấp nhận hơn **nếu consumer idempotent**.

### 15.2. At-least-once application processing

Trong triển khai thực tế, consumer nên thiết kế để **sự kiện có thể được giao hoặc xử lý lặp** khi kết nối lỗi, retry hoặc checkpoint chưa kịp lưu.

Change Streams cung cấp cơ chế resume, nhưng **không tự tạo exactly-once end-to-end** cho mọi downstream.

Một chiến lược:

1. Xử lý theo **event token/business entity ID**.
2. Upsert state thay vì tạo bản ghi trùng không có unique key.
3. Giữ **processed event ID** hoặc version để bỏ qua event đã áp dụng.
4. Nếu effect và checkpoint cùng nằm trong MongoDB deployment, cân nhắc cập nhật nguyên tử/transaction phù hợp.
5. Với hệ thống ngoài MongoDB, dùng sink idempotency, outbox hoặc reconciliation.

### 15.3. Ví dụ cập nhật cache

Với event update:

~~~javascript
{
  operationType: "update",
  documentKey: {
    _id: "ORD-001"
  }
}
~~~

Consumer có thể xóa key cache:

~~~text
DEL cache:order:ORD-001
~~~

Thao tác xóa cache key thường idempotent: nếu thực hiện hai lần, key vẫn không tồn tại. Nhưng consumer vẫn cần đảm bảo authorization, event order và eventual refresh.

### 15.4. Ví dụ cập nhật tìm kiếm

Với insert/replace/update, một consumer có thể truy vấn trạng thái hiện tại rồi **upsert** index theo document ID. Với delete thì xóa index theo ID.

Điều cần chú ý:

- UpdateLookup có thể trả document mới hơn event.
- Event bị replay không nên tạo duplicate search documents.
- Một consumer chậm có thể cập nhật index bằng bản cũ nếu không kiểm soát ordering/version.
- Nếu oplog window đã mất, có thể phải full reindex.

### 15.5. Nhiều consumer instances

Change Streams **không tự cung cấp một consumer group partitioning giống Kafka**. Nếu hai instances đều mở watch trên cùng scope, cả hai có thể nhận cùng các events.

Khi ứng dụng scale ngang, cần quy định:

- Một logical consumer chỉ có **một active owner** (leader election/lease).
- Hoặc nhiều consumers nhận event nhưng thực hiện **idempotent/deduplicated** processing.
- Hoặc chuyển events vào broker có consumer groups.

Không giả định MongoDB tự chia mỗi event chỉ cho một trong hai service instances.

## 16. Bootstrap: lấy dữ liệu ban đầu rồi theo dõi thay đổi

Change Streams nhìn vào **changes** chứ không tự cung cấp ảnh chụp đầy đủ của collection.

Giả sử cần tạo search index từ collection products có sẵn 1 triệu documents:

~~~text
MongoDB products
        |
        +-- Initial full scan  -> Search index baseline
        |
        +-- Change stream     -> incremental updates
~~~

### 16.1. Race condition giữa snapshot và watch

Pattern nguy hiểm:

~~~text
T1: Scan all documents
T2: Một document bị xóa
T3: Mở Change Stream

Delete tại T2 bị mất khỏi luồng.
Search index có thể giữ document đã bị xóa.
~~~

**Không chỉ full scan xong rồi mới bắt đầu watch** nếu giữa hai bước có thể có writes.

### 16.2. Thiết kế bootstrap an toàn hơn

Một chiến lược khái niệm:

1. Mở Change Stream hoặc lấy một starting point được server hỗ trợ.
2. Bắt đầu initial scan/snapshot với cách định nghĩa nhất quán.
3. Trong lúc scan, **buffer hoặc duy trì backlog** các events đến.
4. Hoàn thành baseline.
5. **Replay events** từ mốc đã ghi nhận với ordering/idempotency phù hợp.
6. Chuyển sang chế độ consume liên tục.
7. Chỉ checkpoint khi event đã thực sự được áp dụng.

Chi tiết chính xác phụ thuộc consistency requirement, sharding, snapshot support và kích thước dữ liệu; không xem đây là một thuật toán có thể copy nguyên vào production mà không xử lý races.

### 16.3. Nếu mất oplog trong lúc bootstrap

Nếu initial scan quá lâu và starting point rơi khỏi oplog window, không thể bảo đảm replay toàn bộ delta từ token cũ. Cần **bắt đầu lại bootstrap** với mốc mới hoặc dùng cơ chế CDC có retention phù hợp.

## 17. Connection pool, cursor và tài nguyên

### 17.1. Change Stream là cursor dài hạn

Một Change Stream thường giữ cursor mở để chờ events. Các lệnh **getMore** khi chờ có thể chiếm một connection từ pool.

MongoDB cảnh báo: nếu số active change streams vượt connection pool size, có thể xảy ra **notification latency**. Vì vậy cần sizing pool dựa trên số lượng open streams và tải truy vấn khác.

~~~text
MongoClient pool (maxPoolSize = N)
         |
         +-- stream 1: getMore
         +-- stream 2: getMore
         +-- stream 3: getMore
         +-- HTTP query A
         +-- HTTP query B
~~~

Nếu nhiều stream sử dụng phần lớn connections, HTTP queries có thể chờ lấy connection. Cân nhắc **MongoClient pool chuyên dụng cho CDC consumer** khi ứng dụng có nhiều streams dài hạn.

### 17.2. Đừng tạo một watch mới cho mỗi HTTP request

Pattern nguy hiểm:

~~~text
GET /orders
  -> create new MongoClient
  -> open db.orders.watch()
  -> wait for event

GET /orders
  -> create another MongoClient
  -> open another watch()
~~~

Mỗi request có thể làm tăng số connections/cursors và gây rò rỉ tài nguyên.

Thiết kế phù hợp:

- Một hoặc vài long-lived consumers do service quản lý.
- Dùng chung một MongoClient/pool phù hợp.
- Phân phối notifications tới WebSocket/SSE subscribers nội bộ bằng một router.
- Đóng cursor khi service shutdown, xử lý cancellation/error.

### 17.3. Java synchronous API là blocking

Với Java Sync Driver, duyệt Change Stream cursor thường **chờ event**. Không chạy vòng chờ vô hạn trên HTTP request thread hoặc event-loop thread.

Sử dụng worker thread riêng, managed executor hoặc reactive solution phù hợp. Spring Data documentation khuyến nghị reactive variant khi phù hợp vì sync listener cần một task lâu dài.

### 17.4. MaxAwaitTime không phải total processing deadline

**maxAwaitTimeMS** quyết định khoảng thời gian server có thể chờ trong getMore. Nó không có nghĩa stream tự dừng sau số mili giây đó; cursor có thể tiếp tục chờ nhiều vòng.

Ứng dụng cần shutdown deadline, connection timeout và processing timeout riêng.

### 17.5. Sharded cluster có chi phí khác

Khi mở Change Stream trên sharded cluster, **mongos** thiết lập các streams tương ứng trên shards và xử lý ordering/filtering; đôi khi có thêm fullDocument lookup. Việc có nhiều shards và số streams lớn làm tăng chi phí.

Không mặc định phạm vi collection-level sẽ chỉ cần một connection hoặc chỉ đọc một shard trong mọi trường hợp sharded.

### 17.6. Oplog window và tốc độ sinh event

Oplog retention không được hiểu đơn giản như một con số ngày cố định. Tùy cấu hình dung lượng oplog, tốc độ ghi và retention settings, các entries cũ có thể bị xóa khi hết dung lượng/thời gian lưu.

Khi tốc độ ghi cao, **oplog window có thể ngắn đi**, làm consumer ngắt kết nối vài giờ đã mất khả năng resume. Cần giám sát và dự phòng capacity.

## 18. Java Sync Driver: mở Change Stream đúng cách

MongoDB Java Sync Driver dùng:

- **MongoClient.watch()** cho deployment scope.
- **MongoDatabase.watch()** cho database scope.
- **MongoCollection.watch()** cho collection scope.

Kết quả là **ChangeStreamIterable** và có thể tạo **MongoChangeStreamCursor** để nhận các event.

### 18.1. Chương trình theo dõi orders

~~~java
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
import org.bson.conversions.Bson;

import java.util.List;
import java.util.concurrent.TimeUnit;

public final class OrdersChangeStreamDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must point to a replica set or sharded cluster"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("change_stream_lab");
            MongoCollection<Document> orders =
                    database.getCollection("orders");

            List<Bson> pipeline = List.of(
                    Aggregates.match(
                            Filters.in(
                                    "operationType",
                                    List.of("insert", "update", "replace", "delete")
                            )
                    )
            );

            ChangeStreamIterable<Document> iterable = orders
                    .watch(pipeline)
                    .fullDocument(FullDocument.UPDATE_LOOKUP)
                    .maxAwaitTime(2, TimeUnit.SECONDS);

            try (
                    MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                            cursor = iterable.cursor()
            ) {
                while (!Thread.currentThread().isInterrupted()) {
                    ChangeStreamDocument<Document> event = cursor.tryNext();

                    if (event == null) {
                        continue;
                    }

                    System.out.println(
                            "Event type: " + event.getOperationType()
                    );
                    System.out.println(
                            "Document key: " + event.getDocumentKey()
                    );

                    Document fullDocument = event.getFullDocument();
                    if (fullDocument != null) {
                        System.out.println(fullDocument.toJson());
                    }

                    BsonDocument resumeToken = event.getResumeToken();

                    // Trong production:
                    // 1) Xử lý event bằng một thao tác idempotent.
                    // 2) Chỉ sau khi xử lý thành công,
                    //    checkpoint resumeToken vào nơi lưu bền vững.
                    System.out.println(
                            "Resume token: " + resumeToken.toJson()
                    );
                }
            }
        }
    }
}
~~~

Đoạn trên **chỉ in token để minh họa**, chưa có persistence của checkpoint và chưa có retry/recovery policy production.

### 18.2. Vì sao cần worker riêng?

**MongoChangeStreamCursor.tryNext()** có thể chờ trong lúc đợi server trả batch. Nếu đặt vòng lặp này trong một HTTP controller, request thread có thể bị chiếm lâu không cần thiết.

Production consumer nên chạy bằng **managed worker/service lifecycle**, có shutdown signal, cancellation và close cursor đúng cách.

### 18.3. Event API cần lưu ý

~~~java
event.getResumeToken();   // BsonDocument token dùng cho resume.
event.getDocumentKey();   // BsonDocument định danh document nguồn.
event.getFullDocument();  // Document nếu option/event có dữ liệu.
event.getOperationType();// Loại thao tác.
event.getClusterTime();   // BSON timestamp logic.
~~~

Đừng nhầm **getDocumentKey()** với **getResumeToken()**.

### 18.4. Resume từ một token đã lưu

~~~java
// savedToken phải là token BSON thật đã lấy từ một event/cursor.
BsonDocument savedToken = loadResumeTokenFromCheckpoint();

ChangeStreamIterable<Document> iterable = orders
        .watch()
        .resumeAfter(savedToken)
        .fullDocument(FullDocument.UPDATE_LOOKUP);
~~~

**loadResumeTokenFromCheckpoint()** trong ví dụ là hàm do ứng dụng tự triển khai, không phải API mặc định của MongoDB driver.

Khi triển khai hàm này:

1. Lưu token ở dạng BSON giữ nguyên dữ liệu.
2. Dùng cùng change stream pipeline/options như khi tạo token.
3. Kiểm tra trường hợp token đã ngoài oplog window.
4. Không tự bỏ qua lỗi resume rồi bắt đầu từ “now” nếu business không chấp nhận mất delta.

### 18.5. Connection URI và Client lifecycle

Một replica set URI có thể như:

~~~text
mongodb://db1.example:27017,db2.example:27017,db3.example:27017/?replicaSet=rs0
~~~

Hoặc dùng **mongodb+srv** khi provider hỗ trợ:

~~~text
mongodb+srv://<user>:<password>@cluster.example/?retryWrites=true
~~~

Đây là URI minh họa, không phải endpoint truy cập được. Không hardcode credentials trong source và không tạo MongoClient mới cho mỗi event.

### 18.6. Java sync driver không tự bảo đảm exactly-once

Driver có thể tự resume sau một số lỗi resumable theo semantics của nó, nhưng **không biết downstream đã xử lý thành công hay chưa**.

Nếu sự kiện đã được gửi sang search index nhưng token chưa checkpoint, sau restart consumer có thể nhận lại event. Hãy thiết kế **upsert idempotent**, unique business ID hoặc lưu transactionally cả result và checkpoint trong cùng MongoDB deployment khi phù hợp.

## 19. Spring Data MongoDB: Change Streams với reactive và imperative APIs

Spring Data MongoDB có cơ chế xử lý Change Streams trên cả imperative và reactive drivers.

### 19.1. ReactiveMongoTemplate

Với Spring Data MongoDB Reactive, có thể:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;
import reactor.core.Disposable;

public final class ReactiveOrdersListener {
    private final ReactiveMongoTemplate template;

    public ReactiveOrdersListener(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Disposable start() {
        Flux<ChangeStreamEvent<Document>> changes = template
                .changeStream(Document.class)
                .watchCollection("orders")
                .listen();

        return changes.subscribe(
                event -> {
                    Document body = event.getBody();
                    System.out.println("Change: " + body);
                    System.out.println("Token: " + event.getResumeToken());
                    // Production: đẩy sang một pipeline xử lý
                    // idempotent và checkpoint token.
                },
                error -> {
                    System.err.println("Change stream failed: " + error);
                    // Production: phân loại resumable/non-resumable,
                    // restart theo checkpoint và chính sách backoff.
                }
        );
    }
}
~~~

**Disposable** dùng để hủy subscription khi service shutdown. Đây là ví dụ minh họa luồng reactive, không phải cơ chế xử lý lỗi và checkpoint đầy đủ.

### 19.2. Reactive không tự làm công việc nhanh hơn trong mọi trường hợp

Reactive model hữu ích cho stream chờ I/O và khả năng quản lý non-blocking subscribers. Nhưng nếu consumer xử lý mỗi event bằng CPU-bound tasks dài hoặc gọi một HTTP blocking API trực tiếp trong subscriber, vẫn có thể tắc nghẽn.

Cần tổ chức:

- Backpressure/flow control phù hợp.
- Schedulers hoặc client non-blocking đúng loại.
- Giới hạn concurrency downstream.
- Ordering theo entity nếu business yêu cầu.
- Retry/resume token và error routing.

### 19.3. Imperative MessageListenerContainer

Spring Data còn hỗ trợ **DefaultMessageListenerContainer** và **ChangeStreamRequest** cho imperative applications. Cơ chế này khởi tạo một task chờ sự kiện trên sync driver.

Điểm cần nhớ:

1. **Sync Change Stream chặn thread** khi chờ dữ liệu, nên listener container cần thread/task riêng.
2. Tạo và register subscription request có collection scope/options.
3. Đăng ký **ErrorHandler** để xử lý lỗi stream; không chỉ để exception nằm trong log.
4. Stop container khi application shutdown.
5. Nếu watch database có nhiều document types, dùng kiểu **Document** khi không thể map mọi event về một entity cố định.

### 19.4. Không đồng nhất ChangeStreamEvent với entity

Một change event không chỉ là một Product/Order entity; nó có metadata **operationType, resumeToken, documentKey** và có thể **không chứa fullDocument** trong một số thao tác như delete.

Spring Data mapping cần xử lý đúng sự khác biệt giữa event envelope và domain document.

### 19.5. Spring Data resume API

Spring Data ChangeStreamOptions có cơ chế resume từ token hoặc server time theo các APIs hỗ trợ. Khi resume bằng thời gian, cần chú ý BSON timestamp precision. Nếu đã có resume token chính xác, thường nên ưu tiên token.

Tài liệu chính thức có ví dụ **resumeAt** và cách đọc **ChangeStreamEvent.getResumeToken()**; kiểm tra API signatures theo Spring Data version thực tế.

## 20. Khi nào nên dùng Change Streams, outbox hoặc message broker?

### 20.1. Change Stream cho projection theo thay đổi dữ liệu

Ví dụ sản phẩm thay name/price:

~~~text
MongoDB products
      |
      v
Change Stream
      |
      v
Search Index Consumer
      |
      v
Elasticsearch / OpenSearch
~~~

Consumer cần biết document nào đổi rồi cập nhật projection. Change Streams phù hợp vì yêu cầu gắn trực tiếp với persisted data changes.

### 20.2. Transactional outbox cho domain event

Một nghiệp vụ chuyển tiền có thể cần một event rõ nghĩa như **TransferCompleted** chứ không chỉ ba thay đổi ở hai tài khoản và collection transfers.

~~~text
MongoDB transaction:
  update source account
  update target account
  insert transfer record
  insert outbox event
           |
           v
      COMMIT
           |
           v
Change Stream on outbox
           |
           v
Publisher -> Message Broker
~~~

Trong mô hình này, Change Stream dùng để **phát hiện outbox event đã commit**, còn outbox document cung cấp **business event contract**.

### 20.3. Vì sao không chỉ watch orders rồi gửi email ngay?

Nếu email sender xử lý event rồi crash trước khi checkpoint:

~~~text
Send email thành công
       |
       X crash
       |
Resume cùng event
       |
       v
Send email lần hai
~~~

Để tránh duplicate emails, cần idempotency key hoặc record trạng thái gửi được cập nhật bền vững. Change Stream không tự thu hồi email đã gửi.

### 20.4. Message broker cho fan-out/replay dài hạn

Khi có hàng chục consumer groups độc lập, yêu cầu giữ event trong nhiều tháng và replay theo offset, một broker chuyên dụng có thể thích hợp hơn cho phân phối.

Một kiến trúc thường gặp:

~~~text
MongoDB
  |
  +-- Change Stream Reader
         |
         +-- Normalize / Validate / Enrich
         |
         v
      Kafka topic
         |
         +-- Search projection consumer
         +-- Analytics consumer
         +-- Notification consumer
~~~

Việc chọn kiến trúc phụ thuộc throughput, retention, SLA, failover, replay semantics và vận hành. Không mặc định Change Streams “thua” hay “thắng” broker ở mọi bài toán.

## 21. Dữ liệu thay đổi trong transactions và các trường hợp đặc biệt

### 21.1. Change events từ multi-document transactions

MongoDB phát các events liên quan những thay đổi đã commit và có thể kèm **lsid, txnNumber**. Các event cần được hiểu trong ngữ cảnh transaction đã commit, không phải mọi operation chưa commit đều được phát ra.

Nếu transaction abort, những writes chưa commit thuộc transaction đó không được phát như các thay đổi bền vững đã xảy ra.

### 21.2. Không suy từ một event ra toàn bộ business transaction

Một transaction có thể cập nhật cả orders, payments và inventory. Consumer watch **orders** chỉ thấy phần thay đổi thuộc scope orders, không tự nhận full summary của transaction.

Nếu downstream cần một sự kiện tổng hợp **OrderPlaced/PaymentSettled** có schema ổn định, dùng **outbox/domain event**.

### 21.3. Deletes và TTL

Deletes có event phù hợp khi thay đổi được ghi nhận, nhưng document đã mất nên không còn fullDocument để lookup. Nếu cần thông tin tenant hoặc fields cũ để xóa projection, phải giữ mapping, dùng documentKey/shard key hoặc pre-image khi được hỗ trợ.

Không dựa vào **updatedAt polling** để phát hiện mọi delete; Change Streams giải quyết bài toán này tốt hơn với event delete.

### 21.4. Sharded documentKey không luôn chỉ có _id

Trong sharded collection, **documentKey** có thể chứa shard key fields ngoài _id. Khi xử lý cache key hoặc query, cần hiểu shard key, schema và field có thể bị thiếu.

Không kết luận mọi documentKey có cấu trúc đúng **{_id:...}** ở mọi sharded deployment/version.

### 21.5. Những thao tác DDL

Collection drop/rename có thể làm stream invalidate; các expanded events như create/index-related events yêu cầu options/version tương ứng. Consumer cần phân biệt:

- Thay đổi dữ liệu document.
- Thay đổi schema/collection lifecycle.
- Những thao tác nội bộ MongoDB không phát qua scope thông thường.

## 22. Những câu hỏi cần trả lời trước khi triển khai production

### 22.1. Mục tiêu xử lý là gì?

Viết rõ:

~~~text
Khi collection orders có thay đổi status,
consumer làm mới projection của order trong search index.

Latency mục tiêu: theo SLA ứng dụng.
Có thể nhận trùng event: có, nếu xử lý idempotent.
Thời gian downtime cần resume: phải nằm trong oplog window.
Khi mất history: thực hiện full reconciliation/rebuild.
~~~

Nếu chưa xác định hành động downstream và độ trễ có thể chấp nhận, chưa đủ thông tin để chọn scope, tài nguyên và recovery.

### 22.2. Deployment có đủ điều kiện không?

Phải xác nhận:

- Là replica set hoặc sharded cluster, không phải standalone.
- Storage engine phù hợp (WiredTiger) và protocol pv1.
- MongoDB server và driver versions hỗ trợ options muốn dùng.
- URI kết nối đúng topology; sharded cluster qua mongos.
- User/service account có **find + changeStream** trong scope cần thiết.
- Network/TLS và authentication hoạt động ổn định.

### 22.3. Có cần fullDocument hay pre/post-images?

Hãy cân nhắc:

- **updateDescription** có đủ cho consumer không?
- Nếu cần bản hiện tại, chấp nhận **updateLookup có thể mới hơn event** không?
- Nếu cần đúng bản trước/sau, có hỗ trợ và đã bật pre/post-images không?
- Document có lớn khiến event có thể vượt 16 MiB không?
- Dữ liệu nhạy cảm có bị phát rộng hơn nhu cầu không?

Không bật fullDocument/pre-images chỉ vì “có sẵn”, vì tăng tải và phạm vi dữ liệu truyền.

### 22.4. Consumer xử lý trùng như thế nào?

Định nghĩa một **idempotency strategy**:

| Loại downstream | Ví dụ chiến lược |
|---|---|
| Cache | Delete/invalidate cùng key nhiều lần vẫn an toàn. |
| Search index | Upsert theo document ID/version, không tạo entry trùng. |
| Analytics | Dedupe theo event token/business event ID hoặc dùng upsert versioned. |
| Email | Unique notification key và trạng thái gửi đã lưu. |
| Payment provider | Provider idempotency key; không charge trực tiếp theo raw change event. |

Nếu một consumer không thể xử lý lặp, không nên đưa nó vào production chỉ với một vòng **while(hasNext())**.

### 22.5. Token được lưu ở đâu?

Ví dụ collection **change_stream_checkpoints**:

~~~javascript
{
  _id: "orders-search-index-v1",
  consumerName: "orders-search-index",
  token: {
    _data: "<opaque-resume-token>"
  },
  pipelineVersion: 1,
  updatedAt: ISODate("2026-07-01T00:00:00Z")
}
~~~

Đây là schema minh họa; token thật do MongoDB tạo. **Giữ nguyên BSON type của token**. Nếu nhiều instances có thể ghi vào cùng checkpoint, cần lease/fencing/version CAS để một instance cũ không ghi đè checkpoint tiến độ của instance mới.

### 22.6. Nếu mất token hoặc oplog đã xóa history?

Không âm thầm bắt đầu watch từ hiện tại rồi tuyên bố projection chính xác. Phải xác định:

- Có checkpoint cuối nào còn hợp lệ?
- Khoảng dữ liệu bị bỏ lỡ dài bao nhiêu?
- Có thể rebuild toàn bộ từ MongoDB source không?
- Có reconciliation jobs kiểm tra chênh lệch không?
- Có thể tạm dừng downstream hoặc đánh dấu dữ liệu stale cho đến khi rebuild xong không?

### 22.7. Cần bao nhiêu active streams?

Mỗi Change Stream sử dụng cursor/getMore và có thể chiếm connection chờ event. Nếu 100 tenants tạo 100 streams trên cùng pool 20 connections, cần dự đoán độ trễ và contention.

Có thể chọn một database-level consumer định tuyến theo tenant thay vì 100 collection-level streams, **nhưng phải cân bằng bảo mật, throughput và phạm vi failure**. Không có một phương án đúng tuyệt đối.

## 23. Bảng chọn triển khai theo kịch bản

| Kịch bản | Scope gợi ý | Bắt buộc chuẩn bị |
|---|---|---|
| Làm mới cache orders | Collection | Idempotent invalidation, token, restart handling. |
| Search index của products | Collection | Initial bootstrap, version/order handling, rebuild nếu mất oplog. |
| Analytics nhiều collections cùng database | Database | Filter namespace, mapping nhiều schema, checkpoint. |
| Central CDC cho nhiều databases | Deployment | Quyền rộng, governance, routing, throughput, network/security. |
| Notification theo domain event | Outbox collection | Business event schema, idempotent publisher/consumer. |
| Theo dõi thao tác trên standalone local | Chưa thể watch | Chuyển thành replica set thử nghiệm hoặc dùng polling. |
| Audit dài hạn cần lưu nhiều năm | Không chỉ Change Stream | Lưu audit records bền vững và áp dụng retention/security. |
| Update UI gần thời gian thực | Collection/Database → app relay | User authorization, WebSocket/SSE, backpressure, reconnection. |

### 23.1. Một câu hỏi định hướng

Nếu ứng dụng chỉ cần “khi document đổi thì cache invalidated”, Change Streams thường đủ làm nguồn notification khi có consumer đúng cách.

Nếu nghiệp vụ đòi “đã xác nhận thanh toán xong thì phát đúng một domain event sang năm hệ thống và có thể replay sau sáu tháng”, nên thiết kế **outbox/broker/retention** bên cạnh hoặc phía sau Change Streams.

## 24. Kiểm thử và giám sát

### 24.1. Kiểm thử chức năng cơ bản

Trên replica set lab:

1. Mở stream collection orders.
2. Insert một order mới.
3. Update status của order.
4. Replace order.
5. Delete order.
6. Quan sát **operationType, documentKey, updateDescription, fullDocument**.
7. Kiểm tra không phát sự kiện cho một lần read thuần túy.

### 24.2. Kiểm thử mất kết nối và resume

1. Mở consumer, xử lý E1 và lưu token.
2. Dừng consumer.
3. Thực hiện E2, E3 khi consumer chưa chạy.
4. Khởi động lại với **resumeAfter(token E1)**.
5. Kiểm tra E2/E3 được tiêu thụ khi oplog history còn đủ.
6. Thử crash sau xử lý E2 nhưng trước checkpoint để xác nhận idempotency.

### 24.3. Kiểm thử mất oplog window

Trên môi trường test được kiểm soát, tạo tình huống checkpoint quá cũ so với oplog retention.

Kỳ vọng: consumer phải **phát hiện lỗi resume**, chuyển sang quy trình rebuild/reconciliation hoặc báo sự cố nghiêm trọng; **không âm thầm bỏ qua các event bị mất**.

### 24.4. Kiểm thử invalidate

Trên một collection test không chứa dữ liệu thật:

~~~javascript
db.temp_watch_lab.insertOne({ _id: 1 });
~~~

Mở watch cho temp_watch_lab rồi trong terminal khác:

~~~javascript
db.temp_watch_lab.drop();
~~~

Quan sát event drop/invalidate tùy stream scope. Kiểm tra consumer không nhầm invalidate với một error network có thể resumeAfter thông thường.

**Không drop collection thật để kiểm thử.**

### 24.5. Kiểm thử scale/connections

Đo:

- Số active streams.
- Connection pool occupancy, wait time, timeouts.
- Latency từ clusterTime/event đến lúc consumer hoàn tất.
- Độ dài queue/backlog.
- Throughput events/giây.
- CPU/RAM và lag của downstream.

Không chỉ đo latency khi collection có một document lab; benchmark phải phản ánh tải thực tế.

### 24.6. Metrics vận hành

| Metric | Vì sao cần |
|---|---|
| **change_stream_events_total** | Biết tốc độ sự kiện và operationType. |
| **change_stream_processing_latency** | Quan sát consumer chậm. |
| **change_stream_resume_total** | Phát hiện kết nối không ổn định. |
| **change_stream_resume_failures_total** | Báo nguy cơ mất history/token không hợp lệ. |
| **change_stream_checkpoint_age** | So thời gian checkpoint với oplog window. |
| **change_stream_active_cursors** | Hiểu số streams/connection pressure. |
| **change_stream_duplicate_events_total** | Quan sát replay/idempotency. |
| **change_stream_downstream_errors_total** | Phân biệt lỗi MongoDB với lỗi sink. |
| **oplog_window_seconds** | Khả năng chịu downtime trước khi mất resume. |
| **change_stream_invalidation_total** | Phát hiện collection drop/rename/lifecycle. |

Các tên trên là **metrics gợi ý ở ứng dụng**, không phải tên server metrics mặc định bắt buộc của MongoDB.

### 24.7. Alert theo rủi ro business

Ví dụ:

~~~text
Checkpoint age > 50% oplog window
   -> warning, kiểm tra consumer lag.

Checkpoint age gần oplog window
   -> critical, nguy cơ mất khả năng resume.

Resume repeatedly failed
   -> không restart vô hạn không delay;
      escalations + bắt đầu recovery plan.

Large backlog / downstream slow
   -> throttle, scale consumer hoặc tăng sink capacity.
~~~

Các ngưỡng phần trăm chỉ minh họa; chọn dựa trên retention thực, tốc độ ghi và SLO.

## 25. Troubleshooting các lỗi triển khai phổ biến

### 25.1. “The $changeStream stage is only supported on replica sets”

Nguyên nhân thường gặp: kết nối đang trỏ tới **standalone mongod**.

Hướng xử lý:

1. Kiểm tra **db.hello()**.
2. Xác nhận đang chạy replica set/sharded cluster.
3. Với local, cấu hình single-node replica set.
4. Với production, thay đổi topology theo quy trình quản trị, không sửa nóng tùy tiện.

### 25.2. Unauthorized khi watch

Nguyên nhân: thiếu **find** hoặc **changeStream** cho scope được yêu cầu.

Hướng xử lý: kiểm tra role của service account, scope watch, auth database và connection credentials; cấp **quyền tối thiểu** thay vì admin toàn cluster.

### 25.3. Stream không có event dù có writes

Kiểm tra:

- Terminal/app có kết nối tới đúng cluster/database/collection không?
- Stream được mở trước writes cần quan sát chưa?
- Write có thực sự tạo thay đổi dữ liệu không?
- Pipeline $match có lọc mất operationType/namespace không?
- Write đã majority committed chưa?
- Cursor có đang chạy, không bị close/cancel hay không?
- Consumer có chờ đủ thời gian và không block thread sai cách không?

### 25.4. Có event nhưng fullDocument null

Không phải mọi event đều có fullDocument:

- **delete** không có post-image.
- **update** mặc định chỉ có delta.
- **updateLookup** có thể không tìm được document hiện tại nếu đã bị xóa hoặc không còn phù hợp lúc lookup.
- **whenAvailable** có thể không có image khi chưa bật collection option hoặc image đã hết retention.

Chọn giải pháp theo nhu cầu: delta, lookup, pre/post-images hoặc domain event.

### 25.5. Resume token invalid / oplog history lost

Khả năng:

- Token không được lưu nguyên vẹn.
- Đã dùng documentKey._id thay cho event._id.
- Pipeline/options thay đổi không tương thích.
- Oplog window không còn chứa event cũ.
- Collection lifecycle invalidation yêu cầu startAfter thay vì resumeAfter.

Không tự bỏ qua lỗi rồi bắt đầu xem dữ liệu chỉ từ thời điểm hiện tại nếu downstream phải đầy đủ.

### 25.6. Event xử lý hai lần

Điều này có thể xảy ra nếu consumer crash **sau side effect trước checkpoint** hoặc resume/retry. Hướng xử lý là **idempotent consumer**, dedupe và checkpoint discipline, không mong event stream có global exactly-once effect.

### 25.7. Notification chậm khi tăng số streams

Xem **maxPoolSize**, số active cursors và getMore connections, tốc độ xử lý của consumer và sharded cluster fan-out.

Đừng chỉ tăng CPU nếu bottleneck nằm ở connection pool hoặc downstream sink.

### 25.8. Mỗi service instance đều xử lý cùng event

Nếu nhiều instances cùng gọi watch trên một collection, chúng **đều đăng ký stream riêng**. Không có cơ chế consumer group tự chia event.

Thiết kế singleton consumer/lease, idempotent fan-out hoặc broker có phân phối consumer groups.

### 25.9. Collection bị drop rồi watch ngừng

Phân biệt invalidate event với lỗi network. Khi cần theo dõi collection mới được tạo lại, xem semantics **startAfter**, tái bootstrap và cập nhật checkpoint/pipeline phù hợp.

### 25.10. Chỉ chạy được trên local replica set, lỗi trên sharded production

Kiểm tra:

- URI có qua **mongos** không?
- Auth scope trên database/collections có đủ không?
- Shard key/documentKey handling có phù hợp không?
- Chunk migrations/shard removal có gây cursor lifecycle khác không?
- FullDocument lookup, pool size và throughput có đáp ứng tải không?

Local single-node replica set không thể thay thế kiểm thử topology sharded.

## 26. Checklist triển khai Change Streams

Trước khi bật consumer production, xác nhận:

1. **Mục tiêu:** event nào tạo ra hành động gì ở downstream?
2. **Topology:** replica set hoặc sharded cluster, đúng storage engine/protocol.
3. **Version:** server, driver, Spring Data tương thích API/options đã dùng.
4. **URI:** đúng replica set/mongos, TLS và network được cấu hình.
5. **RBAC:** có find + changeStream, scope tối thiểu.
6. **Watch scope:** collection/database/deployment được chọn có chủ đích.
7. **Pipeline:** lọc đúng event, không sửa resume token _id.
8. **Event contract:** phân biệt documentKey, resume token, update delta và fullDocument.
9. **Pre-/post-images:** chỉ bật khi cần, có retention và sizing.
10. **Initial state:** đã có kế hoạch bootstrap không mất events.
11. **Checkpoint:** lưu token bền vững sau successful/idempotent processing.
12. **Resume:** có backoff, handling cho invalidate và oplog history lost.
13. **Idempotency:** downstream chịu được event replay hoặc có dedupe.
14. **Concurrency:** nhiều instances có lease/fencing hoặc mô hình fan-out rõ.
15. **Resources:** sizing connection pool, getMore cursors, memory và queue.
16. **Security:** không relay dữ liệu nhạy cảm sai tenant.
17. **Observability:** consumer lag, checkpoint age, resume failures, oplog window.
18. **Recovery:** nếu oplog quá cũ có thể rebuild/reconcile.
19. **Testing:** insert/update/replace/delete, disconnect, restart, failover, high load.
20. **Lifecycle:** đóng cursor, subscription và MongoClient khi shutdown.

## 27. Bài thực hành

### Bài 1 — Mục tiêu Change Streams

Một e-commerce platform muốn cập nhật search index khi product đổi giá hoặc tên. Hãy mô tả flow từ updateOne đến change event, consumer và search index. Liệt kê nơi có thể phát sinh trễ.

### Bài 2 — Polling vs Change Streams

Giải thích ít nhất ba rủi ro khi chỉ dùng:

~~~javascript
db.products.find({
  updatedAt: { $gt: lastCheckpoint }
});
~~~

Tại sao thao tác delete khó được phát hiện bằng polling này?

### Bài 3 — Kiểm tra topology

Trên một MongoDB mongosh:

~~~javascript
db.hello();
~~~

Xác định nó là standalone, replica set hay mongos. Một standalone có chạy Change Streams được không?

### Bài 4 — Local replica set

Trên **máy test riêng**, cấu hình một single-node replica set, gọi rs.initiate và mở db.orders.watch(). Tại sao test này chưa đủ để đánh giá failover production?

### Bài 5 — Quyền truy cập

Viết custom role chỉ có **find** và **changeStream** trên **appdb.orders**. Vì sao không nên gán admin role cho consumer chỉ theo dõi orders?

### Bài 6 — Collection vs database scope

Một service chỉ cần orders, một service khác cần orders và products. Chọn watch scope cho từng service và giải thích trade-off.

### Bài 7 — Quan sát event

Mở Change Stream trong terminal A. Terminal B chạy insert, update, replace, delete trên ORD-001. Ghi lại operationType, documentKey và fullDocument/updateDescription của mỗi event.

### Bài 8 — Resume token

Giải thích sự khác nhau giữa:

~~~text
event._id
event.documentKey._id
~~~

Field nào cần truyền vào resumeAfter?

### Bài 9 — Resume sau restart

Consumer đã checkpoint token E1. Trong lúc nó tắt, server phát E2 và E3. Khởi động với resumeAfter(E1). Điều kiện gì về oplog phải được thỏa?

### Bài 10 — Invalidate

Collection bị drop sau một event. Vì sao resumeAfter(invalidateToken) không phù hợp? Khi nào xem xét startAfter và bootstrap lại?

### Bài 11 — fullDocument updateLookup

Event E1 đổi status từ PENDING thành PAID, sau đó E2 đổi PAID thành SHIPPED. Consumer xử lý E1 muộn, với fullDocument updateLookup. Tại sao fullDocument của E1 có thể là SHIPPED?

### Bài 12 — Pre/post-image

Giải thích điều kiện để có pre-image của một update trên MongoDB 6.0+. Vì sao image có thể thiếu dù consumer đã bật whenAvailable?

### Bài 13 — Pipeline filter

Viết watch pipeline chỉ nhận insert và update. Sau đó viết thêm filter cho updateDescription.updatedFields.status. Vì sao cần xử lý replace riêng nếu muốn biết mọi thay đổi trạng thái?

### Bài 14 — Exactly-once

Consumer cập nhật search index thành công rồi crash trước checkpoint. Sau restart, event được phát lại. Thiết kế idempotent upsert theo document ID/version.

### Bài 15 — Initial bootstrap

Từ một collection có 500.000 documents, làm thế nào build projection ban đầu mà không bỏ mất các updates xảy ra giữa full scan và lúc mở stream?

### Bài 16 — Java Sync Driver

Viết Java code mở collection.watch(), dùng FullDocument.UPDATE_LOOKUP, tryNext() và event.getResumeToken(). Vì sao phải đặt nó ở worker thread thay vì HTTP controller?

### Bài 17 — Spring Data Reactive

Dùng ReactiveMongoTemplate.changeStream(...).watchCollection("orders").listen() để tạo Flux events. Trình bày cách đóng subscription và xử lý lỗi khi stream disconnect.

### Bài 18 — Connection pool

Một service mở 150 streams nhưng maxPoolSize=50. Theo tài liệu MongoDB, nguy cơ vận hành là gì? Những phương án thiết kế nào có thể giảm số streams?

### Bài 19 — Multi-instance

Ba instances của một service đều mở db.orders.watch(). Có phải mỗi event chỉ được gửi cho một instance như Kafka consumer group không? Thiết kế cách tránh ba lần gửi email.

### Bài 20 — Transactional outbox

Một transaction đặt hàng cập nhật orders, inventory và chèn outbox event. Vì sao watch outbox có thể phản ánh business event tốt hơn watch mọi update trên orders?

### Bài 21 — Sự cố mất oplog

Consumer offline lâu khiến token rơi khỏi oplog. Viết runbook ngắn để khôi phục search index mà không tuyên bố dữ liệu đã đồng bộ hoàn toàn khi thực tế còn thiếu.

### Bài 22 — Tenant authorization

Một database-level stream nhận events của 100 tenants. Backend muốn đẩy qua WebSocket cho từng tenant. Những kiểm tra bảo mật nào phải thực hiện trước khi relay event?

## 28. Câu hỏi ôn tập

1. Change Streams giải quyết bài toán nào?
2. Vì sao Change Streams không chỉ là polling với interval ngắn?
3. MongoDB Change Streams khác tự tail oplog ra sao?
4. Change Streams có dùng trên standalone mongod không?
5. Single-node replica set đủ để làm gì và chưa kiểm thử được điều gì?
6. Với sharded cluster, Change Stream nên mở qua thành phần nào?
7. WiredTiger và pv1 có vai trò gì trong điều kiện triển khai?
8. MongoDB thông báo các thay đổi đã đạt trạng thái commit nào?
9. Watch cấp collection, database, deployment khác nhau ra sao?
10. Tại sao watch toàn deployment có rủi ro quyền truy cập lớn hơn?
11. MongoDB cần hai actions nào để watch một collection khi bật authorization?
12. Event field _id có phải là document ID không?
13. documentKey và resume token có mục đích khác nhau thế nào?
14. Tại sao update event thường chỉ có updateDescription?
15. fullDocument updateLookup có phải bản document tại đúng thời điểm event không?
16. Khi nào cần pre/post-images và điều kiện về version nào áp dụng?
17. Khi delete, tại sao không có post-image để lookup?
18. Vì sao không được $project bỏ event._id khỏi change stream pipeline?
19. resumeAfter và startAfter khác nhau thế nào ở invalidate?
20. Vì sao oplog window ảnh hưởng trực tiếp khả năng resume?
21. Checkpoint trước hay sau xử lý giúp giảm nguy cơ mất event? Trade-off?
22. Change Streams có bảo đảm exactly-once end-to-end cho downstream không?
23. Vì sao initial scan rồi mới mở watch có thể bỏ mất events?
24. Tại sao mỗi active change stream có thể ảnh hưởng connection pool?
25. Java Sync Driver và Spring Data Reactive có khác biệt gì về cách chờ events?
26. Khi nhiều instances cùng watch, MongoDB có tự chia event theo consumer group không?
27. Change Streams khác domain events trong transactional outbox ra sao?
28. Những metrics nào nên dùng để phát hiện consumer sắp mất khả năng resume?
29. Khi watch() không phát event, cần kiểm tra các điều kiện gì đầu tiên?
30. Nếu mất oplog history, tại sao không nên tự bắt đầu lại từ hiện tại?

## 29. Tổng kết

**Change Streams** là API Change Data Capture của MongoDB giúp ứng dụng phản ứng với những **thay đổi dữ liệu đã majority committed**, thay vì phải tự tail oplog hoặc polling liên tục.

~~~text
MongoDB replica set / sharded cluster
        |
        v
Insert / Update / Replace / Delete
        |
        v
Majority-committed change
        |
        v
watch() -> Change Stream Event
        |
        v
Consumer xử lý idempotent
        |
        v
Checkpoint resume token
        |
        v
Downstream cache / search / analytics
~~~

**Điều kiện triển khai bắt buộc và quan trọng nhất:**

1. **Topology:** replica set hoặc sharded cluster; standalone không hỗ trợ.
2. **Hạ tầng:** WiredTiger/pv1, phiên bản server/driver phù hợp, kết nối qua mongos khi sharded.
3. **Quyền:** find + changeStream trên scope cần thiết.
4. **Scope:** chọn collection/database/deployment theo trách nhiệm của consumer.
5. **Event contract:** hiểu operationType, updateDescription, fullDocument, documentKey và resume token.
6. **Lịch sử:** oplog còn đủ để resume sau downtime; không có khả năng replay vô hạn.
7. **Độ tin cậy:** checkpoint sau xử lý; chấp nhận replay, idempotency và phục hồi khi history không còn.
8. **Tài nguyên:** cursor/getMore dài hạn, connection pool, sharded fan-out và downstream backpressure.
9. **An toàn:** bảo vệ tenant, dữ liệu nhạy cảm và quyền truy cập ngoài database.
10. **Vận hành:** giám sát lag, checkpoint age, resume errors, restart và rebuild.

Không nên chọn Change Streams chỉ vì nó có chữ **real-time**. Câu hỏi đúng là: **“Ứng dụng muốn phản ứng với thay đổi nào, cần độ mới và độ bền thế nào, và sẽ phục hồi ra sao khi consumer bỏ lỡ dữ liệu?”**. Trả lời đủ những câu hỏi đó giúp xác định Change Streams có phù hợp hay cần kết hợp thêm outbox, broker, snapshots và reconciliation.

### Tài liệu chính thức

- [MongoDB Change Streams — tổng quan, availability, access control và resumability](https://www.mongodb.com/docs/manual/changestreams/).
- [MongoDB db.collection.watch()](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/) — mở stream, options, fullDocument và pre/post-images.
- [MongoDB db.watch()](https://www.mongodb.com/docs/manual/reference/method/db.watch/) — watch cấp database.
- [MongoDB $changeStream aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/) — semantics của change stream stage.
- [MongoDB Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — cấu trúc và operation types.
- [MongoDB Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog và lịch sử replication.
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — MongoCollection.watch(), MongoChangeStreamCursor và fullDocument.
- [Spring Data MongoDB — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html) — imperative MessageListenerContainer, ReactiveMongoTemplate và resume options.
- [MongoDB Production Notes for Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — connection pool sizing và sharded cluster considerations.

Change Streams hữu ích nhất khi được triển khai như **một thành phần trong kiến trúc đồng bộ dữ liệu có recovery**, không phải một vòng lặp đọc events chạy mãi mà không có checkpoint và idempotency. Khi các điều kiện topology, quyền, oplog retention và downstream reliability được chuẩn bị đúng, Change Streams là cách tự nhiên để xây các hệ thống phản ứng với thay đổi MongoDB gần thời gian thực.




