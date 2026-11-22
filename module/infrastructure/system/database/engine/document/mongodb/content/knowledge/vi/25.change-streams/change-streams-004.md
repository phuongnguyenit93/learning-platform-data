# Lọc, biến đổi sự kiện và bảo toàn resume token trong MongoDB Change Streams

**MongoDB Change Streams** cho phép ứng dụng theo dõi các thay đổi dữ liệu gần thời gian thực thay vì liên tục chạy truy vấn polling. Một consumer có thể lọc event, chỉ giữ field cần thiết rồi đồng bộ search index, cache, read model, dịch vụ thông báo hoặc hệ thống phân tích.

Điều làm change stream khác một aggregation thông thường là **resume token**: field **_id của change event** chứa token do MongoDB cấp để xác định vị trí tiếp tục đọc. Nếu một pipeline dùng $project, $unset, $set hoặc $replaceRoot khiến _id bị loại bỏ hay thay đổi, khả năng resume bị ảnh hưởng; MongoDB có cơ chế từ chối các pipeline biến đổi resume token. Khi xây dựng consumer chịu lỗi, **giữ nguyên token là điều kiện bắt buộc nhưng chưa đủ**: còn phải checkpoint đúng thứ tự, xử lý retry và idempotency.

Bài học tập trung vào:

1. Cấu trúc change event và khác biệt giữa **event._id** với **documentKey._id**.
2. Dùng **$match**, **$project**, **$addFields**, **$unset**, **$replaceRoot** để lọc và chuẩn hóa event mà vẫn giữ resume token.
3. **resumeAfter**, **startAfter**, **startAtOperationTime**, **post-batch resume token (PBRT)** và giới hạn thời gian lưu history.
4. Checkpoint đúng thời điểm, xử lý song song, failure recovery, idempotency và triển khai bằng **MongoDB Java Sync Driver**.
5. Các tình huống production: sharded change streams, updateLookup, pre/post images, invalidate, thay đổi pipeline và monitoring.

Mọi ví dụ thao tác dữ liệu dùng collection thử nghiệm **cdc_lab.orders**. Để mở change stream cần replica set hoặc sharded cluster được hỗ trợ; standalone mongod thông thường không đáp ứng yêu cầu này.

## 1. Change stream là gì?

Một change stream là một cursor dài hạn phát sự kiện khi dữ liệu được thay đổi. Sự kiện có thể thuộc nhiều operation type, chẳng hạn insert, update, replace, delete hoặc những hoạt động vòng đời namespace và DDL trong phạm vi/version hỗ trợ.

Có các phạm vi theo dõi:

| Phạm vi | API thường dùng | Mục đích |
| --- | --- | --- |
| Collection | **db.orders.watch()** | Chỉ theo dõi orders |
| Database | **db.watch()** | Theo dõi nhiều collection trong database |
| Deployment | **MongoClient.watch()** trong driver | Theo dõi dữ liệu trên phạm vi triển khai hỗ trợ |

Ví dụ mongosh:

~~~javascript
use cdc_lab

const stream = db.orders.watch();

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
~~~

Cursor có thể chờ lâu nếu chưa có thay đổi. Để quan sát, nên chạy watcher trong một terminal và tạo insert/update từ terminal khác.

### 1.1. Phân biệt source change với event nghiệp vụ

Change event phản ánh một thay đổi trên MongoDB. Nó không nhất thiết có cùng ý nghĩa với business event.

Ví dụ update status thành PAID không tự chứng minh đã thu tiền thành công theo quy tắc thanh toán, hay tất cả side effects khác đã hoàn tất. Nếu nghiệp vụ cần các invariant như thanh toán và publish event cùng thành công, cần thiết kế outbox/transaction/idempotency riêng.

### 1.2. Change stream không phải lịch sử vô hạn

Consumer chỉ có thể resume từ những điểm còn được lịch sử oplog/change stream hỗ trợ. Nó không tự phục vụ yêu cầu phát lại mọi event của nhiều năm.

## 2. Cấu trúc một change event

Document đơn hàng:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "C-01",
  status: "PENDING",
  totalCents: NumberLong(150000)
}
~~~

Khi chạy:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

Event update có thể có dạng khái quát:

~~~javascript
{
  _id: {
    _data: "OPAQUE_RESUME_TOKEN"
  },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: {
    db: "cdc_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-1001"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
~~~

Đây là hình minh họa, không phải token thực có thể copy để resume. Các field tùy operation type, watch options và phiên bản.

### 2.1. Những field cần hiểu

| Field | Ý nghĩa |
| --- | --- |
| **_id** | Resume token của **sự kiện** |
| **operationType** | insert, update, replace, delete... |
| **clusterTime** | Mốc thời gian logic của thay đổi |
| **ns** | Database/collection liên quan |
| **documentKey** | Khóa của document thay đổi |
| **updateDescription** | Các field được đổi, xóa, thông tin array tương ứng |
| **fullDocument** | Hình ảnh document khi được cung cấp |
| **fullDocumentBeforeChange** | Pre-image nếu tính năng/cấu hình cho phép |

Không có nghĩa mọi event đều có fullDocument. Delete thường không có nội dung đầy đủ của document đã xóa.

### 2.2. event._id khác documentKey._id

~~~javascript
change._id
// Ví dụ một BsonDocument chứa resume token.

change.documentKey._id
// "ORD-1001": ID của order được cập nhật.
~~~

Nếu cùng order bị sửa năm lần, documentKey._id có thể giống nhau nhưng resume token khác nhau ở mỗi event.

**Không dùng documentKey._id làm token cho resumeAfter.** Nó không xác định được vị trí sự kiện trong luồng.

### 2.3. Token là BSON opaque

Mặc dù token thường trông như document có field _data, ứng dụng không nên:

- Chỉ trích _data và bỏ những field khác.
- Giải mã _data bằng logic nội bộ tự viết.
- Tự tạo token từ clusterTime hoặc documentKey.
- So sánh hai token bằng thứ tự từ điển của chuỗi JSON.
- Thay token bằng timestamp, ObjectId hoặc string cho dễ lưu.

Hãy giữ **toàn bộ BSON value nguyên vẹn**.

## 3. Chuẩn bị môi trường thử nghiệm

Sử dụng replica set/sharded cluster thử nghiệm, không chạy những lệnh bên dưới trên dữ liệu thật khi chưa có quyền.

~~~javascript
use cdc_lab

db.orders.insertMany([
  {
    _id: "ORD-1001",
    customerId: "C-01",
    region: "APAC",
    status: "PENDING",
    totalCents: NumberLong(150000),
    email: "alice@example.test"
  },
  {
    _id: "ORD-1002",
    customerId: "C-02",
    region: "EMEA",
    status: "PAID",
    totalCents: NumberLong(250000),
    email: "bob@example.test"
  },
  {
    _id: "ORD-1003",
    customerId: "C-03",
    region: "APAC",
    status: "DRAFT",
    totalCents: NumberLong(99000)
  }
]);
~~~

Terminal A, mở watcher:

~~~javascript
use cdc_lab

const watcher = db.orders.watch();

while (watcher.hasNext()) {
  printjson(watcher.next());
}
~~~

Terminal B, tạo changes:

~~~javascript
use cdc_lab

db.orders.updateOne(
  { _id: "ORD-1001" },
  { $set: { status: "PAID" } }
);

db.orders.insertOne({
  _id: "ORD-1004",
  status: "PENDING",
  customerId: "C-04",
  region: "APAC",
  totalCents: NumberLong(180000)
});

db.orders.deleteOne({ _id: "ORD-1003" });
~~~

Watcher mới mở không tự đọc toàn bộ những thay đổi đã xảy ra từ trước. Nếu phải dựng snapshot ban đầu và tiếp tục CDC không mất khoảng trống, cần một quy trình snapshot+stream cụ thể.

## 4. Pipeline của change stream

API watch nhận một aggregation pipeline xử lý **change event**. Người dùng không cần tự chèn $changeStream stage khi gọi watch().

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: "update"
    }
  }
]);
~~~

