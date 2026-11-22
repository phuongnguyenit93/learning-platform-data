# WiredTiger: document, index và tổ chức dữ liệu lưu trữ

Khi ứng dụng thực hiện `db.orders.findOne({ _id: ... })`, MongoDB không đơn giản mở một tệp JSON rồi tìm chuỗi văn bản. MongoDB nhận truy vấn, chọn cách truy cập dữ liệu, sử dụng các chỉ mục nếu phù hợp và yêu cầu **storage engine** đọc hoặc ghi những bản ghi tương ứng. **WiredTiger** là storage engine mặc định của các phiên bản MongoDB hiện đại, chịu trách nhiệm quan trọng trong việc tổ chức bản ghi, lưu chỉ mục, quản lý bộ nhớ đệm, nén trang dữ liệu, đồng thời hỗ trợ cơ chế ghi bền vững và phục hồi sau sự cố.

Nắm được cách WiredTiger xử lý document và index giúp giải thích nhiều hiện tượng thực tế: vì sao một truy vấn tìm vài document vẫn phải đọc rất nhiều dữ liệu, vì sao thêm index vừa cải thiện đọc vừa khiến ghi tốn chi phí hơn, vì sao xóa document không lập tức làm tệp dữ liệu nhỏ đi và vì sao dung lượng bộ nhớ ảnh hưởng rõ rệt đến tốc độ truy vấn.

## 1. Vị trí của WiredTiger trong kiến trúc MongoDB

**MongoDB** là hệ quản trị cơ sở dữ liệu hoàn chỉnh, còn **WiredTiger** là một thành phần trong `mongod` phụ trách lưu trữ và truy cập dữ liệu ở mức thấp. Các lớp này có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính |
|---|---|
| Client/driver | Gửi lệnh, nhận kết quả, quản lý kết nối, retry tùy cấu hình |
| MongoDB query layer | Phân tích truy vấn, chọn query plan, thực thi filter, sort, aggregation và các thao tác ở mức database |
| Collection/index catalog | Quản lý metadata của collection, index, tùy chọn và định danh nội bộ |
| WiredTiger storage engine | Tổ chức record store và index trên các cấu trúc lưu trữ, cache, page, compression, concurrency, checkpoint và journal |
| Hệ điều hành, hệ thống tệp, thiết bị lưu trữ | Cấp phát tệp và khối dữ liệu, filesystem cache, I/O và độ bền vật lý của thao tác ghi |

Luồng khái quát:

```text
          Ứng dụng / MongoDB Driver
                      |
                      v
            mongod: query layer
                      |
           Query planner / executor
                      |
            +---------+---------+
            |                   |
            v                   v
      Collection data        Index access
       (record store)       (index B-tree)
            |                   |
            +---------+---------+
                      v
                WiredTiger
             Cache / Pages / I/O
                      |
                      v
       Tệp dữ liệu và chỉ mục trên ổ đĩa
```

Đây là **sơ đồ khái niệm**. Query planner không nhất thiết đọc collection trước rồi mới đọc index: với truy vấn dùng index, luồng thông thường là định vị khóa trong index, lấy định danh bản ghi và chỉ đọc document cần thiết; một số truy vấn có thể được trả lời hoàn toàn từ index.

**Phân biệt ba thuật ngữ:**

- **Document** là đơn vị dữ liệu logic mà ứng dụng nhìn thấy qua MongoDB API. Document có thể lồng object, array và có `_id`.
- **Record** là đơn vị biểu diễn lưu trữ tương ứng với một document trong collection record store; MongoDB/WiredTiger dùng định danh bản ghi nội bộ (`RecordId`) khi liên kết dữ liệu với index.
- **Page** là đơn vị tổ chức bên trong cây lưu trữ của WiredTiger, chứa nhiều khóa/giá trị và metadata. Page không đồng nghĩa document; một page có thể chứa dữ liệu liên quan đến nhiều document, tùy kích thước và cách tổ chức.

## 2. Document BSON: lớp logic và biểu diễn lưu trữ

MongoDB hiển thị dữ liệu theo cú pháp gần JSON, nhưng biểu diễn chuẩn của document là **BSON (Binary JSON)**. BSON hỗ trợ những kiểu mà JSON thuần không thể mô tả trực tiếp, như `ObjectId`, `Date`, `Decimal128`, dữ liệu nhị phân và nhiều kiểu số.

Ví dụ trong `mongosh`:

```javascript
db.orders.insertOne({
  _id: ObjectId("65a12f010000000000000001"),
  customerId: "CUS-001",
  status: "PAID",
  createdAt: ISODate("2026-03-15T10:30:00Z"),
  amount: NumberDecimal("125000.50"),
  shipping: {
    city: "Hà Nội",
    method: "EXPRESS"
  },
  items: [
    { sku: "BK-01", quantity: 2, unitPrice: NumberDecimal("50000.00") },
    { sku: "PN-02", quantity: 1, unitPrice: NumberDecimal("25000.50") }
  ]
});
```

