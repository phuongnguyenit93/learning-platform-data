# Đọc metadata, thống kê dung lượng và thông tin collection trong MongoDB

## 1. Mục tiêu bài học và bối cảnh

Khi làm việc với MongoDB, đọc dữ liệu bằng `find()` chỉ cho biết nội dung document. Để quản trị database và tối ưu ứng dụng, chúng ta còn cần trả lời những câu hỏi như:

- Server đang có những database nào và tài khoản hiện tại nhìn thấy database nào?
- Một database chứa những collection, view hoặc cấu trúc đặc biệt nào?
- Collection được tạo với tùy chọn gì: validator, collation, capped collection hay time series?
- Collection đang có bao nhiêu document, kích thước dữ liệu logic, vùng lưu trữ vật lý và index là bao nhiêu?
- Một index có những trường nào, có ràng buộc unique hay TTL không, và đang chiếm bao nhiêu dung lượng?
- Vì sao xóa nhiều document nhưng dung lượng trên đĩa chưa giảm tương ứng?

Trong chương **Database và collection** của **Database Engine Document MongoDB**, bài này tập trung vào cách **đọc metadata và thống kê** bằng `mongosh`, sau đó quan sát thông tin tương ứng trong MongoDB Compass. Các thao tác chính là đọc; phần đầu có một bộ dữ liệu nhỏ để tự thực hành.

> **Phân biệt quan trọng:** Metadata nói về cấu trúc và cấu hình; thống kê mô tả số lượng và tài nguyên; tài liệu ứng dụng là nội dung của từng document. Ba nhóm thông tin này phục vụ các mục đích khác nhau.

Sau bài học, bạn có thể kiểm tra một database/collection mà không cần mở từng document, diễn giải các đơn vị dung lượng, so sánh thống kê ở nhiều thời điểm và tránh những kết luận sai thường gặp.

## 2. Metadata là gì trong MongoDB?

**Metadata** là thông tin mô tả đối tượng được MongoDB quản lý. Nó có thể gồm:

| Cấp độ | Ví dụ thông tin | Cách tra cứu |
|---|---|---|
| Database | Tên database, số collection, số object, dung lượng dữ liệu và index | `show dbs`, `listDatabases`, `dbStats` |
| Collection | Tên, loại đối tượng, tùy chọn tạo, validator, collation, UUID nội bộ, định nghĩa time series hoặc capped | `listCollections`, `db.getCollectionInfos()` |
| Index | Tên index, khóa và chiều sắp xếp, unique, TTL, partial filter, collation | `db.collection.getIndexes()` |
| Thống kê collection | Document count, logical size, allocated storage, index sizes, dung lượng từng index | `$collStats` hoặc lệnh `collStats` |
| Thống kê truy cập index | Các lượt truy cập index được thống kê từ lúc thu thập bắt đầu | `$indexStats` |

Một số thuật ngữ:

- **Database:** vùng chứa collection và các đối tượng liên quan.
- **Collection:** tập document BSON, có thể chứa các document với cấu trúc khác nhau.
- **View:** truy vấn đọc được định nghĩa trên collection/view khác; thông thường không có vùng lưu trữ document riêng như collection thực.
- **Index:** cấu trúc dữ liệu giúp truy vấn tìm kiếm/sắp xếp hiệu quả hơn; có vùng lưu trữ và chi phí ghi bổ sung.
- **Namespace:** tên đầy đủ dạng `database.collection`, chẳng hạn `metadata_lab.demoOrders`.
- **Collection UUID:** định danh nội bộ của collection, có thể xuất hiện trong metadata; không nên dùng làm khóa nghiệp vụ ổn định sau khi drop/recreate.

MongoDB không giống cơ sở dữ liệu quan hệ ở chỗ không bắt buộc mọi document cùng collection có schema giống nhau. Tuy vậy, collection vẫn có **metadata riêng** và có thể áp dụng **validator** để kiểm soát dữ liệu khi ghi.

### 2.1. Metadata không phải thống kê

Ví dụ:

~~~javascript
db.getCollectionInfos({ name: "demoOrders" })
~~~

Lệnh trên trả về mô tả collection, như `name`, `type`, `options` và một số trường `info`. Nó **không phải** lệnh đo dung lượng.

Ngược lại:

~~~javascript
db.runCommand({ collStats: "demoOrders", scale: 1024 })
~~~

Lệnh này trả về thống kê của collection, gồm các trường như `count`, `size`, `storageSize` và `totalIndexSize` khi server hỗ trợ. Nó **không thay thế** danh sách tùy chọn tạo collection.

Còn:

~~~javascript
db.demoOrders.findOne()
~~~

Lệnh này trả về một document ứng dụng, không thể dùng để suy luận toàn bộ cấu hình hay dung lượng collection.

### 2.2. Tại sao phải quan tâm quyền truy cập?

MongoDB sử dụng cơ chế phân quyền. Người dùng có thể chỉ được xem một database hoặc một số collection. Kết quả liệt kê đối tượng phụ thuộc **quyền của tài khoản hiện tại**, vì vậy “không thấy trong danh sách” không luôn có nghĩa đối tượng không tồn tại.

Các lệnh thu thập số liệu ở phạm vi toàn server hoặc theo dõi vận hành có thể yêu cầu quyền riêng. Với tài khoản thực hành, chỉ cần quyền thích hợp để đọc database và collection đang học. Nếu gặp lỗi `not authorized`, hãy xác minh role với người quản trị thay vì thử đoán thông tin đăng nhập hoặc tự cấp quyền.

## 3. Chuẩn bị dữ liệu thực hành

Bài học sử dụng database `metadata_lab` và collection `demoOrders`. Mở `mongosh` kết nối tới một MongoDB Server local hoặc môi trường thực hành mà bạn được cấp quyền, rồi thực hiện trong shell:

~~~javascript
use metadata_lab