Không phải mọi aggregation stage đều hợp lệ sau $changeStream. Những stage thường được hỗ trợ trong change stream pipeline gồm:

- **$match**
- **$project**
- **$addFields / $set**
- **$unset**
- **$replaceRoot / $replaceWith**
- **$redact**

Tập stage được hỗ trợ và giới hạn cụ thể phụ thuộc phiên bản; không tự đưa $group, $sort, $lookup, $out, $merge hay stage tùy ý vào change stream pipeline.

### 4.1. Điều kiện bất biến

Khi tạo pipeline, **không thay đổi hoặc xóa _id của change event**.

MongoDB có cơ chế phát hiện và trả lỗi nếu pipeline làm mất hoặc thay resume token. Đừng dựa vào việc consumer có thể “tự dựng lại” token từ payload đã biến đổi.

### 4.2. Lọc từ source khác với lọc tại client

Khi dùng $match trong watch, server có thể loại event không cần thiết trước khi trả về application, giảm bandwidth và khối lượng xử lý tại consumer.

Tuy nhiên, điều đó không có nghĩa mọi filter miễn phí hay thay đổi cách dữ liệu nguồn được ghi. Phần lịch sử dưới source vẫn phải được xử lý theo cơ chế MongoDB.

## 5. $match theo operationType

Chỉ quan tâm insert và update:

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update"]
      }
    }
  }
]);
~~~

Một search index mirror thường phải quan tâm:

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

Nếu quên **delete**, dữ liệu trên search index có thể không bị xóa khi document nguồn đã mất.

### 5.1. Một số operationType cần phân biệt

| Operation | Payload/ý nghĩa thường gặp |
| --- | --- |
| insert | Document mới; có thể có fullDocument |
| update | Có updateDescription; fullDocument tùy option |
| replace | Document được thay thế; thường có fullDocument |
| delete | documentKey, không mặc nhiên có fullDocument |
| drop / rename | Sự kiện lifecycle tùy watch scope |
| invalidate | Stream bị invalidated theo ngữ nghĩa namespace |
| DDL mở rộng | Phụ thuộc phiên bản/tùy chọn showExpandedEvents |

Không nên giả định consumer chỉ cần update vì ứng dụng đôi khi dùng replaceOne hoặc các thao tác khác để sửa dữ liệu.

### 5.2. Lọc theo documentKey

~~~javascript
db.orders.watch([
  {
    $match: {
      "documentKey._id": "ORD-1001"
    }
  }
]);
~~~

Đây là lọc theo ID document nghiệp vụ, **không** phải resume token.

Trong sharded collection, documentKey có thể có thêm các field shard key liên quan. Không giả định cấu trúc documentKey luôn chỉ có _id.

## 6. Lọc theo namespace ở phạm vi database

Khi watch cả database:

~~~javascript
db.watch([
  {
    $match: {
      "ns.coll": {
        $in: ["orders", "payments"]
      },
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

Trong deployment-scope watch, khi cần phân biệt những collection cùng tên ở database khác nhau, lọc cả **ns.db** và **ns.coll**.

Một $match chỉ có ns.coll = "orders" không đủ nếu deployment có nhiều database đều chứa collection orders.

## 7. Lọc updateDescription

Một update bằng $set/$unset:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID",
      updatedBy: "payment-service"
    },
    $unset: {
      oldNote: ""
    }
  }
);
~~~

Event có thể bao gồm:

~~~javascript
{
  operationType: "update",
  updateDescription: {
    updatedFields: {
      status: "PAID",
      updatedBy: "payment-service"
    },
    removedFields: ["oldNote"]
  }
}
~~~

### 7.1. Lọc event set status thành PAID

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: "update",
      "updateDescription.updatedFields.status": "PAID"
    }
  }
]);
~~~

Điều này chứng minh **sự kiện update mô tả status vừa được set bằng PAID**. Nó không tự chứng minh trạng thái trước đó là PENDING.

Nếu nghiệp vụ yêu cầu chuyển trạng thái **PENDING → PAID**, cần nguồn trạng thái cũ: pre-image, business transition metadata hoặc một cơ chế khác phù hợp.

### 7.2. Field name chứa dấu chấm

Với thay đổi field lồng nhau, updateDescription.updatedFields có thể chứa key nguyên văn như **"shipping.city"**. Lúc này một field path thông thường:

~~~javascript
"$updateDescription.updatedFields.shipping.city"
~~~

không nhất thiết truy cập đúng key literal. Có thể dùng $getField ở phiên bản hỗ trợ:

~~~javascript
{
  $getField: {
    field: "shipping.city",
    input: "$updateDescription.updatedFields"
  }
}
~~~

Cần kiểm tra schema event thực tế; đừng mặc định mọi updatedFields đều là object lồng theo dotted path.

### 7.3. Delete event không có status cũ mặc định

Không nên viết:

~~~javascript
{
  $match: {
    operationType: "delete",
    "fullDocument.status": "PAID"
  }
}
~~~

rồi kỳ vọng nó trả mọi delete của order từng PAID. Delete thường có documentKey, còn status trước khi xóa chỉ có khi được cung cấp bởi pre-image hoặc một nguồn khác.

## 8. fullDocument và updateLookup

Với update event, mặc định change stream có thể chỉ mang updateDescription. Muốn lấy document đầy đủ hiện hành sau cập nhật, có thể bật:

~~~javascript
db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace"]
        }
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

### 8.1. updateLookup có thể đọc trạng thái mới hơn thời điểm event

Giả sử:

~~~text
T1: order đổi PENDING -> PAID  (event E1)
T2: order đổi PAID -> REFUNDED (event E2)
T3: updateLookup được thực hiện cho E1
~~~

fullDocument của E1 có thể phản ánh trạng thái tại thời điểm lookup, khác với trạng thái ngay sau E1. Nó cũng có thể vắng mặt nếu document bị xóa sau đó.

Vì vậy:

- **updateDescription** thích hợp để biết field nào event vừa cập nhật.
- **updateLookup** thích hợp khi cần lấy document hiện hành.
- Muốn pre/post image gắn với sự kiện thì xem tính năng pre/post images theo phiên bản.

### 8.2. Lọc theo fullDocument.status

~~~javascript
db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace"]
        },
        "fullDocument.status": "PAID"
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

