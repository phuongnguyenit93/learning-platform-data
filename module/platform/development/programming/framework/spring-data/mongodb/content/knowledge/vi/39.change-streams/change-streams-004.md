# ChangeStreamOptions, bộ lọc pipeline và kiểu dữ liệu sự kiện

> **Chương:** Change stream  
> **Module:** `SPRING_DATA_MONGODB`

Một ứng dụng đặt hàng muốn cập nhật bảng điều khiển khi đơn mới được tạo, khi trạng thái chuyển từ `NEW` sang `PAID`, hoặc khi một đơn bị xóa. Thay vì liên tục hỏi MongoDB “có gì mới?” bằng polling, ứng dụng có thể mở **change stream** để nhận các sự kiện thay đổi từ collection, database hoặc deployment được hỗ trợ.

Trong Spring Data MongoDB, `ChangeStreamOptions` điều khiển **những sự kiện nào được trả ra, có tra cứu toàn bộ document sau update không, và bắt đầu đọc lại từ đâu**. Kết quả thường là `ChangeStreamEvent<T>`: wrapper chứa thông tin thao tác, resume token, thời điểm và phần dữ liệu được convert sang loại `T`. Sự kiện MongoDB không phải chính document nghiệp vụ; phải phân biệt `fullDocument`, `documentKey` và `updateDescription` để tránh xử lý sai các thao tác `update` và `delete`.

Bài này thuộc module `SPRING_DATA_MONGODB`, nơi ta kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository, thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Phạm vi trực tiếp là **`ChangeStreamOptions`, pipeline filter và kiểu dữ liệu của sự kiện**, kèm ví dụ consumer có checkpoint/recovery và kiểm thử.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích sự khác nhau giữa **MongoDB document** và **change event envelope**.
2. Đọc cấu trúc `_id`/resume token, `operationType`, `ns`, `documentKey`, `fullDocument`, `updateDescription` và `clusterTime`.
3. Tạo `ChangeStreamOptions` bằng `builder()`, `filter(Aggregation)` hoặc `filter(Document...)`, `returnFullDocumentOnUpdate()` và các lựa chọn resume.
4. Viết pipeline `$match` theo `operationType` và `fullDocument` mà không vô tình loại các event không có body.
5. Giải thích vì sao không được loại bỏ/sửa `_id` (resume token) trong pipeline.
6. Dùng `ReactiveMongoTemplate`/fluent `changeStream(...).listen()` để lấy `Flux<ChangeStreamEvent<T>>`; nhận biết lựa chọn imperative listener container.
7. Phân biệt `getBody()`, `getBodyBeforeChange()`, `getRaw()` và `getResumeToken()`, nhất là khi update/delete không có full document.
8. Hiểu `resumeAfter`, `startAfter` và `resumeAt`, giới hạn oplog và yêu cầu giữ pipeline/options ổn định khi resume.
9. Thiết kế checkpoint sau khi xử lý, idempotency, backpressure và xử lý invalidation/consumer failure.
10. Viết integration test trên replica set, xác minh bộ lọc, loại event, token và mapping mà không dựa trên sleep cố định.

## 2. Điều kiện để dùng change streams

MongoDB change streams chỉ hoạt động trên **replica set hoặc sharded cluster được hỗ trợ**; standalone MongoDB thông thường không thể cung cấp đầy đủ cơ chế này. Ứng dụng cần driver/Spring Data tương thích, xác thực có quyền watch/read phù hợp, kết nối được topology và **một consumer sống đủ lâu để duy trì cursor**.

```text
MongoDB replica set / sharded cluster
             |
             | committed changes
             v
       change stream cursor
             |
             | event envelope + resume token
             v
   Spring Data ChangeStreamEvent<T>
             |
             +-- operationType / documentKey
             +-- body or raw updateDescription
             +-- resumeToken / clusterTime
             |
             v
    Consumer -> business processing
             |
             v
       Persist checkpoint
```

Change streams không phải message broker độc lập. Cần tính đến **giới hạn lưu trữ lịch sử trong oplog**, lỗi mạng, election, consumer chậm, duplicate delivery sau resume và sự kiện làm stream mất hiệu lực. Không coi việc mở cursor là bảo đảm end-to-end “exactly once”.

### 2.1. Scope của stream

| Scope | Điều đang theo dõi | Kiểu payload nên chọn |
| --- | --- | --- |
| Collection | Các thay đổi trong một collection, ví dụ `orders` | `OrderDocument` nếu toàn bộ event body có cùng schema |
| Database | Nhiều collection thuộc một database | `org.bson.Document` hoặc envelope phân loại theo namespace |
| Deployment/cluster | Nhiều database/collection nếu API và quyền hỗ trợ | Raw document + routing theo `ns`, không ép mọi collection về một entity |

Một stream ở phạm vi database không đảm bảo mọi document đều tương thích với entity `OrderDocument`. Khi các collection có schema khác nhau, dùng `Document` cho raw body hoặc tạo router dựa trên `getCollectionName()` rồi convert có chủ đích.

### 2.2. Khi nào nên dùng change stream?

- Đồng bộ một read model/search index sau các thay đổi MongoDB.
- Cập nhật dashboard theo các event mới khi UX chấp nhận eventual consistency.
- Kích hoạt downstream processing idempotent theo `operationId`/resume token.
- Ghi nhận thay đổi dữ liệu để audit/monitoring khi đã thiết kế quyền, dữ liệu và retention phù hợp.

Không dùng change streams thay thế một transaction nếu hai thao tác phải **commit atomically**. Không dùng nó làm duy nhất nguồn sự thật cho các sự kiện trước khi được triển khai/resume đúng; nếu nghiệp vụ bắt buộc không mất sự kiện vượt thời gian oplog, cần kiến trúc bền vững hơn như transactional outbox hoặc replay/snapshot strategy.

## 3. Dữ liệu mẫu: đơn hàng có trạng thái

File `OrderDocument.java`:

```java
package com.example.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String status,
    long totalMinor,
    Instant updatedAt
) {}
```

Một document BSON:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  status: "NEW",
  totalMinor: NumberLong(50000),
  updatedAt: ISODate("2026-11-20T02:00:00Z")
}
```

Trong các ví dụ, ID có prefix `ORD-` để dễ nhận diện. `tenantId` chỉ được dùng để minh họa bộ lọc; phân quyền phải đến từ authentication/application policy chứ không từ một chuỗi tenant do client tự khai báo.

## 4. Một change event không phải một OrderDocument

Ví dụ sự kiện insert ở dạng BSON/JSON minh họa:

```javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "insert",
  clusterTime: Timestamp( /* server timestamp */ ),
  ns: { db: "shop", coll: "orders" },
  documentKey: { _id: "ORD-101" },
  fullDocument: {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    status: "NEW",
    totalMinor: NumberLong(50000)
  }
}
```

Đây là **cấu trúc minh họa**, không phải lệnh mongosh có thể thực thi nguyên xi; trường và định dạng cụ thể có thể khác theo MongoDB version, operation, sharding và tuỳ chọn stream.

### 4.1. Các field quan trọng

| Field của change event | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `_id` | **Resume token** opaque, nhận diện vị trí trong stream | Không phải `_id` của đơn hàng; không tự sửa/cắt |
| `operationType` | `insert`, `update`, `replace`, `delete`, `invalidate` và các loại khác | Cần xử lý theo loại; event không nhất thiết có body |
| `ns.db` / `ns.coll` | Namespace phát sinh thao tác | Dùng để route nếu watch scope rộng |
| `documentKey` | Khóa nhận diện document bị thay đổi, thường có `_id` | Cần cho delete vì không có `fullDocument` mặc định |
| `fullDocument` | Document hoàn chỉnh khi có | Có thể **vắng mặt/null**, nhất là update/delete |
| `updateDescription` | Delta của update: field đổi, field xóa, mảng bị cắt, ... | Chỉ có ý nghĩa cho update tương ứng |
| `clusterTime` | Thời điểm logic BSON timestamp của sự kiện | Không phải đồng hồ wall-clock của thiết bị người dùng |
| `wallTime` | Wall-clock time nếu server/version cung cấp | Không dùng thay resume token |
| `fullDocumentBeforeChange` | Pre-image khi đã bật/cấu hình và còn dữ liệu | Không có mặc định |

### 4.2. Hai loại “_id”

```text
event._id                    -> RESUME TOKEN của change stream
event.documentKey._id        -> ID của document bị thay đổi
event.fullDocument._id       -> ID trong document khi fullDocument có mặt
```

Nhầm hai giá trị này là lỗi phổ biến. Không lấy `event._id` rồi dùng `repository.findById(...)` để tìm đơn hàng; token không phải business key. Ngược lại, không lấy `documentKey._id` để làm resume token: nó không xác định vị trí sự kiện và không thể truyền cho `resumeAfter(...)`.

### 4.3. Các loại sự kiện thường gặp

| Operation | `fullDocument` mặc định | `documentKey` | `updateDescription` |
| --- | --- | --- | --- |
| `insert` | Thường có document vừa insert | Có | Không |
| `replace` | Thường có document thay thế | Có | Không phải kiểu update-delta |
| `update` | Mặc định thường **không có**; có thể dùng update lookup | Có | Có delta |
| `delete` | Không có full document sau delete | Có | Không |
| `invalidate` | Không có document nghiệp vụ | Không phải document key thông thường | Không |
| DDL/expanded events | Phụ thuộc loại sự kiện/option/version | Phụ thuộc | Phụ thuộc |

Không viết một handler ép `event.getBody()` phải khác null cho **mọi** event. Điều đó sẽ làm rơi hoặc gây NullPointerException với delete/update không có lookup.

## 5. update event: nhìn delta trước khi tra cứu full document

Ví dụ update:

```javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { status: "PAID" } }
)
```

Envelope update thường chứa:

```javascript
{
  _id: { _data: "<another-opaque-token>" },
  operationType: "update",
  ns: { db: "shop", coll: "orders" },
  documentKey: { _id: "ORD-101" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: [],
    truncatedArrays: []
  }
  // fullDocument có thể vắng mặt nếu không bật updateLookup.
}
```

Nếu consumer chỉ cần phát tín hiệu “`status` được set thành `PAID`”, `updateDescription.updatedFields.status` có thể đủ mà không cần tra cứu thêm nguyên document. Nhưng khi update là pipeline/replace, MongoDB có thể phát biểu diễn khác; nếu yêu cầu phát hiện **mọi** thay đổi trạng thái, cần cân nhắc cả `replace`/`insert` và quy tắc business riêng.

### 5.1. Không suy ra mọi update đều có status

Một update khác:

```javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { updatedAt: new Date() } }
)
```

`updateDescription.updatedFields` ở đây có thể không chứa `status`. Nếu lọc sự kiện bằng `operationType="update"` rồi luôn đọc `updatedFields.status` và coi null là “hủy đơn”, đó là lỗi domain logic.

### 5.2. updatedFields không phải snapshot

`updateDescription.updatedFields` chỉ phản ánh các thay đổi do **một lệnh cập nhật**, không phải toàn bộ document. Nó không chứa các field không đổi như `tenantId` nếu lệnh chỉ set `status`. Vì vậy một bộ lọc kiểu `fullDocument.tenantId` và một bộ lọc kiểu `updateDescription.updatedFields.status` có semantics khác nhau; không thay thế lẫn nhau tùy tiện.

## 6. ChangeStreamOptions: một đối tượng cấu hình cho stream

Trong Spring Data MongoDB, `org.springframework.data.mongodb.core.ChangeStreamOptions` tập hợp các tuỳ chọn truyền tới MongoDB driver khi tạo cursor. Ta dùng `ChangeStreamOptions.builder()`:

```java
import org.springframework.data.mongodb.core.ChangeStreamOptions;

ChangeStreamOptions options =
    ChangeStreamOptions.builder()
        .returnFullDocumentOnUpdate()
        .build();
