# Cấu trúc sự kiện và phân biệt insert, update, replace, delete trong MongoDB Change Streams

## 1. Vì sao ứng dụng cần biết document đã thay đổi thế nào?

Giả sử ứng dụng quản lý sản phẩm lưu dữ liệu trong MongoDB. Khi một sản phẩm được tạo, cập nhật giá, thay toàn bộ thông tin hoặc xóa, nhiều hệ thống khác cần biết để làm việc tiếp:

- Đồng bộ sản phẩm sang công cụ tìm kiếm.
- Cập nhật cache và read model.
- Gửi sự kiện đến một worker xử lý dữ liệu.
- Ghi dấu vết thay đổi để hỗ trợ đối soát.
- Cập nhật bảng thống kê mà không phải quét lại toàn bộ collection.

Một cách là để API chủ động gửi sự kiện sau mỗi lệnh ghi. Nhưng nếu ứng dụng có nhiều service, batch jobs hoặc tác vụ quản trị cùng ghi, một số thay đổi có thể không đi qua đúng API. **Change Streams** cho phép một consumer đăng ký nhận thông báo về thay đổi dữ liệu MongoDB theo một giao diện hỗ trợ chính thức.

Ví dụ ý tưởng:

~~~text
            MongoDB collection: products
                       |
                  Các thao tác ghi
                insert/update/replace/delete
                       |
                       v
                   Change Stream
                       |
              +--------+---------+
              |                  |
              v                  v
         Search Index        Cache / Read Model
~~~

Điều quan trọng nhất là **không phải mọi sự kiện đều chứa cùng một bộ field**:

- **insert:** document mới thường xuất hiện trong **fullDocument**.
- **update:** các thay đổi kiểu field-level được mô tả trong **updateDescription**; không mặc định có nguyên document mới.
- **replace:** document được thay thế được trình bày như một document mới trong **fullDocument**, không phải danh sách từng field bị sửa.
- **delete:** document bị xóa không mặc định xuất hiện ở **fullDocument**; chủ yếu có **documentKey** để nhận diện document.

Nếu consumer dùng một đoạn code giả định mọi event đều có **fullDocument.status**, nó rất dễ làm sai hoặc làm rơi sự kiện **delete**.

### Mục tiêu bài học

Sau khi hoàn thành, bạn sẽ:

1. Đọc được cấu trúc chung của một **change event**.
2. Phân biệt **_id resume token** với **documentKey._id**.
3. Hiểu **operationType** và các trường đặc trưng cho bốn loại thay đổi.
4. Biết khi nào có **fullDocument**, **updateDescription** và **fullDocumentBeforeChange**.
5. Xử lý **$set, $unset, $inc**, thay cả document, xóa và thao tác **upsert**.
6. Viết consumer có **resume token**, checkpoint và idempotency.
7. Chạy một lab hai phiên **mongosh** để phát ra và nhận bốn kiểu event.
8. Phân tích các giới hạn về oplog retention, failover, pre/post-images và kích thước sự kiện.

> Bài tập dùng database riêng **mongo_change_stream_lab** và collection **lab_items**. Mọi đoạn lệnh gây thay đổi dữ liệu đều giới hạn vào những ID mẫu của bài. Không dùng trên production hoặc collection của người khác.

## 2. Điều kiện để Change Streams hoạt động

### 2.1. Replica set hoặc sharded cluster

Change Streams dựa vào hạ tầng replication và lịch sử thay đổi MongoDB, thường được sử dụng với:

- **Replica set**.
- **Sharded cluster** thông qua **mongos**.

Một **standalone mongod** thông thường không hỗ trợ Change Streams theo cách một replica set hỗ trợ. Nếu kết nối lab của bạn là standalone, cần chuyển sang một môi trường replica set được thiết lập hợp lệ; không thể chỉ thêm tùy chọn watch rồi mong nó hoạt động.

### 2.2. Dữ liệu được ghi bền vững trước khi phát sự kiện

Change Streams cung cấp các thay đổi đã được **majority-committed** theo cơ chế của MongoDB. Một write mới được áp dụng ở primary nhưng chưa majority-committed không mặc nhiên xuất hiện ngay trong stream.

Điều này có hai hệ quả:

- Consumer không nên coi Change Stream là callback chạy tức thời **trước khi commit**.
- Thời điểm ứng dụng thực hiện write có thể sớm hơn thời điểm event đến consumer vì replication, streaming, scheduling và network.

**Không đồng nhất:** “Một lệnh ghi trả ACK w:1” và “Change Stream đã phát event đó”. Event phản ánh thay đổi đã qua các điều kiện Change Stream áp dụng.

### 2.3. Quyền truy cập

Tài khoản consumer phải có các quyền thích hợp để **watch/read** collection hoặc database theo phạm vi và phiên bản tương ứng. Những thao tác như bật pre/post-images, thay đổi cấu hình collection hoặc đọc metadata quản trị đòi hỏi quyền khác.

Không cấp quyền quản trị toàn cluster cho worker chỉ để nó đọc event từ một collection.

### 2.4. Phạm vi watch

MongoDB hỗ trợ theo dõi ở những phạm vi khác nhau:

~~~javascript
// Chỉ một collection:
const streamA = db.getCollection("products").watch();

// Các collection trong database hiện tại:
const streamB = db.watch();

// Phạm vi toàn deployment, khi có quyền và API hỗ trợ:
// MongoClient.watch() trong driver, hoặc API tương ứng của môi trường.
~~~

Đừng sử dụng **db.watch()** rồi giả định chỉ nhận sự kiện của collection products. Phạm vi watch ảnh hưởng cả số event, quyền đọc và chi phí consumer.

## 3. Cấu trúc chung của một change event

Một change event là **một BSON document** có các trường mô tả thay đổi. Không phải mọi trường đều xuất hiện ở tất cả loại sự kiện.

Ví dụ hình dạng minh họa:

~~~javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "update",
  clusterTime: Timestamp({ t: 1780000000, i: 3 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-01"
  },
  updateDescription: {
    updatedFields: {
      status: "active",
      quantity: 7,
      "attributes.color": "navy"
    },
    removedFields: ["obsoleteFlag"]
  }
}
~~~

**Lưu ý:** timestamp và token trong đoạn trên chỉ dùng để giải thích hình dạng. Resume token là dữ liệu opaque do server tạo; **không tự dựng token từ chuỗi giả định** và không dùng giá trị placeholder để resume một stream thật.

### 3.1. Bảng các trường quan trọng

| Field | Ý nghĩa | Có ở đâu? |
| --- | --- | --- |
| **_id** | **Resume token** định danh vị trí sự kiện trong stream | Trường quan trọng cho resumption; không phải _id của document |
| **operationType** | Loại thay đổi, ví dụ insert/update/replace/delete | Các change events chính |
| **clusterTime** | Thời điểm logic BSON Timestamp liên quan đến event | Phần lớn sự kiện thay đổi dữ liệu |
| **ns** | Namespace với db và coll | Các event gắn với namespace tương ứng |
| **documentKey** | Khóa nhận diện document bị ảnh hưởng; thường có _id | insert/update/replace/delete |
| **fullDocument** | Document đầy đủ theo semantics của loại event và option | Thường có với insert/replace; tùy option với update |
| **updateDescription** | Mô tả thay đổi field và array đối với update | update |
| **fullDocumentBeforeChange** | Bản document trước thay đổi, nếu pre-image được bật và yêu cầu | Một số update/replace/delete khi khả dụng |
| **wallTime** | Thời điểm dạng BSON Date do server cung cấp ở các phiên bản hỗ trợ | Tùy version và loại event |
| **lsid, txnNumber** | Ngữ cảnh logical session/transaction trong trường hợp tương ứng | Có thể xuất hiện với thao tác thuộc transaction |
| **collectionUUID** | Định danh collection trong các trường hợp/option hỗ trợ | Không mặc định dùng làm khóa nghiệp vụ |

Những field khác có thể xuất hiện ở phiên bản MongoDB hoặc event loại khác. **Consumer nên xử lý schema theo operationType và option watch**, không giả định mọi event giống hệt một mẫu JSON cố định.

### 3.2. _id ở cấp event là resume token

Quan sát:

~~~javascript
{
  _id: { _data: "<resume-token>" },
  documentKey: { _id: "cs272-item-01" }
}
~~~

Hai trường mang tên _id nhưng **khác vai trò**:

- **event._id:** token dùng để resume một Change Stream sau vị trí đã nhận.
- **event.documentKey._id:** _id của document nghiệp vụ, ví dụ sản phẩm cs272-item-01.

Một document có thể được update 100 lần, tạo 100 event với những resume token khác nhau, trong khi **documentKey._id vẫn là một ID**.

**Đừng dùng documentKey._id làm checkpoint stream.** Nếu làm vậy, bạn không thể biết đã xử lý đến lần update thứ mấy của document.

### 3.3. ns xác định nơi xảy ra thay đổi

~~~javascript
ns: {
  db: "mongo_change_stream_lab",
  coll: "lab_items"
}
~~~

Nếu watch phạm vi toàn database hoặc toàn deployment, hai event có thể có cùng documentKey._id nhưng đến từ **hai collection khác nhau**. Do đó, một consumer chung cần tính đến **namespace + documentKey** khi định danh đối tượng nguồn.

Đối với một consumer chỉ watch đúng một collection, namespace vẫn hữu ích để log và phát hiện đổi cấu hình.

### 3.4. clusterTime không phải ID duy nhất của event

**clusterTime** là BSON Timestamp mang ý nghĩa logic trong cơ chế MongoDB. Nhiều thao tác thuộc cùng transaction có thể chia sẻ cùng một clusterTime; trong sharded cluster, các sự kiện cũng có sắc thái về ordering và metadata.

Do đó:

- Không dùng **clusterTime đơn lẻ** làm khóa dedup cho mọi change events.
- Không lấy một timestamp và tự tạo resume token từ đó.
- Không mặc định nó tương đương thời gian đồng hồ để tính SLA độ trễ.
- Nếu cần resume chính xác, lưu **event._id** đầy đủ ở dạng BSON phù hợp.

**wallTime**, nếu được trả về, gần với thời gian thực nhưng không thay thế resume token và không phải khóa event duy nhất.

### 3.5. documentKey và sharding

Với collection unsharded, documentKey thường có:

~~~javascript
documentKey: { _id: "cs272-item-01" }
~~~

Với sharded collection, documentKey có thể có **_id và các trường shard key cần thiết** theo quy tắc MongoDB của version tương ứng.

Ví dụ hình dạng:

~~~javascript
documentKey: {
  _id: "order-001",
  tenantId: "t001",
  orderNo: "SO-001"
}
~~~

Đây là minh họa; không giả định mọi sharded deployment luôn có đúng ba trường như trên. Consumer phải đọc documentKey thực tế, không hardcode một schema khác với collection của mình.

## 4. Bốn operationType chính: bảng đối chiếu

| Loại | Thao tác điển hình | fullDocument | updateDescription | documentKey |
| --- | --- | --- | --- | --- |
| **insert** | insertOne, insertMany, upsert tạo mới | Thường là document mới | Không | Có |
| **update** | updateOne với $set/$inc/$unset, v.v. | **Không mặc định**; có thể yêu cầu qua option | **Có** | Có |
| **replace** | replaceOne thay document | Thường là document sau thay thế | Không dùng dạng diff updateDescription | Có |
| **delete** | deleteOne/deleteMany | **Không có document đã xóa ở fullDocument mặc định** | Không | Có |

**Lưu ý:** chỉ nhìn lệnh API chưa chắc đủ để phân loại trong mọi tình huống. Ví dụ, **upsert** có thể phát **insert** nếu server tạo document mới, hoặc **update/replace** nếu nó tác động lên document đã tồn tại. Hãy xử lý event theo **operationType thực tế**.

### 4.1. Sơ đồ ra quyết định trong consumer

~~~text
                Change Event
                     |
             event.operationType
                     |
   +----------+------+------+----------+
   |          |             |          |
 insert     update        replace     delete
   |          |             |          |
 fullDocument updateDescription fullDocument documentKey
   |          |             |          |
 tạo index  patch/fetch    rebuild     xóa index/
 hoặc cache theo nhu cầu   snapshot    cache key
~~~

Đây là **logic gợi ý**. Một search index có thể chọn luôn **rebuild từ fullDocument** khi updateLookup khả dụng, thay vì tự áp patch; điều đó tùy tính nhất quán và khả năng chịu dữ liệu stale.

## 5. Insert: document mới xuất hiện

### 5.1. Thao tác nguồn

~~~javascript
db.lab_items.insertOne({
  _id: "cs272-item-04",
  dataset: "change-stream-v1",
  sku: "P-004",
  status: "draft",
  quantity: 3,
  attributes: { color: "white" }
});
~~~

### 5.2. Event minh họa

~~~javascript
{
  _id: { _data: "<token-insert>" },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1780000001, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-04"
  },
  fullDocument: {
    _id: "cs272-item-04",
    dataset: "change-stream-v1",
    sku: "P-004",
    status: "draft",
    quantity: 3,
    attributes: { color: "white" }
  }
}
~~~

Document trong **fullDocument** biểu diễn bản ghi được insert. Event insert không cần **updateDescription**, vì không có phép sửa các field của một document cũ để liệt kê.

### 5.3. Cách xử lý

Một consumer đồng bộ search index có thể:

1. Đọc **documentKey._id** để xác định ID nguồn.
2. Đọc **fullDocument** làm dữ liệu tạo một bản ghi index.
3. Dùng **upsert** hoặc cơ chế idempotent ở hệ thống đích để tránh lỗi khi event được phát lại sau reconnect.
4. Chỉ checkpoint resume token khi đã xử lý thành công theo chính sách.

**Không** chỉ lấy event._id làm ID sản phẩm, vì nó là resume token, không phải business ID.

### 5.4. insertMany có thể tạo nhiều insert events

Nếu ứng dụng chạy:

~~~javascript
db.lab_items.insertMany([
  { _id: "a", status: "draft" },
  { _id: "b", status: "draft" }
]);
~~~

Change Stream có thể phát **hai sự kiện insert** tương ứng hai document, không phải một sự kiện duy nhất chứa Array document chỉ vì API dùng insertMany. Với batching hoặc transaction, token/order/clusterTime có những sắc thái cần xem theo version và cách thao tác được commit.

## 6. Update: thay đổi từng field, không nhất thiết có cả document

### 6.1. Thao tác nguồn

~~~javascript
db.lab_items.updateOne(
  { _id: "cs272-item-01" },
  {
    $set: {
      status: "active",
      "attributes.color": "navy"
    },
    $inc: { quantity: 2 },
    $unset: { obsoleteFlag: "" }
  }
);
~~~

### 6.2. Event minh họa