Ở mức API, dữ liệu là **một document** dù có nhiều object và phần tử mảng lồng nhau. Ở mức storage engine, WiredTiger lưu các bản ghi theo cấu trúc key–value nội bộ và đưa chúng vào các trang của một cây lưu trữ. Có thể hình dung collection record store như một ánh xạ:

```text
RecordId (khóa nội bộ)  --->  BSON document (giá trị)
```

`RecordId` là chi tiết triển khai nội bộ, **không phải `_id` của ứng dụng**. `_id` là trường trong document và thường có một unique index tự động; một bản ghi có thể được định vị bằng `RecordId` sau khi MongoDB đi qua index. Vì vậy, không được lấy `_id` làm bằng chứng rằng mọi document trong collection thường được sắp vật lý theo thứ tự `_id`.

Trong collection thông thường, thứ tự dữ liệu trên đĩa không phải một hợp đồng bảo đảm cho ứng dụng. Nếu muốn thứ tự kết quả ổn định, phải chỉ định `sort()`. **Clustered collection** là cơ chế đặc biệt có cách tổ chức dữ liệu theo clustered key; không nên dùng ngoại lệ này để suy diễn tổ chức mặc định của mọi collection.

### 2.1. Kích thước và chi phí của document

Mỗi BSON document có giới hạn kích thước **16 MiB**. Nhúng object và array thuận tiện để đọc theo một đơn vị nghiệp vụ, nhưng có ba hệ quả:

1. Document lớn khiến truy vấn phải truyền và xử lý nhiều byte hơn nếu không dùng projection phù hợp.
2. Array tăng không giới hạn có thể làm document phình to và gây cạnh tranh cập nhật trên một record.
3. Khi document thay đổi kích thước, storage engine có thể phải điều chỉnh cách biểu diễn trên page và ghi lại các vùng dữ liệu; không nên giả định update luôn là thay đổi vài byte tại chỗ.

Một document nhúng danh sách năm địa chỉ giao hàng có thể hợp lý; document nhúng hàng triệu sự kiện của một thiết bị thì thường không hợp lý. MongoDB cung cấp các mô hình như reference, bucket hoặc time-series collection để xử lý những dạng dữ liệu khác nhau.

## 3. Tổ chức dữ liệu trên đĩa: cây B-tree và file WiredTiger

WiredTiger tổ chức nhiều cấu trúc dữ liệu bằng các biến thể **B-tree**. Các page bên trong cây giúp định vị một dải khóa mà không cần đọc tất cả bản ghi từ đầu đến cuối.

```text
                      Root page
                    /           \
                   /             \
          Internal page       Internal page
          /     |    \         /     |    \
         v      v     v       v      v     v
       Leaf   Leaf   Leaf   Leaf   Leaf   Leaf
       page   page   page   page   page   page
         |      |      |      |      |      |
       Key/value entries (records hoặc index keys)
```

Các internal page lưu thông tin định tuyến tới page con; leaf page chứa các mục dữ liệu hoặc mục chỉ mục. Khi tìm khóa, hệ thống đi qua các tầng cây để đến vùng phù hợp. Page được giữ trong cache khi cần; page không có sẵn có thể phải được đọc từ ổ đĩa. Tùy thao tác, WiredTiger có thể tạo phiên bản cập nhật trong bộ nhớ và ghi page đã được xử lý xuống đĩa ở những thời điểm thích hợp.

**B-tree ở đây là cấu trúc nội bộ của storage engine**, không phải lời hứa về số cấp, kích thước page cố định hay thứ tự quét của `find()`. Các chi tiết có thể thay đổi theo phiên bản, cách nén và cấu hình.

### 3.1. Collection và index thường có cấu trúc lưu trữ riêng

Một database MongoDB có thể có nhiều collection; một collection có thể có nhiều index. Với cấu hình WiredTiger phổ biến, dữ liệu collection và từng index được lưu trong các tệp dạng:

```text
<dbPath>/
  WiredTiger.wt
  WiredTiger.turtle
  collection-<internal-id>.wt
  index-<internal-id>.wt
  index-<another-id>.wt
  journal/
    WiredTigerLog.<number>
  ...
```

Sơ đồ trên **chỉ mang tính minh họa**, không phải danh sách tệp bắt buộc cho mọi phiên bản hoặc cấu hình. MongoDB còn có các tệp catalog, metadata và trạng thái riêng; vị trí tệp có thể thay đổi khi dùng những tùy chọn đường dẫn hoặc cơ chế quản lý lưu trữ khác. `WiredTiger.wt` cũng không phải tệp tổng hợp duy nhất chứa mọi JSON document.