```

Hoặc nếu không muốn thay đổi mặc định:

```java
ChangeStreamOptions options = ChangeStreamOptions.empty();
```

Builder thiết lập **cách stream hoạt động**, không phải một công cụ lưu trạng thái consumer. Mỗi lần restart, ứng dụng vẫn phải tải checkpoint bền vững rồi chọn offset/resume token phù hợp.

### 6.1. Những lựa chọn nên biết

| Phương thức builder | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `filter(Aggregation)` | Áp pipeline aggregation sau change-stream stage | Mapping field qua Spring Data có quy tắc riêng |
| `filter(Document...)` | Gửi các pipeline stages BSON thô | Dễ kiểm soát field envelope, không qua domain mapping tương đương |
| `returnFullDocumentOnUpdate()` | Yêu cầu `FullDocument.UPDATE_LOOKUP` cho update | Tra cứu document hiện tại, không đảm bảo snapshot đúng thời điểm |
| `fullDocumentLookup(FullDocument)` | Chọn policy full document ở API driver | Semantics phụ thuộc enum và MongoDB version |
| `fullDocumentBeforeChangeLookup(FullDocumentBeforeChange)` | Chọn chính sách pre-image | Cần cấu hình pre-images trên server |
| `returnFullDocumentBeforeChange()` | Yêu cầu pre-image khi có | Không tự làm DB lưu lịch sử quá khứ |
| `resumeAfter(BsonValue)` / `resumeToken(BsonValue)` | Tiếp tục sau một token hợp lệ | Dùng khi stream bị gián đoạn, không dùng sau invalidate |
| `startAfter(BsonValue)` | Tạo stream sau token, kể cả loại invalidate trong trường hợp hỗ trợ | Không mặc định thay `resumeAfter` ở mọi ca |
| `resumeAt(Instant)` / `resumeAt(BsonTimestamp)` | Bắt đầu từ thời điểm/cluster time | Giới hạn oplog; `BsonTimestamp` chính xác hơn `Instant` |
| `collation(Collation)` | Quy tắc collation của pipeline hỗ trợ | Không thay metadata token hoặc logic xử lý sự kiện |
| `showExpandedEvents(boolean)` | Yêu cầu thêm các loại event mở rộng khi server hỗ trợ | Tương thích phiên bản; kiểm tra Spring Data/driver cụ thể |

Không kết hợp `resumeAfter`, `startAfter` và `resumeAt` một cách mâu thuẫn: ở cấp MongoDB change stream, các chế độ offset này có những quy tắc **loại trừ nhau**.

### 6.2. Config tối thiểu cho trạng thái đơn hàng

```java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(
        new Document("$match",
            new Document("operationType",
                new Document("$in",
                    List.of("insert", "update", "replace"))))
    )
    .returnFullDocumentOnUpdate()
    .build();
```

Lệnh `filter(Document...)` ở đây nhận một stage `$match`. Nó không lọc event `delete`, `drop`, `rename` hoặc `invalidate` ra khỏi **pipeline kết quả** khi filter loại chúng; tuy nhiên các thao tác làm mất hiệu lực stream vẫn có thể khiến cursor đóng/lỗi theo semantics của MongoDB. Không dùng pipeline lọc để “ngăn một collection bị drop”.

### 6.3. Chọn fullDocument có thể làm thêm công việc đọc

`returnFullDocumentOnUpdate()` dùng `FullDocument.UPDATE_LOOKUP` để server tìm document tương ứng trong collection. Điều này hữu ích khi consumer muốn entity đầy đủ; nhưng có chi phí và không phải một snapshot bất biến của thời điểm update.

Nếu use case chỉ cần `documentKey` cùng delta `updateDescription`, có thể **không bật update lookup**. Nếu bật, cần đo:

- Tần suất update events.
- Document size và chi phí mạng.
- Số lượng full-document lookups.
- Trường hợp entity bị xóa hoặc thay tiếp trước khi lookup hoàn thành.
- Ảnh hưởng tới độ trễ consumer và memory/backpressure.

Không cho rằng “event update đã xảy ra” đồng nghĩa “`getBody()` luôn khác null” kể cả khi dùng update lookup.

## 7. Lọc pipeline: match theo operationType

Change stream nhận một pipeline **sau `$changeStream` stage** do MongoDB/driver tạo. Các stage được phép dùng có những giới hạn riêng; lựa chọn an toàn phổ biến là `$match` rồi (nếu thật cần) một phép chiếu không phá resume token.

Ví dụ MongoDB raw:

```javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace"]
      }
    }
  }
], {
  fullDocument: "updateLookup"
})
```

Tương ứng với Spring Data `ChangeStreamOptions` raw `Document`:

```java
Document matchTypes = new Document("$match",
    new Document("operationType",
        new Document("$in",
            List.of("insert", "update", "replace"))));

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(matchTypes)
    .returnFullDocumentOnUpdate()
    .build();
```

**Tác dụng:** chỉ các operation types nằm trong danh sách mới được phát tới consumer qua nhánh pipeline này. Không nên thêm `delete` vào danh sách rồi dùng handler duy nhất yêu cầu `body != null`.

### 7.1. Chỉ nhận insert

```java
ChangeStreamOptions insertOnly = ChangeStreamOptions.builder()
    .filter(new Document("$match",
        new Document("operationType", "insert")))
    .build();
```

Đây là trường hợp có thể không cần update lookup. Với insert, `fullDocument` thường có sẵn. Nhưng event lớn, mapping không tương thích hoặc pipeline sửa projection vẫn có thể gây lỗi; test trên dữ liệu schema thực.

### 7.2. Chỉ nhận update có thay đổi status

Một bộ lọc dựa trên delta:

```javascript
db.orders.watch([
  {
    $match: {
      operationType: "update",
      "updateDescription.updatedFields.status": {
        $exists: true
      }
    }
  }
])
```

Spring Data raw:

```java
Document matchStatusChange = new Document(
    "$match",
    new Document("operationType", "update")
        .append("updateDescription.updatedFields.status",
            new Document("$exists", true)));

ChangeStreamOptions statusChanges = ChangeStreamOptions.builder()
    .filter(matchStatusChange)
    .build();
```

**Ý nghĩa:** bắt event update có `status` nằm trong `updatedFields`. Nó không bao phủ mọi kiểu `replace`, thao tác đổi cấu trúc document hoặc các cách server biểu diễn thay đổi khác. Nếu cần “mọi tình huống trạng thái đơn thay đổi”, xây một hợp đồng rõ cho các loại write và test đầy đủ.

### 7.3. Dữ liệu updateDescription dạng path

Với path lồng như `shipping.status`, MongoDB có thể biểu diễn:

```javascript
updateDescription: {
  updatedFields: {
    "shipping.status": "DELIVERED"
  }
}
```

Đây là một key **chứa dấu chấm** trong BSON document `updatedFields`, không phải mặc định một object lồng `shipping: { status: ... }`. Khi parse raw BSON, phải hiểu key/path semantics. Một vài trường hợp field names chứa dấu chấm/số có thể cần `disambiguatedPaths` (khi version/option hỗ trợ).

Đừng dùng parser giả định mọi dấu chấm trong path chỉ nghĩa là Java nested property; có thể cần phân biệt field thật với array index và key chứa ký tự đặc biệt.

## 8. Filter Aggregation: khi nào dùng thay raw Document?

`ChangeStreamOptions.ChangeStreamOptionsBuilder.filter(Aggregation)` nhận pipeline Spring Data và tận dụng `Aggregation`/`Criteria`. Ví dụ:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

Aggregation pipeline = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("operationType")
            .in("insert", "update", "replace")));

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(pipeline)
    .returnFullDocumentOnUpdate()
    .build();
```

Trường `operationType` là **reserved event field** được Spring Data giữ ở cấp envelope; nó không cần tiền tố `fullDocument.`. Những property khác có thể được mapper coi là field của domain entity và **tự thêm tiền tố `fullDocument.`**.

### 8.1. Khác biệt quan trọng giữa event fields và domain fields

Trong overload `filter(Aggregation)`, Spring Data document nêu quy tắc:

- `operationType`, `ns`, `documentKey`, `fullDocument` là các tên reserved của event, được hiểu ở cấp event.
- Các expression fields khác có thể được map/prefix thành `fullDocument.<field>`.
- `TypedAggregation` giúp map tên property Java sang trường BSON được annotation `@Field` đổi tên.

Vì vậy:

```text
Event predicate:
  operationType == "update"

Domain field predicate:
  status == "PAID"     (có thể được map thành fullDocument.status)

Raw BSON predicate:
  "updateDescription.updatedFields.status" exists
```

Khi muốn lọc trực tiếp theo `updateDescription` hoặc metadata ít phổ biến, raw `Document` pipeline thường **dễ kiểm chứng hơn** vì nó giữ nguyên field path được viết. Không áp dụng mù một `Aggregation.match(Criteria.where("updateDescription..."))` có nguy cơ map sai sang `fullDocument.updateDescription...` theo ngữ cảnh mapping.

### 8.2. Một rule tránh nhầm

| Muốn lọc | Nên cân nhắc |
| --- | --- |
| `operationType` | `Aggregation.match(Criteria.where("operationType")...)` hoặc raw `Document` |
| Field của entity trong `fullDocument` | Typed aggregation hoặc raw `Document("fullDocument.<field>", ...)` |
| `documentKey._id` | Raw envelope path hoặc aggregation với mapping đã xác minh |
| `updateDescription.updatedFields` | Raw `Document` cho cấu trúc metadata BSON |
| `ns.coll` / `ns.db` ở stream rộng | Raw envelope path |
| Conditional event routing đa schema | Raw `Document` + `getRaw()/getCollectionName()` |

### 8.3. Ví dụ filter theo tenant và loại event

```java
Document match = new Document("$match",
    new Document("operationType",
        new Document("$in",
            List.of("insert", "update", "replace")))
        .append("fullDocument.tenantId", "TENANT-A"));

ChangeStreamOptions tenantStream = ChangeStreamOptions.builder()
    .filter(match)
    .returnFullDocumentOnUpdate()
    .build();
```

Đây là **ví dụ filter cho những event có fullDocument**. Với delete, `fullDocument` vắng mặt, nên filter này loại delete. Với update, `UPDATE_LOOKUP` có thể trả **phiên bản document muộn hơn thời điểm của event**, hoặc không tìm thấy nếu document đã biến mất; vì thế filter theo `fullDocument.tenantId` không luôn là phép phân loại một update theo “tenant tại đúng thời điểm update”.

**Nếu cần audit/bảo mật multi-tenant chính xác cho mọi thao tác,** tốt hơn nên watch collection phân chia rõ tenant hoặc thiết kế sự kiện/outbox có tenant identity bền vững. Không dùng change-stream filter để thay thế authorization trong các API khác.

### 8.4. Không đưa authorization vào filter một cách hời hợt

Người dùng gọi API “watch tenant B” không có nghĩa họ được quyền theo dõi tenant B. Consumer backend thường có một tài khoản MongoDB có quyền rộng để đọc change streams. Vì vậy:

1. Backend phải tự xác thực/ủy quyền tenant.
2. Không expose nguyên raw change event cho client tùy ý.
3. Không cho phép client tự cấu hình `filter(Document...)` với dữ liệu từ HTTP mà không kiểm soát.
4. Nếu gửi kết quả tới nhiều nhóm người dùng, phải lọc quyền ở service và có phân loại dữ liệu nhạy cảm.

Change stream chỉ là luồng kỹ thuật của DB, không tự tạo hàng rào tenant isolation.

## 9. Projection trong pipeline: không phá resume token

MongoDB change event có `_id` là resume token. Từ MongoDB 4.2 trở đi, change stream pipeline cố tình sửa `_id` của change event sẽ bị từ chối. Điều này bao gồm các pipeline xóa hoặc biến đổi token bằng `$project`/`$unset`/`$replaceRoot`.

### 9.1. Phản ví dụ: bỏ _id để giảm payload

```javascript
// PHẢN VÍ DỤ — KHÔNG dùng với change streams.
db.orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      fullDocument: 1
    }
  }
])
```