~~~javascript
{
  _id: { _data: "<token-update>" },
  operationType: "update",
  clusterTime: Timestamp({ t: 1780000002, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-01"
  },
  updateDescription: {
    updatedFields: {
      status: "active",
      quantity: 7,
      "attributes.color": "navy"
    },
    removedFields: ["obsoleteFlag"]
  }
}
~~~

**updatedFields** chứa **giá trị mới** của những path đã được cập nhật. Chẳng hạn với **$inc: {quantity:2}**, updateDescription có thể thể hiện **quantity:7**, không phải “cộng thêm 2”.

**removedFields** chứa tên các field bị gỡ bỏ, ví dụ field bị $unset. Nó không chứa giá trị cũ của những field ấy.

### 6.3. Không xem updateDescription là nguyên document

Document thực tế sau update có thể là:

~~~javascript
{
  _id: "cs272-item-01",
  dataset: "change-stream-v1",
  sku: "P-001",
  status: "active",
  quantity: 7,
  attributes: {
    color: "navy",
    size: "M"
  },
  labels: ["new", "web"]
}
~~~

Trong khi updateDescription chỉ nói về những phần đổi. Nếu consumer viết:

~~~javascript
searchIndex.replace("cs272-item-01", event.updateDescription.updatedFields);
~~~

thì nó có nguy cơ **làm mất các field không xuất hiện trong delta**, ví dụ sku, labels hoặc attributes.size.

Để đồng bộ toàn document, consumer phải:

- Áp dụng **patch** đúng semantics lên bản sao đang giữ, gồm dotted paths, removedFields và các thay đổi Array; hoặc
- Dùng **fullDocument** với tùy chọn thích hợp, đồng thời hiểu giới hạn tính nhất quán của bản lookup.

### 6.4. $set, $inc, $unset thể hiện thế nào?

| Lệnh MongoDB | Điều consumer thường nhìn thấy trong updateDescription |
| --- | --- |
| **$set: {status:"active"}** | updatedFields.status = "active" |
| **$inc: {quantity:2}** | updatedFields.quantity = giá trị cuối sau khi tăng |
| **$unset: {obsoleteFlag:""}** | removedFields chứa "obsoleteFlag" |
| Cập nhật nested field | Path có thể ở dạng dấu chấm, ví dụ "attributes.color" |
| Thay đổi cấu trúc Array | Các đường dẫn chỉ số, giá trị Array hoặc truncatedArrays tùy kiểu thao tác/version |

Không nên gắn chặt consumer vào việc một toán tử update MongoDB bắt buộc sinh đúng một entry trong updatedFields. MongoDB mô tả **thay đổi quan sát được** trong event, không hứa ánh xạ một-một từ từng toán tử nguồn sang từng field output ở mọi phiên bản.

### 6.5. removedFields không phải danh sách document đã xóa

Khi **$unset: {obsoleteFlag:""}**, operationType vẫn là **"update"**. Field obsoleteFlag bị xóa khỏi document, nhưng document cs272-item-01 **vẫn tồn tại**.

Khi **deleteOne** xóa cả document, operationType mới là **"delete"**.

Nhầm hai trường hợp này có thể khiến consumer xóa toàn bộ bản ghi search index chỉ vì một field bị $unset.

### 6.6. Trường nested và dấu chấm

Một event có thể có:

~~~javascript
updateDescription: {
  updatedFields: {
    "attributes.color": "navy"
  }
}
~~~

Path này biểu diễn thay đổi trong object lồng nhau theo semantics của MongoDB. **Không** được tự gán:

~~~javascript
copy["attributes.color"] = "navy";
~~~

rồi tin rằng copy.attributes.color đã đổi. Với JavaScript object thông thường, code trên tạo field literal tên **"attributes.color"** ở cấp ngoài.

Một patch processor phải hiểu path lồng nhau, field names đặc biệt và Array. Nếu dữ liệu cho phép field name có dấu chấm hoặc ký tự đặc biệt, việc diễn giải path còn phức tạp hơn; các event/version mới có thể cung cấp metadata bổ sung như **disambiguatedPaths** khi được yêu cầu/hỗ trợ.

### 6.7. Array và truncatedArrays

Khi update làm ngắn một Array, event ở những phiên bản hỗ trợ có thể có:

~~~javascript
updateDescription: {
  updatedFields: {},
  removedFields: [],
  truncatedArrays: [
    { field: "labels", newSize: 2 }
  ]
}
~~~

Đây là **mẫu minh họa** cho thông tin truncation, không phải khẳng định mọi thao tác $pop hay $pull đều tạo đúng hình dạng đó. Cấu trúc thông báo Array chịu ảnh hưởng bởi cách update được thực thi và phiên bản MongoDB.

Consumer muốn tự áp delta cho Array cần đọc tài liệu của version đang dùng và kiểm thử các thao tác như:

- Thêm phần tử vào Array.
- Sửa phần tử theo index.
- Xóa phần tử.
- Cắt ngắn độ dài Array.
- Thay toàn bộ Array.

**Không** chỉ áp updatedFields rồi bỏ qua truncatedArrays nếu mục tiêu là duy trì bản sao chính xác.

## 7. Replace: thay cả document, không phải patch field

### 7.1. Thao tác nguồn

~~~javascript
db.lab_items.replaceOne(
  { _id: "cs272-item-02" },
  {
    _id: "cs272-item-02",
    dataset: "change-stream-v1",
    sku: "P-002",
    status: "archived",
    quantity: 0,
    attributes: { color: "gray" }
  }
);
~~~

**replaceOne** thay document được chọn bằng **replacement document**. Những field cũ không được đưa vào replacement có thể biến mất khỏi document, trừ các ràng buộc đặc biệt như _id.

Ví dụ nếu trước replace document có:

~~~javascript
{
  _id: "cs272-item-02",
  sku: "P-002",
  status: "draft",
  quantity: 2,
  legacy: "temporary",
  attributes: { color: "red", size: "L" }
}
~~~

sau replace như trên, **legacy** và **attributes.size** không còn nữa.

### 7.2. Event minh họa

~~~javascript
{
  _id: { _data: "<token-replace>" },
  operationType: "replace",
  clusterTime: Timestamp({ t: 1780000003, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-02"
  },
  fullDocument: {
    _id: "cs272-item-02",
    dataset: "change-stream-v1",
    sku: "P-002",
    status: "archived",
    quantity: 0,
    attributes: { color: "gray" }
  }
}
~~~

Điểm phân biệt:

- **operationType = "replace"**, không phải "update".
- **fullDocument** mang document thay thế.
- Không có một **updateDescription** liệt kê từng field đã đổi theo semantics của event update.

### 7.3. Vì sao replace cần xử lý khác update?

Giả sử hệ thống đích giữ:

~~~javascript
{
  id: "cs272-item-02",
  status: "draft",
  quantity: 2,
  legacy: "temporary"
}
~~~

Nếu consumer nhận replace rồi chỉ merge các field trong fullDocument vào bản cũ, field **legacy** có thể còn sót ở hệ thống đích, dù document nguồn đã loại bỏ nó.

Vì vậy, với **replace event**, hướng xử lý phổ biến là **thay toàn bộ snapshot** ở hệ thống đích, không áp merge patch kiểu update.

### 7.4. Update khác replace dù giá trị cuối giống nhau

Hai thao tác có thể tạo ra document cuối giống nhau:

~~~javascript
// Chỉ cập nhật vài field.
db.lab_items.updateOne(
  { _id: "cs272-item-02" },
  { $set: { status: "archived", quantity: 0 } }
);

// Thay thế toàn document bằng bản mới.
db.lab_items.replaceOne(
  { _id: "cs272-item-02" },
  {
    _id: "cs272-item-02",
    dataset: "change-stream-v1",
    sku: "P-002",
    status: "archived",
    quantity: 0,
    attributes: { color: "gray" }
  }
);
~~~

Nhưng **ngữ nghĩa thay đổi** khác nhau: update bảo toàn những field không bị động đến, còn replace định nghĩa lại trạng thái document từ replacement. Không suy đoán bằng cách so sánh chỉ hai giá trị status/quantity.

## 8. Delete: còn khóa để nhận diện, không mặc định còn document

### 8.1. Thao tác nguồn

~~~javascript
db.lab_items.deleteOne({
  _id: "cs272-item-03"
});
~~~

### 8.2. Event minh họa

~~~javascript
{
  _id: { _data: "<token-delete>" },
  operationType: "delete",
  clusterTime: Timestamp({ t: 1780000004, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-03"
  }
}
~~~

**Không có fullDocument** trong ví dụ delete mặc định. MongoDB không thể lấy document hiện tại của bản ghi vừa bị xóa như khi xử lý insert. Nếu consumer thử:

~~~javascript
const id = event.fullDocument._id;
~~~

trên delete event, code có thể lỗi vì **fullDocument không tồn tại**.

**Cách đúng để xác định document bị xóa** là dùng **event.documentKey._id** cùng namespace và shard key khi cần.

### 8.3. Xử lý delete ở hệ thống đích

~~~javascript
if (event.operationType === "delete") {
  const sourceId = event.documentKey._id;

  // Pseudocode cho một adapter search index:
  // await index.deleteById(sourceId);
}
~~~

Xóa ở hệ thống đích nên **idempotent** nếu có thể: xóa một ID đã không còn không nên gây lỗi không thể phục hồi. Điều này quan trọng vì consumer có thể nhận lại cùng event khi resume/checkpoint/retry.

### 8.4. Cần thông tin trước khi xóa thì sao?

Nếu business muốn biết **status cũ, sku cũ hoặc tenantId cũ** của document vừa xóa, chỉ nhìn delete event mặc định có thể không đủ.

Các phương án:

1. **Pre-image**: bật lưu document trước thay đổi ở những phiên bản MongoDB hỗ trợ, và yêu cầu **fullDocumentBeforeChange**.
2. **Mô hình soft delete**: thay status/isDeleted bằng update để vẫn có dữ liệu document trước khi cleanup vật lý.
3. **Tạo audit/outbox event** cùng thao tác nghiệp vụ trong transaction khi cần bảo đảm mạnh hơn.
4. **Giữ dữ liệu ở read model** và xóa bằng documentKey, không cần đọc lại document nguồn đã bị xóa.

Không thể mặc định gọi **findOne(_id)** sau delete để lấy thông tin cũ: document đã bị xóa, nên findOne thường trả null.

## 9. fullDocument: lúc nào có, lúc nào không?

### 9.1. Hành vi mặc định

Với change stream mặc định:

~~~javascript
const stream = db.lab_items.watch();
~~~

Khái quát:

| operationType | fullDocument mặc định |
| --- | --- |
| **insert** | Thường chứa document đã insert |
| **update** | Không mặc định có document hoàn chỉnh |
| **replace** | Thường chứa replacement document |
| **delete** | Không chứa bản document đã xóa |

**Không dùng fullDocument để phân loại operationType.** Hãy xem **operationType** trước, rồi chọn trường cần đọc.

### 9.2. fullDocument: "updateLookup"

Khi consumer muốn nhận toàn bộ document hiện tại sau một update, có thể dùng:

~~~javascript
const stream = db.lab_items.watch(
  [],
  { fullDocument: "updateLookup" }
);
~~~

Với event update, MongoDB sẽ thực hiện lookup document đầy đủ sau khi event xuất hiện và cung cấp vào **fullDocument** khi tìm thấy theo semantics của option này.

Nhưng điểm cần nhớ:

**fullDocument từ updateLookup không phải lúc nào cũng là bản sao chính xác ngay tại thời điểm update event xảy ra.**

Ví dụ:

~~~text
T1: update quantity từ 5 -> 7
T2: update quantity từ 7 -> 9
T3: consumer xử lý event T1, updateLookup đọc document hiện tại

fullDocument của event T1 có thể thể hiện quantity=9
vì lookup xảy ra khi document đã được cập nhật tiếp.
~~~

Vì vậy:

- **updateDescription** phản ánh những thay đổi gắn với event update.
- **updateLookup** hỗ trợ lấy trạng thái hiện tại gần lúc lookup, không phải cơ chế tái tạo snapshot lịch sử hoàn hảo.
- Nếu document bị xóa trước khi lookup, **fullDocument** cho update có thể là **null**.
- Với tính đúng đắn cao, cân nhắc pre/post-images hoặc event/outbox chuyên biệt.

### 9.3. fullDocument: "whenAvailable" và "required"

Trên các phiên bản MongoDB hỗ trợ (ví dụ tính năng pre/post-images từ MongoDB 6.0), tùy chọn **fullDocument** có thể yêu cầu document post-image chính xác gắn với thao tác thay đổi:

~~~javascript
const stream = db.lab_items.watch(
  [],
  { fullDocument: "whenAvailable" }
);
~~~

Hoặc:

~~~javascript
const stream = db.lab_items.watch(
  [],
  { fullDocument: "required" }
);
~~~

Ý nghĩa khái quát:

- **whenAvailable:** trả post-image khi dữ liệu được lưu và còn khả dụng; nếu không, consumer phải chấp nhận field thiếu/không sẵn có theo semantics cụ thể.
- **required:** yêu cầu post-image; nếu không thể cung cấp, stream có thể phát lỗi theo cơ chế được hỗ trợ.

Các tùy chọn này **khác updateLookup**. Chúng dựa vào khả năng lưu **change stream pre/post-images** của collection và chính sách retention. Bật option watch ở consumer **không tự bật lưu images** cho collection nguồn.

### 9.4. Đừng dùng một option cho mọi yêu cầu

| Nhu cầu | Lựa chọn ban đầu có thể cân nhắc |
| --- | --- |
| Tạo search index từ insert | fullDocument mặc định |
| Đồng bộ một update theo patch | updateDescription, với patch processor đúng |
| Refresh cache bằng trạng thái mới gần hiện tại | fullDocument: "updateLookup", xử lý null/stale |
| Cần post-image đúng thao tác để audit | Pre/post-images và fullDocument option phù hợp |
| Cần document trước delete | fullDocumentBeforeChange với pre-images |
| Chỉ cần xóa theo ID | documentKey ở delete, không cần images |

## 10. Pre-images và post-images: giá trị trước/sau thay đổi

### 10.1. Pre-image

**Pre-image** là bản document **trước** thao tác update/replace/delete, nếu đã bật tính năng và image được lưu/khả dụng trong môi trường hỗ trợ.

Ví dụ:

~~~javascript
{
  operationType: "delete",
  documentKey: { _id: "cs272-item-03" },
  fullDocumentBeforeChange: {
    _id: "cs272-item-03",
    dataset: "change-stream-v1",
    sku: "P-003",
    status: "active",
    quantity: 1
  }
}
~~~

Nhờ pre-image, consumer có thể biết document trước khi bị xóa, ví dụ dùng để tạo audit record hoặc tìm tenant cũ.

### 10.2. Post-image

**Post-image** là bản document **sau** thay đổi, gắn với thao tác tương ứng, khác với việc lookup trạng thái có thể đã bị những update sau đó sửa tiếp.

Với yêu cầu chính xác theo từng event, post-image có thể giúp consumer xác định trạng thái sau update mà không phải tự áp những đường dẫn nested/Array.

### 10.3. Điều kiện cần

Trên phiên bản có hỗ trợ Change Stream pre/post-images, collection phải được cấu hình lưu images; consumer dùng các option tương ứng:

~~~javascript
// Chỉ là ví dụ cấu hình dành cho collection trong lab riêng.
// Cần quyền quản trị thích hợp và MongoDB version hỗ trợ.
db.getSiblingDB("mongo_change_stream_lab").runCommand({
  collMod: "lab_items",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

**Không chạy collMod trên production hoặc collection dùng chung chỉ để làm bài.** Việc bật images có chi phí lưu trữ và retention; cần duyệt quy trình của đội vận hành.

Sau đó, consumer có thể yêu cầu:

~~~javascript
const stream = db.lab_items.watch(
  [],
  {
    fullDocumentBeforeChange: "whenAvailable",
    fullDocument: "whenAvailable"
  }
);
~~~

Nếu yêu cầu nghiêm ngặt, cân nhắc **"required"** và xử lý lỗi khi image không thể được cung cấp. Điều kiện availability phụ thuộc lúc bật feature, thời điểm sự kiện được tạo, retention và khả năng trả images.

### 10.4. Chi phí và retention

Pre/post-images không tồn tại vô thời hạn. MongoDB có cơ chế retention và cleanup riêng, đồng thời Change Streams còn phụ thuộc vào cửa sổ lịch sử oplog. Một consumer dừng quá lâu có thể không còn resume hoặc lấy image mong muốn.

Không xem pre-image store như kho audit độc lập và vô hạn. Với yêu cầu lưu vết pháp lý lâu dài, thiết kế hệ thống audit/sự kiện bền vững riêng, cùng chính sách quyền truy cập, mã hóa và retention.

## 11. Lab mongosh: quan sát cả bốn loại event

Đây là lab chính của bài. Dùng **hai terminal mongosh** cùng kết nối tới **một replica set/sharded cluster thực hành**. Một terminal mở Change Stream; terminal còn lại ghi dữ liệu mẫu.

### 11.1. Phạm vi và điều kiện

- Database **mongo_change_stream_lab**.
- Collection **lab_items**.
- Dataset **change-stream-v1**.
- Các document có ID cố định **cs272-item-01** tới **cs272-item-04**.
- Kết nối tới replica set hoặc mongos, không dùng standalone mongod.
- Người dùng có quyền watch/read và CRUD trên database lab.
- Không cần drop collection, tạo failover hoặc thay đổi cấu hình cluster.

Lần đầu mở terminal và kiểm tra:

~~~javascript
const info = db.hello();

printjson({
  replicaSetName: info.setName,
  mongos: info.msg === "isdbgrid",
  isWritablePrimary: info.isWritablePrimary
});

if (!info.setName && info.msg !== "isdbgrid") {
  throw new Error(
    "Cần replica set hoặc sharded cluster để thực hành Change Streams."
  );
}
~~~

### 11.2. Bước A — seed dữ liệu trước khi watch

Chạy ở terminal B **trước khi mở watcher**:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_change_stream_lab");
  const items = lab.getCollection("lab_items");
  const tag = "change-stream-v1";

  const ids = [
    "cs272-item-01",
    "cs272-item-02",
    "cs272-item-03",
    "cs272-item-04"
  ];

  // Chỉ xóa 4 ID cố định của lab; không drop collection.
  items.deleteMany(
    { _id: { $in: ids } },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  items.insertMany(
    [
      {
        _id: "cs272-item-01",
        dataset: tag,
        sku: "P-001",
        status: "draft",
        quantity: NumberInt(5),
        obsoleteFlag: true,
        attributes: { color: "black", size: "M" },
        labels: ["new", "web"]
      },
      {
        _id: "cs272-item-02",
        dataset: tag,
        sku: "P-002",
        status: "draft",
        quantity: NumberInt(2),
        legacy: "temporary",
        attributes: { color: "red", size: "L" },
        labels: ["sale"]
      },
      {
        _id: "cs272-item-03",
        dataset: tag,
        sku: "P-003",
        status: "active",
        quantity: NumberInt(1),
        attributes: { color: "green" },
        labels: []
      }
    ],
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  printjson({
    seeded: items.countDocuments({ _id: { $in: ids } }),
    items: items.find(
      { _id: { $in: ids } },
      { _id: 1, sku: 1, status: 1, quantity: 1 }
    ).sort({ _id: 1 }).toArray()
  });
})();
~~~

**Kết quả mong đợi:** seeded = **3**: item-01, item-02, item-03. **item-04 chưa tồn tại** để watcher nhận một event insert sau đó.

Việc seed sinh những change events trong lịch sử MongoDB, nhưng vì **watcher chưa mở**, đoạn lab này không dùng chúng làm bốn events cần xem. Mục đích là quan sát những thao tác phát sinh **sau khi watcher được thiết lập**.

### 11.3. Bước B — Terminal A mở Change Stream

Mở **một terminal mongosh khác**, kết nối cùng cluster rồi chạy:

~~~javascript
const lab = db.getSiblingDB("mongo_change_stream_lab");
const items = lab.getCollection("lab_items");

const watchedIds = [
  "cs272-item-01",
  "cs272-item-02",
  "cs272-item-03",
  "cs272-item-04"
];

const changeStream = items.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        },
        "documentKey._id": { $in: watchedIds }
      }
    }
  ],
  {
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  }
);