const sampleOrders = [
  {
    _id: "order-001",
    customer: "Lan",
    status: "PAID",
    amount: NumberDecimal("120.50"),
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    items: [{ sku: "BK-001", quantity: 2 }]
  },
  {
    _id: "order-002",
    customer: "Minh",
    status: "PENDING",
    amount: NumberDecimal("75.00"),
    createdAt: ISODate("2026-11-02T09:30:00Z"),
    items: [{ sku: "BK-002", quantity: 1 }]
  },
  {
    _id: "order-003",
    customer: "An",
    status: "PAID",
    amount: NumberDecimal("230.00"),
    createdAt: ISODate("2026-11-03T12:10:00Z"),
    items: [{ sku: "BK-003", quantity: 4 }]
  },
  {
    _id: "order-004",
    customer: "Hà",
    status: "CANCELLED",
    amount: NumberDecimal("42.25"),
    createdAt: ISODate("2026-11-04T07:15:00Z"),
    items: [{ sku: "BK-004", quantity: 1 }]
  },
  {
    _id: "order-005",
    customer: "Linh",
    status: "PENDING",
    amount: NumberDecimal("99.99"),
    createdAt: ISODate("2026-11-05T18:20:00Z"),
    items: [{ sku: "BK-005", quantity: 3 }]
  }
];

sampleOrders.forEach(order => {
  db.demoOrders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.demoOrders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_createdAt" }
);

db.demoOrders.countDocuments({});
~~~

Nếu ban đầu `metadata_lab` chưa có dữ liệu, kết quả đếm dự kiến là **5 document**. Nếu database từng có dữ liệu khác, tổng số có thể lớn hơn. Các lệnh `replaceOne(..., { upsert: true })` giúp tránh tạo bản ghi trùng `_id`, nhưng **sẽ đặt lại nội dung năm document mẫu** khi chạy lại.

Collection `demoOrders` có index mặc định trên `_id` và một index ghép trên `status`, `createdAt`. Lệnh `createIndex` khi chạy lại với cùng định nghĩa và tên thông thường không tạo thêm index trùng.

Để có thêm ví dụ về cấu hình collection, có thể tạo một collection có validator; đoạn mã chỉ tạo nếu chưa tồn tại:

~~~javascript
if (db.getCollectionInfos({ name: "validatedOrders" }).length === 0) {
  db.createCollection("validatedOrders", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["orderCode", "status"],
        properties: {
          orderCode: { bsonType: "string" },
          status: { bsonType: "string" }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}
~~~

Bài này không cần chèn document vào `validatedOrders`; mục đích là đọc metadata về validator.

## 4. Liệt kê và nhận diện database

### 4.1. Các lệnh nhanh trong mongosh

~~~javascript
show dbs
db.getName()
~~~

- `show dbs` liệt kê database mà tài khoản nhìn thấy; cách hiển thị có thể kèm ước lượng dung lượng.
- `db.getName()` cho biết database hiện đang được chọn, chẳng hạn `metadata_lab`.

Chuyển ngữ cảnh:

~~~javascript
use metadata_lab
db.getName()
~~~

Lệnh `use` không tự tạo database trên server. Database mới có thể chỉ xuất hiện trong danh sách sau khi có collection hoặc dữ liệu được tạo.

### 4.2. Dùng lệnh `listDatabases`

Có thể gọi trực tiếp lệnh quản trị:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  authorizedDatabases: true
});
~~~

Các tùy chọn trong ví dụ:

- `listDatabases: 1` yêu cầu liệt kê database.
- `nameOnly: true` ưu tiên danh sách tên và bỏ một số thống kê dung lượng.
- `authorizedDatabases: true` yêu cầu kết quả phù hợp các database mà tài khoản có quyền thấy theo cơ chế phân quyền.

Muốn xem thêm thống kê từ lệnh liệt kê, bỏ `nameOnly`:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  authorizedDatabases: true
});
~~~

Phản hồi thường có mảng `databases` chứa `name` và có thể có `sizeOnDisk`, `empty` tùy quyền, tùy chọn và phiên bản server. Các con số là trạng thái tại thời điểm lệnh chạy; đừng dùng chúng làm báo cáo dung lượng chính xác tuyệt đối của toàn bộ hạ tầng.

**Phạm vi kết quả:** Trên môi trường được quản lý như MongoDB Atlas, một số thao tác quản trị bị giới hạn. Nếu `listDatabases` báo thiếu quyền, bạn vẫn có thể kiểm tra database được cấp quyền thông qua `db.getName()` và lệnh xem collection.

### 4.3. Tránh nhầm tên database với namespace

Ví dụ:

~~~text
Database: metadata_lab
Collection: demoOrders
Namespace: metadata_lab.demoOrders
~~~

`metadata_lab.demoOrders` là tên namespace đầy đủ; dấu chấm trong ví dụ ngăn cách database và collection. Khi ứng dụng tạo nhiều collection cùng tên ở các database khác nhau, chỉ dùng tên `demoOrders` có thể gây nhầm lẫn trong log hoặc script giám sát.

## 5. Đọc danh sách collection và view

### 5.1. Lệnh liệt kê đơn giản

~~~javascript
use metadata_lab

show collections
db.getCollectionNames()
~~~

`show collections` thuận tiện cho thao tác tương tác, còn `db.getCollectionNames()` trả về một mảng JavaScript để bạn có thể lọc, in hoặc xử lý. Tùy hệ thống, danh sách có thể có cả **view** bên cạnh collection thông thường.

Ví dụ lọc các tên bắt đầu bằng `demo`:

~~~javascript
db.getCollectionNames().filter(name => name.startsWith("demo"));
~~~

Khi chỉ biết tên, chưa thể khẳng định đối tượng đó là collection vật lý hay view; cần xem metadata `type`.

### 5.2. Lấy metadata bằng `db.getCollectionInfos()`

~~~javascript
db.getCollectionInfos()
~~~

Kết quả là một mảng object. Một phần metadata có thể trông như sau (các trường hiển thị thực tế phụ thuộc loại collection và phiên bản MongoDB):