Tên dạng `collection-...` hoặc `index-...` dùng định danh nội bộ, không trực tiếp đặt theo tên `orders` hay `customers`. MongoDB quản lý ánh xạ từ collection/index logic đến cấu trúc lưu trữ. **Không chỉnh tay các tệp `.wt`** để sửa document hoặc index: thao tác hợp lệ phải thông qua giao thức MongoDB và quy trình backup/restore được hỗ trợ.

### 3.2. Dữ liệu đã xóa có thể vẫn chiếm dung lượng file

Khi xóa document, không nên kỳ vọng dung lượng tệp `.wt` trên filesystem sẽ giảm ngay. WiredTiger có thể giữ lại vùng trống để tái sử dụng cho các lần ghi tiếp theo. Các chỉ số như **logical data size**, **allocated storage size**, **free/reusable space** và dung lượng thực tế của hệ thống tệp đo những khía cạnh khác nhau.

Nếu cần thu hồi dung lượng cho hệ điều hành, phải tìm hiểu giải pháp `compact`, resync hoặc tái xây dựng phù hợp với phiên bản, workload, replication và môi trường; không nên coi `deleteMany()` là thao tác thu nhỏ file ngay lập tức.

## 4. Index lưu gì, vì sao index giúp truy vấn nhanh?

Index là cấu trúc giúp MongoDB tìm document theo khóa truy vấn mà không phải luôn quét toàn collection. Với **B-tree index thông thường**, có thể hình dung mục index là:

```text
Giá trị khóa index  --->  RecordId của document tương ứng

"CUS-001"            ->  R101
"CUS-002"            ->  R208
"CUS-003"            ->  R315
```

Hình minh họa bỏ qua các chi tiết mã hóa khóa, thứ tự, uniqueness và cách triển khai nội bộ. Index được duy trì **riêng với collection record store**. Nếu document đổi một trường đã lập chỉ mục, MongoDB phải duy trì những index tương ứng, bên cạnh việc ghi document.

Mỗi collection thông thường có index unique trên `_id` do MongoDB tạo mặc định. Ứng dụng có thể tạo thêm index phục vụ các truy vấn cụ thể:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find(
  { customerId: "CUS-001" },
  { status: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(10);
```

Với index `{ customerId: 1, createdAt: -1 }`, MongoDB có thể đi tới vùng có `customerId = "CUS-001"` rồi đọc theo thứ tự `createdAt` giảm dần. Điều này thường hiệu quả hơn việc quét mọi đơn hàng, lọc xong mới sắp xếp, đặc biệt khi tập dữ liệu lớn và truy vấn chọn lọc. Tuy nhiên, query planner là thành phần quyết định có sử dụng index đó hay không.

### 4.1. Collection scan, index scan và fetch document

Giả sử collection có hàng triệu đơn hàng nhưng chỉ vài chục đơn thuộc một khách hàng:

```text
Không dùng index:
  COLLECTION SCAN -> đọc/kiểm tra nhiều record -> lọc -> sort -> kết quả

Dùng index phù hợp:
  INDEX SCAN -> lấy RecordId phù hợp -> FETCH document -> kết quả

Truy vấn được index bao phủ:
  INDEX SCAN -> lấy đủ trường trả về từ index -> kết quả
```

Trong `explain()`, các tên stage dễ gặp gồm `COLLSCAN`, `IXSCAN`, `FETCH`; biểu diễn cụ thể còn tùy query engine và phiên bản. **Index scan không đồng nghĩa mọi byte của document đều đã nằm trong index**. Nếu projection yêu cầu `status` nhưng index chỉ có `customerId` và `createdAt`, MongoDB thường cần đọc document để lấy `status`.

### 4.2. Covered query: khi chỉ cần đọc index

Một truy vấn có thể chỉ lấy các trường đã nằm trong index:

```javascript
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });

db.orders.find(
  { customerId: "CUS-001", status: "PAID" },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }
).sort({ createdAt: -1 });
```

Index chứa các trường lọc, sắp xếp và projection; `_id: 0` tránh yêu cầu trường `_id` vốn không nằm trong index vừa tạo. Trong điều kiện phù hợp, query planner có thể trả dữ liệu từ index mà không cần fetch document. Khả năng **cover** phụ thuộc kiểu index, điều kiện truy vấn, array/multikey, cách projection và plan thực tế; phải xem `explain()` thay vì giả định rằng cứ đủ tên trường là chắc chắn covered.

### 4.3. Compound index và thứ tự khóa

Với index ghép `{ customerId: 1, status: 1, createdAt: -1 }`, thứ tự sắp xếp vật lý của khóa trước hết theo `customerId`, tiếp đến `status`, rồi `createdAt`. Vì vậy, thứ tự trường ảnh hưởng đáng kể đến truy vấn có thể được phục vụ hiệu quả.

Một nguyên tắc thiết kế hữu ích là **Equality → Sort → Range (ESR)**: ưu tiên các trường được so sánh bằng, tiếp theo là trường dùng cho sắp xếp, rồi trường dùng cho khoảng giá trị. Đây là heuristic để đề xuất index ban đầu, không thay cho việc đo thực tế; đôi khi range rất chọn lọc lại nên xuất hiện sớm hơn.

Ví dụ:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});

db.orders.find({
  customerId: "CUS-001",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-01-01T00:00:00Z") }
}).sort({ createdAt: -1 });
```

**Quy tắc prefix:** index ghép có thể hỗ trợ các truy vấn dựa trên phần tiền tố của khóa, nhưng hiệu quả khi chỉ lọc theo trường ở cuối index có thể thấp. Ví dụ index bắt đầu bằng `customerId` không thường là giải pháp đầu tiên cho báo cáo chỉ lọc `status` trên mọi khách hàng.

### 4.4. Multikey index cho array

Vì document BSON có array, MongoDB có thể dùng **multikey index** để truy vấn theo từng giá trị trong mảng:

```javascript
db.orders.createIndex({ "items.sku": 1 });

db.orders.find({ "items.sku": "BK-01" });
```

Với array các object, index có thể tạo mục khóa liên quan đến từng `sku` trong `items`. Một document vẫn là một document logic; index chỉ làm tăng số mục để phục vụ tìm kiếm. Hệ quả là array lớn có thể khiến index phình to, chi phí cập nhật cao và quy tắc compound multikey phức tạp hơn (chẳng hạn các hạn chế khi nhiều trường index đều là array). Khi cần khớp nhiều điều kiện thuộc **cùng một phần tử mảng**, phải xét `$elemMatch` thay vì nối điều kiện độc lập một cách máy móc.

### 4.5. Một số loại index khác

MongoDB còn hỗ trợ những loại index/phương thức truy vấn chuyên biệt như TTL, partial, sparse, unique, text, geospatial, hashed và các tùy chọn khác tùy phiên bản/sản phẩm. Không phải mọi loại đều có semantics truy vấn giống hệt index B-tree đơn trường thông thường. Đặc biệt, **TTL index** yêu cầu quy trình xóa nền và không bảo đảm document biến mất chính xác tại mili-giây hết hạn; **unique index** giúp cưỡng chế duy nhất ở mức database cho tổ hợp khóa được lập chỉ mục.

## 5. Cache: điều gì xảy ra giữa RAM và ổ đĩa?

WiredTiger duy trì một **internal cache** chứa page dữ liệu và index đang được sử dụng. Hệ điều hành đồng thời có thể duy trì **filesystem cache** cho dữ liệu đọc/ghi qua hệ thống tệp. Hai lớp cache có mục đích và cách quản lý khác nhau; không nên cộng dung lượng của chúng như thể đều là bộ nhớ hoàn toàn trống hoặc được ứng dụng tự kiểm soát.

```text
Query / Update
      |
      v
WiredTiger cache (pages đang dùng)
      |                 ^
      | cache miss      | page load / decompression
      v                 |
Filesystem cache / I/O layer
      |                 ^
      v                 |
Compressed on-disk pages (.wt)
```

Khi truy vấn dùng index:

1. MongoDB cần các page index để định vị vùng khóa.
2. Nếu phải fetch document, nó cần thêm các page của collection.
3. Page đang có trong WiredTiger cache tránh được một phần chi phí I/O và giải nén.
4. Nếu cache miss, hệ thống phải lấy dữ liệu từ các lớp bên dưới; tùy tình trạng filesystem cache, có thể cần truy cập thiết bị lưu trữ thật.

**Working set** là tập dữ liệu và chỉ mục được truy cập thường xuyên trong khoảng thời gian thực tế. Nếu working set vừa bộ nhớ và tập truy vấn ổn định, hiệu năng đọc thường tốt hơn. Nếu working set lớn hơn cache, các page phải liên tục được nạp/thay thế, có thể dẫn đến nhiều I/O và độ trễ cao.

### 5.1. Eviction và dirty pages

Page mới đọc hoặc page vừa được sửa có thể lưu trong WiredTiger cache. **Dirty page** là page có thay đổi chưa được phản ánh hoàn toàn vào trạng thái dữ liệu bền vững tương ứng trên đĩa. WiredTiger cần cơ chế **eviction** để giải phóng cache và quản lý các page cũ/ít sử dụng; quá trình này có thể liên quan đến reconcile hoặc ghi page xuống tầng lưu trữ tùy trạng thái.