print("Watcher đã mở; thực hiện các lệnh ở terminal B.");

for (let i = 0; i < 4; i++) {
  const event = await changeStream.next();

  print("Event " + (i + 1) + ": " + event.operationType);
  printjson({
    operationType: event.operationType,
    eventToken: event._id,
    clusterTime: event.clusterTime,
    ns: event.ns,
    documentKey: event.documentKey,
    fullDocument: event.fullDocument,
    updateDescription: event.updateDescription,
    fullDocumentBeforeChange: event.fullDocumentBeforeChange
  });
}

await changeStream.close();
print("Đã nhận đủ 4 events; watcher đã đóng.");
~~~

**Quan trọng:** Terminal A có thể **chờ** ở changeStream.next() cho đến khi có event phù hợp. Không cần liên tục nhấn Enter hay mở lại stream. Hãy giữ terminal A ở trạng thái đang chạy rồi thực hiện Bước C.

Nếu terminal A không hỗ trợ cú pháp top-level await do môi trường shell quá cũ, cập nhật mongosh phù hợp hoặc dùng script async IIFE theo JavaScript runtime được hỗ trợ; logic vẫn là **mở cursor trước, sau đó mới phát các lệnh ghi**.

### 11.4. Bước C — Terminal B tạo bốn thay đổi

**Sau khi thấy terminal A thông báo watcher đã mở**, chạy lần lượt:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_change_stream_lab");
  const items = lab.getCollection("lab_items");
  const tag = "change-stream-v1";
  const wc = { w: "majority", wtimeout: 10000 };

  // 1. INSERT: item-04 mới.
  const inserted = items.insertOne(
    {
      _id: "cs272-item-04",
      dataset: tag,
      sku: "P-004",
      status: "draft",
      quantity: NumberInt(3),
      attributes: { color: "white" },
      labels: ["featured"]
    },
    { writeConcern: wc }
  );

  // 2. UPDATE: đổi một số field, xóa obsoleteFlag.
  const updated = items.updateOne(
    { _id: "cs272-item-01", dataset: tag },
    {
      $set: {
        status: "active",
        "attributes.color": "navy"
      },
      $inc: { quantity: 2 },
      $unset: { obsoleteFlag: "" }
    },
    { writeConcern: wc }
  );

  // 3. REPLACE: thay toàn bộ item-02, bỏ các field legacy cũ.
  const replaced = items.replaceOne(
    { _id: "cs272-item-02", dataset: tag },
    {
      _id: "cs272-item-02",
      dataset: tag,
      sku: "P-002",
      status: "archived",
      quantity: NumberInt(0),
      attributes: { color: "gray" }
    },
    { writeConcern: wc }
  );

  // 4. DELETE: xóa cả document item-03.
  const deleted = items.deleteOne(
    { _id: "cs272-item-03", dataset: tag },
    { writeConcern: wc }
  );

  printjson({
    insertedId: inserted.insertedId,
    updateMatched: updated.matchedCount,
    updateModified: updated.modifiedCount,
    replaceMatched: replaced.matchedCount,
    replaceModified: replaced.modifiedCount,
    deletedCount: deleted.deletedCount
  });
})();
~~~

**Kết quả mong đợi khi collection ở trạng thái seed ban đầu:**

| Operation | Kết quả phía ghi |
| --- | --- |
| insertOne item-04 | insert thành công |
| updateOne item-01 | matchedCount=1, modifiedCount=1 |
| replaceOne item-02 | matchedCount=1, modifiedCount=1 |
| deleteOne item-03 | deletedCount=1 |

Terminal A nên nhận **bốn event** theo thứ tự thao tác đã commit trong một luồng ghi nối tiếp:

~~~text
Event 1: insert
Event 2: update
Event 3: replace
Event 4: delete
~~~

Nếu có writer khác cùng sửa những ID cố định, hoặc bạn seed/chạy lệnh khác trong khi watcher hoạt động, số event và thứ tự có thể khác. Lab này giả định **không có thao tác cạnh tranh trên bốn ID**.

### 11.5. Bước D — đọc kết quả cuối

Ở terminal B:

~~~javascript
db.getSiblingDB("mongo_change_stream_lab")
  .getCollection("lab_items")
  .find({
    _id: {
      $in: [
        "cs272-item-01",
        "cs272-item-02",
        "cs272-item-03",
        "cs272-item-04"
      ]
    }
  })
  .sort({ _id: 1 })
  .toArray();
~~~

Diễn giải:

- **item-01:** status=active, quantity=7, attributes.color=navy; obsoleteFlag không còn.
- **item-02:** status=archived, quantity=0; field legacy và attributes.size không còn vì replace.
- **item-03:** không còn vì delete.
- **item-04:** tồn tại vì insert.

Việc database có ba document cuối cùng không liên quan đến **số event = 4**: event là các **chuyển trạng thái**, không phải danh sách toàn bộ document hiện có.

### 11.6. Nếu không thấy event

Kiểm tra lần lượt:

1. Terminal A có thực sự kết nối đến replica set/mongos không?
2. Watcher đã mở **trước** khi chạy Bước C chưa?
3. Database/collection và bốn _id có đúng không?
4. Terminal B có báo matchedCount/deletedCount bằng 1 không?
5. Có thao tác nào bị lỗi write concern hoặc thiếu quyền không?
6. Watch pipeline có filter nhầm **fullDocument.dataset** làm rơi delete không?
7. Cursor có bị close, invalidate hoặc lỗi kết nối không?

Không sửa config server, oplog hoặc gây failover chỉ để “làm event hiện ra”.

## 12. Lọc events trong watch pipeline: phải nhớ delete không có fullDocument

### 12.1. Lọc đúng bốn operationType

~~~javascript
const stream = db.lab_items.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

Đây là cách thuận tiện để chỉ xử lý thay đổi CRUD document trong một bài học. Change Streams còn có những loại event khác, vì vậy không nên viết consumer production mà không xác định hành vi đối với các event quản trị/invalidating.

### 12.2. Lỗi: lọc chỉ dựa trên fullDocument

Ví dụ dễ sai:

~~~javascript
const stream = db.lab_items.watch([
  {
    $match: {
      "fullDocument.dataset": "change-stream-v1"
    }
  }
]);
~~~

Filter này có thể **loại delete**, vì delete event mặc định không có fullDocument. Nó cũng có thể loại update khi fullDocument không được yêu cầu hoặc không tìm được.

### 12.3. Lọc theo documentKey và operationType

Trong lab, _id có prefix riêng, nhưng query change stream không cần giả định String regex trên token. Với danh sách biết trước:

~~~javascript
const stream = db.lab_items.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      },
      "documentKey._id": {
        $in: [
          "cs272-item-01",
          "cs272-item-02",
          "cs272-item-03",
          "cs272-item-04"
        ]
      }
    }
  }
]);
~~~

Cách này giữ được delete vì documentKey tồn tại với delete. Trong hệ multi-tenant thực tế, có thể phải kết hợp namespace/shard key và quyền truy cập; **không mặc định mọi documentKey đều chứa tenantId** nếu schema/sharding khác.

### 12.4. Projection trong stream phải giữ resume token

Một lỗi rất nghiêm trọng:

~~~javascript
// Không nên làm như thế này:
db.lab_items.watch([
  { $project: { _id: 0, operationType: 1, documentKey: 1 } }
]);
~~~

Change Stream **_id** là resume token. MongoDB yêu cầu consumer không làm thay đổi/loại bỏ resume token bằng các stage trong watch pipeline; thao tác như trên có thể gây lỗi hoặc khiến stream không thể tiếp tục đúng.

Nếu muốn log chỉ vài field, hãy **giữ nguyên event trong cursor** rồi tạo một object log rút gọn ở phía ứng dụng. Không sửa **event._id** bên trong pipeline.

### 12.5. Không tùy tiện dùng mọi aggregation stage

Pipeline của Change Stream có những **hạn chế khác aggregation pipeline thông thường**. Các stage biến đổi cấu trúc như $group, $sort, $out, $merge hoặc stage thay đổi ID/nhận dạng event không thể tùy ý áp vào watch như một aggregate truy vấn dữ liệu.

Hãy dùng những stage được MongoDB hỗ trợ cho Change Streams, đặc biệt **$match** và phép biến đổi không làm mất token, và đọc tài liệu phiên bản nếu muốn thêm stage. Với việc tính tổng, thường nên **xử lý ở consumer hoặc pipeline cập nhật read model** thay vì cố biến Change Stream thành một aggregation batch.

## 13. Resume token: điểm tiếp tục khi consumer bị ngắt

### 13.1. Vì sao cần checkpoint?

Một consumer có thể bị khởi động lại vì:

- Deploy phiên bản mới.
- Mất kết nối mạng.
- Primary election/failover.
- Worker crash.
- API sink tạm thời không sẵn sàng.

Nếu mỗi lần restart đều gọi **watch()** mới mà không có resume token, consumer bắt đầu một stream mới ở thời điểm mới và **có thể bỏ sót thay đổi** xảy ra khi nó offline.

### 13.2. Lưu event._id chứ không lưu document ID

Ví dụ:

~~~javascript
const token = event._id;                    // Resume token
const productId = event.documentKey._id;   // ID sản phẩm
~~~

Checkpoint nên lưu **token ở đúng dạng BSON** hoặc dạng Extended JSON bảo toàn thông tin type khi bắt buộc serialize. Không lấy:

~~~javascript
event.clusterTime.toString()
~~~

làm resume token; cũng không dùng mỗi documentKey._id.

### 13.3. resumeAfter

Với một resume token đã lưu hợp lệ:

~~~javascript
const stream = db.lab_items.watch(
  [],
  {
    resumeAfter: savedResumeToken,
    fullDocument: "updateLookup"
  }
);
~~~

**resumeAfter** yêu cầu tiếp tục **sau** event tương ứng. Vì thế, consumer thường checkpoint token của event **đã xử lý thành công**, không phải token của event vừa nhận nhưng chưa xử lý.

### 13.4. Đặt checkpoint trước hay sau xử lý?

Hai lựa chọn đều có rủi ro:

~~~text
CÁCH SAI CHO HỆ CẦN KHÔNG BỎ SÓT:
  nhận event E
  lưu token của E
  xử lý E ở hệ thống đích

Nếu crash sau lưu token nhưng trước xử lý:
  resumeAfter E -> bỏ qua E
~~~

Thiết kế thông thường:

~~~text
  nhận event E
  xử lý E tại hệ thống đích
  ghi checkpoint token của E

Nếu crash sau xử lý nhưng trước checkpoint:
  E có thể được xử lý lại
~~~

Vì vậy, consumer nên **idempotent**. Nếu sink và checkpoint nằm trong cùng transaction phù hợp, có thể kết hợp để giảm khoảng rủi ro trong phạm vi đó; nhưng **transaction MongoDB không thể rollback side effect ở một hệ thống ngoài** như search engine hoặc email provider.

### 13.5. Resume token không tồn tại vô hạn

Change Streams phụ thuộc vào lịch sử oplog/điều kiện retention. Một consumer offline quá lâu có thể không còn resume được từ token cũ vì entry liên quan đã ra khỏi oplog.

Khi gặp lỗi resume không thể phục hồi, không nên:

1. Xóa checkpoint trong im lặng.
2. Bắt đầu watch mới.
3. Vẫn tuyên bố read model đã đồng bộ hoàn chỉnh.

Thay vào đó, kích hoạt **quy trình rebuild/backfill** có kiểm soát, xác định điểm bắt đầu mới và xử lý khoảng dữ liệu có thể đã bị bỏ sót.

### 13.6. Invalidate, resumeAfter và startAfter

Những thao tác như **drop collection**, **rename collection** hoặc **drop database** có thể phát sinh event quản trị và **invalidate** stream trong các trường hợp tương ứng.

Không được coi invalidate là một delete thông thường.

**resumeAfter** không dùng để tiếp tục sau invalidate event theo cách một event CRUD bình thường. Với phiên bản hỗ trợ, **startAfter** có thể dùng để mở stream mới **sau token invalidate** theo semantics của MongoDB.

Sự khác nhau:

- **resumeAfter:** tiếp tục từ một event trước đó, ngoại trừ trường hợp token invalidate không được hỗ trợ theo cùng cách.
- **startAfter:** có thể bắt đầu sau một invalidate event trong những tình huống thích hợp.
- **startAtOperationTime:** bắt đầu từ một mốc thời gian oplog đủ điều kiện, không phải thay thế hoàn toàn cho token checkpoint.

Tất cả phụ thuộc **lịch sử còn trong oplog** và phạm vi watch. Không khôi phục được dữ liệu đã mất chỉ bằng cách đặt một timestamp mới hơn.

### 13.7. Token có thể thay đổi hình dạng theo version

Resume token là **opaque**. Không parse trường **_data** để suy ra shard, timestamp, document ID hoặc nghiệp vụ. Format token có thể thay đổi giữa các phiên bản.

Consumer lưu/khôi phục token ở dạng đầy đủ và chuyển nguyên vẹn vào API watch. Nếu sử dụng JSON serialization, cần bảo toàn BSON types và không làm mất cấu trúc token.

## 14. Node.js driver: consumer xử lý bốn loại sự kiện

Đoạn này minh họa một consumer Node.js sử dụng package **mongodb**. Nó không triển khai đầy đủ một dịch vụ production; mục tiêu là cho thấy **switch theo operationType** và checkpoint/resume. Chạy trên replica set/sharded lab, dùng URI từ môi trường.

### 14.1. Consumer chỉ log đúng thông tin

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

const items = client
  .db("mongo_change_stream_lab")
  .collection("lab_items");

const stream = items.watch(
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
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  }
);

