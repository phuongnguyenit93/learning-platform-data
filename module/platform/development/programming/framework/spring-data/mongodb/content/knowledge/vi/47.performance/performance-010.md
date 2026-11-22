# Document lớn, array không giới hạn và mô hình dữ liệu gây điểm nóng

## Mục tiêu học tập

Trong **Spring Data MongoDB**, mô hình dữ liệu quyết định không chỉ cách ánh xạ document thành entity Java mà còn cả lượng dữ liệu phải đọc, số lần cập nhật một document, kích thước index và mức độ phân tán tải ghi. Một truy vấn có index tốt vẫn có thể chậm nếu mỗi document quá lớn; thêm nhiều CPU hoặc chuyển sang `ReactiveMongoTemplate` cũng không giải quyết được tình trạng hàng nghìn request cùng ghi vào một document.

Sau bài này, bạn có thể:

- Nhận biết ba nguồn gây suy giảm hiệu năng: **document phình to**, **array tăng không giới hạn** và **điểm nóng (hotspot) khi nhiều thao tác tập trung vào một document, index range hoặc shard**.
- Lựa chọn giữa embedded document, collection riêng, bounded array, bucket, subset và counter phân mảnh theo yêu cầu truy cập.
- Viết thao tác `MongoTemplate`/repository để truy vấn theo trang, cập nhật nhỏ gọn và tránh tải lịch sử không cần thiết.
- Đọc dấu hiệu từ `explain("executionStats")`, kích thước BSON, chỉ số ứng dụng và phép thử tải để xác minh cải thiện.
- Hiểu ranh giới giữa tối ưu mô hình, index, transaction, sharding và reactive access.

Bối cảnh xuyên suốt là hệ thống quản lý đơn hàng: mỗi `Order` có trạng thái hiện tại, hàng nghìn sự kiện lịch sử, các ghi chú vận hành và một số lượt cập nhật đồng thời.

## 1. Document MongoDB lớn ảnh hưởng đến hệ thống như thế nào?

MongoDB lưu dữ liệu dạng **BSON document**. **Kích thước tối đa của một BSON document là 16 MiB**; giới hạn áp dụng cho **toàn bộ document**, gồm field, object lồng nhau và phần tử array. Đây là giới hạn cứng, nhưng chi phí vận hành thường xuất hiện **trước khi** chạm 16 MiB.

Khi một document lớn dần, ứng dụng có thể gặp:

1. **Đọc dư dữ liệu:** một màn hình chỉ cần `orderId`, `status` và `total` nhưng repository trả toàn bộ document, bao gồm lịch sử hàng MB; mạng, CPU giải mã BSON và ánh xạ entity phải xử lý phần dữ liệu không cần.
2. **Tăng chi phí cập nhật:** document và cấu trúc lưu trữ cần xử lý thay đổi của một đối tượng ngày càng lớn. Cập nhật một phần bằng `$set`/`$inc` thường hiệu quả hơn thay thế toàn bộ document bằng `save`, nhưng không loại bỏ áp lực từ document quá lớn.
3. **Bộ nhớ và cache bị chiếm dụng:** ít document lớn có thể cạnh tranh cache với nhiều document nhỏ thường xuyên truy cập; payload JSON trả về client còn có thể làm tăng GC của ứng dụng Java.
4. **Index multikey tăng kích thước:** index trên một trường nằm trong array có thể tạo nhiều khóa index từ một document; array càng dài, chi phí duy trì index và dung lượng index càng đáng kể.
5. **Khó sửa và di chuyển cấu trúc:** thao tác aggregation, cập nhật đồng thời, backfill hoặc chuyển dữ liệu lịch sử có thể chịu chi phí lớn hơn.

Không có một ngưỡng kích thước “đẹp” áp dụng cho mọi ứng dụng. Cần xem **phân bố kích thước document (p50/p95/p99), tần suất đọc/ghi, dữ liệu được trả về và mức độ tranh chấp**. Document vài chục KiB có thể ổn cho đọc nguyên khối ít lần, trong khi một document nhỏ nhưng bị cập nhật hàng nghìn lần mỗi giây vẫn có thể là điểm nóng.

### Ví dụ: một `Order` ôm toàn bộ lịch sử

```json
{
  "_id": "ORD-1042",
  "customerId": "C-15",
  "status": "SHIPPED",
  "total": 280000,
  "events": [
    { "at": "2026-01-15T08:00:00Z", "type": "CREATED", "note": "..." },
    { "at": "2026-01-15T08:12:00Z", "type": "PAID", "note": "..." }
  ],
  "operatorNotes": [
    { "at": "2026-01-15T08:20:00Z", "text": "..." }
  ]
}
```

Nếu `events` và `operatorNotes` chỉ tăng, một đơn hàng tồn tại lâu có thể tích lũy hàng trăm nghìn phần tử. API xem chi tiết đơn hàng, API thêm sự kiện và luồng kiểm toán lúc đó cạnh tranh trên cùng document.

## 2. Array không giới hạn: tiện khi bắt đầu, khó duy trì khi tăng trưởng