Một query aggregation thông thường có thể không cần `_id`, nhưng change stream **cần resume token để khôi phục cursor**. Không dùng pattern “`$project: { _id: 0 }`” quen thuộc từ report aggregation vào pipeline stream.

### 9.2. Ví dụ projection có giữ token

```javascript
db.orders.watch([
  {
    $match: {
      operationType: { $in: ["insert", "update", "replace"] }
    }
  },
  {
    $project: {
      _id: 1,
      operationType: 1,
      ns: 1,
      documentKey: 1,
      fullDocument: 1,
      updateDescription: 1,
      clusterTime: 1
    }
  }
])
```

Đây là ví dụ **lựa chọn field có chủ đích**, không phải yêu cầu “mọi stream đều phải `$project`”. Nếu `$project` loại một field mà ứng dụng cần (ví dụ `ns` để route hoặc `fullDocument` để convert), handler có thể nhận dữ liệu thiếu. Tốt hơn nên bắt đầu với `$match` và chỉ thêm projection khi đã đo nhu cầu payload.

### 9.3. Mỗi thay đổi pipeline cần regression test resume

MongoDB khuyến nghị **giữ cùng pipeline và options khi resume bằng token**. Thay đổi cách lọc hoặc chiếu giữa lúc lưu token và lúc restart có thể tạo hành vi không mong đợi hoặc làm resume thất bại. Hãy version hóa cấu hình stream cùng checkpoint; khi deploy một pipeline mới, có thể phải xây kế hoạch cutover/rebuild read model theo nghiệp vụ.

### 9.4. Bộ lọc có thể làm mất những event cần thiết

Ví dụ filter chỉ có `operationType: "insert"`:

- Nó phù hợp để xây một read model **chỉ cần sự kiện tạo mới**.
- Nó **không phù hợp** để giữ read model đồng bộ mọi thay đổi, bởi update/delete bị loại.
- Không nên filter delete rồi sau đó dùng read model như snapshot luôn đúng.

Một consumer cần xem **toàn bộ vòng đời của entity** nên bắt các operation types tương ứng, kể cả `replace` và `delete` khi sản phẩm có thao tác đó.

## 10. ChangeStreamEvent<T>: kiểu trả về của Spring Data

API tiêu biểu cho reactive:

```java
Flux<ChangeStreamEvent<OrderDocument>> events =
    reactiveTemplate.changeStream(OrderDocument.class)
        .watchCollection("orders")
        .listen();
```

`ReactiveMongoTemplate` tạo `Flux<ChangeStreamEvent<OrderDocument>>`; `OrderDocument` là kiểu được converter dùng cho `fullDocument` khi có. **Envelope của event vẫn chứa metadata riêng**.

### 10.1. Các getters nên dùng

| Spring Data `ChangeStreamEvent<T>` | Kiểu dữ liệu | Trường MongoDB liên quan |
| --- | --- | --- |
| `getBody()` | `T` hoặc null | `fullDocument` đã convert |
| `getBodyBeforeChange()` | `T` hoặc null | `fullDocumentBeforeChange` khi có pre-image |
| `getRaw()` | `ChangeStreamDocument<Document>` hoặc null | Raw driver event |
| `getResumeToken()` | `BsonValue` hoặc null | `_id` event (opaque token) |
| `getOperationType()` | `OperationType` hoặc null | `operationType` |
| `getCollectionName()` | `String` hoặc null | `ns.coll` |
| `getDatabaseName()` | `String` hoặc null | `ns.db` |
| `getTimestamp()` | `Instant` hoặc null | `clusterTime` quy đổi thành Instant |
| `getBsonTimestamp()` | `BsonTimestamp` hoặc null | `clusterTime` chính xác hơn tới phần tăng |

Các nullable annotations của API cho biết **không được ép mọi getter khác null**. Đặc biệt, delete event thường không có `getBody()`.

### 10.2. Đọc typed body và raw envelope

```java
package com.example.orders;

import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import com.mongodb.client.model.changestream.UpdateDescription;
import org.bson.BsonDocument;
import org.bson.BsonValue;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;

public final class OrderChangeDebugFormatter {

    private OrderChangeDebugFormatter() {}

    public static String describe(
            ChangeStreamEvent<OrderDocument> event) {

        OperationType type = event.getOperationType();
        BsonValue token = event.getResumeToken();
        OrderDocument body = event.getBody();
        ChangeStreamDocument<Document> raw = event.getRaw();

        String docId = "<not-available>";
        String changedFields = "<not-an-update>";

        if (raw != null) {
            BsonDocument key = raw.getDocumentKey();
            if (key != null && key.containsKey("_id")) {
                docId = key.get("_id").toString();
            }

            UpdateDescription delta =
                raw.getUpdateDescription();
            if (delta != null
                    && delta.getUpdatedFields() != null) {
                changedFields =
                    delta.getUpdatedFields().toString();
            }
        }

        return "operation=" + type
            + ", documentId=" + docId
            + ", hasFullDocument=" + (body != null)
            + ", hasResumeToken=" + (token != null)
            + ", changedFields=" + changedFields;
    }
}
```

Đây là code demo **để học cách phân loại**, không được log nguyên `token`/raw BSON trong production nếu nó chứa dữ liệu nhạy cảm. `getUpdatedFields()` hoặc các metadata khác có thể rỗng/null theo operation và driver version. Trong ứng dụng thật nên kiểm tra null, tóm tắt field names và redaction trước khi ghi log.

### 10.3. getBody() không được biến thành điều kiện để bỏ qua event

Phản ví dụ:

```java
// SAI khi consumer còn phải xử lý delete/update thiếu fullDocument.
return events
    .map(ChangeStreamEvent::getBody)
    .filter(order -> order != null);
```

Trong Reactor, `map` không chấp nhận mapper trả null: nếu `getBody()` null, nó có thể tạo lỗi reactive chứ không đơn thuần bị `filter` loại bỏ. Quan trọng hơn, **delete event có body null nhưng vẫn là thay đổi có ý nghĩa**.

Đúng là kiểm tra `operationType` trước, sau đó chọn cách lấy khóa/document/delta theo từng loại:

```java
return events.concatMap(event -> {
    OperationType type = event.getOperationType();
    if (type == OperationType.DELETE) {
        return handleDeleteByDocumentKey(event);
    }
    if (event.getBody() != null) {
        return handleCurrentDocument(event.getBody());
    }
    return handleWithoutFullDocument(event);
});
```

Đây là pseudocode trong một service có các hàm `handleDeleteByDocumentKey`, `handleCurrentDocument` và `handleWithoutFullDocument` trả `Mono<Void>`. `concatMap` giữ thứ tự xử lý. Trong production, cần phân biệt `insert`/`replace`/`update` và không giả định mọi body là snapshot đúng thời điểm của update.

## 11. ReactiveMongoTemplate: một ví dụ nghe stream hoàn chỉnh

File `OrderChangeStreamSource.java`:

```java
package com.example.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public final class OrderChangeStreamSource {

    private final ReactiveMongoTemplate template;

    public OrderChangeStreamSource(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<OrderDocument>>
            watchOrderMutations() {

        Document match = new Document("$match",
            new Document("operationType",
                new Document("$in",
                    List.of("insert",
                            "update",
                            "replace",
                            "delete"))));

        ChangeStreamOptions options = ChangeStreamOptions.builder()
            .filter(match)
            .returnFullDocumentOnUpdate()
            .build();

        return template.changeStream(
            "orders", options, OrderDocument.class);
    }
}
```

Overload `changeStream(String collectionName, ChangeStreamOptions options, Class<T> targetType)` sử dụng trực tiếp object options. Với fluent API, `withOptions(...)` nhận `Consumer<ChangeStreamOptionsBuilder>`, **không phải** object `ChangeStreamOptions`; có thể cấu hình fluent bằng `.withOptions(builder -> builder.returnFullDocumentOnUpdate())`. Ví dụ này cố ý dùng overload nhận options để tránh nhầm hai signature.

### 11.1. Không tạo stream rồi bỏ quên subscribe

```java
Flux<ChangeStreamEvent<OrderDocument>> flux =
    source.watchOrderMutations();

// Chỉ tạo Publisher chưa phải đang nghe events.
```

Với reactive API, **subscription** mở lifecycle của luồng; cancellation/dispose đóng tài nguyên liên quan. Không coi `Flux` là một queue có dữ liệu tự chảy nếu không có subscriber.

### 11.2. Đừng đặt subscribe() tùy tiện trong mỗi request

Phản thiết kế:

```java
@GetMapping("/start-watching")
public Mono<String> startWatching() {
    source.watchOrderMutations().subscribe(
        event -> handle(event));
    return Mono.just("started");
}
```

Mỗi HTTP request có thể tạo thêm **một cursor, một consumer và bản sao sự kiện**. Không có lifecycle/cancellation/backpressure đúng. Với listener phục vụ toàn ứng dụng, hãy tạo thành phần có quản lý khởi động/dừng, ownership giữa replicas và checkpoint; nếu expose SSE/WebSocket cho từng user, phải thiết kế authorization, fan-out và tài nguyên riêng.

### 11.3. Processing phải diễn ra trước checkpoint

```text
Receive event E with resume token R
          |
          v
Validate / deduplicate / process E
          |
          v
Confirm durable side effects
          |
          v
Persist checkpoint R
```

Nếu ghi token **trước** khi xử lý E rồi process crash, khi resume từ R ứng dụng sẽ bỏ qua E và có thể mất một side effect. Nếu xử lý E xong rồi crash **trước** khi ghi token, E có thể được gửi lại: vì vậy consumer phải **idempotent**.

Không nhét một `checkpointStore.save(event.getResumeToken())` vô điều kiện vào `doOnNext` trước downstream processing. `doOnNext` không chờ một Publisher xử lý bất đồng bộ; cần compose và chờ terminal success.

## 12. Imperative: MessageListenerContainer

Ứng dụng không dùng Reactor vẫn có thể nhận change streams qua Spring Data messaging abstraction. Vì MongoDB Java driver sync theo dõi cursor là công việc **blocking kéo dài**, Spring Data cung cấp `DefaultMessageListenerContainer` để quản lý các subscription tasks.

Ví dụ rút gọn:

```java
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequest;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequestOptions;
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListener;
import org.springframework.data.mongodb.core.messaging.MessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.Subscription;

MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);
container.start();

MessageListener<ChangeStreamDocument<Document>, OrderDocument>
    listener = message -> {
        OrderDocument body = message.getBody();
        // Cần xử lý metadata/raw với API Message tương ứng.
        // Body có thể null khi event delete.
    };

ChangeStreamRequestOptions requestOptions =
    new ChangeStreamRequestOptions(
        "shop", "orders", ChangeStreamOptions.empty());

Subscription subscription = container.register(
    new ChangeStreamRequest<>(listener, requestOptions),
    OrderDocument.class);

// Khi ứng dụng dừng: hủy/stop theo lifecycle phù hợp.
container.stop();
```

Đây là đoạn code minh họa **các đối tượng chính**, không phải một ứng dụng chạy rồi stop ngay như trình tự trên; trong production, `container.stop()` phải nằm ở lifecycle shutdown, không nằm ngay sau register. Spring Data documentation cho biết `DefaultMessageListenerContainer` có tích hợp `SmartLifecycle` khi đăng ký làm bean.

Khi listener gặp lỗi, đừng dựa vào log mặc định làm cơ chế chống mất dữ liệu. Cấu hình `ErrorHandler`, checkpoint/recovery, shutdown và giám sát rõ ràng. Với nhiều consumer instances, mỗi instance có thể nhận sự kiện riêng; change streams không tự làm competing-consumers group giống message broker.

### 12.1. Chọn reactive hay imperative?