try {
  for await (const event of stream) {
    const id = event.documentKey?._id;

    switch (event.operationType) {
      case "insert":
        console.log("INSERT", id, event.fullDocument);
        break;
      case "update":
        console.log("UPDATE", id, event.updateDescription);
        console.log("Current document:", event.fullDocument ?? null);
        break;
      case "replace":
        console.log("REPLACE", id, event.fullDocument);
        break;
      case "delete":
        console.log("DELETE", id);
        break;
      default:
        console.log("OTHER EVENT", event.operationType);
    }

    // Chỉ in token minh họa; ví dụ này CHƯA checkpoint.
    console.log("Resume token:", event._id);
  }
} finally {
  await stream.close();
  await client.close();
}
~~~

Consumer này chạy liên tục cho đến khi bạn dừng tiến trình hoặc xảy ra lỗi. Một ứng dụng production cần signal handling, retries, checkpoint, metrics, logging bảo mật và quản lý lifecycle.

### 14.2. Phân biệt cách cập nhật search index

Ví dụ logic:

~~~javascript
async function applyChange(event, sink) {
  const namespace = event.ns;
  const id = event.documentKey?._id;

  if (!id) {
    throw new Error("Event thiếu documentKey._id");
  }

  const sinkId = namespace.db + "." + namespace.coll + ":" + id;

  switch (event.operationType) {
    case "insert":
      if (!event.fullDocument) {
        throw new Error("Insert event thiếu fullDocument");
      }
      await sink.replaceById(sinkId, event.fullDocument);
      return;

    case "update":
      // Cách A: dùng delta (sink phải hỗ trợ đúng updateDescription).
      // await sink.applyMongoPatch(sinkId, event.updateDescription);

      // Cách B: dùng trạng thái gần hiện tại từ updateLookup.
      // CHÚ Ý: có thể null hoặc phản ánh update mới hơn.
      if (!event.fullDocument) {
        throw new Error("Update không có document để đồng bộ");
      }
      await sink.replaceById(sinkId, event.fullDocument);
      return;

    case "replace":
      if (!event.fullDocument) {
        throw new Error("Replace event thiếu fullDocument");
      }
      await sink.replaceById(sinkId, event.fullDocument);
      return;

    case "delete":
      await sink.deleteById(sinkId);
      return;

    default:
      // Các operationType khác cần policy riêng.
      return;
  }
}
~~~

**sink** ở đây là một adapter giả định, không phải API của package mongodb. Hàm dùng để làm rõ khác biệt giữa **patch** và **replace**.

Trong production:

- **insert/replace:** upsert hoặc replace idempotent.
- **update:** patch đúng semantics hoặc làm mới từ fullDocument với hiểu biết về stale lookup.
- **delete:** xóa theo documentKey, không tìm fullDocument.
- **events khác:** policy riêng; không coi drop/invalidate là delete một document.

### 14.3. Checkpoint trong MongoDB

Một skeleton consumer lưu token vào collection checkpoint:

~~~javascript
import { MongoClient } from "mongodb";

async function consumeWithCheckpoint(uri) {
  const client = new MongoClient(uri);
  await client.connect();

  const lab = client.db("mongo_change_stream_lab");
  const items = lab.collection("lab_items");
  const checkpoints = lab.collection("lab_checkpoints");
  const consumerId = "cs272-lab-consumer";

  const checkpoint = await checkpoints.findOne({
    _id: consumerId
  });

  const options = {
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  };

  if (checkpoint?.resumeToken) {
    options.resumeAfter = checkpoint.resumeToken;
  }

  const stream = items.watch(
    [
      {
        $match: {
          operationType: {
            $in: ["insert", "update", "replace", "delete"]
          }
        }
      }
    ],
    options
  );

  try {
    for await (const event of stream) {
      // processAndPersistChange là hàm do ứng dụng triển khai.
      // Nó phải đảm bảo xử lý hoàn tất hoặc ném lỗi.
      await processAndPersistChange(event);

      // Chỉ lưu token SAU khi xử lý event thành công.
      await checkpoints.updateOne(
        { _id: consumerId },
        {
          $set: {
            resumeToken: event._id,
            lastOperationType: event.operationType,
            lastDocumentId: event.documentKey?._id,
            updatedAt: new Date()
          }
        },
        {
          upsert: true,
          writeConcern: {
            w: "majority",
            wtimeoutMS: 10000
          }
        }
      );
    }
  } finally {
    await stream.close();
    await client.close();
  }
}

// Ví dụ là skeleton: phải cung cấp processAndPersistChange.
// await consumeWithCheckpoint(process.env.MONGODB_URI);
~~~

**Quan trọng:** đây là skeleton về trình tự, không phải bảo đảm exactly-once.

Nếu xử lý ở sink thành công rồi crash trước khi checkpoint, event có thể được xử lý **lần nữa** khi khôi phục. Tác động tại sink phải idempotent hoặc có dedup theo khóa phù hợp. Nếu checkpoint và sink thuộc cùng MongoDB cluster, một transaction có thể giúp commit chúng cùng nhau trong các điều kiện được hỗ trợ; với hệ thống ngoài, cần giao thức ứng dụng riêng.

### 14.4. Đừng dùng resume token để loại duplicate document nghiệp vụ

Một Change Stream có thể chứa:

~~~text
E1: insert document X       token R1
E2: update document X       token R2
E3: update document X       token R3
E4: replace document X      token R4
E5: delete document X       token R5
~~~

Nếu consumer dedup bằng documentKey._id = X, nó chỉ xử lý E1 và bỏ E2-E5 — sai hoàn toàn.

Nếu consumer dedup bằng **token** nhưng vẫn đánh dấu token trước khi sink thành công, nó có thể mất event. Cần thiết kế **token checkpoint, xử lý idempotent và thứ tự áp dụng** cùng nhau.

## 15. Upsert: vì sao một lệnh update có thể tạo insert event?

### 15.1. Upsert tạo mới

~~~javascript
db.lab_items.updateOne(
  { _id: "cs272-upsert-01" },
  {
    $set: {
      sku: "P-100",
      status: "draft",
      dataset: "change-stream-v1"
    }
  },
  { upsert: true }
);
~~~

Nếu document chưa tồn tại, MongoDB tạo document mới. Change Stream phản ánh **thay đổi thực tế ở dữ liệu**, nên operationType có thể là **"insert"**, mặc dù API được gọi tên **updateOne**.

### 15.2. Upsert khớp document cũ

Khi document đã tồn tại và cùng lệnh updateOne với upsert:true khớp nó, thao tác có thể tạo **update** event khi dữ liệu được thay đổi.

Do đó:

- Đừng xác định event bằng tên method được service log.
- Hãy dùng **operationType** trong Change Stream.
- Xem thêm **documentKey**, **updateDescription/fullDocument** để biết ảnh hưởng.

### 15.3. Không có thay đổi thực sự

Một update trùng giá trị cũ có thể không sinh thay đổi dữ liệu hữu ích theo semantics của server. Đừng giả định **mỗi lần gọi updateOne luôn phát một event update**.

Nếu workflow cần ghi nhận **mọi yêu cầu kể cả no-op**, Change Stream không phải log request nghiệp vụ. Hãy dùng audit/outbox record có chủ đích.

## 16. Thứ tự events, transactions và clusterTime

### 16.1. Thứ tự trên một stream

Change Stream trả các event theo thứ tự của lịch sử thay đổi được server cung cấp trong phạm vi watch. Điều này phù hợp khi consumer xử lý tuần tự một stream để xây một bản sao dựa trên sự kiện.

Tuy nhiên:

- Nhiều consumer chạy độc lập có thể xử lý với tốc độ khác nhau.
- Nếu bạn tự phân phối events tới nhiều worker song song, **thứ tự áp dụng ở sink có thể thay đổi**.
- Hai events của cùng document cần được xử lý theo thứ tự hợp lý để không cập nhật ngược trạng thái.
- Với sharded cluster/transactions, event metadata và ordering có những quy tắc riêng; không suy luận tuyệt đối chỉ từ đồng hồ treo tường.

### 16.2. Transactions tạo nhiều events

Một transaction có thể sửa hai document:

~~~text
BEGIN TRANSACTION
  update Order A
  update Order B
COMMIT
~~~

Change Stream có thể phát **nhiều change events** cho các document được thay đổi sau commit, thay vì một event duy nhất có operationType "transaction".

Các event liên quan có thể mang metadata như **lsid, txnNumber** và có thể chia sẻ **clusterTime** theo semantics của phiên bản.

Không dùng **clusterTime** làm khóa duy nhất của event. Dùng **resume token** để xác định vị trí trong stream.

### 16.3. Đừng nghĩ Change Stream là distributed transaction với sink

MongoDB commit một giao dịch nguồn; consumer đọc events và gửi cập nhật tới search engine. Việc gửi đó **không nằm trong transaction nguồn**. Nếu search engine lỗi, MongoDB không tự rollback transaction đã commit.

Với hệ thống cần dữ liệu đồng bộ có thể phục hồi:

- Lưu checkpoint.
- Retry có giới hạn/backoff.
- Xử lý idempotent.
- Rebuild/backfill khi mất lịch sử oplog.
- Giám sát lag và dead-letter/quarantine cho event không thể xử lý.

### 16.4. Không dùng wallTime làm thứ tự tuyệt đối

Wall clock có thể bị lệch giữa host. Với ordered event processing, hãy dựa vào **stream/resume semantics** và dữ liệu đảm bảo thứ tự do hệ thống cung cấp, không dùng mỗi **wallTime** làm khóa sort toàn cluster.

## 17. Các loại event ngoài bốn CRUD operationType

Một consumer production không nên giả định Change Stream chỉ có insert/update/replace/delete.

Tùy phiên bản, phạm vi watch và các option như **showExpandedEvents**, bạn có thể gặp các loại như:

- **drop:** collection bị drop.
- **rename:** collection đổi tên.
- **dropDatabase:** database bị drop.
- **invalidate:** stream không còn tiếp tục bình thường sau một số thao tác thay đổi namespace.
- Các event DDL/metadata mở rộng như create, createIndexes, dropIndexes, modify hoặc các thao tác sharding theo những phiên bản hỗ trợ.

