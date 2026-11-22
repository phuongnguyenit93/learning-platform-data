# Document đầy đủ, mô tả cập nhật và dữ liệu trước/sau thay đổi trong Change Streams

## Mục tiêu của bài học

Trong **Spring Data MongoDB**, change stream cho phép ứng dụng nhận sự kiện khi document được thêm, cập nhật, thay thế hoặc xóa mà không phải liên tục polling collection. Tuy nhiên, một sự kiện thay đổi không phải lúc nào cũng chứa toàn bộ trạng thái document. Với sự kiện `update`, mặc định MongoDB thường chỉ trả phần mô tả **trường nào đã thay đổi**; nếu cần document đầy đủ hay trạng thái **trước/sau** thay đổi, phải chọn đúng tùy chọn của change stream và đáp ứng điều kiện hỗ trợ của MongoDB.

Bài học thuộc chương **Change stream**, tập trung vào ba nhóm thông tin:

1. `updateDescription`: mô tả thay đổi dạng delta, gồm giá trị mới của các trường được cập nhật, tên trường bị xóa và thông tin mảng bị rút ngắn khi có.
2. `fullDocument`: document đầy đủ sau thao tác hoặc bản đọc lại gần thời điểm xử lý change event, tùy chế độ `fullDocument`.
3. `fullDocumentBeforeChange`: **pre-image**, tức ảnh chụp document trước thao tác; kết hợp chế độ post-image để so sánh chính xác trước/sau khi hệ thống hỗ trợ.

Ta sẽ sử dụng `mongosh` để quan sát BSON event, rồi dùng `ReactiveMongoTemplate` và `ChangeStreamOptions` để ánh xạ dữ liệu trong Java. Các nguyên tắc về resume token, độ trễ, chi phí lưu trữ và lỗi thiếu image cũng áp dụng khi dùng MongoDB Java Driver hoặc cơ chế listener đồng bộ của Spring Data.

> **Điều kiện chạy:** change streams yêu cầu MongoDB deployment hỗ trợ, điển hình là replica set hoặc sharded cluster; standalone MongoDB thông thường không đáp ứng. Pre/post-images được giới thiệu trong MongoDB **6.0** và cần bật riêng cho collection. Ví dụ Spring Data dùng API `getBodyBeforeChange()` và `fullDocumentBeforeChangeLookup(...)` có trong Spring Data MongoDB **4.0+**; hãy đối chiếu đúng phiên bản server, Java driver và Spring Data của dự án.

## 1. Một event trong change stream có những phần nào?

Giả sử collection `orders` lưu đơn hàng:

```javascript
db.orders.insertOne({
  _id: "order-42",
  status: "CREATED",
  amount: 100,
  coupon: "WELCOME"
});
```

Mở một terminal `mongosh` khác để theo dõi thay đổi **trước khi thực hiện update**:

```javascript
const stream = db.orders.watch();

while (stream.hasNext()) {
  printjson(stream.next());
}
```