~~~javascript
[
  {
    name: "demoOrders",
    type: "collection",
    options: {},
    info: { /* thông tin nội bộ */ },
    idIndex: { /* định nghĩa _id index */ }
  },
  {
    name: "validatedOrders",
    type: "collection",
    options: {
      validator: { /* JSON Schema */ },
      validationLevel: "strict",
      validationAction: "error"
    }
  }
]
~~~

Lọc đúng collection:

~~~javascript
db.getCollectionInfos({ name: "demoOrders" });
db.getCollectionInfos({ name: "validatedOrders" });
~~~

Lấy riêng tùy chọn tạo:

~~~javascript
const infos = db.getCollectionInfos({ name: "validatedOrders" });
printjson(infos.length > 0 ? infos[0].options : null);
~~~

Các thông tin hữu ích trong `options` có thể gồm:

| Tùy chọn | Ý nghĩa |
|---|---|
| `validator` | Điều kiện kiểm tra document khi ghi, thường gồm `$jsonSchema` |
| `validationLevel` | Phạm vi áp dụng validator, ví dụ `strict` hoặc `moderate` |
| `validationAction` | Hành động khi vi phạm; ví dụ `error` hoặc chế độ cảnh báo nếu được cấu hình |
| `collation` | Quy tắc so sánh chuỗi, ngôn ngữ và cách sắp xếp |
| `capped`, `size`, `max` | Chỉ ra cấu hình collection có giới hạn dung lượng/số document nếu sử dụng capped collection |
| `timeseries` | Cấu hình time series collection, như trường thời gian và trường metadata |
| `changeStreamPreAndPostImages` | Thiết lập lưu ảnh trước/sau cập nhật khi cấu hình và phiên bản hỗ trợ |

Không phải mọi trường đều tồn tại trên mọi collection. Với collection thông thường tạo mặc định, `options` có thể chỉ là object rỗng.

### 5.3. Lệnh `listCollections` cấp database

Tương đương ở mức command:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: { name: "demoOrders" },
  nameOnly: false
});
~~~

Phản hồi có thể chứa `cursor.firstBatch` và metadata tương tự `getCollectionInfos()`. Với nhiều collection, command sử dụng **cursor**; `firstBatch` không nhất thiết là toàn bộ dữ liệu. Trong thực hành, dùng `db.getCollectionInfos()` thường thuận tiện hơn vì helper xử lý việc liệt kê.

Muốn liệt kê theo loại đối tượng:

~~~javascript
db.getCollectionInfos({ type: "collection" });
db.getCollectionInfos({ type: "view" });
~~~

Nếu cần xem riêng tên và loại mà không in quá nhiều metadata:

~~~javascript
db.getCollectionInfos().map(info => ({
  name: info.name,
  type: info.type
}));
~~~

### 5.4. Phân biệt collection với view

Thử tạo một view, nếu chưa tồn tại và tài khoản có quyền:

~~~javascript
if (db.getCollectionInfos({ name: "paidOrdersView" }).length === 0) {
  db.createView("paidOrdersView", "demoOrders", [
    { $match: { status: "PAID" } }
  ]);
}

db.getCollectionInfos({ name: "paidOrdersView" });
db.paidOrdersView.find();
~~~

Metadata của view thường có `type: "view"` cùng thông tin `viewOn` và `pipeline` trong `options`. View cung cấp kết quả truy vấn dựa trên dữ liệu nguồn; nó không được tính như một collection vật lý độc lập có tập document lưu riêng.

**Lưu ý:** Không gọi `collStats` để suy luận dung lượng lưu riêng của view như một collection. Với nhu cầu đo dung lượng, hãy xác định collection vật lý phía sau view.

## 6. Đọc thống kê ở cấp database với `dbStats`

### 6.1. Lệnh thống kê

Trong `mongosh`:

~~~javascript
use metadata_lab

db.runCommand({ dbStats: 1 });
~~~

Có thể yêu cầu các giá trị dung lượng theo đơn vị KiB bằng hệ số `1024`:

~~~javascript
db.runCommand({
  dbStats: 1,
  scale: 1024
});
~~~

Cách viết `db.stats()` cũng thường thấy trong tài liệu/thao tác shell:

~~~javascript
db.stats();
~~~

Các lệnh thuộc nhóm thống kê database. Khi cần kiểm soát tường minh hệ số scale hoặc truyền đúng command server, dùng `db.runCommand({ dbStats: 1, scale: 1024 })`.

### 6.2. Diễn giải các trường trả về

Tùy phiên bản và storage engine, phản hồi có thể bao gồm:

| Trường | Ý nghĩa thường dùng | Điểm cần nhớ |
|---|---|---|
| `db` | Tên database được thống kê | Xác nhận không đọc nhầm database |
| `collections` | Số lượng collection vật lý | Không đồng nghĩa số view |
| `views` | Số lượng view nếu được báo cáo | View không tự mang dữ liệu lưu trữ như collection |
| `objects` | Tổng số document trong các collection | Có thể khác số liệu ở thời điểm khác khi đang có ghi/xóa |
| `avgObjSize` | Kích thước trung bình của document | Ý nghĩa và cách scale cần đối chiếu đầu ra thực tế |
| `dataSize` | Dung lượng logic của dữ liệu | Không phải toàn bộ số byte file MongoDB dùng trên đĩa |
| `storageSize` | Dung lượng vùng lưu trữ cho dữ liệu collection | Có thể chịu ảnh hưởng nén, cấp phát và phân mảnh |
| `indexes` | Tổng số index | Mỗi collection thông thường có `_id` index mặc định |
| `indexSize` | Dung lượng lưu trữ index | Khác số lượng index |
| `totalSize` | Tổng phần lưu trữ dữ liệu và index theo định nghĩa command | Không phải toàn bộ dung lượng ổ đĩa của máy chủ |
| `scaleFactor` | Hệ số scale đang áp dụng nếu trả về | Dùng khi giải thích đơn vị |
| `fsUsedSize`, `fsTotalSize` | Thông tin hệ thống file nếu được cung cấp | Không đồng nghĩa dung lượng dữ liệu MongoDB riêng database |