Filter này không nhất thiết chỉ chọn những event **chuyển sang PAID**. Một update khác trên order vốn đã PAID cũng có thể match nếu fullDocument.status = PAID.

### 8.3. Chi phí lookup

Tra cứu fullDocument có thể tăng I/O và kích thước event. Nếu consumer chỉ cần vài field trong updateDescription, không nhất thiết phải bật updateLookup.

## 9. Pre-images và post-images

MongoDB ở những phiên bản phù hợp hỗ trợ lưu **change stream pre- and post-images** khi cấu hình collection.

Ví dụ lệnh cấu hình trong lab:

~~~javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

Đây là thay đổi cấu hình; không chạy trên production khi chưa biết phiên bản, retention, dung lượng và quyền quản trị.

### 9.1. Pre-image

Có thể yêu cầu fullDocumentBeforeChange theo mode được hỗ trợ, như **whenAvailable** hoặc **required**.

Nếu pre-image không được lưu hoặc đã hết thời gian retention, consumer không thể mặc định có dữ liệu cũ.

### 9.2. Post-image

Một số mode fullDocument như **whenAvailable** hoặc **required** có thể sử dụng post-image đã được lưu khi feature tương ứng được bật. Không đồng nhất post-image này với updateLookup lấy document hiện hành sau thay đổi.

### 9.3. Token vẫn độc lập với image

Ngay cả khi fullDocumentBeforeChange và fullDocument được cung cấp đầy đủ, **event._id mới là resume token**. Không dùng ảnh document để tái tạo vị trí stream.

## 10. $project: giảm payload, giữ nguyên _id

Consumer chỉ cần vài field:

~~~javascript
db.orders.watch(
  [
    {
      $project: {
        _id: 1,
        operationType: 1,
        ns: 1,
        clusterTime: 1,
        documentKey: 1,
        updateDescription: 1,
        "fullDocument.status": 1,
        "fullDocument.totalCents": 1
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

### 10.1. Vì sao _id: 1 được viết tường minh?

Trong aggregation thông thường, $project có thể giữ _id mặc định nếu không loại nó. Nhưng với change stream, viết **_id: 1** làm rõ rằng token phải được bảo toàn và giúp người sửa pipeline không nhầm nó với documentKey._id.

### 10.2. Ví dụ sai: loại _id

~~~javascript
{
  $project: {
    _id: 0,
    operationType: 1,
    documentKey: 1
  }
}
~~~

Thao tác này làm mất resume token trong output; change stream không được phép thay đổi token.

### 10.3. Ví dụ sai: thay _id bằng business ID

~~~javascript
{
  $project: {
    _id: "$documentKey._id",
    operationType: 1
  }
}
~~~

Đây là thay event ID bằng ID của order. Một event mới và event cũ của cùng order không còn có token riêng.

Cách đúng là giữ _id và thêm field khác:

~~~javascript
{
  $addFields: {
    businessId: "$documentKey._id"
  }
}
~~~

## 11. $unset: bỏ thông tin không cần thiết

Ví dụ fullDocument có PII:

~~~javascript
{
  $unset: [
    "fullDocument.email",
    "fullDocument.phone",
    "fullDocument.address"
  ]
}
~~~

Không thêm **"_id"** vào $unset. Nếu consumer cần documentKey để xóa cache hoặc index khi delete, cũng không bỏ documentKey một cách thiếu chủ đích.

Projection chỉ giảm dữ liệu được cung cấp cho downstream; nó không thay thế authentication, authorization, TLS, mã hóa và kiểm soát logs.

## 12. $addFields / $set: tạo metadata dẫn xuất

~~~javascript
db.orders.watch([
  {
    $addFields: {
      eventKind: {
        $concat: [
          "order.",
          "$operationType"
        ]
      },
      businessId: "$documentKey._id"
    }
  }
]);
~~~

Event có thêm eventKind và businessId, **event._id không bị thay**.

### 12.1. Chuẩn hóa theo operationType

~~~javascript
{
  $addFields: {
    businessAction: {
      $switch: {
        branches: [
          {
            case: { $eq: ["$operationType", "insert"] },
            then: "created"
          },
          {
            case: { $eq: ["$operationType", "delete"] },
            then: "removed"
          }
        ],
        default: "changed"
      }
    }
  }
}
~~~

### 12.2. Không dùng $set để ghi đè token

Sai:

~~~javascript
{
  $set: {
    _id: "$documentKey._id"
  }
}
~~~

Muốn định danh record nghiệp vụ, tạo **businessId** thay vì thay _id của event.

### 12.3. Missing/fullDocument null

~~~javascript
{
  $addFields: {
    visibleStatus: {
      $ifNull: [
        "$fullDocument.status",
        "UNKNOWN"
      ]
    }
  }
}
~~~

UNKNOWN trong output không nhất thiết có nghĩa document nguồn mang status UNKNOWN. Nó có thể chỉ là do fullDocument không tồn tại hoặc field null.

## 13. $replaceRoot: thay hình dạng nhưng không mất token

Một cách viết rất dễ sai:

~~~javascript
{
  $replaceRoot: {
    newRoot: "$fullDocument"
  }
}
~~~

fullDocument._id là **document ID**, không phải resume token. Hơn nữa delete event có thể không có fullDocument.

### 13.1. Thay root đúng cách

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      _id: "$_id",
      operationType: "$operationType",
      namespace: "$ns",
      businessId: "$documentKey._id",
      payload: "$fullDocument",
      changedFields: "$updateDescription.updatedFields"
    }
  }
}
~~~

Result root vẫn giữ **_id: "$_id"**, tức là chính resume token do server cấp.

### 13.2. Lỗi $mergeObjects ghi đè _id

Nếu merge fullDocument vào event:

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        "$$ROOT",
        "$fullDocument"
      ]
    }
  }
}
~~~

có nguy cơ **fullDocument._id** ghi đè **event._id** vì object ở phía sau có ưu tiên với field trùng trong $mergeObjects. Cách an toàn và dễ đọc là tạo root tường minh với _id giữ từ event.

### 13.3. Không biến token thành string trong root

~~~javascript
{
  $project: {
    _id: {
      $toString: "$_id"
    }
  }
}
~~~

Dù dễ in log, việc này làm đổi kiểu/giá trị token và không phù hợp với bất biến của change stream. Nếu cần dạng text để lưu, serialize **toàn bộ BSON token** bên ngoài output _id theo API driver.

## 14. Pipeline hoàn chỉnh: lọc và biến đổi an toàn

Yêu cầu: chỉ nhận insert/update/replace/delete, không gửi email, có businessId, giữ nguyên resume token.

~~~javascript
const pipeline = [
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      operationType: 1,
      clusterTime: 1,
      ns: 1,
      documentKey: 1,
      updateDescription: 1,
      "fullDocument._id": 1,
      "fullDocument.status": 1,
      "fullDocument.totalCents": 1
    }
  },
  {
    $addFields: {
      businessId: "$documentKey._id",
      eventKind: {
        $concat: [
          "orders.",
          "$operationType"
        ]
      }
    }
  }
];

const stream = db.orders.watch(
  pipeline,
  {
    fullDocument: "updateLookup"
  }
);

while (stream.hasNext()) {
  printjson(stream.next());
}
~~~