| Tiêu chí | Reactive `Flux` | Imperative `MessageListenerContainer` |
| --- | --- | --- |
| Thread dùng để chờ event | Không cần một blocking thread riêng mỗi stream theo kiểu sync | Task theo dõi sync cursor dùng blocking execution |
| Metadata | `ChangeStreamEvent<T>` | `Message<ChangeStreamDocument<Document>, T>` |
| Error propagation | `onError` và Reactor operators | `ErrorHandler`/container lifecycle |
| Backpressure/processing | Reactor flow operators, vẫn cần giới hạn downstream | Đặt queue/executor/flow control phù hợp |
| Resource cleanup | Dispose/cancel subscription | Stop/cancel Subscription/container |
| Tính bền vững token | **Phải tự thiết kế** | **Phải tự thiết kế** |

Không suy luận “reactive” đồng nghĩa “không bao giờ mất sự kiện”, hoặc “imperative” đồng nghĩa “luôn blocking request thread”. Mỗi kiểu đều cần quản lý cursor, lỗi và checkpoints.

## 13. Resume token: dữ liệu quan trọng nhất để khôi phục stream

Mỗi change event có một resume token ở event `_id`. Spring Data expose nó qua:

```java
import org.bson.BsonValue;

BsonValue token = event.getResumeToken();
```

`event` là một `ChangeStreamEvent<OrderDocument>` có sẵn trong consumer. Token là **opaque BSON value**, không phải timestamp số nguyên hoặc `OrderDocument.id`. Trong các phiên bản thông dụng, token thường là `BsonDocument` với dữ liệu binary/hex nội bộ; không tự bóc `_data` để “tăng lên một” hoặc ghép token từ document ID.

### 13.1. Resume sau event đã được xử lý

```java
import org.bson.BsonValue;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

BsonValue lastProcessedToken = checkpointStore.load();

ChangeStreamOptions options =
    ChangeStreamOptions.builder()
        .resumeAfter(lastProcessedToken)
        .returnFullDocumentOnUpdate()
        .build();
```

Ví dụ giả định `checkpointStore.load()` đã trả token **khác null** từ kho checkpoint có cấu trúc phù hợp. Trong code thật, phải có hai nhánh:

- Có checkpoint hợp lệ → build options với `resumeAfter(token)`.
- Chưa từng xử lý event → chọn chiến lược khởi đầu (từ thời điểm hiện tại, mốc server time hay snapshot + stream cutover), **không truyền null** vào builder.

Không tự động “fallback start now” khi resume thất bại do token đã hết hiệu lực: cách đó có thể bỏ qua thay đổi trong khoảng downtime. Hãy báo lỗi, kiểm tra oplog retention và thực hiện một quy trình resnapshot/reconciliation đã được phê duyệt.

### 13.2. Lưu token BSON không làm mất kiểu dữ liệu

Đoạn minh họa việc chuyển token dạng `BsonDocument` qua Extended JSON:

```java
import org.bson.BsonDocument;
import org.bson.BsonValue;

public final class ResumeTokenCodec {

    private ResumeTokenCodec() {}

    public static String serialize(BsonValue token) {
        if (!(token instanceof BsonDocument doc)) {
            throw new IllegalArgumentException(
                "Cần BsonDocument resume token");
        }
        return doc.toJson();
    }

    public static BsonDocument deserialize(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException(
                "Checkpoint JSON trống");
        }
        return BsonDocument.parse(json);
    }
}
```

Trong một dự án thật, lưu cùng **stream identity**, collection scope, pipeline version và thông tin xử lý tương ứng; ưu tiên BSON native nếu kho lưu trữ hỗ trợ. Không log full token với dữ liệu môi trường production nếu không cần thiết, và không mã hóa nó thành một `String` tùy tiện làm mất type/format.

**Quan trọng:** token lưu phải đến từ **event đã xử lý bền vững**, không phải event vừa nhận nhưng chưa xử lý xong.

### 13.3. Checkpoint và xử lý sự kiện

Một mô hình xử lý:

```text
Event E(token=R) received
      |
      v
Has E been processed already?
  +-- yes --> verify state, update/keep checkpoint if safe
  |
  +-- no
       |
       v
  Apply idempotent business effect
       |
       v
  Confirm effect durable
       |
       v
  Persist R as processed checkpoint
```

Nếu effect và checkpoint đều ở **cùng MongoDB database** và hỗ trợ transaction, có thể thiết kế ghi cả hai trong một transaction ngắn để giảm cửa sổ lỗi. Nhưng phải tránh một consumer tự kích hoạt thay đổi liên tục trên **collection đang watch**, gây feedback loop; đặt riêng checkpoint/read model collections và filter/routing hợp lý.

Với hiệu ứng nằm ở hệ thống ngoài (HTTP, Kafka, email), một MongoDB transaction không thể tự bảo đảm exactly-once qua mọi hệ thống. Cần idempotency key, outbox/inbox hoặc cơ chế reconcile tương ứng.

### 13.4. Tại sao cần idempotency dù có resume token?

```text
t0  Receive event E
t1  Write target read model successfully
t2  Process crashes before saving E's token
t3  Restart from previous token
t4  Receive E again
```

Nếu áp dụng update một cách không idempotent (ví dụ `$inc: {points:10}` theo event không dedupe), bạn có thể cộng điểm hai lần. Khi có khả năng phát lại, thiết kế target xử lý “một event ID/token chỉ được áp hiệu ứng một lần” hoặc rebuild trạng thái deterministically từ source of truth.

### 13.5. Oplog retention và token hết hạn

Resume token chỉ có thể giúp replay nếu cluster còn đủ lịch sử phù hợp. Khi consumer dừng quá lâu, MongoDB có thể không còn oplog segment cần thiết; việc resume sẽ **thất bại**, không có cơ chế tự động replay vô hạn thời gian.

Theo dõi:

- `resume token age` và độ trễ của consumer so với thay đổi mới nhất.
- Oplog window thực tế trên các replica-set members/shards.
- Tần suất stream reconnect, resume failure và số event pending.
- Kế hoạch backfill/rebuild read model nếu không thể resume.

Không đặt retry vô hạn trên lỗi token hết hạn; điều đó chỉ làm service liên tục lỗi và không đồng bộ dữ liệu.

## 14. resumeAfter, startAfter, resumeAt: ba cách bắt đầu khác nhau

| Tuỳ chọn | Vị trí bắt đầu | Trường hợp điển hình |
| --- | --- | --- |
| `resumeAfter(token)` | Sau event/token đã biết | Consumer restart thông thường |
| `startAfter(token)` | Sau token và cho phép tạo stream mới sau `invalidate` theo quy tắc MongoDB | Collection drop/rename/invalidation đã được xử lý |
| `resumeAt(Instant)` | Theo thời điểm được chọn | Khởi tạo/khôi phục từ một mốc server time còn trong oplog |
| `resumeAt(BsonTimestamp)` | Theo logical cluster timestamp chính xác hơn | Phục hồi theo offset chính xác khi có BsonTimestamp |

Không kết hợp tùy tiện ba cách trong một builder. MongoDB quy định `resumeAfter`, `startAfter` và `startAtOperationTime` là những offset lựa chọn **không dùng đồng thời**.

### 14.1. Ví dụ builder từng trường hợp

```java
ChangeStreamOptions fromToken = ChangeStreamOptions.builder()
    .resumeAfter(previousToken)
    .build();

ChangeStreamOptions fromInvalidate = ChangeStreamOptions.builder()
    .startAfter(invalidateToken)
    .build();

ChangeStreamOptions fromTime = ChangeStreamOptions.builder()
    .resumeAt(serverTime)
    .build();
```

Ở đây `previousToken`/`invalidateToken` là `BsonValue` khác null; `serverTime` là `BsonTimestamp` hoặc `Instant` lấy từ nguồn đủ tin cậy. Không dùng `Instant.now()` trên application host làm một phép khôi phục chính xác nếu hệ thống cần tránh mất event: đồng hồ app có thể lệch và timestamp có độ phân giải khác cluster time.

### 14.2. Invalidate không giống disconnect thông thường

Collection drop hoặc rename có thể phát **`invalidate`** khiến change stream scope tương ứng bị đóng. Sau invalidate, `resumeAfter(token)` **không phải** cách khôi phục được phép để đi tiếp stream cũ; `startAfter(token)` có thể dùng để bắt đầu một stream mới sau invalidate theo quy tắc MongoDB.

Trong nghiệp vụ, collection đã bị drop/rename có thể không còn đúng schema/scope. Không dùng `startAfter` rồi tiếp tục như chưa có sự kiện gì: cần kiểm tra tên collection, mapping, quyền và có cần rebuild dữ liệu downstream hay không.

### 14.3. Pipeline thay đổi làm resume khó dự đoán

Nếu checkpoint R được sinh từ pipeline P1 lọc `status=PAID`, restart bằng pipeline P2 lọc `tenantId=TENANT-B` có thể thay đổi ý nghĩa các event đã bỏ qua và dẫn tới hành vi khó dự đoán. MongoDB khuyến nghị dùng **cùng pipeline và options** với token lúc tạo ra.

Đặt `streamName` và `pipelineVersion` cạnh token để deployment có thể:

1. Phát hiện phiên bản filter khác trước.
2. Quyết định có cần migration/read-model rebuild.
3. Có quy trình đổi version riêng thay vì tự tiếp tục với token cũ không kiểm chứng.

### 14.4. Không dùng token làm business sequence number

Resume token opaque không phải một trường có thể so sánh bằng thứ tự số học hoặc sắp xếp tùy ý trong Java. Đừng biến `_data` thành long, tăng nó hoặc tự dùng nó làm timestamp. Nếu cần business ordering, xác định quy tắc dùng `clusterTime`, thứ tự stream và idempotency; không giả định mọi event có cluster time duy nhất.

## 15. getTimestamp, getBsonTimestamp và độ chính xác của mốc resume

`getTimestamp()` cho `Instant` giúp log và quan sát, nhưng `Instant` không nhất thiết mang đầy đủ phần tăng của `BsonTimestamp`. Trong MongoDB, `BsonTimestamp` chứa phần **seconds** và **increment** cho logical operation ordering.

```java
import org.bson.BsonTimestamp;
import java.time.Instant;

Instant wallRepresentation = event.getTimestamp();
BsonTimestamp logicalOffset = event.getBsonTimestamp();
```

Hai giá trị được minh họa để đọc; cả hai có thể null theo API. **Ưu tiên resume token** để khôi phục event-level processing. Chỉ dùng timestamp khi có lý do/mốc đáng tin cậy và hiểu giới hạn của việc bắt đầu theo thời gian.

### 15.1. Hai events có thể có cùng clusterTime

Không lấy `clusterTime` làm unique event key trong transaction/sharded cluster. Các event có thể chia sẻ timestamp logic theo ngữ nghĩa oplog/transaction. Để dedupe, event-level resume token hoặc business event ID bền vững thường phù hợp hơn.

### 15.2. Không dùng system clock để xác định lag duy nhất

`Instant.now() - event.getTimestamp()` là một chỉ số gần đúng có thể bị sai do clock skew, scheduler delay và các dạng timestamp khác nhau. Khi giám sát, kết hợp:

- Event processing latency đo ở application.
- Cluster/oplog metrics của MongoDB.
- Khoảng tuổi checkpoint.
- Độ dài hàng đợi downstream và thời gian xử lý.

Không có event trong 10 giây chưa phải dấu hiệu stream bị treo: có thể đơn giản là không có thay đổi.

## 16. fullDocument và fullDocumentBeforeChange: chính sách khác nhau

Khi MongoDB phát một update event, mặc định thường có **delta** trong `updateDescription` nhưng không có full document. Spring Data cho phép thay đổi chính sách này qua options.

### 16.1. UPDATE_LOOKUP: xem trạng thái hiện tại sau update

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .returnFullDocumentOnUpdate()
    .build();
```

Hoặc khai báo enum driver:

```java
import com.mongodb.client.model.changestream.FullDocument;

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .fullDocumentLookup(FullDocument.UPDATE_LOOKUP)
    .build();