**Một quy ước hữu ích:** Khi `scale: 1024`, các **trường dung lượng được command scale hỗ trợ** thường có giá trị theo **KiB (1024 byte)**. Khi `scale: 1048576`, các trường đó theo **MiB**. Những trường đếm như `collections`, `objects`, `indexes` không biến thành KiB; vì vậy không được coi mọi con số trong cùng response đều dùng một đơn vị.

Ví dụ giả định:

~~~text
dataSize: 2048
storageSize: 1536
indexSize: 512
scaleFactor: 1024
~~~

Khi đó có thể đọc là dữ liệu logic khoảng 2048 KiB, vùng lưu trữ dữ liệu 1536 KiB và index 512 KiB theo cách command báo cáo. Các con số này **chỉ để minh họa**, không phải kết quả sẽ thấy ở database thực hành.

### 6.3. Logical size khác physical storage

MongoDB lưu BSON và có thể dùng bộ máy lưu trữ WiredTiger với cơ chế nén, cấp phát, tái sử dụng vùng trống. Vì thế:

- `dataSize`/`size` thể hiện **kích thước logic** của document ở phạm vi thống kê.
- `storageSize` thể hiện kích thước **vùng lưu trữ được cấp phát/ghi nhận** cho dữ liệu collection; có thể thấp hơn hoặc cao hơn logical size tùy dữ liệu và overhead.
- `indexSize`/`totalIndexSize` phản ánh phần lưu trữ dành cho index, cần tính riêng.
- Các file dữ liệu, journal, oplog, metadata máy chủ, bản sao replica set và phần khác trên ổ đĩa **không thể suy ra đầy đủ chỉ từ `dbStats`**.

Không tính “tỷ lệ nén chính xác của toàn cluster” đơn giản bằng cách chia `dataSize / storageSize` trong mọi tình huống. Cần xem mục đích đo, bộ máy lưu trữ, mô hình replica/sharding và thời điểm thu thập.

## 7. Thống kê một collection với `collStats`

### 7.1. Đọc trực tiếp bằng database command

~~~javascript
use metadata_lab

db.runCommand({
  collStats: "demoOrders",
  scale: 1024
});
~~~

Collection `demoOrders` phải tồn tại ở database hiện hành. Kết quả thành công thường có `ok: 1`. Tên đầy đủ có thể hiển thị ở trường `ns`, ví dụ `metadata_lab.demoOrders`.

Các trường thường gặp:

| Trường | Mô tả | Cách sử dụng |
|---|---|---|
| `ns` | Namespace của collection | Xác minh đúng database/collection |
| `count` | Số document được thống kê | Không tự xem là snapshot giao dịch hoàn toàn đồng nhất với mọi lệnh khác |
| `size` | Kích thước dữ liệu logic của document | Ước tính quy mô nội dung thực |
| `avgObjSize` | Kích thước trung bình document | Quan sát xu hướng tăng do thêm trường/mảng |
| `storageSize` | Kích thước vùng lưu trữ dữ liệu | Theo dõi chi phí cấp phát/nén |
| `nindexes` | Số index | So sánh với danh sách định nghĩa index |
| `totalIndexSize` | Tổng dung lượng lưu trữ index | Xem mức tăng khi thêm index |
| `indexSizes` | Dung lượng của từng index theo tên | Xác định index chiếm nhiều tài nguyên |
| `totalSize` | Tổng dung lượng thống kê dữ liệu và index | Cần phân biệt với disk usage của toàn server |
| `wiredTiger` | Chi tiết nội bộ của storage engine nếu có | Có thể khác lớn giữa các phiên bản và cách triển khai |

Tham khảo một ví dụ in gọn:

~~~javascript
{
  const stats = db.runCommand({
    collStats: "demoOrders",
    scale: 1024
  });

  if (stats.ok !== 1) {
    printjson(stats);
  } else {
    printjson({
      namespace: stats.ns,
      documentCount: stats.count,
      logicalSizeKiB: stats.size,
      storageSizeKiB: stats.storageSize,
      indexCount: stats.nindexes,
      totalIndexKiB: stats.totalIndexSize,
      indexSizesKiB: stats.indexSizes
    });
  }
}
~~~

Đây là **lệnh chỉ đọc**. Kết quả bằng `0` hoặc rất nhỏ khi mới có 5 document không chứng minh collection không dùng tài nguyên. Các vùng cấp phát, metadata, cách làm tròn số và quy mô mẫu đều tác động tới giá trị hiển thị.

### 7.2. Dùng aggregation stage `$collStats`

MongoDB còn cung cấp stage `$collStats` để đưa thông tin collection vào aggregation pipeline. Ví dụ yêu cầu thống kê số document và dung lượng lưu trữ theo KiB:

~~~javascript
db.demoOrders.aggregate([
  {
    $collStats: {
      count: {},
      storageStats: { scale: 1024 }
    }
  },
  {
    $project: {
      _id: 0,
      ns: 1,
      host: 1,
      shard: 1,
      count: 1,
      logicalSizeKiB: "$storageStats.size",
      storageSizeKiB: "$storageStats.storageSize",
      indexesKiB: "$storageStats.totalIndexSize"
    }
  }
]);
~~~

`$collStats` cần được đặt ở **đầu pipeline**. Trong cluster phân mảnh, số document kết quả và phạm vi mỗi document thống kê có thể khác triển khai server đơn; không mặc định chỉ có đúng một bản ghi hoặc cộng trực tiếp tất cả các số như thể chúng được đo trên một node.

Khi dùng API driver Java hoặc một hệ thống giám sát muốn xử lý kết quả bằng pipeline, `$collStats` thường linh hoạt hơn so với việc chỉ in nguyên response của command.

### 7.3. Những trường hợp đặc biệt