Ví dụ tư duy:

~~~text
deleteOne({_id:"X"})
  -> delete event cho document X

drop collection "products"
  -> drop/invalidate và các event liên quan
  -> không phải hàng triệu delete events cho từng product
~~~

Vì vậy, nếu search index gắn một-một với collection, **drop** có thể yêu cầu quy trình invalidation/rebuild riêng; không thể chỉ đợi delete events để xóa từng document.

### 17.1. Policy gợi ý

| operationType | Hành vi consumer |
| --- | --- |
| insert/update/replace/delete | Xử lý CRUD như bài học |
| drop/rename/dropDatabase | Xử lý namespace/metadata, báo trạng thái và quyết định rebuild |
| invalidate | Đóng/recreate stream theo semantics hỗ trợ, kiểm tra token và scope |
| Event DDL mở rộng | Bật option khi thật sự cần, thêm handler và schema phù hợp |
| Event lạ ở version mới | Log/alert có kiểm soát; không mặc định xóa dữ liệu đích |

Khi viết switch-case, default branch **không nên** giả định “không phải insert thì là delete”.

## 18. Đồng bộ search index, cache và read model theo bốn loại

### 18.1. Search index

Một index phụ lưu sản phẩm để tìm kiếm:

~~~text
MongoDB products  --->  Change Stream  --->  Search Index
~~~

Chiến lược:

- **insert:** tạo/upsert document trong search index.
- **update:** cập nhật những field được đổi hoặc rebuild snapshot khi có fullDocument thích hợp.
- **replace:** thay toàn bộ nội dung index của product.
- **delete:** xóa product theo documentKey.

Không thể dùng chung một hành động **merge tất cả fields** cho replace và update nếu replacement có quyền xóa các field cũ.

### 18.2. Cache invalidation

Với cache chỉ cần loại bỏ key khi dữ liệu thay đổi, handler có thể đơn giản:

~~~javascript
if (["insert", "update", "replace", "delete"].includes(
  event.operationType
)) {
  const id = event.documentKey?._id;
  // await cache.delete("product:" + id);
}
~~~

Nhưng:

- Cache key có thể cần tenantId/namespace.
- Event đến trễ nên cache có thể tạm stale.
- Cache invalidation sau một update không phải bảo đảm transactional read-your-writes.
- Nếu một document bị xóa và ID tái sử dụng, phải định nghĩa thế hệ/version để tránh event cũ xóa dữ liệu mới.

### 18.3. Materialized view

Giả sử view lưu **số sản phẩm active theo tenant**:

- insert active: tăng count.
- update draft → active: tăng count.
- update active → draft: giảm count.
- replace: cần biết trạng thái trước và sau để tính delta.
- delete: cần biết trạng thái cũ để biết có giảm count không.

**Chỉ nhìn updateDescription.updatedFields.status = "active" chưa đủ để biết trạng thái cũ là draft hay active.** Đặc biệt nếu các chuyển trạng thái hoặc event phát lại có thể xảy ra.

Các hướng:

1. Dùng pre-image/post-image khi phù hợp.
2. Duy trì state từng document trong sink và áp dụng chuyển trạng thái idempotent.
3. Ghi event nghiệp vụ rõ ràng (stateFrom/stateTo) trong outbox.
4. Định kỳ reconcile bằng cách tính lại từ MongoDB.

Không cập nhật counter một cách mù quáng cho mọi update vì có thể đếm trùng khi retry.

### 18.4. Audit

Change Stream hữu ích để phát hiện document đã được sửa, nhưng **không phải hệ thống audit hoàn chỉnh**:

- Event không mặc định chứa userId/actor hoặc lý do nghiệp vụ.
- Delete không mặc định chứa document cũ.
- Lịch sử change stream có cửa sổ retention.
- Một API request không làm thay đổi dữ liệu có thể không có event.
- Các thao tác rollback/replication và schema event cần hiểu đúng.

Nếu cần log tuân thủ, cần thiết kế audit record có **actor, requestId, lý do, timestamp, payload phù hợp và retention**, cùng chính sách bảo mật riêng.

## 19. Backfill dữ liệu ban đầu và bắt kịp Change Stream

### 19.1. Watch không tự gửi toàn bộ collection hiện có

Mở:

~~~javascript
const stream = db.products.watch();
~~~

không có nghĩa MongoDB sẽ phát insert event cho **tất cả products đã tồn tại từ năm trước**. Change Stream theo dõi thay đổi từ điểm bắt đầu được xác định.

Vì vậy, để xây mới một search index từ collection đã có hàng triệu document, cần:

1. **Backfill** một snapshot các document hiện tại.
2. **Consume thay đổi** xảy ra trong khi backfill.
3. Reconcile thứ tự/thời điểm để tránh bỏ sót hoặc áp event cũ đè lên dữ liệu mới.
4. Chuyển sang chế độ consume liên tục.

### 19.2. Race condition khi backfill

Mẫu dễ bỏ sót:

~~~text
T1: Bắt đầu quét products hiện có
T2: Product X được update
T3: Quét xong
T4: Mới mở Change Stream

Update tại T2 có thể không được phản ánh đúng
trong snapshot hoặc stream, tùy thứ tự quét.
~~~

Không chỉ “quét xong rồi mới watch” nếu yêu cầu không mất delta. Cần một quy trình đã được thiết kế cho **điểm bắt đầu stream + snapshot nhất quán + replay** theo version và khả năng của hệ thống.

### 19.3. Khi resume token hết hạn

Nếu consumer offline lâu hơn cửa sổ oplog, hướng xử lý có thể là:

- Dừng công bố read model là cập nhật đầy đủ.
- Gắn trạng thái degraded/rebuild.
- Bắt đầu quy trình snapshot/backfill mới có ranh giới thời gian phù hợp.
- Theo dõi token/lag sau khi chuyển sang consume liên tục.
- Đối soát số document và dữ liệu mẫu với nguồn.

Không bỏ qua lỗi resume rồi tiếp tục làm như thể chưa từng mất event.

## 20. Giới hạn về độ trễ, kích thước và tài nguyên

### 20.1. Không phải event bus vô hạn

Change Streams tận dụng oplog và cơ chế replication của MongoDB. Nó **không thay thế** một event broker có retention dài, partition management và replay policy riêng cho mọi use case.

Nếu có nhiều consumer phải xử lý các workflow độc lập, có thể đưa change events vào một pipeline trung gian durable theo kiến trúc tổ chức, cùng cơ chế dead-letter và observability.

### 20.2. Kích thước event

Event có metadata, fullDocument, updateDescription và có thể cả pre/post-images. Khi bật images cho document lớn, event có thể tăng đáng kể; cần tính đến giới hạn kích thước BSON document và các quy tắc Change Stream đối với event lớn trong phiên bản đang dùng.

**Không** bật tất cả pre/post-images cho mọi collection lớn mà không đo chi phí.

### 20.3. Consumer chậm

Một consumer chậm làm khoảng cách giữa **vị trí event mới nhất** và **resume token đã checkpoint** lớn dần. Nếu nó chậm lâu tới mức token rơi khỏi cửa sổ oplog, việc resume có thể không còn được hỗ trợ.

Các chỉ số nên theo dõi:

- Thời gian từ thay đổi nguồn đến lúc consumer xử lý xong.
- Tuổi của token đã checkpoint.
- Số event/giây và số event xử lý lỗi.
- Số lần reconnect/resume.
- Tần suất lỗi do token cũ.
- Lag của replication/Change Stream theo topology.
- Tỉ lệ cập nhật thất bại ở sink.

### 20.4. Nhiều watcher

Mỗi watcher có cursor/connection và chi phí lọc/xử lý. Hàng nghìn watcher cho cùng một collection có thể tạo áp lực lớn hơn một consumer có thể fan-out tới các service khác.

Không tạo một Change Stream mới cho mỗi HTTP request chờ thay đổi khi không có thiết kế kiểm soát connection, timeout và vòng đời.

### 20.5. Sharded cluster

Khi watch sharded collection hoặc toàn deployment:

- Những thay đổi đến từ nhiều shards.
- mongos và thành phần cluster tham gia hợp nhất luồng event.
- Token, ordering và resume cần theo semantics hỗ trợ, không parse thủ công.
- Dữ liệu có thể thay đổi placement giữa các shard.
- Consumer cần tính đến namespace/documentKey và các thay đổi sharding.

Không suy ra vị trí shard hiện tại chỉ từ một token hoặc từ nơi document được insert ban đầu.