```

Lựa chọn này có thể mang lại `event.getBody()` khi event là `update`. Tuy nhiên MongoDB tra **phiên bản document majority-committed mới nhất tại lúc lookup**, không đảm bảo chính xác snapshot **ngay sau operation tạo ra event**.

Timeline:

```text
t0: Order.status = NEW
t1: update status = PAID         --> Event E1
t2: update status = SHIPPED      --> Event E2
t3: updateLookup for E1

Possible E1.fullDocument.status = SHIPPED
Even though E1.updateDescription.updatedFields.status = PAID.
```

Đây không phải bug bắt buộc của Spring Data; đó là bản chất của **lookup tại thời điểm xử lý stream**. Nếu nghiệp vụ phải phát tín hiệu chính xác “lệnh thay đổi trạng thái sang PAID đã xảy ra”, ưu tiên delta/event payload phù hợp, không thay bằng `getBody().status()` rồi suy luận thứ tự giao dịch.

### 16.2. WHEN_AVAILABLE và REQUIRED cho post-image

Ở những MongoDB versions hỗ trợ **document pre/post images** (MongoDB 6.0+ cho tính năng này), một số chính sách `FullDocument` như `WHEN_AVAILABLE` và `REQUIRED` có ý nghĩa nhận **post-image đã được lưu** thay vì update lookup thông thường.

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .fullDocumentLookup(
        FullDocument.WHEN_AVAILABLE)
    .build();
```

Điều này **đòi hỏi server và collection được cấu hình lưu change stream pre/post images**; nếu không bật hoặc history đã hết, `WHEN_AVAILABLE` có thể không có body tương ứng, còn `REQUIRED` có thể khiến stream lỗi khi image bắt buộc không sẵn.

Không dùng enum này rồi mặc định mọi deployment đều có historical images. Kiểm tra phiên bản server, FCV, cấu hình collection, retention và quyền trước khi chọn policy.

### 16.3. Pre-image cho trạng thái trước khi update/delete

Ví dụ:

```java
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .fullDocumentBeforeChangeLookup(
        FullDocumentBeforeChange.WHEN_AVAILABLE)
    .build();
```

Khi pre-image có sẵn, `ChangeStreamEvent<T>.getBodyBeforeChange()` có thể cho phiên bản document **trước thay đổi**. Một ứng dụng cần kiểm tra quyền/tenant lúc document bị xóa có thể cân nhắc pre-image, nhưng:

- Cần bật lưu pre/post images trên collection đúng thời điểm.
- Pre-image không tự được tạo cho các thay đổi đã xảy ra **trước khi bật**.
- Không có bảo đảm images được giữ vô hạn.
- `WHEN_AVAILABLE` cho phép vắng image; handler vẫn phải xử lý null.
- `REQUIRED` có thể làm stream thất bại nếu image không còn.

Ví dụ bật cấu hình trên **test collection** trong MongoDB 6.0+:

```javascript
// Chỉ chạy với quyền và topology được cấp trên cluster TEST.
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
})
```

Không chạy lệnh `collMod` này tùy tiện trên production trong lúc soạn bài; cần đánh giá chi phí lưu trữ, retention và các quy tắc vận hành.

### 16.4. Pre-image không thay bản ghi audit bền vững

Nếu sản phẩm có yêu cầu audit pháp lý nhiều năm, change stream pre/post images và oplog retention có thể không đáp ứng thời hạn. Audit log/outbox có schema và chính sách lưu trữ riêng có thể phù hợp hơn. Change streams dùng để **quan sát thay đổi**, không tự thay thế cơ chế chứng cứ bất biến nhiều năm.

### 16.5. Filter theo post-image có thể tạo hiểu nhầm

Nếu pipeline có `"fullDocument.status": "PAID"` nhưng updateLookup trả trạng thái `SHIPPED` vì đã có update sau, event `E1` có thể bị filter loại. Đừng thiết kế một audit “mọi lần chuyển sang PAID” dựa duy nhất vào snapshot updateLookup; lọc `updateDescription.updatedFields.status` hoặc dùng business event riêng với semantics rõ.

## 17. Kiểu dữ liệu sự kiện trong Java: typed, raw và domain event

Có ba lớp không nên trộn:

```text
Raw ChangeStreamDocument<Document>
  - operationType
  - documentKey
  - updateDescription
  - fullDocument (BSON)
             |
             v
Spring ChangeStreamEvent<OrderDocument>
  - typed getBody() when present
  - typed getBodyBeforeChange() when available
  - getRaw() preserves envelope
             |
             v
Application DomainEvent / DTO
  - stable business ID
  - tenant and authorization policy
  - fields needed by consumer
  - version / idempotency key
```

`ChangeStreamEvent<T>` là **một sự kiện kỹ thuật MongoDB**. Không expose trực tiếp cho browser hoặc gửi nguyên sang hệ thống ngoài nếu chưa có hợp đồng domain và quy tắc bảo mật.

### 17.1. Tránh map database-wide stream về một entity duy nhất

```java
// Với stream theo dõi nhiều collections, dùng Document phù hợp.
Flux<ChangeStreamEvent<Document>> allCollections =
    reactiveTemplate.changeStream(Document.class)
        .listen();
```

Khi nhận event, dựa vào `getCollectionName()`/`getDatabaseName()` và `getRaw()` để phân loại. Nếu dùng `OrderDocument.class` cho cả `orders`, `customers` và `inventory`, converter có thể map sai hoặc bỏ field; ứng dụng dễ tạo domain logic dựa trên dữ liệu thiếu.

### 17.2. Dùng documentKey cho delete

Ví dụ đơn giản:

```java
import com.mongodb.client.model.changestream.OperationType;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;

public static String deletedOrderId(
        ChangeStreamEvent<OrderDocument> event) {

    if (event.getOperationType() != OperationType.DELETE) {
        throw new IllegalArgumentException("Không phải delete");
    }
    ChangeStreamDocument<Document> raw = event.getRaw();
    if (raw == null) {
        throw new IllegalStateException("Thiếu raw event");
    }
    BsonDocument key = raw.getDocumentKey();
    if (key == null || !key.containsKey("_id")) {
        throw new IllegalStateException("Thiếu documentKey._id");
    }
    return key.get("_id").asString().getValue();
}
```

Hàm giả định document ID thật là **BSON String**; nếu collection dùng ObjectId hoặc composite shard key, `asString()` không đúng. Trong production, sử dụng mapper/codec phù hợp và giữ đủ các field trong document key để nhận diện record an toàn.

### 17.3. UpdateDescription có thêm những dạng thay đổi khác

Với update event, `UpdateDescription` không chỉ có `updatedFields`. Còn có:

- `removedFields`: danh sách field bị `$unset` hoặc bị loại theo update semantics.
- `truncatedArrays`: mô tả mảng bị rút gọn trong những thao tác tương ứng.
- `disambiguatedPaths`: giúp giải nghĩa đường dẫn có dấu chấm/số trong trường hợp server/expanded events hỗ trợ.

Đừng dùng mỗi `updatedFields` để khẳng định đã biết **toàn bộ** thay đổi của event. Mỗi operation có thể ảnh hưởng mảng, loại bỏ field hoặc thay nguyên document (`replace`).

### 17.4. Tạo một domain event nhỏ

```java
package com.example.orders;

public record OrderStateChanged(
    String operationId,
    String orderId,
    String tenantId,
    String newStatus
) {}
```

Để xây một event này từ change stream:

1. Phải có một `operationId` ổn định/được lưu từ business write, hoặc một ID được định nghĩa từ event token theo quy tắc không trùng.
2. Phải biết `tenantId` đáng tin cậy, không suy từ thông tin thiếu trong delta.
3. Với `update`, đọc `updateDescription` hoặc post-image theo ngữ nghĩa đã chọn.
4. Không phát sự kiện business hai lần khi change stream resume/retry.

Không tự gán `operationId = orderId` cho mọi status transition: một order có thể có nhiều events khác nhau. Chọn idempotency key ở **mức event hoặc business operation**, không phải luôn mức entity.

## 18. Một consumer reactive có thứ tự xử lý và checkpoint

Mô hình bên dưới cố ý dùng các interfaces trừu tượng cho xử lý/ghi checkpoint. Mục tiêu là minh họa **thứ tự các lời gọi Publisher**, không tạo một hệ thống message broker hoàn chỉnh.

File `OrderStreamProcessor.java`:

```java
package com.example.orders;

import org.bson.BsonValue;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class OrderStreamProcessor {

    public interface OrderEventHandler {
        Mono<Void> process(
            ChangeStreamEvent<OrderDocument> event);
    }

    public interface CheckpointWriter {
        Mono<Void> save(BsonValue token);
    }

    private final OrderEventHandler handler;
    private final CheckpointWriter checkpoints;

    public OrderStreamProcessor(
            OrderEventHandler handler,
            CheckpointWriter checkpoints) {
        this.handler = handler;
        this.checkpoints = checkpoints;
    }

    public Mono<Void> processEvent(
            ChangeStreamEvent<OrderDocument> event) {

        BsonValue token = event.getResumeToken();
        if (token == null) {
            return Mono.error(
                new IllegalStateException(
                    "Event không có resume token"));
        }

        // Processing trước, checkpoint sau.
        // process(...) phải idempotent/durable theo policy.
        return handler.process(event)
            .then(checkpoints.save(token));
    }

    public Flux<Void> consume(
            Flux<ChangeStreamEvent<OrderDocument>> source) {
        // concatMap = giữ trình tự xử lý, không chạy
        // nhiều checkpoint cạnh tranh đồng thời.
        return source.concatMap(this::processEvent);
    }
}
```

Đây là **mẫu orchestration**, chưa giải quyết tất cả trường hợp:

- Nếu `handler.process` ghi sang hệ thống ngoài và thành công rồi `checkpoints.save` thất bại, event có thể được replay. Handler cần idempotency.
- Nếu nhiều instances chạy độc lập, mỗi instance có thể nhận cùng event; cần ownership/sharding/leader election hoặc inbox dedupe.
- Nếu checkpoint là một giá trị duy nhất, không được ghi token của event **sau** khi event **trước** chưa hoàn tất.
- Nếu pipeline có filter khác, checkpoint phải được gắn đúng stream identity/version.
- Khi xử lý mất nhiều thời gian, stream có thể bị chậm; cần backpressure/metrics và cơ chế recovery.
- `Flux<Void>` không phát phần tử `onNext` khi mỗi `Mono<Void>` hoàn tất; subscriber cần quan sát completion/error/cancellation và lifecycle. Với stream sống dài, completion thông thường chỉ xảy ra khi stream đóng.

Trong ứng dụng thật, điều phối subscription bằng component lifecycle và lưu checkpoint durable. Không gọi `subscribe()` trong mỗi HTTP request rồi bỏ reference `Disposable`, vì không thể dừng và quan sát consumer đúng cách.

### 18.1. Tại sao không dùng flatMap mặc định?

```java
// PHẢN VÍ DỤ nếu checkpoint là một offset tuần tự duy nhất.
source.flatMap(event ->
    handler.process(event)
        .then(checkpoints.save(event.getResumeToken())));
```

`flatMap` có thể xử lý nhiều event cùng lúc và hoàn tất **không đúng thứ tự**. Nếu event E2 checkpoint trước khi E1 hoàn tất rồi process crash, resume từ E2 có thể bỏ E1. Với một checkpoint tuần tự, `concatMap` giúp giữ thứ tự; nếu cần parallelism, phải thiết kế partitioning và checkpoint watermark theo từng partition/đơn vị xử lý.

### 18.2. Pipeline trước và sau checkpoint đều phải có chính sách lỗi

Đừng viết:

```java
// PHẢN VÍ DỤ: che lỗi nghiệp vụ và vẫn checkpoint.
handler.process(event)
    .onErrorResume(ex -> Mono.empty())
    .then(checkpoints.save(event.getResumeToken()));
```

Một exception đã bị nuốt nên checkpoint có thể đi tiếp, làm event bị đánh dấu processed dù business effect thất bại. Nếu một lỗi được chấp nhận bỏ qua (ví dụ event type thật sự không thuộc scope), hãy phân loại rõ, ghi metric và xác nhận checkpoint là quyết định đúng theo hợp đồng.