- **Collection rỗng:** `count` có thể là `0` trong khi index metadata hoặc vùng cấp phát vẫn tồn tại.
- **Collection nhiều lần ghi/xóa:** `storageSize` không nhất thiết giảm tỷ lệ với số document giảm vì vùng trống có thể được tái sử dụng.
- **Collection bị nén:** logical `size` có thể lớn hơn `storageSize`; với mẫu quá nhỏ, overhead cũng có thể làm điều ngược lại.
- **View:** hãy đọc metadata `type` và xác định collection nguồn; không so sánh trực tiếp view với collection vật lý.
- **Time series:** MongoDB sử dụng cơ chế bucket lưu trữ phía dưới; thống kê logic và vật lý có thể yêu cầu cách diễn giải khác collection thông thường.
- **Sharded collection:** kiểm tra scope của phản hồi, số liệu từ router và các shard; không cộng nhầm các bản sao replica set thành logical size.
- **Managed service:** trường thống kê hoặc quyền chạy command có thể bị giới hạn; khi thiếu quyền cần báo cho người quản trị.

## 8. Đọc định nghĩa index và dung lượng index

### 8.1. Xem index hiện có

~~~javascript
db.demoOrders.getIndexes();
~~~

Với bộ dữ liệu ở mục 3, bạn sẽ thấy ít nhất:

~~~javascript
[
  {
    name: "_id_",
    key: { _id: 1 }
  },
  {
    name: "idx_status_createdAt",
    key: { status: 1, createdAt: -1 }
  }
]
~~~

Ví dụ trên chỉ giữ hai trường để dễ đọc. Đầu ra thực có thể có các trường như `v`, `unique`, `expireAfterSeconds`, `partialFilterExpression`, `collation`, `hidden`.

Ý nghĩa của một số metadata:

| Trường | Ý nghĩa |
|---|---|
| `name` | Tên index được dùng khi quản trị hoặc theo dõi |
| `key` | Các trường được index và chiều sắp xếp `1` / `-1` |
| `unique` | Ràng buộc không cho các khóa index trùng theo quy tắc index |
| `sparse` | Chỉ index một tập document theo quy tắc sparse |
| `partialFilterExpression` | Chỉ index document khớp điều kiện lọc |
| `expireAfterSeconds` | Thiết lập TTL, cho phép cơ chế xóa document hết hạn theo điều kiện |
| `collation` | Quy tắc so sánh chuỗi của index |
| `hidden` | Index bị ẩn với query planner trong cấu hình hỗ trợ |

**Đọc index definition không cho biết index đó có được sử dụng thường xuyên hay không.** Nó cũng không trực tiếp cho biết index chiếm bao nhiêu byte; hai câu hỏi này cần công cụ thống kê khác.

### 8.2. Thống kê dung lượng từng index

~~~javascript
{
  const info = db.runCommand({
    collStats: "demoOrders",
    scale: 1024
  });

  printjson(info.indexSizes);
  print("Total index size (KiB): " + info.totalIndexSize);
}
~~~

`indexSizes` thường là object ánh xạ tên index sang dung lượng, ví dụ `_id_` và `idx_status_createdAt`. Đây là dung lượng do storage engine báo cáo; không phải số lượng document được index hay số truy vấn sử dụng index.

Với một collection nhỏ, index có thể có chi phí tối thiểu tương đối lớn so với kích thước dữ liệu. Với collection lớn, hãy xem dung lượng index cùng với tác dụng đối với truy vấn và chi phí ghi.

### 8.3. Thống kê truy cập bằng `$indexStats`

~~~javascript
db.demoOrders.aggregate([
  { $indexStats: {} }
]);
~~~

Kết quả có thể chứa thông tin tên index, key, host và `accesses.ops`/`accesses.since` theo khả năng phiên bản MongoDB. Điều này giúp nhận diện index có hoặc chưa có lượt truy cập được ghi nhận trong khoảng thời gian theo dõi.

**Không kết luận index “thừa” chỉ vì `accesses.ops = 0`.** Thống kê có thể reset khi server khởi động lại, index được tạo lại hoặc sự kiện vận hành khác; một số luồng truy vấn ít xảy ra nhưng rất quan trọng. Index còn có thể tồn tại vì ràng buộc unique hoặc hỗ trợ một tình huống nghiệp vụ theo chu kỳ.

Ngoài `$indexStats`, nên kết hợp truy vấn mẫu với `explain("executionStats")`:

~~~javascript
db.demoOrders
  .find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Nhận diện `IXSCAN` hay `COLLSCAN` giúp hiểu kế hoạch truy vấn. Dữ liệu mẫu chỉ có 5 document nên query planner có thể chọn collection scan; đó không phải bằng chứng chắc chắn index bị sai.

## 9. Đếm document: chính xác và ước lượng

Một collection có thể được đếm theo nhiều cách:

~~~javascript
db.demoOrders.countDocuments({});
db.demoOrders.estimatedDocumentCount();
~~~

| Cách | Đặc điểm | Nên dùng khi |
|---|---|---|
| `countDocuments({})` | Đếm document khớp filter; dùng khi cần kết quả đếm theo điều kiện | Giao diện phân trang, kiểm tra số lượng bản ghi nghiệp vụ |
| `estimatedDocumentCount()` | Dựa trên metadata/thống kê lưu trữ để ước lượng tổng số document | Dashboard hoặc giám sát cần kết quả nhanh ở quy mô lớn |
| `collStats.count` | Con số trong bản thống kê của collection | Theo dõi tài nguyên và tình trạng collection |
| `dbStats.objects` | Tổng số object/document toàn database theo thống kê | Quan sát quy mô database, không thay thế đếm riêng từng collection |

Ví dụ đếm theo trạng thái:

~~~javascript
db.demoOrders.countDocuments({ status: "PAID" });
~~~

Với năm document mẫu, kết quả là `2`. `estimatedDocumentCount()` không nhận filter để đếm riêng `status: "PAID"`.

Ngay cả khi dùng lệnh đếm chính xác, dữ liệu có thể thay đổi giữa lúc bạn chạy `countDocuments` và lúc đọc `collStats` nếu ứng dụng đang ghi đồng thời. Muốn đối soát nghiêm ngặt cần thiết kế consistency/snapshot phù hợp, không giả định hai lệnh chạy khác thời điểm phải cho kết quả giống nhau từng đơn vị.