Nhúng một array vào document mang lại lợi ích thật: đọc nguyên đối tượng trong một lần query, cập nhật các field của document bằng thao tác atomic đơn document, và tránh nhiều lần truy cập collection. Nhưng lợi ích này phù hợp nhất khi **kích thước array có giới hạn và thường được truy cập cùng document cha**.

Một thiết kế dễ gặp:

```java
@Document("orders")
public class Order {
    @Id
    private String id;

    private String status;

    // Nguy cơ phình to nếu mọi sự kiện từ trước đến nay đều nằm ở đây.
    private List<OrderEvent> events = new ArrayList<>();
}
```

Và service ghi:

```java
Order order = mongoTemplate.findById(orderId, Order.class);
order.getEvents().add(newEvent);
mongoTemplate.save(order);
```

Cách này có hai vấn đề riêng:

- `findById`/`save` đi qua **toàn bộ entity**, nên lượng dữ liệu xử lý tăng theo số sự kiện; nếu hai request đọc cùng phiên bản, cách ghi lại entity có thể gây **lost update** nếu không có cơ chế kiểm soát đồng thời.
- Array không có giới hạn: không có gì ngăn document tăng đến mức tốn tài nguyên hoặc chạm giới hạn BSON.

Thay bằng một lệnh cập nhật nhỏ như `$push` tránh vòng đọc rồi ghi nguyên entity và tận dụng cập nhật atomic trên **một document**:

```java
Query byId = Query.query(Criteria.where("_id").is(orderId));
Update appendEvent = new Update().push("events", newEvent);

mongoTemplate.updateFirst(byId, appendEvent, Order.class);
```

Tuy vậy, **`$push` một mình không giải quyết array tăng vô hạn**. Nó chỉ cải thiện đường ghi so với tải và `save` toàn bộ entity, còn dung lượng lịch sử và tranh chấp trên document cha vẫn tích tụ.

### Dấu hiệu nên tách array

Cân nhắc tách array thành collection riêng khi có một hoặc nhiều đặc điểm:

- Số phần tử không có cận trên hữu hạn trong vòng đời đối tượng.
- Lịch sử hiếm khi được đọc cùng dữ liệu hiện tại, hoặc chỉ cần xem theo trang.
- Phần tử được thêm với tần suất cao từ nhiều request/worker.
- Cần index, tìm kiếm, lọc, lưu giữ và xóa từng phần tử độc lập.
- Giá trị array có thể làm document tiến gần giới hạn 16 MiB.
- Ứng dụng phải gửi hoặc ánh xạ cả array để hiển thị một số trường rất nhỏ.

Ngược lại, array chứa vài số điện thoại, một số cài đặt cố định, hoặc danh sách **tối đa** vài chục mục luôn được dùng cùng parent thường là ứng viên embedding tốt.

## 3. Điểm nóng không chỉ là document lớn

**Điểm nóng** là nơi quá nhiều thao tác tập trung vào một tài nguyên, khiến hiệu năng bị giới hạn bởi tài nguyên đó ngay cả khi cụm MongoDB còn nhiều máy và CPU tổng thể chưa đầy.

Có ít nhất ba dạng hotspot cần phân biệt:

| Dạng điểm nóng | Ví dụ | Biểu hiện điển hình |
| --- | --- | --- |
| **Document hot** | Mọi worker đều `$inc` bộ đếm tổng trên một document `campaign` | Nhiều cập nhật cùng document, tăng độ trễ ghi hoặc xung đột |
| **Index/range hot** | Ghi liên tục theo một khóa tăng đơn điệu | Các ghi tập trung vào một vùng khóa hoặc vùng dữ liệu đang hoạt động |
| **Shard hot** | Shard key chọn kém, dữ liệu mới chỉ ghi vào một shard | Một shard quá tải trong khi shard khác rảnh, tốc độ ghi không tăng khi mở rộng cụm |

Document nhỏ **vẫn có thể rất hot** nếu được cập nhật bởi nhiều luồng. Chẳng hạn:

```javascript
db.campaign_stats.updateOne(
  { _id: "CAMPAIGN-1" },
  { $inc: { totalViews: 1 } }
)
```

`$inc` atomic trên một document, giúp tránh mất cập nhật như cách đọc rồi ghi thủ công. Nhưng mọi lượt xem vẫn cạnh tranh tài nguyên cập nhật của **cùng một document**. Atomicity và khả năng mở rộng tải ghi là hai thuộc tính khác nhau.

Tương tự, sharding không tự giải quyết tranh chấp của một document: một document nằm trên một shard và các cập nhật của nó vẫn tập trung tại đó. Cần thay đổi mô hình ghi nếu một document đã trở thành nút cổ chai.

## 4. Đo nguyên nhân trước khi đổi schema

Hiệu năng MongoDB chịu ảnh hưởng của dữ liệu, truy vấn, index, phần cứng, network và tải cùng lúc. Không kết luận “chậm vì document lớn” chỉ từ tên collection hoặc độ dài của class Java.

### 4.1. Lấy mẫu kích thước BSON và số phần tử array