Trong terminal ghi dữ liệu, chạy:

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  {
    $set: { status: "PAID", amount: 120 },
    $unset: { coupon: "" }
  }
);
```

Một sự kiện có thể có cấu trúc minh họa như sau (đã lược bớt metadata; resume token thật có dạng BSON và giá trị không cố định):

```javascript
{
  _id: { _data: "<resume-token>" },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: { db: "shop", coll: "orders" },
  documentKey: { _id: "order-42" },
  updateDescription: {
    updatedFields: { status: "PAID", amount: 120 },
    removedFields: ["coupon"],
    truncatedArrays: []
  }
}
```

| Trường event | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `_id` | Resume token dùng tiếp tục stream tại vị trí đã biết | Không phải `_id` của đơn hàng; không được xóa hoặc sửa trong pipeline |
| `operationType` | Kiểu sự kiện: `insert`, `update`, `replace`, `delete`, ... | Quyết định trường nào có ý nghĩa |
| `clusterTime` | Thời điểm logic gắn với thao tác trong oplog | Không đồng nghĩa thời gian ứng dụng xử lý event |
| `ns` | Namespace database và collection | Có thể phục vụ định tuyến ở các stream phạm vi rộng |
| `documentKey` | Định danh document chịu tác động, gồm `_id` và có thể gồm thông tin shard key | Dùng xác định bản ghi thay đổi |
| `updateDescription` | Mô tả phần thay đổi cho `update` | Không chứa đầy đủ document hay giá trị cũ của trường |
| `fullDocument` | Document đầy đủ khi có sẵn hoặc được yêu cầu theo chế độ phù hợp | Có thể vắng mặt hoặc `null` ở `update` |
| `fullDocumentBeforeChange` | Pre-image nếu được bật và yêu cầu | Có thể vắng mặt hoặc `null` khi không có image |

**Đừng nhầm ba loại ID:** `event._id` là resume token; `documentKey._id` là ID của document; `fullDocument._id` là ID nằm trong bản đầy đủ của document (nếu có).

Sự kiện không chứa body đầy đủ chưa chắc là lỗi. Với `update`, đó thường là hành vi mặc định để giảm lượng dữ liệu phải truyền.

## 2. Hiểu đúng updateDescription

Đối với thao tác `update`, MongoDB thường cung cấp:

```javascript
updateDescription: {
  updatedFields: { "status": "PAID", "amount": 120 },
  removedFields: ["coupon"],
  truncatedArrays: []
}
```

### updatedFields: giá trị mới của trường thay đổi

`updatedFields` ánh xạ đường dẫn trường đến **giá trị mới**. Đối với `$set`, đó thường là giá trị vừa gán; với `$inc`, nó phản ánh giá trị sau tăng/giảm, không phải phép toán `$inc` gốc.

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  { $inc: { amount: 10 } }
);

// Ví dụ delta tương ứng (khi amount trước đó là 120):
// updateDescription.updatedFields: { amount: 130 }
```

Vì vậy, từ `updatedFields: { amount: 130 }` **không suy ra được** amount trước đó là 120; chỉ biết giá trị sau update. Nếu nghiệp vụ cần tính chênh lệch chính xác, phải có trạng thái trước đó (pre-image, một snapshot được quản lý riêng hoặc một nguồn dữ liệu đủ tin cậy).

Với trường lồng nhau, key thường biểu diễn bằng dot notation:

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  { $set: { "delivery.city": "Hà Nội" } }
);