### 14.1. Các field nên giữ theo nghiệp vụ

| Field | Tại sao giữ |
| --- | --- |
| _id | Resume token |
| operationType | Phân biệt insert/update/replace/delete |
| documentKey | Xác định document đích kể cả khi delete |
| ns | Phân biệt collection ở watch scope rộng |
| clusterTime | Telemetry/thời gian logic |
| updateDescription | Field mới được cập nhật |
| fullDocument | Dữ liệu cần đồng bộ, khi có |

### 14.2. Vì sao không nhất thiết nên lọc delete?

Một consumer đồng bộ search index nếu bỏ delete sẽ giữ record đã xóa, dẫn đến dữ liệu đích sai. Filter phải phản ánh yêu cầu sink chứ không chỉ tối ưu event rate.

## 15. Resume token: ý nghĩa

**Resume token** là BSON value được MongoDB cấp để định vị change stream.

Các option quan trọng:

- **resumeAfter:** tiếp tục đọc sau token cụ thể.
- **startAfter:** bắt đầu sau token, đặc biệt quan trọng khi cần đi qua invalidate theo ngữ nghĩa hỗ trợ.
- **startAtOperationTime:** bắt đầu từ một BSON operation timestamp; không phải token.

Token không phải datetime, không phải clusterTime đơn thuần và không phải documentKey.

### 15.1. Token không phải một thứ tự string có thể so sánh

Không dùng thứ tự lexical của _data hoặc JSON để quyết định event mới hơn. Thứ tự xử lý được quản lý qua cursor/order và checkpoint của consumer, không phải bằng sort token tùy tiện.

### 15.2. Watch scope và pipeline gắn với checkpoint

Một token thu được từ pipeline A không nên được sử dụng bừa bãi như checkpoint của consumer B có namespace/pipeline khác. Metadata checkpoint nên lưu consumerId, scope và pipelineVersion.

## 16. resumeAfter sau khi restart

Giả sử consumer nhận một event:

~~~javascript
const stream = db.orders.watch();

const change = stream.next();

const token = change._id;

// Xử lý change thành công rồi mới lưu token.
~~~

Ở lần chạy sau:

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    resumeAfter: token
  }
);
~~~

Theo ngữ nghĩa resume, stream tiếp tục sau vị trí event đã cho.

### 16.1. Checkpoint phải theo tiến độ xử lý

Chuỗi đúng:

~~~text
Nhận E1 -> xử lý E1 thành công -> lưu token E1
Nhận E2 -> xử lý E2 thành công -> lưu token E2
Nhận E3 -> crash trước khi xử lý
Restart resumeAfter(E2)
E3 có thể được đọc tiếp
~~~

Chuỗi nguy hiểm:

~~~text
Nhận E3
Lưu token E3
Crash trước khi xử lý E3
Restart resumeAfter(E3)
E3 bị bỏ qua
~~~

Đừng lưu token ngay khi cursor giao event nếu business handler chưa commit thành công.

### 16.2. Đọc ahead/batch buffering

Driver có thể đọc một batch trước khi ứng dụng xử lý xong từng event. Token được dùng để checkpoint không được tiến vượt qua event vẫn còn pending.

**Checkpoint phản ánh mọi event trước vị trí đó đã được xử lý thành công**, không chỉ “driver đã từng nhìn thấy vị trí này”.

## 17. Post-batch resume token (PBRT)

Một consumer có thể lọc rất mạnh: ví dụ chỉ nhận status chuyển PAID, trong khi nguồn liên tục có nhiều loại update khác.

Server có thể trả **postBatchResumeToken** trong phản hồi batch/getMore, kể cả khi batch không có event thỏa filter được trả tới ứng dụng.

### 17.1. Vì sao cần PBRT?

Nếu consumer chỉ lưu token của event cuối cùng mà nó **nhìn thấy**, checkpoint có thể đứng yên nhiều giờ hoặc ngày dù cursor liên tục đọc các batch mới.

Khi restart, token quá cũ có thể hết lịch sử oplog cần thiết.

PBRT cho phép theo dõi tiến độ đọc tới vị trí cuối batch an toàn mà không cần tạo một event giả.

### 17.2. Không checkpoint PBRT trước event chưa xử lý

Chỉ lưu cursor/post-batch token nếu:

1. Driver cung cấp token hợp lệ.
2. Mọi event được giao trước vị trí đó đã xử lý thành công.
3. Không có worker pending trên event cũ hơn.
4. Checkpoint bền vững và đúng consumer ownership.

Nếu còn E101 đang pending nhưng cursor đã đọc tới E110, không được checkpoint E110.

### 17.3. PBRT không kéo dài oplog

PBRT giúp checkpoint không quá cũ khi ít event match. Nó không tự lưu thêm lịch sử trên server và không thể phục hồi token đã hết hạn.

## 18. startAfter và invalidate

Change stream có thể nhận **invalidate** trong các thao tác lifecycle của namespace, ví dụ collection drop/rename theo scope watch.

### 18.1. resumeAfter không đi qua invalidate như event thường

Không dùng resumeAfter để tiếp tục sau invalidate theo cách thông thường.

### 18.2. startAfter

Khi phiên bản/scope cho phép theo dõi sau invalidate event:

~~~javascript
db.orders.watch(
  [],
  {
    startAfter: invalidateToken
  }
);
~~~

Cần hiểu namespace có thể đã bị drop, rename hoặc tạo lại; consumer không được mặc định schema/dữ liệu cũ vẫn tồn tại.

### 18.3. Lọc invalidate và lifecycle

Nếu $match chỉ lấy update, consumer có thể không nhìn thấy những event lifecycle quan trọng dù cursor bị invalidated. Cần quan sát cursor completion, lỗi và kế hoạch khôi phục, không chỉ đếm matched events.

## 19. startAtOperationTime

Một số tình huống hỗ trợ mở stream từ **BSON Timestamp** hợp lệ:

~~~javascript
db.orders.watch(
  [],
  {
    startAtOperationTime: Timestamp({
      t: 1762000000,
      i: 1
    })
  }
);
~~~

Timestamp trên chỉ minh họa. Trong thực tế phải dùng operation time được ghi nhận phù hợp từ server/session và nằm trong lịch sử còn sẵn.

### 19.1. Không đồng nhất timestamp và token

BSON Timestamp khác JavaScript Date. Nó cũng không thay resume token vốn chứa vị trí cụ thể hơn trong luồng.

### 19.2. Không tự fallback từ token hỏng sang watch từ hiện tại

Nếu history lost khiến resumeAfter thất bại, bắt đầu từ “bây giờ” mà không backfill có thể tạo khoảng trống dữ liệu và khiến downstream sai.

## 20. Oplog và lỗi mất lịch sử

Change streams phụ thuộc lịch sử replication/change stream còn được MongoDB giữ.

Nếu consumer offline lâu hơn cửa sổ lịch sử, việc resume có thể thất bại với lỗi nhóm **ChangeStreamHistoryLost** hoặc lỗi liên quan tùy phiên bản/trạng thái.

### 20.1. Nguyên nhân thường gặp