Trong `mongosh`, dùng `$bsonSize` để đo kích thước document:

```javascript
db.orders.aggregate([
  { $sample: { size: 500 } },
  {
    $project: {
      _id: 1,
      bsonBytes: { $bsonSize: "$$ROOT" },
      eventCount: { $size: { $ifNull: ["$events", []] } }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 20 }
])
```

Mẫu này hữu ích khi điều tra; **không bảo đảm phản ánh đầy đủ các document lớn hiếm gặp**. Với collection rất lớn, `$sample` và tính kích thước BSON vẫn tiêu tốn tài nguyên; thực hiện ở môi trường đo phù hợp, có giới hạn và đối chiếu với thống kê hệ thống.

Cần quan sát đồng thời: kích thước BSON, số phần tử array, kích thước index/collection, tỷ lệ đọc/ghi và số request chạm cùng `_id`. Nếu muốn đưa ra ngưỡng cảnh báo, nên dựa trên phân vị và tốc độ tăng theo thời gian.

### 4.2. Giải thích truy vấn bằng `explain`

Ví dụ API lấy các sự kiện gần nhất của một đơn hàng:

```javascript
db.order_events
  .find({ orderId: "ORD-1042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(50)
  .explain("executionStats")
```

Kiểm tra những thông tin sau trong plan của phiên bản MongoDB đang dùng:

- `nReturned`: số document thực sự trả về.
- `totalDocsExamined` và `totalKeysExamined`: lượng dữ liệu/khóa đã quét; tỷ lệ cao so với `nReturned` thường gợi ý query/index chưa phù hợp.
- `executionTimeMillis` và các stage liên quan: có scan, sort ngoài index hay stage tốn tài nguyên không.
- Kích thước payload thực tế trả về, độ trễ mạng và thời gian mapping Java — **không** thể suy ra đầy đủ chỉ từ `explain`.

Index hỗ trợ lọc và sort không làm một document 10 MiB trở nên rẻ để đọc nguyên khối; cần kết hợp phân tích execution plan với **projection** và mô hình dữ liệu.

### 4.3. Đo ở ứng dụng và trong cụm

Dùng metrics/tracing tại tầng API, `MongoTemplate` hoặc MongoDB driver để nhìn thấy:

- P50/P95/P99 độ trễ đọc, ghi, truy vấn lịch sử và cập nhật document hot.
- Kích thước response, thời gian serialize/deserialize BSON/JSON và GC của JVM.
- Số lần ghi, retry, optimistic-lock failure, timeout, write conflict.
- Tài nguyên MongoDB: CPU, I/O, cache, lock/queue, độ trễ đĩa và sự mất cân đối tải giữa các shard (nếu có).
- Query shape gây tải: `find`, `aggregate`, `updateOne`/`updateMany`, `findAndModify`.

Cần đo theo **request thực** và so sánh trước/sau với cùng dataset, cường độ tải, index và cấu hình nhất quán.

## 5. Mẫu 1 — Tách lịch sử sang collection riêng

Nếu màn hình thường chỉ cần trạng thái hiện tại và danh sách 20 sự kiện gần nhất, lưu toàn bộ lịch sử trong một document là dư thừa. Một thiết kế phổ biến:

```text
orders
  _id, customerId, status, total, updatedAt, ...

order_events
  _id, orderId, createdAt, type, actorId, payload, ...
```

Mỗi sự kiện trở thành một document độc lập. `orders` giữ dữ liệu current-state nhỏ gọn; `order_events` hỗ trợ ghi nối tiếp, lọc và phân trang. Thêm một sự kiện không khiến mảng `events` trong `orders` tăng mãi.

### 5.1. Entity và compound index trong Spring Data MongoDB

```java
@Document("order_events")
@CompoundIndex(
    name = "order_created_id_desc",
    def = "{ 'orderId': 1, 'createdAt': -1, '_id': -1 }")
public class OrderEvent {

    @Id
    private ObjectId id;

    private String orderId;
    private Instant createdAt;
    private String type;
    private String actorId;
    private String message;

    // Constructor, getters và setters được lược bỏ.
}
```

Index `{ orderId: 1, createdAt: -1, _id: -1 }` giúp lọc theo một `orderId` và lấy các sự kiện mới nhất theo thứ tự xác định. Thêm `_id` vào cuối thứ tự sort giúp phân trang ổn định khi nhiều sự kiện có cùng `createdAt`.

Để thực sự tạo index, cần cấu hình chiến lược quản lý index phù hợp: Spring Data MongoDB không nên được mặc định là đã tạo mọi index chỉ vì có annotation. Ở production, thường quản lý việc tạo index bằng migration hoặc script vận hành, có kiểm tra kết quả triển khai.

### 5.2. Đọc theo trang bằng keyset/cursor

Phân trang `skip` với offset lớn có thể phải đi qua nhiều bản ghi đã bỏ qua. Khi xem lịch sử dài, dùng **keyset pagination** theo `(createdAt, _id)` thường phù hợp hơn.

Trang đầu:

```java
Query firstPage = Query.query(
        Criteria.where("orderId").is(orderId))
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")))
    .limit(50);

List<OrderEvent> events =
        mongoTemplate.find(firstPage, OrderEvent.class);
```

Trang tiếp theo dựa trên phần tử cuối của trang trước:

```java
Criteria olderThanCursor = new Criteria().orOperator(
    Criteria.where("createdAt").lt(lastCreatedAt),
    new Criteria().andOperator(
        Criteria.where("createdAt").is(lastCreatedAt),
        Criteria.where("_id").lt(lastId))
);

Criteria filter = new Criteria().andOperator(
    Criteria.where("orderId").is(orderId),
    olderThanCursor
);

Query nextPage = Query.query(filter)
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")))
    .limit(50);

List<OrderEvent> next =
        mongoTemplate.find(nextPage, OrderEvent.class);
```

Ở đây `lastCreatedAt` và `lastId` được lấy từ document cuối của trang trước; `lastId` là `ObjectId` tương ứng field `_id`. Bộ lọc và thứ tự sort phải tương thích. Nếu nhiều sự kiện được chèn thêm trong lúc người dùng phân trang, trang theo cursor vẫn có hành vi rõ ràng hơn so với offset, nhưng **không mặc nhiên cung cấp một snapshot bất biến** của toàn bộ lịch sử.

### 5.3. Ghi sự kiện có cần transaction?

Hai thao tác thường là: cập nhật trạng thái hiện tại ở `orders` và chèn sự kiện vào `order_events`. Vì thuộc **hai document**, chúng không có atomicity chung nếu chỉ gọi hai lệnh nối tiếp.

Cần xác định yêu cầu nghiệp vụ:

- Nếu event là nhật ký cần nhất quán tức thì với current-state, cân nhắc **MongoDB transaction** với `MongoTransactionManager` và MongoDB deployment có hỗ trợ; đánh giá chi phí transaction cùng khả năng retry.
- Nếu hệ thống chấp nhận **eventual consistency**, dùng sự kiện làm nguồn sự thật hoặc một cơ chế phát sự kiện đáng tin cậy để cập nhật current-state/read model.
- Tránh tuyên bố hai lệnh độc lập tự động là “cùng thành công hoặc cùng thất bại”.

**Đổi lại:** thiết kế này cần thêm query để lấy lịch sử và có thể cần transaction/luồng đồng bộ dữ liệu, nhưng thời gian đọc current-state ít phụ thuộc vào độ dài lịch sử và việc ghi lịch sử không còn cập nhật cùng một document cha.

## 6. Mẫu 2 — Bounded array / subset pattern

Không phải array nào cũng cần collection riêng. Nếu màn hình chính chỉ hiển thị **50 sự kiện gần nhất**, có thể nhúng một **bản tóm tắt có giới hạn** vào `orders`, đồng thời lưu toàn bộ lịch sử trong `order_events` nếu cần.

```java
@Document("orders")
public class OrderSummary {

    @Id
    private String id;

    private String status;
    private List<EventPreview> recentEvents = new ArrayList<>();
}
```

Cập nhật giới hạn bằng `$push` + `$each` + `$slice`:

```java
Query byId = Query.query(Criteria.where("_id").is(orderId));

Update update = new Update()
    .push("recentEvents")
    .each(new EventPreview(eventTime, eventType))
    .slice(-50);

mongoTemplate.updateFirst(byId, update, OrderSummary.class);
```

`$slice: -50` giữ tối đa 50 phần tử **cuối** của array sau thao tác push. Đây là cách chặn kích thước array tăng vô hạn. Cần hiểu rằng:

- Giới hạn số phần tử **không đồng nghĩa** với giới hạn byte: mỗi `EventPreview` phải được thiết kế có kích thước được kiểm soát, tránh nhúng payload lớn.
- MongoDB chỉ lưu các phần tử còn lại trong array bounded; nếu đây là **nơi lưu duy nhất**, các phần tử cũ sẽ bị bỏ. Muốn giữ lịch sử, phải ghi sang collection riêng hoặc kho lưu phù hợp.
- Nhiều writer vẫn ghi vào **cùng document `OrderSummary`**, nên bounded array giải quyết kích thước nhưng **không tự xử lý document hotspot**.
- Thứ tự thêm không bảo đảm tương ứng với `eventTime` khi nhiều request đồng thời; nếu cần thứ tự theo thời gian nghiệp vụ, phải thiết kế và kiểm thử việc sắp xếp/ghi phù hợp.

**Subset pattern** có thể áp dụng cho sản phẩm hiển thị vài đánh giá nổi bật, cuộc hội thoại hiển thị một số tin nhắn gần nhất hoặc tài khoản lưu vài địa chỉ thường dùng. Hãy chọn ranh giới nhỏ, có ý nghĩa nghiệp vụ và đo được.

### Projection giúp đọc ít dữ liệu nhưng không giải quyết mọi vấn đề

Khi chưa thể đổi schema ngay, chỉ lấy các field cần thiết:

```java
Query query = Query.query(Criteria.where("_id").is(orderId));
query.fields().include("status").include("total");

Document summary = mongoTemplate.findOne(
    query, Document.class, "orders");
```

Trong trường hợp này, server trả về phần được projection thay vì toàn bộ array. Điều đó giúp giảm dữ liệu truyền đi và chi phí mapping ở client, nhưng **không xóa array khỏi storage, không giảm tranh chấp ghi và không loại bỏ giới hạn 16 MiB**. Với entity đầy đủ, projection thiếu field có thể khiến dữ liệu mapping không như mong muốn; cân nhắc DTO/read model thay vì ghi đè lại một entity chỉ được load một phần.

## 7. Mẫu 3 — Bucket pattern cho dữ liệu theo chuỗi thời gian

Một hệ thống có thể thu thập hàng triệu phép đo nhỏ (ví dụ cảm biến, log nghiệp vụ, số lượt truy cập). Nếu lưu **mỗi phép đo là một document**, số lượng document/index entry có thể lớn; nếu gom **tất cả phép đo vào một document**, lại quay về array vô hạn.

**Bucket pattern** gom một nhóm có kiểm soát vào từng document:

```json
{
  "_id": "device-18:2026-11-20T13:00:00Z:0",
  "deviceId": "device-18",
  "bucketStart": "2026-11-20T13:00:00Z",
  "count": 3,
  "measurements": [
    { "at": "2026-11-20T13:00:02Z", "value": 42 },
    { "at": "2026-11-20T13:00:14Z", "value": 43 },
    { "at": "2026-11-20T13:00:28Z", "value": 44 }
  ]
}
```

Quy tắc thiết kế thường dựa trên **giới hạn số phần tử/byte**, thời gian và partition key. Ví dụ tối đa 200 phép đo hoặc một khoảng thời gian ngắn mỗi bucket, tùy kích thước payload. Khi bucket đạt giới hạn, tạo bucket mới.

Lợi ích là đọc theo dải thời gian có thể giảm số document cần xử lý và giảm overhead từng phép đo. Nhưng nếu nhiều thiết bị hoặc worker cùng ghi vào **một bucket đang mở**, bucket đó vẫn hot. Trong hệ có ghi đồng thời lớn, cân nhắc nhiều bucket song song (ví dụ partition/bucket slot), batch ingest hoặc chiến lược khác; chốt bucket một cách an toàn để tránh vượt cận khi nhiều writer tranh nhau.

MongoDB còn có **time series collections** tối ưu lưu trữ và truy vấn dữ liệu đo có cấu trúc thời gian. Đây là lựa chọn nên đánh giá trước khi tự xây bucket cho telemetry thuần thời gian. Time series collection có khả năng cập nhật/xóa và quy tắc index khác collection thông thường; quyết định dựa trên API cần dùng và phiên bản MongoDB đang vận hành.

## 8. Mẫu 4 — Phân tán cập nhật bộ đếm nóng

Đối với một chiến dịch có hàng chục nghìn lượt xem mỗi giây, lưu tổng `viewCount` trong một document là một hotspot dù document rất nhỏ.

Có thể phân tán lượt ghi vào **N counter stripe**:

```text
campaign_counters
  { campaignId: "C1", slot: 0, views: 12345 }
  { campaignId: "C1", slot: 1, views: 12981 }
  { campaignId: "C1", slot: 2, views: 12015 }
  ...
  { campaignId: "C1", slot: 15, views: 11888 }
```

Mỗi request chọn một `slot` dựa trên hàm băm/nguồn phân phối phù hợp, rồi tăng tại document đó. Cần **unique compound index** trên `(campaignId, slot)` để mỗi stripe có một document duy nhất.

```java
int slot = ThreadLocalRandom.current().nextInt(16);

Query key = Query.query(
    Criteria.where("campaignId").is(campaignId)
            .and("slot").is(slot));

Update increment = new Update().inc("views", 1);

mongoTemplate.upsert(
    key, increment, "campaign_counters");
```

Tổng lượt xem là tổng `views` trên các stripe. Có thể tổng hợp bằng aggregation, hoặc tạo read model/materialized counter được cập nhật theo chu kỳ nếu màn hình yêu cầu truy vấn rất thường xuyên.

**Đánh đổi:** tăng số document và chi phí đọc tổng; một tổng đọc từ nhiều stripe không mặc nhiên là snapshot tại cùng một thời điểm. Nếu bài toán yêu cầu số thứ tự tăng liên tục, chính xác tuyệt đối cho từng sự kiện hoặc tính nhất quán tức thì giữa nhiều field, không thể coi striped counter là giải pháp thay thế trực tiếp nếu chưa thiết kế ràng buộc giao dịch.

Với tải ghi không lớn, **một `$inc` đơn giản** có thể vẫn là phương án tốt nhất. Stripe chỉ có giá trị khi đo đạc chứng minh document hot là nút cổ chai.

## 9. Các chiến lược khác: outlier và tách dữ liệu lạnh