Nhiều thao tác ghi trên cùng vùng dữ liệu hoặc quá nhiều index tạo ra áp lực cache/I/O. Vì vậy một hệ thống còn nhiều RAM tổng thể vẫn có thể gặp áp lực WiredTiger cache, còn hệ thống dùng nhiều RAM chưa chắc đang rò rỉ bộ nhớ.

### 5.2. Nén dữ liệu và chỉ mục

WiredTiger có các kỹ thuật nén để giảm dung lượng trên đĩa. Cơ chế thông dụng gồm:

- **Block/page compression cho collection:** MongoDB thường dùng Snappy theo mặc định với WiredTiger, nhưng lựa chọn có thể được cấu hình, ví dụ `zlib`, `zstd` hoặc không nén khi được hỗ trợ.
- **Prefix compression cho khóa index:** các khóa có chung tiền tố có thể được biểu diễn tiết kiệm hơn, nhất là index có nhiều giá trị đầu khóa lặp lại.
- **Journal compression:** cơ chế nén journal có lựa chọn và cấu hình riêng; không nên suy luận compressor journal bằng compressor của collection.

Compression giảm byte đọc/ghi đĩa, nhưng tiêu tốn CPU khi nén/giải nén. Với dữ liệu lặp và đĩa chậm, nén thường có lợi; với dữ liệu vốn đã nén hoặc workload bị giới hạn CPU, lợi ích thay đổi. **Tỷ lệ nén không thể suy ra chỉ từ số document**, vì còn phụ thuộc kiểu trường, giá trị lặp, index và kích thước page.

## 6. Cơ chế ghi: từ update đến journal và checkpoint

Giả sử ứng dụng cập nhật trạng thái đơn hàng:

```javascript
db.orders.updateOne(
  { _id: ObjectId("65a12f010000000000000001") },
  { $set: { status: "SHIPPED" } }
);
```

Ở mức khái niệm, thao tác sẽ tìm document (thường qua `_id` index), kiểm tra điều kiện và thay đổi bản ghi. Nếu trường cập nhật thuộc một hay nhiều index, các mục index liên quan cũng cần được cập nhật. WiredTiger quản lý phiên bản/đồng thời của các thay đổi, dirty pages, log phục hồi và việc ghi những thay đổi ra trạng thái lưu trữ lâu dài.

```text
Ghi document
     |
     +--> Thay đổi record / index trong phiên bản và cache
     |
     +--> Journal / recovery log theo chế độ và thời điểm ghi
     |
     +--> Checkpoint định kỳ tạo điểm khôi phục trên đĩa
     |
     +--> Replication là cơ chế độc lập ở mức MongoDB
```

Sơ đồ thể hiện các trách nhiệm, **không phải cam kết về thứ tự chính xác của mọi byte ghi**. Khi client được xác nhận thành công phụ thuộc `writeConcern`, journaling và trạng thái replication; không thể suy ra “đã an toàn khỏi mọi sự cố” chỉ từ một lệnh trả về thành công theo cấu hình mặc định bất kỳ.

### 6.1. Journal: phục hồi sau sự cố

**Journal** là cơ chế log phục hồi liên quan đến thay đổi đã ghi. Nó cho phép WiredTiger phục hồi các thao tác đủ điều kiện sau khi quá trình `mongod` hoặc máy chủ bị dừng đột ngột, dựa trên trạng thái checkpoint và log tương ứng. Tư duy cơ bản tương tự write-ahead logging: dữ liệu phục hồi cần được lưu bền vững theo quy tắc phù hợp trước khi coi cập nhật đã durable.

Ví dụ lệnh ghi có yêu cầu journal:

```javascript
db.runCommand({
  update: "orders",
  updates: [{
    q: { _id: ObjectId("65a12f010000000000000001") },
    u: { $set: { status: "SHIPPED" } }
  }],
  writeConcern: { w: 1, j: true }
});
```

Với `j: true`, client yêu cầu xác nhận liên quan đến việc ghi journal bền vững theo semantics của MongoDB/WiredTiger. Nhưng `w: 1` **không yêu cầu một đa số replica đã nhận dữ liệu**. Nhu cầu durability và khả năng chịu lỗi nút phải được xét cùng `w`, `j`, replica set và chính sách backup; các lựa chọn mặc định có thể phụ thuộc cấu hình/phiên bản.

### 6.2. Checkpoint: điểm khởi đầu để khôi phục

**Checkpoint** đưa trạng thái lưu trữ về một điểm nhất quán có thể dùng cho recovery trên đĩa. WiredTiger tạo checkpoint định kỳ hoặc theo sự kiện/cấu hình; không cần đợi mọi page dirty trở thành clean trước mỗi lần client đọc được dữ liệu mới.