## 19. Change streams và transactions: chỉ phát sau thay đổi đã commit

Change stream cung cấp thông báo về những thay đổi đã được commit theo ngữ nghĩa của MongoDB. Các write trong một multi-document transaction chưa commit **không được coi là sự kiện nghiệp vụ đã thành công** để phát tới consumer. Khi transaction abort, các ghi chưa commit không trở thành change events đã xác nhận.

Nhưng không vì vậy mà coi change streams là event bus exactly-once:

- Nhiều documents trong cùng transaction có thể tạo nhiều change events.
- Những event có thể chia sẻ `clusterTime`; không dùng timestamp làm khóa dedupe.
- Stream listener có thể restart/replay.
- Không nên dựa vào một event của record A để chứng minh **consumer của record B** đã xử lý, nếu không có protocol/saga riêng.
- Lệnh update một document có thể phát dưới biểu diễn `replace` khi server chọn biểu diễn đó phù hợp.

Nếu cần một business event duy nhất như `OrderPaid` cho nhiều thay đổi đồng thời, **transactional outbox** tạo một record `OrderPaid` trong cùng transaction là pattern rõ ràng. Change stream có thể watch **outbox collection** để giao event xuống downstream, trong khi business state nằm ở các collection khác.

## 20. Kiểm thử tích hợp change streams trên MongoDB replica set

Unit test chỉ khởi tạo `ChangeStreamOptions` có thể kiểm tra cấu hình Java, nhưng không chứng minh MongoDB server **thực sự phát event đúng loại**, không chứng minh `getBody()`/`getRaw()` đúng với write, cũng không chứng minh resume token hoạt động. Cần **replica set test** hoặc sharded cluster test phù hợp; standalone không đủ.

### 20.1. Ma trận kiểm thử

| Test | Dữ liệu/operation | Điều cần assert |
| --- | --- | --- |
| Insert event | `insertOne` với `_id` duy nhất | `operationType=insert`, body convert, documentKey và token |
| Update event | `$set(status=PAID)` | `updateDescription.updatedFields.status=PAID`, body có/không tùy update lookup |
| Replace event | `replaceOne` | `operationType=replace` hoặc biểu diễn server có thể sinh theo thao tác; handler chấp nhận dạng hợp lệ |
| Delete event | `deleteOne` | `operationType=delete`, `documentKey._id` có, body có thể null |
| Filter loại event | `$match(operationType=insert)` | Update/delete không xuất hiện trong stream đã lọc |
| Filter fullDocument | `tenantId` theo dữ liệu mẫu | Chỉ event có fullDocument match; giải thích vì sao delete thiếu body |
| Resume | Lưu token R, tạo event tiếp theo | `resumeAfter(R)` có thể nhận những event sau R nếu oplog còn đủ |
| Token và projection | `$project` giữ `_id` | Resume còn hợp lệ; không biến đổi token |
| Cancellation | Dispose subscription | Cursor/resource được đóng theo lifecycle |
| Invalidation | Drop/rename trên **cluster test riêng** | Xác nhận `resumeAfter` không thay thế `startAfter` |
| Pre-image | Bật pre/post images trên test collection | `getBodyBeforeChange()` có ý nghĩa khi image available |

### 20.2. Một unit test cho ChangeStreamOptions

File `OrderChangeStreamOptionsTest.java`:

```java
package com.example.orders;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

import static org.assertj.core.api.Assertions.assertThat;

class OrderChangeStreamOptionsTest {

    @Test
    void filterAndUpdateLookupArePresent() {
        Document filterStage = new Document(
            "$match",
            new Document("operationType",
                new Document("$in",
                    List.of("insert", "update"))));

        ChangeStreamOptions options = ChangeStreamOptions.builder()
            .filter(filterStage)
            .returnFullDocumentOnUpdate()
            .build();

        assertThat(options.getFilter()).isPresent();
        assertThat(options.getFullDocumentLookup()).isPresent();
    }

    @Test
    void emptyOptionsDoNotSpecifyResumeToken() {
        ChangeStreamOptions empty =
            ChangeStreamOptions.empty();

        assertThat(empty.getResumeToken()).isEmpty();
    }
}
```

Test này xác minh **object options**, không kiểm tra server operations. Để biết filter có được serialize đúng thành `$match` hoặc fullDocument được trả ra, phải chạy integration test.

### 20.3. Kiểm thử event mapping độc lập với MongoDB

Ta có thể thiết kế một adapter chuyển dữ liệu metadata sang một record dễ test:

```java
package com.example.orders;

import com.mongodb.client.model.changestream.OperationType;
import org.springframework.data.mongodb.core.ChangeStreamEvent;

public record OrderChangeSummary(
    OperationType operation,
    String orderId,
    boolean hasBody,
    boolean hasToken
) {
    public static OrderChangeSummary from(
            ChangeStreamEvent<OrderDocument> event) {
        String id = null;
        var raw = event.getRaw();
        if (raw != null
                && raw.getDocumentKey() != null
                && raw.getDocumentKey().containsKey("_id")) {
            id = raw.getDocumentKey().get("_id").toString();
        }

        return new OrderChangeSummary(
            event.getOperationType(),
            id,
            event.getBody() != null,
            event.getResumeToken() != null);
    }
}
```

Adapter cố tình không buộc `getBody()` phải có. Có thể unit test với event fixture mà không khởi động MongoDB, nhưng event fixture cần tạo bằng API driver/converter đúng version. Không chỉ mock `getBody()` để khẳng định `updateLookup` hoạt động: đó là hành vi của database/driver.

## 21. Integration test với StepVerifier: tránh race giữa subscribe và write

Vì change stream là một **cursor sống dài**, `StepVerifier` không thể đơn giản gọi `verifyComplete()` trên một stream không có `take(...)`. Đồng thời, chỉ gọi `subscribe()` rồi ngay lập tức insert có thể **rơi vào race** nếu server chưa thực sự khởi tạo cursor.

### 21.1. Cấu trúc test đúng

```text
Setup MongoDB replica set TEST and collection "orders"
        |
        v
Establish controlled resume point R
        |
        v
Write a uniquely identified order E1
        |
        v
Build stream with resumeAfter(R)
        |
        v
StepVerifier.create(stream.filter(event -> matches E1).take(1))
        |
        v
Assert event type, raw documentKey, typed body, token
        |
        v
verifyComplete()
        |
        v
Cleanup only IDs created by test
```

Việc thiết lập resume point **phải thật sự có R hợp lệ** từ sự kiện/driver cursor đã quan sát trước, không tạo token giả. Với cùng pipeline/options và còn lịch sử oplog, test có thể ghi E1 trước khi subscribe stream resumed; từ đó loại race “cursor chưa sẵn sàng khi write”.

Nếu không có token fixture, một phương án khác là tạo một subscriber, đợi một **tín hiệu server-side cursor sẵn sàng** từ test harness/driver instrumentation trước khi write. Không dùng `Thread.sleep(500)` làm chứng cứ chắc chắn watcher đã sẵn sàng.

### 21.2. Skeleton của StepVerifier cho event đã có resume token

File `OrderChangeStreamIntegrationTest.java` (trích đoạn method; `template` và `resumeToken` được test fixture thiết lập):

```java
import java.time.Duration;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.BsonValue;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

void verifiesInsertAfterKnownCheckpoint(
        BsonValue resumeToken,
        String expectedOrderId) {

    ChangeStreamOptions options = ChangeStreamOptions.builder()
        .resumeAfter(resumeToken)
        .build();

    Flux<ChangeStreamEvent<OrderDocument>> flux =
        reactiveTemplate.changeStream(
            "orders", options, OrderDocument.class);

    Flux<ChangeStreamEvent<OrderDocument>> matching =
        flux.filter(event -> event.getBody() != null
            && expectedOrderId.equals(
                event.getBody().id()))
            .take(1);

    StepVerifier.create(matching)
        .assertNext(event -> {
            assertThat(event.getOperationType())
                .isEqualTo(OperationType.INSERT);
            assertThat(event.getResumeToken()).isNotNull();
            assertThat(event.getRaw()).isNotNull();
        })
        .expectComplete()
        .verify(Duration.ofSeconds(30));
}
```

Đây là **test skeleton**, không phải class chạy độc lập: `reactiveTemplate`, `assertThat`, test replica set và `resumeToken` phải được cấu hình. Dùng ID riêng cho mỗi test; filter client-side trong đoạn minh họa để chọn event E1 **không thay thế server-side pipeline filter** của bài. Khi test filter server-side, thêm `$match` vào `ChangeStreamOptions` và assert không có event bị loại trong một cửa sổ quan sát có giới hạn.

### 21.3. Không dùng expectNoEvent() như chứng minh tuyệt đối

`expectNoEvent(Duration.ofSeconds(1))` chỉ chứng minh **không phát event trong một khoảng thời gian có giới hạn** với điều kiện test đã bắt đầu đúng. Nó không chứng minh MongoDB sẽ không bao giờ phát event; startup lag, network/scheduler hoặc write chưa commit có thể làm một test false positive.

Để kiểm tra filter “chỉ insert” chắc hơn:

1. Establish stable resume point R.
2. Ghi một update/delete và một insert cùng test ID đã phân biệt.
3. Resume từ R với filter insert.
4. Assert nhận **insert event mong muốn**, đồng thời không nhận các event có operation type không được phép trước khi `take(1)` kết thúc.
5. Trong test riêng, xác minh unfiltered stream có thể nhìn thấy update/delete tương ứng.

### 21.4. Test updateLookup và null body

Với update event:

```text
ChangeStreamOptions.empty():
  update event
  raw.updateDescription populated
  getBody() may be null

ChangeStreamOptions.builder()
    .returnFullDocumentOnUpdate()
    .build():
  update event
  getBody() may contain looked-up OrderDocument
  getBody() can still be null if lookup unavailable
```

Đừng viết integration test yêu cầu `getBody().status() == "PAID"` sau khi đã cố tình cập nhật tiếp sang `SHIPPED` trước khi lookup: kết quả `UPDATE_LOOKUP` không phải snapshot chính xác của E1.

### 21.5. Test delete và pre-image

Với delete không bật pre-images:

- `getOperationType()==OperationType.DELETE`.
- `getRaw().getDocumentKey()` thường có khóa để xác định document.
- `getBody()` thường null.

Nếu bật pre-image phù hợp trong test:

- `getBodyBeforeChange()` có thể chứa document trước delete.
- Với policy `WHEN_AVAILABLE`, test cần xác định server thực sự lưu image; không gắn assert cứng khi setup chưa đáp ứng.
- Với policy `REQUIRED`, test cần có trường hợp image thiếu dẫn đến lỗi theo hợp đồng.

Không xóa collection dùng chung để test invalidate. Nếu muốn kiểm tra drop/rename, dùng **database riêng của test job** và fixture quản lý vòng đời, không đụng vào môi trường dev/prod.

### 21.6. Test resume, replay và idempotency

Một integration test end-to-end:

1. Consumer A nhận E1 và xử lý thành công, ghi token R1.
2. Ngắt A, tạo E2 khi A offline.
3. Consumer B mở lại từ `resumeAfter(R1)` với **cùng pipeline/options**.
4. Xác minh E2 được nhận và có token R2.
5. Giả lập crash sau khi xử lý E2 nhưng trước checkpoint R2.
6. Resume lại từ R1, xác minh E2 **có thể được phát lại**, nhưng side effect idempotent chỉ được áp một lần.

Đây mới là bài kiểm tra hữu ích về độ bền consumer. Một test chỉ `take(1)` và in log không chứng minh hệ thống chống double apply.

## 22. Hiệu năng, backpressure và vận hành stream

Change stream có thể hoạt động lâu dài, nhận hàng nghìn events mỗi giây trong thời điểm cao điểm. Khi handler chậm hơn nguồn phát, bài toán chuyển từ “nhận event” sang **điều phối, bộ đệm, tốc độ xử lý và khả năng bắt kịp oplog**.