// Ví dụ:
// updatedFields: { "delivery.city": "Hà Nội" }
```

Nếu tên trường thật có dấu chấm hoặc key dạng số gây mơ hồ với vị trí phần tử mảng, MongoDB có thể cung cấp `updateDescription.disambiguatedPaths` để mô tả các thành phần đường dẫn. Trường này được thêm từ MongoDB 6.1 và điều kiện phát sinh còn phụ thuộc phiên bản/tùy chọn `showExpandedEvents`; không nên tự tách mọi key bằng dấu chấm rồi coi đó là đường dẫn chắc chắn.

### removedFields: tên trường bị xóa

`removedFields` chứa danh sách đường dẫn trường đã bị loại bỏ, chẳng hạn `["coupon"]` sau `$unset`. Nó **không chứa giá trị cũ** của trường. Khi cần biết mã khuyến mãi nào đã bị xóa, phải đọc pre-image hoặc lưu lịch sử ở nơi khác.

### truncatedArrays: thay đổi độ dài mảng

Đối với một số cập nhật bằng aggregation pipeline làm cắt ngắn mảng, MongoDB có thể trả:

```javascript
updateDescription: {
  updatedFields: {},
  removedFields: [],
  truncatedArrays: [
    { field: "items", newSize: 2 }
  ]
}
```

`truncatedArrays` cho biết tên mảng và kích thước mới. Tùy cách update, MongoDB cũng có thể báo thay thế cả mảng trong `updatedFields` thay vì báo truncate riêng. Không nên giả định mọi sửa đổi mảng đều sinh `truncatedArrays`.

### update, replace và delete khác nhau

- `update`: thường có `updateDescription`; `fullDocument` phụ thuộc tùy chọn stream.
- `replace`: khi thay toàn bộ document, sự kiện mang `fullDocument` chứa nội dung thay thế; không nên dựa vào `updateDescription` như với update từng trường.
- `delete`: document đã không còn, nên không có document sau xóa để đọc. Nếu pre-image sẵn có, `fullDocumentBeforeChange` cho biết giá trị trước lúc xóa.
- `insert`: có `fullDocument` của bản ghi mới; không có pre-image trước khi chèn.

## 3. fullDocument: mặc định, updateLookup và post-image

`fullDocument` có một số chế độ quan trọng:

| Giá trị `fullDocument` | Với sự kiện update | Yêu cầu |
| --- | --- | --- |
| `"default"` | Thường không trả full document, vẫn có delta | Không cần bật pre/post-images |
| `"updateLookup"` | Đọc document đang tồn tại tại lúc lookup, ở trạng thái majority-committed; có thể `null` | Không cần bật pre/post-images |
| `"whenAvailable"` | Trả **post-image gắn với sự kiện** nếu có; khi không có, giá trị `null` | MongoDB 6.0+ và bật pre/post-images cho collection |
| `"required"` | Yêu cầu post-image; báo lỗi nếu image không sẵn có | MongoDB 6.0+ và bật pre/post-images cho collection |

`"default"` là hành vi thông thường. Với `insert` và `replace`, full document có sẵn theo bản chất sự kiện; với `delete` không có post-document.

### updateLookup: bản đầy đủ tại lúc đọc lại

```javascript
const stream = db.orders.watch([], {
  fullDocument: "updateLookup"
});

while (stream.hasNext()) {
  const event = stream.next();
  printjson({
    operation: event.operationType,
    delta: event.updateDescription,
    currentDocument: event.fullDocument
  });
}
```

Với `updateLookup`, MongoDB đọc lại bản **hiện tại đã majority-committed** của document được sửa. Nếu document bị xóa trước khi lookup, `fullDocument` có thể là `null`. Nếu một update khác xảy ra nhanh sau update gây event, bản đọc lại có thể đã chứa **các thay đổi đến sau**:

```text
t1: order-42  status=CREATED
t2: update A  status=PAID      -> event A: updatedFields.status=PAID
t3: update B  status=SHIPPED   -> event B: updatedFields.status=SHIPPED
t4: lookup cho event A        -> fullDocument.status có thể là SHIPPED
```

Do đó, `updateDescription` của event A và `fullDocument` từ `updateLookup` có thể phản ánh **hai thời điểm khác nhau**. Đây không phải dữ liệu hỏng mà là tính chất của thao tác đọc lại. Không dùng `updateLookup` làm nguồn chứng minh tuyệt đối cho ảnh sau *chính xác tại thời điểm event* nếu có ghi đồng thời.

Trong một số tình huống xóa nhanh, việc lọc change stream bằng trường `fullDocument` kết hợp `updateLookup` còn có thể làm phức tạp khôi phục resume token; phải thử nghiệm cách lọc và cơ chế resume thay vì chỉ trông vào body đọc lại.

### whenAvailable và required: post-image của sự kiện

Sau khi bật pre/post-images, MongoDB có thể trả nội dung sau thay đổi tương ứng với **chính thao tác** gây ra event bằng `"whenAvailable"` hoặc `"required"`. Đây là cách phù hợp khi cần biết trạng thái ngay sau update, thay vì bản mới nhất ở thời điểm lookup.

- `whenAvailable`: tiếp tục stream khi thiếu image; phía ứng dụng phải xử lý `null`.
- `required`: stream lỗi nếu image được yêu cầu mà không có. Chỉ nên dùng khi nghiệp vụ thực sự yêu cầu image cho mỗi event thuộc phạm vi hỗ trợ và đã có cơ chế giám sát/khôi phục phù hợp.

## 4. Bật và đọc pre-image/post-image trong MongoDB 6.0+

Pre-image là document **trước khi** `update`, `replace` hoặc `delete`. Post-image là document **sau khi** `insert`, `update` hoặc `replace`. Không có pre-image cho `insert` và không có post-image cho `delete`.

Để bật ghi image cho collection `orders` đã tồn tại:

```javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: { enabled: true }
});
```

Bật tính năng **trước khi thực hiện các thay đổi muốn theo dõi**. MongoDB không tự tạo pre-image lịch sử cho những update/delete đã xảy ra trước lúc bật.

Trong cửa sổ A, mở stream và yêu cầu cả hai ảnh:

```javascript
const stream = db.orders.watch([], {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
});