Sau sự cố, storage engine có thể khôi phục từ checkpoint hợp lệ rồi áp dụng các log cần thiết. Vì vậy, checkpoint và journal **bổ sung cho nhau**:

| Khái niệm | Mục tiêu | Không thay thế được |
|---|---|---|
| WiredTiger checkpoint | Điểm nhất quán phục vụ lưu trữ và recovery | Bản sao lưu độc lập, replication, khả năng khôi phục khi toàn bộ ổ đĩa hỏng |
| WiredTiger journal | Ghi nhận thay đổi phục vụ phục hồi sau crash | Backup lịch sử, replica ở máy khác |
| MongoDB replication / oplog | Nhân bản các thay đổi sang thành viên khác và hỗ trợ đồng bộ | Tự động có bản backup chống xóa nhầm hoặc ransomware |
| Backup/PITR phù hợp | Phục hồi theo yêu cầu từ bản sao lưu, có thể tới một thời điểm | Tối ưu truy vấn hoặc thay thế trực tiếp cơ chế transaction |

Không nên chỉ sao chép vài tệp `.wt` khi `mongod` đang hoạt động rồi xem đó là bản backup nhất quán. Hãy dùng cơ chế snapshot/backup được MongoDB hỗ trợ, có tính đến journal, metadata và kiến trúc triển khai.

### 6.3. Cập nhật đồng thời và transaction

WiredTiger sử dụng các kỹ thuật kiểm soát đồng thời theo hướng **optimistic concurrency** đối với dữ liệu document; MongoDB cũng có những lớp khóa/điều phối ở cấp cao hơn. Nhiều thao tác trên những document khác nhau có thể tiến hành đồng thời. Khi hai thao tác tranh chấp thay đổi, MongoDB có thể phát hiện write conflict và retry trong những ngữ cảnh phù hợp hoặc báo lỗi để ứng dụng xử lý.

**Một thao tác ghi trên một document là nguyên tử** theo contract MongoDB. Nếu nghiệp vụ phải cập nhật nhiều document/collection như tạo đơn + trừ kho, cần cân nhắc multi-document transaction với điều kiện triển khai được hỗ trợ, chi phí của transaction và xử lý retry. Đây là đặc tính của MongoDB phối hợp với storage engine, không phải chức năng của một tệp B-tree đơn lẻ.

## 7. Đường đi thực tế của một truy vấn và một lần ghi

Hãy đặt các khái niệm vừa học vào hai tình huống:

### 7.1. Truy vấn theo khách hàng và thời gian

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({
  customerId: "CUS-001",
  createdAt: { $gte: ISODate("2026-03-01T00:00:00Z") }
}).sort({ createdAt: -1 }).limit(20);
```

1. Query layer nhận bộ lọc, `sort` và `limit`.
2. Planner có thể chọn compound index khi ước lượng chi phí tốt hơn collection scan.
3. WiredTiger cung cấp các index page chứa khóa ở vùng `CUS-001`.
4. Các mục index cho biết record nào cần lấy; nếu cần trường ngoài index, engine truy xuất page chứa document.
5. Kết quả được giải mã BSON và trả về driver; `limit(20)` giới hạn số document trả về, nhưng không phải luôn giới hạn số index entry phải xét đúng bằng 20.

Độ trễ tăng khi phải fetch nhiều document nằm rải rác trên nhiều page lạnh, khi có sort không được index hỗ trợ hoặc khi index không đủ chọn lọc. Vì vậy, **tối ưu index** phải xét cả số khóa quét, số document fetch và số byte truyền về.

### 7.2. Ghi thêm đơn hàng có nhiều index

Giả sử `orders` có index trên `_id`, `{ customerId, createdAt }`, `status` và `items.sku`. Khi insert một đơn hàng chứa ba dòng hàng:

1. MongoDB chuẩn bị record BSON cho document.
2. Record store ghi bản ghi logic mới.
3. Các index liên quan phải tạo khóa mới; multikey index có thể phát sinh nhiều mục từ mảng `items`.
4. WiredTiger quản lý các thay đổi trong cache, log và cơ chế checkpoint/recovery phù hợp.
5. MongoDB xác nhận cho client theo write concern của thao tác.

Thêm index giúp đọc theo nhiều kiểu truy vấn, **nhưng mọi thao tác insert/update/delete phải duy trì chúng**. Một index không còn được workload sử dụng vẫn có thể tiêu tốn dung lượng, RAM và I/O khi ghi. Do đó, “càng nhiều index càng nhanh” là kết luận sai.

## 8. Quan sát và giải thích hành vi WiredTiger

Các công cụ của MongoDB giúp liên hệ kiến trúc với dữ liệu thực tế. Những lệnh dưới đây minh họa dùng trong `mongosh`; quyền truy cập, tên trường và thống kê sẵn có có thể thay đổi theo phiên bản/sản phẩm.

### 8.1. Kiểm tra index đang có

```javascript
db.orders.getIndexes();
```

Kết quả cho biết khóa index, tên, uniqueness và các option liên quan. Dùng thông tin này để giải thích vì sao một query có thể hoặc không thể dùng một index mong đợi.

### 8.2. Xem query plan và lượng dữ liệu quét

```javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Nên chú ý những ý nghĩa sau:

| Chỉ số / stage | Câu hỏi cần trả lời |
|---|---|
| `winningPlan` | Planner chọn phương án truy vấn nào? |
| `IXSCAN` | Có dùng index phù hợp không, đang quét index nào? |
| `COLLSCAN` | Có phải kiểm tra collection theo kiểu quét không? |
| `FETCH` | Có cần đọc toàn bộ document sau khi đi qua index không? |
| `totalKeysExamined` | Bao nhiêu mục khóa index đã được kiểm tra? |
| `totalDocsExamined` | Bao nhiêu document được xem xét? |
| `nReturned` | Có bao nhiêu document được trả ra? |
| `executionTimeMillis` | Thời gian ghi nhận trong thống kê thực thi; cần đo lặp và hiểu tác động của môi trường |

Những trường hợp nên tìm nguyên nhân gồm `totalKeysExamined` hoặc `totalDocsExamined` lớn hơn nhiều so với `nReturned`, hoặc truy vấn cần `COLLSCAN` và sort tốn tài nguyên. Không cần ép mọi truy vấn dùng index: quét collection có thể hợp lý với collection rất nhỏ hoặc truy vấn trả về phần lớn dữ liệu.

### 8.3. Quan sát dung lượng collection và index

```javascript
db.orders.stats();
db.orders.totalIndexSize();
db.orders.dataSize();
db.orders.storageSize();
```

`dataSize` phản ánh dung lượng dữ liệu logic theo cách MongoDB thống kê; `storageSize` liên quan dung lượng được cấp phát cho collection; `totalIndexSize` phản ánh không gian dùng cho index. Chúng **không nhất thiết cộng lại thành đúng dung lượng trên đĩa** vì còn metadata, journal, vùng trống tái sử dụng, nén, snapshot và overhead khác.

### 8.4. Quan sát cache và trạng thái server

```javascript
const status = db.serverStatus();
status.wiredTiger?.cache;
```

Trong môi trường có quyền xem `serverStatus`, thống kê WiredTiger có thể cung cấp dữ liệu về cache, pages, eviction và I/O liên quan. Không nên dựa vào một tên counter duy nhất qua mọi phiên bản mà không kiểm tra schema hiện hành. Khi phân tích sự cố, đặt số liệu cache cạnh CPU, disk read/write latency, tốc độ ghi, query latency, kích thước index và thời điểm checkpoint.

## 9. Các hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Mỗi document được lưu thành một file JSON.” | Document BSON là bản ghi logic; WiredTiger lưu nhiều bản ghi trong các page/cấu trúc dữ liệu trên tệp lưu trữ. |
| “`_id` chính là địa chỉ vật lý của bản ghi.” | `_id` là khóa ứng dụng/index; storage engine có định danh record nội bộ và có thể thay đổi bố trí vật lý. |
| “Index lưu bản sao toàn bộ document.” | B-tree index thông thường giữ khóa và thông tin để định vị record; chỉ những truy vấn phù hợp mới được index bao phủ. |
| “MongoDB luôn trả document theo thứ tự chèn hoặc `_id`.” | Muốn thứ tự có hợp đồng ổn định phải dùng `sort()`; thứ tự lưu trữ không bảo đảm thứ tự kết quả mặc định. |
| “Index chỉ làm đọc nhanh mà không có chi phí.” | Index tiêu tốn dung lượng và cần cập nhật theo từng thao tác ghi liên quan. |
| “Thêm RAM cho máy nghĩa là toàn bộ dữ liệu đã nằm trong WiredTiger cache.” | Cache có giới hạn/cơ chế riêng, filesystem cache là lớp khác, working set và eviction mới quyết định hiệu quả. |
| “Xóa document sẽ lập tức giảm dung lượng file.” | Vùng trống có thể được giữ lại để tái sử dụng; cách thu hồi về OS phụ thuộc cơ chế lưu trữ. |
| “Checkpoint, journal, replica và backup là một.” | Đây là các lớp bảo vệ với mục đích khác nhau; không thể thay thế hoàn toàn cho nhau. |
| “Mọi truy vấn `IXSCAN` đều nhanh.” | Index kém chọn lọc, scan nhiều key hoặc fetch nhiều document vẫn có thể tốn chi phí. |