### 22.1. Các chỉ số nên theo dõi

| Metric | Mục tiêu |
| --- | --- |
| `change_stream_open_total` / active subscriptions | Biết đang có bao nhiêu cursors/subscribers |
| `change_stream_reconnect_total` | Quan sát network/election/client recovery |
| `change_stream_resume_failed_total` | Phát hiện token invalid, hết oplog, sai options |
| `change_stream_events_received_total` theo `operationType` | Tỉ lệ insert/update/delete/replace |
| `change_stream_events_processed_total` | So với số received, phát hiện backlog |
| `change_stream_processing_latency_seconds` | Mức chậm của downstream handler |
| `change_stream_checkpoint_age_seconds` | Độ trễ theo checkpoint đã xử lý |
| `change_stream_checkpoint_write_failed_total` | Rủi ro replay/không thể khôi phục |
| `change_stream_duplicate_events_total` | Số event đã xử lý được thấy lại |
| `change_stream_full_document_missing_total` | Hiểu số lần update lookup/pre-image không có |
| `change_stream_dead_letter_total` | Các event lỗi cần xử lý thủ công |
| `change_stream_resume_token_expired_total` | Khi lịch sử oplog không còn đủ |

Đặt alert theo **SLA dữ liệu downstream**. Không có event mới chưa chắc là lỗi; cần thêm health của subscription/cursor, heartbeat/server metrics và checkpoint age so với các thay đổi thực.

### 22.2. Không log nguyên mọi event

`ChangeStreamEvent.getRaw()` có thể mang nguyên document có PII, thông tin giao dịch, địa điểm kho hoặc dữ liệu nhạy cảm. Tránh:

```java
// PHẢN VÍ DỤ trên production:
events.doOnNext(System.out::println);
```

Thay bằng log tối thiểu: stream name, loại operation, namespace đã duyệt quyền, hashed/correlation ID không nhạy cảm, trạng thái xử lý, latency và error category. Không đặt resume token/document key đầy đủ làm metric label có cardinality rất cao.

### 22.3. Không tạo cursor cho mỗi kết nối client mà không kiểm soát

Nếu một ứng dụng WebSocket/SSE muốn broadcast thay đổi đơn hàng tới 1.000 clients, mở **1.000 change stream cursors** có thể tạo tải không cần thiết cho MongoDB. Thường nên có một số consumer backend được quản lý và một tầng fan-out/broker/cache với tenant authorization phù hợp.

Khi triển khai nhiều application replicas:

- Mỗi replica mở một stream có thể nhận **cùng event**.
- Change stream không cung cấp consumer-group partitioning giống Kafka.
- Nếu mong mỗi event xử lý nghiệp vụ đúng một lần, phải có ownership/partitioning và deduplication.
- Khi đổi leader, checkpoint phải durable và có fencing/locking phù hợp để tránh hai owners cùng ghi không kiểm soát.

### 22.4. Bounded concurrency

`concatMap` giữ thứ tự nhưng xử lý tuần tự, phù hợp làm điểm bắt đầu khi một checkpoint tuyến tính. Khi throughput đòi hỏi cao hơn, có thể partition theo entity/tenant rồi xử lý song song, nhưng phải:

1. Định nghĩa thứ tự cần bảo toàn trong mỗi partition.
2. Không checkpoint vượt qua event chưa xử lý.
3. Có cơ chế chặn backlog tăng vô hạn.
4. Đảm bảo effect idempotent và retry được.
5. Giữ cơ chế rebuild khi token hết lịch sử.

Đừng đổi thành `flatMap(..., 128)` rồi chỉ lưu resume token lớn nhất đã hoàn tất; điều đó có nguy cơ đánh dấu “xong” cho những events còn đang chạy.

### 22.5. Khi nào nên dùng outbox?

Nếu chỉ cần rebuild cache/read model từ một collection và chấp nhận eventual consistency, watch trực tiếp collection có thể đủ với checkpoint/rebuild. Nếu cần phát một **business event ổn định** qua nhiều collections, side effects và consumer không đồng nhất, outbox giúp tách nghiệp vụ khỏi chi tiết `updateDescription`/`fullDocument`.

Ví dụ:

```text
Order transaction:
  update orders.status = PAID
  insert outbox {
    eventId: "ORDER-PAID-OP-123",
    type: "OrderPaid",
    orderId: "ORD-101",
    tenantId: "TENANT-A"
  }
      |
      v
MongoDB COMMIT
      |
      v
change stream on outbox
      |
      v
idempotent dispatcher/consumer
```

Change stream giúp phát hiện **outbox record đã commit**. Nó vẫn không thay thế chính sách xử lý duplicate, checkpoint và broker acknowledgement.

## 23. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Mở stream báo unsupported | MongoDB standalone | Dùng replica set/sharded cluster hỗ trợ |
| Có write nhưng Flux không phát gì | Chưa subscribe, filter sai, watcher chưa sẵn | Kiểm tra subscription, source scope, pipeline, setup |
| Update event có body null | Chưa bật update lookup hoặc lookup không tìm được | Đọc `getRaw().getUpdateDescription()`; cân nhắc `returnFullDocumentOnUpdate()` |
| Delete event gây NullPointerException | Handler ép `getBody()` nonnull | Dùng `documentKey` hoặc pre-image khi đủ điều kiện |
| Filter theo `status` không hoạt động | Aggregation mapping prefix sang `fullDocument.status` hoặc thiếu full document | Inspect pipeline BSON, dùng raw `Document` khi cần |
| `updateDescription.updatedFields.status` thiếu | Update field khác, replace event hoặc shape thay đổi | Phân loại `operationType` và delta đúng |
| Event type được xử lý hai lần | Resume replay hoặc nhiều app replicas | Idempotency/ownership/processed-event key |
| Mất event sau crash | Checkpoint được ghi trước khi xử lý | Ghi checkpoint **sau** durable effect |
| Backlog tăng liên tục | Consumer chậm, full lookup nặng, downstream lỗi | Đo processing latency, scale/partition có checkpoint đúng |
| Token hết hạn | Consumer offline lâu hơn oplog window | Alert và resnapshot/reconciliation |
| Cannot resume after invalidate | Dùng `resumeAfter` trên invalidate token | Dùng `startAfter` khi phù hợp và kiểm tra schema/scope |
| Thay pipeline rồi resume sai | Checkpoint không gắn version/options | Version stream contract, cutover theo kế hoạch |
| `$project` làm stream lỗi | Bỏ/sửa `_id` event | Giữ nguyên resume token |
| Event tenant khác xuất hiện | Watch scope rộng, filter/authorization thiếu | Giới hạn collection, lọc và route theo policy |
| Đọc event từ nhiều collections bị map sai | Dùng một domain type cho mọi collection | Dùng `Document`/router theo `ns` |
| status “PAID” event có fullDocument “SHIPPED” | `UPDATE_LOOKUP` lấy current document muộn hơn | Dựa vào delta/structured domain event phù hợp |
| Pre-image null dù bật lookup | Collection chưa bật pre/post images hoặc history không còn | Kiểm tra collMod/retention/version; xử lý WHEN_AVAILABLE |
| Listener sync bị kẹt | Blocking cursor task/lifecycle không được quản lý | Dùng MessageListenerContainer và monitor task |
| App shutdown nhưng cursor còn / duplicate watcher | Subscription không dispose/stop đúng | Dừng lifecycle có kiểm soát |
| Sự kiện update từ transaction không thấy ngay | Transaction chưa commit hoặc stream trễ | Kiểm tra commit, cluster health, cursor lag |
| Pipeline chỉ bắt insert làm read model thiếu delete | Filter loại operations cần thiết | Bổ sung loại event và rebuild read model |

### 23.1. Không thấy event: checklist điều tra

Theo thứ tự:

1. **Topology:** replica set/sharded cluster? Member nào hoạt động?
2. **Authentication:** tài khoản stream đủ quyền trên namespace/scope?
3. **Subscription:** có `subscribe`/listener container thực sự hoạt động?
4. **Start position:** stream được mở trước hay sau write? Có checkpoint hoặc resumeAt đúng?
5. **Pipeline:** bộ lọc `operationType`, `fullDocument` và `ns` có loại event không?
6. **Full document policy:** có body null vì delete/update mặc định không?
7. **Resume state:** token còn trong oplog, có giữ pipeline/options như cũ?
8. **Errors:** có `onError` hoặc `ErrorHandler` bị bỏ qua/log thiếu?
9. **Downstream:** event đã nhận nhưng handler/channels thất bại?

Không bật full collection scan mỗi khi change stream lỗi. Cần phân biệt **không nhận sự kiện** với **nhận nhưng không xử lý**, và có quy trình rebuild khi lịch sử đã mất.

### 23.2. Lỗi phân loại theo event body

Một consumer có thể cần:

```java
switch (event.getOperationType()) {
    case INSERT, REPLACE -> {
        // getBody() thường có; xác nhận không null.
    }
    case UPDATE -> {
        // updateDescription có thể đủ; body phụ thuộc policy.
    }
    case DELETE -> {
        // Document key, và pre-image nếu được bật.
    }
    default -> {
        // Drop, rename, invalidate, DDL... có policy riêng.
    }
}
```

Đây là **skeleton switch** nằm trong một method có `event`, không phải handler production hoàn chỉnh. Nếu `getOperationType()` có thể null, hãy kiểm tra trước khi switch. Enum `OperationType` còn có giá trị theo phiên bản driver/server; có `default` để handler không làm sai dữ liệu khi gặp loại mới.

### 23.3. Đừng retry mọi lỗi y hệt

Một `retryWhen(Retry.max(Long.MAX_VALUE))` bên ngoài stream không giải quyết:

- Sai quyền.
- Sai pipeline.
- Token không còn trong oplog.
- Event poison pill khiến handler luôn lỗi.
- Invalidate và collection đổi schema.

Phân loại lỗi **recoverable** (mạng/election, với driver có thể tự resume) và **non-recoverable** (pipeline sai, thiếu quyền, token invalid). Dùng retry budget/backoff/jitter, trạng thái fail-fast/alert và cơ chế manual reconciliation khi cần.

## 24. Checklist thiết kế ChangeStreamOptions

1. **Chọn scope đúng:** một collection hay toàn database? Có nhiều schema không?
2. **Chọn kiểu body đúng:** `OrderDocument` cho một collection, `Document` khi heterogenous.
3. **Chọn operation types:** có cần insert/update/replace/delete/invalidate không?
4. **Chọn raw hay Aggregation filter:** field ở envelope hay ở `fullDocument`?
5. **Giữ event._id:** không project/unset/replace làm mất resume token.
6. **Chọn fullDocument policy:** mặc định delta, `UPDATE_LOOKUP` hay pre/post images?
7. **Không giả định body luôn có:** nhánh delete/update/lookup missing.
8. **Dùng updateDescription đúng:** field changed, removedFields, truncatedArrays.
9. **Chọn resume mode:** `resumeAfter`, `startAfter` hoặc `resumeAt` theo trường hợp.
10. **Checkpoint bền vững:** token lưu theo stream identity/pipeline version.
11. **Đúng thứ tự:** durable processing → checkpoint, không ngược lại.
12. **Idempotency:** có thể replay event sau crash hoặc chạy nhiều replicas.
13. **Lập kế hoạch oplog expiry:** không thể replay lịch sử vô hạn.
14. **Quản lý lifecycle:** start/stop/cancel cursor, không tạo vô hạn watchers.
15. **Backpressure:** consumer không giữ buffer vô hạn hoặc checkpoint vượt event chưa xong.
16. **Bảo mật:** không lộ raw event/PII, lọc tenant sau khi xác thực.
17. **Test trên replica set:** kiểm tra event types, raw fields, typed body và resume.
18. **Test pipeline mapping:** `Aggregation` có thể prefix field thành `fullDocument.`.
19. **Test invalidate/pre-image:** chỉ trên database test riêng, cấu hình hỗ trợ.
20. **Giám sát:** lag, reconnect, resume failure, processing, checkpoint age, duplicates.