Không phải mọi khách hàng, hội thoại hoặc đơn hàng đều có kích thước giống nhau. Đa số có vài sự kiện nhưng một số ít có hàng trăm nghìn sự kiện. **Outlier pattern** giữ trường hợp phổ biến đơn giản và xử lý đối tượng bất thường bằng collection phụ.

Ví dụ, `orders` giữ tối đa 50 ghi chú gần nhất và trường `hasArchivedNotes`; khi vượt ngưỡng, các ghi chú lâu hơn chuyển sang `order_notes`. Tầng service có thể:

1. Tải thông tin tổng quan từ `orders`.
2. Nếu người dùng mở “Xem lịch sử đầy đủ”, truy vấn `order_notes` theo `orderId` và cursor.
3. Không gộp toàn bộ lịch sử lại vào `orders` trong mỗi lần cập nhật.

Nếu payload là tệp nhị phân hoặc đối tượng lớn, không nhúng trực tiếp vào document chỉ để tiết kiệm một liên kết. Có thể lưu metadata và tham chiếu đến **GridFS** hoặc object storage, tùy yêu cầu quản lý file. GridFS là cơ chế lưu file lớn, không thay thế cho mô hình event/history có thể truy vấn riêng lẻ.

Một chính sách **retention/archival** cũng có thể giúp giới hạn working set: dữ liệu cũ được chuyển sang nơi phù hợp hoặc xóa theo thời hạn được cho phép. TTL index hữu ích cho các document có thời điểm hết hạn, nhưng không tự xóa từng phần tử bên trong một array embedded và không thay thế chính sách lưu trữ nghiệp vụ.

## 10. Sharding và mô hình dữ liệu: phân phối được tải hay chỉ chuyển điểm nóng?

Khi collection được sharding, lựa chọn **shard key** ảnh hưởng trực tiếp đến cách phân bố document và tải ghi. Một số sai lầm phổ biến:

- Chọn shard key **tăng đơn điệu** khi luồng ghi chủ yếu thêm dữ liệu mới theo thời gian: vùng khóa mới có thể tập trung nhiều ghi trên một shard.
- Chọn shard key có **quá ít giá trị phân biệt**: một số tenant/nhóm lớn có thể chiếm phần lớn tải.
- Dùng `tenantId` hoặc `orderId` theo trực giác mà không phân tích phân bố lưu lượng, kích thước từng nhóm và truy vấn truy cập.
- Cho rằng thêm shard sẽ tự phân tán cập nhật của **một document**; document đó vẫn phải nằm ở một shard.

Một **hashed shard key** có thể giúp phân bố các insert theo giá trị khóa có độ phân biệt tốt, nhưng làm thay đổi khả năng định tuyến và chi phí truy vấn theo khoảng. Hashing không tự giải quyết trường hợp nhiều request mang **cùng một giá trị shard key**, và cũng không thay thế việc chia nhỏ một document hot.

Khi chọn shard key, hãy khảo sát:

- Phân bố write/read theo key, mức độ skew giữa khách hàng lớn và nhỏ.
- Query chính có dùng điều kiện shard key để nhắm đúng shard không.
- Dải thời gian truy vấn, chiến lược sort/index và nhu cầu pagination.
- Khả năng dữ liệu và tải tăng trong tương lai, không chỉ số document hiện tại.

**Mô hình logical data và shard key cần được thiết kế cùng nhau.** Ví dụ lưu sự kiện thành `order_events` giúp phân tán dữ liệu thành nhiều document, nhưng nếu sharding theo một khóa không phù hợp thì hotspot vẫn có thể xuất hiện ở mức shard.

## 11. Index, mapping và thao tác cập nhật trong Spring Data MongoDB

### 11.1. Index đúng truy vấn, tránh nhân số entry không cần thiết

Một array sự kiện embedded có thể được index theo field con, ví dụ `events.type`. MongoDB sử dụng **multikey index** cho giá trị array; index có thể hỗ trợ truy vấn nhưng mỗi phần tử/giá trị có khả năng góp thêm index keys. Khi array tăng, bộ index cũng có xu hướng tăng.

Khi tách thành collection `order_events`, ta có thể tạo compound index tập trung vào mẫu truy vấn:

- Theo đơn hàng và thời gian: `{ orderId: 1, createdAt: -1, _id: -1 }`.
- Theo loại sự kiện trong một đơn hàng: cân nhắc `{ orderId: 1, type: 1, createdAt: -1 }` **nếu** truy vấn tương ứng đủ thường xuyên để bù chi phí ghi/index.

Đừng tạo nhiều index chỉ vì các query có thể có trong tương lai. Mỗi index mới làm tăng chi phí ghi và tốn disk/cache.

### 11.2. Chọn `updateFirst`/`findAndModify` thay vì `save` khi phù hợp

Khi chỉ đổi trạng thái, hãy cập nhật field cần thay đổi:

```java
Query q = Query.query(Criteria.where("_id").is(orderId));

Update u = new Update()
    .set("status", "SHIPPED")
    .currentDate("updatedAt");

mongoTemplate.updateFirst(q, u, "orders");
```