while (stream.hasNext()) {
  const event = stream.next();
  printjson({
    operationType: event.operationType,
    documentKey: event.documentKey,
    before: event.fullDocumentBeforeChange,
    delta: event.updateDescription,
    after: event.fullDocument,
    resumeToken: event._id
  });
}
```

Trong cửa sổ B, chạy một update:

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  {
    $set: { status: "SHIPPED", amount: 140 },
    $unset: { coupon: "" }
  }
);
```

Ví dụ logic của một event update, với giả thiết bản ghi ngay trước đó có `status: "PAID"`, `amount: 120` và không còn `coupon`:

```javascript
{
  operationType: "update",
  documentKey: { _id: "order-42" },
  before: {
    _id: "order-42",
    status: "PAID",
    amount: 120
  },
  delta: {
    updatedFields: { status: "SHIPPED", amount: 140 },
    removedFields: [],
    truncatedArrays: []
  },
  after: {
    _id: "order-42",
    status: "SHIPPED",
    amount: 140
  },
  resumeToken: { _data: "<resume-token>" }
}
```

Đây là **minh họa cấu trúc**, không phải kết quả thực thi hay cam kết về thứ tự trường BSON. Trong thao tác này `$unset` không có tác dụng nếu `coupon` đã vắng mặt; vì thế `removedFields` có thể rỗng. Nếu muốn kiểm tra `removedFields`, hãy đặt một giá trị `coupon` mới rồi xóa nó trong một update sau.

Sau đó thử xóa:

```javascript
db.orders.deleteOne({ _id: "order-42" });
```

Ở event `delete`, `fullDocument` không còn bản sau; khi pre-image sẵn có, `fullDocumentBeforeChange` chứa document ngay trước khi xóa. Không dùng `updateLookup` để cố lấy document đã xóa: lúc lookup, bản ghi có thể không tồn tại.

### Tùy chọn pre-image

| `fullDocumentBeforeChange` | Hành vi |
| --- | --- |
| `"off"` (mặc định) | Không yêu cầu pre-image |
| `"whenAvailable"` | Trả pre-image khi có; nếu thiếu có thể là `null` |
| `"required"` | Báo lỗi nếu không thể lấy pre-image khi event cần pre-image |

Để dùng `"required"` có ý nghĩa, cần đảm bảo collection đã được cấu hình trước thời điểm update/delete và image không bị hết hạn trước khi consumer đọc. Không phải tất cả event (ví dụ `insert` hoặc `invalidate`) đều có khái niệm pre-image.

### Lưu trữ và giới hạn cần tính đến

Pre/post-images làm tăng chi phí lưu trữ và xử lý. Ảnh có thể bị xóa theo chính sách lưu giữ và vòng đời oplog. Việc bật collection sau khi thay đổi đã xảy ra không bổ sung ảnh lịch sử; do đó `whenAvailable` phải được xử lý như kiểu dữ liệu có thể thiếu. Chế độ `required` biến tình trạng thiếu ảnh thành lỗi cần can thiệp.