- Tốc độ write cao làm oplog window co lại.
- Consumer dừng dài ngày.
- Checkpoint không tiến do filter rất chọn lọc và không lưu PBRT.
- Thay đổi topology/namespace làm token không còn khả dụng.
- Retention của pre/post images không đáp ứng nhu cầu payload.

### 20.2. Không retry vô hạn token không thể resume

Sai:

~~~text
while true:
  resumeAfter(oldToken)
  if history lost:
    sleep 1 second
    retry forever
~~~

Lịch sử bị ghi đè không tự xuất hiện lại nhờ retry.

### 20.3. Quy trình an toàn

1. Dừng consumer hoặc đánh dấu cần can thiệp.
2. Lưu lại lỗi, consumerId, token, pipelineVersion và thời điểm.
3. Phân biệt lỗi mạng tạm thời với history lost/invalidate.
4. Đối soát source và sink.
5. Làm resnapshot/backfill hoặc rebuild phù hợp.
6. Khởi tạo checkpoint mới không tạo gap theo quy trình.
7. Điều chỉnh oplog/lag monitoring để tránh tái diễn.

## 21. Exactly-once không tự có từ resume token

Nếu consumer thực hiện side effect trước khi checkpoint:

~~~text
Nhận E100
Gọi external API thành công
Crash trước khi lưu token E100
Restart resumeAfter(E99)
Nhận lại E100
Gọi API lần hai
~~~

Đó là một ví dụ **at-least-once**: event có thể được xử lý lại.

### 21.1. Checkpoint trước effect còn nguy hiểm hơn

~~~text
Nhận E100
Lưu token E100
Crash trước khi thực hiện effect
Restart resumeAfter(E100)
E100 không được xử lý
~~~

Vì vậy checkpoint nên xảy ra **sau khi effect commit thành công**, đồng thời cần idempotency để xử lý replay.

### 21.2. Idempotency ở sink

Có thể sử dụng business event ID hoặc một khóa event được biểu diễn ổn định từ token để phát hiện event đã xử lý.

Ví dụ ý tưởng:

~~~javascript
db.processedEvents.updateOne(
  {
    consumerId: "orders-search-indexer",
    eventKey: "STABLE_EVENT_KEY"
  },
  {
    $setOnInsert: {
      processedAt: new Date()
    }
  },
  {
    upsert: true
  }
);
~~~

Marker này không tự nguyên tử với một side effect ở collection khác. Nếu cả hai write cùng MongoDB, có thể cần transaction; nếu sink là API ngoài, cần idempotency key mà API hỗ trợ.

### 21.3. Exactly-once là đặc tính end-to-end

Phải xem:

- Sự kiện nguồn.
- Retry/resume.
- Checkpoint.
- Side effect.
- Crash/restart.
- Duplicate.
- Transaction boundary/idempotency.
- Thay đổi pipeline và replay.

Không tuyên bố exactly-once chỉ vì consumer có resumeAfter.

## 22. Xử lý song song và committed watermark

Giả sử ba worker xử lý song song:

~~~text
E101 -> Worker A pending
E102 -> Worker B done
E103 -> Worker C done
~~~

Nếu checkpoint token E103 và crash, E101 sẽ bị bỏ qua sau resume.

### 22.1. Prefix liên tục

Chỉ checkpoint đến event cuối của một **prefix đã xử lý đầy đủ**:

~~~text
E100 done
E101 pending
E102 done
E103 done

Checkpoint an toàn: E100
~~~

Khi E101 hoàn thành, có thể nâng checkpoint tới E103, nếu không còn event chưa xử lý trước đó.

### 22.2. Ordering theo document

Nếu cùng document có E1 đổi status và E2 đổi total, xử lý E2 xong trước E1 có thể làm downstream sai dù checkpoint được quản lý. Cần cân nhắc partition theo documentKey hoặc cơ chế giữ thứ tự cho những business keys yêu cầu ordering.

### 22.3. PBRT và queue

Không dùng PBRT để vượt pending events trong worker queue. PBRT là một vị trí có thể resume về mặt stream, không phải sự xác nhận đã hoàn tất business effects.

## 23. Lưu token đúng kiểu dữ liệu

Các lựa chọn:

1. Lưu toàn bộ token dưới dạng BSON document.
2. Serialize bằng Extended JSON bảo toàn BSON types, rồi parse lại bằng API tương ứng.

Ví dụ metadata checkpoint:

~~~javascript
{
  _id: "orders-consumer-v3",
  tokenExtendedJson: "{...}",
  pipelineVersion: 3,
  watchScope: "cdc_lab.orders",
  updatedAt: ISODate("2026-11-14T05:00:00Z")
}
~~~

### 23.1. Vì sao lưu pipelineVersion?

Nếu filter v1 bỏ delete nhưng v2 cần delete, resume từ token của v1 không làm những delete cũ xuất hiện lại.

Checkpoint gắn với một **ý nghĩa xử lý**. Khi đổi logic, cần đánh giá backfill/rebuild hoặc cutover.

### 23.2. Không chỉnh _data

Không sửa, cắt, ghép hoặc so sánh trường _data theo trực giác. Token có thể có cấu trúc phức tạp hơn giữa các phiên bản và sharded deployments.

### 23.3. Bảo vệ checkpoint

Checkpoint nên có cơ chế durable write, hạn chế quyền ghi, backup/phục hồi, kiểm soát ownership và metric để phát hiện khi lưu không thành công.

## 24. Hai consumers dùng chung checkpoint: race condition

Giả sử:

~~~text
Pod A đọc token E100 -> xử lý E101..E105
Pod B đọc token E100 -> xử lý E101..E110

Pod B lưu E110
Pod A sau đó lưu E105
~~~

Checkpoint có thể lùi, hoặc tiến vượt vị trí mà pod khác thực sự đã xử lý.

### 24.1. Unique checkpoint ID chưa đủ

Unique index trên consumerId giúp có một document checkpoint nhưng không ngăn hai processes thay nhau update nó.

### 24.2. Ownership và fencing

Các mô hình thường dùng:

- Chỉ một active consumer, các instance còn lại standby.
- Lease có thời hạn.
- Fencing epoch tăng khi đổi owner.
- Conditional update chỉ cho owner/epoch hiện tại cập nhật.
- Idempotent sink dù có duplicate sau failover.

Nếu chia workload thành nhiều partitions/consumers, mỗi partition cần quy tắc checkpoint và ordering riêng.

## 25. Java Sync Driver: watcher có filter và projection