## 10. Kiểm tra metadata và dung lượng bằng MongoDB Compass

MongoDB Compass là client đồ họa. Giao diện có thể khác theo phiên bản và cấu hình MongoDB Server/Atlas, nhưng cách quan sát cơ bản như sau:

1. Mở Compass, kết nối tới MongoDB Server đã dùng trong `mongosh`.
2. Chọn database `metadata_lab` ở thanh điều hướng.
3. Xem danh sách collection, xác nhận `demoOrders` và `validatedOrders` (nếu đã tạo).
4. Mở `demoOrders`; các tab như **Documents**, **Aggregations**, **Schema** và **Indexes** giúp xem dữ liệu và index.
5. Vào **Indexes** để đối chiếu `_id_` và `idx_status_createdAt` với `db.demoOrders.getIndexes()`.
6. Nếu phiên bản Compass cung cấp thống kê count, size, average document size hoặc index size trong phần **Collections/Collection Overview**, hãy kiểm tra đơn vị và thời điểm số liệu được cập nhật.
7. Mở `validatedOrders` để khảo sát cấu hình/validation nếu UI phiên bản đó hỗ trợ hiển thị. Khi cần thông tin chính xác về `validator`, sử dụng `db.getCollectionInfos({name:"validatedOrders"})` trong mongosh.

Compass có thể chỉ trình bày một phần metadata; các số liệu dung lượng không nhất thiết xuất hiện ở cùng vị trí trên mọi phiên bản. Khi muốn đo theo một `scale` nhất quán hoặc lưu kết quả cho báo cáo, lệnh mongosh là lựa chọn rõ ràng hơn.

### 10.1. Phân biệt các màn hình trong Compass

| Khu vực thường gặp | Trả lời câu hỏi | Không nên suy luận |
|---|---|---|
| **Documents** | Document đang có những trường và giá trị nào? | Không suy ra kích thước vật lý toàn collection từ vài document |
| **Schema** | Các trường/kiểu dữ liệu phân bố thế nào trong mẫu được phân tích? | Không mặc định mẫu là toàn bộ collection |
| **Indexes** | Index nào tồn tại, định nghĩa ra sao? | Không khẳng định index có lợi cho mọi truy vấn |
| **Aggregations** | Pipeline trả kết quả nào, biến đổi dữ liệu ra sao? | Không đồng nghĩa với metadata/storage stats |
| **Collection overview/metrics**, nếu có | Count/dung lượng ở thời điểm được thu thập | Không mặc định metric thời gian thực hoặc cùng đơn vị với mongosh |

Một ứng dụng Compass và một phiên mongosh chỉ nhìn thấy cùng dữ liệu nếu chúng thực sự kết nối đến **cùng host/cluster, database và collection**. Nếu con số khác nhau, hãy kiểm tra cấu hình kết nối, quyền, bộ lọc đang áp dụng và thời điểm làm mới dữ liệu trước.

## 11. Theo dõi dung lượng theo thời gian

Một số số đo chỉ có ý nghĩa khi đặt cạnh nhau ở các thời điểm được định nghĩa rõ:

- Số document tăng từ bao nhiêu lên bao nhiêu?
- Logical data size thay đổi bao nhiêu MiB trong một ngày?
- Index size tăng vì thêm index hay vì số document tăng?
- Storage size không giảm dù ứng dụng đã xóa dữ liệu: có thể do vùng trống đã được cấp phát vẫn dùng để tái sử dụng?
- Bản thống kê lấy trên primary, secondary, router hay cluster quản lý? Có thể so sánh cùng phạm vi hay không?

### 11.1. In snapshot thống kê đơn giản

Trong `mongosh`, có thể chạy đoạn chỉ đọc để thu một snapshot:

~~~javascript
{
  const snapshotTime = new Date();
  const databaseStats = db.runCommand({
    dbStats: 1,
    scale: 1048576
  });
  const collectionStats = db.runCommand({
    collStats: "demoOrders",
    scale: 1048576
  });

  printjson({
    collectedAt: snapshotTime,
    database: db.getName(),
    namespace: collectionStats.ns,
    dbCollections: databaseStats.collections,
    dbObjects: databaseStats.objects,
    dbLogicalMiB: databaseStats.dataSize,
    dbStorageMiB: databaseStats.storageSize,
    dbIndexMiB: databaseStats.indexSize,
    collectionCount: collectionStats.count,
    collectionLogicalMiB: collectionStats.size,
    collectionStorageMiB: collectionStats.storageSize,
    collectionIndexMiB: collectionStats.totalIndexSize
  });
}
~~~

Đoạn mã này chỉ **in kết quả**, không tự lưu vào một collection hoặc file. Với dữ liệu thực hành rất nhỏ, giá trị theo MiB có thể là số thập phân rất nhỏ hoặc hiển thị `0` tùy cách server tính và định dạng.

Nếu dùng snapshot cho báo cáo vận hành:

1. Giữ nguyên hệ số `scale` và tên metric giữa các lần lấy số liệu.
2. Ghi thời điểm, server/cluster, database, collection, phiên bản nếu cần.
3. Ghi nhận những sự kiện ảnh hưởng đến số liệu như tạo/drop index, migration, compaction hoặc thay đổi sharding.
4. Tránh cộng cùng một dữ liệu giữa các bản sao replica set.
5. Giải thích rõ giới hạn: thống kê metadata/storage không phải công cụ đo toàn bộ dung lượng ổ đĩa hay backup size.

### 11.2. Tính toán dung lượng theo tỷ lệ

Giả sử collection báo cáo:

~~~text
logical data size: 100 MiB
allocated data storage: 65 MiB
index storage: 20 MiB
~~~

Có thể ghi nhận tổng phần **allocated data storage + index storage** được thống kê là khoảng `85 MiB`. Không nên gọi đây là kích thước file backup hoặc lượng ổ đĩa trống sẽ tăng thêm `85 MiB` nếu drop collection. Các thành phần khác của storage engine và hạ tầng vẫn tồn tại.