Một change event có giới hạn kích thước BSON **16 MiB**. Nếu yêu cầu cả pre-image, post-image và phần mô tả thay đổi lớn, tổng payload có thể vượt ngưỡng dù từng document riêng lẻ hợp lệ. Cần đặc biệt thận trọng với document gần 16 MiB và những collection có cập nhật thường xuyên. Với hệ thống cần lưu vết dài hạn, chính sách image retention không thay thế kho audit hoặc lịch sử nghiệp vụ được thiết kế riêng.

## 5. Ánh xạ trong Spring Data MongoDB

Trong Spring Data MongoDB, `ChangeStreamOptions` chọn cách server cung cấp document, còn `ChangeStreamEvent<T>` cung cấp dữ liệu đã ánh xạ và bản sự kiện gốc từ Java driver.

### Entity và DTO quan sát

Ví dụ một entity đơn giản (đặt trong file `OrderSnapshot.java`):

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderSnapshot(
    @Id String id,
    String status,
    Integer amount,
    String coupon
) {}
```

DTO nội bộ cho consumer (đặt trong file `OrderChange.java`):

```java
import java.util.List;
import org.bson.BsonDocument;
import org.bson.BsonValue;
import com.mongodb.client.model.changestream.OperationType;

public record OrderChange(
    OperationType operationType,
    BsonValue resumeToken,
    OrderSnapshot before,
    OrderSnapshot after,
    BsonDocument updatedFields,
    List<String> removedFields
) {}
```

`OrderSnapshot` biểu diễn một trạng thái đầy đủ khi có, còn `OrderChange` chứa hai trạng thái và delta. Trường `before`/`after` đều **có thể null**, tùy operation và tùy chọn stream. Bản ví dụ không lưu resume token ra file; `BsonValue` được giữ nguyên trong tầng xử lý để tránh biến đổi mất thông tin.

### ReactiveMongoTemplate: lấy body trước/sau và delta

```java
import java.util.List;

import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;
import com.mongodb.client.model.changestream.UpdateDescription;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class OrderChangeService {

    private final ReactiveMongoTemplate template;

    public OrderChangeService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<OrderChange> changes() {
        ChangeStreamOptions options = ChangeStreamOptions.builder()
            .fullDocumentLookup(FullDocument.WHEN_AVAILABLE)
            .fullDocumentBeforeChangeLookup(
                FullDocumentBeforeChange.WHEN_AVAILABLE
            )
            .build();

        return template.changeStream(
            "orders", options, OrderSnapshot.class
        ).map(this::toChange);
    }

    private OrderChange toChange(ChangeStreamEvent<OrderSnapshot> event) {
        var raw = event.getRaw();
        UpdateDescription delta =
            raw == null ? null : raw.getUpdateDescription();

        return new OrderChange(
            event.getOperationType(),
            event.getResumeToken(),
            event.getBodyBeforeChange(),
            event.getBody(),
            delta == null ? null : delta.getUpdatedFields(),
            delta == null || delta.getRemovedFields() == null
                ? List.of()
                : delta.getRemovedFields()
        );
    }
}
```

Ở đoạn code trên:

- `fullDocumentLookup(FullDocument.WHEN_AVAILABLE)` yêu cầu **post-image** nếu có. Có thể thay bằng `FullDocument.UPDATE_LOOKUP` nếu cần đọc document hiện tại mà chưa bật pre/post-images; hai kiểu có ý nghĩa thời điểm khác nhau.
- `fullDocumentBeforeChangeLookup(FullDocumentBeforeChange.WHEN_AVAILABLE)` yêu cầu pre-image. Nếu muốn thiếu ảnh khiến stream lỗi, dùng `FullDocumentBeforeChange.REQUIRED`.
- `event.getBody()` ánh xạ từ `fullDocument`; `event.getBodyBeforeChange()` ánh xạ từ `fullDocumentBeforeChange`. API trước thay đổi có từ Spring Data MongoDB 4.0.
- `event.getRaw()` trả `ChangeStreamDocument<Document>` của MongoDB Java driver; `getUpdateDescription()` truy xuất delta cho `update`. Trong các event khác, delta có thể là `null`.
- `event.getResumeToken()` dùng để lưu vị trí tiếp tục stream. Token là BSON; khi lưu lâu dài phải bảo toàn cấu trúc và kiểu dữ liệu.
- `Flux` chưa thực sự nhận event cho đến khi có subscriber. Change stream có thể chạy lâu dài; cần đặt nó trong lifecycle của một consumer được quản lý, thay vì tạo subscription mới cho mọi HTTP request.

Nếu chưa cần pre-image, có thể đọc document hiện tại khi update:

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .returnFullDocumentOnUpdate()
    .build();

// Tương đương chọn fullDocumentLookup(FullDocument.UPDATE_LOOKUP).
```