## 21. Lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| watch báo không hỗ trợ | MongoDB standalone hoặc topology/permission không phù hợp | Dùng replica set/sharded cluster hợp lệ |
| Không thấy event vừa insert | Watcher mở sau thao tác ghi hoặc filter sai | Mở watch trước, kiểm tra scope và IDs |
| Delete không đi qua $match | Filter chỉ dựa vào fullDocument | Lọc operationType/documentKey, thiết kế riêng cho delete |
| Crash khi xử lý delete | Code truy cập event.fullDocument._id | Dùng event.documentKey._id |
| Update ghi mất field ở sink | Dùng updatedFields làm replacement | Áp patch đúng semantics hoặc lấy snapshot |
| Replace vẫn để lại field đã bị loại | Merge replacement vào object cũ | Thay toàn bộ snapshot ở sink |
| quantity trong updatedFields là 7 thay vì 2 | Event mô tả giá trị mới, không phải operand $inc | Phân biệt delta toán tử với giá trị kết quả |
| updateDescription không chứa field không đổi | Chỉ mô tả thay đổi | Không giả định đây là toàn document |
| fullDocument updateLookup là trạng thái mới hơn | Lookup sau event xảy ra, document đã đổi tiếp | Dùng pre/post-images hoặc logic versioned phù hợp |
| fullDocument updateLookup bằng null | Document đã bị xóa trước lookup hoặc không tìm được | Xử lý null, không coi event tự động không hợp lệ |
| Không nhận pre-image | Chưa bật feature hoặc image không còn | Kiểm tra config/version/retention |
| Cursor lỗi vì sửa _id trong pipeline | Resume token bị thay đổi/loại bỏ | Giữ nguyên event._id trong watch |
| Resume sau restart bỏ sót event | Checkpoint trước khi xử lý | Checkpoint sau xử lý thành công |
| Event bị xử lý hai lần | Crash sau sink success nhưng trước checkpoint | Idempotency/dedup ở sink |
| Token không resume được | Oplog window không còn chứa lịch sử | Rebuild/backfill có kiểm soát |
| start lại stream sau invalidate bị lỗi | Dùng resumeAfter trên invalidate token | Xem startAfter hoặc mở stream mới theo policy |
| Upsert nhưng nhận insert | Upsert đã tạo document mới | Xử lý theo operationType thực tế |
| Lỗi khi dùng clusterTime làm dedup key | Nhiều event có thể chung clusterTime | Dùng resume token và business ID riêng |
| Counter active bị tăng hai lần | Retry event hoặc không biết trạng thái trước | Pre-image/state tracking/idempotent aggregation |
| Không thấy thao tác $set no-op | Không có thay đổi dữ liệu đáng kể | Audit request riêng nếu cần ghi mọi thao tác |
| Consumer chậm rồi mất lịch sử | Oplog retention không đủ | Theo dõi lag, tăng năng lực/rebuild |
| Đánh nhầm drop collection thành delete document | Không phân biệt loại DDL/invalidate | Handler riêng cho drop/rename/invalidate |

## 22. Bài tập thực hành

### Bài 1 — Đọc một event

Cho event có **_id resume token**, **operationType update**, **documentKey._id = X**. Giải thích ba trường và tại sao không được dùng documentKey._id để resume stream.

### Bài 2 — Quan sát bốn operationType

Chạy lab hai terminal ở mục 11. Ghi lại operationType của bốn event, các trường nào xuất hiện ở mỗi event và trạng thái cuối của bốn documents.

### Bài 3 — Update vs replace

Document ban đầu có fields sku, status, quantity, legacy, attributes.size. Nếu updateOne chỉ $set status, những field nào còn? Nếu replaceOne không chứa legacy và attributes.size, những field nào còn? Consumer phải xử lý khác nhau ra sao?

### Bài 4 — Delete không có fullDocument

Viết handler cho delete dùng **documentKey** để xóa cache key. Nếu muốn biết status của document trước delete, đề xuất hai phương án có thể triển khai được.

### Bài 5 — Nested updatedFields

Event updateDescription có updatedFields["attributes.color"] = "navy". Viết thuật toán áp nested path đúng vào JavaScript object, nêu rủi ro khi field names chứa dấu chấm/ký tự đặc biệt và khi thay đổi phần tử Array.

### Bài 6 — $inc

Document quantity=5, API chạy $inc: {quantity:2}. Trong updateDescription có thể là giá trị nào? Vì sao không nên cộng thêm quantity một lần nữa nếu consumer coi updatedFields.quantity là operand?

### Bài 7 — Truncated arrays

Một update làm ngắn Array labels từ 5 phần tử xuống 2. Consumer cần xem trường nào ngoài updatedFields/removedFields trên các version hỗ trợ? Vì sao bỏ qua thông tin Array truncation có thể làm sink giữ dữ liệu dư?

### Bài 8 — UpdateLookup không phải snapshot đúng thời điểm

T1 update quantity 5→7, T2 update 7→9, sau đó consumer xử lý event T1 với fullDocument updateLookup. fullDocument có thể chứa quantity nào và vì sao? Nếu nghiệp vụ đòi trạng thái tại chính T1, nên dùng tính năng nào?

### Bài 9 — Upsert

Chạy updateOne với upsert:true trên _id chưa tồn tại, sau đó chạy một update khác lên cùng _id. Dự đoán operationType của hai event và giải thích vì sao tên API “updateOne” không quyết định event luôn là update.

### Bài 10 — Watch filter

Một consumer watch với $match trên **fullDocument.tenantId = t001**. Hãy chỉ ra ít nhất hai loại event có thể bị mất khi fullDocument không tồn tại. Thiết kế lại dựa vào documentKey, event type hoặc mô hình dữ liệu phù hợp.

### Bài 11 — Resume token

Consumer xử lý E1, E2, E3 rồi mất kết nối sau khi đã lưu token của E2. Khi resumeAfter E2, event nào có thể được xử lý lại? Thiết kế sink idempotent.

### Bài 12 — Thứ tự checkpoint

So sánh “checkpoint trước khi ghi sink” với “ghi sink trước checkpoint”. Với mỗi cách, mô tả trạng thái khi crash ở khoảng giữa. Cách nào phù hợp hơn để tránh mất event và tại sao phải chấp nhận xử lý lặp?

### Bài 13 — Oplog retention

Consumer dừng ba ngày, oplog chỉ còn lịch sử ngắn hơn. ResumeAfter token cũ báo lỗi. Tại sao không được tự xóa checkpoint rồi bắt đầu stream mới mà vẫn gọi read model đồng bộ? Đề xuất bước rebuild/backfill.

### Bài 14 — Invalidate

Collection bị drop trong khi watcher chạy. Có giống một loạt delete events cho từng document không? Cần xử lý drop/invalidate, startAfter/resumeAfter và quy trình tái tạo consumer thế nào?

### Bài 15 — Pre-image và delete

Bật pre/post-images trong một lab cô lập có phiên bản hỗ trợ. Watch với fullDocumentBeforeChange khiAvailable, xóa một document và xem pre-image nếu được lưu. Khi image không có, consumer phải làm gì?

### Bài 16 — Audit và actor

Bạn cần biết “ai thay đổi status từ draft sang paid”. Vì sao updateDescription không mặc định chứa userId/reason? Thiết kế một audit/outbox record nghiệp vụ có requestId, actor, old/new status và retention phù hợp.

### Bài 17 — Materialized count

Một counter activeProductsByTenant nhận insert/update/replace/delete events. Nêu tại sao chỉ nhìn operationType và status sau thay đổi không đủ để tính delta trong mọi trường hợp. Đề xuất state tracking/pre-image hoặc cách reconcile.

### Bài 18 — Concurrent processing

Hai events E1 và E2 của cùng sản phẩm được chuyển cho hai workers song song. Worker xử lý E2 trước E1. Hệ quả với search index là gì? Đề xuất xử lý theo thứ tự của một stream hoặc dùng version/conditional apply để tránh trạng thái cũ ghi đè.

### Bài 19 — Sharded documentKey

Một collection shard theo tenantId/orderNo. Event documentKey có thể chứa những trường nào ngoài _id? Tại sao consumer không nên chỉ dựa vào _id để xác định nguồn nếu namespace và shard key cần thiết cho nghiệp vụ?

### Bài 20 — Phân biệt backfill và stream

Một search index mới bắt đầu bằng việc quét toàn bộ collection rồi mở stream. Trong lúc quét, document X đổi giá. Hãy mô tả race condition, sau đó đề xuất quy trình thiết lập snapshot/boundary và replay để không mất delta.

### Bài 21 — Monitoring

Thiết kế dashboard consumer gồm event lag, checkpoint age, oplog window, resume failures, sink retries, duplicate handling và số event theo operationType. Cảnh báo nào cần ưu tiên để tránh mất khả năng resume?

### Bài 22 — Xử lý event không biết

Ứng dụng nâng phiên bản MongoDB và consumer gặp operationType mới thuộc DDL. Vì sao default branch “xóa index document” là nguy hiểm? Hãy nêu cách log/alert/quarantine mà không âm thầm làm sai dữ liệu.

### Bài 23 — Test end-to-end

Xây dựng kịch bản kiểm tra trên môi trường lab:

1. Seed ba items.
2. Mở watcher.
3. Phát insert/update/replace/delete.
4. Xác nhận event shape.
5. Dừng consumer sau checkpoint event thứ hai.
6. Resume và quan sát các event tiếp theo.
7. Gửi lại một event vào sink idempotent.
8. Kiểm tra dữ liệu sink khớp trạng thái nguồn.

Nêu rõ bạn sẽ đo **đúng loại event** và **không mất/nhân bản tác động**, chứ không chỉ đếm đủ bốn dòng log.

## 23. Tài liệu tham khảo chính thức

- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- MongoDB Manual — [Change Events](https://www.mongodb.com/docs/manual/reference/change-events/).
- MongoDB Manual — [$changeStream](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/).
- MongoDB Manual — [Change Streams Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/).
- MongoDB Manual — [Change Streams with Document Pre- and Post-Images](https://www.mongodb.com/docs/manual/changestreams/#change-streams-with-document-pre--and-post-images).
- MongoDB Manual — [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Node.js Driver — [Monitor Data with Change Streams](https://www.mongodb.com/docs/drivers/node/current/monitoring-and-logging/change-streams/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).

**Kết luận:** Change Stream là luồng các **sự kiện thay đổi**, không phải danh sách document hiện có và không phải audit log lưu vô hạn. Mỗi event có **resume token ở _id**, **operationType**, **namespace**, **documentKey** và những field tùy thuộc loại thao tác. **Insert** thường mang document mới ở **fullDocument**; **update** dùng **updateDescription** mô tả thay đổi, không mặc định chứa toàn document; **replace** đưa replacement document mà không có delta field-level như update; **delete** chủ yếu dùng documentKey vì document đã biến mất. Consumer vững chắc cần **switch đúng operationType, không làm mất resume token, checkpoint sau khi xử lý thành công, idempotency và kế hoạch rebuild khi oplog không còn lịch sử**. Khi cần trạng thái trước/sau chính xác, hãy hiểu rõ **updateLookup khác pre/post-images** và lựa chọn theo hợp đồng nghiệp vụ.