## 25. Bài tập thực hành

Một hệ thống thương mại điện tử lưu `orders` và đồng bộ read model `order_search`. Bản ghi đơn hàng có `_id`, `tenantId`, `status`, `totalMinor`, `updatedAt`. Read model cần nhận cập nhật và xóa tương ứng, đồng thời có khả năng restart consumer mà không mất sự kiện.

### Bài tập 1 — Phân loại cấu trúc sự kiện

Xem sự kiện:

```javascript
{
  _id: { _data: "<opaque-token-E1>" },
  operationType: "update",
  documentKey: { _id: "ORD-101" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Trả lời:

1. `event._id` là token hay ID đơn hàng?
2. Lấy ID đơn hàng ở field nào?
3. Vì sao `getBody()` có thể null?
4. Có thể suy ra `tenantId` từ sự kiện này không nếu delta không chứa nó?
5. Có nên phát `OrderPaid` ngay chỉ vì `fullDocument.status` có thể là PAID khi tra cứu không?

**Gợi ý:** cần phân biệt trạng thái tại một update operation, snapshot tra cứu sau update và dữ liệu domain/tenant authoritative.

### Bài tập 2 — Filter bằng raw Document

Viết `ChangeStreamOptions` chỉ nhận:

- `insert`,
- `update`,
- `replace`,

và bật `returnFullDocumentOnUpdate()`. Sau đó thêm `delete` và giải thích vì sao handler không được coi `getBody()` là nonnull cho mọi event.

Đáp án tham khảo:

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(new Document("$match",
        new Document("operationType",
            new Document("$in",
                List.of("insert", "update",
                        "replace", "delete")))))
    .returnFullDocumentOnUpdate()
    .build();
```

Trong code thật, dùng imports `Document`/`List` phù hợp. Tách xử lý `delete` theo `documentKey`.

### Bài tập 3 — Filter theo delta

Muốn chỉ nhận những update thao tác trên `status`, xây:

```javascript
{
  $match: {
    operationType: "update",
    "updateDescription.updatedFields.status": {
      $exists: true
    }
  }
}
```

Giải thích:

1. Vì sao filter này không đảm bảo bắt `replace`?
2. Vì sao có update chỉ đổi `updatedAt` bị loại?
3. Nếu status được update rồi document lập tức được update tiếp, vì sao `UPDATE_LOOKUP` có thể trả trạng thái khác?
4. Khi schema có field path chứa dấu chấm, cần lưu ý những gì?

### Bài tập 4 — Aggregation mapping khác raw BSON

So sánh:

```java
Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("operationType").is("update")));
```

với:

```java
new Document("$match",
    new Document("updateDescription.updatedFields.status",
        new Document("$exists", true)));
```

Hãy nêu trường nào thuộc **event envelope**, trường nào thuộc **domain document**, vì sao mapping có thể tự thêm `fullDocument.`, và khi nào cần `TypedAggregation` hoặc raw `Document`.

### Bài tập 5 — Token và pipeline projection

Một developer muốn giảm payload bằng:

```javascript
{
  $project: {
    _id: 0,
    operationType: 1,
    documentKey: 1
  }
}
```

Hãy sửa để giữ `_id` và giải thích:

- Vì sao token khác `documentKey._id`?
- Vì sao từ MongoDB 4.2 việc sửa `event._id` có thể làm stream lỗi?
- Khi đổi pipeline, vì sao phải kiểm tra khả năng resume từ checkpoint cũ?

### Bài tập 6 — updateLookup và pre-image

Cho timeline:

```text
10:00:00  status=NEW
10:00:01  update NEW -> PAID       (E1)
10:00:02  update PAID -> SHIPPED   (E2)
10:00:03  consumer reads E1 with UPDATE_LOOKUP
```

Câu hỏi:

1. `E1.updateDescription.updatedFields.status` là gì?
2. `E1.fullDocument.status` có thể là gì?
3. `getBodyBeforeChange()` cần điều kiện gì để có trước ảnh?
4. Nếu chính sách `WHEN_AVAILABLE` không có image, handler nên làm gì?
5. Khi nào nên dùng outbox event `OrderPaid` thay vì suy từ fullDocument?

### Bài tập 7 — Consumer và checkpoint

Cho code:

```java
// PHẢN VÍ DỤ:
source.flatMap(event ->
    checkpoints.save(event.getResumeToken())
        .then(handler.process(event)));
```

Chỉ ra ít nhất ba lỗi:

1. Checkpoint được ghi **trước** xử lý.
2. `flatMap` có thể ghi token sự kiện sau trước khi sự kiện trước hoàn tất.
3. Handler thất bại có thể khiến sự kiện bị bỏ qua sau resume.

Sửa bằng xử lý `concatMap` tuần tự và chỉ checkpoint sau `handler.process(event)` hoàn thành bền vững; bổ sung idempotency.

### Bài tập 8 — Restart và duplicate

Mô phỏng:

```text
Event E1 processed
Checkpoint R1 saved
Event E2 processed
Crash before checkpoint R2
Restart with resumeAfter(R1)
E2 delivered again
```

Xây cơ chế dedupe theo event ID/token hoặc idempotent business write. Hãy mô tả cách tránh nhân đôi `$inc` hoặc gửi email hai lần.

### Bài tập 9 — Invalidate và oplog window

1. Drop một collection **test riêng** rồi quan sát `invalidate`.
2. Vì sao `resumeAfter(invalidateToken)` không tương đương `startAfter(invalidateToken)`?
3. Nếu token đã bị oplog cuốn mất, tại sao retry vô hạn không giúp?
4. Làm sao resnapshot/backfill read model một cách an toàn?
5. Vì sao phải giữ pipeline/options nhất quán khi resume?

### Bài tập 10 — Test StepVerifier

Trên replica set test:

1. Thiết lập resume token R hoặc cơ chế server-side cursor readiness.
2. Insert `OrderDocument` có ID ngẫu nhiên vào `orders`.
3. Subscribe stream từ R, dùng `take(1)` sau khi lọc event test.
4. Xác minh `operationType`, `getResumeToken()`, `getRaw().getDocumentKey()` và `getBody()`.
5. Update và delete document, xác minh các loại event có body/delta khác nhau.
6. Không dùng `Thread.sleep` cố định để chứng minh watcher đã sẵn.
7. Cleanup đúng test IDs, không drop database dùng chung.

### Bài tập 11 — Thiết kế pipeline nhiều tenant

Một stream watch database có cả `orders`, `customers` và `audit_events`. Hãy:

- Dùng `ChangeStreamEvent<Document>` thay cho ép về `OrderDocument`.
- Kiểm tra `getCollectionName()` trước khi convert.
- Xác minh `tenantId` từ nguồn đáng tin cậy.
- Tránh phát nguyên raw event tới client không đủ quyền.
- Xác định event delete không có fullDocument sẽ được route tenant thế nào.
- Đề xuất phương án outbox nếu identity của tenant không thể lấy an toàn từ delete event.

### Bài tập 12 — Xử lý sự cố

Hệ thống báo:

```text
change_stream_events_received_total      tăng
change_stream_events_processed_total     không tăng
change_stream_checkpoint_age_seconds     tăng
change_stream_resume_failed_total        chưa tăng
```

Hãy đánh giá khả năng handler downstream đang lỗi/chậm, queue bị nghẽn hoặc `onError` không được quan sát. Đề xuất trace và metric để xác định event bị dừng ở pha nào, cùng chính sách retry/dead-letter/alert **không checkpoint event chưa xử lý**.

## 26. Câu hỏi tự kiểm tra

| Câu hỏi | Gợi ý đáp án |
| --- | --- |
| Change stream hỗ trợ standalone MongoDB không? | Thường không; cần replica set/sharded cluster hỗ trợ |
| Event `_id` là gì? | Resume token, không phải document ID |
| `documentKey` dùng khi nào? | Định danh document, đặc biệt với delete |
| `getBody()` luôn có với update? | Không; mặc định update delta, lookup có thể vẫn null |
| `getRaw()` giúp gì? | Đọc envelope, updateDescription/documentKey và metadata không có trong entity |
| `filter(Aggregation)` và `filter(Document...)` khác nhau? | Spring mapping/prefix versus raw BSON stages |
| Khi nào dùng `returnFullDocumentOnUpdate()`? | Khi muốn lookup document hiện tại cho update và chấp nhận hạn chế |
| Có thể bỏ `_id` trong `$project`? | Không, cần giữ resume token |
| `resumeAfter` có dùng sau invalidate không? | Không theo quy tắc MongoDB; cân nhắc `startAfter` |
| Resume token có tồn tại mãi không? | Không; phụ thuộc oplog/history |
| Thời điểm ghi checkpoint? | Sau durable processing |
| Vì sao cần idempotency? | Resume/retry có thể phát lại event |
| Có được map mọi collection thành `OrderDocument`? | Không, khi nhiều schema nên dùng raw `Document`/router |
| `clusterTime` có là unique event ID không? | Không; có thể trùng giữa các events |
| `Flux` có tự phát khi chưa subscribe không? | Không |
| `concatMap` có ích gì cho checkpoint? | Giữ thứ tự xử lý events |
| Change stream có phải message broker consumer group? | Không, mỗi cursor có thể nhìn cùng events |

## 27. Tài liệu tham khảo

- Spring Data MongoDB — [Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html): imperative `MessageListenerContainer`, reactive `ChangeStreamEvent` và resume.
- Spring Data MongoDB API — [ChangeStreamOptions](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.html): builder, getter, các tuỳ chọn stream.
- Spring Data MongoDB API — [ChangeStreamOptionsBuilder](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.ChangeStreamOptionsBuilder.html): `filter(Aggregation)`, `filter(Document...)`, `resumeAfter`, `startAfter`, `returnFullDocumentOnUpdate`.
- Spring Data MongoDB API — [ChangeStreamEvent](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamEvent.html): `getBody`, `getBodyBeforeChange`, `getRaw`, `getResumeToken`, timestamps.
- Spring Data MongoDB API — [ReactiveMongoOperations](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoOperations.html): `changeStream(String, ChangeStreamOptions, Class<T>)` và fluent API.
- Spring Data MongoDB API — [ReactiveChangeStreamOperation.ChangeStreamWithOptions](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveChangeStreamOperation.ChangeStreamWithOptions.html): `withOptions(Consumer<ChangeStreamOptionsBuilder>)`.
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changestreams/): resume, invalidation, options/pipeline, oplog history.
- MongoDB Manual — [Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/): event envelope, `update`/`delete`/`replace` và token.
- MongoDB Manual — [Update Event](https://www.mongodb.com/docs/manual/reference/change-events/update/): `updateDescription`, updated/removed fields và path semantics.
- MongoDB Manual — [`$changeStream` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/): fullDocument policy, `resumeAfter`/`startAfter` và pre/post images.
- MongoDB Manual — [Collection Watch](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/): tùy chọn watch và ngữ nghĩa cursor.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscription, `concatMap`, error handling và backpressure.

## Ghi nhớ

**`ChangeStreamOptions` quyết định bộ lọc pipeline, full-document lookup, pre/post images và điểm bắt đầu đọc sự kiện; `ChangeStreamEvent<T>` là envelope chứa cả entity đã convert lẫn metadata MongoDB.** `getBody()` có thể null, vì update mặc định thường chỉ có `updateDescription` và delete thường chỉ có `documentKey`. Phân biệt event `_id` (resume token) với document `_id`; không xóa token khỏi `$project`. Với `filter(Aggregation)`, cần hiểu quy tắc map domain fields thành `fullDocument.*`, còn `filter(Document...)` giữ BSON paths raw. Sau khi xử lý bền vững mới lưu checkpoint; khi resume giữ pipeline/options ổn định, theo dõi oplog window, chấp nhận khả năng event replay và thiết kế consumer idempotent. Hãy kiểm thử insert/update/replace/delete, full document, raw event và resume trên MongoDB replica set thật trước khi đưa change streams vào production.