Nếu muốn tính tỷ lệ:

\[
\text{index-to-data-storage ratio}
= \frac{\text{totalIndexSize}}{\text{storageSize}}
\]

Ví dụ trên bằng `20 / 65 ≈ 0.308`, tức khoảng **30,8%**. Chỉ so sánh tỷ lệ qua các snapshot cùng đơn vị, cùng phạm vi và cách thu thập.

## 12. Vì sao xóa document nhưng dung lượng đĩa không giảm ngay?

Thử nghiệm xóa một document trong database học tập:

~~~javascript
db.demoOrders.deleteOne({ _id: "order-005" });

db.demoOrders.countDocuments({});

db.runCommand({
  collStats: "demoOrders",
  scale: 1024
});
~~~

Số document giảm một, nhưng `storageSize` hoặc dung lượng file hệ thống có thể không giảm như mong đợi. Nguyên nhân phổ biến:

- MongoDB có thể giữ không gian đã cấp phát để tái sử dụng cho các lần ghi sau.
- Storage engine tổ chức dữ liệu theo trang và nén; kích thước cấp phát không thay đổi tuyến tính theo một document.
- Index cũng có không gian cấp phát riêng và không nhất thiết co lại tức thì.
- Dung lượng đĩa thực tế còn bị ảnh hưởng bởi journal, oplog, replica set, backup hoặc các thành phần của dịch vụ quản lý.

Vì thế:

~~~text
Xóa 1.000 document
    ↓
Số document / logical data size thường giảm
    ↓
Allocated storage / file size có thể giữ nguyên
    ↓
Khoảng trống có thể được tái sử dụng cho ghi mới
~~~

Các thao tác như `compact`, `repairDatabase` hoặc xây dựng lại collection có thể có chi phí và ràng buộc vận hành, phụ thuộc phiên bản/topology. **Không chạy các lệnh bảo trì này chỉ để kiểm tra một bài thống kê.** Trong môi trường sản xuất, cần kế hoạch và tài liệu vận hành riêng.

### 12.1. Nếu muốn làm lại bộ dữ liệu

Để đưa document `order-005` trở lại như ví dụ ban đầu, chạy lại phần nạp `sampleOrders` ở mục 3 khi cần. Điều đó cũng sẽ khôi phục nội dung của bốn document mẫu khác. Không cần xóa cả database để hoàn thành bài.

## 13. Những lưu ý với sharding, replication và môi trường quản lý

### 13.1. Replica set

Replica set giữ nhiều bản sao dữ liệu để tăng khả dụng. Nếu một collection có ba bản sao, không thể lấy dung lượng logical data của một bản rồi nhân ba để gọi đó là dung lượng dữ liệu nghiệp vụ; con số nhân bản phản ánh một phần chi phí hạ tầng theo cấu hình.

Một primary và các secondary có thể khác nhau tạm thời về số liệu vận hành, thời điểm áp dụng thay đổi, vùng cấp phát và trạng thái bảo trì. Khi so sánh, cần ghi rõ node hay điểm truy cập đã dùng.

### 13.2. Sharded cluster

Ở sharded cluster, dữ liệu có thể được chia giữa nhiều shard. Lệnh thống kê qua `mongos` và stage `$collStats` có thể đưa ra số liệu hoặc cấu trúc kết quả theo phạm vi khác nhau. Tùy phiên bản, trường như `shard`, `host` có thể xuất hiện.

Vì vậy:

- Xác nhận metric đang là **tổng hợp toàn cluster** hay **theo từng shard**.
- Không cộng nhầm số liệu tổng hợp với chính số liệu thành phần.
- Không nhân các bản sao replica set để suy ra dung lượng logical.
- Khi collection vừa được reshard/migrate chunk, các số thống kê có thể dao động theo thời điểm đo.

### 13.3. MongoDB Atlas và dịch vụ quản lý

Atlas cung cấp các trang monitoring riêng cho storage, CPU, RAM, connections, IOPS hoặc tốc độ tăng dữ liệu theo gói dịch vụ/cluster. Các biểu đồ có thể dùng cách tổng hợp và khoảng thời gian khác với kết quả `dbStats` hay `collStats` tức thời.

Trong một số môi trường, command yêu cầu quyền cao hơn quyền đọc thông thường. Hãy mô tả lỗi quyền, account, database/collection và loại metric cần truy cập để người quản trị cấp quyền tối thiểu thích hợp.

## 14. Các lỗi và hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `show dbs` không thấy database vừa `use` | Database chưa có collection/dữ liệu hoặc quyền không đủ | Xác nhận dữ liệu đã được ghi; kiểm tra quyền |
| `getCollectionInfos()` trả mảng rỗng | Tên sai, sai database, đối tượng chưa tồn tại hoặc giới hạn quyền | Chạy `db.getName()`, `show collections`, kiểm tra tên chính xác |
| `collStats` báo namespace không tồn tại | Collection chưa được tạo hoặc đang chọn database khác | Kiểm tra `db.getCollectionInfos({name:"..."})` |
| `not authorized` khi gọi `dbStats` / `listCollections` | Role không có quyền xem metadata hoặc thống kê | Dùng tài khoản được cấp quyền phù hợp hoặc nhờ quản trị viên |
| `indexSize` khác `totalIndexSize` | Hai trường đến từ cấp database và cấp collection khác nhau | Chọn cùng phạm vi đo, cùng đơn vị |
| `storageSize` nhỏ hơn `size` | Nén dữ liệu và cách tổ chức lưu trữ | Không xem đây là lỗi, phân biệt logic và vật lý |
| Xóa dữ liệu mà `storageSize` không giảm | Storage engine giữ vùng cấp phát để tái sử dụng | Theo dõi nhiều kỳ; không suy ra dung lượng giải phóng từ count |
| Count trong Compass khác `countDocuments` | Hiển thị ước lượng, cache, bộ lọc, thời điểm khác nhau | Refresh, xác minh query và phạm vi |
| Không thấy trường `wiredTiger` hoặc các metric phụ | Khác storage engine/phiên bản/quyền | Chỉ dựa vào trường thực sự có trong output |
| `getIndexes()` cho biết nhiều index nhưng `$indexStats` ít truy cập | Index phục vụ workload hiếm, chưa phát sinh truy vấn hoặc stats reset | Quan sát dài hơn và kết hợp explain/query workload |
| Collection view bị coi như collection lưu trữ | Không kiểm tra `type: "view"` | Dùng `getCollectionInfos` và xác định collection nguồn |
| Tổng dung lượng các node cao hơn logical data | Dữ liệu được sao chép/ phân mảnh và có overhead | Phân biệt replicated storage với logical collection size |