Điều này tránh đọc rồi ghi lại toàn bộ entity chỉ để đổi một field. Nếu cần điều kiện chuyển trạng thái hợp lệ, thêm trạng thái cũ vào filter và kiểm tra `matchedCount`:

```java
Query transition = Query.query(
    Criteria.where("_id").is(orderId)
            .and("status").is("PAID"));

Update ship = new Update().set("status", "SHIPPED");

UpdateResult result =
    mongoTemplate.updateFirst(transition, ship, "orders");

if (result.getMatchedCount() == 0) {
    // Không tồn tại hoặc trạng thái đã thay đổi:
    // xử lý xung đột theo quy tắc nghiệp vụ.
}
```

Cách này dùng điều kiện ngay trong lệnh cập nhật để kiểm soát cạnh tranh trên một document. Nếu dùng entity có `@Version` và `save`, Spring Data có cơ chế optimistic locking theo version khi được cấu hình đúng; xung đột cần được xử lý rõ ràng. Tuy vậy, nhiều lần xung đột/retry cũng có thể là **dấu hiệu thiết kế đã dồn quá nhiều ghi vào cùng document**.

### 11.3. Projection và API đọc riêng

Không nên áp dụng `findAll()` rồi lọc lịch sử trong Java, cũng không nên luôn trả entity lưu trữ nguyên vẹn cho endpoint danh sách. Dùng projection/DTO riêng cho use case:

```java
Query listQuery = Query.query(
    Criteria.where("customerId").is(customerId))
    .with(Sort.by(Sort.Direction.DESC, "updatedAt"))
    .limit(20);

listQuery.fields()
    .include("_id")
    .include("status")
    .include("total")
    .include("updatedAt");

List<Document> summaries =
    mongoTemplate.find(listQuery, Document.class, "orders");
```

Index phù hợp với filter/sort vẫn cần được đánh giá bằng `explain`. Nếu collection rất lớn và khách hàng có nhiều đơn, cân nhắc keyset pagination cho danh sách đơn hàng giống cách làm với `order_events`.

### 11.4. Reactive không tự sửa schema

`ReactiveMongoTemplate` và reactive repository phù hợp cho xử lý I/O bất đồng bộ, backpressure và phục vụ nhiều request mà không chặn thread trong lúc chờ I/O. Tuy nhiên, một truy vấn tải document lớn, array không giới hạn hoặc một chuỗi ghi liên tục vào document hot vẫn tạo tải tương tự ở phía MongoDB. Điều chỉnh concurrency có thể giới hạn áp lực tức thời, nhưng **cải thiện cấu trúc dữ liệu và mẫu truy cập** mới giải quyết gốc vấn đề.

## 12. Chọn mô hình theo yêu cầu nghiệp vụ

| Đặc điểm dữ liệu và truy cập | Mô hình nên cân nhắc | Đánh đổi cần chấp nhận |
| --- | --- | --- |
| Số phần tử ít, có giới hạn, luôn đọc cùng cha | Embedded subdocuments | Parent cập nhật cùng nhau |
| Lịch sử tăng mãi, phải phân trang hoặc lọc độc lập | Reference và collection sự kiện riêng | Có thêm query/khả năng cần transaction |
| Chỉ cần 20–50 phần tử mới nhất trên trang chính | Bounded array hoặc subset | Giới hạn payload, có thể cần bản lưu lịch sử riêng |
| Nhiều phép đo nhỏ theo thời gian | Bucket có giới hạn hoặc time series collection | Thiết kế bucket/khả năng cập nhật và index |
| Hầu hết document nhỏ, một số ít cực lớn | Outlier pattern, archive/cold data | Có thêm đường đọc cho dữ liệu ngoại lệ |
| Một bộ đếm chịu lượng cập nhật cực cao | Striped/distributed counter | Tổng hợp có chi phí và vấn đề nhất quán |
| Ghi phân bố không đều giữa các shard | Xem lại shard key và phân bố workload | Query targeting và migration/resharding phức tạp |

Không có mẫu nào tốt nhất cho mọi hệ thống. Quyết định chủ yếu dựa trên **giới hạn tăng trưởng**, cách đọc thông dụng, phân bố ghi, nhu cầu nhất quán và số liệu đo đạc.

## 13. Quy trình cải thiện hiệu năng có kiểm chứng

Một quy trình thực hành cho `orders` đang chậm:

1. **Tái hiện:** tạo dataset phản ánh phân bố kích thước thật (đơn thường, đơn có rất nhiều events), traffic ghi đồng thời và các truy vấn chính.
2. **Đo baseline:** p95/p99 endpoint, bytes trả về, `$bsonSize`, độ dài array, `explain("executionStats")`, số conflict/retry và tài nguyên server.
3. **Tách nguyên nhân:** phân biệt query thiếu index, document quá lớn, ứng dụng mapping dư dữ liệu, và hotspot từ nhiều writer cùng `_id`.
4. **Áp dụng thay đổi nhỏ, có mục tiêu:** projection nếu chỉ đọc dư; `$set`/`$push` nếu đang `save` nguyên entity; bounded array nếu dữ liệu có thể giới hạn; collection lịch sử nếu dữ liệu tăng vô hạn; stripe nếu một counter hot.
5. **Migrate an toàn:** chuyển dữ liệu lịch sử, tạo index cần thiết, điều chỉnh đường ghi/đọc, có cách kiểm tra số sự kiện trước và sau. Nếu chạy song song hai mô hình một thời gian, phải xác định nguồn dữ liệu chuẩn và quy tắc đồng bộ.
6. **Kiểm tra chức năng:** số sự kiện không mất/nhân đôi, phân trang ổn định, trạng thái đơn hàng chính xác, retry không gây lỗi nghiệp vụ, quyền truy cập dữ liệu giữ nguyên.
7. **Kiểm tra tải sau thay đổi:** cùng workload, so sánh latency, throughput, bytes/network, cache, index size và kết quả query plan. Theo dõi trường hợp ngoại lệ chứ không chỉ trung bình.
8. **Theo dõi sau triển khai:** phát hiện array lại tăng không giới hạn, queue/write conflicts và shard imbalance mới.

Ví dụ tiêu chí nghiệm thu **do nhóm dự án tự đặt**, không phải giới hạn chung của MongoDB: tài liệu `orders` p99 không vượt ngưỡng kích thước đã thống nhất; `recentEvents` tối đa 50 mục; endpoint danh sách không trả lịch sử; truy vấn 50 sự kiện gần nhất dùng index mong đợi; p95 giảm trong cùng workload mà không tăng bất thường tỷ lệ lỗi.

### Những câu hỏi cần trả lời khi review schema

- Array này có giới hạn hữu hạn không? Giới hạn được **cưỡng chế ở đâu**, kể cả khi xử lý song song?
- Ứng dụng cần toàn bộ array cùng parent hay chỉ một tập con mới nhất?
- Nếu document tăng từ 10 đến 100.000 phần tử, query và update nào thay đổi độ phức tạp?
- Có bao nhiêu tác vụ đồng thời ghi vào **cùng một `_id`**?
- Index có phát sinh quá nhiều entry từ array hoặc ghi liên tục theo một vùng khóa?
- Transaction hoặc eventual consistency được lựa chọn có đáp ứng yêu cầu nghiệp vụ không?
- Đã đo hiệu năng trên dữ liệu có phân bố sát thực tế chưa?

## 14. Bài tập tự thực hành

**Tình huống:** API xử lý đơn hàng lưu `Order` với 200.000 sự kiện trong `events`. Mỗi cập nhật trạng thái gọi `findById`, thêm event vào list rồi `save`. Trang danh sách chỉ hiển thị `id`, `status` và `total`; một số đơn hàng cùng lúc nhận hàng trăm cập nhật từ các worker.

Hãy thử lần lượt:

1. Viết query chỉ đọc các field cần cho trang danh sách; dùng `explain` và đo kích thước response.
2. Chuyển lịch sử sang `order_events` có compound index phù hợp; phân trang lịch sử mới nhất bằng cursor.
3. Giữ tối đa 20 `recentEvents` trong `orders` cho màn hình chi tiết nếu thực sự cần; thiết kế cách duy trì lịch sử đầy đủ.
4. Thay `save` cả entity bằng `updateFirst` với điều kiện chuyển trạng thái; đo số conflict khi tăng concurrency.
5. Chạy tải với số lượng đơn hàng khác nhau, đặc biệt trường hợp **100 worker cùng cập nhật một order**. Phân biệt throughput của hệ thống tổng thể với throughput của một document hot.
6. Lập bảng đo trước/sau: p95/p99, bytes/response, số document examined, document BSON size và số lỗi cập nhật.

Câu hỏi kết thúc: **tại sao một index tốt không cứu được luồng `save` nguyên document chứa 200.000 sự kiện?** Vì index chủ yếu giúp tìm document; nó không loại bỏ chi phí đọc, mapping, truyền dữ liệu và ghi lại trạng thái của một đối tượng quá lớn.

## Ghi nhớ

- **Giới hạn 16 MiB** là trần cứng cho một BSON document, nhưng cần tối ưu trước khi đến trần.
- **Array vô hạn** thường là dấu hiệu phải tách dữ liệu lịch sử thành collection riêng; chỉ dùng embedded khi phạm vi tăng trưởng được kiểm soát.
- **Bounded array** giảm kích thước nhưng không xóa tranh chấp ghi nếu nhiều luồng tiếp tục cập nhật cùng document.
- **Hot document, hot index range và hot shard** là những vấn đề khác nhau; phải đo đúng loại mới chọn đúng giải pháp.
- Trong Spring Data MongoDB, ưu tiên **projection, update theo field, truy vấn theo cursor và index theo query thực tế**; tránh `findById + save` toàn entity cho những thay đổi nhỏ.
- Chọn **reference, subset, bucket, outlier, striped counter hoặc time series collection** theo mẫu đọc/ghi và mức nhất quán cần thiết.
- Mọi thay đổi schema cần có kế hoạch migration, kiểm thử tính đúng đắn và đo hiệu năng trên workload có ý nghĩa.