**Cảnh báo về độ chính xác:** `returnFullDocumentOnUpdate()` tiện để dựng lại một read model ở trạng thái gần hiện tại, nhưng `getBody()` của nó có thể phản ánh thay đổi xảy ra **sau** `updateDescription` trong event đó.

### Đọc từ MongoDB Java Driver trực tiếp

Khi cần quan sát cấu trúc BSON mà không qua conversion của Spring Data:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;
import org.bson.Document;

MongoCollection<Document> orders =
    mongoClient.getDatabase("shop").getCollection("orders");

var cursor = orders.watch()
    .fullDocument(FullDocument.WHEN_AVAILABLE)
    .fullDocumentBeforeChange(FullDocumentBeforeChange.WHEN_AVAILABLE)
    .iterator();

try (cursor) {
    while (cursor.hasNext()) {
        var event = cursor.next();
        System.out.println("operation=" + event.getOperationType());
        System.out.println("delta=" + event.getUpdateDescription());
        System.out.println("before=" + event.getFullDocumentBeforeChange());
        System.out.println("after=" + event.getFullDocument());
    }
}
```

Ví dụ này giả sử có một biến `mongoClient` kiểu `com.mongodb.client.MongoClient` đã được khởi tạo và kết nối hợp lệ. Đây là vòng lặp chặn thread, phù hợp minh họa hoặc worker chuyên dụng có cơ chế đóng cursor; không đặt trực tiếp vào thread xử lý HTTP. Đối với ứng dụng có Spring Data reactive, `ReactiveMongoTemplate` giúp tích hợp vòng đời subscription, backpressure và xử lý lỗi với Reactor.

## 6. Chọn dữ liệu phù hợp với mục đích sử dụng

| Nhu cầu | Nên đọc | Lý do |
| --- | --- | --- |
| Gửi thông báo “đơn đã đổi trạng thái” | `updateDescription.updatedFields` | Gọn, không cần đọc lại cả document |
| Cập nhật cache/read model với trạng thái hiện tại | `fullDocument: "updateLookup"` hoặc post-image | Cần body; xác định rõ yêu cầu về thời điểm |
| Tính sự khác biệt **trước và sau chính update** | Pre-image + post-image | Hai ảnh gắn với sự kiện, nếu hỗ trợ và sẵn có |
| Audit: biết giá trị đã bị `$unset` | `fullDocumentBeforeChange` | `removedFields` chỉ chứa tên trường |
| Hiển thị bản ghi vừa `insert` | `fullDocument` mặc định | Insert event đã chứa document được chèn |
| Ghi nhận document vừa `delete` | `fullDocumentBeforeChange` | Không còn post-document sau xóa |
| Chỉ cần thống kê số sự kiện | `operationType`, `documentKey`, metadata | Tránh thêm chi phí image không cần thiết |

Dù chọn cách nào, dữ liệu nhận được vẫn phải qua kiểm tra quyền truy cập và bảo mật. Pre-image có thể chứa giá trị đã bị xóa hoặc che khỏi UI hiện tại; không tự động đưa nguyên vẹn pre/post-images lên log công khai hoặc gửi qua websocket.

## 7. Resume token, thứ tự xử lý và vận hành

Một consumer lâu dài thường phải:

1. Nhận event và lấy resume token gốc từ `ChangeStreamEvent.getResumeToken()`.
2. Xử lý công việc nghiệp vụ hoặc lưu vào outbox/queue theo mô hình đã thiết kế.
3. **Chỉ ghi checkpoint token sau khi side effect được xử lý đủ an toàn**. Nếu checkpoint trước khi xử lý, crash có thể làm mất cơ hội chạy lại event.
4. Khi khởi động lại, dùng token đã lưu qua `ChangeStreamOptions.builder().resumeAfter(token).build()` (hoặc cơ chế resume tương ứng của driver) để tiếp tục, với điều kiện token còn hợp lệ trong thời gian oplog lưu giữ.
5. Thiết kế side effect **idempotent** theo định danh event/nghiệp vụ, vì sự cố giữa xử lý và checkpoint có thể khiến một event được xử lý lại.

Lưu token với đúng kiểu BSON, không chuyển sang chuỗi hiển thị rồi suy ngược tùy ý. Không xóa hoặc thay đổi `_id` của change event trong pipeline, vì đó là resume token; việc biến đổi `_id` có thể làm stream lỗi.

### Những giới hạn quan trọng

- **Không phải snapshot toàn bộ collection:** watch chỉ nhận các thay đổi trong phạm vi và thời điểm stream hỗ trợ; nếu cần bản hiện tại ban đầu, phải phối hợp với quy trình snapshot/initial load.
- **Không phải hàng đợi lưu vết vĩnh viễn:** việc resume phụ thuộc oplog, trạng thái collection và tính hợp lệ của token; nếu ứng dụng dừng quá lâu, phải có chiến lược tái đồng bộ.
- **Không có exactly-once end-to-end mặc định:** consumer có thể thực hiện lại side effect khi retry. Cần checkpoint và idempotency.
- **Không đảm bảo có pre/post-image nếu chưa bật hoặc image đã hết hạn:** đặc biệt lưu ý các event phát sinh trước khi cấu hình.
- **Không đảm bảo lookup đúng thời điểm event:** `updateLookup` đọc bản hiện tại đã majority-committed, có thể là trạng thái mới hơn.
- **Không phù hợp để thay thế transaction/audit log có tính pháp lý:** với yêu cầu lưu lịch sử bắt buộc, cân nhắc ghi sự kiện nghiệp vụ bền vững trong transaction/outbox được thiết kế riêng.

### Các sự cố thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách chẩn đoán và xử lý |
| --- | --- | --- |
| `getBody() == null` ở event update | Dùng mặc định, lookup không tìm thấy, hoặc thiếu post-image | Kiểm tra `fullDocument` option và trạng thái image |
| `getBodyBeforeChange() == null` | Chưa yêu cầu, chưa bật image, không thuộc loại event, hoặc ảnh đã hết hạn | Kiểm tra `collMod`, phiên bản và thời điểm phát sinh event |
| Stream lỗi khi dùng `REQUIRED` | Pre/post-image được yêu cầu không còn tồn tại | Xác định retention và cách khôi phục/đồng bộ lại |
| `updateDescription == null` | Sự kiện `insert`, `replace`, `delete` hoặc sự kiện không phải update | Phân nhánh theo `operationType` |
| `updatedFields` không có giá trị cũ | Delta chỉ lưu giá trị sau thay đổi | Dùng pre-image hoặc lưu lịch sử riêng |
| `fullDocument` khác delta | Có update đến sau trước khi `updateLookup` chạy | Dùng post-image nếu cần ảnh chính xác |
| Không thể mở stream | Standalone hoặc deployment/role không hỗ trợ | Kiểm tra topology, quyền `changeStream` và phiên bản |
| Consumer trễ, token không hợp lệ | Oplog hoặc dữ liệu image không còn đáp ứng khôi phục | Theo dõi lag, checkpoint và chuẩn bị initial resync |
| Không nhận event dù dữ liệu có thay đổi | Chưa subscribe `Flux` hoặc watcher được mở sau thao tác | Bảo đảm subscription sống và tạo thay đổi mới sau đó |
| Payload quá lớn | Full document và ảnh trước/sau vượt giới hạn 16 MiB | Giảm kích thước document hoặc bớt yêu cầu image |

## 8. Thực hành và kiểm chứng

**Bài tập 1 — Delta:** Chạy watcher mặc định, thực hiện `$set`, `$inc`, `$unset` và update một trường lồng nhau. In `updatedFields` và `removedFields`. Giải thích vì sao delta không cho biết giá trị cũ.

**Bài tập 2 — updateLookup:** Bật `fullDocument: "updateLookup"`. Cho hai update liên tiếp trên cùng một document và quan sát `fullDocument` cùng `updateDescription`. Giải thích tại sao có thể khác nhau, kể cả khi sự khác biệt không xuất hiện trong một lần chạy thử do timing.

**Bài tập 3 — Pre/post-images:** Trên replica set MongoDB 6.0+, bật `changeStreamPreAndPostImages`, chạy watcher với hai tùy chọn `whenAvailable`. Thực hiện `update`, `replace`, `delete` và điền bảng: operation, before, delta, after. Chỉ rõ trường nào có thể `null`.

**Bài tập 4 — REQUIRED và retention:** Thử `fullDocumentBeforeChange: "required"` trên môi trường kiểm thử, quan sát hành vi nếu pre-image không có hoặc phát sinh sự kiện từ trước khi bật tính năng. Giải thích cách ứng dụng cần xử lý lỗi thay vì lặng lẽ bỏ qua.

**Bài tập 5 — Spring Data:** Hoàn thiện `OrderChangeService`, viết consumer nhận `OrderChange` rồi lưu checkpoint an toàn. Mô phỏng restart và kiểm tra idempotency của xử lý event. Không lưu token trước khi side effect hoàn tất.

### Checklist hoàn thành

- Phân biệt được `documentKey._id` với resume token `event._id`.
- Nêu đúng ý nghĩa `updatedFields`, `removedFields`, `truncatedArrays` và giới hạn về giá trị cũ.
- Giải thích tại sao `updateLookup` có thể đọc bản mới hơn thời điểm xảy ra event.
- Phân biệt `whenAvailable` và `required` cho pre/post-image, và biết điều kiện MongoDB 6.0+.
- Xác định dữ liệu có thể thiếu theo `insert`, `update`, `replace`, `delete`.
- Sử dụng `ChangeStreamOptions`, `getBody()`, `getBodyBeforeChange()`, `getRaw()` và `getResumeToken()` đúng mục đích.
- Thiết kế consumer có checkpoint, xử lý lặp và tránh gửi ảnh nhạy cảm ra ngoài.

## Tài liệu tham khảo

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/)
- [MongoDB Manual — `$changeStream` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changestream/)
- [MongoDB Manual — `db.collection.watch()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [MongoDB Manual — Update Change Event](https://www.mongodb.com/docs/manual/reference/change-events/update/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [Spring Data MongoDB — `ChangeStreamOptions.ChangeStreamOptionsBuilder` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.ChangeStreamOptionsBuilder.html)
- [Spring Data MongoDB — `ChangeStreamEvent<T>` API](https://docs.spring.io/spring-data/data-mongodb/reference/api/java/org/springframework/data/mongodb/core/ChangeStreamEvent.html)
- [Spring Data MongoDB — `ReactiveMongoOperations` API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoOperations.html)