## 15. Bài thực hành tổng hợp

Thực hiện tuần tự trong `metadata_lab`:

1. Dùng `db.getName()` xác nhận database đang chọn; dùng `show dbs` và `listDatabases` để nhận diện database được phép xem.
2. Liệt kê `show collections` và `db.getCollectionNames()`, sau đó dùng `db.getCollectionInfos()` phân biệt collection thông thường, collection có validator và view (nếu đã tạo).
3. Lấy `options` của `validatedOrders`. Giải thích `validator`, `validationLevel` và `validationAction`.
4. Chạy `dbStats` với `scale: 1024`, ghi lại `collections`, `objects`, `dataSize`, `storageSize` và `indexSize`.
5. Chạy `collStats` trên `demoOrders`, ghi lại `count`, `size`, `storageSize`, `nindexes` và `totalIndexSize`.
6. Gọi `db.demoOrders.getIndexes()`, phân biệt index mặc định `_id_` và index ghép `idx_status_createdAt`.
7. Gọi `$indexStats`; giải thích vì sao một index có `accesses.ops = 0` chưa đủ để quyết định xóa.
8. So sánh `countDocuments({})` và `estimatedDocumentCount()`; nêu ý nghĩa và giới hạn của mỗi cách.
9. Mở Compass, kiểm tra collection `demoOrders` và danh sách Indexes, đối chiếu với mongosh.
10. Xóa một document mẫu bằng `deleteOne`, đo lại count và `storageSize`; giải thích vì sao hai số không giảm cùng tỷ lệ.

Lệnh tham khảo để thực hiện nhanh:

~~~javascript
use metadata_lab

db.getName();
db.getCollectionNames();

db.getCollectionInfos({ name: "demoOrders" });
db.getCollectionInfos({ name: "validatedOrders" });

db.runCommand({ dbStats: 1, scale: 1024 });
db.runCommand({ collStats: "demoOrders", scale: 1024 });

db.demoOrders.getIndexes();
db.demoOrders.aggregate([{ $indexStats: {} }]);

db.demoOrders.countDocuments({});
db.demoOrders.estimatedDocumentCount();
~~~

### Câu hỏi kiểm tra hiểu biết

**Câu 1.** `db.getCollectionInfos({name:"demoOrders"})` và `db.runCommand({collStats:"demoOrders"})` khác nhau như thế nào?

*Đáp án:* Lệnh thứ nhất đọc metadata về đối tượng và tùy chọn cấu hình; lệnh thứ hai đọc thống kê count/dung lượng/index của collection.

**Câu 2.** `dataSize = 100 MiB` và `storageSize = 60 MiB` có nghĩa 40 MiB đã mất dữ liệu?

*Đáp án:* Không. Hai số đo các khía cạnh khác nhau: kích thước logic của document và vùng lưu trữ được cấp phát/ghi nhận, có thể chịu ảnh hưởng nén và overhead.

**Câu 3.** Có thể cộng dung lượng primary và secondary để tính logical size của một collection không?

*Đáp án:* Không. Các node replica giữ bản sao dữ liệu; nếu tính logical size theo nghiệp vụ, không được đếm các bản sao như dữ liệu độc lập.

**Câu 4.** `estimatedDocumentCount()` có thể đếm chính xác document `status: "PAID"` không?

*Đáp án:* Không. Hàm này không dùng filter để đếm theo điều kiện. Hãy dùng `countDocuments({status:"PAID"})` hoặc một aggregation phù hợp.

**Câu 5.** Tại sao `show collections` không đủ để quyết định đối tượng có storage riêng?

*Đáp án:* Danh sách tên có thể bao gồm view. Cần xem `type` trong metadata; view không có bộ document lưu riêng theo cách collection thông thường.

## 16. Kinh nghiệm khi đọc thông tin database trong dự án

- **Xác minh ngữ cảnh:** Kiểm tra host/cluster, `db.getName()`, namespace và quyền trước khi kết luận thống kê.
- **Đúng công cụ cho đúng câu hỏi:** `getCollectionInfos` đọc cấu hình; `getIndexes` đọc index definition; `dbStats`/`collStats` đọc dung lượng; `countDocuments` đếm theo filter.
- **Giữ đơn vị nhất quán:** Ghi rõ byte, KiB hay MiB; `1024` byte = `1 KiB` và `1.048.576` byte = `1 MiB`.
- **Phân biệt dung lượng logic và vật lý:** Dữ liệu BSON, index, allocated storage và dung lượng toàn máy chủ là các số đo khác nhau.
- **Cẩn trọng với snapshot:** Kết quả phụ thuộc thời điểm, quyền, phiên bản server, storage engine và topology.
- **Không can thiệp storage để “thử”:** Chỉ đo và diễn giải trong bài này; các tác vụ compaction, repair hoặc drop cần quy trình vận hành riêng.
- **Kết hợp chỉ số với workload:** Dung lượng index lớn hay số lượt sử dụng nhỏ không tự chứng minh index không cần thiết; kiểm tra truy vấn và mục tiêu nghiệp vụ.

Khi hiểu cấu trúc metadata và ý nghĩa của từng trường thống kê, bạn có thể đánh giá database MongoDB một cách có cơ sở: collection nào đang tồn tại, chúng được cấu hình ra sao, dữ liệu và index đang sử dụng tài nguyên thế nào, cũng như những giới hạn cần lưu ý khi so sánh các con số.