Ví dụ Java Sync Driver trên collection cdc_lab.orders. Code minh họa watcher chạy dài hạn, cần thêm graceful shutdown và error policy cho production.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class OrderChangeStreamReader {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Cần MONGODB_URI của replica set/sharded cluster"
            );
        }

        List<Document> pipeline = Arrays.asList(
                new Document("$match",
                        new Document("operationType",
                                new Document("$in",
                                        Arrays.asList(
                                                "insert",
                                                "update",
                                                "replace",
                                                "delete"
                                        )
                                )
                        )
                ),
                new Document("$project",
                        new Document("_id", 1)
                                .append("operationType", 1)
                                .append("clusterTime", 1)
                                .append("ns", 1)
                                .append("documentKey", 1)
                                .append("updateDescription", 1)
                                .append("fullDocument.status", 1)
                )
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("cdc_lab")
                    .getCollection("orders");

            try (MongoChangeStreamCursor<
                    ChangeStreamDocument<Document>> cursor =
                    orders.watch(pipeline)
                            .fullDocument(FullDocument.UPDATE_LOOKUP)
                            .maxAwaitTime(1, TimeUnit.SECONDS)
                            .cursor()) {

                while (true) {
                    ChangeStreamDocument<Document> event =
                            cursor.tryNext();

                    if (event == null) {
                        continue;
                    }

                    System.out.println(
                            "Type: " + event.getOperationType()
                    );
                    System.out.println(
                            "Key: " + event.getDocumentKey()
                    );
                    System.out.println(
                            "Token: " + event.getResumeToken()
                    );
                }
            }
        }
    }
}
~~~

### 25.1. Các API event cần phân biệt

~~~java
event.getResumeToken();     // Vị trí sự kiện
event.getDocumentKey();     // ID/khóa document
event.getOperationType();   // Loại operation
event.getFullDocument();    // Có thể null
event.getUpdateDescription();
~~~

Không dùng getDocumentKey() thay cho getResumeToken().

### 25.2. Projection và _id

Trong pipeline Java, project **_id: 1** là chủ đích. Nếu developer thêm projection loại _id, pipeline có thể làm mất token và bị MongoDB từ chối.

### 25.3. fullDocument có thể null

Delete hoặc updateLookup không tìm thấy document có thể khiến getFullDocument() null. Consumer phải xử lý được, không mặc định mọi event đều có payload.

## 26. Java: resume từ checkpoint

Ví dụ một hàm nhận MongoCollection và BsonDocument token đã lưu:

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;

import java.util.Collections;

public class ResumeConsumer {

    public static void consume(
            MongoCollection<Document> orders,
            BsonDocument savedToken
    ) {

        ChangeStreamIterable<Document> watch =
                orders.watch(Collections.emptyList())
                        .fullDocument(FullDocument.UPDATE_LOOKUP);

        if (savedToken != null) {
            watch = watch.resumeAfter(savedToken);
        }

        try (MongoChangeStreamCursor<
                ChangeStreamDocument<Document>> cursor =
                watch.cursor()) {

            while (true) {
                ChangeStreamDocument<Document> event =
                        cursor.tryNext();

                if (event == null) {
                    continue;
                }

                handleBusinessEvent(event);

                // Chỉ checkpoint sau khi business event
                // đã được xử lý/commit thành công.
                saveCheckpoint(event.getResumeToken());
            }
        }
    }

    private static void handleBusinessEvent(
            ChangeStreamDocument<Document> event
    ) {
        // Thay bằng xử lý thật, có idempotency.
    }

    private static void saveCheckpoint(BsonDocument token) {
        // Lưu token bền vững và bảo toàn BSON type.
    }
}
~~~

Các phương thức handleBusinessEvent và saveCheckpoint là điểm mở rộng minh họa. Để có consumer production, cần điều kiện dừng, retry phân loại lỗi, xử lý checkpoint ownership, shutdown và cơ chế tránh duplicate.

### 26.1. Không gọi resumeAfter(null)

Nếu chưa có checkpoint, chọn một chiến lược start rõ ràng (watch từ thời điểm bắt đầu, operation timestamp hợp lệ hoặc snapshot+CDC). Không truyền token rỗng theo giả định server sẽ tự chọn đúng.

### 26.2. Không tự xóa token khi gặp history lost

Nếu resume không thể tiếp tục, consumer cần reconcile/backfill chứ không tự thay token bằng null để bỏ qua lịch sử.

## 27. Java: encode/decode nguyên token

~~~java
import org.bson.BsonDocument;

public class ResumeTokenCodec {

    public static String encode(BsonDocument token) {
        return token == null ? null : token.toJson();
    }

    public static BsonDocument decode(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return BsonDocument.parse(value);
    }
}
~~~

Dạng Extended JSON cần dùng serializer/parser BSON phù hợp. Không chỉ lưu field _data rồi tự dựng một token mới.

### 27.1. Vì sao không thể so token string?

Token là opaque. So sánh vị trí mới/cũ theo thứ tự đọc và checkpoint ownership; không dùng toán tử so sánh chuỗi JSON để quyết định token mới hơn.

## 28. Java: checkpoint vào MongoDB

Ví dụ lưu tokenExtendedJson trong một collection checkpoint:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import org.bson.BsonDocument;
import org.bson.Document;

public class MongoCheckpointStore {

    private final MongoCollection<Document> checkpoints;

    public MongoCheckpointStore(
            MongoCollection<Document> checkpoints
    ) {
        this.checkpoints = checkpoints;
    }

    public BsonDocument load(String consumerId) {
        Document row = checkpoints.find(
                Filters.eq("_id", consumerId)
        ).first();

        if (row == null) {
            return null;
        }

        String json = row.getString("tokenExtendedJson");

        return json == null ? null : BsonDocument.parse(json);
    }

    public void save(
            String consumerId,
            BsonDocument token,
            int pipelineVersion
    ) {
        checkpoints.updateOne(
                Filters.eq("_id", consumerId),
                Updates.combine(
                        Updates.set(
                                "tokenExtendedJson",
                                token.toJson()
                        ),
                        Updates.set(
                                "pipelineVersion",
                                pipelineVersion
                        ),
                        Updates.currentDate("updatedAt")
                ),
                new UpdateOptions().upsert(true)
        );
    }
}
~~~

### 28.1. Ví dụ này chưa xử lý những gì?

- Hai instance cùng ghi một checkpoint.
- Checkpoint bị lùi vì concurrent writes.
- Checkpoint và side effect ở hai collection không cùng transaction.
- Write concern checkpoint chưa đủ bền vững theo nghiệp vụ.
- Business effect bị lặp khi crash trước checkpoint.
- Pipeline version thay đổi và migration offset.
- Server trả timeout khiến trạng thái save không rõ.

Nó là điểm xuất phát để hiểu persistence của token, không phải một thư viện exactly-once hoàn chỉnh.

## 29. Java: PBRT và cursor.getResumeToken()

MongoDB Java Sync Driver có phương thức lấy resume token hiện tại của change stream cursor:

~~~java
BsonDocument token = cursor.getResumeToken();
~~~

Token có thể phản ánh event token hoặc post-batch token mà driver biết theo ngữ cảnh.

Nếu không có event trả về sau một lần tryNext(), một consumer tuần tự có thể cân nhắc lưu token để cập nhật tiến độ idle:

~~~java
ChangeStreamDocument<Document> event = cursor.tryNext();

if (event != null) {
    handleBusinessEvent(event);
    saveCheckpoint(event.getResumeToken());
} else {
    BsonDocument idleToken = cursor.getResumeToken();

    if (idleToken != null && noPendingEvents()) {
        saveCheckpoint(idleToken);
    }
}
~~~

**noPendingEvents()** là hàm kiểm tra hàng đợi của application do developer tự định nghĩa, không phải API MongoDB.

Nếu consumer xử lý song song, phải chắc chắn token không vượt qua event pending. Không lấy PBRT làm lý do bỏ qua business event chưa hoàn tất.