## 10. Hướng dẫn thiết kế để tận dụng WiredTiger

Khi xây collection MongoDB, nên đi từ truy vấn và vòng đời dữ liệu trước khi nghĩ đến cấu trúc file:

1. **Chọn ranh giới document theo nghiệp vụ.** Nhúng thành phần được đọc/cập nhật cùng nhau với số lượng có giới hạn; tham chiếu phần tăng không giới hạn hoặc có vòng đời độc lập.
2. **Lập index theo query thật.** Liệt kê các filter, sort, range và projection có tần suất cao; thử compound index đúng thứ tự trường và quan sát bằng `explain()`.
3. **Kiểm soát số lượng index.** Unique, TTL, multikey, compound index đều có giá; tránh index trùng lặp hoặc không được dùng.
4. **Theo dõi working set.** Đọc dữ liệu và index cùng cache khi tải tăng; đo disk I/O và eviction trước khi kết luận vấn đề do CPU hay do thiếu RAM.
5. **Tính đến compression và dạng dữ liệu.** BSON có overhead của trường và giá trị; khả năng nén không giống nhau giữa dữ liệu lặp, dữ liệu ngẫu nhiên và dữ liệu đã nén.
6. **Phân biệt durability với replication.** Xác định `writeConcern`, journal, backup và mục tiêu khôi phục theo giá trị nghiệp vụ của dữ liệu.
7. **Đo lại sau thay đổi mô hình.** Mỗi thay đổi embedding, array, compound index hoặc workload ghi đều có thể thay đổi I/O, cache pressure và thời gian thực thi.

## 11. Bài tập thực hành

### Bài 1: So sánh query trước và sau khi có index

Tạo collection thử nghiệm với nhiều đơn hàng có `customerId`, `createdAt`, `status`. Thực hiện:

```javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");

db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(10)
  .explain("executionStats");
```

Ghi lại `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`. Giải thích vì sao index mới có thể giảm số document phải xét và tránh sort bổ sung; nếu kết quả không đổi hoặc collection quá nhỏ, giải thích vì sao planner có thể không chọn index.

### Bài 2: Covered query

Tạo index `{ customerId: 1, status: 1, createdAt: -1 }`. So sánh hai projection: một projection chỉ chứa các trường trên (và loại `_id`), một projection thêm `shipping.city`. Dùng `explain("executionStats")` để xem kế hoạch có cần fetch document hay không.

### Bài 3: Multikey và document lớn

Thiết kế collection cho bài viết có thể có hàng trăm nghìn bình luận. Giải thích vì sao không nên nhúng tất cả vào một array. Đề xuất `comments` collection riêng với các trường `postId`, `createdAt`, `authorId`, `content` và index hỗ trợ lấy 20 bình luận mới nhất theo bài viết.

### Bài 4: Xóa dữ liệu và dung lượng ổ đĩa

Trong môi trường thử nghiệm, ghi dữ liệu đủ lớn rồi quan sát `stats()`, `dataSize()`, `storageSize()` và dung lượng file trước/sau khi xóa nhiều document. Giải thích vì sao kích thước logic có thể giảm trong khi vùng lưu trữ được cấp phát chưa giảm tương ứng. Không chạy compact hoặc thay đổi tệp WiredTiger thủ công trên môi trường production.

### Bài 5: Phục hồi sau sự cố

Phân biệt bốn câu hỏi sau: “ghi đã tới cache?”, “ghi đã đáp ứng journal durability?”, “đa số replica đã xác nhận?”, “có thể khôi phục đơn bị xóa nhầm hôm qua?”. Gán từng câu hỏi với WiredTiger cache, journal/write concern, replication và backup/PITR; giải thích vì sao mỗi cơ chế chỉ giải quyết một phần yêu cầu.

## Kết luận

MongoDB cung cấp cách nhìn **document BSON và collection** cho lập trình viên; WiredTiger quản lý biểu diễn vật lý của **record store, index và các page B-tree**, cùng với cache, nén, concurrency, journal và checkpoint. Index định vị document hiệu quả hơn khi khóa phù hợp với filter/sort; cache giảm truy cập đĩa; nén giảm dung lượng; journal và checkpoint hỗ trợ phục hồi. Mỗi cơ chế đều có chi phí và phạm vi bảo đảm riêng.

Hiểu đúng ranh giới giữa **document logic**, **index tra cứu** và **page lưu trữ** giúp thiết kế mô hình dữ liệu, chọn index và điều tra hiệu năng MongoDB dựa trên dữ liệu đo được, thay vì dựa vào giả định về những tệp `.wt` nằm dưới `dbPath`.