## 30. Retry policy và state machine

Một consumer có thể tổ chức logic:

~~~text
START
  |
LOAD CHECKPOINT + PIPELINE VERSION
  |
OPEN WATCH OR RESUME
  |
READ EVENT / IDLE TOKEN
  |
  +--- EVENT ---> PROCESS IDEMPOTENTLY
  |                    |
  |                 COMMIT EFFECT
  |                    |
  |                 SAVE TOKEN
  |
  +--- IDLE ----> IF NO PENDING EVENTS
                       |
                    SAVE SAFE CURSOR TOKEN
  |
NEXT READ

Transient resumable error:
  reopen with safe checkpoint and backoff

History lost / invalid pipeline / incompatible scope:
  stop, investigate and reconcile
~~~

### 30.1. Phân biệt lỗi tạm thời và không thể tự sửa

| Lỗi | Chiến lược |
| --- | --- |
| Network hiccup/election | Retry có giới hạn/backoff theo khả năng resumable |
| Authentication/authorization | Sửa credential/quyền, không retry vô hạn |
| Pipeline làm đổi _id | Sửa code và cấu hình |
| History lost | Resnapshot/backfill/reconcile |
| Invalidate | Xem lifecycle/startAfter theo scope |
| Sink API lỗi | Retry có idempotency, không checkpoint trước |
| Checkpoint store lỗi | Không tiến token nếu chưa lưu an toàn |

### 30.2. Monitoring quan trọng

Theo dõi:

- Consumer running/retrying/blocked.
- Last processed event/time.
- Last checkpoint/token update time.
- Consumer lag và oplog window.
- Resume attempts và labels/errors.
- Sink processing latency/failures.
- Duplicate/idempotency hits.
- Pipeline version và watch scope.
- Owner/lease/fencing epoch.

Watcher không có matched event nhiều giờ **không chắc đã chết**. Dùng cursor heartbeat/PBRT, getMore activity và oplog lag để phân biệt yên tĩnh với bị treo.

## 31. Change streams trên sharded cluster

Một sharded collection có thể được chia thành nhiều ranges trên các shards. Change stream ở cấp cluster/collection được MongoDB điều phối theo semantics phù hợp.

### 31.1. Không tự kết hợp oplog từng shard

Không tự mở một luồng oplog ở từng shard rồi ghép bằng clusterTime, vì có ordering/resume semantics phức tạp hơn.

Dùng API change stream tiêu chuẩn qua mongos/driver theo topology được hỗ trợ.

### 31.2. Token trong sharded cluster vẫn opaque

Đừng giả định _data là một timestamp đơn giản hoặc có cùng cách biểu diễn giữa topology/version.

### 31.3. Migration không yêu cầu consumer tự đổi shard owner

Chunk migration và metadata routing thuộc hạ tầng sharding. Consumer không nên giữ mapping tenant/shard cố định làm cơ sở lấy sự kiện.

### 31.4. Quan sát tài nguyên

Khi change stream hợp nhất từ nhiều shards, cần xem write volume, network, lag, trạng thái từng shard và hiệu năng mongos theo deployment.

## 32. Thay đổi pipeline version và backfill

Giả sử:

~~~text
V1 filter:
  chỉ nhận operationType update

V2 filter:
  nhận update và delete
~~~

Nếu consumer V2 resume từ token của V1, nó không tự nhận được những delete **đã xảy ra trước checkpoint** của V1.

### 32.1. Chính sách thay đổi

1. Gắn phiên bản pipeline với checkpoint.
2. Đánh giá dữ liệu nào từng bị lọc nhưng version mới cần.
3. Làm snapshot/backfill/rebuild nếu downstream bị thiếu state.
4. Chuyển consumer có kiểm soát, tránh gap hoặc duplicate vượt quy tắc.
5. Đo reconciliation sau deploy.

### 32.2. Không phải đổi projection nào cũng cần reset stream

Nếu chỉ thêm một field không cần backfill, có thể áp dụng từ thời điểm mới. Quyết định phụ thuộc contract của downstream.

### 32.3. Hai phiên bản đồng thời

Nếu chạy V1 và V2 song song, dùng checkpoint IDs/ownership riêng trừ khi có cơ chế coordination được thiết kế cụ thể.

## 33. Bảo mật và giảm PII

Một users change stream có thể vô tình gửi fullDocument chứa email, phone, address hoặc thông tin nhạy cảm.

Ví dụ projection nhỏ:

~~~javascript
db.users.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    },
    {
      $project: {
        _id: 1,
        operationType: 1,
        documentKey: 1,
        "fullDocument.displayName": 1,
        "fullDocument.status": 1
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

### 33.1. Lọc payload không thay RBAC

Một service có quyền truy cập quá rộng vẫn là rủi ro dù pipeline giảm field output. Cần RBAC, TLS, secret handling và log controls độc lập.

### 33.2. Log an toàn

Không ghi toàn bộ fullDocument, pre-image hoặc token cộng PII vào log debug không có retention và access controls.

### 33.3. Schema evolution

Consumer phải xử lý field thiếu/null, operationType mới và sự thay đổi document shape. Không phụ thuộc cứng vào một cấu trúc updateDescription từ một phiên bản ứng dụng cũ.

## 34. Bảng lỗi thường gặp

| Sai lầm | Hệ quả |
| --- | --- |
| Dùng documentKey._id làm resume token | Không phải vị trí event |
| Project _id = 0 | Mất token, pipeline có thể lỗi |
| ReplaceRoot bằng fullDocument | Thay/mất event._id |
| Set _id bằng business ID | Thay resume token |
| Lưu mỗi _data string | Phụ thuộc cấu trúc nội bộ |
| Checkpoint trước business effect | Bỏ event chưa xử lý |
| Checkpoint cursor token khi worker còn pending | Tiến qua event chưa hoàn tất |
| Không dùng PBRT trong stream filter mạnh | Checkpoint đứng yên quá lâu |
| Retry history lost mãi | Không khôi phục lịch sử bị mất |
| Dùng resumeAfter sau invalidate | Không đúng semantics |
| Dùng clusterTime thay token | Thiếu vị trí event |
| Filter chỉ update và quên replace/delete | Downstream state sai |
| FullDocument status được coi là transition | updateLookup có thể thấy trạng thái khác |
| Hai pods cùng ghi checkpoint thiếu lease | Checkpoint lùi hoặc tiến sai |
| Thay pipeline nhưng không backfill | Event cũ bị lọc không trở lại |
| Coi watch() là snapshot dữ liệu | Không phát lại tự động lịch sử trước khi mở |
| Coi silent watcher là chết | Filter mạnh có thể không emit |
| Coi token còn giá trị mãi | Oplog có retention |
| Cho rằng resumeAfter là exactly-once | Side effect vẫn có thể bị lặp |
| Đọc oplog từng shard rồi ghép theo timestamp | Không bảo toàn stream semantics |

## 35. Bài thực hành: sự kiện và pipeline

### Bài 1 – Token và document ID

Mở watch trên orders. Update một order ba lần. Ghi event._id, documentKey._id, clusterTime và operationType. Vì sao document ID giống nhau nhưng resume token khác?

### Bài 2 – $match operationType

Viết pipeline chỉ nhận insert, update và replace. Sau đó giải thích tại sao consumer đồng bộ search index cần cân nhắc thêm delete.

### Bài 3 – Lọc chuyển PAID

So sánh:

~~~javascript
{
  $match: {
    "updateDescription.updatedFields.status": "PAID"
  }
}
~~~

và:

~~~javascript
{
  $match: {
    "fullDocument.status": "PAID"
  }
}
~~~

Nêu khác biệt giữa “event thay đổi status” và “document hiện hành có status PAID”.

### Bài 4 – Projection

Project chỉ giữ _id, operationType, documentKey, clusterTime và fullDocument.status. Vì sao _id không được đổi thành documentKey._id?

### Bài 5 – Replace root

Sửa:

~~~javascript
{
  $replaceRoot: {
    newRoot: "$fullDocument"
  }
}
~~~

thành một root chuẩn hóa vẫn giữ nguyên event._id và có businessId riêng.

### Bài 6 – Delete event

Consumer xóa cache khi nhận delete nhưng đã project bỏ documentKey. Nó thiếu thông tin gì? Hãy sửa pipeline.

## 36. Bài thực hành: resume và checkpoint

### Bài 7 – Crash trước checkpoint

~~~text
E1 xử lý xong -> lưu E1 token
E2 xử lý xong -> crash trước lưu E2 token
~~~

Sau resumeAfter(E1), chuyện gì có thể xảy ra? Dùng idempotency ra sao?

### Bài 8 – Crash sau checkpoint

~~~text
Nhận E3 -> lưu E3 token -> crash trước xử lý E3
~~~

Vì sao E3 có thể bị bỏ qua? Hãy sửa trình tự.

### Bài 9 – Parallel watermark

~~~text
E100 done
E101 pending
E102 done
E103 done
~~~

Có thể checkpoint token nào? Khi E101 hoàn thành thì nâng được tới đâu?

### Bài 10 – Idle PBRT

Consumer chỉ nhận một event match mỗi vài giờ, nhưng source có hàng nghìn events/giây. Vì sao chỉ checkpoint event._id nhìn thấy gây rủi ro? Khi nào được checkpoint cursor token?

### Bài 11 – Oplog history lost

Consumer offline bốn ngày, oplog history còn một ngày. Thiết kế quy trình phục hồi không tạo gap dữ liệu im lặng.

### Bài 12 – Invalidate

Collection bị drop trong lúc có watcher. So sánh resumeAfter/startAfter, điều kiện namespace lifecycle và khả năng cần resnapshot.

## 37. Bài thực hành: Java và vận hành

### Bài 13 – Java watch

Dùng MongoDB Java Sync Driver tạo watcher với $match, $project giữ _id:1 và FullDocument.UPDATE_LOOKUP. Trả lời getResumeToken khác getDocumentKey thế nào.

### Bài 14 – Token codec

Viết encode/decode BsonDocument bằng toJson()/parse(), lưu tokenExtendedJson trong checkpoint. Vì sao không chỉ lưu _data?

### Bài 15 – Checkpoint ownership

Hai pods cùng load E100, xử lý rồi lưu checkpoint với cùng ID. Phân tích race và đề xuất lease/fencing.

### Bài 16 – Payment side effect

Consumer gọi payment API, API thành công rồi process crash trước lưu token. Làm sao tránh thanh toán trùng khi event được replay?

### Bài 17 – Pipeline evolution

V1 chỉ nhận update, V2 nhận thêm delete. Vì sao giữ checkpoint V1 không đủ để rebuild downstream state? Đề xuất backfill strategy.

### Bài 18 – Giảm PII

Viết projection cho users chỉ giữ displayName/status cùng event._id và documentKey. Nêu yêu cầu RBAC/logging còn cần.

### Bài 19 – Capacity

Peak write rate tăng mạnh, consumer có thể offline 8 giờ. Cần theo dõi oplog window, consumer lag và checkpoint progress thế nào?

### Bài 20 – Sharded stream

Collection phân bố trên nhiều shards và chunks migration. Vì sao consumer không nên tự route theo mapping shard hoặc ghép token bằng cách so chuỗi _data?

## 38. Checklist trước production

1. Source là replica set hoặc sharded cluster hỗ trợ change streams.
2. Watch scope được định nghĩa rõ.
3. Pipeline chỉ gồm stage hợp lệ.
4. event._id được giữ nguyên value/type.
5. documentKey được giữ nếu sink cần ID của record.
6. Operation types phù hợp insert/update/replace/delete/lifecycle.
7. updateLookup/pre-post images được dùng có chủ đích.
8. Filter không vô tình bỏ event downstream cần.
9. Projection giảm payload/PII.
10. Checkpoint chỉ sau xử lý thành công.
11. Cursor/PBRT checkpoint không vượt pending events.
12. Token lưu nguyên BSON/Extended JSON.
13. Có idempotency hoặc transaction phù hợp.
14. Parallel processing có committed watermark/ordering.
15. Multi-instance có lease/fencing/ownership.
16. ResumeAfter/startAfter dùng đúng tình huống.
17. Có chính sách history lost/backfill.
18. Pipeline version gắn với checkpoint.
19. Theo dõi oplog window và lag.
20. Có retry backoff và phân loại lỗi.
21. Có graceful shutdown và cursor cleanup.
22. Có reconciliation sau sự cố.
23. RBAC, TLS và log policy đúng.
24. Có test restart, crash, duplicate và không có event match.
25. Kết quả vận hành dựa trên metrics chứ không chỉ watcher còn chạy.

## 39. Kết luận

Lọc và biến đổi MongoDB Change Streams bằng **$match**, **$project**, **$addFields** và các stage được hỗ trợ giúp giảm sự kiện không cần thiết, chuẩn hóa payload và hạn chế dữ liệu nhạy cảm được gửi xuống consumer.

Nhưng quy tắc quan trọng nhất luôn là:

> **Field _id ở root của change event là resume token. Không thay đổi hoặc xóa nó khi lọc và biến đổi event.**

Để định danh record nghiệp vụ, dùng **documentKey._id** trong field riêng như businessId. Để thay root, giữ tường minh **_id: "$_id"**. Để resume, lưu toàn bộ BSON token và dùng resumeAfter/startAfter theo đúng ngữ nghĩa.

Consumer bền vững cần thêm:

- Checkpoint sau khi side effects đã commit.
- PBRT khi idle/filter mạnh, nhưng không vượt event pending.
- Idempotency để chịu event replay.
- Theo dõi oplog/history và khôi phục có backfill khi token hết hạn.
- Quản lý pipeline version và quyền ghi checkpoint khi có nhiều instance.

**Giữ token đúng chỉ giúp tiếp tục đọc đúng vị trí; bảo đảm không mất hoặc không nhân đôi hiệu ứng nghiệp vụ là trách nhiệm của thiết kế consumer end-to-end.**

## Tài liệu tham khảo

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [MongoDB Manual — $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/)
- [MongoDB Manual — $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [MongoDB Manual — $replaceRoot](https://www.mongodb.com/docs/manual/reference/operator/aggregation/replaceRoot/)
- [MongoDB Manual — $getField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getField/)
- [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
